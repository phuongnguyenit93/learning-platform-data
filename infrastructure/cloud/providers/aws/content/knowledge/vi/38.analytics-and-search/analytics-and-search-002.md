# Athena workgroup, partition pruning và kiểm soát chi phí

## 1. Vì sao cần quản trị Athena theo workgroup?

Amazon Athena là dịch vụ truy vấn SQL serverless cho dữ liệu trong Amazon S3 và các nguồn dữ liệu được hỗ trợ. Người dùng không phải cấp phát cluster, nhưng mỗi truy vấn vẫn đọc dữ liệu, tiêu thụ tài nguyên, tạo kết quả và có thể phát sinh chi phí ở nhiều dịch vụ liên quan.

Trong mô hình trả theo lượng dữ liệu quét, chi phí phụ thuộc chủ yếu vào số bytes Athena phải đọc. Số bytes này chịu ảnh hưởng bởi:

- Cách dữ liệu được tổ chức: partition, file format, compression, kích thước và số lượng file.
- Cách query được viết: cột được chọn, filter partition, join, aggregation và phạm vi dữ liệu.
- Khả năng dùng lại kết quả của query trước.
- Cách workload được phân chia và kiểm soát concurrency.

Athena Workgroups giúp tổ chức và quản trị workload truy vấn. Một workgroup có thể áp dụng cấu hình kết quả, mã hóa, CloudWatch metrics, data usage controls, engine version và quyền truy cập riêng.

Một chiến lược hiệu quả kết hợp ba lớp: workgroup governance, data layout và query discipline. Workgroup tạo cơ chế kiểm soát và đo lường; chi phí giảm khi truy vấn đọc ít dữ liệu hơn hoặc sử dụng capacity hiệu quả hơn.

## 2. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vai trò của Athena Workgroups và các cấu hình quản trị.
2. Phân biệt per-query scan cutoff với workgroup-wide usage alarms.
3. Thiết lập output location, encryption, expected bucket owner và enforce workgroup configuration.
4. Giải thích cách Athena tính phí theo bytes scanned và các khoản phí liên quan.
5. Thiết kế partition key theo query pattern và thực hiện partition pruning.
6. Phân biệt Glue partition metadata, partition projection và Glue partition indexes.
7. Dùng Parquet/ORC, compression, bucketing và file compaction để giảm scan.
8. Dùng CTAS để materialize dữ liệu và tối ưu truy vấn lặp lại.
9. Dùng EXPLAIN, query statistics và CloudWatch để tìm bottleneck.
10. Cấu hình query result reuse và đánh giá rủi ro dữ liệu cũ.
11. Thiết kế IAM, S3 results bucket, KMS và cost allocation tags.
12. Tạo workgroup, chạy query và kiểm tra chi phí bằng AWS CLI.

## 3. Athena Workgroup là gì?

Workgroup là đơn vị quản lý các truy vấn Athena. Mỗi query execution được chạy trong một workgroup được chỉ định. Workgroup có thể giúp:

- Tách workload theo team, ứng dụng, môi trường hoặc mức độ quan trọng.
- Quản lý nơi lưu query results trong S3.
- Ép buộc encryption và cấu hình kết quả.
- Giới hạn bytes scanned cho từng query.
- Đặt ngưỡng usage tổng hợp theo giờ/ngày và phát cảnh báo.
- Publish query metrics lên CloudWatch.
- Chọn Athena engine version.
- Gắn tags để phân bổ và theo dõi chi phí.
- Gán workgroup vào capacity reservation nếu dùng mô hình capacity-based.

Workgroup không phải database, schema, VPC hay compute cluster riêng. Workgroup cũng không tự cấp quyền đọc bảng hoặc bucket dữ liệu nguồn. Data access vẫn được kiểm soát bằng IAM, S3 bucket policy, Lake Formation và quyền của Data Catalog.

### 3.1. Mô hình workgroup tham khảo

| Workgroup | Người dùng | Mục đích | Guardrail |
|---|---|---|---|
| `analytics-dev` | Developer, data engineer | Phát triển và thử query | Scan cutoff thấp, output riêng |
| `analytics-prod` | Dashboard/service role | Truy vấn production | Enforce config, encryption, alerts |
| `analytics-ad-hoc` | Analyst | Khám phá dữ liệu | Scan cutoff theo query, usage alerts |
| `analytics-finance` | Finance team | Báo cáo chi phí/tài chính | Quyền dữ liệu hạn chế, output riêng |
| `analytics-etl` | Pipeline role | CTAS/INSERT/UNLOAD | Capacity/limits phù hợp workload |

Không nên gom tất cả người dùng vào `primary` workgroup nếu cần phân quyền, theo dõi chi phí và giới hạn truy vấn khác nhau.

## 4. Cấu hình quan trọng của Workgroup

| Thuộc tính | Vai trò |
|---|---|
| `EnforceWorkGroupConfiguration` | Ép client dùng cấu hình workgroup thay vì cấu hình do query/client gửi |
| `ResultConfiguration.OutputLocation` | S3 prefix lưu query results |
| `ExpectedBucketOwner` | Xác minh account owner của bucket chứa query results |
| `EncryptionConfiguration` | SSE-S3, SSE-KMS hoặc CSE-KMS theo cấu hình hỗ trợ |
| `PublishCloudWatchMetricsEnabled` | Publish query metrics lên CloudWatch |
| `BytesScannedCutoffPerQuery` | Giới hạn bytes scanned của từng query |
| `EngineVersion` | Chọn hoặc quản lý Athena engine version |
| `RequesterPaysEnabled` | Cho phép truy vấn Requester Pays buckets khi cần |

Workgroup cần có query results location ở cấp workgroup hoặc query/client. Nếu không có output location hợp lệ, query có thể thất bại.

### 4.1. Enforce workgroup configuration

Khi `EnforceWorkGroupConfiguration=true`, workgroup settings override các client-side settings như output location, expected bucket owner, encryption và cấu hình object results. Điều này giúp quản trị viên bảo đảm mọi query trong workgroup dùng chung policy.

Nếu không bật enforce, client có thể cung cấp cấu hình riêng trong phạm vi được phép. Điều đó thuận tiện cho thử nghiệm nhưng khó kiểm soát vị trí output và mã hóa ở môi trường production.

