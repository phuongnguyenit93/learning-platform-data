# `delete`, `deleteById`, `deleteAllById` và `deleteAll` trong Spring Data MongoDB

> **Chương:** Repository CRUD  
> **Module:** `SPRING_DATA_MONGODB` — kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository; mở rộng sang thiết kế truy vấn, kiểm thử, transaction và chẩn đoán hiệu năng.  
> **Mục tiêu:** Chọn đúng API xóa theo entity, một ID, nhiều ID hoặc toàn collection; hiểu `@Version`, kết quả khi không tìm thấy, rủi ro xóa hàng loạt và cách xác nhận số document đã xóa.

## 1. Bốn tên phương thức, nhiều ý nghĩa

`MongoRepository<T, ID>` cung cấp các thao tác CRUD kế thừa từ Spring Data Commons. Trong cùng một repository, những lời gọi sau đều hợp lệ nhưng **khác phạm vi và cách kiểm tra điều kiện xóa**:

~~~java
orders.delete(order);                           // Xóa một entity.
orders.deleteById("o101");                       // Xóa theo một ID.
orders.deleteAllById(List.of("o102", "o103"));    // Xóa theo một nhóm ID.
orders.deleteAll();                              // Xóa toàn bộ collection của repository.
orders.deleteAll(List.of(order1, order2));       // Xóa các entity được cung cấp.
~~~

| API | Đối số | Phạm vi | Dạng kết quả | Điểm đáng chú ý |
| --- | --- | --- | --- | --- |
| `delete(T entity)` | Entity có ID | Một document ứng với entity | `void` | Với `@Version`, kiểm tra phiên bản của entity |
| `deleteById(ID id)` | Một ID | Document có `_id` tương ứng | `void` | Không cần tải entity; bỏ qua kiểm tra phiên bản |
| `deleteAllById(Iterable<? extends ID> ids)` | Nhiều ID | Tập document có `_id` nằm trong danh sách | `void` | MongoDB repository triển khai bằng bộ lọc ID; không kiểm tra phiên bản từng entity |
| `deleteAll()` | Không | **Mọi document** trong collection của repository | `void` | Rất nguy hiểm nếu chạy nhầm môi trường |
| `deleteAll(Iterable<? extends T> entities)` | Nhiều entity | Các entity được truyền vào | `void` | MongoDB repository thực hiện lần lượt `delete(entity)`, có thể phát sinh lỗi phiên bản |

Trong `SimpleMongoRepository` hiện hành, `deleteById`, `deleteAllById` và `deleteAll()` được triển khai qua thao tác `MongoOperations.remove(Query, ...)`. `delete(T entity)` xóa dựa trên entity và kiểm tra kết quả xóa khi entity có `@Version`. Cách cài đặt chi tiết có thể thay đổi giữa phiên bản Spring Data; khi nâng cấp, đối chiếu tài liệu và phiên bản dependency của dự án.

**Không nhầm với JPA:** Một số API như `deleteAllByIdInBatch` thuộc Spring Data JPA; đây không phải phương thức mặc định cần dùng trong `MongoRepository`.

## 2. Chuẩn bị entity và bộ dữ liệu thực hành

### 2.1. Entity Java

Ví dụ dùng entity đơn giản, với ID được lưu chính xác dưới BSON `string` nhờ `@MongoId(FieldType.STRING)`. Trường `@Version` sẽ dùng ở mục kiểm soát cập nhật/xóa đồng thời.

~~~java
package com.example.orders;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_delete_demo_006")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String state;
    private long totalVnd;

    @Version
    private Long version;

    protected OrderDocument() { }

    public OrderDocument(String id, String state, long totalVnd) {
        this.id = id;
        this.state = state;
        this.totalVnd = totalVnd;
    }

    public String getId() { return id; }
    public String getState() { return state; }
    public long getTotalVnd() { return totalVnd; }
    public Long getVersion() { return version; }
    public void setState(String state) { this.state = state; }
}
~~~

~~~java
package com.example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    long countByState(String state);

    boolean existsByState(String state);
}
~~~

`String` trong `MongoRepository<OrderDocument, String>` là kiểu của ID ở API Java. Chính mapping của entity quyết định kiểu BSON `_id`. Nếu dùng `@Id String` thay vì `@MongoId(FieldType.STRING)`, một chuỗi gồm 24 ký tự hex hợp lệ có thể được Spring Data chuyển thành BSON `ObjectId`, khiến truy vấn/xóa theo ID không khớp document được lưu bằng chuỗi.

### 2.2. Dữ liệu MongoDB ban đầu

Mở `mongosh` trên **database thử nghiệm riêng**:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_delete_demo_006;

orders.insertMany([
  { _id: "o101", state: "NEW",       totalVnd: 100000, version: NumberLong(0) },
  { _id: "o102", state: "CANCELLED", totalVnd: 200000, version: NumberLong(0) },
  { _id: "o103", state: "CANCELLED", totalVnd: 300000, version: NumberLong(0) },
  { _id: "o104", state: "PAID",      totalVnd: 400000, version: NumberLong(0) },
  { _id: "o105", state: "ARCHIVED",  totalVnd: 500000, version: NumberLong(0) },
  { _id: "o106", state: "NEW",       totalVnd: 600000, version: NumberLong(0) }
]);

