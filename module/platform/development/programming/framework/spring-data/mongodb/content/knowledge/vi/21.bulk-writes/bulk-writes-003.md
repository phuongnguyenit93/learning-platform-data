# ORDERED, UNORDERED và hành vi khi một thao tác thất bại

## 1. Đặt vấn đề: ghi hàng loạt không đồng nghĩa giao dịch nguyên tử

Một hệ thống thương mại điện tử cần nhập 5.000 sản phẩm vào MongoDB. Gửi từng lệnh insert trong một vòng lặp có thể phát sinh nhiều lần giao tiếp với database và khó tổng hợp lỗi. **Bulk write** cho phép nhóm nhiều thao tác insert, update, replace hoặc delete thành một yêu cầu ghi hàng loạt ở tầng driver, giúp quản lý và tối ưu đường ghi.

Nhưng cần giải quyết một câu hỏi trước khi triển khai: **nếu thao tác thứ ba thất bại, các thao tác phía sau có tiếp tục không?**

MongoDB cung cấp hai chế độ:

- **ORDERED:** các thao tác được xử lý theo thứ tự khai báo; khi gặp **write error** ở một thao tác, bulk dừng việc xử lý các thao tác còn lại của yêu cầu đó.
- **UNORDERED:** các thao tác không có cam kết về thứ tự thực thi; khi gặp một lỗi ghi ở một phần tử, MongoDB vẫn có thể tiếp tục xử lý các thao tác độc lập còn lại và tổng hợp lỗi.

**Cả hai chế độ mặc định không phải giao dịch “tất cả hoặc không có gì”.** Những thao tác đã ghi thành công trước khi bulk thất bại thường không tự rollback. Một lệnh ghi trên từng document vẫn có tính nguyên tử ở phạm vi document đó, nhưng cả batch không tự có atomicity nhiều document.

Đây là chủ đề **ORDERED, UNORDERED và hành vi khi một thao tác thất bại**, thuộc chương **Ghi hàng loạt** trong module **SPRING_DATA_MONGODB**. Trong bối cảnh dịch vụ sử dụng Spring Data MongoDB để kết nối, ánh xạ document, thao tác qua **repository hoặc MongoTemplate**, việc hiểu bulk write còn là nền tảng để thiết kế truy vấn, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài học, bạn có thể:

1. Chọn đúng ORDERED hoặc UNORDERED theo mức độ phụ thuộc giữa các thao tác.
2. Dự đoán tác động của duplicate key, schema validation và các lỗi ghi thường gặp.
3. Gọi **MongoTemplate.bulkOps(...)** và đọc **BulkWriteResult**.
4. Phân biệt lỗi cấp thao tác, lỗi write concern và sự cố có kết quả chưa xác định.
5. Tránh kỳ vọng sai rằng ORDERED có rollback hoặc UNORDERED luôn hoàn thành mọi thao tác.
6. Thiết kế retry/idempotency, transaction, batch size và quy trình đối soát.
7. Viết kiểm thử tích hợp chứng minh những document nào thực sự được ghi khi một thao tác trong bulk lỗi.

## 2. Bộ dữ liệu mẫu: products và SKU duy nhất

Giả sử collection **products** lưu:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  stock: NumberInt(10),
  active: true,
  updatedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

SKU là khóa nghiệp vụ và phải duy nhất. Trên database, ta tạo **unique index**:

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_products_sku" }
);
~~~

Khi một bulk insert cố ghi hai document có SKU giống nhau, MongoDB có thể trả lỗi **duplicate key (thường có mã 11000)**. Đó là ví dụ dễ tái hiện để so sánh ORDERED và UNORDERED.

Entity Spring Data:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    int stock,
    boolean active,
    Instant updatedAt
) {}
~~~

Một số ví dụ sẽ dùng **ObjectId được tạo trước ở Java** thay vì chờ database sinh ID. Cách này giúp đối soát thao tác nào đã được ghi sau một bulk thất bại. Nếu dự án dùng ID kiểu String hoặc định danh nghiệp vụ khác, cần dùng đúng kiểu BSON của collection thực tế.

## 3. Hai chế độ có ý nghĩa khác nhau thế nào?

| Tiêu chí | ORDERED | UNORDERED |
| --- | --- | --- |
| Thứ tự thao tác | Theo thứ tự đã khai báo | Không bảo đảm thứ tự |
| Gặp write error ở một phần tử | Dừng các thao tác tiếp theo trong bulk | Có thể tiếp tục các thao tác khác |
| Các thao tác đã thành công | Không tự rollback | Không tự rollback |
| Lỗi được ghi nhận | Thường lỗi đầu tiên làm dừng | Có thể tổng hợp nhiều lỗi |
| Phụ thuộc thao tác trước → sau | Có thể phù hợp hơn, nhưng không thay thế transaction | Không được dựa vào thứ tự |
| Mức song song/tối ưu | Có thể hạn chế cơ hội tối ưu | Có thể được server/driver sắp xếp để tối ưu |
| Dùng khi nào | Các thao tác có trình tự có ý nghĩa | Các thao tác độc lập, ưu tiên xử lý tối đa |

**ORDERED không có nghĩa thao tác ghi sẽ chậm trong mọi trường hợp**, và **UNORDERED không có nghĩa MongoDB luôn chạy mọi thao tác cùng lúc**. Khả năng thực thi, nhóm lệnh và tối ưu còn phụ thuộc phiên bản driver, deployment, loại thao tác và cách MongoDB phân phối công việc.

Đừng chọn UNORDERED chỉ vì tên gọi gợi ý “nhanh hơn”. Câu hỏi đầu tiên phải là **các thao tác có phụ thuộc vào nhau không, và nghiệp vụ xử lý partial success thế nào?**

### 3.1. Sơ đồ xử lý

~~~mermaid
flowchart TD
    A["Bulk có 4 thao tác"] --> B{"Mode?"}
    B -->|ORDERED| C["op0 thành công → op1 lỗi"]
    C --> D["op2/op3 không được thực hiện"]
    B -->|UNORDERED| E["op1 lỗi, vẫn thử op0/op2/op3"]
    D --> F["Các ghi đã thành công không tự rollback"]
    E --> F
    F --> G["Ứng dụng đối soát kết quả và lỗi"]
~~~

Sơ đồ minh họa **lỗi ghi ở cấp thao tác** thông thường. Các lỗi nghiêm trọng như mất kết nối, hết thời gian chờ, lỗi lệnh chung hoặc lỗi transaction có thể làm diễn biến khác đi; phần sau sẽ phân biệt rõ.

## 4. Ví dụ trực quan: phần tử thứ hai bị trùng khóa

Giả sử trong products đã có document với SKU **BOOK-001**. Ta chuẩn bị một bulk gồm ba thao tác:

| Vị trí | Thao tác | Mô tả |
| --- | --- | --- |
| 0 | Insert BOOK-002 | SKU mới, hợp lệ |
| 1 | Insert BOOK-001 | SKU đã tồn tại → duplicate key |
| 2 | Insert BOOK-003 | SKU mới, hợp lệ |

### 4.1. Khi dùng ORDERED

Thứ tự diễn ra:

1. Insert BOOK-002 thành công.
2. Insert BOOK-001 thất bại do unique index.
3. Insert BOOK-003 **không được thực hiện** vì bulk dừng ở thao tác lỗi.

Sau bulk, BOOK-002 vẫn tồn tại. BOOK-001 cũ vẫn giữ nguyên. BOOK-003 chưa được thêm.

**Không có rollback tự động** cho BOOK-002. Để có hành vi rollback nhiều thao tác, phải thiết kế transaction phù hợp chứ không chỉ dùng ORDERED.

### 4.2. Khi dùng UNORDERED

MongoDB có thể thực hiện cả những thao tác độc lập khác mặc dù BOOK-001 bị trùng. Trong trường hợp bulk insert thông thường với kết nối và server hoạt động bình thường:

- BOOK-002 có thể được insert thành công.
- BOOK-001 phát sinh duplicate key.
- BOOK-003 vẫn có thể được insert thành công.

