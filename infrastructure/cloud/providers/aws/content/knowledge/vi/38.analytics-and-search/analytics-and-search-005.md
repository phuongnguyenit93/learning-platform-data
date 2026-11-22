# Nạp dữ liệu, phân phối bảng và tối ưu truy vấn Redshift

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Mô tả kiến trúc xử lý dữ liệu phân tán của Amazon Redshift và cách dữ liệu được nạp, lưu trữ, phân phối, sắp xếp.
- Chọn cách nạp dữ liệu bằng COPY từ Amazon S3, manifest, Parquet, ORC hoặc file dạng văn bản.
- Thiết kế IAM role, bucket policy, KMS key policy và network path cho tác vụ COPY.
- Tổ chức file đầu vào để tận dụng MPP, giảm thời gian prepare và tránh tải tuần tự.
- Phân biệt staging load, incremental load, full refresh và cách bảo đảm một batch không bị nạp trùng.
- Chọn DISTSTYLE AUTO, KEY, EVEN hoặc ALL theo kích thước bảng, join pattern và phân bố dữ liệu.
- Chọn SORTKEY AUTO, compound hoặc interleaved theo predicate và workload thực tế.
- Hiểu compression encoding, ANALYZE, VACUUM và Automatic Table Optimization.
- Đọc EXPLAIN plan, nhận diện broadcast/redistribution, scan, sort, join và aggregate tốn tài nguyên.
- Tối ưu SQL, materialized views, workload management và concurrency.
- Dùng SYS monitoring views để chẩn đoán query, load và table maintenance.
- Xây dựng quy trình nạp dữ liệu, kiểm tra chất lượng và tối ưu hiệu năng có thể lặp lại.

## 1. Amazon Redshift xử lý dữ liệu như thế nào?

Amazon Redshift là data warehouse quan hệ theo mô hình massively parallel processing (MPP). Một truy vấn được lập kế hoạch rồi chia thành các bước chạy song song trên compute nodes và slices. Dữ liệu được lưu theo cột, chia thành blocks; mỗi block có metadata như giá trị nhỏ nhất/lớn nhất để engine có thể bỏ qua các block không liên quan đến điều kiện lọc.

Một cluster provisioned có leader node điều phối truy vấn và compute nodes xử lý dữ liệu. Redshift Serverless cung cấp workgroup và namespace với compute được quản lý theo nhu cầu. Cả hai đều dùng SQL và các nguyên tắc thiết kế bảng, phân phối dữ liệu, sort key và tối ưu query tương tự; một số system views và thao tác quản trị khác nhau theo deployment type.

~~~mermaid
flowchart TD
    U["BI / SQL clients / applications"] --> L["Leader / query coordinator"]
    L --> P["Query plan"]
    P --> C1["Compute node / slices"]
    P --> C2["Compute node / slices"]
    P --> C3["Compute node / slices"]
    C1 --> R["Intermediate results"]
    C2 --> R
    C3 --> R
    R --> L
    L --> U
    S3["Amazon S3 data lake"] -->|COPY / Spectrum| C1
~~~

Hiệu năng phụ thuộc nhiều hơn vào CPU. Một truy vấn có thể chậm vì phải di chuyển dữ liệu giữa nodes, đọc quá nhiều blocks, sắp xếp lượng dữ liệu lớn, dùng statistics cũ hoặc chờ tài nguyên WLM.

Ba quyết định thiết kế liên kết chặt chẽ:

1. **Load layout:** file đầu vào và cách nạp quyết định khả năng song song của COPY.
2. **Table layout:** distribution style và sort key quyết định nơi rows được lưu và thứ tự blocks.
3. **Query shape:** filter, join, aggregation và concurrency quyết định engine phải đọc, di chuyển và tính toán bao nhiêu dữ liệu.

## 2. Chọn cách nạp dữ liệu vào Redshift

Có nhiều cách đưa dữ liệu vào Redshift. Hãy chọn theo nguồn dữ liệu, kích thước, tần suất và độ trễ cần đạt.

| Phương pháp | Khi phù hợp | Điểm cần chú ý |
|---|---|---|
| COPY từ Amazon S3 | Batch load lớn, định kỳ hoặc theo partition | Tận dụng MPP, dùng IAM role |
| COPY với manifest | Tập file chính xác, nhiều prefix hoặc nhiều bucket | Danh sách file có thể kiểm soát và kiểm toán |
| COPY Parquet/ORC | Dữ liệu columnar từ data lake | Schema và format phải tương thích; một số option COPY bị giới hạn |
| INSERT nhiều rows | Dữ liệu nhỏ hoặc tác vụ ứng dụng | Không phù hợp để thay thế bulk load lớn |
| Staging table + MERGE/INSERT | Incremental load và upsert | Cần khóa nghiệp vụ, dedup và transaction rõ |
| Amazon Redshift Spectrum | Truy vấn dữ liệu nằm trong S3 mà không nạp toàn bộ vào local table | Hiệu năng phụ thuộc file layout, partitioning và scan volume |
| Streaming ingestion | Dữ liệu liên tục từ Kinesis hoặc MSK | Khác với batch COPY; thiết kế theo freshness và stream semantics |

Đối với batch lớn, COPY từ S3 thường là lựa chọn đầu tiên vì Redshift đọc nhiều file song song. INSERT từng row qua ứng dụng tạo nhiều request và overhead, khiến compute không được tận dụng hiệu quả.

## 3. Chuẩn bị dữ liệu trước khi COPY

Một pipeline nạp tốt chuẩn hóa dữ liệu trước khi ghi vào warehouse:

1. Kiểm tra schema và version của dữ liệu.
2. Chuẩn hóa tên cột, kiểu dữ liệu, timezone và encoding.
3. Kiểm tra null, duplicate, giá trị ngoài miền và trường bắt buộc.
4. Chia file thành nhiều phần có kích thước tương đối đồng đều.
5. Ghi file vào prefix theo batch/date.
6. Tạo manifest nếu cần danh sách file chính xác.
7. Chạy COPY vào staging hoặc target table.
8. Đối soát row count, load errors và batch identifier.
9. Chạy MERGE/INSERT vào bảng phục vụ analytics.
10. Cập nhật statistics và kiểm tra query plan khi workload thay đổi đáng kể.

Nên giữ raw data bất biến trong S3 để có thể nạp lại. Không sửa file đã được một batch load tham chiếu; thay vào đó ghi một batch version mới và lưu manifest hoặc batch ID để truy vết.

## 4. COPY từ Amazon S3

COPY nhận S3 object prefix hoặc manifest file. Khi dùng prefix, Redshift tải tất cả object có key bắt đầu bằng prefix đó. Điều này tiện cho folder theo ngày, nhưng có thể nạp nhầm file backup, file tạm hoặc file của batch khác nếu prefix không được thiết kế chặt.

Ví dụ bảng đích:

~~~sql
CREATE TABLE stage_orders (
    order_id        BIGINT,
    customer_id     BIGINT,
    order_ts        TIMESTAMP,
    order_status    VARCHAR(30),
    order_amount    DECIMAL(18,2),
    source_batch_id VARCHAR(80)
)
DISTSTYLE AUTO
SORTKEY AUTO;
~~~

Ví dụ COPY file pipe-delimited:

~~~sql
COPY stage_orders (
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount,
    source_batch_id
)
FROM 's3://company-data-lake/curated/orders/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto'
DATEFORMAT 'auto'
EMPTYASNULL
BLANKSASNULL
TRUNCATECOLUMNS
STATUPDATE ON;
~~~

Ví dụ giả định file nguồn có sáu fields, trong đó field cuối là batch ID do pipeline thêm vào. Nếu source file không có batch ID, hãy nạp vào staging riêng cho batch rồi gắn ID bằng bước điều phối sau COPY; không cập nhật toàn bảng khi nhiều batch có thể chạy đồng thời. Hãy bỏ TRUNCATECOLUMNS nếu cắt chuỗi không được phép trong nghiệp vụ. Không bật ACCEPTINVCHARS hoặc MAXERROR rộng chỉ để ép load thành công; các tùy chọn đó có thể che giấu lỗi dữ liệu.

COPY append rows vào bảng. Nếu chạy lại cùng một batch, rows có thể bị nạp trùng. Hãy dùng staging table, batch ID, manifest bất biến và quy trình merge/dedup có thể chạy lại an toàn.

### 4.1 Region của S3 bucket

Theo mặc định, S3 bucket được COPY nên ở cùng Region với Redshift. Có thể chỉ định REGION khi nguồn nằm ở Region khác, nhưng cross-Region transfer làm tăng latency và có thể phát sinh data transfer charges.

