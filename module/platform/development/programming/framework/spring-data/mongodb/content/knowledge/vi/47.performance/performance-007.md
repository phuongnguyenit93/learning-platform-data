# Giới hạn dữ liệu trung gian từ `$lookup`, `$unwind` và `$group`

## 1. Bài toán: kết quả cuối nhỏ nhưng truy vấn vẫn tốn bộ nhớ

Trong ứng dụng **Spring Data MongoDB**, một API báo cáo có thể chỉ trả về 20 sản phẩm bán chạy nhất nhưng lại phải xử lý hàng triệu dòng chi tiết đơn hàng để tính được 20 kết quả đó. Dữ liệu trung gian phát sinh khi kết hợp `$lookup`, `$unwind` và `$group` thường lớn hơn rất nhiều so với kết quả hiển thị.

Ví dụ dữ liệu gồm hai collection:

- `orders`: `_id`, `tenantId`, `status`, `placedAt`; mỗi document đại diện một đơn hàng.
- `order_items`: `_id`, `orderId`, `productId`, `state`, `quantity`, `netAmount`; mỗi document đại diện một dòng hàng.

Yêu cầu: tìm **20 sản phẩm có doanh thu cao nhất** trong các đơn đã thanh toán của một tenant, trong một khoảng thời gian. Doanh thu được tính bằng tổng `netAmount` của các dòng `state = "VALID"`. Giả sử một ngày có **10.000 đơn**, mỗi đơn có trung bình **200 dòng**; kết hợp sai thứ tự có thể khiến pipeline phải xử lý khoảng **2 triệu dòng** trước khi trả về 20 sản phẩm.

Bài học này giúp bạn:

1. Phân biệt **số document trung gian**, **độ lớn BSON** và **bộ nhớ thực thi** của pipeline.
2. Ước lượng độ phình dữ liệu qua `$lookup` → `$unwind` → `$group`.
3. Thiết kế pipeline giảm fan-out, giảm kích thước document và giảm trạng thái tích lũy.
4. Áp dụng các kỹ thuật đó với `MongoTemplate`, Spring Data Aggregation API và truy vấn reactive.
5. Dùng `explain("executionStats")` cùng đo tải thực tế để xác nhận cải thiện.

## 2. Ba phép toán tạo chi phí trung gian như thế nào?

### 2.1. `$lookup`: tăng số phần tử trong document cha

Một `$lookup` theo điều kiện `orders._id = order_items.orderId` thường tạo một trường mảng `items` trên mỗi document đơn hàng:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    as: "items"
  }
}
```

Nếu có `N` đơn đi vào `$lookup`, và đơn thứ `i` khớp `k_i` dòng hàng, số document ở đầu ra logic của phép join vẫn có thể là `N`, nhưng mỗi document có thể mang thêm mảng `items` chứa `k_i` phần tử. Dung lượng dữ liệu trung gian phụ thuộc vào **kích thước từng dòng hàng** và `k_i`, không chỉ số đơn.

`$lookup` trên `foreignField` không có index có thể quét collection phụ nhiều lần. Khi một document cha khớp hàng nghìn document con, chi phí dựng, xử lý và chuyển dữ liệu join có thể cao dù cuối cùng chỉ cần một tổng doanh thu.

### 2.2. `$unwind`: mở rộng cardinality

```javascript
{ $unwind: "$items" }
```

Mỗi phần tử của mảng `items` trở thành một document đầu ra. Nếu tất cả đơn có ít nhất một dòng hàng, số document sau `$unwind` là:

\[
N_{\text{after unwind}} = \sum_{i=1}^{N} k_i
\]

Với 10.000 đơn × 200 dòng/đơn, con số xấp xỉ **2.000.000 document**. Trong dòng chảy logic sau `$unwind`, các trường của document cha có thể bị lặp lại cho từng dòng con. Nếu giữ cả địa chỉ, ghi chú, lịch sử trạng thái và các mảng lớn từ document cha, kích thước mỗi bản ghi trung gian tăng vô ích.

Một số trường hợp cần chú ý:

| Mảng trước `$unwind` | `preserveNullAndEmptyArrays: false` (mặc định) | `preserveNullAndEmptyArrays: true` |
| --- | --- | --- |
| Có 3 phần tử | 3 document | 3 document |
| Mảng rỗng | 0 document | 1 document |
| Thiếu/null | 0 document | 1 document |

Không tự động bật `preserveNullAndEmptyArrays: true` khi báo cáo chỉ tính dòng hàng hợp lệ; các document thiếu dòng hàng có thể làm sai kết quả đếm nếu logic phía sau không phân biệt rõ.

### 2.3. `$group`: thu nhỏ đầu ra nhưng giữ trạng thái trong RAM

```javascript
{
  $group: {
    _id: "$items.productId",
    revenue: { $sum: "$items.netAmount" },
    lineCount: { $sum: 1 }
  }
}
```

`$group` là **blocking stage**: phải xử lý toàn bộ đầu vào liên quan rồi mới cho ra kết quả tổng hợp theo từng khóa. Số đầu ra có thể chỉ còn vài nghìn sản phẩm, nhưng server vẫn cần giữ trạng thái tích lũy theo số nhóm phân biệt và accumulator.

Hai thiết kế cùng có 1.000 nhóm có thể có bộ nhớ rất khác:

```javascript
// Thường gọn: chỉ lưu tổng và số lượng trên mỗi nhóm.
{ $group: {
    _id: "$items.productId",
    revenue: { $sum: "$items.netAmount" },
    count: { $sum: 1 }
} }

