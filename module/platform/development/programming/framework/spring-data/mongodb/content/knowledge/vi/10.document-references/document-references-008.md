# Tham chiếu hỏng, xóa dữ liệu và chính sách toàn vẹn ứng dụng

> **Chương:** Tham chiếu tài liệu  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document, thao tác qua `MongoTemplate` hoặc repository và thiết kế truy vấn, transaction, kiểm thử, chẩn đoán dữ liệu.  
> **Mục tiêu:** Nhận diện tham chiếu hỏng (dangling/orphan reference), lựa chọn chính sách khi xóa document được tham chiếu, áp dụng chính sách ở tầng ứng dụng, phát hiện dữ liệu sai lệch và xử lý các trường hợp ghi đồng thời.

## 1. Vì sao tham chiếu giữa các document có thể bị hỏng?

MongoDB lưu dữ liệu theo **document**. Một document có thể nhúng toàn bộ dữ liệu liên quan (embedding), hoặc lưu một **giá trị tham chiếu** tới document độc lập trong collection khác.

Ví dụ, collection `customers` chứa khách hàng, còn `orders` chứa đơn hàng:

~~~javascript
// customers
{ _id: "c001", name: "An", status: "ACTIVE" }

// orders
{
  _id: "o001",
  customerId: "c001",
  totalVnd: 250000,
  state: "OPEN"
}
~~~

Trong trường hợp này, `orders.customerId` có ý nghĩa nghiệp vụ: “đơn hàng o001 thuộc về khách hàng c001”. Tuy nhiên MongoDB **không tự tạo ràng buộc khóa ngoại** giữa `customerId` và `customers._id`. Bạn vẫn có thể:

- Chèn một order trỏ tới `customerId: "c404"` mặc dù không có khách hàng `c404`.
- Xóa khách hàng `c001` mà không xóa/sửa các order đang trỏ tới họ.
- Đổi schema hay kiểu BSON của `customers._id` khiến việc tra cứu không còn khớp.
- Tạo hai luồng ghi đồng thời làm một phép kiểm tra tồn tại trở nên lỗi thời.

Khi một tham chiếu có giá trị nhưng không tìm được đối tượng đích theo hợp đồng dữ liệu, ta gọi đó là **tham chiếu hỏng** (*dangling reference*). Nếu document con vẫn tồn tại nhưng không còn document cha hợp lệ, nó cũng thường được gọi là **orphan** theo ngữ cảnh nghiệp vụ.

Một tham chiếu tùy chọn bị thiếu trường hoặc đặt `null` **không nhất thiết hỏng**. Nó chỉ hỏng khi quy tắc nghiệp vụ **bắt buộc** quan hệ đó phải trỏ đến đối tượng tồn tại.

### 1.1. Các trạng thái cần phân biệt

| Trạng thái order | Diễn giải | Cách xử lý phụ thuộc nghiệp vụ |
| --- | --- | --- |
| `customerId: "c001"`, customer c001 tồn tại | Tham chiếu hợp lệ | Có thể đọc thông tin khách hàng |
| `customerId: "c404"`, customer c404 không tồn tại | Tham chiếu hỏng | Báo lỗi, sửa liên kết, xử lý hàng đợi đối soát |
| Không có `customerId` | Tham chiếu thiếu | Hợp lệ nếu quan hệ tùy chọn; lỗi nếu bắt buộc |
| `customerId: null` | Có trường nhưng không có đích | Theo hợp đồng: “không gán” hoặc dữ liệu lỗi |
| `customerId` có BSON `ObjectId`, `_id` đích là BSON string | Sai kiểu khóa | Truy vấn có thể không khớp dù chuỗi hiển thị giống nhau |
| Customer có `deletedAt` nhưng vẫn tồn tại | Tham chiếu vật lý còn hợp lệ, đối tượng đã xóa logic | Quyết định có cho order hiển thị lịch sử hay không |

Điều cần thiết kế là **tính toàn vẹn theo nghiệp vụ**: một order đã thanh toán có thể cần giữ lịch sử khách hàng, trong khi quan hệ “thành viên thuộc nhóm” có thể phải bị gỡ ngay khi nhóm bị xóa.

## 2. Các cách lưu tham chiếu trong MongoDB và Spring Data

### 2.1. Manual reference: lưu ID của document đích

Đây là lựa chọn phổ biến và minh bạch:

~~~javascript
// Collection customers
{ _id: "c001", name: "An", status: "ACTIVE" }

// Collection orders
{ _id: "o001", customerId: "c001", totalVnd: 250000 }
~~~

Ứng dụng truy vấn `orders`, sau đó tra cứu `customers` bằng `customerId`. Có thể dùng một truy vấn `$lookup` để kết hợp dữ liệu khi phù hợp. MongoDB khuyến nghị manual references cho phần lớn trường hợp cần lưu quan hệ giữa các document độc lập.

Ưu điểm của manual reference: trường BSON đơn giản, dễ index, thuận tiện khi cần kiểm tra tham chiếu còn tồn tại hay không. Nhược điểm: phía ứng dụng tự quyết định khi nào tra cứu, xử lý kết quả rỗng và duy trì tính toàn vẹn.

### 2.2. `@DBRef`: BSON DBRef

Spring Data MongoDB hỗ trợ annotation `@DBRef`:

~~~java
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("orders_dbref_example")
public class OrderWithDbRef {
    @MongoId(FieldType.STRING)
    private String id;

    @DBRef
    private CustomerDocument customer;

    protected OrderWithDbRef() { }
}
~~~

DBRef sử dụng cấu trúc tham chiếu chứa collection, ID và tùy chọn database đích:

~~~javascript
{
  _id: "o001",
  customer: { $ref: "customers_ref_demo_008", $id: "c001" }
}
~~~

Khi Spring Data nạp `OrderWithDbRef`, framework có thể resolve `customer` sang entity đích, mặc định theo cách eager; `@DBRef(lazy = true)` yêu cầu lazy loading. Việc resolve cần thao tác đọc từ MongoDB và có thể tạo thêm round-trip.

**Lưu ý quan trọng:** Spring Data **không tự cascade save** các entity được `@DBRef` tham chiếu. Đừng suy rằng gọi `orderRepository.save(order)` sẽ tự lưu `customer`. Tương tự, không kỳ vọng việc xóa order hoặc customer tự cascade xóa các document liên quan: chính sách xóa phải được triển khai rõ ràng ở service.

### 2.3. `@DocumentReference`: tham chiếu do Spring Data quản lý

