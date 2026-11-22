# Tính phân biệt, phân bố giá trị và hiệu quả lọc

## 1. Vì sao cùng một chỉ mục có lúc rất nhanh, có lúc gần như không giúp gì?

Giả sử ứng dụng bán hàng lưu 10 triệu đơn trong một cơ sở dữ liệu NoSQL. Hai yêu cầu truy vấn:

**Truy vấn A:** Tìm đơn có orderId = O1001.

**Truy vấn B:** Tìm tất cả đơn có status = PAID.

Nếu orderId là định danh duy nhất, truy vấn A thường chỉ cần định vị một bản ghi. Nhưng nếu 75% đơn có status = PAID, truy vấn B có thể phải xử lý 7,5 triệu bản ghi dù đã có chỉ mục trên status.

Vậy **có chỉ mục** chưa đủ. Hiệu quả của một đường truy cập còn phụ thuộc:

- **Tính phân biệt (cardinality, number of distinct values):** Một trường có bao nhiêu giá trị khác nhau?
- **Phân bố giá trị (value distribution):** Các giá trị xuất hiện đều nhau hay có một vài giá trị áp đảo?
- **Độ chọn lọc của điều kiện lọc (predicate selectivity):** Một điều kiện giữ lại bao nhiêu phần trăm bản ghi?
- **Mẫu truy vấn (access pattern):** Lọc, sắp xếp, giới hạn số kết quả và phân trang theo khóa nào?
- **Kiến trúc NoSQL:** Trường nào là partition key, sort/clustering key, secondary index, và bộ lọc được áp dụng ở tầng nào?

Đây là bài học về **tính phân biệt, phân bố giá trị và hiệu quả lọc** trong chương **Chỉ mục và đường truy cập** của module **Database No SQL**.

**Mục tiêu:** Có thể ước lượng độ chọn lọc từ dữ liệu, nhận diện phân bố lệch và tương quan giữa các trường, thiết kế đường đọc trong MongoDB/DynamoDB/Cassandra/search engine, đọc chỉ số thực thi, và giải thích lúc nào nên hoặc không nên thêm chỉ mục.

## 2. Ba đại lượng không được nhầm lẫn

### 2.1. Số lượng bản ghi N

Giả sử một collection Orders có:

\[
N = 10.000.000\ \text{đơn hàng}.
\]

N là số bản ghi được xem xét trong **phạm vi phân tích**. Phạm vi đó có thể là toàn collection, một tenant, một partition hoặc một cửa sổ thời gian.

Chẳng hạn, tenant T17 có 200.000 đơn trong tháng 11, thì với truy vấn đã xác định tenant và tháng, phạm vi ứng viên có thể nhỏ hơn rất nhiều so với 10 triệu bản ghi toàn hệ.

### 2.2. Số giá trị phân biệt D (distinct cardinality/NDV)

NDV = *number of distinct values*, số giá trị khác nhau của một trường trong phạm vi được xét.

Ví dụ:

| Trường | Số giá trị phân biệt ước lượng | Nhận xét |
|---|---:|---|
| orderId | 10.000.000 | Gần như duy nhất nếu đúng ràng buộc định danh |
| status | 4 | Ít giá trị khác nhau |
| country | 50 | Số quốc gia trong dữ liệu ví dụ |
| customerId | 700.000 | Nhiều khách đặt hơn một đơn |
| tenantId | 5.000 | Tập khách hàng tổ chức |

**Cardinality cao** thường giúp điều kiện bằng một giá trị có khả năng thu hẹp kết quả. Nhưng điều đó chỉ là gợi ý khi chưa biết phân bố.

Đặc biệt, **NDV không phải số dòng sẽ trả về**, cũng không phải bảo đảm tính duy nhất. Một trường có nhiều giá trị khác nhau nhưng một giá trị cực kỳ phổ biến vẫn có thể lọc kém.

### 2.3. Độ chọn lọc p của một điều kiện

Trong bài này quy ước:

\[
p = \frac{\text{số bản ghi thỏa điều kiện}}{\text{số bản ghi trong phạm vi đang xét}}.
\]

Nếu p nhỏ, bộ lọc loại được nhiều bản ghi và gọi là **chọn lọc cao** theo nghĩa thực hành.

Ví dụ:

- p = 0,0001 (0,01% khớp): bộ lọc rất chọn lọc.
- p = 0,02 (2% khớp): bộ lọc tương đối chọn lọc.
- p = 0,75 (75% khớp): bộ lọc ít chọn lọc.

Một số tài liệu dùng từ *selectivity* cho một tỉ số có chiều ngược lại hoặc dùng chỉ số NDV/N; khi đọc tài liệu của sản phẩm, cần kiểm tra định nghĩa. Ở đây, **p luôn là tỉ lệ bản ghi sống sót sau lọc**.

Nếu biết N và p:

\[
\text{ExpectedMatches} \approx N \times p.
\]

Với N = 10 triệu, p = 0,1%:

\[
10.000.000 \times 0,001 = 10.000\ \text{bản ghi}.
\]

Đó vẫn là 10.000 bản ghi, không phải một bản ghi, dù 0,1% nghe có vẻ rất nhỏ.

## 3. Cardinality cao chưa chắc chọn lọc cao cho mọi giá trị

### 3.1. Ước lượng khi phân bố đồng đều

Nếu D giá trị xuất hiện **xấp xỉ đều nhau**, điều kiện equality trên một giá trị có:

\[
p \approx \frac{1}{D},\qquad
\text{ExpectedMatches} \approx \frac{N}{D}.
\]

Ví dụ 10 triệu đơn và 100.000 customerId, **nếu khách có số đơn đều nhau** thì trung bình mỗi khách 100 đơn.

Nhưng **giả định đồng đều** thường không đúng trong thực tế.

### 3.2. Phân bố lệch (skew)

Giả sử trường status trong 10 triệu đơn có phân bố:

| status | Số đơn | Tỉ lệ |
|---|---:|---:|
| PAID | 7.500.000 | 75% |
| PENDING | 1.800.000 | 18% |
| SHIPPED | 600.000 | 6% |
| FRAUD_REVIEW | 100.000 | 1% |
| **Tổng** | **10.000.000** | **100%** |

Status có NDV = 4. Nhưng điều kiện:

~~~text
status = PAID         -> giữ 75% dữ liệu.
status = FRAUD_REVIEW -> giữ 1% dữ liệu.
~~~

**Cùng một trường và một chỉ mục, hai giá trị có độ chọn lọc khác nhau tới 75 lần.**

Do đó, phát biểu “trường có cardinality thấp luôn không nên lập chỉ mục” là quá đơn giản. Một giá trị hiếm trong trường ít giá trị vẫn có thể mang tính chọn lọc cao.

### 3.3. Trường cardinality cao vẫn có heavy hitter

Giả sử tenantId có 5.000 giá trị, nhưng một tenant lớn chiếm 40% tổng đơn hàng. Query theo tenant lớn có thể chạm hàng triệu record, còn query theo tenant nhỏ chỉ trả vài trăm record.

~~~text
tenantId có 5.000 giá trị, nhưng:

T_BIG -> 4.000.000 đơn
T17   -> 200.000 đơn
T88   -> 80 đơn
...
~~~

Nếu dựa vào NDV để chia đều 10 triệu / 5.000 = 2.000 đơn/tenant, ước lượng cho T_BIG sẽ sai rất lớn.

**Hệ quả thiết kế:** Với NoSQL phân vùng, heavy hitter còn có thể tạo **hot partition**, không chỉ làm index ít chọn lọc.

### 3.4. Đuôi dài và phân bố kiểu Zipf

