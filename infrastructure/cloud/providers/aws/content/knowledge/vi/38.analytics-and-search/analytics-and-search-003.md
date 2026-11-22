# Amazon Redshift và mô hình kho dữ liệu

Amazon Redshift là dịch vụ kho dữ liệu phân tích được quản lý trên AWS. Redshift được thiết kế cho truy vấn SQL trên tập dữ liệu lớn bằng kiến trúc xử lý song song quy mô lớn (Massively Parallel Processing — MPP), lưu trữ dạng cột (columnar storage) và tối ưu hóa truy vấn theo workload. Dịch vụ phù hợp với báo cáo BI, phân tích lịch sử, dashboard, data mart và các workload phân tích cần kết hợp dữ liệu từ nhiều hệ thống.

Để sử dụng Redshift hiệu quả, cần hiểu đồng thời hai lớp:

- **Mô hình kho dữ liệu:** dữ liệu nào được lưu, grain của fact table, dimension, lịch sử thay đổi, chất lượng và lineage.
- **Kiến trúc thực thi:** dữ liệu được phân phối ra sao, truy vấn đọc bao nhiêu block, join có phải di chuyển dữ liệu giữa node không, workload được xếp hàng và cấp compute thế nào.

Một kho dữ liệu tốt không chỉ chạy truy vấn nhanh. Nó phải cung cấp số liệu nhất quán, kiểm soát quyền truy cập, hỗ trợ khôi phục, có thể mở rộng theo nhu cầu và có chi phí dự đoán được.

Bài học thuộc chương **Phân tích và tìm kiếm** trong module CLOUD_PROVIDERS_AWS. Module giúp người học khám phá hệ sinh thái AWS từ Region/AZ, IAM, VPC đến compute, storage, database, integration và serverless; qua đó rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Amazon Redshift trong kiến trúc phân tích dữ liệu và phân biệt kho dữ liệu với cơ sở dữ liệu OLTP.
- Mô tả kiến trúc MPP, leader node, compute node, slice, columnar storage và Redshift Managed Storage.
- Chọn giữa Redshift Provisioned và Redshift Serverless theo workload, yêu cầu kiểm soát và mô hình chi phí.
- Thiết kế star schema, fact table, dimension, surrogate key và slowly changing dimension.
- Chọn distribution style, sort key, compression và kiểu dữ liệu để giảm data movement và block scan.
- Nạp dữ liệu hiệu quả bằng S3, IAM role, COPY, staging table và MERGE.
- Kết hợp Redshift với S3, AWS Glue Data Catalog, Redshift Spectrum, streaming ingestion, federated query và zero-ETL integration.
- Quản lý workload, concurrency, materialized view và tối ưu SQL.
- Bảo vệ dữ liệu bằng IAM, database role, encryption, network isolation, row-level security và audit logging.
- Thiết lập backup, monitoring, cost guardrail và quy trình vận hành kho dữ liệu.

## 1. Kho dữ liệu giải quyết bài toán nào?

### 1.1. OLTP và OLAP

Cơ sở dữ liệu giao dịch và kho dữ liệu phục vụ hai kiểu truy cập khác nhau.

| Đặc điểm | OLTP | OLAP / Data Warehouse |
|---|---|---|
| Mục tiêu | Ghi nhận giao dịch nghiệp vụ | Phân tích và tổng hợp dữ liệu |
| Truy vấn | Ngắn, có điều kiện theo khóa | Quét nhiều dòng/cột, join và aggregate |
| Ghi dữ liệu | Nhiều giao dịch nhỏ, liên tục | Batch, micro-batch, CDC hoặc stream |
| Mẫu truy cập | INSERT/UPDATE/DELETE từng bản ghi | SELECT, GROUP BY, JOIN, window function |
| Mô hình | Thường chuẩn hóa để giảm dư thừa | Thường dimensional/star schema hoặc mô hình phân tích |
| Tối ưu | Transaction latency, consistency, concurrency | Throughput, scan reduction, parallelism |
| Ví dụ | Đơn hàng đang được tạo, số dư tài khoản | Doanh thu theo tháng, cohort, tồn kho lịch sử |

Không nên dùng một OLTP database để chạy mọi truy vấn phân tích nặng. Truy vấn tổng hợp trên nhiều năm dữ liệu có thể tranh chấp CPU, I/O và connection với giao dịch của ứng dụng. Ngược lại, Redshift không phải lựa chọn mặc định để xử lý từng giao dịch có latency thấp hoặc cập nhật một hàng đơn lẻ với tần suất cao.

### 1.2. Vai trò của Redshift trong kiến trúc dữ liệu

Redshift có thể là analytical warehouse trung tâm hoặc một compute warehouse đọc dữ liệu từ data lake. Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    A[Ứng dụng OLTP] --> B[CDC / Zero-ETL]
    C[Event streams] --> D[Kinesis / MSK]
    E[File và batch] --> F[Amazon S3]
    B --> G[Amazon Redshift]
    D --> G
    F --> H[Glue Data Catalog]
    H --> I[Redshift Spectrum]
    I --> G
    G --> J[BI / Dashboard]
    G --> K[Data Science / SQL]
    G --> L[Data Sharing]
~~~

Các đường nạp không thay thế lẫn nhau:

- Batch load phù hợp dữ liệu có lịch nạp và khối lượng lớn.
- CDC/zero-ETL phù hợp đồng bộ thay đổi từ operational database.
- Streaming ingestion phù hợp sự kiện cần phân tích với độ trễ thấp.
- Spectrum phù hợp dữ liệu vẫn lưu ở S3 nhưng cần truy vấn cùng dữ liệu warehouse.
- Federated query phù hợp truy cập có chọn lọc dữ liệu đang nằm trong operational database.

Hãy chọn theo latency, volume, consistency, chi phí và mức độ phức tạp vận hành.

## 2. Kiến trúc Amazon Redshift

### 2.1. MPP, leader node và compute node

Redshift phân chia công việc truy vấn thành các bước có thể thực hiện song song trên compute resources.

- **Leader node:** nhận kết nối client, phân tích SQL, lập kế hoạch thực thi, điều phối compute nodes và tổng hợp kết quả cuối.
- **Compute nodes:** lưu trữ và xử lý dữ liệu. Các node được chia thành nhiều **slice**; mỗi slice xử lý một phần dữ liệu và công việc.
- **MPP execution:** các slice thực hiện scan, filter, join, aggregate và sort song song khi query plan cho phép.
- **Columnar storage:** dữ liệu được lưu theo cột, giúp chỉ đọc các cột mà truy vấn cần thay vì đọc toàn bộ hàng.
- **Compression:** encoding theo cột giảm dung lượng lưu trữ và lượng dữ liệu phải đọc từ storage.

Tăng số compute node hoặc compute capacity có thể tăng khả năng xử lý song song, nhưng không tự động làm mọi truy vấn nhanh hơn. Một truy vấn có distribution skew, join không phù hợp hoặc đọc quá nhiều dữ liệu vẫn có thể trở thành bottleneck.

### 2.2. Redshift Managed Storage

Với kiến trúc RA3, compute và storage được tách rời:

- Compute node cung cấp CPU, memory và năng lực xử lý truy vấn.
- Redshift Managed Storage (RMS) quản lý dữ liệu bền vững, mở rộng theo dung lượng.
- Redshift tự quản lý việc đưa dữ liệu cần thiết vào cache cục bộ và lấy dữ liệu từ managed storage.
- Có thể thay đổi compute capacity mà không cần gắn cứng dung lượng dữ liệu với số node như mô hình cũ.

RA3 giúp lựa chọn compute theo hiệu năng và storage theo dung lượng. Tuy nhiên, RMS vẫn là một thành phần chi phí riêng; tăng dữ liệu lưu trữ không miễn phí chỉ vì không cần tăng số compute node.

### 2.3. Provisioned và Serverless

Redshift có hai cách cung cấp compute warehouse phổ biến.

| Tiêu chí | Provisioned | Serverless |
|---|---|---|
| Đơn vị quản lý | Cluster | Namespace và workgroup |
| Compute | Chọn node family và số node | Redshift Processing Units (RPU) |
| Scaling | Resize, elastic resize hoặc concurrency scaling tùy cấu hình | Tự động scale trong giới hạn cấu hình |
| Billing compute | Theo node-hour, kể cả thời gian cluster đang chạy | Theo RPU-hour sử dụng; không tính compute khi không có query chạy |
| Storage | RMS với RA3; node-local storage với một số node family cũ | Redshift Managed Storage, tính riêng theo GB-month |
| Kiểm soát | Kiểm soát capacity, maintenance và parameter group rõ hơn | Quản lý ít hạ tầng hơn, có base/max capacity và usage limits |
| Phù hợp | Workload ổn định, cần capacity dự đoán và tuning chuyên sâu | Workload biến động, nhóm không muốn quản lý cluster hoặc môi trường theo nhu cầu |

**Provisioned** phù hợp khi workload có mức sử dụng đều, cần kiểm soát node family, maintenance window, parameter group và khả năng dự đoán hiệu năng. Với RA3, compute và RMS được tính riêng. Cluster có thể được resize hoặc pause trong trường hợp phù hợp; khi pause, compute charge dừng nhưng storage, snapshot và các tài nguyên liên quan vẫn có thể phát sinh chi phí.

**Serverless** dùng namespace để quản lý database objects, users, encryption và các thuộc tính storage; workgroup quản lý compute, network và base capacity. Một namespace có thể được liên kết với workgroup theo thiết kế hỗ trợ của dịch vụ. Base RPU là mức compute nền, còn max capacity đặt trần scaling. Redshift tính compute theo RPU-hour trên cơ sở giây, với mức charge tối thiểu 60 giây cho một lần sử dụng tài nguyên; storage tính riêng.

Thời gian chạy query trên system tables/views cũng được tính vào mức sử dụng compute. Nếu dashboard vận hành liên tục query SYS_QUERY_HISTORY hoặc các view khác, hãy kiểm soát refresh interval và số lần chạy.

