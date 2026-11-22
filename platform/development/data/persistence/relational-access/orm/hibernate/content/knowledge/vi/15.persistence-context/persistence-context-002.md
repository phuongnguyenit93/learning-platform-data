# Bộ nhớ đệm cấp một và việc đọc lại không nhất thiết phát SQL mới

Trong Hibernate ORM, một lời gọi Java tới `EntityManager.find()` hoặc `Session.get()` **không nhất thiết tạo một câu `SELECT` mới**. Lý do là mỗi `Session`/`EntityManager` quản lý một **persistence context** chứa những entity đã được nạp hoặc đang được quản lý. Hibernate sử dụng persistence context như một **bộ nhớ đệm cấp một** (*first-level cache*, L1 cache) và một **identity map**: trong cùng một context, mỗi persistent identity chỉ có một đối tượng managed đại diện.

Điều này đem lại ba lợi ích quan trọng:

1. **Tránh truy vấn không cần thiết:** cùng một entity được tìm nhiều lần theo khóa chính thường chỉ cần truy cập database lần đầu.
2. **Bảo toàn identity:** hai lần `find()` cùng khóa trong một context trả về cùng Java object, không chỉ một object có dữ liệu tương đương.
3. **Nhất quán trong đơn vị công việc:** thay đổi chưa `flush()` của một entity managed được nhìn thấy qua các tham chiếu tới chính entity đó.

Tuy nhiên, L1 cache **không phải** “cache mọi kết quả SQL”, **không bảo đảm dữ liệu luôn mới nhất**, **không chia sẻ giữa hai `EntityManager` độc lập**, và **không có nghĩa mọi lệnh đọc đều tránh SQL**. Bài học giải thích chính xác khi nào Hibernate tái sử dụng object, khi nào vẫn truy vấn database, và cách kiểm tra bằng code/log.

## 1. Persistence context là gì?

Theo Jakarta Persistence, persistence context là tập hợp các entity instance được quản lý, trong đó với mỗi **entity type + primary key**, có tối đa một instance đại diện. Trong Hibernate, `org.hibernate.Session` là API trung tâm của persistence context; `jakarta.persistence.EntityManager` cung cấp API chuẩn JPA cho cùng mô hình quản lý.

Ví dụ:

```text
Persistence Context của EntityManager A
┌───────────────────────────────────────────────────┐
│ Persistent identity                Managed object │
│ (Customer, 10) -----------------> Customer@0xA123 │
│ (Customer, 20) -----------------> Customer@0xB456 │
│ (Order,    30) -----------------> Order@0xC789    │
└───────────────────────────────────────────────────┘
                  │
                  │ Nếu chưa có đối tượng tương ứng
                  ▼
              JDBC / SQL
                  │
                  ▼
               Database
```

Khi gọi:

```java
Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 10L);
```

với cùng `em`, nếu lần đầu đã load thành công và không có thao tác nào tách/xóa/refresh thay đổi trạng thái quản lý, thì:

```java
first == second    // true
```

Đây là **reference identity** trong cùng persistence context. Nó không phụ thuộc vào việc bạn có tự override `Customer.equals()` hay không.

### 1.1. Khóa tra cứu trong L1 cache

Có thể hình dung khóa nội bộ là:

```text
(Entity type, entity identifier) → Managed entity instance
```

Cách triển khai nội bộ của Hibernate có thêm metadata liên quan entity mapping, tenant, trạng thái và proxy; không nên suy ra chính xác cấu trúc `Map` nội bộ từ sơ đồ trên.

Một số điểm quan trọng:

- `Customer(id=10)` và `Order(id=10)` **không phải cùng identity**.
- Hai entity instance có cùng ID **trong hai context khác nhau** không nhất thiết cùng object Java.
- Một entity có `@EmbeddedId` vẫn được nhận diện bằng persistent identifier tương ứng.
- Persistence context còn quản lý **trạng thái**, snapshot cần thiết cho dirty checking, associations và collections; nó không chỉ là một map tối giản.
- `EntityManager`/`Session` thường **không thread-safe**; không chia sẻ chúng tùy tiện giữa nhiều request/thread để “tận dụng cache”.

## 2. “First-level cache” không phải cache được cấu hình bật/tắt như L2

L1 cache là một đặc tính nền tảng của mô hình stateful `Session`/`EntityManager`. Trong cách sử dụng thông thường, bạn **không cần bật property cache** để nhận được identity map.

Phân biệt:

| Cơ chế | Phạm vi | Lưu gì | Có mặc định không? |
| --- | --- | --- | --- |
| **First-level cache / persistence context** | Một `Session`/`EntityManager` | Managed entities và trạng thái liên quan | Có trong stateful ORM session |
| **Second-level cache (L2)** | Thường ở mức `SessionFactory`/persistence unit, tùy cấu hình | Dữ liệu entity/collection phù hợp chiến lược cache | Không mặc nhiên cache mọi entity |
| **Query result cache** | Provider/cache region được cấu hình | Thông tin kết quả truy vấn, thường ID và giá trị kết quả | Cần bật/cấu hình riêng |
| **Database buffer cache** | Database server | Pages/blocks của database | Ngoài Hibernate |
| **HTTP/Redis/application cache** | Theo kiến trúc ứng dụng | DTO, response, dữ liệu tùy chọn | Ngoài persistence context |

L1 cache **không cần annotation `@Cacheable` hoặc `@Cache`** để tránh `SELECT` thứ hai cho cùng managed entity theo khóa chính trong cùng context.

Ngược lại, `@Cacheable`/Hibernate L2 cache không làm hai context biến thành một context. Chúng có thể giúp **giảm truy vấn database giữa các session** nhưng mỗi session vẫn quản lý các instance riêng biệt.

### 2.1. Tại sao gọi là cấp một?

Vì Hibernate luôn kiểm tra trạng thái trong persistence context của session trước khi phải tìm dữ liệu ngoài context. Nếu object cần đọc đã có và có thể dùng lại, không cần tới JDBC cho phép tải theo khóa chính thông thường.

Có thể hình dung:

```text
em.find(Customer.class, 10L)
        |
        v
  Persistence context
        |
   ┌────┴────┐
   │         │
 Cache hit  Cache miss
   │         │
   v         v
 Trả cùng   Có thể thử L2 cache (nếu cấu hình)
 object     hoặc đọc JDBC/DB
```

Không nên đọc sơ đồ này như một cam kết **mọi** `find()` miss L1 đều sinh đúng một SELECT: L2, entity proxy, lazy state, eager associations và cơ chế nạp dữ liệu có thể làm số SQL khác nhau.

## 3. Entity mẫu để quan sát L1 cache

Ví dụ `Customer` tối giản:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, unique = true, length = 200)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {
        // Constructor không tham số cho JPA.
    }

    public Customer(String email, String displayName) {
        this.email = Objects.requireNonNull(email);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String newName) {
        this.displayName = Objects.requireNonNull(newName);
    }
}
```

DDL minh họa cho PostgreSQL:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(200) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL
);
```

Giả sử database đã có:

```text
customers
+----+-------------------+--------------+
| id | email             | display_name |
+----+-------------------+--------------+
| 10 | alice@example.org | Alice        |
+----+-------------------+--------------+
```

Các ví dụ dùng `EntityManagerFactory emf` đã cấu hình với Hibernate và transaction **resource-local**, trừ khi nói khác. `@GeneratedValue(IDENTITY)` ở entity minh họa cho trường hợp insert; ID `10` trong các ví dụ đọc được giả định là dữ liệu đã có, không được gán trực tiếp vào field từ Java.

## 4. Hai lần `find()` theo cùng ID trong cùng `EntityManager`