Nhiều dữ liệu thực tế có **long tail**:

- Một vài bài viết có hàng triệu lượt xem; rất nhiều bài chỉ có vài lượt.
- Một số sản phẩm bán cực nhiều; đa số sản phẩm bán ít.
- Một số tenant có khối lượng lớn; đa số tenant nhỏ.
- Một số tag xuất hiện rất thường xuyên; nhiều tag rất hiếm.

Hình dung:

~~~text
Số lần xuất hiện
^
|█
|██
|███
|████
|█████...
+------------------------> Giá trị theo thứ tự phổ biến
  vài giá trị lớn        đuôi dài giá trị hiếm
~~~

Trong phân bố này, trung bình theo NDV có thể che khuất sự khác biệt giữa các giá trị phổ biến và hiếm.

## 4. Phạm vi thống kê quyết định ý nghĩa của selectivity

### 4.1. Toàn hệ so với trong một tenant

Giả sử status = PENDING chiếm 18% toàn hệ. Nhưng tenant T17 vừa nhập dữ liệu và 90% đơn của T17 đang PENDING.

Khi truy vấn:

~~~text
tenantId = T17 AND status = PENDING
~~~

phải xét:

\[
P(\text{PENDING}\mid \text{tenantId=T17})
\]

chứ không chỉ lấy tỉ lệ PENDING toàn hệ.

Nếu tenant T17 có 200.000 đơn và 90% PENDING, kết quả dự kiến là:

\[
200.000 \times 0,9 = 180.000\ \text{đơn}.
\]

Đây là rất nhiều kết quả, dù có hai điều kiện bằng nhau.

### 4.2. Tính chọn lọc theo partition

Trong DynamoDB/Cassandra, truy vấn có thể định vị **một partition** bằng khóa chính. Khi đó, độ chọn lọc có ý nghĩa vận hành thường là **tỉ lệ lọc trong partition đã đọc**, không chỉ trên toàn bảng.

~~~text
Toàn bảng có 10 triệu đơn.
Partition tenant T17 có 200.000 đơn.
Filter status=PENDING giữ 180.000 đơn.
~~~

Đã tránh scan 10 triệu đơn, nhưng trong partition T17 vẫn phải xử lý tập rất lớn. Đó là lý do mô hình khóa phân vùng và clustering/sort key quan trọng hơn một predicate tùy ý.

### 4.3. Phân bố theo thời gian

Độ chọn lọc thay đổi theo giờ/ngày/tháng:

- Trong ngày thường chỉ 2% đơn PENDING.
- Ngay sau đợt khuyến mại, 60% đơn mới là PENDING.
- Đơn hơn một năm có thể gần như toàn PAID hoặc CLOSED.

Nếu chỉ thống kê toàn bộ lịch sử, ta có thể đánh giá sai bộ lọc trên **dữ liệu nóng gần đây**. Cần xem phân bố theo các cửa sổ thời gian mà API thực sự truy vấn.

## 5. Tương quan giữa các điều kiện lọc

### 5.1. Không nhân các tỉ lệ một cách mù quáng

Giả sử trong dữ liệu:

\[
P(\text{country=VN}) = 40\%.
\]

\[
P(\text{city=HCM}) = 10\%.
\]

Nếu **giả định độc lập**, ta ước lượng:

\[
P(\text{country=VN AND city=HCM})
\approx 0,4 \times 0,1 = 4\%.
\]

Nhưng nếu mọi bản ghi có city=HCM đều thuộc country=VN, giao của hai điều kiện thực ra là **10%**.

Sai lệch tới 2,5 lần dù mỗi tỉ lệ riêng lẻ đều đúng.

### 5.2. Điều kiện xác định nhau

Những cặp trường thường tương quan:

- country và city.
- tenantId và region.
- productCategory và brand.
- orderStatus và paidAt.
- accountType và permissions.
- eventType và payload fields.

Nếu country được xác định bởi city, thêm country vào điều kiện có thể giúp partitioning/authorization nhưng **không nhất thiết giảm số kết quả thêm lần nữa**.

### 5.3. Tương quan âm và điều kiện loại trừ

Giả sử orderStatus = PENDING luôn đồng nghĩa paidAt chưa tồn tại. Điều kiện:

~~~text
status = PENDING AND paidAt exists
~~~

có thể trả **0 bản ghi**, dù một phép nhân xác suất độc lập dự đoán nhiều bản ghi.

Phân tích điều kiện kết hợp cần hiểu ràng buộc nghiệp vụ, không chỉ thống kê từng field.

### 5.4. Tính p theo tập ứng viên thật

Với các điều kiện A và B:

\[
P(A\cap B) = P(A)\times P(B\mid A).
\]

Nếu một partition đã cố định tenantId, hãy đo tỉ lệ status PENDING **trong tenant đó**. Đó là điều kiện có ý nghĩa trực tiếp cho chi phí lọc tiếp theo.

## 6. Lọc có ba kiểu chi phí rất khác nhau

### 6.1. Lọc bằng khóa truy cập

Ví dụ tra cứu orderId theo primary key:

~~~text
GetByKey(orderId=O1001)
~~~

Hệ có thể định vị trực tiếp item/partition hoặc một phạm vi rất nhỏ. Đây là đường truy cập thường có chi phí dự đoán được, nếu khóa và topology được thiết kế đúng.

### 6.2. Lọc bằng secondary index

Ví dụ một B-tree/multikey/inverted index hỗ trợ tìm document ID từ giá trị field:

~~~text
Index(status) -> tập document có status=PENDING
               -> lấy document hoặc trả từ index.
~~~

Chi phí thường gồm:

- Duyệt cấu trúc index.
- Xử lý số lượng index entries phù hợp.
- Đọc document gốc nếu index không chứa đủ trường.
- Áp dụng các predicate còn lại.
- Sắp xếp và phân trang nếu thứ tự không được index hỗ trợ.

Vì vậy index trên một giá trị cực phổ biến có thể tạo ra nhiều thao tác hơn dự kiến.

### 6.3. Lọc sau khi đọc (post-read filtering)

Một số hệ như DynamoDB tách **KeyConditionExpression** và **FilterExpression**. Nếu filter chạy **sau khi các item đã được đọc**, nó có thể giảm payload trả về nhưng **không giảm tương ứng số item đã được hệ đọc để xét**.

Tương tự trong Cassandra, một predicate không thuộc đường khóa/chỉ mục có thể buộc hệ đọc/quét nhiều dữ liệu để lọc.

Đây là khác biệt cực kỳ quan trọng:

> **Một bộ lọc có tính chọn lọc cao ở kết quả không nhất thiết có hiệu quả cao ở đường đọc nếu engine chỉ áp dụng nó sau khi đọc tập dữ liệu lớn.**

## 7. Ví dụ chi phí: giảm kết quả chưa chắc giảm số bản ghi đọc

Giả sử tenant T17 có 200.000 đơn. Chỉ 200 đơn thuộc trạng thái FRAUD_REVIEW.

Filter trả:

\[
p = \frac{200}{200.000}=0,001=0,1\%.
\]

Nhưng có hai đường đọc:

**A. Query toàn bộ partition tenant rồi lọc status:**

~~~text
Candidate items read: 200.000
Items returned:       200
Tỉ lệ lọc:             0,1%
~~~

**B. Index/read model có khóa (tenantId, status):**

~~~text
Candidate items accessed: xấp xỉ 200
Items returned:           xấp xỉ 200
~~~

B có thể tiết kiệm rất nhiều việc đọc, tùy hệ, độ phủ index, paging và query shape.

