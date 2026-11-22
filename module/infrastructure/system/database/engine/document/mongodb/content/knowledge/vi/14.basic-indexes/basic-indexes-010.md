# Hidden index và thử nghiệm tác động trước khi loại bỏ index trong MongoDB

Index giúp MongoDB tìm document, lọc, sắp xếp và thực thi nhiều truy vấn hiệu quả hơn, nhưng mỗi index cũng tiêu tốn dung lượng đĩa, bộ nhớ cache và chi phí bảo trì khi dữ liệu thay đổi. Khi một collection tích lũy quá nhiều index, nhóm phát triển có thể muốn loại bỏ những index ít được dùng để giảm chi phí vận hành.

Vấn đề là **xóa index là một thay đổi có rủi ro**: một truy vấn hiếm nhưng quan trọng có thể đang dựa vào index đó. Sau khi xóa, truy vấn có thể phải quét collection lớn, phát sinh sort tốn tài nguyên hoặc làm tăng độ trễ vào thời điểm cao điểm. Nếu cần phục hồi, việc tạo lại index trên dữ liệu lớn cũng tiêu tốn tài nguyên và không phải thao tác tức thời.

MongoDB cung cấp **hidden index (index bị ẩn)** để thử nghiệm một bước trung gian: **giữ nguyên index trong database, nhưng không cho query planner sử dụng nó khi lập kế hoạch truy vấn**. Nếu workload vẫn hoạt động tốt trong một khoảng quan sát đại diện, nhóm vận hành có thêm cơ sở để cân nhắc xóa index. Nếu hiệu năng giảm, có thể **bỏ trạng thái ẩn** mà không phải xây dựng lại index.

Bài học tập trung vào chức năng của hidden index, cách bật/tắt, quy trình khảo sát tác động trước khi drop, cách đọc số liệu, các ngoại lệ của unique/TTL index và giới hạn của phương pháp thử nghiệm này.

## 1. Hidden index là gì?

**Hidden index** là một index vẫn tồn tại, vẫn được cập nhật cùng dữ liệu và vẫn chiếm tài nguyên, nhưng **không được query planner xem là lựa chọn để phục vụ truy vấn**.

Hãy hình dung collection có ba index:

~~~text
Collection: shop.orders

Index:
  _id_                            [VISIBLE]
  idx_orders_customer_created     [VISIBLE]
  idx_orders_status_created       [VISIBLE]

Query planner:
  Có thể cân nhắc các index visible phù hợp với query.
~~~

Khi ẩn index thứ ba:

~~~text
Collection: shop.orders

Index:
  _id_                            [VISIBLE]
  idx_orders_customer_created     [VISIBLE]
  idx_orders_status_created       [HIDDEN]

Query planner:
  KHÔNG xem idx_orders_status_created là ứng viên.
  Vẫn có thể dùng các index visible hoặc collection scan.
~~~

Index bị ẩn **không bị xóa khỏi đĩa**. Các thao tác insert, update và delete vẫn duy trì dữ liệu index. Về mặt này, hidden index khác hoàn toàn một index đã bị drop.

### 1.1. Các thuộc tính quan trọng

| Thuộc tính | Index visible | Index hidden | Index đã drop |
| --- | --- | --- | --- |
| Còn tồn tại trong collection | Có | Có | Không |
| Query planner sử dụng cho truy vấn | Có thể | **Không** | Không |
| Có thể dùng làm index hint | Có thể | **Không** | Không |
| Được duy trì khi document thay đổi | Có | **Có** | Không |
| Tiêu tốn dung lượng index | Có | **Có** | Không còn index đó |
| Tác động đến chi phí ghi | Có | **Vẫn có** | Không còn chi phí của index đó |
| Unique constraint nếu là unique index | Được thực thi | **Vẫn được thực thi** | Mất ràng buộc của index đã drop |
| TTL nếu là TTL index | Vẫn hoạt động | **Vẫn hoạt động** | Không còn cơ chế TTL của index đã drop |
| Có thể phục hồi khả năng dùng cho query nhanh | Vốn đang visible | **Unhide, không cần rebuild** | Phải tạo lại index |

MongoDB hỗ trợ hidden index từ **MongoDB 4.4**. Trong những phiên bản hỗ trợ, trạng thái hidden được lưu trong metadata của index và tồn tại cho tới khi được thay đổi lại.

**Không thể ẩn index _id mặc định.** Đây là index đặc biệt gắn với định danh document. Với các index khác, vẫn cần kiểm tra yêu cầu vận hành và ràng buộc đặc biệt trước khi quyết định hide hoặc drop.

### 1.2. Vì sao hidden index phù hợp để thử tác động của việc drop?

Nếu bạn drop index ngay, tác động lên query planner có thể quan sát được nhưng đường phục hồi tốn kém: phải chạy lại quá trình xây dựng index.

Nếu **hide** index trước:

1. Query planner ngừng sử dụng index đó.
2. Bạn quan sát kế hoạch truy vấn và độ trễ thật.
3. Nếu thấy regression, gọi **unhideIndex()** để cho query planner cân nhắc index trở lại.
4. Nếu không có regression đáng kể sau khoảng quan sát phù hợp, có thể cân nhắc **dropIndex()** ở bước sau.

Về mặt **lựa chọn index cho truy vấn**, trạng thái hidden giúp mô phỏng việc index không còn được sử dụng. Nhưng đây **không phải mô phỏng hoàn chỉnh mọi hệ quả của drop**, vì index vẫn còn chi phí ghi, chi phí lưu trữ và các ràng buộc như unique/TTL.

## 2. Ví dụ collection đơn hàng và ba loại truy vấn

Ta dùng collection minh họa **shop.orders**:

~~~javascript
{
  _id: ObjectId("673111111111111111111111"),
  customerId: "CUS-001",
  status: "PAID",
  createdAt: ISODate("2026-10-15T08:30:00Z"),
  totalAmount: NumberDecimal("450000.00"),
  shipping: {
    city: "HCM"
  }
}
~~~

Giả sử các truy vấn nghiệp vụ gồm:

**Truy vấn A – lấy đơn của một khách, mới nhất trước:**

~~~javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

**Truy vấn B – lấy đơn PAID mới nhất:**

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

**Truy vấn C – tra cứu một đơn theo _id:**

~~~javascript
db.orders.findOne({
  _id: ObjectId("673111111111111111111111")
});
~~~

Các index được tạo theo nhu cầu:

~~~javascript
use shop

db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_orders_customer_created" }
);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_orders_status_created" }
);
~~~

Index **idx_orders_customer_created** hỗ trợ truy vấn A. Index **idx_orders_status_created** là ứng viên phù hợp cho truy vấn B. Truy vấn C có thể dùng index **_id_** mặc định.

Giả sử nhóm phát triển nghi ngờ **idx_orders_status_created** không còn cần thiết do luồng lọc status ít được sử dụng. **Mục tiêu thử nghiệm là index này**, không phải toàn bộ collection.

### 2.1. Danh sách index trước khi thử nghiệm

~~~javascript
db.orders.getIndexes();
~~~

Kết quả có thể chứa các phần tử như:

~~~javascript
[
  {
    v: 2,
    key: { _id: 1 },
    name: "_id_"
  },
  {
    v: 2,
    key: { customerId: 1, createdAt: -1 },
    name: "idx_orders_customer_created"
  },
  {
    v: 2,
    key: { status: 1, createdAt: -1 },
    name: "idx_orders_status_created"
  }
]
~~~

Đây là kết quả minh họa. Metadata thực tế có thể có thêm các field tùy phiên bản MongoDB và cấu hình index. Trước khi thay đổi, hãy lưu **định nghĩa đầy đủ** của index ứng viên, không chỉ tên.

## 3. Các thao tác hideIndex, unhideIndex và dropIndex

