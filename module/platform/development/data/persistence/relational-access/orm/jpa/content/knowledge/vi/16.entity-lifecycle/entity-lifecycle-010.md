# Tác động của commit, rollback và đóng ngữ cảnh tới vòng đời entity

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Vòng đời entity

Trong JPA, một object Java có thể được tạo bằng `new`, trở thành **managed** khi đưa vào persistence context, bị đánh dấu **removed** khi yêu cầu xóa, hoặc trở thành **detached** khi không còn được persistence context quản lý. Việc entity chuyển qua các trạng thái đó liên quan chặt chẽ đến giao dịch và vòng đời `EntityManager`, nhưng **transaction và persistence context không phải là một**.

Ba thao tác dễ gây nhầm lẫn nhất là:

- **Commit**: xác nhận transaction; **không phải lúc nào cũng đóng persistence context**.
- **Rollback**: hủy thay đổi chưa commit trong database; **không tự hoàn tác mọi setter đã chạy trên object Java**.
- **Đóng ngữ cảnh**: kết thúc việc quản lý entity, khiến các object còn lại không được theo dõi tự động; **không thay thế commit hay rollback**.

Vì thế, sau `commit()`, `rollback()` hoặc `EntityManager.close()`, cần đặt hai câu hỏi riêng: **database đang lưu gì?** và **object Java hiện còn được quản lý không?** Câu trả lời chính xác còn phụ thuộc loại persistence context: **transaction-scoped**, **application-managed** hoặc **extended**.

Bài này đi qua từng trạng thái entity, trình bày bảng chuyển trạng thái, các timeline transaction, ví dụ Java với Jakarta Persistence và những tình huống lỗi thực tế.

---

## 1. Mục tiêu bài học

Sau bài học, bạn có thể:

1. Nhận diện bốn trạng thái thường dùng: **new/transient**, **managed**, **removed**, **detached**.
2. Giải thích đúng khác biệt giữa trạng thái Java entity và sự tồn tại của bản ghi database.
3. Dự đoán ảnh hưởng của `persist()`, `remove()`, `detach()`, `clear()` và `close()` đối với vòng đời.
4. Hiểu vì sao `commit()` có thể làm entity trở thành detached ở **transaction-scoped context**, nhưng vẫn managed với một **application-managed EntityManager** còn mở.
5. Trình bày lý do rollback không nhất thiết phục hồi object Java về giá trị trước giao dịch.
6. Xử lý an toàn entity đã được cấp generated ID nhưng transaction INSERT bị rollback.
7. Phân biệt `flush()` với `commit()` khi dự đoán thời điểm SQL được thực thi.
8. Giải thích điều gì xảy ra khi xóa entity rồi commit, xóa entity rồi rollback, hoặc đóng context khi còn thay đổi chưa flush.
9. Biết khi nào phải dùng EntityManager mới, `find()`, `merge()` hoặc `refresh()` thay vì tái sử dụng entity không còn managed.
10. Thiết kế unit of work và viết thử nghiệm để kiểm tra lifecycle trên provider/database cụ thể.

## 2. Hai trục cần theo dõi đồng thời

Một entity tồn tại ít nhất theo **hai góc nhìn**:

**Góc nhìn Java/JPA:** object có được một persistence context quản lý không? Provider có theo dõi field của nó và thực hiện dirty checking không?

**Góc nhìn database:** hàng tương ứng đã INSERT chưa, đã COMMIT chưa, bị DELETE trong transaction chưa, và transaction có thể ROLLBACK không?

Hai góc nhìn đó không luôn trùng nhau.

```text
OBJECT JAVA                               DATABASE

new Customer("An")                        chưa có hàng
      |
      | em.persist()
      v
managed Customer                           INSERT có thể đang chờ
      |
      | flush()                             INSERT/UPDATE/DELETE
      |                                     trong transaction
      |
      | tx.commit()                         thay đổi được xác nhận
      |   hoặc tx.rollback()                 hoặc hủy bỏ
      |
      | em.close() / clear()                 không phải thao tác COMMIT
      v
detached Customer                          hàng có thể còn hoặc không
                                          tùy giao dịch trước đó
```

Ví dụ rõ nhất: sau `rollback()` của một INSERT dùng database-generated ID, object Java có thể vẫn chứa một ID đã cấp, nhưng hàng đó **không tồn tại ở trạng thái đã commit**. Ngược lại, sau `close()` của một EntityManager đã commit thành công, entity trở thành detached dù hàng trong database vẫn tồn tại.

### 2.1. Ba khái niệm không nên đánh đồng

| Khái niệm | Vai trò | Điều không bảo đảm |
|---|---|---|
| **Persistence context** | Identity map và nơi quản lý managed entities | Không tự xác nhận transaction |
| **EntityManager** | API làm việc với context và truy vấn database | Không phải bản thân database transaction |
| **Transaction** | Ranh giới xác nhận/hủy các thao tác ghi | Không định nghĩa rằng mọi EntityManager phải đóng khi commit |

Một EntityManager có thể tồn tại qua nhiều transaction; một context khác có thể gắn với đúng một transaction. Do đó không thể suy từ `commit()` thành “mọi object bị detach” khi chưa xác định loại context.

---

## 3. Bốn trạng thái vòng đời quan trọng

### 3.1. New / transient

Một object do ứng dụng tự tạo, chưa được đưa vào persistence context:

```java
Customer customer = new Customer("An");
```

Đặc điểm:

- Chưa được context quản lý.
- Chưa mặc nhiên có hàng database tương ứng.
- Với ID sinh bởi database, ID thường là `null` trước khi persist.
- Đổi field chỉ làm thay đổi object Java.
- Không được dirty checking đồng bộ bởi một EntityManager nào.

### 3.2. Managed

Một entity được persistence context quản lý:

```java
Customer managed = em.find(Customer.class, 10L);
```

hoặc:

```java
Customer created = new Customer("Bình");
em.persist(created);
```

Khi managed:

- Provider biết identity và theo dõi state phù hợp.
- Trong cùng context, cùng entity identity tương ứng một managed instance.
- Thay đổi trên field persistent có thể được ghi qua dirty checking trong transaction.
- Association lazy có thể được provider tải khi cần, nếu context và các điều kiện truy cập phù hợp.
- Managed **không đồng nghĩa** transaction đã commit, cũng không bảo đảm hàng database hiện còn tồn tại sau khi transaction khác can thiệp.

### 3.3. Removed

Một **managed entity** được đánh dấu để xóa:

```java
Customer managed = em.find(Customer.class, 10L);
em.remove(managed);
```

Đặc điểm:

- Provider đã nhận yêu cầu xóa entity.
- Lệnh SQL `DELETE` có thể chờ đến flush hoặc được thực hiện theo chiến lược provider.
- Trước commit, việc xóa còn thuộc transaction và có thể rollback.
- Sau commit xóa thành công, object Java vẫn tồn tại trong bộ nhớ nếu code giữ tham chiếu, nhưng nó **không còn biểu diễn một hàng đã tồn tại trong database**.
- Không nên giả định rằng một object sau khi xóa có thể được tái sử dụng như một managed entity bình thường.

### 3.4. Detached

Entity từng được managed nhưng không còn nằm trong context:

```java
Customer managed = em.find(Customer.class, 10L);
em.detach(managed);
```

Hoặc khi context của nó kết thúc:

```java
Customer managed = em.find(Customer.class, 10L);
em.close(); // Với application-managed EntityManager.
```

Object detached:

- Vẫn giữ các field Java đã được nạp, kể cả ID.
- Không còn được EntityManager cũ theo dõi thay đổi.
- Gọi setter sau detach không tự làm database `UPDATE`.
- Lazy association chưa khởi tạo có thể không truy cập được khi context đóng, tùy provider và cấu hình.
- Có thể được dùng làm dữ liệu đầu vào cho quá trình cập nhật, nhưng cần load lại entity hoặc dùng `merge` phù hợp trong context mới.

