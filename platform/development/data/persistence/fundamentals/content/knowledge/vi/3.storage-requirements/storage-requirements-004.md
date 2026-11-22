# Phân biệt tải xử lý giao dịch với tải phân tích

Trong chương **Yêu cầu lưu trữ** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, một quyết định quan trọng là xác định hệ thống đang phải phục vụ **tải xử lý giao dịch (OLTP)**, **tải phân tích (OLAP)** hay cả hai. Điều này ảnh hưởng trực tiếp đến mô hình dữ liệu, lược đồ, chỉ mục, truy vấn, giao dịch, mức cô lập, kiểm soát đồng thời, ranh giới persistence trong Java và cách tối ưu hiệu năng. Nó cũng quyết định cách xử lý lỗi kết nối, tiến hóa schema, bảo mật và sao lưu.

Hai tải này đều đọc và ghi dữ liệu, nhưng mục đích sử dụng khác nhau: **OLTP giúp công việc nghiệp vụ diễn ra đúng và nhanh ở từng thao tác**; **OLAP giúp đặt câu hỏi trên lượng dữ liệu lớn để rút ra xu hướng, chỉ số và quyết định**. Không nên chọn hệ quản trị hay cấu trúc bảng chỉ từ nhãn “SQL”, “NoSQL”, “real time” hoặc “Big Data”; cần làm rõ từng dạng tải.

Sau bài học, người học có thể:

- Phân biệt OLTP và OLAP dựa vào dạng truy vấn, số dòng xử lý, tần suất, độ trễ, tính nhất quán và mức đồng thời.
- Giải thích vì sao giao dịch ngắn và truy vấn tổng hợp dài có thể tranh chấp tài nguyên.
- Đề xuất lược đồ, chỉ mục, định dạng lưu trữ, đường đọc/ghi và pipeline thích hợp cho từng tải.
- Thiết kế ranh giới Java khi dữ liệu giao dịch và dữ liệu báo cáo được lưu riêng; nhận diện độ trễ đồng bộ, lỗi lặp và yêu cầu bảo mật, sao lưu.
- Đưa ra yêu cầu có thể đo được thay vì nhận xét chung như “hệ thống phải nhanh”.

## 1. Hai dạng tải từ một ví dụ bán hàng

Một nền tảng bán hàng có hai yêu cầu cùng sử dụng thông tin đơn hàng:

1. Khi khách nhấn **Đặt hàng**, hệ thống kiểm tra tồn kho, tạo đơn, ghi nhận số tiền và xác nhận kết quả. Thao tác phải bảo vệ bất biến nghiệp vụ ngay khi nhiều người đặt đồng thời. Đây là tải **OLTP**.
2. Mỗi sáng, nhân viên muốn biết **doanh thu theo ngày, kênh bán, khu vực, dòng sản phẩm trong 12 tháng**, so sánh với cùng kỳ và phân tích nhóm khách hàng. Truy vấn đọc nhiều dòng, kết hợp và tổng hợp dữ liệu lịch sử. Đây là tải **OLAP**.

Một hệ thống có thể vừa ghi đơn hàng vừa làm báo cáo. Vấn đề không nằm ở việc dữ liệu “đơn hàng” thuộc OLTP hay OLAP: **cùng một sự kiện nghiệp vụ có thể được lưu thành các mô hình khác nhau để phục vụ hai loại truy vấn**. Chẳng hạn bản ghi đơn hàng phục vụ giao dịch trong hệ thống nguồn, còn sự kiện thanh toán trở thành một dòng dữ kiện (fact) trong kho phân tích.

### 1.1. Bảng so sánh thực dụng

