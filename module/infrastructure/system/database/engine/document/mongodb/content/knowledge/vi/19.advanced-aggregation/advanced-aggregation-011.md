# Giới hạn pipeline, kích thước document và tràn bộ nhớ ra đĩa trong MongoDB

## 1. Vì sao aggregation có thể hết bộ nhớ dù chỉ trả vài dòng?

Aggregation pipeline là cơ chế xử lý dữ liệu mạnh của MongoDB. Một pipeline có thể lọc, tính toán, nhóm, join, sắp xếp, tạo báo cáo, phân trang và ghi dữ liệu tổng hợp. Tuy nhiên, khi tập dữ liệu lớn, câu hỏi không chỉ là **pipeline có cho ra kết quả đúng không**, mà còn là:

- Có bao nhiêu stage trong pipeline?
- Mỗi document đầu ra có vượt giới hạn BSON không?
- Stage nào cần giữ nhiều dữ liệu trong RAM, thay vì xử lý từng document theo luồng?
- Nếu một stage cần hơn ngân sách bộ nhớ, MongoDB sẽ lỗi hay **spill** dữ liệu tạm ra đĩa?
- `allowDiskUse: true` giải quyết được những giới hạn nào, và **không** giải quyết được giới hạn nào?
- `$facet`, `$group`, `$push`, `$sort` và `$lookup` có những rủi ro khác nhau ra sao?
- Làm thế nào tránh một pipeline chậm, tốn ổ đĩa hoặc gây áp lực lên cả cụm dữ liệu?

Bài này thuộc chương **Aggregation nâng cao** của module **Database Engine Document MongoDB**. Nội dung tập trung vào **giới hạn pipeline, kích thước document và tràn bộ nhớ ra đĩa**.

Sau khi học, bạn có thể:

1. Phân biệt giới hạn **16 MiB cho từng BSON document**, giới hạn **1.000 stage** và ngân sách **100 MB** thường áp dụng cho những stage aggregation cần dùng nhiều bộ nhớ.
2. Giải thích vì sao kết quả cursor gồm hàng triệu document không đồng nghĩa một document được phép lớn hơn 16 MiB.
3. Sử dụng `allowDiskUse` cho các stage hỗ trợ tràn dữ liệu tạm ra đĩa, đồng thời hiểu `allowDiskUseByDefault` từ MongoDB 6.0.
4. Nhận diện giới hạn đặc biệt của `$facet` và `$push`: những trường hợp có thể lỗi **ngay cả khi bật disk spill**.
5. Thiết kế `$match`, `$sort`, `$limit`, `$group` và `$project` để giảm dữ liệu phải giữ trong RAM.
6. Đọc `explain("executionStats")`, dấu hiệu `usedDisk` trong profiler/diagnostic log và các thông số spill khi phiên bản server cung cấp.
7. Viết pipeline mongosh và Java Driver với cấu hình thời gian, bộ nhớ và output an toàn.

**Nguyên tắc tổng quát:** `allowDiskUse` là một cơ chế xử lý khi thiếu bộ nhớ của **một số stage hỗ trợ**, không phải công tắc bỏ mọi giới hạn của MongoDB. Đặc biệt, nó không hợp thức hóa một BSON document đầu ra vượt 16 MiB và không làm `$facet` tự tràn ra đĩa.

## 2. Bản đồ các giới hạn cần phân biệt

Các giới hạn tồn tại ở những tầng khác nhau:

| Phạm vi | Giới hạn/quy tắc thường gặp | Ý nghĩa |
|---|---|---|
| **Một BSON document trả về hoặc được lưu** | **16 MiB** | Một document đơn lẻ không được quá kích thước BSON tối đa |
| **Một pipeline aggregation** | **1.000 stage** | Vượt số stage trước hoặc sau bước phân tích/canonicalization có thể bị từ chối |
| **Stage sử dụng nhiều RAM** | Mốc **100 MB** đối với những stage thuộc cơ chế hạn chế bộ nhớ/spill | Stage được hỗ trợ có thể spill ra đĩa nếu được phép; nếu không có thể lỗi |
| **`$facet`** | Document do stage xây dựng tối đa **100 MB**, **không spill** | Bật `allowDiskUse` không khắc phục giới hạn này |
| **`$facet` output cuối** | Vẫn chịu giới hạn **16 MiB/document** | Facet có thể qua ngưỡng bộ nhớ riêng nhưng thất bại khi trả result quá lớn |
| **Accumulator `$push`** | Có giới hạn bộ nhớ accumulator riêng, mặc định cỡ **100 MB**, **không spill** | Dồn toàn bộ danh sách vào một array có thể lỗi dù `allowDiskUse:true` |
| **Toàn query operation** | Từ **MongoDB 9.0** có thêm giới hạn bộ nhớ tổng của operation | Cần xem phiên bản và tham số cấu hình cụ thể của server |
| **Ổ đĩa tạm, thời gian, I/O** | Phụ thuộc triển khai/giới hạn vận hành | Có thể hết ổ đĩa hoặc timeout dù stage hỗ trợ spill |

**Lưu ý về phiên bản:** MongoDB có thể thay đổi thông số vận hành giữa các phiên bản. Phần dưới trình bày cơ chế phổ biến và đánh dấu những mốc phiên bản quan trọng. Khi triển khai trên cụm thật, luôn đối chiếu phiên bản MongoDB Server, driver, Atlas tier và các tham số đã được cấu hình.

### 2.1. MiB khác MB như thế nào?

- `1 MiB = 1.048.576 byte`.
- `16 MiB = 16.777.216 byte`.
- Các tài liệu MongoDB thường gọi mốc stage memory là **100 megabytes**, trong khi kích thước BSON được ghi rõ là **16 mebibytes (MiB)**.

Không nên dùng công thức 16.000.000 byte rồi cho rằng đó chính là 16 MiB, hoặc quy mọi giới hạn thành một đơn vị duy nhất mà không xem định nghĩa nguồn.

### 2.2. Dòng chảy dữ liệu

~~~text
Document lưu trên đĩa
        |
        |  Một document BSON hợp lệ <= 16 MiB
        v
Aggregation pipeline
        |
        +--> $match / $project / $set: thường biến đổi/lọc từng document
        |
        +--> $sort / $group: có thể phải giữ nhiều dữ liệu trong RAM
        |            |
        |            +--> Stage hỗ trợ spill + disk use được phép?
        |                      |
        |                  Có: dữ liệu tạm ra đĩa
        |                  Không: có thể lỗi giới hạn bộ nhớ
        |
        +--> $facet: giới hạn riêng, không spill
        |
        v
Cursor hoặc stage ghi
        |
        |  Mỗi document kết quả vẫn <= 16 MiB
        v
Client hoặc collection đích
~~~

Pipeline có thể xử lý **rất nhiều document**. Ngưỡng BSON 16 MiB áp dụng cho **từng document** trong result, không phải tổng byte của tất cả document qua một cursor.

## 3. Chuẩn bị bộ dữ liệu thực hành

Ví dụ dùng `mongosh` trên database riêng. Không chạy các lệnh tạo dữ liệu mẫu trong collection sản xuất.

~~~javascript
use aggregation_limits_lab
~~~

Tạo 24 document đơn hàng giả lập:

~~~javascript
const sampleOrders = [];

for (let i = 1; i <= 24; i++) {
  const id = "ord-" + String(i).padStart(3, "0");

  const status =
    i % 3 === 0 ? "PAID" :
    i % 3 === 1 ? "NEW" :
    "SHIPPED";

  sampleOrders.push({
    _id: id,
    tenantId: i <= 18 ? "tenant-A" : "tenant-B",
    status: status,
    category: ["book", "pen", "bag"][i % 3],
    amount: NumberDecimal(String(i * 10) + ".00"),
    createdAt: new Date(Date.UTC(2026, 9, i + 1, 8, 0, 0)),
    items: [
      {
        sku: "SKU-" + String(i).padStart(3, "0"),
        qty: NumberInt(2),
        price: NumberDecimal("5.00")
      },
      {
        sku: "PEN-001",
        qty: NumberInt(1),
        price: NumberDecimal("2.00")
      }
    ],
    note: "Dữ liệu mẫu cho aggregation limits"
  });
}

sampleOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

Trên collection mới và rỗng, kết quả là **24**. Vì dùng `replaceOne(..., {upsert:true})`, chạy lại sẽ đặt lại 24 document mẫu có ID từ `ord-001` tới `ord-024`; document khác nếu từng được thêm sẽ **không** tự bị xóa.

Trong bộ dữ liệu:

- Tenant-A có **18** đơn, tenant-B có **6** đơn.
- Tenant-A có **6** đơn mỗi trạng thái `NEW`, `SHIPPED`, `PAID`.
- Tenant-B có **2** đơn mỗi trạng thái.
- Mỗi đơn có hai dòng `items`, là mảng object.
- `amount` được lưu kiểu Decimal128.
- `createdAt` tăng theo ID, thuận tiện cho ví dụ sort và limit.

Tạo index dùng trong nhiều phép so sánh:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_tenant_status_date_id"
  }
);
~~~

Quan sát document và count:

~~~javascript
db.orders.find(
  {},
  { _id: 1, tenantId: 1, status: 1 }
).sort({ _id: 1 });

db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
}); // 6 khi chỉ có dữ liệu mẫu
~~~