### 3.5. Bảng trạng thái

| Trạng thái | Có thể có ID? | Context đang theo dõi? | Sửa field có tự được dirty checking? |
|---|---|---|---|
| New | Có thể, nhất là ID do ứng dụng cấp | Không | Không |
| Managed | Có thể có hoặc đang chờ được cấp ID tùy generator/tình huống | Có | Có, theo quy tắc flush/transaction |
| Removed | Có thể có ID của hàng đang bị xóa | Theo vòng đời removed của context | Không nên sửa như một managed entity thông thường |
| Detached | Có thể giữ ID đã cấp | Không | Không |

**Lưu ý:** `id != null` không phải phép kiểm tra đáng tin cậy để xác định một entity có đang managed hay không. Nếu cần biết một object có được **một EntityManager cụ thể** quản lý, dùng `em.contains(entity)` khi EntityManager còn mở và object hợp lệ.

---

## 4. Các thao tác lifecycle trước khi xét commit/rollback

Bảng sau tóm lược hành vi điển hình của các phương thức JPA:

| Thao tác | Đối tượng đầu vào | Tác động chính |
|---|---|---|
| `new Entity(...)` | Không có entity trước đó | Tạo object new |
| `em.persist(e)` | New entity | Đăng ký e thành managed, INSERT có thể chờ flush hoặc được phát sớm |
| `em.find(Type.class, id)` | Entity identity | Trả managed instance hoặc null nếu không tìm thấy theo ngữ nghĩa truy xuất |
| `em.merge(detached)` | Detached/new entity | Sao chép state sang **managed instance trả về**, không nhất thiết quản lý object đầu vào |
| `em.remove(managed)` | Managed entity | Chuyển sang trạng thái removed |
| `em.detach(managed)` | Managed entity | Ngừng quản lý entity cụ thể |
| `em.clear()` | Context | Tách tất cả managed entities khỏi context |
| `em.flush()` | Context đang có transaction phù hợp | Đồng bộ thay đổi pending thành SQL; không commit |
| `tx.commit()` | Transaction active | Xác nhận transaction thành công; scope context quyết định entity còn managed hay không |
| `tx.rollback()` | Transaction active | Hủy thay đổi chưa commit; state object/context sau rollback cần xử lý thận trọng |
| `em.close()` | Application-managed EM | Kết thúc context theo vòng đời EM; không tự commit pending changes |

Từng thao tác có ý nghĩa riêng. Ví dụ:

```java
em.clear();
```

không có nghĩa “rollback transaction”. Nếu provider đã `flush()` dữ liệu vào database trong một transaction rồi bạn `clear()`, transaction vẫn có thể commit các SQL đã chạy. Ngược lại, nếu có pending changes chưa flush và `clear()` khiến entity bị detach, những thay đổi chưa đồng bộ có thể bị bỏ qua.

---

## 5. Commit làm gì với entity?

**Commit trước hết tác động đến transaction.** Khi commit thành công, các thao tác INSERT/UPDATE/DELETE thuộc transaction được xác nhận theo bảo đảm của database và transaction manager.

Về vòng đời entity, câu hỏi quan trọng là: **persistence context có kết thúc cùng transaction này không?**

### 5.1. Với transaction-scoped persistence context

Một context kiểu **transaction-scoped**, điển hình trong container-managed JTA hoặc proxy EntityManager được gắn với transaction theo cách thông dụng, có vòng đời gắn với transaction.

```text
TX #1:    BEGIN -------------------------------- COMMIT
PC #1:    [    managed Customer, Order, ...    ]
         ↑                                     ↑
      Context được dùng                Context kết thúc
      trong transaction                 entity trở thành detached
```

Sau khi transaction-scoped context kết thúc, các entity mà nó quản lý không còn managed trong context đó. Code có thể còn giữ tham chiếu Java, nhưng các object này trở thành detached.

**Hệ quả:** sau khi service transaction kết thúc, một controller giữ entity trả về không được dựa vào lazy association chưa tải hoặc dirty checking để tự ghi những setter mới.

### 5.2. Với application-managed EntityManager còn mở

Ở Java SE dùng `EntityManagerFactory.createEntityManager()`, EntityManager do ứng dụng tạo thường sở hữu context tồn tại đến khi EM được đóng hoặc được xử lý detach/clear.

```text
EntityManager:     OPEN -------------------------------- CLOSE
Persistence Context: [----------------------------------]
Transaction #1:       [ BEGIN ------- COMMIT ]
Transaction #2:                              [ BEGIN --- COMMIT ]

Customer#10:        managed ----------------------------- detached
```

Ví dụ:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer customer = em.find(Customer.class, 10L);
    customer.rename("Sau giao dịch 1");

    tx.commit();

    // Với application-managed EM còn mở:
    System.out.println(em.contains(customer)); // true

    tx.begin();
    customer.rename("Sau giao dịch 2");
    tx.commit();
} finally {
    em.close();
}
```

Giả sử customer tồn tại và hai transaction thành công. **Commit của transaction #1 không đóng EM**. Object vẫn managed vì context vẫn tồn tại. Đây là minh họa điển hình cho việc **transaction boundary khác persistence-context boundary**.

### 5.3. Với extended persistence context

Một **extended persistence context** do container quản lý (thường gắn với một stateful component) có thể giữ managed entities qua nhiều transaction:

```java
@Stateful
public class CustomerEditor {

    @PersistenceContext(type = PersistenceContextType.EXTENDED)
    private EntityManager em;

    // Các method thuộc cùng editor/session được quản lý.
}
```

Phải phân biệt:

- **Một context extended**: vùng managed entity được giữ lâu hơn.
- **Nhiều transaction**: mỗi transaction có begin/commit/rollback riêng.
- Không có chuyện annotation EXTENDED tự biến một workflow nhiều request thành **một transaction database dài**.

Sau một commit thành công, nếu extended context vẫn sống và không có thao tác detach/clear khác, các object có thể tiếp tục managed. Tuy nhiên, extended context kéo dài cũng mang rủi ro stale data, tích lũy object và concurrency cần được quản lý.

### 5.4. Commit không có nghĩa đóng mọi EntityManager

| Bối cảnh | Sau commit thành công |
|---|---|
| Transaction-scoped context kết thúc với TX | Entity thường detached khi context kết thúc |
| Application-managed EM vẫn mở | Entity thường vẫn managed |
| Extended context vẫn mở | Entity có thể vẫn managed |
| Application-managed EM được đóng ngay sau commit | Entity trở thành detached vì context đóng |
| Object đã bị detach trước commit | Không tự trở lại managed chỉ vì commit |
| Entity đã được xóa thành công | Row không còn; đừng xem object cũ là managed entity có hàng tương ứng |

Không nên viết một quy tắc chung “sau commit entity luôn detached” hoặc “sau commit entity luôn managed” mà không nêu context scope.

---

## 6. Commit sau INSERT: entity mới đi qua những mốc nào?

Giả sử entity được tạo trong ứng dụng và lưu thành công:

```java
tx.begin();

Customer customer = new Customer("An"); // new
em.persist(customer);                   // managed

tx.commit();                            // DB INSERT được xác nhận
```

Dòng thời gian khái niệm:

```text
T0: new Customer
    - Object Java new
    - Chưa có bản ghi đã commit

T1: em.persist(customer)
    - Object thành managed
    - INSERT có thể được trì hoãn hoặc chạy ngay theo generator/provider

T2: flush tự động hoặc tường minh
    - Những INSERT còn pending được đồng bộ vào DB trong transaction

T3: commit thành công
    - Hàng được xác nhận
    - Còn managed hay detached tùy context scope

T4: em.close() nếu application-managed
    - Entity trở thành detached
    - Hàng DB đã commit vẫn tồn tại