Ưu tiên đặt landing bucket và Redshift trong cùng Region nếu yêu cầu kiến trúc cho phép. Nếu dữ liệu nằm khác Region vì DR hoặc data ownership, tính cả chi phí chuyển dữ liệu và thời gian nạp.

### 4.2 IAM role cho COPY

Ưu tiên IAM role gắn với Redshift cluster hoặc namespace thay vì access key tĩnh. Role cần quyền đọc đúng bucket/prefix, ví dụ:

- s3:ListBucket với điều kiện prefix phù hợp.
- s3:GetObject trên các objects cần nạp.
- s3:GetBucketLocation nếu workflow cần kiểm tra Region.
- kms:Decrypt nếu objects được mã hóa bằng customer managed KMS key.

Trust policy phải cho phép Redshift service assume role. Với SSE-KMS, IAM policy và KMS key policy đều phải cho phép role giải mã. Cross-account S3 cần thêm bucket policy và key policy ở account sở hữu dữ liệu.

Không cấp s3:* trên toàn account nếu COPY chỉ cần đọc một prefix. Không nhúng access key vào SQL, notebook hoặc source control.

## 5. Sử dụng manifest để kiểm soát tập file

Manifest là file JSON liệt kê chính xác các S3 objects cần nạp. Dùng manifest khi:

- Các file nằm ở nhiều prefix hoặc bucket.
- Chỉ một subset file được phép nạp.
- Cần bảo đảm mọi file bắt buộc đều tồn tại.
- Muốn lưu lại bằng chứng một batch đã gồm những file nào.

Ví dụ manifest:

~~~json
{
  "entries": [
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0001.csv",
      "mandatory": true
    },
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0002.csv",
      "mandatory": true
    },
    {
      "url": "s3://company-data-lake/curated/orders/batch-20261119/part-0003.csv",
      "mandatory": true
    }
  ]
}
~~~

COPY với manifest:

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/manifests/orders-20261119.manifest'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
MANIFEST
CSV
IGNOREHEADER 1;
~~~

Trường mandatory mặc định là false. Đặt true cho file bắt buộc để COPY thất bại nếu file không tồn tại. Manifest có giới hạn kích thước 100 MB; nếu danh sách lớn hơn, chia thành nhiều manifest và chạy nhiều COPY commands.

Khi dùng Parquet hoặc ORC với manifest, manifest cần metadata content_length theo định dạng AWS yêu cầu. Kiểm tra ví dụ manifest tương ứng với columnar format trước khi triển khai.

## 6. Chọn định dạng và compression

| Định dạng | Ưu điểm | Lưu ý |
|---|---|---|
| CSV | Dễ trao đổi, hỗ trợ split nếu không nén | Cần thống nhất delimiter, quote, null và encoding |
| Delimited text | Đơn giản và hiệu quả cho batch | Escape và field ordering phải rõ |
| JSON | Linh hoạt với semi-structured data | Có thể dùng JSON auto hoặc JSONPaths; thường không split tự động |
| Parquet | Columnar, schema rõ, phù hợp data lake | COPY có giới hạn option và yêu cầu tương thích schema |
| ORC | Columnar, nén tốt | Tương tự Parquet, kiểm tra hỗ trợ option |
| GZIP/BZIP2/LZOP/ZSTD | Giảm bytes lưu và truyền | File nén không phải lúc nào cũng split được |

COPY hỗ trợ nhiều kiểu compression cho text input như GZIP, BZIP2, LZOP và ZSTD. ZSTD trong tài liệu COPY được hỗ trợ khi tải từ S3. Không giả định mọi codec hoặc option áp dụng cho mọi format.

### 6.1 Kích thước và số lượng file

COPY dùng MPP để chia công việc cho slices. Với uncompressed CSV và columnar Parquet/ORC, Redshift có thể tự chia file lớn từ 128 MB thành các chunks. Parquet/ORC nhỏ hơn 128 MB không được split tự động.

JSON và CSV nén bằng các codec không thể split tự động có thể khiến mỗi file được xử lý tuần tự. AWS khuyến nghị chia các file không split được thành nhiều file gần bằng nhau, khoảng 1 MB đến 1 GB sau compression, và số file nên là bội số của số slices.

Không tạo hàng triệu file rất nhỏ. Số object quá lớn làm tăng LIST/GET overhead, thời gian inventory và độ phức tạp vận hành.

## 7. COPY Parquet và ORC

Parquet/ORC thường phù hợp khi dữ liệu được tạo bởi Spark, Glue hoặc một data lake pipeline. Ví dụ:

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/curated/orders-parquet/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
FORMAT AS PARQUET;
~~~

Các điểm cần lưu ý:

- S3 bucket phải ở cùng Region với Redshift khi COPY Parquet/ORC.
- COPY columnar không tự áp dụng compression encodings như một số text loads.
- Chỉ một tập con COPY parameters được hỗ trợ cho columnar formats.
- Schema của file và table cần tương thích về số lượng, thứ tự và kiểu dữ liệu theo quy tắc mapping.
- Nếu load thất bại, COPY command thất bại; kiểm tra lỗi schema/format trước khi retry.

Nếu source có nested fields hoặc schema evolution, hãy kiểm thử mapping bằng tập file đại diện. Với dữ liệu cần xử lý phức tạp, có thể chuẩn hóa bằng Glue/Spark thành Parquet trước khi COPY.

## 8. JSON, CSV và xử lý lỗi dữ liệu

Với JSON, COPY có thể dùng JSON auto khi tên field khớp tên cột, hoặc JSONPaths để ánh xạ cấu trúc khác. JSON auto không phải schema inference tổng quát cho mọi cấu trúc nested.

Ví dụ JSONPaths mapping:

~~~json
{
  "jsonpaths": [
    "$.order.id",
    "$.customer.id",
    "$.created_at",
    "$.status",
    "$.total"
  ]
}
~~~

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/raw/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
JSON 's3://company-data-lake/config/order-jsonpaths.json';
~~~

Thứ tự biểu thức JSONPaths phải khớp thứ tự cột đích được COPY. Nếu dùng danh sách cột trong COPY, kiểm tra thứ tự mapping tương ứng.

Với CSV, dùng CSV option khi field có dấu phẩy, quote hoặc newline theo chuẩn CSV. Không dùng DELIMITER đơn giản nếu source có delimiter xuất hiện trong giá trị mà không escape.

### 8.1 Kiểm tra trước khi nạp

COPY hỗ trợ NOLOAD để xác thực khả năng đọc/parse mà không ghi rows vào bảng. Đây là bước hữu ích trong pipeline deploy hoặc trước một batch lớn.

~~~sql
COPY stage_orders
FROM 's3://company-data-lake/curated/orders/dt=2026-11-19/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftCopyRole'
CSV
IGNOREHEADER 1
NOLOAD;
~~~

NOLOAD không thay thế kiểm tra nghiệp vụ như duplicate, referential integrity hoặc tổng tiền. Hãy kiểm tra cả schema, row count, null rate và business totals.

### 8.2 MAXERROR và dữ liệu bị bỏ qua

MAXERROR cho phép COPY tiếp tục khi gặp một số lỗi parse. Chỉ dùng khi có chính sách rõ về dữ liệu lỗi và có thể đối soát số rows bị bỏ qua. Không đặt ngưỡng lớn trong production để che lỗi upstream.

Sau khi COPY thất bại, xem SYS_LOAD_HISTORY và SYS_LOAD_ERROR_DETAIL. Với provisioned cluster, một số STL views như STL_LOAD_ERRORS cũng hữu ích; chúng không bao phủ mọi workload của Redshift Serverless hoặc concurrency scaling.

## 9. Staging table và incremental load an toàn

COPY append dữ liệu vào target table. Nếu batch bị retry, cùng một file có thể tạo duplicate. Một mẫu an toàn là:

1. Nạp batch vào staging table.
2. Gắn batch_id hoặc load_id.
3. Kiểm tra số rows và duplicate business keys.
4. Chạy transaction để merge vào target.
5. Ghi trạng thái batch đã commit.
6. Chỉ xóa staging rows sau khi đối soát hoàn tất.

Ví dụ dùng DELETE + INSERT theo batch:

~~~sql
BEGIN;

DELETE FROM fact_orders
USING stage_orders
WHERE fact_orders.order_id = stage_orders.order_id
  AND stage_orders.source_batch_id = 'batch-20261119';

INSERT INTO fact_orders (
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount
)
SELECT
    order_id,
    customer_id,
    order_ts,
    order_status,
    order_amount
FROM stage_orders
WHERE source_batch_id = 'batch-20261119';

