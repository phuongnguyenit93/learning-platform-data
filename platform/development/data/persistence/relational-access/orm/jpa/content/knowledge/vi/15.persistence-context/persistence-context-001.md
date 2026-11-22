# Định danh duy nhất của entity trong cùng ngữ cảnh lưu trữ

Một điểm khác biệt quan trọng giữa **JPA (Jakarta Persistence)** và thao tác JDBC thuần là JPA không chỉ chuyển một hàng trong database thành một đối tượng Java rồi trả về. JPA còn quản lý **identity** (định danh) và **trạng thái** của các entity trong một **persistence context** (ngữ cảnh lưu trữ).

Giả sử ứng dụng thực hiện hai lần:

```java
Customer first = entityManager.find(Customer.class, 42L);
Customer second = entityManager.find(Customer.class, 42L);
```

Nếu cùng một `EntityManager` với persistence context đang hoạt động và hàng tương ứng tồn tại, JPA duy trì quy tắc cốt lõi: **cùng một định danh entity trong cùng persistence context tương ứng với một managed entity instance duy nhất**. Vì vậy, khi cả hai lời gọi trả về entity đó, ta có thể kỳ vọng:

```java
first == second // true
```

Điều này không đồng nghĩa toàn bộ ứng dụng có một `Customer` duy nhất cho ID 42. Khi sử dụng persistence context khác, ta có thể nhận một Java object khác, dù cả hai object biểu diễn **cùng một hàng database**.

Bài học phân tích chính xác phạm vi của tính duy nhất này, liên hệ với `find()`, JPQL, entity reference/proxy, `persist()`, `merge()`, `detach()`, `clear()` và các mô hình quản lý transaction. Hiểu nguyên tắc này giúp tránh lỗi mất cập nhật, đồng nhất sai các instance và sử dụng entity detached như thể chúng vẫn đang managed.

## 1. Ba loại “đồng nhất” cần phân biệt

Khi nói hai entity “giống nhau”, ta cần xác định đang so sánh khía cạnh gì.

### 1.1. Đồng nhất tham chiếu Java

```java
a == b
```

Biểu thức này kiểm tra liệu `a` và `b` có tham chiếu tới **cùng một object trong JVM** hay không.

Ví dụ:

```java
Customer a = new Customer("Nguyễn An");
Customer b = a;

System.out.println(a == b); // true
```

Nếu tạo object mới:

```java
Customer c = new Customer("Nguyễn An");
System.out.println(a == c); // false
```

Dù dữ liệu hiển thị giống nhau, chúng vẫn là hai object Java.

### 1.2. Đồng nhất định danh persistent entity

Một entity JPA có khóa chính được ánh xạ bằng `@Id`, `@EmbeddedId` hoặc `@IdClass`. Ví dụ:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    // ...
}
```

Hai object `Customer` có cùng primary key có thể đại diện cho **cùng entity identity ở tầng persistence**, ngay cả khi chúng là hai Java object khác nhau được tải từ hai persistence context.

Ở mức ý tưởng, định danh persistent phụ thuộc vào **loại entity và giá trị khóa chính** trong phạm vi persistence unit và dữ liệu mà nó quản lý; không được suy rằng số `42` tự nó đủ phân biệt mọi entity. `Customer #42` và `Order #42` là hai entity identity khác nhau.

### 1.3. Bình đẳng theo `equals()`

```java
a.equals(b)
```

Kết quả tùy cách class định nghĩa `equals()`.

- Nếu không override `equals()`, behavior kế thừa từ `Object` thường tương đương đồng nhất tham chiếu.
- Nếu override theo khóa chính, hai instance khác tham chiếu có thể được coi là bằng nhau.
- Nếu override theo business key, sự bằng nhau còn có thể phụ thuộc quy tắc nghiệp vụ, kể cả trước khi có database ID.

**JPA quản lý tính duy nhất của managed instance theo entity identity; JPA không tự quy định rằng mọi class entity phải dùng một cách viết `equals()/hashCode()` duy nhất.**

| Phép kiểm tra | Câu hỏi được trả lời | Phạm vi |
| --- | --- | --- |
| `a == b` | Có cùng object Java không? | Trong JVM |
| Hai identity persistent có khớp? | Có cùng loại entity và cùng primary key không? | Theo mapping/persistence unit |
| `a.equals(b)` | Class cho rằng hai object bằng nhau không? | Do implementation `equals()` |
| Hai hàng có cùng dữ liệu? | Các cột đang có giá trị giống nhau không? | Dữ liệu quan hệ tại thời điểm xét |

Trộn lẫn bốn điều này là nguồn gốc của nhiều lỗi khi làm việc với entity JPA.

## 2. Persistence context thực chất quản lý gì?

**Persistence context** là tập các entity instance được JPA provider quản lý cùng với identity và state tương ứng. Có thể hình dung nó như một bảng tra cứu identity trong bộ nhớ, thường gọi là **identity map** hoặc **first-level cache**.

Sơ đồ khái niệm:

```text
                 EntityManager
                      │
                      ▼
               Persistence Context
        ┌──────────────────────────────────┐
        │  (Customer, ID=42) → object A     │
        │  (Customer, ID=73) → object B     │
        │  (Order,    ID=42) → object C     │
        └──────────────────────────────────┘
                   │         ▲
                   │ SQL     │ dữ liệu hàng
                   ▼         │
                 Database
```

Trong cùng context:

- Tra `Customer #42` trả về **managed instance A** nếu nó đang được quản lý.
- Tra lại `Customer #42` không tạo một **managed Customer instance thứ hai** đại diện cùng identity.
- `Customer #73` là identity khác, nên được biểu diễn bởi instance B.
- `Order #42` cũng là identity khác với `Customer #42`, nên được biểu diễn bởi instance C.

Đây là **mô hình tư duy**, không phải yêu cầu provider phải cài đặt đúng một `HashMap` hoặc một cấu trúc dữ liệu cụ thể. Provider có thể dùng nhiều cấu trúc nội bộ để quản lý state, proxies, snapshots và dirty checking.

### Tại sao tính duy nhất quan trọng?

Nếu trong một context có hai managed object khác nhau cùng đại diện `Customer #42`:

```text
Customer A: id=42, name="Nguyễn An"
Customer B: id=42, name="Trần Bình"
```

thì khi flush, provider sẽ phải giải quyết hai phiên bản state mâu thuẫn của cùng một identity. Quy tắc **một managed instance cho một identity** tránh việc provider phải tự suy đoán object nào mới là đại diện đúng trong phạm vi context.

Đặc điểm này hỗ trợ:

1. **Tính nhất quán tham chiếu trong bộ nhớ:** các đường truy cập cùng entity identity gặp lại cùng managed instance.
2. **Dirty checking:** provider theo dõi một đại diện được quản lý của entity và phát hiện thay đổi ở state.
3. **Quan hệ giữa entity:** nhiều association có thể tham chiếu cùng một object managed.
4. **Tránh tạo lại object không cần thiết:** nếu entity đã managed, query có thể dùng instance đang tồn tại.

