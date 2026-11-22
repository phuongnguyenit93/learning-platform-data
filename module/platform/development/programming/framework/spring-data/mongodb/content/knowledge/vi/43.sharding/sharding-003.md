# Range, hashed key, chỉ mục và yêu cầu uniqueness

Trong **Spring Data MongoDB**, ứng dụng thường thao tác qua `MongoTemplate` hoặc repository, còn việc phân phối dữ liệu giữa các shard do **MongoDB sharded cluster** thực hiện. Chọn shard key không chỉ quyết định nơi lưu document mà còn ảnh hưởng trực tiếp đến khả năng định tuyến truy vấn, tốc độ ghi, cách thiết kế index và những ràng buộc `unique` mà hệ thống có thể đảm bảo.

Bài này thuộc chương **Sharding**, tập trung vào cách chọn giữa **range-based sharding** và **hashed sharding**, chuẩn bị chỉ mục phù hợp và bảo toàn quy tắc duy nhất khi số shard tăng lên.

## 1. Mục tiêu học tập

Sau khi hoàn thành bài, bạn có thể:

1. Phân biệt cơ chế phân phối của range và hashed shard key, kể cả khi nào xảy ra hotspot hoặc scatter-gather.
2. Chọn shard key dựa trên cardinality, phân bố ghi, truy vấn phổ biến và nhu cầu mở rộng.
3. Tạo chỉ mục hỗ trợ shard key trước khi shard collection đã có dữ liệu.
4. Phân biệt `unique index` trên một collection thông thường với tính duy nhất được bảo đảm **trên toàn sharded cluster**.
5. Kết hợp cấu hình MongoDB với entity `@Sharded`, `MongoTemplate` và Spring Data repository.
6. Kiểm tra lựa chọn bằng `sh.status()`, `getIndexes()` và `explain()`.

## 2. Shard key thực sự điều khiển điều gì?

Một sharded collection được chia thành những **khoảng giá trị shard key**; mỗi khoảng được quản lý bởi cluster và phân phối đến các shard. Router `mongos` dùng metadata phân vùng cùng điều kiện truy vấn để tìm shard có thể chứa dữ liệu.

Ví dụ, mỗi đơn hàng có dạng:

```javascript
{
  _id: ObjectId("66c000000000000000000001"),
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  createdAt: ISODate("2026-11-20T02:15:00Z"),
  totalAmount: 250000,
  status: "NEW"
}
```

Ta có thể chọn `tenantId`, `createdAt`, `_id` hoặc tổ hợp nhiều trường làm shard key. Không có lựa chọn tối ưu cho mọi workload. Để đánh giá đúng, cần tách ba câu hỏi:

- **Phân phối dữ liệu:** các giá trị key có đủ khác nhau để tạo nhiều vùng dữ liệu và cân bằng tải không?
- **Định tuyến:** truy vấn có cung cấp điều kiện trên shard key để `mongos` giới hạn các shard cần hỏi không?
- **Tính duy nhất:** hệ thống cần ngăn trùng giá trị theo từng tenant hay trên toàn bộ tập dữ liệu?

Shard key **không đồng nghĩa** với primary key, cũng không mặc nhiên là một unique index.

## 3. Range-based sharding và hashed sharding

### 3.1. Range-based: giữ thứ tự giá trị

Với shard key tăng dần `{ createdAt: 1 }`, MongoDB chia các khoảng liên tiếp của `createdAt`. Các giá trị gần nhau có xu hướng được đặt trong cùng một vùng dữ liệu; các vùng này có thể được chuyển giữa các shard.

```text
Giá trị createdAt tăng dần
|---- khoảng cũ ----|---- khoảng giữa ----|---- khoảng mới ---->
       chunk A              chunk B               chunk C
          |                    |                     |
        shard 1              shard 2               shard 3
```

