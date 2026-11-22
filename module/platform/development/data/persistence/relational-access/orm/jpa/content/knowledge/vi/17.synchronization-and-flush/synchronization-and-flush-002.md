# Phân biệt persist, flush và commit trong JPA

Trong **Jakarta Persistence (JPA)**, thao tác tạo hoặc sửa một entity trong Java không đồng nghĩa cơ sở dữ liệu đã ghi bền vững ngay lập tức. JPA duy trì một **persistence context** để quản lý các entity, theo dõi thay đổi và đồng bộ chúng với database trong phạm vi transaction. Ba thao tác thường bị nhầm lẫn là:

- **`EntityManager.persist(entity)`**: yêu cầu đưa một entity mới vào trạng thái **managed** trong persistence context, để nó được lưu xuống database theo vòng đời JPA.
- **`EntityManager.flush()`**: yêu cầu provider **đồng bộ các thay đổi đang chờ** từ persistence context thành các thao tác SQL phù hợp, nhưng **không kết thúc transaction**.
- **`commit()`**: hoàn tất **transaction**; khi thành công, các thay đổi của transaction được commit tại database. Trong transaction bình thường, provider phải đồng bộ các thay đổi còn chờ trước khi giao dịch hoàn tất.

Cách ghi nhớ là: **persist thay đổi trạng thái quản lý entity; flush đồng bộ SQL; commit xác nhận transaction**. Đây là ba khái niệm liên quan nhưng không hoán đổi được.

Bài học giải thích chúng dưới góc nhìn **Data Persistence, Relational Access, ORM JPA**, chương **Đồng bộ và flush**: thời điểm sinh SQL, lúc có khóa chính, cách phát hiện vi phạm constraint, ảnh hưởng của rollback, việc JPQL kích hoạt flush tự động, và cách tổ chức transaction an toàn trong Java SE, Jakarta EE hoặc Spring.

## 1. Ba thao tác nằm ở ba lớp trách nhiệm khác nhau

Hãy hình dung một ứng dụng bán hàng tạo một đơn hàng mới:

~~~text
Java application
     |
     | new PurchaseOrder(...)
     v
Transient Java object
     |
     | em.persist(order)
     v
Persistence context
     |   - theo dõi một managed entity
     |   - quản lý thay đổi cần lưu
     |   - có thể yêu cầu cấp ID
     |
     | em.flush() hoặc provider tự flush
     v
SQL chạy trong transaction của database
     |   INSERT / UPDATE / DELETE
     |   constraint có thể được kiểm tra
     |   dữ liệu có thể nhìn thấy trong transaction này
     |   CHƯA nhất thiết được commit
     |
     | transaction.commit()
     v
Database commit
     |   transaction thành công
     v
Dữ liệu đã commit
~~~

**Lưu ý:** sơ đồ thể hiện trách nhiệm logic, không phải lịch phát SQL bất biến. Với một số chiến lược cấp ID, provider có thể phát `INSERT` ngay trong hoặc sau `persist()`; với những thao tác khác, provider có thể trì hoãn tới flush/commit.

| Thao tác | Đối tượng chịu tác động | Ý nghĩa chính | Có bắt buộc kết thúc transaction? |
| --- | --- | --- | --- |
| `new PurchaseOrder(...)` | Object Java | Tạo object mới, chưa do JPA quản lý | Không |
| `em.persist(order)` | Persistence context | Biến entity mới thành managed; đánh dấu cần lưu | Không |
| `em.flush()` | Persistence context → database | Đồng bộ những thay đổi cần thiết thành SQL | Không |
| `em.getTransaction().commit()` | Transaction resource-local | Commit giao dịch, sau khi các thay đổi cần thiết được đồng bộ | **Có** |
| `em.getTransaction().rollback()` | Transaction resource-local | Hủy các thay đổi thuộc giao dịch chưa commit | **Có**, theo hướng rollback |

Trong môi trường Spring hoặc Jakarta EE có transaction manager, việc commit thường do **framework/container** thực hiện, không phải gọi `em.getTransaction().commit()` trực tiếp.

## 2. Mô hình ví dụ: entity PurchaseOrder

Để minh họa, dùng một entity đơn giản với khóa `Long` và một mã đơn duy nhất.

~~~java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "order_seq")
    @jakarta.persistence.SequenceGenerator(
        name = "order_seq",
        sequenceName = "purchase_order_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true, length = 40)
    private String orderCode;

    @Column(name = "status", nullable = false, length = 30)
    private String status = "DRAFT";

    protected PurchaseOrder() {
        // Constructor dành cho JPA.
    }

    public PurchaseOrder(String orderCode) {
        this.orderCode = Objects.requireNonNull(orderCode);
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public String getStatus() {
        return status;
    }

    public void confirm() {
        if (!"DRAFT".equals(status)) {
            throw new IllegalStateException(
                "Only draft orders can be confirmed");
        }
        status = "CONFIRMED";
    }
}
~~~

Schema PostgreSQL tương ứng:

~~~sql
CREATE SEQUENCE purchase_order_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    order_code VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL
);
~~~

Ví dụ dùng `GenerationType.SEQUENCE` để tách rõ **cấp ID** khỏi **INSERT bản ghi**. `em.persist(order)` có thể làm provider lấy giá trị sequence để đặt ID, nhưng không nhất thiết đã phát câu `INSERT` cho đơn hàng.

Nếu chạy trên database không hỗ trợ sequence, phải chọn chiến lược ID tương thích. Điểm cần học về `persist`, `flush` và `commit` vẫn giữ nguyên, dù thời điểm SQL cụ thể có thể khác.

## 3. persist(): đưa entity mới vào trạng thái managed

### 3.1. Từ transient sang managed

Khi vừa tạo:

~~~java
PurchaseOrder order = new PurchaseOrder("ORD-2026-001");
~~~

`order` là object Java bình thường, thuộc trạng thái **new/transient**, chưa là entity managed của `EntityManager`.

Sau khi gọi:

~~~java
em.persist(order);
~~~

JPA làm cho entity mới **managed** trong persistence context hiện hành (với các quy tắc và điều kiện transaction tương ứng). Provider sẽ bảo đảm thao tác INSERT cần thiết được thực hiện trong quá trình đồng bộ.

Một đặc điểm quan trọng: **`persist()` là thao tác trên entity mới**, không phải cách “lưu tất cả object bất kỳ” hay “ép SQL INSERT chạy ngay”.

### 3.2. Ví dụ kiểm tra trạng thái managed