orders.find({}, { _id: 1, state: 1, version: 1 }).sort({ _id: 1 });
orders.countDocuments({}); // 6
~~~

`NumberLong(0)` giúp giá trị MongoDB cùng kiểu số dài với thuộc tính `Long version`. Bộ dữ liệu dùng khóa cố định; chạy lại `insertMany` vào collection đã có dữ liệu sẽ báo `E11000 duplicate key`. Các kết quả dự kiến trong bài **được hiểu độc lập trên bộ dữ liệu ban đầu**, trừ khi mục đó nói rõ chạy tuần tự.

Nếu muốn thực hành lại một kịch bản, dùng **collection thử nghiệm mới** hoặc đặt lại dữ liệu đã có quyền quản lý. Đừng áp dụng `deleteAll()` vào một repository trỏ tới database dùng chung để “reset” bài tập.

## 3. `delete(T entity)`: xóa theo đối tượng

Khi đã có entity từ một truy vấn hoặc luồng nghiệp vụ, dùng:

~~~java
OrderDocument order = repository.findById("o101")
    .orElseThrow(() -> new IllegalArgumentException("Order not found"));

repository.delete(order);
~~~

Trong ví dụ, `repository` là biến `OrderRepository` đã được inject. Với entity có `@Version`, Spring Data MongoDB dùng **ID và version của đối tượng** để đảm bảo bạn không xóa nhầm phiên bản dữ liệu vừa bị người khác thay đổi.

### 3.1. Vì sao truyền entity thay vì ID?

`delete(order)` hữu ích khi:

- Bạn vừa đọc entity và cần kiểm tra điều kiện nghiệp vụ, chẳng hạn chỉ đơn hàng `NEW` mới được phép xóa.
- Entity có `@Version` và hành động xóa cần tuân theo **optimistic locking**.
- Bạn cần giữ rõ ý định “xóa đúng đối tượng đã được tải và kiểm tra”.

~~~java
public void deleteDraftOrder(String id) {
    OrderDocument order = repository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Order not found"));

    if (!"NEW".equals(order.getState())) {
        throw new IllegalStateException(
            "Only NEW orders can be deleted"
        );
    }

    repository.delete(order);
}
~~~

Đây là ví dụ method nằm trong service có biến `OrderRepository repository`. Nếu client khác thay đổi document qua thao tác có cập nhật `version` giữa lúc đọc và lúc xóa, `delete(order)` sẽ không âm thầm xóa bản đã đổi; trường hợp version không khớp có thể phát sinh `OptimisticLockingFailureException`. Điều này không thay thế quy tắc phân quyền, kiểm tra tham chiếu và các điều kiện nghiệp vụ khác.

### 3.2. Khi document đã không còn

Với entity có `@Version`, thao tác `delete(entity)` được Spring Data MongoDB kiểm tra trên kết quả xóa **đã được server xác nhận**. Khi kết quả xóa bằng 0 do version không khớp hoặc document đã biến mất, Spring Data có thể ném `OptimisticLockingFailureException`.

Với entity **không có** `@Version`, bạn không nên giả định sẽ nhận ngoại lệ như vậy khi xóa một document không còn tồn tại. Nếu nghiệp vụ cần phân biệt “đã xóa” và “không tìm thấy”, hãy thiết kế phương thức trả kết quả rõ ràng (mục 10).

## 4. `deleteById(ID id)`: xóa theo một khóa

~~~java
repository.deleteById("o102");
~~~

Với mapping của `OrderDocument`, lệnh nhắm đến document có `_id` BSON string `"o102"`. Bạn không cần đọc entity trước khi gọi. Trong cách triển khai MongoDB hiện hành, phương thức tạo filter theo ID rồi gọi `MongoOperations.remove(Query, ...)`; phiên bản entity **không nằm trong điều kiện xóa**.

### 4.1. Trường hợp ID không tồn tại

~~~java
repository.deleteById("o999");
// Không có o999: theo hợp đồng CRUD, việc thiếu ID được bỏ qua.
~~~

`deleteById` trả về `void`, do đó không cho biết có bao nhiêu document đã bị xóa. Hợp đồng của Spring Data Commons nói rằng ID không tìm thấy được **bỏ qua một cách im lặng**. `null` là đầu vào không hợp lệ:

~~~java
repository.deleteById(null);
// IllegalArgumentException.
~~~

Đừng hiểu “không ném ngoại lệ” là “đã xóa một document”. Khi yêu cầu API phải thông báo số document thực tế bị xóa, dùng `MongoTemplate.remove(Query, Entity.class)` và kiểm tra `DeleteResult`.

### 4.2. `deleteById` khác `delete(entity)` với `@Version`

Giả sử entity `o101` được tải ở version 0, sau đó một người khác cập nhật thành version 1:

- `repository.delete(staleEntity)` sử dụng ID **và version 0**; MongoDB không còn document khớp điều kiện, và Spring Data báo lỗi optimistic locking.
- `repository.deleteById("o101")` sử dụng **ID**; nếu document còn tồn tại, nó vẫn bị xóa dù version lúc này là 1.

Vì thế, **không dùng `deleteById` để thay thế `delete(entity)` trong luồng bắt buộc kiểm soát phiên bản**. Đây là khác biệt cụ thể của Spring Data MongoDB; giao diện `CrudRepository` chung có tài liệu bao quát nhiều module, nên khi có sự khác biệt hãy dựa vào tài liệu MongoDB và triển khai repository tương ứng.

