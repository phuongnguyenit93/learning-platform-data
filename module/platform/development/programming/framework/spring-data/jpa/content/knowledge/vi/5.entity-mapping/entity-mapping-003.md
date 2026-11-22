# Chọn truy cập theo trường hoặc thuộc tính bằng @Access

## Mục tiêu

Sau bài này, bạn có thể phân biệt hai chiến lược truy cập của JPA là `FIELD` và `PROPERTY`; xác định cách JPA chọn chiến lược mặc định; dùng `@Access` để khai báo rõ ràng hoặc ghi đè ở từng thuộc tính; áp dụng an toàn với entity kế thừa và embeddable; đồng thời tránh lỗi ánh xạ trùng lặp hoặc hành vi getter/setter ngoài dự kiến.

## 1. Access type quyết định điều gì?

Một entity Java có thể lưu trạng thái trong các field và cung cấp getter/setter để đọc, thay đổi trạng thái đó. JPA cần biết nó sẽ đọc và ghi trạng thái persistent ở đâu. Quyết định này được gọi là **access type**.

Jakarta Persistence có hai giá trị trong enum `AccessType`:

- `AccessType.FIELD`: provider truy cập trực tiếp các field persistent của lớp.
- `AccessType.PROPERTY`: provider truy cập các thuộc tính Java thông qua getter và setter theo quy ước JavaBeans.

`@Access` là annotation dùng để chỉ định chiến lược này. Nó thuộc package `jakarta.persistence` trong Spring Boot 3 trở lên:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
```

Access type điều khiển cách JPA đọc/ghi trạng thái object. Nó không quyết định database nào được dùng, không thay đổi bản chất SQL và cũng không phải quyền truy cập `public`/`private` của Java. Ví dụ, JPA vẫn có thể ánh xạ một field `private` khi dùng field access.

## 2. JPA xác định chiến lược mặc định như thế nào?

Nếu entity không khai báo `@Access` ở cấp lớp, JPA xác định chiến lược mặc định dựa trên vị trí khai báo annotation định danh:

- `@Id` hoặc `@EmbeddedId` nằm trên field: mặc định là `FIELD`.
- `@Id` hoặc `@EmbeddedId` nằm trên getter: mặc định là `PROPERTY`.

Ví dụ, cách đặt `@Id` sau đây chọn field access:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String email;
}
```

Ngược lại, đặt `@Id` trên getter chọn property access:

```java
@Entity
public class Customer {
    private Long id;
    private String email;

    @Id
    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
    public void setEmail(String email) {
        this.email = email;
    }
}
```

Vị trí của `@Id`/`@EmbeddedId` là dấu hiệu quan trọng để suy ra access type. Đừng đặt annotation mapping của một số thuộc tính trên field và một số thuộc tính khác trên getter một cách tùy ý. Nếu cách đặt annotation không nhất quán và không có `@Access` chỉ rõ chiến lược, hành vi ánh xạ có thể không xác định theo đặc tả.

Trong code thực tế, nên khai báo `@Access` tường minh ở cấp lớp khi muốn người đọc thấy ngay quy ước của entity. Điều này đặc biệt hữu ích khi entity có nhiều thuộc tính, kế thừa hoặc cần trộn hai cách truy cập.

## 3. Field access: JPA làm việc trực tiếp với field

Khi dùng `FIELD`, các annotation mapping được đặt trên field. Provider đọc và ghi field trực tiếp, kể cả khi field là `private`; getter/setter không phải điểm truy cập persistence.

Ví dụ:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@Access(AccessType.FIELD)
public class FieldAccessCustomer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email_address", nullable = false, length = 160)
    private String email;

    protected FieldAccessCustomer() {
        // JPA cần constructor không tham số.
    }

    public FieldAccessCustomer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Trong ví dụ này:

- `@Id`, `@GeneratedValue` và `@Column` được đặt trên field.
- Hibernate đọc/ghi `id` và `email` trực tiếp.
- Các getter/setter vẫn hữu ích cho code nghiệp vụ hoặc serialization, nhưng JPA không cần gọi chúng để đọc/ghi hai thuộc tính này.
- Field có thể là `private`; không cần đổi thành `public` để JPA ánh xạ.

### Ưu điểm và điểm cần chú ý

