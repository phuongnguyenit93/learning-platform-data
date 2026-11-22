# Index cho sắp xếp, chiều tăng giảm và bộ lọc kết hợp trong MongoDB

Khi một collection MongoDB có nhiều document, việc truy vấn đúng dữ liệu mới là một nửa yêu cầu. Ứng dụng còn thường cần **trả kết quả theo thứ tự xác định**: đơn hàng mới nhất trước, sản phẩm có giá từ thấp đến cao, hay các giao dịch thuộc một trạng thái được xếp theo thời điểm. Nếu không có index thích hợp, MongoDB có thể phải đọc nhiều document rồi thực hiện một bước **sắp xếp** riêng, khiến truy vấn tốn CPU, bộ nhớ và thời gian hơn khi dữ liệu tăng.

MongoDB sử dụng **index** để hỗ trợ cả **lọc (filter)** lẫn **sắp xếp (sort)**. Trong khai báo index thông thường, giá trị **1** biểu diễn chiều tăng dần và **-1** biểu diễn chiều giảm dần. Với index một trường, MongoDB có thể duyệt theo cả hai hướng. Với **compound index (index ghép nhiều trường)**, thứ tự trường và tương quan chiều tăng/giảm quyết định kiểu sắp xếp nào được hỗ trợ hiệu quả.

Bài học này giải thích cách tạo index phục vụ sort, vì sao index ghép không phải tổ hợp ngẫu nhiên của các trường, cách áp dụng nguyên tắc **Equality – Sort – Range (ESR)**, cách đọc **explain()**, cùng những hạn chế liên quan tới collation, multikey index và dữ liệu không đồng nhất. Các ví dụ thực hành sử dụng mongosh, sau đó chuyển sang MongoDB Java Driver và Spring Data MongoDB.

## 1. Hai việc khác nhau: lọc và sắp xếp

Ví dụ, một màn hình quản lý đơn hàng cần:

> Lấy đơn hàng có trạng thái PAID, thuộc vùng APAC, mới nhất trước; khi nhiều đơn có cùng thời điểm thì dùng _id để phân biệt.

Truy vấn:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
})
~~~

Đây là hai nhóm yêu cầu:

- **Filter:** status bằng PAID **và** region bằng APAC.
- **Sort:** createdAt giảm dần, nếu bằng nhau thì _id giảm dần.

Index tốt có thể giúp MongoDB đi đến những entry phù hợp rồi **đọc chúng theo đúng thứ tự cần trả về**, thay vì gom một tập kết quả lớn để sắp xếp riêng.

~~~text
                     Query
        status = PAID, region = APAC
        sort(createdAt DESC, _id DESC)
                       |
                       v
          MongoDB Query Planner
                  /         \
          Có index phù hợp   Không có index phù hợp
                 |                |
          Duyệt index theo        Lọc và/hoặc đọc
          đúng thứ tự              nhiều document
                 |                |
                 |             SORT riêng
                 |                |
                 +--------+-------+
                          |
                          v
                    Kết quả trả về
~~~

MongoDB có thể chọn nhiều kế hoạch khác nhau tùy dữ liệu, thống kê và index hiện hữu. **Có index không có nghĩa mọi truy vấn chắc chắn sử dụng index đó**; cần kiểm tra kế hoạch thực thi khi tối ưu.

## 2. Dữ liệu mẫu cho toàn bài

Hãy dùng một MongoDB thực hành và kết nối bằng **mongosh**. Chọn database riêng:

~~~javascript
use index_sort_lab
~~~

Các lệnh dưới đây giả định collection **orders** chưa có dữ liệu. Mỗi document có trường _id dạng chuỗi dễ quan sát, status, region, total (Decimal128) và createdAt (BSON Date).

~~~javascript
db.orders.insertMany([
  {
    _id: "O01", status: "PAID", region: "APAC",
    total: NumberDecimal("120.00"),
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "O02", status: "PAID", region: "APAC",
    total: NumberDecimal("85.00"),
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "O03", status: "PAID", region: "EU",
    total: NumberDecimal("200.00"),
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "O04", status: "PENDING", region: "APAC",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "O05", status: "PAID", region: "APAC",
    total: NumberDecimal("230.00"),
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "O06", status: "CANCELLED", region: "US",
    total: NumberDecimal("90.00"),
    createdAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: "O07", status: "PAID", region: "EU",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: "O08", status: "PENDING", region: "APAC",
    total: NumberDecimal("40.00"),
    createdAt: ISODate("2026-10-08T08:00:00Z")
  },
  {
    _id: "O09", status: "PAID", region: "APAC",
    total: NumberDecimal("95.00"),
    createdAt: ISODate("2026-10-09T08:00:00Z")
  },
  {
    _id: "O10", status: "PAID", region: "US",
    total: NumberDecimal("300.00"),
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "O11", status: "PAID", region: "APAC",
    total: NumberDecimal("150.00"),
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "O12", status: "PAID", region: "APAC",
    total: NumberDecimal("70.00"),
    createdAt: ISODate("2026-10-11T08:00:00Z")
  }
])
~~~

Hai document **O11** và **O12** có cùng createdAt, giúp minh họa nhu cầu sắp xếp bằng khóa phụ. Sau khi insert, kiểm tra:

~~~javascript
db.orders.countDocuments({});
db.orders.find(
  {},
  { _id: 1, status: 1, region: 1, total: 1, createdAt: 1 }
).sort({ _id: 1 });
~~~

Kết quả count dự kiến là **12**. Nếu chạy lại insertMany với cùng _id, bạn có thể gặp lỗi trùng khóa; nên tạo dữ liệu mẫu một lần hoặc dùng collection thử nghiệm mới.

| _id | status | region | total | Ngày UTC |
|---|---|---|---:|---|
| O01 | PAID | APAC | 120.00 | 01/10 |
| O02 | PAID | APAC | 85.00 | 02/10 |
| O03 | PAID | EU | 200.00 | 03/10 |
| O04 | PENDING | APAC | 150.00 | 04/10 |
| O05 | PAID | APAC | 230.00 | 05/10 |
| O06 | CANCELLED | US | 90.00 | 06/10 |
| O07 | PAID | EU | 150.00 | 07/10 |
| O08 | PENDING | APAC | 40.00 | 08/10 |
| O09 | PAID | APAC | 95.00 | 09/10 |
| O10 | PAID | US | 300.00 | 10/10 |
| O11 | PAID | APAC | 150.00 | 11/10 |
| O12 | PAID | APAC | 70.00 | 11/10 |

Các ví dụ kết quả trong bài dựa trên bộ dữ liệu này và **không giả định thứ tự mặc định của find()**. Khi cần xác nhận thứ tự, luôn dùng sort() tường minh.

## 3. Hiểu ký hiệu chiều 1 và -1

Trong một **index key specification**:

~~~javascript
{ createdAt: 1 }   // Tăng dần
{ createdAt: -1 }  // Giảm dần
~~~

Cũng trong **sort specification**:

~~~javascript
db.orders.find().sort({ createdAt: 1 });
db.orders.find().sort({ createdAt: -1 });
~~~

Tuy cùng dùng số 1/-1, hai ngữ cảnh khác nhau:

- **createIndex()** định nghĩa cách khóa được tổ chức trong index.
- **sort()** định nghĩa thứ tự kết quả mà truy vấn yêu cầu.

Ví dụ tạo một index:

~~~javascript
db.orders.createIndex({ createdAt: 1 });
~~~

MongoDB có thể dùng index **createdAt tăng dần** để hỗ trợ cả:

~~~javascript
db.orders.find().sort({ createdAt: 1 });
db.orders.find().sort({ createdAt: -1 });
~~~

