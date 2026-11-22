# Persistence context, dirty checking và thao tác flush khi xử lý nhiều bản ghi

Trong ứng dụng Java dùng JPA/Hibernate, gọi `persist()` hoặc thay đổi thuộc tính của entity không nhất thiết gửi SQL ngay xuống database. ORM thường quản lý entity trong một **persistence context**, theo dõi trạng thái của chúng và đồng bộ thay đổi xuống database khi thực hiện **flush**. Cơ chế này giúp code nghiệp vụ làm việc với object, nhưng nếu xử lý hàng nghìn hoặc hàng triệu bản ghi mà không quản lý persistence context, bộ nhớ có thể tăng liên tục, dirty checking tốn thêm CPU và số câu SQL thực tế có thể lớn hơn dự kiến.

Bài học thuộc chương **Ứng dụng Java** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, tối ưu persistence context, dirty checking và flush cần xem đồng thời chi phí ORM ở JVM, số lần round trip JDBC, transaction/lock ở database và tính đúng đắn của dữ liệu sau mỗi lô.

## 1. Persistence context là gì?

Persistence context là vùng quản lý các entity mà một `EntityManager` đang theo dõi. Trong Hibernate, khái niệm tương ứng thường được gọi là first-level cache hoặc persistence context của `Session`.

Persistence context đảm nhiệm một số việc:

- Theo dõi entity đang managed và trạng thái của chúng.
- Duy trì identity map: trong cùng persistence context, một entity với cùng entity type và primary key được biểu diễn bởi cùng một object managed.
- Giữ thông tin cần thiết để phát hiện thay đổi so với trạng thái đã nạp hoặc đã đồng bộ.
- Lập lịch INSERT, UPDATE và DELETE để thực hiện khi flush.
- Phối hợp với cascade, relationship management và cơ chế đồng bộ của ORM.

Ví dụ:

```java
Order first = entityManager.find(Order.class, 100L);
Order second = entityManager.find(Order.class, 100L);

assert first == second;
```

Trong cùng persistence context, lần tìm thứ hai thường trả về object đã được quản lý thay vì tạo một object managed khác cho cùng identity. Điều này giúp tránh nhiều bản sao trạng thái của cùng một hàng trong một unit of work.

Persistence context không phải shared cache toàn hệ thống. Nó thường có phạm vi một transaction hoặc một unit of work; JPA cũng có extended persistence context trong một số mô hình. First-level cache thuộc từng persistence context, trong khi second-level cache của provider là cơ chế riêng có phạm vi rộng hơn.

### 1.1. Persistence context và transaction

Trong ứng dụng Java thông thường, một transaction service method thường dùng một persistence context gắn với transaction. Khi transaction kết thúc, persistence context transaction-scoped thường được đóng hoặc kết thúc theo lifecycle của container/framework.

Không nên chia sẻ một `EntityManager` đang hoạt động giữa nhiều thread. `EntityManager` và persistence context không được thiết kế để nhiều thread đồng thời thao tác như một object thread-safe. Mỗi transaction hoặc unit of work cần dùng context đúng phạm vi.

## 2. Các trạng thái vòng đời của entity

JPA mô tả các trạng thái chính của entity:

| Trạng thái | Ý nghĩa | Ví dụ thao tác |
|---|---|---|
| New/Transient | Object mới, chưa được persistence context quản lý và chưa có identity được quản lý trong DB | `new Order()` |
| Managed/Persistent | Entity đang được persistence context theo dõi | `persist()`, `find()`, truy vấn trả entity managed |
| Detached | Entity từng managed nhưng hiện không còn được context theo dõi | Sau `clear()`, `detach()` hoặc đóng context |
| Removed | Entity managed đã được đánh dấu xóa khi đồng bộ | `remove(entity)` |

Ví dụ:

```java
Order order = new Order();                 // transient
entityManager.persist(order);              // managed
order.setStatus(OrderStatus.CONFIRMED);    // thay đổi trên managed entity
entityManager.detach(order);               // detached
```

Khi entity detached, thay đổi tiếp theo trên object không còn được persistence context hiện tại tự động phát hiện. Nếu cần lưu trạng thái detached, có thể dùng `merge()` theo đúng semantics của JPA.

### 2.1. `persist()` và `merge()` không giống nhau

`persist()` đưa entity mới vào trạng thái managed. `merge()` sao chép trạng thái từ object truyền vào sang một instance managed và trả về instance đó. Object ban đầu không vì gọi `merge()` mà tự trở thành managed.

```java
Order detached = loadOutsideCurrentContext();
detached.setStatus(OrderStatus.PAID);

Order managed = entityManager.merge(detached);
managed.setNote("Đã đối soát");
```

Các thay đổi cần theo dõi tiếp nên thực hiện trên `managed`. Nếu tiếp tục sửa `detached`, persistence context không tự theo dõi những thay đổi đó. Gọi `merge()` cho một object detached lớn trong vòng lặp có thể làm tăng công việc đọc, sao chép và đồng bộ; với batch insert mới, `persist()` thường phù hợp hơn.

## 3. Dirty checking hoạt động thế nào?

Dirty checking là cơ chế ORM phát hiện entity managed đã thay đổi để tạo SQL UPDATE khi flush. Thay vì bắt ứng dụng gọi `update()` cho từng object, ORM so sánh trạng thái hiện tại với trạng thái đã biết hoặc dùng cơ chế theo dõi thay đổi để xác định thuộc tính nào bị sửa.

Ví dụ:

```java
Order order = entityManager.find(Order.class, 100L);
order.setStatus(OrderStatus.SHIPPED);

// Chưa nhất thiết có SQL UPDATE tại dòng setStatus().
entityManager.flush();
```

Khi flush, Hibernate/JPA phát hiện `status` thay đổi và có thể phát SQL tương tự:

```sql
UPDATE orders
SET status = ?
WHERE order_id = ?;
```

SQL thực tế phụ thuộc mapping, version column, dynamic update, dialect và provider. Một số provider có thể cập nhật toàn bộ cột được map trong UPDATE; không nên giả định SQL luôn chỉ chứa đúng một cột đã thay đổi.

### 3.1. Snapshot-based dirty checking

Một cách triển khai phổ biến là lưu snapshot trạng thái entity khi nạp hoặc sau khi đồng bộ. Khi flush, ORM so sánh trạng thái hiện tại với snapshot để xác định entity dirty. Cách này đơn giản về mặt khái niệm nhưng có chi phí:

- Bộ nhớ để giữ entity và trạng thái cần so sánh.
- CPU để duyệt entity/thuộc tính khi flush.
- Công việc tạo SQL và bind parameter cho entity thay đổi.
- Chi phí quản lý collection và association nếu chúng cũng thay đổi.

Nếu persistence context chứa hàng trăm nghìn entity managed, một lần flush có thể phải kiểm tra một lượng object lớn, kể cả entity không thay đổi. Chi phí thực tế phụ thuộc provider, mapping và enhancement.

### 3.2. Bytecode enhancement và change tracking

Hibernate có thể dùng bytecode enhancement để theo dõi thuộc tính thay đổi ở mức chi tiết hơn, tùy cấu hình và phiên bản. Cách này có thể giảm công việc so sánh snapshot trong một số trường hợp, nhưng không loại bỏ chi phí giữ entity managed, quan hệ, collection hoặc dirty entity. Không nên bật enhancement chỉ vì nghe nói dirty checking chậm; hãy đo trên mapping và workload thực tế.

### 3.3. Dirty checking không đồng nghĩa ghi ngay

Lệnh setter chỉ thay đổi object trong JVM. Dirty checking thường được xử lý ở thời điểm flush. Trước flush, dữ liệu trong persistence context có thể khác dữ liệu đã commit trong database. Nếu transaction rollback, thay đổi chưa commit sẽ không trở thành dữ liệu bền vững.

## 4. Flush là gì và khác commit thế nào?

**Flush** đồng bộ các thay đổi đang được persistence context quản lý xuống database bằng cách phát các câu SQL cần thiết. **Commit** kết thúc transaction thành công và làm các thay đổi của transaction trở nên bền vững theo transaction semantics của database.

| Thao tác | Ý nghĩa | Có kết thúc transaction không? |
|---|---|---|
| `persist()` | Đưa entity mới vào persistence context | Không |
| Sửa thuộc tính entity managed | Thay đổi trạng thái trong JVM, ORM theo dõi | Không |
| `flush()` | Gửi SQL đồng bộ các thay đổi xuống DB trong transaction hiện tại | Không |
| `commit()` | Commit transaction; provider thường flush trước commit theo quy tắc JPA | Có |
| `rollback()` | Hủy các thay đổi chưa commit theo transaction | Có |

Flush không đồng nghĩa commit. Sau flush, SQL có thể đã chạy và constraint có thể đã được kiểm tra, nhưng transaction vẫn mở; transaction khác thông thường chưa nhìn thấy thay đổi chưa commit theo isolation level của DB. Nếu sau đó rollback, thay đổi đã flush vẫn bị rollback.

### 4.1. Vì sao cần flush tường minh?

Flush tường minh có thể hữu ích khi:

- Muốn phát hiện sớm constraint violation trước một bước xử lý tiếp theo.
- Muốn bảo đảm thay đổi pending được đồng bộ trước một truy vấn hoặc native SQL cụ thể.
- Muốn giải phóng một phần trạng thái pending khỏi persistence context bằng cặp `flush()` và `clear()` trong batch.
- Muốn đo riêng chi phí đồng bộ SQL thay vì để nó dồn vào cuối transaction.

Không nên gọi `flush()` sau từng entity mà không có lý do. Flush quá thường xuyên có thể chia nhỏ JDBC batches, tăng round trip và làm mất cơ hội gộp câu lệnh.

### 4.2. Flush không giải phóng lock và transaction resource

Flush gửi SQL xuống DB nhưng transaction vẫn mở. Lock do transaction giữ có thể tiếp tục tồn tại cho đến commit/rollback; snapshot và transaction resource cũng có thể tiếp tục được giữ. Vì vậy, `flush()` không thay thế việc chia transaction khi cần giảm thời gian giữ lock hoặc giới hạn lượng công việc rollback.

## 5. Khi nào JPA/Hibernate tự động flush?

Thời điểm flush phụ thuộc flush mode, provider và loại thao tác.

### 5.1. `FlushModeType.AUTO`

Đây là flush mode mặc định theo JPA trong nhiều tình huống. Provider phải bảo đảm thay đổi cần thiết được đồng bộ để truy vấn nhìn thấy các thay đổi có liên quan theo semantics của JPA. Hibernate thường có thể flush trước một query khi query có thể bị ảnh hưởng bởi các thay đổi pending trong persistence context.

Ví dụ:

```java
entityManager.persist(new Product("SKU-01", "Bàn phím"));

// Provider có thể flush trước truy vấn nếu cần để bảo đảm kết quả đúng.
List<Product> products = entityManager.createQuery(
    "select p from Product p where p.sku = :sku", Product.class)
    .setParameter("sku", "SKU-01")
    .getResultList();
```

Không nên dựa vào chi tiết provider sẽ flush ở mọi query theo cùng một cách. Hãy xem SQL log và tài liệu phiên bản đang dùng.

### 5.2. `FlushModeType.COMMIT`

Chế độ này hướng đến việc flush khi commit. Provider vẫn có thể flush sớm trong một số trường hợp; không nên giả định `COMMIT` cấm mọi flush trước commit. Cũng không nên dựa vào một truy vấn JPQL sẽ phản ánh mọi thay đổi pending nếu chưa đồng bộ, trừ khi semantics và provider bảo đảm.

### 5.3. Flush mode riêng của Hibernate

Hibernate cung cấp các flush mode riêng ngoài enum JPA trong API native, chẳng hạn `MANUAL`, `COMMIT`, `AUTO` hoặc `ALWAYS` tùy phiên bản. `MANUAL` trao trách nhiệm flush nhiều hơn cho ứng dụng và có thể làm thay đổi thời điểm dữ liệu được gửi xuống DB. Chỉ dùng khi hiểu rõ lifecycle transaction và kiểm thử đầy đủ; quên flush có thể khiến thay đổi không được đồng bộ như mong đợi.

## 6. Thứ tự SQL khi flush

Hibernate không nhất thiết phát SQL theo đúng thứ tự các lệnh Java được gọi. Provider quản lý action queue và có thể sắp xếp thao tác theo loại để bảo đảm ràng buộc và tận dụng batching. Thứ tự thường gặp có thể gồm insert, update, collection operations và delete theo quy tắc nội bộ, nhưng không nên dựa vào thứ tự cụ thể ngoài hợp đồng của provider.

Điều này quan trọng khi:

- Có foreign key giữa entity cha và con.
- Có unique constraint mà các thao tác thay đổi giá trị có thể tạm thời xung đột.
- Nhiều transaction cập nhật các hàng theo thứ tự khác nhau, gây deadlock.
- Bật `hibernate.order_inserts` hoặc `hibernate.order_updates` để gom câu lệnh tương thích.

Nếu thứ tự nghiệp vụ quan trọng, hãy biểu diễn quan hệ và constraint đúng, chia transaction hợp lý và kiểm thử với database thật. Không dựa vào việc gọi `persist()` trước hay sau để suy ra chắc chắn thứ tự SQL.

## 7. Vì sao xử lý nhiều entity trong một persistence context gây tốn bộ nhớ?

Khi gọi `persist()` cho mỗi bản ghi, entity managed thường được giữ trong persistence context cho đến khi detach, clear hoặc context kết thúc. ORM cần giữ identity map, snapshot/change tracking, collection và association liên quan.

Ví dụ vòng lặp sau có thể làm persistence context lớn dần:

```java
for (OrderInput input : inputs) {
    Order order = new Order(input.customerId(), input.totalAmount());
    entityManager.persist(order);
}
```

Nếu `inputs` có hàng trăm nghìn phần tử, số entity managed có thể tăng tương ứng. Hậu quả có thể gồm:

- Heap usage tăng và GC hoạt động thường xuyên hơn.
- Dirty checking phải xét nhiều entity khi flush.
- Snapshot và collection metadata chiếm thêm bộ nhớ.
- Flush cuối transaction tạo lượng SQL lớn và kéo dài.
- Transaction giữ lock lâu, tăng khả năng blocking và chi phí rollback.
- JDBC batch không được tận dụng tốt nếu flush quá muộn hoặc statement shape không tương thích.

Không phải mọi entity đều có cùng kích thước. Quan hệ hai chiều, collection lớn, eager loading, bytecode enhancement và trạng thái thay đổi có thể làm chi phí khác nhau đáng kể.

## 8. Flush và clear theo từng lô

Với batch lớn, một mẫu thường dùng là flush định kỳ rồi clear persistence context để giải phóng các entity managed đã xử lý:

```java
@Transactional
public void importOrders(List<OrderInput> inputs) {
    int batchSize = 50;

    for (int i = 0; i < inputs.size(); i++) {
        OrderInput input = inputs.get(i);
        Order order = new Order(input.customerId(), input.totalAmount());
        entityManager.persist(order);

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Ý nghĩa:

- `flush()` phát SQL cho các thay đổi pending trong context.
- `clear()` detach tất cả entity đang managed trong context hiện tại.
- Sau `clear()`, các entity đã xử lý không còn được giữ như managed entities trong persistence context đó.
- Cuối vòng lặp cần xử lý phần còn lại chưa đủ một batch.

`clear()` tác động đến toàn bộ entity managed trong context, không chỉ entity được tạo trong vòng lặp. Nếu context đang quản lý entity khác mà code còn cần thay đổi tự động được theo dõi, việc clear sẽ detach cả chúng. Cần thiết kế phạm vi unit of work phù hợp.

### 8.1. Vì sao phải flush trước clear?

Nếu clear trước khi flush, các entity managed có thay đổi pending sẽ bị detach. Những thay đổi chưa được đồng bộ có thể không được gửi xuống DB. Vì vậy, với mẫu batch thông thường, thứ tự là:

```java
entityManager.flush();
entityManager.clear();
```

Sau flush, SQL đã được gửi trong transaction hiện tại; clear chỉ loại entity khỏi context. Transaction vẫn chưa commit nếu chưa kết thúc transaction.

### 8.2. Sau clear, object cũ là detached

Không nên tiếp tục giả định entity đã clear vẫn được dirty checking. Nếu cần cập nhật entity đó sau này, phải nạp lại hoặc merge theo đúng semantics. Lazy association có thể không truy cập được sau khi context đóng/không còn session phù hợp; hãy lấy dữ liệu cần thiết trước khi detach hoặc thiết kế projection.

### 8.3. Chọn batch window

Batch size không có một giá trị tối ưu cố định. Có thể bắt đầu thử các mức như 25, 50 hoặc 100, sau đó đo:

- Heap usage và GC pause.
- Thời gian mỗi lần flush.
- JDBC batch size thực tế.
- Số round trip và số SQL statement.
- Lock duration, transaction duration và log generation.
- Throughput và p95/p99.

Batch quá nhỏ làm tăng số lần flush/round trip. Batch quá lớn làm persistence context, JDBC buffers và transaction lớn hơn; có thể tăng lock time và rollback cost. Chọn theo driver, DBMS, kích thước hàng, index và concurrency.

## 9. Transaction size khác flush batch size

Một điểm rất quan trọng: gọi `flush()` mỗi 50 entity nhưng vẫn giữ một transaction kéo dài đến cuối 100.000 entity không có nghĩa đã commit từng 50 bản ghi.

| Khái niệm | Kiểm soát điều gì? | Hệ quả |
|---|---|---|
| Flush batch/window | Thời điểm đồng bộ SQL và có thể clear context | Giảm số entity managed và chia nhỏ công việc flush |
| JDBC batch size | Số lệnh tương thích được gom vào một JDBC batch | Giảm round trip JDBC tùy driver/DB |
| Transaction chunk size | Số bản ghi hoặc thao tác nằm trong một transaction | Kiểm soát atomicity, lock lifetime, rollback scope và commit frequency |

Ví dụ `flush/clear` mỗi 50 hàng trong một transaction 100.000 hàng vẫn có thể giữ transaction, lock và undo/WAL liên quan trong thời gian dài. Nếu nghiệp vụ cho phép commit theo chunk, có thể chia thành nhiều transaction độc lập. Nhưng đó là thay đổi semantics: nếu chunk thứ 7 thất bại, các chunk trước có thể đã commit.

Không chia transaction chỉ để tăng tốc nếu nghiệp vụ yêu cầu tất cả dữ liệu được ghi atomically. Hãy xác định khả năng chạy lại, idempotency, checkpoint tiến độ và xử lý bản ghi lỗi trước khi dùng commit theo chunk.

## 10. Bật JDBC batching trong Hibernate

Flush định kỳ giúp giới hạn persistence context; JDBC batching giúp gom nhiều câu SQL cùng dạng vào một batch để giảm số lần giao tiếp giữa JVM và database. Hai cơ chế bổ sung cho nhau nhưng không giống nhau.

Với Hibernate, có thể cấu hình các thuộc tính như:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Ý nghĩa:

- `hibernate.jdbc.batch_size`: kích thước batch JDBC mục tiêu của Hibernate.
- `hibernate.order_inserts`: sắp xếp insert để các statement cùng loại/entity có cơ hội được gom batch.
- `hibernate.order_updates`: sắp xếp update để cải thiện khả năng batching và có thể giảm một số deadlock do thứ tự cập nhật nhất quán hơn trong workload phù hợp.

Đây là cấu hình Hibernate, không phải thuộc tính chuẩn JPA. Tên property và hiệu quả cần xác nhận theo phiên bản Hibernate và driver.

### 10.1. Batch chỉ hiệu quả khi statement tương thích

JDBC batching thường gom các câu lệnh cùng prepared statement shape. Nếu mỗi entity tạo SQL khác cấu trúc, thứ tự thao tác liên tục xen kẽ nhiều entity type hoặc có flush xen giữa từng bản ghi, batch có thể nhỏ hoặc không hình thành như mong đợi.

Driver cũng cần hỗ trợ batching hiệu quả. Một số driver có thể rewrite batch insert thành multi-row insert hoặc tối ưu giao thức; một số chỉ gửi nhiều statement theo cách riêng. Hãy kiểm tra log SQL, driver metrics hoặc datasource proxy để xác nhận batch thực tế.

### 10.2. IDENTITY generation có thể hạn chế insert batching

Với Hibernate, chiến lược sinh khóa `GenerationType.IDENTITY` thường cần thực thi INSERT để lấy generated key ngay, do đó có thể ngăn insert batching hiệu quả cho entity dùng chiến lược này. Sequence-based generation hoặc pooled/hi-lo optimizer có thể cho phép ORM cấp ID trước và gom insert tốt hơn, tùy DBMS/provider.

Không đổi ID generation chỉ vì muốn bật batching. Cần xem khả năng của database, schema, yêu cầu ID, thứ tự insert và tác động migration. Kiểm chứng bằng số batch thực tế.

### 10.3. Batch update và optimistic locking

Entity có `@Version` dùng optimistic locking. Khi Hibernate batch update entity versioned, driver/provider cần trả về số hàng bị ảnh hưởng đủ chính xác để phát hiện optimistic lock failure. Hỗ trợ và cấu hình batching versioned data phụ thuộc Hibernate version và JDBC driver.

Hãy kiểm tra rằng batch không làm mất khả năng phát hiện conflict. Nếu một hàng bị cập nhật bởi transaction khác, ứng dụng phải nhận đúng lỗi optimistic locking và xử lý retry hoặc báo xung đột theo nghiệp vụ.

## 11. Ví dụ batch update entity managed

Giả sử cần cập nhật trạng thái cho nhiều đơn hàng. Một cách làm là truy vấn từng entity, sửa trạng thái và flush theo cửa sổ:

```java
@Transactional
public void markOrdersAsReviewed(List<Long> orderIds) {
    int batchSize = 50;

    for (int i = 0; i < orderIds.size(); i++) {
        Order order = entityManager.find(Order.class, orderIds.get(i));
        if (order == null) {
            continue;
        }

        order.setReviewed(true);

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Đoạn code minh họa cách quản lý context, nhưng mỗi `find()` vẫn có thể phát sinh SELECT nếu entity chưa có trong cache của context. Nếu cần cập nhật số lượng lớn và không cần lifecycle callback hoặc dirty checking của từng entity, bulk JPQL hoặc JDBC batch có thể phù hợp hơn.

Nếu cần cập nhật một số entity cụ thể cùng các quan hệ, entity-level dirty checking vẫn có ích. Cần tránh N+1 SELECT bằng cách tải theo lô hoặc dùng truy vấn phù hợp; flush batching không tự giải quyết N+1.

## 12. Bulk JPQL/SQL khác dirty checking entity

Bulk update/delete tác động trực tiếp đến nhiều hàng trong database mà không nạp từng entity vào persistence context.

Ví dụ JPQL:

```java
entityManager.flush();

int updated = entityManager.createQuery(
    "update Order o " +
    "set o.reviewed = true " +
    "where o.createdAt < :cutoff")
    .setParameter("cutoff", cutoff)
    .executeUpdate();

entityManager.clear();
```

Ưu điểm:

- Không cần tạo và giữ object cho từng hàng.
- Có thể cập nhật hàng loạt bằng một câu SQL.
- Giảm dirty checking và số lần round trip nếu điều kiện phù hợp.

Điểm cần chú ý:

- Bulk JPQL update/delete bỏ qua entity lifecycle callbacks thông thường.
- Không cập nhật trạng thái của các entity đã managed trong persistence context; chúng có thể trở nên stale.
- Cơ chế optimistic locking/version không tự động giống entity-level update; nếu cần, phải xử lý version theo yêu cầu và semantics của provider.
- Cascade và orphan removal của entity không được áp dụng giống thao tác xóa từng entity.
- Native SQL cũng có thể làm persistence context không còn đồng bộ với database.

Vì vậy, thường cần flush thay đổi pending trước bulk DML và clear/refresh các entity liên quan sau đó. Chỉ clear khi đã cân nhắc mọi entity managed khác trong cùng context.

## 13. Đọc dữ liệu nhiều bản ghi mà không làm phình persistence context

Nếu chỉ cần xuất báo cáo hoặc chuyển dữ liệu, không nhất thiết phải nạp mọi hàng thành entity managed.

Các lựa chọn:

- Dùng DTO projection chỉ lấy các cột cần thiết.
- Dùng pagination hoặc keyset pagination để đọc theo lô.
- Dùng read-only query hint hoặc chế độ read-only của provider khi phù hợp.
- Flush/clear định kỳ nếu thực sự cần entity managed.
- Dùng JDBC trực tiếp cho ETL hoặc bulk processing cần kiểm soát SQL rõ ràng.
- Với Hibernate, cân nhắc `StatelessSession` cho workload phù hợp.

`StatelessSession` là API riêng của Hibernate, không phải JPA `EntityManager`. Nó không duy trì persistence context theo cách thông thường, nên không có first-level cache và dirty checking như `Session` thông thường; cascade, lifecycle events/interceptors và relationship handling cũng khác hoặc không có cùng semantics. Nó có thể hữu ích cho import/export lớn nhưng yêu cầu code tự quản lý nhiều trách nhiệm hơn.

## 14. Transaction chunking và xử lý lỗi

Nếu dữ liệu rất lớn, một transaction duy nhất có thể giữ lock lâu, tạo lượng log lớn, làm rollback tốn thời gian và ảnh hưởng transaction khác. Chia thành nhiều transaction chunk có thể giảm phạm vi lỗi và thời gian giữ tài nguyên cho mỗi chunk.

Ví dụ ý tưởng trong Spring:

```java
for (List<OrderInput> chunk : chunks(inputs, 500)) {
    transactionTemplate.executeWithoutResult(status -> {
        importChunk(chunk);
    });
}
```

`importChunk()` có thể dùng `flush/clear` và JDBC batching bên trong từng transaction. `TransactionTemplate` là ví dụ Spring; cách quản lý transaction phụ thuộc framework.

Trước khi commit từng chunk, cần giải quyết:

- **Atomicity:** nghiệp vụ có chấp nhận một phần lô đã commit không?
- **Idempotency:** chạy lại chunk có tạo bản ghi trùng hoặc trừ số lượng hai lần không?
- **Checkpoint:** làm sao biết chunk nào đã hoàn tất?
- **Ordering:** các chunk có phụ thuộc thứ tự không?
- **Foreign key:** dữ liệu tham chiếu có thể được tạo ở chunk khác chưa?
- **Retry:** lỗi deadlock, timeout hoặc network có thể retry an toàn không?
- **Partial failure:** cách lưu lỗi và tiếp tục xử lý bản ghi không hợp lệ?

Không bắt đầu transaction mới trong cùng vòng lặp mà vẫn vô tình giữ transaction cha lâu hơn dự kiến. Với Spring, propagation và proxy boundary ảnh hưởng cách `@Transactional` được áp dụng; self-invocation có thể không đi qua proxy trong cấu hình proxy-based. Hãy xác nhận transaction thực tế bằng integration test hoặc log.

## 15. Persistence context, cascade và quan hệ entity

Khi xử lý batch, quan hệ giữa entity có thể làm số object managed tăng nhanh hơn số bản ghi đầu vào.

Ví dụ mỗi `Order` có nhiều `OrderItem`, và mapping cascade persist:

```java
@OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
private List<OrderItem> items = new ArrayList<>();
```

Khi persist order, ORM có thể quản lý cả các item được cascade. Nếu mỗi order có 20 item, một batch 100 order có thể đưa khoảng 2.100 entity vào persistence context, chưa kể customer/product reference và collection state.

Các điểm cần kiểm tra:

- Cascade có đúng với vòng đời nghiệp vụ không?
- Có tạo graph object lớn hơn dự kiến không?
- Có dùng `EAGER` khiến nhiều quan hệ được tải ngoài nhu cầu không?
- Có giữ collection hai chiều lớn trong heap không?
- Khi clear, object cha/con nào trở thành detached?
- Có cần giữ reference đến entity sau khi flush/clear không?

Không bật cascade rộng chỉ để giảm số dòng code. Cascade quyết định thao tác ORM lan truyền đến quan hệ nào; nó có thể làm batch lớn hơn và khó kiểm soát hơn.

## 16. Flush, constraint và lỗi database

Một số lỗi chỉ xuất hiện khi SQL được gửi xuống DB, không nhất thiết tại lúc gọi `persist()` hoặc setter:

- Unique constraint violation.
- Foreign key violation.
- NOT NULL hoặc CHECK constraint violation.
- Optimistic locking failure.
- Deadlock hoặc lock timeout.
- Data truncation, conversion hoặc lỗi driver.

Nếu không flush tường minh, lỗi có thể xuất hiện khi provider tự flush trước query hoặc lúc commit. Điều này đôi khi khiến stack trace trỏ đến một dòng code khác với nơi tạo dữ liệu không hợp lệ.

Có thể flush tại ranh giới lô để phát hiện lỗi sớm hơn và gắn lỗi với nhóm bản ghi tương ứng. Nhưng sau một lỗi SQL trong transaction, database/provider có thể đánh dấu transaction rollback-only hoặc transaction không còn dùng tiếp được. Không bắt lỗi rồi tiếp tục dùng cùng transaction như thể chưa có gì xảy ra; hãy rollback và xử lý theo cơ chế transaction của DB/framework.

## 17. Đo hiệu năng persistence context và flush

Không đánh giá batch chỉ bằng thời gian tổng. Cần tách chi phí JVM, ORM, JDBC và database.

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| JVM | Heap used, allocation rate, GC count/pause | Entity và snapshot có làm tăng bộ nhớ/GC không? |
| Persistence context | Số entity managed, collection và thời gian flush | Context có tăng không kiểm soát và dirty checking có nặng không? |
| ORM | Entity insert/update/delete count, flush count, query count | ORM có phát quá nhiều SQL hoặc flush ngoài dự kiến không? |
| JDBC | Batch size thực tế, executeBatch count, round trips | Batching có thực sự được driver sử dụng không? |
| Database | TPS, statement latency, logical/physical reads, WAL/log bytes | DB có nhận ít round trip hơn và giữ throughput tốt hơn không? |
| Concurrency | Lock waits, deadlocks, transaction duration | Batch lớn có giữ lock lâu hoặc làm transaction khác chờ không? |
| Correctness | Rows inserted/updated, constraint errors, version conflicts | Kết quả có đầy đủ và không mất cập nhật không? |

### 17.1. SQL logging và thống kê Hibernate

Trong môi trường phát triển/kiểm thử, có thể bật SQL logging hoặc Hibernate statistics để xem số statement, flush và entity operation. SQL log có thể làm thay đổi hiệu năng và chứa dữ liệu nhạy cảm trong bind parameter; không bật log verbose trên production mà không đánh giá dung lượng, bảo mật và overhead.

Hibernate cung cấp `SessionFactory` statistics khi bật cấu hình phù hợp. Ví dụ minh họa:

```java
Statistics statistics = sessionFactory.getStatistics();

long flushes = statistics.getFlushCount();
long inserts = statistics.getEntityInsertCount();
long updates = statistics.getEntityUpdateCount();
long deletes = statistics.getEntityDeleteCount();
long preparedStatements = statistics.getPrepareStatementCount();
```

API và counter phụ thuộc Hibernate version. Statistics có thể tích lũy từ lúc bật hoặc reset; lấy snapshot trước/sau cửa sổ đo và tính delta. Không so sánh tổng tích lũy của hai lần chạy có thời lượng khác nhau.

### 17.2. Dùng Java Flight Recorder và heap analysis

Nếu heap hoặc GC là nút thắt, Java Flight Recorder (JFR) có thể giúp xem allocation, GC pause, lock contention và thread activity. Heap dump hoặc profiler có thể xác định entity, snapshot hoặc collection nào giữ nhiều bộ nhớ.

Tránh lấy heap dump tùy tiện trên production nếu kích thước lớn hoặc thao tác có thể làm pause/áp lực lưu trữ. Dùng môi trường staging hoặc quy trình quan sát an toàn, ghi rõ tải và giới hạn phép đo.

## 18. Quy trình benchmark cho batch persistence

Một phép thử có thể thực hiện theo trình tự:

1. **Xác định dữ liệu:** số bản ghi, kích thước entity, số quan hệ, tỷ lệ insert/update và phân bố khóa.
2. **Định nghĩa correctness:** số hàng mong đợi, constraint, thứ tự phụ thuộc, optimistic locking và khả năng retry.
3. **Đo baseline:** không thay đổi batch, ghi heap, GC, SQL count, flush time, DB TPS và transaction duration.
4. **Bật JDBC batching:** chọn một batch size ban đầu, kiểm tra driver và xác nhận executeBatch thực sự xảy ra.
5. **Thêm flush/clear window:** giới hạn số entity managed; đo memory và thời gian flush.
6. **Thử các batch size:** tăng/giảm từng bước, không thay đồng thời nhiều cấu hình.
7. **Đánh giá transaction chunk:** nếu transaction quá dài, thử chia transaction chỉ khi nghiệp vụ cho phép.
8. **Đọc execution plan và DB metrics:** xác định index, foreign key, log flush, lock hoặc I/O có trở thành nút thắt không.
9. **Kiểm tra sau ghi:** flush, clear, đọc lại từ DB hoặc chạy truy vấn đối chiếu để tránh chỉ kiểm tra object còn trong first-level cache.
10. **So sánh toàn diện:** throughput, p95/p99, heap, GC, round trips, lock duration, log volume và tính đúng đắn.

Giữ cùng database, schema, index, dữ liệu, phần cứng, mức đồng thời và cách warm-up. Lặp lại đủ lần để phân biệt cải thiện thật với biến động tự nhiên.

## 19. Ví dụ tổng hợp: import 100.000 dòng

Giả sử một dịch vụ cần import 100.000 bản ghi `CustomerEvent`. Mỗi event có một customer reference và một số thuộc tính đơn giản.

### 19.1. Cách làm giữ toàn bộ entity managed

```java
@Transactional
public void importAll(List<CustomerEventInput> inputs) {
    for (CustomerEventInput input : inputs) {
        CustomerEvent event = new CustomerEvent();
        event.setCustomerId(input.customerId());
        event.setEventType(input.eventType());
        event.setOccurredAt(input.occurredAt());
        entityManager.persist(event);
    }
}
```

Cách này đơn giản nhưng persistence context có thể giữ 100.000 entity cùng snapshot đến cuối transaction. Flush cuối có thể tạo một lượng công việc lớn; heap và GC có thể tăng.

### 19.2. Cách làm flush/clear theo cửa sổ

```java
@Transactional
public void importAll(List<CustomerEventInput> inputs) {
    int batchSize = 100;

    for (int i = 0; i < inputs.size(); i++) {
        CustomerEventInput input = inputs.get(i);

        CustomerEvent event = new CustomerEvent();
        event.setCustomerId(input.customerId());
        event.setEventType(input.eventType());
        event.setOccurredAt(input.occurredAt());
        entityManager.persist(event);

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

Kết hợp Hibernate JDBC batch size phù hợp, ví dụ 50 hoặc 100 để bắt đầu benchmark. Trong ví dụ này, flush/clear giới hạn số entity managed ở mỗi cửa sổ, nhưng vẫn giữ một transaction cho toàn bộ import. Nếu transaction 100.000 dòng quá dài, cần đánh giá commit theo chunk như một quyết định nghiệp vụ riêng.

### 19.3. Kiểm tra sau import

Không chỉ kiểm tra `inputs.size()` hoặc số entity object đã tạo. Hãy kiểm tra database sau khi flush/commit:

```sql
SELECT COUNT(*)
FROM customer_event
WHERE import_batch_id = :batch_id;
```

Nếu test đang chạy trong cùng persistence context, gọi `clear()` trước khi đọc lại hoặc dùng một context mới để tránh kết quả bị phục vụ từ first-level cache. Đối chiếu số hàng, khóa duy nhất, foreign key, lỗi từng bản ghi và tổng hợp checksum/aggregate nghiệp vụ nếu cần.

## 20. Những sai lầm thường gặp

- **Cho rằng `persist()` gửi INSERT ngay:** SQL thường được phát khi flush theo provider và flush mode.
- **Nhầm flush với commit:** flush không kết thúc transaction và không giải phóng toàn bộ lock.
- **Giữ hàng trăm nghìn entity trong một context:** heap, snapshot và dirty checking có thể tăng mạnh.
- **Gọi flush sau từng entity:** phá cơ hội batching và tăng round trip.
- **Clear trước flush:** thay đổi pending có thể bị detach mà chưa được đồng bộ.
- **Cho rằng clear chỉ xóa entity vừa import:** `clear()` detach toàn bộ entity managed trong context.
- **Tưởng flush/clear chia transaction:** transaction vẫn mở nếu chưa commit/rollback.
- **Bật batch size nhưng không kiểm tra driver:** batch có thể không được gửi như kỳ vọng.
- **Dùng IDENTITY mà kỳ vọng insert batch luôn hiệu quả:** Hibernate thường cần insert ngay để lấy ID.
- **Dùng `merge()` cho mọi entity mới:** merge sao chép trạng thái và trả về instance managed khác; có thể phát sinh công việc không cần thiết.
- **Dùng bulk JPQL rồi tiếp tục đọc entity cũ:** persistence context có thể chứa trạng thái stale.
- **Chia transaction mà không xử lý partial commit:** retry có thể tạo dữ liệu trùng hoặc cập nhật lặp.
- **Chỉ đo thời gian Java method:** không tách flush, JDBC, DB execution, GC và commit.
- **Kiểm tra dữ liệu qua entity đang managed:** first-level cache có thể che giấu trạng thái thực tế sau bulk SQL hoặc clear sai thời điểm.

## 21. Bài tập tự kiểm tra

### Bài tập 1: Dirty checking và flush

Một service gọi `find()`, thay đổi `order.setStatus(PAID)` rồi trả về mà không gọi `merge()` hoặc `update()`.

**Câu hỏi:** khi nào thay đổi được gửi xuống DB?

**Gợi ý trả lời:** nếu `order` vẫn managed trong persistence context, dirty checking phát hiện thay đổi và provider đồng bộ khi flush, thường trước commit hoặc ở một thời điểm flush tự động. Setter không nhất thiết phát SQL ngay.

### Bài tập 2: Flush không commit

Một transaction gọi `persist()`, `flush()` rồi phát sinh exception và rollback.

**Câu hỏi:** hàng vừa flush có còn trong DB không?

**Gợi ý trả lời:** không, nếu rollback transaction thành công thì các thay đổi của transaction bị hủy. Flush gửi SQL trong transaction, không làm transaction commit.

### Bài tập 3: Batch lớn gây OOM

Một import 500.000 entity giữ tất cả trong một persistence context và heap tăng đến giới hạn.

**Câu hỏi:** nên thử thay đổi nào và cần phân biệt điều gì?

**Gợi ý trả lời:** thử JDBC batching cùng `flush()`/`clear()` theo cửa sổ để giới hạn entity managed. Phân biệt batch window với transaction chunk: flush/clear không commit. Nếu transaction quá dài, chỉ chia transaction khi nghiệp vụ chấp nhận partial commit và có idempotency/checkpoint.

### Bài tập 4: Clear làm mất thay đổi

Code gọi `persist(entity)`, sau đó `clear()` ngay, cuối transaction không có INSERT như mong đợi.

**Câu hỏi:** vấn đề có thể nằm ở đâu?

**Gợi ý trả lời:** entity bị detach trước khi pending insert được flush. Với batch, gọi `flush()` trước `clear()` để đồng bộ SQL trong transaction rồi mới giải phóng context.

### Bài tập 5: Bật JDBC batching nhưng vẫn nhiều round trip

Sau khi đặt `hibernate.jdbc.batch_size=50`, log vẫn cho thấy nhiều INSERT riêng lẻ.

**Câu hỏi:** cần kiểm tra những gì?

**Gợi ý trả lời:** kiểm tra IDENTITY generation, flush quá thường xuyên, SQL shape xen kẽ, mapping/cascade, driver batching support, transaction boundary và cấu hình thực tế được framework nạp. Đo executeBatch và số round trip thay vì chỉ tin property đã đặt.

### Bài tập 6: Bulk update và persistence context stale

Một EntityManager đã load `Product` với `price = 100`. Sau đó JPQL bulk update đổi giá trong DB thành 120. Code đọc lại cùng entity từ EntityManager vẫn thấy 100.

**Câu hỏi:** vì sao và cách xử lý?

**Gợi ý trả lời:** bulk DML không đồng bộ object đã managed trong persistence context. Flush pending changes trước bulk operation nếu cần, rồi clear hoặc refresh entity liên quan trước khi đọc tiếp.

### Checklist xử lý nhiều bản ghi bằng JPA/Hibernate

- [ ] Đã xác định persistence context và transaction scope.
- [ ] Đã phân biệt transient, managed, detached và removed.
- [ ] Đã hiểu `persist()` khác `merge()` và dùng instance trả về từ merge.
- [ ] Đã xác định thời điểm dirty checking và flush.
- [ ] Không nhầm flush với commit hoặc transaction chunk.
- [ ] Đã chọn flush mode và kiểm tra auto-flush behavior.
- [ ] Đã flush trước clear để không detach thay đổi pending.
- [ ] Đã nhớ `clear()` detach toàn bộ entity managed trong context.
- [ ] Đã chọn batch window theo heap, GC, flush time và JDBC batch metrics.
- [ ] Đã bật JDBC batching và xác nhận driver thực sự batch.
- [ ] Đã kiểm tra ID generation strategy, cascade và statement ordering.
- [ ] Đã đánh giá bulk JPQL/native SQL và trạng thái stale của persistence context.
- [ ] Đã xác định có cần chia transaction hay phải giữ atomicity toàn lô.
- [ ] Đã thiết kế idempotency, checkpoint và retry cho partial failure nếu commit theo chunk.
- [ ] Đã đo JVM, ORM, JDBC, DB, lock, log và throughput.
- [ ] Đã đọc lại dữ liệu từ context mới/database để xác nhận correctness.

Persistence context giúp ORM quản lý identity và thay đổi entity; dirty checking phát hiện khác biệt để tạo SQL; flush đồng bộ SQL trong transaction còn commit mới kết thúc transaction thành công. Khi xử lý nhiều bản ghi, cần giới hạn số entity managed bằng flush/clear theo cửa sổ, cấu hình và xác minh JDBC batching, đồng thời phân biệt rõ batch window với transaction chunk. Hãy đo heap/GC, số round trip, thời gian flush, lock duration và throughput, rồi đọc lại dữ liệu từ database để xác nhận kết quả đúng trước khi chấp nhận tối ưu.
