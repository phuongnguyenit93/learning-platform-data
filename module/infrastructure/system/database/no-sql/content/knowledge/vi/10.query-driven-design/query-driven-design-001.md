# Thu thập và phân loại đầy đủ các mẫu truy cập

Trong thiết kế cơ sở dữ liệu NoSQL, câu hỏi **“dữ liệu gồm những thực thể và thuộc tính nào?”** là cần thiết nhưng chưa đủ. Một mô hình lưu trữ chỉ thực sự phù hợp khi nó phục vụ được những thao tác mà hệ thống phải thực hiện: đọc một sản phẩm theo ID, liệt kê đơn hàng mới nhất của khách hàng, tìm kiếm theo từ khóa, đặt giữ tồn kho, cập nhật trạng thái thanh toán, tổng hợp số liệu theo ngày hoặc xóa dữ liệu đã hết thời hạn lưu giữ.

Những thao tác đó được gọi là **mẫu truy cập** (*access patterns*). Khả năng thu thập và phân loại đầy đủ access patterns là nền tảng của **thiết kế theo truy vấn** (*query-driven/query-first design*): thay vì tạo cấu trúc dữ liệu trước rồi hy vọng DBMS trả lời được mọi câu hỏi, ta xác định **cần đọc/ghi điều gì, với điều kiện nào, bao nhiêu lần, trong bao lâu và với bảo đảm gì**, sau đó mới đánh giá khóa, phân vùng, chỉ mục và cách biểu diễn dữ liệu.

Đặc biệt với một số mô hình NoSQL như key–value và wide-column, các đường truy cập được thiết kế từ đầu ảnh hưởng rất mạnh tới hiệu năng. Tuy vậy, **thiết kế theo truy vấn không dành riêng cho NoSQL**; cơ sở dữ liệu quan hệ, document DBMS, graph DBMS và kho tìm kiếm cũng cần phân tích workload. Khác biệt nằm ở mức độ linh hoạt của truy vấn, giới hạn API và chi phí khi phải thêm các cấu trúc dữ liệu phụ.

## 1. Mẫu truy cập là gì, khác một câu truy vấn ra sao?

Một **mẫu truy cập** là cách một tác nhân hoặc tiến trình dùng dữ liệu để đạt một mục đích, kèm hình dạng yêu cầu và những ràng buộc vận hành. Nó có thể là **đọc**, **ghi**, **cập nhật có điều kiện**, **xóa**, **duyệt liên kết**, **tìm kiếm**, **tổng hợp** hoặc **đồng bộ dữ liệu**.

Ví dụ:

> “Khách hàng xem 20 đơn hàng gần nhất của chính mình, theo thời gian tạo giảm dần; trang đầu phải phản hồi nhanh và không được hiển thị đơn của người khác.”

Đây là một access pattern rõ hơn câu nói “cần truy vấn bảng đơn hàng” vì nó đã gợi ra:

- **Tác nhân:** khách hàng đã đăng nhập.
- **Đối tượng:** đơn hàng thuộc khách hàng đó.
- **Đầu vào:** danh tính khách hàng, có thể thêm cursor của trang sau.
- **Bộ lọc:** đơn hàng của khách hàng; ràng buộc quyền truy cập.
- **Thứ tự:** thời gian tạo giảm dần và một khóa phá hòa ổn định.
- **Kích thước kết quả:** 20 đơn/trang.
- **Yêu cầu phi chức năng:** độ trễ, độ mới, phân trang và bảo mật.

Từ đây mới đánh giá các cấu trúc có thể hỗ trợ: index trên `(customerId, createdAt)`, khóa phân vùng theo khách hàng với clustering theo thời gian, hoặc một **read model** chuyên phục vụ màn hình lịch sử đơn hàng.

### Một endpoint không nhất thiết tương ứng một access pattern

Ví dụ `GET /products` có thể có các biến thể:

~~~text
GET /products?category=book&sort=price_asc
GET /products?category=book&minPrice=100000&maxPrice=500000
GET /products?search=nosql
GET /products?brand=A&color=blue&sort=popular
~~~

Các biến thể này có thể yêu cầu những đường truy cập khác nhau: lọc bằng theo danh mục, khoảng giá, tìm toàn văn, kết hợp nhiều điều kiện và sắp xếp theo độ phổ biến. Gộp tất cả thành một dòng “danh sách sản phẩm” sẽ che giấu chi phí và giới hạn thiết kế.

Ngược lại, **nhiều endpoint có thể chia sẻ cùng một access pattern**. Ví dụ màn hình web và ứng dụng di động đều lấy chi tiết đơn hàng theo `orderId`, cùng ràng buộc quyền và cùng mức nhất quán. Ta có thể mô tả một mẫu truy cập, rồi ghi nhận các kênh tiêu thụ.

## 2. “Đầy đủ” nghĩa là gì trong kiểm kê access patterns?

**Đầy đủ** không có nghĩa liệt kê mọi giá trị tham số có thể xảy ra: không cần tạo một dòng riêng cho từng `customerId` hoặc từng ngày. Mục tiêu là **không bỏ sót những hình dạng thao tác khác biệt về cách dữ liệu được truy cập, cập nhật, phân phối và bảo đảm đúng đắn**.

Một danh mục được xem là đủ để bắt đầu thiết kế khi nó bao phủ:

1. **Tất cả luồng nghiệp vụ quan trọng**, không chỉ trang người dùng cuối.
2. **Tất cả vai trò truy cập**: khách hàng, nhân viên vận hành, quản trị viên, đối tác, dịch vụ nội bộ và tác vụ tự động.
3. **Các biến thể điều kiện truy vấn đáng kể**: đọc theo ID, lọc bằng, lọc khoảng, sắp xếp, tìm kiếm, phân trang, tổng hợp, duyệt nhiều bước.
4. **Các thao tác ghi và thay đổi trạng thái**: tạo, sửa, upsert, cập nhật có điều kiện, batch, xóa, TTL.
5. **Các tình huống không thuận lợi**: request bị gửi lại, dữ liệu đến trễ, đồng thời ghi, dữ liệu rất lớn, mất kết nối, phục hồi và backfill.
6. **Yêu cầu ngoài đường đi chính**: báo cáo, xuất dữ liệu, tìm kiếm quản trị, kiểm toán, giữ/xóa dữ liệu và chuyển đổi schema.
7. **Kích thước và phân bố tải**: khối lượng trung bình, đỉnh, tỉ lệ đọc/ghi, tăng trưởng, hot key/hot partition.
8. **Mức nhất quán, độ trễ và phạm vi quyền truy cập** cho từng thao tác, thay vì một giả định chung cho toàn hệ thống.

Đây là một danh mục **có phiên bản và được bổ sung liên tục**. Không thể bảo đảm rằng mọi yêu cầu tương lai đều đã được biết. Ta cần lưu lại những **giả định còn mở** và cách cập nhật danh mục khi phát sinh chức năng mới.

## 3. Nguồn thông tin để thu thập mẫu truy cập

Không nên chỉ hỏi một lập trình viên “ứng dụng sẽ query gì?” rồi xem danh sách nhận được là hoàn chỉnh. Các nguồn khác nhau nhìn thấy những phần khác nhau của workload.