Lý do: đối với **index một trường**, MongoDB có thể duyệt index theo hướng tiến hoặc ngược. Vì vậy, **không phải cứ có hai loại sort tăng/giảm trên một field thì phải tạo cả hai index {field:1} và {field:-1}**.

### 3.1. $natural không tương đương sort theo index nghiệp vụ

~~~javascript
db.orders.find().sort({ $natural: 1 });
~~~

**$natural** liên quan đến thứ tự tự nhiên trong lưu trữ, không phải “theo thời điểm tạo” hay “theo _id”. Không nên dùng $natural để thay cho sort({createdAt: 1}) khi muốn thứ tự nghiệp vụ ổn định.

### 3.2. Khi hai document có cùng khóa sort

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({ createdAt: -1 });
~~~

Hai document O11 và O12 có cùng createdAt. Nếu chỉ sort theo createdAt, bạn **không có hợp đồng về thứ tự tương đối** của hai document này.

Thêm khóa phụ duy nhất:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Kết quả từ mới đến cũ là **O12, O11, O09, O05, O02, O01**. Khóa _id làm cho thứ tự giữa các document trùng createdAt trở nên rõ ràng.

**Sort ổn định** rất quan trọng khi kết hợp với limit(), phân trang theo khóa hoặc checkpoint trong batch job; nó giúp tránh kết quả chồng lặp hoặc thay đổi vị trí khi nhiều record có cùng thời điểm.

## 4. Một index một trường có thể phục vụ hai chiều sort

Giả sử thường xem tất cả đơn hàng theo createdAt:

~~~javascript
db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_createdAt_desc" }
);
~~~

Truy vấn:

~~~javascript
// Mới nhất trước
db.orders.find().sort({ createdAt: -1 });

// Cũ nhất trước
db.orders.find().sort({ createdAt: 1 });
~~~

Một index trên createdAt có thể được duyệt theo chiều thuận hoặc ngược để hỗ trợ cả hai. MongoDB vẫn phải cân nhắc chi phí đọc và có thể chọn một kế hoạch khác trên dữ liệu nhỏ. Nếu kết quả cần thứ tự xác định khi trùng ngày, thêm _id vào sort, rồi thiết kế compound index tương ứng khi workload đòi hỏi.

### 4.1. Index không thay đổi các quy tắc của sort()

Tạo index không làm truy vấn này tự sắp xếp:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

Nếu cần mới nhất trước, **vẫn phải chỉ định sort()**. Index chỉ là cấu trúc hỗ trợ để MongoDB có thể thực thi yêu cầu đó hiệu quả hơn.

### 4.2. Khi nào cần compound index ngay từ đầu?

Nếu giao diện luôn yêu cầu:

~~~javascript
.sort({ createdAt: -1, _id: -1 })
~~~

thì index chỉ có createdAt có thể không cung cấp toàn bộ thứ tự trên hai khóa. Một lựa chọn phù hợp hơn:

~~~javascript
db.orders.createIndex(
  { createdAt: -1, _id: -1 },
  { name: "idx_createdAt_id_desc" }
);
~~~

Index này sắp xếp createdAt giảm dần và, trong nhóm cùng createdAt, sắp xếp _id giảm dần. Tuy nhiên, trước khi thêm index mới, cần xem các filter thường được dùng cùng sort vì một index ghép với trường equality đứng trước có thể phục vụ truy vấn nghiệp vụ tốt hơn.

## 5. Compound index: thứ tự trường là thành phần của thiết kế

Một **compound index** lưu khóa của nhiều field theo thứ tự chỉ định:

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1
});
~~~

Index không chỉ đơn thuần “chứa ba field”. Có thể hình dung khóa được sắp theo:

~~~text
status ASC
    |
    +-- region ASC (trong mỗi status)
           |
           +-- createdAt DESC (trong mỗi status + region)
~~~

Tương tự một danh bạ xếp theo **tỉnh**, rồi **quận**, sau đó **tên người**, nếu bỏ qua tỉnh và quận thì các tên không còn được sắp xếp toàn cục theo một thứ tự duy nhất.

### 5.1. Index prefix là gì?

Với index:

~~~javascript
{ status: 1, region: 1, createdAt: -1 }
~~~

Các **prefix** là:

~~~javascript
{ status: 1 }
{ status: 1, region: 1 }
{ status: 1, region: 1, createdAt: -1 }
~~~

Index thường có thể hỗ trợ các truy vấn/sort dựa trên prefix. Ngược lại, **{region:1}** hoặc **{createdAt:-1}** không phải là prefix của index đó. Khả năng tận dụng một trường nằm phía sau phụ thuộc thêm vào điều kiện của các trường trước nó, không chỉ việc trường đó tồn tại trong index.

### 5.2. Vì sao không thể đảo vị trí field tùy ý?

So sánh:

~~~javascript
// Index A
{ status: 1, createdAt: -1 }

// Index B
{ createdAt: -1, status: 1 }
~~~

Nếu filter có **status = "PAID"** và sort theo **createdAt giảm dần**, index A giúp MongoDB khoanh vùng một nhóm status rồi đọc theo createdAt. Index B lại sắp toàn bộ theo createdAt, rồi mới theo status trong những nhóm cùng createdAt; có thể phải đi qua nhiều record không phải PAID.

Với truy vấn chỉ yêu cầu mới nhất trên **tất cả** status, index B có thể hữu ích hơn vì createdAt đứng đầu. Đây là lý do một index tốt phải được chọn theo **mẫu truy vấn (query pattern)**, không chỉ theo tên field.

## 6. Chiều tăng/giảm trong compound index

Khác với index một trường, compound index phải xét **hướng tương đối của các field sort**.

Ví dụ:

~~~javascript
db.orders.createIndex(
  { total: 1, createdAt: -1 },
  { name: "idx_total_asc_created_desc" }
);
~~~

Index này có thể hỗ trợ toàn bộ thứ tự:

~~~javascript
// Cùng chiều với index key pattern
db.orders.find().sort({
  total: 1,
  createdAt: -1
});

// Duyệt ngược toàn bộ index key pattern
db.orders.find().sort({
  total: -1,
  createdAt: 1
});
~~~

Hai sort trên là **hai hướng đảo ngược hoàn toàn của nhau**.

Ngược lại, nếu không có equality constraint làm mất ý nghĩa một số khóa, hai sort sau **không có cùng kiểu hướng** với index trên:

~~~javascript
db.orders.find().sort({
  total: 1,
  createdAt: 1
});

db.orders.find().sort({
  total: -1,
  createdAt: -1
});
~~~

Index {total:1, createdAt:-1} không trực tiếp tạo ra thứ tự cần thiết cho hai trường hợp vừa nêu bằng một lượt quét tuần tự toàn bộ index. MongoDB có thể cần bước SORT hoặc chọn một index khác.

### 6.1. Bảng chiều của compound index

Giả sử index có khóa **{a:1, b:-1}**, cả a và b thực sự tham gia sort, không có điều kiện equality cố định a:

| Sort yêu cầu | Có khớp hướng của index để đọc trực tiếp? | Giải thích |
|---|---|---|
| {a:1, b:-1} | Có | Cùng hướng |
| {a:-1, b:1} | Có | Đảo ngược toàn bộ |
| {a:1, b:1} | Không theo quy tắc hướng trực tiếp | Hướng b khác |
| {a:-1, b:-1} | Không theo quy tắc hướng trực tiếp | Hướng b khác |
| {a:1} | Có thể | Là prefix |
| {b:-1} | Không thể suy ra chỉ từ index | b không phải prefix; cần xét điều kiện trên a |

Đây là một quy tắc thiết kế index cho sort. **Query planner vẫn lựa chọn kế hoạch theo chi phí**: ngay cả khi index có khả năng cung cấp thứ tự, việc thực thi cụ thể còn phụ thuộc filter, projection, limit và các index khác.

