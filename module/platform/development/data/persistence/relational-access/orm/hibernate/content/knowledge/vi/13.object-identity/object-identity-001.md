# Phân biệt cùng tham chiếu Java, cùng định danh lưu trữ và cùng giá trị nghiệp vụ

Trong Hibernate ORM, hai biến Java có thể chỉ đến **cùng một đối tượng trong bộ nhớ**, hoặc đến **hai đối tượng khác nhau đại diện cho cùng một bản ghi database**, hoặc đến **hai bản ghi khác nhau nhưng có các giá trị nghiệp vụ giống nhau**. Ba tình huống đó liên quan đến ba khái niệm **danh tính đối tượng (object identity)**, **định danh lưu trữ (persistence identity)** và **bằng nhau về giá trị nghiệp vụ (business/value equality)**. Chúng có thể trùng nhau trong một trường hợp cụ thể, nhưng không nên coi là một.

Phân biệt đúng ba khái niệm giúp giải thích vì sao:

- `a == b` đúng khi đọc cùng một entity hai lần trong một persistence context, nhưng có thể sai khi đọc cùng một hàng ở hai `Session` khác nhau.
- Hai object có `id = 42` có thể đại diện cùng bản ghi, dù chúng không phải cùng object Java.
- Hai khách hàng cùng tên vẫn là hai entity khác nhau nếu có hai khóa chính khác nhau.
- Một entity mới chưa được lưu có `id = null`; nếu viết `equals()` chỉ bằng `Objects.equals(id, other.id)`, nhiều entity mới khác nhau sẽ bị coi là bằng nhau.
- Đưa entity có khóa sinh tự động vào `HashSet` rồi persist có thể khiến `contains()` thất bại nếu `hashCode()` thay đổi sau khi ID được cấp.
- Hibernate proxy, `merge()`, detached state và nhiều persistence context khiến cách so sánh entity trở thành một quyết định kiến trúc, không chỉ là câu chuyện cú pháp `equals()`.

> **Phạm vi:** Bài dùng Jakarta Persistence (`jakarta.persistence`), Hibernate ORM 6.x và Java 17+ ở các ví dụ có record. Hibernate 5 dùng `javax.persistence`. Các ví dụ `Session`, `@NaturalId` và `HibernateProxy` là khả năng riêng của Hibernate; khi muốn dùng JPA provider khác cần cân nhắc tính portable. Bài tập trung vào danh tính và quy tắc so sánh, không giả định mọi cách cài đặt `equals()/hashCode()` đều phù hợp với mọi entity.

## 1. Ba câu hỏi khác nhau đối với cùng hai đối tượng

Giả sử có hai biến `a` và `b` chứa các entity `Customer`.

| Câu hỏi | Khái niệm | Cách kiểm tra thường gặp | Ý nghĩa |
|---|---|---|---|
| Hai biến có chỉ vào **đúng một Java object** không? | **Java reference identity** | `a == b` | Hai reference trỏ đến cùng một instance trong JVM. |
| Hai entity có đại diện **cùng một định danh đã lưu** không? | **Persistence identity** | So entity type/scope và `@Id` theo mapping | Cùng một identity mà ORM/database dùng để nhận diện bản ghi. |
| Hai đối tượng có **cùng giá trị nghiệp vụ** theo quy tắc domain không? | **Business equality** | So các thuộc tính nghiệp vụ được chọn | Ví dụ cùng email chuẩn hóa, cùng mã sản phẩm theo tenant, hoặc cùng tên hiển thị; quy tắc tùy domain. |

Một ví dụ dễ hình dung:

~~~text
Java heap                         Database

a ---> Customer object #A -------+
       id=42, name="Lan"          |
                                  +---- customer(id=42, name="Lan")
b ---> Customer object #B -------+
       id=42, name="Lan"

a == b            -> false  (hai Java objects)
same persisted ID  -> true   (cùng Customer #42)
same name          -> true   (cùng giá trị một field)
~~~

Một ví dụ khác:

~~~text
c ---> Customer object #C -------> customer(id=43, name="Lan")

a == c             -> false
same persisted ID   -> false  (42 khác 43)
same display name   -> true   ("Lan" giống nhau)
~~~

Trong hai ví dụ, “cùng tên” là một tiêu chí so giá trị nghiệp vụ **rất yếu**. Nếu nghiệp vụ định nghĩa khách hàng bằng một mã khác, tiêu chí so bằng nhau phải theo quy tắc đó. Hibernate không thể suy ra mọi luật nghiệp vụ chỉ từ tên field.

## 2. Java reference identity: `==` so sánh cái gì?

Trong Java, với hai biến kiểu tham chiếu, toán tử `==` kiểm tra chúng có trỏ tới **cùng instance** hay không. Nó không so sánh tất cả field và không truy cập database.

~~~java
Customer a = new Customer("lan@example.com", "Lan");
Customer b = a;
Customer c = new Customer("lan@example.com", "Lan");

System.out.println(a == b); // true
System.out.println(a == c); // false
~~~

`a` và `b` cùng trỏ một object; `c` được tạo bằng một lần `new` khác dù hai chuỗi email/name giống nhau. Mọi thay đổi qua `a` đều thấy qua `b` vì thực chất chỉ có một object:

~~~java
a.rename("Lan Nguyen");
System.out.println(b.getDisplayName()); // Lan Nguyen
~~~

Đây là tính chất của **Java heap**, không phụ thuộc Hibernate, transaction hay database.

### `==` và `equals()` không mặc định có cùng mục đích

~~~java
String first = new String("BOOK");
String second = new String("BOOK");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

`String.equals()` so nội dung chuỗi, còn `String` là kiểu giá trị bất biến có semantics rõ ràng. Một JPA entity thường có vòng đời, định danh DB và quan hệ đến entity khác, vì vậy không nên sao chép cách nghĩ “mọi field giống nhau thì `equals()` bằng nhau” của `String` sang entity.

### `System.identityHashCode()` cũng không phải primary key

`System.identityHashCode(object)` trả hash code theo identity object theo cơ chế JVM, không phải giá trị `@Id` và cũng không bảo đảm duy nhất cho mọi object. Hai object khác nhau có thể có identity hash collision. Nó có thể hữu ích khi debug reference identity nhưng không được lưu làm foreign key hoặc business identifier.

## 3. Persistence identity: Hibernate nhận diện entity theo định danh nào?

Một entity được đánh dấu `@Entity` có identity được xác định bởi mapping, thường gồm:

1. **Entity type/entity hierarchy** tương ứng.
2. **Identifier** được ánh xạ bởi `@Id` hoặc `@EmbeddedId`/`@IdClass`.
3. **Phạm vi persistence** liên quan, ví dụ tenant/database/schema khi mô hình đa thuê bao có không gian ID riêng.

Với bảng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    version BIGINT NOT NULL
);
~~~

row:

~~~text
id | email            | display_name | version
---+------------------+--------------+--------
42 | lan@example.com  | Lan          | 3
~~~

thì `customer.id = 42` là khóa chính định danh hàng; email là một **candidate/natural key** nếu được coi là duy nhất theo schema; display name chỉ là field nghiệp vụ không unique.

Trong Hibernate, hai object `Customer` có cùng ID `42` được hiểu là **cùng persistent identity** trong cùng miền nhận diện, kể cả khi chúng hiện đang chứa giá trị `displayName` khác nhau do được load ở thời điểm khác nhau.

### Một entity mẫu

~~~java
import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
@SequenceGenerator(
    name = "customer_id_gen",
    sequenceName = "customer_seq",
    allocationSize = 1
)
public class Customer {
    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "customer_id_gen"
    )
    private Long id;

    @Column(name = "email", nullable = false, length = 200)
    private String email;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected Customer() {} // JPA cần constructor không tham số

    public Customer(String email, String displayName) {
        this.email = Objects.requireNonNull(email);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public Long getId() { return id; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }

    public void rename(String newName) {
        this.displayName = Objects.requireNonNull(newName);
    }
}
~~~

