# Đọc kết quả aggregation bằng cursor và kiểm chứng từng stage trong MongoDB

## 1. Mục tiêu bài học

Trong MongoDB, **aggregation pipeline** xử lý document qua một chuỗi stage như `$match`, `$project`, `$unwind`, `$group`, `$sort` và `$limit`. Mỗi stage nhận dữ liệu từ stage trước và tạo dữ liệu đầu vào cho stage tiếp theo. Kết quả cuối cùng thường được trả về cho ứng dụng thông qua **cursor**, không nhất thiết là một mảng được tải toàn bộ vào RAM.

Bài này giải quyết hai kỹ năng thường đi cùng nhau:

1. **Đọc kết quả đúng cách:** sử dụng aggregation cursor trong `mongosh` và driver; lựa chọn `toArray()`, `forEach()`, `hasNext()/next()`; hiểu batch, `getMore`, đóng cursor và giới hạn tài nguyên.
2. **Kiểm chứng từng stage:** tách pipeline thành các đoạn tiền tố, so sánh document trước/sau mỗi biến đổi, đối chiếu số lượng, giá trị và kiểu BSON; sử dụng `explain()` để hiểu kế hoạch thực thi mà không nhầm với kết quả nghiệp vụ.

Sau bài học, bạn sẽ biết cách nhận diện một tổng doanh thu bị sai do `$unwind`, một tổng đếm bị sai do `$group`, một kết quả mất trường do `$project` hoặc một truy vấn chậm do stage chặn như `$sort`.

> **Phạm vi:** Các ví dụ tập trung vào pipeline đọc dữ liệu. Các stage ghi dữ liệu như `$merge` và `$out` có tác dụng phụ, nên không được đưa vào các tiện ích kiểm tra trung gian một cách tùy tiện.

## 2. Mô hình hoạt động: pipeline và cursor

Có thể hình dung luồng xử lý:

~~~text
Collection orders
       |
       v
   $match          -> chọn đơn PAID
       |
       v
   $project        -> giữ trường cần xử lý
       |
       v
   $unwind         -> mỗi item trở thành một document logic
       |
       v
   $set            -> tính thành tiền từng item
       |
       v
   $group          -> tổng hợp theo mã hàng
       |
       v
   $sort           -> xếp theo doanh thu
       |
       v
   $limit          -> lấy nhóm đầu
       |
       v
Aggregation cursor
       |
       +-- next()/hasNext(): đọc tuần tự
       +-- forEach():       xử lý từng document
       +-- toArray():       gom toàn bộ kết quả vào mảng
       +-- close():         giải phóng tài nguyên cursor
~~~

Một số stage có thể xử lý theo kiểu streaming, trong khi các stage như `$group` và `$sort` có thể cần đọc và giữ nhiều dữ liệu đầu vào trước khi phát ra kết quả. Vì vậy cursor là cơ chế **đọc kết quả đầu ra**, **không đảm bảo toàn bộ pipeline đều xử lý một document rồi trả ngay một document**.

Điểm khác biệt quan trọng:

| Đối tượng/khái niệm | Chức năng |
| --- | --- |
| **Aggregation pipeline** | Quy tắc biến đổi dữ liệu gồm các stage theo thứ tự |
| **Aggregation result document** | Một document được tạo ra ở đầu ra pipeline |
| **Aggregation cursor** | Giao diện để client đọc lần lượt các result document |
| **Batch** | Một nhóm result document được truyền từ server tới client |
| **`getMore`** | Lệnh lấy thêm batch của cursor đang hoạt động |
| **`explain`** | Thông tin về kế hoạch và quá trình thực thi, không phải danh sách kết quả nghiệp vụ |

Một pipeline có thể trả **0, 1, 10 hoặc hàng triệu document**. Cursor giúp ứng dụng không bắt buộc phải tải hàng triệu kết quả vào bộ nhớ cùng một lúc.

## 3. Chuẩn bị dữ liệu thực hành có thể đối chiếu bằng tay

Dùng **mongosh** kết nối tới MongoDB rồi tạo database riêng:

~~~javascript
var lab = db.getSiblingDB("aggregation_cursor_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: "O01",
    status: "PAID",
    customerId: "C01",
    region: "north",
    createdAt: ISODate("2026-01-03T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 2, unitPrice: 100 },
      { sku: "MS", quantity: 1, unitPrice: 50 }
    ]
  },
  {
    _id: "O02",
    status: "PAID",
    customerId: "C02",
    region: "south",
    createdAt: ISODate("2026-01-04T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 1, unitPrice: 100 },
      { sku: "PAD", quantity: 2, unitPrice: 30 }
    ]
  },
  {
    _id: "O03",
    status: "PENDING",
    customerId: "C01",
    region: "north",
    createdAt: ISODate("2026-01-05T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 5, unitPrice: 100 }
    ]
  },
  {
    _id: "O04",
    status: "PAID",
    customerId: "C03",
    region: "north",
    createdAt: ISODate("2026-01-06T08:00:00Z"),
    items: [
      { sku: "MS", quantity: 3, unitPrice: 50 }
    ]
  },
  {
    _id: "O05",
    status: "PAID",
    customerId: "C01",
    region: "south",
    createdAt: ISODate("2026-01-07T08:00:00Z"),
    items: [
      { sku: "MS", quantity: 2, unitPrice: 50 },
      { sku: "PAD", quantity: 1, unitPrice: 30 }
    ]
  },
  {
    _id: "O06",
    status: "CANCELLED",
    customerId: "C04",
    region: "south",
    createdAt: ISODate("2026-01-08T08:00:00Z"),
    items: [
      { sku: "PAD", quantity: 4, unitPrice: 30 }
    ]
  },
  {
    _id: "O07",
    status: "PAID",
    customerId: "C02",
    region: "north",
    createdAt: ISODate("2026-01-09T08:00:00Z"),
    items: [
      { sku: "KB", quantity: 1, unitPrice: 100 },
      { sku: "MS", quantity: 1, unitPrice: 50 },
      { sku: "PAD", quantity: 1, unitPrice: 30 }
    ]
  },
  {
    _id: "O08",
    status: "PAID",
    customerId: "C03",
    region: "south",
    createdAt: ISODate("2026-01-10T08:00:00Z"),
    items: []
  },
  {
    _id: "O09",
    status: "PAID",
    customerId: "C05",
    region: "north",
    createdAt: ISODate("2026-01-11T08:00:00Z")
    // Cố ý thiếu field items.
  }
]);

lab.orders.find(
  {},
  { _id: 1, status: 1, items: 1 }
).sort({ _id: 1 });
~~~

Có tổng cộng **9 đơn hàng**:

- **7 đơn PAID:** O01, O02, O04, O05, O07, O08 và O09.
- **1 đơn PENDING:** O03.
- **1 đơn CANCELLED:** O06.
- **O08** có `items: []`; **O09** không có field `items`.

Hai trường hợp cuối giúp nhận biết những stage có thể **làm giảm số document đầu ra**. Trong dữ liệu mẫu, `unitPrice` và `quantity` là số nguyên nhỏ để có thể kiểm chứng tổng bằng tay; với tiền tệ thực tế, nên chọn kiểu số và quy tắc làm tròn phù hợp như Decimal128.

**Không chạy `drop()` trên collection sản xuất.** Bộ dữ liệu trong database `aggregation_cursor_lab` chỉ phục vụ bài thực hành.

## 4. Viết pipeline báo cáo doanh thu theo SKU

Mục tiêu: chỉ tính những item thuộc đơn đã thanh toán, rồi trả **hai SKU có doanh thu cao nhất**.

~~~javascript
var pipeline = [
  // Stage 1: chỉ các đơn đã thanh toán.
  {
    $match: {
      status: "PAID"
    }
  },

  // Stage 2: giữ các trường cần thiết cho phép tính.
  {
    $project: {
      _id: 0,
      orderId: "$_id",
      customerId: 1,
      region: 1,
      items: 1
    }
  },

  // Stage 3: mỗi item trở thành một dòng logic.
  {
    $unwind: "$items"
  },

  // Stage 4: tính doanh thu của dòng item.
  {
    $set: {
      lineTotal: {
        $multiply: ["$items.quantity", "$items.unitPrice"]
      }
    }
  },

  // Stage 5: gộp các dòng cùng SKU.
  {
    $group: {
      _id: "$items.sku",
      totalQuantity: { $sum: "$items.quantity" },
      totalRevenue: { $sum: "$lineTotal" },
      lineCount: { $sum: 1 }
    }
  },

  // Stage 6: đặt tên trường thân thiện với API.
  {
    $project: {
      _id: 0,
      sku: "$_id",
      totalQuantity: 1,
      totalRevenue: 1,
      lineCount: 1
    }
  },

  // Stage 7: doanh thu lớn trước; sku làm khóa phụ.
  {
    $sort: {
      totalRevenue: -1,
      sku: 1
    }
  },

  // Stage 8: chỉ lấy 2 nhóm đầu.
  {
    $limit: 2
  }
];
~~~