Trong **mongosh**, có thể thay trạng thái hidden bằng các method của collection.

### 3.1. Ẩn index theo tên

~~~javascript
db.orders.hideIndex("idx_orders_status_created");
~~~

Từ thời điểm thay đổi có hiệu lực, query planner không sử dụng index này để phục vụ các query mới được lập kế hoạch.

Xem metadata:

~~~javascript
db.orders.getIndexes().filter(
  index => index.name === "idx_orders_status_created"
);
~~~

Một kết quả minh họa:

~~~javascript
[
  {
    v: 2,
    key: { status: 1, createdAt: -1 },
    name: "idx_orders_status_created",
    hidden: true
  }
]
~~~

Field **hidden: true** là tín hiệu quan trọng. Với index visible, field hidden có thể không xuất hiện hoặc thể hiện trạng thái không ẩn tùy biểu diễn; đừng dựa vào thứ tự field để nhận diện index.

### 3.2. Ẩn index theo key specification

Ngoài tên, có thể xác định index bằng tài liệu key tương ứng:

~~~javascript
db.orders.hideIndex({
  status: 1,
  createdAt: -1
});
~~~

Trong vận hành, tên index thường dễ kiểm soát hơn khi cần ghi log, tạo runbook và tránh nhầm một index gần giống về key pattern.

### 3.3. Bỏ ẩn để phục hồi query planner

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

Index trở lại trạng thái visible; MongoDB có thể cân nhắc nó cho các truy vấn tương thích. **Không cần xây lại dữ liệu index**, vì index đã được duy trì trong suốt thời gian hidden.

Unhide không bảo đảm mọi truy vấn lập tức chọn index đó: query planner vẫn cân nhắc các lựa chọn visible, độ chọn lọc và nhiều yếu tố khác.

### 3.4. Drop index sau khi đã có cơ sở

~~~javascript
db.orders.dropIndex("idx_orders_status_created");
~~~

Khác với unhide, **dropIndex** loại bỏ cấu trúc index khỏi collection. Khi muốn khôi phục, phải tạo lại index:

~~~javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_orders_status_created" }
);
~~~

Trên collection lớn, xây dựng lại index có thể tốn thời gian và tài nguyên; không nên coi đây là rollback tức thì như **unhideIndex()**.

### 3.5. Có thể tạo một index ở trạng thái hidden ngay từ đầu

~~~javascript
db.orders.createIndex(
  { shippingCity: 1, createdAt: -1 },
  {
    name: "idx_orders_city_created_trial",
    hidden: true
  }
);
~~~

Trong trường hợp này, index được xây dựng và duy trì, nhưng **chưa được query planner sử dụng** cho tới khi unhide. Cách này phù hợp khi muốn chuẩn bị một index mới mà chưa thay đổi kế hoạch truy vấn ngay.

Tuy nhiên, thao tác **createIndex** vẫn cần đọc và xây dựng dữ liệu index, có chi phí tài nguyên thực tế. Trạng thái hidden không làm quá trình tạo index trở nên miễn phí.

## 4. Cách hiểu đúng về tác động của hidden index

Việc hide index ảnh hưởng tới **khả năng được chọn để đọc**, nhưng không có nghĩa index bị vô hiệu hóa hoàn toàn.

### 4.1. Query planner ngừng chọn hidden index

Giả sử trước khi hide, truy vấn B dùng index:

~~~javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(20);
~~~

Nếu không còn index phù hợp, MongoDB có thể:

- Chọn index visible khác nếu có lợi.
- Quét collection (**COLLSCAN**).
- Thực hiện sort không được index hỗ trợ.
- Kết hợp các bước thực thi khác theo query planner.

Một truy vấn có thể trở nên chậm hơn, nhưng cũng có trường hợp gần như không đổi vì query planner vốn không dùng index ứng viên.

### 4.2. Hint không thể buộc dùng hidden index

~~~javascript
db.orders.find({ status: "PAID" })
  .hint("idx_orders_status_created");
~~~

Nếu index đang hidden, yêu cầu hint tới nó **không thể dùng index đó để thực thi truy vấn** và thông thường dẫn đến lỗi liên quan index hint. Hidden có nghĩa index không sẵn có cho query planner, kể cả khi ứng dụng cố yêu cầu trực tiếp.

Đây là lý do cần khảo sát code và cấu hình có **hint cố định** trước khi hide: ứng dụng có thể lỗi thay vì chỉ chậm hơn.

### 4.3. Write vẫn phải duy trì index

Khi index ẩn, thao tác sau vẫn có nghĩa vụ cập nhật các entry index tương ứng:

~~~javascript
db.orders.insertOne({
  customerId: "CUS-999",
  status: "PENDING",
  createdAt: new Date(),
  totalAmount: 100000
});
~~~

Với update thay field nằm trong index:

~~~javascript
db.orders.updateOne(
  { _id: someOrderId },
  { $set: { status: "PAID" } }
);
~~~

Index **idx_orders_status_created** vẫn được cập nhật dù query planner không được dùng nó. Vì vậy, benchmark tốc độ **insert/update/delete trong trạng thái hidden** chưa phản ánh lợi ích giảm write amplification mà việc **drop index** có thể đem lại.

### 4.4. Dung lượng không tự giảm khi hide

~~~javascript
const info = db.orders.stats();

printjson(info.indexSizes);
print(info.totalIndexSize);
~~~

Index ẩn vẫn xuất hiện trong thống kê và chiếm tài nguyên lưu trữ. Muốn tiết kiệm dung lượng của index đó, cần loại bỏ thực sự bằng drop, sau khi đã kiểm tra ràng buộc và mức rủi ro.

## 5. Quy trình an toàn: khảo sát, ẩn thử, quan sát, quyết định

Một quy trình thực tế nên có các giai đoạn:

~~~text
            Kiểm kê index và workload
                        |
                        v
             Chọn đúng index ứng viên
                        |
                        v
             Lưu định nghĩa + số liệu gốc
                        |
                        v
             Thử trên môi trường đại diện
                        |
                        v
              Hide index có kiểm soát
                        |
                        v
             Quan sát truy vấn và hệ thống
                        |
              +---------+----------+
              |                    |
        Có regression          Không thấy regression
              |                    |
              v                    v
         Unhide ngay        Đánh giá đủ thời gian
              |                    |
              v                    v
         Điều tra và          Quyết định giữ ẩn,
         giữ index            unhide hoặc drop
~~~

Không phải cứ một phép **explain** sau khi hide không báo lỗi là có thể xóa index. Chúng ta cần quan sát **toàn bộ nhóm truy vấn quan trọng** trong một khoảng thời gian có ý nghĩa.

### 5.1. Xác định mục tiêu của thử nghiệm

Ví dụ:

> Xác định việc không sử dụng index idx_orders_status_created có làm tăng đáng kể độ trễ của các truy vấn liệt kê đơn hàng và báo cáo cuối ngày hay không.

Nên đặt ngưỡng chấp nhận trước khi thay đổi, ví dụ:

- p95 latency của API liên quan không tăng vượt ngưỡng ngân sách đã phê duyệt.
- Không xuất hiện lỗi hint index trong ứng dụng.
- Không có đợt tăng nghiêm trọng ở totalDocsExamined/totalKeysExamined cho truy vấn quan trọng.
- CPU, I/O và áp lực bộ nhớ trên database không vượt mức vận hành cho phép.
- Các job cuối ngày, cuối tháng hoặc chạy theo lịch đã được xét đến.

Các ngưỡng phải dựa trên SLO và workload thực tế; **không có một con số phần trăm an toàn chung** cho mọi hệ thống.

### 5.2. Kiểm kê phụ thuộc nghiệp vụ

Một index có thể đang hỗ trợ:

- API có tần suất thấp nhưng độ ưu tiên rất cao.
- Báo cáo kế toán chạy mỗi ngày hoặc mỗi tháng.
- Truy vấn filter và sort kết hợp.
- Truy vấn thuộc batch job hoặc migration.
- Truy vấn có **hint()** cố định trong code.
- Truy vấn aggregation dùng **$match**, **$sort** hoặc join phù hợp.
- Tác vụ đọc ở môi trường admin hoặc hệ thống tích hợp.

Đừng chỉ nhìn một màn hình ứng dụng rồi kết luận index không cần thiết. Cần hiểu **độ phủ workload**.

## 6. Bước một: lưu định nghĩa và trạng thái hiện tại

Trước khi hide, lưu thông tin của index ứng viên:

~~~javascript
const targetName = "idx_orders_status_created";

const target = db.orders.getIndexes()
  .find(index => index.name === targetName);

printjson(target);
~~~

Cần ghi nhận:

- **name** và **key pattern**.
- **unique**, **partialFilterExpression**, **sparse**, **collation** nếu có.
- **expireAfterSeconds** nếu là TTL index.
- **hidden** nếu đã có.
- Cấu hình khác như wildcard, text, geospatial, đặc tính phiên bản.
- Collection, database và môi trường đang thao tác.

Ví dụ một index khác có thể có định nghĩa:

~~~javascript
{
  key: { email: 1 },
  name: "uq_accounts_email",
  unique: true,
  partialFilterExpression: {
    email: { $type: "string" }
  }
}
~~~

Nếu drop rồi cần tạo lại, **không thể chỉ nhớ key pattern** mà bỏ qua unique và partial filter. Một index được tạo lại sai định nghĩa có thể làm thay đổi quy tắc nghiệp vụ.

### 6.1. Xác định index có phải _id mặc định không

~~~javascript
db.orders.getIndexes()
  .filter(index => index.name === "_id_");
~~~

MongoDB không cho hide index **_id** mặc định. Với nhiệm vụ tối ưu index cơ bản, hãy chọn các index phụ có mục đích rõ ràng và có thể phân tích.

### 6.2. Phân biệt index trùng và index gần trùng

Giả sử có:

~~~javascript
{ status: 1 }
{ status: 1, createdAt: -1 }
~~~

Index compound thứ hai có **prefix** là status. Trong nhiều tình huống nó có thể phục vụ truy vấn chỉ lọc theo status. Tuy nhiên, không có nghĩa index đầu tiên luôn thừa:

- Kích thước hai index khác nhau.
- Truy vấn sort hoặc projection có đặc điểm riêng.
- Index có thể khác collation, partial filter hoặc sparse.
- Độ chọn lọc, thống kê và query planner ảnh hưởng hiệu quả thực thi.
- Một index có thể bị hint trực tiếp.

Hidden index giúp kiểm nghiệm sự phụ thuộc của workload thay vì suy đoán từ việc hai index có phần key trùng nhau.

## 7. Bước hai: thu thập mức sử dụng index

MongoDB hỗ trợ aggregation stage **$indexStats** để quan sát thống kê sử dụng index.

~~~javascript
db.orders.aggregate([
  { $indexStats: {} }
]);
~~~

Kết quả có thể chứa các field như:

~~~javascript
{
  name: "idx_orders_status_created",
  key: {
    status: 1,
    createdAt: -1
  },
  host: "db-01.example.net:27017",
  accesses: {
    ops: NumberLong(12),
    since: ISODate("2026-11-01T00:00:00Z")
  }
}
~~~

Đây là ví dụ minh họa. **accesses.ops** biểu thị số lần index được ghi nhận là sử dụng kể từ mốc **accesses.since** trong phạm vi thống kê tương ứng. Nó không trực tiếp cho biết thời gian tiết kiệm được nhờ index, cũng không bảo đảm một index ít ops là không quan trọng.

Lọc thống kê cho index ứng viên:

~~~javascript
db.orders.aggregate([
  { $indexStats: {} },
  {
    $match: {
      name: "idx_orders_status_created"
    }
  },
  {
    $project: {
      _id: 0,
      name: 1,
      key: 1,
      host: 1,
      accesses: 1
    }
  }
]);
~~~

### 7.1. Vì sao accesses.ops = 0 chưa đủ để drop?

Một số khả năng:

- Truy vấn cần index chỉ chạy vào cuối tháng, còn thời gian quan sát mới vài ngày.
- Query đang chạy trên một replica set member khác.
- Ứng dụng có workload mùa vụ hoặc batch hiếm.
- Số đếm sử dụng có mốc **since** mới do restart hoặc sự kiện thay đổi metadata.
- Index có vai trò ràng buộc, như **unique** hoặc **TTL**, không thể đánh giá chỉ bằng lượt phục vụ truy vấn.
- Một truy vấn quan trọng vốn bị lỗi hoặc chưa chạy trong cửa sổ thống kê hiện tại.

Vì vậy, số liệu index usage nên được kết hợp với **logs, profiler, telemetry ứng dụng, kế hoạch query và lịch chạy nghiệp vụ**.

### 7.2. Thống kê phải có thời gian và nguồn rõ ràng

Trong replica set hoặc sharded cluster, thống kê có thể gắn với từng node, từng shard hoặc thành viên tương ứng. Đừng đọc một kết quả ở một nơi rồi suy ra toàn cluster không dùng index.

Nên ghi lại ít nhất:

~~~text
indexName: idx_orders_status_created
environment: production
observationStart: ...
observationEnd: ...
member/shard: ...
accesses.ops at start: ...
accesses.ops at end: ...
queries known to depend on index: ...
~~~

Những thông tin này giúp tránh kết luận sai từ counter bị reset hoặc cửa sổ thống kê không đại diện.

## 8. Bước ba: lưu baseline kế hoạch truy vấn

Trước khi hide, chạy explain cho những query quan trọng nhất. Ví dụ:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

Phản hồi **explain** có thể cho thấy:

- **winningPlan**: kế hoạch được chọn.
- **IXSCAN**: quét index.
- **COLLSCAN**: quét collection.
- **SORT**: giai đoạn sắp xếp riêng nếu kế hoạch cần.
- **totalKeysExamined**: số key index được xét.
- **totalDocsExamined**: số document được xét.
- **nReturned**: số document trả về.
- **executionTimeMillis**: thời gian thực thi được ghi nhận trong lần explain.

Tên và vị trí các stage có thể khác nhau tùy phiên bản MongoDB và execution engine, như classic engine và SBE. Hãy đọc **ý nghĩa kế hoạch**, không chỉ dùng một phép tìm chuỗi cố định trong JSON.

### 8.1. Ví dụ baseline trước khi hide

Giả sử dữ liệu production có vài triệu document và query trên sử dụng index ứng viên.

| Chỉ số | Giá trị trước hide, minh họa |
| --- | ---: |
| nReturned | 20 |
| totalKeysExamined | 20 |
| totalDocsExamined | 20 |
| Có index scan ứng viên | Có |
| Có sort tốn tài nguyên riêng | Không |
| Thời gian explain | 7 ms |

**Các số này là ví dụ giả định để minh họa cách so sánh, không phải kết quả chạy trên môi trường thật.**

Một index compound phù hợp có thể hỗ trợ cả điều kiện **status = PAID** lẫn thứ tự **createdAt giảm dần**. Khi hide index, planner có thể mất đường truy cập này.

### 8.2. Lưu cùng giá trị tham số đại diện

Không nên chỉ benchmark một trạng thái rất hiếm hoặc chỉ một khách hàng có ít dữ liệu. Cần lấy dữ liệu đại diện cho:

- Giá trị filter phổ biến và hiếm.
- Các khoảng thời gian khác nhau.
- Limit nhỏ và các truy vấn đọc nhiều kết quả.
- Các tenant hoặc khu vực có lượng dữ liệu chênh lệch.
- Query có sort/aggregation.
- Khả năng sử dụng projection và covered query.

Một index có thể không cần thiết cho một filter chọn lọc kém, nhưng rất quan trọng cho một filter khác có độ chọn lọc cao.

### 8.3. Không coi explain là benchmark đầy đủ

**Explain** giúp nhìn kế hoạch và lượng tài nguyên logic được dùng, nhưng không đại diện hoàn toàn cho độ trễ trong ứng dụng:

- Cache ấm/lạnh khác nhau.
- Concurrency thực tế có thể cao hơn.
- Network và bước giải mã ở driver không được tính giống request API.
- Query planner có thể chọn plan khác theo giá trị filter hoặc thống kê.
- Môi trường chạy explain chưa chắc giống tải production.

Vì vậy, nên kết hợp **explain trước/sau** với **metric thực của workload**.

## 9. Bước bốn: thực hiện thử nghiệm hide

Sau khi có baseline và kế hoạch rollback, thực hiện:

~~~javascript
db.orders.hideIndex("idx_orders_status_created");
~~~

Sau đó xác nhận:

~~~javascript
const index = db.orders.getIndexes().find(
  i => i.name === "idx_orders_status_created"
);

printjson({
  name: index?.name,
  hidden: index?.hidden
});
~~~

Kết quả mong đợi là **hidden: true** với index đang được kiểm tra.

### 9.1. Chạy lại cùng query

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

Giả sử sau hide, planner không tìm được index tương đương:

| Chỉ số | Trước hide | Sau hide | Ý nghĩa |
| --- | ---: | ---: | --- |
| nReturned | 20 | 20 | Số kết quả như nhau |
| totalKeysExamined | 20 | 0 | Plan có thể đã chuyển sang COLLSCAN |
| totalDocsExamined | 20 | 2.000.000 | Chi phí đọc tăng mạnh |
| SORT riêng | Không | Có | Phải sắp xếp mà không có index hỗ trợ |
| Thời gian explain | 7 ms | 900 ms | Regression đáng chú ý |

**Bảng là kịch bản giả định**, không phải kết quả cố định hoặc một dự báo chắc chắn. Trong một môi trường có index khác đáp ứng được query, mức thay đổi có thể rất nhỏ hoặc khác hoàn toàn.

### 9.2. Phân biệt correctness và performance

Khi một index bị ẩn, kết quả logic của truy vấn bình thường **không nên thay đổi chỉ vì index đó không thể được chọn**, nhưng:

- Truy vấn có thể chậm hơn hoặc timeout.
- Một yêu cầu có **hint chỉ vào hidden index** có thể bị lỗi.
- Query không có sort xác định vẫn không được bảo đảm về thứ tự kết quả.
- Nếu các thành phần ứng dụng phụ thuộc thời gian phản hồi, tác động gián tiếp có thể nghiêm trọng.

Đó là lý do thử nghiệm không chỉ kiểm tra “trả về đúng số document” mà còn phải kiểm tra **độ trễ, tải, timeout và tình trạng API**.

### 9.3. Ẩn chỉ một index mỗi lần, nếu có thể

Nếu đồng thời hide ba index, khi có regression rất khó xác định nguyên nhân. Một quy trình thận trọng thường thay đổi **mỗi lần một ứng viên**, theo dõi đủ các truy vấn chịu ảnh hưởng, rồi mới chuyển sang ứng viên khác.

Tuy nhiên, có những trường hợp nhiều index có quan hệ chặt chẽ, chẳng hạn những index gần trùng nhau. Khi cần thử cả một tập thay đổi, phải có thiết kế thí nghiệm và khả năng rollback rõ ràng.

## 10. Khi nào cần unhide ngay?

Một số tín hiệu dừng thử nghiệm:

- Query vốn có p95 dưới ngưỡng SLO nay vượt xa ngân sách độ trễ.
- Xuất hiện nhiều **COLLSCAN** hoặc **SORT** tốn tài nguyên.
- Query đang dùng hint cố định bị lỗi.
- Một API quan trọng tăng timeout/error rate.
- CPU, disk I/O hoặc cache pressure tăng rõ rệt.
- Replication lag hoặc tải các thành viên liên quan tăng đáng kể.
- Job nghiệp vụ định kỳ không hoàn thành đúng hạn.

Phục hồi index:

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

Rồi xác nhận trạng thái:

~~~javascript
db.orders.getIndexes().filter(
  index => index.name === "idx_orders_status_created"
);
~~~

Sau khi unhide, tiếp tục theo dõi tới khi hiệu năng trở lại ổn định. Query planner có thể chọn index khác trong một số trường hợp; nếu vấn đề không hồi phục, cần điều tra thêm thay vì kết luận toàn bộ sự cố do trạng thái hidden.

**Rollback bằng unhide không khôi phục những timeout, retry hay tác động đã xảy ra trong lúc thử.** Vì vậy production trial vẫn cần cửa sổ triển khai và giám sát thích hợp.

## 11. Các loại index đặc biệt: phải phân tích ngoài hiệu năng đọc

Một index ít được query planner sử dụng vẫn có thể rất quan trọng vì **ràng buộc dữ liệu** hoặc tính năng hệ thống.

### 11.1. Unique index: ẩn không làm mất uniqueness

Ví dụ:

~~~javascript
db.accounts.createIndex(
  { email: 1 },
  {
    name: "uq_accounts_email",
    unique: true
  }
);
~~~

Ẩn index:

~~~javascript
db.accounts.hideIndex("uq_accounts_email");
~~~

**Unique constraint vẫn được thực thi.** Một insert tạo email trùng theo quy tắc của index vẫn có thể gặp duplicate key error:

~~~javascript
db.accounts.insertOne({
  email: "same@example.net"
});
~~~

Nếu xóa unique index, ràng buộc uniqueness do index đó cung cấp **không còn nữa**. Đây là khác biệt nghiệp vụ lớn mà hidden index **không mô phỏng**.

Trước khi drop unique index, phải hiểu liệu có **ràng buộc thay thế** bảo đảm tính duy nhất hay không. Không dùng phép thử “hide mà hệ thống không lỗi” để kết luận một unique index có thể xóa.

### 11.2. TTL index: ẩn vẫn duy trì cơ chế hết hạn

Ví dụ TTL index trên field BSON Date:

~~~javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "ttl_sessions_expiry",
    expireAfterSeconds: 0
  }
);
~~~

Nếu hide:

~~~javascript
db.sessions.hideIndex("ttl_sessions_expiry");
~~~

Index TTL vẫn được duy trì và **TTL monitor vẫn có thể xóa document hết hạn** theo cấu hình. Hidden ở đây không phải cách tạm dừng tự động xóa dữ liệu.

Nếu drop TTL index, collection không còn cơ chế hết hạn do index đó cung cấp. Những document vốn sẽ được xóa tự động có thể tiếp tục tồn tại, ảnh hưởng retention và dung lượng.

Nếu mục tiêu là thay đổi chính sách retention, phải xem xét cấu hình TTL và yêu cầu nghiệp vụ, không dùng hide như một công tắc dừng TTL.

### 11.3. Partial index và sparse index

Ví dụ partial index:

~~~javascript
db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  {
    name: "idx_paid_customer_created",
    partialFilterExpression: {
      status: "PAID"
    }
  }
);
~~~

Index chỉ chứa các entry phù hợp điều kiện partial filter. Nó có thể ít được dùng trong thống kê toàn collection nhưng có giá trị lớn cho nhóm query quan trọng.

Khi khảo sát, phải ghi lại **partialFilterExpression** và filter của các query tương ứng. Tương tự, sparse index không chứa mọi document theo cùng cách như index thông thường; không thể coi hai index có key pattern giống nhau là hoàn toàn tương đương nếu một index sparse còn index kia không.