Nó **không** tự thay thế transaction isolation, optimistic locking hoặc cơ chế đồng bộ giữa các tiến trình.

## 3. Một entity minh họa xuyên suốt

Ví dụ `Customer`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Version
    private long version;

    protected Customer() {
        // JPA khởi tạo entity khi cần.
    }

    public Customer(String fullName) {
        rename(fullName);
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("fullName");
        }
        this.fullName = newName.trim();
    }
}
```

Ở đây:

- `id` xác định persistent identity trong database.
- `version` hỗ trợ optimistic locking đối với các thay đổi có versioning phù hợp.
- `fullName` là state nghiệp vụ được ánh xạ.
- No-args constructor `protected` cho phép JPA provider khởi tạo entity theo hợp đồng thông thường của chuẩn.
- Constructor nghiệp vụ kiểm tra dữ liệu khi ứng dụng tạo Customer mới.

`@Version` được giới thiệu để minh họa rằng **identity trong persistence context và khả năng phát hiện cập nhật đồng thời là hai cơ chế khác nhau**. Có thể hiểu ví dụ định danh ngay cả khi một entity không dùng versioning.

## 4. `find()` hai lần trong cùng context: cùng instance

Một ví dụ resource-local đơn giản:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    Customer first = em.find(Customer.class, 42L);
    Customer second = em.find(Customer.class, 42L);

    if (first != null) {
        System.out.println(first == second); // true
        System.out.println(em.contains(first)); // true
    }
} finally {
    em.close();
}
```

Giả sử hàng `customers.id = 42` tồn tại và cả hai lời gọi dùng cùng persistence context:

- Lần đầu provider có thể truy vấn DB hoặc dùng cache để lấy state, sau đó quản lý instance.
- Lần thứ hai entity cùng identity đã managed, nên provider trả lại instance đó.
- Hai biến Java trỏ đến cùng object.

Điều cần nhớ:

**Bảo đảm quan trọng là tính duy nhất của instance managed, không phải một con số cố định về số câu SQL.**

Lần đầu `find()` có thể cần SQL, có thể tận dụng cache cấp hai, hoặc có trạng thái đã được nạp bởi thao tác khác. Ngoài ra, cơ chế provider có thể phải làm việc với proxies hoặc thông tin lifecycle riêng. Vì thế, không thể đếm chắc chắn số query chỉ từ hai lệnh Java mà không xét bối cảnh.

### Nếu ID không tồn tại?

```java
Customer missing = em.find(Customer.class, 999999L);
// Thông thường trả về null nếu không tìm thấy entity.
```

Khi `find()` trả về `null`, không có managed Customer instance tương ứng để so sánh identity. Đừng diễn giải `null == null` thành một chứng minh về identity map.

### Nếu một instance đã được quản lý từ trước?

```java
Customer customer = em.find(Customer.class, 42L);

Customer again = em.find(Customer.class, 42L);
// again là cùng managed instance với customer.
```

Điều này vẫn đúng dù trước đó entity được tải qua JPQL, association hoặc thao tác JPA khác trong cùng context, miễn là kết quả biểu diễn cùng persistent identity.

## 5. `find()` và JPQL có cùng identity map không?

Có. Persistence context không phải một cache riêng cho từng loại truy vấn. Một entity `Customer #42` được trả về từ các truy vấn khác nhau trong cùng context vẫn là **cùng managed instance**.

Ví dụ:

```java
Customer first = em.find(Customer.class, 42L);

Customer second = em.createQuery(
    "SELECT c FROM Customer c WHERE c.id = :id",
    Customer.class
).setParameter("id", 42L)
 .getSingleResult();

System.out.println(first == second); // true
```

Giả sử entity tồn tại, cùng `EntityManager` và context chưa bị clear/detach, cả hai lối truy vấn tương ứng một identity.

Điều tương tự có thể xảy ra khi cùng entity được gặp lại qua các association:

```java
Order order1 = em.find(Order.class, 101L);
Order order2 = em.find(Order.class, 102L);

Customer customer1 = order1.getCustomer();
Customer customer2 = order2.getCustomer();
```

Nếu cả hai Order tham chiếu `Customer #42` trong cùng context, persistence context quản lý một Customer identity tương ứng. Provider có thể dùng reference/proxy tùy chiến lược lazy loading, nhưng không nên hình dung mỗi đường điều hướng tự tạo một managed entity độc lập cho cùng hàng.

### Kết quả JPQL có thể chứa tham chiếu lặp

Giả sử một Customer có ba Order. JPQL:

```java
List<Customer> results = em.createQuery(
    "SELECT c FROM Customer c JOIN c.orders o " +
    "WHERE c.id = :id",
    Customer.class
).setParameter("id", 42L)
 .getResultList();
```

Tùy ngữ nghĩa truy vấn và phiên bản provider, kết quả có thể phản ánh nhiều hàng join cho cùng root Customer nếu không sử dụng xử lý loại trùng thích hợp. **Tính duy nhất của managed instance không có nghĩa một `List` kết quả luôn chứa mỗi entity đúng một lần.**

Ta cần phân biệt:

- **Unique managed instance:** cùng identity → một Java object managed trong context.
- **Unique list element:** query result có thể có lặp các tham chiếu tới object đó khi phép JOIN tạo nhiều kết quả.

Khi cần loại trùng kết quả theo entity, có thể dùng JPQL `DISTINCT`:

```java
List<Customer> customers = em.createQuery(
    "SELECT DISTINCT c FROM Customer c JOIN c.orders o",
    Customer.class
).getResultList();
```

Cách provider tạo SQL hoặc xử lý DISTINCT có thể khác nhau, nhưng ý định ở mức JPQL là loại các kết quả trùng tương ứng.

## 6. Tính duy nhất giúp dirty checking như thế nào?

Giả sử:

```java
em.getTransaction().begin();

Customer first = em.find(Customer.class, 42L);
Customer second = em.find(Customer.class, 42L);

first.rename("Nguyễn An Mới");

System.out.println(second.getFullName());
// Nguyễn An Mới, vì first và second là cùng object managed.

em.getTransaction().commit();
```

Hai biến trỏ đến cùng object. Khi method `rename()` sửa `fullName`, đọc lại qua `second` sẽ thấy thay đổi trong bộ nhớ mà không cần một bước đồng bộ hai object.

Đến lúc flush/commit, provider có thể phát hiện state persistent bị thay đổi và tạo `UPDATE` tương ứng:

```sql
UPDATE customers
SET full_name = ?, version = ?
WHERE id = ? AND version = ?;
```

SQL là minh họa cho optimistic locking; cấu trúc thực tế phụ thuộc provider, dialect, mapping và những cột được cập nhật.

### Một identity map không phải cơ chế chống ghi đè xuyên transaction

Nếu hai context khác nhau đồng thời quản lý `Customer #42`, mỗi context có bản state riêng. Một context đổi tên thành A, context khác đổi tên thành B. Việc mỗi context chỉ giữ một instance không giải quyết xung đột liên context.

Đó là lý do các ứng dụng cần:

