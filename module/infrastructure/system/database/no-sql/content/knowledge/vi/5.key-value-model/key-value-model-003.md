# Tra cứu chính xác, truy vấn theo khoảng và các giới hạn cần kiểm tra

Trong mô hình **khóa–giá trị (key–value)**, thao tác đơn giản nhất là biết một khóa rồi lấy giá trị tương ứng. Ví dụ, ứng dụng đã biết mã phiên đăng nhập **S-183** và cần đọc trạng thái phiên đó. Đường truy cập trực tiếp theo khóa thường là lý do quan trọng để chọn mô hình key–value.

Tuy nhiên, yêu cầu thực tế hiếm khi chỉ có “lấy đúng một khóa”. Một sản phẩm có thể cần **20 đơn hàng mới nhất của khách**, **mọi sự kiện trong khoảng thời gian**, **các sản phẩm có giá từ A đến B**, hoặc **lấy lần lượt toàn bộ dữ liệu để xuất báo cáo**. Những yêu cầu này đặt ra câu hỏi khác: hệ thống có thể **duyệt khóa có thứ tự** không, thứ tự đó tồn tại trong phạm vi nào, có chỉ mục nào, và khi tải tăng thì chi phí ra sao?

Không phải mọi kho key–value đều hỗ trợ truy vấn khoảng như nhau. Có hệ chỉ hỗ trợ tìm bằng khóa chính; có hệ lưu khóa theo thứ tự và cung cấp iterator; có hệ tổ chức dữ liệu theo **partition key + sort key**, cho phép truy vấn khoảng trong một phân vùng; có hệ cung cấp cấu trúc sorted set hoặc chỉ mục phụ. Bài học này hướng dẫn cách phân biệt những khả năng đó, thiết kế khóa và kiểm tra giới hạn trước khi chọn giải pháp.

## 1. Mô hình khóa–giá trị cho chúng ta điều gì?

Ở mức logic, một kho key–value quản lý ánh xạ:

~~~text
key                     value
--------------------------------------------------------
session:S-183           { userId: "U-12", active: true }
order:T-01:O-1042       { customerId: "C-27", total: 530000 }
inventory:SKU-07        { available: 42, version: 9 }
feature:T-01:checkout   { enabled: true }
~~~

Các thao tác thường gặp:

| Thao tác | Ý nghĩa | Câu hỏi cần xác minh |
|---|---|---|
| **GET(key)** | Đọc giá trị gắn với đúng khóa | Khóa không tồn tại trả gì? Đọc từ replica có thể cũ không? |
| **PUT(key, value)** | Tạo hoặc ghi giá trị cho khóa | Có ghi đè mặc định không? Có kiểm tra version được không? |
| **DELETE(key)** | Xóa hoặc đánh dấu xóa một khóa | Xóa có hiển thị ngay ở mọi replica/cache không? |
| **MGET / batch get** | Đọc nhiều khóa biết trước | Có giới hạn số khóa, tổng payload, ordering không? |
| **Conditional update / CAS** | Chỉ ghi khi điều kiện/version đúng | Điều kiện có nguyên tử trong phạm vi khóa không? |
| **SCAN / iterator / range** | Duyệt một tập khóa | Duyệt theo thứ tự hay không? Trong toàn kho hay một partition? |
| **TTL / expiry** | Cho khóa hết hạn | Hết hạn vật lý và hết hạn quan sát được có cùng thời điểm không? |

Đây là các **khả năng cần tìm hiểu**, không phải hợp đồng API chung được mọi sản phẩm cung cấp. Tên phương thức, kiểu dữ liệu, ranh giới nhất quán và transaction phụ thuộc hệ quản trị.

### 1.1. Tra cứu chính xác khác với tìm kiếm theo thuộc tính

Với khóa **order:T-01:O-1042**, ứng dụng có thể đọc trực tiếp:

~~~text
GET("order:T-01:O-1042")
    → { customerId: "C-27", total: 530000, ... }
~~~

Nhưng câu hỏi “các đơn của khách C-27” **không xác định một khóa đơn hàng cụ thể**. Nếu customerId chỉ nằm bên trong value, kho key–value thuần túy không tự có đường truy cập theo thuộc tính đó.

Để trả lời, hệ thống có thể cần:

- **Chỉ mục thứ cấp** hỗ trợ tra cứu theo customerId.
- **Một tập khóa phụ** ánh xạ customerId đến các orderId.
- **Một read model** được sắp theo customerId và thời gian.
- **Quét dữ liệu rồi lọc**, chỉ nên dùng nếu tải và quy mô cho phép.

Điểm cốt lõi: **biết khóa** và **biết một trường trong giá trị** là hai bài toán khác nhau. Một thao tác GET rất nhanh không chứng minh truy vấn lọc theo value cũng nhanh.

### 1.2. Chi phí GET có điều kiện

Trong nhiều hệ key–value, GET theo khóa được tối ưu để truy cập một mục với số thao tác tương đối nhỏ. Nhưng nói “GET luôn có độ phức tạp O(1) và mất 1 ms” là quá đơn giản.

Thời gian thực tế còn phụ thuộc:

- Cấu trúc lưu trữ nội bộ: hash, B-tree, LSM-tree, chỉ mục trên bộ nhớ, cache.
- Định tuyến đến node/partition sở hữu khóa.
- Cache hit hay phải đọc SSD/disk.
- Kích thước value, nén và serialization.
- Replication và mức nhất quán mong muốn.
- Tranh chấp khóa nóng, queue, throttling và network RTT.

Vì vậy, **đo p95/p99 GET trên workload đại diện** có giá trị hơn việc suy luận từ nhãn “key–value”.

## 2. Truy vấn theo khoảng thực chất là truy vấn gì?

**Range query** lấy những bản ghi có khóa hoặc trường sắp xếp nằm trong một khoảng có thứ tự, ví dụ:

~~~text
Tất cả sự kiện từ 08:00 đến trước 09:00.
20 đơn mới nhất trong tháng 11 của khách C-27.
Sản phẩm có giá từ 100.000 đến 200.000 đồng.
Các khóa bắt đầu bằng tiền tố "invoice:T-01:202611:".
~~~

Muốn thực hiện hiệu quả, hệ thống phải có **một đường truy cập giữ được thứ tự thích hợp**. Dữ liệu không tự được sắp xếp chỉ vì khóa được đặt tên có chứa ngày, giá hay tenantId.

### 2.1. Ba kiểu hỗ trợ range thường gặp

| Cách lưu/truy cập | Tra cứu chính xác | Truy vấn khoảng | Giới hạn đáng chú ý |
|---|---|---|---|
| **Hash-oriented key–value** | Thường là điểm mạnh | Không mặc nhiên có thứ tự khóa; có thể phải scan hoặc tạo cấu trúc phụ | Scan không tương đương range có thứ tự; khó phân trang theo khoảng lớn |
| **Ordered key–value** | Hỗ trợ theo khóa | Có thể dùng seek/iterator để duyệt dãy khóa theo thứ tự so sánh | Phải hiểu thứ tự byte, phạm vi iterator, snapshot và chi phí duyệt |
| **Partition key + sort key** | Truy cập theo khóa/partition | Có thể truy vấn sort-key range trong partition theo quy tắc DB | Range thường **không** là khoảng toàn cục trên tất cả partition |
| **Key–value có index/sorted structure** | Hỗ trợ theo khóa | Có thể theo secondary index, sorted set hoặc view | Có chi phí ghi phụ và semantics consistency riêng |

Một cơ sở dữ liệu cụ thể có thể kết hợp nhiều hàng trên, nhưng không nên coi chúng tương đương.

### 2.2. Đừng nhầm SCAN với range query

Một số hệ cung cấp lệnh **SCAN** để duyệt dần không gian khóa. Điều đó không có nghĩa:

- Kết quả được sắp xếp tăng dần theo khóa.
- Có thể nhảy thẳng tới một khóa mốc bằng **seek**.
- Có thể dừng khi đã vượt khỏi khoảng cần tìm.
- Mỗi khóa xuất hiện đúng một lần khi có ghi/xóa đồng thời.
- Duyệt 10 triệu khóa chỉ để tìm 20 kết quả là rẻ.

**SCAN** có thể hữu ích cho bảo trì, thống kê, batch hoặc quản trị với cách sử dụng phù hợp. Còn màn hình cần 20 bản ghi mới nhất thường đòi hỏi một **chỉ mục hoặc tập dữ liệu đã được sắp đúng chiều truy vấn**.

### 2.3. Prefix query là trường hợp đặc biệt của range

Nếu kho lưu khóa theo thứ tự từ điển của byte và hỗ trợ truy vấn trong khoảng, các khóa có cùng tiền tố thường nằm liền nhau:

~~~text
order:T-01:202611:O-001
order:T-01:202611:O-002
order:T-01:202611:O-003
order:T-01:202612:O-004
order:T-02:202611:O-005
~~~

Ta có thể đọc prefix **order:T-01:202611:** bằng cách seek tới điểm bắt đầu rồi dừng khi tiền tố không còn khớp; hoặc dùng khoảng nửa mở **[startInclusive, endExclusive)** khi hệ hỗ trợ.

Tuy nhiên, điều này chỉ đúng trong **thứ tự so sánh khóa thực sự của hệ** và trong phạm vi mà các khóa có thể được scan. Với hệ phân vùng bằng hash, các khóa có cùng prefix có thể không nằm gần nhau ở tầng vật lý.

## 3. Thiết kế khóa cho tra cứu chính xác

Khóa phải phản ánh cách ứng dụng biết và phân biệt tài nguyên. Ví dụ một hệ nhiều tenant cần đọc đơn hàng theo tenant và orderId:

~~~text
order|T-01|O-1042  → order document
order|T-02|O-1042  → another tenant's order
~~~

Trong ví dụ, hai tenant có thể trùng orderId nhưng không trùng **khóa đầy đủ**.

### 3.1. Thành phần của một khóa tốt

| Thành phần | Vai trò | Cần lưu ý |
|---|---|---|
| **Namespace / entity type** | Phân biệt session, order, inventory | Tránh vô tình va chạm giữa các loại bản ghi |
| **Tenant / scope** | Phân định chủ sở hữu dữ liệu | Phải đi kèm kiểm tra quyền, không thay thế authorization |
| **Business identifier** | Xác định đúng mục | Unique trong phạm vi nào, có thay đổi không? |
| **Bucket / shard** (nếu dùng) | Phân bố tải hoặc quản lý vòng đời | Có làm tìm kiếm theo ID cần thêm bước định tuyến không? |
| **Version** (nếu cần) | Tạo bản ghi bất biến hoặc quản lý lịch sử | Khóa đọc phiên bản mới nhất được xác định bằng cách nào? |

Không có nghĩa mọi khóa phải chứa tất cả thành phần. Khóa ngắn và dễ định tuyến thường có lợi, nhưng **khả năng truy cập và tính duy nhất** quan trọng hơn hình thức.

### 3.2. Không tin tenantId chỉ vì nó có mặt trong khóa

Ví dụ API nhận:

~~~text
GET /tenants/T-02/orders/O-1042
~~~

Backend phải xác minh người gọi có quyền với **T-02** trước khi xây khóa và đọc. Nếu chỉ ghép tenantId từ request vào key rồi GET, một kẻ không có quyền vẫn có thể thử mã tenant khác.

Lược đồ an toàn ở mức ý tưởng:

~~~text
principal = authenticate(request)
tenantId = resolveAndAuthorizeTenant(principal, request.tenant)
orderId = validateOrderId(request.orderId)
order = store.get(encodeKey("order", tenantId, orderId))
return authorizeResourceAndReturn(principal, order)
~~~

Đây là mã giả, không phải API của một sản phẩm. Cần áp dụng kiểm tra quyền phù hợp ở mọi đường truy cập, bao gồm index phụ, export, batch job và read model.

### 3.3. GET nhiều khóa và bài toán N+1

Giả sử một danh sách khách hàng gồm 100 orderId và ứng dụng gọi GET từng ID tuần tự. Dù mỗi GET nhanh, tổng thời gian có thể lớn do 100 lần round trip.

Các phương án:

- **Batch get** nếu hệ hỗ trợ, chú ý giới hạn số khóa và kích thước.
- **Đọc song song có giới hạn** để tránh làm nghẽn DB hoặc quá tải connection pool.
- **Read model** chứa đủ trường cho danh sách để không phải lấy toàn bộ đơn.
- **Cache** cho dữ liệu có đặc tính truy cập lặp lại, kèm chính sách hết hạn và cập nhật.

**MGET có thể trả dữ liệu không theo cùng thứ tự đầu vào**, có thể trả thiếu khóa hoặc kết quả từng phần, tùy API. Client cần gắn kết quả trở lại đúng key và xử lý retry/partial failures.

## 4. Thiết kế khóa cho truy vấn theo khoảng thời gian

Xét yêu cầu: “Lấy 20 đơn mới nhất của khách **C-27** thuộc tenant **T-01** trong tháng 11/2026”.

Một khóa tra cứu trực tiếp **order|T-01|O-1042** không đủ để lấy danh sách theo thời gian. Ta có thể tạo thêm một đường truy cập chuyên biệt:

~~~text
ordersByCustomer|T-01|C-27|202611|20261114T080001123Z|O-1042
ordersByCustomer|T-01|C-27|202611|20261114T092735000Z|O-1043
ordersByCustomer|T-01|C-27|202611|20261115T102000500Z|O-1050
~~~

Trong đó:

- **ordersByCustomer** cho biết mục đích của index/read model.
- **T-01** cô lập phạm vi tenant ở lược đồ khóa.
- **C-27** gom dữ liệu cần đọc cùng nhau.
- **202611** là bucket tháng, giúp giới hạn một nhóm dữ liệu theo thời gian.
- **Timestamp cố định độ dài** cung cấp thứ tự thời gian nếu comparator là lexicographic trên encoding phù hợp.
- **OrderId** phân biệt hai đơn có cùng timestamp và giúp tạo cursor ổn định.

Nếu hệ hỗ trợ **scan theo thứ tự khóa** trong phạm vi trên, ta có thể chọn điểm bắt đầu trong bucket 202611 rồi duyệt có giới hạn.

### 4.1. Mã hóa khóa phải giữ đúng thứ tự mong muốn

Hãy so sánh:

~~~text
"price|2"  và "price|10"
~~~

Theo thứ tự từ điển thông thường, **10** đứng trước **2** vì ký tự **1** đứng trước **2**. Nếu muốn sắp theo số tăng dần, có thể dùng phần số với độ rộng cố định:

~~~text
price|0000000002
price|0000000010
~~~

Ví dụ khác:

~~~text
2026-1-9
2026-11-2
~~~

Khi phần tháng/ngày không được zero-pad, thứ tự ký tự có thể khác thứ tự thời gian.

Các quy tắc cần thiết:

1. **Số nguyên:** dùng encoding có thứ tự được xác định, chẳng hạn decimal zero-padded cho miền **không âm và có giới hạn độ rộng**; số âm cần cơ chế biến đổi riêng.
2. **Timestamp:** thống nhất múi giờ, độ chính xác và định dạng có độ dài cố định, hoặc dùng ordered binary encoding/epoch đã chuẩn hóa.
3. **Chuỗi:** kiểm tra comparator là bytewise, collation hay phép so sánh do sản phẩm định nghĩa; chữ hoa, chữ thường, dấu tiếng Việt có thể sắp khác kỳ vọng.
4. **Dấu phân tách:** escape hoặc giới hạn ký tự trong từng thành phần để một ID chứa dấu **|** không làm hỏng phép tách khóa.
5. **Định dạng binary:** không giả định byte encoding của integer, floating-point hoặc UUID tự bảo toàn thứ tự mong muốn.
6. **Khóa dài:** nhiều thành phần giúp biểu diễn truy vấn nhưng tăng dung lượng index, băng thông và chi phí so sánh; kiểm tra giới hạn kích thước khóa.

