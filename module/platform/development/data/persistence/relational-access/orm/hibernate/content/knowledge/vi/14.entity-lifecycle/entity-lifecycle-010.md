# Lỗi thực thể detached được đưa vào thao tác không phù hợp trong Hibernate ORM

Khi làm việc với Hibernate, một entity Java không chỉ mang dữ liệu mà còn có **trạng thái đối với persistence context**. Cùng một đối tượng có thể đang được Hibernate quản lý, đã tách khỏi Session, hoặc chưa từng được lưu. Nếu nhầm lẫn các trạng thái này, ứng dụng có thể nhận lỗi rất quen thuộc:

```text
org.hibernate.PersistentObjectException:
    detached entity passed to persist: com.example.Customer
```

Lỗi thường xuất hiện khi lập trình viên muốn tạo một bản ghi mới có tham chiếu đến một entity đã tồn tại, nhưng Hibernate lại nhận yêu cầu **`persist` chính entity đã tồn tại đó** — trực tiếp hoặc thông qua `CascadeType.PERSIST`. Một số trường hợp lỗi không xuất hiện tại lệnh gọi `persist()` mà bộc lộ khi `flush()` hoặc commit transaction, khiến việc lần theo nguyên nhân khó hơn.

Bài học giải thích trạng thái **transient, managed, detached, removed**; hợp đồng của `persist`, `merge` và các thao tác khác; lý do cascade đưa entity detached vào đường xử lý không hợp lệ; cùng các giải pháp an toàn trong kiến trúc Hibernate/Jakarta Persistence và Spring.

## 1. Bắt đầu từ vòng đời entity

Một object entity có thể trải qua những trạng thái sau:

| Trạng thái | Ý nghĩa | Hibernate có theo dõi thay đổi để ghi tự động không? |
|---|---|---|
| **Transient / new** | Object mới tạo, chưa thuộc persistence context và chưa được thiết lập là một entity đã lưu | Không |
| **Managed / persistent** | Object đang gắn với một persistence context hoạt động | Có, thông qua dirty checking và flush |
| **Detached** | Object từng đại diện cho entity được quản lý/lưu, nhưng hiện không thuộc persistence context đang sử dụng | Không, đối với context hiện tại |
| **Removed** | Entity đang được quản lý và đã được đánh dấu để xóa trong persistence context | Hibernate xử lý xóa khi flush theo lifecycle |

Sơ đồ ý tưởng:

```text
new Customer(...)
      |
      | em.persist(customer)
      v
  MANAGED ------------------+
      |                     |
      | em.detach(...)      | em.remove(...)
      | em.clear()          v
      | em.close()        REMOVED
      | context kết thúc     |
      v                      | flush/commit
  DETACHED                  v
      |               DELETE khỏi database
      |
      | em.merge(detached)
      v
  Managed copy (có thể là object khác)
```

Sơ đồ rút gọn để nhấn mạnh thao tác chính. Hibernate còn có các trường hợp chuyển trạng thái, flush và rollback cụ thể tùy trạng thái ban đầu, cascade và quy tắc persistence context.

### 1.1. Transient: object chưa được quản lý

Ví dụ:

```java
Customer customer = new Customer("An");
```

Đối tượng vừa tạo **chưa tự động được Hibernate lưu**. Dù entity có các trường giống với một hàng database, Hibernate không theo dõi nó cho tới khi nó tham gia một persistence context theo một thao tác thích hợp.

### 1.2. Managed: entity trong một persistence context

```java
Customer customer = em.find(Customer.class, customerId);
customer.changeName("An Nguyễn");
```

Khi `customer` được `find` thành công và `em` còn quản lý nó, thay đổi tên có thể được phát hiện và đồng bộ thành `UPDATE` khi flush trong transaction hợp lệ. Không cần gọi `persist(customer)` lần nữa chỉ để lưu thay đổi của managed entity.

### 1.3. Detached: có dữ liệu entity nhưng không còn được context quản lý

```java
Customer detached;

EntityManager first = emf.createEntityManager();
try {
    detached = first.find(Customer.class, customerId);
} finally {
    first.close();
}

// EntityManager first đã đóng; detached không còn managed tại đây.
detached.changeName("Tên mới");
```

Đối tượng vẫn là một instance `Customer` Java, vẫn giữ ID và các giá trị đã tải. Nhưng vì persistence context ban đầu đã đóng, Hibernate **không tự ghi thay đổi** khi code sửa `detached` ở bên ngoài context.

Một `EntityManager` mới không tự động nhận quản lý đối tượng ấy chỉ vì nó có ID hợp lệ.

### 1.4. Removed: đã được yêu cầu xóa

```java
Customer customer = em.find(Customer.class, customerId);
em.remove(customer);
```

Trong transaction phù hợp, entity được đánh dấu để xóa; SQL `DELETE` thường được đồng bộ khi flush. Điều này khác việc đưa một object detached bất kỳ vào `remove`.

## 2. Detached không đồng nghĩa “không có ID”

Nhiều đoạn code kiểm tra:

```java
if (customer.getId() == null) {
    em.persist(customer);
} else {
    em.persist(customer); // Sai: không phải đối tượng có ID nào cũng là new.
}
```

Một entity đã detached thường **có ID**, bởi nó đã từng được đọc hoặc lưu. Nhưng quy tắc “ID khác null thì chắc chắn detached” cũng không tuyệt đối:

- Entity mới với khóa **assigned ID** có thể được cấp ID trước `persist`.
- Entity dùng generated ID thường bắt đầu với `id == null`, rồi nhận ID khi generator chạy.
- Một object được khởi tạo từ request/DTO và gán ID có thể bị Hibernate xem là detached hoặc có hành vi khác tùy generator, version và unsaved-value strategy.
- Entity đã rollback sau khi nhận generated ID không chắc quay ID về null.
- Một object có ID có thể đang **managed** trong context khác nhưng không managed ở context hiện tại.

Vì vậy, **trạng thái của entity được xác định trong quan hệ với persistence context và hợp đồng generator**, không thể suy ra đầy đủ từ một trường số.

### Kiểm tra `contains()`

`EntityManager.contains(entity)` cho biết object có được **EntityManager đang xét** quản lý không:

```java
boolean managedHere = em.contains(customer);
```

Kết quả `false` có thể là transient, detached hoặc object không thuộc context này. `contains()` **không phải công cụ phân loại tất cả trạng thái entity**. Nó chỉ trả lời câu hỏi “đối tượng này có đang được context hiện tại quản lý không?”.

Nếu một instance đang managed trong `EntityManager A`, nó **không tự động managed** trong `EntityManager B`. Mỗi persistence context có identity map và vòng đời riêng.

## 3. `persist` có hợp đồng gì?

`EntityManager.persist(entity)` dùng để **đưa một entity mới vào trạng thái managed** để Hibernate có thể insert nó. Với object transient hợp lệ:

```java
Customer customer = new Customer("An");

em.persist(customer);
// customer được quản lý; việc INSERT xảy ra theo generator/flush.
```

Nhưng với một object đã detached:

```java
Customer detachedCustomer = loadCustomerInOldEntityManager();

em.persist(detachedCustomer); // Không phải thao tác phù hợp.
```

