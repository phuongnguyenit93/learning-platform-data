# Chọn kết hợp đối tượng thay vì kế thừa khi quan hệ nghiệp vụ không phù hợp

## 1. Bài toán thiết kế: dùng kế thừa vì có vài thuộc tính giống nhau?

Trong Hibernate ORM, một hệ phân cấp entity có thể ánh xạ xuống database bằng `@Inheritance`, `@MappedSuperclass` hoặc các cơ chế riêng của provider. Khả năng đó không có nghĩa **mọi quan hệ giữa hai khái niệm nghiệp vụ đều nên dùng `extends`**.

Ví dụ một hệ thống bán hàng có khách hàng, người bán và nhân viên kiểm duyệt. Cả ba đều có email, tên hiển thị và mật khẩu đăng nhập. Một thiết kế dễ nghĩ tới là:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Account { /* id, email, passwordHash */ }

@Entity
public class Customer extends Account { /* ... */ }

@Entity
public class Seller extends Account { /* ... */ }

@Entity
public class Moderator extends Account { /* ... */ }
```

Nhưng nếu cùng một tài khoản vừa mua hàng, vừa bán hàng, và sau đó được cấp quyền kiểm duyệt, hệ phân cấp trên đặt ra câu hỏi khó: **một object có thể “đổi lớp” từ `Customer` sang `Seller` khi dữ liệu nghiệp vụ thay đổi không?** Trong mô hình JPA thông thường, kiểu entity được quyết định bởi mapping/class/discriminator; cập nhật một field không biến instance `Customer` thành instance `Seller` hay làm nó trở thành cả hai subtype.

Thiết kế thích hợp hơn có thể là:

```text
                      Account
                         │
                         │ has
                         ▼
                    RoleAssignment
                     ├── CUSTOMER
                     ├── SELLER
                     └── MODERATOR

Một Account có thể có nhiều role đồng thời;
việc cấp/thu hồi role không đổi loại entity Account.
```

Đó là **kết hợp đối tượng** (*composition/object composition*): cấu trúc và hành vi của một đối tượng hình thành từ các thành phần mà nó sở hữu hoặc tham chiếu. Trong thiết kế Java, composition thường biểu diễn quan hệ **HAS-A**, **USES-A**, **PLAYS-A-ROLE** hoặc **IS-CONFIGURED-BY**. Kế thừa chỉ phù hợp nếu có quan hệ **IS-A** thực sự, ổn định và có ngữ nghĩa thay thế được.

Nội dung bài tập trung vào cách nhận ra một hệ phân cấp Hibernate không phản ánh đúng domain, các lựa chọn thay thế bằng `@Embedded`, association và delegation, cùng cách bảo vệ định danh, transaction, cascade và truy vấn sau khi chuyển sang composition.

## 2. IS-A và HAS-A khác nhau ở đâu?

Kế thừa kiểu lớp:

```java
class SpecialOrder extends Order {}
```

ngụ ý `SpecialOrder` **là một** `Order` và có thể được sử dụng ở những nơi yêu cầu `Order` theo hợp đồng của lớp cha.

Kết hợp:

```java
class Order {
    private DeliveryMethod deliveryMethod;
}
```

ngụ ý `Order` **có một** phương thức giao hàng. `DeliveryMethod` không phải là một subtype của Order, và việc thay đổi phương thức giao hàng không cần thay đổi bản chất của entity `Order`.

| Câu hỏi | Nghiêng về kế thừa | Nghiêng về composition |
|---|---|---|
| “X là một Y” có đúng theo ngôn ngữ nghiệp vụ? | Có, không phải chỉ do dùng chung field | X chỉ có/đóng vai trò/sử dụng Y |
| X có thay thế Y mà không vi phạm invariant không? | Có, theo hợp đồng hành vi | Hành vi tùy cấu hình hoặc phụ thuộc đối tượng cộng tác |
| Vai trò/loại của một đối tượng có đổi trong vòng đời không? | Hiếm khi, loại mang tính định danh ổn định | Thường thay đổi, bật/tắt hoặc tồn tại đồng thời |
| Có thể kết hợp nhiều đặc tính cùng lúc không? | Một nhánh subtype cố định đủ biểu diễn | Nhiều vai trò, chính sách, tùy chọn độc lập |
| Có cần query đa hình các subtype cùng một identity domain không? | Có | Có thể query owner hoặc thành phần theo quan hệ |
| Có chỉ trùng vài field hoặc một đoạn code không? | Đây **chưa đủ** lý do dùng `extends` | Dùng value object, component, service hoặc utility |
| Thành phần có thể được chia sẻ bởi nhiều owner không? | Hiếm khi có ý nghĩa subtype | Association tới entity tham chiếu dùng chung |

Hãy thử hai câu:

> “Một hóa đơn đã thanh toán **là một kiểu hóa đơn khác** hay là **một hóa đơn có trạng thái đã thanh toán**?”

> “Một sản phẩm được giao qua hãng vận chuyển A **là một subtype của Product** hay **có một cấu hình/đơn vị vận chuyển**?”

Thông thường, trạng thái và cấu hình nên là thuộc tính hoặc object liên kết của entity, trừ khi domain thực sự xác định các loại thực thể bất biến với invariant và vòng đời khác nhau.

## 3. Nguyên tắc thay thế được quan trọng hơn việc dùng chung code

Nguyên tắc Liskov Substitution Principle (LSP) nhấn mạnh: đối tượng của subtype phải dùng được ở nơi cần supertype mà không làm sai kỳ vọng hợp đồng.

Ví dụ không phù hợp:

```java
abstract class Payment {
    abstract void capture();
}

class CashOnDeliveryPayment extends Payment {
    @Override
    void capture() {
        throw new UnsupportedOperationException(
                "COD không capture qua cổng thanh toán");
    }
}
```

Nếu nghiệp vụ đã hứa rằng mọi `Payment.capture()` sẽ xử lý capture, subtype trên phá hợp đồng. Đưa `CashOnDeliveryPayment` vào hierarchy chỉ vì đều “liên quan tới thanh toán” khiến một API chung không còn có nghĩa nhất quán.

Có thể biểu diễn giao dịch thanh toán bằng một entity `Payment` với trạng thái và **phương thức xử lý** được chọn từ một component/policy phù hợp:

```text
Payment (entity: id, amount, state, methodCode)
    │
    ├── PaymentMethod/Provider configuration
    │       ├── CARD
    │       ├── BANK_TRANSFER
    │       └── CASH_ON_DELIVERY
    │
    └── Application service chọn processor hợp lệ
             ├── CardProcessor
             ├── BankTransferProcessor
             └── CashOnDeliveryProcessor
```

Nếu các method thực sự có hợp đồng khác nhau, hãy dùng các interface chính xác như `OnlineCapturablePaymentMethod`, `RefundablePaymentMethod` hoặc tách command `captureOnlinePayment` khỏi `markCashCollected`. Composition không có nghĩa phải tạo một interface khổng lồ bao gồm cả các operation không hợp lệ đối với một số thành phần.

### Một dấu hiệu thiết kế chưa tốt

Khi subclass phải override method chỉ để ném `UnsupportedOperationException`, thường xuyên kiểm tra `instanceof` để tránh lỗi, hoặc dùng cast về subtype trước khi gọi nghiệp vụ, hãy xem lại quan hệ IS-A. Có thể parent đang mô tả khái niệm quá rộng hoặc các đặc tính thực ra là vai trò/chính sách có thể kết hợp.

## 4. Kế thừa entity trong Hibernate mang theo chi phí gì?

Hibernate hỗ trợ một số chiến lược ánh xạ inheritance, mỗi chiến lược có tác động khác nhau lên schema và SQL:

| Chiến lược | Cấu trúc quan hệ | Lợi ích | Đánh đổi khi hierarchy không phù hợp |
|---|---|---|---|
| `SINGLE_TABLE` | Một bảng cho toàn hierarchy, thường có discriminator | Query polymorphic đơn giản; không cần join subtype | Nhiều cột chỉ áp dụng cho từng subtype, nullability/constraint phức tạp |
| `JOINED` | Bảng gốc và bảng riêng cho từng subtype; khóa liên kết theo ID | Chuẩn hóa các field đặc thù | Query subtype/polymorphic có join; chuyển loại entity không đơn giản |
| `TABLE_PER_CLASS` | Mỗi concrete subtype có bảng riêng | Cột riêng rõ cho từng subtype | Query đa hình có thể cần UNION, identity generation và FK đến toàn hierarchy khó hơn |
| `@MappedSuperclass` | Copy mapping field xuống bảng entity con; không tạo entity gốc | Tái sử dụng mapping của các field chung | Không có polymorphic entity query tới mapped superclass; vẫn là Java inheritance |

Ví dụ:

```java
import jakarta.persistence.DiscriminatorColumn;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Inheritance;
import jakarta.persistence.InheritanceType;

