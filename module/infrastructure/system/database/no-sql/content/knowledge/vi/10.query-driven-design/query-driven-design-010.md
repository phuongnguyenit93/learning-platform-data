# Bổ sung đường truy cập mới khi yêu cầu nghiệp vụ thay đổi

Trong thiết kế NoSQL theo truy vấn (*query-driven design*), cấu trúc lưu trữ được lựa chọn từ **những cách ứng dụng cần đọc và ghi dữ liệu**. Một bảng theo khóa chính có thể cực kỳ hiệu quả để lấy một đơn hàng theo `orderId`, nhưng lại không phù hợp khi sản phẩm bổ sung màn hình “những đơn cần giao của cửa hàng, mới nhất trước”.

Đây là tình huống rất thường gặp trong vòng đời sản phẩm: **đường truy cập cũ vẫn hoạt động tốt, nhưng một yêu cầu mới đòi hỏi cách định vị, lọc hoặc sắp xếp khác**. Nếu cứ nối thêm bộ lọc, quét dữ liệu, hoặc lấy hàng nghìn bản ghi về ứng dụng để tự sắp xếp, hệ thống có thể vượt ngân sách độ trễ và chi phí khi dữ liệu tăng.

Bài học này trình bày cách bổ sung một đường truy cập mới trong NoSQL mà không làm hỏng những chức năng đang chạy: từ phân tích yêu cầu, lựa chọn chỉ mục/bảng đọc, quản lý dữ liệu trùng lặp, nạp dữ liệu lịch sử (*backfill*), đồng bộ thay đổi mới (*change stream/CDC*), chuyển đổi không gián đoạn, cho tới đo lường chi phí và tính đúng đắn.

Ví dụ xuyên suốt là một hệ thống quản lý đơn hàng đa cửa hàng, minh họa chi tiết bằng bảng kiểu **wide-column/Cassandra CQL**. Đồng thời, bài sẽ chỉ ra khi nào nên chọn **secondary index**, **global secondary index**, **read model**, **cache** hoặc **hệ tìm kiếm** ở những loại NoSQL khác.

## 1. Đường truy cập là gì?

**Đường truy cập (access path)** là cách hệ thống xác định nơi có dữ liệu phù hợp và lấy chúng theo mẫu truy vấn cụ thể, thay vì phải duyệt toàn bộ tập dữ liệu.

Nó có thể được hiện thực bằng:

| Loại đường truy cập | Ví dụ | Truy vấn phù hợp |
| --- | --- | --- |
| **Primary key lookup** | `orders_by_id[(tenantId, orderId)]` | Lấy một đơn theo ID |
| **Secondary/compound index** | Index trên `tenantId, shopId, status, createdAt` | Lọc và sắp xếp theo các trường đã đánh chỉ mục |
| **Partition + clustering order** | `orders_by_customer_month` | Lấy các đơn mới nhất của một khách |
| **Bảng dữ liệu đọc riêng** | `ready_orders_by_shop_day` | Lấy đơn cần giao theo cửa hàng và ngày |
| **Chỉ mục tự duy trì trong key–value** | `shop:12:ready-orders` | Lấy tập ID đã sắp xếp hoặc nhóm trước |
| **Search index** | Index tìm kiếm văn bản/thuộc tính | Bộ lọc linh hoạt, keyword, relevance |
| **Materialized aggregate** | `daily_orders_by_shop` | Dashboard thống kê tổng hợp |
| **Graph relationship path** | `(Shop)-[:HAS_ORDER]->(Order)` | Duyệt và phân tích quan hệ phù hợp |

Đường truy cập không nhất thiết là một bảng mới. Một index bổ sung trên tập dữ liệu hiện có cũng có thể giải quyết nhu cầu. Ngược lại, một query rất khác đôi khi nên được phục vụ bởi **một read model riêng** được thiết kế theo đúng đầu vào và thứ tự cần trả về.

### 1.1. Vì sao không thể chỉ “thêm WHERE”?

Trong nhiều NoSQL:

- Một **key–value store** không tự hiểu các thuộc tính bên trong value nếu không có index bổ sung.
- Một **wide-column store** được tối ưu cho các partition key và clustering key đã thiết kế; lọc ở cột bất kỳ có thể dẫn đến quét dữ liệu.
- Một **document store** linh hoạt trong biểu diễn truy vấn, nhưng truy vấn mới vẫn cần index phù hợp nếu dữ liệu lớn.
- Một **graph store** thuận lợi khi truy vấn theo quan hệ, song không mặc định hiệu quả khi phải sort một tập node khổng lồ theo thuộc tính toàn cục.

**Thiết kế theo truy vấn** không có nghĩa mỗi yêu cầu phải tạo một database mới. Nó có nghĩa phải xem xét cụ thể **cấu trúc nào giúp query thực sự chạy hiệu quả**, rồi cân bằng chi phí thêm cấu trúc đó.

## 2. Hệ thống ban đầu và nhu cầu phát sinh

Giả sử một nền tảng thương mại có nhiều tenant, mỗi tenant quản lý nhiều cửa hàng. Mỗi đơn hàng có:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "shopId": "shop-12",
  "customerId": "U42",
  "createdAt": "2026-11-14T09:30:00Z",
  "status": "PAID",
  "totalVnd": 1000000,
  "version": 3
}
~~~

Một đơn có thể chuyển qua:

~~~text
CREATED -> PAID -> READY_TO_SHIP -> SHIPPED -> DELIVERED
                 |
                 -> CANCELLED (nếu quy tắc nghiệp vụ cho phép)
~~~

Sơ đồ là luồng minh họa; hệ thống thật có thể có trạng thái hoàn tiền, thất bại thanh toán, giao thất bại hoặc chuyển tiếp khác. Các chuyển trạng thái phải tuân theo quy tắc nghiệp vụ đã định.

### 2.1. Những truy vấn có từ đầu

| Mã | Yêu cầu | Đầu vào | Kết quả |
| --- | --- | --- | --- |
| **Q1** | Xem chi tiết một đơn | `tenantId + orderId` | Một đơn |
| **Q2** | Xem 10 đơn gần nhất của khách | `tenantId + customerId` | Danh sách đơn mới nhất |

Một kiến trúc ban đầu có thể có hai bảng: `orders_by_id` giữ dữ liệu nghiệp vụ chính và `orders_by_customer_month` phục vụ Q2.

~~~mermaid
flowchart LR
    A["API tạo / cập nhật đơn"] --> B["orders_by_id<br/>Nguồn sự thật"]
    B --> C["orders_by_customer_month<br/>Đường đọc Q2"]
    D["GET /orders/O900"] --> B
    E["GET /customers/U42/orders"] --> C
~~~

Ví dụ CQL:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id text,
    shop_id text,
    customer_id text,
    created_at timestamp,
    status text,
    total_vnd bigint,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    month_bucket text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Q1 đọc bằng khóa chính:

~~~sql
SELECT *
FROM orders_by_id
WHERE tenant_id = 'merchant-a'
  AND order_id = 'O900';
~~~

Q2 đọc theo khách hàng và bucket tháng:

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE tenant_id = 'merchant-a'
  AND customer_id = 'U42'
  AND month_bucket = '2026-11'
LIMIT 10;
~~~

Nếu tháng hiện tại có ít đơn, API đọc thêm tháng trước và hợp nhất kết quả. Đường truy cập này hiệu quả với Q2 vì ứng dụng biết đầy đủ partition key và các hàng được xếp theo `created_at`.

### 2.2. Yêu cầu mới: màn hình điều phối giao hàng

Sau khi sản phẩm phát triển, quản lý cửa hàng cần màn hình:

> **Q3:** “Xem tối đa 20 đơn đang ở trạng thái `READY_TO_SHIP` của cửa hàng `shop-12`, được tạo trong 7 ngày gần đây, sắp xếp từ đơn mới nhất đến cũ nhất.”

Hợp đồng yêu cầu:

| Thuộc tính | Quy định minh họa |
| --- | --- |
| Tenant | Lấy từ ngữ cảnh xác thực; không tin giá trị tenant do client tự khai |
| Cửa hàng | `shopId`, phải thuộc tenant và quyền người gọi |
| Trạng thái | Chính xác `READY_TO_SHIP` |
| Cửa sổ thời gian | `createdAt >= now - 7 days` (đặt rõ là thời gian tạo) |
| Sắp xếp | `createdAt DESC`, nếu bằng nhau `orderId ASC` |
| Phân trang | 20 đơn/trang; cursor thay vì quét/offset lớn |
| Độ trễ mục tiêu | Ví dụ p95 không quá 150 ms tại tải dự kiến |
| Độ mới dữ liệu | Ví dụ dashboard chấp nhận trễ tối đa vài giây |
| Đúng quyền | Không bao giờ trả đơn của tenant/cửa hàng khác |