Không thể kết luận chỉ từ **tỉ lệ kết quả nhỏ** rằng truy vấn A đã tối ưu. Cần biết **bao nhiêu dữ liệu được truy cập trước khi lọc**.

## 8. Có nên lập chỉ mục riêng cho trường ít giá trị?

### 8.1. Giá trị rất phổ biến

Nếu status=PAID chiếm 75% collection, một index đơn trên status có thể ít giúp cho truy vấn:

~~~text
Tìm tất cả đơn PAID.
~~~

Khi phải trả lượng dữ liệu rất lớn, chi phí đọc index rồi truy cập document có thể đáng kể. Trong các engine có bộ tối ưu, scan tuần tự hoặc một access path khác đôi khi phù hợp hơn. Trong nhiều NoSQL, API không hỗ trợ full scan hiệu quả cho đường đọc trực tuyến, vì thế câu hỏi còn là **có nên trả tất cả bản ghi đó qua một request hay không**.

### 8.2. Giá trị hiếm

Nếu status=FRAUD_REVIEW chỉ chiếm 1%, cùng index trên status có thể giúp thu hẹp đáng kể.

Tuy nhiên 1% của 10 triệu vẫn là 100.000 đơn. Nếu API chỉ cần 20 đơn gần nhất, cần thêm **thứ tự thời gian và giới hạn** thay vì đọc 100.000 rồi sort ở ứng dụng.

### 8.3. Index chọn lọc kết hợp

Truy vấn thực:

~~~text
tenantId = T17
status = FRAUD_REVIEW
createdAt >= đầu tháng
ORDER BY createdAt DESC
LIMIT 20
~~~

Một compound index hoặc read model theo **tenant + status + thời gian** thường phù hợp hơn index chỉ gồm status.

**Kết luận:** Không quyết định dựa trên “D cao hay thấp” một mình; phải nhìn tỉ lệ khớp của giá trị được hỏi, thứ tự, giới hạn, phân bố và dạng truy cập được hệ hỗ trợ.

## 9. Compound index: thứ tự trường quan trọng

### 9.1. Prefix của index

Một compound index:

~~~text
(tenantId, status, createdAt DESC)
~~~

đặt tenantId trước status rồi đến thời gian. Nó đặc biệt phù hợp với query xác định tenant và status, sau đó lấy các đơn theo thời gian.

Trong những engine có chỉ mục B-tree phù hợp, hệ có thể dùng **tiền tố index (leftmost prefix)** để tìm phạm vi hiệu quả. Nhưng không nên cho rằng index trên (tenantId, status, createdAt) tự phục vụ tốt mọi query chỉ có createdAt hoặc chỉ có status.

### 9.2. Điều kiện bằng, điều kiện khoảng và sắp xếp

Một nguyên tắc thường gặp trong thiết kế compound index MongoDB là cân nhắc:

- Các điều kiện **equality**.
- Các trường phục vụ **sort**.
- Các điều kiện **range**.

Thứ tự thực tế phụ thuộc truy vấn. Ví dụ:

~~~text
Filter:
  tenantId = T17
  status = PENDING
  createdAt >= 2026-11-01

Sort:
  createdAt DESC
  _id DESC

Limit: 20
~~~

Một index ứng viên:

~~~text
(tenantId ASC, status ASC, createdAt DESC, _id DESC)
~~~

Các điều kiện equality cố định tiền tố; các bản ghi trong phạm vi ấy được sắp theo createdAt rồi _id.

### 9.3. Thứ tự equality đôi khi linh hoạt, nhưng không phải luôn vậy

Nếu truy vấn luôn có cả tenantId và status bằng một giá trị, hai field equality đứng trước có thể đều hiệu quả. Nhưng nếu **các truy vấn khác chỉ lọc tenantId**, đặt tenantId trước status có lợi hơn về khả năng dùng prefix.

Vì vậy chọn index cho **tập workload**, không chỉ một truy vấn.

### 9.4. Range trước hay sau sort?

Khi truy vấn có hai trường range hoặc một range và sort trên trường khác, tối ưu lọc và tối ưu sort có thể cạnh tranh:

~~~text
price BETWEEN 100 AND 200
ORDER BY createdAt DESC
LIMIT 20
~~~

Index ưu tiên price có thể giảm ứng viên trước nhưng cần sort. Index ưu tiên createdAt có thể cung cấp thứ tự trước, nhưng phải quét nhiều entry để tìm sản phẩm đúng khoảng giá.

Không có thứ tự cố định tối ưu cho mọi phân bố và LIMIT. Hãy đo **keys/documents examined và sort stage** theo các giá trị thực.

## 10. MongoDB: index và độ chọn lọc trong một collection

### 10.1. Dữ liệu ví dụ

Một document Orders:

~~~javascript
{
  _id: "O1001",
  tenantId: "T17",
  customerId: "C001",
  status: "PENDING",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  totalMinor: 1590000,
  country: "VN"
}
~~~

Giả sử cần:

~~~javascript
db.orders.find(
  {
    tenantId: "T17",
    status: "PENDING",
    createdAt: {
      $gte: ISODate("2026-11-01T00:00:00Z")
    }
  },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalMinor: 1
  }
).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

### 10.2. Compound index theo query

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Index này dùng tiền tố tenantId/status để định vị tập phù hợp, đồng thời hỗ trợ sắp xếp theo createdAt và _id trong phạm vi các điều kiện bằng nhau.

Nhưng nếu ứng dụng còn có endpoint chỉ tìm theo customerId, index trên tenant/status/time không tự giải quyết truy vấn đó. Có thể cần index khác hoặc một read model theo khách hàng.

### 10.3. Đo bằng explain

~~~javascript
db.orders.find({
  tenantId: "T17",
  status: "PENDING"
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20).explain("executionStats");
~~~

Những trường thường đáng xem:

| Thông tin | Câu hỏi cần trả lời |
|---|---|
| winningPlan | Engine chọn access path nào? |
| IXSCAN / COLLSCAN | Có dùng index hay quét collection? |
| totalKeysExamined | Đã xét bao nhiêu index entries? |
| totalDocsExamined | Đã đọc bao nhiêu document? |
| nReturned | Trả bao nhiêu kết quả? |
| SORT stage | Có cần sort thêm ngoài index không? |
| executionTimeMillis | Thời gian ghi nhận trong lần thực thi; cần đặt trong ngữ cảnh |

**Một explain không phải kết luận hiệu năng tuyệt đối.** Thời gian bị ảnh hưởng cache, tải hệ thống, dữ liệu mẫu, phiên bản engine và điều kiện thử nghiệm. Sử dụng explain để hiểu access path, rồi đo p95/p99 trên workload phù hợp.

### 10.4. Tỉ lệ examined/returned

Nếu một truy vấn trả 20 nhưng đọc 500.000 document:

\[
\frac{500.000}{20}=25.000
\]

tức trung bình **25.000 document được xét cho mỗi kết quả trả về** trong lần chạy đó. Điều này là tín hiệu để kiểm tra lại index và query shape.

Ngược lại, nếu totalDocsExamined thấp nhưng totalKeysExamined rất cao, có thể index vẫn phải quét một phạm vi lớn trước khi tìm được kết quả.

### 10.5. Covered query

Nếu index có tất cả field cần lọc và trả về, một số truy vấn có thể được phục vụ từ index mà không phải tải document gốc theo cơ chế engine. Đây là **covered query**.

Nhưng thêm mọi field trả về vào compound index có thể khiến index lớn, chậm ghi, tốn RAM và disk. Cần cân bằng:

- Tỉ lệ truy vấn.
- Số document trả về.
- Kích thước dữ liệu thêm vào index.
- Chi phí cập nhật các field.
- Khả năng dùng index cho các query khác.

Không nên cố “cover mọi query” bằng các index cực rộng.

## 11. MongoDB: partial index, sparse index và giá trị hiếm

### 11.1. Partial index cho nhóm được hỏi thường xuyên

Giả sử giao diện vận hành chỉ cần **đơn PENDING**, còn PAID chiếm phần lớn và hiếm khi được truy vấn qua màn này.

~~~javascript
db.orders.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    partialFilterExpression: {
      status: "PENDING"
    }
  }
);
~~~