### 11.4. Collation và index theo ngôn ngữ

Hai index cùng key pattern nhưng khác **collation** có thể phục vụ các điều kiện so sánh chuỗi khác nhau. Ví dụ query dùng collation không phân biệt hoa/thường có thể cần index có collation tương ứng để tối ưu.

Khi ẩn một index có collation đặc biệt, đừng chỉ kiểm tra query mặc định; hãy kiểm tra các query có khai báo collation mà ứng dụng dùng thật.

### 11.5. Các index phục vụ tính năng chuyên biệt

Text, geospatial, wildcard và những loại index chuyên biệt khác có tác động khác B-tree thường:

- Text query có thể cần text index thích hợp.
- Truy vấn geospatial dùng những index và quy tắc riêng.
- Wildcard index có thể phục vụ nhiều path động.
- Index liên quan shard key có thể có vai trò vận hành đặc biệt.

Với nhóm này, cần đọc đúng chức năng index và các ràng buộc trước khi hide hoặc drop, không chỉ chạy một phép tìm kiếm đơn giản.

## 12. Tại sao không thể dùng hidden index để đo hết lợi ích của việc drop?

Hidden index là một **thử nghiệm phụ thuộc query planner**, không phải một phép mô phỏng drop toàn diện.

### 12.1. Những điều hidden index có thể giúp kiểm tra

- Query nào mất đường truy cập bằng index?
- Query planner có lựa chọn visible thay thế không?
- Thời gian chạy query có tăng không?
- Có tăng collection scan hoặc sort không?
- Có code dùng hint tới index không?
- Workload đọc có chịu được khi thiếu index ứng viên không?

### 12.2. Những điều hidden index chưa mô phỏng

- **Giảm dung lượng lưu trữ** sau khi drop.
- **Giảm chi phí ghi** do không còn cập nhật entry index.
- **Giảm áp lực cache** do index đã bị loại bỏ thực sự.
- **Mất uniqueness** nếu drop unique index.
- **Mất TTL** nếu drop TTL index.
- **Chi phí và thời gian xây lại index** nếu cần rollback sau drop.
- Những thay đổi vận hành phụ thuộc đặc tính đặc biệt của index.

Nếu mục tiêu chính là giảm write amplification, trạng thái hidden không phải bằng chứng định lượng cho mức cải thiện. Bạn có thể dùng hidden để kiểm tra **rủi ro phía đọc**, rồi dùng staging/benchmark được thiết kế riêng để ước lượng lợi ích phía ghi sau khi drop.

## 13. Query plan, index prefix và các trường hợp gây hiểu lầm

### 13.1. Một index có thể phục vụ nhiều query shape

Index compound:

~~~javascript
{
  customerId: 1,
  createdAt: -1
}
~~~

Có thể hữu ích cho cả:

~~~javascript
db.orders.find({ customerId: "CUS-001" });
~~~

và:

~~~javascript
db.orders.find({ customerId: "CUS-001" })
  .sort({ createdAt: -1 });
~~~

Khi hide index, có thể có regression ở **một query shape** nhưng không ở query shape khác. Chỉ nhìn độ trễ API đầu tiên sẽ bỏ sót tác động.

### 13.2. Index khác có thể che lấp tác động

Giả sử collection còn có:

~~~javascript
{ status: 1 }
{ status: 1, createdAt: -1 }
{ createdAt: -1 }
~~~

Khi hide index status + createdAt, MongoDB có thể dùng index status rồi sort, hoặc dùng index createdAt rồi lọc. Tùy dữ liệu, một trong các plan này vẫn chấp nhận được hoặc có thể kém hiệu quả.

Kết luận đúng của thử nghiệm là **“với workload được quan sát và các index còn visible, không thấy regression vượt ngưỡng”**, không phải **“index bị hide tuyệt đối vô ích trong mọi điều kiện”**.

### 13.3. Covered query có thể mất tính chất được index bao phủ

Ví dụ:

~~~javascript
db.orders.find(
  { status: "PAID" },
  { _id: 0, status: 1, createdAt: 1 }
);
~~~

Nếu index compound chứa đủ các field được truy vấn và trả về, một query có thể được xử lý hiệu quả mà không phải đọc document đầy đủ, tùy điều kiện. Khi hide index, plan thay thế có thể phải truy cập document nhiều hơn.

Do đó, so sánh **totalDocsExamined** cùng với số lượng kết quả được trả về hữu ích hơn chỉ nhìn một chỉ số thời gian.

### 13.4. Độ chọn lọc thay đổi theo dữ liệu

Khi trạng thái PAID chiếm 90% collection, lọc PAID có thể kém chọn lọc. Khi trạng thái PENDING chỉ chiếm 0,1%, index status có thể rất quan trọng cho nhóm query PENDING.

Cần benchmark cả giá trị **phổ biến** và **hiếm**, nhất là với collection có phân bố dữ liệu lệch mạnh.

## 14. Quan sát production: kết hợp nhiều nguồn đo

Không nên dựa chỉ vào một phép explain hoặc một lần đếm index usage.

| Nguồn | Câu hỏi trả lời | Giới hạn |
| --- | --- | --- |
| **getIndexes()** | Index tồn tại và có hidden không? | Không thể hiện index có hữu ích với workload hay không |
| **$indexStats** | Index đã được sử dụng bao nhiêu lần từ mốc thống kê? | Counter không trực tiếp đo giá trị hiệu năng hoặc tác vụ hiếm |
| **explain("executionStats")** | Query thực thi theo plan nào và xét bao nhiêu key/document? | Không thay thế latency quan sát trên workload thật |
| **Profiler/slow query log** | Có những query nào chậm và plan thay đổi ra sao? | Cần cấu hình thu thập phù hợp và xét overhead |
| **APM/application telemetry** | p50/p95/p99 API và error rate thay đổi thế nào? | Còn ảnh hưởng của nhiều tầng ngoài database |
| **Host/cluster metrics** | CPU, I/O, cache, replication lag có tăng không? | Cần so sánh với tải và thời điểm tương ứng |
| **Lịch batch nghiệp vụ** | Có truy vấn hiếm hoặc job định kỳ cần index không? | Không phải lúc nào cũng xuất hiện trong window thử |

### 14.1. So sánh trước và sau theo một cửa sổ phù hợp

Một bản ghi trial có thể dùng bảng:

| Metric | Baseline | Hidden trial | Ngưỡng chấp nhận |
| --- | ---: | ---: | --- |
| p95 API list orders | 80 ms | 95 ms | < 150 ms |
| p99 API list orders | 180 ms | 250 ms | < 300 ms |
| Timeout rate | 0,02% | 0,03% | < 0,10% |
| Số query COLLSCAN tăng | 0 | 5 | Cần xem kỹ |
| CPU database | 45% | 49% | Theo ngân sách tải |
| Job đối soát cuối ngày | Hoàn thành | Chưa chạy | **Chưa đủ kết luận** |

**Toàn bộ số liệu trong bảng là giả định.** Điểm quan trọng là một trial đang tốt với API thường ngày vẫn chưa đủ nếu **job đối soát cuối ngày chưa chạy**.

### 14.2. Cần đánh giá cả chu kỳ workload

Một số hệ thống có tải đặc biệt:

- Buổi sáng đồng bộ dữ liệu.
- Cuối ngày tổng hợp báo cáo.
- Cuối tuần chạy batch cleanup.
- Đầu tháng đối soát tài chính.
- Dịp chiến dịch khuyến mãi có lượng truy vấn vượt bình thường.

Thời gian thử phải bao phủ những workload liên quan hoặc có kiểm thử đại diện tương đương. Nếu không thể quan sát toàn bộ lịch, hãy ghi rõ phần **chưa kiểm chứng** trước khi quyết định drop.

