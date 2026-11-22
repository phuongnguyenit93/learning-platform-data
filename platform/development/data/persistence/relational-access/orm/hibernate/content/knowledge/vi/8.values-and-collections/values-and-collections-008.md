# Khóa ánh xạ, giá trị ánh xạ và tập hợp đối tượng nhúng

Trong Hibernate/JPA, dữ liệu thuộc về một entity không phải lúc nào cũng là một field đơn giản hoặc một quan hệ đến entity khác. Ứng dụng có thể cần lưu **bảng ánh xạ `Map<K, V>`**, ví dụ các tùy chọn cấu hình theo tên khóa, hoặc **tập hợp những giá trị nhúng `@Embeddable`**, ví dụ danh sách địa chỉ giao hàng của một khách hàng.

Có ba điều cần hiểu rõ:

1. **Khóa ánh xạ (map key)** xác định phần tử theo khóa trong Java `Map`. Nó có thể được lưu ở một cột riêng, lấy từ thuộc tính của entity làm value hoặc được biểu diễn bằng nhiều cột nếu khóa là object nhúng.
2. **Giá trị ánh xạ (map value)** là dữ liệu nằm ở mỗi entry của `Map`. Value có thể là kiểu cơ bản, `@Embeddable` hoặc entity tùy thiết kế.
3. **Tập hợp đối tượng nhúng** dùng `@ElementCollection` và `@Embeddable` để lưu nhiều value object phụ thuộc vào chủ sở hữu, thường trong một bảng phụ không có vòng đời entity độc lập.

Bài học trình bày sơ đồ lưu trữ, các annotation JPA, ví dụ Java/SQL, truy vấn, vòng đời dữ liệu, hiệu năng và cách chọn mô hình thích hợp.

## 1. Bắt đầu từ mô hình Java và mô hình quan hệ

Giả sử người dùng có các tùy chọn hiển thị:

~~~java
Map<String, String> preferences = Map.of(
    "theme", "dark",
    "language", "vi",
    "pageSize", "20"
);
~~~

Trong bộ nhớ, dữ liệu gồm các cặp `key -> value`. Database quan hệ không có cột chung mặc định cho một `Map` có số entry thay đổi; cách ánh xạ thường gặp là thêm bảng phụ.

| account_id | setting_key | setting_value |
| ---: | --- | --- |
| 10 | theme | dark |
| 10 | language | vi |
| 10 | pageSize | 20 |
| 11 | theme | light |

Với thiết kế này:

- `account_id` là **khóa ngoại chỉ về entity chủ**.
- `setting_key` lưu **Map key**.
- `setting_value` lưu **Map value**.
- Cặp `(account_id, setting_key)` nên là duy nhất để cùng một chủ sở hữu không có hai hàng cho cùng khóa.

Đối với `List<Address>`, bảng phụ thường có các cột của từng đối tượng `Address` cùng khóa ngoại chỉ về chủ sở hữu; nếu cần lưu thứ tự List, có thể có thêm cột vị trí.

~~~mermaid
erDiagram
    USER_ACCOUNT ||--o{ ACCOUNT_PREFERENCE : has
    USER_ACCOUNT {
        bigint id PK
        string username
    }
    ACCOUNT_PREFERENCE {
        bigint account_id FK
        string setting_key
        string setting_value
    }
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : has
    CUSTOMER {
        bigint id PK
        string full_name
    }
    CUSTOMER_ADDRESS {
        bigint customer_id FK
        int address_position
        string street
        string city
        string postal_code
    }
~~~

Cách thể hiện này nhấn mạnh rằng **bảng phụ có thể chỉ chứa value object thuộc một entity**, không nhất thiết tương ứng với lớp `@Entity` riêng.

## 2. Phân biệt @ElementCollection, @Embeddable và các quan hệ entity

Trước khi viết mapping, xác định loại dữ liệu muốn lưu.

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `@Entity` | Đối tượng có danh tính persistent và vòng đời riêng | `Customer`, `Product`, `OrderLine` |
| `@Embeddable` | Kiểu giá trị được nhúng vào entity hoặc collection; không có identity entity độc lập | `PostalAddress`, `Money`, `Coordinates` |
| `@Embedded` | Một thuộc tính đơn có kiểu embeddable, thường lưu cùng hàng với entity chủ | `Customer.billingAddress` |
| `@ElementCollection` | Collection của các giá trị cơ bản hoặc embeddable | `Set<String>`, `List<PostalAddress>`, `Map<String, String>` |
| `@OneToMany` / `@ManyToMany` | Quan hệ giữa các entity có identity | `Order.lines`, `Project.members` |

Một `@Embeddable` **không tự trở thành entity** vì có nhiều field. Nó không có `@Id` riêng theo mô hình entity. Nếu một địa chỉ cần được chia sẻ bởi nhiều khách hàng, cần được tìm bằng ID và có vòng đời độc lập, ánh xạ địa chỉ thành entity sẽ phù hợp hơn.

`@ElementCollection` cho biết các phần tử phụ thuộc vào chủ sở hữu: Hibernate quản lý lưu/xóa chúng trong ngữ cảnh của collection thuộc entity chủ. Những phần tử này không được truy xuất độc lập bằng `EntityManager.find(Address.class, id)` như entity có khóa chính.

## 3. Ánh xạ Map<String, String> với @ElementCollection

Đây là trường hợp đơn giản nhất: map key và map value đều là kiểu cơ bản.

~~~java
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.MapKeyColumn;
import jakarta.persistence.Table;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "account_preferences",
        joinColumns = @JoinColumn(name = "account_id")
    )
    @MapKeyColumn(name = "setting_key", nullable = false)
    @Column(name = "setting_value", nullable = false)
    private Map<String, String> preferences = new LinkedHashMap<>();

    protected UserAccount() {}

    public UserAccount(String username) {
        this.username = username;
    }

    public Long getId() {
        return id;
    }

    public Map<String, String> getPreferences() {
        return preferences;
    }

    public void putPreference(String key, String value) {
        preferences.put(
            Objects.requireNonNull(key),
            Objects.requireNonNull(value)
        );
    }

    public void removePreference(String key) {
        preferences.remove(key);
    }
}
~~~

