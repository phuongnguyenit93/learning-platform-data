# Query shape, plan cache và thay đổi kế hoạch khi dữ liệu biến động trong MongoDB

Một truy vấn MongoDB có thể chạy nhanh trong vài tuần rồi bất ngờ chậm đi dù câu lệnh trong ứng dụng không hề thay đổi. Nguyên nhân không nhất thiết nằm ở code: số document tăng, tỉ lệ các giá trị trong một trường thay đổi, một index mới được tạo hoặc một kế hoạch truy vấn từng phù hợp nay phải đọc quá nhiều dữ liệu. Để phân tích hiện tượng này, cần hiểu ba khái niệm liên quan chặt chẽ:

1. **Query shape:** cấu trúc của câu truy vấn, giúp MongoDB nhận diện các truy vấn có hình thức tương tự.
2. **Query plan và plan cache:** cách MongoDB chọn kế hoạch thực thi, lưu lại kế hoạch đã chọn và tái sử dụng trong những lần chạy sau.
3. **Replanning:** quá trình đánh giá/chọn lại kế hoạch khi điều kiện thực tế khiến kế hoạch cũ không còn hiệu quả hoặc khi cấu trúc index thay đổi.

Ví dụ, cùng một mẫu truy vấn lọc **status** và sắp xếp theo **createdAt**:

~~~javascript
db.orders.find({ status: "NEW" }).sort({ createdAt: -1 });
db.orders.find({ status: "FAILED" }).sort({ createdAt: -1 });
~~~

Hai câu lệnh có giá trị status khác nhau nhưng cấu trúc tương tự. Nếu **NEW chiếm 99%** document còn **FAILED chỉ chiếm 1%**, một cách đọc tối ưu cho giá trị này có thể không tối ưu cho giá trị kia. Khi tỉ lệ dữ liệu thay đổi, hiệu năng còn có thể biến động theo thời gian.

Bài học này tập trung vào **cách nhận diện query shape, phân biệt các định danh plan cache, hiểu quá trình chọn và thay kế hoạch, kiểm tra bằng explain() và $planCacheStats**, rồi xây dựng một quy trình chẩn đoán trên dữ liệu thử nghiệm. Ví dụ sử dụng **mongosh** và có phần áp dụng trong Java/Spring Data MongoDB.

## 1. Truy vấn MongoDB được thực thi như thế nào?

Khi ứng dụng gửi lệnh find(), MongoDB cần quyết định cách lấy dữ liệu và cách sắp xếp kết quả. Tùy truy vấn và index hiện có, những hướng khả dĩ có thể bao gồm:

- **COLLSCAN:** duyệt các document trong collection rồi kiểm tra filter.
- **IXSCAN:** duyệt entry của một index, có thể kết hợp **FETCH** để đọc document đầy đủ.
- **SORT:** sắp xếp riêng khi thứ tự từ index chưa đáp ứng yêu cầu.
- **LIMIT, PROJECTION và các stage khác:** giới hạn số document, chọn trường trả về hoặc xử lý các bước của kế hoạch.

Ví dụ:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20);
~~~

Nếu có index:

~~~javascript
{ status: 1, createdAt: -1 }
~~~

MongoDB **có thể** xác định nhóm status bằng index và đọc theo createdAt giảm dần. Nhưng nếu chỉ có:

~~~javascript
{ status: 1 }
~~~

server có thể dùng index để lọc rồi cần bước SORT; hoặc chọn cách khác tùy dữ liệu và chi phí.

### 1.1. Sơ đồ tổng thể

~~~text
Ứng dụng gửi filter + sort + projection + tùy chọn
                           |
                           v
                    Query shape
                           |
                           v
                Tra cứu plan cache
                    /          \
       Có kế hoạch phù hợp    Không có / không dùng cache
               |                     |
               v                     v
       Thử kế hoạch cache       Planner đánh giá
               |                các phương án
               |                     |
               +----------+----------+
                          |
                          v
                  Thực thi truy vấn
                          |
                    Phản hồi thực tế
                          |
                 Có thể dùng để đánh giá
                   hoặc chọn lại plan
~~~

Đây là mô hình khái niệm, không phải sơ đồ bắt buộc từng truy vấn phải qua đúng một chuỗi bước. Một số truy vấn đơn giản chỉ có một kế hoạch khả thi, một số truy vấn dùng cơ chế tối ưu khác, và việc tạo/tái sử dụng entry cache phụ thuộc loại truy vấn cùng phiên bản MongoDB.

### 1.2. Kế hoạch thực thi khác với kết quả truy vấn

Hai kế hoạch khác nhau có thể trả **cùng tập document** nhưng chi phí khác hẳn:

~~~text
Plan A: IXSCAN(status) -> FETCH -> SORT(createdAt) -> LIMIT
Plan B: IXSCAN(status, createdAt) -> FETCH -> LIMIT
~~~

Với cùng filter, cả hai có thể trả 20 đơn hàng phù hợp. Nhưng Plan A có thể cần sắp xếp nhiều document; Plan B có khả năng đọc kết quả theo thứ tự có sẵn từ index.

**Truy vấn trả đúng dữ liệu không chứng minh nó đã chạy hiệu quả**. Muốn đánh giá kế hoạch, cần quan sát số entry index/document đã đọc, stage SORT, thời gian thực thi và đặc điểm workload.

## 2. Query shape là gì?

**Query shape** là biểu diễn cấu trúc của một truy vấn. Trong các truy vấn thông thường, các thành phần như **filter**, **sort**, **projection** và **collation** có vai trò quan trọng trong việc phân biệt shape. Query shape giúp MongoDB nhận ra những truy vấn có hình thức tương tự để áp dụng cơ chế lập kế hoạch hoặc quan sát thống kê.

Ví dụ:

~~~javascript
// Truy vấn A
db.orders.find({
  status: "NEW"
}).sort({ createdAt: -1 });

// Truy vấn B
db.orders.find({
  status: "FAILED"
}).sort({ createdAt: -1 });
~~~

Hai truy vấn có cùng kiểu điều kiện trên status và cùng sort theo createdAt; việc thay giá trị literal **NEW** thành **FAILED** thường không làm thay đổi cấu trúc shape trong mô hình kế hoạch truy vấn thông dụng.

Một điểm cần thận trọng: **không được suy ra mọi thay đổi literal đều luôn giữ nguyên shape trong mọi phiên bản và mọi toán tử**. Một số loại biểu thức, kiểu dữ liệu và trường hợp đặc biệt có quy tắc canonicalization/parameterization riêng. Khi cần kết luận chính xác, hãy xem định danh shape mà chính server trả về.

### 2.1. Những thay đổi thường tạo shape khác

So sánh:

~~~javascript
// Shape S1: điều kiện bằng status, sort createdAt DESC
db.orders.find({ status: "NEW" })
  .sort({ createdAt: -1 });

// Shape S2: thêm điều kiện region
db.orders.find({ status: "NEW", region: "APAC" })
  .sort({ createdAt: -1 });

// Shape S3: sort theo total thay vì createdAt
db.orders.find({ status: "NEW" })
  .sort({ total: -1 });

// Shape S4: thêm projection
db.orders.find(
  { status: "NEW" },
  { _id: 0, status: 1, total: 1 }
).sort({ createdAt: -1 });

// Shape S5: range trên createdAt
db.orders.find({
  status: "NEW",
  createdAt: { $gte: ISODate("2026-10-01T00:00:00Z") }
}).sort({ createdAt: -1 });
~~~

S2 có thêm predicate, S3 đổi khóa sort, S4 đổi projection, S5 thêm điều kiện range. Đây là những thay đổi có thể dẫn đến shape khác so với S1.

### 2.2. Query shape không phải văn bản truy vấn y nguyên

Hai câu JavaScript được trình bày khác nhau:

~~~javascript
db.orders.find({ status: "NEW" });

db.orders.find({
  status: { $eq: "NEW" }
});
~~~

cùng diễn đạt phép so sánh bằng ở mức logic. MongoDB có các bước chuẩn hóa biểu thức trước khi lập kế hoạch. Tuy nhiên, **đừng tự viết một hàm băm chuỗi JSON của truy vấn và coi đó là query shape của server**: cách server canonicalize còn phụ thuộc toán tử và phiên bản.

### 2.3. Query shape không quyết định duy nhất hiệu năng

Hai lần chạy cùng shape có thể khác nhau về:

- **Giá trị tham số**: một status rất phổ biến, một status rất hiếm.
- **Dung lượng và phân bố dữ liệu**: số document phù hợp tăng hoặc giảm.
- **Index khả dụng**: tạo/drop index làm thay đổi những kế hoạch có thể chọn.
- **Trạng thái tài nguyên**: bộ nhớ đệm, I/O, CPU, truy vấn đồng thời.
- **Thời điểm thực thi và dữ liệu có thay đổi hay không**.

Shape giúp nhóm những truy vấn tương tự, nhưng không bảo đảm chúng có cùng chi phí hoặc cùng kế hoạch tối ưu trong mọi hoàn cảnh.

## 3. Plan cache là gì?

**Plan cache** lưu thông tin về những kế hoạch truy vấn được chọn cho một số query shape để MongoDB có thể tái sử dụng, giảm chi phí đánh giá lại nhiều phương án trong những lần thực thi tiếp theo.

Nếu một truy vấn thường xuyên được gọi:

~~~javascript
db.orders.find({
  status: "FAILED",
  region: "APAC"
}).sort({ createdAt: -1 });
~~~

thì việc cạnh tranh giữa các index khả dụng ở mọi request có thể gây chi phí không cần thiết. Cơ chế plan cache giúp tái sử dụng kế hoạch đã được đánh giá khi phù hợp.

**Plan cache không phải result cache.** Nó không lưu sẵn danh sách đơn hàng trả về; các document vẫn phải được đọc theo trạng thái dữ liệu hiện tại ở mỗi lần truy vấn.

| Khái niệm | Lưu/cung cấp điều gì? | Điều gì không được bảo đảm? |
|---|---|---|
| Query shape | Cấu trúc để nhận diện lớp truy vấn | Không nói chính xác có bao nhiêu document sẽ khớp |
| Query plan | Các stage/chiến lược để truy cập dữ liệu | Không bảo đảm luôn nhanh nhất sau khi dữ liệu đổi |
| Plan cache | Thông tin kế hoạch đã được lựa chọn để tái sử dụng | Không lưu kết quả truy vấn, không bảo đảm kế hoạch tồn tại mãi |
| Result set | Document thực sự được trả ở một lần chạy | Không tự ổn định nếu dữ liệu thay đổi |