Ưu điểm lớn là **truy vấn theo khoảng** trên shard key thường có thể nhắm đến tập shard hẹp hơn. Ví dụ, nếu shard key chứa tiền tố phù hợp, truy vấn theo `tenantId` và thời gian có thể tận dụng định tuyến và index.

Rủi ro xuất hiện khi shard key **tăng đơn điệu**, như timestamp hoặc sequence. Phần lớn bản ghi mới rơi vào khoảng giá trị cao nhất, khiến một chunk hoặc một shard đang giữ khoảng đó nhận phần lớn lượt ghi. Đây là kiểu **write hotspot**. Việc di chuyển chunk có thể giúp phân bổ dữ liệu theo thời gian nhưng không tự biến luồng ghi nối tiếp thành phân phối đều tức thời.

Một shard key như `{ tenantId: 1 }` cũng có thể bị lệch khi một tenant chiếm đa số traffic: tất cả document có cùng `tenantId` nằm trong cùng giá trị shard key, nên chỉ hash hay index thêm ở ứng dụng sẽ không chia tải cho tenant đó nếu shard key vẫn chỉ là `tenantId`.

### 3.2. Hashed: phân phối theo giá trị băm

Với shard key `{ eventId: "hashed" }`, MongoDB tính hash của giá trị `eventId`, rồi chia **khoảng giá trị hash** thành các chunk. Ứng dụng không tự tính hoặc lưu hash này.

```text
eventId liên tiếp: E001 E002 E003 E004 E005 E006
                       |    |    |    |    |
                    hash nội bộ MongoDB
                       |    |    |    |    |
vùng hash/chunk:       C3   C1   C4   C2   C1   C4
```

Các giá trị sát nhau về mặt số học hoặc thời gian có thể rơi vào những khoảng hash khác nhau. Vì thế hashed sharding thường phân phối tốt hơn các lượt ghi có ID tăng dần, nếu key có **cardinality cao**.

Đổi lại, truy vấn khoảng như `eventId >= "E100"` không còn tương ứng với một khoảng hash liên tiếp: router thường phải hỏi nhiều shard. Truy vấn **equality trên toàn shard key**, chẳng hạn `{ eventId: "E100" }`, vẫn có thể được định tuyến đến shard phù hợp.

**Lưu ý về hash:**

- Hashed index **không** phải unique index; hai giá trị có thể tạo cùng hash và phép băm không chứng minh tính duy nhất.
- Hashed index không hỗ trợ dạng multikey: không dùng một trường mảng làm trường hash.
- Chọn một trường có ít giá trị phân biệt, ví dụ `status` chỉ nhận vài trạng thái, sẽ không tạo phân phối tốt chỉ nhờ gắn `"hashed"`.
- MongoDB hỗ trợ **compound hashed shard key**, ví dụ `{ region: 1, eventId: "hashed" }`; cần đánh giá riêng các ràng buộc về vùng và phân phối khởi tạo khi dùng key phức hợp.

### 3.3. Bảng so sánh

| Tiêu chí | Range shard key | Hashed shard key |
| --- | --- | --- |
| Cách chia | Theo khoảng giá trị gốc | Theo khoảng hash |
| Thế mạnh | Workload lọc/sắp xếp theo khoảng và tiền tố shard key | Ghi trải rộng với trường có cardinality cao, kể cả giá trị tăng dần |
| Truy vấn bằng toàn bộ key | Có thể định tuyến có mục tiêu | Có thể định tuyến có mục tiêu |
| Truy vấn khoảng trên key | Thường có lợi thế | Có thể phải truy vấn nhiều shard |
| Rủi ro | Hotspot ở đầu/cuối dải tăng đơn điệu, lệch phân bố | Không phù hợp key ít giá trị, mất tính cục bộ của range |
| `unique` trên chính key | Có thể có theo các điều kiện của sharded cluster | Không thể đặt `unique` trên hashed index hay `unique: true` cho hashed shard key |

