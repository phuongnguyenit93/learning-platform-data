# Phân biệt đối tượng nguồn và đối tượng trả về từ merge

> **Chủ đề:** Data Persistence – Relational Access, ORM, JPA  
> **Nhóm kiến thức:** Vòng đời entity

Một nhầm lẫn phổ biến khi dùng JPA là cho rằng **EntityManager.merge(entity)** sẽ biến chính đối tượng truyền vào thành entity được quản lý. Thực tế, **merge sao chép trạng thái của đối tượng nguồn sang một đối tượng được quản lý trong persistence context**, rồi **trả về đối tượng managed đó**.

~~~java
Customer source = ...; // Một entity detached từ transaction trước.

Customer managed = entityManager.merge(source);

System.out.println(entityManager.contains(source));  // false.
System.out.println(entityManager.contains(managed)); // true.
System.out.println(source == managed);                // false.
~~~

Đối với ví dụ **source detached**, source và managed có thể cùng loại entity, cùng ID database nhưng là **hai instance Java khác nhau**, có khả năng được dirty checking khác nhau.

Nếu gọi merge rồi tiếp tục sửa **source**, thay đổi đó **không tự xuất hiện trong managed result**. Ngược lại, sửa **managed** khi nó còn trong persistence context và transaction phù hợp có thể được ghi xuống DB ở lần flush tiếp theo.

Bài học này trình bày: vòng đời entity; semantics merge cho **new, managed, detached và removed**; identity map; cách nhận diện source/return value; SQL và flush; cascade merge; null overwrite và đồ thị quan hệ; optimistic locking; Spring Data JPA save; cùng những tình huống thực tế và bài tập.

## 1. Vòng đời entity và persistence context

JPA quản lý một entity dựa trên **quan hệ giữa instance Java và persistence context**, không chỉ dựa trên việc thuộc tính ID có null hay không.

| Trạng thái | Đặc trưng | Dirty checking tự động |
|---|---|---|
| **New / transient** | Object vừa tạo, chưa được context quản lý | Không |
| **Managed / persistent** | Instance thuộc persistence context đang hoạt động | Có, khi thay đổi được đồng bộ trong transaction thích hợp |
| **Detached** | Instance từng managed nhưng không còn thuộc context đang xét | Không |
| **Removed** | Entity được đánh dấu xóa trong persistence context | Không sử dụng như object cập nhật bình thường |

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    N["New"] -->|"persist"| M["Managed"]
    N -->|"merge tạo managed copy"| M
    M -->|"detach, clear, close"| D["Detached"]
    D -->|"merge trả managed target"| M
    M -->|"remove"| R["Removed"]
    M -->|"flush / commit"| DB[("Database")]
    R -->|"flush / commit"| DB
~~~

Mũi tên merge ở sơ đồ không có nghĩa object nguồn tự biến đổi trạng thái. Nó diễn đạt **một managed instance nhận state và được trả về**.

### 1.1. Identity map

Với cùng một persistence context, JPA giữ một managed instance tương ứng với một entity identity:

~~~java
Customer a = em.find(Customer.class, 10L);
Customer b = em.find(Customer.class, 10L);

System.out.println(a == b);       // true trong cùng context.
System.out.println(em.contains(a)); // true.
~~~

Một EntityManager khác có persistence context khác:

~~~java
Customer fromEm1 = em1.find(Customer.class, 10L);
Customer fromEm2 = em2.find(Customer.class, 10L);

// Chúng có thể khác reference Java dù cùng ID database.
~~~

Dùng **==** để so sánh reference Java; dùng ID/entity identity để nói về hàng DB. Hai khái niệm này không đồng nhất.

### 1.2. Những thao tác ảnh hưởng trạng thái

| Thao tác | Kết quả |
|---|---|
| **new Customer(...)** | Object new, chưa managed |
| **em.persist(entity)** | New entity được quản lý; INSERT theo lifecycle |
| **em.find(Customer.class, id)** | Trả managed entity hoặc null |
| **em.detach(entity)** | Tách một instance khỏi context |
| **em.clear()** | Tách các managed instances khỏi context |
| **em.close()** | Đóng EntityManager, kết thúc việc quản lý bởi context ấy |
| **em.merge(source)** | Trả managed result nhận state nguồn theo quy tắc merge |
| **em.remove(entity)** | Đánh dấu managed entity để xóa |
| **em.flush()** | Đồng bộ thay đổi pending xuống DB trong transaction |
| **transaction.commit()** | Cố gắng hoàn tất transaction; có thể phát flush/lỗi |

**Commit không luôn đồng nghĩa detach.** Với resource-local EntityManager còn mở, entity có thể tiếp tục managed sau commit. Context gắn transaction do container/framework quản lý có vòng đời khác. Khi cần xác định trạng thái hãy xét context hiện tại và **em.contains()**, không dựa vào việc đã có một commit.

## 2. Hợp đồng của merge: nhận source, trả managed target

Phương thức:

~~~java
<T> T merge(T entity)
~~~

có hai khái niệm cần phân biệt:

1. **Source/argument:** object được truyền vào **merge**. Nó có thể detached, new hoặc managed.
2. **Target/return value:** instance thuộc persistence context hiện tại, nhận trạng thái tương ứng từ source và được trả về.

Đối với detached source:

~~~text
SOURCE (detached)                         TARGET (managed)
  id = 10                                    id = 10
  displayName = "Lan sửa offline"             displayName = "Lan sửa offline"
  thuộc object graph cũ                      thuộc persistence context hiện tại

                   em.merge(source)
                 sao chép trạng thái  ─────────►

        source != target (hai Java references khác nhau).
        source vẫn detached; target được dirty checking.
~~~

Đừng hiểu **merge** như một thao tác “attach lại object nguồn”. Nó không thiết lập một liên kết đồng bộ hai chiều giữa source và result.

### 2.1. Dòng xử lý khái niệm

~~~mermaid
sequenceDiagram
    participant App as Application
    participant S as Detached source
    participant EM as EntityManager
    participant PC as Persistence context
    participant DB as Database

    App->>EM: merge(S)
    EM->>PC: tìm managed target cùng entity identity
    alt Target chưa có trong context
        PC->>DB: có thể SELECT theo ID
        DB-->>PC: hàng dữ liệu/version
    end
    PC->>PC: copy các thuộc tính phù hợp từ S
    PC-->>EM: managed target
    EM-->>App: return managed target
    Note over S,App: S vẫn detached
    App->>EM: flush / commit
    EM->>DB: INSERT/UPDATE cần thiết
~~~

Đây là mô tả logic, không phải cam kết về số SELECT/UPDATE. Provider có thể tối ưu SQL, sử dụng instance có sẵn, cascade, version và flush theo cấu hình. Điều quan trọng là **return value là instance managed**.

### 2.2. Merge không đồng nghĩa UPDATE ngay

~~~java
Customer managed = em.merge(source);
// Ngay tại dòng này chưa thể khẳng định SQL UPDATE đã commit.
~~~

JPA có thể phải load instance cùng ID rồi sao chép state; UPDATE thường được gửi khi flush. Với source new, INSERT có thể xảy ra theo ID strategy. Một số constraint hoặc lỗi optimistic locking có thể xuất hiện lúc merge, flush hoặc commit.