```java
import jakarta.persistence.EntityManager;

try (EntityManager em = emf.createEntityManager()) {
    Customer first = em.find(Customer.class, 10L);
    Customer second = em.find(Customer.class, 10L);

    System.out.println(first == second); // true
    System.out.println(first.getDisplayName());  // Alice
    System.out.println(second.getDisplayName()); // Alice
}
```

Dòng thời gian điển hình, trong một môi trường không có L2 cache hit và không có SQL bổ sung từ association:

```text
T0  em được tạo                   L1 cache rỗng

T1  find(Customer, 10)            L1 miss
                                   → SELECT ... WHERE id = 10
                                   → Customer#10 được managed

T2  find(Customer, 10)            L1 hit
                                   → trả cùng Java instance
                                   → không cần SELECT mới

T3  em.close()                    kết thúc persistence context
                                   → entity trở thành detached
```

Giá trị của L1 cache là **lần đọc thứ hai không cần load lại entity từ database**. Điều kiện quan trọng:

- Cả hai lời gọi dùng **cùng persistence context**.
- Entity còn **managed**, chưa bị `clear()`, `detach()` hoặc context bị đóng.
- Đây là thao tác tìm theo primary key thông thường, không yêu cầu khóa pessimistic, refresh hoặc thao tác có yêu cầu truy cập database khác.
- Không có yếu tố provider/mapping đặc biệt bắt buộc truy cập thêm dữ liệu chưa load.

Vì thế câu “`find()` lần hai chắc chắn không bao giờ phát SQL” là **quá tuyệt đối**. Kết luận chính xác hơn: **đối với entity đã managed và một lời gọi `find()` thông thường, Hibernate có thể trả từ L1 mà không SELECT lại hàng của entity đó**.

### 4.1. Identity khác với equals

Ngay cả khi `Customer` không override `equals()`/`hashCode()`:

```java
first == second          // true
first.equals(second)     // true do cùng reference
```

Điều này **không chứng minh** hàm `equals()` của entity đã được viết đúng để so hai object đến từ các session khác nhau. L1 cache bảo đảm một instance theo persistent identity **trong một context**, chứ không sửa hợp đồng equality của Java.

## 5. Hai `EntityManager` khác nhau: hai L1 cache khác nhau

```java
Customer first;
Customer second;

try (EntityManager em1 = emf.createEntityManager()) {
    first = em1.find(Customer.class, 10L);
}

try (EntityManager em2 = emf.createEntityManager()) {
    second = em2.find(Customer.class, 10L);
}

System.out.println(first == second); // Thường false.
```

`em1` và `em2` có hai persistence contexts riêng. Mỗi context có thể phải nạp entity lần đầu.

```text
EntityManager A                       EntityManager B
+----------------------+              +----------------------+
| (Customer,10) → A@1  |              | (Customer,10) → B@2  |
+----------------------+              +----------------------+
           |                                     |
           +--------- cùng hàng DB #10 ----------+
```

Nếu **không cấu hình L2**, thông thường có thể quan sát hai lần SELECT, mỗi context một lần. Nếu L2 đang bật và entity cacheable, session thứ hai có thể lấy dữ liệu từ L2 mà **không phát SELECT ở lần đọc đầu tiên** trong context mới. Tuy vậy, `first` và `second` vẫn không bắt buộc là cùng Java object.

Vì thế, để chẩn đoán một SELECT có xuất hiện hay không cần xác định **cả scope session và cấu hình L2**, không chỉ đếm số lần gọi repository.

## 6. Cùng một entity có thể đã thay đổi trong bộ nhớ trước khi SQL được gửi

Đây là hành vi quan trọng hơn việc tiết kiệm một SELECT.

```java
EntityManager em = emf.createEntityManager();
var tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = em.find(Customer.class, 10L);
    customer.rename("Alice Updated");

    Customer again = em.find(Customer.class, 10L);

    System.out.println(customer == again); // true
    System.out.println(again.getDisplayName()); // Alice Updated

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em.close();
}
```

Ở đây, lời gọi `rename()` thay thuộc tính Java của **managed entity**. Trước khi transaction được flush, database có thể vẫn đang lưu `"Alice"`, nhưng:

```java
again.getDisplayName()
```

trả `"Alice Updated"` vì `again` là **cùng object đang managed**.

Timeline:

```text
SELECT Customer#10
    ↓
Managed object: displayName = "Alice"
    ↓ customer.rename("Alice Updated")
Managed object: displayName = "Alice Updated"
Database row:   display_name = "Alice"       (trước flush)
    ↓ em.find(Customer,10) lần nữa
Trả managed object với "Alice Updated"
    ↓ flush/commit
Hibernate dirty checking → UPDATE database (nếu hợp lệ)
```

**Không có chuyện Hibernate phải đọc lại SQL để “thấy” thay đổi do chính Java vừa thực hiện.** Persistence context vừa là identity map vừa là **unit-of-work tracker**.

### 6.1. Dirty checking và cache có liên quan nhưng không đồng nhất

L1 cache giữ entity managed; Hibernate còn theo dõi những thay đổi cần đồng bộ.

- **Cache hit** cho biết entity đã có sẵn trong context.
- **Dirty checking** so/tracking trạng thái để quyết định `UPDATE`.
- **Flush** đồng bộ những thay đổi đang chờ vào database.
- **Commit** kết thúc transaction; thường flush trước khi commit nếu có thay đổi cần ghi.

Vì thế một lần `find()` không tạo `SELECT` **không có nghĩa không có SQL khác trong transaction**: commit vẫn có thể phát `UPDATE`.

## 7. Những thao tác có thể và không thể tận dụng L1 cache

| Thao tác | Có thể tránh SQL nhờ L1? | Giải thích |
| --- | --- | --- |
| `em.find(Customer.class, 10L)` lần hai | Có | Nếu cùng identity đang managed, trả object hiện có |
| `session.get(Customer.class, 10L)` lần hai | Có | Hibernate Session dùng cùng persistence context |
| `em.getReference(Customer.class, 10L)` | Có thể không SELECT | Có thể trả reference/proxy; không đồng nghĩa đã xác nhận hàng tồn tại |
| `customer.getDisplayName()` trên entity đã initialized | Có | Đọc state Java đang có |
| `em.persist(customer)` với entity mới | Không phải một “cache lookup” | Đăng ký managed entity và có thể INSERT theo generator/flush |
| `em.refresh(customer)` | Không dùng L1 để thay thế DB read | Có chủ đích nạp lại từ database, ghi đè state đã managed |
| `em.clear()` | Không | Xóa các association managed khỏi context; lần `find` sau có thể load lại |
| `em.detach(customer)` rồi `find()` | Không giữ entry đó | Có thể load instance mới |
| JPQL `select c from Customer c ...` | Không được đảm bảo bỏ SQL | Truy vấn phải xác định tập kết quả, dù entity trong kết quả có thể đã managed |
| JPQL `select count(c) ...` | L1 không tự trả lời aggregate | Thường cần SQL/DB hoặc query cache nếu có |
| Native SQL `SELECT ...` | L1 không tự chặn SQL | Native query thường chạy DB; entity kết quả vẫn có identity resolution |
| Lazy collection chưa initialized | Không | Lần truy cập có thể cần query riêng |
| Lazy collection đã initialized | Có | Lặp truy cập thường dùng collection đã nạp |
| `em.flush()` | Không dùng cache để “né” mọi SQL | Có thể phát INSERT/UPDATE/DELETE để đồng bộ |
| `em.lock(..., PESSIMISTIC_WRITE)` | Không thể coi chỉ là L1 read | Có thể cần SQL khóa trên database |
| `em.remove(managed)` | Đánh dấu xóa trong context | DELETE thường xảy ra khi flush/commit; không phải đọc lại |

