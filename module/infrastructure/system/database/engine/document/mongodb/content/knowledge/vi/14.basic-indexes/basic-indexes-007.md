# Truy vấn được index bao phủ và điều kiện cần đọc document trong MongoDB

Một index không chỉ giúp MongoDB **tìm document nhanh hơn**. Trong một số trường hợp, nó còn chứa đủ thông tin để MongoDB **trả luôn kết quả** mà **không cần mở document gốc trong collection**. Đây là **truy vấn được index bao phủ** (*covered query*). Hiểu chính xác khái niệm này giúp thiết kế compound index phù hợp, giảm số lần đọc document, giảm I/O và đánh giá execution plan bằng `explain()`.

Tuy nhiên, **có dùng index** không đồng nghĩa với **được index bao phủ**. Một truy vấn có thể sử dụng `IXSCAN` để tìm khóa phù hợp, sau đó vẫn phải dùng `FETCH` để đọc tài liệu nhằm lấy trường chưa có trong index hoặc đánh giá điều kiện chưa được index đáp ứng.

Bài học này giải thích:

- Covered query là gì và khác một truy vấn **chỉ dùng index để lọc/sort** như thế nào.
- Điều kiện cần để filter, projection và sort có thể xử lý bằng index.
- Khi nào MongoDB cần đọc document, kể cả khi `explain` cho thấy index đã được sử dụng.
- Cách nhận biết `IXSCAN`, `FETCH`, `COLLSCAN`, `totalKeysExamined` và `totalDocsExamined`.
- Các trường hợp đặc biệt: `_id`, điều kiện `null`, multikey index, trường lồng nhau, collation, index một phần và sharding.
- Cách quyết định có nên mở rộng compound index để bao phủ một truy vấn thường xuyên hay không.

## 1. Từ index lookup đến covered query

### 1.1. Index chứa những gì?

Đối với B-tree index thông thường, MongoDB lưu các **khóa index** được tạo từ những trường đã khai báo, liên kết với thông tin giúp định vị document nguồn. Xem một index ghép:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  customerId: 1,
  createdAt: -1
});
~~~

Index này lưu các thành phần khóa:

~~~text
(tenantId, status, customerId, createdAt)
                |
                v
         Vị trí document nguồn
~~~

Tùy query, MongoDB có thể dùng khóa của index để tìm những bản ghi phù hợp. Nếu muốn đọc trường `totalAmount` hay `internalNote` **không thuộc index**, MongoDB thường còn phải truy xuất document.

### 1.2. Index scan rồi đọc document

Một kế hoạch thường gặp:

~~~text
IXSCAN theo index
   |
   v
FETCH document trong collection
   |
   v
Projection trường trả về
   |
   v
Client
~~~

Ở đây:

1. `IXSCAN` duyệt các index key phù hợp.
2. `FETCH` truy xuất document gốc, chẳng hạn để lấy `totalAmount`.
3. MongoDB áp dụng những điều kiện/phép chiếu còn lại và trả kết quả.

Dù query có dùng index hiệu quả, nó **chưa phải covered query** vì document nguồn vẫn được xem xét.

### 1.3. Covered query: chỉ cần index

Khi **toàn bộ dữ liệu cần cho filter và kết quả** đã nằm trong index, MongoDB có thể thực thi:

~~~text
IXSCAN theo index
   |
   v
Projection trực tiếp từ index key
   |
   v
Client

Không cần FETCH document nguồn
~~~

Một index có thể phục vụ đồng thời việc xác định document khớp, sắp xếp và cung cấp các giá trị được trả về. Theo MongoDB Manual, điều kiện chính cho covered query gồm:

1. **Tất cả trường dùng trong filter** (bao gồm cả trường hệ thống cần thiết trong một số triển khai như sharding) được xử lý từ cùng index.
2. **Tất cả trường được trả về** cũng nằm trong **chính index đó**.
3. **Không có điều kiện lọc field bằng `null`**.
4. Index và dạng query đáp ứng những ràng buộc bổ sung của loại index, ví dụ các giới hạn về multikey.

Nếu query cần một khóa sort, việc sắp xếp cũng phải thực thi mà không cần đọc thêm trường từ document để giữ truy vấn ở trạng thái index-only.

**Định nghĩa thực tế:** Covered query là truy vấn có thể hoàn tất bằng index, **không kiểm tra bất kỳ document gốc nào**. Nó không có nghĩa là index làm truy vấn tốn 0 công việc: MongoDB vẫn có thể duyệt nhiều index key, giải mã giá trị và xây dựng kết quả.

## 2. Phân biệt ba mức độ sử dụng index

| Trường hợp | Index tham gia? | Đọc document nguồn? | Dấu hiệu thường gặp |
| --- | --- | --- | --- |
| **Collection scan** | Không dùng B-tree index cho việc duyệt chính | Có | `COLLSCAN` |
| **Index scan + fetch** | Có | Có | `IXSCAN` cùng `FETCH` |
| **Covered query** | Có | Không | `IXSCAN` và không có `FETCH`; `totalDocsExamined = 0` |

Ví dụ:

~~~text
Index: (status, customerId, createdAt)

Query A:
  filter  = status, customerId
  return  = customerId, createdAt
  _id     = loại bỏ
  => Có thể index-only

Query B:
  filter  = status, customerId
  return  = customerId, createdAt, totalAmount
  => Cần đọc document nếu totalAmount không nằm trong index

Query C:
  filter  = status, customerId, totalAmount > 100
  return  = customerId, createdAt
  => Cần đọc document để kiểm tra totalAmount
~~~

Các ví dụ mang tính mô hình. **Query planner quyết định kế hoạch thực tế**; phải xem `explain("executionStats")` thay vì kết luận chỉ từ hình dạng query. Index thiếu trường cần thiết thường không thể thực hiện một covered plan, nhưng optimizer có thể chọn index khác, index intersection hoặc collection scan tùy dữ liệu và danh sách index hiện có.