`@DocumentReference` cho phép lưu một ID đơn giản thay vì BSON DBRef, hoặc cấu hình `lookup` khác `_id`:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders_docref_example")
public class OrderWithDocumentReference {
    @MongoId(FieldType.STRING)
    private String id;

    @DocumentReference
    private CustomerDocument customer;

    protected OrderWithDocumentReference() { }
}
~~~

Với lookup mặc định dựa vào `_id`, BSON của order có thể lưu trường `customer` như một chuỗi ID:

~~~javascript
{ _id: "o001", customer: "c001" }
~~~

Spring Data ánh xạ giá trị `"c001"` tới document trong collection của `CustomerDocument`. Nếu cần lookup theo khóa khác `_id` (ví dụ `code`), có thể cấu hình `lookup`, đồng thời bảo đảm **giá trị được ghi vào trường tham chiếu và quy tắc đọc khớp nhau**. Không mặc định mọi đối tượng tùy biến sẽ được ghi đúng chỉ nhờ khai báo một chuỗi truy vấn; một số trường hợp yêu cầu converter hoặc cấu hình bổ sung.

`@DocumentReference` không phải khóa ngoại của MongoDB và cũng **không tự cascade save**. Với reactive access, cần kiểm tra giới hạn hỗ trợ cụ thể: tài liệu Spring Data MongoDB hiện ghi rõ **không hỗ trợ đọc document references qua hạ tầng reactive**; lựa chọn chắc chắn khi dùng reactive là lưu ID rồi truy vấn đích tường minh bằng `ReactiveMongoTemplate` hoặc repository reactive.

### 2.4. Chọn kiểu tham chiếu phù hợp

| Cách tổ chức | Trường lưu trong BSON | Hợp khi | Chú ý |
| --- | --- | --- | --- |
| Embed document con | Dữ liệu con nằm trong document cha | Dữ liệu luôn được đọc/sửa cùng cha, kích thước hợp lý | Cân nhắc giới hạn kích thước document và cập nhật dữ liệu lặp |
| Manual reference | `customerId: "c001"` | Cần kiểm soát lookup, kiểm tra tồn tại, xử lý xóa | Ứng dụng tự quản lý liên kết |
| `@DocumentReference` | Thường là ID đơn giản, có lookup tùy chỉnh | Muốn mapping reference trong Spring Data imperative | Resolution, cache/latency, không cascade |
| `@DBRef` | `{ $ref, $id, $db? }` | Phải tương thích dữ liệu DBRef có sẵn hoặc cần định dạng đó | Spring Data resolve qua driver; không phải lựa chọn mặc định cho đa số hệ thống mới |

Quy tắc thực hành: nếu chỉ cần một khóa liên kết và xử lý nghiệp vụ cụ thể khi xóa, **manual reference thường đơn giản hơn**. Nếu luôn đọc dữ liệu con cùng cha và một document có thể chứa trọn mối quan hệ, cân nhắc embed để giảm số thao tác liên collection.

## 3. Bộ dữ liệu để quan sát tham chiếu hỏng

Dùng `mongosh` trên database thực hành. Các ví dụ sau chỉ dành cho collection riêng của bài học:

~~~javascript
use spring_data_mongodb_lab

const customers = db.customers_ref_demo_008;
const orders = db.orders_ref_demo_008;

customers.insertMany([
  { _id: "c001", name: "An", status: "ACTIVE" },
  { _id: "c002", name: "Bình", status: "ACTIVE" },
  { _id: "c003", name: "Chi", status: "INACTIVE" }
]);

orders.insertMany([
  { _id: "o001", customerId: "c001", totalVnd: 250000, state: "OPEN" },
  { _id: "o002", customerId: "c404", totalVnd: 150000, state: "OPEN" },
  { _id: "o003", customerId: "c002", totalVnd: 800000, state: "PAID" },
  { _id: "o004", customerId: null, totalVnd: 90000, state: "DRAFT" },
  { _id: "o005", totalVnd: 50000, state: "DRAFT" },
  { _id: "o006", customerId: "c001", totalVnd: 175000, state: "PAID" }
]);

// Tăng hiệu quả khi tìm order theo customerId.
orders.createIndex({ customerId: 1 });
~~~

Không chạy lại đoạn insert trên cùng dữ liệu nếu chưa chuẩn bị collection thử nghiệm mới: các `_id` cố định sẽ bị lỗi trùng khóa. Các kết quả kỳ vọng bên dưới giả định dữ liệu gốc chưa bị thay đổi.

`o002` là tham chiếu hỏng rõ ràng: trỏ tới `c404` không tồn tại. `o004` và `o005` thể hiện trường null/missing; với business rule “order DRAFT được phép chưa có khách hàng”, chúng **không phải tham chiếu hỏng**. `c003` là khách hàng không có order nào, nhưng không có nghĩa dữ liệu của họ bị lỗi.

### 3.1. Truy vấn trực tiếp hai bước

~~~javascript
const order = orders.findOne({ _id: "o002" });
const customer = customers.findOne({ _id: order.customerId });

printjson(order);     // Có customerId: "c404".
printjson(customer);  // null, vì không có c404.
~~~

Khi viết code, kết quả `customer == null` phải được xử lý như một tình huống nghiệp vụ, không được mặc nhiên dereference để đọc `customer.name`. Cũng phải xác định trường `customerId` có null/missing là hợp lệ hay không trước khi kết luận “mọi kết quả null đều là lỗi”.

## 4. Phát hiện tham chiếu hỏng bằng `$lookup`

`$lookup` có thể kết hợp dữ liệu trong hai collection để kiểm tra các liên kết. Trong ví dụ này, hai collection nằm cùng database và khóa `customerId`/`_id` đều là BSON string.

### 4.1. Tìm order có customerId nhưng không có khách hàng tương ứng

~~~javascript
orders.aggregate([
  // Chỉ kiểm tra order thực sự mang một ID dạng string.
  {
    $match: { customerId: { $type: "string" } }
  },
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "customerId",
      foreignField: "_id",
      as: "matchedCustomers"
    }
  },
  {
    $match: {
      matchedCustomers: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      state: 1,
      totalVnd: 1
    }
  }
]);
// Với dữ liệu gốc: chỉ o002 có customerId "c404".
~~~

Tại sao cần `$match` đầu tiên? Khi `localField` hoặc `foreignField` bị thiếu, `$lookup` có ngữ nghĩa so khớp liên quan tới `null`. Chặn ở bước đầu giúp tách **tham chiếu có ID nhưng không resolve được** khỏi **quan hệ tùy chọn đang trống**.