| Nguồn | Những mẫu truy cập thường phát hiện | Câu hỏi nên hỏi |
| --- | --- | --- |
| **Hành trình người dùng / user stories** | Xem chi tiết, danh sách, bộ lọc, giỏ hàng, theo dõi tiến độ | Người dùng bắt đầu từ đâu, làm gì tiếp, cần xem kết quả nào? |
| **Màn hình và API contract** | Tham số lọc, thứ tự, phân trang, kích thước response | Có bao nhiêu cách gọi cùng API? Có tìm kiếm tự do không? |
| **Quy tắc nghiệp vụ** | Cập nhật có điều kiện, bất biến, chống xử lý lặp | Điều gì tuyệt đối không được sai khi hai request đến cùng lúc? |
| **Sự kiện và luồng đồng bộ** | Consumer, read model, search index, retry, replay | Một thay đổi nguồn được chuyển cho những nơi nào? |
| **Batch, cron, ETL và báo cáo** | Quét theo khoảng, tổng hợp lớn, export, archive | Job chạy khi nào, phải hoàn thành trước hạn nào? |
| **Sản phẩm đang vận hành** | Truy vấn thực, độ trễ, hot key, peak traffic | Log và traces cho thấy hình dạng truy cập nào? |
| **Đội vận hành / hỗ trợ** | Tìm kiếm thủ công, sửa dữ liệu, điều tra sự cố | Khi có khiếu nại, nhân viên cần tra thông tin bằng tiêu chí nào? |
| **Bảo mật / quản trị dữ liệu** | Kiểm tra quyền, xóa theo tenant, retention, audit | Dữ liệu của ai được xem, và có thể bị xóa theo yêu cầu nào? |
| **Kế hoạch sản phẩm** | Bộ lọc sắp ra mắt, tính năng đang thử nghiệm | Những truy vấn có thể xuất hiện trong 6–12 tháng tới? |

### Thu thập qua hành trình, không chỉ qua danh sách thực thể

Ví dụ luồng **thanh toán đơn hàng**:

~~~text
Khách hàng mở giỏ
    │
    ├── Đọc giỏ hàng theo cartId
    ├── Đọc giá/khuyến mãi của các SKU
    ├── Kiểm tra và giữ tồn kho
    ├── Tạo đơn hàng
    ├── Yêu cầu thanh toán
    ├── Nhận kết quả thanh toán (có thể retry)
    ├── Cập nhật trạng thái đơn
    ├── Phát sự kiện OrderPaid
    ├── Gửi thông báo
    └── Cập nhật báo cáo doanh thu
~~~

Nếu chỉ ghi “đọc/ghi Order”, ta bỏ sót nhiều mẫu truy cập quan trọng: đọc nhiều SKU, kiểm tra số lượng còn lại, cập nhật có điều kiện, xử lý callback lặp, tiêu thụ sự kiện và cập nhật dữ liệu dẫn xuất.

### Đừng quên đường đi ngoại lệ

Một luồng nghiệp vụ cần được xem cả khi:

- Người dùng gửi lại thao tác vì timeout.
- Cổng thanh toán trả callback hai lần.
- Đơn hàng được hoàn tiền sau nhiều ngày.
- Một sự kiện tới sau khi báo cáo đã chốt.
- Một khách hàng có hàng triệu bản ghi thay vì vài chục.
- Tác vụ export yêu cầu dữ liệu trải qua nhiều partition hoặc ngày.
- Người dùng đổi tenant/ngữ cảnh đăng nhập và hệ thống phải cô lập quyền.

Những trường hợp này có thể không làm thay đổi tên endpoint, nhưng lại làm thay đổi **bảo đảm ghi, cách định danh, phân vùng hoặc yêu cầu tra cứu lịch sử**.

## 4. Quy trình thu thập có hệ thống

Có thể dùng quy trình bảy bước, lặp lại cho từng phân hệ.

### Bước 1 — Xác định ranh giới nghiệp vụ

Trước tiên liệt kê những nhóm đối tượng và luồng dữ liệu chính:

~~~text
Phân hệ Catalog:
  Product, Category, Brand, SearchIndex

Phân hệ Checkout:
  Cart, Order, OrderItem, InventoryReservation, Payment

Phân hệ Customer:
  Customer, Address, Session

Phân hệ Analytics:
  OrderPaid event, DailyRevenue, ProductViewMetric
~~~

Danh sách này chỉ để tìm **những nơi có hoạt động truy cập**; chưa phải schema cuối cùng. Đừng khóa thiết kế vào một collection/bảng cho mỗi entity trước khi hiểu các query.

### Bước 2 — Liệt kê người dùng và tiến trình

Với mỗi phân hệ, ghi **ai hoặc điều gì thực hiện thao tác**:

~~~text
Customer UI          → đọc sản phẩm, đặt hàng, xem lịch sử
Seller dashboard     → cập nhật sản phẩm, xem đơn của shop
Support tool         → tìm đơn theo mã, email, trạng thái
Payment callback     → xác nhận thanh toán, chống lặp
Search indexer       → nhận thay đổi sản phẩm, lập chỉ mục
Analytics ETL        → đọc sự kiện, tạo báo cáo
Retention job        → xóa/lưu trữ dữ liệu hết hạn
~~~

Đây là cách phát hiện những **mẫu truy cập ngoài luồng khách hàng cuối** mà các nhóm phát triển dễ quên.

### Bước 3 — Chuyển từng hành động thành thao tác dữ liệu

Hỏi với từng thao tác:

- Đọc hay ghi? Ghi mới, cập nhật từng trường hay thay toàn bộ?
- Có biết ID/khóa chính ngay lúc truy cập không?
- Có lọc theo những trường nào và dùng toán tử gì?
- Cần sắp xếp, phân trang hay lấy top N?
- Có đọc hoặc ghi nhiều thực thể trong một hành động không?
- Sau khi ghi, phần nào phải nhìn thấy ngay và phần nào có thể trễ?

Ví dụ “nhân viên xem các đơn chưa giao trong tuần” trở thành:

~~~text
Input: tenantId, warehouseId?, status in {PAID, PACKING},
       createdAt trong [start, end)
Filter: tenant + trạng thái + khoảng thời gian, có thể theo kho
Sort: createdAt tăng dần
Return: orderId, customer, total, status, createdAt
Page: 50 dòng/trang, cursor ổn định
~~~

Nó khác “khách hàng xem 20 đơn gần nhất” dù cùng đọc dữ liệu đơn hàng.

### Bước 4 — Tách các hình dạng truy vấn quan trọng

Ví dụ màn hình danh mục có:

~~~text
P1: category = X ORDER BY price ASC
P2: category = X AND brand = Y ORDER BY price ASC
P3: category = X AND price BETWEEN a AND b ORDER BY price ASC
P4: keyword full-text AND category = X ORDER BY relevance
~~~

Nếu sự khác biệt chỉ là `category = books` hay `category = phones`, thường là **một pattern với nhiều giá trị tham số**. Nếu khác toán tử, thứ tự sắp xếp hoặc yêu cầu tìm toàn văn, có thể cần **pattern khác**, vì đường truy cập và chi phí khác nhau.

“Thu thập đầy đủ” không có nghĩa tạo mọi tổ hợp 20 bộ lọc thành hàng triệu dòng. Cần mô tả các **query shapes có ý nghĩa** và những tổ hợp quan trọng nhất; với bộ lọc tùy ý thực sự, ghi rõ đây là một access pattern có tính linh hoạt cao, cần giải pháp thích hợp và giới hạn được công bố.

### Bước 5 — Bổ sung yêu cầu tải và độ đúng đắn

Không dừng ở `WHERE` và `ORDER BY`. Cần hỏi tần suất, kích thước, đỉnh tải, ràng buộc thời gian phản hồi, tính mới, dữ liệu đến trễ và xung đột ghi.

### Bước 6 — Tập hợp thành danh mục truy cập chung

Mỗi pattern cần có **ID ổn định**, người sở hữu, mức ưu tiên và trạng thái xác minh. Các nhóm khác nhau có thể dùng chung mẫu biểu; điều này ngăn việc một pattern chỉ tồn tại trong đầu người làm một màn hình.

### Bước 7 — Xác nhận với những bên có liên quan

Đối chiếu danh mục với hành trình người dùng, API contract, sơ đồ sự kiện, job lịch, quy tắc bảo mật và telemetry hiện có. Mỗi pattern cần có người chịu trách nhiệm xác nhận: “đúng là thao tác này tồn tại hoặc đã nằm trong phạm vi phát triển”.

**Mục tiêu cuối cùng của quy trình là tài liệu để đưa ra quyết định mô hình hóa**, không phải một file liệt kê các câu SQL hiện tại.

## 5. Thẻ mô tả một access pattern cần có thông tin gì?