COMMIT;
~~~

Đây là ví dụ minh họa; cần xác định semantics upsert, duplicate và batch ID phù hợp. Nếu batch có nhiều bản ghi cho cùng order_id, phải deduplicate trong staging trước khi merge.

Không truncate staging table trong lúc một batch khác đang nạp. Dùng bảng staging theo batch hoặc transaction/process orchestration để tránh hai loader xóa dữ liệu của nhau.

## 10. Nạp dữ liệu song song và điều phối batch

COPY được thiết kế để nạp nhiều file song song. Một pipeline hiệu quả thường có:

~~~mermaid
flowchart TD
    A["Source database / applications"] --> B["S3 raw landing"]
    B --> C["Validate schema and quality"]
    C --> D["Partition and split files"]
    D --> E["Manifest / batch metadata"]
    E --> F["COPY into staging"]
    F --> G["Validate counts and errors"]
    G --> H["MERGE / INSERT into warehouse"]
    H --> I["ANALYZE / query validation"]
    I --> J["BI and downstream users"]
~~~

Các nguyên tắc:

- Không chạy quá nhiều COPY đồng thời đến mức làm cạn WLM slots hoặc I/O.
- Nhóm file theo một batch có schema thống nhất.
- Dùng manifest để khóa tập file.
- Theo dõi thời gian từ start đến commit, không chỉ COPY elapsed time.
- Tách raw, staging và curated tables theo quyền và vòng đời.
- Dùng batch ID để truy vết dữ liệu từ S3 đến report.
- Đặt retry ở orchestration layer và bảo đảm batch idempotent.

## 11. Distribution style và vì sao nó quan trọng

Redshift phân phối rows của mỗi table đến compute nodes theo distribution style. Khi join hai bảng, optimizer cố gắng đặt rows liên quan trên cùng node để giảm network movement.

Bốn kiểu phân phối:

| Kiểu | Cách hoạt động | Trường hợp phù hợp |
|---|---|---|
| AUTO | Redshift tự chọn và có thể thay đổi theo kích thước/workload | Lựa chọn mặc định cho phần lớn bảng mới |
| EVEN | Chia rows vòng tròn tương đối đều | Không có join key phù hợp hoặc bảng không join thường xuyên |
| KEY | Rows có cùng giá trị DISTKEY nằm cùng slice | Bảng lớn thường join theo cùng key và key phân bố đều |
| ALL | Bản sao toàn bộ bảng trên mọi node | Một số bảng dimension nhỏ, ít thay đổi |

DISTSTYLE AUTO là default và thường là điểm bắt đầu tốt. Redshift có thể chọn ALL cho bảng nhỏ, sau đó chuyển sang KEY hoặc EVEN khi bảng lớn lên. Thay đổi được thực hiện nền với tác động tối thiểu đến query.

### 11.1 DISTSTYLE KEY

Ví dụ fact_orders và dimension_customer thường join theo customer_id:

~~~sql
CREATE TABLE fact_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_amount DECIMAL(18,2)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (customer_id, order_ts);
~~~

~~~sql
CREATE TABLE dim_customer (
    customer_id BIGINT,
    customer_name VARCHAR(200),
    customer_segment VARCHAR(40)
)
DISTSTYLE KEY
DISTKEY (customer_id)
SORTKEY (customer_id);
~~~

Nếu hai bảng được phân phối theo cùng join key, rows tương ứng có thể nằm cùng slices và giảm redistribution. Tuy nhiên, đừng chọn key chỉ vì nó xuất hiện trong nhiều câu SQL. Hãy xem cardinality và phân bố giá trị.

### 11.2 Tránh skew

Một DISTKEY có quá nhiều giá trị trùng hoặc một giá trị chiếm tỷ lệ lớn có thể dồn rows vào một số slices. Khi đó một node làm việc nhiều hơn node khác, làm giảm parallelism.

Tránh dùng các cột như status có vài giá trị, boolean, country nếu số quốc gia ít hoặc tenant_id nếu một tenant chiếm phần lớn dữ liệu, trừ khi đã đo được phân bố phù hợp.

Kiểm tra skew bằng SVV_TABLE_INFO và các system views liên quan. Nếu một slice chứa nhiều rows/bytes hơn đáng kể, xem xét đổi key hoặc quay lại AUTO/EVEN.

### 11.3 DISTSTYLE ALL

ALL sao chép toàn bộ bảng lên mọi node. Nó có thể giảm broadcast khi join với một dimension nhỏ và ổn định, nhưng làm tăng storage và chi phí load/update vì mọi node đều cần bản sao.

Không mặc định dùng ALL cho mọi dimension nhỏ. Redshift có thể broadcast một bảng nhỏ với chi phí thấp; chỉ giữ ALL khi query plan và workload chứng minh lợi ích.

## 12. Chọn distribution key theo workload

Khi đánh giá một candidate DISTKEY, hãy hỏi:

1. Bảng có tham gia join thường xuyên không?
2. Join key nào xuất hiện trong các truy vấn quan trọng?
3. Kích thước dữ liệu sau filter của hai phía là bao nhiêu?
4. Giá trị key có phân bố đều không?
5. Có null hoặc hot values chiếm tỷ trọng lớn không?
6. Có thể dùng cùng key cho nhiều bảng lớn mà không tạo skew không?
7. Lợi ích collocation có lớn hơn chi phí storage/load và thay đổi schema không?

AWS khuyến nghị ưu tiên AUTO nếu chưa có bằng chứng workload rõ. Nếu cần chọn thủ công, hãy dựa trên filtered dataset và query plan chứ không chỉ tổng kích thước bảng.

## 13. Sort key và zone maps

Sort key xác định thứ tự rows trên disk. Redshift lưu min/max metadata cho từng data block; nếu điều kiện query không giao với range của block, engine có thể bỏ qua block đó. Cơ chế này gọi là block skipping/zone maps.

Ví dụ bảng fact_orders thường lọc theo khoảng ngày:

~~~sql
CREATE TABLE fact_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_status VARCHAR(30),
    order_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY (order_ts);
~~~

Query:

~~~sql
SELECT
    DATE_TRUNC('day', order_ts) AS order_day,
    SUM(order_amount) AS revenue
FROM fact_orders
WHERE order_ts >= '2026-11-01'
  AND order_ts <  '2026-12-01'
GROUP BY 1
ORDER BY 1;
~~~

Sort key order_ts giúp Redshift bỏ qua blocks ngoài khoảng ngày nếu dữ liệu được sắp xếp tốt.

### 13.1 SORTKEY AUTO

Nếu không chỉ định sort key, Redshift dùng AUTO. Automatic Table Optimization quan sát workload và có thể chọn sort key khi có đủ query history. Đây là lựa chọn nên ưu tiên khi access pattern còn thay đổi.

### 13.2 Compound sort key

Compound key gồm nhiều cột theo thứ tự. Nó hữu ích khi query filter dùng prefix của sort key.

Ví dụ SORTKEY(order_ts, customer_id) có lợi nhất với filter theo order_ts hoặc order_ts cùng customer_id. Nếu query chỉ filter customer_id mà không có order_ts, lợi ích có thể giảm.

### 13.3 Interleaved sort key

Interleaved key phân bổ trọng số cho các cột để hỗ trợ filter theo nhiều chiều khác nhau. Tuy nhiên, interleaved có chi phí maintenance và VACUUM REINDEX cao hơn, đặc biệt khi dữ liệu liên tục được thêm vào với phân bố thay đổi.

Chỉ chọn interleaved khi workload có nhiều predicate độc lập trên các chiều và benchmark chứng minh lợi ích. Với phần lớn bảng có ingest định kỳ, compound hoặc AUTO thường dễ vận hành hơn.

## 14. Automatic Table Optimization (ATO)

ATO quan sát query patterns và metadata để tự động đề xuất/thực hiện thay đổi distribution style và sort key. Nó giảm nhu cầu chọn key thủ công khi workload chưa ổn định.

Có thể bật AUTO cho bảng hiện có:

~~~sql
ALTER TABLE fact_orders ALTER DISTSTYLE AUTO;
ALTER TABLE fact_orders ALTER SORTKEY AUTO;
~~~

Theo dõi:

- SVV_TABLE_INFO: distribution, sort key, unsorted rows và table health.
- SVV_ALTER_TABLE_RECOMMENDATIONS: đề xuất tối ưu.
- SVL_AUTO_WORKER_ACTION: lịch sử các thay đổi tự động trên provisioned clusters.
- SYS_AUTOMATIC_OPTIMIZATION: sự kiện autonomics như AutoAlterTable, VacuumSort và Analyze; chỉ superuser xem được. Một số SVV/SVL recommendations và audit views có phạm vi provisioned-only, vì vậy kiểm tra loại deployment và quyền trước khi tạo dashboard.