### 6.2. Ví dụ nhiều khóa sort

Giả sử màn hình yêu cầu sắp theo **status tăng dần**, **createdAt giảm dần** rồi **_id giảm dần**:

~~~javascript
db.orders.find().sort({
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Một index phù hợp về hướng:

~~~javascript
db.orders.createIndex({
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Index này cũng có thể được duyệt ngược để phục vụ sort **{status:-1, createdAt:1, _id:1}**. Nhưng nếu người dùng chỉ đảo chiều createdAt và giữ nguyên hai chiều khác, đó không còn là hướng đảo ngược toàn bộ; phải xem lại khả năng của index.

### 6.3. Equality constraint thay đổi yêu cầu sort thực tế

Với index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

Truy vấn:

~~~javascript
db.orders.find({
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

MongoDB có thể dùng index để tìm **nhóm status = PAID**, trong đó createdAt đã được xếp giảm dần. Vì status được cố định bằng equality, nó không cần xuất hiện trong sort.

Nếu không có filter status:

~~~javascript
db.orders.find().sort({
  createdAt: -1
});
~~~

thì index {status:1,createdAt:-1} **không cung cấp một thứ tự createdAt giảm dần toàn cục**, bởi createdAt được xếp thành những nhóm theo status.

Đây là khái niệm **non-prefix subset sort**: MongoDB có thể tận dụng thứ tự của những trường phía sau trong index nếu các khóa đứng trước được ràng buộc bằng điều kiện equality thích hợp.

## 7. Bộ lọc equality kết hợp sort: index sát với nhu cầu

Quay lại nhu cầu màn hình đơn hàng:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Một index hữu ích:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_status_region_created_id" }
);
~~~

Tại sao chọn thứ tự như vậy?

1. **status** và **region** là các điều kiện bằng, giúp xác định nhóm document cần đọc.
2. **createdAt** và **_id** nằm sau các khóa equality, theo đúng hướng sort.
3. Khi status/region cố định, các entry index của nhóm đó được tổ chức theo createdAt giảm dần và _id giảm dần.

Với dữ liệu mẫu, kết quả theo thứ tự là:

~~~text
O12 (11/10, _id O12)
O11 (11/10, _id O11)
O09 (09/10)
O05 (05/10)
O02 (02/10)
O01 (01/10)
~~~

### 7.1. Nếu chỉ lọc một trong hai trường equality?

Index:

~~~javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

Truy vấn chỉ lọc status:

~~~javascript
db.orders.find({
  status: "PAID"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Trong nhóm status PAID, MongoDB vẫn phải đi qua nhiều **region** khác nhau. Vì region nằm trước createdAt và không được cố định bằng equality, index đó không bảo đảm tạo ra một thứ tự createdAt toàn cục cho tất cả region.

Nếu đây là một query pattern thường xuyên, index:

~~~javascript
{ status: 1, createdAt: -1, _id: -1 }
~~~

có thể thích hợp hơn.

**Thiết kế theo workload:** Một index duy nhất không nhất thiết phục vụ tối ưu mọi biến thể bộ lọc. Cần nhìn vào những truy vấn thường chạy nhất, không chỉ truy vấn phức tạp nhất.

### 7.2. Thứ tự các trường equality có thể khác nhau

Khi một truy vấn **luôn ràng buộc cả status và region bằng equality**, cả:

~~~javascript
{ status: 1, region: 1, createdAt: -1 }
{ region: 1, status: 1, createdAt: -1 }
~~~

đều có thể hỗ trợ lọc theo cặp equality rồi sort theo createdAt. Tuy nhiên, thứ tự equality vẫn ảnh hưởng tới **prefix** và khả năng tái sử dụng index cho những truy vấn chỉ lọc một trong hai field. Vì thế cần xem workload tổng thể trước khi chọn.

## 8. Nguyên tắc ESR: Equality – Sort – Range

Một hướng dẫn thiết kế compound index phổ biến của MongoDB là **ESR**:

~~~text
E = Equality: các field dùng điều kiện bằng
S = Sort:     các field dùng sắp xếp
R = Range:    các field dùng khoảng $gt/$gte/$lt/$lte, v.v.
~~~

Ý tưởng điển hình:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1
});
~~~

Một index theo hướng **Equality → Sort → Range**:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    total: 1
  },
  { name: "idx_esr_status_region_date_total" }
);
~~~

Khi status và region được cố định, index có thể cung cấp thứ tự createdAt giảm dần. Trường total đặt sau createdAt được dùng cho điều kiện khoảng, nhưng vì các khóa createdAt ở trước không bị giới hạn tương ứng, MongoDB có thể phải quét nhiều entry hơn rồi loại những document có total dưới 100.

Với dữ liệu mẫu, kết quả mong muốn là **O11, O05, O01** theo createdAt giảm dần.

### 8.1. Vì sao range thường được đặt sau sort?

Đặt range trước sort có thể khiến các entry được nhóm theo trường range, không còn giữ thứ tự toàn cục của trường sort. Ví dụ:

~~~javascript
// Equality -> Range -> Sort
{
  status: 1,
  region: 1,
  total: 1,
  createdAt: -1
}
~~~

Với filter **total >= 100** rồi sort theo **createdAt giảm dần**, index trên xếp theo total trước. Các đơn có total 120, 150, 230 nằm ở những vị trí theo total; createdAt được xếp bên trong các nhóm giá trị total, không phải theo một thứ tự createdAt toàn cục. Query planner có thể cần bước sort riêng.

Ngược lại, index **{status:1,region:1,createdAt:-1,total:1}** ưu tiên giữ thứ tự trả về, chấp nhận việc phải kiểm tra thêm điều kiện total.

### 8.2. ESR là hướng dẫn, không phải định luật bất biến

Nếu điều kiện range **rất chọn lọc** (chỉ còn rất ít document), một index theo thứ tự **Equality – Range – Sort (ERS)** có thể đọc ít dữ liệu hơn dù cần sort nhỏ ở cuối. Thứ tự ESR không phải mặc định nhanh nhất trong mọi workload.

Ví dụ nếu total >= 1.000.000 chỉ khớp vài đơn trong hàng triệu record, lọc theo total sớm có thể rẻ hơn duyệt rất nhiều record theo createdAt để giữ sort rồi kiểm tra total.

Quyết định cần dựa vào:

- Mức **chọn lọc** của equality và range.
- Số document dự kiến trả về.
- Có **limit** hay không.
- Chi phí sort, có thể sort trong bộ nhớ hay dùng tài nguyên khác.
- Dữ liệu và index đã có.
- Kết quả từ **explain("executionStats")** với workload đại diện.

### 8.3. Không nhầm range với tất cả biểu thức điều kiện

Những toán tử như **$gt, $gte, $lt, $lte** là range điển hình. Điều kiện **$ne**, **$nin** có tính chọn lọc và cách dùng index riêng, thường không hoạt động như một equality point thông thường. **$in** cũng cần xét ngữ cảnh, số phần tử và sort; không nên tự coi mọi $in đều tương đương một equality duy nhất.

ESR hữu ích khi bạn có thể mô tả rõ query pattern trước khi tạo index, chứ không thay thế việc phân tích một truy vấn thực tế.

## 9. Range và sort trên cùng một trường

Một trường hợp dễ tối ưu hơn là **lọc theo khoảng và sort chính trên cùng một field**. Ví dụ sản phẩm/đơn hàng có tổng tiền từ 100 đến dưới 250 và cần sắp theo tổng tiền tăng dần:

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1
});
~~~

Index phù hợp:

~~~javascript
db.orders.createIndex(
  { status: 1, total: 1 },
  { name: "idx_paid_total" }
);
~~~

Khi status được cố định là PAID, MongoDB có thể quét **khoảng total** trong index theo thứ tự tăng dần. Trong dữ liệu mẫu, các document thỏa filter được sắp theo giá trị total như sau:

~~~text
O01   120.00
O07   150.00
O11   150.00
O03   200.00
O05   230.00
~~~

Thứ tự giữa **O07** và **O11** chưa được bảo đảm khi chỉ sort theo total, vì chúng cùng giá trị 150.00. Nếu cần thứ tự duy nhất:

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1,
  _id: 1
});
~~~

