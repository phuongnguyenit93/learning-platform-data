# Thiết lập Access nhất quán trong mô hình ánh xạ JPA

Trong Jakarta Persistence (thường gọi là JPA), một **entity** là đối tượng Java có trạng thái được ánh xạ vào cơ sở dữ liệu. Khi quản lý entity, persistence provider cần biết sẽ **đọc và ghi trạng thái thông qua các field hay thông qua các getter/setter**. Quy tắc đó được gọi là **access type** của mô hình ánh xạ.

Chọn access type tưởng như chỉ là quyết định đặt annotation ở đâu, nhưng nó ảnh hưởng trực tiếp đến cách JPA nhận diện thuộc tính được lưu, ánh xạ khóa chính, theo dõi thay đổi, tải quan hệ và hoạt động của getter/setter. Một entity có thể biên dịch thành công mà vẫn ánh xạ sai nếu annotation nằm không đúng vị trí.

Mục tiêu của bài học là thiết lập access nhất quán cho các entity, mapped superclass, embeddable và định danh; nhận biết cách JPA suy ra mặc định; đồng thời sử dụng `@Access` có chủ đích khi cần ngoại lệ.

## 1. Access type là gì?

JPA hỗ trợ hai cách truy cập trạng thái của entity:

- **Field access (`AccessType.FIELD`)**: provider truy cập các field của đối tượng theo metadata ánh xạ, kể cả field `private`. Annotation ánh xạ thường đặt trực tiếp trên field.
- **Property access (`AccessType.PROPERTY`)**: provider truy cập thuộc tính theo các phương thức JavaBeans getter/setter. Annotation ánh xạ thường đặt trên getter.

Ví dụ, cả hai cách dưới đây đều có thể ánh xạ thuộc tính `name` sang cột `product_name` nhưng thông qua các điểm truy cập khác nhau:

~~~text
FIELD access                           PROPERTY access
-----------------------------------    -----------------------------------
@Column(name="product_name")           @Column(name="product_name")
private String name;                   public String getName() { ... }

Provider đọc/ghi field name             Provider đọc/ghi property name
theo cơ chế truy cập field             qua getName()/setName(...)
~~~

**Access type không phải** quyền truy cập database, mức `public/private` của API nghiệp vụ, cũng không phải thuộc tính `FetchType.LAZY/EAGER`. Đây là quy tắc JPA sử dụng để đọc/ghi **trạng thái ánh xạ của đối tượng Java**.

Các annotation chịu ảnh hưởng của vị trí access gồm `@Id`, `@EmbeddedId`, `@Column`, `@Basic`, `@Version`, `@ManyToOne`, `@OneToMany`, `@Embedded`, `@Enumerated`, `@Convert` và nhiều annotation ánh xạ khác.

## 2. JPA xác định access type mặc định như thế nào?

Khi không chỉ định `@Access` tường minh, JPA suy ra cách truy cập từ **vị trí đặt các annotation ánh xạ** trong mô hình, đặc biệt là vị trí `@Id` hoặc `@EmbeddedId`:

~~~java
// @Id ở field -> thường dẫn tới FIELD access.
@Id
private Long id;
~~~

~~~java
// @Id ở getter -> thường dẫn tới PROPERTY access.
@Id
public Long getId() {
    return id;
}
~~~

Trong hệ phân cấp entity, việc suy ra access type còn chịu ảnh hưởng của annotation ánh xạ trên entity và `@MappedSuperclass` cùng hệ phân cấp. **Không nên nghĩ mỗi thuộc tính tự suy ra kiểu truy cập độc lập chỉ từ chỗ đặt `@Column`.** Quy tắc mặc định cần nhất quán trong hệ phân cấp nếu không có khai báo `@Access` rõ ràng.

Đối với mô hình không khai báo `@Access`, việc trộn annotation ánh xạ ở field và getter trong cùng hệ phân cấp có thể dẫn đến **hành vi không được xác định theo đặc tả**. Provider có thể bỏ qua annotation, sinh mapping khác dự kiến hoặc báo lỗi. Không nên dựa vào một implementation cụ thể đang “chạy được” để coi cách trộn đó là hợp lệ.

### Quy tắc thực hành

1. Quyết định một access type thống nhất cho entity hoặc hệ phân cấp.
2. Đặt **`@Id` / `@EmbeddedId` và các annotation ánh xạ khác ở cùng phía** theo access type đã chọn.
3. Khi cần ngoại lệ, sử dụng `@Access` một cách tường minh trên class hoặc thuộc tính.
4. Không đặt cùng một ánh xạ lặp ở cả field và getter.
5. Với mapped superclass và embeddable, làm rõ access type để người đọc và provider không phải suy đoán.

## 3. Thiết lập FIELD access

Ví dụ một entity dùng field access:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "product_name", nullable = false, length = 150)
    private String name;

    @Column(name = "unit_price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    @Transient
    private String displayLabel;

    protected Product() {
        // Constructor không tham số mà JPA cần.
    }

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = newName;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changePrice(BigDecimal newPrice) {
        this.price = newPrice;
    }

    public String getDisplayLabel() {
        return sku + " - " + name;
    }
}
~~~

