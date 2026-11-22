# Thực thể trong HashSet hoặc làm khóa HashMap khi thuộc tính bị thay đổi

Một thực thể Hibernate thường có các thuộc tính thay đổi trong vòng đời: `id` có thể từ `null` thành giá trị do database sinh ra khi `persist()`; email, mã nghiệp vụ, trạng thái hoặc số lượng có thể bị sửa bởi setter; association `parent` cũng có thể đổi khi đối tượng được chuyển sang một tập hợp khác. Nếu những thuộc tính đó tham gia `equals()` hoặc `hashCode()`, việc đưa entity vào `HashSet` hoặc làm khóa `HashMap` có thể dẫn đến lỗi khó phát hiện: **phần tử vẫn nằm trong collection, nhưng `contains()`, `get()` hoặc `remove()` không tìm thấy nó nữa**.

Đây không phải lỗi đặc biệt của Hibernate collection. Nó bắt nguồn từ **hợp đồng hashing của Java** kết hợp với **vòng đời và danh tính của JPA entity**. Hibernate làm vấn đề rõ hơn vì nhiều thực thể có ID sinh sau khi được thêm vào collection, tồn tại ở các trạng thái transient/managed/detached, được biểu diễn qua lazy proxy hoặc có các bản sao trong nhiều persistence context.

Trong bài này, ta đi từ cơ chế `HashSet`/`HashMap` đến thiết kế entity, những cách viết equality an toàn trong từng tình huống và phương pháp kiểm chứng. Các ví dụ tập trung vào Hibernate ORM 6.x với `jakarta.persistence`; Hibernate 5 dùng `javax.persistence` và một số chi tiết proxy/ID generation khác nhau.

## 1. Tình huống mở đầu: entity “biến mất” khỏi HashSet

Giả sử `Customer` có mã email tham gia cả `equals()` và `hashCode()`:

~~~java
import java.util.Objects;

public class MutableCustomer {
    private String email;

    public MutableCustomer(String email) {
        this.email = email;
    }

    public void changeEmail(String newEmail) {
        this.email = newEmail;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof MutableCustomer that)) return false;
        return Objects.equals(email, that.email);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(email);
    }
}
~~~

Code sử dụng:

~~~java
MutableCustomer customer = new MutableCustomer("old@example.com");
Set<MutableCustomer> customers = new HashSet<>();

customers.add(customer);
System.out.println(customers.contains(customer)); // true

customer.changeEmail("new@example.com");
System.out.println(customers.contains(customer)); // có thể false!
System.out.println(customers.size());              // vẫn là 1
~~~

Hành vi “có thể false” là chủ đích: `HashSet` chọn vị trí tra cứu theo hash của key **ở thời điểm mỗi phép tra cứu**; khi hash đổi, vị trí mới có thể không chứa node đã lưu tại vị trí cũ. Kết quả cụ thể tùy hash, dung lượng bảng, số phần tử và cách JVM triển khai; không phải mọi lần sửa đều chắc chắn làm `contains()` false. Nhưng **không được dựa vào việc nó tình cờ vẫn true**.

Nếu cố gắng xóa:

~~~java
boolean removed = customers.remove(customer); // có thể false
System.out.println(customers.size());         // vẫn có thể là 1
~~~

Đối tượng Java không bị xóa khỏi memory; dữ liệu trong hash table chỉ **không còn được định vị theo hash hiện tại**. Nếu collection ấy đại diện `@OneToMany(orphanRemoval = true)`, lỗi này còn có thể khiến thao tác xóa quan hệ nghiệp vụ không diễn ra như người viết code tưởng.

## 2. HashSet và HashMap hoạt động như thế nào?

`HashSet<E>` về mặt cấu trúc dựa trên một hash table (trong OpenJDK thông thường dùng một `HashMap` nội bộ), còn `HashMap<K,V>` lưu các cặp khóa–giá trị. Cả hai cần:

1. **`hashCode()`** để tính hash và xác định nhóm/bucket ứng viên.
2. **`equals()`** để phân biệt các khóa trong nhóm ứng viên.

Về ý tưởng:

~~~mermaid
flowchart TD
    A["set.add(entity)"] --> B["Tính entity.hashCode() = h1"]
    B --> C["Đặt entry vào bucket theo h1"]
    C --> D["Entity bị sửa thuộc tính tham gia hashCode()"]
    D --> E["hashCode() bây giờ trả h2"]
    E --> F["set.contains(entity) tính lại h2"]
    F --> G{"h2 dẫn tới bucket cũ?"}
    G -- "Không" --> H["Không tìm thấy entry dù object vẫn trong Set"]
    G -- "Có" --> I["Có thể tìm thấy; nhưng thiết kế vẫn không an toàn"]
~~~

Đơn giản hóa qua mô hình bảng:

~~~text
Lúc thêm:
  customer.email = "old@example.com"
  hashCode() = h1
  hash bucket[h1] -> customer

Sau khi sửa:
  customer.email = "new@example.com"
  hashCode() = h2
  HashSet vẫn giữ entry ở bucket[h1]

Lúc tra cứu:
  contains(customer) đi tìm ở bucket[h2]
  -> có thể không thấy entry đã lưu ở bucket[h1].
~~~

Không cần Hibernate can thiệp vào cấu trúc này: một POJO mutable bình thường cũng có thể gây ra lỗi. Điểm Hibernate đặc thù là **provider có thể tự tạo giá trị ID sau khi entity đã nằm trong collection**, ngay cả khi application không gọi setter nào.

### Vì sao `size()` vẫn bằng một?

`HashSet.size()` phản ánh số node mà collection đang giữ, không chứng minh mọi node còn có thể được tra cứu chính xác theo hash hiện tại. `iterator()` vẫn có thể duyệt đến entity ấy trong khi `contains(entity)` trả false.

### Vì sao không thể sửa bằng cách gọi lại `add()`?

Khi hash đã thay đổi, `set.add(customer)` có thể chèn **thêm một entry tham chiếu đúng object đó** ở bucket mới vì không tìm được entry cũ. Khi ấy collection có thể chứa hai entry trỏ cùng Java instance; thao tác này làm cấu trúc dữ liệu càng khó dự đoán. Không dùng `add()` để “đồng bộ lại” HashSet sau khi key bị mutation.

## 3. Hợp đồng equals/hashCode của Java

Một lớp dùng làm khóa trong hash table phải giữ các nguyên tắc:

| Quy tắc | Ý nghĩa |
|---|---|
| `equals` phản xạ | `a.equals(a)` phải đúng với `a` khác null. |
| `equals` đối xứng | `a.equals(b)` và `b.equals(a)` cho cùng kết quả. |
| `equals` bắc cầu | Nếu `a.equals(b)` và `b.equals(c)` thì `a.equals(c)`. |
| `equals` nhất quán | Khi thông tin phục vụ equality không đổi, kết quả không đổi. |
| Không equal với null | `a.equals(null)` phải false. |
| Hash tương thích equality | Nếu `a.equals(b)` thì `a.hashCode() == b.hashCode()`. |
| Hash ổn định khi làm key | Những field ảnh hưởng `equals/hashCode` không được đổi trong khi đối tượng nằm trong hash-based collection. |

Quy tắc cuối đặc biệt quan trọng: Java cho phép một object mutable có `hashCode()` thay đổi khi state thay đổi; **nhưng HashMap/HashSet không tự tái lập bảng băm cho entry đã lưu** khi state đó đổi. Vì vậy ứng dụng phải bảo đảm key ổn định trong thời gian object đang được dùng làm key.

