# Từ thao tác đối tượng đến hàng đợi hành động và SQL gửi qua JDBC trong Hibernate

Khi ứng dụng gọi `entityManager.persist(entity)`, sửa thuộc tính của một entity, hoặc gọi `entityManager.remove(entity)`, Hibernate không đơn giản chuyển từng dòng Java thành một câu SQL ngay lập tức. Nó quản lý **trạng thái đối tượng trong persistence context**, xác định những thay đổi cần đồng bộ, xếp các thao tác ghi vào **hàng đợi hành động (ActionQueue)**, sắp xếp chúng theo quy tắc nội bộ, tạo SQL phù hợp với cơ sở dữ liệu và thực thi thông qua **JDBC**. Quá trình đồng bộ đó được gọi là **flush**.

Hiểu được đường đi này giúp giải thích các hiện tượng tưởng như bất thường: đã gọi `persist()` nhưng chưa thấy `INSERT`; chỉ sửa một đối tượng mà Hibernate phát sinh `UPDATE`; `DELETE` được gọi trước `INSERT` nhưng SQL lại chạy sau; query bất ngờ kích hoạt ghi dữ liệu; hoặc một ràng buộc duy nhất bị vi phạm dù code Java đã “xóa trước, thêm sau”.

> **Phạm vi:** Các ví dụ dùng API Jakarta Persistence (`jakarta.persistence`) và cách vận hành phổ biến của Hibernate ORM 6.x. Hibernate 5 dùng tên gói `javax.persistence` và một số chi tiết log/nội bộ khác. Thứ tự các nhóm hành động và khả năng tối ưu hóa có thể thay đổi theo phiên bản, mapping và cấu hình; không nên coi thứ tự một số câu SQL cụ thể là hợp đồng công khai của ORM.

## 1. Bức tranh tổng thể: từ Java đến cơ sở dữ liệu

~~~mermaid
flowchart TD
    A["Ứng dụng: persist, find, sửa field, remove"] --> B["EntityManager / Hibernate Session"]
    B --> C["Persistence context: entity được quản lý, identity map, snapshot"]
    C --> D["Flush: kiểm tra thay đổi, cascade, đồng bộ collection"]
    D --> E["ActionQueue: INSERT, UPDATE, DELETE, collection actions"]
    E --> F["Sắp xếp thao tác và tạo SQL theo mapping / Dialect"]
    F --> G["JDBC: PreparedStatement, bind tham số, execute/batch"]
    G --> H["Database: constraint, lock, transaction log, dữ liệu"]
    H --> I["Kết quả / exception / số hàng bị ảnh hưởng"]
    I --> B
    B --> J["Commit hoặc rollback transaction"]
~~~

Cần phân biệt ba thời điểm:

1. **Đối tượng thay đổi trong bộ nhớ:** sau `item.setQuantity(12)`, đối tượng Java đã có giá trị mới.
2. **Flush thực thi SQL:** Hibernate gửi thao tác ghi xuống database qua JDBC. Dữ liệu có thể đã được ghi *trong transaction đang mở*, nhưng chưa được commit.
3. **Commit transaction:** database xác nhận giao dịch. Nếu transaction rollback, các thay đổi đã flush cũng bị hủy.

`flush()` không đồng nghĩa với `commit()`; `commit()` trong cách dùng transaction thông thường sẽ kích hoạt flush các thay đổi còn chờ trước khi xác nhận giao dịch. Lệnh SQL đọc, truy xuất identifier, thao tác bulk và một số cách sinh khóa có thể đi qua JDBC ở thời điểm khác với luồng ghi thông thường.

### Những thành phần tham gia

| Thành phần | Trách nhiệm chính |
|---|---|
| `EntityManager` / `Session` | API làm việc với entity, truy vấn và vòng đời persistence context; `Session` là API gốc của Hibernate, `EntityManager` là API chuẩn JPA. |
| Persistence context (first-level cache) | Bảo đảm một entity identity tương ứng với một đối tượng managed trong cùng context, lưu trạng thái theo dõi thay đổi và các collection liên quan. |
| Dirty checking | Xác định entity/thuộc tính nào thay đổi so với trạng thái Hibernate đang theo dõi. |
| Flush processing | Phối hợp kiểm tra thay đổi, cascade và chuẩn bị các hành động đồng bộ. |
| `ActionQueue` | Chứa/điều phối các hành động ghi entity và collection, thực thi chúng theo thứ tự Hibernate quy định. Đây là cấu trúc nội bộ, không phải API ứng dụng nên phụ thuộc phiên bản. |
| Mapping metadata và SQL mutation machinery | Biết entity ứng với bảng/cột nào, khóa, association, version, cách sinh giá trị và SQL cần phát sinh. |
| `Dialect` | Điều chỉnh cú pháp và khả năng SQL theo hệ quản trị database, chẳng hạn PostgreSQL, MySQL hay Oracle. |
| JDBC | Chuẩn bị `PreparedStatement`, gán bind parameters, gọi `executeUpdate()` hoặc JDBC batch, nhận kết quả/lỗi từ driver. |
| Database | Thực thi SQL, kiểm tra constraint, kiểm soát transaction và quyết định thành công/thất bại. |

## 2. Persistence context: nơi đối tượng trở thành trạng thái được theo dõi

Hibernate không thể tạo đúng SQL nếu không biết đối tượng nào là mới, đối tượng nào đang được quản lý và thay đổi nào đã xảy ra. Vì vậy phải hiểu **vòng đời entity**:

| Trạng thái | Ý nghĩa | Hệ quả khi flush |
|---|---|---|
| **Transient / new** | Đối tượng Java chưa nằm trong persistence context, chưa được đăng ký để lưu. | Tự thay đổi field không tạo SQL. |
| **Managed / persistent** | Entity gắn với persistence context, Hibernate theo dõi identity và thay đổi. | Thay đổi phù hợp có thể dẫn tới `INSERT`/`UPDATE`/`DELETE` tương ứng. |
| **Detached** | Entity từng managed nhưng đã tách khỏi context. | Chỉ sửa detached object không làm context hiện tại tự cập nhật DB. |
| **Removed** | Entity managed đã được đánh dấu xóa. | Hibernate chuẩn bị hành động `DELETE`, thường thực thi khi flush. |

~~~java
InventoryItem item = new InventoryItem("KB-01", 10); // transient
entityManager.persist(item);                         // managed
item.increase(5);                                    // đổi state managed
entityManager.flush();                               // đồng bộ thành SQL
entityManager.detach(item);                          // detached
item.increase(1);                                    // không tự được đồng bộ nữa
~~~

Một persistence context có **identity map**: trong cùng context, hai lần tìm cùng entity type và primary key thường trả lại cùng *instance* Java:

~~~java
InventoryItem a = entityManager.find(InventoryItem.class, 42L);
InventoryItem b = entityManager.find(InventoryItem.class, 42L);
assert a == b;
~~~

Điều này cũng lý giải vì sao query có thể lấy entity từ context mà không chạy thêm `SELECT`, và vì sao một object managed thay đổi trong bộ nhớ có thể hiển thị giá trị mới trước khi phát sinh `UPDATE`. First-level cache gắn với persistence context; nó khác second-level cache (nếu bật), vốn chia sẻ dữ liệu giữa nhiều session theo chính sách cache.

Thông thường Hibernate lưu một **snapshot** của trạng thái entity khi tải từ database hoặc sau khi đồng bộ, rồi so sánh với trạng thái hiện tại khi dirty checking. Khi sử dụng **bytecode enhancement** hỗ trợ theo dõi thay đổi, Hibernate có thể nhận biết field đã bị sửa mà không nhất thiết so sánh mọi thuộc tính theo cùng cách. Khác biệt triển khai này không thay đổi nguyên tắc: Java object thay đổi chưa đồng nghĩa SQL được gửi ngay.

## 3. Ví dụ xuyên suốt: `persist()`, sửa object, flush, rồi commit

Xét entity đơn giản sau:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {
    @Id
    @SequenceGenerator(
        name = "inventory_item_seq_gen",
        sequenceName = "inventory_item_seq",
        allocationSize = 1
    )
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "inventory_item_seq_gen"
    )
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected InventoryItem() {} // JPA cần constructor không tham số

    public InventoryItem(String sku, int quantity) {
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() { return id; }
    public int getQuantity() { return quantity; }

    public void increase(int amount) {
        if (amount <= 0) throw new IllegalArgumentException("amount");
        quantity += amount;
    }
}
~~~

Với transaction `RESOURCE_LOCAL`, ứng dụng làm:

~~~java
EntityTransaction tx = entityManager.getTransaction();
tx.begin();

InventoryItem item = new InventoryItem("KB-01", 10);
entityManager.persist(item);   // (A) đưa entity vào context
item.increase(5);              // (B) số lượng thành 15
entityManager.flush();         // (C) đồng bộ lần 1
item.increase(2);              // (D) số lượng thành 17

tx.commit();                   // (E) flush còn chờ, rồi commit
~~~

Giả sử dùng PostgreSQL, bảng và sequence đã tồn tại, và không có trigger/default đặc biệt. Một **diễn tiến SQL minh họa** có thể là:

~~~sql
-- (A) Hibernate cần identifier từ sequence:
select nextval('inventory_item_seq');

-- (C) Lần flush đầu: trạng thái cuối của entity lúc này là quantity = 15
insert into inventory_item (quantity, sku, version, id)
values (?, ?, ?, ?);
-- bind: 15, 'KB-01', 0, <id vừa cấp>

-- (E) Commit đòi hỏi đồng bộ phần mới thay đổi sau lần flush trước:
update inventory_item
set quantity = ?, sku = ?, version = ?
where id = ? and version = ?;
-- bind ví dụ: 17, 'KB-01', 1, <id>, 0
~~~

Danh sách cột và vị trí bind thực tế do mapping, cấu hình và phiên bản quyết định. Với mapping thường, `UPDATE` có thể bao gồm nhiều cột có thể cập nhật dù chỉ `quantity` đổi; `@DynamicUpdate` là một lựa chọn để Hibernate sinh SQL dựa trên các cột dirty, nhưng cần cân nhắc tác động lên việc tái sử dụng statement và batching.

| Thời điểm | Trạng thái trong Java | Trạng thái đồng bộ |
|---|---|---|
| Mới `new` | `quantity = 10` | Chưa có hành động persistence. |
| Sau `persist()` | Managed, `quantity = 10` | Có thể đã lấy ID bằng SQL sequence; thường chưa `INSERT` bảng entity. |
| Sau `increase(5)` | Managed, `quantity = 15` | Chưa cần `UPDATE`: bản ghi vẫn chưa được chèn. |
| Sau `flush()` | Managed, `quantity = 15` | `INSERT` thành công trong transaction, snapshot được đồng bộ. |
| Sau `increase(2)` | Managed, `quantity = 17` | Entity lại dirty, chưa bắt buộc có SQL ngay. |
| Sau `commit()` | Giá trị mới đã được đồng bộ | `UPDATE` gửi qua JDBC trước commit; DB commit nếu không có lỗi. |