```

### 6.1. Sinh ID trước commit không phải bằng chứng đã lưu

Với `GenerationType.IDENTITY`, database thường cần chạy INSERT để sinh khóa. Vì thế object có thể nhận ID ngay sau `persist()` trong một transaction đang active:

```java
tx.begin();

Customer customer = new Customer("An");
em.persist(customer);

Long generatedId = customer.getId(); // Có thể đã có.

tx.rollback();
```

Sau rollback, object có thể vẫn giữ `generatedId`, nhưng **hàng database không được commit**. Không dùng `generatedId != null` để xác nhận nghiệp vụ lưu thành công.

### 6.2. ID tăng không đồng nghĩa số bản ghi đã commit

Database sequence/identity có thể cấp số trong transaction rồi vẫn không tái sử dụng số khi rollback. Vì vậy bảng có ID `1, 3, 5` không tự chứng minh có bản ghi bị xóa.

Không dùng generated primary key để suy ra:

- Thứ tự commit tuyệt đối.
- Số lượng giao dịch thành công.
- Số hóa đơn liên tục không có khoảng trống.
- Kết quả nghiệp vụ đã commit.

Cần dùng transaction result hoặc một cơ chế audit/đánh số nghiệp vụ riêng khi thật sự cần.

---

## 7. Commit sau UPDATE: managed state và database state

Giả sử customer đã tồn tại:

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
customer.rename("Tên mới");

tx.commit();
```

Khi entity managed thay đổi, provider dùng dirty checking để đồng bộ state theo chính sách flush. Nếu commit thành công, field persistent mới được lưu vào database.

Trước commit:

```text
Java object managed:
  displayName = "Tên mới"

Database:
  Có thể chưa nhận UPDATE (nếu chưa flush)
  hoặc đã nhận UPDATE nhưng transaction chưa xác nhận.
```

Sau commit thành công:

```text
Database:
  display_name đã lưu giá trị được xác nhận.

Java object:
  Có thể vẫn managed (context còn sống)
  hoặc detached (context kết thúc).
```

Nếu client nhận object sau commit và tiếp tục gọi setter, khả năng ghi tự động phụ thuộc object có còn managed trong một context hợp lệ, có transaction tương ứng hay không. Không suy luận chỉ từ tên class hoặc việc object có ID.

### 7.1. Không cần gọi persist lần nữa để lưu sửa đổi

Một entity đã managed không cần `em.persist(customer)` lại sau khi đổi field:

```java
Customer managed = em.find(Customer.class, customerId);
managed.rename("Tên mới");
// JPA theo dõi thay đổi theo quy tắc dirty checking.
```

Trong transaction phù hợp, flush/commit sẽ xử lý. `persist` là thao tác đưa new entity vào quản lý, không phải “save mọi object” theo nghĩa tổng quát.

### 7.2. Commit thất bại không phải commit thành công

`tx.commit()` có thể ném exception vì:

- Constraint violation.
- Optimistic locking conflict.
- Lỗi kết nối hoặc transaction manager.
- Deadlock hoặc lỗi database khác.
- Transaction đã được đánh dấu rollback-only.

Khi commit thất bại, **không được coi dữ liệu đã lưu chỉ vì code đã gọi phương thức commit**. Cần xử lý đúng loại lỗi, tình trạng transaction và khả năng xác định outcome theo môi trường. Trong trường hợp lỗi kết nối ở thời điểm commit, kết quả transaction đôi khi có thể không rõ với ứng dụng; không nên luôn khẳng định chắc chắn rollback đã diễn ra nếu không có bằng chứng.

---

## 8. Commit sau REMOVE: khác gì với detach?

Ví dụ:

```java
tx.begin();

Customer managed = em.find(Customer.class, customerId);
em.remove(managed);

tx.commit();
```

Khi xóa thành công:

- Entity đã chuyển sang trạng thái removed ở phía JPA trước khi commit.
- Database row tương ứng bị xóa qua SQL và được xác nhận khi commit.
- Java object vẫn có thể còn `id`, `displayName` hoặc những field đã load nếu code giữ reference.
- Không nên dùng object đó như một managed entity hợp lệ có hàng DB còn tồn tại.

Đây không giống `em.detach(managed)`.

| Thao tác | Row DB sau commit thành công | Object Java sau thao tác |
|---|---|---|
| `em.remove(managed)` trong TX | Bị xóa | Vẫn có thể còn reference Java nhưng row không còn |
| `em.detach(managed)` | Không bị xóa do chính thao tác detach | Object không còn được theo dõi |
| `em.clear()` | Không xóa row do chính clear | Toàn bộ managed instances bị detach |
| `em.close()` | Không xóa row do chính close | Context kết thúc; entity bị detach |

**Nguyên tắc:** *Remove* là yêu cầu xóa entity khỏi persistence; *detach* là yêu cầu ngừng quản lý entity. Hai hành động có ý nghĩa hoàn toàn khác nhau.

### 8.1. Phụ thuộc FK và cascade

Nếu Customer được các bảng khác tham chiếu, DELETE có thể bị foreign key constraint từ chối. `CascadeType.REMOVE`, `orphanRemoval` hoặc DB `ON DELETE CASCADE` có thể thay đổi các row liên quan, nhưng mỗi cơ chế có quy tắc riêng.

Không nên suy luận rằng `em.remove(parent)` luôn xóa thành công chỉ vì entity đang managed. Transaction có thể rollback nếu ràng buộc database bị vi phạm.

---

## 9. Rollback làm gì với transaction?

`rollback()` hủy các thay đổi chưa được xác nhận thuộc transaction, theo quy tắc transaction manager và database. Nếu SQL đã phát ở bước flush, nó vẫn thuộc transaction chưa commit và có thể bị hoàn tác.

```text
BEGIN
  INSERT ...
  UPDATE ...
  DELETE ...
ROLLBACK

Các thao tác ghi trong transaction không được commit.
```

Nhưng rollback **không phải phép quay ngược thời gian của bộ nhớ Java**. Các setter đã chạy, biến `id` đã được provider gán, collection đã bị sửa... có thể vẫn giữ giá trị trong object mà ứng dụng đang tham chiếu.

### 9.1. Vấn đề lớn: Java state và DB state có thể lệch nhau

```text
Trước TX:
  DB Customer#10 = "An"
  Java Customer#10 = "An"

Trong TX:
  customer.rename("Bình")
  Java Customer#10 = "Bình"
  Có thể SQL UPDATE đã chạy.

Sau ROLLBACK:
  DB Customer#10 = "An"
  Java object cũ có thể vẫn = "Bình"
```

Điều này **không phải bug của rollback**. Transaction rollback là cơ chế hủy các thay đổi database chưa commit, không phải chức năng khôi phục tất cả object Java về snapshot nghiệp vụ ban đầu.

### 9.2. Có nên tiếp tục dùng cùng persistence context sau rollback?

Không nên giả định các entity cũ vẫn ở trạng thái quản lý hợp lệ hoặc có nội dung khớp database sau rollback. Các quy tắc cleanup và state sau rollback phụ thuộc loại context và JPA provider; transaction-scoped context kết thúc theo transaction, còn context tồn tại dài hơn cần được xử lý thận trọng.

Một hướng an toàn cho unit of work thất bại:

1. Rollback transaction nếu còn active và rollback được.
2. Kết thúc hoặc clear persistence context phù hợp.
3. Không tái sử dụng object có state chưa được xác nhận như bằng chứng dữ liệu đã lưu.
4. Ở unit of work mới, tải lại entity từ database bằng EntityManager mới.
5. Nếu cần thử lại thao tác, tái áp dụng input nghiệp vụ trên managed entity mới và kiểm tra xung đột/constraint.

Đây là hướng dùng thực tế giúp tránh stale state; không phải lời khẳng định rằng mọi provider đều bắt buộc đóng EM sau từng rollback.