~~~java
em.getTransaction().begin();

PurchaseOrder order = new PurchaseOrder("ORD-2026-001");

boolean before = em.contains(order); // false
em.persist(order);
boolean after = em.contains(order);  // true

em.getTransaction().commit();
~~~

`EntityManager.contains(entity)` trả lời entity đó hiện có được context này quản lý hay không. Nó **không cho biết bản ghi đã commit** và cũng không phải công cụ kiểm tra SQL đã chạy.

Trong một transaction đang hoạt động, entity mới được persist thành managed và những thay đổi đối với entity đó tiếp tục được provider theo dõi.

### 3.3. persist không tương đương INSERT tức thì

Một cách suy luận sai:

~~~java
em.persist(order);

// Không thể kết luận trong mọi provider:
// "Lệnh INSERT đã hoàn thành và người khác đã đọc được order".
~~~

Có thể chưa có `INSERT`. Ngay cả khi đã có `INSERT`, transaction vẫn chưa commit, nên một transaction bên ngoài thường chưa thấy bản ghi theo mức isolation thông dụng.

Trường hợp `GenerationType.IDENTITY` có thể làm provider cần INSERT sớm để lấy ID. Trường hợp `SEQUENCE` có thể lấy ID trước khi INSERT. Không rút ra quy tắc “persist không bao giờ chạm database” hoặc “persist luôn ghi database ngay”.

### 3.4. persist không áp dụng cho entity detached như entity mới

Nếu một entity đã từng được persist, rồi detached, gọi `persist(detachedEntity)` không phải thao tác chuẩn để cập nhật nó; provider có thể ném ngoại lệ liên quan đến entity đã tồn tại, đôi khi chỉ tại flush.

Khi cần cập nhật một entity đã có dữ liệu, nên tìm entity managed rồi sửa:

~~~java
PurchaseOrder managed =
    em.find(PurchaseOrder.class, existingId);

managed.confirm();
~~~

Hoặc cân nhắc `merge` khi làm việc với detached state, và nhớ rằng `merge` trả về **managed instance**, không biến nhất thiết chính detached instance thành managed.

~~~java
PurchaseOrder managedCopy = em.merge(detachedOrder);
// Sử dụng managedCopy cho các thao tác sau đó.
~~~

`persist` và `merge` có mục đích khác nhau; cả hai đều **không thay thế transaction commit**.

## 4. flush(): đồng bộ persistence context với database

### 4.1. Flush làm gì?

`em.flush()` yêu cầu provider xử lý những thay đổi cần đồng bộ từ context sang database. Chúng có thể bao gồm:

- `INSERT` cho entity mới đã được persist.
- `UPDATE` cho các managed entity có thuộc tính thay đổi.
- `DELETE` cho các entity được đánh dấu remove.
- Các thao tác liên quan tới collection, khóa ngoại, bảng liên kết và thứ tự phần tử.

Ví dụ:

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    new PurchaseOrder("ORD-2026-002");

em.persist(order);
em.flush(); // Đồng bộ những thay đổi đang chờ thành SQL.

em.getTransaction().commit();
~~~

Sau `flush()` thành công, các lệnh cần thiết tại thời điểm đó đã được gửi và thực thi trong transaction hiện hành. **Điều này không có nghĩa transaction đã commit**.

### 4.2. Flush không xóa persistence context

Sau `flush()`, entity vẫn có thể managed:

~~~java
em.getTransaction().begin();

PurchaseOrder order = new PurchaseOrder("ORD-2026-003");
em.persist(order);

em.flush();
boolean stillManaged = em.contains(order); // true

order.confirm();
em.flush(); // Đồng bộ thay đổi tiếp theo nếu cần.

em.getTransaction().commit();
~~~

Flush không phải `clear()` và không phải `detach()`. Entity vẫn thuộc persistence context; provider tiếp tục dirty checking các thay đổi xảy ra sau flush.

### 4.3. SQL minh họa

Với `SEQUENCE` trong ví dụ:

~~~text
begin transaction

persist(order)
  -> có thể SELECT nextval(...) để lấy ID

flush()
  -> INSERT INTO purchase_orders
       (id, order_code, status)
       VALUES (?, 'ORD-2026-003', 'DRAFT')

order.confirm()

flush()
  -> UPDATE purchase_orders
       SET status = 'CONFIRMED'
       WHERE id = ?

commit()
  -> COMMIT
~~~

Đây là **trình tự minh họa**, không phải SQL bắt buộc ở mọi provider. ORM có thể chọn thời điểm và hình thức SQL khác tùy trạng thái thực tế, batching, mapping và cấu hình.

### 4.4. Flush không đảm bảo mọi kiểm tra nghiệp vụ đã xong

Một `flush` thành công thường cho thấy các SQL đã thực thi không bị từ chối bởi các constraint kiểm tra tại thời điểm đó. Nhưng không phải mọi kiểm tra đều xảy ra ngay:

- Một số FK hoặc unique constraint trên database có thể được **defer** tới commit nếu schema hỗ trợ.
- Các quy tắc nghiệp vụ do ứng dụng kiểm tra có thể chưa được thực thi.
- Transaction khác có thể gây xung đột hoặc thay đổi tình trạng dữ liệu.
- Một lỗi I/O, khóa, serialization hoặc transaction có thể chỉ xuất hiện về sau.

Do đó **flush thành công chưa phải bằng chứng commit chắc chắn thành công**.

## 5. commit(): hoàn tất transaction

### 5.1. Commit chốt thay đổi của một giao dịch

Trong môi trường resource-local:

~~~java
em.getTransaction().begin();

PurchaseOrder order = new PurchaseOrder("ORD-2026-004");
em.persist(order);

// Không bắt buộc gọi em.flush() thủ công ở đây.
em.getTransaction().commit();
~~~

Với transaction được commit bình thường, provider cần bảo đảm các thay đổi đang chờ được đồng bộ với database khi giao dịch hoàn tất. Vì vậy chương trình **không nhất thiết phải gọi `flush()` trước `commit()`**.

Commit có ý nghĩa lớn hơn flush:

1. Làm việc với **toàn bộ thay đổi thuộc transaction**, không chỉ một entity.
2. Kết thúc transaction thành công khi database chấp nhận.
3. Xác lập tính bền vững của dữ liệu đã commit theo cơ chế giao dịch của database.
4. Cho phép transaction khác nhìn thấy dữ liệu đã commit theo isolation/visibility thích hợp.

