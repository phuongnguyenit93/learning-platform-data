# Các trạng thái transient, managed, detached và removed

## 1. Vì sao cần hiểu vòng đời thực thể?

Trong ứng dụng Java sử dụng Jakarta Persistence (JPA) với Hibernate ORM, một đối tượng Java được khai báo `@Entity` không tự động được ghi xuống cơ sở dữ liệu. Việc Hibernate có theo dõi đối tượng đó, phát sinh SQL cho nó, hay bỏ qua các thay đổi của nó phụ thuộc vào **trạng thái vòng đời (entity lifecycle state)** và **persistence context** mà đối tượng có thể đang thuộc về.

Ví dụ cùng một class:

~~~java
@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "name", nullable = false, length = 150)
    private String name;

    @Column(name = "price", nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    @Version
    private long version;

    protected Product() {}

    public Product(String sku, String name, BigDecimal price) {
        this.sku = sku;
        this.name = name;
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }

    public void rename(String name) {
        this.name = name;
    }

    public void reprice(BigDecimal price) {
        this.price = price;
    }
}
~~~

Các import của ví dụ gồm những annotation tương ứng từ `jakarta.persistence` (`Entity`, `Table`, `Id`, `GeneratedValue`, `GenerationType`, `Column`, `Version`) và `java.math.BigDecimal`. Class này chỉ là ví dụ xuyên suốt; bảng `products` thực tế phải có schema phù hợp.

Ta có thể tạo một `Product` bằng `new`, truy vấn nó từ database, đưa ra khỏi persistence context, rồi yêu cầu xóa. Bốn thời điểm đó có hành vi ORM khác nhau dù cùng một class.

### Bốn trạng thái cốt lõi

| Trạng thái | Tên thường dùng | Có được persistence context hiện tại quản lý? | Ý nghĩa dữ liệu |
|---|---|---|---|
| **Transient** | New, new/transient | Không | Đối tượng mới chưa được đặt dưới quản lý persistence; chưa có yêu cầu lưu từ ORM |
| **Managed** | Persistent | Có | ORM theo dõi trạng thái và có thể đồng bộ thay đổi khi flush |
| **Detached** | Detached | Không | Từng có định danh/persistence identity nhưng hiện không được context này quản lý |
| **Removed** | Removed | Đã được đánh dấu xóa trong context, không còn là entity managed bình thường cho các thao tác thông thường | ORM đã nhận yêu cầu xóa; SQL DELETE có thể chưa thực thi |

> **Điểm mấu chốt:** trạng thái của entity và trạng thái của **hàng trong database** không phải cùng một thứ. Gọi `persist()`, `remove()` hay sửa một managed entity không bảo đảm SQL đã được chạy ngay lập tức. `flush` và transaction quyết định khi nào công việc được đồng bộ xuống database; `commit` mới quyết định khả năng tồn tại lâu dài của thay đổi trong một transaction thành công.

## 2. Persistence context: nền tảng của các trạng thái

**Persistence context** là phạm vi Hibernate/JPA quản lý tập entity instances, thường được truy cập qua `EntityManager`. Trong Hibernate native API, `Session` là khái niệm tương ứng. Persistence context thường được gọi là **first-level cache**.

Có thể hình dung:

~~~text
Ứng dụng (Java objects)
          |
          v
   EntityManager / Session
   +-----------------------------+
   | Persistence Context         |
   |                             |
   | Identity map                |
   | Entity snapshots            |
   | Managed entity instances    |
   | Pending inserts/updates/... |
   +-----------------------------+
          |
          | flush SQL trong transaction
          v
    JDBC -> Relational Database
~~~

Đây là sơ đồ khái niệm; chi tiết snapshot và hàng đợi thao tác phụ thuộc Hibernate. Điều quan trọng là **EntityManager không chỉ là một công cụ gọi SQL**. Nó duy trì những đối tượng được quản lý và biết một đối tượng đã thay đổi so với trạng thái ban đầu hay chưa.

### 2.1. Tính duy nhất của entity instance trong một context

Trong một persistence context, với cùng một identity của entity, provider duy trì **một managed instance đại diện**. Ví dụ:

~~~java
Product first = em.find(Product.class, productId);
Product second = em.find(Product.class, productId);

System.out.println(first == second); // Thông thường: true trong cùng context
~~~

Nếu entity đã có trong context, Hibernate có thể trả lại instance hiện có mà không cần SELECT lại. Khi dùng hai context khác nhau, hai instance Java có thể cùng biểu diễn một hàng DB nhưng không phải cùng object reference.

Điều này giải thích vì sao **detached object không thể được coi là cùng instance đang managed trong một EntityManager mới**, dù cả hai có cùng `id`.

### 2.2. Không nhầm first-level cache với second-level cache

First-level cache thuộc về persistence context và gắn liền với quản lý vòng đời entity. Second-level cache là cơ chế tùy chọn của Hibernate có thể chia sẻ dữ liệu giữa các session. Một entity detached không trở thành managed chỉ vì dữ liệu của nó có trong second-level cache. Để dirty checking hoạt động, entity instance vẫn phải thuộc một persistence context phù hợp.

### 2.3. Persistence context và transaction không hoàn toàn đồng nhất

Trong Java SE, ứng dụng thường tạo `EntityManager` và tự điều khiển resource-local transaction. Trong môi trường Spring/Jakarta EE, `EntityManager` có thể được quản lý theo transaction. Một `EntityManager` được giữ mở lâu không phải đồng nghĩa cùng một transaction; ngược lại, một transaction có thể bao gồm nhiều thao tác trên entity trong một context.

Có các kiểu context có phạm vi khác nhau (chẳng hạn transaction-scoped và extended persistence context trong môi trường hỗ trợ). Bài học dùng mô hình phổ biến: **một use case thao tác dữ liệu trong một transaction và một persistence context được quản lý rõ ràng**.

EntityManager không thread-safe. Không chia sẻ một EntityManager giữa các request/thread độc lập để tránh chi phí tạo context.

## 3. Sơ đồ chuyển trạng thái

~~~text
                         new Product(...)
                                |
                                v
                        TRANSIENT (new)
                                |
                          persist() hoặc
                          cascade PERSIST
                                |
                                v
                      MANAGED (persistent)
                        /       |         \
                       /        |          \
              remove()       detach()     clear()/close()
                  |          (hoặc context kết thúc)
                  v             |              |
               REMOVED          +--------------+
                  |                            |
          flush / commit                       v
          -> DELETE DB                      DETACHED
                  |                            |
                  |                         merge()
                  |                            |
                  |                            v
                  |                    MANAGED COPY
                  |
             transaction commit
             entity không còn
             được quản lý như trước

   find()/query/getReference() trên entity tồn tại
                -> trả về managed instance/reference

   rollback -> transaction không commit các thay đổi;
               phải xử lý/discard context theo mô hình sử dụng
~~~

Sơ đồ tập trung vào luồng điển hình, không phải toàn bộ các trường hợp được đặc tả. Chẳng hạn, `merge()` với transient object cũng có thể tạo một managed instance mới, còn `persist()` với một removed entity có quy tắc riêng. Hibernate có các hành vi mở rộng native như `Session.update()` ở những API/version cụ thể, nhưng nên học hợp đồng Jakarta Persistence trước.

### Bảng các lời gọi quan trọng