// Dễ phình: lưu mọi document con trong mảng của từng nhóm.
{ $group: {
    _id: "$items.productId",
    allItems: { $push: "$items" }
} }
```

`$sum` và `$count` thường chỉ cần trạng thái nhỏ trên mỗi nhóm. `$push`/`$addToSet` tích lũy mảng nên có thể dùng lượng bộ nhớ và BSON lớn hơn rất nhiều. Không dùng `$push: "$$ROOT"` để lấy dữ liệu “cho tiện” nếu API chỉ cần tổng số và doanh thu.

### 2.4. Tư duy theo hai trục: fan-out và độ rộng document

| Điểm trong pipeline | Số document logic | Độ rộng document | Chi phí dễ tăng |
| --- | ---: | --- | --- |
| `$match` đơn theo tenant/ngày/trạng thái | Số đơn khớp | Trường gốc của đơn | Scan khi thiếu index |
| `$project` chỉ giữ `_id` | Không đổi | Nhỏ | Chi phí đọc nếu thiếu index phù hợp |
| `$lookup` các dòng hàng | Có thể không đổi | Mảng `items` có thể rất lớn | Join scan, số kết quả khớp, dựng mảng |
| `$unwind` mảng `items` | Có thể tăng mạnh | Lặp metadata cha theo dòng | CPU, xử lý, dữ liệu chuyển stage |
| `$group` theo sản phẩm | Số productId phân biệt | Phụ thuộc accumulator | Memory/spill, mảng quá lớn |
| `$sort` rồi `$limit: 20` | Còn 20 | Nhỏ nếu group đã gọn | Sort nếu nhóm đầu ra vẫn lớn |

Các số ở bảng là **cardinality logic**, không khẳng định MongoDB luôn giữ toàn bộ document trung gian trong RAM. Query optimizer có thể gộp stage và engine có thể dùng cơ chế thực thi theo luồng.

## 3. Giới hạn thực tế của MongoDB

### 3.1. Giới hạn kích thước BSON 16 MiB

MongoDB giới hạn **mỗi document kết quả trả về** là **16 MiB BSON**. Trong quá trình xử lý aggregation, một số document trung gian có thể vượt 16 MiB; vì vậy tránh kết luận rằng mọi đầu ra tạm của `$lookup` sẽ lập tức lỗi khi chạm ngưỡng này.

Tuy nhiên, việc giữ mảng join lớn hoặc `$group` với `$push` rồi xuất một document kết quả sẽ dễ chạm giới hạn 16 MiB. Ví dụ `$group: { _id: null, allOrders: { $push: "$$ROOT" } }` có thể gây lỗi khi dữ liệu nhiều, dù tổng số document trả về chỉ là một.

Giảm kích thước bằng cách **không gom toàn bộ document thành mảng**, chỉ giữ số liệu tổng hợp hoặc tách thành các bản ghi kết quả độc lập khi nghiệp vụ cho phép.

### 3.2. Bộ nhớ 100 MB của các stage blocking và khả năng spill

Một số stage như `$group`, `$sort`, `$bucket` có ngưỡng bộ nhớ thực thi khoảng **100 MB/stage**. Khi vượt ngưỡng, stage hỗ trợ spill có thể ghi tạm xuống đĩa nếu `allowDiskUse` được cho phép; nếu không, pipeline có thể lỗi vì thiếu bộ nhớ.

Từ MongoDB **6.0**, thiết lập server `allowDiskUseByDefault` quy định hành vi mặc định. Lệnh aggregation có thể ghi đè bằng `{ allowDiskUse: true }` hoặc `{ allowDiskUse: false }`.

```javascript
db.orders.aggregate(
  [ /* các stage báo cáo */ ],
  {
    allowDiskUse: true,
    maxTimeMS: 30_000,
    comment: "performance-007-report"
  }
);
```

**`allowDiskUse: true` không biến pipeline thành vô hạn bộ nhớ và không khắc phục thuật toán sai.** Một số accumulator như `$push` có giới hạn mảng tích lũy riêng, không thể spill mảng đó xuống đĩa. Các giới hạn nội bộ khác vẫn có thể phát sinh theo stage hoặc phiên bản server. Nếu cần nhiều thời gian xử lý và dùng đĩa tạm lớn, truy vấn vẫn có thể chậm hoặc tạo áp lực I/O.

Từ MongoDB **9.0**, còn có **giới hạn bộ nhớ tổng theo operation** bên cạnh giới hạn từng stage. Mặc định là giá trị lớn hơn giữa **1 GiB** và **20% bộ nhớ khả dụng cho tiến trình server**; thông số có thể cấu hình. Vì vậy khi điều tra lỗi memory trên bản mới, cần phân biệt ngưỡng stage, accumulator và operation tổng.

### 3.3. Những giới hạn liên quan khác

- Một aggregation pipeline có giới hạn **1.000 stage** sau quá trình phân tích, tối ưu. Tách stage thừa là hữu ích nhưng số stage thường ít quan trọng hơn cardinality và index.
- `$lookup` có các hạn chế theo schema, index, phiên bản server, cấu hình sharding và loại collection. Không suy rằng `allowDiskUse` sẽ tự xử lý mọi vấn đề phát sinh khi một mảng join quá lớn.
- `$group` không bảo đảm thứ tự đầu ra. Nếu muốn top 20 theo doanh thu, cần `$sort` rõ ràng trước `$limit`.
- Cursor và `batchSize` điều tiết lượng kết quả chuyển về client theo từng batch; **không** giới hạn số bản ghi mà các stage trong server phải xử lý.

## 4. Pipeline dễ gây dữ liệu trung gian lớn

Một cách viết dễ gặp là join toàn bộ dòng hàng, trải mảng, rồi mới lọc đơn:

```javascript
const start = ISODate("2026-10-01T00:00:00Z");
const end   = ISODate("2026-11-01T00:00:00Z");