Theo hợp đồng Jakarta Persistence, việc đưa detached entity vào `persist` có thể dẫn đến `EntityExistsException`, hoặc một `PersistenceException` khác tại thời điểm gọi, flush hoặc commit. Trong Hibernate native, lỗi thường thấy là:

```text
org.hibernate.PersistentObjectException:
    detached entity passed to persist: com.example.Customer
```

Điều quan trọng là **nguyên nhân**, không phải giả định một loại exception giống nhau ở mọi môi trường. Spring có thể bọc hoặc dịch exception; Hibernate/JPA version và thời điểm flush cũng ảnh hưởng lớp exception bên ngoài.

### Vì sao Hibernate từ chối?

`persist` diễn đạt ý định “đây là entity mới cần được lưu”, trong khi object detached đại diện cho **identity đã có hoặc từng được quản lý**. Hibernate không được tự giả định rằng yêu cầu persist là “update bản ghi cùng ID” hoặc “tạo lại bản ghi đã tồn tại”.

Nếu làm vậy, ranh giới giữa insert và update sẽ trở nên mơ hồ và có thể dẫn đến:

- Ghi đè hàng không chủ ý.
- Trùng khóa chính.
- Xóa mất dữ liệu do graph detached chứa trường chưa cập nhật.
- Vượt qua quy tắc optimistic locking và concurrency.
- Không rõ bản ghi nên được tạo mới hay cập nhật.

Việc lỗi sớm giúp ứng dụng phát hiện **sai ý định vòng đời** thay vì thực hiện âm thầm một thao tác dữ liệu khác.

## 4. Ví dụ trực tiếp gây lỗi: persist entity đã detach

Giả sử có entity:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public void changeName(String name) {
        this.name = name;
    }
}
```

Một giao dịch ban đầu tạo customer:

```java
Long customerId;

EntityManager first = emf.createEntityManager();
EntityTransaction firstTx = first.getTransaction();

try {
    firstTx.begin();

    Customer customer = new Customer("An");
    first.persist(customer);

    firstTx.commit();
    customerId = customer.getId();
} finally {
    first.close();
}
```

Sau đó, một context mới tải customer, rồi đóng:

```java
Customer detached;

EntityManager reader = emf.createEntityManager();
try {
    detached = reader.find(Customer.class, customerId);
} finally {
    reader.close();
}
```

Bây giờ:

```java
EntityManager writer = emf.createEntityManager();
EntityTransaction tx = writer.getTransaction();

try {
    tx.begin();

    writer.persist(detached); // Sai mục đích: detached không phải new.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    writer.close();
}
```

Hibernate có thể báo `detached entity passed to persist`. Nếu intent chỉ là **sửa tên** khách hàng đã tồn tại, đúng hơn là tải customer managed trong transaction hiện tại rồi thay đổi:

```java
Customer managed = writer.find(Customer.class, customerId);
managed.changeName("An Nguyễn");
```

Không có lý do gọi `persist` với customer đã tồn tại.

**Đặc biệt:** không nên “sửa lỗi” bằng cách gán `detached.id = null`. Với generated ID, việc xóa ID có thể khiến Hibernate tạo **một hàng mới khác** thay vì cập nhật đúng hàng, làm phát sinh trùng dữ liệu nghiệp vụ hoặc phá vỡ liên kết.

## 5. Nguyên nhân hay gặp nhất: cascade PERSIST qua association

Nhiều trường hợp code **không trực tiếp** gọi `persist(detachedCustomer)`. Nó chỉ persist một entity mới, nhưng association có cascade khiến Hibernate lan thao tác sang một entity đã tồn tại.

Ví dụ mô hình đơn hàng:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(
        fetch = FetchType.LAZY,
        cascade = CascadeType.PERSIST // Dễ sai cho customer đã tồn tại.
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = customer;
    }
}
```

Code nghiệp vụ:

```java
// customer được trả về từ một EntityManager đã đóng.
Customer detachedCustomer = loadExistingCustomer();

PurchaseOrder order = new PurchaseOrder(detachedCustomer);

em.persist(order);
```

Lời gọi trực tiếp chỉ là `persist(order)`, nhưng Hibernate diễn giải cascade:

```text
em.persist(order)
    |
    v
PurchaseOrder là entity mới
    |
    +-- CascadeType.PERSIST trên order.customer
           |
           v
       persist(customer)
           |
           v
       Customer đã detached
           |
           v
    "detached entity passed to persist"
```

Đây là lý do stack trace có thể nêu **`Customer`**, dù lập trình viên đang muốn lưu `PurchaseOrder`.

### Vì sao `CascadeType.ALL` còn dễ gây nhầm?

`CascadeType.ALL` bao gồm nhiều thao tác cascade như `PERSIST`, `MERGE`, `REMOVE`, `REFRESH` và `DETACH`. Vì vậy:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

cũng có thể đưa `Customer` detached vào đường cascade persist.

Hơn nữa, `REMOVE` từ đơn hàng sang customer còn nguy hiểm: xóa một đơn hàng **không nên tự xóa khách hàng** khi khách hàng có thể sở hữu nhiều đơn hàng.

**Nguyên tắc:** cascade mô tả **quyền sở hữu vòng đời**, không phải “hãy tự lưu mọi thứ liên quan”. Với quan hệ tham chiếu đến entity đã tồn tại, dùng cascade một cách chọn lọc, thậm chí không dùng cascade, thường an toàn hơn.

## 6. Sửa ví dụ: giữ customer là một tham chiếu đã được quản lý

Nếu đơn hàng **mới** tham chiếu đến khách hàng **đã tồn tại**, hãy để khách hàng được quản lý trong transaction hiện tại và persist **đơn hàng**.

Mapping phù hợp:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "customer_id", nullable = false)
private Customer customer;
```

Không có `CascadeType.PERSIST` từ order sang customer.

Service sử dụng `find`:

```java
import jakarta.persistence.EntityManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final EntityManager em;

    public OrderService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void createOrder(Long customerId) {
        Customer customer = em.find(Customer.class, customerId);

        if (customer == null) {
            throw new IllegalArgumentException("Customer not found");
        }

        PurchaseOrder order = new PurchaseOrder(customer);
        em.persist(order);
    }
}
```

Ví dụ giả định Spring đang cấu hình đúng transaction manager và entity mapping. Khi `em.find` thành công, `customer` managed trong persistence context hiện tại. Hibernate có thể dùng ID của customer làm khóa ngoại để insert đơn hàng.

### Khi đã biết ID, dùng `getReference()`

Nếu use case chỉ cần tạo liên kết qua ID và không cần tải chi tiết customer:

```java
Customer customerRef = em.getReference(
    Customer.class,
    customerId
);