Một **access pattern card** nên đủ chi tiết để hai người thiết kế khác nhau hình dung cùng một truy vấn và cùng một ràng buộc vận hành.

| Nhóm thông tin | Trường gợi ý | Lý do |
| --- | --- | --- |
| **Nhận diện** | ID, tên, phân hệ, chủ sở hữu, trạng thái | Dễ tham chiếu và theo dõi thay đổi |
| **Nghiệp vụ** | Actor, trigger, tình huống, mức quan trọng | Hiểu vì sao thao tác tồn tại |
| **Kiểu thao tác** | Point read, range read, search, aggregate, insert, conditional update, delete, replay | Xác định lớp bài toán |
| **Khóa đầu vào** | Tenant ID, user ID, entity ID, time range, cursor | Đánh giá khả năng định vị partition |
| **Điều kiện** | Equality, range, IN, prefix, full-text, geo, graph traversal | Đánh giá index và cấu trúc truy vấn |
| **Kết quả** | Trường trả về, số bản ghi, top N, thứ tự, pagination | Tránh đọc quá nhiều dữ liệu |
| **Tải** | Reads/sec, writes/sec, peak, burst, phân bố theo key, tăng trưởng | Đánh giá throughput và hot partition |
| **Thời gian** | p95/p99 latency, thời hạn job, timeout | Đánh giá SLO |
| **Độ đúng đắn** | Atomicity, consistency, điều kiện ghi, xử lý lặp, dữ liệu đến trễ | Bảo toàn bất biến nghiệp vụ |
| **Bảo mật** | Phạm vi tenant, kiểm tra quyền, dữ liệu nhạy cảm | Tránh lộ dữ liệu giữa người dùng |
| **Vòng đời** | Retention, TTL, archive, delete, backfill | Biết khi nào dữ liệu mất hoặc cần tái xử lý |
| **Giả định** | Nguồn có thẩm quyền, dependency, giới hạn chưa rõ | Giữ các bất định hiển thị được |

Ví dụ một thẻ mẫu:

~~~yaml
id: ORD-R-02
name: "Get latest orders of one customer"
actor: "Authenticated customer"
trigger: "Open purchase history"
operation: "Range/paginated read"
sourceOfTruth: "Order service"
inputs:
  required:
    - tenantId
    - customerId
  optional:
    - pageCursor
filters:
  equality:
    - tenantId
    - customerId
sort:
  - "createdAt DESC"
  - "orderId DESC (stable tiebreaker)"
output:
  fields: [orderId, createdAt, status, totalAmount, currency]
  pageSize: 20
  pagination: "Cursor/keyset"
load:
  readRate: "TBD: average and peak separately"
  largestCustomerOrderCount: "TBD"
latency:
  targetP95Ms: 200
consistency:
  requirement: "A newly created order should appear promptly"
security:
  boundary: "Only orders owned by authenticated customer in tenant"
priority: P0
owner: "Checkout team"
openQuestions:
  - "How stale can the history screen be after checkout?"
  - "Do cancelled or refunded orders remain visible?"
~~~

Các con số trong thẻ là **giả định minh họa**, không phải SLO thực của một công ty. Trường `TBD` giúp phân biệt thông tin **chưa đo** với thông tin được xác nhận, thay vì âm thầm coi thông số chưa biết bằng 0.

## 6. Phân loại theo thao tác: đọc, ghi, duy trì dữ liệu

Đây là trục phân loại đầu tiên vì mỗi nhóm tạo yêu cầu rất khác nhau cho mô hình lưu trữ.

### 6.1. Các nhóm đọc

| Nhóm | Hình dạng truy cập | Ví dụ | Câu hỏi quan trọng |
| --- | --- | --- | --- |
| **Point lookup** | Tìm một bản ghi theo ID/key | Lấy sản phẩm theo `productId` | Biết key hay cần tìm qua thuộc tính khác? |
| **Batch key lookup** | Tìm một tập key đã biết | Lấy chi tiết 30 SKU trong giỏ | Có giới hạn batch/multi-key/cùng partition không? |
| **Range query** | Tìm các bản ghi theo khoảng | Sự kiện thiết bị từ 10:00–11:00 | Có partition key và clustering/range phù hợp không? |
| **Filtered list** | Lọc theo nhiều thuộc tính | Đơn `status=PAID` trong một shop | Có index/filter phù hợp hay phải scan? |
| **Sorted top N** | Lấy N bản ghi đầu theo thứ tự | 20 đơn mới nhất của khách hàng | Thứ tự có được hỗ trợ bởi index/clustering không? |
| **Full-text search** | Tìm từ khóa/ngữ nghĩa văn bản | Tìm sản phẩm chứa “NoSQL” | Có inverted/text index và quy tắc phân tích ngôn ngữ không? |
| **Aggregation** | Nhóm và tính toán | Doanh thu theo ngày | Tính trực tiếp hay dùng dữ liệu dẫn xuất? |
| **Graph traversal** | Đi qua quan hệ nhiều bước | Các khóa học tiên quyết gián tiếp | Bắt đầu từ node nào, đi bao nhiêu bước? |
| **Time-series query** | Lấy/tổng hợp theo cửa sổ thời gian | Nhiệt độ trung bình 15 phút | Độ phân giải, timestamp, bucket, dữ liệu trễ? |
| **Export/scan** | Đọc lượng lớn dữ liệu theo lô | Xuất lịch sử đơn hàng tháng | Có thể quét/phân trang theo phạm vi ổn định không? |

Một pattern có thể mang **nhiều nhãn**, chẳng hạn “range query + sorted top N” hoặc “full-text + filtered list”. Không nên ép mỗi truy vấn chỉ thuộc một loại nếu điều đó che giấu yêu cầu thực thi.

### 6.2. Các nhóm ghi

| Nhóm | Ví dụ | Điều cần xác định |
| --- | --- | --- |
| **Create/insert** | Tạo giỏ hoặc đơn hàng | ID có duy nhất, tạo lặp được không? |
| **Upsert** | Cập nhật trạng thái thiết bị | Nếu key chưa có thì tạo mới có hợp lệ không? |
| **Partial update** | Đổi tên sản phẩm | Có cập nhật một trường mà giữ nguyên trường khác không? |
| **Conditional update** | Trừ tồn kho nếu đủ hàng | Điều kiện được kiểm tra nguyên tử ở phạm vi nào? |
| **Multi-entity transaction** | Tạo đơn và cập nhật các dòng hàng | Những thay đổi nào phải cùng thành công/thất bại? |
| **Counter/accumulator** | Tăng số lượt xem | Có tránh lost update và xử lý duplicate không? |
| **Append-only event** | Ghi `OrderPaid` | Event ID, thứ tự, phát lặp và retention? |
| **Bulk ingest** | Nhập hàng triệu bản đo | Ghi theo batch, tốc độ đỉnh, idempotency? |
| **Delete/expire** | Xóa session hoặc dữ liệu quá hạn | Xóa vật lý/logical, TTL, chỉ mục phụ và bản sao? |
| **Rebuild/backfill** | Tạo lại search index | Có phát lặp, thay đổi thứ tự và ảnh hưởng tải hệ thống không? |

Một lỗi phổ biến là chỉ thu thập các truy vấn `SELECT` và bỏ qua ghi. Nhưng **chìa khóa phân vùng**, **đơn vị cập nhật nguyên tử** và **chi phí nhân bản dữ liệu** phải được thiết kế từ đầu cho cả phía đọc lẫn phía ghi.

## 7. Phân loại theo hình dạng bộ lọc và đường truy cập

Các câu truy vấn có vẻ tương tự ở giao diện có thể khác nhau rất lớn ở góc nhìn DBMS.

### 7.1. Đọc theo khóa đã biết

~~~text
GetProduct(productId)
GetCart(cartId)
GetOrder(tenantId, orderId)
~~~

