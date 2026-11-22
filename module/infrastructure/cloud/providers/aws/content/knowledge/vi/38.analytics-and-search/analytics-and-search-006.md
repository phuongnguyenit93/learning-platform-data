# Redshift Spectrum và chia sẻ dữ liệu phân tích

Một doanh nghiệp thường có dữ liệu phân tích ở nhiều nơi: bảng fact lớn trong Amazon S3, bảng dimension trong kho dữ liệu, dữ liệu do nhóm BI quản lý và dữ liệu được chia sẻ với các account hoặc đơn vị kinh doanh khác. Sao chép tất cả dữ liệu về một warehouse có thể làm tăng chi phí ETL, lưu trữ và thời gian đồng bộ. Ngược lại, để từng nhóm tự truy cập S3 và tự định nghĩa schema có thể dẫn tới quyền truy cập không nhất quán, logic phân tích trùng lặp và khó kiểm soát.

Amazon Redshift cung cấp hai khả năng bổ trợ nhau:

- **Redshift Spectrum** cho phép truy vấn dữ liệu nằm ngoài warehouse, phổ biến nhất là file trong Amazon S3 được mô tả bằng AWS Glue Data Catalog, Athena Data Catalog hoặc Hive metastore. Người dùng có thể kết hợp external table với bảng local trong cùng câu lệnh SQL.
- **Redshift data sharing** cho phép chia sẻ database objects đang sống trong một Redshift producer tới cluster hoặc Serverless workgroup khác thông qua datashare. Consumer truy vấn dữ liệu được chia sẻ bằng compute của chính mình, không cần tạo bản sao ETL riêng.

Trong hệ sinh thái **CLOUD_PROVIDERS_AWS**, hai khả năng này giúp xây dựng kiến trúc analytics dùng chung data lake và warehouse, hỗ trợ BI, data science, báo cáo liên phòng ban và chia sẻ dữ liệu đa account/Region. Người học cần phân biệt external table, datashare và Lake Formation; thiết kế IAM, metadata, partition, quyền producer/consumer, hiệu năng và chi phí. Mục tiêu là cung cấp dữ liệu đúng, có kiểm soát và có thể quan sát được.

## 1. Hai bài toán và hai cơ chế

Redshift Spectrum và data sharing đều giúp nhiều nhóm truy cập dữ liệu, nhưng giải quyết các lớp khác nhau.

| Tiêu chí | Redshift Spectrum | Redshift data sharing |
|---|---|---|
| Dữ liệu chính | File ngoài warehouse, thường nằm trên S3 | Database objects trong Redshift producer; có thể gồm external data lake tables được hỗ trợ |
| Metadata | External schema và external catalog | Datashare, object permissions và consumer association |
| Cách truy cập | Query external table bằng SQL | Consumer tạo database tham chiếu datashare rồi query |
| Sao chép dữ liệu | Không cần load toàn bộ file vào local table | Không tạo bản sao dữ liệu warehouse cho consumer |
| Compute query | Redshift query engine kết hợp lớp data lake query | Compute của consumer thực thi truy vấn trên dữ liệu được chia sẻ |
| Quyền | IAM role tới catalog/S3, cộng quyền SQL trong Redshift; có thể dùng Lake Formation | Producer cấp quyền datashare và consumer; consumer cấp quyền cho user/role nội bộ |
| Mục đích | Kết hợp data lake và warehouse | Phân phối dữ liệu phân tích đã được quản trị tới nhiều warehouse |

Một kiến trúc có thể dùng cả hai: producer Redshift tạo datashare chứa một view kết hợp bảng local với bảng external từ S3; consumer nhận datashare và query view đó cùng các bảng riêng của mình.

## 2. Redshift Spectrum là gì?

Redshift Spectrum là khả năng truy vấn dữ liệu trong Amazon S3 thông qua external tables. External table lưu metadata như tên cột, kiểu dữ liệu, định dạng file và vị trí S3; dữ liệu vẫn nằm trong S3. Người dùng truy vấn external table trong Redshift như một bảng SQL và có thể join với local table.

Với kiến trúc RA3 provisioned, các truy vấn data lake dùng một fleet xử lý Spectrum chuyên dụng, tách khỏi compute cluster. Với Redshift RG provisioned và Redshift Serverless, data lake query engine được tích hợp vào compute của dịch vụ. Vì kiến trúc thực thi khác nhau, cần đọc đúng tài liệu và pricing theo loại warehouse đang sử dụng.

~~~mermaid
flowchart LR
    A[BI / SQL client] --> B[Amazon Redshift]
    B --> C[Local tables]
    B --> D[External schema]
    D --> E[AWS Glue Data Catalog]
    D --> F[Redshift Spectrum / data lake query engine]
    F --> G[Amazon S3 data files]
~~~

Spectrum không tự chuyển toàn bộ dữ liệu từ S3 vào local table trước mỗi truy vấn. Query optimizer có thể đẩy một số thao tác lọc và tổng hợp xuống tầng xử lý data lake để giảm dữ liệu trả về warehouse.

Kiểm tra Region theo loại warehouse trước khi triển khai. Với RA3 provisioned cluster, cluster và S3 bucket dùng cho Spectrum phải ở cùng Region. RG provisioned và Redshift Serverless dùng integrated data lake query engine có hỗ trợ truy vấn S3 cross-Region theo tài liệu dịch vụ hiện hành.

## 3. External schema và external table

External schema là schema trong Redshift tham chiếu tới database nằm trong external data catalog. External table là metadata mô tả file bên ngoài mà Redshift đọc.

External catalog có thể là AWS Glue Data Catalog, Athena Data Catalog hoặc Apache Hive metastore, ví dụ metastore do Amazon EMR quản lý.

Khi catalog được quản lý tập trung, nhiều công cụ như Athena, Glue ETL và Redshift có thể sử dụng cùng metadata. Thay đổi catalog sẽ được các cluster Redshift tham chiếu tới nhìn thấy mà không cần tạo lại local table.

### Luồng thiết lập

1. Đưa file dữ liệu lên S3 theo layout và format đã chọn.
2. Tạo metadata database/table/partition trong Glue Data Catalog hoặc catalog tương thích.
3. Tạo IAM role cho Redshift đọc catalog và dữ liệu.
4. Gắn role vào Redshift cluster hoặc Serverless namespace/workgroup theo cấu hình dịch vụ.
5. Tạo external schema trỏ tới database trong catalog.
6. Tạo external table trong schema, hoặc sử dụng table đã tồn tại trong catalog.
7. Cấp quyền SQL cho người dùng Redshift.
8. Kiểm tra query plan, số file và bytes scanned.