Hai chiến lược đều cần đánh giá **cả hướng đọc lẫn hướng ghi**. Một hệ thống ingest log có thể ưu tiên hashed key để ghi đều, còn ứng dụng tra cứu lịch sử của một khách hàng theo thời gian có thể ưu tiên compound/range key dựa trên truy vấn thực tế.

## 4. Chọn shard key từ workload

Giả sử ứng dụng Spring Data MongoDB phục vụ nhiều cửa hàng, có những thao tác điển hình:

| Thao tác | Điều kiện truy vấn | Nhu cầu |
| --- | --- | --- |
| Xem một đơn hàng | `tenantId = ?` và `orderNumber = ?` | Lookup nhanh, mã đơn duy nhất trong mỗi tenant |
| Liệt kê đơn trong tháng | `tenantId = ?` và `createdAt BETWEEN ...` | Định tuyến hẹp, index hỗ trợ range |
| Ghi sự kiện mới | `eventId = ?` với ID tăng theo thời gian | Phân phối ghi đều |
| Tra cứu sự kiện | `eventId = ?` | Equality lookup |

Có thể thiết kế **hai collection với hai shard key khác nhau**:

- `tenantOrders` dùng range shard key `{ tenantId: 1 }` nếu số tenant đủ lớn, tải từng tenant tương đối cân bằng, và yêu cầu uniqueness là cặp `(tenantId, orderNumber)`.
- `events` dùng hashed shard key `{ eventId: "hashed" }` nếu phần lớn thao tác ghi và tra cứu theo `eventId`, còn truy vấn range ít quan trọng.

Đây là cấu hình minh họa. Với một số ít tenant rất lớn, `tenantId` đơn lẻ có thể trở thành điểm nóng; cần thử một shard key phức hợp thích hợp hoặc điều chỉnh phân vùng dữ liệu theo workload trước khi triển khai.

### 4.1. Những câu hỏi cần trả lời trước khi tạo key

1. **Cardinality:** có bao nhiêu giá trị shard key phân biệt, và liệu một giá trị có chiếm phần lớn document?
2. **Tần suất truy vấn:** bao nhiêu phần trăm truy vấn lọc bằng shard key đầy đủ, tiền tố hay hoàn toàn không có shard key?
3. **Kiểu ghi:** shard key có tăng liên tục khiến lượt insert dồn vào cuối dải không?
4. **Tính ổn định:** giá trị shard key có thường bị cập nhật không? Việc đổi giá trị key có thêm chi phí và điều kiện vận hành.
5. **Uniqueness:** cần duy nhất cho một trường toàn cục, hay duy nhất theo tổ hợp có tiền tố shard key?
6. **Vận hành:** sẽ sharding một collection trống hay collection đã chứa nhiều dữ liệu và index hiện hữu?

Đừng chọn `_id` mặc định chỉ vì mọi document đều có trường này: hãy đo xem shard key đó có phù hợp truy vấn và tính duy nhất cần bảo vệ hay không.

## 5. Chỉ mục bắt buộc và chỉ mục phục vụ truy vấn

Một sharded collection cần **index hỗ trợ shard key**. Với shard key dạng compound, shard key phải là **tiền tố** của index hỗ trợ; thứ tự các trường quyết định điều này.

Giả sử shard key là `{ tenantId: 1, createdAt: 1 }`:

```javascript
// Hỗ trợ shard key đúng thứ tự
db.orders.createIndex({ tenantId: 1, createdAt: 1 });
db.orders.createIndex({ tenantId: 1, createdAt: 1, status: 1 });

// Không dùng làm index hỗ trợ cho shard key phía trên
db.orders.createIndex({ createdAt: 1, tenantId: 1 });
db.orders.createIndex({ tenantId: 1 });
```

Index `{ tenantId: 1 }` có thể hỗ trợ một số truy vấn theo tenant, nhưng **không đủ** làm index hỗ trợ cho toàn bộ shard key phức hợp `{ tenantId: 1, createdAt: 1 }`.

