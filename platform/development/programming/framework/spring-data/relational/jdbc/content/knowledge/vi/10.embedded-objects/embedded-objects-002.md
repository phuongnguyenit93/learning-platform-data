# Mô hình hóa địa chỉ hoặc số tiền bằng value object

Trong ứng dụng Spring Data Relational JDBC, không phải dữ liệu nào cũng cần trở thành một entity hoặc một bảng riêng. Một địa chỉ giao hàng, địa chỉ thanh toán hoặc số tiền thường là **value object**: một nhóm giá trị mô tả một khái niệm trong nghiệp vụ, được sở hữu bởi một đối tượng khác và không có danh tính độc lập trong miền nghiệp vụ.

Spring Data JDBC hỗ trợ mô hình này bằng **embedded object**. Các thuộc tính của value object được ánh xạ thành các cột trong cùng hàng với aggregate root. Nhờ đó, mã Java vẫn biểu diễn được cấu trúc có ý nghĩa như `Address` hoặc `Money`, trong khi schema quan hệ lưu các giá trị đó bằng các cột thông thường.

Bài học trình bày cách thiết kế value object, dùng `@Embedded` và prefix để ánh xạ địa chỉ/số tiền, lựa chọn cách xử lý khi tất cả cột đều `NULL`, thiết kế constraint trong database và những trường hợp nên dùng một bảng riêng thay cho embedded object.

## 1. Value object là gì?

**Value object** là đối tượng được xác định bởi các giá trị cấu thành nó, thay vì một ID riêng. Hai value object có cùng giá trị được xem là tương đương theo ý nghĩa nghiệp vụ.

Ví dụ:

- Địa chỉ gồm đường, thành phố, mã bưu chính và quốc gia.
- Số tiền gồm giá trị số và loại tiền tệ.
- Khoảng thời gian gồm thời điểm bắt đầu và kết thúc.
- Tọa độ gồm kinh độ và vĩ độ.

Một địa chỉ thường không cần một `address_id` chỉ để diễn đạt địa chỉ giao hàng của một đơn hàng. Địa chỉ đó có ý nghĩa trong ngữ cảnh đơn hàng sở hữu nó. Tương tự, số tiền `100.00 USD` và `100.00 VND` không có cùng ý nghĩa; chỉ lưu `100.00` là chưa đủ thông tin.

### Entity và value object khác nhau thế nào?

| Tiêu chí | Entity | Value object |
| --- | --- | --- |
| Danh tính | Có identity ổn định, thường là ID | Không cần identity riêng |
| So sánh | Chủ yếu theo identity | Theo toàn bộ giá trị cấu thành |
| Vòng đời | Có thể tồn tại độc lập trong miền nghiệp vụ | Thường thuộc vòng đời của đối tượng sở hữu |
| Thay đổi | Có thể cập nhật trạng thái trong khi giữ nguyên identity | Thường bất biến; thay đổi bằng cách tạo giá trị mới |
| Ví dụ | `Customer`, `PurchaseOrder`, `Product` | `Address`, `Money`, `DateRange` |

Giả sử một đơn hàng có địa chỉ giao hàng. Nếu người mua sửa địa chỉ của đơn hàng trước khi gửi, nghiệp vụ có thể thay toàn bộ value object `Address`. Địa chỉ đó không nhất thiết phải được quản lý như một thực thể riêng.

Ngược lại, nếu doanh nghiệp quản lý danh sách địa chỉ đã xác minh, cho phép nhiều đơn hàng cùng tham chiếu đến một địa chỉ dùng chung, có trạng thái xác minh và lịch sử chỉnh sửa riêng, địa chỉ có thể cần trở thành entity hoặc aggregate độc lập.

**Quyết định value object hay entity xuất phát từ vòng đời và quy tắc nghiệp vụ**, không chỉ từ việc một nhóm trường có thể gom thành class Java.

## 2. Embedded object trong Spring Data JDBC

Spring Data JDBC dùng annotation `@Embedded` để khai báo một thuộc tính value object được lưu cùng hàng với đối tượng chứa nó.

Ví dụ đơn giản:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded(prefix = "shipping_")
    private Address shippingAddress;
}
~~~

Nếu `Address` có các thuộc tính `street`, `city` và `postalCode`, các giá trị được lưu trong bảng `purchase_orders` bằng những cột có tiền tố `shipping_`, chẳng hạn:

- `shipping_street`
- `shipping_city`
- `shipping_postal_code`

Không có bảng `addresses` riêng được tạo ra chỉ vì có class `Address`. Embedded object không có ID riêng, không phải aggregate root mới và không được lưu như một hàng độc lập.

~~~mermaid
flowchart TD
    A["PurchaseOrder<br/>aggregate root"] --> B["Address<br/>value object"]
    B --> C["street"]
    B --> D["city"]
    B --> E["postalCode"]
    A --> F["Một hàng purchase_orders"]
    C --> F
    D --> F
    E --> F
~~~