Lưu thời gian dưới dạng chuỗi ISO 8601 có UTC thường hữu ích, nhưng **không phải mọi chuỗi ISO 8601 đều sort đúng cùng một cách** nếu lẫn offset, độ dài phần thập phân hoặc độ chính xác khác nhau. Nên chuẩn hóa thành một format cố định và xác minh thứ tự thực tế.

### 4.2. Khoảng nửa mở giúp tránh chồng lấn ở ranh giới

Ví dụ muốn lấy toàn bộ tháng 11/2026 cho một khách. Các khóa sử dụng tháng có độ rộng cố định:

~~~text
startInclusive:
  ordersByCustomer|T-01|C-27|202611|

endExclusive:
  ordersByCustomer|T-01|C-27|202612|

query:
  scan(startInclusive, endExclusive)
~~~

Các khóa tháng 11 có cùng phần đầu **202611|** đều nằm trước mốc **202612|**, với điều kiện hệ lưu đúng thứ tự từ điển và cấu trúc khóa hợp lệ.

Nếu tìm các sự kiện trong khoảng **08:00:00 đến trước 09:00:00**, khoảng nửa mở **[08:00, 09:00)** rõ nghĩa hơn việc tự chế “23:59:59.999” hoặc “08:59:59” vì độ chính xác thời gian có thể khác nhau.

Với prefix không có một mốc kế tiếp tự nhiên, API có thể cung cấp **seek + duyệt tới khi prefix không còn khớp**. Một số hệ hỗ trợ cách tính *prefix successor* theo byte; thuật toán đó phải dựa vào comparator và encoding của hệ, không nên mặc định nối một ký tự lớn như “\uFFFF” sẽ đúng với mọi key encoding.

### 4.3. Chiều sắp xếp tăng và giảm

Khóa thời gian tăng dần tự nhiên hỗ trợ đọc từ cũ tới mới. Nhưng giao diện thường cần **mới nhất trước**.

Có ba hướng:

- **Reverse iterator / descending sort** nếu hệ hỗ trợ trong phạm vi query.
- **Đảo chiều mã hóa timestamp** bằng biểu diễn có thứ tự ngược và giới hạn miền giá trị rõ ràng.
- **Duy trì index theo thứ tự mong muốn** trong sorted structure hoặc read model.

Không nên giả định mọi API range đều có reverse scan. Nếu không hỗ trợ, cấu trúc khóa phải phản ánh chiều truy vấn, hoặc ứng dụng cần phương án khác. Việc đọc toàn bộ hàng triệu khóa rồi đảo mảng tại ứng dụng không phù hợp với màn hình 20 bản ghi.

### 4.4. Trùng timestamp và khóa duy nhất

Hai đơn có thể được tạo cùng một mili giây. Nếu index chỉ dùng timestamp làm phần định danh cuối:

~~~text
ordersByCustomer|T-01|C-27|202611|20261114T080001123Z
~~~

thì hai bản ghi có thể trùng khóa. Thêm **orderId** hoặc một định danh duy nhất:

~~~text
ordersByCustomer|T-01|C-27|202611|20261114T080001123Z|O-1042
ordersByCustomer|T-01|C-27|202611|20261114T080001123Z|O-1043
~~~

Không chỉ tránh ghi đè, thành phần phân biệt này còn giúp **phân trang bằng cursor** theo một thứ tự toàn phần.

## 5. Partition key và sort key: range ở đâu?

Trong một số hệ NoSQL, dữ liệu được lưu bằng cặp:

~~~text
partition key = (tenantId, customerId)
sort key      = (createdAt, orderId)
~~~

Hệ có thể hỗ trợ lấy những hàng trong **một partition** có sort key thuộc một khoảng. Tuy nhiên, không vì có sort key mà suy ra có **range scan toàn cục** trên tất cả tenant và customerId.

### 5.1. Truy vấn trong một partition

~~~text
Query partition = (T-01, C-27)
     sortKey >= 2026-11-01T00:00:00Z
     sortKey <  2026-12-01T00:00:00Z
     limit = 20
~~~

Đây là một đường truy cập khả thi **nếu** sản phẩm cho phép điều kiện khoảng như vậy trên sort key và phần định danh thời gian được mã hóa đúng.

### 5.2. Truy vấn trên nhiều partition

Giả sử cần “mọi đơn được tạo trong tháng 11 của **tất cả khách hàng**”. Nếu partition key có customerId, không còn một partition duy nhất. Tùy sản phẩm, hệ thống có thể phải:

- Query nhiều partition rồi merge kết quả.
- Thêm index/read model theo **tenantId + monthBucket + timestamp**.
- Chạy job phân tích hay tổng hợp theo thời gian.
- Dùng engine truy vấn chuyên dụng phù hợp workload.

Một query range tối ưu theo khách hàng không tự động tối ưu theo toàn tenant.

### 5.3. Hot partition và giới hạn dung lượng

Giả sử một tenant có khách hàng tạo hàng triệu sự kiện/ngày. Nếu khóa phân vùng là:

~~~text
partition key = (tenantId, customerId)
sort key      = timestamp
~~~

thì một khách hàng nóng có thể dồn ghi vào một partition, khiến độ trễ và lỗi throttle tăng. Bucketing theo ngày/tháng hoặc thêm shard có thể phân tải:

~~~text
partition key = (tenantId, customerId, dayBucket, shardNo)
sort key      = (timestamp, eventId)
~~~

Nhưng lần đọc dữ liệu một tuần sẽ phải truy cập nhiều bucket/shard và ghép kết quả đúng thứ tự. Các hệ có mức hỗ trợ shard tự động khác nhau; không được coi thêm shard là cải thiện miễn phí.

**Bài toán thiết kế luôn có hai mặt:** khóa giúp dữ liệu cần đọc nằm gần nhau, nhưng cũng không được gom quá nhiều tải cạnh tranh vào cùng một điểm.

## 6. Thiết kế một secondary access path

Giữ một bản ghi có thẩm quyền theo ID:

~~~text
order|T-01|O-1042
    → { customerId: C-27, createdAt: ..., status: CONFIRMED, total: ... }
~~~

Để truy vấn theo khách hàng, thêm một chỉ mục/read model:

~~~text
ordersByCustomer|T-01|C-27|202611|20261114T080001123Z|O-1042
    → { orderId: O-1042, status: CONFIRMED, total: 530000 }
~~~

Ở đây **OrdersById** là nguồn dữ liệu có thẩm quyền; **OrdersByCustomer** phục vụ danh sách. Có hai cách tổ chức:

**Tham chiếu:** index chỉ lưu orderId, sau đó ứng dụng batch GET để lấy chi tiết. Ưu điểm là giảm dữ liệu trùng; nhược điểm là có thêm lần đọc.

**Covering read model:** index chứa sẵn status, total, thời gian và những trường cần cho danh sách. Ưu điểm là có thể trả trang kết quả ngay; nhược điểm là phải cập nhật bản sao khi trường hiển thị thay đổi.

### 6.1. Cập nhật một trường được lập chỉ mục

Nếu read model chứa **status**, khi đơn chuyển **PENDING → CONFIRMED**, cần bảo đảm bản sao cuối cùng phản ánh đúng trạng thái. Có thể dùng chỉ mục nội bộ do database duy trì hoặc pipeline cập nhật. Các cơ chế có thể có tính nhất quán và chi phí khác nhau.

Nếu **customerId hoặc createdAt** thay đổi, đó có thể là thay đổi **vị trí trong index**:

~~~text
DELETE old index key
PUT    new index key
~~~

Nếu hai thao tác không nằm trong một transaction phù hợp, trong lúc chuyển tiếp có thể xuất hiện cả khóa cũ lẫn mới, hoặc mất một khóa tạm thời. Cần thiết kế event/version, idempotency, đối soát và rebuild khi chấp nhận cập nhật bất đồng bộ.