**Lý do bộ mẫu nhỏ:** Các pipeline trong bài được thiết kế để minh họa cấu trúc và cơ chế. Chúng **không cố tình tạo hàng trăm megabyte dữ liệu hoặc làm đầy ổ đĩa** chỉ để ép server gặp lỗi. Trên tập 24 document, `allowDiskUse:true` thường không tạo file spill, và đó là kết quả bình thường.

## 4. Giới hạn 16 MiB áp dụng cho từng BSON document

### 4.1. Một document kết quả phải nằm trong giới hạn

MongoDB giới hạn một BSON document thông thường tối đa **16 MiB**. Trong aggregation, lệnh có thể trả một cursor với hàng nghìn document; mỗi document trong kết quả phải hợp lệ theo giới hạn này.

Ví dụ trả nhiều document nhỏ:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1
    }
  }
]);
~~~

Có 18 document nếu chỉ chứa dữ liệu mẫu. Tổng dữ liệu của cursor có thể vượt 16 MiB trong workload thực, miễn là **không có document riêng lẻ** vượt giới hạn và các tài nguyên khác vẫn đáp ứng được.

### 4.2. Đừng nhầm 16 MiB với kích thước kết quả toàn pipeline

Sai:

> "Aggregation chỉ được trả tổng cộng tối đa 16 MiB dữ liệu."

Đúng hơn:

> "Mỗi document trả về hoặc được ghi phải tuân thủ giới hạn BSON 16 MiB. Cursor có thể trả nhiều document qua các batch."

Các batch của cursor có những giới hạn truyền dữ liệu riêng và server/driver quản lý việc gửi theo batch. Đây không phải lý do để gom tất cả record vào một array khổng lồ trong **một document**.

### 4.3. Một document trung gian có thể vượt 16 MiB

Theo giới hạn aggregation của MongoDB, giới hạn BSON cho document **trong tập kết quả** không có nghĩa mọi document trung gian ở mọi stage đều phải dưới 16 MiB. Một số pipeline có thể tạo document trung gian lớn hơn trước khi rút gọn.

Tuy nhiên:

- Kết quả cuối vẫn phải đáp ứng 16 MiB/document.
- Các stage riêng như `$facet` và accumulator có thể áp dụng giới hạn độc lập.
- Việc document trung gian đôi lúc được phép lớn hơn **không** bảo đảm mọi phép biến đổi khác đều chấp nhận không giới hạn.
- Không nên thiết kế pipeline phụ thuộc vào việc tích tụ dữ liệu cực lớn rồi “hy vọng stage cuối thu nhỏ kịp”.

### 4.4. Đo kích thước BSON bằng $bsonSize

MongoDB có aggregation expression `$bsonSize` để tính kích thước byte của document/object BSON.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: {
        $bsonSize: "$$ROOT"
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 5 }
]);
~~~

`$$ROOT` là document hiện tại của stage; `$bsonSize` trả số byte BSON của object đó.

Có thể thêm thông tin quy đổi:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: {
        $bsonSize: "$$ROOT"
      },
      bsonMiB: {
        $divide: [
          { $bsonSize: "$$ROOT" },
          1048576
        ]
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 3 }
]);
~~~

Trong thực tế, `$bsonSize` có thể hữu ích để nhận diện record có mảng lớn hoặc object lồng nhau bất thường trước khi triển khai pipeline tổng hợp.

### 4.5. Đếm kích thước document đích, không chỉ field payload

BSON chứa tên field, metadata kiểu, giá trị, terminator và các chi phí biểu diễn liên quan. Một chuỗi payload 15 MiB không có nghĩa cả document BSON đúng 15 MiB; cần tính toàn bộ cấu trúc BSON.

Nếu một document có xu hướng tăng không giới hạn do chứa quá nhiều phần tử lịch sử, cần xem lại mô hình dữ liệu, thay vì nâng `allowDiskUse` để cố vượt BSON limit.

## 5. Rủi ro $group và $push tạo một document rất lớn

### 5.1. $group tạo một record tổng hợp cho mỗi nhóm

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với 24 document, mỗi trạng thái có 8 đơn. Kết quả là ba document nhỏ, mỗi document chứa mã nhóm, count và tổng tiền.

`$group` phải duy trì trạng thái accumulator cho các nhóm. Khi số nhóm rất lớn hoặc accumulator giữ nhiều dữ liệu, bộ nhớ có thể tăng đáng kể.

### 5.2. $push: "$$ROOT" có thể tạo output khổng lồ

Cú pháp nguy hiểm trên collection lớn:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      allOrders: {
        $push: "$$ROOT"
      }
    }
  }
]);
~~~

Mỗi nhóm có một mảng chứa toàn bộ document đơn hàng. Nếu tenant có hàng triệu đơn, một document duy nhất có thể rất lớn.

Điều này có ít nhất **hai nhóm rủi ro**:

1. Bộ nhớ của accumulator `$push` có giới hạn riêng và không thể trông chờ spill để giải quyết hoàn toàn.
2. Document kết quả có thể vượt **16 MiB**, dù phần logic nhóm đã xử lý xong.

`allowDiskUse:true` không làm cho một document BSON vượt 16 MiB trở nên hợp lệ.

### 5.3. Thay $push toàn bộ bằng aggregate số liệu

Nếu nhu cầu là báo cáo số đơn và doanh thu:

~~~javascript
db.orders.aggregate([
  {
    $match: { tenantId: "tenant-A" }
  },
  {
    $group: {
      _id: "$status",
      orderCount: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Nếu cần danh sách ID đại diện, cân nhắc một `$first`/`$top` hoặc cơ chế lấy trang riêng theo hợp đồng, thay vì đưa toàn bộ document vào array.

### 5.4. Giới hạn riêng của $push

Tài liệu MongoDB mô tả accumulator `$push` có giới hạn bộ nhớ riêng; nó **không ghi dữ liệu accumulator sang file tạm** chỉ nhờ `allowDiskUse`. Mặc định thông số nội bộ `internalQueryMaxPushBytes` thường là 104.857.600 byte (xấp xỉ 100 MiB).

Không nên tùy tiện thay đổi server parameter để “sửa” một mô hình giữ vô hạn tài liệu trong một array. Thay vào đó, chia nhóm, giới hạn kết quả, lưu các phần tử ở document riêng và đọc theo trang.

## 6. Giới hạn số stage trong pipeline

MongoDB giới hạn **1.000 aggregation stage trong một pipeline**. Nếu số stage vượt ngưỡng trước hoặc sau quá trình phân tích/canonicalization, server có thể trả lỗi.

Một pipeline hợp lý:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $set: {
      isPaid: { $eq: ["$status", "PAID"] }
    }
  },
  {
    $group: {
      _id: "$isPaid",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Có bốn stage rõ ràng. Một pipeline được generator xây bằng hàng nghìn stage nhỏ và lặp lại có thể gặp giới hạn, dù đầu vào chỉ có vài document.

### 6.1. Trường hợp generator tạo stage lặp lại

Ví dụ sau **được thiết kế để nhận lỗi số stage**; chỉ dùng trên database thực hành nếu muốn quan sát:

~~~javascript
const tooManyStages = Array.from(
  { length: 1001 },
  () => ({ $set: { touched: true } })
);

try {
  db.orders.aggregate(tooManyStages).toArray();
} catch (e) {
  print("Pipeline quá số stage: " + e.message);
}
~~~

MongoDB có thể báo lỗi vượt stage limit khi parse, trước khi xử lý document. Thông điệp cụ thể tùy phiên bản.

**Không nên tối ưu bằng cách tăng giới hạn này:** hãy đơn giản hóa công thức, gộp các phép tính cùng ngữ nghĩa vào stage hợp lý và giảm các bước trung gian không cần thiết.

### 6.2. $set nhiều field thay vì hàng trăm stage đơn giản

Thay vì:

~~~javascript
db.orders.aggregate([
  { $set: { statusText: "$status" } },
  { $set: { tenantText: "$tenantId" } },
  { $set: { amountText: { $toString: "$amount" } } }
]);
~~~

có thể viết:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      statusText: "$status",
      tenantText: "$tenantId",
      amountText: {
        $toString: "$amount"
      }
    }
  }
]);
~~~

Cách này giảm số stage và dễ đọc hơn, **nếu các expression không phụ thuộc vào field vừa được tạo trong cùng stage**. Khi field sau cần đọc kết quả của field trước, vẫn cần tách stage theo dependency.

### 6.3. Không chỉ đếm số dòng trong code

Một stage như `$facet` có nhiều sub-pipeline. Các stage do generator, driver hoặc optimizer biến đổi cũng có thể khiến tổng stage được tính khác cách một lập trình viên chỉ nhìn một danh sách top-level đơn giản.

Nên tránh thiết kế sát ngưỡng 1.000; kiểm tra pipeline thực tế do ứng dụng phát ra, nhất là pipeline được xây động từ nhiều bộ lọc.

## 7. Vì sao một số stage cần RAM lớn?

Một số stage có thể xử lý document kiểu streaming: nhận một document rồi tạo ra kết quả tương ứng hoặc loại nó đi.

Ví dụ:

~~~javascript
{ $match: { status: "PAID" } }
{ $project: { _id: 1, amount: 1 } }
{ $set: { doubleAmount: { $multiply: ["$amount", 2] } } }
~~~

Nhiều thao tác dạng này không cần giữ mọi document của đầu vào trong RAM cùng lúc.

Ngược lại, **blocking stages** có thể cần thu thập nhiều document trước khi tạo đủ kết quả:

~~~text
Input documents
    |
    v
  $sort       Có thể cần nắm nhiều record/keys để xác định thứ tự
    |
    v
  $group      Có thể cần giữ trạng thái cho rất nhiều nhóm
    |
    v
  $setWindowFields   Có thể cần buffer/partitions cho window calculation
    |
    v
  Output
~~~

Nếu không có index hoặc tối ưu phù hợp, `$sort` trên dữ liệu lớn có thể tạo áp lực bộ nhớ. `$group` với số nhóm lớn hoặc accumulator phức tạp cũng vậy.

Các ví dụ stage có thể spill khi được phép gồm:

- `$sort` khi không được index đáp ứng đủ.
- `$group`.
- `$bucket` và `$bucketAuto`.
- `$sortByCount`.
- `$setWindowFields`.

Hỗ trợ và giới hạn chi tiết phụ thuộc phiên bản MongoDB. Không suy luận rằng **mọi stage** tự động spill nếu bật `allowDiskUse`.

## 8. Ngưỡng 100 MB và allowDiskUse

### 8.1. Thế nào là spill to disk?

Khi stage có khả năng spill cần nhiều bộ nhớ hơn ngân sách áp dụng, MongoDB có thể ghi một phần trạng thái trung gian vào file tạm trên đĩa và đọc lại khi cần.

~~~text
                 Blocking stage
                       |
                RAM đủ hay không?
                     /   \
                   Có    Không
                   |       |
                   v       v
              Xử lý RAM   Được phép spill?
                              /   \
                            Có     Không
                            |        |
                            v        v
                      File tạm    Memory limit error
                      trên đĩa
                            |
                            v
                         Tiếp tục
~~~

**Spill không làm toàn bộ thao tác miễn phí**. Nó chuyển một phần áp lực từ RAM sang I/O và dung lượng lưu trữ. Một truy vấn không còn lỗi bộ nhớ nhưng có thể chậm hơn rất nhiều và tạo áp lực ổ đĩa.

### 8.2. allowDiskUse là tùy chọn theo operation

Ví dụ:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$status",
        orderCount: { $sum: 1 },
        totalAmount: { $sum: "$amount" }
      }
    },
    { $sort: { totalAmount: -1 } }
  ],
  {
    allowDiskUse: true
  }
);
~~~