Ép cấu hình output không tự động giới hạn vị trí dữ liệu nguồn. Query vẫn cần quyền đọc source S3 location và Data Catalog.

### 4.2. Query results location

Dùng bucket/prefix riêng theo workgroup, ví dụ:

```text
s3://company-athena-results/
  analytics-prod/
  analytics-dev/
  analytics-finance/
```

Query results có thể chứa dữ liệu trích xuất từ bảng nguồn, nên phải xem đây là dữ liệu cần bảo vệ. Cấu hình Block Public Access, bucket policy giới hạn principal, SSE-KMS nếu yêu cầu, KMS key policy, lifecycle expiration và object ownership theo nhu cầu quản trị.

Expected bucket owner trong workgroup chỉ áp dụng cho S3 output location của query results. Nó không tự áp dụng cho source bucket, vị trí CTAS/INSERT INTO, UNLOAD output hoặc spill bucket của federated query.

### 4.3. Encryption

Workgroup có thể ép query results dùng encryption. Với SSE-KMS, principal và dịch vụ cần quyền KMS phù hợp như `kms:GenerateDataKey` và `kms:Decrypt` theo luồng sử dụng.

Không chỉ mã hóa dữ liệu nguồn. Query results cũng có thể chứa dữ liệu nhạy cảm và thường được nhiều người dùng tải về.

## 5. Tổ chức Workgroups theo trách nhiệm và chi phí

Nên thiết kế workgroup dựa trên owner chịu trách nhiệm chi phí, loại workload, mức độ nhạy cảm dữ liệu, SLO, output bucket, encryption, scan limit và tags.

Ví dụ tags:

| Tag | Giá trị ví dụ |
|---|---|
| `Environment` | `prod` |
| `Owner` | `data-platform` |
| `CostCenter` | `CC-ANALYTICS-01` |
| `DataDomain` | `orders` |
| `Application` | `athena-reporting` |

Workgroup tags có thể dùng cho IAM condition và cost allocation. Để tag xuất hiện trong báo cáo billing/CUR theo cơ chế cost allocation tags, cần kích hoạt user-defined cost allocation tags trong Billing and Cost Management.

Không tạo workgroup cho từng cá nhân nếu không có nhu cầu governance rõ ràng. Quá nhiều workgroups khiến policy, dashboard và lifecycle khó quản lý.

## 6. Athena tính phí như thế nào?

Athena SQL có thể dùng mô hình trả theo query dựa trên lượng dữ liệu quét hoặc mô hình capacity-based qua capacity reservations. Với mô hình phổ biến pay-per-query:

\[
\text{Query cost} =
\frac{\text{Billable bytes scanned}}{\text{Bytes per TB}}
\times \text{Regional price per TB}
\]

Giá mỗi TB thay đổi theo Region và thời điểm. Dùng AWS Pricing Calculator hoặc trang Amazon Athena Pricing để lấy giá hiện hành cho Region triển khai.

Theo cơ chế pay-per-query, số bytes scanned được làm tròn lên MB gần nhất và có mức tối thiểu 10 MB cho mỗi query. DDL như CREATE/ALTER/DROP và các statement quản lý partition không bị tính phí scan theo mô hình này; query thất bại không bị tính phí query scan. Query bị cancel vẫn bị tính theo lượng dữ liệu đã quét đến thời điểm cancel.

### 6.1. Ví dụ chi phí minh họa

Giả sử một Region có mức giá minh họa `P = 5 USD/TB`. Đây chỉ là số giả định để minh họa công thức, không phải báo giá cho mọi Region.

| Bytes scanned | Chi phí minh họa |
|---:|---:|
| 1 TB | 5 USD |
| 200 GB | 1 USD |
| 50 GB | 0,25 USD |
| 10 GB | 0,05 USD |

Nếu một dashboard chạy 100 lần/ngày và mỗi query scan 200 GB, lượng scan là 20 TB/ngày. Nếu tối ưu xuống 10 GB/query, lượng scan còn 1 TB/ngày. Chi phí query giảm theo tỷ lệ dữ liệu đọc, chưa tính S3, Glue, KMS và các dịch vụ khác.

### 6.2. Các khoản phí ngoài query scan

Cần tính thêm S3 storage của source data và query results, S3 requests/data transfer, AWS Glue Data Catalog, Lambda cho federated query connectors, KMS requests, capacity reservations, dịch vụ ETL/compaction và cross-Region transfer.

Một query scan rẻ không đồng nghĩa toàn pipeline không phát sinh chi phí.

## 7. Hai loại data usage controls

Athena hỗ trợ hai lớp giới hạn usage quan trọng trong workgroup.

### 7.1. Per-query data usage control

`BytesScannedCutoffPerQuery` giới hạn tổng bytes scanned cho từng query trong workgroup.

- Mỗi workgroup có một per-query cutoff.
- Khi một query vượt ngưỡng, Athena cancel query đó.
- Cutoff áp dụng cho từng query, không phải tổng của tất cả query.
- Query đã bị cancel vẫn có thể bị tính phí cho bytes đã scan.
- Query có thể đã ghi một phần kết quả vào S3 trước khi bị cancel; cần lifecycle policy để dọn multipart uploads/kết quả không hoàn chỉnh.

Đặt cutoff theo loại workload. Workgroup ad-hoc có thể có giới hạn thấp hơn workgroup ETL.

### 7.2. Workgroup-wide data usage controls

Workgroup-wide controls theo dõi tổng bytes scanned của tất cả query trong một khoảng thời gian như giờ hoặc ngày. Có thể đặt nhiều threshold và dùng CloudWatch alarm/SNS để thông báo hoặc kích hoạt hành động vận hành.

Đây là cơ chế usage alert và response, không phải một transaction budget bảo đảm ngắt mọi query ngay khi tổng scan chạm ngưỡng. Query đang chạy có thể tiếp tục cho đến khi có cơ chế xử lý bổ sung. Muốn guardrail rõ ràng, kết hợp per-query cutoff, workgroup-wide alarms, IAM hạn chế người có quyền chạy query, CloudWatch/SNS/Lambda runbook, AWS Budgets và admission control.

### 7.3. Chọn ngưỡng