@Entity
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(name = "document_kind")
public abstract class Document {
    @Id
    @GeneratedValue
    private Long id;

    private String title;
}

@Entity
public class Report extends Document {
    private String reportingPeriod;
}

@Entity
public class Letter extends Document {
    private String recipient;
}
```

Một câu truy vấn `select d from Document d` có thể trả cả `Report` và `Letter` theo runtime type được xác định từ mapping/discriminator. Điều này hợp lý **nếu một report thực sự là một document và một letter thực sự là một document**, cùng chung identity/lifecycle contract.

Nhưng nếu chỉ vì `Customer`, `Partner` và `Staff` có field `email` mà lập hierarchy, mọi thay đổi nghiệp vụ về vai trò buộc phải giải quyết ở tầng kiểu entity, discriminator hoặc migration. Chi phí này không mang lại giá trị nếu domain chỉ cần một Account cùng nhiều role.

### 4.1. @MappedSuperclass không phải một quan hệ domain tự động đúng

Một lớp nền:

```java
import jakarta.persistence.Column;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;

@MappedSuperclass
public abstract class AuditedEntity {
    @Column(name = "created_by", updatable = false)
    protected String createdBy;

    @Version
    protected Long version;
}
```

giúp tái sử dụng mapping chung trong nhiều entity. Tuy vậy, `AuditedEntity` không tự là một entity có bảng/ID để query đa hình, và dùng `extends AuditedEntity` không biến các entity thành một khái niệm nghiệp vụ chung.

Khi chỉ tái sử dụng `createdBy`, `createdAt` hoặc những field audit, cân nhắc embedded component `AuditInfo` hoặc listener tùy yêu cầu. Chọn `@MappedSuperclass` khi muốn dùng chung **mapping kỹ thuật** một cách có chủ ý, không xem nó là bằng chứng cho quan hệ IS-A trong domain.

### 4.2. Entity type không giống một trạng thái thay đổi được

Với inheritance entity, discriminator hoặc bảng subtype biểu diễn **loại entity**. Một record đã được lưu là subtype nào thường không thể “đổi runtime class” bằng `setStatus()`. Muốn đổi subtype có thể phải tạo/xóa entity, cập nhật discriminator và dữ liệu subtype qua migration phức tạp, làm ảnh hưởng FK, cache, cascade và semantics của ID.

Nếu trạng thái có thể thay đổi theo thời gian, mô hình state trong entity thường phản ánh đúng nghiệp vụ hơn.

## 5. Bài toán chính: không biến trạng thái hóa đơn thành các lớp con

Xét một hóa đơn chuyển lần lượt qua `DRAFT → ISSUED → PAID`, đôi khi `CANCELLED`. Thiết kế kém phù hợp:

```java
// Ví dụ phản diện:
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Invoice { /* ... */ }

@Entity
public class DraftInvoice extends Invoice { /* ... */ }

@Entity
public class IssuedInvoice extends Invoice { /* ... */ }

@Entity
public class PaidInvoice extends Invoice { /* ... */ }
```

Vấn đề:

- Một hóa đơn giữ cùng số chứng từ và identity trong suốt vòng đời; nó **không trở thành một thực thể mới** mỗi khi đổi trạng thái.
- Query `Invoice` phải hiểu hierarchy dù các loại trên chỉ là một trục trạng thái.
- Chuyển trạng thái trên cùng managed entity không thể đổi Java class từ `DraftInvoice` sang `PaidInvoice`.
- Foreign key tới invoice và audit trail sẽ khó xử lý nếu ứng dụng phải xóa subtype cũ và tạo subtype mới.
- Thêm trạng thái `OVERDUE` hoặc `PARTIALLY_PAID` khiến hierarchy phình ra.

### 5.1. Model dùng một entity cùng trạng thái

DDL PostgreSQL minh họa:

```sql
CREATE TABLE invoices (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    invoice_no VARCHAR(40) NOT NULL UNIQUE,
    total_amount NUMERIC(19, 2) NOT NULL,
    currency_code VARCHAR(3) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_invoice_total_nonnegative
        CHECK (total_amount >= 0),
    CONSTRAINT ck_invoice_status
        CHECK (status IN ('DRAFT', 'ISSUED', 'PAID', 'CANCELLED'))
);
```

Mapping:

```java
package com.example.billing.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.math.BigDecimal;

public enum InvoiceStatus {
    DRAFT, ISSUED, PAID, CANCELLED
}

@Entity
@Table(name = "invoices")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "invoice_no", nullable = false,
            unique = true, length = 40)
    private String invoiceNo;

    @Column(name = "total_amount", nullable = false,
            precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "currency_code", nullable = false, length = 3)
    private String currencyCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private InvoiceStatus status;

    @Version
    private Long version;

    protected Invoice() {}

    public Invoice(String invoiceNo, BigDecimal totalAmount,
                   String currencyCode) {
        if (invoiceNo == null || invoiceNo.isBlank()
                || totalAmount == null || totalAmount.signum() < 0
                || currencyCode == null || currencyCode.length() != 3) {
            throw new IllegalArgumentException(
                    "Thông tin hóa đơn không hợp lệ");
        }
        this.invoiceNo = invoiceNo;
        this.totalAmount = totalAmount;
        this.currencyCode = currencyCode;
        this.status = InvoiceStatus.DRAFT;
    }

    public Long getId() { return id; }
    public InvoiceStatus getStatus() { return status; }
    public Long getVersion() { return version; }

    public void issue() {
        if (status != InvoiceStatus.DRAFT) {
            throw new IllegalStateException(
                    "Chỉ hóa đơn nháp mới được phát hành");
        }
        status = InvoiceStatus.ISSUED;
    }

    public void markPaid() {
        if (status != InvoiceStatus.ISSUED) {
            throw new IllegalStateException(
                    "Chỉ hóa đơn đã phát hành mới được thanh toán");
        }
        status = InvoiceStatus.PAID;
    }

    public void cancel() {
        if (status != InvoiceStatus.DRAFT
                && status != InvoiceStatus.ISSUED) {
            throw new IllegalStateException(
                    "Không thể hủy hóa đơn ở trạng thái hiện tại");
        }
        status = InvoiceStatus.CANCELLED;
    }
}
```

Các class/enum ở trên thuộc package minh họa; trong Java thật, `InvoiceStatus` và `Invoice` public cần đặt trong file riêng cùng tên. Việc dùng enum với `@Enumerated(EnumType.STRING)` giúp giá trị database đọc được; khi đổi tên enum phải chuẩn bị migration tương ứng.

Trong transaction:

```java
import jakarta.persistence.EntityManager;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void payInvoice(Long invoiceId) {
    Invoice invoice = entityManager.find(Invoice.class, invoiceId);
    if (invoice == null) {
        throw new IllegalArgumentException("Không tìm thấy hóa đơn");
    }
    invoice.markPaid();
    // Entity vẫn giữ id và runtime class Invoice.
    // Hibernate dirty checking → UPDATE status, version khi flush/commit.
}
```

Một entity giữ cùng `id` trong suốt vòng đời, `@Version` giúp phát hiện conflict khi hai transaction cập nhật cùng hóa đơn. Database vẫn cần những constraint/invariant phù hợp; nếu có nhiều đường ghi bỏ qua method, `markPaid()` ở Java không tự bảo vệ mọi thay đổi từ native SQL, bulk update hoặc hệ thống ngoài.

### 5.2. Nếu các trạng thái có hành vi khác nhau rõ rệt thì sao?

Vẫn có thể dùng **composition với policy/state object**:

```java
public interface InvoiceActionPolicy {
    boolean canCancel();
    boolean canAcceptPayment();
}