- Transaction phù hợp.
- Mức isolation và ràng buộc DB theo nghiệp vụ.
- `@Version` nếu cần optimistic locking.
- Hoặc pessimistic lock khi thao tác phải được tuần tự hóa.

**Identity map giải quyết tính đồng nhất trong một context; concurrency control giải quyết sự tương tác giữa các context/transaction.**

## 7. Hai `EntityManager`: cùng hàng DB, có thể khác object Java

Ví dụ:

```java
EntityManager em1 = entityManagerFactory.createEntityManager();
EntityManager em2 = entityManagerFactory.createEntityManager();

try {
    Customer c1 = em1.find(Customer.class, 42L);
    Customer c2 = em2.find(Customer.class, 42L);

    // Hai context độc lập có thể tạo hai Java object khác nhau.
    System.out.println(c1 == c2); // thông thường false nếu đều tồn tại

    System.out.println(em1.contains(c1)); // true
    System.out.println(em2.contains(c2)); // true
    System.out.println(em1.contains(c2)); // false
} finally {
    em1.close();
    em2.close();
}
```

`c1` và `c2` có cùng persistent identity là `Customer #42` nhưng thuộc hai persistence context khác nhau. Chúng không bị ràng buộc phải là cùng tham chiếu Java.

Sơ đồ:

```text
EntityManager em1                   EntityManager em2
     │                                   │
     ▼                                   ▼
Persistence Context 1              Persistence Context 2
(Customer,42) → object A           (Customer,42) → object B
     │                                   │
     └──────────┬────────────────────────┘
                ▼
       customers.id = 42 (DB)
```

**Bảo đảm một instance duy nhất không phải singleton toàn ứng dụng.** Nó áp dụng trong từng persistence context.

### Không chia sẻ EntityManager tùy tiện giữa các luồng

`EntityManager` và persistence context thông thường không được thiết kế để truy cập đồng thời như một tài nguyên thread-safe do ứng dụng tự chia sẻ. Không nên đặt một `EntityManager` do ứng dụng tạo trong static field rồi dùng cho tất cả HTTP request.

Hệ thống thường quản lý `EntityManager` theo request, transaction hoặc cơ chế container/framework phù hợp. Với Spring và Jakarta EE, tham chiếu được inject có thể là proxy/handle và quy tắc context cụ thể do môi trường cung cấp; cần phân biệt điều đó với việc tự chia sẻ một instance `EntityManager` thực.

## 8. Persistence context khác transaction như thế nào?

Một nhầm lẫn phổ biến là coi **mỗi transaction luôn tương đương một persistence context**. Hai khái niệm có liên quan nhưng không hoàn toàn đồng nhất.

- **Persistence context**: phạm vi quản lý identity và state của entity.
- **Transaction**: phạm vi xử lý thao tác cần tính nguyên tử, nhất quán theo quy tắc JPA/database.

Trong ứng dụng Jakarta EE thường gặp **transaction-scoped persistence context**. Một context gắn với transaction; trong transaction đó các thao tác JPA được điều phối để cùng quản lý entity.

Có cả **extended persistence context**, đặc biệt trong các component có state và các luồng nghiệp vụ kéo dài. Context này có thể tồn tại qua nhiều transaction, nhưng vẫn phải tuân thủ những quy tắc về synchronization/lifecycle và không nên được hiểu là cache tùy ý toàn hệ thống.

Với `EntityManager` dạng application-managed, vòng đời context phụ thuộc cách tạo/đóng `EntityManager` và kiểu synchronization/transaction tương ứng. Vì vậy, quy tắc an toàn khi phân tích identity là:

> Hãy hỏi **“Hai thao tác có dùng cùng persistence context đang quản lý entity không?”**, thay vì chỉ hỏi **“Chúng có cùng tên transaction hay cùng method Java không?”**.

### Trong ứng dụng Spring Data JPA

Một method Spring có `@Transactional` thường hoạt động với một `EntityManager`/persistence context được liên kết với transaction theo cấu hình framework. Hai repository call cùng transaction có thể cùng nhận managed instance cho một ID.

Ngược lại, hai lần gọi repository không được bao bọc bởi một transaction chung **không nên mặc định có cùng persistence context** chỉ vì chúng nằm trong cùng service method hoặc cùng HTTP request. Cần xem transaction boundaries, cách `EntityManager` được quản lý và cấu hình như Open EntityManager in View nếu có.

Chi tiết lifecycle thuộc framework/container; JPA specification đặt ra quy tắc về context và entity identity bên trong phạm vi đó.

## 9. `getReference()` có phá vỡ tính duy nhất không?

JPA cung cấp:

```java
Customer reference = em.getReference(Customer.class, 42L);
```

Mục đích thường là lấy một **tham chiếu tới entity identity** mà chưa nhất thiết phải tải ngay toàn bộ state persistent. Provider có thể sử dụng proxy hoặc kỹ thuật khác; lúc nào SQL xảy ra và hành vi với ID không tồn tại tùy hợp đồng và implementation.

Ví dụ:

```java
Customer ref = em.getReference(Customer.class, 42L);
Customer loaded = em.find(Customer.class, 42L);
```

Trong cùng context, JPA vẫn duy trì nguyên tắc một managed entity instance cho cùng identity; nhưng **không nên suy diễn chi tiết kỹ thuật như “getReference luôn tạo một proxy mới” hoặc “find luôn phát SQL”**.

Điều cần chú ý:

- `getReference()` có thể không xác thực ngay hàng có thật ở DB.
- Truy cập state của reference có thể kích hoạt load.
- Nếu ID không tồn tại, provider có thể ném `EntityNotFoundException` khi truy cập.
- Proxy có thể là subtype hoặc cơ chế wrapper phù hợp provider; `getClass()`, reflection và cách `equals()` dựa vào runtime class cần được thiết kế thận trọng.
- Tính duy nhất của **managed entity identity** không phải cam kết tất cả thư viện/proxy đều dùng cùng class runtime.

### Vì sao `getReference()` hữu ích?

Giả sử cần liên kết `Order` mới tới một `Customer` đã tồn tại:

```java
Customer customerRef =
    em.getReference(Customer.class, existingCustomerId);

Order order = new Order(customerRef);
em.persist(order);
```

Nếu không cần đọc tên, email của customer, có thể không cần tải toàn bộ Customer chỉ để đặt khóa ngoại. Tuy nhiên, nếu ID sai, transaction có thể lỗi do foreign key hoặc khi dereference. `getReference()` **không phải thay thế cho một bước xác minh ID tồn tại** khi nghiệp vụ yêu cầu thông báo lỗi rõ ràng.

## 10. Một entity new/transient không tự trở thành managed

Ví dụ:

```java
Customer a = new Customer("Nguyễn An");
Customer b = new Customer("Nguyễn An");

System.out.println(a == b); // false
```

Cả hai là Java object **new/transient**, chưa có persistent identity được JPA quản lý. Không thể áp dụng quy tắc “một managed instance duy nhất” để kết luận chúng là cùng khách hàng chỉ vì tên giống nhau.

Khi:

```java
em.getTransaction().begin();

Customer a = new Customer("Nguyễn An");
em.persist(a);

System.out.println(em.contains(a)); // true

em.getTransaction().commit();
```

