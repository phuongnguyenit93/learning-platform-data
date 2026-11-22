# Chọn thuộc tính cho equals và hashCode của thực thể trong Hibernate ORM

Trong Hibernate ORM, một entity có thể xuất hiện dưới nhiều hình thức: đối tượng Java vừa được tạo bằng `new`, đối tượng đang được một `Session`/`EntityManager` quản lý, bản sao đã *detached* hoặc proxy được tạo để tải dữ liệu trì hoãn. Hai đối tượng Java khác nhau vẫn có thể đại diện cho **cùng một hàng dữ liệu** trong cơ sở dữ liệu.

Điều này dẫn đến câu hỏi thiết kế quan trọng: **khi nào hai entity được xem là bằng nhau trong Java, và cần tính `hashCode()` từ những thuộc tính nào?**

Nếu lựa chọn sai, chương trình có thể gặp những lỗi khó thấy:

- Hai entity mới chưa lưu bị coi là cùng một đối tượng chỉ vì cả hai có khóa chính `null`.
- `HashSet.contains(entity)` hoặc `HashMap.get(entity)` thất bại sau khi Hibernate gán ID.
- `equals()` vô tình truy cập quan hệ `LAZY`, làm xuất hiện nhiều câu SQL hoặc `LazyInitializationException`.
- Hai entity đại diện cho cùng hàng nhưng được tải trong hai Session khác nhau bị so sánh sai kỳ vọng.
- Thay đổi tên, email, trạng thái hoặc collection làm hash code thay đổi.
- Proxy Hibernate và entity thật bị xem là khác loại chỉ vì `getClass()` cho ra lớp runtime khác nhau.

Bài học này xây dựng phương pháp chọn thuộc tính cho `equals()`/`hashCode()` theo **danh tính miền nghiệp vụ**, **kiểu định danh**, **vòng đời persistence**, **tính bất biến** và **cách entity tham gia collection của Java**.

## 1. Ba khái niệm danh tính cần phân biệt

### 1.1. Danh tính đối tượng Java: reference identity

Hai biến cùng trỏ đến một instance Java thì toán tử `==` trả `true`:

```java
Customer first = new Customer("C-001");
Customer second = first;

System.out.println(first == second); // true
```

Nếu tạo hai instance khác nhau:

```java
Customer first = new Customer("C-001");
Customer second = new Customer("C-001");

System.out.println(first == second); // false
```

Mặc định, nếu không override, `Object.equals()` so sánh theo reference identity. Đây là semantics hợp lệ cho nhiều entity, nhưng không biểu diễn việc hai đối tượng ở hai persistence context khác nhau cùng đại diện cho một hàng database.

### 1.2. Danh tính persistence: entity type + primary key

Trong ORM, danh tính của một hàng thường gồm **loại entity** và **giá trị định danh `@Id`**, trong phạm vi một persistence unit/database/tenant phù hợp.

Ví dụ hai đối tượng đều biểu diễn `Customer(id = 42)` nhưng được tải qua hai `EntityManager` khác nhau:

```java
Customer a = em1.find(Customer.class, 42L);
Customer b = em2.find(Customer.class, 42L);

// Hai Java instance có thể khác nhau:
System.out.println(a == b); // Có thể false.
```

Ở tầng nghiệp vụ, chúng có thể được coi là hai biểu diễn của cùng khách hàng. Tuy nhiên, nếu giữ nguyên `Object.equals()` thì `a.equals(b)` có thể là `false`.

Trong **cùng một persistence context**, Hibernate có *identity map*: khi truy xuất cùng entity type và ID, Hibernate thường duy trì một managed instance tương ứng:

```java
Customer a = em.find(Customer.class, 42L);
Customer b = em.find(Customer.class, 42L);

System.out.println(a == b); // Thông thường true trong cùng context.
```

Điều đó giúp giảm nhu cầu tự viết equality khi ứng dụng chỉ thao tác với các managed entity trong **một Session**.

### 1.3. Danh tính nghiệp vụ: business/natural key

Đôi khi domain có một thuộc tính xác định danh tính ngay từ khi object được tạo, ví dụ:

- Mã quốc gia ISO đã chuẩn hóa.
- Mã đơn vị tiền tệ theo chuẩn.
- Mã danh mục do hệ thống bên ngoài cấp và được bảo đảm duy nhất.
- Cặp `(issuer, externalReference)` bất biến và được ràng buộc unique.

Đây là **business key** hoặc **natural key**, khác với khóa kỹ thuật sinh bởi database.

Ví dụ:

```text
Country:
    id       = 7251          (khóa kỹ thuật)
    isoCode  = "VN"          (khóa nghiệp vụ bất biến)
    name     = "Việt Nam"    (thuộc tính có thể đổi)
```

Nếu `isoCode` luôn ổn định và duy nhất, có thể định nghĩa hai `Country` là cùng danh tính ngay cả **trước khi database sinh ID**.

**Điểm quyết định:** không có quy tắc “mọi entity phải dùng `id`” hay “mọi entity phải dùng business key”. Cần lựa chọn dựa vào bất biến thực sự của domain và vòng đời đối tượng.

## 2. Hợp đồng Java của equals và hashCode

Trước khi chọn thuộc tính, phải hiểu contract của Java.

### `equals()`

Với mọi object hợp lệ, phép so sánh cần thỏa:

1. **Reflexive:** `x.equals(x)` luôn true.
2. **Symmetric:** nếu `x.equals(y)` thì `y.equals(x)`.
3. **Transitive:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
4. **Consistent:** trong khi những thông tin tạo nên equality không đổi, các lần gọi cho kết quả nhất quán.
5. **Non-null:** `x.equals(null)` luôn false.

### `hashCode()`

Có hai yêu cầu quan trọng:

- Nếu `a.equals(b)` là true, thì **`a.hashCode() == b.hashCode()` bắt buộc đúng**.
- Hai object không bằng nhau **được phép** có cùng hash code. Hash code không cần duy nhất.

Hash code thường được sử dụng để chọn vùng lưu trữ (*bucket*) của `HashSet` và `HashMap`.

Ví dụ:

```java
Set<Customer> customers = new HashSet<>();
customers.add(customer);

boolean found = customers.contains(customer);
```

Nếu `customer.hashCode()` đổi trong khi object vẫn nằm trong tập, `contains` có thể tìm sai bucket và trả `false` dù object đã được thêm vào.

Đây là lý do **ổn định hash code theo thời gian** quan trọng với entity, nhất là entity có ID được sinh muộn hoặc các thuộc tính nghiệp vụ có thể thay đổi.

## 3. Vòng đời entity khiến equality khó hơn value object

Một entity trong Hibernate có thể đi qua các trạng thái:

```text
new Customer()
      |
      | persist()
      v
  managed entity --------> flush / commit
      |
      | detach(), clear(), close()
      v
  detached entity
      |
      | merge() trả về managed instance khác
      v
  managed copy

managed -- remove() --> trạng thái removed
```

Tên trạng thái và chi tiết lifecycle phụ thuộc ngữ cảnh, nhưng ý nghĩa đối với equality như sau:

| Trạng thái | ID có thể thế nào? | Điểm cần chú ý |
|---|---|---|
| Transient/new với generated ID | Thường `null` | Hai entity mới khác nhau không được bằng nhau chỉ vì ID cùng null |
| Transient/new với assigned business ID | Có thể đã khác null | Có thể so sánh từ sớm nếu ID bất biến và duy nhất |
| Managed | Thường có ID hoặc sắp được gán theo generator | Hibernate đồng nhất instance trong một persistence context |
| Detached | Thường giữ ID đã có | Có thể so sánh với managed instance khác reference |
| Removed | Có thể vẫn giữ ID trong Java | ID không chứng minh row còn tồn tại trong DB |
| Object sau rollback | Có thể vẫn giữ ID được cấp | ID không chứng minh transaction đã commit |

