# Phân biệt thay toàn bộ array và cập nhật từng phần tử

## 1. Bài toán: một thay đổi nhỏ có nên ghi lại cả mảng?

Giả sử document đơn hàng chứa mảng **items** với các sản phẩm đã mua. Một khách hàng tăng số lượng sách từ 2 lên 3. Có hai hướng xử lý:

1. Đọc Order, sửa danh sách items trong Java rồi dùng repository.save(...) để ghi lại document.
2. Gửi lệnh update tới MongoDB, chỉ tăng thuộc tính quantity của **phần tử phù hợp** trong mảng.

Hai cách có thể cho kết quả giống nhau khi chỉ có một request, nhưng khác nhau đáng kể về **phạm vi ghi, xung đột cập nhật, tính nhất quán và chi phí xử lý**. Một lệnh thay toàn bộ array có thể ghi đè thay đổi đồng thời ở các phần tử khác; một update theo phần tử thường diễn đạt chính xác hơn điều kiện nghiệp vụ.

Đây là chủ đề **Phân biệt thay toàn bộ array và cập nhật từng phần tử**, thuộc chương **Thao tác array** của module **SPRING_DATA_MONGODB**. Nội dung tập trung vào MongoDB update operators và cách sử dụng qua **MongoTemplate**, repository hoặc ReactiveMongoTemplate, đồng thời liên hệ tới truy vấn, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

Mục tiêu sau bài:

1. Giải thích sự khác nhau giữa **thay mảng bằng $set**, **save/replace document** và **cập nhật một phần tử**.
2. Sử dụng **$**, **$[]**, **$[identifier]** và **arrayFilters** để sửa đúng phần tử mong muốn.
3. Chọn **$push, $addToSet, $pull, $pop** cho các thao tác thêm/xóa phần tử.
4. Biết khi nào dùng **$inc** thay vì đọc giá trị và tính toán trong ứng dụng.
5. Hiểu tính nguyên tử của update **trên một document**, giới hạn của các thao tác đa document và nguy cơ lost update.
6. Áp dụng điều kiện truy vấn, kiểm tra UpdateResult, optimistic locking và quy tắc nghiệp vụ khi cập nhật.
7. Viết kiểm thử xác minh những phần tử không liên quan không bị thay đổi.

## 2. Document mẫu và đối tượng Java

Giả sử collection **orders** có document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  orderNumber: "ORD-1001",
  status: "DRAFT",
  items: [
    {
      sku: "BOOK-001",
      quantity: NumberInt(2),
      unitPriceMinor: NumberLong("159000")
    },
    {
      sku: "PEN-002",
      quantity: NumberInt(1),
      unitPriceMinor: NumberLong("12000")
    }
  ],
  updatedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Ở đây **items** là một BSON array chứa các embedded documents. Các phần tử nằm **trong cùng document Order**, không phải những document độc lập trong collection khác. Mỗi item có sku, quantity và đơn giá tại thời điểm tạo đơn hàng.

Mô hình Java:

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String orderNumber,
    String status,
    List<OrderItem> items,
    Instant updatedAt
) {}
~~~

~~~java
package com.example.orders;

public record OrderItem(
    String sku,
    int quantity,
    long unitPriceMinor
) {}
~~~

Record giúp dễ hình dung dữ liệu bất biến tại phía Java. Dù một record không thể sửa field trực tiếp, ta vẫn có thể tạo danh sách mới hoặc gửi lệnh **Update** để MongoDB thay đổi trực tiếp các giá trị BSON. Hai hướng đó không giống nhau về cách thực hiện.

### 2.1. Ba mức thao tác cần phân biệt

| Mức thao tác | Ví dụ | Phạm vi |
| --- | --- | --- |
| Thay document | repository.save(order) hoặc replaceOne | Có thể ghi lại toàn bộ document từ trạng thái Java |
| Thay riêng field array | $set: { items: [...] } | Ghi lại giá trị toàn bộ field items |
| Sửa một phần tử/field con | $inc: { "items.$.quantity": 1 } | Chỉ thay giá trị field được chỉ định trên phần tử khớp |

**$set cả field items không giống replace cả Order**, vì những field khác như status và orderNumber vẫn giữ nguyên. Nhưng đối với nội dung array, $set sẽ thay **toàn bộ giá trị hiện tại của mảng**, không tự hợp nhất với bản cũ.

## 3. Hiểu mô hình atomicity trước khi chọn giải pháp

MongoDB bảo đảm **một thao tác ghi trên một document có tính nguyên tử**: một update hợp lệ thay nhiều field của cùng một document được áp dụng như một đơn vị, không để người đọc thấy trạng thái được ghi nửa chừng trong thao tác đó.

Tuy nhiên, **nguyên tử không đồng nghĩa không có lost update** khi ứng dụng:

1. Đọc document ở thời điểm T1.
2. Tạo bản mới dựa trên dữ liệu đã đọc.
3. Ghi bản mới ở thời điểm T2.

Giữa T1 và T2, request khác có thể đã thay đổi document. Một update nguyên tử ở T2 vẫn có thể ghi đè dữ liệu mà request kia vừa lưu.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant M as MongoDB
    participant B as Request B
    A->>M: Đọc Order, items=[BOOK:2, PEN:1]
    B->>M: Đọc Order, items=[BOOK:2, PEN:1]
    A->>M: $set items=[BOOK:3, PEN:1]
    B->>M: $set items=[BOOK:2, PEN:2]
    Note over M: Kết quả có thể mất cập nhật BOOK:3
~~~

Hai thao tác $set là nguyên tử riêng lẻ, nhưng **không có điều kiện bảo vệ phiên bản**, nên thao tác sau có thể thay thế nội dung array do thao tác trước ghi.

Trong khi đó, hai lệnh $inc nhắm đúng phần tử, chẳng hạn tăng BOOK và tăng PEN, có thể được MongoDB áp dụng tuần tự mà không phải ghi lại giá trị cũ của toàn bộ array.

## 4. Thay toàn bộ array bằng $set