## 4. IAM role cho Redshift Spectrum

Redshift cần quyền truy cập catalog và object S3 thay mặt người dùng chạy query. Cách phổ biến là tạo IAM role, thiết lập trust policy cho dịch vụ Redshift, gắn role vào cluster/namespace và khai báo ARN trong CREATE EXTERNAL SCHEMA.

Role thường cần các nhóm quyền:

- S3: s3:ListBucket trên bucket/prefix và s3:GetObject trên object cần đọc.
- Glue Data Catalog: các quyền đọc database, table, partition và metadata cần thiết như glue:GetDatabase, glue:GetTable, glue:GetPartitions.
- KMS: kms:Decrypt nếu object được mã hóa bằng SSE-KMS và role phải đọc được key.
- Lake Formation: quyền được cấp qua Lake Formation nếu table/path được quản lý bởi dịch vụ này.

Không cấp quyền s3:* trên toàn bộ account nếu workload chỉ đọc một bucket hoặc prefix. Có thể tách role theo data domain, account hoặc mức nhạy cảm để thu hẹp phạm vi.

Ví dụ tạo external schema tham chiếu Glue Data Catalog:

~~~sql
CREATE EXTERNAL SCHEMA spectrum_sales
FROM DATA CATALOG
DATABASE 'sales_lake'
IAM_ROLE 'arn:aws:iam::111122223333:role/RedshiftSpectrumReadRole'
REGION 'ap-southeast-1';
~~~

Trong câu lệnh này, REGION là Region của Data Catalog, không phải chỉ dẫn về Region chứa file S3. Nếu catalog ở Region khác, hãy khai báo đúng Region của catalog và kiểm tra giới hạn truy cập dữ liệu theo loại Redshift warehouse.

### SQL permission trong Redshift

IAM role cho phép dịch vụ đọc nguồn dữ liệu; nó không tự động cấp quyền query cho mọi database user. Người dùng còn cần quyền USAGE trên external schema và quyền TEMP trên database để chạy Spectrum query.

~~~sql
GRANT USAGE ON SCHEMA spectrum_sales TO GROUP analysts;
GRANT TEMP ON DATABASE analytics TO GROUP analysts;
~~~

Nếu dùng Lake Formation, quyền truy cập table/column/row được kiểm tra theo principal và policy được cấu hình trong Lake Formation. Không giả định IAM role đọc được S3 đồng nghĩa mọi Redshift user được phép đọc mọi cột.

## 5. Tạo external table trên S3

Nếu metadata chưa có trong catalog, có thể tạo external table bằng Redshift DDL. Ví dụ dữ liệu orders được lưu dưới dạng Parquet trong S3:

~~~sql
CREATE EXTERNAL TABLE spectrum_sales.orders (
    order_id       BIGINT,
    customer_id    BIGINT,
    order_ts       TIMESTAMP,
    region         VARCHAR(32),
    total_amount   DECIMAL(18,2)
)
PARTITIONED BY (year SMALLINT, month SMALLINT)
STORED AS PARQUET
LOCATION 's3://company-data-lake/curated/orders/'
TABLE PROPERTIES ('numRows'='250000000');
~~~

LOCATION trỏ tới prefix chứa file dữ liệu. PARTITIONED BY mô tả các partition column nằm trong cấu trúc dữ liệu. numRows là thống kê số hàng ước lượng giúp optimizer lập kế hoạch join; Redshift không tự chạy ANALYZE để tạo thống kê cho external table như đối với local table.

Nếu table đã được định nghĩa trong Glue Data Catalog hoặc Athena, có thể tạo external schema tham chiếu database đó rồi sử dụng table có sẵn. Tránh định nghĩa cùng một dataset nhiều lần với schema, partition hoặc location không thống nhất.

### Kiểm tra external table

~~~sql
SELECT schemaname, tablename, location
FROM svv_external_tables
WHERE schemaname = 'spectrum_sales';
~~~

Có thể dùng SVV_EXTERNAL_COLUMNS để xem schema và SVV_EXTERNAL_PARTITIONS để xem partition metadata.

## 6. Partitioning cho external tables

Partitioning chia dataset thành prefix theo các thuộc tính thường được dùng trong filter, chẳng hạn năm, tháng, ngày, khu vực hoặc loại sự kiện. Redshift Spectrum có thể loại bỏ partition không liên quan khi query lọc trực tiếp partition column.

Ví dụ layout:

~~~text
s3://company-data-lake/curated/orders/
  year=2026/
    month=11/
      part-00001.parquet
      part-00002.parquet
~~~

Đăng ký partition:

~~~sql
ALTER TABLE spectrum_sales.orders
ADD PARTITION (year=2026, month=11)
LOCATION 's3://company-data-lake/curated/orders/year=2026/month=11/';
~~~

Nếu table được quản lý bằng Glue Data Catalog, partition có thể được tạo qua Glue crawler, Glue ETL hoặc API. Khi thêm partition qua Redshift, metadata được cập nhật trong external catalog tương ứng theo cơ chế hỗ trợ.

### Query phải lọc partition column

~~~sql
SELECT
    region,
    SUM(total_amount) AS revenue
FROM spectrum_sales.orders
WHERE year = 2026
  AND month = 11
  AND order_ts >= TIMESTAMP '2026-11-20 00:00:00'
  AND order_ts <  TIMESTAMP '2026-11-21 00:00:00'
GROUP BY region;
~~~

Điều kiện year và month giúp pruning partition. Điều kiện order_ts lọc chính xác phạm vi thời gian trong file. Nếu chỉ lọc order_ts mà không lọc partition column, query có thể phải xét nhiều partition hơn.

Chọn partition key theo query pattern và cardinality. Partition theo customer_id có thể tạo quá nhiều partition nhỏ; cân nhắc giữ customer_id trong file Parquet, dùng sort/encoding/statistics hoặc thiết kế layout khác.

## 7. Định dạng file và kích thước file

Redshift Spectrum hỗ trợ nhiều định dạng như Parquet, ORC, text, CSV và một số định dạng khác theo tài liệu dịch vụ. Với workload phân tích, Parquet hoặc ORC thường phù hợp hơn vì là columnar format.