Chạy:

~~~javascript
var cursor = lab.orders.aggregate(pipeline);

cursor.toArray();
~~~

Kết quả về mặt giá trị:

~~~javascript
[
  {
    sku: "KB",
    totalQuantity: 4,
    totalRevenue: 400,
    lineCount: 3
  },
  {
    sku: "MS",
    totalQuantity: 7,
    totalRevenue: 350,
    lineCount: 4
  }
]
~~~

Phần `PAD` không xuất hiện ở kết quả cuối vì `$limit: 2`, **không phải vì tổng doanh thu bằng 0**. Khi kiểm chứng `$group` trước `$limit`, bạn sẽ thấy nhóm PAD có doanh thu 120.

### Kiểm chứng số học bằng tay

| SKU | Dòng trong đơn PAID | Số lượng bán | Doanh thu |
| --- | --- | ---: | ---: |
| KB | O01: 2 × 100; O02: 1 × 100; O07: 1 × 100 | 4 | **400** |
| MS | O01: 1 × 50; O04: 3 × 50; O05: 2 × 50; O07: 1 × 50 | 7 | **350** |
| PAD | O02: 2 × 30; O05: 1 × 30; O07: 1 × 30 | 4 | **120** |
| **Tổng** | 10 dòng item trong 5 đơn có item | **15** | **870** |

Dù có **7 đơn PAID**, chỉ **5 đơn PAID có ít nhất một item**. Nếu nhóm theo SKU sau `$unwind` mặc định, O08 và O09 sẽ không đóng góp dòng nào.

## 5. Aggregation trả về cursor như thế nào?

### 5.1. `aggregate()` trả cursor, không phải JavaScript array

Trong `mongosh`, đối với pipeline trả kết quả đọc thông thường:

~~~javascript
var resultCursor = lab.orders.aggregate(pipeline);
~~~

`resultCursor` là đối tượng cursor. Nó có thể cung cấp các thao tác:

~~~javascript
resultCursor.hasNext();
resultCursor.next();
resultCursor.toArray();
resultCursor.forEach(doc => printjson(doc));
resultCursor.close();
~~~

**Chỉ chọn một chiến lược tiêu thụ trên một cursor**. Sau khi đã gọi `toArray()`, các phần tử đã được tiêu thụ; không thể kỳ vọng `next()` lại trả phần tử đầu tiên như ban đầu.

Muốn đọc lại kết quả từ đầu, tạo **cursor mới bằng lệnh aggregate mới**:

~~~javascript
var again = lab.orders.aggregate(pipeline);
again.toArray();
~~~

Một cursor **không phải bản sao dữ liệu đã lưu trong biến**. Nó đại diện cho quá trình nhận kết quả của một lần thực thi; dữ liệu nguồn có thể thay đổi giữa các lần gọi lệnh riêng.

### 5.2. Dùng `toArray()` khi kết quả nhỏ

~~~javascript
var smallCursor = lab.orders.aggregate(pipeline);
var rows = smallCursor.toArray();

printjson(rows);
print("Số nhóm trả về: " + rows.length);
~~~

Ưu điểm:

- Dễ thử nghiệm trong `mongosh`.
- Dễ kiểm tra toàn bộ output nhỏ.
- Có thể dùng `map()`, `filter()`, `reduce()` ở JavaScript để đối chiếu.

Hạn chế:

- `toArray()` **gom toàn bộ kết quả còn lại vào bộ nhớ client**.
- Với tập kết quả lớn, có thể gây tăng RAM và làm chậm/đổ ứng dụng.
- Một cursor đã đọc dở thì `toArray()` chỉ lấy **phần còn lại**, không tự đọc lại các phần tử đã tiêu thụ.

Ví dụ:

~~~javascript
var c = lab.orders.aggregate(pipeline);
var firstDoc = c.next();

printjson(firstDoc);
printjson(c.toArray()); // Chỉ còn nhóm thứ hai.
~~~

Với bài toán báo cáo top 2, `toArray()` phù hợp. Với xuất dữ liệu hàng triệu dòng, nên xử lý tuần tự hoặc theo batch.

### 5.3. Đọc tuần tự bằng `hasNext()` và `next()`

~~~javascript
var c = lab.orders.aggregate(pipeline);

while (c.hasNext()) {
  var row = c.next();

  print(row.sku + ": " + row.totalRevenue);
}

c.close();
~~~

`hasNext()` cho biết còn phần tử để đọc hay không, có thể cần lấy thêm dữ liệu từ server. `next()` trả document kế tiếp; không gọi `next()` sau khi cursor đã hết nếu không xử lý tình huống lỗi.

Cách này phù hợp khi:

- Muốn xử lý từng bản ghi thay vì giữ toàn bộ output.
- Cần dừng sớm theo quy tắc riêng của ứng dụng.
- Muốn gửi dữ liệu vào file/output stream theo từng dòng.

### 5.4. Dùng `forEach()`

~~~javascript
var c = lab.orders.aggregate(pipeline);

c.forEach(doc => {
  print(doc.sku + " | qty=" + doc.totalQuantity +
        " | revenue=" + doc.totalRevenue);
});
~~~

`forEach()` gọi callback cho từng document được trả về và tiêu thụ cursor. Khi callback có thể báo lỗi, cần xử lý lỗi/đóng cursor phù hợp với ngữ cảnh. Không tái sử dụng cùng cursor sau khi đã duyệt hết mà mong có dữ liệu mới.

### 5.5. Dừng sớm và đóng cursor

Với pipeline trả nhiều kết quả, có thể chỉ đọc vài document rồi dừng:

~~~javascript
var c = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { _id: 1 } }
]);

var readCount = 0;

try {
  while (c.hasNext() && readCount < 3) {
    printjson(c.next());
    readCount++;
  }
} finally {
  c.close();
}
~~~

Đóng cursor sớm giúp giải phóng các tài nguyên liên quan phía client và server khi còn cursor mở. Với pipeline có stage blocking, server có thể đã xử lý lượng dữ liệu đáng kể trước khi bạn gọi `next()`, nên dừng client sau ba dòng **không đồng nghĩa server chỉ xử lý ba document**.

## 6. Batch size, getMore và cách cursor lấy dữ liệu

### 6.1. Cursor đọc kết quả theo batch

MongoDB không nhất thiết truyền từng document bằng một network request. Thay vào đó, server trả một **batch đầu tiên** rồi các batch tiếp theo thông qua `getMore` khi cần.

~~~text
Client gửi aggregate(pipeline)
          |
          v
MongoDB thực thi và trả firstBatch + cursor id (nếu còn dữ liệu)
          |
          v
Client đọc document trong batch hiện có
          |
          +--- vẫn còn trong batch: đọc trực tiếp
          |
          +--- hết batch, cursor còn: getMore
                                    |
                                    v
                                 batch kế
~~~

`batchSize` là **số document mục tiêu tối đa trong một batch theo cấu hình**, không phải số document tổng cộng của aggregation. Server còn giới hạn kích thước batch theo thông điệp/BSON và có thể trả ít hơn con số được yêu cầu.

### 6.2. Chỉ định batch size trong mongosh

Tùy API của `mongosh`, có thể cấu hình cursor batch khi gọi `aggregate()`:

~~~javascript
var c = lab.orders.aggregate(
  [
    { $match: { status: "PAID" } },
    { $sort: { _id: 1 } }
  ],
  {
    cursor: { batchSize: 2 }
  }
);

c.forEach(doc => print(doc._id));
~~~

Hoặc dùng phương thức cấu hình cursor nếu phiên bản cursor API hỗ trợ:

~~~javascript
var c2 = lab.orders.aggregate([
  { $match: { status: "PAID" } }
]);

c2.batchSize(2);
c2.toArray();
~~~

Mục đích là minh họa rằng **batch size điều chỉnh cách truyền**, không làm thay đổi filter, sort hay số kết quả logic.

Đối với pipeline mẫu có `$limit: 2`, thay batch size không thể khiến server trả ba SKU. Muốn ba SKU, cần thay `$limit` hoặc bỏ stage đó.

### 6.3. Batch size không phải $limit

| Cấu hình | Điều gì bị giới hạn? |
| --- | --- |
| `$limit: 2` trong pipeline | **Tổng số result document** ở vị trí pipeline đó |
| `cursor: { batchSize: 2 }` | Kích thước mỗi đợt dữ liệu trả về cho client |
| `find().limit(2)` | Số document của truy vấn find, không phải số phần tử của mảng trong từng document |
| `$slice` trên một mảng | Số phần tử được lấy trong mảng, không phải batch cursor |

Ví dụ:

~~~javascript
// Có thể trả 7 document PAID, nhưng theo các batch nhỏ.
var c = lab.orders.aggregate(
  [{ $match: { status: "PAID" } }],
  { cursor: { batchSize: 2 } }
);