### 3.1. Plan cache là trạng thái runtime, không phải hợp đồng vĩnh viễn

Plan cache là cơ chế tối ưu hóa của server, có thể thay đổi khi khởi động lại tiến trình, tạo/drop index, thay đổi môi trường hoặc bị loại entry vì chính sách quản lý bộ nhớ. Nó không phải artifact ứng dụng cần backup để giữ nguyên qua các lần triển khai.

Trong một deployment có nhiều mongod, trạng thái cache có thể khác nhau giữa các node. Do đó, quan sát cache trên một node không tự động đại diện cho mọi node trong hệ thống.

### 3.2. Vì sao có lúc truy vấn đầu tiên chậm hơn?

Khi chưa có kế hoạch tái sử dụng phù hợp, query planner có thể phải so sánh nhiều **candidate plan** trước khi chọn kế hoạch có vẻ tốt nhất. Quá trình thử nghiệm này tốn công việc bổ sung so với việc dùng một plan đã được chọn.

Tuy nhiên, lần đầu chậm hơn cũng có thể vì dữ liệu/index chưa nằm trong cache của hệ điều hành hoặc storage engine. **Không nên nhìn một lần chạy rồi kết luận toàn bộ thời gian chênh lệch là chi phí của plan cache**.

## 4. Định danh shape và định danh plan cache

Trong output chẩn đoán của MongoDB, có thể gặp những định danh như **queryHash**, **planCacheShapeHash** và **planCacheKey**. Chúng không nên được xem là từ đồng nghĩa.

| Định danh | Mục đích khái niệm | Điều cần nhớ |
|---|---|---|
| queryHash | Định danh gắn với query shape ở các phiên bản/đầu ra trước đây | Không tự mô tả tất cả index hiện tại |
| planCacheShapeHash | Hash của query shape trong các phiên bản có hỗ trợ | Được giới thiệu ở MongoDB 8.0; có thể thấy cùng queryHash vì mục đích tương thích |
| planCacheKey | Định danh entry/kế hoạch cache được hình thành từ shape **và** những index khả dụng | Có thể đổi khi bộ index khả dụng thay đổi dù shape giữ nguyên |

Ví dụ khái niệm:

~~~text
Query shape:
  filter: status = ?
  sort: createdAt DESC

Lúc A: collection có index {status:1}
  shape hash:  S
  plan cache key: K1

Lúc B: thêm index {status:1, createdAt:-1}
  shape hash:  S
  plan cache key: K2 (có thể thay đổi)
~~~

**Không tự suy luận giá trị hash cụ thể từ chuỗi filter**. MongoDB tính định danh theo cách triển khai của phiên bản server. Khi phân tích log/profiler, nên dùng đúng trường được trả về thay vì tự nối query và băm bằng một thuật toán bất kỳ.

### 4.1. Query shape và planCacheKey trả lời hai câu hỏi khác nhau

- **Shape hash:** “Đây là lớp cấu trúc truy vấn nào?”
- **Plan cache key:** “Đây là lớp truy vấn trong bối cảnh những index khả dụng nào để lựa chọn kế hoạch?”

Khi so sánh trước/sau khi tạo index, đừng thấy planCacheKey đổi rồi kết luận ứng dụng đã thay đổi filter/sort. Có thể ứng dụng gửi cùng shape nhưng tập index đã thay đổi.

### 4.2. Có cùng shape thì có chắc dùng cùng kế hoạch?

Không. Một truy vấn có thể không dùng entry cache, entry bị loại, kế hoạch bị chọn lại, hoặc môi trường/index khác nhau. Ngay cả trong cùng một môi trường, kế hoạch có thể đổi khi server nhận thấy hiệu năng không còn phù hợp.

Hơn nữa, các trường hợp đặc biệt như **hint**, một số loại biểu thức hoặc quy tắc tối ưu khác có thể ảnh hưởng cơ chế chọn plan. Vì vậy, **shape là đơn vị quan sát hữu ích**, không phải lời cam kết mọi lần thực thi đều qua một plan bất biến.

## 5. Một query plan được chọn và tái sử dụng như thế nào?

Khi có nhiều index khả dụng, MongoDB có thể tạo các **candidate plan**, thử thực thi chúng trên một phần công việc và chọn một phương án theo các tiêu chí của query planner. Một phần thông tin về phương án này có thể được giữ trong plan cache.

Ví dụ collection có:

~~~javascript
db.orders.createIndex({ status: 1 });
db.orders.createIndex({ createdAt: -1 });
db.orders.createIndex({ status: 1, createdAt: -1 });
~~~

Với truy vấn:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
~~~

những chiến lược có thể được xem xét theo dữ liệu và phiên bản:

~~~text
Ứng viên A
  IXSCAN(status)
      -> FETCH những document phù hợp
      -> SORT(createdAt DESC)
      -> LIMIT(20)

Ứng viên B
  IXSCAN(createdAt DESC)
      -> FETCH/kiểm tra status
      -> dừng khi đủ 20 kết quả

Ứng viên C
  IXSCAN(status, createdAt DESC)
      -> FETCH document phù hợp
      -> LIMIT(20)
~~~

Không nên xem ba sơ đồ là **winningPlan** chắc chắn. MongoDB có thể chọn kế hoạch khác hoặc trình bày stage khác, đặc biệt giữa các query execution engine và phiên bản.

### 5.1. Điều gì quyết định phương án tốt?

Các yếu tố thường ảnh hưởng đến chi phí:

- **Selectivity (độ chọn lọc):** filter loại được bao nhiêu document.
- **Cardinality:** bao nhiêu giá trị phân biệt hoặc bao nhiêu record cùng một giá trị.
- **Sort:** index có cung cấp đúng thứ tự kết quả không, hay phải sắp xếp riêng.
- **Limit:** cần 20 document đầu hay toàn bộ 500.000 document.
- **Projection:** có phải đọc document gốc không.
- **Kích thước document và index**, tính chất dữ liệu, cache RAM, I/O và số truy vấn đồng thời.

Một index chỉ theo status có thể rất tốt khi status là giá trị hiếm. Nếu status chiếm phần lớn collection, duyệt index rồi FETCH gần như mọi document có thể không hiệu quả bằng chiến lược khác.

### 5.2. Kết quả dùng plan cache khác “lập lại kế hoạch mỗi lần”

Khi một kế hoạch phù hợp đã được ghi nhớ, các lần thực thi cùng shape có thể tái sử dụng nó mà không cần tổ chức lại cuộc cạnh tranh giữa mọi ứng viên. Điều đó giúp giảm overhead nhưng tạo ra tình huống cần quan tâm: **kế hoạch từng phù hợp có thể trở nên không còn phù hợp khi dữ liệu đổi**.

### 5.3. Các trạng thái cache cần biết

Trong cơ chế cache có các trạng thái khái niệm như:

| Trạng thái | Ý nghĩa |
|---|---|
| **Missing** | Chưa có entry cache tương ứng |
| **Inactive** | Có thông tin về ứng viên/kế hoạch, nhưng chưa được xem là entry đang dùng tích cực theo cơ chế cache |
| **Active** | Entry có thể được dùng để tái sử dụng kế hoạch |

MongoDB có những quy tắc riêng để chuyển trạng thái dựa trên phản hồi thực thi và số công việc cần thiết. Trình tự chi tiết và trường hiển thị khác nhau theo phiên bản/engine; không nên giả định **mỗi truy vấn chạy đúng hai lần thì cache chắc chắn Active**.

Một số query shape có thể không tạo entry như kỳ vọng vì chỉ có một kế hoạch khả dĩ hoặc vì chính sách cache. **Không thấy một entry không đồng nghĩa truy vấn thất bại**.

## 6. Vì sao phân bố dữ liệu làm thay đổi hiệu năng?

Giả sử hệ thống có một triệu đơn hàng:

| status | Số lượng | Tỷ trọng |
|---|---:|---:|
| NEW | 990.000 | 99% |
| FAILED | 10.000 | 1% |

Hai truy vấn:

~~~javascript
db.orders.find({ status: "NEW" });
db.orders.find({ status: "FAILED" });
~~~

có cấu trúc tương tự, nhưng số document cần trả khác nhau rất lớn. Nếu dùng index status, trường hợp FAILED có thể chỉ cần duyệt khoảng index hẹp, còn NEW có thể đòi hỏi truy cập phần lớn collection.

### 6.1. Skew: khi phân bố dữ liệu lệch mạnh

**Data skew** nghĩa là những giá trị khác nhau của cùng một field có tần suất rất khác nhau. Các trường thường gặp:

- status: NEW/PAID/CANCELLED/FAILED.
- tenantId: một tenant rất lớn và nhiều tenant nhỏ.
- category: một category chiếm đa số.
- region: khu vực chính và khu vực ít giao dịch.
- isDeleted: false ở gần như mọi document, true ở số ít.

Truy vấn theo một giá trị hiếm và theo một giá trị phổ biến có thể có chi phí khác xa, ngay cả khi planner nhóm chúng vào cùng query shape.

### 6.2. Phân bố có thể thay đổi theo thời gian

Ví dụ đầu tháng:

~~~text
NEW:    99%
FAILED:  1%
~~~

Sau một sự cố:

~~~text
NEW:    40%
FAILED: 60%
~~~

Một kế hoạch vốn có lợi vì FAILED hiếm có thể phải đọc nhiều record hơn khi FAILED trở nên phổ biến. **Không cần sửa code truy vấn** để xuất hiện hiện tượng này; chỉ cần dữ liệu thay đổi.

Đồng thời, số document tăng theo thời gian, dữ liệu cũ bị xóa, độ dài array thay đổi và giá trị sort phân bố khác cũng có thể làm chi phí biến động.

### 6.3. Cùng shape không đồng nghĩa cùng selectivity

Khi nhóm truy vấn theo shape để phân tích, cần xem thêm **literal hoặc phân nhóm giá trị có độ chọn lọc khác nhau**. Nếu chỉ quan sát thời gian trung bình của shape, các truy vấn nhanh ở tenant nhỏ có thể che khuất truy vấn chậm ở tenant lớn.

Điều này không có nghĩa nên ghi toàn bộ giá trị nhạy cảm vào log. Có thể sử dụng nhãn workload, phân nhóm tenant theo quy mô hoặc thống kê tổng hợp đã loại dữ liệu nhạy cảm.