## 5. `deleteAllById(Iterable<ID>)`: xóa theo danh sách khóa

~~~java
repository.deleteAllById(List.of("o102", "o103", "o999"));
~~~

Nếu dữ liệu gốc có `o102` và `o103`, hai document đó được xóa; `o999` không tồn tại nên được bỏ qua. API trả `void` và không báo lại “2 trên 3 ID đã xóa”.

Ở `SimpleMongoRepository` hiện hành, `deleteAllById` xây bộ lọc từ các ID và thực hiện thao tác remove dựa trên query, tương đương về ý tưởng:

~~~javascript
// Minh họa filter BSON; không cần chạy sau lệnh repository ở trên.
orders.deleteMany({ _id: { $in: ["o102", "o103", "o999"] } });
~~~

Với entity có `@Version`, cách xóa theo **tập ID** này không kiểm tra version riêng của từng document. Nếu cần bảo vệ optimistic locking cho mỗi đối tượng, hãy đọc các entity phù hợp rồi dùng `deleteAll(entities)` hoặc `delete(entity)`, đồng thời chấp nhận rằng nhiều thao tác riêng lẻ không tự tạo một transaction nguyên tử.

### 5.1. Các trường hợp biên

~~~java
repository.deleteAllById(List.of()); // Danh sách rỗng: không có ID cần xóa.

repository.deleteAllById(List.of("o101", "o101"));
// ID lặp không có nghĩa sẽ xóa hai lần một document.

repository.deleteAllById(null);
// IllegalArgumentException.
~~~

Hợp đồng Spring Data Commons yêu cầu `Iterable` không được `null` và không chứa phần tử `null`. `List.of(...)` của Java không cho phép tạo danh sách chứa null; nếu lấy ID từ input bên ngoài, hãy lọc/kiểm tra trước khi gọi. Không dựa vào cách triển khai xử lý phần tử null trong một phiên bản cụ thể.

Nếu một danh sách chứa nhiều nghìn hoặc hàng triệu ID, việc tạo một query `$in` khổng lồ có thể gây vấn đề kích thước lệnh, bộ nhớ, hiệu năng và giới hạn BSON. Hãy chia thành **batch có kiểm soát**, theo dõi kết quả và giới hạn số lượng đầu vào.

### 5.2. Một lệnh xóa nhiều ID có phải transaction không?

Không. `deleteAllById` có thể được triển khai bằng một lời gọi MongoDB delete nhiều document, nhưng **không biến toàn bộ tập document thành một đơn vị nguyên tử**. MongoDB bảo đảm thao tác ghi trên mỗi document là nguyên tử; yêu cầu tính nguyên tử xuyên nhiều document cần transaction trên topology phù hợp.

Với API `void`, cũng không biết được chính xác ID nào đã bị xóa khi một phần ID không tồn tại. Nếu cần audit, hãy tự kiểm chứng/truy vấn hoặc dùng cơ chế lưu log nghiệp vụ.

## 6. `deleteAll()`: xóa toàn bộ document trong collection

~~~java
repository.deleteAll();
~~~

Không có đối số nghĩa là **xóa tất cả document của collection mà repository ánh xạ đến**, ví dụ `orders_delete_demo_006`. Nó không chỉ xóa các order đang tải trong bộ nhớ, không chỉ xóa những bản ghi đã lọc trên giao diện, và không phụ thuộc trạng thái `NEW`/`CANCELLED`.

Trên bộ dữ liệu gốc có 6 order, sau khi gọi:

~~~javascript
orders.countDocuments({}); // 0
~~~

`deleteAll()` dùng query không có điều kiện để remove các document của collection. Nó **không phải** `dropCollection()`: collection và các index có thể vẫn tồn tại. Nó cũng không phải thao tác “đưa database về trạng thái ban đầu”; metadata, index, nguồn ghi đồng thời và các collection khác không tự bị xóa.

### 6.1. Khi nào nên dùng?

Tình huống hợp lý thường là database thử nghiệm biệt lập, dữ liệu tạm có thể tái tạo hoặc một workflow đã được thiết kế rõ việc xóa toàn bộ một collection.

Trong API nghiệp vụ, thường nên dùng filter hẹp hơn, chẳng hạn xóa đơn hàng `CANCELLED` cũ. `MongoRepository.deleteAll()` không có tham số filter; nếu cần điều kiện, dùng query với `MongoTemplate` hoặc một repository delete query được khai báo phù hợp.

### 6.2. Xóa toàn bộ và `@Version`

`deleteAll()` **không đọc từng entity** để đối chiếu `version`. Theo cách triển khai hiện hành, nó gửi một câu lệnh remove với query rỗng. Không kỳ vọng optimistic locking trên từng document hay callback cấp entity theo cách giống `delete(entity)`.

**Nguyên tắc bảo vệ:** tách database/collection test; kiểm tra active profile, database URI, tên collection và quyền truy cập trước bất kỳ thao tác xóa toàn bộ nào.

## 7. Một overload dễ nhầm: `deleteAll(Iterable<? extends T> entities)`

~~~java
List<OrderDocument> selected = repository.findAllById(
    List.of("o101", "o104")
);

repository.deleteAll(selected);
~~~