| Tiêu chí | OLTP — Online Transaction Processing | OLAP — Online Analytical Processing |
| --- | --- | --- |
| Câu hỏi chính | “Đơn này có được tạo?”, “Còn đủ hàng?”, “Thanh toán đã ghi nhận?” | “Tổng doanh thu theo tháng?”, “Nhóm nào tăng trưởng?”, “Tỷ lệ giữ chân theo quý?” |
| Đơn vị công việc | Giao dịch hoặc thao tác nhỏ trên vài hàng đến tập hàng có giới hạn | Truy vấn quét, ghép nhóm, tổng hợp hoặc phân tích nhiều hàng |
| Tính chất đọc/ghi | Đọc/ghi thường xuyên, tần suất cao, cùng tác động lên trạng thái hiện tại | Đọc và tính toán chiếm ưu thế; dữ liệu thường được nạp theo lô hoặc luồng |
| Dạng truy vấn | Tìm theo khóa; truy vấn điều kiện chọn lọc; INSERT/UPDATE/DELETE | Scan tập dữ liệu lớn, JOIN, GROUP BY, window function, phép tổng hợp |
| Độ trễ ưu tiên | Thấp ở từng yêu cầu, chú trọng p95/p99 khi nhiều thao tác đồng thời | Thời gian hoàn tất truy vấn và throughput của nhiều truy vấn; có thể từ giây đến phút tùy yêu cầu |
| Tính đúng đắn | ACID, ràng buộc, giao dịch và bảo vệ bất biến tại nơi ghi | Định nghĩa chỉ số, tính đầy đủ, chính xác của phép biến đổi và mốc dữ liệu |
| Mức độ mới | Nhiều thao tác cần đọc trạng thái vừa commit | Có thể chấp nhận trễ phút/giờ; báo cáo thời gian gần thực cần thiết kế riêng |
| Mô hình thường dùng | Bảng theo thực thể, chuẩn hóa hợp lý, khóa chính/ngoại, chỉ mục chọn lọc | Fact/dimension, bảng tổng hợp, dữ liệu cột hoặc mô hình chuyên dụng |
| Mẫu mở rộng | Giao dịch ngắn, quản lý contention, connection pool, index, partition phù hợp | Đọc song song, xử lý theo lô, partition/pruning, lưu trữ cột, pre-aggregation |
| Ví dụ công nghệ | PostgreSQL/MySQL/SQL Server và hệ giao dịch phù hợp | Warehouse, hệ phân tích cột, data lake/lakehouse, engine phân tích |

Đây là **đặc điểm thường gặp**, không phải ranh giới tuyệt đối. OLAP có thể cần ghi và giao dịch; OLTP có thể chạy thống kê nhỏ. Một database quan hệ có thể phục vụ cả hai khi quy mô và yêu cầu phù hợp. Điều quan trọng là **mẫu truy cập và cam kết của từng workload**.

## 2. Nhận diện tải qua truy vấn và lượng dữ liệu chạm đến

### 2.1. OLTP: cập nhật cục bộ có ràng buộc

Giả sử Inventory sở hữu số lượng hàng còn khả dụng. Khi nhận yêu cầu giữ `quantity` đơn vị hàng, lệnh SQL có thể được viết theo hướng **kiểm tra và ghi nguyên tử**:

~~~sql
-- Ví dụ PostgreSQL; tham số phải được bind từ tầng ứng dụng.
UPDATE inventory_stock
SET available = available - :quantity,
    version = version + 1
WHERE sku = :sku
  AND available >= :quantity
RETURNING available, version;
~~~

Trước khi gọi, ứng dụng phải kiểm tra `quantity > 0`; bảng cần ràng buộc `available >= 0` và khóa duy nhất theo `sku`. Nếu không có hàng trả về, SKU không tồn tại hoặc tồn kho không đủ. Không nên tách thành “SELECT số lượng, kiểm tra ở Java, rồi UPDATE không điều kiện” vì hai yêu cầu cạnh tranh có thể cùng nhìn thấy số lượng cũ.

Khi tạo phiếu giữ hàng và ghi outbox, các lệnh liên quan phải được thực hiện **trong cùng giao dịch cục bộ**. Cần `request_id` duy nhất và chính sách idempotency để tránh giữ hàng hai lần sau retry hoặc khi client mất phản hồi. Thời gian phản hồi của tác vụ này ảnh hưởng trực tiếp tới trải nghiệm đặt hàng.

### 2.2. OLAP: đọc rộng và tính toán theo chiều phân tích

Ví dụ một bảng dữ kiện `fact_payment` lưu từng giao dịch thanh toán đã xác nhận, gồm `paid_at`, `channel`, `currency`, `gross_amount_minor` và định danh sự kiện duy nhất. Câu truy vấn sau tìm giá trị giao dịch đã thanh toán theo ngày UTC, kênh và tiền tệ:

~~~sql
-- Ví dụ PostgreSQL; :from_time và :to_time là tham số.
SELECT date_trunc('day', paid_at AT TIME ZONE 'UTC') AS day_utc,
       channel,
       currency,
       COUNT(*) AS payment_count,
       SUM(gross_amount_minor) AS gross_minor
FROM fact_payment
WHERE paid_at >= :from_time
  AND paid_at < :to_time
GROUP BY 1, channel, currency
ORDER BY 1, channel, currency;
~~~

Truy vấn này có thể phải duyệt hàng triệu khoản thanh toán, phân nhóm và tính tổng. Việc **lọc theo khoảng nửa mở** (`>= from`, `< to`) giúp tránh chồng lặp khi chia cửa sổ thời gian. Nhóm theo `currency` ngăn cộng lẫn các đơn vị tiền tệ. `gross_minor` là tổng số tiền giao dịch danh nghĩa theo đơn vị nhỏ nhất; **không mặc nhiên là doanh thu thuần hoặc lợi nhuận**, vì còn hoàn tiền, phí, thuế, hủy giao dịch và chính sách ghi nhận doanh thu.