Khi muốn thay **toàn bộ danh sách hàng** theo một phiên bản mới đã được xác nhận, có thể dùng $set:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $set: {
      items: [
        { sku: "BOOK-001", quantity: 3, unitPriceMinor: NumberLong("159000") },
        { sku: "PEN-002", quantity: 1, unitPriceMinor: NumberLong("12000") }
      ]
    }
  }
);
~~~

Sau update, field **items** có đúng hai phần tử theo mảng mới. Các field ngoài items không bị ghi đè do riêng lệnh $set này. Nhưng nếu người khác thêm item thứ ba ngay trước lúc update, mảng mới sẽ **loại mất item thứ ba**.

Trong Spring Data:

~~~java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

public UpdateResult replaceItems(
        MongoTemplate template,
        ObjectId orderId,
        List<OrderItem> replacement) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
    );

    Update update = new Update().set("items", replacement);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

Spring Data MappingMongoConverter chuyển các OrderItem trong List thành embedded BSON documents. Ví dụ giả định OrderDocument dùng các field trùng tên trong MongoDB và MongoTemplate đã được cấu hình.

### 4.1. Khi nào thay cả array là chủ đích đúng?

- Người dùng thực hiện thao tác **“Thay toàn bộ giỏ hàng bằng danh sách vừa xác nhận”**.
- Có yêu cầu **sắp xếp lại thứ tự** toàn bộ phần tử.
- Quy trình migration thay đổi schema cho tất cả item trong một array nhỏ và đã kiểm soát concurrency.
- Mảng thể hiện một cấu hình trọn gói phải được validate như một phiên bản duy nhất.

Ngược lại, nếu yêu cầu chỉ là “tăng quantity của BOOK-001 lên một”, thay toàn mảng thường **rộng hơn phạm vi nghiệp vụ cần thiết**.

### 4.2. Cần kiểm soát dữ liệu đầu vào

Trước khi thay toàn mảng, nên xác nhận:

1. **SKU hợp lệ** và mỗi SKU có xuất hiện tối đa một lần theo hợp đồng.
2. quantity dương và không vượt giới hạn nghiệp vụ.
3. Đơn giá được lấy từ nguồn tin cậy hoặc là snapshot được phép lưu.
4. Order vẫn ở trạng thái cho phép sửa.
5. Yêu cầu ghi có cơ chế phát hiện thay đổi đồng thời nếu cần.

Không nên lấy toàn bộ cấu trúc items từ request HTTP và ghi thẳng vào MongoDB mà không kiểm tra ownership, giá hay field nội bộ.

## 5. Repository.save có thể là thao tác rộng hơn

Một cách khác:

~~~java
OrderDocument previous = orderRepository.findById(orderId)
    .orElseThrow();

List<OrderItem> newItems = buildNewItems(previous.items());

OrderDocument edited = new OrderDocument(
    previous.id(),
    previous.orderNumber(),
    previous.status(),
    newItems,
    previous.updatedAt()
);

OrderDocument saved = orderRepository.save(edited);
~~~

Ở đây **buildNewItems(...)** là hàm nghiệp vụ giả định dùng để tạo danh sách mới. Đoạn mã minh họa đọc → biến đổi trong Java → save. Nó không có cơ chế bảo vệ phiên bản trong mô hình OrderDocument hiện tại.

Với entity đã tồn tại, repository.save thường đi qua cơ chế lưu document của Spring Data MongoDB và có thể ghi lại nhiều field của entity, không chỉ items. Nếu bản đọc thiếu field hoặc stale, việc save có thể làm mất dữ liệu.

**Không suy rằng save tự động merge từng item theo SKU**. Spring Data không thể biết SKU nào được phép ghi đè hay bản nào mới hơn nếu ứng dụng không thiết kế quy tắc đó.

Khi domain dùng **@Version** và optimistic locking, repository.save có thể phát hiện bản stale theo quy tắc version. Phần 13 sẽ trình bày cơ chế bảo vệ này.

## 6. Cập nhật một phần tử đầu tiên bằng toán tử vị trí $

Nếu chỉ cần tăng số lượng của item **BOOK-001**, MongoDB có positional operator **$** để tham chiếu phần tử mảng đầu tiên khớp điều kiện truy vấn:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    "items.sku": "BOOK-001"
  },
  {
    $inc: { "items.$.quantity": 1 }
  }
);
~~~

Trong biểu thức **items.$.quantity**, dấu **$** là vị trí phần tử phù hợp **đầu tiên** trong array items. Điều kiện **items.sku** ở filter là rất quan trọng để MongoDB xác định phần tử tương ứng.

Nếu array có hai item cùng SKU, positional $ chỉ sửa **phần tử khớp đầu tiên**, không tự sửa cả hai. Nếu nghiệp vụ quy định mỗi SKU chỉ có một dòng hàng, cần bảo vệ bất biến này khi thêm item và trong kiểm thử.

### 6.1. MongoTemplate.updateFirst

~~~java
import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public UpdateResult increaseQuantity(
        MongoTemplate template, ObjectId orderId, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

Lệnh này không cần đọc toàn bộ Order trước khi tăng quantity và không ghi lại cả array từ một bản copy cũ. Nó thay đổi đúng field quantity của một item trên document khớp.

### 6.2. Vì sao $inc tốt hơn $set cho thao tác cộng?

Giả sử quantity=2. Hai request đồng thời đều đọc giá trị 2 rồi cùng gửi $set quantity=3; kết quả cuối có thể chỉ là 3. Nếu cả hai gửi **$inc quantity:1** trên cùng phần tử, MongoDB áp dụng mỗi update nguyên tử, kết quả có thể là **4** nếu cả hai đều thành công.

Tuy nhiên, $inc **không tự bảo vệ** quy tắc quantity tối đa. Nếu tồn kho chỉ còn một sản phẩm, cần bổ sung điều kiện bất biến/luồng reservation phù hợp. Chỉ dùng $inc không đảm bảo không oversell.

### 6.3. Giới hạn của positional $

Toán tử vị trí đơn **$** không nên dùng tùy tiện khi filter liên quan nhiều array khác nhau hoặc khi cần sửa nhiều phần tử. Trong các tình huống mảng lồng nhau hoặc nhiều phần tử khớp, nên dùng **$[]** hoặc **$[identifier]** cùng arrayFilters theo khả năng phiên bản MongoDB.

**Không dùng positional $ như một lệnh upsert tùy ý** khi chưa có phần tử array để match. Nếu không có phần tử phù hợp, nên quyết định bổ sung item hoặc trả lỗi nghiệp vụ, không để một positional path mơ hồ tự tạo array.

## 7. Sửa tất cả phần tử bằng $[]

Toán tử **$[]** áp dụng update vào **mọi phần tử** của một array thuộc document khớp:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $inc: { "items.$[].quantity": 1 }
  }
);
~~~