ATO cần workload đủ đại diện để đưa ra quyết định. Không kết luận một bảng đã được tối ưu chỉ vì AUTO được bật; quan sát recommendation, query plan và thời gian truy vấn qua nhiều chu kỳ.

Nếu tự đặt DISTKEY hoặc SORTKEY cụ thể, bảng không còn được tự động quản lý phần key đó. Chỉ chuyển khỏi AUTO khi có bằng chứng và có kế hoạch review khi workload thay đổi.

## 15. Compression encoding và column storage

Redshift lưu dữ liệu theo cột và hỗ trợ compression encoding để giảm storage I/O. Encoding phù hợp có thể giảm bytes đọc, nhưng encoding không phù hợp có thể tăng CPU giải nén hoặc làm tăng dung lượng.

Các encoding thường gặp:

| Encoding | Đặc điểm chung | Dữ liệu có thể phù hợp |
|---|---|---|
| AZ64 | Nén hiệu quả cho numeric/date/time | Số, timestamp |
| ZSTD | Nén tổng quát mạnh | Nhiều kiểu dữ liệu |
| LZO | Nén nhanh | Một số workload text |
| BYTEDICT | Dictionary theo byte | Cột text ngắn, cardinality phù hợp |
| DELTA / DELTA32K | Nén chênh lệch | Giá trị số tăng/giảm tuần tự |
| RAW | Không nén | Một số sort key hoặc dữ liệu cần truy cập đặc thù |

Ưu tiên ENCODE AUTO để Redshift chọn compression theo dữ liệu và workload. Với bảng hiện có, có thể dùng ANALYZE COMPRESSION để nhận đề xuất encoding; kết quả cần được benchmark trên representative dataset.

Không tối ưu compression bằng một mẫu dữ liệu quá nhỏ hoặc lệch phân bố. Cardinality và value distribution trong production có thể khác sample.

## 16. ANALYZE và statistics

ANALYZE cập nhật statistical metadata để optimizer ước lượng số rows và chọn join order, join method, memory và data movement phù hợp.

Redshift có automatic analyze chạy nền khi dữ liệu thay đổi. Tuy vậy, sau một bulk load lớn hoặc thay đổi đáng kể ở cột thường dùng trong filter/join, có thể cần chạy ANALYZE rõ ràng:

~~~sql
ANALYZE fact_orders;
~~~

Có thể giới hạn predicate columns để tiết kiệm tài nguyên:

~~~sql
ANALYZE fact_orders PREDICATE COLUMNS;
~~~

Statistics cũ có thể khiến optimizer nghĩ một bảng rất nhỏ trong khi thực tế lớn, chọn inner table sai hoặc chọn broadcast không phù hợp. Khi EXPLAIN có row estimates lệch nhiều so với thực tế, kiểm tra statistics trước khi đổi DISTKEY/SORTKEY.

## 17. VACUUM, unsorted rows và deleted rows

INSERT, UPDATE và DELETE có thể làm tăng unsorted region hoặc đánh dấu rows là deleted. Điều này làm scan tốn kém và có thể giảm lợi ích của sort key.

VACUUM có các mục tiêu:

- Sắp xếp lại rows theo sort key.
- Thu hồi space từ deleted rows.
- Reindex cho interleaved sort keys trong các tình huống cần thiết.

Redshift tự động sort và chạy VACUUM DELETE trong nền, vì vậy không cần chạy VACUUM FULL theo lịch cứng cho mọi bảng. Hãy quan sát table health trước khi can thiệp.

Ví dụ:

~~~sql
VACUUM SORT ONLY fact_orders;
ANALYZE fact_orders;
~~~

Lệnh trên là ví dụ cho bảng cần resort. Với bảng khác, có thể cần DELETE ONLY hoặc chế độ phù hợp. VACUUM tốn tài nguyên và có thể ảnh hưởng workload; tránh chạy hàng loạt không có dữ liệu đo.

Theo dõi unsorted percentage, deleted rows và lịch sử vacuum. Nếu COPY nạp dữ liệu theo sort key order, lượng unsorted rows có thể thấp hơn.

## 18. Quy trình tối ưu table layout

Một quy trình thực tế:

1. Xác định 5–10 query quan trọng nhất theo frequency, latency và business impact.
2. Xác định join keys và filter predicates.
3. Đo table size, skew, unsorted percentage và stats freshness.
4. Chạy EXPLAIN để xem data movement và scan.
5. Đánh giá AUTO trước.
6. Nếu cần thủ công, thử distribution/sort key trên bản sao hoặc môi trường benchmark.
7. Nạp representative data.
8. ANALYZE và chạy workload mẫu.
9. So sánh elapsed time, queue time, bytes scanned và query plan.
10. Triển khai có rollback và theo dõi sau thay đổi.

Không tối ưu một query đơn lẻ bằng cách làm chậm tất cả workload khác. Table design cần phản ánh workload mix.

## 19. Đọc EXPLAIN query plan

EXPLAIN hiển thị plan mà Redshift dự kiến dùng nhưng không thực thi query. Đọc plan từ dưới lên để hiểu dữ liệu được scan, join, aggregate và trả kết quả như thế nào.

~~~sql
EXPLAIN
SELECT
    c.customer_segment,
    SUM(o.order_amount) AS revenue
FROM fact_orders o
JOIN dim_customer c
  ON o.customer_id = c.customer_id
WHERE o.order_ts >= '2026-11-01'
  AND o.order_ts <  '2026-12-01'
GROUP BY c.customer_segment;
~~~

Các nhãn data movement thường gặp:

| Nhãn | Ý nghĩa | Nhận định |
|---|---|---|
| DS_DIST_NONE | Không cần redistribute | Thường là tốt cho join lớn |
| DS_DIST_ALL_NONE | Bảng inner đã có mặt trên mọi node | Có thể phù hợp với ALL |
| DS_BCAST_INNER | Broadcast inner table tới mọi node | Chấp nhận được nếu bảng nhỏ |
| DS_DIST_INNER | Redistribute inner table | Xem kích thước dữ liệu di chuyển |
| DS_DIST_OUTER | Redistribute outer table | Xem có thể collocate không |
| DS_DIST_BOTH | Redistribute cả hai phía | Thường là tín hiệu cần điều tra |
| DS_DIST_ALL_INNER | Đưa inner table về một slice do cách phân phối ALL của outer | Có thể làm mất parallelism |

Cost trong EXPLAIN là giá trị tương đối tích lũy trong plan, không phải thời gian thực tế hay số MB đọc. Không so sánh cost giữa hai query plans như thể đó là benchmark tuyệt đối.

EXPLAIN không cho biết mọi chi tiết runtime. Sau khi chạy query, xem SYS_QUERY_DETAIL hoặc query summary để so sánh rows/bytes thực tế với estimates.

## 20. Tối ưu SQL cho Redshift

Các nguyên tắc thường có tác động lớn:

- Chỉ chọn columns cần dùng, tránh SELECT * trên bảng rộng.
- Filter sớm để giảm rows trước join/aggregate.
- Dùng predicate trực tiếp trên sort key khi có thể.
- Tránh ép kiểu hoặc bọc hàm trên cột filter nếu làm mất khả năng block skipping.
- Dùng join predicate rõ ràng và đúng kiểu dữ liệu.
- Không cast join keys ở một phía nếu có thể chuẩn hóa schema.
- Tránh Cartesian join do thiếu join condition.
- Giảm dữ liệu trung gian trong subqueries và CTEs khi chúng không cần thiết.
- Dùng approximate aggregation hoặc pre-aggregation khi business chấp nhận.
- Không dùng DISTINCT để che duplicate do join sai.
- Kiểm tra skew và cardinality trước khi tăng parallelism.

### 20.1 Join

Join giữa các bảng lớn thường cần phân phối rows theo join key. Nếu hai bảng collocated, EXPLAIN có thể hiển thị DS_DIST_NONE. Nếu thấy DS_DIST_BOTH, xem xét AUTO hoặc key phù hợp cho workload.

Đừng tối ưu chỉ bằng cách đảo thứ tự bảng trong FROM; optimizer dùng statistics để quyết định inner/outer relation. Hãy cập nhật statistics và xem query plan.

### 20.2 Filter và block skipping

Điều kiện range trên sort key giúp Redshift loại bỏ blocks ngoài khoảng. Ví dụ:

~~~sql
WHERE order_ts >= '2026-11-01'
  AND order_ts < '2026-11-08'
