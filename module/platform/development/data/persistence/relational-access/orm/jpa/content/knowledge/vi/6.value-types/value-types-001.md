# Thiết kế đối tượng giá trị có ý nghĩa nghiệp vụ

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Kiểu giá trị

Trong hệ thống dùng JPA, một thuộc tính không nhất thiết chỉ là `String`, `BigDecimal` hay `LocalDate`. Những dữ liệu như **số tiền kèm đơn vị tiền tệ**, **mã sản phẩm**, **địa chỉ giao hàng** hoặc **khoảng ngày có hiệu lực** thường mang quy tắc nghiệp vụ riêng. Nếu chỉ lưu chúng dưới dạng các field rời rạc, code có thể cho phép trạng thái vô nghĩa: cộng USD với VND, lưu số tiền không đúng độ chính xác, ghép mã sản phẩm không hợp lệ hoặc tạo khoảng ngày có điểm kết thúc trước điểm bắt đầu.

**Value Object (đối tượng giá trị)** giúp đưa ý nghĩa và quy tắc đó vào một kiểu dữ liệu. Giá trị được nhận diện bởi **nội dung có ý nghĩa nghiệp vụ**, thay vì một ID riêng. Trong JPA, đối tượng giá trị thường được ánh xạ qua `@Embeddable`/`@Embedded`, `AttributeConverter` hoặc `@ElementCollection`, nhưng quyết định thiết kế domain phải đi trước quyết định annotation.

Bài này hướng dẫn từ cách nhận diện một value object, xây dựng các bất biến (*invariants*), xác định equality và tính bất biến, đến ánh xạ JPA và cập nhật dữ liệu an toàn.

## 1. Kết quả cần đạt

Sau bài học, bạn nên có thể:

- Phân biệt **Entity** và **Value Object** qua identity, vòng đời và cách so sánh.
- Nhận biết khi nào cần tạo một kiểu `Money`, `ProductCode`, `Address` hay `DateRange` thay vì truyền các primitive rời rạc.
- Thiết kế constructor/factory chỉ cho phép giá trị hợp lệ; đặt hành vi nghiệp vụ bên trong kiểu dữ liệu.
- Áp dụng tư duy **immutable value**: thay thế đối tượng khi giá trị đổi, giữ `equals()`/`hashCode()` ổn định.
- Ánh xạ một value object có nhiều thuộc tính bằng `@Embeddable` và `@Embedded`; tái sử dụng cùng kiểu bằng `@AttributeOverrides`.
- Ánh xạ một value object vào **một cột** với `AttributeConverter`; hiểu khác biệt với embedded object.
- Dùng `@ElementCollection` khi entity sở hữu một tập giá trị và hiểu hệ quả về lifecycle, SQL và hiệu năng.
- Giữ ràng buộc nghiệp vụ nhất quán giữa Java, JPA mapping, database constraint và các đường nhập dữ liệu.

## 2. Value Object khác Entity ở đâu?

Xét hai đối tượng:

- **Đơn hàng #1024:** dù khách thay địa chỉ nhận hàng, đó vẫn là cùng đơn hàng. Đơn hàng có identity và lịch sử riêng.
- **Địa chỉ giao hàng:** “12 Nguyễn Huệ, Quận 1, TP.HCM” mô tả một giá trị. Nếu hai đơn hàng có cùng địa chỉ này, hai bản địa chỉ có thể có **giá trị bằng nhau** mà không nhất thiết phải chia sẻ một bản ghi địa chỉ độc lập.

| Tiêu chí | Entity | Value Object |
|---|---|---|
| Câu hỏi nhận diện | “Có phải **cùng thực thể**?” | “Có mang **cùng giá trị**?” |
| Identity | Thường có ID riêng và tồn tại xuyên qua thay đổi | Không cần identity độc lập để so sánh |
| Equality | Thường dựa trên entity identity theo chính sách domain | Thường dựa trên các thành phần tạo nên giá trị |
| Thay đổi | Có thể đổi thuộc tính trong khi vẫn là cùng entity | Thường tạo giá trị mới để thay thế |
| Vòng đời | Có thể được tìm, cập nhật, xóa độc lập | Thường thuộc về một entity hoặc aggregate |
| Ví dụ | `Order`, `Customer`, `Invoice` | `Money`, `ProductCode`, `Address`, `DateRange` |
| JPA thông dụng | `@Entity`, `@Id` | `@Embeddable`, `@Embedded` hoặc `@Convert` |

**Điểm phân biệt quan trọng:** có nhiều bản ghi chứa cùng một địa chỉ không làm địa chỉ tự trở thành entity. Ngược lại, nếu hệ thống quản lý “địa điểm nhận hàng” với trạng thái hoạt động, phân quyền, lịch sử, mã định danh và quan hệ dùng chung, **địa điểm** có thể là một entity. Cùng tên gọi “Address” có thể dẫn đến hai mô hình khác nhau tùy nghiệp vụ.

### 2.1. Identity, equality và vòng đời

```text
Entity: Order#1024
   |
   +-- shippingAddress = Address("12 Nguyen Hue", "HCM", "VN")
   |
   +-- total = Money(120.00, "USD")

Entity: Order#2048
   |
   +-- shippingAddress = Address("12 Nguyen Hue", "HCM", "VN")
   |
   +-- total = Money(120.00, "USD")

Hai Order khác nhau vì ID khác nhau.
Hai Address có thể bằng nhau về nội dung.
Hai Money có thể bằng nhau nếu cả amount và currency đều bằng nhau.
```

Không nên dùng toàn bộ dữ liệu hiện tại để định nghĩa identity của `Order`: thay đổi địa chỉ không được làm đơn hàng “biến thành” entity khác. Nhưng với `Money`, thay đổi số tiền chính là tạo ra một giá trị khác.

### 2.2. Domain Value Object và JPA embeddable không hoàn toàn đồng nghĩa

**Value Object** là quyết định thiết kế mô hình nghiệp vụ. **`@Embeddable`** là một cơ chế ánh xạ của JPA. Nhiều value object phù hợp với embeddable, nhưng có loại được ánh xạ vào một cột bằng converter hoặc được dùng chỉ trong domain mà không cần lưu trực tiếp.

Ngược lại, đánh dấu một lớp `@Embeddable` **không tự động** khiến nó có bất biến nghiệp vụ, immutable, hoặc có implementation `equals()/hashCode()` đúng. Annotation chỉ nói cho JPA biết cách ánh xạ các thuộc tính của lớp vào dữ liệu lưu trữ.

## 3. Khi nào nên trích xuất một Value Object?

Một kiểu dữ liệu đáng cân nhắc khi xuất hiện một hoặc nhiều tín hiệu sau:

1. **Có tên và ý nghĩa nghiệp vụ riêng:** số tiền, mã SKU, số điện thoại, khoảng hiệu lực, địa chỉ.
2. **Có quy tắc hợp lệ:** amount không thể cộng khác currency, khoảng ngày phải có start trước end, mã hàng phải theo định dạng được chấp nhận.
3. **Các field luôn đi cùng nhau:** `amount` và `currencyCode` mà bị tách ra thì dễ sử dụng sai.
4. **Có hành vi dựa trên chính giá trị:** `Money.add`, `DateRange.contains`, `ProductCode.of`.
5. **Cần so sánh theo nội dung:** hai mã chuẩn hóa bằng nhau, hai khoản tiền cùng amount và currency.
6. **Nhiều use case lặp lại cùng quy tắc:** nếu mỗi service tự kiểm tra định dạng hay rounding, logic sẽ lệch nhau.
7. **Truyền tham số kiểu primitive dễ nhầm:** `createPayment("USD", 120)` có thể đảo vị trí hoặc thiếu kiểm tra; `createPayment(Money.of(...))` diễn đạt ý nghĩa hơn.

