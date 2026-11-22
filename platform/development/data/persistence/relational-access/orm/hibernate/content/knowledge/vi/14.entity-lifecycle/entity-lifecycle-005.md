# merge và sự khác nhau giữa đối tượng truyền vào với kết quả được quản lý

Trong Hibernate/JPA, `merge()` là một trong những API dễ gây hiểu nhầm nhất của vòng đời entity. Nhiều người thấy đoạn code:

~~~java
entityManager.merge(customer);
~~~

rồi kết luận rằng `customer` đã “được gắn lại” vào `EntityManager` và Hibernate sẽ theo dõi mọi sửa đổi tiếp theo của chính biến đó. **Kết luận này không đúng với một entity detached.**

Ý nghĩa cốt lõi của `merge()` là: **sao chép trạng thái persistent từ đối tượng nguồn vào một đối tượng tương ứng đang được quản lý trong persistence context, rồi trả về đối tượng managed đó**. Đối tượng truyền vào **không tự trở thành managed** chỉ vì được gọi `merge()`.

Sự khác biệt giữa **đối tượng truyền vào** và **đối tượng trả về** ảnh hưởng trực tiếp đến việc cập nhật dữ liệu, optimistic locking, cascade, transaction, quan hệ và cách dùng repository. Bài học này trình bày toàn bộ luồng thao tác, những trường hợp cụ thể và cách tránh ghi đè dữ liệu không mong muốn.

## 1. Ôn lại các trạng thái của entity

Một entity JPA có thể trải qua các trạng thái sau:

| Trạng thái | Ý nghĩa | Hibernate có theo dõi thay đổi? |
| --- | --- | --- |
| **New/transient** | Đối tượng Java mới được tạo, chưa có identity persistent được quản lý | Chưa |
| **Managed/persistent** | Đối tượng có mặt trong persistence context của `EntityManager` hiện tại | Có, theo mapping và cơ chế dirty checking |
| **Detached** | Đã từng thuộc persistence context nhưng hiện không còn được quản lý ở đó | Không, đối với context đã tách |
| **Removed** | Đối tượng được đánh dấu xóa trong persistence context | Đang trong quá trình xóa khi flush/commit |

Một đối tượng có `id != null` **không đủ để chứng minh** nó đang managed. ID chỉ là một phần identity persistent; trạng thái managed còn phụ thuộc vào **persistence context cụ thể**.

Ví dụ:

~~~java
Customer customer = entityManager.find(Customer.class, 42L);
// customer là managed trong EntityManager hiện tại.

entityManager.detach(customer);
// customer vẫn có id, name, version..., nhưng giờ là detached.

customer.setName("Đổi tên ở ngoài context");
// Hibernate không tự theo dõi sửa đổi này qua context vừa detach.
~~~

Có thể dùng `entityManager.contains(customer)` để kiểm tra một đối tượng có đang được quản lý **bởi EntityManager này** hay không:

~~~java
boolean isManaged = entityManager.contains(customer);
~~~

`contains()` không trả lời rằng hàng tương ứng có tồn tại trong database hay không; nó trả lời câu hỏi về **đối tượng Java và persistence context hiện tại**.

### 1.1. Tại sao detached thường xuất hiện?

Detached không phải lỗi bất thường. Nó xuất hiện tự nhiên khi:

- Transaction/persistence context kết thúc và entity được giữ lại để dùng sau.
- `EntityManager` được đóng.
- Gọi `entityManager.detach(entity)` hoặc `entityManager.clear()`.
- Một entity được gửi qua tầng giao diện, qua một request, rồi được đưa trở lại ở request khác.
- Đối tượng được deserialize hoặc được dựng lại từ một nguồn bên ngoài, mang identity tương ứng với bản ghi đã có.

Điều quan trọng là phân biệt **đối tượng Java đang tồn tại** với **đối tượng đang được Hibernate quản lý trong ngữ cảnh hiện tại**.

## 2. merge() thực sự làm gì?

Phương thức chuẩn JPA:

~~~java
<T> T EntityManager.merge(T entity);
~~~

Khi truyền một entity detached vào `merge()`, JPA/Hibernate về mặt khái niệm sẽ:

1. Xác định entity type và persistent identity của đối tượng nguồn.
2. Tìm một đối tượng **managed tương ứng** trong persistence context; nếu chưa có, có thể phải tải từ database hoặc tạo managed instance phù hợp.
3. Sao chép trạng thái persistent được phép merge từ đối tượng nguồn sang managed instance.
4. Xử lý các liên kết được cấu hình cascade `MERGE`/`ALL` theo quy tắc JPA.
5. Trả về managed instance.
6. Đồng bộ thay đổi của managed instance xuống database khi flush/commit theo transaction hợp lệ.

**Không phải toàn bộ các bước trên đều là một câu UPDATE ngay lúc gọi `merge()`.** Hibernate có thể cần SELECT, có thể dùng object đã managed, và có thể trì hoãn SQL UPDATE đến flush. Nếu trạng thái persistent không thay đổi, thậm chí có thể không có UPDATE.

~~~mermaid
flowchart TD
    A["detachedCustomer<br/>đối tượng nguồn, không managed"] -->|"em.merge(detachedCustomer)"| B{"Managed instance<br/>đã có trong context?"}
    B -->|"Có"| C["Lấy instance managed hiện có"]
    B -->|"Chưa"| D["Tải/tạo instance managed phù hợp"]
    D --> C
    C -->|"Sao chép persistent state"| E["managedCustomer<br/>đối tượng kết quả"]
    E -->|"dirty checking + flush/commit"| F[("Database")]
    A -. "Vẫn detached, không tự được gắn lại" .-> A