Nếu nhiều truy vấn phân tích lặp đi lặp lại, có thể tiền tổng hợp theo ngày/kênh hoặc lưu dữ liệu ở hệ tối ưu scan cột. Tuy vậy, bảng tổng hợp phải có quy tắc cập nhật khi có hoàn tiền, dữ liệu đến muộn và sửa sai. Không thể chỉ chạy `GROUP BY` một lần rồi mặc định kết quả sẽ luôn đúng.

### 2.3. Tại sao cùng là `SELECT` mà chi phí khác nhau?

Chi phí phụ thuộc vào **số hàng và byte cần đọc, cách lọc, số phép JOIN, độ rộng hàng, số nhóm, phép sắp xếp, bộ nhớ trung gian và mức song song**. Câu `SELECT * FROM orders WHERE id = ?` với khóa chính có thể chỉ chạm rất ít trang dữ liệu. Trong khi `SELECT SUM(total) ... GROUP BY region` có thể cần đi qua phần lớn lịch sử.

Chỉ mục B-tree giúp nhiều truy vấn điểm và khoảng chọn lọc; nhưng khi cần đọc phần lớn bảng, scan tuần tự hoặc lưu trữ cột có thể hiệu quả hơn. “Có index là nhanh” không đúng cho mọi truy vấn phân tích. Luôn xem **execution plan**, lượng dữ liệu thực sự quét, bộ nhớ, I/O và kết quả đo đạc.

## 3. Xung đột tài nguyên khi cho hai tải chạy chung

Một dashboard tưởng chỉ đọc dữ liệu vẫn có thể làm chậm giao dịch:

- Truy vấn tổng hợp quét nhiều trang, cạnh tranh CPU, I/O và băng thông bộ nhớ với các thao tác ngắn.
- JOIN/GROUP BY lớn tiêu thụ RAM, tạo dữ liệu tạm và gây đổ ra đĩa khi thiếu bộ nhớ.
- Nhiều kết nối báo cáo chiếm slot pool hoặc connection limit, khiến request giao dịch phải chờ.
- Truy vấn kéo dài có thể giữ snapshot/transaction, gây áp lực lên MVCC và quá trình dọn phiên bản cũ; ở một số hệ quản trị và mức cô lập còn phát sinh tranh chấp khóa.
- Tác vụ ETL chạy `UPDATE` hoặc `DELETE` hàng loạt trên bảng giao dịch có thể tạo WAL, tăng replication lag, làm nặng backup và ảnh hưởng tới checkpoint.

Không nên khẳng định mọi truy vấn đọc dài đều khóa các hàng ghi: **hành vi cụ thể phụ thuộc hệ quản trị, isolation level, MVCC và loại câu lệnh**. Tuy nhiên, ngay cả khi không có khóa ghi trực tiếp, cạnh tranh tài nguyên vẫn đủ khiến p99 của API tăng đáng kể.

Ví dụ: hệ thống đang đạt p95 đặt hàng 180 ms nhưng chạy báo cáo toàn bảng khiến p95 tăng lên 1,5 giây. Việc thêm cache ở API không xử lý triệt để nếu nghẽn xảy ra ở I/O hay CPU của database giao dịch. Cần đánh giá tách tài nguyên, giới hạn truy vấn, index, mô hình dữ liệu và lịch nạp.

## 4. Mô hình dữ liệu theo mục đích sử dụng

### 4.1. Mô hình giao dịch: rõ ràng bất biến và quyền sở hữu