public final class IssuedInvoicePolicy implements InvoiceActionPolicy {
    @Override
    public boolean canCancel() { return true; }

    @Override
    public boolean canAcceptPayment() { return true; }
}

public final class PaidInvoicePolicy implements InvoiceActionPolicy {
    @Override
    public boolean canCancel() { return false; }

    @Override
    public boolean canAcceptPayment() { return false; }
}
```

Đây là các **đối tượng hành vi Java thông thường**, không nhất thiết là `@Entity`. Service có thể chọn policy theo `InvoiceStatus` đã lưu. Hệ thống tránh tạo lớp con Hibernate cho mỗi trạng thái, nhưng vẫn có chỗ tổ chức logic phức tạp theo trạng thái.

Không giữ một reference policy Java bất kỳ trong field persistent của entity mà mong Hibernate tự ánh xạ nó. Nếu dùng field cho object xử lý runtime, có thể đặt `@Transient` khi phù hợp hoặc để service/domain layer tạo policy từ state được lưu.

## 6. Composition trong Hibernate gồm những hình thức nào?

“Composition” trong thiết kế hướng đối tượng không tương đương duy nhất một annotation ORM. Một component có thể được nhúng như giá trị, là entity phụ thuộc, là entity chia sẻ hoặc là object service không được persist.

| Quan hệ domain | Cách biểu diễn | Khi thích hợp | Ownership/lifecycle |
|---|---|---|---|
| Owner **có một giá trị** | `@Embedded` + `@Embeddable` | Địa chỉ, khoảng thời gian, giá trị tiền, cấu hình nhỏ | Giá trị sống theo owner; thường không có ID riêng |
| Owner **có nhiều giá trị** | `@ElementCollection` | Danh sách tag, một vài số điện thoại | Các element thuộc owner; không có entity identity riêng |
| Owner **có entity phụ thuộc** | `@OneToOne` hoặc `@OneToMany` | Hồ sơ phụ, dòng đơn hàng, thông tin phê duyệt có ID | Cân nhắc cascade/orphanRemoval theo domain |
| Entity **tham chiếu entity dùng chung** | `@ManyToOne`, `@ManyToMany` | Loại tiền, vai trò, danh mục, nhà cung cấp | Không cascade remove tùy tiện tới entity dùng chung |
| Owner **dùng hành vi khác nhau** | Java interface + strategy/delegation | Pricing, gửi thông báo, thanh toán qua provider | Service/container tạo và sở hữu; không nhất thiết là mapping |
| Chỉ muốn dùng chung field/mapping | `@MappedSuperclass` hoặc embedded component | Audit fields, metadata | Lựa chọn kỹ thuật; không tự là domain subtype |

Khi nói “ưu tiên composition”, cần xác định **thành phần có identity và vòng đời riêng hay không**, có được chia sẻ giữa nhiều parent hay không, và liệu component cần được Hibernate quản lý như một entity hay chỉ là value object.

## 7. @Embeddable: tách giá trị mà không tạo hierarchy entity

Giả sử tài khoản cần lưu địa chỉ thanh toán. `Address` không phải một loại `Account`; Account **có một** Address.

```java
package com.example.accounts.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class PostalAddress {
    @Column(name = "street", nullable = false)
    private String street;

    @Column(name = "city", nullable = false)
    private String city;

    @Column(name = "postal_code")
    private String postalCode;

    protected PostalAddress() {}

    public PostalAddress(String street, String city,
                         String postalCode) {
        if (street == null || street.isBlank()
                || city == null || city.isBlank()) {
            throw new IllegalArgumentException("Địa chỉ không hợp lệ");
        }
        this.street = street;
        this.city = city;
        this.postalCode = postalCode;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }
}
```

Owner:

```java
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class CustomerAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Embedded
    private PostalAddress billingAddress;

    protected CustomerAccount() {}

    public CustomerAccount(PostalAddress billingAddress) {
        this.billingAddress = billingAddress;
    }

    public void changeBillingAddress(PostalAddress newAddress) {
        this.billingAddress = newAddress;
    }
}
```

Trong mapping cơ bản, các field của `PostalAddress` thường được lưu thành cột trên bảng `CustomerAccount`. Nếu cùng entity có hai địa chỉ (billing/shipping) cần dùng `@AttributeOverride(s)` để đặt tên cột không trùng. Không phải cứ `@Embeddable` là tự tạo một bảng riêng.

Giá trị nhúng thường **không có identity database độc lập**. Hai owner có địa chỉ giống nhau vẫn có hai bộ giá trị thuộc hai owner. Khi đổi địa chỉ, ứng dụng có thể thay toàn bộ `PostalAddress`; dirty checking của owner xử lý cập nhật trong transaction.

### Khi không nên dùng @Embedded

Nếu địa chỉ:

- Có ID được nhiều entity tham chiếu;
- Có quy trình xác minh, lịch sử và quyền sửa riêng;
- Cần phân trang, tìm kiếm và quản trị độc lập;
- Có vòng đời không phụ thuộc trực tiếp owner;

thì `Address` có thể cần là entity riêng. Ngược lại, bản chụp địa chỉ giao hàng của một đơn hàng thường nên là value object để giữ đúng địa chỉ tại thời điểm đặt, thay vì liên kết động đến địa chỉ hiện tại của khách hàng.

### Value object “bất biến” và Hibernate

Một `@Embeddable` có thể thiết kế API không có setter public và thay bằng instance mới. Nhưng trong mapping JPA truyền thống, provider vẫn cần cơ chế khởi tạo/điền field; không nên mặc nhiên dùng `final class` với mọi field `final` rồi cho rằng Hibernate phiên bản nào cũng xử lý được. Một số Hibernate version hỗ trợ record embeddable, nhưng khả năng đó phụ thuộc version/mapping và không có nghĩa record hợp làm `@Entity`.

## 8. Association: component có identity riêng

Một order có thể gắn với **một phương thức giao hàng** được quản trị tập trung:

```text
Order
  ├── id
  ├── status
  └── deliveryMethodId ───► DeliveryMethod
                               ├── id
                               ├── code
                               └── displayName
```

Nếu `DeliveryMethod` là dữ liệu tham chiếu dùng chung cho nhiều order, `@ManyToOne` phù hợp hơn tạo subtype `ExpressOrder`, `StandardOrder`, `PickupOrder`:

```java
@Entity
@Table(name = "delivery_methods")
public class DeliveryMethod {
    @Id
    private String code;

    @Column(nullable = false)
    private String displayName;

    protected DeliveryMethod() {}

    public String getCode() { return code; }
}
```

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "delivery_method_code", nullable = false)
    private DeliveryMethod deliveryMethod;

    protected Order() {}

    public void chooseDeliveryMethod(DeliveryMethod method) {
        if (method == null) {
            throw new IllegalArgumentException("Thiếu phương thức giao hàng");
        }
        this.deliveryMethod = method;
    }
}
```

DDL khái quát:

```sql
CREATE TABLE delivery_methods (
    code VARCHAR(30) PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL
);

CREATE TABLE orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    delivery_method_code VARCHAR(30) NOT NULL,
    CONSTRAINT fk_orders_delivery_method
        FOREIGN KEY (delivery_method_code)
        REFERENCES delivery_methods(code)
);
```

