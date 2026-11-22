# View chỉ đọc: định nghĩa, cách truy vấn và giới hạn trong MongoDB

## 1. Khái niệm view trong MongoDB

**View (standard view)** trong MongoDB là một đối tượng có thể truy vấn tương tự collection, nhưng nội dung của nó được **định nghĩa bằng aggregation pipeline** trên một collection hoặc một view khác. Khi client truy vấn view, MongoDB thực thi pipeline định nghĩa view, kết hợp với điều kiện của truy vấn rồi trả về kết quả.

Một view chuẩn có ba đặc điểm:

1. **Chỉ đọc (read-only):** cho phép truy vấn, không cho phép trực tiếp `insert`, `update`, `replace`, `delete` vào chính view.
2. **Không lưu bản sao dữ liệu kết quả:** MongoDB lưu **định nghĩa** của view, không lưu toàn bộ document mà view trả về.
3. **Kết quả phụ thuộc dữ liệu nguồn tại thời điểm truy vấn:** sau khi collection nguồn thay đổi, truy vấn view tiếp theo có thể trả về kết quả mới mà không cần “refresh” thủ công.

Sơ đồ khái niệm:

~~~text
Ứng dụng
   |
   |  find() / aggregate()
   v
VIEW: paid_orders_public
  pipeline: $match(status=PAID) -> $project(các trường công khai)
   |
   v
COLLECTION: orders (lưu tài liệu thật, có thể được cập nhật)
   |
   v
Kết quả truy vấn được tính theo yêu cầu
~~~

Ví dụ, một collection `orders` chứa cả đơn đang xử lý, đơn thanh toán và ghi chú nội bộ. Ta có thể tạo view `paid_orders_public` chỉ trình bày đơn đã thanh toán và chỉ giữ những trường mà màn hình thống kê cần đọc.

### View khác collection như thế nào?

| Tiêu chí | Collection | Standard view |
| --- | --- | --- |
| Lưu document thực | Có | Không, chỉ lưu định nghĩa pipeline |
| `find()`, `aggregate()` | Có | Có, với một số giới hạn |
| `insertOne()`, `updateOne()`, `deleteOne()` | Có nếu được cấp quyền | Không |
| Index B-tree/compound thông thường | Tạo trực tiếp được | Không tạo trực tiếp; dựa vào index nguồn |
| Khi dữ liệu nguồn thay đổi | Document trong collection thay đổi | Kết quả view thay đổi ở lần đọc tiếp theo |
| Thích hợp | Dữ liệu vận hành, nguồn dữ liệu gốc | Lớp truy vấn dùng lại, lọc trường, biểu diễn dữ liệu |
| Chi phí truy vấn | Theo truy vấn và index của collection | Gồm chi phí thực thi pipeline của view cùng truy vấn của client |

**Lưu ý:** View ở đây là *standard view*. MongoDB còn có **on-demand materialized view**, được tạo bằng cách ghi kết quả aggregation vào collection. Hai khái niệm có cách lưu trữ, cập nhật và tối ưu khác nhau; xem mục 10.

## 2. Chuẩn bị dữ liệu thực hành

Có thể chạy ví dụ trên MongoDB Community/Enterprise hoặc MongoDB Atlas qua **mongosh**. Thực hành dùng database riêng có tên `views_lab` để tránh ảnh hưởng dữ liệu khác.

Trong `mongosh`:

~~~javascript
use views_lab

// Collection chứa dữ liệu thực.
db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C01",
    status: "PAID",
    amount: 250000,
    createdAt: ISODate("2026-01-10T08:00:00Z"),
    customerEmail: "a@example.test",
    internalNote: "Nguồn quảng cáo A"
  },
  {
    _id: "O-1002",
    customerId: "C02",
    status: "PENDING",
    amount: 180000,
    createdAt: ISODate("2026-01-11T09:00:00Z"),
    customerEmail: "b@example.test",
    internalNote: "Đang chờ xác nhận thanh toán"
  },
  {
    _id: "O-1003",
    customerId: "C01",
    status: "PAID",
    amount: 125000,
    createdAt: ISODate("2026-02-02T10:00:00Z"),
    customerEmail: "a@example.test",
    internalNote: "Khách hàng quay lại"
  },
  {
    _id: "O-1004",
    customerId: "C03",
    status: "PAID",
    amount: 300000,
    createdAt: ISODate("2026-02-08T13:00:00Z"),
    customerEmail: "c@example.test",
    internalNote: "Ưu tiên giao hàng"
  }
]);