`a` trở thành managed trong context thích hợp, và JPA phối hợp lưu entity, sinh khóa theo strategy đã khai báo.

### Hai object mới trùng natural key không phải tự hợp nhất

Giả sử hai `Customer` có email trùng nhau. Dù email được coi là unique business key, JPA không tự gộp hai object new chỉ vì nội dung field giống nhau. Cần validation và unique constraint ở DB để quyết định có cho phép hai hàng cùng email không.

**Business key** như email, số điện thoại hoặc mã tài khoản không mặc nhiên là **primary key** dùng trong persistence context. Nếu domain dùng khóa nghiệp vụ làm `@Id`, quy tắc identity sẽ dựa trên mapping đó; nếu không, nó là một trường thông thường với ràng buộc riêng.

## 11. Entity identity và khóa chính phải ổn định

Với entity có `@Id`:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

`id` là thành phần cốt lõi của identity persistent. Sau khi entity đã persistent, không nên tự thay primary key của một managed entity.

Ví dụ một API thiết kế rủi ro:

```java
public void setId(Long newId) {
    this.id = newId;
}
```

Nếu `Customer #42` đã được quản lý trong identity map, code tự đổi `id` thành `73` sẽ khiến state của object không còn phù hợp identity mà context đang theo dõi. JPA không định nghĩa đây là cách chuẩn để “di chuyển” một entity sang hàng khác; nó có thể gây lỗi khi flush hoặc kết quả không được hỗ trợ.

**Hướng thiết kế:** không công khai setter tùy ý cho primary key được sinh ra; ID nên do provider/DB xử lý theo strategy đã chọn. Nếu nghiệp vụ thực sự cần mã có thể thay đổi, hãy đặt mã đó ở một thuộc tính khác, đừng biến nó thành primary key bất ổn.

### Khóa tổng hợp cũng là identity

Entity có khóa tổng hợp:

```java
@EmbeddedId
private EnrollmentId id;
```

hoặc `@IdClass` vẫn tuân thủ nguyên tắc một instance managed cho một persistent identity. Trong trường hợp này, identity gồm **tập thành phần khóa** theo mapping, không phải một `Long` đơn lẻ.

Value type làm composite key cần implement `equals()/hashCode()` nhất quán với giá trị khóa và có cấu trúc theo yêu cầu JPA. Không nên thay đổi nội dung của một embedded ID đang đại diện cho identity của managed entity.

## 12. `detach()`: một identity không còn được context quản lý

Giả sử:

```java
Customer first = em.find(Customer.class, 42L);

System.out.println(em.contains(first)); // true

em.detach(first);

System.out.println(em.contains(first)); // false
```

Sau `detach(first)`, object `first` vẫn tồn tại trong bộ nhớ, còn có `id` và các field đã được tải. Nhưng nó **không còn managed** bởi context đó.

Nếu context sau đó cần tải `Customer #42`:

```java
Customer second = em.find(Customer.class, 42L);
```

provider có thể tạo một managed instance khác cho identity đó, bởi object `first` đã bị detach.

Sơ đồ:

```text
Trước detach:
Persistence Context
  (Customer,42) ───► first (managed)

Sau detach:
Persistence Context
  không còn quản lý first
first (detached) vẫn tồn tại trong JVM

Sau find:
Persistence Context
  (Customer,42) ───► second (managed)

first và second có thể cùng ID nhưng khác tham chiếu Java.
```

Đây không vi phạm quy tắc identity: tại một thời điểm, context chỉ có **một managed instance** cho identity đó; object cũ đã detached.

### Thay đổi object detached có được ghi tự động không?

Không. Ví dụ:

```java
em.detach(first);
first.rename("Tên mới");

// Không còn dirty checking đối với first trong context này.
```

Việc sửa field trên detached object không tự được context cũ flush xuống DB. Cần một thao tác nghiệp vụ rõ ràng, như tải entity managed rồi áp dụng thay đổi, hoặc sử dụng `merge` phù hợp.

Với association và cascade, `detach` cũng có quy tắc lan truyền khi mapping dùng `CascadeType.DETACH` hoặc `CascadeType.ALL`. Điều này cần được hiểu khi thao tác trên object graph, nhưng không thay đổi định nghĩa cốt lõi của managed identity.

## 13. `clear()`: làm rỗng persistence context

`EntityManager.clear()` tách **tất cả** managed entity khỏi context:

```java
Customer a = em.find(Customer.class, 42L);
Customer b = em.find(Customer.class, 73L);

em.clear();

System.out.println(em.contains(a)); // false
System.out.println(em.contains(b)); // false
```

Nếu sau đó `find(Customer.class, 42L)`:

```java
Customer newlyManaged = em.find(Customer.class, 42L);
```

thì provider có thể tạo managed instance mới đại diện `Customer #42`. `a` vẫn là object detached trong JVM, nhưng không còn là managed representative.

### `clear()` không xóa hàng khỏi database

`clear()` **không phải** `DELETE` và cũng không phải `ROLLBACK`. Nó làm các object mất liên kết với context.

Nguy cơ quan trọng: những thay đổi chưa được flush trên managed entity có thể không được đồng bộ khi `clear()` tách chúng ra.

Ví dụ:

```java
em.getTransaction().begin();

Customer customer = em.find(Customer.class, 42L);
customer.rename("Tên sẽ bị bỏ qua");

em.clear();

// Vì đã clear trước khi flush, không nên kỳ vọng thay đổi
// vừa thực hiện vẫn được context đồng bộ khi commit.

em.getTransaction().commit();
```

Nếu muốn bảo đảm các thay đổi pending được gửi tới DB trước khi clear, cần `flush()` phù hợp khi transaction đang hoạt động và còn hợp lệ:

```java
em.flush();
em.clear();
```

Nhưng `flush()` chưa đồng nghĩa transaction đã commit. Nếu transaction sau đó rollback, thay đổi đã flush vẫn có thể bị hủy theo semantics của DB.

### Khi nào cần `clear()`?

Trong batch processing với nhiều entity, context có thể giữ rất nhiều object và snapshot. Một kỹ thuật thường dùng là xử lý theo lô:

```java
for (int i = 0; i < items.size(); i++) {
    em.persist(items.get(i));

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}
```

Sau mỗi lần clear, các object trước đó trở thành detached. Đây là biện pháp quản lý bộ nhớ có chủ đích, nhưng phải tránh sử dụng lại chúng như managed entity trong các bước tiếp theo.

## 14. `merge()`: managed copy, không phải gắn lại object cũ một cách máy móc

`merge()` là một nguồn nhầm lẫn quan trọng về identity.

Giả sử:

```java
Customer detached = ...; // Entity có ID 42, không còn managed.

em.getTransaction().begin();

Customer managed = em.merge(detached);

System.out.println(em.contains(managed));  // true
System.out.println(em.contains(detached)); // thông thường false

em.getTransaction().commit();
```