Mỗi order có thể đổi sang phương thức khác bằng cách thay FK trong transaction; runtime type của `Order` không đổi. Có thể thêm phương thức giao hàng mới bằng dữ liệu cấu hình nếu các quy tắc xử lý chung đã hỗ trợ. Nếu phát sinh thuật toán tính phí riêng, kết hợp với policy/service tương ứng thay vì lập thêm subtype Order cho từng nhà cung cấp.

**Không đặt `CascadeType.REMOVE`/`ALL` lên `Order.deliveryMethod` chỉ vì muốn Hibernate “lưu tất cả”**: `DeliveryMethod` là entity chia sẻ; xóa một Order không được xóa phương thức giao hàng mà các Order khác đang sử dụng.

### Entity phụ thuộc thực sự: @OneToOne và orphanRemoval

Khi component có ID/lifecycle phụ thuộc owner, `@OneToOne(cascade = ..., orphanRemoval = true)` có thể hợp lý. Ví dụ `Account` có `AccountProfile`, profile tồn tại chỉ khi tài khoản tồn tại.

```java
@Entity
public class AccountProfile {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String displayName;

    protected AccountProfile() {}

    public AccountProfile(String displayName) {
        this.displayName = displayName;
    }
}
```

```java
@Entity
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(cascade = CascadeType.ALL, orphanRemoval = true)
    @JoinColumn(name = "profile_id", unique = true)
    private AccountProfile profile;

    protected Account() {}

    public void replaceProfile(AccountProfile newProfile) {
        this.profile = newProfile;
    }
}
```

Đoạn trên minh họa association một-một và vòng đời phụ thuộc; trong thực tế cần quyết định vị trí FK (owner hay profile), nullability và thứ tự SQL khi thay profile có unique constraint. `orphanRemoval=true` có nghĩa profile cũ có thể bị xóa khi thay reference; chỉ dùng nếu profile **thật sự thuộc riêng Account và phải biến mất khi rời owner**.

Nếu profile cần được chuyển sang owner khác hoặc dùng chung, không chọn orphan removal như trên. Khi đó quan hệ và lifecycle phải được thiết kế khác.

## 9. Vai trò linh hoạt: Account có nhiều role thay vì các subtype

Quay lại ví dụ Account. Giả sử một user có thể đồng thời mua và bán, vai trò có thể được cấp/thu hồi. Khi đó role là **một thuộc tính/quan hệ động**, không phải một lớp con cố định.

### 9.1. Cách đơn giản: enum role như tập hợp giá trị

Nếu vai trò là danh sách nhỏ, ổn định, không cần metadata riêng:

```java
public enum AccountRole {
    CUSTOMER, SELLER, MODERATOR
}
```

```java
@Entity
@Table(name = "accounts")
public class Account {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String email;

    @ElementCollection(fetch = FetchType.LAZY)
    @CollectionTable(name = "account_roles",
            joinColumns = @JoinColumn(name = "account_id"))
    @Enumerated(EnumType.STRING)
    @Column(name = "role_code", nullable = false, length = 30)
    private Set<AccountRole> roles = new HashSet<>();

    protected Account() {}

    public void grant(AccountRole role) {
        roles.add(Objects.requireNonNull(role));
    }

    public void revoke(AccountRole role) {
        roles.remove(role);
    }
}
```

Giả sử import `java.util.HashSet`, `Set`, `Objects` và các Jakarta annotations tương ứng. DDL:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE account_roles (
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    role_code VARCHAR(30) NOT NULL,
    PRIMARY KEY (account_id, role_code)
);
```

Một account có thể có nhiều role. Khi role bị thu hồi, Hibernate thay đổi collection table trong transaction. Đây là một tập hợp **giá trị** gắn với Account; từng role assignment không có entity ID riêng trong mô hình đơn giản này.

### 9.2. Khi việc cấp role có metadata: entity liên kết

Nếu cần biết **ai** cấp quyền, **khi nào**, **đến bao giờ**, hoặc quyền cần phê duyệt, mỗi lần cấp quyền có vòng đời riêng. Khi đó chuyển sang entity `RoleAssignment`:

```text
Account (1)
    │
    └── RoleAssignment (N)
           ├── id
           ├── account_id → Account
           ├── role_code
           ├── granted_by
           ├── granted_at
           └── expires_at
```

DDL:

```sql
CREATE TABLE role_assignments (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    role_code VARCHAR(30) NOT NULL,
    granted_by BIGINT NOT NULL,
    granted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_account_current_role
        UNIQUE (account_id, role_code)
);
```

Entity:

```java
@Entity
@Table(name = "role_assignments")
public class RoleAssignment {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "account_id", nullable = false)
    private Account account;

    @Enumerated(EnumType.STRING)
    @Column(name = "role_code", nullable = false, length = 30)
    private AccountRole role;

    @Column(name = "granted_by", nullable = false)
    private Long grantedBy;

    @Column(name = "granted_at", nullable = false)
    private Instant grantedAt;

    @Column(name = "expires_at")
    private Instant expiresAt;

    protected RoleAssignment() {}

    public RoleAssignment(Account account, AccountRole role,
                          Long grantedBy, Instant grantedAt) {
        this.account = Objects.requireNonNull(account);
        this.role = Objects.requireNonNull(role);
        this.grantedBy = Objects.requireNonNull(grantedBy);
        this.grantedAt = Objects.requireNonNull(grantedAt);
    }
}
```

Ví dụ giả định có import `java.time.Instant`, `java.util.Objects`, các Jakarta annotations, và sử dụng entity `Account` phiên bản dành cho mô hình liên kết (thay collection giá trị `roles` bằng quan hệ đến assignments). **Không ánh xạ đồng thời hai mô hình trên cùng bảng chỉ để “hỗ trợ cả hai”**; đây là hai phương án thay thế nhau.

Nếu muốn lưu lịch sử cấp/thu hồi nhiều lần cùng một role, unique constraint trên `(account_id, role_code)` không còn phù hợp cho mọi row: cần xác định cách đánh dấu assignment active, bảng lịch sử riêng, partial unique index theo trạng thái hoặc ràng buộc khác tùy database.

**Ưu thế của composition:** cấp role mới không yêu cầu thay runtime class hay discriminator của Account. Entity `RoleAssignment` có thể được truy vấn, kiểm tra hiệu lực và audit theo nhu cầu, trong khi Account giữ định danh ổn định.

### 9.3. Phân quyền không chỉ là có record role

Role là dữ liệu đầu vào cho authorization; việc có quan hệ `Account → RoleAssignment` không tự chặn một HTTP request truy cập tài nguyên của người khác. Tầng security/service phải kiểm tra role hiệu lực, quyền trên đối tượng cụ thể, tenant và trạng thái account. Khi thu hồi role trong transaction, cache/token đã phát hành có thể cần chính sách đồng bộ riêng.

## 10. Kết hợp thuật toán qua Strategy và delegation

Không phải thành phần nào của domain cũng cần lưu thành bảng. Một sản phẩm có chính sách tính chiết khấu khác nhau có thể giữ cấu hình bền vững trong entity, còn thuật toán do Java object độc lập thực thi.

Thiết kế kế thừa nhiều nhánh dễ phình:

```text
Product
  ├── SeasonalDiscountProduct
  ├── LoyaltyDiscountProduct
  ├── CouponDiscountProduct
  └── NoDiscountProduct
```

Nếu cùng một sản phẩm vừa có khuyến mãi theo mùa vừa có coupon, class hierarchy một chiều không biểu diễn tự nhiên các quy tắc có thể kết hợp. Nếu chỉ cần đổi chính sách mà không đổi identity sản phẩm, subtype lại càng bất tiện.

### 10.1. Value object lưu cấu hình

```java
public enum DiscountKind {
    NONE, PERCENTAGE, FIXED_AMOUNT
}

@Embeddable
public class DiscountConfig {
    @Enumerated(EnumType.STRING)
    @Column(name = "discount_kind", nullable = false)
    private DiscountKind kind;

    @Column(name = "discount_value", precision = 19, scale = 2)
    private BigDecimal value;

    protected DiscountConfig() {}