Vì `@Id` nằm trên field `id`, mô hình này sử dụng field access mặc định. Các annotation `@Column` và `@Version` cũng đặt trên field.

### Provider thao tác với trạng thái ra sao?

- Khi nạp dữ liệu, provider có thể gán giá trị trực tiếp cho field `private`, không bắt buộc đi qua getter/setter nghiệp vụ.
- Các phương thức `rename` hoặc `changePrice` vẫn có thể được ứng dụng sử dụng để bảo đảm bất biến nghiệp vụ.
- Provider có thể nhận biết thay đổi trên entity **managed** thông qua dirty checking và đồng bộ khi flush/commit.
- Không phải tạo getter/setter cho mọi field chỉ để JPA hoạt động với field access.
- Field `displayLabel` được đánh dấu `@Transient`, nên không trở thành thuộc tính lưu trữ; đây chỉ là dữ liệu trình bày tính từ các field được lưu.

Field access không xóa yêu cầu về constructor không tham số phù hợp của entity. Trong ví dụ, `protected Product()` là lựa chọn phù hợp để provider tạo instance. Ngoài ra, việc JPA đọc/ghi trực tiếp không có nghĩa ứng dụng nên tự do thay đổi tất cả field ở mọi tầng; vẫn có thể thiết kế các phương thức nghiệp vụ có kiểm soát.

### Tại sao FIELD access thường được chọn?

Field access cho phép ánh xạ nằm gần trạng thái thực tế của đối tượng. API nghiệp vụ có thể dùng `rename()`, `changePrice()` hoặc các phương thức khác mà không bị buộc phải phơi bày setter công khai cho mọi thuộc tính. Những thay đổi trong triển khai getter thường ít ảnh hưởng hơn đến mapping.

Tuy nhiên, không nên nghĩ field access tự động thực thi kiểm tra trong setter. Vì provider có thể bỏ qua setter, **quy tắc luôn phải đúng đối với dữ liệu** còn cần được bảo đảm ở nơi phù hợp: constructor, phương thức nghiệp vụ, validation, transaction và constraint database.

## 4. Thiết lập PROPERTY access

Trong property access, annotation ánh xạ được đặt trên getter. Ví dụ:

~~~java
package com.example.persistence;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import java.math.BigDecimal;

@Entity
@Table(name = "subscriptions")
@Access(AccessType.PROPERTY)
public class Subscription {

    private Long id;
    private String planCode;
    private BigDecimal monthlyFee;

    protected Subscription() {
    }

    public Subscription(String planCode, BigDecimal monthlyFee) {
        this.planCode = planCode;
        this.monthlyFee = monthlyFee;
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "plan_code", nullable = false, length = 40)
    public String getPlanCode() {
        return planCode;
    }

    protected void setPlanCode(String planCode) {
        this.planCode = planCode;
    }

    @Column(name = "monthly_fee", nullable = false, precision = 12, scale = 2)
    public BigDecimal getMonthlyFee() {
        return monthlyFee;
    }

    protected void setMonthlyFee(BigDecimal monthlyFee) {
        this.monthlyFee = monthlyFee;
    }

    @Transient
    public String getPlanSummary() {
        return planCode + ": " + monthlyFee;
    }

    public void changeFee(BigDecimal newFee) {
        this.monthlyFee = newFee;
    }
}
~~~

Ở đây `@Access(AccessType.PROPERTY)` làm rõ lựa chọn cho class. `@Id` và các annotation `@Column` được đặt ở getter; các field lưu trạng thái không mang annotation ánh xạ.

Theo mô hình JavaBeans, property `planCode` được xác định qua cặp `getPlanCode()` và `setPlanCode(...)`. Với property access, cần cung cấp các accessor phù hợp, thường là getter/setter `public` hoặc `protected` theo yêu cầu của JPA. Setter có thể để `protected` nhằm hạn chế quyền gọi từ mã nghiệp vụ bên ngoài.

### Lưu ý khi viết getter/setter

Property access khiến getter/setter trở thành **một phần của giao thức persistence**, vì thế cần giữ chúng ổn định và dễ dự đoán:

- Tránh truy cập mạng, ghi file, phát sự kiện hoặc làm việc tốn kém trong getter/setter của thuộc tính persistent.
- Tránh làm thay đổi dữ liệu khác trong getter (chẳng hạn getter tự tăng bộ đếm hoặc tự cập nhật timestamp).
- Tránh setter từ chối giá trị hợp lệ mà provider cần đặt khi nạp trạng thái, trừ khi quy tắc đó được thiết kế cẩn thận.
- Không biến getter của thuộc tính persistent thành giá trị tính toán bất định mỗi lần được gọi.
- Đánh dấu thuộc tính chỉ để hiển thị bằng `@Transient` trên **getter** khi muốn loại khỏi mapping ở chế độ property access.