### 6.2. Sắp xếp theo trường trong value phải có đường truy cập

Ví dụ truy vấn: “Sản phẩm có giá từ 100.000 đến 200.000 đồng”.

Nếu sản phẩm chỉ lưu:

~~~text
product|P-1 → { name: "A", price: 120000 }
product|P-2 → { name: "B", price: 80000 }
~~~

thì **GET theo productId** không giải quyết truy vấn giá. Một index ứng viên:

~~~text
productsByPrice|VND|000000120000|P-1
productsByPrice|VND|000000080000|P-2
~~~

Đọc một khoảng theo price có thể hiệu quả **trong phạm vi mà engine cho phép scan các khóa đó theo thứ tự**.

Khi giá P-1 đổi từ 120.000 sang 230.000, index phải được chuyển vị trí. Giá còn cần được chuẩn hóa theo currency và đơn vị nhỏ nhất (ví dụ số nguyên đồng hoặc xu tùy loại tiền) để tránh lỗi so sánh floating-point. Không nên giả định so sánh hai giá khác đơn vị tiền tệ là hợp lệ.

### 6.3. Đánh đổi của bản sao

| Lựa chọn | Đọc | Ghi | Nhất quán | Vận hành |
|---|---|---|---|---|
| Chỉ dữ liệu gốc theo ID | GET theo ID đơn giản | Ít cập nhật phụ | Nguồn duy nhất | Truy vấn khác có thể cần scan |
| Secondary index do DB quản lý | Thêm đường tìm kiếm | Có chi phí index | Theo semantics index của DB | Quản trị index, đo hiệu năng |
| Read model tự quản lý | Tối ưu cho màn hình cụ thể | Ghi hoặc phát sự kiện phụ | Đồng bộ/bất đồng bộ tùy thiết kế | Retry, đối soát, backfill, rebuild |
| Phân tích trên hệ riêng | Tốt cho scan/tổng hợp lớn | Có pipeline ingest | Thường có độ trễ | Nhiều thành phần hơn, chi phí vận hành |

Không nên xem một access path phụ là “chỉ thêm một khóa”. Nó tạo thêm dữ liệu phải duy trì qua vòng đời cập nhật, xóa, phục hồi và migration.

## 7. Phân trang range: đúng thứ tự, đúng cursor

Trả về 20 mục đầu tiên rất đơn giản. Khó hơn là cho người dùng bấm “xem tiếp” mà không bị mất hoặc lặp dữ liệu khi có bản ghi mới.

### 7.1. Dùng cursor dựa trên khóa cuối cùng

Giả sử khóa được sắp tăng:

~~~text
...|08:00:00|O-101
...|08:00:00|O-102
...|08:01:00|O-103
...|08:02:00|O-104
~~~

Đọc trang đầu với limit 2:

~~~text
page 1:
  ...|08:00:00|O-101
  ...|08:00:00|O-102

nextCursor = ...|08:00:00|O-102
~~~

Trang sau phải bắt đầu **sau khóa cuối cùng** của trang trước, với thứ tự và phạm vi truy vấn không đổi:

~~~text
page 2:
  ...|08:01:00|O-103
  ...|08:02:00|O-104
~~~

Cách này thường gọi là **keyset pagination** hoặc **seek pagination**. Nếu API của DB có token phân trang riêng, nên dùng đúng token của API và không tự suy luận rằng token là khóa cuối.

### 7.2. Những lỗi phân trang thường gặp

- **Không có tie-breaker:** hai bản ghi cùng timestamp, cursor chỉ lưu timestamp sẽ bỏ sót hoặc lặp kết quả.
- **Nhầm inclusive/exclusive:** bắt đầu trang sau bằng điều kiện **>= lastKey** sẽ lặp phần tử cuối.
- **Sort không ổn định:** ghi/đổi trường dùng làm sort key có thể di chuyển bản ghi giữa các trang.
- **Offset lớn:** bỏ qua 100.000 mục đầu có thể đòi hỏi scan nhiều mục, tùy engine.
- **Vượt bucket:** đọc hết tháng này phải biết cách tiếp tục tháng trước/tiếp theo.
- **Gộp nhiều shard:** phải merge theo một thứ tự toàn cục, lưu tiến độ từng shard hoặc một cursor tổng hợp.
- **Cursor không gắn query:** người dùng sửa filter nhưng vẫn dùng cursor cũ sẽ có kết quả sai.

Một cursor API thường cần chứa hoặc liên kết tới **phiên bản query, tenant, sort direction, giới hạn/bucket và vị trí tiếp theo**. Nếu token trao cho client, cần bảo vệ tính toàn vẹn hoặc dùng token opaque do server quản lý để ngăn sửa phạm vi trái phép.

### 7.3. Ghi đồng thời khi đang phân trang

Keyset pagination cho thứ tự ổn định hơn offset trong nhiều trường hợp, nhưng **không tự tạo snapshot nhất quán**. Trong khi người dùng đọc:

- Bản ghi mới có thể được chèn vào trước hoặc sau vị trí cursor.
- Bản ghi đã đọc có thể bị xóa.
- Thuộc tính dùng làm khóa sắp xếp có thể thay đổi.
- Replica và index có thể bắt kịp dữ liệu ở những thời điểm khác nhau.

Nếu ứng dụng cần **ảnh chụp cố định của toàn bộ kết quả**, phải kiểm tra DB hỗ trợ snapshot/transaction read đến đâu, hoặc dùng mốc thời gian/version bất biến và quy tắc truy vấn phù hợp. Màn hình feed có thể chấp nhận biến động; xuất dữ liệu kế toán thường cần yêu cầu mạnh hơn.

### 7.4. Limit không nhất thiết là số bản ghi trả về

Một số API tính limit theo **số mục đọc/đánh giá** rồi mới áp dụng filter; một số giới hạn theo **số kết quả**, dung lượng trang hoặc request unit. Vì vậy limit 20 không bảo đảm trang luôn có 20 mục dù vẫn còn dữ liệu, và không bảo đảm đọc đúng 20 mục. Cần hiểu semantics API, xử lý continuation token và tránh gọi vô hạn nếu dữ liệu được lọc nhiều.

## 8. Ví dụ Java: tạo khóa có thứ tự dự kiến

Đoạn Java sau minh họa phần **mã hóa khóa trong ứng dụng**. Nó không phụ thuộc SDK cụ thể; việc scan hoạt động thế nào còn tùy ordered key–value store hoặc partitioned database được chọn.

~~~java
import java.time.Instant;
import java.time.YearMonth;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class OrderKeys {
    private OrderKeys() {}

    private static final DateTimeFormatter MONTH =
        DateTimeFormatter.ofPattern("uuuuMM")
            .withZone(ZoneOffset.UTC);

    private static final DateTimeFormatter TIME =
        DateTimeFormatter.ofPattern("uuuuMMdd'T'HHmmssSSS'Z'")
            .withZone(ZoneOffset.UTC);

    // Demo: ID chỉ cho phép ký tự an toàn,
    // tránh làm hỏng ranh giới thành phần của khóa.
    private static String safeId(String value) {
        if (value == null || !value.matches("[A-Za-z0-9-]+")) {
            throw new IllegalArgumentException("Invalid key component");
        }
        return value;
    }

    public static String orderById(String tenantId, String orderId) {
        return "order|" + safeId(tenantId) + "|" + safeId(orderId);
    }

    public static String ordersByCustomerPrefix(
            String tenantId, String customerId, YearMonth month) {
        return "ordersByCustomer|"
            + safeId(tenantId) + "|"
            + safeId(customerId) + "|"
            + month.format(MONTH) + "|";
    }

    public static String ordersByCustomerKey(
            String tenantId, String customerId,
            Instant createdAt, String orderId) {
        YearMonth month = YearMonth.from(createdAt.atZone(ZoneOffset.UTC));
        return ordersByCustomerPrefix(tenantId, customerId, month)
            + TIME.format(createdAt) + "|"
            + safeId(orderId);
    }

    public static String monthEndExclusive(
            String tenantId, String customerId, YearMonth month) {
        return ordersByCustomerPrefix(
            tenantId, customerId, month.plusMonths(1));
    }
}
~~~