**flush ≠ commit**: flush đưa SQL tới database trong transaction, commit mới kết thúc transaction thành công. Giao dịch vẫn có thể rollback sau flush.

### 2.3. Merge không có bước copy ngược

~~~java
Customer managed = em.merge(source);

source.changeDisplayName("A");
managed.changeDisplayName("B");
~~~

Hai lời gọi sửa **hai object khác nhau** nếu source là detached. JPA không xem “A” là thay đổi mới nhất cần tự copy ngược vào managed.

## 3. Entity mẫu để thí nghiệm

~~~java
package com.example.persistence;

import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    @Column(name = "email", nullable = false, length = 200)
    private String email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() { }

    public Customer(String email, String displayName) {
        this.email = Objects.requireNonNull(email);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getEmail() { return email; }
    public String getDisplayName() { return displayName; }

    public void changeDisplayName(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
        this.displayName = newName;
    }

    public void changeEmail(String newEmail) {
        this.email = Objects.requireNonNull(newEmail);
    }
}
~~~

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    email VARCHAR(200) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);
~~~

**@Version** hỗ trợ optimistic locking. Giá trị version ban đầu cụ thể phụ thuộc provider/kiểu version, không nên hard-code vào service. Unique constraint phải tồn tại thật qua migration nếu muốn database chặn hai email trùng.

Các snippet sau giả định **EntityManagerFactory emf** đã được cấu hình và application đang dùng một database phù hợp.

## 4. Thí nghiệm: detached source và managed result

### 4.1. Lưu Customer lần đầu

~~~java
Long customerId;

EntityManager em1 = emf.createEntityManager();
EntityTransaction tx1 = em1.getTransaction();

try {
    tx1.begin();

    Customer original = new Customer(
        "lan@example.com", "Lan ban đầu");

    em1.persist(original);
    tx1.commit();

    customerId = original.getId();
} catch (RuntimeException ex) {
    if (tx1.isActive()) {
        tx1.rollback();
    }
    throw ex;
} finally {
    em1.close();
}
~~~

Với **GenerationType.IDENTITY**, ID thường được tạo khi INSERT; sau khi commit thành công ở ví dụ này có thể đọc ID.

### 4.2. Tạo một source detached

~~~java
Customer detached;

EntityManager readEm = emf.createEntityManager();
try {
    detached = readEm.find(Customer.class, customerId);
} finally {
    readEm.close(); // detached không còn thuộc readEm.
}

detached.changeDisplayName("Lan sửa offline");
~~~

**detached** từng là managed instance trong readEm. Sau khi context đóng, thay đổi displayName chỉ diễn ra trong RAM và chưa được DB tự theo dõi.

### 4.3. Merge trong EntityManager mới

~~~java
EntityManager em2 = emf.createEntityManager();
EntityTransaction tx2 = em2.getTransaction();

try {
    tx2.begin();

    Customer managed = em2.merge(detached);

    System.out.println(em2.contains(detached)); // false.
    System.out.println(em2.contains(managed));  // true.
    System.out.println(detached == managed);     // false.

    System.out.println(
        detached.getId().equals(managed.getId())); // true.

    System.out.println(managed.getDisplayName());
    // "Lan sửa offline"

    tx2.commit();
} catch (RuntimeException ex) {
    if (tx2.isActive()) {
        tx2.rollback();
    }
    throw ex;
} finally {
    em2.close();
}
~~~

**Cùng ID nhưng khác Java instance.** Đây là biểu hiện tiêu biểu khi merge detached entity.

### 4.4. Sửa tiếp sau merge: object nào mới được ghi?

~~~java
Customer managed = em.merge(detached);

detached.changeDisplayName("A trên source");
managed.changeDisplayName("B trên managed");

em.flush();
~~~

Nếu transaction commit thành công và không có đường ghi khác, DB sẽ giữ giá trị từ **managed** là **"B trên managed"**, không tự chọn state mới nhất của source.

| Mốc | detached source | managed result | Trạng thái sẽ được ORM ghi |
|---|---|---|---|
| Trước merge | "Offline" | Chưa có | Dữ liệu cũ |
| Sau merge | "Offline" | "Offline" | Theo state đã copy |
| Sửa source | "A" | "Offline" | Không tự nhận "A" |
| Sửa managed | "A" | "B" | "B" khi flush/commit |
| Commit thành công | "A" | "B" | "B" |

### 4.5. Lỗi phổ biến: bỏ qua return value

~~~java
public void updateCustomer(Customer detached) {
    em.merge(detached);
    detached.changeDisplayName("Đã duyệt");
}
~~~

Nếu detached thực sự detached, lời gọi **changeDisplayName** sau merge không tác động lên managed result. Sửa:

~~~java
public void updateCustomer(Customer detached) {
    Customer managed = em.merge(detached);
    managed.changeDisplayName("Đã duyệt");
}
~~~

Hoặc khi chỉ thay một field, thường dễ kiểm soát hơn:

~~~java
public void updateCustomer(long id, String displayName) {
    Customer managed = em.find(Customer.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Customer không tồn tại");
    }
    managed.changeDisplayName(displayName);
}
~~~

Với managed entity, dirty checking làm việc trong transaction phù hợp, không cần merge thêm.

## 5. Merge source đã managed, new hoặc removed

Đừng hiểu “merge luôn trả một object khác” như quy tắc tuyệt đối. Kết quả phụ thuộc **trạng thái source**.

| Source tại lúc gọi | Xử lý khái niệm | Source sau merge | Giá trị trả về |
|---|---|---|---|
| **Detached** | Copy state vào managed instance có cùng identity hoặc instance mới được quản lý | Vẫn detached | Managed target, khác reference source |
| **New** | Tạo managed copy, copy state và sẽ INSERT theo lifecycle | Vẫn new theo semantics merge | Managed copy |
| **Managed** | Đã managed; không cần copy vào instance khác, có thể cascade merge | Vẫn managed | Chính managed instance |
| **Removed** | Merge không hợp lệ với entity đã removed | Không phục hồi bằng merge | Lỗi IllegalArgumentException theo JPA (có thể phát hiện tại call/flush) |

### 5.1. Merge entity đã managed

~~~java
Customer alreadyManaged = em.find(Customer.class, customerId);
Customer result = em.merge(alreadyManaged);

System.out.println(em.contains(alreadyManaged)); // true.
System.out.println(em.contains(result));         // true.
System.out.println(result == alreadyManaged);    // true.
~~~

Nếu source đã managed, không có lý do biến nó thành managed lần nữa. JPA merge vẫn có thể **cascade** cho các quan hệ được cấu hình CascadeType.MERGE hoặc ALL.

Vì vậy:

~~~java
Customer customer = em.find(Customer.class, customerId);
customer.changeDisplayName("Tên mới");
// Không cần em.merge(customer) chỉ để lưu field này.
~~~

là đường cập nhật bình thường bằng dirty checking.

### 5.2. Merge một entity new

~~~java
Customer source = new Customer("new@example.com", "Khách mới");

Customer managed = em.merge(source);

System.out.println(em.contains(source));  // false với new source.
System.out.println(em.contains(managed)); // true.
~~~