Điểm cần nhớ khi gọi `sh.shardCollection()`:

- **Collection trống:** MongoDB có thể tự tạo index cho shard key nếu chưa có index phù hợp.
- **Collection đã có document:** phải tạo index hỗ trợ shard key trước thao tác sharding.
- Có thể tạo index phục vụ truy vấn khác ngoài shard key index, miễn đáp ứng các ràng buộc của sharded collection (đặc biệt đối với `unique`).
- Không thể tùy tiện xóa hoặc ẩn index duy nhất đang hỗ trợ shard key. Một số phiên bản MongoDB cho phép xóa **hashed shard key index** trong điều kiện đặc biệt, nhưng điều đó kéo theo tác động đến balancing và truy vấn; đây không phải tối ưu mặc định.

### 5.1. Shard key index chưa đủ để tối ưu mọi truy vấn

Nếu collection shard theo `{ tenantId: 1 }`, truy vấn:

```javascript
db.tenantOrders.find({
  tenantId: "shop-a",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 });
```

có thể được `mongos` định tuyến dựa vào `tenantId`, nhưng index chỉ có `tenantId` chưa chắc hiệu quả cho bước lọc/sắp xếp theo `createdAt`. Khi workload thường xuyên chạy truy vấn này, hãy xem xét index phụ:

```javascript
db.tenantOrders.createIndex({ tenantId: 1, createdAt: -1 });
```

Cần phân biệt hai việc: **shard targeting** do shard key hỗ trợ và **query execution** bên trong shard do các index thích hợp giúp tối ưu. Hãy đo bằng `explain("executionStats")` thay vì giả định mọi truy vấn có shard key đều nhanh.

## 6. Uniqueness trong sharded cluster

### 6.1. Vì sao có ràng buộc “shard key là tiền tố”?

Một shard tự kiểm tra được các document lưu trên shard đó. Để bảo đảm một cặp key không bị trùng **trên toàn cluster**, mọi document có cùng cặp key phải được định tuyến tới cùng shard kiểm tra.

Vì vậy, trên **ranged sharded collection**, MongoDB cho phép các unique index sau:

1. Unique index trực tiếp trên shard key.
2. Unique compound index có **toàn bộ shard key làm tiền tố**, theo đúng thứ tự.
3. Index `_id` mặc định, với ngoại lệ quan trọng được giải thích bên dưới.

Ví dụ, collection shard theo `{ tenantId: 1 }`:

| Index | Hợp lệ dưới dạng unique index? | Ý nghĩa |
| --- | --- | --- |
| `{ tenantId: 1 }` | Có | Mỗi `tenantId` tối đa một document, thường không phù hợp collection đơn hàng |
| `{ tenantId: 1, orderNumber: 1 }` | Có | Mỗi tenant không được trùng `orderNumber` |
| `{ tenantId: 1, email: 1 }` | Có | Mỗi tenant không được trùng `email` |
| `{ orderNumber: 1 }` | Không | Thiếu tiền tố shard key |
| `{ orderNumber: 1, tenantId: 1 }` | Không | Có shard key nhưng sai thứ tự tiền tố |

Index `{ tenantId: 1, orderNumber: 1 }` với `unique: true` đảm bảo **cặp giá trị** không trùng. Nó **không** yêu cầu tất cả `orderNumber` trên toàn cluster đều khác nhau. Hai tenant khác nhau được phép cùng dùng `"ORD-1001"`.

Nếu shard key là `{ tenantId: 1, createdAt: 1 }`, index `{ tenantId: 1, orderNumber: 1 }` **không đáp ứng** điều kiện unique vì thiếu trường `createdAt` thuộc shard key. Việc thêm `createdAt` vào unique index sẽ thay đổi ý nghĩa uniqueness: khi đó các document có cùng `tenantId` và `orderNumber` nhưng khác `createdAt` có thể cùng tồn tại. Đây là lý do **yêu cầu uniqueness phải được xác định trước khi chốt shard key**.