Index chỉ bao gồm những document thỏa điều kiện partial. Với truy vấn có điều kiện status=PENDING theo cách mà planner có thể chứng minh đủ điều kiện, index có thể nhỏ hơn index toàn bộ dữ liệu.

Nhưng query không có status=PENDING không thể tùy ý dùng partial index đó để trả đầy đủ kết quả, vì dữ liệu ngoài điều kiện **không nằm trong index**.

### 11.2. Partial index khác sparse index

**Sparse index** liên quan việc chỉ index những document có field được index theo quy tắc MongoDB, còn **partial index** cho phép diễn đạt một điều kiện lọc tập document linh hoạt hơn.

Với null/missing, các toán tử query và cơ chế index có ngữ nghĩa riêng. Không nên coi **field thiếu, field null và field chứa chuỗi rỗng** là cùng một trường hợp.

### 11.3. Vì sao giá trị hiếm đáng cân nhắc?

Nếu 1% đơn cần kiểm tra gian lận nhưng 99% không có trạng thái đó, partial index phù hợp với đúng đường đọc có thể tiết kiệm nhiều không gian index hơn so với việc index những đơn không bao giờ được query qua đường này.

Đổi lại, khi status chuyển sang hoặc rời khỏi FRAUD_REVIEW, engine phải cập nhật membership của index. Cần đo chi phí ghi và cấu trúc truy vấn thực tế.

## 12. MongoDB: mảng, multikey và điều kiện cùng phần tử

### 12.1. Field dạng mảng có phân bố khác scalar

Một sản phẩm:

~~~json
{
  "_id": "P101",
  "tags": ["nosql", "backend", "database"]
}
~~~

Một document có thể khớp **nhiều giá trị tag**, nên tổng tần suất xuất hiện của các tag có thể vượt số document. Tính NDV và selectivity cần phân biệt:

- Số tag khác nhau trên toàn tập.
- Số sản phẩm chứa từng tag.
- Số lần tag xuất hiện trong các phần tử.
- Số phần tử tag trung bình trên mỗi sản phẩm.

Nếu tags có trung bình 20 phần tử/document, một multikey index có thể chứa nhiều index entries tương ứng, tăng chi phí lưu và cập nhật.

### 12.2. Tạo multikey index

~~~javascript
db.products.createIndex({ tags: 1 });
~~~

Truy vấn:

~~~javascript
db.products.find({ tags: "nosql" });
~~~

Index có thể giúp tìm những document chứa tag này, nhưng hiệu quả phụ thuộc tag hiếm hay phổ biến và số lượng kết quả.

### 12.3. Điều kiện phải thuộc cùng phần tử

Xét:

~~~json
{
  "variants": [
    {"color": "red", "size": "M"},
    {"color": "blue", "size": "L"}
  ]
}
~~~

Query muốn tìm biến thể **đỏ và size L trong cùng biến thể**. Hai predicate dot path riêng có thể khớp từ **hai phần tử khác nhau**.

Trong MongoDB, dùng:

~~~javascript
db.products.find({
  variants: {
    $elemMatch: {
      color: "red",
      size: "L"
    }
  }
});
~~~

Document ví dụ không khớp, vì không phần tử nào đồng thời red và L.

**Hiệu quả lọc không có ý nghĩa nếu điều kiện lọc sai ngữ nghĩa.** Thiết kế index và đọc explain phải bắt đầu từ query trả đúng dữ liệu.

### 12.4. Giới hạn compound multikey

MongoDB có những hạn chế đối với compound multikey index liên quan nhiều trường mảng. Không nên giả định mọi tổ hợp array fields đều có thể đưa vào một compound index có chi phí hợp lý. Cần đối chiếu kiểu dữ liệu thực tế và các giới hạn của engine.

## 13. DynamoDB: Partition key, sort key và FilterExpression

### 13.1. Access path theo khóa là trọng tâm

DynamoDB tối ưu truy cập bằng primary key, có thể gồm partition key và sort key. Trong Query, **KeyConditionExpression** xác định partition key bằng equality và có thể thu hẹp phạm vi sort key theo những biểu thức được hỗ trợ.

Ví dụ một bảng:

~~~text
PK                    SK
-----------------------------------------------
TENANT#T17            ORDER#2026-11-14T09:00:00Z#O1001
TENANT#T17            ORDER#2026-11-14T08:50:00Z#O1002
TENANT#T88            ORDER#2026-11-14T08:00:00Z#O2001
~~~

Nếu query theo tenant T17, hệ đọc đúng tập item thuộc khóa đó, thay vì một scan toàn bảng.

### 13.2. FilterExpression áp dụng sau truy cập khóa

Ví dụ SDK JavaScript v3 với Document Client:

~~~javascript
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import {
  DynamoDBDocumentClient,
  QueryCommand
} from "@aws-sdk/lib-dynamodb";

const client = DynamoDBDocumentClient.from(
  new DynamoDBClient({ region: "ap-southeast-1" })
);

const result = await client.send(new QueryCommand({
  TableName: "Orders",
  KeyConditionExpression: "PK = :pk AND begins_with(SK, :prefix)",
  FilterExpression: "#s = :status",
  ExpressionAttributeNames: {
    "#s": "status"
  },
  ExpressionAttributeValues: {
    ":pk": "TENANT#T17",
    ":prefix": "ORDER#",
    ":status": "FRAUD_REVIEW"
  },
  Limit: 100
}));
~~~

**Điểm quan trọng:** Limit và giới hạn trang của Query áp dụng tới **item được xét trước FilterExpression**, không phải bảo đảm có 100 kết quả khớp status. FilterExpression loại item khỏi response sau khi đọc theo khóa; chi phí đọc không giảm chỉ vì ít item được trả về.

Nếu trong 100 item đầu không có FRAUD_REVIEW, response có thể có Items rỗng **nhưng vẫn có LastEvaluatedKey** để tiếp tục phân trang.

### 13.3. Vì sao filter hiếm có thể vẫn đắt?

Giả sử:

~~~text
Partition TENANT#T17:
  200.000 Orders
  200 Fraud reviews (0,1%)
~~~

Để tìm đủ 20 Fraud reviews theo thứ tự thời gian, một Query chỉ có PK rồi lọc status có thể phải đọc rất nhiều item ứng viên. Đây là trường hợp **predicate chọn lọc cao nhưng access path lọc kém**.

### 13.4. Chuyển status vào đường khóa

Một GSI có thể thiết kế:

~~~text
GSI1PK = TENANT#T17#STATUS#FRAUD_REVIEW
GSI1SK = 2026-11-14T09:00:00Z#O1001
~~~

Khi Query GSI1 theo đúng GSI1PK, hệ định vị những item thuộc tenant/status đó và lấy theo thứ tự thời gian của GSI1SK.

~~~javascript
const result = await client.send(new QueryCommand({
  TableName: "Orders",
  IndexName: "GSI1",
  KeyConditionExpression: "GSI1PK = :pk",
  ExpressionAttributeValues: {
    ":pk": "TENANT#T17#STATUS#FRAUD_REVIEW"
  },
  ScanIndexForward: false,
  Limit: 20
}));
~~~