JPA tạo một **managed copy** và sẽ INSERT khi cần. Không được mặc định mong **source.getId()** hay **source.getVersion()** được provider cập nhật ngược. Hãy sử dụng **managed result** để lấy identity/state được provider quản lý.

Nếu cần generated ID ngay, phải xét **ID generator**, thời điểm INSERT/flush và transaction. Một ID có thể chưa được gán tại thời điểm code đọc trước flush tùy strategy; với IDENTITY, provider thường cần INSERT sớm để lấy key.

### 5.3. So sánh persist và merge

| | **persist(new)** | **merge(new)** |
|---|---|---|
| Return value | void | managed instance |
| Đối tượng nguồn | Trở thành managed | Không phải managed copy |
| Entity được INSERT | Instance gọi persist | Managed result |
| Hữu ích khi | Chủ động tạo entity mới | Hợp nhất state new/detached |
| Cần giữ return value? | Không có | Có nếu sửa tiếp/lấy ID |
| Thời điểm SQL | Theo provider/transaction | Theo provider/transaction |

Không nên dùng merge thay persist máy móc khi chắc chắn object là new. Dù cả hai có thể dẫn tới INSERT, semantics reference và chi phí xử lý entity state không giống nhau.

### 5.4. Source removed

Nếu entity bị **em.remove(managed)** rồi lại gọi merge trên removed entity trong cùng context, merge không phải cách “hủy xóa”. JPA có thể báo **IllegalArgumentException** đối với removed entity. Nếu nghiệp vụ muốn khôi phục một bản ghi đã xóa, cần thiết kế thao tác mới, trạng thái soft-delete hoặc quy trình tạo lại thay vì giả định merge phục hồi object.

### 5.5. ID khác null không chứng minh detached

~~~java
Customer customer = ...; // Có thể ứng dụng tự gán ID với assigned identifier.
~~~

Một object có ID vẫn có thể new, detached hoặc do ứng dụng tạo giả từ request. Các entity dùng assigned ID và version có semantics nhận diện new khác với ID generated. Không chọn merge chỉ vì **id != null** mà bỏ qua trạng thái, quyền ghi và thiết kế tạo/cập nhật.

## 6. Merge không phải một câu UPSERT nguyên tử

“Upsert” trong database thường là thao tác nguyên tử kiểu **INSERT ... ON CONFLICT ... DO UPDATE** hoặc khả năng tương đương của DBMS. Merge JPA **không có nghĩa tương đương**:

- Nó có thể phải SELECT rồi quyết định INSERT/UPDATE.
- Unique constraint có thể bị vi phạm khi hai transaction cùng tạo.
- State cũ có thể ghi đè field hiện tại.
- Optimistic locking có thể phát hiện version không còn đúng.
- Cascade có thể tạo/cập nhật nhiều entity.
- SQL có thể thực hiện ở flush/commit, không ngay tại merge.

Nếu hệ thống cần upsert theo business key với concurrency cao, phải thiết kế uniqueness, idempotency và transaction/SQL strategy thích hợp, không dùng merge như giải pháp nguyên tử mặc định.

## 7. Merge khi target cùng ID đã nằm trong persistence context

Trường hợp quan trọng: EntityManager **đã quản lý Customer cùng ID** trước khi gọi merge.

~~~java
Customer managedBeforeMerge = em.find(Customer.class, customerId);
managedBeforeMerge.changeDisplayName("Thay đổi từ service A");

// detachedCustomer từng được tải ở context khác.
detachedCustomer.changeDisplayName("Dữ liệu từ màn hình B");

Customer result = em.merge(detachedCustomer);

System.out.println(result == managedBeforeMerge); // true.
System.out.println(result == detachedCustomer);   // false.
~~~

JPA không tạo một managed Customer thứ hai có cùng identity trong persistence context. Thay vào đó, state được merge **vào managed instance đã có**. Những field đã đổi trên managedBeforeMerge có thể bị **state detached của source ghi đè trong bộ nhớ**, nếu các field tương ứng được merge.

**merge không phải thuật toán so sánh hai phiên bản và giữ giá trị mới nhất cho từng field**. Nó không tự biết màn hình nào vừa sửa field nào, không tự giải quyết conflict giữa hai nguồn dữ liệu.

### 7.1. Trình tự trạng thái

Giả sử database đang có:

~~~text
Customer#10: email=lan@example.com, displayName="Lan gốc"
~~~

Trong persistence context:

~~~java
Customer managed = em.find(Customer.class, 10L);
managed.changeDisplayName("Lan do A đổi");
~~~

Detached source lại có:

~~~text
Customer#10: email=lan@example.com, displayName="Lan từ B"
~~~

Sau:

~~~java
Customer result = em.merge(detached);
~~~

thì **result == managed**, và displayName có thể là **"Lan từ B"** vì source state được sao chép vào managed target. Đây là lỗi kinh điển khi gọi merge sau khi code đã cập nhật một managed entity trong cùng transaction.

### 7.2. Phân biệt find, merge và refresh

| API | Mục đích |
|---|---|
| **em.find(Customer.class, id)** | Tìm/đọc managed entity từ context hoặc DB |
| **em.merge(detached)** | Chép state nguồn vào một managed entity phù hợp |
| **em.refresh(managed)** | Nạp lại state từ DB, có thể ghi đè những thay đổi chưa flush |
| **em.contains(object)** | Kiểm tra chính instance này có đang managed trong context không |

Nếu chỉ muốn dữ liệu mới nhất từ DB, **find** hoặc refresh theo tình huống phù hợp. Đừng dùng merge với một source cũ vì nó có thể làm ngược điều mong muốn.

## 8. Rủi ro: null và dữ liệu snapshot cũ bị merge đè

Giả sử API chỉ cho phép đổi tên:

~~~json
{
  "id": 10,
  "displayName": "Tên mới"
}
~~~

Nếu mapper tạo một Customer object chứa:

~~~text
id = 10
displayName = "Tên mới"
email = null
~~~

rồi service gọi:

~~~java
em.merge(requestMappedCustomer);
~~~

thì **email=null** có thể được copy vào managed entity và dẫn đến UPDATE null, vi phạm NOT NULL hoặc làm mất email nếu DB cho phép. Merge không tự phân biệt “JSON không gửi email” với “người dùng cố ý xóa email”.

### 8.1. Merge không phải semantics HTTP PATCH

Lệnh PATCH thường chỉ thay một số thuộc tính; merge hoạt động ở mức **entity state**. Nếu source chứa null/default được xem là giá trị đã biết, chúng có thể trở thành state của target.

Một thao tác sửa tên thường an toàn và dễ kiểm soát hơn:

~~~java
@Transactional
public void updateName(long id, UpdateCustomerNameRequest request) {
    Customer customer = em.find(Customer.class, id);
    if (customer == null) {
        throw new IllegalArgumentException("Customer không tồn tại");
    }
    customer.changeDisplayName(request.displayName());
}
~~~

DTO:

~~~java
public record UpdateCustomerNameRequest(String displayName) { }
~~~

Entity đang managed, nên không cần gọi merge thêm chỉ để thay đổi displayName.

### 8.2. Không bind trực tiếp JSON vào entity rồi merge

~~~java
Customer incoming = objectMapper.convertValue(payload, Customer.class);
em.merge(incoming);
~~~