Đừng chọn Serverless chỉ vì workload thỉnh thoảng chạy. Hãy kiểm tra base capacity, thời gian query, mức scale-up, thời gian scale-down, storage và usage limit. Với workload thường trực, Provisioned có thể kinh tế hơn tùy node reservation và mức sử dụng.

### 2.4. Namespace và workgroup của Serverless

- Namespace là tập hợp database objects và thông tin liên quan đến storage/security: database, users, permissions, KMS key, datashares và recovery points.
- Workgroup là tập hợp compute resources, VPC/subnet/security group, endpoint và capacity settings.
- Có thể tách compute workload theo môi trường hoặc persona bằng nhiều workgroup, đồng thời cân nhắc dùng chung namespace nếu security boundary và quyền truy cập cho phép.
- Workgroup có usage limits để giới hạn RPU-hours theo ngày/tuần/tháng; action có thể alert, log vào system table hoặc tắt user queries.
- Max RPU capacity là trần scaling; usage limit là ngưỡng theo thời gian có action. Hai cơ chế giải quyết hai mục tiêu khác nhau.

### 2.5. Chọn mô hình triển khai

Dùng câu hỏi sau để ra quyết định:

1. Workload chạy gần như liên tục hay chỉ theo đợt?
2. Có cần kiểm soát node family, parameter group và maintenance sâu không?
3. Số query đồng thời và SLA có ổn định không?
4. Có cần tách compute warehouse theo nhóm người dùng bằng data sharing không?
5. Đội vận hành có khả năng theo dõi cluster, resize, backup và WLM không?
6. Ngân sách cần dự báo theo node-hour hay theo RPU usage?
7. Region và feature cần dùng có hỗ trợ lựa chọn đó không?

Luôn kiểm tra service availability và feature parity theo Region, node type, engine version và loại warehouse trước khi chốt kiến trúc.

## 3. Mô hình dữ liệu kho dữ liệu

### 3.1. Grain là quyết định quan trọng nhất

**Grain** mô tả chính xác một dòng trong fact table đại diện cho điều gì. Ví dụ:

- Một dòng cho một sản phẩm trong một đơn hàng.
- Một dòng cho một lần thanh toán.
- Một dòng cho tồn kho của một SKU tại một cửa hàng vào cuối ngày.
- Một dòng cho một lượt truy cập website.

Nếu grain không rõ, các nhóm có thể cộng trùng doanh thu, nhân bản số lượng hoặc join sai cardinality. Trước khi tạo bảng, hãy viết một câu xác định grain và kiểm tra bằng khóa nghiệp vụ.

Ví dụ: fact_sales có grain “mỗi dòng sản phẩm trong một đơn hàng”, không phải “một đơn hàng”. Nếu đơn hàng có ba sản phẩm, bảng sẽ có ba dòng; tổng doanh thu đơn hàng được tính bằng tổng các dòng sản phẩm.

### 3.2. Fact table và dimension table

**Fact table** lưu sự kiện hoặc số đo có thể phân tích:

- Foreign key tới các dimension.
- Measure như quantity, amount, discount, duration.
- Date/time key hoặc timestamp.
- Degenerate dimension như order number nếu cần giữ mã nghiệp vụ ngay trong fact.

**Dimension table** mô tả ngữ cảnh:

- Customer: phân khúc, khu vực, kênh.
- Product: danh mục, thương hiệu, loại sản phẩm.
- Store: cửa hàng, tỉnh/thành, vùng.
- Date: ngày, tuần, tháng, quý, năm.
- Employee hoặc campaign: người phụ trách, chương trình.

### 3.2.1. Các loại fact table

- **Transaction fact:** một dòng cho mỗi sự kiện/giao dịch ở grain đã xác định, ví dụ một dòng sản phẩm trong đơn hàng.
- **Periodic snapshot fact:** một dòng cho mỗi thực thể tại một chu kỳ cố định, ví dụ tồn kho cuối ngày hoặc số dư cuối tháng. Các measure như số dư thường là semi-additive: có thể cộng theo cửa hàng nhưng không nên cộng qua nhiều ngày.
- **Accumulating snapshot fact:** một dòng đại diện cho một quy trình có nhiều mốc, ví dụ đơn hàng từ tạo, đóng gói, giao hàng đến hoàn tất. Các cột timestamp được cập nhật khi quy trình tiến triển.

Chọn loại fact theo nghiệp vụ và cách phân tích. Không trộn nhiều grain trong một bảng nếu measure sẽ bị cộng sai; nếu cần kết hợp, hãy chuẩn hóa grain hoặc tạo mart riêng.

### 3.3. Star schema và snowflake schema

~~~mermaid
flowchart TB
    D1[dim_customer] --> F[fact_sales]
    D2[dim_product] --> F
    D3[dim_store] --> F
    D4[dim_date] --> F
    D5[dim_channel] --> F
~~~

Star schema có fact ở trung tâm và các dimension kết nối trực tiếp; dễ hiểu cho BI và thường giảm số lần join.

**Snowflake schema** chuẩn hóa dimension thành các bảng con, ví dụ product → category → department. Cách này giảm lặp dữ liệu nhưng tăng số join và có thể khiến truy vấn BI phức tạp hơn. Chọn dựa trên khả năng quản trị, chất lượng dữ liệu, độ trùng lặp và pattern truy vấn; không có một mô hình đúng cho mọi hệ thống.

### 3.4. Surrogate key và business key

Business key là mã từ hệ thống nguồn, ví dụ customer_id. Surrogate key là khóa thay thế do warehouse quản lý, ví dụ customer_key.

Lợi ích của surrogate key:

- Tách warehouse khỏi thay đổi mã định danh nguồn.
- Hỗ trợ lưu nhiều phiên bản dimension trong SCD Type 2.
- Kết hợp nhiều nguồn có cùng customer code nhưng khác namespace.
- Giúp fact table tham chiếu một phiên bản dimension cụ thể.

Không dùng business key làm surrogate key nếu cần lưu lịch sử thuộc tính dimension. Một khách hàng đổi khu vực có thể có nhiều dimension version với cùng business key nhưng surrogate key khác nhau.

### 3.5. Slowly Changing Dimensions

Các loại SCD phổ biến:

| Loại | Cách xử lý | Khi phù hợp |
|---|---|---|
| Type 0 | Giữ nguyên giá trị ban đầu | Thuộc tính bất biến hoặc không cần cập nhật |
| Type 1 | Ghi đè giá trị cũ | Sửa lỗi, không cần phân tích lịch sử |
| Type 2 | Thêm dòng mới, đóng hiệu lực dòng cũ | Cần phân tích theo thuộc tính tại thời điểm giao dịch |
| Type 3 | Lưu thêm cột giá trị trước đó | Chỉ cần một mức lịch sử hạn chế |

Ví dụ SCD Type 2:

| customer_key | customer_id | region | valid_from | valid_to | is_current |
|---:|---|---|---|---|---|
| 101 | C-1001 | North | 2025-01-01 | 2025-09-30 | false |
| 245 | C-1001 | South | 2025-10-01 | 9999-12-31 | true |

Khi customer chuyển vùng, warehouse đóng phiên bản cũ và tạo phiên bản mới. Fact mới tham chiếu customer_key 245; fact lịch sử vẫn tham chiếu customer_key 101, giữ nguyên ngữ cảnh tại thời điểm phát sinh.

Cần xử lý các trường hợp late-arriving dimension, duplicate CDC event, timezone, ngày hiệu lực và giao dịch đến trễ. Nếu không, fact có thể gắn nhầm phiên bản dimension.

### 3.6. Primary key và foreign key trong Redshift

Redshift cho phép khai báo primary key, unique và foreign key constraints, nhưng các constraint này **không được enforce** như ở nhiều OLTP database. Query optimizer có thể sử dụng thông tin constraint để tạo execution plan tốt hơn. Vì vậy:

- Chỉ khai báo constraint khi pipeline đảm bảo tính duy nhất và quan hệ tham chiếu thực sự đúng.
- Dữ liệu vi phạm constraint có thể dẫn đến kết quả truy vấn sai nếu optimizer dựa vào metadata đó.
- Dùng quy trình data quality để kiểm tra duplicate key, orphan fact và null key trước khi publish dataset.

Ví dụ kiểm tra orphan fact:

~~~sql
SELECT COUNT(*) AS orphan_rows
FROM fact_sales f
LEFT JOIN dim_customer d
  ON f.customer_key = d.customer_key
WHERE d.customer_key IS NULL;
~~~

## 4. Thiết kế bảng và phân phối dữ liệu

### 4.1. Distribution style

Redshift phân phối rows tới compute nodes/slices. Mục tiêu là phân bố workload đồng đều và giảm dữ liệu phải di chuyển khi join hoặc aggregate.

| Distribution style | Hành vi | Khi cân nhắc |
|---|---|---|
| AUTO | Redshift tự chọn và có thể đổi style khi bảng phát triển | Điểm bắt đầu khuyến nghị cho phần lớn bảng mới |
| EVEN | Phân phối round-robin | Không có join key phù hợp hoặc bảng ít tham gia join |
| KEY | Phân phối theo giá trị một cột | Hai bảng lớn thường join trên cùng key, key có phân bố đủ đều |
| ALL | Sao chép toàn bộ bảng tới mọi node | Dimension nhỏ, ít thay đổi, cần local join |

Các khái niệm cần hiểu:

- **Data redistribution:** query engine phải gửi rows sang node khác để thực hiện join/aggregate.
- **Broadcast:** một tập dữ liệu được gửi tới nhiều node.
- **Skew:** một số node nhận quá nhiều dữ liệu hoặc công việc, khiến node đó quyết định thời gian hoàn thành.
- **Collocation:** các rows có cùng join key đã nằm trên cùng node/slice, giảm data movement.

