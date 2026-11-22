# Constructor không tham số và khả năng khởi tạo entity

Trong Java thông thường, ta hay tạo đối tượng bằng một constructor có tham số để bảo đảm dữ liệu hợp lệ ngay từ đầu:

```java
Customer customer = new Customer("Nguyễn An", "an@example.com");
```

Nhưng khi lấy dữ liệu từ cơ sở dữ liệu, ứng dụng thường không tự gọi constructor đó:

```java
Customer customer = entityManager.find(Customer.class, 42L);
```

Ở lệnh thứ hai, **JPA provider phải có khả năng tạo một instance của `Customer`**, rồi khôi phục trạng thái từ các cột trong hàng dữ liệu. Đó là lý do entity JPA cần **constructor không tham số** (*no-argument constructor*, thường gọi *no-args constructor*).

Bài học này tập trung vào yêu cầu constructor trong kiến trúc Java Persistence API (JPA, hiện được chuẩn hóa dưới tên **Jakarta Persistence**), cách provider khởi tạo entity, và cách thiết kế entity vừa tương thích JPA vừa giữ được quy tắc nghiệp vụ.

## 1. Vì sao JPA cần tự khởi tạo entity?

Hãy xét bảng `customers`:

| id | full_name | email |
| ---: | --- | --- |
| 42 | Nguyễn An | an@example.com |
| 73 | Trần Bình | binh@example.com |

Ta muốn mỗi hàng được biểu diễn bằng một Java object thuộc class `Customer`.

Khi viết:

```java
Customer customer = entityManager.find(Customer.class, 42L);
```

JPA provider phải kết hợp nhiều việc:

1. Xác định entity cần tải theo class `Customer` và khóa chính `42`.
2. Kiểm tra persistence context xem entity với identity này đã được quản lý chưa.
3. Nếu cần truy vấn, lấy dữ liệu từ database và tạo instance tương ứng.
4. Gán các giá trị của hàng vào các thuộc tính được ánh xạ.
5. Theo dõi instance trong persistence context và thực hiện các callback thích hợp.

Diễn đạt ở mức khái niệm:

```text
Ứng dụng
  │
  │ entityManager.find(Customer.class, 42L)
  ▼
JPA provider
  │
  ├── Kiểm tra persistence context
  │      └── Đã quản lý? → trả về managed instance hiện có
  │
  └── Cần tải từ DB
         │
         ├── SELECT ... FROM customers WHERE id = 42
         ├── Tạo instance Customer
         ├── Khôi phục id, fullName, email
         └── Đưa vào trạng thái managed
                    │
                    ▼
             Customer object
```

Sơ đồ trên là mô hình tư duy, không mô tả bắt buộc thứ tự mọi thao tác nội bộ. Provider có thể dùng reflection, bytecode enhancement, proxy hoặc cách tối ưu khác. **Hợp đồng quan trọng** là class entity phải cung cấp một cách khởi tạo hợp lệ theo chuẩn; ứng dụng không nên phụ thuộc vào thuật toán khởi tạo cụ thể của một provider.

Nếu class chỉ có constructor buộc truyền `fullName` và `email`, provider không có cách chung, được chuẩn hóa, để biết phải cung cấp tham số nào cho constructor đó. Constructor không tham số giải quyết điểm này.

## 2. Yêu cầu của chuẩn JPA đối với constructor

Đối với một **entity class**, quy tắc thông dụng trong đặc tả JPA/Jakarta Persistence là:

> Entity phải có constructor không tham số với mức truy cập **`public` hoặc `protected`**; entity vẫn được phép khai báo thêm các constructor khác.

Ví dụ đáp ứng yêu cầu:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String fullName;

    protected Customer() {
        // Constructor dành cho JPA.
    }

    public Customer(String fullName) {
        this.fullName = fullName;
    }
}
```

Trong ví dụ này:

- `protected Customer()` cho phép JPA provider khởi tạo entity theo yêu cầu của chuẩn.
- `public Customer(String fullName)` cho phép ứng dụng tạo khách hàng bằng API nghiệp vụ có kiểm soát.
- `@Id` xác định trường định danh entity; nó không thay thế yêu cầu constructor.
- JPA không yêu cầu toàn bộ trường persistent phải được truyền vào constructor.

### Vì sao nên chọn `protected`?

`public` no-args constructor vẫn hợp lệ:

```java
public Customer() {}
```

Nhưng nó cho phép bất kỳ đoạn mã nào tạo:

```java
Customer customer = new Customer();
```

Ngay sau đó, `fullName` có thể chưa được gán, khiến object ở trạng thái chưa hợp lệ theo nghiệp vụ. Nếu nghiệp vụ muốn tạo khách hàng chỉ khi có họ tên, để constructor không tham số ở mức `protected` thường là lựa chọn thực tế hơn.

`protected` không làm constructor hoàn toàn không thể gọi từ mọi mã ứng dụng: các class cùng package và subclass vẫn có thể truy cập theo quy tắc Java. Tuy nhiên, nó làm API khởi tạo công khai của entity rõ ràng hơn.

### `private` có được không?

Đoạn sau **không đáp ứng yêu cầu portable của chuẩn JPA**:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private Customer() {}
}
```

Một số phiên bản/cấu hình của Hibernate có thể tạo instance bằng cơ chế riêng dù constructor là `private`. Điều đó **không có nghĩa mọi JPA provider đều phải hỗ trợ**, và cũng có thể gây trở ngại cho cơ chế proxy.

Để thiết kế entity dựa vào hợp đồng Jakarta Persistence và dễ chuyển provider, hãy dùng `protected` hoặc `public`.