~~~

Thường dễ tối ưu hơn việc áp dụng hàm lên cột rồi so sánh kết quả:

~~~sql
WHERE DATE_TRUNC('day', order_ts) = '2026-11-01'
~~~

Có thể chuyển logic thành range predicate tương đương để engine dùng zone maps tốt hơn.

### 20.3 Aggregation và window functions

Aggregation trên lượng rows lớn cần đọc và phân phối dữ liệu. Hãy lọc sớm, dùng group keys có cardinality phù hợp và xem operator HashAggregate/Sort trong plan. Window functions có thể cần sort theo PARTITION BY và ORDER BY; giảm tập rows trước khi áp dụng window nếu semantics cho phép.

## 21. Materialized views và pre-aggregation

Materialized view lưu kết quả đã tính trước từ một query trên base tables. Nó phù hợp với dashboard hoặc báo cáo chạy lặp lại, join/aggregate lớn và dữ liệu có thể chấp nhận độ trễ refresh.

Ví dụ:

~~~sql
CREATE MATERIALIZED VIEW mv_daily_sales
AUTO REFRESH YES
AS
SELECT
    DATE_TRUNC('day', order_ts) AS sales_day,
    customer_id,
    SUM(order_amount) AS total_amount,
    COUNT(*) AS order_count
FROM fact_orders
GROUP BY 1, 2;
~~~

Refresh thủ công:

~~~sql
REFRESH MATERIALIZED VIEW mv_daily_sales;
~~~

Redshift có thể incremental refresh khi định nghĩa view và thay đổi base table thuộc nhóm hỗ trợ; nếu không, nó thực hiện full refresh. Auto refresh chạy khi có tài nguyên và có thể trễ so với thời điểm base data thay đổi.

Automatic query rewrite có thể dùng materialized view còn fresh ngay cả khi SQL không tham chiếu trực tiếp view. Hãy kiểm tra EXPLAIN và SYS_MV_AQMV_HISTORY để biết query có được rewrite hay không. Nếu view stale, engine không dùng nó cho automatic rewrite để tránh trả dữ liệu cũ.

Không tạo materialized view cho mọi query. Mỗi view có chi phí storage và refresh. So sánh latency tiết kiệm được với compute dùng để refresh.

## 22. Automatic Materialized Views và result cache

Redshift có thể tự tạo và quản lý Automated Materialized Views (AutoMV) dựa trên workload. AutoMV giúp tăng tốc các query lặp lại mà không yêu cầu DBA tự định nghĩa từng aggregate view.

Result cache lưu kết quả của một số query trong memory. Khi query mới khớp cache hợp lệ và underlying objects/configuration không thay đổi, Redshift có thể trả kết quả đã cache mà không chạy lại query.

Result cache không phải substitute cho table design hoặc materialized views. Nó không giúp mọi query; ví dụ query dùng volatile function hoặc external Spectrum tables có thể không đủ điều kiện. Khi benchmark, cần biết query được cache hay thực thi thật để không kết luận sai.

## 23. Workload Management (WLM) và concurrency

WLM quản lý tài nguyên cho các query chạy đồng thời. Hai chế độ:

| Chế độ | Đặc điểm | Khi dùng |
|---|---|---|
| Automatic WLM | Redshift quyết định concurrency và memory cho query | Khuyến nghị cho phần lớn workload |
| Manual WLM | DBA tự cấu hình queues, slots và memory | Use case đặc thù cần kiểm soát sâu |

Auto WLM có thể kết hợp query priorities và Query Monitoring Rules (QMR). Manual WLM có thể tách queue theo workload như ETL, dashboard và ad-hoc analytics.

### 23.1 Tách workload

Ví dụ:
- ETL queue chạy COPY/MERGE và batch aggregation.
- Dashboard queue ưu tiên query ngắn.
- Analyst queue dành cho truy vấn ad-hoc.
- Admin queue cho maintenance có kiểm soát.

Không tăng concurrency vô hạn. Nhiều query đồng thời có thể làm memory mỗi query giảm, spill ra disk hoặc kéo dài thời gian hoàn tất.

### 23.2 Query Monitoring Rules

QMR áp dụng điều kiện theo metrics và action như log, hop hoặc abort. Ví dụ, có thể log query có nested loop hoặc abort query chạy quá lâu trong queue dashboard.

Đặt rule dựa trên workload thật. Rule quá nghiêm có thể hủy query hợp lệ; rule quá rộng làm mất khả năng bảo vệ cluster.

### 23.3 Concurrency Scaling

Concurrency Scaling có thể bổ sung compute capacity khi workload đồng thời tăng và tự giảm khi nhu cầu giảm. Nó hữu ích cho bursty concurrency, nhưng không giải quyết query plan kém hoặc một query đơn lẻ bị nghẽn do data movement.

Theo dõi query chạy trên main cluster hay concurrency scaling cluster và kiểm tra chi phí/cấu hình eligibility.

## 24. System views để theo dõi query và load

Ưu tiên SYS monitoring views khi cần truy vấn thống nhất cho provisioned và Serverless. Một số STL/SVL/STV views chỉ dành cho provisioned clusters hoặc có visibility khác nhau.

| View | Mục đích |
|---|---|
| SYS_QUERY_HISTORY | Lịch sử query, status, elapsed/queue/execution time |
| SYS_QUERY_DETAIL | Chi tiết step/metric của query |
| SYS_QUERY_EXPLAIN | Query plan theo query ID |
| SYS_LOAD_HISTORY | Lịch sử COPY/load |
| SYS_LOAD_DETAIL | Chi tiết load theo file/table |
| SYS_LOAD_ERROR_DETAIL | Chi tiết lỗi load |
| SYS_VACUUM_HISTORY | Lịch sử vacuum |
| SYS_ANALYZE_HISTORY | Lịch sử analyze |
| SYS_AUTOMATIC_OPTIMIZATION | Sự kiện task autonomics như AutoAlterTable, VacuumSort và Analyze; chỉ superuser xem được |
| SVV_TABLE_INFO | Kích thước, distribution, sort key và table health |
| SVV_ALTER_TABLE_RECOMMENDATIONS | Đề xuất ATO |

Ví dụ tìm query chậm trong 24 giờ:

~~~sql
SELECT
    query_id,
    query_type,
    status,
    elapsed_time / 1000000.0 AS elapsed_seconds,
    queue_time / 1000000.0 AS queue_seconds,
    execution_time / 1000000.0 AS execution_seconds,
    LEFT(query_text, 300) AS query_sample
FROM sys_query_history
WHERE start_time >= DATEADD(day, -1, GETDATE())
ORDER BY elapsed_time DESC
LIMIT 20;
~~~

Các trường elapsed_time, queue_time và execution_time trong SYS_QUERY_HISTORY được biểu diễn bằng microseconds. So sánh queue time với execution time để biết query chậm do chờ tài nguyên hay do chính plan.

### 24.1 Theo dõi table health

~~~sql
SELECT
    "schema",
    "table",
    size,
    pct_used,
    unsorted,
    stats_off,
    skew_rows,
    diststyle,
    sortkey1
FROM svv_table_info
ORDER BY size DESC
LIMIT 30;
~~~

Tên và visibility của columns có thể khác theo phiên bản/service. Nếu một column không có trong environment, kiểm tra schema view hiện hành trước khi dùng dashboard production.

## 25. Chẩn đoán COPY và load failures

Khi COPY lỗi, đừng chỉ retry. Tìm nguyên nhân:

- IAM role không được assume hoặc thiếu S3 permissions.
- Bucket nằm sai Region hoặc endpoint không đúng.
- KMS key policy thiếu quyền decrypt.
- Prefix trỏ tới file không mong muốn hoặc không có object.
- Manifest thiếu file mandatory.
- Schema/column order không khớp.
- CSV quotes/delimiters không cân bằng.
- Timestamp, decimal, integer hoặc UTF-8 sai định dạng.
- Parquet/ORC schema không tương thích.
- Load đồng thời vào cùng staging table gây xung đột logic.

Truy vấn lỗi load bằng SYS views:

~~~sql
SELECT
    e.query_id,
    h.table_name,
    e.start_time,
    e.file_name,
    line_number,
    column_name,
    column_type,
    error_code,
    e.error_message
FROM sys_load_error_detail e
LEFT JOIN sys_load_history h
  ON e.query_id = h.query_id
ORDER BY e.start_time DESC
LIMIT 50;
~~~

Đây là mẫu minh họa; kiểm tra column names theo SYS_LOAD_ERROR_DETAIL schema trong Region/version đang dùng. Trên provisioned cluster có thể dùng STL_LOAD_ERRORS và STL_S3CLIENT_ERROR để điều tra chi tiết tương ứng.

