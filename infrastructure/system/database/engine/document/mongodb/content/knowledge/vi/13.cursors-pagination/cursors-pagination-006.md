# Đếm tổng số bản ghi và đánh đổi độ chính xác với độ trễ trong MongoDB

## 1. Vì sao tổng số bản ghi trở thành vấn đề khi phân trang?

Trong hệ thống MongoDB, một màn hình danh sách thường cần hai loại thông tin:

- **Dữ liệu trang hiện tại:** ví dụ 20 đơn hàng mới nhất.
- **Tổng số document phù hợp bộ lọc:** ví dụ có tất cả 125.430 đơn hàng đã thanh toán thuộc tenant đang đăng nhập.

Để lấy 20 document đầu, MongoDB có thể sử dụng index theo bộ lọc và thứ tự sắp xếp, sau đó dừng khi đã đủ `limit(20)`. Nhưng để trả lời **chính xác tổng cộng bao nhiêu document khớp**, server thường phải xét một phạm vi dữ liệu lớn hơn nhiều. Vì thế, một API có phần dữ liệu trang trả nhanh vẫn có thể bị chậm do truy vấn đếm tổng.

Bài học thuộc chương **Cursor và phân trang** của **Database Engine Document MongoDB**, nhằm trả lời các câu hỏi:

- Khi nào nên dùng `countDocuments()`, khi nào nên dùng `estimatedDocumentCount()`?
- Dùng `$count` hoặc `$facet` trong aggregation có lợi gì?
- Làm sao đếm theo đúng filter của trang, không vô tình đếm toàn collection?
- `skip/limit` có gây độ trễ ở trang sâu không, và cursor/keyset pagination giải quyết điều gì?
- Một con số chính xác ở thời điểm đếm có còn đúng khi user chuyển trang sau vài giây?
- Có thể bỏ qua exact total và chỉ trả `hasNext` không?
- Nên hiển thị total ước lượng/cached total như thế nào để không khiến người dùng hiểu nhầm?

Sau bài học, bạn có thể thiết kế API phân trang có ý nghĩa rõ, chọn chiến lược đếm phù hợp SLA, quan sát query plan và phân tích đánh đổi giữa độ chính xác, độ trễ và khả năng mở rộng.

## 2. Định nghĩa các con số thường gặp

Giả sử một danh sách có 6 đơn hàng thỏa bộ lọc, mỗi trang hiển thị 2 đơn hàng:

| Thành phần | Giá trị | Ý nghĩa |
|---|---:|---|
| `pageSize` | 2 | Số document tối đa trên một trang |
| `returnedCount` | 2 | Số document thực tế trả ở response này |
| `totalMatching` | 6 | Tổng số document thỏa filter trước phân trang |
| `totalPages` | 3 | Số trang dựa trên tổng và pageSize |
| `hasNext` | true với trang 1, 2 | Còn kết quả sau trang hiện tại hay không |

Công thức nếu tổng chính xác và `pageSize > 0`:

\[
\text{totalPages}=\left\lceil\frac{\text{totalMatching}}{\text{pageSize}}\right\rceil
\]

Nếu không có document, phép tính trả 0 trang. Một giao diện có thể tùy chọn hiển thị “Trang 1/1” khi rỗng, nhưng phải phân biệt quy ước UI với số trang tính toán.

**Không nhầm:** `items.length` hoặc `returnedCount` chỉ nói về trang hiện tại, không phải tổng số kết quả. Một trang có 20 document không có nghĩa toàn bộ kết quả chỉ có 20.

### 2.1. Bốn mức tin cậy của total

**Exact:** Count được tính bằng một truy vấn đếm theo filter. Nó chính xác theo ngữ nghĩa truy vấn ở thời điểm quan sát, nhưng dữ liệu vẫn có thể thay đổi sau đó.

**Estimated:** Con số ước lượng, thường được lấy từ metadata hoặc phương pháp thống kê. Không có cam kết khớp từng document.

**Cached:** Count từng được tính ở một thời điểm trước, nhưng có thể đã cũ nếu dữ liệu thay đổi.

**Not computed:** Không tính total; API chỉ cung cấp trang kết quả cùng `hasNext` hoặc `nextCursor`.

Các mức này có thể được biểu diễn bằng `totalKind` trong response. Không nên gọi một số ước lượng là chính xác chỉ vì trên bộ dữ liệu nhỏ giá trị tình cờ trùng nhau.

## 3. Chuẩn bị bộ dữ liệu thực hành

Mở `mongosh` kết nối tới MongoDB Server hoặc cluster bạn có quyền ghi, và dùng database riêng:

~~~javascript
use pagination_count_lab
~~~

Chèn 24 document mẫu vào collection `orders`:

~~~javascript
const demoOrders = [];

for (let i = 1; i <= 24; i++) {
  const id = "ord-" + String(i).padStart(3, "0");

  const status =
    i % 3 === 0 ? "PAID" :
    i % 3 === 1 ? "NEW" :
    "SHIPPED";

  demoOrders.push({
    _id: id,
    tenantId: i <= 18 ? "tenant-A" : "tenant-B",
    status: status,
    customerId: "cus-" + String((i % 7) + 1).padStart(2, "0"),
    amount: NumberDecimal(String(10 + i) + ".50"),
    createdAt: new Date(Date.UTC(2026, 9, i + 1, 9, 0, 0)),
    active: i % 4 !== 0
  });
}

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

Với collection ban đầu rỗng, kết quả là **24 document**. Mỗi lần chạy lại, `replaceOne` sẽ đưa 24 document có ID từ `ord-001` đến `ord-024` về nội dung mẫu, nhưng không xóa document khác. Vì vậy các con số kỳ vọng dưới đây giả định bạn chưa thêm record ngoài bộ dữ liệu đã nạp.

Phân bố:

- `tenant-A` có ID `ord-001` tới `ord-018`, tổng **18** document.
- `tenant-B` có ID `ord-019` tới `ord-024`, tổng **6** document.
- Mỗi tenant có ba trạng thái `NEW`, `SHIPPED` và `PAID` phân bố đều.
- `tenant-A` có đúng **6 đơn PAID**: `ord-003`, `ord-006`, `ord-009`, `ord-012`, `ord-015` và `ord-018`.
- `createdAt` có BSON Date và tăng theo chỉ số ID, giúp dự đoán kết quả sắp xếp.
- `active` bằng false với các ID có chỉ số chia hết cho 4.

Tạo index phục vụ filter và sort:

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_tenant_status_created_id" }
);
~~~

Các ví dụ chính sẽ dùng:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const pageSize = 2;
const sort = { createdAt: -1, _id: -1 };
~~~