Với entity detached, `merge` sao chép state cần thiết của object được truyền vào sang một **managed instance tương ứng** và trả về managed instance ấy. Object `detached` **không tự động biến thành managed** chỉ vì nó là đối số của `merge`.

Vì vậy:

```java
Customer managed = em.merge(detached);

managed.rename("Tên A");  // thay đổi managed instance

detached.rename("Tên B"); // detached vẫn detached
```

Không nên kỳ vọng thay đổi sau trên `detached` sẽ được flush, trừ khi application gọi merge khác hoặc thực hiện thao tác đồng bộ rõ ràng.

### Nếu context đã có Customer #42

```java
Customer existing = em.find(Customer.class, 42L);
Customer merged = em.merge(detachedCustomerWithId42);

System.out.println(existing == merged); // true
```

Khi identity này đã managed trong context, `merge` sử dụng managed representative tương ứng để nhận state. Ví dụ minh họa lý do identity map vẫn chỉ có một managed instance, dù một object detached khác được đưa vào.

### Vì sao không sửa một managed entity bằng cách tạo bản sao thủ công?

Giả sử ứng dụng có:

```java
Customer managed = em.find(Customer.class, 42L);
Customer anotherObject = ...; // cùng ID, nhưng object khác
```

Không có cơ chế chuẩn để đưa cả hai object thành **hai managed representatives** cùng identity trong một context. Nếu cần cập nhật state, nên:

- Thay đổi trực tiếp `managed` qua domain methods, hoặc
- Dùng `merge()` với hiểu biết về bản sao managed được trả về, cascade và optimistic locking.

Đưa đối tượng detached vào association và kỳ vọng nó lập tức được quản lý có thể dẫn đến những lỗi trạng thái khác; cần kiểm soát ranh giới giữa managed/detached.

## 15. Tại sao gọi `persist()` lên detached entity là sai mục đích?

`persist()` được dùng để đưa một entity **new** vào trạng thái persistent. Nếu object đã có hàng DB và đã detached, nó không trở thành “new” chỉ vì không nằm trong context hiện tại.

Ví dụ sai về ý định:

```java
Customer detached = loadInAnotherContext();
em.persist(detached);
```

Tùy provider và trạng thái cụ thể, đoạn code có thể gây `EntityExistsException`, `PersistenceException` hoặc lỗi khi flush/commit. Không nên dùng `persist()` như một lệnh “đảm bảo entity đang managed” cho mọi object có ID.

Cách hợp lý là xác định mục đích:

| Mục đích | Thao tác thường phù hợp |
| --- | --- |
| Tạo Customer mới, chưa persistent | `persist(newCustomer)` |
| Tải Customer có sẵn theo ID | `find(Customer.class, id)` |
| Cần reference tới entity đã biết ID | `getReference()`, với lưu ý kiểm tra tồn tại |
| Cập nhật state của entity đã managed | Gọi domain method trực tiếp |
| Đồng bộ state của detached entity | `merge(detached)`, dùng managed result |
| Ngừng quản lý một entity | `detach(entity)` |
| Tách tất cả managed entity | `clear()` |

**Trạng thái entity quan trọng không kém ID.** Một object có ID chưa đủ để kết luận nó đang managed.

## 16. `contains()` giúp xác định entity có đang managed không

`EntityManager.contains(entity)` được dùng để kiểm tra entity instance có thuộc persistence context của `EntityManager` hay không.

Ví dụ:

```java
Customer managed = em.find(Customer.class, 42L);

System.out.println(em.contains(managed)); // true

em.detach(managed);
System.out.println(em.contains(managed)); // false
```

Một object ở context khác:

```java
Customer a = em1.find(Customer.class, 42L);

System.out.println(em1.contains(a)); // true
System.out.println(em2.contains(a)); // false
```

`contains()` kiểm tra **instance đang được context quản lý**, không phải câu hỏi “database có hàng với ID này không?”. Muốn kiểm tra tồn tại của hàng, cần truy vấn phù hợp.

Đừng dùng:

```java
if (!em.contains(entity)) {
    em.persist(entity);
}
```

như một quy tắc tổng quát. `!contains` có thể là new, detached hoặc instance từ context khác; cách xử lý cho mỗi trường hợp khác nhau.

## 17. Tính duy nhất của entity và collection association

Giả sử hai đơn hàng cùng thuộc một khách hàng:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

trong class `PurchaseOrder`.

Hai đơn:

```text
orders:
  id=101, customer_id=42
  id=102, customer_id=42
```

Khi load hai Order trong cùng persistence context:

```java
PurchaseOrder firstOrder =
    em.find(PurchaseOrder.class, 101L);

PurchaseOrder secondOrder =
    em.find(PurchaseOrder.class, 102L);

Customer customer1 = firstOrder.getCustomer();
Customer customer2 = secondOrder.getCustomer();
```

JPA quản lý `Customer #42` như một entity identity trong context, thay vì tạo hai managed Customer object khác nhau tương ứng với mỗi Order. Với proxy/lazy loading, chi tiết khởi tạo và truy cập cần xét provider; về mặt mô hình, hai association cùng trỏ tới một persistent entity identity.

Điều này quan trọng khi thay đổi object:

```java
customer1.rename("Nguyễn An");

System.out.println(customer2.getFullName());
// Cùng trạng thái của Customer được quản lý trong context.
```

### Collection có thể lặp phần tử kết quả nhưng không lặp managed instance

Một query JOIN nhiều bản ghi con có thể tạo nhiều hàng SQL ứng với cùng parent. Provider có thể trả nhiều tham chiếu đến parent trong result list tùy ngữ nghĩa query, nhưng chúng vẫn có thể cùng trỏ tới một managed instance.

**Đừng dùng `results.size()` của một JPQL JOIN không được thiết kế loại trùng để suy ra số lượng entity identity khác nhau.** Hãy dùng `DISTINCT`, `COUNT(DISTINCT ...)` hoặc projection đúng mục đích.

## 18. Entity identity không đồng nghĩa business key

Giả sử có hai Customer:

```text
customers:
id  email
42  an@example.com
73  an+new@example.com
```

Nếu doanh nghiệp coi email là định danh tự nhiên (*natural key*), đó vẫn không tự động là primary key JPA nếu mapping đang dùng `id`.

```java
@Id
private Long id;

@Column(unique = true)
private String email;
```

JPA identity map quản lý theo `id`, không theo giá trị `email`. Mỗi `Customer` có ID riêng sẽ là entity identity riêng dù email giống nhau trong Java trước khi database ràng buộc uniqueness.

Một business key có thể thay đổi (email, số điện thoại) nên thường không phù hợp làm tiêu chí identity ổn định trong mọi tình huống. Cần phân biệt:

- **Primary key/JPA identity:** cách persistence context nhận diện một entity.
- **Business key:** giá trị nghiệp vụ dùng để tìm hoặc kiểm soát tính duy nhất.
- **Object reference:** địa chỉ đối tượng trong JVM.
- **`equals()/hashCode()`:** quy tắc bình đẳng do class implement.

Nếu sử dụng email làm `@Id`, đó là một lựa chọn thiết kế mapping khác; phải đảm bảo primary key đủ ổn định và các quy tắc thay đổi phù hợp.