Đây **không phải** `deleteAll()` không tham số. Nó chỉ xóa những **entity được truyền vào**. Trong triển khai `SimpleMongoRepository`, overload này duyệt danh sách và gọi `delete(entity)` cho từng phần tử:

~~~java
// Ý tưởng triển khai, không phải code thay thế của framework:
for (OrderDocument order : selected) {
    repository.delete(order);
}
~~~

Vì vậy:

- Có thể sử dụng kiểm tra `@Version` cho từng entity.
- Có thể phát sinh nhiều lời gọi xóa thay vì một query `$in`.
- Nếu lỗi xảy ra giữa chừng, những entity đã xóa trước đó **không tự được khôi phục**.
- Nếu cần xóa toàn bộ như một transaction, dùng `MongoTransactionManager` và transaction hỗ trợ, với giới hạn/chi phí phù hợp.

`deleteAllById(ids)` và `deleteAll(entities)` khác nhau cả về **kiểu đối số** lẫn **ý nghĩa version/per-entity processing**. Đổi từ cái này sang cái kia chỉ để tối ưu số truy vấn có thể làm thay đổi yêu cầu nhất quán dữ liệu.

## 8. So sánh trực tiếp với `MongoTemplate`

Repository đơn giản hóa CRUD, nhưng các phương thức xóa ở trên đều trả `void`. `MongoTemplate` có API xóa theo entity/query trả về `DeleteResult` của MongoDB driver:

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Giả sử template đã được inject vào service.
DeleteResult one = template.remove(
    Query.query(Criteria.where("id").is("o101")),
    OrderDocument.class
);

long deleted = one.getDeletedCount();
~~~

Lưu ý kết quả `DeleteResult` cần được **acknowledged** để truy cập số đếm đáng tin cậy. Với write concern `UNACKNOWLEDGED`, không nên trông đợi các kiểm tra kết quả hay optimistic locking hoạt động như khi được server xác nhận.

| Repository | Cách tương đương về ý tưởng qua MongoDB / `MongoTemplate` | Ghi chú |
| --- | --- | --- |
| `delete(entity)` | `template.remove(entity)` | Xóa theo entity; có thể bao gồm kiểm tra `@Version` |
| `deleteById(id)` | `template.remove(Query theo id, Entity.class)` | Query theo ID, không kiểm tra version |
| `deleteAllById(ids)` | `template.remove(Query theo danh sách id, Entity.class)` | Một query nhiều ID, không kiểm tra version từng entity |
| `deleteAll()` | `template.remove(new Query(), Entity.class)` | Không có filter, xóa toàn collection |
| `deleteAll(entities)` | Lặp `template.remove(entity)` | Xóa từng entity; có thể xảy ra lỗi giữa chừng |

### 8.1. Xóa theo điều kiện nghiệp vụ

Ví dụ xóa tất cả order ở trạng thái `CANCELLED`:

~~~java
Query cancelled = Query.query(
    Criteria.where("state").is("CANCELLED")
);

DeleteResult result = template.remove(
    cancelled,
    OrderDocument.class
);

long numberDeleted = result.getDeletedCount();
~~~

Trước khi xóa, có thể đếm để biết quy mô:

~~~java
long candidates = template.count(
    cancelled,
    OrderDocument.class
);
~~~

**Chú ý concurrency:** số `candidates` đọc trước có thể khác `numberDeleted` nếu dữ liệu thay đổi đồng thời; hai phép gọi không tự chạy trong một snapshot giao dịch. `DeleteResult.getDeletedCount()` cho biết số document server báo đã xóa, nhưng repository `void` không cung cấp trực tiếp thông tin này.

### 8.2. Xóa theo ID nhưng phải có đúng trạng thái

Khi nghiệp vụ chỉ cho phép xóa order `NEW`, một query có **hai điều kiện** giúp kiểm tra và xóa một document trong cùng thao tác:

~~~java
Query safeDelete = Query.query(
    Criteria.where("id").is("o101")
        .and("state").is("NEW")
);

DeleteResult result = template.remove(
    safeDelete,
    OrderDocument.class
);

if (result.getDeletedCount() == 0) {
    // Không có order, hoặc order không còn ở trạng thái NEW.
    throw new IllegalStateException(
        "Order not found or state no longer allows deletion"
    );
}
~~~

Đây là cách **xóa có điều kiện nguyên tử trên một document** mà không cần đọc rồi mới quyết định xóa ở hai lời gọi riêng. Nó không tự kiểm tra `@Version` trừ khi bạn thêm điều kiện version vào `Query`.

### 8.3. Khi cần lấy document vừa xóa

Nếu chức năng audit cần chính document bị xóa thay vì chỉ số lượng, có thể dùng `MongoTemplate.findAndRemove(Query, Class)`:

~~~java
OrderDocument deletedOrder = template.findAndRemove(
    Query.query(Criteria.where("id").is("o101")),
    OrderDocument.class
);
// deletedOrder == null khi không có document khớp.
~~~

Với một document, thao tác tìm-và-xóa là nguyên tử ở phía MongoDB. Nếu cần audit tồn tại độc lập trong một collection khác, việc ghi audit và xóa order là **hai thao tác khác nhau**, cần thiết kế transaction hoặc outbox theo yêu cầu.

## 9. `@Version` và optimistic locking trong thao tác xóa