Trong phiên bản class này, chúng ta **chưa override `equals()/hashCode()`**, vì muốn quan sát được khác biệt giữa so reference mặc định và so persistence identity. Phần sau sẽ trình bày những lựa chọn triển khai equality.

Ví dụ khai báo sequence PostgreSQL tương ứng:

~~~sql
CREATE SEQUENCE customer_seq START WITH 1 INCREMENT BY 1;
~~~

### ID có giá trị không chứng minh row đã commit

Với `SEQUENCE`, Hibernate có thể cấp ID trong lúc `persist()` trước khi insert; với `IDENTITY`, ID thường được DB trả sau khi insert nhưng transaction có thể chưa commit. Do đó:

~~~java
entityManager.persist(customer);
Long id = customer.getId();
~~~

`id != null` thường cho biết đã có identifier trong bộ nhớ, **không phải điều kiện bảo đảm row đã commit**. Khi transaction rollback, ID có thể vẫn nằm trên Java object, trong khi hàng tương ứng không còn tồn tại trong database.

## 4. Cùng giá trị nghiệp vụ: phải định nghĩa rõ “giống nhau” là gì

Các field của entity thể hiện nhiều loại thông tin khác nhau:

- **Mã kỹ thuật/PK:** `id = 42`, dùng cho quan hệ FK, truy vấn và persistence identity.
- **Business/natural key:** `email = "lan@example.com"`, nếu nghiệp vụ/schema xác định email là duy nhất trong phạm vi nào đó.
- **Giá trị mô tả:** `displayName = "Lan"`, không nhất thiết unique và có thể thay đổi thường xuyên.

Hai customer có cùng tên:

~~~java
Customer lanA = new Customer("lan.a@example.com", "Lan");
Customer lanB = new Customer("lan.b@example.com", "Lan");

boolean sameName = lanA.getDisplayName()
    .equals(lanB.getDisplayName()); // true
~~~

`sameName` đúng không có nghĩa hai người là cùng một customer entity. Khi chúng được persist, database có thể cấp hai ID khác nhau.

### Business key có thể có phạm vi

Một mã sản phẩm `SKU-001` có thể unique trong một cửa hàng nhưng tồn tại ở nhiều tenant:

~~~text
tenant_id | product_id | sku
----------+------------+--------
10        | 1001       | SKU-001
20        | 1002       | SKU-001
~~~

Trong nghiệp vụ này, **`(tenant_id, sku)`** mới là business key unique, không phải `sku` đơn lẻ. Nếu so giá trị theo `sku` mà bỏ tenant, hai sản phẩm khác nhau có thể bị coi nhầm là một.

Một nguyên tắc khác: **normalization**. Email có thể cần bỏ khoảng trắng, quy ước chữ hoa/chữ thường theo nghiệp vụ hoặc collation DB; nhưng không được giả định toàn bộ địa chỉ email mặc nhiên không phân biệt chữ hoa/thường trong mọi hệ thống. Nếu business key được định nghĩa qua giá trị đã chuẩn hóa, lưu và so sánh phải dùng cùng quy tắc với unique constraint của database.

### Business key có thể thay đổi

Email là ví dụ dễ hiểu nhưng trong nhiều hệ thống khách hàng có thể đổi email. Khi đó email không phải khóa bất biến phù hợp cho mọi `equals()/hashCode()`. Một business key dùng làm equality cho entity cần được đánh giá về tính ổn định trong suốt vòng đời object, không chỉ về uniqueness ở thời điểm hiện tại.

## 5. Bảng tình huống: ba kiểu “giống nhau” có thể tách biệt

| Tình huống | `a == b` | Cùng persistence identity? | Cùng giá trị nghiệp vụ? |
|---|---|---|---|
| `b = a`, cả hai trỏ một object | **Có** | Có nếu object đã có mapped identity tương ứng; object transient chưa có identity đã lưu | Cùng giá trị hiện tại vì là một object. |
| Hai lần `find(Customer.class, 42L)` trong cùng persistence context | Thường **có** | **Có** | Các giá trị đã load trong cùng instance nên giống nhau ở thời điểm so. |
| Load customer #42 bằng hai session khác nhau | Thường **không** | **Có** | Có thể giống hoặc khác tùy snapshot, giao dịch và thời điểm load. |
| Hai customer có ID #42 và #43, cùng display name | **Không** | **Không** | **Có** theo tiêu chí tên hiển thị. |
| Hai transient customer mới, cùng email | **Không** | Chưa có database identity được cấp | Có theo email, dù schema có thể không cho persist cả hai. |
| Entity detached #42 và managed entity #42 sau `merge()` | Có thể **không** | **Có** | Có thể giống tại một thời điểm, nhưng trạng thái sau này có thể tách nhau. |

Những câu trả lời “cùng giá trị nghiệp vụ” chỉ có ý nghĩa khi đã xác định **tập field và quy tắc domain**. Hai customer có cùng name nhưng khác email có “bằng nhau” hay không phụ thuộc bạn đang hỏi “cùng tên” hay “cùng khách hàng theo email”.

## 6. Persistence context: vì sao đọc một row hai lần thường nhận cùng object

Hibernate `Session` hoặc JPA `EntityManager` quản lý một **persistence context** (first-level cache/identity map). Trong context đó, ORM giữ một instance managed ứng với một entity identity, tránh tạo nhiều managed objects độc lập cho cùng hàng.

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Customer a = entityManager.find(Customer.class, 42L);
Customer b = entityManager.find(Customer.class, 42L);

System.out.println(a == b); // thông thường true
System.out.println(entityManager.contains(a)); // true

tx.commit();
~~~

Nếu customer #42 đang tồn tại và context không bị clear/detach giữa hai lời gọi, Hibernate thường trả cùng reference. Lần tìm thứ hai thường không cần thêm `SELECT` vì identity map đã có entity managed.

~~~mermaid
flowchart LR
    A["find(Customer, 42)"] --> C["Persistence Context"]
    B["find(Customer, 42) lần 2"] --> C
    C --> D["Identity key: Customer / 42"]
    D --> E["Managed Customer object #A"]
~~~

Đây là lý do một entity managed có thể thay đổi trong bộ nhớ và được đọc lại từ context với trạng thái vừa thay, ngay cả khi SQL `UPDATE` chưa được flush xuống DB.

### Một query HQL cũng dùng managed identity

~~~java
Customer a = entityManager.find(Customer.class, 42L);

Customer b = entityManager.createQuery(
    "select c from Customer c where c.id = :id",
    Customer.class
).setParameter("id", 42L)
 .getSingleResult();

System.out.println(a == b); // thông thường true nếu cùng managed context
~~~

Query có thể chạy SQL, nhưng khi materialize kết quả, Hibernate tham chiếu entity đang được quản lý nếu identity đã nằm trong persistence context. **Query trả entity** khác với projection trả DTO hoặc scalar: DTO là object mới theo quy tắc của constructor/projection, không nhất thiết dùng identity map entity.

### Giới hạn của bảo đảm

Không xây ứng dụng phụ thuộc tuyệt đối vào `==` như cách xác nhận hai entity cùng database row. Các kỹ thuật proxy/lazy references, bytecode enhancement và đặc điểm của provider có thể làm cách ứng dụng nhìn reference/concrete class khác với trực giác. Bảo đảm quan trọng là Hibernate **không quản lý hai state entity độc lập cho cùng entity key trong một persistence context bình thường**; còn logic nghiệp vụ cần so identity một cách tường minh nếu đi qua nhiều context.

## 7. Hai Session khác nhau: cùng hàng nhưng thường khác Java instance

First-level cache thuộc về từng persistence context. Hai Hibernate sessions không chia sẻ identity map instance:

~~~java
Customer first;
Customer second;

try (Session s1 = sessionFactory.openSession();
     Session s2 = sessionFactory.openSession()) {
    first = s1.find(Customer.class, 42L);
    second = s2.find(Customer.class, 42L);
}

System.out.println(first == second); // thông thường false
System.out.println(first.getId().equals(second.getId())); // true
~~~

Ví dụ giả định customer #42 tồn tại và mapping có ID dạng `Long`. Ở code thực tế nên quản lý transaction đọc phù hợp với database/configuration, và cần kiểm tra null trước khi dereference nếu hàng có thể không tồn tại.

~~~text
Session A                        Session B
IdentityMap A                    IdentityMap B
Customer/42 -> Java #A           Customer/42 -> Java #B
                    \            /
                     \          /
                    database row #42
~~~

**Second-level cache không thay thế quy tắc này.** Nếu bật Hibernate second-level cache, các session có thể tái sử dụng dữ liệu trạng thái đã cache, nhưng mỗi persistence context vẫn quản lý entity instances riêng. Không mong `s1.find(...) == s2.find(...)` chỉ vì có shared cache.

### Trạng thái có thể khác nhau

~~~text
T1: Session A load #42, displayName = "Lan"
T2: Transaction khác cập nhật #42, displayName = "Lan Nguyen", rồi commit
T3: Session B load #42, displayName = "Lan Nguyen"
~~~

Hai Java objects đại diện **cùng persistence identity**, nhưng `displayName` có thể khác nhau tại thời điểm so do caching và transaction isolation. Đây là ví dụ rõ ràng cho thấy **cùng ID không đồng nghĩa tất cả field hiện có bằng nhau**.

Nếu application cần trạng thái DB mới nhất, phải cân nhắc transaction isolation, refresh/reload, cache và optimistic locking, không chỉ so ID.

## 8. Transient, managed, detached và removed ảnh hưởng so sánh ra sao?

Entity có các trạng thái vòng đời:

| State | Ý nghĩa | `@Id`/so sánh cần chú ý |
|---|---|---|
| **Transient/new** | Object Java mới, chưa được Hibernate quản lý | ID generated thường `null`; hai transient objects cùng `null` không phải cùng persistence identity. |
| **Managed** | Được persistence context quản lý | Hibernate theo dõi ID, dirty state, snapshot; lặp truy vấn thường trả managed instance theo identity map. |
| **Detached** | Từng managed nhưng đã tách khỏi context | Vẫn có ID, nhưng sửa object không được tự động flush vào DB; có thể tồn tại nhiều bản sao detached/managed cùng ID trong JVM. |
| **Removed** | Đã được đánh dấu xóa trong context | ID có thể vẫn hiện diện trên object dù row sắp bị xóa; identity trong bộ nhớ không đảm bảo row còn tồn tại sau commit. |

~~~java
Customer customer = new Customer("a@example.com", "A");
System.out.println(customer.getId()); // thường null trước persist

entityManager.persist(customer);      // managed, có thể được cấp ID
entityManager.flush();                // SQL ghi nếu cần

entityManager.detach(customer);       // detached
customer.rename("Updated locally");   // không tự ghi DB
~~~

Chỉ so `customer.getId()` không cho biết object đang managed hay detached. Muốn biết một instance cụ thể có được context hiện tại quản lý không, dùng `entityManager.contains(customer)`; ngay cả khi ID khớp với một managed instance khác, detached instance vẫn không vì thế tự trở thành managed.

### Sau rollback có thể có ID nhưng không có row

Với generator như sequence, một entity đã được cấp `id = 120` trong transaction rồi rollback có thể vẫn mang ID 120. Do đó so ID để xác định “hai object cùng bản ghi đã lưu” phải giả định bản ghi thực sự tồn tại/được xác nhận. **Giá trị khóa được gán** và **row đã commit** là hai tình trạng khác nhau.

## 9. `merge()`: cùng định danh nhưng object ban đầu không trở thành managed

Đây là nơi nhiều lập trình viên nhầm ba loại danh tính:

~~~java
Customer detached = loadCustomerInPreviousSession(42L);
// previous session đã đóng; detached có id=42

EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Customer managed = entityManager.merge(detached);

System.out.println(detached == managed); // thường false
System.out.println(
    detached.getId().equals(managed.getId())
); // true nếu cùng persistent identity

managed.rename("Lan Updated");
tx.commit();
~~~

`merge()` **sao chép state của detached object vào managed instance** tương ứng hoặc tạo managed copy thích hợp; nó **trả về managed instance**. Detached instance được truyền vào không trở thành managed chỉ nhờ gọi `merge()`.

Nếu persistence context đã chứa `Customer#42`, Hibernate thường sử dụng chính managed instance đó làm đối tượng nhận state. Nếu chưa có, Hibernate có thể load row hoặc tạo managed instance, theo mapping và state. Vì vậy `managed == detached` không phải điều kiện để xác nhận merge đúng.

### Sai lầm thường gặp

~~~java
entityManager.merge(detached);
detached.rename("New name after merge");
tx.commit();
~~~

Đổi `detached` sau lời gọi merge có thể không được theo dõi. Hãy dùng kết quả:

~~~java
Customer managed = entityManager.merge(detached);
managed.rename("New name after merge");
tx.commit();
~~~

Nếu muốn đối chiếu entity trước và sau merge, hãy so persistence identity khi cần, hoặc quan sát state của managed instance; không dùng `==` giữa detached và managed làm điều kiện nghiệp vụ.

### `persist()` khác `merge()`

`persist()` dùng cho entity mới theo semantics JPA; `merge()` dùng để sao chép trạng thái vào managed entity thích hợp. Đừng gọi `persist()` trên một detached entity có ID rồi kỳ vọng Hibernate “nhận ra đây là cùng row và cập nhật” trong mọi trường hợp; có thể gặp lỗi detached entity hoặc duplicate key.

## 10. `equals()` mặc định của Object: phù hợp trong hoàn cảnh nào?

Nếu entity không override `equals()`, nó thừa hưởng `Object.equals()` và `Object.hashCode()`. Semantics mặc định của `equals()` gần với reference identity: chỉ bằng nhau khi cùng object.

~~~java
Customer a = new Customer("a@example.com", "A");
Customer b = new Customer("a@example.com", "A");

System.out.println(a.equals(b)); // false nếu không override
System.out.println(a == b);      // false
~~~

Với entity chỉ đi qua **một transaction/persistence context** và không dùng làm key/element trong collections cần de-dup giữa nhiều contexts, cách mặc định có thể đơn giản, ổn định và tránh các lỗi hash code do generated ID.

Nhược điểm: hai detached objects hoặc một detached và một managed entity cùng ID sẽ `equals() == false` mặc dù cùng persistence identity. Khi ứng dụng dùng `Set<Customer>` hoặc so object qua service/serialization boundary, điều này có thể không phù hợp mong muốn.

### Không có quy tắc “mọi JPA entity bắt buộc override equals”

Việc override phụ thuộc cách domain dùng entity và các yêu cầu từ collection/API. Một entity không override equals vẫn là entity hợp lệ, vẫn được Hibernate nhận diện theo `@Id` và persistence context. **Hibernate không sử dụng chính `Customer.equals()` để quyết định mọi thứ về khóa chính trong identity map.**

Ngược lại, khi chọn override, phải giữ đúng hợp đồng `equals()/hashCode()` của Java và tránh xung đột với proxy, inheritance, ID generation và mutable business state.

## 11. Ba chiến lược viết `equals()/hashCode()` cho entity