Quan sát:

~~~javascript
db.orders.find(
  filter,
  { _id: 1, status: 1, createdAt: 1 }
).sort(sort);
~~~

Thứ tự kết quả mong đợi:

~~~text
ord-018, ord-015, ord-012, ord-009, ord-006, ord-003
~~~

## 4. Exact count bằng countDocuments()

### 4.1. Cú pháp

`countDocuments()` đếm số document khớp filter:

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ tenantId: "tenant-A" });
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});
~~~

Trong collection đúng 24 document mẫu, kết quả tương ứng là:

~~~text
24
18
6
~~~

Lệnh đếm không trả document; nó trả một số. Nếu bạn cần số lượng đơn PAID của tenant-A, phải truyền **đúng bộ lọc đó**, không thể dùng tổng toàn collection rồi coi là tổng sau lọc.

### 4.2. Count và truy vấn trang phải cùng filter nghiệp vụ

Ví dụ API cần danh sách đơn đã thanh toán của tenant-A:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const total = db.orders.countDocuments(filter);

const rows = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(2)
  .toArray();

printjson({
  total: total,
  returnedCount: rows.length,
  items: rows
});
~~~

Với dữ liệu mẫu không đổi, `total = 6` và `returnedCount = 2`.

Một lỗi phổ biến:

~~~javascript
// Sai khi trang chỉ hiển thị đơn PAID:
const total = db.orders.countDocuments({
  tenantId: "tenant-A"
});
// total = 18 thay vì 6.
~~~

Nếu ứng dụng đa tenant, count **cũng phải giữ điều kiện tenant và phạm vi quyền**, không chỉ câu lệnh lấy trang. Đây là yêu cầu bảo mật dữ liệu, không đơn thuần vấn đề thống kê.

### 4.3. Filter có nhiều điều kiện

~~~javascript
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: { $in: ["PAID", "SHIPPED"] }
});
~~~

Kết quả: **12** document.

~~~javascript
db.orders.countDocuments({
  tenantId: "tenant-A",
  active: true
});
~~~

Trong 18 đơn của tenant-A, các ID 4, 8, 12 và 16 có `active: false`, nên kết quả là **14**.

Cũng như `find()`, count theo filter có thể dùng các toán tử truy vấn phù hợp. Điều kiện phải được thiết kế dựa trên **đơn vị cần đếm**: đơn hàng, khách hàng, sản phẩm hay một thực thể đã tổng hợp.

### 4.4. Vì sao exact count có thể chậm?

Để cho biết chính xác số document thỏa filter, server cần xác định số lượng trên phạm vi truy vấn. Tùy dữ liệu và index:

- Có thể chỉ cần quét một phạm vi khóa index.
- Có thể cần đọc nhiều document nếu filter không được index hỗ trợ đầy đủ.
- Với filter không chọn lọc hoặc rỗng, phải xét một phần rất lớn collection.
- Kết quả chỉ là một số nhưng chi phí đếm không nhất thiết nhỏ.

Do đó, **ít dữ liệu trả về không có nghĩa ít dữ liệu phải duyệt**.

Exact count vẫn có thể rất nhanh với tập dữ liệu nhỏ hoặc filter có index tốt và độ chọn lọc cao. Không có quy tắc “countDocuments luôn chậm”; cần đo bằng dữ liệu thực tế.

### 4.5. Tránh truyền nhầm skip và limit vào phép đếm

Các tùy chọn `skip`/`limit` của `countDocuments` có thể thay đổi số lượng được đếm:

~~~javascript
db.orders.countDocuments(filter, {
  skip: 2,
  limit: 2
});
~~~

Với 6 document thỏa filter, lệnh này đếm sau skip và limit nên có thể trả `2`, **không phải tổng 6**.

Đối với một API có `totalMatching`, thường chỉ truyền **filter nghiệp vụ** vào count; các tham số trang áp dụng cho câu lệnh lấy `items`.

## 5. Ước lượng bằng estimatedDocumentCount()

### 5.1. Khác biệt căn bản

~~~javascript
db.orders.estimatedDocumentCount();
~~~

`estimatedDocumentCount()` trả số lượng **ước lượng toàn collection**, sử dụng thông tin thống kê/metadata lưu trữ. Nó thường tránh việc phải chạy một phép lọc theo điều kiện giống `countDocuments(filter)`, nên có thể nhẹ hơn khi chỉ cần biết quy mô collection.

Nhưng API này **không nhận filter** để đếm riêng đơn PAID hoặc tenant-A.

So sánh:

~~~javascript
// Exact count theo filter:
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});

// Estimated count toàn bộ collection:
db.orders.estimatedDocumentCount();
~~~

Trên dữ liệu mẫu, lệnh đầu trả **6**. Lệnh thứ hai có thể cho kết quả gần hoặc bằng **24**, nhưng không có nghĩa đó là ước lượng cho 6 document đã lọc.

### 5.2. Khi nào dùng được?

Phù hợp nếu:

- Dashboard chỉ cần biết “khoảng N document” trong collection.
- Biểu đồ theo dõi quy mô lưu trữ.
- Dữ liệu được truy cập ở mức toàn collection, không đòi chính xác từng bản ghi.
- Độ trễ của exact count quan trọng hơn độ chính xác tuyệt đối.

Không phù hợp nếu:

- Tính tổng số đơn PAID của một tenant.
- Cần đối soát tài chính hoặc báo cáo pháp lý.
- Dùng số lượng làm quyết định nghiệp vụ như số lượt giao dịch còn được phép.
- Giao diện cần chính xác tổng số trang theo một filter.

### 5.3. Ước lượng có thể lệch vì sao?

Thống kê lưu trữ có thể không phản ánh hoàn toàn trạng thái document theo cách một phép đếm truy vấn thực hiện, nhất là trong một số tình huống vận hành, phục hồi hoặc cấu hình sharding.

Cần hiểu sự khác nhau giữa:

- **Có 24 document trong bài thực hành và estimate đang trả 24:** chỉ là một quan sát.
- **Mọi estimate luôn chính xác:** đây là kết luận không được bảo đảm.

Nếu sản phẩm hiển thị estimate, nên ghi rõ “ước tính” hoặc lưu metadata về cách đo.

### 5.4. Không suy ra estimate theo filter từ tổng toàn collection

Ví dụ toàn collection ước lượng có 5 triệu document. Không thể sử dụng con số đó để khẳng định tenant-A có 5 triệu, hoặc nhóm PAID có 20% nếu chưa có mô hình phân bố phù hợp.

