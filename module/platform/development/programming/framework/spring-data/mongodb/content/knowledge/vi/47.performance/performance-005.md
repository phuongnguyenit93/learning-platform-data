# Tối ưu index theo filter, sort, collation và phân trang

## 1. Bối cảnh: index phải phục vụ truy vấn thực tế

Trong module **SPRING_DATA_MONGODB**, chúng ta sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua MongoTemplate hoặc repository. Bên cạnh truy vấn, aggregation, transaction, reactive access và kiểm thử, một kỹ năng cần thiết là **chẩn đoán hiệu năng dữ liệu dựa trên kế hoạch thực thi**, đặc biệt khi màn hình danh sách phải lọc, sắp xếp và phân trang cùng lúc.

Giả sử ứng dụng bán hàng có nhiều khách hàng doanh nghiệp (tenant). Một màn hình quản lý đơn hàng yêu cầu:

- Chỉ lấy đơn thuộc tenant đang đăng nhập.
- Lọc theo trạng thái như PAID hoặc PENDING.
- Hiển thị đơn mới nhất trước.
- Sắp xếp ổn định khi hai đơn có cùng thời điểm tạo.
- Phân trang nhiều lần, kể cả khi dữ liệu có hàng triệu đơn.
- Ở một màn hình khác, sắp xếp tên khách hàng theo quy tắc tiếng Việt, có thể không phân biệt hoa/thường.

Nếu chỉ tạo index riêng cho từng trường, ứng dụng vẫn có thể đọc quá nhiều khóa, phải sắp xếp trong bộ nhớ hoặc càng chuyển tới trang sâu càng chậm. Một **compound index** hợp lý cần phản ánh cách các điều kiện **filter**, **sort**, **collation** và **pagination** phối hợp với nhau.

Sau bài này, bạn có thể:

1. Xác định query shape và chọn thứ tự khóa cho compound index theo Equality–Sort–Range (ESR), đồng thời nhận biết khi nên cân nhắc Equality–Range–Sort (ERS).
2. Giải thích vì sao chiều sort, khóa tiền tố và phép lọc range ảnh hưởng việc tận dụng index.
3. Tạo index và truy vấn có collation tương thích cho chuỗi tiếng Việt.
4. Phân biệt offset pagination với keyset/cursor pagination, thiết kế thứ tự ổn định bằng khóa duy nhất.
5. Viết ví dụ MongoTemplate/Repository phù hợp và kiểm chứng bằng explain("executionStats").
6. Đánh giá đánh đổi giữa tốc độ đọc, dung lượng index và chi phí ghi.

## 2. Mô hình dữ liệu và query shape

Collection **orders** lưu document như sau:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  tenantId: "tenant-A",
  status: "PAID",
  createdAt: ISODate("2026-11-18T08:30:00Z"),
  customerName: "Nguyễn An",
  totalAmount: NumberDecimal("125000.00")
}
~~~

Các giả định của bài thực hành:

- **tenantId**, **status** là chuỗi; **createdAt** là BSON Date; **_id** là ObjectId.
- **createdAt** và **_id** đều tồn tại, khác null; **createdAt** không bị tự ý sửa sau khi tạo. ID là duy nhất.
- Query chính dùng bộ lọc tenantId = tenant-A và status = PAID; sắp xếp **createdAt giảm dần rồi _id giảm dần**.
- Việc phân quyền theo tenant được thực hiện ở tầng ứng dụng và luôn đi vào truy vấn.
- Ví dụ dùng MongoDB và Spring Data MongoDB tương thích với các API minh họa; hệ thống thật cần đối chiếu phiên bản thư viện đang triển khai.

Truy vấn thường xuyên chạy:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

**Query shape** không chỉ là danh sách trường: nó bao gồm các toán tử lọc (bằng, lớn hơn, trong tập, regex...), trường và chiều sort, collation, giới hạn số bản ghi, projection và đôi khi cả điều kiện phân trang. Hai truy vấn cùng dùng tenantId, createdAt nhưng khác sort hoặc collation có thể cần chiến lược index khác nhau.

| Yêu cầu | Mẫu truy vấn | Hệ quả đối với index |
| --- | --- | --- |
| Lọc tenant và status | tenantId = ..., status = ... | Các trường equality thường đi đầu. |
| Lấy mới nhất | sort(createdAt DESC, _id DESC) | Hai khóa sort cần đúng thứ tự và tương thích chiều. |
| Lọc khoảng tiền | totalAmount >= ... | Là range; vị trí so với sort cần cân nhắc độ chọn lọc. |
| Tên khách theo tiếng Việt | sort(customerName ASC) + collation vi | Index và query phải dùng collation tương thích. |
| Trang sâu | skip(offset) + limit | Vẫn tốn công bỏ qua các kết quả trước đó. |
| Trang tiếp theo bằng cursor | createdAt/_id nhỏ hơn vị trí cuối | Cần sort ổn định và index cùng khóa sắp xếp. |

## 3. Chọn compound index cho filter và sort

### 3.1. Equality – Sort – Range (ESR)

Với query chính, lựa chọn khởi đầu tự nhiên là:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_status_created_id" }
);
~~~

Các khóa có vai trò:

1. **tenantId: 1**: thu hẹp vào một tenant bằng phép so sánh equality.
2. **status: 1**: tiếp tục thu hẹp bằng equality.
3. **createdAt: -1**: lấy dữ liệu theo thứ tự thời gian giảm dần.
4. **_id: -1**: làm khóa phụ duy nhất để thứ tự luôn xác định ngay cả khi nhiều đơn có cùng createdAt.