Ví dụ với boolean, JavaBeans có thể dùng `isActive()` và `setActive(boolean)`; tên property phải nhất quán với cách nhận diện JavaBeans mà provider hỗ trợ.

## 5. So sánh FIELD và PROPERTY access

| Khía cạnh | `FIELD` | `PROPERTY` |
| --- | --- | --- |
| Annotation ánh xạ | Đặt trên field | Đặt trên getter |
| Vị trí `@Id` mặc định | Trên field | Trên getter |
| Cách provider truy cập | Field trực tiếp theo metadata | Thông qua accessor property |
| Yêu cầu getter/setter persistent | Không bắt buộc chỉ vì mục đích ánh xạ | Cần accessor phù hợp |
| Getter tính toán | Không tự động là persistent nếu không thuộc mapping field | Có thể bị xem là property; `@Transient` nếu cần loại trừ |
| Đóng gói API nghiệp vụ | Dễ dùng phương thức nghiệp vụ thay setter | Accessor trở thành một phần của mapping |
| Rủi ro đặc thù | Không tự chạy logic trong setter | Getter/setter có tác dụng phụ gây khó đoán |
| Dirty checking | Có thể theo dõi entity managed | Có thể theo dõi entity managed |
| SQL/index/transaction | Không do kiểu access tự quyết định | Không do kiểu access tự quyết định |

Không có quy tắc rằng `FIELD` luôn nhanh hơn `PROPERTY` hoặc ngược lại. Chi phí thực tế phụ thuộc provider, bytecode enhancement, mô hình và khối lượng truy vấn. Chọn kiểu truy cập trước hết để đảm bảo **mô hình nhất quán và dễ hiểu**.

## 6. Dùng `@Access` để khai báo tường minh

Annotation chuẩn:

~~~java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;

@Access(AccessType.FIELD)
// hoặc:
@Access(AccessType.PROPERTY)
~~~

`@Access` có thể đặt ở cấp entity, mapped superclass, embeddable hoặc ở cấp thuộc tính trong các trường hợp hỗ trợ. Nó giúp loại bỏ sự mơ hồ của suy luận mặc định.

Ví dụ khai báo trực tiếp:

~~~java
@Entity
@Access(AccessType.FIELD)
public class Invoice {
    @Id
    private Long id;

    @Column(name = "invoice_number", nullable = false)
    private String number;

    protected Invoice() {
    }
}
~~~

Khi đã ghi `@Access(AccessType.FIELD)`, người đọc không cần suy luận từ vị trí `@Id` để biết provider truy cập trạng thái ra sao. Tuy vậy, annotation của các persistent field vẫn phải được đặt ở đúng chỗ; khai báo `@Access` **không sửa hộ annotation đặt sai trên getter**.

### Khi nào nên khai báo `@Access` ở class?

- Hệ thống có entity kế thừa từ mapped superclass; muốn thể hiện quy tắc rõ ngay trên lớp khai báo.
- Mô hình có nhiều contributor hoặc code generation, cần quy ước ít phụ thuộc suy luận.
- Có embeddable được dùng từ nhiều entity với kiểu access khác nhau.
- Cần ngoại lệ từng thuộc tính và muốn chỉ rõ kiểu mặc định còn lại.
- Đang chuyển đổi mô hình cũ và muốn kiểm soát từng bước thay đổi mapping.

Khai báo rõ không thay thế nhu cầu đặt annotation đúng mục tiêu theo `FIELD` hoặc `PROPERTY`.

## 7. Không trộn annotation field/getter một cách ngẫu nhiên

Xét entity dễ gây nhầm lẫn:

~~~java
@Entity
public class WrongProduct {

    @Id
    private Long id;                // Gợi ý FIELD access.

    private String name;

    @Column(name = "product_name") // Sai vị trí theo lựa chọn FIELD.
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    protected WrongProduct() {
    }
}
~~~

Với access mặc định dựa trên field, `name` là field cần xét để ánh xạ. Nhưng `@Column(name = "product_name")` lại được đặt trên getter. Kết quả mong đợi là cột `product_name` có thể **không được áp dụng như ý định**; trộn annotation như vậy không phải một cách ánh xạ di động và tin cậy.

Cách sửa nhất quán theo field access:

~~~java
@Entity
@Access(AccessType.FIELD)
public class Product {

    @Id
    private Long id;

    @Column(name = "product_name")
    private String name;

    protected Product() {
    }

    public String getName() {
        return name;
    }
}
~~~

Hoặc nếu lựa chọn property access thì chuyển `@Id` và các annotation ánh xạ sang getter một cách đồng bộ, đồng thời cung cấp getter/setter tương ứng.

Đặc biệt tránh hai lỗi:

1. **Đặt `@Id` trên field nhưng `@ManyToOne` hoặc `@Column` trên getter** mà không khai báo ngoại lệ đúng cách.
2. **Đánh dấu cùng một thuộc tính persistent ở cả field và getter**, dẫn đến ánh xạ trùng hoặc hành vi khó dự đoán.