Với `GenerationType.SEQUENCE`, Hibernate thường gán ID trước `INSERT`. Với `IDENTITY`, thường cần insert để lấy ID; với UUID do provider sinh, ID có thể có trước insert. **Thời điểm ID từ null thành khác null khác nhau**, nhưng mọi chiến lược sinh ID muộn đều đặt ra vấn đề tương tự nếu entity đã tham gia hash collection trước đó.

## 4. Cần chọn thuộc tính theo tiêu chí nào?

Đối với mỗi thuộc tính định đưa vào `equals()`, hãy đặt các câu hỏi:

1. **Thuộc tính có xác định cùng một thực thể theo domain không?** Hai người trùng tên không có nghĩa là một người.
2. **Giá trị có sẵn ngay từ khi object được tạo không?** Nếu chỉ có sau `persist`, hash code dựa vào nó có thể đổi.
3. **Giá trị có bất biến trong suốt vòng đời entity không?** Email, tên hiển thị, trạng thái, giá tiền thường có thể đổi.
4. **Có thể null không?** Hai entity mới đều null có thể bị so sánh nhầm.
5. **Giá trị có duy nhất và được database bảo vệ không?** Quy ước “thường không trùng” yếu hơn một ràng buộc unique thực tế.
6. **Giá trị có cần tải LAZY hoặc gọi SQL không?** Tránh equality phải initialize association.
7. **Giá trị có phụ thuộc locale, định dạng, normalization hoặc tenant không?**
8. **Việc so sánh có ổn định khi entity là proxy hoặc nằm trong hệ kế thừa không?**

Bảng đánh giá nhanh:

| Ứng viên | Có nên dùng để định nghĩa equality? | Vì sao |
|---|---|---|
| `@Id` sinh tự động | Có điều kiện | Chỉ so sánh khi khác null; không để hash phụ thuộc ID mới sinh |
| `@Id` do ứng dụng cấp, bất biến | Thường phù hợp | Định danh có sẵn sớm, nếu phạm vi duy nhất rõ |
| Business key bất biến, unique, non-null | Thường phù hợp | Equality ổn định trước và sau persistence |
| Tên hiển thị | Thường không | Có thể đổi và nhiều entity trùng tên |
| Email người dùng | Thường không, nếu đổi được | Có thể đổi, tái sử dụng, cần chuẩn hóa và xác minh uniqueness |
| Số tiền, số lượng, trạng thái | Không | Thuộc tính mutable, không phải danh tính |
| `@Version` | Không | Tăng khi cập nhật, làm hash thay đổi |
| `createdAt`/`updatedAt` | Thường không | Timestamp có thể đến muộn, không unique, có thể đổi |
| Collection `@OneToMany` | Không | Có thể lazy, mutable và chứa tham chiếu vòng |
| `@ManyToOne` tới parent | Thường tránh | Có thể lazy, mutable khi chuyển parent và dễ sinh chuỗi truy cập |
| Trường tính toán từ dữ liệu mutable | Không | Giá trị kéo theo thay đổi |
| Composite business key bất biến | Có thể | Cần chuẩn hóa, kiểm soát uniqueness và proxy/tenant semantics |

Không đưa toàn bộ fields của entity vào equality theo thói quen. **Entity đại diện một đối tượng có danh tính; không phải value object so sánh bằng toàn bộ trạng thái.**

## 5. Có thể không override equals/hashCode

Trước khi viết một dòng `equals`, cần hỏi: **ứng dụng có thật sự cần hai Java instance khác nhau đại diện cùng row được xem là bằng nhau không?**

Nếu mọi thao tác diễn ra trong một `EntityManager` duy nhất, Hibernate thường bảo đảm một managed instance cho một identity. Giữ mặc định `Object.equals` có thể đơn giản và nhất quán.

Ví dụ:

```java
Customer customer = em.find(Customer.class, 42L);

Order order = new Order();
order.assignCustomer(customer);

// Tất cả thao tác ở một persistence context,
// không cần so sánh Customer giữa các Session.
```

Giữ mặc định có ưu điểm:

- Không có hash code đổi theo generated ID.
- Không truy cập quan hệ lazy trong equals.
- Không phải xử lý các quy tắc so sánh proxy/phân cấp phức tạp.

Nhưng đánh đổi là:

```java
Customer first = em1.find(Customer.class, 42L);
Customer second = em2.find(Customer.class, 42L);

System.out.println(first.equals(second)); // Có thể false.
```

Đối với ứng dụng truyền detached entity, dùng `Set<Entity>` xuyên nhiều Session hoặc so sánh bản managed sau `merge()` với object nguồn, điều này có thể không phù hợp kỳ vọng.

**Nguyên tắc:** không override chỉ là một lựa chọn có chủ đích, không phải lỗi. Chỉ override khi có semantics equality rõ ràng và use case thật sự cần nó.

## 6. Lỗi phổ biến: dùng generated ID mà không kiểm tra null

Giả sử entity:

```java
@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
}
```

Implementation sai:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Product that)) {
        return false;
    }

    return java.util.Objects.equals(id, that.id);
}
```

Hai object mới:

```java
Product a = new Product("Bàn phím");
Product b = new Product("Chuột");

// a.id == null
// b.id == null

System.out.println(a.equals(b)); // true nếu dùng implementation sai.
```

Hai sản phẩm mới **không phải một entity** chỉ vì chưa được cấp khóa. Equality này có thể khiến `HashSet` bỏ mất một phần tử trước khi chúng được lưu.

Hướng xử lý khi dùng generated ID:

- `this == other` luôn được xem là bằng nhau.
- Hai instance khác nhau với ID null **không bằng nhau**.
- Chỉ so sánh ID khi đã khác null.
- Kèm quy tắc kiểm tra loại entity thực tế.

Ví dụ ý tưởng:

```java
if (this == other) {
    return true;
}
if (!(other instanceof Product that)) {
    return false;
}
return getId() != null
    && getId().equals(that.getId());
```

Mẫu này giải quyết **null ID trong equals**, nhưng còn một vấn đề lớn: cách tính `hashCode()`.

## 7. Lỗi thứ hai: hashCode phụ thuộc generated ID thay đổi

Một cách viết dễ nghĩ ra:

```java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
```

Nhưng với entity có generated ID:

```java
Product product = new Product("Bàn phím");

Set<Product> products = new HashSet<>();
products.add(product);

boolean before = products.contains(product); // true

entityManager.persist(product);

boolean after = products.contains(product);
// Có thể false nếu hashCode đổi khi ID được gán.
```

Khi thêm `product`, hash code được tính từ `id == null`. Sau `persist`, ID có thể thành `123`, khiến hash code khác. `HashSet` không tự di chuyển object tới bucket mới.

Một lỗi tương tự xảy ra nếu dùng entity làm khóa của `HashMap`:

```java
Map<Product, String> labels = new HashMap<>();

labels.put(product, "new");
entityManager.persist(product);