`allowDiskUse:true` cho phép những stage hỗ trợ tràn dữ liệu ra file tạm trong các điều kiện cần thiết. Nó không yêu cầu server nhất định phải tạo file tạm ở mỗi lần chạy.

Với 18 document tenant-A, không có lý do mong đợi một sự kiện spill chỉ nhờ bật tùy chọn.

### 8.3. allowDiskUse: false

~~~javascript
db.orders.aggregate(
  [
    { $sort: { amount: -1 } }
  ],
  {
    allowDiskUse: false
  }
);
~~~

Tùy chọn này cấm sử dụng disk spill cho thao tác, kể cả khi mặc định server cho phép. Trên dữ liệu nhỏ, lệnh vẫn thành công; với workload lớn cần vượt ngân sách bộ nhớ của stage, nó có thể lỗi.

Cách hiểu:

| Tùy chọn | Mong muốn |
|---|---|
| `allowDiskUse: true` | Cho phép stage hỗ trợ sử dụng file tạm khi cần |
| `allowDiskUse: false` | Không cho stage spill; có thể lỗi khi thiếu bộ nhớ |
| Không chỉ định | Phụ thuộc server version và `allowDiskUseByDefault`/cấu hình môi trường |

### 8.4. Không thay giới hạn BSON 16 MiB

Ngay cả khi:

~~~javascript
db.orders.aggregate(
  [
    {
      $group: {
        _id: null,
        allOrders: { $push: "$$ROOT" }
      }
    }
  ],
  { allowDiskUse: true }
);
~~~

vẫn có thể thất bại trên tập dữ liệu đủ lớn vì accumulator quá lớn hoặc **một document output** vượt BSON 16 MiB. Cho phép spill không thay đổi kích thước tối đa của document trả về.

### 8.5. Không phải cứ error là cần bật allowDiskUse

Những lỗi khác nhau có cách xử lý khác nhau:

- BSON result quá lớn → thay đổi cấu trúc output, không chỉ bật spill.
- `$facet` memory limit → giảm dữ liệu nhánh facet, không chỉ bật spill.
- `$push` accumulator limit → tránh giữ toàn bộ record trong array.
- Quá 1.000 stage → đơn giản hóa pipeline.
- Lỗi schema/type/regex → sửa dữ liệu hoặc expression.
- Hết ổ đĩa → giảm workload/spill và xử lý storage.
- Timeout → tối ưu query, giới hạn công việc và đánh giá SLA.

## 9. allowDiskUseByDefault từ MongoDB 6.0

Từ MongoDB **6.0**, tham số server `allowDiskUseByDefault` quyết định hành vi mặc định của những stage thuộc cơ chế memory/spill thông thường.

### 9.1. Khi allowDiskUseByDefault = true

- Những stage hỗ trợ có thể sử dụng file tạm nếu vượt mức bộ nhớ cần spill.
- Một command cụ thể có thể đặt `{allowDiskUse:false}` để cấm sử dụng disk tạm cho command đó.

### 9.2. Khi allowDiskUseByDefault = false

- Những stage vượt ngưỡng và không được phép spill có thể trả lỗi.
- Một command cụ thể có thể đặt `{allowDiskUse:true}` để cho phép disk spill.

Vì vậy, không nên ghi cứng trong tài liệu ứng dụng rằng “MongoDB 6.0 trở lên luôn spill mặc định” mà không kiểm tra cấu hình thực tế.

### 9.3. Xem tham số nếu có quyền quản trị

Trong môi trường self-managed mà bạn có quyền phù hợp, có thể truy vấn server parameter:

~~~javascript
db.adminCommand({
  getParameter: 1,
  allowDiskUseByDefault: 1
});
~~~

Trên dịch vụ managed, một số tham số có thể không được phép đọc/chỉnh trực tiếp. Nếu bị từ chối, hãy làm việc với DBA hoặc xem cấu hình được nhà cung cấp hỗ trợ.

**Không cần thay server parameter để học bài.** Với mỗi pipeline có nhu cầu rõ ràng, đặt `allowDiskUse` ở cấp command thường làm ý định minh bạch hơn.

### 9.4. Phiên bản trước MongoDB 6.0

Ở các phiên bản cũ hơn, việc cho phép disk spill thường cần tùy chọn `allowDiskUse:true` khi chạy lệnh. Khi viết tài liệu hoặc code dùng cho nhiều phiên bản, cần kiểm tra khả năng của server được triển khai, không lấy hành vi mặc định của bản mới áp vào mọi nơi.

## 10. MongoDB 9.0: giới hạn bộ nhớ trên toàn operation

Ngoài giới hạn bộ nhớ theo stage, tài liệu MongoDB phiên bản **9.0 trở lên** mô tả thêm giới hạn **tổng bộ nhớ của một query operation**. Giới hạn này cộng gộp mức tiêu thụ của các thành phần được theo dõi trong cùng operation.

Theo cấu hình mặc định được tài liệu mô tả, ngân sách tổng là **giá trị lớn hơn giữa 1 GiB và 20% bộ nhớ khả dụng cho tiến trình server**, được xác định theo cơ chế của phiên bản đó. Việc thay đổi có thể thông qua server parameter và thiết lập được phép trong môi trường tương ứng.

Điều này có nghĩa:

- Một operation có nhiều stage cùng tốn bộ nhớ có thể gặp giới hạn tổng, ngay cả khi một stage đơn lẻ chưa có dấu hiệu đặc biệt.
- Giới hạn tổng **không thay thế** cơ chế memory limit và spill theo stage.
- Một số expression dùng nhiều bộ nhớ còn có giới hạn riêng.
- Cách xử lý khi vượt giới hạn phụ thuộc loại công việc và khả năng spill của các thành phần.

**Chú ý tương thích:** Nếu cluster đang chạy MongoDB 7.x hoặc 8.x, không tự khẳng định tham số/giới hạn tổng của 9.0 đã tồn tại. Trong môi trường nhiều phiên bản, hãy dựa trên tài liệu đúng major version.

Đối với bài thực hành trên 24 document, không cần thay đổi bất kỳ tham số bộ nhớ của server.

## 11. $sort là blocking stage điển hình

### 11.1. Sort tất cả document không có index phù hợp

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1 } }
]);
~~~

Nếu MongoDB không có index phục vụ thứ tự `amount`, server phải sắp xếp dữ liệu. Trên collection lớn, bước sort có thể giữ nhiều dữ liệu trong RAM hoặc spill ra đĩa nếu được phép.

Vấn đề không nằm ở số document cuối cùng được trả về, mà ở việc phải xác định thứ tự của tập đầu vào.

### 11.2. Thêm $limit để chỉ lấy top N

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 }
]);
~~~

Khi `$sort` đứng trước `$limit` và không có stage trung gian làm thay đổi số document, MongoDB optimizer có thể gộp `$limit` vào `$sort` và chỉ giữ **top N** kết quả cần thiết.

Điều đó giúp giảm bộ nhớ so với sắp xếp để trả toàn bộ tập. Nếu chính N document cũng quá lớn, bộ nhớ/spill vẫn có thể là vấn đề.

### 11.3. Match trước sort

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 }
]);
~~~

`$match` giảm từ 24 xuống 18 document trong bộ mẫu. Trong workload lớn, lọc sớm theo điều kiện có index có thể làm phạm vi sort nhỏ hơn đáng kể.

Index `{tenantId:1,status:1,createdAt:-1,_id:-1}` trong phần chuẩn bị có thể tối ưu tốt cho filter có cả tenantId lẫn status:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