## 7. Khi nào MongoDB chọn lại kế hoạch?

**Replanning** là việc server đánh giá lại lựa chọn kế hoạch thay vì tiếp tục tin tưởng hoàn toàn vào kế hoạch cũ. MongoDB có cơ chế nhận biết khi một cached plan tiêu tốn nhiều công việc hơn dự kiến và có thể chọn lại kế hoạch.

Cơ chế chi tiết còn phụ thuộc phiên bản và query engine. Ở mức thực hành, cần phân biệt hai nhóm nguyên nhân:

### 7.1. Thay đổi dữ liệu nhưng index giữ nguyên

Ví dụ trạng thái FAILED tăng từ 1% lên 60%:

~~~text
Trước:
  Cùng query shape
  Plan đang cache phù hợp với tập kết quả nhỏ

Sau:
  Query shape giữ nguyên
  Index không đổi
  Số record phù hợp tăng mạnh
  Plan cũ có thể cần đọc nhiều dữ liệu hơn
~~~

MongoDB **có thể** phát hiện kế hoạch cũ hoạt động kém và lập kế hoạch lại. Không nên khẳng định mọi thay đổi tỉ lệ dữ liệu đều kích hoạt replan ngay ở lần chạy đầu tiên. Một số truy vấn vẫn dùng plan cũ cho đến khi đạt điều kiện đánh giá/invalidating cụ thể, và việc chậm đi không nhất thiết có nghĩa server đã đổi plan.

### 7.2. Tạo hoặc xóa index

Khi thêm index:

~~~javascript
db.orders.createIndex({ status: 1, createdAt: -1 });
~~~

MongoDB có thêm một cách truy cập dữ liệu. Tạo hoặc drop index có thể làm các entry plan cache của collection không còn phù hợp và bị xóa/invalidated theo cơ chế quản lý. **planCacheKey có thể thay đổi** vì tập index khả dụng đã thay đổi.

Khi điều tra trước/sau một lần deploy, cần kiểm tra lịch sử thay đổi index chứ không chỉ truy vấn trong code.

### 7.3. Những thay đổi khác ảnh hưởng lựa chọn kế hoạch

Tùy server và loại truy vấn, thay đổi về:

- **Collation** của truy vấn.
- **Projection, sort hoặc điều kiện filter**.
- **Index bị ẩn/hiện (hidden index)**.
- **Query settings, hint, một số tùy chọn lập kế hoạch**.
- **Restart hoặc failover** dẫn tới điều kiện cache runtime khác nhau.

có thể khiến server chọn cách thực thi khác hoặc không dùng lại entry cũ.

**Không đồng nhất thay đổi plan cache với thay đổi kết quả.** Một query đúng về logic vẫn phải trả tập document đáp ứng filter/sort; việc chọn plan chủ yếu thay đổi cách thực thi, hiệu năng và một số hành vi thứ tự không được bảo đảm khi thiếu sort.

## 8. Replanning không phải cơ chế chữa mọi truy vấn chậm

Nếu chỉ có một index rất không phù hợp hoặc không có index nào hỗ trợ một truy vấn quan trọng, lập kế hoạch lại không thể tự tạo ra một index tốt.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "tenant-large",
  status: "PAID"
}).sort({
  createdAt: -1
});
~~~

Nếu ứng dụng thường truy vấn theo tenantId + status rồi sort theo createdAt, có thể cần cân nhắc index:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1
});
~~~

Index phù hợp với filter equality và sort có thể quan trọng hơn việc chờ cơ chế replan tự khắc phục.

### 8.1. Không nên coi một plan change là lỗi

Kế hoạch đổi từ COLLSCAN sang IXSCAN, hoặc ngược lại, không phải luôn là regression. Nếu dữ liệu nhỏ đi, một collection scan có thể rẻ hơn việc duyệt index và fetch nhiều document. Nếu dữ liệu rất lớn nhưng filter chọn lọc, IXSCAN thường có lợi hơn.

Đánh giá bằng **chi phí thực tế của query pattern** và yêu cầu độ trễ, không chỉ bằng tên stage.

### 8.2. Một số yếu tố làm chậm dù plan không đổi

- Hệ thống chịu tải CPU/I/O đồng thời.
- Data/index bị đẩy ra khỏi cache bộ nhớ.
- Document lớn hơn trước.
- Đường truyền tới MongoDB chậm hoặc có lỗi.
- Tập kết quả lớn hơn vì ít document bị filter loại hơn.
- Ứng dụng chuyển từ projection ít field sang lấy document đầy đủ.

Do đó, phân tích plan cache chỉ là một phần của quá trình điều tra độ trễ end-to-end.

## 9. Chuẩn bị môi trường mongosh để quan sát query plan

Để làm thực hành, kết nối mongosh đến MongoDB có quyền tạo collection/index trong một database thử nghiệm:

~~~javascript
use query_plan_lab
~~~

Tạo collection **orders** với tập dữ liệu nhỏ dễ kiểm tra logic. Chạy đoạn insert một lần khi collection chưa có các _id tương ứng:

~~~javascript
db.orders.insertMany([
  {
    _id: "O01", status: "NEW", tenantId: "T-A",
    totalCents: 12000,
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "O02", status: "NEW", tenantId: "T-A",
    totalCents: 7500,
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "O03", status: "FAILED", tenantId: "T-A",
    totalCents: 13500,
    createdAt: ISODate("2026-10-03T08:00:00Z")
  },
  {
    _id: "O04", status: "NEW", tenantId: "T-A",
    totalCents: 19900,
    createdAt: ISODate("2026-10-04T08:00:00Z")
  },
  {
    _id: "O05", status: "PAID", tenantId: "T-B",
    totalCents: 39900,
    createdAt: ISODate("2026-10-05T08:00:00Z")
  },
  {
    _id: "O06", status: "NEW", tenantId: "T-A",
    totalCents: 14900,
    createdAt: ISODate("2026-10-06T08:00:00Z")
  },
  {
    _id: "O07", status: "FAILED", tenantId: "T-B",
    totalCents: 9900,
    createdAt: ISODate("2026-10-07T08:00:00Z")
  },
  {
    _id: "O08", status: "NEW", tenantId: "T-B",
    totalCents: 8800,
    createdAt: ISODate("2026-10-08T08:00:00Z")
  },
  {
    _id: "O09", status: "NEW", tenantId: "T-A",
    totalCents: 6400,
    createdAt: ISODate("2026-10-09T08:00:00Z")
  },
  {
    _id: "O10", status: "PAID", tenantId: "T-A",
    totalCents: 21000,
    createdAt: ISODate("2026-10-10T08:00:00Z")
  },
  {
    _id: "O11", status: "NEW", tenantId: "T-A",
    totalCents: 8600,
    createdAt: ISODate("2026-10-11T08:00:00Z")
  },
  {
    _id: "O12", status: "NEW", tenantId: "T-B",
    totalCents: 7400,
    createdAt: ISODate("2026-10-12T08:00:00Z")
  }
])
~~~

Kiểm tra:

~~~javascript
db.orders.countDocuments({})

db.orders.aggregate([
  { $group: { _id: "$status", count: { $sum: 1 } } },
  { $sort: { count: -1, _id: 1 } }
])
~~~

Với dữ liệu mẫu: **NEW = 8, FAILED = 2, PAID = 2**. Tập 12 document chỉ dùng để hiểu cú pháp, **không đủ lớn để suy luận planner production sẽ chọn IXSCAN hay COLLSCAN**.

### 9.1. Tạo nhiều phương án index

~~~javascript
db.orders.createIndex(
  { status: 1 },
  { name: "idx_status" }
);

db.orders.createIndex(
  { createdAt: -1 },
  { name: "idx_created_desc" }
);

db.orders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_status_created_desc" }
);
~~~

Ba index này cho planner nhiều cách truy cập dữ liệu. Truy vấn mẫu:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(5);
~~~

Với dữ liệu đã tạo, kết quả logic là **O07 rồi O03**. Index/plan nào được chọn cần quan sát từ chính server, không thể khẳng định chỉ dựa vào số index.

### 9.2. Index nào hợp với filter và sort?

| Index | Khả năng chính | Điểm cần cân nhắc |
|---|---|---|
| {status:1} | Lọc theo status | Sort createdAt có thể cần bước riêng |
| {createdAt:-1} | Trả thứ tự thời gian | Có thể phải kiểm tra nhiều status không phù hợp |
| {status:1,createdAt:-1} | Lọc status rồi đọc theo createdAt giảm | Thường phù hợp với pattern equality + sort |

Đây là **khả năng về cấu trúc**. Nếu query trả hầu như toàn bộ collection hoặc collection quá nhỏ, kế hoạch chạy nhanh nhất có thể khác dự kiến.

## 10. Sử dụng explain() để xem truy vấn có thể chạy ra sao

Lệnh explain() cho biết kế hoạch query planner xây dựng và, với chế độ phù hợp, các chỉ số thực thi:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(5).explain("executionStats");
~~~

Kết quả thực tế chứa nhiều nhánh. Hãy tìm:

| Trường/stage | Câu hỏi hỗ trợ trả lời |
|---|---|
| winningPlan | Kế hoạch nào được chọn? |
| IXSCAN | Có sử dụng index scan không? |
| COLLSCAN | Có quét toàn collection không? |
| SORT | Có bước sắp xếp riêng không? |
| FETCH | Có cần lấy document gốc không? |
| indexName | Tên index được quét là gì? |
| totalKeysExamined | Đã duyệt bao nhiêu entry index? |
| totalDocsExamined | Đã đọc/kiểm tra bao nhiêu document? |
| nReturned | Truy vấn trả bao nhiêu document? |
| executionTimeMillis | Thời gian thống kê trong lần explain |

**Lưu ý quan trọng:** **explain() bỏ qua những plan cache entry hiện có và không tạo thêm entry mới vào cache**. Nó hữu ích để khảo sát cách planner đánh giá truy vấn nhưng **không trực tiếp chứng minh một request production vừa sử dụng cached plan nào**.

Một số phiên bản dùng các cấu trúc **queryPlanner.winningPlan.queryPlan** hoặc stage riêng cho execution engine. Không hard-code code phân tích dựa trên một đường dẫn stage duy nhất mà chưa kiểm tra phiên bản và output thực tế.

### 10.1. Ba chế độ explain phổ biến

~~~javascript
db.orders.find({ status: "FAILED" })
  .explain("queryPlanner");