| Workgroup | Per-query cutoff | Workgroup alert |
|---|---:|---|
| `analytics-dev` | 10 GB | 100 GB/ngày |
| `analytics-ad-hoc` | 50 GB | 500 GB/ngày |
| `analytics-prod` | 100 GB | 2 TB/ngày |
| `analytics-etl` | 500 GB | 10 TB/ngày |

Các con số là ví dụ. Đặt threshold dựa trên baseline thực tế, số người dùng, data growth và SLO.

## 8. Theo dõi chi phí theo Workgroup

Bật `PublishCloudWatchMetricsEnabled` để publish query metrics. Khi tạo workgroup qua console, tùy chọn metrics thường được bật mặc định; khi dùng API/CLI, cần kiểm tra cấu hình rõ ràng.

Theo dõi data scanned per query, query execution time, query planning time, query queue time, số query thành công/thất bại/cancel, workgroup usage theo giờ/ngày, top query IDs theo bytes scanned và owner.

CloudWatch metrics giúp tạo dashboard và alarms. Athena console cũng hiển thị query stats và execution details. Workgroup metrics không thay thế Cost Explorer/CUR: dùng query metrics để tìm nguyên nhân kỹ thuật, billing data để đối soát khoản phí thực tế.

## 9. Partition pruning là gì?

Partitioning chia dữ liệu thành các vùng vật lý/logical dựa trên key như ngày, tháng, region hoặc tenant. Athena dùng predicate trong `WHERE` để xác định partition cần đọc và bỏ qua partition không liên quan.

Ví dụ dữ liệu lưu ở:

```text
s3://company-lake/orders/
  dt=2026-11-18/region=ap-southeast-1/part-000.parquet
  dt=2026-11-18/region=ap-northeast-1/part-001.parquet
  dt=2026-11-19/region=ap-southeast-1/part-002.parquet
  dt=2026-11-20/region=ap-southeast-1/part-003.parquet
```

Query chỉ cần ngày 20/11 và region Singapore thì Athena có thể bỏ qua các partition còn lại nếu bảng metadata và predicate được cấu hình đúng.

Partition pruning giảm dữ liệu đọc, cải thiện latency và giảm chi phí pay-per-query.

## 10. Chọn partition keys theo query pattern

Không chọn partition chỉ vì field tồn tại trong event. Hãy phân tích dashboard thường lọc theo ngày/tháng hay khoảng thời gian, analyst lọc theo region/business unit/tenant, số giá trị distinct của key, phân bố dữ liệu, dung lượng mỗi partition và số tổ hợp partition rỗng.

Với event/log dữ liệu lớn, key thường gặp là `dt` hoặc `year/month/day` cho thời gian, `region` cho địa lý, `event_type` nếu cardinality thấp và được filter thường xuyên.

Không partition theo `request_id`, `transaction_id`, `user_id` có hàng triệu giá trị hoặc timestamp tới mili giây. Những key này tạo quá nhiều partition nhỏ, tăng metadata overhead và file count. Nếu cần lọc theo high-cardinality key, xem xét bucketing, Parquet statistics hoặc sort/cluster data.

AWS khuyến nghị dùng kiểu `STRING` cho partition keys để Athena có thể push partition filtering xuống AWS Glue hiệu quả. Nếu giá trị partition là ngày, lưu chuỗi chuẩn hóa như `YYYY-MM-DD`. Khi cần phép tính date, cast giá trị sau khi đã filter partition hoặc dùng cột timestamp riêng trong dữ liệu.

## 11. Hive-style partitions và Glue Data Catalog

Hive-style path có dạng `key=value`, ví dụ:

```text
s3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/
```

Khi tạo external table, khai báo partition columns:

```sql
CREATE EXTERNAL TABLE analytics.orders (
    order_id STRING,
    customer_id STRING,
    order_total DECIMAL(18,2),
    created_at TIMESTAMP
)
PARTITIONED BY (
    dt STRING,
    region STRING
)
STORED AS PARQUET
LOCATION 's3://company-lake/orders/';
```

Athena cần metadata partition trong Glue Data Catalog hoặc cơ chế partition projection để xác định vị trí dữ liệu.

### 11.1. Thêm partition thủ công

```sql
ALTER TABLE analytics.orders
ADD IF NOT EXISTS PARTITION (
    dt = '2026-11-20',
    region = 'ap-southeast-1'
)
LOCATION 's3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/';
```

Có thể tự động thêm partition bằng Glue crawler, Glue APIs hoặc pipeline ingest.

### 11.2. MSCK REPAIR TABLE

`MSCK REPAIR TABLE` quét S3 prefix để tìm Hive-style partitions chưa đăng ký và thêm vào catalog. Nó hữu ích cho một số luồng ban đầu nhưng không nên chạy định kỳ trên bảng lớn nếu có lựa chọn quản lý partition tốt hơn.

Lưu ý: có thể mất thời gian khi prefix chứa nhiều partition; chủ yếu nhận dạng Hive-style `key=value`; không xóa partition metadata đã cũ khỏi Glue; không thay thế thiết kế partition projection hoặc partition index.

Với bảng lớn, dùng Glue APIs/partition projection/index và quy trình lifecycle metadata rõ ràng.

## 12. Viết query để kích hoạt partition pruning

Giả sử partition keys là `dt` và `region`.

Query tốt:

```sql
SELECT
    order_id,
    order_total,
    created_at
FROM analytics.orders
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01'
  AND region = 'ap-southeast-1';
```

Predicate tham chiếu trực tiếp partition columns và giới hạn phạm vi dữ liệu.

Query kém hơn:

```sql
SELECT *
FROM analytics.orders
WHERE CAST(dt AS DATE) = DATE '2026-11-20'
  AND lower(region) = 'ap-southeast-1';
```

Dùng function/cast trên partition column có thể khiến partition pushdown khó tối ưu. Hãy chuẩn hóa partition value và so sánh trực tiếp với string literal.

Partition predicate giảm số folder/object cần đọc. Data predicate như `order_total > 1000000` tiếp tục lọc record trong file. Với Parquet/ORC, column statistics và predicate pushdown có thể giúp bỏ qua row groups hoặc stripes không phù hợp.

## 13. AWS Glue partition indexes

