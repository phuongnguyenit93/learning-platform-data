# Ghi đè thuộc tính của khóa và giá trị nhúng trong Map bằng JPA

Trong Java, `Map<K, V>` là cấu trúc liên kết **một khóa (key)** với **một giá trị (value)**. Khi đưa `Map` vào entity JPA, vấn đề không chỉ là lưu một collection: persistence provider phải biết khóa và giá trị thuộc loại dữ liệu nào, những thành phần nào được lưu thành cột, và các tên cột đó có trùng nhau hoặc xung đột với khóa ngoại trỏ về entity sở hữu hay không.

Đặc biệt, nếu khóa hoặc giá trị của `Map` là một lớp `@Embeddable`, chúng thường gồm **nhiều thuộc tính cơ bản**, mỗi thuộc tính tương ứng với một cột SQL. Khi cùng một kiểu embeddable được sử dụng trong những ngữ cảnh khác nhau, tên cột mặc định ở class có thể không phù hợp. Jakarta Persistence (JPA) cung cấp `@AttributeOverride` / `@AttributeOverrides` và, với quan hệ bên trong embeddable, `@AssociationOverride` để **ghi đè ánh xạ tại nơi sử dụng**.

Điểm quan trọng nhất trong bài là **tiền tố của đường dẫn thuộc tính**:

- `key.` dùng để chỉ một thuộc tính **bên trong khóa nhúng** của `Map`.
- `value.` dùng để chỉ một thuộc tính **bên trong giá trị nhúng** của `Map`.
- Đường dẫn có thể đi tiếp qua embeddable lồng nhau, chẳng hạn `value.rule.discountPercent`.

Đây là **tên thuộc tính Java**, không phải tên cột SQL. Hiểu đúng cách chọn phía khóa/giá trị giúp tránh lỗi provider tìm sai thuộc tính, trùng cột trong collection table hoặc vô tình thay đổi ngữ nghĩa của map key.

## 1. Map trong Java khác bảng trong cơ sở dữ liệu thế nào?

Giả sử một sản phẩm có bảng giá khác nhau theo thị trường và kênh bán:

~~~text
Product(id=101)
  prices:
    (VN, ONLINE)  ->  199000 VND
    (VN, STORE)   ->  209000 VND
    (SG, ONLINE)  ->  18.50 SGD
~~~

Về phía Java, có thể diễn đạt:

~~~java
Map<MarketKey, PriceQuote> prices;
~~~

Trong đó:

~~~text
MarketKey                      PriceQuote
--------------------------     --------------------------
marketCode: "VN"               amount: 199000
salesChannel: "ONLINE"         currencyCode: "VND"
                               rule.discountPercent: 5.00
~~~

`MarketKey` và `PriceQuote` đều là những **value object**, không phải entity có định danh độc lập. Có thể đánh dấu chúng là `@Embeddable` và lưu vào **collection table**:

~~~text
products
+-----+------------+
| id  | sku        |
+-----+------------+
| 101 | JPA-BOOK   |
+-----+------------+
          |
          | FK product_id
          v
product_price_matrix
+------------+-------------+---------------+-----------+---------------+------------------+
| product_id | market_code | sales_channel | amount    | currency_code | discount_percent |
+------------+-------------+---------------+-----------+---------------+------------------+
| 101        | VN          | ONLINE        | 199000.00 | VND           | 5.00             |
| 101        | VN          | STORE         | 209000.00 | VND           | 0.00             |
| 101        | SG          | ONLINE        | 18.50     | SGD           | 0.00             |
+------------+-------------+---------------+-----------+---------------+------------------+
~~~

Một hàng của bảng trung gian lưu **cả khóa lẫn giá trị** của một entry. Cột `product_id` chỉ biết **Map này thuộc Product nào**, còn `market_code` và `sales_channel` là **các thành phần của key**. Các cột `amount`, `currency_code` và `discount_percent` là **thành phần của value**.

Sự phân biệt này quyết định nơi khai báo `@CollectionTable`, `@JoinColumn` và các `@AttributeOverride`.

## 2. Nhắc lại ba loại thành phần của một Map persistent

Khi khai báo một map trong entity, cần phân biệt:

| Thành phần | Ví dụ | Cách ánh xạ thông thường |
| --- | --- | --- |
| Entity sở hữu collection | `Product` | `@Entity`, `@Id` |
| Khóa của Map | `MarketKey("VN", "ONLINE")` | `@Embeddable` hoặc kiểu basic/entity tùy mô hình |
| Giá trị của Map | `PriceQuote(amount, currency, rule)` | `@Embeddable`, basic hoặc entity tùy annotation quan hệ |
| Bảng lưu các entry | `product_price_matrix` | `@CollectionTable` với `@ElementCollection` |
| FK trở về chủ sở hữu | `product_id` | `@CollectionTable(joinColumns = @JoinColumn(...))` |
| Thuộc tính khóa nhúng | `marketCode` | `@AttributeOverride(name = "key.marketCode", ...)` |
| Thuộc tính giá trị nhúng | `amount` | `@AttributeOverride(name = "value.amount", ...)` |

Một cột join về chủ sở hữu **không phải** một thuộc tính của khóa `Map` chỉ vì tên cột có từ `key`. `product_id` xác định owner của hàng; còn `market_code + sales_channel` xác định vị trí entry trong map của owner.

Ngoài ra, `@ElementCollection` dùng cho collection có **giá trị phần tử là basic hoặc embeddable**; nó không phải một quan hệ `@OneToMany` giữa hai entity. Nếu value là entity độc lập, cần một mapping association phù hợp và xử lý map key theo cách tương ứng.

## 3. Tạo lớp khóa nhúng `MarketKey`

Đầu tiên, định nghĩa key là một embeddable gồm hai thuộc tính:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class MarketKey implements Serializable {

    @Column(name = "default_market_code", length = 12)
    private String marketCode;

    @Column(name = "default_sales_channel", length = 20)
    private String salesChannel;

    protected MarketKey() {
        // Constructor không tham số cho JPA.
    }

    public MarketKey(String marketCode, String salesChannel) {
        this.marketCode = Objects.requireNonNull(marketCode);
        this.salesChannel = Objects.requireNonNull(salesChannel);
    }

    public String getMarketCode() {
        return marketCode;
    }

    public String getSalesChannel() {
        return salesChannel;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof MarketKey)) {
            return false;
        }
        MarketKey that = (MarketKey) other;
        return Objects.equals(marketCode, that.marketCode)
            && Objects.equals(salesChannel, that.salesChannel);
    }

    @Override
    public int hashCode() {
        return Objects.hash(marketCode, salesChannel);
    }
}
~~~

`MarketKey` không có `@Id` vì đây **không phải entity**. Danh tính của một map entry được hình thành từ owner và giá trị khóa theo ngữ nghĩa của map.

### Vì sao khóa Map cần `equals()` / `hashCode()`?

Khi ứng dụng gọi:

~~~java
prices.get(new MarketKey("VN", "ONLINE"));
~~~

Java cần phân biệt key này với các key khác. Trong `HashMap`, hai key logic giống nhau phải có cùng `hashCode()` và được `equals()` xem là bằng nhau. Nếu key object chỉ dùng identity mặc định của `Object`, ứng dụng có thể không tìm thấy entry vừa đọc từ database khi tạo một key instance mới có cùng nội dung.

Với embeddable làm khóa Map, nên thiết kế các thành phần key theo **value equality** và không thay đổi chúng sau khi entry đã được đưa vào map.