db.orders.find({ status: "FAILED" })
  .explain("executionStats");

db.orders.find({ status: "FAILED" })
  .explain("allPlansExecution");
~~~

Ý nghĩa tổng quan:

- **queryPlanner:** thông tin về kế hoạch được chọn và các ứng viên theo phạm vi hiển thị.
- **executionStats:** thống kê thực thi của kế hoạch thắng.
- **allPlansExecution:** bổ sung thống kê về các ứng viên được thử trong giai đoạn đánh giá khi có.

Không phải output nào cũng chứa đầy đủ thống kê cho nhiều ứng viên. Số lượng ứng viên và mức hiển thị phụ thuộc cấu trúc truy vấn, phiên bản, engine và những cơ chế tối ưu được áp dụng.

### 10.2. Kiểm tra một index cụ thể bằng hint()

Để thí nghiệm hai phương án index trên cùng filter:

~~~javascript
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .hint("idx_status")
  .explain("executionStats");

db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 })
  .hint("idx_status_created_desc")
  .explain("executionStats");
~~~

Đọc **SORT**, **keys/docs examined** và các stage khác để hiểu chi phí. **hint() ép sử dụng index được chỉ định**, nên đây là cách so sánh những khả năng truy cập, không phải bằng chứng query planner sẽ tự chọn phương án đó trong production.

Không đưa hint vào ứng dụng một cách mặc định khi chưa đo và chưa có chiến lược duy trì index; ép một index có thể trở nên bất lợi khi dữ liệu biến động.

### 10.3. Tránh đọc executionTimeMillis như một benchmark tuyệt đối

Thời gian một lần explain có thể bị ảnh hưởng bởi cache dữ liệu, tải hệ thống, số document, disk I/O và nhiều yếu tố. So sánh trong môi trường thí nghiệm nhỏ có thể tạo ra những con số bất thường.

Để đánh giá thực tế, cần lặp đo trên dữ liệu đại diện, xem **tỷ lệ keys/docs examined trên nReturned**, kiểm tra plan và theo dõi latency ứng dụng trong cùng điều kiện tải.

## 11. Xem plan cache bằng $planCacheStats

MongoDB cung cấp aggregation stage **$planCacheStats** để xem thông tin về các entry trong plan cache của collection, khi deployment/phiên bản và quyền người dùng hỗ trợ.

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
])
~~~

Tùy phiên bản, output có thể chứa những trường như **planCacheKey**, **planCacheShapeHash** hoặc **queryHash**, **isActive**, **works**, **cachedPlan**, **createdFromQuery** và thông tin host/engine. Không nên giả định mọi phiên bản đều trả tất cả trường giống nhau.

### 11.1. Chỉ xem những field chẩn đoán cần thiết

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1,
      createdFromQuery: 1
    }
  }
])
~~~

**$planCacheStats phải được đặt ở đầu pipeline** trong trường hợp sử dụng thông thường như ví dụ. Những trường không có trong output của phiên bản server có thể không xuất hiện sau $project.

### 11.2. Nếu không thấy entry thì sao?

Một số nguyên nhân:

- Truy vấn vừa tạo và chưa đi qua đủ điều kiện để cache entry xuất hiện.
- Query planner không cần cạnh tranh nhiều phương án cho shape đó.
- Cache bị invalidated/evicted hoặc server mới restart.
- Bạn đang xem plan cache trên một node khác node đã chạy truy vấn.
- Truy vấn/thao tác đang dùng cách lập kế hoạch không tạo entry như kỳ vọng.

Vì vậy, **plan cache trống không chứng minh index đang bị bỏ qua**, và **có cache entry không chứng minh query đang nhanh**.

### 11.3. Không dùng explain() để “làm nóng” plan cache

Đây là một nhầm lẫn dễ mắc:

~~~javascript
// Khảo sát planner, không làm ấm cache.
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Nếu muốn quan sát sự hình thành/tái sử dụng plan cache trong điều kiện phù hợp, cần **thực hiện truy vấn thông thường** để driver/mongosh thật sự tiêu thụ kết quả:

~~~javascript
for (let i = 0; i < 5; i++) {
  db.orders.find({
    status: "FAILED"
  }).sort({
    createdAt: -1
  }).toArray();
}

db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

Đoạn này chỉ sử dụng bộ dữ liệu nhỏ 12 document, nên toArray() không gây vấn đề bộ nhớ. Tuy nhiên, **chạy năm lần không phải lời đảm bảo chắc chắn sẽ sinh entry Active**; kết quả còn phụ thuộc planner, engine và index.

### 11.4. Plan cache của node nào?

Trong replica set, mỗi **mongod** có quá trình thực thi truy vấn, tài nguyên và plan cache riêng. Khi có nhiều node phục vụ đọc, cùng shape có thể được thực thi ở những node với cache/trạng thái khác nhau.

Trong môi trường sharded, việc quan sát càng cần biết truy vấn được router và các shard xử lý ra sao. Không nên lấy số liệu của một node rồi khẳng định đó là trạng thái duy nhất của toàn deployment.

## 12. Thực hành dữ liệu lệch mạnh trên collection riêng

Bộ dữ liệu 12 document phù hợp để đọc kết quả nhưng quá nhỏ để nghiên cứu ảnh hưởng của data skew. Ta tạo collection riêng **skewOrders** với 5.000 document. Bài thử này **không cần chạy trên production**; hãy dùng database thực hành và bảo đảm có đủ tài nguyên lưu trữ.

### 12.1. Tạo 4.900 NEW và 100 FAILED

Trong mongosh:

~~~javascript
use query_plan_lab

const total = 5000;
const chunkSize = 500;

for (let start = 1; start <= total; start += chunkSize) {
  const batch = [];
  const end = Math.min(start + chunkSize - 1, total);

  for (let i = start; i <= end; i++) {
    batch.push({
      _id: "S-" + String(i).padStart(5, "0"),
      seq: i,
      status: i <= 4900 ? "NEW" : "FAILED",
      tenantId: i % 10 === 0 ? "T-small" : "T-large",
      totalCents: 1000 + (i % 200) * 100,
      createdAt: new Date(
        Date.UTC(2026, 9, 1) + i * 60 * 1000
      )
    });
  }

  db.skewOrders.insertMany(batch);
}
~~~

Chạy **một lần** trên collection chưa có các _id này. Chạy lại sẽ báo trùng khóa; không cần xóa/ghi đè dữ liệu thật để làm thí nghiệm.

Thống kê phân bố:

~~~javascript
db.skewOrders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
~~~

Kết quả dự kiến:

| status | Số document | Tỷ trọng |
|---|---:|---:|
| NEW | 4.900 | 98% |
| FAILED | 100 | 2% |

Tập này vẫn khá nhỏ so với production, nhưng minh họa rõ sự khác nhau của một giá trị phổ biến và một giá trị hiếm.

### 12.2. Tạo index có chiến lược khác nhau

~~~javascript
db.skewOrders.createIndex(
  { status: 1 },
  { name: "idx_skew_status" }
);

db.skewOrders.createIndex(
  { createdAt: -1 },
  { name: "idx_skew_created" }
);

db.skewOrders.createIndex(
  { status: 1, createdAt: -1 },
  { name: "idx_skew_status_created" }
);
~~~

Hai truy vấn tương tự nhau:

~~~javascript
// Giá trị rất phổ biến
db.skewOrders.find({
  status: "NEW"
}).sort({ createdAt: -1 }).limit(20);

// Giá trị hiếm
db.skewOrders.find({
  status: "FAILED"
}).sort({ createdAt: -1 }).limit(20);
~~~

Cả hai có cùng filter/sort về cấu trúc. Tuy nhiên, nếu đánh giá truy vấn **không có limit**, giá trị NEW cần trả 4.900 document còn FAILED chỉ trả 100. Với limit(20), cả hai có thể dừng sau khi tìm đủ 20 document phù hợp, khiến chênh lệch chi phí phụ thuộc mạnh vào index và phân bố theo createdAt.

### 12.3. So sánh kế hoạch với explain()

~~~javascript
db.skewOrders.find({
  status: "NEW"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");

db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");
~~~

Hãy xem:

- **Có SORT riêng không?**
- **winningPlan chọn index nào hoặc COLLSCAN?**
- **totalKeysExamined và totalDocsExamined** khác nhau ra sao?
- **nReturned** có cùng bằng 20 không?
- Nếu có nhiều candidate, **allPlansExecution** cho thấy gì?

**Quan trọng:** Hai lệnh explain giúp so sánh **quyết định mới của planner trên giá trị cụ thể**, không phải bằng chứng direct rằng hai lần chạy thường đã dùng cùng entry cache.

### 12.4. Thử thay đổi phân bố mà không đổi query shape

Trong **collection skewOrders chỉ dùng để thử nghiệm**, đổi 3.000 document đầu từ NEW sang FAILED:

~~~javascript
db.skewOrders.updateMany(
  {
    status: "NEW",
    seq: { $lte: 3000 }
  },
  {
    $set: { status: "FAILED" }
  }
)
~~~

Sau thao tác:

~~~javascript
db.skewOrders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  }
])
~~~

Phân bố kỳ vọng:

| status | Số document | Tỷ trọng |
|---|---:|---:|
| NEW | 1.900 | 38% |
| FAILED | 3.100 | 62% |

Filter và sort trong code không thay đổi, nhưng **tỉ lệ dữ liệu của mỗi status đã đảo chiều mạnh**.

### 12.5. Quan sát lại sau thay đổi

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).explain("executionStats");

db.skewOrders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1
    }
  }
])
~~~

Với cùng điều kiện truy vấn, hãy suy nghĩ:

1. Dữ liệu nào giờ phổ biến hơn?
2. Truy vấn có cần đọc nhiều document hơn trước không?
3. Nếu winningPlan thay đổi, **do phân bố, index hay điều kiện thực thi**?
4. Nếu winningPlan không đổi, hiệu năng có vẫn thay đổi không?
5. Có thể khẳng định cache đã replan chỉ bằng explain không? **Không.**

Bài thử không bảo đảm query planner luôn đổi kế hoạch. Một compound index phù hợp có thể tiếp tục tốt cho cả hai phân bố, nhất là khi chỉ cần 20 kết quả. Mục đích là hiểu **cách đặt giả thuyết và thu thập chứng cứ**, không phải ép server phải tạo ra một plan change.

### 12.6. Phân bố status là một phần của bài toán