Với dữ liệu mẫu, kết quả là `ord-018` và `ord-015`.

### 11.4. Sort bằng index so với sort trong RAM

MongoDB có thể tận dụng index cho `$sort` khi stage này xuất hiện ở vị trí phù hợp, đặc biệt khi là stage đầu hoặc được đi trước bởi `$match` mà không làm biến đổi khóa sort.

Ví dụ:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

Khi có index phục vụ cả filter và sort, server có thể tránh bước blocking sort lớn.

Ngược lại, nếu tính khóa mới rồi mới sort:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      doubledAmount: {
        $multiply: ["$amount", 2]
      }
    }
  },
  { $sort: { doubledAmount: -1 } }
]);
~~~

khóa `doubledAmount` không phải trường được index sẵn trên collection. Phép sort này có thể phải sắp xếp dữ liệu trung gian.

### 11.5. $sort không bảo đảm ổn định khi khóa trùng

Nếu nhiều document có cùng giá trị `amount`, thứ tự giữa chúng không nhất thiết ổn định. Khi phân trang:

~~~javascript
{ $sort: { amount: -1, _id: 1 } }
~~~

khóa phụ `_id` giúp tạo thứ tự quyết định. Tính ổn định của phân trang là vấn đề riêng với bộ nhớ; index phù hợp cũng nên phản ánh thứ tự sort thực tế.

## 12. $group: giữ trạng thái của nhiều nhóm

### 12.1. Nhóm theo status

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với bộ mẫu tenant-A, mỗi status có `count:6`. Tổng tiền phụ thuộc ID thuộc từng nhóm.

### 12.2. Số nhóm có thể lớn

Nếu nhóm theo một field có cardinality rất cao, ví dụ `userId` của hàng triệu người dùng:

~~~javascript
db.events.aggregate([
  {
    $group: {
      _id: "$userId",
      eventCount: { $sum: 1 }
    }
  }
], { allowDiskUse: true });
~~~

`$group` có thể phải duy trì rất nhiều nhóm. `allowDiskUse:true` có thể giúp nếu stage thuộc trường hợp spill được hỗ trợ, nhưng không làm bộ nhớ sử dụng bằng zero.

Ví dụ `db.events` chỉ minh họa workload ngoài collection thực hành; không cần chạy khi không có collection `events`.

### 12.3. Tránh đưa toàn bộ document vào một nhóm

Khi bạn viết:

~~~javascript
{
  $group: {
    _id: "$tenantId",
    documents: { $push: "$$ROOT" }
  }
}
~~~

bạn đang tạo một array lớn với toàn bộ document. Nếu ứng dụng chỉ cần thống kê, nên dùng `$sum`, `$avg`, `$min`, `$max`, hoặc các biểu thức top/bottom thích hợp với phiên bản server.

Nếu cần lấy mọi document của một tenant, dùng cursor có filter/sort/pagination thay vì gom tất cả vào một BSON result.

### 12.4. $sortByCount cũng cần tài nguyên

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sortByCount: "$status" }
], { allowDiskUse: true });
~~~

`$sortByCount` tổng hợp số lần xuất hiện rồi sort kết quả. Nó có thể chịu áp lực memory/spill trên tập dữ liệu có rất nhiều nhóm, dù output cuối chỉ gồm mỗi nhóm và count.

### 12.5. $bucket và $bucketAuto

Các phép phân nhóm theo khoảng:

~~~javascript
db.orders.aggregate([
  {
    $bucket: {
      groupBy: "$amount",
      boundaries: [
        NumberDecimal("0"),
        NumberDecimal("100"),
        NumberDecimal("200"),
        NumberDecimal("1000")
      ],
      default: "other",
      output: {
        count: { $sum: 1 }
      }
    }
  }
], { allowDiskUse: true });
~~~

`$bucket`/`$bucketAuto` cũng có thể cần nhiều trạng thái trung gian. Cần thiết kế số bucket và accumulator, tránh giữ nguyên cả document nếu chỉ cần count.

## 13. $setWindowFields và bộ nhớ phân vùng

Các window function có thể tính tổng lũy kế, moving average, row number và thống kê theo phân vùng.

Ví dụ tổng tiền lũy kế theo tenant:

~~~javascript
db.orders.aggregate([
  {
    $setWindowFields: {
      partitionBy: "$tenantId",
      sortBy: {
        createdAt: 1,
        _id: 1
      },
      output: {
        runningAmount: {
          $sum: "$amount",
          window: {
            documents: ["unbounded", "current"]
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1,
      amount: 1,
      runningAmount: 1
    }
  }
], { allowDiskUse: true });
~~~

Stage có thể phải sắp xếp/buffer dữ liệu theo partition và window. Trên nhiều partition lớn hoặc cửa sổ rộng, bộ nhớ và file tạm có thể tăng đáng kể.

Những cân nhắc quan trọng:

- Có thể lọc tập dữ liệu sớm theo tenant/khoảng thời gian nếu nghiệp vụ cho phép.
- Index theo `partitionBy` và `sortBy` có thể hữu ích nhưng phải kiểm tra kế hoạch thực tế.
- Window `unbounded` không nên được dùng vô thức khi ứng dụng chỉ cần cửa sổ vài bản ghi.
- `allowDiskUse` có thể giúp stage được hỗ trợ spill, nhưng không thay giới hạn BSON của output.

## 14. $facet: giới hạn đặc biệt không thể giải bằng allowDiskUse

`$facet` chạy nhiều sub-pipeline trên cùng tập document đầu vào rồi ghép kết quả vào một document chứa nhiều array.

Ví dụ:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $facet: {
      statusCounts: [
        {
          $group: {
            _id: "$status",
            count: { $sum: 1 }
          }
        },
        { $sort: { _id: 1 } }
      ],
      latestOrders: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            status: 1,
            createdAt: 1
          }
        }
      ]
    }
  }
]);
~~~

Kết quả có cấu trúc:

~~~javascript
[
  {
    statusCounts: [
      { _id: "NEW", count: 6 },
      { _id: "PAID", count: 6 },
      { _id: "SHIPPED", count: 6 }
    ],
    latestOrders: [
      { _id: "ord-018", /* ... */ },
      { _id: "ord-017", /* ... */ },
      { _id: "ord-016", /* ... */ }
    ]
  }
]
~~~

### 14.1. Giới hạn bộ nhớ của $facet

Theo tài liệu MongoDB, document mà `$facet` xây dựng bị giới hạn **100 MB** trong quá trình xử lý stage; **`$facet` không thể spill ra đĩa**. `allowDiskUse:true` không làm tăng mức 100 MB đó.

Nếu các array do nhánh facet tạo ra quá lớn, MongoDB có thể trả lỗi `ExceededMemoryLimit`.

### 14.2. Giới hạn output 16 MiB vẫn áp dụng

Dù document bên trong `$facet` chưa vượt 100 MB, khi nó trở thành document **kết quả cuối cùng**, vẫn phải dưới giới hạn **16 MiB BSON**.

Đây là hai tầng giới hạn khác nhau:

~~~text
$facet tạo document gồm nhiều array
             |
             v
        100 MB stage limit
        (không spill)
             |
             v
       16 MiB BSON result limit
             |
             v
        Client nhận output
~~~

Một pipeline facet có thể lỗi do document kết quả vượt 16 MiB **trước khi đạt 100 MB**, và bật `allowDiskUse` không giải quyết được.

### 14.3. Vì sao facet phân trang dễ gặp lỗi?

Cách không nên dùng trên collection lớn:

~~~javascript
db.orders.aggregate([
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1 } }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

Nhánh `data` trả **mọi document** vào một array. Tổng array tăng theo số lượng record, có thể vượt ngân sách facet hoặc BSON output.

Cách an toàn hơn là giới hạn nhánh data:

~~~javascript
const filter = { tenantId: "tenant-A" };
const page = 2;
const pageSize = 3;
const offset = (page - 1) * pageSize;

db.orders.aggregate([
  { $match: filter },
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $skip: offset },
        { $limit: pageSize },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
      ],
      metadata: [
        { $count: "total" }
      ]
    }
  },
  {
    $project: {
      data: 1,
      total: {
        $ifNull: [
          { $arrayElemAt: ["$metadata.total", 0] },
          0
        ]
      }
    }
  }
]);
~~~

Ở bộ mẫu, `total=18` và nhánh `data` trả 3 document của trang 2.

### 14.4. Một lệnh facet không có nghĩa đếm miễn phí

Dù nhánh `data` chỉ trả 3 document, nhánh `metadata` vẫn phải đếm cả tập đầu vào phù hợp. Giảm số round trip không đồng nghĩa giảm toàn bộ công việc phải làm.

Với báo cáo phức tạp, cần đo chi phí facet và cân nhắc hai truy vấn riêng, cache count hoặc phân trang chỉ trả `hasNext` nếu không cần total chính xác.

### 14.5. Không thể chạy mọi stage trong facet

Một số stage không được phép xuất hiện bên trong sub-pipeline của `$facet`, đặc biệt các stage ghi dữ liệu như `$out` và `$merge`. Khi cần ghi kết quả, phải thiết kế pipeline tổng hợp và bước ghi riêng đúng quy tắc MongoDB; không thể dùng facet để bỏ qua các ràng buộc stage đó.

## 15. $lookup và fan-out: không chỉ vấn đề RAM

`$lookup` có thể join document từ collection khác vào một array. Nếu một đơn hàng liên kết rất nhiều dòng hàng, array kết quả có thể trở nên cực lớn.