    public DiscountConfig(DiscountKind kind, BigDecimal value) {
        this.kind = Objects.requireNonNull(kind);
        this.value = Objects.requireNonNull(value);
        if (value.signum() < 0
                || (kind == DiscountKind.PERCENTAGE
                    && value.compareTo(new BigDecimal("100")) > 0)) {
            throw new IllegalArgumentException(
                    "Cấu hình chiết khấu không hợp lệ");
        }
    }

    public DiscountKind getKind() { return kind; }
    public BigDecimal getValue() { return value; }
}
```

`DiscountConfig` là value object thuộc về sản phẩm hoặc một chương trình khuyến mãi, không cần trở thành subtype của `Product`. Các ví dụ Java giả định import `BigDecimal`, `Objects` và các annotation.

### 10.2. Strategy xử lý hành vi

```java
import java.math.BigDecimal;

public interface DiscountPolicy {
    BigDecimal apply(BigDecimal originalPrice, BigDecimal value);
}

public final class PercentageDiscount implements DiscountPolicy {
    @Override
    public BigDecimal apply(BigDecimal originalPrice,
                            BigDecimal value) {
        BigDecimal multiplier = BigDecimal.ONE.subtract(
                value.movePointLeft(2));
        return originalPrice.multiply(multiplier);
    }
}

public final class FixedAmountDiscount implements DiscountPolicy {
    @Override
    public BigDecimal apply(BigDecimal originalPrice,
                            BigDecimal value) {
        return originalPrice.subtract(value).max(BigDecimal.ZERO);
    }
}

public final class NoDiscount implements DiscountPolicy {
    @Override
    public BigDecimal apply(BigDecimal originalPrice,
                            BigDecimal value) {
        return originalPrice;
    }
}
```

Service chọn strategy từ persisted configuration:

```java
public final class PriceCalculator {
    private final Map<DiscountKind, DiscountPolicy> policies;

    public PriceCalculator() {
        this.policies = Map.of(
                DiscountKind.NONE, new NoDiscount(),
                DiscountKind.PERCENTAGE, new PercentageDiscount(),
                DiscountKind.FIXED_AMOUNT, new FixedAmountDiscount());
    }

    public BigDecimal calculate(BigDecimal original,
                                DiscountConfig config) {
        DiscountPolicy policy = policies.get(config.getKind());
        if (policy == null) {
            throw new IllegalArgumentException(
                    "Chính sách chiết khấu không được hỗ trợ");
        }
        return policy.apply(original, config.getValue());
    }
}
```

Ví dụ giả định import `java.util.Map`, `BigDecimal`; kết quả tính tiền cần quy tắc rounding/currency chính xác ở tầng nghiệp vụ. Có thể dùng dependency injection thay `new` strategy trực tiếp.

Ở đây các subclass `PercentageDiscount`, `FixedAmountDiscount`, `NoDiscount` **là polymorphism Java hợp lệ** theo interface `DiscountPolicy`; nhưng chúng **không phải JPA entity inheritance hierarchy**. Dùng composition không có nghĩa loại bỏ mọi kế thừa hoặc interface; nó đặt tính đa hình ở đúng tầng trách nhiệm.

Nếu nhiều chính sách có thể xếp chồng, domain có thể lưu danh sách discount rule và một policy pipeline có thứ tự/điều kiện rõ ràng. Không tạo subclass entity cho mọi tổ hợp `SeasonalAndCouponAndMemberDiscountProduct`.

### 10.3. Chú ý ranh giới persist và runtime

Nếu entity có field:

```java
private DiscountPolicy discountPolicy;
```

Hibernate không tự biết lưu một interface Java thành cột nào. Phương án thông thường là persist `DiscountConfig` hoặc quan hệ tới `DiscountRule @Entity`, rồi ở service ánh xạ dữ liệu đó sang policy Java. Nếu field chỉ dùng trong runtime, đánh dấu `@Transient` hoặc không đặt nó trong entity.

## 11. Những dấu hiệu nghiệp vụ nên tránh inheritance entity

### 11.1. Một đối tượng có nhiều vai trò cùng lúc

Một Account đồng thời là buyer và seller; một Employee đồng thời là manager và reviewer. Kế thừa đơn lớp `Buyer extends Account` và `Seller extends Account` không biểu diễn trực tiếp trạng thái đồng thời. Dùng role assignment hoặc capability relationship.

### 11.2. Loại được chọn khi cấu hình, rồi thường xuyên thay đổi

Một Order đổi từ standard shipping sang express, một Product đổi pricing plan, một Invoice đi qua các trạng thái. Với cùng identity, trường dữ liệu/association thay đổi hợp lý hơn việc “đổi class”.

### 11.3. Các đặc tính độc lập kết hợp với nhau

Product có shipping type, tax category, discount policy và warranty plan. Bốn trục đó độc lập. Nếu tạo subtype cho mọi tổ hợp, số loại tăng theo tích số lựa chọn:

```text
4 loại shipping × 3 tax categories × 5 discount plans
    = 60 tổ hợp subtype tiềm năng
```

Composition thể hiện mỗi trục bằng thành phần hoặc thuộc tính riêng, giảm số class và giúp thay từng chính sách độc lập.

### 11.4. Subclass chỉ khác một boolean hoặc vài field

`PremiumCustomer extends Customer` chỉ vì có `premium=true` là tín hiệu nên xem lại. Nếu trạng thái premium có thể được cấp, gia hạn hoặc hết hạn, có thể dùng `Membership`/`Subscription` entity hoặc value object. Nếu PremiumCustomer thực sự là một loại customer có contract vĩnh viễn và vòng đời riêng, kế thừa có thể vẫn hợp lý; cần quyết định theo domain.

### 11.5. Subclass thường xuyên cast/instanceof

Nếu mọi nơi sử dụng:

```java
if (order instanceof ExpressOrder) {
    // Lấy provider
} else if (order instanceof PickupOrder) {
    // Lấy cửa hàng nhận
}
```

và các nhánh chỉ phân biệt phương thức giao hàng, entity có thể nên giữ `DeliveryOption` và truyền việc xử lý cho strategy. Nếu subtype có contract thật sự khác nhau, polymorphism qua method/interface phù hợp có thể tốt; chỉ việc `instanceof` xuất hiện nhiều nơi là một tín hiệu xem xét, chưa phải bằng chứng tuyệt đối.

### 11.6. Subclass chỉ để dùng chung các cột

`Person`, `Company` và `Warehouse` đều có địa chỉ nhưng không cùng một quan hệ IS-A. Hãy tạo `PostalAddress @Embeddable` hoặc `Address @Entity` dùng chung theo yêu cầu identity. Tránh đặt tất cả dưới `AddressOwnerEntity` chỉ để tái sử dụng ba field.

## 12. Khi nào inheritance vẫn là lựa chọn đúng?

Ưu tiên composition **không có nghĩa mọi entity inheritance đều sai**. Một hierarchy hữu ích khi:

1. Các subtype thực sự là các dạng của cùng một entity concept, có chung identity/lifecycle contract.
2. Runtime type của đối tượng ổn định sau khi tạo.
3. Query đa hình và quan hệ đến superclass là nhu cầu thật.
4. Hành vi subtype tuân thủ hợp đồng của superclass.
5. Số subtype và cấu trúc thuộc tính tương đối ổn định; chiến lược database mapping có chi phí chấp nhận được.

Ví dụ một hệ thống quản lý tài sản có `Asset` và các subtype `VehicleAsset`, `BuildingAsset`, `EquipmentAsset`. Nếu nghiệp vụ coi chúng là các loại tài sản khác nhau, mỗi loại có metadata và quy tắc định giá riêng, type không thay đổi và báo cáo cần query tất cả Asset, Hibernate inheritance có thể phù hợp.

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Asset {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String assetCode;
}

@Entity
public class VehicleAsset extends Asset {
    private String vehicleIdentificationNumber;
}

@Entity
public class BuildingAsset extends Asset {
    private BigDecimal floorArea;
}
```