Ví dụ đơn giản về các bảng giao dịch:

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE sales_order_item (
    order_id BIGINT NOT NULL REFERENCES sales_order(order_id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor >= 0),
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

CREATE INDEX idx_sales_order_customer_created
    ON sales_order (customer_id, created_at DESC);
~~~

Đây là lược đồ **minh họa**, chưa đầy đủ các yêu cầu nghiệp vụ về thuế, vận chuyển hay thanh toán. Cấu trúc theo thực thể giúp cập nhật một đơn và các dòng của đơn trong ranh giới giao dịch. Khóa chính, khóa ngoại, `CHECK` và `version` bảo vệ những ràng buộc cần thiết.

Các chỉ mục nên xuất phát từ đường truy vấn thật: tra đơn theo `order_id`, liệt kê đơn của một khách theo thời gian, hoặc kiểm tra SKU. Thêm quá nhiều chỉ mục làm tăng chi phí cho mỗi lần INSERT/UPDATE, dung lượng lưu trữ và thời gian bảo trì. Chuẩn hóa cũng không phải mục đích tự thân: đôi khi một snapshot của giá đã chốt trong dòng đơn là chính xác hơn việc luôn JOIN sang bảng giá hiện tại.

### 4.2. Mô hình phân tích: fact, dimension và mức hạt

Kho phân tích thường tổ chức dữ liệu theo **fact** (sự kiện có thể đo) và **dimension** (góc nhìn để lọc/nhóm):

~~~mermaid
flowchart TB
    F["FactPayment — một dòng cho một giao dịch đã xác nhận"]
    D1["DimDate — ngày, tuần, tháng"] --> F
    D2["DimChannel — kênh bán"] --> F
    D3["DimProduct — dòng sản phẩm"] --> F
    D4["DimRegion — khu vực"] --> F
    F --> M["Measure: số giao dịch, gross amount"]
~~~

**Mức hạt (grain)** phải được xác định trước khi tạo fact. Nếu mỗi dòng fact là **một giao dịch thanh toán**, không được JOIN trực tiếp với nhiều dòng sản phẩm rồi cộng `gross_amount_minor`: một giao dịch có ba dòng hàng sẽ bị đếm ba lần. Muốn phân tích theo sản phẩm, cần fact ở mức **dòng đơn hàng**, phân bổ số tiền theo quy tắc rõ ràng, hoặc xây dựng bridge/cầu nối phù hợp.

Một số khái niệm quan trọng:

- **Fact table:** mã sự kiện duy nhất, khóa tham chiếu dimension, thời gian sự kiện và measure được định nghĩa rõ.
- **Dimension:** tên kênh, vùng, nhóm hàng, nhóm khách; có thể lưu lịch sử thay đổi (ví dụ Slowly Changing Dimension Type 2) để truy vấn theo trạng thái tại thời điểm phát sinh.
- **Snapshot:** ghi nhận trạng thái ở các mốc phục vụ câu hỏi “tồn kho cuối ngày” hay “số đơn đang mở”. Snapshot khác với dòng sự kiện thanh toán.
- **Aggregation/materialized view:** tính trước số liệu thường dùng để đáp ứng dashboard, nhưng cần chính sách refresh hoặc cập nhật tăng dần.

Lựa chọn mô hình phụ thuộc câu hỏi. Tổng số tiền thanh toán trong tháng, số đơn đã hoàn tất và tồn kho tại 23:59 là ba measure có **định nghĩa nghiệp vụ khác nhau**; không nên ép tất cả vào một bảng tổng hợp chung nếu làm mất ý nghĩa.

### 4.3. Row store và column store

Lưu trữ theo hàng (row-oriented) thường phù hợp khi thao tác cần đọc/ghi đủ các thuộc tính của một thực thể hoặc ít hàng. Lưu trữ theo cột (column-oriented) thường phù hợp khi quét một số cột trên rất nhiều hàng, vì có thể nén và đọc chọn lọc các cột cần thiết. Đây là khuynh hướng kiến trúc, không phải luật tuyệt đối: engine, index, cache, partition và workload thật mới quyết định hiệu năng.

Không nên chuyển một bảng OLTP sang warehouse chỉ vì lưu trữ cột có tốc độ tính tổng tốt. Hệ phân tích có thể có độ trễ nạp hoặc giới hạn cho cập nhật từng hàng, ràng buộc và transaction khác biệt so với yêu cầu giao dịch.

## 5. Tách đường giao dịch và đường phân tích

Khi hai tải cùng lớn và có mức dịch vụ khác nhau, kiến trúc thường tách nguồn ghi giao dịch khỏi hệ xử lý phân tích:

~~~mermaid
flowchart LR
    U["Ứng dụng Java"] -->|"Command / ghi nghiệp vụ"| O[("OLTP database")]
    U -->|"Đọc cần trạng thái mới nhất"| O
    O -->|"Outbox / CDC / ETL"| P["Pipeline xử lý"]
    P -->|"Chuẩn hóa, kiểm chứng, chống trùng"| W[("Warehouse / OLAP store")]
    W --> B["Dashboard / phân tích"]
    O -->|"Replication"| R[("Read replica")]
    R --> Q["Một số truy vấn đọc"]
~~~

**Database OLTP là nguồn có thẩm quyền cho giao dịch** theo ranh giới sở hữu. Warehouse là bản biểu diễn phục vụ phân tích, có thể kết hợp các nguồn khác nhau và phải công bố độ mới dữ liệu. Trường hợp đặc biệt như HTAP có thể xử lý giao dịch và phân tích trong cùng nền tảng nhưng vẫn phải tách tài nguyên, đảm bảo mức nhất quán và đo ảnh hưởng lẫn nhau.

### 5.1. Những phương án triển khai thường dùng

| Phương án | Khi nào phù hợp | Giới hạn chính |
| --- | --- | --- |
| Một database với truy vấn báo cáo có kiểm soát | Lượng dữ liệu nhỏ, ít dashboard, tài nguyên còn dư | Dễ ảnh hưởng p95/p99 giao dịch khi báo cáo tăng |
| Read replica cho truy vấn đọc | Báo cáo tương đối đơn giản, dung sai độ trễ sao chép | Vẫn dùng kiểu dữ liệu/index giao dịch; truy vấn nặng gây lag và tốn tài nguyên |
| Materialized view / bảng tổng hợp trong cùng hệ | Các chỉ số có mẫu cố định, refresh vừa phải | Chi phí làm mới; vẫn có thể tranh chấp tài nguyên |
| Database/kho phân tích riêng được nạp theo lô | Báo cáo nhiều chiều, dữ liệu lớn, chấp nhận chậm cập nhật | ETL, orchestration, backfill và quản lý pipeline |
| CDC hoặc event stream vào hệ phân tích | Cần cập nhật thường xuyên, giảm quét bảng nguồn | Phức tạp về thứ tự, lặp, schema và lỗi đường truyền |
| HTAP / hệ kết hợp có cách ly tài nguyên | Cần truy vấn mới với cả đặc điểm giao dịch và phân tích | Phải kiểm chứng cam kết thực tế về độ trễ, isolation và chi phí |

**Read replica không tự động là warehouse**: nó thường sao chép lược đồ và các cập nhật của OLTP, không tự xây fact/dimension, sửa định nghĩa metric hay giải quyết báo cáo lịch sử. Nếu truy vấn phân tích làm follower bị quá tải, lag có thể tăng, ảnh hưởng cả mục đích failover.

### 5.2. Đồng bộ dữ liệu: snapshot, CDC, idempotency và backfill

Một pipeline đúng cần trả lời:

1. **Lấy dữ liệu từ đâu?** Dùng snapshot có tính nhất quán, outbox, CDC/WAL/binlog, API hay truy xuất định kỳ. Nếu ghép snapshot ban đầu với luồng thay đổi, phải có **ranh giới/vị trí log** để không bỏ sót hoặc ghi trùng trong giai đoạn chuyển tiếp.
2. **Nhận diện sự kiện thế nào?** Dùng khóa sự kiện, khóa nghiệp vụ và phiên bản; cùng một event có thể đến nhiều lần sau retry. Consumer cần chống xử lý lặp.
3. **Đối phó sai thứ tự và đến muộn ra sao?** Có thể cần xử lý upsert theo version, watermark, cửa sổ tính lại, hoặc backfill phạm vi đã ảnh hưởng.
4. **Làm sao biết dữ liệu đã đủ?** Theo dõi watermark, hàng tồn đọng, độ trễ, số bản ghi và đối soát với nguồn có thẩm quyền.
5. **Khi schema đổi thì sao?** Quản lý hợp đồng dữ liệu, thêm trường tương thích, chuyển đổi dần và kiểm tra những phép đo phụ thuộc trường cũ.

Nếu database giao dịch commit thành công nhưng quá trình phát sự kiện thất bại, **transactional outbox** có thể ghi ý định phát cùng giao dịch và gửi lại sau. Tuy nhiên, phát lại sự kiện có thể tạo thông điệp lặp; phía phân tích phải dùng ID/version để bảo đảm phép tổng hợp không đếm hai lần. Không nên coi “đã gửi tới broker” là bảo đảm tuyệt đối rằng tất cả dashboard đã bắt kịp.

## 6. Tính nhất quán: giao dịch đúng và chỉ số đúng không giống nhau

### 6.1. Cam kết OLTP

Với các thao tác như trừ tồn kho hoặc xác nhận thanh toán, cần:

- **Atomicity:** các phần phụ thuộc của một thao tác cùng commit hoặc cùng rollback.
- **Consistency:** ràng buộc dữ liệu và bất biến nghiệp vụ được thực thi đúng.
- **Isolation:** các giao dịch đồng thời không tạo kết quả sai theo mức cô lập được chọn.
- **Durability:** dữ liệu đã commit được giữ theo cam kết của hệ thống lưu trữ.

Nhiều bất biến không thể bảo vệ chỉ bằng `CHECK` một hàng. Ví dụ, chống đặt quá một suất cho cùng khung giờ có thể cần khóa duy nhất, khóa hàng, SERIALIZABLE hoặc một thuật toán đặt chỗ đúng theo dạng tranh chấp. Việc chọn isolation level phải dựa trên sự cố muốn tránh (lost update, write skew, phantom...) và chi phí thực tế.

### 6.2. Cam kết OLAP

Một kết quả phân tích đúng đòi hỏi nhiều hơn việc SQL chạy thành công:

- **Đúng định nghĩa chỉ số:** “doanh thu” tính ở thời điểm đặt hàng, khi thanh toán hay khi ghi nhận kế toán? Hoàn tiền có trừ không?
- **Đúng mức hạt:** không nhân đôi doanh thu vì JOIN nhiều dòng.
- **Đúng phạm vi thời gian:** dùng múi giờ nào, tính theo `paid_at` hay `created_at`, có xử lý dữ liệu đến muộn không?
- **Đúng tập dữ liệu:** pipeline đã bắt kịp đến mốc nào, có thiếu partition hoặc duplicate event không?
- **Có thể tái lập:** cùng định nghĩa, dữ liệu nguồn và phiên bản chuyển đổi phải cho ra kết quả đối soát được.

Một dashboard có thể hiển thị nhất quán **theo snapshot của dữ liệu phân tích**, nhưng snapshot đó vẫn có thể cũ so với giao dịch mới nhất. Phân biệt **đúng tại thời điểm dữ liệu đã chốt** với **mới nhất hiện tại**.

## 7. Thiết kế mục tiêu hiệu năng có thể đo

“Cần nhanh” không đủ để chọn hệ lưu trữ. Hãy đặt mục tiêu theo hành vi người dùng và độ lớn dữ liệu giả định:

| Yêu cầu | Mục tiêu minh họa | Cần đo |
| --- | --- | --- |
| Ghi đơn hàng | p95 dưới 250 ms tại 300 request/s | Thời gian end-to-end, p95/p99, lỗi, lock wait, commit latency |
| Tra cứu đơn theo ID | p95 dưới 80 ms | Query plan, index hit, số hàng quét, pool wait |
| Dashboard tổng hợp 12 tháng | p95 dưới 8 giây khi 20 người cùng mở | Thời gian query, CPU, memory spill, scan bytes, concurrency |
| Độ mới dashboard | 99% dữ liệu thanh toán xuất hiện trong 5 phút | End-to-end ingestion lag, watermark, lỗi và retry |
| Đối soát | Không có ID thanh toán thiếu/trùng ngoài ngưỡng kiểm soát | Count/checksum theo phân đoạn, tổng tiền từng loại tiền tệ |

Những con số là **ví dụ để luyện cách đặc tả**, không phải chuẩn chung cho mọi sản phẩm. Ngưỡng thật phải gắn với đặc tính người dùng, khối lượng dữ liệu, chi phí và sự thống nhất của nhóm sở hữu nghiệp vụ.

### 7.1. Đánh giá tải giao dịch

Xác định số lệnh ghi và đọc mỗi giây, tỷ lệ đọc/ghi, kích thước transaction, phân bố truy cập khóa nóng và mức đồng thời. Một hệ có QPS không cao vẫn có thể tắc khi tất cả giao dịch tranh chấp cùng một hàng tồn kho. Quan sát connection pool, deadlock, lock wait, WAL và số lần retry khi chọn cơ chế cô lập.

### 7.2. Đánh giá tải phân tích

Xác định số ngày/tháng lịch sử, số dòng/byte quét, số dimension lọc, tập group lớn nhất, số dashboard đồng thời, nhu cầu refresh và dung lượng lưu trữ tăng theo thời gian. Thử các truy vấn đại diện, không chỉ một câu `SELECT COUNT(*)`. Cần có workload mùa cao điểm và dữ liệu tương tự thực tế khi đo.

## 8. Ranh giới persistence trong Java

Ứng dụng Java nên thể hiện rõ **đường giao dịch có quyền ghi** và **đường phân tích chỉ đọc** bằng repository/service và cấu hình kết nối phù hợp. Ví dụ dưới dùng hai `DataSource` tách biệt để minh họa vai trò. Chúng có thể trỏ đến hai hệ quản trị, hai cụm hoặc hai pool khác nhau tùy thiết kế:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

record SalesByChannel(String channel, String currency, long grossMinor) {}

public final class PersistenceBoundary {
    private final DataSource transactionDataSource;
    private final DataSource analyticsDataSource;

    public PersistenceBoundary(DataSource transactionDataSource,
                               DataSource analyticsDataSource) {
        this.transactionDataSource = transactionDataSource;
        this.analyticsDataSource = analyticsDataSource;
    }

    public boolean decreaseStock(String sku, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        try (Connection connection = transactionDataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                int changed;
                try (PreparedStatement statement = connection.prepareStatement(
                        "UPDATE inventory_stock "
                      + "SET available = available - ?, version = version + 1 "
                      + "WHERE sku = ? AND available >= ?")) {
                    statement.setInt(1, quantity);
                    statement.setString(2, sku);
                    statement.setInt(3, quantity);
                    changed = statement.executeUpdate();
                }
                if (changed != 1) {
                    connection.rollback();
                    return false;
                }
                connection.commit();
                return true;
            } catch (SQLException error) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }

    public List<SalesByChannel> salesByChannel(
            java.time.Instant from, java.time.Instant to) throws SQLException {
        String sql = """
                SELECT channel, currency, SUM(gross_amount_minor) AS gross_minor
                FROM fact_payment
                WHERE paid_at >= ? AND paid_at < ?
                GROUP BY channel, currency
                ORDER BY channel, currency
                """;
        List<SalesByChannel> rows = new ArrayList<>();
        try (Connection connection = analyticsDataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setTimestamp(1, java.sql.Timestamp.from(from));
            statement.setTimestamp(2, java.sql.Timestamp.from(to));
            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    rows.add(new SalesByChannel(
                            result.getString("channel"),
                            result.getString("currency"),
                            result.getLong("gross_minor")
                    ));
                }
            }
        }
        return rows;
    }
}
~~~