## 3. Tạo bộ dữ liệu thực hành

Mở `mongosh`, kết nối MongoDB đang chạy và sử dụng database riêng:

~~~javascript
const lab = db.getSiblingDB("mongo_covered_query_lab");

lab.orders.drop();

lab.orders.insertMany([
  {
    _id: ObjectId("000000000000000000000001"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-01T08:00:00Z"),
    totalAmount: 120,
    internalNote: "Đơn hàng gấp",
    tags: ["web", "priority"]
  },
  {
    _id: ObjectId("000000000000000000000002"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-03T08:00:00Z"),
    totalAmount: 150,
    internalNote: "Ưu đãi mùa hè",
    tags: ["web"]
  },
  {
    _id: ObjectId("000000000000000000000003"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C02",
    createdAt: ISODate("2026-06-03T09:00:00Z"),
    totalAmount: 240,
    internalNote: "Khách hàng mới",
    tags: ["store"]
  },
  {
    _id: ObjectId("000000000000000000000004"),
    tenantId: "T1",
    status: "PENDING",
    customerId: "C01",
    createdAt: ISODate("2026-06-04T10:00:00Z"),
    totalAmount: 90,
    internalNote: "Chưa thanh toán",
    tags: ["web"]
  },
  {
    _id: ObjectId("000000000000000000000005"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-05T08:00:00Z"),
    totalAmount: 175,
    internalNote: "Đã xác nhận",
    tags: ["web", "sale"]
  },
  {
    _id: ObjectId("000000000000000000000006"),
    tenantId: "T1",
    status: "PAID",
    customerId: "C03",
    createdAt: ISODate("2026-06-06T08:00:00Z"),
    totalAmount: 300,
    internalNote: "Giao thường",
    tags: ["store", "sale"]
  },
  {
    _id: ObjectId("000000000000000000000007"),
    tenantId: "T2",
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-07T08:00:00Z"),
    totalAmount: 210,
    internalNote: "Tenant khác",
    tags: ["web"]
  }
]);

lab.orders.find().sort({ createdAt: 1 });
~~~

Hai đặc điểm cần chú ý:

- `tenantId` phân biệt dữ liệu giữa các tenant, nên **không được bỏ điều kiện tenant** chỉ để làm query được bao phủ.
- `totalAmount` và `internalNote` là những trường **không nằm trong index minh họa ở phần tiếp theo**, giúp quan sát lúc nào cần `FETCH`.

Trong dữ liệu mẫu, các đơn `PAID` của tenant `T1` và khách `C01` là ba document có đuôi `_id` `01`, `02` và `05`.

## 4. Tạo compound index phục vụ covered query

Tạo index:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1
  },
  { name: "ix_tenant_status_customer_created" }
);

lab.orders.getIndexes();
~~~

Index này có các trường:

| Thành phần index | Vai trò trong ví dụ |
| --- | --- |
| `tenantId` | Điều kiện bằng để cô lập tenant |
| `status` | Điều kiện bằng để chọn đơn đã thanh toán |
| `customerId` | Điều kiện bằng để chọn khách |
| `createdAt` | Giá trị thời gian cần trả về và sort giảm dần |

Với filter equality ở ba trường đầu, MongoDB có thể khai thác thứ tự `createdAt: -1` trong phần index phù hợp. Chọn index theo **filter và sort thực tế** chứ không chỉ vì mong muốn covered query.

### 4.1. Truy vấn có thể được index bao phủ

~~~javascript
const coveredFilter = {
  tenantId: "T1",
  status: "PAID",
  customerId: "C01"
};

const coveredProjection = {
  _id: 0,
  status: 1,
  customerId: 1,
  createdAt: 1
};

lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .toArray();
~~~

Kết quả theo dữ liệu mẫu, mới nhất trước:

~~~javascript
[
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-05T08:00:00.000Z")
  },
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-03T08:00:00.000Z")
  },
  {
    status: "PAID",
    customerId: "C01",
    createdAt: ISODate("2026-06-01T08:00:00.000Z")
  }
]
~~~

Vì sao truy vấn có thể được bao phủ?

1. Filter `tenantId`, `status`, `customerId` đều là các khóa trong compound index.
2. Projection chỉ trả `status`, `customerId` và `createdAt`, tất cả đều có trong index.
3. Projection đặt rõ `_id: 0`; `_id` **không nằm trong compound index** đang dùng.
4. Sort `createdAt: -1` phù hợp với phần index nằm sau các trường equality.
5. Không có điều kiện bằng `null`, không cần trả về trường mảng.

`hint()` trong bài giúp chủ động chọn index muốn nghiên cứu; thông thường, **production không nhất thiết nên ép index**. Planner có thể chọn một kế hoạch khác khi dữ liệu và các index thay đổi.

### 4.2. Xem explain của truy vấn được bao phủ

~~~javascript
const coveredExplain = lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");

printjson({
  nReturned: coveredExplain.executionStats.nReturned,
  totalKeysExamined: coveredExplain.executionStats.totalKeysExamined,
  totalDocsExamined: coveredExplain.executionStats.totalDocsExamined
});

printjson(coveredExplain.queryPlanner.winningPlan);
~~~

Trong tình huống này, số `nReturned` dự kiến là **3**. Khi MongoDB thực thi theo covered plan, ta mong đợi:

~~~text
IXSCAN: có
FETCH: không
totalDocsExamined: 0
~~~

`totalKeysExamined` thường lớn hơn hoặc bằng số bản ghi được trả, nhưng giá trị chính xác có thể thay đổi theo optimizer, bounds và dữ liệu. Một covered query có thể quét index key mà không trả document nào; `totalDocsExamined: 0` vẫn đúng.