String label = labels.get(product); // Có thể null dù key còn trong map.
```

**Quy tắc tổng quát:** không dùng một field có thể đổi trong khi object nằm trong hash collection để tính `hashCode` của object đó.

### Giải pháp thường dùng: hashCode ổn định theo kiểu entity

Với generated ID, một phương án là cho mọi instance cùng một loại entity trả **cùng một hash code** bất kể ID:

```java
@Override
public int hashCode() {
    return Product.class.hashCode();
}
```

Hash code hằng theo loại entity không phân tán đều như hash theo ID, nhưng nó không đổi khi `id` từ null thành giá trị. Vì contract Java chỉ yêu cầu hai object bằng nhau có hash bằng nhau, cách này hợp lệ.

Đánh đổi: nếu đặt hàng trăm nghìn entity cùng loại vào một `HashSet`, nhiều phần tử nằm cùng bucket và hiệu năng có thể kém. Khi collection quá lớn, hãy cân nhắc dữ liệu phù hợp hơn như `Map<Long, DTO>` sau khi ID có sẵn, hoặc business key bất biến.

**Đừng tối ưu phân bố hash bằng cách hy sinh tính đúng đắn.**

## 8. Mẫu equals/hashCode dựa trên generated ID

Đây là một mẫu dành cho **entity không có phân cấp kế thừa phức tạp**, dùng ID `Long` được provider sinh:

```java
import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Product() {
    }

    public Product(String name) {
        this.name = Objects.requireNonNull(name);
    }

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Product that)) {
            return false;
        }

        return getId() != null
            && getId().equals(that.getId());
    }

    @Override
    public int hashCode() {
        return Product.class.hashCode();
    }
}
```

Mẫu trên có các tính chất:

- Hai object mới khác reference, cùng ID null: **không bằng nhau**.
- Một object tự so sánh với chính nó: **bằng nhau**.
- Hai object của `Product` có ID khác null và bằng nhau: **bằng nhau** theo chính sách.
- Hash code **không thay đổi** khi Hibernate gán ID.
- Không sử dụng `name`, vì tên không nhất thiết unique và có thể sửa.

### Giới hạn của kiểm tra `instanceof`

Nếu `Product` có các lớp con entity thật sự và chúng được phép có ID trùng trong những identity space khác nhau, kiểm tra `instanceof Product` có thể quá rộng. Trong một hệ kế thừa, lựa chọn equality phải phù hợp với:

- Cách Hibernate ánh xạ inheritance.
- Việc ID dùng chung giữa các subtype hay không.
- Java proxy có subclass entity hay không.
- Domain có chấp nhận entity con loại khác là cùng danh tính không.

Mẫu trên là lựa chọn thực dụng cho **entity class cụ thể không có hierarchy phức tạp**, không phải công thức đúng tuyệt đối cho mọi hệ entity.

### Vì sao nên dùng getter ID?

Ví dụ dùng `getId()` thay vì trực tiếp `that.id`. Với một Hibernate proxy, identifier có thể được quản lý qua proxy initializer; truy cập field trực tiếp không luôn phản ánh cùng semantics với getter.

Điều đó **không bảo đảm** getter ID sẽ không phát sinh SQL trong mọi version/cấu hình, nhất là nếu proxy bị khởi tạo khi gọi `equals()` hoặc các thiết lập JPA compliance đặc biệt. Cần hiểu cách provider xử lý proxy trong ứng dụng cụ thể.

## 9. Hibernate proxy và kiểm tra loại thực thể

Một association lazy có thể là proxy:

```java
Product reference =
    entityManager.getReference(Product.class, 42L);
```

Ở cơ chế proxy subclass, kiểu runtime của reference có thể khác class Java gốc:

```java
reference.getClass() == Product.class // Có thể false.
```

Vì vậy, implementation dạng:

```java
if (getClass() != other.getClass()) {
    return false;
}
```

có thể so sánh sai **proxy Product** với **instance Product**.

Ngược lại, chỉ dùng `instanceof` trên một root entity có nhiều subtype có thể trộn những loại nghiệp vụ vốn phải phân biệt.

### Một helper Hibernate-specific để lấy entity class qua proxy

Nếu muốn so sánh theo **loại entity thực chất** trong Hibernate, có thể dùng contract `HibernateProxy`:

```java
import org.hibernate.proxy.HibernateProxy;

public final class EntityTypes {
    private EntityTypes() {
    }

    public static Class<?> persistentClass(Object entity) {
        if (entity instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                .getPersistentClass();
        }
        return entity.getClass();
    }
}
```

Trong trường hợp proxy chuẩn, helper trên lấy class entity được proxy đại diện thay vì subclass runtime. API/chi tiết có thể khác theo phiên bản và bytecode enhancement; code phụ thuộc vào Hibernate, không còn di động thuần Jakarta Persistence.

Không nên mặc định thay bằng `Hibernate.getClass(proxy)` mà chưa đọc Javadoc của version đang dùng: một số API lấy class có thể cần **initialize proxy** và có tác dụng phụ về SQL. Nếu tránh lazy initialization là yêu cầu, phải hiểu rõ contract cụ thể.

### Mẫu dựa trên generated ID và persistent class

Với một **entity không có semantics equality xuyên các subtype**:

```java
import org.hibernate.proxy.HibernateProxy;

@Entity
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    protected Product() {
    }

    public Long getId() {
        return id;
    }

    private static Class<?> entityClass(Object object) {
        return object instanceof HibernateProxy proxy
            ? proxy.getHibernateLazyInitializer()
                   .getPersistentClass()
            : object.getClass();
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (other == null
                || entityClass(this) != entityClass(other)) {
            return false;
        }

        Product that = (Product) other;

        return getId() != null
            && getId().equals(that.getId());
    }

    @Override
    public int hashCode() {
        return entityClass(this).hashCode();
    }
}
```

Ý tưởng:

- Entity type được xác định nhất quán cho object thật và proxy Hibernate tiêu chuẩn.
- Chỉ so sánh ID khi khác null.
- `hashCode()` ổn định theo persistent class, không phụ thuộc ID.

**Lưu ý kỹ thuật:** proxy có thể intercept lời gọi `equals()`, và behavior initialization còn phụ thuộc cách bytecode/proxy được tạo. Ví dụ này là chiến lược equality ở tầng ứng dụng, không phải lời cam kết “gọi equals trên proxy luôn không truy vấn”. Một hệ kế thừa phức tạp cần chính sách riêng.

### Quan hệ với `getReference()` và `find()`

Khi một Session có entity đã managed, Hibernate có thể dùng cùng reference identity cho các lần lấy cùng ID. Khi so sánh giữa các Session, một bên có thể là proxy chưa initialize và một bên là entity loaded.

Vì vậy, nếu nghiệp vụ thật sự yêu cầu equality giữa các Session, cần xem proxy là một phần của mô hình kiểm thử chứ không chỉ thử với hai object `new`.

## 10. Business key bất biến: khi nào phù hợp hơn ID?

Đôi khi entity có một natural key tồn tại ngay từ khi tạo object và không được phép đổi trong suốt vòng đời.

Ví dụ `Country` có mã ISO hai chữ cái được chuẩn hóa:

```java
import jakarta.persistence.*;
import java.util.Locale;
import java.util.Objects;

@Entity
@Table(
    name = "countries",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_country_iso",
        columnNames = "iso_code"
    )
)
public class Country {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(
        name = "iso_code",
        nullable = false,
        updatable = false,
        length = 2
    )
    private String isoCode;

    @Column(nullable = false)
    private String displayName;

    protected Country() {
    }