| Thao tác | Đối tượng đầu vào thường gặp | Kết quả/ý nghĩa chính |
|---|---|---|
| `new Product(...)` | Không có | Tạo transient object |
| `em.persist(entity)` | Transient | Đưa chính instance đó vào trạng thái managed; lên lịch insert |
| `em.find(Product.class, id)` | Khóa ID | Trả managed entity hoặc null nếu không tìm thấy |
| `em.getReference(Product.class, id)` | Khóa ID | Trả managed reference, có thể chưa tải đủ dữ liệu |
| `em.merge(entity)` | Detached (hoặc transient) | Trả **managed instance chứa trạng thái được sao chép**; đầu vào không tự thành managed |
| `em.remove(entity)` | Managed | Chuyển entity sang removed, lên lịch xóa |
| `em.detach(entity)` | Managed | Gỡ instance khỏi context, làm nó detached |
| `em.clear()` | Context | Gỡ mọi entity khỏi context, hủy các thay đổi chưa đồng bộ theo cơ chế context |
| `em.close()` | EntityManager application-managed | Đóng context; các entity đã từng managed trở thành detached |
| `em.refresh(entity)` | Managed | Nạp lại trạng thái từ DB, ghi đè thay đổi trong bộ nhớ của instance |
| `em.flush()` | Context/transaction hợp lệ | Đồng bộ các thay đổi pending xuống DB nhưng **chưa commit** |
| `em.contains(entity)` | Object | Kiểm tra entity có đang managed trong context hiện tại theo hợp đồng JPA không |

Không thể dùng `em.contains()` để kết luận “đã có hàng trong database hay chưa”; một transient object chưa có DB, một detached object vẫn có thể có DB, và một entity removed có thể vẫn còn hàng chưa bị DELETE trước flush.

## 4. Transient: đối tượng Java mới chưa được ORM quản lý

### 4.1. Tạo transient object

~~~java
Product product = new Product(
    "JAVA-001",
    "Java Persistence Guide",
    new BigDecimal("299.00")
);
~~~

Đây là một đối tượng Java mới. Hibernate **chưa** theo dõi thay đổi của nó chỉ vì class có annotation `@Entity`.

~~~java
product.rename("Hibernate Basics");
// Không có INSERT/UPDATE tự phát sinh chỉ do gọi setter.
~~~

Trong trường hợp `@GeneratedValue`, ID thường chưa được cấp cho object vừa `new`; nhưng **không dùng `id == null` làm phép kiểm tra vòng đời tuyệt đối**. Với ID tự gán, transient entity có thể có ID khác null. Ngược lại, một detached instance vẫn có ID, còn managed entity mới có thể được cấp ID trước hoặc sau SQL INSERT tùy generator.

### 4.2. Chuyển transient sang managed bằng persist()

~~~java
em.getTransaction().begin();

Product p = new Product(
    "JAVA-001",
    "Java Persistence Guide",
    new BigDecimal("299.00")
);

em.persist(p);      // p trở thành managed.
p.reprice(new BigDecimal("319.00"));

em.getTransaction().commit();
~~~

`persist(p)` không trả về entity. Chính instance `p` được đặt dưới quản lý của context. Nếu còn trong transaction, thay đổi sau đó có thể được Hibernate theo dõi và ghi dữ liệu cuối cùng phù hợp.

**Không nên đồng nhất persist với INSERT ngay tại dòng gọi.** Hibernate có thể trì hoãn SQL đến flush/commit, nhưng với một số chiến lược ID như `IDENTITY`, provider có thể phải thực hiện INSERT sớm để lấy khóa do DB tạo. Vì thế thời điểm ID xuất hiện và SQL chạy phụ thuộc ID generator, flush mode, provider và ngữ cảnh transaction.

### 4.3. Persist không phải phép upsert

Đoạn sau không phải cách cập nhật một entity đã tồn tại:

~~~java
Product old = ...; // Detached entity đã từng được lưu
em.persist(old);   // Không phải thao tác update chuẩn JPA.
~~~

Hợp đồng JPA dành `persist` chủ yếu cho entity mới. Nếu truyền detached entity, `EntityExistsException` có thể được ném khi gọi hoặc một `PersistenceException` khác có thể xuất hiện khi flush/commit, tùy thời điểm phát hiện.

Nếu muốn thay đổi dữ liệu của entity đã tồn tại, cần hiểu managed vs detached và chọn cách tìm managed entity rồi sửa, hoặc `merge` phù hợp.

### 4.4. Cascading PERSIST

Transient entity có thể được đưa vào managed thông qua cascade từ một entity khác:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi persist `Order`, các `OrderLine` liên quan có thể được persist nhờ cascade nếu object graph và owning references được thiết lập đúng. Cascade không thay đổi ý nghĩa cơ bản của `persist` và không tự sửa một quan hệ hai chiều đang thiếu owning side.

Không tự động dùng `CascadeType.ALL` cho mọi association: cascade remove sang entity được dùng chung như `Customer` hay `Category` có thể gây mất dữ liệu ngoài ý định.

## 5. Managed: Hibernate theo dõi đối tượng trong context

### 5.1. Trở thành managed bằng find()

~~~java
em.getTransaction().begin();

Product p = em.find(Product.class, productId);
if (p == null) {
    throw new IllegalArgumentException("Product not found");
}

p.rename("Updated product name");
p.reprice(new BigDecimal("349.00"));

em.getTransaction().commit();
~~~

Ở đây không gọi `em.update(p)`. Hibernate theo dõi trạng thái của managed entity, phát hiện thay đổi, và có thể tạo SQL `UPDATE` khi flush.

Đây là **dirty checking**.

### 5.2. Dirty checking và flush

~~~text
find() hoặc persist()
      |
      v
Managed entity trong context
      |
      +-- p.rename(...)
      +-- p.reprice(...)
      |
      v
flush()
      |
      +-- kiểm tra thay đổi
      +-- phát sinh INSERT/UPDATE/DELETE cần thiết
      v
Database transaction (chưa chắc commit)
~~~

Hibernate có thể dùng snapshot hoặc cơ chế enhancement tương ứng để phát hiện thay đổi. Không cần gọi một method save riêng sau mỗi setter trên managed entity; điều kiện là entity còn managed và transaction/flush cho phép ghi.

Ví dụ SQL minh họa:

~~~sql
UPDATE products
SET name = ?, price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

SQL chính xác phụ thuộc mapping, Hibernate version, cấu hình `@DynamicUpdate`, optimistic locking và dialect. Với `@Version`, Hibernate thường thêm điều kiện version để phát hiện concurrent modification.

### 5.3. Managed không có nghĩa sẽ ghi mọi thay đổi trong mọi hoàn cảnh

Còn nhiều điều kiện:

- Entity có thể được đọc trong transaction read-only hoặc persistence context được cấu hình read-only theo Hibernate; hành vi dirty checking/flush có thể bị hạn chế.
- Thuộc tính đánh dấu `@Transient` không phải persistent state.
- `@Column(updatable = false)` không tham gia UPDATE của mapping đó.
- Thay đổi chưa flush không nhất thiết xuất hiện tại DB.
- Nếu transaction rollback, thay đổi không được commit.
- Nếu entity bị detach trước flush, thay đổi sau detach không còn được theo dõi bởi context cũ.
- Gọi `refresh` có thể ghi đè những thay đổi chưa đồng bộ.

Do đó, “managed tự lưu” là cách nói rút gọn: đúng hơn là **provider có thể phát hiện và đồng bộ thay đổi của entity đang được context quản lý khi điều kiện flush/transaction phù hợp**.

### 5.4. Managed reference và lazy loading

~~~java
Product reference = em.getReference(Product.class, productId);
~~~

`getReference` có thể trả proxy/reference chưa SELECT đầy đủ. Nó tham gia quản lý của persistence context và có thể được dùng để đặt foreign key theo ID trong một số trường hợp. Nhưng `getReference` **không xác thực ngay rằng hàng chắc chắn tồn tại**. Lỗi như `EntityNotFoundException` hoặc vi phạm FK có thể xuất hiện khi truy cập hoặc flush.