---

## 10. Rollback với entity NEW được persist

Xét thao tác tạo customer mới:

```java
tx.begin();

Customer customer = new Customer("Khách thử nghiệm");
em.persist(customer);

Long assignedId = customer.getId();

tx.rollback();
```

Sau rollback:

- Database không giữ hàng INSERT chưa commit.
- `customer` vẫn là một object Java.
- `assignedId` có thể là `null` hoặc một ID đã cấp, tùy strategy/provider/thời điểm SQL.
- Nếu object còn giữ ID đã được cấp, không được coi nó là entity đã lưu thành công.
- State quản lý của object sau rollback không nên dựa vào giả định từ thời điểm trước rollback.

### 10.1. Vì sao không gọi persist lại ngay object cũ?

Thử code:

```java
// Transaction đầu đã rollback, nhưng customer có thể còn ID.
EntityManager newEm = emf.createEntityManager();

newEm.getTransaction().begin();
newEm.persist(customer); // Có thể lỗi vì state/id đã được gán.
newEm.getTransaction().commit();
```

Nếu ID được provider sinh trong transaction đầu, một object cũ có ID có thể bị nhận diện như detached hoặc không phù hợp để persist như new entity. Hành vi phụ thuộc generator và provider; không nên dùng mẫu này như cách retry portable.

Cách thực tế hơn là **tạo entity mới từ input nghiệp vụ** trong transaction mới:

```java
String customerNameFromRequest = "Khách thử nghiệm";

EntityManager em2 = emf.createEntityManager();
EntityTransaction tx2 = em2.getTransaction();

try {
    tx2.begin();

    Customer retry = new Customer(customerNameFromRequest);
    em2.persist(retry);

    tx2.commit();
} catch (RuntimeException error) {
    if (tx2.isActive()) {
        tx2.rollback();
    }
    throw error;
} finally {
    em2.close();
}
```

Với business workflow nhạy cảm như thanh toán/đặt hàng, cần thêm **idempotency** và quy tắc retry theo loại lỗi. Không mặc định “thử lại bằng đối tượng mới” là an toàn nếu kết quả commit trước đó chưa rõ ràng.

---

## 11. Rollback với entity MANAGED bị cập nhật

Ví dụ:

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);

customer.rename("Tên A");
em.flush();

customer.rename("Tên B");

tx.rollback();
```

Cần phân biệt:

- SQL `UPDATE` đầu có thể đã được gửi tại `flush()`.
- Thay đổi thứ hai có thể vẫn đang ở bộ nhớ.
- Rollback hủy những thay đổi chưa commit trong database.
- Object Java có thể vẫn giữ `"Tên B"`, dù database giữ giá trị trước giao dịch.
- Context cũ không được tự động xem là một snapshot sạch sau rollback.

Muốn đọc trạng thái đã commit:

```java
EntityManager freshEm = emf.createEntityManager();

try {
    Customer fresh = freshEm.find(Customer.class, customerId);
    System.out.println(fresh.getDisplayName());
} finally {
    freshEm.close();
}
```

Đọc lại bằng **context mới** là cách rõ ràng để kiểm tra database. Nếu bạn chỉ `em.find` trên một context cũ vẫn chứa managed instance, query có thể trả lại object đang được giữ mà không đọc mới như mong muốn.

---

## 12. Rollback với entity REMOVED

Giả sử đang xóa customer:

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
em.remove(customer);

tx.rollback();
```

Kết quả database: DELETE chưa commit bị hoàn tác, nên hàng trước đó có thể vẫn tồn tại (giả sử không có transaction khác thay đổi và rollback thành công).

Nhưng **không nên kết luận** object `customer` cũ đã tự động quay lại trạng thái managed bình thường và sẵn sàng để sửa tiếp. Sau rollback, nên tải lại entity bằng context mới nếu cần tiếp tục xử lý:

```java
EntityManager freshEm = emf.createEntityManager();

try {
    Customer existing = freshEm.find(Customer.class, customerId);
    // existing biểu diễn trạng thái có thể đọc trong context mới.
} finally {
    freshEm.close();
}
```

### 12.1. Không cố “undo remove” bằng cách persist lại cùng object

```java
em.remove(customer);
// Sau rollback:
em.persist(customer); // Không phải cách portable để khôi phục.
```

Đây không phải một phép đảo ngược lifecycle được bảo đảm. Muốn khôi phục dữ liệu hoặc tiếp tục nghiệp vụ, dùng transaction mới và đọc lại record; nếu muốn tạo lại một entity đã xóa thật, đó là một **use case mới** với chính sách ID, FK và audit rõ ràng.

---

## 13. Rollback với collection và quan hệ entity

Không chỉ field scalar, object graph cũng có thể đã thay đổi trong bộ nhớ.

Ví dụ:

```java
tx.begin();

PurchaseOrder order = em.find(PurchaseOrder.class, orderId);
order.addLine("PEN-01", 5);

tx.rollback();
```

Nếu `addLine` thêm object vào collection Java và thiết lập association, object graph có thể vẫn chứa `OrderLine` mới sau rollback trong reference mà application giữ, dù hàng child chưa bao giờ được commit.

Tương tự với:

- `order.removeLine(line)` và `orphanRemoval=true`.
- `employee.setDepartment(otherDepartment)`.
- `customer.getAddresses().clear()`.
- `product.getTags().add("new")`.

Sau rollback:

- Database phải phản ánh những dữ liệu đã commit trước đó, theo transaction semantics.
- Object graph Java có thể vẫn phản ánh các thao tác vừa thực hiện.
- Không nên tái sử dụng object graph đó trực tiếp cho transaction mới với giả định đã được phục hồi nguyên vẹn.
- Nếu cần tiếp tục, tải aggregate mới và tái áp dụng ý định nghiệp vụ đã được xác thực.

**Nguyên tắc:** rollback không phải “undo stack” cho các object Java và collection đã mutate.

---

## 14. Đóng EntityManager làm gì?

Với **application-managed EntityManager**, gọi:

```java
em.close();
```

là kết thúc việc sử dụng EntityManager đó. Persistence context gắn với nó kết thúc theo lifecycle hợp lệ và những managed entity còn lại trở thành detached.

### 14.1. Close không xóa bản ghi

```java
EntityManager em = emf.createEntityManager();

Customer customer;
try {
    customer = em.find(Customer.class, customerId);
} finally {
    em.close();
}

// customer còn là object Java, nhưng context đã đóng.
System.out.println(customer.getId());
```

Nếu dữ liệu đã được commit từ trước, hàng Customer vẫn tồn tại trong database. `em.close()` không có nghĩa `DELETE FROM customers`.

### 14.2. Close không phải commit

Sai cách hiểu:

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
customer.rename("Tên mới");

em.close(); // Không phải cách xác nhận transaction.
```

Không dùng close thay cho `tx.commit()`. Nếu transaction vẫn active, hành vi cleanup và lỗi khi đóng EM phụ thuộc transaction type/provider; JPA có quy tắc riêng cho EntityManager đang tham gia transaction. Một thiết kế đúng phải **kết thúc transaction bằng commit hoặc rollback theo kiểm soát rõ ràng** rồi mới đóng EM do ứng dụng quản lý.

Mẫu thông dụng:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        Customer customer = em.find(Customer.class, customerId);
        customer.rename("Tên mới");
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

### 14.3. Đóng EntityManagerFactory khác đóng EntityManager

`EntityManagerFactory` là factory thường được tạo một lần cho một persistence unit và được dùng để tạo nhiều EntityManager. Đóng EMF là thao tác lifecycle cấp ứng dụng, không phải cách commit các transaction con:

```java
EntityManagerFactory emf =
    Persistence.createEntityManagerFactory("demoPU");