**Không có yêu cầu hai object khác nhau phải có hash khác nhau.** Collision là hợp lệ; nhưng quá nhiều collision có thể làm giảm hiệu năng. Ngược lại, không có hash collision **không đủ** để kết luận equality đúng: `equals()` vẫn phải phản ánh định nghĩa danh tính mong muốn.

## 4. Vì sao JPA entity dễ thay đổi hash dù không gọi setter ID?

Giả sử:

~~~java
@Entity
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    private String sku;

    protected Product() {}

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() { return id; }
}
~~~

Với generator `SEQUENCE`, trước `persist()` entity thường có `id = null`. Sau `persist()`, Hibernate có thể cấp ID trước khi insert; với `IDENTITY`, ID thường được lấy khi insert diễn ra, có thể sớm hoặc muộn theo transaction/provider. Do đó:

~~~java
Product product = new Product("SKU-001");
System.out.println(product.getId()); // null trước persist

entityManager.persist(product);
System.out.println(product.getId()); // thường đã có ID, tùy generator
~~~

Nếu `hashCode()` dựa vào `id`, giá trị hash có thể đổi ở một bước không do setter nghiệp vụ. Đây là điểm giao nhau giữa vòng đời entity và hash-based collections.

### Ba thời điểm không nên đánh đồng

| Thời điểm | Ý nghĩa |
|---|---|
| Entity được cấp `@Id` | ORM đã có giá trị identifier cho object. |
| SQL `INSERT` chạy | Database đã nhận thao tác, có thể chưa commit. |
| Transaction `commit` thành công | Dữ liệu đã được xác nhận theo semantics của DB. |

ID có thể được cấp trước khi row được insert; rollback có thể xảy ra sau khi ID đã cấp. Vì thế ID dùng để nhận diện lưu trữ **không phải cờ “đã commit”**.

## 5. Anti-pattern: equals theo ID, hashCode cũng theo ID

Một implementation trông hợp lý:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Product p)) return false;
    return id != null && id.equals(p.id);
}

@Override
public int hashCode() {
    return id == null ? 0 : id.hashCode();
}
~~~

Phần `equals()` đã tránh lỗi hai transient entities cùng `null` bị coi bằng nhau. Nhưng `hashCode()` vẫn **thay đổi theo thời điểm Hibernate sinh ID**:

~~~java
Product p = new Product("SKU-001");
Set<Product> products = new HashSet<>();

products.add(p);             // hashCode() dựa trên id == null
entityManager.persist(p);    // id được cấp, hashCode() thay đổi

boolean found = products.contains(p); // có thể false
boolean deleted = products.remove(p); // có thể false
~~~

Với `HashMap`:

~~~java
Map<Product, Integer> quantities = new HashMap<>();
Product product = new Product("SKU-001");

quantities.put(product, 10);   // hash lúc id == null
entityManager.persist(product);

Integer quantity = quantities.get(product); // có thể null
~~~

Vấn đề nằm ở **định vị entry bằng hash**, không phải ở transaction isolation hay Hibernate cache.

### Anti-pattern còn tệ hơn: hai ID null được xem là equal

~~~java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Product p)) return false;
    return Objects.equals(id, p.id);
}
~~~

Hai sản phẩm transient khác nhau đều có ID null sẽ equal:

~~~java
Product a = new Product("SKU-A");
Product b = new Product("SKU-B");

// id == null ở cả hai:
// a.equals(b) == true với implementation sai phía trên.
~~~

`HashSet` có thể bỏ một phần tử ngay khi thêm; lỗi này xảy ra **trước cả khi gọi Hibernate**. Nếu định nghĩa equality dựa trên ID generated, phải phân biệt rõ state chưa được cấp ID.

## 6. Trường hợp HashMap còn nguy hiểm hơn thế nào?

`HashMap` lưu key và value; nếu key đổi hash sau `put()`:

~~~java
Map<Product, String> labels = new HashMap<>();
Product p = new Product("SKU-001");

labels.put(p, "in stock");
entityManager.persist(p);

String value = labels.get(p);       // có thể null
boolean exists = labels.containsKey(p); // có thể false
String removed = labels.remove(p);  // có thể null
~~~

Điều này có thể làm mất khả năng tra cứu bộ nhớ trong các luồng nghiệp vụ như:

- Map entity tới số lượng đặt hàng.
- Map entity tới kết quả validation hoặc thông báo lỗi.
- Cache request-scoped keyed by entity instance.
- Map aggregate root tới state xử lý của batch.
- Map entity tới metadata của UI hoặc công việc đồng bộ.

Nếu gọi `labels.put(p, "updated")` sau khi hash đổi, Map có thể thêm một entry khác cho cùng Java object. Không nên suy luận rằng `labels.size() == 1` luôn đúng chỉ vì bạn chỉ có một biến `p`.

### Sửa value có sao không?

~~~java
Map<Long, Product> productsById = new HashMap<>();
productsById.put(p.getId(), p);
p.changeDescription("Updated"); // không làm thay đổi Long key
~~~

Ở đây key là một `Long` bất biến, nên sửa value `Product` không làm bucket key đổi. Đây là điểm khác biệt cơ bản giữa **entity là value của Map** và **entity là key của Map**.

Nếu bản thân value lại được dùng làm key ở một Map/Set khác, các ràng buộc ở collection khác vẫn phải được tính riêng.

## 7. Hai loại danh tính: object identity và persistence identity

Java `==` kiểm tra hai reference có trỏ vào cùng object hay không; Hibernate entity identity dựa trên mapped entity type và identifier trong phạm vi persistence phù hợp.

~~~java
Product first;
Product second;

try (Session s1 = sessionFactory.openSession();
     Session s2 = sessionFactory.openSession()) {
    first = s1.find(Product.class, 42L);
    second = s2.find(Product.class, 42L);
}

System.out.println(first == second); // thường false
System.out.println(first.getId().equals(second.getId())); // true
~~~

Hai sessions thường tải hai Java instances khác nhau cho cùng database row. Trong một persistence context, Hibernate thường trả cùng managed instance khi load cùng entity identity lần nữa:

~~~java
Product a = entityManager.find(Product.class, 42L);
Product b = entityManager.find(Product.class, 42L);
System.out.println(a == b); // thường true trong cùng persistence context
~~~

**Tại sao liên quan đến HashSet?** Nếu entity dùng reference equality mặc định, hai instances từ hai sessions có thể được giữ như hai phần tử Set khác nhau, dù chúng đại diện cùng row. Nếu ứng dụng muốn dedup theo database identity, cần tiêu chí equality hoặc một key riêng. Nhưng sửa `equals()` theo ID cũng phải tránh bẫy hash biến đổi trước/sau persist.

### So business key là chuyện thứ ba

Hai sản phẩm có `sku` giống nhau có thể là cùng business value theo một quy tắc, nhưng nếu `sku` chỉ unique trong từng tenant thì cần thêm `tenantId` vào tiêu chí. Hai entities có name/description giống nhau không mặc định là cùng row hoặc cùng domain identity.

## 8. Lựa chọn A: giữ Object.equals/hashCode mặc định

Không override `equals()` và `hashCode()` cũng là **một chiến lược có chủ đích**:

~~~java
@Entity
public class Product {
    @Id
    @GeneratedValue
    private Long id;

    private String name;

    // Không override equals()/hashCode().
}
~~~

Với implementation mặc định của `Object`, equality gần với reference identity và hash không đổi do Hibernate cấp giá trị field ID. Một `Product` trong `HashSet` vẫn có thể được tìm theo **chính reference ấy** khi field của object thay đổi.

Ưu điểm:

- Đơn giản, không làm hash thay đổi khi `@Id` được gán.
- Không vô tình kích hoạt lazy loading qua `equals()/hashCode()`.
- Phù hợp khi entity chỉ được dùng trong một persistence context hoặc không cần dedup các bản sao detached.

Giới hạn:

- Hai entity instances đại diện cùng row nhưng load từ hai sessions khác nhau vẫn có thể `equals() == false`.
- Nếu business logic cần so persistence identity xuyên các transaction, phải so ID/type một cách tường minh hoặc dùng key riêng.

Không có yêu cầu JPA chung rằng mọi entity **bắt buộc** override `equals()/hashCode()`. Chỉ override khi đã định nghĩa rõ ý nghĩa equality và cách entity thực sự được dùng.

## 9. Lựa chọn B: equals theo ID generated nhưng hashCode ổn định

Nếu nghiệp vụ thường phải so detached và managed copies của cùng row, equality theo identifier có thể phù hợp. Điều kiện quan trọng là **hash code không được thay đổi khi ID chuyển từ null sang giá trị được sinh**.

Ví dụ cơ bản cho một entity không có hierarchy:

~~~java
@Entity
@Table(name = "product")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "sku", nullable = false)
    private String sku;

    protected Product() {}

    public Product(String sku) {
        this.sku = sku;
    }

    public Long getId() {
        return id;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Product that)) return false;
        return getId() != null && getId().equals(that.getId());
    }

    @Override
    public int hashCode() {
        return Product.class.hashCode();
    }
}
~~~

Điểm đáng chú ý:

1. `this == other` giữ reflexivity, kể cả entity chưa có ID.
2. `getId() != null` ngăn hai transient entities khác nhau cùng null-ID bị coi equal.
3. Khi có non-null ID, hai objects cùng loại có thể equal theo persistence identity.
4. `Product.class.hashCode()` **không đổi** khi Hibernate cấp ID hoặc khi `sku` bị thay đổi.

Đây là mẫu **minh họa một hướng thiết kế**, không phải công thức phù hợp mọi entity:

- Nếu `Product` có entity subclasses, `instanceof` và class constant có thể gây equality semantics không mong muốn giữa các subtype. Cần thiết kế quy tắc hierarchy trước khi triển khai.
- Hibernate lazy proxy có thể ảnh hưởng cách gọi `equals()`, `getId()` và phép kiểm tra class; phần sau trình bày lưu ý.
- Mọi `Product` có cùng hash value; điều này **không vi phạm Java contract**, nhưng có thể làm giảm hiệu năng Set/Map lớn do nhiều collision.

### Vì sao constant hash có thể đúng về mặt kỹ thuật?

Quy tắc Java chỉ yêu cầu:

~~~text
a.equals(b) == true  =>  a.hashCode() == b.hashCode()
~~~

Nó **không yêu cầu**:

~~~text
a.equals(b) == false => a.hashCode() != b.hashCode()
~~~

Vì vậy một hash theo entity class có thể hợp lệ, miễn equality ổn định đúng quy tắc. Tuy nhiên, nếu Set chứa hàng trăm nghìn entity, một hash chung là trade-off về CPU/hiệu năng; có thể cân nhắc không dùng entity làm key hoặc dùng immutable identifier key riêng.

## 10. Bẫy khi cố “cải tiến” hashCode lúc đã có ID

Cách sau là sai nếu entity có thể được thêm vào Set trước khi persist:

~~~java
@Override
public int hashCode() {
    if (id == null) {
        return Product.class.hashCode();
    }
    return id.hashCode(); // hash thay đổi sau persist!
}
~~~

Đôi khi người viết code cho rằng “chỉ transient mới cần hash constant; sau persist có ID rồi thì dùng hash theo ID cho nhanh”. Nhưng **HashSet không biết mốc entity đổi trạng thái** và sẽ không tự chuyển entry sang bucket mới.

Nguyên tắc:

> Nếu một entity có thể tồn tại trong HashSet hoặc làm key HashMap **trước và sau** khi được cấp generated ID, `hashCode()` phải giữ ổn định xuyên qua sự thay đổi đó.

Một cấu trúc `Map<Long, Value>` chỉ được tạo **sau khi ID đã thực sự có** có thể tận dụng hashing của `Long` mà không gặp bẫy này.

## 11. Lựa chọn C: equality theo natural key bất biến

Đôi khi entity có business key unique và ổn định **ngay từ khi tạo**. Ví dụ `Country` được định danh về nghiệp vụ bằng mã ISO đã chuẩn hóa, không cho sửa:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.NaturalId;
import java.util.Objects;

@Entity
@Table(
    name = "country",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_country_iso_code",
        columnNames = "iso_code"
    )
)
public class Country {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @NaturalId(mutable = false)
    @Column(name = "iso_code", nullable = false, updatable = false, length = 2)
    private String isoCode;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    protected Country() {}

    public Country(String isoCode, String displayName) {
        this.isoCode = Objects.requireNonNull(isoCode);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public String getIsoCode() {
        return isoCode;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Country that)) return false;
        return isoCode != null && isoCode.equals(that.getIsoCode());
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(isoCode);
    }
}
~~~

Trong ví dụ, ISO code được truyền vào constructor và **không có setter**, nên hash đã ổn định trước khi `persist()`:

~~~java
Country vn = new Country("VN", "Viet Nam");
Set<Country> countries = new HashSet<>();

countries.add(vn);
entityManager.persist(vn);     // generated ID có thể đổi null -> số

System.out.println(countries.contains(vn)); // dự kiến true
~~~

Hash theo `isoCode` không bị tác động bởi việc Hibernate cấp `id`.

### Những điều kiện để natural key thực sự an toàn

- Key phải **unique** đúng phạm vi nghiệp vụ (toàn hệ thống hay theo tenant).
- Key phải được **gán trước khi làm HashMap key/HashSet element**.
- Key phải **bất biến trong suốt thời gian object được dùng làm hash key**.
- Quy tắc chuẩn hóa (chữ hoa/thường, khoảng trắng, Unicode, collation) phải nhất quán với database.
- DB cần unique constraint phù hợp; `equals()` ở Java không ngăn race giữa các transactions khác nhau.
- Lazy proxy có thể ảnh hưởng cách truy cập key qua getter; cần quyết định rõ khi so entity chưa initialize.

`@NaturalId` là **mở rộng của Hibernate** hỗ trợ natural-id mapping/lookup; nó **không tự sinh `equals()/hashCode()`** và không thay thế việc thiết kế immutable key. `@Column(updatable = false)` hạn chế SQL update cột theo mapping, nhưng không có nghĩa Java field tự động bất biến nếu vẫn cung cấp setter; domain code cần giữ invariant.

## 12. Nếu business key có thể thay đổi thì sao?

Email là ví dụ rõ:

~~~java
@Entity
class UserAccount {
    @Id
    @GeneratedValue
    Long id;

    @Column(unique = true)
    String email;
}
~~~

Nếu `equals/hashCode` tính từ `email`, việc gọi:

~~~java
account.changeEmail("new@example.com");
~~~

có thể làm Set/Map mất khả năng tra cứu key. Điều này đúng ngay cả khi database vẫn giữ unique constraint và Hibernate update email thành công.

Không nên giải quyết bằng cách cấm người dùng đổi email chỉ để `HashSet` hoạt động. Nếu domain cần email mutable, chọn một phương án:

1. Dùng **reference equality** cho entity nếu không cần so across contexts.
2. Dùng **generated-ID equality với hash ổn định** khi cần so persistence identity.
3. Dùng **immutable key riêng** cho Map, chẳng hạn `UserKey(tenantId, userId)` hoặc một application-assigned UUID không đổi.
4. Nếu thật sự muốn Map keyed by email, dùng `Map<String, Value>` và **re-key một cách tường minh** khi email đổi.