Trong ví dụ:

- `@ElementCollection`: collection chứa các **basic values** (`String`); không tạo entity cho mỗi entry.
- `@CollectionTable`: các entry nằm trong bảng `account_preferences`.
- `@JoinColumn(name = "account_id")`: cột tham chiếu `user_accounts.id`.
- `@MapKeyColumn(name = "setting_key")`: **khóa của Map** được lưu ở cột `setting_key`.
- `@Column(name = "setting_value")`: **giá trị của Map** được lưu ở cột `setting_value`.
- `FetchType.LAZY`: ưu tiên nạp collection khi cần, dù việc trì hoãn thực tế tùy provider.
- `LinkedHashMap`: tạo một Map có thứ tự duyệt theo insertion order trong Java; **không tự bảo đảm thứ tự hàng sau khi load từ database**.

Cần tránh nhầm `@Column` với `@MapKeyColumn`. Chúng không chỉ tới cùng một cột.

### 3.1. DDL minh họa

Một schema có thể được tạo bởi migration:

~~~sql
CREATE TABLE user_accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE account_preferences (
    account_id BIGINT NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value VARCHAR(500) NOT NULL,
    CONSTRAINT fk_preference_account
        FOREIGN KEY (account_id) REFERENCES user_accounts(id),
    CONSTRAINT pk_account_preference
        PRIMARY KEY (account_id, setting_key)
);
~~~

DDL trên minh họa một thiết kế PostgreSQL hoặc hệ quản trị tương thích với cú pháp identity đó. Hibernate không nhất thiết tự tạo đúng các constraint/tên cột/độ dài như ví dụ nếu thiếu annotation hoặc cấu hình DDL thích hợp. Khi dự án quản lý schema bằng Flyway/Liquibase, hãy giữ entity mapping và migration nhất quán.

### 3.2. Lưu và đọc Map

Giả sử `EntityManager em` đang ở trong một transaction hợp lệ:

~~~java
UserAccount account = new UserAccount("minh");
account.putPreference("theme", "dark");
account.putPreference("language", "vi");

em.persist(account);
em.flush();

Long id = account.getId();
em.clear();

UserAccount loaded = em.find(UserAccount.class, id);
System.out.println(loaded.getPreferences().get("theme")); // dark
~~~

Hibernate nạp các entry và xây dựng `Map<String, String>`. Khi entity đã managed, thay đổi Map có thể được ORM ghi lại khi flush:

~~~java
loaded.putPreference("theme", "light");
loaded.removePreference("language");
em.flush();
~~~

Hibernate có thể phát sinh `INSERT`, `UPDATE` hoặc `DELETE` cho các hàng collection tùy loại collection, tình trạng snapshot và chiến lược persister. Không nên giả định mọi thay đổi chỉ tạo đúng một SQL statement; cần quan sát SQL thực tế với dữ liệu đại diện.

## 4. Khóa Map: @MapKeyColumn khác @MapKey

Hai annotation này giống tên nhưng giải quyết bài toán khác nhau.

### 4.1. @MapKeyColumn — khóa được lưu trong cột riêng

Ở `Map<String, String>` phía trên:

~~~java
@ElementCollection
@CollectionTable(
    name = "account_preferences",
    joinColumns = @JoinColumn(name = "account_id")
)
@MapKeyColumn(name = "setting_key")
@Column(name = "setting_value")
private Map<String, String> preferences;
~~~

**Map key có cột riêng** `setting_key` trên bảng collection. Nó không lấy từ một thuộc tính khác trong value `String`.

`@MapKeyColumn` thường dùng cho map key kiểu cơ bản khi khóa cần một cột trong collection table hoặc bảng quan hệ thích hợp.

### 4.2. @MapKey — khóa suy ra từ thuộc tính của entity value

Giả sử một đơn hàng có nhiều dòng hàng, và code muốn truy cập dòng hàng theo mã sản phẩm:

~~~java
Map<String, OrderLine> linesByProductCode;
~~~

Nếu mỗi `OrderLine` là entity và có field persistent `productCode`, có thể dùng `@MapKey(name = "productCode")`.

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @MapKey(name = "productCode")
    private Map<String, OrderLine> linesByProductCode =
        new LinkedHashMap<>();

    protected PurchaseOrder() {}

    public void addLine(OrderLine line) {
        String key = line.getProductCode();
        if (linesByProductCode.containsKey(key)) {
            throw new IllegalArgumentException("Mã sản phẩm trùng");
        }
        line.assignOrder(this);
        linesByProductCode.put(key, line);
    }
}
~~~

Entity value:

~~~java
@Entity
@Table(name = "purchase_order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_code", nullable = false)
    private String productCode;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public OrderLine(String productCode, int quantity) {
        this.productCode = productCode;
        this.quantity = quantity;
    }

    public String getProductCode() {
        return productCode;
    }

    void assignOrder(PurchaseOrder order) {
        this.order = order;
    }
}
~~~

Các import của JPA được lược bớt để tập trung vào mapping. Khi Hibernate tải `PurchaseOrder.linesByProductCode`, nó dùng thuộc tính `productCode` của `OrderLine` làm khóa Map.

**Điểm phân biệt:** `@MapKey(name = "productCode")` không cần thêm cột “map_key” riêng; cột `product_code` vốn thuộc entity `OrderLine` vừa giữ giá trị thuộc tính vừa cung cấp khóa cho Map. Trái lại, `@MapKeyColumn` tạo mapping cho cột khóa map riêng trong bảng liên quan.

### 4.3. Vấn đề đồng bộ khi khóa lấy từ thuộc tính của value

Nếu bạn thay đổi `line.productCode` sau khi Map đã được xây, key đang có trong Map Java có thể không tự đổi ngay. Ví dụ Map vẫn chứa key `"P-001"` trong khi entity line đã có `productCode = "P-002"`.