Trong một số phiên bản MongoDB, plan có stage `PROJECTION_COVERED` phía trên `IXSCAN`. Với các phiên bản dùng **slot-based query execution engine**, cấu trúc giải thích có thể khác. **Đừng viết logic vận hành phụ thuộc cứng vào việc một stage phải xuất hiện đúng tên ở cùng một cấp JSON.** Hãy kết hợp chỉ số document examined với cây kế hoạch thực tế.

## 5. Vì sao _id thường khiến query không được bao phủ?

### 5.1. _id được trả về mặc định

Trong MongoDB, `find(filter, projection)` thường trả `_id` nếu bạn không đặt `_id: 0`. Hãy bỏ điều kiện loại `_id` ở ví dụ trước:

~~~javascript
const withIdProjection = {
  status: 1,
  customerId: 1,
  createdAt: 1
  // Không đặt _id: 0.
};

lab.orders.find(
  coveredFilter,
  withIdProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Kết quả phải chứa `_id`. **Compound secondary index đang dùng không có `_id` như một khóa được truy vấn/project**, nên MongoDB cần đọc document gốc để trả về định danh; query không còn covered theo index đó.

**Không nhầm:** MongoDB mặc định có index riêng trên `_id`, nhưng điều đó **không có nghĩa** một truy vấn có thể ghép khóa từ index `_id` và một index compound khác để tự động trả kết quả hoàn toàn index-only. Định nghĩa covered query yêu cầu các trường cần thiết có thể xử lý bằng cùng index phù hợp.

### 5.2. Hai cách để xử lý

**Cách A — API không cần _id:** loại `_id` khỏi projection:

~~~javascript
{
  _id: 0,
  customerId: 1,
  createdAt: 1
}
~~~

**Cách B — API cần _id:** thêm `_id` vào compound index khi đây là truy vấn quan trọng và đánh đổi dung lượng là phù hợp:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    _id: 1
  },
  { name: "ix_tenant_status_customer_created_id" }
);
~~~

Truy vấn:

~~~javascript
lab.orders.find(
  coveredFilter,
  {
    _id: 1,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created_id")
 .explain("executionStats");
~~~

Với index mới, các trường lọc và các trường trả về đều nằm trong index. Lúc này `_id` có thể được trả từ khóa index và truy vấn có cơ hội được bao phủ.

**Không tự động thêm `_id` vào mọi compound index.** Mỗi khóa bổ sung làm index lớn hơn và tăng chi phí ghi/dùng bộ nhớ. Nếu chỉ vài truy vấn hiếm hoi cần `_id`, chi phí `FETCH` có thể chấp nhận được.

## 6. Khi projection yêu cầu một trường không có trong index

Một truy vấn có filter/sort được index hỗ trợ, nhưng API muốn hiển thị tổng tiền:

~~~javascript
lab.orders.find(
  coveredFilter,
  {
    _id: 0,
    customerId: 1,
    createdAt: 1,
    totalAmount: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

`totalAmount` không nằm trong index được hint, nên MongoDB không thể xây dựng đầy đủ kết quả chỉ từ index key. Kế hoạch sẽ cần đọc document:

~~~text
IXSCAN (lọc + thứ tự)
   |
   v
FETCH  (đọc totalAmount)
   |
   v
PROJECTION
~~~

Với tập dữ liệu minh họa, `totalDocsExamined` có thể là **3**, vì có ba document được trả và cần lấy trường ngoài index. Trong tình huống khác, MongoDB có thể đọc nhiều document hơn số trả về nếu còn filter phải đánh giá sau `FETCH`.

Một sự thật cần nhớ: **projection nhỏ hơn không tự động đồng nghĩa covered query**. Projection giúp giảm payload trả về, nhưng chỉ khi các trường trong projection trùng với khóa index phù hợp mới có cơ hội tránh đọc document.

### 6.1. Có nên thêm totalAmount vào index?

Có thể tạo index mở rộng:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "ix_tenant_status_customer_created_amount" }
);
~~~

Truy vấn trước đó giờ có thể được bao phủ bằng index mới, miễn không có trở ngại khác. Tuy nhiên:

- Index mới lớn hơn index ban đầu.
- Mọi ghi/sửa `totalAmount` có thể cần duy trì thêm khóa index.
- Index rộng tiêu tốn dung lượng đĩa và bộ nhớ cache.
- Nếu thêm nhiều trường chỉ để “tránh FETCH”, index có thể trở nên cồng kềnh.
- Nếu phần lớn truy vấn trả rất ít document và document nhỏ, chi phí FETCH có thể ít hơn lợi ích từ index rộng.

**Kết luận thiết kế:** lợi ích covered query phải được cân đối với chi phí ghi và lưu trữ, không phải một mục tiêu tuyệt đối.

## 7. Khi filter dùng trường không có trong index

Giả sử chỉ lấy đơn có `totalAmount > 140` nhưng vẫn dùng index ban đầu:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01",
    totalAmount: { $gt: 140 }
  },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Mặc dù **projection không có totalAmount**, MongoDB vẫn cần **đọc trường totalAmount** để xác định document có khớp bộ lọc hay không. Index đang dùng không lưu trường này nên không thể đánh giá hoàn toàn điều kiện.

Kết quả dự kiến gồm hai đơn với `_id` đuôi `05` và `02`, nhưng `_id` không được trả do projection. `Pseudocode`:

~~~text
IXSCAN:
  tìm các đơn T1 + PAID + C01
   |
   v
FETCH:
  đọc totalAmount của từng document ứng viên
   |
   v
FILTER:
  chỉ giữ totalAmount > 140
   |
   v
Trả customerId, createdAt
~~~

Nếu có ba ứng viên nhưng chỉ hai kết quả, có thể thấy `totalDocsExamined = 3` và `nReturned = 2`. Số liệu thực tế có thể khác theo phiên bản/plan nhưng mối quan hệ thể hiện rõ: số document **được kiểm tra** khác với số document **được trả**.

### 7.1. Phân biệt điều kiện truy vấn và điều kiện post-filter

Khi một điều kiện có mặt trong index, optimizer có thể thu hẹp khoảng `indexBounds` ngay trong `IXSCAN`. Khi điều kiện không được index phục vụ, MongoDB phải đánh giá lại trên giá trị lấy từ document sau `FETCH`.

Đôi khi index cung cấp một phần thông tin cần thiết, còn document vẫn phải được đọc để xác nhận phép so khớp. Vì vậy một plan có `IXSCAN` cùng `FETCH` không có nghĩa index bị bỏ phí: index vẫn có thể giảm mạnh số document cần kiểm tra.

## 8. Query và sort dùng index vẫn chưa chắc là covered

Một truy vấn có thể sắp xếp bằng index nhưng vẫn đọc document để trả dữ liệu:

~~~javascript
lab.orders.find(
  coveredFilter,
  { _id: 0, customerId: 1, totalAmount: 1 }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Index hỗ trợ cả ba equality filter và thứ tự `createdAt`; tuy nhiên muốn trả `totalAmount` phải dùng `FETCH`.

Ngược lại, nếu sort theo một trường **không nằm trong index** như `totalAmount`, dù projection chỉ trả các trường có trong index, MongoDB vẫn cần biết giá trị sort để xếp kết quả:

~~~javascript
lab.orders.find(
  coveredFilter,
  { _id: 0, status: 1, customerId: 1 }
).sort({ totalAmount: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Trường `totalAmount` không có trong index, nên việc sắp xếp theo trường đó không thể hoàn tất chỉ từ index key này. Kế hoạch có thể cần `FETCH` và `SORT`.

Hãy phân biệt ba câu hỏi độc lập:

1. **Index có giúp tìm document khớp filter không?**
2. **Index có giúp sắp xếp theo thứ tự yêu cầu không?**
3. **Index có đủ giá trị để trả kết quả mà không cần mở document không?**

Chỉ khi câu thứ ba được đáp ứng và mọi bước liên quan cũng index-only mới có covered query.

## 9. Điều kiện bằng null: trường hợp đặc biệt

MongoDB Manual quy định một covered query **không có điều kiện so sánh field bằng `null`**. Ví dụ:

~~~javascript
// Không đáp ứng điều kiện covered query theo tài liệu MongoDB:
lab.orders.find(
  { status: null },
  { _id: 0, status: 1 }
);

// Tương tự:
lab.orders.find(
  { status: { $eq: null } },
  { _id: 0, status: 1 }
);
~~~

Trong MongoDB, truy vấn `{ field: null }` có thể khớp document **có giá trị null** và document **không có field đó**. Sự khác biệt giữa missing và null là một lý do các kết quả chỉ dựa vào khóa index không luôn đủ để chứng minh điều kiện đúng.

Cần đặc biệt phân biệt:

| Document | `{ status: null }` | Diễn giải |
| --- | --- | --- |
| `{ status: null }` | Khớp | Có giá trị BSON null |
| `{ }` | Khớp | Không có field status |
| `{ status: "PAID" }` | Không khớp | Giá trị khác null |

**Không phải mọi điều kiện phủ định hoặc kiểm tra tồn tại đều giống nhau.** `$exists`, `$type`, `$ne` hay `$nin` có semantics khác nhau và khả năng sử dụng index cũng khác nhau. Đừng áp dụng máy móc rằng “nếu index có field thì mọi điều kiện về field đó đều được bao phủ”.

Nếu ứng dụng thường dùng `status` hoặc `createdAt` trong covered query, schema validation giúp đảm bảo field **luôn có mặt và đúng BSON type**. Tuy nhiên validation không biến điều kiện `{ field: null }` thành covered query.

## 10. Multikey index và mảng: có thể bao phủ có điều kiện

Khi một field được index chứa **mảng**, MongoDB tạo **multikey index**. Mỗi phần tử của mảng có thể tạo một index key tương ứng. Tuy nhiên **index không lưu đủ cấu trúc đầy đủ của mảng** để tái tạo trực tiếp giá trị mảng gốc trong projection.

### 10.1. Tạo multikey index

Bộ dữ liệu `lab.orders` có trường `tags`:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    tags: 1,
    status: 1
  },
  { name: "ix_tenant_tags_status" }
);
~~~

Vì `tags` là mảng ở các document, index này là **compound multikey index**.

### 10.2. Bao phủ truy vấn mà không trả mảng

Có thể lọc document có tag `"web"` nhưng **chỉ trả trường scalar `status`**:

~~~javascript
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

MongoDB có thể dùng compound multikey index để bao phủ một số truy vấn khi thỏa các điều kiện:

- **Không trả chính trường mảng `tags`** trong projection.
- **Không dùng `$elemMatch`** trong truy vấn.
- Tất cả các yêu cầu covered query còn lại được đáp ứng.

Trong ví dụ này, `tenantId` và `tags` là điều kiện lọc, còn `status` là trường được trả, đều có trong cùng index. Điều kiện `tags: "web"` khớp các document có phần tử `"web"`; không cần dựng lại toàn bộ mảng `tags` để trả kết quả.

### 10.3. Trả mảng thì phải đọc document

~~~javascript
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1, tags: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

Bây giờ client muốn nhận **mảng `tags` gốc**; multikey index không thể trả đầy đủ mảng đó từ index keys. Truy vấn cần đọc document.

Ví dụ document có:

~~~javascript
tags: ["web", "priority"]
~~~

Index có thể có khóa cho từng phần tử, nhưng **không thay thế document chứa mảng nguyên gốc**. Thứ tự phần tử, giá trị lặp và hình dạng mảng là những thông tin mà việc chỉ dựa vào các khóa multikey không bảo toàn theo cách cần thiết cho projection.

### 10.4. $elemMatch làm mất khả năng covered query

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    tags: { $elemMatch: { $eq: "web" } }
  },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status")
 .explain("executionStats");
~~~

Query `$elemMatch` có ý nghĩa về **một phần tử mảng**, và tài liệu MongoDB nêu đây là trường hợp **không được multikey index bao phủ**. Index vẫn có thể được dùng để tìm ứng viên, nhưng cần đọc document để xác nhận kết quả.

**Đừng nhầm:** multikey index **có thể giúp truy vấn mảng nhanh hơn** mà vẫn không đủ điều kiện covered query. Tối ưu filter và bao phủ toàn bộ kết quả là hai khía cạnh riêng.

## 11. Trường lồng nhau và dotted path

Covered query không chỉ giới hạn ở các field top-level. MongoDB có thể dùng index của một **trường lồng nhau** nếu filter/projection dùng đúng đường dẫn và các điều kiện khác được đáp ứng.

Giả sử collection `profiles` chứa:

~~~javascript
{
  _id: 1,
  userId: "U01",
  contact: {
    city: "Hanoi",
    country: "VN",
    phone: "0900000000"
  }
}
~~~

Tạo index:

~~~javascript
lab.profiles.drop();

lab.profiles.insertMany([
  {
    _id: 1,
    userId: "U01",
    contact: { city: "Hanoi", country: "VN", phone: "0900000000" }
  },
  {
    _id: 2,
    userId: "U02",
    contact: { city: "Danang", country: "VN", phone: "0911111111" }
  }
]);

lab.profiles.createIndex(
  { "contact.city": 1, userId: 1 },
  { name: "ix_city_user" }
);
~~~

Truy vấn chỉ trả đúng dotted field đã index:

~~~javascript
lab.profiles.find(
  { "contact.city": "Hanoi" },
  {
    _id: 0,
    "contact.city": 1,
    userId: 1
  }
).hint("ix_city_user")
 .explain("executionStats");
~~~

Đây là một ứng viên covered query vì các đường dẫn dùng để lọc và trả kết quả đều thuộc index. Ngược lại, yêu cầu trả **toàn bộ object `contact`** hoặc `contact.phone` sẽ cần document nguồn, vì index chỉ lưu `contact.city` và `userId`.

Khi làm việc với nested arrays hoặc các field chứa object có giá trị khác loại, cần chú ý thêm những giới hạn của multikey index và ngữ nghĩa của dotted path. Không coi index trên một field con là bản sao đầy đủ của object cha.

## 12. Collation, partial index và sparse index

### 12.1. Collation trên chuỗi

**Collation** xác định quy tắc so sánh chuỗi (chữ hoa/thường, dấu, locale). Index có collation có thể lưu **khóa sắp xếp được mã hóa theo quy tắc collation**, khác với biểu diễn chuỗi gốc.

Ví dụ:

~~~javascript
lab.profiles.createIndex(
  { userId: 1 },
  {
    name: "ix_user_collated",
    collation: { locale: "en", strength: 2 }
  }
);
~~~

Một query muốn sử dụng index này cho **string comparison** cần có collation tương thích:

~~~javascript
lab.profiles.find(
  { userId: "u01" },
  { _id: 0, userId: 1 }
).collation({ locale: "en", strength: 2 })
 .hint("ix_user_collated")
 .explain("executionStats");
~~~

Với collation không phải `simple`, các giá trị chuỗi trong index có thể không bảo toàn nguyên dạng phù hợp cho mọi phép projection. Vì vậy **một query dùng index theo collation không mặc nhiên là covered query**, đặc biệt khi cần trả chuỗi gốc. Hãy đọc `explain` và chọn index/collation theo yêu cầu ứng dụng thay vì giả định.

### 12.2. Partial index không chứa mọi document

Partial index chỉ lưu khóa từ document thỏa `partialFilterExpression`.

Ví dụ:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, customerId: 1, createdAt: -1 },
  {
    name: "ix_paid_orders_partial",
    partialFilterExpression: { status: "PAID" }
  }
);
~~~