Ví dụ re-key đúng với Map keyed by String:

~~~java
Map<String, UserView> usersByEmail = new HashMap<>();

String oldEmail = "old@example.com";
String newEmail = "new@example.com";

UserView value = usersByEmail.remove(oldEmail);
if (value != null) {
    usersByEmail.put(newEmail, value);
}
~~~

Chú ý nếu application có concurrent writers hoặc email normalization, phải xử lý atomicity, collisions và business validation ở mức thích hợp. Map chỉ là cấu trúc bộ nhớ, không tự bảo đảm uniqueness trong database.

## 13. Khi thực sự cần đổi khóa: remove trước, mutate sau, add lại

Với một **POJO mutable do application sở hữu** (không gắn vào Hibernate persistent collection có lifecycle đặc biệt), nếu buộc phải thay thuộc tính dùng làm hash key, cách an toàn là **lấy nó khỏi collection khi hash cũ còn hiệu lực** rồi mới sửa và thêm lại:

~~~java
MutableCustomer customer = new MutableCustomer("old@example.com");
Set<MutableCustomer> customers = new HashSet<>();
customers.add(customer);

boolean removed = customers.remove(customer); // hash cũ còn hiệu lực
if (!removed) {
    throw new IllegalStateException("Customer not in set");
}

customer.changeEmail("new@example.com");
boolean added = customers.add(customer);       // hash mới
if (!added) {
    // Có object khác equal theo key mới; cần giải quyết xung đột nghiệp vụ.
}
~~~

Với `HashMap`:

~~~java
Map<MutableCustomer, Integer> map = new HashMap<>();
map.put(customer, 5);

Integer quantity = map.remove(customer);  // lấy khi hash chưa đổi
customer.changeEmail("another@example.com");
if (quantity != null) {
    map.put(customer, quantity);           // thêm với hash mới
}
~~~

**Giới hạn:** Đoạn này chỉ minh họa cách giữ cấu trúc hash nhất quán khi application thật sự kiểm soát mọi collection chứa object. Nếu cùng object đang là key trong nhiều Maps/Sets, phải re-key **tất cả**; nếu một collection khác đang duyệt hoặc nhiều thread đồng thời đọc, cần đồng bộ hóa. Do rủi ro cao, thiết kế **key bất biến** thường tốt hơn.

### Không áp dụng máy móc vào `@OneToMany(orphanRemoval = true)`

`persistentCollection.remove(child)` có thể mang nghĩa **thay đổi quan hệ ORM** và kích hoạt orphan removal/dirty tracking, không chỉ là thao tác tổ chức bảng băm. Xóa rồi thêm con lại để đổi một field có thể gây hành vi lifecycle không mong muốn. Với persistent Sets, nên sửa **thiết kế equality và domain methods**, không dùng remove/mutate/add như giải pháp tổng quát cho mọi entity.

## 14. HashMap với key kiểu ID bất biến: phương án thường rõ ràng nhất

Thay vì:

~~~java
Map<Product, Integer> quantityByProduct = new HashMap<>();
~~~

hãy cân nhắc:

~~~java
Map<Long, Integer> quantityByProductId = new HashMap<>();

Product p = entityManager.find(Product.class, 42L);
quantityByProductId.put(p.getId(), 10);

p.changeDescription("Updated product");
Integer quantity = quantityByProductId.get(42L); // không phụ thuộc state p
~~~

Ưu điểm:

- `Long` bất biến, hash không bị đổi theo setter của entity.
- Cùng entity được load từ hai sessions khác nhau vẫn dùng cùng ID key.
- Không cần initialize lazy associations hoặc dựa vào proxy class chỉ để tìm Map entry.
- Dễ serialize, log và truyền qua service boundaries.

Giới hạn:

- Nếu entity **chưa có ID**, không thể dựa vào `null` làm key duy nhất cho nhiều entity mới.
- Nếu dữ liệu thuộc nhiều entity types hoặc tenants với ID trùng, cần key chứa đủ **type/scope**.
- Nếu ID thay đổi bởi thiết kế đặc biệt (không nên với entity managed), phải xem lại khái niệm persistent identity.

### Composite key cho multi-tenant

~~~java
public record ProductKey(long tenantId, long productId) {}

Map<ProductKey, Integer> quantities = new HashMap<>();
quantities.put(new ProductKey(10L, 42L), 5);
quantities.put(new ProductKey(20L, 42L), 8);
~~~

Record component primitive `long` là immutable; equality/hash do record sinh theo giá trị cả hai components. Hai sản phẩm có local ID `42` ở hai tenants không bị trộn lẫn.

Nếu scope còn bao gồm entity type, có thể dùng một record như `EntityKey(String entityType, long tenantId, long id)` theo quy ước nội bộ rõ ràng.

## 15. Thực thể chưa được persist: lấy gì làm khóa?

ID generated có thể chưa tồn tại trong giai đoạn tạo một graph lớn:

~~~java
Product p1 = new Product("SKU-A");
Product p2 = new Product("SKU-B");
// p1.getId() == null, p2.getId() == null
~~~

Không làm:

~~~java
Map<Long, Product> byId = new HashMap<>();
byId.put(p1.getId(), p1);
byId.put(p2.getId(), p2); // key null bị ghi đè; chỉ còn một entry null
~~~

Lựa chọn đúng phụ thuộc mục đích:

**Theo object reference trong một unit of work:** dùng `IdentityHashMap<Product, V>` nếu thật sự muốn khóa so bằng `==` bất kể entity override equals:

~~~java
Map<Product, String> temporaryNotes = new IdentityHashMap<>();
temporaryNotes.put(p1, "first");
temporaryNotes.put(p2, "second");
~~~

`IdentityHashMap` có semantics **khác Map thông thường**: nó cố ý dùng reference identity (`==`) và identity hash. Nó phù hợp một số thuật toán theo object graph trong phạm vi hẹp, nhưng không thay thế Map keyed by persistence identity xuyên sessions.

**Theo business key bất biến:** dùng `Map<String, Product>` keyed by normalized SKU nếu SKU chắc chắn unique/immutable trong scope.

**Theo temporary identifier ứng dụng cấp:** dùng UUID/record tạo khi constructor, chẳng hạn `creationToken` không đổi để định danh object trong batch; khi được persist, map business objects sang DB ID riêng.

**Theo primary key:** chờ Hibernate cấp ID và đảm bảo ID có giá trị rồi mới đưa vào `Map<Long,...>`, đồng thời không nhầm việc có ID với transaction commit.

## 16. HashSet trong quan hệ @OneToMany: tác động ORM

Ví dụ:

~~~java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private Set<OrderLine> lines = new HashSet<>();

    // ...
}

@Entity
public class OrderLine {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    // ...
}
~~~

Giả sử `OrderLine.hashCode()` được tính trực tiếp từ ID generated:

~~~java
OrderLine line = new OrderLine("BOOK", 2);
order.addLine(line);     // thêm vào HashSet khi id == null

entityManager.persist(order); // cascade persist, line được cấp id
order.removeLine(line);       // HashSet.remove có thể thất bại!
~~~

Nếu `removeLine()` giả định `lines.remove(line)` luôn thành công, code có thể không đổi owning side `line.order`, không cập nhật collection và không dẫn tới xóa orphan như mong đợi.

### Vì sao vấn đề không chỉ nằm trong Java Set?

Hibernate thường dùng các wrapper collection như `PersistentSet` để theo dõi trạng thái và thay đổi collection. Khi equality/hashCode của entity không ổn định:

- Thao tác `contains/remove` có thể thất bại ở lớp collection.
- Việc so snapshot với current collection để phát hiện insert/delete có thể khó dự đoán.
- Code domain có thể đồng bộ hai chiều không đầy đủ khi một nhánh dựa vào kết quả `remove()`.
- `orphanRemoval` có thể không được thực hiện theo ý định nếu collection không thay đổi như dự kiến.

Không nên khẳng định Hibernate sẽ luôn sinh một câu SQL sai cố định trong mọi tình huống; hành vi còn phụ thuộc state, persistence context, cascade, flush và cơ chế collection của phiên bản Hibernate. Bảo đảm thiết kế vẫn là: **đừng thay đổi các giá trị chi phối hash/equality khi entity còn ở trong một hash-based persistent collection**.

### Domain helper cần đồng bộ hai phía

~~~java
public void addLine(OrderLine line) {
    if (lines.add(line)) {
        line.attachTo(this); // owning side: @ManyToOne order
    }
}

public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.attachTo(null);
    }
}
~~~

Helper này dựa vào `Set.add/remove` hoạt động đúng theo equality của entity. Nếu `hashCode()` thay đổi, cả logic đồng bộ hai chiều cũng trở nên không đáng tin cậy. Với entity không cần Set semantics thật sự, `List` và domain validation/DB constraint có thể là lựa chọn rõ ràng hơn.

## 17. Set hay List: chọn vì domain, không chỉ vì cú pháp

| Tiêu chí | `Set<Entity>` | `List<Entity>` |
|---|---|---|
| Mục tiêu chính | Không trùng theo `equals()` đã định nghĩa. | Giữ các phần tử theo cấu trúc danh sách, có thể theo thứ tự. |
| Rủi ro khi hashCode đổi | Trực tiếp, nghiêm trọng với `HashSet`/`PersistentSet`. | Không phụ thuộc hash bucket trong thao tác danh sách thông thường, nhưng equality vẫn có thể ảnh hưởng `contains/remove`. |
| Đảm bảo uniqueness ở DB | **Không thay thế** unique constraint. | **Không thay thế** unique constraint. |
| Entity ID generated | Cần equality/hashCode có thiết kế rõ. | Thường đơn giản hơn với nhiều graph mới; vẫn cần quy tắc tránh duplicate theo domain. |
| Thứ tự persistence | Set không có thứ tự được đảm bảo. | List có thứ tự Java, nhưng thứ tự DB cần `@OrderBy`/`@OrderColumn` nếu muốn ổn định sau reload. |

`List.remove(Object)` thường dựa vào `equals()`, nên nếu equality thay đổi theo field, thao tác vẫn có thể cho kết quả không mong muốn (ví dụ xóa nhầm object equal theo business field). Nhưng nó **không có lỗi sai bucket** đặc trưng của HashSet khi `hashCode()` thay đổi.

Đừng chọn `Set` chỉ để Hibernate “không tạo duplicate SQL row”. Database uniqueness phải được bảo vệ bằng PK/unique constraints, còn collection type diễn đạt semantics ở Java.

## 18. HashMap và entity proxy: equals/getClass có thể làm tra cứu lệch

Hibernate có thể trả proxy cho entity lazy-load:

~~~java
Product reference = entityManager.getReference(Product.class, 42L);
Product loaded = entityManager.find(Product.class, 42L);
~~~

Về persistence identity, chúng có thể đại diện cùng `Product#42`. Nhưng proxy runtime class có thể là subclass do Hibernate tạo. Nếu equality được viết:

~~~java
if (getClass() != other.getClass()) return false;
~~~

thì một proxy và entity instance thông thường có thể không equal, dù ID giống nhau. Khi dùng entity làm `HashMap` key, `get(reference)` có thể không tìm được entry đã insert bằng một instance khác không chỉ vì hash đổi, mà còn vì **quy tắc type equality không phù hợp proxy**.

### Một cách lấy persistent class trong Hibernate

~~~java
import org.hibernate.proxy.HibernateProxy;

static Class<?> persistentClass(Object object) {
    if (object instanceof HibernateProxy proxy) {
        return proxy.getHibernateLazyInitializer().getPersistentClass();
    }
    return object.getClass();
}
~~~

Mã này dùng API riêng của Hibernate. Các cách khác như `Hibernate.getClass(object)` có thể khởi tạo proxy tùy phiên bản/cấu hình. Ngoài ra, `getIdentifier()` của Hibernate lazy initializer cũng có các lưu ý về JPA proxy compliance. Không copy một đoạn equality có gọi getter/field tùy tiện vào mọi class mà chưa hiểu mapping proxy và inheritance.

### Generated-ID equality với proxy cần thống nhất

Một implementation proxy-aware có thể so:

1. Reference identity (`this == other`).
2. Persistent class hoặc hierarchy identity scope phù hợp.
3. Non-null identifier.
4. Hash code ổn định dựa vào persistent class/hierarchy, không dựa vào generated ID.

Nếu entity có inheritance, việc so exact subtype vs root proxy có thể có những trường hợp đặc biệt: thiết kế equality nên nhất quán ở toàn hierarchy và tuân thủ symmetry/transitivity. Bài này không khuyến nghị một công thức proxy-aware duy nhất cho mọi entity hierarchy.

## 19. Một ví dụ equality theo ID có xét proxy

Với một entity không có subclass nghiệp vụ, Hibernate-specific implementation có thể như sau:

~~~java
import jakarta.persistence.*;
import org.hibernate.proxy.HibernateProxy;
import java.util.Objects;

@Entity
@Table(name = "catalog_item")
public class CatalogItem {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(nullable = false)
    private String title;

    protected CatalogItem() {}

    public CatalogItem(String title) {
        this.title = title;
    }

    public Long getId() { return id; }

    private static Class<?> effectiveClass(Object value) {
        if (value instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                        .getPersistentClass();
        }
        return value.getClass();
    }

    private static Object effectiveId(CatalogItem value) {
        if (value instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                        .getIdentifier();
        }
        return value.getId();
    }

    @Override
    public final boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof CatalogItem that)) return false;
        if (effectiveClass(this) != effectiveClass(that)) return false;

        Object myId = effectiveId(this);
        Object otherId = effectiveId(that);
        return myId != null && Objects.equals(myId, otherId);
    }

    @Override
    public final int hashCode() {
        return effectiveClass(this).hashCode();
    }
}
~~~

Hàm `hashCode()` dựa trên class của entity nên không thay đổi theo title/ID, còn `equals()` chỉ coi hai instances khác nhau bằng nhau khi ID đã có và phù hợp type.

**Giới hạn cần nhớ:**

- Đây là ví dụ **dành cho Hibernate**, không portable JPA thuần.
- Hibernate version/proxy compliance có thể ảnh hưởng cách lấy ID mà không khởi tạo proxy; cần hiểu cấu hình runtime.
- Nếu ứng dụng có inheritance subtype hoặc multi-tenant identity namespaces, equality theo class + ID như trên có thể chưa đủ hoặc không khớp domain.
- Final methods và khả năng proxy/enhancement tùy Hibernate; cần bảo đảm cách thức gọi method phù hợp mapping.
- Constant/class hash tạo collision giữa các entity cùng loại; hiệu năng cần được đo nếu Set/Map lớn.

Đừng chỉ thay `hashCode()` mà giữ `equals()` so các mutable fields; như vậy tuy hash có thể ổn định, equality vẫn thay đổi khi entity nằm trong collection, có thể gây duplicate logical keys và các kết quả bất thường khác.

## 20. Detached và merge: cùng row nhưng là hai object khác nhau

Một entity có thể đi qua nhiều transaction:

~~~java
CatalogItem detached = loadInPreviousSession(42L);
CatalogItem managed;

EntityTransaction tx = entityManager.getTransaction();
tx.begin();

managed = entityManager.merge(detached);
tx.commit();

System.out.println(detached == managed); // thường false
System.out.println(detached.getId().equals(managed.getId())); // true
~~~

`merge()` thường tạo hoặc chọn managed instance và sao chép state từ detached; nó **không biến instance detached ban đầu thành managed**.

### Tác động với Set

~~~java
Set<CatalogItem> items = new HashSet<>();
items.add(detached);
items.add(managed);
~~~

- Nếu giữ `Object.equals()` mặc định, Set có thể chứa **hai entries** vì hai references khác nhau.
- Nếu dùng equality theo non-null ID và type, Set thường chỉ giữ **một logical entry**, vì hai objects đại diện cùng row.
- Nếu dùng equality theo mutable title, hai objects có thể equal hoặc không tùy giá trị title tại thời điểm so; đây thường là tiêu chí không phù hợp để xác định cùng entity.

Không có lựa chọn đúng tuyệt đối. Nếu mục tiêu collection là “những object instances đang xử lý”, reference identity có thể thích hợp. Nếu mục tiêu là “những database entities duy nhất”, ID key hoặc ID-based equality có thể phù hợp hơn.

### Tránh sửa detached key khi vẫn nằm trong Map

Ngay cả sau merge, một detached instance vẫn có thể được application giữ như Map key. Khi sửa business key trên detached object hoặc managed copy, hai snapshots có thể chênh nhau; một Map keyed by entity mutable làm việc suy luận càng khó. Giữ key riêng bất biến thường làm rõ ranh giới giữa object state và identity.

## 21. Thay đổi @Id thủ công không phải giải pháp

Một số người cố xử lý HashSet bằng cách gán sẵn `id` cho entity:

~~~java
Product p = new Product("SKU-A");
p.setId(999L); // không hợp lệ về mặt thiết kế nếu provider sinh @Id
~~~

Nếu mapping dùng `@GeneratedValue`, application **không nên tự ý gán hoặc sửa ID** sau khi entity được tạo/managed. Điều này có thể gây:

- Collision primary key khi insert.
- Entity bị coi là detached hoặc không hợp lệ cho `persist()`.
- Identity map và association FK không đồng bộ.
- Những khác biệt hành vi giữa versions/providers.

Nếu cần identifier ngay từ lúc xây object, hãy cân nhắc thiết kế **application-assigned immutable UUID/ULID hoặc business key** theo mapping và migration cụ thể, không tự ghi vào field đang để Hibernate sinh khóa.

### Application-assigned ID thay đổi điểm nào?

Ví dụ một field UUID được cấp bằng constructor và không sửa:

~~~java
@Entity
public class ExternalTask {
    @Id
    private UUID id;

    protected ExternalTask() {}

    public ExternalTask() {
        this.id = UUID.randomUUID();
    }

    public UUID getId() { return id; }
}
~~~

Vì ID có từ khi object được tạo, equality/hashCode theo ID bất biến có thể phù hợp hơn. Tuy nhiên, phải thống nhất quy tắc assigned ID khi Hibernate hydrate entity và khi ứng dụng tạo task, quản lý uniqueness ở DB, cũng như kiểm tra semantics của `persist()/merge()`. Cách này không biến key thành “không thể thay đổi” nếu class vẫn có public setter hoặc reflection/business code sửa nó.

## 22. @Embeddable, composite key và mutable ID component

Với `@EmbeddedId`, object khóa thường có value-based `equals/hashCode`:

~~~java
@Embeddable
public class TenantSkuId implements Serializable {
    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "sku")
    private String sku;

    protected TenantSkuId() {}

    public TenantSkuId(Long tenantId, String sku) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.sku = Objects.requireNonNull(sku);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TenantSkuId that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(sku, that.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }
}
~~~

Một khóa ghép như `(tenantId, sku)` phải được coi là **bất biến sau khi làm identity**. Nếu ứng dụng sửa `sku` bên trong object ID khi nó đang làm HashMap key, lỗi bucket đổi vẫn xảy ra dù object là `@Embeddable` chứ không phải `@Entity`.

Điều quan trọng:

- Composite key class phải có equality/hash dựa trên các thành phần khóa.
- Những thành phần đó phải ổn định khi object được dùng làm hash key.
- Đừng sửa identifier của entity managed để đổi SKU nghiệp vụ; nếu SKU phải đổi thì không nên mặc định dùng nó làm primary key bất biến.
- Nếu Map keyed by một key object, key class nên được thiết kế bất biến thật sự; Java record hoặc immutable DTO có thể dễ bảo vệ hơn trong code thuần Java, còn JPA embeddable cần đáp ứng yêu cầu provider về constructor/access.

## 23. @MapKey và Map-valued association cũng cần thiết kế key

JPA có thể ánh xạ collection dưới dạng `Map<K,V>`:

~~~java
@Entity
class Catalog {
    @Id
    private Long id;

    @OneToMany(mappedBy = "catalog")
    @MapKey(name = "sku")
    private Map<String, CatalogItem> itemsBySku = new HashMap<>();
}
~~~

`@MapKey(name = "sku")` có thể dùng thuộc tính `sku` của value entity để làm key. Nhưng **thay đổi `CatalogItem.sku` không có nghĩa Hibernate/JPA sẽ tự chuyển entry từ key cũ sang key mới trong Map đã loaded**. Map có key hiện tại và giá trị entity đã sửa là hai trạng thái cần được đồng bộ theo đúng mapping.

Ví dụ về object graph:

~~~java
CatalogItem item = catalog.getItemsBySku().get("SKU-OLD");
item.changeSku("SKU-NEW");

// Map đã loaded có thể vẫn dùng key "SKU-OLD".
// Không mặc định rằng get("SKU-NEW") tự tìm được item.
~~~

Nếu nghiệp vụ cho phép đổi SKU, phải thiết kế domain method cập nhật Map keys (hoặc load lại/mapping phù hợp), đồng thời bảo đảm transaction, uniqueness và DB schema. Nếu SKU là business identity bất biến, nên không cung cấp thao tác thay đổi key.

Trường hợp Map có **entity làm key** (`Map<Entity, Value>`) còn chịu trực tiếp quy tắc hash/equality của entity key. Cần phân biệt:

1. Map key là chuỗi/identifier bất biến.
2. Map key là một entity object.
3. Hibernate `@MapKey(name=...)` lấy key từ một property của value entity.

Chúng có API Map giống nhau nhưng yêu cầu đồng bộ khác nhau.

## 24. Vì sao không nên dùng tất cả field trong equals/hashCode?

Một entity thường có:

~~~java
@Entity
class CustomerOrder {
    @Id
    Long id;

    String orderCode;
    BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY)
    Customer customer;

    @OneToMany(mappedBy = "order")
    Set<OrderLine> lines;
}
~~~

Nếu code generator như Lombok `@Data` tự tạo `equals/hashCode` từ tất cả field:

- `total` đổi khi thêm line → hash đổi.
- `customer` có thể là lazy proxy → gọi equals/hash có thể kích hoạt SQL hoặc `LazyInitializationException`.
- `lines` và `line.order` tạo vòng tham chiếu → có thể gây đệ quy vô hạn.
- Collection `lines` thay đổi sau cascade persist → equality/hash đổi.
- `toString()` cũng có thể kéo cả collection lazy vào log một cách bất ngờ.

### Không để Lombok quyết định domain identity vô tình

~~~java
@lombok.Data
@Entity
class CustomerOrder {
    @Id
    Long id;