`EntityManager` có thể tiếp tục được sử dụng sau commit nếu vẫn mở, nhưng transaction vừa rồi đã kết thúc. Các thay đổi tiếp theo cần transaction phù hợp để được ghi xuống DB.

### 5.2. Commit không phải phương thức của EntityManager

Đây là cách dùng trong **resource-local transaction**:

~~~java
em.getTransaction().commit();
~~~

Không tồn tại lời gọi `em.commit()` trong API `EntityManager` chuẩn.

Với **JTA**, transaction thường do container hoặc `UserTransaction`/transaction manager điều phối. Trong Spring, `@Transactional` thường giao việc begin/commit/rollback cho framework. Không nên trộn `EntityManager.getTransaction()` với một `EntityManager` do JTA/container quản lý.

### 5.3. Trạng thái database trước và sau commit

Giả sử hai kết nối database dùng mức isolation thông thường như `READ COMMITTED`:

~~~text
Transaction A                       Transaction B
-----------------------------       -------------------------------
BEGIN
persist new Order
flush -> INSERT order
                                    SELECT Order by ID
                                    -> thường chưa thấy hàng chưa commit

COMMIT
                                    SELECT Order by ID (lần mới)
                                    -> có thể thấy hàng đã commit
~~~

SQL INSERT đã chạy trong transaction A, nhưng **quyền nhìn thấy các thay đổi chưa commit** ở transaction B phụ thuộc isolation của database và hệ thống; phần lớn môi trường production không cho phép dirty read ở mức isolation thông dụng.

Nếu transaction B đang dùng snapshot được giữ qua nhiều lần SELECT, nó có thể vẫn chưa thấy dữ liệu mới dù A đã commit. Không nên khẳng định “commit làm mọi transaction đang mở ngay lập tức nhìn thấy thay đổi”; còn tùy isolation và snapshot.

## 6. Bảng so sánh persist, flush và commit

| Tiêu chí | `persist` | `flush` | `commit` |
| --- | --- | --- | --- |
| Phạm vi | Entity mới và cascade persist | Những thay đổi pending của persistence context | Toàn transaction |
| Mục đích | Đưa entity mới vào managed state | Đồng bộ thay đổi với DB | Hoàn tất giao dịch |
| Có thể phát SQL? | **Có thể**, tùy provider/ID strategy | **Có**, khi có thay đổi cần đồng bộ | **Có thể**, nếu còn thay đổi chưa flush |
| Bắt buộc có INSERT? | Không nhất thiết ngay lúc gọi | Không nếu context không có thay đổi cần INSERT | Không nếu giao dịch không tạo bản ghi |
| Có kết thúc transaction? | Không | Không | Có |
| Có làm dữ liệu visible cho transaction khác? | Không tự bảo đảm | Không tự bảo đảm | Theo quy tắc isolation sau khi commit thành công |
| Có thể rollback sau đó? | Có, nếu transaction chưa commit | Có, nếu transaction chưa commit | Không rollback transaction đã commit |
| Entity còn managed? | Có trong context phù hợp | Có | Phụ thuộc lifetime của `EntityManager`; context có thể tiếp tục tồn tại hoặc kết thúc theo cấu hình |
| Dùng cho entity đã tồn tại? | Không dùng để cập nhật detached entity theo kiểu “save” | Đồng bộ cả các managed entity bị thay đổi | Commit mọi thao tác của transaction |
| Vị trí trong API | `EntityManager.persist` | `EntityManager.flush` | `EntityTransaction.commit` hoặc transaction manager |

Câu hỏi quyết định là **“Tôi muốn JPA bắt đầu quản lý đối tượng, muốn DB xử lý thay đổi đang chờ, hay muốn kết thúc giao dịch?”** Mỗi mong muốn ứng với một thao tác khác nhau.

## 7. Ví dụ hoàn chỉnh: tạo đơn hàng bằng EntityManager

Đây là ví dụ Java SE với `EntityManagerFactory` ứng với một persistence unit `shopPU` đã được khai báo trong `persistence.xml`. Giả định database, JDBC driver và JPA provider đã được cấu hình đúng.

~~~java
package com.example.shop;

import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

public final class CreateOrderExample {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("shopPU");