**Không được diễn giải kết quả là “insert theo thứ tự 0 → 1 → 2 rồi bỏ qua lỗi”**. UNORDERED không cam kết thứ tự, nên nếu nhiều thao tác tranh cùng một khóa hoặc phụ thuộc dữ liệu do thao tác khác tạo ra, kết quả cụ thể có thể khác.

Trong cả hai chế độ, caller vẫn cần nhận biết **bulk có lỗi** dù một số ghi thành công; không nên coi “đã ghi được vài document” là toàn bộ batch thành công.

## 5. Gọi bulkWrite bằng mongosh

MongoDB cung cấp lệnh collection.bulkWrite để thực hiện nhiều loại write model:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          sku: "BOOK-002",
          name: "MongoDB căn bản",
          stock: 3,
          active: true
        }
      }
    },
    {
      insertOne: {
        document: {
          sku: "BOOK-001",
          name: "Trùng SKU",
          stock: 1,
          active: true
        }
      }
    },
    {
      insertOne: {
        document: {
          sku: "BOOK-003",
          name: "Tối ưu MongoDB",
          stock: 5,
          active: true
        }
      }
    }
  ],
  { ordered: true }
);
~~~

Thay **ordered: true** bằng **ordered: false** để yêu cầu chế độ UNORDERED. Trước khi chạy hai thí nghiệm, hãy dọn hoặc đổi mã SKU riêng cho mỗi lượt, nếu không trạng thái còn lại từ lần trước sẽ gây lỗi trùng không liên quan.

### 5.1. Bulk có thể trộn nhiều loại thao tác

~~~javascript
db.products.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "BOOK-002" },
        update: { $inc: { stock: 2 } }
      }
    },
    {
      insertOne: {
        document: {
          sku: "PEN-009",
          name: "Bút",
          stock: 10,
          active: true
        }
      }
    },
    {
      deleteOne: {
        filter: { sku: "BOOK-OLD" }
      }
    }
  ],
  { ordered: false }
);
~~~

Trong ví dụ này, cả ba thao tác có mục đích độc lập nên UNORDERED có thể phù hợp. Ngược lại, nếu updateOne nhắm chính document được insertOne tạo ra trong cùng batch, không được dùng UNORDERED mà vẫn giả định insert chắc chắn thực hiện trước update.

### 5.2. Bulk write không phải bulk read

bulkWrite chỉ gồm các thao tác ghi. Nó không cung cấp một chuỗi “find rồi tính toán rồi ghi” có bước logic Java chen giữa. Khi cần thay đổi dữ liệu dựa trên trạng thái hiện tại, nên dùng update operators có điều kiện, update pipeline, hoặc tách quy trình theo yêu cầu nghiệp vụ.

## 6. Spring Data MongoDB: MongoTemplate.bulkOps

Trong Spring Data MongoDB, API thường dùng:

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.MongoTemplate;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.ORDERED,
    ProductDocument.class
);
~~~

**BulkMode.ORDERED** và **BulkMode.UNORDERED** là hai lựa chọn tương ứng với MongoDB bulk write. ProductDocument cung cấp metadata ánh xạ field và collection từ @Document.

Ví dụ dùng **insert**:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import com.mongodb.bulk.BulkWriteResult;

List<ProductDocument> products = List.of(
    new ProductDocument(
        new ObjectId(), "BOOK-101", "Sách A",
        5, true, Instant.now()
    ),
    new ProductDocument(
        new ObjectId(), "BOOK-102", "Sách B",
        9, true, Instant.now()
    )
);

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.ORDERED, ProductDocument.class
);

bulk.insert(products);
BulkWriteResult result = bulk.execute();
~~~

**bulk.insert(...)** đăng ký các thao tác cần thực hiện. **bulk.execute()** mới thực hiện batch trong API đồng bộ. BulkOperations thường là đối tượng được xây cho **một lần thực thi**; đừng tùy tiện tái sử dụng nó cho nhiều batch hoặc chia sẻ giữa các request.

### 6.1. Có nên gọi repository.saveAll thay cho bulkOps?

Không nên đồng nhất hai API. **saveAll** là hợp đồng repository với semantics lưu entity; còn **bulkOps** cho phép lựa chọn rõ ordered/unordered và tập hợp các lệnh insert, update, delete trong một batch.

Một số tối ưu của repository phụ thuộc vào trạng thái entity mới/cũ và phiên bản Spring Data. Nếu cần hành vi cụ thể khi một thao tác lỗi, kết quả per-operation và lựa chọn ordered/unordered, **dùng API bulk rõ ràng** sẽ dễ kiểm soát hơn việc suy đoán saveAll được triển khai ra sao.

### 6.2. Thêm update và delete

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);

bulk.updateOne(
    Query.query(Criteria.where("sku").is("BOOK-101")),
    new Update().inc("stock", 2)
);

bulk.updateMulti(
    Query.query(Criteria.where("active").is(false)),
    new Update().set("stock", 0)
);

bulk.remove(
    Query.query(Criteria.where("sku").is("BOOK-OLD"))
);

BulkWriteResult result = bulk.execute();
~~~

**updateOne** chỉ nhắm một document khớp query, **updateMulti** có thể thay đổi nhiều document, và **remove** xóa theo query được khai báo. Với các thao tác phụ thuộc nhau, cần chuyển sang ORDERED hoặc thiết kế quy trình khác; không được giả định UNORDERED giữ thứ tự đăng ký.

### 6.3. BulkOperations không có đầy đủ semantics của save

**BulkOperations không hỗ trợ optimistic locking dựa trên @Version theo cùng cách repository.save hoạt động**: không được giả định framework sẽ tự kiểm tra version riêng của từng entity, cập nhật version trên object Java hoặc ném lỗi stale tương tự save. Những logic dựa vào entity callbacks/auditing cũng cần được kiểm tra theo khả năng của API bulk thay vì mặc định giống đường save từng entity.

Nếu một bulk update yêu cầu version check, cần đưa **expectedVersion vào điều kiện Query** và thiết kế cách tăng version/kiểm tra kết quả có chủ đích. Với modified timestamp, nên xác định rõ thao tác nào tạo updatedAt thay vì cho rằng mọi bulk write đều gọi đầy đủ các callback như repository.save.

## 7. ORDERED: điều được bảo đảm và điều không được bảo đảm

Giả sử bulk có các thao tác A, B, C, D và B gây **write error**.

Trong một batch ORDERED bình thường:

- A được thử trước B và có thể thành công.
- B thất bại.
- C, D không được thực hiện sau lỗi B trong bulk đó.
- A không bị rollback chỉ vì B thất bại.

### 7.1. ORDERED hữu ích khi kết quả phụ thuộc thứ tự

Ví dụ một nhóm thao tác trên cùng Product:

1. Chuyển status sang ARCHIVED.
2. Sửa các field tương thích với ARCHIVED.

Nếu dùng UNORDERED, thao tác thứ hai không được phép giả định rằng status đã được cập nhật. Với ORDERED, thứ tự được giữ trong trường hợp không có lỗi ở thao tác trước.

Tuy vậy, hai thao tác riêng vẫn có thể bị quan sát giữa chừng bởi các request khác và không tạo atomicity toàn batch. Nếu cả hai cùng tác động một document, thường tốt hơn khi gộp thành **một update có điều kiện** nếu có thể.

### 7.2. ORDERED không tương đương transaction

| Thuộc tính | ORDERED ngoài transaction | Transaction nhiều document |
| --- | --- | --- |
| Thứ tự yêu cầu | Có | Theo trình tự lệnh do ứng dụng thực hiện |
| Gặp lỗi ở lệnh thứ ba | Các lệnh trước có thể vẫn được ghi | Có thể rollback những ghi trong transaction nếu transaction abort |
| Có commit nguyên tử cho toàn batch? | Không | Có, khi transaction được cấu hình/hỗ trợ đúng |
| Có tự kiểm tra điều kiện nghiệp vụ? | Không | Không |
| Chi phí và điều kiện vận hành | Theo bulk bình thường | Có điều kiện triển khai và chi phí transaction |

**Không cần mở transaction chỉ để dùng ORDERED.** Transaction nên được chọn khi nghiệp vụ thực sự cần một nhóm ghi trên nhiều document cùng commit hoặc rollback.