Ví dụ schema:

~~~javascript
// orders:
{
  _id: "ord-001",
  tenantId: "tenant-A"
}

// orderLines:
{
  _id: "ord-001#01",
  orderId: "ord-001",
  sku: "SKU-001",
  qty: 2
}
~~~

Tạo dữ liệu dòng hàng nhỏ cho bài thực hành:

~~~javascript
for (let i = 1; i <= 24; i++) {
  const orderId = "ord-" + String(i).padStart(3, "0");

  for (let j = 1; j <= 3; j++) {
    const lineId = orderId + "#" + String(j).padStart(2, "0");

    db.orderLines.replaceOne(
      { _id: lineId },
      {
        _id: lineId,
        orderId: orderId,
        sku: "LINE-" + String(j),
        qty: NumberInt(j),
        price: NumberDecimal(String(j * 2) + ".00")
      },
      { upsert: true }
    );
  }
}

db.orderLines.createIndex(
  { orderId: 1 },
  { name: "idx_orderLines_orderId" }
);
~~~

Khi collection `orderLines` mới, có **72** dòng mẫu (3 dòng cho mỗi đơn). Lệnh nạp lại cập nhật các ID mẫu nhưng không xóa record khác.

### 15.1. Join đơn giản

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      as: "lines"
    }
  },
  {
    $project: {
      _id: 1,
      lines: 1
    }
  }
]);
~~~

Trong bộ mẫu, output chỉ có ba line. Nhưng trong hệ thống thật, nếu một order có hàng triệu line, `lines` có thể đẩy document tổng hợp vượt giới hạn BSON hoặc tiêu tốn tài nguyên lớn.

### 15.2. Giới hạn dữ liệu join theo nhu cầu

Nếu chỉ cần preview 3 dòng:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $sort: { _id: 1 } },
        { $limit: 3 },
        {
          $project: {
            _id: 1,
            sku: 1,
            qty: 1
          }
        }
      ],
      as: "previewLines"
    }
  },
  {
    $project: {
      _id: 1,
      previewLines: 1
    }
  }
]);
~~~

Nhánh `pipeline` của `$lookup` chỉ lấy số line cần thiết theo ý định preview. Đây **không** phải số line đầy đủ của đơn, và response cần đặt tên/giải thích phù hợp.

### 15.3. Khi cần tất cả line, cân nhắc kết quả dạng dòng

Thay vì nhét toàn bộ `lines` vào một document, có thể lấy dòng hàng bằng query riêng:

~~~javascript
db.orderLines.find({
  orderId: "ord-001"
})
.sort({ _id: 1 })
.limit(20);
~~~

Hoặc thiết kế pipeline dùng `$unwind` để tạo nhiều document đầu ra nhỏ:

~~~javascript
db.orders.aggregate([
  { $match: { _id: "ord-001" } },
  {
    $lookup: {
      from: "orderLines",
      localField: "_id",
      foreignField: "orderId",
      as: "lines"
    }
  },
  { $unwind: "$lines" },
  {
    $project: {
      _id: 1,
      sku: "$lines.sku",
      qty: "$lines.qty"
    }
  }
]);
~~~

**Cẩn trọng:** Pipeline trên vẫn phải tạo array `lines` trong `$lookup` trước khi `$unwind`. Với fan-out rất lớn, nó có thể gặp giới hạn **ngay ở bước lookup**, trước khi unwind kịp tách output. Đối với dữ liệu thật cực lớn, nên đọc `orderLines` trực tiếp theo `orderId` hoặc thiết kế hướng streaming/pagination thay vì coi unwind sau lookup là cách luôn tránh được mọi giới hạn.

## 16. $unwind có thể nhân số lượng document

Mỗi document mẫu có 2 phần tử trong mảng `items`:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unwind: "$items" },
  { $count: "lineCount" }
]);
~~~

Với 18 order của tenant-A và mỗi order có 2 item, kết quả là:

~~~javascript
[{ lineCount: 36 }]
~~~

`$unwind` thường phát nhiều document đầu ra hơn đầu vào, không nhất thiết là blocking stage giữ toàn bộ dữ liệu trong RAM. Nhưng nó làm **các stage phía sau** như `$sort`, `$group` hoặc `$facet` phải xử lý nhiều record hơn.

Nếu một document chứa mảng 100.000 phần tử, một lần unwind có thể tăng cardinality mạnh. Nếu trước đó có lookup với fan-out lớn, số row sau unwind còn có thể tăng theo tích các quan hệ.

### 16.1. Lọc trước khi unwind

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      totalQty: { $sum: "$items.qty" }
    }
  }
]);
~~~

Đưa filter theo tenant/status lên trước làm giảm số document phải unwind và nhóm, khi điều đó giữ đúng ngữ nghĩa nghiệp vụ.

### 16.2. Không group trở lại toàn bộ dữ liệu nếu không cần

Sau `$unwind`, một lỗi phổ biến là group lại toàn bộ record vào `{$push:"$$ROOT"}`. Nếu chỉ cần số lượng hoặc tổng tiền, nên tổng hợp thành số thay vì tái tạo mảng lớn.

## 17. Giảm kích thước output bằng $project và $unset

### 17.1. Chỉ trả field cần thiết

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 5 },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      createdAt: 1
    }
  }
]);
~~~

`$project` định nghĩa **allowlist** field của output, giảm payload trả về client và tránh vô tình lộ các field không cần thiết.

### 17.2. Xóa field lớn

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unset: ["items", "note"] }
]);
~~~

Đây chỉ là phép biến đổi **kết quả pipeline**. Dữ liệu gốc trên collection không bị xóa.

### 17.3. Đặt $project sớm có luôn nhanh hơn?

Không nhất thiết. MongoDB optimizer thường có khả năng phát hiện field nào cần cho các stage và tối ưu việc chỉ giữ những field cần thiết.

Nếu bạn loại field `amount` trước một stage cần tính tổng `amount`:

~~~javascript
db.orders.aggregate([
  { $project: { status: 1 } },
  {
    $group: {
      _id: "$status",
      total: { $sum: "$amount" }
    }
  }
]);
~~~

thì stage sau không còn dữ liệu gốc `amount` để tính đúng tổng. Vì vậy việc tối ưu pipeline cần tôn trọng **dependency giữa stage**.

Đặt `$match` theo field gốc sớm, dùng index phù hợp cho sort/filter và chỉ giữ những field cần thiết thường hữu ích hơn một quy tắc cứng “luôn đặt project lên đầu”.

## 18. allowDiskUse không đảm bảo luôn thành công

Giả sử stage `$sort` được phép ghi file tạm. Những rủi ro vẫn có thể xảy ra:

- Không đủ dung lượng ổ đĩa tạm.
- I/O bị bão hòa vì nhiều query cùng spill.
- Thời gian thực thi kéo dài quá SLA hoặc `maxTimeMS`.
- Một stage **không hỗ trợ spill** vẫn vượt giới hạn riêng.
- Document result vượt 16 MiB.
- Một accumulator như `$push` tạo array quá lớn.
- Phân trang hoặc group tạo quá nhiều record trung gian.
- Cluster sharded cần tổng hợp kết quả từ nhiều shard, gây áp lực ở nơi merge.
- Trên bản server mới, giới hạn tổng memory của operation có thể bị chạm.

Trong MongoDB Atlas hoặc môi trường managed, file tạm cũng có thể tạo áp lực storage và dẫn đến thay đổi chi phí/auto-scaling theo cấu hình dịch vụ.

**Không bật `allowDiskUse:true` đại trà mà không giám sát.** Mỗi pipeline cần giải thích vì sao phải spill, có index nào tránh sort lớn không, và dung lượng/độ trễ có chấp nhận được không.

## 19. Quan sát spill bằng explain

Một cách xem execution plan trong mongosh:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { totalAmount: -1 } }
], { allowDiskUse: true });
~~~

Kết quả explain phụ thuộc phiên bản MongoDB, query engine và optimizer.

Các trường/stage cần chú ý:

| Dấu hiệu | Ý nghĩa |
|---|---|
| `IXSCAN` | Truy vấn có dùng index |
| `COLLSCAN` | Quét collection |
| `SORT` | Có bước sắp xếp trong execution plan |
| `GROUP` hoặc biểu diễn tương ứng | Có bước nhóm |
| `totalKeysExamined` | Số khóa index được xét |
| `totalDocsExamined` | Số document được xét |
| `nReturned` | Số document được trả ở một plan/stage |
| `executionTimeMillis` | Thời gian thực thi theo kết quả explain |
| `usedDisk` | Dấu hiệu disk spill nếu được báo cáo |
| `spills`, `spilledDataStorageSize` hoặc field tương tự | Thông tin số lần/lượng dữ liệu spill khi phiên bản/stage hỗ trợ |

Không phải mọi server version hay stage đều in các field giống nhau. Nếu trường `usedDisk` vắng mặt trong explain, chưa thể kết luận chỉ từ việc vắng field rằng không có spill; cần xem profiler/diagnostic log phù hợp và phiên bản đang chạy.

### 19.1. Đọc sự khác biệt giữa query có index và không index

Ví dụ sort có index hỗ trợ:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 3 }
]);
~~~

Ví dụ sort có thể cần xử lý trong RAM:

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $sort: { amount: -1 } },
  { $limit: 3 }
]);
~~~

Hãy so plan, stage, số document/keys đã đọc. Trên 24 document, cả hai đều nhỏ; hiệu năng lớn cần đo với dữ liệu đại diện.