Khi dữ liệu đổi từ NEW nhiều sang FAILED nhiều, index cũng phải được cập nhật cho những document đổi status. Điều đó tạo thêm **chi phí ghi**. Trong hệ thống thật, việc xử lý hàng nghìn/millions update có thể tốn tài nguyên; không chạy updateMany có phạm vi lớn khi chưa đánh giá ảnh hưởng production.

## 13. Quan sát plan cache trước/sau thay đổi index

Thay đổi index có thể làm **planCacheKey** đổi mà query shape không đổi. Hãy dùng một collection thử nghiệm riêng để minh họa.

Ví dụ trước khi thêm index:

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).toArray();
~~~

Xem cache theo khả năng hỗ trợ:

~~~javascript
db.skewOrders.aggregate([
  { $planCacheStats: {} }
])
~~~

Thêm một index ứng viên phù hợp với một query pattern mới:

~~~javascript
db.skewOrders.createIndex(
  { tenantId: 1, status: 1, createdAt: -1 },
  { name: "idx_tenant_status_created" }
);
~~~

Thực thi truy vấn:

~~~javascript
db.skewOrders.find({
  tenantId: "T-small",
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20).toArray();
~~~

Rồi quan sát lại $planCacheStats. Khi index được tạo, các entry cache cũ có thể bị invalidated và những entry mới dùng **planCacheKey** tương ứng tập index hiện tại.

**Không thể kết luận shape hash của hai câu truy vấn khác nhau ở trên phải bằng nhau**: câu query có tenantId và câu không có tenantId là hai shape khác. Để so sánh hash trước/sau index, phải dùng **chính cùng filter + sort + projection** ở hai thời điểm, không đổi query pattern giữa chừng.

### 13.1. Phân biệt tạo index và thay đổi dữ liệu

| Thao tác | Query shape của cùng câu query | Plan cache / planCacheKey |
|---|---|---|
| Tăng số document, đổi tỉ lệ status | Thông thường giữ nguyên | Không nhất thiết invalidated ngay; hiệu năng có thể đổi, có thể replan |
| Tạo index mới | Query shape giữ nguyên | Tập index khả dụng thay đổi; entry có thể invalidated và key có thể đổi |
| Drop index | Query shape giữ nguyên | Plan dùng index cũ không còn hợp lệ; cache cần thích ứng |
| Đổi filter hoặc sort trong ứng dụng | Có thể thành shape khác | Có thể dùng entry riêng |
| Restart node | Query shape về logic không đổi | Cache runtime không được bảo đảm giữ nguyên |

Đó là lý do khi debug “query tự nhiên chậm”, cần kiểm tra **cả biến động dữ liệu lẫn lịch sử index/deployment**.

## 14. Khi nào nên xóa plan cache?

MongoDB cung cấp cơ chế quản trị để xóa các entry plan cache khi cần. Với mongosh, một cách thường dùng trong phiên bản hỗ trợ là:

~~~javascript
// Chỉ dùng ở môi trường thực hành hoặc theo quy trình vận hành được duyệt.
db.skewOrders.getPlanCache().clear();
~~~

Hoặc lệnh quản trị tương ứng theo server:

~~~javascript
db.runCommand({
  planCacheClear: "skewOrders"
});
~~~

Xóa plan cache **không xóa document, không xóa index và không làm thay đổi query shape của ứng dụng**. Nó khiến những lần chạy sau có thể cần lập kế hoạch lại thay vì dùng entry cũ.

### 14.1. Không dùng clear cache như giải pháp chữa cháy mặc định

Nếu thực chất truy vấn thiếu index hoặc dữ liệu có tỉ lệ khác trước, xóa cache có thể giúp một số trường hợp tạm thời nhưng **không giải quyết nguyên nhân gốc**. Lần chạy sau còn có thể tốn chi phí lập kế hoạch lại.

Chỉ thao tác với cache khi đã hiểu tác động và có lý do cụ thể, chẳng hạn thí nghiệm truy vấn, điều tra sự cố theo quy trình hay xử lý một trạng thái cache bất lợi đã được xác nhận.

**Không nên chạy clear đồng loạt trong production** chỉ vì thấy latency tăng. Trên nhiều node, cần xác định đúng node/collection và đánh giá hậu quả tới workload khác.

### 14.2. Hint là một loại can thiệp khác

~~~javascript
db.skewOrders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).hint("idx_skew_status_created");
~~~

**hint** yêu cầu sử dụng index được chỉ định; nó có thể giúp chẩn đoán hoặc khắc phục trường hợp đặc biệt, nhưng làm ứng dụng phụ thuộc vào index đó. Nếu index bị drop/ẩn hoặc phân bố dữ liệu đổi, hint có thể gây lỗi hoặc khiến truy vấn chậm.

Trong những phiên bản MongoDB hỗ trợ, **query settings** có thể cho phép quản lý một số hành vi của lớp query shape; đây là cấu hình quản trị nâng cao, phải kiểm tra version và quyền. Không nên đồng nhất query settings với việc tự sửa trực tiếp một entry trong plan cache.

## 15. Quy trình điều tra khi một query shape bỗng chậm

Giả sử một endpoint từng trả kết quả trong thời gian ngắn, nay độ trễ tăng mạnh sau một đợt nhập dữ liệu. Thay vì xóa plan cache ngay, có thể dùng quy trình sau.

### Bước 1. Xác định truy vấn thực sự được chạy

Ghi lại:

- Collection và database.
- Filter và **kiểu BSON** của các giá trị.
- Sort, projection, limit, skip, collation.
- Tên index đang có.
- Version MongoDB, deployment, node phục vụ truy vấn.
- Tần suất gọi, độ trễ trước/sau và số document trả về.

Ví dụ:

~~~javascript
db.orders.find(
  {
    tenantId: "T-A",
    status: "NEW"
  },
  {
    _id: 1,
    createdAt: 1,
    totalCents: 1
  }
).sort({
  createdAt: -1
}).limit(50);
~~~

**Đừng bỏ projection hoặc limit** khi tái hiện truy vấn. Thay đổi chúng có thể khiến query shape/plan khác, và kết quả thí nghiệm không phản ánh request thật.

### Bước 2. Nhóm theo shape nhưng vẫn kiểm tra các giá trị lệch

Hai request có thể cùng shape:

~~~javascript
{ tenantId: "T-A", status: "NEW" }
{ tenantId: "T-B", status: "NEW" }
~~~

nhưng tenant T-A có thể chứa hàng triệu document, T-B chỉ có vài trăm. Cần đối chiếu độ chọn lọc và tần suất truy vấn theo nhóm giá trị, không chỉ thời gian trung bình toàn shape.

Với dữ liệu đa tenant, luôn giữ **tenantId trong filter và index phù hợp** khi kiến trúc bảo mật/yêu cầu dữ liệu quy định. Không bỏ điều kiện tenant chỉ để benchmark nhanh hơn.

### Bước 3. Xem phân bố dữ liệu

Với collection không quá lớn hoặc môi trường thí nghiệm:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Đối với collection lớn trong production, truy vấn quét toàn bộ collection để thống kê có thể đắt. Nên ưu tiên các metric đã có, hệ thống analytics hoặc các phép kiểm kê được lên kế hoạch, thay vì thực hiện group không giới hạn lúc hệ thống đang cao tải.

### Bước 4. Xem index và lịch sử deploy

~~~javascript
db.orders.getIndexes();
~~~

Kiểm tra có index vừa được tạo, drop, ẩn/hiện hoặc đổi collation hay không. Nếu query dùng index khác sau một lần deploy, thay đổi index là một giả thuyết cần xem xét.

Đối với index ghép, đánh giá **thứ tự trường** và pattern **equality + sort + range**. Chỉ thấy field nằm trong index không đủ chứng minh index hỗ trợ cả filter lẫn sort.

### Bước 5. Dùng explain để phân tích các phương án hiện tại

~~~javascript
db.orders.find({
  tenantId: "T-A",
  status: "NEW"
}).sort({
  createdAt: -1
}).limit(50).explain("executionStats");
~~~

Đọc winningPlan, stage SORT, keys/docs examined và nReturned. Nếu cần so sánh hai index, dùng hint có chủ đích trong môi trường thử nghiệm.

Nhớ rằng **explain không phản ánh trực tiếp plan cache đã được dùng ở lần chạy bình thường**. Khi cần bằng chứng về hành vi runtime và replan, phải kết hợp quan sát profiler/log/APM và $planCacheStats theo phiên bản.

### Bước 6. Quan sát cache và các lần thực thi thường

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} },
  {
    $project: {
      _id: 0,
      planCacheKey: 1,
      planCacheShapeHash: 1,
      queryHash: 1,
      isActive: 1,
      works: 1
    }
  }
]);
~~~

Nếu entry chưa có, không tự kết luận cache hỏng. Nếu có entry Active, cũng không tự kết luận lần query đang xét chắc chắn đã dùng nó; cần đối chiếu shape/key và request/host.

### Bước 7. Chọn giải pháp theo nguyên nhân

| Nguyên nhân tìm thấy | Hướng xử lý |
|---|---|
| Query thiếu index phù hợp | Cân nhắc tạo compound index đúng filter/sort |
| Data skew cao | Đánh giá các query pattern và giá trị lệch, cân nhắc index chuyên biệt/điều chỉnh mô hình |
| Kết quả tăng quá nhiều | Giới hạn dữ liệu cần trả, phân trang, projection phù hợp |
| Sort không dùng index | Xem lại thứ tự khóa và chiều index |
| Cache/plan cũ thực sự bất lợi | Đánh giá replanning và can thiệp có kiểm soát khi cần |
| Tài nguyên hệ thống bị nghẽn | Điều tra CPU/I/O/memory, concurrency, network |
| Query thay đổi trong code | Xem lại shape, projection, sort, collation và index |
| Các node có hiệu năng khác | Kiểm tra routing, dữ liệu, cache và cấu hình từng node |

### Bước 8. Theo dõi sau thay đổi

Sau khi tạo index hoặc sửa query, đo lại:

- **p50, p95, p99 latency** của endpoint/query pattern.
- **nReturned** và tỷ lệ keys/docs examined trên số trả về.
- **Tốc độ insert/update** và dung lượng index.
- **Tần suất plan change/replanning** nếu cơ chế observability có cung cấp.
- **Tình trạng query trên các node** chứ không chỉ máy đã thử.