Lưu ý: ngay cả khi đã có ID sau `persist()`, điều đó **không chứng minh hàng đã tồn tại trong bảng**. Sequence có thể cấp khóa trước khi chèn. Ngược lại, với `GenerationType.IDENTITY`, Hibernate thường phải thực thi `INSERT` sớm hơn để database tạo ID; đây là ngoại lệ đáng nhớ đối với mô hình “ghi dồn đến flush”.

Trong ứng dụng Spring hoặc môi trường JTA, transaction thường được quản lý bằng `@Transactional`/container. Khi đó không tự gọi `entityManager.getTransaction()` như ví dụ `RESOURCE_LOCAL`; ý nghĩa của managed state và flush về cơ bản vẫn tương tự.

## 4. Từ lời gọi API đến hành động đang chờ

Không phải mọi lời gọi API đều tương ứng với một câu SQL hay một hành động có sẵn ngay lập tức:

| Thao tác ứng dụng | Hibernate xử lý | SQL thường xảy ra khi nào? |
|---|---|---|
| `persist(newEntity)` | Đăng ký entity mới, áp dụng cascade persist, quyết định identifier, chuẩn bị chèn. | Thường lúc flush; có ngoại lệ lấy ID hoặc insert sớm do generator/mapping. |
| `find(Entity.class, id)` | Kiểm tra persistence context, cần thì đọc database, đưa kết quả vào context. | `SELECT` có thể chạy ngay nếu chưa có sẵn trong context/cache. |
| Gọi setter trên managed entity | Đổi trạng thái Java; dirty checking ghi nhận chênh lệch vào lúc thích hợp. | `UPDATE` thường được chuẩn bị khi flush. |
| `remove(managedEntity)` | Đánh dấu entity removed, xử lý cascade remove. | `DELETE` thường lúc flush; một số side effect/cascade có thể truy vấn thêm dữ liệu. |
| Thay đổi persistent collection | Hibernate theo dõi collection/association và chủ sở hữu quan hệ. | Có thể phát sinh SQL của bảng con/bảng nối ở flush. |
| `merge(detachedEntity)` | Tìm/tạo managed instance và **sao chép trạng thái** từ detached object vào nó, có thể cascade merge. | Có thể `SELECT` trước; `INSERT`/`UPDATE` tùy trạng thái và dirty check khi flush. |
| `refresh(entity)` | Đọc lại trạng thái từ DB và cập nhật instance managed. | Thường phát sinh `SELECT`; thay đổi chưa flush trên entity đó có thể bị ghi đè. |
| JPQL/HQL bulk `update`/`delete` | Chạy lệnh bulk trực tiếp thay vì sửa lần lượt các managed entity. | SQL bulk chạy ở `executeUpdate()`; có thể đòi hỏi flush trước và không tự cập nhật mọi object đang managed. |

Một vài hệ quả:

- **Không cần gọi `save()` sau mỗi setter.** Với entity đang managed, Hibernate dựa trên dirty checking để tạo `UPDATE`. `save()` là API Hibernate có lịch sử riêng; `persist()`/`merge()` là các thao tác chuẩn JPA với ý nghĩa khác nhau.
- **`merge()` không biến chính detached object thành managed.** Biến trả về từ `merge()` mới là instance cần tiếp tục thao tác nếu muốn thay đổi được theo dõi.
- **Object không managed thì không được tự động ghi.** Một DTO hay entity detached có thể thay đổi vô hạn lần mà Hibernate không tạo `UPDATE` tương ứng nếu không có thao tác kết nối trạng thái thích hợp.
- **Cascade là chính sách truyền thao tác vòng đời**, không phải bảo đảm mọi SQL được thực thi ngay sau lời gọi Java. Các constraint của database và phía sở hữu relationship vẫn là yếu tố quyết định tính đúng đắn.

## 5. Flush: điểm chuyển từ trạng thái object sang SQL

Có thể hình dung một lần flush theo các bước logic:

1. Hibernate xem xét persistence context và trạng thái các entity/collection đang được quản lý.
2. Nó thực hiện các xử lý cần thiết như cascade, dirty checking, kiểm tra version và xác định insert/update/delete hoặc thay đổi collection.
3. Nó đưa/hoàn thiện các thao tác ghi thành những hành động có thể thực thi trong `ActionQueue`.
4. Nó xử lý thứ tự hành động và những điều kiện phụ thuộc (khóa ngoại, collection, orphan removal, identifier, v.v.).
5. Nó tạo hoặc tái sử dụng SQL phù hợp mapping và dialect; đưa tham số vào JDBC statement/batch.
6. JDBC gửi SQL đến DB; kết quả và lỗi được phản hồi về Hibernate. Hibernate cập nhật bookkeeping/snapshot khi flush thành công.

Đây là **mô hình khái niệm**, không phải lịch gọi hàm nội bộ cố định: ví dụ hành động insert có thể được tạo từ lúc `persist()`; update thường được phát hiện ở flush; collection có cơ chế theo dõi riêng; một số SQL có thể đã chạy trước flush.

### Khi nào flush diễn ra?