### 14.3. Lưu dấu query shape

Một query shape là cấu trúc filter, sort, projection và các đặc tính truy vấn liên quan, thay vì chỉ một giá trị tham số cụ thể. Khi tìm ảnh hưởng của index, nhóm theo query shape giúp tránh nhầm mười nghìn truy vấn giống nhau với mười nghìn loại truy vấn.

Các công cụ theo dõi query có thể có cách định danh query shape khác nhau giữa các phiên bản MongoDB. Hãy sử dụng schema metadata theo phiên bản đang triển khai.

## 15. Môi trường staging và production: lựa chọn phạm vi thử

### 15.1. Staging với dữ liệu đại diện

Ưu điểm:

- Thử hide/unhide mà không tác động trực tiếp người dùng.
- Có thể chạy workload ghi và đọc theo kịch bản.
- Phù hợp để khám phá những query đã biết phụ thuộc index.

Hạn chế:

- Dung lượng dữ liệu nhỏ hơn làm query planner chọn kế hoạch khác.
- Phân bố giá trị và thống kê có thể không giống production.
- Ít concurrency, cache/IO khác biệt.
- Job hiếm có thể không được mô phỏng.

Staging là bước quan trọng, nhưng kết quả tốt trên vài nghìn document không thể tự suy ra an toàn với vài trăm triệu document.

### 15.2. Production trial cần kiểm soát thay đổi

**Hide index trên production là thay đổi thật của hành vi query planner**, không phải mô phỏng không ảnh hưởng đến client. Vì vậy chỉ nên thực hiện khi có quyền và kế hoạch thay đổi phù hợp.

Một lần triển khai được kiểm soát cần:

1. Xác nhận collection và index name.
2. Lưu định nghĩa index và baseline.
3. Xác định người theo dõi metric và người được phép rollback.
4. Có cửa sổ quan sát và ngưỡng hủy.
5. Chuẩn bị sẵn lệnh unhide.
6. Theo dõi các API/job liên quan.
7. Ghi nhận kết quả và quyết định sau thử nghiệm.

Nếu hệ thống có khả năng thử một phần workload hoặc môi trường gần production hơn, hãy lựa chọn phạm vi ít rủi ro nhất có thể đại diện cho tình huống thật.

### 15.3. Hidden không phải cờ bật/tắt theo từng người dùng

Thay đổi trạng thái hidden của index là thay đổi ở cấp index/collection. Nó không phải flag mà mỗi request có thể tự bật tắt để mô phỏng độc lập. Những truy vấn được lập kế hoạch trong thời gian index hidden đều chịu ảnh hưởng của trạng thái này theo phạm vi triển khai.

Vì vậy, không thể giả định “chỉ 5% người dùng gặp index hidden” khi thực hiện **hideIndex()** trực tiếp trên một collection chung, trừ khi kiến trúc triển khai đã tách hẳn môi trường hoặc dữ liệu/thành phần phục vụ theo cách hỗ trợ thử nghiệm như vậy.

## 16. Hidden index trong replica set và sharded cluster

### 16.1. Replica set

Mỗi thành viên replica set có dữ liệu và index tương ứng phục vụ truy vấn trên thành viên đó, theo topology và cấu hình đọc. Khi đánh giá tác động, cần quan sát:

- Query đọc từ primary.
- Query đọc từ secondary theo read preference.
- Mức tải và độ trễ của các node.
- Quá trình replication và thay đổi topology nếu có.

Không chỉ kiểm tra một node rồi kết luận mọi client đều có cùng query performance. Driver có thể đọc từ thành viên khác, với tình trạng cache và áp lực công việc khác.

### 16.2. Sharded cluster

Trong sharded cluster, một collection được phân bố trên nhiều shard. Query planner và hiệu năng có thể khác theo phân bố dữ liệu, các shard liên quan và khả năng định tuyến theo shard key.

Trước khi hide hoặc drop index trong cụm sharding, cần xét:

- Truy vấn có shard key hay phải scatter/gather?
- Index hỗ trợ filter/sort ở từng shard hay không?
- Collection và index có ràng buộc với shard key không?
- Metric index usage được thu thập từ những shard nào?
- Có shard nào lớn hơn nhiều so với shard khác?
- Kế hoạch thực hiện thao tác index trên toàn collection đã được vận hành chấp thuận chưa?

Khi quản trị sharded collection, thực hiện lệnh qua **mongos** theo quy trình phù hợp; không tự ý thay đổi trạng thái index ở từng shard riêng lẻ làm trạng thái cụm thiếu nhất quán.

### 16.3. Hidden index không thay thế phân tích shard key

Một index phụ có thể hỗ trợ truy vấn nhưng không giải quyết vấn đề shard key kém chọn lọc hoặc phân bố dữ liệu lệch. Nếu query vẫn phải hỏi nhiều shard, việc hide một index chỉ cho biết một phần tác động lên quá trình thực thi trong shard.

Không được xóa index có liên hệ tới điều kiện vận hành của sharded cluster chỉ vì nó có số lượt query usage thấp. Phải kiểm tra các ràng buộc riêng của topology.

## 17. Ví dụ thao tác với collMod

Bên cạnh helper **hideIndex()** và **unhideIndex()**, MongoDB cung cấp lệnh quản trị **collMod** để cập nhật một số thuộc tính index, trong đó có hidden.

Ẩn index theo tên:

~~~javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "idx_orders_status_created",
    hidden: true
  }
});
~~~

Bỏ ẩn:

~~~javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "idx_orders_status_created",
    hidden: false
  }
});
~~~

Thực hiện trong database **shop** vì trường **collMod: "orders"** chỉ ra collection của database hiện tại.

Đối với bài thực hành thông thường, helper **db.orders.hideIndex()** và **db.orders.unhideIndex()** dễ đọc hơn. Khi tích hợp vào công cụ quản trị hoặc driver không có helper tương ứng, lệnh collMod là lựa chọn rõ ràng.

### 17.1. Cần quyền thao tác index

Việc xem danh sách index và việc thay đổi hidden state có yêu cầu quyền khác nhau. Tài khoản ứng dụng chỉ được phép đọc collection thông thường không mặc nhiên có quyền hide/unhide/drop.

Trong production, nên dùng danh tính quản trị có quyền tối thiểu cần thiết, có audit và quy trình phê duyệt thay đổi. Không nên trao quyền quản trị index cho một API nghiệp vụ chỉ để cho phép thử nghiệm.

## 18. Ví dụ Java Sync Driver để quản lý hidden index

Một ứng dụng Java thường không nên tự hide index trong code xử lý request. Nhưng công cụ quản trị hoặc migration job có thể cần phát lệnh **collMod**.

Ví dụ dùng **MongoDatabase.runCommand()**:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ToggleHiddenIndex {

    private static void setHidden(
            MongoDatabase database,
            String collectionName,
            String indexName,
            boolean hidden) {

        Document indexOptions = new Document("name", indexName)
                .append("hidden", hidden);

        Document command = new Document("collMod", collectionName)
                .append("index", indexOptions);

        Document result = database.runCommand(command);
        System.out.println(result.toJson());
    }

    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("shop");

            // Thí nghiệm có chủ đích; không tự chạy trong HTTP request.
            setHidden(
                    database,
                    "orders",
                    "idx_orders_status_created",
                    true
            );

            // Sau khi đã quan sát, có thể phục hồi:
            setHidden(
                    database,
                    "orders",
                    "idx_orders_status_created",
                    false
            );
        }
    }
}
~~~

Đây là ví dụ về API Java, **không phải một quy trình production tự động an toàn**. Chạy code yêu cầu MongoDB server hỗ trợ hidden index, index có sẵn, URI đúng và tài khoản có quyền thích hợp.