### 6.2. Trường `_id` có ngoại lệ dễ gây hiểu nhầm

MongoDB tạo index `_id` unique mặc định. Tuy nhiên, nếu sharded collection sử dụng shard key **khác** `_id`, unique index mặc định trên `_id` chỉ bảo đảm uniqueness **bên trong từng shard**; hai document có cùng `_id` vẫn có thể nằm trên hai shard khác nhau.

Vì vậy:

- Tạo `_id` đủ duy nhất từ phía ứng dụng, ví dụ một ID được sinh độc lập với khả năng trùng cực thấp.
- Đừng diễn giải việc tồn tại `_id_` index như bằng chứng cho global uniqueness trên mọi thiết kế shard key.
- Nếu bài toán bắt buộc unique tuyệt đối cho mã nghiệp vụ toàn hệ thống, cần thiết kế shard key hoặc quy trình ghi có cơ chế đảm bảo phù hợp.

### 6.3. Hashed key không có `unique: true`

Các lệnh kiểu sau **không hợp lệ**:

```javascript
// Ví dụ minh họa lệnh sai — KHÔNG chạy:
db.events.createIndex({ eventId: "hashed" }, { unique: true });
sh.shardCollection("shop.events", { eventId: "hashed" }, true);
```

MongoDB không cho phép unique constraint trên **hashed index**, cũng không chấp nhận tham số `unique = true` khi shard key là hashed.

Có thể có hướng xử lý uniqueness bằng một collection quản lý định danh riêng hoặc thay đổi mô hình shard key, nhưng **không nên giả định** rằng chỉ cần thêm một unique index thông thường trên cùng trường của hashed shard key là MongoDB sẽ bảo đảm duy nhất toàn cluster. Khi thiết kế giải pháp, phải xét đầy đủ ràng buộc unique index của sharded collection.

### 6.4. Các điều kiện khác cần kiểm tra

- Khi sharding một collection đang có unique index, các unique index đó phải tương thích với shard key dự kiến; nếu không, thao tác sharding sẽ thất bại.
- Khi collection đã sharded, không thể tạo unique index tùy ý thiếu shard key ở tiền tố.
- Unique index dùng collation cần lưu ý: bảo đảm uniqueness trong sharded cluster yêu cầu **simple collation** theo ràng buộc của MongoDB.
- Document thiếu trường trong unique index có thể tạo giá trị index tương đương `null`; nên chuẩn hóa dữ liệu, rà duplicate và xác định chính sách cho field tùy chọn.
- `unique: true` trong `sh.shardCollection()` (với **ranged key**) yêu cầu unique index **chính xác trên shard key**, không chỉ một unique compound index có shard key làm tiền tố.

## 7. Thực hành với `mongosh`

Các lệnh dưới đây dành cho **môi trường thực hành đã có sharded cluster** và kết nối tới **`mongos`**. Hai ví dụ dùng hai collection riêng để không trộn các lựa chọn shard key.

### 7.1. Ví dụ A — Range key và unique theo tenant

Bài toán: mỗi tenant có nhiều đơn hàng; mã `orderNumber` phải duy nhất **trong tenant**.

```javascript
// Kết nối mongosh tới mongos, rồi chọn database
use shop

// 1. Tạo collection và index trước khi ghi dữ liệu
db.createCollection("tenantOrders");
db.tenantOrders.createIndex({ tenantId: 1 });
db.tenantOrders.createIndex(
  { tenantId: 1, orderNumber: 1 },
  { unique: true, name: "uk_tenant_order" }
);
db.tenantOrders.createIndex({ tenantId: 1, createdAt: -1 });

// 2. Shard collection bằng range shard key
sh.shardCollection("shop.tenantOrders", { tenantId: 1 });

// 3. Ghi hai đơn hàng thuộc hai tenant
db.tenantOrders.insertMany([
  {
    tenantId: "shop-a",
    orderNumber: "ORD-1001",
    createdAt: ISODate("2026-11-20T02:15:00Z")
  },
  {
    tenantId: "shop-b",
    orderNumber: "ORD-1001",
    createdAt: ISODate("2026-11-20T02:16:00Z")
  }
]);

// 4. Kiểm thử duplicate trong cùng tenant: dự kiến E11000
db.tenantOrders.insertOne({
  tenantId: "shop-a",
  orderNumber: "ORD-1001",
  createdAt: ISODate("2026-11-20T02:17:00Z")
});
```