Khi bảng có hàng trăm nghìn hoặc hàng triệu partitions, thời gian gọi Glue `GetPartitions` có thể trở thành bottleneck trong query planning.

Glue partition index giúp Data Catalog tìm subset partitions phù hợp thay vì tải toàn bộ partition list rồi lọc.

Khi tạo index, chọn thứ tự partition keys, ví dụ `(region, dt)` hoặc `(dt, region)`. Index được thiết kế theo thứ tự key. Predicate cần có key đầu tiên của index để tận dụng tối ưu index.

Athena cần bật table property:

```sql
ALTER TABLE analytics.orders
SET TBLPROPERTIES (
    'partition_filtering.enabled' = 'true'
);
```

Giới hạn cần biết:

- Một Glue table có thể có tối đa ba partition indexes.
- Index có trạng thái CREATING, ACTIVE, FAILED hoặc DELETING.
- Index chỉ hỗ trợ một số biểu thức lọc; AND và các toán tử so sánh được hỗ trợ là trường hợp phổ biến.
- Các biểu thức OR, LIKE, IN, NOT có thể không được dùng để lọc bằng index.
- Key đầu tiên trong index cần xuất hiện trong expression.
- Index tạo thêm storage item và chi phí Glue Data Catalog.

Partition index không giảm bytes trong các file đã chọn nếu query vẫn đọc cùng các object. Nó chủ yếu giảm chi phí metadata lookup và query planning.

## 14. Partition projection

Partition projection cho phép Athena tự tính partition values và S3 locations từ table properties thay vì lấy toàn bộ partition metadata từ Glue Data Catalog.

Phù hợp khi dữ liệu partition theo pattern dự đoán được, partition mới xuất hiện đều đặn theo ngày/giờ, bảng có số lượng partitions lớn và không muốn quản lý partition registration thủ công.

### 14.1. Các kiểu projection

| Projection type | Ví dụ |
|---|---|
| `date` | Ngày/giờ trong một khoảng |
| `integer` | ID/range số nguyên liên tục |
| `enum` | Tập giá trị hữu hạn như Region |
| `injected` | Giá trị được đưa trực tiếp từ predicate theo cấu hình hỗ trợ |

### 14.2. Ví dụ cấu hình partition projection

Giả sử S3 layout:

```text
s3://company-lake/orders/dt=2026-11-20/region=ap-southeast-1/
```

Cấu hình table properties:

```sql
ALTER TABLE analytics.orders
SET TBLPROPERTIES (
  'projection.enabled' = 'true',
  'projection.dt.type' = 'date',
  'projection.dt.range' = '2025-01-01,NOW',
  'projection.dt.format' = 'yyyy-MM-dd',
  'projection.dt.interval' = '1',
  'projection.dt.interval.unit' = 'DAYS',
  'projection.region.type' = 'enum',
  'projection.region.values' = 'ap-southeast-1,ap-northeast-1',
  'storage.location.template' =
    's3://company-lake/orders/dt=${dt}/region=${region}/'
);
```

Cấu hình `projection.dt.format` phải khớp với giá trị partition và đường dẫn thực tế. Nếu partition values là `YYYY-MM-DD`, dùng format tương ứng và chỉnh template cho khớp.

### 14.3. Những giới hạn của projection

- Khi bật projection, Athena bỏ qua partition metadata đã đăng ký trong Glue cho table đó.
- Nếu projected partition không tồn tại trên S3, query thường trả về không có record thay vì báo lỗi.
- Nếu hơn một nửa projected partitions là rỗng, traditional Glue partitions thường có hiệu năng tốt hơn.
- Projection chỉ được Athena sử dụng; engine khác như EMR/Redshift Spectrum có thể vẫn cần Glue partition metadata.
- `SHOW PARTITIONS` không liệt kê các partition được projection nhưng chưa đăng ký trong Glue.
- Query nằm ngoài range cấu hình có thể trả 0 rows thay vì báo lỗi.

Không dùng projection nếu partition space quá thưa hoặc dữ liệu không theo pattern dự đoán được.

## 15. Chọn giữa Glue partitions, partition indexes và projection

| Tiêu chí | Glue partitions | Glue partition indexes | Partition projection |
|---|---|---|---|
| Partition metadata | Lưu từng partition trong catalog | Lưu partition và index | Tính từ table properties |
| Quản lý partition | Cần crawler/API/DDL | Cần quản lý partition và index | Không cần đăng ký từng partition |
| Query planning | Có thể chậm khi partition rất nhiều | Tăng tốc GetPartitions filtering | Tránh GetPartitions lookup |
| Phù hợp | Bảng nhỏ/vừa, dữ liệu không quá thưa | Bảng lớn, partition metadata nhiều | Partition pattern đều và dự đoán được |
| Sparse partitions | Metadata phản ánh partition thật | Metadata phản ánh partition thật | Có thể project nhiều partition không tồn tại |
| Engine compatibility | Rộng hơn | Engine hỗ trợ Glue index | Chủ yếu Athena |

Quy tắc chọn: bảng ít partition dùng Glue partitions bình thường; bảng có nhiều partition thật và filter pattern rõ thì đánh giá partition indexes; bảng partition liên tục theo date/integer/enum thì đánh giá projection; bảng rất sparse thì ưu tiên metadata partition thực tế và index.

## 16. Bucketing cho key cardinality cao

Partitioning phù hợp với key có số giá trị vừa phải và query thường filter theo key đó. Với key cardinality cao như `customer_id` hoặc `device_id`, tạo partition cho từng giá trị thường không hiệu quả.

Bucketing chia dữ liệu thành một số bucket dựa trên hash của một hoặc nhiều columns. Điều này có thể giúp lookup/join trên high-cardinality keys và giảm lượng data cần đọc trong các tình huống được hỗ trợ.

Chọn key có cardinality cao, phân bố tương đối đều và thường được filter; chọn số bucket dựa trên dung lượng và workload; không tạo quá nhiều bucket nhỏ; kiểm thử join/filter plan trước khi triển khai. Partition và bucket có thể kết hợp, ví dụ partition theo `dt` và bucket theo `customer_id`.

## 17. Columnar formats, compression và column pruning

Athena có thể giảm bytes scanned đáng kể khi dữ liệu được lưu ở định dạng columnar.