Đây là ví dụ dạy **phân chia trách nhiệm và bind tham số**, không phải API production hoàn chỉnh. Phương thức giảm tồn kho chưa thực hiện phiếu giữ, outbox hay idempotency; ứng dụng thật phải gắn chúng trong cùng transaction khi nghiệp vụ cần. Phương thức báo cáo giả định analytics store có bảng `fact_payment` và có dữ liệu theo đúng định nghĩa; `Timestamp`/múi giờ cần cấu hình nhất quán với cột dữ liệu và trình điều khiển đang dùng.

Cần bổ sung giới hạn thời gian truy vấn, số dòng trả về, phân trang hoặc xuất báo cáo bất đồng bộ cho truy vấn lớn, kiểm soát lỗi và cấu hình pool riêng. Không cấp quyền ghi giao dịch cho tài khoản analytics; không để batch báo cáo vô tình dùng pool OLTP. Nếu database hỗ trợ giao dịch read-only, có thể khai báo và áp dụng nó đúng đường đọc.

### 8.1. Lỗi kết nối và retry có hệ quả khác nhau

- **OLTP:** khi kết nối mất đúng lúc `COMMIT`, client có thể không biết giao dịch đã thành công hay chưa. Retry lệnh không idempotent có thể gây trừ tiền/tồn kho hai lần; cần request ID, ràng buộc duy nhất và kiểm tra trạng thái nguồn.
- **OLAP:** truy vấn thuần đọc có thể thử lại khi lỗi tạm thời, nhưng phải kiểm soát timeout, chi phí tài nguyên và snapshot. Nếu dữ liệu đang được nạp, lần retry có thể thấy tập dữ liệu khác; báo cáo cần định nghĩa `as_of` hoặc watermark nếu yêu cầu tái lập.
- **Pipeline:** “đã nạp một nửa batch” là trạng thái lỗi riêng. Cần staging, commit theo phân đoạn, idempotent merge và cơ chế khôi phục con trỏ xử lý.