Ví dụ trên tăng quantity **của mọi dòng hàng** lên một, chứ không chỉ BOOK-001. Đây chỉ là minh họa cú pháp; nghiệp vụ đặt hàng thực tế hiếm khi cần tăng toàn bộ số lượng một cách vô điều kiện.

Trong MongoTemplate:

~~~java
Update update = new Update()
    .inc("items.$[].quantity", 1);

template.updateFirst(
    Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
    ),
    update,
    OrderDocument.class
);
~~~

Nếu bạn chỉ định **items.$[].quantity**, mỗi phần tử có cùng update trên field quantity. Nếu array rỗng thì không có phần tử nào để cập nhật. Nếu mảng chứa những phần tử không cùng schema hoặc quantity không phải kiểu số, thao tác có thể lỗi.

**Phân biệt:** $[] là mọi phần tử **trong một array của document được chọn**; nó không có nghĩa cập nhật toàn bộ document trong collection. Để cập nhật nhiều document, còn phải chọn giữa **updateOne/updateFirst** và **updateMany/updateMulti**.

## 8. Chọn phần tử bằng $[identifier] và arrayFilters

Muốn tăng quantity ở **mọi dòng có sku=BOOK-001**, ngay cả khi array có nhiều dòng trùng SKU, có thể dùng **filtered positional operator**:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $inc: { "items.$[line].quantity": 1 }
  },
  {
    arrayFilters: [
      { "line.sku": "BOOK-001" }
    ]
  }
);
~~~

Trong đường dẫn **items.$[line].quantity**, chuỗi **line** là một identifier để gắn với bộ lọc **line.sku**. MongoDB sửa mỗi phần tử items thỏa điều kiện arrayFilters.

Đây là điểm khác biệt với positional **$**:

| Cú pháp | Phạm vi trong array |
| --- | --- |
| items.$.quantity | Phần tử khớp đầu tiên theo điều kiện vị trí từ query |
| items.$[].quantity | Tất cả phần tử trong array |
| items.$[line].quantity + arrayFilters | Tất cả phần tử thỏa bộ lọc của line |

### 8.1. MongoTemplate với Update.filterArray

Spring Data MongoDB cung cấp cách khai báo array filter trong Update:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
);

Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku").is("BOOK-001")
    );

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

Ví dụ sử dụng API **Update.filterArray(CriteriaDefinition)** trong các phiên bản Spring Data MongoDB có hỗ trợ filtered positional updates. Tên trong **line.sku** phải khớp identifier **line** của đường dẫn update.

**Chú ý:** với một query chỉ lọc _id và status, **matchedCount có thể là 1 dù không có phần tử nào thỏa arrayFilters**; khi đó modifiedCount có thể bằng 0. Nếu nghiệp vụ yêu cầu báo lỗi khi SKU không có trong Order, cần kiểm tra thêm điều kiện **items.sku** ngay trong Query hoặc thiết kế kết quả trả rõ ràng.

### 8.2. Khi nào nên dùng arrayFilters?

- Một array có thể chứa nhiều phần tử thỏa cùng điều kiện.
- Cần cập nhật các item theo loại, nhãn, trạng thái hoặc khoảng giá trị.
- Có các array lồng nhau và cần định vị phần tử theo nhiều cấp.
- Không muốn thay cả mảng từ trạng thái Java có thể đã cũ.

Không tự tạo arrayFilters từ chuỗi JSON do client gửi mà chưa kiểm soát. Hãy bind các giá trị từ tham số đã validate, dùng API Query/Update của framework, và kiểm tra đường dẫn field theo schema đã định.

## 9. Thêm phần tử: $push và $addToSet

Sửa một phần tử khác với **thêm một phần tử mới**. MongoDB có các toán tử chuyên dụng cho array.

### 9.1. $push: luôn thêm phần tử

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011"), status: "DRAFT" },
  {
    $push: {
      items: {
        sku: "ERASER-003",
        quantity: 1,
        unitPriceMinor: NumberLong("8000")
      }
    }
  }
);
~~~

Trong MongoTemplate:

~~~java
Update update = new Update().push(
    "items",
    new OrderItem("ERASER-003", 1, 8_000L)
);

template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")),
    update,
    OrderDocument.class
);
~~~

**$push không tự chống trùng SKU**. Nếu request được gửi hai lần, bạn có thể có hai phần tử ERASER-003. Nếu mỗi SKU phải duy nhất trong Order, cần thiết kế thao tác thêm có điều kiện, idempotency key hoặc một chiến lược data model phù hợp.

### 9.2. $addToSet: thêm nếu chưa có phần tử giống hệt

Với array **tags** gồm các chuỗi:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  { $addToSet: { tags: "SPRING" } }
);
~~~

Nếu tags đã chứa chuỗi SPRING, nó không được thêm lần nữa. Đây là kiểu **set-like operation** cho các phần tử giống nhau theo quy tắc so sánh BSON.

Trong Spring Data:

~~~java
Update update = new Update()
    .addToSet("tags", "SPRING");
~~~

**Cẩn thận với array of objects:** $addToSet so sánh **toàn bộ giá trị embedded document**, không tự hiểu rằng hai object cùng sku là một item nghiệp vụ duy nhất. Nếu price hoặc quantity khác, hai object có thể cùng tồn tại dù cùng SKU.

### 9.3. Thêm nhiều phần tử bằng $each

MongoDB hỗ trợ:

~~~javascript
db.products.updateOne(
  { sku: "BOOK-001" },
  { $addToSet: { tags: { $each: ["JAVA", "MONGODB"] } } }
);
~~~

Trong Spring Data:

~~~java
Update update = new Update()
    .addToSet("tags")
    .each("JAVA", "MONGODB");