## 26. Kiến trúc ingestion tham khảo

Một kiến trúc batch warehouse:

~~~mermaid
flowchart TD
    A["Operational DB / SaaS / files"] --> B["S3 raw zone"]
    B --> C["Glue / ETL validation"]
    C --> D["S3 curated Parquet"]
    D --> E["Manifest / batch registry"]
    E --> F["Redshift COPY"]
    F --> G["Staging tables"]
    G --> H["Dedup / MERGE / transaction"]
    H --> I["Fact and dimension tables"]
    I --> J["ANALYZE / ATO / maintenance"]
    J --> K["BI dashboards / analysts"]
    I --> L["Materialized views"]
    L --> K
~~~

Tách raw và curated giúp giữ nguyên nguồn ban đầu, đồng thời cho phép chuẩn hóa schema và chia file trước khi load. Manifest và batch registry giúp chứng minh chính xác batch đã được nạp.

Nếu dữ liệu chỉ cần truy vấn ad-hoc và không cần local warehouse performance, cân nhắc Spectrum hoặc external tables thay vì COPY toàn bộ vào Redshift. Nếu truy vấn lặp lại và SLA chặt, local tables hoặc materialized views có thể phù hợp hơn.

## 27. Case study: tối ưu bảng fact_orders

Một doanh nghiệp thương mại điện tử có fact_orders với 2 tỷ rows. Dashboard thường lọc theo tháng, join dim_customer và group theo customer_segment. Query đang mất 90 giây.

### Triệu chứng

- EXPLAIN cho thấy DS_DIST_BOTH giữa fact_orders và dim_customer.
- Query scan nhiều blocks dù chỉ lấy một tháng.
- SVV_TABLE_INFO cho thấy unsorted percentage cao.
- stats_off lớn sau một đợt bulk load.
- WLM queue time tăng vào giờ dashboard.

### Cách điều tra

1. Xác định query frequency và p95 latency.
2. Kiểm tra sort key và distribution style của hai bảng.
3. Kiểm tra customer_id skew.
4. Chạy ANALYZE để cập nhật statistics.
5. Kiểm tra xem timestamp có phải leading sort key phù hợp không.
6. Xem liệu AUTO có recommendation cho distribution/sort key không.
7. Xem queue time và execution time để tách WLM contention khỏi query execution.

### Hành động

- Bắt đầu với DISTSTYLE AUTO và SORTKEY AUTO trên bản thử nghiệm.
- Nếu workload chứng minh customer_id là key join ổn định, thử KEY distribution cùng customer_id cho các bảng lớn liên quan.
- Dùng order_ts làm sort key dẫn đầu nếu truy vấn range theo thời gian chiếm ưu thế và AUTO chưa chọn phù hợp.
- Nạp dữ liệu theo thứ tự sort key khi pipeline có thể kiểm soát.
- ANALYZE sau bulk load lớn.
- Chỉ chạy VACUUM khi unsorted/deleted rows cho thấy cần thiết.
- Tạo materialized view cho dashboard aggregation nếu refresh latency đáp ứng SLA.
- Tách workload dashboard và ETL bằng Auto WLM priorities/QMR.

### Kết quả cần đo

- Bytes scanned và rows scanned.
- Số blocks bị scan.
- DS_DIST_NONE/BCAST/DIST_BOTH trong EXPLAIN.
- p50/p95/p99 elapsed time.
- Queue time và execution time.
- Refresh time và staleness của materialized view.
- Chi phí compute và storage sau thay đổi.

Không đặt mục tiêu chỉ là giảm một query xuống vài giây. Cần bảo đảm ETL vẫn hoàn thành đúng lịch và workload ad-hoc không bị suy giảm.

## 28. Lab: nạp dữ liệu từ S3 và đọc query plan

Lab dùng Redshift sandbox hoặc environment học tập. Không chạy trên production warehouse. Thay bucket, Region, account ID và role ARN bằng tài nguyên đã được cấp.

### Bước 1: tạo bảng

~~~sql
CREATE TABLE lab_orders (
    order_id BIGINT,
    customer_id BIGINT,
    order_ts TIMESTAMP,
    order_status VARCHAR(30),
    order_amount DECIMAL(18,2)
)
DISTSTYLE AUTO
SORTKEY AUTO;
~~~

### Bước 2: tạo file mẫu

File CSV pipe-delimited, không có header:

~~~text
1001|501|2026-11-19 10:00:00|PAID|125000.00
1002|502|2026-11-19 10:05:00|PENDING|45000.00
1003|501|2026-11-19 10:10:00|PAID|89000.00
1004|503|2026-11-19 10:15:00|CANCELLED|120000.00
~~~

Upload file vào prefix S3 được cấp cho lab. Không dùng bucket production.

### Bước 3: chạy COPY NOLOAD

~~~sql
COPY lab_orders
FROM 's3://company-redshift-lab/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftLabCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto'
NOLOAD;
~~~

Nếu NOLOAD báo lỗi, kiểm tra IAM role, prefix, schema và delimiter trước khi nạp thật.

### Bước 4: nạp dữ liệu

~~~sql
COPY lab_orders
FROM 's3://company-redshift-lab/orders/'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftLabCopyRole'
REGION 'ap-southeast-1'
DELIMITER '|'
TIMEFORMAT 'auto';
~~~

### Bước 5: xác minh rows

~~~sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT order_id) AS unique_orders,
    SUM(order_amount) AS total_amount,
    MIN(order_ts) AS first_order,
    MAX(order_ts) AS last_order
FROM lab_orders;
~~~

Nếu chạy COPY lần thứ hai, kiểm tra duplicate. Điều này minh họa COPY append rows và lý do cần batch idempotency.

### Bước 6: đọc EXPLAIN

~~~sql
EXPLAIN
SELECT
    customer_id,
    SUM(order_amount) AS total_amount
FROM lab_orders
WHERE order_ts >= '2026-11-19'
GROUP BY customer_id;
~~~

Thử thay đổi table design trong một bảng lab khác, chạy ANALYZE và so sánh query plan. Không suy luận hiệu năng từ cost estimate đơn lẻ; chạy query và đo elapsed time/bytes scanned.

### Bước 7: kiểm tra system views

~~~sql
SELECT *
FROM sys_query_history
ORDER BY start_time DESC
LIMIT 10;
~~~

~~~sql
SELECT
    "schema",
    "table",
    size,
    unsorted,
    stats_off,
    diststyle,
    sortkey1
FROM svv_table_info
WHERE "table" = 'lab_orders';
~~~

### Bước 8: cleanup

~~~sql
DROP TABLE IF EXISTS lab_orders;
~~~

Xóa S3 lab objects, manifest và IAM role chỉ khi chắc chắn chúng không được lab khác sử dụng. Không xóa bucket dùng chung.

## 29. Troubleshooting thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| COPY AccessDenied | IAM role, bucket policy hoặc KMS key policy thiếu quyền | Kiểm tra trust policy, S3 prefix và KMS permissions |
| COPY không tìm thấy file | Prefix sai hoặc manifest trỏ tới object không tồn tại | Kiểm tra S3 keys và mandatory entries |
| COPY nạp thiếu file nhưng vẫn thành công | Prefix không bảo đảm mọi file mong muốn tồn tại | Dùng manifest với mandatory=true |
| COPY rất chậm | Một file lớn không split được hoặc quá ít files | Chia file, cân bằng size và tận dụng parallel load |
| COPY Parquet lỗi | Schema/Region/format option không tương thích | Kiểm tra schema và giới hạn COPY columnar |
| CSV delimiter error | Delimiter, quote hoặc escape không nhất quán | Chuẩn hóa CSV và kiểm tra file mẫu |
| Timestamp parse error | TIMEFORMAT/DATEFORMAT không khớp | Dùng auto hoặc format tường minh |
| Nạp trùng dữ liệu | COPY append và batch retry | Dùng staging, batch ID và dedup/merge |
| Query có DS_DIST_BOTH | Hai bảng cần redistribution | Xem AUTO, join key và key skew |
| Query scan quá nhiều blocks | Sort key không phù hợp hoặc unsorted region cao | Xem filter, sort key, VACUUM và ATO |
| Query plan ước lượng rows sai | Statistics cũ | Chạy ANALYZE và kiểm tra stats_off |
| Một node xử lý lâu hơn | Distribution skew hoặc hot key | Kiểm tra skew_rows và đổi distribution strategy |
| Query queue time cao | WLM concurrency hoặc workload cạnh tranh | Kiểm tra Auto WLM, priorities và QMR |
| Materialized view không được dùng | View stale hoặc query không đủ điều kiện rewrite | Refresh view, EXPLAIN và kiểm tra rewrite history |
| VACUUM kéo dài | Bảng lớn, nhiều unsorted/deleted rows hoặc interleaved index | Chọn đúng vacuum mode và lên lịch phù hợp |
| SYS view không hiển thị query | Quyền/visibility hoặc thời gian retention | Kiểm tra user permissions và view scope |
| STL_LOAD_ERRORS trống trên Serverless | STL view không bao phủ Serverless | Dùng SYS_LOAD_ERROR_DETAIL |
| Query nhanh bất thường khi benchmark | Result cache hit | Kiểm tra result_cache_hit và benchmark cold/warm riêng |