PurchaseOrder order = new PurchaseOrder(customerRef);
em.persist(order);
```

Với Hibernate, `getReference` thường có thể trả proxy/reference mà chưa phải SELECT toàn bộ customer. Nhưng:

- Không bảo đảm customer ID thực sự tồn tại ngay tại thời điểm gọi.
- Nếu customer không tồn tại, lỗi có thể xuất hiện lúc truy cập proxy hoặc khi database kiểm tra khóa ngoại.
- Không thay thế kiểm tra quyền truy cập hoặc trạng thái nghiệp vụ.
- `getReference` hoạt động trong **persistence context hiện hành**, không phải cách “attach” lại chính Java instance detached ban đầu.

Nếu quy tắc nghiệp vụ yêu cầu customer đang hoạt động hoặc người dùng có quyền tạo đơn, nên dùng truy vấn/validation thích hợp thay vì chỉ lấy reference.

## 7. Một kiểu lỗi tương tự: một object mới giả làm entity đã tồn tại

Ở API REST, client thường gửi dữ liệu kiểu:

```json
{
  "customerId": 42,
  "items": [
    {"productId": 100, "quantity": 2}
  ]
}
```

Một cách làm không nên:

```java
Customer customer = new Customer();
customer.setId(request.customerId()); // Tự gắn ID generated.

PurchaseOrder order = new PurchaseOrder(customer);
em.persist(order);
```

Object `customer` vừa được tạo nhưng mang ID có vẻ như của bản ghi đã tồn tại. Với generated identifier, Hibernate có thể nhận diện nó như detached, hoặc gặp một lỗi khác khi cascade/flush. Kể cả khi không báo lỗi, đây vẫn không phải cách xác nhận liên kết phù hợp.

Cách đúng thường là **nhận ID ở ranh giới API**, rồi dùng `find` hoặc `getReference` trong service đang có transaction:

```java
Customer managed = em.find(Customer.class, request.customerId());

if (managed == null) {
    throw new IllegalArgumentException("Unknown customer");
}

PurchaseOrder order = new PurchaseOrder(managed);
em.persist(order);
```

Không biến request body thành một entity graph mang ID để Hibernate phải đoán object nào mới, object nào cũ.

### Tại sao constructor/setter ID cần được kiểm soát?

Với generated ID:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

ID nên được coi là **kết quả của cơ chế sinh khóa**, không phải thuộc tính nghiệp vụ để client tự ý sửa. Một entity mới có ID giả có thể khiến hành vi Hibernate khó dự đoán, đặc biệt khi cùng lúc cấu hình cascade và merge.

## 8. `merge` không phải là một cách viết khác của `persist`

Khi cần **đưa thay đổi của một entity detached vào persistence context mới**, Jakarta Persistence có `EntityManager.merge`.

Ví dụ:

```java
Customer detached = loadCustomerInOldEntityManager();
detached.changeName("Tên mới");

Customer managed = em.merge(detached);
```

Hợp đồng cần nhớ:

> `merge(detached)` **sao chép trạng thái** của object detached sang một managed instance tương ứng và **trả về managed instance đó**. Object truyền vào không tự biến thành managed chỉ vì đã gọi `merge`.

Sơ đồ:

```text
Detached Customer D
   id = 42
   name = "Tên mới"
          |
          | em.merge(D)
          v
Hibernate tìm/tạo managed instance M tương ứng
          |
          | copy state từ D sang M
          v
Managed Customer M
   id = 42
   name = "Tên mới"
          |
          v
em.merge(...) trả về M

D vẫn detached; M thuộc persistence context hiện tại.
```

Có thể xảy ra:

```java
Customer managed = em.merge(detached);

System.out.println(managed == detached); // Thường false.
System.out.println(em.contains(detached)); // false.
System.out.println(em.contains(managed));  // true.
```

Trong một số trường hợp, input đã là managed nên `merge` có thể trả cùng instance, nhưng đừng thiết kế code dựa trên giả định `merge` luôn trả instance khác hoặc luôn trả cùng instance. Hãy **sử dụng kết quả trả về**.

### Bẫy: tiếp tục sửa object detached sau merge

```java
Customer managed = em.merge(detached);

detached.changeName("Thay đổi lần hai"); // Vẫn trên object detached.
```

Thay đổi lần hai **không tự động được Hibernate đồng bộ** chỉ vì trước đó đã merge. Nếu muốn tiếp tục chỉnh sửa trong transaction, sửa `managed`:

```java
Customer managed = em.merge(detached);
managed.changeName("Thay đổi lần hai");
```

### `merge` có thể đọc database

Hibernate có thể cần tìm entity managed theo ID, tải trạng thái hiện tại hoặc tạo instance tương ứng để hợp nhất dữ liệu; vì thế `merge` có thể tạo thêm `SELECT` và sau đó `UPDATE` khi flush. Không nên xem `merge` là “UPDATE SQL trực tiếp” hoặc “attach không tốn truy vấn”.

`merge` cũng có thể được dùng cho một entity mới theo quy tắc JPA, nhưng việc dùng nó **mù quáng** cho cả create/update che khuất ý định và có thể tạo SQL không mong muốn. Nếu có workflow rõ là **tạo mới**, `persist` thường dễ hiểu hơn.

## 9. Khi nào nên chọn `persist`, `find`, `getReference` hoặc `merge`?

| Nhu cầu thực tế | Thao tác thường phù hợp | Điều cần nhớ |
|---|---|---|
| Tạo entity mới chưa lưu | `em.persist(newEntity)` | Đặt đúng cascade cho các child thực sự mới |
| Cập nhật entity đã tồn tại | `em.find(...); managed.change...` | Dirty checking ghi thay đổi khi flush |
| Tạo entity mới tham chiếu parent đã tồn tại | `em.find` hoặc `em.getReference` cho parent, rồi `persist(child)` | Không cascade persist sang parent đã tồn tại |
| Áp dụng trạng thái từ một entity detached | `em.merge(detached)` và dùng kết quả trả về | Có nguy cơ ghi đè dữ liệu khi graph detached cũ/không đầy đủ |
| Xóa entity đã tồn tại | `em.find/getReference` phù hợp rồi `em.remove(managed)` | `remove` cần managed reference theo hợp đồng JPA |
| Làm mới state của managed entity từ database | `em.refresh(managed)` | Không phải thao tác dành cho detached object tùy ý |
| Chỉ cần kiểm tra có thuộc context hiện tại không | `em.contains(entity)` | `false` không phân biệt transient và detached |

Không có một thao tác “cứ gọi là Hibernate tự suy ra phải insert hay update đúng mong muốn” cho mọi đối tượng. Trước tiên, xác định **nghiệp vụ là tạo mới, tham chiếu hay cập nhật**.

### So sánh theo thao tác trên object detached

```java
Customer detached = /* entity từ context cũ */;
```

- `em.persist(detached)`: không hợp lệ theo ý định tạo mới; có thể báo lỗi detached entity passed to persist.
- `em.merge(detached)`: hợp nhất state vào managed instance; trả về managed instance, cần xử lý concurrency và graph.
- `em.remove(detached)`: không phải cách xóa đúng cho detached object theo JPA; nên lấy managed entity phù hợp.
- `em.refresh(detached)`: không phải thao tác làm mới detached object theo contract thông thường.
- `em.detach(detached)`: không “attach” object; thao tác detach áp dụng khi cần tách entity đang managed.

Đọc tên phương thức theo **ngữ nghĩa** thay vì suy đoán từ việc object có ID.

## 10. `merge` và nguy cơ ghi đè trường không chủ ý

Dù `merge` là thao tác được hỗ trợ cho detached entity, nó **không phải lời giải tự động cho mọi lỗi persist**.

Giả sử một form chỉnh sửa chỉ có tên:

```json
{
  "id": 42,
  "name": "Tên mới"
}
```

Nhưng entity thật còn các trường:

```java
private String name;
private String email;
private String phone;
private boolean active;
```

Nếu tạo một entity giả từ payload:

```java
Customer detached = new Customer();
detached.setId(request.id());
detached.setName(request.name());
// email, phone vẫn null; active mặc định false.