Khi một proxy lazy chưa khởi tạo bị detach và mã cố đọc thuộc tính cần tải từ DB, Hibernate có thể ném `LazyInitializationException`. Đây là hệ quả của context/lazy state, không phải vì đối tượng Java đột nhiên mất mọi field đã được đọc.
## 6. Detached: entity đã rời persistence context

### 6.1. Detached là gì?

Một detached entity là object từng đại diện cho một entity được quản lý, nhưng hiện tại **không còn được persistence context đang sử dụng theo dõi**. Các giá trị của nó vẫn tồn tại trong bộ nhớ Java. Nó thường giữ `id` và các thuộc tính đã được tải, nhưng những thay đổi tiếp theo không tự phát sinh UPDATE trong context cũ.

Các nguyên nhân điển hình:

- Gọi `em.detach(entity)`.
- Gọi `em.clear()` khiến tất cả managed entities trong context rời khỏi context.
- Đóng `EntityManager` do ứng dụng quản lý bằng `em.close()`.
- Kết thúc phạm vi persistence context do framework/container quản lý; object còn được code giữ tham chiếu nhưng không còn context.
- Dữ liệu được đưa qua các tầng hoặc request khác nhau: entity từ request trước vẫn còn trong Java, nhưng context tạo nó không còn.

Một entity **không tự detached chỉ vì ta rời khỏi một method Java**; trạng thái phụ thuộc persistence context còn quản lý nó hay không. Một extended persistence context có thể tồn tại ngoài một transaction, vì vậy không phải lúc nào kết thúc transaction cũng đồng nghĩa detach. Mô hình phổ biến trong các ứng dụng transaction-scoped là entity không còn được quản lý khi context kết thúc.

### 6.2. Detached sau khi đóng EntityManager

~~~java
Product detached;

EntityManager em = emf.createEntityManager();
try {
    em.getTransaction().begin();

    Product managed = em.find(Product.class, productId);
    if (managed == null) {
        throw new IllegalArgumentException("Missing product");
    }

    detached = managed;
    em.getTransaction().commit();
} finally {
    em.close();
}

detached.rename("Renamed outside context");
// Đây chỉ là thay đổi object Java.
// Không có UPDATE tự động từ EntityManager đã đóng.
~~~

Đối tượng `detached` vẫn có thể được sử dụng để hiển thị những thuộc tính đã tải. Nhưng việc đọc lazy association chưa khởi tạo có thể gặp lỗi vì không còn session để tải dữ liệu.

### 6.3. detach() một entity cụ thể

~~~java
em.getTransaction().begin();

Product product = em.find(Product.class, productId);
em.detach(product);

product.reprice(new BigDecimal("399.00"));

em.getTransaction().commit();
// Việc sửa trên product sau detach không được context này dirty-check.
~~~

Gọi `detach` loại object khỏi quản lý; bản thân nó **không tạo một yêu cầu xóa hàng DB**. Thao tác `detach` không có nghĩa entity “được unload khỏi RAM”; object Java vẫn được giữ bởi các tham chiếu trong ứng dụng.

Nếu entity có association cấu hình `cascade = CascadeType.DETACH` hoặc `ALL`, thao tác detach có thể lan theo các quan hệ được cấu hình. Cần cân nhắc cascade để tránh bất ngờ khi một graph lớn bị detach.

### 6.4. clear() tách tất cả entity, có thể làm mất thay đổi chưa flush

~~~java
em.getTransaction().begin();

Product p = em.find(Product.class, productId);
p.rename("Unflushed change");

em.clear(); // Clear persistence context.

em.getTransaction().commit();
~~~

Vì `clear()` gỡ tất cả managed objects và có thể bỏ những thay đổi chưa đồng bộ, tên mới trong ví dụ **không nên được kỳ vọng sẽ lưu**. Lưu ý những SQL đã được flush trước `clear` vẫn thuộc transaction và có thể được commit hoặc rollback tùy transaction; `clear` không phải lệnh SQL ROLLBACK.

Nếu ý định là lưu thay đổi rồi giảm bộ nhớ của context, thường phải `flush()` **trước** `clear()`:

~~~java
em.flush(); // Gửi SQL thay đổi pending.
em.clear(); // Tách entities và giải phóng quản lý.
~~~

Cặp lệnh này hay xuất hiện trong xử lý hàng loạt. Tuy nhiên, flush chưa commit; nếu sau đó transaction rollback, các SQL đã flush cũng bị rollback.

### 6.5. Detached không có nghĩa database luôn còn bản ghi

Giả sử service A đọc `Product(id=10)` rồi đóng context. Service B xóa sản phẩm trong một transaction khác. Object cũ ở service A vẫn tồn tại trong RAM với `id=10`, nhưng hàng DB có thể đã biến mất.

Vì vậy không thể suy luận “có ID + detached” là dữ liệu vẫn tồn tại. Khi cần xác nhận sự tồn tại hiện tại, dùng transaction và query phù hợp; khi cần ngăn ghi đè dữ liệu cũ, cân nhắc optimistic locking.

## 7. merge(): làm việc với đối tượng detached

### 7.1. Điều quan trọng nhất: merge trả về một managed instance khác

Đây là hiểu nhầm phổ biến khi làm việc với JPA:

~~~java
Product detached = ...; // Một entity đã rời context.

em.getTransaction().begin();

Product managed = em.merge(detached);

System.out.println(managed == detached); // Thông thường: false

em.getTransaction().commit();
~~~

`merge(detached)` **không biến chính reference `detached` thành managed**. Nó sao chép trạng thái persistence của đầu vào sang một managed instance tương ứng trong context và **trả về managed instance đó**.

Nếu context đã có entity cùng identity, provider dùng managed instance hiện có để hợp nhất trạng thái. Nếu chưa có, provider có thể cần tải entity từ DB hoặc tạo một managed instance thích hợp. Chi tiết SELECT/INSERT/UPDATE phụ thuộc trạng thái đầu vào, version, ID và provider.

Sơ đồ:

~~~text
      Detached Product (D)
      id = 42, price = 399
                |
                | em.merge(D): copy persistent state
                v
      Managed Product (M)
      id = 42, price = 399
                |
           flush/commit
                |
                v
           DB row id=42

      D vẫn DETACHED.
      M là instance được quản lý trong context hiện tại.
~~~

### 7.2. Sai khi tiếp tục sửa object detached sau merge

~~~java
em.getTransaction().begin();

Product managed = em.merge(detached);
detached.rename("New title after merge"); // Sửa object gốc detached.

em.getTransaction().commit();
~~~

Lệnh sửa ở `detached` sau khi merge **không tự đồng bộ** sang `managed`. Nếu muốn thay đổi được ghi, thao tác trên instance trả về:

~~~java
em.getTransaction().begin();

Product managed = em.merge(detached);
managed.rename("New title after merge");

em.getTransaction().commit();
~~~

Cũng cần nhớ không phải mọi thuộc tính Java đều được sao chép: chỉ trạng thái persistent theo mapping hợp lệ và cascade merge phù hợp. Các trường `@Transient` không được chuyển thành thuộc tính DB chỉ vì merge.

### 7.3. merge() không có nghĩa chỉ UPDATE

Với đối tượng transient chưa từng được lưu:

~~~java
Product p = new Product(
    "JAVA-NEW",
    "New product",
    new BigDecimal("129.00")
);

em.getTransaction().begin();

Product managed = em.merge(p); // Có thể tạo một managed copy mới.
em.getTransaction().commit();
~~~

Hợp đồng `merge` chấp nhận việc sao chép trạng thái của transient object để tạo managed instance mới, có thể dẫn đến INSERT. Nhưng nếu mục đích rõ ràng là tạo mới, `persist` thường trực tiếp và dễ hiểu hơn: nó không tạo thêm một managed copy riêng biệt của entity mới.