Các annotation `@Column(name = "default_market_code")` trong `MarketKey` mô tả tên cột khi class được sử dụng ở một vị trí mặc định. Ta sẽ ghi đè chúng thành `market_code` và `sales_channel` **tại field Map**, chứ không sửa class dùng chung.

## 4. Tạo giá trị nhúng `PriceQuote` và embeddable lồng nhau

Value object thứ hai chứa số tiền, mã tiền tệ và một cấu hình chiết khấu:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;

@Embeddable
public class PriceRule {

    @Column(
        name = "default_discount_percent",
        precision = 5,
        scale = 2)
    private BigDecimal discountPercent;

    protected PriceRule() {
    }

    public PriceRule(BigDecimal discountPercent) {
        this.discountPercent = discountPercent;
    }

    public BigDecimal getDiscountPercent() {
        return discountPercent;
    }
}
~~~

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.Embedded;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
public class PriceQuote {

    @Column(
        name = "default_price_amount",
        precision = 14,
        scale = 2)
    private BigDecimal amount;

    @Column(name = "default_currency_code", length = 3)
    private String currencyCode;

    @Embedded
    private PriceRule rule;

    protected PriceQuote() {
    }

    public PriceQuote(
            BigDecimal amount,
            String currencyCode,
            PriceRule rule) {
        this.amount = Objects.requireNonNull(amount);
        this.currencyCode = Objects.requireNonNull(currencyCode);
        this.rule = Objects.requireNonNull(rule);
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }

    public PriceRule getRule() {
        return rule;
    }
}
~~~

Quan hệ lồng nhau ở đây là:

~~~text
PriceQuote
  ├─ amount
  ├─ currencyCode
  └─ rule: PriceRule
       └─ discountPercent
~~~

Khi giá trị `PriceQuote` xuất hiện trong `Map<MarketKey, PriceQuote>`, đường dẫn đến chiết khấu là `value.rule.discountPercent`:

- `value`: đi vào phía **value** của Map.
- `rule`: đi vào embeddable `PriceRule` nằm trong `PriceQuote`.
- `discountPercent`: thuộc tính được ánh xạ thành một cột.

Những dấu chấm trong `name` là **đường dẫn thuộc tính** của mô hình Java, không phải dấu phân tách tên bảng/cột SQL.

## 5. Ánh xạ Map và ghi đè cả key lẫn value

Đây là ví dụ trung tâm của bài. Entity `Product` sở hữu một Map có key và value đều là embeddable:

~~~java
package com.example.persistence;

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
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.HashMap;
import java.util.Map;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "product_price_matrix",
        joinColumns = @JoinColumn(name = "product_id"),
        uniqueConstraints = @UniqueConstraint(
            name = "uq_product_market_channel",
            columnNames = {
                "product_id", "market_code", "sales_channel"
            }
        )
    )
    @AttributeOverrides({
        @AttributeOverride(
            name = "key.marketCode",
            column = @Column(
                name = "market_code", nullable = false, length = 12)
        ),
        @AttributeOverride(
            name = "key.salesChannel",
            column = @Column(
                name = "sales_channel", nullable = false, length = 20)
        ),
        @AttributeOverride(
            name = "value.amount",
            column = @Column(
                name = "amount",
                nullable = false,
                precision = 14,
                scale = 2)
        ),
        @AttributeOverride(
            name = "value.currencyCode",
            column = @Column(
                name = "currency_code", nullable = false, length = 3)
        ),
        @AttributeOverride(
            name = "value.rule.discountPercent",
            column = @Column(
                name = "discount_percent", precision = 5, scale = 2)
        )
    })
    private Map<MarketKey, PriceQuote> prices = new HashMap<>();

    protected Product() {
    }

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    public PriceQuote getPrice(MarketKey key) {
        return prices.get(key);
    }

    public void putPrice(MarketKey key, PriceQuote value) {
        if (key == null || value == null) {
            throw new IllegalArgumentException(
                "Map key và value không được null");
        }
        prices.put(key, value);
    }

    public void removePrice(MarketKey key) {
        prices.remove(key);
    }
}
~~~

### Đọc từng annotation

| Annotation hoặc thuộc tính | Đang chỉ đến đâu? | Kết quả |
| --- | --- | --- |
| `@ElementCollection` | Map có value là embeddable | Lưu các entry như collection các giá trị thuộc Product |
| `@CollectionTable(name = ...)` | Bảng lưu collection | `product_price_matrix` |
| `joinColumns = @JoinColumn(name = "product_id")` | FK từ bảng collection về Product | Cột `product_id` |
| `name = "key.marketCode"` | Thuộc tính `MarketKey.marketCode` | Cột `market_code` |
| `name = "key.salesChannel"` | Thuộc tính `MarketKey.salesChannel` | Cột `sales_channel` |
| `name = "value.amount"` | Thuộc tính `PriceQuote.amount` | Cột `amount` |
| `name = "value.currencyCode"` | Thuộc tính `PriceQuote.currencyCode` | Cột `currency_code` |
| `name = "value.rule.discountPercent"` | Thuộc tính `PriceQuote.rule.discountPercent` | Cột `discount_percent` |
| `uniqueConstraints = ...` | Cặp khóa Map phải duy nhất trong mỗi Product | Metadata uniqueness của ba cột |

Ở đây, trường `prices` dùng **field access**, phù hợp với việc các annotation ánh xạ nằm trên field. Bản thân hai embeddable cũng đặt annotation lên field.

### Ba điểm cần ghi nhớ

**Thứ nhất, `key.` và `value.` là quy tắc chọn phía trong Map.** Dù cả hai phía đều là embeddable, provider phải biết đang ghi đè class nào.

**Thứ hai, `@Column(name = "...")` chỉ tên cột SQL mới, còn `@AttributeOverride(name = "...")` chỉ thuộc tính Java cần ghi đè.** Đảo hai ý nghĩa này sẽ làm mapping sai.

**Thứ ba, ghi đè được đặt ở nơi Map được khai báo.** Nó chỉ thay mapping của `MarketKey` hoặc `PriceQuote` tại ngữ cảnh `Product.prices`, không làm thay đổi mọi chỗ khác sử dụng hai class embeddable.

## 6. Schema vật lý tương ứng và vai trò của các ràng buộc

Một DDL minh họa bằng PostgreSQL:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE product_price_matrix (
    product_id BIGINT NOT NULL,
    market_code VARCHAR(12) NOT NULL,
    sales_channel VARCHAR(20) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    discount_percent NUMERIC(5, 2),

    CONSTRAINT pk_product_price_matrix
        PRIMARY KEY (
            product_id, market_code, sales_channel
        ),

    CONSTRAINT fk_price_matrix_product
        FOREIGN KEY (product_id) REFERENCES products(id)
);
~~~

Trong DDL này:

- `product_id` gắn từng hàng với đúng entity `Product`.
- `market_code` và `sales_channel` biểu diễn **key**.
- `amount`, `currency_code` và `discount_percent` biểu diễn **value**.
- PK ba cột bảo đảm một `Product` không có hai entry trùng cùng key.
- Bảng không có PK riêng cho từng value object, vì `PriceQuote` không có danh tính entity độc lập.

Trong ví dụ JPA trước đó, `@CollectionTable(uniqueConstraints = ...)` yêu cầu **UNIQUE** theo tổ hợp ba cột khi provider sinh schema. DDL ở đây chọn **PRIMARY KEY** cho cùng tổ hợp, nên không cần thêm một UNIQUE lặp lại. Hai thiết kế đều có thể bảo vệ uniqueness nhưng không hoàn toàn tương đương về metadata và cách quản lý schema.