Thông báo lỗi cụ thể có thể khác giữa Hibernate, EclipseLink và các provider khác; không nên thiết kế mapping dựa vào việc một provider tình cờ bỏ qua annotation sai chỗ.

## 8. Ngoại lệ có chủ đích: override access của một thuộc tính

Đôi khi phần lớn entity được ánh xạ qua field nhưng một thuộc tính cần truy cập qua property. Khi đó, sử dụng `@Access` ở đúng thuộc tính và loại bỏ đường ánh xạ mặc định của phần backing state để không ánh xạ hai lần.

Ví dụ entity mặc định dùng field access, nhưng `normalizedCode` được đọc/ghi qua getter/setter:

~~~java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Transient;

@Entity
@Access(AccessType.FIELD)
public class CatalogItem {

    @Id
    private Long id;

    @Column(name = "raw_code")
    private String rawCode;

    // Chỉ là backing field; tránh ánh xạ mặc định theo FIELD.
    @Transient
    private String normalizedCode;

    protected CatalogItem() {
    }

    @Access(AccessType.PROPERTY)
    @Column(name = "normalized_code")
    public String getNormalizedCode() {
        return normalizedCode;
    }

    protected void setNormalizedCode(String normalizedCode) {
        this.normalizedCode = normalizedCode;
    }
}
~~~

Ở ví dụ này:

- Các thuộc tính khác dùng field access của class.
- Getter `getNormalizedCode()` được chỉ định `@Access(AccessType.PROPERTY)` và mang annotation `@Column`.
- Backing field `normalizedCode` mang `@Transient` để không bị ánh xạ tự động theo field access của class.
- Setter tương ứng tồn tại để provider có thể gán lại giá trị khi nạp dữ liệu.

Một chiều override ngược lại cũng có thể xảy ra: entity mặc định `PROPERTY`, nhưng một field có `@Access(AccessType.FIELD)`. Khi đó cần làm rõ rằng getter tương ứng không được JPA tiếp tục ánh xạ như một property độc lập. **Không áp dụng override tùy tiện cho mọi thuộc tính**; mỗi ngoại lệ làm mô hình khó đọc và khó bảo trì hơn.

Trong thực tế, nên ưu tiên cả class có một access type. Override thuộc tính chỉ dùng khi có lý do thực sự rõ ràng như tương thích mã cũ hoặc một thuộc tính có cách truy cập đặc biệt.

## 9. Access type khi dùng `@MappedSuperclass` và kế thừa entity

Một mô hình thường có lớp cha chứa định danh và thông tin kiểm soát phiên bản:

~~~java
package com.example.persistence;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.Version;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private long version;

    public Long getId() {
        return id;
    }
}
~~~

Lớp con:

~~~java
package com.example.persistence;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer extends BaseEntity {

    @Column(name = "full_name", nullable = false)
    private String fullName;

    protected Customer() {
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
~~~

Với mô hình này, metadata mapping ở `BaseEntity` nằm trên field, và `Customer` cũng đặt `@Column` trên field. Các thực thể con thừa hưởng phần định danh đã khai báo ở mapped superclass. Lớp `BaseEntity` bản thân không nhất thiết có bảng riêng vì chỉ được đánh dấu `@MappedSuperclass`.

### Vì sao cần quan tâm toàn bộ hierarchy?

Trong mô hình không khai báo access tường minh, default access được xác định theo vị trí annotation ở hệ phân cấp. Khi một lớp cha dùng `@Id` trên field còn lớp con lại gắn `@Column` ở getter, đây không thể được hiểu như hai kiểu access độc lập mặc định một cách an toàn.

Khi thiết kế hierarchy:

1. Xác định nơi định nghĩa `@Id` hoặc `@EmbeddedId`.
2. Chọn cách truy cập phù hợp cho entity và mapped superclass.
3. Áp dụng thống nhất cho các thuộc tính mapping được khai báo ở các cấp.
4. Nếu một class hoặc một thuộc tính cần kiểu khác, dùng `@Access` tường minh tại vị trí phù hợp, kèm mapping đúng chỗ.

Các chiến lược kế thừa bảng như `SINGLE_TABLE`, `JOINED` hay `TABLE_PER_CLASS` giải quyết câu hỏi **dữ liệu được bố trí vào bảng nào**; chúng khác với câu hỏi **provider truy cập field hay property nào**. Không nên nhầm `@Inheritance` với `@Access`.

## 10. Access type của `@Embeddable` và `@Embedded`

Một **embeddable** đại diện cho nhóm giá trị có thể được nhúng vào entity, ví dụ địa chỉ giao hàng:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    @Column(name = "street")
    private String street;

    @Column(name = "city")
    private String city;

    protected Address() {
    }

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }
}
~~~

~~~java
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class ShippingOrder {

    @Id
    private Long id;

    @Embedded
    private Address shippingAddress;

    protected ShippingOrder() {
    }
}
~~~

