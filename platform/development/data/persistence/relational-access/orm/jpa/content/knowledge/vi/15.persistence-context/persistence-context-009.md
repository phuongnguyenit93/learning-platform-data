# Phân biệt phạm vi persistence context và phạm vi giao dịch

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Persistence Context

Trong ứng dụng sử dụng JPA, hai khái niệm rất dễ bị đánh đồng là **persistence context** và **transaction**. Một bên quản lý **trạng thái các đối tượng entity trong bộ nhớ**, còn bên kia quyết định **ranh giới xác nhận hoặc hủy bỏ những thao tác với dữ liệu**.

Ví dụ, một đoạn code có thể đang giữ một đối tượng `Customer` ở trạng thái *managed* nhưng **không có giao dịch database nào đang mở**. Ngược lại, một transaction có thể kết thúc trong khi một `EntityManager` application-managed vẫn còn mở và tiếp tục giữ các entity được quản lý. Trong môi trường container-managed transaction-scoped, persistence context thường kết thúc cùng transaction; nhưng đó là **một cấu hình vòng đời cụ thể**, không phải định nghĩa cho tất cả persistence context của JPA.

Hiểu sự khác biệt này giúp giải thích những hiện tượng thường gặp:

- Vì sao gọi `em.find()` hai lần có thể trả về đúng **cùng một object Java**?
- Vì sao đã sửa field của managed entity nhưng database chưa thay đổi?
- Vì sao `flush()` đã phát SQL mà `rollback()` vẫn hủy được thay đổi?
- Vì sao sau khi đóng `EntityManager`, truy cập association lazy có thể thất bại?
- Vì sao cùng một entity sau hai request có thể là hai Java object khác nhau?
- Vì sao một `EntityManager` dùng qua nhiều transaction có thể giữ dữ liệu cũ?
- Vì sao `@Transactional` trong Spring không đồng nghĩa với `@PersistenceContext(type = EXTENDED)`?

Bài này xây dựng một mô hình tư duy thống nhất để phân biệt **phạm vi persistence context** (*persistence-context scope*) và **phạm vi giao dịch** (*transaction scope*), sau đó xem các kiểu EntityManager, JTA, RESOURCE_LOCAL, Spring và những tình huống thực hành.

---

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Định nghĩa persistence context, transaction và EntityManager mà không coi chúng là cùng một đối tượng.
2. Phân biệt *first-level cache*, identity map, managed entity và trạng thái detached.
3. Mô tả lúc nào một entity được quản lý, lúc nào bị detach và điều gì khiến một thay đổi được ghi vào database.
4. Phân biệt **transaction-scoped persistence context** và **extended persistence context** trong môi trường container-managed.
5. Giải thích vì sao **application-managed EntityManager** có persistence context kéo dài theo vòng đời của chính EntityManager, có thể vượt qua nhiều transaction.
6. Hiểu các mốc `persist()`, `find()`, `flush()`, `commit()` và `rollback()`.
7. Phân biệt việc tham gia JTA transaction với thời gian tồn tại của persistence context; biết vai trò của `joinTransaction()` khi cần.
8. Diễn giải thông dụng của Spring `@PersistenceContext`, `@Transactional` và Open EntityManager in View (OSIV).
9. Nhận biết các vấn đề khi dùng context quá dài: dữ liệu cũ, memory growth, concurrency, lazy loading và optimistic locking.
10. Chọn ranh giới thích hợp cho một use case và quan sát hành vi bằng code JPA.

## 2. Ba khái niệm, ba trách nhiệm

| Khái niệm | Trách nhiệm chính | Phạm vi/vòng đời do ai quyết định? |
|---|---|---|
| **Persistence context** | Theo dõi các entity managed, bảo đảm identity trong phạm vi context, phát hiện thay đổi, quản lý trạng thái cần đồng bộ | EntityManager, container hoặc framework tùy loại context |
| **EntityManager** | API tương tác với persistence context: `persist`, `find`, `merge`, `remove`, `flush`, truy vấn | Application tạo/đóng hoặc container/framework cấp proxy và quản lý |
| **Transaction** | Gom các thao tác thành một đơn vị commit/rollback; phối hợp ranh giới ACID với resource database | `EntityTransaction`, JTA transaction manager, Spring transaction manager... |

Không nên diễn đạt “EntityManager là transaction”. EntityManager là giao diện quản lý entity; transaction là ranh giới xác nhận tính bền vững. Chúng phối hợp nhưng có hai vòng đời khác nhau.

### 2.1. Persistence context là gì?

Persistence context là tập hợp các **entity instance đang được quản lý** bởi JPA provider, gắn với một `EntityManager`/ngữ cảnh quản lý thích hợp. Trong một persistence context, một entity identity tương ứng với **một managed Java entity instance** theo quy tắc JPA.

Sơ đồ:

```text
Persistence Context A
  |
  +-- Customer(id=10) ---> object Java #A10
  +-- Customer(id=20) ---> object Java #A20
  +-- Order(id=50)    ---> object Java #A50

Persistence Context B
  |
  +-- Customer(id=10) ---> object Java #B10

Cùng hàng Customer#10 trong database
  nhưng hai persistence context có thể có
  hai instance Java khác nhau: #A10 và #B10.
```

Nhiều tài liệu gọi persistence context là **first-level cache** của ORM. Tên gọi này hữu ích nhưng chưa đầy đủ: context không chỉ lưu entity đã tìm, mà còn theo dõi trạng thái thay đổi, chuẩn bị thao tác insert/update/delete, quản lý quan hệ và thực hiện các quy tắc của entity lifecycle.

### 2.2. Transaction là gì?

Transaction là đơn vị công việc được xác nhận hoặc hủy bỏ cùng nhau theo khả năng của database và transaction manager. Ví dụ một yêu cầu “chuyển tiền từ tài khoản A sang B” cần hai thay đổi cùng thành công, nếu không thì rollback.

```text
BEGIN TRANSACTION
  UPDATE accounts SET balance = ... WHERE id = A
  UPDATE accounts SET balance = ... WHERE id = B
COMMIT

Hoặc khi lỗi:
ROLLBACK
```

Transaction không định nghĩa object Java nào thuộc first-level cache. Điều đó thuộc persistence context. Một transaction có thể làm việc với các managed entity nhưng không biến bản thân transaction thành kho chứa identity map.

### 2.3. Hai trục độc lập

Cần trả lời **hai câu hỏi riêng**:

- **Trục A — Context:** đối tượng nào đang managed? Context được mở lúc nào và đóng lúc nào? Object có còn được theo dõi sau thao tác không?
- **Trục B — Transaction:** những SQL nào thuộc một transaction? Transaction có active không? Thay đổi đã commit hay bị rollback?

```text
Context:
  [----------- managed objects / identity map -----------]

Transaction:
       [----- TX #1 -----]     [----- TX #2 -----]

Có thể context rộng hơn nhiều transaction.
Cũng có thể một context riêng được tạo cho mỗi transaction.
```

Chính cấu hình scope cụ thể quyết định hai khoảng thời gian này có trùng nhau không.

---

## 3. Ví dụ đầu tiên: một persistence context giữ identity

Giả sử có entity `Customer`:

```java
package demo.domain;

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

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    protected Customer() {
        // JPA
    }

    public Customer(String displayName) {
        rename(displayName);
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String newDisplayName) {
        Objects.requireNonNull(newDisplayName, "displayName");

        String normalized = newDisplayName.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                "Customer name must not be blank");
        }
        this.displayName = normalized;
    }
}
```

Nếu entity `Customer#10` đã tồn tại và được đọc hai lần trong **cùng persistence context**, thì:

```java
Customer first = em.find(Customer.class, 10L);
Customer second = em.find(Customer.class, 10L);

System.out.println(first == second); // true trong cùng context.
```

Dấu `==` so sánh **đúng cùng Java instance**, không phải `equals()` do ứng dụng tự định nghĩa. Đây là bảo đảm identity của persistence context cho một entity identity.

### 3.1. Nhưng mở hai EntityManager khác nhau thì sao?

```java
EntityManager em1 = emf.createEntityManager();
EntityManager em2 = emf.createEntityManager();

try {
    Customer inFirstContext = em1.find(Customer.class, 10L);
    Customer inSecondContext = em2.find(Customer.class, 10L);

    System.out.println(inFirstContext == inSecondContext);
    // Thường false: hai context có hai Java instance riêng.
} finally {
    em1.close();
    em2.close();
}
```

Điều này **không có nghĩa** database có hai hàng Customer#10. Hai instance cùng biểu diễn một database identity nhưng thuộc **hai context khác nhau**.

Vì vậy, không dùng `==` để so sánh entity được lấy từ các request/context khác nhau, trừ khi bạn thực sự muốn kiểm tra Java reference identity. Khi domain cần equality giữa các detached instances, chính sách `equals()/hashCode()` của entity phải được thiết kế riêng, nhất là với generated ID.

### 3.2. First-level cache không phải bộ cache kết quả mọi truy vấn

Một `em.find(Customer.class, 10L)` lặp lại có thể không cần truy cập database lần hai nếu entity đang managed. Nhưng các JPQL query có điều kiện khác nhau **vẫn có thể gửi SQL** để xác định tập kết quả, ngay cả khi một số entity tương ứng đã ở trong context.

```java
Customer customer = em.find(Customer.class, 10L);

List<Customer> matches = em.createQuery(
    "select c from Customer c where c.displayName like :prefix",
    Customer.class
)
.setParameter("prefix", "A%")
.getResultList();
```