| Định dạng | Đặc điểm | Khi nên cân nhắc |
|---|---|---|
| Parquet | Columnar, column pruning, compression và ecosystem rộng | Lựa chọn phổ biến cho curated data lake |
| ORC | Columnar, stripe/index/statistics | Workload Hive/analytics có benchmark tốt |
| CSV/Text | Dễ trao đổi nhưng thường phải đọc nhiều dữ liệu hơn | Dữ liệu raw nhỏ hoặc yêu cầu tương thích đơn giản |
| JSON | Giữ cấu trúc linh hoạt nhưng parsing có thể tốn chi phí | Raw events hoặc dữ liệu bán cấu trúc |

AWS khuyến nghị dùng nhiều file để tận dụng parallel processing, giữ file lớn hơn khoảng 64 MB và tránh kích thước file lệch nhau quá nhiều. Đây là hướng dẫn tối ưu, không phải giới hạn cứng; kích thước phù hợp phụ thuộc số lượng dữ liệu, query concurrency và định dạng.

Quá nhiều file nhỏ làm tăng overhead listing, metadata và lập lịch scan. Một file quá lớn có thể hạn chế parallelism nếu không chia được thành nhiều scan range. Hãy compact file theo partition và benchmark với query thực tế.

## 8. Query Spectrum cùng bảng local

Một ưu điểm quan trọng là có thể join external table với local table trong cùng Redshift SQL. Ví dụ, fact orders lớn nằm ở S3 còn dimension customer nhỏ được nạp vào warehouse:

~~~sql
SELECT
    c.customer_segment,
    o.region,
    SUM(o.total_amount) AS revenue
FROM spectrum_sales.orders AS o
JOIN public.dim_customer AS c
  ON o.customer_id = c.customer_id
WHERE o.year = 2026
  AND o.month = 11
GROUP BY c.customer_segment, o.region;
~~~

Mô hình thường hiệu quả khi fact table lớn được lưu trong S3, còn các dimension nhỏ và được truy cập thường xuyên nằm trong Redshift. Query optimizer có thể đẩy filter hoặc aggregate xuống Spectrum trước khi đưa kết quả về warehouse để join.

Không phải mọi thao tác SQL đều được pushdown. Dùng EXPLAIN để xem phần xử lý nào chạy ở tầng S3 và phần nào chạy trong cluster. Khi lượng dữ liệu trả từ Spectrum quá lớn, cluster vẫn có thể trở thành bottleneck.

## 9. Predicate pushdown và aggregate pushdown

Predicate pushdown cho phép điều kiện lọc được thực thi gần nơi dữ liệu nằm, giảm số hàng truyền về warehouse. Aggregate pushdown cho phép một số phép tổng hợp được tính ở tầng Spectrum.

Các loại thao tác có thể được pushdown gồm điều kiện so sánh và pattern matching như LIKE, một số hàm tổng hợp như COUNT/SUM/AVG/MIN/MAX, GROUP BY và một số hàm chuỗi được hỗ trợ.

Các thao tác như DISTINCT và ORDER BY không được pushdown theo danh sách hỗ trợ hiện hành trong tài liệu Spectrum. Vì vậy, không nên viết query với giả định toàn bộ SQL sẽ chạy trên S3.

Ví dụ xem query plan:

~~~sql
EXPLAIN
SELECT
    region,
    SUM(total_amount)
FROM spectrum_sales.orders
WHERE year = 2026
  AND month = 11
  AND total_amount > 100
GROUP BY region;
~~~

Tìm các node như S3 Seq Scan, S3 HashAggregate, S3 Query Scan, Seq Scan PartitionInfo và Partition Loop. S3 Seq Scan có filter cho thấy điều kiện được xử lý ở tầng Spectrum; S3 HashAggregate cho biết aggregation được thực hiện gần nguồn dữ liệu.

## 10. Tối ưu query Spectrum

Các nguyên tắc thường đem lại hiệu quả:

1. Dùng Parquet hoặc ORC cho dữ liệu curated.
2. Chỉ chọn những cột cần thiết, tránh SELECT * trên bảng rộng.
3. Partition theo predicate thường dùng và lọc trực tiếp partition columns.
4. Giữ nhiều file có kích thước tương đối đồng đều để tăng parallelism.
5. Đặt fact table lớn ở S3 và dimension nhỏ, truy cập thường xuyên trong Redshift khi phù hợp.
6. Đẩy filter và aggregate xuống Spectrum khi query engine hỗ trợ.
7. Cập nhật numRows cho external table để optimizer có thông tin cardinality.
8. Tạo column statistics trong Glue Data Catalog khi phù hợp.
9. Dùng materialized view trên Spectrum table cho workload lặp lại nếu refresh semantics đáp ứng yêu cầu.
10. Đo query plan và số bytes scan trước/sau thay đổi.

Không partition theo mọi cột trong WHERE. Partition quá nhỏ làm metadata tăng; partition quá lớn khiến pruning ít hiệu quả. Chọn layout dựa trên tần suất filter, kích thước partition và cách ETL ghi file.

## 11. Quản lý metadata và schema evolution

Glue Data Catalog giữ metadata dùng chung cho nhiều công cụ. Một thay đổi schema cần được phối hợp giữa writer, catalog và reader:

- Thêm cột mới: kiểm tra file cũ không có cột đó và cách engine biểu diễn giá trị thiếu.
- Đổi kiểu dữ liệu: kiểm tra cast, precision và tương thích Parquet/ORC.
- Đổi tên cột: có thể cần tạo view tương thích hoặc ghi lại dữ liệu.
- Thay partition key: cần thay đổi layout và metadata theo kế hoạch.
- Thay location: cập nhật catalog hoặc external table location, không để hai nơi mô tả khác nhau.

Với bảng external được định nghĩa trong catalog, nên có một nguồn quản lý schema rõ ràng. Tránh để Glue crawler tự suy luận schema từ các file không đồng nhất rồi làm thay đổi metadata production ngoài dự kiến.

## 12. Spectrum và giới hạn thao tác dữ liệu

External table là tham chiếu tới dữ liệu bên ngoài, không có đầy đủ hành vi như local Redshift table.