## 9. Bảo mật, sao lưu và thay đổi schema

Tách OLTP/OLAP không có nghĩa rằng warehouse không cần kiểm soát dữ liệu. Warehouse có thể tập hợp nhiều nguồn thành tập dữ liệu nhạy cảm hơn từng nguồn:

- **Quyền truy cập:** cấp tài khoản OLTP quyền giao dịch tối thiểu; công cụ BI chỉ đọc các view/bảng đã được phê duyệt. Giới hạn truy cập dữ liệu cá nhân, tách vai trò phân tích và quản trị.
- **Ẩn dữ liệu nhạy cảm:** hạn chế đồng bộ token, mật khẩu, dữ liệu thanh toán nhạy cảm; cân nhắc mask/pseudonymization cho mục đích phân tích.
- **Lược đồ và hợp đồng dữ liệu:** thay đổi field nguồn theo quy trình mở rộng → chuyển đổi → thu hẹp; không để pipeline silently cast sai đơn vị tiền hoặc đổi nghĩa trạng thái.
- **Sao lưu và phục hồi:** OLTP cần xác định RPO/RTO để bảo vệ dữ liệu giao dịch. Kho phân tích có thể tái dựng nếu còn nguồn, log và logic ETL, nhưng việc dựng lại có thể rất lâu; vì vậy vẫn cần kế hoạch backup hoặc snapshot dựa trên RTO, chi phí và khả năng backfill.
- **Đối soát:** xác minh tổng tiền/đếm giao dịch theo khoảng thời gian giữa hệ nguồn và hệ phân tích, có quy tắc loại trừ trạng thái chưa chốt và hoàn tiền.