Ví dụ:

~~~java
String oneOrder = OrderKeys.orderById("T-01", "O-1042");
// order|T-01|O-1042

YearMonth month = YearMonth.of(2026, 11);
String start = OrderKeys.ordersByCustomerPrefix("T-01", "C-27", month);
String end   = OrderKeys.monthEndExclusive("T-01", "C-27", month);

// Nếu store cho phép range bytewise trên không gian khóa này:
// scan(startInclusive = start, endExclusive = end, limit = 20)
~~~

Đoạn code thể hiện vài quyết định:

1. **ID có định dạng được kiểm soát** để phép ghép khóa không bị nhập nhằng.
2. **Tháng và timestamp dùng UTC, zero-pad và độ chính xác mili giây cố định**.
3. **OrderId** giúp phân biệt các đơn cùng mili giây.
4. **Khoảng tháng dùng mốc đầu tháng kế tiếp**, không dùng một timestamp cực đại tự chọn.

Các giới hạn phải biết khi áp dụng:

- Nếu ID có Unicode, dấu phân cách hoặc dữ liệu tùy ý, cần escaping/length-prefix/binary encoding đúng nghĩa; mẫu **safeId** chỉ là quy ước demo.
- Timestamp formatter làm việc ở độ chính xác mili giây; nếu cần phân biệt sự kiện trong cùng mili giây, orderId phải duy nhất hoặc cần thêm thành phần sequence.
- Phạm vi năm, kiểu sắp xếp byte, encoding ký tự, max key size và semantics range phải được xác minh.
- Nếu hệ chia partition theo hash của khóa đầy đủ, một khoảng chuỗi như ví dụ **không đảm bảo** được scan hiệu quả toàn cục.
- Nếu ứng dụng cần **mới nhất trước**, phải kiểm tra hỗ trợ reverse iterator hoặc chọn khóa theo chiều thích hợp.
- Việc tạo khóa đúng **không tự duy trì** read model khi đơn hàng được thêm, sửa hoặc xóa.

### 8.1. Pseudocode cho truy vấn có cursor

~~~text
function listOrders(tenant, customer, month, pageSize, cursor):
    authorize(tenant, customer)

    start = keyPrefix(tenant, customer, month)
    endExclusive = keyPrefix(tenant, customer, nextMonth(month))

    page = orderedStore.scan(
        startInclusive = start,
        endExclusive = endExclusive,
        afterExclusive = cursor.lastKeyIfPresent,
        limit = pageSize,
        direction = DESCENDING
    )

    return {
        items: mapIndexEntriesToOrderSummaries(page.entries),
        nextCursor: encodeScopedCursor(page.nextPosition, queryParameters)
    }
~~~

Đây chỉ là **thuật toán minh họa**. Các API cụ thể có thể nhận start/stop theo chiều đảo, có cursor opaque hoặc có token continuation thay vì **afterExclusive**. Nếu dùng descending sort, cách giới hạn và cursor phải được điều chỉnh theo semantics của sản phẩm. Không thể copy mã giả này để gọi trực tiếp bất kỳ database nào.

## 9. Khi truy vấn theo khoảng không còn phù hợp

Range trên khóa được thiết kế tốt có thể rất hiệu quả, nhưng nó có những giới hạn tự nhiên.

### 9.1. Không thể lấy một khoảng trên trường không được lập chỉ mục

Các khóa:

~~~text
order|T-01|O-1042
order|T-01|O-1043
~~~

không tự hỗ trợ “đơn có tổng tiền từ 500.000 đến 1.000.000”. Nếu **total** chỉ nằm trong value, muốn tìm theo total phải có index hoặc read model theo giá trị đó, hoặc chấp nhận scan/filter.

### 9.2. Một thứ tự khóa không tối ưu mọi chiều truy vấn

Sắp theo **customerId → createdAt** thuận tiện khi xem lịch sử một khách, nhưng không thuận tiện khi thống kê tất cả đơn theo ngày. Sắp theo **status → createdAt** phục vụ hàng đợi xử lý, nhưng đổi status kéo theo việc đổi vị trí index.

Mỗi secondary path được thêm vào làm tăng chi phí ghi và công việc đồng bộ. Không nên tạo index cho mọi tổ hợp trường chỉ vì về lý thuyết có thể truy vấn.

### 9.3. Range lớn vẫn là đọc nhiều dữ liệu

Một truy vấn lấy “mọi bản ghi trong 5 năm” có thể chạm hàng tỷ mục. Dù engine có thể seek đúng vị trí bắt đầu, nó vẫn phải duyệt nhiều mục để xuất kết quả.

Nếu mục tiêu là **COUNT**, **SUM** hay **GROUP BY**, có thể cần:

- Bộ đếm/tổng hợp cập nhật theo nghiệp vụ.
- Materialized view hoặc projection theo thời gian.
- Job batch/stream.
- Kho phân tích phù hợp với workload quét và tổng hợp.

Không phải cứ có range iterator là có thể thực hiện báo cáo lớn với độ trễ tương tác.

### 9.4. Điều kiện lọc sau khi scan có thể gây read amplification

Ví dụ index sắp theo thời gian nhưng UI đòi hỏi **status = CONFIRMED**. Nếu chỉ 1% bản ghi trong khoảng có trạng thái đó, hệ có thể cần duyệt khoảng 2.000 mục để lấy 20 kết quả, tùy phân bố dữ liệu.

Hướng cải thiện có thể là một index đặt status vào thành phần khóa trước thời gian, ví dụ:

~~~text
ordersByStatus|T-01|CONFIRMED|202611|timestamp|orderId
~~~

Nhưng một nhóm status có thể trở thành điểm nóng; đổi trạng thái đòi hỏi xóa/thêm index. Cần cân đối tần suất đọc, cập nhật trạng thái, dữ liệu trong từng nhóm và độ trễ mong muốn.

### 9.5. Truy vấn quan hệ, văn bản và không gian

Key–value range đơn giản không tự giải quyết:

- **Join động** qua nhiều tập dữ liệu.
- **Duyệt quan hệ nhiều bước** như bạn của bạn.
- **Tìm kiếm toàn văn** theo token, relevance hoặc ngôn ngữ.
- **Tìm kiếm bán kính** trên tọa độ địa lý.
- **Tìm vector gần nhất** theo embedding.

Một sản phẩm cụ thể có thể bổ sung các chỉ mục hoặc công cụ này; cũng có thể cần kho dữ liệu chuyên biệt. Cần đánh giá workload thay vì ép mọi truy vấn thành “scan một prefix”.

## 10. Consistency và transaction: chính xác về khóa không đồng nghĩa chính xác nghiệp vụ

### 10.1. GET sau PUT có thấy dữ liệu mới không?

Giả sử:

~~~text
PUT("order|T-01|O-1042", status = "CONFIRMED")
GET("order|T-01|O-1042")
~~~

Tùy chính sách replication và read consistency, một lần GET ngay sau PUT có thể thấy giá trị mới hoặc giá trị cũ nếu đọc từ replica chưa bắt kịp. Cần xác minh **read-your-writes**, **strong/linearizable read**, **session consistency**, hoặc mức bảo đảm tương ứng của sản phẩm.

Range query qua index phụ có thể có mức độ mới khác với đọc bản gốc. Không được suy từ GET theo khóa mạnh mà kết luận toàn bộ index hoặc read model cũng cập nhật tức thời.

### 10.2. Check-then-put dễ gặp race condition

Một ứng dụng quản lý tồn kho:

~~~text
available = GET("inventory|SKU-7")
if available >= 3:
    PUT("inventory|SKU-7", available - 3)
~~~