~~~

### 2.1. Đối tượng truyền vào và kết quả trả về

Với một entity detached thông thường:

~~~java
Customer managedCustomer = entityManager.merge(detachedCustomer);
~~~

thì:

- `detachedCustomer`: là **nguồn trạng thái**, tiếp tục là đối tượng detached.
- `managedCustomer`: là **đối tượng managed** tương ứng do `merge()` trả về.
- Hai biến thường tham chiếu tới **hai Java object khác nhau**.
- Hibernate theo dõi sửa đổi trên `managedCustomer`, **không theo dõi** sửa đổi tiếp theo trên `detachedCustomer`.
- Cả hai object có thể có cùng persistent identity (cùng ID và entity type), nhưng không có cùng **Java object identity** (tham chiếu bộ nhớ).

Đây là lý do nên **luôn dùng giá trị trả về** khi thực sự muốn làm việc tiếp với entity managed sau merge.

## 3. Ví dụ hoàn chỉnh với Customer

Giả sử bảng `customers` có `id`, `name`, `email` và `version`. Entity:

~~~java
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

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, length = 200)
    private String email;

    @Version
    private long version;

    protected Customer() {
        // Constructor cho JPA.
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public long getVersion() {
        return version;
    }

    public void rename(String value) {
        this.name = value;
    }

    public void changeEmail(String value) {
        this.email = value;
    }
}
~~~

Đoạn tiếp theo giả định `EntityManager em` đang mở, có transaction hợp lệ, và schema tương thích với mapping.

### 3.1. Tạo entity rồi detach

~~~java
Customer original = new Customer(
    "An",
    "an@example.test"
);

em.persist(original);
em.flush();          // Bản ghi được đồng bộ xuống DB.
Long id = original.getId();

System.out.println(em.contains(original)); // true

em.detach(original);

System.out.println(em.contains(original)); // false
~~~

`original` vẫn là một object Java có ID, tên và email. Nhưng nó không còn được Hibernate theo dõi trong persistence context hiện tại.

Thay đổi sau đây diễn ra **chỉ trên object detached**:

~~~java
original.rename("An Nguyen");
~~~

Nếu không có thao tác lưu phù hợp nào khác, riêng thay đổi này **không tự sinh UPDATE** trong context đã detach.

### 3.2. Merge và kiểm tra object identity

~~~java
Customer merged = em.merge(original);

System.out.println(em.contains(original)); // false
System.out.println(em.contains(merged));   // true

System.out.println(original == merged);    // false với original detached
System.out.println(original.getId().equals(merged.getId())); // true
~~~

Ở thời điểm này, `original` và `merged` có thể có cùng dữ liệu persistent được sao chép, nhưng chúng không phải cùng object.

Nếu sửa tiếp:

~~~java
original.rename("Tên chỉ sửa trên detached");
merged.changeEmail("new-an@example.test");

em.flush();
~~~

Hibernate theo dõi `merged`. Vì vậy, email mới trên `merged` là trạng thái được quản lý; còn tên thay đổi thêm trên `original` **sau lần merge** không tự được sao chép tiếp sang `merged`.

Nếu cần tên mới nhất từ `original`, phải thực hiện một thao tác có chủ đích để đưa thay đổi đó vào managed state, chẳng hạn cập nhật `merged` hoặc cân nhắc merge lại trong điều kiện phù hợp. Cách rõ ràng hơn thường là **ngừng sửa detached object sau merge và chỉ sử dụng managed result**.

### 3.3. Vì sao phải gọi flush để quan sát?

Trong JPA, `merge()` không bảo đảm SQL UPDATE được thực thi ngay tại dòng gọi. Hibernate có thể ghi khi flush, trước một số truy vấn hoặc lúc commit. Điều đó phụ thuộc trạng thái entity, flush mode và transaction.

~~~java
Customer managed = em.merge(original);

// Đối tượng managed đã có state được sao chép.
System.out.println(managed.getName());

// SQL có thể được gửi tại đây:
em.flush();
~~~

Đừng dùng việc chưa thấy SQL lập tức để kết luận merge không hoạt động. Cũng đừng kết luận database đã được cập nhật bền vững chỉ vì vừa gọi `flush()`: **commit transaction** mới quyết định việc thay đổi được xác nhận sau giao dịch.

## 4. Trường hợp EntityManager đã có một instance managed cùng ID

Một persistence context chỉ nên có **một managed entity instance cho một persistent identity** tại một thời điểm. Giả sử:

~~~java
Customer managed = em.find(Customer.class, customerId);
Customer detached = loadDetachedCopyFromPreviousRequest();

Customer result = em.merge(detached);
~~~

Ở đây `loadDetachedCopyFromPreviousRequest()` là một phương thức minh họa trả về object detached đại diện cho cùng bản ghi.

Nếu `managed` đã tồn tại trong persistence context cho cùng identity, `merge()` sẽ sao chép trạng thái của `detached` lên managed instance đó và trả về managed reference:

~~~java
System.out.println(result == managed); // Thường là true.
System.out.println(result == detached); // Không, nếu detached thật.
~~~

Đây là một tình huống nguy hiểm khi detached object mang dữ liệu **cũ hoặc thiếu**:

~~~java
Customer managed = em.find(Customer.class, id);
managed.changeEmail("new@example.test");

// Một object detached cũ vẫn giữ email trước đây.
Customer result = em.merge(detachedOldCustomer);
~~~