~~~

Các thao tác $push cũng có biến thể $each, thậm chí có tùy chọn $position, $sort, $slice tùy yêu cầu; cần kiểm tra khả năng phiên bản MongoDB/Spring Data và chính sách thứ tự trước khi áp dụng.

## 10. Xóa phần tử: $pull và $pop

### 10.1. $pull: loại các phần tử thỏa điều kiện

Nếu người dùng xóa SKU PEN-002 khỏi đơn nháp:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT"
  },
  {
    $pull: {
      items: { sku: "PEN-002" }
    }
  }
);
~~~

**$pull xóa tất cả phần tử array thỏa điều kiện**, không chỉ một phần tử đầu tiên. Nếu dữ liệu lỗi có hai dòng cùng SKU, cả hai có thể bị xóa.

Trong MongoTemplate:

~~~java
import org.bson.Document;

Update update = new Update().pull(
    "items",
    new Document("sku", "PEN-002")
);

template.updateFirst(
    Query.query(Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")),
    update,
    OrderDocument.class
);
~~~

### 10.2. $pop: xóa phần tử ở đầu hoặc cuối

Nếu array có ý nghĩa thứ tự và cần bỏ **phần tử cuối**:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $pop: { items: 1 } }
);
~~~

Giá trị **1** loại phần tử cuối, **-1** loại phần tử đầu. $pop **không lọc theo SKU**; vì vậy nó thường không phù hợp cho “xóa sản phẩm BOOK-001” nếu vị trí item trong mảng có thể thay đổi.

### 10.3. Khác biệt với $unset

Để loại một field của item mà vẫn giữ item, có thể dùng **$unset** trên đường dẫn phần tử phù hợp:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011"), "items.sku": "BOOK-001" },
  { $unset: { "items.$.unitPriceMinor": "" } }
);
~~~

Lệnh này **không xóa item khỏi mảng**, chỉ xóa field unitPriceMinor của item phù hợp. Nếu phần tử bắt buộc phải có đơn giá, thao tác sẽ phá invariant và không nên được phép trong ứng dụng.

Đặc biệt, **$unset một phần tử tại chỉ số mảng** có thể để lại giá trị null ở vị trí đó thay vì làm array ngắn lại; dùng **$pull** khi muốn loại một phần tử khỏi mảng.

## 11. Thay một trường của item không phải thay item hoặc array

Giả sử cần cập nhật giá snapshot của một item chưa chốt:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    "items.sku": "BOOK-001"
  },
  {
    $set: {
      "items.$.unitPriceMinor": NumberLong("149000")
    }
  }
);
~~~

Lệnh chỉ thay **unitPriceMinor** của item đầu tiên có SKU phù hợp, giữ quantity và các item khác không đổi.

Trong Spring Data:

~~~java
Update update = new Update()
    .set("items.$.unitPriceMinor", 149_000L);
~~~

So sánh:

| Lệnh | Kết quả |
| --- | --- |
| $set: { items: newArray } | Thay toàn bộ array items |
| $set: { "items.$": newItem } | Thay toàn bộ object của phần tử khớp đầu tiên |
| $set: { "items.$.unitPriceMinor": newPrice } | Chỉ thay field giá của phần tử khớp |
| $inc: { "items.$.quantity": 1 } | Tăng số lượng trên phần tử khớp |

Khi thay **toàn bộ embedded object** bằng items.$, những field của item cũ không có trong object mới sẽ không được bảo toàn. Nếu chỉ muốn thay một field, đặt đường dẫn tới chính field đó.

## 12. Đường dẫn lồng nhau và nhiều cấp array

Một schema phức tạp có thể có:

~~~javascript
{
  shipments: [
    {
      shipmentCode: "S1",
      packages: [
        { packageCode: "P1", checked: false },
        { packageCode: "P2", checked: false }
      ]
    }
  ]
}
~~~

Muốn đánh dấu checked=true cho package P2 thuộc shipment S1, có thể dùng hai identifier:

~~~javascript
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  {
    $set: {
      "shipments.$[shipment].packages.$[pkg].checked": true
    }
  },
  {
    arrayFilters: [
      { "shipment.shipmentCode": "S1" },
      { "pkg.packageCode": "P2" }
    ]
  }
);
~~~

Nhờ arrayFilters, MongoDB định vị phần tử ở **từng tầng array**, thay vì thay cả cấu trúc shipments. Tuy nhiên, nhiều cấp nested arrays làm truy vấn, index và cập nhật khó hiểu hơn. Nếu shipment/package có vòng đời độc lập và được truy cập thường xuyên, hãy đánh giá lại ranh giới nhúng và tham chiếu.

**Không dùng một path update tùy ý do client truyền**. Tên các trường và identifier phải đến từ code được kiểm soát; client chỉ nên cung cấp giá trị như shipmentCode hoặc packageCode sau validation.

## 13. Tránh lost update bằng optimistic locking

Cập nhật targeted giúp giảm rủi ro ghi đè toàn array, nhưng khi nghiệp vụ cần thay cả danh sách, cần phát hiện phiên bản cũ.

Spring Data MongoDB hỗ trợ **@Version**:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record VersionedOrderDocument(
    @Id ObjectId id,
    String orderNumber,
    String status,
    List<OrderItem> items,
    Instant updatedAt,
    @Version Long version
) {}
~~~

Khi repository.save thực hiện optimistic locking cho một entity có version được quản lý, Spring Data có thể phát hiện stale version và ném **OptimisticLockingFailureException** nếu update không còn khớp phiên bản mong đợi. Phải sử dụng write concern được acknowledge và giữ đúng semantics của framework/driver trong phiên bản dự án.

### 13.1. Điều kiện version trong update

Một chiến lược khác là gắn expectedVersion vào filter:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    version: NumberLong("4")
  },
  {
    $set: {
      items: [
        { sku: "BOOK-001", quantity: 3, unitPriceMinor: NumberLong("159000") }
      ]
    },
    $inc: { version: NumberLong("1") }
  }
);
~~~

Với version=4, request hợp lệ đổi version thành 5. Request khác dựa trên version=4 có **matchedCount=0**, từ đó ứng dụng trả thông báo conflict và yêu cầu client tải lại dữ liệu.