Đường đi này có thể tạo ra:
- **Mass assignment:** client gửi những field không được phép sửa.
- **Null overwrite:** các field vắng mặt trong request trở thành null.
- **Broken association:** client gửi ID liên quan không được kiểm tra quyền.
- **Unexpected collection replacement:** các collection thiếu hoặc rỗng được hiểu không đúng.
- **Lost update:** source version cũ ghi đè dữ liệu mới.
- **Insert ngoài ý muốn:** state new/detached bị xác định sai.

Dùng DTO/command chứa **những thuộc tính được phép sửa**, nạp managed entity từ ID đã xác thực và áp dụng business methods. Với các yêu cầu cần phân biệt vắng mặt và explicit null, thiết kế DTO hỗ trợ trạng thái ba giá trị hoặc endpoint riêng để xóa một field.

### 8.3. updatable=false không giải quyết mọi vấn đề

~~~java
@Column(name = "created_at", updatable = false)
private Instant createdAt;
~~~

Cờ **updatable=false** làm mapping không ghi cột trong UPDATE do provider sinh từ property ấy. Nó **không phải permission check**, không ngăn native SQL và không tự bảo đảm state Java không thể bị gán. Một source detached có giá trị field chỉ đọc khác DB có thể làm managed state và database khác nhau nếu code không hiểu cơ chế mapping/readback.

### 8.4. LAZY chưa fetch khác với null do mapper gán

JPA yêu cầu provider không merge **lazy attributes chưa được fetch** như thể chúng là state đã có. Đây là khác biệt quan trọng với:

1. Một field đã fetch và có giá trị null thật.
2. Một field do ứng dụng tự gán null.
3. Một DTO thiếu field nhưng mapper khởi tạo field null.
4. Một lazy field được provider nhận biết là **unfetched**.

Trường hợp thứ tư có metadata/khả năng theo dõi từ provider. Không thể biến mọi field null thành “unfetched” bằng cách không đưa nó vào JSON. Khi mapping DTO thành một object mới, **null thường là một giá trị của object**, không phải dấu hiệu lazy chưa fetch.

Vì vậy **không dựa vào cơ chế ignore unfetched lazy state để thực hiện PATCH tự động**.

## 9. Merge đồ thị quan hệ: CascadeType.MERGE

Một entity thực tế thường có associations và collections. Khi merge một detached root, phải hiểu **những entity con nào được cascade**, và có sự khác biệt giữa **source graph** với **managed graph**.

Ví dụ Order và OrderLine:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(
        mappedBy = "order",
        cascade = {CascadeType.PERSIST, CascadeType.MERGE},
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() { }

    public Long getId() { return id; }
    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        Objects.requireNonNull(line);
        if (line.getOrder() != null && line.getOrder() != this) {
            throw new IllegalStateException("Line thuộc Order khác");
        }
        if (!lines.contains(line)) {
            lines.add(line);
        }
        line.assignOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.assignOrder(null);
        }
    }
}
~~~

~~~java
@Entity
@Table(name = "order_lines")
public class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private Integer quantity;

    protected OrderLine() { }

    public OrderLine(String sku, int quantity) {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("OrderLine không hợp lệ");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }

    void assignOrder(PurchaseOrder order) {
        this.order = order;
    }

    public void changeQuantity(int next) {
        if (next <= 0) {
            throw new IllegalArgumentException("Quantity phải > 0");
        }
        quantity = next;
    }
}
~~~

Các snippet giả định import **jakarta.persistence.\*** và các class Java collection/Objects phù hợp. Khi dùng **List.contains/remove** với entity, cần thiết kế equals/hashCode an toàn; mẫu này tập trung vào semantics merge.

### 9.1. CascadeType.MERGE thực hiện điều gì?

~~~java
PurchaseOrder managedOrder = em.merge(detachedOrder);
~~~

Nếu **PurchaseOrder.lines** có CascadeType.MERGE, merge lan tới các OrderLine thích hợp, nhận/copy state vào những **managed OrderLine targets**. **Detached OrderLine objects của source graph không tự biến thành managed**.

~~~java
em.merge(detachedOrder);

detachedOrder.getLines().get(0).changeQuantity(9);
// Chỉ sửa source graph, không tự được dirty checking sau merge.
~~~

Muốn sửa tiếp qua graph được quản lý:

~~~java
PurchaseOrder managedOrder = em.merge(detachedOrder);
managedOrder.getLines().get(0).changeQuantity(9);
~~~

Với dữ liệu có thứ tự hoặc collection chưa fetch, cần xác định đúng line, không phụ thuộc **get(0)** tùy tiện trong business code. Có thể truy vấn OrderLine theo ID và orderId thay vì load collection lớn.

### 9.2. Cascade MERGE không đồng nghĩa PERSIST hoặc REMOVE

| Cấu hình | Mục đích |
|---|---|
| **CascadeType.PERSIST** | Lan thao tác persist tới entity liên quan |
| **CascadeType.MERGE** | Lan thao tác merge tới entity liên quan |
| **CascadeType.REMOVE** | Lan remove khi entity chủ được remove |
| **CascadeType.ALL** | Gồm nhiều loại cascade, có cả REMOVE |
| **orphanRemoval=true** | Xóa child khi rời quan hệ sở hữu theo semantics thích hợp |

Không bật **CascadeType.ALL** với các entity độc lập như User–Role, Student–Course hoặc Employee–Department chỉ để “merge cho tiện”, vì xóa một entity có thể lan xóa entity dùng chung. Xác định cascade theo vòng đời nghiệp vụ.

### 9.3. Owning side vẫn quyết định FK

Trong ví dụ, **OrderLine.order** là owning side ghi cột order_id; **PurchaseOrder.lines** là inverse side dùng mappedBy. Nếu source graph có collection và owning reference mâu thuẫn, kết quả ghi có thể không như business mong đợi. Helper **addLine/removeLine** cần duy trì cả hai phía.

### 9.4. Collection thiếu dữ liệu và orphanRemoval nguy hiểm

Giả sử DB lưu Order #5 với ba Line **A, B, C**. API chỉ muốn sửa quantity của A nhưng mapper dựng một detached Order chứa collection **[A]**.

Nếu merge coi collection source là danh sách đầy đủ, kết quả có thể loại B, C khỏi managed collection; với **orphanRemoval=true**, những child bị loại có thể bị **DELETE ngoài ý muốn**.

Vì vậy không merge detached aggregate dựng lại từ một JSON payload không đầy đủ khi cần update một field. Thay bằng query một managed OrderLine thuộc Order, kiểm tra quyền và cập nhật đúng quantity:

~~~java
@Transactional
public void changeQuantity(long orderId, long lineId, int nextQty) {
    OrderLine managed = em.createQuery(
        """
        select l
        from OrderLine l
        where l.id = :lineId and l.order.id = :orderId
        """,
        OrderLine.class)
      .setParameter("lineId", lineId)
      .setParameter("orderId", orderId)
      .getResultStream()
      .findFirst()
      .orElseThrow(() ->
          new IllegalArgumentException("Line không thuộc Order"));

    managed.changeQuantity(nextQty);
}
~~~

Cách này không tự tải và thay cả collection của Order. Ví dụ dùng Jakarta Persistence với transaction do Spring quản lý.