Provider có thể tái sử dụng managed instance tương ứng với entity identity đã được quản lý, nhưng không nên mặc định query sẽ bỏ qua database hoàn toàn. Cần phân biệt **entity identity map** với **query result caching** (một tính năng khác, thường cần cấu hình riêng).

---

## 4. Trạng thái entity và quan hệ với persistence context

Một entity Java thường được mô tả qua các trạng thái:

| Trạng thái | Đặc điểm | Persistence context có quản lý không? |
|---|---|---|
| **New / transient** | Object mới tạo bằng `new`, chưa được đưa vào persistence | Không |
| **Managed** | Thuộc persistence context; provider theo dõi các thay đổi phù hợp | Có |
| **Detached** | Từng được quản lý nhưng không còn thuộc context hiện tại | Không |
| **Removed** | Entity managed đã được yêu cầu xóa | Có trạng thái removed theo quy tắc lifecycle; không coi là entity hoạt động bình thường |

Sơ đồ:

```text
new Customer(...)
       |
       | em.persist(customer)
       v
     managed <--------- em.merge(detached) trả về managed copy
       |                          ^
       |                          |
       | em.detach / em.clear     |
       | hoặc đóng context        |
       v                          |
     detached --------------------+
       |
       | Không tự được dirty checking theo dõi.

managed -- em.remove(...) --> removed
```

Các transaction thường bao quanh thao tác tạo/sửa/xóa dữ liệu, nhưng **trạng thái managed không được định nghĩa đơn giản bằng việc transaction còn active hay không**. Một context có thể sống qua nhiều transaction tùy loại.

### 4.1. Dirty checking không phải commit

```java
Customer customer = em.find(Customer.class, 10L);
customer.rename("Tên mới");
```

Nếu `customer` là managed, provider có thể phát hiện `displayName` đã thay đổi. Nhưng dữ liệu chỉ được đồng bộ vào database theo quy tắc flush, và **chỉ bền vững sau commit thành công**.

Không nên kết luận:

- “Gọi setter là đã UPDATE database.”
- “Object managed nghĩa là có transaction.”
- “Entity đã nhận ID nghĩa là đã commit.”

Ba kết luận trên đều có thể sai.

### 4.2. Detached entity vẫn chứa dữ liệu Java

Nếu `em.close()`, managed entity thường trở thành detached. Các field đã load vẫn nằm trong object:

```java
Customer detached;

EntityManager em = emf.createEntityManager();
try {
    detached = em.find(Customer.class, customerId);
} finally {
    em.close();
}

System.out.println(detached.getDisplayName()); // Field đã load.
detached.rename("Tên đổi trên object detached");
```

Lời gọi `rename` cuối cùng chỉ đổi object Java detached, **không tự lưu** xuống database. Muốn ghi, cần một transaction mới và chọn cách reattach/merge thích hợp, thường rõ nhất là load lại managed entity rồi áp dụng thay đổi.

---

## 5. Flush và commit: vì sao phạm vi transaction quan trọng?

JPA sử dụng persistence context để gom các thao tác thay đổi trạng thái entity. `flush()` là yêu cầu **đồng bộ** những thay đổi thích hợp của context với database; `commit()` là yêu cầu **xác nhận** transaction.

```text
T0: tx.begin()
    |
T1: em.find(Customer#10)
    |  Entity được quản lý.
    |
T2: customer.rename("An Updated")
    |  Context ghi nhận thay đổi.
    |  Chưa mặc định đồng nghĩa có SQL UPDATE.
    |
T3: em.flush()
    |  Có thể phát SQL UPDATE trong transaction.
    |  Nhưng transaction chưa commit.
    |
T4: tx.rollback()
       Database hủy thay đổi chưa commit.
```

Nếu transaction bị rollback, `UPDATE` đã thực thi trong transaction vẫn có thể bị hoàn tác. SQL đã chạy **không phải** bằng chứng dữ liệu đã commit.

### 5.1. Flush mode AUTO và COMMIT

JPA cung cấp `FlushModeType.AUTO` và `FlushModeType.COMMIT`:

- `AUTO`: provider phải bảo đảm các thay đổi trong persistence context được xét phù hợp khi truy vấn có thể bị ảnh hưởng; một cách thường gặp là flush trước query liên quan.
- `COMMIT`: ưu tiên đồng bộ tại commit; hiệu lực thay đổi chưa flush đối với các query trong transaction có thể không xác định theo quy tắc đặc tả cho chế độ này.

Ví dụ:

```java
em.setFlushMode(FlushModeType.AUTO);

Customer customer = em.find(Customer.class, customerId);
customer.rename("New Name");

List<Customer> result = em.createQuery(
    "select c from Customer c where c.displayName = :name",
    Customer.class
)
.setParameter("name", "New Name")
.getResultList();
```

Với transaction đang active, provider có thể flush trước query để kết quả phù hợp. Nhưng thời điểm/số câu SQL cụ thể còn phụ thuộc provider và mapping; không nên suy luận rằng mỗi JPQL query đều luôn phát `UPDATE` ngay.

### 5.2. Flush ngoài transaction

Với các thao tác cần ghi vào database, JPA thường yêu cầu context tham gia một transaction. Gọi `em.flush()` khi không có transaction phù hợp có thể dẫn đến `TransactionRequiredException`. Với extended persistence context, ứng dụng có thể tạm giữ thay đổi trong bộ nhớ ngoài transaction; chúng không tự được commit chỉ vì context còn sống.

**Không dùng flush để thay commit.** Nếu nghiệp vụ cần lưu bền vững, hãy có transaction rõ ràng và xử lý lỗi/rollback.

### 5.3. IDENTITY có thể khiến INSERT xuất hiện sớm

Khi ID được database sinh bằng `GenerationType.IDENTITY`, provider có thể phải `INSERT` sớm để nhận generated key. Vì thế thậm chí `em.persist` cũng có thể tạo SQL trước `flush`/`commit` trong trường hợp phổ biến. Đây là khác biệt về **thời điểm thực thi SQL**, không làm thay đổi ý nghĩa rằng transaction còn có thể rollback.

---

## 6. Hai loại persistence context trong môi trường container-managed

Ở môi trường Jakarta EE/JTA dùng container-managed EntityManager, JPA phân biệt hai scope quan trọng:

1. **Transaction-scoped persistence context** — mặc định khi dùng `@PersistenceContext`.
2. **Extended persistence context** — được khai báo tường minh, thường gắn với stateful session bean.

Điểm cần quan sát là **vòng đời của các managed entity**, không chỉ việc mã Java còn giữ một tham chiếu EntityManager.

### 6.1. Transaction-scoped persistence context

Ví dụ:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

public class CustomerRepository {

    @PersistenceContext
    private EntityManager em;

    public Customer find(Long id) {
        return em.find(Customer.class, id);
    }
}
```

Khi container quản lý EntityManager với transaction-scoped persistence context (giá trị mặc định `PersistenceContextType.TRANSACTION`), một context thường được gắn với **JTA transaction** đang hoạt động. Trong một transaction, các thao tác tham gia cùng persistence unit và cùng transaction có thể dùng cùng context theo cơ chế propagation của container.

```text
JTA Transaction #1
  BEGIN
    Service A ---> EntityManager proxy ---+
                                          |
    Service B ---> EntityManager proxy ---+--> Persistence Context #1
                                               Customer#10 -> Java object A
  COMMIT
  Context #1 kết thúc trong mô hình transaction-scoped.

JTA Transaction #2
  BEGIN
    Service A ---> EntityManager proxy ------> Persistence Context #2
                                               Customer#10 -> Java object B
  COMMIT
```

Một injected EntityManager reference có thể trông như tồn tại lâu trong object component, nhưng thực chất container có thể cấp một **proxy** định tuyến đến context hiện hành. **Độ dài sống của proxy không chứng minh persistence context sống lâu**.

### 6.2. Khai báo tường minh TRANSACTION

```java
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@PersistenceContext(type = PersistenceContextType.TRANSACTION)
private EntityManager em;
```

Với một dịch vụ được container quản lý, transaction-scoped context thích hợp cho các nghiệp vụ ngắn: một request hoặc một use case bắt đầu transaction, làm việc trên entity graph, commit/rollback và giải phóng state quản lý.

**Lưu ý:** JPA/EJB/JTA có các quy định chi tiết về trường hợp gọi EntityManager **ngoài active transaction**, cách context gắn vào transaction tiếp theo và cách các component chia sẻ context. Không nên biến sơ đồ minh họa thành phát biểu tuyệt đối “mọi lệnh `find` ngoài transaction đều thất bại” — đọc dữ liệu có thể được cho phép, nhưng vòng đời entity được quản lý và khả năng ghi không giống khi đang ở một transaction rõ ràng.

### 6.3. Ví dụ khi hai phương thức cùng một JTA transaction

```java
@Stateless
public class OrderService {

    @PersistenceContext
    private EntityManager em;

    @EJB
    private CustomerAuditService auditService;