Đây thường là những pattern dễ hỗ trợ bằng key–value, document hoặc RDBMS có chỉ mục ID. Nhưng nếu `orderId` chỉ duy nhất **trong một tenant**, thì `tenantId` cũng thuộc khóa nhận diện nghiệp vụ; không thể bỏ nó nếu như vậy dẫn đến tìm nhầm đơn.

### 7.2. Lọc bằng và truy cập trong một nhóm

~~~text
ListOrders(customerId = C42)
ListOrders(status = PAID)
ListOrders(tenantId = T17, status = PAID)
~~~

Ba hình dạng này không tương đương. Nếu một bảng wide-column phân vùng theo `customerId`, việc liệt kê đơn theo khách hàng có thể hiệu quả, nhưng liệt kê mọi đơn `PAID` của tenant khi không biết khách hàng có thể phải đọc rất nhiều partition.

### 7.3. Lọc khoảng, thứ tự và giới hạn

~~~text
ListOrders(
  tenantId = T17,
  customerId = C42,
  createdAt in [2026-11-01, 2026-12-01),
  sort = createdAt DESC,
  limit = 20
)
~~~

Một index ghép hoặc clustering key đúng thứ tự thường giúp lọc và đọc theo thời gian. Nếu yêu cầu chuyển sang sort theo `totalAmount DESC`, đường truy cập cũ không nhất thiết còn phù hợp.

### 7.4. Tìm kiếm đa thuộc tính hoặc toàn văn

~~~text
SearchProducts(
  keyword = "laptop mỏng nhẹ",
  brand in [A, B],
  price in [10000000, 20000000),
  sort = relevance DESC
)
~~~

Đây không phải point lookup. Cần xét khả năng tìm văn bản, lọc dạng faceted search, xếp hạng, phân trang và tính mới của chỉ mục. Một kho key–value thuần túy không tự có khả năng tìm mọi giá trị bên trong payload; có thể cần công cụ tìm kiếm hoặc read model riêng.

### 7.5. Duyệt quan hệ

~~~text
FindAllPrerequisiteCourses(courseId, maxDepth = 5)
~~~

Nếu domain có nhiều đường đi liên quan và thường xuyên truy vấn nhiều bước, mô hình đồ thị có thể được cân nhắc. Tuy nhiên, vẫn phải biết bắt đầu từ node nào, giới hạn độ sâu và độ phân nhánh; “cần graph” không đủ để đánh giá hiệu năng.

### 7.6. Truy vấn có bộ lọc tùy ý

Nếu người dùng có thể kết hợp 30 thuộc tính theo nhiều toán tử và sort khác nhau, không thể giả định có một index đơn lẻ tối ưu tất cả. Danh mục access patterns cần nêu rõ **những tổ hợp bắt buộc nhanh**, **những tổ hợp cho phép chạy chậm/async**, và **những tổ hợp không hỗ trợ**.

Đừng biến câu “cần lọc linh hoạt” thành yêu cầu không giới hạn. Nó phải được làm rõ bằng:

- Danh sách trường và toán tử thực sự cần.
- Mẫu tổ hợp thường gặp và dữ liệu có độ chọn lọc cao/thấp.
- Các sort bắt buộc.
- Số bản ghi trả về và giới hạn trang.
- Latency, độ mới và chi phí chấp nhận được.

## 8. Phân loại theo tính nhất quán và bất biến nghiệp vụ

Một query phản hồi nhanh nhưng trả dữ liệu không phù hợp có thể nguy hiểm hơn một query chậm.

| Nhóm yêu cầu | Ví dụ | Tác động thiết kế |
| --- | --- | --- |
| **Strong/authoritative read** | Đọc số lượng còn để xác nhận bán | Cần xác định nguồn có thẩm quyền và điều kiện ghi |
| **Read-after-write** | Vừa tạo đơn, mở trang chi tiết phải thấy đơn | Cần biết nơi dữ liệu đã ghi và cơ chế đọc sau ghi |
| **Eventual consistency** | Search index sản phẩm cập nhật trễ vài giây | Phải công bố/đo lag và xử lý kết quả cũ |
| **Conditional atomic update** | Chỉ giảm stock khi còn đủ | Kiểm tra điều kiện và cập nhật phải phối hợp an toàn |
| **Idempotent operation** | Callback thanh toán đến lặp | Định danh request/event và xử lý trùng |
| **Multi-record invariant** | Đơn và thanh toán phải thống nhất theo nghiệp vụ | Đánh giá transaction hoặc quy trình phân tán |
| **Audit/history** | Xem ai sửa giá và giá cũ | Ghi lịch sử, retention và quyền đọc |

### Một pattern cần xác định “đọc ngay tại đâu”

Ví dụ:

~~~text
Checkout:
  Order service lưu trạng thái PAID làm nguồn chính.
  Search index và báo cáo doanh thu cập nhật từ sự kiện.

Pattern A:
  Customer mở chi tiết đơn ngay sau thanh toán.
  Yêu cầu: trạng thái chính xác theo Order service.

Pattern B:
  Admin xem thống kê doanh thu theo giờ.
  Yêu cầu: cho phép trễ trong một ngưỡng đã định.
~~~

Hai mẫu có thể cùng đọc thông tin từ đơn hàng nhưng **khác mức nhất quán và mục tiêu độ trễ**. Không nên để một projection có thể chậm quyết định việc giao hàng hoặc xác nhận thanh toán nếu nghiệp vụ không cho phép.

Ngoài ra, không tự mặc định mọi NoSQL DBMS đều thiếu transaction hoặc mọi RDBMS đều cho phép mọi truy vấn được nhất quán toàn cục. Bảo đảm thực tế phụ thuộc DBMS, cách triển khai, cấu hình và phạm vi giao dịch.

## 9. Phân loại theo tải, kích thước và phân bố

Đây là phần thường bị bỏ sót nếu nhóm phát triển chỉ phỏng vấn về chức năng.

### 9.1. Tách số lượt trung bình và đỉnh

Giả sử hệ thống có **1.200.000 lượt mở chi tiết sản phẩm mỗi ngày**. Tốc độ trung bình xấp xỉ:

~~~text
1.200.000 / 86.400 ≈ 13,9 reads/giây
~~~

Nếu giờ cao điểm cao gấp 20 lần trung bình, tốc độ có thể ở mức khoảng **278 reads/giây**. Đây là **giả định minh họa**, không phải phép dự báo đã đo.

Chỉ ghi “1,2 triệu reads/ngày” chưa đủ để chọn hệ lưu trữ. Cần bổ sung:

- RPS trung bình/peak và tần suất burst.
- Kích thước response, số bản ghi và số byte đọc mỗi request.
- Số lượng đọc cache hit/miss nếu có cache.
- Độ chọn lọc của bộ lọc: 0,1%, 10% hay 90% bản ghi phù hợp.
- Tăng trưởng dữ liệu/ngày và vòng đời dữ liệu.
- Tỉ lệ đọc/ghi theo từng loại entity.

### 9.2. Phân bố lệch có thể quan trọng hơn tổng lượng

Ví dụ hệ thống có một triệu sản phẩm, nhưng 90% lượt xem tập trung vào một nghìn sản phẩm hot. Nếu chỉ chia tổng reads cho một triệu `productId`, sẽ đánh giá thấp tải trên các key nóng.

Tương tự, một tenant có thể có 500 đơn/ngày còn tenant lớn nhất có 500.000 đơn/ngày. Với thiết kế partition theo `tenantId` đơn độc, **tenant lớn nhất** có thể quyết định vấn đề nóng hoặc phân vùng phát triển không giới hạn.

Nên thu thập:

~~~text
Per-tenant: count, rps, peak rps, top 10 tenants
Per-key: top read keys / write keys
Per-customer: orders count distribution
Per-device: event rate, payload size, late arrival rate
Per-query: p50, p95, p99 latency and scanned/returned ratio
~~~

Không nhất thiết phải đo mọi chỉ số cho mọi pattern ở giai đoạn đầu, nhưng những **giả định về phân bố** phải được ghi rõ.

### 9.3. Nguồn số liệu