`merge()` không phải phép “upsert an toàn bất kể dữ liệu đầu vào”. Với entity đã có khóa/`@Version`, provider có thể xác định detached hay transient khác nhau, và có thể ném lỗi optimistic locking hoặc lỗi khi hàng không còn tồn tại. Không nên dựa vào merge để tự động hồi sinh một bản ghi đã bị xóa, hoặc tự tạo lại hàng với ID cũ mà không kiểm soát.

### 7.4. Một cách cập nhật khác: tải managed entity rồi chỉnh có chọn lọc

Trong nhiều service, lựa chọn dễ kiểm soát hơn là:

~~~java
@Transactional
public void changeProductPrice(long id, BigDecimal requestedPrice) {
    Product managed = em.find(Product.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Product not found");
    }

    managed.reprice(requestedPrice);
}
~~~

Mã này giả định transaction được framework quản lý. Chỉ một thuộc tính được phép sửa, nên service không vô tình sao chép các field cũ từ detached object vào một managed entity đang có dữ liệu mới hơn.

Nếu ứng dụng nhận dữ liệu từ HTTP, nên phân biệt **request DTO** với **entity**. Không tự nhận toàn bộ detached entity từ phía client rồi merge không kiểm soát, vì có thể dẫn đến sửa trường ngoài quyền hoặc ghi đè các giá trị mà request không định cập nhật.

### 7.5. Khi merge có nguy cơ ghi đè dữ liệu mới

Giả sử:

1. Request A đọc sản phẩm giá 100, trả entity detached.
2. Request B đổi giá trong DB thành 120 và commit.
3. Request A gửi lại object cũ chỉ với tên mới, nhưng giá trong detached object vẫn là 100.
4. Service gọi `merge(detached)`.

Nếu không có kiểm soát concurrency, việc copy state cũ có thể đưa giá 100 trở lại. `@Version` hỗ trợ phát hiện xung đột optimistic locking; khi version của detached entity cũ hơn version trong DB, provider có thể báo lỗi ở merge, flush hoặc commit.

Không nên xem `@Version` chỉ là một cột kỹ thuật. Nó giúp các giao dịch nhận ra dữ liệu đã thay đổi kể từ lần đọc trước. Nhưng nếu các hệ thống khác chỉnh DB trực tiếp mà không cập nhật version đúng quy tắc, việc bảo vệ cũng bị suy yếu.

### 7.6. Cascade MERGE theo graph

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.MERGE)
private List<OrderLine> lines;
~~~

Khi merge `Order`, hành động merge có thể lan đến `OrderLine` theo mapping. `CascadeType.MERGE` không đồng nghĩa `CascadeType.PERSIST`, và cascade trên một collection cũng không thay thế nghĩa vụ đồng bộ owning side của quan hệ hai chiều.

Với graph lớn, merge có thể chạm nhiều entity và phát sinh truy vấn/updates bất ngờ nếu payload detached chứa nhiều phần dữ liệu không được kiểm soát.

### 7.7. Các thao tác native Hibernate không hoàn toàn giống merge của JPA

Hibernate có API như `Session` và một số thao tác reattachment trong các phiên bản cụ thể. Những ví dụ cũ có thể dùng `Session.update(detached)` hoặc `saveOrUpdate`. Chữ ký và hướng sử dụng có thể khác giữa Hibernate 5, 6 và các bản mới.

Điều cần nhớ về **JPA `EntityManager.merge`** là: **copy trạng thái và trả về managed instance**. Không trộn mô hình này với reattach cùng instance của một số API native khi chưa hiểu rõ contract và phiên bản.

## 8. Removed: entity được đánh dấu xóa khỏi persistence

### 8.1. remove() trên managed entity

~~~java
em.getTransaction().begin();

Product p = em.find(Product.class, productId);
if (p != null) {
    em.remove(p);
}

em.getTransaction().commit();
~~~

`em.remove(p)` đánh dấu entity để xóa. SQL `DELETE` có thể chưa chạy ngay tại lời gọi, mà được đồng bộ khi flush/commit tùy provider, ràng buộc, cascade và transaction.

~~~text
Managed Product
     |
     | em.remove(product)
     v
Removed Product
     |
     | flush
     v
DELETE FROM products WHERE id = ?
     |
     | commit
     v
Hàng bị xóa nếu transaction thành công
~~~

Removed là **trạng thái vòng đời trong persistence context**, không phải trạng thái “đối tượng Java đã được giải phóng”. Object vẫn có thể tồn tại trong RAM sau khi gọi `remove()`, nhưng không nên tiếp tục dùng nó như một managed entity bình thường để sửa dữ liệu nghiệp vụ.

### 8.2. remove() không nhận detached entity như một managed entity

Sai thường gặp:

~~~java
Product detached = ...; // Đã rời context

em.getTransaction().begin();
em.remove(detached); // Có thể ném IllegalArgumentException theo JPA.
em.getTransaction().commit();
~~~

Trong JPA, `remove()` yêu cầu entity thích hợp đang managed trong context; truyền detached entity không phải đường xóa hợp lệ thông thường.

Cách phổ biến là lấy managed entity trong transaction:

~~~java
em.getTransaction().begin();

Product managed = em.find(Product.class, productId);
if (managed != null) {
    em.remove(managed);
}

em.getTransaction().commit();
~~~

Hoặc nếu đã có một detached entity, có thể cân nhắc `merge` trước rồi `remove` **managed instance trả về**, nhưng cần chú ý stale state, version và chi phí sao chép graph. Với thao tác xóa theo ID, `find` rồi `remove` thường rõ ý định hơn.

### 8.3. “Removed” chưa phải “database đã xóa vĩnh viễn”

Nếu transaction rollback, thao tác DELETE đã flush trước đó cũng bị rollback theo khả năng transaction DB. Nếu xóa thất bại vì FK constraint, transaction có thể bị đánh dấu rollback-only hoặc ném exception. Nếu session không flush, lệnh DELETE có thể chưa được gửi.

Sau một lỗi transaction, không nên tiếp tục dựa vào object graph và context như thể mọi thay đổi đã được phục hồi nguyên vẹn. Cách an toàn trong application-managed persistence thường là rollback, đóng/discard context không còn tin cậy và tạo context mới cho use case tiếp theo.

### 8.4. Xóa vật lý khác xóa mềm

`EntityManager.remove` theo mô hình mặc định dẫn tới xóa dữ liệu như một entity row, nhưng Hibernate và ứng dụng có thể cấu hình **soft delete** (đánh dấu trạng thái thay vì thực thi DELETE vật lý). Một số phiên bản Hibernate cung cấp `@SoftDelete` hoặc các cơ chế extension khác.

Vì vậy, khi nói `remove` “xóa”, cần tách:

- **Semantics ở JPA:** entity được chuyển sang removed và không còn được coi là entity đang tồn tại trong persistence theo mapping.
- **SQL/DB thực tế:** DELETE vật lý hoặc một cơ chế soft-delete đã cấu hình riêng.
- **Nghiệp vụ:** hủy, lưu trữ, khôi phục, giữ lịch sử và quan hệ phụ thuộc phải được thiết kế riêng.

### 8.5. Cascade REMOVE và orphanRemoval

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = CascadeType.REMOVE,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

`CascadeType.REMOVE` có thể lan thao tác remove từ parent sang child khi parent bị remove. `orphanRemoval = true` xử lý child bị tách khỏi association riêng theo quy tắc JPA phù hợp.

Hai cơ chế này không giống nhau. Đặc biệt, **không tùy tiện cascade remove sang entity được dùng chung**, chẳng hạn `Order.customer` hoặc `Employee.department`. Việc xóa một order không được làm mất customer nếu customer có vòng đời độc lập.