    @OneToMany(mappedBy = "order")
    Set<OrderLine> lines;
}
~~~

Thay vì mặc định dùng `@Data`, cân nhắc `@Getter`, setter có kiểm soát, `@ToString(onlyExplicitlyIncluded = true)` và một implementation equality theo quy tắc đã chọn. `@EqualsAndHashCode(onlyExplicitlyIncluded = true)` có thể được dùng có chủ đích, nhưng nếu field được include là mutable generated ID, nó vẫn có cùng bẫy hash thay đổi.

## 25. Mutable field không tham gia equality thì có sao không?

Không phải mọi thay đổi thuộc tính đều gây lỗi trong HashSet/HashMap. Xét:

~~~java
@Override
public boolean equals(Object other) {
    // so non-null id và đúng entity type
}

@Override
public int hashCode() {
    return Product.class.hashCode();
}
~~~

Với cách thiết kế đó, sửa `description` hoặc `price` **không làm kết quả equals/hash đổi**:

~~~java
Product p = entityManager.find(Product.class, 42L);
Set<Product> products = new HashSet<>();
products.add(p);

p.changePrice(new BigDecimal("129.00"));
System.out.println(products.contains(p)); // dự kiến true
~~~

Hibernate có thể dirty-check và flush `UPDATE product SET price=...`; đó là hoạt động ORM độc lập với hashing. Vấn đề không phải “entity không được thay đổi khi ở Set”, mà là:

> **Không thay đổi những thuộc tính chi phối equality và hash code khi entity đang nằm trong một hash-based collection**, trừ khi collection được quản lý lại theo cách an toàn và phù hợp domain.

Nếu entity equality dựa trên business key bất biến, thay đổi một field mô tả ngoài key là bình thường.

## 26. Equality thay đổi dù hash không đổi vẫn có thể gây lỗi logic

Giả sử `hashCode()` luôn trả một hằng số:

~~~java
@Override
public int hashCode() {
    return 31;
}
~~~

nhưng `equals()` so một email mutable:

~~~java
@Override
public boolean equals(Object other) {
    if (!(other instanceof UserAccount that)) return false;
    return Objects.equals(email, that.email);
}
~~~

Khi email đổi, bucket không đổi, nên `contains(object)` có thể vẫn true khi dùng đúng cùng reference. Nhưng một vấn đề khác xuất hiện:

~~~java
UserAccount a = new UserAccount("a@example.com");
UserAccount b = new UserAccount("b@example.com");

Set<UserAccount> users = new HashSet<>();
users.add(a);
users.add(b);

b.changeEmail("a@example.com");
// a.equals(b) giờ true theo email
// Set có thể đang giữ hai phần tử vốn nay được coi là equal.
~~~

`HashSet` không tự duyệt và loại bỏ duplicate khi `equals()` thay đổi. Vì vậy **constant hashCode không cứu được mọi cách viết equals dựa vào mutable field**. Để entity là hash collection member ổn định, phải kiểm soát **cả equality lẫn hash** theo quy tắc không đổi trong thời gian key được giữ.

## 27. Concurrency: map đúng hash vẫn chưa đủ thread safety

`HashMap` và `HashSet` thông thường không thread-safe. Nếu nhiều threads đồng thời ghi/đọc Map hoặc thay thuộc tính của entity key, có **hai lớp rủi ro độc lập**:

1. Hash/equality mutation làm key không còn ổn định.
2. Concurrent modification mà không đồng bộ hóa có thể làm cấu trúc Map/Set hoạt động sai hoặc gây data race.

`ConcurrentHashMap` giải quyết một phần vấn đề concurrency theo contract của nó, **nhưng không giải quyết mutable-key hash**. Key có `hashCode()` đổi trong lúc đang nằm trong `ConcurrentHashMap` vẫn là thiết kế không an toàn.

Hibernate `Session` cũng không thread-safe. Không chia một managed entity graph đang gắn với Session qua nhiều worker threads rồi vừa mutate state vừa dùng làm keys trong các Maps. Với asynchronous workflows, thường truyền immutable IDs/DTOs, tạo transaction/context thích hợp trong thread xử lý, và dùng synchronization/concurrency control cho shared data structures.

### Đừng nhầm optimistic locking với ổn định HashMap

`@Version` giúp Hibernate phát hiện xung đột cập nhật DB. Nó không làm `HashMap` tự rehash khi Java field đổi. Ngược lại, hash stability không thay thế transaction isolation hoặc optimistic locking đối với database.

## 28. Tìm lỗi khi entity đã không thể remove khỏi Set

Trong môi trường debug, có thể quan sát:

~~~java
System.out.println("size = " + set.size());
System.out.println("contains = " + set.contains(entity));
System.out.println("currentHash = " + entity.hashCode());

for (Product p : set) {
    System.out.println(
        "sameRef = " + (p == entity)
        + ", id = " + p.getId()
        + ", hashNow = " + p.hashCode()
    );
}
~~~

Nếu iterator thấy đúng reference nhưng `contains(entity)` false, đó là tín hiệu mạnh rằng collection đã lưu entry theo hash cũ hoặc bị thay đổi ngoài contract. `iterator()` không truy cập entry bằng hash của entity như `contains()`.

### Sửa trạng thái Set đang hỏng như thế nào?

Với **HashSet ứng dụng thông thường**, có thể tạo lại một Set mới từ các entries hiện tại để xây buckets theo hash hiện tại:

~~~java
Set<Product> rebuilt = new HashSet<>();
for (Product p : damagedSet) {
    rebuilt.add(p);
}
~~~

Đây là biện pháp phục hồi cấu trúc **tạm thời**, không sửa thiết kế equality. Nếu các phần tử giờ equal theo giá trị mới, việc rebuild có thể **gộp bớt phần tử**. Vì thế cần hiểu uniqueness domain, không làm việc này âm thầm với dữ liệu quan trọng.

**Không áp dụng phương pháp rebuild tùy tiện cho Hibernate persistent collections** đã được gắn với entity managed: thay collection wrapper có thể ảnh hưởng dirty tracking, orphan removal hoặc gây exception về collection ownership. Với persistent collection, nên rollback transaction lỗi, sửa mapping/domain methods và xử lý dữ liệu theo transaction được thiết kế rõ ràng.

## 29. Kiểm thử: generated ID không làm HashSet mất phần tử

Một test quan trọng là thêm entity **trước** persist:

~~~java
@Test
void generatedIdDoesNotBreakHashSet() {
    Product p = new Product("SKU-NEW");
    Set<Product> set = new HashSet<>();

    set.add(p);
    int hashBefore = p.hashCode();

    entityManager.getTransaction().begin();
    entityManager.persist(p);
    entityManager.flush();

    int hashAfter = p.hashCode();

    assertEquals(hashBefore, hashAfter);
    assertTrue(set.contains(p));
    assertTrue(set.remove(p));
    entityManager.getTransaction().rollback();
}
~~~

Ví dụ giả định đang dùng JUnit 5 và `EntityManager` application-managed với transaction `RESOURCE_LOCAL`. Trong project Spring/JTA, transaction cần do framework quản lý. Trong code test thật, nên bảo đảm rollback/close ở finally hoặc test lifecycle; `flush()` chưa commit transaction.

Với implementation `hashCode()` tính trực tiếp từ generated ID, test có thể thất bại. Với constant/class-based hash hoặc natural key bất biến, hash trước/sau được giữ nguyên.

### Vì sao phải test cả `remove()`?

`contains()` true chưa chứng minh tất cả thao tác logic Set đều ổn, đặc biệt khi equals của các phần tử khác đã đổi. Test `remove()` giúp bắt lỗi khi domain method cần xóa một child. Với `@OneToMany(orphanRemoval = true)`, còn cần integration test kiểm tra SQL/DB state sau flush/clear/load lại.