- Traces/log truy vấn hiện có: tần suất theo endpoint hoặc query shape.
- APM/metrics: độ trễ, lỗi, retry, số lần gọi/giây.
- Số liệu nghiệp vụ: số người dùng hoạt động, đơn/ngày, sản phẩm/shop, kích thước giỏ.
- Tác vụ batch: số bản ghi/quãng thời gian xử lý, đỉnh theo lịch.
- Dự báo sản phẩm: sự kiện ra mắt, chiến dịch khuyến mãi, mở tenant mới.

Khi chưa có hệ đang chạy, nên ghi **ước lượng có nguồn và biên độ**, sau đó lập kế hoạch đo khi triển khai thử. Đừng chuyển phỏng đoán thành con số chắc chắn trong tài liệu.

## 10. Phân loại theo phạm vi dữ liệu và an toàn truy cập

Phân loại theo tính năng là chưa đủ; phải biết **truy vấn được phép nhìn thấy tập dữ liệu nào**.

Ví dụ:

~~~text
GET /orders/{orderId}

Không đủ:
  orderId = O1008

Cần thêm:
  authenticatedCustomerId = C42
  tenantId = T17
  order must belong to C42 and T17
~~~

Một pattern nên ghi:

- **Định danh và phạm vi tenant**: user nào, shop nào, tổ chức nào.
- **Điều kiện kiểm quyền**: chủ sở hữu, vai trò, quyền trên tài nguyên.
- **Trường được trả về**: một số thuộc tính chỉ dành cho nhân viên hoặc đối tác.
- **Hạn mức truy vấn**: giới hạn export, số dòng/trang, tốc độ truy cập.
- **Retention và yêu cầu xóa**: có bản cache, index, bản sao hoặc lịch sử không.

Không được coi việc đưa `tenantId` vào key hoặc partition key là đủ để ngăn truy cập chéo tenant. Đó là cách **tổ chức dữ liệu**, còn xác thực và phân quyền cần được thực thi trong ứng dụng và DBMS/hạ tầng tương ứng.

Một tác vụ quản trị “tìm đơn theo số điện thoại khách hàng” có thể ít được gọi, nhưng rủi ro dữ liệu cao và yêu cầu index khác với tìm đơn theo `orderId`. Vì vậy các pattern quản trị vẫn phải được ghi vào danh mục.

## 11. Ví dụ đầy đủ: danh mục mẫu truy cập của một sàn thương mại điện tử

Giả sử ứng dụng có nhiều **shop/tenant**, khách hàng mua sản phẩm, theo dõi đơn hàng, nhân viên xử lý đơn và hệ thống tạo báo cáo. Đây là mô hình nghiệp vụ **giả định** để minh họa cách kiểm kê.

### 11.1. Nhóm đọc của khách hàng và nhân viên

| ID | Mẫu truy cập | Đầu vào/bộ lọc và thứ tự | Kết quả | Nhóm chính |
| --- | --- | --- | --- | --- |
| **CAT-R-01** | Xem chi tiết sản phẩm | `tenantId + productId` | Một sản phẩm với thuộc tính chi tiết | Point read |
| **CAT-R-02** | Duyệt danh mục | `tenantId + categoryId`, giá tăng dần, cursor | 20 sản phẩm/trang | Filtered/range + sorted top N |
| **CAT-R-03** | Tìm kiếm sản phẩm | Từ khóa + danh mục/giá/thương hiệu, xếp hạng | 20 kết quả + tổng/facets nếu cần | Full-text search |
| **CART-R-01** | Xem giỏ hàng | `customerId/cartId` | Dòng hàng và tổng tạm tính | Point read / embedded read |
| **ORD-R-01** | Xem chi tiết đơn | `tenantId + orderId`, kiểm quyền | Trạng thái và các dòng hàng | Point read |
| **ORD-R-02** | Xem đơn mới nhất của khách | `tenantId + customerId`, `createdAt DESC` | 20 đơn/trang | Ordered range read |
| **ORD-R-03** | Shop xem đơn cần xử lý | `tenantId + shopId + status`, `createdAt ASC` | 50 đơn/trang | Filtered list |
| **SUP-R-01** | Hỗ trợ tìm đơn theo email/số điện thoại | Người liên hệ + khoảng thời gian, kiểm quyền | Danh sách đơn phù hợp | Secondary lookup / admin search |
| **ANL-R-01** | Doanh thu theo ngày | `shopId + date range` | Tổng tiền/số đơn theo ngày | Aggregate/time-series |

### 11.2. Nhóm ghi, sự kiện và vận hành

| ID | Mẫu truy cập | Điều kiện đầu vào/bất biến | Nhóm chính |
| --- | --- | --- | --- |
| **CAT-W-01** | Tạo/cập nhật sản phẩm | ID không trùng; thông số đúng loại; version khi sửa | Insert/conditional update |
| **CART-W-01** | Thêm SKU vào giỏ | Tăng số lượng không làm mất cập nhật song song | Partial update/counter |
| **INV-W-01** | Giữ số lượng tồn | Chỉ giữ nếu còn đủ; không xử lý trùng request | Conditional atomic update |
| **ORD-W-01** | Tạo đơn | Mã yêu cầu chống lặp, giá tại thời điểm chốt, dòng hàng | Transactional create |
| **PAY-W-01** | Xác nhận thanh toán | Callback có thể trùng/đến trễ, chuyển trạng thái hợp lệ | Idempotent state transition |
| **EVT-W-01** | Ghi/phát `OrderPaid` | Event ID, bảo đảm không bỏ sót tác động đã commit | Append/event delivery |
| **ANL-W-01** | Cập nhật doanh thu ngày | Hạn chế đếm trùng, dữ liệu hoàn tiền và đến muộn | Derived data update |
| **OPS-R-01** | Xuất đơn theo tháng | Lọc theo tenant/date, phân trang toàn bộ dữ liệu | Batch/export scan |
| **OPS-W-01** | Xóa session/dữ liệu hết hạn | Chính sách retention, TTL, các bản sao và index | Delete/expire |
| **OPS-W-02** | Tạo lại search index | Đọc nguồn, reindex, đối soát tiến độ, bắt kịp cập nhật | Backfill/rebuild |

Danh mục này không chỉ có “sản phẩm”, “đơn hàng”, “khách hàng”. Nó mô tả **các cách cụ thể dữ liệu được truy cập và thay đổi**, gồm cả đường vận hành và dữ liệu dẫn xuất.

### 11.3. Đi sâu vào các pattern dễ bị gộp nhầm

**CAT-R-01 và CAT-R-02** cùng đọc sản phẩm nhưng không cùng đường truy cập. Một document truy cập theo ID có thể phù hợp CAT-R-01; CAT-R-02 cần tìm sản phẩm theo danh mục, thứ tự giá và phân trang. Nếu dùng document DBMS, có thể cân nhắc index ghép theo các trường truy vấn; nếu dùng key–value thuần túy, có thể cần cấu trúc tra cứu được duy trì riêng.

**ORD-R-02 và ORD-R-03** cùng đọc đơn hàng nhưng một cái có nhóm theo khách hàng và thời gian giảm dần, cái còn lại nhóm theo shop/trạng thái và thời gian tăng dần. Một bảng wide-column phân vùng theo khách hàng **không tự** làm truy vấn theo shop/trạng thái hiệu quả. Có thể cần nhiều read model hoặc DBMS có cơ chế truy vấn phụ phù hợp.

**ORD-W-01 và PAY-W-01** không thể mô tả gọn là “ghi order”. Tạo đơn và xác nhận thanh toán có bất biến khác nhau; một callback trùng không được dẫn đến thanh toán hoặc trừ kho hai lần. Cần xác định key chống lặp, điều kiện chuyển trạng thái và phạm vi transaction.

**ANL-R-01** có thể chấp nhận dữ liệu chậm vài phút và dùng bảng tổng hợp, còn trạng thái thanh toán trong **ORD-R-01** có thể phải đến từ nguồn có thẩm quyền. Đặt cả hai vào một collection dùng chung mà không ghi yêu cầu độ mới là một rủi ro thiết kế.