**Không nên giả định** việc khai báo annotation là đủ để database đang chạy tự có PK/FK/UNIQUE đúng. Khi schema được quản lý bằng Flyway, Liquibase hoặc SQL migration, chính migration phải bảo đảm các constraint vật lý phù hợp.

### Vì sao phải tính cả `product_id` vào uniqueness?

Hai sản phẩm khác nhau có thể cùng có giá theo thị trường và kênh `(VN, ONLINE)`:

~~~text
product_id=101, market_code=VN, sales_channel=ONLINE
product_id=202, market_code=VN, sales_channel=ONLINE
~~~

Đây là hai entry hợp lệ vì chúng thuộc **hai Map của hai Product khác nhau**. Nếu đặt `UNIQUE(market_code, sales_channel)` toàn bảng, sản phẩm thứ hai sẽ bị chặn sai. Phạm vi đúng của key thường là **trong collection của owner**, được thể hiện bằng `(product_id, market_code, sales_channel)`.

### Tính nullability của các thành phần key

Thông thường nên ràng buộc `NOT NULL` cho các thành phần của khóa Map nếu một entry luôn cần khóa đầy đủ. Một `Map` ở Java có thể chấp nhận null tùy implementation, nhưng mô hình khóa nhúng trên database có yêu cầu riêng về tính duy nhất, so sánh và FK/PK.

Nếu doanh nghiệp thật sự có trạng thái “thị trường chưa xác định”, cần mô hình hóa rõ trạng thái đó thay vì ngầm dùng NULL như một loại key không được kiểm soát.

## 7. Quy tắc đường dẫn thuộc tính `key.` / `value.`

Khi ghi đè thông qua `@AttributeOverride` ở field Map:

~~~java
@AttributeOverride(
    name = "key.marketCode",
    column = @Column(name = "market_code"))
~~~

**Phần trước dấu chấm đầu tiên** là từ khóa xác định phía:

- `key`: class embeddable dùng làm Map key.
- `value`: class embeddable dùng làm Map value.

Các thành phần còn lại là đường dẫn field/property Java:

~~~text
key.marketCode
└── MarketKey.marketCode

value.currencyCode
└── PriceQuote.currencyCode

value.rule.discountPercent
└── PriceQuote.rule.discountPercent
~~~

### Một số đường dẫn sai thường gặp

| Viết sai | Vì sao sai? | Cách viết đúng trong ví dụ |
| --- | --- | --- |
| `name = "market_code"` | Đây là tên cột DB, không phải tên field Java | `key.marketCode` |
| `name = "marketCode"` | Thiếu tiền tố phân biệt phía key trong Map | `key.marketCode` |
| `name = "value.marketCode"` | `marketCode` thuộc MarketKey, không phải PriceQuote | `key.marketCode` |
| `name = "key.currencyCode"` | `currencyCode` thuộc value | `value.currencyCode` |
| `name = "value.discountPercent"` | Thuộc tính nằm trong embeddable `rule` | `value.rule.discountPercent` |
| `name = "prices.key.marketCode"` | Không thêm tên field Map vào đường dẫn tại chính annotation đặt trên field Map | `key.marketCode` |
| `column = @Column(name = "value.amount")` | `value.amount` là đường dẫn Java, không phải tên cột mong muốn | `column = @Column(name = "amount")` |

Khi đọc code, hãy lần theo generic type `Map<K, V>`: thuộc tính nằm trong `K` thì dùng `key.`, nằm trong `V` thì dùng `value.`.

### Khi key và value có tên field giống nhau

Giả sử cả hai embeddable đều có thuộc tính `code`:

~~~java
@Embeddable
public class CodePart {
    private String code;

    protected CodePart() {
    }
}
~~~

Một Map có thể dùng `Map<CodePart, CodePart>` nếu class khóa được thiết kế với `equals/hashCode` phù hợp. Hai phía dùng **cùng class** nhưng cần **hai cột khác nhau**:

~~~java
@ElementCollection
@CollectionTable(
    name = "code_translations",
    joinColumns = @JoinColumn(name = "owner_id"))
@AttributeOverrides({
    @AttributeOverride(
        name = "key.code",
        column = @Column(name = "source_code")),
    @AttributeOverride(
        name = "value.code",
        column = @Column(name = "target_code"))
})
private Map<CodePart, CodePart> translations = new HashMap<>();
~~~

Chính tiền tố `key.` / `value.` cho phép JPA phân biệt **hai lần sử dụng cùng một embeddable**. Nếu không ghi đè và cả hai phía mặc định cùng tạo cột `code`, có thể phát sinh xung đột tên cột tùy cấu trúc mapping/provider.

## 8. Ghi đè embeddable lồng nhau ở phía value

Một `@Embeddable` có thể chứa một embeddable khác. Ví dụ:

~~~text
Map<MarketKey, ShippingOffer>

ShippingOffer
  ├─ price
  └─ destination: Address
       ├─ city
       └─ postalCode
~~~

Trong trường hợp này:

~~~java
@AttributeOverrides({
    @AttributeOverride(
        name = "value.price",
        column = @Column(name = "offer_price")),
    @AttributeOverride(
        name = "value.destination.city",
        column = @Column(name = "ship_city")),
    @AttributeOverride(
        name = "value.destination.postalCode",
        column = @Column(name = "ship_postal_code"))
})
~~~

Hai tiền tố `value.destination` là phần đường dẫn để đi từ map value đến embeddable lồng trong nó. Không cần tạo một entity mới chỉ vì embeddable có nhiều cấp; các thuộc tính basic của các cấp sẽ được lưu thành **các cột của cùng collection table**, trừ khi mô hình được thay đổi thành quan hệ entity thực sự.

### Ghi đè ở lớp embeddable hay nơi dùng Map?

Có thể đặt annotation trên `@Embedded` của class chứa nó để điều chỉnh một cách sử dụng cụ thể, nhưng khi yêu cầu cần phân biệt **key/value trong Map**, việc đặt `@AttributeOverride` ngay tại mapping Map với tiền tố đầy đủ làm ý định rõ ràng hơn.

Nếu cùng một `ShippingOffer` được sử dụng ở:

~~~java
@Embedded
private ShippingOffer defaultOffer;

@ElementCollection
private Map<MarketKey, ShippingOffer> offersByMarket;
~~~

hai vị trí sử dụng có thể cần tên cột khác nhau mà **không phải sửa mọi annotation ở class `ShippingOffer`**. Một ghi đè tại `offersByMarket` chỉ tác động tới context của Map đó.

## 9. Phân biệt `@AttributeOverride` với `@AssociationOverride`

`@AttributeOverride` ghi đè mapping **của thuộc tính basic** trong embeddable. Nhưng một embeddable còn có thể chứa **quan hệ tới entity**, chẳng hạn địa chỉ thanh toán chứa quốc gia được chuẩn hóa thành một entity `Country`.

Ví dụ lớp embeddable làm **value** của Map:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;

@Embeddable
public class DeliveryOption {

    @Column(name = "default_service_name")
    private String serviceName;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "default_country_id")
    private Country country;

    protected DeliveryOption() {
    }
}
~~~

Giả sử `Country` là một entity có PK `Long id`. Khi ánh xạ:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_delivery_options",
    joinColumns = @JoinColumn(name = "product_id"))