### 9.5. Entity đầu mút độc lập không nên bị merge theo graph vô ý

Nếu Order chứa:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

và Customer có vòng đời độc lập, **không mặc định cascade MERGE từ Order sang Customer** nếu cập nhật Order không được phép sửa thông tin Customer. Service nên tải hoặc tham chiếu Customer theo ID sau khi kiểm tra quyền. Chỉ thêm cascade khi có một chủ thể sở hữu vòng đời/phạm vi cập nhật phù hợp.

## 10. @Version và xung đột từ detached snapshot cũ

Detached entities có thể sống lâu. Một người dùng tải form lúc 10:00 và chỉ gửi yêu cầu sửa lúc 10:30. Trong khoảng đó, một transaction khác có thể đã thay đổi cùng hàng.

### 10.1. Lost update

~~~text
10:00  User A đọc Customer#10:
       email=lan@old.example, name="Lan", version=3

10:05  User B sửa email thành lan@new.example và commit:
       version=4

10:30  User A gửi detached snapshot cũ:
       email=lan@old.example, name="Lan mới", version=3

10:30  Nếu merge snapshot cũ không kiểm soát version,
       email mới của B có nguy cơ bị ghi đè.
~~~

Dù A chỉ định sửa name, object detached có thể vẫn chứa email cũ.

### 10.2. Optimistic locking bằng @Version

~~~java
@Version
private Long version;
~~~

Nếu source detached giữ version 3, nhưng DB đã là version 4, provider có thể phát hiện stale state và báo **OptimisticLockException** ở bước merge, flush hoặc commit tùy implementation.

SQL ý tưởng:

~~~sql
UPDATE customers
SET email = ?,
    display_name = ?,
    version = 4
WHERE id = 10 AND version = 3;
~~~

Khi DB không còn version 3, không có row được cập nhật theo điều kiện và xung đột được phát hiện.

Sau optimistic locking failure:
- Rollback transaction.
- Không tiếp tục dùng transaction đã lỗi.
- Đọc lại state trong transaction mới.
- Báo conflict, cho người dùng so sánh, hoặc retry toàn bộ operation khi an toàn.
- Không sửa field version bằng tay để “ép merge chạy được”.

### 10.3. Version không biến merge thành PATCH

Nếu source chứa email=null và version vẫn mới nhất, merge vẫn có thể áp null trái ý muốn. **@Version** phát hiện concurrent entity updates, không xác định field nào client được phép thay đổi. Cần DTO/command, domain validation, authorization và DB constraints riêng.

### 10.4. Entity bị xóa trong lúc detached

Nếu một Customer đã bị xóa khỏi DB sau khi source được tải, merge không phải cách “khôi phục” chắc chắn. Với versioned entity provider có thể ném optimistic locking exception. Với các mapping khác, chi tiết nhận diện new/detached và lỗi phụ thuộc provider. Muốn restore dữ liệu đã xóa phải có quy trình nghiệp vụ rõ, không dựa vào merge ngẫu nhiên.

## 11. Flush, commit, rollback và tham chiếu managed

### 11.1. Merge chưa commit

~~~java
tx.begin();

Customer managed = em.merge(detached);
managed.changeDisplayName("Tên mới");

em.flush();
// SQL có thể đã chạy, nhưng transaction chưa commit.

tx.commit();
// Chỉ khi commit thành công, thay đổi mới được hoàn tất.
~~~

**flush** đồng bộ SQL pending trong transaction; **commit** hoàn tất transaction nếu thành công. Một số constraint hoặc lỗi có thể chỉ phát sinh tại commit, nên không coi “merge trả về không lỗi” là bằng chứng dữ liệu đã lưu thành công.

### 11.2. Rollback không làm field Java tự quay về giá trị cũ

~~~java
Customer managed = em.merge(detached);
managed.changeDisplayName("Tên lỗi");
em.flush();
tx.rollback();
~~~

Sau rollback:
- DB không giữ thay đổi chưa commit.
- Object Java còn tham chiếu không tự chắc chắn trở về giá trị cũ.
- Persistence context có thể không còn phù hợp cho workflow sau lỗi; nạp lại state trong context/transaction mới khi cần.

### 11.3. Bảng phân biệt các thao tác

| Thao tác | Tác động | Có tự commit? |
|---|---|---|
| **merge(source)** | Copy state sang managed target | Không |
| **managed.changeName(...)** | Đổi state Java đang được tracking | Không |
| **flush()** | Gửi SQL pending | Không |
| **commit()** | Hoàn tất transaction nếu thành công | Có |
| **refresh(managed)** | Nạp lại state từ DB, có thể mất thay đổi chưa flush | Không |
| **clear()** | Detach managed entities | Không |
| **detach(entity)** | Detach một entity | Không |
| **close()** | Đóng EntityManager | Không tự commit |

### 11.4. Exception có thể xảy ra

- **IllegalArgumentException** khi argument không phải entity hợp lệ hoặc đã removed theo semantics JPA.
- **OptimisticLockException** khi version stale.
- Constraint violation từ database khi flush/commit.
- **PersistenceException** và exception theo provider/framework.
- Lỗi cascade hoặc quan hệ tới entity ở trạng thái không hợp lệ.
- Lỗi transaction bị đánh dấu rollback.

Nên xử lý ở boundary transaction, rollback và dịch lỗi DB thành thông báo nghiệp vụ khi xác định được nguyên nhân. Không bắt mọi exception rồi tiếp tục ghi bằng transaction đã lỗi.

## 12. Spring Data JPA save và đối tượng trả về

Nhiều ứng dụng không gọi **em.merge** trực tiếp mà gọi **JpaRepository.save(entity)**. Dù tên là “save”, implementation Spring Data JPA thông dụng chọn **persist hoặc merge theo nhận diện entity mới**:

- Entity được coi là new: gọi **EntityManager.persist(entity)**.
- Entity không được coi là new: gọi **EntityManager.merge(entity)** và trả managed result.

Cách xác định newness phụ thuộc mapping ID/version, cấu hình repository và có thể interface **Persistable**. Không khẳng định mọi lần save đều gọi merge hoặc luôn trả object khác source.

### 12.1. Khi repository gọi persist

~~~java
Customer source = new Customer(
    "new@example.com", "Người mới");

Customer saved = repository.save(source);
~~~

Nếu source được coi là new, **persist** làm chính source trở thành managed. saved có thể là source. Đừng suy từ trường hợp này rằng save của detached entity cũng cùng reference.

### 12.2. Khi repository gọi merge

~~~java
Customer detached = ...; // Entity từ context trước.
Customer saved = repository.save(detached);
~~~

Nếu repository chọn merge, saved là managed result trong persistence context còn hoạt động; detached vẫn là source.

Một lỗi:

~~~java
@Transactional
public void update(Customer detached) {
    repository.save(detached);
    detached.changeDisplayName("Tên sau save");
}
~~~

Nếu save đi qua merge, thay đổi sau save chỉ xảy ra trên detached source. Cần nhận return value:

~~~java
@Transactional
public void update(Customer detached) {
    Customer saved = repository.save(detached);
    saved.changeDisplayName("Tên sau save");
}
~~~