Ví dụ gọi hide rồi unhide liên tiếp để minh họa cú pháp, nên không tạo ra thời gian quan sát workload đáng kể. Trong thử nghiệm thực, hai thao tác thuộc **hai bước vận hành tách biệt**, với giai đoạn thu thập metric ở giữa.

### 18.1. Cẩn trọng khi tự động hóa drop

Nếu code tự chạy:

~~~java
// Đừng suy ra nên drop chỉ vì hide thành công.
~~~

thì thiếu bằng chứng rằng workload không cần index. Quyết định drop nên dựa trên quan sát đủ chu kỳ, tính năng index và kế hoạch phục hồi đã được chuẩn bị.

Một tool quản trị có thể tự động lưu định nghĩa index và metric, nhưng nên có cơ chế kiểm soát thay đổi rõ ràng trước khi drop.

## 19. Quyết định giữ, unhide hay drop

Sau khi thử, có thể kết luận theo các trường hợp:

| Kết quả thử | Quyết định phù hợp |
| --- | --- |
| Query quan trọng chậm đáng kể | **Unhide** và giữ index, hoặc thiết kế index thay thế |
| Có lỗi do hint index | **Unhide**, sửa dependency hoặc chuẩn bị phương án phù hợp |
| Không thấy regression nhưng chưa thử job cuối tháng | Tiếp tục quan sát hoặc giữ index; **chưa đủ cơ sở drop** |
| Không thấy regression trong workload đại diện, không có ràng buộc đặc biệt | Có thể cân nhắc **drop** sau khi hoàn tất đánh giá |
| Index là unique, TTL hoặc phục vụ quy tắc nghiệp vụ | Cần đánh giá ràng buộc riêng; hidden trial **không đủ** |
| Chỉ muốn tránh query planner dùng index nhưng vẫn cần ràng buộc | Có thể **giữ hidden** lâu dài nếu đó là chủ đích và vận hành chấp nhận chi phí |
| Dự kiến workload tương lai sẽ cần index | Giữ index hoặc có kế hoạch xây dựng phù hợp trước khi tính năng ra mắt |

Một index **không cần thiết trong workload hiện tại** có thể vẫn được giữ chủ đích cho tính năng sắp ra mắt; ngược lại, một index có ít lượt truy cập nhưng là **index của truy vấn cực quan trọng** có thể đáng giữ.

### 19.1. Lưu cấu hình để có thể tạo lại

Trước khi drop, lưu đầy đủ:

~~~javascript
const definition = db.orders.getIndexes().find(
  i => i.name === "idx_orders_status_created"
);

printjson(definition);
~~~

Đối với index mẫu, lệnh tạo lại có thể là:

~~~javascript
db.orders.createIndex(
  { status: 1, createdAt: -1 },
  {
    name: "idx_orders_status_created"
  }
);
~~~

Nếu index thực tế có unique, TTL, collation, partialFilterExpression hoặc cấu hình khác, phải lưu và phục hồi các thuộc tính đó theo đúng mục đích. Lệnh ví dụ trên **không đủ** để dựng lại mọi loại index.

### 19.2. Drop xong vẫn cần quan sát

Việc hidden trial thành công làm giảm rủi ro, nhưng sau khi drop cần tiếp tục giám sát:

- Độ trễ truy vấn và lỗi ứng dụng.
- Tài nguyên storage/cache.
- Throughput và độ trễ ghi.
- Query plan trong workload thực.
- Những job định kỳ lần lượt được chạy sau thay đổi.

Drop có thể giúp giảm write/storage overhead, nhưng mức cải thiện thực tế phải được đo; nó không được bảo đảm bằng đúng tỷ lệ dung lượng index đã bị xóa.

## 20. Runbook mẫu cho một thử nghiệm

Một runbook ngắn nhưng đủ thao tác có thể viết như sau.

### Giai đoạn A – Chuẩn bị

**Mục tiêu:** kiểm tra index idx_orders_status_created có thể loại bỏ an toàn khỏi collection shop.orders không.

Các bước:

1. Xác nhận đúng môi trường, database và collection.
2. Lưu output **getIndexes()** và định nghĩa index ứng viên.
3. Phân loại unique, TTL, partial, sparse, collation, các ràng buộc sharding.
4. Thu thập **$indexStats** trong cửa sổ đại diện.
5. Liệt kê API/job/query shape phụ thuộc index.
6. Ghi baseline explain và p95/p99 latency.
7. Thống nhất ngưỡng rollback.
8. Chuẩn bị sẵn lệnh **unhideIndex()**.

### Giai đoạn B – Thực hiện

~~~javascript
use shop

db.orders.hideIndex("idx_orders_status_created");

db.orders.getIndexes().filter(
  i => i.name === "idx_orders_status_created"
);
~~~

Xác nhận index có **hidden: true**, rồi quan sát workload.

### Giai đoạn C – So sánh

Chạy cùng query đại diện:

~~~javascript
db.orders.find({
  status: "PAID"
})
.sort({
  createdAt: -1
})
.limit(20)
.explain("executionStats");
~~~

Ghi lại:

~~~text
Query shape:
Index ứng viên:
Thời điểm baseline:
Thời điểm hidden:
Plan trước:
Plan sau:
DocsExamined trước/sau:
KeysExamined trước/sau:
p95/p99 trước/sau:
Lỗi và timeout:
Tình trạng batch/report:
Kết luận:
~~~

### Giai đoạn D – Rollback nếu vượt ngưỡng

~~~javascript
db.orders.unhideIndex("idx_orders_status_created");
~~~

Xác nhận metadata và tiếp tục giám sát. Nếu thử nghiệm đã gây regression, không tiến hành drop.

### Giai đoạn E – Quyết định

Khi đã đủ số liệu:

- **Giữ visible:** index có ích hoặc rủi ro loại bỏ không chấp nhận được.
- **Giữ hidden:** muốn tránh planner dùng nhưng vẫn cần duy trì index/ràng buộc.
- **Drop:** đã kiểm tra tác động truy vấn và các ràng buộc, có kế hoạch phục hồi.
- **Thay thế index:** cần một index khác hỗ trợ tốt hơn nhiều query shape; xây và thử index mới trước khi xóa index cũ.

Không nên biến runbook thành script tự động **hide → đợi vài giây → drop**, vì vài giây không chứng minh được hệ thống đã chạy đầy đủ workload quan trọng.

## 21. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Hidden index đã bị xóa khỏi database | Nó vẫn tồn tại, được duy trì và chiếm dung lượng |
| Hide index sẽ làm insert/update nhanh hơn như drop | Chi phí duy trì index vẫn tồn tại khi hidden |
| Query planner có thể dùng hidden index nếu nó rất phù hợp | Hidden index không được dùng để hỗ trợ query |
| Có thể hint một hidden index để kiểm thử | Hint không biến hidden index thành usable index |
| Hide unique index làm ngừng kiểm tra unique | Unique constraint vẫn được thực thi |
| Hide TTL index làm ngừng xóa dữ liệu hết hạn | TTL vẫn hoạt động |
| Thấy accesses.ops = 0 là chắc chắn index vô dụng | Cần xét mốc thống kê, node, query hiếm và ràng buộc |
| Explain trước/sau là đủ để quyết định drop | Cần quan sát workload, SLO, concurrency và thời điểm định kỳ |
| Unhide và tạo lại index là hai thao tác tương đương | Unhide không cần rebuild; drop rồi tạo lại có chi phí |
| Index có chung key prefix thì một index chắc chắn thừa | Cần xét sort, projection, độ chọn lọc, collation và loại index |
| Hide chỉ ảnh hưởng query đang thử | Hide thay đổi khả năng dùng index cho workload liên quan trong phạm vi collection |
| Có thể ẩn index _id mặc định | Không thể hide index _id mặc định |
| Trial không thấy chậm nghĩa là không có rủi ro | Có thể chưa chạy job hiếm hoặc chưa quan sát peak load |
| Drop index đã hidden chỉ là thay đổi trạng thái nhỏ | Drop còn xóa cấu trúc index và có thể mất ràng buộc đặc biệt |