| Chiến lược | Định nghĩa equality | Điểm mạnh | Rủi ro |
|---|---|---|---|
| **Giữ mặc định reference equality** | Chỉ cùng Java instance mới equal | Đơn giản, hash ổn định, ít lazy side effect | Các bản sao cùng DB row ở khác session không equal. |
| **So persistent ID** | Cùng entity type/identity scope và `@Id` không null | Hợp lý khi thường xuyên so entity qua các context | ID sinh sau persist; phải xử lý transient null, stable hash và proxy. |
| **So immutable business key** | Cùng khóa nghiệp vụ ổn định và đúng scope | Có thể so entity ngay khi transient; hash ổn nếu key bất biến | Key phải unique/immutable theo domain; proxy có thể kích hoạt load; migration/business rules phức tạp. |

**Không nên mặc định so tất cả field.** Một entity có quan hệ bidirectional, lazy collections, version, lastUpdated, giá trị có thể sửa... So toàn bộ field vừa có chi phí lớn vừa khiến equality thay đổi theo thời gian.

Trong những phần sau, ta xét các cách triển khai cụ thể và giới hạn của từng cách.

## 12. Anti-pattern: so `@Id` bằng `Objects.equals()` mà không kiểm tra null

Một cách viết dễ thấy:

~~~java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Customer customer)) return false;
    return Objects.equals(id, customer.id);
}

@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Vấn đề thứ nhất: hai entity transient khác nhau thường đều có `id = null`:

~~~java
Customer a = new Customer("a@example.com", "A");
Customer b = new Customer("b@example.com", "B");

// id của cả a và b đều null:
// Objects.equals(a.id, b.id) == true
~~~

Nếu `equals()` trả true, một `HashSet` có thể chỉ giữ lại một trong hai khách hàng mới:

~~~java
Set<Customer> customers = new HashSet<>();
customers.add(a);
customers.add(b);
// Có thể chỉ còn 1 phần tử nếu equals() dùng null-ID sai cách.
~~~

Vấn đề thứ hai: `hashCode()` từ ID thay đổi khi Hibernate cấp ID. Điều này vi phạm giả định ổn định của hash-based collections trong lúc object là thành viên của chúng.

### Quy tắc cần có với equality theo generated ID

Một object transient **không được xem là bằng một transient object khác chỉ vì cả hai `id` null**. Sau khi đã có identifier, equality theo ID phải kiểm tra type/scope phù hợp. `hashCode()` phải ổn định khi ID từ null thành giá trị sinh.

## 13. Ví dụ equality theo generated ID với hash code ổn định

Đây là **một lựa chọn thực tế** cho entity không có kế thừa entity con và có ID do provider cấp. Nó thể hiện các mục tiêu:

- Cùng reference thì equal.
- Hai entity mới khác nhau có `id = null` không equal.
- Hai instance cùng concrete persistent type và non-null ID thì equal.
- `hashCode()` không đổi khi Hibernate gán ID.
- Xử lý lớp Hibernate proxy theo cách phản ánh persistent class thay vì Java proxy subclass.

~~~java
import java.util.Objects;
import org.hibernate.proxy.HibernateProxy;

@Entity
@Table(name = "customer")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    // Các field/method khác như phần entity mẫu...

    public Long getId() { return id; }

    private static Class<?> persistentClass(Object object) {
        if (object instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                        .getPersistentClass();
        }
        return object.getClass();
    }

    private static Object identifier(Customer entity) {
        if (entity instanceof HibernateProxy proxy) {
            return proxy.getHibernateLazyInitializer()
                        .getIdentifier();
        }
        return entity.getId();
    }

    @Override
    public final boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Customer that)) return false;
        if (persistentClass(this) != persistentClass(that)) return false;

        Object thisId = identifier(this);
        Object thatId = identifier(that);
        return thisId != null && Objects.equals(thisId, thatId);
    }

    @Override
    public final int hashCode() {
        return persistentClass(this).hashCode();
    }
}
~~~

**Giải thích từng quyết định:**

1. `this == other` xử lý nhanh trường hợp cùng object, kể cả transient.
2. `instanceof Customer` loại object không thuộc kiểu entity đang so; trong mô hình có inheritance phức tạp cần thiết kế quy tắc class equality riêng.
3. `persistentClass(...)` dùng Hibernate proxy metadata để xác định class entity mà proxy đại diện, tránh so trực tiếp `getClass()` của proxy subclass với entity class thông thường.
4. `identifier(...)` đọc identifier của proxy qua lazy initializer; với entity thường đọc getter.
5. `thisId != null` ngăn hai transient instances có ID null bị coi là equal.
6. `hashCode()` dựa vào persistent class, không dựa vào ID vốn thay đổi từ null sang số.

Trong ví dụ này, mọi `Customer` đã persist có cùng hash code nếu cùng entity class. Điều đó **hợp lệ** theo Java contract (equal objects bắt buộc cùng hash; objects khác nhau được phép trùng hash), nhưng hiệu năng hash-based collection có thể giảm nếu chứa rất nhiều entity cùng class. Cần đo theo cách sử dụng thực tế; không phải mọi ứng dụng nên copy đúng công thức này.

### Lưu ý về proxy và Hibernate version

`HibernateProxy` là API riêng của Hibernate. Phương thức `getIdentifier()` trên proxy có thể có hành vi khởi tạo phụ thuộc cấu hình JPA proxy compliance; truy cập một entity qua proxy cũng có những giới hạn với mapping/inheritance. Khi cần portable JPA, không thể mặc định dùng lớp này ở provider khác. Cách viết trên là **một ví dụ có chủ đích**, không phải hợp đồng chuẩn JPA cho mọi kiểu hierarchy.

### Lưu ý về inheritance

Nếu `Customer` là root của một hierarchy, cách so exact concrete class có thể khiến hai proxy/instance nhìn ở cấp khác nhau cần được xử lý theo cùng semantics entity identity của hierarchy. Không viết công thức so class hoặc `instanceof` tùy tiện trên root và subtype rồi để `equals()` bất đối xứng. Phần kế tiếp giải thích thêm.

## 14. Hợp đồng `equals()/hashCode()` của Java

Nếu override equality, phải tuân thủ:

| Thuộc tính | Yêu cầu |
|---|---|
| **Reflexive** | `a.equals(a)` luôn true với object không null. |
| **Symmetric** | `a.equals(b)` và `b.equals(a)` có cùng kết quả. |
| **Transitive** | Nếu `a.equals(b)` và `b.equals(c)`, thì `a.equals(c)`. |
| **Consistent** | Khi các thông tin dùng để so không thay đổi, kết quả phải nhất quán qua nhiều lần gọi. |
| **Non-null** | `a.equals(null)` phải false. |
| **Hash contract** | Nếu `a.equals(b)` true thì `a.hashCode() == b.hashCode()`. |

Vi phạm hợp đồng gây lỗi trong `HashMap`, `HashSet` và nhiều thuật toán Java Collection, kể cả khi code ORM vẫn chạy.

### Một lỗi bất đối xứng do inheritance

Giả sử:

~~~java
class BaseEntity {
    Long id;

    @Override
    public boolean equals(Object o) {
        if (!(o instanceof BaseEntity b)) return false;
        return id != null && id.equals(b.id);
    }
}

class SpecialEntity extends BaseEntity {
    String specialCode;

    @Override
    public boolean equals(Object o) {
        if (!(o instanceof SpecialEntity s)) return false;
        return super.equals(s)
            && Objects.equals(specialCode, s.specialCode);
    }
}
~~~

`BaseEntity.equals(special)` có thể true theo ID, nhưng `SpecialEntity.equals(base)` false vì base không phải subtype. Đây là vi phạm symmetry. Nếu có JPA inheritance, hãy thống nhất một định nghĩa equality ở hierarchy và cân nhắc Hibernate proxy behavior.

Một thiết kế đơn giản thường là **không tạo entity inheritance chỉ để tái sử dụng equals**, hoặc dùng root entity với logic identity nhất quán. Nếu cần một base class dùng chung, giới hạn rõ class nào có identity namespace chung và cách phân biệt subtype.