| Constructor | Có tham số? | Phù hợp yêu cầu no-args chuẩn JPA? | Ghi chú |
| --- | --- | --- | --- |
| `public Customer()` | Không | Có | Công khai cho mọi mã ứng dụng |
| `protected Customer()` | Không | Có | Thường nên ưu tiên |
| `Customer()` (package-private) | Không | Không theo hợp đồng chuẩn | Một số provider có thể hỗ trợ ngoài chuẩn |
| `private Customer()` | Không | Không theo hợp đồng chuẩn | Phụ thuộc provider, có thể ảnh hưởng proxy |
| `public Customer(String name)` | Có | Không, nếu đứng một mình | Có thể tồn tại **thêm** bên cạnh no-args |

## 3. Quy tắc tự sinh constructor của Java: nguồn gây lỗi thường gặp

Java có một hành vi rất dễ bị hiểu nhầm: **compiler chỉ tự sinh constructor không tham số mặc định nếu class không khai báo constructor nào**.

### Trường hợp A: chưa viết constructor nào

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
```

Class có constructor mặc định do Java cung cấp. Vì `Customer` là một class `public` và không khai báo constructor nào, constructor mặc định cũng có mức truy cập thích hợp. Trong ví dụ này, yêu cầu no-args được đáp ứng mà không phải viết thủ công.

Tuy nhiên, để diễn đạt rõ ý đồ và tránh lỗi khi sau này thêm constructor có tham số, nhiều nhóm vẫn chủ động khai báo:

```java
protected Customer() {}
```

### Trường hợp B: thêm một constructor có tham số

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String fullName;

    public Customer(String fullName) {
        this.fullName = fullName;
    }
}
```

Từ lúc khai báo `Customer(String fullName)`, compiler **không tự sinh** `Customer()` nữa. Class trên thiếu constructor không tham số. Cách sửa là khai báo thêm:

```java
protected Customer() {}

public Customer(String fullName) {
    this.fullName = fullName;
}
```

Đừng nhầm **không khai báo constructor** với **không có no-args constructor**: trước khi thêm constructor có tham số, class có constructor mặc định; sau khi thêm, không còn.

### Trường hợp C: dùng `this(...)` hoặc `super(...)`

Constructor không tham số có thể gọi một constructor khác bằng `this(...)` nếu phù hợp, nhưng cần tránh ép JPA đi qua logic chỉ dành cho lúc tạo đối tượng mới:

```java
protected Customer() {
    this("UNKNOWN"); // Có thể gây hiểu nhầm trạng thái khi hydrating.
}
```

Provider có thể ghi đè `fullName` bằng dữ liệu từ database sau khi constructor chạy. Nếu constructor ghi audit log, phát sự kiện nghiệp vụ, cấp mã mới hoặc gọi service, những tác dụng phụ đó không phải ý đồ của quá trình load entity.

**Cách thông dụng:** để no-args constructor rỗng hoặc chỉ thực hiện khởi tạo trạng thái nội bộ thật sự an toàn.

## 4. Thiết kế entity có constructor không tham số nhưng vẫn bảo vệ nghiệp vụ

Một entity tốt thường có **hai lối khởi tạo phục vụ hai mục đích**:

- JPA provider dùng no-args constructor để có một instance và khôi phục trạng thái từ database.
- Mã nghiệp vụ dùng constructor/factory nhận dữ liệu cần thiết để tạo entity mới hợp lệ.

Ví dụ đầy đủ hơn:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Column(name = "email", nullable = false, length = 240)
    private String email;

    protected Customer() {
        // JPA dùng để khởi tạo khi nạp entity.
    }

    public Customer(String fullName, String email) {
        this.fullName = requireText(fullName, "fullName");
        this.email = requireText(email, "email");
    }

    private static String requireText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                field + " must not be blank"
            );
        }
        return value.trim();
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public void changeEmail(String newEmail) {
        this.email = requireText(newEmail, "email");
    }
}
```

Điểm nổi bật:

1. **Không đặt `id` làm tham số tạo mới.** Trong ví dụ, khóa chính do database sinh theo `GenerationType.IDENTITY`; JPA sẽ phối hợp lấy ID khi lưu.
2. **Có constructor `protected Customer()`** để provider đáp ứng yêu cầu tạo instance.
3. **Constructor công khai kiểm tra đầu vào**, tránh tạo khách hàng mới với tên hoặc email rỗng qua API nghiệp vụ.
4. **Không công khai setter cho mọi field.** Method `changeEmail()` diễn đạt rõ thao tác nghiệp vụ và chỗ kiểm tra dữ liệu.
5. **Trường được ánh xạ không khai báo `final`** để tránh vi phạm các ràng buộc của mô hình entity portable và để provider khôi phục trạng thái.

Trong ví dụ, `@Column(nullable = false)` mô tả metadata ánh xạ/schema. Cần có constraint `NOT NULL` thực sự trong database, và có thể kết hợp Jakarta Bean Validation để bảo đảm tính toàn vẹn theo nhu cầu. Không nên xem constructor validation là tuyến bảo vệ duy nhất cho mọi đường ghi dữ liệu.

### Constructor nghiệp vụ không bắt buộc phải là `public`

Khi muốn có factory method diễn đạt nghiệp vụ, có thể dùng:

```java
@Entity
public class Account {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String ownerName;

    protected Account() {}

    private Account(String ownerName) {
        if (ownerName == null || ownerName.isBlank()) {
            throw new IllegalArgumentException("ownerName");
        }
        this.ownerName = ownerName.trim();
    }

