# Giới hạn converter với định danh, phiên bản và kiểu ánh xạ đặc biệt trong JPA

Trong Jakarta Persistence API (JPA), `AttributeConverter<X, Y>` giúp chuyển đổi **giá trị của một thuộc tính Java** sang dạng thích hợp để lưu trong cơ sở dữ liệu, rồi chuyển ngược khi đọc. Cơ chế này đặc biệt tiện lợi khi mô hình miền nghiệp vụ dùng những kiểu giá trị như `EmailAddress`, `CurrencyCode`, `PhoneNumber` hoặc một enum có mã lưu trữ riêng.

Tuy nhiên, **converter không phải cơ chế ánh xạ vạn năng**. Các thuộc tính định danh (`@Id`, `@EmbeddedId`), phiên bản (`@Version`), quan hệ giữa entity, và những thuộc tính đang dùng một số kiểu ánh xạ chuyên biệt như `@Enumerated` hoặc `@Temporal` có những quy tắc riêng trong JPA. Gắn `@Convert` lên chúng không bảo đảm hành vi portable, ngay cả khi một phiên bản Hibernate hoặc database cụ thể vẫn chạy được.

Bài này giải thích phạm vi của converter, lý do các giới hạn tồn tại, cách xử lý những kiểu dữ liệu đặc biệt, và các hướng thiết kế an toàn khi cần chuyển đổi một giá trị nhưng không thể đặt converter trực tiếp lên thuộc tính đó.

## 1. Nhắc lại cơ chế `AttributeConverter`

Một converter là lớp triển khai giao diện:

```java
package jakarta.persistence;

public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
```

Trong đó:

- `X` là **kiểu thuộc tính ở Java/domain**, ví dụ `EmailAddress`.
- `Y` là **kiểu Java trung gian mà JPA/JDBC xử lý để lưu xuống database**, ví dụ `String`.
- `convertToDatabaseColumn` chuyển từ `X` sang `Y` khi ghi dữ liệu.
- `convertToEntityAttribute` chuyển từ `Y` về `X` khi đọc dữ liệu.

`Y` không phải tên kiểu SQL. Chẳng hạn, converter trả `String` không tự bảo đảm cột là `VARCHAR(255)` trên mọi hệ quản trị. JPA provider, JDBC driver, dialect và annotation ánh xạ quyết định kiểu SQL cụ thể.

### 1.1. Một ví dụ hợp lệ trên thuộc tính cơ bản

Giả sử ứng dụng định nghĩa giá trị email:

```java
package com.example.domain;

public record EmailAddress(String value) {
    public EmailAddress {
        if (value == null || value.isBlank() || !value.contains("@")) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
    }
}
```

Đây là **value object**, không phải entity. Nó không có vòng đời JPA riêng và được nhận diện bằng giá trị của `value`.

Viết converter:

```java
package com.example.persistence;

import com.example.domain.EmailAddress;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress value) {
        return value == null ? null : value.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbValue) {
        return dbValue == null ? null : new EmailAddress(dbValue);
    }
}
```

Dùng trong entity:

```java
import com.example.domain.EmailAddress;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email", nullable = false, length = 254)
    private EmailAddress email;

    protected Customer() {
    }

    public Customer(EmailAddress email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }
}
```

Một row khái niệm:

| id | email |
|---:|---|
| 7 | `an@example.com` |

Khi `Customer` được tải, converter chuyển chuỗi trong cột `email` thành `EmailAddress`. Khi entity managed được lưu hoặc cập nhật, JPA chuyển `EmailAddress` về chuỗi.

Đây là trường hợp converter hoạt động đúng mục đích: **chuyển giá trị của một basic attribute**, không thay đổi cách JPA định danh entity, kiểm soát phiên bản hay quản lý quan hệ.

### 1.2. Vị trí của converter trong luồng ORM

```text
             Ứng dụng Java / domain
                       |
                       v
          Customer.email : EmailAddress
                       |
                       | AttributeConverter<X, Y>
                       v
                  Java String
                       |
                       | JPA + JDBC + SQL type mapping
                       v
              Cột customer.email
                       |
                       | Đọc dữ liệu từ database
                       v
                  Java String
                       |
                       | convertToEntityAttribute(...)
                       v
                   EmailAddress
```

Converter chuyển **giá trị một thuộc tính**. Nó không thay thế `EntityManager`, SQL transaction, mapping quan hệ, xử lý lazy loading, hay các quy tắc riêng của định danh và optimistic locking.

## 2. Bảng tổng quan: converter được hỗ trợ ở đâu?

| Vị trí/kiểu thuộc tính | Converter theo JPA chuẩn | Điều cần nhớ |
|---|---|---|
| Basic attribute thông thường | **Có** | Phù hợp nhất với `@Convert` / `@Converter` |
| Basic attribute ở `@MappedSuperclass` | **Có** | Tôn trọng access type và cấu hình kế thừa |
| Basic attribute bên trong `@Embeddable` không phải định danh | **Có** | Có thể cấu hình tại thuộc tính hoặc qua đường dẫn trong `@Convert` |
| Basic element của `@ElementCollection` | **Có** | Ánh xạ giá trị phần tử, không phải quan hệ entity |
| `@Id` | **Không được JPA chuẩn bảo đảm** | Định danh có quy tắc mapping riêng; không dựa vào converter để tạo kiểu ID portable |
| `@EmbeddedId` và thành phần khóa ghép | **Không nên dựa vào converter** | Thuộc vùng định danh; cần mapping ID phù hợp với JPA/provider |
| `@Version` | **Không được JPA chuẩn bảo đảm** | Provider quản lý phiên bản khi kiểm tra optimistic locking |
| `@ManyToOne`, `@OneToOne`, `@OneToMany`, `@ManyToMany` | **Không** | Đây là association mapping, không phải basic value |
| Thuộc tính có `@Enumerated` | **Không kết hợp theo chuẩn** | Chọn enum mapping hoặc converter có chủ đích |
| Thuộc tính có `@Temporal` | **Không kết hợp theo chuẩn** | Chọn temporal mapping hoặc kiểu Java thời gian phù hợp |
| `@Embedded` như một đối tượng nguyên khối | **Không phải basic value** | Chuyển đổi các basic field bên trong, không convert cả embedded object như một cột mặc định |
| `@Lob` trên một basic attribute | **Cần xem xét cùng JDBC type/provider** | Không đồng nhất `@Lob` với converter; kiểm tra kiểu SQL và cách tải LOB |
| JSON, SQL array, geometry, kiểu DB riêng | **Không phải mọi kiểu đều có thể tạo chỉ bằng converter** | Có thể cần custom JDBC type / provider extension / mapping chuyên biệt |

**Nguyên tắc chính:** Converter chỉ nên được dùng tại nơi JPA coi thuộc tính là **basic persistent attribute có thể chuyển đổi**. Một annotation `@Convert` không làm biến mất giới hạn do `@Id`, `@Version` hoặc relationship mapping đặt ra.

Một số provider có mở rộng ngoài tiêu chuẩn. “Không được bảo đảm theo chuẩn” có nghĩa ứng dụng phụ thuộc vào provider/phiên bản có thể hoạt động trong môi trường này nhưng không portable sang môi trường khác; không nhất thiết mọi provider phải báo lỗi ngay lập tức.

## 3. Giới hạn thứ nhất: thuộc tính định danh `@Id`

### 3.1. Vì sao định danh không phải basic attribute thông thường?

Định danh JPA là cơ sở để persistence context biết **entity nào là entity nào**:

```text
Persistence context
    |
    +-- (Customer.class, id=7)   -> một managed Customer
    +-- (Customer.class, id=12)  -> một managed Customer khác
```

JPA dùng định danh trong các thao tác như:

- `EntityManager.find(EntityClass.class, id)`.
- Quản lý identity map trong persistence context.
- `persist`, `merge`, `remove` và phát hiện entity managed/detached.
- Khóa ngoại và mapping giữa các entity.
- Cache cấp hai, proxy và xử lý quan hệ tùy provider.
- Sinh khóa với `@GeneratedValue`, `@SequenceGenerator` hoặc cơ chế khác.

Do đó, việc chuyển đổi tùy ý định danh thành kiểu database có thể ảnh hưởng đến nhiều quy tắc của ORM ngoài thao tác ghi một cột.

Theo giới hạn của Jakarta Persistence, **attribute converter không được áp dụng theo cách portable cho ID attribute**. Một cấu hình như sau không nên được xem là mapping JPA chuẩn, ngay cả khi provider cụ thể cho phép:

```java
@Converter
public class CustomerIdConverter
        implements AttributeConverter<CustomerId, Long> {
    @Override
    public Long convertToDatabaseColumn(CustomerId id) {
        return id == null ? null : id.value();
    }

    @Override
    public CustomerId convertToEntityAttribute(Long value) {
        return value == null ? null : new CustomerId(value);
    }
}

@Entity
public class Customer {
    @Id
    @Convert(converter = CustomerIdConverter.class)
    private CustomerId id; // ĐỪNG giả định đây là mapping portable.
}
```

Ví dụ trên chỉ minh họa **cấu hình cần tránh**. Ngoài ràng buộc về converter, kiểu ID cũng phải phù hợp yêu cầu định danh của JPA/provider.

### 3.2. Giải pháp portable: giữ kiểu persistent ID được hỗ trợ

Một cách thiết kế là để JPA quản lý ID ở kiểu scalar thông dụng, còn domain có thể dùng value object tại ranh giới ứng dụng:

```java
package com.example.domain;

public record CustomerId(Long value) {
    public CustomerId {
        if (value == null || value <= 0L) {
            throw new IllegalArgumentException("ID phải dương");
        }
    }
}
```

```java
package com.example.persistence;

import com.example.domain.CustomerId;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id; // JPA quản lý ID dạng Long.

    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getPersistentId() {
        return id;
    }

    public CustomerId getDomainId() {
        return id == null ? null : new CustomerId(id);
    }
}
```

Khi tìm entity:

```java
CustomerId customerId = new CustomerId(7L);

Customer customer =
    entityManager.find(Customer.class, customerId.value());
```

Ở đây, `CustomerId` làm rõ kiểu của ID ở tầng domain/application. JPA tiếp tục dùng `Long` làm định danh persistent, không cần converter trên `@Id`.

Một hệ thống DDD phức tạp có thể tổ chức domain model và persistence model thành các lớp riêng để không phải để kiểu database xuất hiện trực tiếp trong domain. Đó là lựa chọn kiến trúc; không bắt buộc cho mọi ứng dụng nhỏ.

### 3.3. Nếu ID là mã nghiệp vụ dạng chuỗi

Ví dụ một sản phẩm được định danh bằng SKU ổn định:

```java
@Entity
public class CatalogProduct {

    @Id
    @Column(name = "sku", length = 64)
    private String sku; // Khóa lưu trữ hợp lệ trong ví dụ.

    private String displayName;

    protected CatalogProduct() {
    }

    public CatalogProduct(String sku, String displayName) {
        this.sku = sku;
        this.displayName = displayName;
    }
}
```

Không cần converter chỉ để lưu một `String` thành một cột text. Nếu miền nghiệp vụ có `SkuCode` value object, có thể bọc chuỗi trong service/domain API mà vẫn giữ mapping ID persistent là `String`.

Cần phân biệt **khóa nghiệp vụ** với **surrogate key**. Tên/mã có thể thay đổi hoặc mang rủi ro tái sử dụng thì không nên tùy tiện dùng làm `@Id`. Quyết định chọn khóa cần dựa trên yêu cầu về danh tính lâu dài, không xuất phát từ khả năng sử dụng converter.

### 3.4. `@EmbeddedId` và thành phần của khóa ghép

Khóa ghép có thể được mô tả bằng một `@Embeddable`:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {

    private Long orderId;
    private Integer lineNo;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNo) {
        this.orderId = orderId;
        this.lineNo = lineNo;
    }

    public Long getOrderId() {
        return orderId;
    }

    public Integer getLineNo() {
        return lineNo;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderLineId that)) return false;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNo, that.lineNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNo);
    }
}
```

```java
@Entity
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    private String sku;

    protected OrderLine() {
    }
}
```

Các trường `orderId` và `lineNo` góp phần vào **khóa chính của entity**. Vì vậy đừng suy luận rằng “nằm trong `@Embeddable`” thì mọi field đều được tự động áp dụng converter như các embeddable thông thường. Đối với khóa ghép, cần tuân thủ mapping ID của JPA và kiểm tra khả năng provider nếu định dùng value object hoặc chuyển đổi tùy biến cho thành phần khóa.

Điều này cũng áp dụng khi dùng `@IdClass`: các thuộc tính được đánh dấu `@Id` vẫn là định danh; converter trên chúng không được chuẩn bảo đảm.

### 3.5. `@MapsId` không phải cách “lách” giới hạn converter

`@MapsId` có thể dùng khi một entity lấy toàn bộ hoặc một phần khóa từ quan hệ với entity khác, thường xuất hiện trong mô hình shared primary key hoặc derived identity:

```java
@Entity
public class CustomerProfile {

    @Id
    private Long id;

    @OneToOne
    @MapsId
    @JoinColumn(name = "customer_id")
    private Customer customer;

    protected CustomerProfile() {
    }
}
```

`@MapsId` và `@JoinColumn` hướng dẫn JPA ánh xạ quan hệ/định danh dẫn xuất. **Không đặt converter lên `customer` để ép entity reference thành Long**. Nếu muốn đi từ `Customer` tới khóa ngoại, JPA đã có association mapping.

## 4. Giới hạn thứ hai: thuộc tính phiên bản `@Version`

### 4.1. Version thuộc cơ chế optimistic locking

JPA dùng `@Version` để phát hiện trường hợp hai transaction cập nhật cùng một entity dựa trên trạng thái cũ:

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    private int quantity;

    @Version
    private Long version;

    protected InventoryItem() {
    }
}
```

Giả sử ban đầu:

| id | quantity | version |
|---:|---:|---:|
| 41 | 20 | 3 |

Transaction A và B đều đọc `version = 3`:

```text
A đọc (quantity=20, version=3)
B đọc (quantity=20, version=3)

A cập nhật quantity=19
    -> UPDATE ... WHERE id=41 AND version=3
    -> version tăng lên 4

B cố cập nhật quantity=18 từ version=3
    -> kiểm tra version cũ không còn khớp
    -> optimistic lock conflict
```

SQL cụ thể do provider sinh có thể khác, nhưng ý tưởng là **version được JPA quản lý và dùng trong điều kiện cập nhật để phát hiện xung đột**.

### 4.2. Không dùng converter để thay thế kiểu version

Ví dụ cần tránh:

```java
public record Revision(long value) { }

@Converter
public class RevisionConverter
        implements AttributeConverter<Revision, Long> {
    @Override
    public Long convertToDatabaseColumn(Revision revision) {
        return revision == null ? null : revision.value();
    }

    @Override
    public Revision convertToEntityAttribute(Long value) {
        return value == null ? null : new Revision(value);
    }
}

@Entity
public class IncorrectDocument {

    @Id
    private Long id;

    @Version
    @Convert(converter = RevisionConverter.class)
    private Revision version; // Không portable theo JPA.
}
```

`@Version` thuộc quy tắc optimistic locking của persistence provider. Converter không phải công cụ mở rộng tùy ý loại version được JPA chấp nhận. Thay vào đó, nên sử dụng **kiểu version được đặc tả/provider hỗ trợ**, chẳng hạn một kiểu số nguyên được hỗ trợ, và cho JPA quản lý thuộc tính đó.

```java
@Version
@Column(name = "version", nullable = false)
private Long version;
```

Nếu tầng API cần trả revision dưới dạng chuỗi hoặc value object, hãy chuyển đổi khi tạo DTO:

```java
public record DocumentResponse(Long id, String revision) { }

// Ví dụ tạo response sau khi tải entity:
DocumentResponse response = new DocumentResponse(
    document.getId(),
    String.valueOf(document.getVersion())
);
```

DTO ở đây có thể dùng representation khác với persistent field. Việc dựng DTO không thay đổi quy tắc ánh xạ `@Version`.

### 4.3. Không tự sửa version tùy tiện

Một lỗi khác:

```java
document.setVersion(document.getVersion() + 1L);
```

Về nguyên tắc, phiên bản phải do provider kiểm soát theo quy tắc optimistic locking. Tự tăng version từ code nghiệp vụ có thể gây sai lệch hoặc xung đột không mong muốn. Cần bảo vệ transaction, dùng `@Version` đúng vị trí, và để JPA phát hiện tranh chấp.

## 5. Giới hạn thứ ba: thuộc tính quan hệ entity

### 5.1. Quan hệ không phải basic value

Các annotation:

- `@ManyToOne`
- `@OneToOne`
- `@OneToMany`
- `@ManyToMany`

mô tả **liên kết giữa entity**, khác với `@Basic` hoặc một basic field mặc định.

Ví dụ:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    protected PurchaseOrder() {
    }
}
```

JPA quản lý mối quan hệ `PurchaseOrder.customer`, gắn với khóa ngoại `customer_id`. Không nên áp dụng converter để biến reference `Customer` thành khóa:

```java
@ManyToOne
@Convert(converter = CustomerToLongConverter.class)
private Customer customer; // Không phải mapping converter chuẩn.
```

Lý do:

- Quan hệ phải duy trì identity của entity đích.
- Provider có thể tạo proxy hoặc lazy-load entity liên kết.
- Quan hệ còn tham gia cascade, join, flush ordering, foreign key và tính nhất quán.
- Converter chỉ biết chuyển hai giá trị X↔Y; nó không thay thế toàn bộ hợp đồng association mapping.

### 5.2. Nếu chỉ cần mã tham chiếu thì sao?

Một thiết kế có thể lưu **giá trị scalar** thay vì association:

```java
@Entity
public class ImportRecord {

    @Id
    private Long id;

    @Column(name = "external_customer_code", length = 50)
    private String externalCustomerCode;

    protected ImportRecord() {
    }
}
```

Đây là basic attribute bình thường. Nếu ứng dụng muốn dùng value object cho mã tham chiếu, converter có thể phù hợp **miễn thuộc tính đó không phải `@Id`, `@Version` hoặc annotation mapping bị loại trừ khác**.

Nhưng lưu chuỗi mã tham chiếu không tạo ra `@ManyToOne`. Nếu hệ thống cần quan hệ thực sự, ràng buộc foreign key và phép join entity, hãy dùng association mapping thay vì nghĩ rằng converter có thể khôi phục mọi ngữ nghĩa quan hệ.

### 5.3. Collection entity khác collection giá trị

So sánh:

```java
@OneToMany(mappedBy = "customer")
private List<PurchaseOrder> orders;
```

và:

```java
@ElementCollection
private Set<String> tags;
```

`orders` là tập **entity relationship**, không phải các phần tử basic dùng converter. Trong khi đó `tags` là collection các giá trị cơ bản; JPA có thể ánh xạ phần tử basic bằng converter nếu cần.

## 6. Giới hạn thứ tư: `@Enumerated` và enum converter

### 6.1. Hai chiến lược khác nhau cho enum

Một enum Java:

```java
public enum PaymentStatus {
    CREATED,
    AUTHORIZED,
    SETTLED,
    CANCELLED
}
```

Có thể ánh xạ bằng cơ chế enum của JPA:

```java
@Enumerated(EnumType.STRING)
@Column(name = "payment_status", nullable = false)
private PaymentStatus status;
```

JPA lưu tên enum bằng biểu diễn phù hợp, ví dụ chuỗi `SETTLED`. `EnumType.ORDINAL` có cơ chế dựa trên vị trí ordinal; việc thêm hoặc sắp xếp lại enum constant có thể làm sai dữ liệu đã lưu nếu không migration cẩn thận.

Nếu muốn lưu mã ổn định theo domain, ví dụ `CREATED -> "C"`, `SETTLED -> "S"`, có thể **dùng converter thay cho `@Enumerated`**:

```java
public enum PaymentStatus {
    CREATED("C"),
    AUTHORIZED("A"),
    SETTLED("S"),
    CANCELLED("X");

    private final String code;

    PaymentStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static PaymentStatus fromCode(String code) {
        for (PaymentStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Mã PaymentStatus không hợp lệ: " + code
        );
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class PaymentStatusConverter
        implements AttributeConverter<PaymentStatus, String> {

    @Override
    public String convertToDatabaseColumn(PaymentStatus status) {
        return status == null ? null : status.code();
    }

    @Override
    public PaymentStatus convertToEntityAttribute(String code) {
        return code == null ? null : PaymentStatus.fromCode(code);
    }
}
```

Trong entity:

```java
@Convert(converter = PaymentStatusConverter.class)
@Column(name = "payment_status", nullable = false, length = 1)
private PaymentStatus status;
```

Ở cách thứ hai, **không thêm `@Enumerated`**. Converter được dùng để biểu diễn enum bằng mã tùy chọn; `@Enumerated` đã có cơ chế mapping enum riêng.

### 6.2. Đừng dùng đồng thời `@Enumerated` và `@Convert`

Một cấu hình mơ hồ:

```java
@Enumerated(EnumType.STRING)
@Convert(converter = PaymentStatusConverter.class)
private PaymentStatus status; // Không phải tổ hợp portable.
```

Trong JPA, converter không được áp dụng theo chuẩn cho attribute được đánh dấu `@Enumerated`. Dù dùng `@Converter(autoApply = true)` cho enum, một thuộc tính có `@Enumerated` vẫn thuộc nhóm bị loại trừ khỏi chuyển đổi tự động theo quy tắc JPA.

**Cách chọn:**

| Yêu cầu | Cách ánh xạ |
|---|---|
| Lưu tên enum như `CREATED`, `SETTLED` | `@Enumerated(EnumType.STRING)` |
| Lưu ordinal theo yêu cầu đặc biệt, đã kiểm soát migration | `@Enumerated(EnumType.ORDINAL)` (cân nhắc rủi ro) |
| Lưu mã domain cố định như `C`, `S` | `@Convert` với converter enum, bỏ `@Enumerated` |
| Muốn database native enum type hoặc hỗ trợ enum chuyên biệt | Xem cơ chế dialect/provider và migration, không giả định converter tự tạo native enum |

Trong các phiên bản Jakarta Persistence mới có thêm khả năng liên quan biểu diễn enum; nếu dùng tính năng này, cần xét **phiên bản đặc tả và provider**. Nguyên tắc xuyên suốt là không trộn các cơ chế ánh xạ có ngữ nghĩa khác nhau một cách tùy tiện.

## 7. Giới hạn thứ năm: `@Temporal` và kiểu ngày giờ

### 7.1. `@Temporal` có mục đích riêng

Trong JPA truyền thống, `@Temporal` được dùng để chỉ định kiểu thời gian cho `java.util.Date` và `java.util.Calendar`:

```java
@Temporal(TemporalType.DATE)
@Column(name = "birth_date")
private java.util.Date birthDate;

@Temporal(TemporalType.TIMESTAMP)
@Column(name = "created_at")
private java.util.Date createdAt;
```

JPA dùng mapping temporal để lựa chọn biểu diễn ngày, giờ hoặc timestamp. Một thuộc tính đã được khai báo `@Temporal` không thuộc nhóm dùng converter theo cách portable.

Ví dụ không nên dựa vào:

```java
@Temporal(TemporalType.TIMESTAMP)
@Convert(converter = LegacyDateConverter.class)
private java.util.Date createdAt;
```

Không phải cách chuẩn để yêu cầu JPA đồng thời áp dụng hai cơ chế chuyển đổi.

### 7.2. Với `java.time` thường không cần `@Temporal`

Java hiện đại cung cấp:

- `LocalDate` cho ngày không có giờ.
- `LocalTime` cho giờ địa phương.
- `LocalDateTime` cho ngày và giờ địa phương.
- `Instant` cho mốc thời gian tuyệt đối.
- `OffsetDateTime` cho ngày giờ kèm offset.

Nhiều kiểu `java.time` đã có basic mapping trong các phiên bản JPA hiện đại, nên có thể viết:

```java
@Column(name = "business_day")
private java.time.LocalDate businessDay;
```

Không thêm `@Temporal` cho `LocalDate`. Nếu ứng dụng cần value object biểu diễn ngày nghiệp vụ:

```java
public record BusinessDay(java.time.LocalDate value) {
    public BusinessDay {
        if (value == null) {
            throw new IllegalArgumentException("Thiếu ngày nghiệp vụ");
        }
    }
}
```

Có thể tạo converter **cho thuộc tính basic này** nếu không dùng `@Temporal` hoặc mapping bị loại trừ khác:

```java
@Converter
public class BusinessDayConverter
        implements AttributeConverter<BusinessDay, java.time.LocalDate> {

    @Override
    public java.time.LocalDate convertToDatabaseColumn(
            BusinessDay businessDay) {
        return businessDay == null ? null : businessDay.value();
    }

    @Override
    public BusinessDay convertToEntityAttribute(
            java.time.LocalDate value) {
        return value == null ? null : new BusinessDay(value);
    }
}
```

```java
@Convert(converter = BusinessDayConverter.class)
@Column(name = "business_day")
private BusinessDay businessDay;
```

Cần phân biệt **ý nghĩa dữ liệu**: `LocalDateTime` không gắn múi giờ, còn `Instant` biểu diễn mốc thời gian trên trục thời gian toàn cầu. Converter không tự giải quyết việc chọn timezone, offset, daylight saving hoặc quy định của database. Hãy chọn kiểu Java phù hợp với ngữ nghĩa nghiệp vụ trước khi viết converter.

## 8. Các kiểu ánh xạ đặc biệt: khi nào converter chưa đủ?

Không phải mọi trường hợp ngoài `String`, `Long`, `LocalDate` đều bị cấm chuyển đổi. Nhưng với loại mapping mang ngữ nghĩa đặc biệt, cần xác định rõ converter đang làm việc tại tầng nào.

### 8.1. `@Embedded`: chuyển đổi thuộc tính bên trong, không tự thu gọn cả object

Một embeddable nhóm nhiều cột:

```java
@Embeddable
public class ContactDetails {

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email")
    private EmailAddress email;

    @Column(name = "phone")
    private String phone;

    protected ContactDetails() {
    }
}
```

```java
@Entity
public class ContactOwner {

    @Id
    private Long id;

    @Embedded
    private ContactDetails details;

    protected ContactOwner() {
    }
}
```

Ở đây, `email` là **basic field trong embeddable** nên converter được dùng đúng mục đích. Nhưng `details` mang annotation `@Embedded` là cả **nhóm thuộc tính**, không phải một basic field duy nhất có thể tùy ý gắn `AttributeConverter<ContactDetails, String>` rồi mong JPA tự chuyển toàn bộ mapping nhiều cột thành một cột.

Nếu muốn một value object được lưu trong một cột duy nhất, thiết kế nó thành basic converted attribute phù hợp; khi đó không sử dụng `@Embedded` cho chính thuộc tính đó. Nếu muốn nhiều cột, dùng `@Embeddable` với mapping các thành phần.

### 8.2. Đổi converter ở một field bên trong embeddable

Một entity có thể override converter theo đường dẫn:

```java
@Embedded
@Convert(
    attributeName = "email",
    converter = EmailAddressConverter.class
)
private ContactDetails details;
```

Ý nghĩa `attributeName = "email"`: thuộc tính `email` **bên trong** `details` được áp dụng converter. Điều này khác với việc convert toàn bộ `details`.

Đường dẫn sâu hơn hoặc ở key/value của map collection có quy tắc đặc biệt về `attributeName`. Khi cần mapping phức tạp, hãy tuân thủ cú pháp annotation của phiên bản Jakarta Persistence đang sử dụng, tránh suy luận từ tên field Java mà không xem cấu trúc embeddable/collection.

### 8.3. `@EmbeddedId` khác `@Embedded`

Hai ví dụ có cấu trúc bề ngoài giống nhau:

```java
@Embedded
private ShippingAddress shippingAddress;
```

và:

```java
@EmbeddedId
private OrderLineId id;
```

Với `@Embedded`, đối tượng là một value object thành phần của entity, và converter có thể áp dụng trên các basic attribute đủ điều kiện bên trong.

Với `@EmbeddedId`, toàn bộ object đóng vai trò **định danh entity**. Những hạn chế của identity vẫn cần được tôn trọng; không được suy ra rằng converter sẽ portable trên các thành phần khóa chỉ vì chúng nằm trong embeddable.

### 8.4. `@ElementCollection`: phần tử giá trị có thể chuyển đổi

Ví dụ một value object dùng làm tag:

```java
public record TagCode(String value) {
    public TagCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Tag rỗng");
        }
    }
}
```

```java
@Converter
public class TagCodeConverter
        implements AttributeConverter<TagCode, String> {

    @Override
    public String convertToDatabaseColumn(TagCode tag) {
        return tag == null ? null : tag.value();
    }

    @Override
    public TagCode convertToEntityAttribute(String value) {
        return value == null ? null : new TagCode(value);
    }
}
```

```java
@Entity
public class Note {

    @Id
    private Long id;

    @ElementCollection
    @CollectionTable(
        name = "note_tag",
        joinColumns = @JoinColumn(name = "note_id")
    )
    @Column(name = "tag_code")
    @Convert(converter = TagCodeConverter.class)
    private Set<TagCode> tags = new HashSet<>();