Ở đây `VehicleAsset` *là một* `Asset` có identity ổn định. Tuy nhiên nếu tài sản chỉ có “cấu hình bảo hiểm” hoặc “đơn vị vận hành” khác nhau, những phần đó nên là association/policy của Asset, không phải một hierarchy con khác cho mọi kết hợp.

### Kế thừa và composition có thể cùng tồn tại

```text
Asset (@Inheritance JOINED)
  ├── VehicleAsset
  └── BuildingAsset

Mỗi Asset:
  ├── has Owner (@ManyToOne)
  ├── has AuditInfo (@Embedded)
  ├── has MaintenanceRecords (@OneToMany)
  └── uses ValuationPolicy (Java service/strategy)
```

Đây thường là thiết kế thực tế: inheritance chỉ mô tả **taxonomy thật sự**, còn quan hệ và hành vi biến đổi được thể hiện bằng composition.

## 13. Hibernate identity: vì sao composition giữ vòng đời ổn định hơn?

Hibernate dùng identifier mapping của một entity để ánh xạ hàng database tới managed object trong persistence context. Trong cùng `Session`, Hibernate thường trả cùng Java instance khi lấy cùng entity type và ID. Với hierarchy kế thừa, runtime entity type được ánh xạ theo mapping/discriminator, tham gia persistence context và được sử dụng trong polymorphic query.

Khi một business role hoặc state đổi:

```text
KẾ THỪA THEO TRẠNG THÁI:
  DraftInvoice(id=10)
          │ "đã thanh toán"
          ▼
  PaidInvoice(id=10) ?   ← Java object/class không tự biến dạng.

COMPOSITION THEO TRẠNG THÁI:
  Invoice(id=10, status=DRAFT)
          │ markPaid() sau các bước hợp lệ
          ▼
  Invoice(id=10, status=PAID)
                          ← Cùng entity identity và class.
```

Tương tự, Account được cấp thêm role không cần xóa Account cũ rồi tạo subtype mới, nên những FK từ Orders/Profiles/Messages đến Account vẫn giữ nguyên.

### Natural key và business attribute

Một doanh nghiệp có thể muốn gắn vai trò người bán theo số đăng ký kinh doanh. Dù đây là business key, việc role thay đổi không nên ảnh hưởng primary key của Account. Một surrogate `account_id` ổn định cùng bảng `seller_profiles` hoặc `role_assignments` cho phép bổ sung dữ liệu người bán theo nhu cầu.

Không chọn inheritance chỉ để nhóm lại những record có nhiều cột trùng; hãy đặt identity và vòng đời trước, sau đó mới quyết định cấu trúc class.

## 14. Composition không loại bỏ vấn đề cascade và ownership

Khi tách thành phần thành entity riêng, phải xác định ai sở hữu quan hệ và lúc nào được xóa component.

| Quan hệ | Hướng mapping | Cascade thường cân nhắc | Nguy cơ nếu sai |
|---|---|---|---|
| Order có OrderLines, dòng chỉ sống trong order | `@OneToMany(mappedBy=...)` + `@ManyToOne` phía con | `PERSIST`, `REMOVE`/`orphanRemoval` nếu domain cho phép | Xóa child không mong muốn, quên cập nhật FK phía owning side |
| Order tham chiếu DeliveryMethod dùng chung | `@ManyToOne` | Thường không cascade remove | Xóa phương thức dùng chung làm hỏng các Order khác |
| Account có Profile thuộc riêng | `@OneToOne` | `PERSIST`, có thể `orphanRemoval` | Profile cũ bị xóa dù còn cần lịch sử/chuyển owner |
| Account có RoleAssignment | `@OneToMany` hoặc query child trực tiếp | Theo chính sách lịch sử/thu hồi | Mất audit nếu xóa vật lý assignment |
| Article gắn Tags dùng chung | `@ManyToMany` hoặc association entity | Tránh `REMOVE` tới Tag | Xóa Tag được các Article khác dùng |
| Account có Address value | `@Embedded` | Không có entity cascade độc lập | Dùng address thay đổi động cho lịch sử không phù hợp |

**Owning side:** với quan hệ hai chiều, phía nắm FK hoặc join table quyết định việc Hibernate ghi quan hệ. Ví dụ `OrderLine.order` là phía sở hữu FK trong `@OneToMany(mappedBy="order")`. Khi thêm/xóa child, helper method nên cập nhật cả collection cha và reference con để đồ thị trong memory nhất quán.

**Orphan removal:** chỉ nên dùng nếu việc một component bị tách khỏi owner thật sự có nghĩa nó phải bị xóa. Nếu role assignment cần giữ lịch sử để audit, có thể dùng `revokedAt`/trạng thái hiệu lực thay vì `orphanRemoval=true`.

### Ví dụ helper đồng bộ hai phía

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(mappedBy = "order",
            cascade = CascadeType.PERSIST,
            orphanRemoval = true)
    private List<PurchaseLine> lines = new ArrayList<>();

    public void addLine(PurchaseLine line) {
        Objects.requireNonNull(line);
        lines.add(line);
        line.attachTo(this);
    }

    public void removeLine(PurchaseLine line) {
        if (lines.remove(line)) {
            line.detach();
        }
    }
}

@Entity
public class PurchaseLine {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    void attachTo(PurchaseOrder order) { this.order = order; }
    void detach() { this.order = null; }
}
```

Các class trên là ví dụ khái niệm với imports được lược bớt. Khi có `orphanRemoval=true`, việc tách child khỏi parent làm Hibernate xử lý xóa orphan ở flush, dù field `order` trong Java tạm null. Không áp dụng cùng helper để “gỡ liên kết nhưng vẫn giữ row” khi FK là `NOT NULL`.

## 15. Fetch plan: composition không tự làm SQL nhanh hơn

Một hệ phân cấp `JOINED` có thể tạo join đến các bảng subtype, trong khi composition tạo join đến các entity liên quan khi query/fetch cần. Chuyển sang composition giúp mô hình linh hoạt hơn, nhưng không miễn phí về hiệu năng:

- Quan hệ `@ManyToOne` mặc định trong JPA là `EAGER` nếu không chỉ rõ; nhiều association eager có thể kéo thêm bảng/SQL không cần thiết.
- Dùng `fetch = LAZY` cho association thích hợp giúp trì hoãn tải, nhưng khi truy cập nhiều proxy trong vòng lặp có thể phát sinh **N+1 query**.
- `JOIN FETCH` hữu ích khi cần một quan hệ cụ thể, nhưng fetch collection lớn hoặc nhiều collection cùng lúc có thể làm số row tăng mạnh.
- Trả trực tiếp entity graph cho JSON serializer có thể làm serializer truy cập lazy association ngoài ý muốn.
- Second-level cache, batch fetching và entity graph là công cụ tối ưu sau khi xác định đúng dữ liệu cần dùng.

Ví dụ query lấy đơn hàng và tên phương thức giao hàng để hiển thị:

```java
public record OrderListRow(
        Long id,
        String deliveryMethodName) {}
```

```java
List<OrderListRow> rows = em.createQuery(
        "select new com.example.read.OrderListRow(" +
        "  o.id, m.displayName) " +
        "from Order o join o.deliveryMethod m " +
        "order by o.id",
        OrderListRow.class)
        .setMaxResults(50)
        .getResultList();
```

Giả định record `OrderListRow` nằm trong package `com.example.read` và các entity mapping có trường được truy cập. Constructor projection chỉ chọn hai giá trị cần hiển thị, không phải nạp toàn bộ graph của `Order`, `DeliveryMethod` và các collection khác. Cần có index thích hợp và phân trang có thứ tự ổn định.

### Không dùng inheritance để né một phép join

Một số thiết kế gộp `DeliveryMethod` thành subtype của Order chỉ vì muốn tránh FK join. Nhưng chi phí query phải cân với chi phí diễn đạt sai domain: subtype explosion, migration phức tạp, khó thay role/configuration và khó tái sử dụng method ở nhiều order.

Nếu đọc nhiều lần một vài giá trị hiển thị, có thể chọn projection, read model hoặc denormalize một thuộc tính có kiểm soát. Không thay đổi ontology của domain chỉ để loại bỏ một phép JOIN chưa được đo.

## 16. Transaction và concurrency sau khi tách component

Khi một entity mang nhiều thành phần, ranh giới transaction phải bao phủ những thay đổi cần nguyên tử. Ví dụ cấp role `SELLER` cần tạo `RoleAssignment` và thiết lập hồ sơ người bán:

```text
begin transaction
    ├── kiểm tra Account có đủ điều kiện
    ├── thêm RoleAssignment(accountId, SELLER)
    ├── tạo/cập nhật SellerProfile
    └── commit