Một index có thể giúp cả bước lọc và bước sắp xếp nếu truy vấn sử dụng các khóa theo cách tương thích. MongoDB có thể đi qua các entry của index theo thứ tự cần thiết, thay vì gom toàn bộ kết quả rồi thực hiện một phép sort chặn (blocking sort).

~~~mermaid
flowchart LR
  A[tenantId = tenant-A] --> B[status = PAID]
  B --> C[createdAt DESC]
  C --> D[_id DESC]
  D --> E[Giới hạn 20 kết quả]
~~~

**ESR là quy tắc thiết kế khởi đầu, không phải bảo đảm mọi truy vấn đều tối ưu**. Planner còn dựa trên thống kê, dữ liệu thực tế, tính chọn lọc, số trường cần trả về, điều kiện range và những index khác.

### 3.2. Khái niệm index prefix

Index có các khóa theo thứ tự:

~~~text
tenantId → status → createdAt → _id
~~~

Các prefix liên tiếp từ đầu index là:

~~~text
{ tenantId }
{ tenantId, status }
{ tenantId, status, createdAt }
{ tenantId, status, createdAt, _id }
~~~

Một query chỉ lọc status mà không có tenantId không tận dụng hiệu quả tiền tố đầu của index này như query có cả tenantId. MongoDB đôi khi vẫn chọn quét index theo cách khác; điều quan trọng là **không mặc định một index nhiều trường thay thế hiệu quả index dành cho mọi tập con tùy ý**.

Nếu cần dùng index để sort theo một phần khóa **không nằm đầu**, các trường prefix đứng trước phần sort thường phải có điều kiện equality. Ví dụ:

~~~javascript
// Hợp với index vì cả tenantId và status đã cố định.
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);

// Không cố định status: thường không thể dùng cùng index
// để lấy thứ tự createdAt tổng thể cho cả hai trạng thái.
db.orders.find({ tenantId: "tenant-A" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
~~~

Truy vấn thứ hai có thể cần index riêng:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_tenant_created_id" }
);
~~~

Không nên tạo cả hai index một cách máy móc. Hãy kiểm tra truy vấn thực sự phổ biến, độ trễ, tần suất ghi và dung lượng trước khi quyết định.

### 3.3. Chiều sort trên compound index

Trong MongoDB, một compound index có thể hỗ trợ chiều sort trùng với thứ tự khóa, hoặc đảo ngược đồng thời toàn bộ chiều của các khóa sort tương ứng.

Ví dụ index:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Khi tenantId và status là equality, các kiểu sort sau tương thích với phần sort:

~~~javascript
.sort({ createdAt: -1, _id: -1 }) // Cùng chiều index.
.sort({ createdAt:  1, _id:  1 }) // Đảo đồng thời cả hai chiều.
~~~

Còn kiểu sort sau không tương thích với chính thứ tự đó:

~~~javascript
.sort({ createdAt: -1, _id: 1 })
~~~

Để tối ưu trường hợp thứ ba có thể cần index khác hoặc chấp nhận sort bổ sung. Không suy luận từ một truy vấn chỉ sort createdAt rằng mọi tổ hợp chiều createdAt + _id đều được hỗ trợ.

### 3.4. Trường equality có thứ tự tùy ý hay không?

Với truy vấn luôn cố định cả tenantId và status, hai index sau đều có thể giảm phạm vi tìm kiếm trước khi sort:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
{ status: 1, tenantId: 1, createdAt: -1, _id: -1 }
~~~

Nhưng nếu ứng dụng thường truy vấn **theo tenant mà không lọc status**, thứ tự có tenantId đầu tiên hữu dụng hơn cho pattern đó. Nên chọn thứ tự equality dựa trên nhóm query thực tế, cardinality, nhu cầu reuse prefix và khả năng phân vùng theo tenant. Không có công thức bắt buộc trường có cardinality cao nhất luôn đứng đầu trong mọi trường hợp.

## 4. Filter range: khi ESR và ERS dẫn tới đánh đổi

Giả sử màn hình còn lọc các đơn có số tiền từ một ngưỡng:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  totalAmount: { $gte: NumberDecimal("1000000") }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Hai phương án ứng viên:

~~~javascript
// ESR: equality → sort → range.
db.orders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1, totalAmount: 1 },
  { name: "idx_orders_esr" }
);

// ERS: equality → range → sort.
db.orders.createIndex(
  { tenantId: 1, status: 1, totalAmount: 1, createdAt: -1, _id: -1 },
  { name: "idx_orders_ers" }
);
~~~

**ESR** ưu tiên trình tự kết quả theo createdAt/_id để tránh blocking sort; đổi lại, nếu rất ít đơn vượt ngưỡng tiền, MongoDB có thể phải đi qua nhiều entry trước khi tìm đủ 20 đơn phù hợp.

**ERS** đặt totalAmount range trước phần sort; nhờ đó có thể thu hẹp các entry sớm hơn. Tuy nhiên, vì totalAmount không cố định ở một giá trị, thứ tự createdAt toàn cục trong các khoảng tiền không còn liền mạch. Query có thể phải sort các bản phù hợp, tốn CPU/bộ nhớ.