    public Country(String isoCode, String displayName) {
        if (isoCode == null || !isoCode.matches("[A-Za-z]{2}")) {
            throw new IllegalArgumentException("Invalid ISO code");
        }
        this.isoCode = isoCode.toUpperCase(Locale.ROOT);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public String getIsoCode() {
        return isoCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Country that)) {
            return false;
        }
        return Objects.equals(
            getIsoCode(), that.getIsoCode()
        );
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(getIsoCode());
    }
}
```

Trong ví dụ, `isoCode`:

1. Được gán ngay khi tạo entity.
2. Được chuẩn hóa theo một quy tắc nhất quán.
3. Không có public setter.
4. Có ràng buộc unique trong database.
5. Không phụ thuộc vào ID sinh tự động.
6. Có ý nghĩa nghiệp vụ bền vững, khác `displayName`.

Nhờ đó, `hashCode()` không phải thay đổi sau `persist()`.

### “Không có setter” chưa đủ để chứng minh bất biến

`@Column(updatable = false)` có thể khiến Hibernate bỏ cột khỏi SQL `UPDATE` trong đường ghi ORM thông thường, nhưng nó **không tự ngăn Java code/reflection sửa field**, không tự ngăn SQL trực tiếp đổi giá trị, và không bảo đảm uniqueness nếu schema thật không có constraint.

Để dùng business key làm equality, cần bảo vệ bất biến ở **tầng domain, mapping và schema thực tế**. Nếu business key có thể bị đổi bởi migration, quy trình vận hành phải hiểu tác động tới cache và các đối tượng đang ở trong hash collection.

### Khi business key có thể đổi

Email đăng nhập là ví dụ điển hình:

```java
private String email;
```

Ngay cả khi email unique ở một thời điểm, người dùng có thể đổi email; địa chỉ cũ có thể được cấp cho người khác. Khi dùng email trong `hashCode`, thay đổi email làm `HashSet` và `HashMap` gặp lỗi tương tự generated ID.

Vì vậy, **unique không đồng nghĩa immutable**. Muốn dùng email làm danh tính, domain phải thực sự cam kết email không bao giờ thay đổi hoặc có một identifier bền vững khác.

## 11. Business key gồm nhiều thuộc tính

Một business key đôi khi phải là **tổ hợp các trường**, không có trường đơn lẻ nào unique.

Ví dụ mã sản phẩm từ hệ thống ngoài chỉ unique trong phạm vi nhà cung cấp:

```text
supplierCode = "SUP-01"
externalSku  = "A-100"
```

Cặp `(supplierCode, externalSku)` mới xác định sản phẩm.

Entity minh họa:

```java
@Entity
@Table(
    name = "supplier_products",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_supplier_product",
        columnNames = {"supplier_code", "external_sku"}
    )
)
public class SupplierProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "supplier_code", nullable = false, updatable = false)
    private String supplierCode;

    @Column(name = "external_sku", nullable = false, updatable = false)
    private String externalSku;

    protected SupplierProduct() {
    }

    public SupplierProduct(String supplierCode, String externalSku) {
        this.supplierCode = java.util.Objects.requireNonNull(supplierCode);
        this.externalSku = java.util.Objects.requireNonNull(externalSku);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof SupplierProduct that)) {
            return false;
        }
        return java.util.Objects.equals(
                supplierCode, that.supplierCode)
            && java.util.Objects.equals(
                externalSku, that.externalSku);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(supplierCode, externalSku);
    }
}
```

Cặp thuộc tính này chỉ phù hợp khi:

- Cả hai được cấp trước khi object vào hash collection.
- Cả hai không đổi trong vòng đời thực thể.
- Có constraint unique đúng phạm vi.
- Chuẩn hóa khoảng trắng, case, Unicode hoặc ký hiệu nếu hệ thống yêu cầu.
- Không có hai entity type khác nhau bị so sánh nhập nhằng.

Nếu `supplierCode` là một `@ManyToOne` entity thay vì chuỗi, không nên máy móc đưa cả `Supplier` entity vào `equals`. Có thể chọn một mã bất biến hoặc một value object chứa định danh ổn định, tránh kích hoạt lazy loading.

### Multi-tenant và business key

Một `externalSku` có thể unique trong **một tenant**, không phải toàn hệ thống. Khi định nghĩa equality xuyên tenant, cần xét khóa nghiệp vụ gồm tenant:

```text
(tenantId, supplierCode, externalSku)
```

Nếu hai object ở tenant khác nhau có cùng `supplierCode` và `externalSku`, nhưng `equals` bỏ qua tenant, chúng có thể bị coi là một thực thể.

Bởi vậy, “unique” phải luôn được hiểu kèm **phạm vi**, không chỉ theo tên field.

## 12. `@NaturalId` liên quan gì đến equals/hashCode?

Hibernate có annotation riêng `@NaturalId` để mô tả định danh tự nhiên:

```java
import org.hibernate.annotations.NaturalId;

@NaturalId(mutable = false)
@Column(nullable = false, unique = true, updatable = false)
private String isoCode;
```

Natural ID giúp Hibernate hiểu một số cách tra cứu và có thể tích hợp với cơ chế cache natural-id khi được cấu hình. Nhưng:

- **`@NaturalId` không tự tạo `equals()` hoặc `hashCode()`.**
- Nó **không bắt buộc** ứng dụng phải dùng trường ấy cho Java equality.
- `mutable = false` mô tả ý định bất biến ở mapping; không thay thế toàn bộ ràng buộc hoặc quy tắc domain.
- Với natural ID có thể thay đổi (`mutable = true`), dùng nó trong `hashCode` sẽ nguy hiểm nếu entity nằm trong hash collection trước khi thay đổi.

Ví dụ tra cứu theo natural ID trong Hibernate API:

```java
Country country = session.bySimpleNaturalId(Country.class)
    .load("VN");
```

Đây là một cách tìm entity theo natural ID, **khác** với việc định nghĩa equality của Java object.

### Có thể dùng `@NaturalId` mutable làm equality không?

Cần rất thận trọng. Nếu một trường được phép đổi, entity vẫn là cùng entity nghiệp vụ dù mã tự nhiên thay đổi. Equality theo giá trị mới có thể thay đổi giữa hai thời điểm và gây vấn đề với `Set`/`Map`.

Trong đa số trường hợp có natural ID mutable, khóa kỹ thuật không đổi hoặc một business identity khác bất biến thường phù hợp hơn để biểu diễn danh tính dài hạn.

## 13. Assigned ID và UUID do ứng dụng tạo

Nếu ID được gán **trước khi entity có thể tham gia collection**, việc dùng ID trong `equals/hashCode` đơn giản hơn.

Ví dụ UUID tạo trong constructor:

```java
import java.util.UUID;
import jakarta.persistence.*;

@Entity
public class AuditEvent {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String eventType;

    protected AuditEvent() {
    }

    public AuditEvent(String eventType) {
        this.id = UUID.randomUUID();
        this.eventType = eventType;
    }