Spring Data MongoDB hỗ trợ optimistic locking qua `@Version`. Khi lưu entity hiện có, Spring Data thường đưa version cũ vào điều kiện cập nhật rồi tăng version. Tương tự, khi xóa **bằng entity**, thông tin version giúp phát hiện một object cũ.

### 9.1. Tình huống hai người cùng sửa

Giả sử `o101` ban đầu có `version = 0`:

~~~java
OrderDocument stale = repository.findById("o101").orElseThrow();
OrderDocument current = repository.findById("o101").orElseThrow();

current.setState("PAID");
repository.save(current); // Version trong MongoDB thường tăng từ 0 -> 1.

repository.delete(stale);
// Với write acknowledgement: OptimisticLockingFailureException.
~~~

Vì `stale` mang version 0, xóa theo entity không khớp document đã tăng version. Cách xử lý nghiệp vụ thường là tải lại entity, hiển thị xung đột cho client, hoặc retry theo quy tắc cụ thể; **không tự chuyển sang `deleteById` để lách version**.

Ngược lại:

~~~java
repository.deleteById("o101");
// Xóa theo ID nếu còn document, dù version hiện tại là 1.
~~~

Hai đoạn trên là **hai nhánh so sánh**. Không chạy nối tiếp rồi mong dữ liệu vẫn còn để minh họa kết quả của cả hai.

### 9.2. Bảng tác động của `@Version`

| API của MongoDB repository | Theo triển khai MongoDB hiện hành |
| --- | --- |
| `delete(entity)` | Kiểm tra ID + version; có thể ném `OptimisticLockingFailureException` |
| `deleteById(id)` | Không kiểm tra version |
| `deleteAllById(ids)` | Không kiểm tra version của từng entity |
| `deleteAll(entities)` | Gọi xóa từng entity, nên có thể gặp optimistic locking |
| `deleteAll()` | Xóa bằng query rỗng, không kiểm tra version |

Tài liệu Spring Data Commons dùng một hợp đồng CRUD áp dụng cho nhiều store và có thể mô tả khả năng optimistic locking nói chung. Với **MongoDB**, tài liệu chính thức nêu rõ `CrudRepository.deleteById(ID)` dùng để xóa **không cần kiểm tra version**; mã `SimpleMongoRepository` cũng tạo query theo ID.

### 9.3. Write concern cần xác nhận

Kiểm tra optimistic locking dựa trên việc server xác nhận số document bị tác động. Nếu dùng `WriteConcern.UNACKNOWLEDGED`, ứng dụng không thể dựa vào kết quả trả về để phát hiện mọi xung đột. Với dữ liệu nghiệp vụ cần bảo toàn, dùng write concern phù hợp yêu cầu độ bền và khả năng quan sát lỗi.

## 10. Xây API xóa trả về kết quả có ý nghĩa

### 10.1. Endpoint idempotent và “không tìm thấy”

Với REST, `DELETE /orders/o101` có thể được thiết kế theo hai kiểu:

- **Idempotent về trạng thái:** xóa ID nếu tồn tại; nếu đã xóa trước đó vẫn trả phản hồi thành công như `204 No Content`.
- **Phân biệt không tồn tại:** trả `404 Not Found` khi không có order, hoặc báo `409 Conflict` khi trạng thái/version không cho phép xóa.

`deleteById` phù hợp với biến thể đầu do không trả số lượng. Với biến thể sau, dùng query có điều kiện và `DeleteResult`, hoặc thiết kế rõ bước kiểm tra. Một cặp thao tác `existsById()` rồi `deleteById()` có **race condition**: document có thể thay đổi giữa hai bước.

### 10.2. Ví dụ service xóa có trạng thái rõ ràng

~~~java
package com.example.orders;

import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderDeletionService {
    private final MongoTemplate template;

    public OrderDeletionService(MongoTemplate template) {
        this.template = template;
    }

    public boolean deleteNewOrder(String orderId) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("state").is("NEW")
        );

        DeleteResult result = template.remove(query, OrderDocument.class);
        return result.getDeletedCount() == 1;
    }
}
~~~

Ở đây `false` nghĩa là **không có document khớp đồng thời ID và state=NEW**. Nó không tự phân biệt “ID không có” với “đã chuyển trạng thái”; service/caller phải quyết định cách ánh xạ thành phản hồi API. Ví dụ cũng giả định write acknowledgement và collection đang dùng đúng database.

Đối với yêu cầu “chỉ xóa nếu client đã xem version N”, thêm điều kiện `and("version").is(expectedVersion)` vào query. Sau khi delete thất bại, có thể tra cứu lại để phân biệt stale version với không tồn tại; vẫn phải chấp nhận dữ liệu có thể biến động nếu không ở trong transaction.

## 11. Xóa dữ liệu liên quan: repository không tự cascade

MongoDB không tự tạo foreign key cho manual references. Spring Data MongoDB cũng không tự cascade xóa liên collection chỉ vì entity sử dụng `@DBRef` hoặc `@DocumentReference`.

Ví dụ:

~~~javascript
// customers
{ _id: "c001", name: "An" }

// orders
{ _id: "o101", customerId: "c001" }
~~~

Nếu gọi `customerRepository.deleteById("c001")`, document order vẫn có thể giữ `customerId: "c001"`, trở thành tham chiếu hỏng. Vì vậy trước khi xóa entity chính cần xác định chính sách:

| Chính sách | Ý nghĩa |
| --- | --- |
| `RESTRICT` | Chặn xóa khi còn document phụ thuộc |
| `CASCADE` | Xóa document phụ thuộc theo quy tắc nghiệp vụ |
| `DETACH / SET NULL` | Gỡ liên kết ở document phụ thuộc |
| `SOFT DELETE` | Giữ document, đánh dấu không còn hiệu lực |
| `RETAIN SNAPSHOT` | Giữ dữ liệu lịch sử cần thiết ở document phụ thuộc |

Không dùng `deleteAll()` để “dọn” một collection phụ thuộc khi chưa có chính sách. Xóa nhiều collection **không tự nguyên tử**. Nếu cần bảo đảm nhất quán xuyên document, cân nhắc MongoDB transaction trên topology hỗ trợ, đồng thời xử lý race giữa những writer đang tạo liên kết mới.

## 12. Xóa mềm khác xóa vật lý

Các phương thức `delete...` ở trên thực hiện **hard delete**: document không còn được truy vấn như trước. Nếu cần lịch sử/audit hoặc khả năng khôi phục, có thể dùng **soft delete**:

~~~javascript
orders.updateOne(
  { _id: "o101", deletedAt: { $exists: false } },
  { $set: { deletedAt: new Date() } }
);
~~~

Trong Java:

~~~java
Query active = Query.query(
    Criteria.where("id").is("o101")
        .and("deletedAt").exists(false)
);

template.updateFirst(
    active,
    new org.springframework.data.mongodb.core.query.Update()
        .set("deletedAt", java.time.Instant.now()),
    OrderDocument.class
);
~~~

Để lưu được `deletedAt` qua entity mapping, class cần khai báo thuộc tính hoặc kiểm soát converter; nếu thao tác chỉ qua `MongoTemplate.updateFirst` thì update vẫn có thể ghi trường BSON, nhưng lần `save(entity)` sau này có thể ảnh hưởng trường chưa được mapping. Hãy khai báo trường `deletedAt` và thống nhất quy tắc query nếu đưa soft delete vào hệ thống.

**Chú ý:** việc thêm `deletedAt` vào entity không khiến các phương thức `findAll`/`findById` mặc định tự ẩn bản ghi đã xóa. Cần thiết kế filter/query hoặc repository abstraction nhất quán, kể cả khi tính count, dùng index và xử lý quan hệ.

## 13. Hiệu năng và xóa số lượng lớn

### 13.1. Xóa một document

Truy vấn theo `_id` thường sử dụng index mặc định của MongoDB. `deleteById(id)` không cần đọc entity trước nên tránh được một số round-trip so với code tự `findById` rồi `delete(entity)`; đổi lại, nó không kiểm tra version.

### 13.2. Xóa nhiều ID

`deleteAllById(ids)` phù hợp khi biết chính xác danh sách khóa. Với một danh sách rất lớn, cần tính:

- Kích thước `$in`/BSON command và bộ nhớ phía ứng dụng.
- Áp lực ghi, I/O và replication khi xóa hàng loạt.
- Khả năng một số ID không tồn tại hoặc được tạo/sửa đồng thời.
- Nhu cầu ghi lại kết quả từng batch để retry idempotent.

Một hướng thực hành với danh sách được xác thực:

~~~java
// Pseudocode batching; batchSize nên được cấu hình theo hệ thống.
int batchSize = 500;

for (int from = 0; from < ids.size(); from += batchSize) {
    int to = Math.min(ids.size(), from + batchSize);
    repository.deleteAllById(ids.subList(from, to));
}
~~~

Ở đây `ids` là `List<String>` đã được khử trùng và kiểm tra giá trị, không phải input thô. Vòng lặp không tự tạo transaction bao trùm mọi batch. Một lỗi giữa chừng có thể khiến các batch trước đã xóa nhưng batch sau chưa xóa; workflow retry phải xử lý khả năng đó.

### 13.3. Xóa theo trạng thái và thời gian

Nếu muốn dọn đơn hàng `CANCELLED` đã quá thời hạn lưu:

~~~java
Query expired = Query.query(
    Criteria.where("state").is("CANCELLED")
        .and("createdAt").lt(cutoff)
);

DeleteResult result = template.remove(expired, OrderDocument.class);
~~~

Trong ví dụ, `cutoff` là `Instant` hoặc kiểu thời gian đã được cấu hình converter tương ứng; model thực tế cần trường `createdAt`. Đặt index phù hợp với truy vấn, thử trên dữ liệu nhỏ và quan sát `explain("executionStats")` cho phần tìm kiếm. Không mặc nhiên dùng `deleteAll()` rồi nạp lại dữ liệu mới để thực hiện retention.

Nếu có **TTL index**, MongoDB có thể tự loại bỏ document khi hết hạn, nhưng TTL là cơ chế xóa theo thời gian có độ trễ, không thay thế hoàn toàn chính sách nghiệp vụ và không dành cho mọi collection.

### 13.4. Event và auditing

Thao tác xóa qua query/bulk không có một entity Java đầy đủ cho từng document đã xóa. Nếu nghiệp vụ yêu cầu gửi event/audit chứa dữ liệu của từng order bị xóa, cần thiết kế riêng: lấy snapshot trước khi xóa (có thể gặp race), dùng change streams hoặc transaction/outbox thích hợp. Không mặc định rằng `deleteAllById` hay `deleteAll()` sẽ tự phát sự kiện nghiệp vụ cho từng entity.