**Phạm vi bảo đảm:** DynamoDB GSI được cập nhật bất đồng bộ và chỉ có eventually consistent reads. GSI phù hợp read model nếu độ trễ cập nhật được chấp nhận; nếu quyết định giao dịch/authorization yêu cầu mới nhất, cần nguồn có thẩm quyền.

### 13.5. GSI làm tăng chi phí ghi và lưu trữ

Một item Orders đổi status từ PENDING sang PAID. Nếu status nằm trong GSI partition key, entry GSI phải chuyển từ nhóm PENDING sang PAID. Đó là write amplification và tiêu thụ tài nguyên index.

Nếu status thay đổi liên tục, cần cân nhắc chi phí duy trì GSI so với lợi ích của đường Query chọn lọc.

### 13.6. Skew gây hot partition

GSI1PK = TENANT#T_BIG#STATUS#PENDING có thể chứa khối lượng rất lớn nếu T_BIG tạo hàng triệu đơn PENDING. Lựa chọn khóa ít giá trị hoặc tổ hợp có skew làm tăng nguy cơ hot key.

Có thể thêm bucket ngày hoặc shard, nhưng lúc đó một query bao quát nhiều ngày/shard phải đọc và hợp nhất nhiều partition. Không có thiết kế nào miễn phí cho cả ghi phân tán lẫn đọc một lần.

### 13.7. Count/ScannedCount và paging

Kết quả Query có thể cung cấp:

- Count: số item được trả sau lọc ở trang đó.
- ScannedCount: số item được xét trước filter trong phạm vi trang truy vấn.
- LastEvaluatedKey: điểm bắt đầu cho lần Query tiếp theo khi còn dữ liệu.

Trong tình huống Count rất thấp so với ScannedCount, cần xem lại đường khóa hoặc mô hình truy vấn. Tuy nhiên ScannedCount không phải mọi byte IO nội bộ; vẫn cần tính tới kích thước item, capacity units, GSI projection và workload.

## 14. Cassandra/ScyllaDB: partition key và clustering quan trọng hơn filter tùy ý

### 14.1. Mô hình chính theo tenant và ngày

~~~sql
CREATE TABLE orders_by_tenant_day (
    tenant_id text,
    order_day date,
    created_at timestamp,
    order_id text,
    status text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, order_day),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Truy vấn:

~~~sql
SELECT order_id, status, created_at
FROM orders_by_tenant_day
WHERE tenant_id = 'T17'
  AND order_day = '2026-11-14'
LIMIT 20;
~~~

Đường đọc tận dụng partition key và clustering order. Query “20 đơn mới nhất trong ngày” phù hợp mà không cần quét mọi tenant.

### 14.2. Filter trên status chưa được tổ chức thành khóa

Nếu muốn:

~~~text
tenant = T17
day = 2026-11-14
status = FRAUD_REVIEW
ORDER BY createdAt DESC
LIMIT 20
~~~

trường status trong ví dụ **không nằm trong primary key**. Không thể mặc định Cassandra sẽ lọc/định vị hiệu quả như một bộ tối ưu SQL có toàn bộ index liên quan. Một số truy vấn có thể đòi ALLOW FILTERING hoặc chỉ mục phụ theo tính năng, nhưng ALLOW FILTERING có thể khiến hệ đọc nhiều dữ liệu trước khi loại phần lớn.

### 14.3. Bảng theo truy vấn thứ hai

Nếu API status là đường đọc thường xuyên:

~~~sql
CREATE TABLE orders_by_tenant_status_day (
    tenant_id text,
    status text,
    order_day date,
    created_at timestamp,
    order_id text,
    total_minor bigint,
    PRIMARY KEY (
        (tenant_id, status, order_day),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total_minor
FROM orders_by_tenant_status_day
WHERE tenant_id = 'T17'
  AND status = 'FRAUD_REVIEW'
  AND order_day = '2026-11-14'
LIMIT 20;
~~~

Đường truy vấn dùng partition key đầy đủ, không cần quét toàn bộ đơn của ngày để lọc status.

### 14.4. Đánh đổi khi nhân bảng

Nếu một Order đổi status:

- Bảng chính cần cập nhật nguồn trạng thái.
- Bảng theo status cần xóa entry ở status cũ và tạo entry status mới nếu status thuộc primary key.
- Hai thao tác độc lập không tự là một transaction toàn vẹn trên mọi partition.
- Cần cơ chế đồng bộ, retry, idempotency và repair nếu chấp nhận eventual consistency ở read model.

Đó là cái giá để có một access path hiệu quả.

### 14.5. Secondary index và SAI

Một số phiên bản/triển khai Cassandra hỗ trợ **Storage-Attached Indexes (SAI)** hoặc cơ chế secondary index khác. Chúng có thể giúp các điều kiện không nằm trong primary key.

Nhưng phải xác minh:

- Hệ và phiên bản triển khai có hỗ trợ không?
- Điều kiện kết hợp nào được hỗ trợ?
- Có phục vụ thứ tự và LIMIT theo yêu cầu không?
- Kích thước partition, skew và cardinality có phù hợp không?
- Kế hoạch đọc thực tế và chi phí fan-out?

Không nên suy “có secondary index” nghĩa mọi điều kiện lọc tùy ý đều hiệu quả như partition-key lookup.

### 14.6. Low cardinality có thể tạo partition nóng

Nếu thiết kế partition key chỉ là status, toàn bộ đơn PAID có thể tập trung vào một tập khóa rất nhỏ. Với hàng triệu ghi, điều này có thể tạo hot partition và giới hạn mở rộng.

Trong wide-column store, partition key thường cần có **đủ tính phân biệt và phân phối tải phù hợp**, nhưng cũng phải giữ những dữ liệu được đọc cùng nhau. Thêm tenant + time bucket có thể giúp phân phối, đổi lại query nhiều thời gian cần đọc nhiều partition.

## 15. Search engine: inverted index và filter hiệu quả

### 15.1. Một giá trị ánh xạ tới danh sách document

Search engine như Elasticsearch/OpenSearch có thể dùng inverted index:

~~~text
status=PAID         -> doc1, doc2, doc3, ... rất nhiều
status=FRAUD_REVIEW -> doc105, doc900, ... ít hơn
country=VN          -> nhiều doc
~~~

Bộ lọc có thể xử lý các tập ID/bitset/postings để thu hẹp ứng viên mà không nhất thiết tải mọi document gốc theo một vòng lặp ở ứng dụng.

Tuy nhiên, giá trị phổ biến có postings lớn, và điều kiện cần kết hợp với range, sort, aggregation, phân shard, caching và phân bố dữ liệu.

### 15.2. Term query trên field keyword

Một truy vấn minh họa:

~~~json
{
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {"term": {"tenantId": "T17"}},
        {"term": {"status": "FRAUD_REVIEW"}},
        {
          "range": {
            "createdAt": {
              "gte": "2026-11-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "sort": [
    {"createdAt": {"order": "desc"}},
    {"orderId": {"order": "desc"}}
  ]
}
~~~

Ví dụ giả định tenantId, status, orderId được mapping phù hợp cho exact matching và sort, còn createdAt có kiểu date. Với field dạng text đã qua analyzer, term query có thể không khớp như mong muốn. Cần phân biệt **text search** với **lọc chính xác trên keyword/ID**.

### 15.3. Filter context và cache

Trong những search engine hỗ trợ bool filter context, điều kiện lọc thường không cần tính relevance score cho từng document như full-text query. Một số filter hoặc kết quả trung gian có thể được cache theo cơ chế engine, nhưng **không có nghĩa mọi filter đều luôn được cache**.

Nếu có 90% dữ liệu khớp một filter, engine vẫn phải xử lý tập lớn, đặc biệt khi query trả aggregation toàn bộ hoặc sort qua nhiều shard.

### 15.4. Nested field và hiệu quả lọc

Giả sử document có:

~~~json
{
  "variants": [
    {"color": "red", "size": "M"},
    {"color": "blue", "size": "L"}
  ]
}
~~~

Muốn lọc **color=red AND size=L trên cùng biến thể**, không thể tự tin rằng hai điều kiện trên các field object array mặc định bảo toàn ranh giới từng phần tử. Trong Elasticsearch/OpenSearch, kiểu nested cùng nested query có thể giúp giữ quan hệ giữa các field của một object con, nhưng tạo thêm chi phí index/query.

Vì vậy, phải xác minh **ngữ nghĩa kết quả trước khi tối ưu hiệu năng**.

## 16. Chỉ mục text, numeric, geo và vector có selectivity khác nhau

Không nên lấy một khái niệm “index” rồi áp dụng cùng mô hình chi phí cho mọi kiểu truy vấn.

| Loại truy vấn | Đường truy cập thường gặp | Chú ý |
|---|---|---|
| Equality ID | Primary key, hash/B-tree, partition lookup | Thường rất chọn lọc nếu ID duy nhất |
| Equality enum/status | B-tree/secondary index, posting list | Có thể rất phổ biến hoặc rất hiếm |
| Range thời gian/giá | Sorted index/clustering/sort key | Thứ tự, giới hạn và phân bố theo thời gian quan trọng |
| Full-text | Inverted index với analyzer | Token frequency và relevance khác exact match |
| Geo radius/bounding box | Spatial/geospatial index | Phân bố địa lý lệch và phải lọc hình học chính xác |
| Vector nearest neighbors | ANN/vector index | Tính gần đúng, recall và độ trễ; không chỉ p của equality |
| JSON nested array | Multikey/nested index | Số phần tử và điều kiện cùng phần tử quan trọng |

Ví dụ tìm 20 vector gần nhất không tương đương “lọc 1% bản ghi theo status”. ANN index được đánh giá bằng **recall@k, latency, độ chính xác và điều kiện lọc kết hợp**.

## 17. Cardinality của khóa phân vùng và cân bằng tải

### 17.1. Quá ít giá trị khóa

Nếu PK = status với 4 trạng thái, dữ liệu và lưu lượng ghi có thể bị dồn vào số khóa logic rất nhỏ. Dù hệ chia nội bộ theo cách riêng, một khóa nóng vẫn có thể hạn chế thông lượng hoặc làm query theo một partition quá nặng.

### 17.2. Quá nhiều giá trị không tự tốt

Nếu PK = orderId duy nhất, tra một đơn cực tốt. Nhưng truy vấn “20 đơn mới nhất của T17” sẽ cần một access path khác. Một partition key quá phân tán so với query có thể tạo **fan-out** nếu phải truy cập nhiều khóa.

### 17.3. Khóa tốt cân bằng ba mục tiêu

Một khóa phân vùng cần:

1. Định vị tập dữ liệu theo query.
2. Tránh partition khổng lồ/hot key theo tải thực.
3. Cho phép phân trang và sắp xếp hiệu quả khi kết hợp sort/clustering key.

Ví dụ:

~~~text
PK = TENANT#T17#DAY#2026-11-14
SK = TIME#2026-11-14T09:00:00Z#ORDER#O1001
~~~

Tổ chức này hữu ích cho “đơn theo tenant/ngày”, nhưng truy vấn cả tháng phải đọc nhiều partition ngày. Nếu thêm status vào PK, truy vấn không biết status có thể fan-out qua nhiều trạng thái.

**Mọi chỉ mục hoặc bảng tra phụ tối ưu một nhóm đường đọc sẽ tạo đánh đổi cho những đường đọc khác.**

## 18. Giá trị null, missing và sparse distribution

### 18.1. Một trường có thể thiếu hoặc rỗng

Ba document:

~~~json
{"orderId": "O1"}
~~~

~~~json
{"orderId": "O2", "fraudScore": null}
~~~

~~~json
{"orderId": "O3", "fraudScore": 0.97}
~~~

Không nên đếm D hoặc selectivity mà bỏ qua:

- Field không tồn tại.
- Field có null.
- Field có giá trị mặc định.
- Field có giá trị nhưng không hợp lệ.

Nếu chỉ 0,5% đơn có fraudScore, một index hoặc mô hình read chuyên dụng cho các đơn được chấm rủi ro có thể có ích hơn index toàn tập tùy query.

### 18.2. Predicate thiếu và null có ngữ nghĩa khác nhau theo hệ

MongoDB có những quy tắc query đặc thù cho null và field thiếu. DynamoDB có attribute_exists/attribute_not_exists trong biểu thức phù hợp nhưng FilterExpression sau Query vẫn không giảm reads. Cassandra và Redis lại có mô hình riêng.

Đừng coi mọi query:

~~~text
fraudScore = null
~~~

là đồng nghĩa “không có trường fraudScore” ở mọi cơ sở dữ liệu.

### 18.3. Biến động schema làm thay đổi selectivity

Sau khi triển khai tính năng fraud detection cho toàn bộ đơn mới, fraudScore từ chỗ hiếm trở thành phổ biến ở dữ liệu gần đây. Một thiết kế index dựa trên phân bố cũ có thể không còn tối ưu. Khi schema và workload tiến hóa, phân bố giá trị cũng thay đổi.

## 19. Đo phân bố dữ liệu bằng cách nào?

### 19.1. Histogram/tần suất theo giá trị

Thống kê hữu ích:

- Tổng bản ghi.
- NDV của từng field.
- Top K giá trị phổ biến.
- Tỉ lệ missing/null.
- Phân vị (percentiles) của field số/thời gian.
- Tần suất theo tenant, ngày, vùng.
- Phân bố có điều kiện của một field khi đã lọc field khác.

Không chỉ lưu giá trị trung bình; phải nhìn đuôi phân bố và heavy hitters.

### 19.2. Một truy vấn thống kê MongoDB minh họa

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

Truy vấn này có thể tốn kém trên collection rất lớn. Chạy trong môi trường phù hợp, thời điểm phù hợp hoặc dùng pipeline/số liệu đã tổng hợp.

Để lấy mẫu:

~~~javascript
db.orders.aggregate([
  { $sample: { size: 100000 } },
  {
    $group: {
      _id: "$status",
      countInSample: { $sum: 1 }
    }
  },
  { $sort: { countInSample: -1 } }
]);
~~~

Kết quả là **thống kê mẫu**, không phải đếm chính xác toàn tập. Mức sai số phụ thuộc cách lấy mẫu, kích thước và giá trị hiếm.

### 19.3. Những giá trị cực hiếm dễ bị bỏ sót

Nếu chỉ 0,001% bản ghi thuộc một trạng thái, mẫu 10.000 bản ghi kỳ vọng có:

\[
10.000 \times 0,00001 = 0,1\ \text{bản ghi}.
\]

Mẫu có thể không chứa giá trị đó dù toàn hệ có 100 bản ghi hiếm trên 10 triệu đơn. Vì thế đánh giá đường query cho giá trị hiếm bằng mẫu ngẫu nhiên nhỏ có thể sai.

Có thể dùng **stratified sampling**, số liệu nghiệp vụ, đếm chính xác có giới hạn hoặc metric đã tổng hợp để hiểu nhóm hiếm mà không quét hệ thống sản xuất tùy tiện.

### 19.4. Đếm distinct gần đúng

Trên tập dữ liệu cực lớn, có thể dùng những thuật toán như **HyperLogLog** để ước lượng NDV với chi phí bộ nhớ thấp theo độ chính xác xác định. Nhưng NDV ước lượng **không cho biết phân bố theo từng giá trị**, nên vẫn cần thống kê top K/histogram/conditional distribution.

## 20. Chọn chỉ số đo hiệu quả lọc

### 20.1. Đường đọc

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| Returned rows/items | Người dùng thực sự nhận bao nhiêu? |
| Examined keys/index entries | Index đã xét bao nhiêu phần tử? |
| Examined documents/items | Phải tải bao nhiêu bản ghi gốc? |
| Bytes read/transferred | Có đang tốn mạng và IO không? |
| Partitions/nodes touched | Truy vấn có fan-out không? |
| p50/p95/p99 latency | Độ trễ trên workload thật |
| Throughput/RCU/IO | Chi phí vận hành |
| Sort/aggregation work | Có phải sắp xếp/tính toán sau đọc không? |
| Cache hit ratio | Có phải chỉ nhanh nhờ cache tạm? |

### 20.2. Đường ghi

Thêm chỉ mục có chi phí:

- Dung lượng lưu trữ.
- Mỗi INSERT/UPDATE/DELETE phải duy trì index.
- Thời gian backfill.
- Có thể tăng contention hoặc write latency.
- Phục hồi/replication index.
- Hot key khi dữ liệu lệch.

Nếu một chỉ mục chỉ giúp một màn hình ít được dùng nhưng làm tăng tải ghi cho toàn bộ hệ, chưa chắc nó đáng duy trì.

### 20.3. Tỉ lệ index/record examined

Một chỉ báo:

\[
\text{WorkPerResult}
= \frac{\text{records examined}}{\max(1,\text{records returned})}.
\]

Nếu query trả 20 item nhưng engine xem xét 200.000, tỉ lệ là 10.000. Đây là dấu hiệu để xem access path, nhưng không phải một ngưỡng toàn cầu vì:

- Một index-only scan có chi phí khác việc đọc 200.000 document lớn.
- Truy vấn báo cáo tổng hợp có thể phải xử lý rất nhiều dữ liệu một cách hợp lý.
- Một query LIMIT 20 có ý nghĩa khác query cần đếm chính xác tất cả.

## 21. Tối ưu top-K, sắp xếp và phân trang

### 21.1. Chỉ cần 20 kết quả không có nghĩa chỉ đọc 20

Một query:

~~~text
status = FRAUD_REVIEW
ORDER BY createdAt DESC
LIMIT 20
~~~

có thể cần duyệt rất nhiều record nếu index chỉ trên status và việc sắp xếp theo createdAt phải làm sau đó. Index trên status + createdAt có thể cho đường đọc phù hợp hơn.

Tương tự, một DynamoDB Query có FilterExpression status rồi Limit 20 **không bảo đảm trả đủ 20 item khớp**, vì Limit áp dụng trước filter.

### 21.2. Keyset/cursor pagination

Nếu truy vấn lấy dữ liệu theo:

~~~text
createdAt DESC, orderId DESC
~~~

cursor nên phản ánh một khóa thứ tự ổn định, chẳng hạn (createdAt, orderId). Nhiều bản ghi có cùng timestamp thì orderId giúp phá hòa, tránh bỏ sót/trùng trong một số tình huống.

Tùy công nghệ:

- MongoDB có thể dùng range predicate theo cặp khóa.
- DynamoDB dùng LastEvaluatedKey.
- Cassandra driver có paging state.
- Search engine có search_after/PIT khi phù hợp yêu cầu.

Không nên tự coi offset 1 triệu kết quả luôn rẻ, đặc biệt ở hệ phải bỏ qua một tập dữ liệu lớn để đến trang sâu.

### 21.3. Paging không tự tạo snapshot cố định

Giữa trang 1 và trang 2 có thể có bản ghi mới/xóa/cập nhật status. Nếu nghiệp vụ đòi kết quả tại một thời điểm nhất quán, cần cơ chế snapshot/point-in-time/version được hệ hỗ trợ, không chỉ cursor.

## 22. Chiến lược chọn access path theo workload

### 22.1. Ghi lại các truy vấn thực

| Query | Filter | Sort | Limit | Tần suất | Yêu cầu độ mới |
|---|---|---|---:|---|---|
| Q1 | orderId | Không | 1 | Rất cao | Cần nguồn chính |
| Q2 | tenantId + status | createdAt DESC | 20 | Cao | Có thể trễ ngắn tùy nghiệp vụ |
| Q3 | customerId | createdAt DESC | 20 | Cao | Gần mới nhất |
| Q4 | tenantId + day | Không | Tổng hợp | Theo kỳ | Có thể dùng aggregate |
| Q5 | country + category | Giá tăng | 50 | Trung bình | Chấp nhận search eventual |

Không có một index tối ưu cả Q1–Q5 mà không có chi phí. Có thể dùng primary key cho Q1, một GSI/query table cho Q2, một đường đọc theo customer cho Q3 và search/read model chuyên biệt cho Q5.

### 22.2. Ưu tiên theo giá trị mang lại

Một cách ra quyết định:

1. Xác định truy vấn chậm hoặc tốn capacity nhất.
2. Xác định số result, số record examined và phân bố giá trị.
3. Đánh giá có thể giảm N+1, batch, cache hoặc chọn field nhỏ hơn không.
4. Xác định khóa/chỉ mục phù hợp với filter + sort + limit.
5. Tính write amplification và dung lượng bổ sung.
6. Đặt mức consistency và phương án backfill/repair.
7. Đo lại trên tập truy vấn và giá trị phổ biến/hiếm.

### 22.3. Tránh tối ưu trên một giá trị duy nhất

Chỉ thử tenant T88 có 80 đơn rồi kết luận index nhanh là không đủ. Cần thử cả:

- Tenant lớn nhất.
- Tenant trung bình.
- Tenant nhỏ.
- Status phổ biến và hiếm.
- Dữ liệu ngày hiện tại và lịch sử.
- Query có/không có sort.
- Phân trang sâu.

Một access path có thể tốt ở tenant nhỏ nhưng tạo hot partition ở tenant lớn.

## 23. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Xem cardinality cao luôn là index tốt | Bỏ qua heavy hitter và query shape | Đo phân bố từng giá trị |
| Xem cardinality thấp luôn vô ích | Bỏ qua giá trị hiếm | Xem tỉ lệ khớp của predicate |
| Ước lượng nhiều điều kiện bằng cách nhân p độc lập | Sai khi field tương quan | Đo phân bố có điều kiện |
| Chỉ đo nReturned | Không biết bao nhiêu item đã đọc | Đo examined/ScannedCount/bytes |
| Dùng DynamoDB FilterExpression như index | Đọc nhiều nhưng trả ít | Thiết kế KeyCondition/GSI |
| Dùng Cassandra ALLOW FILTERING không xét chi phí | Quét nhiều partition/row | Query table/index phù hợp |
| Đặt PK=status | Dồn tải vào ít khóa | Ghép tenant/time/shard theo workload |
| Dùng orderId làm mọi partition key | Khó liệt kê theo tenant/time | Thêm access path đúng query |
| Bỏ sort/limit khi thiết kế index | Engine cần sort rộng | Compound index có thứ tự |
| Thêm index cho mọi field | Tăng tải ghi, disk và backfill | Ưu tiên đường đọc thực tế |
| Không xét null/missing | Thống kê sai, query khác nghĩa | Phân loại giá trị rõ |
| Dùng sample nhỏ cho giá trị cực hiếm | Không thấy nhóm dữ liệu quan trọng | Lấy mẫu phân tầng hoặc số liệu chính xác |
| Coi query index-only mặc định | Vẫn phải đọc document gốc | Đo covered query và examined docs |
| Không xem phân bố theo tenant/time | Query lúc tải cao chậm bất ngờ | Thống kê theo phạm vi |
| Bỏ qua GSI eventual | Ra quyết định trên dữ liệu cũ | Xác minh nguồn khi cần |
| Dùng array predicates không cùng phần tử | Trả kết quả sai | $elemMatch/nested query |
| Chỉ thử query một lần trong cache nóng | Đánh giá sai p95/p99 | Đo nhiều tình huống tải |

## 24. Bài tập thực hành

### Bài 1. Tính NDV và độ chọn lọc

Collection có 12 triệu đơn:

| Trường | Giá trị | Số đơn |
|---|---|---:|
| status | PAID | 9.000.000 |
| status | PENDING | 2.400.000 |
| status | CANCELLED | 540.000 |
| status | FRAUD_REVIEW | 60.000 |

Hãy:

1. Tính NDV của status.
2. Tính p cho PAID, PENDING và FRAUD_REVIEW.
3. Xác định giá trị nào chọn lọc cao nhất.
4. Giải thích vì sao index status có thể hữu ích cho FRAUD_REVIEW nhưng ít lợi ích cho query trả toàn bộ PAID.

**Gợi ý:** FRAUD_REVIEW chiếm \(60.000/12.000.000=0,5\%\), còn PAID chiếm 75%.

### Bài 2. Cardinality cao nhưng phân bố lệch

Một bảng có 10 triệu bản ghi và 5.000 tenant. Tenant T_BIG có 4 triệu bản ghi, T_SMALL chỉ có 100.

1. Nếu giả định phân bố đều, số bản ghi/tenant ước lượng là bao nhiêu?
2. Sai lệch của giả định với T_BIG như thế nào?
3. Vì sao partition key chỉ là tenantId có thể có vấn đề với T_BIG?
4. Đề xuất cách dùng bucket ngày hoặc shard, nêu đánh đổi khi cần truy vấn một tháng.

### Bài 3. Điều kiện tương quan

Trong 1 triệu khách:

- 40% có country=VN.
- 10% có city=HCM.
- Mọi city=HCM đều thuộc country=VN.

Hãy tính:

1. Số kết quả nếu dùng giả định độc lập.
2. Số kết quả đúng theo thông tin tương quan.
3. Vì sao index/query planner hoặc mô hình thống kê chỉ có NDV riêng từng field có thể ước lượng sai?

**Gợi ý:** Giả định độc lập cho 40.000, còn thực tế có 100.000.

### Bài 4. MongoDB compound index

Query:

~~~javascript
db.orders.find({
  tenantId: "T17",
  status: "PENDING",
  createdAt: { $gte: ISODate("2026-11-01T00:00:00Z") }
}).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Hãy:

1. Đề xuất compound index.
2. Giải thích vai trò của equality và thứ tự.
3. Nêu những trường trong explain("executionStats") cần xem.
4. Giải thích vì sao index đó không nhất thiết tối ưu query chỉ lọc customerId.

### Bài 5. DynamoDB FilterExpression

Partition TENANT#T17 có 200.000 item, chỉ 0,1% là FRAUD_REVIEW.

Một Query theo PK có FilterExpression=status FRAUD_REVIEW và Limit=100.

1. Query chắc chắn trả đủ 100 item FRAUD_REVIEW không?
2. Vì sao Count có thể bằng 0 dù LastEvaluatedKey còn?
3. ScannedCount và Count khác nhau ra sao?
4. Đề xuất GSI key phục vụ truy vấn “20 fraud reviews gần nhất”.
5. Nêu rủi ro eventual consistency của GSI.

### Bài 6. Cassandra query table

Một bảng lưu theo (tenantId, orderDay) và clustering createdAt DESC. API cần tìm 20 đơn PENDING trong ngày theo tenant.

Hãy:

1. Giải thích vì sao status không thuộc key gây bất lợi.
2. Đề xuất bảng thứ hai với partition key (tenantId, status, orderDay).
3. Nêu cách xử lý khi status PENDING chuyển sang PAID.
4. Giải thích vì sao một bảng nhân theo query làm tăng chi phí ghi.
5. Phân tích hot partition nếu một tenant tạo hàng triệu PENDING trong cùng ngày.

### Bài 7. Index riêng cho giá trị hiếm

Trong MongoDB, 1% đơn có status=FRAUD_REVIEW. Giao diện chỉ truy cập nhóm đó, theo tenant và createdAt mới nhất.

Hãy đề xuất partial index và điều kiện query đủ để index được sử dụng. Vì sao một query không lọc FRAUD_REVIEW không được tùy ý dùng partial index này để trả đầy đủ dữ liệu?

### Bài 8. Điều kiện trên mảng

Document:

~~~json
{
  "variants": [
    {"color": "red", "size": "M"},
    {"color": "blue", "size": "L"}
  ]
}
~~~

Ứng dụng cần tìm sản phẩm có **một biến thể red, size L**.

1. Vì sao hai điều kiện dot path riêng có thể khớp sai?
2. Viết query MongoDB dùng $elemMatch.
3. Với Elasticsearch, vì sao cần xem xét nested mapping/query?
4. Nêu chi phí bổ sung của việc index mảng nhiều phần tử.

### Bài 9. Thiết kế benchmark chọn lọc

Hãy lập một bộ test gồm:

- Một tenant lớn, một tenant trung bình, một tenant nhỏ.
- Một status phổ biến, một status hiếm.
- Query giới hạn 20, query lấy nhiều kết quả, query sắp theo thời gian.
- Dữ liệu hiện tại và lịch sử.

Ghi lại returned rows, examined keys/docs, bytes, partitions touched, p95/p99 latency và chi phí ghi/index. Dựa trên kết quả, giải thích khi nào nên dùng compound index, partial index hoặc bảng query riêng.

## 25. Tổng kết

**Tính phân biệt, phân bố giá trị và hiệu quả lọc** là ba phần của cùng một quyết định thiết kế access path:

1. **Cardinality/NDV** cho biết có bao nhiêu giá trị khác nhau, nhưng không nói mỗi giá trị phổ biến tới đâu.
2. **Phân bố** cho biết heavy hitter, long tail, giá trị hiếm, null/missing và biến động theo tenant/thời gian.
3. **Độ chọn lọc** cho biết phần dữ liệu còn lại sau một predicate trong phạm vi truy vấn, nhưng không tự nói engine đã đọc bao nhiêu trước khi lọc.
4. **Tương quan điều kiện** khiến phép nhân các tỉ lệ độc lập có thể sai nghiêm trọng.
5. **Access path quyết định chi phí thực tế:** Primary key, compound index, GSI, query table, multikey hay inverted index có phạm vi và mức bảo đảm khác nhau.
6. **Lọc và sắp xếp phải được xem cùng nhau.** LIMIT 20 không tự làm truy vấn nhanh nếu hệ phải đọc/sort hàng trăm nghìn ứng viên.
7. **Chỉ mục có giá:** Storage, write amplification, consistency, backfill và nguy cơ hot partition.
8. **Đo đạc trên phân bố thực** quan trọng hơn suy đoán theo một giá trị hoặc một truy vấn trong cache nóng.

Câu hỏi đúng không chỉ là “trường này có nhiều giá trị khác nhau không?” mà là **“Với giá trị và tổ hợp điều kiện người dùng thực sự truy vấn, hệ sẽ truy cập bao nhiêu dữ liệu, ở những partition nào, theo thứ tự nào và với chi phí vận hành ra sao?”**