Các cột của `Address` được trải phẳng vào hàng `purchase_orders`. Khi đọc hàng đó, Spring Data JDBC ghép các giá trị cột lại để tạo đối tượng `Address` rồi gán vào `PurchaseOrder`.

### So sánh với collection hoặc entity con

Embedded object và entity con trong Spring Data JDBC có cấu trúc lưu trữ khác nhau:

| Mô hình Java | Cách lưu thường dùng | Quan hệ |
| --- | --- | --- |
| `@Embedded Address address` | Các cột của Address nằm trong bảng cha | Cùng hàng |
| `@MappedCollection List<OrderLine> lines` | Các hàng ở bảng con, có cột tham chiếu về aggregate root | Bảng riêng, thuộc aggregate |
| `Long customerId` hoặc `AggregateReference<Customer, Long>` | Cột FK/ID trong bảng đơn hàng | Tham chiếu aggregate khác |

Không nên dùng `@MappedCollection` cho địa chỉ chỉ có ý nghĩa trong một đơn hàng nếu địa chỉ không có vòng đời riêng. Ngược lại, không nên nhúng một danh sách dòng hàng có số lượng không giới hạn vào cùng hàng đơn hàng; collection entity con phù hợp hơn.

## 3. Thiết kế value object Address

Một value object địa chỉ có thể là Java record để thể hiện tính bất biến:

~~~java
import java.util.Objects;
import java.util.Locale;

import org.springframework.data.relational.core.mapping.Column;

public record Address(
    @Column("street") String street,
    @Column("city") String city,
    @Column("postal_code") String postalCode,
    @Column("country_code") String countryCode
) {
    public Address {
        street = requireText(street, "street");
        city = requireText(city, "city");
        countryCode = requireText(countryCode, "countryCode")
            .toUpperCase(Locale.ROOT);

        if (countryCode.length() != 2) {
            throw new IllegalArgumentException(
                "countryCode must contain two characters"
            );
        }

        // postalCode có thể tùy chọn theo quy tắc địa chỉ của quốc gia.
    }

    private static String requireText(String value, String field) {
        Objects.requireNonNull(value, field + " must not be null");
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value.trim();
    }
}
~~~

Record tự cung cấp constructor, accessor, `equals` và `hashCode` dựa trên các component. Vì vậy, hai địa chỉ có cùng giá trị component có thể được so sánh theo giá trị.

Việc kiểm tra trong compact constructor bảo vệ bất biến của object mỗi khi ứng dụng tạo một địa chỉ. Tuy nhiên, cần hiểu rằng khi dữ liệu được đọc từ database, constructor cũng được gọi trong quá trình materialization. Nếu schema có hàng cũ chứa giá trị không hợp lệ, việc đọc hàng có thể thất bại. Dữ liệu cũ cần được làm sạch hoặc quy tắc validation cần được thiết kế phù hợp với dữ liệu thực tế.

### Tại sao dùng value object thay cho bốn trường rời rạc?

Nếu aggregate root khai báo:

~~~java
private String shippingStreet;
private String shippingCity;
private String shippingPostalCode;
private String shippingCountryCode;
~~~

thì các trường cùng mô tả một khái niệm nhưng logic kiểm tra, chuẩn hóa và so sánh bị phân tán trong aggregate. Khi dùng `Address`, những quy tắc liên quan địa chỉ được gom vào một kiểu có ý nghĩa.

Điều này cũng giúp tránh truyền nhầm các chuỗi giữa những API. Phương thức nhận `Address` thể hiện rõ nó cần một địa chỉ hoàn chỉnh; phương thức nhận bốn chuỗi không diễn đạt được cùng mức ý nghĩa.

## 4. Nhúng Address bằng @Embedded

Aggregate root có thể khai báo địa chỉ giao hàng và địa chỉ thanh toán:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;

    @Embedded.Nullable(prefix = "billing_")
    private Address billingAddress;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Address shippingAddress, Address billingAddress) {
        this.shippingAddress = shippingAddress;
        this.billingAddress = billingAddress;
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public Address getBillingAddress() {
        return billingAddress;
    }
}
~~~

Ví dụ dùng `@Embedded.Nullable` vì địa chỉ có thể chưa được cung cấp. Prefix giúp phân biệt các cột của hai value object cùng kiểu:

| Property Java | Prefix | Cột SQL |
| --- | --- | --- |
| `shippingAddress.street` | `shipping_` | `shipping_street` |
| `shippingAddress.city` | `shipping_` | `shipping_city` |
| `shippingAddress.postalCode` | `shipping_` | `shipping_postal_code` |
| `shippingAddress.countryCode` | `shipping_` | `shipping_country_code` |
| `billingAddress.street` | `billing_` | `billing_street` |
| `billingAddress.city` | `billing_` | `billing_city` |
| `billingAddress.postalCode` | `billing_` | `billing_postal_code` |
| `billingAddress.countryCode` | `billing_` | `billing_country_code` |