## 14. Reactive repository: ý nghĩa tương tự, cách thực thi khác

Với `ReactiveMongoRepository<OrderDocument, String>`, nhóm API xóa tương ứng sử dụng publisher, thường là `Mono<Void>`:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {
}
~~~

~~~java
import reactor.core.publisher.Mono;

Mono<Void> deletedOne = reactiveRepository.deleteById("o101");
Mono<Void> deletedMany = reactiveRepository.deleteAllById(
    List.of("o102", "o103")
);
Mono<Void> deletedAll = reactiveRepository.deleteAll();
~~~

Các `Mono` trên là thao tác **lazy**: cần subscribe bởi chuỗi reactive thì lệnh mới được thực thi. Không gọi `block()` trong event loop. Tương tự API đồng bộ, `Mono<Void>` không cung cấp số document đã xóa; khi cần số đếm có thể dùng `ReactiveMongoTemplate.remove(Query, Class)`, trả `Mono<DeleteResult>` và map `getDeletedCount()`.

Chú ý: reactive API còn có một số overload nhận `Publisher` và các chi tiết hành vi có thể phụ thuộc phiên bản. Đừng coi `Mono<Void>` là `Boolean` “xóa thành công một document”; nó chỉ mô tả hoàn tất hoặc lỗi của thao tác.

## 15. Kiểm thử việc xóa

Vì xóa tác động trực tiếp MongoDB và Spring Data mapping/`@Version`, các case cốt lõi nên dùng **integration test** trên MongoDB Testcontainers hoặc một database test được cô lập. Mock repository thường không phát hiện được sai kiểu BSON ID hoặc khác biệt giữa hai overload.

### 15.1. Ma trận test cần có

| Test | Điều cần khẳng định |
| --- | --- |
| `delete(entity)` với version hiện hành | Document bị xóa |
| `delete(entity)` với version cũ | Ném `OptimisticLockingFailureException`, giữ bản mới |
| `deleteById(id)` với ID hợp lệ | Document đúng ID bị xóa |
| `deleteById(missingId)` | Không làm thay đổi document khác; không xem đó là lỗi |
| `deleteAllById` có ID tồn tại + ID thiếu | Chỉ document khớp bị xóa |
| `deleteAll(entities)` có entity stale | Có thể có lỗi optimistic locking; xác nhận không giả định rollback tự động |
| `deleteAll()` trên collection test | Số document giảm về 0; collection không bị drop |
| Query xóa theo state | Xóa đúng state, không làm mất các state khác |
| ID dạng hex nhưng lưu BSON string | Truy vấn xóa đúng kiểu nhờ mapping `@MongoId` |

### 15.2. Ví dụ test không dùng `deleteAll()` để dọn fixture

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderRepositoryDeletionTest {
    @Autowired OrderRepository repository;

    @Test
    void deletesSelectedIdsAndIgnoresMissingId() {
        // Chỉ chạy trên database test được cô lập.
        String first = "fixture-006-a";
        String second = "fixture-006-b";

        repository.deleteAllById(List.of(first, second));
        try {
            repository.save(new OrderDocument(first, "NEW", 100));
            repository.save(new OrderDocument(second, "NEW", 200));

            repository.deleteAllById(
                List.of(first, "fixture-006-missing")
            );

            assertThat(repository.existsById(first)).isFalse();
            assertThat(repository.existsById(second)).isTrue();
        } finally {
            repository.deleteAllById(List.of(first, second));
        }
    }
}
~~~

Ví dụ giả định không có test khác đang sử dụng cùng các ID fixture và các document có thể được lưu độc lập. Để kiểm tra `deleteAll()`, hãy dùng repository trỏ tới **collection chỉ dành cho test đó**; không chạy trên collection của nhiều test hoặc môi trường chia sẻ. Với transaction behavior, test phải dùng MongoDB topology hỗ trợ transaction.

### 15.3. Test optimistic locking

Một test nên tạo entity có `@Version`, đọc thành hai bản Java, lưu một bản làm tăng version rồi gọi `delete(stale)`. Xác nhận:

~~~java
assertThatThrownBy(() -> repository.delete(stale))
    .isInstanceOf(OptimisticLockingFailureException.class);
~~~