Nếu email nằm trong persistent state được merge, thao tác này có thể **ghi đè email mới của managed object bằng giá trị cũ** từ detached source. `merge()` không phải thuật toán “chỉ cập nhật field đã sửa ở client”; nó sao chép trạng thái theo mapping, không tự biết ý nghĩa “field không được người dùng nhập”.

Cần xem version, validation và cơ chế phối hợp dữ liệu để tránh mất cập nhật.

## 5. Đối tượng truyền vào có thể ở trạng thái nào?

`merge()` không chỉ nhận detached entity. Hiểu đầy đủ hơn:

| Trạng thái nguồn | Hành vi merge về mặt khái niệm | Đối tượng trả về |
| --- | --- | --- |
| **Detached** | Sao chép trạng thái sang managed entity tương ứng | Managed instance; đối tượng truyền vào tiếp tục detached |
| **New/transient** | Tạo một managed copy, với thao tác insert sẽ được lên lịch khi thích hợp | Managed copy; nguồn vẫn không tự managed |
| **Managed** | Nguồn đã managed; trạng thái đang do context theo dõi, cascade merge có thể được xử lý | Managed entity tương ứng, thường chính nguồn đó |
| **Removed** | Không phải trạng thái hợp lệ để merge như một entity bình thường | Có thể ném `IllegalArgumentException` theo quy tắc JPA |

Đối với entity new, việc `merge()` quyết định insert hay load tùy ID, mapping, unsaved-value/version và cách Hibernate phân loại đối tượng. **Không tự gán ID tùy tiện rồi kỳ vọng merge luôn INSERT hoặc luôn UPDATE.** Với các bản Hibernate mới, những trường hợp đối tượng được xác định chắc chắn là detached nhưng hàng trong database đã biến mất có thể dẫn đến lỗi optimistic locking/stale state thay vì tự INSERT lại.

### 5.1. New entity: nên dùng persist() khi mục đích là tạo mới

~~~java
Customer source = new Customer(
    "Binh",
    "binh@example.test"
);

Customer managed = em.merge(source);
~~~

`managed` là object được Hibernate quản lý; `source` vẫn không trở thành managed. Với ID generated như IDENTITY, giá trị ID có thể chưa được đồng bộ theo cách người gọi mong đợi tại mọi điểm trong quá trình insert. Nên dùng object trả về khi cần lấy ID/giá trị generated của bản managed.

Nếu nhiệm vụ chỉ là tạo mới:

~~~java
Customer created = new Customer(
    "Binh",
    "binh@example.test"
);

em.persist(created);
// created chính là managed instance.
~~~

`persist()` rõ ý định hơn và không tạo ra hai biến có cùng logical identity nhưng khác object identity như merge(new entity).

### 5.2. Managed entity: thường không cần merge

~~~java
Customer customer = em.find(Customer.class, id);
customer.rename("Tên mới");

// Không cần em.merge(customer) chỉ để ghi thay đổi.
~~~

Nếu đang trong transaction và entity managed, dirty checking sẽ xử lý thay đổi persistent khi flush/commit. Việc gọi merge thừa có thể làm code rối và gây cascade không cần thiết.

### 5.3. Removed entity: không dùng merge để “khôi phục”

~~~java
Customer customer = em.find(Customer.class, id);
em.remove(customer);
// em.merge(customer); // Không phải cách khôi phục đúng.
~~~

Một entity đang removed có vòng đời khác. Nếu nghiệp vụ cần khôi phục soft delete, nên thiết kế lệnh restore riêng hoặc cơ chế soft-delete tương ứng, không giả định `merge()` đảo ngược `remove()`.

## 6. persist() và merge() khác nhau ở điểm nào?

| Tiêu chí | `persist(entity)` | `merge(entity)` |
| --- | --- | --- |
| Mục đích chính | Đưa entity mới vào persistence context để insert | Sao chép persistent state vào managed entity tương ứng |
| Giá trị trả về | `void` | Managed entity reference |
| Object truyền vào | Với entity mới, chính object này trở thành managed | Với detached/new source, object truyền vào không tự managed |
| Với detached entity | Không phải thao tác đúng; có thể báo lỗi | Là use case chính |
| Với managed entity | Không cần để tiếp tục tracking | Thường thừa |
| SQL tức thì? | Không bảo đảm INSERT ngay, trừ yêu cầu generation/flush | Không bảo đảm SELECT/UPDATE ngay như cách người dùng tưởng |
| Cascade | `CascadeType.PERSIST` / `ALL` | `CascadeType.MERGE` / `ALL` |
| Việc tiếp tục sửa dữ liệu | Sửa object đã persist khi còn managed | Sửa **object trả về** khi còn managed |

Không phải lúc nào “có ID” cũng có nghĩa nên merge, hoặc “ID null” luôn có nghĩa nên persist. Quyết định còn liên quan đến ID generation, version, trạng thái entity, quy tắc nghiệp vụ và framework ở tầng repository.

### 6.1. Không nhầm với Session.update() của Hibernate cũ

Trong API Hibernate native có các cơ chế reattachment như `Session.update()` ở một số thế hệ API, với semantics khác `merge()`. Chúng không nên bị xem là tương đương, và sự sẵn có của các API này thay đổi qua các phiên bản Hibernate.

Cách diễn đạt an toàn khi học JPA là:

- `persist()`: quản lý chính object mới.
- `merge()`: sao chép trạng thái từ object truyền vào sang object managed được trả về.
- Với object managed đã load qua `find()`, thường chỉ cần thay đổi thuộc tính trong transaction.