## 8. UNORDERED: xử lý được nhiều thao tác, nhưng không có thứ tự

UNORDERED cho phép driver/server tổ chức thao tác theo cách có thể hiệu quả hơn, đặc biệt trong một số môi trường sharded. Các lệnh không có ràng buộc thứ tự khi được thực thi.

Ví dụ batch có:

- Insert SKU A.
- Insert SKU B đã tồn tại và bị duplicate key.
- Insert SKU C.
- Update stock của một SKU D độc lập.

Một write error ở B **không buộc phải chặn** các thao tác còn lại. Ứng dụng vẫn cần xem những thao tác nào đã thành công và những thao tác nào báo lỗi.

### 8.1. Đừng tạo phụ thuộc logic bên trong UNORDERED

Ví dụ nguy hiểm:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          sku: "NEW-001",
          name: "Sản phẩm mới",
          stock: 1
        }
      }
    },
    {
      updateOne: {
        filter: { sku: "NEW-001" },
        update: { $inc: { stock: 1 } }
      }
    }
  ],
  { ordered: false }
);
~~~

Nếu updateOne được thực thi trước insertOne, nó có thể **matchedCount=0**, và stock cuối cùng vẫn là 1. Nếu insert được thực hiện trước update, stock có thể thành 2. Không được dựa vào kết quả ngẫu nhiên ở môi trường test để xây quy tắc nghiệp vụ.

Cách tốt hơn là insert sản phẩm với giá trị stock cuối cùng, hoặc thực hiện một upsert/update có điều kiện phù hợp, hoặc tách thành hai giai đoạn theo thứ tự được xác nhận.

### 8.2. UNORDERED không có nghĩa “mọi thao tác chắc chắn chạy”

Với lỗi write thông thường, server có thể tiếp tục các thao tác độc lập. Nhưng sự cố như:

- Không thể gửi yêu cầu do mạng.
- Lỗi xác thực/quyền hoặc lỗi lệnh cấp cao.
- Server ngắt kết nối giữa chừng.
- Write concern không được đáp ứng.
- Transaction bị abort.

có thể khiến caller **không có bằng chứng rằng mọi thao tác đã được thử hoặc commit**. Một số trường hợp còn có kết quả ghi chưa xác định. Vì vậy, “unordered tiếp tục sau lỗi” là quy tắc cho **write errors cấp thao tác trong bulk**, không phải lời bảo đảm hoàn thành trong mọi tình huống vận hành.

## 9. BulkWriteResult: các con số nói gì?

Khi batch hoàn thành không có lỗi làm ném exception và write concern được acknowledge, **BulkOperations.execute()** trả về **BulkWriteResult** từ MongoDB Java Driver.

~~~java
import com.mongodb.bulk.BulkWriteResult;

BulkWriteResult result = bulk.execute();

boolean acknowledged = result.wasAcknowledged();
int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserts = result.getUpserts().size();
~~~

Các chỉ số thường gặp:

| Chỉ số | Ý nghĩa |
| --- | --- |
| wasAcknowledged | Server đã acknowledge theo write concern áp dụng hay chưa |
| insertedCount | Số document được insert trong bulk |
| matchedCount | Số document khớp những thao tác update được thống kê |
| modifiedCount | Số document có dữ liệu thực sự bị thay đổi |
| deletedCount | Số document đã bị xóa |
| upserts | Các thao tác upsert đã tạo document mới, có thông tin index/ID tương ứng khi được trả |

**matchedCount không đồng nghĩa modifiedCount.** Một update có thể match Product nhưng đặt stock bằng đúng giá trị cũ nên không có thay đổi thực tế.

### 9.1. Không suy ra kết quả từng phần tử từ tổng count

Nếu insertedCount=7 trong batch gồm 10 insert, bạn **chưa biết chính xác ba item còn lại là gì** chỉ từ count. Cần kết hợp:

1. Danh sách thao tác đầu vào có định danh rõ.
2. Các write errors cùng index khi được cung cấp.
3. Trạng thái dữ liệu thực sau lỗi, nhất là với lỗi chưa xác định.

Với API Spring Data BulkOperations, không nên kỳ vọng nhận một đối tượng ProductDocument riêng đã được cập nhật ID cho mỗi insert như ở phương thức repository.save. Nếu cần liên kết kết quả với input, **tạo ID hoặc operation key trước khi gửi bulk** và đối soát bằng khóa đó.

### 9.2. Chỉ đọc count khi kết quả có acknowledge

Nếu hệ thống cấu hình write concern không acknowledge, không được giả định các count chi tiết luôn khả dụng hoặc kết quả đã được server xác nhận. BulkResult và driver có giới hạn khi đọc những chỉ số của unacknowledged write; với bài toán nhập dữ liệu cần đối soát, nên ưu tiên acknowledged writes.

## 10. Khi lỗi xảy ra, execute() có thể ném exception

Một thao tác trùng unique index thường khiến bulk **ném exception** thay vì trả một BulkWriteResult bình thường với một field “success=false”.

Ví dụ:

~~~java
import org.springframework.dao.DataAccessException;

try {
    BulkWriteResult result = bulk.execute();
    // Chỉ tới đây nếu bulk hoàn thành theo kết quả mà API công bố.
    recordSuccess(result);
} catch (DataAccessException ex) {
    // Có thể đã có một số thao tác ghi thành công.
    recordFailure(ex);
    throw ex;
}
~~~

Hai hàm **recordSuccess** và **recordFailure** là hàm nghiệp vụ giả định. Spring Data có thể **dịch exception từ MongoDB driver sang hệ DataAccessException**. Tên exception chính xác và thông tin đi kèm phụ thuộc loại lỗi và phiên bản Spring Data/driver.

**Không bắt exception rồi giả định toàn batch thất bại sạch sẽ.** Cần phân biệt thao tác nào chắc chắn đã ghi, thao tác nào chắc chắn lỗi và thao tác nào chưa rõ kết quả.

### 10.1. Lỗi từ Java Driver

Ở tầng MongoDB Java Driver, lỗi bulk có thể được thể hiện bằng **MongoBulkWriteException**, cung cấp danh sách **BulkWriteError** và một số thông tin về kết quả ghi:

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(models, options);
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        int index = error.getIndex();
        int code = error.getCode();
        String message = error.getMessage();
        // Đối chiếu index với danh sách write models đã gửi.
    }
}
~~~

Đoạn mã giả định **collection**, **models** và **options** là các đối tượng MongoDB Java Driver đã khởi tạo trước. Đây là mẫu trình bày thông tin lỗi của tầng driver; ở Spring Data, ngoại lệ đã dịch có thể không trực tiếp là MongoBulkWriteException. Không cast exception một cách mù quáng.

### 10.2. Index lỗi có ý nghĩa gì?

Với một yêu cầu bulkWrite sử dụng danh sách write models, write error index thường chỉ tới **vị trí thao tác trong danh sách được gửi theo hợp đồng driver**. Ví dụ error.index=1 ứng với thao tác thứ hai.

Khi sử dụng các lớp trừu tượng gom/sắp nhóm thao tác, split batch hoặc trộn loại lệnh, cần **xác minh mapping index với request trong phiên bản driver đang chạy**, thay vì chỉ dựa vào một thứ tự do ứng dụng tưởng tượng. Luôn giữ một bảng ánh xạ **operation ID → input record** để việc ghi nhận lỗi có ý nghĩa nghiệp vụ.

## 11. Ba nhóm lỗi cần phân biệt

Không phải mọi thất bại trong bulk đều là duplicate key ở một phần tử.

| Nhóm | Ví dụ | Điều có thể biết |
| --- | --- | --- |
| **Write error cấp thao tác** | Duplicate key, validation thất bại, update không hợp lệ | Có thể có index, code, message cho thao tác lỗi |
| **Write concern error** | Không đạt mức xác nhận replica theo cấu hình trong thời gian cho phép | Dữ liệu có thể đã được ghi trên primary; chưa chắc đáp ứng độ bền/yêu cầu xác nhận |
| **Lỗi lệnh/kết nối chung** | Mất mạng, quyền, server không thể xử lý yêu cầu | Có thể không biết đầy đủ thao tác nào đã xảy ra |