`matchedCustomers: { $size: 0 }` áp dụng cho array kết quả `$lookup`. Vì `customers._id` là duy nhất, liên kết hợp lệ sẽ cho một document đích; liên kết hỏng sẽ cho mảng rỗng.

### 4.2. Phân loại cả missing, null, dangling và hợp lệ

Để làm báo cáo chất lượng dữ liệu, có thể phân loại:

~~~javascript
orders.aggregate([
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "customerId",
      foreignField: "_id",
      as: "matches"
    }
  },
  {
    $project: {
      _id: 1,
      customerId: 1,
      referenceState: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$customerId" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: ["$customerId", null] },
              then: "NULL"
            },
            {
              case: { $eq: [{ $size: "$matches" }, 0] },
              then: "DANGLING"
            }
          ],
          default: "RESOLVED"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kỳ vọng: `o001/o003/o006 → RESOLVED`, `o002 → DANGLING`, `o004 → NULL`, `o005 → MISSING`.

**Giới hạn:** đây là ảnh chụp trạng thái tại thời điểm truy vấn. Trong lúc báo cáo chạy, writer khác có thể thêm hoặc xóa khách hàng. Kết quả kiểm tra không tự tạo ràng buộc toàn vẹn cho các thao tác ghi sau đó.

### 4.3. Tham chiếu trong mảng

Nếu một document chứa `memberIds: ["c001", "c404"]`, không thể dùng `matchedCustomers.length === memberIds.length` trong mọi trường hợp, vì ID trùng trong mảng có thể làm sai phép đếm.

Một hướng xử lý là lấy các ID đích đã tồn tại rồi so sánh tập khóa:

~~~javascript
// Chỉ minh họa một biến thể dữ liệu thử nghiệm.
db.groups_ref_demo_008.insertOne({
  _id: "g001",
  memberIds: ["c001", "c404"]
});

db.groups_ref_demo_008.aggregate([
  {
    $lookup: {
      from: "customers_ref_demo_008",
      localField: "memberIds",
      foreignField: "_id",
      as: "membersFound"
    }
  },
  {
    $project: {
      memberIds: 1,
      missingIds: {
        $setDifference: [
          "$memberIds",
          {
            $map: {
              input: "$membersFound",
              as: "member",
              in: "$$member._id"
            }
          }
        ]
      }
    }
  }
]);
// g001 có missingIds: ["c404"].
~~~

Ví dụ giả định `memberIds` là mảng luôn chứa string, không có null; nếu dữ liệu đầu vào không đồng nhất, hãy chuẩn hóa hoặc kiểm tra kiểu trước khi tính `$setDifference`. Đừng mặc định các liên kết trong mảng đều cần cascade delete khi document đích bị xóa.

### 4.4. Hiệu năng của công việc đối soát

- Tạo index trên trường truy vấn thường xuyên, ví dụ `orders.customerId`. `customers._id` đã có unique index mặc định.
- Với collection rất lớn, quét `$lookup` toàn bộ thường tốn chi phí; cân nhắc phân lô theo `_id`, giới hạn khoảng thời gian hoặc dùng event/outbox để phát hiện sớm.
- Phân biệt **dữ liệu thực sự hỏng** với liên kết đang được cập nhật bởi giao dịch hoặc tiến trình đồng bộ; đặt quy tắc độ trễ/chờ phù hợp.
- Không đưa một truy vấn đối soát nặng vào đường xử lý của mỗi HTTP request khi có thể dùng truy vấn theo ID với index.

## 5. Chính sách khi xóa document đang được tham chiếu

Trước khi triển khai `deleteById()` hoặc `MongoTemplate.remove()` cho entity cha, cần xác định chính sách cho từng loại quan hệ.

| Chính sách | Khi xóa customer còn order | Dùng khi | Rủi ro cần xử lý |
| --- | --- | --- | --- |
| **RESTRICT / BLOCK** | Từ chối xóa nếu còn order tham chiếu | Order bắt buộc có customer hợp lệ | Race giữa kiểm tra và xóa |
| **CASCADE** | Xóa các order liên quan trước/cùng lúc với customer | Document con không có giá trị độc lập | Mất lịch sử, thao tác nhiều document có thể dở dang |
| **SET NULL / DETACH** | Bỏ `customerId` hoặc đặt null cho các order, sau đó xóa customer | Quan hệ tùy chọn | Cần schema và UI hiểu trạng thái không gán |
| **SOFT DELETE / TOMBSTONE** | Giữ document customer, đánh dấu đã xóa | Cần audit, đơn hàng lịch sử, khả năng khôi phục | Mọi truy vấn nghiệp vụ phải lọc trạng thái phù hợp |
| **RETAIN SNAPSHOT** | Giữ thông tin khách hàng cần cho lịch sử trong order và cho phép xóa bản gốc theo chính sách | Hóa đơn, chứng từ, lịch sử thương mại | Thông tin snapshot phải được quản lý về quyền riêng tư, retention |

Đây là **chính sách ở tầng ứng dụng**, không phải các tùy chọn cascade tự động của MongoDB. Spring Data MongoDB không mô phỏng đầy đủ cơ chế `ON DELETE CASCADE`/`RESTRICT` của cơ sở dữ liệu quan hệ cho các tham chiếu document.

### 5.1. RESTRICT: ngăn xóa khi còn tham chiếu

Ở `mongosh`, kiểm tra:

~~~javascript
const customerId = "c001";

const linkedOrders = orders.countDocuments({ customerId });
print(linkedOrders); // 2 với dữ liệu gốc.

if (linkedOrders === 0) {
  customers.deleteOne({ _id: customerId });
} else {
  print("RESTRICT: khách hàng còn order, từ chối xóa");
}
~~~

Vì `c001` đang có `o001` và `o006`, phép xóa bị chặn trong ví dụ trên.

**Cảnh báo concurrency:** đoạn kiểm tra rồi xóa là **hai thao tác riêng**. Một writer khác có thể chèn order mới ngay sau `countDocuments` nhưng trước `deleteOne`. Do đó đây là ví dụ minh họa chính sách, chưa đủ bảo đảm RESTRICT tuyệt đối khi có nhiều writer.

Nếu chỉ có một service ghi dữ liệu và nghiệp vụ chấp nhận mức nhất quán này, bạn có thể cân nhắc kiểm tra đơn giản kèm kiểm tra định kỳ. Với ràng buộc nghiêm ngặt khi có ghi đồng thời, cần giao thức phối hợp giữa **mọi writer** và transaction như mục 8.