## 7. Những nhầm lẫn trực tiếp về biến truyền vào và biến trả về

Hãy nhìn đoạn code:

~~~java
Customer detached = getCustomerFromSomewhere();

em.merge(detached);

detached.rename("Tên cuối cùng");

em.flush();
~~~

Thay đổi sau lệnh merge có thể **không được lưu**, vì `detached` không được gắn trở lại. Đây là lỗi dễ gặp khi bỏ qua return value.

Nên viết:

~~~java
Customer managed = em.merge(detached);
managed.rename("Tên cuối cùng");

em.flush();
~~~

Hoặc nếu chỉ cần áp dụng thay đổi từ một DTO:

~~~java
Customer managed = em.find(Customer.class, dto.id());
managed.rename(dto.name());
managed.changeEmail(dto.email());
~~~

Cách thứ hai thường an toàn và dễ kiểm soát hơn vì bạn quyết định chính xác field nào được phép thay đổi.

### 7.1. Sau khi transaction kết thúc, managed result có còn managed mãi không?

Không. `merge()` trả về đối tượng managed **trong persistence context hiện tại**.

Khi context đóng hoặc entity bị detach/clear, chính object trả về đó **cũng có thể trở thành detached**:

~~~java
Customer managed = em.merge(detached);
em.flush();

em.clear();

System.out.println(em.contains(managed)); // false
~~~

Vì vậy, câu “dùng biến trả về sau merge” phải được hiểu đúng scope: **sử dụng biến trả về khi còn trong context/transaction nơi nó được quản lý**, không phải giữ đối tượng đó qua mọi request rồi kỳ vọng Hibernate theo dõi mãi.

## 8. merge() sao chép trạng thái gì?

`merge()` hướng tới **persistent state** theo mapping, không phải toàn bộ nội dung bộ nhớ của một Java object một cách mù quáng.

Xét entity:

~~~java
@Entity
public class Profile {

    @Id
    private Long id;

    private String displayName;

    @Transient
    private String uiMessage;

    private transient String temporaryNote;

    // Getters/setters...
}
~~~

Với field access, hai field `uiMessage` và `temporaryNote` không thuộc persistent state. Việc merge không có trách nhiệm lưu chúng xuống database; không nên dựa vào merge để chuyển các giá trị không persistent từ source sang managed target.

Tương tự, các thuộc tính được ánh xạ `updatable = false`, field generated hoặc property chịu converter có semantics riêng. Không thể kết luận rằng mọi field Java được copy nguyên vẹn rồi sinh một UPDATE tương ứng.

### 8.1. Trạng thái từ entity detached có thể là dữ liệu cũ

Detached object không tự đồng bộ với database trong thời gian tách khỏi context. Nếu nó được giữ trong session web hoặc client rồi gửi lại sau vài phút, các giá trị có thể đã bị transaction khác sửa.

Khi merge, những giá trị cũ có thể được sao chép về managed instance. Cần đánh giá:

- Có `@Version` để phát hiện xung đột không?
- Client gửi về toàn bộ entity hay chỉ những trường được phép sửa?
- Trường không gửi có bị deserialize thành `null` và vô tình ghi đè dữ liệu không?
- Có field nhạy cảm mà client không được quyền thay đổi không?
- Có quan hệ/cascade mà client không nên điều khiển không?

**Merge không phải cơ chế patch HTTP.** Với PATCH hoặc form chỉ cập nhật vài thuộc tính, tốt hơn là load managed entity và áp dụng các thay đổi đã validate theo whitelist.

### 8.2. Lazy attribute chưa được tải

Một detached entity có thể có thuộc tính lazy chưa initialized. Theo semantics JPA, provider phải xử lý trạng thái chưa được fetch của các thuộc tính lazy và không được xem chúng như giá trị đã biết để ghi đè tùy tiện trong quá trình merge.

Điều đó **khác** với việc client dựng một object Java mới có `null` trong field và gọi merge; `null` đó có thể là trạng thái persistent thực sự được sao chép. Không đánh đồng “lazy chưa tải của một detached entity do JPA cung cấp” với “field không có trong JSON request”.

Để cập nhật một phần, tránh việc dựng entity từ JSON rồi merge thẳng vào database.

## 9. Cascade MERGE và đồ thị entity

Đối với quan hệ có cascade:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.MERGE
)
private List<OrderLine> lines = new ArrayList<>();
~~~

khi merge `Order`, Hibernate có thể cascade merge tới các `OrderLine` liên quan. Nhưng `cascade = MERGE` **không thay đổi owning side của FK** và **không tự biến domain graph thành đúng nghiệp vụ**.

Điều quan trọng:

1. Hibernate tạo/tìm **managed copy** của entity con theo identity.
2. State từ detached child có thể được sao chép sang managed child.
3. Quan hệ hai chiều vẫn phải có mapping owning side phù hợp.
4. Collection có thể có semantics orphan removal, ordered list, bag hoặc set khác nhau.
5. Những child mới và child cũ trong cùng một graph phải có identity hợp lệ.
6. Một object graph quá rộng có thể gây nhiều SELECT, INSERT, UPDATE ngoài dự kiến.

### 9.1. Không giữ giả định rằng source graph trở thành managed

Ví dụ:

~~~java
Order detachedOrder = loadDetachedOrder();

Order managedOrder = em.merge(detachedOrder);
~~~

Nếu merge được cascade, các phần tử trong `managedOrder.getLines()` là những managed references hoặc giá trị tương ứng theo Hibernate. Những object trong `detachedOrder.getLines()` **không tự được “gắn lại”** thành managed chỉ bởi cascade merge.