print(c.toArray().length); // 7
~~~

### 6.4. Cursor timeout và lifecycle

Một server-side cursor có thể bị đóng do:

- Đã đọc hết kết quả.
- Client đóng cursor.
- Kết nối/phiên làm việc chấm dứt.
- Cursor không hoạt động quá thời gian được cấu hình và bị server thu hồi.
- Lỗi query, timeout hoặc các điều kiện quản trị khác.

Không nên giữ cursor sống qua những khoảng nghỉ dài của người dùng trong REST API. Với phân trang nhiều HTTP request, thường tạo một truy vấn mới cho mỗi trang và dùng **keyset cursor token hoặc filter phân trang** thay vì giữ cursor server mở trong thời gian dài.

Tùy phiên bản/driver, có tùy chọn `noCursorTimeout` hoặc cấu hình session, nhưng không biến nó thành giải pháp mặc định vì cursor lâu dài tiêu tốn tài nguyên và session vẫn có vòng đời riêng.

## 7. Kiểm chứng pipeline từng stage bằng cách chạy tiền tố

Lỗi aggregation dễ xảy ra khi nhiều stage nối tiếp. Cách chắc chắn nhất để hiểu **ngữ nghĩa dữ liệu** là chạy từng **tiền tố (prefix)** của pipeline:

~~~text
P1 = [stage1]
P2 = [stage1, stage2]
P3 = [stage1, stage2, stage3]
...
P8 = [stage1, ..., stage8]
~~~

Mỗi `Pk` cho biết document trông thế nào **ngay sau stage thứ k theo logic pipeline**.

### 7.1. Hàm xem đầu ra của một prefix

Trong `mongosh`:

~~~javascript
function inspectStage(pipeline, stageCount, sampleSize = 5) {
  if (!Number.isInteger(stageCount) ||
      stageCount < 1 || stageCount > pipeline.length) {
    throw new Error("stageCount không hợp lệ");
  }

  if (!Number.isInteger(sampleSize) || sampleSize < 1) {
    throw new Error("sampleSize phải >= 1");
  }

  // Tạo pipeline mới, không sửa mảng pipeline gốc.
  var prefix = pipeline.slice(0, stageCount);

  // Limit ở cuối prefix giúp tránh in ra quá nhiều output.
  var preview = prefix.concat([{ $limit: sampleSize }]);

  print("Sau stage " + stageCount +
        " | " + Object.keys(pipeline[stageCount - 1])[0]);

  lab.orders.aggregate(preview).forEach(printjson);
}
~~~

Gọi:

~~~javascript
inspectStage(pipeline, 1); // sau $match
inspectStage(pipeline, 2); // sau $project
inspectStage(pipeline, 3); // sau $unwind
inspectStage(pipeline, 4); // sau $set
inspectStage(pipeline, 5); // sau $group
inspectStage(pipeline, 6); // sau $project thứ hai
inspectStage(pipeline, 7); // sau $sort
inspectStage(pipeline, 8); // sau $limit
~~~

**Hai lưu ý quan trọng:**

- `$limit` được **thêm ở cuối prefix**, không được chèn vào giữa pipeline gốc rồi dùng kết quả đó để kết luận rằng toàn bộ pipeline giữ nguyên ngữ nghĩa. Đặc biệt, đưa `$limit` trước `$group` hoặc `$sort` sẽ làm thay đổi tổng hợp hoặc thứ tự.
- Với stage blocking như `$group`/`$sort`, một `$limit` ở cuối prefix vẫn có thể buộc server xử lý phần lớn hoặc toàn bộ input. Đây là cách **giới hạn số dòng in ra**, không phải công cụ đảm bảo query tiết kiệm tài nguyên.

Với pipeline có `$out` hoặc `$merge`, **không sử dụng tiện ích tự động chạy prefix** như trên nếu prefix có stage ghi; việc “xem thử” có thể gây ghi dữ liệu. Các ví dụ trong bài đều là pipeline đọc.

### 7.2. Dùng $limit và $sort có chủ đích để kiểm tra

Nếu muốn xem một mẫu **ổn định** trước khi tạo pipeline phức tạp, có thể chạy **truy vấn debug riêng**:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $sort: { _id: 1 } },
  { $limit: 3 },
  { $project: { _id: 1, customerId: 1, items: 1 } }
]);
~~~

Đây là **pipeline để thăm dò dữ liệu**, không phải tiền tố giống hệt pipeline báo cáo chính. Nó hữu ích để nhìn vài document dễ so sánh, nhưng không được dùng ba document mẫu để khẳng định tổng doanh thu toàn bộ collection.

Nếu muốn kiểm tra **đầy đủ tất cả các nhóm** của `$group`, hãy chạy prefix đến stage `$group` và **không đặt giới hạn làm mất nhóm**.

## 8. Kiểm chứng stage 1: $match

Stage đầu lọc đơn đã thanh toán:

~~~javascript
lab.orders.aggregate([
  {
    $match: { status: "PAID" }
  }
]).toArray();
~~~

Kết quả phải chứa **7** document:

~~~text
O01, O02, O04, O05, O07, O08, O09
~~~

Thử đếm trực tiếp:

~~~javascript
var matched = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $count: "orderCount" }
]).toArray();

printjson(matched);
// [{ orderCount: 7 }]
~~~

Hoặc so sánh:

~~~javascript
lab.orders.countDocuments({ status: "PAID" }); // 7
~~~

**Điều cần kiểm chứng:**

- Có lọc đúng giá trị enum `"PAID"` không, hay dữ liệu có `"paid"`/`"Paid"`?
- Có bản ghi thiếu `status` không?
- Query có ràng buộc tenant, quyền truy cập hoặc ngày cần thiết chưa?
- Kết quả đếm có phù hợp quy tắc nghiệp vụ không?

`$match` về mặt logic chỉ giữ hoặc loại document, **không biến một document thành nhiều document**. Nếu số lượng tăng sau `$match`, phải xem lại cách đo hoặc dữ liệu nguồn đã thay đổi giữa hai lần chạy.

## 9. Kiểm chứng stage 2: $project

Dùng prefix hai stage:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 2))
  .forEach(printjson);
~~~

Một document minh họa:

~~~javascript
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: [
    { sku: "KB", quantity: 2, unitPrice: 100 },
    { sku: "MS", quantity: 1, unitPrice: 50 }
  ]
}
~~~

Stage `$project` trong pipeline:

~~~javascript
{
  $project: {
    _id: 0,
    orderId: "$_id",
    customerId: 1,
    region: 1,
    items: 1
  }
}
~~~

Đối chiếu:

- Trường `_id` bị loại khỏi output.
- Giá trị `_id` gốc được chuyển thành `orderId`.
- `customerId`, `region`, `items` được giữ.
- `status` và `createdAt` không còn trong kết quả prefix, vì không được include.
- Số document vẫn là **7**; chỉ hình dạng document thay đổi.

**Lỗi phổ biến:** Nếu stage tiếp theo muốn sử dụng `"$status"` hoặc `"$createdAt"` mà `$project` đã loại bỏ chúng, biểu thức có thể nhận missing/null, làm sai kết quả. Khi kiểm tra từng prefix, hãy xác định rõ những field sẽ được stage sau dùng.

Không nhất thiết `$project` phải nằm sớm nhất trong mọi pipeline. MongoDB optimizer có thể tự tối ưu lượng field cần thiết. Dùng `$project` có chủ đích để chuẩn hóa output, không chỉ với giả định rằng nó luôn làm query nhanh hơn.

## 10. Kiểm chứng stage 3: $unwind

Dùng:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 3))
  .forEach(printjson);
~~~

`$unwind: "$items"` tạo **một result document cho mỗi phần tử mảng items**. Đơn O01 có hai item nên trở thành hai document logic:

~~~javascript
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: { sku: "KB", quantity: 2, unitPrice: 100 }
}
{
  orderId: "O01",
  customerId: "C01",
  region: "north",
  items: { sku: "MS", quantity: 1, unitPrice: 50 }
}
~~~

Số dòng theo từng đơn:

| Đơn PAID | Số phần tử items | Dòng sau $unwind mặc định |
| --- | ---: | ---: |
| O01 | 2 | 2 |
| O02 | 2 | 2 |
| O04 | 1 | 1 |
| O05 | 2 | 2 |
| O07 | 3 | 3 |
| O08 | 0 | 0 |
| O09 | Thiếu field | 0 |
| **Tổng** | **10 phần tử có thật** | **10 dòng** |

Vì vậy:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 3),
  { $count: "rowsAfterUnwind" }
]).toArray();
// [{ rowsAfterUnwind: 10 }]
~~~

**Tại sao cần kiểm chứng ở bước này?**