Replication không thay thế backup: thao tác xóa nhầm có thể lan đến replica. Warehouse cũng không mặc nhiên là backup có thể khôi phục database giao dịch; dữ liệu đã biến đổi hoặc tổng hợp có thể không còn đủ các thông tin để dựng lại giao dịch gốc.

## 10. Bài tập tình huống: báo cáo cuối tháng làm chậm đặt hàng

Một API Java dùng PostgreSQL để tạo đơn hàng và phục vụ dashboard quản trị. Thông số giả định:

- Giờ cao điểm: 250 thao tác đặt hàng/giây; p95 mục tiêu của API đặt hàng là 300 ms.
- Bảng đơn hàng có 80 triệu hàng, giữ lịch sử 3 năm.
- Dashboard chạy truy vấn tổng doanh thu theo tháng, nhóm sản phẩm và vùng; mỗi truy vấn quét hàng chục triệu dòng.
- Khi 15 người mở dashboard cùng lúc, CPU database tăng gần bão hòa, truy vấn báo cáo tràn bộ nhớ ra đĩa, p95 đặt hàng tăng lên hơn 2 giây.
- Nhóm sản phẩm muốn dashboard cập nhật trong vòng 10 phút sau thanh toán; báo cáo kế toán cuối ngày cần kết quả có thể đối soát.