Nếu một bước lỗi → rollback toàn bộ thay đổi DB cùng transaction.
```

Nếu chạy thành hai service method mỗi method tự commit riêng, một method thành công rồi method kia thất bại có thể để account ở trạng thái nghiệp vụ không nhất quán.

### 16.1. @Version ở owner có tự bảo vệ mọi association không?

Không nên giả định. Nếu `Account` có `@Version` nhưng transaction chỉ `INSERT` một `RoleAssignment` qua entity child, version của Account **không nhất thiết được tăng** vì bản thân Account không có field được update. Tương tự, thay `OrderLine.quantity` không nhất thiết tăng `Order.version`.

Khi invariant nằm trên toàn aggregate, cần protocol nhất quán:

- Khóa owner bằng `PESSIMISTIC_WRITE` trong tất cả đường ghi cần serialize.
- Dùng optimistic locking và chủ động tăng/check version owner theo thiết kế.
- Đặt unique/foreign-key/check constraint thích hợp ở database để chặn race condition.
- Giới hạn transaction và xử lý ngoại lệ do constraint/lock/timeout phát sinh.

Ví dụ nếu mỗi Account chỉ có một assignment active cho một role, unique constraint theo mô hình trạng thái hiệu lực là lớp bảo vệ bắt buộc. Hai transaction cùng kiểm tra “chưa có role” rồi cùng insert vẫn có thể cạnh tranh; kiểm tra ở Java không thay thế constraint.

### 16.2. Composition với dịch vụ ngoài

Nếu Invoice có PaymentProvider và nghiệp vụ vừa commit SQL vừa gọi API thanh toán bên ngoài, rollback Hibernate không thể “hoàn tác” một giao dịch đã xác nhận ở provider. Composition chỉ giúp tổ chức hành vi; nó không tự tạo distributed transaction. Có thể cần idempotency key, transactional outbox, saga hoặc cơ chế đối soát theo yêu cầu.

## 17. Migration từ hierarchy không phù hợp sang composition

Chuyển mô hình kế thừa đã có dữ liệu không chỉ là sửa Java class. Phải giữ identity, FK, lịch sử và hỗ trợ rolling deployment nếu nhiều phiên bản ứng dụng chạy đồng thời.

Giả sử schema cũ dùng `JOINED`:

```text
accounts(id, email, ...)
  ├── customers(account_id PK/FK, ...)
  ├── sellers(account_id PK/FK, ...)
  └── moderators(account_id PK/FK, ...)