**Các con số SLA chỉ là giả định học tập.** Điều quan trọng là chuyển mong muốn “hiển thị nhanh” thành một tập điều kiện có thể đo.

### 2.3. Đường đọc hiện tại thiếu gì?

`orders_by_id` yêu cầu `tenantId + orderId`, nhưng Q3 **không biết trước orderId**.

`orders_by_customer_month` yêu cầu `customerId`, trong khi Q3 cần đọc **mọi khách của một shop**.

Do vậy, cả hai bảng hiện tại **không định vị trực tiếp được tập đơn cần giao**. Việc tồn tại `shopId` và `status` trong các hàng không có nghĩa truy vấn theo hai thuộc tính ấy tự động rẻ.

## 3. Ba cách sửa nhanh nhưng dễ gây vấn đề

### 3.1. Quét toàn bảng rồi lọc

Một ý tưởng:

~~~text
Đọc mọi đơn của tenant
-> lọc shopId = shop-12
-> lọc status = READY_TO_SHIP
-> lọc createdAt trong 7 ngày
-> sort createdAt DESC
-> lấy 20 đơn
~~~

Nếu tenant có hàng chục triệu đơn, phải xử lý rất nhiều hàng để lấy 20 kết quả. Với Cassandra, thêm `ALLOW FILTERING` vào một truy vấn không khớp khóa **không tự tạo chỉ mục**; hệ thống có thể phải lọc lượng dữ liệu lớn, gây độ trễ và áp lực lên các node.

### 3.2. Lấy dữ liệu gần đúng rồi lọc tại ứng dụng

Giả sử ứng dụng lấy `LIMIT 20` từ một danh sách khác, sau đó mới lọc trạng thái. Nếu chỉ 5% đơn là `READY_TO_SHIP`, 20 đơn đầu có thể không chứa đủ 20 đơn hợp lệ, dù ở phía sau vẫn còn rất nhiều.

**Giới hạn trước khi lọc** trên đường truy cập không phù hợp có thể tạo **kết quả thiếu hoặc sai thứ tự**. Tăng thành 1.000 bản ghi chỉ là cách trì hoãn vấn đề nếu phân bố status và dữ liệu còn thay đổi.

### 3.3. Dùng một cache danh sách không có kế hoạch cập nhật

Một cache `shop-12:ready-orders` có thể trả nhanh, nhưng nếu không có cách thêm đơn mới, loại đơn đã giao, xử lý retry và dọn dữ liệu cũ thì danh sách nhanh mà **sai nghiệp vụ**.

Cache là một lớp hỗ trợ; phải xác định **nguồn sự thật, điều kiện làm mới, TTL và cách tự sửa lệch** trước khi xem nó là giải pháp chính.

## 4. Chọn chiến lược bổ sung đường truy cập

Không có một phương án duy nhất cho mọi NoSQL. Cần đánh giá loại hệ quản trị, selectivity, cách sắp xếp, tần suất truy vấn, tốc độ cập nhật và yêu cầu nhất quán.

| Phương án | Cách thực hiện | Điểm mạnh | Chi phí hoặc giới hạn |
| --- | --- | --- | --- |
| **Secondary/compound index** | Tạo index trên các trường của đơn | Ít thay đổi mô hình ứng dụng; dữ liệu vẫn nằm cùng collection/table | Chi phí duy trì index, độ chọn lọc, hiệu năng sort, giới hạn engine |
| **Global secondary index (GSI)** | Một key truy cập khác được hệ quản trị duy trì | Hỗ trợ query theo khóa thay thế; ít code đồng bộ thủ công | Dung lượng/ghi bổ sung, độ trễ cập nhật, giới hạn query và projection |
| **Bảng đọc riêng (read model)** | Tạo `ready_orders_by_shop_day` chứa đúng các đơn cần giao | Tối ưu chính xác Q3, chủ động partition và order | Dữ liệu trùng, phải backfill, đồng bộ và sửa lệch |
| **Materialized view do DB quản lý** | Engine duy trì hình chiếu/index tương ứng | Bớt công sức đồng bộ thủ công | Khả năng và giới hạn tùy công nghệ, không mặc nhiên giải mọi query |
| **Search/analytics index** | Đẩy order events sang công cụ tìm kiếm | Hợp với nhiều bộ lọc động, tìm kiếm và tổng hợp | Thêm hệ thống, pipeline, độ trễ đồng bộ và chi phí vận hành |
| **Precomputed cache** | Tạo danh sách/trang đọc sẵn | Trả lời rất nhanh cho query nóng | Làm mới và invalidation khó; thường không phù hợp làm nguồn sự thật |
| **Quét theo lô** | Scan định kỳ rồi tạo báo cáo | Chấp nhận được cho một báo cáo hiếm | Không phù hợp truy vấn tương tác thường xuyên |

### 4.1. Khi nào chỉ thêm index là đủ?

Trong document database như MongoDB, một **partial compound index** có thể là phương án đáng cân nhắc nếu truy vấn lọc trạng thái cố định.

Ví dụ minh họa:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, shopId: 1, createdAt: -1, _id: -1 },
  {
    name: "ready_orders_by_shop_time",
    partialFilterExpression: { status: "READY_TO_SHIP" }
  }
);
~~~

Truy vấn:

~~~javascript
db.orders.find({
  tenantId: "merchant-a",
  shopId: "shop-12",
  status: "READY_TO_SHIP",
  createdAt: { $gte: cutoffDate }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Ở đây `cutoffDate` là một **Date** được ứng dụng tính từ thời điểm yêu cầu. Chỉ mục partial chứa những document thỏa điều kiện `status`; khi trạng thái đổi, index phải được cập nhật.

**Điểm cần kiểm tra:** index có thực sự được query planner chọn không, `sort` có sử dụng thứ tự index hay phải sort thêm, index có đủ điều kiện truy vấn hay không, chi phí write amplification và thời gian xây index khi dữ liệu đã lớn. Dùng `explain` và số đo workload thực, không chỉ nhìn cấu trúc index rồi kết luận.

### 4.2. Khi nào cân nhắc GSI?

Trong DynamoDB, có thể thiết kế một GSI với:

~~~text
GSI partition key = TENANT#merchant-a#SHOP#shop-12#READY#2026-11-14
GSI sort key      = 2026-11-14T09:30:00Z#O900
~~~

Để chỉ đưa đơn cần giao vào GSI, ứng dụng có thể gán các thuộc tính khóa GSI **chỉ khi trạng thái là READY_TO_SHIP**, và gỡ các thuộc tính ấy khi đơn rời trạng thái. Đây là dạng *sparse index* dựa trên việc item có hay không có thuộc tính khóa GSI.

GSI không tự hỗ trợ một query bao trùm tất cả ngày nếu ngày nằm trong partition key; API vẫn cần đọc từng bucket. Hãy kiểm tra cách projection của GSI ảnh hưởng tới số lần đọc bảng chính, giới hạn throughput và việc **đọc GSI có thể chỉ eventual consistent**. Không thể yêu cầu strong consistency trên một GSI theo cách đọc bảng chính.

### 4.3. Khi nào chọn bảng đọc riêng?

Với Cassandra-like wide-column store, đường truy cập thường được chủ động định nghĩa bằng partition và clustering key. Nếu Q3 là API quan trọng, xuất hiện thường xuyên và cần thứ tự ổn định, một **bảng truy vấn riêng** có thể đơn giản hơn quét hoặc dựa vào filtering.

Các mục tiếp theo xây dựng phương án này để làm rõ quy trình thay đổi mô hình dữ liệu.

## 5. Thiết kế bảng mới theo Q3 thay vì theo thực thể

Q3 cần:

~~~text
Tenant = merchant-a
Shop   = shop-12
Status = READY_TO_SHIP
Ngày   = trong 7 ngày gần đây
Sort   = createdAt DESC, orderId ASC
Limit  = 20
~~~

Chọn bảng **chỉ chứa những đơn đang cần giao**. Trạng thái đã được “mã hóa” bằng **việc hàng có hiện diện trong bảng hay không**, nên không cần đưa `status` vào partition key của bảng chuyên dụng.

### 5.1. Chọn partition key

Một lựa chọn ban đầu:

~~~text
(tenantId, shopId, dayBucket)
~~~

Trong đó `dayBucket` lấy từ **`createdAt` theo UTC**, ví dụ `2026-11-14`. Bucket giúp tránh dồn toàn bộ lịch sử một shop vào một partition tăng không giới hạn.

Nếu một cửa hàng nhận lượng đơn lớn đột biến, một partition theo ngày vẫn có thể nóng. Ta thêm thành phần `shardNo`:

~~~text
(tenantId, shopId, dayBucket, shardNo)
~~~

Ví dụ:

~~~text
shardNo = stableHash(orderId) mod 8
~~~

Ứng dụng phải dùng **cùng thuật toán hash, cùng cách mã hóa ID và cùng số shard phù hợp** ở mọi nơi ghi, xóa, đọc và backfill. Nếu tự ý đổi từ 8 sang 16 shard, những bản ghi cũ không tự chuyển vị trí; cần kế hoạch versioning/migration.

### 5.2. Chọn clustering columns

Để trả kết quả mới nhất trước:

~~~text
createdAt DESC
orderId ASC
~~~

`orderId` là thành phần phân biệt và tạo thứ tự ổn định khi hai đơn có cùng `createdAt`. Chỉ dùng `createdAt` làm clustering key có thể khiến hai đơn tạo cùng thời điểm cùng nhắm vào một hàng logic.

### 5.3. CQL cho bảng mới

~~~sql
CREATE TABLE ready_orders_by_shop_day (
    tenant_id text,
    shop_id text,
    day_bucket date,
    shard_no smallint,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_vnd bigint,
    source_version bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, day_bucket, shard_no),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Một hàng trong bảng này chỉ chứa **dữ liệu cần để hiển thị danh sách**. Chi tiết đầy đủ vẫn được đọc từ `orders_by_id` khi mở một đơn.

Ví dụ hàng Q3:

~~~text
partition: (merchant-a, shop-12, 2026-11-14, shard=3)

created_at           order_id   customer_id   total_vnd  source_version
09:30:00Z            O900       U42           1000000    4
08:59:12Z            O871       U33            250000    2
08:10:41Z            O850       U71            600000    5
~~~

Sự hiện diện của `O900` ở đây có nghĩa read model đang xem đơn này là `READY_TO_SHIP`. Cột `source_version` hữu ích để phát hiện bản chiếu cũ, nhưng **tự lưu version trong một hàng không thay thế được quy trình tránh xử lý sự kiện sai thứ tự**.

### 5.4. Thứ tự khóa và việc đọc trong một partition

~~~sql
SELECT created_at, order_id, customer_id, total_vnd
FROM ready_orders_by_shop_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND day_bucket = '2026-11-14'
  AND shard_no = 3
LIMIT 20;
~~~

Truy vấn cung cấp đầy đủ partition key và lấy các hàng theo clustering order. Không có quét toàn bộ tenant hoặc lọc status sau khi đọc mọi đơn.

**Nhưng:** vì `shard_no` là một phần partition key, kết quả trên **chỉ là top-20 của shard 3**, chưa phải top-20 của cả cửa hàng.

## 6. Một đường truy cập mới có thể gồm nhiều partition

Để thực hiện Q3 với 8 shard/ngày, cần đọc các shard thuộc những ngày trong cửa sổ truy vấn.

~~~mermaid
flowchart TD
    A["Q3: shop-12, READY, 7 ngày, top-20"] --> B["Tính các dayBucket UTC"]
    B --> C["Với mỗi ngày, đọc shard 0..7"]
    C --> D["Mỗi shard trả hàng theo createdAt DESC"]
    D --> E["K-way merge theo createdAt DESC, orderId ASC"]
    E --> F["Lọc đúng cutoff và lấy 20 đơn"]
    F --> G["Trả trang và cursor"]
~~~

### 6.1. Vì sao phải merge?

Giả sử hai shard trả về:

~~~text
Shard 0: O901@10:05, O899@09:40, O894@09:00
Shard 1: O902@10:10, O900@09:50, O890@08:55
~~~

Nối danh sách shard 0 rồi shard 1:

~~~text
O901, O899, O894, O902, O900, O890
~~~

**không** đúng thứ tự thời gian toàn cửa hàng.

Merge đúng:

~~~text
O902@10:10
O901@10:05
O900@09:50
O899@09:40
O894@09:00
O890@08:55
~~~

Thuật toán **k-way merge** có thể dùng heap/priority queue. Nếu có `p` danh sách đã sắp xếp và trả `k` kết quả, phần trộn lý tưởng có chi phí tính toán xấp xỉ `O(k log p)` sau khi đã có các đầu danh sách; **thời gian đọc từ database và số bản ghi được tải về** thường mới là chi phí lớn cần đo.

### 6.2. Tìm top-20 theo từng ngày

Vì ngày mới hơn chứa thời gian `createdAt` mới hơn ngày cũ hơn, API có thể xử lý **ngày mới nhất trước**:

1. Tính cutoff chính xác: `now - 7 days`.
2. Tính các `day_bucket` UTC giao với cửa sổ đó.
3. Với ngày mới nhất, đọc các shard và merge thành thứ tự toàn ngày.
4. Nếu chưa đủ 20 đơn, tiếp tục ngày trước đó.
5. Dừng khi có đủ 20 kết quả hoặc hết khoảng.
6. Loại bản ghi nằm ngoài cutoff chính xác ở ngày biên.

**Một khoảng 7 × 24 giờ có thể chạm tới 8 ngày lịch UTC** nếu bắt đầu và kết thúc không đúng ranh giới ngày. Vì vậy không được cố định “luôn đúng 7 partition ngày”.

### 6.3. Giá của fan-out

Nếu query có 8 bucket ngày và mỗi bucket 8 shard, số partition có thể phải xét ở trường hợp rộng là:

\[
8 \times 8 = 64\ \text{partition}
\]

Nếu lấy 20 hàng đầu từ mỗi partition để trộn top-20, một cách triển khai đơn giản có thể tải tối đa:

\[
64 \times 20 = 1280\ \text{hàng ứng viên}
\]

cho một trang, trước khi giảm về 20 hàng. Đây là **giới hạn minh họa cho cách query nạp sẵn 20 hàng/partition**; một thuật toán đọc theo từng ngày và nạp thêm dần có thể giảm số truy vấn hoặc lượng dữ liệu, nhưng phức tạp hơn.

Người thiết kế phải cân bằng:

- **Ít shard:** ít partition cần đọc, nhưng mỗi partition có nguy cơ lớn/nóng.
- **Nhiều shard:** phân tán ghi, nhưng fan-out và merge đắt hơn.
- **Bucket nhỏ:** partition nhỏ hơn, nhưng nhiều bucket/ngày và khó phân trang.
- **Bucket lớn:** ít fan-out, nhưng dữ liệu/partition tăng.

### 6.4. Cursor thay cho offset lớn

Một cursor phân trang có thể chứa:

~~~json
{
  "tenantId": "merchant-a",
  "shopId": "shop-12",
  "status": "READY_TO_SHIP",
  "cutoff": "2026-11-07T10:00:00Z",
  "upperBound": "2026-11-14T10:00:00Z",
  "currentDay": "2026-11-14",
  "lastCreatedAt": "2026-11-14T09:30:00Z",
  "lastOrderId": "O900",
  "shardPositions": {
    "0": "...",
    "1": "...",
    "2": "..."
  }
}
~~~

Đây là **cấu trúc minh họa**, không phải định dạng chung của Cassandra. Với truy vấn đa shard, cursor phải giữ thông tin cần thiết để tiếp tục các dòng đã đọc nhưng chưa trả, và để không bỏ qua một shard còn ứng viên.

Cursor truyền cho client nên được **ký/mã hóa hoặc bảo vệ tính toàn vẹn**, kiểm tra tenant và quyền người gọi, có thời hạn sử dụng và không lộ paging state nội bộ nhạy cảm một cách tùy tiện.

Mốc `upperBound` giúp tránh đưa đơn **mới tạo sau trang đầu** vào một phiên phân trang đang diễn ra. Tuy vậy, nếu các đơn cũ rời `READY_TO_SHIP` hoặc dữ liệu được backfill muộn, nhiều trang không mặc nhiên tạo thành một snapshot bất biến. Nếu API bắt buộc snapshot, cần cơ chế mạnh hơn, không chỉ cursor.

## 7. Xác định rõ thời gian nào quyết định đường truy cập

Q3 quy định:

> “Đơn **được tạo** trong 7 ngày gần đây và **đang** `READY_TO_SHIP`.”

Do đó bảng theo `dayBucket(createdAt)` và thứ tự `createdAt DESC` phù hợp.

Nhưng một yêu cầu khác:

> “Đơn **vừa chuyển sang** `READY_TO_SHIP` trong 7 ngày gần đây, mới chuyển trạng thái nhất trước.”

phải dùng **`readyAt`** hoặc thời gian hiệu lực của chuyển trạng thái làm khóa sắp xếp. Hai truy vấn có thể trả ra **thứ tự hoàn toàn khác**.

Ví dụ:

| Đơn | createdAt | readyAt |
| --- | --- | --- |
| O900 | 12/11 08:00 | 14/11 10:00 |
| O901 | 14/11 09:00 | 14/11 09:05 |

Theo `createdAt DESC`, O901 đứng trước O900. Theo `readyAt DESC`, O900 đứng trước O901.

Đây là lý do phải viết rõ **định nghĩa “mới nhất”** trước khi quyết định clustering key. Thêm một bảng index theo trường thời gian sai có thể rất nhanh nhưng trả đáp án sai.

## 8. Cập nhật trạng thái làm thay đổi bảng đọc như thế nào?

Bảng `orders_by_id` là **nguồn sự thật cho trạng thái hiện tại của đơn**. Bảng `ready_orders_by_shop_day` chỉ là **hình chiếu phục vụ màn hình**.

Giả sử đơn O900 trải qua:

~~~text
version 1: CREATED
version 2: PAID
version 3: READY_TO_SHIP
version 4: SHIPPED
~~~

Các thao tác cần có:

| Chuyển trạng thái | Ở `orders_by_id` | Ở `ready_orders_by_shop_day` |
| --- | --- | --- |
| Tạo CREATED | Tạo đơn | Không thêm hàng |
| CREATED → PAID | Cập nhật source | Không thêm hàng |
| PAID → READY_TO_SHIP | Cập nhật source | **Thêm hàng** vào bucket/shard tương ứng |
| READY_TO_SHIP → SHIPPED | Cập nhật source | **Xóa hàng** khỏi bảng READY |
| READY_TO_SHIP → CANCELLED | Cập nhật source nếu hợp lệ | **Xóa hàng** |
| Sửa metadata cần hiển thị | Cập nhật source | Cập nhật trường chiếu tương ứng |

Với order O900 có `createdAt` và `shardNo` đã xác định, thêm vào bảng:

~~~sql
INSERT INTO ready_orders_by_shop_day (
    tenant_id, shop_id, day_bucket, shard_no,
    created_at, order_id, customer_id,
    total_vnd, source_version
) VALUES (
    'merchant-a', 'shop-12', '2026-11-14', 3,
    '2026-11-14T09:30:00Z', 'O900', 'U42',
    1000000, 3
);
~~~

Khi đơn được giao:

~~~sql
DELETE FROM ready_orders_by_shop_day
WHERE tenant_id = 'merchant-a'
  AND shop_id = 'shop-12'
  AND day_bucket = '2026-11-14'
  AND shard_no = 3
  AND created_at = '2026-11-14T09:30:00Z'
  AND order_id = 'O900';
~~~

Phép xóa cần **đầy đủ primary key** của hàng mục tiêu. Vì vậy event trạng thái hoặc projector phải biết khóa chiếu cũ, không chỉ trạng thái mới. Nếu `shopId` hoặc thời gian dùng để bucket thay đổi, cần xóa biểu diễn cũ rồi ghi biểu diễn mới.

### 8.1. Chi phí của việc xóa thường xuyên

Trong Cassandra, `DELETE` có thể tạo **tombstone**; tombstone chưa được thu hồi ngay. Nếu mọi đơn chỉ ở trạng thái READY trong vài phút, bảng đọc sẽ có nhiều insert/delete. Một query `LIMIT 20` vẫn có thể phải xét dấu xóa để tìm hàng còn sống.

Các lựa chọn cần đánh giá:

- Bảng chỉ chứa đơn READY, chấp nhận churn và quan sát tombstone/compaction.
- Một bảng theo `(shop, status, bucket)` với cơ chế di chuyển giữa trạng thái, vẫn phát sinh xóa ở trạng thái cũ.
- Một index có khả năng quản lý cập nhật trạng thái phù hợp với workload.
- Một hệ tìm kiếm/dịch vụ read model có chiến lược quản lý tài liệu thay đổi.
- Một truy vấn lấy ứng viên theo cửa sổ thời gian rồi kiểm tra trạng thái gốc nếu số lượng nhỏ và SLA cho phép.

**Không nên chọn bảng sparse “chỉ chứa READY” mà bỏ qua tần suất rời trạng thái READY**. Tỷ lệ thay đổi trạng thái và mức tồn tại trong READY quyết định write amplification và hiệu quả truy vấn.

## 9. Một nguồn sự thật, nhiều bản sao phục vụ truy vấn

Thiết kế theo truy vấn thường dẫn tới **denormalization**: cùng `orderId`, `createdAt`, `totalVnd` xuất hiện trong nhiều bảng. Việc lặp này là có chủ đích để giảm chi phí đọc.

Nhưng phải xác định:

1. **Nguồn sự thật:** `orders_by_id` quyết định trạng thái nào là hợp lệ.
2. **Bảng đọc phụ:** Q2/Q3 chỉ giữ dữ liệu giúp trả nhanh, có thể tái tạo từ nguồn sự thật.
3. **Quy tắc đồng bộ:** sự kiện nào thêm, cập nhật hoặc xóa bản chiếu.
4. **Mức nhất quán:** Q3 có được phép trễ vài giây không?
5. **Cơ chế sửa lệch:** chạy lại sự kiện, quét đối soát hoặc xây dựng lại bảng đọc.

Một sơ đồ:

~~~mermaid
flowchart LR
    A["Lệnh nghiệp vụ"] --> B["Orders service"]
    B --> C["orders_by_id<br/>Nguồn sự thật"]
    C --> D["Change stream / Outbox / CDC"]
    D --> E["Projection worker"]
    E --> F["orders_by_customer_month"]
    E --> G["ready_orders_by_shop_day"]
    H["Q1: chi tiết"] --> C
    I["Q2: lịch sử khách"] --> F
    J["Q3: đơn cần giao"] --> G
~~~

**Đây là mô hình kiến trúc khái niệm**, không khẳng định mọi Cassandra deployment có sẵn change stream hay transaction outbox tương đương nhau. Cơ chế lấy thay đổi phải phù hợp sản phẩm và hạ tầng đang dùng.

### 9.1. Tại sao ghi hai bảng độc lập chưa đủ?

Giả sử API làm:

~~~text
1. UPDATE orders_by_id -> status = READY_TO_SHIP
2. INSERT ready_orders_by_shop_day
~~~

Nếu tiến trình chết giữa bước 1 và 2, đơn đã READY ở nguồn nhưng không xuất hiện trên dashboard.

Nếu làm ngược thứ tự:

~~~text
1. INSERT ready_orders_by_shop_day
2. UPDATE orders_by_id -> status = READY_TO_SHIP
~~~

thì có thể tạo hàng READY trong bảng phụ trong khi source vẫn chưa chuyển trạng thái.

Một **batch ghi** không tự tương đương transaction ACID tổng quát trên mọi bảng/partition. Phạm vi nguyên tử, điều kiện ghi và consistency của từng hệ quản trị phải được kiểm tra. Với dữ liệu nghiệp vụ quan trọng, nên thiết kế đường đồng bộ có khả năng **phát lại và tự phục hồi**.

## 10. Dùng sự kiện thay đổi và projector

Khi source cập nhật thành công, hệ thống phát/ghi nhận một sự kiện:

~~~json
{
  "eventId": "evt-order-O900-v3",
  "eventType": "ORDER_STATE_CHANGED",
  "tenantId": "merchant-a",
  "orderId": "O900",
  "version": 3,
  "previousStatus": "PAID",
  "status": "READY_TO_SHIP",
  "shopId": "shop-12",
  "customerId": "U42",
  "createdAt": "2026-11-14T09:30:00Z",
  "totalVnd": 1000000
}
~~~

**Điều kiện quan trọng:** event phải phản ánh một thay đổi **đã commit** ở nguồn sự thật. Nếu gửi event trước khi source ghi thành công, bảng đọc có thể hiển thị trạng thái chưa bao giờ được xác nhận.

### 10.1. Đồng bộ bằng outbox hoặc CDC

Hai hướng thường gặp:

**Transactional outbox**, khi database hỗ trợ ghi bản ghi nghiệp vụ và outbox **trong cùng ranh giới transaction**:

~~~text
TRANSACTION:
    cập nhật Order với điều kiện version/trạng thái hợp lệ
    ghi OutboxEvent(eventId, orderId, version, payload)
COMMIT

Publisher:
    đọc outbox event
    gửi đến broker
    đánh dấu đã phát / ghi checkpoint
~~~

**CDC / change stream:** sử dụng nguồn thay đổi đáng tin cậy từ database hoặc log đã commit, sau đó projector chuyển đổi sự thay đổi thành thao tác trên read model.

Trong cả hai cách:

- Publisher/consumer có thể phát/nhận một event **nhiều lần**.
- Cần định danh sự kiện hoặc phiên bản nguồn để xử lý lặp.
- Cần theo dõi lag và xử lý *dead-letter queue* khi event không thể áp dụng.
- Cần khả năng **replay** để xây lại bảng đọc sau lỗi.

Nếu nguồn NoSQL không hỗ trợ giao dịch cần thiết cho outbox hoặc không có CDC phù hợp, không thể chỉ viết từ khóa “outbox” rồi giả định mọi khoảng lỗi biến mất. Phải chọn kiến trúc tương thích hoặc chấp nhận một quy trình đối soát mạnh hơn.

### 10.2. Projector diễn giải sự kiện

Pseudocode:

~~~text
onOrderChanged(event):
    if event đã được áp dụng an toàn:
        return

    oldProjectionKey = lookupLastProjectedKey(event.orderId)
    newProjectionKey =
        event.status == READY_TO_SHIP
        ? computeKey(event.tenantId, event.shopId,
                     dayBucket(event.createdAt),
                     shard(event.orderId),
                     event.createdAt, event.orderId)
        : none

    if oldProjectionKey exists AND oldProjectionKey != newProjectionKey:
        removeRow(oldProjectionKey)

    if newProjectionKey exists:
        upsertReadyRow(newProjectionKey, event.projectionFields)

    recordProjectionProgress(event.orderId, event.version, newProjectionKey)
~~~

Đây là **ý tưởng thuật toán**, không phải một transaction hoàn chỉnh. Nếu `removeRow`, `upsertReadyRow` và `recordProjectionProgress` nằm trên nhiều partition mà không có giao dịch chung, worker có thể chết giữa các bước. Cần thiết kế tiến độ có thể phục hồi, phát lại an toàn và đối soát để không bỏ sót thao tác.

### 10.3. Sự kiện đến sai thứ tự

Giả sử projector nhận:

~~~text
event version 4: O900 -> SHIPPED
event version 3: O900 -> READY_TO_SHIP (đến muộn)
~~~

Nếu xử lý vô điều kiện, version 3 có thể **thêm lại hàng READY** sau khi version 4 đã xóa, khiến dashboard hiện đơn đã giao.

Các cơ chế cần cân nhắc:

- Có **version đơn hàng tăng đơn điệu** tại source và event mang version đó.
- Định tuyến sự kiện của **cùng orderId** theo một khóa để giữ thứ tự khi broker hỗ trợ.
- Projector ghi tiến độ đã áp dụng cho từng order và từ chối event cũ.
- Khi hàng READY bị xóa, vẫn phải có **dấu vết phiên bản cao nhất** ở nơi phù hợp; nếu không, event cũ có thể tái tạo hàng đã xóa.
- Ghi có điều kiện hoặc xử lý tuần tự theo mỗi order để tránh hai worker cùng đảo thứ tự cập nhật.
- Khi không thể bảo đảm thứ tự, đọc lại trạng thái nguồn và tái dựng bản chiếu hiện tại.

**Lưu `source_version` chỉ trong hàng READY là chưa đủ để ngăn hồi sinh dữ liệu sau xóa**, vì khi hàng bị xóa, version đó cũng không còn ở hàng đang sống. Cần ledger/tombstone phiên bản đủ bền, cơ chế tuần tự hoặc thuật toán reconciliation đúng.

### 10.4. Hậu quả của eventual consistency

Đơn chuyển sang READY tại 10:00:00, nhưng projector hoàn tất lúc 10:00:03. Trong 3 giây, `orders_by_id` và `ready_orders_by_shop_day` có thể khác nhau.

Nếu dashboard chấp nhận độ trễ vài giây, đây có thể là lựa chọn hợp lý. Nhưng **quyết định giao hàng thực tế** không nên chỉ dựa trên một hàng trong bảng đọc phụ đã cũ: API thực thi cần kiểm tra source hoặc sử dụng điều kiện cập nhật trạng thái nguyên tử.

Điều cần công bố trong hợp đồng:

- Bảng đọc cập nhật gần thời gian thực hay ngay lập tức?
- Độ trễ tối đa mục tiêu là bao nhiêu?
- Nếu projector dừng 5 phút, UI xử lý cảnh báo dữ liệu cũ thế nào?
- Khi người dùng vừa đổi trạng thái và mở lại màn hình, ứng dụng có yêu cầu **read-your-writes** không?

Không thể nói “eventual consistency là được” mà không gắn với hậu quả nghiệp vụ.

## 11. Nạp dữ liệu lịch sử (backfill) khi thêm bảng mới

Một lỗi thường gặp là **chỉ cập nhật read model cho đơn phát sinh sau ngày triển khai**. Khi bật Q3, những đơn READY đã tồn tại từ trước sẽ biến mất khỏi dashboard.

Vì vậy phải xây bảng mới bằng dữ liệu lịch sử trước khi chuyển luồng đọc chính thức.

### 11.1. Các bước backfill khái niệm

1. **Chuẩn bị schema** cho `ready_orders_by_shop_day` và xác định retention.
2. **Bắt đầu thu thay đổi mới một cách bền vững** (CDC/outbox/luồng event) từ một mốc có thể replay, trước hoặc đồng bộ với bước snapshot.
3. **Đọc nguồn theo các dải có thể checkpoint**, chỉ lấy đơn liên quan đến cửa sổ cần hiển thị.
4. **Biến đổi từng đơn** thành hàng chiếu nếu trạng thái hiện tại là READY.
5. **Ghi theo batch có giới hạn**, theo dõi throughput, tỷ lệ lỗi và checkpoint.
6. **Phát lại thay đổi trong lúc backfill** theo version/thứ tự hợp lệ.
7. **Đối soát** số hàng và mẫu bản ghi giữa source với read model.
8. Chỉ khi read model **đã đuổi kịp** và đạt tiêu chí đọc mới bật luồng Q3.

~~~mermaid
sequenceDiagram
    participant S as Source Orders
    participant C as Change Log
    participant B as Backfill Worker
    participant P as Read Model
    participant A as API Q3
    S->>C: Ghi nhận thay đổi từ mốc W
    B->>S: Đọc dữ liệu nền theo lô
    B->>P: Ghi các đơn READY
    C->>P: Replay những thay đổi sau W
    Note over P,C: Áp dụng theo version, xử lý lặp và sai thứ tự
    P-->>A: Read model sẵn sàng
    A->>P: Bắt đầu phục vụ Q3
~~~

Sơ đồ giả định nguồn có cơ chế thay đổi và mốc replay đủ tin cậy. Nếu hệ quản trị **không hỗ trợ snapshot nhất quán hoặc change log có vị trí tương ứng**, không thể đơn giản coi một lượt scan và replay là bảo đảm chính xác tuyệt đối. Khi đó cần thiết kế bổ sung việc version-gating, retry và reconciliation định kỳ.

### 11.2. Race condition giữa backfill và cập nhật trực tiếp

Giả sử:

~~~text
10:00  Backfill đọc O900 ở version 3, status=READY_TO_SHIP.
10:01  O900 chuyển version 4, status=SHIPPED.
10:02  Projector xóa O900 khỏi bảng READY.
10:03  Backfill ghi hàng READY từ snapshot cũ của version 3.
~~~

Kết quả sai: O900 xuất hiện trở lại.

Đây là lý do **backfill không được ghi mù quáng đè lên trạng thái mới**. Có thể xử lý bằng một trong các cách:

- Snapshot nhất quán tại mốc W và replay sự kiện sau W theo đúng thứ tự.
- Mỗi projection có version source kèm cơ chế **ngăn phiên bản cũ ghi đè phiên bản mới**, kể cả trạng thái bị xóa.
- Single-writer/serialized processing theo `orderId` cho backfill và thay đổi mới.
- So sánh source mới nhất trước khi ghi và chạy reconciliation sau backfill, nếu độ nhất quán có thể chấp nhận.

Một `INSERT` đơn thuần trên khóa cũ không tự hiểu rằng version 4 đã xóa dữ liệu; phải thiết kế cơ chế xử lý phù hợp.

### 11.3. Backfill có giới hạn tài nguyên

Nếu hệ thống có 100 triệu đơn:

- Không nên quét toàn bộ nguồn bằng một tiến trình không checkpoint.
- Chia theo token range/partition/page hoặc cơ chế scan tương thích với database.
- Giới hạn số request đọc và số mutation ghi mỗi giây để không làm nghẽn traffic production.
- Có retry với backoff khi lỗi tạm thời; ghi lại **mốc đã hoàn thành**.
- Không dùng OFFSET lớn để phân trang toàn bộ tập dữ liệu ở engine không tối ưu dạng truy vấn đó.
- Theo dõi read latency của hệ thống cũ, không chỉ tốc độ backfill.

Nếu Q3 chỉ cần 7 ngày gần nhất, nên xem có thể **chỉ backfill khoảng thời gian phục vụ Q3** hay không. Điều này giảm đáng kể khối lượng so với nạp toàn bộ lịch sử; đồng thời phải xác định cách xử lý những đơn lâu hơn 7 ngày nhưng vẫn ở trạng thái READY nếu sau này yêu cầu nghiệp vụ thay đổi.

## 12. Triển khai đường truy cập mới không gián đoạn

Một thay đổi schema/query thường cần nhiều bước, thay vì bật ngay bảng mới và hy vọng mọi dữ liệu đã có.

### Giai đoạn A — Expand

- Tạo index hoặc bảng mới, không xóa đường đọc cũ.
- Bổ sung khả năng phát event/CDC cho thay đổi order.
- Triển khai projector ở chế độ ghi dữ liệu phụ, chưa cho Q3 phụ thuộc hoàn toàn vào bảng.
- Theo dõi số hàng, lỗi đồng bộ, latency ghi và dung lượng tăng.

### Giai đoạn B — Populate & catch up

- Chạy backfill theo lô.
- Replay event, đo lag.
- Đối soát nguồn và hình chiếu trên những mẫu/bucket.
- Kiểm tra query plan và độ trễ của đường đọc mới theo đúng filter và sort.

### Giai đoạn C — Shadow read

Ở một phần traffic hoặc tập query được phép:

~~~text
API nhận Q3
    -> đọc read model mới
    -> đồng thời hoặc theo mẫu kiểm chứng bằng source/đường chuẩn
    -> ghi khác biệt vào metric/log nội bộ
    -> chưa dùng kết quả mới cho quyết định quan trọng
~~~

Việc so sánh phải xét **độ trễ đồng bộ được phép** và cùng mốc thời gian; nếu source đổi trong khi hai nhánh chạy, chênh lệch nhất thời chưa chắc là lỗi. Không quét toàn bộ source để so sánh trên mọi request production vì có thể gây áp lực lớn. Nên dùng mẫu được kiểm soát, job đối soát hoặc đường chuẩn thích hợp.

### Giai đoạn D — Canary & cutover

- Bật tính năng cho một nhóm tenant/shop nhỏ thông qua feature flag.
- Theo dõi p95/p99, số hàng, tỷ lệ lỗi, projection lag và chênh lệch kết quả.
- Mở rộng traffic theo từng bước khi đạt tiêu chí.
- Giữ khả năng rollback sang chế độ cũ/ẩn tính năng nếu có sự cố.

### Giai đoạn E — Contract

- Chỉ loại bỏ mã đồng bộ/index dư thừa khi biết không còn consumer phụ thuộc.
- Cân nhắc dọn dữ liệu cũ, cập nhật retention và quyền truy cập.
- Ghi rõ trách nhiệm vận hành cho projector và kế hoạch phục hồi.

**Rollback logic không luôn đồng nghĩa rollback schema.** Khi có sự cố, có thể tắt Q3 hoặc cho UI hiển thị thông báo dữ liệu chưa sẵn sàng, trong khi vẫn giữ bảng/index mới để điều tra và sửa. Xóa ngay schema mới có thể làm mất khả năng đối soát.

## 13. Thêm đường đọc là thêm chi phí ghi và lưu trữ

### 13.1. Một ví dụ tính dung lượng

Giả sử một shop tạo **200.000 đơn/ngày**. Tại thời điểm quan sát, trung bình có khoảng **25% số đơn của một ngày** đang ở trạng thái READY. Nếu một hàng read model chứa khoảng **600 byte dữ liệu logic**:

~~~text
Số đơn READY trong một nhóm 200.000 đơn = 200.000 × 25%
                                         = 50.000 hàng

Dung lượng dữ liệu logic = 50.000 × 600 byte
                         = 30.000.000 byte
                         ≈ 28,61 MiB
~~~

Đây chỉ là **ước lượng snapshot của một nhóm đơn**, không phải chi phí dung lượng vật lý của Cassandra. Chưa tính overhead cột/khóa, SSTable, compaction, tombstone, replica, index phụ, event log hoặc backup.

Nếu dùng 8 shard và phân bố tương đối đều:

~~~text
50.000 / 8 ≈ 6.250 hàng/shard
30.000.000 / 8 = 3.750.000 byte/shard
                 ≈ 3,58 MiB/shard
~~~

Các con số giúp hình dung kích thước, nhưng **thời gian lưu đơn ở READY và tần suất chuyển trạng thái** cũng quyết định tổng write load. Một order đi vào rồi rời READY có thể phát sinh **một ghi thêm và một xóa** trong bảng chiếu, ngoài ghi source và event/metadata.

### 13.2. Read amplification và write amplification

| Lựa chọn | Chi phí đọc Q3 | Chi phí ghi khi đơn đổi trạng thái |
| --- | --- | --- |
| Quét source | Cao, phụ thuộc số đơn phải xem xét | Không cần read model mới |
| Bảng READY không shard | Ít partition, đọc đơn giản | Insert/delete bảng phụ, có thể hot partition |
| Bảng READY chia 8 shard | Fan-out và merge nhiều hơn | Phân tán write, vẫn insert/delete |
| Compound/partial index | Có thể đọc trực tiếp qua index | Engine phải cập nhật index theo thay đổi status |
| Search engine riêng | Có thể lọc/sort linh hoạt | Đồng bộ dữ liệu qua pipeline, thêm hệ vận hành |
| Cache kết quả Q3 | Đọc cực nhanh khi cache đúng và còn mới | Invalidation/refresh, nguy cơ dữ liệu cũ |

Nếu Q3 chỉ được gọi 10 lần/ngày, một cấu trúc phức tạp với CDC và nhiều shard có thể không đáng giá. Nếu Q3 đạt hàng nghìn QPS ở giờ cao điểm, khoản đầu tư vào read model có thể hợp lý.

### 13.3. Công thức đánh giá ở mức tương đối

Một mô hình gần đúng:

\[
\text{Tổng chi phí}
= \text{Read workload cost}
+ \text{Write amplification cost}
+ \text{Storage \& replication}
+ \text{Build/backfill}
+ \text{Operations \& recovery}
\]

Không nhất thiết quy đổi tất cả sang tiền ở bước đầu. Chỉ cần liệt kê các nguồn chi phí, đo trên workload và nhận ra rằng **thêm đường đọc nhanh hơn thường làm tăng một dạng chi phí khác**.

## 14. Đừng bỏ qua an toàn dữ liệu và phân quyền

Trong hệ đa tenant, đường truy cập mới phải kế thừa đúng quy tắc bảo mật cũ.

Ví dụ:

- `tenantId` phải được lấy từ danh tính/xác thực hoặc ràng buộc với danh tính đó.
- `shopId` phải được kiểm tra người gọi có quyền quản lý cửa hàng tương ứng.
- Partition key/index phải tránh trộn dữ liệu giữa các tenant.
- Cursor phải bị ràng buộc với tenant, shop, filter và quyền đã được kiểm tra.
- Nếu log event hoặc projection chứa địa chỉ, số điện thoại hay thông tin nhạy cảm, cần quyền truy cập và retention tương ứng.
- Bảng phụ chỉ nên chứa **các trường thật sự cần cho Q3**, giảm bề mặt lộ dữ liệu.

Một điều rất dễ sai là API mới đọc thẳng bảng `ready_orders_by_shop_day` theo `shopId` nhưng quên kiểm tra shop thuộc tenant của người gọi. Chỉ mục có thể lọc đúng dữ liệu theo khóa được cung cấp, nhưng **khóa do client gửi không phải bằng chứng quyền truy cập**.

Nếu source xóa hoặc hạn chế truy cập một đơn, phải có cách xóa/ẩn nó trong read model và trong cache. Mục tiêu “dashboard nhanh” không được vượt trên quy tắc bảo vệ dữ liệu.

## 15. Khi yêu cầu thay đổi lần thứ hai

Sau Q3, quản lý muốn thêm:

> **Q4:** “Những đơn READY_TO_SHIP có tổng tiền trên 2.000.000 VND, theo mức giá trị giảm dần.”

Bảng `ready_orders_by_shop_day` hiện được sắp theo `createdAt`, **không theo `totalVnd`**. Không thể tự động coi `ORDER BY total_vnd DESC` là truy vấn rẻ trên bảng wide-column này.

Các lựa chọn:

1. **Nếu tập READY của một shop nhỏ:** đọc một cửa sổ có giới hạn rồi lọc/sort tại API, nhưng phải kiểm tra tính đầy đủ và giới hạn dữ liệu.
2. **Nếu Q4 thường xuyên:** tạo một read model khác theo `shopId`, bucket/nhóm phù hợp và `totalVnd` làm clustering column, chú ý cập nhật tổng tiền.
3. **Nếu có nhiều điều kiện tùy biến:** cân nhắc hệ tìm kiếm/index hỗ trợ filter + sort linh hoạt.
4. **Nếu Q4 chỉ phục vụ báo cáo theo lô:** dùng hệ analytics thay vì tối ưu API thời gian thực.

Khi một sản phẩm liên tục thêm các kiểu lọc và sort tự do, việc tạo **một bảng denormalized cho mỗi tổ hợp** có thể trở nên khó vận hành. Query-driven design không phải lời khuyên tạo vô hạn bảng; đó là cách tìm ra **mức đầu tư phù hợp cho những truy vấn đủ quan trọng**.

### 15.1. Nhóm truy vấn thành các họ (*query families*)

Thay vì một bảng cho từng biến thể nhỏ, hãy nhóm theo mẫu:

| Query family | Ví dụ | Cấu trúc có thể dùng chung |
| --- | --- | --- |
| Lấy chi tiết theo ID | Đơn O900, O901 | `orders_by_id` |
| Lịch sử theo khách và thời gian | 10/20/50 đơn gần nhất | `orders_by_customer_month` |
| Danh sách tác vụ vận hành theo shop và ngày | READY mới nhất, theo dõi trạng thái | Read model theo shop/status/time phù hợp |
| Tìm kiếm linh hoạt | Theo giá, tên, khu vực, ghi chú | Search index/document query/index phù hợp |
| Thống kê | Doanh thu theo ngày, tỷ lệ giao trễ | Aggregate/table OLAP phù hợp |

Quyết định nên dựa trên **các bộ lọc bắt buộc, thứ tự, giới hạn, độ mới và QPS** của cả họ truy vấn.

## 16. Đo lường và vận hành đường truy cập mới

Ngay cả khi code mới trả đúng 20 đơn trong môi trường nhỏ, vẫn cần đo các tín hiệu vận hành khi dữ liệu tăng và liên tục đổi trạng thái.

| Metric | Câu hỏi cần trả lời |
| --- | --- |
| Q3 p50/p95/p99 latency | Người dùng có nhìn thấy dashboard đúng SLA? |
| Partitions/query | Một request phải chạm bao nhiêu bucket và shard? |
| Rows fetched/returned | Có đọc hàng trăm/nghìn ứng viên để trả 20 hàng không? |
| Projection lag | Sự kiện mới mất bao lâu để xuất hiện trong read model? |
| Projection error/retry count | Worker có đang kẹt hoặc liên tục xử lý lại không? |
| Missing/stale row count | Bảng phụ có thiếu đơn READY hoặc chứa đơn đã SHIPPED không? |
| Tombstones scanned | Các lần xóa khi đổi trạng thái có làm query chậm? |
| Hot partition/tenant | Cửa hàng lớn có làm mất cân bằng tải? |
| Extra write throughput | Một thay đổi order phát sinh bao nhiêu mutation phụ? |
| Storage + replication | Read model tốn bao nhiêu dung lượng vật lý? |
| Backfill progress | Có đang hoàn tất theo đúng phạm vi, không gây quá tải source? |
| Authorization violations | Có trường hợp query trả dữ liệu ngoài phạm vi được cấp quyền không? |

### 16.1. Định nghĩa rõ tính đầy đủ của kết quả

Với cùng một mốc thời gian `T`, tập đúng cho Q3 là:

~~~text
Eligible(T) =
    các order có
      tenantId = merchant-a
      shopId   = shop-12
      status(T) = READY_TO_SHIP
      createdAt trong [T - 7 days, T]
~~~

Top-20 đúng là 20 phần tử đầu của `Eligible(T)` theo `createdAt DESC, orderId ASC`.

Đây là một **định nghĩa kiểm chứng** chứ không phải lệnh SQL/CQL. Nếu read model có lag `L`, việc so sánh kết quả tại thời điểm `T` phải có quy tắc xử lý khác biệt trong khoảng `L` hoặc dùng snapshot logic phù hợp.

### 16.2. Không chỉ kiểm tra số lượng

Giả sử read model có đúng 20 hàng nhưng một hàng là đơn đã SHIPPED, còn một đơn READY mới hơn bị thiếu. **Số lượng vẫn đúng nhưng kết quả sai.**

Đối soát nên xét:

- Tập ID đúng hay sai.
- Có bản ghi không thuộc tenant/shop không.
- Status từ source tại mốc phù hợp.
- Thứ tự và tie-breaker.
- Có bản ghi trùng khi merge từ nhiều shard hay không.
- Cursor có bỏ sót/trùng ở các trang khi dữ liệu thay đổi không.

Khi cần quyết định vận hành có tác động thật (giao hàng, trừ tiền), xác minh trạng thái nguồn trước khi thực hiện, kể cả dashboard đã hiển thị đơn đó.

## 17. Một quy trình ra quyết định có thể áp dụng lại

Khi nhận yêu cầu mới, đừng sửa schema ngay. Có thể đi theo trình tự:

### Bước 1 — Viết query contract

Ghi rõ:

~~~yaml
queryName: readyOrdersByShop
inputs:
  - authenticatedTenantId
  - authorizedShopId
  - cutoffTime
filters:
  status: READY_TO_SHIP
  createdAt: ">= now - 7 days"
sort:
  - createdAt: DESC
  - orderId: ASC
pageSize: 20
latencyTarget: "p95 <= 150 ms (mục tiêu minh họa)"
freshnessTarget: "phải được nghiệp vụ chấp nhận rõ"
~~~

Đây là đặc tả minh họa. Không để các cụm mơ hồ như “mới nhất”, “gần đây”, “nhanh”, “cập nhật liền” không có định nghĩa.

### Bước 2 — So với đường đọc hiện có

Với mỗi bảng/index, hỏi:

- Query có biết đủ khóa định vị không?
- Có thể lọc bằng index/key, hay phải quét hàng?
- Sắp xếp có được đảm bảo **trước** khi giới hạn kết quả không?
- Cần bao nhiêu partition, round trip và hàng trung gian?
- Kích thước partition/cửa sổ có tăng không giới hạn không?

### Bước 3 — Chọn phương án ít phức tạp nhất đáp ứng yêu cầu

Một index ghép đủ tốt thì không cần triển khai cả pipeline CDC mới. Nhưng nếu engine không hỗ trợ query mới một cách hiệu quả, một read model riêng có thể đáng giá.

### Bước 4 — Thiết kế đường ghi song song với đường đọc

Mọi bản chiếu mới phải trả lời: khi **insert/update/delete/status change** của source xảy ra, dữ liệu phụ thay đổi thế nào? Nếu không trả lời được, đường đọc mới chỉ đúng trong dữ liệu tĩnh.

### Bước 5 — Lập kế hoạch backfill và chuyển đổi

Chuẩn bị schema, snapshot/change log, replay, đối soát, shadow, canary, feature flag và rollback. Không dùng cách tạo bảng hôm nay rồi chấp nhận mất toàn bộ dữ liệu cũ.

### Bước 6 — Đo dưới tải và điều chỉnh

Đánh giá read latency, write amplification, kích thước partition, cache, tombstone, lag và chi phí vận hành với phân bố tenant/shop thực tế.

~~~mermaid
flowchart TD
    A["Có yêu cầu truy vấn mới"] --> B["Viết filter, sort, limit, SLA, freshness"]
    B --> C{"Đường truy cập hiện tại đáp ứng?"}
    C -->|Có| D["Giữ cấu trúc, đo và tối ưu query"]
    C -->|Không| E{"Index phù hợp với workload?"}
    E -->|Có| F["Thêm index và kiểm tra build/read/write cost"]
    E -->|Không| G["Thiết kế read model / search path mới"]
    F --> H["Backfill/catch-up nếu cần"]
    G --> H
    H --> I["Đồng bộ insert/update/delete + đối soát"]
    I --> J["Shadow read -> Canary -> Cutover"]
    D --> K["Theo dõi chất lượng và tải"]
    J --> K
~~~

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tiếp cận tốt hơn |
| --- | --- | --- |
| Chọn partition key theo tên thực thể thay vì query | Query mới không định vị được dữ liệu | Bắt đầu từ filter/sort/limit thực tế |
| Thêm `ALLOW FILTERING` vào mọi câu truy vấn Cassandra | Quét nhiều hàng, latency khó dự đoán | Thiết kế index/read model đúng khóa |
| Chỉ cập nhật bảng mới cho đơn phát sinh sau khi deploy | Mất dữ liệu lịch sử | Backfill và replay change stream |
| Backfill ghi đè event mới | Hồi sinh trạng thái cũ | Snapshot/mốc replay và version/ordering |
| Ghi hai bảng rồi coi như giao dịch nguyên tử | Dữ liệu phụ có thể thiếu hoặc thừa | Đồng bộ bền vững, retry và reconciliation |
| Đưa `status` vào read model nhưng không xử lý rời trạng thái | Dashboard hiển thị đơn đã hoàn tất | Xóa/cập nhật projection đúng lúc và theo version |
| Chia quá nhiều shard để tránh nóng | Fan-out đọc lớn, merge phức tạp | Tính trade-off partition size và query fan-out |
| Chỉ dùng TTL để “tự sửa mọi dữ liệu cũ” | Dữ liệu sai có thể tồn tại quá lâu; có thể mất dữ liệu còn cần | Cơ chế sửa lệch rõ ràng, TTL chỉ là phần retention |
| Chỉ nhìn p50 latency | Truy vấn của tenant lớn hoặc ngày cao điểm bị chậm | Theo dõi p95/p99 và phân bố theo tenant |
| Thêm index/read model cho mọi bộ lọc tưởng tượng | Write cost, dung lượng, vận hành tăng mạnh | Phân nhóm query families theo ưu tiên |
| Bỏ qua quyền truy cập ở API mới | Rò rỉ dữ liệu giữa tenant/shop | Ràng buộc auth và kiểm tra quyền trước query |
| Cho phép Q3 quyết định giao hàng trực tiếp từ dữ liệu eventual | Thao tác trên đơn không còn READY | Kiểm tra nguồn sự thật bằng cập nhật có điều kiện |

## 19. Bài tập thực hành tư duy thiết kế

### Bài 1 — Mở rộng truy vấn đơn hàng

Từ `orders_by_id` và `orders_by_customer_month`, sản phẩm bổ sung:

> “Quản lý shop cần xem 50 đơn `CANCELLED` mới nhất trong 30 ngày, sắp xếp theo **thời điểm hủy**.”

Hãy xác định:

1. Khóa đầu vào nào có sẵn?
2. Thời gian dùng để bucket/order là `createdAt` hay `cancelledAt`?
3. Chọn index trên source hay bảng read model riêng? Vì sao?
4. Khi trạng thái hủy bị đảo ngược theo quy tắc nghiệp vụ, read model phải thay đổi thế nào?
5. Phân trang 30 ngày nếu dữ liệu chia nhiều shard cần lưu gì trong cursor?

### Bài 2 — Tính toán fan-out

Một tenant có 200 cửa hàng. Mỗi shop dùng 16 shard/ngày, Q3 cần đọc khoảng 7 ngày lịch.

- Nếu một query phải đọc đủ 7 ngày và mọi shard, số partition có thể chạm tới là bao nhiêu?
- Với 20 kết quả mỗi partition, tối đa có bao nhiêu hàng ứng viên theo cách prefetch đơn giản?
- Đề xuất cách giảm query fan-out hoặc chỉ đọc ngày cũ khi thật cần.
- Nếu mỗi shop thường chỉ có 3 đơn READY/ngày, dùng 16 shard có thể là lựa chọn hợp lý không?

### Bài 3 — Xử lý dữ liệu cũ khi backfill

Tạo timeline:

~~~text
t0: Backfill thấy O900 version 3 = READY_TO_SHIP
t1: Event version 4 = SHIPPED
t2: Projector đã xóa hàng READY
t3: Backfill ghi bản cũ READY
~~~

Hãy giải thích vì sao xuất hiện dữ liệu sai và đề xuất một thiết kế có thứ tự/version đủ bền để tránh hồi sinh O900. Nếu không thể bảo đảm transaction giữa source và read model, mô tả cơ chế phát hiện và sửa lệch.

### Bài 4 — Chọn giữa index và search engine

Ứng dụng muốn tìm đơn theo tổ hợp tùy chọn: `status`, khoảng tổng tiền, khu vực giao hàng, người nhận và tìm kiếm văn bản ghi chú.

Hãy thảo luận khi nào một vài compound index đủ đáp ứng, khi nào tạo nhiều bảng theo truy vấn trở nên quá đắt, và khi nào một search index riêng có thể hợp lý hơn. Nêu thêm chi phí đồng bộ và cách kiểm soát dữ liệu nhạy cảm.

### Bài 5 — Thiết kế kế hoạch triển khai

Giả sử hệ thống có 50 triệu order, ghi mới 10.000 order/phút, Q3 phải hoạt động trước cuối tháng mà không dừng API hiện tại.

Hãy lập kế hoạch: expand schema, bật change capture, backfill theo khoảng được yêu cầu, checkpoint, replay, kiểm tra độ trễ/khác biệt, canary và rollback. Nêu các chỉ số cho phép quyết định có nên mở rộng traffic hay chưa.

## Kết luận

Trong NoSQL, **yêu cầu nghiệp vụ mới thường kéo theo nhu cầu truy cập dữ liệu theo một khóa, bộ lọc hoặc thứ tự mới**. Cách xử lý tốt không phải mặc định quét toàn bộ dữ liệu, và cũng không phải tạo vô hạn bảng/index.

Một quy trình thiết kế bền vững cần:

- Chuyển yêu cầu nghiệp vụ thành **hợp đồng truy vấn cụ thể**: đầu vào, bộ lọc, sort, phân trang, độ trễ và độ mới.
- Xác định **đường đọc hiện tại thiếu gì**, rồi lựa chọn index, bảng đọc riêng, search hoặc cách xử lý theo lô phù hợp.
- Nếu tạo read model, thiết kế **partition, clustering, bucket và shard** theo workload thực tế.
- Xem **insert/update/delete và chuyển trạng thái** là một phần bắt buộc của thiết kế, không chỉ xét dữ liệu tĩnh.
- Có kế hoạch **backfill, đồng bộ thay đổi, chống xử lý sai thứ tự, đối soát và rollout an toàn**.
- Đánh giá **chi phí đọc, ghi, lưu trữ, tính nhất quán, vận hành và phân quyền** cùng nhau.

Một đường truy cập mới chỉ thực sự hoàn thành khi nó **trả đúng kết quả của yêu cầu mới trên cả dữ liệu cũ lẫn dữ liệu đang thay đổi**, đạt mức hiệu năng cần thiết và có thể được vận hành, khôi phục một cách tin cậy.