    protected Note() {
    }
}
```

Trong ví dụ, `Note` là entity; `TagCode` là basic value được converter ánh xạ thành chuỗi trong bảng collection. Những annotation này có thể yêu cầu các import như `jakarta.persistence.ElementCollection`, `CollectionTable`, `JoinColumn`, `Column`, `Convert` và `java.util.Set`/`HashSet`.

Điểm phân biệt:

- `@ElementCollection Set<TagCode>`: phần tử là **value**, có thể convert bằng basic mapping phù hợp.
- `@OneToMany List<NoteTagEntity>`: phần tử là **entity**, thuộc relationship mapping và không dùng converter để thay thế.
- Collection map có key/value phức tạp có quy tắc `@Convert.attributeName` riêng; không áp dụng kết luận “mọi collection đều có thể convert” cho các association.

### 8.5. `@Lob`: converter không đảm bảo kiểu BLOB/CLOB mong muốn

`@Lob` dùng để biểu thị dữ liệu lớn, ví dụ:

```java
@Lob
private byte[] documentBytes;

@Lob
private String articleBody;
```

Cần phân biệt:

- `@Lob` mô tả **ngữ nghĩa large object** ở tầng persistence.
- `AttributeConverter` mô tả **chuyển đổi giữa kiểu Java X và kiểu trung gian Y**.
- JDBC driver/dialect quyết định chi tiết mapping nhị phân, ký tự và kiểu SQL.
- `@Basic(fetch = FetchType.LAZY)` trên một basic LOB chỉ là gợi ý; provider có thể tải ngay.

Nếu muốn kết hợp converter với một basic attribute có `@Lob`, cần xác định rõ dạng dữ liệu sau chuyển đổi, khả năng của provider và kiểu cột thực tế. Ví dụ converter mã hóa chuỗi thành byte array **không đồng nghĩa** JPA tự tạo đúng cột BLOB tương thích ở mọi database. Một số provider còn phân biệt cột nhị phân thường với locator-based LOB.

Tùy yêu cầu, nên dùng trực tiếp `@Lob byte[]`/`@Lob String`, hoặc cơ chế định kiểu JDBC/provider riêng để kiểm soát DDL và binding. Converter cũng không tự biến `byte[]` thành luồng streaming hay tự quản lý mật mã.

### 8.6. JSON, SQL array và kiểu cột đặc thù

Một converter có thể serialize một value object thành `String`:

```java
@Converter
public class PreferencesConverter
        implements AttributeConverter<Preferences, String> {

    @Override
    public String convertToDatabaseColumn(Preferences value) {
        return value == null ? null : value.toJson();
    }

    @Override
    public Preferences convertToEntityAttribute(String value) {
        return value == null ? null : Preferences.fromJson(value);
    }
}
```

Nhưng như vậy **không bắt buộc** database dùng native JSON column. Nếu cần truy vấn theo JSON path, index JSON, SQL array, geometry, enum DB native, custom binary type hoặc tính năng vendor, một converter X↔String có thể không đủ.

Có thể cần:

- Cấu hình dialect/schema migration phù hợp.
- Cơ chế mapping JSON/array theo phiên bản JPA provider.
- Custom JDBC type hoặc type descriptor của provider.
- Tính năng SQL đặc thù của database.

Ví dụ `@JdbcTypeCode` là annotation riêng của Hibernate, **không phải annotation portable của Jakarta Persistence**. Khi sử dụng tính năng như vậy, nên ghi rõ phụ thuộc provider và phiên bản trong dự án.

## 9. `autoApply` không bỏ qua giới hạn

`@Converter(autoApply = true)` yêu cầu provider tự áp dụng converter cho các basic attribute phù hợp về kiểu:

```java
@Converter(autoApply = true)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress value) {
        return value == null ? null : value.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String value) {
        return value == null ? null : new EmailAddress(value);
    }
}
```

Nếu một entity có:

```java
private EmailAddress primaryEmail;
private EmailAddress backupEmail;
```

Hai thuộc tính basic phù hợp có thể dùng converter tự động, không cần đặt `@Convert` cho từng field.

**Nhưng autoApply không hợp pháp hóa các thuộc tính bị loại trừ.** Converter tự động không được dựa vào để ánh xạ:

- `@Id` hoặc `@EmbeddedId`.
- `@Version`.
- Quan hệ entity.
- Thuộc tính có `@Enumerated`.
- Thuộc tính có `@Temporal`.

Nếu codebase dùng type domain giống nhau cho nhiều vai trò, phải xét từng nơi sử dụng. Ví dụ một `CustomerCode` có thể là **basic non-ID attribute** tại bảng log nhập liệu nhưng lại là **ID attribute** trong entity khách hàng; converter chỉ có thể được kỳ vọng hoạt động theo chuẩn ở vị trí đủ điều kiện.

### 9.1. Ưu tiên converter tường minh và vô hiệu hóa tự động

Khi có một converter tự động cho `EmailAddress`, có thể vô hiệu hóa tại một thuộc tính basic:

```java
@Convert(disableConversion = true)
private EmailAddress rawEmail;
```

Tuy nhiên, vô hiệu hóa converter có nghĩa provider phải còn một mapping basic hợp lệ cho **kiểu `EmailAddress`**. Nếu đó là một kiểu Java tùy biến mà provider không biết lưu, việc tắt converter không tự sinh mapping thay thế. Do đó `disableConversion = true` chỉ thích hợp khi có phương án lưu trữ khác được xác định rõ.

Có thể chọn converter tường minh:

```java
@Convert(converter = EmailAddressConverter.class)
private EmailAddress email;
```

Cấu hình tường minh giúp người đọc code biết chính xác cách attribute được chuyển đổi, đặc biệt khi có nhiều converter cho cùng kiểu domain.

### 9.2. Một converter không nên giấu nhiều hành vi khác nhau

Giả sử converter cho `String` chuyển mọi chuỗi thành chữ in hoa và được đặt `autoApply = true`. Tác động có thể lan sang hàng trăm thuộc tính như tên riêng, mã API, token hoặc văn bản người dùng. Điều này dễ làm sai ngữ nghĩa dữ liệu.

Nên ưu tiên **type domain chuyên biệt** (`EmailAddress`, `CurrencyCode`, `CountryCode`) hoặc `@Convert` tường minh cho các chuyển đổi có ý nghĩa nghiệp vụ rõ ràng.

## 10. Quy tắc chuyển đổi phải nhất quán với vòng đời JPA

### 10.1. Không giả định mỗi transaction gọi converter đúng một lần

Converter có thể được JPA provider gọi trong các thời điểm như:

- Hydrate dữ liệu từ kết quả truy vấn.
- Chuẩn bị giá trị ghi xuống database.
- Đồng bộ trạng thái managed entity.
- Bind tham số JPQL hoặc Criteria cho thuộc tính mapped.
- Các thao tác nội bộ khác tùy provider và chiến lược dirty checking.

Không nên dựa vào **số lần gọi hoặc thứ tự gọi cụ thể** của converter để thực hiện nghiệp vụ.

Ví dụ cần tránh:

```java
@Override
public String convertToDatabaseColumn(EmailAddress value) {
    auditService.recordEmailChanged(value); // Tác dụng phụ nguy hiểm.
    return value == null ? null : value.value();
}
```

Converter không phải điểm mở rộng cho audit event, gửi email hoặc gọi HTTP service. Việc JPA gọi converter trong flush, load hay xử lý query không đồng nghĩa người dùng thực sự vừa thực hiện hành động nghiệp vụ “thay đổi email”.

Nếu cần audit hoặc domain event, hãy dùng cơ chế service/domain event hoặc lifecycle/callback có kiểm soát theo yêu cầu.

### 10.2. Chuyển đổi nên giữ ý nghĩa round trip

Với một giá trị hợp lệ `x`:

```text
X domain
   |
   | convertToDatabaseColumn(x)
   v