try {
    EntityManager em = emf.createEntityManager();
    try {
        // Các thao tác...
    } finally {
        em.close();
    }
} finally {
    emf.close();
}
```

Không tạo/đóng EMF cho từng hàng dữ liệu như cách tạo/đóng EntityManager. Trong application container/Spring, framework thường quản lý những lifecycle này.

### 14.4. Close một injected EntityManager?

Trong container-managed JPA, ứng dụng **không tự gọi `close()` trên injected EntityManager** do container sở hữu. Container/framework quản lý lifecycle và có thể từ chối thao tác close trực tiếp.

Phân biệt:

- Application-managed `emf.createEntityManager()`: application chịu trách nhiệm close.
- Injected container-managed `@PersistenceContext`: container quản lý; ứng dụng không tự đóng.
- Spring proxy EntityManager: framework quản lý context/binding; không chủ động close proxy như EM tự tạo.

---

## 15. Đóng context ảnh hưởng đến lazy loading

Giả sử `Customer` có collection lazy:

```java
@OneToMany(mappedBy = "customer", fetch = FetchType.LAZY)
private List<PurchaseOrder> orders = new ArrayList<>();
```

Sau:

```java
Customer customer = em.find(Customer.class, customerId);
em.close();

customer.getOrders().size();
```

nếu collection `orders` chưa được load, Hibernate thường ném `LazyInitializationException` vì không còn session/persistence context hợp lệ để tải collection. Tên exception đó là của Hibernate, không phải một tên exception chung được JPA chuẩn hóa cho mọi provider.

### 15.1. Loaded field vẫn có thể đọc sau close

Đóng context **không hủy object Java**:

```java
System.out.println(customer.getId());
System.out.println(customer.getDisplayName());
```

Các field đã load vẫn có thể truy cập thông thường. Nhưng field/association chưa được nạp có thể gặp vấn đề nếu provider dùng cơ chế lazy loading.

### 15.2. Cách tránh phụ thuộc context sau response boundary

Một cách là trả DTO được xây dựng trong context còn hoạt động:

```java
public record CustomerView(Long id, String name) {}

Customer customer = em.find(Customer.class, customerId);

CustomerView view = new CustomerView(
    customer.getId(),
    customer.getDisplayName()
);
```

Nếu API cần cả đơn hàng:

- Truy vấn với fetch plan phù hợp.
- Hoặc query DTO/projection riêng.
- Chuyển các dữ liệu cần thiết thành DTO trước khi đóng context.
- Không mặc định bật EAGER cho mọi association chỉ để serializer có thể đi qua toàn bộ object graph.

### 15.3. Open EntityManager in View không kéo dài transaction mặc nhiên

Trong một số ứng dụng Spring web, Open EntityManager in View có thể giữ EntityManager còn mở đến lúc render view/serialize response. Điều đó đôi khi cho phép lazy loading sau khi service `@Transactional` đã kết thúc.

Nhưng **context còn mở không có nghĩa transaction service vẫn active**. Query phát trong giai đoạn view có thể chạy ngoài transaction ban đầu, gây N+1 hoặc dữ liệu không nhất quán theo thời điểm đọc. Không dựa vào OSIV như giải pháp thay cho fetch plan và transaction boundary rõ ràng.

---

## 16. clear(), detach() và close() khác nhau ở đâu?

Ba phương thức đều có thể khiến entity ngừng được theo dõi, nhưng mức tác động khác nhau.

| Phương thức | Tác động lên entity | EntityManager còn dùng được? | Có commit/rollback không? |
|---|---|---|---|
| `em.detach(entity)` | Detach đúng entity đó (và quan hệ tùy cascade DETACH) | Có | Không |
| `em.clear()` | Detach toàn bộ managed entities trong context | Có | Không |
| `em.close()` | Kết thúc application-managed EntityManager/context | Không dùng EM đó nữa | Không phải lệnh commit/rollback |

### 16.1. Ví dụ detach một entity

```java
Customer customer = em.find(Customer.class, customerId);

System.out.println(em.contains(customer)); // true

em.detach(customer);

System.out.println(em.contains(customer)); // false
```

Những entity khác có thể vẫn managed trong cùng context. Nếu entity có cascade `DETACH` trên association, propagation của detach cũng cần được tính đến.

### 16.2. Ví dụ clear toàn context

```java
Customer a = em.find(Customer.class, customerAId);
Customer b = em.find(Customer.class, customerBId);

em.clear();

System.out.println(em.contains(a)); // false
System.out.println(em.contains(b)); // false
```

`em` vẫn mở; ứng dụng có thể `em.find` lần nữa và nhận managed instances mới.

### 16.3. Thận trọng với thay đổi chưa flush

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
customer.rename("Tên chỉ sửa trong bộ nhớ");

em.clear();

tx.commit();
```

Vì entity đã được detach trước khi pending change được flush, thay đổi có thể **không được ghi**. Không coi `clear()` là “lưu rồi dọn bộ nhớ”.

Nếu đã có thao tác flush trước đó:

```java
tx.begin();

Customer customer = em.find(Customer.class, customerId);
customer.rename("Tên đã flush");
em.flush();

em.clear();

tx.commit();
```

SQL UPDATE đã được đồng bộ vào **transaction**, nên `clear()` không tự rollback SQL đó. Nếu commit thành công, thay đổi đã flush vẫn có thể được xác nhận.

Đây là điểm dễ nhầm: `clear` làm sạch **persistence context**, không trực tiếp đảo ngược dữ liệu đã được gửi tới database trong transaction.

---

## 17. Merge sau khi entity đã detached

Khi EntityManager đóng, object trở thành detached. Nếu muốn lưu thay đổi từ object cũ, phải phân biệt **object đầu vào** và **managed instance trả về từ merge**.

```java
Customer detached = obtainCustomerFromPreviousContext();
detached.rename("Tên sửa trên DTO/entity detached");

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Customer managedCopy = em.merge(detached);

    System.out.println(managedCopy == detached);
    // Thường false vì detached là object ngoài context.

    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
} finally {
    em.close();
}
```

Ý nghĩa:

- `merge(detached)` chuyển state thích hợp sang một managed instance.
- Input `detached` **không được biến thành managed** chỉ vì gọi merge.
- Muốn tiếp tục sửa trong transaction, dùng **giá trị trả về**.
- Merge có thể tác động đến association theo cascade MERGE và dễ copy những field ngoài ý muốn nếu input thiếu kiểm soát.

Với API nhận input từ client, một cách rõ ràng hơn là tải lại entity managed rồi áp dụng các field được phép:

```java
Customer managed = em.find(Customer.class, command.customerId());

if (managed == null) {
    throw new IllegalArgumentException("Customer not found");
}

managed.rename(command.displayName());
```

Điều này giúp kiểm soát permission, validation, invariant và optimistic locking. Trong ví dụ, `command` là DTO nghiệp vụ của ứng dụng, không phải API chuẩn JPA.

### 17.1. Không dùng merge như “undo rollback”

Sau rollback, state object cũ có thể chứa những thay đổi không được commit. Nếu merge nguyên object đó vào transaction mới, bạn có thể vô tình **ghi lại chính những thay đổi đáng lẽ đã hủy**.

Muốn retry, hãy phân biệt:

- **Input nghiệp vụ hợp lệ** muốn áp dụng lại.
- **State object đã mutate trước rollback** và có thể chứa giá trị không mong muốn.

Thông thường nên tải entity mới theo ID và chỉ tái áp dụng những thay đổi được người dùng xác nhận, chứ không merge cả graph bị rollback mà không kiểm tra.

---

## 18. Mẫu code Java SE an toàn: commit hoặc rollback rồi close

Dưới đây là một entity và chương trình minh họa riêng để thực hành.

### 18.1. Entity Customer

```java
package demo.jpa;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "display_name", nullable = false, length = 150)
    private String displayName;

    @Version
    @Column(name = "version")
    private Long version;

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

    public Long getVersion() {
        return version;
    }

    public void rename(String newName) {
        Objects.requireNonNull(newName, "displayName");

        String normalized = newName.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Name is blank");
        }
        this.displayName = normalized;
    }
}
```