Ví dụ trên mô tả **MongoDB driver/mongosh raw update**. Khi dùng MongoTemplate trên entity có @Version, Spring Data có quy tắc quản lý version trong update; tránh vừa tự tăng version bằng code vừa để framework tự tăng mà chưa xác minh cơ chế phiên bản đang dùng.

### 13.2. Không nhầm optimistic lock với transaction

Optimistic locking kiểm tra xem document còn ở phiên bản mong đợi trước một update. Transaction nhiều document có mục đích nhóm những ghi trên các document khác nhau thành một đơn vị commit/rollback. Một transaction cũng **không tự giải quyết mọi cuộc đua nghiệp vụ** nếu thiếu filter hoặc bất biến phù hợp.

Nếu chỉ cập nhật các field khác nhau trong **một Order**, một lệnh update nguyên tử có điều kiện thường đơn giản hơn việc lập transaction nhiều document.

## 14. Kiểm tra UpdateResult để không báo thành công sai

Lệnh update có thể **không tìm thấy document** hoặc **tìm thấy nhưng không thay đổi gì**. Với MongoTemplate:

~~~java
UpdateResult result = template.updateFirst(
    query,
    update,
    OrderDocument.class
);

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

Hai chỉ số khác nhau:

| Kết quả | Ý nghĩa thường gặp |
| --- | --- |
| matched=0 | Không có document khớp filter, ví dụ Order không tồn tại, sai status hoặc SKU |
| matched=1, modified=1 | Document khớp và thực sự bị sửa |
| matched=1, modified=0 | Document khớp nhưng update không làm đổi dữ liệu, ví dụ $set cùng giá trị hoặc arrayFilters không match item |

Với **updateFirst**, matchedCount tối đa 1; với **updateMulti**, có thể nhiều document được match. Khi sử dụng lệnh update cùng arrayFilters và query chỉ theo _id, matched=1 **không chứng minh có item nào được sửa**.

### 14.1. Ràng buộc điều kiện nghiệp vụ vào filter

Nếu chỉ được tăng số lượng trên Order đang DRAFT:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
        .and("items.sku").is(sku)
);
~~~

Việc thêm status vào filter biến yêu cầu “Order vẫn còn DRAFT” thành một phần **điều kiện ghi nguyên tử**, tốt hơn kiểu đọc status trước rồi update không kiểm tra lại.

Đừng trả lỗi “Order không tồn tại” cho mọi matched=0. Có thể Order tồn tại nhưng đã chuyển trạng thái, hoặc SKU không có trong array. Nếu API cần phân biệt các lỗi, phải dùng đường kiểm tra phù hợp nhưng cũng hiểu rằng mỗi lần đọc thêm có thể thấy trạng thái sau khi update đã thất bại.

## 15. Tăng/giảm số lượng có giới hạn

Giảm quantity 1 đơn vị chỉ hợp lệ nếu quantity hiện tại lớn hơn 1, hoặc nghiệp vụ phải chọn **xóa dòng hàng khi quantity về 0**.

Một filter với **$elemMatch** gắn điều kiện sku và quantity cho **cùng một item**:

~~~javascript
db.orders.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    status: "DRAFT",
    items: {
      $elemMatch: {
        sku: "BOOK-001",
        quantity: { $gt: 1 }
      }
    }
  },
  {
    $inc: { "items.$.quantity": -1 }
  }
);
~~~

Điều kiện $elemMatch tránh trường hợp một item có SKU phù hợp nhưng quantity thấp, còn item khác có quantity > 1. Toán tử vị trí **$** tham chiếu phần tử được match của mảng theo điều kiện phù hợp.

Trong MongoTemplate:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Criteria eligibleItem = Criteria.where("sku").is(sku)
    .and("quantity").gt(1);

Query query = Query.query(
    Criteria.where("_id").is(orderId)
        .and("status").is("DRAFT")
        .and("items").elemMatch(eligibleItem)
);

Update update = new Update()
    .inc("items.$.quantity", -1);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

Điều kiện và phép giảm nằm trong **một update nguyên tử trên một document**. Nếu không khớp, không nên tự đổi quantity thành 0 khi chưa có chính sách nghiệp vụ.

**Lưu ý về hệ thống bán hàng:** bảo đảm quantity của item không âm **khác** với bảo đảm tồn kho của Product không bị oversell khi nhiều Order cạnh tranh. Điều kiện tồn kho thường nằm trên document Product hoặc quy trình reservation riêng; nếu cần ghi đồng thời nhiều document, phải thiết kế transaction hoặc giao thức phối hợp thích hợp.

## 16. Cập nhật array qua reactive access

Với **ReactiveMongoTemplate**, cùng Query và Update có thể dùng trong publisher:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<UpdateResult> incrementReactive(
        ReactiveMongoTemplate template, ObjectId orderId, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(orderId)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    return template.updateFirst(
        query, update, OrderDocument.class
    );
}
~~~

**Mono<UpdateResult>** chỉ thực hiện update khi được subscribe. Trong WebFlux, không gọi **block()** để lấy kết quả trong service/controller và cũng không tự subscribe() nhiều lần: mỗi subscription có thể thực thi lại update, đặc biệt nguy hiểm với **$inc** vì nó không idempotent.

### 16.1. Cập nhật rồi đọc trạng thái mới

Nếu API cần trả Order mới, có thể dùng **findAndModify** với tùy chọn returnNew:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

public Mono<OrderDocument> incrementAndRead(
        ReactiveMongoTemplate template, ObjectId id, String sku) {

    Query query = Query.query(
        Criteria.where("_id").is(id)
            .and("status").is("DRAFT")
            .and("items.sku").is(sku)
    );

    Update update = new Update()
        .inc("items.$.quantity", 1);

    FindAndModifyOptions options =
        FindAndModifyOptions.options().returnNew(true);

    return template.findAndModify(
        query, update, options, OrderDocument.class
    );
}
~~~

Nếu document không khớp query, publisher có thể hoàn thành **không có Order**. Tầng API cần xử lý trường hợp này; không nên trả thành công giả. findAndModify cho phép update và lấy document sau update như một thao tác trên document đó, nhưng không thay thế bảo vệ idempotency khi client retry.