Không cần biến mọi `String` hay `int` thành một lớp riêng. Một kiểu value object đáng giá khi nó **đặt tên đúng cho khái niệm và chịu trách nhiệm thực thi quy tắc**, không đơn thuần đóng gói field để thêm boilerplate.

### 3.1. Câu hỏi trước khi viết class

Với mỗi ứng viên, ghi rõ:

- **Các thành phần:** giá trị gồm những thông tin nào? Ví dụ `Money` = số tiền + mã tiền tệ.
- **Invariant:** trạng thái nào bị cấm? Ví dụ amount không phải `null`; scale lưu trữ phù hợp.
- **Chuẩn hóa:** có loại bỏ khoảng trắng, chuẩn hóa chữ hoa hoặc scale không? Có mất thông tin không?
- **Equality:** hai giá trị nào được xem là cùng một giá trị?
- **Các phép toán:** cộng, so sánh, đổi đơn vị, kiểm tra bao gồm… có quy tắc gì?
- **Ownership:** đối tượng giá trị thuộc entity nào? Có cần được truy cập/cập nhật độc lập không?
- **Persistence shape:** lưu vào một cột, nhiều cột cùng bảng hay bảng collection riêng?
- **Lỗi:** đầu vào sai được báo ở đâu, bằng exception/validation nào và database kiểm tra lại ra sao?

Sau khi trả lời, mới quyết định mapping JPA cụ thể.

## 4. Nguyên tắc thiết kế: tạo giá trị hợp lệ và giữ nguyên ngữ nghĩa

### 4.1. Encapsulation thay cho các field tách rời

Thiết kế dễ sai:

```java
class Product {
    BigDecimal priceAmount;
    String priceCurrency;
}

BigDecimal total = product.priceAmount.add(discountAmount);
// Không ai kiểm tra currency của hai số tiền.
```

Cách tiếp cận value object:

```java
Money price = Money.of(new BigDecimal("125.00"), "USD");
Money fee = Money.of(new BigDecimal("5.00"), "USD");

Money total = price.add(fee); // Kết quả: 130.00 USD

// price.add(Money.of(new BigDecimal("5.00"), "VND"))
// => Bị từ chối vì khác loại tiền.
```

Một `Money` có thể từ chối phép cộng không hợp lệ ngay tại phương thức `add`. Quy tắc nằm tại **chính kiểu dữ liệu mang ý nghĩa**, thay vì đặt rải rác ở controller, service, mapper và repository.

### 4.2. Bất biến về nghiệp vụ

Một value object nên bảo vệ invariant ngay lúc tạo. Ví dụ một khoảng thời gian không thể có ngày bắt đầu sau ngày kết thúc:

```java
public final class DateRange {
    private final LocalDate startInclusive;
    private final LocalDate endExclusive;

    public DateRange(LocalDate startInclusive,
                     LocalDate endExclusive) {
        Objects.requireNonNull(startInclusive);
        Objects.requireNonNull(endExclusive);

        if (!startInclusive.isBefore(endExclusive)) {
            throw new IllegalArgumentException(
                    "Khoảng ngày phải có độ dài dương");
        }

        this.startInclusive = startInclusive;
        this.endExclusive = endExclusive;
    }

    public boolean contains(LocalDate day) {
        return !day.isBefore(startInclusive)
            && day.isBefore(endExclusive);
    }
}
```

Đây là ví dụ **domain class thuần Java**, chưa khai báo mapping JPA. Nó minh họa một quyết định phải nói rõ: khoảng trên **bao gồm đầu** và **không bao gồm cuối** (quy ước nửa mở). Nếu nghiệp vụ chọn hai đầu đều bao gồm, thay đổi điều kiện và tên field tương ứng.

### 4.3. Tư duy immutable: thay giá trị, không sửa tại chỗ

Thay vì:

```java
order.getShippingAddress().setCity("Da Nang");
```

hãy ưu tiên:

```java
order.changeShippingAddress(
    order.getShippingAddress().withCity("Da Nang")
);
```

Phương thức `withCity` trả về **một `Address` mới**, giữ nguyên các field còn lại. Cách này giúp object dùng trong `Set` hoặc làm key của `Map` không bị thay đổi hash vì sửa field sau khi thêm vào collection.

Với JPA, **immutable ở mức API/domain** không nhất thiết đồng nghĩa mọi field phải là `final`. Đặc tả/provider có những yêu cầu và cơ chế khởi tạo, hydrate object; lớp `@Embeddable` tương thích rộng thường cần constructor không tham số và các field có thể được provider gán. Ta có thể **không cung cấp setter công khai** và chỉ cho phép ứng dụng tạo instance hợp lệ qua factory, trong khi để provider hydrate dữ liệu bằng field access.

Đây là một thỏa hiệp giữa mô hình nghiệp vụ và cơ chế persistence: application code đối xử với object như giá trị bất biến; provider được phép khởi tạo nó để tái tạo dữ liệu đã lưu.

### 4.4. Equality theo tất cả thành phần tạo nên giá trị

Với `Money`, hai số tiền chỉ nên bằng nhau khi **amount và currency** đều tương đương theo quy tắc mà domain đã chọn:

```text
Money(100.00, USD) == Money(100.00, USD)  -> true
Money(100.00, USD) == Money(100.00, VND)  -> false
Money(100.00, USD) == Money(200.00, USD)  -> false
```

Nếu bỏ qua mã tiền tệ khi viết `equals()`, ứng dụng có thể coi hai giá trị hoàn toàn khác nhau là cùng một giá trị.

## 5. Ví dụ đầy đủ: Money là Value Object được nhúng bằng JPA

Ta xây `Money` có hai thành phần:

- `BigDecimal amount`: lượng tiền, tránh sai số nhị phân của `double` khi tính toán tiền.
- `String currencyCode`: mã tiền tệ, ví dụ `USD` hoặc `VND`.

Ví dụ này chọn **hai chữ số thập phân cố định** và chỉ chấp nhận giá trị biểu diễn chính xác ở scale đó. Đây là **quy tắc của ứng dụng mẫu**, không phải quy tắc chung cho mọi currency: VND thường dùng không có phần lẻ trong nhiều quy trình; có loại tiền cần ba chữ số thập phân và nhiều phép tính trung gian cần độ chính xác cao hơn.

### 5.1. Implementation `Money`