    public void renameAndAudit(Long customerId, String name) {
        Customer customer = em.find(Customer.class, customerId);
        customer.rename(name);

        auditService.recordChange(customerId, name);
    }
}
```

Ví dụ giả định các method được container điều khiển transaction mặc định phù hợp và `CustomerAuditService` tham gia **cùng JTA transaction**. Nếu service khác dùng cùng persistence unit và context được propagation theo quy tắc container, nó có thể chia sẻ identity map của transaction đó. Nhưng nếu method được cấu hình transaction mới, khác persistence unit hoặc chạy ngoài container, hành vi phải xét lại.

`@Stateless` và `@EJB` thuộc Jakarta Enterprise Beans; ví dụ này không áp dụng nguyên xi cho ứng dụng Java SE RESOURCE_LOCAL hay Spring Boot thông thường.

---

## 7. Extended persistence context: context sống qua nhiều transaction

Một **extended persistence context** giữ các managed entity **vượt ra ngoài ranh giới của một transaction đơn lẻ**. Cơ chế này thích hợp cho một số workflow có nhiều bước tương tác nhưng cần một object graph nhất quán ở phía server trong suốt quá trình.

Một cấu hình điển hình trong Jakarta EE:

```java
import jakarta.ejb.Stateful;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.PersistenceContextType;

@Stateful
public class CustomerEditor {

    @PersistenceContext(type = PersistenceContextType.EXTENDED)
    private EntityManager em;

    private Customer editing;

    public void beginEditing(Long customerId) {
        editing = em.find(Customer.class, customerId);
    }

    public void changeName(String name) {
        editing.rename(name);
    }