db.orders.aggregate([
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      as: "items"
    }
  },
  { $unwind: "$items" },
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: { $gte: start, $lt: end },
      "items.state": "VALID"
    }
  },
  {
    $group: {
      _id: "$items.productId",
      revenue: { $sum: "$items.netAmount" },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 20 }
]);
```

Vấn đề của cách biểu diễn này:

1. Điều kiện `tenantId`, `status` và `placedAt` độc lập với join, nhưng được viết sau `$lookup`; nếu không được đẩy sớm, nhiều đơn không cần thiết vẫn tham gia join.
2. `$lookup` lấy **toàn bộ field** của từng dòng hàng dù `$group` chỉ dùng `productId` và `netAmount`.
3. `$unwind` tạo fan-out trước khi lọc dòng `state = "VALID"`.
4. Phần lớn dữ liệu được tính rồi bỏ đi để lấy 20 nhóm cuối cùng.

MongoDB có **query optimizer**, nên không phải lúc nào thực thi cũng đúng thứ tự vật lý như văn bản trên. Chẳng hạn, `$match` độc lập có thể được di chuyển và chuỗi `$lookup` → `$unwind` → `$match` có thể được **coalesce** thành một `$lookup` nội bộ. Vì vậy hãy xem `explain` trước khi kết luận bản viết này chắc chắn chậm.

## 5. Thiết kế pipeline giảm dữ liệu ngay từ nguồn

### 5.1. `$match` đơn hàng trước khi join; giữ trường cần thiết

Chỉ đưa các đơn thuộc tenant, trạng thái và khoảng thời gian cần báo cáo vào `$lookup`.

```javascript
const start = ISODate("2026-10-01T00:00:00Z");
const end   = ISODate("2026-11-01T00:00:00Z");