| Điều kiện dữ liệu | Ứng viên thường nên đo trước | Lý do |
| --- | --- | --- |
| Người dùng luôn yêu cầu top 20 mới nhất; range không quá chọn lọc | ESR | Giữ khả năng đọc kết quả theo sort. |
| Range cực kỳ chọn lọc, ít tài liệu phù hợp | ERS | Giảm số lượng khóa cần tìm trước khi sort. |
| Không có điều kiện totalAmount | Index cơ bản theo equality + sort | Tránh thêm trường khiến index lớn hơn khi chưa cần thiết. |
| Có nhiều query shape khác nhau | Bộ index tối thiểu theo workload | Mỗi index thêm đều làm tăng chi phí bảo trì khi ghi. |

Không tạo hai index ESR và ERS trên production chỉ vì cùng tồn tại hai quy tắc. Hãy đo với phân bố dữ liệu gần thực tế, đặc biệt các giá trị totalAmount ở nhiều percentile và các tenant có quy mô khác nhau.

Lưu ý thêm: các toán tử như **$gt, $lt, $ne, $nin** và một số trường hợp **$in** nhiều giá trị tạo ra những khoảng/phương án thực thi khác equality đơn giản. Hành vi tối ưu sort có thể thay đổi theo cấu trúc truy vấn và phiên bản MongoDB; luôn kiểm tra explain thay vì áp ESR theo chữ cái.

## 5. Collation: index và truy vấn phải cùng cách so sánh chuỗi

### 5.1. Vấn đề với tên tiếng Việt

Giả sử collection **customers**:

~~~javascript
{ _id: ObjectId("65350f8453dbe413901c1221"),
  tenantId: "tenant-A",
  displayName: "Nguyễn An" }

{ _id: ObjectId("65350f8453dbe413901c1222"),
  tenantId: "tenant-A",
  displayName: "nguyễn bình" }

{ _id: ObjectId("65350f8453dbe413901c1223"),
  tenantId: "tenant-A",
  displayName: "Nguyen Cuong" }
~~~

Sắp xếp nhị phân mặc định (**simple collation**) dựa trên chuỗi byte, không tự nhiên cho mọi ngôn ngữ. MongoDB hỗ trợ **collation** để so sánh và sắp xếp theo locale, strength và những tùy chọn ICU liên quan.

Ví dụ tạo index để lọc tenant, sort tên rồi dùng _id phân giải trường hợp cùng thứ tự:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, displayName: 1, _id: 1 },
  {
    name: "idx_customers_tenant_name_vi",
    collation: { locale: "vi", strength: 2 }
  }
);
~~~

Và query phải dùng **cùng collation**:

~~~javascript
db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ displayName: 1, _id: 1 })
  .limit(20);
~~~

**strength: 2** phân biệt dấu nhưng bỏ qua khác biệt chữ hoa/thường trong so sánh cơ bản; **strength: 1** còn bỏ qua cả khác biệt dấu ở cấp so sánh chính. Cách sắp xếp thực tế do ICU/locale xác định; hãy kiểm thử những ví dụ tên tiếng Việt của hệ thống, không tự suy đoán toàn bộ thứ tự ký tự.

Truy vấn không ghi collation sẽ dùng **collation mặc định của collection** (nếu có), nếu không là simple. Một index collation tiếng Việt thường **không thể phục vụ việc so sánh/sort chuỗi** của query dùng simple collation. MongoDB có thể vẫn sử dụng phần tiền tố không phải chuỗi trong một số tình huống, nhưng không nên hiểu đó là đã tối ưu được sort displayName.

### 5.2. Khác nhau ở đâu?

| Trường hợp | Có thể tận dụng index collation cho chuỗi? | Giải thích |
| --- | --- | --- |
| Index vi, strength 2; query vi, strength 2 | Có, nếu điều kiện khóa cũng phù hợp | Cùng quy tắc so sánh chuỗi. |
| Index vi, strength 2; query simple | Không cho phần so sánh/sort chuỗi theo index đó | Quy tắc so sánh không khớp. |
| Index vi, strength 2; query vi, strength 1 | Không cho phần so sánh/sort chuỗi theo index đó | Strength khác nhau. |
| Truy vấn chỉ dùng tiền tố số của index có collation khác | Có thể dùng tiền tố, tùy kế hoạch | Không đồng nghĩa phần sort chuỗi được tối ưu. |

Collation có thể làm **index key lớn hơn** do dùng khóa ICU. Khi chọn strength, locale hoặc numericOrdering, nên thống nhất quy ước cho cả index và query, đồng thời cân nhắc việc tạo nhiều index trùng khóa chỉ khác collation.

**Collation không khiến regex chứa cờ i trở thành truy vấn được tăng tốc bằng index collation.** Tìm kiếm gần đúng, substring, fuzzy search hoặc autocomplete có yêu cầu khác; có thể cần thiết kế truy vấn và công cụ tìm kiếm riêng.

### 5.3. Collation và phân trang

Nếu phân trang theo displayName:

~~~javascript
.sort({ displayName: 1, _id: 1 })
~~~

Việc thêm _id giúp thứ tự **toàn phần** trong trường hợp các tên bằng nhau theo collation. Cursor của trang sau phải giữ được **giá trị displayName và _id cuối trang**, sử dụng đúng collation cũ và cùng điều kiện filter. Không được đổi locale/strength giữa hai trang rồi tiếp tục dùng cursor cũ, vì quan hệ lớn hơn/nhỏ hơn có thể đổi.

Đối với keyset, các trường sort nên không null và ổn định. Nếu ứng dụng cho phép sửa tên khách hàng, phần tử có thể chuyển vị trí giữa các lần tải; cần chấp nhận hành vi đó hoặc đưa ra cơ chế snapshot/watermark phù hợp yêu cầu.

## 6. Phân trang: offset và keyset không tương đương về chi phí