Vì vậy nên thiết kế trường dùng làm khóa Map **ổn định** trong vòng đời association, hoặc có thao tác cập nhật vừa đổi thuộc tính, vừa gỡ key cũ và thêm key mới để duy trì nhất quán trong bộ nhớ. Đặt constraint/unique index ở database cho cặp `(order_id, product_code)` nếu nghiệp vụ yêu cầu duy nhất.

Không coi `@MapKey` là cơ chế tự đồng bộ lại mọi key Java tại thời điểm setter được gọi.

## 5. Khóa Enum, ngày tháng và khóa là entity

Map key không nhất thiết là `String`.

### 5.1. Map có khóa Enum

Ví dụ lưu mức giá theo loại khách hàng:

~~~java
public enum CustomerTier {
    STANDARD, SILVER, GOLD
}
~~~

~~~java
@ElementCollection
@CollectionTable(
    name = "tier_prices",
    joinColumns = @JoinColumn(name = "product_id")
)
@MapKeyColumn(name = "tier_name")
@MapKeyEnumerated(EnumType.STRING)
@Column(name = "price_amount", nullable = false)
private Map<CustomerTier, BigDecimal> pricesByTier =
    new EnumMap<>(CustomerTier.class);
~~~

`@MapKeyEnumerated(EnumType.STRING)` nói rằng **khóa enum** được lưu theo tên, như `GOLD`, thay vì ordinal. Giá trị của Map là `BigDecimal`, được lưu ở cột `price_amount`.

Vì thứ tự enum có thể thay đổi trong mã nguồn, cách lưu `EnumType.STRING` thường rõ và ít rủi ro hơn việc lưu ordinal, nhưng vẫn cần quản lý việc đổi tên hằng enum vì dữ liệu đã lưu có thể chứa tên cũ.

Chú ý phân biệt:

- `@MapKeyEnumerated`: tác động lên **khóa Map** kiểu enum.
- `@Enumerated` trên một thuộc tính/giá trị enum: tác động lên giá trị enum được ánh xạ theo cách tương ứng.

### 5.2. Map key kiểu ngày tháng

Với kiểu `java.util.Date` hoặc `Calendar` đời cũ, JPA có `@MapKeyTemporal` để khai báo độ chính xác `DATE`, `TIME` hoặc `TIMESTAMP` của khóa Map.

Ví dụ minh họa:

~~~java
@ElementCollection
@CollectionTable(
    name = "daily_totals",
    joinColumns = @JoinColumn(name = "report_id")
)
@MapKeyColumn(name = "business_date")
@MapKeyTemporal(TemporalType.DATE)
@Column(name = "total_amount")
private Map<Date, BigDecimal> totalsByDate = new HashMap<>();
~~~

Với `java.time.LocalDate`, thường không cần `@MapKeyTemporal`; để Hibernate map theo hỗ trợ kiểu Java time tương ứng. Không trộn Date/Calendar và Java time mà không xét độ chính xác, múi giờ, cách so sánh key và kiểu SQL thực tế.

### 5.3. Khi Map key là entity

Một Map có thể sử dụng entity làm khóa, chẳng hạn `Map<Country, ShippingRate>` khi `Country` có identity độc lập. Trong các quan hệ entity phù hợp, `@MapKeyJoinColumn` có thể xác định cột khóa ngoại tham chiếu entity key.

Khái niệm cần phân biệt:

- `@MapKeyColumn` lưu **giá trị key cơ bản**.
- `@MapKeyJoinColumn` mô tả **FK cho entity key** trong trường hợp mapping cho phép.
- `@MapKey(name = "...")` lấy key từ **thuộc tính của entity value**.

Không nên tùy ý hoán đổi ba annotation này. Chọn dựa trên bản chất key là scalar, entity độc lập hay thuộc tính của value entity và trên loại quan hệ được ánh xạ.

## 6. Đối tượng nhúng @Embeddable là value object

Xét địa chỉ bưu chính. Một địa chỉ gồm đường, thành phố và mã bưu chính, nhưng trong nhiều hệ thống, địa chỉ không cần ID riêng hoặc service/repository riêng.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.util.Objects;

@Embeddable
public class PostalAddress {

    @Column(name = "street", nullable = false)
    private String street;

    @Column(name = "city", nullable = false)
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected PostalAddress() {}

    public PostalAddress(
        String street, String city, String postalCode) {
        this.street = Objects.requireNonNull(street);
        this.city = Objects.requireNonNull(city);
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

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof PostalAddress that)) return false;
        return Objects.equals(street, that.street)
            && Objects.equals(city, that.city)
            && Objects.equals(postalCode, that.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
~~~

`PostalAddress` không có `@Id`, vì nó là **value type**. Hai địa chỉ cùng street, city và postalCode có thể được coi là bằng nhau theo nghiệp vụ. Việc viết `equals()`/`hashCode()` đặc biệt có ích khi sử dụng trong `Set` hoặc làm khóa của `Map`.

### 6.1. @Embedded cho một đối tượng

Nếu một khách hàng có đúng một địa chỉ thanh toán:

~~~java
@Embedded
private PostalAddress billingAddress;
~~~

Các field của `PostalAddress` thường được lưu cùng hàng với entity chủ, trong những cột tương ứng. `@Embedded` là lựa chọn cho **một giá trị nhúng**.

### 6.2. @ElementCollection cho nhiều đối tượng nhúng

Nếu khách hàng có nhiều địa chỉ giao hàng, có thể dùng:

~~~java
@ElementCollection
private List<PostalAddress> shippingAddresses;
~~~

Lúc này giá trị của danh sách nằm trong **bảng collection phụ**. Để chủ động schema và thứ tự, nên cấu hình cụ thể hơn như phần tiếp theo.

## 7. Lưu List<PostalAddress> bằng @ElementCollection

Ví dụ entity `Customer` chứa danh sách địa chỉ giao hàng:

~~~java
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OrderColumn;
import jakarta.persistence.Table;

import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false)
    private String fullName;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "customer_shipping_addresses",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @OrderColumn(name = "address_position")
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street", nullable = false)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city", nullable = false)
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code")
        )
    })
    private List<PostalAddress> shippingAddresses = new ArrayList<>();

    protected Customer() {}

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public void addShippingAddress(PostalAddress address) {
        shippingAddresses.add(address);
    }

    public void removeShippingAddress(int index) {
        shippingAddresses.remove(index);
    }

    public List<PostalAddress> getShippingAddresses() {
        return shippingAddresses;
    }
}
~~~