### 19.2. Explain không phải benchmark tuyệt đối

`executionTimeMillis` trong explain có thể bị ảnh hưởng bởi caching, quy mô dữ liệu, hạ tầng và kế hoạch thực thi. Lệnh explain có thể có overhead khác truy vấn bình thường.

Khi đánh giá production, quan sát:

- p50/p95/p99 latency của API.
- CPU/RAM và I/O của database.
- Số operation có disk spill.
- Dung lượng file tạm/available storage.
- Số lượng document qua từng stage.
- Tần suất query và mức độ chạy song song.
- Mức độ tăng của fan-out do `$unwind`/`$lookup`.

## 20. usedDisk trong profiler và diagnostic log

MongoDB có thể ghi chỉ báo **`usedDisk`** trong profiler và diagnostic logs khi một aggregation stage phải ghi dữ liệu tạm ra đĩa do giới hạn bộ nhớ.

Đó là tín hiệu quan trọng để phân biệt:

~~~text
Query hoàn tất nhờ sử dụng RAM
            so với
Query hoàn tất nhưng đã spill ra đĩa
~~~

Hai query có thể đều trả kết quả đúng nhưng rất khác nhau về thời gian và chi phí hệ thống.

### 20.1. Không tự bật profiler trên môi trường chung

Profiler là công cụ vận hành có thể tạo overhead và lưu thông tin truy vấn. Việc bật/tăng mức ghi log cần quyền và quy trình quản trị phù hợp.

Trong bài thực hành, ưu tiên `explain("executionStats")` và chỉ đọc các metric/profiler đã được DBA cho phép. Không tự thay `profilingLevel` hoặc tham số logging trên cluster dùng chung để ép thu thập dữ liệu.

### 20.2. Ý nghĩa của usedDisk

`usedDisk:true` báo rằng một stage đã dùng file tạm vì hạn chế bộ nhớ theo cách MongoDB ghi nhận. Nó **không** tự cho biết toàn bộ số byte I/O, thời gian bị chậm hoặc nguyên nhân thiết kế gốc.

Cần kết hợp with explain, query shape, kích thước dữ liệu, index và các metric storage.

## 21. Độ trễ và chi phí tài nguyên khi spill

Đường đi tương đối:

~~~text
Không spill:
RAM xử lý → xuất kết quả

Có spill:
RAM xử lý → ghi tệp tạm → đọc tệp tạm → merge/sort/group → xuất kết quả
~~~

Nếu một stage vừa phải scan nhiều document vừa ghi nhiều file tạm, tổng thời gian có thể bị chi phối bởi disk I/O.

Tốc độ và tác động phụ thuộc:

- Số lượng và kích thước record trung gian.
- Số nhóm trong `$group`.
- Sort key và số document phải sắp xếp.
- Kích thước partition/window.
- Thông lượng và độ trễ storage.
- Số query cùng spill và cạnh tranh CPU/I/O.
- Cấu hình server/shard và nơi thực hiện merge.
- Giới hạn thời gian và khả năng quota/auto-scale của môi trường.

Không thể khẳng định một stage spill sẽ luôn chậm hơn một mức phần trăm cố định. Cần đo với workload thật.

## 22. Thêm maxTimeMS để kiểm soát thời gian thực thi

Một query có thể sử dụng tối ưu index tốt mà vẫn tốn thời gian do dữ liệu quá lớn. Có thể thiết lập `maxTimeMS` trong command:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    {
      $group: {
        _id: "$status",
        count: { $sum: 1 }
      }
    }
  ],
  {
    allowDiskUse: true,
    maxTimeMS: 3000
  }
);
~~~

`maxTimeMS` là giới hạn thời gian thực thi do MongoDB áp dụng theo cơ chế tương ứng, **không phải cách tối ưu làm query nhanh hơn**. Nếu operation vượt giới hạn, có thể trả lỗi timeout.

Ứng dụng phải phân biệt:

- Không có document khớp.
- Có document nhưng aggregation timeout.
- Stage vượt memory limit.
- Vượt kích thước BSON.
- Lỗi quyền, network hoặc storage.

Không chuyển mọi lỗi timeout thành `count:0` hoặc danh sách rỗng, vì điều đó biến “không có kết quả” thành một kết luận sai.

## 23. Dùng $merge hoặc $out có giúp tránh giới hạn 16 MiB không?

Một aggregation có thể ghi kết quả sang collection qua `$merge` hoặc `$out`, nhưng **mỗi document ghi ra vẫn phải là BSON document hợp lệ**. Không có cơ chế “bật `$merge` để lưu một document 50 MiB” trong collection bình thường.

Ví dụ tạo số liệu tóm tắt theo tenant và trạng thái:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      orderCount: { $sum: 1 },
      amountTotal: { $sum: "$amount" }
    }
  },
  {
    $merge: {
      into: "orderSummaries",
      on: "_id",
      whenMatched: "replace",
      whenNotMatched: "insert"
    }
  }
], { allowDiskUse: true });
~~~

Mỗi document summary nhỏ, không chứa toàn bộ order. Đây là hướng thiết kế tốt hơn so với `$push:"$$ROOT"` tạo một record khổng lồ.

**Quan trọng:** `$merge` thật sự **ghi dữ liệu** vào collection `orderSummaries`. Chỉ chạy ví dụ này trong database thực hành và với quyền được phép. Khi ứng dụng cần read-only aggregation, không thêm stage ghi.

### 23.1. Ghi nhiều document nhỏ tốt hơn một document khổng lồ

Thay vì:

~~~javascript
{
  _id: "tenant-A",
  allOrders: [
    /* hàng triệu document */
  ]
}
~~~

thiết kế:

~~~javascript
{
  _id: {
    tenantId: "tenant-A",
    status: "PAID"
  },
  orderCount: 6,
  amountTotal: NumberDecimal("...")
}
~~~

Một summary với các con số có kích thước giới hạn rõ. Nếu cần xem từng order, đọc từ collection nguồn theo cursor và phân trang.

## 24. Chiến lược thiết kế lại pipeline khi gặp giới hạn

### 24.1. Bước 1: Xác định đúng lỗi

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| Thông báo BSON object/document too large | Một document vượt 16 MiB |
| ExceededMemoryLimit ở facet | Document do `$facet` xây dựng vượt ngân sách stage |
| Memory limit và no disk use | Stage cần memory/spill nhưng disk không được phép |
| `$push` accumulator vượt ngưỡng | Array tích lũy quá lớn, không spill được |
| Too many aggregation pipeline stages | Pipeline vượt 1.000 stage |
| Query timeout | Công việc vượt `maxTimeMS` hoặc timeout ở tầng khác |
| Disk full/insufficient storage | Spill hoặc workload khác chiếm hết tài nguyên |
| `usedDisk:true` và latency cao | Query đã spill, cần phân tích index/cardinality |

**Không sửa theo kiểu thử bật mọi tùy chọn**. Xác định giới hạn nào bị chạm trước rồi chọn biện pháp phù hợp.

### 24.2. Bước 2: Giảm dữ liệu đầu vào

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
]);
~~~

Filter đầu pipeline có thể giảm tập dữ liệu cần group. Tuy nhiên, nếu nghiệp vụ cần tổng trên **mọi tenant**, đừng tự thêm filter chỉ để query chạy nhanh mà làm sai kết quả.

### 24.3. Bước 3: Giảm kích thước từng record

Chỉ đưa field cần thiết qua những bước cần thiết, và giới hạn output:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $project: {
      _id: 1,
      status: 1,
      amount: 1,
      createdAt: 1
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 10 }
]);
~~~

Khi tối ưu thực tế, cần xem optimizer/index và không loại những field mà stage sau cần. Một projection quá sớm có thể làm mất dữ liệu hoặc ngăn plan dùng index sort theo cách mong muốn.

### 24.4. Bước 4: Hạn chế fan-out

- Cẩn thận với `$unwind` trên mảng rất dài.
- Chỉ join các field/record cần thiết trong `$lookup`.
- Phân trang collection con nếu quan hệ 1-n rất lớn.
- Tránh group lại toàn bộ kết quả fan-out vào một array lớn.
- Định nghĩa rõ đơn vị cần tính: order, order line, customer hay event.

### 24.5. Bước 5: Tối ưu sort

- Xây index đúng prefix filter và thứ tự sort.
- Kết hợp `$sort` với `$limit` khi chỉ cần top N.
- Tránh sort trên expression được tạo từ toàn bộ document nếu có thể dùng khóa đã lưu/index.
- Dùng tie-breaker unique cho phân trang.
- So sánh query plan trên dữ liệu đại diện.

### 24.6. Bước 6: Quyết định có cho phép spill hay không

Khi stage được hỗ trợ và đã tối ưu hợp lý, `allowDiskUse:true` có thể là giải pháp để xử lý workload phải dùng nhiều memory.

Nhưng phải đi kèm:

- Giám sát file tạm, I/O và độ trễ.
- Giới hạn thời gian và tài nguyên.
- Đánh giá concurrency trong giờ cao điểm.
- Kiểm tra disk quota và autoscaling.
- Xem tác động tới các query khác cùng cluster.

### 24.7. Bước 7: Thay đổi hình dạng output nếu vượt BSON

Nếu `$facet` hoặc `$group` tạo document có array rất lớn, lựa chọn thường tốt hơn là:

- Trả nhiều document nhỏ qua cursor.
- Tách dữ liệu chi tiết và dữ liệu summary.
- Sử dụng pagination cho danh sách liên quan.
- Chỉ lấy top N.
- Ghi aggregate gọn vào collection summary.
- Lưu lịch sử dài thành nhiều document con thay vì một array vô hạn.

