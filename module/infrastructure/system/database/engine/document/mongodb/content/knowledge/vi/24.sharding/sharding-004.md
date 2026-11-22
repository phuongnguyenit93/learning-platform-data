# Chọn shard key theo độ phân tán, tần suất và hướng tăng giá trị

Khi một collection MongoDB trở nên quá lớn hoặc nhận quá nhiều thao tác đọc/ghi để một replica set phục vụ hiệu quả, **sharding** cho phép phân phối dữ liệu trên nhiều **shard**. Nhưng việc tăng số shard không tự bảo đảm hệ thống sẽ phân phối đều tải, truy vấn nhanh hoặc dễ mở rộng. Kết quả phụ thuộc rất lớn vào **shard key** được chọn.

Shard key là một hoặc nhiều field mà MongoDB dùng để xác định **document thuộc phạm vi shard-key nào và được định tuyến tới shard nào**. Trong một sharded cluster, `mongos` và metadata phân vùng phối hợp để route các thao tác; dữ liệu được tổ chức thành các **chunk/range** có thể được phân bổ hoặc di chuyển giữa các shard tùy chính sách cân bằng và khả năng phân chia.

Một shard key kém có thể gây ra các tình huống tưởng như trái ngược:

- Collection có hàng chục triệu document nhưng **hầu hết insert dồn vào một shard**.
- Số lượng khách hàng rất lớn nhưng một **tenant cực kỳ nóng** vẫn làm nghẽn một shard.
- Hash giúp insert phân bố đều hơn, nhưng một báo cáo theo **khoảng thời gian** lại phải đọc từ nhiều shard.
- Tăng số shard không giải quyết được một **giá trị shard key xuất hiện quá nhiều lần**.
- Một truy vấn rất nhanh khi có filter theo shard key trở thành **scatter-gather** khi API quên truyền shard key.
- Các bản ghi được phân bố đều về **dung lượng** nhưng không đều về **request/giây**, khiến latency vẫn lệch.

Chọn shard key vì thế không phải “chọn field có nhiều giá trị nhất” mà là bài toán đồng thời về:

1. **Độ phân tán/cardinality:** có bao nhiêu giá trị shard key phân biệt và chúng có tạo đủ không gian để chia dữ liệu?
2. **Tần suất/frequency:** mỗi giá trị xuất hiện bao nhiêu lần, chịu bao nhiêu lượt truy cập và có **hot key** hay không?
3. **Hướng tăng/monotonicity:** giá trị shard key được tạo theo chuỗi tăng/giảm liên tục hay phân bố đa dạng, và điều đó ảnh hưởng ghi mới ra sao?
4. **Mẫu truy vấn/query patterns:** API thường tìm đúng một khóa, lọc theo tiền tố của compound key hay quét một khoảng?
5. **Ràng buộc vận hành:** uniqueness, zones, kích thước dữ liệu, metadata, balancing, resharding và khả năng phục hồi.

Bài học phân tích ba tiêu chí đầu làm trọng tâm, rồi kết nối chúng với cách chọn **ranged, hashed và compound shard key** cho một hệ thống thực tế.

## 1. Shard key tham gia vào đường đi của một truy vấn như thế nào?

Hình dung một sharded cluster:

```text
                        Application
                            |
                         mongos
                 (router + shard metadata)
                            |
                  +---------+---------+
                  |         |         |
                Shard A   Shard B   Shard C
               (replica) (replica) (replica)
                  |         |         |
              chunk(s)  chunk(s)  chunk(s)
```

Một collection được sharding theo:

```javascript
{ tenantId: 1, orderId: 1 }
```

thì giá trị shard key là cặp:

```javascript
{
  tenantId: "TENANT-A",
  orderId: "ORD-000001"
}
```

Để thực hiện một thao tác, `mongos` cần xác định giá trị shard key hoặc khoảng khóa có liên quan. Nếu có đủ thông tin trong filter, router có thể **target một shard hoặc tập shard nhỏ hơn**. Nếu thiếu thông tin cần thiết, truy vấn có thể được gửi tới nhiều shard (**scatter-gather**).

Ví dụ minh họa:

```javascript
// Có equality trên cả hai field shard key.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-000001"
});

// Chỉ biết tenant, chưa biết orderId.
db.orders.find({
  tenantId: "TENANT-A"
});

// Không có thành phần shard key.
db.orders.find({
  status: "PAID"
});
```

Với shard key compound, việc truy vấn có được target tốt hay không còn phụ thuộc thứ tự field, loại sharding, range metadata và query shape. Đừng tự cho rằng câu thứ hai luôn target một shard hoặc câu thứ ba tự động có truy vấn hiệu quả chỉ vì trên từng shard có index `status`.

**Đây là hai cấp tối ưu khác nhau:**

- **Shard targeting:** những shard nào phải tham gia?
- **Local query execution:** trên mỗi shard, MongoDB dùng index/query plan nào để đọc dữ liệu?

Một shard key tốt nhưng index cục bộ kém vẫn có thể chậm; một index rất tốt nhưng phải gửi query tới hàng chục shard vẫn có chi phí fan-out và gộp kết quả.

## 2. Ba tiêu chí cốt lõi: cardinality, frequency, monotonicity

Để đánh giá một field ứng viên, trước hết phân biệt các khái niệm.

| Tiêu chí | Câu hỏi | Rủi ro khi chọn sai |
|---|---|---|
| **Cardinality** | Có bao nhiêu giá trị khóa khác nhau? | Quá ít giá trị thì không đủ đơn vị để phân phối dữ liệu |
| **Frequency** | Một giá trị xuất hiện bao nhiêu lần, chiếm bao nhiêu dữ liệu/lưu lượng? | Một giá trị quá phổ biến gây hot key/hot shard |
| **Monotonicity** | Các giá trị mới có đi đều về phía đầu/cuối miền khóa không? | Range-sharded collection có thể dồn insert vào một vùng biên |
| **Query locality** | API có thường biết khóa hoặc khoảng khóa cần đọc không? | Scatter-gather, tăng network/CPU |
| **Growth pattern** | Dữ liệu tăng theo tenant, thời gian hay ID? | Phân bố hôm nay tốt nhưng sáu tháng sau lệch |
| **Stability** | Shard key có thường thay đổi không? | Cập nhật/move dữ liệu phức tạp và tốn tài nguyên |

Ba tiêu chí đầu tác động trực tiếp tới **khả năng phân chia** và **độ lệch tải**. Nhưng chưa đủ để chốt shard key, vì đọc/ghi thực tế có thể thay đổi kết luận.

### 2.1. Cardinality là số giá trị phân biệt

Giả sử collection có một triệu đơn hàng:

```text
status:
  "NEW", "PAID", "CANCELLED"              -> 3 giá trị

region:
  "NORTH", "CENTRAL", "SOUTH"              -> 3 giá trị

tenantId:
  hàng nghìn tenant                        -> nhiều giá trị

orderId:
  mỗi order có ID riêng                    -> gần một triệu giá trị
```

Trường `status` hoặc `region` có cardinality rất thấp, nên thường không phải shard key độc lập phù hợp cho tập lớn. Các tài liệu có cùng giá trị khóa không thể được chia thành vô số vùng giá trị **khác nhau** chỉ bằng cách thêm shard.

`orderId` có cardinality cao hơn rất nhiều; nhưng điều đó chưa bảo đảm tốt nếu ID được cấp tăng dần liên tục hoặc truy vấn chủ yếu không có `orderId`.

### 2.2. Frequency là mức tập trung vào từng giá trị

Giả sử `tenantId` có 10.000 giá trị phân biệt, tưởng như rất tốt. Nhưng:

```text
TENANT-BIG:     75% dữ liệu
9.999 tenant:   25% dữ liệu còn lại
```

Nếu shard key **chỉ là `tenantId`**, mọi document của `TENANT-BIG` có **cùng giá trị shard key**. Hệ thống không thể chia chính một giá trị tenantId sang nhiều range shard-key riêng biệt mà vẫn chỉ dựa vào giá trị khóa đó.

**Cardinality toàn collection cao nhưng frequency của một key quá lớn** có thể gây mất cân bằng.

### 2.3. Monotonicity là xu hướng tăng/giảm

Giả sử `orderNo` tăng:

```text
100001, 100002, 100003, 100004, ...
```

Nó có cardinality cao, mỗi giá trị thường xuất hiện một lần. Nhưng nếu dùng **range-based sharding** trên `orderNo`, các insert mới thường đi tới **đầu hoặc cuối miền khóa**, tập trung vào chunk ở biên trong một giai đoạn.

Điều này có thể tạo **hot shard cho insert** dù về lâu dài dữ liệu cũ đã được phân phối trên nhiều shard. High cardinality + low duplicate frequency **không tự giải quyết monotonicity**.

## 3. Một ví dụ so sánh ba shard key ứng viên