    public static Account openFor(String ownerName) {
        return new Account(ownerName);
    }
}
```

Cách gọi:

```java
Account account = Account.openFor("Nguyễn An");
entityManager.persist(account);
```

Ứng dụng có thể dùng factory với tên mang ý nghĩa nghiệp vụ; JPA vẫn có constructor không tham số cần thiết. Quyết định dùng constructor công khai hay static factory là lựa chọn thiết kế domain, không phải quy tắc bắt buộc của JPA.

## 5. Entity được tạo khi nào, và trạng thái của nó ra sao?

Một entity object có thể xuất hiện theo nhiều cách:

| Cách xuất hiện | Ai yêu cầu tạo? | Trạng thái persistence ban đầu/tiếp theo |
| --- | --- | --- |
| `new Customer(...)` | Code ứng dụng | **New/transient**, chưa managed |
| `Account.openFor(...)` | Factory của ứng dụng | **New/transient**, chưa managed |
| `entityManager.persist(entity)` | Code ứng dụng yêu cầu JPA quản lý object đã có | Trở thành **managed** theo quy tắc JPA |
| `entityManager.find(Customer.class, id)` | Provider trả về instance theo ID | Trả về managed entity hoặc `null` nếu không tìm thấy |
| JPQL trả về entity | Provider xử lý truy vấn | Entity trong kết quả thường được quản lý trong persistence context |
| `entityManager.getReference(Customer.class, id)` | Ứng dụng yêu cầu tham chiếu entity | Provider có thể trả reference/proxy mà chưa truy vấn đầy đủ |
| `entityManager.merge(detached)` | Ứng dụng yêu cầu hợp nhất state | Trả về một managed instance; object truyền vào có thể vẫn detached |

Điểm cần phân biệt: **no-args constructor là cơ chế cho phép tạo instance, không quyết định entity có được quản lý bởi JPA hay không**.

Ví dụ:

```java
Customer a = new Customer("Nguyễn An", "an@example.com");
// a là object Java bình thường, chưa thuộc persistence context.

entityManager.persist(a);
// a trở thành managed trong persistence context phù hợp.
```

Gọi `new` không tự phát `INSERT`. Ngược lại, gọi `find()` không nhất thiết tạo object mới nếu entity cùng identity đã có trong persistence context.

### Luồng tạo mới và luồng nạp lại có mục đích khác nhau

```text
Tạo mới theo nghiệp vụ:
new Customer(name, email)
          │
          ├── Kiểm tra dữ liệu đầu vào
          └── persist() → managed → flush/commit → INSERT

Nạp từ database:
entityManager.find(Customer.class, id)
          │
          ├── Provider tìm managed instance hiện có
          └── Hoặc đọc DB, tạo/khôi phục entity → managed
```

Vì hai luồng này khác nhau, không nên dùng constructor không tham số để tạo mã đơn hàng mới, gửi email chào mừng, kiểm tra trạng thái từ một service bên ngoài, hoặc thực hiện thao tác nghiệp vụ chỉ dành cho trường hợp **tạo mới**.

## 6. JPA có gọi constructor nghiệp vụ khi tải entity không?

Giả sử:

```java
public Customer(String fullName, String email) {
    this.fullName = requireText(fullName, "fullName");
    this.email = requireText(email, "email");
}
```

Khi tải một hàng từ DB, JPA **không có hợp đồng yêu cầu gọi constructor này với các cột tương ứng**. Cách chuẩn bị một entity để load khác việc ứng dụng gọi constructor có tham số.

Mô hình khái niệm:

```text
[1] Khởi tạo instance thông qua cách mà provider hỗ trợ
                │
                ▼
[2] Instance có field Java ở trạng thái mặc định
                │
                ▼
[3] Khôi phục state được ánh xạ từ dữ liệu database
                │
                ▼
[4] Kích hoạt lifecycle callback theo quy định
                │
                ▼
[5] Ứng dụng sử dụng managed entity đã được nạp
```

Không nên viết logic kỳ vọng “constructor có tham số sẽ được chạy lại mỗi khi entity được đọc từ DB”. Nếu constructor nghiệp vụ có quy tắc validation quan trọng, hãy bảo đảm quy tắc ấy cũng được bảo vệ bởi database constraint, các thao tác thay đổi state, và cơ chế validation thích hợp.

### Không dựa vào thứ tự/hành vi nội bộ khi khởi tạo

JPA provider có thể dùng reflection, cơ chế subclass proxy hoặc bytecode enhancement. Số lần một constructor cụ thể được thực thi không phải thước đo chuẩn để đếm entity load. Với một lần `find()`, provider có thể trả về managed instance đã tồn tại và không cần tạo object mới.

Ví dụ sai ý đồ:

```java
protected Customer() {
    System.out.println("Loaded a Customer!");
}
```

Thông báo trên không phải một sự kiện chuẩn cho “vừa load một hàng từ DB”. Nó liên quan tới việc tạo instance, và có thể không xảy ra ở mọi lần query.

## 7. Field access và property access ảnh hưởng việc khôi phục trạng thái

JPA có hai cách truy cập trạng thái phổ biến:

- **Field access:** annotation mapping đặt trên field; provider đọc/ghi trực tiếp theo field.
- **Property access:** annotation mapping đặt trên getter JavaBeans; provider đọc/ghi theo property.

### 7.1. Field access

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String fullName;

    protected Customer() {}

    public Customer(String fullName) {
        this.fullName = fullName;
    }

    public String getFullName() {
        return fullName;
    }
}
```

`@Id` nằm trên **field**, nên mặc định mapping của entity sử dụng field access. Provider có thể khôi phục `fullName` qua field mà không cần gọi setter nghiệp vụ.

Nếu ta thêm:

```java
public void rename(String newName) {
    if (newName == null || newName.isBlank()) {
        throw new IllegalArgumentException("newName");
    }
    this.fullName = newName.trim();
}
```

thì `rename()` chỉ chạy khi mã ứng dụng gọi, không phải một callback mặc định khi database load entity.

### 7.2. Property access