Khi query này được sử dụng thường xuyên, index:

~~~javascript
{ status: 1, total: 1, _id: 1 }
~~~

có thể hỗ trợ cả thứ tự total và khóa phụ _id. Không nên cho rằng index chỉ có {status:1,total:1} bảo đảm thứ tự thứ hai theo _id: muốn một tie-breaker ổn định ở cấp truy vấn, phải khai báo sort và lựa chọn index theo cả hai khóa.

### 9.1. Sort ngược cũng có thể dùng index

Với index **{status:1,total:1}**, nếu status được cố định bằng equality, MongoDB có thể đi ngược nhóm index để phục vụ:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ total: -1 });
~~~

Khi một index gồm nhiều field thực sự tham gia sort, hãy xét **hướng đảo ngược toàn bộ của key pattern**. Khi các field đứng trước được cố định bằng equality, yêu cầu sort chỉ còn phụ thuộc những field phía sau.

### 9.2. Range ở trước sort khác có thể phá thứ tự

Index:

~~~javascript
{ status: 1, total: 1, createdAt: -1 }
~~~

có thể hỗ trợ filter status và khoảng total, đồng thời trả total tăng dần. Nhưng nếu muốn **sort chỉ theo createdAt giảm dần** trên toàn bộ các total nằm trong range, index không sắp createdAt toàn cục: nó sắp createdAt bên trong từng giá trị total. Vì thế cần cân nhắc index khác hoặc bước SORT.

Quy tắc thực hành: khi có nhiều field, hãy tự hỏi **“Tại thời điểm đọc các entry trong index, các khóa đứng trước trường sort đã được cố định thành một giá trị chưa?”**

## 10. Xem kế hoạch thực thi với explain()

Không thể đánh giá index chỉ bằng việc câu truy vấn chạy đúng. Mục tiêu tối ưu là giảm lượng dữ liệu phải duyệt và tránh sort tốn kém khi lợi ích đủ lớn.

MongoDB cung cấp **explain()** để kiểm tra kế hoạch truy vấn:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

Bạn sẽ thấy thông tin về **queryPlanner** và **executionStats**. Cấu trúc hiển thị có thể khác nhau tùy phiên bản MongoDB và query execution engine; một số phiên bản đưa stage vào winningPlan trực tiếp, một số có cấu trúc lồng nhau như queryPlan.

### 10.1. Những phần quan trọng cần tìm

| Trường hoặc stage thường thấy | Ý nghĩa |
|---|---|
| winningPlan | Kế hoạch thực thi được chọn |
| IXSCAN | Quét theo index |
| COLLSCAN | Quét collection |
| SORT | Bước sắp xếp riêng trong kế hoạch |
| FETCH | Lấy document đầy đủ khi index chưa cung cấp đủ dữ liệu |
| PROJECTION_* | Lấy hoặc định hình các trường cần trả |
| indexName | Tên index đang được sử dụng ở stage thích hợp |
| totalKeysExamined | Số entry index được xem xét |
| totalDocsExamined | Số document được đọc/kiểm tra |
| nReturned | Số document được trả về |
| executionTimeMillis | Thời gian thực thi được thống kê theo quy tắc của explain |

Chỉ số cần đọc **trong bối cảnh**: IXSCAN không mặc định tốt nếu phải quét phần lớn index. COLLSCAN không mặc định xấu trên collection có vài document. Một SORT riêng có thể chấp nhận được với vài chục record sau khi filter range rất chọn lọc.

### 10.2. Quan sát index đúng với query pattern

Tạo index đã thiết kế:

~~~javascript
db.orders.createIndex(
  {
    status: 1,
    region: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "idx_status_region_created_id" }
);
~~~

Sau đó:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

Nếu optimizer chọn index thích hợp để cung cấp thứ tự, bạn thường thấy index scan liên quan và **không cần một bước SORT blocking riêng cho kết quả**. Tuy nhiên, vì collection mẫu chỉ có 12 document, MongoDB hoàn toàn có thể chọn COLLSCAN + SORT do chi phí tổng thể thấp hơn; đừng diễn giải việc đó như lỗi tạo index.

Trong thí nghiệm, có thể dùng **hint()** để yêu cầu một index cụ thể nhằm quan sát hành vi:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).hint(
  "idx_status_region_created_id"
).explain("executionStats");
~~~

**hint() là công cụ thăm dò và có những trường hợp sử dụng chuyên biệt**, không phải cách tối ưu mặc định cho mọi truy vấn production. Hint ép sử dụng một index dù query planner có thể muốn một kế hoạch tốt hơn.

### 10.3. totalKeysExamined không bằng nReturned là bình thường

Nếu index chứa status, region, createdAt rồi total nhưng query còn filter total >= 100, server có thể đi qua nhiều entry của nhóm PAID/APAC, kiểm tra giá trị total, rồi chỉ trả một phần. Khi đó:

~~~text
totalKeysExamined  > nReturned
~~~

không nhất thiết là lỗi. Câu hỏi cần đặt là: số entry phải xem có hợp lý với độ chọn lọc, kích thước dữ liệu và mục tiêu độ trễ hay không?

### 10.4. So sánh trước và sau index trên tập dữ liệu đại diện

Một quy trình quan sát hữu ích:

1. Ghi lại filter, projection, sort và limit đúng như ứng dụng thực tế.
2. Chạy explain("executionStats") trước khi thay đổi index.
3. Tạo index dự kiến cho query pattern.
4. Xem lại winningPlan, keys/docs examined, nReturned và SORT.
5. Đo thời gian thực tế trong điều kiện tải và dữ liệu đại diện.
6. Kiểm tra chi phí insert/update và dung lượng index tăng thêm.

**Không chạy benchmark theo cách làm ảnh hưởng hệ thống thật**. Tập dữ liệu mười hai document chỉ phục vụ hiểu cơ chế, không đại diện cho hiệu năng của collection hàng triệu document.

## 11. Sort + limit: index hữu ích cho trang kết quả đầu tiên

Một giao diện thường chỉ cần **20 đơn hàng mới nhất**:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Nếu index hỗ trợ filter và sort, MongoDB có thể đọc những entry phù hợp theo thứ tự rồi dừng khi đủ 20 document, thay vì nhất thiết phải sắp xếp toàn bộ tập phù hợp.

Đây là lý do index phục vụ sort thường đặc biệt giá trị với truy vấn **top N** hoặc màn hình phân trang.

### 11.1. Limit không thay thế sort

~~~javascript
db.orders.find({ status: "PAID" }).limit(20);
~~~

Câu này yêu cầu tối đa 20 document nhưng không bảo đảm đó là **20 đơn mới nhất**. Muốn mới nhất phải có **sort({createdAt:-1,...})**.

### 11.2. Offset pagination có thể tốn chi phí

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).skip(10000).limit(20);
~~~

Ngay cả khi có index hỗ trợ thứ tự, việc bỏ qua một offset lớn có thể khiến MongoDB cần đi qua nhiều entry trước trang mong muốn. Nếu dữ liệu đang được thêm/xóa, vị trí offset cũng có thể dịch chuyển, gây trùng lặp hoặc bỏ sót giữa các trang.