DISTSTYLE KEY có thể tối ưu join nhưng chọn key có cardinality thấp hoặc phân bố lệch sẽ gây skew. DISTSTYLE ALL tăng storage và chi phí nạp/cập nhật vì phải duy trì bản sao ở mọi node; không nên dùng cho dimension lớn hoặc thay đổi liên tục.

### 4.2. Sort key

Sort key xác định thứ tự dữ liệu trên storage. Redshift lưu metadata min/max theo block, cho phép bỏ qua block không chứa giá trị phù hợp với predicate.

- **SORTKEY AUTO:** để automatic table optimization chọn sort order theo workload.
- **Compound sort key:** phù hợp khi truy vấn thường lọc theo cột đầu tiên và các cột tiếp theo theo thứ tự.
- **Interleaved sort key:** là kỹ thuật chuyên biệt cho một số workload nhiều chiều; cần đánh giá chi phí maintenance và không nên chọn mặc định cho bảng mới.

Nếu phần lớn query chỉ phân tích dữ liệu gần đây, timestamp có thể là ứng viên sort key. Nếu query thường join hoặc lọc theo một key cụ thể, hãy đo hiệu quả bằng query plan trước khi pin sort key thủ công.

### 4.3. Automatic table optimization

Automatic table optimization có thể tự đề xuất và áp dụng distribution style, sort key và một số encoding dựa trên cách query thực tế sử dụng bảng. Bảng tạo mới không chỉ định key thường dùng AUTO.

Lợi ích:

- Giảm công việc tuning ban đầu.
- Thích nghi khi table size và query workload thay đổi.
- Giảm rủi ro chọn distribution/sort key dựa trên giả định chưa được đo.

Tuy nhiên, AUTO không thay thế việc thiết kế grain, loại dữ liệu, phân vùng S3 hoặc viết query đúng. Hãy theo dõi các thay đổi automatic và workload sau khi tối ưu; bảng có workload rất đặc thù vẫn có thể cần cấu hình thủ công.

### 4.4. Compression và kiểu dữ liệu

Redshift lưu dữ liệu dạng cột và sử dụng encoding để giảm dung lượng/scan. Khi nạp dữ liệu bằng COPY, Redshift có thể chọn compression encoding phù hợp; có thể sử dụng ENCODE AUTO cho bảng để dịch vụ quản lý encoding.

Nguyên tắc:

- Dùng kiểu dữ liệu nhỏ nhất đáp ứng miền giá trị.
- Dùng DECIMAL(p,s) cho số tiền, tránh floating point cho giá trị tài chính cần chính xác thập phân.
- Dùng DATE/TIMESTAMP/TIMESTAMPTZ phù hợp semantics thời gian và thống nhất timezone.
- Tránh VARCHAR quá rộng nếu không cần.
- Không lưu số hoặc ngày ở dạng text nếu cần so sánh, sắp xếp và tính toán thường xuyên.
- Chỉ giữ cột cần cho phân tích; loại payload raw lớn khỏi fact table nếu có thể truy xuất từ data lake.

### 4.5. Ví dụ tạo dimension và fact

Ví dụ sau dùng AUTO để Redshift có thể tự tối ưu distribution và sort:

~~~sql
CREATE TABLE dim_customer (
    customer_key BIGINT IDENTITY(1,1),
    customer_id  VARCHAR(64) NOT NULL,
    customer_name VARCHAR(256),
    region       VARCHAR(64),
    valid_from   TIMESTAMP NOT NULL,
    valid_to     TIMESTAMP NOT NULL,
    is_current   BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE fact_sales (
    sales_line_id VARCHAR(80) NOT NULL,
    order_id      VARCHAR(64) NOT NULL,
    order_ts      TIMESTAMP NOT NULL,
    customer_key  BIGINT,
    product_key   BIGINT,
    store_key     BIGINT,
    quantity      INTEGER NOT NULL,
    net_amount    DECIMAL(18,2) NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

Đây là skeleton minh họa. Hãy bổ sung cột, constraint và default theo data contract. Nếu khai báo PK/FK, phải đảm bảo pipeline giữ các quan hệ hợp lệ vì Redshift không tự enforce chúng.

## 5. Nạp dữ liệu vào Redshift

### 5.1. Các phương pháp nạp

| Phương pháp | Phù hợp với | Lưu ý |
|---|---|---|
| COPY từ S3 | Batch lớn, file CSV/JSON/Parquet/ORC | Thường là lựa chọn ưu tiên cho bulk load |
| INSERT nhiều dòng | Dataset nhỏ, thao tác kiểm soát | Tránh insert từng row trong vòng lặp |
| MERGE | Upsert từ staging/CDC | Cần xác định business key và xử lý duplicate |
| Streaming ingestion | Kinesis Data Streams hoặc MSK | Dùng materialized view để đọc stream |
| Zero-ETL | Nguồn dữ liệu hỗ trợ integration | Giảm công sức tự xây pipeline CDC, vẫn cần giám sát |
| Federated query | Dữ liệu còn ở RDS/Aurora | Truy vấn trực tiếp, chú ý latency và tải OLTP |

### 5.2. COPY từ S3

COPY đọc nhiều file song song và thường hiệu quả hơn nhiều INSERT nhỏ. Để tải tốt:

- Chia dữ liệu thành nhiều file có kích thước hợp lý, không tạo một file đơn lẻ quá lớn hoặc hàng triệu file rất nhỏ.
- Dùng file nén hoặc columnar format khi phù hợp.
- Nạp dữ liệu theo batch nhất quán và tránh nhiều job cùng ghi vào một bảng nếu không cần.
- Dùng manifest khi cần chỉ định chính xác danh sách file.
- Đưa dữ liệu vào staging table trước khi kiểm tra và merge.
- Theo dõi lỗi load và bảng system load error.

Ví dụ COPY CSV:

~~~sql
COPY staging.sales_raw
FROM 's3://company-data-lake/warehouse/sales/batch-2026-11-20/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
CSV
IGNOREHEADER 1
TIMEFORMAT 'auto'
DATEFORMAT 'auto'
COMPUPDATE PRESET
STATUPDATE ON;
~~~

Ví dụ COPY Parquet:

~~~sql
COPY staging.sales_parquet
FROM 's3://company-data-lake/warehouse/sales-parquet/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
FORMAT AS PARQUET;
~~~

Lưu ý với Parquet/ORC:

- S3 bucket phải ở cùng AWS Region với Redshift database khi dùng COPY columnar format.
- COPY columnar có tập tham số hỗ trợ giới hạn; không giả định mọi option CSV đều dùng được.
- COPY không tự động áp dụng compression encoding cho dữ liệu columnar như quy trình COPY text truyền thống.
- Kiểm tra schema compatibility, decimal precision, timestamp semantics và schema evolution trước khi nạp.

### 5.3. IAM role cho COPY và UNLOAD

Không nhúng access key/secret key dài hạn vào SQL. Gắn IAM role phù hợp với cluster hoặc workgroup và tham chiếu role trong COPY/UNLOAD.

Role load thường cần quyền tối thiểu:

- s3:ListBucket trên bucket/prefix cần đọc.
- s3:GetObject trên object cần nạp.
- kms:Decrypt nếu object được mã hóa bằng customer managed KMS key và role cần giải mã.
- glue:GetDatabase, glue:GetTable, glue:GetPartitions nếu truy cập Data Catalog theo luồng cần thiết.
- Quyền network/DNS/endpoint phù hợp nếu bật Enhanced VPC Routing.

Không cấp s3:* trên toàn bộ tài khoản chỉ để chạy một lệnh COPY. Tách role load, unload, spectrum và integration theo nhiệm vụ.

### 5.4. Staging, validation và MERGE

Một pipeline an toàn thường có các bước:

1. Nạp raw batch vào staging table.
2. Kiểm tra schema, row count, null, duplicate và giá trị ngoài miền.
3. Chuẩn hóa timezone, business key và dữ liệu lỗi.
4. Khử trùng lặp theo source event ID hoặc version/timestamp.
5. MERGE dữ liệu hợp lệ vào dimension/fact.
6. Ghi ingestion watermark, batch ID và kết quả kiểm tra.
7. Chỉ publish batch khi transaction hoàn tất.

Ví dụ MERGE:

~~~sql
MERGE INTO dim_customer AS target
USING staging.customer_delta AS source
ON target.customer_id = source.customer_id
AND target.is_current = true
WHEN MATCHED THEN
    UPDATE SET
        customer_name = source.customer_name,
        region = source.region
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        customer_name,
        region,
        valid_from,
        valid_to,
        is_current
    )
    VALUES (
        source.customer_id,
        source.customer_name,
        source.region,
        source.change_ts,
        '9999-12-31 00:00:00',
        true
    );
~~~

Ví dụ trên thể hiện Type 1 update đơn giản, không phải SCD Type 2 hoàn chỉnh. Với Type 2, cần đóng version hiện tại, insert version mới và cập nhật fact key mapping theo thời điểm nghiệp vụ. Tránh chạy lại cùng một batch làm nhân bản dòng; hãy thiết kế idempotency bằng batch ID, source event ID hoặc watermark.

### 5.5. UNLOAD dữ liệu ra S3

UNLOAD xuất kết quả query ra S3, hữu ích cho chia sẻ file, archive hoặc chuyển dữ liệu sang hệ thống khác.

~~~sql
UNLOAD ('SELECT order_date, store_key, SUM(net_amount) AS revenue
         FROM fact_sales
         GROUP BY order_date, store_key')
TO 's3://company-analytics/exports/daily-revenue/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftUnloadRole'
FORMAT AS PARQUET
ALLOWOVERWRITE;
~~~

Cân nhắc:

- Prefix output phải được quản lý theo batch và retention.
- ALLOWOVERWRITE có thể ghi đè object cùng tên; tránh dùng khi nhiều job có thể chạy đồng thời.
- Dữ liệu nhạy cảm phải được bảo vệ bằng bucket policy, KMS, access point hoặc Lake Formation tùy kiến trúc.
- UNLOAD tạo data transfer và S3 storage/request; hãy tính chi phí và dọn output tạm đúng policy.

## 6. ELT, CDC và tích hợp dữ liệu

### 6.1. ETL và ELT

- **ETL:** extract từ nguồn, transform ở hệ thống xử lý trung gian, sau đó load vào warehouse.
- **ELT:** extract và load raw/staging trước, transform bằng SQL bên trong warehouse.

ELT thường tận dụng sức mạnh MPP của Redshift, đồng thời giữ dữ liệu raw để tái xử lý. Tuy nhiên, không nên biến warehouse thành nơi chứa mọi bản sao không có retention hoặc lineage. Hãy phân biệt raw, staging, curated và mart; mỗi lớp có owner, schema, chất lượng và retention rõ ràng.

### 6.2. CDC và idempotency

CDC ghi nhận thay đổi từ nguồn, thường gồm insert/update/delete cùng metadata như transaction ID, log sequence number hoặc commit timestamp.

Một pipeline CDC tốt cần:

- Khóa sự kiện duy nhất để deduplicate.
- Xác định thứ tự sự kiện và xử lý event đến trễ.
- Xử lý delete rõ ràng, không chỉ upsert.
- Theo dõi replication lag và schema drift.
- Có khả năng replay từ checkpoint.
- Dùng staging và MERGE có tính idempotent.
- Không coi event timestamp là thứ tự tuyệt đối nếu nguồn không đảm bảo.

### 6.3. Zero-ETL integration

Zero-ETL integration kết nối nguồn dữ liệu được hỗ trợ với Redshift, thực hiện initial load và tiếp tục replicate thay đổi để dữ liệu sẵn sàng cho phân tích mà không cần tự vận hành toàn bộ pipeline ETL/CDC.

Các điểm cần nhớ:

- “Zero-ETL” không có nghĩa là không có latency, không có cấu hình hoặc không có chi phí.
- Phải cấu hình quyền, encryption, network và target warehouse.
- Theo dõi trạng thái integration, lag, lỗi schema và recovery.
- Initial load có thể tốn thời gian và tài nguyên; target Redshift vẫn cần compute và storage.
- Danh sách nguồn hỗ trợ và Region availability thay đổi theo thời gian; xác minh ma trận hỗ trợ trước khi thiết kế.

Zero-ETL phù hợp khi cần analytics trên dữ liệu operational được replicate. Nếu cần transform phức tạp, hợp nhất nhiều nguồn, kiểm soát lịch sử hoặc data quality sâu, vẫn có thể cần pipeline bổ sung.

### 6.4. Data sharing giữa warehouse

Redshift data sharing cho phép consumer đọc dữ liệu live từ producer warehouse mà không phải UNLOAD sang S3 rồi COPY thành một bản sao riêng. Có thể chia sẻ giữa Provisioned cluster và Serverless workgroup, trong cùng account hoặc cross-account; cross-Region cũng được hỗ trợ ở các Region/warehouse phù hợp.

Luồng cross-account thường gồm hai phía:

1. Producer tạo datashare, thêm database objects và cấp quyền cần thiết.
2. Producer authorize AWS account hoặc consumer theo phạm vi được hỗ trợ.
3. Consumer associate datashare vào namespace/cluster/workgroup phù hợp.
4. Consumer tạo database tham chiếu datashare và GRANT quyền cho user/role nội bộ.

Data sharing có thể hỗ trợ read và một số trường hợp write nếu producer cấp rõ quyền INSERT/UPDATE/CREATE và consumer associate theo chế độ được phép. Không mặc định mọi datashare đều có quyền ghi. Cross-Region data sharing phát sinh phí data transfer từ Region producer tới Region consumer; compute query do consumer chịu theo warehouse của consumer. Cả hai bên cần đáp ứng yêu cầu encryption và quyền truy cập. Data sharing phù hợp khi cần tách compute theo workload/đơn vị mà vẫn dùng chung dữ liệu đã quản trị.

## 7. Truy vấn data lake với Redshift Spectrum

### 7.1. Spectrum hoạt động như thế nào?

Redshift Spectrum cho phép truy vấn dữ liệu ở S3 thông qua external schema/table, thường dùng AWS Glue Data Catalog hoặc catalog tương thích. Dữ liệu vẫn nằm ở S3; Redshift không cần load toàn bộ dữ liệu đó vào bảng nội bộ.

Ví dụ tạo external schema:

~~~sql
CREATE EXTERNAL SCHEMA lake_sales
FROM DATA CATALOG
DATABASE 'analytics_catalog'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftSpectrumRole'
REGION 'ap-southeast-1'
CREATE EXTERNAL DATABASE IF NOT EXISTS;
~~~

External table có metadata mô tả schema, format và S3 location. Redshift cần quyền Glue Catalog và S3; nếu Lake Formation quản trị quyền dữ liệu, phải cấu hình quyền tương ứng cho principal/role.

### 7.2. Partition pruning và columnar format

Spectrum có thể giảm lượng dữ liệu đọc nếu layout data lake được thiết kế tốt:

- Partition theo các cột thường lọc như năm/tháng/ngày hoặc source.
- Dùng Parquet/ORC để đọc các cột cần thiết.
- Chọn compression phù hợp.
- Tránh quá nhiều file nhỏ gây overhead listing/metadata.
- Tránh SELECT * khi chỉ cần vài cột.
- Filter trực tiếp trên partition key và kiểu dữ liệu phù hợp.
- Duy trì Glue Catalog/partition metadata nhất quán.

Ví dụ query có partition filter:

~~~sql
SELECT store_id, SUM(net_amount) AS revenue
FROM lake_sales.sales_external
WHERE sales_year = 2026
  AND sales_month = 11
GROUP BY store_id;
~~~

Nếu partition key là string nhưng query ép kiểu hoặc bọc hàm không phù hợp, optimizer có thể không prune partition như mong đợi. Kiểm tra query plan và bytes scanned.

### 7.3. Chi phí Spectrum

Với Provisioned warehouse, Spectrum thường có phí dựa trên lượng dữ liệu quét, ngoài chi phí warehouse compute và S3. Với Redshift Serverless, truy vấn data lake được tính theo thời gian compute/RPU như query trên dữ liệu warehouse, không có khoản Spectrum scan riêng theo cùng cách tính provisioned.

Dù dùng mô hình nào, giảm scan vẫn có lợi: query nhanh hơn, giảm compute time và giảm tải data lake. Đọc trang pricing theo Region và loại warehouse trước khi ước lượng.

## 8. Streaming ingestion từ Kinesis và MSK

Redshift hỗ trợ streaming ingestion từ Amazon Kinesis Data Streams và Amazon Managed Streaming for Apache Kafka (MSK) thông qua materialized view.

~~~mermaid
flowchart LR
    A[Producers] --> B[Kinesis Data Streams / MSK]
    B --> C[Redshift external schema]
    C --> D[Streaming materialized view]
    D --> E[Curated tables / BI]
~~~

Ví dụ khởi tạo external schema cho Kinesis:

~~~sql
CREATE EXTERNAL SCHEMA streaming_kds
FROM KINESIS
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftStreamingRole';
~~~

Tạo materialized view đọc stream (tên stream cần thay bằng stream thực tế):

~~~sql
CREATE MATERIALIZED VIEW sales_stream_mv AS
SELECT
    approximate_arrival_timestamp,
    partition_key,
    shard_id,
    sequence_number,
    kinesis_data
FROM streaming_kds."sales-stream";

REFRESH MATERIALIZED VIEW sales_stream_mv;
~~~

Streaming ingestion cần lưu ý:

- IAM role phải được cấp quyền đọc stream và các quyền liên quan.
- Dữ liệu raw có thể là JSON/AVRO hoặc payload nhị phân; cần parse và validate trước khi transform.
- Theo dõi shard/partition, throughput, lag, duplicate và event ordering.
- Thiết kế refresh cadence theo freshness target; refresh quá dày có thể tạo overhead.
- Materialized view không thay thế data quality, deduplication và retention.
- Khi xử lý event có thể replay, pipeline downstream cần idempotent.

Dùng streaming ingestion khi muốn truy vấn event mới với độ trễ thấp hơn batch. Nếu cần fan-out, enrichment hoặc điều phối phức tạp, có thể cần Kinesis Data Analytics/Flink, Lambda hoặc pipeline khác trước khi đến Redshift.

## 9. Federated query với RDS và Aurora

Federated query cho phép Redshift truy vấn dữ liệu live ở Amazon RDS for PostgreSQL/MySQL hoặc Amazon Aurora PostgreSQL/MySQL và kết hợp với dữ liệu trong warehouse/S3.

Ví dụ external schema tới PostgreSQL:

~~~sql
CREATE EXTERNAL SCHEMA operational
FROM POSTGRES
DATABASE 'orders'
SCHEMA 'public'
URI 'orders-db.cluster-abcdefghijkl.ap-southeast-1.rds.amazonaws.com'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftFederationRole'
SECRET_ARN 'arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:redshift/federation/orders';
~~~

Query dữ liệu nguồn:

~~~sql
SELECT o.order_id, o.status, f.net_amount
FROM operational.orders o
JOIN fact_sales f
  ON f.order_id = o.order_id
WHERE o.updated_at >= CURRENT_DATE - INTERVAL '1 day';
~~~

Federated query có thể push down một phần filter/compute về database nguồn, sau đó đưa result rows về Redshift. Cần cân nhắc:

- Không dùng query phân tích nặng để quét toàn bộ OLTP database.
- Tối ưu predicate pushdown và chọn cột cần lấy.
- Đảm bảo network route, security group, enhanced VPC routing và Secrets Manager access.
- Tính latency, remote database IOPS, connection load và cross-Region transfer nếu có.
- Đây là read path; không dùng federated query như cơ chế ghi ngược vào operational database.
- Federated query không hỗ trợ concurrency scaling trong các giới hạn tài liệu hiện hành.

Nếu dữ liệu được truy vấn thường xuyên hoặc cần hiệu năng ổn định, hãy cân nhắc replicate/CDC vào warehouse thay vì truy vấn nguồn trực tiếp mỗi lần.

## 10. Materialized view và tối ưu truy vấn lặp

Materialized view lưu kết quả query đã tính trước, giúp các truy vấn sau đọc dữ liệu tổng hợp thay vì chạy lại toàn bộ join/aggregate.

Ví dụ:

~~~sql
CREATE MATERIALIZED VIEW mv_monthly_store_sales AS
SELECT
    DATE_TRUNC('month', order_ts) AS sales_month,
    store_key,
    SUM(net_amount) AS revenue,
    SUM(quantity) AS units_sold
FROM fact_sales
GROUP BY 1, 2;
~~~

Khi dữ liệu nguồn thay đổi, materialized view cần được refresh theo cơ chế được hỗ trợ. Một số query có thể incremental refresh; một số query cần full refresh tùy SQL construct và thay đổi nguồn. Kiểm tra khả năng refresh trước khi dựa vào freshness.

Redshift còn có automated materialized views (AutoMV), có thể quan sát workload và tự tạo/duy trì một số materialized view để tăng tốc query phù hợp. Không phải mọi query đều được materialize; hãy theo dõi lợi ích, storage và maintenance.

Đánh đổi:

- Query đọc nhanh hơn.
- Tốn storage cho kết quả đã tính.
- Refresh tiêu thụ compute.
- Dữ liệu có thể cũ nếu refresh cadence không phù hợp.
- Materialized view dư thừa làm tăng chi phí và độ phức tạp.

## 11. SQL và tối ưu query

### 11.1. Query plan với EXPLAIN

Dùng EXPLAIN để xem execution plan mà không chạy query:

~~~sql
EXPLAIN
SELECT
    d.region,
    DATE_TRUNC('month', f.order_ts) AS sales_month,
    SUM(f.net_amount) AS revenue
FROM fact_sales f
JOIN dim_customer d
  ON f.customer_key = d.customer_key
WHERE f.order_ts >= '2026-01-01'
GROUP BY 1, 2;
~~~

Đọc plan để tìm:

- Table scan có đọc quá nhiều block không?
- Filter có được áp dụng sớm không?
- Join có phải broadcast/redistribute dữ liệu không?
- Có nested loop không mong muốn không?
- Có sort/hash aggregate lớn hoặc spill to disk không?
- Có node nào xử lý lượng rows lớn hơn hẳn các node khác không?

Một số nhãn trong plan:

| Nhãn | Ý nghĩa khái quát |
|---|---|
| DS_DIST_NONE | Dữ liệu đã phân phối phù hợp, không cần redistribute cho join đó |
| DS_BCAST_INNER | Broadcast inner relation tới các node |
| DS_DIST_INNER | Redistribute inner relation |
| DS_DIST_OUTER | Redistribute outer relation |
| DS_DIST_BOTH | Cả hai phía phải phân phối lại |

Không đánh giá plan chỉ bằng một nhãn. Xem estimated rows, actual runtime, bytes scanned, skew và queue time để hiểu bottleneck thực.

### 11.2. Viết query hiệu quả

- Chỉ chọn cột cần thiết; tránh SELECT * trên fact lớn.
- Lọc sớm bằng predicate có thể prune block/partition.
- Không bọc sort-key column trong hàm khi có thể viết range predicate trực tiếp.
- Dùng đúng kiểu dữ liệu ở phép join, tránh cast gây tốn compute.
- Tránh join bảng fact với fact nếu có thể aggregate trước hoặc dùng dimension.
- Tránh Cartesian join ngoài ý muốn.
- Hạn chế subquery lặp có thể materialize hoặc rewrite.
- Dùng window function có partition hợp lý, tránh sort toàn bộ dữ liệu không cần thiết.
- Chọn precision decimal phù hợp, không ép kiểu liên tục trong biểu thức.
- Tránh nhiều truy vấn nhỏ thay cho một bulk operation hiệu quả.

Ví dụ predicate theo timestamp:

~~~sql
SELECT SUM(net_amount)
FROM fact_sales
WHERE order_ts >= TIMESTAMP '2026-11-01 00:00:00'
  AND order_ts <  TIMESTAMP '2026-12-01 00:00:00';
~~~

Thay vì viết DATE_PART(month, order_ts) = 11 nếu cần tận dụng sort order hoặc block pruning theo timestamp. Biểu thức hàm trên cột có thể khiến engine phải tính toán cho nhiều rows và giảm khả năng tận dụng metadata.

### 11.3. VACUUM và ANALYZE

- **VACUUM:** sắp xếp lại rows theo sort key, reclaim space sau delete và hỗ trợ duy trì chất lượng sort.
- **ANALYZE:** cập nhật statistics để optimizer ước lượng cardinality và chọn join/plan tốt hơn.
- Redshift có automatic vacuum và automatic analyze trong nhiều trường hợp; không chạy lệnh thủ công theo lịch máy móc nếu không có vấn đề cụ thể.
- Sau bulk load, update/delete lớn hoặc thay đổi dữ liệu đáng kể, kiểm tra sort state và statistics.
- Chỉ định VACUUM SORT ONLY, VACUUM DELETE ONLY hoặc VACUUM FULL theo mục tiêu; chọn sai có thể tạo workload maintenance lớn.

### 11.4. Workload Management

Workload Management (WLM) điều phối query concurrency và resource allocation.

**Automatic WLM** là điểm bắt đầu được khuyến nghị trong phần lớn workload. Redshift quyết định số query chạy đồng thời và phân bổ memory dựa trên workload.

Có thể dùng:

- Query priority để phân biệt workload critical, reporting và ad-hoc.
- Short Query Acceleration để cải thiện latency cho query ngắn đủ điều kiện.
- Query Monitoring Rules (QMR) để log, hop hoặc abort query vượt ngưỡng.
- Concurrency scaling cho queue đủ điều kiện trên Provisioned warehouse, giúp tăng khả năng xử lý query đồng thời.
- Queue routing bằng user group, role, query group hoặc rule.

Không đặt priority cao cho mọi nhóm. Nếu tất cả query đều highest, hệ thống mất ý nghĩa phân tầng. Dùng QMR để kiểm soát query chạy quá lâu, spill quá nhiều hoặc tiêu thụ tài nguyên vượt ngưỡng; thử nghiệm rule ở môi trường staging trước khi abort query production.

### 11.5. Concurrency không giống throughput

- **Concurrency** là số query/session cùng được xử lý hoặc chờ.
- **Throughput** là lượng công việc hoàn tất trong một khoảng thời gian.
- Tăng concurrency quá mức có thể làm giảm memory mỗi query, tăng spill và kéo dài latency.
- Concurrency scaling giúp mở rộng compute cho query đủ điều kiện, nhưng không thay thế query tuning hoặc mô hình dữ liệu đúng.

## 12. Bảo mật và quản trị truy cập

### 12.1. Network isolation

- Đặt Redshift trong VPC và private subnet nếu workload không cần public endpoint.
- Tắt public accessibility khi không có yêu cầu rõ ràng.
- Security group chỉ mở port kết nối từ application/BI subnet hoặc endpoint được duyệt.
- Sử dụng VPC endpoint/Redshift managed VPC endpoint khi cần private access theo kiến trúc.
- Bật Enhanced VPC Routing nếu cần kiểm soát đường đi COPY/UNLOAD tới S3 qua VPC, endpoint, route table và network policy.
- Dùng TLS cho kết nối client; cấu hình JDBC/ODBC driver và certificate policy theo yêu cầu.

Enhanced VPC Routing không tự tạo quyền S3 hoặc endpoint. Cần IAM role, endpoint policy, route, security group và bucket policy tương ứng.

### 12.2. Encryption

Redshift hỗ trợ encryption at rest cho dữ liệu và backup. Có thể dùng AWS KMS key mặc định hoặc customer managed key:

- Customer managed key cho phép kiểm soát key policy, rotation, disable và audit.
- Redshift dùng envelope encryption và key hierarchy.
- KMS key phải ở đúng Region và được Redshift service/role sử dụng hợp lệ.
- Không disable hoặc schedule deletion KMS key khi còn cluster, snapshot, integration hoặc restore cần key đó.
- Encryption in transit cần được bật/ép theo security policy.

Nếu dữ liệu đi qua S3, Glue hoặc Kinesis, encryption của Redshift không tự động bảo vệ các bản copy ở nguồn/đích; phải cấu hình SSE-KMS hoặc cơ chế encryption phù hợp cho từng service.

### 12.3. IAM authentication và database authorization

Tách hai lớp:

- **IAM authorization:** ai được gọi API quản lý cluster/workgroup, snapshot, namespace, datashare hoặc lấy temporary database credentials.
- **Database authorization:** user/role nào được CONNECT, USAGE, SELECT, INSERT, UPDATE hoặc quyền trên schema/table.

Ưu tiên temporary credentials và IAM federation/IdP thay vì password tĩnh. Redshift hỗ trợ IAM-based database authentication, có thể tích hợp SAML 2.0 IdP và driver JDBC/ODBC tương thích.

Ví dụ database RBAC:

~~~sql
CREATE ROLE analyst_readonly;

GRANT USAGE ON SCHEMA analytics TO ROLE analyst_readonly;

GRANT SELECT ON ALL TABLES IN SCHEMA analytics
TO ROLE analyst_readonly;

GRANT ROLE analyst_readonly TO analyst_user;
~~~

Để áp dụng cho bảng tạo trong tương lai, cấu hình default privileges phù hợp với owner/schema và kiểm thử bằng tài khoản thực tế. Không cấp superuser cho BI analyst hoặc ETL runtime nếu không cần.

### 12.4. Row-level security và dynamic data masking

- **Row-level security (RLS):** giới hạn những rows mà user/role được phép xem.
- **Dynamic data masking (DDM):** biến đổi giá trị nhạy cảm khi query chạy để người dùng chỉ thấy mức chi tiết được phép.
- Column-level privileges giúp giới hạn quyền đọc cột.
- Data sharing và Lake Formation cần mapping quyền rõ ràng giữa producer, consumer và external data.

Ví dụ, nhóm bán hàng khu vực Bắc chỉ xem rows thuộc khu vực Bắc; analyst có thể xem tổng doanh thu nhưng không thấy email/điện thoại khách hàng. Chính sách cần được kiểm thử cả với view, datashare, role inheritance và superuser/break-glass access.

### 12.5. Audit logging

Redshift cung cấp system tables/views để điều tra query và user activity. Có thể bật audit logging tới CloudWatch Logs hoặc S3:

- Connection log: authentication, connect/disconnect.
- User log: thay đổi user definitions.
- User activity log: hoạt động SQL; cần bật cấu hình liên quan.
- CloudTrail ghi nhận API control-plane, ví dụ tạo/đổi cluster, snapshot, parameter và resource policy.
- Lưu audit log theo retention, phân quyền và KMS/Object Lock nếu cần bằng chứng tuân thủ.

Audit logging không mặc định được bật cho mọi destination. Hãy xác minh cả database parameter và export configuration; kiểm tra rằng log thực sự đến destination.

## 13. Backup, recovery và khả năng sẵn sàng

### 13.1. Provisioned snapshots

Redshift Provisioned hỗ trợ automated và manual snapshots:

- Automated snapshots là incremental, lưu các thay đổi kể từ snapshot trước.
- Mặc định có thể tạo khoảng mỗi 8 giờ hoặc sau 5 GB thay đổi trên mỗi node, tùy điều kiện nào đến trước; khoảng tối thiểu phụ thuộc kích thước dataset.
- Automated snapshot retention mặc định là 1 ngày và có thể cấu hình. Với RA3, không thể tắt automated snapshots; retention được đặt trong khoảng 1–35 ngày. Với node type khác, đặt retention bằng 0 có thể tắt automated snapshots theo giới hạn dịch vụ.
- Manual snapshots mặc định được giữ đến khi xóa hoặc đến hết retention được đặt.
- Snapshot storage có tính phí; copy snapshot sang Region khác tạo data transfer và storage ở Region đích.

Snapshot restore tạo cluster mới; dữ liệu có thể được load dần trong khi cluster đã có thể bắt đầu phục vụ query, tùy trạng thái restore.

### 13.2. Serverless recovery points

Redshift Serverless tự tạo recovery points theo chu kỳ, thường mỗi 30 phút hoặc sau 5 GB thay đổi trên mỗi node, tùy điều kiện nào đến trước; các recovery point tự động được giữ trong 24 giờ. Ngoài ra có thể tạo snapshot thủ công để giữ lâu hơn.

Không nhầm recovery point 24 giờ với chính sách backup dài hạn. Nếu cần đáp ứng RPO/RTO và retention nhiều tháng/năm, cần kế hoạch snapshot/AWS Backup/cross-Region phù hợp.

### 13.3. Thiết kế DR

Một kế hoạch DR cần nêu rõ:

- RPO: mức mất dữ liệu tối đa chấp nhận được.
- RTO: thời gian tối đa để khôi phục dịch vụ.
- Region nguồn và Region DR.
- Snapshot copy, encryption key ở Region đích và retention.
- Cách tạo lại endpoint, security group, IAM role, secret và BI connection.
- Quy trình kiểm tra dữ liệu sau restore.
- Người phê duyệt và runbook chuyển đổi.

Đừng chỉ bật cross-Region snapshot copy rồi coi như DR đã hoàn thành. Cần thử restore định kỳ, đo thời gian thực tế và xác nhận ứng dụng/BI có thể kết nối.

## 14. Monitoring và vận hành

### 14.1. Chỉ số cần quan sát

| Nhóm | Chỉ số/nguồn quan sát | Câu hỏi vận hành |
|---|---|---|
| Compute | CPU, query duration, throughput, RPU usage | Compute có thiếu hay bị idle? |
| Storage | RMS used, disk space, snapshot size | Dữ liệu tăng nhanh ở đâu? |
| Workload | Queue length, query queue time, running queries | Query chờ vì concurrency hay query plan? |
| Query | Rows scanned, bytes scanned, spill, execution steps | Có scan quá nhiều hoặc redistribute lớn? |
| Connection | DatabaseConnections, failed connections | BI/app có tạo quá nhiều connection? |
| Load | COPY duration, load errors, batch lag | Pipeline có trễ hoặc file format lỗi? |
| Security | Failed login, privilege changes, audit log | Có truy cập bất thường hoặc quyền dư? |
| Serverless | Base/max RPU, RPU-hours, usage limits | Workload scale thế nào và có vượt budget? |

Kết hợp CloudWatch metrics, Redshift system views, CloudTrail, audit logs và query history. Metric tổng hợp cho biết triệu chứng; system view và query plan giúp tìm nguyên nhân.

### 14.2. System views và query history

Các view hữu ích tùy warehouse version:

- SYS_QUERY_HISTORY: trạng thái, thời gian, user, query type và query text theo mô hình system view mới.
- SYS_QUERY_DETAIL: chi tiết các bước query, bytes/rows và execution behavior.
- SYS_LOAD_HISTORY hoặc view load tương ứng: theo dõi COPY/load.
- SVV_TABLE_INFO: kích thước, sort key, distribution và trạng thái bảng.
- SVL_QUERY_SUMMARY và các system log views: chẩn đoán query trên provisioned cluster.
- STL_LOAD_ERRORS hoặc view load error tương ứng: xác định record/file gây lỗi.

Ví dụ lấy query gần đây (điều chỉnh time window và quyền truy cập theo môi trường):

~~~sql
SELECT
    query_id,
    status,
    start_time,
    elapsed_time,
    queue_time,
    execution_time,
    query_text
FROM SYS_QUERY_HISTORY
WHERE start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP)
ORDER BY start_time DESC
LIMIT 20;
~~~

Không dựa vào một view duy nhất cho cả Provisioned và Serverless; một số system table/view chỉ có ở loại warehouse nhất định. Kiểm tra tài liệu system views cho deployment đang dùng.

### 14.3. Redshift Advisor

Redshift Advisor có thể đề xuất cải thiện như:

- Distribution/sort key.
- Compression.
- Workload management.
- Table maintenance.
- Cluster sizing.

Đây là khuyến nghị dựa trên quan sát workload, không phải lệnh bắt buộc. Hãy đánh giá trên query thực tế, thời gian maintenance, tác động đến workload và chi phí trước khi áp dụng.

## 15. Kiểm soát chi phí

### 15.1. Các thành phần chi phí

| Thành phần | Provisioned | Serverless |
|---|---|---|
| Compute | Node-hour, tùy node type và số node | RPU-hour sử dụng |
| Storage | Redshift Managed Storage trên RA3 hoặc storage của node family tương ứng | Redshift Managed Storage theo GB-month |
| Backup | Snapshot storage, manual retention, cross-Region copy | Snapshot/recovery point theo loại và retention |
| Data lake | Spectrum scan theo pricing của provisioned | Query time/RPU như query warehouse |
| Data transfer | Cross-Region, S3/network và datashare theo luồng | Cross-Region datashare và network tương ứng |
| Extra capacity | Concurrency scaling và các feature được bật | Scale vượt base RPU, compute time |
| Integration | CDC/zero-ETL và service nguồn/đích | Tương tự, cộng compute/storage đích |

Không thể so sánh hai lựa chọn chỉ bằng giá mỗi node hoặc RPU. Hãy tính theo workload hoàn chỉnh: query time, số query, concurrency, storage growth, snapshot, data transfer và service tích hợp.

### 15.2. Cost guardrail

Với Serverless:

- Đặt base RPU phù hợp mức sử dụng thường ngày.
- Đặt max RPU để giới hạn trần scaling.
- Đặt usage limit theo ngày/tuần/tháng với action phù hợp: alert, log hoặc stop query.
- Theo dõi RPU-hours và storage GB-month.
- Tách workgroup cho workload có mức ưu tiên và budget khác nhau nếu cần.

Với Provisioned:

- Right-size node count và node type dựa trên CPU, queue, query runtime và RMS.
- Dùng reserved pricing khi workload ổn định và có cam kết dài hạn phù hợp.
- Pause cluster non-production khi không dùng nếu không ảnh hưởng SLA/maintenance.
- Xem xét concurrency scaling và elastic resize có kiểm soát.
- Xóa snapshot thủ công hết retention, cluster thử nghiệm và resource không còn owner.

### 15.3. Tối ưu storage và query cost

- Loại raw/staging data hết retention.
- Dùng compression, sort key và partition phù hợp.
- Không copy cùng dataset sang nhiều warehouse nếu có thể dùng datashare.
- Giảm Spectrum bytes scanned bằng partition pruning và Parquet/ORC.
- Giảm snapshot retention nhưng vẫn đáp ứng RPO/compliance.
- Hạn chế query dashboard chạy liên tục với refresh quá dày.
- Materialize các aggregate lặp nếu tổng compute tiết kiệm lớn hơn chi phí refresh/storage.
- Dùng workload isolation để query ad-hoc không ảnh hưởng pipeline quan trọng.

## 16. Kiến trúc tham khảo cho hệ thống bán hàng

Một doanh nghiệp bán lẻ có các nguồn:

- Aurora PostgreSQL lưu đơn hàng và khách hàng.
- DynamoDB lưu session và event trạng thái.
- Kinesis Data Streams nhận clickstream.
- S3 lưu lịch sử đơn hàng, product feed và file batch.
- BI cần dashboard doanh thu theo vùng, cửa hàng, sản phẩm và cohort.

Một thiết kế khả thi:

1. Operational database tiếp tục phục vụ transaction.
2. Dùng zero-ETL hoặc CDC cho các bảng cần phân tích từ Aurora/DynamoDB.
3. Clickstream đi vào Kinesis; Redshift streaming ingestion đọc stream cho dashboard gần real-time.
4. File batch vào S3 theo partition year/month/day.
5. Glue Data Catalog quản lý schema data lake.
6. Redshift COPY nạp curated batch vào staging/fact/dimension.
7. Spectrum truy vấn raw historical data ở S3 khi không cần load toàn bộ.
8. Materialized views tạo aggregate theo ngày/tháng.
9. Data sharing cho phép BI warehouse đọc live curated data mà không copy.
10. RLS/DDM giới hạn dữ liệu theo khu vực và vai trò.
11. CloudWatch, system views và audit logs giám sát hiệu năng, security và freshness.
12. Snapshot, cross-Region copy và restore drill bảo vệ RPO/RTO.

~~~mermaid
flowchart TB
    A[Aurora / DynamoDB] --> B[Zero-ETL / CDC]
    C[Kinesis / MSK] --> D[Streaming ingestion]
    E[Batch files] --> F[S3 raw zone]
    F --> G[Glue Catalog]
    G --> H[Spectrum]
    B --> I[Redshift staging]
    D --> I
    H --> I
    I --> J[Dimension / Fact]
    J --> K[Materialized views]
    K --> L[BI / Data Sharing]
~~~

Điểm quan trọng: không phải mọi nguồn đều cần được replicate vào Redshift. Dữ liệu raw ít dùng có thể ở S3; dữ liệu phục vụ dashboard có thể được materialize; dữ liệu operational có thể truy vấn federated trong trường hợp hẹp. Mỗi đường đi phải có freshness, ownership, security và cost model rõ ràng.

## 17. Lab: dựng mô hình kho dữ liệu bán hàng

Lab này dùng SQL minh họa, không cần chạy trên production. Hãy tạo warehouse thử nghiệm với quyền hạn tối thiểu.

### Bước 1: tạo schema

~~~sql
CREATE SCHEMA staging;
CREATE SCHEMA analytics;
~~~

### Bước 2: tạo dimension và fact

~~~sql
CREATE TABLE analytics.dim_store (
    store_key BIGINT IDENTITY(1,1),
    store_id VARCHAR(40) NOT NULL,
    store_name VARCHAR(200),
    region VARCHAR(80),
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.dim_customer (
    customer_key BIGINT IDENTITY(1,1),
    customer_id VARCHAR(64) NOT NULL,
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.dim_product (
    product_key BIGINT IDENTITY(1,1),
    product_id VARCHAR(64) NOT NULL,
    is_current BOOLEAN NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;

CREATE TABLE analytics.fact_sales (
    sales_line_id VARCHAR(80) NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    order_ts TIMESTAMP NOT NULL,
    store_key BIGINT,
    customer_key BIGINT,
    product_key BIGINT,
    quantity INTEGER NOT NULL,
    net_amount DECIMAL(18,2) NOT NULL
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

### Bước 3: nạp dữ liệu vào staging

~~~sql
CREATE TABLE staging.sales_raw (
    sales_line_id VARCHAR(80),
    order_id VARCHAR(64),
    order_ts TIMESTAMP,
    store_id VARCHAR(40),
    customer_id VARCHAR(64),
    product_id VARCHAR(64),
    quantity INTEGER,
    net_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY AUTO
ENCODE AUTO;
~~~

Sau khi gắn IAM role và chuẩn bị file S3:

~~~sql
COPY staging.sales_raw
FROM 's3://YOUR_BUCKET/sales/sample/'
IAM_ROLE 'arn:aws:iam::123456789012:role/RedshiftLoadRole'
CSV
IGNOREHEADER 1
TIMEFORMAT 'auto';
~~~

Thay YOUR_BUCKET, Region, IAM role và prefix bằng giá trị của môi trường lab. Không dùng ARN ví dụ trong production.

### Bước 4: kiểm tra chất lượng dữ liệu

Trước bước nạp fact, hãy nạp dữ liệu dimension tương ứng vào dim_store, dim_customer và dim_product. Lab chỉ tạo schema và minh họa truy vấn; không giả định các dimension tự có dữ liệu.

~~~sql
SELECT COUNT(*) AS total_rows
FROM staging.sales_raw;

SELECT COUNT(*) AS invalid_amount_rows
FROM staging.sales_raw
WHERE net_amount IS NULL OR net_amount < 0;

SELECT sales_line_id, COUNT(*) AS duplicate_count
FROM staging.sales_raw
GROUP BY sales_line_id
HAVING COUNT(*) > 1;
~~~

### Bước 5: nạp fact sau khi dimension key đã được ánh xạ

~~~sql
INSERT INTO analytics.fact_sales (
    sales_line_id,
    order_id,
    order_ts,
    store_key,
    customer_key,
    product_key,
    quantity,
    net_amount
)
SELECT
    s.sales_line_id,
    s.order_id,
    s.order_ts,
    d.store_key,
    c.customer_key,
    p.product_key,
    s.quantity,
    s.net_amount
FROM staging.sales_raw s
JOIN analytics.dim_store d
  ON d.store_id = s.store_id
 AND d.is_current = true
JOIN analytics.dim_customer c
  ON c.customer_id = s.customer_id
 AND c.is_current = true
JOIN analytics.dim_product p
  ON p.product_id = s.product_id
 AND p.is_current = true;
~~~

Trong hệ thống thực, phải bổ sung logic chọn dimension version theo thời điểm giao dịch, xử lý key không tìm thấy, deduplication và idempotent batch. Không giả định dimension hiện tại luôn đúng cho fact lịch sử.

### Bước 6: chạy báo cáo và xem plan

~~~sql
SELECT
    d.region,
    DATE_TRUNC('month', f.order_ts) AS sales_month,
    SUM(f.net_amount) AS revenue,
    SUM(f.quantity) AS units
FROM analytics.fact_sales f
JOIN analytics.dim_store d
  ON f.store_key = d.store_key
WHERE f.order_ts >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY 1, 2
ORDER BY 2, 1;
~~~

Chạy EXPLAIN trước khi chạy truy vấn lớn. Ghi lại query duration, rows scanned, redistribution, queue time và kết quả; sau đó thay đổi một yếu tố tại một thời điểm để so sánh.

## 18. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| COPY bị AccessDenied | IAM role, bucket policy, KMS hoặc endpoint policy | Kiểm tra role attached, S3 List/Get, KMS decrypt và CloudTrail |
| COPY báo lỗi format | CSV delimiter, encoding, schema hoặc Parquet type | Xem load error, file sample và schema mapping |
| Query chậm sau bulk load | Sort order, statistics hoặc distribution | Xem EXPLAIN, SVV_TABLE_INFO, ANALYZE/VACUUM khi cần |
| Query spill ra disk | Query memory thiếu, join/aggregate lớn, skew | Xem SYS_QUERY_DETAIL, WLM, predicate và intermediate rows |
| Một node chạy lâu hơn | Distribution skew hoặc data skew | Xem skew metric, distribution key và join plan |
| Queue time tăng | Concurrency, query dài, workload priority | Xem WLM queue, Auto WLM, QMR và concurrency scaling |
| Spectrum scan quá lớn | Partition pruning kém, file format hoặc query đọc quá nhiều cột | Xem partition, Parquet/ORC, EXPLAIN và bytes scanned |
| Streaming view trễ | Stream lag, refresh cadence, shard/partition throughput | Kiểm tra source metrics, IAM, refresh và consumer lag |
| Zero-ETL integration lỗi | Permission, KMS, schema change, source limits | Xem integration status, event và source/target configuration |
| Federated query timeout | Network, security group, remote database overload | Kiểm tra route, enhanced VPC routing, Secrets Manager và remote load |
| BI connection thất bại | Endpoint, TLS, IAM auth hoặc database privileges | Kiểm tra JDBC/ODBC, credential expiry, SG và GRANT |
| Serverless cost tăng bất ngờ | Base RPU, scale-up kéo dài, query/system table load | Kiểm tra RPU usage, max capacity, usage limits và query history |
| Restore không hoạt động | KMS key, Region, IAM, snapshot retention | Kiểm tra snapshot state, destination key grant và restore permission |

Không thay đổi nhiều tham số cùng lúc khi điều tra. Ghi lại baseline, thực hiện một thay đổi có giả thuyết, đo lại và rollback nếu kết quả xấu.

## 19. Những sai lầm thiết kế phổ biến

**Dùng Redshift như OLTP database.** Nhiều update nhỏ và point lookup liên tục có thể không phù hợp. Hãy giữ transaction ở database operational và đưa dữ liệu sang warehouse bằng CDC/ELT.

**Không xác định grain.** Fact table có thể đếm trùng, aggregate sai hoặc join sai. Ghi grain trước khi thiết kế schema.

**Tự chọn DISTKEY quá sớm.** Key bị skew làm một node trở thành bottleneck. Bắt đầu với AUTO, quan sát workload rồi mới pin thủ công.

**Dùng DISTSTYLE ALL cho dimension lớn.** Bản sao tăng storage và chi phí load/update. Chỉ cân nhắc với dimension nhỏ, ít thay đổi.

**Dùng sort key nhưng query không lọc theo thứ tự đó.** Sort key không có lợi nếu query pattern không tận dụng block pruning.

**Khai báo PK/FK không đúng.** Redshift không enforce constraint; optimizer có thể giả định dữ liệu hợp lệ. Chỉ khai báo khi pipeline đảm bảo.

**Nạp dữ liệu bằng từng INSERT đơn lẻ.** Dùng COPY/bulk load cho lượng lớn, staging và MERGE cho upsert.

**Bỏ qua duplicate và late-arriving event.** Replay CDC/stream có thể tạo bản ghi lặp hoặc sai dimension version. Thiết kế idempotency và watermark.

**Truy vấn federated toàn bộ operational data.** Có thể làm database nguồn quá tải và tăng latency. Chỉ lấy dữ liệu cần thiết hoặc replicate vào warehouse.

**Quét S3 bằng Spectrum mà không partition.** Query scan lớn làm tăng thời gian và chi phí. Partition, Parquet/ORC và projection.

**Tạo quá nhiều materialized view.** Refresh và storage có thể đắt hơn query gốc. Đo workload và chỉ giữ view tạo lợi ích thực.

**Không kiểm thử restore.** Snapshot có nhưng không có runbook/permission/KMS key phù hợp thì recovery có thể thất bại.

**Để Serverless scale không có guardrail.** Đặt max RPU và usage limits, theo dõi query/system table usage và budget.

## 20. Bài tập tự kiểm tra

1. Redshift khác OLTP database ở workload và kiến trúc tối ưu như thế nào?
2. Vai trò của leader node, compute node và slice là gì?
3. Columnar storage giúp giảm I/O ra sao?
4. Redshift Managed Storage tách compute và storage như thế nào trên RA3?
5. Khi nào nên chọn Provisioned thay vì Serverless?
6. Namespace và workgroup trong Serverless quản lý những gì?
7. Vì sao base RPU, max capacity và usage limit là ba khái niệm khác nhau?
8. Grain của fact table là gì? Hậu quả khi grain không rõ?
9. Fact table và dimension table khác nhau thế nào?
10. Star schema và snowflake schema có trade-off gì?
11. Surrogate key giúp SCD Type 2 như thế nào?
12. Redshift có enforce primary key và foreign key không? Điều này ảnh hưởng thiết kế ra sao?
13. DISTSTYLE AUTO, EVEN, KEY và ALL khác nhau thế nào?
14. Data skew ảnh hưởng query performance ra sao?
15. Sort key giúp block pruning như thế nào?
16. Vì sao nên bắt đầu với AUTO table optimization?
17. Tại sao COPY thường tốt hơn INSERT từng dòng?
18. IAM role cho COPY cần những quyền tối thiểu nào?
19. Staging table và MERGE giúp xử lý CDC ra sao?
20. Redshift Spectrum truy vấn S3 như thế nào và chi phí phụ thuộc điều gì?
21. Partition pruning giúp giảm scan ra sao?
22. Streaming ingestion dùng Kinesis/MSK và materialized view như thế nào?
23. Zero-ETL có nghĩa là không có latency và chi phí hay không?
24. Federated query khác CDC/replication thế nào?
25. Auto WLM, QMR và concurrency scaling giải quyết các vấn đề gì?
26. EXPLAIN giúp tìm bottleneck query như thế nào?
27. VACUUM và ANALYZE có vai trò gì?
28. IAM authentication và database RBAC bảo vệ hai lớp nào?
29. RLS và DDM khác nhau thế nào?
30. Vì sao phải thử restore snapshot và đo RTO/RPO định kỳ?

## 21. Checklist production

- [ ] Workload đã được phân loại: BI, ELT, ad-hoc, streaming hay data science.
- [ ] Đã chọn Provisioned/Serverless dựa trên workload và chi phí tổng thể.
- [ ] VPC, subnet, endpoint, security group và Enhanced VPC Routing đã được kiểm tra.
- [ ] Namespace/workgroup hoặc cluster có owner, environment tag và budget.
- [ ] Grain, fact, dimension, business key và surrogate key được định nghĩa.
- [ ] SCD policy và late-arriving data được thiết kế.
- [ ] PK/FK chỉ khai báo khi pipeline bảo đảm dữ liệu hợp lệ.
- [ ] Distribution, sort key và encoding dùng AUTO hoặc có benchmark chứng minh cấu hình thủ công.
- [ ] COPY/UNLOAD dùng IAM role least privilege và KMS policy đúng.
- [ ] Staging, deduplication, validation, MERGE và idempotency được kiểm thử.
- [ ] Spectrum partition, Glue Catalog, Lake Formation và S3 policy đúng.
- [ ] Zero-ETL/streaming/federated có freshness target và monitor lag.
- [ ] WLM, query priority, QMR và concurrency scaling phù hợp.
- [ ] EXPLAIN và query history được dùng trong performance review.
- [ ] Encryption at rest, TLS, IAM auth, RBAC, RLS/DDM và audit logging đã cấu hình.
- [ ] Snapshot, retention, cross-Region copy và KMS key recovery đã được xác nhận.
- [ ] Restore drill đã đo RTO/RPO thực tế.
- [ ] CloudWatch metrics, system views và alert có owner/runbook.
- [ ] Serverless max RPU/usage limits hoặc Provisioned resize/pause policy đã rõ.
- [ ] Cost allocation, storage growth, query usage và data transfer được review định kỳ.

## Kết luận

Amazon Redshift là nền tảng kho dữ liệu phân tích dựa trên SQL và kiến trúc MPP. Hiệu quả của Redshift phụ thuộc vào việc kết hợp đúng mô hình dữ liệu, chiến lược phân phối/sắp xếp, ingestion, workload management, security và cost governance.

Hãy bắt đầu từ grain và data contract, dùng AUTO để giảm tuning ban đầu, nạp dữ liệu bằng COPY/staging/MERGE, tối ưu query dựa trên EXPLAIN và số liệu thực tế. Kết hợp Spectrum, streaming, federated query, zero-ETL và data sharing khi mỗi mô hình phù hợp với yêu cầu latency và ownership. Cuối cùng, backup, audit, monitoring và cost guardrail phải được thiết kế cùng kiến trúc chứ không phải bổ sung sau khi warehouse đã chạy production.

## Tài liệu AWS tham khảo

- [What is Amazon Redshift?](https://docs.aws.amazon.com/redshift/latest/mgmt/welcome.html)
- [Amazon Redshift best practices](https://docs.aws.amazon.com/redshift/latest/dg/best-practices.html)
- [Amazon Redshift architecture](https://docs.aws.amazon.com/redshift/latest/dg/c_high_level_system_architecture.html)
- [Amazon Redshift Serverless workgroups and namespaces](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-workgroup-namespace.html)
- [Amazon Redshift Serverless billing](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-billing.html)
- [Amazon Redshift Serverless snapshots and recovery points](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-snapshots-recovery-points.html)
- [Setting usage limits for Amazon Redshift Serverless](https://docs.aws.amazon.com/redshift/latest/mgmt/serverless-workgroup-max-rpu.html)
- [Amazon Redshift node types](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-clusters.html)
- [Redshift Managed Storage](https://docs.aws.amazon.com/redshift/latest/dg/c_high_level_system_architecture.html)
- [Best practices for designing tables](https://docs.aws.amazon.com/redshift/latest/dg/c_designing-tables-best-practices.html)
- [Choosing a distribution style](https://docs.aws.amazon.com/redshift/latest/dg/c_choosing_dist_sort.html)
- [Choosing the best sort key](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-sort-key.html)
- [Automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/c_autonomics.html)
- [Data distribution for query optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Distributing_data.html)
- [Loading data best practices](https://docs.aws.amazon.com/redshift/latest/dg/c_loading-data-best-practices.html)
- [COPY command](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY.html)
- [COPY from Parquet and ORC](https://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-columnar.html)
- [Using IAM_ROLE with COPY and UNLOAD](https://docs.aws.amazon.com/redshift/latest/dg/copy-parameters-authorization.html)
- [MERGE command](https://docs.aws.amazon.com/redshift/latest/dg/r_MERGE.html)
- [UNLOAD command](https://docs.aws.amazon.com/redshift/latest/dg/r_UNLOAD.html)
- [Redshift Spectrum external tables](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-tables.html)
- [CREATE EXTERNAL SCHEMA](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_SCHEMA.html)
- [Streaming ingestion from Kinesis and MSK](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-streaming-ingestion.html)
- [Zero-ETL integrations](https://docs.aws.amazon.com/redshift/latest/mgmt/zero-etl-using.html)
- [Federated queries](https://docs.aws.amazon.com/redshift/latest/dg/federated-overview.html)
- [Data sharing overview](https://docs.aws.amazon.com/redshift/latest/dg/datashare-overview.html)
- [Considerations for data sharing](https://docs.aws.amazon.com/redshift/latest/dg/datashare-considerations.html)
- [Sharing data across AWS accounts](https://docs.aws.amazon.com/redshift/latest/dg/across-account.html)
- [Sharing data across AWS Regions](https://docs.aws.amazon.com/redshift/latest/dg/across-region.html)
- [Workload management](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html)
- [Automatic WLM](https://docs.aws.amazon.com/redshift/latest/dg/automatic-wlm.html)
- [Concurrency scaling](https://docs.aws.amazon.com/redshift/latest/dg/concurrency-scaling.html)
- [WLM query monitoring rules](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-wlm-query-monitoring-rules.html)
- [Query performance tuning](https://docs.aws.amazon.com/redshift/latest/dg/c-optimizing-query-performance.html)
- [SYS_QUERY_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_HISTORY.html)
- [EXPLAIN command](https://docs.aws.amazon.com/redshift/latest/dg/r_EXPLAIN.html)
- [Vacuuming tables](https://docs.aws.amazon.com/redshift/latest/dg/t_Reclaiming_storage_space202.html)
- [Database security and access control](https://docs.aws.amazon.com/redshift/latest/dg/r_Database_objects.html)
- [IAM authentication for database credentials](https://docs.aws.amazon.com/redshift/latest/mgmt/generating-user-credentials.html)
- [Database encryption](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-db-encryption.html)
- [Enhanced VPC routing](https://docs.aws.amazon.com/redshift/latest/mgmt/enhanced-vpc-routing.html)
- [Database audit logging](https://docs.aws.amazon.com/redshift/latest/mgmt/db-auditing.html)
- [Snapshots and backups](https://docs.aws.amazon.com/redshift/latest/mgmt/working-with-snapshots.html)
- [Cross-Region snapshot copy](https://docs.aws.amazon.com/redshift/latest/mgmt/cross-region-snapshot-copy.html)
- [Amazon Redshift pricing](https://aws.amazon.com/redshift/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