```java
package demo.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Embeddable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Money {

    private BigDecimal amount;
    private String currencyCode;

    protected Money() {
        // JPA tạo object trước, sau đó hydrate các field.
    }

    private Money(BigDecimal amount, String currencyCode) {
        this.amount = normalizeAmount(amount);
        this.currencyCode = normalizeCurrency(currencyCode);
    }

    public static Money of(BigDecimal amount, String currencyCode) {
        return new Money(amount, currencyCode);
    }

    public static Money of(String amount, String currencyCode) {
        return of(new BigDecimal(amount), currencyCode);
    }

    private static BigDecimal normalizeAmount(BigDecimal source) {
        Objects.requireNonNull(source, "amount");

        // Không tự làm tròn: yêu cầu caller đưa ra giá trị
        // biểu diễn chính xác với 2 chữ số thập phân.
        return source.setScale(2, RoundingMode.UNNECESSARY);
    }

    private static String normalizeCurrency(String source) {
        Objects.requireNonNull(source, "currencyCode");

        String code = source.trim().toUpperCase(Locale.ROOT);
        Currency.getInstance(code); // Từ chối mã tiền tệ không hợp lệ.
        return code;
    }

    public BigDecimal amount() {
        return amount;
    }

    public String currencyCode() {
        return currencyCode;
    }

    public Money add(Money other) {
        Objects.requireNonNull(other, "other");

        requireSameCurrency(other);
        return Money.of(amount.add(other.amount), currencyCode);
    }

    public Money subtract(Money other) {
        Objects.requireNonNull(other, "other");

        requireSameCurrency(other);
        return Money.of(amount.subtract(other.amount), currencyCode);
    }

    public boolean isNegative() {
        return amount.signum() < 0;
    }

    private void requireSameCurrency(Money other) {
        if (!currencyCode.equals(other.currencyCode)) {
            throw new IllegalArgumentException(
                "Cannot combine different currencies: "
                + currencyCode + " and " + other.currencyCode);
        }
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Money)) {
            return false;
        }

        Money that = (Money) other;
        return Objects.equals(amount, that.amount)
            && Objects.equals(currencyCode, that.currencyCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currencyCode);
    }

    @Override
    public String toString() {
        return amount + " " + currencyCode;
    }
}
```

Những quyết định cần hiểu:

1. `Money` không có `@Id` vì không cần identity độc lập. Hai instance có cùng amount/currency được xem là cùng một giá trị.
2. Factory `of` tập trung kiểm tra và chuẩn hóa đầu vào. Mã nghiệp vụ không được đặt tùy tiện `amount = null` hoặc `currencyCode = "???"`.
3. Dùng `BigDecimal(String)` để tạo giá trị chính xác theo chuỗi thập phân, tránh khởi tạo bằng `new BigDecimal(0.1)`.
4. `setScale(2, UNNECESSARY)` chuẩn hóa `1`, `1.0` và `1.00` về `1.00`, đồng thời từ chối dữ liệu cần làm tròn. Chính sách rounding khi thật sự cần làm tròn phải nằm ở phép toán/use case có quy định nghiệp vụ.
5. `add` và `subtract` giữ nguyên currency, từ chối cộng/trừ khác đơn vị. Quy đổi tiền tệ là một nghiệp vụ khác, đòi hỏi tỷ giá, thời điểm hiệu lực và quy tắc làm tròn.
6. Mẫu cho phép amount âm ở cấp `Money` để hỗ trợ hiệu số, điều chỉnh hoặc hoàn tiền. Nếu **giá bán** không được âm, invariant đó nằm ở `Product` hoặc một kiểu chuyên biệt `NonNegativeMoney`.
7. `Objects.equals`/`Objects.hash` diễn đạt equality trên các thành phần. Provider có thể tạo đối tượng bằng constructor không tham số và gán field sau đó; application code chỉ nên dùng các giá trị đã được khởi tạo hợp lệ.
8. Các thành phần `BigDecimal` và `String` tự chúng là immutable; mã nghiệp vụ không có setter thay đổi field sau khi `Money` được tạo.

**Giới hạn có chủ đích:** `Currency.getInstance` kiểm tra mã được Java nhận diện, nhưng không tự xác nhận đồng tiền đó được phép thanh toán trong thị trường của ứng dụng. Nếu domain chỉ chấp nhận một tập tiền tệ, hãy kiểm tra tập đó hoặc xây một quy tắc riêng.

### 5.2. Equality của BigDecimal: vì sao phải thống nhất scale?

`BigDecimal` có hai khái niệm so sánh cần phân biệt:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));          // false
```

`compareTo` so giá trị số học, còn `equals` cũng xét scale. Nếu một value object tính `equals` theo `compareTo` nhưng vẫn hash theo `BigDecimal.hashCode()`, **hai object bằng nhau có thể có mã băm khác nhau**, vi phạm hợp đồng `equals/hashCode`.

Mẫu `Money` ở trên **chuẩn hóa scale** khi tạo nên có thể dùng `BigDecimal.equals/hashCode` nhất quán cho các giá trị đã chuẩn hóa. Nếu hệ thống cần nhiều scale khác nhau, bạn phải xác định một dạng chuẩn khác và áp dụng nó cho cả equals lẫn hash.

Đặc biệt không dùng `double` làm cơ sở cho equality số tiền vì lỗi biểu diễn thập phân có thể lan sang điều kiện nghiệp vụ.

### 5.3. Không để validation “ẩn” trong persistence annotation

`@Embeddable` không tự kiểm tra tiền âm hay currency khác. `@Column(nullable=false)` chủ yếu cung cấp metadata mapping/DDL; ứng dụng vẫn cần factory/constructor bảo vệ invariant, database cần constraint, và các đường nhập dữ liệu khác cũng phải được kiểm soát.

Khi provider hydrate entity từ các hàng đã lưu, nó có thể gán trực tiếp field mà **không gọi factory `Money.of`**. Vì vậy dữ liệu lỗi từ SQL trực tiếp, migration sai hoặc dữ liệu lịch sử vẫn có thể vào object. Thiết kế production thường kết hợp:

- **Domain validation:** factory và phương thức thay giá trị.
- **Bean Validation:** ví dụ `@NotNull`, `@Valid`, custom validator nếu ứng dụng tích hợp Jakarta Validation.
- **Database constraint:** `NOT NULL`, `CHECK`, `UNIQUE` và kiểu cột thích hợp.
- **Migration và backfill:** xử lý dữ liệu cũ trước khi siết constraint mới.

Không một tầng riêng lẻ nào nên bị xem là thay thế toàn bộ các tầng còn lại.

## 6. Ánh xạ Money vào entity bằng @Embedded

Giả sử `Product` có giá bán `unitPrice`. Vì `Money` gồm hai thành phần, ta lưu nó trong **hai cột của bảng sản phẩm**:

```text
products
+----+----------+-------------------+---------------------+
| id | sku      | unit_price_amount | unit_price_currency |
+----+----------+-------------------+---------------------+
| 10 | PEN-001  |            12.50  | USD                 |
+----+----------+-------------------+---------------------+
```

Mapping:

```java
package demo.domain;

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
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 32)
    private String sku;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "unit_price_amount",
                nullable = false,
                precision = 19,
                scale = 2
            )
        ),
        @AttributeOverride(
            name = "currencyCode",
            column = @Column(
                name = "unit_price_currency",
                nullable = false,
                length = 3
            )
        )
    })
    private Money unitPrice;

    protected Product() {
        // JPA
    }

    public Product(String sku, Money unitPrice) {
        this.sku = Objects.requireNonNull(sku, "sku");
        changeUnitPrice(unitPrice);
    }

    public Long getId() {
        return id;
    }

    public Money getUnitPrice() {
        return unitPrice;
    }

    public void changeUnitPrice(Money replacement) {
        Objects.requireNonNull(replacement, "unitPrice");

        if (replacement.isNegative()) {
            throw new IllegalArgumentException(
                "Unit price cannot be negative");
        }
        this.unitPrice = replacement;
    }
}
```

Trong ví dụ, `Product` là **Entity** có ID, còn `Money` là **Value Object** nằm trong trạng thái của Product. Việc thay giá bán **không đổi identity của Product**.

`@AttributeOverride(name = "amount")` và `@AttributeOverride(name = "currencyCode")` chỉ rõ cột vật lý cho **field của Money**, không phải tên getter ở Product. `precision = 19, scale = 2` là thông tin mapping hữu ích nhưng cần kiểm tra DDL thực tế và khả năng của database; quy định giới hạn và chính sách số học của domain vẫn phải được viết rõ.

### 6.1. Sử dụng trong transaction

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Product product = em.find(Product.class, productId);

    if (product == null) {
        throw new IllegalArgumentException("Unknown product: " + productId);
    }

    product.changeUnitPrice(Money.of("19.90", "USD"));

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đoạn này giả định `em` là `EntityManager` của persistence unit `RESOURCE_LOCAL` và được tạo/đóng trong phạm vi bên ngoài. Entity `Product` được `find` trong transaction thường ở trạng thái managed; provider phát hiện thay đổi field embedded khi flush/commit.

Tư duy domain ở đây là **thay toàn bộ giá trị Money**, không gọi `product.getUnitPrice().setAmount(...)`. Cách này giữ invariant “amount đi cùng currency” và tránh đột biến object value được nhiều đoạn mã tham chiếu.

Trong ứng dụng Spring dùng `@Transactional`, transaction do Spring quản lý; không dùng lại `getTransaction()` của resource-local một cách máy móc.

## 7. Nhúng cùng một kiểu Value Object nhiều lần

Một đơn hàng có thể có **địa chỉ giao hàng** và **địa chỉ xuất hóa đơn**. Cả hai là `Address`, nhưng cần cột riêng. Đây là tình huống tự nhiên cho `@AttributeOverrides`.

### 7.1. Domain type Address

```java
package demo.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Embeddable;

