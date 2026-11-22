# Amazon Athena và truy vấn dữ liệu S3 bằng SQL

Khi dữ liệu đã được tập trung trong Amazon S3, nhóm phân tích thường cần trả lời câu hỏi nghiệp vụ mà không muốn dựng và vận hành một cụm database riêng chỉ để chạy truy vấn. Amazon Athena cung cấp cách tiếp cận serverless: người dùng gửi câu lệnh SQL, Athena đọc dữ liệu tại vị trí lưu trữ được hỗ trợ, thực thi truy vấn và ghi kết quả vào Amazon S3. Nhóm không phải cấp phát máy chủ truy vấn hoặc quản lý cluster trong thời gian không sử dụng.

Athena đặc biệt hữu ích khi dữ liệu được lưu dưới dạng Parquet, ORC, JSON, CSV, Avro hoặc các định dạng được hỗ trợ khác trên S3. Dịch vụ tích hợp với AWS Glue Data Catalog để tra cứu schema và partition, đồng thời có thể phối hợp với AWS Lake Formation để quản trị quyền dữ liệu. Nhờ đó, analyst có thể dùng SQL để khám phá dữ liệu raw, truy vấn curated dataset, tạo bảng dẫn xuất và chia sẻ kết quả với công cụ BI.

Serverless không có nghĩa truy vấn tự động nhanh hoặc miễn phí. Chi phí Athena phụ thuộc mô hình sử dụng và lượng dữ liệu được xử lý; truy vấn quét quá nhiều file, chọn mọi cột hoặc bỏ qua partition có thể tốn kém. Một kiến trúc hiệu quả cần tổ chức file, schema, partition, workgroup, quyền truy cập và vị trí lưu kết quả ngay từ đầu.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: lựa chọn dịch vụ phù hợp, xây dựng hệ thống có khả năng giám sát, bảo mật, phục hồi và kiểm soát chi phí. Trọng tâm là cách Athena truy vấn dữ liệu S3 bằng SQL, cách quản lý catalog và workgroup, tối ưu hiệu năng, bảo vệ dữ liệu và vận hành truy vấn trong môi trường nhiều nhóm.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích kiến trúc serverless của Amazon Athena và cách dịch vụ đọc dữ liệu trên S3.
- Phân biệt dữ liệu nguồn, metadata trong Glue Data Catalog và kết quả truy vấn.
- Tạo external table, khai báo schema, partition và định dạng dữ liệu.
- Viết SQL để lọc, tổng hợp, join và phân tích dữ liệu trên S3.
- Dùng CTAS, INSERT INTO và UNLOAD trong các kịch bản được hỗ trợ.
- Quản lý query bằng workgroup, output location, encryption và giới hạn dữ liệu quét.
- Kết hợp IAM, S3 policy, Lake Formation và KMS để kiểm soát quyền truy cập.
- Tối ưu chi phí và hiệu năng bằng Parquet, compression, partition pruning và file compaction.
- Nhận diện lỗi thường gặp và thiết kế quy trình vận hành Athena.

## 2. Amazon Athena là gì?

### 2.1. Dịch vụ truy vấn serverless

Amazon Athena là dịch vụ phân tích tương tác cho phép chạy SQL trên dữ liệu được lưu ở các nguồn mà Athena hỗ trợ, phổ biến nhất là Amazon S3. Athena quản lý hạ tầng thực thi truy vấn; người dùng tập trung vào SQL, schema, dữ liệu và cách kiểm soát workload.

Đặc điểm chính:

- Không cần tạo hoặc duy trì query cluster cho mô hình truy vấn serverless phổ biến.
- Có thể đọc nhiều định dạng dữ liệu trên S3.
- Tích hợp AWS Glue Data Catalog để tra cứu database, table, column và partition.
- Hỗ trợ SQL dựa trên hệ sinh thái Presto/Trino, với các khác biệt theo engine version và tính năng Athena.
- Có thể tạo table và ghi dữ liệu dẫn xuất trên S3 qua các câu lệnh được hỗ trợ.
- Có thể dùng workgroup để tách workload, cấu hình output, kiểm soát truy vấn và theo dõi chi phí.
- Có thể mở rộng truy vấn sang nguồn dữ liệu khác qua federated query connector được hỗ trợ.

Athena phù hợp với truy vấn ad hoc, data exploration, phân tích log, báo cáo theo lô, kiểm tra dữ liệu và truy vấn lake. Với workload BI có tần suất cao, độ trễ rất thấp hoặc cần quản lý concurrency chặt chẽ, cần đánh giá thêm Redshift hoặc các lựa chọn capacity của Athena.

### 2.2. Athena không phải database truyền thống

Trong database truyền thống, dữ liệu thường được nạp vào storage do database quản lý. Với Athena, dữ liệu có thể tiếp tục nằm trong S3; Athena đọc object theo metadata và SQL mà người dùng cung cấp.

Điều này tạo ra một số khác biệt:

- Tạo external table chủ yếu đăng ký metadata và location; không nhất thiết copy dữ liệu.
- Xóa table metadata không đồng nghĩa xóa object trong S3.
- Thay đổi object bên dưới có thể ảnh hưởng truy vấn kế tiếp.
- Hiệu năng phụ thuộc mạnh vào file format, kích thước file, partition và lượng dữ liệu cần đọc.
- Athena không tự cung cấp mọi tính năng transaction/update như một hệ quản trị cơ sở dữ liệu quan hệ.

Với dữ liệu dạng file append-only, external table thường đủ. Nếu cần update, delete, merge, snapshot và schema evolution, hãy đánh giá table format như Apache Iceberg cùng engine và phiên bản hỗ trợ.

### 2.3. Athena và các dịch vụ liên quan

| Thành phần | Vai trò |
|---|---|
| Amazon S3 | Lưu object dữ liệu và kết quả truy vấn |
| AWS Glue Data Catalog | Lưu metadata database, table, schema và partition |
| AWS Lake Formation | Quản trị quyền truy cập data lake ở mức database/table và các bộ lọc được hỗ trợ |
| Amazon Athena | Thực thi SQL trên dữ liệu |
| AWS Glue ETL | Làm sạch, chuyển đổi, compact và chuẩn hóa dữ liệu |
| Amazon QuickSight | Xây dựng dashboard và phân tích BI |
| Amazon Redshift | Data warehouse cho workload phân tích có mô hình và yêu cầu vận hành riêng |
| AWS KMS | Quản lý khóa mã hóa khi dùng SSE-KMS hoặc mã hóa kết quả |

Các dịch vụ này bổ sung cho nhau. Glue Data Catalog mô tả dữ liệu; Athena thực thi SQL; S3 giữ object. Lake Formation và IAM kiểm soát quyền. Không nên nhầm metadata table với chính các file dữ liệu.

## 3. Kiến trúc và luồng thực thi truy vấn

### 3.1. Luồng cơ bản

Một truy vấn Athena thường đi qua các bước:

1. Người dùng gửi SQL từ Athena console, CLI, SDK hoặc ứng dụng BI.
2. Athena xác định workgroup và kiểm tra cấu hình, quyền gọi API, giới hạn và output location.
3. Athena tra cứu metadata trong Glue Data Catalog hoặc catalog/connector được cấu hình.
4. Query engine lập kế hoạch đọc các file và partition phù hợp.
5. Athena đọc dữ liệu từ S3 hoặc nguồn liên kết, thực thi phép lọc, join, aggregate và các biểu thức SQL.
6. Kết quả được trả về qua API và thường được ghi vào S3 output location của workgroup.
7. Người dùng xem kết quả, tải file hoặc dùng kết quả từ ứng dụng khác.

~~~mermaid
flowchart TD
    U[Analyst / BI / SDK] --> W[Athena Workgroup]
    W --> Q[Query Engine]
    Q --> C[Glue Data Catalog]
    C --> M[Schema và partition metadata]
    Q --> S3[Amazon S3 data lake]
    Q --> F[Federated connector nếu được cấu hình]
    Q --> R[SQL execution]
    R --> O[S3 query results]
    R --> API[GetQueryResults / ứng dụng]
    LF[Lake Formation và IAM] -. kiểm soát quyền .-> Q
    KMS[AWS KMS] -. mã hóa .-> S3
~~~

Sơ đồ mô tả logic tổng quát. Cách Athena truy cập dữ liệu và metadata phụ thuộc loại catalog, connector, Lake Formation, IAM và cấu hình của workgroup.

### 3.2. Storage và compute tách biệt

S3 lưu dữ liệu độc lập với compute thực thi SQL. Vì vậy:

- Có thể dùng Athena khi cần mà không phải giữ một cluster truy vấn chạy liên tục.
- Nhiều workgroup có thể truy vấn cùng dataset với cấu hình và quyền khác nhau.
- Glue, EMR, Redshift Spectrum hoặc engine khác có thể tiêu thụ dữ liệu trên S3 nếu có quyền và hỗ trợ định dạng.
- Dữ liệu gốc có thể được giữ lại trong raw zone, còn curated zone được tối ưu cho truy vấn.

Sự tách biệt này giúp linh hoạt nhưng đòi hỏi quản lý schema và file chặt chẽ. Nếu producer thay đổi cấu trúc object mà không cập nhật catalog hoặc data contract, truy vấn có thể lỗi hoặc diễn giải dữ liệu sai.

### 3.3. SQL engine và phiên bản

Athena cung cấp các engine version được AWS quản lý. SQL dựa trên Presto/Trino nhưng có khác biệt theo engine version, loại table và tính năng Athena. Workgroup có thể cấu hình engine version hoặc dùng lựa chọn được AWS quản lý theo cấu hình hiện hành.

Trước khi dùng cú pháp mới, hàm đặc thù hoặc tính năng Iceberg:

- Kiểm tra engine version của workgroup.
- Xác nhận tính năng có được hỗ trợ ở Region đang dùng.
- Thử truy vấn trên dữ liệu đại diện.
- Đọc tài liệu tương thích của connector/table format.
- Tránh giả định cú pháp của PostgreSQL, MySQL hoặc Spark SQL sẽ hoạt động giống hệt trong Athena.

## 4. Chuẩn bị môi trường Athena

### 4.1. Chọn Region và account

Athena được sử dụng theo Region. Hãy xác định:

- Region nơi triển khai data lake.
- Account sở hữu bucket S3.
- Account chạy Athena và Glue Data Catalog.
- Account/role của người dùng truy vấn.
- Vị trí lưu kết quả truy vấn.
- VPC endpoint hoặc private access nếu tổ chức yêu cầu.

Khi bucket, catalog và Athena nằm ở các account hoặc Region khác nhau, cần kiểm tra hỗ trợ tích hợp, quyền cross-account, KMS key và chi phí data transfer. Tránh mặc định mọi quyền trong account truy vấn sẽ tự động áp dụng lên bucket nguồn.

### 4.2. Chuẩn bị S3 bucket cho dữ liệu

Data bucket cần có:

- Cấu trúc prefix và zone rõ ràng.
- Object format và compression đã thống nhất.
- Quyền đọc cho role truy vấn.
- Mã hóa theo chính sách tổ chức.
- Lifecycle và retention phù hợp.
- Versioning hoặc replication khi yêu cầu phục hồi.
- Catalog table trỏ tới đúng location.

Không nên đặt dữ liệu nguồn và query result trong cùng prefix. Tách riêng result bucket hoặc ít nhất một prefix chuyên dụng giúp kiểm soát retention, quyền truy cập và chi phí dễ hơn.

### 4.3. Chuẩn bị query result location

Athena cần vị trí để lưu kết quả truy vấn. Có thể cấu hình output location ở workgroup hoặc chỉ định theo request nếu workgroup cho phép. Trong môi trường dùng chung, nên cấu hình tập trung tại workgroup và bật tùy chọn ghi đè cấu hình phía client để tránh người dùng ghi kết quả vào bucket ngoài kiểm soát.

Ví dụ:

~~~text
s3://company-athena-results/analytics-team/
~~~

Bucket kết quả có thể chứa dữ liệu nhạy cảm được trích xuất từ lake. Vì vậy cần:

- Chặn public access.
- Cấp quyền ghi cho principal thực thi query và quyền đọc cho người dùng cần xem kết quả.
- Bật mã hóa phù hợp, có thể là SSE-S3 hoặc SSE-KMS.
- Cấu hình lifecycle xóa kết quả hết hạn theo yêu cầu.
- Hạn chế quyền xóa hoặc chia sẻ object.
- Theo dõi truy cập và chi phí storage.

Không xem query result bucket là thư mục tạm vô hại. Một câu SELECT có thể trả về PII hoặc dữ liệu tài chính mà người dùng không được phép chia sẻ rộng.

### 4.4. Tạo database trong Glue Data Catalog

Có thể tạo database trong Athena console hoặc qua DDL:

~~~sql
CREATE DATABASE IF NOT EXISTS analytics;
~~~

Database trong Glue Data Catalog là namespace metadata. Nó không tạo một relational database server và không tự cấp quyền truy cập vào S3 object.

Có thể tổ chức database theo domain hoặc zone:

- raw_sales
- standardized_sales
- curated_commerce
- curated_finance

Tên database và table nên có quy tắc thống nhất, tránh tên trùng hoặc phụ thuộc vào môi trường cá nhân.

## 5. Tạo external table trên dữ liệu S3

### 5.1. External table là gì?

External table mô tả cấu trúc logic của dữ liệu đang nằm bên ngoài Athena, thường là object trên S3. Metadata gồm tên cột, kiểu dữ liệu, định dạng, SerDe, partition và location.

Khi tạo external table:

- Athena ghi metadata vào Glue Data Catalog.
- Dữ liệu vẫn ở vị trí S3 được khai báo.
- Query engine dùng metadata để diễn giải file.
- Thay đổi table metadata không tự động chuyển đổi hoặc ghi lại file nguồn.

### 5.2. Ví dụ tạo table Parquet

Giả sử dữ liệu đơn hàng nằm theo cấu trúc:

~~~text
s3://company-data-lake/curated/orders/
  order_date=2026-11-19/
    region=ap-southeast-1/
      part-00001.parquet
  order_date=2026-11-20/
    region=ap-southeast-1/
      part-00002.parquet