Khi số trang lớn, cân nhắc **keyset pagination** với khóa sắp xếp ổn định:

~~~javascript
// Giả sử phần tử cuối trang trước:
const lastCreatedAt = ISODate("2026-10-09T08:00:00Z");
const lastId = "O09";

db.orders.find({
  status: "PAID",
  region: "APAC",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Điều kiện dùng **$lt** vì đang đọc từ mới đến cũ. Với dữ liệu mẫu và mốc O09, trang tiếp theo là **O05, O02, O01**. Hãy bảo đảm _id và createdAt có kiểu nhất quán, khóa sort không đổi tùy tiện và index được thiết kế phù hợp với mẫu truy vấn.

**Keyset pagination cũng không tự tạo snapshot bất biến** khi dữ liệu thay đổi đồng thời; nó chủ yếu giúp biểu diễn vị trí trang bằng khóa thay vì offset.

## 12. Projection và covered query

Một index không chỉ hỗ trợ filter/sort, mà đôi khi còn chứa **toàn bộ field ứng dụng cần trả**, giúp MongoDB giảm số document cần fetch. Đây thường được gọi là **covered query** khi truy vấn được xử lý dựa trên index theo điều kiện thích hợp.

Ví dụ index:

~~~javascript
{
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
}
~~~

Truy vấn chỉ yêu cầu những trường có trong index:

~~~javascript
db.orders.find(
  {
    status: "PAID",
    region: "APAC"
  },
  {
    _id: 1,
    status: 1,
    region: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
});
~~~

Về mặt field cần thiết, index đã chứa filter, sort và projection. MongoDB **có thể** đáp ứng truy vấn này mà không phải đọc document gốc, tùy cấu hình index và điều kiện thực tế. Để biết có covered hay không, xem **totalDocsExamined**, stage FETCH và winningPlan.

Nếu thêm field **total** vào projection nhưng index không chứa total:

~~~javascript
{
  _id: 1,
  status: 1,
  region: 1,
  createdAt: 1,
  total: 1
}
~~~

thì MongoDB có thể cần lấy document gốc để đọc total. Không nên bổ sung mọi field của document vào index chỉ nhằm tạo covered query nếu chi phí index quá lớn.

### 12.1. Lưu ý về _id trong projection

Theo mặc định, kết quả truy vấn MongoDB thường có **_id**. Nếu index không chứa _id và bạn muốn một covered query không cần _id, projection nên loại _id tường minh:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { status: 1, region: 1, _id: 0 }
);
~~~

Việc _id có nằm trong index hay không phụ thuộc index được tạo. Một index ghép có **_id:1** hoặc **_id:-1** thì có thể cung cấp khóa đó; một index chỉ trên status/region không tự trở thành index có _id như một field thường cần cho mọi kiểu projection.

### 12.2. Covered query không phải mục tiêu duy nhất

Một index rộng có thể giúp đọc nhưng lại:

- Chiếm thêm dung lượng RAM và đĩa.
- Làm thao tác ghi phải cập nhật nhiều index key hơn.
- Tăng chi phí build/rebuild, vận hành và bảo trì.
- Không giải quyết được tất cả filter/sort khác.

Chọn index để cân bằng **chi phí đọc** với **chi phí ghi và lưu trữ**, không phải tạo index cho mọi tổ hợp field.

## 13. Các yếu tố làm index không hỗ trợ sort như kỳ vọng

Một index nhìn có vẻ khớp tên field vẫn có thể không phục vụ được toàn bộ sort. Trước khi đánh giá kế hoạch, cần kiểm tra thêm kiểu dữ liệu, collation, multikey và các điều kiện khác.

### 13.1. Collation khi so sánh và sắp xếp chuỗi

Sort chuỗi chịu ảnh hưởng của **collation**. Collation có thể quy định ngôn ngữ, cách phân biệt chữ hoa/thường và dấu. Nếu index được tạo với collation khác truy vấn, nó có thể không được sử dụng để hỗ trợ các phép so sánh/sắp xếp chuỗi theo yêu cầu.

Ví dụ collection khách hàng có country và fullName:

~~~javascript
db.customers.createIndex(
  { country: 1, fullName: 1 },
  {
    name: "idx_country_name_vi",
    collation: {
      locale: "vi",
      strength: 2
    }
  }
);
~~~

Truy vấn với collation tương ứng:

~~~javascript
db.customers.find({
  country: "VN"
}).collation({
  locale: "vi",
  strength: 2
}).sort({
  fullName: 1
});
~~~

Index có thể hữu ích vì country được ràng buộc bằng equality và fullName đứng sau. Nhưng nếu truy vấn dùng **simple collation** hoặc một collation khác để sắp xếp tên, kết quả thứ tự theo quy tắc khác và MongoDB có thể không dùng index trên để đáp ứng sort.

Với các trường mã kỹ thuật như sku hoặc code, nên xác định rõ cần so sánh nhị phân hay theo ngôn ngữ; đừng dùng một kiểu collation cho mọi dữ liệu chỉ vì phù hợp với tên người.

### 13.2. Multikey index khi field là array

MongoDB tạo **multikey index** khi index một field dạng array theo những điều kiện được hỗ trợ. Index này thường chứa khóa liên quan đến từng phần tử array, nên hữu ích cho truy vấn giá trị phần tử.

Ví dụ:

~~~javascript
db.products.createIndex({
  tags: 1,
  createdAt: -1
});
~~~

Index trên không nên được hiểu đơn giản rằng mọi truy vấn sort trên array tags hoặc createdAt đều không cần SORT. Khi sắp xếp trường mảng, MongoDB có các quy tắc về giá trị dùng cho thứ tự và các điều kiện index bounds/multikey path; một số tổ hợp filter và sort vẫn cần bước sắp xếp riêng.

Nếu một màn hình thường sort theo **createdAt** và lọc theo một tag, hãy xem **explain()** trên dữ liệu thật thay vì suy từ sự hiện diện của hai field trong index.

### 13.3. Dữ liệu có nhiều kiểu BSON

Giả sử trường total được ghi lúc là Decimal128, lúc là String:

~~~javascript
{ total: NumberDecimal("100.00") }
{ total: "100.00" }
~~~

Index vẫn sắp xếp theo quy tắc so sánh BSON và kiểu dữ liệu, không tự hiểu chuỗi "100.00" như Decimal128. Query filter số có thể không khớp chuỗi, và sort của dữ liệu không đồng nhất có thể khác thứ tự số học mong đợi.

Giải pháp là **quy định kiểu BSON tại thời điểm ghi**, dùng schema validation khi phù hợp và migration dữ liệu cũ. Index không thể tự sửa kiểu dữ liệu sai.

### 13.4. Một index không tự thay thế mọi index khác

Nếu có index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

nó có thể phục vụ tốt filter status + sort theo createdAt. Nhưng query chỉ lọc hoặc sort theo **region**, hay query chỉ sort theo createdAt trên mọi status, có thể cần index hoặc kế hoạch khác.

Index intersection (kết hợp nhiều index trong một số kế hoạch) cũng **không đồng nghĩa** với việc mọi tổ hợp filter + sort đều được đáp ứng hiệu quả như một compound index. Nếu sort là đường đi quan trọng của màn hình, hãy thiết kế index dựa trên toàn bộ query pattern.

### 13.5. Partial index: hữu ích khi chỉ phục vụ một tập con

Nếu phần lớn truy vấn chỉ đọc đơn hàng PAID, có thể cân nhắc **partial index**:

~~~javascript
db.orders.createIndex(
  {
    region: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_paid_region_date",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

Index chỉ chứa các document đáp ứng điều kiện partial đã khai báo. Truy vấn cần có bộ lọc tương thích, bảo đảm kết quả yêu cầu nằm trong tập mà index bao phủ, để MongoDB có thể sử dụng nó:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Nếu truy vấn **không giới hạn status = PAID**, partial index này không bao phủ đầy đủ kết quả, nên không thể tự dùng nó để lấy toàn bộ đơn hàng. Đây là tối ưu chuyên biệt, không phải thay thế tổng quát cho index bình thường.

### 13.6. Index có chi phí với thao tác ghi

Mỗi lần insert, update những field được index, hoặc delete, MongoDB có thể phải duy trì các index tương ứng. Việc tạo quá nhiều compound index có thể:

- Tăng dung lượng lưu trữ và bộ nhớ đệm.
- Tăng chi phí ghi và cập nhật.
- Kéo dài thời gian tạo index hoặc bảo trì index.
- Làm hệ thống có nhiều kế hoạch index cần cân nhắc hơn.

Vì vậy, **không tạo mọi hoán vị tăng/giảm của các field**. Trước tiên tận dụng khả năng duyệt ngược, prefix và equality-prefix; sau đó mới thêm index khác cho query pattern thực sự cần.

## 14. Index cho nhiều hướng sort trong một sản phẩm

Giả sử giao diện có hai tùy chọn:

1. **Mới nhất:** sắp theo createdAt giảm dần, _id giảm dần.
2. **Cũ nhất:** sắp theo createdAt tăng dần, _id tăng dần.

Với filter status + region bằng nhau:

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
});
~~~

Một index có thể hỗ trợ cả hai sort nếu các field equality được cố định:

~~~javascript
// Mới nhất
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});