Đây là bảng **ngữ nghĩa**, không phải số lượng SQL chắc chắn. L2/query cache, fetch graphs, flush mode, cascading và DB dialect có thể thay đổi câu SQL thực tế.

## 8. `find()` khác JPQL query: điểm dễ nhầm nhất

Xét:

```java
Customer byId = em.find(Customer.class, 10L);

List<Customer> customers = em.createQuery(
        "select c from Customer c where c.email = :email",
        Customer.class
    )
    .setParameter("email", "alice@example.org")
    .getResultList();
```

`find()` là **lookup theo primary key**; Hibernate có thể xác định có instance tương ứng ngay trong L1 cache.

JPQL query là yêu cầu **tìm tập kết quả theo một điều kiện**. L1 cache không được thiết kế như một index tổng quát cho mọi điều kiện, ví dụ `email LIKE`, `status`, `createdAt`, `COUNT`, `SUM`, `JOIN` hay pagination.

Dòng chảy thường là:

```text
JPQL query
    ↓
Hibernate tạo và thực thi SQL SELECT theo điều kiện
    ↓
Database trả rows / entity identifiers
    ↓
Hibernate đối chiếu từng persistent identity
    ↓
Nếu entity đã managed: tái sử dụng managed object
Nếu chưa có: hydrate và đưa entity vào persistence context
    ↓
Trả kết quả Java
```

Vì vậy có thể xảy ra **đồng thời**:

```java
customers.get(0) == byId     // true
```

và **SQL SELECT vẫn đã được gửi** để xác định kết quả JPQL.

### 8.1. L1 cache không phải query result cache

Query cache là cơ chế khác, cần cấu hình riêng và không mặc định áp dụng cho mọi query. Nó có thể giữ thông tin để tái sử dụng kết quả của một số truy vấn, nhưng khi trả về entity vẫn phải giải quyết dữ liệu/identity qua persistence context và có thể L2 hoặc database.

**Chỉ vì entity đã được `find()` theo ID không có nghĩa mọi JPQL query nhắc đến entity đó đều bỏ SELECT.**

### 8.2. Cùng kết quả query nhưng state Java có thể đã đổi

Giả sử `Customer#10` được load với `displayName="Alice"`, rồi ứng dụng đổi thành `"Alice Local"` trong context nhưng chưa flush. Một JPQL query lấy entity cùng ID có thể trả về **chính instance đang managed**, với `"Alice Local"`.

Đó là identity-map semantics; query **không phải** lệnh “ghi đè tất cả field đang managed bằng giá trị database vừa trả”. Nếu cần đọc lại state thực từ DB, hãy dùng `refresh()` có chủ đích.

Khi dùng `FlushModeType.AUTO`, Hibernate/JPA có thể flush trước query để đảm bảo các thay đổi có thể ảnh hưởng kết quả được đồng bộ. Với `FlushModeType.COMMIT`, tác động của thay đổi chưa flush lên kết quả query có giới hạn khác. Không coi query là công cụ reset lại entity state.

## 9. `persist()` và entity mới có trong persistence context

Một entity vừa được persist trở thành managed, dù SQL `INSERT` có thể chưa được gửi:

```java
EntityManager em = emf.createEntityManager();
var tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = new Customer(
        "new@example.org", "New Customer"
    );
    em.persist(customer);

    // Lúc này customer là managed.
    System.out.println(em.contains(customer)); // true

    em.flush(); // Đảm bảo đồng bộ INSERT tại thời điểm này.

    Long id = customer.getId();
    Customer again = em.find(Customer.class, id);

    System.out.println(customer == again); // true

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    em.close();
}
```

Ở đây dùng `em.flush()` để chắc chắn đã có ID sau khi INSERT thành công với chiến lược sinh khóa phù hợp. Với `IDENTITY`, Hibernate có thể phải thực hiện INSERT sớm để lấy ID; với `SEQUENCE`, nó có thể lấy ID trước và trì hoãn INSERT. **Không giả định một thời điểm sinh ID duy nhất cho mọi generator.**

Điểm mấu chốt: `persist()` đưa entity vào persistence context, và khi đã có ID, một `find()` tương ứng trong cùng context có thể trả chính instance đó.

### 9.1. `persist()` không phải `save` trả ngay ID theo mọi môi trường

JPA `EntityManager.persist()` có kiểu trả về `void`. Việc ID có ngay sau lời gọi hay sau flush phụ thuộc mapping và generator. Không cố gọi `em.find(Customer.class, null)` khi chưa có ID: API yêu cầu primary key hợp lệ và không null.

## 10. `getReference()` và proxy: không SELECT chưa chắc đã có dữ liệu

`EntityManager.getReference()` cho phép nhận tham chiếu tới entity theo khóa chính mà provider **có thể trì hoãn việc tải state**:

```java
Customer reference = em.getReference(Customer.class, 10L);

// Tùy Hibernate/proxy/bytecode enhancement, có thể chưa SELECT:
Long id = reference.getId();

// Khi cần thuộc tính chưa có, provider có thể SELECT:
String name = reference.getDisplayName();
```

`getReference()` đặc biệt hữu ích khi chỉ cần **gán foreign key** mà không cần đọc các thuộc tính khác của parent. Tuy nhiên:

- Nếu entity đã có managed instance trong context, Hibernate có thể trả chính instance/reference đó.
- Nếu chưa có, Hibernate có thể trả proxy hoặc một representation lazy khác.
- `getReference()` **không bảo đảm** hàng có ID đó đang tồn tại; lỗi như `EntityNotFoundException` có thể xuất hiện khi truy cập state.
- Proxy có thể kích hoạt SQL khi method cần initialize state.
- Nếu session đã đóng trước khi initialize, truy cập thuộc tính lazy có thể gặp `LazyInitializationException`.

**Không dùng `getReference()` như phép kiểm tra tồn tại**. Khi cần xác minh entity, dùng `find()` hoặc truy vấn/constraint phù hợp.

### 10.1. Proxy cũng tham gia identity map

Trong cùng context, Hibernate cần duy trì quy tắc một managed representation cho persistent identity. Nếu một reference/proxy đã tồn tại, `find()`/load sau đó phải tương tác với representation đó thay vì tạo những entity managed độc lập cho cùng identity. Hình thức Java cụ thể phụ thuộc proxy và enhancement strategy của Hibernate.

Vì thế, khi đo “`getReference()` không SQL”, cần xem cả câu lệnh gọi tiếp theo: SQL có thể xảy ra **lúc dereference**, không phải lúc lấy reference.

## 11. Lazy association và collection có vòng đời nạp riêng

L1 cache giúp tránh đọc lại **entity đã managed**, nhưng không có nghĩa **toàn bộ object graph đã được load**.

Ví dụ:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();
}
```

Đây là trích đoạn mapping; một class chạy đầy đủ cần constructors/getters và entity `OrderLine` có quan hệ ngược `order` phù hợp.

Tình huống:

```java
PurchaseOrder order = em.find(PurchaseOrder.class, 20L);
// order được managed, nhưng lines có thể vẫn chưa initialized.

int count = order.getLines().size();
// Có thể phát SELECT cho collection ở lần truy cập đầu.