    public String currentName() {
        return editing.getDisplayName();
    }
}
```

Đoạn code minh họa **scope và API**, chưa phải một workflow production hoàn chỉnh: transaction attributes của từng method, thời điểm join transaction và thời điểm flush/commit phải được quyết định rõ. Trong một stateful session bean, extended context thường gắn với lifecycle của bean và được giữ qua nhiều method invocation/transaction.

### 7.1. Timeline của extended persistence context

```text
Extended Persistence Context #E
  |
  |-- Method 1: mở editor, load Customer#10
  |           [TX #1] ... COMMIT
  |
  |-- Method 2: thay đổi dữ liệu trong phiên chỉnh sửa
  |           [không có transaction ghi?]
  |           Managed object vẫn còn trong context E
  |
  |-- Method 3: xác nhận và lưu
  |           [TX #2] ... FLUSH/COMMIT
  |
  |-- Method 4: đọc trạng thái trong cùng editor
  |           Context E vẫn sống
  |
  +-- Kết thúc lifecycle bean/editor
              -> context E được đóng/giải phóng
```

Khác với transaction-scoped, context ở đây **không bị hủy ngay sau TX #1**. Object managed có thể giữ identity Java và các thay đổi trong bộ nhớ qua nhiều transaction.

### 7.2. Extended không có nghĩa “transaction kéo dài”

Đây là khác biệt quan trọng nhất:

- **Extended persistence context:** object graph/identity map kéo dài.
- **Transaction:** vẫn là từng transaction độc lập có begin/commit/rollback riêng.

Một extended context **không** biến ba HTTP request thành một database transaction liên tục. Nó cũng không có nghĩa dữ liệu sửa ngoài transaction được lưu ngay hoặc lock database được giữ xuyên suốt workflow.

Nếu business flow có bước “xem trước → sửa → xác nhận”, việc giữ object graph trong context là một lựa chọn về **state management**, không phải cam kết ACID cho toàn bộ các bước.

### 7.3. Ưu điểm và rủi ro

Ưu điểm:

- Có thể giữ cùng các managed instances qua nhiều method/transaction trong một session phù hợp.
- Giảm nhu cầu detach rồi merge object graph ở mỗi bước trong một số workflow.
- Diễn đạt phiên làm việc có state theo cách JPA hỗ trợ.

Rủi ro:

- Context giữ nhiều entity lâu sẽ tiêu tốn bộ nhớ.
- Dữ liệu managed có thể **stale** nếu transaction khác cập nhật database.
- Những sửa đổi ở một bước có thể còn pending và xuất hiện ở bước sau ngoài dự kiến.
- Transaction rollback không tự bảo đảm toàn bộ Java object graph quay về trạng thái cũ phù hợp với database.
- Cần chính sách phiên làm việc, timeout, concurrency, bảo mật và dọn dẹp rõ ràng.
- Extended context thường có vòng đời và giới hạn sử dụng riêng; không nên biến nó thành singleton toàn ứng dụng để chia sẻ giữa nhiều request/người dùng.

### 7.4. Khi nào không nên chọn extended?

Với API stateless thông thường, mỗi request thực hiện một use case ngắn trong transaction riêng, **transaction-scoped** thường đơn giản, rõ ràng và dễ kiểm soát hơn. Extended context chỉ nên được cân nhắc khi có workflow thực sự cần giữ entity graph ở phía server qua nhiều transaction và framework/container hỗ trợ đúng mô hình.

---

## 8. Application-managed EntityManager: ví dụ quan trọng nhất về hai scope khác nhau

Trong Java SE, code thường tự tạo `EntityManagerFactory` rồi `EntityManager` và điều khiển transaction bằng `EntityTransaction`. Đây là **application-managed EntityManager** với kiểu transaction `RESOURCE_LOCAL`.

Lúc này persistence context tồn tại cùng `EntityManager` mà ứng dụng tạo, không tự biến mất chỉ vì một lần `commit()` thành công.

### 8.1. Mã Java SE

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("demoPU");

EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    // Transaction thứ nhất.
    tx.begin();

    Customer customer = em.find(Customer.class, 10L);
    customer.rename("Tên sau TX 1");

    tx.commit();

    // Sau commit, cùng application-managed EntityManager
    // vẫn mở; customer có thể vẫn là managed.
    System.out.println(em.contains(customer)); // true

    // Transaction thứ hai, cùng EntityManager.
    tx.begin();

    customer.rename("Tên sau TX 2");

    tx.commit();
} finally {
    em.close();
    emf.close();
}
```

Giả sử `Customer#10` tồn tại, hai transaction đều thành công và entity không bị detach/clear/remove giữa chừng.

Ở đây:

- `EntityManager` được tạo **một lần**.
- Persistence context gắn với EntityManager đó **có thể kéo dài qua TX #1 và TX #2**.
- Hai lần `commit()` là hai transaction xác nhận độc lập.
- Object `customer` vẫn là managed sau commit thứ nhất, vì EntityManager application-managed chưa đóng và chưa clear.
- Đóng `em` sẽ kết thúc context và các entity còn managed sẽ trở thành detached.

Đây là bằng chứng cụ thể rằng **persistence context scope không nhất thiết bằng transaction scope**.

### 8.2. Timeline rõ hơn

```text
EntityManager em:           open -------------------------------- close
Persistence context PC-A:        ----------------------------------

RESOURCE_LOCAL TX #1:        [begin ---------- commit]
RESOURCE_LOCAL TX #2:                                [begin -- commit]

Customer object:            managed ------------------------------ detached
                           ^ còn managed sau commit của TX #1
```

### 8.3. Application-managed không đồng nghĩa EXTENDED annotation

Một EntityManager tạo bằng `emf.createEntityManager()` có context gắn theo vòng đời của nó, có thể đi qua nhiều transaction. Nhưng đó **không tự động** là một injected container-managed `@PersistenceContext(type = EXTENDED)`.

Phân biệt:

- `@PersistenceContext(type = EXTENDED)`: một kiểu **container-managed extended persistence context**, với các quy tắc lifecycle/propagation của container.
- `EntityManagerFactory.createEntityManager()`: **application-managed EntityManager**, ứng dụng chịu trách nhiệm close và quản lý transaction/join đúng kiểu.
- Cả hai có thể có context dài hơn một transaction, nhưng **cơ chế tạo, quản lý và propagation khác nhau**.

Cũng không nên gọi mọi EntityManager sống lâu là “transaction-scoped” chỉ vì lúc thao tác có transaction.

### 8.4. Vì sao không giữ EntityManager toàn ứng dụng?

`EntityManager` không được thiết kế để chia sẻ an toàn giữa các thread đồng thời như một singleton toàn hệ thống. Nếu nhiều request cùng dùng một `EntityManager`, state của persistence context có thể bị trộn lẫn và dẫn tới race conditions, dữ liệu cũ hoặc những thay đổi không thuộc cùng unit of work.

Thực tế thường dùng:

- Một `EntityManagerFactory` thread-safe được tái sử dụng theo lifecycle ứng dụng.
- Mỗi unit of work/request cần một EntityManager được quản lý đúng scope.
- Đóng application-managed EntityManager khi xong, kể cả khi lỗi.
- Không truyền EntityManager sang thread khác rồi đồng thời dùng nó.

## 9. JTA và việc EntityManager tham gia transaction

Trong hệ thống sử dụng JTA, transaction có thể được quản lý bởi container/transaction manager. Một `EntityManager` có thể **tham gia** transaction hiện hành để đồng bộ thay đổi khi transaction commit.

Hai khái niệm cần tách:

1. **Persistence context vẫn tồn tại và quản lý entity**.
2. **Persistence context đang tham gia JTA transaction nào**, nếu có.

Một context được giữ qua nhiều transaction **không có nghĩa** nó tự động tham gia mọi transaction trong mọi cấu hình. Cách tự động join phụ thuộc loại context, synchronization type và cơ chế container/application quản lý EntityManager.

### 9.1. Context đồng bộ với transaction (SYNCHRONIZED)

Với `SynchronizationType.SYNCHRONIZED`, persistence context được đồng bộ với JTA transaction theo quy tắc JPA. Đây là cách sử dụng thông dụng.

Ví dụ tường minh:

```java
@PersistenceContext(
    type = PersistenceContextType.TRANSACTION,
    synchronization = SynchronizationType.SYNCHRONIZED
)
private EntityManager em;
```

Trong môi trường container-managed và JTA transaction đang active, container xử lý sự tham gia theo lifecycle context. Ứng dụng không phải điều khiển `EntityTransaction.begin()` trên một JTA-managed EntityManager như ví dụ RESOURCE_LOCAL.

### 9.2. Context chưa đồng bộ (UNSYNCHRONIZED)

JPA cũng hỗ trợ `SynchronizationType.UNSYNCHRONIZED` để persistence context **không tự đồng bộ** với JTA transaction cho đến khi được yêu cầu tham gia theo cơ chế phù hợp.

Ví dụ:

```java
@PersistenceContext(
    type = PersistenceContextType.EXTENDED,
    synchronization = SynchronizationType.UNSYNCHRONIZED
)
private EntityManager em;
```

Một tình huống thực tế là workflow thay đổi trạng thái entity qua nhiều bước và chỉ muốn đồng bộ khi người dùng bấm xác nhận.

Khi transaction JTA phù hợp đang active, ứng dụng có thể gọi:

```java
em.joinTransaction();
```

để yêu cầu EntityManager/persistence context tham gia transaction đó. **`joinTransaction()` không bắt đầu một transaction mới**; nó dùng transaction đã tồn tại. Nếu không có JTA transaction phù hợp, việc gọi phương thức này không tự tạo giao dịch và có thể dẫn đến exception tùy ngữ cảnh/quy tắc API.

### 9.3. Lưu ý về loại persistence context

JPA có các quy tắc và giới hạn cụ thể khi kết hợp `TRANSACTION`/`EXTENDED` với `SYNCHRONIZED`/`UNSYNCHRONIZED` theo container và version của Jakarta Persistence. Mẫu được dùng để học sự khác nhau là **extended unsynchronized context** với một transaction JTA được mở rõ ràng ở thời điểm commit.

Không nên chỉ sao chép annotation vào bất kỳ class Spring hoặc Jakarta EE nào rồi giả định container sẽ cấp đúng lifetime mong muốn. Với application-managed EntityManager, dùng overload của `createEntityManager` phù hợp và kiểm tra hỗ trợ transaction type.

### 9.4. Khi cần transaction nhưng chưa join

Một context unsynchronized có thể giữ entity state mà không đồng bộ vào transaction hiện hành. Đây là mục đích của việc tách “context sống lâu” khỏi “giao dịch đang xác nhận”.

```text
Extended UNSYNCHRONIZED PC
    |
    +-- load/edit entity trong phiên làm việc
    |
    +-- JTA Transaction A tồn tại
    |     PC chưa join -> không tự flush với A
    |
    +-- JTA Transaction B tồn tại
          em.joinTransaction()
          -> PC tham gia B
          -> thay đổi phù hợp có thể flush/commit cùng B
```

Ứng dụng phải kiểm soát rõ **thời điểm join** và xử lý các thay đổi pending; không suy luận rằng mọi thay đổi “bên ngoài transaction” là bị bỏ đi ngay lập tức hay tự được ghi khi một transaction bất kỳ kết thúc.

---

## 10. Transaction-scoped context trong Spring Data JPA

Phần lớn ứng dụng Spring dùng Spring Data JPA thường có các service annotate `@Transactional`. Trong cấu hình Spring/JPA phổ biến, một EntityManager được gắn với transaction hiện hành thông qua transaction manager, và `@PersistenceContext` đưa vào một **EntityManager proxy**.

Ví dụ:

```java
@Service
public class CustomerService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameCustomer(Long id, String newName) {
        Customer customer = em.find(Customer.class, id);

        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        customer.rename(newName);
    }
}
```

Mặc định trong một cấu hình Spring thông dụng:

1. `@Transactional` tạo hoặc tham gia transaction theo propagation policy.
2. EntityManager proxy trỏ đến EntityManager/context đang được Spring quản lý cho transaction.
3. `em.find` trả managed entity trong context đó.
4. Thay đổi `rename` được đồng bộ khi transaction flush/commit.
5. Khi transaction/context kết thúc, các entity được trả ra có thể trở thành detached.

Trong Spring, một bean `@Service` có thể là singleton và tồn tại suốt ứng dụng, nhưng trường `em` injected thường là proxy. **Không suy luận context sống suốt đời singleton service**.

### 10.1. Hai lời gọi service, hai transaction

```java
customerService.renameCustomer(10L, "A");
customerService.renameCustomer(10L, "B");
```

Nếu mỗi lời gọi đi qua Spring transaction interceptor và không có transaction bao ngoài, chúng có thể tạo hai transaction độc lập. Cùng một entity identity `Customer#10` được truy cập trong hai lần có thể là **hai managed Java instances khác nhau ở hai persistence context khác nhau**.

Không nên giữ một managed entity từ lần gọi thứ nhất trong field của singleton service rồi coi nó vẫn managed trong lần gọi thứ hai.

### 10.2. @Transactional không tương đương @PersistenceContext(EXTENDED)

`@Transactional` quyết định **phạm vi transaction** và propagation policy trong Spring. Nó **không tự biến** persistence context thành extended context để giữ managed entities qua nhiều transaction.

Nếu ứng dụng cần workflow nhiều bước, các phương án thường dễ quản lý hơn là:

- Dùng DTO/draft state giữa các request.
- Lưu trạng thái bản nháp trong database với transaction ngắn.
- Khi xác nhận, tải lại entity trong transaction mới và áp dụng thay đổi hợp lệ.
- Dùng optimistic locking nếu cần phát hiện thay đổi cạnh tranh.

### 10.3. readOnly không có nghĩa “không có context”

```java
@Transactional(readOnly = true)
public CustomerDetails getDetails(Long id) {
    // Đọc dữ liệu và chuyển thành DTO.
}
```

`readOnly = true` thể hiện ý định chỉ đọc và có thể tạo một số tối ưu hóa/setting provider-specific của Spring/Hibernate. Nó không có nghĩa EntityManager biến mất hay mọi entity đều lập tức detached.

**Không dựa vào `readOnly=true` như một cơ chế bảo mật chặn toàn bộ lệnh ghi ở database.** Nó không thay thế permission, API boundary và database constraints.

### 10.4. Propagation và ranh giới context

`@Transactional(propagation = Propagation.REQUIRED)` thường tham gia transaction đang có; `REQUIRES_NEW` có thể tạo transaction mới và tạm đình chỉ transaction cũ. Trong cấu hình Spring JPA phổ biến, điều này cũng ảnh hưởng đến EntityManager/context được gắn với từng transaction.

```java
@Transactional
public void outer() {
    // Transaction A.
    helper.requiresNewWork();
    // Transaction A được tiếp tục.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void requiresNewWork() {
    // Transaction B khác với A nếu gọi qua proxy đúng cách.
}
```

Hai method ở trên chỉ minh họa annotation/ý tưởng; trong Spring proxy mode, một lời gọi trực tiếp từ method này sang method khác **trong cùng instance** (*self-invocation*) thường không kích hoạt transaction interceptor cho method được gọi. Muốn kiểm tra thực sự có hai transaction, cần tách service hoặc dùng cơ chế gọi đúng qua proxy.

Không suy luận rằng một object `Customer` managed trong transaction A tự động tiếp tục managed trong transaction B. Phụ thuộc EntityManager/context mà framework gắn với từng transaction và cách object được truyền qua ranh giới.

### 10.5. Không dùng EntityManager như biến toàn cục trên thread khác

`EntityManager`/persistence context không phù hợp để chia sẻ đồng thời tùy tiện giữa nhiều thread. Khi xử lý `@Async`, executor hoặc luồng khác, transaction context gắn với thread hiện tại **không tự động chuyển theo** theo cách mà ứng dụng có thể dựa vào.

Không truyền một managed entity sang thread khác rồi giả định lazy loading và dirty checking hoạt động trong cùng context. Hãy truyền ID/DTO, tạo unit of work riêng ở thread đích và tải lại entity khi cần.

---

## 11. Open EntityManager in View không phải extended persistence context

Trong ứng dụng web Spring, một cấu hình thường được nhắc đến là **Open EntityManager in View** (OSIV). Ý tưởng là gắn một EntityManager với phạm vi xử lý request web để có thể truy cập một số lazy association trong lúc render view/serialize response.

```text
HTTP Request bắt đầu
   |
   +-- Open EntityManager
   |
   +-- Service @Transactional
   |     BEGIN TX
   |     load Customer / Order
   |     COMMIT TX
   |
   +-- Controller/View serialization
   |     EntityManager có thể còn mở
   |     Lazy association có thể được tải tiếp
   |
   +-- Close EntityManager
HTTP Request kết thúc
```

Trong cấu hình này, **vòng đời EntityManager có thể dài hơn transaction của service**. Nhưng đừng gọi nó là `@PersistenceContext(type=EXTENDED)`: OSIV là cơ chế tích hợp web/framework, không phải loại container-managed extended persistence context gắn với stateful session bean.

### 11.1. Vì sao OSIV dễ gây nhầm?

Vì code có thể truy cập lazy collection **sau khi service transaction đã commit** mà không ném ngay exception, lập trình viên có thể nghĩ transaction vẫn còn mở. Thực tế, query phát sinh lúc render view có thể chạy ngoài transaction service ban đầu, theo hành vi JDBC/provider/database cụ thể.

Hệ quả có thể gồm:

- N+1 query bị ẩn ở lớp view/serialization.
- Dữ liệu đọc lúc render có thể không nhất quán với dữ liệu đã đọc trong transaction service.
- Connection/SQL work có thể kéo dài thời gian request.
- Khó xác định rõ use case nào đã tải những quan hệ nào.

Không nên dùng OSIV làm phương án mặc định để giải quyết mọi `LazyInitializationException`.

### 11.2. Cách làm rõ ranh giới hơn

Thiết kế service trả **DTO**:

```java
public record CustomerDetails(Long id, String name) {}

@Service
public class CustomerQueryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public CustomerDetails getDetails(Long id) {
        Customer customer = em.find(Customer.class, id);

        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        return new CustomerDetails(
            customer.getId(),
            customer.getDisplayName()
        );
    }
}
```

Trong ví dụ, service chuyển dữ liệu cần thiết thành DTO trong transaction; tầng controller không phụ thuộc vào lifecycle của entity managed hay proxy lazy. Nếu cần collection, hãy chủ động fetch trong use case và chuyển sang DTO trước khi trả.

---

## 12. Phân tích các trường hợp thường gây nhầm

### 12.1. Case A: cùng transaction, cùng context

```text
BEGIN TX
  em.find(Customer, 10) -> object A
  em.find(Customer, 10) -> object A
  em.contains(object A) -> true
COMMIT
```

Trong cùng persistence context, một entity identity tương ứng một managed instance. Với transaction-scoped context, khi transaction kết thúc thì context đó kết thúc và các object không còn managed trong context ấy.

### 12.2. Case B: hai transaction, mỗi transaction một context

```text
TX #1:
  find(Customer#10) -> object A
  COMMIT -> context #1 kết thúc

TX #2:
  find(Customer#10) -> object B
  COMMIT -> context #2 kết thúc
```

Object A và B cùng tương ứng một database row nhưng có thể là hai Java references khác nhau. Không dùng tham chiếu A ở TX #2 như một managed entity chỉ vì nó từng được managed.

### 12.3. Case C: hai transaction, cùng application-managed EM

```text
em = emf.createEntityManager()

TX #1:
  customer = em.find(Customer#10) -> object A
  COMMIT

Không transaction:
  em.contains(customer) -> true

TX #2:
  customer.rename(...)
  COMMIT

em.close() -> object A detached
```

Đây là trường hợp context vượt qua transaction. Sự tồn tại của context **không tự mở transaction** ở khoảng trống giữa hai TX.

### 12.4. Case D: context còn mở nhưng database đã thay đổi bên ngoài

```text
PC-A load Customer#10, name="An"

PC-B (transaction khác):
  UPDATE Customer#10 name="Bình"
  COMMIT

PC-A:
  em.find(Customer#10)
  -> có thể trả managed object name="An" vẫn đang có trong PC-A
```

First-level cache có thể giữ snapshot đã cũ. Nếu business logic cần cập nhật lại dữ liệu, có thể dùng `em.refresh(customer)` trong điều kiện hợp lệ, hoặc kết thúc context và mở context mới, kết hợp locking/version theo nhu cầu.

Không mặc định một context sống lâu sẽ tự cập nhật mọi thay đổi database diễn ra ở transaction khác.

### 12.5. Case E: entity đã detached nhưng ID vẫn có

```java
Customer customer = em.find(Customer.class, 10L);
em.detach(customer);

System.out.println(customer.getId());     // 10
System.out.println(em.contains(customer)); // false
```

Có ID và có dữ liệu field **không có nghĩa** entity đang managed. `em.contains` giúp kiểm tra trạng thái quản lý của một object đối với chính EntityManager đó.

### 12.6. Case F: rollback không có nghĩa Java object tự quay về giá trị cũ

Giả sử:

```java
tx.begin();

Customer customer = em.find(Customer.class, 10L);
customer.rename("Tên chưa được xác nhận");

tx.rollback();
```

Database không lưu thay đổi chưa commit. Nhưng object Java `customer` có thể vẫn chứa `"Tên chưa được xác nhận"` trong bộ nhớ, và trạng thái liên quan đến managed/detached sau rollback phụ thuộc quy tắc lifecycle và loại EntityManager/context.

**Không dựa vào rollback để “undo” từng setter trên object Java.** Với application-managed context, sau lỗi/rollback thường nên đóng/clear context rồi tải lại dữ liệu từ database trong unit of work mới khi cần trạng thái chắc chắn.

### 12.7. Case G: flush trong transaction nhưng chưa commit

```java
tx.begin();

Customer customer = em.find(Customer.class, 10L);
customer.rename("Updated");
em.flush();

// SQL có thể đã UPDATE database trong TX hiện hành.
// Nhưng giao dịch vẫn chưa commit.

tx.rollback();
```

Không dùng việc nhìn thấy SQL log để xác nhận thao tác thành công. Chỉ sau commit thành công mới có kết quả bền vững theo transaction.

---

## 13. Thao tác với detached entity: merge không phải nối lại object cũ

Khi context ngắn, entity thường bị detach sau khi trả khỏi service hoặc đóng `EntityManager`. Khi đó một object bị chỉnh sửa ở tầng khác cần được đồng bộ lại theo một quy trình rõ ràng.

### 13.1. Load managed entity rồi áp dụng thay đổi: phương án rõ ràng

```java
tx.begin();

Customer managed = em.find(Customer.class, detached.getId());

if (managed == null) {
    throw new IllegalArgumentException("Customer not found");
}

managed.rename(detached.getDisplayName());

tx.commit();
```

Cách này tách dữ liệu đầu vào khỏi đối tượng quản lý và thuận tiện kiểm tra quyền, version hoặc invariant. Nếu dữ liệu đầu vào đến từ client, không nên tin rằng mọi field trên detached entity đều được phép cập nhật.

### 13.2. Merge tạo/trả về managed instance

```java
tx.begin();

Customer managedCopy = em.merge(detached);

System.out.println(managedCopy == detached); // Thường false nếu detached.

tx.commit();
```

`merge` sao chép state phù hợp từ entity detached sang một managed instance trong context. **Nó không nhất thiết biến chính object `detached` thành managed**.

Mã sau dễ gây nhầm:

```java
em.merge(detached);
detached.rename("Another name");
// Lần rename trên detached sau merge không tự được track.
```

Nếu cần tiếp tục thao tác, hãy giữ **giá trị trả về** từ `merge`. Các association, cascade MERGE, optimistic locking và dữ liệu client không tin cậy cần được xử lý cẩn thận.

### 13.3. Context scope quyết định lúc nào cần merge

Trong transaction-scoped context, sau khi transaction/context kết thúc, entity trả ra thường detached. Một use case mới muốn cập nhật phải tải lại/merge.

Trong application-managed EntityManager còn mở qua nhiều transaction, entity có thể vẫn managed và không cần merge chỉ vì transaction trước đã commit. Đây chính là khác biệt của scope.

---

## 14. Giữ context lâu gây stale data như thế nào?

Giả sử một EntityManager application-managed tồn tại trong một quá trình xử lý dài:

```java
EntityManager em = emf.createEntityManager();

Customer customer = em.find(Customer.class, customerId);

// Vài phút sau, transaction khác đã đổi tên Customer trong DB.
Customer again = em.find(Customer.class, customerId);

System.out.println(customer == again); // true, cùng context.
```

`again` có thể vẫn phản ánh state cũ, vì JPA ưu tiên identity nhất quán trong context. Để cập nhật:

```java
em.refresh(customer);
```

`refresh` yêu cầu tải lại state từ database theo quy tắc JPA, nhưng cần chú ý:

- Có thể ghi đè các thay đổi **chưa flush** của object.
- Có thể cần transaction/lock phù hợp tùy ngữ cảnh, provider và cách gọi.
- Không bảo đảm mọi thứ được đồng bộ theo cách giống nhau nếu có association hoặc giá trị được cache nhiều tầng.
- Không thay thế một chiến lược concurrency có ý nghĩa nghiệp vụ.

### 14.1. clear() và detach()

```java
em.detach(customer); // Tách riêng customer khỏi context.

em.clear();          // Tách tất cả entity khỏi context.
```

`detach`/`clear` không commit transaction. Các thay đổi đang chờ nhưng chưa được đồng bộ có thể **không được lưu** nếu bạn detach/clear object trước khi flush phù hợp.

Một pattern an toàn khi đã quyết định lưu thành công:

```java
tx.begin();
try {
    // Sửa managed entities...
    em.flush();
    tx.commit();

    em.clear(); // Chỉ khi không cần tiếp tục managed state cũ.
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Không cần `flush` tường minh trong mọi transaction vì commit thường thực hiện đồng bộ cần thiết; ví dụ trên nhấn mạnh thứ tự khi chủ động dùng `clear`. Với lỗi/rollback, nên xem lại toàn bộ context trước khi tái sử dụng.

### 14.2. Memory growth

Một context sống lâu có thể tích lũy hàng nghìn entity đã load. Dù code đã hoàn tất một transaction, entity vẫn có thể nằm trong identity map nếu context chưa đóng/clear. Hậu quả là tăng bộ nhớ và chi phí dirty checking.

Trong batch processing bằng application-managed EM, người ta có thể làm theo từng chunk:

```java
tx.begin();

for (int i = 0; i < records.size(); i++) {
    em.persist(mapToEntity(records.get(i)));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}

tx.commit();
```

Đây là pattern minh họa cho việc giới hạn số entity managed ở mỗi chunk; nó giả định transaction active và không còn cần tham chiếu managed đã bị clear. Cần xử lý rollback/finally ở code production. `clear` không tự giảm tải SQL generator IDENTITY hay bảo đảm JDBC batching; đó là bài toán khác.

### 14.3. Context dài và concurrency

Một persistence context không phải cache đa người dùng. Đừng dùng một extended context hoặc một shared EntityManager làm bộ nhớ trạng thái chung cho toàn bộ hệ thống.

Nếu hai người dùng cùng chỉnh sửa một Customer, hãy kiểm soát concurrency bằng transaction, domain policy và có thể `@Version`. Context dài không tự giải quyết lost update; đôi khi còn khiến xung đột dữ liệu khó phát hiện hơn.

---

## 15. @Version, optimistic locking và phạm vi giao dịch

Một entity có thể có:

```java
@Version
private Long version;
```

Khi hai transaction sửa cùng một row, optimistic locking giúp phát hiện một số tình huống cập nhật dựa trên version cũ:

```text
TX A:
  Read Customer#10 version=7

TX B:
  Read Customer#10 version=7
  UPDATE ... WHERE id=10 AND version=7
  COMMIT -> version=8

TX A:
  UPDATE ... WHERE id=10 AND version=7
  -> Không còn khớp; optimistic lock conflict
```

`@Version` theo dõi phiên bản entity ở database và hỗ trợ phát hiện xung đột cập nhật. Nó **không quyết định persistence context sống bao lâu**. Một context extended sống nhiều transaction vẫn phải xử lý version conflict khi commit về sau.

Nếu transaction khác cập nhật row nhưng context đang giữ state cũ, chỉ gọi `find` lại trên cùng context không buộc provider bỏ state cũ; cơ chế version có thể giúp phát hiện khi ghi, nhưng UI vẫn phải cân nhắc cách trình bày thông tin cũ.

### 15.1. Transaction isolation không đồng nghĩa context cache freshness

Ngay cả khi database dùng một isolation level cụ thể, object managed trong persistence context vẫn là state Java được provider giữ. Đừng coi việc thay isolation level là bảo đảm mọi `find` lặp lại sẽ tải lại row từ database.

Nếu yêu cầu nghiệp vụ đòi hỏi giá trị mới nhất, hãy thiết kế re-read/refresh/context mới/locking phù hợp, rồi kiểm tra hành vi trong transaction thực.

---

## 16. Một EntityManager có thể dùng đồng thời ở nhiều thread không?

Câu trả lời thực tế là **không nên và không được giả định thread-safe**. JPA EntityManager và persistence context được thiết kế cho một unit of work/ngữ cảnh sử dụng thích hợp, không phải một object chia sẻ để nhiều thread gọi cùng lúc.

Sai lầm:

```java
public final class GlobalEntityManagerHolder {
    public static EntityManager em;
}
```

Nếu mọi HTTP request dùng chung `em`, các transaction và managed entities có thể can thiệp nhau, dẫn đến dữ liệu cũ, lỗi lifecycle và race conditions.

Mẫu tổ chức phổ biến:

- **EntityManagerFactory:** khởi tạo một lần cho ứng dụng/persistence unit, tái sử dụng theo cách thread-safe được hỗ trợ.
- **EntityManager:** được tạo/gắn theo unit of work và đóng/giải phóng theo scope thích hợp.
- **Transaction:** bắt đầu/commit/rollback cho mỗi nghiệp vụ cần tính nguyên tử.
- **DTO/ID:** dùng để giao tiếp giữa request, thread, queue hoặc các tầng không cùng context.

Khi dùng framework, hãy để transaction manager/proxy quản lý EntityManager thay vì tự trữ một EntityManager field dùng chung không kiểm soát.

---

## 17. Chọn scope theo loại ứng dụng

### 17.1. REST API stateless

Ví dụ request “đổi tên khách hàng”:

```text
HTTP PUT /customers/10
  |
  +-- Controller nhận DTO
  |
  +-- Service @Transactional
  |      load Customer#10
  |      validate + rename
  |      flush/commit
  |
  +-- Trả DTO kết quả
```

Lựa chọn phổ biến: **context gắn với transaction/unit of work ngắn**. Không cần giữ entity managed qua nhiều request. Phù hợp với throughput, kiểm soát memory và ranh giới consistency rõ ràng.

### 17.2. Batch import lớn

Ví dụ nạp 100.000 hàng:

- Có thể dùng application-managed EntityManager trong Java SE.
- Chia transaction thành chunk theo yêu cầu lỗi/nguyên tử dữ liệu.
- Dùng `flush`/`clear` để kiểm soát số managed entities nếu phù hợp.
- Không giữ toàn bộ entity graph trong một context quá lâu.
- Cân nhắc SQL/JDBC batching, generator và bulk loader khi cần hiệu năng.

Context và transaction boundaries có thể được tổ chức khác nhau: một EM cho một chunk, hoặc một EM qua nhiều chunk nhưng clear đúng điểm. Phải lựa chọn theo yêu cầu recovery và cách provider hoạt động.

### 17.3. Giao diện chỉnh sửa nhiều bước

Ví dụ wizard tạo hồ sơ trong nhiều màn hình:

- Không nhất thiết cần một transaction dài giữ database lock qua toàn bộ thời gian người dùng thao tác.
- Có thể lưu draft state/DTO và commit ở mỗi bước hoặc ở bước xác nhận cuối.
- Nếu container hỗ trợ stateful session bean và extended persistence context, đó là một lựa chọn cần cân nhắc với quản lý lifecycle và stale data rõ ràng.
- Với ứng dụng web phân tán, lưu draft vào database thường dễ phục hồi, scale và bảo trì hơn context stateful kéo dài.

### 17.4. Công việc bất đồng bộ

Khi xử lý event, job hoặc message:

- Truyền ID và dữ liệu bất biến cần thiết trong message.
- Worker thread mở transaction/context riêng.
- Tải lại entity theo ID trong context đó.
- Không chuyển một managed entity hoặc EntityManager qua thread rồi kỳ vọng transaction cũ theo cùng.

---

## 18. Bảng so sánh trọng tâm

| Cấu hình/vòng đời | Persistence context kéo dài bao lâu? | Transaction kéo dài bao lâu? | Managed entity còn sau commit? |
|---|---|---|---|
| **Container-managed TRANSACTION** | Thường gắn với một JTA transaction | Theo JTA transaction | Không trong context vừa kết thúc; entity thường detached |
| **Container-managed EXTENDED** | Theo vòng đời extended context, điển hình stateful component | Có thể nhiều transaction riêng | Có thể còn managed khi context vẫn sống |
| **Application-managed RESOURCE_LOCAL EM** | Từ khi `emf.createEntityManager()` đến `em.close()`/clear phù hợp | Mỗi `EntityTransaction.begin()/commit()/rollback()` | Có thể vẫn managed nếu EM còn mở |
| **Spring @Transactional, mặc định thông dụng** | Context quản lý theo transaction và cơ chế binding của Spring | Theo service transaction, propagation | Thường detached khi context liên quan đóng |
| **Spring với OSIV bật** | EntityManager có thể mở đến hết web request | Transaction service thường ngắn hơn request | Có thể còn managed đến lúc EM request đóng, nhưng TX đã kết thúc |
| **Detached DTO/entity** | Không thuộc context active | Không có transaction gắn tự động | Detached; thay đổi không được dirty checking tự động |

**Chú ý:** các dòng trên mô tả mô hình phổ biến, không biến mọi tình huống thành tuyệt đối. JTA join, context synchronization, transaction propagation, OSIV và framework proxy đều có cấu hình/ngoại lệ riêng.

### 18.1. Bảng so sánh thao tác

| Hành động | Thay đổi PC? | Thay đổi transaction? | Có ghi DB bền vững ngay? |
|---|---|---|---|
| `em.find` | Có thể thêm entity managed vào context | Không tự bắt đầu TX RESOURCE_LOCAL | Không |
| `em.persist` | Đăng ký entity mới là managed | Không tự commit TX | Không; SQL có thể chạy sớm |
| Sửa field managed | Context theo dõi thay đổi | Không tự mở TX | Không |
| `em.flush` | Đồng bộ state phù hợp với DB | Không commit | Không; SQL vẫn có thể rollback |
| `tx.commit` | Context có thể còn hoặc kết thúc tùy scope | Kết thúc TX | Có nếu thành công |
| `tx.rollback` | State PC sau lỗi cần xử lý thận trọng | Hủy TX | Không giữ thay đổi chưa commit |
| `em.detach(entity)` | Entity cụ thể không còn managed | Không commit/rollback | Không |
| `em.clear` | Tách toàn bộ entity khỏi context | Không commit/rollback | Không |
| `em.close` | Kết thúc application-managed context | Không thay thế commit | Không |
| `em.merge(detached)` | Tạo/trả về managed copy thích hợp | Không tự commit | Không đến khi flush + commit thành công |
| `em.joinTransaction` | Yêu cầu tham gia JTA TX hiện hành | Không bắt đầu TX mới | Không ngay lập tức |

---

## 19. Bài thực hành 1: chứng minh context sống qua hai transaction

Bài thực hành này dùng Java SE, `RESOURCE_LOCAL` và một application-managed EntityManager. Có thể chạy với Hibernate ORM và H2, hoặc provider/database JPA tương thích.

### 19.1. persistence.xml mẫu

File `src/main/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">
    <persistence-unit name="demoPU"
                      transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.domain.Customer</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:scope_demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ để học trên database tạm. -->
            <property name="hibernate.hbm2ddl.auto"
                      value="create-drop"/>
            <property name="hibernate.show_sql" value="true"/>
            <property name="hibernate.format_sql" value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Cần có thư viện Jakarta Persistence API, Hibernate ORM và H2 JDBC driver tương thích. `hibernate.*` là thuộc tính riêng Hibernate. `create-drop` có thể xóa schema và dữ liệu; không dùng với production.

### 19.2. Chương trình minh họa

```java
package demo;

import demo.domain.Customer;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class ScopeDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("demoPU");

        try {
            demonstrateTwoTransactions(emf);
        } finally {
            emf.close();
        }
    }

    private static void demonstrateTwoTransactions(
            EntityManagerFactory emf) {

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();

            // Transaction #1: tạo entity.
            tx.begin();

            Customer customer = new Customer("Customer A");
            em.persist(customer);

            tx.commit();

            System.out.println("After TX #1:");
            System.out.println("  id = " + customer.getId());
            System.out.println("  EM open = " + em.isOpen());
            System.out.println("  managed = " + em.contains(customer));

            // Transaction #2: cùng context nếu EM vẫn mở.
            tx.begin();

            Customer again = em.find(
                Customer.class, customer.getId());

            System.out.println("During TX #2:");
            System.out.println("  same Java instance = "
                + (customer == again));

            again.rename("Customer B");

            tx.commit();

            System.out.println("After TX #2:");
            System.out.println("  managed = " + em.contains(customer));
        } finally {
            em.close();
        }
    }
}
```

Với application-managed EntityManager và cả hai transaction thành công, bạn thường quan sát:

```text
After TX #1:
  EM open = true
  managed = true

During TX #2:
  same Java instance = true

After TX #2:
  managed = true
```

ID cụ thể phụ thuộc database. Điểm then chốt là **TX #1 đã commit nhưng persistence context vẫn sống** vì EntityManager chưa bị đóng/clear.

**Đọc đúng kết quả:** `em.contains(customer) == true` nói về trạng thái trong **EntityManager đó**, không bảo đảm dữ liệu mới nhất từ mọi transaction bên ngoài.

### 19.3. Thử đóng EntityManager

Sau khi `em.close()`, không gọi `em.contains` nữa vì EntityManager đã đóng. Thay vào đó, mở EntityManager khác để load Customer theo ID và so sánh reference:

```java
EntityManager secondEm = emf.createEntityManager();

try {
    Customer loaded = secondEm.find(
        Customer.class, customerId);

    System.out.println(loaded == oldCustomer); // Thường false.
} finally {
    secondEm.close();
}
```

`customerId` và `oldCustomer` ở đây là ID và instance giữ lại từ bài thực hành trước. Khi đọc bằng một context mới, bạn không còn sở hữu Java instance cũ như managed instance của context mới.

---

## 20. Bài thực hành 2: khác nhau giữa flush và commit

1. Tạo Customer và commit ở transaction đầu.
2. Mở EntityManager mới.
3. Bắt đầu transaction.
4. Load Customer thành managed.
5. Đổi `displayName`.
6. Gọi `em.flush()` và quan sát SQL.
7. Gọi `tx.rollback()` thay vì commit.
8. Đóng EM và mở EM khác.
9. Tìm Customer theo ID, kiểm tra tên vẫn là giá trị đã commit trước đó.

Mã trọng tâm:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    Customer customer = em.find(Customer.class, customerId);
    customer.rename("Should be rolled back");

    em.flush();

    tx.rollback();
} finally {
    em.close();
}
```

Hãy ghi rõ:

- `flush()` có thể làm SQL `UPDATE` xuất hiện.
- `rollback()` hủy thay đổi transaction chưa commit.
- Giá trị còn trong object Java cũ không chứng minh database đã lưu.
- Kiểm tra trạng thái database bằng **persistence context mới**, tránh nhầm với first-level cache cũ.

---

## 21. Bài thực hành 3: context dài và stale data

Mục tiêu là thấy first-level cache và database freshness không đồng nhất.

```java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    // Context A load dữ liệu.
    Customer a = emA.find(Customer.class, customerId);
    String firstName = a.getDisplayName();

    // Context B thay đổi và commit.
    EntityTransaction txB = emB.getTransaction();
    txB.begin();

    try {
        Customer b = emB.find(Customer.class, customerId);
        b.rename("Updated by B");
        txB.commit();
    } catch (RuntimeException ex) {
        if (txB.isActive()) txB.rollback();
        throw ex;
    }

    // Tìm lại bằng context A đang còn giữ managed instance.
    Customer againA = emA.find(Customer.class, customerId);

    System.out.println(a == againA); // true.

    // Có thể vẫn thấy dữ liệu cũ ở A.
    System.out.println(againA.getDisplayName());

    // Khi cần trạng thái mới nhất theo policy:
    emA.refresh(a);
    System.out.println(a.getDisplayName());
} finally {
    emA.close();
    emB.close();
}
```

Khi chạy trên database thật, kết quả visibility của refresh còn phụ thuộc transaction/isolation và thời điểm đọc. Trong thí nghiệm này, `emA` không có transaction đang active tại lúc refresh; provider có thể yêu cầu một transaction cho các thao tác/lock cụ thể. Nếu stack yêu cầu, thực hiện refresh trong transaction đọc phù hợp.

Phần cần quan sát: `emA.find` với cùng ID trả lại **object đang managed trong context A**, không phải luôn tạo object mới phản ánh dữ liệu mới nhất.

---

## 22. Bài thực hành 4: so sánh transaction-scoped và extended trong container

Trong môi trường Jakarta EE có hỗ trợ Enterprise Beans/JTA:

### Phần A — TRANSACTION

1. Tạo component container-managed với `@PersistenceContext(type=TRANSACTION)`.
2. Tại transaction #1, `em.find(Customer.class, id)` và ghi nhận giá trị.
3. Kết thúc transaction.
4. Tại transaction #2, load lại cùng ID.
5. Quan sát identity behavior trong từng transaction/context.
6. Không dựa vào Java reference cũ ở transaction #2 như entity managed.

### Phần B — EXTENDED

1. Tạo stateful session bean với `@PersistenceContext(type=EXTENDED)`.
2. Tải Customer trong một method.
3. Gọi method khác của cùng bean trong một transaction khác.
4. Quan sát object managed có thể được giữ qua các transaction.
5. Xem thời điểm bean bị remove/timeout và context kết thúc.
6. Mô phỏng transaction khác cập nhật dữ liệu để nhận diện stale state.
7. Không biến toàn bộ workflow thành một transaction database duy nhất.

### Phần C — UNSYNCHRONIZED và joinTransaction

1. Tạo extended unsynchronized context theo container hỗ trợ.
2. Tạo/điều chỉnh entity state trong phiên.
3. Mở JTA transaction phù hợp.
4. Chủ động gọi `em.joinTransaction()`.
5. Flush/commit và kiểm tra dữ liệu.
6. So sánh với việc không join transaction.
7. Giải thích vì sao `joinTransaction()` không bắt đầu giao dịch mới.

Phần thực hành container không áp dụng nguyên xi cho Java SE RESOURCE_LOCAL; cần môi trường Jakarta EE và cấu hình JTA phù hợp.

---

## 23. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
|---|---|
| “Persistence context và transaction là cùng một thứ.” | Context quản lý entity state; transaction xác nhận/hủy SQL và dữ liệu. |
| “Khi transaction kết thúc, mọi EntityManager đều bị đóng.” | Không đúng với application-managed EM còn mở hoặc extended context. |
| “Đối tượng có ID là đang managed.” | Entity detached vẫn có ID. Kiểm tra context cụ thể bằng `contains`. |
| “Gọi setter trên managed entity là đã commit.” | Thay đổi cần flush/commit trong transaction phù hợp. |
| “Flush đồng nghĩa commit.” | Flush đồng bộ SQL; rollback vẫn có thể hủy. |
| “Commit sẽ tự đưa field Java về giá trị trước rollback.” | Rollback không tự undo mọi mutation trên object Java. |
| “Cùng một ID luôn cùng một object Java trên mọi request.” | Bảo đảm Java identity chỉ trong cùng persistence context. |
| “Spring singleton @Service giữ cùng persistence context suốt ứng dụng.” | EntityManager injected thường là proxy theo scope quản lý. |
| “@Transactional đồng nghĩa context extended.” | @Transactional điều khiển transaction, không tự kéo dài context qua nhiều TX. |
| “OSIV nghĩa transaction mở tới cuối HTTP request.” | OSIV có thể giữ EntityManager mở lâu hơn service transaction. |
| “EXTENDED nghĩa một transaction nhiều phút.” | Extended kéo dài context, không kéo dài một transaction duy nhất. |
| “Ứng dụng sửa entity detached sẽ tự lưu.” | Detached object không được dirty checking theo dõi. |
| “merge biến object được truyền vào thành managed.” | `merge` trả về managed instance; đầu vào detached không tự được quản lý. |
| “EntityManager nên làm singleton để giảm overhead.” | EntityManager không được dùng đồng thời tùy tiện giữa các thread. |
| “First-level cache tự biết thay đổi database từ TX khác.” | Context dài có thể giữ stale state; cần refresh/reload/locking thích hợp. |
| “JTA joinTransaction bắt đầu transaction.” | Nó yêu cầu tham gia transaction JTA đang tồn tại. |
| “readOnly=true ngăn mọi SQL ghi.” | Đây là hint/policy framework, không phải cơ chế chặn ghi tuyệt đối. |
| “@Version quyết định khi nào context đóng.” | Version phục vụ concurrency; không quyết định vòng đời context. |

---

## 24. Tình huống thiết kế thực tế

### 24.1. Người dùng mở biểu mẫu, để đó 15 phút rồi nhấn Save

Hệ thống REST stateless nên làm gì?

Một hướng:

1. Request mở biểu mẫu trả DTO gồm dữ liệu và `version` nếu dùng optimistic locking.
2. Người dùng chỉnh sửa trong browser mà không giữ một transaction database dài.
3. Request Save mở transaction mới.
4. Service tải lại entity managed.
5. Kiểm tra permission, version, invariant và áp dụng thay đổi.
6. Commit hoặc trả conflict khi dữ liệu đã bị người khác sửa.

Không cần giữ một persistence context xuyên 15 phút ở server chỉ để tái sử dụng một object Java.

### 24.2. Job import 500.000 hàng

Một transaction khổng lồ có thể dùng nhiều bộ nhớ/lock. Có thể chia thành chunk, mỗi chunk có transaction và context riêng, hoặc giữ application-managed EM nhưng `flush`/`clear` có kiểm soát. Cần quyết định tính atomicity giữa các chunk: chia chunk nghĩa là một số chunk đã commit có thể không rollback cùng các chunk sau.

Context scope không quyết định thay cho transaction recovery policy.

### 24.3. Hệ thống bán hàng cần tải lại giá mới nhất trước khi xác nhận

Một context sống lâu có thể giữ Product cũ. Nếu nghiệp vụ cần giá hiện tại, nên đọc/tính toán trong transaction xác nhận với chính sách consistency phù hợp. Không dựa vào `em.find` lần thứ hai trên một long-lived context như chắc chắn nhận giá mới.

### 24.4. API trả entity JPA trực tiếp cho JSON serializer

Nếu serializer truy cập lazy relationship ngoài transaction, có thể phát sinh lỗi hoặc N+1 ẩn, đặc biệt khi OSIV bật. Cân nhắc DTO/projection cùng fetch plan được xác định tại service. Không mở rộng transaction hay context chỉ để cho serializer đi qua toàn bộ graph bất chấp nhu cầu thật.

### 24.5. Người dùng thao tác qua nhiều tab cùng một phiên

Nếu giữ một extended context gắn với phiên mà nhiều tab cùng dùng, có thể phát sinh thao tác đồng thời lên cùng graph. Mô hình này cần ranh giới concurrency rõ ràng. Một stateful context không phải giải pháp mặc định cho nhiều tab/người dùng; một API stateless với DTO và optimistic locking thường dễ kiểm soát hơn.

---

## 25. Checklist tư duy khi gặp lỗi về scope

Khi ứng dụng JPA có kết quả bất ngờ, hãy trả lời lần lượt:

1. **Entity đến từ đâu?** `new`, `find`, JPQL, `merge` hay deserialization?
2. **Nó hiện đang managed trong EntityManager nào?** `em.contains(entity)` có đúng không?
3. **Ai tạo EntityManager?** Ứng dụng gọi `emf.createEntityManager`, container inject hay Spring proxy?
4. **Persistence context có scope gì?** TRANSACTION, EXTENDED, application-managed, hay framework web request?
5. **Transaction nào active?** RESOURCE_LOCAL `EntityTransaction`, JTA, hay Spring `@Transactional`?
6. **Context có tham gia transaction đó không?** Đặc biệt khi dùng UNSYNCHRONIZED.
7. **Đã xảy ra flush chưa?** SQL có thể chạy trước commit nhưng vẫn rollback.
8. **Commit đã thành công chưa?** Có constraint/optimistic lock exception không?
9. **Object có bị detach/clear/close không?** Thay đổi trên detached có còn được track không?
10. **Có request hoặc thread khác dùng cùng EntityManager không?** Nếu có, đây là rủi ro thiết kế.
11. **Database có thể đã bị transaction khác cập nhật không?** Context hiện có có giữ state cũ không?
12. **Có OSIV hoặc lazy proxy không?** Query có chạy ở view/serialization ngoài transaction service không?
13. **Đã đo SQL và query plan thực tế chưa?** Không suy từ annotation thành kết luận tuyệt đối về thời điểm SQL.
14. **Use case cần một transaction duy nhất hay nhiều transaction?** Context không thay thế quyết định này.

Những câu hỏi đó giúp tách lỗi thuộc **lifecycle Java/JPA** khỏi lỗi thuộc **transaction/locking/database**.

---

## 26. Sơ đồ tổng hợp

```text
                  APPLICATION / SERVICE
                           |
                           v
                       EntityManager
                           |
                           v
                  Persistence Context
                  +-------------------+
                  | Identity map      |
                  | Managed entities  |
                  | Pending changes   |
                  | State tracking    |
                  +-------------------+
                           |
                    flush / queries
                           |
                           v
                       DATABASE
                           ^
                           |
                    TRANSACTION
                    begin / commit
                    rollback / locking