Nếu vô tình đếm `$sum: 1` sau `$unwind`, bạn đang đếm **dòng item**, không phải **đơn hàng**. Một đơn có ba item có thể được đếm ba lần. Kết quả `10` ở bước này không được gọi là “10 đơn PAID”.

### 10.1. preserveNullAndEmptyArrays thay đổi cardinality

Nếu nghiệp vụ muốn giữ cả O08 và O09:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $unwind: {
      path: "$items",
      preserveNullAndEmptyArrays: true
    }
  },
  {
    $project: {
      _id: 1,
      items: 1
    }
  }
]).toArray();
~~~

Khi `preserveNullAndEmptyArrays: true`, những document có mảng rỗng, null hoặc thiếu field vẫn có thể được giữ trong output; với bộ dữ liệu này tổng số document sau unwind sẽ là **12** (10 dòng item và hai document O08/O09).

Nếu tiếp tục tính `$multiply` hoặc `$group` theo `items.sku`, phải xử lý hai document không có item hợp lệ. **Không bật preserve chỉ để giữ số lượng và kỳ vọng mọi phép tổng hợp tự đúng**.

### 10.2. includeArrayIndex để xác định thứ tự phần tử

Trong trường hợp cần đối chiếu phần tử thứ mấy đã tạo dòng:

~~~javascript
lab.orders.aggregate([
  { $match: { _id: "O01" } },
  {
    $unwind: {
      path: "$items",
      includeArrayIndex: "itemIndex"
    }
  },
  {
    $project: {
      _id: 1,
      itemIndex: 1,
      items: 1
    }
  }
]);
~~~

O01 sẽ cho hai dòng với `itemIndex` là 0 và 1. Đây là công cụ rất hữu ích khi nghi có phần tử mảng sai định dạng hoặc đang nghiên cứu kết quả được tạo bởi `$unwind`.

## 11. Kiểm chứng stage 4: $set và biểu thức tính toán

Stage `$set` thêm trường `lineTotal`:

~~~javascript
{
  $set: {
    lineTotal: {
      $multiply: ["$items.quantity", "$items.unitPrice"]
    }
  }
}
~~~

Đọc prefix đến stage 4:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 4))
  .forEach(doc => {
    print(doc.orderId + " | " +
          doc.items.sku + " | " +
          doc.items.quantity + " x " +
          doc.items.unitPrice + " = " +
          doc.lineTotal);
  });
~~~

Một số dòng có thể được in:

~~~text
O01 | KB  | 2 x 100 = 200
O01 | MS  | 1 x 50  = 50
O02 | KB  | 1 x 100 = 100
O02 | PAD | 2 x 30  = 60
O04 | MS  | 3 x 50  = 150
O05 | MS  | 2 x 50  = 100
O05 | PAD | 1 x 30  = 30
O07 | KB  | 1 x 100 = 100
O07 | MS  | 1 x 50  = 50
O07 | PAD | 1 x 30  = 30
~~~

Stage này giữ nguyên cardinality: **10 document vào, 10 document ra**.

Kiểm chứng giá trị bằng một pipeline đối chiếu:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 4),
  {
    $group: {
      _id: null,
      lines: { $sum: 1 },
      quantity: { $sum: "$items.quantity" },
      revenue: { $sum: "$lineTotal" }
    }
  }
]).toArray();
// [{ _id: null, lines: 10, quantity: 15, revenue: 870 }]
~~~

Trong ứng dụng thực, hãy kiểm tra:

- `quantity` và `unitPrice` là kiểu số BSON hay string?
- Giá trị null/missing có thể đi vào phép `$multiply` không?
- Kiểu kết quả phải là int32, int64, double hay Decimal128?
- Phép làm tròn và đơn vị tiền tệ có được quy định thống nhất không?

Với `$sum`, các giá trị không phải số trong nhiều ngữ cảnh sẽ bị bỏ qua khi cộng; điều đó có thể làm **doanh thu thấp đi một cách âm thầm** nếu dữ liệu đầu vào không được chuẩn hóa. Không nên xem tổng bằng 0 là bằng chứng mọi item đều có giá trị 0.

## 12. Kiểm chứng stage 5: $group

Stage `$group` nhận 10 dòng item và nhóm theo SKU:

~~~javascript
{
  $group: {
    _id: "$items.sku",
    totalQuantity: { $sum: "$items.quantity" },
    totalRevenue: { $sum: "$lineTotal" },
    lineCount: { $sum: 1 }
  }
}
~~~

Chạy prefix:

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 5))
  .toArray();
~~~

Giá trị dự kiến, **chưa có thứ tự xác định**:

~~~javascript
[
  { _id: "KB", totalQuantity: 4, totalRevenue: 400, lineCount: 3 },
  { _id: "MS", totalQuantity: 7, totalRevenue: 350, lineCount: 4 },
  { _id: "PAD", totalQuantity: 4, totalRevenue: 120, lineCount: 3 }
]
~~~

**Không tin vào thứ tự hiển thị của `$group`.** Stage này không bảo đảm thứ tự đầu ra. Mảng minh họa phía trên chỉ để đối chiếu **tập giá trị**, không phải thứ tự mà server phải trả.

### 12.1. Kiểm chứng số nhóm

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  { $count: "skuCount" }
]).toArray();
// [{ skuCount: 3 }]
~~~

Từ **10 dòng item**, sau `$group` có **3 nhóm SKU**. Việc giảm từ 10 xuống 3 là **chủ đích**, không phải mất document do lỗi.

### 12.2. Kiểm chứng tổng sau khi gộp

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  {
    $group: {
      _id: null,
      grandRevenue: { $sum: "$totalRevenue" },
      grandQuantity: { $sum: "$totalQuantity" },
      grandLines: { $sum: "$lineCount" }
    }
  }
]).toArray();
// [{ _id: null, grandRevenue: 870, grandQuantity: 15, grandLines: 10 }]
~~~

Ba tổng này phải bằng tổng trước `$group` ở mục 11 nếu business rule là cộng đơn giản. Đây là một **invariant (bất biến kiểm tra)** rất hữu ích để phát hiện lỗi do thay đổi nhóm, điều kiện lọc hoặc nhân bản item.

### 12.3. Không nhầm đơn hàng với dòng item

Trong dữ liệu ví dụ:

- Có **7 đơn PAID**.
- Có **5 đơn PAID có item**.
- Có **10 dòng item**.
- Có **3 SKU**.

Nếu dashboard muốn hiển thị “số đơn hàng”, không được sử dụng `lineCount` rồi gắn nhãn `orderCount`. Muốn đếm đơn hàng duy nhất theo SKU, có thể dùng `$addToSet: "$orderId"` và tính số phần tử sau đó, nhưng đây là một quy tắc đo lường khác:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 4),
  {
    $group: {
      _id: "$items.sku",
      orderIds: { $addToSet: "$orderId" }
    }
  },
  {
    $project: {
      sku: "$_id",
      _id: 0,
      orderCount: { $size: "$orderIds" }
    }
  },
  { $sort: { sku: 1 } }
]);
~~~

Với dữ liệu mẫu, mỗi dòng item của cùng SKU xuất hiện tối đa một lần trong mỗi đơn; nếu một đơn có hai item cùng SKU, `lineCount` sẽ khác số đơn duy nhất, còn `$addToSet` giúp loại trùng ID.

## 13. Kiểm chứng stage 6–8: projection, sort và limit

### 13.1. Stage 6: đặt tên trường output

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 6))
  .toArray();
~~~

Stage `$project`:

~~~javascript
{
  $project: {
    _id: 0,
    sku: "$_id",
    totalQuantity: 1,
    totalRevenue: 1,
    lineCount: 1
  }
}
~~~

Sau stage này, kết quả phải có:

- `sku` là mã SKU, thay cho khóa nhóm `_id`.
- `totalQuantity`, `totalRevenue` và `lineCount` được giữ.
- Không còn `_id` trong response.

Vẫn có **3 document**, nhưng hình dạng đã đổi. Khi client báo thiếu `sku` hoặc có field `_id` không mong muốn, đây là stage đầu tiên cần kiểm tra.

### 13.2. Stage 7: sort phải có quy tắc phá hòa nếu cần

~~~javascript
lab.orders.aggregate(pipeline.slice(0, 7))
  .toArray();
~~~

Kết quả theo thứ tự doanh thu giảm dần:

~~~text
KB  400
MS  350
PAD 120
~~~

Stage:

~~~javascript
{
  $sort: {
    totalRevenue: -1,
    sku: 1
  }
}
~~~

Trường `sku` là khóa sort phụ để có thứ tự ổn định khi doanh thu bằng nhau. Nếu bỏ khóa phụ mà nhiều SKU cùng doanh thu, thứ tự giữa các nhóm bằng nhau không được bảo đảm. Điều này đặc biệt quan trọng khi phía sau có `$limit` hoặc phân trang.

### 13.3. Stage 8: limit chỉ giữ hai nhóm đầu