## 12. Chuyển access patterns thành những câu hỏi mô hình hóa NoSQL

Sau khi có danh mục, ta chưa nên lập tức quyết định một DBMS. Trước hết phân tích từng pattern theo **đường truy cập và đơn vị dữ liệu**.

| Đặc tính pattern | Câu hỏi thiết kế | Hướng cần khảo sát |
| --- | --- | --- |
| Point read với key biết trước | ID/partition key được xác định từ request chưa? | Key–value/document/bảng khóa chính |
| Đọc cả thực thể có nhiều trường con | Các trường có luôn được đọc và cập nhật cùng nhau không? | Document embedding hoặc thiết kế giá trị nguyên khối |
| Sorted range theo một nhóm | Nhóm và thứ tự có phù hợp partition/clustering hay index ghép không? | Wide-column, index ghép, ordered read model |
| Lọc nhiều thuộc tính tùy chọn | Trường nào thường lọc, có tìm từ khóa không? | Document/RDBMS index, search engine |
| Duyệt mối quan hệ nhiều bước | Độ sâu, loại cạnh, hướng và số nhánh là gì? | Property graph, recursive queries hoặc projection |
| Time-series ghi liên tục | Event time, bucket, retention, write rate ra sao? | Time partitioning, time-series store, wide-column |
| Aggregate thường được xem | Quét nguồn có đáp ứng SLO không? | Materialized view, rollup, analytics read model |
| Ghi nhiều thực thể có ràng buộc | Phải nguyên tử và cô lập đến đâu? | Transaction và domain consistency |
| Nhiều đường đọc trên cùng dữ liệu | Có thể nhân bản/projection không, và chấp nhận trễ bao lâu? | Secondary index, CQRS, materialized views |

### Ví dụ về mô hình hóa theo truy vấn trong wide-column

Giả sử `ORD-R-02` yêu cầu 20 đơn gần nhất của một khách hàng. Một bảng hướng truy vấn trong Apache Cassandra có thể là:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    bucket_month text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, bucket_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Đây là **ví dụ CQL**, không phải lựa chọn bắt buộc. `tenant_id + customer_id + bucket_month` là partition key ghép; `created_at`, `order_id` là clustering columns. Truy vấn theo một khách hàng trong một tháng có đường truy cập rõ ràng, nhưng nếu trang lịch sử cần dữ liệu qua nhiều tháng, ứng dụng phải đọc các bucket liên quan và gộp/phân trang đúng.

**ORD-R-03** (“đơn cần xử lý theo shop và trạng thái”) vẫn chưa được giải quyết bằng bảng này vì thiếu `customer_id`. Danh mục access patterns giúp phát hiện nhu cầu ấy **trước khi khóa schema**.

### Ví dụ về index trong document DBMS

Với `CAT-R-02`, một index được cân nhắc trong MongoDB:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryId: 1,
  price: 1,
  _id: 1
});

db.products.find({
  tenantId: "T17",
  categoryId: "books",
  price: { $gte: 100000, $lt: 500000 }
}).sort({ price: 1, _id: 1 }).limit(20);
~~~

Ví dụ minh họa tương quan giữa **điều kiện lọc**, **thứ tự trả về** và **thứ tự trường trong index**. Việc DBMS có chọn index này và có đáp ứng SLO không phụ thuộc số lượng dữ liệu, độ chọn lọc, bộ tối ưu hóa và kế hoạch thực thi thực tế. Các pattern tìm toàn văn vẫn có thể cần index/tính năng khác.

### Đường truy cập mới có thể tạo dữ liệu dẫn xuất

~~~text
         Order service: authoritative orders
                        │
               OrderChanged events
                        │
          ┌─────────────┼────────────┐
          ▼             ▼            ▼
  orders_by_customer  orders_by_shop  daily_revenue
     (read model)       (read model)   (aggregate)
          │             │            │
      ORD-R-02       ORD-R-03       ANL-R-01
~~~

Nếu dùng mô hình này, phải thêm **những pattern bảo trì** vào danh mục: ghi projection, xử lý trùng sự kiện, rebuild sau lỗi, đo độ trễ đồng bộ và đối soát nguồn. Chỉ ghi các pattern đọc mà bỏ qua chi phí duy trì bản dữ liệu dẫn xuất sẽ khiến đánh giá mô hình quá lạc quan.

## 13. Phân trang, sắp xếp và giới hạn kết quả là phần của pattern

“Liệt kê đơn hàng của khách” chưa đủ. Cần biết:

- Một trang có 20, 50 hay 1.000 bản ghi?
- Có cần tổng số kết quả chính xác không?
- Sort theo `createdAt`, `updatedAt`, giá trị đơn hay trạng thái?
- Có thể tải trang thứ 10.000 không?
- Dữ liệu mới có thể được thêm trong lúc người dùng phân trang không?
- Cursor có cần giữ thứ tự và ràng buộc quyền truy cập theo tenant không?

### Offset so với cursor/keyset pagination

Với dữ liệu tăng liên tục, truy vấn dạng:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 'C42'
ORDER BY created_at DESC
LIMIT 20 OFFSET 100000;
~~~

có thể ngày càng tốn kém khi offset lớn, tùy DBMS và kế hoạch thực thi. Nó cũng có thể gặp tình huống dữ liệu bị thêm/xóa trong lúc người dùng chuyển trang.

Một mô hình phân trang theo **cursor/keyset** thường dùng trường sắp xếp ổn định, chẳng hạn cặp `(createdAt, orderId)`. Ở mức ý tưởng:

~~~text
Page 1: newest 20 orders, sorted by (createdAt DESC, orderId DESC)
Cursor: last (createdAt, orderId) from page 1
Page 2: next 20 orders older than cursor
~~~

Việc chọn cursor cần phù hợp semantics DBMS, xử lý dữ liệu đồng thời và xác nhận không đưa quyền của tenant khác vào cursor. Một API có thể còn cần watermark/snapshot khi người dùng yêu cầu danh sách bất biến trong suốt phiên export.

**Chỉ có index không thay thế được yêu cầu phân trang.** Kết quả trả một triệu dòng trong một request vẫn có thể không đáp ứng thời gian và giới hạn bộ nhớ, ngay cả khi tìm kiếm bước đầu nhanh.

## 14. Phân loại theo vòng đời: realtime, gần realtime và batch

Mẫu truy cập cũng cần được chia theo **nhịp thực hiện** và **thời gian chấp nhận hoàn thành**.

| Nhịp | Ví dụ | Trọng tâm |
| --- | --- | --- |
| **Đồng bộ theo request** | Xem chi tiết đơn, xác nhận giữ tồn | Latency thấp, bảo đảm dữ liệu và timeout rõ |
| **Bất đồng bộ gần realtime** | Cập nhật search index từ ProductChanged | Consumer lag, event ordering, retry |
| **Theo cửa sổ thời gian** | Tổng hợp sensor mỗi phút | Event time, dữ liệu đến trễ, watermark |
| **Batch định kỳ** | Doanh thu cuối ngày, export tháng | Throughput, quãng xử lý, điểm dừng/restart |
| **Vận hành bất thường** | Backfill, reindex, khôi phục dữ liệu | Tải đỉnh ngoài dự kiến, không phá SLO online |

Một hệ thống có thể có **cùng tập dữ liệu nhưng nhiều nhịp truy cập**. Chẳng hạn bộ dữ liệu đơn hàng có point lookup đồng bộ, read model gần realtime, batch export cuối tháng và job retention mỗi quý. Mỗi loại cần tiêu chí đánh giá riêng.

Đối với tác vụ batch, “xử lý 20 triệu bản ghi” chưa đủ; phải biết **khi nào chạy**, **có thể ảnh hưởng traffic online không**, **khả năng tiếp tục sau lỗi** và **cần trạng thái nhất quán ở một mốc nào không**.

## 15. Ưu tiên các pattern mà không bỏ quên trường hợp ít gặp