Ước lượng **theo filter** cần chiến lược riêng như sampling có thống kê rõ, counter duy trì theo từng nhóm hoặc cache count đã tính. Những cách đó mang sai số và chi phí riêng, không phải hành vi tự động của `estimatedDocumentCount()`.

## 6. Aggregation $count

Stage `$count` cho phép đếm sau các stage lọc và biến đổi:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
~~~

Kết quả trên bộ mẫu:

~~~javascript
[{ total: 6 }]
~~~

Nếu không có document đầu vào:

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "not-existing" } },
  { $count: "total" }
]);
~~~

Pipeline thường trả về **mảng rỗng**, không tự sinh một document `{total:0}`.

Có thể chuẩn hóa ở tầng ứng dụng:

~~~javascript
const counted = db.orders.aggregate([
  { $match: { tenantId: "not-existing" } },
  { $count: "total" }
]).toArray();

const total = counted.length > 0 ? counted[0].total : 0;
print(total);
~~~

### 6.1. Đếm sau biến đổi cần biết đang đếm cái gì

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A" } },
  { $group: { _id: "$customerId" } },
  { $count: "totalCustomers" }
]);
~~~

Pipeline này đếm số `customerId` riêng biệt sau `$group`, không phải số đơn hàng gốc. Tương tự, đếm sau `$unwind` có thể là đếm **phần tử mảng**, không còn là số document đơn hàng ban đầu.

`$count` linh hoạt nhưng không phải đường tắt “không tốn chi phí”: tất cả document đi vào stage sau các phép biến đổi upstream vẫn phải được xử lý theo pipeline.

## 7. Phân trang offset: skip và limit

### 7.1. Cách hoạt động

Với page bắt đầu từ 1:

\[
\text{offset}=(\text{page}-1)\times\text{pageSize}
\]

Truy vấn trang 2 với pageSize 2:

~~~javascript
const page = 2;
const size = 2;
const offset = (page - 1) * size;

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(offset)
.limit(size);
~~~

Kết quả dự kiến:

| Page | Offset | IDs |
|---|---:|---|
| 1 | 0 | `ord-018`, `ord-015` |
| 2 | 2 | `ord-012`, `ord-009` |
| 3 | 4 | `ord-006`, `ord-003` |
| 4 | 6 | Không có document |

### 7.2. Sắp xếp ổn định là điều kiện quan trọng

Nếu chỉ sort theo `createdAt` và hai document có cùng giá trị, thứ tự giữa chúng có thể không quyết định. Thêm `_id`, một khóa unique, vào cuối sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Tạo ra thứ tự xác định khi khóa thời gian trùng nhau. Tránh phân trang dựa trên thứ tự “tự nhiên” của document khi API phải hỗ trợ truy cập nhiều trang liên tiếp.

### 7.3. Lấy items và total bằng hai lệnh

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const page = 2;
const size = 2;
const offset = (page - 1) * size;

const items = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .skip(offset)
  .limit(size)
  .toArray();

const total = db.orders.countDocuments(filter);

const result = {
  items: items,
  page: page,
  pageSize: size,
  returnedCount: items.length,
  total: total,
  totalPages: Math.ceil(total / size),
  hasNext: offset + items.length < total
};

printjson(result);
~~~

Khi dữ liệu không đổi, `total = 6`, `totalPages = 3`, `items.length = 2`.

Hai lệnh có thể thực hiện tuần tự hoặc theo cách ứng dụng tổ chức khác, nhưng **không tự chia sẻ một snapshot thời gian**. Một insert/delete giữa chúng có thể làm `items` và `total` tạm thời không nhất quán.

### 7.4. Skip sâu gây chi phí

`skip(100000)` không có nghĩa MongoDB nhảy tức thì đến record thứ 100001. Với nhiều kế hoạch truy vấn, server vẫn phải đi qua các kết quả đứng trước để bỏ qua chúng. Vì vậy trang sâu thường có độ trễ tăng theo offset.

Dù có index giúp sort, một offset lớn vẫn có thể cần duyệt nhiều index entries. Đây là một lý do nên cân nhắc **seek/keyset pagination** cho danh sách lớn có thao tác “Tải thêm”.

## 8. Dùng $facet để lấy page và count trong một lệnh

Aggregation `$facet` cho phép xử lý cùng một tập đầu vào qua nhiều nhánh:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const page = 2;
const size = 2;
const offset = (page - 1) * size;