import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Address {

    private String street;
    private String city;
    private String countryCode;

    protected Address() {
        // JPA
    }

    public Address(String street, String city, String countryCode) {
        this.street = requireText(street, "street");
        this.city = requireText(city, "city");
        this.countryCode = requireText(countryCode, "countryCode");
    }

    private static String requireText(String text, String fieldName) {
        Objects.requireNonNull(text, fieldName);
        String result = text.trim();
        if (result.isEmpty()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return result;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }

    public String getCountryCode() {
        return countryCode;
    }

    public Address withCity(String newCity) {
        return new Address(street, newCity, countryCode);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Address)) return false;
        Address that = (Address) other;
        return Objects.equals(street, that.street)
            && Objects.equals(city, that.city)
            && Objects.equals(countryCode, that.countryCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, countryCode);
    }
}
```

Ở đây, `Address` không có `id`, không có public setter và có phương thức `withCity` tạo bản mới. Equality dùng các thành phần có ý nghĩa nghiệp vụ mà mô hình đã chọn. Trong một hệ thống đa quốc gia, định dạng địa chỉ thường phức tạp hơn nhiều; mã quốc gia, mã bưu chính, khu vực hành chính và quy tắc chuẩn hóa cần được thiết kế theo phạm vi hỗ trợ của sản phẩm. Không nên tự động xóa dấu, đổi toàn bộ sang chữ hoa hoặc ghép chuỗi hiển thị để làm khóa định danh địa chỉ.

### 7.2. Hai @Embedded trong cùng entity

```java
package demo.domain;

import jakarta.persistence.*;

import java.util.Objects;

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
            column = @Column(name = "ship_street", nullable = false)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "ship_city", nullable = false)
        ),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(
                name = "ship_country_code", nullable = false, length = 3)
        )
    })
    private Address shippingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "bill_street", nullable = false)
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "bill_city", nullable = false)
        ),
        @AttributeOverride(
            name = "countryCode",
            column = @Column(
                name = "bill_country_code", nullable = false, length = 3)
        )
    })
    private Address billingAddress;

    protected PurchaseOrder() {
        // JPA
    }

    public PurchaseOrder(Address shipping, Address billing) {
        this.shippingAddress =
            Objects.requireNonNull(shipping, "shipping");
        this.billingAddress =
            Objects.requireNonNull(billing, "billing");
    }

    public Address getShippingAddress() {
        return shippingAddress;
    }

    public void changeShippingAddress(Address replacement) {
        this.shippingAddress =
            Objects.requireNonNull(replacement, "replacement");
    }
}
```

Về mặt dữ liệu, một hàng của `purchase_orders` có thể gồm:

```text
id | ship_street | ship_city | ship_country_code |
   | bill_street | bill_city | bill_country_code
```

Không có bảng `addresses` riêng chỉ vì dùng class `Address`. Mỗi lần nhúng, các thuộc tính của value được ánh xạ vào cột của bảng entity sở hữu nó. Nếu không override khi nhúng nhiều instance, tên cột mặc định có thể trùng nhau hoặc phụ thuộc naming strategy của provider.

### 7.3. Quyết định null cho một value object nhiều cột

Một `@Embedded Address` có thể được xem là `null` khi không có dữ liệu, nhưng biểu diễn thực tế phụ thuộc mapping/provider và các giá trị cột. Với một `Address` gồm ba cột, các trạng thái có thể phát sinh:

```text
street = null, city = null, country = null
street = "12 ...", city = null, country = "VN"
street = "12 ...", city = "HCM", country = "VN"
```

Domain phải quyết định địa chỉ **bắt buộc**, **tùy chọn**, hay cho phép **một phần**. Nếu một địa chỉ bắt buộc phải đầy đủ, có thể dùng `NOT NULL` ở các cột, validation của entity và constructor domain; nếu địa chỉ tùy chọn, có thể cho phép toàn bộ nhóm cột null và áp dụng thêm ràng buộc “hoặc tất cả null, hoặc tất cả có dữ liệu” tại database khi phù hợp.

Đừng giả định `@Embedded` tự áp đặt quy tắc “tất cả field hoặc không field nào”.

## 8. Value Object một cột: AttributeConverter

Không phải value object nào cũng cần nhiều cột. Một **mã sản phẩm** có thể là một chuỗi, nhưng có ý nghĩa nghiệp vụ và quy tắc riêng:

- Không được bỏ trống.
- Chỉ chấp nhận một tập ký tự quy định.
- Quy ước mã không phân biệt chữ thường/chữ hoa.
- Được chuẩn hóa ngay lúc tạo.
- Hai mã đã chuẩn hóa giống nhau thì bằng nhau.

Trong trường hợp này, mô hình domain có thể là một class Java độc lập, còn database chỉ lưu một cột `VARCHAR`. `AttributeConverter` là một lựa chọn phù hợp.

### 8.1. Domain type ProductCode

```java
package demo.domain;

import java.util.Locale;
import java.util.Objects;

public final class ProductCode {

    private final String value;

    private ProductCode(String normalized) {
        this.value = normalized;
    }