Hai yêu cầu đồng thời có thể cùng đọc cùng giá trị cũ rồi ghi đè nhau. Thứ cần thiết là một thao tác có **điều kiện nguyên tử** trong phạm vi bảo đảm của DB:

~~~text
conditionalUpdate("inventory|SKU-7"):
    if current.available >= 3 and current.version == expectedVersion:
        new.available = current.available - 3
        new.version = current.version + 1
~~~

Mã trên mô tả nghiệp vụ, không phải cú pháp chung. Một số hệ có CAS, optimistic locking, atomic increment kèm điều kiện hoặc transaction; các cơ chế phải được đánh giá theo khả năng **ngăn mất cập nhật và không giữ vượt tồn**.

### 10.3. Hai khóa không mặc nhiên cập nhật nguyên tử cùng nhau

Khi tạo đơn và cập nhật index:

~~~text
PUT("order|T-01|O-1042", document)
PUT("ordersByCustomer|T-01|C-27|...|O-1042", summary)
~~~

Nếu tiến trình chết giữa hai thao tác, có thể tồn tại đơn gốc nhưng chưa có mục trong danh sách. Những lựa chọn:

- Transaction đa khóa nếu DB hỗ trợ đúng phạm vi, isolation và chi phí phù hợp.
- Write batch nguyên tử **nếu** API thực sự bảo đảm atomicity cho các khóa đang dùng.
- Outbox/CDC/event pipeline để cập nhật index bất đồng bộ, kèm retry, idempotency và đối soát.
- Thiết kế lại aggregate để đưa những thay đổi bắt buộc chung vào một ranh giới nguyên tử hợp lệ.

**Batch** không tự đồng nghĩa **transaction**. Một API nhận nhiều lệnh trong một request có thể chỉ tối ưu mạng, vẫn có partial failure. Phải đọc hợp đồng rõ ràng.

### 10.4. Range scan có nhất quán snapshot không?

Một iterator đang duyệt các khóa có thể gặp ghi/xóa đồng thời. Sản phẩm có thể cung cấp:

- Snapshot iterator tại một thời điểm.
- Read consistency theo request nhưng không theo toàn phiên quét.
- Iterator có thể quan sát một phần thay đổi đang diễn ra.

Nếu cần export dữ liệu chính xác, reconcile hoặc xử lý các bản ghi đúng một lần, phải làm rõ **snapshot, cursor, retry, idempotency và checkpoint**. Không nên giả định range scan tự là transaction dài.

### 10.5. TTL và phạm vi khoảng

TTL giúp session/event hết hạn, nhưng cần biết:

- Hết hạn được kiểm tra tại lúc đọc hay qua tiến trình dọn nền?
- Bản ghi hết hạn có còn chiếm dung lượng/tài nguyên trong một thời gian không?
- Range iterator có bỏ qua khóa đã hết hạn không?
- Index phụ và read model có được dọn theo TTL của nguồn không?
- Snapshot/backup có giữ các bản ghi trước khi hết hạn không?

Một index tham chiếu tới khóa gốc đã bị xóa hoặc hết hạn cần xử lý trường hợp **dangling reference**. TTL trên nguồn không mặc nhiên áp dụng cho tất cả bản sao ứng dụng tự quản lý.

## 11. Giới hạn cần xác minh theo sản phẩm và cấu hình

Bảng này là công cụ kiểm tra khi làm việc với bất kỳ hệ key–value hoặc key–value-like nào.

| Nhóm | Câu hỏi kỹ thuật cần trả lời | Hệ quả nếu bỏ sót |
|---|---|---|
| **Lookup** | GET theo một khóa có mức nhất quán nào? Khóa quá lớn được xử lý ra sao? | Trễ, đọc cũ hoặc lỗi do giới hạn |
| **Ordering** | Khóa có được duyệt theo thứ tự không? Comparator là bytewise hay kiểu khác? | Range cho kết quả sai hoặc không hiệu quả |
| **Range scope** | Scan toàn bộ keyspace hay chỉ trong partition/prefix? | Truy vấn nhiều phân vùng quá đắt |
| **Boundary** | Có hỗ trợ >=, >, <=, <; start/end bao gồm hay loại trừ? | Lặp hoặc mất phần tử tại ranh giới |
| **Direction** | Có reverse scan / descending không? | Danh sách mới nhất đòi hỏi index khác |
| **Pagination** | Token có bền qua ghi/xóa? Có snapshot? Giới hạn trang theo mục hay byte? | Lặp, thiếu dữ liệu, trang rỗng bất ngờ |
| **Key/value size** | Giới hạn byte cho khóa, value, record và batch? | Lỗi ghi, throughput giảm, thay đổi schema |
| **Partitioning** | Phân vùng bằng hash/range gì? Tự split không? Giới hạn theo partition? | Hot key, hot partition |
| **Batch** | Batch get/put có atomic không? Có partial success? | Mất đồng bộ giữa source/index |
| **Conditional writes** | CAS có được hỗ trợ và phạm vi nguyên tử ở đâu? | Lost update, vi phạm bất biến |
| **Transactions** | Có transaction nhiều key/partition không? Isolation và giới hạn? | Workflow nhiều bước không an toàn |
| **Indexes** | Có secondary index? Cập nhật đồng bộ/bất đồng bộ? | Query thiếu dữ liệu mới, write amplification |
| **TTL/delete** | Expiry và compaction có semantics thế nào? | Dữ liệu “ma”, dung lượng tăng, index treo |
| **Replication** | Đọc từ đâu, ghi được xác nhận khi nào? Failover có mất ghi không? | Read lag, RPO/RTO ngoài mục tiêu |
| **Capacity** | Throughput tính theo request, bytes hay read/write units? | Dự toán chi phí sai |
| **Security** | Có kiểm soát tenant, encryption, audit, backup và residency không? | Rò rỉ dữ liệu hoặc sai phạm vi lưu trữ |
| **Operations** | Có đo p95/p99, scan bytes, throttle, index lag, restore được không? | Không phát hiện nút thắt và khó khôi phục |

Cần kiểm tra trên **phiên bản sản phẩm, hình thức triển khai, topology và mức tài nguyên** sẽ thực sự sử dụng. Tên tính năng giống nhau không có nghĩa giới hạn giống nhau.

### 11.1. Ví dụ khác biệt giữa các sản phẩm

Các ví dụ sau chỉ nhằm minh họa kiểu năng lực cần tìm hiểu, không phải tài liệu API đầy đủ:

- **Redis:** GET hỗ trợ lookup theo khóa; SCAN duyệt keyspace không bảo đảm là một range sắp theo khóa. Nếu cần truy vấn theo thứ tự score, sorted set với API thích hợp là một cấu trúc dữ liệu khác cần quản lý. Cần kiểm tra cơ chế persistence, replication và transaction ứng dụng mong muốn.
- **RocksDB/LevelDB-style ordered store:** có thể tổ chức khóa theo thứ tự comparator và dùng iterator seek/scan; cần xác minh phạm vi instance, snapshot và việc ứng dụng phải tự giải quyết replication/distribution nếu dùng engine nhúng.
- **DynamoDB-style partition/sort key:** truy vấn có thể dựa trên partition key và điều kiện trên sort key theo giới hạn API; điều đó không tự là scan theo sort key trên toàn bộ partitions. Cần đọc giới hạn key condition, index, consistency và capacity ở sản phẩm đang dùng.

Một hệ có thể phát triển thêm tính năng qua phiên bản. Khi ra quyết định, dùng tài liệu hiện hành và PoC, tránh lấy một đặc điểm từ tài liệu của sản phẩm khác áp vào hệ của mình.

## 12. Hiệu năng và vận hành: kiểm tra đúng thứ sẽ làm hệ thống chậm

### 12.1. Đừng chỉ benchmark GET theo khóa ngẫu nhiên

Một benchmark hợp lý có cả:

| Workload | Đo gì? |
|---|---|
| GET ngẫu nhiên | p50/p95/p99, cache hit, kích thước payload, network |
| GET khóa nóng | contention, throttling, độ trễ đuôi |
| Batch GET | kích thước batch, số round trip, partial failure |
| Range ngắn | thời gian seek, quét 20/100/1.000 mục, số bytes |
| Range dài | throughput scan, giới hạn trang, thời gian tổng |
| Range + filter | số mục đọc so với số mục trả về |
| Ghi đồng thời | conflict rate, retry rate, latency conditional write |
| Ghi + cập nhật index | write amplification, lag và lỗi đồng bộ |
| Ghi/xóa trong khi phân trang | tính ổn định cursor, duplicate/missing theo semantics |
| TTL, backup và restore | lưu trữ thực, thời gian rebuild index, khả năng phục hồi |

Với range, nên đo **read amplification**:

~~~text
readAmplification =
    records_examined / records_returned
~~~

Đây là tỷ số minh họa. Nếu scan 10.000 mục mới trả về 20 mục sau filter, tỷ số bằng **500**. Trong những trường hợp ấy, thêm index phù hợp hoặc thay đổi cấu trúc dữ liệu có thể quan trọng hơn tối ưu serialization.

### 12.2. Tải lệch khiến kết quả benchmark sai kỳ vọng

Nếu tạo dữ liệu thử nghiệm với khóa hoàn toàn ngẫu nhiên và phân phối đều, benchmark có thể không mô phỏng được:

- Một tenant chiếm phần lớn lưu lượng.
- Một sản phẩm flash sale nhận tất cả cập nhật.
- Hầu hết request đọc 20 mục **mới nhất** trên cùng một khoảng thời gian.
- Một tháng/bucket đang nóng trong khi dữ liệu cũ ít truy cập.
- Nhiều job đồng thời scan cùng tập dữ liệu.

Cần dựng cả tình huống phân phối đều lẫn trường hợp lệch mạnh, đặc biệt khi partition key được tạo từ tenantId, customerId hoặc timestamp.

### 12.3. Đường đọc gần nhau không có nghĩa lưu trữ vật lý gần nhau

Một chuỗi khóa có cùng prefix có thể được xử lý như một khoảng logic; nhưng storage engine có thể phải đọc nhiều SSTable, block, shard hoặc remote node tùy tổ chức nội bộ. Compaction, tombstone, fragmentation và cache cũng ảnh hưởng scan latency.

Vì vậy, **không dùng kết quả so sánh chuỗi làm bằng chứng về cách đặt dữ liệu vật lý**. Điều đó chỉ chứng minh thứ tự khóa theo một comparator đã biết.

### 12.4. Khi dữ liệu tăng, khả năng phục hồi cũng là một giới hạn

Nếu ứng dụng duy trì **OrdersByCustomer** tự quản lý, cần chuẩn bị:

1. Nguồn dữ liệu nào đủ tin cậy để rebuild.
2. Cách đọc nguồn theo trang/checkpoint mà không bỏ sót.
3. Làm sao vừa backfill vừa nhận cập nhật mới.
4. Cách loại bỏ event lặp hoặc event cũ theo version.
5. Cách đối soát số bản ghi và dữ liệu giữa hai đường truy cập.
6. Khi nào mới được chuyển traffic sang index mới.

Nếu hệ cho phép tự động tạo index, vẫn cần biết thời gian build, tác động lên ghi và khả năng phục hồi nếu index đang xây bị lỗi.

## 13. Case study: chọn đường truy cập cho ứng dụng quản lý đơn

Giả sử ứng dụng nhiều tenant có ba API:

~~~text
GET /tenants/T-01/orders/O-1042
GET /tenants/T-01/customers/C-27/orders?month=202611&limit=20
GET /tenants/T-01/orders?status=PENDING&day=20261114&limit=100
~~~

Thiết kế ứng viên:

| API | Đường truy cập | Ưu điểm | Điểm phải trả |
|---|---|---|---|
| Chi tiết đơn | **order|tenantId|orderId** | Exact GET đơn giản | Không tự hỗ trợ các danh sách |
| Lịch sử khách | **ordersByCustomer|tenantId|customerId|month|time|orderId** | Có thể seek và phân trang theo khách | Thêm chỉ mục hoặc bản sao; xử lý qua nhiều tháng |
| Đơn cần xử lý | **ordersByStatus|tenantId|status|day|time|orderId** | Đọc theo trạng thái và thời gian | Status đổi làm di chuyển index; partition PENDING có thể nóng |

### 13.1. Ghi một đơn mới

Giả sử hệ tự quản lý các access path:

~~~text
Business write:
  order|T-01|O-1042

Related access paths:
  ordersByCustomer|T-01|C-27|202611|...|O-1042
  ordersByStatus|T-01|PENDING|20261114|...|O-1042
~~~

Chúng ta phải quyết định **mốc nào được xem là tạo đơn thành công**. Nếu ghi nguồn xong mà cập nhật index sau, UI đọc index có thể chậm thấy đơn. Nếu nghiệp vụ không cho phép độ trễ đó, phải dùng transaction/chỉ mục có bảo đảm phù hợp hoặc sửa cách truy xuất.

Khi status chuyển **PENDING → CONFIRMED**:

~~~text
UPDATE source order
REMOVE pending-status index entry
ADD confirmed-status index entry  (nếu cần truy vấn trạng thái này)
UPDATE customer-history summary
~~~

Không nên mặc định bốn thao tác luôn atomic. Lựa chọn cơ chế phụ thuộc DB hỗ trợ transaction bao nhiêu khóa/partition và ứng dụng có chấp nhận projection lag không.

### 13.2. Truy vấn vượt tháng

Nếu khách muốn xem 20 đơn mới nhất **không giới hạn tháng**, client có thể:

1. Bắt đầu từ bucket tháng hiện tại, đọc theo chiều mới đến cũ.
2. Nếu chưa đủ 20 mục, tiếp tục bucket tháng trước.
3. Dừng khi đã đủ hoặc không còn bucket dữ liệu.
4. Cursor chứa trạng thái bucket và vị trí trong bucket.

Đây là một ứng viên thiết kế nếu tần suất truy vấn lịch sử không quá sâu; với khách có hàng trăm tháng dữ liệu hoặc phân bố cực lệch, cần đánh giá mức fan-out và phương án index toàn thời gian.

### 13.3. Hot status: vì sao khóa vẫn có thể sai?

Nếu mọi đơn mới ghi vào:

~~~text
ordersByStatus|T-01|PENDING|20261114|...
~~~

thì một tenant tạo lượng đơn cực lớn có thể dồn ghi vào cùng prefix, partition hoặc một vùng khóa. Bucketing theo giờ, chia shard, dùng queue công việc chuyên dụng hoặc phân công theo nhóm tác vụ có thể hiệu quả hơn; nhưng mỗi giải pháp thay đổi cách lấy 100 đơn chờ xử lý theo thứ tự.

Không có một “khóa tổng hợp chuẩn” tối ưu đồng thời mọi nhu cầu. Đúng hơn, cần ghi rõ **API nào dùng access path nào** và **chi phí viết/đọc/vận hành của đường đó**.

## 14. Những nhầm lẫn phổ biến

### “Key–value nghĩa là chỉ có GET/PUT và không thể có range”

Không chính xác cho mọi sản phẩm. Một ordered store hoặc hệ có sort key/sorted structure có thể hỗ trợ range. Cần hỏi **range trên thứ tự nào, phạm vi nào và API nào**.

### “Khóa có chứa timestamp thì truy vấn thời gian sẽ nhanh”

Chỉ đúng khi hệ thực sự có đường truy cập theo thứ tự timestamp trong phạm vi cần thiết. Hashing khóa đầy đủ có thể phá vỡ khả năng scan prefix; timestamp không zero-pad hoặc lẫn timezone cũng có thể sai thứ tự.

### “SCAN có thể thay thế index vì cùng lấy nhiều khóa”

SCAN toàn bộ không gian khóa rồi filter có thể đọc lượng dữ liệu lớn, trong khi index phù hợp cho phép seek vào khoảng nhỏ. Chúng khác nhau cả về chi phí lẫn semantics ordering.