Y database representation
   |
   | convertToEntityAttribute(y)
   v
X' domain
```

Mong muốn chung là `X'` có **cùng ý nghĩa nghiệp vụ** với `x`. Không nhất thiết phải là cùng Java instance, nhưng nên có equality hoặc tính tương đương được định nghĩa rõ.

Ví dụ converter làm tròn tiền:

```java
@Override
public BigDecimal convertToDatabaseColumn(MoneyAmount value) {
    return value.amount().setScale(0, RoundingMode.HALF_UP);
}
```

Nếu phần lẻ có ý nghĩa, chuyển đổi này làm mất thông tin. Hãy xác định quy định độ chính xác, độ dài, timezone, charset và biểu diễn null trước khi chọn converter.

### 10.3. Converter phải xử lý null rõ ràng

Hai phương thức nhận giá trị có thể null trong thực tiễn. Ví dụ:

```java
@Override
public String convertToDatabaseColumn(EmailAddress value) {
    return value == null ? null : value.value();
}

@Override
public EmailAddress convertToEntityAttribute(String value) {
    return value == null ? null : new EmailAddress(value);
}
```

Đừng dựa vào giả định provider sẽ luôn hoặc sẽ không gọi converter với null. Việc quy đổi null thành một “giá trị mặc định” cũng cần cân nhắc kỹ vì có thể làm mất sự khác biệt giữa “chưa có dữ liệu” và “đã có một giá trị hợp lệ”.

### 10.4. Exception khi chuyển đổi dữ liệu lịch sử

Nếu database đã có mã enum cũ hoặc giá trị không hợp lệ, `convertToEntityAttribute` có thể ném exception khi tải entity:

```java
throw new IllegalArgumentException("Mã không được hỗ trợ: " + code);
```

Kết quả có thể làm truy vấn thất bại. Khi thay đổi representation hoặc thêm converter mới, cần kế hoạch migration dữ liệu lịch sử, hoặc chiến lược đọc tương thích với các mã cũ theo yêu cầu nghiệp vụ.

### 10.5. `equals` và dirty checking

Value object bất biến và có `equals`/`hashCode` theo thành phần thường dễ làm việc với persistence hơn kiểu mutable phức tạp. Nếu type domain bị thay đổi bên trong mà entity không nhận ra, provider có thể cần snapshot hoặc cơ chế mutability riêng để nhận biết dirty state.

`AttributeConverter` **không giải quyết mọi vấn đề mutable type và dirty checking**. Khi xử lý JSON object, collection tùy biến hoặc byte array, cần kiểm tra cơ chế snapshot/mutability của provider; ưu tiên tạo giá trị mới và gán lại thuộc tính khi đó phù hợp với domain.

## 11. JPQL, Criteria và native SQL: converter nằm ở đâu?

### 11.1. JPQL làm việc với thuộc tính Java mapped

Giả sử `Payment.status` là enum basic với `PaymentStatusConverter`:

```java
List<Payment> results = entityManager
    .createQuery(
        "select p from Payment p where p.status = :status",
        Payment.class
    )
    .setParameter("status", PaymentStatus.SETTLED)
    .getResultList();
```

Ở đây `p.status` có mapping converter. JPA provider có thể chuyển tham số `PaymentStatus.SETTLED` thành representation cột, ví dụ `"S"`, vì tham số gắn với persistent attribute được ánh xạ.

### 11.2. Native SQL không tự có đầy đủ ngữ cảnh mapped attribute

Với câu SQL nguyên bản:

```java
List<?> rows = entityManager.createNativeQuery(
    "select id from payment where payment_status = :code"
)
.setParameter("code", "S")
.getResultList();
```

Ở đây nên bind giá trị phù hợp với cột SQL thực tế. Không mặc định rằng một native SQL parameter dùng tên `:status` sẽ được JPA tự suy ra converter nào cần chạy, vì truy vấn native có thể không gắn tham số với thuộc tính JPA nào.

Nếu cần mapping kết quả native SQL vào domain value object, có thể phải thiết lập result mapping hoặc chuyển đổi tại tầng ứng dụng theo cơ chế được provider hỗ trợ.

### 11.3. Converter không thay thế validation và constraint

Một converter có thể chuẩn hóa mã khi ghi, nhưng không thay thế:

- Unique constraint và foreign key ở database.
- Kiểm tra quyền truy cập và business rule.
- Check constraint về miền giá trị.
- Quản lý transaction.
- Migration schema và dữ liệu lịch sử.

Đặc biệt đối với ID và version, không có converter nào thay được cơ chế identity/locking của JPA.

## 12. Ví dụ đầy đủ: các mapping đúng và sai trong cùng miền nghiệp vụ

Giả sử ứng dụng thanh toán có:

- ID do database cấp.
- Phiên bản phục vụ optimistic locking.
- Quan hệ tới khách hàng.
- Trạng thái thanh toán dùng mã một ký tự.
- Mã đối tác bên ngoài dưới dạng value object.
- Thời điểm tạo.
- Ghi chú văn bản dài.

Một entity đề xuất:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Version;
import java.time.Instant;

@Entity
public class Payment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Convert(converter = PaymentStatusConverter.class)
    @Column(name = "status_code", nullable = false, length = 1)
    private PaymentStatus status;

    @Convert(converter = PartnerCodeConverter.class)
    @Column(name = "partner_code", length = 40)
    private PartnerCode partnerCode;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Lob
    @Column(name = "note")
    private String note;

    protected Payment() {
    }

    // Constructor và phương thức nghiệp vụ được bổ sung theo nhu cầu.
}
```

Giả định `PartnerCode` là value object và `PartnerCodeConverter` chuyển nó về `String`. Converter này dùng được vì `partnerCode` là **basic attribute thông thường**, không phải ID hoặc association.

Sơ đồ:

```text
                      Payment entity
                            |
      +---------------------+----------------------+
      |                     |                      |
   @Id Long id         @Version Long         @ManyToOne Customer
      |                     |                      |
      v                     v                      v
 Identity mapping     Version mapping        Association / FK
      |                     |                      |
      +---------------------+----------------------+
                            |
              Basic attributes còn lại
                 /                     \
                v                       v
     PaymentStatus + @Convert    PartnerCode + @Convert
                |                       |
                v                       v
             String "S"             String "PARTNER-42"
                \                       /
                 +---------------------+
                            |
                            v
                 SQL columns trong payment