```java
@Entity
@Access(AccessType.PROPERTY)
public class Customer {
    private Long id;
    private String fullName;

    protected Customer() {}

    @Id
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    public String getFullName() {
        return fullName;
    }

    protected void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Ở property access, provider sử dụng các accessor tương ứng để truy cập persistent property. Setter vì thế phải phù hợp với quá trình khôi phục dữ liệu. Không nên đặt side effect như gửi email, gọi API, cấp token hoặc phát domain event trong setter thuộc mapping.

**Constructor không tham số vẫn cần thiết cho cả field access và property access.** Chọn cách access chỉ quyết định cách trạng thái persistent được đọc/ghi, không thay thế yêu cầu khởi tạo instance.

Có thể dùng `@Access` để chỉ định kiểu access một cách tường minh; khi trộn field/property mapping, cần tuân thủ quy tắc rõ ràng của JPA thay vì tùy ý di chuyển annotation.

## 8. Vai trò của lifecycle callbacks: `@PostLoad`, `@PrePersist`

Khi cần xử lý vòng đời entity, JPA cung cấp callback riêng. Chúng giúp phân biệt thời điểm **khởi tạo Java object** với các thời điểm **quản lý persistence**.

Ví dụ:

```java
import jakarta.persistence.*;

@Entity
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String displayName;

    @Transient
    private String normalizedName;

    protected Product() {}

    public Product(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("displayName");
        }
        this.displayName = displayName.trim();
        updateNormalizedName();
    }

    @PostLoad
    private void afterLoad() {
        updateNormalizedName();
    }

    private void updateNormalizedName() {
        normalizedName = displayName == null
            ? null
            : displayName.trim().toLowerCase(java.util.Locale.ROOT);
    }

    public String getNormalizedName() {
        return normalizedName;
    }
}
```

`@Transient` trong ví dụ báo cho JPA rằng `normalizedName` **không được ánh xạ thành dữ liệu persistent**. `@PostLoad` cho phép tính lại giá trị phụ sau khi state persistent đã được khôi phục từ DB.

Chú ý:

- `@PostLoad` không phải constructor và không thay thế no-args constructor.
- Callback không nên thực hiện I/O nặng, gọi lại các truy vấn tùy tiện hoặc có side effect không kiểm soát.
- Nếu `displayName` có thể đổi khi entity managed, cần đồng bộ `normalizedName` trong method thay đổi hoặc tính nó tại thời điểm truy cập.
- Các callback như `@PrePersist` hay `@PreUpdate` có mục đích khác `@PostLoad`: chúng liên quan sự kiện trước thao tác persistence tương ứng.

Nếu dùng constructor để khởi tạo một field transient dựa vào field persistent, dữ liệu transient tính ra trước khi hydrate có thể không còn đúng. `@PostLoad` hoặc phương thức tính toán khi cần thường phù hợp hơn.

## 9. Constructor không tham số trong quan hệ kế thừa

Yêu cầu constructor còn chịu ảnh hưởng quy tắc kế thừa của Java. Khi một subclass được khởi tạo, constructor của superclass được gọi theo chuỗi.

Ví dụ:

```java
import jakarta.persistence.*;

@MappedSuperclass
public abstract class BaseEntity {
    @Id
    @GeneratedValue
    private Long id;

    protected BaseEntity() {
        // Cho phép các subclass entity khởi tạo.
    }

    public Long getId() {
        return id;
    }
}
```

Entity kế thừa:

```java
@Entity
public class Category extends BaseEntity {
    @Column(nullable = false)
    private String name;

    protected Category() {
        super();
    }

    public Category(String name) {
        super();
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name");
        }
        this.name = name.trim();
    }

    public String getName() {
        return name;
    }
}
```

Ở đây:

- `BaseEntity` được đánh dấu `@MappedSuperclass` để chia sẻ mapping `id`; bản thân nó không phải một entity có thể query trực tiếp.
- `BaseEntity` có no-args constructor `protected` để subclass gọi.
- `Category` cũng có no-args constructor cho JPA.
- Constructor `Category(String)` phục vụ tạo object mới với quy tắc kiểm tra tên.

### Nếu superclass không có constructor không tham số thì sao?

```java
public abstract class AuditedObject {
    protected AuditedObject(String source) {
        // ...
    }
}

@Entity
public class Order extends AuditedObject {
    @Id
    private Long id;