Trong ví dụ này:

- Hai document đầu **hợp lệ** dù cùng `orderNumber` vì thuộc hai tenant khác nhau.
- Insert cuối dự kiến lỗi `E11000 duplicate key` do trùng cặp `(tenantId, orderNumber)`.
- Shard key `{ tenantId: 1 }` đủ làm tiền tố của unique index `{ tenantId: 1, orderNumber: 1 }`.
- Unique index `uk_tenant_order` vừa bảo vệ quy tắc nghiệp vụ vừa có thể phục vụ truy vấn lọc bằng cả hai trường; index thời gian phục vụ kiểu truy vấn khác.

Nếu collection có sẵn dữ liệu, hãy **kiểm tra trùng lặp trước khi tạo unique index**. Việc tạo unique index sẽ thất bại khi đã có dữ liệu vi phạm.

### 7.2. Ví dụ B — Hashed key cho luồng sự kiện

Bài toán: ứng dụng liên tục ghi các sự kiện có ID tăng dần và thường đọc lại một sự kiện theo ID.

```javascript
use shop

db.createCollection("events");
db.events.createIndex({ eventId: "hashed" });

// Hashed shard key: KHÔNG truyền unique=true
sh.shardCollection("shop.events", { eventId: "hashed" });

db.events.insertMany([
  { eventId: "E000001", kind: "ORDER_CREATED" },
  { eventId: "E000002", kind: "ORDER_PAID" },
  { eventId: "E000003", kind: "ORDER_SHIPPED" }
]);

db.events.findOne({ eventId: "E000002" });
```

Hashed key có thể giúp phân tán các insert tăng dần khi tập giá trị đủ rộng. Tuy nhiên, **ví dụ này không cung cấp global unique constraint trên `eventId`**. Nếu cần ngăn trùng tuyệt đối, phải thiết kế thêm cơ chế thích hợp ngay từ đầu.

### 7.3. Ví dụ C — Thấy rõ giới hạn unique index

Với `shop.tenantOrders` đã sharded trên `{ tenantId: 1 }`, cú pháp sau **không được dùng để tạo unique index**:

```javascript
// Ví dụ minh họa lệnh không hợp lệ — KHÔNG chạy:
db.tenantOrders.createIndex(
  { orderNumber: 1 },
  { unique: true }
);

// Có thể tạo index bình thường phục vụ truy vấn,
// nhưng nó KHÔNG đảm bảo uniqueness cho orderNumber:
db.tenantOrders.createIndex({ orderNumber: 1 });
```

Một index **không unique** trên `orderNumber` là hợp lệ cho nhu cầu tra cứu, nhưng truy vấn không chứa shard key có thể phải gửi đến nhiều shard. Việc index tồn tại ở mỗi shard không tự giải quyết chi phí định tuyến.

## 8. Gắn với Spring Data MongoDB

Spring Data MongoDB giúp ánh xạ document và xây dựng truy vấn. **Việc tạo sharded cluster, lựa chọn shard key thực tế và chạy `sh.shardCollection()` là thao tác cấu hình MongoDB**. Chỉ đặt annotation Java không thay thế bước chuẩn bị index và shard collection trên server.

### 8.1. Entity dùng ranged shard key

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Sharded;
import org.springframework.data.mongodb.core.mapping.ShardingStrategy;