Collection `orders` có:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  orderNo: NumberLong("12004567"),
  orderId: "ORD-12004567",
  customerId: "CUS-9081",
  status: "PAID",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-03-01T08:30:00Z")
}
```

Các ứng viên:

| Shard key | Cardinality | Frequency | Monotonicity | Cân nhắc chính |
|---|---|---|---|---|
| `{ status: 1 }` | Rất thấp | Một vài giá trị cực phổ biến | Không nhất thiết tăng | Phân tán kém, hot values |
| `{ tenantId: 1 }` | Có thể cao | Có thể lệch nặng theo tenant | Thường không tăng | Tốt cho tenant locality nhưng hot tenant |
| `{ orderNo: 1 }` | Cao | Gần một document/giá trị | **Tăng liên tục** | Hot range ở biên khi insert |
| `{ orderNo: "hashed" }` | Cao | Gần một document/giá trị | Hash phá thứ tự tăng | Phân tán writes tốt hơn, range query kém locality |
| `{ tenantId: 1, orderId: "hashed" }` | Cao nhờ orderId | Phân tách nhiều order trong một tenant | Hash thành phần orderId | Có thể giảm hot tenant nếu phân vùng phù hợp, nhưng đọc theo tenant phải xét routing |
| `{ tenantId: 1, createdAt: 1 }` | Cao theo tổ hợp | Trùng timestamp có thể lớn | Tăng theo thời gian trong tenant | Tốt cho range của tenant nhưng có thể hot theo mỗi tenant |

Không có dòng nào “luôn thắng”. Cần đặt bên cạnh từng query mà ứng dụng thực sự chạy.

## 4. Cardinality: hiểu sâu hơn số lượng distinct values

Cardinality thường được ước tính bằng:

\[
D = |\{k(d): d \in \text{collection}\}|
\]

Trong đó `k(d)` là giá trị shard key của document `d`, `D` là số giá trị khác nhau.

Nếu tổng số document là `N`, tỷ lệ đơn giản:

\[
\text{distinctRatio} = \frac{D}{N}
\]

giúp hình dung số lượng giá trị phân biệt so với quy mô dữ liệu. Tuy nhiên, tỷ lệ này **không đủ** để chốt shard key.

### 4.1. Ví dụ hai ứng viên có cùng cardinality

Giả sử có 10 triệu document, hai field đều có `D=100.000`.

- **Field A:** mỗi giá trị xuất hiện khoảng 100 document.
- **Field B:** một giá trị xuất hiện 7 triệu document, 99.999 giá trị còn lại chia nhau 3 triệu.

Cả hai có cardinality giống nhau nhưng khả năng phân phối theo giá trị khác xa. Field B là ứng viên rất rủi ro nếu giá trị phổ biến nhất tạo hot key.

Do đó, sau khi đếm distinct phải đo **frequency distribution**.

### 4.2. Cardinality quá thấp không được cứu chỉ bằng nhiều shard

Nếu một collection có shard key `status` chỉ gồm 4 giá trị:

```text
NEW
PAID
CANCELLED
REFUNDED
```

thêm shard thứ 20 không tạo thêm 16 giá trị status mới. Không thể kỳ vọng mỗi shard tự động có cùng lượng document nếu một status chiếm 90% dữ liệu.

Sharding không thay đổi miền giá trị nghiệp vụ. Muốn phân tán hơn phải chọn **shard key khác hoặc compound key** có nhiều giá trị phân biệt phù hợp, chẳng hạn kết hợp định danh đơn hàng.

### 4.3. Null và missing có thể làm cardinality thấp đi

Nếu nhiều document không có field ứng viên:

```javascript
{ _id: 1, tenantId: null }
{ _id: 2 }
{ _id: 3, tenantId: null }
```

những record này không tạo ra vô số shard key value hữu ích. Trường shard key thiếu/null có quy tắc biểu diễn/routing riêng trong MongoDB, nhưng về thiết kế, một lượng lớn record thiếu khóa có thể tạo **tập trung dữ liệu và truy vấn**.

Hãy chuẩn hóa schema, kiểm tra tỷ lệ null/missing và đảm bảo field shard key tồn tại với giá trị có ý nghĩa trước khi quyết định.

## 5. Frequency: một giá trị khóa nóng gây hậu quả gì?

Gọi `f(v)` là số document có shard key value `v`. Khi đó:

\[
f_{\max} = \max_v f(v)
\]

và:

\[
p_{\max} = \frac{f_{\max}}{N}
\]

là tỷ lệ document chiếm bởi giá trị phổ biến nhất.

Nếu `p_max = 0.75`, nghĩa là **75% document dùng cùng một giá trị shard key**. Trong range-based sharding với một shard key độc lập như tenantId, đó là một tín hiệu đỏ.

### 5.1. Dung lượng theo key và tải theo key là hai thống kê khác

Frequency có ít nhất hai nghĩa vận hành:

1. **Data frequency:** số record/byte gắn với một giá trị.
2. **Request frequency:** số operation/giây đọc/ghi gắn với giá trị đó.

Ví dụ:

```text
TENANT-A có 50% document nhưng chỉ 5% request.
TENANT-B có 2% document nhưng 70% request.
```

Từ góc độ dung lượng, tenant A lớn. Từ góc độ tải, tenant B là hot key.

Một shard key nên được đánh giá cả **data size distribution** lẫn **read/write traffic distribution**; chỉ đếm document không đủ để dự báo CPU, IOPS hoặc p99 latency.

### 5.2. Một key duy nhất có thể là giới hạn mở rộng

Giả sử collection shard theo `{ userId: 1 }` và một tài khoản nổi tiếng tạo 10.000 event/giây:

```javascript
{
  userId: "celebrity-user",
  eventId: "...",
  createdAt: ISODate("2026-03-01T08:00:00Z")
}
```

Mọi event của user này dùng cùng `userId` trong shard key. Tăng thêm shard không tự phân tán những event đó ra nhiều giá trị shard key. Hot user có thể trở thành nút thắt của một shard.

Hướng giải quyết có thể là shard key compound có thêm một trường phân biệt, ví dụ eventId hoặc bucket/hash suffix, nhưng khi đó cần đánh giá tác động đến **đọc toàn bộ lịch sử một user**.

### 5.3. Salting có đánh đổi

Một thiết kế thủ công có thể thêm:

```javascript
{
  userId: "celebrity-user",
  bucketNo: 0,    // 0..15
  eventId: "EVT-123",
  ...
}
```

và shard theo `{ userId: 1, bucketNo: 1 }` trong một mô hình phù hợp.

Nếu `bucketNo` có 16 giá trị, một user nóng có thể được chia thành nhiều shard-key value, **nhưng không bảo đảm mỗi giá trị thực sự nằm trên shard khác** nếu metadata/balancing/topology không phù hợp.

Đọc toàn bộ event của user lại cần quét các bucket tương ứng. Nếu `bucketNo` là số ngẫu nhiên được gán tùy ý, truy vấn theo user có thể phải fan-out. Ngoài ra, uniqueness theo user/event, phân trang và thứ tự theo thời gian phức tạp hơn.

Không thêm salt chỉ vì bảng frequency lệch nếu chưa xác định **lợi ích ghi và chi phí đọc**.

## 6. Monotonicity: vì sao key tăng dần tạo hot shard?

Giả sử dùng range sharding trên:

```javascript
{ orderNo: 1 }
```

và tất cả insert mới có `orderNo` tăng:

```text
Sharding range:
[-∞, 100000)       -> Shard A
[100000, 200000)   -> Shard B
[200000, +∞)       -> Shard C

Insert mới:
230001, 230002, 230003, ...
                          └──> Shard C
```

Tại thời điểm này, **mọi insert mới** rơi vào chunk/range cuối, nên shard C có thể chịu phần lớn write traffic. Balancer có thể di chuyển các range/chunk về sau, nhưng việc di chuyển dữ liệu **không tự loại bỏ tính chất mọi giá trị mới tiếp tục dồn vào vùng biên**.

### 6.1. Những field dễ có hướng tăng

- `createdAt` hoặc timestamp từ nguồn phát sinh event;
- Auto-increment `orderNo`, `invoiceNo`, sequence;
- Số phiên bản tăng;
- ObjectId được tạo theo thời gian thường có **xu hướng tăng** do thành phần timestamp, dù không phải đồng hồ toàn cục và không đảm bảo thứ tự tuyệt đối;
- Những mã String có tiền tố thời gian và suffix tăng theo thứ tự từ điển.

Nếu cần tối ưu append-heavy workloads, phải kiểm tra thực tế thứ tự BSON của field, không chỉ nhìn tên `id` hay `timestamp`.

### 6.2. Hướng giảm cũng có vấn đề đối xứng

Nếu một sequence tạo số âm giảm dần:

```text
-1, -2, -3, -4, ...
```

insert có thể tập trung ở range **đầu** thay vì range cuối. Vấn đề không phải “giá trị tăng là xấu” mà là **giá trị mới liên tục đổ về một biên của không gian range**.

### 6.3. Có cardinality cao và frequency thấp vẫn hot

Một `orderNo` unique có:

```text
D ≈ N
f_max = 1
```

Đây là hai chỉ số đẹp. Nhưng nếu `orderNo` tăng mỗi giây, range sharding vẫn có thể tạo hot insert range.

Vì thế, **cardinality, frequency và monotonicity phải được đánh giá cùng nhau**.

### 6.4. Hot shard khác hot index page

Ngay cả trong một replica set không sharded, index trên khóa tăng có thể tạo write pressure ở những vùng B-tree nhất định. Trong sharding, vấn đề còn thêm **routing tất cả insert tới một shard**.

Hash shard key có thể giúp phân tán hoạt động lên nhiều shard, nhưng không mặc định giải quyết mọi loại contention bên trong từng shard, đặc biệt khi application có một document bị cập nhật dồn dập.

## 7. Range-based sharding: ưu và nhược điểm

Range-based sharding đặt các giá trị shard key vào những khoảng liên tiếp theo thứ tự BSON.

Ví dụ khai báo ý tưởng:

```javascript
sh.shardCollection(
  "shop.orders",
  { orderNo: 1 }
);
```

Lệnh trên chỉ có ý nghĩa trong **sharded cluster** được cấu hình qua `mongos`, với các yêu cầu index, quyền và điều kiện version phù hợp. Không chạy lệnh sharding trên production khi chưa có thiết kế phân vùng và kế hoạch vận hành.

### 7.1. Lợi ích: locality của khoảng

Query:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

có thể target các shard chứa những shard-key range liên quan, thay vì scatter toàn cluster theo mặc định. Điều này hữu ích khi hệ thống thường:

- Quét dữ liệu theo đoạn số;
- Chạy báo cáo theo khoảng thời gian;
- Xử lý các vùng khóa;
- Cần gắn một range dữ liệu vào zone/địa điểm theo chính sách;
- Thực hiện các batch job theo thứ tự.

### 7.2. Nhược điểm: write concentration khi insert đơn điệu

Nếu `orderNo` tăng liên tục, write-heavy applications có thể dồn vào range cuối.

Đánh đổi:

```text
Range shard key:
  + target range queries tốt
  + dữ liệu gần nhau theo key có locality
  - insert monotonically increasing có thể hot
  - key tần suất cao có thể thành range khó chia