```

Mục tiêu:

```text
accounts(id, email, ...)
account_roles(account_id, role_code, ...)
seller_profiles(id, account_id, ...)
```

Trong mô hình cũ, một account thuộc subtype cụ thể; trong mô hình mới, account có nhiều role. Phải quyết định account hiện có nhận role nào, và giữ những field riêng của seller/customer ở đâu.

### 17.1. Các bước triển khai

1. **Xác định quy tắc domain mới.** Role nào có thể đồng thời? Khi role bị thu hồi có xóa profile không? Dữ liệu lịch sử có phải giữ không?
2. **Thêm schema mới bằng migration.** Tạo bảng role assignment/profile, FK, unique constraint, index và các giá trị mặc định hợp lệ; không phá bảng cũ ngay.
3. **Backfill dữ liệu.** Từ mỗi subtype cũ sinh role và dữ liệu profile tương ứng; giữ nguyên `accounts.id` để FK của các bảng nghiệp vụ không phải thay đổi.
4. **Đối chiếu dữ liệu.** Kiểm tra số account, role mapping, dữ liệu liên kết, bản ghi thiếu và xung đột uniqueness. Xác định rõ cách xử lý account bị mất subtype hoặc dữ liệu legacy sai.
5. **Chuyển đường đọc.** Service mới query role/profile thay vì discriminator. Dùng DTO/adapter khi cần giữ API contract trong giai đoạn chuyển đổi.
6. **Chuyển đường ghi.** Command tạo/cấp/thu hồi role ghi vào schema mới; có kế hoạch tương thích nếu triển khai rolling và app cũ vẫn ghi schema cũ.
7. **Cutover và dọn cũ.** Chỉ bỏ mapping/bảng subtype sau khi mọi instance mới, dữ liệu và job phụ trợ đã chuyển hết. Giữ kế hoạch rollback phù hợp với loại migration.

Nếu dùng `SINGLE_TABLE` trước đó, migration có thể chuyển discriminator sang role assignment và đưa các cột subtype sang bảng profile hoặc giữ trong owner theo quyết định. Nếu một record thuộc nhiều role cùng lúc nhưng schema cũ chỉ cho một discriminator, dữ liệu mới không thể được biểu diễn đầy đủ trên phiên bản app cũ; phải giải quyết compatibility trước khi mở chức năng nhiều role.

### 17.2. Những gì cần tránh

- Không “đổi class entity trong memory” rồi mong Hibernate tự sửa discriminator và bảng subtype.
- Không xóa subtype table trước khi backfill/cutover dữ liệu đã được kiểm soát.
- Không áp dụng `cascade = ALL` lên tất cả các quan hệ mới vì sẽ dẫn tới xóa dữ liệu dùng chung.
- Không dựa vào `merge()` một graph detached có dữ liệu thiếu để thực hiện migration domain.
- Không để hai mapping ORM khác nhau ghi cùng một bảng theo hai semantics đối nghịch trong thời gian dài.

Migration không nhất thiết phải thay đổi primary key của Account. Giữ identity ổn định là một lợi ích lớn của mô hình composition: phần thay đổi là dữ liệu vai trò và liên kết, không phải đối tượng Account đã được các nghiệp vụ khác tham chiếu.

## 18. Các tình huống lựa chọn thực tế

### A. Product có nhiều đặc tính thay đổi độc lập

Một sản phẩm có loại thuế, chính sách vận chuyển, cấu hình bảo hành và chiến dịch khuyến mãi. Không tạo mọi tổ hợp `TaxableDiscountedExpressProduct`. Dùng `Product @Entity` cùng `TaxCategory`, `DeliveryOption`, `WarrantyPlan` và các policy; quan hệ dùng `@Embedded` hay association tùy identity/lifecycle.

### B. User có nhiều quyền và role

Role được cấp, hết hạn, thu hồi và có thể đồng thời. Dùng account + role assignments. Nếu quyền chỉ là vài enum ổn định và không cần metadata, `@ElementCollection` có thể đủ; nếu cần audit, status, người cấp, dùng entity liên kết.

### C. Invoice trải qua vòng đời

Trạng thái DRAFT/ISSUED/PAID là state của cùng hóa đơn. Dùng một entity với `@Enumerated(EnumType.STRING)`, domain methods và `@Version`. Hành vi thay đổi theo state có thể dùng policy/state object không được persist như subtype entity.

### D. Nhiều loại tài sản có cùng identity domain

`VehicleAsset` và `BuildingAsset` có thể là subtype thật của `Asset` nếu chúng luôn là loại tài sản ổn định với hợp đồng chung. Dùng Hibernate inheritance khi query đa hình và mapping phù hợp; các thông tin như owner, bảo hiểm và định giá vẫn dùng composition.

### E. Order có nhiều dòng hàng

Một dòng hàng không phải “một kiểu Order”. Dùng `OrderLine @Entity` với `@ManyToOne Order`, query theo FK và helper phù hợp nếu có collection hai chiều. Với hàng nghìn dòng, không bắt Order luôn giữ toàn bộ list; phân trang child độc lập.

### F. Nhiều phương thức thanh toán

Phương thức thanh toán không phải một subtype của Payment Transaction trong mọi domain. Có thể lưu `methodCode` và liên kết thông tin tài khoản/provider; dùng processor strategy ở service. Nếu domain có các subtype Payment thật sự khác nhau, hãy phân tích hợp đồng capture/refund/lifecycle trước khi chọn inheritance.

### G. Customer và Vendor có cùng thông tin pháp lý

Nếu một tổ chức vừa là customer vừa là vendor, hierarchy `Customer extends Party` / `Vendor extends Party` một chiều gây khó. Có thể mô hình `Party @Entity` cùng `CustomerRelationship`, `VendorRelationship` hoặc các role assignment. Địa chỉ pháp lý là `@Embedded` hoặc entity địa chỉ tùy nhu cầu lịch sử và dùng chung.

### H. Báo cáo nhiều loại chứng từ

Nếu tất cả `Invoice`, `Receipt` và `CreditNote` thật sự là `FinancialDocument` với ID/lifecycle chung và hệ thống cần query đa hình, inheritance có thể đúng. Nếu chúng chỉ cần một giao diện báo cáo chung, có thể dùng projection `DocumentListRow`/union SQL hoặc read model mà không ép tất cả bảng thành một entity hierarchy.

## 19. Những lỗi thường gặp khi chuyển sang composition

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Một Account bị “đóng băng” ở role ban đầu | Đã chọn `Customer extends Account` như một trạng thái | Đưa role sang value/association có thể cấp/thu hồi |
| Query polymorphic phải join nhiều bảng subtype chỉ để đọc vài field chung | Hierarchy `JOINED` không phản ánh nhu cầu query | Xem lại identity domain; projection hoặc composition khi phù hợp |
| Một Order phải có hàng chục subtype cho shipping/tax/discount | Nhiều trục tính chất độc lập được mã hóa bằng class | Kết hợp các component/policy riêng |
| Hibernate không biết persist một strategy interface | Nhầm runtime behavior object với persistent state | Lưu config/type/association, tạo policy ở service |
| Xóa Order vô tình xóa DeliveryMethod | Cascade REMOVE sang shared entity | Không cascade remove tới reference data |
| Thay một embedded value nhưng không thấy dữ liệu | Owner detached hoặc transaction chưa commit | Tải managed owner và cập nhật trong transaction |
| N+1 sau khi chuyển @ManyToOne | Truy cập lazy association trong vòng lặp | Query DTO/projection hoặc fetch plan rõ ràng |
| Role mới được cấp nhưng permission check vẫn cũ | Cache/token hoặc state authorization chưa đồng bộ | Thiết kế hiệu lực, refresh/invalidation và ranh giới bảo mật |
| Hai request cùng cấp một role gây trùng | Chỉ kiểm tra tồn tại ở Java | Unique constraint, transaction và xử lý conflict |
| @Version của Account không đổi khi sửa RoleAssignment | Chỉ child entity bị update | Áp dụng protocol aggregate locking/version thống nhất |
| Migration làm mất FK lịch sử | Xóa/tạo lại entity khi đổi subtype | Giữ account ID, backfill và cutover có kiểm soát |
| Dùng @Embedded cho component cần được tìm/xóa độc lập | Value object không có entity ID | Đổi sang entity association nếu có identity riêng |
| Orphan removal xóa dữ liệu audit | Mô hình lifecycle “thu hồi” bị nhầm thành “xóa” | Dùng trạng thái/retention hoặc archive |
| Thêm nhiều flag vào owner thay cho subtype nhưng logic rối | Trộn quá nhiều trách nhiệm vào entity | Tách value object, policy/service và aggregate boundary hợp lý |

## 20. Một quy trình ra quyết định cho kiến trúc Hibernate

Khi định thêm `extends SomeEntity`, hãy trả lời lần lượt:

**1. Đây có phải quan hệ IS-A thật sự?** Nếu chỉ vì hai class có `id`, `name`, `address` hay cùng cần audit, đó chưa đủ lý do cho entity inheritance.

**2. Subtype có thay thế được superclass?** Các method chung có hợp đồng đúng cho mọi subtype không? Có subtype phải ném `UnsupportedOperationException` cho thao tác được coi là chung không?

**3. Loại có thay đổi trong vòng đời không?** Nếu user có thể thành seller, invoice thành paid, order đổi shipping method, đây là dấu hiệu dùng state/role/association.

**4. Các đặc tính có đồng thời hoặc độc lập không?** Nếu một object có nhiều role/strategy tùy ý, composition giúp tránh nổ số lượng subtype.

**5. Component có identity riêng không?** Giá trị thuần dùng `@Embeddable`; entity phụ thuộc dùng `@OneToOne`/`@OneToMany`; dữ liệu tham chiếu dùng `@ManyToOne`; hành vi dùng strategy không nhất thiết persist.

**6. Ai sở hữu lifecycle?** Cần quyết định cascade/orphanRemoval, FK ownership, soft delete/audit. Đừng cấp cascade REMOVE cho entity dùng chung.

**7. Ranh giới transaction nào giữ invariant?** Nếu owner và component phải đổi cùng nhau, quản lý chung transaction; xác định version/lock/constraint cho concurrent changes.

**8. Những query quan trọng là gì?** Cần query đa hình trên superclass hay query owner/association? Đo SQL và chọn fetch plan/projection thay vì đoán inheritance luôn nhanh hoặc composition luôn chậm.

**9. Nếu sau này domain đổi, thiết kế nào dễ mở rộng đúng nghĩa?** Thêm role hoặc policy mới nên là thêm dữ liệu/strategy, nếu những đặc tính đó không làm thay entity identity.

**10. Nếu hệ thống đã có dữ liệu, migration có giữ ID/FK không?** Thiết kế schema song song, backfill, chuyển đường đọc/ghi và dọn phần cũ theo quy trình.

## 21. Sơ đồ tổng hợp

```text
                    Hai khái niệm có chung dữ liệu/hành vi
                                      │
                              Có đúng IS-A?
                            ┌─────────┴─────────┐
                            │                   │
                           CÓ                  KHÔNG
                            │                   │
                   Subtype có thay được          ▼
                   superclass theo contract?  HAS-A / ROLE / STATE /
                            │                  USES-A / SHARES-A
                      ┌─────┴─────┐             │
                     CÓ          KHÔNG          ▼
                      │            │      Thành phần cần lưu DB?
                      │       Composition        │
                      ▼                    ┌─────┴─────┐
              Runtime type ổn định?        CÓ         KHÔNG
                  ┌───┴───┐                │            │
                 CÓ      KHÔNG             ▼            ▼
                  │        │       Có entity identity?  Java strategy,
                  │    State/role              │        service, policy
                  │    composition       ┌─────┴──────┐
                  ▼                      │            │
             Cân nhắc @Inheritance     KHÔNG         CÓ
             SINGLE_TABLE / JOINED      │            │
             / TABLE_PER_CLASS          ▼            ▼
                                  @Embedded /     Association
                                  @ElementCollection @OneToOne /
                                                    @ManyToOne /
                                                    @OneToMany
                                                         │
                                                         ▼
                                              Cascade, FK, fetch,
                                              version và transaction
                                              theo vòng đời domain
```

Khi quan hệ nghiệp vụ là **có một thành phần, đóng một vai trò, mang một trạng thái hoặc sử dụng một chính sách**, composition thường giữ đúng ý nghĩa hơn entity inheritance. Hibernate cung cấp cả value mapping, entity association và cơ chế giao dịch để hiện thực hóa thiết kế đó. Kế thừa vẫn hữu ích cho những subtype **thật sự là một dạng của cùng thực thể**, có hợp đồng và identity ổn định; phần còn lại nên được biểu diễn bằng thành phần và quan hệ phù hợp với vòng đời nghiệp vụ.