Trong đoạn này cần `import static org.assertj.core.api.Assertions.assertThatThrownBy;` và `import org.springframework.dao.OptimisticLockingFailureException;`; `stale` được tạo bằng phép đọc trên database test trước khi version tăng. Việc xác nhận bản mới vẫn tồn tại giúp phân biệt đúng lỗi optimistic lock với lỗi kết nối.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Gọi `deleteById` mà document vẫn còn | Sai database/collection; kiểu ID BSON không khớp; không có ID đó | Đối chiếu `@Document`, `@Id`/`@MongoId`, kiểm tra bằng `mongosh` |
| `deleteById` không ném lỗi khi ID không có | Đây là hợp đồng CRUD; xóa theo ID im lặng nếu thiếu | Dùng `DeleteResult` nếu cần biết số bị xóa |
| `delete(entity)` ném `OptimisticLockingFailureException` | Entity đã cũ, version thay đổi hoặc bị xóa | Tải lại và giải quyết xung đột, không tùy tiện bỏ version |
| `deleteAllById` xóa ít hơn số ID truyền | ID lặp, không tồn tại, mapping ID sai hoặc thay đổi đồng thời | Kiểm tra ID và dùng `MongoTemplate` khi cần count |
| `deleteAll()` xóa dữ liệu ngoài mong đợi | Repository kết nối nhầm database hoặc collection dùng chung | Cô lập môi trường, giới hạn quyền, kiểm tra cấu hình trước khi gọi |
| Xóa một số entity rồi dừng | `deleteAll(entities)` xóa lần lượt và có lỗi ở giữa | Cân nhắc transaction hoặc workflow retry/compensate |
| Xóa parent làm child còn tham chiếu hỏng | Không có cascade tự động giữa collection | Áp dụng RESTRICT/DETACH/CASCADE/soft delete theo chính sách |
| Query xóa hàng loạt quá chậm | Filter thiếu index, số document lớn, ghi/replication tốn tài nguyên | Tạo index phù hợp, chia batch, đo plan/độ trễ |
| Xóa bằng repository nhưng không có số đếm | Các API trên trả `void` | Dùng `MongoTemplate.remove` và kiểm tra `DeleteResult` |
| Chạy reactive delete không thấy thay đổi | `Mono` chưa được subscribe | Kết nối vào reactive chain/`StepVerifier` trong test |

## 17. Bài thực hành

Các bài dưới đây giả định bạn tạo lại 6 document gốc trong collection thử nghiệm (mục 2.2) **trước mỗi bài**.

### Bài 1 — Xóa một order theo ID

Viết code repository xóa `o102`, sau đó kiểm tra `o104` vẫn tồn tại.

~~~java
repository.deleteById("o102");

boolean targetDeleted = !repository.existsById("o102");
boolean unrelatedRemains = repository.existsById("o104");
// targetDeleted=true, unrelatedRemains=true trên fixture ban đầu.
~~~

**Câu hỏi:** Nếu `o102` chưa có từ đầu, `targetDeleted=true` có chứng minh delete vừa xóa một document không? **Không**. Kiểm tra hậu điều kiện “không còn tồn tại” khác với việc ghi nhận số document đã xóa.

### Bài 2 — Xóa nhiều ID

Hãy xóa `o102`, `o103` và `o999` bằng một lời gọi repository. Còn bao nhiêu document từ bộ dữ liệu gốc?

~~~java
repository.deleteAllById(
    List.of("o102", "o103", "o999")
);
// Còn 4 document: o101, o104, o105, o106.
~~~

`o999` không tồn tại nên không tính là một document bị xóa.

### Bài 3 — So sánh hai overload của `deleteAll`

~~~java
List<OrderDocument> selected = repository.findAllById(
    List.of("o101", "o106")
);
repository.deleteAll(selected);
~~~

Câu hỏi: Tại sao lệnh này khác `repository.deleteAll()`?

**Đáp án:** `deleteAll(selected)` chỉ xử lý các entity trong `selected`, có thể kiểm tra `@Version` và xóa từng entity. `deleteAll()` xóa toàn bộ document trong collection của repository, không dùng danh sách và không kiểm tra version từng entity.

### Bài 4 — Không cho xóa order đã thanh toán

Yêu cầu: chỉ được xóa order `NEW`. Viết lời gọi `MongoTemplate` vừa kiểm tra ID vừa kiểm tra trạng thái, sau đó xem số đã xóa.

~~~java
DeleteResult result = template.remove(
    Query.query(
        Criteria.where("id").is("o101").and("state").is("NEW")
    ),
    OrderDocument.class
);

long deletedCount = result.getDeletedCount(); // 1 trên dữ liệu gốc.
~~~

Nếu đổi `o101` sang `PAID` trước khi chạy, `deletedCount` sẽ là 0. Đó là hành vi đúng của xóa có điều kiện.

### Bài 5 — Tranh chấp phiên bản

Hai request cùng đọc order `o101` ở version 0. Request A lưu thay đổi và tăng version lên 1. Request B gọi `delete(staleEntity)`. Điều gì xảy ra? Nếu B đổi sang `deleteById("o101")` thì sao?

**Đáp án:** Với `delete(staleEntity)`, Spring Data MongoDB so sánh version 0 và không xóa bản mới; khi được server xác nhận, ném `OptimisticLockingFailureException`. `deleteById` chỉ lọc theo ID, nên vẫn có thể xóa bản mới nếu còn tồn tại. Không đổi sang API này nếu yêu cầu bảo vệ cập nhật đồng thời.

## Tài liệu tham khảo

- [Spring Data Commons — `CrudRepository` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html): các overload delete, tham số, hợp đồng khi ID không tồn tại.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate.remove`, các thao tác delete và `@Version`.
- [Spring Data MongoDB — `SimpleMongoRepository` source](https://github.com/spring-projects/spring-data-mongodb/blob/main/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/repository/support/SimpleMongoRepository.java): cách triển khai `delete`, `deleteById`, `deleteAllById`, `deleteAll`.
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html): mô hình repository và truy vấn MongoDB.
- [MongoDB Manual — Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/): `deleteOne()`/`deleteMany()`, hành vi lệnh xóa.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): tính nguyên tử trên một document, transaction khi thao tác nhiều document.