## 15. Proxy: cùng bản ghi không đồng nghĩa cùng Java runtime class

Hibernate có thể tạo lazy proxy khi gọi `getReference()` hoặc truy cập association:

~~~java
Customer reference = entityManager.getReference(Customer.class, 42L);
Customer loaded = entityManager.find(Customer.class, 42L);
~~~

Trong cùng persistence context, Hibernate thường kết nối cả hai thao tác với cùng managed identity. Tuy nhiên, `reference.getClass()` có thể trả **proxy subclass**, còn class gốc là `Customer.class`; hành vi có thể khác khi Hibernate dùng bytecode enhancement hoặc khi provider không tạo proxy theo cách đó.

~~~java
System.out.println(reference.getClass() == Customer.class);
// Có thể false vì Hibernate tạo proxy subclass.
~~~

Đây là lý do cách viết:

~~~java
if (getClass() != other.getClass()) return false;
~~~

có thể làm hai biểu diễn cùng persistent identity bị coi khác class.

### `Hibernate.getClass()` và proxy initialization

Hibernate có `Hibernate.getClass(object)` để lấy effective persistent class, nhưng tùy phiên bản nó có thể khởi tạo proxy hoặc tạo thêm truy vấn. Giải pháp `HibernateProxy.getHibernateLazyInitializer().getPersistentClass()` trong ví dụ trước tránh dựa hoàn toàn vào `getClass()` của proxy subclass, song vẫn là API gắn với Hibernate. Đặc biệt, không nên dựa vào class comparison để thực hiện business query theo subtype; trong JPQL dùng `TYPE()` khi lọc trên DB.

### Hai entity cùng ID nhưng thuộc hierarchy khác nhau

Chỉ so số `id` không đủ nếu:

~~~text
Customer(id=1)
PurchaseOrder(id=1)
~~~

Hai loại entity có thể có cùng khóa số trong **hai bảng riêng** nhưng chắc chắn không phải cùng persistent identity. Đây là lý do equality theo generated ID phải xét **entity type/namespace**, không so `id` trần.

Trong `@Inheritance`, nhiều subtype của cùng root có thể chung một identity namespace. Khi thiết kế equality theo class, cần xét loại root, concrete subtype và việc Hibernate bảo đảm một row thuộc subtype cụ thể; không tự động so các lớp bất kỳ có cùng `id`.

## 16. Vấn đề `HashSet` khi ID thay đổi sau persist

Giả sử `hashCode()` được viết:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
~~~

Rồi entity được đưa vào hash-based collection trước khi persist:

~~~java
Customer customer = new Customer("a@example.com", "A");
Set<Customer> set = new HashSet<>();

set.add(customer);                // id hiện null
entityManager.persist(customer); // id có thể được sinh ở đây

System.out.println(set.contains(customer)); // có thể false
~~~

Vì `HashSet` đặt object vào một bucket dựa trên hash lúc `add()`, sau đó `hashCode()` đổi khi ID được gán, `contains()` có thể tìm nhầm bucket. Dù `set.add(customer)` từng thành công, collection không còn hoạt động đúng như mong đợi.

### Hai cách tránh

**Cách 1:** Giữ reference-based equality mặc định khi không cần de-dup across contexts. `Object.hashCode()` ổn định theo object trong vòng đời sử dụng bình thường.

**Cách 2:** Nếu equality theo generated ID, dùng **stable hash code** không đổi khi ID được cấp, ví dụ constant/class-based hash như phần trên. Khi đó transient object có thể đã trong Set trước khi persist mà `contains()` vẫn tìm được.

**Cách 3:** Nếu có **immutable natural key** đã được gán trước khi entity vào Set, có thể định nghĩa equality/hash theo key đó, với điều kiện key unique và không bị thay đổi.

Lưu ý: Không nên thay toàn bộ domain model sang `Set` chỉ vì muốn dedup bản ghi database. Với những thao tác cần tra cứu theo identity, một cấu trúc `Map<EntityId, Entity>` sử dụng khóa ID ổn định có thể rõ ràng hơn, đặc biệt khi entity chưa được persist.

## 17. Natural/business key: khi nào phù hợp để viết equality?

Một natural key là giá trị có ý nghĩa nghiệp vụ được dùng để nhận diện đối tượng, ví dụ mã quốc gia ISO, mã đơn vị tổ chức bất biến trong một hệ thống, hoặc mã sản phẩm ổn định trong một tenant.

Hibernate có annotation `@NaturalId`:

~~~java
import jakarta.persistence.*;
import org.hibernate.annotations.NaturalId;

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
    @Column(
        name = "iso_code",
        nullable = false,
        updatable = false,
        length = 2
    )
    private String isoCode;

    @Column(nullable = false)
    private String name;

    protected Country() {}

    public Country(String isoCode, String name) {
        this.isoCode = java.util.Objects.requireNonNull(isoCode);
        this.name = java.util.Objects.requireNonNull(name);
    }

    public String getIsoCode() { return isoCode; }
}
~~~

Trong ví dụ, `isoCode` là business key **bất biến** sau khi tạo. Nếu tất cả row của `Country` luôn có ISO code đã được chuẩn hóa, unique theo DB và không đổi, so equality theo `isoCode` có thể thích hợp cả khi object chưa persist.

Ví dụ khái niệm:

~~~java
Country a = new Country("VN", "Viet Nam");
Country b = new Country("VN", "Vietnam");

// Nếu equality của Country được định nghĩa theo isoCode:
// a.equals(b) -> true, mặc dù a != b và a/b đều transient.
~~~

Đây là một **quyết định domain**: hai object có cùng natural key được coi là đại diện cho một quốc gia theo định nghĩa nghiệp vụ. Nhưng DB unique constraint vẫn cần thiết, vì `equals()` ở Java **không ngăn được hai transaction khác nhau chèn duplicate key**.

### Natural key khác primary key

| Primary key `@Id` | Natural key `@NaturalId` |
|---|---|
| Dùng làm persistence identity và khóa tham chiếu chính trong ORM. | Dùng nhận diện theo một hoặc nhiều thuộc tính nghiệp vụ. |
| Có thể do DB/provider sinh tự động. | Thường ứng dụng biết trước; có thể unique theo domain. |
| Có thể là surrogate number/UUID. | Có ý nghĩa nghiệp vụ, ví dụ ISO country code. |
| Phải bảo đảm unique theo identity scope. | Cần ràng buộc unique phù hợp schema/scope; `@NaturalId` riêng nó không thay thế mọi DDL migration. |
| Không nên tùy ý thay khi entity đã managed. | Có thể immutable hoặc mutable tùy mapping/nghiệp vụ; mutable key không thích hợp cho stable hash nếu thay khi ở Set. |

### Tìm entity theo natural ID với Hibernate

~~~java
try (Session session = sessionFactory.openSession()) {
    Country country = session.bySimpleNaturalId(Country.class)
                             .load("VN");
}
~~~

Hibernate hỗ trợ natural-id resolution và có các tùy chọn cache natural ID theo cấu hình. Đây là cơ chế lookup riêng, **không biến `isoCode` thành `@Id`** và cũng không tự định nghĩa `equals()/hashCode()` của entity. Nếu muốn equality theo natural key, vẫn phải viết và duy trì logic tương ứng.

## 18. Ví dụ equality theo immutable business key

Nếu chọn so `Country` theo mã ISO, một triển khai khái niệm có thể:

~~~java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Country country)) return false;
    return isoCode != null
        && isoCode.equals(country.getIsoCode());
}

@Override
public int hashCode() {
    return java.util.Objects.hashCode(isoCode);
}
~~~

Code này chỉ phù hợp nếu:

1. `isoCode` đã được gán trước khi đối tượng có thể xuất hiện trong `HashSet` hoặc làm key trong `HashMap`.
2. `isoCode` **không thay đổi** sau đó.
3. Giá trị key đã được chuẩn hóa theo quy tắc nghiệp vụ.
4. Tất cả entity cùng loại/scope chia sẻ cùng quy tắc unique của database.
5. Các trường hợp proxy/inheritance được xử lý nếu chúng xuất hiện trong ứng dụng.

Ví dụ trên ngắn để tập trung vào semantics; với Hibernate proxy, lấy trực tiếp field `isoCode` của một proxy chưa initialize có thể gặp vấn đề, và gọi getter có thể kích hoạt lazy initialization. Nếu muốn một implementation dùng Hibernate proxy thật sự, phải thiết kế thêm cách lấy key an toàn (hoặc chấp nhận initialization theo transaction boundaries). Không dùng code minh họa làm “mẫu chung” cho mọi entity.

### Key mutable phá vỡ hash-based collections

~~~java
Country c = new Country("VN", "Viet Nam");
Set<Country> set = new HashSet<>();
set.add(c);

// Nếu cho phép:
c.setIsoCode("XX");

set.contains(c); // có thể false vì hashCode đã đổi
~~~

Đó là lý do equality theo business key đòi key bất biến, hoặc ứng dụng phải tránh dùng entity làm hash collection key xuyên qua thay đổi đó. Một `@NaturalId(mutable = true)` có thể là mapping hợp lệ nhưng không vì thế tự trở thành equality key an toàn.

## 19. Entity equality khác value-object equality

Với entity, định danh là thuộc tính nền tảng: hai entity có mọi field giống nhau vẫn có thể là hai đối tượng nghiệp vụ độc lập. Trong khi đó, **value object** thường bằng nhau khi toàn bộ giá trị có ý nghĩa giống nhau.

Ví dụ Java record:

~~~java
public record Money(
    java.math.BigDecimal amount,
    String currencyCode
) {
    public Money {
        if (amount == null || currencyCode == null) {
            throw new IllegalArgumentException("Money fields required");
        }
    }
}
~~~

~~~java
Money priceA = new Money(new BigDecimal("10.00"), "USD");
Money priceB = new Money(new BigDecimal("10.00"), "USD");

System.out.println(priceA == priceB);      // false
System.out.println(priceA.equals(priceB)); // true
~~~

Lưu ý `BigDecimal.equals()` xét cả scale, nên `new BigDecimal("10.0")` và `new BigDecimal("10.00")` **không equal** theo Java mặc dù `compareTo() == 0`; nếu domain của `Money` muốn bỏ qua scale phải định nghĩa normalization/equality riêng.

Trong JPA, value object có thể được map bằng `@Embeddable`:

~~~java
@Embeddable
public class PostalAddress {
    private String city;
    private String street;

    protected PostalAddress() {}

    public PostalAddress(String city, String street) {
        this.city = city;
        this.street = street;
    }

    // equals/hashCode theo giá trị nếu domain định nghĩa như vậy.
}
~~~

Một `@Embeddable` không có `@Id` riêng như entity độc lập; nó thường là một phần state của entity chứa. So sánh theo giá trị là thiết kế tự nhiên hơn, nhưng vẫn phải chọn những trường phù hợp domain và ổn định nếu được dùng trong hash collection.

### Một ví dụ phân biệt

Hai `PurchaseOrder` có cùng `Money(total = 100 USD)` chưa chắc cùng đơn hàng. Hai `Money` bằng nhau theo giá trị không hề ngụ ý các đơn chứa chúng có cùng persistence identity.

## 20. Composite key và phạm vi định danh

Không phải mọi entity có một cột `id` đơn. Trong hệ thống đa tenant, một định danh có thể là `(tenantId, localCustomerId)`:

~~~sql
CREATE TABLE tenant_customer (
    tenant_id BIGINT NOT NULL,
    customer_no BIGINT NOT NULL,
    display_name VARCHAR(150),
    PRIMARY KEY (tenant_id, customer_no)
);
~~~

Ở đây:

~~~text
(tenant_id=10, customer_no=42)
(tenant_id=20, customer_no=42)
~~~

là **hai persistence identities khác nhau**, dù phần `customer_no` bằng nhau.

Với `@EmbeddedId`:

~~~java
import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class TenantCustomerId implements Serializable {
    @Column(name = "tenant_id")
    private Long tenantId;

    @Column(name = "customer_no")
    private Long customerNo;

    protected TenantCustomerId() {}

    public TenantCustomerId(Long tenantId, Long customerNo) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.customerNo = Objects.requireNonNull(customerNo);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TenantCustomerId that)) return false;
        return Objects.equals(tenantId, that.tenantId)
            && Objects.equals(customerNo, that.customerNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, customerNo);
    }
}

@Entity
@Table(name = "tenant_customer")
public class TenantCustomer {
    @EmbeddedId
    private TenantCustomerId id;

    @Column(name = "display_name")
    private String displayName;

    protected TenantCustomer() {}
    // constructor, getter và domain methods...
}
~~~

`TenantCustomerId` là **value object định danh**: hai ID objects có cùng hai thành phần thì equal dù không cùng Java reference. JPA yêu cầu primary key class phù hợp và equality/hash dựa trên các thành phần khóa. Không thay đổi field khóa sau khi entity được lưu; ví dụ có thể thiết kế constructor/getter và không cung cấp public setter.

### Multi-tenancy theo schema/database

Nếu hai tenant được tách ở hai schema hoặc database khác nhau và cùng có `Customer#42`, so mỗi số `42` cũng không đủ để kết luận đó là cùng một bản ghi toàn hệ thống. Persistence identity phải được hiểu trong **phạm vi tenant/persistence unit** tương ứng. Vì vậy, equality theo `id` không chứa tenant scope có thể sai nếu ứng dụng đưa entity từ nhiều tenant vào cùng một collection.

## 21. `@Version` giúp phát hiện xung đột, không phải định danh

Giả sử:

~~~text
Session A: Customer(id=42, version=3, name="Lan")
Session B: Customer(id=42, version=4, name="Lan Nguyen")
~~~

Hai object đại diện **cùng persistence identity** dù `version` và `displayName` khác nhau. `@Version` được dùng để phát hiện concurrent updates:

~~~sql
UPDATE customer
SET display_name = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Nếu row đã bị transaction khác cập nhật, điều kiện version cũ có thể ảnh hưởng 0 row và Hibernate ném optimistic-lock exception. `version` thay đổi theo vòng đời, nên thường **không nên đưa nó vào `equals()/hashCode()`** của entity.

### Vì sao không so mọi field?

Nếu equality bao gồm `version` hoặc `displayName`, một entity trước và sau khi update có thể đổi hash code và “không equal với chính bản sao detached cùng ID” chỉ vì hai bản thể hiện snapshot khác nhau. Với entity, điều này thường ngược mong muốn nếu `equals` được định nghĩa theo persistence identity.

Business layer đôi khi thật sự cần so **state differences**, nhưng đó là một tác vụ khác: có thể viết `sameContentAs(...)` hoặc diff DTO/snapshot thay vì thay đổi equality toàn cục của entity.

## 22. Hibernate collections, Set và quan hệ hai chiều

Một `@OneToMany` có thể được khai báo:

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private Set<OrderLine> lines = new HashSet<>();
~~~

Nếu entity con có `equals()/hashCode()` sai, Hibernate persistent collection hoặc code domain có thể gặp các hành vi khó hiểu khi thêm/xóa phần tử:

- Hai con transient có `id = null` bị coi là bằng nhau nếu equality so null-ID.
- Sau `persist()`, ID được cấp và hash code đổi, khiến `lines.remove(line)` có thể thất bại.
- Equality so association `line.order` có thể kích hoạt lazy loading, đệ quy qua `order.lines` hoặc vòng lặp equals.
- Equality so nhiều field mutable có thể khiến collection coi một entity thành “phần tử khác” sau thay đổi.