Các annotation chính:

- `@ElementCollection`: mỗi địa chỉ là **embeddable value**, thuộc `Customer`.
- `@CollectionTable`: bảng phụ lưu các địa chỉ.
- `@JoinColumn`: liên kết mỗi hàng tới `Customer`.
- `@AttributeOverride`: đổi tên cột cho **field của embeddable** trong ngữ cảnh collection; class `PostalAddress` có thể tái sử dụng ở nơi khác.
- `@OrderColumn`: Hibernate/JPA lưu **vị trí của từng phần tử List** thành một cột riêng, cho phép tái lập thứ tự khi đọc.

### 7.1. DDL minh họa

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL
);

CREATE TABLE customer_shipping_addresses (
    customer_id BIGINT NOT NULL,
    address_position INTEGER NOT NULL,
    shipping_street VARCHAR(255) NOT NULL,
    shipping_city VARCHAR(255) NOT NULL,
    shipping_postal_code VARCHAR(50),
    CONSTRAINT fk_shipping_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT pk_shipping_address_position
        PRIMARY KEY (customer_id, address_position)
);
~~~

Cột `address_position` là thông tin vị trí trong List. DDL thực tế của Hibernate/dialect có thể khác; tên ràng buộc và độ dài ở đây dành cho ví dụ migration.

### 7.2. @OrderColumn khác @OrderBy

- `@OrderColumn` **lưu vị trí** của phần tử vào cột SQL riêng. Di chuyển phần tử từ vị trí 5 lên vị trí 1 có thể cần cập nhật nhiều vị trí.
- `@OrderBy("city ASC")` yêu cầu **sắp xếp khi tải dữ liệu** theo thuộc tính persistent, không diễn tả thứ tự kéo/thả do người dùng quyết định.
- Không có hai annotation này, chỉ khai báo `List` không phải cam kết thứ tự bền vững theo yêu cầu nghiệp vụ trên mọi mapping.
- Nếu nghiệp vụ không cần thứ tự, `Set<PostalAddress>` có thể là lựa chọn hợp lý khi định nghĩa equality đúng.

Khi dùng `Set` chứa value object khả biến, tránh sửa field tham gia `hashCode()` khi object đang nằm trong Set. Điều này có thể khiến tìm/xóa phần tử thất bại vì vị trí bucket không còn đúng.

## 8. Map có giá trị là @Embeddable

Một yêu cầu phổ biến là mỗi khách hàng có nhiều địa chỉ, mỗi địa chỉ được gắn nhãn: `HOME`, `OFFICE`, `OTHER`. Trong Java:

~~~java
Map<String, PostalAddress> addressesByLabel;
~~~

Khóa Map là nhãn string; value là object nhúng. Ta có thể kết hợp `@MapKeyColumn` và `@ElementCollection`.

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "customer_address_book",
        joinColumns = @JoinColumn(name = "customer_id")
    )
    @MapKeyColumn(name = "address_label", nullable = false)
    @AttributeOverrides({
        @AttributeOverride(
            name = "value.street",
            column = @Column(name = "street_name", nullable = false)
        ),
        @AttributeOverride(
            name = "value.city",
            column = @Column(name = "city_name", nullable = false)
        ),
        @AttributeOverride(
            name = "value.postalCode",
            column = @Column(name = "zip_code")
        )
    })
    private Map<String, PostalAddress> addressesByLabel =
        new HashMap<>();

    protected Customer() {}

    public void putAddress(String label, PostalAddress address) {
        addressesByLabel.put(label, address);
    }

    public PostalAddress getAddress(String label) {
        return addressesByLabel.get(label);
    }
}
~~~

Điểm mới là `name = "value.street"` và các đường dẫn tương tự. Với `Map` mà value là embeddable, tiền tố **`value.`** xác định rằng thuộc tính cần override nằm **bên trong value của entry**, chứ không phải thuộc tính của entity `Customer`.

Lưu ý đoạn mã này chỉ minh họa mapping trong một lớp `Customer`; nếu áp dụng cùng ví dụ `Customer` ở phần danh sách địa chỉ, hãy kết hợp các field trong **một entity**, không tạo hai class `Customer` trùng tên.

Bảng phụ có thể có dạng:

| customer_id | address_label | street_name | city_name | zip_code |
| ---: | --- | --- | --- | --- |
| 7 | HOME | 21 Le Loi | HCMC | 700000 |
| 7 | OFFICE | 40 Pasteur | HCMC | 700000 |
| 8 | HOME | 15 Nguyen Hue | HCMC | 700000 |

Ở đây:

- `customer_id` xác định **chủ sở hữu**.
- `address_label` xác định **Map key**.
- Ba cột địa chỉ biểu diễn **Map value** là `PostalAddress`.
- Nếu yêu cầu mỗi nhãn duy nhất cho một khách hàng, có thể đặt unique constraint hoặc primary key trên `(customer_id, address_label)`.

`@Column(name = "address_value")` là không phù hợp với một embeddable có nhiều field cần cột riêng; lúc này dùng `@AttributeOverride(s)` để chỉ định các cột bên trong value.

## 9. Khóa Map là @Embeddable: dùng tiền tố key.

Không chỉ value, **key của Map cũng có thể là value object nhúng**. Ví dụ dùng địa bàn (mã quốc gia và mã vùng) làm khóa để truy cập giá vận chuyển.

~~~java
@Embeddable
public class RegionKey {

    @Column(name = "country_code", nullable = false)
    private String countryCode;

    @Column(name = "region_code", nullable = false)
    private String regionCode;

    protected RegionKey() {}

    public RegionKey(String countryCode, String regionCode) {
        this.countryCode = countryCode;
        this.regionCode = regionCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof RegionKey that)) return false;
        return Objects.equals(countryCode, that.countryCode)
            && Objects.equals(regionCode, that.regionCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(countryCode, regionCode);
    }
}
~~~