### 16.2. Tránh retry tự động với $inc

Một retry sau timeout có thể gửi lại update tăng quantity, kể cả khi server đã áp dụng lần đầu nhưng response bị mất. Nếu hệ thống cần “mỗi lệnh tăng chỉ áp dụng một lần”, phải thiết kế **idempotency key / deduplication / trạng thái lệnh** phù hợp. Đừng mặc định rằng dùng reactive hoặc transaction sẽ làm một lệnh $inc tự động trở thành idempotent.

## 17. Kích thước array, index và hiệu năng

MongoDB có giới hạn kích thước BSON document (thông thường **16 MiB**). Một array embedded tăng không giới hạn có thể khiến Order vượt giới hạn hoặc tạo chi phí update/đọc lớn.

Các tín hiệu cần đánh giá:

- Array items thường có bao nhiêu phần tử?
- API có thường đọc cả Order hay chỉ một item?
- Có nhiều request cập nhật các item khác nhau trong cùng Order không?
- SKU có cần index và truy vấn theo item không?
- Có yêu cầu giữ lịch sử nhiều năm làm array tăng không giới hạn không?

### 17.1. Multikey index

Nếu thường tìm Order chứa một SKU:

~~~javascript
db.orders.createIndex({ "items.sku": 1 });
~~~

MongoDB sử dụng **multikey index** cho field nằm trong array. Index giúp tìm document có item mang SKU phù hợp, nhưng có chi phí bảo trì khi mảng thay đổi. Khi filter còn có status hoặc tenant, cần đánh giá compound index theo workload thực, chẳng hạn:

~~~javascript
db.orders.createIndex({
  status: 1,
  "items.sku": 1
});
~~~

Không nên tự tạo nhiều index chỉ dựa vào mọi field xuất hiện trong một update. Index tối ưu đường **tìm document**, còn hiệu năng thực tế còn phụ thuộc số document, độ chọn lọc và khả năng cập nhật.

### 17.2. Đo bằng explain

~~~javascript
db.orders.find({
  status: "DRAFT",
  "items.sku": "BOOK-001"
}).explain("executionStats");
~~~

Quan sát winningPlan, totalKeysExamined, totalDocsExamined và nReturned. **explain** của một truy vấn find không tự mô tả đầy đủ chi phí update array, nhưng cho biết liệu giai đoạn tìm document mục tiêu có được index hỗ trợ không.

Khi update chậm, cần thêm metrics thời gian ghi, kích thước document, index maintenance, lock/contention và tần suất sửa trên cùng document. Một $inc theo phần tử thường tránh việc ứng dụng phải đọc/sửa/ghi cả array, nhưng không thể kết luận mọi update theo phần tử đều nhanh hơn trong mọi tình huống.

### 17.3. Khi nào nên tách document?

Array lồng trong Order hợp lý khi items có vòng đời phụ thuộc Order và thường được đọc cùng Order. Nếu một collection có một document chứa mảng hàng triệu sự kiện, các phần tử được thêm liên tục, cần phân trang từng sự kiện và cập nhật độc lập, mô hình **collection riêng + reference** có thể phù hợp hơn.

Không tách array chỉ vì một lệnh update phức tạp; cân nhắc ranh giới aggregate, kích thước BSON, mô hình truy cập và tính nhất quán theo nghiệp vụ.

## 18. Thay array và concurrency: các tình huống so sánh

| Tình huống | Thao tác ưu tiên xem xét | Rủi ro cần quản lý |
| --- | --- | --- |
| Khách hàng thay toàn bộ giỏ hàng | $set items + version check | Lost update nếu dùng bản stale |
| Tăng số lượng một SKU | $inc items.$.quantity | Trùng SKU, retry và giới hạn số lượng |
| Đổi một field của item | $set items.$.field | Nhắm đúng item, không làm mất field khác |
| Tăng mọi item | $inc items.$[].quantity | Có thể sửa rộng hơn mong đợi |
| Sửa mọi item thỏa điều kiện | $[identifier] + arrayFilters | Matched document nhưng không modified item |
| Thêm item mới | $push | Trùng SKU nếu request lặp |
| Thêm tag không trùng giá trị | $addToSet | Embedded object được so toàn bộ, không theo khóa nghiệp vụ |
| Xóa item theo SKU | $pull | Xóa tất cả phần tử thỏa điều kiện |
| Xóa phần tử cuối | $pop | Phụ thuộc thứ tự array, không lọc theo SKU |
| Cập nhật hai collection | Transaction hoặc giao thức phối hợp | Atomicity một document không áp dụng sang collection khác |

### 18.1. “Thay toàn mảng” có luôn sai không?

Không. Khi nghiệp vụ thật sự định nghĩa **bản danh sách mới là nguồn chân lý**, thay toàn array có thể là lựa chọn đúng và đơn giản. Điều cần làm là xác minh dữ liệu đầu vào, trạng thái Order, phiên bản hiện tại và ảnh hưởng khi có request song song.

### 18.2. “Cập nhật phần tử” có luôn đúng không?

Không. Nếu việc đổi một item làm vi phạm tổng giá, số lượng tối đa, quy tắc khuyến mãi hoặc trạng thái đơn, update từng field riêng có thể khiến các field liên quan không được đồng bộ. Có thể cần **một update nguyên tử có nhiều toán tử** trên cùng document, một update pipeline hoặc quy trình tính toán lại với optimistic locking.

Chọn phạm vi ghi theo **bất biến nghiệp vụ cần bảo vệ**, không theo số dòng code ít nhất.

## 19. Kiểm thử tích hợp với MongoTemplate

Unit test chỉ giả lập UpdateResult chưa kiểm chứng MongoDB có hiểu đường dẫn **items.$.quantity** hay converter có map OrderItem đúng. Nên có kiểm thử tích hợp trên database riêng, ví dụ MongoDB Testcontainers được cấu hình cho Spring Boot test.

Một test kiểm tra **chỉ item được chọn tăng quantity**:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

@DataMongoTest
class OrderArrayUpdateTest {

    @Autowired
    MongoTemplate template;