`@Version` minh họa optimistic locking khi có nhiều transaction cập nhật cùng một row. Nó không quyết định entity đang managed hay detached; chức năng đó thuộc persistence context.

### 18.2. persistence.xml

Ví dụ file `src/main/resources/META-INF/persistence.xml` dành cho Java SE với Hibernate ORM và H2:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xsi:schemaLocation="
               https://jakarta.ee/xml/ns/persistence
               https://jakarta.ee/xml/ns/persistence/persistence_3_0.xsd"
             version="3.0">

    <persistence-unit name="entityLifecyclePU"
                      transaction-type="RESOURCE_LOCAL">

        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>demo.jpa.Customer</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:lifecycle_demo;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>

            <!-- Chỉ cho môi trường học tập, database tạm. -->
            <property name="hibernate.hbm2ddl.auto"
                      value="create-drop"/>
            <property name="hibernate.show_sql"
                      value="true"/>
            <property name="hibernate.format_sql"
                      value="true"/>
        </properties>
    </persistence-unit>
</persistence>
```

Cần dependency phù hợp: Jakarta Persistence API, Hibernate ORM provider và H2 JDBC driver. Những thuộc tính `hibernate.*` thuộc Hibernate; provider khác có cấu hình riêng.

**Không dùng `hibernate.hbm2ddl.auto=create-drop` trên database chứa dữ liệu thật** vì nó có thể tạo/xóa schema. Trong production, nên dùng migration được quản lý và cấu hình kết nối an toàn.

### 18.3. Chương trình commit rồi kiểm tra trạng thái

```java
package demo.jpa;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.Persistence;

public class LifecycleDemo {

    public static void main(String[] args) {
        EntityManagerFactory emf =
            Persistence.createEntityManagerFactory("entityLifecyclePU");

        try {
            Long id = createCustomer(emf);
            demonstrateCommitScope(emf, id);
            demonstrateDetachOnClose(emf, id);
        } finally {
            emf.close();
        }
    }

    private static Long createCustomer(EntityManagerFactory emf) {
        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();

            try {
                Customer customer = new Customer("Customer A");
                em.persist(customer);
                tx.commit();

                return customer.getId();
            } catch (RuntimeException failure) {
                rollbackIfActive(tx, failure);
                throw failure;
            }
        } finally {
            em.close();
        }
    }

    private static void demonstrateCommitScope(
            EntityManagerFactory emf, Long id) {

        EntityManager em = emf.createEntityManager();

        try {
            EntityTransaction tx = em.getTransaction();
            tx.begin();

            try {
                Customer customer = em.find(Customer.class, id);
                customer.rename("After commit");

                tx.commit();

                System.out.println(
                    "EM still open = " + em.isOpen());

                System.out.println(
                    "Still managed after commit = "
                        + em.contains(customer));
            } catch (RuntimeException failure) {
                rollbackIfActive(tx, failure);
                throw failure;
            }
        } finally {
            em.close();
        }
    }

    private static void demonstrateDetachOnClose(
            EntityManagerFactory emf, Long id) {

        EntityManager em = emf.createEntityManager();
        Customer customer;

        try {
            customer = em.find(Customer.class, id);

            System.out.println(
                "Managed before close = " + em.contains(customer));
        } finally {
            em.close();
        }

        // Object Java vẫn tồn tại, dù context đã đóng.
        customer.rename("Changed on detached object");

        EntityManager freshEm = emf.createEntityManager();

        try {
            Customer fresh = freshEm.find(Customer.class, id);
            System.out.println(
                "Database name = " + fresh.getDisplayName());
        } finally {
            freshEm.close();
        }
    }

    private static void rollbackIfActive(
            EntityTransaction tx, RuntimeException original) {

        if (tx.isActive()) {
            try {
                tx.rollback();
            } catch (RuntimeException rollbackFailure) {
                original.addSuppressed(rollbackFailure);
            }
        }
    }
}
```

Các hành vi quan sát được theo mô hình application-managed `RESOURCE_LOCAL`:

- Sau commit, EntityManager vẫn mở cho đến khi code gọi `close()`.
- Với EM đó, entity có thể vẫn managed sau commit.
- Khi EM đóng, object thành detached.
- Đổi tên trên detached object **không tự ghi database**.
- EM mới đọc dữ liệu đã commit, không tự lấy giá trị setter vừa gọi trên detached object.

Mã này dùng `Customer` trong cùng package và xử lý transaction rollback một cách tường minh. Mục tiêu là quan sát lifecycle; chưa bao gồm các yêu cầu nghiệp vụ như kiểm tra quyền, logging và retry.

---

## 19. Bài thực hành: kiểm chứng từng trạng thái

Để quan sát chính xác trên stack đang dùng, hãy bật SQL log và mở EntityManager mới khi cần xác minh dữ liệu đã commit.

### Phần A — NEW → MANAGED → COMMIT

1. Tạo `new Customer("An")`.
2. Kiểm tra ID trước `persist()`.
3. Bắt đầu transaction.
4. Gọi `em.persist(customer)`.
5. Dùng `em.contains(customer)` khi EM còn mở.
6. Commit.
7. Kiểm tra `em.isOpen()` và `em.contains(customer)` trên application-managed EM.
8. Đóng EM, rồi đọc lại customer từ EM mới.

Câu hỏi: **Commit đã đóng EntityManager hay chưa?** Vì sao dữ liệu vẫn còn sau khi EM đóng?

### Phần B — UPDATE → FLUSH → ROLLBACK

1. Đọc một Customer đã commit.
2. Trong transaction, đổi `displayName`.
3. Gọi `em.flush()`.
4. Quan sát log `UPDATE`.
5. Gọi `tx.rollback()`.
6. In `customer.getDisplayName()` của object Java cũ.
7. Đóng EM và dùng EM mới để đọc database.
8. Giải thích sự khác nhau giữa hai giá trị.

Câu hỏi: **SQL đã xuất hiện có đồng nghĩa với thay đổi bền vững không?**

### Phần C — INSERT → ROLLBACK với IDENTITY

1. Bắt đầu transaction.
2. Persist Customer mới dùng `GenerationType.IDENTITY`.
3. Ghi ID trước và sau persist.
4. Rollback.
5. Đóng EM và mở EM mới.
6. Tìm lại entity theo ID nếu ID khác null.
7. Giải thích vì sao ID có thể tồn tại trong Java mà hàng không tồn tại trong DB.
8. Thử retry bằng cách tạo object mới từ input; không giả định repersist object cũ là portable.

### Phần D — REMOVE → COMMIT

1. Tạo customer, commit.
2. Trong EM mới, tải customer.
3. Bắt đầu transaction và gọi `em.remove(customer)`.
4. Ghi nhận trạng thái theo API thích hợp khi context còn mở.
5. Commit.
6. Dùng EM mới gọi `find(Customer.class, id)`.
7. Giải thích vì sao object Java cũ vẫn có field nhưng row không còn.

### Phần E — REMOVE → ROLLBACK

1. Tạo customer và commit.
2. Bắt đầu transaction mới, tải entity.
3. Gọi `remove`, tùy chọn `flush` để quan sát DELETE.
4. Rollback.
5. Không tái sử dụng object cũ như managed entity.
6. Dùng EM mới đọc lại cùng ID và xác nhận dữ liệu đã commit ban đầu.
7. Giải thích vì sao không “undo remove” bằng `persist` object cũ.

### Phần F — CLEAR trước và sau FLUSH

Tạo hai trường hợp:

**Trường hợp 1:**

```java
tx.begin();
customer.rename("Change A");
em.clear();
tx.commit();
```

**Trường hợp 2:**

```java
tx.begin();
customer.rename("Change B");
em.flush();
em.clear();
tx.commit();
```

Trong từng trường hợp, cần tải lại managed Customer phù hợp ở đầu transaction; không dùng object detached từ trường hợp trước mà tưởng vẫn managed. Quan sát dữ liệu sau commit bằng EM mới.

Câu hỏi: **clear làm mất pending changes hay rollback SQL đã flush?** Hai tình huống khác nhau ở điểm nào?

### Phần G — Hai transaction cùng application-managed EM

1. Tạo một EM.
2. TX #1 load Customer và commit.
3. Sau commit, gọi `em.contains(customer)`.
4. TX #2 sửa cùng object và commit.
5. Đóng EM.
6. Giải thích vì sao persistence context có thể vượt qua cả hai transaction.

### Phần H — Transaction-scoped context qua service

Nếu có Jakarta EE hoặc Spring:

1. Tạo service transaction-scoped.
2. Trong một transaction, load Customer và gọi hai lần `find`.
3. Kiểm tra Java identity trong cùng context.
4. Kết thúc transaction.
5. Gọi service lần hai với transaction mới.
6. Không dựa vào reference từ lần gọi đầu là managed ở lần gọi sau.
7. So sánh với application-managed EM ở Phần G.

### Bảng ghi chép kết quả

| Kịch bản | Trạng thái object Java sau thao tác | Trạng thái hàng DB sau commit/rollback | Điều cần ghi nhận |
|---|---|---|---|
| Persist rồi commit | Managed hoặc detached tùy scope | Hàng đã được commit | Context có còn mở? |
| Update rồi commit | Managed hoặc detached tùy scope | Field mới được commit | Dirty checking/flush |
| Update rồi rollback | Không tin state object cũ | DB giữ state trước TX | Java setter không được undo |
| Insert rồi rollback | Object có thể vẫn giữ ID | Không có hàng được commit bởi TX | ID không chứng minh thành công |
| Remove rồi commit | Không còn đại diện hàng tồn tại | Hàng bị xóa | Object Java không tự biến mất |
| Remove rồi rollback | Không giả định object cũ managed bình thường | DELETE bị hoàn tác | Load lại trong context mới |
| Close sau commit | Detached | DB vẫn giữ dữ liệu đã commit | Close không xóa row |
| Clear trước flush | Detached | Pending state có thể không được lưu | Clear không phải save |
| Clear sau flush, rồi commit | Detached | SQL đã flush có thể được commit | Clear không rollback |
| Hai TX, một application-managed EM | Có thể giữ managed xuyên TX | Mỗi TX commit độc lập | Scope context khác scope TX |

---

## 20. Những tình huống lỗi cần phân tích

### 20.1. Gọi persist rồi trả HTTP 200 trước khi transaction commit

```java
em.persist(order);
return ResponseEntity.ok(order.getId());
```

Nếu transaction commit diễn ra sau khi return và thất bại, ID đã được trả không bảo đảm đơn hàng đã được lưu. Trong framework, transaction interceptor thường commit quanh method call trước khi kết quả được hoàn tất theo luồng thích hợp, nhưng phải hiểu chính xác ranh giới request/service.

Khi thiết kế API, chỉ coi thao tác tạo thành công khi **transaction đã kết thúc thành công**, hoặc dùng mô hình asynchronous processing có trạng thái công việc rõ ràng. ID không thay thế outcome của transaction.

### 20.2. Cố sửa entity sau khi EntityManager đóng

```java
Customer customer = loadCustomer();
customer.rename("New name");
```

Nếu `loadCustomer()` trả entity detached vì context đã đóng, setter chỉ sửa Java object. Không có dirty checking tự động. Cần một transaction mới với managed entity và cập nhật được kiểm soát.

### 20.3. Gọi merge rồi tiếp tục sửa detached input

```java
Customer managed = em.merge(detached);