~~~

Có thể khai báo table:

~~~sql
CREATE EXTERNAL TABLE IF NOT EXISTS curated_commerce.orders (
    order_id       string,
    customer_id    string,
    order_ts       timestamp,
    status         string,
    currency       string,
    total_amount   decimal(18, 2)
)
PARTITIONED BY (
    order_date string,
    region string
)
STORED AS PARQUET
LOCATION 's3://company-data-lake/curated/orders/';
~~~

Các cột order_date và region được khai báo là partition columns, không nằm trong danh sách cột dữ liệu thông thường trong phần đầu của định nghĩa. Tên partition phải khớp với cấu trúc dữ liệu và catalog.

Định nghĩa schema phải khớp với nội dung Parquet. Nếu cột trong file có kiểu khác, tên khác hoặc thứ tự/metadata không tương thích, query có thể lỗi hoặc trả dữ liệu sai. Với Parquet, schema được lưu trong file; khai báo table không tự chuyển kiểu dữ liệu vật lý.

### 5.3. Định dạng dữ liệu và SerDe

SerDe (serializer/deserializer) giúp Athena diễn giải file thành hàng và cột. Với các định dạng phổ biến:

| Định dạng | Đặc điểm | Lưu ý |
|---|---|---|
| Parquet | Columnar, hỗ trợ compression và đọc chọn cột | Thường phù hợp analytics |
| ORC | Columnar, có metadata phục vụ tối ưu | Kiểm tra tương thích engine |
| JSON | Linh hoạt, phù hợp event và dữ liệu lồng nhau | Schema có thể không đồng nhất |
| CSV/TSV | Dễ trao đổi và debug | Cần xử lý delimiter, quote, escape và header |
| Avro | Có schema và serialization theo record | Cần khai báo SerDe/schema phù hợp |
| Text | Dạng dòng hoặc log | Có thể cần Regex SerDe hoặc xử lý trước |

Nếu dữ liệu đầu vào lộn xộn, schema không ổn định hoặc file CSV có quote/newline phức tạp, nên chuẩn hóa bằng Glue trước khi đưa vào curated zone.

### 5.4. Tạo table bằng Glue crawler

Glue crawler có thể quét S3, suy luận schema và tạo/cập nhật table metadata. Crawler hữu ích cho discovery hoặc nguồn dữ liệu mới, nhưng cần cấu hình include path, classifier, grouping và update behavior cẩn thận.

Rủi ro khi dùng crawler không kiểm soát:

- Nhiều schema khác nhau trong cùng prefix làm tạo nhiều table.
- Cột bị suy luận thành kiểu không mong muốn.
- Partition hoặc table được tạo trùng.
- Crawler quét cả query result hoặc temporary output.
- Schema drift làm consumer cũ lỗi.

Với dataset production, nên có data contract và quy trình review schema. Crawler có thể hỗ trợ khám phá, còn schema chính thức nên được quản lý có kiểm soát.

## 6. Partition và partition pruning

### 6.1. Vì sao cần partition?

Partition chia dataset thành các nhóm vật lý theo thuộc tính, thường là ngày, tháng, khu vực hoặc loại sự kiện. Khi truy vấn có điều kiện trên partition key, Athena có thể bỏ qua các partition không liên quan.

Ví dụ, query doanh thu ngày 20-11-2026 không cần đọc tất cả dữ liệu nhiều năm nếu table được partition theo order_date.

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
GROUP BY region;
~~~

Điều kiện trên partition column giúp partition pruning. Nếu query chỉ lọc order_ts trong khi partition key là order_date, Athena có thể không loại bỏ partition hiệu quả. Hãy dùng predicate trên partition key và cột dữ liệu theo đúng semantics.

### 6.2. Chọn partition key

Partition key nên được chọn từ mẫu truy vấn thực tế:

- Ngày hoặc tháng cho dữ liệu có chiều thời gian.
- Region, country hoặc business unit nếu thường xuyên lọc theo các chiều này.
- Loại event khi mỗi loại có lượng dữ liệu đủ lớn và query thường lọc theo loại.

Tránh partition theo giá trị có cardinality rất cao như user ID, request ID hoặc transaction ID. Quá nhiều partition tạo metadata lớn, tăng thời gian planning và gây small files.

Không phải dataset nào cũng cần partition. Với dataset nhỏ, query thường quét toàn bộ hoặc dữ liệu không có chiều lọc ổn định, partition có thể làm kiến trúc phức tạp hơn lợi ích mang lại.

### 6.3. Đăng ký partition bằng MSCK REPAIR TABLE

Với Hive-style partition path, có thể dùng:

~~~sql
MSCK REPAIR TABLE curated_commerce.orders;
~~~

Lệnh này yêu cầu Athena phát hiện và thêm partition metadata từ cấu trúc S3 tương ứng. Nó không phải công cụ tối ưu để chạy liên tục trên một dataset có số lượng partition rất lớn. Việc phát hiện partition mới có thể tốn thời gian.

Một lựa chọn khác là thêm partition cụ thể:

~~~sql
ALTER TABLE curated_commerce.orders
ADD IF NOT EXISTS
PARTITION (
    order_date = '2026-11-20',
    region = 'ap-southeast-1'
)
LOCATION 's3://company-data-lake/curated/orders/order_date=2026-11-20/region=ap-southeast-1/';
~~~

Có thể tự động hóa cập nhật partition bằng Glue crawler, Glue job hoặc pipeline metadata. Chọn một cơ chế sở hữu rõ ràng để tránh nhiều thành phần cùng cập nhật catalog theo cách khác nhau.

### 6.4. Partition projection

Partition projection cho phép Athena suy ra partition values từ quy tắc cấu hình thay vì lưu và truy xuất từng partition trong Glue Data Catalog. Tính năng này phù hợp khi partition có pattern đều và số lượng lớn.

Ví dụ table partition theo ngày:

~~~sql
TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.order_date.type' = 'date',
  'projection.order_date.range' = '2025-01-01,NOW',
  'projection.order_date.format' = 'yyyy-MM-dd',
  'projection.order_date.interval' = '1',
  'projection.order_date.interval.unit' = 'DAYS',
  'storage.location.template' =
    's3://company-data-lake/curated/orders/order_date=${order_date}/'
);
~~~

Đây là phần thuộc tính bổ sung cho table đã khai báo partition column order_date. Với nhiều partition key, cần khai báo projection cho từng key và template phải khớp cấu trúc S3. Nếu range quá rộng hoặc location template sai, Athena có thể lập kế hoạch đọc nhiều đường dẫn không tồn tại.

### 6.5. Partition projection hay catalog partition?

| Tiêu chí | Catalog partition | Partition projection |
|---|---|---|
| Metadata | Lưu từng partition trong catalog | Tính từ quy tắc |
| Phù hợp | Partition không đều hoặc cần metadata tường minh | Partition theo pattern đều, số lượng lớn |
| Cập nhật | Cần crawler, DDL hoặc pipeline cập nhật | Điều chỉnh projection properties |
| Rủi ro | Catalog nhiều partition | Range/template sai gây scan location không mong muốn |

