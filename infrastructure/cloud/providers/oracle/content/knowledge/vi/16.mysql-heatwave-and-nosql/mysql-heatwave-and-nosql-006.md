# HeatWave cluster và xử lý truy vấn phân tích

## 1. Mục tiêu và bối cảnh

Trong chương **MySQL HeatWave và NoSQL** của lộ trình Oracle Cloud Infrastructure (OCI), bài này trình bày cách HeatWave cluster tăng tốc truy vấn phân tích trên dữ liệu MySQL, từ kiến trúc xử lý đến nạp dữ liệu, kiểm tra offload và vận hành.

Sau bài học, bạn có thể:

- Phân biệt MySQL DB system, InnoDB và HeatWave cluster.
- Giải thích vì sao truy vấn quét, join và tổng hợp có thể hưởng lợi từ HeatWave.
- Chuẩn bị các bảng, nạp dữ liệu và xác nhận bảng sẵn sàng truy vấn.
- Kiểm tra truy vấn có sử dụng secondary engine RAPID hay không.
- Đánh giá kết quả, tính cập nhật dữ liệu, hiệu năng, tài nguyên và chi phí.
- Xây dựng quy trình giám sát và xử lý fallback hoặc load lỗi.

Các ví dụ chính sử dụng bảng **InnoDB trong DB system**. HeatWave còn có Lakehouse để xử lý dữ liệu từ Object Storage và các khả năng khác, nhưng những đường nạp đó có điều kiện riêng. Không lấy hành vi cập nhật của bảng InnoDB để suy ra hành vi của mọi nguồn Lakehouse.

Tên schema, dữ liệu mẫu, mục tiêu thời gian và số liệu benchmark giả định trong bài chỉ phục vụ học tập. Shape, giới hạn, tính năng và metadata cần đối chiếu phiên bản dịch vụ đang sử dụng.

## 2. Kiến trúc: MySQL tiếp nhận SQL, HeatWave tăng tốc phần phân tích

### 2.1. Các thành phần chính

| Thành phần | Vai trò |
| --- | --- |
| MySQL DB system | Cung cấp endpoint MySQL, xác thực, xử lý SQL và phục vụ công việc trên database |
| InnoDB | Primary storage engine cho các bảng giao dịch trong ví dụ |
| HeatWave cluster | Cụm xử lý phân tích phân tán, lưu dữ liệu theo định dạng phù hợp và thực thi query được offload |
| RAPID | Tên secondary engine dùng để gắn các bảng với đường xử lý HeatWave |
| Cơ chế load và change propagation | Đưa dữ liệu ban đầu và các thay đổi phù hợp từ bảng nguồn sang HeatWave |