| Định dạng | Đặc điểm | Phù hợp |
|---|---|---|
| CSV/JSON | Row-oriented, linh hoạt, dễ debug | Raw landing, payload biến đổi |
| Parquet | Columnar, compression và statistics | Analytics, dashboard, query chọn một số cột |
| ORC | Columnar, compression và stripe statistics | Hive-oriented analytics |
| Avro | Row-oriented, schema evolution | Data exchange/streaming use cases |

Với Parquet/ORC, Athena có thể chỉ đọc các cột cần thiết thay vì toàn bộ row file. Compression cũng giảm bytes đọc từ S3.

Query chỉ chọn các cột cần thiết thường tiết kiệm hơn `SELECT *` nếu bảng có nhiều cột không cần thiết và dùng columnar format.

Quá nhiều file nhỏ làm tăng S3 listing, metadata và query planning overhead. File quá lớn hoặc không splittable có thể hạn chế parallelism. Dùng CTAS, Glue ETL hoặc compaction pipeline để gom file nhỏ thành file columnar có kích thước phù hợp với throughput và query pattern. Không chọn một kích thước cố định cho mọi workload; đo thời gian scan, số file và concurrency.

## 18. CTAS để chuyển đổi và materialize dữ liệu

`CREATE TABLE AS SELECT` (CTAS) tạo table mới từ kết quả query và ghi file vào S3. CTAS hữu ích để chuyển CSV/JSON sang Parquet/ORC, chỉ giữ các cột cần thiết, chuẩn hóa schema, tạo partition layout mới, materialize aggregation/join dùng lặp lại và tạo curated layer cho dashboard.

Ví dụ tạo bảng Parquet partition theo ngày và Region:

```sql
CREATE TABLE analytics.orders_curated
WITH (
    format = 'PARQUET',
    write_compression = 'SNAPPY',
    external_location = 's3://company-curated/orders/',
    partitioned_by = ARRAY['dt', 'region']
) AS
SELECT
    order_id,
    customer_id,
    order_total,
    created_at,
    dt,
    region
FROM analytics.orders_raw
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01';
```

Trong CTAS, các partition columns cần được đặt ở cuối danh sách SELECT tương ứng với `partitioned_by`.

CTAS cũng tiêu thụ bytes scanned ở input và ghi dữ liệu ra S3. Tính chi phí ETL, storage và maintenance trước khi materialize. CTAS có giới hạn số partition được tạo trong một statement; nếu cần tạo nhiều partition hơn giới hạn hiện hành, chia thành các batch hoặc dùng pipeline ETL phù hợp.

Không nên chạy CTAS toàn bộ lịch sử mỗi ngày nếu chỉ có partition mới. Dùng `INSERT INTO`, Glue ETL hoặc pipeline incremental để xử lý phần dữ liệu mới. Cần quản lý late-arriving records, partition overwrite/reprocessing, duplicate events, schema evolution, data quality, retention và compaction.

## 19. Query result reuse

Athena có thể tái sử dụng kết quả query trước đó để tránh thực thi lại cùng query và scan dữ liệu.

Khi bật result reuse, Athena tìm kết quả phù hợp trong cùng workgroup. Các điều kiện bao gồm query string, database/catalog, result configuration, quyền truy cập bảng và quyền đọc S3 result object.

Giới hạn quan trọng:

- Result reuse chỉ hoạt động trong cùng workgroup.
- Chỉ hỗ trợ các query tạo result set trên S3; chủ yếu SELECT/EXECUTE theo tài liệu.
- Kết quả mặc định hết hạn sau 60 phút nếu không đặt max age.
- Max age có thể cấu hình đến 7 ngày.
- Athena không kiểm tra source data đã thay đổi hay chưa trước khi tái sử dụng kết quả.
- Không phù hợp cho query cần dữ liệu mới nhất hoặc dùng non-deterministic functions như `rand()`.
- Có các hạn chế với federated catalogs, Lake Formation row/column filters và managed query results.

Chỉ bật result reuse khi nghiệp vụ chấp nhận freshness window. Dashboard tài chính, báo cáo tồn kho và monitoring near-real-time cần đánh giá độ mới của kết quả trước khi bật.

## 20. EXPLAIN và EXPLAIN ANALYZE

`EXPLAIN` hiển thị execution plan để xem cách Athena dự định đọc bảng, join, filter và phân phối dữ liệu. Nó hữu ích để kiểm tra plan mà không chạy toàn bộ query.

```sql
EXPLAIN
SELECT
    region,
    COUNT(*) AS order_count
FROM analytics.orders
WHERE dt >= '2026-11-01'
  AND dt < '2026-12-01'
GROUP BY region;
```

`EXPLAIN ANALYZE` thực thi query và cung cấp runtime statistics như CPU, rows input/output và operator behavior.

```sql
EXPLAIN ANALYZE
SELECT
    region,
    COUNT(*) AS order_count
FROM analytics.orders
WHERE dt = '2026-11-20'
GROUP BY region;
```

Vì query thực sự chạy và scan data, EXPLAIN ANALYZE có thể phát sinh phí như query bình thường. Chỉ dùng khi cần runtime evidence.

## 21. Đọc Query statistics

Sau mỗi query, kiểm tra Query stats hoặc API `GetQueryExecution`.

| Statistic | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| `DataScannedInBytes` | Bytes dữ liệu đã quét | Cao bất thường so với output |
| `EngineExecutionTimeInMillis` | Thời gian engine thực thi | Query xử lý nặng |
| `QueryPlanningTimeInMillis` | Thời gian lập plan, gồm lookup partitions | Cao có thể do nhiều partitions |
| `QueryQueueTimeInMillis` | Thời gian chờ tài nguyên trong queue | Cao có thể do concurrency/capacity |
| `TotalExecutionTimeInMillis` | Tổng thời gian query | Chỉ số trải nghiệm end-to-end |
| `ServiceProcessingTimeInMillis` | Thời gian finalize/publish kết quả | Chậm ở giai đoạn trả kết quả |
| `ResultReuseInformation` | Query có dùng kết quả cũ không | Đánh giá tiết kiệm scan và freshness |

Một query chậm không nhất thiết scan nhiều dữ liệu. Nếu query planning time cao, xem partition metadata/index/projection. Nếu queue time cao, xem concurrency, workgroup workload và capacity. Nếu engine execution cao, xem join, aggregation, skew và file layout.