## 22. Bài thực hành với collection thử nghiệm

Bài thực hành dùng một collection riêng để tránh ảnh hưởng dữ liệu nghiệp vụ. Ví dụ dưới đây dành cho mongosh trên MongoDB hỗ trợ hidden indexes.

### Bài 1 – Tạo dữ liệu và index

~~~javascript
use hidden_index_lab

db.orders.insertMany([
  {
    _id: 1,
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-01-01T10:00:00Z"),
    amount: 100000
  },
  {
    _id: 2,
    customerId: "C-02",
    status: "PENDING",
    createdAt: ISODate("2026-01-02T10:00:00Z"),
    amount: 200000
  },
  {
    _id: 3,
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-01-03T10:00:00Z"),
    amount: 300000
  },
  {
    _id: 4,
    customerId: "C-03",
    status: "CANCELLED",
    createdAt: ISODate("2026-01-04T10:00:00Z"),
    amount: 150000
  },
  {
    _id: 5,
    customerId: "C-02",
    status: "PAID",
    createdAt: ISODate("2026-01-05T10:00:00Z"),
    amount: 280000
  }
]);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created" }
);
~~~

Nếu chạy lại insertMany trên collection đã có ID 1–5 sẽ gặp duplicate key; hãy dùng database thử nghiệm mới hoặc xử lý dữ liệu mẫu rõ ràng thay vì chạy trên production.

### Bài 2 – Quan sát trước khi hide

~~~javascript
db.orders.getIndexes();

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Hãy tìm:

- Index **idx_status_created** có tồn tại không?
- Winning plan có dùng index này không?
- Có bao nhiêu document được trả?
- Có giai đoạn SORT riêng không?
- totalKeysExamined và totalDocsExamined là bao nhiêu?

Với collection **chỉ có 5 document**, query planner có thể chọn COLLSCAN vì chi phí nhỏ; đừng coi việc không dùng index ở dữ liệu mẫu nhỏ là bằng chứng index vô ích trên production.

### Bài 3 – Hide index và so sánh

~~~javascript
db.orders.hideIndex("idx_status_created");

db.orders.getIndexes().filter(
  index => index.name === "idx_status_created"
);

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .explain("executionStats");
~~~

Giải thích:

1. Index có còn xuất hiện trong getIndexes() không?
2. Vì sao hidden: true không đồng nghĩa với drop?
3. Query planner có thể dùng index này sau hide không?
4. Có thay đổi plan không? Nếu chưa thấy thay đổi do collection nhỏ, cần môi trường thử nghiệm như thế nào để đo đúng?

### Bài 4 – Tìm hiểu hint

Khi index còn hidden:

~~~javascript
db.orders.find({ status: "PAID" })
  .hint("idx_status_created")
  .toArray();
~~~

Quan sát thông báo lỗi và giải thích vì sao không thể dùng hint để ép query planner sử dụng hidden index.

Sau đó bỏ ẩn:

~~~javascript
db.orders.unhideIndex("idx_status_created");
~~~

Chạy lại query hint nếu cần quan sát sự khác biệt trong một collection thử nghiệm.

### Bài 5 – Thử unique index

~~~javascript
db.accounts.insertOne({
  _id: 1,
  email: "an@example.net"
});

db.accounts.createIndex(
  { email: 1 },
  {
    name: "uq_accounts_email",
    unique: true
  }
);

db.accounts.hideIndex("uq_accounts_email");
~~~

Thử insert một account khác có cùng email:

~~~javascript
db.accounts.insertOne({
  _id: 2,
  email: "an@example.net"
});
~~~

MongoDB vẫn từ chối vi phạm unique constraint. Hãy giải thích vì sao thử nghiệm hidden không đủ để kết luận **drop unique index** là an toàn.

### Bài 6 – Phân tích một index nghi ngờ dư thừa

Giả sử một hệ thống thực có ba index:

~~~javascript
{ customerId: 1 }
{ customerId: 1, createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

Có các truy vấn:

~~~javascript
// Q1
db.orders.find({ customerId: "C-01" });

// Q2
db.orders.find({ customerId: "C-01" })
  .sort({ createdAt: -1 })
  .limit(30);

// Q3
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1 })
  .limit(30);
~~~

Hãy đề xuất:

1. Index nào có thể là ứng viên thử ẩn đầu tiên?
2. Q1, Q2, Q3 có phụ thuộc cùng một index không?
3. Trường hợp nào cần kiểm tra độ chọn lọc và projection?
4. Tại sao không nên hide cả ba index trong một bước?
5. Những metric và query shape nào cần theo dõi trước khi drop?

### Bài 7 – Viết runbook của riêng bạn

Bạn cần giảm dung lượng index của collection có 100 triệu document. Viết kế hoạch gồm:

- Mục tiêu và tên index ứng viên.
- Lệnh kiểm tra definition và usage.
- Cách xác định query quan trọng, job định kỳ và hint.
- Các baseline metric.
- Lệnh hide và xác nhận hidden state.
- Ngưỡng rollback và lệnh unhide.
- Khoảng quan sát đại diện.
- Những điều hidden trial không mô phỏng.
- Điều kiện được phép drop và cách lưu định nghĩa để rebuild.

Một kế hoạch tốt sẽ không chỉ có **ba lệnh hide–unhide–drop**, mà còn có **lý do chọn index, bằng chứng từ workload, tiêu chí dừng và quy trình phục hồi**.

## 23. Nguyên tắc ghi nhớ

Hidden index là công cụ **giảm rủi ro khi đánh giá một index có còn cần cho hiệu năng truy vấn hay không**. Khi hide, MongoDB vẫn giữ index nhưng ngăn query planner sử dụng; khi unhide, planner có thể cân nhắc lại mà không phải xây dựng index từ đầu.

Vì thế, quy trình đúng thường là:

**Kiểm kê → Đo baseline → Hide → Quan sát workload → Unhide nếu có regression → Chỉ drop khi đã đánh giá đầy đủ.**

Không được quên ba giới hạn:

1. Hidden index **vẫn tiêu tốn tài nguyên ghi và dung lượng**.
2. Hidden index **vẫn thực thi unique/TTL và những cơ chế được gắn với nó**, nên không mô phỏng hết hậu quả của drop.
3. Một phép thử ngắn hoặc một query đơn lẻ **không đại diện cho toàn bộ workload**, đặc biệt với báo cáo định kỳ, query hiếm và môi trường sharded cluster.

Thiết kế thử nghiệm tốt phải trả lời được không chỉ câu “index đang dùng hay không”, mà cả câu **“nếu không còn index này, những truy vấn và ràng buộc quan trọng nào sẽ bị ảnh hưởng, và hệ thống phục hồi thế nào?”**.

## Tài liệu tham khảo

- [MongoDB Manual — Hidden Indexes](https://www.mongodb.com/docs/manual/core/index-hidden/)
- [MongoDB Manual — db.collection.hideIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.hideIndex/)
- [MongoDB Manual — db.collection.unhideIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.unhideIndex/)
- [MongoDB Manual — db.collection.dropIndex()](https://www.mongodb.com/docs/manual/reference/method/db.collection.dropIndex/)
- [MongoDB Manual — db.collection.getIndexes()](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/)
- [MongoDB Manual — $indexStats](https://www.mongodb.com/docs/manual/reference/operator/aggregation/indexStats/)
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Manual — Index Properties](https://www.mongodb.com/docs/manual/core/indexes/index-properties/)