    public static ProductCode of(String raw) {
        Objects.requireNonNull(raw, "productCode");

        String code = raw.trim().toUpperCase(Locale.ROOT);
        if (!code.matches("[A-Z0-9][A-Z0-9._-]{1,31}")) {
            throw new IllegalArgumentException(
                "Product code must be 2..32 valid characters");
        }
        return new ProductCode(code);
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ProductCode)) return false;
        ProductCode that = (ProductCode) other;
        return value.equals(that.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }
}
```

Class này **không cần `@Embeddable` hoặc constructor JPA**: khi được ánh xạ qua converter, JPA xem nó như một thuộc tính được chuyển đổi tới một cột. Nó là một value object immutable thuần Java.

Quy tắc regex ở trên là ví dụ của **domain mẫu**, không phải chuẩn mã sản phẩm phổ quát. Hãy thay bằng quy tắc của hệ thống thật.

### 8.2. Converter

```java
package demo.persistence;

import demo.domain.ProductCode;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class ProductCodeConverter
        implements AttributeConverter<ProductCode, String> {

    @Override
    public String convertToDatabaseColumn(ProductCode attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public ProductCode convertToEntityAttribute(String dbData) {
        return dbData == null ? null : ProductCode.of(dbData);
    }
}
```

Hai hướng chuyển đổi:

```text
Java domain:
ProductCode.of(" pen-001 ")  -> ProductCode("PEN-001")
                                 |
                                 | convertToDatabaseColumn
                                 v
Database:
VARCHAR sku = "PEN-001"
                                 |
                                 | convertToEntityAttribute
                                 v
Java domain:
ProductCode("PEN-001")
```

Gắn converter lên field:

```java
@Convert(converter = ProductCodeConverter.class)
@Column(name = "sku", nullable = false, unique = true, length = 32)
private ProductCode sku;
```

Nếu muốn đưa converter này vào class `Product` ở phần 6, thay field `String sku` bằng `ProductCode sku` và thay constructor tương ứng thành `Product(ProductCode sku, Money unitPrice)`. Đây là phiên bản cải tiến, không phải một entity khác.

- `autoApply = false`: converter chỉ được áp dụng tại vị trí khai báo `@Convert`.
- Nếu bật `autoApply = true`, nó có thể tự áp dụng cho các thuộc tính cùng kiểu trong persistence unit theo quy tắc JPA; cần tránh ảnh hưởng ngoài ý muốn.
- `@Column(unique = true)` là metadata; quy tắc duy nhất phải tồn tại trong schema thực tế, đặc biệt khi môi trường dùng migration thay vì tự sinh DDL.
- Chuẩn hóa ở Java chỉ áp dụng khi giá trị đi qua factory/converter. Nếu có luồng SQL ghi trực tiếp, cần kiểm soát chuẩn hóa và uniqueness ở tầng database/nhập dữ liệu.

### 8.3. Chọn @Convert hay @Embedded?

| Câu hỏi | `AttributeConverter` | `@Embeddable` + `@Embedded` |
|---|---|---|
| Dữ liệu lưu vật lý | Thường một giá trị JDBC/cột đích | Nhiều thuộc tính/cột của bảng owner, hoặc mapping phức tạp hơn |
| Ví dụ | `ProductCode` → `VARCHAR` | `Money` → amount + currency |
| Truy vấn theo thành phần | Phụ thuộc cách converter mã hóa; DB chỉ thấy một cột | JPQL có thể đi theo thuộc tính con, như `p.price.amount` |
| Mapping độc lập với chi tiết bên trong | Converter kiểm soát serialization sang cột | JPA nhìn các field persistent của embeddable |
| Khi phù hợp | Một giá trị đơn có invariant/domain logic | Một nhóm giá trị có cấu trúc và thành phần cần truy vấn |

Một value object có thể có hai field Java nhưng được serialization thành một JSON/text column thông qua converter; ngược lại, một VO gồm một field vẫn có thể được `@Embeddable`. Quyết định phụ thuộc yêu cầu truy vấn, indexing, constraint, portability và mô hình schema. Tránh cố gắn `@Convert` và `@Embedded` lên **cùng một thuộc tính** như hai cách ánh xạ đồng thời.

## 9. Tập hợp Value Object bằng @ElementCollection

Đôi khi một entity sở hữu **nhiều giá trị**, mỗi giá trị không có lifecycle độc lập. Ví dụ một bài viết có nhiều nhãn nội dung (*tag*). Nếu nhãn không được quản lý như một entity trong domain, có thể dùng `Set<Tag>` và `@ElementCollection`.

### 9.1. Tag là Value Object

```java
package demo.domain;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.util.Locale;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class Tag {

    @Column(name = "tag_value", nullable = false, length = 40)
    private String value;

    protected Tag() {
        // JPA
    }

    public Tag(String input) {
        Objects.requireNonNull(input, "tag");

        String normalized =
            input.trim().toLowerCase(Locale.ROOT);

        if (normalized.isEmpty() || normalized.length() > 40) {
            throw new IllegalArgumentException("Invalid tag");
        }
        this.value = normalized;
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Tag)) return false;
        Tag that = (Tag) other;
        return Objects.equals(value, that.value);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(value);
    }
}
```

Vì `Tag` không cung cấp setter và `value` không thay đổi sau khi tạo, nó phù hợp làm phần tử của `HashSet`. Nếu cho phép sửa `value` tại chỗ khi phần tử đang ở trong Set, mã băm sẽ thay đổi và có thể làm `contains`/`remove` không còn tìm được phần tử.

### 9.2. Entity sở hữu collection

```java
package demo.domain;

import jakarta.persistence.*;

import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

@Entity
@Table(name = "articles")
public class Article {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(
        name = "article_tags",
        joinColumns = @JoinColumn(name = "article_id")
    )
    private Set<Tag> tags = new HashSet<>();

    protected Article() {
        // JPA
    }

    public void addTag(Tag tag) {
        tags.add(Objects.requireNonNull(tag));
    }

    public void removeTag(Tag tag) {
        tags.remove(tag);
    }

    public Set<Tag> getTags() {
        return java.util.Collections.unmodifiableSet(tags);
    }
}
```

Cấu trúc lưu trữ có thể là:

```text
articles
  id (PK)

article_tags
  article_id (FK -> articles.id)
  tag_value
```

Không có entity `Tag` độc lập, không có `@Id` cho mỗi phần tử collection. `article_tags` là bảng lưu giá trị thuộc `Article`. Nếu domain cần quản lý tag dùng chung với thông tin người tạo, trạng thái duyệt, số lượt sử dụng hoặc quan hệ riêng, **Tag có thể cần thành entity**, và mapping sẽ đổi thành association giữa các entity.

`@ElementCollection` mặc định tải lazy theo đặc tả JPA, nhưng hành vi SQL thực tế vẫn phụ thuộc provider và cách truy cập. Không mặc nhiên có một lệnh SQL cho mọi thay đổi collection: một số provider có thể xóa/ghi lại nhiều hàng khi thay đổi tập giá trị, tùy mapping và khả năng định danh hàng. Quan sát SQL trước khi áp dụng collection lớn hoặc cập nhật thường xuyên.

### 9.3. Set trong JPA cần equals/hashCode ổn định

Với value object, equality theo **nội dung bất biến** là tự nhiên:

```java
Set<Tag> tags = new HashSet<>();