    protected Order() {
        // Java cố gọi super() nhưng superclass không có constructor đó.
    }
}
```

Đây là lỗi **biên dịch Java**: constructor `Order()` ngầm gọi `super()` trong khi superclass chỉ có `AuditedObject(String)`.

Có thể khắc phục bằng cách điều chỉnh thiết kế superclass hoặc cho subclass gọi constructor thích hợp:

```java
protected Order() {
    super("JPA");
}
```

Tuy nhiên, truyền một giá trị giả chỉ để thỏa constructor superclass có thể làm dữ liệu nghiệp vụ khó hiểu. Trong hệ phân cấp entity, cách tốt hơn thường là thiết kế superclass cung cấp constructor không tham số phù hợp và để nghiệp vụ thiết lập thuộc tính cần thiết thông qua constructor/factory công khai.

**Không phải cứ có no-args constructor ở superclass là đủ:** entity concrete vẫn phải có đường khởi tạo không tham số hợp lệ của chính nó. Khi class khai báo constructor có tham số, hãy chủ động thêm no-args cho entity đó.

## 10. Constructor và cơ chế lazy proxy

Một số JPA provider sử dụng **proxy** hoặc bytecode enhancement để hỗ trợ lazy loading. Ví dụ, association được khai báo:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Khi tải `Order`, provider có thể đại diện cho `customer` bằng một object có khả năng trì hoãn việc đọc toàn bộ state đến lúc ứng dụng truy cập.

Một cách triển khai proxy là tạo class con từ entity và chặn lời gọi phương thức để kích hoạt load. Vì vậy, ngoài yêu cầu constructor chuẩn, provider có thể đặt thêm yêu cầu thực tế về visibility, khả năng subclass, và phương thức có thể được override.

Điều nên nhớ:

- Constructor `protected` cho phép subclass theo quy tắc Java gọi constructor cha.
- `private` no-args có thể cản trở các chiến lược subclass proxy, ngoài việc không tuân thủ yêu cầu portable của JPA.
- Entity `final`, method `final` hoặc field persistent `final` không phù hợp với các ràng buộc entity portable truyền thống và có thể gây khó khăn cho proxy/enhancement.
- Không nên giả định mọi provider tạo cùng loại proxy hoặc cùng thời điểm thực hiện SQL.
- Không nên lấy `getClass()` của entity rồi mặc định đó luôn là class gốc thay vì proxy subclass; khi cần xác định kiểu và identity, hãy cân nhắc giải pháp tương thích với provider đang dùng.

Constructor không tham số giải quyết yêu cầu tạo object; **lazy loading vẫn là một cơ chế riêng** với ranh giới persistence context và query cần hiểu đầy đủ.

## 11. Lombok và những annotation dễ khiến entity mất constructor hợp lệ

Lombok giúp giảm boilerplate nhưng thay đổi constructor ngay ở bước biên dịch. Vì JPA có yêu cầu constructor cụ thể, cần nhận biết annotation nào sinh hoặc loại bỏ constructor mặc định.

### 11.1. `@AllArgsConstructor` có thể làm mất no-args mặc định

```java
import lombok.AllArgsConstructor;

@Entity
@AllArgsConstructor
public class Customer {
    @Id
    private Long id;

    private String fullName;
}
```

Khi Lombok sinh constructor nhận tất cả field, class không còn dựa được vào default no-args constructor do Java tự tạo. Để entity portable, thêm no-args constructor:

```java
import lombok.AccessLevel;
import lombok.NoArgsConstructor;

@Entity
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Customer {
    @Id
    private Long id;

    private String fullName;

    public Customer(String fullName) {
        this.fullName = fullName;
    }
}
```

Trong ví dụ thứ hai, Lombok tạo constructor không tham số `protected`. Constructor có tham số do ta viết, dùng để diễn đạt và kiểm tra dữ liệu nghiệp vụ.

### 11.2. `@Builder` không tự giải quyết yêu cầu JPA

Builder hữu ích ở một số kiểu dữ liệu, nhưng `@Builder` không phải annotation JPA và không nên được xem là cách bảo đảm có no-args constructor. Nếu Lombok builder được áp dụng theo cách sinh một constructor có tham số, entity có thể mất constructor mặc định.

Ngoài ra, builder có thể cho phép tạo object thiếu trường bắt buộc nếu không đặt validation/factory phù hợp. Không nên lấy “có thể build được object” làm bảo đảm invariant nghiệp vụ.

### 11.3. Cẩn trọng với `@NoArgsConstructor(force = true)`

Tùy chọn `force = true` của Lombok có thể khởi tạo field `final` bằng giá trị mặc định cưỡng bức khi không có constructor tương thích. Điều này không làm một mô hình entity có các persistent field `final` trở nên portable hoặc bảo đảm chúng sẽ được JPA quản lý đúng.

Với entity JPA, nên thiết kế field/mapping theo yêu cầu của JPA thay vì dùng ép buộc constructor để chữa một thiết kế bất biến không tương thích.

### 11.4. `@Data` và `@Value` không phải lựa chọn mặc định an toàn

`@Data` sinh các method như `equals()`, `hashCode()`, `toString()` và setter dựa vào field theo quy tắc của Lombok. Đối với JPA entity, điều đó có thể gây vấn đề vì:

- `equals()` và `hashCode()` dựa vào ID sinh sau khi persist hoặc vào collection có thể thay đổi.
- `toString()` truy cập quan hệ lazy, dẫn đến SQL ngoài ý muốn hoặc vòng lặp qua quan hệ hai chiều.
- Setter được công khai rộng hơn ý đồ nghiệp vụ.

`@Value` thường tạo class/field bất biến với `final`, không phù hợp cách biểu diễn entity portable. Entity và immutable DTO có mục đích khác nhau; không nên áp dụng một bộ annotation Lombok cho cả hai mà không xét vòng đời persistence.

## 12. Java record, DTO và entity: không nên đánh đồng

Java record rất phù hợp để biểu diễn dữ liệu đầu ra:

```java
public record CustomerSummary(
    Long id,
    String fullName
) {}
```

Record có constructor theo các component và thường được dùng làm DTO, chẳng hạn trong JPQL constructor projection:

```java
List<CustomerSummary> summaries = entityManager.createQuery(
    "SELECT NEW com.example.CustomerSummary(c.id, c.fullName) " +
    "FROM Customer c",
    CustomerSummary.class
).getResultList();
```

Nhưng **Java record không phải lựa chọn portable cho một entity JPA thông thường**, vì record là `final`, component field mang tính bất biến, và mô hình constructor của record không khớp với yêu cầu entity.

Lưu ý phân biệt:

| Loại object | Có cần no-args của entity JPA? | Cách khởi tạo phù hợp |
| --- | --- | --- |
| `@Entity Customer` | Có | `protected`/`public` no-args và constructor/factory nghiệp vụ |
| DTO Java record | Không theo yêu cầu entity | Canonical constructor của record |
| Projection DTO class | Không theo yêu cầu entity | Constructor theo dữ liệu truy vấn |
| Java service | Không | Constructor phục vụ dependency injection |
| `@Embeddable` | Quy tắc ánh xạ riêng theo phiên bản Jakarta Persistence | Xem đúng đặc tả và provider đang dùng |

Không nên sửa DTO đang hoạt động tốt chỉ để thêm constructor không tham số, nếu DTO không được JPA quản lý như entity.

### Ghi chú về Kotlin

Kotlin class thường là `final` mặc định và primary constructor có tham số; điều này khác kiểu entity class Java truyền thống. Khi dùng Kotlin với JPA, các dự án thường sử dụng plugin công cụ như `kotlin-jpa` (hỗ trợ tạo no-args constructor) và cấu hình `all-open` nếu cần để phù hợp cơ chế subclass/proxy. Đây là cơ chế hỗ trợ ở tầng ngôn ngữ/build, không làm thay đổi hợp đồng của JPA. Việc tương thích phải kiểm tra theo phiên bản Kotlin, provider và cách build.

## 13. Không đặt logic có side effect trong no-args constructor

Một sai lầm nguy hiểm là nghĩ constructor chạy chỉ lúc tạo bản ghi mới.

Ví dụ không phù hợp:

```java
@Entity
public class Order {
    @Id
    private Long id;