db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: { $gte: start, $lt: end }
    }
  },
  { $project: { _id: 1 } },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $match: { state: "VALID" } },
        { $project: { _id: 0, productId: 1, netAmount: 1 } }
      ],
      as: "items"
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.productId",
      revenue: { $sum: "$items.netAmount" },
      lineCount: { $sum: 1 }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 20 }
], {
  allowDiskUse: true,
  maxTimeMS: 30_000
});
```

Phiên bản `$lookup` kết hợp `localField`/`foreignField` với `pipeline` được hỗ trợ trên MongoDB **5.0+**. `pipeline` lọc và rút gọn các document ngoại trước khi đưa kết quả join về phía pipeline chính.

Thiết kế này nhằm giảm **số đơn tham gia**, **số dòng hàng được đưa vào mảng join**, và **độ rộng của mỗi dòng**. Việc giảm dữ liệu thường quan trọng hơn cho phép spill xuống đĩa.

### 5.2. Index theo bộ lọc và khóa join

Trên collection `orders`, bộ lọc là tenant, trạng thái và khoảng ngày; một compound index gợi ý:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  placedAt: 1
});
```

Trên collection `order_items`, điều kiện join là `orderId` và chỉ dùng dòng hợp lệ:

```javascript
db.order_items.createIndex({
  orderId: 1,
  state: 1
});
```

Đây là **index ứng viên**, không phải công thức áp dụng cho mọi workload. Cần kiểm tra `explain` xem server có dùng index tương ứng không, số khóa/document đọc thực tế ra sao, và đánh đổi với chi phí ghi dữ liệu. Với `$lookup` dùng `let`/`$expr`, khả năng dùng index phụ thuộc điều kiện so sánh và các hạn chế (ví dụ so sánh field với hằng đủ điều kiện, xử lý giá trị rỗng và multikey).

Không tạo nhiều index lớn chỉ để tránh `COLLSCAN` trên một dataset rất nhỏ; giá trị của index được đánh giá qua workload và khả năng chọn lọc.

### 5.3. Khi chỉ cần tổng, gom nhỏ dữ liệu ở collection ngoại