```

Bảng quyết định:

| Thuộc tính | Annotation | Converter? | Lý do |
|---|---|---|---|
| `id` | `@Id` | **Không** | ID do JPA quản lý |
| `version` | `@Version` | **Không** | Optimistic locking |
| `customer` | `@ManyToOne` | **Không** | Association mapping |
| `status` | `@Convert`, không có `@Enumerated` | **Có** | Enum mã hóa bằng code domain |
| `partnerCode` | `@Convert` | **Có** | Custom basic value |
| `createdAt` | Basic `Instant` | Thường **không cần** | Có basic mapping cho kiểu thời gian |
| `note` | `@Lob` `String` | **Không cần** | LOB ký tự không yêu cầu value converter |

Điều quan trọng là **kiểu Java tùy biến không đồng nghĩa bắt buộc dùng converter**, và **có converter không đồng nghĩa dùng được ở mọi vị trí của entity**.

## 13. Trường hợp ngoại lệ phụ thuộc Hibernate hoặc provider

Hibernate, EclipseLink hoặc các JPA provider khác có thể hỗ trợ kiểu ánh xạ vượt ra ngoài phạm vi chuẩn. Ví dụ, một provider có thể cho phép chuyển đổi trên ID hoặc cung cấp custom type cho enum, JSON, array hay khóa chuyên biệt.

Khi quyết định dùng tiện ích như vậy, cần phân biệt ba mức:

| Mức | Ví dụ | Hệ quả |
|---|---|---|
| **JPA chuẩn** | Converter trên basic field `EmailAddress` | Khả năng portable cao hơn giữa provider |
| **JPA chuẩn + cấu hình DB/dialect** | Converter `EmailAddress -> String` với độ dài cột phù hợp | Logic converter portable, schema vẫn phụ thuộc DB |
| **Provider extension** | Custom Hibernate type, annotation SQL/JDBC đặc thù, converter trên vị trí chuẩn không bảo đảm | Phụ thuộc provider, phiên bản và driver |

Có thể dùng provider extension khi lợi ích đủ lớn, nhưng khi đó cần ghi nhận:

1. Phiên bản provider và dialect đang sử dụng.
2. Kiểu SQL/JDBC thực tế được bind và đọc.
3. Hành vi với query parameter, find, merge, cache, dirty checking.
4. Tương thích schema, migration và dữ liệu đã có.
5. Hành vi trong optimistic locking hoặc khóa ghép nếu liên quan.

Việc một đoạn code “chạy được trên Hibernate hiện tại” không tự chứng minh nó là yêu cầu portable của Jakarta Persistence. Bài học này ưu tiên quy tắc chuẩn, đồng thời cho phép lựa chọn mở rộng **có chủ đích** khi kiến trúc yêu cầu.

## 14. Các sai lầm thường gặp và cách sửa

### Sai lầm 1: Dùng `@Convert` trên ID vì ID là value object

```java
@Id
@Convert(converter = CustomerIdConverter.class)
private CustomerId id;
```

**Vấn đề:** ID thuộc nhóm không được converter bảo đảm theo chuẩn.

**Sửa:** dùng kiểu persistent ID hợp lệ như `Long` hoặc `String`; chuyển giữa ID persistent và domain wrapper ở service/mapper hoặc dùng thiết kế provider-specific được kiểm soát rõ.

### Sai lầm 2: Converter mã phiên bản thay `@Version`

```java
@Version
@Convert(converter = RevisionConverter.class)
private Revision revision;
```

**Vấn đề:** `@Version` do provider quản lý, không hỗ trợ tùy biến kiểu bằng converter portable.

**Sửa:** dùng kiểu version được hỗ trợ, ví dụ `Long`, và chuyển sang DTO/domain representation riêng khi cần.

### Sai lầm 3: Dùng converter cho `@ManyToOne`

```java
@ManyToOne
@Convert(converter = CustomerConverter.class)
private Customer customer;
```

**Vấn đề:** Association không phải basic attribute.

**Sửa:** ánh xạ bằng `@JoinColumn`, `@JoinTable` và annotation quan hệ phù hợp; chỉ dùng converter cho mã tham chiếu nếu đó thực sự là basic value.

### Sai lầm 4: Vừa `@Enumerated` vừa converter enum

```java
@Enumerated(EnumType.STRING)
@Convert(converter = StatusConverter.class)
private Status status;
```

**Vấn đề:** Hai chiến lược enum cạnh tranh; không portable.

**Sửa:** chọn `@Enumerated` hoặc converter, không dùng đồng thời.

### Sai lầm 5: Vừa `@Temporal` vừa converter tùy ý

```java
@Temporal(TemporalType.DATE)
@Convert(converter = CustomDateConverter.class)
private java.util.Date date;
```

**Vấn đề:** Property có temporal mapping riêng.

**Sửa:** chọn mô hình thời gian Java phù hợp; nếu cần value object tùy biến, dùng basic field không có `@Temporal` và converter hợp lệ.

### Sai lầm 6: Giả định mọi field bên trong `@EmbeddedId` là field giá trị bình thường

```java
@Embeddable
class OrderId {
    @Convert(converter = OrderNumberConverter.class)
    private OrderNumber number;
}

@EmbeddedId
private OrderId id;
```

**Vấn đề:** Mapping khóa ghép vẫn thuộc vùng định danh. Không thể lấy quy tắc của embeddable phi-ID áp dụng tự động cho ID.

**Sửa:** dùng các thành phần khóa có mapping ID được provider/JPA hỗ trợ, hoặc xác minh rõ phần mở rộng nếu muốn dùng kiểu đặc biệt.

### Sai lầm 7: Dùng converter như một công cụ chọn SQL type

```java
// X -> String không có nghĩa cột sẽ là JSONB hoặc CLOB.
@Convert(converter = ObjectToJsonStringConverter.class)
private Preferences preferences;
```

**Vấn đề:** Converter chỉ chuyển kiểu Java; SQL type có thể vẫn là loại text thông thường.

**Sửa:** dùng mapping schema/JDBC phù hợp với loại SQL mong muốn, có thể cần provider extension cho JSON native.

### Sai lầm 8: Cho rằng `autoApply = true` áp dụng cả vào ID và version

**Vấn đề:** autoApply vẫn chịu các quy tắc loại trừ của converter.

**Sửa:** tổ chức domain type và mapping rõ ràng, chọn kiểu JPA được hỗ trợ ở ID/version, chỉ dựa vào autoApply cho các basic attribute hợp lệ.

### Sai lầm 9: Trộn converter với mã hóa có trạng thái

Một converter mã hóa dùng IV ngẫu nhiên hoặc lấy key từ service bất kỳ có thể tạo dữ liệu khác nhau cho cùng domain value, ảnh hưởng tìm kiếm theo equality, so sánh snapshot, khóa, cache hoặc migration key. Nếu cần encryption at rest, nên thiết kế riêng mô hình lưu, key rotation và cách truy vấn. Converter không tự giải quyết tất cả yêu cầu mật mã và bảo mật.

### Sai lầm 10: Dùng converter để thay business validation

Converter có thể từ chối representation không hợp lệ khi đọc, nhưng giá trị đầu vào vẫn cần được kiểm tra ở ranh giới nghiệp vụ; database vẫn cần constraint phù hợp. Không nên để lần load đầu tiên từ bảng mới phát hiện một giá trị không hợp lệ mà ứng dụng có thể chặn từ trước.

## 15. Tình huống thực hành

### Bài tập 1: Xác định thuộc tính đủ điều kiện

Xem lớp:

```java
@Entity
public class Device {

    @Id
    private String serialNo;

    @Version
    private Long version;

    @Enumerated(EnumType.STRING)
    private DeviceState state;

    @ManyToOne
    private Warehouse warehouse;

    private FirmwareCode firmwareCode;