// Cũ nhất
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: 1,
  _id: 1
});
~~~

Nhưng nếu tùy chọn giao diện là:

~~~javascript
// createdAt giảm, _id tăng
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: 1
});
~~~

thì phần hướng sort không còn là cùng chiều hay đảo ngược toàn bộ của đoạn **{createdAt:-1, _id:-1}**. Nếu truy vấn này rất quan trọng, có thể cần một index key pattern khác hoặc chấp nhận SORT.

### 14.1. Phân biệt chiều của equality key và sort key

Khi status và region đã được cố định bởi điều kiện bằng, chiều 1 hay -1 của các trường này **không tác động đến thứ tự bên trong một nhóm có cùng giá trị**. Vì vậy, khi xem xét reverse scan cho sort createdAt/_id, điều quan trọng là chiều tương đối của **những khóa thực sự tham gia sắp xếp**.

Tuy nhiên, hướng của các khóa equality vẫn ảnh hưởng đến những query pattern khác dùng chúng trong sort hoặc chỉ lọc một phần prefix. Không nên tùy tiện thay đổi hướng trong index mà chưa khảo sát các truy vấn khác.

### 14.2. Không nhất thiết thêm index chỉ vì người dùng đảo “mới nhất/cũ nhất”

Trường hợp sort hai khóa cùng đảo chiều:

~~~javascript
{ createdAt: -1, _id: -1 }
{ createdAt: 1, _id: 1 }
~~~

có thể dùng một index phù hợp duyệt theo hai hướng. Đây là lý do hiểu **reverse index traversal** giúp giảm index trùng lặp.

## 15. MongoDB Java Sync Driver: tạo index và sort

Trong ứng dụng Java sử dụng MongoDB Sync Driver, package **com.mongodb.client.model.Indexes** giúp tạo index, còn **Sorts** giúp xây dựng sort. Các ví dụ giả định project có dependency **mongodb-driver-sync** tương thích và biến môi trường **MONGODB_URI** đã cấu hình.

### 15.1. Tạo compound index bằng Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Indexes;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

public class CreateOrdersIndex {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("index_sort_lab")
                    .getCollection("orders");

            Bson indexKeys = Indexes.compoundIndex(
                    Indexes.ascending("status", "region"),
                    Indexes.descending("createdAt", "_id")
            );

            String name = orders.createIndex(
                    indexKeys,
                    new IndexOptions().name("idx_status_region_created_id")
            );

            System.out.println("Index: " + name);
        }
    }
}
~~~

Trong đoạn code:

- **Indexes.ascending("status","region")** tạo hai khóa tăng dần.
- **Indexes.descending("createdAt","_id")** tạo hai khóa giảm dần.
- **Indexes.compoundIndex(...)** ghép các khóa theo thứ tự.
- **IndexOptions().name(...)** đặt tên để dễ nhận diện trong danh sách index và explain.

Việc tạo index là thao tác DDL/quản trị có chi phí. Trong ứng dụng thực tế, nên quản lý index bằng một quy trình khởi tạo/migration có kiểm soát, không để mỗi request tự tạo lại index.

### 15.2. Truy vấn có filter + sort + limit

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ReadRecentPaidOrders {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.and(
                Filters.eq("status", "PAID"),
                Filters.eq("region", "APAC")
        );

        Bson sort = Sorts.orderBy(
                Sorts.descending("createdAt"),
                Sorts.descending("_id")
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("index_sort_lab")
                    .getCollection("orders");

            try (MongoCursor<Document> cursor = orders.find(filter)
                    .projection(Projections.include(
                            "status", "region", "createdAt"))
                    .sort(sort)
                    .limit(20)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document order = cursor.next();
                    System.out.println(order.toJson());
                }
            }
        }
    }
}
~~~

Truy vấn Java tương đương filter/sort đã dùng trong mongosh. Trong ví dụ này, **MongoCursor** được đóng bằng try-with-resources, còn MongoClient được đóng khi chương trình dòng lệnh kết thúc. Ứng dụng web chạy lâu dài nên tái sử dụng MongoClient qua cấu hình quản lý bean/client, đồng thời đóng cursor sau mỗi lượt đọc.

### 15.3. Dùng Sorts.ascending và Sorts.descending đúng mục đích

~~~java
// Một trường, tăng dần
Sorts.ascending("total");

// Một trường, giảm dần
Sorts.descending("createdAt");

// Nhiều trường, hướng hỗn hợp
Sorts.orderBy(
        Sorts.ascending("total"),
        Sorts.descending("createdAt")
);
~~~

Những biểu thức này chỉ tạo **sort specification**. MongoDB dùng index nào để thực thi phụ thuộc các index có trong collection và bộ lọc đi kèm; tên API Sorts không tự tạo index.

## 16. Spring Data MongoDB: Query, Sort và compound index