```

Không nên chọn `createdAt: 1` cho một event stream rất lớn **chỉ vì dashboard thường lọc theo ngày** mà không đo insert distribution và khả năng gánh tải của shard nhận dữ liệu mới.

## 8. Hashed sharding: phá hướng tăng để phân tán khóa

Hashed shard key lưu/định tuyến theo **hash được MongoDB tính từ giá trị key**. Khi các ID tăng liên tục nhưng khác nhau, giá trị hash có xu hướng phân bố trên miền khác thứ tự gốc.

Ví dụ:

```javascript
sh.shardCollection(
  "shop.orders",
  { orderNo: "hashed" }
);
```

Minh họa:

```text
orderNo      hash(orderNo)      Shard/key range
-------      -------------      ---------------
100001       H71                 A
100002       H08                 C
100003       H92                 B
100004       H34                 A
100005       H59                 C
...
```

Các ký hiệu H71/H08 chỉ là ví dụ, không phải hash thực tế. Điểm cốt lõi: hai `orderNo` gần nhau không còn buộc phải nằm cạnh nhau trong không gian hash.

### 8.1. Khi nào hashed shard key phù hợp?

Đặc biệt hữu ích khi:

- Field có **nhiều giá trị distinct**;
- Mỗi giá trị không tạo tải quá lớn riêng lẻ;
- Giá trị mới tăng hoặc giảm đơn điệu;
- Workload thường tìm **equality** trên field đó;
- Không bắt buộc tối ưu mạnh range scans trên chính field shard key.

Ví dụ:

```javascript
db.orders.findOne({
  orderNo: NumberLong("12004567")
});
```

Với hashed shard key trên `orderNo`, router có thể tính hash của một giá trị chính xác để target shard tương ứng theo metadata.

### 8.2. Hashed sharding không giữ locality của khoảng gốc

Query:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

không tương ứng với một đoạn hash liên tục. MongoDB không thể dùng chính trật tự hash để target vùng giá trị `orderNo` gốc giống range sharding.

Hệ quả có thể là truy vấn range cần **scatter-gather qua nhiều shard**. Tùy các filter khác và topology, planner có thể có cách tối ưu riêng, nhưng không nên giả định hashed sharding vẫn giữ khả năng prune range theo `orderNo`.

### 8.3. Hash không giải quyết hot key duy nhất

Nếu một tỷ document có:

```javascript
{ tenantId: "TENANT-HOT" }
```

thì:

```javascript
{ tenantId: "hashed" }
```

vẫn chỉ băm `"TENANT-HOT"` thành **một giá trị hash**. Hash giúp phân tán **nhiều giá trị khóa khác nhau**, không tự chia một giá trị lặp lại thành nhiều giá trị.

Vì vậy:

> **Hashed key tốt để phá monotonicity của nhiều khóa phân biệt; không tốt để cứu một khóa có frequency cực cao mà không có thêm chiều phân biệt.**

### 8.4. Hash không phải giải pháp cho mọi loại field

Một số giới hạn cần biết:

- Hashed index không phải B-tree index có thể range scan theo giá trị gốc;
- Hashed index không cung cấp unique constraint như unique B-tree index;
- Không dùng array field làm hashed key vì giới hạn multikey hashed index;
- Numeric hashing có quy tắc chuyển đổi trước khi hash, cần tránh giả định mọi giá trị thập phân khác nhau đều cho hash khác nhau;
- Một field ít distinct vẫn ít distinct sau hashing.

Hashed sharding là công cụ phân phối, **không phải phép mã hóa bảo mật** hay lời hứa cân bằng tải tuyệt đối.

## 9. Compound shard key: phối hợp locality và độ phân tán

Một shard key có thể gồm nhiều thành phần.

Ví dụ:

```javascript
{ tenantId: 1, orderNo: 1 }
```

hoặc một compound hashed shard key trong phiên bản hỗ trợ:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

### 9.1. Tại sao thêm field có thể làm giảm frequency của khóa?

Giả sử 70% document thuộc tenant A:

```javascript
{ tenantId: "A" }
```

Nếu shard key chỉ có tenantId, giá trị A rất nóng.

Thêm `orderId`:

```javascript
{ tenantId: "A", orderId: "ORD-1001" }
{ tenantId: "A", orderId: "ORD-1002" }
{ tenantId: "A", orderId: "ORD-1003" }
```

Giờ các **giá trị compound shard key** khác nhau dù cùng tenant. Điều này tạo thêm khả năng phân chia dữ liệu trong một tenant nếu phân vùng/balancing tạo và phân phối các key ranges phù hợp.

Nhưng **thêm một suffix vào key không bảo đảm tự phân tán tức thì**: phụ thuộc việc collection được shard/refine/reshard, chunk metadata, index, lượng dữ liệu và khả năng balancer thực hiện split/migration trong phiên bản triển khai.

### 9.2. Compound ranged key `{ tenantId: 1, createdAt: 1 }`

Lợi ích:

- Có thể cung cấp locality cho từng tenant;
- Query với tenantId equality và khoảng thời gian có thể target vùng phù hợp;
- Tốt cho một số batch job/retention theo tenant và thời gian.

Nhược điểm:

- `createdAt` tăng trong mỗi tenant;
- Nếu tenant A chiếm 70% write traffic, các insert mới của A có thể tập trung tại một vùng biên của tenant A;
- Timestamp trùng nhiều lần có thể tạo frequency cao ở một cặp `(tenantId,createdAt)`;
- Query toàn hệ thống chỉ theo thời gian, không có tenantId, có thể phải fan-out.

### 9.3. Compound hashed key `{ tenantId: 1, orderId: "hashed" }`

Ý tưởng:

```javascript
sh.shardCollection(
  "shop.orders",
  { tenantId: 1, orderId: "hashed" }
);
```

Các document thuộc tenant A vẫn có prefix tenantId, nhưng thành phần `orderId` được băm để phá hướng tăng và tạo nhiều giá trị compound key trong tenant.

Tuy nhiên, cần đánh giá:

- Query bằng **cả tenantId và orderId** có thể target tốt.
- Query chỉ theo **tenantId** có thể liên quan tới nhiều ranges/chunks/shards, vì một tenant đã được trải theo nhiều giá trị orderId hash.
- Query theo tenantId và **khoảng createdAt** không tự được target hiệu quả bởi shard key thiếu createdAt, dù có index cục bộ phù hợp.
- Nếu orderId không distinct hoặc có một giá trị rất nóng, hash suffix không loại bỏ hot key.

Cách này đặc biệt đáng cân nhắc khi nhu cầu ghi phân tán trong tenant lớn quan trọng hơn việc mọi dữ liệu một tenant phải nằm tại một shard.

### 9.4. Thứ tự field quan trọng

So sánh:

```javascript
{ tenantId: 1, orderId: "hashed" }
```

và:

```javascript
{ orderId: "hashed", tenantId: 1 }
```

Cả hai có thể phân biệt các order, nhưng khả năng target query **chỉ có tenantId** khác nhau vì thành phần đầu của shard key thay đổi.

Đừng quyết định thứ tự field theo thói quen “tenant luôn đứng trước” hoặc “hashed luôn đứng trước”. Hãy xem:

1. Filter thực tế chứa field nào;
2. Tỷ lệ query theo tenant-only, order-only, tenant+order;
3. Tập nào cần locality/zone;
4. Số chunk có thể phân phối của tenant lớn;
5. Nhu cầu uniqueness và ràng buộc của compound shard key.

## 10. Đánh đổi giữa shard-key targeting và index cục bộ

Giả sử ứng dụng có ba API:

```javascript
// API A: tìm một đơn hàng chính xác.
db.orders.findOne({
  tenantId: "TENANT-A",
  orderId: "ORD-000123"
});

// API B: lịch sử đơn hàng của một tenant theo thời gian.
db.orders.find({
  tenantId: "TENANT-A",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
}).sort({ createdAt: -1, _id: -1 }).limit(50);

// API C: báo cáo toàn hệ thống về đơn hàng PAID.
db.orders.find({
  status: "PAID",
  createdAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-04-01T00:00:00Z")
  }
});
```

Một shard key `{ tenantId: 1, orderId: "hashed" }` có thể đặc biệt tốt cho **API A**, nhưng API B có thể fan-out trên các chunk của tenant, và API C có thể phải đọc trên nhiều shard.

Bạn vẫn có thể tạo local indexes:

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: -1,
  _id: -1
});

db.orders.createIndex({
  status: 1,
  createdAt: -1
});
```

Index này có thể giúp **thực thi nhanh trên từng shard**, nhưng không thay đổi việc một truy vấn có shard key predicate hay không. Một query fan-out với local index hiệu quả có thể vẫn hợp lý nếu nó không chạy nhiều; một endpoint p99 quan trọng fan-out mọi lần có thể gây áp lực lớn lên cluster.

### 10.1. Một shard key không thể tối ưu đồng thời mọi query

Trong thực tế, sharding thường buộc chọn những **query patterns quan trọng nhất** để định tuyến tốt, còn các query khác dựa vào local indexes, materialized views, analytics store hoặc kiến trúc đọc riêng.

Đây không phải dấu hiệu thiết kế thất bại; nó là hệ quả của việc một collection chỉ có **một shard key hiện hành** tại một thời điểm.

## 11. Không nhầm shard key với unique index

Một shard key có thể có cardinality cao nhưng không nhất thiết **unique**.

Ví dụ:

```javascript
{ tenantId: 1 }
```

là shard key hợp lệ về mặt khái niệm dù mỗi tenant có nhiều document, nhưng khả năng chia nhỏ/hot key có vấn đề.

Ngược lại, một application business key duy nhất:

```javascript
{ orderId: 1 }
```

có thể unique, nhưng nếu được cấp tăng tuần tự và dùng range sharding thì vẫn tạo hướng ghi đơn điệu.