Mapping collection:

~~~java
@ElementCollection
@CollectionTable(
    name = "regional_shipping_rates",
    joinColumns = @JoinColumn(name = "rate_plan_id")
)
@AttributeOverrides({
    @AttributeOverride(
        name = "key.countryCode",
        column = @Column(name = "destination_country")
    ),
    @AttributeOverride(
        name = "key.regionCode",
        column = @Column(name = "destination_region")
    )
})
@Column(name = "fee_amount")
private Map<RegionKey, BigDecimal> feeByRegion = new HashMap<>();
~~~

Ở đây:

- `RegionKey` là **Map key kiểu embeddable** gồm hai field.
- `@AttributeOverride(name = "key.countryCode", ...)` và `key.regionCode` chọn tên cột cho **thành phần khóa**.
- `BigDecimal` là **basic value**, nên `@Column(name = "fee_amount")` chọn cột của value.
- Không dùng một `@MapKeyColumn` đơn lẻ để ánh xạ toàn bộ `RegionKey` nếu nó cần nhiều cột.

Với Map có **cả key và value là embeddable**, cách override vẫn dùng các tiền tố `key.` và `value.` để chỉ đúng phần thuộc tính cần ánh xạ.

### 9.1. Equality của key quyết định tính đúng của Map

Một `HashMap<RegionKey, ...>` yêu cầu hai key bằng nhau theo nghiệp vụ phải có `equals()` và `hashCode()` tương ứng. Khi đã dùng làm key, tốt nhất tránh sửa những field tham gia tính hash. Nếu mutate object key sau khi đặt vào Map, ứng dụng có thể không tìm được entry dù giá trị vẫn có trong bộ nhớ.

Đây là vấn đề của **Java Map** trước khi xét Hibernate. JPA không thể tự sửa một Map có hợp đồng `equals/hashCode` sai.

## 10. Truy vấn JPQL cho Map: KEY, VALUE và ENTRY

Khi collection đã được ánh xạ, JPQL cung cấp các biểu thức dành cho Map để truy vấn **key** và **value**.

Giả sử entity `UserAccount` có `preferences` từ phần 3.

### 10.1. Tìm người dùng có preference theo key và value

~~~java
List<UserAccount> users = em.createQuery("""
    SELECT DISTINCT u
    FROM UserAccount u
    JOIN u.preferences p
    WHERE KEY(p) = :settingKey
      AND VALUE(p) = :settingValue
    """, UserAccount.class)
    .setParameter("settingKey", "theme")
    .setParameter("settingValue", "dark")
    .getResultList();
~~~

Trong JPQL:

- `JOIN u.preferences p` tạo alias cho entry của Map.
- `KEY(p)` là **khóa Map**.
- `VALUE(p)` là **giá trị Map**.
- `DISTINCT` giúp tránh entity trùng trong kết quả ở các trường hợp join tạo nhiều hàng phù hợp.

JPQL vận hành trên tên entity và thuộc tính Java persistent, **không trực tiếp dùng tên bảng/cột** như `account_preferences` hay `setting_key`.

### 10.2. Chỉ truy vấn key và value

~~~java
List<Object[]> rows = em.createQuery("""
    SELECT KEY(p), VALUE(p)
    FROM UserAccount u
    JOIN u.preferences p
    WHERE u.id = :accountId
    """, Object[].class)
    .setParameter("accountId", accountId)
    .getResultList();

for (Object[] row : rows) {
    String key = (String) row[0];
    String value = (String) row[1];
    System.out.println(key + " = " + value);
}
~~~

JPA cũng có biểu thức `ENTRY(p)` trong ngữ cảnh lựa chọn entry của map theo hỗ trợ của JPQL/provider. Trong code dùng lâu dài, DTO projection hoặc kiểu kết quả rõ ràng thường dễ bảo trì hơn `Object[]` nếu logic phức tạp.

### 10.3. Truy vấn field của embeddable value

Nếu Map value là `PostalAddress`, có thể truy vấn dựa trên thuộc tính persistent của value:

~~~java
List<Customer> result = em.createQuery("""
    SELECT DISTINCT c
    FROM Customer c
    JOIN c.addressesByLabel address
    WHERE KEY(address) = :label
      AND VALUE(address).city = :city
    """, Customer.class)
    .setParameter("label", "HOME")
    .setParameter("city", "HCMC")
    .getResultList();
~~~

Khả năng dùng cú pháp đường dẫn cụ thể và cú pháp `VALUE(alias)` phụ thuộc JPQL version và provider. Trong truy vấn thực tế có thể viết đường dẫn từ identification variable tương ứng, chẳng hạn `address.city`, theo cú pháp JPQL được hỗ trợ. Nên giữ truy vấn và mapping thống nhất với phiên bản JPA/Hibernate đang dùng.

### 10.4. Dùng SQL khi cần truy vấn đặc thù

Vì Map được lưu trong bảng collection, SQL có thể join trực tiếp khi phục vụ báo cáo, bulk operation hoặc database-specific feature:

~~~sql
SELECT u.id, u.username
FROM user_accounts u
JOIN account_preferences p ON p.account_id = u.id
WHERE p.setting_key = 'theme'
  AND p.setting_value = 'dark';
~~~

Sử dụng parameter binding trong JDBC/native query để tránh SQL injection khi giá trị đến từ người dùng.

## 11. Vòng đời và cập nhật của element collection

### 11.1. Collection thuộc quyền sở hữu entity

`@ElementCollection` không phải danh sách các entity độc lập. Giá trị trong collection thường được persist khi owner được persist, và thay đổi collection được theo dõi khi owner ở trạng thái managed.

Ví dụ:

~~~java
Customer customer = em.find(Customer.class, customerId);

customer.addShippingAddress(new PostalAddress(
    "123 Tran Hung Dao", "HCMC", "700000"
));

em.flush();
~~~

Hibernate sẽ xử lý thay đổi collection khi flush, dựa trên snapshot và loại collection. Không cần gọi `em.persist(address)` vì `PostalAddress` không phải entity.