### “Có sort key thì có thể lấy khoảng trên toàn bộ database”

Một số hệ cho phép sort key range **trong một partition**, không phải toàn bộ tập dữ liệu. Truy vấn trên mọi tenant hay customer có thể cần index khác hoặc fan-out.

### “Limit 20 có nghĩa DB đọc đúng 20 mục”

Không phải mọi API đều tính limit như nhau. Một số có filtering sau đọc, giới hạn bytes hoặc continuation token. Cần đo items examined, returned và request cost.

### “Chỉ cần timestamp là phân trang không trùng”

Timestamp có thể trùng. Thêm ID duy nhất hoặc sequence, dùng so sánh cursor đúng inclusive/exclusive, và xét concurrent updates.

### “Batch write luôn nguyên tử”

Batch có thể chỉ giúp giảm số request và vẫn có partial failure. Muốn ràng buộc nhiều khóa phải kiểm tra transaction semantics cụ thể.

### “GET thấy dữ liệu mới thì range index cũng thấy ngay”

Nguồn, replica và secondary index/read model có thể có đường cập nhật khác nhau. Phải xác định mức nhất quán riêng cho mỗi truy vấn.

### “Prefix theo tenant là đủ bảo mật”

Khóa theo tenant giúp tổ chức dữ liệu nhưng không thay thế authentication, authorization, giới hạn quyền trên API/batch/export và kiểm soát ở tầng database.

### “Đã có range query thì có thể chạy mọi báo cáo”

Seek đến đầu khoảng có thể nhanh nhưng duyệt hàng trăm triệu bản ghi để tổng hợp vẫn tốn tài nguyên. Reporting có thể cần preaggregation hoặc hệ phân tích.

## 15. Quy trình quyết định cho một access pattern

Khi thiết kế một truy vấn mới cho kho key–value, hãy đi theo trình tự:

1. **Xác định đầu vào:** API biết chính xác khóa, biết một prefix, hay chỉ biết điều kiện lọc trên value?
2. **Xác định kết quả:** một mục, một danh sách có thứ tự, một khoảng thời gian, một phép tổng hợp?
3. **Xác định phạm vi tenant/partition:** truy vấn diễn ra trong một partition hay nhiều partition?
4. **Xác minh kiểu storage:** key hash, ordered key, sort key range, secondary index hay sorted structure?
5. **Thiết kế encoding:** delimiter, escape, zero-padding, time zone, collation, tie-breaker, chiều sort.
6. **Thiết kế phân trang:** boundary inclusive/exclusive, cursor, limit, snapshot và hành vi concurrent writes.
7. **Thiết kế ghi:** cập nhật source và các index bằng cơ chế nào; có cần transaction, outbox hoặc đối soát?
8. **Kiểm tra skew:** tenant/khóa nào nóng, partition có quá lớn hoặc cần bucket/shard không?
9. **Đo trên dữ liệu đại diện:** p95/p99, bytes examined, records returned, retry/throttle và chi phí.
10. **Lập kế hoạch vận hành:** TTL, delete, backup, rebuild, migration, phân quyền và data placement.

Một bảng ghi quyết định có thể dùng trong tài liệu thiết kế:

| Access pattern | Khóa biết sẵn | Access path | Consistency cần | Giới hạn/đo đạc |
|---|---|---|---|---|
| Xem một đơn | tenantId + orderId | Exact GET | Cần xem trạng thái có thẩm quyền | p99 GET, hot key |
| Lịch sử khách | tenantId + customerId + khoảng tháng | Ordered index/range trong nhóm | Có thể trễ nếu UI chấp nhận | Scan bytes, pages, index lag |
| Tìm đơn theo trạng thái | tenantId + status + day | Index theo trạng thái | Trạng thái queue cần xử lý lặp an toàn | Hot status, retry, update cost |
| Báo cáo tháng | tenant + date range | Tổng hợp hoặc analytical path | Theo lịch thống nhất | Scan cost, backfill, freshness |

## 16. Bài tập thực hành

### Bài 1 — Chọn GET hay range

Một ứng dụng cần:

1. Đọc giỏ hàng bằng **cartId**.
2. Lấy 50 hoạt động gần nhất của một user.
3. Tìm các giỏ hàng có tổng tiền trên 1 triệu đồng.

Hãy chỉ rõ thao tác nào có thể dùng exact GET, thao tác nào cần ordered access path hoặc index phụ. Nếu hệ chỉ hỗ trợ hash lookup theo khóa, những truy vấn nào phải thiết kế bổ sung?

### Bài 2 — Sắp xếp chuỗi và số

Các khóa được lưu:

~~~text
score|3|U-1
score|12|U-2
score|100|U-3
score|25|U-4
~~~

Trong ordered store so sánh chuỗi lexicographic, thứ tự trả về có đúng điểm số tăng dần không? Hãy thiết kế lại thành phần điểm số để có thứ tự mong muốn, sau đó nêu phương án nếu điểm có thể âm và vượt miền độ rộng đã chọn.

### Bài 3 — Phân trang thời gian

Ba bản ghi cùng thời gian **2026-11-14T08:00:00.000Z** nhưng có ID A, B, C. Trang đầu trả A và B. Nếu cursor chỉ chứa timestamp, trang hai có thể gặp vấn đề gì? Hãy xây cursor dùng cặp **(timestamp, id)** và quy định phép so sánh ranh giới.

### Bài 4 — Hot partition

Hệ lưu mọi sự kiện theo **partition key = tenantId**. Một tenant chiếm 80% ghi; mọi request đến trong một giờ. Đề xuất hai phương án chia bucket hoặc shard, mô tả cách đọc toàn bộ sự kiện của tenant trong tuần gần nhất và đo chi phí fan-out.

### Bài 5 — Phân biệt SCAN và range

Một worker dùng SCAN toàn bộ keyspace rồi chỉ giữ khóa có prefix **ordersByCustomer|T-01|C-27|202611|**. Hãy đề xuất đường truy cập thay thế nếu DB hỗ trợ ordered iterator hoặc partition+sort key. Nêu điều kiện khiến thay thế đó thực sự hiệu quả.

### Bài 6 — Chính xác khi cập nhật hai đường truy cập

Một đơn được ghi vào **OrdersById**, sau đó index **OrdersByCustomer** được cập nhật qua message. Worker nhận lại cùng message hai lần; một event cũ có thể đến sau event mới. Thiết kế idempotency/version check và phương án đối soát nếu index thiếu đơn.

### Bài 7 — Thẩm định sản phẩm

Hai dịch vụ đều được quảng bá “NoSQL key–value, high performance, supports range”. Hãy viết tối thiểu mười câu hỏi kỹ thuật để kiểm tra:

- Comparator, phạm vi range, reverse scan và pagination.
- Batch semantics, transaction, conditional write, consistency của index.
- Giới hạn partition, hot keys, TTL, snapshot và chi phí đọc/ghi.

Một câu trả lời tốt không dừng ở việc chọn tên mô hình. Nó chỉ rõ **khóa nào được dùng**, **kết quả được tìm theo thứ tự nào**, **truy vấn phải đọc bao nhiêu dữ liệu**, **bất biến nào được bảo vệ** và **kết quả đo nào chứng minh lựa chọn đáp ứng workload**.

---

**Kết luận:** Tra cứu chính xác là thế mạnh tự nhiên của mô hình khóa–giá trị khi ứng dụng đã biết khóa. Truy vấn khoảng chỉ hiệu quả khi hệ có **đường truy cập duy trì đúng thứ tự trong phạm vi cần thiết**, khóa được mã hóa phù hợp và dữ liệu được phân vùng để không tạo điểm nóng. Khi thiết kế, phải kiểm tra thêm pagination, nhất quán, transaction, index, giới hạn kích thước, chi phí quét và vận hành; không thể suy ra các bảo đảm đó chỉ từ tên “key–value”.