## 30. Kiểm thử: HashMap key sau merge và từ Session khác

Test một thứ khác: yêu cầu collection dedup **theo database identity**, không chỉ theo Java reference.

~~~java
Product first = loadInSessionA(42L);
Product second = loadInSessionB(42L);

Map<Product, String> byEntity = new HashMap<>();
byEntity.put(first, "loaded-A");

String found = byEntity.get(second);
~~~

Kết quả phụ thuộc `equals/hashCode`:

- Reference equality mặc định: `found` thường null vì hai Java objects khác nhau.
- ID-based equality với hash ổn định, entity type/tenant scope đúng: `found` có thể là `"loaded-A"`.
- Business-key equality: phụ thuộc key và state, có thể vô tình coi hai rows khác nhau là cùng entity.

Nếu yêu cầu thật là lookup theo row, thiết kế thường rõ hơn:

~~~java
Map<Long, String> byId = new HashMap<>();
byId.put(first.getId(), "loaded-A");

String foundById = byId.get(second.getId());
~~~

Ở đây không cần kỳ vọng hai entity instances có cùng Java reference hoặc mang cùng state snapshot.

### Thêm tình huống transient

~~~java
Product a = new Product("A");
Product b = new Product("B");
Set<Product> set = new HashSet<>();
set.add(a);
set.add(b);
~~~

Nếu equality theo generated ID, Set phải giữ được **hai đối tượng khác nhau khi cả hai ID null**. Nếu chỉ còn một, cần kiểm tra `equals()` đã coi hai null IDs là equal.

## 31. Bộ tình huống thực hành về mutation

Một bộ thí nghiệm tự chứa có thể dùng các thao tác:

| Thí nghiệm | Thao tác | Điều cần quan sát |
|---|---|---|
| A: Mutable business key | Add vào Set khi email cũ; đổi email | `contains/remove` có thể false, `size` vẫn có entry. |
| B: Generated ID | Add transient entity; persist; flush | Hash trước/sau, `contains/remove`, ID thời điểm cấp. |
| C: Immutable natural key | Add `Country(isoCode)`; persist | Hash không đổi khi `@Id` được cấp. |
| D: Detached copy | Load cùng ID từ hai sessions; add cả hai | Kết quả phụ thuộc reference equality hay ID-based equality. |
| E: Hibernate proxy | `getReference()` so với entity được load | Proxy class/identifier và logic equals có phù hợp không. |
| F: @OneToMany Set | Add child transient; cascade persist; remove | Có xóa quan hệ/xóa orphan đúng theo mapping không. |
| G: Mutable Map key | Put entity vào Map; đổi field trong hash | `get/containsKey/remove` có còn tìm được không. |
| H: Value mutation | Map `Long -> Product`; sửa Product | Lookup theo Long vẫn ổn định. |
| I: Composite key | Dùng `TenantSkuId`, thử sửa component | Phân biệt immutable key và hash bị phá vỡ. |
| J: Constant hash + mutable equals | Hai đối tượng ban đầu khác nhau rồi đổi thành equal | Set có thể chứa hai logical duplicates dù hash không đổi. |

Những kiểm thử này không thay thế unit/integration tests của ứng dụng, nhưng giúp quan sát trực tiếp điều kiện **hash/equality ổn định trong thời gian làm key**, vốn dễ bị che khuất khi chỉ kiểm tra happy path sau khi entity đã có ID.

## 32. Chọn chiến lược theo nhu cầu ứng dụng

| Nhu cầu | Phương án đáng cân nhắc | Cảnh báo |
|---|---|---|
| Chỉ thao tác với object trong một Session, không cần dedup bản sao | Giữ reference equality mặc định | Khác sessions tạo objects khác nhau. |
| Entity cần equal across Sessions theo DB ID | ID-based `equals()` + hash ổn định | Không coi null IDs equal; cân nhắc proxy/hierarchy/tenant. |
| Business key ổn định từ constructor và unique | Equality/hash dựa trên immutable natural key | Không dùng key mutable; có DB unique constraint. |
| Map tra cứu theo entity đã có ID | `Map<Long, Value>` hoặc immutable composite key record | ID phải có trước `put`; xét tenant/type. |
| Map tra cứu theo business identifier | `Map<ImmutableBusinessKey, Value>` | Re-key có chủ đích khi business identifier được phép đổi. |
| Object mới chưa có ID nhưng cần key theo instance | `IdentityHashMap` trong phạm vi hẹp | Không so persistent identity; không thay thế thread safety. |
| Hibernate collection không cần Set semantics | `List` cộng domain methods và DB constraints | List vẫn cần cân nhắc `equals` khi dùng remove/contains. |
| Persistent `@OneToMany Set` với generated-ID children | Equality/hash ổn định xuyên lifecycle và helper hai chiều | Thử nghiệm insert, detach, orphanRemoval, proxy. |
| Nhiều threads dùng shared map | Immutable keys + cấu trúc concurrent phù hợp | ConcurrentHashMap không sửa được mutable-key bug. |

Khi cân nhắc override `equals/hashCode`, đặt câu hỏi: **Cần so cùng Java object, cùng hàng database hay cùng giá trị nghiệp vụ?** Không nên viết equality theo mọi field chỉ vì IDE hoặc Lombok có thể generate.

## 33. Mô hình ghi nhớ cuối bài

~~~mermaid
flowchart TD
    A["Entity sắp dùng trong HashSet / làm HashMap key"] --> B{"equals/hashCode dựa vào gì?"}
    B -- "Reference identity mặc định" --> C["ID/field đổi không đổi identity hash của object"]
    B -- "Generated @Id" --> D{"Hash có đổi khi id null -> giá trị?"}
    D -- "Có" --> E["Nguy cơ tra cứu/xóa sai bucket"]
    D -- "Không" --> F["Vẫn kiểm tra equals null-ID, proxy, tenant"]
    B -- "Business key" --> G{"Business key có immutable không?"}
    G -- "Không" --> E
    G -- "Có" --> H["Đảm bảo uniqueness, normalization, scope"]
    C --> I["Đối chiếu yêu cầu so qua nhiều persistence contexts"]
    F --> I
    H --> I
    I --> J["Cân nhắc dùng immutable ID/record key riêng khi phù hợp"]
~~~

**Kết luận:** Một entity Hibernate có thể thay đổi state thoải mái ở những field không tham gia equality, nhưng **không nên thay đổi giá trị chi phối `equals()/hashCode()` trong thời gian entity nằm trong hash-based collection**. Generated ID thường được cấp **sau khi entity đã được tạo**, nên `hashCode()` theo ID là bẫy nếu entity được đưa vào Set/Map từ lúc transient. Business key có thể đổi cũng tạo bẫy tương tự, còn constant hash chỉ xử lý một nửa vấn đề nếu `equals()` vẫn dựa vào mutable state.

Thiết kế an toàn bắt đầu từ việc phân biệt **Java reference**, **persistence identity** và **business equality**. Chọn một quy tắc ổn định, phù hợp proxy và vòng đời entity; hoặc đơn giản hơn, dùng **immutable key riêng như Long/UUID/composite record** cho HashMap. Với `@OneToMany Set`, còn phải đồng bộ hai phía quan hệ và kiểm tra hành vi cascade/orphanRemoval. Khi làm rõ các ranh giới này, bạn tránh được những lỗi “phần tử vẫn ở đó nhưng không thể tìm/xóa” và giữ object graph nhất quán giữa Java collections với Hibernate.