Vì thế, sau merge, không nên tiếp tục sửa `detachedOrder` hoặc các child detached rồi kỳ vọng SQL tự xuất hiện.

### 9.2. Collection thiếu phần tử: có thể dẫn tới xóa con

Một mối nguy lớn khi gắn:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Nếu ứng dụng tạo một object detached Order với collection không đầy đủ, rồi merge, trạng thái collection được sao chép có thể được diễn giải là loại bỏ những child không còn nằm trong collection. Với orphan removal, điều này **có thể làm xóa những child** mà client không hề yêu cầu xóa.

Không nên để client gửi một JSON payload thiếu `lines`, map thành entity với collection rỗng, rồi merge nguyên cả aggregate. Hãy load Order managed, kiểm tra quyền, thực hiện các phương thức nghiệp vụ `addLine()`, `changeQuantity()`, `removeLine()` tương ứng với **lệnh được xác định rõ**.

### 9.3. Các detached copy trùng identity

Một graph có thể chứa hai object Java detached khác nhau nhưng cùng persistent identity (ví dụ hai bản `Customer` có cùng ID được nhét vào hai nhánh). Hibernate có cơ chế xử lý trường hợp **multiple representations of same entity** khi merge, có thể phát hiện và báo lỗi hoặc có cấu hình xử lý tùy phiên bản.

Không nên tin rằng Hibernate sẽ luôn tự quyết định object nào đúng khi hai copy mang state khác nhau. Giữ một identity nhất quán trong domain graph hoặc cập nhật theo managed reference đã load.

## 10. @Version và optimistic locking trong merge

Nếu entity có:

~~~java
@Version
private long version;
~~~

Hibernate có thể kiểm tra version của detached source và entity/database state để phát hiện giao dịch cạnh tranh. Một tình huống:

1. Transaction A tải Customer version 3, rồi detach object A.
2. Transaction B tải cùng Customer version 3, thay email và commit, làm version tăng thành 4.
3. Transaction A gọi `merge(detachedA)` với version 3.
4. Hibernate có thể phát hiện version không khớp và phát sinh `OptimisticLockException` hoặc exception Hibernate tương ứng, tại merge, flush hoặc commit tùy trường hợp.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as Database
    A->>DB: Đọc Customer version=3
    B->>DB: Đọc Customer version=3
    B->>DB: UPDATE ... WHERE version=3
    DB-->>B: Thành công, version=4
    A->>DB: Merge/flush trạng thái version=3
    DB-->>A: Xung đột version
~~~

`@Version` giúp ngăn một số dạng **lost update**, nhưng không thay thế việc kiểm tra quyền, validation, và ý định người dùng. Khi gặp optimistic lock conflict, ứng dụng nên rollback transaction, cung cấp thông tin xung đột và quyết định retry/merge dữ liệu theo nghiệp vụ; không tự động bỏ version hoặc ghi đè dữ liệu mới.

### 10.1. Merge không bảo đảm “last write wins” hay “có xung đột thì tự giải quyết”

Không có `@Version`, việc merge dữ liệu cũ lên managed instance có thể ghi đè thay đổi của người khác khi commit. Có `@Version`, Hibernate có cơ chế phát hiện xung đột, nhưng **không biết field nào quan trọng hơn** hoặc phiên bản nào “đúng” theo nhu cầu business.

### 10.2. Xung đột có thể phát hiện muộn

Một lỗi có thể chỉ xuất hiện khi `flush()` hoặc transaction commit, không nhất thiết ngay tại `merge()`. Vì thế:

~~~java
Customer managed = em.merge(detached);
// Chưa thấy lỗi không có nghĩa transaction sẽ commit thành công.
~~~

Ứng dụng phải xử lý exception và transaction boundary đúng cách. Trong Spring, exception JPA thường được dịch thành loại exception dữ liệu/optimistic locking phù hợp tại tầng repository hoặc transaction manager.

## 11. Trong Spring Data JPA: repository.save() có thể gọi merge

Spring Data JPA cung cấp:

~~~java
Customer saved = customerRepository.save(customer);
~~~

Nhiều người gọi `save()` rồi tiếp tục thay đổi `customer` vì nghĩ repository đã “gắn lại” object. Đây có thể là cùng một lỗi như khi bỏ qua kết quả `EntityManager.merge()`.

Về ý tưởng, Spring Data JPA thường quyết định:

- Nếu entity được coi là **new**, dùng `EntityManager.persist()`.
- Nếu entity được coi là **existing**, dùng `EntityManager.merge()`.

Cách xác định “new” phụ thuộc mapping ID, version, việc implement `Persistable` và cấu hình/version của Spring Data. **Không được suy luận rằng `save()` luôn là INSERT hoặc luôn UPDATE chỉ từ tên phương thức**.

### 11.1. Vì sao dùng giá trị trả về của save()?

~~~java
Customer saved = customerRepository.save(customer);
~~~

Nếu repository gọi merge, `saved` là managed instance được trả về trong context liên quan; `customer` có thể vẫn detached. Vì vậy, khi cần dùng giá trị đã được cập nhật hoặc ID generated, nên sử dụng `saved` thay vì mặc định coi hai biến là cùng object.

Tuy nhiên, trong Spring, transaction/persistence context có thể đã kết thúc ngay sau một repository call nếu không có transaction service bao ngoài. Khi đó object `saved` cũng có thể trở thành detached tại code gọi. **Giữ reference trả về không kéo dài thời gian managed của nó.**

### 11.2. Mẫu service an toàn: load và cập nhật có chọn lọc