- Không hỗ trợ UPDATE hoặc DELETE trên external tables.
- INSERT vào external table chỉ dùng được trong những cấu hình/định dạng được hỗ trợ; không giả định mọi external table đều có thể ghi.
- Metadata của external table được xem qua các system view dành riêng như SVV_EXTERNAL_TABLES, SVV_EXTERNAL_COLUMNS và SVV_EXTERNAL_PARTITIONS.
- Nếu không dùng Glue Data Catalog tích hợp Lake Formation, quyền user trên external data thường được kiểm soát ở cấp external schema thay vì từng external table.
- Với Lake Formation enabled Data Catalog, có thể quản lý quyền database/table/column và data filters theo cấu hình hỗ trợ.

Nếu workload cần transaction, update/delete thường xuyên hoặc constraint kiểu warehouse, hãy cân nhắc nạp dữ liệu vào local Redshift table hoặc dùng table format và engine có semantics phù hợp.

## 13. Redshift data sharing là gì?

Redshift data sharing cho phép một producer chia sẻ quyền truy cập tới live database objects với một hoặc nhiều consumer là Redshift provisioned cluster hoặc Redshift Serverless namespace/workgroup. Đơn vị chia sẻ là datashare.

Datashare chứa các schema, table, view, materialized view hoặc object được hỗ trợ cùng quyền tương ứng. Một datashare gắn với một database nguồn; chỉ object trong database đó mới được thêm vào datashare.

Khi producer commit thay đổi dữ liệu, consumer có thể nhìn thấy dữ liệu mới nhất theo cơ chế data sharing mà không cần chạy ETL để copy dữ liệu sang warehouse riêng. Consumer dùng compute của mình để chạy query, vì vậy nhiều nhóm có thể cô lập workload và lịch vận hành.

~~~mermaid
flowchart LR
    subgraph Producer["Producer warehouse"]
      A[Database]
      B[Datashare]
      A --> B
    end
    subgraph Consumers["Consumer warehouses"]
      C[BI cluster]
      D[Data science workgroup]
      E[Reporting cluster]
    end
    B --> C
    B --> D
    B --> E
    C --> F[Consumer queries]
    D --> G[Consumer queries]
    E --> H[Consumer queries]
~~~

## 14. Datashare khác với sao chép dữ liệu

| Tiêu chí | ETL/copy sang consumer | Redshift data sharing |
|---|---|---|
| Dữ liệu | Tạo bản sao riêng | Truy cập object được chia sẻ |
| Độ trễ cập nhật | Theo lịch hoặc pipeline đồng bộ | Live data; thay đổi có thể thấy sau commit |
| Storage | Có thể nhân bản dữ liệu | Không cần tạo bản sao warehouse cho consumer |
| Compute | Consumer query bản sao của mình | Consumer query dữ liệu chia sẻ bằng compute của consumer |
| Quản trị | Cần quản lý pipeline, schema và freshness của bản sao | Producer quản lý object và quyền share; consumer quản lý quyền nội bộ |
| Cô lập workload | Có | Có, mỗi consumer dùng compute riêng |
| Phù hợp | Cần biến đổi độc lập, snapshot riêng hoặc tách vòng đời | Nhiều nhóm cần truy cập cùng dữ liệu đã quản trị |

Data sharing không có nghĩa consumer được quyền truy cập trực tiếp toàn bộ S3 bucket của producer. Consumer truy cập các object được đưa vào datashare; với data lake table, cần cấu hình external catalog và quyền nguồn dữ liệu phù hợp.

## 15. Tạo datashare ở producer

Quy trình SQL cơ bản:

1. Tạo datashare trong database nguồn.
2. Thêm schema vào datashare.
3. Thêm bảng/view cần chia sẻ và quyền tương ứng.
4. Thêm consumer namespace hoặc AWS account.
5. Với cross-account, thực hiện bước authorize theo quy trình Redshift.

Ví dụ:

~~~sql
CREATE DATASHARE sales_share;

ALTER DATASHARE sales_share
ADD SCHEMA mart;

ALTER DATASHARE sales_share
ADD TABLE mart.daily_sales;

GRANT USAGE ON DATASHARE sales_share
TO ACCOUNT '222233334444';
~~~

CREATE DATASHARE gắn share với database đang kết nối. ALTER DATASHARE ADD SCHEMA thêm schema vào share; thao tác này không tự động thêm tất cả object bên trong. ADD TABLE thêm object và cấp quyền SELECT mặc định theo cách thêm trực tiếp.

Nếu cần thêm các object hiện tại và tương lai theo schema, có thể dùng scoped permissions hoặc cấu hình INCLUDENEW theo tài liệu Redshift. Hãy hiểu rõ phạm vi quyền trước khi bật tự động đưa object mới vào share.

### Xác minh datashare

~~~sql
SELECT *
FROM svv_datashares;

SELECT *
FROM svv_datashare_objects
WHERE share_name = 'sales_share';
~~~

Các view hệ thống giúp kiểm tra object đã được thêm và consumer nào đang được cấu hình.

## 16. Cấp quyền producer và nguyên tắc least privilege

Datashare có thể cấp quyền ở mức schema, table, view hoặc function được hỗ trợ. Nên chỉ chia sẻ các object đã được chuẩn hóa và phê duyệt.

Ví dụ chỉ chia sẻ bảng báo cáo:

~~~sql
CREATE DATASHARE finance_read_share;
ALTER DATASHARE finance_read_share ADD SCHEMA reporting;
ALTER DATASHARE finance_read_share ADD TABLE reporting.monthly_revenue;
GRANT USAGE ON DATASHARE finance_read_share
TO NAMESPACE 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
~~~

Khi thêm schema bằng ALTER DATASHARE ADD SCHEMA, quyền USAGE được thêm cho schema. Khi thêm table bằng ALTER DATASHARE ADD TABLE, quyền SELECT được cấp theo hành vi mặc định. Có thể dùng GRANT để cấp quyền cụ thể hoặc scoped permissions cho nhóm object.

Không đưa schema staging, bảng chứa PII hoặc dữ liệu chưa kiểm duyệt vào share chỉ vì chúng nằm cạnh bảng báo cáo. Dùng view đã masking hoặc projection các cột được phép nếu consumer không cần toàn bộ dữ liệu.

## 17. Chia sẻ cross-account

Chia sẻ giữa AWS accounts có thêm bước xác thực hai chiều.

**Producer:**

1. Tạo datashare và thêm object.
2. Thêm AWS account của consumer.
3. Cấp USAGE cho account.
4. Authorize datashare cho consumer account qua console hoặc API/CLI.
5. Nếu cho phép write, phải chủ động bật authorization cho writes, cấp đúng object privileges và consumer phải associate datashare với cluster/workgroup cụ thể có quyền ghi.