detached.rename("Last minute change");
// Sửa detached không phải sửa managed.
```

Nếu muốn sửa tiếp trong transaction, dùng `managed.rename(...)`. Nếu chỉ bỏ qua giá trị trả về từ merge, code rất dễ ghi thiếu dữ liệu.

### 20.4. Sau rollback vẫn dùng entity cũ trong service khác

Một object cũ có thể chứa:

- ID của hàng chưa commit.
- Field thay đổi không còn đúng với database.
- Collection đã thêm/bớt phần tử.
- Tham chiếu association đã đổi.
- Version cũ hoặc state không còn phù hợp.

Truyền object đó sang service khác rồi merge máy móc có thể ghi lại dữ liệu vừa rollback. Nên truyền **ID và input nghiệp vụ** để service mới tải lại state và quyết định.

### 20.5. Giữ EntityManager trong singleton cho nhiều request

`EntityManager` và persistence context không được dùng đồng thời tùy tiện giữa các thread. Nếu tạo một EM toàn ứng dụng và chia sẻ, rất dễ gặp stale state, race condition hoặc transaction lẫn nhau.

Dùng `EntityManagerFactory` theo lifecycle ứng dụng; để container/framework cấp EM theo unit of work, hoặc ứng dụng tự tạo/đóng EM trong phạm vi phù hợp.

### 20.6. Gọi close khi transaction vẫn active

Đừng dựa vào `close()` để quyết định commit/rollback một transaction đang hoạt động. Có các quy tắc khác nhau theo RESOURCE_LOCAL/JTA/provider và trạng thái transaction. Pattern rõ nhất là **commit hoặc rollback trước**, sau đó close application-managed EM trong `finally`.

### 20.7. Nhầm rollback với xóa entity

Rollback chỉ hủy những thay đổi **trong transaction bị rollback**. Nó không xóa bản ghi đã được commit trong một transaction trước:

```text
TX #1:
  INSERT Customer#10
  COMMIT

TX #2:
  UPDATE Customer#10
  ROLLBACK

Customer#10 vẫn tồn tại với dữ liệu đã commit ở TX #1.
```

### 20.8. Nhầm “cùng ID” với “cùng Java instance”

Hai context khác nhau có thể load cùng database identity vào hai object khác nhau:

```java
Customer a = emA.find(Customer.class, 10L);
Customer b = emB.find(Customer.class, 10L);

System.out.println(a == b); // Thường false.
```

First-level cache chỉ bảo đảm identity trong một persistence context. Với detached entities, equality/hashCode cần thiết kế rõ nếu ứng dụng dùng entity trong Set/Map hoặc so sánh qua nhiều request.

---

## 21. Optimistic locking, version và rollback

Với entity có:

```java
@Version
private Long version;
```

provider có thể phát hiện khi một transaction cố cập nhật entity dựa trên version cũ.

Ví dụ:

```text
TX A đọc Customer#10 version=2.
TX B đọc Customer#10 version=2.

TX B:
  đổi tên, commit -> version=3.

TX A:
  đổi tên, flush/commit -> xung đột version.
  Có thể nhận OptimisticLockException.