### 11.1. Unique indexes trên sharded collection có ràng buộc

MongoDB áp dụng quy tắc riêng cho **unique index trên sharded collection**: thường cần tương thích với shard key dưới dạng prefix theo các giới hạn cụ thể, và hashed indexes không hỗ trợ `unique: true` như B-tree unique index.

Ví dụ nghiệp vụ yêu cầu unique `orderId` **trên toàn hệ thống**, nhưng shard key `{ tenantId: 1, createdAt: 1 }` không bao gồm orderId ở prefix. Không được mặc định rằng:

```javascript
db.orders.createIndex(
  { orderId: 1 },
  { unique: true }
);
```

sẽ cưỡng chế tính duy nhất trên toàn sharded cluster theo cách mong muốn.

Cần kiểm tra ràng buộc unique index với shard key, giới hạn về `_id` khi `_id` không thuộc shard key, và có thể chọn thiết kế định danh hoặc registry riêng nếu cần tính duy nhất toàn cục.

**Shard key selection và unique constraint là hai yêu cầu phải thiết kế cùng lúc**, không đợi sau khi shard xong mới phát hiện không tạo được unique index cần thiết.

### 11.2. ID tăng nhưng unique không nhất thiết là shard key tốt

Một khóa auto-increment rất tiện cho uniqueness và sort, nhưng có tính monotonicity. Có thể giữ B-tree unique index trên một field (nếu các quy tắc sharded uniqueness cho phép) trong khi chọn một shard key khác để phân phối, hoặc dùng compound key phù hợp.

Giải pháp cụ thể phải xét topology và phạm vi unique; không có công thức “chỉ cần đổi sang hashed là giữ nguyên mọi unique constraint”.

## 12. Shard key bị thiếu, null hoặc kiểu không đồng nhất

Một collection có thể chứa:

```javascript
{ _id: 1, tenantId: "A", orderId: "O1" }
{ _id: 2, tenantId: null, orderId: "O2" }
{ _id: 3, orderId: "O3" }
{ _id: 4, tenantId: 1001, orderId: "O4" }
```

Ở đây, `tenantId` có String, Number, null và missing. Những giá trị này có thể gây:

- Phân phối không mong muốn;
- Query routing khó dự đoán theo nghĩa nghiệp vụ;
- Nhiều record tập trung quanh những giá trị thiếu/null;
- Ứng dụng tưởng rằng `"1001"` và `1001` là cùng tenant dù BSON type khác;
- Migration shard key khó vì dữ liệu không thống nhất.

Trước khi chọn shard key, nên:

1. Thống kê BSON type bằng `$type`;
2. Kiểm tra tỷ lệ missing/null;
3. Chuẩn hóa kiểu và định dạng;
4. Ràng buộc validation trên write path;
5. Xác nhận mọi nhà sản xuất dữ liệu (API, import, ETL) dùng cùng schema.

Một shard key không phải công cụ tự sửa chất lượng dữ liệu.

## 13. Sự khác biệt giữa số document và kích thước document

Giả sử có hai loại đơn hàng:

```text
Tenant A: 100.000 document, mỗi document ~1 KB
Tenant B: 100.000 document, mỗi document ~50 KB
```

Cả hai có **cùng số document** nhưng Tenant B có thể chiếm khoảng 50 lần số byte dữ liệu gốc, chưa kể index và storage overhead.

Nếu đánh giá shard key chỉ theo document count, một shard chứa Tenant B có thể đầy disk trước các shard khác dù số record rất cân bằng.

Tương tự, một record có array rất lớn có thể có chi phí update/replication cao hơn một record nhỏ.

Do đó, cần quan sát:

- Số document theo shard/key;
- Tổng bytes lưu trữ;
- Dung lượng index;
- Phân bố kích thước document (p50/p95);
- Write/update rates;
- Working set trong RAM;
- I/O và CPU của từng shard.

**Mục tiêu của sharding là phân phối tài nguyên và tải thực, không phải chỉ phân phối số dòng.**

## 14. Shard key và giới hạn chia chunk/range

MongoDB phân chia phạm vi shard key thành các đơn vị metadata có thể được phân bổ, di chuyển hoặc cân bằng giữa các shard theo cơ chế/version phù hợp.

Khi dữ liệu tăng:

- Một range có thể cần được chia thành những range nhỏ hơn nếu có các điểm chia hợp lệ;
- Balancer có thể di chuyển range/chunk để cải thiện phân bố;
- Metadata có thể thay đổi theo resharding/migration;
- Những range chứa quá nhiều document có **cùng giá trị shard key** có thể khó hoặc không thể chia nhỏ ở ranh giới giá trị đó.

### 14.1. Range không thể chia: một giá trị xuất hiện quá nhiều

Giả sử một triệu document có:

```javascript
{ tenantId: "TENANT-HOT" }
```

và shard key chỉ là `tenantId`.

Thực tế không có nhiều giá trị shard key để MongoDB cắt vùng chứa `TENANT-HOT` thành các range không chồng nhau nhưng vẫn phân biệt được document bằng chính tenantId. Đây là tình huống **indivisible/unsplittable range** về mặt khóa.

Những range lớn, khó chia hoặc khó migrate có thể dẫn tới mất cân bằng và những hạn chế quản trị; các cơ chế, thuật ngữ như jumbo chunk và hành vi balancer khác theo phiên bản MongoDB.

**Không giả định MongoDB tự tạo thêm shard key value** hay cứ tăng số shard thì một tenant duy nhất sẽ được trải đều.

### 14.2. Tăng chunk size có giải quyết hot key?

Tăng chunk size có thể thay đổi số lượng/mức độ migration nhưng không tạo thêm tính phân biệt cho shard key. Với một hot key đơn lẻ, vấn đề cốt lõi là **không có ranh giới chia hữu ích trong không gian khóa**.

Ngược lại, giảm chunk size một cách tùy tiện có thể tăng metadata/migration overhead mà vẫn không chia được những document có cùng giá trị key.

### 14.3. Balancer không bảo đảm cân bằng request/giây

Balancer chủ yếu làm việc với phân bố vùng dữ liệu theo các quy tắc, giới hạn và chính sách của cluster. Nếu shard A có 20% dữ liệu nhưng nhận 80% traffic cho một key nóng, việc cân bằng dung lượng chưa chắc làm đều CPU/IOPS.

Để phân phối **lưu lượng**, shard key phải cho phép những request hoặc document được chia theo những giá trị khác nhau, đồng thời application query shape phải tận dụng khả năng này.

## 15. Thiết kế cho workload theo tenant

Đa số hệ thống SaaS có field `tenantId`. Vì vậy, “shard theo tenantId” nghe rất tự nhiên.

### 15.1. Lợi ích của tenant-oriented shard key

Nếu phần lớn endpoint luôn có:

```javascript
{ tenantId: "TENANT-A" }
```

thì một shard key có tenant prefix có thể giúp `mongos` giới hạn những vùng shard-key liên quan.

Lợi ích có thể gồm:

- Query có ranh giới tenant rõ;
- Một số truy vấn tenant-only có locality tốt;
- Khả năng áp dụng zone/range chính sách theo tenant nếu thiết kế phù hợp;
- Bảo trì, di chuyển hoặc phân tích theo tenant dễ mô hình hóa hơn.

### 15.2. Rủi ro hot tenant

Nếu một tenant có 80% write traffic hoặc chứa hàng trăm GB, `{ tenantId: 1 }` là lựa chọn nguy hiểm: tenant đó chỉ có một giá trị shard key.

### 15.3. Ba phương án để so sánh

**Phương án A — `{ tenantId: 1 }`:**

- Đơn giản, tập trung theo tenant;
- Query tenant-only có thể target rõ;
- Không chia một tenant khổng lồ thành nhiều shard-key values.

**Phương án B — `{ tenantId: 1, orderNo: 1 }`:**

- Phân biệt nhiều order trong tenant;
- Có locality theo tenant + khoảng orderNo;
- Nếu orderNo tăng đều trong tenant, vẫn có hot range cho tenant lớn.

**Phương án C — `{ tenantId: 1, orderId: "hashed" }`:**

- Tạo nhiều compound key và phá thứ tự tăng của orderId;
- Có tiềm năng phân tán write-heavy tenant lớn;
- Query tenant-only có thể liên quan nhiều shard, truy vấn theo thời gian không được hash tự hỗ trợ range.

Chọn phương án dựa vào **quy mô tenant lớn nhất**, khối lượng writes của tenant đó và tỷ trọng query đọc theo tenant-only so với tenant+order.

## 16. Thiết kế cho event/time-series workload

Giả sử hệ thống thu thập sự kiện:

```javascript
{
  deviceId: "DEVICE-001",
  eventId: "EV-1001",
  eventAt: ISODate("2026-03-01T09:00:00Z"),
  measurement: 42.7
}
```

Những query phổ biến:

```javascript
// Lịch sử một thiết bị trong một khoảng thời gian.
db.events.find({
  deviceId: "DEVICE-001",
  eventAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-03-02T00:00:00Z")
  }
});

// Tìm một sự kiện chính xác.
db.events.findOne({
  eventId: "EV-1001"
});

// Báo cáo mọi thiết bị theo thời gian.
db.events.find({
  eventAt: {
    $gte: ISODate("2026-03-01T00:00:00Z"),
    $lt: ISODate("2026-03-02T00:00:00Z")
  }
});
```

### 16.1. Shard theo `eventAt` ranged

Ưu điểm: khoảng thời gian có thể có locality.

Nhược điểm: hầu hết event mới thuộc vùng thời gian mới nhất -> có thể **hot insert shard**. Nếu dữ liệu có burst lớn, balancer không nhất thiết kịp giảm áp lực lên range mới.

### 16.2. Shard theo `deviceId` hashed

Ưu điểm: khi có nhiều thiết bị với lượng ghi tương đối đều, hash deviceId có thể phân phối thiết bị sang nhiều shard; truy vấn equality một deviceId có thể target tốt.