    protected Device() {
    }
}
```

**Yêu cầu:** Thuộc tính nào thích hợp để áp dụng `AttributeConverter`?

**Gợi ý trả lời:**

- `serialNo`: không, vì là ID.
- `version`: không, vì là `@Version`.
- `state`: không đồng thời với `@Enumerated`; có thể chọn bỏ `@Enumerated` rồi dùng converter nếu muốn mã domain riêng.
- `warehouse`: không, vì là association.
- `firmwareCode`: **có**, nếu là basic value type đủ điều kiện và có converter thích hợp.

### Bài tập 2: Đổi representation của enum

Một bảng đang lưu mã `"N"` và `"D"` cho trạng thái giao hàng, nhưng enum Java có tên `NEW` và `DELIVERED`.

**Yêu cầu:** Có thể viết `@Enumerated(EnumType.STRING)` để đọc được dữ liệu cũ không?

**Gợi ý trả lời:** Không, nếu dữ liệu cũ là mã rút gọn khác tên enum. Hãy chọn converter enum X↔String (không gắn `@Enumerated`), hoặc migration dữ liệu sang tên enum nếu muốn dùng `EnumType.STRING`.

### Bài tập 3: Dùng value object cho ID nhưng vẫn portable

Domain mong muốn `InvoiceId` là một record bọc `Long`, trong khi repository JPA muốn dùng `EntityManager.find`.

**Yêu cầu:** Thiết kế một cách nhận ID từ API và truy vấn entity.

**Gợi ý trả lời:** Định nghĩa `InvoiceId(Long value)` trong domain/API, để entity JPA giữ `@Id Long id`. Repository chuyển `invoiceId.value()` khi gọi `find`. Tránh đặt converter trên `@Id`.

### Bài tập 4: Dữ liệu embedded khác embedded ID

Entity `Person` có `@Embedded Address`, trong đó `postalCode` là value object `PostalCode`. Entity `OrderLine` có `@EmbeddedId OrderLineId`, trong đó khóa có thành phần `OrderNumber`.

**Yêu cầu:** Hai converter cho `PostalCode` và `OrderNumber` có cùng mức hỗ trợ không?

**Gợi ý trả lời:** Không. Converter trên basic field `Address.postalCode` là trường hợp thông thường trong embeddable phi-ID. Thành phần của `@EmbeddedId` thuộc mapping khóa và không nên dựa vào converter portable.

### Bài tập 5: JPQL và native SQL

Một field `Payment.status` dùng converter để lưu enum `SETTLED` thành mã `"S"`.

**Yêu cầu:** Phân biệt tham số cho hai truy vấn:

```java
// JPQL
"select p from Payment p where p.status = :status"

// Native SQL
"select id from payment where status_code = :statusCode"
```

**Gợi ý trả lời:** Trong JPQL, tham số `:status` gắn với attribute mapped có converter nên truyền giá trị domain enum phù hợp. Trong native SQL, không nên giả định JPA suy ra converter từ tên cột; bind representation SQL phù hợp, ví dụ `"S"`, hoặc dùng result/parameter mapping riêng của provider.

### Bài tập 6: Vì sao autoApply vẫn không cứu được?

Một converter cho `DocumentNumber` được cấu hình `autoApply = true`. Type này xuất hiện ở hai nơi:

```java
@Id
private DocumentNumber number;

private DocumentNumber relatedNumber;
```

**Yêu cầu:** Hai field có tương đương nhau không?

**Gợi ý trả lời:** Không. `number` là ID; converter không được JPA chuẩn bảo đảm. `relatedNumber` là basic field thông thường nên converter có thể áp dụng tự động nếu đủ điều kiện. Cần thiết kế lại mapping ID, không chỉ sửa cờ autoApply.

## 16. Hướng chọn cơ chế ánh xạ

Khi gặp một kiểu Java mới trong entity, có thể dùng chuỗi câu hỏi sau:

```text
Thuộc tính có phải ID (@Id / @EmbeddedId) không?
  |
  +-- Có --> Chọn mapping ID được JPA/provider hỗ trợ.
  |
  +-- Không
       |
       v
   Có phải @Version không?
       |
       +-- Có --> Chọn kiểu version hợp lệ, để provider quản lý.
       |
       +-- Không
            |
            v
       Có phải entity relationship không?
            |
            +-- Có --> Dùng @ManyToOne/@OneToMany/... và join mapping.
            |
            +-- Không
                 |
                 v
            Có @Enumerated hoặc @Temporal không?
                 |
                 +-- Có --> Chọn mapping chuyên biệt,
                 |          hoặc loại annotation chuyên biệt
                 |          trước khi dùng converter phù hợp.
                 |
                 +-- Không
                      |
                      v
                Có phải basic value không?
                      |
                      +-- Có --> Cân nhắc AttributeConverter.
                      |
                      +-- Không --> Xem @Embeddable,
                                   collection mapping,
                                   custom JDBC/provider type.
```

Bảng lựa chọn tổng hợp:

| Mục tiêu | Cơ chế nên ưu tiên |
|---|---|
| Domain value object ↔ chuỗi/số cơ bản | `AttributeConverter<X, Y>` |
| ID auto-generated | `@Id` + `@GeneratedValue` trên kiểu ID được hỗ trợ |
| Domain ID wrapper ↔ JPA ID scalar | Mapping tại service/repository hoặc tách domain/persistence model |
| Kiểm soát xung đột cập nhật | `@Version` + transaction và optimistic locking |
| Quan hệ entity | `@ManyToOne`, `@OneToMany`, `@JoinColumn`, v.v. |
| Enum lưu tên | `@Enumerated(EnumType.STRING)` |
| Enum lưu mã tùy biến | Converter enum trên basic field, không có `@Enumerated` |
| Ngày giờ Java hiện đại | Basic mapping `java.time` phù hợp |
| Value object nhiều thành phần/nhiều cột | `@Embeddable`/`@Embedded` |
| Collection các basic value | `@ElementCollection`, có thể dùng converter trên phần tử |
| Dữ liệu lớn | `@Lob` hoặc storage riêng tùy nhu cầu |
| Kiểu SQL JSON/array/geometry/native | Mapping JDBC/provider/database chuyên biệt khi cần |

## 17. Ghi nhớ khi làm việc với converter

- **`AttributeConverter` dành cho thuộc tính giá trị cơ bản.** Nó là điểm chuyển đổi X↔Y, không thay thế toàn bộ ORM mapping.
- **Định danh và phiên bản có hợp đồng riêng.** Không áp dụng converter lên `@Id`, `@EmbeddedId` hoặc `@Version` rồi mặc định đó là hành vi chuẩn.
- **Quan hệ entity là association mapping.** Không chuyển entity reference thành foreign key bằng converter.
- **`@Enumerated` và `@Temporal` loại trừ converter theo chuẩn.** Muốn converter riêng, hãy chọn chiến lược ánh xạ khác phù hợp và bỏ annotation xung đột.
- **`@Embedded`, `@ElementCollection` và `@Lob` cần phân tích đúng cấp độ.** Basic field bên trong embeddable hoặc basic collection element có thể convert; toàn bộ object nhúng, khóa ghép hoặc SQL type đặc thù là câu chuyện khác.
- **`autoApply` không làm mất giới hạn**, còn `@Convert(disableConversion = true)` không tạo ra mapping thay thế cho một kiểu Java chưa được JPA hỗ trợ.
- **Converter nên thuần túy, nhất quán và không có side effect.** Tránh phụ thuộc số lần gọi, transaction, kết nối mạng hoặc dữ liệu bên ngoài.
- **Có thể dùng extension của provider khi thực sự cần**, nhưng khi đó phải quản lý rõ sự phụ thuộc vào phiên bản, dialect, JDBC và chiến lược migration.

Khi nhìn thấy một `@Convert` trong entity JPA, hãy xác định trước **thuộc tính đó thuộc nhóm basic value hay thuộc mapping đặc biệt**. Từ câu hỏi này, bạn sẽ biết nên tiếp tục dùng converter, chuyển sang annotation chuẩn khác, hay cần một cơ chế persistence chuyên biệt hơn.