Không phải tất cả pattern đều quan trọng như nhau. Có thể dùng ba mức ưu tiên:

| Mức | Cách hiểu | Ví dụ |
| --- | --- | --- |
| **P0 — Bắt buộc đáp ứng** | Đường nghiệp vụ thiết yếu, yêu cầu đúng đắn/độ trễ nghiêm ngặt hoặc rủi ro cao | Thanh toán, giữ tồn, đọc đơn theo quyền |
| **P1 — Quan trọng thường xuyên** | Trải nghiệm sử dụng chính, tải đáng kể, hiệu năng cần được thiết kế | Danh mục, tìm kiếm, lịch sử đơn |
| **P2 — Ít thường xuyên hoặc có thể xử lý bất đồng bộ** | Có thể đáp ứng bằng job/báo cáo với ngưỡng thời gian khác | Export lớn, phân tích lịch sử |

Đây là **hệ thống phân cấp minh họa**; mỗi đội có thể dùng quy ước khác. Không nên xếp P2 chỉ vì ít gọi: một truy vấn xóa theo yêu cầu pháp lý hoặc phục hồi sau sự cố ít xảy ra vẫn có thể **cực kỳ quan trọng** và phải nằm trong phạm vi thiết kế.

Một bảng đánh giá còn có thể xét:

~~~text
Mức ưu tiên ≠ chỉ số requests/second

Mức ưu tiên cần xem đồng thời:
  - Thiệt hại khi sai hoặc không chạy được
  - Tần suất và lượng người bị ảnh hưởng
  - Latency/SLO và thời hạn hoàn thành
  - Độ khó thay đổi mô hình sau này
  - Rủi ro về quyền, dữ liệu cá nhân, pháp lý
  - Tải đỉnh và nguy cơ tạo hot partition
~~~

Mục tiêu không phải loại bỏ pattern ít dùng, mà là **quyết định pattern nào cần đường truy cập trực tiếp ngay từ đầu**, pattern nào có thể dùng job, search store hoặc read model bổ sung, và pattern nào được chấp nhận có độ trễ cao hơn.

## 16. Các giả định cần xác minh trước khi chốt mô hình

Một access-pattern inventory hữu ích luôn phân biệt:

- **Đã xác minh:** có API hoặc user story được chấp nhận, có log/tải thực tế.
- **Đã thống nhất nhưng chưa đo:** có yêu cầu nghiệp vụ, số lượng dự kiến nhưng chưa chạy thử.
- **Giả định cần kiểm tra:** ví dụ “đa số khách hàng có ít hơn 100 đơn” chưa có dữ liệu xác nhận.
- **Chưa quyết định:** ví dụ chính sách retention, khả năng tìm kiếm nhiều bộ lọc hay độ trễ cho phép của search index.

Ví dụ những câu hỏi mở:

~~~text
ORD-R-02:
  - Tenant lớn nhất có bao nhiêu đơn/khách?
  - Khách có được lọc theo trạng thái không?
  - Có cần đọc toàn bộ lịch sử 5 năm?
  - Sau checkout bao lâu đơn phải xuất hiện trong lịch sử?

CAT-R-03:
  - "Tìm kiếm" nghĩa là prefix, full-text hay semantic search?
  - Có cần facets, số lượng kết quả hoặc gợi ý từ khóa?
  - Giá trong search index được phép chậm bao lâu?

INV-W-01:
  - Có bao nhiêu địa điểm/kho?
  - Một sản phẩm được giữ tồn ở nhiều kho đồng thời không?
  - Nhiều request dùng cùng idempotency key được xử lý thế nào?
~~~

Không nên chọn partition key, index hay mô hình transaction dựa trên các câu trả lời chưa rõ nhưng lại trình bày chúng như sự thật.

## 17. Đối chiếu danh mục với workload thực tế

Với hệ thống đã có dữ liệu, danh mục ban đầu cần được kiểm chứng bằng thông tin vận hành:

1. **Nhóm log theo query shape**, không theo từng giá trị tham số. Ví dụ mọi `GET /orders/{id}` có thể là một shape.
2. **Kiểm tra các truy vấn chậm và phổ biến**, không chỉ top truy vấn theo RPS. Một query ít chạy nhưng quét hàng triệu bản ghi cũng có thể ảnh hưởng cụm.
3. **Đối chiếu với traces hành trình**, xem một hành động người dùng gọi bao nhiêu dịch vụ và phát sinh bao nhiêu truy vấn phụ.
4. **Tìm workload không hiện trong API**, như message consumer, cron, export, migration và công cụ vận hành.
5. **Đo phân bố dữ liệu theo khóa**, xác định nhóm/tenant hot, số phần tử tối đa, phạm vi thời gian.
6. **Đo độ trễ từng pattern theo percentile**, kết hợp tải đỉnh, kích thước kết quả và lỗi.
7. **Theo dõi biến động sau phát hành**, bổ sung pattern mới và cập nhật giả định cũ.

Ví dụ, nếu telemetry cho thấy `GET /products` có 80% request dùng sort theo giá và 20% dùng sort theo mức độ phổ biến, hai hình dạng này nên được mô tả riêng dù giao diện hiển thị chung màn hình danh mục.

Không cần biến bước này thành việc chạy bộ benchmark khi mới thu thập yêu cầu; mục tiêu là **thu được đặc trưng và bằng chứng đủ để thiết kế đúng**. Benchmark và đánh giá chi tiết được thực hiện trong giai đoạn lựa chọn/kiểm chứng giải pháp.

## 18. Những thiếu sót phổ biến trong thu thập access patterns

| Thiếu sót | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ liệt kê entity và CRUD | Không biết các truy vấn lọc/sắp xếp quan trọng | Ghi query shape theo từng hành động |
| Chỉ liệt kê màn hình khách hàng | Bỏ qua admin, batch, reindex, retention | Kiểm kê actor và job |
| Gộp mọi biến thể một endpoint thành một dòng | Không thấy nhu cầu index và truy vấn khác nhau | Tách những hình dạng có đường truy cập khác |
| Coi “truy vấn linh hoạt” là một yêu cầu đầy đủ | Không biết phạm vi index/search phải hỗ trợ | Liệt kê trường, toán tử, sort và các tổ hợp bắt buộc |
| Chỉ ghi read, không ghi write | Bỏ qua tranh chấp, transaction và write amplification | Bổ sung mọi đường tạo/sửa/xóa và cập nhật dẫn xuất |
| Chỉ lấy QPS trung bình | Không thấy peak, burst và hot key | Thu thập phân bố tải và trường hợp cực trị |
| Không ghi cách kiểm quyền | Thiết kế có nguy cơ đọc nhầm tenant hoặc dữ liệu nhạy cảm | Gắn boundary và quyền vào pattern |
| Không ghi độ mới dữ liệu | Dùng read model eventual cho quyết định cần dữ liệu đúng tức thời | Phân loại nguồn chính và lag cho phép |
| Không ghi pagination/sort | Truy vấn có index nhưng không đáp ứng trải nghiệm | Mô tả thứ tự, top N, cursor, kích thước kết quả |
| Bỏ qua dữ liệu đến trễ và retry | Ghi trùng, báo cáo sai, thiếu kết quả | Ghi idempotency, event time, watermark và replay |
| Chọn DBMS trước rồi viết lại yêu cầu cho khớp | Không còn nhìn thấy nhu cầu thật của nghiệp vụ | Giữ inventory độc lập với thiết kế vật lý ban đầu |
| Không cập nhật inventory sau khi ra tính năng mới | Schema/index dần không phục vụ được workload | Version hóa danh mục và review khi thay đổi API |

## 19. Bài tập thực hành

### Bài 1 — Tách access pattern từ một màn hình

Một màn hình “Đơn hàng” có ba tab: **Tất cả**, **Đang giao**, **Đã hủy**; có bộ lọc theo tháng và sắp theo đơn mới nhất. Hãy:

1. Đặt tên những query shape khác nhau.
2. Xác định các tham số bắt buộc về khách hàng/tenant.
3. Ghi điều kiện lọc, thứ tự và phân trang cho từng shape.
4. Phân biệt biến thể `status` nào có thể dùng cùng một index và biến thể nào cần đánh giá thêm.

**Gợi ý:** không cần một dòng cho từng tháng. Nhưng phải ghi rõ một shape không lọc trạng thái và một shape có lọc trạng thái có thể cần đường truy cập khác; tác động phụ thuộc DBMS và thứ tự index.

### Bài 2 — Tìm lỗi trong bản mô tả

Một tài liệu yêu cầu ghi:

~~~text
Feature: Product listing
Query: Get products
Load: High
Consistency: Normal
~~~

Hãy chỉ ra ít nhất sáu thông tin đang thiếu.

**Gợi ý:** đầu vào danh mục/tenant, bộ lọc, sort, kết quả/trang, QPS đỉnh, p95 latency, mức độ mới, bảo mật, độ chọn lọc, dữ liệu tăng trưởng và quy tắc phân trang.

### Bài 3 — Phân loại read/write

Xếp các thao tác sau vào nhóm phù hợp:

~~~text
A. GET product by ID
B. Search products by keyword and brand
C. Decrement stock only when available >= requested
D. Get last 100 temperature readings of one device
E. Replay OrderPaid events after consumer crash
F. Export all orders from one tenant for previous year
G. Update daily-revenue projection after payment
~~~

**Gợi ý:** lần lượt có thể là point read, full-text/filter, conditional update, ordered range/time-series, replay/batch, export scan, derived-data update. Một thao tác có thể thuộc nhiều nhóm.

### Bài 4 — Phát hiện query không được schema hỗ trợ

Một bảng Cassandra có partition key `(tenantId, customerId)` và clustering theo `createdAt DESC`. Hệ thống đã hỗ trợ lấy lịch sử đơn theo khách hàng. Sau đó xuất hiện yêu cầu:

> “Nhân viên kho cần 50 đơn trạng thái PACKING mới nhất của một shop.”

Vì sao đây là access pattern mới đáng ghi riêng? Có thể đặt câu hỏi gì trước khi tạo thêm bảng hoặc index?

**Gợi ý:** truy vấn không biết `customerId`; cần xem phân bố theo shop, trạng thái, thời gian, yêu cầu độ mới, quyền truy cập và cách cập nhật read model khi order đổi trạng thái.

### Bài 5 — Ước lượng tải đúng cách

Một ứng dụng có 600.000 lượt đọc sản phẩm/ngày. Có nên lấy giá trị trung bình/giây rồi coi đó là tải tối đa để chọn DBMS không? Những yếu tố nào có thể khiến đỉnh thực tế cao hơn rất nhiều?

**Gợi ý:** không; cần xét giờ cao điểm, chiến dịch marketing, retry, cache miss, bot, hot product, burst, số lượng truy vấn phụ trên mỗi hành động.

### Bài 6 — Điều kiện nhất quán

Trạng thái đơn đã thanh toán được ghi trong Order service, còn màn hình báo cáo sử dụng search index cập nhật bất đồng bộ. Người dùng vừa thanh toán và nhấn “Xem chi tiết đơn”, còn nhân viên xem doanh thu theo ngày.

Hãy ghi **hai access pattern** với nguồn đọc, độ mới cho phép, cách xử lý khi projection chậm và hậu quả nếu đọc nhầm nguồn dữ liệu.

**Gợi ý:** đọc chi tiết giao dịch thường cần nguồn có thẩm quyền hoặc cơ chế đảm bảo vừa ghi xong thì nhìn thấy. Báo cáo có thể cho phép lag có đo/hiển thị, tùy yêu cầu nghiệp vụ.

## 20. Mẫu bảng tổng hợp cuối cùng để dùng trong thiết kế

Một bảng tối thiểu có thể bắt đầu bằng:

| ID | Actor/trigger | Kiểu | Key/bộ lọc | Sort/page | Độ mới & điều kiện ghi | Tải/độ trễ | Ưu tiên |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CAT-R-01 | Customer xem sản phẩm | Point read | Tenant + productId | Một bản ghi | Dữ liệu hiển thị có thể theo chính sách cache | Peak TBD, p95 TBD | P0 |
| CAT-R-02 | Customer duyệt danh mục | Filtered range | Tenant + category + price | Price ASC, 20/page | Độ mới giá/tồn cần xác định | Peak TBD, p95 TBD | P1 |
| ORD-R-02 | Customer xem lịch sử | Ordered range | Tenant + customer | CreatedAt DESC, 20/page | Sau checkout phải hiện trong ngưỡng đã định | Peak TBD, p95 TBD | P0 |
| INV-W-01 | Checkout giữ tồn | Conditional write | Tenant + SKU + location | Không áp dụng | Không trừ vượt tồn; chống request trùng | Peak TBD, p95 TBD | P0 |
| ANL-R-01 | Seller xem doanh thu | Aggregate | Shop + date range | Theo ngày | Cho phép lag có giới hạn | Job/read TBD | P1 |
| OPS-R-01 | Support xuất dữ liệu | Export scan | Tenant + date range | Paged/batch | Phân quyền và mốc dữ liệu xuất | Deadline TBD | P1 |

Bảng này là **mục lục**. Các pattern quan trọng nên có thẻ chi tiết như phần 5, vì một dòng ngắn không thể chứa đầy đủ quy tắc nghiệp vụ hoặc workload. Đặc biệt, mọi ô `TBD` cần có người chịu trách nhiệm và hạn xác minh, không được coi là đã hoàn thành thu thập.

Khi danh mục được dùng để thiết kế, có thể bổ sung cột:

~~~text
ProposedAccessPath
  = Primary key / partition+clustering / secondary index
    / search index / graph traversal / materialized view

ProposedSource
  = Authoritative data / derived read model / cache

Evidence
  = Product requirement / API contract / observed metric / assumption

DecisionStatus
  = Draft / Agreed / Validated in workload test / Needs revision
~~~

Những cột này **nên được bổ sung sau khi đã hiểu pattern**, để không biến danh mục yêu cầu thành cách biện minh cho công nghệ chọn trước.

## 21. Kết luận: kiểm kê trước, mô hình hóa sau

Thu thập và phân loại access patterns là công việc chuyển **nhu cầu của người dùng và hệ thống** thành một bản mô tả có thể dùng để thiết kế cơ sở dữ liệu. Một bản kiểm kê tốt trả lời được:

1. **Ai truy cập và vì sao?** Gắn truy vấn với hành trình, API, sự kiện, job và trách nhiệm nghiệp vụ.
2. **Dữ liệu được đọc/ghi theo hình dạng nào?** Key, điều kiện bằng/khoảng, sắp xếp, giới hạn, phân trang, tổng hợp, tìm kiếm, duyệt quan hệ hay cập nhật có điều kiện.
3. **Có bao nhiêu tải và phân bố ra sao?** Trung bình, đỉnh, hot key, tăng trưởng, dung lượng kết quả, số phần tử trong một nhóm.
4. **Cần bảo đảm điều gì?** Độ trễ, độ mới, nguyên tử, chống ghi trùng, quyền truy cập, retention và khả năng phục hồi.
5. **Những gì chưa biết?** Ghi rõ giả định, người xác nhận và cách đo để không khóa mô hình theo phỏng đoán.

**Đầy đủ không có nghĩa mô tả mọi giá trị hay mọi tổ hợp lý thuyết; đầy đủ nghĩa là không bỏ sót một kiểu truy cập có thể làm thay đổi quyết định lưu trữ, chỉ mục, phân vùng, bảo đảm cập nhật hoặc vận hành.**

Khi access patterns đã được mô tả rõ, việc chọn giữa key–value, document, wide-column, graph, RDBMS hoặc các read model chuyên dụng trở thành một quá trình **đánh giá có căn cứ**. Đó chính là nền tảng của tư duy *thiết kế theo truy vấn* trong NoSQL.