Nhược điểm: một thiết bị cực nóng vẫn là một hash duy nhất; query toàn bộ thiết bị theo thời gian có thể scatter.

### 16.3. Compound key theo device và thời gian

Ví dụ:

```javascript
{ deviceId: 1, eventAt: 1 }
```

có thể hỗ trợ locality cho lịch sử một thiết bị, nhưng một thiết bị gửi event liên tục vẫn có vùng biên tăng trong nhóm device đó.

Một phương án thêm `eventId` hoặc bucket có thể phân tán hơn nhưng làm lịch sử thiết bị phải truy cập nhiều range.

### 16.4. Time-series collection có quy tắc riêng

MongoDB **time-series collections** có những ràng buộc đặc biệt về cách tổ chức bucket nội bộ, metaField/timeField và shard key tùy phiên bản. Không sao chép trực tiếp quy tắc của regular collection sang time-series collection mà không kiểm tra tài liệu phiên bản đang dùng.

Trước khi quyết định, hãy làm rõ đây là **regular collection chứa event** hay một MongoDB time-series collection thực sự.

## 17. Thiết kế cho ID tăng dần

Nhiều ứng dụng dùng:

```javascript
{
  orderNo: NumberLong("12004567")
}
```

`orderNo` thường dùng để:

- Tra cứu một đơn hàng;
- Hiển thị mã dễ đọc;
- Phân trang theo ID;
- Xuất các đơn hàng trong một khoảng;
- Gán định danh duy nhất.

### 17.1. Nếu workload chủ yếu là equality

Nếu 95% query tìm một `orderNo` cụ thể và insert tăng đều, shard key hashed theo orderNo có thể rất phù hợp:

```javascript
{ orderNo: "hashed" }
```

Nó giúp phân tán khóa tăng và vẫn cho equality targeting.

### 17.2. Nếu workload chủ yếu là range scan

Nếu hệ thống liên tục chạy:

```javascript
db.orders.find({
  orderNo: {
    $gte: NumberLong("12000000"),
    $lt: NumberLong("12100000")
  }
});
```

range shard key có lợi thế locality. Nhưng phải đánh giá hot insert ở biên và khả năng thay đổi thiết kế phân vùng/ingestion.

### 17.3. Không giả định ObjectId là hoàn toàn ngẫu nhiên

BSON ObjectId có thành phần thời gian nên các giá trị được tạo trong thời gian gần nhau thường có tính tăng theo thứ tự so sánh, dù không đồng nghĩa một sequence tuyệt đối xuyên tất cả client.

Do đó, dùng `{ _id: 1 }` trong ranged sharding có thể có write hot range với những workload tạo ObjectId liên tục. Nếu muốn phân phối theo ID, cần kiểm tra tính chất thực tế của ID và cân nhắc hashed shard key khi phù hợp.

### 17.4. UUID hoặc random ID cũng cần đánh giá

Một ID có vẻ ngẫu nhiên có thể giúp phá monotonicity, nhưng vẫn cần:

- Cardinality và collision policy;
- Query equality có mang shard key không;
- Kiểu BSON nhất quán;
- Chi phí index/storage;
- Uniqueness;
- Khả năng debug và thứ tự phân trang.

Không suy ra “random ID luôn tốt hơn tăng dần” nếu phần lớn workload cần quét ranges theo ID hoặc dữ liệu có locality quan trọng.

## 18. Thu thập bằng chứng từ dữ liệu

Không nên chọn shard key chỉ dựa trên cảm giác field nào “có vẻ đều”. Trước tiên cần khảo sát dataset đại diện.

Ví dụ một collection thử `shardKeyLab`:

```javascript
// CHỈ CHẠY TRÊN DB HỌC TẬP.
// drop() xóa collection nếu đã tồn tại.
db.shardKeyLab.drop();

const totalDocs = 100000;
const batchSize = 1000;
const baseTime = Date.parse("2026-01-01T00:00:00Z");

let seed = 259;

function randomUnit() {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
  return seed / 4294967296;
}

let batch = [];

for (let i = 0; i < totalDocs; i++) {
  const r = randomUnit();

  // 65% orders thuộc một tenant rất lớn.
  const tenantId = r < 0.65
      ? "TENANT-HOT"
      : "TENANT-" + (1 + Math.floor(randomUnit() * 1000));

  batch.push({
    tenantId: tenantId,
    orderNo: NumberLong(String(i + 1)),
    orderId: "ORD-" + String(i + 1).padStart(8, "0"),
    customerId: "CUS-" + String(i % 20000),
    status: i % 10 < 7 ? "PAID" : "PENDING",
    createdAt: new Date(baseTime + i * 1000),
    total: NumberDecimal(String((i % 5000) + 100))
  });

  if (batch.length === batchSize) {
    db.shardKeyLab.insertMany(batch, { ordered: false });
    batch = [];
  }
}

if (batch.length > 0) {
  db.shardKeyLab.insertMany(batch, { ordered: false });
}

print("Inserted: " + db.shardKeyLab.countDocuments({}));
```

Bộ dữ liệu này có chủ đích:

- `tenantId` lệch mạnh về một tenant;
- `orderNo` và `orderId` gần như unique;
- `orderNo` tăng dần;
- `createdAt` tăng theo thời gian;
- `status` ít giá trị.

Dữ liệu test là synthetic, **không thay thế hoàn toàn production**: document size, truy vấn/giây, network topology và các hot keys thực có thể khác.

### 18.1. Đo frequency theo tenant

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId",
      documentCount: { $sum: 1 }
    }
  },
  { $sort: { documentCount: -1 } },
  { $limit: 10 }
]);
```

Kết quả sẽ cho thấy `TENANT-HOT` chiếm tỷ trọng lớn. Không cần “biết trước” dữ liệu có đều; phải quan sát.

### 18.2. Đếm distinct values

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId"
    }
  },
  {
    $count: "distinctTenantCount"
  }
]);
```

Tương tự với `orderId`, `orderNo`, `status`, có thể so sánh số giá trị phân biệt. Với tập cực lớn, aggregation chính xác này có thể tốn nhiều tài nguyên; cần dùng công cụ phân tích/sample và thời điểm phù hợp.

### 18.3. Tìm giá trị phổ biến nhất

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Nếu `PAID` có hơn 70% record, shard key `{ status: 1 }` không mang lại không gian phân phối tốt.

### 18.4. Đánh giá document size theo tenant

```javascript
db.shardKeyLab.aggregate([
  {
    $group: {
      _id: "$tenantId",
      docs: { $sum: 1 },
      bytesApprox: { $sum: { $bsonSize: "$$ROOT" } }
    }
  },
  { $sort: { bytesApprox: -1 } },
  { $limit: 10 }
]);
```

`$bsonSize` đo kích thước BSON của document tại bước pipeline tương ứng, **không** bao gồm chính xác mọi overhead storage/compression/index. Nhưng nó giúp thấy trường hợp một tenant có ít document mà payload rất lớn.

## 19. Đánh giá monotonicity bằng quan sát thực tế

Monotonicity không chỉ được xác định từ tên field. Cần xem các giá trị xuất hiện theo **thứ tự insert/thời gian ghi**.

Ví dụ, tạo một danh sách các giá trị mới nhất:

```javascript
db.shardKeyLab.find(
  {},
  {
    _id: 0,
    orderNo: 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1 })
.limit(20);
```

Trong dataset này, `orderNo` tăng cùng `createdAt`. Nhưng trên production, các event có thể đến muộn, retry, backfill hoặc nhập dữ liệu lịch sử, khiến xu hướng tăng không tuyệt đối.

### 19.1. Dữ liệu backfill có thể thay đổi pattern

Một hệ thống event bình thường chỉ thêm timestamp hiện tại, nhưng job backfill thêm 100 triệu event của năm trước. Khi đó shard key ranged trên `eventAt` có thể phân tán tải tới **vùng thời gian cũ**, không còn chỉ là vùng cuối.

Vì thế, thiết kế cần tính đến:

- Streaming data;
- Bulk backfill;
- Retry/out-of-order events;
- Dữ liệu theo mùa;
- Kế hoạch archive/purge;
- Tenant onboarding và migration.

### 19.2. Một chỉ số monotonicity không thay thế workload analysis

Giả sử 90% insert theo `orderNo` tăng, 10% là backfill ngẫu nhiên. Tính chất tổng thể vẫn có thể đủ để tạo hot shard. Ngược lại, field tăng đối với từng user nhưng toàn bộ hệ thống có hàng triệu user phân tán tốt có thể không có một hot range toàn cục giống một sequence duy nhất.

Phải quan sát **write distribution trên miền shard key**, không chỉ tỷ lệ các cặp giá trị liền nhau tăng.

## 20. Phân tích query patterns: field xuất hiện ở đâu?

Một shard key nên được đánh giá cùng tập query quan trọng.

Ví dụ thống kê từ ứng dụng:

| Query pattern | Tỷ lệ request | Trường lọc | Kết quả mong muốn |
|---|---:|---|---|
| Tìm đơn hàng chính xác | 55% | tenantId + orderId | Targeted, latency thấp |
| Lịch sử một khách | 25% | tenantId + customerId + createdAt | Có thể phân trang theo thời gian |
| Báo cáo tenant tháng này | 12% | tenantId + createdAt | Query theo range |
| Thống kê toàn hệ thống | 5% | status + createdAt | Chấp nhận analytic fan-out |
| Tìm lỗi reconciliation | 3% | orderNo | Targeted nếu có key phù hợp |

Bảng số liệu là minh họa. Trong sản phẩm thật, cần lấy từ logs/telemetry được thu thập đúng quyền, có sampling và bảo vệ dữ liệu nhạy cảm.

### 20.1. Câu hỏi cần hỏi về từng query

1. Filter có **đầy đủ shard key** không?
2. Nếu compound key, có **prefix** phù hợp không?
3. Toán tử là equality hay range?
4. Query có kèm sort/pagination mà index cục bộ hỗ trợ không?
5. Query có cần đọc nhiều tenant hoặc nhiều khoảng thời gian?
6. Endpoint này chạy bao nhiêu lần/giây?
7. Kích thước kết quả lớn hay nhỏ?
8. Có hot tenant/user làm thay đổi phân bố request không?