Nếu một đơn có nhiều dòng cùng `productId`, có thể **tổng hợp theo từng đơn và sản phẩm ngay trong `$lookup.pipeline`** trước khi đưa về luồng chính:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    pipeline: [
      { $match: { state: "VALID" } },
      {
        $group: {
          _id: "$productId",
          revenue: { $sum: "$netAmount" },
          lineCount: { $sum: 1 }
        }
      }
    ],
    as: "productTotals"
  }
}
```

Sau đó `$unwind: "$productTotals"` và `$group` lần nữa theo `"$productTotals._id"`, cộng `revenue` và `lineCount` từ từng đơn:

```javascript
{ $unwind: "$productTotals" },
{
  $group: {
    _id: "$productTotals._id",
    revenue: { $sum: "$productTotals.revenue" },
    lineCount: { $sum: "$productTotals.lineCount" }
  }
}
```

Kỹ thuật này có lợi khi **mỗi đơn có nhiều dòng trùng sản phẩm**; nếu hầu hết mỗi sản phẩm chỉ xuất hiện một lần trong đơn thì một `$group` bổ sung ở foreign pipeline có thể làm chậm hơn. Cần so sánh số nhóm và số bản ghi trung gian trước khi quyết định. Ngoài ra, `$group` trong subpipeline cũng phải tuân theo giới hạn bộ nhớ.

### 5.4. Kiểm soát fan-out mà không phá hỏng kết quả

Một số lựa chọn có ý nghĩa khác nhau:

| Kỹ thuật | Khi nên dùng | Rủi ro về tính đúng |
| --- | --- | --- |
| `$match` trên parent trước `$lookup` | Luôn ưu tiên khi điều kiện độc lập với dữ liệu join | Không đổi kết quả nếu đúng phạm vi lọc. |
| `$match` trong `$lookup.pipeline` | Chỉ lấy dòng con thỏa điều kiện báo cáo | Phải bảo toàn ngữ nghĩa nếu vẫn cần parent không có dòng con. |
| `$project` trong foreign pipeline | Chỉ lấy trường cần tính toán | Không bỏ trường cần dùng ở stage sau. |
| `$limit` trong foreign pipeline | Nghiệp vụ thực sự chỉ cần tối đa `K` phần tử mỗi parent | **Làm sai tổng** nếu nghiệp vụ phải tính tất cả dòng con. |
| `$sort` + `$limit` trước `$lookup` | Chỉ phân tích `K` parent được chọn theo tiêu chí có trước join | Làm sai top `K` theo chỉ số chỉ biết sau join, như doanh thu. |
| `$group` với `$sum`/`$count` | Cần số liệu tổng hợp | Cần định nghĩa đúng dòng được tính và kiểu tiền tệ. |
| `$group` với `$push` | Thực sự cần danh sách đầy đủ | Có thể đụng giới hạn mảng tích lũy và BSON. |

Ví dụ sai phổ biến:

```javascript
// KHÔNG dùng khi cần tổng doanh thu của mọi dòng hàng.
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    pipeline: [
      { $sort: { netAmount: -1, _id: 1 } },
      { $limit: 5 }
    ],
    as: "items"
  }
}
```

Pipeline này chỉ xét **5 dòng có doanh thu cao nhất mỗi đơn**, nên tổng doanh thu theo sản phẩm không còn là tổng tất cả dòng. Nó chỉ đúng nếu báo cáo được định nghĩa là “top 5 dòng mỗi đơn”. Nếu dùng `$limit` theo nghiệp vụ, đặt `$sort` có khóa phụ ổn định để có kết quả tái lập.

### 5.5. Tránh mảng dài ở `$group`

Nếu báo cáo cần một vài giá trị nổi bật thay vì danh sách đầy đủ, cân nhắc các accumulator giới hạn số phần tử như `$topN`, `$firstN` (có từ MongoDB 5.2), hoặc tính tổng rồi chọn top qua `$sort` + `$limit`. Các accumulator giới hạn có điều kiện sử dụng và không thay thế một cách máy móc cho tổng hợp đầy đủ.

Ví dụ danh sách **3 dòng có giá trị cao nhất của mỗi sản phẩm** trên phiên bản hỗ trợ:

```javascript
{
  $group: {
    _id: "$productId",
    topItems: {
      $topN: {
        n: 3,
        sortBy: { netAmount: -1, _id: 1 },
        output: { orderId: "$orderId", netAmount: "$netAmount" }
      }
    }
  }
}
```

Đây là kết quả **top 3**, không phải tất cả dòng. `$topN` vẫn tiêu thụ bộ nhớ và tuân theo giới hạn tương ứng; nó chỉ tránh tích lũy mảng tỷ lệ thuận với số dòng của một nhóm.

Nếu tiền phải tính chính xác, ưu tiên lưu `netAmount` bằng **Decimal128** (hoặc số nguyên đơn vị nhỏ nhất theo thiết kế) thay vì `double` dễ sai số.

## 6. MongoDB có thể gộp `$lookup`, `$unwind`, `$match`

Ví dụ chuỗi stage:

```javascript
{
  $lookup: {
    from: "order_items",
    localField: "_id",
    foreignField: "orderId",
    as: "items"
  }
},
{ $unwind: "$items" },
{ $match: { "items.state": "VALID" } }
```

Khi điều kiện cho phép, MongoDB optimizer **coalesce** `$unwind` vào `$lookup`, và cũng có thể đưa điều kiện `$match` liên quan đến `items` vào lookup. Trong `explain`, bạn có thể thấy `$lookup` nội bộ có `pipeline` và trường `unwinding`. Việc này tránh phải vật hóa một số mảng trung gian lớn.

Điểm quan trọng: **không đánh giá tối ưu chỉ dựa vào thứ tự JSON đầu vào**. Một pipeline viết rõ `$match` và `$project` từ đầu vẫn dễ hiểu, dễ quản lý và giúp thể hiện mục đích lọc; nhưng kết luận về hiệu năng phải dựa vào kế hoạch thực thi.

Các thao tác khác có thể ảnh hưởng tối ưu:

- `$sort` + `$limit` liền nhau có thể được kết hợp để giữ top `K` thay vì sort toàn bộ. Nếu có `$unwind` hoặc `$group` **làm thay đổi số document ở giữa**, optimizer không thể gộp tùy ý mà vẫn giữ ngữ nghĩa.
- `$match` đặt sớm có cơ hội dùng index ở collection gốc; `$sort` đầu pipeline có thể dùng index trong điều kiện phù hợp.
- `$lookup` equality join có thể xuất hiện `EQ_LOOKUP` khi sử dụng Slot-Based Execution Engine trên các phiên bản hỗ trợ; `$lookup` chạy subpipeline ngoại có thể không đi theo cùng đường tối ưu SBE. Không coi mọi pipeline join đều phải có `EQ_LOOKUP`.

## 7. Triển khai với Spring Data MongoDB

### 7.1. Pipeline gọn bằng Aggregation API

Ví dụ dưới đây dùng các thao tác chuẩn của `MongoTemplate`, phù hợp khi chỉ cần join đơn giản; các import chính:

```java
import java.time.Instant;
import java.util.List;