Ví dụ authorize qua CLI:

~~~bash
aws redshift authorize-data-share \
  --data-share-arn "arn:aws:redshift:ap-southeast-1:111122223333:datashare:12345678-1234-1234-1234-123456789012/sales_share" \
  --consumer-identifier "222233334444"
~~~

**Consumer:**

1. Nhận datashare invitation trong Redshift console.
2. Associate datashare với toàn account, Region hoặc namespace cụ thể.
3. Tạo database từ datashare.
4. Cấp quyền nội bộ cho user/role.
5. Chạy query và theo dõi usage.

Với cross-account data sharing, cả producer và consumer cluster phải được mã hóa. Consumer có thể associate ở phạm vi account hoặc namespace tùy yêu cầu; associate toàn account sẽ mở rộng phạm vi cho các namespace hiện tại và tương lai theo cấu hình. Đối với write sharing cross-account, association phải chỉ định cluster/workgroup cụ thể và được cấu hình cho phép ghi; chỉ authorize account là chưa đủ.

## 18. Tạo database và query ở consumer

Sau khi datashare được associate, consumer administrator tạo database tham chiếu datashare.

~~~sql
CREATE DATABASE sales_shared
FROM DATASHARE sales_share
OF ACCOUNT '111122223333'
NAMESPACE 'producer-namespace-guid';
~~~

Đối với datashare trong cùng account, có thể bỏ ACCOUNT và chỉ định namespace producer. Với cross-account, cần cả account ID và producer namespace GUID.

Sau khi tạo database, cấp quyền cho nhóm phân tích:

~~~sql
GRANT USAGE ON DATABASE sales_shared TO ROLE analyst_role;
~~~

Nếu database được tạo với WITH PERMISSIONS, cần cấp thêm quyền object-level cho schema/table theo nhu cầu. Nếu không dùng WITH PERMISSIONS, user/role có USAGE trên database sẽ được truy cập các object trong database theo quy tắc của datashare.

Query dữ liệu:

~~~sql
SELECT
    region,
    SUM(revenue) AS total_revenue
FROM sales_shared.mart.daily_sales
WHERE sales_date >= DATE '2026-11-01'
GROUP BY region;
~~~

Consumer có thể tạo view hoặc materialized view riêng trên dữ liệu được chia sẻ nếu workload cần lớp semantic hoặc tổng hợp cục bộ.

## 19. Chia sẻ dữ liệu qua nhiều Region

Redshift hỗ trợ data sharing giữa các Region theo cấu hình và loại warehouse được hỗ trợ. Consumer có thể associate datashare với toàn account, một Region hoặc namespace cụ thể trong Region.

Các điểm cần lưu ý:

- Dữ liệu vẫn do producer quản lý; consumer truy vấn qua datashare.
- Cross-Region data transfer phát sinh chi phí truyền dữ liệu từ Region producer sang Region consumer.
- Cả hai phía cần cấu hình encryption và quyền truy cập phù hợp.
- Region/namespace association xác định phạm vi consumer được phép sử dụng.
- Query performance phụ thuộc compute của consumer, network và khối lượng dữ liệu được đọc.

Cross-Region sharing phù hợp khi các đội phân tích ở nhiều địa lý cần truy cập cùng dữ liệu. Nếu consumer cần snapshot độc lập, latency thấp tại chỗ hoặc khả năng hoạt động khi producer không sẵn sàng, cân nhắc pipeline copy/replication thay vì chỉ dựa vào datashare.

Lưu ý: chia sẻ datashare qua AWS Lake Formation có các giới hạn khác với Redshift datashare trực tiếp. Theo tài liệu hiện hành, Lake Formation-managed datashare cross-Region chưa được hỗ trợ; không suy rộng khả năng cross-Region của datashare thông thường sang luồng này.

## 20. Chia sẻ external data lake tables qua datashare

Datashare không chỉ chứa local Redshift tables. Producer có thể chia sẻ table từ external schema tham chiếu AWS Glue Data Catalog, hoặc chia sẻ late-binding view kết hợp data lake table với local table.

Hai cách chính:

| Cách | Khi phù hợp |
|---|---|
| Chia sẻ external table trực tiếp | Consumer cần truy vấn table gốc hoặc join với bảng local của mình |
| Chia sẻ late-binding view | Producer muốn cung cấp một lớp logic đã chọn cột, join hoặc chuẩn hóa schema |

### Chia sẻ external table trực tiếp

Điều kiện quan trọng là IAM role của producer phải có quyền SELECT trên table. Sau khi external schema và table tồn tại, thêm schema và table vào datashare:

~~~sql
ALTER DATASHARE lake_share
ADD SCHEMA spectrum_sales;

ALTER DATASHARE lake_share
ADD TABLE spectrum_sales.orders;
~~~

Consumer associate datashare, tạo database tham chiếu và query external table được chia sẻ. Có thể join table đó với local table của consumer.

### Chia sẻ late-binding view

Late-binding view có thể kết hợp external table và local table:

~~~sql
CREATE VIEW reporting.orders_enriched AS
SELECT
    o.order_id,
    o.order_ts,
    o.total_amount,
    c.customer_segment
FROM spectrum_sales.orders AS o
JOIN mart.customer_dimension AS c
  ON o.customer_id = c.customer_id
WITH NO SCHEMA BINDING;
~~~

Thêm các schema chứa view và base tables vào datashare trước khi thêm view:

~~~sql
ALTER DATASHARE lake_share ADD SCHEMA reporting;
ALTER DATASHARE lake_share ADD SCHEMA spectrum_sales;
ALTER DATASHARE lake_share ADD SCHEMA mart;
ALTER DATASHARE lake_share ADD TABLE reporting.orders_enriched;
~~~

Late-binding view hữu ích khi producer muốn định nghĩa một giao diện dữ liệu ổn định. Consumer không cần tự viết lại logic join giữa local table và data lake table.

## 21. Redshift Spectrum kết hợp AWS Lake Formation

AWS Lake Formation cung cấp governance tập trung cho database, table, column và data filters trên dữ liệu trong S3 được đăng ký với Glue Data Catalog.

Khi sử dụng Redshift Spectrum với Data Catalog được Lake Formation quản lý:

1. Lake Formation administrator đăng ký S3 location và catalog database/table.
2. Administrator cấp quyền cho principal hoặc role.
3. Redshift sử dụng IAM role hoặc federated identity phù hợp để truy cập catalog.
4. Khi query, Lake Formation xác minh quyền và cấp credential tạm thời cho Spectrum.
5. Data filters có thể giới hạn row/column theo cấu hình được hỗ trợ.

Lake Formation giúp tránh việc chỉ dựa vào bucket policy hoặc schema-level access khi nhiều nhóm cần quyền dữ liệu khác nhau. Cần kiểm tra Region availability và giới hạn của tích hợp. Ví dụ, cell-level filters có giới hạn riêng và không nên mặc định rằng mọi policy của Lake Formation đều áp dụng được cho mọi kiểu datashare.

### Lake Formation-managed datashares

Redshift datashare có thể được publish tới AWS Glue Data Catalog để Lake Formation quản lý việc chia sẻ và cấp quyền tới consumer. Luồng này phù hợp khi tổ chức muốn một lớp governance thống nhất cho Redshift objects.

Các điểm cần nhớ:

- Producer tạo datashare và grant usage tới Lake Formation account.
- Producer authorize datashare theo quy trình.
- Lake Formation administrator discover/register datashare và liên kết với Glue Data Catalog.
- Tạo federated database và cấp quyền database/table cho consumer principals.
- Consumer cần quyền phù hợp ở cả Redshift và Lake Formation.
- Producer/consumer phải đáp ứng yêu cầu encryption và loại warehouse được hỗ trợ.

Theo tài liệu hiện hành, Lake Formation-managed datashare cross-Region chưa được hỗ trợ. Khi cần cross-Region, đánh giá datashare Redshift trực tiếp hoặc phương án sao chép dữ liệu phù hợp.

## 22. Bảo mật và audit cho Spectrum

Các lớp bảo vệ chính:

- IAM role theo least privilege cho S3 và Glue.
- Bucket policy giới hạn bucket/prefix và principal.
- KMS key policy cho object và Glue Data Catalog nếu catalog được mã hóa.
- Lake Formation permissions cho database/table/column/row khi dùng.
- Redshift SQL permissions trên external schema và database.
- VPC endpoint, enhanced VPC routing và network path theo kiến trúc warehouse.
- CloudTrail để audit API quản trị và truy cập nguồn dữ liệu theo khả năng logging.

Với enhanced VPC routing, cần cấu hình VPC endpoint cho S3 và Glue để cluster truy cập dữ liệu/catalog theo yêu cầu. Tuy nhiên, với RA3 Spectrum, luồng scan S3 do fleet quản lý bên ngoài VPC thực hiện; không giả định toàn bộ traffic scan sẽ đi qua VPC chỉ vì bật enhanced VPC routing.

## 23. Bảo mật và audit cho datashare

Producer cần quản lý quyền chia sẻ ở hai lớp:

1. Quyền của user/role được phép sửa datashare, thêm object hoặc grant consumer.
2. Quyền của consumer account/namespace được phép truy cập datashare và object cụ thể.

Consumer cần quản lý quyền truy cập database được tạo từ datashare cho user/role nội bộ. Không cấp USAGE cho toàn bộ account hoặc PUBLIC nếu chỉ một nhóm BI cần dữ liệu.

Một số guardrail:

- Giữ PUBLICACCESSIBLE ở FALSE trừ khi có yêu cầu rõ ràng cho public cluster/workgroup.
- Chỉ chia sẻ view đã chuẩn hóa hoặc bảng được duyệt.
- Tách datashare theo data domain và consumer group.
- Dùng WITH PERMISSIONS khi cần object-level permissions ở consumer.
- Audit producer/consumer access, thay đổi object và authorization.
- Thu hồi USAGE hoặc association khi hợp đồng chia sẻ kết thúc.
- Không đưa secret hoặc dữ liệu nhạy cảm vào view nếu consumer không cần.

Nếu dùng Lake Formation để kiểm soát row/column, hãy cấu hình policy tại đúng lớp được hỗ trợ và kiểm tra tương tác với Redshift row-level/column-level security. Không giả định policy ở producer tự động giữ nguyên khi publish qua mọi kiểu datashare.

## 24. Hiệu năng và tính độc lập của consumer

Data sharing giúp mỗi consumer dùng compute riêng. Một workload BI chạy nặng ở consumer không nhất thiết chiếm slot query của producer như khi mọi người cùng truy vấn một cluster. Tuy vậy, hiệu năng vẫn phụ thuộc:

- Compute size và concurrency của consumer.
- Độ phức tạp query, join và aggregation.
- Khối lượng dữ liệu được đọc từ datashare hoặc external S3.
- Network và cross-Region transfer.
- Statistics, distribution/sort design và materialized views.
- Cấu hình WLM hoặc Serverless capacity.

Không coi datashare là một bản sao được tối ưu sẵn cho mọi query. Consumer vẫn cần tối ưu SQL, phân tích plan, cân nhắc materialized view và điều chỉnh compute.

## 25. Chi phí cần theo dõi

Chi phí phụ thuộc vào loại warehouse, kiến trúc Spectrum, vị trí dữ liệu và hướng chia sẻ.

| Thành phần | Bên thường chịu chi phí |
|---|---|
| Redshift producer compute | Account producer |
| Redshift consumer compute | Account consumer |
| S3 storage và S3 operations | Account sở hữu bucket |
| Spectrum scan trên RA3 provisioned consumer | Consumer theo mô hình tính phí Spectrum/data scanned hiện hành |
| Data lake query trên RG provisioned hoặc Serverless | Tính trong compute pricing tương ứng theo tài liệu hiện hành |
| Cross-Region data transfer của datashare | Theo pricing áp dụng cho luồng nhận dữ liệu |
| Glue/Lake Formation và KMS | Theo mức sử dụng và account sở hữu tài nguyên |

Khi consumer truy vấn data lake table được chia sẻ, chi phí scan được tính cho consumer; chi phí S3 storage và operations vẫn thuộc account sở hữu bucket. Cần xác nhận bảng giá theo Region và loại warehouse trước khi lập ngân sách.

Để giảm chi phí:

- Partition và dùng Parquet/ORC để giảm bytes scanned.
- Tránh SELECT * và filter theo partition columns.
- Dùng materialized view cho query lặp lại khi refresh cost hợp lý.
- Chia sẻ view/table đã chọn cột thay vì toàn bộ schema.
- Chọn Region consumer phù hợp để giảm cross-Region transfer.
- Theo dõi query frequency và unused consumer association.
- Đặt workload nặng ở consumer warehouse có capacity phù hợp.