@MapKeyColumn(name = "option_code")
@AttributeOverride(
    name = "value.serviceName",
    column = @Column(name = "service_name"))
@AssociationOverride(
    name = "value.country",
    joinColumns = @JoinColumn(name = "country_id"))
private Map<String, DeliveryOption> deliveryOptions = new HashMap<>();
~~~

Với đoạn này cần import các annotation `ElementCollection`, `CollectionTable`, `MapKeyColumn`, `AttributeOverride`, `AssociationOverride`, `JoinColumn`, cùng `Map` và `HashMap`.

**Điểm khác biệt:**

- `value.serviceName` là thuộc tính basic nên dùng `@AttributeOverride`.
- `value.country` là một quan hệ `@ManyToOne` nên dùng `@AssociationOverride` để thay join column.
- Cột `country_id` nằm trong bảng collection `product_delivery_options`, được dùng làm FK tới bảng Country theo mapping.
- Key `String` của Map không phải embeddable nên dùng `@MapKeyColumn(name = "option_code")`, không dùng `key.someAttribute`.

Trong các phiên bản JPA hỗ trợ quan hệ to-one trong embeddable dùng làm element collection, đây là một cách hợp lệ để biểu diễn mối tham chiếu từ mỗi value tới một entity khác. Không nên đưa quan hệ collection-valued `@OneToMany` hoặc `@ManyToMany` tùy tiện vào embeddable của element collection; các giới hạn về relationship mapping trong embeddable phải được tuân thủ.

### AssociationOverride không tạo entity mới

`@AssociationOverride` chỉ thay metadata **join** của một quan hệ đã có trong embeddable. Nó không biến `DeliveryOption` thành entity và không tự tạo bảng entity riêng cho DeliveryOption.

Nếu giá trị của Map phải có danh tính và vòng đời độc lập, hãy cân nhắc mô hình `@OneToMany` hoặc entity liên kết phù hợp thay vì cố mở rộng embeddable quá mức.

## 10. Map key kiểu basic dùng `@MapKeyColumn`

Không phải mọi Map key đều là `@Embeddable`. Với Map đơn giản:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_labels",
    joinColumns = @JoinColumn(name = "product_id"))
@MapKeyColumn(name = "locale_code", nullable = false, length = 16)
@Column(name = "label_text", nullable = false, length = 250)
private Map<String, String> labels = new HashMap<>();
~~~

Một bản ghi có thể là:

~~~text
product_id | locale_code | label_text
-----------+-------------+-----------------------
101        | vi-VN       | Sách học JPA
101        | en-US       | JPA Learning Book
~~~

Ở đây:

- Key là `String` nên `@MapKeyColumn` chọn cột `locale_code`.
- Value cũng là `String` nên `@Column` chọn cột `label_text`.
- Không cần `@AttributeOverride(name = "key....")` vì `String` **không có thuộc tính nhúng bên trong**.
- Ràng buộc uniqueness hợp lý thường là `(product_id, locale_code)`.

### Basic key + embeddable value

Một Map khác có `String` làm key nhưng `PriceQuote` làm value:

~~~java
@ElementCollection
@CollectionTable(
    name = "prices_by_locale",
    joinColumns = @JoinColumn(name = "product_id"))
@MapKeyColumn(name = "locale_code", length = 16)
@AttributeOverrides({
    @AttributeOverride(
        name = "value.amount",
        column = @Column(name = "price_amount")),
    @AttributeOverride(
        name = "value.currencyCode",
        column = @Column(name = "price_currency"))
})
private Map<String, PriceQuote> pricesByLocale = new HashMap<>();
~~~

Trong trường hợp này, `key` là basic nên dùng `@MapKeyColumn`, còn các field bên trong `value` vẫn có thể ghi đè bằng tiền tố `value.`. Nếu `PriceQuote` còn chứa `rule`, có thể bổ sung override đường dẫn `value.rule.discountPercent` khi muốn thay tên cột tương ứng.

## 11. Embeddable key + basic value

Trường hợp ngược lại:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_stock_by_market",
    joinColumns = @JoinColumn(name = "product_id"))
@AttributeOverrides({
    @AttributeOverride(
        name = "key.marketCode",
        column = @Column(name = "market_code")),
    @AttributeOverride(
        name = "key.salesChannel",
        column = @Column(name = "sales_channel"))
})
@Column(name = "stock_quantity", nullable = false)
private Map<MarketKey, Integer> stockByMarket = new HashMap<>();
~~~

Trong ví dụ này:

- Khóa `MarketKey` là embeddable nên dùng `key.marketCode` và `key.salesChannel`.
- Giá trị `Integer` là kiểu basic, được ánh xạ bằng `@Column(name = "stock_quantity")`.
- Không có thuộc tính `value.amount` hoặc `value.quantity` vì value **chính nó đã là một giá trị basic**, không chứa trường persistent cần ghi đè.

Nếu số lượng tồn kho phải gắn với transaction, kho vật lý, hàng giữ chỗ và lịch sử nhập/xuất, một Map basic như vậy có thể không đủ để biểu diễn domain. Trong trường hợp này, entity `InventoryBalance` hoặc bảng ledger có ràng buộc và vòng đời riêng thường thích hợp hơn.

## 12. Phân biệt `@MapKeyColumn`, `@MapKeyJoinColumn` và `@MapKey(name = ...)`

Trong JPA, Map key có thể đến từ **một cột độc lập**, **một entity được tham chiếu**, hoặc **một thuộc tính của entity value**. Ba trường hợp này rất khác nhau.

| Cơ chế | Dùng khi nào? | Ví dụ ý nghĩa |
| --- | --- | --- |
| `@MapKeyColumn` | Map key là kiểu basic lưu trong một cột | `Map<String, PriceQuote>` với `locale_code` |
| `@AttributeOverride(name = "key.x")` | Map key là embeddable chứa các field basic | `Map<MarketKey, PriceQuote>` |
| `@MapKeyJoinColumn` / `@MapKeyJoinColumns` | Map key là entity được lưu thông qua FK | Key là `Region` entity |
| `@MapKey(name = "someProperty")` | Key lấy từ thuộc tính đã được ánh xạ của entity value | Dùng `ProductVariant.code` làm key của map |

### 12.1. `@MapKeyJoinColumn` cho entity key

Nếu key là một entity `Region` được định danh bằng khóa ngoại, một mapping phù hợp có thể dùng `@MapKeyJoinColumn(name = "region_id")`. Trong trường hợp đó, key không phải một embeddable có trường `regionCode` nằm ngay trong collection table; cột `region_id` tham chiếu một hàng entity `Region`.

Không dùng:

~~~java
@AttributeOverride(
    name = "key.regionCode",
    column = @Column(name = "region_id"))
~~~

để thay thế `@MapKeyJoinColumn` nếu `key` thật sự là entity. `@AttributeOverride` chỉ áp dụng cho các thuộc tính basic được nhúng, không phải công cụ tạo FK entity map key.

### 12.2. `@MapKey(name = "...")` lấy key từ entity value

Ví dụ có entity `ProductVariant` với field `variantCode`, và entity cha có:

~~~java
@OneToMany(mappedBy = "product")
@MapKey(name = "variantCode")
private Map<String, ProductVariant> variants = new HashMap<>();
~~~

Điều này yêu cầu `ProductVariant` có thuộc tính persistent `variantCode` và quan hệ `product` đã được ánh xạ phù hợp. Map key lấy **giá trị thuộc tính của entity value** thay vì dùng một cột map-key độc lập.