Dù vậy, với API chỉ sửa vài field nên cân nhắc load managed entity rồi gọi business method, thay vì merge cả detached graph.

### 12.3. SaveAndFlush không tự commit

~~~java
Customer saved = repository.saveAndFlush(detached);
~~~

Phương thức này flush SQL nhưng không có nghĩa transaction bao quanh đã commit. Một lỗi deferred constraint hoặc lỗi muộn vẫn có thể rollback. Không phản hồi API là thành công trước khi transaction hoàn tất.

### 12.4. Managed entity thường không cần save lại

~~~java
@Service
public class CustomerService {
    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public void rename(long id, String displayName) {
        Customer managed = customers.findById(id)
            .orElseThrow(() ->
                new IllegalArgumentException("Customer không tồn tại"));

        managed.changeDisplayName(displayName);
        // Dirty checking sẽ ghi trong transaction phù hợp.
    }
}
~~~

**@Transactional** trên public service method có tác dụng khi advice/proxy của Spring được áp dụng. Với self-invocation theo Spring proxy thông dụng, gọi method annotated từ method khác cùng instance có thể không đi qua advice. Không giữ EntityManager hay managed entities trong singleton field để chia sẻ nhiều HTTP requests: EntityManager không dành cho truy cập đồng thời từ nhiều thread.

### 12.5. Entity return value có thể trở thành detached về sau

Ngay cả khi **save** trả managed object trong transaction, khi transaction-scoped context đóng, result có thể trở thành detached. Một return value không bảo đảm managed **mãi mãi**, mà chỉ trong phạm vi persistence context tương ứng. Khi đưa dữ liệu ra API, dùng DTO/projection thay vì trả entity graph mà serializer truy cập lazy association ngoài context.

## 13. API an toàn hơn merge một detached entity từ request

Luồng dễ gây bug:

~~~text
GET /customers/10 trả toàn bộ Customer
    ↓
Client sửa một field
    ↓
PUT /customers/10 gửi một snapshot thiếu field
    ↓
Controller map JSON thành entity
    ↓
Service merge toàn bộ entity
    ↓
Các field/collection vắng mặt có nguy cơ bị ghi đè
~~~

Luồng có trách nhiệm rõ hơn:

~~~text
HTTP Request DTO
    ↓
Controller kiểm tra cấu trúc request
    ↓
Service @Transactional
      ├─ kiểm tra quyền actor
      ├─ find managed entity theo ID
      ├─ áp dụng đúng field được phép thay đổi
      ├─ kiểm tra business invariants
      └─ tạo response DTO
    ↓
flush / commit / rollback
~~~

### 13.1. DTO chuyên biệt

~~~java
public record RenameCustomerRequest(
    String displayName
) { }
~~~

Service:

~~~java
@Transactional
public CustomerResponse rename(
        long id, RenameCustomerRequest request) {

    Customer managed = em.find(Customer.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Customer không tồn tại");
    }

    managed.changeDisplayName(request.displayName());

    return new CustomerResponse(
        managed.getId(),
        managed.getDisplayName()
    );
}
~~~

Response:

~~~java
public record CustomerResponse(
    Long id,
    String displayName
) { }
~~~

Nếu response phải chứa version sau flush hoặc DB-generated columns, cần thiết kế thời điểm flush/refresh và serialization theo yêu cầu thật. Mẫu này chỉ minh họa update đúng field.

### 13.2. Khi nào merge là lựa chọn hợp lý?

Merge phù hợp nếu:
- Ứng dụng quản lý một detached entity graph **đầy đủ và đáng tin cậy** ngoài transaction.
- Người gọi biết rõ source bao gồm field và relationships nào.
- Business contract thực sự yêu cầu copy state đó vào context.
- Cascade, orphanRemoval, version và transaction đã được thiết kế đúng.
- Service sử dụng return value để thao tác tiếp.
- Conflict được xử lý, không chỉ bị ghi đè.

Ví dụ một công cụ chỉnh sửa offline lưu một aggregate cùng version, người dùng chỉnh đầy đủ, rồi gửi lại toàn bộ aggregate để merge. Đây là use case khác với việc map một PATCH JSON thiếu field thành entity rồi merge.

### 13.3. Merge cũng không tự bảo vệ request trùng

Khi request tạo mới bị gửi hai lần do timeout, merge không tự bảo đảm idempotency hay uniqueness theo business key. Có thể cần **UNIQUE** ở DB, idempotency key, transaction và logic xử lý duplicate. Không đồng nhất “merge có thể INSERT” với “gửi lại request sẽ luôn chỉ tạo một hàng”.

## 14. Tóm tắt từng trường hợp merge và instance cần sử dụng

| Tình huống | Source trước merge | Managed return value | Source sau merge |
|---|---|---|---|
| Entity từ context đã đóng | Detached | Một managed target trong context hiện tại | Vẫn detached |
| Entity mới chưa persist | New | Một managed copy | Không tự trở thành managed copy |
| Entity đã find trong chính context | Managed | Chính managed instance | Vẫn managed |
| Source detached, context đã có cùng ID | Detached | Managed instance có sẵn được copy state | Vẫn detached |
| Entity removed | Removed | Merge không hợp lệ | Không được “cứu” bằng merge |
| CascadeType.MERGE qua graph | Graph new/detached | Managed root và related targets phù hợp | Không tự trở thành managed graph |
| Spring Data save gọi persist | New | Thường là cùng source | Source trở thành managed |
| Spring Data save gọi merge | Non-new/detached | Managed result | Detached source vẫn detached |

**Managed** là một tính chất gắn với **instance cụ thể và persistence context cụ thể**, không phải nhãn cố định của một ID database.

### 14.1. Ba phép kiểm tra khác nhau

~~~java
Customer result = em.merge(source);

boolean sourceManaged = em.contains(source);
boolean resultManaged = em.contains(result);
boolean sameJavaObject = source == result;
~~~

Đối với source detached, thường nhận được **false, true, false**. Đối với source đã managed trong context hiện tại, nhận **true, true, true**.

~~~java
source.getId().equals(result.getId()); // Có thể true.
source == result;                       // Có thể false.
~~~

**Cùng ID không có nghĩa cùng Java reference**. Ngay cả khi **equals** được cài đặt dựa trên ID và trả true, hai object vẫn có thể có trạng thái managed/detached khác nhau. Không dùng equals để xác định liệu EntityManager có theo dõi chính instance đó không.

### 14.2. Hai EntityManager không tự đồng bộ object

~~~java
Customer source = em1.find(Customer.class, id);
Customer target = em2.merge(source);
~~~

Nếu cả em1 và em2 còn mở, mỗi bên có persistence context riêng. source có thể vẫn managed với em1 nhưng không managed với em2; target managed với em2. Việc thay đổi cả hai không có cơ chế đồng bộ hai chiều; transaction và @Version phải bảo vệ những ghi chồng chéo.

Thông thường service nên nạp và sửa entity bên trong **một transaction/persistence context** rõ ràng, không giữ entity managed qua nhiều request hoặc thread.

## 15. Integration test quan sát nguồn và kết quả

Một bài test chỉ so sánh thuộc tính sau merge không chứng minh dữ liệu được ghi thành công. Nên kiểm tra **reference identity**, **em.contains** và **round trip DB** sau flush/clear.