        try {
            createOrder(emf, "ORD-2026-005");
        } finally {
            emf.close();
        }
    }

    private static void createOrder(
            EntityManagerFactory emf,
            String code) {

        EntityManager em = emf.createEntityManager();

        try {
            em.getTransaction().begin();

            PurchaseOrder order = new PurchaseOrder(code);

            em.persist(order);
            System.out.println(
                "Managed after persist: " + em.contains(order));

            em.flush();
            System.out.println(
                "ID after flush: " + order.getId());

            order.confirm();

            em.getTransaction().commit();
            System.out.println(
                "Committed order: " + order.getId());

        } catch (RuntimeException ex) {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Trong quy trình trên:

1. Bắt đầu transaction trước khi thực hiện thay đổi database.
2. Tạo entity mới bằng constructor.
3. Gọi `persist` để đăng ký entity mới.
4. Gọi `flush` tường minh để yêu cầu SQL cho các thay đổi hiện tại được xử lý.
5. Sửa `status` của managed entity; dirty checking theo dõi thay đổi.
6. Gọi `commit`, provider đồng bộ những thay đổi còn chờ và hoàn tất transaction.
7. Nếu có lỗi, rollback transaction đang hoạt động và đóng `EntityManager`.

**Trong ứng dụng thực tế không cần cố ý gọi flush sau mỗi persist.** Ví dụ có flush để làm rõ ranh giới. Nếu không cần kiểm tra constraint sớm hoặc thao tác SQL đặc biệt theo từng giai đoạn, thường để provider tự flush ở thời điểm cần thiết là phù hợp hơn.

## 8. Rollback sau flush: SQL đã chạy nhưng không được commit

Đây là trường hợp giúp phân biệt flush và commit rõ nhất.

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    new PurchaseOrder("ORD-ROLLBACK-001");

em.persist(order);
em.flush(); // INSERT có thể đã chạy thành công.

em.getTransaction().rollback(); // Hủy giao dịch.
~~~

Sau rollback, bản ghi chèn trong transaction không trở thành bản ghi được commit. Khi thực hiện một giao dịch mới tìm theo khóa đó, không nên kỳ vọng thấy đơn hàng vừa bị rollback.

~~~text
BEGIN
  persist(order)
  flush()
    -> INSERT INTO purchase_orders (...)
  -- database hiện có thay đổi chưa commit trong transaction A
ROLLBACK
  -> thay đổi INSERT bị hủy
~~~

Điều quan trọng:

- **Rollback có thể hủy các thay đổi đã flush**, miễn chúng còn thuộc transaction chưa commit.
- Rollback **không đảo ngược những hiệu ứng ngoài transaction** như email đã gửi, HTTP request gọi dịch vụ ngoài hoặc ghi log ở hệ thống độc lập.
- Với một số database, giá trị sequence/identity đã cấp có thể **không được thu hồi** khi rollback. Vì vậy có khoảng trống trong ID là điều bình thường.
- Object Java có thể vẫn giữ giá trị ID đã được cấp trước rollback, nhưng điều đó không chứng minh bản ghi tồn tại trong database.

### 8.1. Vì sao không nên tái sử dụng object sau rollback một cách tùy tiện?

Sau rollback, các entity từng được managed có thể mang trạng thái Java không khớp database. Tùy loại persistence context và điều kiện rollback, các instance có thể trở thành detached hoặc không còn an toàn để tiếp tục dùng như trước.

Cách tiếp cận rõ ràng là kết thúc thao tác, đóng hoặc làm mới persistence context theo mô hình ứng dụng, rồi **tải lại dữ liệu trong transaction mới** nếu cần. Không gọi `commit` lại trên cùng transaction đã rollback.

## 9. Thời điểm có ID không phải dấu mốc commit

Nhiều lập trình viên dựa vào `getId()` để suy luận dữ liệu đã lưu:

~~~java
em.persist(order);
System.out.println(order.getId());
~~~

Đây là suy luận không đáng tin. Thời điểm ID có giá trị phụ thuộc chiến lược khóa.

### 9.1. GenerationType.SEQUENCE

~~~java
@Id
@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "order_seq")
private Long id;
~~~

Provider có thể lấy giá trị sequence trước khi chèn bản ghi:

~~~text
persist(order)
    -> SELECT nextval('purchase_order_seq')
    -> order.id = 1201
    -> INSERT có thể còn chờ tới flush
~~~

ID có giá trị **không đồng nghĩa INSERT đã chạy**, càng không đồng nghĩa transaction đã commit.

### 9.2. GenerationType.IDENTITY

~~~java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
~~~

Với IDENTITY, database thường là nơi cấp ID tại INSERT. Provider có thể phải chèn sớm để nhận generated key. Vì vậy ngay sau `persist()`, SQL INSERT **có thể** đã chạy, nhưng vẫn thuộc transaction chưa commit.

### 9.3. UUID hoặc khóa do ứng dụng cấp

Với khóa tự cấp:

~~~java
@Id
private java.util.UUID id;

public PurchaseOrder(java.util.UUID id) {
    this.id = id;
}
~~~

Entity có ID ngay khi được tạo bằng constructor, thậm chí **trước cả `persist()`**. Tương tự, từ Jakarta Persistence 3.1 có `GenerationType.UUID` để yêu cầu provider sinh UUID, nhưng thời điểm cấp giá trị phụ thuộc vào hoạt động của provider.

Bảng tổng hợp:

| Trường hợp | Lúc ID có thể xuất hiện | Chứng minh đã commit không? |
| --- | --- | --- |
| SEQUENCE | Có thể trước INSERT | Không |
| IDENTITY | Thường gắn với INSERT để lấy khóa | Không |
| UUID do ứng dụng tạo | Ngay khi xây object | Không |
| UUID do provider tạo | Theo chiến lược provider | Không |
| Assigned ID | Trước persist nếu ứng dụng đã gán | Không |

Muốn xác nhận một thay đổi đã commit, phải xét kết quả **transaction commit**, không chỉ trạng thái ID hoặc việc `flush` không báo lỗi.

## 10. Dirty checking: UPDATE không cần persist lại

Khi entity đang managed, JPA theo dõi những thay đổi đối với các thuộc tính có mapping và thực hiện đồng bộ phù hợp.

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.confirm();

em.getTransaction().commit();
~~~

Trong ví dụ trên **không cần `em.persist(order)`**. Entity đã managed từ `find`; việc thay đổi `status` đủ để provider phát UPDATE khi flush/commit theo dirty checking.

Nếu muốn kiểm tra SQL hoặc constraint trước thời điểm commit:

~~~java
order.confirm();
em.flush();
~~~

Điều đó làm provider đồng bộ pending UPDATE. Tuy nhiên transaction vẫn chưa hoàn tất, và sửa thêm entity sau flush có thể dẫn tới một lượt đồng bộ tiếp theo.

### 10.1. Cập nhật nhiều lần trước flush

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.confirm();

// Giả sử có những thay đổi managed khác trước flush.
em.flush();

em.getTransaction().commit();
~~~

Provider thường tính chênh lệch trạng thái từ managed entity và quyết định SQL cần thiết. Không suy luận “mỗi lần setter được gọi sẽ phát một UPDATE”, cũng không suy luận “flush luôn cập nhật đúng từng cột đã sửa”. SQL và tối ưu dirty checking phụ thuộc provider, mapping và cấu hình.

## 11. Flush có thể xảy ra tự động

JPA có `FlushModeType` giúp điều khiển khi nào provider cần đồng bộ những thay đổi pending so với việc thực hiện truy vấn.

### 11.1. FlushModeType.AUTO

`AUTO` là chế độ mặc định phổ biến của JPA. Khi một truy vấn trong transaction cần nhìn thấy các cập nhật đang chờ của persistence context, provider có trách nhiệm bảo đảm hiệu ứng của các cập nhật đó được phản ánh theo ngữ nghĩa của truy vấn.

Ví dụ:

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    new PurchaseOrder("ORD-2026-006");
em.persist(order);

Long count = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    Long.class
)
.setParameter("code", "ORD-2026-006")
.getSingleResult();

em.getTransaction().commit();
~~~

Trong `AUTO`, provider có thể **flush trước truy vấn** để kết quả phù hợp với thay đổi pending. Tuy nhiên, không phải mọi truy vấn đều yêu cầu một SQL flush mới; provider có thể quyết định không flush nếu vẫn bảo đảm hiệu ứng đúng. Vì vậy không có quy tắc “mọi `SELECT` đều flush”.

### 11.2. FlushModeType.COMMIT

Có thể đặt:

~~~java
em.setFlushMode(jakarta.persistence.FlushModeType.COMMIT);
~~~