## 19. `equals()/hashCode()` và hai entity cùng ID ở hai context

Đây là một bài toán thiết kế thường gặp khi entity được đưa vào `Set` hoặc làm key trong `Map`.

Giả sử:

```java
Customer a = em1.find(Customer.class, 42L);
Customer b = em2.find(Customer.class, 42L);

System.out.println(a == b); // khác tham chiếu trong hai context
```

Nếu class không override `equals()`, `a.equals(b)` có thể là `false`. Nhưng về mặt persistent identity, cả hai đại diện cho `Customer #42`.

Một số nhóm chọn implement `equals()` dựa trên khóa chính khi ID khác null. Tuy nhiên, phải xử lý cẩn thận entity **transient** chưa có ID và proxies.

### Sai lầm: coi mọi entity ID null đều bằng nhau

Đoạn code sau là không phù hợp:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof Customer c)) return false;
    return Objects.equals(id, c.id);
}
```

Hai Customer mới cùng có `id == null` sẽ được coi là bằng nhau vì `Objects.equals(null, null)` trả true. Trong một `HashSet`, một trong hai object có thể bị mất khỏi collection ngay cả khi chúng khác nhau.

### Sai lầm: hash code thay đổi sau `persist()`

Ví dụ:

```java
@Override
public int hashCode() {
    return Objects.hashCode(id);
}
```

Nếu ID từ `null` thành `42` sau khi persist, hash code thay đổi. Một object đã nằm trong `HashSet` có thể không còn được tìm/xóa đúng qua thuật toán hash thông thường.

### Một hướng thiết kế có thể cân nhắc

Với entity dùng ID sinh và không có immutable business key phù hợp, một mẫu thường được thảo luận là:

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (!(other instanceof Customer c)) return false;
    return id != null && id.equals(c.getId());
}

@Override
public int hashCode() {
    return Customer.class.hashCode();
}
```

Mẫu này minh họa các ý tưởng:

- Cùng tham chiếu thì bằng nhau.
- Hai transient instances khác nhau không tự bằng nhau khi cùng ID null.
- Hai entity persistent có cùng ID có thể được coi bằng nhau.
- Hash code không đổi khi ID được sinh.

Tuy nhiên, **không phải công thức phổ quát**. Nếu hệ thống dùng kế thừa entity, proxy subclass, nhiều persistence unit hoặc quy tắc runtime class khác nhau, cần điều chỉnh cách xác định kiểu, có thể phụ thuộc provider. `Customer.class.hashCode()` là một ví dụ đơn giản cho class không có hệ phân cấp phức tạp; không nên chép máy móc khi inheritance làm hai class có thể nhận cùng identity semantics khác.

Điều quan trọng nhất của bài này: **không cần override `equals()` để bảo đảm JPA chỉ quản lý một instance cho một identity trong cùng persistence context**. Đó là trách nhiệm của provider, không phụ thuộc vào `equals()` do ứng dụng tự viết.

## 20. Cache cấp một khác cache cấp hai

Persistence context thường được mô tả là **first-level cache**. Một số provider còn hỗ trợ **second-level cache** hoặc shared cache giữa nhiều context.

### First-level cache / identity map

- Gắn với persistence context cụ thể.
- Duy trì identity của managed entity trong context đó.
- Theo dõi thay đổi state cho dirty checking.
- Bị ảnh hưởng bởi `detach()`, `clear()`, `close()` và lifecycle context.

### Second-level cache / shared cache

- Có thể được chia sẻ giữa nhiều persistence context tùy provider/cấu hình.
- Có thể giữ trạng thái entity hoặc dữ liệu khác để giảm truy cập database.
- Không biến hai persistence context thành cùng một context.
- **Không có nghĩa hai `EntityManager` phải trả về cùng object reference Java**.

Sơ đồ:

```text
Context A                       Context B
Customer 42 → Object A          Customer 42 → Object B
       │                               │
       └───────────┬───────────────────┘
                   ▼
          Optional Shared Cache
                   │
                   ▼
                Database
```

Dù cache chia sẻ state, mỗi context vẫn cần quản lý identity của **managed entity instance của riêng mình**.

### Khi shared cache stale

Nếu một chương trình khác cập nhật database trực tiếp, cache cấp hai và context cấp một có thể còn dữ liệu cũ. Cần chiến lược eviction, refresh, invalidation hoặc transaction/cache consistency phù hợp với provider.

**Identity consistency không đồng nghĩa dữ liệu mới nhất từ database luôn được tự động tải lại.**

## 21. Identity map không phải bảo đảm dữ liệu luôn mới

Giả sử:

1. `em1` tải `Customer #42`, tên lúc đó là “An”.
2. Một transaction của `em2` cập nhật DB thành “An Mới” và commit.
3. `em1` gọi `find(Customer.class, 42L)` lần nữa.

Vì Customer #42 đã managed trong `em1`, lời gọi `find()` có thể trả lại **chính instance hiện có** với state đã nạp trước đó, thay vì tự động truy vấn tên mới từ DB.

Điều này duy trì tính duy nhất identity trong context, nhưng ứng dụng có thể thấy **state cũ**.

### Khi cần lấy lại state từ DB

```java
Customer customer = em.find(Customer.class, 42L);

// Ở thời điểm thích hợp:
em.refresh(customer);
```

`refresh()` có ý định đồng bộ state của managed entity từ database theo quy tắc JPA và các lock/cascade phù hợp. Cần sử dụng trong transaction/context hợp lệ và hiểu tác động tới những thay đổi local chưa flush.

Ngoài ra có thể dùng transaction/context mới, lựa chọn cache bypass, hoặc lock strategy nếu yêu cầu nhất quán cụ thể.

### Không thay optimistic locking bằng identity map

Nếu hai context cập nhật cùng hàng, `@Version` giúp phát hiện xung đột ghi theo semantics optimistic locking. Mỗi context duy trì identity riêng không đủ để ngăn lost update.

Khi gặp vấn đề stale data, hãy phân biệt:

- State đang managed trong context.
- Cache cấp hai.
- Transaction isolation/snapshot của database.
- Những thao tác bulk SQL hoặc cập nhật ngoài ORM.
- Cơ chế optimistic/pessimistic locking.

Không nên chỉ gọi `find()` lặp lại và kỳ vọng nó luôn tải bản ghi mới nhất.

## 22. Bulk JPQL update và native SQL có thể làm context không đồng bộ

Giả sử context đã nạp:

```java
Customer customer = em.find(Customer.class, 42L);
```

Sau đó chạy bulk update:

```java
em.getTransaction().begin();

em.createQuery(
    "UPDATE Customer c SET c.fullName = :name " +
    "WHERE c.id = :id"
).setParameter("name", "Tên mới")
 .setParameter("id", 42L)
 .executeUpdate();

em.getTransaction().commit();
```

Bulk update có ngữ nghĩa riêng và **không tự cập nhật state của mọi managed entity instance trong persistence context**. `customer.getFullName()` có thể vẫn là tên cũ trong bộ nhớ.