Các ví dụ giả định JUnit, EntityManager và test transaction được cấu hình.

### 15.1. Detached source khác managed result

~~~java
@Test
void detachedMergeReturnsAnotherManagedInstance() {
    Customer created = new Customer(
        "lan@example.com", "Lan ban đầu");

    em.persist(created);
    em.flush();

    Long id = created.getId();
    em.clear(); // created trở thành detached.

    created.changeDisplayName("Lan offline");

    Customer managed = em.merge(created);

    assertNotSame(created, managed);
    assertFalse(em.contains(created));
    assertTrue(em.contains(managed));
    assertEquals(id, managed.getId());

    em.flush();
    em.clear();

    Customer reloaded = em.find(Customer.class, id);
    assertEquals("Lan offline", reloaded.getDisplayName());
}
~~~

### 15.2. Thay đổi trên source sau merge không tự được lưu

~~~java
@Test
void changingSourceAfterMergeDoesNotModifyManagedTarget() {
    Customer source = new Customer(
        "mai@example.com", "Mai ban đầu");

    em.persist(source);
    em.flush();
    Long id = source.getId();

    em.clear();
    source.changeDisplayName("Tên tại lúc merge");

    Customer managed = em.merge(source);
    source.changeDisplayName("Tên đổi tiếp trên detached");

    assertEquals("Tên tại lúc merge",
                 managed.getDisplayName());

    em.flush();
    em.clear();

    Customer dbValue = em.find(Customer.class, id);
    assertEquals("Tên tại lúc merge",
                 dbValue.getDisplayName());
}
~~~

### 15.3. Target đã nằm sẵn trong context

~~~java
@Test
void mergeUsesExistingManagedInstance() {
    Customer customer = new Customer(
        "test@example.com", "Bản gốc");

    em.persist(customer);
    em.flush();
    Long id = customer.getId();

    em.clear();
    Customer detached = em.find(Customer.class, id);
    em.detach(detached);

    Customer alreadyManaged = em.find(Customer.class, id);
    detached.changeDisplayName("Từ detached");

    Customer result = em.merge(detached);

    assertSame(alreadyManaged, result);
    assertNotSame(detached, result);
    assertEquals("Từ detached",
                 alreadyManaged.getDisplayName());
}
~~~

### 15.4. Source đã managed

~~~java
@Test
void mergeManagedEntityReturnsSameReference() {
    Customer managed = new Customer(
        "same@example.com", "Same");
    em.persist(managed);

    Customer result = em.merge(managed);

    assertSame(managed, result);
    assertTrue(em.contains(result));
}
~~~

### 15.5. Source new

~~~java
@Test
void mergeNewEntityReturnsManagedCopy() {
    Customer source = new Customer(
        "new@example.com", "New");

    Customer result = em.merge(source);

    assertNotSame(source, result);
    assertFalse(em.contains(source));
    assertTrue(em.contains(result));

    em.flush();
    assertNotNull(result.getId());
}
~~~

Không assert rằng source.getId() phải được gán. **result** là nguồn identity được JPA quản lý.

### 15.6. Test version conflict bằng hai transaction

Quy trình:
1. Transaction A load Customer version V và tách entity.
2. Transaction B load cùng Customer, thay đổi và commit version V+1.
3. Transaction A mới merge entity version V.
4. Cố flush/commit trong transaction A.
5. Kỳ vọng optimistic locking failure tại bước do provider xác định.

Phải chạy bằng hai persistence contexts/transactions độc lập; dùng cùng một EntityManager sẽ bị identity map hợp nhất instance và không còn mô phỏng được tình huống detached stale.

### 15.7. Các trường hợp cần bổ sung

| Test | Kỳ vọng |
|---|---|
| Merge source thiếu field được set null | Thấy rủi ro overwrite/constraint thay vì ngầm giả định PATCH |
| Merge parent có CascadeType.MERGE | Child state được đưa vào managed graph phù hợp |
| Merge parent có orphanRemoval | Không xóa child ngoài ý muốn khi update một field |
| Merge entity đã removed | Bị từ chối theo semantics JPA |
| Flush rồi rollback | DB không giữ thay đổi, object RAM không được giả định rollback tự động |
| save trong nhánh persist | Source có thể chính là managed instance |
| save trong nhánh merge | Return value có thể khác detached source |
| unique constraint | Database chặn duplicate dù check ứng dụng bị race |
| Lazy state chưa fetch | Không bị hiểu như explicit null do mapper tạo |

## 16. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Merge xong sửa field nhưng DB không đổi | Sửa detached source | Giữ và sửa managed return value |
| Source và result có ID giống nhưng reference khác | Source detached/new, result managed | Đây là semantics bình thường |
| Source không nhận generated ID | Merge new tạo managed copy | Đọc ID từ result ở thời điểm thích hợp |
| Spring save trả instance khác | save đi qua EntityManager.merge | Dùng return value |
| Merge entity đã find sẵn không tạo object mới | Source đã managed | Không cần merge để dirty checking |
| Field đang sửa bị giá trị cũ ghi đè | Merge detached snapshot vào managed target đã đổi | Tránh merge state cũ, dùng DTO + method |
| Null overwrite | DTO thiếu field được map thành null | Load managed, sửa field được phép |
| Collection con bị xóa | Merge graph thiếu phần tử + orphanRemoval | Tránh merge partial graph |
| Quan hệ child không được lưu | Cascade hoặc owning side chưa đúng | Thiết kế cascade/helper phù hợp |
| @Version báo stale | Transaction khác đã sửa dữ liệu | Rollback và xử lý optimistic conflict |
| Merge không báo lỗi nhưng commit lỗi | SQL/constraint kiểm tra muộn | Xử lý ở transaction boundary |
| Rollback rồi object vẫn có giá trị mới | Rollback DB không tự reset Java fields | Nạp lại bằng context mới |
| Màn hình JSON bị đệ quy | Serialize entity graph hai chiều | Dùng response DTO |
| Merge bị xem như UPSERT | Không có atomic upsert semantics | Unique/idempotency/transaction rõ |
| Không phân biệt source managed | Chỉ nhìn ID hoặc equals | Dùng em.contains và reference identity |
| Hai EntityManager cùng sửa | Hai persistence contexts độc lập | Dùng transaction/version hợp lệ |
| Lazy field xử lý không như dự kiến | Nhầm unfetched state với explicit null | Nắm fetch state và provider behavior |

Một cách chẩn đoán thực dụng là quan sát **em.contains(source/result)**, ID/version, thời điểm flush và SQL thực tế. Có thể dùng **System.identityHashCode** trong log thử nghiệm để phân biệt Java instances, nhưng không dùng nó làm database identity hay khóa nghiệp vụ. Tránh log PII và dữ liệu nhạy cảm ở production.

## 17. Bài tập thực hành

### Bài 1: Nhận diện hai instance

~~~java
Customer detached = ...; // Đã được load ở EntityManager trước.
Customer result = em.merge(detached);
~~~

Giả sử detached không managed trong em. Hãy dự đoán:
- **detached == result**?
- **em.contains(detached)**?
- **em.contains(result)**?
- **detached.getId().equals(result.getId())**?

**Gợi ý:** false, false, true, true trong trường hợp detached hợp lệ được merge thành công.