Với `COMMIT`, provider không bắt buộc đồng bộ pending changes trước mọi query. Theo đặc tả, ảnh hưởng của thay đổi đang chờ lên kết quả truy vấn trước commit có thể **không được xác định đồng nhất** theo cách bạn mong muốn.

Không nên dựa vào một kết quả COUNT tạm thời khi chưa flush rồi suy luận rằng database không có bản ghi. Nếu nghiệp vụ yêu cầu query nhìn thấy thay đổi, cần hiểu flush mode và thực hiện flush có chủ đích trong transaction phù hợp.

### 11.3. Đặt flush mode ở query

Một số query có thể đặt riêng:

~~~java
var query = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o",
    Long.class
);

query.setFlushMode(
    jakarta.persistence.FlushModeType.AUTO
);
~~~

Lựa chọn này giúp điều khiển cách query tương tác với pending changes. Nó **không commit** transaction và không thay thế cơ chế quản lý nhất quán dữ liệu.

| Chế độ | Định hướng | Điều không nên kết luận |
| --- | --- | --- |
| `AUTO` | Bảo đảm kết quả truy vấn phản ánh thay đổi pending theo hợp đồng JPA | “Mỗi SELECT luôn phát toàn bộ SQL pending ngay trước nó” |
| `COMMIT` | Đồng bộ trước hoàn tất transaction, ít yêu cầu flush trước truy vấn | “Query luôn bỏ qua hoặc luôn thấy mọi thay đổi pending” |
| Gọi `em.flush()` | Ép đồng bộ pending changes trong transaction hiện tại | “Là commit” |

### 11.4. Flush mode không thay thế transaction isolation

Dù provider flush trước SELECT, những transaction khác không vì vậy tự động thấy dữ liệu chưa commit. `FlushModeType` là một cơ chế phía JPA quản lý **thời điểm đồng bộ**, còn **transaction isolation** là một cơ chế database kiểm soát visibility và concurrency.

## 12. Kiểm tra constraint: tại flush hay commit?

Giả sử `order_code` có unique constraint:

~~~sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uk_purchase_orders_code
UNIQUE (order_code);
~~~

Hai đơn hàng cùng mã sẽ vi phạm:

~~~java
em.getTransaction().begin();

em.persist(new PurchaseOrder("DUPLICATE-001"));
em.persist(new PurchaseOrder("DUPLICATE-001"));

// Yêu cầu provider đồng bộ các INSERT.
em.flush();
~~~

Với unique constraint được kiểm tra ngay khi INSERT, lỗi có thể xảy ra tại `flush()`. Nhưng cũng có trường hợp:

- Provider phát INSERT sớm hơn, ví dụ do IDENTITY.
- Provider chưa flush đến tận commit.
- Database hỗ trợ deferred constraint nên chỉ phát hiện ở commit.
- Lỗi được bọc trong exception của provider, JPA hoặc transaction manager.

Điểm cần hiểu là **nơi exception nổi lên không nhất thiết là nơi trạng thái Java gây lỗi được tạo ra**.

### 12.1. Flush sớm để phát hiện lỗi có chủ đích

Một service có thể cần kiểm tra lỗi DB trước khi bước xử lý tiếp theo chạy:

~~~java
em.getTransaction().begin();

try {
    em.persist(new PurchaseOrder(code));
    em.flush(); // Có thể phát hiện lỗi constraint kiểm tra ngay.

    // Tiếp tục những bước cần transaction còn hợp lệ.

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
}
~~~

Chủ động flush có ích nếu cần sớm phát hiện lỗi FK/UNIQUE/NOT NULL, nhưng **không đảm bảo mọi lỗi được phát hiện trước commit**.

Quan trọng hơn, **sau khi flush gặp lỗi SQL, transaction có thể đã ở trạng thái rollback-only hoặc không thể tiếp tục**. Không nên bắt lỗi unique rồi tự ý tiếp tục dùng cùng transaction để ghi dữ liệu khác. Hãy rollback và bắt đầu transaction mới khi thích hợp.

### 12.2. Constraint của database vẫn là nguồn bảo vệ cuối

Kiểm tra trước bằng JPQL:

~~~java
Long existing = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.orderCode = :code
    """,
    Long.class
).setParameter("code", code)
 .getSingleResult();
~~~

không thể thay thế ràng buộc UNIQUE: hai transaction có thể cùng thấy COUNT = 0 rồi đồng thời INSERT cùng mã. DB constraint vẫn cần thiết để bảo vệ dữ liệu khi có cạnh tranh.

## 13. Vì sao có thể flush nhiều lần trong một transaction?

Một transaction có thể trải qua nhiều giai đoạn:

~~~text
BEGIN
  persist(order)
  flush()           -- chèn order, có ID để liên kết
  persist(lineA)
  persist(lineB)
  flush()           -- chèn lineA, lineB theo quan hệ
  order.confirm()
  flush()           -- cập nhật status của order
COMMIT
~~~

Mỗi flush đồng bộ **trạng thái pending tại thời điểm được gọi**, nhưng không “khóa” persistence context thành read-only. Sau đó, ứng dụng có thể tiếp tục thay đổi entity managed.

Đổi lại, flush thường xuyên có thể:

- Tăng số lần đồng bộ SQL và round-trip.
- Làm giảm cơ hội batching/gom UPDATE của provider.
- Kích hoạt constraint sớm hơn.
- Khiến transaction giữ khóa database trong thời gian dài hơn.
- Làm code phụ thuộc nhiều hơn vào thứ tự SQL.

Vì vậy **không cần flush sau từng setter hoặc từng persist**. Mặc định thường ưu tiên gom những thay đổi liên quan trong **một transaction**, để JPA flush đúng lúc. Chỉ chủ động flush khi có lý do về tính đúng đắn, constraint hoặc phối hợp truy vấn.

## 14. Quan hệ parent–child và thứ tự SQL

Một trường hợp thường cần đánh giá flush là tạo entity cha có nhiều entity con. Ví dụ:

~~~text
purchase_orders
   id (PK)
      |
      +--- order_lines.order_id (FK, NOT NULL)
~~~

Model hai chiều:

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

    // Các field và constructor khác...
}
~~~

Tại parent:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines = new ArrayList<>();
~~~

Khi gọi:

~~~java
order.addLine(line);
em.persist(order);
~~~

cần bảo đảm:

1. `order.addLine(line)` thiết lập cả hai phía, nhất là **`line.order` ở owning side**.
2. `cascade = PERSIST` giúp cascade persist từ parent sang child, nếu muốn lưu graph bằng `em.persist(order)`.
3. SQL INSERT child dùng FK tham chiếu parent đã tồn tại trong transaction.
4. Flush/commit đồng bộ thay đổi theo thứ tự provider xác định phù hợp với schema.

**Không nhất thiết phải gọi `em.flush()` giữa việc persist parent và child.** Một mapping đúng cùng provider hỗ trợ quan hệ thường tự xử lý dependency cần thiết. Nếu child có FK `NOT NULL` nhưng owning side là null, flush không thể tự đoán child cần gắn với parent nào.

### 14.1. Ví dụ lỗi ở flush

~~~java
OrderLine line = new OrderLine();
// Chưa gán line.order.

em.persist(line);
em.flush(); // Có thể vi phạm NOT NULL / association bắt buộc.
~~~

Lỗi xuất hiện tại flush không có nghĩa flush tạo ra lỗi; dữ liệu đã không hợp lệ từ lúc ứng dụng xây object graph.

### 14.2. Xóa cha và con

Khi xóa parent, FK của child có thể chặn thao tác nếu còn bản ghi tham chiếu. JPA cascade REMOVE, orphan removal hoặc cơ chế `ON DELETE CASCADE` của DB ảnh hưởng các SQL cần thực hiện.

~~~java
em.remove(order);
em.flush();
~~~

không đảm bảo xóa hợp lệ nếu mapping không xử lý child đúng vòng đời. Flush chỉ đồng bộ yêu cầu xóa đã khai báo; nó không tự thêm cascade ngoài mapping.

## 15. remove(), flush(), commit() cũng tuân theo cùng nguyên lý

`persist` dành cho entity mới. Với entity đang managed, JPA có `remove` để yêu cầu xóa:

~~~java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

if (order != null) {
    em.remove(order);
}

em.flush(); // Đồng bộ DELETE nếu cần.
em.getTransaction().commit();
~~~

Cần phân biệt:

- `em.remove(order)`: chuyển entity sang trạng thái removed theo vòng đời persistence.
- `em.flush()`: thực thi DELETE đang chờ, nếu dữ liệu/schema cho phép.
- `commit()`: xác nhận transaction xóa thành công.

Nếu rollback sau DELETE đã flush, bản ghi bị xóa trong transaction sẽ được khôi phục về trạng thái chưa bị xóa theo ngữ nghĩa rollback của database, miễn thao tác thuộc transaction chưa commit.

Không nên suy luận mọi lần gọi `remove` đều phát DELETE ngay lập tức hoặc mọi DELETE đều thành công mà không cần xét FK, trigger và transaction.

## 16. Spring @Transactional: commit xảy ra ở đâu?

Trong ứng dụng Spring dùng JPA, method service thường khai báo:

~~~java
package com.example.shop.service;

import com.example.shop.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createOrder(String code) {
        PurchaseOrder order = new PurchaseOrder(code);

        em.persist(order);

        // Không gọi commit trực tiếp.
        // Transaction manager sẽ flush/commit nếu method hoàn tất
        // và giao dịch được phép commit.
        return order.getId();
    }
}
~~~

Trong ví dụ, ID từ SEQUENCE có thể đã được cấp trước khi method trả về. Tuy nhiên transaction do Spring quản lý có thể chỉ commit **sau khi method body trả về, trong interceptor bao quanh lời gọi**. Vì vậy log ở cuối body không nhất thiết là bằng chứng commit đã hoàn tất.

### 16.1. flush trong Spring

Khi cần sớm đồng bộ SQL:

~~~java
@Transactional
public Long createOrderAndValidateDb(String code) {
    PurchaseOrder order = new PurchaseOrder(code);
    em.persist(order);

    em.flush(); // Yêu cầu đồng bộ SQL trong transaction.

    return order.getId();
}
~~~

`em.flush()` không thay thế `@Transactional` và không commit. Nếu dùng Spring Data JPA, `repository.saveAndFlush(entity)` cũng có ý nghĩa save và yêu cầu flush theo repository implementation; **không phải commit**.

Không nhầm `repository.save(...)` với `EntityManager.persist(...)` tuyệt đối: Spring Data JPA có thể quyết định dùng persist hoặc merge tùy cách nhận diện entity mới. Tuy nhiên **save** cũng không tự bảo đảm transaction đã commit ở ngay chỗ method được gọi nếu đang tham gia transaction lớn hơn.

### 16.2. Khi nào @Transactional tự rollback?

Theo cấu hình mặc định phổ biến của Spring, transaction được đánh dấu rollback đối với unchecked exceptions và một số lỗi tương ứng; checked exceptions có quy tắc mặc định khác và có thể cần `rollbackFor` hoặc cấu hình riêng. Không nên nói “mọi exception đều rollback” mà không xét framework/configuration.

Ví dụ:

~~~java
@Transactional
public void createAndFail(String code) {
    em.persist(new PurchaseOrder(code));

    throw new IllegalStateException("Reject business operation");
    // Transaction sẽ rollback theo quy tắc mặc định với RuntimeException.
}
~~~

Kể cả nếu provider đã flush trước exception, rollback của transaction sẽ hủy thay đổi chưa commit.

### 16.3. Self-invocation và ranh giới transaction

Trong chế độ proxy transaction thông dụng của Spring, gọi một method `@Transactional` từ **một method khác trong cùng instance bằng `this.method()`** có thể không đi qua interceptor, do đó không tự mở transaction như khi gọi qua proxy.

Vì vậy, khi triển khai ví dụ Spring, hãy bảo đảm method transactional được gọi qua cơ chế quản lý transaction thực tế của ứng dụng. Đây là vấn đề **transaction boundary**, không phải lỗi của `persist` hoặc `flush`.

## 17. Jakarta EE/JTA: không gọi EntityTransaction.commit()

Với container-managed JTA, một service có thể dùng:

~~~java
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Stateless
public class OrderApplicationService {

    @PersistenceContext(unitName = "shopPU")
    private EntityManager em;

    public Long createOrder(String code) {
        PurchaseOrder order = new PurchaseOrder(code);
        em.persist(order);

        // Container quản lý giao dịch theo transaction attribute.
        return order.getId();
    }
}
~~~

Với cấu hình transaction mặc định của EJB phù hợp, container có trách nhiệm bắt đầu/kết thúc transaction bao quanh method. Không gọi:

~~~java
em.getTransaction().commit();
~~~

trên container-managed JTA `EntityManager`. Nếu cần flush vì mục tiêu xử lý constraint hoặc thứ tự thao tác, `em.flush()` có thể được gọi **khi entity manager đã tham gia transaction hợp lệ**.

Ở Jakarta EE, CDI `@Transactional` hoặc các mô hình transaction khác cũng có thể áp dụng; cần tuân theo cấu hình transaction manager của ứng dụng.

## 18. persist hoặc flush ngoài transaction có gì khác?

Trong một môi trường resource-local, nên chủ động bắt đầu transaction cho thao tác ghi:

~~~java
em.getTransaction().begin();

em.persist(order);
em.flush();

em.getTransaction().commit();
~~~

`flush()` trên transaction-scoped context khi không có transaction hoạt động có thể ném `TransactionRequiredException`, vì thao tác này yêu cầu đồng bộ các thay đổi ghi vào database trong phạm vi giao dịch thích hợp.

Trong JTA/container-managed, các quy định cụ thể về propagation của `persist` ngoài transaction và thời điểm flush có thể khác với resource-local. Không nên lấy một ví dụ gọi `persist` không mở transaction trong một provider rồi áp dụng như hành vi portable cho ứng dụng ghi dữ liệu.

**Quy tắc an toàn:** đặt toàn bộ thao tác tạo/sửa/xóa, flush và nghiệp vụ phụ thuộc vào chúng trong transaction boundary rõ ràng. Việc không có transaction cũng không thể được khắc phục bằng cách “gọi flush thêm một lần”.

## 19. clear, detach và refresh không phải flush/commit

Các thao tác khác của `EntityManager` đôi khi bị nhầm:

| Thao tác | Ý nghĩa | Có commit không? |
| --- | --- | --- |
| `flush()` | Đồng bộ pending changes tới database | Không |
| `clear()` | Detach tất cả managed entities khỏi persistence context | Không |
| `detach(entity)` | Detach một entity cụ thể | Không |
| `refresh(entity)` | Nạp lại trạng thái entity từ database theo contract JPA | Không |
| `persist(entity)` | Đưa entity mới vào managed state | Không |
| `remove(entity)` | Đánh dấu entity managed để xóa | Không |

Đặc biệt, `clear()` **không có trách nhiệm tự flush**. Nếu ứng dụng có thay đổi managed chưa đồng bộ rồi gọi `em.clear()`, những thay đổi đó có thể không được gửi xuống database.

Ví dụ:

~~~java
em.getTransaction().begin();

PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.confirm();

em.clear(); // Detach, không phải flush.
em.getTransaction().commit();
~~~

Ở ví dụ trên, đừng mặc định thay đổi status được commit. Nếu cần đảm bảo pending changes được đồng bộ trước khi clear:

~~~java
order.confirm();
em.flush();
em.clear();
~~~

Tuy vậy, transaction vẫn chưa commit; sau flush rồi clear, các thay đổi SQL có thể bị rollback như bình thường.

## 20. Những ngộ nhận thường gặp

| Nhận định | Điều đúng |
| --- | --- |
| “persist = INSERT ngay.” | Persist đưa entity mới thành managed; INSERT có thể ngay hoặc sau, tùy provider/ID strategy. |
| “persist xong là dữ liệu đã lưu bền vững.” | Chưa; phải xét transaction đã commit thành công chưa. |
| “flush là commit.” | Flush đồng bộ SQL nhưng không kết thúc transaction. |
| “Đã flush thì không rollback được.” | Rollback vẫn hủy thay đổi SQL chưa commit trong transaction. |
| “Không gọi flush thủ công thì commit không lưu.” | Với transaction bình thường, provider đồng bộ pending changes khi commit. |
| “Có ID nghĩa là row đã tồn tại và commit.” | ID có thể được cấp trước INSERT hoặc trước commit. |
| “Mọi persist đều chưa chạy SQL tới flush.” | IDENTITY và một số behavior provider có thể phát INSERT sớm. |
| “Mỗi setter tạo một UPDATE.” | Dirty checking và batching quyết định SQL thực tế. |
| “Flush thành công bảo đảm commit thành công.” | Có thể còn deferred constraints, deadlock, serialization hoặc lỗi commit. |
| “AUTO nghĩa là luôn flush trước mọi SELECT.” | Provider flush theo yêu cầu để bảo đảm kết quả, không nhất thiết trước mọi truy vấn. |
| “COMMIT flush mode nghĩa là query luôn bỏ qua pending changes.” | Hành vi thấy pending changes trước commit có thể tùy provider/ngữ nghĩa. |
| “saveAndFlush trong Spring Data là commit.” | Không; nó yêu cầu flush, còn commit do transaction manager. |
| “Có thể tiếp tục transaction sau một SQL flush exception.” | Thường phải rollback/đóng phạm vi hỏng, không tiếp tục ghi bừa. |
| “clear() giống flush().” | Clear detach entities; nếu không flush trước có thể mất các thay đổi chưa đồng bộ. |
| “commit luôn ở dòng cuối service @Transactional.” | Trong Spring, transaction interceptor có thể commit sau khi method body trả về. |

## 21. Tình huống thực hành có lời giải

### Bài 1. Persist nhưng chưa thấy SQL INSERT

Ứng dụng dùng `GenerationType.SEQUENCE`:

~~~java
em.getTransaction().begin();
PurchaseOrder order = new PurchaseOrder("A001");
em.persist(order);
// SQL log chưa có INSERT.
~~~

**Câu hỏi:** Có phải `persist` không hoạt động?

**Đáp án:** Không. Provider có thể trì hoãn INSERT tới flush/commit và chỉ lấy giá trị sequence sớm. Cần phân biệt trạng thái managed với SQL đồng bộ.

### Bài 2. Flush rồi rollback

~~~java
em.getTransaction().begin();
em.persist(new PurchaseOrder("A002"));
em.flush();
em.getTransaction().rollback();
~~~

**Câu hỏi:** Order A002 có được commit không?

**Đáp án:** Không. Flush không commit; rollback hủy các thay đổi thuộc transaction chưa commit. Có thể vẫn có giá trị sequence đã tiêu thụ.

### Bài 3. Không gọi flush mà commit

~~~java
em.getTransaction().begin();
em.persist(new PurchaseOrder("A003"));
em.getTransaction().commit();
~~~

**Câu hỏi:** Có nhất thiết phải thêm `em.flush()` mới lưu thành công?

**Đáp án:** Không. Trong transaction JPA bình thường, provider đồng bộ những thay đổi còn chờ khi transaction commit.

### Bài 4. Đã find entity rồi gọi persist lại

~~~java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
order.confirm();
em.persist(order);
~~~

**Câu hỏi:** `persist` thứ hai có cần thiết để cập nhật `status`?

**Đáp án:** Không. Entity lấy bởi `find` đang managed trong context; JPA dirty checking đồng bộ thay đổi khi flush/commit. `persist` không phải API “save mọi object” theo nghĩa tổng quát.

### Bài 5. unique constraint lỗi xuất hiện ở flush

Hai order có `orderCode` trùng nhau được persist, nhưng exception chỉ xảy ra khi `em.flush()`.

**Đáp án:** Điều này có thể xảy ra vì INSERT được trì hoãn. Flush làm SQL chạy và database kiểm tra UNIQUE. Sau lỗi, rollback transaction; không tiếp tục sử dụng transaction lỗi để ghi dữ liệu như thể không có chuyện gì.

### Bài 6. flush thành công nhưng commit lỗi

Database có FK/UNIQUE constraint deferrable hoặc lỗi serialization xảy ra ở commit.

**Câu hỏi:** `em.flush()` không báo lỗi có bảo đảm commit được không?

**Đáp án:** Không. Flush đồng bộ các thay đổi hiện tại, nhưng một số ràng buộc được kiểm tra về sau; commit vẫn có thể thất bại. Phải xử lý lỗi transaction và rollback khi có thể.

### Bài 7. Có ID nhưng transaction chưa commit

~~~java
em.persist(order);
Long id = order.getId();
~~~

**Đáp án:** Giá trị ID không chứng minh đã commit. Với SEQUENCE, ID có thể đến trước INSERT; với IDENTITY, INSERT có thể đã chạy nhưng chưa được commit.

### Bài 8. Query ngay sau persist

~~~java
em.persist(new PurchaseOrder("A008"));

Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o WHERE o.orderCode = :code",
    Long.class
).setParameter("code", "A008")
 .getSingleResult();
~~~

**Câu hỏi:** Vì sao query có thể thấy entity dù chưa gọi flush tường minh?

**Đáp án:** Với `FlushModeType.AUTO`, provider phải bảo đảm kết quả truy vấn phản ánh thay đổi pending theo yêu cầu JPA, có thể bằng flush tự động. Không suy ra query đã commit dữ liệu.

### Bài 9. Transaction khác chưa thấy dữ liệu đã flush

A persist/flush một order mới, B dùng connection riêng SELECT nhưng không thấy bản ghi.

**Đáp án:** Không có mâu thuẫn; A chưa commit. Với isolation thông dụng không đọc dữ liệu chưa commit, B không được nhìn thấy thay đổi đó. Sau commit, khả năng thấy dữ liệu mới còn tùy isolation và snapshot của B.

### Bài 10. Spring saveAndFlush

Một service đang `@Transactional` gọi:

~~~java
repository.saveAndFlush(order);
~~~

**Câu hỏi:** Có thể gửi email “đơn hàng đã lưu bền vững” ngay sau lời gọi đó không?

**Đáp án:** Không thể coi flush là bằng chứng commit. Nếu service còn có thể rollback, email là side effect khó đảo ngược. Nên phát sự kiện sau commit hoặc dùng transactional outbox phù hợp khi cần tính tin cậy.

### Bài 11. Lỗi sau clear

~~~java
em.getTransaction().begin();
PurchaseOrder managed = em.find(PurchaseOrder.class, id);
managed.confirm();
em.clear();
em.getTransaction().commit();
~~~

**Câu hỏi:** Vì sao status không đổi?

**Đáp án:** `clear()` detach entity, không có nghĩa flush. Nếu UPDATE chưa được đồng bộ, thay đổi managed có thể bị bỏ. Nếu cần, flush trước clear trong transaction nhưng vẫn phải commit sau.

### Bài 12. Entity child thiếu FK

Parent và child được tạo, nhưng child không có tham chiếu owning side:

~~~java
em.persist(parent);
em.persist(child);
em.flush();
~~~

**Câu hỏi:** Vì sao có thể lỗi NOT NULL/FK?

**Đáp án:** Thứ tự Java persist không làm JPA tự đoán quan hệ. Phải thiết lập child.parent đúng metadata sở hữu quan hệ và xử lý cascade/dependency phù hợp trước flush.

## 22. Hướng dẫn lựa chọn khi lập trình

Khi viết logic persistence trong service, hãy hỏi tuần tự:

1. **Đây có phải entity mới cần được quản lý?** Nếu có, sử dụng `persist` (hoặc repository save được thiết kế phù hợp).
2. **Entity đã managed và đang được sửa?** Nếu có, để dirty checking theo dõi thay đổi; không persist lại chỉ để UPDATE.
3. **Có lý do bắt database xử lý pending changes ngay trong transaction?** Nếu có, cân nhắc `flush`, ví dụ phát hiện lỗi constraint sớm, phối hợp một native operation hoặc chuẩn bị dữ liệu cho bước phụ thuộc.
4. **Transaction đã hoàn tất chưa?** Chỉ `commit` thành công theo transaction manager mới là cột mốc xác nhận thay đổi đã được commit.
5. **Có tác dụng phụ bên ngoài database không?** Không xem flush là mốc gửi email, publish event hay thông báo thành công không thể đảo ngược.
6. **Có lỗi khi flush/commit không?** Xử lý rollback/rollback-only và tránh dùng lại transaction hỏng.
7. **Có cần đo SQL thực tế?** Dùng SQL log, tracing/metrics và schema thật; không đoán lịch SQL chỉ từ thứ tự các dòng `persist`.

## 23. Kết luận

Ba thao tác được hiểu ngắn gọn như sau:

~~~text
persist(entity)
    = đăng ký một entity mới vào persistence context

flush()
    = đồng bộ trạng thái đang chờ thành SQL trong transaction

commit()
    = hoàn tất transaction, xác nhận các thay đổi đã được commit
~~~

**`persist` không bảo đảm INSERT ngay. `flush` không phải commit. `commit` không đòi hỏi ứng dụng phải flush tường minh trước đó trong luồng làm việc thông thường.**

Điểm quyết định khi thiết kế ứng dụng JPA là giữ rõ **ranh giới giữa trạng thái object, trạng thái SQL trong transaction và dữ liệu đã commit**. Khi phân biệt được ba lớp này, ứng dụng dễ xử lý hơn các lỗi FK/UNIQUE, lazy/delayed SQL, dirty checking, ID generation, rollback và giao dịch đồng thời.