### 11.1. Duplicate key

Ví dụ E11000 khi insert hai document cùng **sku** trên unique index:

~~~text
E11000 duplicate key error collection: catalog.products
index: uk_products_sku dup key: { sku: "BOOK-001" }
~~~

Thông điệp trên là minh họa, không phải định dạng log cố định. Ở Java, mã **11000** thường dùng để nhận diện duplicate key; vẫn cần kiểm tra trường unique bị trùng để quyết định cách xử lý nghiệp vụ.

### 11.2. Document validation

Nếu collection yêu cầu stock không âm qua schema validation, thao tác insert có stock=-3 có thể thất bại mặc dù _id và sku đều mới.

~~~javascript
db.createCollection("validated_products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "stock"],
      properties: {
        sku: { bsonType: "string" },
        stock: { bsonType: "int", minimum: 0 }
      }
    }
  }
});
~~~

Bulk write vào collection này cần tuân theo validator. Với UNORDERED, lỗi validation của một document không nhất thiết ngăn mọi document hợp lệ khác được ghi. Với ORDERED, một write error có thể dừng các thao tác sau nó.

### 11.3. Write concern timeout

Nếu write concern yêu cầu xác nhận từ nhiều replica nhưng không nhận đủ xác nhận trước thời hạn, server có thể trả **write concern error**. Điều đó không đồng nghĩa primary chưa áp dụng thao tác. **Không retry mù quáng cả batch** khi kết quả có thể đã được ghi.

Các trường hợp này cần đối soát trạng thái database qua định danh nghiệp vụ hoặc operation key trước khi quyết định gửi lại.

## 12. Thao tác liên quan cùng một khóa: khác biệt rất lớn

Với hai lệnh update cùng một Product:

~~~javascript
db.products.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "BOOK-001" },
        update: { $set: { stock: 10 } }
      }
    },
    {
      updateOne: {
        filter: { sku: "BOOK-001" },
        update: { $inc: { stock: 2 } }
      }
    }
  ],
  { ordered: false }
);
~~~

Kết quả stock có thể phụ thuộc thứ tự thực thi:

- Nếu **$set 10** rồi **$inc 2**, stock = 12.
- Nếu **$inc 2** rồi **$set 10**, stock = 10.

**UNORDERED không phù hợp** nếu nghiệp vụ cần một kết quả duy nhất từ chuỗi thao tác có phụ thuộc thứ tự.

Đối với cùng một document, có thể gộp thao tác thành **một update** phù hợp với ngữ nghĩa mong muốn. Ví dụ đặt stock=12 trực tiếp khi giá trị cuối được xác định từ nguồn tin cậy, hoặc dùng một update pipeline tính toán theo trạng thái hiện tại nếu nghiệp vụ cần.

### 12.1. ORDERED có giải quyết hoàn toàn concurrency không?

Không. ORDERED giữ thứ tự **trong batch đó**, nhưng request khác vẫn có thể cập nhật Product giữa các thao tác, trừ khi có thêm cơ chế phối hợp. Với yêu cầu cập nhật có điều kiện, nên đưa điều kiện version/status vào filter hoặc dùng transaction nếu phải bảo vệ nhiều document cùng lúc.

### 12.2. Upsert trong UNORDERED

Hai upsert cùng nhắm một khóa chưa tồn tại có thể cạnh tranh. Kết quả phụ thuộc filter, unique index, thứ tự và cách server thực thi. Nếu business key phải duy nhất, luôn dựa vào **unique index được tạo trên MongoDB** chứ không chỉ kiểm tra exists ở ứng dụng.

Trong một số tình huống, upsert cạnh tranh có thể dẫn tới duplicate key. Ứng dụng phải xử lý lỗi và đọc lại document để quyết định thao tác đã được đáp ứng hay chưa.

## 13. Cách chọn ORDERED hay UNORDERED theo nghiệp vụ

### 13.1. Chọn ORDERED khi

- Yêu cầu thứ tự giữa các thao tác trong cùng batch có ý nghĩa.
- Cần dừng ngay khi một dữ liệu đầu vào không hợp lệ được server từ chối.
- Dễ muốn tìm **điểm dừng** để sửa lỗi dữ liệu và tiếp tục theo thứ tự.
- Các thao tác có phần phụ thuộc mà chưa thể tổ chức lại thành các nhóm độc lập.

Vẫn phải chấp nhận rằng những thao tác trước lỗi đã có thể được ghi; nếu không cho phép partial commit, phải xem lại transaction hoặc thiết kế khác.

### 13.2. Chọn UNORDERED khi

- Mỗi thao tác có thể thành công hoặc thất bại độc lập.
- Hệ thống muốn xử lý tối đa những bản ghi hợp lệ dù có một số bản ghi lỗi.
- Đã có định danh input và cơ chế đối soát/retry từng record.
- Không có phụ thuộc trước–sau giữa các thao tác trong cùng batch.

Ví dụ phù hợp: nhập một danh sách product mới, mỗi product có ID/sku riêng, và lỗi của một product không nên chặn những product còn lại.

### 13.3. Bảng quyết định nhanh

| Kịch bản | Chế độ ưu tiên cân nhắc | Lưu ý |
| --- | --- | --- |
| Import nhiều product độc lập | UNORDERED | Thu lỗi từng product, unique index, idempotency |
| Migration tuần tự, bước sau phụ thuộc bước trước | ORDERED hoặc tách giai đoạn | Thứ tự không tự tạo rollback |
| Hai thao tác trên cùng document cần kết quả xác định | Một update nguyên tử, hoặc ORDERED | Tránh viết hai lệnh nếu có thể gộp |
| Thay đổi nhiều aggregate phải cùng thành công | Transaction/giao thức nghiệp vụ | Mode alone không đáp ứng atomicity |
| Batch lớn có lỗi dữ liệu đầu vào | Thường UNORDERED nếu các dòng độc lập | Báo cáo partial success và retry các dòng lỗi |
| Cần dừng tại lỗi đầu tiên để kiểm tra | ORDERED | Các ghi trước lỗi vẫn tồn tại |

## 14. Batch lỗi không tự rollback: transaction xử lý trường hợp nào?

MongoDB hỗ trợ transaction nhiều document trên các deployment phù hợp. Spring Data có thể sử dụng **MongoTransactionManager** để gắn một nhóm ghi vào transaction:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Ví dụ một service Spring-managed:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public BulkWriteResult importAtomicBatch(
        List<ProductDocument> products) {
    BulkOperations bulk = mongoTemplate.bulkOps(
        BulkMode.ORDERED, ProductDocument.class
    );
    bulk.insert(products);
    return bulk.execute();
}
~~~

Ví dụ chỉ có ý nghĩa nguyên tử nhiều document khi:

1. MongoDB deployment hỗ trợ transaction và driver được cấu hình đúng.
2. MongoTransactionManager được kích hoạt cho các thao tác tham gia.
3. Phương thức @Transactional thực sự được gọi qua Spring proxy/transaction interceptor.
4. Exception gây rollback được truyền ra theo chính sách transaction.

### 14.1. Lỗi bulk bên trong transaction

Nếu có lỗi ghi trong transaction, không nên áp dụng suy luận đơn giản rằng **UNORDERED vẫn tiếp tục tất cả và giữ partial success để commit**. Một write error có thể làm transaction bị abort, khiến các thao tác tiếp theo không còn hợp lệ trong transaction đó. Ứng dụng phải xử lý lỗi, rollback và thử lại **toàn đơn vị nghiệp vụ** khi phù hợp.

Không nên bắt lỗi bulk trong một transaction rồi commit phần đã thành công chỉ vì nghĩ MongoDB sẽ bỏ qua lỗi. Hành vi transaction có quy tắc riêng.

### 14.2. Khi nào không cần transaction?

Nếu mỗi product import là một thực thể độc lập và yêu cầu chấp nhận dòng hợp lệ, transaction toàn batch 5.000 dòng có thể không cần thiết, thậm chí làm tăng chi phí và khiến một dòng lỗi ảnh hưởng toàn bộ lô. Dùng UNORDERED không có transaction cùng báo cáo partial success có thể phù hợp hơn.