Khi xóa owner, các hàng collection thuộc về owner được xử lý theo lifecycle của collection, nhưng chi tiết constraint/FK và thao tác SQL phụ thuộc mapping, cascade ở database và Hibernate.

### 11.2. Collection removal không giống xóa entity riêng

Xóa một địa chỉ nhúng khỏi `List<PostalAddress>` có nghĩa loại value khỏi collection của owner; không có thao tác `em.remove(address)` theo identity của address. Ngược lại, nếu địa chỉ là `@Entity` được chia sẻ hoặc tham chiếu độc lập, xóa khỏi collection không nhất thiết có nghĩa xóa record entity đó.

Với `@OneToMany(orphanRemoval = true)`, việc xóa entity con khỏi quan hệ có semantics riêng. **Đừng dùng `@ElementCollection` chỉ để tránh suy nghĩ về entity lifecycle** khi thực tế đối tượng con cần identity hoặc quan hệ riêng.

### 11.3. Dirty checking và chi phí update collection

Với một `Map<String, String>`, thay đổi key hoặc value được phản ánh vào trạng thái collection khi entity managed. Hibernate có thể dùng các lệnh tương ứng cho row, nhưng hành vi SQL cụ thể phụ thuộc loại collection, mapping và khả năng xác định từng hàng.

Với `List<Embeddable>` có `@OrderColumn`, việc chèn hoặc xóa ở giữa có thể khiến nhiều giá trị `address_position` phải đổi. Với một số collection giá trị, Hibernate có thể delete/insert lại nhiều hàng thay vì cập nhật đúng một row.

Như vậy “không có entity riêng” giúp mô hình đơn giản hơn, nhưng không bảo đảm mọi thao tác đều sinh ra SQL ít nhất.

### 11.4. Đồng bộ collection trong transaction

Một ví dụ service kiểu Spring:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void addAddress(long customerId, PostalAddress address) {
        Customer customer = repository.findById(customerId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Không tìm thấy khách hàng"));

        customer.addShippingAddress(address);
    }
}
~~~

Trong transaction, customer là managed entity; Hibernate sẽ đồng bộ thay đổi collection khi flush/commit. `CustomerRepository` là Spring Data repository tương ứng với entity, không phải repository cho `PostalAddress`.

Tùy cách thiết kế, không nên phơi bày trực tiếp một collection mutable cho code bất kỳ thay đổi không kiểm soát. Có thể dùng phương thức nghiệp vụ để kiểm tra số lượng, trùng lặp, phạm vi giá trị và bất biến.

## 12. Fetching và N+1 với collection

`@ElementCollection` thường được định nghĩa `LAZY`, nhưng dữ liệu collection vẫn cần được đọc từ database khi được sử dụng. Ví dụ, sau khi lấy 100 tài khoản, nếu vòng lặp truy cập `getPreferences()` cho từng tài khoản, Hibernate có thể phải phát nhiều câu query bổ sung.

~~~java
List<UserAccount> accounts = em.createQuery("""
    SELECT u FROM UserAccount u
    ORDER BY u.id
    """, UserAccount.class)
    .getResultList();

for (UserAccount u : accounts) {
    System.out.println(u.getPreferences().size());
}
~~~

Đoạn này có thể tạo nhiều round-trip database tùy fetch strategy; đây là dạng vấn đề **N+1**.

Các hướng xử lý khi thực sự cần collection:

- Dùng truy vấn projection chỉ lấy các key/value cần hiển thị.
- Dùng `JOIN FETCH` hoặc entity graph cho use case phù hợp, có tính tới số lượng phần tử.
- Dùng batch fetching hoặc cơ chế Hibernate phù hợp để giảm query lặp.
- Phân trang owner trước, rồi lấy collection cho số owner trong trang theo truy vấn khác nếu cần.

Cần tránh dùng fetch join collection cùng phân trang offset một cách tùy tiện: join nhiều hàng collection có thể làm số hàng SQL bị nhân lên, khiến phân trang không đúng kỳ vọng hoặc cần xử lý trong bộ nhớ.

### 12.1. LazyInitializationException

Nếu service trả entity đã detach rồi controller/serializer truy cập một collection lazy chưa được nạp, Hibernate có thể ném `LazyInitializationException`.

Một cách thiết kế rõ ràng là: trong transaction, truy vấn đúng dữ liệu cần và chuyển thành DTO; sau đó API trả DTO cho client. Nếu cần collection, chủ động fetch trong transaction phù hợp thay vì phụ thuộc vào session còn mở khi render JSON.

## 13. Map key, unique constraint và thứ tự dữ liệu

### 13.1. Map key là duy nhất trong phạm vi một Map

Java Map không thể có hai entry cùng key theo `equals()` của key. Vì thế schema nên phản ánh điều này:

~~~sql
ALTER TABLE account_preferences
ADD CONSTRAINT uq_account_setting
UNIQUE (account_id, setting_key);
~~~

Nếu bảng đã đặt `PRIMARY KEY (account_id, setting_key)` thì không cần thêm một unique constraint trùng nghĩa. Khi khóa Map có nhiều cột nhúng, constraint thường liên quan toàn bộ các cột key cùng owner ID.

Nếu để database có hai hàng trùng key cho cùng owner, lúc Hibernate dựng Map không thể giữ hai entry độc lập như một `List`. Thiết kế dữ liệu cần ngăn trạng thái này.

### 13.2. Khóa null

Theo semantics của một bảng Map quan hệ, nên xác định quy tắc khóa rõ ràng và thường **không cho phép null** đối với map key, đặc biệt khi key tham gia primary key. Java `HashMap` có thể cho phép một null key, nhưng database constraint và Hibernate mapping có thể không hỗ trợ trường hợp đó theo cách bạn mong đợi.

Ví dụ dùng `Objects.requireNonNull(key)` trong phương thức nghiệp vụ như `putPreference` giúp phát hiện lỗi sớm.

### 13.3. Thứ tự của Map

`HashMap` không bảo đảm thứ tự; `LinkedHashMap` giữ thứ tự duyệt trong một object Java, nhưng khi Hibernate tải lại từ database, kết quả SQL không được bảo đảm có thứ tự nếu mapping/query không yêu cầu.