### Bài 2: Sửa một bug sau merge

~~~java
@Transactional
public void approve(Customer detached) {
    em.merge(detached);
    detached.changeDisplayName("APPROVED");
}
~~~

Vì sao giá trị mới có thể không được lưu? Viết lại bằng managed result. Sau đó viết một bản khác dùng **em.find(id)** và chỉ thay field cần thiết.

### Bài 3: Merge một object mới

~~~java
Customer source = new Customer("x@example.com", "X");
Customer managed = em.merge(source);
em.flush();
~~~

Hãy giải thích:
- Object nào được JPA quản lý?
- Object nào nên dùng để lấy ID generated?
- Nếu gọi source.changeDisplayName sau merge thì sao?
- Khi biết object new, tại sao persist có semantics rõ hơn?

### Bài 4: Source và target cùng ID nhưng state khác

~~~java
Customer current = em.find(Customer.class, 10L);
current.changeDisplayName("A");

Customer detached = ...; // id=10, displayName="B"
Customer result = em.merge(detached);
~~~

Hỏi: result có bằng reference của current không? DisplayName sau merge có thể là gì? Vì sao không có hai managed Customer#10 trong context? Nếu cần giữ thay đổi A, cách merge snapshot B đã phù hợp chưa?

### Bài 5: Null overwrite

Một HTTP PATCH chỉ gửi **displayName**, nhưng mapper tạo entity có **email=null**. Tại sao merge nguy hiểm? Viết service method load managed Customer và chỉ gọi **changeDisplayName**. Nếu muốn cho phép clear một field optional, cần phân biệt **explicit null** và **field không gửi** ra sao?

### Bài 6: Cascade MERGE và orphanRemoval

Order có các Line A, B, C. Detached object từ JSON chỉ có A vì request không gửi B/C. Mapping Order.lines có **orphanRemoval=true**.

Giải thích:
- Vì sao merge có thể xóa B/C?
- CascadeType.MERGE ảnh hưởng managed graph hay source graph?
- Source Line A có tự trở thành managed không?
- Có thể sửa quantity A bằng một managed OrderLine mà không thay toàn bộ collection như thế nào?

### Bài 7: Lazy unfetched và null

So sánh:
- Một detached Order với lines LAZY chưa được provider fetch.
- Một object Order mới dựng từ DTO có lines=null.

Vì sao hai trường hợp không tương đương khi merge? Quy tắc ignore unfetched lazy state giải quyết vấn đề nào và không giải quyết vấn đề nào?

### Bài 8: Xung đột version

T1 tải Customer version 5 rồi detach. T2 sửa Customer, commit version 6. T1 merge source version 5.

Hãy nêu nơi có thể xuất hiện optimistic locking exception và cách xử lý. Tại sao không nên gán source.version=6 chỉ để merge thành công?

### Bài 9: Spring Data save

Phân tích hai trường hợp **repository.save(customer)**: nhánh persist khi new và nhánh merge khi non-new. Khi nào giá trị trả về có thể cùng reference? Khi nào bắt buộc giữ return value để sửa tiếp? **saveAndFlush** đã chắc chắn commit chưa?

### Bài 10: Equality và managed state

Hai Customer Java objects có cùng ID nhưng một detached và một managed. Equals có thể trả true. Vì sao **==** vẫn false? **em.contains** trả true cho object nào? Tại sao equals/hashCode không thay được kiểm tra trạng thái persistence?

### Bài 11: Rollback

Trong transaction, code merge detached, sửa result, flush, rồi rollback. Database và Java object còn giữ có trạng thái thế nào? Vì sao cần load lại sau lỗi?

### Bài 12: Viết integration test

Tạo Customer bằng persist, flush/clear để detach; sửa source; merge; assertNotSame và em.contains; sửa source thêm lần nữa; flush/clear; find từ DB. Viết assertion để chứng minh DB không tự nhận thay đổi trên detached source sau merge.

### Bài 13: Thiết kế endpoint

Đề xuất endpoint **PATCH /customers/{id}/display-name** chỉ nhận displayName. Viết DTO, service @Transactional và response DTO. Giải thích vì sao không cần merge cả detached entity.

### Bài 14: Hai EntityManager

EM1 tải Customer#10; EM2 cũng tải Customer#10 rồi EM2.merge(instance từ EM1). Có mấy context? Có mấy Java references? Mỗi context có thể commit những thay đổi nào? @Version giúp phát hiện xung đột thế nào?

## 18. Checklist sử dụng merge

Khi chuẩn bị gọi **EntityManager.merge**, hãy trả lời:

1. **Source đang new, detached hay managed?** Nếu managed chỉ cần dirty checking; nếu new có thể dùng persist.
2. **Source có đầy đủ và đáng tin cậy không?** Partial DTO không phải detached graph hoàn chỉnh.
3. **Tại sao cần copy toàn bộ state?** Nếu chỉ update vài field, dùng find + domain methods.
4. **Có giữ return value không?** Sửa result sau merge, không sửa source detached và mong tự lưu.
5. **Target đã có trong context chưa?** Merge có thể ghi đè những field vừa được sửa.
6. **Cascades có hợp lý không?** Không để cập nhật Order vô tình cập nhật Customer hoặc xóa child.
7. **Collection có đầy đủ chưa?** Merge partial graph với orphanRemoval có thể DELETE ngoài ý muốn.
8. **Có @Version không?** Snapshot có thể stale và phát sinh conflict.
9. **Có transaction boundary rõ không?** Merge, flush và commit khác nhau.
10. **Có constraint DB thật không?** NOT NULL, UNIQUE, FK và CHECK cần tồn tại trong schema.
11. **Request có được phép sửa các field ấy không?** Authorization và validation không do merge tự làm.
12. **Đã kiểm tra bằng flush/clear/find chưa?** Xác minh DB state thay vì chỉ object RAM.

Ghi nhớ ngắn:

~~~text
persist(new)
  → chính đối tượng new trở thành managed.

merge(detached)
  → chép state sang một managed target.
  → trả managed target.
  → source detached vẫn detached.

merge(new)
  → tạo managed copy.
  → source không tự trở thành managed copy.

merge(managed)
  → source vốn đã managed.
  → thường trả chính instance đã managed.

sau merge(detached):
  phải sửa return value nếu muốn dirty checking.

flush ≠ commit.
cùng ID ≠ cùng reference Java.
equals true ≠ cùng trạng thái managed.
merge ≠ HTTP PATCH.
merge ≠ UPSERT nguyên tử.
~~~

**Kết luận:** **merge** là phép **sao chép trạng thái từ đối tượng nguồn vào một managed instance và trả về instance ấy**, không phải thao tác biến chính detached source thành managed. Phân biệt source với return value, cùng persistence identity với Java reference identity, và merge với flush/commit giúp tránh sửa nhầm object, làm mất dữ liệu vì snapshot cũ hoặc null, xóa collection ngoài ý muốn và dùng sai Spring Data save. Khi cần cập nhật một vài thuộc tính trong giao dịch, **load managed entity rồi áp dụng phương thức nghiệp vụ** thường rõ ràng hơn; khi thật sự cần merge detached graph, phải giữ return value và kiểm soát version, cascade, quan hệ và transaction.