    @Test
    void incrementsOnlyMatchingItem() {
        OrderDocument inserted = template.insert(
            new OrderDocument(
                null,
                "TEST-" + UUID.randomUUID(),
                "DRAFT",
                List.of(
                    new OrderItem("BOOK-001", 2, 159_000L),
                    new OrderItem("PEN-002", 1, 12_000L)
                ),
                Instant.now()
            )
        );

        ObjectId orderId = inserted.id();
        assertThat(orderId).isNotNull();

        try {
            Query query = Query.query(
                Criteria.where("_id").is(orderId)
                    .and("status").is("DRAFT")
                    .and("items.sku").is("BOOK-001")
            );

            UpdateResult result = template.updateFirst(
                query,
                new Update().inc("items.$.quantity", 1),
                OrderDocument.class
            );

            assertThat(result.getMatchedCount()).isEqualTo(1);
            assertThat(result.getModifiedCount()).isEqualTo(1);

            OrderDocument loaded = template.findById(
                orderId, OrderDocument.class
            );

            assertThat(loaded).isNotNull();
            assertThat(loaded.items()).hasSize(2);
            assertThat(loaded.items().get(0).quantity()).isEqualTo(3);
            assertThat(loaded.items().get(1).quantity()).isEqualTo(1);
            assertThat(loaded.items().get(0).unitPriceMinor())
                .isEqualTo(159_000L);
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(orderId)),
                OrderDocument.class
            );
        }
    }
}
~~~

Test sử dụng một Order riêng cho từng lần chạy và dọn document trong finally. **Không chạy trên production.** Nó xác nhận item BOOK tăng từ 2 lên 3 và PEN giữ quantity=1, đồng thời bảo toàn đơn giá.

### 19.1. Test thêm các trường hợp quan trọng

| Test case | Điều cần xác minh |
| --- | --- |
| $set cả array | Các item mới thay danh sách cũ chính xác |
| $inc positional $ | Chỉ item đầu khớp được thay |
| $[] | Mọi phần tử đều thay đúng |
| $[line] và arrayFilters | Chỉ các phần tử thỏa filter thay |
| Không có SKU trong Order | UpdateResult phản ánh không có thay đổi theo query |
| Order status khác DRAFT | Không cập nhật dù ID và SKU tồn tại |
| $push hai lần | Có nguy cơ thêm trùng nếu không có kiểm soát |
| $addToSet tag trùng | Không tạo chuỗi trùng |
| $pull theo SKU | Loại mọi item thỏa điều kiện |
| Hai request $inc cùng một item | Kết quả tích lũy nếu đều thành công |
| Hai request thay mảng từ bản stale | Bị chặn bởi version check nếu hệ thống yêu cầu |
| Quantity=1, giảm 1 với filter quantity>1 | Không giảm xuống 0 |
| Array rỗng và document thiếu items | Xác định chính sách và kiểm tra hành vi cập nhật |

### 19.2. Quan sát BSON trực tiếp

Nếu hành vi không đúng, đọc BSON của một Order trong **database test**:

~~~javascript
db.orders.findOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { orderNumber: 1, status: 1, items: 1 }
);
~~~

Đối chiếu giá trị và kiểu BSON của items.quantity, items.unitPriceMinor, xem có duplicate SKU hay field thiếu. Khi record trong Java có tên khác BSON, phải xác minh @Field và cấu trúc mapping.

## 20. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tăng quantity một item nhưng item khác bị mất | Thay cả array từ dữ liệu stale | Dùng targeted update hoặc version check |
| Positional $ không có phần tử | Query không chứa điều kiện match items hoặc SKU sai | Kiểm tra filter và BSON thực |
| Hai SKU trùng nhưng chỉ một item được sửa | Positional $ chỉ chọn phần tử đầu | Đặt invariant unique SKU hoặc dùng arrayFilters |
| Tất cả item bị đổi | Dùng $[] thay vì $[line] | Rà soát đường dẫn update |
| Không item nào đổi dù Order match | arrayFilters không match phần tử | Kiểm tra identifier, field và modifiedCount |
| Gọi $push hai lần có hai item trùng | $push không chống trùng | Thiết kế idempotency/điều kiện nghiệp vụ |
| $addToSet vẫn thêm object cùng SKU | Hai embedded document không giống toàn bộ | Không dùng nó như unique-by-sku |
| Xóa một item nhưng mất mọi item cùng SKU | $pull loại tất cả phần tử khớp | Định nghĩa dữ liệu và điều kiện chính xác |
| $unset không làm array ngắn đi | Unset một vị trí khác $pull | Dùng $pull để xóa phần tử |
| Quantity thành 0 hoặc âm | Không có filter kiểm tra giá trị tối thiểu | Dùng $elemMatch và update có điều kiện |
| updateFirst matched=1, modified=0 | Update không đổi dữ liệu hoặc arrayFilters không match | Phân biệt matchedCount và modifiedCount |
| Lỗi stale khi save | @Version phát hiện write conflict | Tải lại và hòa giải thao tác |
| Đọc entity partial rồi save mất field | Ghi lại document từ projection không đầy đủ | Dùng DTO/projection đọc và update field có đích |
| Reactive tăng quantity hai lần | Subscribe/retry lệnh $inc hai lần | Bảo vệ idempotency, không subscribe thủ công lặp |
| Thao tác chậm trên array lớn | Document to, index maintenance, contention | Đo metrics, cân nhắc tách collection |

Khi điều tra, thực hiện theo thứ tự:

1. Xác nhận document đúng _id, status và schema mảng items.
2. Xác định mong muốn **thay cả mảng** hay **sửa một phần tử**.
3. Kiểm tra Query có chọn đúng document và đúng item không.
4. Kiểm tra đường dẫn update dùng **$**, **$[]** hay **$[identifier]**.
5. Nếu có arrayFilters, đối chiếu identifier với đường dẫn.
6. Đọc matchedCount và modifiedCount, không tự đồng nhất hai giá trị.
7. Nếu có request song song, kiểm tra optimistic locking, retry và idempotency.
8. Chạy lại với fixture MongoDB test; chỉ sau đó mới xem index/explain và contention.

## 21. Bài tập thực hành