### 20.2. Targeting không phải lúc nào cũng “một shard”

Ngay cả với một shard key phù hợp, query range hoặc partial-prefix filter có thể chạm **nhiều chunk nằm trên nhiều shard**. Đó vẫn có thể là một query được target tốt nếu chỉ liên quan một số vùng nhỏ, thay vì toàn bộ cluster.

Hãy đo **số shard bị truy vấn và lượng dữ liệu trên mỗi shard**, không chỉ ghi nhãn nhị phân “targeted” hoặc “scatter”.

### 20.3. Scatter-gather có chi phí gì?

Một query không có shard key filter có thể cần:

```text
             mongos
          /     |      \
      Shard A Shard B Shard C
        |        |       |
      results  results results
          \     |      /
          merge / sort / limit
```

Chi phí gồm:

- Network fan-out tới nhiều shard;
- CPU/IOPS và query execution trên mỗi shard;
- Truyền partial results;
- Gộp/sort ở router hoặc shard theo execution plan;
- Latency của shard chậm nhất;
- Tăng fan-out khi thêm shard.

Scatter-gather không tuyệt đối sai: với báo cáo toàn hệ thống chạy định kỳ, nó có thể được chấp nhận. Nhưng nếu endpoint tương tác có tần suất cao, đó là tín hiệu shard key/query design cần xem lại.

## 21. Sử dụng analyzeShardKey và query sampling khi được hỗ trợ

MongoDB ở các phiên bản hỗ trợ có các công cụ như **`analyzeShardKey`** để phân tích tính chất shard key ứng viên và, khi có query sampling phù hợp, đánh giá phân bố truy vấn đọc/ghi.

Ví dụ ý tưởng:

```javascript
db.adminCommand({
  analyzeShardKey: "shop.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

Một ứng viên khác:

```javascript
db.adminCommand({
  analyzeShardKey: "shop.orders",
  key: { orderId: "hashed" }
});
```

**Quan trọng:** Khả năng chạy lệnh, yêu cầu index, trường kết quả và tính năng query sampling phụ thuộc phiên bản server, deployment và quyền. Không coi các ví dụ là lệnh chắc chắn chạy trên mọi phiên bản MongoDB.

### 21.1. Những thông tin cần quan sát

Tùy phiên bản và dữ liệu/thiết lập sampling, các phân tích có thể bao gồm:

- Số document;
- Số shard key values phân biệt;
- Những giá trị thường gặp nhất;
- Đánh giá monotonicity;
- Đặc điểm phân phối đọc;
- Đặc điểm phân phối ghi;
- Tỷ lệ truy vấn có thể target một shard/nhiều shard;
- Mức độ tập trung tải.

Không phải mọi trường đều luôn có mặt. Chẳng hạn phân tích workload đọc/ghi cần thông tin query samples được thu thập đủ đại diện; không có samples thì không được suy diễn thành “không có query fan-out”.

### 21.2. Query sampling cần kế hoạch

Ở phiên bản hỗ trợ, có thể cấu hình query analyzer để lấy mẫu workload. Một ví dụ về hình thức lệnh:

```javascript
db.adminCommand({
  configureQueryAnalyzer: "shop.orders",
  mode: "full",
  samplesPerSecond: 10
});
```

Lệnh này chỉ mang tính hướng dẫn; cấu hình sampling phải tuân thủ quy định của phiên bản/cluster và yêu cầu quyền. Trong production, sampling có chi phí và có thể thu metadata/query information nhạy cảm, nên cần:

1. Chọn cửa sổ thời gian đại diện;
2. Bao gồm giờ cao điểm và batch job;
3. Ghi lại tỷ lệ sampling;
4. Xác định cách bảo vệ, lưu giữ và xóa dữ liệu mẫu;
5. Dừng/giảm sampling sau khi thu đủ thông tin.

Đừng bật full sampling không giới hạn chỉ để có một con số phân bố đẹp.

### 21.3. Kết quả phân tích không thay thế thử nghiệm tải

Một shard key có cardinality cao theo `analyzeShardKey` vẫn có thể thua trong ứng dụng nếu:

- Read workload chủ yếu thiếu shard key;
- Một user/tenant chịu cực nhiều request;
- Compound key thiếu locality cho range;
- Dung lượng index quá lớn;
- Balancer/migration chịu áp lực;
- Query planner trên từng shard không tối ưu.

Cần kết hợp **đặc trưng khóa + workload + benchmark**.

## 22. So sánh ứng viên bằng ma trận chấm điểm có căn cứ

Thay vì chọn theo một metric, lập bảng cho các ứng viên.

Ví dụ workload SaaS có tenant lớn:

| Tiêu chí | `{tenantId:1}` | `{orderNo:1}` | `{orderNo:"hashed"}` | `{tenantId:1,orderId:"hashed"}` |
|---|---|---|---|---|
| Cardinality | Trung bình/cao | Cao | Cao | Rất cao theo tổ hợp |
| Hot key risk | **Cao** nếu có tenant lớn | Thấp nếu orderNo unique | Thấp nếu orderNo unique | Thấp hơn tenant-only nếu orderId đa dạng |
| Monotonic insert risk | Tùy tenant distribution | **Cao** | Thấp hơn | Thấp hơn trên phần hashed |
| Equality order lookup | Cần biết tenant | Tốt với orderNo | Tốt với orderNo | Tốt khi có tenant+order |
| Range orderNo | Không được key hỗ trợ trực tiếp | Có locality | **Mất locality theo hash** | Không có orderNo range locality |
| Tenant-only reads | Có thể thuận lợi | Thường fan-out | Thường fan-out | Có thể nhiều shard trong tenant |
| Unique constraints | Cần xem quy tắc | Cần xem quy tắc | Hashed index không unique | Cần xem compound hashed rules |
| Hot tenant writes | Rủi ro | Có thể phân tán theo orderNo nhưng monotonic | Có thể phân tán toàn cluster | Có tiềm năng phân tán trong tenant |

Bảng là **đánh giá sơ bộ theo tính chất khóa**, không phải benchmark đã đo. Không gán điểm tuyệt đối 10/10 mà không có dữ liệu thực.

### 22.1. Dùng trọng số theo SLO

Ví dụ:

```text
Read latency p95 order lookup:       trọng số cao
Write throughput during peak:       trọng số cao
Monthly analytics fan-out:          trọng số thấp
Per-tenant locality:                trọng số trung bình
Operational simplicity:             trọng số trung bình
```

Nếu 80% nghiệp vụ quan trọng là ghi đơn hàng, một hashed key có thể hợp lý dù báo cáo range chạy đêm phải fan-out.

Nếu ứng dụng là công cụ analytics quét dữ liệu theo thời gian liên tục, cần ưu tiên query locality hơn, và có thể phải dùng một mô hình lưu trữ/collection phụ cho analytics.

## 23. Zone sharding: phân phối có chủ đích thay vì hoàn toàn đều

Một số hệ thống cần lưu dữ liệu theo vùng vì:

- Yêu cầu chủ quyền dữ liệu;
- Độ trễ truy cập;
- Hợp đồng khách hàng;
- Phân tầng lưu trữ nóng/lạnh;
- Quy định vận hành.

MongoDB hỗ trợ **zone sharding** trong các điều kiện phù hợp, gắn những shard-key ranges với các zone.

Ví dụ ý tưởng:

```text
Tenant IDs thuộc nhóm EU -> Zone EU
Tenant IDs thuộc nhóm AP -> Zone AP
```

Nếu chọn shard key tạo locality theo region/tenant, việc định nghĩa zone ranges có thể tự nhiên hơn.

Nhưng zone constraints **giới hạn nơi chunk có thể được đặt**, nên cân bằng tải không còn tự do trên toàn bộ cluster. Nếu Zone EU chỉ có một shard hoặc phần lớn traffic tập trung vào một tenant trong EU, thêm shard vào Zone AP không giúp giảm tải EU.

### 23.1. Hashed key và zone policies

Một shard key hashed có thể phân tán khóa trên miền hash, nhưng nếu doanh nghiệp cần mọi document của một tenant ở một vùng cố định, thiết kế hashed key phải được đánh giá với khả năng xác định zone ranges và quy tắc prefix/compound key phù hợp.

Không tự giả định “hash phân bố đều trên toàn cluster” sẽ đồng thời đáp ứng **data residency** và locality theo vùng.

### 23.2. Đánh đổi tính khả dụng vùng

Gắn một tenant vào zone chỉ có một failure domain có thể giảm latency hoặc tuân thủ residency, nhưng làm giảm khả năng phục vụ tenant khi vùng đó gặp sự cố. Shard key, zones và replica set placement phải được thiết kế **cùng nhau**.

## 24. Chọn shard key cho truy vấn theo thời gian

Có một căng thẳng phổ biến:

- **Ghi:** event mới luôn có timestamp lớn, cần phân tán.
- **Đọc:** người dùng thường xem “24 giờ gần nhất”, cần locality theo time range.

Nếu chọn `{ createdAt: 1 }` ranged, read range tốt nhưng insert có thể hot.

Nếu chọn `{ createdAt: "hashed" }`, insert có thể phân tán khi timestamp có đủ distinct values, nhưng range reads có thể scatter; timestamp có nhiều giá trị trùng còn tạo hot hash value.

Nếu chọn `{ deviceId: "hashed" }`, insert của nhiều thiết bị có thể phân tán, nhưng báo cáo toàn bộ thiết bị theo thời gian cần fan-out.

Không có shard key hoàn hảo cho cả hai. Một số kiến trúc có thể:

1. Chọn shard key phù hợp **ingestion throughput**;
2. Dùng secondary indexes trên mỗi shard để giảm chi phí cục bộ;
3. Tính sẵn aggregate theo ngày/giờ vào collection khác;
4. Di chuyển lịch sử sang hệ thống analytics phù hợp;
5. Thiết kế zones/retention theo quy tắc dữ liệu.

### 24.1. Tần suất timestamp cũng quan trọng

Nếu một hệ thống tạo 100.000 event mỗi giây nhưng `createdAt` được làm tròn tới giây, trong mỗi giây có thể có **100.000 document cùng timestamp**.

Ngay cả hashed shard key trên `createdAt` vẫn băm những document đó ra **một hash value**. High write concurrency với độ phân giải timestamp thấp tạo vấn đề frequency.

Có thể dùng eventId unique hoặc compound key có thành phần phân biệt đủ rộng; nhưng phải kiểm tra các yêu cầu truy vấn theo thời gian sau đó.

## 25. Cân nhắc update shard key

Một số trường có thể thay đổi theo thời gian:

```javascript
{
  tenantId: "TENANT-A",
  status: "PENDING",
  ...
}
```

Nếu dùng `status` làm shard key, một order từ `PENDING` sang `PAID` có thể phải **đổi shard-key value**, ảnh hưởng routing và có thể gây di chuyển document/chi phí khác. Ngoài cardinality thấp, đây là một lý do khiến status thường không phù hợp.

Trong những phiên bản MongoDB hiện đại có các điều kiện cho phép cập nhật giá trị shard key, nhưng thao tác này bị ràng buộc bởi loại update, định tuyến, transaction/retry và những yêu cầu khác. **Không được khẳng định shard key luôn bất biến tuyệt đối**, cũng không được coi việc sửa shard key thường xuyên là rẻ.

Ứng viên shard key thường nên có:

- Giá trị ổn định suốt vòng đời document;
- Kiểu BSON ổn định;
- Nhiều giá trị phân biệt;
- Không tập trung tải vào một giá trị;
- Phù hợp truy vấn phổ biến.

## 26. Thay shard key sau khi sharding: refine và reshard

Chọn sai shard key trên collection rất lớn có thể phải trả giá đáng kể khi sửa.

MongoDB có những công cụ như **refining shard key** và **resharding** trong các phiên bản hỗ trợ, nhưng hai thao tác có mục tiêu khác nhau.

### 26.1. Refine shard key

Ví dụ shard key ban đầu:

```javascript
{ tenantId: 1 }
```

Cần thêm thành phần suffix:

```javascript
{ tenantId: 1, orderId: 1 }
```

`refineCollectionShardKey` theo điều kiện phiên bản có thể giúp **mở rộng shard key bằng cách thêm field cuối**. Nó không được hiểu là cách đổi tùy ý thứ tự/type của những thành phần đã có.

Hơn nữa, refine **không tự phân phối lại toàn bộ dữ liệu ngay lập tức theo một hash design mới**. Phải xem metadata/chunk placement, balancer và tính chất các giá trị bổ sung.

Ví dụ minh họa ý tưởng:

```javascript
db.adminCommand({
  refineCollectionShardKey: "shop.orders",
  key: { tenantId: 1, orderId: 1 }
});
```

Lệnh có yêu cầu index/điều kiện và tác động khác nhau theo phiên bản. Chỉ triển khai sau khi đọc hướng dẫn chính thức và có kế hoạch migration.

### 26.2. Reshard collection

Nếu muốn đổi hẳn từ:

```javascript
{ orderNo: 1 }
```

sang:

```javascript
{ orderNo: "hashed" }
```

đó không phải append suffix đơn giản. MongoDB hỗ trợ **resharding** trong các phiên bản/topology thích hợp để thay shard key.

Ví dụ ý tưởng:

```javascript
sh.reshardCollection(
  "shop.orders",
  { orderNo: "hashed" }
);
```

Resharding có thể liên quan tới tạo bản sao dữ liệu mới, đồng bộ thay đổi, điều phối chuyển đổi metadata, index requirements, tải mạng/CPU/disk và các giai đoạn ảnh hưởng ứng dụng tùy phiên bản.

**Không dùng lệnh này như bước sửa nóng khi cluster đã quá tải** mà không có kapasity, giám sát, phương án rollback và runbook phù hợp.

### 26.3. Chọn key đúng sớm rẻ hơn sửa muộn

Trước khi shard collection lớn:

- Mô phỏng tăng trưởng 6–12 tháng;
- Test hot tenant/hot key;
- Xem write distribution trong peak load;
- Đánh giá range queries;
- Tính uniqueness;
- Xem cluster zones và topology;
- Lập phương án thay shard key nếu giả định ban đầu không còn đúng.

Việc chọn shard key vẫn có thể thay đổi qua thời gian, nhưng đổi muộn là một hoạt động vận hành có chi phí chứ không phải sửa một dòng index config đơn giản.

## 27. Quan sát dữ liệu và tải sau khi triển khai

Sau khi collection được shard, cần theo dõi các dấu hiệu thực, không chỉ bảng ước lượng trước triển khai.

| Chỉ số | Ý nghĩa |
|---|---|
| Document/bytes trên từng shard | Cân bằng dung lượng |
| Chunk/range distribution | Khả năng phân bố của shard key |
| Chunk migrations | Balancer có đang di chuyển dữ liệu nhiều không |
| Failed/jumbo/indivisible migrations | Dấu hiệu khóa có frequency quá cao hoặc ràng buộc phân vùng |
| Write ops/giây mỗi shard | Có hot write shard không |
| Read ops/giây mỗi shard | Có hot read shard không |
| CPU, IOPS, disk usage, cache pressure | Chênh lệch tài nguyên |
| p95/p99 theo endpoint/shard | Tác động tới người dùng |
| Targeted vs scatter-gather queries | Query shape có sử dụng shard key không |
| Replication lag từng shard replica set | Khả năng chịu tải và độ mới dữ liệu |
| Balancer activity/window | Thời điểm và chi phí cân bằng |

### 27.1. `sh.status()` và metadata

Trong `mongosh` kết nối qua `mongos`, có thể dùng:

```javascript
sh.status();
```

Công cụ hiển thị thông tin cluster/sharding ở mức khái quát. Cú pháp output và độ chi tiết thay đổi theo phiên bản. Cần kết hợp với monitoring/profiler/explain để hiểu truy vấn.

### 27.2. `explain()` để xem shards involved

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  orderId: "ORD-000123"
}).explain("executionStats");
```