## 30. Best practices cho Redshift ingestion và query performance

### Nạp dữ liệu

- Dùng COPY cho bulk loads.
- Ưu tiên IAM role thay cho access keys.
- Đặt S3 và Redshift cùng Region khi có thể.
- Dùng nhiều file có kích thước cân bằng để khai thác MPP.
- Dùng manifest cho tập file chính xác.
- Chuẩn hóa schema, timezone, null và encoding trước load.
- Dùng NOLOAD và sample batch trước production.
- Theo dõi SYS_LOAD_HISTORY và SYS_LOAD_ERROR_DETAIL.
- Thiết kế staging và batch ID để COPY retry không tạo duplicate.
- Tách raw, staging và curated datasets.

### Table design

- Bắt đầu với DISTSTYLE AUTO và SORTKEY AUTO.
- Chỉ chọn DISTKEY khi join workload và distribution chứng minh lợi ích.
- Tránh skew và low-cardinality distribution keys.
- Dùng ALL có chọn lọc cho bảng nhỏ, ít thay đổi khi có benchmark.
- Chọn sort key theo filter patterns và time-range queries.
- Ưu tiên compound hoặc AUTO cho phần lớn workloads; dùng interleaved khi có lý do đo được.
- Dùng ENCODE AUTO trừ khi có benchmark cụ thể.
- Review ATO recommendations khi workload thay đổi.

### Query tuning

- Dùng EXPLAIN trước khi thay đổi schema.
- Đọc data movement labels và scan/sort/aggregate steps.
- Cập nhật ANALYZE sau bulk changes đáng kể.
- Theo dõi unsorted rows và vacuum history.
- Filter sớm, tránh SELECT * và cast không cần thiết.
- Tối ưu join keys và statistics.
- Dùng materialized views cho workload lặp lại có thể chấp nhận refresh lag.
- Phân biệt queue time và execution time.

### Workload và operations

- Bắt đầu với Auto WLM.
- Dùng query priorities/QMR cho workload khác nhau.
- Theo dõi concurrency scaling và chi phí.
- Dùng SYS monitoring views cho Provisioned và Serverless.
- Bảo vệ S3 data, IAM role và KMS keys.
- Ghi lại load manifest, batch ID và query labels.
- Đo p95/p99 latency và ETL completion time.
- Benchmark bằng dữ liệu đại diện và query cache-aware.
- Có rollback cho table redesign và load pipeline.

## 31. Bài tập tự luyện

1. Vì sao COPY phù hợp hơn INSERT từng row cho batch lớn?
2. Manifest giải quyết rủi ro nào khi COPY từ S3 prefix?
3. Vì sao IAM role được khuyến nghị thay cho access key?
4. COPY NOLOAD giúp kiểm tra điều gì?
5. Vì sao COPY retry có thể tạo duplicate?
6. Khi nào nên dùng Parquet/ORC?
7. Vì sao file GZIP đơn lớn có thể làm load chậm?
8. Kích thước file và số lượng file ảnh hưởng thế nào đến MPP?
9. DISTSTYLE AUTO hoạt động ra sao?
10. Khi nào chọn DISTSTYLE KEY?
11. Khi nào DISTSTYLE ALL có thể hữu ích?
12. Vì sao low-cardinality DISTKEY có thể tạo skew?
13. DISTSTYLE EVEN phù hợp với trường hợp nào?
14. Sort key và distribution key giải quyết hai vấn đề nào khác nhau?
15. Zone maps giúp giảm lượng data scan ra sao?
16. Compound sort key hiệu quả nhất khi query filter theo phần nào của key?
17. Khi nào interleaved sort key đáng cân nhắc?
18. ATO theo dõi và tự tối ưu những gì?
19. ANALYZE cập nhật dữ liệu nào cho optimizer?
20. VACUUM giải quyết unsorted và deleted rows thế nào?
21. Vì sao không nên chạy VACUUM FULL theo lịch cứng cho mọi bảng?
22. EXPLAIN có thực thi query không?
23. DS_DIST_NONE và DS_DIST_BOTH khác nhau ra sao?
24. Vì sao query plan cost không phải thời gian thực thi?
25. SYS_QUERY_HISTORY giúp tách queue time và execution time thế nào?
26. Vì sao Auto WLM phù hợp với phần lớn workload?
27. QMR có thể thực hiện những action nào?
28. Materialized view cần refresh khi nào?
29. Khi nào automatic query rewrite có thể sử dụng materialized view?
30. Vì sao result cache có thể làm sai lệch benchmark?
31. Tại sao SYS_LOAD_ERROR_DETAIL nên dùng cho Serverless thay cho STL_LOAD_ERRORS?
32. Làm thế nào để kiểm soát COPY retry an toàn?

### Gợi ý đáp án

1. COPY nạp song song từ nhiều files, giảm request overhead và tận dụng MPP.
2. Bảo đảm tập file chính xác, phát hiện file bắt buộc bị thiếu và tránh nạp nhầm backup.
3. Role có credential tạm thời, least privilege và không cần lưu secret trong SQL.
4. Khả năng đọc/parse dữ liệu mà không ghi rows vào bảng.
5. COPY append rows; chạy lại cùng files có thể nạp lại cùng records.
6. Khi pipeline tạo dữ liệu columnar có schema rõ và workload cần bulk load.
7. File không split được có thể bị xử lý tuần tự.
8. Nhiều file cân bằng giúp slices xử lý song song; quá ít file làm giảm parallelism.
9. Redshift tự chọn ALL, KEY hoặc EVEN theo size/workload và có thể thay đổi nền.
10. Khi bảng lớn thường join theo key có phân bố đều.
11. Khi bảng dimension nhỏ, ít thay đổi và broadcast/redistribution đang tốn kém.
12. Nhiều rows tập trung vào một số slices, làm mất cân bằng.
13. Khi không có key phù hợp hoặc bảng không join thường xuyên.
14. Distribution quyết định rows nằm ở node nào; sort key quyết định thứ tự rows/blocks.
15. Engine bỏ qua blocks có min/max không giao với predicate.
16. Prefix các cột theo đúng thứ tự khai báo.
17. Khi query filter nhiều chiều độc lập và benchmark chứng minh lợi ích.
18. Distribution style và sort key dựa trên query workload/table metadata.
19. Statistics về phân bố dữ liệu, giúp optimizer ước lượng rows và chọn plan.
20. Sắp xếp rows và thu hồi space từ deleted rows.
21. Redshift đã tự sort và VACUUM DELETE nền; vacuum thủ công tốn tài nguyên và chỉ cần khi table health cho thấy cần.
22. Không. EXPLAIN chỉ hiển thị plan.
23. DS_DIST_NONE không di chuyển dữ liệu; DS_DIST_BOTH di chuyển cả hai phía join.
24. Cost là giá trị tương đối trong plan, không phải elapsed time hay memory.
25. Queue time là thời gian chờ WLM; execution time là thời gian chạy.
26. Nó tự điều chỉnh concurrency và memory theo workload.
27. Log, hop hoặc abort query theo rule.
28. Khi base tables thay đổi và cần cập nhật snapshot kết quả; có thể manual hoặc auto refresh.
29. Khi view còn fresh và query thuộc nhóm được hỗ trợ.
30. Query có thể trả cached result thay vì thực thi, làm latency thấp giả tạo.
31. Một số STL views không bao phủ Serverless; SYS views có phạm vi hỗ trợ rộng hơn.
32. Dùng staging, batch ID, manifest bất biến, validation và transaction merge/dedup.

## 32. Câu hỏi phỏng vấn

### Vì sao COPY là phương pháp bulk load được khuyến nghị?

COPY tận dụng MPP để đọc nhiều files song song, dùng IAM role và hỗ trợ nhiều format. INSERT từng row tạo nhiều round trips và không tận dụng hiệu quả kiến trúc nạp dữ liệu.