### 6.1. Offset pagination bằng skip/limit

Ví dụ trang thứ 1001 nếu mỗi trang có 20 đơn, đếm trang từ 1:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.skip(20000)
.limit(20);
~~~

Index tốt giúp tránh sắp xếp tốn kém, nhưng **skip không dịch chuyển tức thời đến bản ghi thứ 20.001**. Máy chủ vẫn phải duyệt/bỏ qua các kết quả trước đó. Vì vậy, số khóa cần xử lý thường tăng theo độ sâu trang, kể cả khi chỉ trả về 20 document.

Ưu điểm của offset:

- Dễ triển khai API với page number và page size.
- Phù hợp khi dữ liệu ít hoặc người dùng chỉ xem vài trang đầu.
- Dễ kết hợp giao diện nhảy đến một số trang cụ thể.

Nhược điểm:

- Trang sâu có chi phí tăng dần.
- Khi dữ liệu mới được chèn hoặc xóa giữa các lần xem, vị trí offset thay đổi; người dùng có thể gặp kết quả trùng hoặc bị bỏ qua.
- Khi trả Page<T> và yêu cầu tổng số trang, ứng dụng còn có thể phải chạy thêm count query.

**Luôn thêm khóa sort duy nhất** như _id để các document có createdAt giống nhau không bị đổi vị trí ngẫu nhiên giữa hai lần query. Sort ổn định giúp tính nhất quán thứ tự, nhưng không loại bỏ hoàn toàn ảnh hưởng của dữ liệu ghi đồng thời.

### 6.2. Keyset/cursor pagination theo cặp (createdAt, _id)

Thay vì yêu cầu bỏ qua N document, client gửi vị trí cuối cùng đã đọc.

Trang đầu:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Giả sử phần tử cuối trang đầu có:

~~~javascript
{
  _id: ObjectId("65350f8453dbe413901c1211"),
  createdAt: ISODate("2026-11-18T08:30:00Z")
}
~~~

Với sort giảm dần cho **cả hai trường**, phần tử thuộc trang tiếp theo phải thỏa:

~~~text
createdAt < lastCreatedAt
HOẶC
(createdAt = lastCreatedAt VÀ _id < lastId)
~~~

Truy vấn trang tiếp theo:

~~~javascript
const lastCreatedAt = ISODate("2026-11-18T08:30:00Z");
const lastId = ObjectId("65350f8453dbe413901c1211");

db.orders.find({
  tenantId: "tenant-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Compound index ban đầu phù hợp để thử trước:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1, _id: -1 }
~~~

Chú ý **không** dùng:

~~~javascript
// Sai: bỏ mất các document có cùng createdAt nhưng _id nhỏ hơn.
{ createdAt: { $lt: lastCreatedAt } }
~~~

Và cũng không dùng hai điều kiện range độc lập:

~~~javascript
// Sai: yêu cầu cả hai trường đều nhỏ hơn, loại nhầm bản ghi hợp lệ.
{ createdAt: { $lt: lastCreatedAt }, _id: { $lt: lastId } }
~~~

Nhờ predicate theo vị trí, keyset thường tránh chi phí tăng tuyến tính vì phải skip mọi trang trước. Tuy nhiên, pipeline có $or vẫn cần quan sát explain trên MongoDB và dữ liệu thật; việc chọn index hoặc mức quét không phải bảo đảm tuyệt đối chỉ từ hình dạng truy vấn.

### 6.3. Cursor cần chứa thông tin nào?

Một cursor có thể mang:

~~~json
{
  "createdAt": "2026-11-18T08:30:00.000Z",
  "id": "65350f8453dbe413901c1211",
  "sort": "createdAt:desc,id:desc",
  "filtersFingerprint": "hash-of-tenant-and-status",
  "version": 1
}
~~~

Đây là **cấu trúc minh họa**, không phải token đã ký. Hệ thống thực tế nên encode và ký/xác thực cursor, kiểm tra tenant, điều kiện lọc, sort, collation và giới hạn thời hạn sử dụng. Không dùng nội dung cursor từ client để bỏ qua kiểm tra quyền tenant.

Nếu sort thay đổi sang tăng dần, các toán tử so sánh phải đổi tương ứng. Nếu giá trị ngày là nullable hoặc thời gian bị chỉnh sửa sau khi tạo, cần thay đổi contract dữ liệu hoặc thiết kế cursor; so sánh range có null rất dễ gây mất kết quả.

### 6.4. Page, Slice và Window trong Spring Data

| Kiểu trả về | Điểm mạnh | Lưu ý hiệu năng |
| --- | --- | --- |
| Page<T> | Có thông tin tổng số, tổng trang | Có thể phát sinh count query; chủ yếu đi cùng offset. |
| Slice<T> | Biết còn trang tiếp mà không luôn cần tổng số | Thường vẫn dùng offset nếu dựa vào Pageable. |
| Window<T> + OffsetScrollPosition | Hỗ trợ duyệt theo từng nhóm | Vẫn chịu chi phí offset lớn. |
| Window<T> + KeysetScrollPosition | Spring Data xây dựng predicate theo keyset | Phải có sort key không null, index phù hợp và trả đủ key trong projection. |
| Keyset viết bằng Query/Criteria | Chủ động với API riêng và cursor token | Phải tự kiểm soát so sánh, điều kiện lọc, sort và token. |

Spring Data MongoDB hỗ trợ cơ chế **scrolling bằng Window và ScrollPosition** ở các API repository tương ứng. Khi sử dụng keyset scrolling, Spring Data có thể thêm khóa định danh vào sort để bảo đảm tính duy nhất; projection phải có tất cả trường tham gia sort. Đối với màn hình đơn hàng đang minh họa, phần tiếp theo dùng MongoTemplate để thấy rõ predicate tạo ra trên MongoDB.

## 7. Triển khai bằng Spring Data MongoDB

### 7.1. Khai báo entity và index

Entity mẫu:

~~~java
package example.orders;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record Order(
    @Id ObjectId id,
    String tenantId,
    String status,
    Instant createdAt,
    String customerName
) {}
~~~

Tạo index chủ động qua MongoTemplate:

~~~java
package example.orders;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public final class OrderIndexInstaller {
    private OrderIndexInstaller() {}

    public static void create(MongoTemplate template) {
        Index index = new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("status", Sort.Direction.ASC)
            .on("createdAt", Sort.Direction.DESC)
            .on("_id", Sort.Direction.DESC)
            .named("idx_orders_tenant_status_created_id");

        template.indexOps(Order.class).createIndex(index);
    }
}
~~~

Phương thức **createIndex(IndexDefinition)** được cung cấp ở những bản Spring Data MongoDB mới (từ dòng 4.5); các phiên bản cũ dùng **ensureIndex**. Ví dụ chủ động tạo index trên là một thao tác quản trị cần triển khai theo cơ chế migration/chế độ khởi động được kiểm soát, **không gọi trong mỗi HTTP request**. Spring Data không mặc định tự tạo index từ mọi annotation trên mọi phiên bản; từ Spring Data MongoDB 3.0 việc auto-index-creation được tắt theo mặc định nếu không cấu hình bật.

Có thể khai báo bằng **@CompoundIndex** ở cấp class khi cơ chế quản lý index của ứng dụng đã rõ:

~~~java
@CompoundIndex(
  name = "idx_orders_tenant_status_created_id",
  def = "{ 'tenantId': 1, 'status': 1, 'createdAt': -1, '_id': -1 }"
)
~~~

Đoạn annotation trên là ví dụ khai báo đặt trên class được đánh dấu @Document. Không dùng đồng thời nhiều cơ chế tạo cùng index nếu chưa xác định quy trình quản lý schema và quyền trên database.

### 7.2. Query offset bằng MongoTemplate

~~~java
package example.orders;

import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderReadService {
    private final MongoTemplate template;

    public OrderReadService(MongoTemplate template) {
        this.template = template;
    }

    public List<Order> pageByOffset(
            String tenantId, String status, int page, int pageSize) {

        if (page < 0 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid pagination request");
        }

        long offset = (long) page * pageSize;

        Query query = Query.query(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is(status)
        )
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id") // Entity id được ánh xạ thành _id.
        ))
        .skip(offset)
        .limit(pageSize);

        return template.find(query, Order.class);
    }
}
~~~