Khi `variantCode` thay đổi, provider không nhất thiết tự sắp xếp lại cấu trúc `Map` đang nằm trong bộ nhớ. Ứng dụng phải có quy tắc đồng bộ và tránh thay đổi thuộc tính được dùng làm key khi map đã được tải.

### 12.3. Giá trị là entity thì không dùng `@ElementCollection`

Nếu `Map` chứa các entity độc lập làm value, quan hệ phù hợp thường là `@OneToMany` hoặc `@ManyToMany`. `@ElementCollection` dành cho **basic và embeddable value**, không có nghĩa là mọi entry trong Map đều có entity lifecycle riêng.

Việc lựa chọn Map key basic, embeddable hoặc entity phải dựa vào domain, không phải cố sử dụng `@AttributeOverride` cho tất cả trường hợp.

## 13. Ghi đè không thay đổi định nghĩa gốc của embeddable

Giả sử `MarketKey` cũng được dùng ở entity khác:

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "marketCode",
        column = @Column(name = "default_market")),
    @AttributeOverride(
        name = "salesChannel",
        column = @Column(name = "default_channel"))
})
private MarketKey defaultMarket;
~~~

Ở một field `@Embedded` **không nằm trong Map**, đường dẫn ghi đè là:

~~~text
marketCode
salesChannel
~~~

Ở field `Map<MarketKey, PriceQuote>`, đường dẫn lại là:

~~~text
key.marketCode
key.salesChannel
~~~

Lý do không phải vì class `MarketKey` thay đổi, mà vì có **thêm một cấp ngữ cảnh Map**. Tiền tố `key.` hoặc `value.` nói JPA phải bước vào phía nào trước khi đi tới thuộc tính embeddable.

Nhờ vậy, một class embeddable có thể tái sử dụng ở nhiều vị trí với tên cột cụ thể của từng ngữ cảnh mà không cần tạo nhiều class Java gần như giống hệt nhau chỉ để đổi annotation `@Column`.

## 14. Những thay đổi nào là override, những thay đổi nào là cấu trúc Map?

`@AttributeOverride` dùng để **ghi đè ánh xạ cột** của một thuộc tính basic đã tồn tại trong embeddable. Nó không tạo mới thuộc tính Java hoặc thay đổi kiểu ngữ nghĩa của Map.

| Nhu cầu | Cách xử lý |
| --- | --- |
| Đổi tên cột `marketCode` từ `default_market_code` sang `market_code` | `@AttributeOverride(name = "key.marketCode", column = ...)` |
| Đổi độ dài cột key | `@AttributeOverride` với `@Column(length = ...)` |
| Đổi precision/scale của một số tiền ở value | `@AttributeOverride(name = "value.amount", column = @Column(precision=...,scale=...))` |
| Đổi tên cột thuộc embeddable lồng nhau | Đường dẫn `value.rule.discountPercent` |
| Đổi join column của quan hệ to-one trong value embeddable | `@AssociationOverride(name = "value.country", joinColumns = ...)` |
| Đổi bảng chứa các entry Map | `@CollectionTable(name = ...)` |
| Đổi FK từ collection table về entity owner | `@CollectionTable(joinColumns = @JoinColumn(...))` |
| Đổi cột key basic của Map | `@MapKeyColumn` |
| Đổi Map value từ embeddable thành entity | Thiết kế lại quan hệ/lifecycle, không chỉ override |
| Thêm thuộc tính hoàn toàn mới | Sửa class embeddable và schema, không chỉ `@AttributeOverride` |

### Override không phải đổi kiểu Java

Ví dụ `PriceQuote.amount` là `BigDecimal`. Annotation:

~~~java
@AttributeOverride(
    name = "value.amount",
    column = @Column(
        name = "amount",
        precision = 14,
        scale = 2))
~~~

chọn tên và precision của cột SQL, nhưng vẫn không biến `amount` thành `String` trong Java. Nếu cần chuyển biểu diễn dữ liệu (ví dụ `MonetaryAmount` thành số nguyên minor units), có thể cần `AttributeConverter` hoặc thiết kế value object khác, không chỉ đổi tên cột.

## 15. Làm rõ access type khi sử dụng embeddable trong Map

Trong JPA, vị trí đặt annotation ánh xạ có thể phụ thuộc **field access** hay **property access**. Ví dụ minh họa ở các mục trước dùng field access:

~~~java
@Embeddable
public class MarketKey {
    @Column(name = "default_market_code")
    private String marketCode;
}
~~~

Khi `@AttributeOverride(name = "key.marketCode", ...)` đặt trên field Map của entity, provider cần xác định `marketCode` là **thuộc tính persistent** của embeddable theo quy tắc access áp dụng.

Nếu một embeddable tái sử dụng trong nhiều ngữ cảnh có access khác nhau, có thể dùng `@Access(AccessType.FIELD)` hoặc `@Access(AccessType.PROPERTY)` tường minh khi phù hợp. Không trộn annotation trên field và getter một cách tùy tiện.

**Lưu ý:** `name = "key.marketCode"` vẫn dùng **tên thuộc tính theo mô hình Java**, không dùng tên getter `getMarketCode` và cũng không dùng tên cột SQL mặc định.

## 16. Key của Map phải ổn định khi dùng `HashMap`

Giả sử:

~~~java
MarketKey key = new MarketKey("VN", "ONLINE");
prices.put(key, quote);
~~~

Nếu `MarketKey` có setter cho `marketCode` rồi ứng dụng đổi key thành `"SG"` **sau khi đã put vào HashMap**, đối tượng key có thể nằm ở bucket dựa trên hash code cũ, khiến `get()` hoặc `remove()` không hoạt động như dự kiến. Đây là vấn đề của cấu trúc Java, chưa kể provider JPA còn cần cập nhật các cột nhận diện entry.

Vì vậy:

- Xem embeddable dùng làm Map key như **value object bất biến về mặt nghiệp vụ**.
- Không đặt setter công khai cho các thành phần key nếu không cần.
- Khi cần đổi key, hãy **remove entry cũ rồi put entry mới** với key object mới.
- Kiểm tra xem key mới có trùng với key của entry đã tồn tại không.
- Không dùng các thuộc tính volatile như số lượng tồn kho, giá tiền hoặc trạng thái xử lý làm thành phần key nếu chúng thay đổi thường xuyên.

Ví dụ:

~~~java
public void movePrice(
        MarketKey oldKey,
        MarketKey newKey) {

    if (oldKey.equals(newKey)) {
        return;
    }

    if (!prices.containsKey(oldKey)) {
        throw new IllegalArgumentException("Không có giá tại key cũ");
    }

    if (prices.containsKey(newKey)) {
        throw new IllegalStateException("Key mới đã có giá");
    }

    PriceQuote value = prices.remove(oldKey);
    prices.put(newKey, value);
}
~~~

Phương thức được hình dung là thành viên của entity `Product`. Khi entity được quản lý và transaction hoạt động, provider có thể đồng bộ việc đổi key thành DELETE/INSERT hoặc chiến lược khác tùy cách nó theo dõi element collection. **Không cam kết số lượng SQL hay thứ tự phát lệnh chỉ từ thao tác Map.**

Đối với yêu cầu bất biến của business key, DB còn cần UNIQUE/PK phù hợp để ngăn hai transaction đồng thời tạo cùng key.

## 17. Tương đương trong Java và tính duy nhất trong database

Giả sử Java xem hai key bằng nhau khi:

~~~java
new MarketKey("VN", "ONLINE")
new MarketKey("VN", "ONLINE")
~~~