Nếu cần sắp xếp theo key hoặc value, hãy thiết kế truy vấn hoặc cơ chế ordering phù hợp. Hibernate có hỗ trợ các cơ chế ordering/sorting của collection, nhưng cần phân biệt **sắp xếp theo giá trị** với **thứ tự nhập được lưu thành vị trí**, vốn phù hợp hơn với List và `@OrderColumn`.

## 14. Null, chuyển đổi dữ liệu và custom value types

### 14.1. Null value

Map key và value có thể có quy tắc null khác nhau. `@Column(nullable = false)` áp lên value basic; `@MapKeyColumn(nullable = false)` áp lên key basic. Chọn nullability theo nghiệp vụ và database.

Nếu logic cần diễn đạt “không có thiết lập này”, có thể xóa entry khỏi Map thay vì lưu value null, giúp tránh nhầm giữa **không có key** và **key có value null**.

### 14.2. Converter cho giá trị của Map

Khi value là kiểu domain đơn giản cần chuyển sang kiểu cơ bản, có thể dùng `AttributeConverter` phù hợp. Ví dụ object value là `CurrencyCode` nhưng lưu dưới dạng mã `String`.

Các annotation converter cho phần tử collection và map key/value có cách chỉ định attributeName khác nhau tùy trường hợp JPA; khi áp dụng cần xác nhận cú pháp cho loại mapping của bạn. Tránh chọn `@Convert` ngẫu nhiên mà không hiểu nó sẽ chuyển **key hay value**.

### 14.3. Các value object lồng nhau

Một `@Embeddable` có thể chứa một embeddable khác, và annotation `@AttributeOverride` có thể sử dụng đường dẫn thuộc tính lồng nhau. Khi Map chứa embeddable, đường dẫn có thể bắt đầu bằng `key.` hoặc `value.` rồi đến tên thuộc tính con.

Ví dụ ý tưởng:

~~~java
@AttributeOverride(
    name = "value.coordinates.latitude",
    column = @Column(name = "addr_lat")
)
~~~

Điều này chỉ phù hợp nếu `value` có field embeddable `coordinates` chứa `latitude` và mapping tương ứng đã tồn tại.

Nếu cấu trúc lồng nhau quá phức tạp, nhiều cột bị lặp hoặc cần truy vấn/cập nhật độc lập, hãy cân nhắc lại mô hình quan hệ. Cũng cần lưu ý các ràng buộc JPA đối với collection bên trong embeddable đang được dùng làm phần tử của `@ElementCollection`; không nên thiết kế các lớp collection lồng nhau tùy ý rồi giả định provider sẽ tự map.

## 15. Khi nào dùng @ElementCollection, khi nào tạo entity con?

Giả sử muốn lưu các địa chỉ, tag hoặc thuộc tính động của khách hàng.

| Tiêu chí | `@ElementCollection` với value object | `@OneToMany` đến entity con |
| --- | --- | --- |
| Có khóa chính/identity riêng? | Không cần | Có |
| Truy xuất độc lập qua repository? | Không phù hợp | Phù hợp |
| Value chỉ tồn tại cùng owner? | Thường có | Có thể có hoặc không |
| Phần tử được chia sẻ giữa nhiều owner? | Không phải mô hình tự nhiên | Có thể qua quan hệ entity |
| Cần khóa ngoại tham chiếu từng phần tử? | Không tự nhiên nếu phần tử không có ID | Thường phù hợp |
| Thường xuyên cập nhật từng phần tử cụ thể? | Có thể tốn chi phí thay đổi collection | Dễ nhắm tới entity bằng ID |
| Nhu cầu đơn giản và phụ thuộc owner? | Phù hợp | Có thể phức tạp không cần thiết |
| Cần version/locking riêng từng phần tử? | Không có identity entity riêng | Có thể khai báo `@Version` cho entity con |

**Ví dụ chọn `@ElementCollection`:** một sản phẩm lưu tập màu cơ bản; một khách hàng có danh sách địa chỉ giao hàng mang tính snapshot; cấu hình hiển thị gắn với một tài khoản.

**Ví dụ chọn entity con:** địa chỉ giao hàng có ID được tham chiếu bởi nhiều đơn; tag có mô tả, người quản lý, quan hệ tới nhiều bài viết; dòng đơn hàng có trạng thái giao vận riêng và cần cập nhật độc lập.

Không nên chọn theo mỗi số lượng phần tử. Cần xét **identity, lifecycle, khả năng truy vấn, khóa ngoại, đồng thời cập nhật và chi phí SQL**.

## 16. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “`Map<K, V>` được lưu trong một cột mặc định.” | Với `@ElementCollection`, các entry thường nằm trong bảng collection có owner key, map key và value columns. |
| “`@MapKey` và `@MapKeyColumn` giống nhau.” | `@MapKey` dùng thuộc tính của entity value làm key; `@MapKeyColumn` ánh xạ cột key riêng. |
| “`@Column` trên Map chọn cột key.” | Với Map basic value, `@Column` thường chỉ cột value; key dùng `@MapKeyColumn`. |
| “Một `@Embeddable` có ID như entity.” | Embeddable là value object, không có entity identity riêng. |
| “`@Embedded` và `@ElementCollection` đều tạo bảng phụ.” | `@Embedded` đơn thường nằm cùng hàng owner; `@ElementCollection` thường dùng bảng collection. |
| “`@ElementCollection` hỗ trợ mọi quan hệ/nested collection như entity.” | Có giới hạn mapping; cần chọn entity relationship khi phần tử có identity hoặc quan hệ riêng. |
| “List có thứ tự bền vững chỉ vì dùng `ArrayList`.” | Thứ tự trong Java không thay thế `@OrderColumn`/quy tắc ordering ở database. |
| “Đổi thuộc tính đang làm `@MapKey` tự đổi key Java.” | Key trong Map có thể bị cũ; nghiệp vụ cần giữ nhất quán. |
| “Element collection luôn rẻ hơn entity collection.” | Có thể phát sinh nhiều SQL khi sửa List, reorder hoặc flush collection. |
| “Key embeddable chỉ cần một `@MapKeyColumn`.” | Key embeddable có thể cần nhiều cột và `@AttributeOverride(name = "key....")`. |
| “Value embeddable dùng một `@Column` là đủ.” | Mỗi field của value được ánh xạ cột; có thể override bằng `value.` prefix. |
| “Lazy collection luôn dùng được sau khi transaction kết thúc.” | Nếu chưa initialize và session đóng, có thể gặp `LazyInitializationException`. |