Với Spring Data MongoDB, bạn có thể kết hợp **Criteria**, **Query** và **Sort**:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderSearchService {
    private final MongoTemplate mongoTemplate;

    public OrderSearchService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> findRecentPaidApacOrders() {
        Query query = Query.query(
                Criteria.where("status").is("PAID")
                        .and("region").is("APAC")
        );

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
        ));
        query.limit(20);

        return mongoTemplate.find(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

Ví dụ giả định MongoTemplate trỏ tới database **index_sort_lab**. Với dữ liệu mẫu, kết quả theo thứ tự là **O12, O11, O09, O05, O02, O01**.

### 16.1. Khai báo compound index trên entity

Nếu sử dụng Spring Data MongoDB để mapping document sang entity, có thể dùng annotation khai báo compound index theo cấu hình dự án:

~~~java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
@CompoundIndex(
        name = "idx_status_region_created_id",
        def = "{'status': 1, 'region': 1, 'createdAt': -1, '_id': -1}"
)
public class OrderDocument {
    @Id
    private String id;
    private String status;
    private String region;
    private Instant createdAt;

    // Constructors, getters và setters tùy phong cách dự án.
}
~~~

Annotation trên mô tả index mong muốn. **Việc index có được tạo tự động khi khởi động hay không phụ thuộc cấu hình Spring Data MongoDB**, phiên bản và quy trình triển khai. Trong hệ thống production, nên chủ động quản lý việc thay đổi index để tránh build index ngoài ý muốn lúc ứng dụng bắt đầu phục vụ request.

Ngoài ra, trường Java Instant cần được mapping phù hợp sang BSON Date và field _id cần có kiểu khớp với dữ liệu thực tế. Dự án có entity dùng kiểu ObjectId hoặc id riêng có thể cần cấu hình khác.

### 16.2. Index tốt phải khớp truy vấn thực tế của repository

Nếu phương thức repository thường tìm:

~~~text
status = PAID
region = APAC
sort by createdAt DESC, _id DESC
~~~

thì index trên status/region/createdAt/_id phù hợp về nguyên tắc. Nhưng nếu cùng ứng dụng còn có trang “mọi đơn hàng mới nhất” không lọc status/region, trang đó có thể cần index riêng bắt đầu bằng createdAt. Không nên chỉ dựa vào một annotation duy nhất để kết luận mọi repository query đều đã tối ưu.

## 17. Một quy trình thiết kế index cho filter + sort

Thay vì tạo index theo cảm giác, hãy biến yêu cầu nghiệp vụ thành một thiết kế có thể đo được.

### Bước 1. Ghi lại query pattern đầy đủ

Ví dụ:

~~~javascript
db.orders.find(
  {
    status: "PAID",
    region: "APAC",
    total: {
      $gte: NumberDecimal("100.00")
    }
  },
  {
    _id: 1,
    total: 1,
    createdAt: 1
  }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Đừng chỉ ghi “truy vấn orders theo status”. Cần biết cả **projection**, **sort**, **limit** và loại điều kiện của từng field.

### Bước 2. Phân nhóm các field

| Field | Vai trò |
|---|---|
| status | Equality |
| region | Equality |
| total | Range |
| createdAt | Sort giảm dần |
| _id | Sort giảm dần, khóa phụ |

Theo nguyên tắc ESR, một index dự kiến:

~~~javascript
{
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1,
  total: 1
}
~~~

Index này ưu tiên việc đọc kết quả theo đúng thứ tự. Tuy nhiên, total được đặt sau các trường sort nên mức độ thu hẹp bằng điều kiện total có thể không bằng một index đặt total sớm hơn.

### Bước 3. Cân nhắc range trước sort nếu rất chọn lọc

Một phương án khác:

~~~javascript
{
  status: 1,
  region: 1,
  total: 1,
  createdAt: -1,
  _id: -1
}
~~~

Phương án này ưu tiên range trên total, nhưng thường không cung cấp sẵn thứ tự createdAt toàn cục trong khoảng total. Nó có thể cần sort bổ sung.

Nếu ngưỡng total rất hiếm khi khớp, chi phí sort một tập nhỏ có thể hợp lý. Nếu màn hình luôn lấy 20 đơn mới nhất trong một tập nhiều record, giữ thứ tự bằng index có thể đem lại lợi ích lớn hơn. **Không chọn chỉ bằng suy đoán**.

### Bước 4. Đo bằng explain và workload đại diện

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

So sánh số entry index, document đã đọc, số document trả về và có cần SORT hay không. Ngoài latency, đo thêm tác động đến insert/update và kích thước index.

### Bước 5. Kiểm tra những query pattern lân cận

Một số trường hợp thường cùng tồn tại trong sản phẩm:

| Query pattern | Index có thể cân nhắc |
|---|---|
| Mọi đơn mới nhất | {createdAt:-1, _id:-1} |
| Chỉ đơn PAID mới nhất | {status:1, createdAt:-1, _id:-1} |
| PAID của APAC mới nhất | {status:1, region:1, createdAt:-1, _id:-1} |
| PAID theo khoảng total, sort total tăng | {status:1, total:1, _id:1} |
| Chỉ xem một khách hàng theo thời điểm | {customerId:1, createdAt:-1, _id:-1} nếu schema có customerId |

Đây là **những ứng viên** chứ không phải chỉ dẫn tạo tất cả index trong bảng. Một số index dài có thể phục vụ nhu cầu của index ngắn thông qua prefix; nếu một index ngắn hoàn toàn dư thừa theo workload và cách truy vấn, có thể cân nhắc loại bỏ nó. Mặt khác, một index ngắn hơn đôi khi vẫn có lợi vì kích thước nhỏ và hiệu quả đọc/ghi khác. Quyết định cần dựa trên phân tích kế hoạch và vận hành thực tế.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách hiểu đúng |
|---|---|---|
| Index {createdAt:1} chỉ dùng được sort tăng | Tạo thêm index ngược chiều không cần thiết | Index một trường có thể quét thuận/ngược |
| Index compound có mọi trường là đủ | Sort vẫn cần bước SORT | Cần đúng thứ tự khóa và hướng sort tương đối |
| {a:1,b:-1} hỗ trợ mọi tổ hợp tăng/giảm | Lựa chọn index sai | Hỗ trợ trực tiếp pattern cùng chiều hoặc đảo ngược toàn bộ |
| Có index {status:1,createdAt:-1} thì sort createdAt toàn collection luôn hiệu quả | createdAt bị chia theo nhóm status | Cần equality status hoặc index thích hợp cho sort toàn cục |
| Chỉ cần thêm sort() là MongoDB sẽ dùng index | Truy vấn chậm khi dữ liệu lớn | Tạo index phù hợp và kiểm tra explain |
| Có index thì find() không cần sort() | Thứ tự kết quả không được bảo đảm | Vẫn khai báo sort theo yêu cầu |
| status là Equality nên đặt sau Range cũng như nhau | Tăng số entry cần duyệt hoặc mất thứ tự có ích | Xem ESR và phân bố dữ liệu |
| ESR luôn nhanh nhất | Bỏ lỡ phương án ERS khi range rất chọn lọc | So sánh kế hoạch và chi phí thực tế |
| Range trên total rồi sort theo date luôn được index xử lý cả hai | Thứ tự date bị chia theo total | Cân nhắc ưu tiên sort hoặc lọc range |
| Chỉ sort theo createdAt là ổn định khi trùng thời điểm | Phân trang có thể trùng/bỏ sót | Thêm khóa phụ duy nhất, như _id |
| skip(100000) có chi phí ngang skip(10) | Trang sâu chậm | Cân nhắc keyset pagination |
| Index trên String có thể tự sort số lưu dạng String | Kết quả không theo thứ tự số học mong đợi | Đồng nhất BSON type, sửa dữ liệu sai |
| Query collation nào cũng tận dụng index String | Index không phục vụ đúng thứ tự so sánh | Đồng bộ collation của query và index khi cần |
| Multikey index luôn đáp ứng sort cho field mảng | Có thể vẫn cần sort riêng | Kiểm tra quy tắc và explain |
| Có IXSCAN là tối ưu | Vẫn có thể quét rất nhiều entry | Xem keys/docs examined, nReturned và chi phí tổng |
| Hint index luôn tốt hơn planner | Ép một kế hoạch không phù hợp | Dùng hint có chủ đích, không làm mặc định |
| Tạo thêm index không có tác dụng phụ | Tăng chi phí ghi và dung lượng | Chọn index theo query pattern quan trọng |

## 19. Bài tập thực hành

Các bài tập dùng dữ liệu **orders** ở phần 2. Hãy xác định tập kết quả về mặt logic trước, sau đó tạo những index cần thiết và quan sát bằng explain() trên môi trường thực hành.

### Bài 1. Index một trường và hai chiều sort

Tạo một index:

~~~javascript
db.orders.createIndex({ total: 1 });
~~~

Thực hiện:

~~~javascript
db.orders.find().sort({ total: 1 });
db.orders.find().sort({ total: -1 });
~~~

**Câu hỏi:** Có bắt buộc tạo thêm index {total:-1} chỉ vì query thứ hai sort giảm dần không?

**Định hướng:** Không. MongoDB có thể duyệt một index một trường theo hai chiều. Khi nhiều document có cùng total, muốn thứ tự xác định thì thêm khóa phụ vào sort và đánh giá index ghép phù hợp.

### Bài 2. Chiều hỗn hợp của compound index

Cho index:

~~~javascript
{ total: 1, createdAt: -1 }
~~~

Hãy xác định sort nào phù hợp về hướng khi cả hai field tham gia sort:

~~~javascript
// A
{ total: 1, createdAt: -1 }

// B
{ total: -1, createdAt: 1 }

// C
{ total: 1, createdAt: 1 }

// D
{ total: -1, createdAt: -1 }
~~~

**Đáp án:** A cùng hướng, B là đảo ngược toàn bộ. C và D không cùng hướng với index để hỗ trợ toàn bộ thứ tự bằng một lượt quét trực tiếp, trừ những tình huống đặc biệt làm giảm yêu cầu sort thực tế.

### Bài 3. Bộ lọc hai equality, sort mới nhất

Viết query tìm đơn **PAID** tại **APAC**, sắp theo createdAt và _id giảm dần. Tạo index theo cấu trúc Equality → Sort.

**Đáp án tham khảo:**

~~~javascript
db.orders.createIndex({
  status: 1,
  region: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
});
~~~

Kết quả: **O12, O11, O09, O05, O02, O01**.

**Câu hỏi mở:** Nếu bỏ điều kiện region, index trên còn bảo đảm sort createdAt giảm dần toàn bộ các region trong nhóm PAID không? Vì sao?

**Định hướng:** Không theo cấu trúc index đã chọn, vì region là khóa đứng trước createdAt và chưa bị cố định bằng equality.

### Bài 4. Range và sort cùng trường

Tìm các đơn PAID có total từ 100 đến dưới 250, sắp theo total tăng dần.

~~~javascript
db.orders.find({
  status: "PAID",
  total: {
    $gte: NumberDecimal("100.00"),
    $lt: NumberDecimal("250.00")
  }
}).sort({
  total: 1
});
~~~

Index ứng viên:

~~~javascript
{ status: 1, total: 1 }
~~~

Các document thỏa filter: **O01, O03, O05, O07, O11**. Xếp theo total: O01, O07/O11 (cùng 150), O03, O05. Để tránh mơ hồ tại total = 150, thêm _id vào sort và xem xét index {status:1,total:1,_id:1}.

### Bài 5. Phân biệt ESR và ERS

Truy vấn:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC",
  total: { $gte: NumberDecimal("100.00") }
}).sort({
  createdAt: -1
});
~~~