### 5.2. CASCADE: xóa document phụ thuộc

~~~javascript
const customerId = "c003";

// Trên dữ liệu gốc, c003 không có order nên không có gì để xóa.
const removedChildren = orders.deleteMany({ customerId });
const removedParent = customers.deleteOne({ _id: customerId });

printjson({
  deletedOrders: removedChildren.deletedCount,
  deletedCustomers: removedParent.deletedCount
});
~~~

Nếu dùng customer có order, hai thao tác trên có thể xóa dữ liệu lịch sử. Trong một triển khai thực tế, nếu cần tính nguyên tử xuyên hai collection, hãy dùng MongoDB transaction được cấu hình đúng. Với lượng document con quá lớn, giao dịch nhiều document có thể tốn tài nguyên và không phù hợp; hãy dùng quy trình bất đồng bộ có trạng thái, retry và kiểm soát hoàn tất.

**Không dùng CASCADE mặc định cho hóa đơn/đơn hàng đã thanh toán** chỉ vì chúng có `customerId`. Nghiệp vụ và quy định lưu trữ quyết định dữ liệu nào cần giữ.

### 5.3. SET NULL / DETACH: gỡ liên kết

~~~javascript
const customerId = "c002";

// Gỡ liên kết của tất cả order trỏ tới c002.
orders.updateMany(
  { customerId },
  { $unset: { customerId: "" } }
);

// Sau đó mới xóa customer nếu nghiệp vụ cho phép.
customers.deleteOne({ _id: customerId });
~~~

`$unset` làm trường biến mất. Nếu hợp đồng dữ liệu muốn trường vẫn hiện diện với giá trị null, dùng `$set: { customerId: null }`. Cần cập nhật cả API, validation, truy vấn và báo cáo để chấp nhận order không có customer. Thực hiện hai lệnh riêng có thể dẫn đến trạng thái dở dang nếu tiến trình dừng giữa chừng.

### 5.4. SOFT DELETE: giữ tombstone

~~~javascript
customers.updateOne(
  { _id: "c001", status: "ACTIVE" },
  {
    $set: {
      status: "DELETED",
      deletedAt: new Date()
    }
  }
);
~~~

Order vẫn tra cứu được document `c001`, nhưng mọi luồng nghiệp vụ phải định nghĩa xem có được tạo order mới cho customer đã xóa hay không. Nếu không, thao tác tạo order phải kiểm tra `status: "ACTIVE"` bằng một cơ chế chịu được concurrency.

Tombstone không đồng nghĩa với ẩn danh dữ liệu. Nếu chính sách bảo vệ dữ liệu yêu cầu loại bỏ thông tin cá nhân, cần thiết kế việc ẩn/khử định danh và retention phù hợp. Không nên giữ mọi thuộc tính mãi chỉ vì cần bảo toàn tham chiếu.

### 5.5. Retain snapshot: ghi dữ liệu lịch sử ở order

~~~javascript
// Ví dụ dữ liệu lịch sử được chụp tại thời điểm đặt hàng:
{
  _id: "o100",
  customerId: "c001",
  customerSnapshot: {
    displayNameAtPurchase: "An"
  },
  totalVnd: 250000,
  state: "PAID"
}
~~~

Nếu khách hàng đổi tên hoặc bị xóa sau đó, hóa đơn vẫn có tên đã được dùng trong giao dịch. Nên giữ **chỉ dữ liệu thực sự cần cho lịch sử**, với quy tắc quyền truy cập và thời hạn lưu trữ. Snapshot là thiết kế mô hình hóa dữ liệu, không tự bảo đảm consistency giữa các collection tại lúc tạo.

## 6. Cài đặt chính sách bằng Spring Data MongoDB

Ví dụ dưới đây dùng manual reference để các điều kiện và thao tác xóa được nhìn thấy rõ trong code. Dùng ID chuỗi tường minh tránh lỗi Spring Data tự chuyển `String` giống ObjectId.

### 6.1. Hai entity đơn giản

~~~java
// CustomerDocument.java
package com.example.references;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("customers_ref_demo_008")
public class CustomerDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    private String status;

    protected CustomerDocument() { }

    public CustomerDocument(String id, String name, String status) {
        this.id = id;
        this.name = name;
        this.status = status;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public String getStatus() { return status; }
}
~~~

~~~java
// OrderDocument.java
package com.example.references;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders_ref_demo_008")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String customerId;
    private long totalVnd;
    private String state;

    protected OrderDocument() { }

    public OrderDocument(
            String id, String customerId, long totalVnd, String state) {
        this.id = id;
        this.customerId = customerId;
        this.totalVnd = totalVnd;
        this.state = state;
    }

    public String getId() { return id; }
    public String getCustomerId() { return customerId; }
    public long getTotalVnd() { return totalVnd; }
    public String getState() { return state; }
}
~~~

Ở đây `@MongoId(FieldType.STRING)` áp dụng chính sách BSON string cho `_id` của cả hai collection. Thực tế có thể dùng `ObjectId` cho `_id`, nhưng lúc đó trường tham chiếu và các truy vấn phải sử dụng đúng kiểu BSON. Một chuỗi 24 ký tự hex và `ObjectId` có cùng biểu diễn **không phải** hai giá trị tương đương trong MongoDB.

### 6.2. Repository truy cập theo khóa

~~~java
package com.example.references;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<CustomerDocument, String> {
}

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    boolean existsByCustomerId(String customerId);

    long countByCustomerId(String customerId);

    List<OrderDocument> findByCustomerId(String customerId);
}
~~~

`existsByCustomerId()` và `countByCustomerId()` giúp triển khai kiểm tra RESTRICT; tuy nhiên bản thân chúng **không khóa** document hay chặn transaction khác tạo order mới. Trên hệ thống nhiều writer, cần cơ chế phối hợp như phần concurrency.

### 6.3. Service trả kết quả rõ ràng khi tham chiếu hỏng

~~~java
package com.example.references;