db.orders.aggregate([
  { $match: filter },
  {
    $facet: {
      metadata: [
        { $count: "total" }
      ],
      data: [
        { $sort: { createdAt: -1, _id: -1 } },
        { $skip: offset },
        { $limit: size },
        {
          $project: {
            _id: 1,
            status: 1,
            amount: 1,
            createdAt: 1
          }
        }
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

Kết quả có dạng:

~~~javascript
[
  {
    data: [
      { _id: "ord-012", /* các trường được chọn */ },
      { _id: "ord-009", /* các trường được chọn */ }
    ],
    total: 6
  }
]
~~~

Ưu điểm:

- Một lệnh aggregation trả cả data và total.
- Dễ giữ logic filter trong một pipeline.
- Giảm số lượt trao đổi client–server so với hai lệnh riêng.
- Hữu ích khi dữ liệu đã đi qua các phép biến đổi trước khi phân trang.

Nhược điểm và giới hạn:

- Nhánh `metadata` vẫn phải **đếm hết** các document khớp; `data.limit(2)` không khiến nhánh count dừng sau 2 document.
- `$facet` có chi phí bộ nhớ và giới hạn về kích thước kết quả.
- Sắp xếp ở bên trong nhánh facet có thể không tận dụng index giống một query `find().sort()` riêng.
- Với filter rất rộng, nhánh count vẫn chi phối độ trễ.

**Quan trọng:** `$facet` không phải “lệnh exact count miễn phí”. Trước khi dùng mặc định, hãy so sánh plan và độ trễ của phương án facet với hai truy vấn độc lập trên dữ liệu đại diện.

### 8.1. Vì sao cần $ifNull?

Với filter không khớp, nhánh `$count` có thể trả mảng rỗng. Biểu thức:

~~~javascript
{
  $ifNull: [
    { $arrayElemAt: ["$metadata.total", 0] },
    0
  ]
}
~~~

giúp chuẩn hóa thành `total: 0`. Không xử lý trường hợp này có thể dẫn đến total thiếu hoặc null trong response.

### 8.2. Đặt $match trước $facet

Với bộ lọc:

~~~javascript
{ tenantId: "tenant-A", status: "PAID" }
~~~

đặt `$match` trước `$facet` giúp hạn chế tập document đưa vào các nhánh và tạo cơ hội dùng index cho phần filter. Không nên mặc định đặt facet đầu pipeline rồi hy vọng mỗi nhánh sẽ tối ưu giống một câu truy vấn riêng.

## 9. Độ chính xác và tính nhất quán là hai vấn đề khác nhau

Một phép đếm có thể trả số chính xác tại một thời điểm, nhưng trong khi người dùng chuyển trang, dữ liệu có thể thay đổi.

Ví dụ:

~~~text
T0: Có 6 đơn PAID
T1: countDocuments(filter) trả total = 6
T2: Một đơn PAID mới được chèn
T3: find(filter).sort(...).limit(2) thấy tập mới gồm 7 đơn
T4: API trả items từ trạng thái mới cùng total = 6
~~~

Ở đây không phải do `countDocuments` “đếm sai”. Vấn đề là **hai lệnh quan sát dữ liệu tại hai thời điểm khác nhau**.

### 9.1. Các loại yêu cầu về sự nhất quán

| Nhu cầu | Mức cam kết thường cần |
|---|---|
| Feed tin tức, danh sách đơn đang thay đổi | Cho phép total hơi cũ hoặc không trả total |
| Trang quản trị với số lượng tham khảo | Exact count tại thời điểm truy vấn, chấp nhận cập nhật theo thời gian |
| Báo cáo đối soát theo kỳ | Tập dữ liệu nhất quán theo quy tắc chốt kỳ hoặc snapshot |
| Nghiệp vụ giao dịch/giới hạn sử dụng | Điều kiện cập nhật nguyên tử, counter/transaction phù hợp; không dựa vào số phân trang |

Cần phân biệt **mức chính xác của thuật toán đếm** với **tính nhất quán theo thời điểm giữa nhiều request**.

### 9.2. Một pipeline có phải luôn là snapshot tuyệt đối?

`$facet` vận hành các nhánh trên tập đầu vào của cùng một lệnh, nhưng không nên tự tuyên bố rằng mọi hoạt động đọc đều được cố định tại một snapshot duy nhất trước các ghi đồng thời nếu chưa xét read concern.

MongoDB có các mức read concern và trong những cấu hình/ngữ cảnh hỗ trợ có thể dùng snapshot reads hoặc transaction để đạt bảo đảm mạnh hơn. Tuy nhiên, điều đó đòi hỏi xem xét topology, phiên bản, chi phí tài nguyên và thời gian giữ snapshot.

**Không nên giữ một transaction mở xuyên suốt nhiều HTTP request phân trang** chỉ để bảo đảm mọi trang người dùng cuộn trong vài phút cùng một snapshot, trừ khi có yêu cầu đặc biệt và thiết kế vận hành phù hợp.

### 9.3. Dữ liệu thêm mới và offset

Giả sử trang 1 trả `ord-018`, `ord-015`. Trước khi người dùng tải trang 2, một đơn hàng mới hơn được chèn vào đầu thứ tự.

Với `skip(2)`, trang 2 trên tập dữ liệu mới có thể chứa lại một document đã xuất hiện ở trang 1 hoặc bỏ qua một document cũ do vị trí bị dịch. Đó là đặc tính của offset pagination khi danh sách biến động.

## 10. Không đếm total: lấy hasNext bằng limit(pageSize + 1)

Với nhiều giao diện, người dùng chỉ cần biết **có dữ liệu tiếp theo** để hiển thị nút “Tải thêm”. Không cần biết totalPages.

Một kỹ thuật phổ biến:

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const size = 2;

const fetched = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(size + 1)
  .toArray();

const items = fetched.slice(0, size);
const hasNext = fetched.length > size;

printjson({
  items: items,
  returnedCount: items.length,
  hasNext: hasNext
});
~~~

Với bộ dữ liệu mẫu, `items` gồm `ord-018` và `ord-015`. Record thứ ba `ord-012` chỉ dùng để biết `hasNext = true`; nó không được trả trong danh sách của trang đầu.

**Lợi ích:** server chỉ cần tìm thêm một document sau pageSize, thay vì phải xác định chính xác toàn bộ count của filter.

**Giới hạn:** Nếu vẫn dùng `skip(offset)` để sang trang sâu, chi phí offset vẫn tăng. Muốn tránh skip sâu, kết hợp với seek pagination.

## 11. Seek/keyset pagination theo khóa sắp xếp

### 11.1. Phân biệt hai nghĩa của cursor

Trong MongoDB, cursor là đối tượng trả kết quả truy vấn theo batch. Trong API web, **cursor token** thường là một giá trị ở tầng ứng dụng mô tả vị trí trang trước. Token đó không tự xuất hiện từ `find()` như một ID phân trang liên request.

Với sort giảm dần:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Có thể dùng cặp `createdAt` và `_id` của document cuối trang trước làm dấu mốc.

### 11.2. Lấy trang đầu

~~~javascript
const filter = {
  tenantId: "tenant-A",
  status: "PAID"
};

const size = 2;

const fetched = db.orders.find(filter)
  .sort({ createdAt: -1, _id: -1 })
  .limit(size + 1)
  .toArray();

const firstPage = fetched.slice(0, size);
const hasNext = fetched.length > size;
const last = firstPage[firstPage.length - 1];

printjson({
  lastId: last._id,
  hasNext: hasNext
});
~~~

Ở dữ liệu mẫu, `last._id = "ord-015"`.

### 11.3. Lấy trang tiếp theo bằng điều kiện range

Với thứ tự giảm dần trên hai khóa, document nằm sau `last` khi:

- `createdAt` nhỏ hơn `last.createdAt`; hoặc
- `createdAt` bằng `last.createdAt` và `_id` nhỏ hơn `last._id`.

~~~javascript
const after = {
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
};

const nextFetched = db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  ...after
})
.sort({ createdAt: -1, _id: -1 })
.limit(size + 1)
.toArray();

const secondPage = nextFetched.slice(0, size);
const nextHasNext = nextFetched.length > size;

printjson({
  ids: secondPage.map(x => x._id),
  hasNext: nextHasNext
});
~~~

Kết quả trang thứ hai: `ord-012` và `ord-009`, còn `ord-006` nên `nextHasNext = true`.

### 11.4. Tại sao phải có khóa _id phụ?

Nếu hai document có cùng `createdAt`, chỉ dùng điều kiện `createdAt < lastCreatedAt` có thể **bỏ mất** những document có cùng timestamp chưa được đọc. Nếu chỉ dùng `createdAt <= lastCreatedAt` thì có thể đọc lặp document cuối trang trước.

Một tie-breaker unique như `_id` giúp tạo thứ tự quyết định và xây điều kiện tiếp tục chính xác hơn.

### 11.5. Token phân trang trong API

Response có thể có dạng:

~~~json
{
  "items": [
    { "_id": "ord-018", "status": "PAID" },
    { "_id": "ord-015", "status": "PAID" }
  ],
  "pageSize": 2,
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
~~~

`nextCursor` do ứng dụng định nghĩa, có thể lưu cặp khóa sort của document cuối, cùng thông tin phiên bản, filter hoặc tenant. Khi thiết kế token:

- Giữ đúng kiểu của `createdAt` và `_id` khi giải mã.
- Gắn token với sort, filter và tenant tương ứng.
- Xác thực token; cân nhắc ký/HMAC nếu không muốn client chỉnh sửa payload.
- Không xem base64 là mã hóa bảo mật.
- Không đưa dữ liệu nhạy cảm vào token đọc được.
- Có quy tắc xử lý token hết hạn hoặc không còn phù hợp.

### 11.6. Seek giải quyết gì?

Seek pagination có lợi khi:

- Tập dữ liệu lớn, người dùng tải nhiều trang liên tục.
- Có index phù hợp thứ tự sort và filter.
- Không cần nhảy thẳng tới một số trang ngẫu nhiên.
- Sản phẩm chấp nhận `hasNext` thay vì exact totalPages.

Seek không tự đảm bảo mọi trang thuộc một snapshot. Nếu document bị cập nhật khóa sort hoặc rời khỏi filter giữa các request, người dùng vẫn có thể thấy thay đổi. Chọn khóa sort ít thay đổi và định nghĩa hành vi khi dữ liệu biến động.

## 12. Đánh đổi độ chính xác, độ trễ và tải hệ thống

Có thể xem thời gian API gồm:

\[
T_{\text{response}} \approx T_{\text{page}}
+ T_{\text{count}}
+ T_{\text{network}}
+ T_{\text{serialization}}
+ T_{\text{application}}
\]

Đây là mô hình đơn giản cho trường hợp chạy tuần tự. Nếu page và count chạy song song, thời gian tổng có thể gần nhánh chậm nhất cộng overhead, nhưng database vẫn phải làm cả hai công việc.

Ví dụ minh họa, **không phải benchmark**:

~~~text
Page query:      15 ms
Exact count:    280 ms
Serialization:   10 ms
Network:         20 ms

Tổng độ trễ nếu tuần tự có thể bị chi phối bởi exact count.
~~~

Thay exact count bằng `estimatedDocumentCount()` chỉ phù hợp nếu nghiệp vụ cần **ước lượng toàn collection**. Không thể vì muốn giảm 280 ms mà đưa một số ước lượng toàn collection vào trường total của filter tenant/status.

Những phương án cần cân nhắc:

1. **Tối ưu filter/index** trước.
2. **Không trả total** khi UX chỉ cần `hasNext`.
3. **Cache count** theo filter với độ cũ được ghi rõ.
4. **Duy trì counter** riêng nếu nghiệp vụ/traffic phù hợp.
5. **Tách endpoint count** để không chặn việc hiển thị trang đầu.
6. **Dùng `$facet`** nếu một pipeline và bộ dữ liệu cho thấy có lợi.
7. **Giảm skip sâu** bằng seek pagination.
8. **Dùng snapshot/transaction** khi yêu cầu nhất quán nghiêm ngặt, đánh giá chi phí kỹ thuật.

Không có phương án luôn thắng trong mọi workload.

## 13. Kiểm tra hiệu năng bằng explain và index

### 13.1. Query plan cho trang dữ liệu

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
~~~

Trong output, quan sát:

| Trường hoặc stage | Ý nghĩa |
|---|---|
| `winningPlan` | Kế hoạch được chọn |
| `IXSCAN` | Có quét index |
| `COLLSCAN` | Quét collection |
| `SORT` | Có bước sắp xếp, có thể tốn tài nguyên |
| `totalKeysExamined` | Số khóa index đã xem |
| `totalDocsExamined` | Số document đã xem |
| `nReturned` | Số document được trả |
| `executionTimeMillis` | Thời gian theo kết quả explain |

Với 24 document, query planner có thể chọn quét collection; điều đó không đủ kết luận index kém trong production.

### 13.2. Query plan cho phép đếm

Dùng aggregation tương đương để xem plan:

~~~javascript
db.orders.explain("executionStats").aggregate([
  {
    $match: {
      tenantId: "tenant-A",
      status: "PAID"
    }
  },
  { $count: "total" }
]);
~~~

Tùy optimizer, plan có thể chứa `COUNT_SCAN`, `IXSCAN` hoặc các stage khác. Không giả định mọi phiên bản MongoDB luôn hiện một stage nhất định.

### 13.3. Index phù hợp với filter và sort

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Hai điều kiện bằng ở đầu index có thể giúp thu hẹp phạm vi, phần sau có thể hỗ trợ sort. Tuy nhiên, exact count vẫn cần xác định số khóa hoặc document thuộc filter; index **không biến mọi phép đếm có điều kiện thành một lần đọc metadata hằng số**.

Nếu filter thực tế còn trường khác, ví dụ `active` hay khoảng thời gian, phải xem độ chọn lọc và các kế hoạch truy vấn tương ứng. Tạo thêm index cũng làm tăng chi phí ghi và dung lượng lưu trữ.

### 13.4. Giới hạn thời gian count

Một số driver/API hỗ trợ đặt thời gian tối đa, ví dụ trong `mongosh`:

~~~javascript
db.orders.countDocuments(
  {
    tenantId: "tenant-A",
    status: "PAID"
  },
  { maxTimeMS: 2000 }
);
~~~

`maxTimeMS` giúp giới hạn thời gian thực thi server theo cơ chế hỗ trợ; **không làm phép đếm nhanh hơn**. Nếu count bị timeout, ứng dụng có thể trả trang mà không có total, hoặc dùng cached count có nhãn nguồn. Không được chuyển timeout thành `total: 0`, vì zero có nghĩa khẳng định không có document.

## 14. Cache exact count có kiểm soát

Một cách giảm độ trễ khi cùng filter được truy vấn thường xuyên là cache kết quả count:

~~~text
cache key:
  tenantId + status + điều kiện tìm kiếm
  + quyền dữ liệu + phiên bản logic filter

cache value:
  total = 12450
  calculatedAt = <timestamp>
  totalKind = "cached"
~~~

Quy trình:

1. Request đến với filter được chuẩn hóa.
2. Kiểm tra cache theo filter và phạm vi quyền.
3. Nếu cache hit và trong thời hạn chấp nhận được, trả số đã lưu kèm thời điểm tính.
4. Nếu miss, tính count chính xác rồi lưu.
5. Thiết kế TTL hoặc invalidation khi dữ liệu thay đổi.

### 14.1. Ưu điểm

- Tránh lặp lại phép đếm tốn kém trong thời gian ngắn.
- Phù hợp dashboard hoặc danh sách nơi người dùng chấp nhận số hơi cũ.
- Có thể tách việc làm mới count khỏi đường trả trang dữ liệu.

### 14.2. Rủi ro

- Count có thể cũ sau insert, delete hoặc update khiến document vào/ra tập filter.
- Cache key thiếu tenant hoặc filter có thể vừa sai số vừa lộ thông tin.
- Quá nhiều filter khác nhau làm tỷ lệ cache hit thấp.
- Invalidation chính xác có thể phức tạp hơn việc tính lại count.
- Nếu chỉ cache số mà không có `calculatedAt`, người dùng khó biết mức độ tin cậy.

Nên biểu diễn:

~~~json
{
  "total": 12450,
  "totalKind": "cached",
  "totalAsOf": "2026-10-25T09:00:00Z"
}
~~~

Đây là mẫu hợp đồng dữ liệu; timestamp thực phải là thời điểm cache được tính, không phải giá trị được gán tùy ý.

## 15. Duy trì counter riêng

Nếu cần đọc số đơn PAID liên tục, có thể lưu một document tổng hợp riêng theo tenant/trạng thái:

~~~javascript
{
  _id: "tenant-A:PAID",
  tenantId: "tenant-A",
  status: "PAID",
  total: NumberLong("6"),
  updatedAt: ISODate("2026-10-25T09:00:00Z")
}
~~~

Document trên chỉ minh họa **cấu trúc counter**. MongoDB không tự tạo nó cho bạn. Logic ứng dụng phải duy trì:

- Insert đơn PAID → tăng counter PAID.
- Delete đơn PAID → giảm counter PAID.
- Chuyển trạng thái từ NEW sang PAID → giảm nhóm NEW nếu đang theo dõi, tăng PAID.
- Chuyển từ PAID sang CANCELLED → giảm PAID, tăng CANCELLED nếu có nhóm đó.

Ưu điểm: đọc một document counter có thể rất nhanh.

Nhược điểm: phải xử lý đồng bộ giữa thay đổi document nguồn và counter. Nếu có transaction nhiều document với topology hỗ trợ hoặc cơ chế eventual consistency/event có idempotency và đối soát, có thể giảm sai lệch theo yêu cầu. Nhưng nếu event bị xử lý lặp hoặc bị bỏ sót, counter có thể không chính xác.

Counter phổ biến bị cập nhật với tần suất cao còn có thể trở thành điểm nóng ghi. Cần đo workload và thiết kế lại nếu cần.

## 16. Ước lượng theo filter: không phải estimatedDocumentCount

Nếu thật sự cần ước lượng số document theo một filter khó đếm, có thể xem xét:

- Lấy mẫu ngẫu nhiên với kích thước đủ lớn và tính sai số thống kê.
- Duy trì histogram/counter cho các nhóm tìm kiếm phổ biến.
- Cache count từng được tính cho chính filter đó.
- Tổng hợp định kỳ theo các chiều dữ liệu quan trọng.

Tuy nhiên, mỗi cách có giả định:

| Phương pháp | Có thể sai vì |
|---|---|
| Sampling | Mẫu không đại diện, kích thước mẫu nhỏ, nhóm hiếm |
| Tổng hợp định kỳ | Dữ liệu phát sinh sau thời điểm tổng hợp |
| Counter theo event | Event lặp/bỏ sót hoặc cập nhật không nhất quán |
| Cached count | Cache quá cũ hoặc khóa không đúng filter |
| Metadata collection | Không thể trực tiếp biểu diễn filter tùy ý |

Không nên dùng một ước lượng không có định nghĩa sai số làm số liệu kiểm toán. Với ứng dụng tài chính, pháp lý hoặc giới hạn giao dịch, cần thiết kế quy trình exact/consistent riêng.

## 17. Thiết kế API phân trang theo nhu cầu

### 17.1. Exact total và page number

~~~json
{
  "items": [
    { "_id": "ord-018", "status": "PAID" },
    { "_id": "ord-015", "status": "PAID" }
  ],
  "page": 1,
  "pageSize": 2,
  "total": 6,
  "totalPages": 3,
  "totalKind": "exact"
}
~~~

Phù hợp với bảng quản trị cần nhảy tới trang cụ thể hoặc báo cáo có tổng chính xác. Tuy nhiên, exact total là giá trị tại thời điểm truy vấn; nó có thể thay đổi khi document mới được thêm.

### 17.2. Tổng đã cache

~~~json
{
  "items": [
    { "_id": "ord-018" },
    { "_id": "ord-015" }
  ],
  "page": 1,
  "pageSize": 2,
  "total": 6,
  "totalKind": "cached",
  "totalAsOf": "2026-10-25T09:00:00Z"
}
~~~

Nếu sản phẩm chấp nhận số cũ, hãy ghi rõ timestamp. Không dùng cached total để ra quyết định tồn kho hoặc tài chính nhạy cảm.

### 17.3. Không cần total

~~~json
{
  "items": [
    { "_id": "ord-018" },
    { "_id": "ord-015" }
  ],
  "pageSize": 2,
  "hasNext": true,
  "nextCursor": "<opaque-token>"
}
~~~

Phù hợp infinite scroll, feed dữ liệu lớn. Người dùng biết còn kết quả để tải tiếp nhưng không phải đợi exact count.

### 17.4. Tính total theo yêu cầu

Có thể trả trang đầu nhanh, đồng thời UI yêu cầu count từ một endpoint riêng khi cần hiển thị tổng. Cách này giảm độ trễ lúc mở trang nhưng không loại bỏ chi phí count; phải xử lý khi filter đổi, người dùng thoát màn hình hoặc kết quả count về sau dữ liệu trang.

## 18. Java Driver: exact count và phân trang

Giả sử bạn đã có `database` kiểu `MongoDatabase`, ví dụ sử dụng MongoDB Java Driver:

~~~java
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Sorts.descending;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.CountOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

MongoCollection<Document> orders = database.getCollection("orders");

Bson filter = and(
    eq("tenantId", "tenant-A"),
    eq("status", "PAID")
);

int page = 1;
int pageSize = 2;
int offset = (page - 1) * pageSize;

long total = orders.countDocuments(filter);

List<Document> items = orders.find(filter)
    .sort(descending("createdAt", "_id"))
    .skip(offset)
    .limit(pageSize)
    .into(new ArrayList<>());

long totalPages = (total + pageSize - 1L) / pageSize;

System.out.println("Items returned: " + items.size());
System.out.println("Total: " + total);
System.out.println("Total pages: " + totalPages);
~~~

Đây là phần logic truy vấn, chưa phải một chương trình Java độc lập có thiết lập `MongoClient`. Ứng dụng thực tế cần giới hạn `pageSize`, kiểm tra `page >= 1` và ngăn tràn số khi tính offset hoặc tổng trang.

### 18.1. Ước lượng toàn collection

~~~java
long approximateSize = orders.estimatedDocumentCount();
~~~

Không gán `approximateSize` vào total của filter tenant/status.

### 18.2. CountOptions để giới hạn thời gian

~~~java
import java.util.concurrent.TimeUnit;
import com.mongodb.client.model.CountOptions;

CountOptions options = new CountOptions()
    .maxTime(2, TimeUnit.SECONDS);

long total = orders.countDocuments(filter, options);
~~~

Lỗi timeout cần được xử lý riêng; không xem như total bằng zero.

### 18.3. Không đếm, chỉ lấy thêm một record

~~~java
List<Document> fetched = orders.find(filter)
    .sort(descending("createdAt", "_id"))
    .limit(pageSize + 1)
    .into(new ArrayList<>());

boolean hasNext = fetched.size() > pageSize;

List<Document> items = fetched.subList(
    0,
    Math.min(pageSize, fetched.size())
);
~~~

Đoạn này minh họa trang đầu. Nếu dùng phân trang liên tục qua nhiều request, cần lưu dấu mốc sort cuối và xây filter seek như mục 11.

### 18.4. Không kéo toàn bộ cursor chỉ để đếm

Với tập kết quả lớn, tránh:

~~~java
// Không nên dùng làm chiến lược đếm tổng:
List<Document> all = orders.find(filter)
    .into(new ArrayList<>());

long total = all.size();
~~~

Cách này tải toàn bộ document phù hợp qua mạng và đưa vào bộ nhớ ứng dụng chỉ để lấy số lượng. Nó tốn thêm I/O, bandwidth và RAM. Dùng `countDocuments(filter)` hoặc một chiến lược count được thiết kế riêng.

## 19. MongoDB Compass: quan sát count và trang dữ liệu

Compass cung cấp giao diện duyệt collection và có thể hiển thị những số liệu đếm/thống kê khác nhau tùy phiên bản. Không mặc định mọi số “Documents” trên UI là exact count sau filter.

Các bước thực hành:

1. Kết nối Compass đến cùng MongoDB Server/cluster với `mongosh`.
2. Mở `pagination_count_lab.orders`.
3. Trong tab **Documents**, nhập filter:

   ~~~json
   {"tenantId":"tenant-A","status":"PAID"}
   ~~~

4. Nếu có phần **Sort**, nhập:

   ~~~json
   {"createdAt":-1,"_id":-1}
   ~~~

5. Quan sát document đầu và đối chiếu `ord-018`, `ord-015`.
6. Trong mongosh, chạy `countDocuments(filter)` để lấy đúng số **6** sau lọc.
7. Chạy `estimatedDocumentCount()` để đối chiếu với ước lượng tổng collection.
8. Nếu Compass có **Aggregations**, thử `$match` + `$count` hoặc `$facet`.
9. Nếu hỗ trợ **Explain Plan**, xem truy vấn trang có sử dụng index hay phải sắp xếp/quét nhiều dữ liệu.
10. Đổi filter thành tenant-B rồi xem cả dữ liệu trang và count thay đổi theo đúng tenant.

Nếu số trên Compass khác mongosh, hãy kiểm tra filter, việc làm mới UI, tính chất estimate/cached của số liệu và thời điểm quan sát.

## 20. Các sai lầm phổ biến

| Triệu chứng | Nguyên nhân hay gặp | Hướng xử lý |
|---|---|---|
| Total luôn bằng pageSize | Dùng `items.length` làm total | Dùng exact count theo filter hoặc ghi rõ không tính total |
| Total = toàn collection dù đang lọc tenant | Dùng `estimatedDocumentCount()` | Không dùng estimate toàn collection cho tổng sau filter |
| Trang có 2 đơn PAID nhưng total = 18 | Count thiếu điều kiện `status` | Dùng cùng filter nghiệp vụ cho page và count |
| Count trả 0 nhưng trang có dữ liệu | Filter khác nhau hoặc dữ liệu thay đổi giữa hai lệnh | Kiểm tra cùng filter và chính sách consistency |
| Aggregation `$count` trả mảng rỗng | Không có document đầu vào | Chuẩn hóa về 0 ở tầng ứng dụng |
| `$facet` vẫn chậm | Nhánh count xử lý cả tập lớn, sort/memory tốn tài nguyên | Đo explain và cân nhắc bỏ exact total |
| Trang số rất lớn mở chậm | `skip` phải bỏ qua nhiều kết quả | Seek/keyset pagination |
| Một document xuất hiện ở hai trang | Offset thay đổi khi dữ liệu được chèn/xóa | Sort có tie-breaker, dùng seek nếu phù hợp |
| totalPages sai | Tổng là cached/estimated nhưng được dùng như exact | Gắn nhãn nguồn và điều chỉnh UX |
| Đổi filter nhưng số total không đổi | Cache key thiếu thông số | Cache theo filter chuẩn hóa và phạm vi quyền |
| Count timeout bị hiển thị thành 0 | Fallback không đúng | Trả trạng thái không tính được, dùng cache hợp lệ hoặc báo lỗi |
| Count tăng sau `$unwind` | Đếm phần tử mảng, không phải document gốc | Xác định đúng đơn vị và stage đếm |
| Tạo nhiều index nhưng count vẫn tốn thời gian | Phạm vi cần đếm quá rộng | Đo keys/docs examined, xem lại yêu cầu exact total |
| Cursor bị hiểu thành snapshot liên request | Token chỉ lưu vị trí phân trang | Xử lý dữ liệu động, chọn khóa sort ổn định |

## 21. Bài thực hành tổng hợp

Các bài dưới đây giả định collection chỉ gồm 24 document mẫu, chưa có dữ liệu ngoài tập hoặc các thay đổi khác.

### Bài 1. Exact count theo điều kiện

~~~javascript
db.orders.countDocuments({});
db.orders.countDocuments({ tenantId: "tenant-A" });
db.orders.countDocuments({
  tenantId: "tenant-A",
  status: "PAID"
});
~~~

**Kết quả:** 24, 18, 6. Giải thích vì sao phép đếm đầu không phải total phù hợp cho màn hình PAID tenant-A.

### Bài 2. Đếm chính xác và ước lượng

~~~javascript
db.orders.countDocuments({});
db.orders.estimatedDocumentCount();
~~~

Hai giá trị có thể giống nhau trong bài thực hành. Giải thích vì sao điều đó không chứng minh estimatedDocumentCount có thể đếm theo filter hoặc luôn chính xác tuyệt đối.

### Bài 3. Phân trang bằng offset

Dùng pageSize 2, filter tenant-A/PAID và sort giảm dần theo `createdAt`, `_id`:

~~~javascript
function getPage(page) {
  return db.orders.find({
    tenantId: "tenant-A",
    status: "PAID"
  })
  .sort({ createdAt: -1, _id: -1 })
  .skip((page - 1) * 2)
  .limit(2)
  .toArray()
  .map(x => x._id);
}

printjson(getPage(1));
printjson(getPage(2));
printjson(getPage(3));
printjson(getPage(4));
~~~

**Kết quả:** trang 1 = 018,015; trang 2 = 012,009; trang 3 = 006,003; trang 4 rỗng.

### Bài 4. Đếm bằng $count

~~~javascript
db.orders.aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $count: "total" }
]);
~~~

Kết quả có `total: 6`. Đổi tenant thành tên không tồn tại, giải thích vì sao result rỗng và cách chuyển thành total = 0.

### Bài 5. Một pipeline $facet

Sử dụng pipeline mục 8 để nhận đồng thời:

- `data`: hai document của trang 2.
- `total`: 6.

Giải thích vì sao facet là một lệnh nhưng nhánh count vẫn phải duyệt hết phạm vi cần đếm.

### Bài 6. HasNext không cần total

~~~javascript
const fetched = db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.toArray();

const items = fetched.slice(0, 2);
const hasNext = fetched.length > 2;
~~~

**Kết quả:** items gồm `ord-018` và `ord-015`; `hasNext = true` do còn phần tử thăm dò.

### Bài 7. Seek pagination

Dùng document `ord-015` làm mốc kết thúc trang 1. Tạo filter:

~~~javascript
const last = db.orders.findOne({ _id: "ord-015" });

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: last.createdAt } },
    {
      createdAt: last.createdAt,
      _id: { $lt: last._id }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(2);
~~~

**Kết quả:** `ord-012`, `ord-009`. Vì sao phải so sánh cả `_id` khi timestamp trùng?

### Bài 8. Hai thời điểm quan sát

Trong database thực hành:

1. Đếm số đơn PAID của tenant-A.
2. Chèn một record PAID mới thuộc tenant-A với `createdAt` mới hơn.
3. Lấy trang đầu và quan sát kết quả.
4. Đếm lại và đối chiếu số trước/sau.

Ví dụ thêm một document:

~~~javascript
db.orders.insertOne({
  _id: "ord-999",
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: new Date(Date.UTC(2026, 10, 1, 9, 0, 0)),
  amount: NumberDecimal("99.50"),
  active: true
});
~~~

Sau bài thực hành, xóa đúng document đã thêm:

~~~javascript
db.orders.deleteOne({ _id: "ord-999" });
~~~

**Câu hỏi:** Tại sao một exact total đo trước khi insert có thể khác total đo sau insert? Có phải thuật toán đếm sai không?

### Bài 9. Explain index

~~~javascript
db.orders.explain("executionStats").aggregate([
  { $match: { tenantId: "tenant-A", status: "PAID" } },
  { $count: "total" }
]);

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.explain("executionStats");
~~~

Ghi nhận index scan/collection scan nếu có, `totalKeysExamined` và `totalDocsExamined`. Với 24 document, không suy ra benchmark của hệ thống lớn.

### Bài 10. Chọn phương án từ yêu cầu

| Yêu cầu sản phẩm | Phương án phù hợp để bắt đầu |
|---|---|
| Bảng quản trị nhỏ có số trang chính xác | `countDocuments(filter)` + page query |
| Dashboard chỉ xem số document cả collection gần đúng | `estimatedDocumentCount()` |
| Báo cáo đếm kết quả sau nhiều stage aggregation | `$count` |
| API cần page và total từ cùng một pipeline | `$facet` sau khi đo chi phí |
| Feed lớn chỉ cần “Tải thêm” | `limit(pageSize + 1)` và seek |
| Filter đắt nhưng màn hình chấp nhận count cũ | Cache count có timestamp và filter key |
| Counter cần đọc rất nhanh nhiều lần | Counter collection duy trì riêng, có cơ chế nhất quán |
| Báo cáo đối soát phải cùng thời điểm dữ liệu | Thiết kế snapshot/read concern/transaction phù hợp |

## 22. Ghi nhớ khi thiết kế ứng dụng

- **Count chính xác theo filter:** dùng `countDocuments(filter)` hoặc aggregation đếm theo đúng tập dữ liệu.
- **Estimate toàn collection:** dùng `estimatedDocumentCount()` khi không cần filter và chấp nhận sai số.
- **Một response có total không tự nhất quán mãi:** dữ liệu thay đổi; phải phân biệt thuật toán exact với thời điểm snapshot.
- **Đừng nhầm số của trang với số của tập:** `items.length` không phải `totalMatching`.
- **$facet không làm count miễn phí:** vẫn phải đếm toàn bộ tập phù hợp, có thể tăng memory hoặc sort cost.
- **Phân trang sâu:** `skip` có chi phí; seek và index sắp xếp ổn định thường hiệu quả hơn.
- **Không cần total thì đừng bắt buộc count:** `pageSize + 1` giúp trả `hasNext`.
- **Giữ bảo mật theo tenant:** page, count, cache và cursor token đều phải gắn cùng phạm vi quyền.
- **Phân loại nguồn con số:** `exact`, `estimated`, `cached` và `not_computed` là các hợp đồng API khác nhau.
- **Đo trước khi tối ưu:** xem explain, keys/docs examined, thời gian server và latency đầu cuối trên workload thực.

Trong MongoDB, **đếm tổng số bản ghi không chỉ là một thao tác truy vấn mà còn là quyết định thiết kế trải nghiệm phân trang**. Khi xác định đúng mức độ chính xác cần thiết, bạn có thể giảm độ trễ đáng kể mà vẫn không đánh tráo ý nghĩa của dữ liệu được hiển thị.