- **Gọi tường minh** `entityManager.flush()` / `session.flush()`.
- **Trước commit** trong trường hợp transaction managed bình thường có thay đổi phải đồng bộ.
- **Trước một số truy vấn** khi chế độ flush yêu cầu bảo đảm tính nhất quán giữa trạng thái pending và kết quả query. Với Hibernate `AUTO`, JPQL/HQL query liên quan các bảng có thay đổi đang chờ thường kích hoạt flush; native SQL có quy tắc riêng tùy dùng `EntityManager` hay `Session` và cách khai báo vùng đồng bộ.
- **Khi framework chủ động yêu cầu** như phương thức repository có tùy chọn flush; đây chỉ là cách gọi flush qua tầng API.

Các chế độ thường gặp:

| Flush mode | Ý nghĩa thực tế |
|---|---|
| `AUTO` (thông thường) | Hibernate quyết định flush khi cần, gồm trước commit và trước một số query có thể bị ảnh hưởng bởi thay đổi chưa đồng bộ. |
| `COMMIT` | Chủ yếu dồn flush đến commit; mức độ query nhìn thấy thay đổi chưa flush có thể phụ thuộc provider và ngữ cảnh. |
| `ALWAYS` (Hibernate) | Flush trước mỗi truy vấn được thực hiện qua session theo cách Hibernate định nghĩa; dễ làm tăng chi phí. |
| `MANUAL` (Hibernate) | Ứng dụng phải chủ động flush ở thời điểm thích hợp; không nên dùng tùy tiện trong transaction ghi. |

Trong JPA chuẩn có `FlushModeType.AUTO` và `FlushModeType.COMMIT`; `ALWAYS` và `MANUAL` là chế độ riêng của Hibernate. Đừng suy luận rằng mọi `SELECT` đều flush hoặc mọi `SELECT` đều bỏ qua flush.

~~~java
tx.begin();

InventoryItem item = entityManager.find(InventoryItem.class, 42L);
item.increase(3);

// Trong AUTO mode, truy vấn cùng bảng có thể khiến UPDATE được flush trước SELECT.
List<InventoryItem> rows = entityManager.createQuery(
    "select i from InventoryItem i where i.quantity > :min",
    InventoryItem.class
).setParameter("min", 10).getResultList();

tx.commit();
~~~

Trường hợp query kích hoạt flush không có nghĩa Hibernate “commit giữa chừng”. Transaction vẫn mở cho đến khi commit hoặc rollback.

### Flush không bắt buộc tạo SQL

Nếu không có thao tác ghi đang chờ, dirty checking kết luận không có thay đổi, hoặc entity chỉ được đọc, một lần flush có thể **không phát sinh DML**. Đọc một property, gọi setter với cùng giá trị (tùy cơ chế dirty tracking và so sánh), hoặc gọi `flush()` liên tiếp không đủ để khẳng định luôn có `UPDATE` mới.

Ngược lại, annotation và mapping có thể buộc Hibernate làm nhiều việc hơn một lệnh đơn: entity thuộc inheritance mapping nhiều bảng; secondary table; association có join table; cascades; orphan removal; hoặc ID cần lấy sớm.

## 6. ActionQueue: hàng đợi điều phối thao tác ghi

`ActionQueue` là một cấu trúc nội bộ của Hibernate để quản lý các thao tác sẽ thực thi khi flush. Nó không nên được hiểu là một danh sách FIFO đơn giản “gọi hàm Java trước thì SQL trước”. Các loại action có thể nằm trong những nhóm/hàng đợi riêng và được thực thi theo quy tắc ưu tiên.

Trong Hibernate ORM 6.x, tài liệu về **flush operation order** trình bày thứ tự nhóm hành động điển hình như sau (tên lớp nội bộ minh họa):

| Thứ tự nhóm | Loại action |
|---:|---|
| 1 | `OrphanRemovalAction`: xóa orphan theo quy tắc mapping. |
| 2 | `EntityInsertAction` / `EntityIdentityInsertAction`: chèn entity. |
| 3 | `EntityUpdateAction`: cập nhật entity. |
| 4 | `QueuedOperationCollectionAction`: thao tác collection được queue. |
| 5 | `CollectionRemoveAction`: loại bỏ association/collection tương ứng. |
| 6 | `CollectionUpdateAction`: cập nhật collection. |
| 7 | `CollectionRecreateAction`: tái tạo collection. |
| 8 | `EntityDeleteAction`: xóa entity. |

Các tên trên phục vụ giải thích kiến trúc; không nên phụ thuộc vào chúng trong business code hoặc viết test buộc SQL phải theo đúng một thứ tự chi tiết. Giữa các entity cùng nhóm, Hibernate có thể sắp xếp lại khi bật ordering để phục vụ batch và xử lý quan hệ.

### Ví dụ: “xóa trước, thêm sau” trong Java vẫn có thể chèn trước

Giả sử bảng có khóa duy nhất trên `sku`:

~~~java
tx.begin();
InventoryItem oldItem = entityManager.find(InventoryItem.class, oldId);
entityManager.remove(oldItem);
entityManager.persist(new InventoryItem("SKU-CU", 5));
tx.commit();
~~~

Nếu `oldItem.sku` là `"SKU-CU"`, trong cùng flush Hibernate có thể chạy `INSERT` mới **trước** `DELETE` entity cũ. Unique constraint sẽ từ chối `INSERT`, dù thứ tự code gọi `remove()` trước `persist()`.

Nếu thực sự cần xóa rồi tái sử dụng giá trị unique ngay trong cùng transaction, có thể đặt **ranh giới flush chủ động**:

~~~java
tx.begin();
InventoryItem oldItem = entityManager.find(InventoryItem.class, oldId);
entityManager.remove(oldItem);
entityManager.flush(); // ép DELETE được gửi trước