Các constraint FK ở DB vẫn có thể chặn xóa nếu bản ghi liên quan chưa được xử lý. Hibernate không tự biến mọi ràng buộc nghiệp vụ thành cascade hợp lệ.

### 8.6. Persist lại entity removed?

Theo hợp đồng JPA, có những quy tắc riêng cho `persist()` với entity đã được đánh dấu removed trong cùng persistence context, nhưng không nên sử dụng thao tác “remove rồi persist để hủy xóa” như luồng CRUD bình thường. Nó dễ phụ thuộc trạng thái, cascade, flush và version. Trong nghiệp vụ, nếu thao tác được hiểu là khôi phục sản phẩm, nên thiết kế hành vi khôi phục rõ ràng (đặc biệt với soft delete) thay vì suy đoán về SQL pending.
## 9. Flush, commit, rollback: không đồng nghĩa chuyển trạng thái

**Flush** đồng bộ thay đổi trong persistence context xuống database thông qua những SQL cần thiết. **Commit** xác nhận transaction thành công. Đây là hai sự kiện khác nhau.

~~~java
em.getTransaction().begin();

Product p = new Product(
    "JAVA-004", "Transactions", new BigDecimal("189.00")
);
em.persist(p);

em.flush(); // INSERT có thể đã chạy, nhưng CHƯA commit.

em.getTransaction().rollback();
// SQL đã flush thuộc transaction rollback, không được commit.
~~~

Đừng suy luận rằng gọi `flush()` làm entity trở thành detached. Một entity managed thông thường vẫn được context quản lý sau flush; nó vẫn có thể được sửa và dirty-check tiếp. Ngược lại, `em.clear()` hoặc `em.detach()` thay đổi quan hệ giữa entity và context mà không phải hành động commit.

### 9.1. Hibernate tự flush khi nào?

Với `FlushModeType.AUTO`, provider bảo đảm các quy tắc đồng bộ phù hợp, chẳng hạn trước commit và khi cần để truy vấn phản ánh các thay đổi đang chờ theo đặc tả. Hibernate có thể quyết định flush trước query tùy query và bảng liên quan; không phải mọi lần SELECT đều nhất thiết tạo một flush.

~~~java
em.setFlushMode(FlushModeType.AUTO);
em.getTransaction().begin();

Product p = new Product(
    "JAVA-005", "Flush Example", new BigDecimal("99.00")
);
em.persist(p);

List<Product> result = em.createQuery(
        "select p from Product p where p.sku = :sku",
        Product.class)
    .setParameter("sku", "JAVA-005")
    .getResultList();

em.getTransaction().commit();
~~~

Ví dụ dùng `jakarta.persistence.FlushModeType`. Với `FlushModeType.COMMIT`, provider có thể trì hoãn đồng bộ đến commit; việc query thấy các thay đổi chưa flush như thế nào cần dựa vào quy định và implementation. Hibernate có thêm flush modes ở API native.

Không cần gọi `flush()` sau mỗi setter. Dùng flush chủ động khi có lý do nghiệp vụ hoặc kỹ thuật rõ, ví dụ phát hiện lỗi constraint trước một bước xử lý tiếp theo hay giảm kích thước batch trước khi clear.

### 9.2. Rollback không đưa object Java về nguyên trạng

~~~java
em.getTransaction().begin();
Product managed = em.find(Product.class, productId);
managed.rename("Uncommitted name");

em.getTransaction().rollback();
~~~

Database không commit thay đổi. Nhưng `managed` trong RAM vẫn có thể giữ tên mới. **Rollback transaction không phải một phép undo mọi lệnh gán Java**. Sau lỗi giao dịch, không nên tiếp tục dùng persistence context hoặc entity state cũ như thể đã được nạp lại đúng từ DB. Trong luồng xử lý resource-local thông thường, rollback, đóng context không còn tin cậy và bắt đầu use case mới bằng context mới là một cách quản lý an toàn.

### 9.3. Có thể không thấy đúng một SQL cho mỗi thay đổi

~~~java
em.getTransaction().begin();

Product p = new Product(
    "JAVA-006", "Before", new BigDecimal("120.00")
);
em.persist(p);
p.rename("After");

em.getTransaction().commit();
~~~

Nếu SQL INSERT được trì hoãn, Hibernate có thể đưa tên cuối cùng trực tiếp vào INSERT. Với generator `IDENTITY`, INSERT có thể chạy sớm để lấy khóa; khi đó SQL khác có thể cần thiết. **Trạng thái managed không quy định số câu SQL chính xác**.

## 10. Những API liên quan: contains, find, getReference, refresh, lock

### 10.1. contains() trả lời câu hỏi về context

~~~java
Product p = new Product(
    "JAVA-007", "Demo", new BigDecimal("50.00")
);

boolean before = em.contains(p);  // false: transient.

em.getTransaction().begin();
em.persist(p);

boolean during = em.contains(p);  // true: managed.

em.detach(p);
boolean after = em.contains(p);   // false: detached.

em.getTransaction().commit();
~~~

`em.contains()` không phải truy vấn “có hàng này trong DB hay không?”. Một detached entity vẫn có thể có hàng trong DB, một managed entity mới có thể chưa flush INSERT, còn entity removed có thể chưa được DELETE vật lý. `contains` chỉ nên được hiểu theo hợp đồng quản lý instance hiện tại của persistence context.

### 10.2. find và getReference

~~~java
Product found = em.find(Product.class, productId);
Product ref = em.getReference(Product.class, productId);
~~~

`find` trả managed instance nếu có hoặc `null` nếu không tồn tại theo kết quả truy cập tương ứng. `getReference` có thể trả managed reference chưa tải dữ liệu ngay; việc truy cập proxy hoặc dùng ID không tồn tại có thể dẫn đến lỗi muộn hơn. `getReference` không phải phép kiểm tra existence.

### 10.3. refresh() ghi đè thay đổi trong RAM

~~~java
em.getTransaction().begin();

Product managed = em.find(Product.class, productId);
managed.rename("Not yet saved");

em.refresh(managed);
// Dữ liệu từ DB được nạp lại, thay đổi tên chưa flush có thể bị mất.

em.getTransaction().commit();
~~~

`refresh` dành cho entity managed; truyền detached object thông thường không hợp lệ theo JPA. Nếu association cấu hình cascade REFRESH, refresh có thể lan theo mapping. Không dùng refresh như bước mặc định sau mọi update.

### 10.4. lock() không tương đương merge

`em.lock(managed, lockMode)` áp dụng locking theo hợp đồng JPA và transaction/database tương ứng. Nó không phải cách đưa detached object về managed như `merge`. Nếu cần lock một entity chưa có trong context, lấy managed instance bằng `find`/query phù hợp rồi thực hiện locking.

## 11. Transaction-scoped context và service boundary

Một ứng dụng Spring thường có service dùng transaction-scoped persistence context:

~~~java
@Service
public class ProductService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void rename(long id, String newName) {
        Product managed = em.find(Product.class, id);
        if (managed == null) {
            throw new IllegalArgumentException("Not found");
        }
        managed.rename(newName);
    }
}
~~~

Đây là ví dụ trong môi trường Spring, cần import/cấu hình `@Service`, `@Transactional` và `@PersistenceContext` tương ứng. Trong Java SE với `RESOURCE_LOCAL`, dùng `EntityTransaction.begin/commit/rollback` thay vì kỳ vọng annotation Spring tự có hiệu lực.

Trong mô hình transaction-scoped thông thường, các entity thường detached khi persistence context của transaction kết thúc. Nhưng **không phải cứ kết thúc một method Java là entity detached**: nếu transaction bên ngoài vẫn còn và context vẫn quản lý, entity có thể tiếp tục managed. Jakarta Persistence cũng có extended persistence context trong môi trường hỗ trợ, nơi managed entities có thể sống qua nhiều transaction.