Với một quan hệ hai chiều:

~~~java
OrderLine line = new OrderLine("BOOK-01", 2);
order.addLine(line); // helper cập nhật cả order.lines và line.order
~~~

Domain method phải đồng bộ owning/inverse side theo mapping. Equality của entity con là **một quyết định riêng**; nó không thay thế việc đặt `line.order` để Hibernate ghi đúng FK.

### HashSet và persistent collection

Chọn `Set` nếu nghiệp vụ thật sự cần unique membership theo equality đã định nghĩa, không chỉ để “Hibernate tự bỏ duplicate DB rows”. Database uniqueness vẫn nên được bảo vệ bằng primary/unique constraints. Với một tập có số lượng rất lớn, class-constant hash như ví dụ ID-based có thể gây nhiều collisions; đôi khi `List` và kiểm tra membership bằng khóa ổn định hoặc query DB sẽ phù hợp hơn.

## 23. Lombok `@Data` và entity equality: cần thận trọng

Lombok `@Data` thường tạo getter, setter, `toString()`, `equals()` và `hashCode()` dựa trên các field. Với JPA entity có association/lazy fields, mặc định này có thể gây:

1. `equals()` so toàn bộ field, gồm collection và mutable state.
2. `hashCode()` đổi khi setter thay đổi business field hoặc ID.
3. `toString()` truy cập lazy association, gây SQL bất ngờ hoặc `LazyInitializationException` khi session đóng.
4. Quan hệ hai chiều có thể đệ quy vô hạn qua `parent.children -> child.parent`.

Ví dụ cần tránh áp dụng máy móc:

~~~java
@lombok.Data
@Entity
class PurchaseOrder {
    @Id
    Long id;

    @OneToMany(mappedBy = "order")
    List<OrderLine> lines;
}
~~~

Với entity, thường nên chọn annotation Lombok cụ thể như `@Getter`, `@Setter` (có kiểm soát), `@ToString(onlyExplicitlyIncluded = true)` hoặc tự viết equality theo định nghĩa domain. Không nên dùng `@Data` như shortcut mà không kiểm tra generated methods.

### Nếu business key là email, có nên dùng Lombok EqualsAndHashCode(of = "email")?

Chỉ khi email thật sự bất biến, unique theo scope phù hợp và proxy/inheritance semantics được xử lý. Nếu cho phép đổi email, hash code có thể đổi. Nếu email unique chưa được DB bảo đảm, hai bản ghi khác nhau có thể bị coi equal. Annotation không tự quyết định quy tắc domain đúng.

## 24. DTO, JSON và API: đừng truyền identity bằng tham chiếu Java

Khi entity được serialize ra JSON rồi đọc lại ở service khác, object Java mới được tạo ra, không còn cùng reference ban đầu:

~~~json
{
  "id": 42,
  "email": "lan@example.com",
  "displayName": "Lan"
}
~~~

Một DTO từ request có `id = 42` không tự trở thành managed entity, cũng không chắc database còn có row #42. Tầng service cần xác thực quyền, tải entity theo ID trong transaction, rồi áp dụng thay đổi:

~~~java
@Transactional
public void renameCustomer(long id, String newName) {
    Customer managed = entityManager.find(Customer.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Customer not found");
    }
    managed.rename(newName);
}
~~~

Ví dụ `@Transactional` ở đây giả định Spring/Jakarta transaction infrastructure phù hợp. Hibernate dirty checking theo dõi entity managed và flush cập nhật theo transaction. Không đặt niềm tin vào việc DTO `equals` với một entity hay JSON chứa ID để bỏ qua việc load/authorize.

### DTO value equality không phải entity equality

~~~java
public record CustomerView(
    Long id, String email, String displayName
) {}
~~~

Hai `CustomerView` records equal nếu các component equal theo semantics Java record, kể cả chúng được tạo từ hai entity sessions khác nhau. Đó là **snapshot/value equality của DTO**, không phải bằng chứng database đang ở cùng state hay user có quyền thay đổi entity.

Nếu dùng DTO để phát hiện thay đổi giữa hai phiên bản, có thể so bản snapshot giá trị. Nếu cần tham chiếu business object trong database, dùng ID hoặc business key theo quy tắc service.

## 25. Những tình huống thực tế hay bị nhầm

### 25.1. “Hai lần đọc cùng row nhưng `==` là false”

Kiểm tra xem hai lời gọi có cùng `Session`/`EntityManager` và cùng persistence context hay không. Hai transactions/context khác nhau có thể tạo hai Java instances riêng. `==` false không chứng minh hai entity khác persistence identity.

### 25.2. “`equals()` true nhưng DB có hai row”

Có thể equality đang so display name hoặc một business value không unique. Kiểm tra `@Id` của hai entity, schema unique constraints và phạm vi tenant. `equals()` ở Java không tự thực thi uniqueness trong DB.

### 25.3. “Hai entity mới equal dù chưa persist”

Nếu equality theo `id` và cả hai `id = null`, có thể implementation bỏ qua kiểm tra null. Với generated-ID equality, phải yêu cầu non-null ID hoặc dùng business key bất biến được cấp trước.

### 25.4. “Entity biến mất khỏi `HashSet` sau persist”

Hash code phụ thuộc ID generated đã thay đổi khi entity được cấp khóa. Dùng stable hash code, immutable business key hoặc thay cấu trúc dữ liệu nếu không cần entity equality trong Set.

### 25.5. “`getClass()` khác nhau dù hai object biểu diễn cùng row”

Một object có thể là Hibernate proxy subclass. Kiểm tra proxy metadata và class semantics của Hibernate version. Không chỉ dùng raw `getClass()` để so persistent identity nếu project có lazy proxies.

### 25.6. “`merge()` xong sửa object cũ nhưng DB không đổi”

`merge()` trả về managed instance; object được truyền vào vẫn detached. Hãy làm việc với object trả về, trong transaction phù hợp.

### 25.7. “Hai session nhìn cùng ID nhưng field khác nhau”

Cùng persistence identity nhưng snapshot/load time khác nhau. Kiểm tra transaction isolation, stale context, first/second-level cache, optimistic locking và refresh, không viết equality so tất cả field để quyết định “khác customer”.

### 25.8. “Email unique nên chắc chắn dùng email làm equals được”

Chưa chắc. Email có thể đổi, có normalization/collation phức tạp hoặc uniqueness chỉ tồn tại theo tenant. Xác định tính **ổn định và phạm vi** trước khi dùng làm hash key.

### 25.9. “`@Version` khác nhau nghĩa là hai entity khác nhau”

Sai. Version biểu thị thế hệ state để kiểm soát optimistic concurrency. Một entity có cùng ID qua nhiều version vẫn là cùng persistence identity.

### 25.10. “Second-level cache khiến hai Session dùng chung một Java object”

Không. Cache cấp hai giúp tái sử dụng dữ liệu giữa session, nhưng first-level identity map vẫn gắn với từng persistence context và không mặc định chia sẻ managed instance.

## 26. Các thí nghiệm để quan sát ba kiểu danh tính

Thực hành trên một database thử nghiệm với mapping `Customer` như phần đầu. Ở từng thí nghiệm, giữ rõ scope transaction/session và xem kết quả `==`, `equals()`, `getId()` và trạng thái managed.

### Thí nghiệm A — Java reference equality trước khi persist

~~~java
Customer a = new Customer("a@example.com", "Same Name");
Customer b = a;
Customer c = new Customer("c@example.com", "Same Name");

System.out.println(a == b); // true
System.out.println(a == c); // false
System.out.println(
    a.getDisplayName().equals(c.getDisplayName())
); // true
~~~

Không cần Hibernate để giải thích kết quả: hai biến trỏ một object, trong khi hai object khác nhau có thể chứa cùng một giá trị mô tả.

### Thí nghiệm B — Identity map trong một persistence context

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