tags.add(new Tag("Java"));
tags.add(new Tag(" java "));

System.out.println(tags.size()); // 1
```

Hai `Tag` có cùng giá trị chuẩn hóa nên trùng trong Set. Nhưng Set chỉ áp dụng trong bộ nhớ Java. Khi tính nhất quán dữ liệu quan trọng, schema database cũng nên có unique constraint phù hợp cho cặp `(article_id, tag_value)`; điều đó cần được cấu hình/quản lý trong migration.

Cần phân biệt `@ElementCollection` và `@OneToMany`:

| Đặc điểm | `@ElementCollection` | `@OneToMany` |
|---|---|---|
| Phần tử | Basic type hoặc embeddable/value | Entity có identity riêng |
| Lifecycle | Thuộc về owner entity | Phụ thuộc mapping, cascade và quan hệ ownership |
| ID từng phần tử | Không có entity ID độc lập | Entity thường có `@Id` |
| Truy cập độc lập qua EntityManager | Không `find(Tag.class, id)` | Có thể `find(ChildEntity.class, id)` |
| Ví dụ | Tập tag, nhóm giá trị, danh sách mã | Order–OrderLine, Customer–AddressEntity nếu địa chỉ có identity |

Không dùng `@ElementCollection` chỉ vì “khỏi tạo entity” khi phần tử thực sự có lifecycle riêng hoặc lượng dữ liệu khiến cập nhật collection trở thành điểm nghẽn.

## 10. Truy vấn với Value Object trong JPA

Với `@Embedded`, JPQL thường dùng **tên thuộc tính Java** của object graph, không dùng trực tiếp tên cột trong database.

Ví dụ tìm sản phẩm có giá từ `10.00 USD` trở lên:

```java
List<Product> products = em.createQuery(
        "select p from Product p " +
        "where p.unitPrice.currencyCode = :currency " +
        "and p.unitPrice.amount >= :minimum",
        Product.class)
    .setParameter("currency", "USD")
    .setParameter("minimum", new BigDecimal("10.00"))
    .getResultList();
```

`p.unitPrice.currencyCode` đi qua field embedded `unitPrice` đến field `currencyCode` của `Money`; provider ánh xạ xuống `unit_price_currency`. Điều kiện currency **không nên bị bỏ qua** khi so sánh amount vì `100.00 USD` và `100.00 VND` không thể so sánh trực tiếp về sức mua.

Với `@Convert`, truy vấn theo thuộc tính value object:

```java
ProductCode code = ProductCode.of("PEN-001");

List<Product> products = em.createQuery(
        "select p from Product p where p.sku = :sku",
        Product.class)
    .setParameter("sku", code)
    .getResultList();
```

Đoạn này giả định `Product.sku` đã được chuyển sang kiểu `ProductCode` và cấu hình `@Convert` như phần 8. Khi truy vấn JPQL qua thuộc tính được convert, provider áp dụng converter theo mapping. Với native SQL, câu SQL thao tác trực tiếp cột vật lý nên không nên mặc định provider sẽ chuyển mọi tham số native thành value object theo cùng cơ chế.

### 10.1. Value Object không loại bỏ nhu cầu thiết kế index

`@Embedded` vẫn là cột thật trong bảng owner. Nếu truy vấn thường lọc theo `unit_price_currency` và `unit_price_amount`, database có thể cần index phù hợp. Nếu lọc nhiều theo `sku`, cần unique index hoặc index có hỗ trợ truy vấn tương ứng.

Không để abstract domain khiến ta quên cấu trúc dữ liệu thực tế. Domain có thể nói “giá” là một Money bất biến, nhưng optimizer vẫn nhìn các cột số và chuỗi.

## 11. Value Object và tính nhất quán khi cập nhật

### 11.1. Thay cả value thay vì sửa từng thành phần

Giả sử yêu cầu thay giá bán từ 100 USD thành 120 EUR. Nếu code thay từng field:

```java
price.setAmount(new BigDecimal("120.00"));
price.setCurrencyCode("EUR");
```

giữa hai lần gán có trạng thái trung gian **120 USD**, có thể bị quan sát hoặc dùng sai bởi logic khác. Với immutable value, người gọi cung cấp giá trị hoàn chỉnh:

```java
product.changeUnitPrice(Money.of("120.00", "EUR"));
```

Product kiểm tra invariant của price, provider sau đó đồng bộ các cột tương ứng khi transaction hoàn tất. Nếu chuyển từ USD sang EUR là một quy trình quy đổi, **phải dùng tỷ giá theo thời điểm/chính sách nghiệp vụ**; không chỉ thay code tiền tệ trên cùng amount.

### 11.2. Chọn đúng nơi đặt invariant

| Invariant | Vị trí phù hợp |
|---|---|
| Tiền phải có amount và currency hợp lệ | `Money.of` |
| Hai Money muốn cộng phải cùng currency | `Money.add` |
| Giá bán Product không được âm | `Product.changeUnitPrice` hoặc kiểu giá bán chuyên biệt |
| SKU đúng quy tắc định dạng | `ProductCode.of` |
| Mỗi SKU chỉ thuộc một Product | Unique constraint database + xử lý conflict nghiệp vụ |
| Địa chỉ phải có street/city/country | `Address` factory/constructor và constraint |
| Đơn hàng đã giao không được sửa địa chỉ | Hành vi của `Order`/aggregate và quy tắc trạng thái |
| Không có hai transaction cùng ghi đè ngoài ý muốn | Transaction/locking/version ở entity và database |

**Value object nên bảo vệ những điều luôn đúng cho chính giá trị đó.** Quy tắc liên quan trạng thái của entity, quyền thao tác hoặc nhiều aggregate thường thuộc entity/service/domain policy tương ứng.

### 11.3. Dữ liệu lịch sử và bản chụp giá trị

Trong thương mại điện tử, địa chỉ giao hàng trong **đơn hàng đã đặt** thường là một bản chụp của địa chỉ tại thời điểm đặt. Nếu khách hàng sửa địa chỉ mặc định, đơn hàng cũ thường **không nên thay đổi lịch sử**. Đây là ví dụ mạnh cho việc lưu một `Address` value object trong `Order` thay vì buộc mọi order cùng tham chiếu một Address entity dùng chung.

Tương tự, đơn giá tại thời điểm mua có thể là `Money` lưu trong `OrderLine`, dù giá hiện tại của sản phẩm thay đổi. Domain phải quyết định cái gì là **giá trị tại thời điểm sự kiện** và cái gì là **quan hệ đến entity có dữ liệu đang thay đổi**.

## 12. Giá trị ngày giờ, đơn vị đo và mã định danh

Tư duy Value Object không chỉ áp dụng cho Money.

### 12.1. DateRange / ValidityPeriod

Một `ValidityPeriod` gồm `startInclusive` và `endExclusive`, chỉ hợp lệ khi start trước end. Các thao tác có thể gồm `contains(date)`, `overlaps(other)` và `intersect(other)`, với quy ước biên được viết rõ.

Khi ánh xạ JPA bằng `@Embeddable`, hai thuộc tính `LocalDate` tương ứng hai cột `DATE`. **`LocalDate` không chứa timezone**; nó thích hợp cho một ngày lịch chứ không đại diện chính xác một thời điểm trên dòng thời gian. Với thời điểm tuyệt đối, cân nhắc `Instant` và chính sách timezone/UTC thống nhất.

### 12.2. Quantity có đơn vị

```text
Quantity(5, "kg")
Quantity(5000, "g")
```

Hai giá trị này có thể tương đương sau khi quy đổi, nhưng equality và cách lưu phải theo quy tắc đã thiết kế. Nếu hệ thống dùng nhiều đơn vị, cần quy tắc chuyển đổi, độ chính xác và kiểu đơn vị; không nên cộng số `5` với `5000` mà không biết đơn vị.

Nếu chọn một đơn vị chuẩn duy nhất (ví dụ gram) làm representation nội bộ, factory có thể chuyển đổi đầu vào về đơn vị đó. Equality/hash dựa trên representation chuẩn sẽ đơn giản và nhất quán hơn.

### 12.3. EmailAddress / PhoneNumber / CustomerCode

Các kiểu này có thể giúp tránh truyền nhầm tham số `String`. Tuy nhiên, chuẩn hóa cần thận trọng:

- Email local-part có các quy tắc phức tạp; không tự động giả định mọi địa chỉ email có thể lowercase toàn bộ mà không ảnh hưởng ngữ nghĩa.
- Số điện thoại liên quan mã quốc gia, cách nhập và định dạng hiển thị. Một định dạng canonical như E.164 có thể phù hợp nếu phạm vi sản phẩm cho phép và có công cụ validation tin cậy.
- Mã khách hàng có thể là business key bất biến hoặc chỉ là mã hiển thị có thể thay đổi; hai trường hợp không nên dùng cùng chính sách equality.

Nhãn “Value Object” không thay thế cho việc viết **bộ quy tắc nghiệp vụ cụ thể** của từng kiểu.

## 13. Các bẫy thiết kế thường gặp

### 13.1. Value Object chỉ có getter/setter, không có quy tắc

```java
class Money {
    BigDecimal amount;
    String currency;
}
```

Đoạn này chỉ nhóm field, chưa bảo vệ invariant và chưa cho phép các phép toán có ý nghĩa. Nó có thể là một DTO thích hợp trong một số ngữ cảnh, nhưng chưa thể hiện sức mạnh của value object trong domain.

### 13.2. Dùng @Entity cho mọi nhóm dữ liệu

Nếu `Money` là entity có ID riêng, việc lưu giá có thể đòi hỏi bảng money, khóa ngoại, lifecycle riêng và nhiều join không cần thiết. Value Object có thể được nhúng trực tiếp vào owner. **Chỉ dùng entity khi đối tượng thực sự có identity và vòng đời cần quản lý.**

### 13.3. Nhầm immutable với final class/field bắt buộc

Trong Java thuần, `final` field giúp biểu đạt bất biến. Nhưng với `@Embeddable` JPA truyền thống, constructor không tham số và field access của provider là yêu cầu thực tế. Không áp đặt `final` lên class hoặc persistent fields chỉ vì muốn immutable nếu provider không hỗ trợ kiểu đó. Một số phiên bản/provider hỗ trợ constructor mapping, record hoặc chiến lược immutable nâng cao; cần kiểm tra khả năng thực tế của stack đang dùng. Mẫu an toàn phổ biến là lớp không có public mutator, constructor nghiệp vụ tạo giá trị hợp lệ và JPA hydrate qua field access.

### 13.4. Đưa collection hoặc entity liên quan vào equals/hashCode

Value Object nên so sánh các **thành phần thật sự xác định giá trị**. Nếu đưa một association mutable/lazy hoặc graph object vào `equals()`, có thể xảy ra recursion, truy vấn ngoài ý muốn, hoặc kết quả equality thay đổi theo dữ liệu không thuộc giá trị.

Ví dụ với `Address`, so sánh street/city/country. Không cần đi truy cập `Customer.orders` để so sánh hai địa chỉ.

### 13.5. Sửa field của Value Object sau khi thêm vào Set

```java
Set<Address> addresses = new HashSet<>();
Address address = new Address("12 A", "HCM", "VN");
addresses.add(address);