Prefix là một phần của tên cột được mapping. Nếu không có prefix, hai thuộc tính embedded cùng kiểu có thể cùng muốn sử dụng những tên cột như `street` và `city`, gây xung đột.

### DDL minh họa

Với PostgreSQL, schema có thể được tạo như sau:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),

    billing_street VARCHAR(200),
    billing_city VARCHAR(120),
    billing_postal_code VARCHAR(30),
    billing_country_code CHAR(2)
);
~~~

Tất cả cột embedded nằm trong cùng hàng. Khi địa chỉ giao hàng thay đổi, thao tác lưu aggregate cập nhật các cột tương ứng của hàng đơn hàng.

Tên cột trong DDL phải khớp với metadata mapping. Nếu dự án dùng naming strategy hoặc quoting khác, cần kiểm tra tên SQL thực tế mà framework phát sinh.

## 5. @Embedded.Nullable và @Embedded.Empty

Một value object có thể tùy chọn. Khi không có địa chỉ, aggregate có thể giữ `shippingAddress = null`. Nhưng ở database, điều đó được biểu diễn bằng nhiều cột: tất cả cột của địa chỉ đều `NULL`.

Spring Data Relational cung cấp các biến thể của `@Embedded` để xác định cách xử lý tình huống này.

### 5.1. @Embedded.Nullable

~~~java
@Embedded.Nullable(prefix = "shipping_")
private Address shippingAddress;
~~~

Với `@Embedded.Nullable`, nếu tất cả các cột của embedded object đều `NULL`, thuộc tính embedded được tạo thành giá trị `null`. Nếu có ít nhất một cột có giá trị, framework sẽ dựng object từ các cột tương ứng.

Đây là lựa chọn tự nhiên cho địa chỉ tùy chọn: không có địa chỉ nghĩa là không có object `Address`.

Cần phân biệt:

- Tất cả cột `NULL`: object là `null`.
- Có một hoặc nhiều cột khác `NULL`: framework dựng embedded object; constructor/validation có thể từ chối tổ hợp dữ liệu thiếu thành phần bắt buộc.

Ví dụ nếu `shipping_street` có giá trị nhưng `shipping_city` và `shipping_country_code` là `NULL`, constructor `Address` phía trên sẽ không chấp nhận dữ liệu. Đây là điều có chủ đích nếu nghiệp vụ yêu cầu địa chỉ phải đủ trường.

### 5.2. @Embedded.Empty

~~~java
@Embedded.Empty(prefix = "shipping_")
private Address shippingAddress;
~~~

`@Embedded.Empty` chọn cách xử lý khác: khi toàn bộ cột của embedded object đều `NULL`, Spring Data vẫn tạo một instance embedded thay vì đặt thuộc tính thành `null`. Cách này phù hợp với mô hình muốn biểu diễn “đối tượng giá trị rỗng” theo quy ước của ứng dụng.

Tuy nhiên, không phải value object nào cũng có trạng thái rỗng hợp lệ. Với `Address` có constructor bắt buộc street/city/country, việc tạo object từ toàn bộ giá trị `NULL` có thể vi phạm bất biến. Chỉ dùng `@Embedded.Empty` khi kiểu embedded có thể biểu diễn trạng thái đó một cách có ý nghĩa, chẳng hạn một cấu trúc tùy chọn được thiết kế cho phép các trường rỗng.

### 5.3. So sánh lựa chọn

| Annotation | Khi toàn bộ cột embedded là `NULL` | Ý nghĩa |
| --- | --- | --- |
| `@Embedded` | Theo chính sách `onEmpty` của annotation, mặc định là `USE_NULL` | Embedded object theo cấu hình mặc định |
| `@Embedded.Nullable` | Property nhận `null` | Không có value object |
| `@Embedded.Empty` | Tạo instance embedded | Có object rỗng theo mô hình cho phép |

Đừng dùng `@Embedded.Empty` chỉ để tránh `null` trong Java. Nếu domain không định nghĩa được một địa chỉ rỗng hợp lệ, việc ép tạo object sẽ che giấu dữ liệu không đầy đủ.

### 5.4. Ràng buộc database cho địa chỉ tùy chọn

Với địa chỉ tùy chọn, nên bảo đảm dữ liệu ở database có hai trạng thái rõ ràng: không có địa chỉ (mọi cột null) hoặc có địa chỉ với các trường bắt buộc.

Ví dụ PostgreSQL:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT ck_shipping_address_complete
CHECK (
    (
        shipping_street IS NULL
        AND shipping_city IS NULL
        AND shipping_postal_code IS NULL
        AND shipping_country_code IS NULL
    )
    OR
    (
        shipping_street IS NOT NULL
        AND shipping_city IS NOT NULL
        AND shipping_country_code IS NOT NULL
    )
);
~~~

`postal_code` được phép null vì một số quốc gia/khu vực không sử dụng mã bưu chính hoặc nghiệp vụ cho phép thiếu. Các trường bắt buộc phải được quyết định theo yêu cầu thật của ứng dụng.