MÔ HÌNH 1 — TRANSACTION-SCOPED

TX #1:       [ begin ---------------- commit ]
PC #1:       [        managed state         ]

TX #2:                                         [ begin ---- commit ]
PC #2:                                         [ managed state    ]


MÔ HÌNH 2 — APPLICATION-MANAGED / EXTENDED

PC:          [----------------------------------------------]
TX #1:           [begin --- commit]
TX #2:                               [begin --- commit]
TX #3:                                             [begin -- commit]

Cùng context có thể đi qua nhiều transaction,
nhưng mỗi transaction vẫn có commit/rollback riêng.
```

## 27. Câu hỏi ôn tập

1. Persistence context có những trách nhiệm nào mà một transaction không có?
2. Vì sao hai lần `em.find` trong cùng context thường trả cùng Java object?
3. Hai EntityManager khác nhau có thể trả hai Java instances cùng biểu diễn một database row không?
4. Vì sao managed entity không nhất thiết chứng minh transaction đang active?
5. `flush()` khác `commit()` ở điểm nào?
6. Vì sao sau `rollback()`, object Java có thể vẫn giữ giá trị mới?
7. Transaction-scoped persistence context thường kết thúc khi nào trong container-managed JTA?
8. Extended persistence context khác transaction-scoped về vòng đời ở điểm nào?
9. Extended context có tự biến workflow nhiều request thành một transaction database duy nhất không?
10. Tại sao application-managed EntityManager còn mở sau `tx.commit()` có thể vẫn giữ managed entities?
11. Tại sao application-managed EntityManager và `@PersistenceContext(type=EXTENDED)` không hoàn toàn là cùng cơ chế?
12. `joinTransaction()` có bắt đầu transaction JTA mới không?
13. Spring `@Transactional` có buộc context trở thành extended không?
14. Vì sao singleton Spring service có injected EntityManager không có nghĩa EntityManager được chia sẻ trực tiếp như một context toàn cục?
15. OSIV có kéo dài transaction service tới cuối request không?
16. Khi entity detached được sửa, thay đổi có tự động flush không?
17. `merge` trả về điều gì và có biến detached input thành managed object không?
18. Context sống lâu có thể giữ stale data từ transaction khác như thế nào?
19. Khi nào cần `refresh`, `clear` hoặc context mới?
20. `@Version` có thể giải quyết phần nào của vấn đề concurrency nhưng không quyết định điều gì về scope?
21. Tại sao không nên chia sẻ một EntityManager để nhiều thread cùng dùng?
22. Với REST API stateless, vì sao transaction/context ngắn thường dễ quản lý?
23. Khi import dữ liệu lớn, `flush`/`clear` liên quan đến chi phí context như thế nào?
24. Có thể vừa có SQL `UPDATE` đã phát trong transaction, vừa không có thay đổi bền vững sau rollback không?

---

## 28. Bảng ghi nhớ cuối bài

| Câu hỏi | Trả lời ngắn |
|---|---|
| **Persistence context là gì?** | Vùng quản lý managed entity identity và trạng thái cần đồng bộ |
| **Transaction là gì?** | Ranh giới commit/rollback của một đơn vị công việc |
| **Hai scope có luôn trùng nhau?** | Không |
| **TRANSACTION context?** | Context thường gắn với một JTA transaction trong container-managed model |
| **EXTENDED context?** | Context có thể sống qua nhiều transaction |
| **Application-managed EM?** | Context theo vòng đời EM do ứng dụng tạo/đóng |
| **Managed sau commit?** | Tùy scope; có thể còn managed nếu EM/context còn sống |
| **Entity có ID có phải managed?** | Không; detached entity vẫn có ID |
| **Flush là commit?** | Không |
| **Commit có tự đóng mọi EntityManager?** | Không |
| **Rollback có tự undo field Java?** | Không nên giả định |
| **Đọc lazy sau đóng context?** | Có thể lỗi nếu collection/proxy chưa được load |
| **Spring @Transactional quyết định gì?** | Transaction boundary và propagation, không tự biến context thành EXTENDED |
| **OSIV quyết định gì?** | Có thể kéo dài EntityManager qua web request, không đồng nghĩa kéo dài service transaction |
| **Muốn tránh stale state?** | Context ngắn, refresh/reload khi cần và policy locking/version |
| **Muốn dùng entity giữa request?** | Ưu tiên ID/DTO/draft, tải lại trong unit of work phù hợp |

**Nguyên tắc quan trọng nhất:** *Persistence context trả lời câu hỏi “JPA đang quản lý những object Java nào và giữ chúng bao lâu?”, còn transaction trả lời “những thay đổi database nào được commit hoặc rollback cùng nhau?”.* Chỉ trong những cấu hình như **transaction-scoped context** hai khoảng thời gian này mới thường gần trùng nhau. Với **extended** hoặc **application-managed** context, persistence context có thể đi qua nhiều transaction — nhưng không vì thế mà transaction tự kéo dài, dữ liệu tự được commit, hoặc entity luôn phản ánh trạng thái mới nhất của database.