Field access thường phù hợp khi muốn giữ encapsulation: field ở chế độ private, ứng dụng kiểm soát việc thay đổi qua method nghiệp vụ, còn JPA dùng reflection để đọc/ghi trạng thái.

Tuy nhiên, vì provider truy cập field trực tiếp, nó có thể bỏ qua logic trong setter. Nếu setter có kiểm tra, chuẩn hóa hoặc phát sự kiện, không được giả định những logic đó luôn chạy khi JPA nạp entity. Quy tắc bất biến quan trọng nên được bảo vệ trong constructor hoặc method nghiệp vụ; không nên dựa riêng vào setter để bảo vệ dữ liệu.

## 4. Property access: JPA làm việc qua getter/setter

Khi dùng `PROPERTY`, các annotation mapping được đặt trên getter. JPA gọi getter để lấy giá trị và setter để ghi giá trị khi hydrate entity.

Ví dụ:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "property_customers")
@Access(AccessType.PROPERTY)
public class PropertyAccessCustomer {
    private Long id;
    private String email;

    protected PropertyAccessCustomer() {
        // JPA cần constructor không tham số.
    }

    public PropertyAccessCustomer(String email) {
        this.email = email;
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Column(name = "email_address", nullable = false, length = 160)
    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
```

Trong ví dụ này, `@Id` và `@Column` nằm trên getter. Provider dùng `getId()`, `setId(...)`, `getEmail()` và `setEmail(...)` theo access strategy. Setter của khóa chính có thể để `protected` trong ví dụ vì nó phục vụ việc hydrate entity, không nhất thiết là API công khai cho tầng nghiệp vụ.

### Quy ước JavaBeans

Property access dựa trên tên accessor:

- `getName()` tương ứng với thuộc tính `name`.
- `isActive()` thường dùng cho thuộc tính boolean.
- `setName(String name)` là setter của thuộc tính `name`.

Getter phải trả về kiểu dữ liệu phù hợp và setter phải nhận giá trị cùng kiểu. Hãy dùng tên getter/setter nhất quán để provider nhận diện đúng thuộc tính. Trong code thông thường, nên để getter/setter `public` hoặc `protected` và tránh những accessor có hành vi phụ.

### Ưu điểm và điểm cần chú ý

Property access hữu ích khi muốn provider đi qua accessor, hoặc khi mô hình cần biểu diễn một thuộc tính persistent qua getter/setter. Tuy nhiên, getter/setter trở thành một phần của đường đi persistence.

Getter được JPA gọi khi đọc giá trị và setter được gọi khi nạp giá trị. Vì vậy, getter nên trả về trạng thái ổn định, không truy vấn database, không sửa dữ liệu, không phát side effect và không phụ thuộc vào thứ tự gọi. Setter nên gán trạng thái đơn giản; tránh gọi repository, phát sự kiện nghiệp vụ hoặc thực hiện thao tác có thể gây lỗi giữa quá trình hydrate entity.

## 5. So sánh FIELD và PROPERTY

| Tiêu chí | FIELD | PROPERTY |
| --- | --- | --- |
| Annotation mapping đặt ở đâu? | Trên field | Trên getter |
| Provider đọc trạng thái qua | Field trực tiếp | Getter |
| Provider ghi trạng thái qua | Field trực tiếp | Setter |
| Có cần getter/setter để JPA ánh xạ? | Không | Có accessor phù hợp |
| Logic trong setter có chạy khi hydrate? | Không được gọi chỉ để ghi field | Có, vì provider dùng setter |
| Phù hợp khi | Muốn giữ field private và quản lý thay đổi qua method nghiệp vụ | Muốn persistence đi qua accessor |
| Rủi ro thường gặp | Bỏ qua validation/logic trong setter | Getter/setter có side effect hoặc phụ thuộc thứ tự gọi |

Cả hai chiến lược đều hợp lệ. Hãy chọn theo mô hình domain và giữ nhất quán trong entity. Field access là lựa chọn phổ biến trong nhiều ứng dụng Hibernate vì mapping nằm gần trạng thái dữ liệu; property access vẫn hữu ích khi accessor là giao diện persistence có chủ đích.

## 6. Chỉ định access type tường minh bằng @Access

`@Access` có thể được đặt ở cấp lớp để xác định chiến lược mặc định cho các thuộc tính của lớp:

```java
@Entity
@Access(AccessType.FIELD)
public class Product {
    @Id
    private Long id;

    private String name;
}
```

Ở đây JPA dùng field access cho các thuộc tính persistent của `Product`, bất kể getter có tồn tại hay không.

Đặt ở cấp lớp với property access:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Product {
    private Long id;
    private String name;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Khi đã chọn rõ access type ở cấp lớp, hãy đặt mapping annotation ở đúng vị trí tương ứng. Với `FIELD`, đặt annotation trên field; với `PROPERTY`, đặt annotation trên getter.

## 7. Trộn hai chiến lược cho một thuộc tính

Đôi khi entity có một chiến lược mặc định nhưng một thuộc tính cần dùng cách còn lại. JPA hỗ trợ ghi đè ở cấp thuộc tính bằng `@Access` đặt trên field hoặc getter của thuộc tính đó.

Ví dụ entity mặc định dùng field access, nhưng thuộc tính `displayName` được persistence qua getter/setter:

```java
package com.example.learning.customer;

import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

@Entity
@Table(name = "mixed_access_customers")
@Access(AccessType.FIELD)
public class MixedAccessCustomer {
    @Id
    private Long id;

    @Column(name = "first_name")
    private String firstName;

    @Column(name = "last_name")
    private String lastName;

    @Transient
    private String displayName;

    protected MixedAccessCustomer() {
    }

    @Access(AccessType.PROPERTY)
    @Column(name = "display_name")
    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Trong ví dụ này:

- Mặc định các thuộc tính được ánh xạ qua field.
- `id`, `firstName` và `lastName` dùng field access.
- Field `displayName` được đánh dấu `@Transient` để không bị ánh xạ theo chiến lược FIELD mặc định.
- Getter `getDisplayName()` có `@Access(AccessType.PROPERTY)`, vì vậy thuộc tính `displayName` được ánh xạ qua property access và lưu vào cột `display_name`.
- Setter được provider dùng khi nạp giá trị của thuộc tính này.

Quy tắc quan trọng là ghi đè access phải rõ ràng và chỉ áp dụng cho đúng thuộc tính. Không đặt mapping annotation đồng thời trên field và getter của cùng một thuộc tính nếu không có chủ đích và quy tắc `@Access` tương ứng. Nếu cùng một thuộc tính bị ánh xạ hai lần, provider có thể báo lỗi mapping hoặc tạo metadata không hợp lệ.

### Ví dụ ghi đè theo hướng ngược lại

Entity có thể mặc định property access nhưng một field được ánh xạ trực tiếp:

```java
@Entity
@Access(AccessType.PROPERTY)
public class ExternalReference {
    private Long id;
    private String referenceCode;

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Access(AccessType.FIELD)
    @Column(name = "reference_code")
    private String referenceCode;
}
```

Trong trường hợp này, `id` dùng property access, còn `referenceCode` dùng field access. Không đặt thêm `@Column` cho cùng `referenceCode` trên getter.

Chỉ dùng mixed access khi có lý do cụ thể. Mỗi ngoại lệ làm người đọc phải kiểm tra thêm một quy tắc khi xem mapping, vì vậy một chiến lược thống nhất thường dễ bảo trì hơn.

## 8. @Transient và thuộc tính không được lưu

`@Transient` đánh dấu một thuộc tính không thuộc persistent state. Vị trí đặt annotation phải tương ứng với access strategy của thuộc tính:

- Với field access, đặt `@Transient` trên field.
- Với property access, đặt `@Transient` trên getter.
- Với mixed access, hãy đặt annotation trên member thực sự được chọn làm điểm truy cập của thuộc tính.

Ví dụ field access:

```java
@Entity
@Access(AccessType.FIELD)
public class Person {
    @Id
    private Long id;

    private String firstName;
    private String lastName;

    @Transient
    private String searchLabel;

    public String getSearchLabel() {
        return firstName + " " + lastName;
    }
}
```

`searchLabel` được tính trong ứng dụng và không được lưu thành cột. Một field có modifier Java `transient` cũng không phải persistent field theo quy tắc field access; tuy vậy, `@Transient` thường thể hiện ý định mapping rõ hơn và áp dụng được cho cả property.

Đừng nhầm `@Transient` của JPA với việc một thuộc tính bị bỏ qua trong JSON hoặc một cột database bị đánh dấu nullable. Đây là các cơ chế khác nhau.

## 9. Access type với kế thừa và @MappedSuperclass

Entity có thể kế thừa các thuộc tính persistent từ `@MappedSuperclass`. Các thuộc tính được khai báo ở mapped superclass cũng cần một access strategy rõ ràng.

Ví dụ mapped superclass dùng field access:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    protected Long id;

    public Long getId() {
        return id;
    }
}
```

Entity con:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Entity;

@Entity
@Access(AccessType.FIELD)
public class Invoice extends BaseEntity {
    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }
}
```

Ở đây `id` được khai báo trong mapped superclass và được kế thừa như thuộc tính persistent của entity. Nên khai báo access strategy rõ ràng ở nơi sở hữu thuộc tính, đặc biệt khi hierarchy có nhiều lớp hoặc nhiều nhóm mapping.

Không nên suy luận access type chỉ từ một getter ở lớp con nếu khóa chính được khai báo ở lớp cha. Khi entity hierarchy hoặc mapped superclass có chiến lược khác nhau, hãy xem xét chính xác lớp khai báo thuộc tính và chỉ định `@Access` tường minh để metadata không mơ hồ.

## 10. Access type với @Embeddable

Embeddable không có định danh độc lập như entity. Nó được nhúng vào entity thông qua `@Embedded` hoặc dùng trong cấu trúc khóa nhúng `@EmbeddedId`.

Ví dụ value object `Address` dùng field access:

```java
import jakarta.persistence.Access;
import jakarta.persistence.AccessType;
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
@Access(AccessType.FIELD)
public class Address {
    @Column(name = "street_name")
    private String street;

    @Column(name = "city_name")
    private String city;

    protected Address() {
    }

    public Address(String street, String city) {
        this.street = street;
        this.city = city;
    }

    public String getStreet() {
        return street;
    }

    public String getCity() {
        return city;
    }
}
```

Entity sử dụng value object:

```java
@Entity
@Access(AccessType.FIELD)
public class Supplier {
    @Id
    private Long id;

    @Embedded
    private Address address;

    protected Supplier() {
    }
}
```

Access type mặc định của embeddable thường được suy ra từ context sử dụng, vì vậy nếu cùng một embeddable được dùng ở nhiều entity có access type khác nhau, nên khai báo `@Access` trực tiếp trên embeddable. Việc này giúp cách provider đọc/ghi các field hoặc property của value object luôn rõ ràng, không phụ thuộc vào nơi nó được nhúng.

## 11. Những lỗi thường gặp

| Triệu chứng hoặc cách viết | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đặt `@Id` trên field nhưng `@Column` của thuộc tính khác lại đặt trên getter | Annotation mapping bị trộn giữa FIELD và PROPERTY mà không khai báo override | Chọn một access type ở cấp lớp hoặc dùng `@Access` cho thuộc tính ngoại lệ |
| `@Access(PROPERTY)` nhưng getter/setter không theo quy ước JavaBeans | Provider không nhận diện được persistent property như mong muốn | Dùng `getX`/`isX` và setter `setX` có kiểu tương ứng |
| Setter không chạy khi Hibernate nạp entity | Entity đang dùng FIELD access | Đặt mapping trên getter và chọn PROPERTY nếu cần provider gọi setter; hoặc chuyển invariant vào method nghiệp vụ phù hợp |
| Getter tạo truy vấn hoặc thay đổi trạng thái | Property access gọi getter trong quá trình persistence | Giữ getter đơn giản, không side effect |
| Một thuộc tính xuất hiện hai lần trong metadata | Field và getter cùng bị ánh xạ | Đặt `@Transient` cho member không dùng và khai báo `@Access` đúng member được chọn |
| Entity con không ánh xạ thuộc tính từ lớp cha như mong đợi | Access strategy ở hierarchy không rõ hoặc mapping annotation đặt sai lớp | Kiểm tra lớp khai báo thuộc tính và chỉ định access strategy rõ ràng |
| Embeddable được dùng ở các entity khác access type | Cách truy cập mặc định của embeddable có thể không còn rõ ràng | Đặt `@Access` tường minh trên embeddable |
| Thuộc tính chỉ dùng trong tính toán nhưng lại tạo cột | Thuộc tính vẫn được nhận diện là persistent | Đặt `@Transient` trên member được access strategy chọn |

## 12. Quy trình chọn và kiểm tra access strategy

1. Xác định vị trí `@Id` hoặc `@EmbeddedId` trong entity hierarchy để hiểu mặc định JPA suy ra.
2. Chọn `FIELD` hoặc `PROPERTY` dựa trên cách mô hình muốn provider đọc/ghi trạng thái.
3. Nếu muốn quy ước rõ ràng, khai báo `@Access` ở cấp entity, mapped superclass hoặc embeddable phù hợp.
4. Đặt toàn bộ mapping annotation của thuộc tính ở đúng member: field hoặc getter.
5. Nếu cần một thuộc tính ngoại lệ, dùng `@Access` trên chính field/getter của thuộc tính đó và đánh dấu member còn lại `@Transient` khi cần.
6. Kiểm tra các lớp cha, lớp con và embeddable được tái sử dụng để tránh access type mơ hồ.
7. Viết integration test persist rồi đọc lại entity để xác nhận giá trị được lưu và hydrate đúng.
8. Kiểm tra schema/SQL nếu tên cột hoặc trạng thái entity khác với mong đợi.

## 13. Kiểm tra bằng integration test

Ví dụ test với entity field access trong một ứng dụng Spring Boot đã cấu hình JPA và database kiểm thử:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class FieldAccessCustomerTest {
    @Autowired
    private TestEntityManager entityManager;

    @Test
    void persistsAndLoadsEmail() {
        FieldAccessCustomer customer =
            new FieldAccessCustomer("ada@example.test");

        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        FieldAccessCustomer loaded = entityManager.find(
            FieldAccessCustomer.class, customer.getId()
        );

        assertThat(loaded.getEmail()).isEqualTo("ada@example.test");
    }
}
```

`flush()` buộc provider đồng bộ thay đổi xuống database trong transaction test; `clear()` loại entity khỏi persistence context để lần `find` tiếp theo phải nạp lại từ database. Vì vậy test xác nhận cả quá trình ghi và hydrate, thay vì chỉ đọc lại cùng object đang được quản lý.

Với property access, có thể viết test tương tự cho `PropertyAccessCustomer`. Nếu cần chứng minh setter được gọi khi hydrate, hãy dùng một test có instrumentation phù hợp; không nên đưa side effect vào entity production chỉ để kiểm tra.

## 14. Nên chọn chiến lược nào?

| Tình huống | Lựa chọn gợi ý |
| --- | --- |
| Entity có field private và method nghiệp vụ kiểm soát thay đổi | FIELD |
| Muốn provider đọc/ghi qua JavaBean accessor | PROPERTY |
| Mapping hiện tại đã thống nhất theo field | Tiếp tục FIELD |
| Mapping hiện tại đã thống nhất theo getter | Tiếp tục PROPERTY |
| Một thuộc tính thật sự cần cách truy cập khác | Dùng `@Access` ở cấp thuộc tính, có chủ đích |
| Embeddable được chia sẻ giữa nhiều entity khác access type | Đặt `@Access` tường minh trên embeddable |

Không có chiến lược nào tự động làm entity tốt hơn. Giá trị lớn nhất đến từ tính nhất quán và khả năng dự đoán: người đọc biết JPA lấy dữ liệu từ đâu, logic nào được gọi khi hydrate, và member nào thực sự được ánh xạ.

## Kết luận

`FIELD` khiến JPA đọc/ghi field trực tiếp; `PROPERTY` khiến JPA đi qua getter/setter. Mặc định thường được suy ra từ vị trí `@Id` hoặc `@EmbeddedId`, còn `@Access` cho phép khai báo chiến lược rõ ràng ở cấp lớp hoặc ghi đè có kiểm soát ở từng thuộc tính. Hãy đặt mapping annotation đúng vị trí, tránh ánh xạ trùng field/getter và giữ accessor đơn giản để entity hoạt động ổn định qua persist, flush và hydrate.