~~~javascript
lab.orders.aggregate(pipeline).toArray();
~~~

Kết quả chỉ còn **KB** và **MS**. Khi kiểm tra giá trị `870` của toàn bộ dữ liệu, **không được lấy tổng sau `$limit: 2`** rồi kết luận doanh thu toàn bộ chỉ là 750. Stage `$limit` cố ý loại PAD khỏi danh sách top 2.

Bảng tóm tắt:

| Stage | Tên stage | Document đầu ra trong lab | Ý nghĩa chính |
| ---: | --- | ---: | --- |
| Nguồn | `orders` | 9 | Tất cả đơn |
| 1 | `$match` | 7 | Giữ đơn PAID |
| 2 | `$project` | 7 | Đổi hình dạng |
| 3 | `$unwind` | 10 | Mở mảng item thành dòng |
| 4 | `$set` | 10 | Thêm lineTotal |
| 5 | `$group` | 3 | Gộp SKU |
| 6 | `$project` | 3 | Đổi tên trường |
| 7 | `$sort` | 3 | Sắp thứ tự |
| 8 | `$limit` | 2 | Lấy top 2 |

**Quy tắc đọc bảng:** những stage có thể thay đổi cardinality ở pipeline này là `$match`, `$unwind`, `$group` và `$limit`. `$project`/`$set`/`$sort` không tự tạo hoặc bỏ document trong ví dụ, nhưng vẫn có thể thay đổi dữ liệu được hiển thị hay thứ tự kết quả.

## 14. Hàm đo số document ở từng prefix

Khi muốn kiểm chứng **số lượng đầy đủ**, không nên dùng preview có `$limit` rồi đếm số dòng in ra. Hãy chạy tiền tố thật và thêm `$count`:

~~~javascript
function countAfterStage(pipeline, stageCount) {
  if (!Number.isInteger(stageCount) ||
      stageCount < 1 || stageCount > pipeline.length) {
    throw new Error("stageCount không hợp lệ");
  }

  var prefix = pipeline.slice(0, stageCount);

  var result = lab.orders.aggregate([
    ...prefix,
    { $count: "n" }
  ]).toArray();

  // $count trên input rỗng trả về không có document.
  return result.length === 0 ? 0 : result[0].n;
}

for (var i = 1; i <= pipeline.length; i++) {
  print("Sau stage " + i + ": " +
        countAfterStage(pipeline, i));
}
~~~

Kết quả trên dữ liệu không đổi:

~~~text
Sau stage 1: 7
Sau stage 2: 7
Sau stage 3: 10
Sau stage 4: 10
Sau stage 5: 3
Sau stage 6: 3
Sau stage 7: 3
Sau stage 8: 2
~~~

**Cảnh báo vận hành:** mỗi lần gọi `countAfterStage()` **chạy lại pipeline từ nguồn**, không tận dụng kết quả chạy trước. Với collection lớn hoặc pipeline nhiều `$lookup`, `$group`, `$sort`, việc đếm từng prefix có thể rất tốn tài nguyên. Chỉ dùng trong lab, staging, trên tập mẫu được chọn từ trước hoặc khi đã có kế hoạch quan sát tải.

Không thêm `$count` sau stage `$out` hoặc `$merge` để “đo số dòng” bằng cùng chiến lược; đây là những pipeline ghi dữ liệu và có quy tắc cú pháp riêng.

### 14.1. Từng stage có thể làm tổng tăng, giảm hoặc giữ nguyên

Nhận diện nhanh một số stage phổ biến:

| Stage | Cardinality thường gặp |
| --- | --- |
| `$match` | Giữ lại hoặc giảm |
| `$project` / `$set` / `$unset` | Giữ nguyên |
| `$unwind` | Có thể tăng, giảm hoặc giữ nguyên |
| `$group` | Thường giảm thành số nhóm; không tăng vượt số đầu vào với dữ liệu thông thường |
| `$sort` | Giữ nguyên |
| `$skip` / `$limit` | Giảm hoặc giữ nguyên |
| `$lookup` | Thường giữ số document cấp ngoài nhưng bổ sung mảng kết quả join |
| `$facet` | Có thể tạo một output document chứa nhiều mảng |
| `$count` | Có 1 document nếu đầu vào khác rỗng; nếu rỗng, không có output document |

Bảng là hướng dẫn **ngữ nghĩa điển hình**, không thay thế việc quan sát dữ liệu và các tùy chọn của stage. Ví dụ `$lookup` kèm `$unwind` có thể nhân bản document sau join; `$unwind` với `preserveNullAndEmptyArrays` thay đổi hành vi đối với mảng rỗng.

## 15. Kiểm tra loại BSON và dữ liệu thiếu ở giữa pipeline

Những sai lệch khó phát hiện nhất đôi khi không phải số dòng, mà là **kiểu dữ liệu khác mong đợi**.

### 15.1. Dùng $type để kiểm tra cấu trúc trung gian

Ví dụ sau `$unwind`:

~~~javascript
lab.orders.aggregate([
  ...pipeline.slice(0, 3),
  {
    $project: {
      _id: 0,
      orderId: 1,
      sku: "$items.sku",
      quantityType: { $type: "$items.quantity" },
      priceType: { $type: "$items.unitPrice" }
    }
  }
]);
~~~

Kết quả cho biết MongoDB đang thấy giá trị dưới dạng `int`, `long`, `double`, `decimal`, `string` hoặc kiểu khác. Đừng suy luận từ việc `mongosh` in ra `100` rằng chắc chắn BSON type là int32: tùy cách insert/driver, kiểu số lưu trữ có thể khác.

### 15.2. Tìm item thiếu field bằng pipeline kiểm tra riêng

Một chiến lược là lọc những dòng item không có một trong các trường cần cho phép nhân:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $match: {
      $or: [
        { "items.quantity": { $exists: false } },
        { "items.unitPrice": { $exists: false } },
        { "items.sku": { $exists: false } }
      ]
    }
  },
  {
    $project: {
      _id: 1,
      items: 1
    }
  }
]);
~~~

Với dữ liệu lab, query này không trả document nào; nhưng trên dữ liệu thật nó giúp khoanh vùng các dòng làm tổng doanh thu sai.

Tương tự, có thể kiểm tra các giá trị không phải số bằng `$type` hoặc `$isNumber` trong aggregation expression phù hợp phiên bản. Trước khi chuẩn hóa/convert, cần xác định dữ liệu nào là lỗi cần chặn, dữ liệu nào có thể chuyển đổi an toàn.

### 15.3. Empty và missing không giống null hoặc 0

O08 có mảng rỗng; O09 thiếu `items`. `$unwind` mặc định loại cả hai document khỏi kết quả. Nhưng nếu phép tính cần biểu diễn số đơn “không có item” hoặc thống kê lỗi dữ liệu, bạn nên xây một **nhánh kiểm tra riêng** trước `$unwind`:

~~~javascript
lab.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $project: {
      _id: 1,
      itemsType: { $type: "$items" },
      itemsCount: {
        $cond: [
          { $isArray: "$items" },
          { $size: "$items" },
          null
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Tài liệu O08 có `itemsType` là `array` và `itemsCount` bằng 0; O09 có `itemsType` là `missing` và `itemsCount` là null. Hai trạng thái này có thể cần xử lý khác nhau trong nghiệp vụ, không nên âm thầm coi là tương đương nếu schema yêu cầu mọi đơn phải có mảng items.

## 16. Explain aggregation: kiểm tra kế hoạch thực thi, không phải kết quả nghiệp vụ

Các prefix chạy thật dùng để kiểm tra **ngữ nghĩa output**; `explain()` giúp phân tích **MongoDB thực thi pipeline như thế nào**.

### 16.1. Chạy explain trong mongosh

~~~javascript
lab.orders.explain("queryPlanner").aggregate(pipeline);

lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Hai verbosity được dùng phổ biến:

- `queryPlanner`: kế hoạch truy vấn do optimizer lựa chọn.
- `executionStats`: thông tin về thực thi theo cơ chế explain và các chỉ số thực hiện.

Kết quả `explain` là **tài liệu chẩn đoán**, không phải mảng SKU doanh thu để dùng trong báo cáo ứng dụng.

### 16.2. Xem index scan và document scan

Tạo index hỗ trợ điều kiện `status`:

~~~javascript
lab.orders.createIndex(
  { status: 1 },
  { name: "ix_status" }
);

lab.orders.explain("executionStats").aggregate(pipeline);
~~~

Các dấu hiệu thường cần xem:

| Dấu hiệu | Ý nghĩa |
| --- | --- |
| `IXSCAN` | Duyệt index |
| `COLLSCAN` | Quét collection |
| `FETCH` | Truy xuất document nguồn |
| `indexBounds` | Khoảng index key được dùng |
| `totalKeysExamined` | Số lượt key được xét |
| `totalDocsExamined` | Số lượt document được xét |
| `nReturned` | Số document đầu ra tại cấp/stage báo cáo |
| `usedDisk`, `spills` hoặc counters tương tự | Dấu hiệu stage sử dụng đĩa tạm, tùy phiên bản |

Với bộ dữ liệu chỉ có 9 đơn, server **có thể chọn `COLLSCAN` dù đã tạo index** vì quét collection nhỏ thường rẻ hơn duyệt index và truy cập document. Không nên xem đó là bằng chứng rằng index vô dụng trên dữ liệu sản xuất.

### 16.3. Explain có thể không còn đúng một stage-một-stage

MongoDB có **aggregation optimizer**. Tùy phiên bản và hình dạng pipeline, server có thể:

- Đẩy `$match` lên trước những phép biến đổi mà không làm đổi kết quả.
- Hợp nhất hoặc tách các stage.
- Đẩy một số phép toán xuống query execution engine.
- Tối ưu `$sort + $limit`.
- Loại bỏ field trung gian không cần thiết.
- Hiển thị plan bằng cấu trúc khác khi dùng **slot-based query execution engine**.

Do đó, **không thể luôn đối chiếu stage thứ 3 trong source với dòng thứ 3 trong explain**. Nếu bạn cần chứng minh một stage làm gì về mặt logic, hãy **chạy prefix** và so sánh kết quả. Nếu muốn biết stage nào tốn CPU/I/O hoặc có index, hãy dùng **explain/metrics**.

### 16.4. Explain không phải cách tạo mẫu dữ liệu

Đoạn này sai về ý định:

~~~javascript
// SAI về mục đích: explain trả plan, không trả document báo cáo.
var rows = lab.orders.explain("executionStats")
  .aggregate(pipeline);
~~~

Nếu muốn lấy kết quả:

~~~javascript
var rows = lab.orders.aggregate(pipeline).toArray();
~~~

Nếu muốn quan sát stage đầu của pipeline:

~~~javascript
var stage1Rows = lab.orders.aggregate(
  pipeline.slice(0, 1)
).toArray();
~~~

**Cẩn trọng với stage ghi:** `$out`/`$merge` không được xem là lệnh đọc vô hại khi chạy thật. Explain có quy tắc thực thi và hạn chế riêng; không dùng explain như cách kiểm chứng kết quả đã được ghi, cũng không tự động chạy mọi prefix của pipeline ghi vào dữ liệu sản xuất.

## 17. Khi pipeline lớn: memory, allowDiskUse và thời gian chạy

### 17.1. Stage streaming và blocking

Một số stage như `$match` hoặc `$project` thường có thể xử lý lần lượt các document. Ngược lại:

- `$sort` có thể cần giữ nhiều document để xác định thứ tự.
- `$group` cần duy trì trạng thái của các nhóm.
- Một số stage như `$setWindowFields` hoặc thao tác join phức tạp có thể cần bộ nhớ đáng kể.

Điều này có nghĩa: **cursor đọc từng phần tử không đồng nghĩa server chỉ giữ một phần tử trong RAM**. Một pipeline có blocking stage có thể tốn nhiều bộ nhớ trước khi cursor trả về document đầu tiên.

### 17.2. allowDiskUse

Trong các môi trường/phiên bản hỗ trợ:

~~~javascript
var c = lab.orders.aggregate(
  pipeline,
  {
    allowDiskUse: true,
    maxTimeMS: 30000
  }
);

c.forEach(printjson);
~~~

`allowDiskUse` cho phép những stage đủ điều kiện ghi dữ liệu tạm ra đĩa khi cần vượt giới hạn bộ nhớ dành cho stage. Từ MongoDB 6.0, mặc định liên quan đến việc dùng đĩa còn chịu cấu hình `allowDiskUseByDefault`. Khả năng spill phụ thuộc **loại stage và phiên bản**; `allowDiskUse: true` không giúp mọi phép biến đổi tránh được giới hạn bộ nhớ.

`maxTimeMS` đặt ngân sách thời gian xử lý theo cơ chế timeout của MongoDB; một thao tác trên môi trường nhiều dữ liệu có thể bị ngắt khi vượt ngưỡng. Không nên chọn thời gian thấp một cách tùy tiện trong production vì dễ làm ứng dụng phát sinh lỗi gián đoạn.

### 17.3. Giới hạn output và kích thước document

- Kết quả aggregation có thể gồm nhiều document và được đọc qua cursor theo batch.
- **Mỗi document kết quả** vẫn phải tuân theo giới hạn kích thước BSON của MongoDB.
- Nếu `$group` tạo một document với mảng `$push` quá lớn, có thể chạm giới hạn kích thước document dù tổng số result document ít.
- `$limit` sau `$group` không làm giảm kích thước của document `$group` đã tạo.
- `toArray()` ở client có thể gây thiếu RAM dù server xử lý pipeline thành công.

Với báo cáo lớn, cân nhắc giảm các trường trả về, phân vùng theo ngày/tenant, giới hạn số nhóm, xuất streaming, hoặc materialize kết quả khi phù hợp.

### 17.4. Kiểm chứng trên production cần có giới hạn

Các tiện ích kiểm tra từng stage trong bài có thể **chạy lại toàn bộ pipeline nhiều lần**. Trong production, hãy cân nhắc:

1. Lọc một tập con có ý nghĩa bằng `tenantId`/khoảng ngày.
2. Dùng `maxTimeMS` phù hợp.
3. Không in toàn bộ result set lớn.
4. Không dùng `toArray()` vô giới hạn.
5. Đọc `explain("queryPlanner")` hoặc theo dõi metric trước khi dùng nhiều lần `executionStats`.
6. Không chạy trực tiếp pipeline có `$out`/`$merge` chỉ để debug.
7. Lưu số liệu kỳ vọng hoặc fixture kiểm thử trong môi trường riêng.

## 18. Đọc aggregation cursor trong Java Driver

Với **MongoDB Java Sync Driver**, `collection.aggregate(pipeline)` trả về một đối tượng kiểu `AggregateIterable<T>`. Nó có thể được duyệt bằng `MongoCursor<T>`. Ví dụ:

~~~java
import com.mongodb.client.AggregateIterable;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

import static com.mongodb.client.model.Aggregates.*;
import static com.mongodb.client.model.Accumulators.*;
import static com.mongodb.client.model.Filters.*;

public class AggregateCursorExample {

    public static void readPaidOrders(MongoCollection<Document> orders) {
        List<org.bson.conversions.Bson> stages = Arrays.asList(
            match(eq("status", "PAID")),
            group("$customerId", sum("orderCount", 1))
        );

        AggregateIterable<Document> iterable = orders
            .aggregate(stages)
            .batchSize(50)
            .allowDiskUse(true);

        try (MongoCursor<Document> cursor = iterable.iterator()) {
            while (cursor.hasNext()) {
                Document row = cursor.next();
                System.out.println(row.toJson());
            }
        }
    }
}
~~~

Ý nghĩa:

- `AggregateIterable` là cấu hình và khả năng duyệt kết quả aggregation, **không phải List**.
- `batchSize(50)` điều chỉnh batch khi lấy kết quả.
- `try-with-resources` giúp đóng `MongoCursor` kể cả khi lỗi.
- `cursor.hasNext()`/`cursor.next()` đọc tuần tự, không buộc phải giữ toàn bộ output.

Ví dụ Java nhóm số đơn PAID theo khách, **khác** pipeline doanh thu theo SKU của bài lab. Với tập dữ liệu hiện có, nó tạo ba? Thực tế các khách có đơn PAID là C01, C02, C03 và C05: **bốn nhóm**, gồm C01=2, C02=2, C03=2, C05=1. Kết quả từ `group()` không có thứ tự mặc định, cần thêm `sort` nếu muốn trình bày ổn định.

### 18.1. Khi nào không nên dùng into(new ArrayList)?

Java Driver hỗ trợ gom kết quả aggregation vào collection client thông qua API lặp. Ví dụ:

~~~java
List<Document> allRows = orders
    .aggregate(stages)
    .into(new java.util.ArrayList<>());
~~~

Cách này dễ dùng cho **báo cáo nhỏ**. Nếu kết quả lớn, nó có cùng vấn đề như `toArray()` trong `mongosh`: có thể giữ quá nhiều document trong RAM. Khi xuất CSV/NDJSON hoặc tích hợp stream, hãy tiêu thụ tuần tự theo cursor.

## 19. Đọc cursor trong MongoDB Node.js Driver

Với **Node.js MongoDB Driver**, `collection.aggregate(pipeline)` trả về `AggregationCursor`; API driver dùng nhiều thao tác **bất đồng bộ**:

~~~javascript
// Ví dụ ứng dụng Node.js, không chạy trong mongosh.
// Giả định orders là MongoDB collection từ Node.js Driver.
async function printAggregation(orders, pipeline) {
  const cursor = orders.aggregate(pipeline, {
    batchSize: 50,
    allowDiskUse: true
  });

  try {
    for await (const doc of cursor) {
      console.log(doc);
    }
  } finally {
    await cursor.close();
  }
}
~~~

Ở đây:

- `for await...of` đọc bất đồng bộ từng document.
- Cursor không cần được chuyển toàn bộ thành mảng.
- `finally` đảm bảo giải phóng tài nguyên khi vòng lặp bị ngắt do lỗi hay kết thúc sớm.
- Nếu đọc đồng thời cùng một cursor bằng nhiều luồng logic độc lập, có thể gây trạng thái không đoán được; nên dùng một consumer hoặc tạo cursor riêng.

**Khác biệt môi trường:** `mongosh` cung cấp các thao tác đồng bộ tiện lợi cho ví dụ học tập, trong khi Node.js Driver sử dụng Promise/async iterator theo API của nó. Không chép `while (cursor.hasNext())` từ mongosh sang Node.js Driver rồi bỏ `await`.

### 19.1. Trường hợp cần mảng nhỏ

~~~javascript
const cursor = orders.aggregate(pipeline);
const rows = await cursor.toArray();
console.log(rows);
~~~

Chỉ làm khi đã xác định kết quả có kích thước đủ nhỏ. Nếu muốn dùng cursor ở request API và trả nhiều trang, cần thiết kế pagination có thứ tự rõ ràng hoặc logic nhận batch phù hợp, không biến toàn bộ export thành một response JSON rất lớn.

## 20. Cách thiết kế kiểm chứng trong dự án thật

Một tập kiểm thử aggregation tốt không chỉ so sánh tổng cuối cùng, mà còn kiểm tra các **bất biến theo stage**.

### 20.1. Fixture nhỏ nhưng có trường hợp biên

Bộ dữ liệu lab cố tình có:

- Document bị `$match` loại.
- Document có nhiều phần tử mảng.
- Document có mảng rỗng.
- Document thiếu hẳn mảng.
- Nhiều SKU cùng xuất hiện ở nhiều đơn.
- Một SKU có doanh thu thấp hơn nhưng vẫn phải xuất hiện trước `$limit`.

Dữ liệu kiểm thử thực tế nên bổ sung:

- Giá trị số âm/0/null.
- Trường sai BSON type.
- Mảng lồng nhau.
- Document trùng mã trong một đơn.
- Giá trị rất lớn hoặc số thập phân chính xác.
- Trạng thái mới chưa có trong enum.
- Giá trị ngày ở múi giờ khác.

### 20.2. Các invariant đề xuất

| Vị trí | Bất biến cần kiểm tra |
| --- | --- |
| Sau `$match` | Mọi document đều có `status = "PAID"` |
| Sau `$project` | Có đủ `orderId`, `region`, `items` cần cho stage sau |
| Sau `$unwind` | Mỗi output đại diện cho một item; số dòng bằng tổng số phần tử mảng của đơn phù hợp |
| Sau `$set` | `lineTotal = quantity × unitPrice` với kiểu số hợp lệ |
| Sau `$group` | Tổng theo SKU cộng lại bằng tổng `lineTotal` trước nhóm |
| Sau `$project` cuối | Đúng tên và kiểu các field trong API |
| Sau `$sort` | Doanh thu không tăng khi đi từ đầu đến cuối; tie-breaker nhất quán |
| Sau `$limit` | Số kết quả không vượt giới hạn; top N đúng theo sort |

### 20.3. So sánh hai cách tính độc lập

Một nguyên tắc hữu ích là tính tổng ở hai tầng khác nhau:

~~~javascript
// Cách A: tính từ từng item trước khi group SKU.
var totalA = lab.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: null,
      sum: {
        $sum: {
          $multiply: [
            "$items.quantity",
            "$items.unitPrice"
          ]
        }
      }
    }
  }
]).toArray();