Thay vì:

~~~java
@Transactional
public Customer updateFromRequest(Customer payload) {
    return customerRepository.save(payload);
}
~~~

hãy cân nhắc DTO cho phép thay đúng field được cấp quyền:

~~~java
public record UpdateCustomerRequest(
    String name,
    String email
) {}
~~~

~~~java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;

    public CustomerService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Transactional
    public void updateCustomer(Long customerId,
                               UpdateCustomerRequest request) {
        Customer customer = customerRepository.findById(customerId)
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy khách hàng"));

        customer.rename(request.name());
        customer.changeEmail(request.email());

        // customer đang managed; dirty checking sẽ xử lý thay đổi.
    }
}
~~~

Cách này phân biệt rõ **HTTP request DTO** và **persistent entity**, dễ kiểm tra validation, quyền sửa field và hành vi transaction. Không nhất thiết gọi `save()` trên entity đã managed trong cùng transaction để dirty checking hoạt động.

## 12. merge() và trạng thái detached do API/client tạo

Một nhầm lẫn điển hình:

~~~java
// Controller nhận JSON:
Customer customerFromJson = objectMapper.readValue(
    body,
    Customer.class
);

// Sau đó service gọi:
em.merge(customerFromJson);
~~~

Object dựng từ JSON **không nhất thiết** là một detached entity hợp lệ theo nghĩa đã từng được Hibernate quản lý. Nó có thể chỉ là object mới mang ID từ client, thiếu version, thiếu field và có collection rỗng.

Rủi ro:

- Client tự gán ID để sửa hàng không được phép.
- Field thiếu bị coi là `null` và ghi đè dữ liệu.
- Quan hệ tới entity khác bị thay đổi ngoài ý định.
- Cascade MERGE đi qua object graph do client kiểm soát.
- Thiếu version khiến conflict detection yếu đi.
- Một entity có field generated hoặc invariant nội bộ bị ghi sai.

Do đó không nên coi “JSON có id” đồng nghĩa với “entity detached an toàn để merge”. Dùng request DTO, service validation, authorization, và áp dụng thay đổi lên managed entity thường là hướng dễ bảo vệ hơn.

### 12.1. Ví dụ PUT và PATCH

Với `PUT`, API có thể chủ đích thay toàn bộ representation do client quản lý. Nhưng điều đó **không đồng nghĩa** representation chứa tất cả field persistent của entity. Server vẫn có những field riêng như createdAt, internalStatus, ownerId, version, giá trị audit.

Với `PATCH`, chỉ một tập trường được gửi. Gọi `merge()` trên object chỉ có vài trường dễ làm mất dữ liệu những field không được gửi. Đối với PATCH, gần như luôn nên load managed entity và cập nhật rõ các field được sửa.

## 13. Luồng transaction hoàn chỉnh với detached entity

Giả sử request 1 đọc customer, trả dữ liệu ra bên ngoài, request 2 gửi thay đổi. Mô hình vòng đời:

~~~text
Transaction 1:
  em.find(Customer.class, 42)
      ↓
  Customer managed
      ↓ transaction/context kết thúc
  Customer detached / DTO gửi client

Thời gian giữa hai request:
  dữ liệu DB có thể đã thay đổi bởi người khác

Transaction 2:
  nhận cập nhật từ client
      ↓
  Cách A: em.merge(detached)
      ↓
  nhận managed result, xử lý optimistic lock và commit

  Cách B: em.find(id) → kiểm tra quyền/version
      ↓
  áp dụng field được phép sửa lên managed entity
      ↓
  commit (dirty checking)
~~~

Cách A phù hợp khi có một **detached entity graph đáng tin cậy** mà ứng dụng kiểm soát đầy đủ và muốn đồng bộ lại. Cách B phù hợp hơn khi nhận input từ client hoặc chỉ sửa một phần entity.

### 13.1. Không sử dụng EntityManager ngoài scope

Một object managed chỉ có nghĩa trong persistence context đang mở. Đừng giữ `EntityManager` hoặc managed entity làm biến global để tái dùng qua thread/request. Trong Spring, `@PersistenceContext` thường inject proxy gắn EntityManager với transaction/context thích hợp.

`EntityManager` tự nó không thread-safe; không được chia sẻ một instance tự tạo đồng thời giữa nhiều thread.

### 13.2. Flush và commit

Một quy trình có thể có:

~~~java
@Transactional
public Long mergeCustomer(Customer detached) {
    Customer managed = entityManager.merge(detached);
    entityManager.flush();
    return managed.getId();
}
~~~

`flush()` có thể phát hiện lỗi SQL/constraint/optimistic locking sớm hơn trong transaction, nhưng **không commit**. Nếu transaction bị rollback sau đó, dữ liệu không được xác nhận. Trong phần lớn service, không cần flush thủ công chỉ để “lưu được” nếu transaction commit sẽ flush theo cơ chế phù hợp.

## 14. Khi entity đã bị xóa ở database

Giả sử một detached object có ID 42, nhưng hàng ID 42 đã bị transaction khác xóa. Gọi:

~~~java
Customer managed = em.merge(detached);
~~~

không có một kết quả duy nhất bất biến cho mọi cách mapping/phiên bản:

- Provider có thể phát hiện entity detached không còn tồn tại và báo optimistic locking/stale state.
- Với các mapping không đủ thông tin phân biệt new và detached, provider có thể có cách xử lý khác, tùy phiên bản và chiến lược ID.
- Các bản Hibernate mới đã siết chặt một số trường hợp nhận diện detached entity để tránh âm thầm INSERT lại hàng đã xóa.