int again = order.getLines().size();
// Khi collection đã initialized, thường không SELECT lại.
```

Vậy một request có thể chỉ `SELECT` entity một lần nhưng thêm `SELECT` cho collection. SQL count không thể suy từ số lần `find()`.

### 11.1. `find()` không bảo đảm mọi association LAZY đều không fetch

Một quan hệ `@ManyToOne` hoặc `@OneToOne` có thể là EAGER theo mặc định hoặc theo fetch plan; Hibernate có thể load thêm entity liên quan. `@EntityGraph`, `JOIN FETCH`, batch fetching, cache state và bytecode enhancement cũng ảnh hưởng SQL.

Nếu gọi `em.find(Customer.class, id)` chỉ một lần mà thấy nhiều câu SELECT, cần xem **association mapping**, không vội kết luận first-level cache hỏng.

### 11.2. L1 cache không tự chữa N+1

```java
List<PurchaseOrder> orders = em.createQuery(
    "select o from PurchaseOrder o",
    PurchaseOrder.class
).getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getLines().size());
}
```

Nếu mỗi order có collection chưa initialized, code có thể phát 1 query lấy orders và N query đọc lines. L1 cache chỉ giúp không load **lại cùng một entity/collection đã nạp**; nó không tự gộp mọi collection chưa load thành một SQL.

Cần fetch plan phù hợp (`JOIN FETCH`, entity graph, batch fetching, DTO projection…) tùy mục đích. Không bật EAGER mọi nơi như cách chữa chung.

## 12. `refresh()` yêu cầu đọc lại trạng thái từ database

L1 cache cho phép một context giữ trạng thái đã đọc. Nhưng nếu dữ liệu ngoài ứng dụng đã thay đổi, managed entity có thể cũ.

Ví dụ:

```text
T0  EntityManager A: SELECT Customer#10 → "Alice"
T1  EntityManager B: UPDATE Customer#10 → "Alice External", COMMIT
T2  EntityManager A: find(Customer#10) → vẫn cùng instance "Alice"
```

Với session A đang mở, lời gọi `find()` lần nữa **không mặc định là yêu cầu lấy dữ liệu mới nhất từ DB**.

Để làm mới một managed entity:

```java
Customer customer = em.find(Customer.class, 10L);

// Trong phạm vi có transaction/điều kiện thích hợp:
em.refresh(customer);

System.out.println(customer.getDisplayName());
```

`refresh()` có chủ đích tải lại state theo dữ liệu database, đồng thời **ghi đè thay đổi chưa flush trên entity đó**. Nếu đã sửa `customer.rename("Local")` mà chưa commit, gọi `refresh()` có thể làm mất thay đổi Java đang chờ của chính entity đó.

### 12.1. `refresh()` khác `find()` và `clear()`

| API | Tác động chính | Hệ quả |
| --- | --- | --- |
| `find(type, id)` | Tìm managed representation theo ID | Có thể trả từ L1, không reload |
| `refresh(entity)` | Nạp lại state của managed entity từ DB | Ghi đè state đang có, có thể phát SQL |
| `clear()` | Detach tất cả entity khỏi context | Lần `find` sau có thể load instance khác |
| `detach(entity)` | Detach một entity | Những thay đổi chưa flush trên entity không còn được đồng bộ |
| `close()` | Kết thúc `EntityManager` application-managed | Hủy persistence context, giải phóng resource |
| `merge(detached)` | Sao chép state detached vào một managed instance | **Không** phải refresh từ DB, object truyền vào vẫn detached |

`refresh()` chỉ hợp lệ với entity managed theo quy tắc JPA. Nó không phải lệnh reload tổng quát cho DTO hoặc bất kỳ detached object.

### 12.2. `refresh()` không đồng nghĩa thấy bất kỳ external update nào ngay lập tức

Database transaction isolation ảnh hưởng những thay đổi từ transaction khác mà một transaction đang chạy có thể nhìn thấy. Ở isolation như `REPEATABLE READ`, một `SELECT` mới trong cùng transaction chưa chắc nhìn thấy commit mới từ transaction khác. `refresh()` vẫn phải tuân theo transaction visibility của database.

Nếu hệ thống cần tính mới tuyệt đối hoặc điều kiện đồng thời nghiêm ngặt, phải thiết kế transaction, isolation, version/lock và yêu cầu đọc cụ thể; không chỉ gọi `refresh()` theo thói quen.

## 13. `clear()` làm mất lợi thế L1 của những entity trước đó

```java
Customer first = em.find(Customer.class, 10L);

em.clear(); // Detach toàn bộ managed entities.

Customer second = em.find(Customer.class, 10L);

System.out.println(first == second); // false trong kịch bản thông thường.
```

Sau `clear()`, persistence context không còn giữ instance managed `first`. Hibernate có thể tạo một instance mới khi `find()`; nếu L2 bật, SQL có thể không cần nhưng đó **không phải reuse L1**.

### 13.1. `clear()` có thể làm mất thay đổi chưa flush

```java
var tx = em.getTransaction();
tx.begin();

Customer customer = em.find(Customer.class, 10L);
customer.rename("Pending Name");

em.clear(); // Detach trước flush.
tx.commit();
```

Thay đổi `"Pending Name"` **không được Hibernate đồng bộ thông qua dirty checking sau khi entity đã detached**, nếu chưa có flush/SQL trước đó.

Để giữ thay đổi đã ghi khi muốn giải phóng context, có thể:

```java
em.flush();
em.clear();
```

nhưng nhớ rằng `flush()` chưa commit. Transaction có thể rollback sau đó. Không dùng `clear()` như “làm mới dữ liệu” nếu đang có pending changes mà chưa quyết định giữ hay bỏ.

### 13.2. Xóa khỏi context không đồng nghĩa xóa khỏi database

`em.clear()` **không chạy `DELETE` để xóa tất cả bản ghi đã load**. Nó chỉ detach object khỏi persistence context. Đây là sự khác biệt giữa **evict khỏi cache/context** và **remove entity**.

## 14. `detach()` xóa một entry khỏi persistence context

```java
Customer managed = em.find(Customer.class, 10L);
System.out.println(em.contains(managed)); // true

em.detach(managed);
System.out.println(em.contains(managed)); // false

Customer loadedAgain = em.find(Customer.class, 10L);
System.out.println(managed == loadedAgain); // Thường false.
```

`detach(entity)` chỉ gỡ entity được chỉ định, trừ các mối quan hệ được cấu hình cascade detach. Những entity khác còn managed có thể vẫn nằm trong L1.

Một entity detached vẫn là Java object chứa dữ liệu đã được load, nhưng:

- Thay đổi field của detached entity không tự được Hibernate dirty-check trong context cũ.
- Lazy field/association chưa initialized có thể không dùng được ngoài session.
- Cùng persistent ID có thể được load thành một object managed khác trong context.
- Khi cần đồng bộ state detached, dùng `merge()` có chủ đích; không nhầm với `persist()` cho entity mới.

## 15. `merge()` sao chép state, không đưa chính object cũ trở lại context

```java
Customer detached;

try (EntityManager em1 = emf.createEntityManager()) {
    detached = em1.find(Customer.class, 10L);
}

detached.rename("Changed Outside Session");

EntityManager em2 = emf.createEntityManager();
var tx = em2.getTransaction();

try {
    tx.begin();

    Customer managed = em2.merge(detached);

    System.out.println(em2.contains(detached)); // false
    System.out.println(em2.contains(managed));  // true

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) tx.rollback();
    throw ex;
} finally {
    em2.close();
}
```

`merge()` tìm hoặc tạo managed representation cùng persistent identity và **sao chép trạng thái** từ detached object sang managed instance. Nó có thể cần đọc database hoặc tận dụng một entity đã có trong context; thời điểm và số SQL phụ thuộc state, version, cascading và mapping.

Nếu `em2` đã có `Customer#10` trong L1 trước khi merge, Hibernate phải duy trì một managed representation cho ID đó; không thể đơn giản đưa thêm detached object vào làm **managed instance thứ hai**.