    public UUID getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof AuditEvent that)) {
            return false;
        }
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(id);
    }
}
```

ID ở đây là **assigned UUID**, được cấp trong constructor ứng dụng. Vì vậy, object mới hợp lệ có ID ngay khi được tạo và hash theo ID có thể ổn định.

Nhưng cần nhớ:

- JPA vẫn cần constructor không tham số; object được Hibernate dựng từ database sẽ nhận ID qua persistence mechanism.
- Code không được đổi `id` sau khi tạo object.
- Một số luồng thử nghiệm/deserialization có thể tạo object không hợp lệ với ID null; cần quy tắc xử lý rõ.
- Nếu ứng dụng đổi sang `@GeneratedValue(strategy = UUID)` mà ID **không có sẵn cho đến khi gọi `persist`**, hash theo ID lại có nguy cơ đổi.

**Không phải “UUID” tự làm hash ổn định; vấn đề là **ID được gán khi nào** và sau đó có bất biến hay không.**

### ID do đối tác cấp

Nếu khóa là `externalId` do hệ thống bên ngoài cấp, cần chắc chắn:

- Không trùng trong phạm vi dữ liệu dự kiến.
- Không bị đối tác tái sử dụng khi một bản ghi bị xóa.
- Không đổi khi đối tác sửa mã hiển thị.
- Được chuẩn hóa nhất quán trước khi dùng vào equals.

Một mã nhìn có vẻ như ID nhưng vẫn đổi theo thời gian thì không đủ ổn định cho hashing.

## 14. Khóa tổng hợp: `@EmbeddedId` và equals/hashCode

Với entity có **composite primary key**, cách thiết kế equality thường tách thành hai vấn đề:

1. **Lớp khóa** `@Embeddable` phải có `equals()/hashCode()` nhất quán với các thành phần khóa.
2. **Entity** có thể dùng khóa đó cho equality, với điều kiện khóa là danh tính ổn định và được gán đúng thời điểm.

Ví dụ một dòng kết quả có khóa gồm `studentId` và `courseId`:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class EnrollmentId implements Serializable {

    private Long studentId;
    private Long courseId;

    protected EnrollmentId() {
    }

    public EnrollmentId(Long studentId, Long courseId) {
        this.studentId = Objects.requireNonNull(studentId);
        this.courseId = Objects.requireNonNull(courseId);
    }

    public Long getStudentId() {
        return studentId;
    }

    public Long getCourseId() {
        return courseId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof EnrollmentId that)) {
            return false;
        }
        return Objects.equals(studentId, that.studentId)
            && Objects.equals(courseId, that.courseId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(studentId, courseId);
    }
}
```

Entity:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "enrollments")
public class Enrollment {

    @EmbeddedId
    private EnrollmentId id;

    @Column(nullable = false)
    private String status;

    protected Enrollment() {
    }

    public Enrollment(EnrollmentId id, String status) {
        this.id = id;
        this.status = status;
    }

    public EnrollmentId getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof Enrollment that)) {
            return false;
        }
        return id != null && id.equals(that.getId());
    }

    @Override
    public int hashCode() {
        return id == null ? 0 : id.hashCode();
    }
}
```

Ở ví dụ này, `EnrollmentId` được tạo đủ hai thành phần **trước** khi entity tham gia collection và không được phép thay đổi trong domain. Khi bảo đảm điều kiện ấy, hash theo composite ID là phù hợp.

Nếu khóa có thể được bổ sung muộn (`studentId` ban đầu null, sau đó mới cấp), `hashCode` của entity có thể đổi. Trong tình huống đó cần thiết kế lại thời điểm gán khóa hoặc dùng chiến lược hash ổn định như với generated ID.

### `@IdClass` thì sao?

Với `@IdClass`, lớp khóa cũng cần triển khai `equals()/hashCode()` đúng trên các thành phần khóa. Entity vẫn có thể cần chính sách equality riêng nếu ứng dụng sử dụng nó trong collection. Không nên dựa vào `@IdClass` để Hibernate “tự sửa” phương thức `equals` của entity.

### Tránh dùng entity object làm thành phần khóa khi không cần

Composite key bền vững thường dễ xử lý hơn nếu chứa các scalar ID hoặc value object ổn định. Đưa nguyên association lazy vào equality của khóa có thể làm phép so sánh phức tạp và phát sinh truy vấn.

Nếu mapping dùng `@MapsId`, cần hiểu khi nào các thành phần ID trở nên có giá trị và tránh đặt entity vào hash collection trước thời điểm khóa đã ổn định.

## 15. Không đưa collection và quan hệ lazy vào equality

Giả sử:

```java
@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    private String status;
}
```

Implementation so sánh tất cả field:

```java
return Objects.equals(id, that.id)
    && Objects.equals(customer, that.customer)
    && Objects.equals(lines, that.lines)
    && Objects.equals(status, that.status);
```

có nhiều vấn đề:

- `status` thay đổi trong vòng đời đơn hàng nhưng không làm đơn hàng trở thành một thực thể khác.
- `customer` có thể là proxy, gọi `equals` trên nó có thể dẫn tới khởi tạo lazy.
- `lines` là collection mutable; thêm/xóa một dòng khiến equality/hash thay đổi.
- `OrderLine` có thể tham chiếu ngược `Order`, dẫn tới đệ quy khi so sánh toàn graph.
- Hai object đại diện cùng Order ID có thể giữ trạng thái lines khác nhau ở hai Session, khiến equals trả false.
- Chỉ để so sánh hai Order, chương trình có thể phát sinh hàng loạt SQL hoặc `LazyInitializationException` khi Session đã đóng.

**Nguyên tắc:** trong entity, các quan hệ và thuộc tính trạng thái mutable thường **không thuộc danh tính** và không nên được đưa vào `equals()/hashCode()`.

### Ngoại lệ có chủ đích

Một business key có thể bao gồm **mã bất biến của một entity liên quan** — ví dụ `(issuerCode, documentNumber)`. Khi đó nên biểu diễn khóa bằng scalar/value object phù hợp thay vì so sánh toàn bộ entity `Issuer` và gọi `issuer.getDocuments()`.

Nếu domain thật sự định nghĩa danh tính thông qua quan hệ, cần đảm bảo việc lấy thành phần khóa không gây lazy access ngoài ý muốn và có semantics bất biến. Đây là quyết định mô hình hóa nghiêm túc, không nên suy ra tự động từ `@ManyToOne`.

## 16. Tránh đưa thuộc tính mutable và trường quản lý bởi Hibernate vào hashCode

Các trường sau thường không nên dùng:

### 16.1. `@Version`

```java
@Version
private long version;
```

Giá trị version có thể tăng mỗi lần cập nhật. Nếu hash dựa vào version, một entity đang nằm trong `HashSet` có thể trở nên không tìm thấy sau flush.

Ngoài ra, hai instance cùng entity ID có thể giữ version khác nhau do tải tại các thời điểm khác nhau; đó không biến chúng thành hai entity khác.

### 16.2. Timestamp

```java
private Instant createdAt;
private Instant updatedAt;
```

`createdAt` có thể được gán trong callback hoặc do database khi insert. `updatedAt` có thể thay đổi mỗi lần update. Cả hai không mặc nhiên xác định danh tính, và thường không unique.

### 16.3. Trạng thái mềm/xóa mềm

```java
private boolean deleted;
private boolean active;
```

Một entity vẫn là cùng một identity dù được vô hiệu hóa hoặc đánh dấu xóa mềm. Nếu equality thay đổi theo `deleted`, cùng một row có thể bị xem như một object khác khi trạng thái thay đổi.

### 16.4. Tên, mô tả, giá, số lượng

Các trường này thuộc **trạng thái** entity; chúng có thể thay đổi mà không thay đổi danh tính. Không dùng chúng chỉ vì IDE có nút “Generate equals/hashCode from all fields”.

### 16.5. Các kiểu số thập phân có semantics riêng

Nếu business key thực sự chứa `BigDecimal`, cần hiểu `BigDecimal.equals` xét cả scale:

```java
new BigDecimal("2.0").equals(new BigDecimal("2.00")) // false
```

Một khóa nghiệp vụ cần so sánh theo giá trị số có thể cần chuẩn hóa scale và dùng một dạng biểu diễn ổn định. Tuy nhiên, **không tự thay bằng `compareTo` trong equals mà quên thiết kế hash tương ứng**, vì khi `equals` coi hai giá trị bằng nhau thì `hashCode` bắt buộc như nhau.

Với các business key chứa chuỗi, quy tắc normalize/collation Unicode, case và khoảng trắng cũng quan trọng tương tự.

## 17. Lombok trên entity: tiện nhưng dễ sinh sai semantics

Lombok giúp giảm boilerplate Java, nhưng một số annotation có thể sinh equality không mong muốn cho entity.

Ví dụ:

```java
@Data
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @OneToMany(mappedBy = "customer")
    private Set<Order> orders;
}
```

`@Data` thường tạo `equals()`, `hashCode()` và `toString()` dựa trên các fields theo quy tắc Lombok. Những field như `id` sinh muộn, `name` mutable và `orders` lazy khiến implementation mặc định khó phù hợp cho entity.

Các tác động có thể là:

- Hai transient entity có ID null bị coi bằng nhau theo cách không mong muốn.
- Thay đổi trạng thái làm hash thay đổi.
- `equals` hoặc `toString` đi vào collection lazy.
- Quan hệ hai chiều `Customer ↔ Order` có thể dẫn tới recursion.
- Những truy vấn không được dự tính xuất hiện trong log hoặc JSON serialization.

### Cách dùng Lombok có chủ đích

Có thể chỉ dùng:

```java
@Getter
@Setter
@Entity
public class Customer {
    // ...
}
```

rồi tự định nghĩa `equals/hashCode` theo danh tính. Nếu dùng `@EqualsAndHashCode(onlyExplicitlyIncluded = true)`, cần hiểu rằng việc include generated ID **không tự giải quyết** chuyện null ID hoặc hash đổi sau persist.

Ví dụ:

```java
@EqualsAndHashCode(onlyExplicitlyIncluded = true)
public class Customer {