Điều tương tự có thể xảy ra khi chạy native SQL trực tiếp hoặc một ứng dụng khác thay đổi DB. Sự tồn tại của identity map không có nghĩa provider tự quan sát mọi thay đổi xảy ra bên ngoài quá trình dirty checking của managed entity.

Một cách xử lý tùy nhu cầu là:

```java
em.refresh(customer);
```

hoặc:

```java
em.clear();
Customer reloaded = em.find(Customer.class, 42L);
```

Cần chú ý `clear()` tách cả các managed entity khác và có thể làm mất thay đổi pending chưa flush; không nên dùng nó như một câu lệnh “làm mới an toàn cho mọi trường hợp” khi đang có thay đổi local quan trọng.

## 23. Context kéo dài có thể giữ quá nhiều managed entities

Vì context giữ identity và state của nhiều object đã nạp, một transaction hoặc một `EntityManager` mở quá lâu có thể gây:

- Tăng bộ nhớ do số lượng managed instance và snapshot.
- Dữ liệu lâu không được refresh, dễ stale.
- Dirty checking hoặc flush tốn chi phí.
- Khó kiểm soát transaction/locking.
- Lẫn lộn entity managed và detached khi truyền qua các tầng ứng dụng.

Ví dụ batch đọc nhiều khách hàng:

```java
List<Customer> customers = em.createQuery(
    "SELECT c FROM Customer c",
    Customer.class
).getResultList();
```

Nếu bảng có hàng triệu bản ghi, không nên tải toàn bộ vào một persistence context chỉ để xử lý từng record. Cần thiết kế pagination, batch/streaming phù hợp, transaction boundaries, và flush/clear ở thời điểm thích hợp.

Một quy tắc hữu ích: **persistence context nên có vòng đời vừa đủ cho một đơn vị công việc cần tính nhất quán của object graph**, không kéo dài toàn bộ vòng đời server chỉ vì identity map giúp tránh query lặp.

## 24. So sánh vòng đời của một entity qua các thao tác

Bảng sau tổng hợp cách một Java object và một persistence context tương tác:

| Thao tác | Object/identity trong context | Hệ quả về tính duy nhất |
| --- | --- | --- |
| `new Customer(...)` | New/transient, chưa managed | Chưa có managed representative |
| `em.persist(customer)` | Entity new được đưa vào context thích hợp | Context quản lý identity khi được thiết lập |
| `em.find(Customer.class, id)` | Trả về managed entity nếu tồn tại | Cùng identity trong context → cùng managed instance |
| JPQL trả về entity | Entity được quản lý trong context | Cùng persistent identity → cùng managed instance |
| `em.getReference(Customer.class, id)` | Tham chiếu/proxy theo identity | Không làm mất nguyên tắc unique managed identity |
| `em.detach(customer)` | Object không còn managed | Có thể có managed instance khác sau lần load tiếp theo |
| `em.clear()` | Tất cả managed entities thành detached | Identity map của context được làm rỗng |
| `em.merge(detached)` | Sao chép state sang managed instance, trả về instance đó | Detached object không tự thành managed |
| `em.refresh(managed)` | Nạp lại state của managed entity | Không phải tạo managed identity thứ hai |
| `em.close()` | Kết thúc vòng đời EntityManager application-managed | Các instance không còn được context đóng quản lý |

Bảng mô tả tình huống điển hình theo JPA. Với extended persistence context, cascade, context synchronization và provider-specific features, thời điểm các state chuyển đổi cần xét đúng cấu hình; nguyên tắc identity của managed entity vẫn là nền tảng.

## 25. Tình huống ứng dụng thực tế: một đơn hàng, hai đường truy cập Customer

Hãy xét một service xử lý thanh toán:

```java
Customer customer = em.find(Customer.class, customerId);
PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
```

Giả sử `order.getCustomer()` trỏ tới cùng `customerId`:

```java
Customer ownerOfOrder = order.getCustomer();
```

Trong một persistence context quản lý cả hai entity, `customer` và `ownerOfOrder` đại diện **cùng persistent Customer identity**.

Khi ứng dụng gọi:

```java
customer.rename("Nguyễn An Mới");
```

bất kỳ đoạn code nào đọc cùng managed Customer trong context đều nhìn thấy state của object đó. Không phải viết logic đồng bộ hai bản sao customer chỉ vì truy cập qua hai repository/association khác nhau.

### Nhưng chuyển entity sang transaction khác thì sao?

Nếu một DTO hoặc một entity detached được gửi sang một transaction xử lý sau, persistence context mới có thể tải một managed Customer instance khác. Không nên so sánh `==` giữa object từ hai context để quyết định chúng có cùng hàng DB hay không.

Ở ranh giới ứng dụng hoặc message queue, thường nên truyền **ID hoặc DTO** thay vì chuyển nguyên managed entity, rồi tải entity phù hợp trong transaction mới.

## 26. Những sai lầm phổ biến

### Sai lầm 1: “Cùng ID thì luôn cùng Java object”

Sai nếu hai entity đến từ persistence context khác nhau. Quy tắc một managed instance duy nhất chỉ áp dụng **trong cùng context**.

### Sai lầm 2: “Mỗi lần gọi `find()` luôn có một câu SQL”

Không chắc. Nếu entity đã managed, context có thể trả instance hiện có. Provider còn có thể dùng shared cache. Số query phải xem theo cấu hình và SQL thực tế.

### Sai lầm 3: “Không override `equals()` thì JPA không biết hai entity cùng ID”

JPA quản lý entity identity dựa trên metadata mapping/primary key, không dựa vào cách ứng dụng override `equals()`.

### Sai lầm 4: “Kết quả JPQL không bao giờ có phần tử trùng”

Một JOIN có thể tạo nhiều kết quả cho cùng root entity. List có thể chứa lặp reference, dù context vẫn có một managed instance. Dùng `DISTINCT`/projection đúng mục đích.

### Sai lầm 5: “`merge()` biến object truyền vào thành managed”

Với detached entity, merge **trả về managed instance**, còn object truyền vào vẫn detached. Phải sử dụng instance trả về khi muốn tiếp tục thay đổi managed state.

### Sai lầm 6: “`!em.contains(entity)` nghĩa là entity chưa từng lưu”

Sai. Object có thể detached hoặc thuộc context khác. Cần phân biệt new/detached/managed trước khi chọn `persist` hoặc `merge`.

### Sai lầm 7: “`clear()` chỉ làm mới dữ liệu và không có hậu quả”

`clear()` detach tất cả managed entities; thay đổi chưa flush có thể không được đồng bộ. Đó không phải lệnh refresh an toàn mặc định.

### Sai lầm 8: “Identity map ngăn lost update giữa hai request”

Không. Hai context có thể cập nhật cùng hàng độc lập. Dùng transaction isolation, `@Version` và cơ chế locking phù hợp.

### Sai lầm 9: “Shared cache khiến các context dùng cùng object Java”

Không. Cache chia sẻ có thể tái sử dụng dữ liệu/state; mỗi context vẫn quản lý managed entity identity của riêng mình.

### Sai lầm 10: “Đổi primary key của managed entity là cách đổi identity”