**Chọn transaction từ bất biến nghiệp vụ**, không phải vì “bulk có nhiều lệnh” hoặc vì người dùng muốn biết có lỗi hay không.

## 15. Retry và idempotency: phần khó nhất sau partial failure

Giả sử client gửi bulk 100 thao tác, nhưng kết nối bị mất sau khi server đã ghi 60 thao tác. Client không nhận được phản hồi hoàn chỉnh. Nếu gửi lại cả batch, điều gì xảy ra?

- Các insert cùng _id có thể gặp duplicate key.
- Các update kiểu **$inc** có thể bị áp dụng lần nữa, làm tăng stock sai.
- Các delete đã thực hiện có thể không còn document để xóa.
- Các upsert có thể thay đổi dữ liệu tùy filter và update.

Vì thế, **không retry cả bulk một cách mù quáng** khi kết quả chưa xác định.

### 15.1. Phân loại thao tác theo khả năng lặp

| Thao tác | Lặp lại có an toàn không? | Điều kiện |
| --- | --- | --- |
| $set một field thành cùng giá trị | Thường idempotent về giá trị field | Không có writer khác bị ghi đè; timestamp/version cần xét riêng |
| $inc stock thêm 1 | **Không idempotent** | Lặp hai lần có thể cộng hai |
| Insert cùng _id | Lần sau thường duplicate key | Cần đối soát document/payload để xác định “đã hoàn tất” |
| Delete theo _id | Thường đạt cùng trạng thái “không tồn tại” | Nhưng side effects, audit/event ngoài DB cần xét |
| $push thêm item | Không idempotent | Có thể thêm trùng khi retry |
| $addToSet một giá trị giống hệt | Có tính chống trùng theo giá trị | Không phải chống trùng theo business key trong object |
| Upsert bằng $setOnInsert + unique key | Có thể xây idempotency hợp lý | Phải có khóa và quy tắc cập nhật phù hợp |

### 15.2. Sử dụng operation ID

Trong hệ thống import, mỗi dòng có thể mang:

- **batchId**: ID của đợt import.
- **rowId** hoặc **sourceId**: định danh ổn định của dòng từ nguồn.
- **targetId**: ID document đích, được tạo/chuẩn hóa trước.
- **payloadHash**: dấu vết kiểm tra nội dung đã xử lý.

Một collection quản lý tiến độ hoặc một unique key trên dữ liệu đích giúp phân biệt **đã ghi thành công**, **chưa ghi** và **dữ liệu xung đột**. Nếu phân phối retry qua nhiều tiến trình, cần thiết kế atomicity của cơ chế chống trùng; việc chỉ log batchId vào file không ngăn hai worker cùng ghi.

### 15.3. Lỗi duplicate không luôn là “đã xử lý thành công”

Khi retry insert với cùng _id, duplicate key có thể có hai ý nghĩa:

1. Lần gửi trước đã ghi **đúng payload mong đợi**.
2. Document khác hoặc phiên bản dữ liệu khác đang chiếm cùng khóa.

Phải **đọc/đối chiếu** ID, khóa nghiệp vụ và nội dung liên quan trước khi coi lỗi trùng là idempotent success. Nếu bỏ qua mọi duplicate key, hệ thống có thể che giấu xung đột dữ liệu.

## 16. Upsert và replace: chú ý semantics của từng thao tác

BulkOperations hỗ trợ những hành vi cập nhật phổ biến:

~~~java
BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);

bulk.upsert(
    Query.query(Criteria.where("sku").is("BOOK-401")),
    new Update()
        .set("name", "MongoDB chuyên sâu")
        .setOnInsert("stock", 0)
        .setOnInsert("active", true)
);

BulkWriteResult result = bulk.execute();
~~~

Trong ví dụ:

- Nếu tìm thấy Product có sku BOOK-401, update các field được chỉ định theo semantics MongoDB.
- Nếu không tìm thấy, upsert có thể tạo document mới từ filter và update.
- **$setOnInsert** chỉ có tác dụng khi insert mới, phù hợp để khởi tạo dữ liệu mặc định.

**Không nhầm upsert với insert.** Nó có thể sửa dữ liệu cũ; nếu dữ liệu import là nguồn không được phép ghi đè name, phải thiết kế filter/update khác.

### 16.1. ReplaceOne có thể xóa field cũ

Thao tác replaceOne thay document bằng một document mới theo hợp đồng replacement (với quy tắc _id). Nếu replacement không có một field từng tồn tại, field đó có thể biến mất.

Khi migrate schema hoặc nhập dữ liệu từ nguồn chỉ có vài cột, **update $set theo field** thường an toàn hơn replace toàn document. Ngược lại, replacement có thể đúng khi nguồn mới là bản đầy đủ và phải thay trọn trạng thái.

### 16.2. Matched và modified khác nhau

Một updateOne có filter trùng nhưng ghi lại cùng giá trị có thể được tính vào **matchedCount** mà không làm tăng **modifiedCount**. Một updateOne không match và không có upsert cũng không phải write error: nó có thể hoàn thành thành công với matched=0.

**Không được dùng ORDERED để “dừng khi matchedCount=0”** như thể đó là exception. Nếu nghiệp vụ yêu cầu mọi update phải match, cần kiểm tra kết quả theo từng operation, hoặc thiết kế điều kiện lỗi/giao thức riêng thay vì suy từ tổng count của bulk.

## 17. Unique index, validation và kiểm tra trước khi ghi

Bulk write không thay thế việc bảo vệ dữ liệu ở database.

### 17.1. Unique index bảo vệ cạnh tranh

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true }
);
~~~

Nếu ứng dụng làm:

1. findOne để xem SKU chưa tồn tại;
2. insert trong bulk;

thì một writer khác vẫn có thể insert cùng SKU ở giữa hai thao tác. **Unique index** mới là ràng buộc cuối cùng bảo vệ tính duy nhất khi có cạnh tranh.

### 17.2. Validation trước batch vẫn rất hữu ích

Nên validate dữ liệu ở tầng ứng dụng trước khi thêm vào bulk:

- SKU không rỗng và đúng định dạng.
- Stock không âm nếu nghiệp vụ yêu cầu.
- Giá/đơn vị tiền đúng kiểu và giới hạn.
- Không có duplicate SKU ngay trong file import, nếu file không được phép có trùng.
- Mỗi dòng có sourceId để đối soát.
- Không có hành động ghi vào tenant hay collection ngoài quyền.

Validation ứng dụng giúp loại lỗi sớm và tạo thông điệp dễ hiểu. **Validator và unique index ở MongoDB** bảo vệ ràng buộc khi vẫn có writer khác hoặc bug ứng dụng.

### 17.3. Vì sao UNORDERED vẫn cần báo cáo lỗi chi tiết?

Nếu 498/500 dòng được ghi nhưng hai dòng lỗi, response không nên chỉ trả “success”. Nên có:

~~~json
{
  "batchId": "import-2025-06-01",
  "status": "PARTIAL",
  "submitted": 500,
  "confirmedSucceeded": 498,
  "confirmedFailed": 2,
  "unknown": 0
}
~~~

JSON trên minh họa **một hợp đồng API do ứng dụng tự định nghĩa**. Những con số chỉ được công bố sau khi ứng dụng có bằng chứng phù hợp; không tự tính confirmedSucceeded bằng submitted - errors trong sự cố mất kết nối có kết quả chưa xác định.

## 18. Chia batch lớn và điều phối vận hành

Driver có giới hạn về kích thước lệnh, số thao tác trong một batch và kích thước BSON. Nó có thể **chia yêu cầu bulk lớn thành những phần phù hợp giới hạn của server**. Ứng dụng cũng thường chủ động chia một file hàng trăm nghìn dòng thành các chunk nhỏ để theo dõi tiến độ.

Ví dụ:

~~~text
Nguồn 25.000 products
    |
    +-- Chunk 1: dòng 1..500
    +-- Chunk 2: dòng 501..1000
    +-- ...
    +-- Chunk 50: dòng 24501..25000
~~~

### 18.1. Tại sao không gom vô hạn vào một bulk?