Constraint giúp chặn dữ liệu một phần được ghi bởi SQL trực tiếp hoặc ứng dụng khác. Validation trong constructor và constraint database bảo vệ hai lớp khác nhau.

## 6. Mô hình hóa Money bằng value object

Số tiền là một ví dụ đặc biệt quan trọng của value object. Không nên chỉ lưu một `double` hoặc `BigDecimal` mà không lưu loại tiền tệ, bởi `100 USD` và `100 VND` không có cùng ý nghĩa.

Một value object `Money` tối thiểu gồm:

- `amount`: giá trị chính xác, thường dùng `BigDecimal`.
- `currency`: mã tiền tệ, ví dụ `USD`, `VND`, `EUR`.

~~~java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;
import java.util.Locale;

import org.springframework.data.relational.core.mapping.Column;

public record Money(
    @Column("amount") BigDecimal amount,
    @Column("currency") String currency
) {
    public Money {
        Objects.requireNonNull(amount, "amount must not be null");
        Objects.requireNonNull(currency, "currency must not be null");

        currency = Currency.getInstance(
            currency.trim().toUpperCase(Locale.ROOT)
        ).getCurrencyCode();
    }

    public Money plus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money minus(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other must not be null");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot combine different currencies"
            );
        }
    }
}
~~~

Ví dụ:

~~~java
Money subtotal = new Money(new BigDecimal("120.00"), "USD");
Money shipping = new Money(new BigDecimal("8.50"), "USD");

Money total = subtotal.plus(shipping);
// total = 128.50 USD
~~~

Nếu cộng `120 USD` với `8.500 VND`, phương thức `plus` từ chối vì hai loại tiền khác nhau. Việc quy đổi tiền tệ cần tỷ giá, thời điểm áp dụng, nguồn tỷ giá và quy tắc làm tròn; không thể thực hiện bằng cách cộng hai số `BigDecimal`.

### Vì sao không dùng float hoặc double?

Kiểu dấu phẩy động nhị phân có thể biểu diễn một số thập phân như `0.1` bằng giá trị xấp xỉ. Đối với tiền, điều này dễ dẫn tới sai số tích lũy hoặc kết quả không đúng mong đợi.

Dùng `BigDecimal` với chuỗi thập phân:

~~~java
new BigDecimal("19.95");
~~~

Tránh:

~~~java
new BigDecimal(19.95);
~~~

Vế sau khởi tạo từ giá trị floating point đã xấp xỉ, nên không giữ đúng ý định thập phân ban đầu.

### Quy tắc scale và rounding

Không có một quy tắc làm tròn duy nhất áp dụng cho mọi loại tiền và mọi nghiệp vụ. Một số đồng tiền có 0 chữ số thập phân theo quy ước thông dụng, một số có 2 hoặc 3; hệ thống kế toán, thuế, giá sản phẩm và thanh toán cũng có thể quy định scale khác nhau.

Vì vậy:

- Không tự động gọi `setScale(2) cho mọi `Money`.
- Xác định scale theo loại tiền và quy tắc nghiệp vụ.
- Chọn `RoundingMode` tường minh ở ranh giới tính toán cần làm tròn.
- Giữ độ chính xác cần thiết trong quá trình tính toán trung gian.
- Quyết định lưu số tiền theo scale thống nhất hoặc theo từng currency trong schema.

## 7. Nhúng Money vào aggregate

Một đơn hàng có thể có tổng tiền bắt buộc và khoản giảm giá tùy chọn:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded(prefix = "total_")
    private Money total;

    @Embedded.Nullable(prefix = "discount_")
    private Money discount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Money total, Money discount) {
        this.total = total;
        this.discount = discount;
    }

    public Money getTotal() {
        return total;
    }

    public Money getDiscount() {
        return discount;
    }
}
~~~

Mapping:

| Property | Prefix | Các cột |
| --- | --- | --- |
| `total` | `total_` | `total_amount`, `total_currency` |
| `discount` | `discount_` | `discount_amount`, `discount_currency` |

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    total_amount NUMERIC(19, 4) NOT NULL,
    total_currency CHAR(3) NOT NULL,

    discount_amount NUMERIC(19, 4),
    discount_currency CHAR(3),

    CONSTRAINT ck_discount_pair
        CHECK (
            (discount_amount IS NULL AND discount_currency IS NULL)
            OR
            (discount_amount IS NOT NULL AND discount_currency IS NOT NULL)
        )
);
~~~

Trong ví dụ này:

- `total` bắt buộc, nên hai cột total đều `NOT NULL`.
- `discount` tùy chọn, nên cả hai cột discount cùng null hoặc cùng có giá trị.
- `NUMERIC(19,4)` là lựa chọn minh họa; precision/scale thực tế cần dựa vào giới hạn số tiền và quy tắc tiền tệ của hệ thống.
- `CHAR(3)` lưu mã tiền tệ ba ký tự; ứng dụng có thể chuẩn hóa mã bằng `Currency`.

Nếu cần giới hạn currency theo danh sách được chấp nhận, có thể dùng `CHECK` hoặc bảng mã tiền tệ tham chiếu tùy mô hình. Không nên giả định `Currency.getInstance` và database constraint có cùng danh sách hoặc cùng quy tắc nghiệp vụ ở mọi thời điểm.

### Hai Money trong cùng một bảng cần prefix

Nếu cả `total` và `discount` đều nhúng `Money` mà không có prefix, chúng cùng muốn dùng các cột `amount` và `currency`. Prefix phân biệt rõ giá trị thuộc về vai trò nào trong aggregate.

Điều này cũng áp dụng nếu một đối tượng có `originalPrice` và `salePrice`, hoặc `subtotal` và `tax`. Tên cột nên thể hiện ngữ cảnh nghiệp vụ thay vì chỉ lặp lại tên field bên trong value object.

## 8. Kết hợp Address và Money trong một aggregate

Một ví dụ đơn hàng đầy đủ hơn:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @Embedded.Nullable(prefix = "shipping_")
    private Address shippingAddress;

    @Embedded(prefix = "total_")
    private Money total;

    @Embedded.Nullable(prefix = "discount_")
    private Money discount;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            Address shippingAddress,
            Money total,
            Money discount) {
        this.shippingAddress = shippingAddress;
        this.total = total;
        this.discount = discount;
    }
}
~~~

Bảng quan hệ lưu các cột phẳng:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    shipping_street VARCHAR(200),
    shipping_city VARCHAR(120),
    shipping_postal_code VARCHAR(30),
    shipping_country_code CHAR(2),

    total_amount NUMERIC(19, 4) NOT NULL,
    total_currency CHAR(3) NOT NULL,

    discount_amount NUMERIC(19, 4),
    discount_currency CHAR(3),

    CONSTRAINT ck_shipping_address_complete
        CHECK (
            (
                shipping_street IS NULL
                AND shipping_city IS NULL
                AND shipping_postal_code IS NULL
                AND shipping_country_code IS NULL
            )
            OR
            (
                shipping_street IS NOT NULL
                AND shipping_city IS NOT NULL
                AND shipping_country_code IS NOT NULL
            )
        ),

    CONSTRAINT ck_discount_pair
        CHECK (
            (discount_amount IS NULL AND discount_currency IS NULL)
            OR
            (discount_amount IS NOT NULL AND discount_currency IS NOT NULL)
        )
);
~~~

Cấu trúc Java thể hiện khái niệm miền nghiệp vụ; schema quan hệ thể hiện cách lưu trữ. Khi đọc một đơn hàng, Spring Data JDBC tạo `Address` từ nhóm cột `shipping_*`, tạo `Money` từ nhóm `total_*` và tạo hoặc không tạo `Money` cho `discount_*` tùy trạng thái cột.

Không có bảng địa chỉ hoặc bảng tiền riêng trong ví dụ. Nếu một value object cần được chia sẻ, tra cứu, có lịch sử hoặc vòng đời độc lập, hãy đánh giá lại việc nhúng nó.

## 9. Validation ở value object và constraint ở database

Một value object nên bảo vệ các bất biến của chính nó. Ví dụ `Money` yêu cầu amount và currency hợp lệ; `Address` yêu cầu các trường bắt buộc không rỗng.

Nhưng chỉ validation trong Java là chưa đủ, vì database còn có thể được cập nhật bởi:

- SQL script hoặc công cụ quản trị.
- Một service khác.
- Batch job hoặc import dữ liệu.
- Phiên bản ứng dụng cũ.
- Giao dịch đồng thời.

Do đó, hãy dùng constraint SQL để bảo vệ những quy tắc dữ liệu có thể diễn đạt tại database.

| Quy tắc | Validation trong Java | Constraint SQL có thể dùng |
| --- | --- | --- |
| Address có street/city/country | Constructor kiểm tra null/blank | `NOT NULL` theo trường hoặc `CHECK` cho nhóm cột |
| Country code đúng định dạng | Chuẩn hóa/kiểm tra mã | `CHECK` theo format hoặc FK tới bảng mã |
| Money có amount và currency | Constructor kiểm tra không null | `NOT NULL` cho cặp cột |
| Hai cột tiền tùy chọn cùng có hoặc cùng null | Value object nullable | `CHECK` cho cặp amount/currency |
| Amount trong giới hạn nghiệp vụ | Kiểm tra miền giá trị | `CHECK` nếu quy tắc có thể diễn đạt ổn định |
| Currency được hỗ trợ | Danh sách/registry nghiệp vụ | `CHECK` hoặc FK tới bảng currency |

### Constraint cho địa chỉ

Nếu địa chỉ bắt buộc có street và country nhưng postal code là tùy chọn, dùng `CHECK` để cho phép hai trạng thái: toàn bộ nhóm null hoặc các trường bắt buộc có giá trị. Không nên đặt tất cả cột `NOT NULL` nếu toàn bộ Address có thể vắng mặt.

### Constraint cho Money

Với Money bắt buộc, cặp amount/currency nên cùng `NOT NULL`. Với Money tùy chọn, constraint phải đảm bảo cả hai cùng có hoặc cùng không. Nếu chỉ có `discount_amount` mà thiếu `discount_currency`, dữ liệu không còn đủ để diễn giải số tiền.

### Validation không nên làm thay nhiệm vụ của schema

Nếu constructor `Money` từ chối amount âm nhưng schema cho phép ghi amount âm từ SQL trực tiếp, dữ liệu sai vẫn có thể tồn tại và gây lỗi ở lần đọc sau. Nếu nghiệp vụ cấm số tiền âm, cân nhắc `CHECK(amount >= 0)`. Nếu hệ thống kế toán cho phép khoản điều chỉnh âm, đừng thêm constraint cấm âm một cách máy móc; hãy xác định đúng ngữ nghĩa của từng loại Money.

## 10. Cập nhật value object trong Spring Data JDBC

Vì value object thường bất biến, cập nhật địa chỉ có nghĩa là tạo giá trị mới và gán vào aggregate:

~~~java
Address newAddress = new Address(
    "12 Nguyen Hue",
    "Ho Chi Minh City",
    "700000",
    "VN"
);

order.changeShippingAddress(newAddress);
~~~

Một phương thức nghiệp vụ trên aggregate root có thể diễn đạt thay đổi:

~~~java
public void changeShippingAddress(Address newAddress) {
    this.shippingAddress = java.util.Objects.requireNonNull(newAddress);
}
~~~

Với immutable aggregate, có thể thay vào đó trả về một instance mới:

~~~java
public PurchaseOrder withShippingAddress(Address newAddress) {
    return new PurchaseOrder(newAddress, total, discount);
}
~~~

Khi lưu aggregate bằng Spring Data JDBC, các cột embedded được ghi như một phần dữ liệu của hàng aggregate root. Không có repository riêng cho `Address` hoặc `Money` chỉ vì chúng là class Java.

Cần phân biệt việc thay value object với việc cập nhật một entity con trong collection. Embedded object thuộc hàng của root; entity con trong `@MappedCollection` có bảng và vòng đời lưu trữ riêng trong aggregate.

## 11. Khi nào nên dùng bảng riêng thay cho embedded?

Embedded object không phải lựa chọn đúng trong mọi tình huống.

| Dấu hiệu nghiệp vụ | Mô hình thường phù hợp |
| --- | --- |
| Địa chỉ chỉ có ý nghĩa trong một đơn hàng | Embedded `Address` |
| Địa chỉ có ID, được dùng chung và quản lý độc lập | Entity/aggregate `Address` riêng |
| Số tiền chỉ mô tả tổng giá trị của đơn hàng | Embedded `Money` |
| Giao dịch thanh toán có mã giao dịch, trạng thái, thời gian và vòng đời riêng | Entity `Payment` hoặc aggregate thanh toán |
| Value object có số lượng thành phần cố định | Embedded |
| Một đối tượng có số lượng phần tử thay đổi không giới hạn | Collection/child table hoặc bảng riêng |
| Cần truy vấn, cập nhật hoặc phân quyền độc lập theo đối tượng con | Cân nhắc entity/bảng riêng |

Một value object có thể được dùng ở nhiều aggregate mà vẫn không cần chia sẻ một hàng dữ liệu. Ví dụ hai đơn hàng cùng có địa chỉ giao hàng giống nhau về giá trị nhưng mỗi đơn lưu một snapshot riêng. Khi khách hàng đổi địa chỉ trong hồ sơ, lịch sử đơn hàng vẫn giữ địa chỉ tại thời điểm đặt hàng.

Nếu thay vào đó hai đơn hàng tham chiếu cùng một bản ghi địa chỉ dùng chung, thay đổi bản ghi có thể ảnh hưởng cả hai. Đó là semantics khác hẳn và cần entity/aggregate độc lập.

## 12. Embedded object không phải JSON column

Một cách khác để lưu nhóm giá trị là mã hóa toàn bộ object vào một cột JSON hoặc text. Đây không phải hành vi mặc định của `@Embedded`.

| Embedded mapping | JSON/custom conversion |
| --- | --- |
| Mỗi property trở thành một cột SQL | Toàn object có thể thành một cột |
| Có thể dùng `NOT NULL`, `CHECK`, index trên từng cột | Constraint/query phụ thuộc khả năng JSON của database |
| Tên cột có prefix rõ ràng | Cấu trúc field nằm trong JSON |
| Phù hợp dữ liệu có cấu trúc ổn định | Có thể phù hợp dữ liệu linh hoạt hoặc schema thay đổi |
| Mapping bằng `@Embedded` | Thường cần converter hoặc kiểu dữ liệu JSON hỗ trợ |

Ví dụ nếu muốn lưu `Address` vào một cột JSON, phải thiết kế conversion và schema tương ứng. Không thể chỉ thêm `@Embedded` rồi mong framework tự gom tất cả field thành JSON.

Với địa chỉ hoặc tiền có các trường quan trọng cho lọc, kiểm tra, constraint và báo cáo, embedded columns thường dễ quản lý hơn. JSON phù hợp khi cần lưu một cấu trúc linh hoạt và chấp nhận trade-off truy vấn/constraint.

## 13. Migration khi thay đổi value object

Schema của embedded object là một phần của bảng aggregate root. Thêm một trường vào value object có thể đồng nghĩa thêm cột vào nhiều bảng đang nhúng nó.

Ví dụ thêm `district` vào `Address`:

~~~java
public record Address(
    @Column("street") String street,
    @Column("district") String district,
    @Column("city") String city,
    @Column("postal_code") String postalCode,
    @Column("country_code") String countryCode
) {}
~~~

Nếu `Address` được nhúng trong bảng `purchase_orders` với prefix `shipping_`, schema cần thêm `shipping_district`. Nếu cũng được nhúng trong bảng khác với prefix khác, các bảng đó cũng cần migration tương ứng.

Một quy trình triển khai an toàn:

1. Xác định tất cả aggregate/table đang nhúng value object.
2. Tạo migration thêm cột mới với khả năng tương thích dữ liệu hiện tại (ví dụ nullable hoặc default hợp lý).
3. Cập nhật mapping Java và logic đọc/ghi.
4. Backfill dữ liệu cũ nếu nghiệp vụ yêu cầu.
5. Thêm constraint bắt buộc sau khi dữ liệu đã đáp ứng.
6. Triển khai theo chiến lược tương thích nếu nhiều phiên bản ứng dụng cùng chạy.

Không chỉ đổi record component rồi kỳ vọng Spring Data JDBC tự sửa schema. Mapping mô tả cách đọc/ghi; migration thay đổi cấu trúc database.

## 14. Kiểm tra lỗi mapping embedded

Một số lỗi phổ biến:

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Không tìm thấy cột embedded | Prefix hoặc tên cột không khớp DDL | `@Embedded(prefix)`, `@Column` và migration |
| Hai value object cùng kiểu ghi đè tên cột | Thiếu prefix riêng cho từng thuộc tính | Dùng `shipping_`, `billing_`, `total_`… |
| Đọc ra object null dù mong muốn object rỗng | Toàn bộ cột embedded đều null và dùng chính sách USE_NULL | Xác định semantics rồi chọn Nullable/Empty |
| Constructor value object ném lỗi | Hàng có một phần cột null hoặc dữ liệu cũ không hợp lệ | Kiểm tra dữ liệu, constraint và invariant |
| Lưu Money thiếu currency | Schema chỉ có amount hoặc mapping sai prefix | Bảo vệ cặp cột bằng NOT NULL/CHECK |
| Dùng sai kiểu số tiền | Dùng float/double hoặc scale không phù hợp | Dùng BigDecimal và quy tắc rounding rõ ràng |
| Mong có bảng Address nhưng không thấy | @Embedded lưu các cột vào bảng cha | Kiểm tra mô hình có cần entity riêng không |
| Đổi field embedded nhưng ứng dụng lỗi | Cột mới chưa được migration | Kiểm tra schema và thứ tự deploy |

### Kiểm tra schema PostgreSQL

Có thể liệt kê các cột của bảng đơn hàng:

~~~sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'purchase_orders'
ORDER BY ordinal_position;
~~~

Kết quả giúp xác nhận các cột `shipping_*`, `total_*` và `discount_*` đã tồn tại, đúng kiểu và nullable như mong đợi.

Để tìm địa chỉ đang ở trạng thái một phần:

~~~sql
SELECT id
FROM purchase_orders
WHERE
    (
        shipping_street IS NULL
        OR shipping_city IS NULL
        OR shipping_country_code IS NULL
    )
    AND
    (
        shipping_street IS NOT NULL
        OR shipping_city IS NOT NULL
        OR shipping_country_code IS NOT NULL
    );
~~~

Truy vấn này chỉ là ví dụ kiểm tra theo tập trường bắt buộc đã chọn. Quy tắc cụ thể cần điều chỉnh theo schema và yêu cầu địa chỉ của ứng dụng.

## 15. Quy ước thiết kế nên áp dụng

Khi tạo value object cho Spring Data JDBC, nên thống nhất những nguyên tắc sau:

- **Dùng kiểu có ý nghĩa nghiệp vụ:** `Address`, `Money` thay vì một nhóm chuỗi hoặc số rời rạc.
- **Ưu tiên bất biến:** record hoặc class có final fields, constructor kiểm tra bất biến.
- **Không thêm ID giả:** value object không cần ID nếu nghiệp vụ không quản lý identity.
- **Dùng `@Embedded`:** khi các thành phần được lưu trong cùng hàng với aggregate root.
- **Dùng prefix rõ ràng:** khi có nhiều embedded object hoặc nhiều object cùng kiểu.
- **Chọn null semantics có chủ đích:** `@Embedded.Nullable` khi không có object được biểu diễn bằng null; `@Embedded.Empty` khi object rỗng có ý nghĩa hợp lệ.
- **Giữ constraint ở database:** đặc biệt với nhóm cột phải cùng có hoặc cùng null.
- **Dùng `BigDecimal` cho tiền:** luôn gắn amount với currency và quy tắc rounding.
- **Quản lý schema bằng migration:** thay đổi value object cần đánh giá tất cả bảng đang nhúng nó.
- **Chọn entity riêng khi có vòng đời độc lập:** không nhúng chỉ vì muốn giảm số bảng.

Bảng lựa chọn nhanh:

| Nhu cầu | Lựa chọn |
| --- | --- |
| Địa chỉ tùy chọn của một đơn hàng | `@Embedded.Nullable(prefix = "shipping_")` |
| Value object bắt buộc, các cột bắt buộc có giá trị | `@Embedded(prefix = "total_")` và constraint SQL |
| Muốn tạo instance khi mọi cột đều null | `@Embedded.Empty` nếu object rỗng hợp lệ |
| Cùng kiểu Address ở shipping và billing | Hai prefix khác nhau |
| Tổng tiền có amount và currency | `Money` với `BigDecimal` và mã tiền tệ |
| Giá trị có ID/lịch sử/truy vấn độc lập | Entity hoặc aggregate riêng |
| Dữ liệu linh hoạt lưu một cột JSON | Converter/JSON mapping, không phải embedded mặc định |

## 16. Bài tập tự thực hành

### Bài 1 — Address tùy chọn

Tạo record `Address` gồm street, city, postalCode, countryCode. Nhúng vào `PurchaseOrder` bằng `@Embedded.Nullable(prefix = "shipping_")`. Tạo schema PostgreSQL có các cột tương ứng và constraint cho phép hoặc không có toàn bộ địa chỉ, hoặc có đủ các trường bắt buộc.

### Bài 2 — Hai địa chỉ cùng kiểu

Thêm `billingAddress` cùng kiểu `Address`. Dùng prefix `billing_`. Liệt kê tên cột cho hai thuộc tính và giải thích vì sao không thể dùng cùng một prefix.

### Bài 3 — Phân biệt Nullable và Empty

Tạo một embedded type có thể biểu diễn trạng thái rỗng hợp lệ. So sánh kết quả materialization khi toàn bộ cột là null với `@Embedded.Nullable` và `@Embedded.Empty`. Nêu trường hợp không nên dùng Empty.

### Bài 4 — Money

Tạo record `Money(BigDecimal amount, String currency)`. Viết phương thức cộng hai Money nhưng từ chối nếu currency khác nhau. Nhúng `total` và `discount` vào cùng aggregate với hai prefix. Tạo constraint để amount/currency của discount cùng null hoặc cùng có giá trị.

### Bài 5 — Giá trị tiền và làm tròn

Thử `new BigDecimal("0.1")` và `new BigDecimal(0.1)`. Quan sát biểu diễn và giải thích tại sao tiền nên dùng BigDecimal. Thiết kế một quy tắc làm tròn có currency và nghiệp vụ cụ thể, thay vì mặc định hai chữ số cho mọi trường hợp.

### Bài 6 — Khi nào Address trở thành entity?

Giả sử địa chỉ được xác minh, dùng chung bởi nhiều khách hàng, có trạng thái và lịch sử chỉnh sửa. Phân tích vòng đời và quyết định giữ value object snapshot hay tạo aggregate Address riêng. Giải thích tác động đến schema và quan hệ giữa các aggregate.

## 17. Tài liệu tham khảo chính thức

- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/object-mapping.html): cơ chế ánh xạ object, embedded entities, prefix và xử lý embedded object rỗng.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): cách Spring Data JDBC ánh xạ aggregate và các loại thuộc tính.
- [Spring Data Relational — @Embedded API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Embedded.html): annotation embedded, prefix và chính sách khi embedded không có dữ liệu.
- [Spring Data Relational — @Column API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/mapping/Column.html): chỉ định tên cột vật lý cho property.
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác, scale và rounding.
- [Java Currency API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Currency.html): biểu diễn mã tiền tệ và thông tin currency.

Value object giúp mô hình Java thể hiện đúng ngôn ngữ nghiệp vụ: địa chỉ là một địa chỉ, số tiền là một số tiền có loại tiền tệ. Với Spring Data JDBC, `@Embedded` cho phép giữ cấu trúc object đó trong mã nguồn nhưng lưu các giá trị thành các cột của aggregate root. Khi chọn prefix, null semantics, validation và constraint nhất quán, mô hình vừa rõ ràng ở Java vừa bảo vệ được dữ liệu quan hệ.