Không dùng partition projection chỉ vì số partition lớn. Trước hết cần xác định query pattern, cách đặt folder và khả năng bảo trì.

## 7. Viết SQL trên dữ liệu S3

### 7.1. Lọc, chọn cột và giới hạn kết quả

Ví dụ truy vấn một số đơn hàng:

~~~sql
SELECT
    order_id,
    order_ts,
    status,
    total_amount
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
  AND region = 'ap-southeast-1'
  AND status = 'PAID'
ORDER BY total_amount DESC
LIMIT 100;
~~~

Chỉ chọn cột cần dùng giúp columnar format như Parquet/ORC đọc ít dữ liệu hơn. LIMIT giới hạn số hàng trả về, nhưng không đảm bảo giảm lượng dữ liệu phải quét nếu query vẫn cần đọc toàn bộ partition để lọc hoặc sắp xếp.

### 7.2. Tổng hợp theo thời gian

~~~sql
SELECT
    order_date,
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS gross_revenue,
    AVG(total_amount) AS average_order_value
FROM curated_commerce.orders
WHERE order_date BETWEEN '2026-11-01' AND '2026-11-20'
  AND status = 'PAID'
GROUP BY order_date, region
ORDER BY order_date, region;
~~~

Nếu order_date là partition key kiểu string theo định dạng ISO yyyy-MM-dd, điều kiện dạng chuỗi có thể lọc đúng theo thứ tự ngày. Với kiểu partition khác, hãy dùng giá trị và biểu thức khớp schema.

### 7.3. Join hai bảng

Ví dụ join đơn hàng và khách hàng:

~~~sql
SELECT
    o.order_id,
    o.order_date,
    o.total_amount,
    c.customer_segment
FROM curated_commerce.orders o
JOIN curated_commerce.customer_profile c
  ON o.customer_id = c.customer_id
WHERE o.order_date = '2026-11-20';
~~~

Join trên S3 có thể tốn kém nếu cả hai bảng lớn hoặc không được lọc sớm. Hãy:

- Lọc partition trước khi join.
- Chỉ chọn cột cần thiết.
- Kiểm tra key có kiểu dữ liệu thống nhất.
- Tránh join làm nhân bản bản ghi ngoài ý muốn.
- Cân nhắc broadcast/hash strategy theo khả năng engine và kích thước dữ liệu.
- Tạo curated dataset nếu cùng một phép join được lặp lại thường xuyên.

### 7.4. Xử lý dữ liệu null và kiểu dữ liệu

Athena hỗ trợ các hàm SQL như COALESCE, NULLIF, CAST, TRY_CAST, CASE, hàm chuỗi, ngày giờ và aggregate theo engine version.

Ví dụ chuyển dữ liệu chuỗi sang số an toàn:

~~~sql
SELECT
    order_id,
    TRY_CAST(raw_amount AS DECIMAL(18, 2)) AS amount
FROM raw_sales.orders_csv
WHERE raw_amount IS NOT NULL;
~~~

TRY_CAST trả NULL khi không thể chuyển kiểu theo semantics của engine. Cần thống kê số dòng chuyển đổi thất bại để không âm thầm làm mất dữ liệu trong báo cáo.

### 7.5. Xử lý JSON

Với JSON có cấu trúc không đồng nhất, có thể dùng kiểu dữ liệu ROW, ARRAY, MAP hoặc các hàm JSON theo cú pháp được engine hỗ trợ. Nếu schema phức tạp và được dùng thường xuyên, nên chuẩn hóa bằng Glue sang Parquet thay vì phân tích JSON lặp lại trong mọi query.

Ví dụ đọc trường từ JSON:

~~~sql
SELECT
    json_extract_scalar(payload, '$.eventType') AS event_type,
    json_extract_scalar(payload, '$.customerId') AS customer_id
FROM raw_events.application_logs
WHERE ingest_date = '2026-11-20';
~~~

Tên cột payload và cấu trúc JSON chỉ là ví dụ. Hãy kiểm tra file có JSON hợp lệ, một object trên mỗi record hay cấu trúc khác, và khai báo SerDe phù hợp.

## 8. Tạo và ghi dữ liệu bằng CTAS, INSERT INTO và UNLOAD

### 8.1. CTAS

CREATE TABLE AS SELECT (CTAS) tạo table mới từ kết quả truy vấn và ghi dữ liệu ra S3 theo format/partition được chọn. Đây là cách phổ biến để tạo curated dataset hoặc chuyển CSV/JSON sang Parquet.

~~~sql
CREATE TABLE curated_commerce.daily_paid_orders
WITH (
    format = 'PARQUET',
    external_location = 's3://company-data-lake/curated/daily-paid-orders/',
    partitioned_by = ARRAY['order_date']
) AS
SELECT
    order_id,
    customer_id,
    total_amount,
    order_date
FROM standardized_sales.orders
WHERE status = 'PAID';
~~~

Với CTAS có partition, các partition columns cần được đặt ở cuối danh sách SELECT theo yêu cầu của Athena. external_location phải là vị trí phù hợp và không được chứa dữ liệu hiện hữu theo điều kiện CTAS. Kiểm tra output trước khi chạy lại; không dùng cùng một location như thể CTAS tự động ghi đè an toàn.

CTAS tạo metadata table và file output. Cần quản lý quyền ghi S3, Glue Catalog, encryption, partition và lifecycle cho dataset mới.

### 8.2. INSERT INTO

Với table format và loại table được hỗ trợ, INSERT INTO có thể thêm dữ liệu vào table:

~~~sql
INSERT INTO curated_commerce.daily_paid_orders
SELECT
    order_id,
    customer_id,
    total_amount,
    order_date
FROM standardized_sales.orders
WHERE order_date = '2026-11-20'
  AND status = 'PAID';
~~~

Với Hive external table trên file, thao tác này thường ghi thêm file mới; nó không phải thao tác update từng row như database OLTP. Nếu chạy lại cùng batch mà không có kiểm soát, có thể tạo dữ liệu trùng. Hãy dùng batch ID, partition overwrite theo quy trình được hỗ trợ hoặc table format có semantics cập nhật phù hợp.

### 8.3. UNLOAD

UNLOAD xuất kết quả truy vấn ra S3 theo định dạng được hỗ trợ. Nó hữu ích khi cần tạo file kết quả có cấu trúc để hệ thống khác tiêu thụ:

~~~sql
UNLOAD (
    SELECT
        region,
        SUM(total_amount) AS revenue
    FROM curated_commerce.orders
    WHERE order_date = '2026-11-20'
    GROUP BY region
)
TO 's3://company-data-exports/daily-revenue/'
WITH (
    format = 'PARQUET',
    compression = 'SNAPPY'
);
~~~

Kiểm tra cú pháp và tùy chọn output theo engine version. Prefix đích cần đáp ứng điều kiện của UNLOAD và không được coi là nơi ghi đè tùy ý. Bảo vệ file export vì dữ liệu có thể được chia sẻ ra ngoài data lake.

### 8.4. Views

View lưu câu SQL để tái sử dụng logic truy vấn và tạo lớp abstraction cho consumer:

~~~sql
CREATE OR REPLACE VIEW curated_commerce.paid_orders_view AS
SELECT
    order_id,
    order_date,
    region,
    total_amount
FROM curated_commerce.orders
WHERE status = 'PAID';
~~~

View không nhất thiết lưu bản sao dữ liệu. Khi query view, Athena thực thi câu SQL định nghĩa view trên dữ liệu nguồn. Nếu view chứa join và transform nặng, nhiều lần truy vấn có thể lặp lại chi phí. Với báo cáo lặp thường xuyên, hãy đánh giá CTAS hoặc dataset tổng hợp.

## 9. Workgroup và quản lý workload

### 9.1. Workgroup là gì?

Workgroup là đơn vị tổ chức các truy vấn Athena. Có thể dùng workgroup để tách nhóm người dùng, môi trường hoặc workload và áp dụng cấu hình riêng:

- Query result location.
- Mã hóa kết quả.
- Engine version.
- CloudWatch metrics.
- Per-query data usage control.
- Các giới hạn và cấu hình liên quan.

Ví dụ:

| Workgroup | Mục đích | Cấu hình khuyến nghị |
|---|---|---|
| analyst-ad-hoc | Truy vấn khám phá | Giới hạn bytes scanned, result retention ngắn |
| finance-reporting | Báo cáo tài chính | Quyền chặt, output mã hóa, audit đầy đủ |
| data-engineering | ETL và CTAS | Quyền ghi curated prefix, engine được kiểm soát |
| development | Thử nghiệm | Ngân sách và giới hạn query thấp, dữ liệu không nhạy cảm |

### 9.2. Enforce workgroup configuration

Workgroup có thể cấu hình để ghi đè các thiết lập phía client. Trong môi trường doanh nghiệp, nên dùng cơ chế enforce để người dùng không tự chuyển output location sang bucket ngoài kiểm soát hoặc tắt encryption đã quy định.

Hãy xác định rõ ai có quyền:

- Tạo và sửa workgroup.
- Thay đổi engine version.
- Thay đổi query result location.
- Thay đổi giới hạn dữ liệu.
- Xem hoặc chạy query trong workgroup.

Quyền quản trị workgroup có thể ảnh hưởng tới chi phí, bảo mật và nơi lưu kết quả, nên không nên cấp rộng.

### 9.3. Giới hạn dữ liệu quét

Workgroup có thể áp dụng giới hạn dữ liệu được quét cho một query hoặc cảnh báo/kiểm soát theo các tùy chọn được hỗ trợ. Dùng giới hạn để bảo vệ ngân sách trước query vô tình quét toàn bộ lake.

Giới hạn cần phù hợp với workload. Nếu đặt quá thấp, query hợp lệ có thể thất bại; nếu quá cao, giới hạn không còn nhiều giá trị bảo vệ. Theo dõi bytes scanned và điều chỉnh theo nhóm query.

### 9.4. Query history và metrics

Athena cung cấp query execution details và tích hợp CloudWatch metrics. Nên theo dõi:

- Số query theo workgroup và principal.
- Query runtime và queue time.
- Data scanned.
- Failed/cancelled query.
- Query vượt ngưỡng.
- Output size và tăng trưởng result bucket.
- Mức sử dụng capacity nếu dùng mô hình capacity.

Kết hợp query history với tag/workgroup và cost allocation để xác định nhóm tạo chi phí.

## 10. Bảo mật và quản trị quyền truy cập

### 10.1. IAM permission cho Athena

Người dùng cần quyền IAM phù hợp để thao tác Athena, chẳng hạn bắt đầu query, lấy trạng thái, lấy kết quả và truy cập workgroup tương ứng. Các action cụ thể phụ thuộc cách dùng console, CLI, SDK và tính năng.

Một role chỉ có quyền athena:StartQueryExecution vẫn có thể không chạy được query nếu thiếu quyền catalog hoặc S3. Hãy xem quyền theo toàn bộ luồng:

1. Quyền Athena API và workgroup.
2. Quyền Glue Data Catalog để xem database/table/partition.
3. Quyền đọc object nguồn trên S3.
4. Quyền ghi và đọc query result trên S3.
5. Quyền sử dụng KMS key nếu object hoặc kết quả được mã hóa bằng SSE-KMS.
6. Quyền Lake Formation nếu catalog/table được quản lý bằng Lake Formation.

### 10.2. S3 permission

Để đọc dữ liệu, principal thường cần s3:ListBucket ở bucket/prefix phù hợp và s3:GetObject trên object. Để ghi query result, principal cần quyền ghi vào output location theo cấu hình. Quyền xóa object nên được cấp riêng, không tự động cấp cho analyst chỉ vì họ cần chạy SELECT.

Bucket policy có thể giới hạn truy cập theo principal, VPC endpoint, TLS hoặc điều kiện khác. Tránh dùng Principal "*" với quyền đọc/ghi rộng cho bucket data lake hoặc result.

### 10.3. Lake Formation

Khi Lake Formation quản lý data lake, quyền truy cập database/table có thể được cấp theo principal và data permission. Với các tính năng được hỗ trợ, có thể dùng LF-tag, column filter, row filter hoặc cell-level filter.

IAM vẫn cần cho phép principal gọi Athena và các dịch vụ liên quan. Lake Formation grant không tự cấp quyền đọc mọi object hoặc sử dụng mọi KMS key nếu cấu hình nền chưa phù hợp. Hãy kiểm tra mô hình permission mode, data location registration và quyền của service role.

### 10.4. Mã hóa bằng KMS

Với SSE-KMS, principal cần quyền sử dụng key theo key policy và IAM policy. Cần kiểm tra:

- Key thuộc đúng Region.
- Key policy cho phép service/principal cần thiết.
- Cross-account access có cấu hình đầy đủ.
- Query result encryption được bật theo workgroup.
- Người đọc kết quả có quyền giải mã.
- KMS key không bị disable hoặc scheduled deletion khi dữ liệu còn cần truy cập.

S3 Bucket Keys có thể giảm số lần gọi KMS trong một số kịch bản SSE-KMS. Tuy nhiên, cần đánh giá tác động đến policy và audit.

### 10.5. Bảo vệ query results

Kết quả query có thể chứa toàn bộ dữ liệu được chọn từ bảng. Hãy:

- Dùng bucket kết quả riêng và Block Public Access.
- Bật encryption.
- Giới hạn quyền đọc theo workgroup hoặc nhóm.
- Thiết lập lifecycle/retention.
- Kiểm soát chia sẻ URL và file tải xuống.
- Ghi nhận truy cập và thay đổi bucket policy.

Nếu query kết quả chứa PII, việc kiểm soát bảng nguồn bằng Lake Formation chưa đủ nếu result bucket lại cho quá nhiều người đọc.

### 10.6. Cross-account access

Khi Athena chạy ở account A và dữ liệu S3 nằm ở account B, cần cấu hình quyền cross-account ở bucket, IAM, Glue Catalog và KMS theo mô hình được hỗ trợ. Nếu Lake Formation quản trị, cần cấp cross-account data permissions và thiết lập resource link khi cần.