HeatWave cluster cung cấp query engine phân tán, scale-out, in-memory và hybrid columnar. Nó được bổ sung vào MySQL DB system thay vì thay endpoint ứng dụng bằng endpoint từng node phân tích. [Tổng quan HeatWave cluster](https://docs.oracle.com/en-us/iaas/mysql-database/doc/heatwave.html).

Một kết nối MySQL vẫn có thể chạy truy vấn trên InnoDB hoặc offload truy vấn đủ điều kiện sang HeatWave. Vì vậy, chỉ nhìn việc ứng dụng kết nối được tới DB system chưa biết engine nào thực hiện một query cụ thể.

### 2.2. Luồng xử lý tổng quát

~~~mermaid
flowchart LR
    APP["Ứng dụng Java / BI / MySQL client"]
    SQL["MySQL endpoint: xác thực, SQL và optimizer"]
    INNO["InnoDB trên DB system"]
    HW["HeatWave cluster: RAPID"]
    RES["Kết quả trả về client"]

    APP --> SQL
    SQL -->|"Giao dịch và truy vấn theo đường primary"| INNO
    INNO -->|"Load ban đầu và change propagation"| HW
    SQL -->|"Truy vấn phân tích đủ điều kiện"| HW
    INNO --> RES
    HW --> RES
~~~

Sơ đồ mô tả hai đường xử lý; không có nghĩa client tùy ý ghi trực tiếp vào bộ nhớ HeatWave. Các thao tác giao dịch của bộ dữ liệu trong bài vẫn đi qua bảng InnoDB của DB system.

### 2.3. Vì sao định dạng cột và xử lý phân tán có ích?

Một báo cáo doanh thu có thể cần đọc hàng triệu dòng nhưng chỉ sử dụng vài cột: ngày, sản phẩm, số lượng và giá. Định dạng phù hợp phân tích giúp xử lý những cột cần thiết, còn các node chia sẻ công việc để thực hiện scan, join và aggregation.

HeatWave sử dụng xử lý vectorized và phân phối dữ liệu giữa các node. Khi chạy query, các toán tử có thể xử lý các khối dữ liệu thay vì xử lý từng bản ghi theo cùng cách của một đường thực thi truyền thống. [Kiến trúc và xử lý query của HeatWave](https://dev.mysql.com/doc/heatwave/en/mys-hw-about-heatwave.html).

Lợi ích thực tế phụ thuộc dữ liệu, truy vấn, số node, khả năng cân bằng công việc và chi phí trao đổi. Không nên giả định tăng gấp đôi node sẽ giảm đúng một nửa thời gian của mọi query.

## 3. Chọn workload phù hợp và đặt tiêu chí đánh giá

### 3.1. Các ứng viên thường đáng thử

- Báo cáo đọc nhiều bản ghi, lọc theo thời gian rồi GROUP BY.
- Join bảng giao dịch lớn với các bảng danh mục.
- Tổng hợp doanh thu, số lượng, phân bố và xu hướng.
- Phân tích ad hoc cần đọc nhiều dữ liệu hơn một truy vấn lookup thông thường.
- Workload có báo cáo nặng đang tranh tài nguyên với giao dịch.

Một query lấy một đơn hàng bằng primary key có thể đã rất nhanh trên InnoDB. Chi phí lập kế hoạch và thực thi phân tán không bảo đảm tạo lợi ích cho loại truy cập nhỏ này.

### 3.2. Định nghĩa “nhanh hơn” theo mục tiêu dịch vụ

Ví dụ yêu cầu giả định:

~~~text
Báo cáo doanh thu 90 ngày:
- Kết quả đúng theo quy tắc trạng thái đơn và chiết khấu.
- p95 không quá 5 giây ở 8 người chạy đồng thời.
- OLTP vẫn đáp ứng mục tiêu riêng trong cùng khoảng thử.
- Sau thay đổi dữ liệu hợp lệ, báo cáo phản ánh đúng theo
  cơ chế nhất quán và cấu hình đã xác nhận.

Vận hành:
- Các bảng bắt buộc đều sẵn sàng trong HeatWave.
- Biết khi nào query fallback về DB system.
- Có thời gian khôi phục dịch vụ phân tích sau restart.
~~~

Đây là tiêu chí do dự án đặt ra, không phải cam kết hiệu năng của Oracle.

Không chỉ đo query time. Cần đo thời gian load/recovery, ảnh hưởng tới DB system, concurrency, lỗi, kết quả đúng và tổng chi phí cấu hình.

### 3.3. Tách ba trạng thái

| Trạng thái | Bằng chứng cần có |
| --- | --- |
| Cluster đã được tạo và hoạt động | Trạng thái tài nguyên, node và work request |
| Bảng đã được nạp và sẵn sàng | Load status của từng bảng bắt buộc |
| Query thực sự dùng HeatWave | EXPLAIN, thực thi có kiểm soát và telemetry phù hợp |

Ba trạng thái có liên quan nhưng không thay thế nhau. Cluster hoạt động vẫn có thể thiếu một bảng; tất cả bảng đã nạp vẫn có thể có query không đủ điều kiện offload.

## 4. Chuẩn bị tài nguyên OCI, kết nối và quyền

### 4.1. Điều kiện ban đầu

Cần có:

- DB system với shape và cấu hình hỗ trợ HeatWave.
- HeatWave cluster được tạo với tài nguyên phù hợp.
- Đường mạng tới endpoint MySQL của DB system.
- MySQL client hoặc connector tương thích.
- Danh tính database có quyền chuẩn bị/load trong phạm vi được giao.
- Quyền OCI để quản lý hoặc quan sát cluster theo nhiệm vụ.

Khi thêm cluster trong OCI, chọn shape và số node được dịch vụ hỗ trợ; có thể dùng chức năng ước lượng node. Với DB system HA, cluster gắn với primary instance theo mô hình dịch vụ. [Thêm HeatWave cluster](https://docs.oracle.com/en-us/iaas/mysql-database/doc/adding-heatwave-cluster.html).

Không mở kết nối ứng dụng trực tiếp tới mạng nội bộ của HeatWave node. Dùng endpoint MySQL và thiết kế mạng được dịch vụ tài liệu hóa.

### 4.2. Phân tách nhiệm vụ

| Danh tính | Công việc |
| --- | --- |
| Quản trị hạ tầng OCI | Tạo, sửa kích thước, theo dõi work request và chi phí cluster |
| Người quản lý dữ liệu/load | Kiểm tra schema, thực hiện DDL/load và xử lý lỗi nạp |
| Người dùng phân tích | SELECT trên dữ liệu hoặc view được phép |
| Người quan sát | Đọc metric và metadata cần thiết theo phạm vi |

IAM quản lý tài nguyên cloud và quyền MySQL là hai lớp khác nhau. Không cấp quyền ALTER/DDL hoặc quản trị toàn server cho tài khoản báo cáo chỉ để query được offload.

Các routine tự động và bảng Performance Schema có yêu cầu quyền riêng. Nếu runtime không đọc được metadata giám sát, dùng danh tính vận hành phù hợp; không nâng runtime thành administrator.

### 4.3. Ghi phiên bản và cấu hình trước thực hành

Trong phiên MySQL được phép:

~~~sql
SELECT VERSION();

SHOW VARIABLES LIKE 'autocommit';
SHOW VARIABLES LIKE 'use_secondary_engine';

SHOW GLOBAL STATUS LIKE 'rapid_cluster_status';
~~~

Ghi lại DB system, phiên bản, shape/số node và mục đích môi trường. Với bảng hoặc biến không có trong phiên bản đang dùng, đối chiếu tài liệu đúng phiên bản thay vì tự suy cluster đã hỏng.

Các thay đổi session về autocommit và engine ở phần sau phải được thực hiện trong **phiên phân tích riêng, không có transaction nghiệp vụ đang mở**.

## 5. Bộ dữ liệu minh họa: doanh thu theo ngày và danh mục

### 5.1. Mô hình dữ liệu

Ba bảng:

- `product`: danh mục sản phẩm.
- `sales_order`: ngày, vùng và trạng thái của đơn.
- `order_item`: số lượng, đơn giá và tỷ lệ chiết khấu từng dòng.

Bài toán: tổng hợp doanh thu các đơn `PAID` theo ngày và category. Không tính đơn hủy; mỗi dòng đóng góp `quantity × unit_price × (1 - discount)`.

Dữ liệu rất nhỏ để dễ đối soát. Nó không đại diện khả năng tăng tốc ở quy mô lớn và có thể không được optimizer tự chọn offload trong chế độ bình thường.

### 5.2. Tạo schema và bảng

Thực hiện bằng danh tính triển khai phù hợp trên môi trường thử, với tên schema chưa sử dụng:

~~~sql
CREATE DATABASE analytics_lab CHARACTER SET utf8mb4;

CREATE TABLE analytics_lab.product (
    product_id BIGINT NOT NULL,
    product_name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE TABLE analytics_lab.sales_order (
    order_id BIGINT NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

CREATE TABLE analytics_lab.order_item (
    order_id BIGINT NOT NULL,
    line_no INT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    discount DECIMAL(5, 4) NOT NULL DEFAULT 0,
    PRIMARY KEY (order_id, line_no)
) ENGINE = InnoDB;
~~~

Không chạy lệnh tạo hoặc dọn schema thử trên schema production. Việc sử dụng primary key ở đây còn giúp xác định bản ghi rõ ràng cho các thao tác dữ liệu và đối soát.

### 5.3. Nạp dữ liệu vào InnoDB trước

~~~sql
INSERT INTO analytics_lab.product
    (product_id, product_name, category)
VALUES
    (1, 'Keyboard', 'PERIPHERAL'),
    (2, 'Mouse', 'PERIPHERAL'),
    (3, 'Monitor', 'DISPLAY'),
    (4, 'Laptop', 'COMPUTER');

INSERT INTO analytics_lab.sales_order
    (order_id, order_date, region, status)
VALUES
    (1001, '2026-11-01', 'HCM', 'PAID'),
    (1002, '2026-11-01', 'HN', 'PAID'),
    (1003, '2026-11-02', 'HCM', 'CANCELLED'),
    (1004, '2026-11-02', 'DN', 'PAID');

INSERT INTO analytics_lab.order_item
    (order_id, line_no, product_id, quantity, unit_price, discount)
VALUES
    (1001, 1, 1, 2,   500000.00, 0.0000),
    (1001, 2, 2, 1,   200000.00, 0.0000),
    (1002, 1, 3, 1,  3000000.00, 0.1000),
    (1003, 1, 4, 1, 15000000.00, 0.0000),
    (1004, 1, 2, 3,   200000.00, 0.0000),
    (1004, 2, 3, 1,  3200000.00, 0.0000);
~~~

Nếu công cụ đang dùng transaction tường minh, commit dữ liệu mẫu trước khi chuyển sang phần load. Không thay đổi autocommit tùy tiện giữa một transaction khác.

Đến đây dữ liệu đã ở InnoDB; chưa thể khẳng định đã có dữ liệu tương ứng trong HeatWave.

## 6. Nạp bảng vào HeatWave

### 6.1. Chọn các bảng và cột phục vụ truy vấn

Trước khi load:

1. Liệt kê query cần tăng tốc.
2. Xác định đầy đủ bảng và cột được truy cập.
3. Kiểm tra kiểu dữ liệu, SQL mode và tính năng theo phiên bản.
4. Ước lượng memory và thời gian load.
5. Chọn khoảng thực hiện phù hợp tải OLTP.

Một join ba bảng cần cả ba bảng sẵn sàng theo yêu cầu offload của query. Không nạp riêng bảng fact lớn rồi mặc định các bảng dimension nhỏ luôn được đọc từ InnoDB trong cùng đường xử lý.

Nếu một cột được loại khỏi secondary engine, query truy cập cột đó phải được đánh giá lại. Quyết định giảm footprint phải đi cùng inventory truy vấn.

### 6.2. Auto Parallel Load: dryrun trước

Chạy trên schema thử:

~~~sql
CALL sys.heatwave_load(
    JSON_ARRAY('analytics_lab'),
    JSON_OBJECT('mode', 'dryrun')
);
~~~

Dryrun hỗ trợ xem lỗi/cảnh báo, ước lượng và script load được sinh; nó chưa nạp dữ liệu vào cluster. Cần đọc báo cáo, đặc biệt các thay đổi schema/secondary-engine được đề xuất, trước khi chuyển sang load thật. [Auto Parallel Load](https://dev.mysql.com/doc/heatwave/en/mys-hw-auto-parallel-load.html).

Tên bảng báo cáo và chi tiết output có thể khác giữa phiên bản. Dùng phần chỉ dẫn trong kết quả routine và tài liệu của DB system, không sao chép một truy vấn bảng `sys` cũ rồi suy routine đã thành công nếu truy vấn đó lỗi.

Khi đã xử lý các lỗi và xác nhận phạm vi, thực hiện:

~~~sql
CALL sys.heatwave_load(
    JSON_ARRAY('analytics_lab'),
    JSON_OBJECT('mode', 'normal')
);
~~~

Đọc summary và kiểm tra từng bảng. Routine có thể báo lỗi ở một bảng và tiếp tục với bảng khác; việc CALL trả về không chứng minh toàn bộ schema đã load đầy đủ.

Dryrun cũng là thao tác cần tài nguyên và có output/report vận hành; không mô tả nó như một lệnh hoàn toàn không có tác động.

### 6.3. Đường manual để hiểu secondary engine

Đây là phương án thay thế minh họa; không cần chạy lại nếu đã load thành công bằng routine:

~~~sql
ALTER TABLE analytics_lab.product
    SECONDARY_ENGINE = RAPID;
ALTER TABLE analytics_lab.sales_order
    SECONDARY_ENGINE = RAPID;
ALTER TABLE analytics_lab.order_item
    SECONDARY_ENGINE = RAPID;

ALTER TABLE analytics_lab.product SECONDARY_LOAD;
ALTER TABLE analytics_lab.sales_order SECONDARY_LOAD;
ALTER TABLE analytics_lab.order_item SECONDARY_LOAD;
~~~

`SECONDARY_ENGINE = RAPID` xác định secondary engine, còn `SECONDARY_LOAD` đưa dữ liệu vào đường xử lý HeatWave. Một số phiên bản có guided load tự chuẩn bị secondary engine; việc khai báo tường minh ở đây giúp thể hiện hai khái niệm. [Định nghĩa secondary engine](https://dev.mysql.com/doc/heatwave/en/mys-hw-defining-secondary-engine.html).

Không đổi primary engine thành RAPID. Trong mô hình này, InnoDB tiếp tục là primary engine cho bảng giao dịch.

### 6.4. Load là một phần của ngân sách tài nguyên

Load ban đầu đọc và biến đổi dữ liệu từ DB system, nên có thể tác động OLTP. Lên lịch và quan sát CPU, memory, I/O cùng độ trễ ứng dụng.

Nếu có đợt ingest lớn, phương án reload và change propagation phải được đánh giá theo khối lượng, phiên bản và khoảng gián đoạn phân tích chấp nhận được. Không mặc định một cách tối ưu cho mọi kích thước dữ liệu. [Các phương thức load dữ liệu từ DB system](https://dev.mysql.com/doc/heatwave/en/mys-hw-loading-data.html).

## 7. Xác nhận bảng đã sẵn sàng

### 7.1. Kiểm tra trạng thái từng bảng

Bằng danh tính quan sát có quyền phù hợp:

~~~sql
SELECT
    i.TABLE_NAME,
    t.LOAD_STATUS,
    t.NROWS,
    t.SIZE_BYTES
FROM performance_schema.rpd_table_id AS i
JOIN performance_schema.rpd_tables AS t
    ON t.ID = i.ID
WHERE i.SCHEMA_NAME = 'analytics_lab'
ORDER BY i.TABLE_NAME;
~~~

Query minh họa dùng metadata HeatWave được tài liệu hóa; nếu phiên bản có khác biệt cột/quyền, đối chiếu schema metadata của phiên bản đó. [Theo dõi tiến độ và trạng thái load](https://dev.mysql.com/doc/heatwave/en/mys-hw-metadata-queries-load-progress.html).

Một số trạng thái cần nhận biết:

| Trạng thái | Cách hiểu trong vận hành |
| --- | --- |
| NOLOAD_RPDGSTABSTATE | Chưa được load |
| LOADING_RPDGSTABSTATE | Đang load |
| AVAIL_RPDGSTABSTATE | Đã load và có thể dùng cho query |
| STALE_RPDGSTABSTATE | Có vấn đề liên quan cập nhật, dữ liệu HeatWave cần được xử lý |
| UNAVAIL_RPDGSTABSTATE | Chưa khả dụng |

Danh sách và chi tiết thay đổi theo phiên bản. Không dùng một trạng thái “cluster healthy” để bỏ qua bảng đang không khả dụng. [Tham chiếu rpd_tables](https://dev.mysql.com/doc/heatwave/en/mys-hw-rpd-tables-table.html).

Nếu thiếu một trong ba bảng bắt buộc, chưa chuyển sang kết luận query đã sẵn sàng.

### 7.2. Kiểm tra metadata khác với kiểm tra kết quả

`NROWS`, load status và footprint có ích để phát hiện thiếu bảng hoặc load chưa xong. Tuy nhiên, chúng không thay cho đối soát báo cáo nghiệp vụ.

Một bảng có đủ số dòng vẫn có thể chứa dữ liệu nguồn sai. Một query chạy trên đúng engine vẫn có thể join sai khóa hoặc tính trùng doanh thu.

Tách ba phép kiểm:

1. Load đủ đối tượng.
2. Query được thực thi bằng engine dự kiến.
3. Kết quả đáp ứng quy tắc nghiệp vụ.

## 8. Kiểm tra query offload và chạy báo cáo

### 8.1. Điều kiện của đường query trong bài

Đối với các truy vấn phân tích minh họa, cần các bảng được chuẩn bị/load, cấu trúc SQL và kiểu dữ liệu được hỗ trợ, cùng cấu hình session phù hợp.

Tài liệu HeatWave yêu cầu autocommit bật cho đường offload được mô tả, và `use_secondary_engine` ở ON hoặc FORCED. SQL mode, hàm và giới hạn query vẫn cần kiểm tra theo phiên bản. [Điều kiện chạy query HeatWave](https://dev.mysql.com/doc/heatwave/en/mys-hw-query-prerequisites.html).

Trong một phiên phân tích mới, không có transaction khác:

~~~sql
SET SESSION autocommit = 1;

SHOW VARIABLES LIKE 'autocommit';
SHOW VARIABLES LIKE 'use_secondary_engine';
~~~

Chuyển autocommit từ 0 sang 1 có thể commit transaction hiện hành. Vì vậy không chạy bước chuẩn bị này tùy tiện trên connection đang dùng cho nghiệp vụ.

### 8.2. ON, OFF và FORCED

| Giá trị | Vai trò |
| --- | --- |
| OFF | Không dùng secondary engine cho query trong phiên |
| ON | Cho phép chọn HeatWave khi phù hợp; có thể fallback sang primary engine |
| FORCED | Yêu cầu query dùng secondary engine hoặc báo lỗi nếu không thể |

Các chế độ này có phạm vi session. [Biến use_secondary_engine](https://dev.mysql.com/doc/heatwave/en/heatwave-system-variables.html).

Trong vận hành thông thường, ON cho optimizer chọn đường xử lý phù hợp. Trong kiểm chứng, FORCED giúp tránh việc query chạy thành công trên InnoDB rồi bị hiểu nhầm là đã tăng tốc bằng HeatWave.

FORCED không bổ sung hỗ trợ cho SQL chưa được hỗ trợ và không làm bảng chưa load trở nên khả dụng. Nó cũng không phải cấu hình nên áp dụng rộng cho mọi connection giao dịch.

### 8.3. Dùng EXPLAIN để xem đường dự kiến

Với bộ dữ liệu nhỏ, đặt FORCED trong phiên thử riêng:

~~~sql
SET SESSION use_secondary_engine = 'FORCED';

EXPLAIN
SELECT
    o.order_date,
    p.category,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(
        SUM(i.quantity * i.unit_price * (1 - i.discount)),
        2
    ) AS revenue
FROM analytics_lab.sales_order AS o
JOIN analytics_lab.order_item AS i
    ON i.order_id = o.order_id
JOIN analytics_lab.product AS p
    ON p.product_id = i.product_id
WHERE o.status = 'PAID'
  AND o.order_date >= '2026-11-01'
  AND o.order_date < '2026-12-01'
GROUP BY o.order_date, p.category
ORDER BY o.order_date, p.category;
~~~

Trong output EXPLAIN truyền thống, dấu hiệu `Using secondary engine RAPID` ở cột Extra cho biết query được lập kế hoạch offload sang HeatWave. [EXPLAIN và xác nhận offload](https://dev.mysql.com/doc/heatwave/en/mys-hw-run-query.html).

EXPLAIN là bằng chứng kế hoạch tại thời điểm kiểm tra; cần chạy query và quan sát kết quả thực tế. Không coi thời gian chạy EXPLAIN là thời gian xử lý báo cáo.

### 8.4. Thực thi truy vấn

~~~sql
SELECT
    o.order_date,
    p.category,
    COUNT(DISTINCT o.order_id) AS order_count,
    ROUND(
        SUM(i.quantity * i.unit_price * (1 - i.discount)),
        2
    ) AS revenue
FROM analytics_lab.sales_order AS o
JOIN analytics_lab.order_item AS i
    ON i.order_id = o.order_id
JOIN analytics_lab.product AS p
    ON p.product_id = i.product_id
WHERE o.status = 'PAID'
  AND o.order_date >= '2026-11-01'
  AND o.order_date < '2026-12-01'
GROUP BY o.order_date, p.category
ORDER BY o.order_date, p.category;
~~~

Kết quả kỳ vọng từ chính dữ liệu mẫu:

| order_date | category | order_count | revenue |
| --- | --- | --- | --- |
| 2026-11-01 | DISPLAY | 1 | 2700000.00 |
| 2026-11-01 | PERIPHERAL | 1 | 1200000.00 |
| 2026-11-02 | DISPLAY | 1 | 3200000.00 |
| 2026-11-02 | PERIPHERAL | 1 | 600000.00 |

Tổng doanh thu là **7.700.000,00**. Đơn 1003 bị hủy không được tính; monitor của đơn 1002 được giảm 10%.

`order_count` là số đơn riêng biệt **trong từng nhóm**. Không cộng bốn giá trị này rồi kết luận có bốn đơn thanh toán: chỉ có ba đơn PAID, và đơn 1004 xuất hiện ở hai nhóm category. Các phép đếm distinct không phải lúc nào cũng cộng được giữa các nhóm.

Sau phiên kiểm chứng, đưa lựa chọn engine về trạng thái mong muốn:

~~~sql
SET SESSION use_secondary_engine = 'ON';
~~~

Nếu ứng dụng dùng pool, phải kiểm soát việc khôi phục trạng thái session trước khi connection được dùng cho công việc khác. Đừng để FORCED từ một phép thử ảnh hưởng các query runtime không liên quan.

### 8.5. Truy vấn thành công nhưng không offload

Các nhóm nguyên nhân thường gặp:

- Một bảng hoặc một cột cần thiết chưa có trong HeatWave.
- Cluster/bảng không khả dụng.
- Autocommit hoặc session không phù hợp.
- Hàm, toán tử, SQL mode hoặc kiểu dữ liệu chưa được hỗ trợ.
- Query quá rẻ để đường offload được chọn trong chế độ ON.
- Optimizer chọn đường khác theo cơ chế offload của phiên bản.

Tài liệu chẩn đoán có mô tả quyết định theo ngưỡng chi phí hoặc dynamic offload, tùy phiên bản. [Chẩn đoán query offload](https://dev.mysql.com/doc/heatwave/en/mys-hw-debugging-queries.html).

Hãy lưu SQL, cấu hình session, EXPLAIN và lỗi trong phạm vi dữ liệu được phép. Dùng FORCED ở phiên thử để làm rõ lý do, rồi xử lý nguyên nhân. Không thay hàng loạt biến optimizer hoặc tắt điều kiện kiểm tra để đạt một dòng “RAPID” trong output.

## 9. Dữ liệu thay đổi sau load: change propagation

### 9.1. Đường cập nhật của bảng InnoDB

Sau khi bảng được load ở chế độ phù hợp, các thay đổi INSERT/UPDATE/DELETE từ DB system được truyền sang dữ liệu tương ứng trong HeatWave bằng change propagation.

DML phía DB system không đợi toàn bộ bước truyền này hoàn tất. Một truy vấn HeatWave cần đọc dữ liệu vừa cập nhật có thể kích hoạt việc truyền thay đổi cần thiết theo cơ chế dịch vụ. [Change propagation](https://dev.mysql.com/doc/heatwave/en/mys-hw-change-propagation.html).

Không biến một chu kỳ truyền nội bộ được tài liệu mô tả thành SLA rằng mọi dashboard luôn phản ánh mọi thay đổi trong đúng số mili giây đó. Cần xét trạng thái bảng, chế độ load, lỗi và thời gian query chờ xử lý.

Tính đúng kết quả và tính sẵn sàng phải được đánh giá cùng nhau. Nếu bảng stale do lỗi propagation, query có thể không được offload; không nên diễn giải thành việc HeatWave luôn tự trả kết quả cũ mà không có dấu hiệu.

### 9.2. Theo dõi propagation theo toàn hệ thống và theo bảng

Ví dụ quan sát:

~~~sql
SHOW GLOBAL STATUS LIKE 'rapid_change_propagation_status';

SELECT
    i.TABLE_NAME,
    t.POOL_TYPE,
    t.LOAD_STATUS
FROM performance_schema.rpd_table_id AS i
JOIN performance_schema.rpd_tables AS t
    ON t.ID = i.ID
WHERE i.SCHEMA_NAME = 'analytics_lab'
ORDER BY i.TABLE_NAME;
~~~

`POOL_TYPE` phân biệt đường transactional có propagation với các đường snapshot tương ứng; tên giá trị thay đổi theo phiên bản. Không suy chỉ từ biến global ON rằng mọi bảng đều đang dùng propagation. [Theo dõi change propagation](https://dev.mysql.com/doc/heatwave/en/mys-hw-metadata-queries-change-propagation.html).

Nếu chủ động dùng snapshot, phải có quy trình refresh đáp ứng nghiệp vụ. “Đã load” không tự đồng nghĩa “luôn được cập nhật”.

### 9.3. Thử một thay đổi đã commit

Giữ phiên báo cáo ở autocommit phù hợp. Trong **phiên writer riêng** có quyền UPDATE, đổi đơn 1004 của bộ dữ liệu thử:

~~~sql
START TRANSACTION;

UPDATE analytics_lab.sales_order
SET status = 'CANCELLED'
WHERE order_id = 1004;

COMMIT;
~~~

Chạy lại báo cáo bằng phiên phân tích, xác nhận query vẫn theo đường engine dự kiến và kết quả phù hợp. Với dữ liệu mẫu sau thay đổi, chỉ còn hai dòng ngày 2026-11-01, tổng doanh thu **3.900.000,00**.

Ghi thời điểm commit và thời gian query hoàn tất. Nếu có lỗi hoặc không đáp ứng kỳ vọng, kiểm tra propagation, trạng thái bảng và đường xử lý thay vì thêm một lệnh sleep cố định rồi xem vấn đề đã được giải quyết.

Sau phép thử, writer có thể khôi phục dữ liệu:

~~~sql
START TRANSACTION;

UPDATE analytics_lab.sales_order
SET status = 'PAID'
WHERE order_id = 1004;

COMMIT;
~~~

Đối soát lại báo cáo về trạng thái ban đầu. Không so thời gian InnoDB và HeatWave trên hai tập dữ liệu đã thay đổi khác nhau.

### 9.4. Nguồn Lakehouse cần quy trình riêng

Nếu dữ liệu được đọc từ Object Storage qua Lakehouse, phải kiểm tra định dạng file, bảng external, chính sách truy cập và cơ chế load/refresh được hỗ trợ. Không kỳ vọng thao tác thay file nguồn có cùng cơ chế với UPDATE một bảng InnoDB.

Nếu sau này mở rộng bài toán sang Lakehouse, bổ sung riêng yêu cầu freshness và cách phát hiện dữ liệu nguồn thay đổi.

## 10. Đo hiệu năng có đường cơ sở

### 10.1. So cùng query và cùng dữ liệu

Một phép so sánh tối thiểu:

1. Chọn bộ dữ liệu đại diện đã ổn định hoặc một mốc so sánh có kiểm soát.
2. Ghi phiên bản, cluster shape/node và cấu hình DB system.
3. Chạy query với `use_secondary_engine = 'OFF'` để có đường cơ sở InnoDB.
4. Chạy cùng query với FORCED để xác nhận đường RAPID.
5. Kiểm tra kết quả tương đương trước khi so thời gian.
6. Lặp lại theo kế hoạch warm-up/đo đã thống nhất.
7. Trả session về cấu hình phù hợp sau thử.

Không thay đổi index, SQL hoặc dữ liệu giữa hai đường đo rồi quy toàn bộ chênh lệch cho engine. Nếu cần tối ưu riêng, báo rõ đó là phép so sánh phương án đã tối ưu, với các điều kiện khác nhau được ghi nhận.

### 10.2. Dữ liệu nhỏ chỉ kiểm chứng luồng

Bộ dữ liệu trong bài có vài dòng. Nó phù hợp để kiểm tra quyền, load, offload, biểu thức tiền và update sau commit.

Nó không đủ để đánh giá tốc độ scan, phân phối join, memory, data skew hoặc khả năng mở rộng.

PoC hiệu năng cần dữ liệu có kích thước, phân bố và selectivity đại diện, cùng các trường hợp như:

- Bảng fact lớn hơn nhiều lần bảng danh mục.
- Một số key xuất hiện rất nhiều.
- Dữ liệu theo thời gian tăng không đều.
- Các query có số nhóm hoặc tập kết quả lớn.
- Nhiều người dùng chạy query đồng thời.

### 10.3. Ghi cả latency, concurrency và ảnh hưởng OLTP

| Nhóm chỉ số | Điều cần ghi |
| --- | --- |
| Báo cáo | Median/p95, số mẫu, lỗi, timeout và kích thước kết quả |
| Tải | Arrival rate, concurrency, loại query và thời gian thử |
| HeatWave | CPU, memory từng node, network và query được thực thi |
| DB system | CPU/I/O, độ trễ giao dịch, tải load/propagation |
| Dữ liệu | Dung lượng, số dòng, phân bố, phiên bản/mốc dữ liệu |
| Vận hành | Thời gian load, reload, start/recovery và thao tác thủ công |

Một query giảm từ 40 giây xuống 3 giây khi chạy một mình chưa chứng minh tám người dùng đồng thời đều đạt p95 5 giây.

Tương tự, báo cáo nhanh nhưng load ban đầu làm OLTP vi phạm mục tiêu cần được xử lý bằng lịch, sizing hoặc cách triển khai.

### 10.4. Ví dụ cách đọc số liệu

Các số sau hoàn toàn giả định, chỉ minh họa cách tính:

| Query | InnoDB | HeatWave | Tỷ số thời gian InnoDB/HeatWave |
| --- | --- | --- | --- |
| Tổng hợp doanh thu lớn | 48 giây | 2,4 giây | 20 lần |
| Join và phân nhóm | 12 giây | 1,5 giây | 8 lần |
| Lookup đơn lẻ | 0,003 giây | 0,008 giây | 0,375 lần |

Hàng cuối cho thấy một đường phân tích phân tán có thể không phù hợp với lookup nhỏ. Trong vận hành có thể để optimizer chọn đường phù hợp thay vì ép mọi SELECT sang HeatWave.

Không lấy hệ số tăng tốc của query nhanh nhất làm hệ số cho toàn ứng dụng. Có thể tính thời gian toàn workload theo tần suất, nhưng vẫn phải giữ các ràng buộc p95, lỗi và concurrency riêng.

## 11. Ước lượng bộ nhớ, số node và khả năng đồng thời

### 11.1. Dung lượng InnoDB không bằng footprint HeatWave

Không lấy kích thước file dữ liệu hoặc backup rồi chia thẳng cho RAM một node.

Footprint phụ thuộc:

- Các bảng và cột thực sự được load.
- Kiểu dữ liệu, độ dài và số giá trị phân biệt.
- Compression/encoding được dùng.
- Phân phối dữ liệu giữa các node.
- Bộ nhớ cần trong quá trình load.
- Workspace của query, join, sort và aggregation.
- Concurrency và tăng trưởng.

Một schema có cột văn bản lớn nhưng không được báo cáo sử dụng có thể có phương án load khác với schema có nhiều cột cần query. Loại cột phải đi cùng kiểm tra compatibility của workload.

### 11.2. Dùng estimator làm điểm bắt đầu

OCI cung cấp chức năng ước lượng số HeatWave node theo bảng/cột và khả năng nén trong bộ nhớ. Thiếu tài nguyên có thể làm load hoặc query thất bại; cấp thừa làm tăng chi phí. [Ước lượng số HeatWave node](https://docs.oracle.com/en-us/iaas/mysql-database/doc/generating-node-count-estimate.html).

Quy trình:

1. Chọn tập dữ liệu và workload dự kiến.
2. Chạy dryrun/estimator phù hợp.
3. Xử lý lỗi kiểu dữ liệu hoặc phạm vi load.
4. Chọn cấu hình ban đầu.
5. Đo footprint và query ở concurrency mục tiêu.
6. Điều chỉnh cùng kịch bản tăng trưởng.

Ước lượng vừa đủ chứa dữ liệu chưa chứng minh concurrency mục tiêu đạt latency mong muốn. Query có thể cần thêm workspace hoặc bị giới hạn CPU/network.

### 11.3. Một mô hình ngân sách minh họa

Giả sử PoC cho bộ dữ liệu đại diện tạo ra các ước lượng:

~~~text
Dữ liệu đã load:                              600 GiB
Workspace dự trù tại concurrency mục tiêu:    180 GiB
Phần quản lý và hoạt động khác dự trù:         60 GiB
Tổng nhu cầu theo mô hình:                    840 GiB

Nếu chọn mức sử dụng mục tiêu 80%:
    Ngân sách memory hiệu dụng cần có
    = 840 / 0,80
    = 1.050 GiB
~~~

Nếu trong cùng mô hình, mỗi node đóng góp ngân sách hiệu dụng 256 GiB, phép tính sơ bộ là `ceil(1.050 / 256) = 5` node.

Đây là số giả định để minh họa, không phải shape, mức memory khả dụng hoặc tỷ lệ dự phòng chính thức của OCI. Phải kiểm tra giới hạn dịch vụ, kết quả estimator và cách phân bố memory thực; không thay báo cáo dịch vụ bằng công thức này.

Phần workspace trong ví dụ là ngân sách tổng đã đánh giá cho concurrency mục tiêu, không phải khẳng định mọi query đều cấp phát lượng memory cố định hoặc tăng tuyến tính.

### 11.4. Theo dõi từng node và data skew

Tổng memory toàn cluster có thể trông còn dư trong khi một node chịu áp lực lớn. Tương tự, trung bình CPU thấp không loại trừ một phần công việc bị giới hạn.

Data skew xuất hiện khi một số key hoặc nhóm dữ liệu chiếm tỷ trọng rất lớn. Những phép join/group by có thể tạo phân bố công việc không đồng đều.

Khi query tăng chậm dù thêm node, cần xem:

- Từng node có sử dụng tài nguyên tương tự nhau không?
- Join có sinh quá nhiều dòng trung gian không?
- Một số key có chiếm phần lớn dữ liệu không?
- Result set có quá lớn để trả về client không?
- Query có bước ít song song hoặc chi phí trao đổi lớn không?

Dùng cơ chế tối ưu và advisor được phiên bản hỗ trợ khi phù hợp. Đừng thêm node liên tục mà không có bằng chứng về nút thắt.

## 12. Giám sát cả cluster, bảng và dịch vụ phân tích

### 12.1. Các lớp giám sát

| Lớp | Tín hiệu | Câu hỏi vận hành |
| --- | --- | --- |
| Tài nguyên OCI | Trạng thái cluster/node, work request | Cluster có hoạt động hoặc đang thay đổi không? |
| Load | Tiến độ, bảng thiếu, cảnh báo/lỗi | Tất cả bảng bắt buộc đã sẵn sàng chưa? |
| Dữ liệu | Pool type, load status, propagation | Bảng có đang cập nhật theo phương án đã chọn không? |
| Query | Số query HeatWave, engine, lỗi, thời gian | Báo cáo có thực sự chạy theo đường dự kiến không? |
| Tài nguyên xử lý | CPU, memory, network từng node | Giới hạn nào đang bị chạm? |
| DB system | OLTP latency, I/O, CPU và connection | Phân tích/load/fallback có ảnh hưởng giao dịch không? |
| Ứng dụng BI | Queue, timeout, kích thước kết quả, cache | Người dùng có nhận được kết quả đúng và kịp thời không? |

OCI có các metric như `HeatWaveHealth`, `HeatWaveDataLoadProgress`, `HeatWaveStatements`, CPU và memory trong phạm vi resource phù hợp. [Theo dõi metric HeatWave](https://docs.oracle.com/en-us/iaas/mysql-database/doc/monitoring-heatwave-metrics.html).

Chọn đúng resource/dimension, đặc biệt khi xem từng node hoặc tổng hợp. Sự thay đổi metric tổng không tự chỉ ra một query cụ thể đã offload; cần kết hợp thời điểm và telemetry query.

### 12.2. Cảnh báo phải có hướng xử lý

Ví dụ cảnh báo thiết kế, không phải ngưỡng mặc định của dịch vụ:

- Bảng bắt buộc không ở trạng thái sẵn sàng ngoài cửa sổ thay đổi.
- Load không tiến triển hoặc kết thúc có bảng lỗi.
- Báo cáo vượt mục tiêu thời gian liên tục.
- Số query HeatWave giảm bất thường trong khi request phân tích vẫn tăng.
- Memory hoặc CPU từng node gần giới hạn đã xác nhận trong PoC.
- OLTP chậm sau khi nhiều báo cáo fallback.
- Cluster ở trạng thái recovery lâu hơn ngân sách dịch vụ phân tích.

Mỗi cảnh báo cần nhóm nhận, dữ liệu chẩn đoán và hành động. Cảnh báo “cluster đang reload” trong cửa sổ bảo trì có thể cần cách xử lý khác với reload ngoài kế hoạch.

### 12.3. “Healthy” không phải bằng chứng báo cáo dùng được

Một kiểm tra dịch vụ phân tích nên bao gồm một query nhỏ nhưng có ý nghĩa và xác nhận engine dự kiến, quyền, bảng cần thiết và kết quả.

Không dùng query nặng quét toàn bộ dữ liệu với tần suất quá dày làm health check. Thiết kế probe có giới hạn tải, timeout và quyền phù hợp.

Với dashboard có cache, phân biệt lỗi ở database với cache chưa refresh. Thời gian hiển thị trên UI có thể gồm query, trả dữ liệu, xử lý BI và cache.

## 13. Vận hành khi restart, resize và thay đổi schema

### 13.1. Trạng thái tài nguyên và trạng thái phục vụ

Sau start/restart hoặc thay đổi cấu hình, có thể cần thời gian khôi phục/reload trước khi tất cả bảng lại dùng được cho phân tích.

Dịch vụ có cơ chế phục hồi dữ liệu HeatWave đã load; chi tiết resize, đổi shape và yêu cầu reload phụ thuộc phiên bản/cấu hình. [Quản lý HeatWave cluster](https://docs.oracle.com/en-us/iaas/mysql-database/doc/managing-heatwave-cluster.html).

Runbook nên kiểm tra:

1. Work request hoàn tất.
2. Cluster/node có trạng thái mong muốn.
3. Các bảng bắt buộc sẵn sàng.
4. Query kiểm tra offload được.
5. Kết quả và thời gian đáp ứng mục tiêu.

Không lấy mốc “cluster started” làm mốc báo cáo chắc chắn đã phục vụ bình thường.

### 13.2. Persistence phục hồi không thay thế backup database

HeatWave có lớp lưu bền vững hỗ trợ khôi phục dữ liệu cho cluster. Nó phục vụ vòng đời accelerator; không tự thay chiến lược backup, PITR hoặc DR cho dữ liệu nghiệp vụ trong DB system.

Xóa nhầm dữ liệu nguồn hợp lệ rồi commit vẫn cần phương án recovery tương ứng. Tăng số node phân tích cũng không tự tạo standby cho database giao dịch.

Thiết kế riêng RPO/RTO cho dữ liệu nguồn và thời gian khôi phục dịch vụ phân tích. Hai mục tiêu có liên quan nhưng không phải một.

### 13.3. Resize cần đánh giá tác động

Trước resize:

- Chạy lại ước lượng với dữ liệu hiện tại.
- Kiểm tra điều kiện elastic resize hoặc normal resize của cấu hình.
- Xác nhận có cần reload, có ảnh hưởng query và thời gian dự kiến.
- Chọn khoảng tải phù hợp.
- Có tiêu chí xác nhận sau thao tác.

Không cam kết mọi resize đều không gián đoạn. Cũng không giảm số node chỉ dựa trên footprint dữ liệu nếu chưa xét workspace và concurrency.

### 13.4. DDL phải đi cùng kiểm tra offload

Khi thay schema:

1. Xác định bảng/cột liên quan query phân tích.
2. Kiểm tra DDL có được hỗ trợ với bảng đã load không.
3. Đánh giá yêu cầu unload/reload hoặc điều phối khác.
4. Sau migration, kiểm tra load status và compatibility.
5. Chạy lại query quan trọng, đối soát kết quả và EXPLAIN.

Một migration chạy thành công trên InnoDB có thể vẫn cần bước khôi phục đường phân tích. Không chỉ kiểm tra endpoint OLTP rồi kết thúc triển khai.

## 14. Chẩn đoán và xử lý các tình huống thường gặp

### 14.1. Bảng chưa load hoặc load không đủ

Bắt đầu từ summary của routine và trạng thái từng bảng. Phân biệt thiếu quyền, kiểu dữ liệu chưa phù hợp, memory không đủ và cluster chưa hoạt động.

Xử lý bảng lỗi theo nguyên nhân, rồi xác nhận lại các bảng mà query truy cập. Không chạy lặp load toàn schema liên tục nếu vấn đề là một cột hoặc một giới hạn tài nguyên.

Nếu cluster chưa hoạt động, một số luồng routine có thể chỉ thực hiện kiểm tra/dryrun theo cơ chế phiên bản. Luôn xác nhận load status cuối cùng thay vì suy từ việc CALL đã hoàn tất.

### 14.2. Query không được offload

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Không có dấu hiệu RAPID trong EXPLAIN | Session mode, bảng/cột đã load, compatibility và quyết định optimizer |
| Chạy ON thì thành công, FORCED báo lỗi | Lưu lỗi và đối chiếu điều kiện offload |
| Query nhỏ ở ON chạy trên InnoDB | Đánh giá tính phù hợp và chi phí; chưa chắc là sự cố |
| Sau thêm cột query không offload | Cột có trong secondary engine và được hỗ trợ không? |
| Client BI chạy khác MySQL client | Autocommit, SQL sinh ra, SQL mode và session settings |
| Đã nạp bảng fact nhưng join thất bại | Kiểm tra tất cả bảng dimension/query liên quan |
| Sau restart báo cáo chậm | Load/recovery đã hoàn tất hay đang fallback? |

Dùng chẩn đoán có phạm vi để sửa SQL hoặc cấu hình. Nếu SQL không được hỗ trợ, cân nhắc viết lại với cùng ngữ nghĩa và kiểm tra kết quả, hoặc giữ query đó trên đường phù hợp.

### 14.3. Bảng stale do propagation lỗi

Thu thập load status, pool type, lỗi và lịch thay đổi dữ liệu/schema. Một số trường hợp có cơ chế tự phục hồi theo dịch vụ; các trường hợp khác cần unload/reload thủ công theo hướng dẫn phiên bản.

Khi đã xác định cần reload một bảng thử:

~~~sql
ALTER TABLE analytics_lab.sales_order SECONDARY_UNLOAD;
ALTER TABLE analytics_lab.sales_order SECONDARY_LOAD;
~~~

Lệnh unload tác động bản dữ liệu dùng trong secondary engine, không phải lệnh xóa bảng InnoDB. Tuy nhiên, nó làm đường phân tích của bảng không sẵn sàng trong quá trình xử lý.

Không unload đồng loạt trên production mà chưa điều phối truy vấn, tải nguồn và yêu cầu phục vụ. Sau reload, xác nhận query, kết quả và propagation; không chỉ kiểm tra lệnh cuối không báo lỗi.

### 14.4. Fallback làm tăng tải DB system

Trong chế độ ON, một số query không offload có thể quay về đường primary. Nếu nhiều báo cáo lớn cùng fallback, DB system có thể chịu tải khác hẳn thời điểm cluster phục vụ bình thường.

Cần có chính sách ứng dụng:

- Giới hạn concurrency báo cáo.
- Đặt timeout phù hợp và quan sát engine.
- Tạm dừng hoặc xếp hàng báo cáo khi accelerator chưa sẵn sàng.
- Phân loại báo cáo được phép fallback.
- Với query bắt buộc HeatWave, đánh giá dùng FORCED trong phạm vi connection/query đã kiểm chứng và trả lỗi có kiểm soát.

Lựa chọn phải dựa trên mục tiêu dịch vụ. FORCED giúp tránh âm thầm chuyển tải, nhưng đổi lại query có thể lỗi khi accelerator không dùng được.

### 14.5. Kết quả khác nhau giữa hai lần chạy

Trước khi kết luận engine sai, kiểm tra:

- Hai lần đọc có dùng cùng mốc dữ liệu không?
- Writer có commit giữa hai phép đo không?
- Điều kiện thời gian, timezone và SQL mode có giống nhau không?
- Join có nhân bản dòng không?
- Có phép toán floating-point hoặc thứ tự kết quả không xác định không?
- Ứng dụng/BI có cache hoặc làm tròn thêm không?

Trong bài dùng DECIMAL và quy tắc lọc rõ ràng để đối soát doanh thu. Với kiểu số xấp xỉ, cần xác định dung sai theo nghiệp vụ thay vì so chuỗi hiển thị tùy ý.

## 15. Kiểm soát chi phí và tự động hóa

### 15.1. Tính đủ các thành phần

Ước tính chi phí của:

- MySQL DB system phục vụ giao dịch và tiếp nhận SQL.
- HeatWave cluster theo tài nguyên và thời gian hoạt động.
- Storage, backup, kết nối và các dịch vụ bổ sung đang dùng.
- Lakehouse storage nếu bật và có dữ liệu tương ứng.
- Công việc load, recovery, kiểm chứng và vận hành.

Không so chỉ tiền cluster với thời gian một query. Phải xét toàn workload và mức phục vụ được yêu cầu.

Theo tài liệu billing, dừng cluster dừng tính phí cho cluster và khởi động lại sẽ tiếp tục; Lakehouse storage có quy tắc riêng và có thể còn tính phí khi cluster dừng. Các thành phần DB system khác cũng phải được đánh giá riêng. [Billing HeatWave](https://docs.oracle.com/en-us/iaas/mysql-database/doc/billing.html).

### 15.2. Dừng theo lịch cần tính thời gian phục vụ lại

Nếu phân tích chỉ chạy ban ngày, có thể đánh giá lịch hoạt động phù hợp điều kiện dịch vụ. Lịch phải chừa thời gian:

~~~text
Start cluster
    -> recovery/reload
    -> kiểm tra bảng
    -> query kiểm chứng
    -> mở luồng báo cáo
~~~

Không khởi động đúng phút người dùng cần dashboard rồi kỳ vọng mọi bảng sẵn sàng ngay.

Đo cả chi phí và thời gian phục hồi trước khi quyết định dừng thường xuyên. Với workload hoạt động không theo lịch, phương án luôn sẵn sàng có thể phù hợp hơn.

### 15.3. Automation phải kiểm tra kết quả

Một workflow có thể quản lý cấu hình cluster, thực hiện load có kiểm soát, kiểm tra metadata và phát thông báo kết quả.

Các điều kiện nên được mã hóa rõ:

- Đúng DB system/schema và phiên bản mục tiêu.
- Không chạy chồng thao tác quản trị không tương thích.
- Có timeout và lưu work request/error.
- Mọi bảng bắt buộc đã sẵn sàng.
- Query kiểm chứng chạy được trên engine mong muốn.
- Có người nhận khi chưa đạt.

Một script chỉ gọi API “start” rồi báo thành công chưa hoàn thành mục tiêu phục vụ phân tích. Trạng thái cuối cần gắn với khả năng chạy báo cáo.

## 16. Thực hành và bằng chứng hoàn thành

### 16.1. Chuẩn bị

Dùng DB system thử có HeatWave cluster được hỗ trợ, quyền phù hợp, đường kết nối MySQL và dữ liệu không ảnh hưởng production.

Nếu chưa có tài nguyên, có thể hoàn thành thiết kế schema, query và kế hoạch đo. Khi đó chưa được kết luận load/offload hoặc hiệu năng đã được kiểm chứng.

### 16.2. Trình tự

1. Ghi DB system, phiên bản, cấu hình cluster và mục tiêu.
2. Tạo ba bảng mẫu và insert dữ liệu vào InnoDB.
3. Xác nhận dữ liệu nguồn đã commit.
4. Chạy Auto Parallel Load dryrun và đọc lỗi/cảnh báo.
5. Load bằng normal hoặc chọn đường manual đã hiểu rõ.
6. Xác nhận cả ba bảng có trạng thái sẵn sàng.
7. Mở phiên phân tích riêng, kiểm tra autocommit và engine mode.
8. Dùng EXPLAIN và FORCED để kiểm chứng query.
9. Đối soát các dòng báo cáo và tổng doanh thu 7.700.000,00.
10. Dùng writer riêng đổi trạng thái đơn 1004, commit và đối soát tổng 3.900.000,00.
11. Khôi phục dữ liệu mẫu và kiểm tra lại.
12. Trả session về cấu hình phù hợp sau phép thử.
13. Nếu đánh giá hiệu năng, thay bộ dữ liệu nhỏ bằng workload đại diện và chạy kế hoạch đo riêng.
14. Rà cấu hình và dọn tài nguyên thử khi không còn cần theo phạm vi quản trị được giao.

### 16.3. Bảng ghi kết quả

| Mục | Bằng chứng |
| --- | --- |
| Cluster | Cấu hình, trạng thái và work request liên quan |
| Dữ liệu | Số dòng nguồn, trạng thái commit và phạm vi schema |
| Load | Summary, cảnh báo, lỗi và trạng thái ba bảng |
| Offload | Cấu hình session, EXPLAIN và thực thi có kiểm chứng |
| Kết quả | Các nhóm doanh thu và cách tính đã đối soát |
| Cập nhật | Thay đổi đã commit và báo cáo sau thay đổi |
| Hiệu năng | Dataset đại diện, tải, số mẫu, latency và lỗi |
| Tài nguyên | CPU/memory/network, ảnh hưởng OLTP và footprint |
| Vận hành | Thời gian start/recovery/reload và cách xử lý fallback |
| Chi phí | Phạm vi tài nguyên và giả định thời gian sử dụng |

Hoàn thành luồng SQL trên bộ dữ liệu nhỏ chứng minh cách sử dụng cơ chế. Chỉ sau khi đo trên workload đại diện mới có cơ sở chọn kích thước cluster hoặc cam kết mục tiêu phục vụ.

## 17. Các nguyên tắc cần vận dụng

HeatWave tạo một đường xử lý phân tích tăng tốc cho dữ liệu được chuẩn bị phù hợp, trong khi ứng dụng tiếp tục sử dụng giao diện MySQL của DB system.

Khi triển khai, luôn nối bốn bằng chứng: **bảng sẵn sàng, query offload, kết quả đúng và hiệu năng đạt mục tiêu**. Theo dõi thêm cập nhật dữ liệu, tải OLTP, khả năng recovery và chi phí để duy trì kết quả đó trong vận hành.

Autopilot và các cơ chế tự động hỗ trợ ước lượng, load và tối ưu. Trách nhiệm của người vận hành vẫn là chọn đúng workload, xác nhận hành vi theo phiên bản và kiểm chứng mục tiêu thực tế của ứng dụng.