Mục tiêu cuối cùng là hiệu năng ổn định trong workload thật, không chỉ làm một explain trông “đẹp”.

## 16. Profiling, log và APM: phân biệt quan sát với can thiệp

Trong quá trình xử lý sự cố thực tế, dữ liệu từ server log, profiler hoặc hệ thống giám sát ứng dụng thường quan trọng hơn một lần chạy explain thủ công. Tùy phiên bản MongoDB, log/profiler có thể chứa thông tin về query shape, plan cache identifiers, kế hoạch, số document/index entry đã đọc hoặc việc query planner phải chọn lại kế hoạch.

### 16.1. Không bật profiler toàn phần tùy tiện

Profiler có thể tạo overhead và lưu dữ liệu truy vấn trong hệ thống. Trên production, cần chính sách bảo mật, quyền truy cập và đánh giá chi phí trước khi tăng mức profiling hoặc thay đổi slow-operation threshold.

Một truy vấn trong profiler có thể chứa filter hoặc thông tin nhạy cảm tùy cách ghi log. Chỉ cấp quyền và lưu dữ liệu theo chính sách hệ thống; không đổ nguyên truy vấn của khách hàng vào chat công khai để nhờ phân tích.

### 16.2. Dùng driver command monitoring khi phù hợp

MongoDB Driver hỗ trợ các sự kiện command monitoring, cho phép ứng dụng theo dõi những thao tác gửi đến server. Điều này có ích để biết thực tế ứng dụng gọi find()/getMore nào, thời gian từng lệnh, lỗi và mối liên hệ với một request.

Nhưng **command monitoring không tự thay thế query planner metrics**; nó giúp bổ sung thời gian ở tầng driver/client. Khi phân tích có cần tách:

~~~text
Latency API
  = thời gian validate + business logic
  + thời gian chờ connection pool
  + network + MongoDB server execution
  + decode BSON + serialization
  + xử lý dữ liệu và trả response
~~~

Nếu tổng thời gian API tăng nhưng số keys/docs examined của query không đổi, có thể phần chậm nằm ngoài query plan.

### 16.3. Nhận biết replan bằng tín hiệu của server

Một số phiên bản MongoDB có thể ghi thông tin cho biết kế hoạch đã được chọn lại hoặc lý do replan trong các đầu ra chẩn đoán. Định dạng log, tên trường và cách bật quan sát phụ thuộc phiên bản; không nên viết tool bắt buộc phải thấy một chuỗi log cố định cho mọi deployment.

Khi báo cáo một lần thay đổi kế hoạch, nên có ít nhất:

1. Query shape hoặc định danh tương ứng.
2. Index và plan trước/sau nếu có chứng cứ.
3. Phân bố dữ liệu và thời điểm thay đổi.
4. Keys/docs examined và latency trước/sau.
5. Những thay đổi index/deploy hoặc topology xảy ra cùng thời điểm.

Một ảnh chụp explain duy nhất không đủ để xác nhận server đã replan từ cached plan nào.

## 17. Những giới hạn và tình huống đặc biệt cần nhớ

### 17.1. Query shape không phải bản sao toàn bộ command

Một command find có nhiều tùy chọn. Không phải mọi tùy chọn đều nhất thiết nằm trong shape theo cùng một cách trong mọi phiên bản và ngữ cảnh. **Filter, sort, projection, collation** là các yếu tố quan trọng, nhưng những operator đặc biệt, aggregation pipeline, literal và query settings có quy tắc riêng.

Khi cần kết luận “hai request cùng shape”, hãy dựa vào thông tin do MongoDB cung cấp theo phiên bản triển khai, không chỉ dựa vào so sánh chuỗi JSON trong code.

### 17.2. Plan cache không phải nơi lưu toàn bộ lịch sử

$planCacheStats cho biết những entry hiện có theo cơ chế cache, không phải một lịch sử đầy đủ tất cả kế hoạch từng được chọn. Entry có thể biến mất vì restart, invalidation, eviction hoặc những lý do khác.

Nếu cần nghiên cứu performance regression kéo dài nhiều ngày, nên lưu metric và các điểm quan sát theo thời gian trong hệ thống monitoring phù hợp, với retention và bảo mật rõ ràng.

### 17.3. Aggregation pipeline có nhiều hình thức thực thi

Không phải mọi aggregation pipeline đều được tối ưu và cached giống một find đơn giản. Một số stage có thể được đẩy xuống, đổi thứ tự hoặc thực hiện ở những engine khác nhau; một số loại stage có đặc tính chặn dòng dữ liệu, dùng nhiều bộ nhớ hoặc không được tối ưu theo index như mong muốn.

Vì vậy, khi nghiên cứu **plan cache cho aggregation**, cần dùng explain và công cụ observability phù hợp với chính pipeline đó. Không áp dụng cơ học mọi chi tiết của find() vào một pipeline phức tạp.

### 17.4. Sharding có nhiều cấp quyết định

Ở sharded cluster, một query có thể phải được định tuyến qua mongos, gửi đến một hoặc nhiều shard rồi kết hợp kết quả. Query plan trên mỗi shard có thể khác vì index, phân bố dữ liệu hoặc trạng thái cache.

Một shape có cùng cấu trúc không đồng nghĩa mọi shard có cùng cardinality. **Tenant lớn tập trung ở một shard** có thể tạo hiệu năng khác với tenant nhỏ hoặc yêu cầu phân tán.

### 17.5. Cache và query settings có tác dụng khác nhau

Plan cache lưu kế hoạch đã được lựa chọn để tái sử dụng theo chính sách runtime. Query settings ở những phiên bản hỗ trợ giúp quản lý hành vi truy vấn theo cách cấu hình; nó không đơn giản là việc giữ nguyên một cached plan.

Nếu ứng dụng cần hành vi index có kiểm soát, cần tìm hiểu tính tương thích phiên bản, quyền quản trị và chính sách vận hành trước khi sử dụng hint hoặc query settings. Một cơ chế ép index dùng sai thời điểm có thể làm performance regression khó xử lý hơn.

## 18. Java MongoDB Sync Driver: đọc query plan

Trong ứng dụng Java, MongoDB Sync Driver cung cấp các builder như **Filters**, **Sorts**, **Indexes** cùng khả năng gọi **explain()** trên truy vấn. Ví dụ cần dependency **mongodb-driver-sync** tương thích và biến môi trường **MONGODB_URI** được cấu hình.

### 18.1. Truy vấn thông thường

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

public class OrderQueryExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Bson filter = Filters.eq("status", "FAILED");
        Bson sort = Sorts.descending("createdAt");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_plan_lab")
                    .getCollection("orders");

            try (MongoCursor<Document> cursor = orders
                    .find(filter)
                    .sort(sort)
                    .limit(20)
                    .iterator()) {

                while (cursor.hasNext()) {
                    System.out.println(cursor.next().toJson());
                }
            }
        }
    }
}
~~~

Đây là **truy vấn thông thường**. Server có thể lựa chọn hoặc tái sử dụng kế hoạch trong quá trình xử lý. Code ứng dụng không cần tự quản lý plan cache để mỗi request chạy được.

### 18.2. Gọi explain trong Java

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

public class OrderExplainExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("query_plan_lab")
                    .getCollection("orders");

            Document plan = orders.find(
                    Filters.eq("status", "FAILED"))
                    .sort(Sorts.descending("createdAt"))
                    .limit(20)
                    .explain(ExplainVerbosity.EXECUTION_STATS);

            System.out.println(
                    plan.toJson()
            );
        }
    }
}
~~~

Output của explain() chứa cây kế hoạch và execution stats; trong code thực tế nên phân tích các field theo phiên bản driver/server đang dùng. **Đừng lấy thời gian của explain và coi đó chính là độ trễ mọi lần query thông thường**, vì explain có hành vi đặc biệt với plan cache.

### 18.3. Tạo index theo query pattern

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

public class OrderIndexSetup {
    public static void createIndex(
            MongoCollection<Document> orders) {

        orders.createIndex(
                Indexes.compoundIndex(
                        Indexes.ascending("tenantId", "status"),
                        Indexes.descending("createdAt")
                ),
                new IndexOptions()
                        .name("idx_tenant_status_date")
        );
    }
}
~~~

Ví dụ trên là một method nhận **MongoCollection** đã được cấu hình từ trước. Index có thể phù hợp với truy vấn lọc **tenantId = ..., status = ...** và sort **createdAt DESC**.

Đừng chạy tạo index theo yêu cầu mỗi request của người dùng. Trong dự án thật, nên quản lý index bằng migration/bootstrap có kiểm soát, xem tác động build index trên dữ liệu lớn và tránh tạo trùng.

### 18.4. Truy vấn cùng shape từ các tham số Java khác nhau

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;

import java.util.List;
import java.util.ArrayList;

public class StatusQuery {
    public static List<Document> latestByStatus(
            MongoCollection<Document> orders,
            String status) {

        return orders.find(Filters.eq("status", status))
                .sort(Sorts.descending("createdAt"))
                .limit(20)
                .into(new ArrayList<>());
    }
}
~~~

Gọi:

~~~java
latestByStatus(orders, "NEW");
latestByStatus(orders, "FAILED");
~~~

Hai lời gọi giữ cấu trúc filter/sort/limit tương tự, nhưng có thể khác mạnh về số document phù hợp. Nếu status lấy từ HTTP request, ứng dụng phải validate quyền/ngữ nghĩa đầu vào và tránh đưa dữ liệu nhạy cảm vào log chẩn đoán.

## 19. Spring Data MongoDB: query shape trong repository/service

Spring Data MongoDB ánh xạ các điều kiện **Criteria** và **Sort** thành truy vấn MongoDB. Cơ chế plan cache vẫn do **MongoDB server** quản lý, không phải một map các đối tượng Java Query được ứng dụng giữ lại.