    private String referenceCode;

    protected Order() {
        referenceCode = java.util.UUID.randomUUID().toString();
        System.out.println("Create a new order event");
    }
}
```

Khi provider khôi phục entity cũ, constructor có thể sinh `referenceCode` mới rồi provider gán lại giá trị từ DB. Trong trường hợp đó mã mới chỉ là tác dụng phụ vô ích. Nếu phát event, gửi thông báo hoặc truy cập tài nguyên bên ngoài, side effect còn nghiêm trọng hơn.

Nếu `referenceCode` là thuộc tính phải được sinh **khi tạo đơn hàng mới**, đưa nó vào constructor/factory nghiệp vụ:

```java
@Entity
public class Order {
    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "reference_code", nullable = false, unique = true)
    private String referenceCode;

    protected Order() {}

    private Order(String referenceCode) {
        this.referenceCode = referenceCode;
    }

    public static Order createNew() {
        return new Order(java.util.UUID.randomUUID().toString());
    }
}
```

Khi gọi:

```java
Order order = Order.createNew();
entityManager.persist(order);
```

thì việc tạo mã nằm ở use case tạo mới. Khi `Order` được nạp từ database, mã đã lưu được khôi phục; no-args constructor không tự sinh mã mới.

Nếu yêu cầu là audit timestamp khi ghi lần đầu, hãy cân nhắc cơ chế nhất quán như `@PrePersist`, database default, hoặc logic service có kiểm soát. Nếu có nhiều đường ghi dữ liệu, database constraint và cơ chế ghi tập trung vẫn rất quan trọng.

## 14. Khởi tạo collection thế nào cho an toàn?

Một entity có quan hệ một-nhiều thường muốn collection không là `null` lúc tạo object mới:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    @OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(Long id) {
        this.id = id;
    }

    public void addLine(OrderLine line) {
        if (line == null) {
            throw new IllegalArgumentException("line");
        }
        lines.add(line);
        line.attachTo(this);
    }

    public List<OrderLine> getLines() {
        return java.util.Collections.unmodifiableList(lines);
    }
}
```

Trong `OrderLine`, method `attachTo(PurchaseOrder)` cần cập nhật phía giữ foreign key:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "order_id")
private PurchaseOrder order;

void attachTo(PurchaseOrder order) {
    this.order = order;
}
```

Field initializer `new ArrayList<>()` hữu ích khi ứng dụng gọi `new PurchaseOrder(...)` và là thao tác an toàn về mặt side effect. Nhưng khi entity được load, provider có thể thay collection bằng một cấu trúc wrapper riêng để hỗ trợ lazy loading hoặc dirty checking.

Vì vậy:

- Nên khai báo với kiểu interface như `List<OrderLine>` thay vì ép code phụ thuộc `ArrayList` cụ thể.
- Đừng giả định collection luôn là đúng instance `ArrayList` đã tạo tại field initializer.
- Với quan hệ hai chiều, cập nhật cả collection và phía sở hữu foreign key theo quy tắc mapping.
- Phân biệt việc khởi tạo collection rỗng với việc **tải dữ liệu của collection** từ database: hai thao tác không tương đương.

## 15. Ví dụ thực hành: lưu và nạp lại entity với no-args constructor

Ta có entity `Customer` ở mục 4 và một `EntityManager` đã cấu hình kết nối tới database.

Ví dụ bên dưới dùng transaction kiểu resource-local, thích hợp cho minh họa Java SE. Trong Spring/Jakarta EE, cách quản lý transaction thường do framework/container đảm nhiệm.

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    em.getTransaction().begin();

    Customer created =
        new Customer("Nguyễn An", "an@example.com");

    em.persist(created);
    em.flush();

    Long id = created.getId();

    // Xóa các managed entity khỏi persistence context,
    // nhưng không xóa hàng trong database.
    em.clear();

    Customer loaded = em.find(Customer.class, id);

    System.out.println(loaded.getId());
    System.out.println(loaded.getFullName());
    System.out.println(loaded.getEmail());

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Chuỗi thao tác có ý nghĩa:

1. `new Customer(...)` dùng **constructor nghiệp vụ**.
2. `persist(created)` yêu cầu provider quản lý object vừa tạo.
3. `flush()` đồng bộ state với database trong transaction, thuận lợi cho việc lấy ID đã sinh theo chiến lược phù hợp.
4. `clear()` tách các managed instance khỏi persistence context; đây **không phải** `DELETE` hay `ROLLBACK`.
5. `find(Customer.class, id)` yêu cầu JPA đọc lại identity, thay vì trả luôn managed instance trước đó.
6. `loaded` chứa state được khôi phục theo mapping; ứng dụng không phải tự gọi `new Customer()`.
7. `commit()` xác nhận transaction.

Ví dụ này cũng cho thấy **constructor có tham số không phải điều kiện để JPA tìm lại entity**. Điều kiện thiết kế quan trọng là entity có đường khởi tạo đúng chuẩn, mapping hợp lệ và database chứa dữ liệu phù hợp.

Ở các chiến lược sinh ID khác nhau, thời điểm ID sẵn sàng có thể khác nhau; trong ví dụ `flush()` chủ động đồng bộ trước khi đọc `id`. Code production không nên phụ thuộc vào chi tiết nội bộ vượt ngoài hợp đồng/provider đang dùng.

### Một lỗi thường thấy khi bỏ `clear()` trong minh họa

Nếu gọi `find()` ngay sau `persist()` trong **cùng persistence context**, JPA có thể trả về chính managed object `created` đang có sẵn. Lúc đó bài thử **không minh họa** được việc provider cần khởi tạo và hydrate instance từ database. `clear()` được thêm vào để làm rõ ranh giới này.

Tương tự, nếu database hoặc persistence context dùng cache, cách thực thi vật lý có thể khác, nhưng yêu cầu mapping và khả năng tái tạo entity vẫn cần được đáp ứng.

## 16. Thông báo lỗi và cách xác định nguyên nhân

Khi entity thiếu no-args constructor hoặc constructor không truy cập được, lỗi có thể xuất hiện khi khởi động persistence unit, tạo proxy, hoặc khi truy vấn cần khởi tạo entity. Tên exception và nội dung log phụ thuộc provider/phiên bản.

Một số thông báo thường gặp về mặt ý nghĩa:

- `No default constructor for entity`.
- `Could not instantiate entity`.
- `InstantiationException` hoặc `PersistenceException` có nguyên nhân từ constructor.
- Thông báo liên quan đến khả năng tạo proxy/subclass nếu constructor hoặc class không phù hợp.

### Tình huống 1: chỉ có constructor có tham số

```java
@Entity
public class Department {
    @Id
    private Long id;