### 15.1. Merge không giải quyết sự cũ của dữ liệu một cách tự động

Detached object có thể chứa state cũ. Khi merge, state đó có thể ghi đè managed state mới nếu không có cơ chế concurrency/validation phù hợp. Dùng `@Version` và optimistic locking khi cần ngăn lost update; hoặc trong API patch, tải entity managed hiện tại và áp dụng **các field được phép đổi** thay vì merge một snapshot cũ toàn bộ.

## 16. Flush mode: vì sao SQL có thể xuất hiện trước query?

Mặc định trong JPA, flush mode thường là `AUTO`. Theo đặc tả, provider phải đảm bảo các thay đổi pending có thể ảnh hưởng kết quả query được xử lý phù hợp. Hibernate có thể flush các thay đổi trước khi chạy JPQL/HQL query.

Ví dụ:

```java
var tx = em.getTransaction();
tx.begin();

Customer customer = em.find(Customer.class, 10L);
customer.rename("Alice Updated");

List<Customer> result = em.createQuery(
    "select c from Customer c where c.displayName = :name",
    Customer.class
)
.setParameter("name", "Alice Updated")
.getResultList();

tx.commit();
```

Timeline có thể là:

```text
SELECT Customer#10
Java đổi displayName
AUTO flush trước truy vấn có liên quan:
    UPDATE customers SET display_name = ...
JPQL query:
    SELECT ... WHERE display_name = 'Alice Updated'
```

**SQL UPDATE xuất hiện trước SELECT mới** không có nghĩa L1 cache không hoạt động. `flush()` và việc thực thi query là hai phần riêng của unit-of-work management.

### 16.1. `FlushModeType.COMMIT`

```java
em.setFlushMode(jakarta.persistence.FlushModeType.COMMIT);
```

Với chế độ này, việc đồng bộ pending changes thường được trì hoãn tới commit hoặc explicit flush. Đặc tả không bảo đảm kết quả của mọi query giữa transaction sẽ phản ánh những thay đổi chưa flush theo cùng cách như `AUTO`.

Không dùng COMMIT flush mode chỉ để giảm SQL khi chưa hiểu hậu quả đối với tính nhất quán các truy vấn trong cùng transaction.

### 16.2. `flush()` không xóa L1 cache

```java
Customer a = em.find(Customer.class, 10L);
a.rename("Updated");
em.flush();

Customer b = em.find(Customer.class, 10L);
System.out.println(a == b); // true khi vẫn cùng context.
```

`flush()` gửi thay đổi xuống DB nhưng **không detach** entity. Do đó `find()` sau flush vẫn có thể trả cùng object mà không SELECT lại.

## 17. Bulk update/native SQL có thể làm L1 cache bị stale

Xét:

```java
Customer customer = em.find(Customer.class, 10L);

em.createQuery(
    "update Customer c set c.displayName = :name where c.id = :id"
)
.setParameter("name", "Updated by bulk query")
.setParameter("id", 10L)
.executeUpdate();

System.out.println(customer.getDisplayName());
```

Bulk JPQL update không cập nhật từng managed instance như khi gọi setter rồi dirty checking. Vì vậy `customer` có thể vẫn giữ **giá trị cũ trong L1** sau khi bulk query đã thay đổi database.

Tương tự:

```java
em.createNativeQuery(
    "update customers set display_name = :name where id = :id"
)
.setParameter("name", "Updated by SQL")
.setParameter("id", 10L)
.executeUpdate();
```

không biến thành `customer.rename(...)` trong persistence context.

Một cách xử lý có chủ đích:

```java
em.refresh(customer);
```

hoặc nếu cần làm mới toàn bộ context:

```java
em.clear();
Customer fresh = em.find(Customer.class, 10L);
```

Nhưng phải xử lý **pending changes trước khi `clear()`**, và phải xét transaction isolation. Không gọi `clear()` bừa bãi sau bulk mutation nếu có entity khác đang sửa chưa flush.

### 17.1. Bulk delete cũng đi ngoài entity lifecycle thông thường

```java
em.createQuery(
    "delete from Customer c where c.id = :id"
)
.setParameter("id", 10L)
.executeUpdate();
```

Có thể xóa hàng khỏi DB trong khi context vẫn giữ một entity Java đã load cùng ID. `em.find(Customer.class, 10L)` trong context đó không nhất thiết là phép xác nhận hàng còn tồn tại; muốn biết trạng thái thực cần xử lý L1 và transaction visibility cho đúng.

Với entity có associations, bulk delete còn có thể bỏ qua một số cơ chế cascade/lifecycle và gặp FK constraint; vấn đề này không được giải quyết bằng first-level cache.

## 18. L1 cache không thay thế transaction isolation

Một persistence context giữ object nhưng database vẫn quyết định:

- Những thay đổi từ transaction khác có thể thấy ở thời điểm nào.
- Lock và version có cần kiểm tra không.
- Một `SELECT FOR UPDATE` có lấy lock hay phải chờ không.
- Các ràng buộc PK/FK/UNIQUE có hợp lệ khi commit không.

Vì vậy đừng nhầm ba loại “nhất quán”:

| Tầng | Điều được bảo đảm | Điều không được bảo đảm |
| --- | --- | --- |
| Identity map | Một managed representation cho mỗi persistent identity trong một context | Dữ liệu luôn là version mới nhất ở DB |
| Transaction isolation | Quy tắc hiển thị dữ liệu giữa transactions | Object Java tự refresh sau external update |
| Optimistic locking (`@Version`) | Phát hiện một số xung đột update/delete | Mọi `find()` đều phải SELECT, hoặc không có stale reads |

Ví dụ hai request A/B cùng đọc bản ghi, B commit thay đổi, A tiếp tục gọi `find()`:

```text
Session A                 Database                  Session B
  |                          |                         |
  | find #10                 |                         |
  |--- SELECT -------------->|                         |
  |<-- "Alice" --------------|                         |
  |                          |       update #10        |
  |                          |<------------------------|
  |                          |------ COMMIT ---------->|
  | find #10 lần nữa         |                         |
  | trả từ L1: "Alice"       |                         |
  | (không SELECT mới)       |                         |
```

Việc hiển thị dữ liệu mới cần `refresh`/context mới và transaction visibility phù hợp. Nếu A ghi lại object cũ, dùng optimistic locking hoặc strategy concurrency tương ứng để tránh mất cập nhật.

## 19. Scope của persistence context trong Java SE và Spring

### 19.1. EntityManager application-managed

```java
EntityManager em = emf.createEntityManager();
// ... sử dụng ...
em.close();
```

Với `EntityManager` do ứng dụng tự tạo, persistence context thường gắn với vòng đời `em`. Commit một transaction **không mặc nhiên đóng `em`** nếu bạn vẫn giữ nó mở; các entity có thể tiếp tục managed cho tới khi `close()`, `clear()` hoặc `detach()`.

```java
EntityManager em = emf.createEntityManager();

var tx1 = em.getTransaction();
tx1.begin();
Customer a = em.find(Customer.class, 10L);
tx1.commit();

// Nếu em vẫn mở và a vẫn managed:
Customer b = em.find(Customer.class, 10L);
System.out.println(a == b); // true

em.close();
```

Không nên giữ application-managed `EntityManager` quá lâu chỉ để tăng hit rate, vì nó tích lũy object/snapshot và có thể mang dữ liệu cũ.

### 19.2. Transaction-scoped persistence context