entityManager.persist(new InventoryItem("SKU-CU", 5));
tx.commit();           // INSERT ở lần flush sau
~~~

Cách này chỉ giải quyết thứ tự gửi SQL trong transaction hiện tại, không thay thế thiết kế uniqueness/concurrency đúng đắn. Ràng buộc FK, cascade và database constraint có thể khiến cách sửa phù hợp khác đi. Trong các hệ quản trị hỗ trợ deferrable constraints, chính sách kiểm tra constraint cũng có thể ảnh hưởng hành vi.

### Thứ tự action phục vụ điều gì?

Trước hết, nó bảo đảm các nhóm thao tác ORM/collection được xử lý nhất quán. Khi tối ưu batching, Hibernate còn có thể nhóm các câu SQL tương tự để giảm số lần giao tiếp JDBC. Tuy vậy, quy tắc sắp xếp action **không có nghĩa Hibernate có thể giải mọi vòng phụ thuộc khóa ngoại**: mapping phải xác định đúng chủ sở hữu quan hệ; nhiều schema yêu cầu insert/update bổ sung, cấu hình nullable phù hợp hoặc thay đổi cách ghi.

## 7. Quan hệ entity: cascade, khóa ngoại và hành động collection

Giả sử bảng `purchase_order` có các dòng `purchase_order_line`; mỗi dòng chứa `order_id` tham chiếu đến đơn hàng.

~~~java
@Entity
@Table(name = "purchase_order")
class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    Long id;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    List<OrderLine> lines = new ArrayList<>();

    void addLine(OrderLine line) {
        lines.add(line);
        line.order = this; // cập nhật owning side
    }

    void removeLine(OrderLine line) {
        lines.remove(line);
        line.order = null;
    }
}

@Entity
@Table(name = "purchase_order_line")
class OrderLine {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    PurchaseOrder order; // owning side quyết định FK order_id

    String sku;
}
~~~

~~~java
PurchaseOrder order = new PurchaseOrder();
OrderLine line = new OrderLine();
line.sku = "BOOK-01";
order.addLine(line);

entityManager.persist(order); // cascade PERSIST tới line
entityManager.flush();
~~~

Một kết quả thường thấy là Hibernate chèn hàng của `purchase_order` trước rồi chèn hàng của `purchase_order_line` với `order_id` hợp lệ. Việc gán `line.order = this` có ý nghĩa quan trọng: `@ManyToOne` là **owning side** của foreign key. Chỉ thêm phần tử vào `order.lines` mà không thiết lập owning side có thể khiến FK thiếu/sai, dù danh sách trong Java nhìn có vẻ đúng.

Khi một dòng đang managed bị loại khỏi collection và `orphanRemoval = true`, Hibernate có thể lập lịch xóa dòng con tại flush. Cơ chế này khác với chỉ xóa phần tử khỏi một Java `ArrayList` không do Hibernate quản lý. Với quan hệ nhiều-nhiều hoặc collection dùng join table, SQL có thể tác động lên bảng nối thay vì trực tiếp update cột FK của entity đích.

**Đừng trộn lẫn ba khái niệm:**

- `CascadeType.PERSIST` / `REMOVE`: lan truyền thao tác vòng đời sang entity liên quan.
- `orphanRemoval = true`: xóa entity con khi bị loại khỏi quan hệ cha–con theo mapping tương ứng.
- `ON DELETE CASCADE` trong database: DB xóa bản ghi phụ thuộc khi nhận `DELETE`; Hibernate có thể dùng hoặc không biết hết các thay đổi do DB thực hiện, tùy mapping.

Hibernate quyết định SQL dựa trên **owning side, cascade, collection state, khóa ngoại và cấu hình mapping**, không chỉ dựa trên hình dạng object graph.

## 8. SQL được tạo và gửi qua JDBC như thế nào?

Với một `EntityUpdateAction`, Hibernate cần thông tin mapping như tên bảng, cột được ghi, identifier, version và giá trị field. Từ đó nó chuẩn bị SQL có placeholders:

~~~sql
update inventory_item
set quantity = ?, version = ?
where id = ? and version = ?
~~~

Sau đó Hibernate truyền tham số qua JDBC thay vì ghép trực tiếp giá trị vào chuỗi SQL:

~~~java
// Mã minh họa ý tưởng JDBC, không phải mã nguồn nội bộ của Hibernate:
PreparedStatement ps = connection.prepareStatement(
    "update inventory_item set quantity = ?, version = ? " +
    "where id = ? and version = ?"
);
ps.setInt(1, 17);
ps.setLong(2, 1L);
ps.setLong(3, 42L);
ps.setLong(4, 0L);
int affected = ps.executeUpdate();
~~~

Đường đi có thể khái quát:

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant PC as Persistence context
    participant AQ as ActionQueue
    participant JDBC as JDBC driver
    participant DB as Database

    App->>PC: persist(entity), sửa field
    Note over PC: Giữ managed state, theo dõi dirty
    App->>PC: flush() / commit()
    PC->>AQ: Chuẩn bị insert/update/delete actions
    AQ->>JDBC: Prepare SQL + bind parameters
    JDBC->>DB: executeUpdate() / executeBatch()
    DB-->>JDBC: affected rows / lỗi constraint
    JDBC-->>AQ: Kết quả
    AQ-->>PC: Hoàn tất flush hoặc ném exception
    App->>DB: commit/rollback qua transaction coordinator
~~~

Trong ứng dụng thực tế, transaction coordinator, SQL mutation executors, JDBC batching, connection management và driver có thêm các lớp trung gian. Sơ đồ cố ý giữ các ranh giới quan trọng.