Customer a = entityManager.find(Customer.class, 42L);
Customer b = entityManager.find(Customer.class, 42L);

System.out.println(a == b); // thường true nếu row #42 tồn tại
System.out.println(entityManager.contains(a)); // true

tx.commit();
~~~

Quan sát log `SELECT`: lần tìm thứ hai thường được thỏa mãn từ persistence context. Kết quả thực tế cần phân biệt trường hợp `find` trả null do row không tồn tại.

### Thí nghiệm C — Detach, load lại và merge

~~~java
tx.begin();
Customer original = entityManager.find(Customer.class, 42L);
entityManager.detach(original);

Customer managed = entityManager.find(Customer.class, 42L);

System.out.println(original == managed); // thường false
System.out.println(
    original.getId().equals(managed.getId())
); // true
System.out.println(entityManager.contains(original)); // false
System.out.println(entityManager.contains(managed));  // true

Customer mergeResult = entityManager.merge(original);
System.out.println(mergeResult == managed); // thường true
tx.commit();
~~~

Khi context đã có managed `Customer#42`, Hibernate thường sao chép state detached vào instance đó ở merge. Không coi merge là phương thức biến `original` thành managed.

### Thí nghiệm D — Hai Customer có cùng display name

~~~java
tx.begin();
Customer a = new Customer("a1@example.com", "Lan");
Customer b = new Customer("b1@example.com", "Lan");

entityManager.persist(a);
entityManager.persist(b);
tx.commit();

System.out.println(a.getId().equals(b.getId())); // false nếu DB cấp ID riêng
System.out.println(
    a.getDisplayName().equals(b.getDisplayName())
); // true
~~~

Kết quả làm rõ hai row khác persistence identity nhưng cùng một business field.

### Thí nghiệm E — ID generated và HashSet

Tạo một bản class thử nghiệm có `equals/hashCode` theo ID nhưng `hashCode()` trả hash của ID trực tiếp; thêm entity transient vào `HashSet`, persist, rồi gọi `contains()`. Lặp lại với hash code ổn định. Mục tiêu quan sát **hash code đổi trong vòng đời object** chứ không kiểm tra đặc tính SQL.

### Thí nghiệm F — Proxy

~~~java
tx.begin();
Customer proxy = entityManager.getReference(Customer.class, 42L);
Customer loaded = entityManager.find(Customer.class, 42L);

System.out.println(proxy.getClass().getName());
System.out.println(loaded.getClass().getName());
System.out.println(proxy.getId());
tx.commit();
~~~

Kiểm tra Hibernate tạo proxy hay bytecode-enhanced object trên cấu hình thực tế. Không gọi method truy cập lazy sau khi session đóng nếu chưa initialize; `getReference()` cũng có thể trì hoãn lỗi “row không tồn tại” đến lúc proxy bị truy cập.

## 27. Cách chọn quy tắc equality cho một entity mới

Trước khi override `equals()/hashCode()`, trả lời:

1. **Entity có được truyền qua nhiều session/transaction không?** Nếu không, reference identity mặc định có thể đã đủ.
2. **Ứng dụng có cần de-dup các detached/managed copies của cùng row không?** Nếu có, equality dựa trên persistence ID có thể phù hợp.
3. **ID được cấp khi nào?** Với generated ID, tránh hash code thay đổi sau persist và tránh coi hai null IDs bằng nhau.
4. **Có natural key bất biến, duy nhất và được gán ngay khi tạo không?** Nếu có, business-key equality có thể hữu ích; kiểm tra normalization/tenant scope.
5. **Entity có inheritance hoặc Hibernate lazy proxies không?** Cần quy tắc type comparison nhất quán và hiểu hành vi proxy.
6. **Entity có mutable associations/collections không?** Không đưa các field này vào equality một cách máy móc; tránh lazy loading/đệ quy.
7. **Có yêu cầu dùng entity làm key trong HashMap/Set không?** Nếu có, equality/hash stability trở thành yêu cầu thiết kế trực tiếp.
8. **Khóa có scoped theo tenant hoặc composite key không?** So đủ thành phần identifier/scope.

### Ma trận lựa chọn

| Bối cảnh | Lựa chọn cân nhắc | Điểm cần bảo vệ |
|---|---|---|
| Entity chỉ dùng bên trong một persistence context | Giữ `Object.equals/hashCode` mặc định | Không dùng `==` khi đối chiếu qua contexts. |
| Generated ID, phải so detached và managed cùng row | ID-based equals, non-null ID, stable hash | Proxy/type, transient entities, hash collisions. |
| Entity có immutable natural key được cấp ngay từ đầu | Business-key equals/hash | Unique DB, normalization, immutability và scope. |
| Mutable natural key (email có thể đổi) | Thường không dùng trực tiếp làm hash equality key | Chọn generated ID hoặc tham chiếu theo ID khi cần. |
| Value object/embeddable | Value-based equals/hash | Tất cả component có semantics và scale/normalization đúng. |
| Multi-tenant/composite identity | Equality xét đầy đủ identifier và tenant scope | Không nhầm cùng local ID ở các tenants. |
| Hierarchy nhiều subtype/proxy | Thiết kế equality ở cấp hierarchy nhất quán | Symmetry/transitivity, concrete class và proxy. |

Không có một công thức `equals()/hashCode()` tối ưu cho mọi entity Hibernate. Một quyết định tốt là quyết định **phù hợp với semantics domain, lifecycle và cách object được dùng trong collections**, đồng thời không làm mơ hồ persistence identity.

## 28. Mô hình tư duy cuối cùng

~~~mermaid
flowchart TD
    A["Có hai biến Java: a, b"] --> B{"a == b ?"}
    B -- "Có" --> C["Cùng Java instance"]
    B -- "Không" --> D["Hai Java references/instances khác nhau"]
    C --> E["Xét persistence identity nếu entity đã được nhận diện"]
    D --> E
    E --> F{"Cùng mapped entity identity và scope?"}
    F -- "Có" --> G["Có thể là hai bản thể hiện cùng DB row qua contexts"]
    F -- "Không / chưa có ID" --> H["Khác persistent identity hoặc chưa xác định"]
    G --> I["Xét giá trị nghiệp vụ theo domain key/fields"]
    H --> I
    I --> J{"Cùng business value?"}
    J -- "Có" --> K["Bằng theo tiêu chí nghiệp vụ đang xét"]
    J -- "Không" --> L["Giá trị nghiệp vụ khác"]
~~~

Ba tầng câu hỏi có **phạm vi khác nhau**:

**Cùng tham chiếu Java** trả lời: “Hai biến có trỏ đúng một object trong JVM không?” Cách kiểm tra là `==`.

**Cùng định danh lưu trữ** trả lời: “Hai biểu diễn entity có được ORM/database nhận diện bằng cùng entity key không?” Cách kiểm tra thường dựa trên mapped identifier và đúng entity/tenant scope, đặc biệt khi đi qua nhiều persistence contexts.

**Cùng giá trị nghiệp vụ** trả lời: “Các thuộc tính mà domain quan tâm có bằng nhau theo quy tắc nghiệp vụ không?” Cách kiểm tra cần được định nghĩa rõ, có thể không trùng với Java reference hay database identity.

Khi phát triển với Hibernate, hãy **chọn rõ tầng danh tính đang cần** trước khi so entity. Dùng identity map để hiểu đối tượng managed trong một `Session`, dùng `@Id` và database constraints để nhận diện bản ghi, dùng business key/DTO/value object để biểu diễn equality theo domain, và chỉ override `equals()/hashCode()` khi có một quy tắc nhất quán từ transient đến managed, detached và proxy. Như vậy, một phép so sánh đơn giản không vô tình trở thành lỗi dữ liệu, lỗi collection hoặc bug chỉ xuất hiện khi entity đi qua hai transaction khác nhau.