Trong Spring Data JPA với `JpaTransactionManager`/container JPA transaction scope điển hình, persistence context gắn với **transaction hoặc phạm vi quản lý tương ứng**. Hai request hay hai transaction độc lập thường có contexts khác nhau.

Ví dụ:

```java
@Service
public class CustomerService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public CustomerDto loadTwice(Long id) {
        Customer a = em.find(Customer.class, id);
        Customer b = em.find(Customer.class, id);

        return new CustomerDto(
            a.getId(),
            b.getDisplayName(),
            a == b
        );
    }
}
```

`@PersistenceContext`, `@Transactional` và `@Service` cần Spring/Jakarta imports; `CustomerDto` là DTO của ứng dụng (ví dụ `record CustomerDto(Long id, String name, boolean sameInstance) {}`). Mục đích là cho thấy hai `find()` **trong một transaction/context** có thể reuse object.

**Không mặc định mỗi method của service đều có context độc lập** nếu dùng Open-EntityManager-in-View, extended persistence context hoặc transaction propagation. Scope thực tế do framework và cấu hình quyết định.

### 19.3. Open Session In View

Một số web framework có thể giữ Hibernate Session/EntityManager sống xuyên phần render response. Điều này cho phép lazy loading muộn nhưng cũng có thể khiến context giữ object lâu hơn và phát SQL ngoài transaction nghiệp vụ mong muốn.

Không dùng Open Session In View chỉ nhằm “tận dụng L1 cache giữa controller và view”; ưu tiên xác định dữ liệu cần fetch trong service rồi trả DTO phù hợp.

## 20. Mối liên hệ với Hibernate Session và StatelessSession

`EntityManager` là API chuẩn Jakarta Persistence. Hibernate `Session` cung cấp thêm API, nhưng cả hai trong mô hình stateful đều dùng persistence context và L1 cache.

```java
org.hibernate.Session session =
    em.unwrap(org.hibernate.Session.class);

Customer first = session.get(Customer.class, 10L);
Customer second = session.get(Customer.class, 10L);
```

Thông thường hai lần `get()` theo cùng ID trong cùng `Session` sẽ reuse managed representation.

Ngược lại, Hibernate còn có **`StatelessSession`** dành cho các luồng xử lý stateless đặc biệt. Nó **không cung cấp persistence context/L1 cache và dirty checking giống stateful Session**. Vì thế không áp dụng trực tiếp các giả định của bài (`find` cùng instance, entity managed, auto flush…) cho `StatelessSession`.

Đây là khác biệt về **mô hình API**, không phải tùy chọn cấu hình để “tắt cache cấp một” của một `EntityManager` thông thường.

## 21. Tránh để persistence context phình to

L1 cache đem lại lợi ích nhưng cũng chiếm bộ nhớ vì Hibernate giữ managed entities và thông tin phục vụ quản lý trạng thái. Một batch import dài có thể load/persist hàng trăm nghìn object vào **một** context:

```java
for (int i = 0; i < 100_000; i++) {
    em.persist(new Customer(
        "user-" + i + "@example.org",
        "User " + i
    ));
}
```

Nếu giữ context tới cuối, bộ nhớ và chi phí flush có thể tăng đáng kể. Kỹ thuật thường dùng trong batch có kiểm soát:

```java
int batchSize = 50;

for (int i = 0; i < customers.size(); i++) {
    em.persist(customers.get(i));

    if ((i + 1) % batchSize == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
```

Ví dụ giả định toàn bộ vòng lặp nằm trong transaction phù hợp, `customers` chứa entity mới và đã có chính sách error handling. `flush()` đồng bộ INSERT pending; `clear()` giải phóng managed references trong context, **không commit** transaction.

Nếu mã bên ngoài vẫn giữ các references đã detach và sửa tiếp sau clear, Hibernate sẽ không tự nhận những thay đổi đó. Batch processing phải quản lý **identity/state và error recovery** rõ ràng.

### 21.1. Clear theo batch không phải “cache tuning” vô hại

`clear()` có thể làm mất dirty changes chưa flush, detach những entity mà code phía sau vẫn nghĩ là managed và thay đổi cách cascade thực hiện. Cần hiểu việc giải phóng bộ nhớ là đổi lifecycle; không chỉ là “dọn cache cho nhẹ”.

## 22. Kiểm chứng SQL thay vì suy đoán

Để hiểu L1 cache, hãy quan sát **hai thứ riêng**:

1. **Java reference identity:** `first == second`.
2. **JDBC/SQL thực tế:** log statement hoặc đo statistics.

### 22.1. Bật log SQL cho môi trường học/test

Ví dụ cấu hình Hibernate:

```properties
hibernate.show_sql=true
hibernate.format_sql=true
hibernate.highlight_sql=false
```

`show_sql` thuận tiện lúc học, nhưng trong ứng dụng thật nên dùng logger có cấu hình, bảo đảm không log giá trị nhạy cảm.

Ở Hibernate 6/7, có thể bật logger:

```properties
# Ví dụ minh họa tên logger (cú pháp tùy hệ thống logging):
org.hibernate.SQL=DEBUG
```

Nếu dự án sử dụng Spring Boot với Logback/Log4j, property logging tương ứng có dạng:

```properties
logging.level.org.hibernate.SQL=DEBUG
```

Không bật bind parameter logging ở production mà không có chính sách bảo mật: nó có thể chứa email, token, dữ liệu cá nhân hoặc số tiền.

### 22.2. Mẫu log kỳ vọng

Với dữ liệu đã có và **không có L2 cache hit**, quan hệ eager hay các tác động SQL khác:

```java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);
Customer c = em.find(Customer.class, 20L);
```

Có thể thấy:

```sql
select ... from customers where id = 10;
select ... from customers where id = 20;
```

**Không có câu SELECT thứ hai cho id=10** vì lần tìm thứ hai reuse managed instance. Đây chỉ là **mẫu kỳ vọng**, không phải log đã thực thi.

### 22.3. Hibernate Statistics

Trong kiểm thử chuyên sâu, Hibernate có API Statistics và property:

```properties
hibernate.generate_statistics=true
```

Ví dụ truy cập:

```java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sessionFactory.getStatistics();

stats.clear();

Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 10L);

System.out.println(stats.getEntityLoadCount());
System.out.println(stats.getPrepareStatementCount());
```

Các số đếm là **toàn SessionFactory** và có thể chịu ảnh hưởng từ các test/thread khác, eager associations, schema bootstrap, L2 cache và câu SQL khác. `stats.clear()` trong môi trường chạy thật có thể ảnh hưởng monitoring toàn ứng dụng; chỉ sử dụng có kiểm soát ở test hoặc công cụ đo.

Một test đáng tin cậy nên:

- Dùng database test đã seed dữ liệu.
- Cô lập các thao tác của test; tắt hoặc kiểm soát L2/query cache.
- Dùng một `EntityManager` mới và scope rõ ràng.
- Đếm SELECT qua logging/SQL inspector nếu cần phân biệt SELECT và các statement khác.
- So sánh cả `a == b` để chứng minh identity map.

Không chỉ nhìn mỗi `prepareStatementCount` và kết luận tất cả statement là SELECT.

## 23. Integration test: đọc cùng ID hai lần trong một context

Đây là kịch bản test khái niệm với JUnit 5. Giả định `emf` được tạo trong test fixture và database có `Customer#10`:

```java
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FirstLevelCacheTest {

    private final EntityManagerFactory emf;

    FirstLevelCacheTest(EntityManagerFactory emf) {
        // Test fixture/extension phải cấp emf.
        this.emf = emf;
    }

    @Test
    void samePersistenceContextReusesManagedInstance() {
        try (EntityManager em = emf.createEntityManager()) {
            Customer first = em.find(Customer.class, 10L);
            Customer second = em.find(Customer.class, 10L);

            assertNotNull(first);
            assertSame(first, second);
            assertTrue(em.contains(first));
        }
    }
}
```