So sánh với:

```javascript
db.orders.find({
  status: "PAID"
}).explain("executionStats");
```

Kết quả explain trên sharded cluster có thể chứa thông tin về những shard tham gia, winning plans trên shards và số lượng document/key examined. Cấu trúc phụ thuộc phiên bản và query engine.

Không đọc chỉ `executionTimeMillis` tổng rồi suy ra shard key tốt. Hãy xem **fan-out, từng shard và workload thực tế**.

### 27.3. Dữ liệu cân bằng nhưng p99 xấu

Giả sử:

```text
Shard A: 30% dữ liệu, 80% write traffic
Shard B: 35% dữ liệu, 10% write traffic
Shard C: 35% dữ liệu, 10% write traffic
```

Dung lượng khá đều nhưng workload cực lệch. Nếu shard key liên tục target A cho một hot user, cần thiết kế lại phân phối **theo query/write frequency**, không chỉ chạy balancer.

## 28. Một quy trình lựa chọn shard key thực tế

### Bước 1 — Chọn mục tiêu chia tải

Trước hết hỏi:

- Đang vượt giới hạn **storage** hay **write throughput**?
- Workload bị chậm do primary một shard hay do scatter query?
- Dữ liệu cần phân tán theo tenant, theo thiết bị, theo đơn hàng hay theo khu vực?
- SLA và ngân sách là gì?

Không nên thêm sharding chỉ vì collection vượt một ngưỡng số document tự đặt. Nếu bottleneck có thể giải quyết bằng index/schema/query, sharding sẽ thêm độ phức tạp không cần thiết.

### Bước 2 — Liệt kê candidate keys

Ví dụ:

```text
tenantId
orderId
orderNo
customerId
createdAt
(tenantId, orderId)
(tenantId, createdAt)
(tenantId, hashed(orderId))
```

Đánh giá cả trường đơn lẫn compound, tránh chốt ngay từ tên field.

### Bước 3 — Đo cardinality

Ghi:

```text
total documents N
distinct shard key values D
distinctRatio = D/N
```

Với compound key, distinct của **toàn tổ hợp**, không chỉ distinct từng field riêng lẻ.

### Bước 4 — Đo frequency/skew

Ghi:

```text
top 10 most frequent values
f_max
p_max
top 1% key share
document bytes by key
read ops/sec by key
write ops/sec by key
```

Đặc biệt tìm giá trị cực nóng, null/missing và key có khả năng tăng tải trong tương lai.

### Bước 5 — Đo monotonicity

Kiểm tra dòng key mới theo thời gian insert. Xem:

- Tăng/giảm đều;
- Xu hướng tăng theo từng tenant;
- Timestamp trùng;
- Out-of-order/backfill;
- Các đợt bulk insert.

Với candidate tăng đơn điệu, cân nhắc hashed key hoặc compound design, nhưng phải xét range queries.

### Bước 6 — Phân tích query routing

Tính tỷ lệ query:

```text
full shard key equality
shard key prefix equality
range on shard key
no shard key predicate
sort/limit over many shards
```

Xem target shard count và tần suất thực tế của các query quan trọng.

### Bước 7 — Xem ràng buộc

Kiểm tra:

- Unique business keys;
- Shard key update frequency;
- Bson type/arrays/null;
- Zones/data residency;
- Time-series hoặc collection đặc biệt;
- Index requirements;
- Chỗ đặt replica sets, failover;
- Quy mô/memory/disk khi reshard.

### Bước 8 — Thử nghiệm với dữ liệu đại diện

Dùng staging/môi trường kiểm thử để:

- Populate dataset có skew và kích thước tương đương;
- Tạo sharded cluster phù hợp;
- Đo write p50/p95/p99 và throughput mỗi shard;
- Thử range/equality reads;
- Đánh giá query fan-out;
- Quan sát migrations, balancing;
- Thử tăng shard count và kiểm tra có giảm hotspot thật không.