Ở đây page bắt đầu từ 0. Ngoài việc giới hạn pageSize, API production có thể giới hạn offset tối đa hoặc chuyển sang cursor khi người dùng duyệt nhiều trang. Không nhận tùy ý mọi trường sort từ client rồi ghép thẳng vào index strategy mà không có danh sách cho phép.

### 7.3. Query keyset bằng MongoTemplate

Thêm một phương thức trong chính service trên; các import cần thiết được chỉ rõ:

~~~java
import java.time.Instant;
import org.bson.types.ObjectId;

public List<Order> pageAfter(
        String tenantId, String status,
        Instant lastCreatedAt, ObjectId lastId, int pageSize) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid page size");
    }
    if ((lastCreatedAt == null) != (lastId == null)) {
        throw new IllegalArgumentException("Cursor must contain both keys");
    }

    Criteria filter = new Criteria().andOperator(
        Criteria.where("tenantId").is(tenantId),
        Criteria.where("status").is(status)
    );

    if (lastCreatedAt != null) {
        Criteria after = new Criteria().orOperator(
            Criteria.where("createdAt").lt(lastCreatedAt),
            new Criteria().andOperator(
                Criteria.where("createdAt").is(lastCreatedAt),
                Criteria.where("_id").lt(lastId)
            )
        );

        filter = new Criteria().andOperator(filter, after);
    }

    Query query = new Query(filter)
        .with(Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("id")
        ))
        .limit(pageSize);

    return template.find(query, Order.class);
}
~~~

Đoạn phương thức được đặt **bên trong OrderReadService** ở phần 7.2 để dùng trường template của service. Khi gọi lần đầu, truyền null cho cả hai khóa cursor; các lần tiếp theo dùng createdAt và id của phần tử cuối trang. Trong query raw MongoDB, trường định danh lưu ở **_id**; trong Sort của Spring Data entity, property tên **id** được ánh xạ sang **_id**.

Nếu cần trả thêm hasNext một cách tin cậy cho UI, có thể lấy pageSize + 1 bản ghi (với điều kiện giới hạn hợp lý), giữ lại pageSize để hiển thị và dùng bản ghi dư làm dấu hiệu còn trang. Cursor trang tiếp theo phải lấy từ **phần tử cuối thực sự đã trả cho client**, không lấy từ bản ghi dư.

### 7.4. Collation trong MongoTemplate

Một ví dụ query collection customers theo tiếng Việt, dùng raw Document để chỉ tập trung vào filter/sort:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Collation;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Document> listCustomers(
        MongoTemplate template, String tenantId) {

    Collation vietnamese = Collation.of("vi").strength(2);

    Query query = Query.query(Criteria.where("tenantId").is(tenantId))
        .collation(vietnamese)
        .with(Sort.by(
            Sort.Order.asc("displayName"),
            Sort.Order.asc("_id")
        ))
        .limit(20);

    return template.find(query, Document.class, "customers");
}
~~~