Ví dụ:

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

    public List<Document> latestOrdersForTenant(
            String tenantId,
            String status) {

        Query query = new Query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is(status)
        );

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("_id")
        ));

        query.limit(20);
        query.fields()
                .include("createdAt")
                .include("status")
                .include("totalCents");

        return mongoTemplate.find(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

Ở đây, hai request khác status hoặc tenantId có thể cùng cấu trúc truy vấn, nhưng mức độ chọn lọc rất khác. MongoDB có thể dùng hoặc thay đổi plan theo điều kiện thực tế. Nếu application cần tối ưu đường đọc này, ứng viên index thường phải xét cả equality theo tenantId/status và sort createdAt/_id.

### 19.1. Schema Java và BSON type phải nhất quán

Nếu một service lưu **createdAt** là BSON Date, nhưng service khác lưu thành String, hai bộ lọc có hình thức giống nhau vẫn có thể khớp các nhóm dữ liệu khác nhau. MongoDB không tự chuyển String ngày giờ thành Date trong index để phục vụ sort như nhau.

Nên dùng mapping phù hợp, ví dụ **Instant/Date** được chuyển sang BSON Date bằng driver/converter đã cấu hình, và schema validation nếu cần đảm bảo kiểu dữ liệu tại database.

### 19.2. Projection cũng cần được thống nhất khi so sánh performance

Hai method:

~~~java
// A: lấy cả document.
mongoTemplate.find(query, Document.class, "orders");

// B: query chỉ lấy những field cần thiết.
query.fields()
        .include("status")
        .include("createdAt");
mongoTemplate.find(query, Document.class, "orders");
~~~

có yêu cầu projection khác nhau và chi phí đọc/serialization có thể khác. Trong ứng dụng thật, không nên điều tra latency của method A bằng cách explain một query B đã lược bớt field rồi mặc định chúng tương đương.

### 19.3. Có nên dùng @Hint hoặc gắn hint mọi nơi?

Spring Data và MongoDB Driver có API để chỉ định hint trong các trường hợp phù hợp. Nhưng nếu lạm dụng, ứng dụng có thể buộc một index không còn tốt sau khi dữ liệu đổi. Đặc biệt với hệ thống đa tenant hoặc dữ liệu biến động mạnh, cần đo và có quy trình đánh giá lại hint khi thêm/drop index.

Giải pháp ưu tiên thường là xác định **query pattern**, tạo index phù hợp và theo dõi planner, thay vì cố định index ngay từ đầu mà chưa có chứng cứ.

## 20. Tình huống so sánh: cùng shape nhưng khác đường đọc tối ưu

Giả sử ứng dụng có hai nhóm đơn hàng:

~~~text
status = NEW:
  Phần lớn dữ liệu
  Query thường trả hàng nghìn record

status = FAILED:
  Rất ít dữ liệu
  Query chỉ trả vài record
~~~

Có ba lựa chọn index:

~~~javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

Nếu filter theo status và sort createdAt, compound index thường là ứng viên có lợi. Nhưng nếu truy vấn không còn filter status, index chỉ theo createdAt có thể hữu ích hơn. Nếu filter status cực kỳ chọn lọc nhưng query cần một sort khác, index status đơn có thể lọc trước và sort tập nhỏ hợp lý.

### 20.1. Vì sao một query shape không thể có "một index thần kỳ"?

Giả sử ứng dụng có ba màn hình:

~~~javascript
// A: đơn hàng mới nhất toàn hệ thống
db.orders.find().sort({ createdAt: -1 }).limit(20);

// B: đơn FAILED mới nhất
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 }).limit(20);

// C: đơn của một tenant với total lớn
db.orders.find({
  tenantId: "T-large",
  totalCents: { $gte: 10000 }
}).sort({ totalCents: -1 }).limit(20);
~~~

Các query pattern khác nhau:

| Màn hình | Filter | Sort | Index ứng viên |
|---|---|---|---|
| A | Không có | createdAt DESC | {createdAt:-1} |
| B | status equality | createdAt DESC | {status:1,createdAt:-1} |
| C | tenant equality + total range | total DESC | {tenantId:1,totalCents:-1} |

Một index dài chứa tất cả field không nhất thiết đáp ứng tốt cả ba. Thứ tự field trong compound index rất quan trọng, và index nào cũng có chi phí duy trì khi ghi dữ liệu.

### 20.2. Khi giá trị sort không duy nhất

Nếu hai đơn hàng có cùng createdAt, query sort chỉ theo createdAt không bảo đảm thứ tự giữa chúng. Với phân trang hoặc batch checkpoint, dùng khóa phụ như _id:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
~~~

Khi đổi sort, yêu cầu về index cũng có thể đổi. Nếu ứng dụng dùng sort tạo thứ tự duy nhất, nên cân nhắc index phù hợp với cả khóa phụ và dùng cùng sort khi tái hiện sự cố.

## 21. Những nhầm lẫn và lỗi chẩn đoán thường gặp

| Nhầm lẫn hoặc hiện tượng | Vấn đề thực sự | Cách xử lý |
|---|---|---|
| "Hai truy vấn đổi literal chắc chắn luôn là hai shape khác nhau" | Query shape thường dựa trên cấu trúc được chuẩn hóa, không phải từng chuỗi literal | So shape/hash do MongoDB báo và đối chiếu phiên bản |
| "Cùng shape thì tốc độ phải giống nhau" | Selectivity/cardinality theo literal có thể chênh rất lớn | Xem phân bố giá trị và keys/docs examined |
| "planCacheKey chính là queryHash" | Một định danh gắn với shape, một định danh còn phản ánh index khả dụng | Phân biệt planCacheShapeHash/queryHash với planCacheKey |
| "Cùng shape thì plan không bao giờ đổi" | Cache có thể invalidated, replan hoặc evicted | Theo dõi log/metrics và lịch sử index/deploy |
| "Cache lưu lại document kết quả" | Plan cache lưu thông tin kế hoạch, không phải result set | Mỗi lần truy vấn vẫn đọc dữ liệu hiện thời |
| "explain() cho biết cached plan đang được dùng" | explain bỏ qua plan cache và không làm nóng cache | Dùng explain cho khảo sát plan; dùng profiler/log/$planCacheStats cho bối cảnh runtime |
| "Chạy explain nhiều lần là đã warm cache" | Explain không tạo entry cache như truy vấn thường | Thực thi truy vấn thường khi cần quan sát cache và chấp nhận chính sách server |
| "Không có $planCacheStats entry nghĩa là không dùng index" | Query shape có thể không tạo entry hoặc entry bị loại | Kiểm tra winningPlan bằng explain và hiểu điều kiện cache |
| "Cache Active nghĩa là query đang nhanh" | Cached plan có thể trở nên không còn phù hợp | Đo latency, keys/docs examined và feedback |
| "Có IXSCAN tức là tối ưu" | Có thể quét gần hết index và FETCH nhiều document | So nReturned với keys/docs examined |
| "Có COLLSCAN tức là lỗi" | Với collection nhỏ hoặc filter không chọn lọc, COLLSCAN có thể hợp lý | Đánh giá chi phí trên dữ liệu đại diện |
| "Xóa cache sẽ sửa query chậm vĩnh viễn" | Có thể thiếu index, dữ liệu skew hoặc tài nguyên đang nghẽn | Điều tra nguyên nhân rồi mới cân nhắc can thiệp cache |
| "Thêm index không ảnh hưởng plan cache" | Tập index khả dụng thay đổi, key/entry có thể bị invalidated | Theo dõi lịch sử tạo/drop/hide index |
| "Tăng FAILED không ảnh hưởng query nếu query không đổi" | Số record phù hợp có thể tăng mạnh | Xem phân bố mới và chọn lọc thực tế |
| "Một explain ở dev đại diện cho production" | Khác data volume, phân bố, version, topology và tải | Dùng dữ liệu/thời điểm quan sát đại diện |
| "Hint index luôn giúp ổn định performance" | Bắt buộc dùng index có thể không còn tốt khi dữ liệu đổi | Dùng hint có lý do và theo dõi sau triển khai |
| "Cùng ứng dụng nghĩa là mọi node dùng chung cache" | Plan cache thường là trạng thái runtime của node | Kiểm tra node phục vụ và sự khác biệt replica/shard |
| "p95 tăng tức là planner vừa replan" | Network, CPU, I/O, pool wait và payload cũng gây trễ | Phân rã latency và tìm chứng cứ plan change |
| "Dùng sort theo createdAt là ổn định tuyệt đối" | Nhiều document có cùng timestamp | Thêm tie-breaker duy nhất như _id |
| "Tạo index càng nhiều càng tốt" | Index tốn RAM, disk và chi phí ghi | Thiết kế theo query pattern quan trọng |

### 21.1. Vì sao không nên suy ra hash từ query string?

Xét hai biểu thức:

~~~javascript
db.orders.find({ status: "NEW" });

db.orders.find({
  status: { $eq: "NEW" }
});
~~~

Chuỗi JavaScript/JSON của chúng khác nhau, nhưng về ý nghĩa điều kiện đều là so sánh bằng. Planner có bước chuẩn hóa, vì vậy việc tự băm raw query string không cho bạn một định danh shape đáng tin cậy.

Nếu cần theo dõi lâu dài, ứng dụng có thể đặt **tên nghiệp vụ cho query pattern** (ví dụ "orders-by-status-newest") và đối chiếu với định danh do MongoDB trả về. Tên nghiệp vụ giúp các dashboard dễ đọc mà không phải đoán thuật toán hash bên trong.

### 21.2. Plan change và hiệu năng xấu không có quan hệ một-một

Có ít nhất bốn tình huống:

| Có đổi plan? | Có chậm hơn? | Diễn giải có thể xảy ra |
|---|---|---|
| Không | Không | Workload ổn định |
| Không | Có | Cùng plan nhưng số record cần đọc tăng, tài nguyên thiếu hoặc giá trị query khác |
| Có | Không | Planner thích ứng thành công với dữ liệu/index mới |
| Có | Có | Plan mới không thuận lợi với workload hoặc môi trường vẫn bị nghẽn |

Vì thế, một lần đo latency không đủ để xác định plan cache là thủ phạm. Cần đối chiếu plan, dữ liệu, chỉ số thực thi và thời điểm thay đổi.

## 22. Bài tập thực hành

Các bài tập dựa trên database **query_plan_lab** và collection **orders/skewOrders** đã tạo trong bài. Những thao tác tạo index, đổi dữ liệu hoặc clear cache chỉ thực hiện trong môi trường thực hành mà bạn sở hữu. Không dùng trực tiếp dữ liệu production để học.

### Bài 1. Nhận diện query shape

Cho các truy vấn:

~~~javascript
// A
db.orders.find({ status: "NEW" })
  .sort({ createdAt: -1 });

// B
db.orders.find({ status: "FAILED" })
  .sort({ createdAt: -1 });

// C
db.orders.find({ status: "NEW", tenantId: "T-A" })
  .sort({ createdAt: -1 });

// D
db.orders.find({ status: "NEW" })
  .sort({ totalCents: -1 });