### Vai trò của Dialect và prepared statement

Hibernate dùng dialect để biết cú pháp và khả năng riêng của DB: cách lấy sequence value, phân trang, xử lý khóa, returning/generation, kiểu dữ liệu, một số câu lệnh DML. Do đó cùng entity có thể tạo SQL khác nhau trên PostgreSQL và một hệ quản trị khác.

Prepared statement giúp tách **câu lệnh SQL** khỏi **giá trị bind**, hỗ trợ driver xử lý kiểu dữ liệu, giảm rủi ro SQL injection đối với tham số được bind đúng cách và cho phép JDBC statement/batch reuse theo khả năng driver. Điều này không có nghĩa mọi SQL là giống hệt giữa mọi database, hay Hibernate tự tối ưu mọi truy vấn.

### `@Version` và số hàng cập nhật

Trong ví dụ `InventoryItem` có `@Version`, Hibernate thường đưa version cũ vào điều kiện `WHERE` của `UPDATE` và tăng version khi ghi thành công. Nếu một transaction khác đã cập nhật/xóa hàng, lệnh có thể ảnh hưởng **0 hàng**; Hibernate phát hiện xung đột optimistic locking và ném exception thích hợp (ví dụ `OptimisticLockException` / stale state exception tùy API).

Ứng dụng phải xử lý exception bằng rollback/đóng session tương ứng, rồi quyết định retry transaction mới nếu nghiệp vụ cho phép. Sau lỗi SQL/flush, không nên giả định persistence context hiện tại vẫn ở trạng thái sạch để tiếp tục công việc như không có gì xảy ra.

## 9. SQL chạy lúc nào còn phụ thuộc cách sinh khóa chính

`@GeneratedValue` không chỉ quyết định giá trị ID; nó ảnh hưởng khả năng trì hoãn `INSERT` và gom batch.

| Chiến lược | Cách nhận ID thường gặp | Tác động lên thời điểm DML |
|---|---|---|
| `SEQUENCE` | Lấy giá trị từ database sequence; có thể dùng optimizer/pooled allocation. | Có thể lấy ID trước, giữ `INSERT` đến flush và tận dụng batch. |
| `IDENTITY` | DB sinh ID khi insert. | Thường phải insert sớm để nhận ID, khó gom JDBC batch cho insert entity đó; có ngoại lệ theo phiên bản và ngữ cảnh. |
| `TABLE` | Dùng bảng riêng cấp phát identifier. | Có thêm thao tác DB để cấp ID; chi phí/khóa tùy triển khai. |
| `UUID` hoặc ID tự cấp | Có thể tạo ở phía ứng dụng/provider. | Thường không phải chờ insert để biết ID, nhưng vẫn phụ thuộc mapping. |

Với `SEQUENCE`, việc nhìn thấy `select nextval(...)` sau `persist()` **không phải là lệnh insert entity**. Còn với `IDENTITY`, log có thể cho thấy insert xảy ra ngay để Hibernate có khóa chính phục vụ các thao tác tiếp theo.

Một ứng dụng cần insert hàng loạt nên kiểm tra chiến lược ID cùng với JDBC batching; chỉ cấu hình `hibernate.jdbc.batch_size` không bảo đảm mọi `INSERT` đều thành batch.

## 10. JDBC batching và sắp xếp các hành động

Nếu nhiều thao tác dùng SQL shape giống nhau, Hibernate có thể gom thành JDBC batch, giảm số lượt trao đổi với database:

~~~java
tx.begin();
for (int i = 0; i < 100; i++) {
    entityManager.persist(new InventoryItem("SKU-" + i, i));
}
tx.commit();
~~~

Ví dụ cấu hình Hibernate:

~~~properties
hibernate.jdbc.batch_size=30
hibernate.order_inserts=true
hibernate.order_updates=true
hibernate.generate_statistics=true
~~~

- `hibernate.jdbc.batch_size`: giới hạn quy mô batch JDBC mà Hibernate gom; 30 chỉ là giá trị minh họa, phải đo theo workload/driver.
- `hibernate.order_inserts`: cho phép sắp xếp inserts để tăng cơ hội cùng SQL được gom lại; thứ tự SQL giữa các entity có thể khác thứ tự `persist()`.
- `hibernate.order_updates`: cho phép sắp xếp updates, thường giúp batch hiệu quả hơn và trong một số workload giảm deadlock, nhưng không bảo đảm hết deadlock.
- `hibernate.generate_statistics`: cung cấp Hibernate statistics để quan sát khi kiểm tra hiệu năng; không nên bật vô điều kiện ở hệ thống nhạy cảm overhead.

Batch có thể bị chia khi SQL khác nhau (khác bảng, cột, mapping/dynamic SQL), driver không hỗ trợ thích hợp, flush xen kẽ, hoặc identifier generation yêu cầu insert sớm. `@DynamicUpdate` có thể giảm số cột ghi nhưng tạo nhiều dạng SQL khác nhau, làm khó batching; phải cân nhắc theo tải thực tế.

Với một vòng lặp hàng nghìn entity, persistence context cũng tích lũy object/snapshot. Chiến thuật xử lý theo lô có thể là:

~~~java
tx.begin();
for (int i = 0; i < 10_000; i++) {
    entityManager.persist(new InventoryItem("SKU-" + i, i));
    if (i > 0 && i % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
tx.commit();
~~~

`flush()` đẩy thao tác chờ xuống database; `clear()` tách các managed entity để giải phóng tài nguyên theo dõi. Chỉ dùng cặp này khi những object vừa bị tách không còn cần làm việc như managed ở phần còn lại của transaction. **Gọi `clear()` trước khi flush có thể làm mất những thay đổi chưa đồng bộ.** Trong mã thực tế cần xử lý transaction rollback và lựa chọn batch size dựa trên measurement.

## 11. SQL log: nhìn thấy câu lệnh chưa đủ để hiểu toàn bộ pipeline

Muốn xác nhận thời điểm Hibernate gửi SQL, cần quan sát cả SQL, bind parameters và transaction boundary. Ví dụ logging với Hibernate 6:

~~~properties
# Ví dụ cấu hình logger (cú pháp prefix phụ thuộc logging framework).
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Trong Spring Boot, các dòng ví dụ trên có thể đặt trong `application.properties`. Với Hibernate 5, tên logger bind parameter có thể khác (ví dụ logger của `BasicBinder`). Có thể dùng `hibernate.show_sql=true` để thử nhanh, nhưng structured logging thường phù hợp hơn để đối chiếu request, thread và transaction.

Ví dụ log có thể hiện:

~~~text
DEBUG org.hibernate.SQL : select nextval('inventory_item_seq')
DEBUG org.hibernate.SQL : insert into inventory_item (quantity,sku,version,id) values (?,?,?,?)
TRACE org.hibernate.orm.jdbc.bind : binding parameter (1:INTEGER) <- [15]
TRACE org.hibernate.orm.jdbc.bind : binding parameter (2:VARCHAR) <- [KB-01]
~~~

Tên logger, nội dung bind và SQL thực tế phụ thuộc phiên bản/driver/mapping. Log SQL có thể chứa dữ liệu nhạy cảm qua bind values: chỉ bật trace ở môi trường và thời điểm phù hợp với chính sách dữ liệu của hệ thống.

**Cách đọc log đúng:**

1. Xác định transaction và persistence context nào đang hoạt động.
2. Đánh dấu vị trí `persist()`, setter, query, `flush()`, commit.
3. Phân biệt `SELECT` để load entity / lấy sequence với `INSERT`, `UPDATE`, `DELETE`.
4. Kiểm tra bind values và điều kiện `WHERE`, đặc biệt ID, version, FK.
5. Đối chiếu batch execution và exception; số dòng SQL in ra không luôn tương ứng một-một với số lần round trip JDBC.

Khi cần quan sát chương trình sâu hơn, có thể dùng `StatementInspector` để xem SQL trước khi gửi, `Statistics` của Hibernate để kiểm tra số entity insert/update/delete, flush và statement, cùng metrics của connection pool/DB. Không nên suy ra thời điểm commit chỉ từ một dòng log `INSERT`.

## 12. Các tình huống dễ nhầm và cách phân tích

### 12.1. “`persist()` thành công nhưng database chưa có hàng”

Kiểm tra entity còn nằm trong persistence context không, transaction đã flush/commit chưa, generator ID có cấp giá trị sớm không, và công cụ kiểm tra DB đang xem từ **transaction khác** hay không. Với isolation thông thường, một transaction khác chưa chắc nhìn thấy dữ liệu chưa commit. Đừng lấy việc đã có `id` làm bằng chứng hàng đã được commit.

### 12.2. “Tôi không gọi `update()` nhưng lại có `UPDATE`”

Managed entity bị sửa sẽ được dirty checking phát hiện. Kiểm tra setter, mapper, callback entity, collection mutation, quá trình cascade và thời điểm flush. Với `@Version`, Hibernate còn quản lý phiên bản để phát hiện concurrent updates. JPA không yêu cầu ứng dụng gọi `update()` cho managed entity.

### 12.3. “Gọi `flush()` xong thì dữ liệu đã an toàn chưa?”

Chưa. Flush chỉ đồng bộ thao tác SQL trong transaction; transaction vẫn có thể rollback. Ngay cả `INSERT` đã thành công, lỗi ở câu SQL tiếp theo có thể buộc rollback toàn bộ giao dịch.

### 12.4. “Tôi sửa entity rồi chạy query, sao query làm SQL update?”

Với `AUTO` flush mode, Hibernate có thể flush trước query để tránh query đọc kết quả không nhất quán với những thay đổi pending. Kiểm tra query space, loại query (JPQL/HQL hay native), API `EntityManager`/`Session`, flush mode, và synchronization settings.

### 12.5. “Xóa trước rồi thêm cùng khóa unique mà vẫn lỗi”

ActionQueue thường xử lý nhóm insert trước nhóm entity delete. Nếu cần ranh giới xóa trước, dùng flush có chủ đích sau delete hoặc thiết kế lại thao tác nghiệp vụ để tránh tranh chấp unique; không dựa vào thứ tự gọi method Java.

### 12.6. “Tôi thay danh sách con nhưng DB không cập nhật FK”

Kiểm tra entity/collection có đang managed không, ai là owning side, có đặt quan hệ hai chiều nhất quán không, và loại cascade/orphan removal có đúng không. Với `@OneToMany(mappedBy = "...")`, phía `@ManyToOne` thường sở hữu FK.

### 12.7. “Tôi chạy JPQL bulk update nhưng entity đang load vẫn có giá trị cũ”

Bulk JPQL/HQL `UPDATE`/`DELETE` không đi qua dirty checking của từng managed entity như setter và có thể khiến trạng thái context **không còn khớp DB**. Cần chủ động xử lý flush trước bulk theo chiến lược transaction, rồi `clear()`/`refresh()` hoặc chuyển transaction khi thích hợp. Đừng giả định sửa SQL bulk sẽ tự cập nhật mọi object đã load.

### 12.8. “Sau lỗi constraint, có thể sửa entity và flush lại?”

Không nên tái sử dụng session/persistence context của transaction đã lỗi như thể mọi action/snapshot còn nhất quán. Cách an toàn là rollback transaction, kết thúc context hỏng và thực hiện lại nghiệp vụ trong transaction/context mới nếu cần.

## 13. Phân biệt các ranh giới dễ bị lẫn

| Hai khái niệm | Khác biệt cốt lõi |
|---|---|
| `persist()` và `flush()` | Đưa entity mới vào trạng thái được quản lý so với đồng bộ các thao tác ghi với DB. |
| `flush()` và `commit()` | Thực thi SQL trong transaction so với xác nhận transaction. |
| First-level cache và database | Đối tượng managed trong RAM có thể có giá trị chưa được lưu hoặc chưa commit. |
| Dirty checking và `UPDATE` | Dirty checking là phát hiện thay đổi; `UPDATE` là thao tác SQL có thể phát sinh sau đó. |
| `ActionQueue` và JDBC batch | ActionQueue điều phối nghiệp vụ ghi; batch là cơ chế JDBC gom các statement tương tự để giảm số lần thực thi/giao tiếp. |
| Cascade và action order | Cascade quyết định thao tác lan truyền đến object liên quan; action order quyết định nhóm SQL được thực thi khi flush. |
| JPQL bulk DML và managed entity mutation | Bulk DML thao tác trực tiếp theo câu query; managed mutation dựa vào persistence context và dirty checking. |
| SQL log và transaction thành công | Log SQL cho biết câu lệnh được chuẩn bị/thực thi; commit còn có thể thất bại hoặc transaction bị rollback. |

## 14. Thực hành tự kiểm chứng pipeline

Hãy sử dụng một database kiểm thử và bật log SQL + bind values, rồi lần lượt thực hiện:

**Thí nghiệm A — thay đổi trước flush**

~~~java
tx.begin();
InventoryItem item = new InventoryItem("EX-A", 1);
entityManager.persist(item);
item.increase(1);
item.increase(1);
entityManager.flush();
tx.commit();
~~~

Dự đoán: với `SEQUENCE` thường có thao tác lấy ID và **một `INSERT`** ghi `quantity = 3`; không nhất thiết có hai `UPDATE` chỉ vì gọi `increase()` hai lần.

**Thí nghiệm B — thay đổi sau flush**

~~~java
tx.begin();
InventoryItem item = new InventoryItem("EX-B", 1);
entityManager.persist(item);
entityManager.flush(); // INSERT quantity = 1
item.increase(2);
tx.commit();           // UPDATE quantity = 3
~~~

Dự đoán: thường có `INSERT` ở flush đầu và `UPDATE` ở flush khi commit.

**Thí nghiệm C — flush rồi rollback**

~~~java
tx.begin();
entityManager.persist(new InventoryItem("EX-C", 7));
entityManager.flush(); // INSERT có thể đã chạy
tx.rollback();         // hủy thay đổi của transaction
~~~

Dự đoán: log có thể hiện `INSERT` đã gửi, nhưng khi đọc lại trong transaction mới, hàng `EX-C` không tồn tại. Giá trị đã cấp bởi sequence có thể không được hoàn lại sau rollback; chuyện đó khác với tính nguyên tử của insert.

**Thí nghiệm D — tác động của unique constraint**

Tạo một hàng với `sku = "EX-D"`, rồi trong transaction mới `remove()` hàng ấy và `persist()` một hàng mới cũng có `sku = "EX-D"`. Quan sát thứ tự SQL và lỗi unique (nếu có). Lặp lại với `flush()` giữa hai thao tác để hiểu vì sao ranh giới flush thay đổi thứ tự SQL được gửi.

Các dự đoán cần được kiểm chứng với phiên bản Hibernate, database, flush mode, mapping và cấu hình thực tế của dự án. Mục tiêu là phân biệt **thời điểm đổi object**, **thời điểm tạo/thực thi action**, và **thời điểm transaction được commit**.

## 15. Cách suy luận khi gặp một SQL “bất ngờ”

Khi phân tích bất kỳ `INSERT`, `UPDATE` hoặc `DELETE` nào do Hibernate phát ra, hãy lần theo chuỗi câu hỏi:

1. **Entity ở trạng thái nào?** Transient, managed, detached hay removed? Persistence context nào quản lý nó?
2. **Thao tác nào đã làm thay đổi trạng thái?** `persist()`, setter, merge, remove, cascade hay collection change?
3. **Điều gì kích hoạt flush?** Explicit flush, commit, query, hay framework?
4. **Hành động thuộc nhóm nào trong ActionQueue?** Insert, update, delete hay collection/orphan action? Có bị sắp xếp lại không?
5. **Mapping tạo SQL nào?** Bảng/cột, owning side FK, identifier strategy, version và dialect?
6. **JDBC thực thi ra sao?** Statement thường hay batch, bind values nào, affected rows bao nhiêu?
7. **Transaction kết thúc thế nào?** Commit, rollback, constraint violation hay optimistic-lock conflict?

Chuỗi suy luận này giải thích phần lớn hành vi ghi dữ liệu của Hibernate: **Java object biểu diễn trạng thái mong muốn, persistence context theo dõi trạng thái đó, flush chuyển thành các hành động có thứ tự, JDBC gửi SQL, còn database và transaction quyết định kết quả cuối cùng.**