**Chú ý:** JUnit 5 thông thường không tự inject `EntityManagerFactory` vào constructor như trên. Đây là **phần body test cần tích hợp vào fixture** (chẳng hạn `@BeforeAll` bootstrap, Spring test context hoặc JUnit extension). Không copy class này vào project rồi mong tự chạy nếu chưa cung cấp `emf`.

Nếu muốn fixture JPA resource-local đơn giản:

```java
static EntityManagerFactory emf;

@BeforeAll
static void setup() {
    emf = Persistence.createEntityManagerFactory("hibernate-test");
}

@AfterAll
static void teardown() {
    if (emf != null) {
        emf.close();
    }
}
```

Cần thêm import `jakarta.persistence.Persistence`, annotation JUnit, `META-INF/persistence.xml` và cấu hình database/test data phù hợp. Phần này chỉ minh họa nguyên tắc test; việc dựng DB thực tế phụ thuộc project.

### 23.1. Test sau `clear()`

```java
@Test
void clearingContextProducesDifferentManagedInstance() {
    try (EntityManager em = emf.createEntityManager()) {
        Customer first = em.find(Customer.class, 10L);
        assertNotNull(first);

        em.clear();

        Customer second = em.find(Customer.class, 10L);
        assertNotNull(second);

        assertNotSame(first, second);
        assertFalse(em.contains(first));
        assertTrue(em.contains(second));
    }
}
```

Hai object có thể có cùng ID nhưng không còn cùng reference. Test này thể hiện **scope của identity map**; nó không khẳng định `find()` thứ hai bắt buộc phát SQL nếu L2 cache đang hoạt động.

### 23.2. Test hai context

```java
@Test
void twoEntityManagersHaveDifferentManagedInstances() {
    try (EntityManager firstEm = emf.createEntityManager();
         EntityManager secondEm = emf.createEntityManager()) {

        Customer first = firstEm.find(Customer.class, 10L);
        Customer second = secondEm.find(Customer.class, 10L);

        assertNotNull(first);
        assertNotNull(second);
        assertNotSame(first, second);
        assertEquals(first.getId(), second.getId());
    }
}
```

Kết quả là hai instances khác Java reference, cùng persistent identity. Nếu project tự override `equals()`, kết quả `equals()` sẽ theo hợp đồng của entity, không phải do persistence context chung.

## 24. Thử nghiệm refresh sau thay đổi bên ngoài

Kịch bản kiểm thử có hai `EntityManager` và transaction riêng:

```text
1. EM A tải Customer#10, displayName="Alice".
2. EM B bắt đầu transaction; đổi thành "Alice B"; commit.
3. EM A gọi find(Customer#10) lần nữa.
   → trả cùng instance; có thể vẫn là "Alice".
4. EM A refresh(customer).
   → nạp lại dữ liệu DB theo transaction isolation.
5. Quan sát displayName sau refresh.
```

Giải thích kết quả phải xét:

- **A có đang trong transaction dài không?** Isolation có thể giữ snapshot dữ liệu cũ.
- **L2 cache có bật không?** Refresh có cơ chế tương tác với cache tùy provider.
- **B update bằng entity hay bulk SQL?** Bulk SQL có thể không đồng bộ cache theo cùng cách.
- **Có entity version?** Nó ảnh hưởng optimistic locking, không tự làm `find()` là reload.
- **Có pending changes trong A?** `refresh()` ghi đè state pending của entity.

Đây là **thí nghiệm cần chạy trong DB cụ thể**, không phải kết quả cố định cho mọi DBMS/isolation level.

## 25. First-level cache và “read-your-writes” trong một context

Một đặc tính quan trọng là ứng dụng có thể đọc lại state Java vừa sửa mà **không cần commit**:

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("Local Change");

Customer second = em.find(Customer.class, 10L);

assertSame(customer, second);
assertEquals("Local Change", second.getDisplayName());
```

Đó là **read-your-own-managed-state**, không đồng nghĩa database đã có giá trị `"Local Change"`.

Nếu muốn kiểm tra DB thực tế, có thể explicit `flush()` rồi đọc trong transaction theo cách thích hợp; nhưng `flush()` không làm commit, nên transaction khác có thể chưa thấy thay đổi. Với `FlushMode.AUTO`, JPQL query cũng có thể kích hoạt flush; đây là lý do không nên suy rằng việc một query trả kết quả mới luôn có nghĩa L1 cache đã được refresh.

## 26. Vì sao L1 không phải cơ chế làm dữ liệu “mới nhất”?

Persistence context giữ **một phiên bản trạng thái managed** theo thời điểm và những thay đổi Java đã áp dụng. Không có cơ chế tự động hỏi DB mỗi lần bạn đọc getter hay `find()` cùng identity.

Sơ đồ:

```text
Database: Customer#10 = "Alice"
                    |
                    | SELECT
                    v
L1 / Managed object: "Alice"
                    |
                    | Bên khác commit "Bob"
                    v
Database: Customer#10 = "Bob"

L1 / Managed object vẫn: "Alice"
                    |
                    | find(Customer, 10)
                    v