Vì thế **không sử dụng merge như “upsert mặc định”**. Nếu nghiệp vụ cần tạo hoặc cập nhật tùy tồn tại, hãy thiết kế quy trình upsert rõ ràng với transaction, unique constraint, version và các ngoại lệ race condition.

## 15. Vì sao merge có thể tạo nhiều SQL hơn mong đợi?

Với một detached entity, Hibernate thường cần tìm managed instance tương ứng hoặc lấy snapshot để biết state database. Điều đó có thể kéo theo `SELECT` trước khi phát `UPDATE`. Khi cascade vào graph lớn, có thể có thêm nhiều query.

Ví dụ graph `Order` với hàng trăm `OrderLine`, `Product`, `Address` và các relationship khác:

~~~java
Order managed = em.merge(detachedOrder);
~~~

Câu lệnh tưởng chừng một dòng nhưng có thể:

- Tải Order hiện có.
- Đi qua các association được cascade MERGE.
- Tải/tạo managed counterparts của child entity.
- So sánh trạng thái và xử lý collection snapshots.
- INSERT/UPDATE/DELETE các hàng sau flush.
- Kiểm tra version và constraint.

Đây là lý do không nên gọi merge lên toàn bộ object graph một cách tùy tiện trong mỗi API cập nhật đơn giản. Một update command có mục đích rõ ràng thường dễ dự đoán SQL hơn.

### 15.1. Merge không phải “batch update miễn phí”

Nếu cần cập nhật hàng chục nghìn record, lặp qua detached entity rồi `merge()` có thể tiêu tốn memory, SELECT và dirty checking. Cân nhắc batching có kiểm soát hoặc JPQL/native bulk UPDATE khi phù hợp, đồng thời xử lý ranh giới persistence context, version và callback rõ ràng.

### 15.2. Bulk update không đồng bộ managed object

JPQL bulk UPDATE/DELETE có semantics khác merge:

~~~java
em.createQuery("""
    UPDATE Customer c
    SET c.name = :name
    WHERE c.id = :id
    """)
    .setParameter("name", "New name")
    .setParameter("id", id)
    .executeUpdate();
~~~

Bulk DML thao tác trực tiếp lên database và không đồng bộ mọi managed entity như khi sửa đối tượng. Khi kết hợp các cách ghi trong một transaction, có thể cần `flush()`, `clear()` hoặc `refresh()` phù hợp.

## 16. equals(), hashCode() và hai object cùng ID

Sau merge, nguồn detached và kết quả managed có thể là hai object khác nhau:

~~~java
Customer detached = ...;
Customer managed = em.merge(detached);

System.out.println(detached == managed); // false nếu detached thật
~~~

Tuy nhiên, chúng có thể đại diện cho **cùng một hàng database**. Nếu ứng dụng định nghĩa `equals()` theo persistent identity thì `detached.equals(managed)` có thể là `true`, dù `==` là `false`.

Những lưu ý:

- Không dùng `==` để thay thế mọi so sánh identity nghiệp vụ trong object graph có detached entities.
- Không tùy ý dùng ID generated chưa có giá trị trong `hashCode()` của một entity được đưa vào `HashSet` trước khi persist, rồi thay ID sau persist; điều này có thể phá hợp đồng hash collection.
- Thiết kế equals/hashCode với proxy Hibernate, inheritance và ID generation cần nhất quán.
- Dù hai object được coi là equal, **chỉ đối tượng managed mới được context theo dõi**.

Quy tắc “giữ managed return” không phải vì ID khác, mà vì **trạng thái quản lý khác**.

## 17. Các sai lầm thường gặp

| Cách hiểu sai | Vấn đề thực tế | Cách dùng đúng |
| --- | --- | --- |
| “`merge(detached)` biến chính detached thành managed.” | Detached source vẫn không được context theo dõi | Dùng object do `merge()` trả về |
| “Không cần lưu biến trả về.” | Sửa source sau merge có thể mất cập nhật | Gán `managed = em.merge(source)` |
| “`merge()` luôn chạy UPDATE ngay.” | SQL có thể đến lúc flush/commit hoặc không có UPDATE | Hiểu dirty checking và transaction |
| “`merge()` chỉ cập nhật các field client gửi.” | Persistent null/stale values có thể ghi đè dữ liệu | Dùng DTO + load managed + cập nhật có chọn lọc |
| “Một entity có ID thì chắc chắn đang managed.” | Detached entity vẫn giữ ID | Kiểm tra scope và `em.contains()` |
| “`merge()` là upsert an toàn.” | New/detached/stale identity có semantics riêng | Thiết kế upsert tường minh |
| “Cascade MERGE biến toàn bộ source graph thành managed.” | Các managed copies được tạo/tìm, source graph vẫn detached | Dùng graph kết quả, giới hạn cascade |
| “Nếu collection thiếu child, ORM sẽ bỏ qua.” | Orphan removal có thể xóa child do bản sao thiếu | Không merge graph không đầy đủ |
| “`@Version` tự hòa giải conflict.” | Version chỉ phát hiện, không tự quyết định ghi đè nào đúng | Xử lý conflict theo nghiệp vụ |
| “`save(entity)` trong Spring luôn quản lý chính entity đó.” | Nhánh merge có thể trả object managed khác | Dùng return và hiểu transaction |
| “Sau khi gọi merge, object kết quả managed vĩnh viễn.” | Khi context kết thúc nó cũng detached | Không giữ entity managed xuyên request |
| “Detached copy có ID bằng managed thì là cùng object.” | Persistent identity khác với Java reference identity | Phân biệt `==`, `equals()` và trạng thái managed |