### Vì sao cần manifest thay vì chỉ dùng S3 prefix?

Prefix có thể khớp cả file không mong muốn hoặc thiếu một file mà COPY vẫn hoàn tất. Manifest liệt kê chính xác objects và có thể đánh dấu mandatory để bảo đảm batch đầy đủ.

### DISTKEY có phải luôn nên đặt theo primary key?

Không. Redshift không phải OLTP database và không dùng primary key như index để định vị row. DISTKEY nên dựa trên join patterns, cardinality, skew và filtered data volume.

### Khi nào dùng DISTSTYLE ALL?

Khi một bảng nhỏ, ít thay đổi cần join thường xuyên và lợi ích tránh broadcast/redistribution lớn hơn storage/load overhead. Với dimension nhỏ, broadcast có thể đã đủ rẻ.

### Vì sao SORTKEY timestamp thường hữu ích cho fact tables?

Nếu workload thường truy vấn khoảng thời gian gần đây, timestamp leading sort key giúp zone maps bỏ qua blocks ngoài time range.

### ATO có thay thế hoàn toàn việc hiểu query plan không?

Không. ATO tự tối ưu table layout nhưng DBA vẫn cần đọc plan, đo query latency, kiểm tra skew và đánh giá các truy vấn quan trọng.

### Khi nào nên chạy ANALYZE và VACUUM?

ANALYZE khi statistics cũ hoặc dữ liệu thay đổi đáng kể. VACUUM khi unsorted/deleted rows ảnh hưởng hiệu năng và background maintenance chưa đáp ứng. Không chạy theo lịch cứng mà không đo.

### DS_DIST_BOTH có luôn là lỗi không?

Không phải lỗi thực thi, nhưng thường chỉ ra cả hai phía join đều phải di chuyển dữ liệu. Với bảng lớn, điều này có thể tốn network và giảm hiệu năng; cần xem query plan và volume thực tế.

### Vì sao nên dùng SYS monitoring views?

SYS views cung cấp cách quan sát thống nhất hơn cho query/load/maintenance và hỗ trợ cả Redshift Serverless cùng provisioned trong nhiều trường hợp. Một số STL/SVL views chỉ dành cho provisioned.

### Materialized view có luôn nhanh hơn query gốc không?

Không. Nó giảm thời gian tính toán bằng cách lưu kết quả trước, nhưng phát sinh storage và refresh compute. Chỉ dùng khi workload đọc lặp lại đủ nhiều và chấp nhận freshness theo refresh policy.

## 33. Checklist trước khi đưa Redshift warehouse vào production

### Data ingestion

- [ ] S3 prefix/manifest chỉ chứa đúng batch cần nạp.
- [ ] IAM role theo least privilege và KMS key policy đã được kiểm tra.
- [ ] File format, delimiter, encoding, timezone và schema đã được xác nhận.
- [ ] Số lượng/kích thước files tận dụng parallel load.
- [ ] COPY NOLOAD hoặc pilot batch đã PASS.
- [ ] Load errors và row counts có báo cáo.
- [ ] Batch ID và retry semantics chống nạp trùng.
- [ ] Cross-Region transfer cost đã được ước lượng.

### Table layout

- [ ] DISTSTYLE AUTO/SORTKEY AUTO đã được đánh giá đầu tiên.
- [ ] DISTKEY không tạo skew và phù hợp join workload.
- [ ] SORTKEY phù hợp filter patterns.
- [ ] Compression encoding được review.
- [ ] Table size, unsorted rows và stats freshness được theo dõi.
- [ ] ATO recommendations được review định kỳ.

### Query performance

- [ ] Query quan trọng có EXPLAIN plan.
- [ ] Data redistribution và broadcast được đánh giá.
- [ ] Statistics được cập nhật sau bulk load lớn.
- [ ] VACUUM chỉ chạy khi table health yêu cầu.
- [ ] SQL tránh scan/join không cần thiết.
- [ ] Materialized views có refresh/freshness policy.
- [ ] Result cache được tính đến khi benchmark.

### Workload và monitoring

- [ ] Auto WLM và priorities phù hợp.
- [ ] QMR có rule/action rõ.
- [ ] Queue time và execution time được theo dõi.
- [ ] SYS_QUERY_HISTORY/DETAIL và SYS_LOAD_HISTORY/ERROR_DETAIL có dashboard.
- [ ] Serverless/Provisioned system view differences đã được ghi nhận.
- [ ] Concurrency scaling và chi phí được theo dõi.

### Security và operations

- [ ] Redshift role không dùng static credentials.
- [ ] S3 bucket, KMS key và network access được bảo vệ.
- [ ] Quyền SQL theo role/schema/table được review.
- [ ] Có audit trail cho load batch và schema changes.
- [ ] Có runbook cho COPY errors, skew, slow queries và WLM queueing.
- [ ] Có rollback cho table redesign và load pipeline.
- [ ] Có owner cho ingestion, warehouse schema và dashboard SLAs.

## 34. Tài liệu tham khảo chính thức

- [Amazon Redshift best practices for loading data](https://docs.aws.amazon.com/redshift/latest/dg/c_loading-data-best-practices.html)
- [Using the COPY command to load from Amazon S3](https://docs.aws.amazon.com/redshift/latest/dg/t_loading-tables-from-s3.html)
- [COPY command reference](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY.html)
- [COPY examples](https://docs.aws.amazon.com/redshift/latest/dg/r_COPY_command_examples.html)
- [Loading data files and parallel loading](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-use-multiple-files.html)
- [Loading compressed and uncompressed files](https://docs.aws.amazon.com/redshift/latest/dg/t_splitting-data-files.html)
- [COPY from Parquet and ORC](https://docs.aws.amazon.com/redshift/latest/dg/copy-usage_notes-copy-from-columnar.html)
- [COPY authorization parameters](https://docs.aws.amazon.com/redshift/latest/dg/copy-parameters-authorization.html)
- [IAM permissions for COPY, UNLOAD, and CREATE LIBRARY](https://docs.aws.amazon.com/redshift/latest/dg/loading-data-access-permissions.html)
- [Troubleshooting data loads](https://docs.aws.amazon.com/redshift/latest/dg/t_Troubleshooting_load_errors.html)
- [System tables for troubleshooting data loads](https://docs.aws.amazon.com/redshift/latest/dg/system-tables-for-troubleshooting-data-loads.html)
- [SYS_LOAD_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_LOAD_HISTORY.html)
- [SYS_LOAD_ERROR_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_LOAD_ERROR_DETAIL.html)
- [SYS_AUTOMATIC_OPTIMIZATION](https://docs.aws.amazon.com/redshift/latest/dg/SYS_AUTOMATIC_OPTIMIZATION.html)
- [Distribution styles](https://docs.aws.amazon.com/redshift/latest/dg/c_choosing_dist_sort.html)
- [Data distribution for query optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Distributing_data.html)
- [Choose the best sort key](https://docs.aws.amazon.com/redshift/latest/dg/c_best-practices-sort-key.html)
- [Sort keys](https://docs.aws.amazon.com/redshift/latest/dg/t_Sorting_data.html)
- [Automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/t_Creating_tables.html)
- [Monitoring automatic table optimization](https://docs.aws.amazon.com/redshift/latest/dg/c_ato-enabling-disabling-monitoring.html)
- [Compression encodings](https://docs.aws.amazon.com/redshift/latest/dg/c_Compression_encodings.html)
- [ANALYZE command](https://docs.aws.amazon.com/redshift/latest/dg/r_ANALYZE.html)
- [VACUUM command](https://docs.aws.amazon.com/redshift/latest/dg/r_VACUUM_command.html)
- [Creating and interpreting a query plan](https://docs.aws.amazon.com/redshift/latest/dg/c-the-query-plan.html)
- [Analyzing a query plan](https://docs.aws.amazon.com/redshift/latest/dg/c-analyzing-the-query-plan.html)
- [SYS_QUERY_HISTORY](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_HISTORY.html)
- [SYS_QUERY_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_QUERY_DETAIL.html)
- [Workload management](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-implementing-workload-management.html)
- [WLM query monitoring rules](https://docs.aws.amazon.com/redshift/latest/dg/cm-c-wlm-query-monitoring-rules.html)
- [Concurrency scaling](https://docs.aws.amazon.com/redshift/latest/dg/concurrency-scaling.html)
- [Materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-overview.html)
- [Refreshing materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-refresh.html)
- [Automatic query rewriting to use materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-auto-rewrite.html)
- [Automated materialized views](https://docs.aws.amazon.com/redshift/latest/dg/materialized-view-auto-mv.html)