## 25. Bảng quyết định nhanh: giới hạn nào, công cụ nào?

| Vấn đề | `allowDiskUse:true` có giúp trực tiếp? | Hướng xử lý chính |
|---|---|---|
| `$sort` lớn không có index | **Có thể** | Index phù hợp, `$match` sớm, `$limit` top N, spill khi cần |
| `$group` với nhiều nhóm | **Có thể** | Giảm cardinality, aggregate gọn, spill nếu stage hỗ trợ |
| `$setWindowFields` trên partition lớn | **Có thể** | Thu hẹp input/window, index, xem khả năng spill |
| `$facet` document vượt 100 MB | **Không** | Giới hạn sub-pipeline/output, tách facet |
| `$facet` result vượt 16 MiB | **Không** | Giảm các array data, phân trang, trả nhiều document |
| Một result document bất kỳ vượt 16 MiB | **Không** | Thiết kế output thành nhiều document nhỏ |
| `$push` accumulator quá lớn | **Không**, với giới hạn riêng của accumulator | Không tích lũy mọi document vào array |
| Pipeline có hơn 1.000 stage | **Không** | Gộp/tối giản stages, sửa generator |
| `$lookup` tạo một mảng cực lớn | **Không giải quyết BSON limit** | Giới hạn join, tách query, đổi mô hình dữ liệu |
| Hết ổ đĩa do spill | **Không**; còn có thể làm tệ hơn | Giảm spill, xử lý storage/quota |
| Query chậm do scan không chọn lọc | Không phải giải pháp gốc | Filter/index, tối ưu dữ liệu, đo explain |
| Query timeout | Không bảo đảm | Giảm công việc, tối ưu plan hoặc thiết kế async/cached phù hợp |

## 26. MongoDB Compass: xem pipeline và điều khiển allowDiskUse

MongoDB Compass thường có tab **Aggregations** để chạy pipeline, quan sát kết quả và, tùy phiên bản, cấu hình các option như `allowDiskUse`.

Quy trình thực hành:

1. Kết nối Compass vào MongoDB có database `aggregation_limits_lab`.
2. Mở collection `orders`, chọn tab **Aggregations**.
3. Tạo stage `$match`:

   ~~~json
   {"tenantId":"tenant-A"}
   ~~~

4. Thêm `$group`:

   ~~~json
   {
     "_id":"$status",
     "orderCount":{"$sum":1},
     "totalAmount":{"$sum":"$amount"}
   }
   ~~~

5. Thêm `$sort` theo `totalAmount` giảm dần:

   ~~~json
   {"totalAmount":-1}
   ~~~

6. Nếu phiên bản Compass có phần **Options**, quan sát tùy chọn disk usage/`allowDiskUse` và thử bật/tắt trên bộ dữ liệu nhỏ.
7. Nếu có **Explain Plan**, xem index, scan/sort và các thông số được UI cung cấp.
8. Thử `$facet` từ mục 14 nhưng giới hạn `latestOrders` bằng `$limit:3`.
9. Đối chiếu kết quả trong Compass với `mongosh` để phân biệt tác động của pipeline và option.
10. Không cố tăng dữ liệu để tràn bộ nhớ hoặc dùng các command quản trị ngoài phạm vi thực hành.

**Không mặc định Compass sẽ hiện đúng một nút ở mọi phiên bản**. Nếu UI không cho đặt option đầy đủ, dùng mongosh:

~~~javascript
db.orders.aggregate(
  [
    { $match: { tenantId: "tenant-A" } },
    { $sort: { amount: -1 } },
    { $limit: 5 }
  ],
  {
    allowDiskUse: true,
    maxTimeMS: 5000
  }
);
~~~

## 27. Java Driver: cấu hình allowDiskUse và maxTime

Với MongoDB Java Sync Driver, interface aggregate hỗ trợ `allowDiskUse` và giới hạn thời gian trên `AggregateIterable`.

Ví dụ, giả định biến `database` kiểu `MongoDatabase` đã được kết nối:

~~~java
import static com.mongodb.client.model.Accumulators.sum;
import static com.mongodb.client.model.Aggregates.group;
import static com.mongodb.client.model.Aggregates.match;
import static com.mongodb.client.model.Aggregates.sort;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> orders =
    database.getCollection("orders");

List<Bson> pipeline = List.of(
    match(eq("tenantId", "tenant-A")),
    group("$status", sum("orderCount", 1)),
    sort(descending("orderCount"))
);

List<Document> result = orders.aggregate(pipeline)
    .allowDiskUse(true)
    .maxTime(10, TimeUnit.SECONDS)
    .into(new ArrayList<>());

for (Document doc : result) {
    System.out.println(doc.toJson());
}
~~~

`allowDiskUse(true)` cho phép các stage hỗ trợ spill. `maxTime` đặt giới hạn thời gian, không tự tối ưu query.

### 27.1. Dùng streaming cursor thay vì kéo toàn bộ vào RAM ứng dụng

Trên tập kết quả cực lớn, cần tránh:

~~~java
// Có thể tiêu thụ quá nhiều RAM của ứng dụng.
List<Document> everything = orders.aggregate(pipeline)
    .allowDiskUse(true)
    .into(new ArrayList<>());
~~~

Thay vào đó, duyệt cursor theo batch:

~~~java
import com.mongodb.client.MongoCursor;

try (MongoCursor<Document> cursor = orders.aggregate(pipeline)
        .allowDiskUse(true)
        .batchSize(100)
        .iterator()) {

    while (cursor.hasNext()) {
        Document row = cursor.next();
        // Xử lý một row theo quy trình có giới hạn bộ nhớ.
        System.out.println(row.toJson());
    }
}
~~~

Bật spill phía MongoDB **không bảo vệ RAM của ứng dụng** nếu ứng dụng vẫn gom toàn bộ document vào `ArrayList`.

### 27.2. batchSize không thay giới hạn 16 MiB

`batchSize(100)` điều khiển số document mong muốn trên mỗi batch ở mức driver/server tương ứng, không phải quyền trả một document BSON quá 16 MiB.

Nếu một document đơn lẻ quá lớn, giảm batchSize không sửa được; phải thay đổi hình dạng document.

### 27.3. Xử lý lỗi theo loại

Ứng dụng nên xử lý riêng những tình huống:

- Thao tác vượt giới hạn bộ nhớ không được spill.
- Document kết quả vượt BSON size limit.
- Timeout.
- Lỗi network hoặc node không khả dụng.
- Pipeline syntax không hợp lệ.
- Không đủ quyền.
- Storage gặp sự cố.

Không retry vô hạn một pipeline có lỗi cấu trúc chắc chắn, chẳng hạn `$facet` trả array quá lớn, vì retry cùng input thường sẽ gặp lại giới hạn.

## 28. Các bài tập thực hành

Các bài sử dụng bộ dữ liệu nhỏ từ mục 3. Nếu ví dụ có liên quan `orderLines`, nạp thêm dữ liệu tại mục 15 trước. Không cần tạo hàng trăm megabyte để hiểu cơ chế.

### Bài 1. Kích thước BSON theo document

Chạy:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      bytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bytes: -1 } },
  { $limit: 5 }
]);
~~~

**Câu hỏi:** Vì sao một chuỗi ký tự có độ dài 100 byte không có nghĩa toàn document BSON đúng 100 byte?

### Bài 2. Đếm số đơn theo status

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** Mỗi status có **8** đơn nếu chỉ có 24 document mẫu.

### Bài 3. Count cho tenant-A

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

**Kỳ vọng:** `NEW`, `PAID` và `SHIPPED` đều có `count:6`.

### Bài 4. Top 5 theo amount

~~~javascript
db.orders.aggregate([
  { $sort: { amount: -1, _id: 1 } },
  { $limit: 5 }
], { allowDiskUse: false });
~~~

**Câu hỏi:** Vì sao lệnh vẫn thành công trên bộ mẫu dù cấm spill? Khi nào top-N sort giúp giảm memory?

### Bài 5. Query sort có index

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $sort: { createdAt: -1, _id: -1 } },
  { $limit: 2 }
]);
~~~

**Kỳ vọng về dữ liệu:** `ord-018`, `ord-015`. Quan sát plan dùng index hay collection scan/sort.

### Bài 6. allowDiskUse true/false

Chạy cùng pipeline:

~~~javascript
const p = [
  { $match: { tenantId: "tenant-A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
];

db.orders.aggregate(p, { allowDiskUse: false });
db.orders.aggregate(p, { allowDiskUse: true });
~~~

**Câu hỏi:** Vì sao dữ liệu output trên bộ mẫu giống nhau? Bật spill có nghĩa “chắc chắn đã ghi file tạm” không?

### Bài 7. $push và kích thước array

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      ids: { $push: "$_id" }
    }
  }
]);
~~~

Với 24 document mẫu, các array nhỏ và lệnh có thể thành công.

**Câu hỏi:** Điều gì thay đổi nếu bạn thay `ids:{$push:"$_id"}` bằng `allOrders:{$push:"$$ROOT"}` trên một collection nhiều triệu document?

### Bài 8. $facet có giới hạn dữ liệu trang

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  {
    $facet: {
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $limit: 3 },
        { $project: { _id: 1, status: 1 } }
      ],
      meta: [
        { $count: "total" }
      ]
    }
  }
]);
~~~