Không nên chỉ thêm bucket policy rồi giả định truy vấn sẽ chạy. Kiểm tra catalog location, resource policy, KMS key và quyền output location của account chạy Athena.

## 11. Tối ưu hiệu năng và chi phí

### 11.1. Hiểu mô hình chi phí

Athena có thể tính phí theo lượng dữ liệu được quét đối với mô hình on-demand phổ biến; ngoài ra còn có lựa chọn capacity và tính năng tính phí riêng theo workload. Đơn giá thay đổi theo Region và bảng giá hiện hành.

Tổng chi phí một workload Athena có thể bao gồm:

- Athena query hoặc capacity.
- S3 storage cho dữ liệu nguồn và query result.
- S3 request.
- Glue Data Catalog và các tính năng liên quan theo mô hình giá.
- KMS API request.
- Lambda và các tài nguyên của federated connector.
- Data transfer và dịch vụ khác trong pipeline.
- Glue/EMR job dùng để chuẩn hóa dữ liệu.

Không nên chỉ nhìn phí Athena để đánh giá toàn bộ chi phí analytics.

### 11.2. Parquet và ORC

Parquet và ORC thường giúp giảm bytes scanned vì dữ liệu được lưu theo cột. Nếu query chỉ đọc 5 trong 50 cột, engine có thể tránh đọc phần lớn cột không cần thiết. Compression cũng giảm dung lượng lưu và lượng dữ liệu đọc.

Một pipeline thường gặp:

1. Giữ JSON/CSV gốc ở raw zone.
2. Dùng Glue hoặc EMR chuyển sang Parquet/ORC.
3. Ghi standardized/curated dataset theo partition.
4. Cập nhật Glue Data Catalog.
5. Dùng Athena truy vấn bảng đã tối ưu.

Hãy benchmark codec và kích thước file theo workload. Compression quá mạnh có thể tăng CPU; file quá nhỏ tăng overhead.

### 11.3. Partition pruning

Điều kiện lọc partition giúp Athena bỏ qua folder không cần đọc. Query cần đưa predicate trên partition column:

~~~sql
SELECT COUNT(*)
FROM curated_commerce.orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-11-08';
~~~

Nếu partition key là string, định dạng ISO yyyy-MM-dd cho phép so sánh chuỗi theo thứ tự ngày trong phạm vi cùng định dạng. Với partition key khác kiểu hoặc format, hãy dùng predicate tương ứng.

### 11.4. Chỉ đọc cột cần thiết

Tránh SELECT * trên dataset lớn nếu chỉ cần một vài trường. Với columnar format, chọn đúng cột giúp giảm lượng dữ liệu phải đọc và xử lý.

Ví dụ:

~~~sql
SELECT order_id, total_amount
FROM curated_commerce.orders
WHERE order_date = '2026-11-20';
~~~

### 11.5. Small files và compaction

Quá nhiều file nhỏ làm tăng S3 listing, metadata và task overhead. Các cách xử lý:

- Buffer dữ liệu trước khi ghi xuống S3.
- Điều chỉnh Firehose buffer size/time.
- Compact file bằng Glue hoặc EMR.
- Chọn số partition và số writer hợp lý.
- Theo dõi kích thước file trung bình và số object mỗi partition.

File có kích thước hàng trăm MB thường là điểm khởi đầu để benchmark cho analytics, nhưng không phải giới hạn bắt buộc. Workload, concurrency và schema quyết định kích thước phù hợp.

### 11.6. Tránh scan không cần thiết

- Không chạy query không có predicate trên dataset nhiều năm khi chỉ cần một ngày.
- Không dùng ORDER BY nếu không cần sắp xếp.
- Tránh DISTINCT trên dữ liệu lớn khi có thể xử lý duplicate ở ETL.
- Lọc dữ liệu trước khi join.
- Dùng aggregate dataset cho báo cáo lặp lại.
- Đặt query limit trong workgroup.
- Dùng EXPLAIN để xem kế hoạch truy vấn khi cần.

### 11.7. CTAS và materialize kết quả

Nếu cùng một phép transform được chạy thường xuyên, CTAS có thể tạo dataset dẫn xuất đã partition và nén. Các query sau đó đọc ít dữ liệu hơn. Tuy nhiên, CTAS tạo thêm storage và pipeline maintenance; cần tính chi phí refresh, retention và dữ liệu trùng.

### 11.8. Result reuse

Athena có tính năng tái sử dụng kết quả truy vấn cho các trường hợp được hỗ trợ. Khi query và điều kiện phù hợp, hệ thống có thể trả lại kết quả đã lưu thay vì thực thi lại. Điều này có thể giảm thời gian và chi phí cho query lặp, nhưng cần cấu hình tuổi tối đa của kết quả và hiểu điều kiện cache invalidation.

Không dùng result reuse cho dữ liệu cần freshness tức thời nếu kết quả cũ không được chấp nhận. Kiểm tra workgroup, query parameters và điều kiện hỗ trợ trước khi dựa vào tính năng này.

### 11.9. Capacity reservations

Với workload có concurrency và nhu cầu ổn định, tổ chức có thể đánh giá Athena capacity reservations nếu tính năng phù hợp ở Region và loại engine. Capacity có thể giúp kiểm soát hiệu năng và tính sẵn sàng cho workload quan trọng, nhưng tạo cam kết chi phí khác mô hình trả theo dữ liệu quét.

Hãy đo concurrency, query runtime và mức sử dụng trước khi chọn. Không mua capacity chỉ dựa trên số analyst hoặc peak request mà không có dữ liệu workload.

## 12. Federated query

### 12.1. Khái niệm

Athena federated query cho phép truy vấn dữ liệu từ các nguồn ngoài S3 thông qua connector. Connector thường được triển khai bằng Lambda và có thể kết nối tới nguồn dữ liệu được hỗ trợ như relational database, document store hoặc hệ thống khác.

Lợi ích:

- Dùng một giao diện SQL cho nhiều nguồn.
- Hạn chế phải copy mọi dữ liệu về S3 trước khi khám phá.
- Có thể join dữ liệu lake với dữ liệu còn nằm trong hệ thống nguồn.

### 12.2. Những điểm cần cân nhắc

- Connector có thể cần Lambda, IAM role, network/VPC và secret riêng.
- Query có thể tạo tải trực tiếp lên database nguồn.
- Predicate pushdown và hiệu năng phụ thuộc connector.
- Dữ liệu có thể được spill tạm vào S3 theo cấu hình connector.
- Cross-account và KMS permission cần được kiểm tra.
- Chi phí gồm Athena và các tài nguyên connector/downstream.

Federated query phù hợp cho exploration hoặc truy vấn có phạm vi hợp lý. Với analytics lớn và lặp lại, ingest dữ liệu vào S3/warehouse có thể kiểm soát hiệu năng và chi phí tốt hơn.

## 13. Athena với Apache Iceberg

### 13.1. Khi nào dùng Iceberg?

Với file Parquet thuần, append đơn giản nhưng update/delete và concurrent write cần logic riêng. Apache Iceberg bổ sung metadata table, snapshot và transaction semantics theo table format, hỗ trợ schema evolution, partition evolution và các thao tác cập nhật theo engine.