db.orders.find().sort({ _id: 1 });
~~~

Collection `orders` có bốn document, trong đó ba đơn có `status: "PAID"`. Hai trường `customerEmail` và `internalNote` sẽ không xuất hiện trong view được định nghĩa bên dưới.

> Dữ liệu và địa chỉ email `example.test` ở đây chỉ là ví dụ giả lập. Để minh họa việc che trường, ta dùng các trường không cần thiết cho giao diện báo cáo; bài này không tạo người dùng hoặc cấu hình xác thực.

## 3. Tạo view bằng `db.createView()`

Cú pháp tổng quát:

~~~javascript
db.createView(
  "<viewName>",
  "<sourceCollectionOrView>",
  [ /* aggregation pipeline */ ],
  { collation: { /* tùy chọn */ } }
);
~~~

Ý nghĩa:

- `viewName`: tên view sẽ được dùng để truy vấn.
- `sourceCollectionOrView`: tên collection hoặc view nguồn **trong cùng database**, không phải tên có kèm database ở phía trước.
- `pipeline`: mảng các stage aggregation mô tả cách lọc, tính toán hoặc biến đổi dữ liệu nguồn.
- `collation`: tùy chọn thiết lập quy tắc so sánh/sắp xếp chuỗi mặc định cho view.

Tạo view chỉ hiển thị đơn đã thanh toán:

~~~javascript
db.createView(
  "paid_orders_public",
  "orders",
  [
    { $match: { status: "PAID" } },
    {
      $project: {
        _id: 1,
        customerId: 1,
        amount: 1,
        createdAt: 1,
        month: {
          $dateToString: {
            format: "%Y-%m",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      }
    }
  ]
);
~~~

Pipeline có hai stage:

1. `$match` giữ các document có trạng thái `PAID`.
2. `$project` giới hạn trường trả về và tạo thêm `month` từ `createdAt`.

Document được trả về từ view có thể mang dạng:

~~~javascript
{
  _id: "O-1001",
  customerId: "C01",
  amount: 250000,
  createdAt: ISODate("2026-01-10T08:00:00.000Z"),
  month: "2026-01"
}
~~~

Không có `customerEmail` hoặc `internalNote` vì chúng không được đưa vào `$project`. MongoDB vẫn giữ hai trường đó trong collection `orders`; view chỉ điều chỉnh **dữ liệu biểu diễn cho người đọc**.

### Cách tạo tương đương bằng `db.createCollection()`

Có thể dùng `db.createCollection()` cùng `viewOn` và `pipeline`. Ví dụ tạo một view khác:

~~~javascript
db.createCollection("pending_orders_public", {
  viewOn: "orders",
  pipeline: [
    { $match: { status: "PENDING" } },
    { $project: { _id: 1, customerId: 1, amount: 1 } }
  ]
});
~~~

Hai cách tạo đều cho ra **view chuẩn chỉ đọc**, không phải collection vật lý. Không nên dùng cùng một tên cho view và collection vì chúng nằm trong namespace của database.

## 4. Truy vấn view như collection

View hỗ trợ nhiều thao tác truy vấn quen thuộc như `find()`, `findOne()`, `aggregate()`, `distinct()` và `countDocuments()`.

### 4.1. `find()` và điều kiện lọc

~~~javascript
// Đọc toàn bộ đơn đã thanh toán.
db.paid_orders_public.find().sort({ createdAt: 1 });

// Tìm đơn đã thanh toán của khách C01.
db.paid_orders_public.find(
  { customerId: "C01" },
  { _id: 1, amount: 1, month: 1 }
).sort({ amount: -1 });

// Lấy một đơn cụ thể.
db.paid_orders_public.findOne({ _id: "O-1001" });
~~~

Truy vấn thứ hai trả về hai đơn `O-1001` và `O-1003`, có tổng giá trị lần lượt 250.000 và 125.000. Đơn `O-1002` không xuất hiện vì trạng thái là `PENDING`, dù khách có thể truy vấn trực tiếp collection nguồn nếu được cấp quyền.

### 4.2. Sử dụng `aggregate()` trên view

View rất hữu ích khi nhiều màn hình cần dùng chung bước lọc/chiếu, nhưng mỗi màn hình muốn một phép tổng hợp riêng.

~~~javascript
db.paid_orders_public.aggregate([
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { totalAmount: -1 } }
]);
~~~

Kết quả dự kiến từ dữ liệu mẫu ban đầu:

| `_id` | `orderCount` | `totalAmount` |
| --- | ---: | ---: |
| `C01` | 2 | 375000 |
| `C03` | 1 | 300000 |

Nếu yêu cầu báo cáo theo tháng, sử dụng trường `month` mà view đã tạo sẵn:

~~~javascript
db.paid_orders_public.aggregate([
  {
    $group: {
      _id: "$month",
      totalAmount: { $sum: "$amount" },
      orders: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Từ bốn tài liệu ví dụ, tháng `2026-01` có một đơn PAID trị giá 250.000, tháng `2026-02` có hai đơn PAID trị giá tổng 425.000.

### 4.3. `countDocuments()` và `distinct()`

~~~javascript
// Có 3 đơn đã thanh toán trong dữ liệu ban đầu.
db.paid_orders_public.countDocuments({});

// Có 2 đơn đã thanh toán của C01.
db.paid_orders_public.countDocuments({ customerId: "C01" });

// Các customerId xuất hiện trong các đơn PAID.
db.paid_orders_public.distinct("customerId");
~~~

Đây là thao tác truy vấn trên **kết quả logic của view**. Đừng nhầm với một bảng riêng đã được lưu sẵn số liệu.

### 4.4. Kết hợp pipeline view với truy vấn từ client

Khi client gọi:

~~~javascript
db.paid_orders_public.find({ customerId: "C01" });
~~~

MongoDB về mặt logic sẽ đọc theo chuỗi điều kiện:

~~~text
Nguồn orders
  -> $match {status: "PAID"}       (pipeline định nghĩa view)
  -> $project {customerId, ...}    (pipeline định nghĩa view)
  -> $match {customerId: "C01"}    (điều kiện từ client)
  -> trả kết quả
~~~

Hệ thống có thể **tối ưu hóa/reorder** các stage để giảm lượng dữ liệu phải xử lý mà vẫn giữ kết quả tương đương. Đây là mô hình logic giúp hiểu query, không phải khẳng định chính xác thứ tự physical execution của mọi phiên bản MongoDB.

## 5. View là dữ liệu động, không phải ảnh chụp

Để thấy view không lưu bản sao dữ liệu, thêm một đơn PAID vào collection nguồn:

~~~javascript
db.orders.insertOne({
  _id: "O-1005",
  customerId: "C02",
  status: "PAID",
  amount: 90000,
  createdAt: ISODate("2026-02-12T09:00:00Z"),
  customerEmail: "b@example.test",
  internalNote: "Đơn mới"
});

db.paid_orders_public.find({ _id: "O-1005" });
~~~

Truy vấn view sẽ hiển thị `O-1005` dù không có thao tác chèn nào vào view. Thử đổi trạng thái đơn `O-1002` từ `PENDING` sang `PAID`:

~~~javascript
db.orders.updateOne(
  { _id: "O-1002" },
  { $set: { status: "PAID" } }
);

db.paid_orders_public.find({ _id: "O-1002" });
~~~

Lúc này `O-1002` đã thỏa điều kiện của view nên xuất hiện trong kết quả. Ngược lại, nếu sửa trạng thái một đơn từ `PAID` thành `CANCELLED`, nó sẽ bị loại khỏi kết quả view ở những lần đọc tiếp theo.

**Điểm cần hiểu:** View không có nút “đồng bộ dữ liệu” vì mỗi truy vấn đọc dữ liệu nguồn. Tuy nhiên, việc “nhìn thấy” thay đổi giữa nhiều truy vấn riêng lẻ còn phụ thuộc vào thời điểm đọc, read concern, replica lag và cách transaction vận hành; view không tự cung cấp một snapshot cố định hoặc nhất quán giữa các lệnh đọc.

## 6. Vì sao view chỉ đọc?

MongoDB không thể giả định cách ánh xạ một document kết quả của pipeline trở lại document nguồn. Ví dụ một view có thể:

- Lọc đi một số document bằng `$match`.
- Loại bỏ trường cần thiết để sửa bản ghi bằng `$project`.
- Gộp nhiều document vào một kết quả bằng `$group`.
- Tạo trường tính toán bằng `$addFields` hoặc `$project`.
- Kết hợp dữ liệu từ nhiều collection bằng `$lookup`.

Khi đó, `updateOne()` trên “kết quả view” sẽ thiếu quy tắc xác định document gốc hoặc cách tách thay đổi về nguồn. MongoDB vì vậy áp đặt **read-only ở cấp đối tượng view**.

Các thao tác sau không hợp lệ đối với standard view:

~~~javascript
// Minh họa thao tác KHÔNG ĐƯỢC PHÉP trên view.
db.paid_orders_public.insertOne({
  _id: "O-9999",
  customerId: "C09",
  amount: 1000
});

db.paid_orders_public.updateOne(
  { _id: "O-1001" },
  { $set: { amount: 1 } }
);

db.paid_orders_public.deleteOne({ _id: "O-1001" });
~~~

Mỗi lệnh cố ghi vào view sẽ phát sinh lỗi. Các đoạn trên chỉ dùng để hiểu giới hạn; không cần chạy ba lệnh liên tiếp trong một script không bắt lỗi.

Muốn sửa dữ liệu, ghi vào **collection nguồn**, sau đó đọc lại view:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001" },
  { $set: { amount: 260000 } }
);

// View tự hiển thị amount mới ở lần truy vấn sau.
db.paid_orders_public.findOne({ _id: "O-1001" });
~~~

Tính chỉ đọc của view khác với **quyền truy cập**. Người dùng được cấp quyền ghi vào collection nguồn vẫn có thể sửa nguồn trực tiếp; một view không có khả năng “khóa” toàn bộ dữ liệu gốc.

## 7. Xem, sửa và xóa định nghĩa view

### 7.1. Xem danh sách và định nghĩa

Các view xuất hiện cùng collection khi liệt kê namespace:

~~~javascript
db.getCollectionNames();

// Lấy thông tin của đúng view.
db.getCollectionInfos({ name: "paid_orders_public" });
~~~

Trong metadata, đối tượng view có `type: "view"` và phần `options` chứa `viewOn` cùng `pipeline`. Khi muốn xác định một namespace có thực sự là view hay không, hãy xem `type` trong `getCollectionInfos()` thay vì chỉ dựa vào tên.

Có thể kiểm tra kế hoạch thực thi truy vấn:

~~~javascript
db.paid_orders_public.find({ customerId: "C01" }).explain("executionStats");
~~~

Tùy phiên bản MongoDB và dạng query, đầu ra `explain` có cấu trúc khác nhau. Mục đích là quan sát pipeline đã mở rộng và liệu truy vấn có sử dụng index từ collection nguồn hay không.

**Lưu ý bảo mật:** Định nghĩa pipeline của view có thể xuất hiện trong `getCollectionInfos()` và `explain`. Không nhúng trực tiếp khóa bí mật, token hoặc giá trị nhạy cảm vào nội dung pipeline rồi giả định chúng được che khỏi người có quyền xem metadata.

### 7.2. Sửa view bằng `collMod`

Muốn thêm quy tắc chỉ lấy đơn có `amount >= 200000`, dùng lệnh `collMod`:

~~~javascript
db.runCommand({
  collMod: "paid_orders_public",
  viewOn: "orders",
  pipeline: [
    { $match: { status: "PAID", amount: { $gte: 200000 } } },
    {
      $project: {
        _id: 1,
        customerId: 1,
        amount: 1,
        createdAt: 1,
        month: {
          $dateToString: {
            format: "%Y-%m",
            date: "$createdAt",
            timezone: "UTC"
          }
        }
      }
    }
  ]
});
~~~

Sau thay đổi, view chỉ trả về đơn PAID thỏa điều kiện số tiền. Trường hợp triển khai có **access control**, lệnh sửa view yêu cầu quyền tương ứng; `viewOn` và `pipeline` cần được khai báo trong định nghĩa sửa.

Khi chỉnh view, hãy cung cấp toàn bộ pipeline mong muốn vì đây là **thay đổi định nghĩa**, không phải cập nhật một document trong collection nguồn.

### 7.3. Xóa và tạo lại

Nếu cần đổi tên view, MongoDB không có thao tác **rename trực tiếp** cho view. Quy trình thông dụng là tạo view tên mới với cùng định nghĩa, chuyển client sang tên mới, rồi xóa view cũ sau khi chắc chắn không còn phụ thuộc.

Để xóa view đã tạo trong bài:

~~~javascript
// Chỉ xóa view; collection orders vẫn còn.
db.pending_orders_public.drop();
~~~

Đối với view khác còn được sử dụng bởi ứng dụng, kiểm tra dependency trước khi xóa. Xóa view không đồng nghĩa xóa dữ liệu collection nguồn, nhưng các truy vấn vào tên view cũ sẽ không còn hoạt động.

## 8. Giới hạn của view: nhóm thao tác, index và hiệu năng

### 8.1. Những thao tác bị giới hạn

| Nhóm | Hành vi đối với standard view | Cách tiếp cận |
| --- | --- | --- |
| `insert` / `update` / `delete` / `replace` trực tiếp | Không hỗ trợ | Ghi vào collection nguồn |
| `$out`, `$merge` trong **pipeline định nghĩa view** | Không hỗ trợ, kể cả trong pipeline lồng | Dùng aggregation trên collection để tạo dữ liệu materialized |
| `renameCollection` / rename view | Không hỗ trợ | Tạo view tên mới, chuyển client, xóa tên cũ |
| `mapReduce` trên view | Không hỗ trợ | Dùng aggregation với các stage hỗ trợ |
| Truy vấn dùng `$text` trên view | Không hỗ trợ | Tìm trên collection nguồn hoặc dùng phương án Search phù hợp |
| Projection dạng `$` positional, `$elemMatch`, `$slice`, `$meta` trong `find()` | Không hỗ trợ trên view | Thiết kế `$project`, `$filter`, `$slice`... trong pipeline aggregation tương ứng khi được hỗ trợ |
| Tạo **general index** trực tiếp trên standard view | Không hỗ trợ | Tạo index trên collection nguồn |

Chú ý các ngoại lệ về MongoDB Search/Vector Search trên **compatible views** trong các phiên bản/dịch vụ có tính năng tương ứng. Đây không phải là việc tạo index B-tree thông thường trên toàn bộ standard view. Khi thiết kế, cần tham khảo đúng phiên bản MongoDB đang triển khai.

Ngoài ra, view nguồn phải ở **cùng database** với view đang tạo. Một view có thể truy vấn dựa trên một view khác; các view lồng nhau tăng mức tái sử dụng nhưng cũng khiến pipeline thực thi phức tạp hơn.

### 8.2. Không có index thông thường riêng cho view

Các index B-tree nằm trên collection vật lý. Ví dụ:

~~~javascript
db.orders.createIndex({
  status: 1,
  customerId: 1,
  createdAt: -1
});
~~~

Một truy vấn view có điều kiện trên `status` và `customerId` có thể tận dụng index này sau khi optimizer kết hợp pipeline view với truy vấn client. Tuy nhiên **khả năng dùng index phụ thuộc pipeline thực tế**, thứ tự stage, cấu trúc index và thống kê truy vấn; không phải cứ tồn tại index trên nguồn là mọi query view sẽ nhanh.

Để xác minh, dùng `explain("executionStats")`, xem các dấu hiệu `IXSCAN`, `COLLSCAN`, số document đã đọc và thời gian thực thi.

### 8.3. Pipeline của view có chi phí ở mỗi lần đọc

Vì view không lưu document kết quả, truy vấn phức tạp với `$group`, `$lookup`, `$sort` hoặc chuyển đổi nhiều trường có thể tốn CPU, RAM và I/O.

MongoDB có giới hạn bộ nhớ cho các stage chặn như blocking sort/group; khả năng ghi file tạm ra ổ đĩa phụ thuộc phiên bản và cấu hình `allowDiskUseByDefault`/`allowDiskUse`. Trong MongoDB từ 6.0, các stage cần hơn ngưỡng bộ nhớ thường có thể ghi file tạm theo cấu hình mặc định. Nếu truy vấn thường xuyên tạo dữ liệu rất lớn, cần theo dõi disk usage và kiểm tra execution plan.

Những cách cải thiện phổ biến:

1. Lọc bằng `$match` càng sớm càng hợp lý, nhất là trên trường có index nguồn.
2. Giữ `$project` đơn giản; tránh tính các biểu thức đắt đỏ khi không cần.
3. Tối ưu index trên collection nguồn dựa trên workload thực tế.
4. Đo chi phí bằng `explain`, profiler, metrics thay vì đoán.
5. Xem xét **on-demand materialized view** hoặc collection báo cáo riêng khi cùng kết quả tốn nhiều công sức tính lại.

### 8.4. Snapshot/read concern

Một view chuẩn không lưu timestamp của từng thay đổi nguồn và không cung cấp riêng cơ chế **point-in-time/snapshot isolation** cho đối tượng view. Đọc view không tạo “bản chụp lịch sử” cố định để bạn quay lại ở một thời điểm bất kỳ.

Khi nghiệp vụ cần một ảnh chụp dữ liệu nhất quán hoặc giao dịch xuyên nhiều collection, phải tìm hiểu đúng hỗ trợ của **read concern**, transaction, MongoDB deployment và API được dùng, thay vì xem view như snapshot.

## 9. Collation, phân quyền và an toàn dữ liệu

### 9.1. Collation của view

**Collation** quyết định quy tắc so sánh chuỗi, chẳng hạn phân biệt chữ hoa/chữ thường hoặc dấu tiếng Việt. Khi tạo view, có thể truyền collation:

~~~javascript
db.createView(
  "paid_orders_collated",
  "orders",
  [{ $match: { status: "PAID" } }],
  { collation: { locale: "en", strength: 2 } }
);
~~~

Các quy tắc cần nhớ:

- Nếu không đặt collation, view mặc định dùng **simple binary comparison**, không tự kế thừa collation của collection nguồn.
- Truy vấn vào view phải dùng collation đã xác định; cố ghi đè collation khác trong thao tác truy vấn sẽ gây lỗi.
- View được tạo từ view khác phải giữ collation tương thích với view nguồn.
- Các aggregation dùng nhiều view, ví dụ `$lookup` giữa các view, đòi hỏi collation phù hợp.

Vì `status` trong ví dụ là mã viết hoa cố định, không nhất thiết cần custom collation. Với tên người hoặc dữ liệu ngôn ngữ tự nhiên, chọn locale và strength phù hợp nghiệp vụ.

### 9.2. Chỉ cấp quyền đọc view

Khi MongoDB bật xác thực và phân quyền, có thể cho một tài khoản quyền **find** đối với view mà **không cấp find trực tiếp** đối với collection nguồn. Đây là lý do view hữu ích cho các ứng dụng cần nhìn vào một tập con dữ liệu.

Ví dụ về ý tưởng phân quyền:

~~~text
Nguồn: orders
  - có customerEmail, internalNote và dữ liệu chi tiết

View: paid_orders_public
  - chỉ có _id, customerId, amount, createdAt, month

Tài khoản báo cáo:
  - được cấp find trên paid_orders_public
  - không được cấp find trên orders
~~~

Mô hình này hữu ích để giới hạn dữ liệu ứng dụng có thể truy vấn thông qua tài khoản đó. Tuy nhiên cần chú ý:

- **View là đối tượng read-only, không tự tạo quyền**; quyền do hệ thống RBAC của MongoDB quyết định.
- Khi tạo/sửa view trên hệ thống bật phân quyền cần có privilege phù hợp, thường gồm quyền thao tác namespace và quyền đọc nguồn theo điều kiện của MongoDB.
- Định nghĩa view có thể bị lộ qua metadata và explain; đừng đưa trực tiếp chuỗi bí mật vào pipeline.
- Phải kiểm tra cả view khác, quyền đọc collection nguồn, khả năng chạy aggregation và các role khác của tài khoản. Một view che trường không hiệu quả nếu cùng tài khoản vẫn có quyền đọc trực tiếp nguồn.

View hỗ trợ giới hạn **các trường hiển thị**, nhưng không thay thế chính sách an toàn dữ liệu tổng thể, đặc biệt khi dữ liệu nhạy cảm nằm trong pipeline hoặc các đường truy cập khác.

## 10. Standard view và on-demand materialized view

Hai mô hình có thể cùng biểu diễn kết quả aggregation, nhưng cơ chế lưu dữ liệu khác nhau:

| Thuộc tính | Standard view | On-demand materialized view |
| --- | --- | --- |
| Định nghĩa | `db.createView` hoặc `db.createCollection` với `viewOn` | Aggregation ghi kết quả bằng `$merge` hoặc `$out` |
| Lưu kết quả | Không; tính khi đọc | Có; lưu trong collection vật lý |
| Cập nhật khi nguồn đổi | Truy vấn mới đọc lại nguồn | Cần chạy lại hoặc thiết kế quy trình cập nhật |
| Chi phí đọc thường xuyên | Có thể cao nếu pipeline nặng | Thường thấp hơn vì đã tính trước |
| Index thường | Không tạo trực tiếp trên view | Có thể tạo trên collection kết quả |
| Ghi trực tiếp vào kết quả | Không | Collection đích có thể là đối tượng ghi, tùy thiết kế |
| Phù hợp | Lọc/biểu diễn dùng chung, truy vấn động | Báo cáo phức tạp, dữ liệu tính trước, tối ưu đọc |

Ví dụ tạo collection chứa tổng tiền theo khách từ collection `orders`:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$customerId",
      totalPaid: { $sum: "$amount" }
    }
  },
  {
    $merge: {
      into: "paid_totals_snapshot",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
]);
~~~

Kết quả nằm trong **collection vật lý** `paid_totals_snapshot`, có thể đọc bằng `find()` và lập index như collection bình thường.

~~~javascript
db.paid_totals_snapshot.find().sort({ totalPaid: -1 });
~~~

Quan trọng: đây là **kết quả ở lần chạy pipeline**, không tự đồng bộ khi `orders` được cập nhật. Nếu một khách không còn đơn PAID và không xuất hiện trong kết quả aggregation mới, `$merge` dạng trên **không tự xóa** document cũ của khách đó trong collection đích. Muốn cập nhật đúng theo nghiệp vụ cần thiết kế cơ chế refresh, loại bỏ bản ghi lỗi thời hoặc xây dựng lại toàn bộ snapshot.

**Không đưa `$merge` hoặc `$out` vào chính pipeline định nghĩa standard view.** Nếu mục đích là tạo collection lưu kết quả, hãy chạy aggregation trên nguồn và dùng pipeline ghi kết quả phù hợp.

## 11. Lỗi thường gặp khi sử dụng view

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Ghi `insertOne`/`updateOne` vào view báo lỗi | View chuẩn chỉ đọc | Ghi vào collection nguồn |
| Tạo view báo lỗi do `$merge`/`$out` | Pipeline view chứa stage ghi dữ liệu | Bỏ stage ghi khỏi định nghĩa, dùng materialized collection nếu cần |
| Tạo view trên nguồn thuộc database khác | View yêu cầu nguồn trong cùng database | Chuyển view về cùng DB với nguồn hoặc thiết kế lại nguồn/pipeline |
| Query view dùng `$text` bị từ chối | `$text` không được hỗ trợ trên view | Tìm trên collection nguồn hoặc dùng giải pháp search phù hợp |
| Không tạo được index B-tree trên view | View không lưu document vật lý | Tạo index trên collection nguồn, dùng explain |
| Truy vấn view chậm | Pipeline phải tính mỗi lần, index nguồn chưa phù hợp | Tối ưu pipeline/index hoặc cân nhắc materialization |
| View không trả đơn mới như dự kiến | Dữ liệu mới không thỏa `$match`, trường bị `$project` loại | Kiểm tra document gốc và pipeline định nghĩa |
| Kết quả so sánh chuỗi bất ngờ | Collation của view khác giả định | Xem collation khi tạo view, kiểm tra loại so sánh |
| Không tạo/sửa/query được view vì `Unauthorized` | Tài khoản chưa được cấp quyền namespace phù hợp | Kiểm tra privilege và role trên view, source và database |
| View hỏng sau khi đổi tên/xóa collection nguồn | Định nghĩa view vẫn tham chiếu namespace cũ | Cập nhật `viewOn`/pipeline hoặc khôi phục nguồn theo dependency |

Khi gặp lỗi, quy trình chẩn đoán tốt là đọc `db.getCollectionInfos({name: ...})`, đối chiếu namespace `viewOn`, đọc từng stage pipeline, kiểm tra dữ liệu nguồn, kiểm tra quyền và cuối cùng dùng `explain` để tìm vấn đề hiệu năng. Không sửa dữ liệu nguồn chỉ để “làm view có kết quả” trước khi hiểu điều kiện lọc.

## 12. Bài tập thực hành

### Bài tập 1 — View lọc trạng thái

Tạo view `pending_orders_view` từ `orders` chỉ chứa các đơn có `status: "PENDING"`, hiển thị `_id`, `customerId` và `amount`. Truy vấn danh sách, thêm một đơn PENDING mới vào collection nguồn rồi truy vấn lại để quan sát tính động.

### Bài tập 2 — View tổng hợp theo khách

Tạo view `paid_amount_by_customer` từ `orders` với pipeline:

~~~javascript
db.createView(
  "paid_amount_by_customer",
  "orders",
  [
    { $match: { status: "PAID" } },
    {
      $group: {
        _id: "$customerId",
        orderCount: { $sum: 1 },
        totalPaid: { $sum: "$amount" }
      }
    }
  ]
);
~~~

Thử `find({ totalPaid: { $gte: 200000 } })` trên view. Giải thích vì sao truy vấn này không nhất thiết có index hiệu quả trên trường `totalPaid` vì đây là giá trị tính từ aggregation.

### Bài tập 3 — Quyền và giới hạn đọc

Liệt kê các thao tác có thể làm trực tiếp với standard view, thử truy vấn `distinct` và `countDocuments`, rồi dự đoán kết quả khi dùng `updateOne` trên view. Tìm cách thay đổi dữ liệu **thông qua collection nguồn** để view phản ánh trạng thái mới.

### Bài tập 4 — Quan sát optimizer

Tạo index trên `orders.status` và `orders.customerId`, sau đó dùng `explain("executionStats")` với truy vấn `paid_orders_public`. So sánh số document đã duyệt, stage đọc dữ liệu và execution plan trước/sau index. Chỉ đánh giá trên tập dữ liệu đủ lớn hoặc công cụ phân tích phù hợp; tập bốn document có thể khiến optimizer chọn collection scan dù đã có index.

### Bài tập 5 — Chọn giải pháp

Một dashboard cần báo cáo tổng doanh thu theo từng khách mỗi 15 phút. Truy vấn aggregation có nhiều phép `$lookup`, thời gian thực hiện lớn và lượng đơn tăng liên tục. Phân tích khi nào dùng standard view để tránh lặp pipeline và khi nào cần collection kết quả tính trước bằng `$merge` hoặc `$out`. Nếu dùng `$merge`, giải thích cách xử lý những khách không còn xuất hiện trong nguồn để tránh dữ liệu báo cáo cũ.

## 13. Tổng kết kiến thức trọng tâm

Standard view của MongoDB là **lớp truy vấn có tên** được định nghĩa bằng aggregation pipeline. View được tính theo yêu cầu, thích hợp để dùng lại logic lọc/chiếu, tạo giao diện đọc thống nhất và giới hạn các trường có thể nhìn thấy theo tài khoản được cấp quyền. Vì không lưu kết quả thành collection riêng, view không thể nhận thao tác ghi trực tiếp, không có index thông thường riêng và hiệu năng phụ thuộc pipeline cùng collection nguồn.

Khi dữ liệu cần tính toán nặng nhưng được đọc lặp lại nhiều lần, hãy cân nhắc vật chất hóa kết quả thành collection và thiết kế cơ chế đồng bộ. Việc sử dụng view đúng đắn luôn đi cùng kiểm soát quyền truy cập, giới hạn pipeline và quan sát execution plan.

### Tài liệu chính thức để tra cứu thêm

- [Views — MongoDB Manual](https://www.mongodb.com/docs/manual/core/views/): khái niệm standard view, hành vi chỉ đọc, chỉ mục và các giới hạn.
- [Create and Query a View](https://www.mongodb.com/docs/manual/core/views/create-view/): `db.createView`, `db.createCollection`, ví dụ truy vấn và giới hạn pipeline.
- [Supported Operations for Views](https://www.mongodb.com/docs/manual/core/views/supported-operations/): danh sách lệnh hỗ trợ đối với view.
- [Modify or Remove a View](https://www.mongodb.com/docs/manual/core/views/update-view/): thay đổi pipeline bằng `collMod` và xóa view.
- [Create a View with Default Collation](https://www.mongodb.com/docs/manual/core/views/specify-collation/): quy tắc collation.
- [On-Demand Materialized Views](https://www.mongodb.com/docs/manual/core/materialized-views/): lưu kết quả aggregation bằng `$merge` và `$out`.