// Nếu address có setter làm đổi city, hash có thể đổi
// và Set.contains/address removal có thể thất bại.
```

Cách thiết kế trong bài chỉ cho phép `address.withCity(...)` trả về object mới. Khi cần thay giá trị trong Set, hãy **remove giá trị cũ, add giá trị mới** với đối tượng có equality/hash ổn định. Với `@ElementCollection Set<Tag>`, quy tắc này đặc biệt quan trọng.

### 13.6. Nhầm business key với identity lâu dài của entity

`ProductCode` có thể là một value object, nhưng `Product` vẫn có entity identity riêng. Nếu nghiệp vụ cho phép đổi SKU, hãy quyết định đó là thuộc tính thay đổi của cùng Product hay là hành động tạo Product mới. Không tự động viết `Product.equals()` dựa trên SKU nếu chính SKU có thể đổi.

### 13.7. Gộp các loại tiền mà không bảo toàn currency

Một cột amount đơn lẻ không đủ cho dữ liệu tiền đa đơn vị. Nếu API nhận `Money` nhưng schema chỉ lưu amount rồi tự mặc định USD, dữ liệu VND có thể bị diễn giải sai. Thiết kế persistence phải giữ đầy đủ ý nghĩa của value object, trừ khi có quy ước hệ thống bắt buộc một currency và được kiểm chứng rõ.

### 13.8. Để logic normalize phụ thuộc Locale mặc định

Ví dụ mã SKU cần uppercase theo quy tắc ký tự Latin/A-Z, hãy dùng `Locale.ROOT` hoặc chuẩn hóa đã xác định. Việc dùng `toUpperCase()` phụ thuộc locale máy chạy có thể tạo kết quả khác nhau trong một số ngôn ngữ. Với nội dung ngôn ngữ tự nhiên hoặc địa chỉ, không nên chuẩn hóa máy móc nếu làm mất thông tin.

### 13.9. Nghĩ @Embeddable tự sinh bảng riêng

`@Embedded` thông thường ánh xạ field của value object vào cột bảng owner. Muốn lưu collection value trong bảng phụ, dùng `@ElementCollection` cùng `@CollectionTable`. Muốn đối tượng có identity và bảng riêng để tìm độc lập, cân nhắc một `@Entity`.

### 13.10. Chỉ dựa vào @Column/Bean Validation để bảo toàn domain

`@Column(nullable=false)` không diễn đạt “end phải sau start” hoặc “hai loại tiền phải giống nhau khi cộng”. Bean Validation có thể kiểm tra một số ràng buộc trước khi ghi nhưng không tự bao hết mọi đường ghi dữ liệu. Domain factory/hành vi, application transaction, schema constraint và migration cần phối hợp.

## 14. Kiểm thử Value Object theo hành vi nghiệp vụ

Với value object, các test quan trọng nhất thường **không cần khởi động JPA**. Ta có thể kiểm tra invariant, equality và phép toán bằng unit test Java thuần; sau đó bổ sung integration test để xác nhận mapping.

### 14.1. Unit test Money

Ví dụ cú pháp JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class MoneyTest {

    @Test
    void addsAmountsOfSameCurrency() {
        Money a = Money.of("10.00", "USD");
        Money b = Money.of("2.50", "USD");

        assertEquals(Money.of("12.50", "USD"), a.add(b));
        assertEquals(Money.of("10.00", "USD"), a);
    }

    @Test
    void refusesToAddDifferentCurrencies() {
        Money usd = Money.of("10.00", "USD");
        Money vnd = Money.of("10.00", "VND");

        assertThrows(
            IllegalArgumentException.class,
            () -> usd.add(vnd)
        );
    }

    @Test
    void normalizedScaleProducesConsistentEquality() {
        Money first = Money.of(new BigDecimal("1"), "USD");
        Money second = Money.of(new BigDecimal("1.00"), "usd");

        assertEquals(first, second);
        assertEquals(first.hashCode(), second.hashCode());
    }

    @Test
    void rejectsImplicitRounding() {
        assertThrows(
            ArithmeticException.class,
            () -> Money.of("1.234", "USD")
        );
    }
}
```