Athena hỗ trợ truy vấn và một số thao tác ghi/quản lý Iceberg table theo engine version và giới hạn dịch vụ. Trước khi dùng UPDATE, DELETE, MERGE, time travel hoặc vacuum/maintenance, kiểm tra cú pháp và tính năng được hỗ trợ trong Region/workgroup.

### 13.2. Ví dụ tạo Iceberg table

Ví dụ minh họa:

~~~sql
CREATE TABLE curated_commerce.orders_iceberg (
    order_id string,
    customer_id string,
    order_ts timestamp,
    order_date date,
    region string,
    status string,
    total_amount decimal(18, 2)
)
LOCATION 's3://company-data-lake/curated/orders-iceberg/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet'
);
~~~

Schema và cú pháp Iceberg có thể khác theo engine version. Dùng cú pháp trong tài liệu Athena tương ứng với engine đang chạy, và bảo đảm catalog, S3 location, encryption và Lake Formation permissions được cấu hình.

### 13.3. Quản lý snapshot và file

Iceberg tạo metadata và snapshot khi commit dữ liệu. Nếu không quản lý maintenance, số lượng file và metadata có thể tăng. Cần có quy trình:

- Compact data files khi quá nhiều file nhỏ.
- Expire snapshot theo retention được phê duyệt.
- Dọn orphan files bằng thao tác maintenance được hỗ trợ.
- Kiểm soát concurrent writer và commit conflict.
- Kiểm tra khả năng time travel/rollback trước khi dựa vào nó trong quy trình phục hồi.

Không dùng S3 Lifecycle xóa file dữ liệu theo prefix một cách tùy tiện nếu table metadata vẫn tham chiếu đến file đó.

## 14. Truy vấn, kiểm thử và xử lý lỗi

### 14.1. Quy trình kiểm tra query

Trước khi chạy query production:

1. Xác nhận đúng workgroup và Region.
2. Kiểm tra table schema và S3 location.
3. Xác nhận quyền catalog, S3 và KMS.
4. Thêm predicate partition.
5. Chỉ chọn cột cần thiết.
6. Chạy trên khoảng dữ liệu nhỏ hoặc giới hạn an toàn.
7. Xem query execution details, bytes scanned và thời gian.
8. So sánh kết quả với số liệu nguồn hoặc báo cáo kiểm soát.

### 14.2. EXPLAIN

EXPLAIN hiển thị kế hoạch thực thi để hiểu cách engine dự kiến đọc và xử lý dữ liệu:

~~~sql
EXPLAIN
SELECT
    region,
    SUM(total_amount)
FROM curated_commerce.orders
WHERE order_date = '2026-11-20'
GROUP BY region;
~~~

Dùng kế hoạch để kiểm tra partition pruning, join và các bước scan. Kế hoạch không thay thế benchmark; hiệu năng thực tế còn phụ thuộc kích thước file, concurrency và trạng thái hệ thống.

### 14.3. Các lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| AccessDenied khi chạy query | Thiếu quyền Athena, Glue, S3, Lake Formation hoặc KMS | Kiểm tra từng lớp quyền và principal thực thi |
| Không tìm thấy table/database | Sai Region/catalog, table chưa tạo hoặc dùng sai tên | Kiểm tra Glue Data Catalog và workgroup |
| Query trả 0 rows | Partition chưa đăng ký, location sai hoặc predicate không khớp | Kiểm tra object path, partition metadata và filter |
| HIVE_BAD_DATA | File có record/kiểu dữ liệu không phù hợp schema | Kiểm tra file lỗi, SerDe và chuẩn hóa dữ liệu |
| Schema/partition mismatch | Các partition có schema khác nhau | Chuẩn hóa schema hoặc tách dataset theo version |
| Query rất chậm | Nhiều file nhỏ, scan lớn, join không hiệu quả | Compact, Parquet, partition và tối ưu query |
| Query vượt data scan limit | Query đọc quá nhiều dữ liệu | Thêm filter, giới hạn workgroup và giảm cột |
| Kết quả không cập nhật như mong đợi | Đang đọc partition cũ hoặc dùng result reuse | Kiểm tra partition, data arrival và cache settings |
| CTAS/UNLOAD thất bại | Output location, quyền ghi hoặc prefix không phù hợp | Kiểm tra S3 permission, KMS và trạng thái prefix |
| Không giải mã được kết quả | Thiếu quyền KMS hoặc key bị disable | Kiểm tra key policy, IAM và key state |

### 14.4. Đọc query execution details

Khi điều tra, xem:

- Query execution ID.
- Trạng thái và failure reason.
- Workgroup và engine version.
- Data scanned.
- Queue time và engine execution time.
- Output location.
- Query text và principal.

Lưu query execution ID trong ticket hoặc log điều tra để nhóm khác có thể truy vết. Không đưa query text chứa dữ liệu nhạy cảm vào log công khai.

## 15. Ví dụ thực hành: phân tích doanh thu trên S3

### 15.1. Bối cảnh

Một hệ thống thương mại điện tử ghi đơn hàng vào Aurora PostgreSQL. AWS DMS đưa full load và CDC vào raw zone trên S3. Glue job chuẩn hóa schema, loại duplicate và ghi Parquet vào curated zone theo ngày và khu vực.

Nhóm phân tích cần:

- Doanh thu theo ngày và khu vực.
- Số đơn đã thanh toán.
- Giá trị đơn hàng trung bình.
- Danh sách đơn có giá trị cao.
- Truy vấn không được lộ email hoặc số điện thoại khách hàng.

### 15.2. Đăng ký bảng

Glue Data Catalog có database curated_commerce và table orders trỏ tới prefix Parquet đã partition. Lake Formation cấp quyền SELECT cho role analyst trên table hoặc view được phép.

Workgroup finance-reporting được cấu hình:

- Output location riêng.
- Encryption bắt buộc.
- Query limit phù hợp ngân sách.
- Engine version đã được kiểm thử.
- CloudWatch metrics được bật.

### 15.3. Truy vấn tổng hợp

~~~sql
SELECT
    order_date,
    region,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue,
    AVG(total_amount) AS average_order_value
FROM curated_commerce.orders
WHERE order_date >= '2026-11-01'
  AND order_date < '2026-12-01'
  AND status = 'PAID'
GROUP BY order_date, region
ORDER BY order_date, region;
~~~

Query giới hạn tháng cần phân tích bằng partition key order_date. Nếu dữ liệu đã có duplicate do CDC hoặc replay, cần xử lý logic latest record trước khi tổng hợp.

### 15.4. Tạo dataset dẫn xuất

Nếu dashboard cần cùng phép tổng hợp mỗi ngày, data engineering có thể chạy CTAS hoặc Glue ETL để tạo bảng daily revenue. Dataset này có thể được partition theo tháng/ngày và chỉ chứa các cột cần thiết.

Khi refresh:

- Xác định batch/window cần cập nhật.
- Tránh append trùng nếu job được chạy lại.
- Kiểm tra số lượng đơn và tổng doanh thu với nguồn kiểm soát.
- Publish partition sau khi quality check thành công.
- Theo dõi bytes scanned và runtime.