Theo quy tắc mặc định của JPA, **embeddable thường kế thừa access type từ entity chứa nó**, trừ khi bản thân embeddable có khai báo access tường minh phù hợp. Vì `ShippingOrder` sử dụng field access, trường hợp trên phù hợp với annotation đặt trên field của `Address`.

Điều gì xảy ra nếu cùng một `Address` được nhúng trong một entity khác dùng property access? Khi muốn tái sử dụng embeddable với ý nghĩa ánh xạ không đổi, nên chỉ rõ:

~~~java
@Embeddable
@Access(AccessType.FIELD)
public class Address {
    @Column(name = "street")
    private String street;

    @Column(name = "city")
    private String city;

    protected Address() {
    }
}
~~~

Nhờ đó, quy tắc truy cập `Address` không phải suy ra theo từng entity sở hữu. Nếu hai entity cần tên cột khác nhau cho cùng embeddable, dùng `@AttributeOverride` / `@AttributeOverrides` tại điểm nhúng; **đổi tên cột** là bài toán khác với **chọn field/property access**.

~~~java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "street",
        column = @Column(name = "billing_street")),
    @AttributeOverride(
        name = "city",
        column = @Column(name = "billing_city"))
})
private Address billingAddress;
~~~

Đoạn trên cần các import tương ứng `jakarta.persistence.AttributeOverride`, `AttributeOverrides`, `Column`, `Embedded` và được đặt trong entity field-access. Tên `street` và `city` là tên thuộc tính của `Address`, còn `billing_street` và `billing_city` là tên cột đích.

## 11. Access type với `@Id`, `@EmbeddedId` và khóa phức hợp

Định danh là điểm đặc biệt quan trọng vì JPA cần nhận diện entity và quản lý danh tính trong persistence context.

### 11.1. Khóa đơn

Với khóa đơn:

~~~java
@Entity
@Access(AccessType.FIELD)
public class Department {
    @Id
    private Long id;

    private String name;

    protected Department() {
    }
}
~~~

`@Id` nằm trên field, phù hợp kiểu truy cập đã khai báo. Nếu chọn property access thì `@Id` phải nằm trên getter `getId()`. Không nên chỉ di chuyển `@Id` rồi để lại các annotation khác ở field theo kiểu cũ.

### 11.2. Khóa phức hợp với `@EmbeddedId`

Ví dụ một dòng đơn hàng được nhận diện bằng `orderId` và `lineNumber`:

~~~java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
@Access(AccessType.FIELD)
public class OrderLineId implements Serializable {

    @Column(name = "order_id")
    private Long orderId;

    @Column(name = "line_number")
    private Integer lineNumber;

    protected OrderLineId() {
    }

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderLineId)) {
            return false;
        }
        OrderLineId that = (OrderLineId) other;
        return Objects.equals(orderId, that.orderId)
            && Objects.equals(lineNumber, that.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
~~~

Entity sử dụng khóa phức hợp:

~~~java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "order_lines")
@Access(AccessType.FIELD)
public class OrderLine {

    @EmbeddedId
    private OrderLineId id;

    private int quantity;

    protected OrderLine() {
    }

    public OrderLine(OrderLineId id, int quantity) {
        this.id = id;
        this.quantity = quantity;
    }

    public OrderLineId getId() {
        return id;
    }
}
~~~

`@EmbeddedId` được đặt trên field vì `OrderLine` dùng field access. `OrderLineId` có `@Access(FIELD)` độc lập để cách ánh xạ thành phần khóa rõ ràng, ngay cả khi tái sử dụng trong ngữ cảnh khác. Khóa phức hợp cần tuân thủ các yêu cầu của kiểu primary key, trong đó có định nghĩa `equals` / `hashCode` phù hợp với giá trị khóa.

### 11.3. `@IdClass`

Với `@IdClass`, entity khai báo các thuộc tính khóa bằng `@Id`, và lớp khóa khai báo các thành phần tương ứng theo tên/kiểu theo quy tắc của đặc tả. Dù dùng `@IdClass` hay `@EmbeddedId`, **access type của các thuộc tính định danh trên entity vẫn phải nhất quán với cách ánh xạ đã chọn**.

Ví dụ ở entity field-access:

~~~java
@Entity
@IdClass(EnrollmentId.class)
@Access(AccessType.FIELD)
public class Enrollment {
    @Id
    private Long studentId;

    @Id
    private Long courseId;

    protected Enrollment() {
    }
}
~~~

Đây là đoạn minh họa mapping; muốn sử dụng được cần định nghĩa `EnrollmentId` với các thuộc tính tương ứng, constructor phù hợp và `equals` / `hashCode` theo yêu cầu khóa phức hợp. Việc chọn `@IdClass` hay `@EmbeddedId` phụ thuộc thiết kế định danh, không phải một giải pháp để né quy tắc access type.

## 12. Quan hệ entity cũng phải nhất quán theo access

Không chỉ `@Column`, annotation quan hệ cũng thuộc metadata persistence. Với field access:

~~~java
@Entity
@Access(AccessType.FIELD)
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }
}
~~~

`@ManyToOne` và `@JoinColumn` đặt trên **field** `customer`. Trong property access, chúng sẽ đặt trên **getter** `getCustomer()` và provider sử dụng cặp accessor tương ứng.

Các lựa chọn như `FetchType.LAZY`, cascade, owning side và `mappedBy` là **ngữ nghĩa quan hệ**, không quyết định class đang dùng field hay property access. Tuy nhiên, nếu annotation quan hệ đặt sai phía, provider có thể không hiểu quan hệ đúng như ý định.

Một mô hình có hai entity liên quan **có thể** chọn hai access type khác nhau nếu mỗi entity được cấu hình rõ ràng và nhất quán trong phạm vi của nó. Không có yêu cầu mọi entity của toàn bộ ứng dụng phải dùng một kiểu duy nhất. Dù vậy, một quy ước chung trong nhóm dự án thường giúp giảm lỗi.

## 13. `@Transient`, `transient`, `static` và thuộc tính tính toán

Điều quan trọng khi thiết lập access là nhận diện chính xác **thuộc tính nào JPA phải lưu**.

### Trong FIELD access

Các field instance phù hợp có thể là persistent field; field `static` hoặc `transient` của Java không được xử lý như trạng thái persistent thông thường. Có thể dùng `@Transient` để loại trừ field khỏi mapping.

~~~java
@Entity
@Access(AccessType.FIELD)
public class Report {
    @Id
    private Long id;

    private String title;               // Persistent.

    @Transient
    private String displayOnlyNote;     // Không persistent.

    private transient String tempToken; // Không persistent.

    private static final String TYPE = "REPORT"; // Không là field instance.

    protected Report() {
    }
}
~~~

`transient` là keyword của Java; `@Transient` là annotation của Jakarta Persistence. Chúng có phạm vi ý nghĩa khác nhau: keyword cũng liên quan tới cơ chế Java serialization, còn annotation JPA nói rõ thuộc tính không thuộc ánh xạ persistence.

### Trong PROPERTY access

Getter theo quy ước JavaBeans có thể được xem xét như thuộc tính persistent. Một getter dùng chỉ để tính toán nên được đánh dấu `@Transient` trên chính getter:

~~~java
@Transient
public String getDisplayText() {
    return getCode() + " / " + getName();
}
~~~

Nếu đặt `@Transient` lên backing field nhưng entity đang dùng property access, annotation đó không nhất thiết loại đúng property getter như mong muốn. Luôn áp dụng annotation ở **phía mà access type đang sử dụng**.

## 14. Tương tác với framework, reflection và code generation

### 14.1. Lombok

Lombok có thể sinh getter/setter tự động, nhưng JPA không tự động chuyển sang property access chỉ vì class có `@Getter` hoặc `@Setter`.

~~~java
@Entity
@Access(AccessType.FIELD)
@Getter
public class Category {

    @Id
    private Long id;

    private String name;

    protected Category() {
    }
}
~~~

Đây là ví dụ cú pháp Lombok; nếu dùng cần import annotation của Lombok và dependency tương ứng. Entity vẫn ánh xạ qua field do `@Access(FIELD)`. Không nên sinh `equals`, `hashCode` hoặc `toString` không kiểm soát trên tất cả quan hệ lazy; điều đó dễ gây truy vấn ngoài dự kiến hoặc đệ quy.

### 14.2. Framework serialization

Jackson và các thư viện chuyển object sang JSON có thể dùng getter, field hoặc annotation của riêng chúng. Cấu hình serialization **không quyết định** access type của JPA. Một field được JPA ánh xạ có thể không được hiển thị qua JSON; ngược lại getter tính toán có thể xuất hiện trong JSON nhưng không phải cột database.

Điều này là lý do tốt để tránh dùng entity trực tiếp làm dữ liệu phản hồi API khi cần kiểm soát thông tin và quan hệ được tải. DTO hoặc projection có thể phù hợp hơn.

### 14.3. Proxy và bytecode enhancement

Một số provider sử dụng proxy hoặc bytecode enhancement để tải lười, theo dõi thay đổi và tối ưu truy cập. Điều này có thể tạo yêu cầu hoặc hạn chế riêng về constructor, method final, class final và cách truy cập trạng thái. **Quy tắc chuẩn về FIELD/PROPERTY vẫn là hợp đồng ánh xạ**, nhưng cần tham khảo ràng buộc của provider khi dùng tính năng nâng cao.

Không nên tự suy ra rằng `FIELD` nghĩa là JPA “không bao giờ gọi phương thức”, hoặc `PROPERTY` nghĩa là “mọi getter đều chỉ gọi một lần”. Provider có quyền quản lý entity theo cơ chế phù hợp với đặc tả và thời điểm đồng bộ.

### 14.4. Bean Validation