## 26. Giám sát Spectrum và query data lake

Có thể dùng system views để theo dõi số partition, file, bytes scan và thời gian xử lý.

Ví dụ dùng SYS_EXTERNAL_QUERY_DETAIL:

~~~sql
SELECT
    query_id,
    start_time,
    duration,
    total_partitions,
    qualified_partitions,
    scanned_files,
    returned_rows,
    returned_bytes,
    file_format,
    file_location
FROM sys_external_query_detail
WHERE source_type = 'S3'
ORDER BY start_time DESC
LIMIT 20;
~~~

Các trường quan trọng:

- total_partitions: tổng số partition được xét.
- qualified_partitions: số partition được query chọn.
- scanned_files: số file được scan.
- returned_bytes: với source_type = 'S3', số byte được scan; với nguồn federated query, đây là số byte trả về.
- duration: thời gian xử lý segment.
- s3list_time và get_partition_time: thời gian liệt kê S3 và lấy metadata partition.

Với một số provisioned cluster, có thể dùng SVL_S3QUERY và SVL_S3QUERY_SUMMARY. Serverless và các phiên bản warehouse mới có thể cung cấp SYS monitoring views phù hợp hơn; chọn view theo loại deployment.

## 27. Giám sát datashare

Theo dõi cả producer và consumer:

- SVV_DATASHARES: datashare hiện có và thuộc tính.
- SVV_DATASHARE_OBJECTS: schema/table/view nằm trong share.
- SVV_DATASHARE_CONSUMERS: consumer được cấu hình.
- SVV_REDSHIFT_DATABASES: database được tạo từ datashare.
- SYS_DATASHARE_USAGE_PRODUCER và SYS_DATASHARE_USAGE_CONSUMER: usage theo phía producer/consumer khi view được hỗ trợ.
- SYS_DATASHARE_CROSS_REGION_USAGE: usage liên quan cross-Region trong deployment hỗ trợ.

Ngoài system views, dùng CloudTrail và Redshift audit logging để theo dõi thay đổi quyền, association, authorization và truy vấn nhạy cảm. Thiết lập cảnh báo khi consumer bị mất association, share bị revoke hoặc query usage tăng bất thường.

## 28. Mẫu kiến trúc: data lake producer và nhiều BI consumer

Một doanh nghiệp có data lake trên S3, curated tables được catalog trong Glue và một Redshift warehouse làm producer. Các nhóm Finance, Sales và Data Science có warehouse riêng.

Thiết kế:

1. Glue Data Catalog lưu metadata của curated data lake.
2. Producer Redshift tạo external schema tới Glue catalog.
3. Producer tạo external table cho fact data và local table/view cho business logic.
4. Producer tạo datashare, thêm external tables trực tiếp hoặc late-binding views.
5. Producer cấp consumer theo namespace/account và authorize cross-account khi cần.
6. Consumer associate datashare, tạo database tham chiếu và cấp quyền cho analyst.
7. Consumer query dữ liệu được chia sẻ cùng dữ liệu local của mình.
8. Lake Formation quản lý row/column access nếu cần governance tập trung.

~~~mermaid
flowchart TB
    subgraph Lake["Data lake"]
      S3[Amazon S3 Parquet / ORC]
      Glue[AWS Glue Data Catalog]
      S3 --> Glue
    end
    subgraph Producer["Producer Redshift"]
      ES[External schema / Spectrum]
      RT[Local tables and views]
      DS[Datashare]
      Glue --> ES
      ES --> DS
      RT --> DS
    end
    subgraph ConsumerA["Finance consumer"]
      A[Redshift cluster]
      AQ[Finance BI]
      A --> AQ
    end
    subgraph ConsumerB["Sales consumer"]
      B[Serverless workgroup]
      BQ[Sales analytics]
      B --> BQ
    end
    DS --> A
    DS --> B
~~~

Lợi ích là producer giữ quyền kiểm soát schema và dữ liệu, trong khi mỗi nhóm consumer tự quản lý compute và workload. Khi data lake file được cập nhật hoặc producer commit dữ liệu mới, consumer có thể nhìn thấy dữ liệu mới theo cơ chế chia sẻ và metadata tương ứng.

## 29. So sánh các lựa chọn chia sẻ dữ liệu

| Nhu cầu | Lựa chọn | Khi phù hợp |
|---|---|---|
| Query file S3 cùng local Redshift table | Redshift Spectrum | Cần kết hợp data lake và warehouse trong SQL |
| Chia sẻ live Redshift tables/views giữa warehouse | Redshift datashare | Consumer cần dữ liệu mới mà không copy |
| Chia sẻ data lake với quyền tập trung database/table/column/row | Glue Data Catalog + Lake Formation | Nhiều analytics service cùng dùng S3 |
| Phân phối data product cho subscriber bên ngoài | AWS Data Exchange datashare | Cần quản lý subscription/licensing |
| Tạo bản sao dữ liệu độc lập | ETL, UNLOAD/COPY hoặc replication | Consumer cần snapshot, biến đổi hoặc vận hành độc lập |
| Chuyển file theo lịch | AWS DataSync/Glue ETL | Cần đồng bộ hoặc biến đổi dữ liệu thay vì query trực tiếp |

Không có một dịch vụ duy nhất giải quyết mọi dạng sharing. Chọn theo nguồn dữ liệu, độ mới, yêu cầu copy, governance, Region, compute và chi phí.