@Document(collection = "tenantOrders")
@Sharded(shardKey = "tenantId", shardingStrategy = ShardingStrategy.RANGE)
public class TenantOrder {

    @Id
    private String id;

    private String tenantId;
    private String orderNumber;
    private Instant createdAt;
    private String status;

    // Constructor, getters, setters...
}
```

`@Sharded` mô tả shard key trên entity và hỗ trợ Spring Data bổ sung điều kiện shard key cho **một số thao tác thay thế document**. Annotation không có nghĩa Spring Data tự tạo đủ index hay kích hoạt sharding trên cluster.

Với repository, hãy thể hiện tiền tố shard key trong phương thức truy vấn thường dùng:

```java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface TenantOrderRepository
        extends MongoRepository<TenantOrder, String> {

    Optional<TenantOrder> findByTenantIdAndOrderNumber(
            String tenantId, String orderNumber);
}
```

Một truy vấn cập nhật tường minh bằng `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class TenantOrderService {

    private final MongoTemplate template;

    public TenantOrderService(MongoTemplate template) {
        this.template = template;
    }

    public void markPaid(String tenantId, String orderNumber) {
        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                    .and("orderNumber").is(orderNumber)
        );

        Update update = new Update().set("status", "PAID");
        template.updateFirst(query, update, TenantOrder.class);
    }
}
```

Đưa `tenantId` vào filter vừa diễn đạt rõ phạm vi nghiệp vụ, vừa giúp `mongos` định tuyến tốt hơn. Với những thao tác cần shard key trong filter, **không dựa vào `@Sharded` để tự thêm key cho mọi loại query**; tài liệu Spring Data chỉ mô tả việc bổ sung tự động trong một số trường hợp cụ thể. Luôn kiểm tra câu lệnh thực tế và hành vi trên cluster.

### 8.2. Entity dùng hashed shard key

Nếu chọn sharding theo `eventId` cho collection sự kiện:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Sharded;
import org.springframework.data.mongodb.core.mapping.ShardingStrategy;

@Document(collection = "events")
@Sharded(shardKey = "eventId", shardingStrategy = ShardingStrategy.HASH)
public class EventDocument {

    @Id
    private String id;

    private String eventId;
    private String kind;

    // Constructor, getters, setters...
}
```

Giá trị enum của Spring Data là **`ShardingStrategy.HASH`**, còn cú pháp MongoDB trong `mongosh` là **`"hashed"`**. Chúng mô tả cùng chiến lược nhưng không sử dụng cùng từ khóa.

Index có thể được quản lý bằng script triển khai, migration hoặc `MongoTemplate.indexOps(...).ensureIndex(...)`. Nếu dựa vào annotation `@Indexed`/`@CompoundIndex`, phải kiểm tra cấu hình **automatic index creation**, vì tính năng đó không tự động bật trong mọi ứng dụng và không thay thế kiểm soát migration khi production đang có dữ liệu.

## 9. Quan sát cluster và kiểm chứng kết quả

Sau khi cấu hình, cần kiểm tra cả **schema/index**, **ràng buộc dữ liệu** và **truy vấn thực tế**.

### 9.1. Kiểm tra cấu hình/index

```javascript
use shop

sh.status();

db.tenantOrders.getIndexes();
db.events.getIndexes();
```

Từ `sh.status()`, tìm namespace, shard key và thông tin phân vùng tương ứng. Từ `getIndexes()`, xác nhận có index hỗ trợ key, đúng thứ tự trường, đúng `unique` cần thiết và không vô tình tạo unique hashed index (thao tác đó sẽ bị từ chối).

### 9.2. Xem `explain()` cho truy vấn thường dùng