em.merge(detached);
```

Hibernate có thể sao chép cả trạng thái không được client gửi — các trường `null` hoặc giá trị mặc định — vào managed instance. Kết quả có thể **xóa email/phone hoặc đổi active** ngoài ý muốn, tùy cấu trúc mapping và payload.

Cách ít mơ hồ hơn là tải entity managed rồi áp dụng **chỉ những trường có quyền thay đổi**:

```java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = em.find(Customer.class, id);

    if (customer == null) {
        throw new IllegalArgumentException("Customer not found");
    }

    customer.changeName(newName);
}
```

Ở đây, Hibernate theo dõi thay đổi của managed entity; các thuộc tính khác không bị ghi đè chỉ vì không xuất hiện trong request.

### `merge` không phải PATCH

Một API `PATCH` thường có ý nghĩa **chỉ cập nhật các trường được yêu cầu**. `merge` có ngữ nghĩa sao chép state của object graph, không phải tự xác định các trường nào client cố tình bỏ qua.

Nếu phải dùng merge cho detached graph, cần:

- Xác nhận graph detached chứa trạng thái đầy đủ và hợp lệ.
- Có quy tắc kiểm soát trường được phép thay đổi.
- Sử dụng version/optimistic locking khi có cập nhật cạnh tranh.
- Hiểu cascade merge với các association.
- Không tin object được tạo trực tiếp từ request như một mô hình entity hoàn chỉnh.

## 11. Cascade PERSIST và cascade MERGE là hai thao tác khác nhau

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<OrderLine> lines = new ArrayList<>();
```

- `CascadeType.PERSIST`: khi persist order, thao tác persist có thể lan sang các line liên quan.
- `CascadeType.MERGE`: khi merge order, thao tác merge có thể lan sang line theo mapping.
- `CascadeType.ALL` bao gồm cả hai cùng những cascade operation khác.
- **Cascade không đồng nghĩa đối tượng con tự nhiên là new hay detached**; Hibernate vẫn phải đánh giá từng entity và thao tác đang lan truyền.

### 11.1. Cascade PERSIST phù hợp với child mới thuộc aggregate

Ví dụ tạo đơn hàng và các dòng mới:

```java
PurchaseOrder order = new PurchaseOrder(customerManaged);

order.addLine(new OrderLine("SKU-1", 2));
order.addLine(new OrderLine("SKU-2", 1));

em.persist(order);
```

Nếu `OrderLine` có vòng đời thuộc `PurchaseOrder` và mapping `cascade = PERSIST` từ order tới lines, Hibernate có thể lưu các line mới cùng order.

Điều này khác hoàn toàn với `Customer`, vốn là một entity **đã tồn tại độc lập**. Cascade PERSIST từ order sang customer thường không phù hợp.

### 11.2. Khi child collection trộn mới và detached

Xét một aggregate:

```text
Order mới:
  - Line A: new, id = null
  - Line B: detached, id = 500
```

Nếu mapping `cascade = PERSIST` xuống lines, Hibernate có thể cố persist cả Line A **và** Line B. Line B đã detached nên có nguy cơ gây lỗi tương tự.

Trước khi persist object graph, phải biết mỗi node là entity **mới thực sự** hay entity **đã tồn tại**. Không nên gom object cũ và mới vào một graph rồi trông chờ cascade “tự nhận ra nên merge cái nào”.

Trong một số domain, việc tạo order mới chứa lại `OrderLine` của order cũ cũng là vấn đề mô hình hóa: một dòng đơn hàng thường **không thể thuộc hai đơn hàng**. Khi muốn sao chép, phải tạo **OrderLine mới với dữ liệu được sao chép**, không dùng lại entity con cũ.

## 12. Một nguyên nhân khác: dùng entity qua nhiều transaction

Trong ứng dụng có service/repository, detached thường hình thành khi entity vượt qua ranh giới transaction.

Ví dụ hai phương thức Spring:

```java
@Service
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer load(Long id) {
        return repository.findById(id).orElseThrow();
    }
}
```

Service tiếp theo:

```java
@Service
public class OrderWriteService {

    private final CustomerLookupService lookup;
    private final OrderRepository orders;

    @Transactional
    public void create(Long customerId) {
        Customer customer = lookup.load(customerId);
        PurchaseOrder order = new PurchaseOrder(customer);
        orders.save(order);
    }
}
```

**Không thể kết luận `customer` detached chỉ vì nó đi qua hai phương thức** trong ví dụ này: khi transaction bên ngoài vẫn hoạt động và Spring dùng cùng transaction-bound persistence context, lookup có thể tham gia cùng context, nên customer vẫn managed.

Tuy nhiên, nếu lookup được gọi trong một transaction **đã kết thúc**, hoặc qua một EntityManager độc lập, hoặc dữ liệu đi qua thread/task khác, object trả về có thể detached đối với thao tác ghi tiếp theo.

Các trường hợp phổ biến tạo detached:

- Controller giữ entity sau khi service transaction đã kết thúc.
- Entity được serialize/deserialize giữa request.
- Object được đưa vào cache ứng dụng rồi sử dụng lại ở transaction khác.
- Entity được gửi qua message queue, job async hoặc thread khác.
- Mã trực tiếp gọi `EntityManager.close()`, `clear()` hoặc `detach()`.
- Một entity được tải bởi `EntityManager A` rồi đem sang `EntityManager B`.

### Ranh giới thiết kế tốt hơn: truyền ID hoặc DTO

Thay vì truyền nguyên entity qua ranh giới dài:

```java
public void createOrder(Long customerId) {
    // Trong transaction ghi:
    Customer customer = em.find(Customer.class, customerId);
    em.persist(new PurchaseOrder(customer));
}
```

Truyền `customerId` hoặc một DTO bất biến giúp đơn vị công việc mới chủ động quyết định **đối tượng nào cần quản lý, dữ liệu nào cần đọc và thao tác nào cần ghi**.

Entity không phải DTO “có thể mang đi đâu cũng tự cập nhật”.

## 13. Khi Spring Data JPA `save(...)` tham gia vào câu chuyện

Spring Data JPA thường cung cấp:

```java
repository.save(entity);
```

Tùy cơ chế nhận diện entity mới, repository có thể chọn `EntityManager.persist` hoặc `EntityManager.merge`. Việc chọn này có thể dựa vào ID, trường `@Version`, hoặc `Persistable.isNew()` và cơ chế cấu hình khác.

Vì thế không nên hiểu `save` là một câu SQL `INSERT ... ON CONFLICT DO UPDATE`, cũng không nên cho rằng mọi lần `save` đều tương đương `persist`.

### 13.1. `save(newOrder)` vẫn có thể cascade vào detached Customer

Nếu `Order` được Spring Data xem là new, `save` có thể gọi `persist(order)`. Với mapping:

```java
@ManyToOne(cascade = CascadeType.PERSIST)
private Customer customer;
```