// E
db.orders.find(
  { status: "NEW" },
  { _id: 0, createdAt: 1 }
).sort({ createdAt: -1 });
~~~

**Câu hỏi:**

1. Cặp nào có cấu trúc filter/sort giống nhau nhưng literal khác nhau?
2. Vì sao C khác A về cấu trúc điều kiện?
3. Vì sao D và E cần được xem xét khác A?
4. Có nên tự khẳng định mọi cặp khác nhau chắc chắn có hash khác nhau mà chưa xem MongoDB server không?

**Định hướng:** A và B là hai truy vấn cùng pattern thông dụng; C thêm tenantId, D đổi sort và E đổi projection. Khi kiểm chứng shape hash chính xác, dùng thông tin server trả về theo phiên bản.

### Bài 2. Chọn index ứng viên

Truy vấn:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).limit(20);
~~~

So sánh:

~~~javascript
{ status: 1 }
{ createdAt: -1 }
{ status: 1, createdAt: -1 }
~~~

Hãy chỉ ra index nào có cấu trúc giúp lọc status rồi trả createdAt theo thứ tự. Giải thích trường hợp index chỉ trên status có thể cần bước SORT, còn index chỉ trên createdAt có thể phải kiểm tra nhiều status khác.

**Định hướng:** compound index **{status:1,createdAt:-1}** thường là ứng viên phù hợp với filter equality + sort. Nhưng quyết định cuối cùng phụ thuộc data volume và query planner.

### Bài 3. Phân biệt shape hash và planCacheKey

Giả sử ứng dụng không đổi filter/sort/projection, nhưng quản trị viên tạo thêm index phù hợp. Trả lời:

1. Query shape về logic có đổi không?
2. planCacheKey có thể đổi không?
3. Vì sao?
4. Có thể dùng hash của chuỗi JSON truy vấn để thay thế planCacheShapeHash không?

**Định hướng:** shape giữ cấu trúc; planCacheKey có thể đổi vì tập index khả dụng đổi; không tự tính shape hash bằng raw query string.

### Bài 4. Explain và cache

Chạy:

~~~javascript
db.orders.find({
  status: "FAILED"
}).sort({
  createdAt: -1
}).explain("executionStats");
~~~

Rồi:

~~~javascript
db.orders.aggregate([
  { $planCacheStats: {} }
]);
~~~

**Câu hỏi:** Có thể dùng việc thực thi explain ở lệnh thứ nhất làm bằng chứng đã warm plan cache không? Nếu không có entry ở lệnh thứ hai, có thể kết luận query chạy lỗi hoặc không sử dụng index không?

**Đáp án định hướng:** Không. Explain bỏ qua cache và không thêm entry. Không thấy entry có nhiều nguyên nhân, cần tách việc xem kế hoạch ứng viên khỏi trạng thái cache runtime.

### Bài 5. Data skew và lựa chọn plan

Giả sử trước khi có sự cố:

~~~text
NEW    = 99%
FAILED = 1%
~~~

Sau sự cố:

~~~text
NEW    = 40%
FAILED = 60%
~~~

Hãy giải thích:

1. Truy vấn status = FAILED có thể tăng số document khớp bao nhiêu theo tỷ lệ?
2. Nếu ứng dụng không đổi query, query shape có thể vẫn giữ nguyên không?
3. MongoDB có chắc chắn replan ngay trong lần chạy sau không?
4. Việc plan không đổi có đủ chứng minh latency không thể tăng không?

**Định hướng:** Tỷ trọng FAILED tăng từ 1% lên 60%; nếu tổng số document không đổi, số record FAILED tăng khoảng 60 lần. Shape có thể giữ nguyên; server không bảo đảm replan tức thì; cùng plan có thể phải đọc nhiều dữ liệu hơn.

### Bài 6. Đọc executionStats

Giả sử hai phương án được đo trên cùng dữ liệu và request tương đương:

| Chỉ số | Plan X | Plan Y |
|---|---:|---:|
| nReturned | 20 | 20 |
| totalKeysExamined | 15.000 | 25 |
| totalDocsExamined | 14.000 | 20 |
| SORT riêng | Có | Không |

**Câu hỏi:** Plan nào có dấu hiệu đọc ít dữ liệu và ít sort hơn? Có thể khẳng định plan đó chắc chắn nhanh hơn trong mọi điều kiện chỉ từ bảng này không?

**Định hướng:** Plan Y có dấu hiệu thuận lợi hơn về keys/docs examined và sort, nhưng cần đo latency, tài nguyên, index size, concurrency và chi phí ghi trên workload thực. Bảng chỉ minh họa cách suy nghĩ về chỉ số, không phải kết quả đo của collection đã tạo.

### Bài 7. Tạo dữ liệu lệch rồi thay đổi phân bố

Sử dụng **skewOrders** trong phần thực hành:

1. Xem số NEW và FAILED ban đầu.
2. Chạy explain cho filter NEW và FAILED với cùng sort/limit.
3. Thực hiện updateMany trong phần 12.4 trên collection thử nghiệm.
4. Xem lại phân bố.
5. Chạy lại explain.
6. Quan sát $planCacheStats nếu có entry.

Viết một nhận xét ngắn phân biệt:

- **Điều đã đo được**: phân bố, winningPlan, keys/docs examined.
- **Giả thuyết**: thay đổi dữ liệu gây plan change.
- **Điều chưa thể kết luận chỉ bằng explain**: cached plan nào thực sự đã được dùng trong request thông thường.

### Bài 8. So sánh xóa cache với tạo index

Một truy vấn chậm vì không có index phù hợp với bộ lọc **tenantId = ..., status = ...** và sort **createdAt DESC**.

Hãy trả lời:

1. Nếu chỉ clear plan cache mà không thay đổi index, có tạo ra phương án index mới không?
2. Index ứng viên nên có những field nào?
3. Vì sao phải cân nhắc chi phí ghi khi thêm index?
4. Khi nào nên thử hint để chẩn đoán?

**Định hướng:** Clear cache không tạo index. Có thể cân nhắc **{tenantId:1,status:1,createdAt:-1}**. Index có chi phí lưu trữ/ghi; hint dùng có chủ đích để kiểm tra một kế hoạch, không phải biện pháp ép mặc định.

### Bài 9. Phân tích sự cố thực tế

Một endpoint có dấu hiệu:

~~~text
Tuần trước: p95 80 ms
Tuần này:  p95 800 ms
Query pattern: orders theo tenantId + status, sort createdAt
Số record từ tenant lớn tăng mạnh
Vừa có đợt deploy bổ sung index
~~~

Hãy viết kế hoạch điều tra gồm ít nhất:

- Lấy query shape và các thông số filter/sort/projection/limit.
- Kiểm tra phân bố dữ liệu theo tenant/status.
- Xem index trước/sau deploy.
- Quan sát explain theo request đại diện.
- Kiểm tra log/profiler/APM và $planCacheStats nếu hỗ trợ.
- Phân biệt regression của query plan với nghẽn tài nguyên.
- Đề xuất đo lại sau chỉnh sửa.

**Điểm quan trọng:** Có hai thay đổi cùng lúc (dữ liệu và index). Không được khẳng định một trong hai là nguyên nhân duy nhất nếu chưa có chứng cứ.

### Bài 10. Những câu đúng/sai

Đánh giá và giải thích:

1. Plan cache lưu nguyên danh sách document đã trả cho query shape.
2. Hai truy vấn khác literal nhưng cùng cấu trúc có thể cùng shape.
3. planCacheKey luôn giữ nguyên khi tạo thêm index.
4. explain("executionStats") có thể sử dụng để xem các chỉ số của một kế hoạch.
5. Chạy explain liên tục là cách được bảo đảm để làm nóng plan cache.
6. Cache entry Active bảo đảm truy vấn sẽ luôn nhanh.
7. Data skew có thể làm cùng một query pattern chạy khác chi phí.
8. Một kế hoạch bị đổi luôn có nghĩa MongoDB gặp lỗi.

**Đáp án:** (1) Sai; (2) Đúng trong những trường hợp thông dụng; (3) Sai; (4) Đúng; (5) Sai; (6) Sai; (7) Đúng; (8) Sai.

## 23. Cách ghi nhớ để áp dụng

Có thể tóm tắt quan hệ giữa các khái niệm:

~~~text
Query shape
  = "Ứng dụng đang hỏi theo cấu trúc nào?"
                    |
                    v
Indexes + query planner
  = "Có những con đường nào để tìm và sort dữ liệu?"
                    |
                    v
Plan cache
  = "Kế hoạch nào đã được chọn để có thể tái sử dụng?"
                    |
                    v
Runtime feedback / data distribution
  = "Kế hoạch đó còn phù hợp ở thời điểm hiện tại?"
                    |
            +-------+-------+
            |               |
           Có              Không / điều kiện đổi
            |               |
       Tiếp tục dùng       Có thể replan,
       khi phù hợp         invalidation hoặc đổi plan
~~~

**Năm nguyên tắc cốt lõi:**

1. **Query shape mô tả cấu trúc, không mô tả độ chọn lọc.** Hai giá trị khác nhau có thể tạo workloads khác nhau dù shape tương tự.
2. **Plan cache nhớ cách thực thi, không nhớ kết quả.** Dữ liệu vẫn được đọc ở mỗi lần truy vấn và cache là trạng thái có thể thay đổi.
3. **Dữ liệu biến động có thể làm plan cũ kém hiệu quả**, nhưng không có cam kết replan ngay tức thì cho mọi thay đổi.
4. **explain() và $planCacheStats trả lời hai câu hỏi khác nhau.** Explain phân tích cách planner xây dựng/thực thi kế hoạch ở chế độ chẩn đoán; planCacheStats cho biết những entry cache hiện tại trong phạm vi quan sát.
5. **Tối ưu là quá trình đo và kiểm chứng.** Xem data skew, index, filter, sort, projection, limit, kế hoạch, keys/docs examined và latency của hệ thống trước khi can thiệp.

Khi biết tách **query shape**, **kế hoạch đang có**, **phân bố dữ liệu** và **trạng thái cache**, bạn có thể điều tra một truy vấn MongoDB bị chậm đi mà không phải vội xóa cache hoặc ép hint. Cách tiếp cận tốt là thu thập chứng cứ, chọn index/query pattern phù hợp, đo lại trong workload đại diện và theo dõi khả năng thích ứng khi dữ liệu tiếp tục tăng trưởng.