import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOptions;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

// mongoTemplate là bean Spring đã inject.
Aggregation pipeline = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is("tenant-01")
            .and("status").is("PAID")
            .and("placedAt")
                .gte(Instant.parse("2026-10-01T00:00:00Z"))
                .lt(Instant.parse("2026-11-01T00:00:00Z"))
    ),
    Aggregation.project("_id"),
    Aggregation.lookup("order_items", "_id", "orderId", "items"),
    Aggregation.unwind("items"),
    Aggregation.match(Criteria.where("items.state").is("VALID")),
    Aggregation.group("items.productId")
        .sum("items.netAmount").as("revenue")
        .count().as("lineCount"),
    Aggregation.sort(Sort.by(
        Sort.Order.desc("revenue"),
        Sort.Order.asc("_id")
    )),
    Aggregation.limit(20)
).withOptions(
    AggregationOptions.builder().allowDiskUse(true).build()
);

AggregationResults<Document> result =
    mongoTemplate.aggregate(pipeline, "orders", Document.class);
List<Document> topProducts = result.getMappedResults();
```

Thứ tự stage ở đây đã lọc parent sớm, nhưng phép `lookup(...)` đơn giản vẫn chưa giảm trường của foreign document. Khi dữ liệu join lớn, hãy chọn `LookupOperation` builder hỗ trợ `pipeline` của phiên bản Spring Data đang dùng, hoặc cung cấp một `AggregationOperation` cho stage BSON tùy chỉnh.

### 7.2. Dùng `AggregationOperation` cho `$lookup.pipeline`

Ví dụ tạo trực tiếp stage BSON trong ứng dụng Java:

```java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;

AggregationOperation reducedLookup = context ->
    new Document("$lookup",
        new Document("from", "order_items")
            .append("localField", "_id")
            .append("foreignField", "orderId")
            .append("pipeline", List.of(
                new Document("$match",
                    new Document("state", "VALID")),
                new Document("$project",
                    new Document("_id", 0)
                        .append("productId", 1)
                        .append("netAmount", 1))
            ))
            .append("as", "items"));

// Thay Aggregation.lookup(...) của pipeline bên trên bằng reducedLookup.
// Đồng thời bỏ Aggregation.match("items.state") phía sau vì đã lọc
// trong subpipeline. Các stage group/sort/limit giữ nguyên.
```

Lưu ý khi dùng BSON trực tiếp: chuỗi `"orderId"`, `"netAmount"` là **tên field lưu trong MongoDB**, có thể khác tên thuộc tính Java được khai báo qua `@Field`. Không nối chuỗi JSON có tham số từ request; hãy truyền giá trị qua API BSON/Criteria phù hợp để tránh sai kiểu ngày, ObjectId hoặc số.

`allowDiskUse(true)` chỉ quyết định quyền spill trong MongoDB; nó **không giới hạn số document** của `$lookup`/`$unwind` và không thay thế việc giảm dữ liệu. Nếu cần kiểm soát thời gian thực thi của API, cấu hình `maxTime`/timeout phù hợp trong `AggregationOptions` hoặc tầng thực thi tương ứng phiên bản.

### 7.3. Repository và reactive access

`@Aggregation` ở repository có thể tiện cho báo cáo cố định, nhưng pipeline vẫn chạy theo các stage MongoDB; không có việc repository tự giới hạn số dòng join khi method chỉ khai báo trả về `List<T>` ngắn.

Với `ReactiveMongoTemplate`, khác biệt chính là cách nhận kết quả dưới dạng `Flux`/`Mono`. Backpressure của Reactor chủ yếu điều tiết **dữ liệu phát về client**, không bảo đảm giảm số document server cần join/group trước đó.

```java
// Phần mở rộng minh họa: pipeline dùng lại từ ví dụ trên.
Flux<Document> stream = reactiveMongoTemplate
    .aggregate(pipeline, "orders", Document.class);