Trả "Alice" (không buộc reload)
```

Cần xác định một **freshness policy** theo use case:

- Màn hình chi tiết chấp nhận dữ liệu tại thời điểm request: thường mở context theo request/transaction, trả DTO, đóng context.
- Tác vụ cần xác nhận trạng thái mới ngay trước thao tác: cân nhắc reload/refresh/lock/version trong transaction thích hợp.
- Dữ liệu tham chiếu ít đổi: có thể bổ sung L2 cache với chiến lược invalidation rõ ràng.
- Báo cáo aggregate: không trông chờ L1; dùng truy vấn/reporting model phù hợp.
- Tác vụ ghi đồng thời: dùng optimistic/pessimistic locking và business invariant, không chỉ `find()` lặp lại.

L1 cache tối ưu **vòng đời quản lý entity**, không phải giải pháp consistency cho cả hệ thống phân tán.

## 27. Các câu hỏi và hiểu nhầm thường gặp

### “Hai lần `find()` cùng ID luôn gửi hai SQL vì hai lần gọi API”

Sai. Trong cùng persistence context, lần thứ hai có thể trả cùng managed instance mà không SELECT.

### “Nếu SQL không xuất hiện thì chắc chắn là L2 cache”

Sai. Thông thường nguyên nhân đầu tiên cần xét là **L1 cache**; `@Cacheable` không cần thiết cho trường hợp lookup trong cùng session.

### “Mở EntityManager mới nhưng L2 cache bật thì vẫn cùng Java object”

Không. Hai context độc lập quản lý các instances riêng, dù dữ liệu có thể được lấy từ L2 mà không SELECT.

### “Cùng ID ở hai entity types nghĩa là cùng entry L1”

Không. Persistent identity bao gồm entity type và primary key, không chỉ giá trị số ID.

### “Query JPQL trả một entity đang managed nên không có SQL”

Không nhất thiết. JPQL query vẫn thường cần SQL để tìm **tập kết quả**; trong bước materialize, Hibernate tái sử dụng managed instance theo ID.

### “`find()` sau khi code đổi field phải đọc DB mới thấy thay đổi”

Sai. Entity managed là cùng Java object, nên state vừa đổi đã hiện diện trong context trước flush.

### “`flush()` xóa cache cấp một”

Không. `flush()` đồng bộ pending changes, không detach entity; lần `find()` sau vẫn có thể reuse instance.

### “`clear()` xóa tất cả hàng đã load khỏi database”

Không. Nó detach toàn bộ managed entities khỏi persistence context; dữ liệu DB không bị xóa vì `clear()`.

### “`refresh()` không làm mất thay đổi pending”

Sai. Nó có thể ghi đè các field đã sửa nhưng chưa flush bằng state database. Chỉ dùng khi muốn thật sự reload.

### “`getReference()` không SELECT nên chắc chắn hàng tồn tại”

Sai. Có thể là proxy chưa kiểm tra tồn tại; lỗi xuất hiện lúc initialize hoặc khi DB kiểm tra FK.

### “Đổi dữ liệu bằng native SQL thì object managed tự đổi theo”

Sai. Native/bulk SQL có thể bỏ qua state trong persistence context. Cần refresh/clear theo kế hoạch.

### “Cache cấp một đảm bảo đọc mới nhất giữa mọi transaction”

Không. Nó chỉ bảo đảm identity/state trong **một context**. Cập nhật từ transaction khác không tự refresh object đã load.

### “Cứ giữ Session mở càng lâu thì hiệu năng càng tốt”

Không. Session dài có thể tích lũy nhiều managed objects, snapshot và stale data; đồng thời tạo rủi ro quản lý lifecycle/concurrency. Thường nên giới hạn theo unit of work/transaction.

## 28. Bài tập vận dụng

### Bài 1 — Hai lần `find()`

```java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);
```

Trong cùng context, entity chưa bị detach. Có nhất thiết hai SELECT không?

**Trả lời:** Không. `b` có thể chính là `a` (`a == b`), và lookup lần hai được phục vụ từ L1 cache.

### Bài 2 — JPQL sau `find()`

```java
Customer a = em.find(Customer.class, 10L);
Customer b = em.createQuery(
    "select c from Customer c where c.id = :id",
    Customer.class
).setParameter("id", 10L).getSingleResult();
```

Có thể vừa thấy `a == b`, vừa thấy một SQL SELECT ở query JPQL không?

**Trả lời:** Có. SQL dùng để giải quyết query, còn entity trả về được identity-map resolve thành managed instance `a`.

### Bài 3 — State chưa flush

Sau khi `customer.rename("New")`, gọi `find()` cùng ID vẫn trả `"New"` dù chưa commit. Vì sao?

**Trả lời:** Do cùng managed object trong persistence context. `find()` không tự thực hiện reload từ DB.

### Bài 4 — Hai context

Cùng `Customer#10` được load bởi hai `EntityManager` độc lập. L1 cache có khiến hai object cùng reference không?

**Trả lời:** Không. Mỗi EntityManager có persistence context riêng. Nếu L2 không bật thì có thể thấy mỗi context nạp DB một lần; nếu L2 bật thì SQL count có thể khác nhưng Java reference vẫn riêng.

### Bài 5 — `clear()`

```java
Customer a = em.find(Customer.class, 10L);
em.clear();
Customer b = em.find(Customer.class, 10L);
```

Mối liên hệ của `a` và `b` là gì?

**Trả lời:** `a` đã detached, `b` là managed representation mới trong context; thường `a != b` về reference dù cùng persistent ID.

### Bài 6 — `refresh()`

`customer` được sửa trong Java nhưng chưa flush. Gọi `em.refresh(customer)` sẽ làm gì?

**Trả lời:** Đọc lại state của managed entity từ database theo transaction visibility, có thể **ghi đè thay đổi chưa flush**.

### Bài 7 — Bulk SQL

SQL cập nhật row `Customer#10` nhưng `customer` managed đã load trước vẫn giữ tên cũ. L1 có lỗi không?

**Trả lời:** Không. Bulk/native SQL không nhất thiết cập nhật object managed. Cần chủ động đồng bộ lại state bằng refresh/clear hoặc giới hạn scope context.

### Bài 8 — `getReference`

`getReference(Customer.class, 999L)` trả một object mà chưa SQL. Điều này có chứng minh `Customer#999` tồn tại không?

**Trả lời:** Không. Provider có thể trì hoãn kiểm tra tới lúc initialize reference; lúc đó có thể gặp `EntityNotFoundException`.

### Bài 9 — N+1

Một query tải 100 `PurchaseOrder`. Lặp qua 100 collections `lines` LAZY phát 100 SQL. Tại sao L1 không tránh được?

**Trả lời:** Mỗi collection chưa initialized có thể cần query riêng. L1 không tự biến tất cả lazy collection misses thành một query; cần batch fetching, fetch plan/DTO thích hợp.

### Bài 10 — Batch import

`EntityManager` giữ 100.000 entity sau nhiều lần persist. Làm thế nào giảm memory footprint?

**Trả lời:** Thực hiện theo batch, `flush()` rồi `clear()` ở các mốc phù hợp, và hiểu rằng entity đã clear trở thành detached. Kiểm soát transaction, generated ID và error recovery.

## 29. Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 — `EntityManager`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/EntityManager.html): persistence context, identity, lifecycle, `find`, `getReference`, `refresh`, `clear`, `detach`, `merge`, `flush`.
- [Jakarta Persistence 3.2 — Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): quản lý identity, trạng thái managed/detached, semantics của query và transaction-scoped context.
- [Hibernate ORM 7.2 — User Guide, Persistence Context](https://docs.hibernate.org/orm/7.2/userguide/html_single/#pc): trạng thái entity, dirty checking, flushing và thao tác trên persistence context.
- [Hibernate ORM 7.2 — Caching](https://docs.hibernate.org/orm/7.2/userguide/html_single/#caching): first-level, second-level và query cache trong Hibernate.
- [Hibernate ORM 7.2 — Flushing](https://docs.hibernate.org/orm/7.2/userguide/html_single/#flushing): AUTO/COMMIT flush, synchronization trước query và commit.
- [Hibernate ORM 7.2 — Fetching](https://docs.hibernate.org/orm/7.2/userguide/html_single/#fetching): LAZY, JOIN FETCH, batch fetching và N+1.
- [Hibernate ORM Javadoc — `Session`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html): stateful session, persistent identity, `get`, `refresh`, `clear`, `detach`.
- [Hibernate ORM Javadoc — `StatelessSession`](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/StatelessSession.html): sự khác biệt giữa stateless processing và stateful session.

Khi làm dự án thực, hãy ưu tiên user guide/Javadoc của **đúng phiên bản Hibernate** đang dùng. Các ví dụ SQL và thời điểm flush là mô hình để giải thích, không phải số câu SQL đã đo trong một cấu hình cụ thể.

## Kết luận

**Persistence context là bộ nhớ đệm cấp một và identity map của Hibernate.** Khi một entity đã managed trong context, các lần tra cứu tiếp theo theo cùng persistent identity thông thường sẽ nhận **cùng Java instance**, thay vì bắt buộc truy vấn database lại. Bởi vậy `find()` lặp lại có thể không phát SQL mới, và state vừa sửa trong Java có thể nhìn thấy ngay dù chưa `flush()`.

Nhưng L1 cache chỉ có hiệu lực trong **phạm vi một persistence context**. JPQL, query aggregate, lazy associations, flush, lock hoặc refresh có thể vẫn phát SQL; hai `EntityManager` độc lập có L1 khác nhau; bulk/native SQL và cập nhật từ transaction khác có thể khiến managed state cũ. Dùng `refresh()`, `detach()`, `clear()`, scope transaction và optimistic locking một cách có chủ đích, đồng thời quan sát log/Statistics thực tế để hiểu chính xác **khi nào Hibernate tái sử dụng object, khi nào cần đọc DB và khi nào cần đồng bộ state**.