EntityManager không thread-safe. Không chia sẻ một EntityManager dùng chung cho nhiều request/thread độc lập để “giữ” managed entities; điều đó làm phức tạp concurrency, memory và dữ liệu stale.

### Ví dụ DTO thay vì truyền entity giữa request

Một request HTTP có thể mang dữ liệu:

~~~java
public record RenameProductRequest(String newName) {}
~~~

Service xử lý bằng managed entity trong transaction:

~~~java
@Transactional
public void rename(long id, RenameProductRequest request) {
    Product managed = em.find(Product.class, id);
    if (managed == null) {
        throw new IllegalArgumentException("Product not found");
    }
    managed.rename(request.newName());
}
~~~

Điểm mạnh là chỉ thuộc tính được phép sửa mới được cập nhật. Cách này tránh lấy một detached entity không rõ nguồn gốc rồi merge toàn bộ state cũ vào context, có thể ghi đè trường không liên quan hoặc tạo vấn đề phân quyền.

## 12. Cascade và các trạng thái trong một entity graph

Một managed entity có thể tham chiếu đến nhiều đối tượng với trạng thái khác nhau:

~~~text
PurchaseOrder  (managed)
  |
  +-- Customer    (managed hoặc detached)
  |
  +-- OrderLine A (managed)
  |
  +-- OrderLine B (transient mới tạo)
~~~

**Không phải mọi object được tham chiếu từ một managed entity đều tự managed.** Cascade quyết định thao tác JPA được lan sang association nào.

| CascadeType | Ý nghĩa chính |
|---|---|
| `PERSIST` | Lan lời gọi persist tới entity liên quan |
| `MERGE` | Lan merge/copy trạng thái tới graph phù hợp |
| `REMOVE` | Lan remove tới entity liên quan |
| `REFRESH` | Lan refresh |
| `DETACH` | Lan detach |
| `ALL` | Bao gồm những loại cascade chuẩn kể trên |

Ví dụ:

~~~java
@OneToMany(
    mappedBy = "purchaseOrder",
    cascade = { CascadeType.PERSIST, CascadeType.MERGE },
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi persist một order chứa transient lines, cascade PERSIST có thể đưa những line đó vào managed state. Nhưng vẫn cần **đồng bộ owning side của quan hệ hai chiều**:

~~~java
public void addLine(OrderLine line) {
    lines.add(line);
    line.setPurchaseOrder(this);
}
~~~

Đoạn code giả định `OrderLine` có setter/method phù hợp và mapping `@ManyToOne` tới `PurchaseOrder`. Cascade không thay thế yêu cầu nhất quán của foreign key.

Cẩn trọng với:

~~~java
@ManyToOne(cascade = CascadeType.ALL)
private Customer customer;
~~~

Một customer thường được nhiều order sử dụng. Cascade REMOVE từ order sang customer có thể xóa nhầm dữ liệu dùng chung hoặc gặp FK constraint. Chọn cascade theo vòng đời nghiệp vụ, không dựa đơn thuần vào việc quan hệ có một hay hai chiều.

### OrphanRemoval không giống Remove

`orphanRemoval = true` áp dụng cho `@OneToOne` và `@OneToMany` trong những tình huống phù hợp, để xử lý child không còn gắn với association riêng. Có thể có deletion do tách child khỏi collection mà không gọi `em.remove(child)` trực tiếp. Tuy nhiên, cách tách và sự đồng bộ giữa các phía cần đúng mapping; không nên bật orphan removal với entity có vòng đời dùng chung.

## 13. Một luồng end-to-end minh họa bốn trạng thái

~~~java
// 1) Tạo: TRANSIENT.
Product product = new Product(
    "JAVA-101", "Intro to Hibernate",
    new BigDecimal("200.00")
);

// 2) Lưu: instance này thành MANAGED trong em1.
EntityManager em1 = emf.createEntityManager();
try {
    em1.getTransaction().begin();
    em1.persist(product);
    em1.getTransaction().commit();
} finally {
    em1.close();
}

// 3) Context em1 đã đóng: product trở thành DETACHED.
product.rename("Hibernate ORM Fundamentals");

// 4) Dùng context mới, merge trả về MANAGED COPY.
EntityManager em2 = emf.createEntityManager();
try {
    em2.getTransaction().begin();
    Product managedCopy = em2.merge(product);
    managedCopy.reprice(new BigDecimal("220.00"));
    em2.getTransaction().commit();
} finally {
    em2.close();
}

// 5) Xóa trong context mới: MANAGED -> REMOVED.
EntityManager em3 = emf.createEntityManager();
try {
    em3.getTransaction().begin();
    Product managed = em3.find(Product.class, product.getId());
    if (managed != null) {
        em3.remove(managed);
    }
    em3.getTransaction().commit();
} finally {
    em3.close();
}
~~~

Điểm cần nhớ trong ví dụ:

1. `new Product` tạo transient object, không phải database row.
2. `persist` đưa chính object đó vào managed state.
3. `close` làm những managed references của context trở thành detached.
4. `merge` không gắn lại object gốc; nó trả managed copy.
5. `remove` áp dụng trên một managed entity và chuyển nó sang removed.
6. Mọi SQL phụ thuộc flush/transaction/ID strategy. Nếu commit hoặc merge thất bại, luồng thành công trên không còn giữ nguyên; cần error handling và rollback đầy đủ ở code production.

Khi object có lazy associations, phần chưa được nạp ở thời điểm detach có thể không truy cập được ngoài context, ngay cả khi các thuộc tính scalar đã tải vẫn đọc được.
## 14. Lifecycle callback: sự kiện của vòng đời entity

JPA cung cấp annotation callback như `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove` và `@PostLoad`. Những callback này **không phải bốn trạng thái**, mà là hook gắn với các sự kiện cụ thể của provider trong quá trình quản lý entity.

Ví dụ:

~~~java
@Entity
@Table(name = "audit_notes")
public class AuditNote {
    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false)
    private String text;

    private Instant createdAt;
    private Instant updatedAt;

    protected AuditNote() {}

    public AuditNote(String text) {
        this.text = text;
    }

    @PrePersist
    void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

Các import tương ứng lấy từ `jakarta.persistence` và `java.time.Instant`. Khi `persist` đưa một transient entity vào context và provider thực hiện thao tác persist, callback `@PrePersist` có thể thiết lập thời gian. Khi entity managed bị thay đổi và Hibernate chuẩn bị UPDATE, `@PreUpdate` có thể được gọi theo điều kiện của persistence provider.

### Callback có phải thông báo transaction đã commit không?

**Không.** `@PostPersist`/`@PostUpdate`/`@PostRemove` gắn với thao tác lifecycle của persistence provider, không có nghĩa transaction đã commit thành công hay sự kiện đã được hệ thống khác quan sát. Transaction có thể rollback sau khi callback chạy.

Nếu muốn phát sự kiện nghiệp vụ chỉ sau khi DB commit thành công, cần cơ chế transaction synchronization hoặc outbox/event publication phù hợp, thay vì phát trực tiếp từ callback và giả định không bao giờ rollback.

### Callback có biến detached object thành managed không?

Không. `@PostLoad` chạy khi provider nạp entity theo quy tắc tương ứng; nó không làm một detached object tùy ý được quản lý trở lại. `@PreUpdate` cũng không được gọi chỉ vì ta chỉnh một detached object ngoài context.

Callback không thay thế lifecycle API `persist`, `merge`, `remove` và không nên chứa logic database phức tạp phá vỡ kỳ vọng của persistence context.

## 15. Optimistic locking và detached entity có dữ liệu cũ

Thao tác với detached entity thường đi kèm rủi ro *stale state* (trạng thái đã cũ). `@Version` là công cụ quan trọng để phát hiện một phần xung đột khi nhiều transaction cập nhật cùng một entity.

~~~java
@Version
@Column(name = "version", nullable = false)
private long version;
~~~

Giả sử hai request cùng đọc sản phẩm ở version 3:

~~~text
Request A                        Request B
---------                        ---------
Đọc Product v3                   Đọc Product v3
Đổi tên                          Đổi giá
                                Commit -> Product v4
Merge Product v3
Flush/commit -> phát hiện
version không phù hợp
~~~

Nếu provider phát hiện xung đột optimistic locking, có thể ném `OptimisticLockException` hoặc ngoại lệ liên quan tùy API và thời điểm merge/flush/commit. Không nên mặc định lỗi xuất hiện ngay tại `merge()`; nó cũng có thể xuất hiện khi flush hoặc commit.

### Version không phải giải pháp cho mọi xung đột

Cơ chế version chỉ hiệu quả nếu các đường cập nhật liên quan tuân theo quy ước version và transaction. SQL trực tiếp ngoài ORM không thay version có thể làm khả năng phát hiện xung đột suy yếu. Bulk JPQL update và native SQL cũng cần được đánh giá riêng về version và trạng thái entity trong context.

Ngoài ra, các giao dịch có logic kiểm tra nhiều hàng hoặc ràng buộc giữa các entity vẫn có thể cần unique constraint, transaction isolation hoặc locking khác.

### Không cố đặt version bằng giá trị từ client

Client không nên được tự ý quyết định giá trị version/ID như một phương thức tránh optimistic locking. Nếu API dùng version trong request để phát hiện chỉnh sửa đồng thời, service cần so sánh theo hợp đồng rõ ràng và phản hồi conflict thích hợp. Một entity detached được deserialise từ request không mặc nhiên là đối tượng an toàn để merge.

## 16. Trạng thái entity và native/bulk operations

### 16.1. Bulk JPQL UPDATE/DELETE có thể bỏ qua object-level dirty checking

Ví dụ:

~~~java
em.getTransaction().begin();

int updated = em.createQuery(
    "update Product p set p.price = :price where p.sku like :prefix")
    .setParameter("price", new BigDecimal("199.00"))
    .setParameter("prefix", "JAVA-%")
    .executeUpdate();

em.getTransaction().commit();
~~~

Bulk update chạy ở mức database, không đi qua vòng đời setter và dirty checking của từng managed entity theo cùng cách như sửa entity một lượt. Vì vậy các entity `Product` đã managed trong context **có thể giữ giá trị cũ trong RAM** sau câu bulk SQL. `@Version`, lifecycle callbacks và cascade cũng cần được đánh giá riêng đối với bulk operations.

Một chiến lược thường dùng sau bulk operation là kết thúc context/use case hiện tại hoặc cân nhắc `clear`/refresh phù hợp, nhưng cần chú ý các thay đổi khác chưa flush trước khi clear. Không gọi `clear` vô điều kiện khi còn công việc chưa đồng bộ.

### 16.2. Native SQL ngoài context làm object managed có thể stale

Giả sử một stored procedure hoặc ứng dụng khác trực tiếp cập nhật `products.price`. Hibernate không tự biết mọi thay đổi SQL từ bên ngoài. Một `Product` đã managed có thể vẫn giữ giá cũ, vì first-level cache đại diện cho state đã được nạp trước đó.

Khi bắt buộc làm mới giá trị, cân nhắc `refresh(managed)` hoặc dùng context mới. Nhưng refresh có thể ghi đè thay đổi chưa flush, nên phải chủ động lựa chọn thứ tự thao tác.

### 16.3. Batch import: flush và clear có mục tiêu khác nhau

Trong một tác vụ tạo hàng nghìn entity:

~~~java
em.getTransaction().begin();

for (int i = 0; i < inputs.size(); i++) {
    InputRow row = inputs.get(i);

    Product p = new Product(
        row.sku(), row.name(), row.price()
    );
    em.persist(p);

    if ((i + 1) % 100 == 0) {
        em.flush();
        em.clear();
    }
}

em.getTransaction().commit();
~~~

`flush()` đồng bộ SQL pending; `clear()` gỡ những managed entities khỏi context để tránh context phình to. Đây là mẫu khái niệm, không phải bảo đảm mỗi 100 đối tượng tạo đúng một batch SQL. JDBC batching còn phụ thuộc generator, cấu hình `hibernate.jdbc.batch_size`, dialect và tính năng của driver; `IDENTITY` thường hạn chế cơ hội batch insert.

Sau `clear()`, các references đến entity đã tạo là detached. Nếu batch cần tiếp tục thao tác trên chúng, phải có chiến lược rõ ràng (giữ ID, nạp lại hoặc merge trong context phù hợp).

## 17. Những lỗi thường gặp khi nhầm trạng thái

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Gọi setter nhưng database không đổi | Entity detached hoặc context read-only/chưa flush | Xác định context/transaction; nạp managed entity rồi sửa |
| `persist` báo entity đã tồn tại | Truyền detached entity vào persist | Không dùng persist cho cập nhật; xem find/merge |
| `remove` ném `IllegalArgumentException` | Object chưa managed/đã detached | Find managed entity bằng ID rồi remove |
| Gọi `merge` nhưng sửa object gốc vẫn không lưu | Đầu vào merge vẫn detached | Dùng managed object do merge trả về |
| Sau `clear` mất dữ liệu vừa sửa | Thay đổi chưa flush đã bị bỏ theo context | Flush đúng lúc trước clear nếu thực sự cần lưu |
| Gọi `flush` rồi rollback mà DB không có row | Flush không phải commit | Hiểu transaction boundary |
| Kết thúc transaction nhưng object vẫn có dữ liệu mới | Rollback không đảo ngược field Java | Bỏ context lỗi, nạp lại ở context mới |
| `LazyInitializationException` ở controller | Proxy/collection chưa tải đã detached | Fetch đúng use case hoặc tạo DTO trong transaction |
| `OptimisticLockException` khi merge | Detached entity cũ, version đã thay đổi | Xử lý conflict, reload, yêu cầu người dùng quyết định |
| Thêm child mới vào managed collection nhưng không insert | Thiếu cascade PERSIST hoặc child chưa được persist | Gắn owning side, persist hoặc cascade phù hợp |
| Xóa parent làm lỗi FK | Child còn tham chiếu hoặc cascade không đúng | Quy định vòng đời và foreign key |
| Xóa một order lại ảnh hưởng customer | Cascade REMOVE sang entity dùng chung | Thiết kế lại cascade |
| Bulk update xong đọc managed object vẫn là giá cũ | Bulk SQL không tự làm mới first-level state | Refresh/clear/context mới có kiểm soát |
| `getReference` tạo proxy nhưng ID không tồn tại | Reference không luôn kiểm tra DB ngay | Find/query để xác thực khi cần |
| Có ID nên nghĩ entity đang managed | Identity không đủ để xác định state | Kiểm tra context, tránh suy đoán qua null ID |
| `@PostPersist` chạy nhưng transaction sau đó rollback | Callback không phải sự kiện after-commit | Dùng outbox/transaction synchronization nếu cần |

### 17.1. “Không lưu” không phải lúc nào do thiếu save()

Trong JPA/Hibernate, một managed entity có thể được ghi khi flush mà không gọi `save`. Khi thấy dữ liệu không đổi, hãy phân biệt những câu hỏi:

- Object có đang được context hiện tại quản lý không?
- Transaction có chạy và commit thành công không?
- Có rollback/exception nào bị bỏ qua không?
- Field có phải persistent attribute không?
- Có `@Column(updatable = false)` hoặc read-only mapping không?
- Thay đổi có bị `refresh` hoặc merge state khác ghi đè không?
- Câu bulk/native SQL có làm context cũ stale không?

Những nguyên nhân này liên quan trực tiếp đến lifecycle và transaction, không thể chữa bằng cách thêm `persist` bừa bãi.

### 17.2. “Đã xóa” không có nghĩa DELETE đã commit

Khi entity ở removed state, SQL DELETE có thể chưa flush, transaction vẫn có thể rollback, FK constraint có thể chặn xóa, hoặc dự án đã cấu hình soft delete. Cần phân biệt thời điểm yêu cầu xóa, thời điểm database thực thi SQL và thời điểm transaction thành công.

### 17.3. Đừng truyền entity qua các boundary mà không cân nhắc

Đối tượng entity thường chứa lazy associations, trạng thái context và nhiều field không nên lộ ra API. Trả entity trực tiếp qua JSON hoặc nhận lại entity từ client rồi merge có thể tạo vòng lặp serialization, N+1, lỗi lazy, mass assignment hoặc ghi đè stale state.

DTO dành cho input/output với service xử lý managed entities trong transaction là phương án dễ kiểm soát hơn trong nhiều ứng dụng.

## 18. Bài tập tự luyện

### Bài 1 — Chọn trạng thái

~~~java
Product p = new Product(
    "JAVA-501", "Example", new BigDecimal("90.00")
);
~~~

**Câu hỏi:** trạng thái của `p` là gì, nếu chưa gọi `persist` hoặc được cascade?

**Đáp án:** `transient`. Class có `@Entity` không tự làm object được persistence context quản lý.

### Bài 2 — Thay đổi managed entity

~~~java
em.getTransaction().begin();
Product p = em.find(Product.class, id);
p.reprice(new BigDecimal("110.00"));
em.getTransaction().commit();
~~~

**Câu hỏi:** có nhất thiết phải gọi thêm `em.persist(p)` hay `em.merge(p)` không?

**Đáp án:** Không. `p` đang managed, Hibernate có thể phát hiện thay đổi và đồng bộ khi flush. Nếu `find` trả null thì phải xử lý trường hợp không tồn tại trước khi gọi method.

### Bài 3 — Detached sau khi đóng context

~~~java
Product p = em.find(Product.class, id);
em.close();
p.rename("Outside transaction");
~~~

**Câu hỏi:** tên mới có tự được ghi không?

**Đáp án:** Không, vì `p` đã detached khỏi context vừa đóng. Cần dùng một transaction/context mới và thao tác trên managed entity phù hợp.

### Bài 4 — Bẫy merge

~~~java
Product managed = em.merge(detached);
detached.reprice(new BigDecimal("150.00"));
~~~

**Câu hỏi:** đối tượng nào được theo dõi?

**Đáp án:** `managed`. Thay đổi trên detached object sau merge không tự chuyển tới managed instance. Phải sửa `managed` hoặc merge lại trạng thái theo quy trình thích hợp.

### Bài 5 — Remove đúng cách

~~~java
Product detached = loadInPreviousRequest();
em.remove(detached);
~~~

**Câu hỏi:** có hợp lệ không?

**Đáp án:** Không phải cách dùng chuẩn JPA; remove yêu cầu managed entity. Lấy entity bằng `em.find` trong transaction hiện tại rồi remove, và xác định chính sách đối với ID không tồn tại.

### Bài 6 — Flush trước clear

~~~java
em.getTransaction().begin();
Product p = em.find(Product.class, id);
p.rename("Name A");
em.clear();
em.getTransaction().commit();
~~~

**Câu hỏi:** vì sao tên A có thể không được lưu?

**Đáp án:** `clear` detach toàn bộ managed entities, bỏ những thay đổi chưa được đồng bộ. Nếu muốn giữ thay đổi khi clear, cần bảo đảm flush trước đó trong transaction phù hợp.

### Bài 7 — Rollback và bộ nhớ

~~~java
em.getTransaction().begin();
Product p = em.find(Product.class, id);
p.rename("Temporary");
em.getTransaction().rollback();
System.out.println(p.getName());
~~~

**Câu hỏi:** có chắc in ra tên cũ trong DB không?

**Đáp án:** Không. Rollback của DB không làm Java tự chạy ngược setter. Cần bỏ context không còn đáng tin và nạp lại dữ liệu khi cần.

### Bài 8 — Detached và stale state

Hai request cùng đọc version 5. Request A commit một update thành version 6. Request B merge detached entity version 5.

**Câu hỏi:** vai trò của `@Version`?

**Định hướng:** Hỗ trợ phát hiện optimistic lock conflict, có thể ném exception khi merge, flush hoặc commit. Service cần có chiến lược xử lý xung đột thay vì âm thầm ghi đè.

### Bài 9 — Cascade PERSIST

Một managed order chứa transient order line, nhưng association không cascade persist và line chưa được persist trực tiếp.

**Câu hỏi:** chỉ thêm vào collection có bảo đảm line được INSERT không?

**Đáp án:** Không. Cần mapping cascade phù hợp hoặc persist line trực tiếp, đồng thời cập nhật owning reference của quan hệ.

### Bài 10 — Trạng thái Removed

~~~java
em.getTransaction().begin();
Product p = em.find(Product.class, id);
em.remove(p);
// Chưa commit.
~~~

**Câu hỏi:** có thể kết luận hàng DB đã bị xóa vĩnh viễn?

**Đáp án:** Không. Entity đã được đánh dấu removed; SQL có thể chưa flush và transaction có thể rollback hoặc thất bại.

## 19. Tổng kết

Bốn trạng thái vòng đời thực thể trả lời câu hỏi: **Hibernate có đang quản lý instance Java này và sẽ làm gì với thay đổi của nó?**

- **Transient:** object mới chưa được context quản lý. `persist` hoặc cascade PERSIST có thể chuyển nó sang managed.
- **Managed:** object nằm trong persistence context; Hibernate theo dõi persistent state, dirty checking và đồng bộ khi flush.
- **Detached:** object đã rời context; vẫn có ID/giá trị Java nhưng thay đổi tiếp theo không tự được ghi. `merge` sao chép trạng thái và **trả về managed instance**, không biến object đầu vào thành managed.
- **Removed:** entity đã được đánh dấu xóa trong context; DELETE có thể được đồng bộ sau và chỉ có hiệu lực bền vững khi transaction commit thành công.

Đồng thời luôn phân biệt **state transition**, **flush**, **commit/rollback**, **cascade**, **lazy loading** và **database constraints**. Chúng tác động lẫn nhau nhưng không phải cùng một cơ chế.

Một quy tắc hữu ích trong ứng dụng nhiều transaction là: **đọc managed entity trong transaction của use case, cập nhật đúng field được phép, để Hibernate dirty-check, và trả DTO ra khỏi service**. Khi xử lý detached objects, sử dụng `merge` có chủ đích, xử lý optimistic locking và tránh sao chép toàn bộ state cũ một cách mù quáng.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — trạng thái entity, persistence context, EntityManager, cascade, flush và transaction.
- [Jakarta Persistence API — EntityManager](https://jakarta.ee/specifications/persistence/) — tài liệu API của `persist`, `find`, `merge`, `remove`, `detach`, `clear` và `refresh` theo version.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — persistence context, entity states, flushing, dirty checking và cascades.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — các ví dụ về entity state transitions và flush.
- [Hibernate ORM — Session](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Session.html) — native API tương ứng với nhiều khái niệm JPA.

> Các ví dụ mô tả Hibernate/Jakarta Persistence hiện đại. Chi tiết exception, thời điểm SQL được thực thi, ID generator, callback và phạm vi persistence context có thể khác theo phiên bản Hibernate, cách cấu hình và framework tích hợp. Khi làm việc với production, hãy xác định transaction boundary và lifecycle contract của chính ứng dụng.