// Việc subscribe điều khiển luồng kết quả đến ứng dụng;
// không thay thế $match hoặc giảm fan-out ở phía server.
```

Đối với cả blocking và reactive, chỉ benchmark trên dataset có tỷ lệ `items/order` và phân bố `productId` gần với thực tế. Một test chỉ có vài dòng/đơn thường không phơi bày vấn đề của pipeline production.

## 8. Đo số document và chi phí thật bằng `explain`

### 8.1. Xác minh index và cardinality

Dùng pipeline thực tế của ứng dụng:

```javascript
const pipeline = [
  // Dán các stage từ mục 5.1.
];

db.orders.explain("executionStats").aggregate(
  pipeline,
  { allowDiskUse: true }
);
```

Đọc `explain` theo các câu hỏi:

| Thông tin cần xem | Ý nghĩa |
| --- | --- |
| `totalKeysExamined`, `totalDocsExamined` | Số khóa và document engine phải đọc. Lớn hơn nhiều so với document cần thiết có thể cho thấy index/filter chưa hiệu quả. |
| `IXSCAN`, `COLLSCAN` | Có dùng index hay quét collection ở đầu pipeline và các nhánh join? |
| `indexesUsed`, `collectionScans` (nếu được báo cho `$lookup`) | Join có khai thác index trên foreign collection hay không. |
| `nReturned`, `executionTimeMillisEstimate` ở từng stage khi có | Stage nào làm tăng cardinality hoặc tốn thời gian. |
| `usedDisk`, `spills`, thống kê bộ nhớ nếu có | Stage nào phải ghi đĩa hoặc chịu áp lực memory. |
| `unwinding` trong `$lookup`, `EQ_LOOKUP` khi xuất hiện | Optimizer có gộp join/unwind hoặc dùng lối thực thi join khác? |

**Hình dạng explain khác nhau theo MongoDB Server, query engine, loại stage và phiên bản.** Không kỳ vọng mọi trường ở trên đều có trong một kế hoạch. `executionTimeMillis` trong `explain` cũng không nhất thiết bằng latency của API thực khi có network, mapping, cache và tải đồng thời.

Một cách đo trước/sau có ý nghĩa:

1. Dùng **cùng tập dữ liệu, index, thông số server, khoảng thời gian báo cáo và phần trăm đơn có nhiều dòng hàng**.
2. Lưu số document được lọc trước join, ước lượng fan-out `items/order` (trung bình và p95/p99), số sản phẩm phân biệt và kích thước BSON đầu ra.
3. So sánh `explain("executionStats")` bản cũ với bản mới; xác nhận các index trên `orders` và `order_items` được sử dụng.
4. Chạy workload đại diện sau warm-up, đo **p50/p95/p99 latency**, CPU, RAM, I/O, `usedDisk`, tỷ lệ lỗi và thời gian thực thi trên server.
5. Kiểm tra kết quả trả về giống nhau trên dữ liệu mẫu có trường hợp cạnh biên; không đánh đổi tính đúng lấy tốc độ.

Để có hình dung về số dòng join, có thể chạy một pipeline **riêng** trên tập đơn đã lọc:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-01",
      status: "PAID",
      placedAt: {
        $gte: ISODate("2026-10-01T00:00:00Z"),
        $lt: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  {
    $lookup: {
      from: "order_items",
      localField: "_id",
      foreignField: "orderId",
      pipeline: [
        { $match: { state: "VALID" } },
        { $count: "n" }
      ],
      as: "stats"
    }
  },
  {
    $project: {
      validItemCount: {
        $ifNull: [ { $first: "$stats.n" }, 0 ]
      }
    }
  },
  {
    $group: {
      _id: null,
      orderCount: { $sum: 1 },
      validItemTotal: { $sum: "$validItemCount" },
      maxValidItemsPerOrder: { $max: "$validItemCount" }
    }
  }
]);
```

Đây là **truy vấn đo đạc** nên nó cũng tiêu tốn tài nguyên. Chạy có giới hạn và trên môi trường phù hợp; không vô tình đưa nó vào request path production.