được so sánh bằng `equals()`. Nhưng database có thể có collation khác:

~~~text
Java key A: ("vn", "online")
Java key B: ("VN", "ONLINE")
~~~

Nếu Java phân biệt hoa/thường nhưng DB không phân biệt theo collation/index, hai key có thể **khác trong Map Java nhưng trùng theo UNIQUE của SQL**. Ngược lại, nếu ứng dụng chuẩn hóa mã trước khi so sánh nhưng DB UNIQUE theo chuỗi thô phân biệt hoa/thường, database có thể nhận những hàng mà domain coi là trùng.

Phương án:

1. Xác định một chính sách canonicalization rõ ràng cho các thành phần key (ví dụ upper-case mã ASCII theo `Locale.ROOT` khi domain cho phép).
2. Áp dụng chính sách nhất quán trước khi tạo embeddable key.
3. Bảo đảm DB unique constraint/index thực thi cùng ngữ nghĩa so sánh.
4. Ghi rõ cách xử lý dấu cách, null, Unicode và các mã được cấp từ hệ thống bên ngoài.

Ví dụ:

~~~java
import java.util.Locale;
import java.util.Objects;

private static String normalizeAsciiCode(String value) {
    String result = Objects.requireNonNull(value)
            .trim()
            .toUpperCase(Locale.ROOT);
    if (result.isEmpty()) {
        throw new IllegalArgumentException("Mã không được rỗng");
    }
    return result;
}
~~~

Đây là quy tắc minh họa cho **mã kỹ thuật ASCII được nghiệp vụ cho phép chuẩn hóa**; không áp dụng máy móc cho tên người, tiếng tự nhiên hoặc mọi loại identifier quốc tế.

## 18. Cách provider quản lý vòng đời của Map embeddable

Một `@ElementCollection` không lưu mỗi value như một entity độc lập có `@Id`. Các giá trị được quản lý như **phần trạng thái của entity owner**. Khi:

~~~java
Product product = em.find(Product.class, productId);

product.putPrice(
        new MarketKey("VN", "ONLINE"),
        new PriceQuote(
                new BigDecimal("199000.00"),
                "VND",
                new PriceRule(new BigDecimal("5.00"))));
~~~

nếu đoạn chạy trong transaction và `product` là entity managed, provider có thể phát hiện thay đổi trên collection và đồng bộ khi flush/commit.

### 18.1. Thay value tại một key

~~~java
product.putPrice(existingKey, newQuote);
~~~

Về ngữ nghĩa Java, entry ở key đó nhận value mới. Provider có thể thực thi UPDATE, DELETE/INSERT hoặc một loạt câu lệnh khác tùy triển khai và trạng thái collection. Không nên kỳ vọng một thao tác `Map.put()` luôn tương ứng đúng một SQL UPDATE.

### 18.2. Xóa entry

~~~java
product.removePrice(existingKey);
~~~

Khi được đồng bộ, hàng tương ứng với owner và key cần được xóa khỏi collection table. Không có một entity `PriceQuote` độc lập để gọi `em.remove(quote)` theo cách entity thông thường.

### 18.3. Xóa owner

Khi xóa `Product`, các hàng element collection của nó thuộc vòng đời của owner và phải được xử lý theo mapping/provider. Cơ chế xóa cụ thể có thể kết hợp SQL do JPA phát và chính sách FK database.

**Phân biệt:** element collection không phải quan hệ `@OneToMany` tới entity độc lập; giá trị nhúng thường không được chia sẻ theo identity giữa nhiều owner.

### 18.4. Không thay toàn bộ collection bằng object mới một cách tùy tiện

Ở một entity managed, việc thay một persistent collection instance bằng một `HashMap` mới có thể ảnh hưởng cách provider theo dõi thay đổi, đặc biệt khi có proxy/persistent collection wrapper. Thông thường nên cung cấp phương thức nghiệp vụ cập nhật Map hiện tại (put/remove/clear có kiểm soát), thay vì phơi bày setter tự thay cả field collection.

## 19. Vai trò của uniqueness và concurrency

Giả sử Product 101 chưa có giá cho key `("SG", "STORE")`. Hai request đến cùng lúc:

~~~text
Transaction A                          Transaction B
---------------------------            ---------------------------
Đọc Map: chưa thấy key                 Đọc Map: chưa thấy key
put(("SG","STORE"), quoteA)            put(("SG","STORE"), quoteB)
flush/commit                           flush/commit
                 \                      /
                  \                    /
               UNIQUE(product_id, market_code, sales_channel)
                              |
              Một thao tác xung đột cần được xử lý
~~~

Một Map trong memory chỉ có một value cho mỗi key, nhưng **hai transaction có hai persistence context khác nhau**. Do đó Java `Map.put()` hoặc kiểm tra `containsKey()` không đủ để chống trùng dữ liệu đồng thời.

Tùy nhu cầu:

- Bảo vệ uniqueness bằng PK/UNIQUE thực tế trong DB.
- Xử lý `PersistenceException` do constraint và rollback transaction lỗi.
- Dùng optimistic locking trên owner với `@Version`, nếu provider và mẫu cập nhật collection thực thi kiểm soát version phù hợp; cần xác nhận behavior của stack.
- Dùng pessimistic locking trên owner khi nghiệp vụ cần serialize cập nhật cùng một Map.
- Với thao tác idempotent, cân nhắc cơ chế upsert native của DBMS có kiểm soát và tác động tới persistence context.

Nếu hai request cùng sửa value của **cùng một key** mà không tạo hàng mới, unique constraint không giải quyết **lost update**. Khi đó cần cơ chế kiểm soát đồng thời cho nội dung value, không chỉ chống cặp khóa trùng.

## 20. Truy vấn Map với JPQL: KEY và VALUE

JPA có biểu thức truy vấn giúp truy cập các entry của Map ở mức entity:

~~~java
List<Object[]> entries = em.createQuery(
        "SELECT KEY(p), VALUE(p) "
      + "FROM Product product JOIN product.prices p "
      + "WHERE product.id = :productId",
        Object[].class)
    .setParameter("productId", productId)
    .getResultList();
~~~

Mỗi hàng kết quả gồm key và value của một entry. Với ví dụ này, key là `MarketKey` và value là `PriceQuote`.

Trong JPQL:

- `KEY(p)` tham chiếu khóa của entry Map.
- `VALUE(p)` tham chiếu giá trị của entry Map.
- `p` là identification variable từ phép join vào Map.

Khả năng đi sâu vào từng thuộc tính embeddable trong biểu thức truy vấn, bao gồm đường dẫn qua `KEY(p)`, có thể phụ thuộc cú pháp JPQL được phiên bản/spec/provider hỗ trợ; không nên mặc định mọi biểu thức lồng phức tạp đều portable như SQL.

**Đừng nhầm:** `key.` và `value.` trong `@AttributeOverride(name = "...")` là **quy ước tên thuộc tính để ánh xạ**, không phải tên cột hoặc cú pháp SQL. Các từ khóa `KEY(...)`/`VALUE(...)` trong JPQL là **biểu thức truy vấn** ở thời điểm đọc dữ liệu; hai khái niệm có liên hệ nhưng phục vụ hai mục đích khác nhau.

### Đọc theo từng entry thay vì tải toàn Map