Annotation kiểm tra như `@NotNull`, `@Size` của Jakarta Validation có cơ chế kiểm tra đối tượng riêng; vị trí annotation validation và cách công cụ validation đọc field/property là một quyết định liên quan nhưng không đồng nhất với JPA access. Cần thiết kế nhất quán, nhất là khi người dùng mong chờ validation áp dụng cho cả dữ liệu nhập và vòng đời persistence.

## 15. Chọn access type theo tình huống

| Tình huống | Lựa chọn thường dễ bảo trì | Lý do |
| --- | --- | --- |
| Entity có nhiều phương thức nghiệp vụ, không muốn setter public | FIELD | Metadata đặt trên trạng thái; không bắt buộc expose setter |
| Mã cũ đã được thiết kế theo JavaBeans và mapping trên getter | PROPERTY | Tránh đảo toàn bộ hợp đồng ánh xạ chỉ để đổi quy ước |
| Nhiều entity kế thừa mapped superclass chứa id | Access tường minh và thống nhất theo hierarchy | Hạn chế nhầm vị trí `@Id` và annotation ở subclass |
| Embeddable tái sử dụng ở nhiều entity | `@Access` tường minh trên embeddable | Không phụ thuộc kiểu access của từng owner |
| Một thuộc tính phải đi qua getter/setter đặc biệt | Override bằng `@Access` cấp thuộc tính | Chủ động ánh xạ ngoại lệ và tránh mapping trùng |
| Entity đơn giản, chưa có yêu cầu đặc biệt | Chọn một quy ước chung rồi nhất quán | Ít bất ngờ khi bảo trì và onboarding |

Không phải toàn bộ ứng dụng bắt buộc có chung một kiểu access. Nhưng **trong cùng một entity/hierarchy, mọi ngoại lệ phải được biểu đạt rõ**. Việc đổi từ FIELD sang PROPERTY về bản chất là thay đổi hợp đồng giữa mô hình Java và provider, không chỉ là thao tác di chuyển annotation để code “đẹp hơn”.

## 16. Chuyển đổi mô hình đang có mà không làm lệch mapping

Giả sử dự án cũ đặt annotation trên getter nhưng muốn chuẩn hóa sang field access. Cách tiếp cận hợp lý:

1. **Xác định access hiện tại.** Tìm nơi đặt `@Id`, `@EmbeddedId` và annotation ánh xạ trong entity, mapped superclass và embeddable liên quan.
2. **Xác định schema mong đợi.** Ghi nhận tên bảng/cột, quan hệ, khóa chính, `@Version`, converter và các thuộc tính không lưu.
3. **Chọn access mới.** Khai báo `@Access(AccessType.FIELD)` hoặc `PROPERTY` rõ ràng nếu có rủi ro suy luận sai.
4. **Di chuyển annotation đúng phía.** Đồng bộ `@Id`, `@Column`, `@JoinColumn`, `@Embedded`, `@Version`...; tránh bỏ sót inherited mapping.
5. **Phân biệt các getter tính toán.** Đánh dấu `@Transient` đúng phía khi cần để không thêm cột ngoài ý muốn.
6. **Xử lý các ngoại lệ.** Với thuộc tính cần giữ kiểu truy cập cũ, dùng `@Access` cấp thuộc tính và tránh ánh xạ backing field/getter hai lần.
7. **Kiểm tra hành vi với cơ sở dữ liệu.** Trong quy trình phát triển, cần xác nhận metadata mapping, kết quả persist/find/update, quan hệ, khóa và sự khớp với schema thật.

Ví dụ một lỗi thường gặp khi chuyển kiểu:

~~~java
// Trước: property access
@Id
public Long getId() {
    return id;
}

@Column(name = "customer_name")
public String getName() {
    return name;
}
~~~

Nếu chỉ chuyển `@Id` lên field nhưng giữ `@Column` ở getter, class có thể không còn ánh xạ như dự kiến. Muốn chuyển sang field access, cả `@Id` và `@Column` phải được đặt trên field tương ứng, cùng các annotation quan hệ/khóa khác.

Lưu ý: thay access type **không nhất thiết yêu cầu đổi schema**, nếu metadata cuối cùng vẫn trỏ tới cùng bảng/cột. Tuy nhiên, việc đổi cách provider đọc/ghi trạng thái có thể ảnh hưởng getter/setter, giá trị tính toán, kiểm tra nghiệp vụ và hành vi các instance cũ. Không nên coi refactor access là thay đổi thuần cú pháp.

## 17. Tình huống minh họa và cách xử lý

### Tình huống A: `@Id` trên field, `@Version` trên getter

~~~java
@Id
private Long id;

private long version;

@Version
public long getVersion() {
    return version;
}
~~~

Với mặc định field access, cách đặt `@Version` trên getter không nhất quán. Cần chuyển `@Version` xuống field, hoặc cấu hình kiểu truy cập tường minh nếu thực sự muốn ngoại lệ. Thiết kế này đặc biệt nhạy cảm vì `@Version` dùng cho optimistic locking; một mapping sai có thể khiến cách kiểm soát đồng thời không đúng dự định.