## 30. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| AccessDenied khi query Spectrum | Role thiếu S3/Glue/KMS permission hoặc trust policy sai | Kiểm tra role gắn với cluster/namespace, bucket/key policy và catalog permission |
| Không tìm thấy external schema/table | Sai catalog database, Region hoặc metadata chưa được đăng ký | Kiểm tra SVV_EXTERNAL_SCHEMAS, SVV_EXTERNAL_TABLES và Glue catalog |
| Query scan quá nhiều dữ liệu | Thiếu partition predicate, file row-oriented hoặc chọn quá nhiều cột | Thêm filter partition, chuyển Parquet/ORC và chọn cột cần thiết |
| Query planning chậm | Nhiều partition/file và Glue metadata lớn | Tối ưu partition, catalog statistics và layout |
| Join plan không tốt | External table thiếu numRows hoặc statistics | Cập nhật TABLE PROPERTIES numRows, xem EXPLAIN |
| Partition mới không xuất hiện | Chưa cập nhật catalog hoặc external partition metadata | Thêm partition bằng Glue/DDL/crawler phù hợp |
| Consumer không thấy datashare | Producer chưa grant/authorize hoặc consumer chưa associate | Kiểm tra producer/consumer handshake và namespace |
| CREATE DATABASE FROM DATASHARE lỗi | Sai account ID, namespace GUID hoặc share name | Xác minh datashare ARN và producer namespace |
| User consumer không query được | Thiếu USAGE database/schema hoặc object-level grant | Kiểm tra quyền consumer database và WITH PERMISSIONS |
| Cross-account share không hoạt động | Producer/consumer chưa encryption hoặc authorization thiếu | Kiểm tra encryption, account authorization và association |
| Cross-Region query đắt hoặc chậm | Data transfer và latency tăng | Đánh giá Region consumer, materialized view hoặc bản sao cục bộ |
| Data lake table trong datashare lỗi | Producer role không có SELECT hoặc Lake Formation chưa cấp quyền | Kiểm tra IAM role, catalog, Lake Formation grant và object metadata |

## 31. Checklist production

- [ ] Đã xác định dữ liệu cần query là S3 external data hay Redshift database object.
- [ ] External schema trỏ đúng Glue/Athena/Hive catalog và Region.
- [ ] IAM role được gắn đúng cluster/namespace và chỉ có quyền cần thiết.
- [ ] S3 bucket/object, KMS key và Glue catalog policy cho phép truy cập.
- [ ] External table schema, location, format và partition khớp dữ liệu thật.
- [ ] Partition key phản ánh query pattern và không tạo cardinality quá cao.
- [ ] File format Parquet/ORC, kích thước file và compression đã được benchmark.
- [ ] Query plan xác nhận predicate/aggregation pushdown ở mức có thể.
- [ ] External table có numRows phù hợp để optimizer lập kế hoạch.
- [ ] Có monitoring cho bytes scan, files, partitions và planning time.
- [ ] Datashare chỉ chứa schema/table/view đã phê duyệt.
- [ ] Producer đã grant object permissions và consumer đúng namespace/account.
- [ ] Cross-account share đã authorize và consumer đã associate.
- [ ] Producer/consumer encryption đáp ứng yêu cầu.
- [ ] Consumer database và user/role permissions được cấu hình rõ.
- [ ] Lake Formation được dùng nếu cần centralized row/column governance.
- [ ] Cross-Region transfer và chi phí scan được đưa vào ngân sách.
- [ ] Có quy trình revoke share/association khi hết nhu cầu.
- [ ] CloudTrail/audit logs đủ để truy vết quyền và truy cập dữ liệu.

## 32. Ghi nhớ

Redshift Spectrum cho phép truy vấn dữ liệu ngoài warehouse, thường là file trên S3, thông qua external schema và external table được mô tả trong Glue/Athena Data Catalog hoặc Hive metastore. IAM role cấp quyền đọc catalog và S3; partition pruning, Parquet/ORC, predicate pushdown, file size và statistics quyết định nhiều tới hiệu năng và chi phí scan.

Redshift data sharing dùng datashare để chia sẻ live database objects giữa producer và consumer cluster/workgroup mà không cần copy dữ liệu warehouse. Cross-account sharing cần producer authorize và consumer associate; cross-Region có chi phí transfer. External data lake tables cũng có thể được đưa vào datashare trực tiếp hoặc thông qua late-binding view khi cấu hình quyền nguồn dữ liệu phù hợp.

Lake Formation bổ sung governance tập trung cho dữ liệu S3 và một số luồng datashare. Thiết kế production cần phân biệt quyền IAM, catalog, Lake Formation và quyền SQL; theo dõi bytes scan, partition, file, query usage và chi phí. Chọn Spectrum để query data lake, datashare để phân phối dữ liệu warehouse đã quản trị, và kết hợp cả hai khi kiến trúc cần một data product dùng chung.

## Tài liệu tham khảo

- [Amazon Redshift Spectrum Overview](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-overview.html)
- [External Schemas in Amazon Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-schemas.html)
- [External Tables for Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-tables.html)
- [CREATE EXTERNAL SCHEMA](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_SCHEMA.html)
- [CREATE EXTERNAL TABLE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_EXTERNAL_TABLE.html)
- [IAM Policies for Amazon Redshift Spectrum](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-iam-policies.html)
- [Redshift Spectrum Query Performance](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-external-performance.html)
- [Redshift Spectrum Metrics](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-metrics.html)
- [SYS_EXTERNAL_QUERY_DETAIL](https://docs.aws.amazon.com/redshift/latest/dg/SYS_EXTERNAL_QUERY_DETAIL.html)
- [Redshift Spectrum Limitations](https://docs.aws.amazon.com/redshift/latest/dg/c-spectrum-considerations.html)
- [Redshift Spectrum and AWS Lake Formation](https://docs.aws.amazon.com/redshift/latest/dg/spectrum-lake-formation.html)
- [Data Sharing in Amazon Redshift](https://docs.aws.amazon.com/redshift/latest/dg/datashare-overview.html)
- [Creating Datashares](https://docs.aws.amazon.com/redshift/latest/dg/datashare-creation.html)
- [CREATE DATASHARE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_DATASHARE.html)
- [GRANT for Datashare Permissions](https://docs.aws.amazon.com/redshift/latest/dg/r_GRANT.html)
- [Authorizing a Datashare](https://docs.aws.amazon.com/redshift/latest/dg/writes-authorizing.html)
- [Sharing Data Across AWS Accounts](https://docs.aws.amazon.com/redshift/latest/dg/across-account.html)
- [Associating a Datashare from a Different AWS Account](https://docs.aws.amazon.com/redshift/latest/dg/writes-associating.html)
- [CREATE DATABASE from DATASHARE](https://docs.aws.amazon.com/redshift/latest/dg/r_CREATE_DATABASE.html)
- [Sharing Data Across AWS Regions](https://docs.aws.amazon.com/redshift/latest/dg/across-region.html)
- [Adding Data Lake Tables to a Datashare](https://docs.aws.amazon.com/redshift/latest/dg/create-datashare-external-views.html)
- [Considerations for Sharing Data Lake Tables](https://docs.aws.amazon.com/redshift/latest/dg/considerations-datashare-datalake.html)
- [Lake Formation-Managed Datashares](https://docs.aws.amazon.com/redshift/latest/dg/lf_datashare_overview.html)