### 15.5. Kiểm soát quyền

Analyst được đọc view/dataset đã loại bỏ PII. Nhóm hỗ trợ khách hàng có thể được cấp quyền khác nếu có nhu cầu nghiệp vụ và phê duyệt. Result bucket chỉ cho phép nhóm tương ứng đọc kết quả. CloudTrail và query history hỗ trợ điều tra hoạt động truy vấn.

## 16. Vận hành và quản trị Athena trong tổ chức

### 16.1. Chuẩn hóa workgroup

Tổ chức nhiều nhóm nên có workgroup theo workload hoặc mức độ nhạy cảm. Đặt naming convention, owner, output location, encryption, engine version, scan limit và retention. Tránh để tất cả người dùng chạy query trong một workgroup không có owner.

### 16.2. Quản lý schema change

Khi producer thêm, xóa hoặc đổi kiểu cột:

1. Xác định consumer của table.
2. Đánh giá tương thích ngược.
3. Cập nhật data contract và Glue Catalog.
4. Kiểm thử query/view/ETL.
5. Triển khai theo version hoặc migration window nếu thay đổi phá vỡ.
6. Theo dõi lỗi sau khi phát hành.

Không đổi schema trong catalog chỉ để làm query chạy qua nếu file vật lý chưa được chuyển đổi.

### 16.3. Giám sát và cảnh báo

Theo dõi:

- Query failed/cancelled.
- Query runtime và queue time.
- Data scanned theo workgroup.
- Số query vượt ngưỡng.
- Output bucket growth.
- Glue Catalog access failures.
- Lake Formation permission denials.
- Connector Lambda errors và spill storage nếu dùng federated query.

Có thể dùng CloudWatch alarm và EventBridge để thông báo hoặc kích hoạt workflow. Cảnh báo cần có owner, mức độ ưu tiên và hướng xử lý cụ thể.

### 16.4. Quản lý vòng đời kết quả

Query result và CTAS/UNLOAD output có thể tích lũy trong S3. Áp dụng lifecycle riêng:

- Kết quả ad hoc có retention ngắn.
- Báo cáo kiểm toán có retention theo quy định.
- Dataset curated có retention theo nhu cầu nghiệp vụ.
- Temporary CTAS output cần được dọn sau khi xác nhận không còn consumer.

Không dùng một lifecycle rule chung cho mọi prefix nếu retention khác nhau.

### 16.5. Kiểm soát thay đổi và audit

Quản lý thay đổi workgroup, catalog, bucket policy, KMS key, Lake Formation grants và connector. Dùng IaC hoặc quy trình review cho cấu hình production. CloudTrail ghi nhận API activity; query history hỗ trợ xác định câu lệnh và execution. Giới hạn quyền sửa cấu hình để tránh analyst vô tình thay đổi policy chung.

## 17. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Nghĩ tạo external table là copy dữ liệu vào Athena | Nhầm lẫn metadata với object nguồn | Hiểu rõ Glue Catalog và S3 là hai lớp riêng |
| Chạy SELECT * trên lake lớn | Quét nhiều cột và tăng chi phí | Chỉ chọn cột cần thiết |
| Không lọc partition | Quét nhiều ngày/tháng không cần thiết | Dùng predicate trên partition key |
| Partition theo ID có cardinality cao | Metadata phình to và query planning chậm | Chọn partition theo query pattern |
| Dùng quá nhiều file nhỏ | Tăng overhead đọc và metadata | Buffer và compact file |
| Dùng crawler không kiểm soát | Schema drift và table trùng | Data contract và schema review |
| Không cấu hình result bucket | Kết quả có thể ghi vào vị trí không phù hợp | Enforce workgroup output location |
| Chỉ cấp quyền Athena | Query vẫn lỗi ở Glue/S3/KMS/Lake Formation | Kiểm tra quyền toàn luồng |
| Mở quyền result bucket quá rộng | Lộ dữ liệu đã trích xuất | Tách bucket, encryption và quyền đọc |
| Dùng CTAS lặp lại cùng prefix | Lỗi output hoặc dữ liệu không nhất quán | Quản lý location và batch refresh |
| Retry query ghi dữ liệu mà không idempotent | Dữ liệu dẫn xuất bị trùng | Batch ID, kiểm soát partition và table format |
| Dùng Athena cho mọi workload BI | Có thể không đáp ứng latency/concurrency | Đánh giá Redshift hoặc capacity phù hợp |

## 18. Checklist triển khai Athena

### Trước khi truy vấn

1. Xác định Region, account, workgroup và data owner.
2. Kiểm tra bucket/prefix và định dạng dữ liệu.
3. Tạo Glue database/table hoặc catalog phù hợp.
4. Xác minh schema, partition và location.
5. Cấu hình query result bucket, encryption và lifecycle.
6. Cấp quyền Athena, Glue, S3, KMS và Lake Formation.

### Khi viết SQL

1. Chỉ chọn cột cần thiết.
2. Lọc partition ngay trong query.
3. Kiểm tra kiểu dữ liệu, timezone và null.
4. Lọc trước khi join.
5. Dùng EXPLAIN và query execution details khi cần.
6. Chạy thử trên phạm vi dữ liệu nhỏ trước khi chạy toàn bộ.

### Khi vận hành

1. Tách workgroup theo workload và nhóm quyền.
2. Đặt data scan limit và cảnh báo.
3. Theo dõi query runtime, bytes scanned và lỗi.
4. Compact small files và tối ưu Parquet/ORC.
5. Review schema change và catalog metadata.
6. Bảo vệ query result và quản lý retention.
7. Rà soát chi phí Athena, S3, Glue, KMS và connector.
8. Kiểm thử quyền được phép và quyền phải bị từ chối.

## 19. Kết luận

Amazon Athena cho phép truy vấn dữ liệu trên S3 bằng SQL mà không cần quản lý query cluster trong mô hình serverless phổ biến. Athena dùng metadata từ Glue Data Catalog hoặc catalog/connector được hỗ trợ để hiểu schema, partition và vị trí dữ liệu; query engine đọc object, thực thi SQL và ghi kết quả vào S3 output location.

Để truy vấn hiệu quả, cần chọn định dạng file phù hợp, ưu tiên Parquet/ORC cho analytics, partition theo mẫu lọc thực tế, compact small files và tránh đọc cột hoặc partition không cần thiết. External table đăng ký metadata; CTAS tạo dataset dẫn xuất; INSERT INTO và UNLOAD hỗ trợ các luồng ghi/xuất theo tính năng và giới hạn engine. Workgroup giúp tách workload, chuẩn hóa output, mã hóa và giới hạn scan.

Bảo mật Athena là bài toán nhiều lớp: IAM cho API, Glue Catalog cho metadata, S3 cho object, Lake Formation cho quyền dữ liệu và KMS cho mã hóa. Query result cũng cần được bảo vệ như dữ liệu nguồn. Khi kết hợp governance, monitoring, schema management và FinOps, Athena trở thành một thành phần hữu ích của data lake, hỗ trợ analyst khám phá dữ liệu và tạo insight mà vẫn kiểm soát hiệu năng, quyền truy cập và chi phí.