thì cascade vẫn có thể dẫn tới lỗi `detached entity passed to persist` cho Customer.

Việc code gọi `save` thay vì `persist` **không xóa bỏ vấn đề ownership của cascade**.

### 13.2. `saveAndFlush` không khắc phục sai trạng thái

`saveAndFlush` yêu cầu đồng bộ thay đổi sớm hơn theo hợp đồng Spring Data, nhưng nếu graph có detached entity bị persist sai, flush có thể chỉ làm lỗi xuất hiện sớm hơn.

Không nên coi “thêm flush” là biện pháp xử lý tình trạng detached.

### 13.3. Assigned ID và nhận diện `isNew`

Nếu entity dùng khóa gán thủ công, việc ID khác null chưa chắc có nghĩa nó đã tồn tại trong DB. Một số dự án dùng `Persistable` hoặc trường version nullable để Spring Data nhận diện new entity.

Cấu hình sai cơ chế `isNew` có thể khiến một entity mới được merge khi lẽ ra nên persist, hoặc ngược lại. Vì vậy cần tách bạch:

1. **Chính sách nhận diện new của Spring Data.**
2. **Trạng thái entity so với persistence context.**
3. **Chiến lược identifier của Hibernate.**
4. **Ý định nghiệp vụ tạo hay cập nhật.**

Đây là bốn khía cạnh liên quan nhưng không thể thay thế nhau.

## 14. `@Version` và cập nhật detached an toàn hơn

Một entity detached có thể chứa dữ liệu **cũ** so với database. Giả sử hai người cùng chỉnh sửa customer:

```text
T1 đọc Customer(version=3, name="An")
T2 đọc Customer(version=3, name="An")

T2 cập nhật name="An B", version -> 4, commit
T1 merge trạng thái cũ name="An C", version=3
```

Nếu entity không có chiến lược optimistic locking phù hợp, T1 có thể ghi đè thay đổi của T2.

Thêm `@Version`:

```java
@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private String name;

    protected Customer() {
    }

    public void changeName(String name) {
        this.name = name;
    }
}
```

Hibernate dùng version để hỗ trợ phát hiện cạnh tranh khi update/delete tương ứng. Khi đối tượng detached có version cũ được merge và ghi, ứng dụng có thể nhận `OptimisticLockException` hoặc ngoại lệ tương đương được Hibernate/Spring bọc lại, tùy thời điểm kiểm tra.

Điều quan trọng:

- `@Version` là **cơ chế tránh lost update**, không phải “biến detached thành managed”.
- Không tự sửa hoặc giả mạo version từ client.
- Khi conflict xảy ra, phải đưa ra chính sách retry, reload, hiển thị xung đột hoặc yêu cầu người dùng quyết định.
- Không cố vượt conflict bằng cách xóa version hoặc ép `persist`.

### Cẩn thận với đối tượng có ID nhưng version null

Với một số cơ chế Hibernate xác định entity mới/detached, giá trị version nullable có thể ảnh hưởng đến cách suy luận unsaved state. Một object được tạo từ request chỉ có ID mà thiếu version có thể được đánh giá khác dự kiến, đặc biệt trong version Hibernate mới.

Không nên tự chế một entity detached bằng `new Customer(); setId(...); setVersion(null)` rồi dựa vào `merge` để Hibernate “tự hiểu”. Hãy dùng DTO và tải managed entity hoặc một phương thức cập nhật có hợp đồng rõ ràng.

## 15. Cascade MERGE qua graph có thể gây mất dữ liệu

Giả sử `Order` có collection lines, và client chỉ gửi một phần:

```text
Database:
  Order 10 có Line 1, Line 2, Line 3

Request:
  Order 10 chỉ chứa Line 1
```

Nếu code tạo graph detached mới với collection chỉ có Line 1 rồi gọi `merge(order)`, Hibernate có thể đồng bộ collection theo mapping và hành vi cascade, dẫn đến việc thay đổi hoặc xóa những phần tử không có trong request — nhất là khi dùng `orphanRemoval = true`.

Không phải mọi quan hệ đều được đồng bộ giống nhau; kết quả còn phụ thuộc owning side và cách collection được khởi tạo. Nhưng rủi ro **graph detached không đầy đủ** là có thật.

### Phương án cho PATCH collection

Tải aggregate managed:

```java
Order managed = em.find(Order.class, request.orderId());

if (managed == null) {
    throw new IllegalArgumentException("Order not found");
}

// Áp dụng chính xác những thay đổi được yêu cầu:
managed.changeShippingAddress(request.shippingAddress());

for (LineChange change : request.lineChanges()) {
    managed.applyLineChange(change);
}
```

Các method domain `changeShippingAddress` và `applyLineChange` là ví dụ, cần được triển khai theo invariant của aggregate. Điểm chính là **không dùng việc thiếu dữ liệu trong request như tín hiệu xóa mọi entity liên quan**, trừ khi API có chủ đích thay thế toàn bộ collection.

## 16. Có thể gọi `persist` trên managed entity không?

Một managed entity đã thuộc persistence context hiện tại. Theo contract JPA, gọi `persist` trên managed entity thường được **bỏ qua đối với chính entity ấy**, nhưng thao tác cascade `PERSIST` vẫn có thể lan đến các association được cấu hình.

Ví dụ:

```java
Customer customer = em.find(Customer.class, customerId);
em.persist(customer);
```

Không cần thiết để “lưu thay đổi”. Nếu customer mang các association có cascade PERSIST đến entity khác, thao tác có thể kích hoạt cascade ở graph và phát sinh hành vi không mong đợi.

Chỉ cần:

```java
Customer customer = em.find(Customer.class, customerId);
customer.changeName("Tên mới");
// Dirty checking và transaction sẽ xử lý cập nhật.
```

Đó là sự khác biệt quan trọng giữa **gắn trạng thái object vào persistence context** và **yêu cầu flush/commit**.

## 17. `remove` cũng cần đúng trạng thái

Một biến thể của cùng vấn đề xuất hiện khi xóa:

```java
Customer detached = loadCustomerInClosedContext();
em.remove(detached); // Không phải cách xóa đúng theo JPA.
```

`EntityManager.remove` được định nghĩa cho managed entity phù hợp. Với detached object, JPA có thể báo `IllegalArgumentException` hoặc lỗi tương ứng.

Cách rõ ràng:

```java
Customer managed = em.find(Customer.class, detached.getId());
if (managed != null) {
    em.remove(managed);
}
```

Hoặc sử dụng reference managed nếu semantics và khả năng kiểm tra sự tồn tại của use case cho phép:

```java
Customer ref = em.getReference(Customer.class, customerId);
em.remove(ref);
```

Hãy cân nhắc FK, authorization và quy tắc nghiệp vụ trước khi xóa. Lấy một reference không tự kiểm tra quyền xóa hay mọi liên kết còn tồn tại.

### `remove` trên detached khác `merge` rồi remove

Có thể gặp code:

```java
Customer managed = em.merge(detached);
em.remove(managed);
```

Về mặt kỹ thuật có thể phù hợp trong một số trường hợp, nhưng nếu mục tiêu **chỉ là xóa theo ID**, merge toàn bộ state detached có thể thừa truy vấn hoặc lan cascade merge không cần thiết. Tải managed entity theo ID rồi xóa thường dễ hiểu hơn.