Khi Map rất lớn, việc tải cả collection để tìm một giá theo key có thể tốn bộ nhớ và phát sinh SELECT không cần thiết. Có thể dùng truy vấn có điều kiện với key/value, projection hoặc native SQL phù hợp với provider và database đang sử dụng. Cột `(product_id, market_code, sales_channel)` được index theo PK/UNIQUE ở ví dụ có thể hỗ trợ truy vấn entry cụ thể.

## 21. Phân biệt `@CollectionTable` và `@JoinTable`

Hai annotation đều nhắc đến một bảng trung gian, nhưng áp dụng vào các mô hình khác nhau:

| Annotation | Áp dụng cho | Bảng thường chứa |
| --- | --- | --- |
| `@CollectionTable` | `@ElementCollection` của basic/embeddable values | FK owner và các cột basic/embeddable của collection |
| `@JoinTable` | Quan hệ giữa các entity như `@ManyToMany` hoặc một số quan hệ khác | FK của các entity liên quan |

Với:

~~~java
@ElementCollection
@CollectionTable(
    name = "product_price_matrix",
    joinColumns = @JoinColumn(name = "product_id"))
private Map<MarketKey, PriceQuote> prices;
~~~

`PriceQuote` không có `@Entity` hay PK nên dùng `@CollectionTable`.

Với:

~~~java
@ManyToMany
@JoinTable(
    name = "product_tags",
    joinColumns = @JoinColumn(name = "product_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id"))
private Set<Tag> tags;
~~~

`Tag` là entity riêng, liên kết theo FK giữa hai entity nên dùng `@JoinTable`.

**Không phải cứ có bảng trung gian là dùng `@JoinTable`.** Khi Map chứa giá trị nhúng, `@CollectionTable` là công cụ cơ bản để chọn bảng lưu state của collection.

## 22. Một số giới hạn và quyết định thiết kế

### 22.1. Map key nhúng không nên chứa trạng thái quan hệ phức tạp

Một embeddable key thường nên bao gồm các thuộc tính **basic, ổn định và có khả năng so sánh theo giá trị**. Điều này giúp:

- Xác định key duy nhất trong Java và SQL.
- Xây dựng `equals/hashCode` rõ ràng.
- Tránh phải tải entity khác để tính hash code hoặc so sánh key.
- Giảm rủi ro thay đổi FK/ID gây biến đổi identity của entry.

Nếu key về bản chất là một entity `Country` hoặc `Region` có danh tính độc lập, hãy cân nhắc Map key kiểu entity và mapping `@MapKeyJoinColumn` thay vì nhét entity reference vào embeddable key một cách không cần thiết.

### 22.2. Value object nhiều chiều có thể cần entity riêng

Nếu `PriceQuote` bắt đầu có lịch sử thay đổi, phê duyệt, người tạo, mã định danh, version và nhiều nơi tham chiếu tới cùng một quote, việc giữ nó như embeddable value trong `@ElementCollection` có thể không còn phản ánh domain.

Khi đó, cân nhắc:

~~~text
Product (1) ---- (N) ProductPrice (N) ---- (1) Market
                       |
                       +-- @Id
                       +-- amount
                       +-- validFrom
                       +-- version
~~~

Một entity `ProductPrice` độc lập có thể có `@ManyToOne` tới Product, khóa thay thế hoặc khóa ghép, uniqueness theo thị trường/kênh/thời gian. Đây là **thay đổi mô hình nghiệp vụ**, không phải vấn đề sửa `@AttributeOverride`.

### 22.3. Key được phép trùng trong DB theo điều kiện lịch sử?

Nếu cùng owner và cùng key có **nhiều phiên bản giá theo thời gian**, `Map<MarketKey, PriceQuote>` chỉ giữ được một value cho một key tại một thời điểm trong bộ nhớ. Không thể biểu diễn hai hàng:

~~~text
product_id=101, market=VN, channel=ONLINE, valid_from=2027-01-01
product_id=101, market=VN, channel=ONLINE, valid_from=2027-02-01
~~~

như hai entry của cùng một Map nếu key chỉ chứa `market` và `channel`. Có thể mở rộng key thêm `validFrom` nếu domain coi phiên bản ngày hiệu lực là một phần khóa, hoặc dùng một entity lịch sử riêng.

Việc bỏ UNIQUE theo key mà vẫn giữ `Map<MarketKey, PriceQuote>` có thể khiến nhiều hàng database không thể biểu diễn nhất quán dưới dạng một Map Java.

### 22.4. Converter và giá trị nhúng

`@Convert` và `AttributeConverter` có thể hữu ích cho các thuộc tính basic đặc biệt (ví dụ mã tiền tệ hoặc value object chuyển thành một cột), nhưng cần phân biệt:

- `@AttributeOverride`: đổi **metadata cột** của một thuộc tính đã mapped.
- `@Convert`: đổi **cách biểu diễn dữ liệu** giữa Java và database.
- `@AssociationOverride`: đổi **join metadata** của một relationship trong embeddable.

Không dùng converter để giải quyết một vấn đề đơn thuần là xung đột tên cột của embeddable.

## 23. Những lỗi ánh xạ phổ biến

| Lỗi | Hệ quả có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Viết `name = "marketCode"` cho key nhúng trong Map | Không chọn đúng phía key theo quy tắc Map | Dùng `key.marketCode` |
| Viết `name = "value.marketCode"` khi field nằm ở MarketKey | Provider tìm thuộc tính sai phía | Dùng `key.marketCode` |
| Dùng tên cột DB thay cho tên field Java trong `name` | Override không khớp thuộc tính | `name = "value.amount"` và `column.name = "amount"` |
| Quên đoạn `rule.` trong embeddable lồng nhau | Override không đi tới field thực | Dùng `value.rule.discountPercent` |
| Dùng `@MapKeyColumn` cho key embeddable có nhiều field | Không mô tả từng thành phần key | Dùng `@AttributeOverrides` với `key.*` |
| Dùng `@AttributeOverride` để đổi FK của `@ManyToOne` trong value | Sai loại metadata | Dùng `@AssociationOverride` |
| Coi `@CollectionTable.joinColumns` là cột của map key | Trộn owner FK và key-value mapping | Phân biệt `product_id` với `market_code` |
| Đặt `UNIQUE(market_code, sales_channel)` toàn collection table | Chặn hai Product dùng cùng key | Thêm owner FK vào phạm vi UNIQUE/PK |
| Không có constraint tại DB | Concurrent inserts có thể trùng entry | Bổ sung PK/UNIQUE qua migration |
| Sửa field của key object đang nằm trong HashMap | Hash code thay đổi, lookup thất bại | Key ổn định; remove và put key mới |
| Equality key khác quy tắc so sánh của DB | Key Java không trùng nhưng DB coi trùng hoặc ngược lại | Thống nhất canonicalization/collation |
| Trông chờ `@Column` ở embeddable tự đổi tên theo từng lần dùng | Trùng tên cột khi reuse/nesting | Override tại vị trí Map |
| Dùng `@ElementCollection` cho Map value là entity | Sai vòng đời/mapping collection | Dùng association phù hợp |
| Lưu nhiều hàng cùng key nhưng ánh xạ vào Map một giá trị | Không có biểu diễn một-một của entry | Đổi key hoặc tạo entity lịch sử |
| Chỉ kiểm tra `containsKey()` để chống trùng | Race condition giữa transaction | DB uniqueness + xử lý conflict |
| Dùng migration khác với tên cột trong annotation | Lỗi SQL khi runtime | Đồng bộ schema và JPA mapping |

## 24. Quy trình thiết kế một Map có key/value nhúng

Một trình tự đáng dùng khi nhận yêu cầu mới:

1. **Xác định owner:** Map thuộc entity nào? Owner có PK gì?
2. **Xác định ngữ nghĩa key:** một key gồm bao nhiêu thành phần, có thật sự ổn định không?
3. **Xác định ngữ nghĩa value:** value chỉ là trạng thái nhúng hay có định danh/vòng đời riêng?
4. **Chọn kiểu Java:** `Map<Basic, Basic>`, `Map<Embeddable, Embeddable>` hay Map có entity?
5. **Chọn mapping collection:** `@ElementCollection + @CollectionTable` cho basic/embeddable value; quan hệ khác nếu value là entity.
6. **Thiết kế tên cột owner FK:** thường dùng `@CollectionTable(joinColumns=...)`.
7. **Liệt kê thuộc tính key và value:** xác định chính xác đường dẫn Java, kể cả embeddable lồng nhau.
8. **Khai báo override tại vị trí dùng Map:** `key.foo`, `value.bar`, `value.nested.baz`.
9. **Khai báo association override nếu value có quan hệ to-one:** không dùng nhầm attribute override cho FK entity.
10. **Thiết kế uniqueness và NOT NULL:** mặc định thường là owner FK + toàn bộ key columns.
11. **Thống nhất equality/canonicalization:** key Java và DB phải coi cùng các giá trị là tương đương.
12. **Định nghĩa thao tác cập nhật:** put value, remove entry, thay key bằng remove/put và xử lý concurrent writes.
13. **Đảm bảo schema migration khớp mapping:** tên cột, precision, length, FK, PK/UNIQUE và index.
14. **Xem xét giới hạn của mô hình:** lịch sử, phiên bản, nhiều value cho một key hoặc shared value có thể cần entity riêng.

Những bước trên giúp phân biệt hai nhóm vấn đề: **lỗi ghi đè mapping của embeddable** và **thiết kế key/value không phù hợp với domain**. Không thể sửa nhóm thứ hai chỉ bằng đổi tên cột.

## 25. Bài tập vận dụng

### Bài 1 — Ghi đè field của khóa

Có:

~~~java
@Embeddable
class LocaleChannelKey {
    private String locale;
    private String channel;
}
~~~

Và:

~~~java
Map<LocaleChannelKey, PriceQuote> quotes;
~~~

Muốn đặt hai cột là `locale_code` và `channel_code`. Trong `@AttributeOverride(name = "...")` cần dùng những đường dẫn nào?

**Gợi ý:** `key.locale` và `key.channel`. Hai giá trị `locale_code` và `channel_code` nằm trong `@Column(name = "...")`.

### Bài 2 — Ghi đè giá trị nhúng

`PriceQuote` có `amount` và `currencyCode`. Muốn cột ở collection table là `sale_amount` và `sale_currency`, phải khai báo thế nào?

**Gợi ý:** dùng `@AttributeOverride(name = "value.amount", column = @Column(name = "sale_amount"))` và tương tự với `value.currencyCode`.

### Bài 3 — Embeddable lồng nhau

Value `DeliveryOption` có `address: Address`; `Address` chứa `postalCode`. Cột mong muốn là `delivery_postal_code`.

**Gợi ý:** `@AttributeOverride(name = "value.address.postalCode", column = @Column(name = "delivery_postal_code"))`.

### Bài 4 — Key basic, value embeddable

Với `Map<String, PriceQuote>`, khóa String là mã thị trường cần lưu ở cột `market_code`. Có nên viết `key.marketCode` không?

**Gợi ý:** không. Key là basic type nên dùng `@MapKeyColumn(name = "market_code")`. Các field bên trong value vẫn dùng `value.*` khi ghi đè.

### Bài 5 — Quan hệ trong value

Value `DeliveryOption` chứa `@ManyToOne Country country`. Cần đổi join column từ `default_country_id` thành `shipping_country_id`.

**Gợi ý:** dùng `@AssociationOverride(name = "value.country", joinColumns = @JoinColumn(name = "shipping_country_id"))`, không dùng `@AttributeOverride`.

### Bài 6 — Phạm vi uniqueness

Bảng `product_price_matrix` có cùng `(VN, ONLINE)` cho Product 101 và Product 202. Đây có phải hai entry trùng cần chặn không?

**Gợi ý:** không, vì Map thuộc hai owner khác nhau. Constraint hợp lý bao gồm `(product_id, market_code, sales_channel)`.

### Bài 7 — Key mutable

Ứng dụng gọi `put(key, quote)` rồi đổi `key.marketCode` từ `VN` thành `SG`. Vì sao `HashMap.get(key)` và JPA mapping có thể gặp vấn đề?

**Gợi ý:** hash code thay đổi sau khi key đã nằm trong Map; provider cũng cần xác định entry cũ/mới. Giữ key bất biến, đổi bằng remove key cũ rồi put key mới.

### Bài 8 — Lịch sử giá theo ngày

Một sản phẩm có nhiều giá ở cùng thị trường/kênh cho các ngày hiệu lực khác nhau. `Map<MarketKey, PriceQuote>` hiện tại có biểu diễn đồng thời mọi phiên bản không?

**Gợi ý:** không nếu `MarketKey` chỉ gồm thị trường và kênh. Có thể mở rộng key bằng ngày hiệu lực hoặc mô hình hóa entity lịch sử tùy nghiệp vụ.

### Bài 9 — Trùng code trên hai phía

Map dùng cùng một embeddable `CodePart` làm key và value, cả hai có field `code`. Làm sao chỉ rõ cột nguồn và cột đích?

**Gợi ý:** `key.code` ánh xạ cột `source_code`, `value.code` ánh xạ cột `target_code`.

### Bài 10 — Cập nhật đồng thời

Hai transaction cùng put giá vào cùng key cho Product 101. Có thể tin tưởng `Map.put()` ở mỗi transaction tự bảo đảm database không có hai hàng trùng không?

**Gợi ý:** không. Cần UNIQUE/PK ở database và xử lý concurrency; khi cả hai cập nhật cùng value còn phải cân nhắc lost update.

## Kết luận

**Ghi đè thuộc tính của key và value nhúng trong Map là việc ánh xạ đúng một thuộc tính Java vào đúng cột SQL tại đúng vị trí sử dụng embeddable.** Trong `@ElementCollection Map<K,V>`, đường dẫn `key.fieldName` trỏ tới field của embeddable key; `value.fieldName` trỏ tới field của embeddable value. Với embeddable lồng nhau, dùng đường dẫn như `value.rule.discountPercent`. Tên đặt trong `@AttributeOverride(name = ...)` là đường dẫn thuộc tính Java; tên cột SQL nằm trong `@Column(name = ...)`.

`@CollectionTable` chọn bảng và FK về owner, `@MapKeyColumn` xử lý key basic, `@AssociationOverride` thay join mapping của quan hệ nằm trong embeddable value. Chúng giải quyết các lớp vấn đề khác nhau và không nên dùng thay thế lẫn nhau.

Về mặt thiết kế, một Map persistent còn đòi hỏi **key có equality ổn định**, schema bảo vệ **tính duy nhất theo owner + key**, và quy tắc xử lý thay key, thay value, lịch sử và ghi đồng thời. Khi giá trị hoặc liên kết đã có danh tính và vòng đời riêng, nên cân nhắc chuyển sang entity thay vì cố ép mọi dữ liệu vào embeddable Map. Sự nhất quán giữa **object graph Java, metadata JPA và constraint SQL thật** mới quyết định mapping đúng và bền vững.