**Kỳ vọng:** `meta[0].total = 18` và `data` có 3 document. Nếu bỏ `$limit`, rủi ro nào tăng ở collection lớn? Vì sao `allowDiskUse:true` không giải quyết được mọi giới hạn?

### Bài 9. $unwind làm tăng số document

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $unwind: "$items" },
  { $count: "lineCount" }
]);
~~~

**Kỳ vọng:** `lineCount:36`, không phải 18. Giải thích tác động lên `$group` hoặc `$sort` đặt sau `$unwind`.

### Bài 10. $lookup và giới hạn BSON

Sau khi nạp `orderLines`, chạy join cho `ord-001`. Quan sát `lines` gồm ba phần tử.

**Câu hỏi:** Nếu đơn có hàng triệu line, vì sao output một document chứa mọi line có thể không hợp lệ? Khi nào phải chuyển sang truy vấn collection con theo trang?

### Bài 11. Nhận diện lỗi theo mô tả

Chọn giải pháp:

| Tình huống | Giải pháp chính |
|---|---|
| Một document trả về lớn hơn 16 MiB | Trả nhiều document nhỏ, phân trang hoặc giảm field |
| Sort lớn không index, memory limit | Index/filter/top N, và spill nếu stage hỗ trợ |
| Facet data array quá lớn | `$limit` trong nhánh, tách query hoặc đổi output |
| $push dồn hàng triệu document | Không `$push:"$$ROOT"`; dùng count/summary hoặc query riêng |
| Pipeline có hơn 1.000 stage | Đơn giản hóa generator/pipeline |
| Disk spill làm ổ đĩa gần đầy | Giảm spill, tối ưu query và quản lý storage |
| Query đã chạy hết `maxTimeMS` | Giảm khối lượng công việc, không biến timeout thành kết quả rỗng |

### Bài 12. Thiết kế lại báo cáo lớn

Yêu cầu ban đầu: tạo một document chứa toàn bộ order của mọi tenant:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      allOrders: { $push: "$$ROOT" }
    }
  }
]);
~~~

**Bài tập:** Đề xuất hai endpoint:

1. Endpoint **summary**: tổng số đơn và tổng tiền theo tenant/status.
2. Endpoint **detail**: danh sách đơn theo tenant với filter, sort và pagination.

Giải thích vì sao thiết kế mới tránh việc đẩy tất cả order vào một BSON document và dễ kiểm soát độ trễ hơn.

### Bài 13. Stage limit

Giả sử một bộ tạo pipeline tự thêm 1.100 stage `$set` lặp lại để tạo cùng một field. Nó có rủi ro gì? Có nên tăng `allowDiskUse` hay chỉnh ngưỡng memory để sửa không?

*Gợi ý:* Đây là giới hạn **số stage**, không phải dung lượng RAM. Cần sửa generator và gộp những expression có thể gộp.

### Bài 14. Đọc tín hiệu usedDisk

Một truy vấn có:

~~~text
usedDisk: true
executionTimeMillis tăng mạnh
totalDocsExamined rất lớn
~~~

Bạn nên điều tra theo trình tự nào?

*Gợi ý:* Kiểm tra filter/index, sort/group, số lượng document đi qua stage, memory/stats, I/O và concurrency; không chỉ bật thêm disk usage.

### Bài 15. Giới hạn theo phiên bản

Trên một dự án dùng nhiều MongoDB Server version:

- Tìm hiểu `allowDiskUseByDefault` có từ phiên bản nào.
- Xác định phiên bản nào mô tả giới hạn bộ nhớ tổng query operation.
- Vì sao cùng một pipeline có thể chạy khác nhau tùy config dù dữ liệu gần giống?
- Vì sao không nên giả định mọi stage, đặc biệt `$facet`, đều có thể spill?

## 29. Các lỗi và hiểu nhầm thường gặp

| Hiểu nhầm/triệu chứng | Giải thích đúng |
|---|---|
| “Aggregation chỉ trả tối đa tổng 16 MiB” | Giới hạn 16 MiB là **mỗi result document**, cursor có thể trả nhiều document |
| “Bật allowDiskUse thì document 40 MiB hợp lệ” | Không, BSON result vẫn giới hạn 16 MiB |
| “Mọi stage đều spill được” | Chỉ những stage/cơ chế được hỗ trợ; `$facet` không spill |
| “Facet có 100 MB nên result được 100 MB” | Final result vẫn phải theo 16 MiB BSON |
| “$push luôn spill như $group” | `$push` có giới hạn accumulator riêng không spill |
| “100 MB là trần tổng RAM tuyệt đối của mọi aggregation” | Có giới hạn theo stage; các phiên bản mới còn có giới hạn operation riêng |
| “MongoDB 6.0 mặc định luôn spill” | Hành vi phụ thuộc `allowDiskUseByDefault` và override command |
| “Spill đồng nghĩa query thất bại” | Spill có thể giúp query hoàn thành, nhưng tăng I/O/latency |
| “Không thấy usedDisk trong explain tức chắc chắn không spill” | Trường output tùy version/stage; kiểm tra nguồn quan sát phù hợp |
| “Pipeline 1.100 stage sẽ chạy nếu có nhiều RAM” | Vượt giới hạn 1.000 stage, không giải bằng RAM |
| “$sort + $limit vẫn phải giữ mọi record” | Optimizer có thể giữ top N khi điều kiện tối ưu phù hợp |
| “$project đầu pipeline luôn nhanh hơn” | Có optimizer và dependency; cần đo và giữ đúng nghĩa |
| “$lookup rồi $unwind luôn tránh document lớn” | `$lookup` có thể tạo array lớn trước khi unwind |
| “Sort theo index nào cũng được” | Index phải phục vụ filter/sort pattern, thứ tự và collation phù hợp |
| “Timeout thì trả count=0” | Timeout là không có kết quả xác nhận, không phải zero |
| “allowDiskUse bảo vệ RAM ứng dụng Java” | Không; nếu client gom mọi result vào List, RAM client vẫn có thể tăng |
| “Một pipeline có output nhỏ chắc chắn ít RAM” | Blocking stage có thể xử lý lượng dữ liệu lớn trước khi trả output nhỏ |

## 30. Checklist triển khai production

Trước khi đưa một aggregation pipeline lớn vào hệ thống thật, cần thống nhất:

1. **Đầu vào:** Tập dữ liệu có thể lớn bao nhiêu, gồm bao nhiêu document và mảng có thể dài đến mức nào?
2. **Mục tiêu output:** Cần một summary nhỏ, một trang kết quả hay toàn bộ dữ liệu chi tiết?
3. **Giới hạn BSON:** Có nguy cơ một document kết quả chứa array quá lớn không?
4. **Số stage:** Pipeline do generator xây có thể vượt 1.000 stage không?
5. **Blocking stages:** Có `$sort`, `$group`, `$bucket`, `$setWindowFields` hoặc facet lớn không?
6. **Index:** Filter và sort có dùng index đúng pattern và collation không?
7. **Cardinality:** `$unwind`/`$lookup` có nhân số record trung gian lên rất nhiều lần không?
8. **Allow disk:** Có chủ ý cho phép spill không? Tham số server có khác giữa các môi trường không?
9. **Ngoại lệ:** `$facet`, `$push` và output 16 MiB có thiết kế tránh giới hạn riêng chưa?
10. **Time budget:** Query có `maxTimeMS`/SLA và cách xử lý timeout rõ không?
11. **Monitoring:** Có quan sát `usedDisk`, spills, scan, CPU/RAM/I/O và p95/p99 latency không?
12. **Tài nguyên:** Cluster có đủ dung lượng tạm, khả năng autoscale và cách chống quá tải đồng thời không?
13. **Ứng dụng:** Driver có duyệt cursor theo batch, thay vì load mọi document vào RAM không?
14. **Quyền truy cập:** Pipeline có lọc đúng tenant, data scope và tránh lộ field nhạy cảm không?
15. **Tương thích:** Có xác nhận major version MongoDB và các tham số memory tương ứng không?

## 31. Kết luận

Có ba nhóm giới hạn dễ nhầm nhất trong MongoDB Aggregation:

- **Kích thước của từng document:** mỗi result document được trả về hoặc lưu trữ phải nằm trong giới hạn BSON **16 MiB**.
- **Cấu trúc của pipeline:** một pipeline chỉ được có tối đa **1.000 stage** theo giới hạn server.
- **Tài nguyên khi chạy:** các stage blocking có thể cần nhiều RAM, và một số stage hỗ trợ spill khi `allowDiskUse` cho phép; riêng `$facet`, `$push` và các giới hạn khác không tự biến mất.

Bài học thực hành quan trọng nhất là **thiết kế dữ liệu và pipeline để không phải gom vô hạn document vào một array**. Hãy tận dụng `$match` sớm, index phục vụ sort, `$limit` cho top N, group bằng accumulator nhỏ, phân trang dữ liệu chi tiết và đo explain/monitoring. Cho phép disk spill là một giải pháp vận hành hữu ích khi thật sự cần, nhưng không thay thế việc kiểm soát cardinality, kích thước BSON, số stage và độ trễ của hệ thống.

## Tài liệu chính thức

- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Manual — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Manual — $sort](https://www.mongodb.com/docs/manual/reference/operator/aggregation/sort/)
- [MongoDB Manual — $facet](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/)
- [MongoDB Manual — $group](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB Manual — $setWindowFields](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setWindowFields/)
- [MongoDB Manual — explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Java Sync Driver — Aggregation](https://www.mongodb.com/docs/drivers/java/sync/current/aggregation/)