- Khó theo dõi tiến độ hoặc resume sau khi lỗi.
- Dữ liệu đầu vào chiếm bộ nhớ lớn.
- Một sự cố mạng khiến khó xác định trạng thái một batch rất lớn.
- Việc tổng hợp lỗi và retry từng dòng trở nên phức tạp.
- Write concern, index maintenance và khả năng xử lý của server tạo ra giới hạn thực tế.

Không có một **batch size tối ưu cho mọi hệ thống**. Con số 500 trong ví dụ chỉ để minh họa; phải đo theo kích thước document, loại thao tác, network, deployment và mức độ cạnh tranh.

### 18.2. Giữ mapping dòng nguồn

Một record nhập có thể được biểu diễn:

~~~java
public record ImportRow(
    String sourceId,
    String sku,
    String name,
    int stock
) {}
~~~

Khi chuyển sang write models hoặc BulkOperations, giữ danh sách metadata theo **thứ tự đăng ký**. Nếu có lỗi và driver cung cấp index, có thể đối chiếu index về sourceId. Với chunk, cần lưu cả **chunkId + localIndex** để không nhầm index=3 của chunk này với index=3 của chunk khác.

### 18.3. Một lần execute có thể ghi một phần của nhiều chunk nội bộ

Nếu driver phải split batch, một lỗi/timeout có thể xảy ra sau khi một số chunk đã được ghi. **Không dựa vào một biến boolean success** để đại diện toàn bộ 25.000 record. Hãy lưu checkpoint và đối soát theo document ID hoặc sourceId.

## 19. WriteConcern và tính chắc chắn của phản hồi

MongoDB có **write concern** mô tả mức xác nhận mong đợi cho thao tác ghi. Ví dụ:

- **Acknowledged**: caller nhận phản hồi theo write concern đã chọn.
- **Majority**: yêu cầu mức xác nhận theo majority replica phù hợp với deployment.
- **Unacknowledged**: không nhận xác nhận kết quả chi tiết theo cách thông thường.

Sự khác nhau giữa **lỗi ghi trên một document** và **không đạt write concern** rất quan trọng.

### 19.1. Acknowledged không có nghĩa không thể thất bại sau đó

Một thao tác được acknowledge theo mức cấu hình không tự bảo đảm mọi yêu cầu nghiệp vụ đã đạt. Ví dụ, nếu chỉ ghi một record trong batch mà những record khác lỗi, caller vẫn cần xử lý phần lỗi. Nếu hệ thống yêu cầu độ bền qua failover, lựa chọn write concern và môi trường vận hành phải phù hợp.

### 19.2. WriteConcernError và khả năng đã ghi

Khi server không đáp ứng write concern trong thời gian quy định, một số ghi có thể đã được áp dụng. Không gọi lại **$inc** hoặc **$push** một cách mù quáng. Cần điều tra trạng thái hoặc dùng cơ chế idempotency trước khi retry.

### 19.3. Không dựa vào unacknowledged writes để làm báo cáo chính xác

Nếu workflow cần báo cáo bao nhiêu dòng insert thành công, bao nhiêu dòng lỗi và còn dòng nào chưa rõ, nên dùng write concern cho phép xác nhận và thu thông tin lỗi phù hợp. Không thể xây quy trình đối soát chính xác chỉ từ việc đã gửi dữ liệu vào socket.

## 20. Reactive bulk write: cùng semantics, khác cách thực thi

Spring Data MongoDB reactive có API bulk tương ứng qua **ReactiveMongoTemplate**:

~~~java
import java.util.List;
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.ReactiveBulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public Mono<BulkWriteResult> insertBulkReactive(
        ReactiveMongoTemplate template,
        List<ProductDocument> products) {

    ReactiveBulkOperations bulk = template.bulkOps(
        BulkMode.UNORDERED,
        ProductDocument.class
    );
    bulk.insert(products);
    return bulk.execute();
}
~~~

**Mono<BulkWriteResult>** đại diện cho kết quả ghi khi được subscribe. Chế độ ORDERED/UNORDERED vẫn có cùng ý nghĩa về thứ tự, write errors và partial success. Reactive không làm bulk tự trở thành transaction.

### 20.1. Không gọi block trong WebFlux

Tránh:

~~~java
BulkWriteResult result =
    insertBulkReactive(template, products).block();
~~~

Trong service/controller reactive, hãy trả Mono hoặc compose nó bằng map/flatMap. Nếu cần gửi HTTP response, ánh xạ các trạng thái success/partial/failure sau khi nhận tín hiệu từ publisher.

### 20.2. Tránh subscribe nhiều lần vào publisher ghi

Nếu cùng Mono được subscribe hai lần, mã ghi có thể được thực thi lại. Đặc biệt:

- Hai lần **$inc** có thể cộng hai lần.
- Hai lần **$push** có thể thêm trùng.
- Hai lần insert có thể gây duplicate key.

Đừng tự subscribe() để “kích hoạt trước” rồi trả lại Mono cho WebFlux subscribe một lần nữa. Hãy để framework quản lý subscription, và thiết kế idempotency nếu caller có thể retry.

### 20.3. Transaction reactive

Nếu cần atomicity nhiều document ở reactive stack, phải cấu hình **ReactiveMongoTransactionManager** và quản lý transaction context thông qua cơ chế reactive. Không dùng MongoTransactionManager đồng bộ như thể nó tự áp dụng cho mọi publisher reactive.

Transaction không tự biến unordered write errors thành partial success an toàn để commit; hãy xử lý rollback và retry ở ranh giới nghiệp vụ.

## 21. Kiểm thử tích hợp ORDERED và UNORDERED

Vì khác biệt quan trọng nhất là **những ghi đã được thực hiện trước/sau lỗi**, cần kiểm thử bằng MongoDB thật trong môi trường test. Chỉ mock BulkOperations không chứng minh server dừng tại đúng vị trí.

Trong ví dụ dưới đây, dùng **trùng _id** thay vì SKU để tạo duplicate key. Collection MongoDB thông thường có unique index trên _id, nên không cần phụ thuộc vào bước tạo index SKU trong fixture.

### 21.1. Test ORDERED dừng sau lỗi

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class BulkModeTest {
    @Autowired MongoTemplate template;

    private ProductDocument product(ObjectId id, String sku) {
        return new ProductDocument(
            id, sku, "Test " + sku, 1, true, Instant.now()
        );
    }

    @Test
    void orderedStopsAfterDuplicateId() {
        String suffix = UUID.randomUUID().toString();

        ProductDocument existing = product(
            new ObjectId(), "EXIST-" + suffix
        );
        ProductDocument first = product(
            new ObjectId(), "FIRST-" + suffix
        );
        ProductDocument duplicateId = product(
            existing.id(), "DUP-" + suffix
        );
        ProductDocument last = product(
            new ObjectId(), "LAST-" + suffix
        );

        template.insert(existing);
        try {
            BulkOperations bulk = template.bulkOps(
                BulkMode.ORDERED, ProductDocument.class
            );
            bulk.insert(List.of(first, duplicateId, last));

            assertThatThrownBy(bulk::execute)
                .isInstanceOf(RuntimeException.class);

            assertThat(template.exists(
                Query.query(Criteria.where("_id").is(first.id())),
                ProductDocument.class
            )).isTrue();

            assertThat(template.exists(
                Query.query(Criteria.where("_id").is(last.id())),
                ProductDocument.class
            )).isFalse();
        } finally {
            for (ObjectId id : List.of(
                    existing.id(), first.id(), last.id())) {
                template.remove(
                    Query.query(Criteria.where("_id").is(id)),
                    ProductDocument.class
                );
            }
        }
    }
}
~~~

Test chứng minh **FIRST được ghi**, thao tác mang _id trùng phát sinh lỗi và **LAST không được ghi** trong ORDERED. Điều này cũng chứng minh bulk thất bại **không rollback FIRST**.

Test cố ý dùng **RuntimeException** làm lớp exception chung vì mục tiêu là kiểm chứng trạng thái database sau lỗi; khi xây hệ thống thật nên kiểm tra cụ thể exception được dịch và mã lỗi 11000 theo stack Spring Data/driver đang dùng.