## 22. CloudWatch, EventBridge và cảnh báo

Bật query metrics cho từng workgroup. Tạo dashboard theo bytes scanned, query execution time, query planning/queue time, query state/failure count, workgroup usage theo giờ/ngày, top query IDs hoặc principal có scan lớn và query result reuse rate nếu được ghi nhận.

Dùng CloudWatch alarms cho usage thresholds và SNS để thông báo. EventBridge query state change events có thể kích hoạt Lambda/automation khi query hoàn tất, thất bại hoặc bị cancel.

Không gửi toàn bộ SQL text hoặc query results vào log nếu chúng có thông tin nhạy cảm. Dùng query execution ID, workgroup, principal, database và metrics cần thiết.

## 23. IAM, Lake Formation và bảo vệ dữ liệu

Workgroup controls không thay thế data authorization.

Một principal chạy Athena thường cần Athena permissions cho workgroup/query actions, Glue Data Catalog permissions để xem database/table/partition, S3 `GetObject`/`ListBucket` trên source data, S3 `PutObject` trên query results bucket, KMS permissions nếu source/results dùng SSE-KMS và Lake Formation grants nếu table được quản lý bởi Lake Formation.

Dùng IAM policy để giới hạn principal chỉ được chạy query trong workgroup được chỉ định. Có thể dùng resource ARN của workgroup và condition keys phù hợp. Tách quyền admin workgroup khỏi quyền query execution. Analyst không nên tự thay output bucket, encryption hoặc scan cutoff của production workgroup.

Nếu cần row-level, column-level hoặc cell-level permissions, dùng Lake Formation grants và tích hợp Athena. Workgroup chỉ quản lý query execution/configuration; Lake Formation kiểm soát dữ liệu người dùng được phép đọc.

## 24. Cost governance end-to-end

Một quy trình quản trị chi phí có thể gồm:

1. Gắn owner, cost center và data domain cho từng workgroup.
2. Chỉ định output bucket/prefix và lifecycle.
3. Enforce encryption và query result configuration.
4. Đặt per-query scan cutoff.
5. Đặt workgroup-wide hourly/daily alerts.
6. Publish query metrics lên CloudWatch.
7. Lưu query execution metadata để phân tích.
8. Phân tích top scanned queries hàng tuần.
9. Tối ưu partition, Parquet/ORC, compression và CTAS.
10. Review IAM principal có query scan cao.
11. Đối chiếu với Cost Explorer/CUR và AWS Budgets.
12. Cập nhật threshold theo baseline và tăng trưởng dữ liệu.

Với mỗi query scan cao, xác định workgroup/principal, kiểm tra `DataScannedInBytes`, xem query có filter partition không, kiểm tra `SELECT *`, format/compression, số object, join cardinality/skew, khả năng reuse/materialize và so sánh trước/sau bằng query stats.

## 25. Anti-patterns thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| Mọi người dùng chung primary workgroup | Khó phân quyền và chargeback | Tách workgroup theo workload/team |
| Không enforce workgroup settings | User có thể đổi output/encryption | Bật EnforceWorkGroupConfiguration |
| Nhầm workgroup-wide alarm là hard budget cap | Query vẫn tiếp tục chạy | Dùng per-query cutoff và response automation |
| Không đặt query result lifecycle | S3 results tăng liên tục | Lifecycle expiration và access policy |
| `SELECT *` trên bảng rộng | Scan nhiều cột | Chọn cột cần thiết |
| Không lọc partition | Đọc nhiều ngày/tháng không cần thiết | Predicate trực tiếp trên partition keys |
| Partition theo request/user ID | Quá nhiều partition nhỏ | Dùng bucketing hoặc Parquet statistics |
| Partition projection trên bảng sparse | Athena tính nhiều partition không tồn tại | Dùng Glue partitions/index |
| Quá nhiều small files | Metadata/listing overhead | CTAS/compaction |
| Chạy MSCK REPAIR liên tục trên bảng lớn | Planning/metadata overhead | Glue APIs, projection hoặc partition index |
| Chạy EXPLAIN ANALYZE trên query rất lớn chỉ để xem plan | Phát sinh chi phí scan | Dùng EXPLAIN trước |
| Bật result reuse cho báo cáo real-time | Trả dữ liệu cũ | Đặt max age ngắn hoặc tắt reuse |
| Không kiểm tra query planning time | Chỉ tập trung vào engine time | Tối ưu partition metadata |

## 26. Ví dụ thiết kế: phân tích đơn hàng theo ngày và Region

Một doanh nghiệp có 20 TB dữ liệu order events trong S3, mỗi ngày phát sinh khoảng 100 GB. Analyst thường truy vấn theo ngày, Region và loại đơn hàng.

| Thành phần | Lựa chọn |
|---|---|
| Raw layer | JSON/GZIP hoặc Parquet từ ingestion |
| Curated layer | Parquet, compression phù hợp |
| Partition keys | `dt`, `region` |
| Glue Catalog | Table metadata, partition indexes khi số partition lớn |
| Athena workgroup | `analytics-orders` |
| Query results | `s3://company-athena-results/orders/` |
| Encryption | SSE-KMS |
| Per-query cutoff | Theo baseline, ví dụ 50 GB |
| Workgroup alerts | Theo giờ/ngày |
| Metrics | CloudWatch query metrics |
| Query reuse | Bật cho dashboard chấp nhận freshness window |

Query:

```sql
SELECT
    region,
    order_type,
    COUNT(*) AS order_count,
    SUM(order_total) AS revenue
FROM analytics.orders_curated
WHERE dt >= '2026-11-01'
  AND dt < '2026-11-08'
  AND region = 'ap-southeast-1'
GROUP BY region, order_type;
```

Khi dữ liệu được partition theo ngày/Region và lưu Parquet, Athena có thể bỏ qua partition không liên quan và chỉ đọc cột cần thiết.

## 27. AWS CLI: tạo và quản lý Workgroup

### 27.1. Tạo workgroup có enforce settings và cutoff

Ví dụ dưới đây đặt per-query cutoff 50 GiB, lưu query results vào S3 và mã hóa SSE-KMS. Thay bucket, account và key ARN bằng giá trị thực tế.