Index này chỉ chứa các đơn PAID. Truy vấn có điều kiện `status: "PAID"` có thể được hỗ trợ vì filter của truy vấn cho phép MongoDB biết tập kết quả nằm trong phần đã index:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01"
  },
  {
    _id: 0,
    tenantId: 1,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_paid_orders_partial")
 .explain("executionStats");
~~~

Điểm đáng chú ý: trường `status` xuất hiện trong **điều kiện partial index**, nhưng không nằm trong **key pattern**. Nếu projection cần trả `status` hoặc query phức tạp hơn, phải kiểm tra xem planner có thể suy ra đầy đủ kết quả từ index metadata hay cần FETCH; đừng giả định một field dùng trong `partialFilterExpression` cũng được lưu như khóa index.

Một truy vấn **không giới hạn vào các đơn PAID** không được phép dựa hoàn toàn vào partial index này để trả kết quả đầy đủ, bởi index không chứa các document PENDING/ARCHIVED.

### 12.3. Sparse index và điều kiện tồn tại

Sparse index không chứa toàn bộ document theo cùng quy tắc như index thông thường. Các truy vấn có thể khớp document không được index sẽ **không tự động được bao phủ** chỉ vì field xuất hiện trong sparse index.

Ví dụ một truy vấn tìm document **thiếu** một field vốn được sparse-indexed không thể lấy mọi kết quả đúng chỉ bằng những khóa mà index đã bỏ qua. Với partial/sparse index, luôn kiểm tra **tính đầy đủ của tập kết quả**, không chỉ số lượng trường có trong key pattern.

## 13. Covered query trên sharded collection

Trong triển khai **sharded cluster**, MongoDB có thể cần thêm trường nội bộ cho việc định tuyến hoặc kiểm tra tài liệu. MongoDB Manual lưu ý: khi thực thi qua `mongos`, một index chỉ có thể bao phủ truy vấn trên sharded collection nếu index **chứa shard key**.

Điều đó có nghĩa:

- Index đủ field filter và projection ở một collection chưa sharded **không nhất thiết** đủ điều kiện khi triển khai sharding.
- Một query đi qua `mongos` còn phải xét shard key theo cấu hình cluster.
- Một index phù hợp với shard key, filter, sort và projection có thể tăng cơ hội coverage, nhưng không bảo đảm mọi query đều covered.
- Trước khi đổi thiết kế index trên cluster thật, cần xem query routing, scatter-gather và các giới hạn unique index/shard key tương ứng.

Nên kiểm tra explain trên **đường truy cập thực tế** của ứng dụng, không chỉ trên một mongod đơn lẻ dùng làm môi trường phát triển.

## 14. Đọc explain: phân biệt IXSCAN, FETCH và các chỉ số

### 14.1. Lệnh explain cơ bản

~~~javascript
lab.orders.find(
  coveredFilter,
  coveredProjection
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

`executionStats` báo số liệu thực thi của plan được chọn. Những trường quan trọng:

| Tên/khái niệm | Ý nghĩa |
| --- | --- |
| `winningPlan` | Kế hoạch được optimizer chọn |
| `IXSCAN` | Duyệt các entry từ index |
| `COLLSCAN` | Duyệt document collection |
| `FETCH` | Lấy document từ collection dựa trên record locator |
| `PROJECTION_COVERED` | Stage projection xử lý từ index (có thể thấy trong một số plan) |
| `SORT` | Stage sắp xếp; có thể tốn bộ nhớ/I/O nếu index không đáp ứng |
| `nReturned` | Số kết quả được trả ở tầng được thống kê |
| `totalKeysExamined` | Số index entries được xét |
| `totalDocsExamined` | Số lượt document nguồn được xét |
| `indexBounds` | Khoảng giá trị khóa index được truy cập |

**`totalDocsExamined` không phải số document duy nhất**, và cũng không phải luôn bằng `nReturned`. Nếu một document bị xét nhiều lần trong một plan, số lượt kiểm tra được tính tương ứng.

### 14.2. Cách kết luận một covered query

Phương pháp thực hành:

1. Xem `winningPlan` có dùng index phù hợp không.
2. Xem toàn bộ phần plan, tìm `IXSCAN` và kiểm tra có `FETCH` trên đường thực thi không.
3. Xem `executionStats.totalDocsExamined` có bằng **0** không.
4. Xác nhận filter và projection thực sự nhận giá trị từ index, không phải do query trả rỗng/được tối ưu bằng cơ chế khác.
5. So sánh với một query cần field ngoài index để quan sát sự khác nhau.

Một đoạn code đọc các chỉ số:

~~~javascript
function summarizeExplain(cursor) {
  const e = cursor.explain("executionStats");

  printjson({
    nReturned: e.executionStats.nReturned,
    totalKeysExamined: e.executionStats.totalKeysExamined,
    totalDocsExamined: e.executionStats.totalDocsExamined
  });

  printjson(e.queryPlanner.winningPlan);
}

summarizeExplain(
  lab.orders.find(
    coveredFilter,
    coveredProjection
  ).sort({ createdAt: -1 })
   .hint("ix_tenant_status_customer_created")
);
~~~

Trong nhiều phiên bản, `explain` có nhiều tầng plan hoặc cấu trúc khác với ví dụ trên. **Không chỉ nhìn `totalDocsExamined = 0` rồi kết luận mọi query đều được index bao phủ**; một truy vấn không tìm thấy bản ghi hoặc được giải quyết bằng tối ưu đặc biệt cũng có thể đọc 0 document. Với query có kết quả, hãy xác nhận index-only path theo plan.

### 14.3. Diễn giải ba tình huống

**Tình huống A — Covered:**

~~~text
nReturned = 3
totalKeysExamined >= 3
totalDocsExamined = 0
IXSCAN, không FETCH
~~~

**Tình huống B — Index + FETCH:**

~~~text
nReturned = 3
totalKeysExamined >= 3
totalDocsExamined = 3 (ví dụ minh họa)
IXSCAN và FETCH
~~~

**Tình huống C — Filter sau FETCH:**

~~~text
nReturned = 2
totalKeysExamined >= 3
totalDocsExamined = 3 (ví dụ minh họa)
IXSCAN, FETCH, có lọc điều kiện ngoài index
~~~

Các số ở B/C minh họa theo dữ liệu lab và index được hint; số thực tế tùy kế hoạch và cách engine đếm lượt xét document.

### 14.4. Khi nào hint có ích?

`hint()` có ích khi **so sánh hai index cụ thể** trong lab hoặc khi đã xác định planner chọn một index gây vấn đề trong workload sản xuất. Nhưng dùng hint không biến một query thiếu trường thành covered query. Nếu index thiếu `totalAmount` thì hint vào index đó vẫn không cung cấp `totalAmount`.

Trong production, index thay đổi theo thời gian; một hint cố định có thể trở thành không còn phù hợp hoặc gây lỗi khi index bị xóa. Nên cân nhắc hint như công cụ nghiên cứu hoặc biện pháp vận hành có kiểm soát.

## 15. Có nhất thiết phải cố gắng tạo covered query?

Không. Một covered query thường giảm số document reads, nhưng **index rộng hơn** có chi phí riêng.

### 15.1. Lợi ích

- Giảm số lần đọc document gốc khỏi collection.
- Giảm I/O khi document lớn hoặc nằm ngoài cache.
- Có thể xử lý nhiều kết quả bằng index entry nhỏ gọn.
- Giảm công việc projection nếu các trường trả về đã có từ index.

### 15.2. Chi phí

- **Dung lượng index tăng** khi thêm nhiều khóa.
- **Ghi chậm hơn** do index cần được cập nhật khi có insert/update/delete liên quan.
- **RAM/cache pressure** lớn hơn khi nhiều index cạnh tranh bộ nhớ.
- **Độ phức tạp vận hành** tăng: trùng lặp index, thứ tự field, collation, partial filter và phiên bản ứng dụng.
- **Lợi ích có thể nhỏ** nếu query chỉ trả vài document và document nguồn đã ở trong cache.

Bảng gợi ý:

| Workload | Khuyến nghị |
| --- | --- |
| Trang danh sách đọc liên tục, chỉ cần vài field nhỏ | Cân nhắc index có thể cover filter/sort/projection |
| Truy vấn hiếm, trả 1–2 document nhỏ | Có thể chấp nhận FETCH |
| Document rất lớn, chỉ cần vài trường scalar | Covered query có thể mang lại lợi ích rõ rệt |
| API luôn trả mảng lớn hoặc object phức tạp | Khó đạt coverage; tối ưu lọc, projection và thiết kế document |
| Collection ghi nhiều, index đã rất lớn | Tránh thêm trường vào index chỉ vì một màn hình hiếm |
| Truy vấn trên field null, mảng dùng `$elemMatch`, collation đặc biệt | Đọc explain và chấp nhận giới hạn index-only |
| Thêm index nhưng dữ liệu vẫn chậm | Đọc `explain`, profiler, phân bố dữ liệu và cache trước khi kết luận |

Điểm cân bằng là **tối ưu workload tổng thể**, không cố đạt `totalDocsExamined: 0` cho mọi truy vấn.

## 16. So sánh với những khái niệm gần kề

### 16.1. Covered query không phải index-only sort

Một truy vấn có thể dùng index để sort rồi vẫn FETCH vì cần trường ngoài index. Khi xem plan, “không có SORT stage” không đủ để chứng minh covered query.

### 16.2. Covered query không phải projection nhỏ

Projection nhỏ làm response nhẹ hơn nhưng vẫn có thể buộc FETCH nếu trường được trả không nằm trong index.

### 16.3. Covered query không phải một index chứa tất cả trường trong collection

Mục tiêu không phải tạo index sao chép cả document. Chỉ các trường **thực sự cần cho truy vấn quan trọng** mới đáng cân nhắc thêm vào index.

### 16.4. Covered query không phải luôn nhanh nhất

Đôi khi planner chọn plan có FETCH nhưng ít index key hơn, hoặc một index nhỏ hơn có locality/cache tốt hơn. Covered query là một lợi thế tiềm năng, không phải phép đo tốc độ duy nhất.

### 16.5. Covered query không giống materialized view

Covered query đọc trực tiếp **khóa index của document nguồn**. Materialized view lưu **kết quả tổng hợp** trong một collection riêng cần đồng bộ. Hai cơ chế giải quyết những vấn đề khác nhau.

## 17. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân điển hình | Hướng xử lý |
| --- | --- | --- |
| Có `IXSCAN` nhưng vẫn `FETCH` | Filter/projection/sort cần field không có trong index | So sánh từng field với index key pattern |
| Đã project chỉ vài field nhưng vẫn đọc document | Một field trong projection không được index | Bỏ field nếu không cần hoặc cân nhắc mở rộng index |
| Query đã đủ field nhưng vẫn không cover | `_id` trả về mặc định | Đặt `_id: 0` hoặc thêm `_id` vào index |
| Hai index riêng lẻ chứa đủ field nhưng query không cover | Không thể giả định ghép hai index thành một nguồn đủ field trả về | Thiết kế một compound index phù hợp |
| `totalDocsExamined` không bằng `nReturned` | Có document ứng viên bị lọc hoặc đọc nhiều lần | Xem filter và stage FETCH |
| `totalDocsExamined = 0` nhưng không có kết quả | Truy vấn không tìm thấy document | Kiểm tra plan và thử với tập có kết quả |
| Query `{field: null}` không cover | Điều kiện equality với null là giới hạn của covered query | Xem lại semantics null/missing và chấp nhận FETCH |
| Multikey index dùng được nhưng trả mảng phải FETCH | Index không tái tạo được toàn bộ mảng | Không project mảng hoặc chấp nhận FETCH |
| Query mảng dùng `$elemMatch` mất coverage | Multikey covered query không hỗ trợ `$elemMatch` | Tối ưu query/index, không ép coverage |
| Sort nhanh nhưng vẫn phải đọc document | Index hỗ trợ thứ tự, projection cần field khác | Phân biệt sort coverage với query coverage |
| Chỉ số index đủ nhưng query có collation khác | Index string comparison yêu cầu collation tương thích | Đồng bộ collation của query và index |
| Partial index làm bỏ sót dữ liệu nếu ép dùng | Filter không chứng minh tập kết quả nằm trong phần index | Thiết kế lại index/filter, tránh hint không hợp lệ |
| Covered query trong dev nhưng không giống sharded production | Cần shard key và query routing khác | Explain qua mongos với cấu hình thật |
| Thêm rất nhiều field vào compound index, ghi chậm | Index quá rộng và tốn maintenance | Ưu tiên workload đọc quan trọng, đo chi phí tổng thể |

## 18. Bài tập thực hành

Dùng đúng bộ dữ liệu `lab.orders` và các index đã tạo ở mục 3–4. Không cần chỉnh sửa document để hoàn thành các bài này.

### Bài 1 — Covered query cơ bản

Với index:

~~~javascript
{
  tenantId: 1,
  status: 1,
  customerId: 1,
  createdAt: -1
}
~~~

Viết query lấy đơn PAID của khách C01 thuộc tenant T1, chỉ trả `customerId` và `createdAt`. Không trả `_id`.

Gợi ý:

~~~javascript
lab.orders.find(
  {
    tenantId: "T1",
    status: "PAID",
    customerId: "C01"
  },
  {
    _id: 0,
    customerId: 1,
    createdAt: 1
  }
).sort({ createdAt: -1 })
 .hint("ix_tenant_status_customer_created")
 .explain("executionStats");
~~~

Quan sát `totalDocsExamined` và xác định liệu plan có `FETCH` hay không.

### Bài 2 — Trường _id mặc định

Bỏ `_id: 0` khỏi projection bài 1, giữ nguyên index. Giải thích vì sao planner phải xem xét document nguồn để trả `_id`.

Sau đó tạo index có `_id` ở cuối và dùng `hint()` để so sánh. Phân tích lợi ích/chi phí khi thêm khóa định danh vào index.

### Bài 3 — Projection cần trường ngoài index

Thêm `totalAmount: 1` vào projection bài 1 rồi xem `explain`.

Câu hỏi: dữ liệu nằm trong index hay document nguồn? So sánh `nReturned` và `totalDocsExamined`. Nếu màn hình này được đọc hàng nghìn lần mỗi giây, bạn có cân nhắc thêm `totalAmount` vào compound index không? Vì sao?

### Bài 4 — Filter ngoài index

Bổ sung điều kiện:

~~~javascript
totalAmount: { $gt: 140 }
~~~

vào filter và **không trả totalAmount**. Giải thích vì sao query vẫn có thể cần đọc document để kiểm tra điều kiện.

### Bài 5 — Multikey index

Tạo index:

~~~javascript
lab.orders.createIndex(
  { tenantId: 1, tags: 1, status: 1 },
  { name: "ix_tenant_tags_status" }
);
~~~

Chạy ba query:

~~~javascript
// A: chỉ trả scalar field status.
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status");

// B: trả thêm mảng tags.
lab.orders.find(
  { tenantId: "T1", tags: "web" },
  { _id: 0, status: 1, tags: 1 }
).hint("ix_tenant_tags_status");

// C: dùng query $elemMatch trên tags.
lab.orders.find(
  { tenantId: "T1", tags: { $elemMatch: { $eq: "web" } } },
  { _id: 0, status: 1 }
).hint("ix_tenant_tags_status");
~~~

Thêm `.explain("executionStats")` cho từng query và xác định trường hợp nào có thể được index bao phủ.

### Bài 6 — Trường lồng nhau

Trên collection `lab.profiles`, tạo index `{"contact.city": 1, userId: 1}`. Thử:

- Trả chỉ `"contact.city"` và `userId`.
- Trả toàn bộ object `contact`.
- Trả `"contact.phone"`.

Giải thích tại sao hai projection sau phải lấy document.

### Bài 7 — So sánh hai index

Tạo index rộng hơn:

~~~javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    customerId: 1,
    createdAt: -1,
    totalAmount: 1
  },
  { name: "ix_tenant_status_customer_created_amount" }
);
~~~