### 21.2. Test UNORDERED cố gắng ghi những item độc lập

Thêm method dưới đây **vào cùng lớp BulkModeTest** của ví dụ trước để tái sử dụng template và hàm product(...):

~~~java
@Test
void unorderedStillWritesIndependentItems() {
    String suffix = UUID.randomUUID().toString();

    ProductDocument existing = product(
        new ObjectId(), "EXIST-U-" + suffix
    );
    ProductDocument first = product(
        new ObjectId(), "FIRST-U-" + suffix
    );
    ProductDocument duplicateId = product(
        existing.id(), "DUP-U-" + suffix
    );
    ProductDocument last = product(
        new ObjectId(), "LAST-U-" + suffix
    );

    template.insert(existing);
    try {
        BulkOperations bulk = template.bulkOps(
            BulkMode.UNORDERED, ProductDocument.class
        );
        bulk.insert(List.of(first, duplicateId, last));

        assertThatThrownBy(bulk::execute)
            .isInstanceOf(RuntimeException.class);

        assertThat(template.exists(
            Query.query(Criteria.where("_id").is(first.id())),
            ProductDocument.class
        )).isTrue();

        assertThat(template.exists(
            Query.query(Criteria.where("_id").is(last.id())),
            ProductDocument.class
        )).isTrue();
    } finally {
        for (ObjectId id : List.of(
                existing.id(), first.id(), last.id())) {
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                ProductDocument.class
            );
        }
    }
}
~~~

Đây là **test cho môi trường MongoDB test bình thường**, trong đó các insert độc lập không gặp thêm lỗi. Nó chứng minh UNORDERED không dừng ở write error của duplicateId như ORDERED. Không được dùng test này để kết luận mọi sự cố mạng, write concern hoặc transaction cũng cho phép những thao tác còn lại hoàn thành.

### 21.3. Tách dữ liệu fixture và giữ đúng thứ tự

Các test nên:

1. Dùng ID/SKU riêng để tránh ảnh hưởng test khác.
2. Seed document trùng khóa **trước khi tạo bulk**.
3. Dùng **một kiểu thao tác đơn giản** khi kiểm tra điểm dừng, tránh thêm phụ thuộc không liên quan.
4. Kiểm tra trạng thái **database sau lỗi** chứ không chỉ kiểm tra exception.
5. Dọn dữ liệu test trong finally, chỉ trên database test.
6. Bổ sung kiểm thử updateOne, updateMulti, upsert và delete với matched/modified counters.
7. Với transaction test, dùng deployment hỗ trợ transaction và kiểm tra rollback riêng.

### 21.4. Test lỗi chưa xác định

Không thể kết luận an toàn retry chỉ từ test duplicate key. Nên có kiểm thử chaos/fault injection ở tầng integration phù hợp: cắt kết nối, timeout, restart node hoặc mô phỏng write concern error. Những test này phải chạy trong môi trường được kiểm soát, **không thực hiện trên production**.

## 22. Chẩn đoán hiệu năng và vận hành

### 22.1. Những chỉ số nên đo

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tổng thao tác đăng ký | Kích thước batch logic |
| Số operation có kết quả acknowledge | Khối lượng ghi được xác nhận |
| Số write errors | Các thao tác bị server báo lỗi |
| Thời gian execute | Độ trễ của batch |
| Batch size và kích thước BSON | Mức sử dụng bộ nhớ/mạng |
| Tỷ lệ duplicate key | Chất lượng dữ liệu import hoặc retry |
| Write concern errors | Vấn đề xác nhận/replication |
| Số unknown outcomes | Mức khó đối soát khi có timeout/kết nối |
| Retry count | Mức tải bổ sung từ chính sách retry |

Không đo hiệu năng chỉ bằng **số record/giây**. Một workflow UNORDERED có throughput cao nhưng bỏ qua lỗi hoặc tạo duplicate do retry có thể tốn chi phí sửa dữ liệu rất lớn.

### 22.2. Index vẫn quan trọng với bulk update

Ví dụ một batch updateOne theo sku:

~~~javascript
db.products.createIndex({ sku: 1 }, { unique: true });

db.products.find({ sku: "BOOK-001" })
  .explain("executionStats");
~~~

Index giúp xác định document mục tiêu nhanh hơn. **explain của find** có thể minh họa đường tìm kiếm tương ứng, nhưng không mô tả toàn bộ chi phí thực thi bulk write. Để đo bulk update, cần thêm metrics thời gian ghi, lock contention, index maintenance và độ lớn document.

### 22.3. Ordered hay unordered: benchmark đúng workload

Một benchmark đáng tin cậy cần:

- Dùng cùng kích thước batch và kích thước document.
- Có cùng index và dữ liệu ban đầu tương đương.
- Tách batch insert độc lập khỏi batch update tranh chấp cùng khóa.
- Đo riêng lỗi và partial success.
- Kiểm soát write concern.
- Thử trên deployment tương tự môi trường triển khai.

Kết quả “UNORDERED nhanh hơn ORDERED 30%” trên một fixture không thể được áp dụng mặc định cho mọi workload. Trong batch nhỏ hoặc đường ghi có bottleneck khác, chênh lệch có thể rất nhỏ.

## 23. Những lỗi tư duy và lỗi kỹ thuật thường gặp

| Triệu chứng/nhận định | Sai ở đâu? | Cách xử lý |
| --- | --- | --- |
| “ORDERED nghĩa là rollback cả batch” | ORDERED chỉ quy định thứ tự/dừng sau write error | Dùng transaction nếu cần atomicity nhiều document |
| “UNORDERED bỏ qua mọi lỗi” | Caller vẫn nhận lỗi; không phải mọi sự cố đều cho phép tiếp tục | Thu errors và xử lý kết quả không xác định |
| “UNORDERED thực thi đúng thứ tự input” | Không cam kết thứ tự | Chỉ nhóm thao tác độc lập |
| “BulkWriteResult có kết quả từng insert” | Count tổng không đủ suy từng record | Lưu operation ID/index và đối soát |
| “execute() ném lỗi nghĩa là không ghi gì” | Partial success có thể đã xảy ra | Đọc lại dữ liệu và log |
| “Retry toàn batch luôn an toàn” | $inc/$push không idempotent | Dùng dedup/operation key và reconciliation |
| “Duplicate key luôn là đã nhập thành công” | Có thể payload xung đột | So sánh document hiện có |
| “matchedCount=0 là write error” | Update không match thường không phải lỗi | Kiểm tra nghiệp vụ riêng |
| “@Version tự hoạt động như save” | BulkOperations không bảo đảm version như repository save | Quản lý version có chủ đích |
| “Chỉ cần validate ở Java” | Writer khác có thể cạnh tranh | Tạo unique index/validator tại MongoDB |
| “Write concern timeout nghĩa là chưa ghi” | Ghi có thể đã xảy ra | Đối soát trước retry |
| “Reactive Mono được tạo là MongoDB đã ghi” | Publisher lazy, cần subscribe | Compose đúng pipeline |
| “Bulk không có giới hạn” | Driver/server có giới hạn batch/BSON | Chia chunk, đo kích thước |
| “Transaction + UNORDERED cho phép commit phần thành công” | Write error có thể abort transaction | Thiết kế rollback/retry toàn transaction |

### 23.1. Quy trình điều tra batch thất bại

1. Xác định **batchId, chunkId, mode** và danh sách thao tác đã đăng ký.
2. Phân loại lỗi: **write error**, **write concern error** hay **kết quả chưa rõ**.
3. Xem exception có index, code, message và partial result hay không.
4. Kiểm tra document đích bằng **_id/sourceId/sku** trên database được phép.
5. Phân loại từng record: confirmed success, confirmed failure, unknown.
6. Xác định thao tác có idempotent khi retry không.
7. Chỉ retry những record phù hợp sau khi đối soát; không gửi lại cả batch một cách mù quáng.
8. Kiểm tra unique index, schema validator, quyền và write concern.
9. Bổ sung test hồi quy cho đúng dạng lỗi và mode.

## 24. Bài tập thực hành

### Bài tập 1: ORDERED và lỗi ở thao tác thứ ba