```bash
aws athena create-work-group \
  --name analytics-prod \
  --description "Production analytics queries" \
  --configuration '{
    "ResultConfiguration": {
      "OutputLocation": "s3://company-athena-results/analytics-prod/",
      "EncryptionConfiguration": {
        "EncryptionOption": "SSE_KMS",
        "KmsKey": "arn:aws:kms:ap-southeast-1:111122223333:key/00000000-1111-2222-3333-444444444444"
      },
      "ExpectedBucketOwner": "111122223333"
    },
    "EnforceWorkGroupConfiguration": true,
    "PublishCloudWatchMetricsEnabled": true,
    "BytesScannedCutoffPerQuery": 53687091200
  }' \
  --tags Key=Environment,Value=prod Key=Owner,Value=data-platform Key=CostCenter,Value=CC-ANALYTICS-01 \
  --region ap-southeast-1
```

### 27.2. Kiểm tra workgroup

```bash
aws athena get-work-group \
  --work-group analytics-prod \
  --region ap-southeast-1
```

Xác nhận `EnforceWorkGroupConfiguration`, output location, encryption, metrics và cutoff đúng như mong muốn.

### 27.3. Chạy query trong workgroup

```bash
aws athena start-query-execution \
  --query-string "SELECT region, COUNT(*) FROM analytics.orders_curated WHERE dt = '2026-11-20' GROUP BY region" \
  --query-execution-context Database=analytics,Catalog=AwsDataCatalog \
  --work-group analytics-prod \
  --region ap-southeast-1
```

Lưu QueryExecutionId được trả về để kiểm tra trạng thái và statistics.

### 27.4. Đọc bytes scanned và execution time

```bash
aws athena get-query-execution \
  --query-execution-id 01234567-89ab-cdef-0123-456789abcdef \
  --region ap-southeast-1 \
  --query "QueryExecution.{State:Status.State,WorkGroup:WorkGroup,Statistics:Statistics.{DataScannedBytes:DataScannedInBytes,EngineMs:EngineExecutionTimeInMillis,PlanningMs:QueryPlanningTimeInMillis,QueueMs:QueryQueueTimeInMillis,TotalMs:TotalExecutionTimeInMillis}}"
```

Dùng số liệu này để so sánh query trước và sau khi thay đổi partition, file format hoặc SQL.

## 28. Bài thực hành: Workgroup và partition pruning

### 28.1. Mục tiêu

Tạo một workgroup có guardrail, truy vấn một bảng partitioned, đo bytes scanned và giảm chi phí bằng partition pruning/columnar format.

### 28.2. Điều kiện chuẩn bị

- AWS account lab.
- S3 bucket chứa sample dataset theo Hive-style partitions.
- AWS Glue Data Catalog database/table.
- IAM role/user có quyền Athena, Glue, S3 và KMS phù hợp.
- S3 bucket riêng cho query results.
- CloudWatch metrics được bật.

### 28.3. Các bước

1. Chuẩn bị bảng orders partition theo `dt` và `region`.
2. Đăng ký partitions bằng Glue crawler/API hoặc DDL.
3. Tạo workgroup `analytics-lab`.
4. Đặt output location, SSE-KMS và `EnforceWorkGroupConfiguration=true`.
5. Bật CloudWatch metrics.
6. Đặt per-query cutoff phù hợp với dung lượng lab.
7. Chạy `SELECT *` không filter và ghi lại DataScannedInBytes.
8. Chạy query có filter trực tiếp trên `dt` và `region`.
9. Chạy query chỉ chọn 3 cột cần thiết.
10. Chuyển một bản curated sang Parquet bằng CTAS.
11. Chạy lại query trên Parquet và so sánh bytes scanned.
12. Nếu bảng có nhiều partition, tạo Glue partition index và bật `partition_filtering.enabled=true`.
13. Nếu partition theo date liên tục, thử partition projection trong bảng thử nghiệm.
14. Đặt CloudWatch usage alarm và kiểm tra notification.
15. Kiểm tra query result reuse với max age phù hợp.
16. Cấu hình lifecycle cho query results bucket.
17. Ghi lại latency, bytes scanned và chi phí ước tính.

### 28.4. Tiêu chí hoàn thành

- Workgroup có cấu hình output/encryption được enforce.
- Per-query cutoff được áp dụng.
- Workgroup-wide usage alarm phát notification khi vượt threshold.
- Query filter partition scan ít dữ liệu hơn query không filter.
- Parquet và column pruning giảm bytes scanned khi phù hợp.
- Query statistics được lưu để so sánh.
- Partition projection/index được chọn đúng với đặc điểm bảng.
- Query result reuse chỉ bật khi freshness chấp nhận được.
- S3 query results có lifecycle và access policy.

## 29. Câu hỏi tự kiểm tra

### Câu 1

Athena Workgroup dùng để làm gì?

**Đáp án:** Nhóm các query execution để quản lý cấu hình, output location, encryption, metrics, data usage controls, engine version, tags và quyền truy cập.

### Câu 2

`EnforceWorkGroupConfiguration=true` có tác dụng gì?

**Đáp án:** Ép query sử dụng cấu hình workgroup như output location, expected bucket owner và encryption thay vì client-side settings.

### Câu 3

Per-query cutoff khác workgroup-wide usage control như thế nào?

**Đáp án:** Per-query cutoff cancel một query khi bytes scanned vượt ngưỡng. Workgroup-wide controls theo dõi tổng usage theo thời gian và phát alarm/notification.

### Câu 4

Workgroup có tự giới hạn quyền đọc source S3 không?

**Đáp án:** Không. Source access vẫn cần IAM, S3 bucket policy và Lake Formation grants phù hợp.

### Câu 5

Partition pruning giảm chi phí như thế nào?

**Đáp án:** Athena bỏ qua partitions không liên quan theo predicate, từ đó giảm số object/bytes phải đọc.

### Câu 6

Vì sao partition keys thường nên dùng STRING?

**Đáp án:** Để Athena push partition filtering xuống AWS Glue hiệu quả. Giá trị ngày/số có thể chuẩn hóa dưới dạng string và cast khi cần.

### Câu 7

Partition projection khác Glue partition index thế nào?