## 18. Hibernate native `Session` và các API cập nhật legacy

Ngoài Jakarta Persistence `EntityManager`, Hibernate có native `Session`. Trong các phiên bản/lịch sử Hibernate, những phương thức như `update`, `saveOrUpdate`, `replicate` hoặc cách “reattach” entity có semantics khác `merge`.

Một điểm phân biệt quan trọng:

- `merge` thường **sao chép state vào managed instance** và trả về object được quản lý.
- Một số API native reattachment lịch sử có mục tiêu **gắn lại chính instance detached**, thường đòi hỏi persistence context chưa chứa một managed instance khác có cùng entity identity.

Nếu context đã có `Customer(id=42)` managed, rồi code cố reattach một instance khác cũng mang `id=42`, Hibernate có thể báo lỗi kiểu:

```text
A different object with the same identifier value
was already associated with the session
```

hoặc một exception cùng bản chất như `NonUniqueObjectException`, tùy API/version.

Các API native thay đổi qua các phiên bản Hibernate; một số đã được khuyến nghị thay bằng `merge` hoặc `persist`, hoặc không còn được ưu tiên. Với code mới, thường nên dùng API JPA rõ ràng trừ khi có yêu cầu Hibernate-specific và đã kiểm tra tài liệu phiên bản.

**Không thay `persist` bằng `update` một cách máy móc**. Nó thay đổi semantics và có thể gây xung đột identity trong persistence context.

## 19. Phân biệt lỗi detached với một số lỗi gần giống

Không phải mọi exception khi ghi graph đều là cùng một nguyên nhân.

| Thông báo/nhóm lỗi thường gặp | Nguyên nhân khả dĩ | Cần kiểm tra |
|---|---|---|
| `detached entity passed to persist` | Persist trực tiếp/cascade đến entity được nhận diện là detached | Trạng thái entity, cascade PERSIST, graph đi qua |
| `object references an unsaved transient instance` hoặc `TransientObjectException` | Entity tham chiếu tới một object **mới chưa được lưu**, trong khi đường thao tác không xử lý liên kết đó | Persist target mới theo lifecycle phù hợp hoặc cấu hình cascade đúng |
| `NonUniqueObjectException` | Một Session có hai Java instance khác nhau cùng entity type + ID khi cố gắn thêm instance | Identity map, cách reattach, merge, nhiều context |
| `EntityExistsException` | Persist object mâu thuẫn với entity đã tồn tại hoặc provider nhận diện detached | ID, generator, tồn tại row, flush |
| `ConstraintViolationException` (Hibernate SQL) | Database từ chối FK/unique/NOT NULL/check constraint | DDL, dữ liệu đang ghi, thứ tự insert |
| `OptimisticLockException` / stale state | Version hoặc row không còn phù hợp khi cập nhật/xóa | `@Version`, concurrent update/delete, merge detached cũ |
| `LazyInitializationException` | Truy cập dữ liệu lazy sau khi entity detached/Session đóng | Ranh giới transaction, fetch plan |
| `PropertyValueException` | Thuộc tính/association bắt buộc null hoặc không hợp lệ theo mapping | Nullability, owning side, trạng thái graph |

### Một cặp nguyên nhân trái ngược

**Transient target chưa lưu:**

```java
Customer newCustomer = new Customer("An");
PurchaseOrder order = new PurchaseOrder(newCustomer);

// Nếu không persist customer hoặc không có cascade phù hợp,
// flush có thể lỗi vì tham chiếu một transient entity.
em.persist(order);
```

**Detached target đã tồn tại:**

```java
Customer oldCustomer = loadCustomerFromClosedContext();
PurchaseOrder order = new PurchaseOrder(oldCustomer);

// Nếu cascade PERSIST sang oldCustomer,
// có thể lỗi vì oldCustomer là detached.
em.persist(order);
```

Hai tình huống có hướng xử lý khác nhau. Với target mới: **persist target mới** khi nghiệp vụ cần tạo nó. Với target cũ: **dùng managed reference** và tránh cascade PERSIST sai.

## 20. Tại sao lỗi có thể chỉ xuất hiện khi flush hoặc commit?

Hibernate dùng cơ chế **write-behind** và Action Queue: nhiều thao tác SQL được lên lịch rồi thực thi khi flush. Các hoạt động cascade có thể diễn ra ở nhiều giai đoạn tùy thao tác, generator và phiên bản.

Ví dụ:

```java
em.persist(order); // Chưa thấy exception.

em.flush();         // Có thể xuất hiện lỗi.
```

Hoặc:

```java
@Transactional
public void createOrder(...) {
    em.persist(order);
    // Method trả về; transaction manager flush/commit sau đó mới báo lỗi.
}
```

Điều này không làm thay đổi nguyên nhân: một object graph đã đưa entity vào **thao tác không phù hợp với trạng thái của nó**.

Để truy vết:

1. Xác định entity class được nêu trong exception (ví dụ `Customer`).
2. Tìm đường từ entity được persist trực tiếp đến class đó qua association có cascade.
3. Xác định transaction/context ban đầu nơi object được tải.
4. Tìm thời điểm object bị detach hoặc được tái sử dụng ở context khác.
5. Đối chiếu ý định tạo mới/cập nhật/thiết lập tham chiếu.
6. Kiểm tra mapping ID và `@Version` nếu Hibernate phân loại entity không như kỳ vọng.

**Không nên dùng `flush` tràn lan để che lỗi.** Flush sớm đôi khi giúp định vị thời điểm, nhưng không phải phương án sửa trạng thái entity.

## 21. Quy trình chẩn đoán một stack trace thực tế

Giả sử stack trace nói:

```text
jakarta.persistence.PersistenceException: ...
Caused by: org.hibernate.PersistentObjectException:
    detached entity passed to persist: com.example.Customer
```

Nhưng code nghiệp vụ chỉ có:

```java
orderRepository.save(order);
```

Hãy lần theo chuỗi:

### Bước 1: xác định entity bị báo lỗi

Tên `Customer` cho thấy Hibernate đã cố **persist Customer** ở đâu đó, dù thao tác chính là lưu Order.

### Bước 2: xem mapping liên quan

Tìm trong `PurchaseOrder`:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

`ALL` bao gồm `PERSIST` — đây là manh mối.

### Bước 3: xem nguồn gốc object customer

Khách hàng đến từ:

- Một repository trong transaction đã kết thúc?
- Entity được lấy từ cache ứng dụng?
- Đối tượng do JSON mapper tự khởi tạo với ID?
- Một entity dùng chung qua các request?
- Một EntityManager khác?

Nếu customer đại diện cho row hiện hữu nhưng không managed ở transaction đang ghi, nó là ứng viên detached.

### Bước 4: hỏi lại ý định nghiệp vụ

- Có cần **tạo khách hàng mới** không?
- Hay cần **tạo đơn hàng mới cho khách hàng đã có**?
- Hay cần **cập nhật thông tin khách hàng**?

Ba thao tác này nên có ba luồng rõ ràng, không giải quyết bằng một lời gọi `save` mơ hồ.

### Bước 5: sửa ở ranh giới đúng

Nếu mục đích là tạo đơn hàng cho khách hàng cũ:

```java
Customer managed = em.find(Customer.class, customerId);
PurchaseOrder order = new PurchaseOrder(managed);
em.persist(order);
```

Và bỏ cascade PERSIST/ALL không cần thiết từ order sang customer.

### Bước 6: kiểm tra các đường ghi khác

Một sửa đổi mapping có thể ảnh hưởng nhiều nghiệp vụ. Hãy phân biệt nơi thực sự muốn **tạo cả customer mới và order mới** với nơi chỉ tham chiếu customer cũ. Trong workflow tạo cả hai entity mới, persist rõ ràng theo lifecycle hoặc cascade từ một aggregate owner thích hợp.

Bài học này tập trung vào thiết kế và nguyên nhân lỗi; việc kiểm chứng toàn bộ hệ thống thuộc quy trình test/QA của dự án.

## 22. Mẫu thiết kế aggregate giúp tránh cascade sai

Một nguyên tắc hữu ích trong thiết kế domain là **chọn aggregate boundary**.

Ví dụ:

```text
Customer (aggregate riêng)
    |
    | một khách hàng có thể có nhiều đơn hàng
    |
PurchaseOrder (aggregate riêng)
    |
    +-- OrderLine (thành phần có vòng đời theo Order)
    +-- OrderLine
```

Từ góc độ tạo mới:

- Khi tạo `PurchaseOrder`, `Customer` là đối tượng **đã tồn tại độc lập** → tham chiếu bằng managed entity/reference; thường **không cascade PERSIST hoặc REMOVE**.
- `OrderLine` thường không có ý nghĩa độc lập ngoài PurchaseOrder → có thể cấu hình `cascade = PERSIST` và, nếu đúng domain, `orphanRemoval`.
- Khi thay đổi customer của order, đó là thay đổi tham chiếu/foreign key, không phải tạo customer mới.
- Khi xóa order, việc xóa line có thể hợp lý; xóa customer cùng order thường không hợp lý.

Ví dụ mapping:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Customer customer) {
        this.customer = Objects.requireNonNull(customer);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);
        lines.add(line);
        line.assignTo(this);
    }
}
```

Ở ví dụ này, `CascadeType.ALL` được đặt **có chủ đích** cho `OrderLine` vì line có vòng đời phụ thuộc Order theo giả định domain. Nó **không** được đặt lên `Customer`.

Các import `Objects`, `List`, `ArrayList` và annotation tương ứng phải có khi triển khai class hoàn chỉnh. `OrderLine.assignTo(...)` là domain helper giả định cập nhật phía owning `@ManyToOne` của line.

Không nên copy `CascadeType.ALL` cho mọi association chỉ vì “đỡ gọi save nhiều lần”.

## 23. Entity từ DTO và nguyên tắc “không tái tạo graph bằng ID”

Một pattern gây nhiều lỗi detached là map request trực tiếp thành entity:

```text
HTTP JSON
  |
  v
Order DTO
  |
  | ObjectMapper / BeanUtils / mapping framework
  v
PurchaseOrder {
    id = null,
    customer = Customer { id = 42 },
    lines = [...]
}
  |
  v
save(order)
```

Với mã generated ID và cascade ALL, Hibernate có thể hiểu `Customer{id=42}` là detached và cố persist nó, hoặc gặp vấn đề khác về managed identity.

### Tách DTO khỏi entity

Ví dụ request:

```java
public record CreateOrderRequest(
    Long customerId,
    List<CreateLineRequest> lines
) {}