```

Khi gặp optimistic locking conflict:

- Transaction có thể bị đánh dấu rollback-only.
- Không cố commit tiếp cùng unit of work.
- Rollback đúng quy trình.
- Không tái sử dụng nguyên managed graph cũ như thể đã đồng bộ.
- Tải state mới từ database và quyết định conflict resolution theo nghiệp vụ.

`@Version` không tự định nghĩa scope của persistence context. Một context dài vẫn có thể giữ version cũ và gặp xung đột khi ghi.

### 21.1. Retry không phải tự động lặp commit vô hạn

Một retry an toàn cần:

- Biết transaction trước thực sự thất bại hoặc xác định outcome.
- Tạo unit of work/context mới phù hợp.
- Tải lại state và kiểm tra invariant.
- Tái áp dụng yêu cầu có ý nghĩa nghiệp vụ.
- Giới hạn số lần thử.
- Có idempotency khi tạo dữ liệu hoặc thực hiện tác động bên ngoài.

Đặc biệt với thanh toán, gửi email hoặc gọi API bên ngoài, transaction database không tự rollback tác động ở hệ thống khác. Khi cần phối hợp, cân nhắc outbox/event-driven workflow thay vì gắn tác động bên ngoài trực tiếp với niềm tin “rollback sẽ undo tất cả”.

---

## 22. Transaction-scoped, application-managed và extended: bảng tổng kết

| Tình huống | Ai quản lý context? | Commit có chấm dứt context? | Sau rollback cần lưu ý gì? | Đóng như thế nào? |
|---|---|---|---|---|
| Container-managed transaction-scoped | Container/JTA | Thông thường có, theo transaction | Context của TX kết thúc; object cũ không dùng như managed | Container quản lý |
| Spring transaction-bound context (cấu hình thông dụng) | Spring transaction manager | Thông thường gắn với TX; cần xét OSIV/cấu hình | Không giữ entity cũ làm bằng chứng DB state | Framework quản lý |
| Application-managed RESOURCE_LOCAL | Ứng dụng tạo EM | **Không**, nếu EM còn mở | Context/state sau rollback cần cleanup và tải lại cẩn thận | `em.close()` sau TX |
| Container-managed extended | Container, theo component stateful | **Không**, context có thể qua nhiều TX | Context dài có thể chứa state chưa phù hợp sau rollback | Container kết thúc lifecycle |
| Context bị `clear()` | Đối tượng quản lý vẫn còn | Không áp dụng; context còn mở nhưng entity bị detach | Pending state có thể mất khỏi PC | Có thể tiếp tục dùng EM |
| Context bị `close()` | Application-managed EM | Không phải transaction operation | Không thể tiếp tục dùng EM cũ | Đã đóng |

**Chú ý:** Spring OSIV có thể giữ EM đến cuối request, lâu hơn transaction service. Các trường hợp container-managed và JTA có quy tắc synchronization/propagation riêng. Vì vậy cần xác định **loại context thực tế**, không chỉ nhìn thấy annotation `@Transactional`.

---

## 23. Sơ đồ tổng hợp theo ba thao tác

### 23.1. Commit

```text
new Customer()
      |
      | em.persist()
      v
  MANAGED
      |
      | flush/commit thành công
      v
DB lưu dữ liệu
      |
      +-- TRANSACTION-SCOPED context kết thúc
      |      -> Java entity trở thành DETACHED
      |
      +-- APPLICATION-MANAGED EM vẫn mở
      |      -> Java entity có thể tiếp tục MANAGED
      |
      +-- EXTENDED context vẫn sống
             -> Java entity có thể tiếp tục MANAGED
```

### 23.2. Rollback

```text
MANAGED entity trong TX
      |
      | mutate fields, persist, remove, collection changes
      v
Java object graph đã bị thay đổi
      |
      | flush có thể đã phát SQL
      |
      | tx.rollback()
      v
Database hủy các thao tác chưa commit
      |
      +-- Java object không nhất thiết tự trở về giá trị trước TX
      +-- Generated ID có thể vẫn còn trên object
      +-- State context/object sau rollback không nên mặc định an toàn

Cách tiếp tục:
  kết thúc/clear context phù hợp
        -> tạo unit of work mới
        -> load lại managed entity
        -> áp dụng input nghiệp vụ hợp lệ
```

### 23.3. Đóng context

```text
Application-managed EntityManager OPEN
      |
      +-- managed Customer#10
      +-- managed Order#20
      |
      | em.close()
      v
EntityManager CLOSED
      |
      +-- Customer#10 detached
      +-- Order#20 detached
      |
      +-- Không tự commit những thay đổi pending
      +-- Không tự DELETE các hàng đã commit
      +-- Không tiếp tục dùng EntityManager đã đóng
```

---

## 24. Câu hỏi ôn tập

1. Khác biệt giữa trạng thái managed và sự tồn tại của row trong database là gì?
2. Vì sao `id != null` không đủ để chứng minh entity đang managed?
3. `em.persist` biến new entity thành trạng thái nào?
4. Khi update managed entity nhưng chưa flush, database có nhất thiết nhận SQL chưa?
5. `flush()` khác `commit()` ở điểm nào?
6. Vì sao một transaction có `INSERT` đã chạy vẫn có thể rollback?
7. Khi commit thành công, entity có luôn detached không?
8. Với transaction-scoped context, điều gì xảy ra khi transaction kết thúc?
9. Vì sao EntityManager application-managed có thể còn giữ managed entity sau commit?
10. Extended persistence context có kéo dài một database transaction xuyên nhiều request không?
11. Khi rollback UPDATE, vì sao Java object có thể vẫn giữ giá trị mới?
12. Khi rollback INSERT dùng IDENTITY, vì sao ID Java có thể còn dù hàng database không tồn tại?
13. Sau rollback REMOVE, có nên dùng `persist` để “undo” trên cùng object cũ không?
14. `em.close()` có tự commit hoặc rollback một transaction đang active không?
15. Vì sao phải commit/rollback rõ ràng trước khi close?
16. `em.detach`, `em.clear`, `em.close` khác nhau ở phạm vi tác động nào?
17. Nếu `clear` trước khi flush, thay đổi field của managed entity có thể bị gì?
18. Nếu `flush` rồi `clear` trong transaction, tại sao SQL đã thực thi vẫn có thể được commit?
19. Khi entity detached thay đổi, provider có tự dirty checking không?
20. `merge(detached)` có biến chính object `detached` thành managed không?
21. Khi context đóng, vì sao field đã load vẫn đọc được nhưng lazy collection có thể không tải được?
22. Sau rollback, cách an toàn nhất để tiếp tục xử lý cùng entity là gì?
23. Một optimistic lock exception thường yêu cầu xử lý transaction/context thế nào?
24. Tại sao không nên chia sẻ một EntityManager singleton cho nhiều HTTP request?
25. Nếu việc ghi database đã rollback nhưng email đã gửi, vì sao transaction không thể “undo” email?

---

## 25. Nguyên tắc áp dụng trong dự án thực tế

Khi thiết kế một phương thức service JPA, hãy viết rõ:

1. **Scope quản lý:** EntityManager/context được ai tạo và kết thúc khi nào?
2. **Ranh giới transaction:** trường hợp thành công commit ở đâu, trường hợp lỗi rollback ở đâu?
3. **Đầu vào:** entity managed, ID hay DTO? Không tin tưởng detached graph từ client là state cần ghi toàn bộ.
4. **Thao tác lifecycle:** tạo mới cần `persist`, sửa managed dùng dirty checking, xóa managed dùng `remove`, cập nhật detached cần quy trình reload/merge phù hợp.
5. **Sau commit:** cần entity còn managed không? Có đang giữ object ngoài context hay trả DTO cho client?
6. **Sau rollback:** có bỏ state cũ/đóng context đúng cách không? Retry có được thiết kế rõ?
7. **Sau close:** code còn truy cập lazy association hay cố gọi EntityManager đã đóng không?
8. **Đồng thời:** có `@Version`, unique/FK constraint và chính sách conflict/idempotency không?
9. **Quan sát:** kiểm tra row DB bằng context mới, SQL log và kết quả transaction; không suy từ một giá trị ID hoặc một dòng log.
10. **Khả năng phục hồi:** tác động bên ngoài như email/message/payment có được quản lý tách biệt với rollback DB không?

### Tóm lược một câu

**Commit xác nhận transaction; rollback hủy những thay đổi database chưa commit; đóng persistence context chấm dứt việc quản lý entity.** Ba thao tác này ảnh hưởng đến vòng đời entity theo những cách khác nhau và không thể thay thế cho nhau. Muốn hiểu đúng một object sau thao tác, luôn xác định cả **trạng thái Java trong persistence context** lẫn **trạng thái đã commit trong database**, cùng loại context đang sử dụng.