    @EqualsAndHashCode.Include
    private Long id;
}
```

Mã kiểu này có thể có semantics không mong muốn với hai transient entity cùng ID null. Việc “chỉ include ID” **không bằng** mẫu an toàn “ID phải khác null và hash ổn định”.

Đối với entity nhiều quan hệ, viết equality tường minh thường dễ kiểm soát và dễ giải thích hơn việc dựa vào cấu hình sinh mã tự động.

## 18. Quan hệ với Set, List, Map của Hibernate

Java collection có yêu cầu khác nhau:

| Collection | Phụ thuộc equals/hashCode của phần tử? | Lưu ý |
|---|---|---|
| `HashSet` | Có | Hash phải ổn định khi phần tử còn trong tập |
| `HashMap<Entity, V>` | Có, với key entity | Đổi hash của key gây lỗi tìm kiếm |
| `TreeSet` | Phụ thuộc comparator/Comparable | Comparator phải nhất quán và ổn định; thay đổi sort key cũng gây lỗi |
| `ArrayList` | `contains`/`remove(Object)` dùng equals | Không dùng hash để định bucket, nhưng equality sai vẫn gây hành vi sai |
| Hibernate persistent `Set` | Có thể phụ thuộc equality trong quản lý collection và hoạt động Java | Generated ID/null ID có thể ảnh hưởng tập con trước khi persist |
| Hibernate persistent `List` | Có thể dùng equals trong các thao tác Java; thứ tự lưu DB là vấn đề khác | Không mặc nhiên giải quyết ownership/cascade/lifecycle |

### Ví dụ hai child mới trong HashSet

```java
OrderLine a = new OrderLine("SKU-01", 1);
OrderLine b = new OrderLine("SKU-02", 2);

Set<OrderLine> lines = new HashSet<>();
lines.add(a);
lines.add(b);
```

Nếu `OrderLine.equals` chỉ so sánh `id` và cả hai ID null thì bị coi bằng nhau, tập có thể chỉ còn **một phần tử** trước khi Hibernate persist. Đây có thể là lỗi mất dữ liệu nghiệp vụ trước cả khi chạy SQL.

### Khi nào nên dùng List?

Nếu các child có danh tính chưa được cấp và business rule cần lưu nhiều phần tử mới, `List` thường ít phụ thuộc vào hash của phần tử hơn `HashSet`. Nhưng `List` không chữa được tất cả vấn đề:

- `remove(Object)` vẫn gọi `equals`.
- Có thể có duplicate nếu domain không cho phép.
- Thứ tự trong database cần mapping/column/order phù hợp.
- Cần đồng bộ cả hai phía của quan hệ bidirectional.

Lựa chọn collection dựa trên **ngữ nghĩa domain**, không chỉ để tránh sửa `equals`.

### Dùng ID hoặc immutable key trong Map

Thay vì:

```java
Map<Customer, DiscountRule> rules;
```

có thể dùng:

```java
Map<Long, DiscountRule> rulesByCustomerId;
```

sau khi mọi Customer đã có ID ổn định. Khi ứng dụng đa tenant, key có thể cần là composite `(tenantId, customerId)` để không trộn dữ liệu.

Nếu đang xử lý entity mới chưa có ID, nên dùng một key nghiệp vụ bất biến đã được xác định, hoặc giữ một cấu trúc danh sách tạm thời trước khi hoàn tất persistence.

## 19. Entity, value object và DTO có equality khác nhau

Entity khác value object:

- **Entity:** danh tính tồn tại xuyên qua các lần thay đổi trạng thái.
- **Value object:** thường được xem là bằng nhau khi toàn bộ **giá trị có ý nghĩa** bằng nhau, lý tưởng là bất biến.
- **DTO/projection:** chủ yếu truyền dữ liệu, có thể dùng equality theo giá trị nếu phù hợp use case.

Ví dụ value object:

```java
import java.math.BigDecimal;

public record Money(BigDecimal amount, String currency) {
}
```

Java record tự sinh `equals/hashCode` theo components. Với value object bất biến, đó thường là semantics tự nhiên.

Nhưng entity:

```java
@Entity
public class Invoice {
    @Id
    private Long id;

    private BigDecimal total;

    private String status;
}
```

không nên coi hai Invoice bằng nhau chỉ vì `total` và `status` giống nhau. Hai hóa đơn khác nhau có thể cùng số tiền và trạng thái, còn một hóa đơn có thể đổi tổng tiền/trạng thái mà vẫn là cùng hóa đơn.

### Đừng dùng record như một entity JPA truyền thống

Java record có final fields và cấu trúc lớp bất biến theo thiết kế, không đáp ứng nguyên vẹn các yêu cầu của entity JPA thông thường như constructor phù hợp, proxy và persistence enhancement. Record thường phù hợp hơn cho **DTO hoặc value object**. Khi dùng Hibernate version có hỗ trợ record trong các trường hợp đặc thù, cần đối chiếu API/cấu hình; đừng mặc định record là lựa chọn thay thế cho mọi entity.

## 20. Equality, merge và detached objects

Một tình huống khiến ứng dụng muốn override equals là thao tác `merge`:

```java
Customer detached = ...; // Object từ Session đã đóng.