Không. Định danh persistent phải ổn định sau khi entity đã persistent. Nếu cần mã nghiệp vụ đổi được, hãy tách khỏi `@Id`.

### Sai lầm 11: “Truy vấn lại sẽ tự cập nhật dữ liệu bị sửa ngoài JPA”

Chưa chắc. Instance managed đã có có thể vẫn giữ state cũ. Bulk SQL/native SQL và cập nhật từ context khác cần chiến lược refresh/cache invalidation phù hợp.

### Sai lầm 12: “Có cùng email là cùng entity identity”

Chỉ khi email thực sự là một phần định danh persistent được ánh xạ như khóa chính. Nếu `@Id` là `id`, email là business key khác với JPA identity.

## 27. Bài tập suy luận

### Bài tập A: Hai lần tìm cùng ID

```java
Customer a = em.find(Customer.class, 42L);
Customer b = em.find(Customer.class, 42L);
```

**Câu hỏi:** Giả sử hàng tồn tại và hai lời gọi dùng cùng context, `a == b` có ý nghĩa gì?

**Đáp án:** Hai biến trỏ tới cùng managed Customer instance cho identity `Customer #42` trong context.

### Bài tập B: Hai EntityManager

```java
Customer a = em1.find(Customer.class, 42L);
Customer b = em2.find(Customer.class, 42L);
```

**Câu hỏi:** Có bắt buộc `a == b` không?

**Đáp án:** Không. Mỗi context có thể có managed instance riêng dù cùng persistent identity.

### Bài tập C: Clear rồi find lại

```java
Customer a = em.find(Customer.class, 42L);
em.clear();
Customer b = em.find(Customer.class, 42L);
```

**Câu hỏi:** Vì sao `a == b` không được bảo đảm?

**Đáp án:** `clear()` detach `a`. Context có thể tạo managed representative mới `b` cho cùng identity.

### Bài tập D: Merge detached

```java
Customer detached = ...;
Customer managed = em.merge(detached);
```

**Câu hỏi:** Nên tiếp tục sửa object nào để thay đổi được dirty checking trong context?

**Đáp án:** Sửa `managed`, tức instance được `merge` trả về. `detached` không tự trở thành managed.

### Bài tập E: JOIN sinh nhiều hàng

Một Customer có 5 Order. JPQL query JOIN trả Customer theo từng Order.

**Câu hỏi:** Nếu result list có 5 phần tử cho Customer đó, có 5 managed Customer instances không?

**Đáp án:** Không. List có thể chứa lặp tham chiếu tới cùng managed entity instance. Cần tách tính duy nhất của object managed khỏi việc loại trùng trong kết quả query.

### Bài tập F: Bulk SQL

`em` đã tải `Customer #42`, sau đó bulk query cập nhật tên ngay trong DB.

**Câu hỏi:** Vì sao `em.find(Customer.class, 42L)` tiếp theo chưa chắc trả tên mới?

**Đáp án:** Persistence context đã có managed Customer instance; bulk update không tự cập nhật state của instance đó. Cần refresh/clear hoặc thiết kế ranh giới context phù hợp.

### Bài tập G: ID mới sinh sau persist

`Customer` mới có `id == null` trước persist, sau đó DB tạo ID. Một `HashSet` dùng `hashCode()` từ ID và lưu entity trước persist.

**Câu hỏi:** Rủi ro là gì?

**Đáp án:** Hash code thay đổi khi ID xuất hiện, khiến chứa/tìm/xóa phần tử trong Set gặp lỗi. Cần chiến lược equality/hashCode ổn định cho lifecycle entity.

### Bài tập H: Nhiều transaction cùng cập nhật

Hai persistence context cùng load `Customer #42` ở version 5, rồi sửa tên khác nhau.

**Câu hỏi:** Identity map có tự ngăn cập nhật chồng lên nhau không?

**Đáp án:** Không. Cần cơ chế concurrency control như `@Version` và chính sách transaction. Một context không biết trực tiếp managed instance của context kia.

## 28. Quy trình tư duy khi phân tích identity trong JPA

Khi gặp hai biến Java có vẻ đại diện cho cùng entity, hãy hỏi:

1. **Đây có phải hai loại entity giống nhau theo mapping?** `Customer #42` không phải `Order #42`.
2. **Khóa chính tương ứng là gì?** `@Id` đơn hay `@EmbeddedId`/`@IdClass` tổng hợp?
3. **Hai object có nằm trong cùng persistence context không?** Đây là điều kiện quan trọng nhất của unique managed instance.
4. **Chúng đang managed, new hay detached?** Có lệnh `detach()`, `clear()`, `close()` hoặc kết thúc context nào không?
5. **Có `merge()` không?** Nếu có, đang dùng object truyền vào hay managed result?
6. **Kết quả là một list JOIN hay một object instance?** Số phần tử trong list không đồng nghĩa số managed entities khác nhau.
7. **Có proxy/`getReference()` không?** Tránh giả định về class runtime hoặc thời điểm tải.
8. **Có bulk update/SQL trực tiếp hoặc cache không?** Entity có thể là cùng instance nhưng state đã cũ.
9. **Có transaction khác cùng sửa một hàng không?** Identity map không thay locking.
10. **`equals()/hashCode()` có gây hiểu nhầm không?** Tách Java equality khỏi JPA identity.
11. **Context có đang sống quá lâu không?** Cân nhắc stale data, bộ nhớ và ranh giới transaction.
12. **Đang truyền entity qua API/message hay giữa các tầng không?** Cân nhắc truyền ID/DTO, tải lại trong context phù hợp.

Trả lời được chuỗi câu hỏi này giúp xác định vấn đề thuộc identity, entity lifecycle, truy vấn, transaction hay cache mà không sửa nhầm tầng.

## Kết luận

Trong JPA, **một persistent entity identity tương ứng với một managed entity instance duy nhất trong cùng persistence context**. Quy tắc này thường được hiểu qua *identity map* hoặc *first-level cache*: khi cùng entity được tìm bằng `find()`, JPQL hay một association, provider không duy trì hai managed object khác nhau cho cùng identity trong một context.

Phạm vi bảo đảm phải được hiểu chính xác. Hai `EntityManager` với hai context khác nhau có thể tạo hai Java objects cho cùng hàng DB. Sau `detach()` hoặc `clear()`, object cũ không còn managed; `merge()` trả về một managed representative chứ không mặc nhiên biến đối số detached thành managed. Tính duy nhất identity cũng không bảo đảm query result không có phần tử trùng, không đồng nghĩa dữ liệu luôn mới và không tự ngăn xung đột giữa các transaction.

Khi làm việc với entity, hãy phân biệt **tham chiếu Java, định danh database, equality của class và phạm vi persistence context**. Câu hỏi cốt lõi cần luôn nhớ là: **“Hai thao tác này có đang nói về cùng entity identity trong cùng ngữ cảnh đang quản lý hay không?”**. Từ đó, ta có thể dự đoán hành vi của `find`, `persist`, `merge`, dirty checking và những thay đổi state một cách chính xác hơn.