```javascript
// Có shard key: thuận lợi cho shard targeting
db.tenantOrders.find({
  tenantId: "shop-a",
  orderNumber: "ORD-1001"
}).explain("executionStats");

// Thiếu shard key: có nguy cơ phân tán truy vấn
db.tenantOrders.find({
  orderNumber: "ORD-1001"
}).explain("executionStats");

// Equality trên hashed key
db.events.find({
  eventId: "E000002"
}).explain("executionStats");

// Range trên hashed key: có thể phải hỏi nhiều shard
db.events.find({
  eventId: { $gte: "E000001", $lt: "E000100" }
}).explain("executionStats");
```

Khi đọc kết quả, chú ý số shard được truy vấn, stage dùng index, số document được scan và thời gian xử lý. Định dạng `explain` có thể khác nhau giữa các phiên bản MongoDB; đánh giá trên kết quả thực tế thay vì phụ thuộc cứng vào một tên stage.

### 9.3. Các trường hợp lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `shardCollection` báo thiếu index | Collection có dữ liệu nhưng chưa có index hỗ trợ shard key | Tạo index với đủ trường và đúng thứ tự trước khi shard |
| Không thể tạo unique index | Unique index thiếu shard key làm tiền tố, hoặc dữ liệu đã trùng | Thiết kế lại constraint phù hợp và dọn duplicate |
| Insert trả `E11000` | Trùng tổ hợp trường bị ràng buộc `unique` | Kiểm tra giá trị tổ hợp; phản hồi lỗi nghiệp vụ chính xác |
| Ghi liên tục dồn vào một shard | Key range tăng đơn điệu, hoặc một giá trị key quá “nóng” | Xem xét hashed/compound key và phân bố workload |
| Query chậm dù index tồn tại | Filter thiếu shard key, index không hỗ trợ dạng truy vấn, hoặc nhiều shard cùng tham gia | Xem `explain()` và thiết kế lại filter/index |
| Lầm tưởng `_id` duy nhất toàn cluster | Shard key khác `_id`, index mặc định chỉ kiểm tra từng shard | Dùng chiến lược sinh ID duy nhất và xác định constraint toàn cục |
| Dùng hashed key nhưng vẫn cần unique business code | Unique hashed index không được hỗ trợ | Đổi mô hình shard key hoặc thiết kế cơ chế giữ uniqueness riêng |

## 10. Một quy trình ra quyết định có thể áp dụng

Khi bắt đầu một collection mới:

1. **Viết rõ quy tắc dữ liệu trước:** ví dụ “`orderNumber` chỉ cần duy nhất trong `tenantId`”.
2. **Liệt kê các query quan trọng:** equality, range, sort, update và tần suất thực tế.
3. **Ước lượng phân bố giá trị:** cardinality, tenant lớn, độ tăng đơn điệu, tốc độ ghi.
4. **Chọn key và chiến lược:** range nếu giữ thứ tự hỗ trợ truy vấn; hashed nếu cần phân tán giá trị tăng dần và chủ yếu tra cứu equality.
5. **Kiểm tra tính hợp lệ của mọi unique index hiện có:** đặc biệt yêu cầu tiền tố trên sharded collection.
6. **Tạo index hỗ trợ và index truy vấn**, chuẩn bị dữ liệu rồi shard qua `mongos`.
7. **Thử duplicate, quan sát `explain()` và thống kê cluster** trên tập dữ liệu đại diện trước khi đưa vào vận hành.

**Ba nguyên tắc cần nhớ:** range phù hợp khi tính cục bộ của khoảng giá trị quan trọng; hashed phù hợp khi phân phối ghi là ưu tiên và key đủ phân biệt; uniqueness trên sharded collection phải được thiết kế cùng shard key ngay từ đầu. Chọn sai ở bước này thường khó sửa hơn việc thêm một index phục vụ truy vấn.

## Tài liệu tham khảo

- MongoDB Manual — [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- MongoDB Manual — [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- MongoDB Manual — [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/)
- MongoDB Manual — [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/)
- MongoDB Manual — [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- Spring Data MongoDB — [`@Sharded` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Sharded.html)
- Spring Data MongoDB — [`ShardingStrategy` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/ShardingStrategy.html)