// Cách B: tính từ các nhóm SKU đã group.
var totalB = lab.orders.aggregate([
  ...pipeline.slice(0, 5),
  {
    $group: {
      _id: null,
      sum: { $sum: "$totalRevenue" }
    }
  }
]).toArray();

printjson({ totalA, totalB });
// Cả hai sum phải bằng 870 trên dữ liệu ban đầu.
~~~

Nếu hai cách khác nhau, tập trung tìm nguyên nhân ở các phép `$unwind`, `$multiply` và `$group` hoặc dữ liệu biến động giữa hai lần chạy.

**Lưu ý:** Hai pipeline đều có thể mắc cùng một lỗi nghiệp vụ nếu cùng sử dụng định nghĩa `quantity × unitPrice` sai; vì vậy cần thêm một số kết quả kỳ vọng tính bằng tay từ fixture.

## 21. Khác biệt giữa kiểm chứng logic và đo hiệu năng

Không nên trộn hai câu hỏi:

1. **Kết quả có đúng không?**
2. **Truy vấn có chạy tối ưu không?**

| Nhu cầu | Công cụ phù hợp | Điều cần tránh |
| --- | --- | --- |
| Xem output một stage | Chạy prefix + `toArray()` nhỏ hoặc `forEach()` | In toàn bộ dữ liệu production |
| Đếm input/output | Prefix + `$count` | Đếm sau `$limit` rồi suy ra tổng nguồn |
| Kiểm tra phép tính | `$project`/`$set` debug, invariant, fixture | Chỉ nhìn kết quả cuối rồi đoán |
| Kiểm tra field missing/type | `$type`, `$exists`, `$isArray` | Mặc định mọi document cùng schema |
| Kiểm tra index | `explain()` | Nghĩ rằng thấy `IXSCAN` nghĩa kết quả đúng |
| Kiểm tra memory/spill | Execution stats, profiler, server metrics | Chỉ xem số result document |
| Xem batch/client memory | `batchSize`, streaming, monitoring | `toArray()` trên tập rất lớn |
| Xác nhận tính ổn định | Sort có tie-breaker, chạy trên fixture | Tin vào thứ tự output của `$group` |

`explain()` giúp hiểu *cách server làm việc*, còn chạy pipeline từng prefix giúp hiểu *dữ liệu biến đổi ra sao*. Cần kết hợp cả hai, nhưng không dùng một công cụ thay thế công cụ kia.

## 22. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `cursor.toArray()` lần hai trả mảng rỗng | Cursor đã tiêu thụ hết | Gọi `aggregate()` để tạo cursor mới |
| `next()` không có phần tử | Đã hết cursor hoặc không có kết quả | Kiểm tra `hasNext()`/đóng cursor đúng cách |
| Client thiếu RAM | Gom toàn bộ output bằng `toArray()` | Streaming/đọc tuần tự, giới hạn output |
| Batch size 2 nhưng vẫn có 7 kết quả | Batch size không phải tổng limit | Dùng `$limit` khi muốn ít result document |
| `$group` trả số đơn “quá lớn” | `$unwind` biến một đơn thành nhiều dòng | Phân biệt item count, order count và distinct order |
| Không thấy O08/O09 sau unwind | Mảng rỗng/missing bị bỏ mặc định | Xem `preserveNullAndEmptyArrays` và nghiệp vụ |
| Sau `$project` mất field dùng ở stage sau | Projection loại bỏ field | Giữ field hoặc thay đổi thứ tự stage |
| Doanh thu sai nhưng số nhóm đúng | Sai phép `$multiply`, type hoặc dữ liệu rỗng | Kiểm tra stage tính `lineTotal` trước group |
| Tổng nhóm khác tổng dòng item | Lọc thêm, nhân bản, nhóm sai khóa, dữ liệu nguồn thay đổi | So sánh prefix và tổng invariant |
| `$group` trả nhóm theo thứ tự bất ngờ | `$group` không sắp xếp output | Thêm `$sort` rõ ràng |
| Top 2 có thứ tự thiếu ổn định | Sort không có khóa phụ khi các nhóm bằng nhau | Thêm tie-breaker |
| Thấy ít document trong preview nên tưởng ít dữ liệu | Đã thêm `$limit` vào prefix | Dùng `$count` trên prefix đầy đủ |
| `explain` không hiển thị stage như source | Optimizer gộp/đẩy/biến đổi stage | Phân biệt logical pipeline và physical plan |
| `explain` không trả các SKU | Explain chỉ trả tài liệu chẩn đoán | Dùng `aggregate()` để nhận dữ liệu nghiệp vụ |
| Cursor hết hạn khi người dùng chờ lâu | Server/session idle hoặc cursor đã đóng | Không giữ server cursor quá lâu giữa HTTP requests |
| Pipeline có `$merge` gây thay đổi dữ liệu khi debug | Chạy thật stage ghi | Tách pipeline đọc; không chạy prefix có side effect |
| Kết quả hai lần chạy khác nhau | Dữ liệu nguồn được cập nhật giữa hai lần | Dùng fixture ổn định hoặc cơ chế đọc nhất quán thích hợp |
| Stage sort/group dùng RAM lớn | Blocking stage, dữ liệu lớn | Tối ưu `$match`, index, phân vùng, allowDiskUse khi phù hợp |