public record CreateLineRequest(
    Long productId,
    int quantity
) {}
```

Trong transaction:

```java
@Transactional
public void create(CreateOrderRequest request) {
    Customer customer = em.find(
        Customer.class,
        request.customerId()
    );

    if (customer == null) {
        throw new IllegalArgumentException("Customer not found");
    }

    PurchaseOrder order = new PurchaseOrder(customer);

    for (CreateLineRequest dto : request.lines()) {
        Product product = em.find(Product.class, dto.productId());

        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        OrderLine line = new OrderLine(
            product,
            dto.quantity()
        );

        order.addLine(line);
    }

    em.persist(order);
}
```

Ví dụ giả định `OrderLine` có constructor thích hợp và `Product` là một entity độc lập được tham chiếu bằng managed entity. Các quy tắc giá, tồn kho, quyền truy cập, trường hợp duplicate line... thuộc domain cụ thể.

Cách này làm rõ:

- `Order` và `OrderLine` là đối tượng **mới**.
- `Customer` và `Product` là đối tượng **đã tồn tại**.
- Tạo mới order được xử lý bằng `persist`.
- Những ID từ request không bị biến thành entity detached giả một cách tùy tiện.

## 24. Khi nào nên dùng `merge` trong ứng dụng thực tế?

Dùng `merge` là hợp lý khi ứng dụng thực sự có **detached entity đầy đủ** cần đồng bộ lại, ví dụ:

- Một workflow xử lý entity ngoài persistence context rồi quay lại lưu.
- Một tác vụ nghiệp vụ có contract rõ là nhận state hoàn chỉnh của entity đã tồn tại.
- Một hệ thống legacy quản lý entity across contexts và đã xác định chính sách merge, version và cascade.

Ví dụ trong transaction:

```java
@Transactional
public Customer applyDetachedChange(Customer detached) {
    Customer managed = em.merge(detached);
    return managed;
}
```

Nhưng phải bảo đảm input không đến trực tiếp từ request chưa được kiểm soát, và xử lý xung đột version. Khi caller nhận kết quả, nó cần hiểu managed instance chỉ có vòng đời **trong persistence context của transaction**; sau khi transaction kết thúc, object được trả về cũng có thể detached.

### Cần nhớ ba rủi ro của merge

1. **Sao chép state rộng hơn ý định:** field không xuất hiện trong request có thể bị ghi đè.
2. **Cascade qua graph:** có thể merge nhiều association, sinh SELECT/UPDATE không mong đợi.
3. **Stale data:** entity detached từ lâu có thể ghi đè trạng thái mới nếu không có concurrency control.

Đối với phần lớn API CRUD có DTO, cách tải entity managed và áp dụng thay đổi có chủ đích thường dễ hiểu, rõ permission hơn.

## 25. Một số hiểu lầm thường gặp

**“Đã có ID thì gọi `persist` sẽ update.”**  
Không. `persist` dành cho entity mới; entity đã detached không được xử lý như một update tùy ý. Hành vi với assigned ID còn phụ thuộc unsaved-value strategy.

**“Thêm `CascadeType.ALL` là khỏi lo lưu thiếu entity.”**  
Không. Nó còn cascade `PERSIST` sang entity đã tồn tại và `REMOVE` sang entity không nên bị xóa.

**“`merge` biến chính object truyền vào thành managed.”**  
Không. Dùng instance được `merge` trả về.

**“`save` của Spring Data luôn là insert hoặc upsert SQL.”**  
Không. Nó thường chọn persist/merge theo cơ chế nhận diện new entity, rồi Hibernate quyết định SQL khi flush.

**“Lỗi xuất hiện ở commit nghĩa là lỗi transaction manager.”**  
Chưa chắc. Hibernate có thể thực hiện cascade/flush vào cuối transaction; nguồn lỗi vẫn là object graph và trạng thái entity không phù hợp.

**“Chỉ cần gọi `em.flush()` trước hoặc sau `persist` là hết lỗi.”**  
Không. Flush chỉ làm các thao tác đang chờ được đồng bộ, có thể khiến lỗi bộc lộ sớm.

**“Nếu gán ID thủ công cho entity mới, Hibernate sẽ xem nó là reference hợp lệ.”**  
Không có bảo đảm. Generated ID và unsaved-state detection có semantics riêng; gán ID từ DTO không thay thế `find`/`getReference`.

**“Gọi `merge` luôn bảo toàn mọi cập nhật của người dùng khác.”**  
Không. Cần version/optimistic locking và hợp đồng state rõ ràng.

**“Hai object cùng ID có thể cùng managed trong một persistence context.”**  
Hibernate có identity map; cố gắn hai instance khác nhau mang cùng entity identity theo API phù hợp có thể gây lỗi. `merge` giải quyết bằng cách trả về managed instance tương ứng, không đơn giản reattach mọi object.

**“Detached là object hỏng hoặc không thể sử dụng.”**  
Không. Detached vẫn có thể dùng để đọc các thuộc tính đã nạp, tạo DTO hoặc trao đổi state. Lỗi xảy ra khi sử dụng nó **như một managed/new entity mà không theo đúng hợp đồng thao tác**.

## 26. Trình tự xử lý khi gặp lỗi trong một dự án

Một quy trình thực tế có thể áp dụng:

1. **Đọc đúng entity class trong nguyên nhân gốc của exception.** Nếu lỗi nêu `Customer`, đừng chỉ nhìn lệnh `save(Order)`.
2. **Xác định thao tác gốc:** `persist`, `merge`, repository `save`, cascade PERSIST hoặc thao tác native.
3. **Lần đường cascade:** xem `CascadeType.ALL`, `PERSIST` và các association đi từ root graph đến entity bị báo lỗi.
4. **Xác định entity có mới thật không:** nó có được tạo trong transaction hiện tại, được tải từ transaction cũ, hay được tái dựng từ DTO?
5. **Đặt lại ý định nghiệp vụ:** tạo mới root, tham chiếu entity có sẵn hay cập nhật entity cũ?
6. **Dùng managed reference cho entity đã tồn tại:** `find` khi cần validate state, `getReference` khi chỉ cần FK và đã kiểm soát hợp lệ.
7. **Persist chỉ entity mới và những child được sở hữu vòng đời.** Không cascade PERSIST bừa sang parent/shared entity.
8. **Khi cần áp dụng detached state, dùng merge có chọn lọc và kết quả trả về**, hoặc thường tốt hơn là tải managed rồi áp dụng chính xác thay đổi từ DTO.
9. **Giữ transaction và persistence context có ranh giới rõ.** Không tái sử dụng EntityManager hoặc Session ngoài vòng đời thích hợp, không chia sẻ Session giữa thread.
10. **Xử lý concurrency và dữ liệu cũ:** dùng `@Version` hoặc quy tắc nghiệp vụ tương ứng, không coi ID là chứng nhận hàng vẫn tồn tại.

## 27. Bài tập phân biệt nguyên nhân

### Tình huống A: tạo đơn cho customer đã tồn tại

```java
Customer customer = findCustomerFromOldSession(42L);
Order order = new Order(customer);
em.persist(order);
```

Mapping:

```java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
```

**Nhận định:** cascade PERSIST có thể đưa customer detached vào `persist`. Cách sửa là bỏ cascade lifecycle không đúng và lấy customer managed trong transaction ghi.

### Tình huống B: tạo đơn với customer hoàn toàn mới

```java
Customer customer = new Customer("An");
Order order = new Order(customer);
em.persist(order);
```

Không có cascade và customer chưa được persist.

**Nhận định:** có nguy cơ lỗi **unsaved transient reference**, khác với detached. Nếu nghiệp vụ muốn tạo cả hai, cần persist customer mới (hoặc cascade PERSIST nếu ownership thực sự hợp lý), rồi persist order.

### Tình huống C: cập nhật một entity detached

```java
Customer detached = loadAndClose(42L);
detached.changeName("Tên mới");

em.persist(detached);
```

**Nhận định:** `persist` không phù hợp. Có thể tải managed theo ID và đổi tên, hoặc `merge` khi muốn sao chép toàn bộ state có kiểm soát.

### Tình huống D: dùng `merge` nhưng giữ object cũ

```java
Customer managed = em.merge(detached);
detached.changeName("Thay đổi tiếp");
```

**Nhận định:** sửa detached sau merge không tự cập nhật managed. Sử dụng `managed` cho phần còn lại của transaction.

### Tình huống E: nhận request chỉ có ID customer

```java
Customer customer = new Customer();
customer.setId(request.customerId());
em.persist(new Order(customer));
```

**Nhận định:** object giả gắn ID không phải managed reference. Dùng `em.find` hoặc `em.getReference` cho customer trong transaction hiện tại.

## 28. Ghi nhớ

- **Detached entity** là object từng đại diện cho một entity nhưng **không còn được persistence context hiện tại quản lý**; nó không tự động được theo dõi khi thay đổi.
- **`persist` dùng cho entity mới.** Gọi `persist` trực tiếp hoặc cascade vào detached entity có thể tạo lỗi `detached entity passed to persist`.
- **`CascadeType.PERSIST` và `CascadeType.ALL`** là nguồn lỗi phổ biến khi một entity mới tham chiếu đến parent/shared entity đã tồn tại.
- Với **child mới + parent đã có**, hãy lấy parent managed bằng `find`/`getReference` và persist child. Không tự gán generated ID vào một object mới để đóng vai parent cũ.
- Với **cập nhật entity cũ**, thường nên tải entity managed rồi thay đổi qua method domain; Hibernate dirty checking xử lý flush.
- **`merge(detached)` trả về managed instance** và không biến object đầu vào thành managed. Merge có thể truy vấn DB, cascade graph và ghi đè state cũ nếu thiếu kiểm soát.
- **`EntityManager.contains`** xác nhận trạng thái managed trong context hiện tại, nhưng không phân biệt mọi trạng thái khi trả `false`.
- **`@Version`** giúp phát hiện xung đột cập nhật, không thay thế việc chọn đúng `persist`/`merge`.
- **`remove`, `refresh`** và các API khác cũng có điều kiện trạng thái; đừng áp dụng chúng cho detached entity theo suy đoán.
- **ID khác null không chứng minh entity managed, đã commit, hoặc vẫn tồn tại trong DB.**
- Thiết kế aggregate, ranh giới transaction và DTO rõ ràng giúp giảm mạnh việc vô tình đưa detached entity vào đường persist.

**Kết luận:** lỗi “detached entity passed to persist” không chỉ là một exception kỹ thuật. Nó báo hiệu ứng dụng đã nhầm **identity và vòng đời thực thể**: đang yêu cầu Hibernate tạo mới một object vốn được hiểu là đã tồn tại. Cách sửa bền vững không phải thêm một lời gọi `save` hay `flush`, mà là xác định rõ **entity nào mới, entity nào đã tồn tại, entity nào managed trong transaction này, và cascade nào thực sự thuộc quyền sở hữu vòng đời**.