### Bài tập 1: chọn đúng thao tác

API yêu cầu **đổi toàn bộ danh sách items** thành một danh sách được người dùng xác nhận. Nên dùng $set items hay $inc quantity?

**Gợi ý đáp án:** $set items hoặc chiến lược replace có version check, vì nghiệp vụ yêu cầu thay danh sách trọn vẹn. Kiểm tra input, tình trạng Order và xử lý thay đổi đồng thời.

### Bài tập 2: tăng đúng một item

Order có items BOOK-001 quantity=2 và PEN-002 quantity=1. Viết update tăng BOOK-001 thêm một, giữ PEN không đổi.

~~~javascript
db.orders.updateOne(
  { _id: orderId, status: "DRAFT", "items.sku": "BOOK-001" },
  { $inc: { "items.$.quantity": 1 } }
);
~~~

**Giải thích:** positional $ xác định item khớp đầu tiên, $inc thay giá trị quantity trên server, không cần ghi lại array.

### Bài tập 3: so sánh $ với $[]

Một Order có ba item. Nếu dùng **$inc: { "items.$[].quantity": 1 }**, điều gì xảy ra?

**Đáp án:** quantity của **cả ba item** được tăng một, vì $[] nhắm tất cả phần tử. Nếu chỉ muốn một SKU, cần positional $ hoặc arrayFilters.

### Bài tập 4: arrayFilters

Viết lệnh cập nhật **tất cả item có sku=BOOK-001**, không chỉ phần tử đầu.

~~~javascript
db.orders.updateOne(
  { _id: orderId },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "BOOK-001" }] }
);
~~~

### Bài tập 5: $addToSet có unique theo SKU không?

Array chứa {sku:"BOOK-001",quantity:1}. Bạn dùng $addToSet thêm {sku:"BOOK-001",quantity:2}. MongoDB có tự nhận đây là cùng một SKU không?

**Đáp án:** Không. $addToSet so sánh phần tử theo giá trị embedded document, không phải khóa nghiệp vụ sku. Cần một cách bảo đảm unique SKU riêng.

### Bài tập 6: xóa một item

Muốn xóa mọi item mang SKU PEN-002, dùng $pop hay $pull?

**Đáp án:** dùng **$pull: {items:{sku:"PEN-002"}}**. $pop chỉ loại phần tử ở đầu/cuối mảng, không lọc theo SKU.

### Bài tập 7: lost update

Request A và B cùng đọc items ban đầu. A tăng BOOK, B tăng PEN, rồi cả hai dùng $set toàn array. Vì sao có thể mất thay đổi?

**Đáp án:** mỗi request ghi lại bản array được tạo từ snapshot cũ; ghi sau có thể thay bản của ghi trước. Dùng targeted update riêng hoặc optimistic locking với expectedVersion.

### Bài tập 8: quantity không được xuống 0

Làm sao chỉ giảm quantity khi item đúng SKU và quantity > 1?

**Gợi ý:** Query dùng **items.$elemMatch** chứa cả sku và quantity > 1, update **$inc: {"items.$.quantity":-1}**. Hai điều kiện cần nằm trên cùng phần tử array.

### Bài tập 9: matchedCount khác modifiedCount

Lệnh dùng arrayFilters theo SKU không có trong items, nhưng filter _id khớp Order. matchedCount=1, modifiedCount=0 có bất thường không?

**Đáp án:** Không. matchedCount nói document cha khớp, không chứng minh có phần tử array thỏa filter. Cần kiểm tra modifiedCount và định nghĩa hợp đồng báo lỗi theo nghiệp vụ.

### Bài tập 10: reactive retry

Một request tăng quantity bằng $inc, server đã áp dụng nhưng response bị timeout. Client retry cùng request. Vì sao có rủi ro?

**Đáp án:** $inc không idempotent; lần retry có thể làm quantity tăng thêm lần nữa. Cần thiết kế idempotency/deduplication, không coi retry là luôn an toàn.

## 22. Nguyên tắc cần ghi nhớ

1. **Thay cả array và sửa phần tử là hai ý định khác nhau.** $set items thay mọi phần tử; update theo đường dẫn nhắm đúng field con.
2. **repository.save trên entity đã đọc có thể ghi rộng**, không tự merge các item theo SKU.
3. **Positional $** sửa phần tử khớp đầu tiên, **$[]** sửa mọi phần tử, **$[identifier]** sửa những phần tử thỏa arrayFilters.
4. **$inc** phù hợp với thay đổi số lượng dạng cộng/trừ và giúp tránh lost update do tự tính số từ bản đọc cũ, nhưng không tự giới hạn nghiệp vụ.
5. **$push** thêm phần tử, **$addToSet** tránh phần tử giống hệt, **$pull** xóa mọi phần tử khớp, **$pop** xóa theo vị trí đầu/cuối.
6. **Một update trên một document là nguyên tử**, nhưng nhiều bước đọc → sửa → ghi vẫn cần bảo vệ concurrency.
7. **@Version hoặc expectedVersion** hữu ích cho thao tác thay array từ snapshot; không mặc định mọi query/update được bảo vệ giống repository.save.
8. **UpdateResult cần được kiểm tra**. matchedCount=1 không nhất thiết là một phần tử đã bị thay đổi.
9. **Nhiều document/collection cần chiến lược nhất quán riêng**, có thể gồm transaction và quy tắc cập nhật có điều kiện.
10. **Array lớn và index có chi phí**, nên chọn mô hình embedded/reference dựa trên kích thước, quyền sở hữu và mẫu truy cập.
11. **Reactive không làm $inc thành idempotent**; tránh block(), subscribe trùng và retry mù quáng.
12. **Kiểm thử MongoDB thật** để chứng minh đúng phần tử được sửa và các phần tử không liên quan được giữ nguyên.

Phân biệt chính xác **thay toàn bộ array** và **cập nhật từng phần tử** giúp ứng dụng **SPRING_DATA_MONGODB** diễn đạt đúng nghiệp vụ, giảm nguy cơ mất dữ liệu do cập nhật đồng thời và lựa chọn các thao tác MongoTemplate, repository hoặc reactive access an toàn, hiệu quả hơn.