## 23. Bài tập thực hành

### Bài 1 — Đọc cursor theo ba cách

Chạy pipeline `pipeline` ở mục 4, đọc kết quả bằng:

1. `toArray()`.
2. `forEach()`.
3. Vòng lặp `while (hasNext())` + `next()`.

Mỗi cách phải sử dụng **một cursor mới**. Giải thích sự khác nhau về bộ nhớ client và khả năng dừng sớm.

### Bài 2 — Quan sát cursor đã tiêu thụ

~~~javascript
var c = lab.orders.aggregate(pipeline);

printjson(c.next());
printjson(c.toArray());
printjson(c.toArray());
~~~

Tại sao lần `toArray()` thứ nhất chỉ còn một document, còn lần thứ hai trả mảng rỗng? Viết lại để lấy đầy đủ hai SKU mà không dùng cursor cũ.

### Bài 3 — Đếm cardinality ở từng stage

Dùng `countAfterStage(pipeline, i)` với `i` từ 1 đến 8. Điền bảng:

| Stage | Số document cần điền |
| --- | ---: |
| `$match` | ? |
| `$project` | ? |
| `$unwind` | ? |
| `$set` | ? |
| `$group` | ? |
| `$project` | ? |
| `$sort` | ? |
| `$limit` | ? |

Đáp án: **7, 7, 10, 10, 3, 3, 3, 2**. Giải thích stage nào làm tăng và stage nào làm giảm cardinality.

### Bài 4 — Đổi điều kiện $unwind

Thay `$unwind: "$items"` bằng:

~~~javascript
{
  $unwind: {
    path: "$items",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Dự đoán số document sau unwind rồi kiểm tra. Với dữ liệu lab, kết quả là **12**. Phân tích điều gì cần sửa nếu tiếp tục tính `lineTotal` cho những document không có item.

### Bài 5 — Kiểm chứng doanh thu của từng SKU

Dùng prefix đến `$group`, rồi so sánh:

~~~text
KB  -> qty 4, revenue 400, lineCount 3
MS  -> qty 7, revenue 350, lineCount 4
PAD -> qty 4, revenue 120, lineCount 3
~~~

Lấy tổng doanh thu nhóm và đối chiếu với tổng `lineTotal` trước `$group`; cả hai phải là **870**.

### Bài 6 — Cố tình tạo lỗi khi project

Thay stage `$project` đầu tiên bằng phiên bản **không giữ `items`**:

~~~javascript
{
  $project: {
    _id: 0,
    orderId: "$_id",
    region: 1
  }
}
~~~

Dự đoán kết quả tại stage `$unwind` và các stage sau. Vì sao stage `$group` không còn tạo ba nhóm SKU như trước? Sau đó khôi phục stage `$project` đúng.

### Bài 7 — Kiểm tra BSON type

Sử dụng `$type` để xem kiểu của `items.quantity`, `items.unitPrice` và `lineTotal` sau stage `$set`. Nếu một document có `unitPrice: "100"` thay vì số, bạn sẽ thiết kế quy tắc kiểm tra/loại dữ liệu như thế nào trước khi tính doanh thu?

### Bài 8 — Đọc explain và index

Tạo index `{ status: 1 }` trên `orders`. Chạy:

~~~javascript
lab.orders.explain("executionStats").aggregate(pipeline);
~~~

So sánh `IXSCAN`/`COLLSCAN` nếu có, cùng `totalDocsExamined`. Giải thích tại sao với 9 document optimizer có thể vẫn chọn `COLLSCAN`.

### Bài 9 — Tăng số nhóm kết quả

Đổi `$limit: 2` thành `$limit: 3`, chạy lại. Kết quả phải có cả SKU PAD với doanh thu 120. So sánh tổng doanh thu của top 2 (**750**) và cả 3 SKU (**870**) để giải thích vì sao không thể lấy top-N rồi coi là tổng toàn bộ.

### Bài 10 — Thiết kế pipeline kiểm chứng dữ liệu xấu

Tạo một document PAID có item thiếu `unitPrice` hoặc `quantity` dạng string trong **database lab**. Thiết kế một pipeline **đọc** để liệt kê những item không hợp lệ, kèm `orderId`, `sku`, giá trị và `$type` của từng field.

Không tự động đổi giá trị lỗi thành 0 nếu chưa có quyết định nghiệp vụ; làm như vậy có thể tạo báo cáo doanh thu sai nhưng vẫn chạy thành công.

### Bài 11 — Phân biệt cursor ứng dụng và cursor token

Một REST API cần phân trang lịch sử đơn hàng qua nhiều HTTP requests. Có nên giữ một aggregation cursor mở từ request đầu đến khi người dùng bấm trang thứ 20 sau vài phút? Hãy phân tích vòng đời session/cursor, giải pháp keyset pagination có thứ tự ổn định và cách tạo một aggregation query mới cho mỗi trang.

### Bài 12 — Viết kiểm thử tích hợp

Viết một test trên dataset cố định để xác minh:

- Sau `$match` có 7 đơn.
- Sau `$unwind` có 10 dòng.
- Sau `$group` có 3 SKU, tổng doanh thu 870.
- Sau `$sort` là KB, MS, PAD.
- Sau `$limit` có hai SKU đầu KB và MS.

Khi test thất bại, chạy prefix gần nhất để xác định stage đầu tiên làm kết quả khác kỳ vọng thay vì sửa toàn bộ pipeline theo phỏng đoán.

## 24. Tóm tắt các nguyên tắc cần ghi nhớ

Một aggregation pipeline tạo ra **chuỗi biến đổi logic**, còn aggregation cursor là **cách đọc kết quả** cuối cùng từ server. Việc có cursor không có nghĩa toàn bộ stage đã streaming; `$sort` và `$group` vẫn có thể cần bộ nhớ/đĩa để xử lý.

Các quy tắc then chốt:

1. **`aggregate()` trả cursor** trong `mongosh`; `toArray()` chỉ dành cho output nhỏ, còn `forEach()` và `hasNext()/next()` phù hợp xử lý tuần tự.
2. **Cursor là nguồn kết quả có trạng thái**: đọc một lần sẽ tiêu thụ phần tử, muốn đọc lại cần chạy aggregate mới.
3. **Batch size điều khiển số result document mỗi lần truyền**, không giới hạn tổng số result document; `$limit` mới giới hạn cardinality của pipeline.
4. **Kiểm chứng mỗi stage bằng prefix** để quan sát giá trị trung gian; thêm `$limit` ở cuối prefix chỉ để xem mẫu, không thay đổi luồng kiểm chứng đầy đủ.
5. **Đếm bằng prefix + `$count`** khi cần biết chính xác số document sau từng stage, nhưng chú ý chi phí chạy lại pipeline nhiều lần.
6. **Theo dõi cardinality và bất biến số học**: sau `$unwind` đếm dòng item, sau `$group` đếm nhóm, sau `$limit` chỉ còn top-N.
7. **Xem field và BSON type** trước các phép tính; các giá trị missing, null, string hoặc mảng rỗng có thể làm kết quả sai.
8. **`explain()` dùng để hiểu optimizer và hiệu năng**, không trả dữ liệu nghiệp vụ và không phản ánh bắt buộc thứ tự stage hệt như source.
9. **Không chạy tự động pipeline ghi dữ liệu khi debug**; `$out` và `$merge` phải được xử lý như các thao tác có tác dụng phụ.
10. **Trên dữ liệu lớn, kết hợp streaming cursor, filter sớm, index phù hợp, theo dõi memory/spill và giới hạn thời gian** để bảo đảm vận hành an toàn.

### Tài liệu MongoDB chính thức

- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — mô hình xử lý theo stage.
- [db.collection.aggregate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.aggregate/) — cú pháp, options, cursor và các stage ghi.
- [Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/) — optimizer và thay đổi kế hoạch thực thi.
- [$match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/), [$project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/), [$unwind](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/), [$group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/) — các stage trong ví dụ.
- [$sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/) và [$limit](https://www.mongodb.com/docs/manual/reference/operator/aggregation/limit/) — thứ tự và giới hạn kết quả.
- [$count](https://www.mongodb.com/docs/manual/reference/operator/aggregation/count/) — đếm các document được chuyển đến stage.
- [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — giới hạn bộ nhớ và lưu file tạm.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — executionStats và query planner.
- [MongoDB Cursors](https://www.mongodb.com/docs/manual/core/cursors/) — vòng đời cursor và batch.
- [MongoDB Java Driver: Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/) — `AggregateIterable` và Java cursor.
- [MongoDB Node.js Driver: Aggregation](https://www.mongodb.com/docs/drivers/node/current/aggregation/) — `AggregationCursor` và async iteration.