## 9. Những lựa chọn sai thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| `$lookup` trước mọi điều kiện lọc | Join nhiều parent không cần thiết. | `$match` theo field parent càng sớm càng tốt; kiểm tra optimizer bằng explain. |
| Không có index trên `foreignField` | Join có thể quét nhiều document ngoại. | Thiết kế index theo khóa join và điều kiện lọc thực tế. |
| `$unwind` mảng lớn rồi `$project` cuối cùng | Nhiều document trung gian mang các field không cần. | Giảm trường trước join và trong subpipeline; kiểm tra tối ưu của engine. |
| `$group` + `$push: "$$ROOT"` khi chỉ cần đếm | Mảng lớn, lỗi memory/BSON dù đã bật spill. | Dùng `$sum`, `$count`, accumulator gọn hoặc top-N có giới hạn. |
| Thêm `$limit` tùy tiện sau `$lookup` | Làm sai kết quả tổng và top 20. | Chỉ limit khi đó là yêu cầu nghiệp vụ, sau sort xác định. |
| Nghĩ `allowDiskUse` là giải pháp hiệu năng | Chậm do I/O và có thể vẫn lỗi giới hạn riêng. | Giảm cardinality, độ rộng, số nhóm và đo `usedDisk`. |
| Đo `batchSize` thấp rồi tin join đã nhẹ | Server vẫn phải tính group trước khi trả cursor. | Đo pipeline và explain ở phía server. |
| Bỏ `$sort` trước top 20 | Kết quả không có thứ tự được bảo đảm. | `$sort` theo chỉ số và khóa phụ, rồi `$limit`. |
| Dùng `double` cho tiền khi cộng nhiều dòng | Có thể có sai số dấu phẩy động. | Dùng Decimal128 hoặc số nguyên đơn vị nhỏ nhất. |

## 10. Bài tập thực hành

Giả sử có **100.000 đơn hàng**, trung bình 80 dòng mỗi đơn; 5% đơn có trên 1.000 dòng. Mỗi `order_items` chứa thêm `description` 2 KiB và `extraAttributes` 3 KiB, nhưng báo cáo chỉ cần `productId`, `netAmount` và `state`.

1. Ước tính **số document logic sau `$unwind`** nếu join tất cả đơn: lấy trung bình 80 dòng/đơn; giải thích vì sao độ lệch phân bố p95/p99 vẫn có thể gây vấn đề cho các document có mảng rất lớn.
2. Viết lại pipeline đặt `$match` theo tenant/ngày/trạng thái trước join, `$project` tối giản và dùng `$lookup.pipeline` để lọc dòng hợp lệ.
3. Chọn index cho cả hai collection; chỉ ra những trường trong `explain` để xác nhận index hoạt động.
4. Chứng minh vì sao `{ $limit: 10 }` ở cuối pipeline và `{ $limit: 10 }` bên trong `$lookup.pipeline` **không tương đương**.
5. So sánh `$group: { all: { $push: "$$ROOT" } }` với `$group: { count: { $sum: 1 } }` khi có một sản phẩm xuất hiện trong 300.000 dòng.
6. Mô tả cách phân biệt lỗi do 16 MiB BSON, 100 MB stage, giới hạn riêng `$push` và giới hạn operation tổng trên MongoDB 9.0+.
7. Triển khai báo cáo bằng `MongoTemplate`, đo trước/sau bằng `explain` và thử chạy với `allowDiskUse: false` trong môi trường kiểm thử để quan sát giới hạn bộ nhớ; tránh chạy thử tải nặng trên production.

**Gợi ý:** Với 100.000 × 80, ước lượng có **8.000.000 document** sau khi trải mảng (nếu mọi đơn có số dòng xấp xỉ trung bình). Phép tính này chỉ đo cardinality logic; không suy ra MongoDB nhất thiết phải giữ cùng lúc 8 triệu document trong RAM. Bài làm tốt phải chứng minh các tổng doanh thu và thứ hạng vẫn chính xác sau tối ưu.

## Tài liệu tham khảo

- [MongoDB — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB — Aggregation Pipeline Optimization](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-optimization/)
- [MongoDB — `$lookup` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB — `$unwind` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/)
- [MongoDB — `$group` stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/)
- [MongoDB — `$push` accumulator](https://www.mongodb.com/docs/manual/reference/operator/aggregation/push/)
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html)
- [Spring Data MongoDB — AggregationOptions.Builder API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/aggregation/AggregationOptions.Builder.html)