So sánh hai index:

~~~javascript
// A: Equality -> Sort -> Range
{ status: 1, region: 1, createdAt: -1, total: 1 }

// B: Equality -> Range -> Sort
{ status: 1, region: 1, total: 1, createdAt: -1 }
~~~

Hãy giải thích index nào thuận tiện hơn để trả kết quả theo createdAt và index nào có thể phù hợp hơn nếu ngưỡng total cực kỳ chọn lọc. Đề xuất cách dùng explain() để quan sát chi phí thật.

**Định hướng:** A ưu tiên thứ tự createdAt, B ưu tiên lọc theo total. Không có một câu trả lời tối ưu cố định cho mọi phân bố dữ liệu.

### Bài 6. Covered query

Cho index:

~~~javascript
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

Query chỉ trả:

~~~javascript
{
  _id: 1,
  status: 1,
  region: 1,
  createdAt: 1
}
~~~

Hãy chỉ ra vì sao các field cần thiết đều nằm trong index. Sau đó thêm **total** vào projection và giải thích vì sao MongoDB có thể phải FETCH document gốc.

### Bài 7. Phân trang theo khóa

Màn hình hiển thị PAID/APAC theo createdAt DESC, _id DESC. Trang trước kết thúc ở O09. Hãy viết điều kiện lấy các document **cũ hơn O09** theo cùng thứ tự, tối đa 5 document.

**Đáp án tham khảo:**

~~~javascript
const lastCreatedAt = ISODate("2026-10-09T08:00:00Z");
const lastId = "O09";

db.orders.find({
  status: "PAID",
  region: "APAC",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(5);
~~~

Theo dữ liệu ban đầu, kết quả là **O05, O02, O01**.

### Bài 8. Đọc explain() thay vì đoán

Thực hiện:

~~~javascript
db.orders.find({
  status: "PAID",
  region: "APAC"
}).sort({
  createdAt: -1,
  _id: -1
}).explain("executionStats");
~~~

Hãy tìm **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned** và xem có stage SORT riêng không. So sánh sau khi có compound index phù hợp. Giải thích vì sao collection mẫu quá nhỏ để suy ra tốc độ trên production.

### Bài 9. Lựa chọn index theo nhiều màn hình

Giả sử ứng dụng có ba màn hình:

1. Mọi đơn hàng mới nhất, không lọc.
2. Đơn hàng PAID mới nhất, không lọc region.
3. Đơn hàng PAID tại APAC mới nhất.

Hãy đề xuất index ứng viên cho từng màn hình và xác định index nào có khả năng hỗ trợ prefix của truy vấn khác. Không được chỉ đưa ra một tập index; cần giải thích ảnh hưởng của thứ tự khóa và chi phí tạo nhiều index.

**Định hướng:** Có thể cân nhắc lần lượt:

~~~javascript
{ createdAt: -1, _id: -1 }
{ status: 1, createdAt: -1, _id: -1 }
{ status: 1, region: 1, createdAt: -1, _id: -1 }
~~~

Đây là các **ứng viên theo mẫu truy vấn**, không phải yêu cầu tạo cả ba trong mọi deployment. Hãy cân nhắc tần suất của mỗi màn hình, dữ liệu và hiệu quả thực tế bằng explain().

## 20. Tóm lược các nguyên tắc quan trọng

1. **Index một trường có thể được duyệt theo hai chiều.** Không tạo index tăng và giảm trùng lặp chỉ vì cần sort theo hai hướng của cùng một field.
2. **Compound index phụ thuộc thứ tự field và hướng tương đối.** Hỗ trợ sort theo key pattern hoặc đảo ngược toàn bộ; khi chỉ dùng các field phía sau, cần xét equality trên prefix đứng trước.
3. **Filter và sort phải được thiết kế cùng nhau.** Đặt equality trước các trường sort thường giúp MongoDB khoanh vùng dữ liệu rồi đọc theo đúng thứ tự.
4. **ESR là nguyên tắc hữu ích, không phải quy tắc tuyệt đối.** Nếu range cực kỳ chọn lọc, ERS kèm bước sort có thể hiệu quả hơn trong workload cụ thể.
5. **Luôn khai báo sort tường minh**, và thêm khóa phụ duy nhất khi thứ tự phải xác định giữa các record có cùng giá trị.
6. **Explain() là công cụ kiểm chứng kế hoạch.** Hãy quan sát IXSCAN, SORT, FETCH, số keys/docs examined và dữ liệu thực tế, thay vì chỉ đếm index đã tạo.
7. **Index có chi phí ghi và lưu trữ.** Chọn theo những query pattern quan trọng và hạn chế các index dư thừa.

Index tốt không chỉ là index có đúng tên các field được truy vấn. Nó phải phản ánh **cách ứng dụng lọc, thứ tự muốn trả về, chiều tăng giảm và kích thước tập kết quả**. Khi nắm vững việc duyệt ngược index, equality prefix, compound sort và nguyên tắc ESR, bạn có thể thiết kế truy vấn MongoDB chính xác hơn và có cơ sở rõ ràng để tối ưu hiệu năng khi dữ liệu tăng trưởng.