## 18. Quy trình ra quyết định: khi nào nên dùng merge?

**Trường hợp A — Entity mới hoàn toàn**

Bạn tạo mới dữ liệu bên trong transaction và không có yêu cầu đồng bộ detached graph:

~~~java
Customer customer = new Customer("Chi", "chi@example.test");
em.persist(customer);
~~~

Ưu tiên `persist()`: rõ mục đích, chính object được quản lý.

**Trường hợp B — Đã load entity managed để sửa**

~~~java
Customer customer = em.find(Customer.class, id);
customer.rename("Chi Nguyen");
~~~

Không cần `merge()`; để dirty checking xử lý.

**Trường hợp C — Có detached entity đáng tin cậy**

~~~java
Customer managed = em.merge(detachedCustomer);
managed.changeEmail("updated@example.test");
~~~

Dùng merge khi cần sao chép state và hiểu rõ mọi field/cascade có thể bị ảnh hưởng. Luôn dùng managed result.

**Trường hợp D — API nhận request cập nhật một phần**

~~~java
Customer managed = em.find(Customer.class, request.id());
managed.rename(request.name());
~~~

Ưu tiên DTO và update có chọn lọc; không tạo entity mới từ JSON rồi merge nguyên cả object.

**Trường hợp E — Cập nhật hàng loạt**

Đánh giá batch hoặc bulk DML có chủ đích; không mặc định merge hàng nghìn entity là phương pháp tối ưu.

## 19. Bài tập thực hành

### Bài 1 — Đối tượng nào được theo dõi?

Cho đoạn code trong transaction:

~~~java
Customer a = em.find(Customer.class, id);
em.detach(a);
a.rename("A");

Customer b = em.merge(a);
a.rename("B");
b.changeEmail("b@example.test");

em.flush();
~~~

Hãy xác định: `a` và `b` có cùng ID không, có cùng Java reference không, đối tượng nào managed và vì sao việc đổi tên thành `"B"` có thể không được lưu.

### Bài 2 — Khi context đã có managed instance

~~~java
Customer managed = em.find(Customer.class, id);
managed.changeEmail("fresh@example.test");

Customer oldDetached = ...; // Cùng ID, email cũ.
Customer merged = em.merge(oldDetached);
~~~

Hãy giải thích vì sao dữ liệu mới vừa sửa trên `managed` có thể bị ghi đè và cách tránh bằng request DTO, version và giới hạn field được phép thay đổi.

### Bài 3 — Persist hay merge?

Phân loại cách xử lý hợp lý:

1. Tạo một Customer mới với IDENTITY.
2. Load Customer qua `find()` và sửa tên.
3. Nhận một detached Customer từ một persistence context cũ, cần đồng bộ toàn bộ trạng thái đã được xác thực.
4. Nhận JSON PATCH chỉ chứa field `email`.
5. Nhận một object có ID do client tự gán nhưng không rõ hàng đã tồn tại.

### Bài 4 — Collection và orphanRemoval

`Order` có `@OneToMany(cascade = ALL, orphanRemoval = true)`. Client gửi lại payload có collection `lines` rỗng do form chỉ sửa tên đơn hàng. Tại sao merge thẳng payload thành Order có thể nguy hiểm? Hãy mô tả thao tác cập nhật an toàn hơn.

### Bài 5 — Optimistic locking

Request A giữ detached Customer version 5. Request B đã cập nhật hàng và commit version 6. Request A merge version 5. Hibernate có thể làm gì? Lỗi có nhất thiết xuất hiện ngay tại dòng merge không?

### Bài 6 — Spring Data JPA

Với:

~~~java
Customer saved = repository.save(customer);
customer.rename("Tên sau save");
~~~

Hãy giải thích vì sao việc đổi tên trên `customer` không chắc được ghi sau `save()`, và tại sao ngay cả `saved` cũng có thể detached khi repository call kết thúc.

### Gợi ý

- **Bài 1:** `a` và `b` cùng persistent identity nhưng khác Java object; `b` managed, `a` detached; thay đổi `"B"` trên `a` sau merge không được sao chép tự động.
- **Bài 2:** Merge sao chép persistent state từ nguồn cũ lên managed target; nên load entity và cập nhật field xác định, dùng `@Version` để phát hiện conflict.
- **Bài 3:** (1) `persist`; (2) chỉ sửa managed; (3) có thể merge và dùng kết quả; (4) DTO + tìm managed + áp dụng email; (5) không đoán new/detached, xác định trạng thái và nghiệp vụ rõ.
- **Bài 4:** Graph không đầy đủ có thể làm orphanRemoval xóa child; chỉ cập nhật thuộc tính được yêu cầu trên managed root.
- **Bài 5:** Version mismatch có thể gây optimistic locking exception tại merge, flush hoặc commit.
- **Bài 6:** `save()` có thể gọi merge và trả managed copy khác; transaction/context kết thúc thì object trả về cũng có thể detached.

---

**Ghi nhớ:** `EntityManager.merge(source)` **không gắn lại chính `source`** khi nó là detached. Hibernate sao chép persistent state vào một managed entity tương ứng và **trả về managed instance đó**. Muốn tiếp tục sửa dữ liệu trong cùng persistence context, hãy sử dụng object được trả về; muốn cập nhật một phần từ request, thường nên tải entity managed và áp dụng thay đổi có chủ đích. Luôn xem xét transaction, cascade, optimistic locking và trạng thái detached trước khi sử dụng merge.