Điều quan trọng là index của customers cũng dùng **{ locale: "vi", strength: 2 }** như phần 5. Dù code Java có cấu hình Collation, truy vấn vẫn có thể chậm nếu collection chỉ tồn tại index simple collation hoặc nếu thứ tự khóa index không khớp query.

## 8. Dùng explain để xác nhận index thật sự có ích

### 8.1. Đọc các chỉ số cơ bản

Chạy truy vấn đại diện trong mongosh:

~~~javascript
db.orders.find({
  tenantId: "tenant-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Các thông số cần xem:

| Thông tin | Ý nghĩa | Cách diễn giải |
| --- | --- | --- |
| winningPlan | Kế hoạch được chọn | Kiểm tra indexName, IXSCAN, FETCH, SORT/COLLSCAN; cây stage phụ thuộc engine/phiên bản. |
| executionStats.nReturned | Số document được trả về | Dùng làm mẫu số khi so mức quét. |
| totalKeysExamined | Số entry index đã duyệt | Càng gần nReturned càng tốt trong nhiều truy vấn lọc tốt, nhưng không phải quy luật tuyệt đối. |
| totalDocsExamined | Số document đã đọc để xét điều kiện/trả dữ liệu | Cao hơn nhiều nReturned có thể cho thấy filter chưa hiệu quả. |
| executionTimeMillis | Thời gian thực thi trong explain | Dùng so sánh tương đối, không thay thế benchmark p95 tại ứng dụng. |
| SORT stage | Sắp xếp trong bộ nhớ hoặc blocking stage | Thường là dấu hiệu cần kiểm tra thứ tự khóa, chiều sort và collation. |
| COLLSCAN | Quét collection | Không phải luôn sai với collection nhỏ, nhưng đáng điều tra ở truy vấn lớn/tần suất cao. |

Ví dụ minh họa hai kết quả giả định, **không phải số đo thực tế**:

| Chỉ số | Trước index phù hợp | Sau index phù hợp |
| --- | ---: | ---: |
| nReturned | 20 | 20 |
| totalKeysExamined | 40.000 | 20 |
| totalDocsExamined | 30.000 | 20 |
| SORT stage | Có | Không |
| Thời gian đo trên cùng dữ liệu | Cao | Thấp hơn |

Việc totalDocsExamined bằng 0 **không phải điều kiện bắt buộc** cho index tốt. Nếu query trả các field không nằm trong index, MongoDB vẫn cần FETCH document; đó có thể là đánh đổi hợp lý.

Từ MongoDB phiên bản mới, giải thích kế hoạch có thể sử dụng **slot-based execution engine (SBE)** và cây stage khác ví dụ cổ điển. Thay vì chỉ tìm một nhãn ở đúng vị trí cố định trong JSON, hãy kiểm tra toàn bộ queryPlanner, executionStats và index được dùng.

### 8.2. Đo đúng hai biến thể quan trọng

Thử hai query tương tự về filter nhưng khác sort:

~~~javascript
// Query A: có equality trên cả hai khóa đầu.
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");

// Query B: thiếu status; cùng index có thể kém phù hợp cho sort.
db.orders.find({ tenantId: "tenant-A" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
~~~

Thử collation đúng và sai với cùng bộ lọc:

~~~javascript
db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "vi", strength: 2 })
  .sort({ displayName: 1, _id: 1 })
  .limit(20)
  .explain("executionStats");

db.customers.find({ tenantId: "tenant-A" })
  .collation({ locale: "simple" })
  .sort({ displayName: 1, _id: 1 })
  .limit(20)
  .explain("executionStats");
~~~

Thử phân trang nông và sâu với cùng index:

~~~javascript
db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0).limit(20)
  .explain("executionStats");

db.orders.find({ tenantId: "tenant-A", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(20000).limit(20)
  .explain("executionStats");
~~~

Ghi lại dữ liệu đầu vào và số đo trước/sau để so sánh. Với query thực tế, nên thử thêm những tenant lớn/nhỏ, trạng thái phổ biến/hiếm và các khoảng lọc có độ chọn lọc khác nhau. Index planner có thể chọn phương án khác khi phân bố dữ liệu đổi.

**Lưu ý:** Explain tự thực thi kế hoạch để thu thập thống kê, có thể gây tải. Kết quả explain không nhất thiết phản ánh chính xác độ trễ mạng hoặc hành vi query plan cache trong hoạt động bình thường. Không chạy explain quét dữ liệu rất lớn một cách tùy tiện trên production; nên xác nhận với môi trường kiểm thử có dữ liệu đại diện và kết hợp số đo thực tế của ứng dụng.

## 9. Những tối ưu bổ sung cần cân nhắc

### 9.1. Projection và covered query

Nếu màn hình danh sách chỉ cần tenantId, status, createdAt và _id, có thể giới hạn field trả về:

~~~javascript
db.orders.find(
  { tenantId: "tenant-A", status: "PAID" },
  { tenantId: 1, status: 1, createdAt: 1, _id: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Khi tất cả trường dùng để lọc, sort và trả về đều nằm trong index, một số query có thể được **covered**, giúp tránh đọc document đầy đủ. Nhưng không phải index nào có nhiều trường cũng tạo covered query: còn phụ thuộc index type, điều kiện, projection, collation, array/multikey và kế hoạch thực thi.

Không thêm tất cả field của một document vào index chỉ để đạt totalDocsExamined = 0. Index quá rộng tiêu tốn dung lượng, giảm hiệu quả bộ nhớ cache và làm tăng chi phí insert/update/delete.

### 9.2. Partial index cho một màn hình rất cụ thể

Giả sử hầu hết thao tác quản trị chỉ xem trạng thái PAID:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  {
    name: "idx_orders_paid_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
~~~

Index này chỉ chứa các document PAID, nên có thể nhỏ hơn index toàn bộ. Query phù hợp phải **bao hàm điều kiện status: "PAID"** để kết quả không bị thiếu. Query lấy cả PENDING không thể dùng partial index này để trả dữ liệu đầy đủ.

Không nhầm **partial index** với **sparse index**. Partial index dựa trên biểu thức filter rõ ràng; điều kiện áp dụng phải được query planner xác nhận bằng explain. Nếu status phân bố gần như toàn bộ đều PAID hoặc nhiều màn hình cần trạng thái khác nhau, lợi ích thực tế có thể thấp.

### 9.3. Multikey và dữ liệu mảng

Khi một trường index là mảng, MongoDB tạo **multikey index**. Một số tổ hợp sort và filter trên mảng vẫn dẫn tới blocking SORT dù có index; compound multikey còn có ràng buộc khi nhiều trường index cùng chứa array trong một document.

Vì vậy, ví dụ đơn hàng dùng các trường scalar có kiểu ổn định. Nếu mở rộng filter theo mảng tags, products hoặc promotions, cần đo lại kế hoạch; không tự mở rộng index scalar hiện tại rồi kỳ vọng giữ nguyên hiệu năng.

### 9.4. Chi phí write, bộ nhớ và index trùng lặp

Mỗi index phải được cập nhật khi document được insert/delete hoặc các trường index thay đổi. Một tập index dư thừa thường khiến:

- Dung lượng disk và cache bị chiếm nhiều hơn.
- Ghi đơn hàng hoặc thay đổi status tốn thêm I/O.
- Quá trình tạo index hoặc deploy schema kéo dài.
- Có nhiều index giống nhau khiến vận hành khó đo lường và kiểm soát.

Sử dụng **db.orders.getIndexes()** để kiểm tra cấu hình hiện tại. Khi cân nhắc bỏ index cũ, phải đo những query đang dùng nó. MongoDB hỗ trợ **hidden indexes** để đánh giá hệ quả đối với planner trước khi xóa vĩnh viễn trong những môi trường/phiên bản có hỗ trợ; vẫn cần phối hợp với quy trình vận hành vì thao tác ẩn index có thể ảnh hưởng workload thật.

## 10. Kiểm thử chức năng và hiệu năng

Một index mới phải giữ nguyên ý nghĩa truy vấn. Sau khi tạo index, kiểm thử theo cả hai nhóm: **đúng dữ liệu** và **tốc độ/tài nguyên**.

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Có hai đơn cùng createdAt | Thứ tự theo _id là xác định; sang trang không lặp/mất bản ghi trong tập dữ liệu tĩnh. |
| Tenant A và tenant B có status giống nhau | Query chỉ trả đơn tenant được phép; không rò dữ liệu. |
| Không lọc status | Đo lại explain vì index có status trước createdAt có thể không hỗ trợ sort như kỳ vọng. |
| Range totalAmount rộng và hẹp | Đo ESR và ERS với nReturned, keysExamined, docsExamined, SORT. |
| Tên tiếng Việt khác dấu/hoa thường | Collation áp dụng đúng contract; index được chọn như mong muốn. |
| Query dùng collation không khớp index | Phát hiện plan và latency thay đổi; không đoán rằng vẫn tận dụng index sort. |
| Skip 0, 1.000 và 20.000 | Kiểm chứng chi phí offset tăng theo trang. |
| Keyset trang đầu và các trang sau | Đúng thứ tự, cursor không làm thiếu bản có cùng timestamp. |
| Chèn/xóa trong lúc duyệt | Hành vi phù hợp contract về tính nhất quán; thử lại nếu yêu cầu snapshot. |
| Tăng tỷ lệ ghi đồng thời | P95/p99 đọc, throughput ghi và mức dùng disk/cache vẫn chấp nhận được. |

Trình tự thực nghiệm đề xuất:

1. **Chốt query shape và tiêu chí:** p95, số bản ghi trả về, tỷ lệ keysExamined/nReturned, chức năng phân trang, công suất ghi.
2. **Lưu baseline:** chạy explain, quan sát log/profiler và đo latency của ứng dụng trước khi thêm index.
3. **Tạo index ứng viên trong môi trường đo:** có dữ liệu và phân bố giống workload thực tế.
4. **Đo lại cùng truy vấn:** cùng filter, sort, collation, giới hạn, projection và độ sâu trang; so với baseline.
5. **Kiểm thử tính đúng:** đặc biệt ở ranh giới trang, timestamp trùng, dữ liệu thêm/xóa và chuỗi có dấu.
6. **Xem chi phí vận hành:** index size, số index, throughput ghi, buffer/cache và kế hoạch triển khai.
7. **Phê duyệt bằng số đo:** chỉ giữ index có lợi ích đủ lớn cho truy vấn trọng yếu, loại bỏ index ứng viên dư thừa theo quy trình.

Không đặt một chỉ tiêu kiểu “totalKeysExamined luôn bằng 20” cho mọi query. Phép lọc range, trường có nhiều kết quả bị loại, cover/no-cover và kế hoạch thực thi có thể khiến mức quét hợp lý cao hơn. Chỉ số cần đặt trong bối cảnh cùng workload và dữ liệu.

## 11. Các lỗi thiết kế thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Tạo index riêng tenantId, status, createdAt mà không đo compound index | Planner có thể lọc được nhưng phải sort nhiều document | Thiết kế index cho pattern filter + sort thường dùng. |
| Đặt createdAt trước tất cả equality | Có thể quét nhiều tenant hoặc status | Thử thứ tự ESR, đo phân bố thực tế. |
| Chỉ sort createdAt | Timestamp trùng gây thứ tự thiếu xác định | Thêm _id làm tiebreaker trong sort và index. |
| Thiếu equality cho khóa prefix trước sort | MongoDB khó dùng index để cung cấp thứ tự mong muốn | Bổ sung filter hoặc tạo index theo query shape khác. |
| Index sort DESC/DESC nhưng query DESC/ASC | Có thể phải SORT | Đồng bộ chiều hoặc thiết kế index khác. |
| Query tiếng Việt nhưng collation không khớp index | Không tận dụng sort chuỗi theo index | Dùng cùng locale/strength và kiểm tra explain. |
| Dùng regex /i và kỳ vọng collation index xử lý | Kế hoạch tìm kiếm có thể vẫn quét lớn | Dùng truy vấn equality được collation hỗ trợ hoặc giải pháp search. |
| Dùng skip rất lớn cho infinite scroll | Chi phí tăng theo độ sâu trang | Dùng keyset/cursor với các sort key có index. |
| Keyset chỉ dựa createdAt | Trùng timestamp gây mất bản ghi | Cursor phải chứa đủ createdAt và _id. |
| Thay filter/sort nhưng giữ cursor cũ | Sai vị trí, lặp/thiếu kết quả | Gắn cursor với query shape và kiểm tra hợp lệ. |
| Cố covered query bằng index quá rộng | Tăng write amplification và disk/cache | Đo tổng chi phí, giới hạn projection hợp lý. |
| Dựa vào explain trên vài document | Planner trên dữ liệu nhỏ không đại diện | Kiểm tra dữ liệu đa dạng và tải thực tế. |

## 12. Bài thực hành

Tạo một collection đơn hàng đủ lớn trong môi trường thử nghiệm, chứa nhiều tenant, nhiều status và một số đơn có cùng createdAt. Thực hiện tuần tự:

1. Chạy query lọc tenantId + status, sort createdAt DESC và _id DESC khi chưa tạo compound index; lưu explain.
2. Tạo index **{tenantId:1, status:1, createdAt:-1, _id:-1}**; chạy lại cùng query, so sánh metrics.
3. Bỏ điều kiện status; quan sát planner. Đề xuất index cho query mới rồi đo lại.
4. Thêm totalAmount range, so sánh ứng viên ESR với ERS ở khoảng tiền rộng và hẹp.
5. Tạo customers với tên tiếng Việt và index collation vi strength 2; thử query tương thích và không tương thích.
6. So sánh skip(0), skip(10000) với keyset sau mốc tương ứng; ghi nhận keysExamined, docsExamined và thời gian.
7. Tạo vài đơn trùng timestamp, kiểm thử chuyển liên tục qua các trang không làm mất hoặc nhân đôi kết quả trong tập tĩnh.
8. Viết một báo cáo ngắn kết luận index nào cần giữ theo workload đã đo và chi phí ghi của hệ thống.

**Câu hỏi tự đánh giá:**

- Tại sao một compound index có đủ tên trường vẫn có thể không giúp sort?
- ESR và ERS khác nhau ở điểm nào, khi nào nên đo cả hai?
- Vì sao index được tạo với collation tiếng Việt có thể không cải thiện query dùng simple collation?
- Vì sao thêm _id vào sort quan trọng ngay cả khi createdAt có vẻ “gần như duy nhất”?
- Tại sao keyset có lợi ở trang sâu nhưng vẫn có thể bị ảnh hưởng bởi dữ liệu cập nhật giữa hai lần gọi?

Hiệu quả của index đến từ sự phù hợp với **filter, thứ tự sort, collation và kiểu phân trang cụ thể**, không phải số lượng index đã tạo. Chọn một query shape quan trọng, thiết kế index ứng viên, đo bằng explain và benchmark thực tế, rồi giữ lại phương án cho kết quả tốt nhất với chi phí vận hành chấp nhận được.

## 13. Tài liệu tham khảo

- [MongoDB – ESR Guideline](https://www.mongodb.com/docs/manual/tutorial/equality-sort-range-guideline/): thứ tự equality, sort, range và trường hợp ERS.
- [MongoDB – Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/): index prefix và thứ tự khóa.
- [MongoDB – Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/): hỗ trợ sort, non-prefix sort và chiều index.
- [MongoDB – Collation](https://www.mongodb.com/docs/manual/reference/collation/): locale, strength và so sánh chuỗi.
- [MongoDB – Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/): yêu cầu collation tương thích.
- [MongoDB – cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/): chi phí offset, thứ tự ổn định và range pagination.
- [MongoDB – Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): queryPlanner và executionStats.
- [MongoDB – Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): phạm vi index và điều kiện query có thể sử dụng.
- [Spring Data MongoDB – Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html): Query/Criteria, sort, collation và index hints.
- [Spring Data MongoDB – Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): IndexOperations và quản lý index.
- [Spring Data MongoDB – Collations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/collation.html): Collation trong Spring Data.
- [Spring Data MongoDB – Repository Scrolling](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html): Window, offset và keyset.