## 17. Quy trình thiết kế một Map hoặc embedded collection

Trước khi viết entity, hãy trả lời:

1. **Phần tử có identity riêng không?** Nếu có, xét mapping entity relationship thay vì element collection.
2. **Với Map, khóa là gì?** Scalar, enum, embeddable nhiều cột, entity key hay thuộc tính của entity value?
3. **Giá trị là gì?** Basic value, `@Embeddable` hay entity? Chọn `@Column`, `@AttributeOverrides` hoặc entity association tương ứng.
4. **Bảng liên kết sẽ ra sao?** Tên bảng, khóa ngoại owner, cột key, các cột value và unique constraint.
5. **Cần thứ tự không?** Nếu thứ tự do người dùng quyết định, xét `List` + `@OrderColumn`; nếu chỉ sắp xếp để hiển thị, xét ordering.
6. **Có trường hợp key trùng/null không?** Thiết lập validation Java và constraint DB rõ ràng.
7. **Phần tử có khả biến không?** Xác định `equals/hashCode` và cách cập nhật collection tránh stale state.
8. **Sẽ truy vấn thế nào?** JPQL `KEY`/`VALUE`, projection, join, index trên key/value và khả năng N+1.
9. **Collection lớn đến đâu?** Hàng nghìn phần tử luôn được đọc cùng owner có thể cần API truy cập riêng hoặc entity con.
10. **Đã có dữ liệu chưa?** Thiết kế migration cho bảng collection và ràng buộc dữ liệu lịch sử.

## 18. Bài tập thực hành

### Bài 1 — Map cơ bản

Một entity `UserProfile` có `Map<String, String> properties`, ví dụ `"theme" -> "dark"`. Hãy viết các annotation để lưu ở bảng `user_properties` với cột owner `user_id`, key `property_name` và value `property_value`.

**Gợi ý:** `@ElementCollection`, `@CollectionTable(joinColumns = @JoinColumn(...))`, `@MapKeyColumn`, `@Column`.

### Bài 2 — Chọn MapKey hay MapKeyColumn

Entity `Invoice` có `Map<String, InvoiceLine>`; mỗi `InvoiceLine` là entity và có thuộc tính persistent `lineCode`. Hãy chỉ ra khi nào chọn `@MapKey(name = "lineCode")`; nếu business cho phép đổi `lineCode` sau khi line đã nằm trong Map, cần duy trì nhất quán key Java thế nào?

**Gợi ý:** `@MapKey` lấy key từ thuộc tính value entity; cần cập nhật lại entry khi key thay đổi, đồng thời xét uniqueness ở DB.

### Bài 3 — Map enum key

Lưu mức phí theo `MembershipLevel` enum. Hãy dùng `@MapKeyEnumerated(EnumType.STRING)` và phân biệt annotation này với `@Enumerated` áp cho value enum.

### Bài 4 — List địa chỉ nhúng

Entity `Customer` có `List<PostalAddress>`; mỗi địa chỉ gồm `street`, `city`, `postalCode`. Hãy chọn annotation để lưu nhiều địa chỉ trong bảng `customer_addresses` và bảo đảm giữ thứ tự sau khi reload.

**Gợi ý:** `@Embeddable`, `@ElementCollection`, `@CollectionTable`, `@OrderColumn` và `@AttributeOverride` khi cần tên cột khác.

### Bài 5 — Map với embeddable value

Một entity `Customer` chứa `Map<String, PostalAddress>` với key `HOME` hoặc `OFFICE`. Hãy ánh xạ cột key `address_label` và đổi tên cột `street` thành `street_name`. Vì sao dùng `name = "value.street"` trong `@AttributeOverride`?

### Bài 6 — Chọn thiết kế khi nhu cầu thay đổi

Ban đầu, ứng dụng lưu các địa chỉ giao hàng như value object. Về sau mỗi địa chỉ cần ID riêng, liên kết với các đơn hàng, người xác minh, trạng thái phê duyệt và lịch sử cập nhật. Bạn sẽ giữ `@ElementCollection` hay chuyển sang `@Entity`? Hãy nêu tác động đến schema và repository.

### Định hướng giải

- **Bài 1:** key/value cơ bản nằm trong bảng collection; bảo đảm uniqueness của cặp owner + key.
- **Bài 2:** `@MapKey` phù hợp khi key là field persistent của value entity; phải tránh key trong Map bị cũ.
- **Bài 3:** `@MapKeyEnumerated(EnumType.STRING)` biểu diễn key enum theo tên, thuận tiện so với ordinal.
- **Bài 4:** `@ElementCollection` lưu địa chỉ ở bảng phụ; `@OrderColumn` lưu vị trí.
- **Bài 5:** `@MapKeyColumn` dùng cho key string, còn `value.` chỉ thuộc tính của embeddable nằm trong value.
- **Bài 6:** Khi phần tử có identity/lifecycle độc lập và quan hệ riêng, entity con thường phù hợp hơn.

---

**Ghi nhớ:** Với `Map<K, V>`, cần xác định chính xác **key lấy từ đâu và value được biểu diễn ra sao**. `@MapKeyColumn` ánh xạ key vào cột riêng; `@MapKey` lấy key từ thuộc tính entity value; `@MapKeyEnumerated` và `@MapKeyJoinColumn` giải quyết những dạng key đặc biệt. Với value object và tập hợp đối tượng nhúng, `@Embeddable` kết hợp `@ElementCollection`, `@CollectionTable` và `@AttributeOverride` cho phép lưu nhiều giá trị mà không cần tạo entity độc lập cho từng phần tử.