    private String name;

    public Department(String name) {
        this.name = name;
    }
}
```

**Nguyên nhân:** khi thêm constructor `Department(String)`, Java không sinh default constructor nữa.

**Hướng sửa:** thêm `protected Department() {}`.

### Tình huống 2: no-args constructor là `private`

```java
@Entity
public class Department {
    @Id
    private Long id;

    private Department() {}
}
```

**Nguyên nhân:** visibility không đáp ứng hợp đồng portable của JPA.

**Hướng sửa:** thay bằng `protected Department() {}` hoặc `public Department() {}`.

### Tình huống 3: class con có no-args nhưng superclass không hỗ trợ

```java
class BaseModel {
    BaseModel(String metadata) {}
}

@Entity
class Department extends BaseModel {
    @Id
    private Long id;

    protected Department() {} // Không biên dịch: thiếu super() phù hợp.
}
```

**Nguyên nhân:** quy tắc constructor chaining của Java, chưa phải lỗi runtime JPA.

**Hướng sửa:** điều chỉnh superclass hoặc lời gọi `super(...)` theo thiết kế.

### Tình huống 4: Lombok sinh constructor nhưng không sinh no-args

```java
@Entity
@AllArgsConstructor
class Department {
    @Id
    private Long id;
    private String name;
}
```

**Nguyên nhân:** phụ thuộc vào constructor được Lombok sinh; không còn constructor mặc định thích hợp.

**Hướng sửa:** dùng thêm `@NoArgsConstructor(access = AccessLevel.PROTECTED)` hoặc tự viết no-args.

### Tình huống 5: entity là class không thể được khởi tạo theo chuẩn

Một **non-static inner class** giữ tham chiếu ngầm tới outer instance nên không có đường khởi tạo như top-level entity thông thường. Entity portable nên là top-level class hoặc static nested class phù hợp theo đặc tả. Class `final` cũng gây vấn đề với yêu cầu và cơ chế triển khai entity.

**Hướng sửa:** đưa entity ra top-level class hoặc thiết kế lại cấu trúc nested class; tránh dùng kiểu class mà provider không thể khởi tạo đúng hợp đồng.

Khi gặp lỗi, nên đọc dòng **root cause** và kiểm tra signature các constructor sau khi annotation processor/Lombok đã xử lý. Không nên chỉ tìm một đoạn stack trace chứa tên Hibernate rồi kết luận database hỏng.

## 17. Những điều constructor không tham số KHÔNG giải quyết

No-args constructor là một điều kiện cần cho entity portable, nhưng không bảo đảm mọi phần còn lại hợp lệ.

| Vấn đề | Vì sao no-args không đủ? | Thành phần cần xem thêm |
| --- | --- | --- |
| Entity không có định danh | JPA cần nhận diện entity | `@Id`, `@EmbeddedId`, ID mapping |
| Khóa chính sai/không tồn tại | Constructor không sửa được schema | Primary key, strategy, dữ liệu trong DB |
| Quan hệ một-nhiều lưu không đúng | Mapping owning side chưa chính xác | `@JoinColumn`, `mappedBy`, cascade |
| Giá trị `null` vi phạm ràng buộc | Constructor nạp DB không nhất thiết chạy validation của constructor nghiệp vụ | Validation, `NOT NULL`, constraint |
| N+1 query | Khả năng tạo object khác kế hoạch tải association | Fetch plan, JPQL `JOIN FETCH`, entity graph |
| Lazy access sau khi đóng context | Constructor không duy trì persistence context | Transaction boundary, query/projection |
| Đụng độ cập nhật | Constructor không điều phối concurrency | `@Version`, locking, transaction |
| SQL không tương thích database | Constructor không sinh được SQL đúng nếu dialect/schema không phù hợp | Provider, driver, mapping, schema |
| Tạo entity immutable tuyệt đối | ORM còn yêu cầu khôi phục persistent state | Thiết kế entity vs immutable value/DTO |

Ví dụ, entity có no-args constructor nhưng không khai báo `@Id` vẫn không phải entity mapping hợp lệ. Tương tự, `@Column(nullable = false)` không khiến constructor tự ném lỗi khi DB trả giá trị `NULL`; cần kiểm soát tính toàn vẹn tại database và các ranh giới dữ liệu.

## 18. Bài tập vận dụng

Xét ba class sau:

### Ví dụ A

```java
@Entity
public class Book {
    @Id
    private Long id;