Customer managed = entityManager.merge(detached);
```

Hợp đồng `merge` trả về **managed instance**; object truyền vào không tự trở thành managed chỉ vì lời gọi này.

Do đó:

```java
System.out.println(detached == managed); // Có thể false.
```

Nếu cả hai biểu diễn cùng entity ID, business logic có thể muốn:

```java
System.out.println(detached.equals(managed)); // true theo ID policy.
```

Nhưng cũng cần hiểu:

- `equals` không làm detached entity tự được đồng bộ với managed entity.
- Hai object có cùng ID không có nghĩa trạng thái fields của chúng giống nhau.
- `merge` có thể ghi đè một số trạng thái managed dựa trên detached state theo semantics JPA và mapping.
- `equals` không thay thế optimistic locking với `@Version`.
- Sau rollback, ID được cấp vẫn có thể còn trên object, dù insert/update chưa commit.

**Equality trả lời “có xem là cùng identity không?”, không trả lời “dữ liệu có mới nhất, đã persist hoặc đã commit chưa?”.**

## 21. Sự tồn tại trong database khác equality của entity

Giả sử:

```java
Product oldProduct = em.find(Product.class, 42L);
em.remove(oldProduct);
```

Ở Java, `oldProduct.getId()` có thể vẫn là `42`. Nếu có một instance khác cũng mang ID 42, chính sách `equals` theo ID có thể xem hai object bằng nhau.

Điều đó **không chứng minh** hàng 42 còn tồn tại hoặc chưa bị xóa. `equals` không phải lệnh kiểm tra tồn tại. Cũng không nên gọi database trong `equals` để “xác nhận” identity; làm vậy khiến phép so sánh có tác dụng phụ, phụ thuộc transaction và rất khó dùng trong collection.

Khi cần kiểm tra persistence state trong **EntityManager hiện tại**:

```java
boolean managedHere = em.contains(product);
```

`contains` cho biết instance có được context này quản lý không, không xác nhận transaction đã commit.

Khi cần kiểm tra hàng tồn tại hoặc tính hợp lệ nghiệp vụ, hãy truy vấn/kiểm tra bằng service theo một transaction và quyền truy cập thích hợp.

## 22. Kế thừa entity và phạm vi identity

Một ID đơn lẻ có thể không đủ để phân biệt hai entity loại khác nhau:

```text
Customer(id = 10)
Supplier(id = 10)
```

Chúng có cùng số `10`, nhưng là hai loại entity riêng và không nên bằng nhau.

Đó là lý do chính sách ID-based thường bao gồm **entity type**, ít nhất ở mức tương đương persistent class.

### Entity inheritance có thể làm quy tắc phức tạp hơn

Giả sử:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {
    @Id
    private Long id;
}

@Entity
public class CardPayment extends Payment {}

@Entity
public class BankTransfer extends Payment {}
```

Ở một hierarchy JPA với identity chung, hai subtype có thể chia sẻ cùng bảng gốc và cùng dải ID. Nếu muốn equality theo **persistent identity của root hierarchy**, chính sách cần xử lý thống nhất root type + ID.

Nhưng nếu root `Payment` có proxy được tạo trước khi subtype cụ thể được biết đầy đủ, việc so sánh dựa tuyệt đối vào **concrete runtime class** có thể không diễn đạt đúng kỳ vọng trong mọi tình huống. Ngược lại, dùng `instanceof Payment` quá rộng có thể gộp hai đối tượng được coi là khác danh tính trong một thiết kế khác.

Vì thế, đối với entity inheritance:

1. Xác định identity được chia sẻ ở **root hierarchy** hay cần phân biệt subtype.
2. Đảm bảo `equals` là **symmetric** giữa root/proxy/subtype.
3. Đảm bảo tất cả subtype dùng **cùng nguyên tắc hashCode** khi equality có thể coi chúng là bằng nhau.
4. Tránh override `equals` khác nhau ở root và subclass mà không thiết kế một contract chung.

Không có công thức “luôn `getClass()`” hoặc “luôn `instanceof`” cho mọi hierarchy. Phạm vi danh tính phải được xác định từ mapping và domain.

## 23. Tách identity khỏi dữ liệu trình bày và state

Một thiết kế entity có thể gồm:

```java
@Id
@GeneratedValue
private Long id;

@Column(nullable = false)
private String displayName;

private boolean active;

@Version
private long version;

@ManyToOne(fetch = FetchType.LAZY)
private Department department;
```

Nếu cả bốn yếu tố trên có thể thay đổi ngoài `id`, thì quyết định equality theo ID (khi khác null) thường phản ánh đúng việc entity vẫn là **cùng một người dùng/đơn vị** sau cập nhật.

Nếu dùng business key bất biến, key ấy có thể thay ID trong equality, nhưng các trường trình bày/state vẫn nên bị loại khỏi phép so sánh.

### Không nên dùng timestamp hoặc surrogate ID như “thứ tự” để so sánh domain

Một ID tăng dần không phải là chứng cứ của thứ tự commit; một timestamp không phải chứng cứ unique. `equals` nên dựa trên identity, không dựa trên những giá trị gần giống identity vì dễ sinh trùng hoặc thiếu ổn định.

### Soft delete và tái sử dụng business key

Nếu business key có thể được **tái sử dụng sau khi entity bị soft delete**, hai object từ hai thời kỳ có thể cùng key nhưng đại diện hai bản ghi khác nhau.

Ví dụ mã khách hàng `C-001` đã bị vô hiệu, sau đó hệ thống tạo Customer mới cũng có mã `C-001`. Nếu equality chỉ theo mã, hai entity sẽ bị coi bằng nhau dù domain có thể yêu cầu khác.

Khi chọn business key cho equality, phải xem policy **tái sử dụng** và uniqueness theo thời gian, không chỉ uniqueness ở thời điểm hiện tại.

## 24. Đừng đưa equals/hashCode vào service như một phép truy vấn

Một implementation có thể cố so sánh entity bằng cách gọi database mỗi lần:

```java
@Override
public boolean equals(Object other) {
    // Không nên làm:
    // return repository.findById(id).equals(...);
    return false;
}
```

Đây là một anti-pattern vì:

- `equals` có thể được Java collections gọi rất nhiều lần.
- Việc so sánh có thể xảy ra ngoài transaction.
- Ném exception/IO khi tính hash hoặc equals làm collection hoạt động khó dự đoán.
- Nhiều lần equals có thể quan sát trạng thái database khác nhau, gây vấn đề consistency.
- Entity và repository bị coupling vòng, khó kiểm thử.

Equality nên dựa trên **những giá trị identity có sẵn trong object** hoặc thông tin proxy định danh được hỗ trợ, không cần truy vấn nghiệp vụ mới.

Nếu cần trả lời “hai bản ghi có cùng khách hàng theo dữ liệu hiện tại không?”, đó là **business query/service operation**, không nên giấu vào `equals`.

## 25. Cách quyết định theo từng tình huống thực tế

| Tình huống | Hướng lựa chọn | Vì sao |
|---|---|---|
| Entity chỉ dùng trong một persistence context, không cần so sánh giữa Session | Có thể giữ `Object.equals/hashCode` | Đơn giản, không phụ thuộc generated ID |
| Generated `Long` ID, cần so sánh detached với managed cùng hàng | `equals` theo ID khác null + entity type; `hashCode` ổn định | Tránh null ID và hash đổi |
| Business key bất biến, unique, non-null từ constructor | Dùng business key trong cả `equals/hashCode` | Có identity trước persist và hash ổn định |
| Assigned UUID tạo ngay trong constructor và không đổi | Có thể dùng UUID cho cả hai | ID tồn tại sớm và ổn định |
| UUID do Hibernate sinh sau khi tạo object | Xem như generated ID | Hash theo UUID có thể đổi khi `persist` |
| Composite ID đã cấp đầy đủ, bất biến | Lớp khóa implement equality; entity có thể dùng composite ID | Danh tính gồm nhiều thành phần ổn định |
| Email hoặc tên có thể sửa | Không dùng làm hash/equality | Mutable và có thể tái sử dụng |
| Entity có nhiều lazy association | Không đưa association/collection vào equality | Tránh N+1, recursion, lazy initialization |
| Hệ kế thừa entity/proxy phức tạp | Thiết kế chung theo phạm vi identity của hierarchy | Tránh vi phạm symmetry/transitivity |
| Dữ liệu multi-tenant hoặc multi-database | Xét tenant/source trong phạm vi identity | ID có thể trùng giữa các vùng |

### Quy trình ra quyết định

**Bước 1 — Xác định ý nghĩa “cùng thực thể”.**  
Hai instance từ hai Session cùng ID có cần được coi là bằng nhau không? Nếu không, giữ reference identity có thể đủ.

**Bước 2 — Tìm identity bất biến có ngay khi tạo.**  
Có natural key unique và không đổi trong cả vòng đời không? Nếu có, đây là ứng viên tốt. Nếu không, cân nhắc generated ID.