**Hãy đề xuất thiết kế theo các bước sau:**

1. Xác định đường OLTP nào phải giữ độ trễ thấp; nêu bất biến không được vi phạm dù số lượng request tăng.
2. Giải thích vì sao chỉ tối ưu một câu `GROUP BY` hoặc thêm index trên bảng đơn hàng có thể chưa đủ.
3. So sánh ba cách: tiếp tục báo cáo trên primary nhưng giới hạn truy vấn, chuyển sang read replica và đưa dữ liệu sang kho phân tích riêng.
4. Đề xuất pipeline đạt mục tiêu độ mới 10 phút; chọn khóa chống trùng, cách theo dõi lag và cách backfill.
5. Xác định “doanh thu” là gì, mô hình fact ở grain nào và xử lý hoàn tiền, đơn hủy, múi giờ, tiền tệ ra sao.
6. Đặt ít nhất ba phép đo xác minh hệ thống mới không ảnh hưởng OLTP và kết quả phân tích đúng.

**Một hướng giải khả thi:**

- Giữ thao tác tạo đơn và kiểm tra tồn kho trong transaction ngắn, đặt ràng buộc và cơ chế đồng thời tại database có thẩm quyền.
- Giới hạn timeout và concurrency báo cáo ở giai đoạn khẩn cấp; đánh giá index/query plan và chuyển dashboard khỏi pool giao dịch.
- Với khối lượng 80 triệu hàng và dashboard nhiều chiều, ưu tiên warehouse hoặc store phân tích riêng; read replica có thể là bước trung gian nhưng không thay thế mô hình fact/dimension.
- Đồng bộ thay đổi đã commit bằng outbox/CDC hoặc ETL có checkpoint; nạp idempotent theo event ID/version; theo dõi watermark và cảnh báo khi quá 10 phút.
- Dùng sự kiện thanh toán đã xác nhận làm cơ sở đo gross payment; hoàn tiền là sự kiện riêng hoặc phép điều chỉnh có quy tắc, và tính chỉ số theo chính sách nghiệp vụ.
- Đo p95/p99 API đặt hàng khi chạy 15 dashboard đồng thời, query scan/memory spill, ingestion lag, tỷ lệ trùng/thiếu và chênh lệch tổng tiền theo ngày/tiền tệ.

## 11. Checklist chốt yêu cầu lưu trữ

- [ ] Đã phân nhóm workload theo **truy vấn giao dịch, báo cáo vận hành và phân tích lịch sử**.
- [ ] Có mẫu truy vấn điển hình, số hàng/byte quét, tần suất đọc/ghi và số người dùng đồng thời.
- [ ] Đã đặt p95/p99, throughput, timeout và ngưỡng lỗi cho giao dịch quan trọng.
- [ ] Đã nêu độ mới dữ liệu cần thiết và cách công bố mốc dữ liệu của dashboard.
- [ ] Có chủ sở hữu dữ liệu, quy tắc toàn vẹn, transaction và isolation cho thao tác ghi.
- [ ] Đã chọn mô hình schema/index cho OLTP và fact/dimension/aggregation khi phân tích cần.
- [ ] Có phương án giới hạn tài nguyên của báo cáo để bảo vệ giao dịch.
- [ ] Nếu có pipeline, đã thiết kế chống trùng, replay, late data, schema evolution và đối soát.
- [ ] Có ranh giới repository/DataSource và quyền truy cập phù hợp trong ứng dụng Java.
- [ ] Đã xác định backup, RPO/RTO, phân quyền, bảo vệ dữ liệu nhạy cảm và cách phục hồi.
- [ ] Đã đo bằng workload đại diện thay vì chỉ dựa trên lời quảng cáo tính năng công nghệ.

**Ghi nhớ:** OLTP tối ưu **thao tác nghiệp vụ ngắn, đúng và đồng thời**; OLAP tối ưu **đọc rộng, tổng hợp và trả lời câu hỏi từ dữ liệu lịch sử**. Có thể phối hợp nhiều cơ chế lưu trữ, nhưng thiết kế tốt phải bảo vệ ranh giới ghi có thẩm quyền, công bố độ mới dữ liệu phân tích và kiểm chứng cả **hiệu năng giao dịch** lẫn **độ đúng của chỉ số**.