    private String title;

    public Book(String title) {
        this.title = title;
    }
}
```

**Câu hỏi:** Vì sao class này có thể gặp lỗi khi JPA tải entity? Hãy bổ sung constructor để đáp ứng JPA nhưng vẫn yêu cầu ứng dụng tạo `Book` mới có tiêu đề.

**Gợi ý đáp án:**

```java
protected Book() {}

public Book(String title) {
    if (title == null || title.isBlank()) {
        throw new IllegalArgumentException("title");
    }
    this.title = title.trim();
}
```

### Ví dụ B

```java
@Entity
public class Author {
    @Id
    private Long id;

    private String name;
}
```

**Câu hỏi:** Class có cần bắt buộc viết thêm `Author()` hay không?

**Giải thích:** Vì chưa khai báo constructor nào, Java tự sinh constructor mặc định thích hợp với visibility của class `public` này. Viết rõ `protected Author() {}` vẫn hữu ích để ngăn thay đổi về sau vô tình làm mất constructor mặc định khi thêm constructor có tham số.

### Ví dụ C

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    private String invoiceNumber;

    protected Invoice() {
        invoiceNumber = "INV-" + System.nanoTime();
    }
}
```

**Câu hỏi:** Nếu dùng `entityManager.find(Invoice.class, id)` để nạp hóa đơn cũ, việc sinh số hóa đơn trong no-args constructor có đáng tin cậy không?

**Giải thích:** Không nên dựa vào đó. Logic sinh số chỉ phù hợp cho use case tạo hóa đơn mới, trong khi JPA có thể dùng no-args khi nạp dữ liệu cũ và gán lại `invoiceNumber` từ DB. Hãy chuyển logic sinh số sang constructor/factory nghiệp vụ hoặc một thành phần cấp mã chuyên trách, đồng thời bảo vệ tính duy nhất bằng constraint ở database.

### Thử suy luận thêm

Nếu một entity có `@Id`, constructor `protected` không tham số, và constructor `public` nhận đầy đủ dữ liệu, nhưng vẫn không load được khi chạy với Hibernate, những hướng cần điều tra là gì?

Câu trả lời nên bao gồm: cấu hình mapping, class/proxy có thể được khởi tạo không, type của field, tên bảng/cột, schema, database constraint, và root cause của exception. **Không nên mặc định mọi lỗi khởi tạo đều do thiếu no-args constructor.**

## 19. Nguyên tắc thiết kế có thể áp dụng ngay

Khi viết entity cho ứng dụng ORM/JPA, hãy chọn một quy ước nhất quán:

1. **Entity có no-args constructor `protected`** (hoặc `public` nếu có lý do), kể cả khi class còn constructor có tham số.
2. **Constructor/factory nghiệp vụ nhận dữ liệu bắt buộc** và kiểm tra invariant cho trường hợp tạo mới.
3. **No-args constructor không chứa side effect**, truy vấn hay logic chỉ dành cho việc tạo bản ghi.
4. **Không dùng field persistent `final` hoặc entity `final`** nếu muốn tương thích portable với JPA và cơ chế proxy.
5. **Tách quá trình khởi tạo khỏi quá trình khôi phục state**: constructor nghiệp vụ, mapping field/property, và lifecycle callback có vai trò riêng.
6. **Cẩn trọng với Lombok, record, Kotlin và inheritance**, vì mỗi công cụ/ngôn ngữ có cơ chế tạo constructor khác nhau.
7. **Kiểm tra ranh giới transaction và trạng thái managed/detached** khi thử nghiệm việc tạo, lưu và load lại entity.

Những nguyên tắc này hỗ trợ mục tiêu lớn hơn của chương *Entity và định danh*: entity là một đối tượng có identity được JPA quản lý, không đơn thuần là một class Java có vài annotation. Để provider có thể tái tạo identity đó từ dữ liệu quan hệ, entity cần thỏa các quy tắc khởi tạo, ánh xạ và vòng đời.

## Kết luận

**Constructor không tham số là một phần quan trọng trong hợp đồng giữa entity class và JPA provider.** Với entity portable, constructor đó cần có mức truy cập `public` hoặc `protected`. Nếu class có constructor có tham số, Java không tự sinh constructor mặc định nữa, nên phải bổ sung no-args một cách chủ động.

Constructor không tham số phục vụ khả năng **khởi tạo entity để provider quản lý và khôi phục trạng thái**; constructor/factory có tham số phục vụ **tạo entity mới theo quy tắc nghiệp vụ**. Tách hai vai trò này giúp code Java rõ ràng, tránh side effect khi load, giảm lỗi khi dùng Lombok hoặc kế thừa, đồng thời giữ cho entity tương thích với hợp đồng chuẩn JPA.

Khi gặp một entity chưa thể load từ database, hãy bắt đầu từ câu hỏi: **“Provider có thể tạo instance class này bằng đường khởi tạo mà JPA cho phép không?”**. Sau đó mới đi tiếp đến mapping, identity, relation và transaction để tìm đúng nguyên nhân.