Cùng một query trả `totalAmount`, dùng `hint()` lần lượt với index cũ và mới. So sánh kế hoạch, số key/docs examined và lưu ý đây mới là **lab nhỏ**, chưa đủ để kết luận hiệu năng production.

### Bài 8 — Tự đánh giá thiết kế

Một collection có 10 triệu đơn hàng, mỗi document có mảng `items` dài và trường `internalNote` lớn. Trang danh sách chỉ cần `createdAt`, `status`, `customerId`, `totalAmount`. API lọc theo `tenantId` và `status`, sort theo `createdAt` giảm dần.

Hãy đề xuất một compound index có thể hỗ trợ filter/sort/projection (và `_id` nếu API trả về), rồi phân tích:

1. Có cần đưa `items` hoặc `internalNote` vào index không?
2. Covered query giúp giảm công việc đọc document như thế nào?
3. Khi nào index trở nên quá rộng?
4. Nếu trang chi tiết cần toàn bộ `items`, có nên cố bao phủ trang chi tiết bằng cùng index không?
5. Dùng `explain` và metric nào để xác nhận cải thiện?

## 19. Kết luận

Một **covered query** trong MongoDB được thực thi hoàn toàn từ index mà không cần đọc document gốc. Để đạt được điều đó, **filter, projection và các giá trị cần thiết cho thực thi** phải được đáp ứng bằng index phù hợp; không có điều kiện equality với null; đồng thời phải tôn trọng giới hạn của loại index và môi trường triển khai.