import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {
    private final OrderRepository orders;
    private final CustomerRepository customers;

    public OrderLookupService(
            OrderRepository orders, CustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public CustomerDocument customerForOrder(String orderId) {
        OrderDocument order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        String customerId = order.getCustomerId();
        if (customerId == null) {
            throw new IllegalStateException(
                "Order has no customer reference: " + orderId
            );
        }

        return customers.findById(customerId)
            .orElseThrow(() -> new IllegalStateException(
                "Broken customer reference in order: " + orderId
            ));
    }
}
~~~

Đoạn code phân biệt: **order không tồn tại**, **order không có tham chiếu**, và **order trỏ tới customer không tồn tại**. Trong API thực tế, hãy chuyển thành error response có mã thích hợp và **không lộ thông tin nhạy cảm** trong thông điệp trả cho người dùng.

Với order DRAFT được phép không có customer, service nên trả về DTO mô tả trạng thái hoặc `Optional<CustomerDocument>` thay vì ném lỗi ở nhánh null. Quyết định này xuất phát từ hợp đồng nghiệp vụ, không phải từ annotation repository.

### 6.4. RESTRICT đơn giản qua `MongoTemplate`

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class RestrictedCustomerDeletionService {
    private final MongoTemplate template;

    public RestrictedCustomerDeletionService(MongoTemplate template) {
        this.template = template;
    }

    public void deleteCustomerIfUnused(String customerId) {
        boolean hasOrders = template.exists(
            Query.query(Criteria.where("customerId").is(customerId)),
            OrderDocument.class
        );

        if (hasOrders) {
            throw new IllegalStateException(
                "Customer has orders; deletion is restricted"
            );
        }

        DeleteResult result = template.remove(
            Query.query(Criteria.where("id").is(customerId)),
            CustomerDocument.class
        );

        if (result.getDeletedCount() != 1) {
            throw new IllegalArgumentException("Customer not found");
        }
    }
}
~~~

Đoạn này thể hiện quy tắc RESTRICT cho một luồng xử lý bình thường, **chưa an toàn trước race** giữa kiểm tra và xóa khi nhiều writer hoạt động. Phần tiếp theo giải thích giới hạn và cách tăng tính nhất quán.

## 7. Xóa một document có nguyên tử không đồng nghĩa xóa liên collection nguyên tử

MongoDB bảo đảm tính nguyên tử của **một thao tác ghi trên một document**. Tuy nhiên, hai thao tác:

~~~javascript
orders.deleteMany({ customerId: "c001" });
customers.deleteOne({ _id: "c001" });
~~~

không tự trở thành một hành động nguyên tử xuyên collection. Nếu lệnh đầu chạy thành công nhưng lệnh thứ hai lỗi, dữ liệu còn lại khác với trạng thái kỳ vọng; trường hợp ngược lại còn có thể tạo orphan.

Khi nghiệp vụ yêu cầu cập nhật nhiều document trong cùng MongoDB deployment theo cách nguyên tử, có thể dùng **multi-document transaction**. MongoDB transactions cần môi trường hỗ trợ, như replica set hoặc sharded cluster phù hợp, và có chi phí cao hơn một thao tác một document.

### 7.1. Cấu hình transaction manager

~~~java
package com.example.references;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration(proxyBeanMethods = false)
public class MongoReferenceTransactionConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

`MongoTemplate` phải sử dụng database factory tương ứng để tham gia cùng transaction. Đảm bảo các collection cần thiết đã tồn tại trước khi chạy ví dụ transaction, và thiết lập replica set/transaction capability phù hợp.

### 7.2. Transaction cho thao tác detach rồi delete

~~~java
package com.example.references;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerDetachService {
    private final MongoTemplate template;

    public CustomerDetachService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void deleteAndDetach(String customerId) {
        Query customer = Query.query(
            Criteria.where("id").is(customerId)
        );

        if (!template.exists(customer, CustomerDocument.class)) {
            throw new IllegalArgumentException("Customer not found");
        }

        template.updateMulti(
            Query.query(Criteria.where("customerId").is(customerId)),
            new Update().unset("customerId"),
            OrderDocument.class
        );

        var removed = template.remove(customer, CustomerDocument.class);
        if (removed.getDeletedCount() != 1) {
            throw new IllegalStateException("Customer was not deleted");
        }
    }
}
~~~

Nếu có lỗi giữa các thao tác, transaction có thể rollback các thay đổi. Tuy nhiên **transaction không tự cung cấp khóa ngoại** và không giải quyết mọi race với một writer tạo order mới bên ngoài giao thức phối hợp; giao dịch đơn thuần kiểm tra `exists` hoặc `count` vẫn có thể bỏ sót thao tác ghi đồng thời.

Việc gọi method `@Transactional` phải đi qua Spring proxy; gọi nội bộ từ method cùng class có thể không kích hoạt transaction theo cấu hình proxy mặc định. Nếu là ứng dụng reactive, dùng `ReactiveMongoTransactionManager`/`TransactionalOperator` và xử lý `Mono`/`Flux`; không bọc các thao tác reactive vào một method đồng bộ rồi kỳ vọng chúng tự chạy trong giao dịch.

## 8. Race condition: kiểm tra tồn tại trước khi ghi là chưa đủ

Xét hai request chạy song song:

~~~mermaid
sequenceDiagram
    participant A as Request A: xóa customer
    participant DB as MongoDB
    participant B as Request B: tạo order
    A->>DB: count orders(c001) = 0
    B->>DB: find customer(c001) => tồn tại
    A->>DB: delete customer(c001)
    B->>DB: insert order(customerId=c001)
    Note over DB: Order mới trỏ tới customer đã bị xóa
~~~

Mỗi request có thể đã “kiểm tra đúng” tại thời điểm đọc, nhưng kết quả cuối cùng vẫn là tham chiếu hỏng.

### 8.1. Giao thức phối hợp giữa writer và deleter

Nếu ứng dụng cần RESTRICT mạnh, **tất cả luồng tạo order và xóa customer** phải tuân cùng quy tắc. Một cách thiết kế dùng MongoDB transactions là khiến hai thao tác cùng **ghi vào document customer** để tạo điểm xung đột khi chúng chạy đồng thời:

1. Customer có `status: "ACTIVE"` và một trường số `referenceEpoch` dùng làm phiên bản hoặc dấu phối hợp.
2. Khi tạo order, trong transaction, dùng `updateOne` có filter `{ _id: customerId, status: "ACTIVE" }` và `$inc: { referenceEpoch: 1 }` trên customer; chỉ tạo order nếu cập nhật thành công.
3. Khi xóa customer, trong transaction, chuyển `status` từ `ACTIVE` sang `DELETING` bằng thao tác có điều kiện trên **cùng document customer**; kiểm tra order đang tham chiếu rồi quyết định xóa/từ chối.
4. Nếu hai transaction cố sửa cùng document customer trong lúc giao nhau, một transaction có thể gặp write conflict và cần retry toàn bộ nghiệp vụ theo chính sách.

Đây là **giao thức ứng dụng**, không phải tính năng foreign key của MongoDB. Nó tạo thêm write contention trên customer nếu có nhiều order cùng khách hàng. Chỉ áp dụng khi yêu cầu toàn vẹn justify chi phí đó; có thể thay bằng mô hình dữ liệu khác hoặc state machine phù hợp.

### 8.2. Pseudocode của hai nhánh có phối hợp

~~~text
createOrder(customerId, order):
  transaction:
    update customer where id=customerId and status=ACTIVE:
      inc referenceEpoch by 1
    if matchedCount != 1: reject
    insert order referencing customerId
  commit (retry transaction if transient conflict)

deleteCustomerRestricted(customerId):
  transaction:
    update customer where id=customerId and status=ACTIVE:
      set status=DELETING
    if matchedCount != 1: reject
    if countOrders(customerId) > 0: reject and rollback
    delete customer where id=customerId
  commit (retry transaction if transient conflict)
~~~

Mấu chốt là **cả hai nhánh phải tham gia giao thức**. Một import job chèn order trực tiếp, bỏ qua cập nhật `referenceEpoch`, vẫn có thể tạo orphan. Khi có nhiều service cùng ghi collection, phải chuẩn hóa hợp đồng dữ liệu và viết kiểm thử concurrency cho các luồng quan trọng.

**Đừng triển khai retry vô hạn.** MongoDB có thể gắn nhãn lỗi transaction tạm thời; retry cần có giới hạn, backoff thích hợp, hành vi idempotent và khả năng quan sát các lần thất bại.

### 8.3. Khi nên dùng trạng thái `DELETING`

Đối với việc xóa hàng nghìn document con, giao dịch duy nhất có thể quá lớn hoặc quá chậm. Một phương án khác:

~~~text
ACTIVE -> DELETING -> DELETED
                  \-> DELETE_FAILED (chờ xử lý lại)
~~~

- Đánh dấu parent `DELETING` bằng thao tác có điều kiện.
- Tất cả writer mới phải **từ chối tạo liên kết** với parent không còn `ACTIVE`.
- Worker xóa/gỡ liên kết từng lô, lưu tiến độ và retry idempotent.
- Khi đã kiểm tra xong, chuyển `DELETED` hoặc xóa cứng theo chính sách retention.

Nếu writer khác chỉ đọc trạng thái mà không có bước phối hợp/ghi có điều kiện, vẫn có khoảng race. Cần thiết kế điểm đồng bộ rõ ràng; trạng thái `DELETING` là một phần của giao thức, không tự tạo bảo đảm.

## 9. Ứng dụng cần làm gì khi không resolve được tham chiếu?

Không có một hành vi luôn đúng cho mọi domain. Ví dụ:

| Ngữ cảnh | Khi reference không resolve được | Gợi ý |
| --- | --- | --- |
| Đơn hàng đã thanh toán | Vẫn cần tra cứu lịch sử | Hiển thị snapshot cần thiết; ghi cảnh báo vận hành |
| Đơn hàng đang tạo | Có thể không thể xác nhận khách hàng | Từ chối xác nhận và yêu cầu gán customer hợp lệ |
| Danh sách thành viên nhóm | Thành viên không tồn tại | Có thể bỏ khỏi danh sách theo policy, lưu audit |
| Phân quyền tài nguyên | Reference quyền sở hữu bị hỏng | Từ chối truy cập theo nguyên tắc an toàn |
| Báo cáo thống kê | Không nên âm thầm bỏ bản ghi | Phân loại `UNRESOLVED` và số lượng rõ ràng |

Với `@DBRef`/`@DocumentReference`, đừng dựa vào một giả định rằng lazy resolver luôn trả null theo cùng cách giữa mọi kiểu dữ liệu/phiên bản. Tùy mapping, collection và cơ chế proxy, việc truy cập có thể cần query và phát sinh lỗi. **Thiết kế kết quả nghiệp vụ** tường minh: resolved, missing optional, broken, transient failure.

Một service có thể trả DTO:

~~~java
public record OrderCustomerView(
    String orderId,
    String customerId,
    String customerName,
    String referenceState
) {}
~~~

Giá trị `referenceState` nên có quy ước cố định như `RESOLVED`, `OPTIONAL_MISSING`, `BROKEN` để API và log có thể phân tích được. Trong hệ thống lớn, cân nhắc enum thay vì String để tránh sai chính tả.

## 10. Dọn tham chiếu hỏng và sửa dữ liệu đã tồn tại

Phát hiện orphan chưa đồng nghĩa được phép tự xóa hoặc gán lại dữ liệu. Trước khi chạy job sửa:

1. Xác nhận quy tắc nghiệp vụ: parent đã thực sự bị xóa hay lỗi đồng bộ tạm thời?
2. Phân biệt `customerId` thiếu/null với ID có giá trị nhưng không resolve.
3. Xác định kiểu BSON của `customerId` và `customers._id` có giống nhau hay không.
4. Kiểm tra nhật ký, event hoặc bản ghi lịch sử xem parent có thể khôi phục hay không.
5. Chọn hành động sửa: khôi phục parent, chuyển sang tombstone, gỡ reference, gắn lại đúng ID, hoặc xóa child theo chính sách đã duyệt.
6. Ghi lại số lượng, danh sách ID, lý do sửa và khả năng retry/rollback.

### 10.1. Xác minh bằng query trước khi sửa

~~~javascript
// Xem chính xác các order tham chiếu c404.
orders.find(
  { customerId: "c404" },
  { _id: 1, customerId: 1, state: 1, totalVnd: 1 }
);

// Xem parent có tồn tại không.
customers.findOne({ _id: "c404" });
~~~

Không thực hiện `deleteMany({ customerId: { $exists: false } })` với giả định mọi order thiếu customer đều là orphan. Điều đó có thể xóa nhầm order DRAFT hợp lệ.

### 10.2. Ví dụ sửa theo chính sách DETACH

Giả sử đã được xác nhận `o002` có thể trở thành order không gán customer, bạn có thể sửa riêng document ấy:

~~~javascript
const result = orders.updateOne(
  { _id: "o002", customerId: "c404" },
  {
    $unset: { customerId: "" },
    $set: { referenceRepairReason: "MISSING_CUSTOMER" }
  }
);

printjson(result); // Kiểm tra matchedCount, modifiedCount.
~~~

Filter gồm cả `_id` và `customerId` giúp giảm nguy cơ ghi đè một liên kết vừa được người khác sửa. Nếu liên kết đã thay đổi giữa lúc rà soát và cập nhật, `matchedCount = 0` là tín hiệu phải kiểm tra lại, không nên ép sửa theo dữ liệu cũ.

Nếu mục tiêu là giữ lại lịch sử mà không còn parent, thay `$unset` bằng chính sách snapshot hoặc tombstone phù hợp. Không ghi một giá trị giả như `"UNKNOWN"` vào `customerId` nếu nó có thể bị ứng dụng nhầm là ID khách hàng thực.

### 10.3. Đối soát định kỳ và xử lý từng lô

Với dữ liệu lớn, nên dùng job riêng:

~~~text
Job đối soát:
  1. Quét order theo _id hoặc khoảng thời gian, từng batch có giới hạn.
  2. Lọc ID hiện diện và đúng kiểu dữ liệu.
  3. Đối chiếu tập ID khách hàng bằng truy vấn có index.
  4. Phân loại orphan thật / missing hợp lệ / tạm thời chưa đồng bộ.
  5. Ghi kết quả kiểm tra; đưa case cần quyết định vào queue.
  6. Sửa theo policy có điều kiện và idempotent.
  7. Tái kiểm tra và phát metric.
~~~

Không chạy unbounded `$lookup` hoặc lặp một query mạng cho từng order ở đường request khi volume lớn. Có thể dùng `$lookup`, batching hoặc một read model phục vụ đối soát; lựa chọn dựa trên index, latency và kích thước dữ liệu.

### 10.4. Monitoring và cảnh báo

Các chỉ số hữu ích:

- Số lượng `dangling references` theo collection và loại quan hệ.
- Thời gian từ lúc parent bị đánh dấu `DELETING` đến khi xử lý xong.
- Số lần thao tác RESTRICT bị từ chối, transaction conflict và retry.
- Số lượng sửa thất bại hoặc task ở hàng đợi lâu bất thường.
- Số document xóa/gỡ tham chiếu thực tế so với dự kiến.

Không ghi toàn bộ document chứa dữ liệu nhạy cảm vào log khi chỉ cần khóa và trạng thái. Khi log ID, cân nhắc chính sách bảo mật và truy vết của hệ thống.

## 11. Kiểm thử chính sách toàn vẹn

Unit test chỉ mock repository có thể kiểm tra nhánh “đã có child nên chặn xóa”, nhưng không phát hiện được sai kiểu BSON, behavior của `$lookup`, transaction rollback và race giữa hai writer. Với nghiệp vụ quan trọng, dùng **integration test** trên MongoDB có hỗ trợ transaction khi muốn kiểm thử transaction.

### 11.1. Các ca kiểm thử nên có

| Trường hợp | Kết quả mong muốn |
| --- | --- |
| Order tham chiếu customer hợp lệ | Resolve được đúng customer |
| Order tham chiếu customer không tồn tại | Trả trạng thái BROKEN/exception nghiệp vụ rõ |
| Order có `customerId: null` hoặc không có trường | Xử lý theo hợp đồng optional/required |
| ID ở hai collection khác BSON type | Không âm thầm coi là hợp lệ |
| RESTRICT khi còn order | Không xóa customer |
| RESTRICT khi không có order | Có thể xóa theo chính sách |
| DETACH trong transaction gặp lỗi | Các thay đổi liên collection rollback |
| CASCADE có nhiều order | Xóa đúng đối tượng, kiểm tra count và giới hạn |
| Hai writer tạo order và xóa customer đồng thời | Không được commit trạng thái orphan nếu chính sách đòi consistency mạnh |
| Job đối soát chạy nhiều lần | Không xóa/sửa thêm dữ liệu ngoài phạm vi |

### 11.2. Ví dụ kiểm thử hành vi RESTRICT đơn giản

Giả sử ứng dụng đã cấu hình MongoDB test và có `RestrictedCustomerDeletionService` ở mục 6.4:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ReferencePolicyTest {
    @Autowired CustomerRepository customers;
    @Autowired OrderRepository orders;
    @Autowired RestrictedCustomerDeletionService deletionService;

    @Test
    void restrictDeletionWhenOrdersExist() {
        // Fixture phải đặt trong database test riêng.
        orders.deleteById("fixture-o008");
        customers.deleteById("fixture-c008");

        try {
            customers.save(new CustomerDocument(
                "fixture-c008", "Khách hàng thử", "ACTIVE"
            ));
            orders.save(new OrderDocument(
                "fixture-o008", "fixture-c008", 100000, "OPEN"
            ));

            assertThatThrownBy(() ->
                deletionService.deleteCustomerIfUnused("fixture-c008")
            ).isInstanceOf(IllegalStateException.class);

            assertThat(customers.existsById("fixture-c008")).isTrue();
        } finally {
            orders.deleteById("fixture-o008");
            customers.deleteById("fixture-c008");
        }
    }
}
~~~

Đoạn test sử dụng service ở mục 6.4 và chỉ được chạy trên **database test biệt lập**: phần chuẩn bị/dọn fixture có xóa các ID thử nghiệm. Test xác nhận nhánh RESTRICT khi có order, **chưa** kiểm tra race. Test đồng thời cần điều khiển thời điểm của hai transaction/worker, dùng MongoDB topology tương ứng và xác nhận trạng thái cuối cùng.

Nếu ứng dụng dùng `ReactiveMongoRepository`, manual reference được lưu như một trường ID vẫn dùng được. Khi kiểm thử reactive, subscribe vào publisher bằng `StepVerifier`/chuỗi reactive; các phép ghi không tự thực thi chỉ vì đã tạo `Mono` hoặc `Flux`.

## 12. Tình huống thiết kế: đơn hàng và hồ sơ khách hàng

Giả sử hệ thống có yêu cầu:

- Đơn hàng đã thanh toán phải giữ lịch sử giao dịch.
- Khách hàng có thể yêu cầu ngừng tài khoản.
- Không được tạo đơn hàng mới cho khách hàng đã ngừng.
- Thông tin cá nhân phải được xử lý theo retention và quyền truy cập phù hợp.

Một phương án thiết kế:

~~~mermaid
flowchart TD
    A["Yêu cầu đóng tài khoản"] --> B["Đánh dấu customer=DELETING"]
    B --> C{"Còn order lịch sử?"}
    C -->|Có| D["Giữ dữ liệu cần thiết trong order snapshot"]
    C -->|Không| E["Có thể xóa theo policy"]
    D --> F["Ẩn/khử định danh parent theo retention"]
    E --> F
    F --> G["Kiểm tra references và audit"]
    G --> H["Hoàn tất trạng thái DELETED"]
~~~

Hệ thống chỉ nên cho phép tạo order khi customer `ACTIVE`. Việc chọn hard delete, tombstone, snapshot hoặc retention chi tiết cần xuất phát từ chính sách nghiệp vụ và pháp lý tương ứng, không phải từ sự tiện lợi của API `deleteById()`.

Với quan hệ khác như “thẻ theo dõi tài liệu” hay “session tạm thời”, CASCADE hoặc DETACH có thể phù hợp hơn. Vì vậy **chính sách toàn vẹn nên được định nghĩa cho từng quan hệ**, không có một quy tắc toàn cục cho mọi document reference.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `findById(customerId)` trả rỗng dù UI hiển thị ID giống nhau | BSON `ObjectId` khác BSON string; sai database/collection | Kiểm tra `$type` của hai trường ID, metadata `@Id`/`@MongoId` |
| Xóa customer xong order mất thông tin | Hard delete không có snapshot/tombstone hoặc policy xử lý | Rà soát RESTRICT/RETAIN SNAPSHOT/SOFT DELETE |
| Gọi `save(order)` không lưu customer mới | `@DBRef`/`@DocumentReference` không cascade save | Persist customer trước, kiểm tra ID thực tế |
| Cảnh báo/lỗi khi truy cập lazy reference | Resolver thực hiện I/O khi truy cập property; proxy, session hoặc server không sẵn sàng | Xem `@DBRef(lazy=true)`, chiến lược fetch và log resolver |
| `$lookup` báo nhiều orphan “giả” | Trường missing/null bị đưa vào phép join không kiểm soát | Lọc ID hiện diện/đúng kiểu, so sánh BSON raw |
| RESTRICT đôi khi vẫn tạo orphan | Race giữa kiểm tra count và insert order | Áp dụng giao thức phối hợp cho mọi writer; test concurrency |
| DETACH/CASCADE chỉ thực hiện nửa chừng | Các thao tác trên nhiều document không nằm trong transaction hoặc job không có retry | Dùng transaction phù hợp hoặc workflow trạng thái idempotent |
| Job đối soát sửa nhầm order DRAFT | Gộp null/missing và dangling thành một nhóm | Phân loại trạng thái và hợp đồng nghiệp vụ trước khi sửa |
| Xóa hàng loạt chậm | Quét orders thiếu index `customerId`, số child quá lớn | Tạo index theo query, chia lô, đo `explain` |
| Transaction được khai báo nhưng không rollback | Chưa có MongoTransactionManager, sai database factory, self-invocation hoặc topology chưa hỗ trợ | Soát cấu hình bean/proxy/session và integration test |

## 14. Bài thực hành

### Bài 1 — Tìm tham chiếu hỏng

Cho dữ liệu gốc ở mục 3. Hãy tìm order có `customerId` dạng string nhưng không có document khách hàng tương ứng.

**Đáp án:** dùng pipeline `$match` theo `$type: "string"`, `$lookup` vào `customers_ref_demo_008` rồi lọc `matchedCustomers: { $size: 0 }`. Kết quả kỳ vọng là **o002** với `customerId: "c404"`.

### Bài 2 — Chọn chính sách xóa

Ứng dụng cần giữ đơn hàng đã thanh toán và ngăn tạo đơn hàng mới cho customer bị đóng tài khoản. Có nên dùng CASCADE xóa mọi order khi xóa customer?

**Đáp án tham khảo:** Không. Cân nhắc RESTRICT, SOFT DELETE/TOMBSTONE kết hợp snapshot dữ liệu lịch sử cần thiết. Mọi thao tác tạo order phải từ chối customer không còn ACTIVE theo một giao thức xử lý concurrency phù hợp.

### Bài 3 — Phân biệt null và orphan

`o004` có `customerId: null` và `o005` không có `customerId`. Hai order này có phải orphan không?

**Đáp án:** Chưa thể kết luận nếu chưa biết hợp đồng dữ liệu. Nếu order DRAFT cho phép thiếu customer, cả hai hợp lệ. Nếu mọi order phải có customer, chúng là dữ liệu vi phạm ràng buộc required, nhưng khác bản chất với `o002` có ID trỏ đến một document không tồn tại.

### Bài 4 — Chỉ xóa khi không còn liên kết

Viết đoạn `mongosh` kiểm tra `orders.countDocuments({ customerId: "c003" })` rồi mới xóa `customers.deleteOne({ _id: "c003" })`.

**Đáp án tham khảo:**

~~~javascript
const id = "c003";
if (orders.countDocuments({ customerId: id }) !== 0) {
  throw new Error("Deletion restricted: referenced customer");
}
const result = customers.deleteOne({ _id: id });
printjson(result);
~~~

**Câu hỏi mở rộng:** Đoạn này còn lỗ hổng gì? **Đáp án:** giữa phép đếm và phép xóa, request khác có thể thêm order. Phải phối hợp các writer và có chiến lược transaction/khóa logic nếu yêu cầu nhất quán mạnh.

### Bài 5 — Sửa orphan có điều kiện

Đã xác định order `o002` được phép bỏ liên kết customer. Viết lệnh cập nhật không ghi đè nếu ID tham chiếu đã được sửa đồng thời.

**Đáp án:**

~~~javascript
orders.updateOne(
  { _id: "o002", customerId: "c404" },
  { $unset: { customerId: "" } }
);
~~~

Đọc `matchedCount` và `modifiedCount`. Nếu `matchedCount = 0`, cần tải lại order và xác minh, không nên cố ép cập nhật bằng một filter kém chính xác hơn.

## Tài liệu tham khảo

- [MongoDB Manual — Database References](https://www.mongodb.com/docs/manual/reference/database-references/): manual references, DBRefs và lựa chọn cách biểu diễn tham chiếu.
- [Spring Data MongoDB — Using DBRefs and Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DBRef`, `@DocumentReference`, lookup, lazy resolution và giới hạn cascading.
- [Spring Data MongoDB — Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager` và cơ chế transaction.
- [MongoDB Manual — `$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): phép join giữa collection trong aggregation.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): giới hạn và hành vi giao dịch nhiều document.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): khác biệt giữa thao tác nguyên tử trên một document và nhiều thao tác.