### Bước 9 — Chốt decision record

Lưu:

```text
Chosen shard key:
  { tenantId: 1, orderId: "hashed" }

Lý do:
  Phân tán writes trong các tenant lớn,
  equality lookup theo tenant+order phổ biến.

Đánh đổi:
  Tenant-only reads và time-range analytics
  có thể cần đọc từ nhiều shard.

Ràng buộc:
  Unique keys, schema, query routing,
  zones và capacity cần đáp ứng.

Chỉ số giám sát:
  Per-shard write TPS, p95 latency,
  distribution, scatter percentage.

Trigger đánh giá lại:
  Hot tenant > X% load,
  fan-out > Y% query,
  disk skew hoặc latency vượt SLO.
```

Các biến `X`, `Y` phải được điền từ SLO/workload thật, không phải con số phổ quát cho mọi hệ thống.

## 29. Bài tập thực hành

### Bài 1 — Phân biệt ba tiêu chí

Với từng field sau, phân tích cardinality, frequency, monotonicity:

```text
status     = NEW/PAID/CANCELLED
tenantId   = 10.000 tenant, một tenant chiếm 70% order
orderNo    = mỗi order một số tăng liên tục
createdAt  = timestamp tăng, nhiều order có cùng giây
orderId    = UUID/random ID cho từng order
```

Field nào rủi ro nhất cho range sharding? Field nào rủi ro nhất vì hot key? Vì sao high cardinality không đủ để chọn orderNo ranged?

### Bài 2 — Đo frequency với aggregation

Tạo `shardKeyLab` từ phần 18.

1. Đếm số document theo tenantId.
2. Xác định top 5 tenant.
3. Tính tỷ lệ của tenant lớn nhất.
4. Đếm số distinct orderId và status.
5. Giải thích vì sao `{ tenantId: 1 }` có thể gặp vấn đề dù có nhiều tenant.

### Bài 3 — Monotonic insert và hot range

Với range sharding `{ orderNo: 1 }`, giả sử:

```text
Shard A: [-∞, 1.000.000)
Shard B: [1.000.000, 2.000.000)
Shard C: [2.000.000, +∞)
```

Hàng triệu order mới có orderNo từ 2.500.000 trở lên.

1. Những insert mới thường target shard nào?
2. Vì sao balancer chuyển chunk cũ chưa giải quyết tận gốc vấn đề?
3. Nếu chọn `{ orderNo: "hashed" }`, write distribution thay đổi theo ý tưởng nào?
4. Range query orderNo 2.500.000–2.600.000 bị ảnh hưởng ra sao?

### Bài 4 — Hot tenant

Một SaaS có tenant A chiếm 80% writes, 5% tenant khác chia đều 20%.

1. Đánh giá shard key `{ tenantId: 1 }`.
2. Thêm orderId làm suffix tạo thay đổi gì cho cardinality compound key?
3. So sánh `{ tenantId: 1, orderNo: 1 }` và `{ tenantId: 1, orderId: "hashed" }`.
4. Vì sao chỉ thêm nhiều shard không chắc giảm CPU ở tenant A?
5. Đánh giá tác động tới API lấy lịch sử order theo tenant và thời gian.

### Bài 5 — Query targeting

Với shard key `{ tenantId: 1, orderId: "hashed" }`, đánh giá:

```javascript
db.orders.findOne({
  tenantId: "A",
  orderId: "O-1"
});

db.orders.find({
  tenantId: "A"
});

db.orders.find({
  orderId: "O-1"
});

db.orders.find({
  createdAt: { $gte: ISODate("2026-03-01T00:00:00Z") }
});
```

Query nào có đủ full-key equality? Query nào có prefix? Query nào thiếu shard key? Vì sao một local index `createdAt` có thể giúp thực thi nhưng không tự biến query cuối thành một-shard target?

### Bài 6 — Tần suất đọc khác tần suất lưu trữ

Hai tenant:

```text
Tenant A: 50% data, 5% traffic
Tenant B: 2% data, 70% traffic
```

Hãy dự đoán shard nào có thể nóng nếu cả hai được đặt tại những key ranges khác nhau. Chỉ số nào cần đo để phân biệt **storage skew** và **traffic skew**?

### Bài 7 — Time-series ingestion

Một hệ thống ghi 100.000 event/giây, mọi event có timestamp làm tròn tới giây.

1. Tại sao `createdAt` có frequency cao dù biểu kiến là timestamp?
2. Tại sao hash của `createdAt` không tự chia những event cùng giây?
3. Đề xuất key bổ sung có cardinality phù hợp.
4. Đánh giá tác động tới query “mọi event từ 8h đến 9h”.
5. Nếu collection là MongoDB time-series collection, cần kiểm tra những ràng buộc nào thêm?

### Bài 8 — Thiết kế uniqueness

Ứng dụng yêu cầu orderId duy nhất toàn cluster, tenantId là khóa tenant.

1. Phân biệt shard key với unique index.
2. Vì sao `unique: true` trên hashed index không phải giải pháp?
3. Khi shard key không có orderId ở prefix, cần xem những ràng buộc nào?
4. Thiết kế một business identifier/registry hoặc index strategy phù hợp với rules của phiên bản triển khai.

### Bài 9 — Range locality hay phân tán writes?

Một hệ thống có 70% operations là insert, 25% tra cứu order theo ID, 5% báo cáo range theo orderNo. Một hệ thống khác có 10% inserts, 80% range scans theo orderNo.

Với hai hệ thống, so sánh ranged và hashed shard key trên orderNo. Kết luận có thể khác nhau thế nào? Hãy nêu metric phải đo để bảo vệ quyết định.

### Bài 10 — Lập kế hoạch reshard

Collection hiện shard theo `{ tenantId: 1 }`, một tenant chiếm 85% dữ liệu và write load.

1. Giải thích vì sao có thể xuất hiện range không chia được theo tenantId.
2. Đề xuất hai candidate shard keys mới.
3. Khi nào refine suffix đủ, khi nào cần reshard?
4. Những chi phí về disk/network/CPU cần chuẩn bị?
5. Làm thế nào kiểm tra query routing và uniqueness sau thay đổi?

### Bài 11 — Phân vùng theo địa lý

Tenant có dữ liệu phải lưu ở khu vực EU hoặc APAC, nhưng các tenant lớn có thể rất nóng.

1. Shard key/zone policy phải giải quyết locality nào?
2. Nếu zone EU chỉ có một shard, thêm shard APAC có giảm hot EU không?
3. Vì sao hashed key đơn thuần không tự đáp ứng data residency?
4. Lập phương án tăng capacity trong từng zone.
5. Phân biệt balancing theo dung lượng và balancing theo traffic.

### Bài 12 — Báo cáo quyết định shard key

Chuẩn bị một báo cáo kỹ thuật cho hai candidate keys gồm:

- Cardinality và top-frequency values;
- Data size và request rates theo key;
- Monotonicity của inserts;
- Tỷ lệ query có full shard key/prefix/range;
- Dự kiến scatter-gather;
- Unique constraints và data types;
- Throughput/latency test trên staging;
- Lý do chọn, đánh đổi chấp nhận và chỉ số cảnh báo.

Không được chỉ viết “hash giúp phân phối đều” hoặc “range giúp query nhanh” mà không chỉ ra **workload nào** và **điều kiện nào** khiến nhận định có cơ sở.

## 30. Tài liệu MongoDB tham khảo

- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [Choose a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-choose-a-shard-key/)
- [Shard Keys](https://www.mongodb.com/docs/manual/core/sharding-shard-key/)
- [Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [Range-Based Sharding](https://www.mongodb.com/docs/manual/core/ranged-sharding/)
- [Analyze Shard Key](https://www.mongodb.com/docs/manual/reference/command/analyzeShardKey/)
- [Configure Query Analyzer](https://www.mongodb.com/docs/manual/reference/command/configureQueryAnalyzer/)
- [Reshard Collection](https://www.mongodb.com/docs/manual/core/resharding/)
- [Refine a Shard Key](https://www.mongodb.com/docs/manual/core/sharding-refine-a-shard-key/)
- [Zone Sharding](https://www.mongodb.com/docs/manual/core/zone-sharding/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Kết luận

Một shard key tốt cần được chọn từ **dữ liệu và workload**, không chỉ từ tên field.

**Cardinality** cao giúp tạo nhiều giá trị phân biệt để có không gian phân vùng, nhưng chưa đủ. **Frequency** của từng giá trị phải được kiểm tra để tránh một tenant, user hoặc trạng thái chiếm phần lớn dữ liệu/lưu lượng. **Monotonicity** của các giá trị mới quyết định nguy cơ insert liên tục dồn vào range biên khi dùng ranged shard key. Một field có **mỗi document một giá trị unique** vẫn có thể là shard key ranged kém nếu giá trị tăng không ngừng.

**Range sharding** hữu ích khi query theo khoảng và locality quan trọng, nhưng có thể tạo hot shard với khóa đơn điệu. **Hashed sharding** giúp phân tán nhiều khóa phân biệt, kể cả ID tăng dần, nhưng mất locality của range gốc và **không giải quyết một hot key duy nhất**. **Compound shard key** có thể tăng cardinality và chia nhỏ dữ liệu trong tenant, song thứ tự field và thành phần hashed tạo đánh đổi về query targeting, phạm vi đọc, uniqueness và vận hành.

Trước khi chốt, cần đo distinct values, top frequency, request distribution, write direction, data size, query patterns và hành vi trên staging. Sau khi triển khai, giám sát độ lệch giữa các shard, fan-out, hot keys, migration và p95/p99 latency. **Mục tiêu cuối cùng không phải phân đều số document trên sơ đồ, mà là phân phối đúng tải thực tế trong khi giữ những truy vấn quan trọng được định tuyến hiệu quả và đáp ứng ràng buộc dữ liệu của ứng dụng.**