Khi thấy `IXSCAN` trong explain, hãy hỏi tiếp: **MongoDB có còn dùng `FETCH` không?** Nếu có, index vẫn có thể hữu ích cho filter/sort nhưng query **chưa được bao phủ**. Các chỉ số như `totalDocsExamined`, `totalKeysExamined` và `nReturned` giúp xác nhận lượng công việc thực tế.

Trong thiết kế hệ thống, nên tạo compound index theo **workload thường xuyên**: ưu tiên lọc và sắp xếp hiệu quả, sau đó cân nhắc thêm vài trường projection để tránh FETCH nếu lợi ích đọc vượt chi phí index rộng và duy trì ghi.

### Tài liệu tham khảo chính thức

- [Query Optimization — Covered Queries](https://www.mongodb.com/docs/manual/core/query-optimization/) — định nghĩa, các điều kiện coverage, `_id`, null, embedded documents và sharding.
- [Multikey Indexes — Covered Queries](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — điều kiện multikey index có thể bao phủ query.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — `IXSCAN`, `FETCH`, `COLLSCAN` và các chỉ số thực thi.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — thiết kế index gồm nhiều trường.
- [Use Indexes to Sort Query Results](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/) — index và sort.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — tính đầy đủ của kết quả khi dùng index một phần.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — quy tắc so sánh chuỗi và collation của index/query.
- [Project Fields to Return from Query](https://www.mongodb.com/docs/manual/tutorial/project-fields-from-query-results/) — cú pháp projection và hành vi mặc định của `_id`.