Bulk insert có năm thao tác: 0, 1 hợp lệ; 2 duplicate key; 3, 4 hợp lệ. Mode ORDERED, không có transaction. Điều gì xảy ra?

**Đáp án:** thao tác 0 và 1 có thể đã ghi thành công; thao tác 2 lỗi; thao tác 3 và 4 không được thực hiện sau lỗi. Không có rollback tự động của 0 và 1.

### Bài tập 2: cùng dữ liệu nhưng UNORDERED

Nếu dùng UNORDERED cho năm thao tác độc lập ở bài 1, có thể kết luận tất cả đều thành công không?

**Đáp án:** không. Thao tác 2 vẫn lỗi. Các thao tác hợp lệ khác có thể tiếp tục và được ghi trong điều kiện bình thường; caller phải xử lý lỗi và xác minh kết quả.

### Bài tập 3: phát hiện sai kỳ vọng về thứ tự

Một batch UNORDERED insert Product X rồi updateOne Product X để tăng stock. Vì sao kết quả không xác định?

**Đáp án:** update có thể thực hiện trước insert và không match, hoặc sau insert và match. Không dùng UNORDERED khi một thao tác phụ thuộc thao tác trước.

### Bài tập 4: chọn mode cho import

File có 2.000 Product độc lập, nghiệp vụ muốn giữ mọi dòng hợp lệ dù một số SKU bị trùng. Nên cân nhắc mode nào?

**Đáp án:** UNORDERED, kết hợp unique index, validation, báo cáo lỗi theo từng input row và cơ chế đối soát/retry.

### Bài tập 5: kết quả count

Bulk có 20 thao tác updateOne, kết quả matchedCount=12, modifiedCount=9. Có bao nhiêu thao tác chắc chắn thất bại?

**Đáp án:** không thể suy ra từ hai con số này. Có update không match nhưng vẫn hoàn thành hợp lệ, và một số update match nhưng không làm đổi dữ liệu. Cần hiểu filter, operation type và lỗi thực tế.

### Bài tập 6: write concern timeout

Bulk update stock có write concern timeout. Client có nên gửi lại mọi $inc không?

**Đáp án:** không. Một số cập nhật có thể đã áp dụng; retry $inc có thể cộng hai lần. Cần đối soát và dùng idempotency strategy phù hợp.

### Bài tập 7: transaction

Ba thao tác bulk phải cùng thành công hoặc cùng rollback vì thuộc một nghiệp vụ. Chỉ chọn BulkMode.ORDERED có đủ không?

**Đáp án:** không. Cần transaction MongoDB được cấu hình/hỗ trợ đúng và ranh giới rollback phù hợp, hoặc một giao thức bù trừ nếu transaction không dùng được.

### Bài tập 8: duplicate ID khi retry

Client retry insert và nhận E11000 trên _id. Có thể coi record đã hoàn thành ngay không?

**Đáp án:** chưa chắc. Phải đọc/đối chiếu document hiện có với payload và operation ID kỳ vọng; có thể dữ liệu đang xung đột.

### Bài tập 9: Spring Data code

Viết hai dòng đầu để tạo bulk UNORDERED cho ProductDocument, sau đó đăng ký một insert.

~~~java
BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);
bulk.insert(new ProductDocument(
    new ObjectId(), "BOOK-999", "Sách mới",
    5, true, Instant.now()
));
~~~

Lệnh ghi được thực hiện khi gọi **bulk.execute()** trong API đồng bộ.

### Bài tập 10: reactive subscription

Một Mono từ ReactiveBulkOperations.execute() được subscribe hai lần. Có rủi ro gì?

**Đáp án:** batch có thể được thực thi lại. Với insert, duplicate key có thể xuất hiện; với $inc/$push, dữ liệu có thể bị cập nhật hai lần. Không tự subscribe lặp và cần idempotency khi có retry.

### Bài tập 11: thao tác nào có thể lặp?

So sánh update $set stock=10 và update $inc stock=1 khi retry.

**Đáp án:** $set cùng giá trị thường idempotent về trường stock nếu không có writer khác; $inc không idempotent vì có thể cộng nhiều lần. Cả hai vẫn cần xét version, timestamp, side effects và concurrency thực tế.

### Bài tập 12: split batch

Driver chia batch lớn thành nhiều phần; mất kết nối khi đang chạy. Có thể chỉ dựa vào lỗi cuối để suy chính xác những input row đã ghi không?

**Đáp án:** không. Cần checkpoint, mapping sourceId/chunkId và đối soát ID trên database, vì có thể tồn tại thao tác chưa rõ kết quả.

## 25. Checklist triển khai thực tế

Trước khi chạy một bulk ghi dữ liệu production, hãy xác nhận:

- **Mục tiêu nghiệp vụ:** chấp nhận partial success hay yêu cầu all-or-nothing?
- **Mode:** các thao tác có phụ thuộc thứ tự không?
- **Validation:** dữ liệu được kiểm tra trước khi đăng ký write model chưa?
- **Database constraints:** unique index/validator có bảo vệ bất biến không?
- **Operation ID:** có thể đối soát từng dòng khi timeout/lỗi không?
- **Write concern:** mức xác nhận có phù hợp nhu cầu độ bền/đối soát không?
- **Error handling:** có phân biệt write errors, write concern và unknown outcome không?
- **Retry:** đã xác định operation nào idempotent và cách chống ghi trùng chưa?
- **Chunking:** batch size có phù hợp bộ nhớ, kích thước BSON và latency không?
- **Transaction:** nếu cần atomicity nhiều document, hạ tầng transaction đã được kiểm chứng chưa?
- **Monitoring:** có metrics số thành công, thất bại, chưa rõ, thời gian và tỷ lệ retry không?
- **Testing:** đã test ORDERED/UNORDERED với duplicate key và kiểm tra dữ liệu sau lỗi chưa?

Checklist này đặc biệt quan trọng khi import dữ liệu từ CSV, message queue hoặc đồng bộ nhiều hệ thống. Batch nhanh nhưng khó khôi phục có thể gây nhiều thiệt hại hơn việc chọn batch nhỏ với khả năng theo dõi rõ ràng.

## 26. Tổng kết

1. **ORDERED** giữ thứ tự khai báo và dừng các thao tác tiếp theo khi một write operation thất bại theo quy tắc bulk thông thường.
2. **UNORDERED** không bảo đảm thứ tự và có thể tiếp tục những thao tác độc lập sau một write error.
3. **Không mode nào tự rollback toàn bộ bulk** khi các ghi thành công trước đó đã được áp dụng ngoài transaction.
4. **Execute có thể ném exception dù một phần dữ liệu đã ghi**; cần theo dõi write errors và đối soát trạng thái thật.
5. **BulkWriteResult** có các count tổng hợp; không tự cung cấp kết quả đầy đủ của từng input row.
6. **Duplicate key, validation và write concern** cần được phân loại; mất kết nối có thể tạo unknown outcome.
7. **Chọn UNORDERED cho các thao tác thực sự độc lập**, không dựa vào thứ tự khi cùng khóa hoặc có điều kiện trước–sau.
8. **Transaction** là cơ chế riêng để đạt atomicity nhiều document khi cần và được hỗ trợ, không phải thuộc tính của ORDERED.
9. **Retry phải dựa trên idempotency và đối soát**. $inc/$push có thể gây ghi lặp; duplicate key không mặc nhiên là thành công.
10. **Reactive bulk write giữ cùng semantics**, nhưng cần quản lý subscription và không block().
11. **Tối ưu batch size, index, write concern và giám sát** dựa trên workload thực tế.
12. **Kiểm thử MongoDB thật** để chứng minh rõ thao tác nào còn tồn tại khi bulk lỗi, không chỉ assert rằng execute() ném exception.

Nắm vững **ORDERED, UNORDERED và hành vi khi một thao tác thất bại** giúp dịch vụ **SPRING_DATA_MONGODB** lựa chọn chiến lược bulk write phù hợp, chấp nhận hoặc ngăn partial success theo nghiệp vụ, phục hồi an toàn sau sự cố và xây dựng quy trình ghi dữ liệu có thể kiểm thử, đối soát, vận hành và mở rộng.