Các bài kiểm tra này diễn đạt **hành vi của domain type**: cộng đúng đơn vị, không tự làm tròn và chuẩn hóa scale/currency nhất quán. Chúng không phụ thuộc vào việc dùng Hibernate, EclipseLink hay Spring Data JPA.

### 14.2. Integration test cho persistence

Với cơ sở dữ liệu kiểm thử có schema tương thích:

1. Tạo `Product` với `Money.of("15.50", "USD")`.
2. Persist và commit.
3. Tạo `EntityManager` mới, load lại Product theo ID.
4. Kiểm tra `product.getUnitPrice()` bằng giá trị ban đầu.
5. Thay `unitPrice` bằng `Money.of("20.00", "USD")` trong transaction.
6. Commit, mở context mới và xác nhận cả amount/currency được lưu đúng.
7. Thử dữ liệu vi phạm `NOT NULL`/`UNIQUE` qua đường persistence thích hợp để kiểm tra database constraint.
8. Truy vấn JPQL theo `p.unitPrice.currencyCode` và `p.unitPrice.amount`, kiểm tra kết quả.

Với `ProductCodeConverter`, bổ sung thí nghiệm:

- Persist `ProductCode.of(" pen-001 ")`; kiểm tra DB lưu `PEN-001`.
- Load lại qua JPA; nhận object `ProductCode` chứ không phải chuỗi thô.
- Tìm kiếm theo tham số kiểu `ProductCode`.
- Kiểm tra cách ứng dụng xử lý dữ liệu database cũ vi phạm quy tắc factory.

Với `Set<Tag>`, kiểm tra thêm tag trùng, xóa tag, tải lại collection và uniqueness ở DB nếu nghiệp vụ yêu cầu. Đây là **kịch bản kiểm thử được đề xuất** cho bài học; nội dung minh họa không khẳng định đã chạy trong một dự án cụ thể.

## 15. Bài tập thiết kế: hệ thống đặt hàng

Hãy thực hiện một mini project với các yêu cầu:

- `Product` có `ProductCode` bất biến theo quy tắc ứng dụng và `Money unitPrice`.
- `Order` có `Address shippingAddress`, `Money total`, trạng thái đơn hàng và ID riêng.
- `OrderLine` lưu giá chốt tại thời điểm đặt, số lượng và tổng dòng.
- `Article` hoặc `Product` có tập nhãn `Set<Tag>`.
- Đơn hàng đã giao không được thay địa chỉ; thay địa chỉ trước lúc giao bằng **một Address mới**.
- Không được cộng tiền khác currency; đổi ngoại tệ phải qua dịch vụ tỷ giá riêng.
- Mỗi ProductCode chỉ được dùng cho một Product trong DB.

Thực hành từng bước:

1. Liệt kê **entity** và **value object** rồi giải thích vì sao có hoặc không có identity riêng.
2. Viết constructor/factory cho từng value object; đặt tên rõ những bất biến và đầu vào bị từ chối.
3. Viết `equals()/hashCode()` theo đúng các thành phần giá trị; xử lý chuẩn hóa để so sánh nhất quán.
4. Chọn `@Embedded` cho cấu trúc nhiều cột, `@Convert` cho mã một cột và `@ElementCollection` cho tập giá trị.
5. Xác định ràng buộc database và migration trước khi lưu dữ liệu thật.
6. Xây use case đổi giá, thay địa chỉ và thêm/xóa tag bằng thao tác thay giá trị.
7. Quan sát SQL khi cập nhật `@ElementCollection`; xem số câu lệnh và số hàng bị ảnh hưởng.
8. Viết unit test cho domain behavior, integration test cho mapping và constraint.

### 15.1. Sơ đồ phân chia trách nhiệm

```text
Application / Service
    |
    | tạo unit of work, tổ chức transaction, gọi domain
    v
Entity: Order
    |  id, status, lines
    |
    +-- Address shippingAddress (Value Object)
    |     street, city, countryCode
    |
    +-- Money total (Value Object)
    |     amount, currencyCode
    |
    +-- OrderLine (Entity hoặc cấu trúc sở hữu
          vòng đời, tùy yêu cầu domain)
          |
          +-- Money agreedPrice (Value Object)

JPA provider:
    @Entity -> bảng và identity
    @Embedded -> nhiều cột trong bảng owner
    @Convert -> một cột qua converter
    @ElementCollection -> collection value do owner sở hữu

Database:
    PK / FK / UNIQUE / CHECK / NOT NULL / INDEX
```

Trong sơ đồ, `OrderLine` có thể là entity thuộc aggregate Order, hoặc một mô hình khác theo yêu cầu identity/vòng đời. Không tự động coi mọi phần tử trong collection của Order là value object.

## 16. Tóm tắt tiêu chí lựa chọn

| Nếu dữ liệu… | Hướng thiết kế |
|---|---|
| Có identity, lifecycle và lịch sử độc lập | Mô hình `@Entity` |
| Được nhận diện bằng nội dung, có invariant riêng | Tạo Value Object |
| Có một giá trị lưu trữ và quy tắc domain | Value Object + `AttributeConverter` |
| Có nhiều thành phần cần lưu/truy vấn riêng | Value Object + `@Embeddable`/`@Embedded` |
| Cùng một kiểu được nhúng hai lần trong một owner | Dùng `@AttributeOverrides` để đặt tên cột rõ ràng |
| Là tập giá trị thuộc vòng đời entity sở hữu | Xem xét `@ElementCollection` |
| Cần so sánh theo nội dung trong Set/Map | Thiết kế equality/hash theo giá trị **ổn định** |
| Quy tắc hợp lệ liên quan nhiều entity hoặc trạng thái nghiệp vụ | Đặt tại entity, aggregate hoặc domain service phù hợp |
| Dữ liệu có thể được ghi bởi nhiều hệ thống/transaction | Bổ sung database constraints, migration và chiến lược đồng thời |

**Nguyên tắc mang theo:** *Một value object tốt mang ý nghĩa nghiệp vụ, chỉ biểu diễn trạng thái hợp lệ và cung cấp hành vi dựa trên chính giá trị đó*. Khi tích hợp JPA, hãy chọn cách ánh xạ bảo toàn đầy đủ ngữ nghĩa này; JPA là cơ chế lưu trữ, còn quy tắc “điều gì tạo thành một giá trị hợp lệ” vẫn thuộc mô hình nghiệp vụ.