**Bước 3 — Xác định thời điểm ID có giá trị.**  
Nếu ID do Hibernate sinh sau khi object đã xuất hiện, không hash trực tiếp theo ID trừ khi có quy tắc sử dụng collection rất chặt mà ứng dụng bảo đảm được.

**Bước 4 — Xác định phạm vi entity type và tenant.**  
Phải phân biệt các bảng/hierarchy/tenant có thể trùng khóa.

**Bước 5 — Loại khỏi equality mọi field mutable/lazy không mang identity.**  
Tránh collection, version, timestamp, state, label và những association chỉ mang thông tin tham chiếu.

**Bước 6 — Thiết kế equals và hashCode cùng nhau.**  
Nếu equals coi hai instance bằng nhau theo ID, hashCode của chúng phải bằng nhau. Nếu ID được sinh muộn, hashCode cần ổn định trước/sau persist.

**Bước 7 — Xem xét proxy và detached behavior.**  
Đừng giả định `getClass()` trên proxy giống entity class; cũng đừng dùng `instanceof` quá rộng trong hierarchy có semantics riêng.

**Bước 8 — Giữ contract lâu dài.**  
Khi chọn business key, phải có quy tắc không đổi, uniqueness, normalization và xử lý migration phù hợp.

## 26. Các ví dụ sai và cách sửa

### Sai 1: Hai transient entity bằng nhau vì ID null

```java
@Override
public boolean equals(Object o) {
    return o instanceof User that
        && Objects.equals(id, that.id);
}
```

**Sửa:** yêu cầu `id != null`, hoặc dùng business key bất biến nếu có.

### Sai 2: Hash theo ID mới sinh

```java
@Override
public int hashCode() {
    return Objects.hash(id);
}
```

**Sửa:** với generated ID được gán muộn, dùng hash ổn định theo loại entity hoặc một chiến lược khác có tính bất biến thực sự.

### Sai 3: Hash theo email được đổi

```java
@Override
public int hashCode() {
    return email.toLowerCase().hashCode();
}
```

**Sửa:** nếu email mutable, không dùng nó làm identity trong hash; tìm khóa kỹ thuật hoặc business key khác không đổi. Normalization không giải quyết vấn đề mutable.

### Sai 4: So sánh toàn object graph

```java
return Objects.equals(orders, that.orders)
    && Objects.equals(profile, that.profile);
```

**Sửa:** không dùng collection/association lazy như danh tính, trừ một thiết kế domain rất đặc biệt được kiểm soát đầy đủ.

### Sai 5: Dùng `getClass` trên proxy subclass

```java
if (getClass() != other.getClass()) {
    return false;
}
```

**Sửa:** xác định loại entity persistent nhất quán với cơ chế Hibernate proxy và inheritance đang dùng, hoặc chọn mẫu `instanceof` phù hợp cho concrete class không có hierarchy phức tạp.

### Sai 6: Dùng `@EqualsAndHashCode` Lombok chỉ include ID sinh muộn

Việc sinh code tự động không loại bỏ yêu cầu null ID khác nhau và hash ổn định.

**Sửa:** viết logic entity equality có chủ đích; nếu dùng Lombok, cần kiểm soát method được sinh ra và hợp đồng của nó thay vì tin rằng annotation chọn field là đủ.

### Sai 7: Dùng `@Version` trong hashCode

```java
return Objects.hash(id, version);
```

**Sửa:** version đại diện trạng thái concurrency, không phải danh tính. Không đưa version vào equality/hash.

## 27. Những trường hợp cần đưa vào bài kiểm tra thiết kế

Khi tự kiểm chứng lựa chọn equality ở một module, các tình huống quan trọng gồm:

1. Hai entity mới khác instance, cả hai ID null.
2. Một entity tự so sánh với chính nó.
3. Một entity được thêm vào `HashSet` trước khi `persist`, sau đó ID được sinh.
4. Hai entity có cùng ID nhưng được lấy từ **hai Session khác nhau**.
5. Một managed entity và một detached entity cùng ID.
6. Một proxy từ `getReference` và một entity có dữ liệu đã nạp.
7. Entity với business key được normalize cùng quy tắc ở constructor và khi load DB.
8. Entity đổi tên, trạng thái, version hoặc association nhưng vẫn giữ identity.
9. Hai entity khác loại có cùng giá trị ID.
10. Hai entity thuộc tenant khác nhau có ID giống nhau, nếu tenant là một phần của phạm vi identity.
11. Hai subtype trong hierarchy theo chính sách equality đã chọn.
12. Composite key được gán trước khi entity vào collection và không đổi về sau.

Một số phép kiểm tra thuần Java có thể minh họa contract:

```java
Product first = new Product("A");
Product second = new Product("B");

assert !first.equals(second);
assert first.equals(first);

Set<Product> set = new HashSet<>();
set.add(first);

// Sau khi persist làm ID được sinh, cần kỳ vọng:
assert set.contains(first);
```

Ví dụ nhằm mô tả tình huống cần bảo đảm; trong môi trường thật phải có transaction, mapping và database tương ứng để thực hiện phần `persist`. Với proxy, nên có integration test trên Hibernate version ứng dụng sử dụng, vì một phép thử với hai object `new` không kiểm tra được behavior lazy/proxy.

## 28. Tổng kết

- **Java reference identity**, **persistence identity** và **business identity** là ba khái niệm có thể trùng nhưng không đồng nghĩa.
- Hibernate thường duy trì cùng một managed instance cho cùng identity trong **một persistence context**, nhưng hai Session có thể tạo hai object khác nhau cho cùng hàng.
- **Không phải entity nào cũng cần override `equals()/hashCode()`**. Chỉ làm khi use case cần so sánh các instance theo identity vượt quá Java reference.
- Nếu dùng **generated ID**, hãy chỉ xem hai entity khác instance là bằng nhau khi ID **khác null** và phù hợp entity type/scope.
- Khi generated ID có thể từ null thành khác null sau khi object đã tồn tại, **không dùng ID biến đổi làm hashCode** nếu object có thể nằm trong `HashSet`/`HashMap`.
- Một hash code ổn định theo loại entity là giải pháp thực dụng cho ID sinh muộn, với đánh đổi về phân bố hash.
- **Business key bất biến, unique, non-null và có sẵn sớm** là ứng viên tốt cho equality; nhưng unique không đồng nghĩa immutable.
- Với **composite ID**, lớp khóa phải có equality đúng, các thành phần khóa cần ổn định; thời điểm gán vẫn quan trọng.
- **Không dùng field mutable, collection, association lazy, `@Version` hoặc timestamp** để định nghĩa entity identity theo thói quen.
- Hibernate proxy và entity inheritance khiến kiểm tra kiểu trở nên tinh tế: `getClass()` và `instanceof` đều có giới hạn tùy mapping.
- Lombok `@Data` hoặc `@EqualsAndHashCode` mặc định không hiểu danh tính domain; code sinh ra phải được chọn và kiểm soát có chủ đích.
- Equality là quy tắc **so sánh đối tượng Java**, không phải kiểm tra hàng còn tồn tại, đã commit hoặc có trạng thái mới nhất trong database.

**Ý chính:** chọn thuộc tính cho `equals()` và `hashCode()` của Hibernate entity là quyết định về **danh tính bền vững**, không phải quyết định “bao gồm bao nhiêu field”. Một chính sách tốt phải đúng với domain, không bị thay đổi bất ngờ qua vòng đời persistence, tôn trọng contract Java collections và hoạt động nhất quán khi entity xuất hiện dưới dạng managed, detached hoặc proxy.