### Tình huống B: Entity field-access có getter trả về giá trị viết hoa

~~~java
private String code;

public String getCode() {
    return code == null ? null : code.toUpperCase();
}
~~~

Nếu entity dùng `FIELD`, provider lưu trạng thái của field `code`, không mặc định dùng chuỗi đã viết hoa từ getter. Muốn dữ liệu lưu luôn được chuẩn hóa, cần đặt quy tắc chuẩn hóa ở vị trí phù hợp, ví dụ constructor/phương thức cập nhật, converter hoặc cơ chế kiểm tra dữ liệu; không nên giả định getter sẽ được provider gọi để biến đổi dữ liệu.

### Tình huống C: Entity property-access có getter tạo giá trị mới mỗi lần

~~~java
public String getRequestToken() {
    return java.util.UUID.randomUUID().toString();
}
~~~

Nếu getter này được coi là persistent property, provider có thể nhận các giá trị không ổn định và gây hành vi ghi khó hiểu. Nếu chỉ là dữ liệu runtime, dùng `@Transient` trên getter hoặc thiết kế thành phương thức nghiệp vụ không theo quy ước getter của persistent property.

### Tình huống D: Hai entity dùng cùng `Address`, một FIELD và một PROPERTY

Nếu embeddable không khai báo access rõ ràng, quy tắc kế thừa access type từ owner có thể khiến các vị trí annotation trong `Address` không nhất quán. Giải pháp rõ ràng là định nghĩa `@Access(AccessType.FIELD)` hoặc `PROPERTY` ngay trên embeddable và giữ metadata cùng phía.

### Tình huống E: Đặt `@Transient` sai vị trí

Một class dùng `PROPERTY`, có `@Transient` trên backing field nhưng getter `getDisplayText()` không được loại trừ rõ ràng. Không nên kỳ vọng `@Transient` tại field tự động kiểm soát một property được truy cập qua getter. Đặt annotation ở vị trí getter theo kiểu access hiện tại.

## 18. Câu hỏi tự luyện

**1.** Entity có `@Id` trên field và `@Column` trên getter. Đâu là điểm bất nhất?

**Trả lời:** mặc định đang theo field access nhưng metadata của thuộc tính khác được gắn ở phía getter. Cần thống nhất vị trí ánh xạ hoặc khai báo ngoại lệ bằng `@Access` đúng cách.

**2.** Entity sử dụng `@Access(FIELD)` nhưng chỉ có getter, không có setter cho thuộc tính `name`. JPA có nhất thiết phải gọi setter để nạp `name` không?

**Trả lời:** không. Field access cho phép provider thao tác với field theo metadata; tuy nhiên entity vẫn cần đáp ứng các yêu cầu khác của JPA và provider.

**3.** Vì sao mapped superclass chứa `@Id` cần được cân nhắc trước khi lớp con đặt `@Column`?

**Trả lời:** default access có liên quan đến hệ phân cấp ánh xạ. Nếu lớp cha dùng field access thì lớp con không nên tùy ý đặt annotation persistent trên getter mà không có `@Access` tường minh.

**4.** Khi nào nên viết `@Access(AccessType.FIELD)` trên một embeddable?

**Trả lời:** khi muốn quy định rõ cách truy cập, đặc biệt nếu embeddable có thể được dùng trong nhiều entity với access type khác nhau.

**5.** Class dùng `PROPERTY`, có phương thức `getFormattedPrice()` phục vụ giao diện. Làm sao bảo đảm nó không bị JPA coi là thuộc tính lưu trữ?

**Trả lời:** đặt `@Transient` trên getter (hoặc thiết kế phương thức không phải getter persistent) phù hợp với mô hình truy cập đã chọn.

**6.** Đổi `@Id` từ getter sang field có phải luôn là thay đổi vô hại?

**Trả lời:** không. Nó có thể thay đổi default access; phải xem lại toàn bộ annotation ánh xạ trong hệ phân cấp, bao gồm quan hệ, khóa và thuộc tính kế thừa.

## Kết luận

**Thiết lập access nhất quán là điều kiện nền tảng để JPA ánh xạ đúng entity và định danh.** Với `FIELD`, provider làm việc qua field và metadata đặt trên field. Với `PROPERTY`, provider làm việc qua getter/setter và metadata đặt trên getter. Vị trí `@Id`/`@EmbeddedId` là dấu hiệu quan trọng của kiểu truy cập mặc định, nhưng tính nhất quán phải được xem xét trong cả hệ phân cấp.

Hãy chọn một access type rõ ràng cho từng mô hình ánh xạ; áp dụng thống nhất cho id, thuộc tính cơ bản và quan hệ; chỉ dùng `@Access` cấp thuộc tính khi thực sự cần ngoại lệ; và làm rõ access của embeddable được tái sử dụng. Khi JPA thao tác với đúng trạng thái của entity, các phần tiếp theo như dirty checking, khóa lạc quan và quản lý quan hệ mới có cơ sở hoạt động như thiết kế.