**Đáp án:** Projection tính partition values/locations từ table properties và bỏ qua partition metadata Glue; partition index tăng tốc việc tìm subset partitions đã đăng ký trong Glue.

### Câu 8

Khi nào không nên dùng partition projection?

**Đáp án:** Khi partition space rất sparse, nhiều projected partitions không tồn tại hoặc các engine khác ngoài Athena cần đọc Glue partition metadata.

### Câu 9

Vì sao không nên partition theo requestId?

**Đáp án:** Cardinality rất cao tạo quá nhiều partition nhỏ và metadata overhead. Có thể dùng bucketing hoặc Parquet statistics.

### Câu 10

Parquet/ORC giúp giảm bytes scanned thế nào?

**Đáp án:** Columnar format cho phép Athena chỉ đọc cột cần thiết; compression và predicate pushdown giúp bỏ qua dữ liệu không liên quan.

### Câu 11

EXPLAIN ANALYZE có thể phát sinh chi phí không?

**Đáp án:** Có. EXPLAIN ANALYZE thực thi query và scan dữ liệu; EXPLAIN chỉ hiển thị execution plan.

### Câu 12

Query result reuse có thể trả dữ liệu cũ không?

**Đáp án:** Có. Athena không kiểm tra source data đã thay đổi khi reuse result; cần đặt max age phù hợp với yêu cầu freshness.

## 30. Checklist production

### Workgroup governance

- [ ] Workgroups được tách theo workload/team/environment.
- [ ] IAM policy giới hạn quyền truy cập workgroup.
- [ ] EnforceWorkGroupConfiguration được bật cho production.
- [ ] Output location, expected bucket owner và encryption được cấu hình.
- [ ] S3 results bucket có lifecycle và access policy.
- [ ] Workgroup tags có owner/cost center.
- [ ] Per-query cutoff được đặt.
- [ ] Workgroup-wide usage alarms và response runbook đã cấu hình.

### Data layout

- [ ] Partition keys dựa trên query patterns.
- [ ] Partition cardinality và data skew được đánh giá.
- [ ] Partition columns dùng STRING khi phù hợp.
- [ ] Glue partitions/index hoặc projection được chọn theo workload.
- [ ] Không có quá nhiều empty partitions.
- [ ] Dữ liệu analytical dùng Parquet/ORC và compression phù hợp.
- [ ] File compaction giảm small files.
- [ ] Bucketing chỉ dùng khi key/query pattern phù hợp.

### Query optimization

- [ ] Query chọn cột cần thiết, tránh SELECT *.
- [ ] WHERE có predicate trực tiếp trên partition keys.
- [ ] Join và aggregation được kiểm tra cardinality/skew.
- [ ] EXPLAIN được dùng trước khi tối ưu sâu.
- [ ] EXPLAIN ANALYZE chỉ chạy khi cần runtime evidence.
- [ ] Query stats được lưu và so sánh.
- [ ] CTAS/materialized datasets được cân nhắc cho workload lặp lại.
- [ ] Query result reuse có max age phù hợp freshness.

### Cost and security

- [ ] Bytes scanned và query cost được theo dõi.
- [ ] CloudWatch metrics/dashboard/alarms được bật.
- [ ] Cost Explorer/CUR và AWS Budgets được dùng để đối soát.
- [ ] KMS policy và S3 bucket policy theo least privilege.
- [ ] Lake Formation grants bảo vệ row/column nếu cần.
- [ ] Query results không được public.
- [ ] Failed/canceled query artifacts và incomplete multipart uploads có lifecycle cleanup.
- [ ] Có review định kỳ top queries theo scan và owner.

## 31. Tài liệu tham khảo chính thức

### Workgroups và cost controls

- [Use workgroups to control query access and costs](https://docs.aws.amazon.com/athena/latest/ug/workgroups-manage-queries-control-costs.html)
- [Create an Athena workgroup](https://docs.aws.amazon.com/athena/latest/ug/creating-workgroups.html)
- [Override client-side settings](https://docs.aws.amazon.com/athena/latest/ug/workgroups-settings-override.html)
- [Configure per-query and per-workgroup data usage controls](https://docs.aws.amazon.com/athena/latest/ug/workgroups-setting-control-limits-cloudwatch.html)
- [Monitor queries and control costs with CloudWatch and EventBridge](https://docs.aws.amazon.com/athena/latest/ug/workgroups-control-limits.html)
- [Enable CloudWatch query metrics](https://docs.aws.amazon.com/athena/latest/ug/athena-cloudwatch-metrics-enable.html)

### Partitioning và data optimization

- [Partition your data](https://docs.aws.amazon.com/athena/latest/ug/partitions.html)
- [Optimize data for Athena](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-data-optimization-techniques.html)
- [Use partition projection](https://docs.aws.amazon.com/athena/latest/ug/partition-projection.html)
- [Optimize Athena with AWS Glue partition indexes](https://docs.aws.amazon.com/athena/latest/ug/glue-best-practices-partition-index.html)
- [AWS Glue partition indexes](https://docs.aws.amazon.com/glue/latest/dg/partition-indexes.html)
- [Use columnar storage formats](https://docs.aws.amazon.com/athena/latest/ug/columnar-storage.html)
- [Optimize tables and bucketing](https://docs.aws.amazon.com/athena/latest/ug/performance-tuning-s3-throttling-optimizing-your-tables.html)

### Query execution và pricing

- [Create a table from query results (CTAS)](https://docs.aws.amazon.com/athena/latest/ug/ctas.html)
- [CTAS considerations and limitations](https://docs.aws.amazon.com/athena/latest/ug/ctas-considerations-limitations.html)
- [Reuse query results](https://docs.aws.amazon.com/athena/latest/ug/reusing-query-results.html)
- [View query statistics](https://docs.aws.amazon.com/athena/latest/ug/query-stats.html)
- [EXPLAIN and EXPLAIN ANALYZE](https://docs.aws.amazon.com/athena/latest/ug/athena-explain-statement.html)
- [Query execution statistics API](https://docs.aws.amazon.com/athena/latest/APIReference/API_QueryExecutionStatistics.html)
- [Amazon Athena pricing](https://aws.amazon.com/athena/pricing/)
- [Amazon Athena FAQs](https://aws.amazon.com/athena/faqs/)

