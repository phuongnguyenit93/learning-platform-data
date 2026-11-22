# Kiến trúc data lake trên S3

Doanh nghiệp thường lưu dữ liệu ở nhiều hệ thống: cơ sở dữ liệu giao dịch, ứng dụng SaaS, log, file từ đối tác, hệ thống IoT và luồng sự kiện. Nếu mỗi nhóm tự tạo bản sao và pipeline riêng, dữ liệu dễ bị phân mảnh, khó kiểm soát quyền truy cập và tốn công duy trì. Data lake cung cấp một nền tảng lưu trữ tập trung để tiếp nhận dữ liệu ở nhiều định dạng, giữ lại dữ liệu gốc và tạo các lớp dữ liệu đã chuẩn hóa cho phân tích.

Amazon S3 là nền tảng lưu trữ phổ biến cho data lake trên AWS nhờ khả năng mở rộng, độ bền dữ liệu cao, nhiều storage class và tích hợp với các dịch vụ xử lý, truy vấn. Tuy nhiên, một bucket S3 chứa nhiều file chưa tự động trở thành data lake. Một kiến trúc có thể vận hành lâu dài còn cần phân vùng dữ liệu, định dạng file phù hợp, catalog, quyền truy cập ở mức dữ liệu, quản lý chất lượng, lineage, vòng đời lưu trữ và quy trình ingest/transform rõ ràng.

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, data lake trên S3 kết nối nhiều nhóm dịch vụ: AWS Glue để tích hợp và xử lý dữ liệu, AWS Lake Formation để quản trị quyền dữ liệu, Amazon Athena để truy vấn trực tiếp trên S3, Amazon Redshift để phân tích kho dữ liệu, Amazon EMR cho xử lý phân tán và các dịch vụ streaming để tiếp nhận dữ liệu liên tục. Thiết kế cần cân bằng khả năng mở rộng, bảo mật, độ tin cậy, hiệu năng và chi phí.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Amazon S3 trong kiến trúc data lake.
- Phân biệt data lake, data warehouse và data lakehouse.
- Thiết kế các vùng dữ liệu raw, standardized và curated.
- Chọn cấu trúc bucket, prefix, partition và định dạng file phù hợp.
- Mô tả luồng ingest batch, CDC và streaming vào S3.
- Sử dụng AWS Glue Data Catalog để quản lý metadata và schema.
- Giải thích cách AWS Lake Formation kết hợp IAM và S3 policy để quản trị quyền dữ liệu.
- Chọn Athena, Redshift Spectrum, Glue hoặc EMR cho các tác vụ phân tích và xử lý.
- Thiết kế mã hóa, phân loại dữ liệu, chất lượng, lineage, lifecycle và disaster recovery.
- Ước tính chi phí và xây dựng quy trình vận hành data lake.

## 2. Data lake và vai trò của Amazon S3

### 2.1. Data lake là gì?

Data lake là kiến trúc lưu trữ và quản lý dữ liệu tập trung, có thể tiếp nhận dữ liệu có cấu trúc, bán cấu trúc và phi cấu trúc từ nhiều nguồn. Dữ liệu gốc thường được giữ lại để có thể xử lý lại khi quy tắc nghiệp vụ, schema hoặc nhu cầu phân tích thay đổi.

Một data lake thường có các đặc điểm:

- Lưu được nhiều loại dữ liệu như CSV, JSON, Parquet, Avro, ảnh, video, log và dữ liệu nhị phân.
- Tiếp nhận dữ liệu từ hệ thống giao dịch, ứng dụng, thiết bị, SaaS và đối tác.
- Phân tách dữ liệu gốc với dữ liệu đã chuẩn hóa và dữ liệu phục vụ phân tích.
- Quản lý metadata, schema, quyền truy cập, chất lượng và nguồn gốc dữ liệu.
- Cho phép nhiều engine xử lý hoặc truy vấn cùng một tập dữ liệu theo quyền được cấp.
- Có chính sách lưu giữ, mã hóa, kiểm toán và phục hồi.

Data lake không phải nơi đổ mọi file không có quy tắc. Nếu không có owner, catalog, phân loại, retention và kiểm soát truy cập, lake dễ trở thành data swamp: dữ liệu tồn tại nhưng khó tìm, khó tin cậy và khó sử dụng.

### 2.2. Data lake, data warehouse và lakehouse

| Kiến trúc | Trọng tâm | Dữ liệu thường gặp | Cách sử dụng |
|---|---|---|---|
| Data lake | Lưu trữ linh hoạt dữ liệu gốc và đã xử lý | Structured, semi-structured, unstructured | Data engineering, exploration, ML, analytics |
| Data warehouse | Dữ liệu đã mô hình hóa cho phân tích có kiểm soát | Structured, schema rõ | BI, dashboard, SQL analytics |
| Data lakehouse | Kết hợp lưu trữ mở trên object storage với khả năng quản lý bảng và giao dịch | Dữ liệu dạng bảng, thường dùng table format | Analytics, data science và workload cần cập nhật dữ liệu |

Ba mô hình có thể cùng tồn tại. S3 data lake có thể cung cấp dữ liệu cho Redshift hoặc các công cụ BI; warehouse có thể giữ các mô hình dữ liệu được tối ưu cho truy vấn; table format như Apache Iceberg bổ sung metadata và cơ chế quản lý bảng trên S3 để hỗ trợ update, delete, schema evolution và snapshot theo khả năng của engine.

### 2.3. Vì sao dùng Amazon S3?

Amazon S3 phù hợp làm lớp lưu trữ data lake vì:

- Có khả năng mở rộng dung lượng mà không phải quản lý filesystem hoặc storage server.
- Tách biệt storage và compute; nhiều engine có thể đọc cùng dữ liệu mà không cần một cluster luôn chạy.
- Có nhiều storage class để tối ưu theo tần suất truy cập và thời hạn lưu trữ.
- Hỗ trợ versioning, lifecycle, replication, Object Lock và các cơ chế bảo vệ dữ liệu.
- Tích hợp với Glue, Lake Formation, Athena, EMR, Redshift, Kinesis/Data Firehose và nhiều dịch vụ khác.
- Cung cấp strong read-after-write consistency cho các thao tác object được hỗ trợ, giúp ứng dụng quan sát thay đổi sau khi ghi thành công.

S3 lưu object trong bucket, mỗi object có key và metadata. S3 không phải POSIX file system; các thao tác rename hoặc update một phần file thường được triển khai bằng cách tạo object mới hoặc copy/delete. Vì vậy, data lake cần thiết kế file và table format phù hợp với cách truy cập object storage.

## 3. Kiến trúc tổng thể của data lake trên S3

### 3.1. Các lớp chính

Một kiến trúc tham khảo có thể chia thành các lớp:

1. **Data sources:** database giao dịch, ứng dụng, file, SaaS, thiết bị IoT, log và hệ thống đối tác.
2. **Ingestion:** tiếp nhận batch, change data capture (CDC), event và streaming.
3. **Storage zones:** lưu dữ liệu gốc, dữ liệu đã chuẩn hóa và dữ liệu đã tuyển chọn.
4. **Catalog and governance:** quản lý database, table, schema, owner, classification và quyền.
5. **Processing:** làm sạch, chuẩn hóa, join, aggregate, deduplicate và kiểm tra chất lượng.
6. **Consumption:** truy vấn SQL, BI, data science, ML và chia sẻ dữ liệu.
7. **Operations:** orchestration, monitoring, audit, cost management, retention và recovery.

~~~mermaid
flowchart TB
    subgraph SRC["Nguồn dữ liệu"]
        A[Ứng dụng và database]
        B[File và đối tác]
        C[Streaming và IoT]
        D[SaaS và log]
    end
    subgraph ING["Ingestion"]
        E[DMS / DataSync / Transfer Family]
        F[Kinesis / Data Firehose]
        G[Glue connectors / API]
    end
    subgraph LAKE["Amazon S3 data lake"]
        H[Raw zone]
        I[Standardized zone]
        J[Curated zone]
    end
    subgraph GOV["Catalog và governance"]
        K[Glue Data Catalog]
        L[Lake Formation]
    end
    subgraph PROC["Processing và consumption"]
        M[Glue ETL / EMR]
        N[Athena]
        O[Redshift Spectrum / Redshift]
        P[BI và ML]
    end
    A --> E
    B --> E
    C --> F
    D --> G
    E --> H
    F --> H
    G --> H
    H --> M
    M --> I
    I --> M
    M --> J
    H --> K
    I --> K
    J --> K
    K --> L
    L --> N
    L --> O
    J --> P
    N --> P
    O --> P
~~~

Sơ đồ thể hiện các thành phần logic. Một triển khai thực tế có thể dùng nhiều account, bucket, Region và pipeline khác nhau; không nhất thiết mọi nguồn đều đi qua cùng một ingestion service.

### 3.2. Phân vùng dữ liệu theo zone

Một cách tổ chức phổ biến:

| Zone | Mục đích | Quy tắc khuyến nghị |
|---|---|---|
| Raw / landing | Lưu dữ liệu nhận từ nguồn, giữ khả năng kiểm tra và xử lý lại | Hạn chế chỉnh sửa, ghi metadata nguồn và thời điểm ingest |
| Standardized / cleansed | Chuẩn hóa schema, kiểu dữ liệu, timezone, encoding và chất lượng | Áp dụng data contract, loại bản ghi lỗi và ghi nhận kết quả kiểm tra |
| Curated / consumption | Dữ liệu đã mô hình hóa theo nhu cầu phân tích | Tối ưu partition, file format, table format và quyền truy cập |
| Sandbox / transient | Thử nghiệm hoặc dữ liệu tạm | Có owner, quota và lifecycle ngắn |

Tên gọi bronze, silver, gold cũng thường được dùng tương ứng với raw, standardized và curated. Đây là quy ước kiến trúc, không phải tên zone bắt buộc của AWS.

Raw zone nên giữ bản gốc hoặc bản sao gần với nguồn, có timestamp, source system, batch ID và schema version. Nếu cần sửa dữ liệu, tạo phiên bản xử lý mới ở zone tiếp theo thay vì âm thầm ghi đè dữ liệu gốc.

Standardized zone là nơi áp dụng quy tắc kỹ thuật chung: chuẩn hóa encoding, timezone, tên cột, kiểu số, định dạng ngày giờ, đơn vị đo và xử lý bản ghi trùng. Curated zone chứa dataset có ý nghĩa nghiệp vụ rõ, ví dụ doanh thu theo ngày, trạng thái đơn hàng hoặc hành vi người dùng.

### 3.3. Chọn bucket hay prefix?

Có thể dùng một bucket cho nhiều zone với prefix riêng, hoặc nhiều bucket tách theo zone, domain, account hay mức phân loại dữ liệu.

| Lựa chọn | Ưu điểm | Khi nên dùng |
|---|---|---|
| Một bucket, nhiều prefix | Ít tài nguyên quản lý, dễ bắt đầu | Nhóm nhỏ, cùng yêu cầu bảo mật và lifecycle |
| Bucket riêng theo zone | Policy, lifecycle, logging và access boundary rõ hơn | Zone có quyền hoặc retention khác nhau |
| Bucket riêng theo domain/account | Phân tách owner và blast radius tốt | Tổ chức nhiều nhóm, nhiều account, dữ liệu nhạy cảm |

Không có một cấu trúc bucket duy nhất phù hợp mọi tổ chức. Hãy chọn ranh giới dựa trên quyền truy cập, owner, yêu cầu lưu giữ, replication và vận hành. Prefix không phải ranh giới bảo mật tuyệt đối; cần dùng IAM policy, bucket policy, access point và Lake Formation theo mô hình đã thiết kế.

Ví dụ cấu trúc object key:

~~~text
s3://company-data-lake/
  raw/
    sales/
      source=erp/
        ingest_date=2026-11-20/
          batch_id=001/
  standardized/
    sales/
      orders/
        order_date=2026-11-20/
          region=ap-southeast-1/
  curated/
    commerce/
      daily_revenue/
        business_date=2026-11-20/
~~~

Các tên prefix chỉ là ví dụ. Cần thống nhất quy tắc đặt tên, ký tự, phân vùng, ngày giờ và owner để tránh mỗi pipeline tự tạo một cấu trúc khác nhau.

## 4. Ingest dữ liệu vào S3

### 4.1. Batch ingestion

Batch ingestion đưa một tập dữ liệu vào lake theo lịch hoặc theo đợt. Nguồn có thể là file CSV/JSON từ đối tác, export từ database, log theo ngày hoặc object từ hệ thống nội bộ.

Các lựa chọn thường gặp:

- AWS DataSync để chuyển file/object giữa hệ thống lưu trữ on-premises, NFS/SMB và S3 theo các kịch bản được hỗ trợ.
- AWS Transfer Family để nhận file qua SFTP, FTPS hoặc FTP được hỗ trợ và lưu vào S3/EFS.
- AWS Glue connectors hoặc job để đọc từ database, SaaS và nguồn dữ liệu tương thích.
- Ứng dụng tự ghi object vào S3 qua SDK/API với IAM role.
- AWS Storage Gateway trong các kịch bản tích hợp lưu trữ hybrid phù hợp.

Với batch, hãy xác định file arrival convention, manifest, checksum, encoding, schema version, thời gian hoàn tất và cách phát hiện file thiếu. Không nên xem việc file xuất hiện trong S3 là bằng chứng dữ liệu đã được ingest đầy đủ.

### 4.2. Change Data Capture từ database

CDC ghi nhận các thay đổi insert, update và delete từ database để chuyển chúng sang data lake hoặc hệ thống đích. AWS Database Migration Service (AWS DMS) có thể thực hiện full load ban đầu kết hợp ongoing replication/CDC cho các nguồn và đích được hỗ trợ.

Luồng điển hình:

1. DMS kết nối database nguồn và đọc dữ liệu ban đầu.
2. Full load được ghi vào S3 theo cấu hình.
3. DMS tiếp tục đọc transaction log/change stream của database nguồn.
4. Các thay đổi được ghi thành file/object ở S3 theo batch và cấu trúc output đã chọn.
5. Glue crawler, Glue job hoặc pipeline metadata cập nhật catalog và xử lý dữ liệu.

CDC cần xử lý thứ tự sự kiện, khóa chính, delete marker, schema change và checkpoint. Khi file CDC được chia theo thời gian hoặc partition, consumer phải áp dụng change theo đúng semantics của nguồn. Không được giả định chỉ nối tất cả file là có trạng thái hiện tại chính xác.

### 4.3. Streaming ingestion

Với dữ liệu sự kiện liên tục, có thể dùng:

- Amazon Kinesis Data Streams để tiếp nhận stream và cho phép nhiều consumer đọc theo shard/capacity model.
- Amazon Data Firehose để buffer và phân phối dữ liệu tới S3 cùng các đích được hỗ trợ.
- Amazon MSK hoặc connector phù hợp khi hệ thống đã dùng Apache Kafka.
- AWS IoT Core cho ingest message từ thiết bị IoT.
- Amazon EventBridge cho định tuyến event theo rule; target có thể là dịch vụ xử lý hoặc queue trước khi lưu vào lake.

Data Firehose có thể buffer theo kích thước hoặc thời gian trước khi ghi xuống S3. Buffer quá nhỏ tạo nhiều file nhỏ; buffer quá lớn làm tăng độ trễ dữ liệu. Chọn cấu hình theo yêu cầu freshness và hiệu quả truy vấn.

### 4.4. Event notification và xử lý sau ingest

S3 Event Notifications có thể gửi sự kiện object creation/deletion tới SNS, SQS hoặc Lambda theo cấu hình hỗ trợ. Event có thể kích hoạt pipeline sau khi file đến, ví dụ kiểm tra manifest, validate schema hoặc chạy Glue job.

Hãy thiết kế consumer idempotent vì notification có thể được giao lại và thứ tự sự kiện không phải lúc nào cũng phù hợp với giả định của ứng dụng. Nếu cần xử lý một batch gồm nhiều file, manifest hoặc marker hoàn tất thường đáng tin cậy hơn việc kích hoạt pipeline cho từng object mà không có điều phối.

### 4.5. Chọn ingestion service

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Chuyển file từ NAS/on-premises sang S3 | DataSync |
| Nhận file SFTP từ đối tác | Transfer Family |
| Full load và CDC từ database | AWS DMS |
| Stream sự kiện với consumer tùy chỉnh | Kinesis Data Streams |
| Buffer và delivery stream vào S3 | Amazon Data Firehose |
| ETL từ database/SaaS/file | AWS Glue |
| Định tuyến event giữa dịch vụ | EventBridge |
| Ghi object từ ứng dụng | S3 API/SDK với IAM role |

Có thể kết hợp nhiều lựa chọn. Ví dụ, DMS đưa CDC vào raw zone, Glue chuẩn hóa và compaction, sau đó Athena truy vấn curated zone.

## 5. Định dạng file, compression và partition

### 5.1. Row-based và columnar format

CSV và JSON dễ trao đổi, đọc trực tiếp và debug, nhưng thường không tối ưu cho truy vấn phân tích lớn. Parquet và ORC lưu dữ liệu theo cột, hỗ trợ đọc chọn cột, compression và predicate pushdown nên thường phù hợp với analytics.

| Định dạng | Đặc điểm | Trường hợp sử dụng |
|---|---|---|
| CSV | Dễ trao đổi, đơn giản, schema thường nằm ngoài file | Landing, dữ liệu nhỏ, trao đổi với đối tác |
| JSON | Linh hoạt, phù hợp event và dữ liệu lồng nhau | Raw event, log, API payload |
| Avro | Có schema và hỗ trợ serialization theo record | Event/data exchange, schema evolution theo quy trình |
| Parquet | Columnar, nén tốt, phổ biến trong analytics | Standardized và curated dataset |
| ORC | Columnar, tối ưu cho một số engine và workload | Analytics khi engine hỗ trợ tốt |

Một chiến lược thường dùng là giữ JSON/CSV/Avro gốc ở raw zone rồi chuyển sang Parquet ở standardized/curated zone. Không phải mọi nguồn đều cần chuyển ngay; giữ raw giúp tái xử lý khi logic transform thay đổi.

### 5.2. Compression

Compression giảm dung lượng lưu và lượng dữ liệu phải đọc, nhưng tiêu tốn CPU khi nén/giải nén. Với Parquet, các codec phổ biến gồm Snappy và Zstandard; lựa chọn phụ thuộc engine, tốc độ, tỷ lệ nén và khả năng tương thích.

Hãy đo trên dữ liệu thật:

- Dung lượng sau nén.
- Thời gian ETL.
- Bytes scanned và query latency.
- Mức CPU của job.
- Khả năng đọc bởi Athena, Glue, EMR và engine tiêu thụ.

### 5.3. Partitioning

Partitioning chia dataset thành các đường dẫn logic theo một hoặc nhiều thuộc tính, thường là ngày, tháng, khu vực hoặc loại dữ liệu. Query có predicate phù hợp có thể chỉ đọc các partition cần thiết, giảm bytes scanned và chi phí Athena.

Ví dụ:

~~~text
curated/orders/
  order_year=2026/
    order_month=11/
      order_day=20/
        region=ap-southeast-1/
          part-00001.parquet
~~~

Partition nên dựa trên điều kiện lọc phổ biến và cardinality hợp lý:

- Ngày hoặc tháng thường hữu ích cho dữ liệu theo thời gian.
- Region hoặc business unit có thể hữu ích nếu query thường lọc theo thuộc tính đó.
- Không nên partition theo user ID, request ID hoặc giá trị có hàng triệu khả năng nếu không có lý do rõ.
- Quá nhiều partition làm tăng metadata và overhead planning.
- Partition quá rộng có thể khiến query phải quét nhiều dữ liệu.

Không phải dataset nào cũng cần partition. Dataset nhỏ hoặc được truy vấn toàn bộ có thể dùng cấu trúc đơn giản hơn.

### 5.4. Small files problem

Quá nhiều file nhỏ làm tăng số object, metadata, request và overhead lập kế hoạch query. Ví dụ streaming pipeline ghi hàng chục nghìn file vài KB mỗi giờ có thể làm Athena/Glue tốn thời gian liệt kê và mở file thay vì xử lý dữ liệu.

Các cách giảm:

- Tăng buffer size/time trong Data Firehose nếu latency cho phép.
- Dùng Glue hoặc EMR để compact nhiều file thành file lớn hơn.
- Chọn số partition phù hợp với quy mô dữ liệu.
- Tránh ghi một file cho mỗi event.
- Theo dõi số object và kích thước trung bình.

Với analytics trên S3, file cỡ hàng trăm MB thường là điểm khởi đầu hợp lý, nhưng kích thước tối ưu phụ thuộc engine, concurrency, schema và cách partition. Hãy benchmark thay vì áp dụng một con số cứng cho mọi dataset.

## 6. Catalog và quản lý schema

### 6.1. AWS Glue Data Catalog

AWS Glue Data Catalog là metadata catalog tập trung chứa thông tin database, table, location, column, data type, partition và các thuộc tính liên quan. Các dịch vụ như Athena, Glue và Redshift Spectrum có thể dùng catalog để tìm và hiểu dữ liệu trên S3 theo tích hợp được hỗ trợ.

Data Catalog lưu metadata, không phải bản thân dữ liệu. Xóa table metadata không nhất thiết xóa object trong S3; ngược lại, xóa object không tự động đảm bảo catalog được cập nhật đúng.

Một cấu trúc database catalog có thể phản ánh zone hoặc domain:

- raw_sales
- standardized_sales
- curated_commerce
- curated_finance

Tên database/table cần có owner và quy tắc rõ ràng. Tránh để crawler tạo nhiều table gần giống nhau do file path hoặc schema không đồng nhất.

### 6.2. Glue crawler và schema-on-read

Glue crawler có thể quét S3 hoặc nguồn được hỗ trợ, suy luận schema và cập nhật Data Catalog. Crawler hữu ích khi dữ liệu mới hoặc schema có thể được phát hiện tự động, nhưng không nên coi suy luận tự động là data contract.

Rủi ro:

- Kiểu dữ liệu bị suy luận khác giữa các batch.
- Cột thiếu hoặc thêm làm schema thay đổi không dự kiến.
- Crawler tạo table/partition dư thừa.
- Dữ liệu lồng nhau hoặc file không đồng nhất gây schema khó dùng.

Với dataset quan trọng, nên quản lý schema có kiểm soát qua pipeline hoặc IaC, dùng crawler cho discovery hoặc cập nhật partition khi phù hợp. Schema evolution cần có quy tắc tương thích và quy trình thông báo consumer.

### 6.3. Schema registry và event schema

Với streaming/event, AWS Glue Schema Registry có thể quản lý schema cho format được hỗ trợ và áp dụng compatibility mode. Producer và consumer có thể kiểm tra schema version, giảm nguy cơ một thay đổi payload làm hỏng pipeline.

Schema registry không thay thế data catalog của dataset trên S3. Một hệ thống có thể dùng registry cho event schema và Glue Data Catalog cho bảng dữ liệu được lưu.

### 6.4. Partition metadata

Với Hive-style partition, Glue Data Catalog có thể lưu danh sách partition. Partition projection trong Athena cho phép Athena tính toán partition theo quy tắc thay vì phải lưu metadata cho từng partition trong catalog, nếu dataset phù hợp.

Partition projection hữu ích khi số partition lớn và có pattern đều. Tuy nhiên, cấu hình projection sai có thể làm Athena quét các location không tồn tại hoặc ước tính phạm vi quá rộng. Hãy đặt range, format và projection values chính xác.

## 7. Quản trị quyền dữ liệu với AWS Lake Formation

### 7.1. Vì sao IAM và bucket policy chưa đủ?

IAM và S3 bucket policy kiểm soát ai được gọi API và truy cập tài nguyên S3. Nhưng trong data lake, nhu cầu thường chi tiết hơn: analyst được đọc một table nhưng không được xem cột PII; nhóm tài chính chỉ được truy cập dữ liệu finance; một consumer chỉ được xem một số hàng theo tenant.

AWS Lake Formation bổ sung lớp quản trị data lake, quản lý quyền trên catalog database/table, data location và một số khả năng lọc dữ liệu ở mức row, column hoặc cell theo tính năng hỗ trợ.

Lake Formation không loại bỏ IAM. Người dùng hoặc role vẫn cần quyền gọi dịch vụ cần thiết, còn Lake Formation đánh giá quyền dữ liệu theo mô hình tích hợp. Cấu hình sai IAM, S3 policy, KMS key policy hoặc Lake Formation grant đều có thể khiến truy cập thất bại hoặc rộng hơn dự kiến.

### 7.2. Các thành phần governance

- **Data lake administrator:** quản lý cấu hình Lake Formation và quyền quản trị cấp cao.
- **Data location:** vị trí S3 được đăng ký với Lake Formation để quản lý quyền truy cập dữ liệu theo mô hình được hỗ trợ.
- **Database và table:** metadata trong Glue Data Catalog.
- **LF-tag:** nhãn phân loại để cấp quyền theo thuộc tính như domain, classification hoặc environment.
- **Data permission:** quyền đọc, ghi, tạo table hoặc thao tác metadata theo scope được cấp.
- **Resource link và cross-account sharing:** cơ chế chia sẻ database/table với account khác theo quy trình hỗ trợ.

Hãy tách quyền quản trị lake khỏi quyền sử dụng dữ liệu. Không nên cấp quyền administrator cho mọi analyst chỉ để họ truy vấn Athena.

### 7.3. Quy trình cấp quyền

Một quy trình cơ bản:

1. Đăng ký S3 data location với Lake Formation nếu dùng mô hình quản lý location.
2. Xác định database/table trong Glue Data Catalog.
3. Cấp quyền cho role hoặc principal theo database/table hoặc LF-tag.
4. Cấp IAM permission cần thiết để gọi Athena/Glue và truy cập dịch vụ.
5. Cấu hình quyền KMS nếu object được mã hóa bằng SSE-KMS.
6. Kiểm tra truy cập bằng role thực tế của consumer.
7. Kiểm tra cả truy cập được phép và truy cập phải bị từ chối.

Khi Lake Formation quản lý quyền dữ liệu, cần hiểu hybrid access mode và các lựa chọn tích hợp với IAM. Một số workload có thể tiếp tục dùng IAM/S3 permission trong khi workload khác dùng Lake Formation permission. Không trộn hai mô hình mà không có ma trận quyền và kiểm thử rõ ràng.

### 7.4. Row-level và column-level security

Ví dụ:

- Nhóm phân tích marketing được đọc bảng khách hàng nhưng không được xem email và số điện thoại.
- Nhóm vùng Singapore chỉ xem các hàng có region tương ứng.
- Nhóm tài chính được đọc cột doanh thu và chi phí, nhưng không được truy cập định danh cá nhân.

Lake Formation data filters có thể hỗ trợ lọc cột và hàng cho các engine tích hợp. Hãy kiểm tra engine, loại table và giới hạn tính năng cụ thể. Nếu engine không thực thi filter theo cách mong muốn, cần tạo view hoặc dataset đã giảm dữ liệu và kiểm soát S3 location tương ứng.

### 7.5. Chia sẻ dữ liệu giữa AWS accounts

Trong tổ chức nhiều account, data lake có thể nằm trong một account trung tâm, còn producer và consumer nằm ở các account khác. Lake Formation hỗ trợ chia sẻ metadata và quyền dữ liệu qua cơ chế cross-account được tích hợp với AWS RAM.

Luồng khái quát:

1. Lake owner cấp quyền database/table cho account consumer hoặc principal được chỉ định.
2. Chia sẻ resource được gửi qua AWS RAM theo cơ chế dịch vụ.
3. Consumer chấp nhận hoặc nhận share theo cấu hình Organizations/RAM.
4. Consumer tạo resource link trong Glue Data Catalog.
5. Role trong consumer account được cấp quyền phù hợp và truy vấn dữ liệu qua engine hỗ trợ.

Chia sẻ metadata không đồng nghĩa object được copy sang account consumer. Dữ liệu có thể vẫn nằm ở S3 của lake owner và quyền truy cập được kiểm soát theo cấu hình.

## 8. Xử lý dữ liệu với AWS Glue và Amazon EMR

### 8.1. AWS Glue ETL

AWS Glue cung cấp dịch vụ tích hợp dữ liệu serverless, gồm job ETL, crawler, Data Catalog và các khả năng quản lý pipeline. Glue job có thể đọc từ S3 hoặc nguồn được hỗ trợ, biến đổi schema, làm sạch dữ liệu, join, aggregate và ghi kết quả sang zone khác.

Các tác vụ thường gặp:

- Chuẩn hóa timestamp về UTC.
- Chuyển kiểu dữ liệu và tên cột.
- Làm sạch null, giá trị không hợp lệ và encoding.
- Loại bỏ bản ghi trùng theo khóa và thời gian.
- Mask hoặc tokenize PII theo chính sách.
- Chuyển JSON/CSV sang Parquet.
- Tạo partition và compact file.
- Tính dữ liệu tổng hợp phục vụ dashboard.

Glue job có thể dùng Spark hoặc các tùy chọn runtime được hỗ trợ. Chọn worker type, worker count, job bookmark, retry và timeout theo workload. Job bookmark có thể giúp theo dõi dữ liệu đã xử lý cho một số nguồn và cấu hình, nhưng không thay thế checkpoint và idempotency cho mọi pipeline.

### 8.2. AWS Glue Data Quality

Glue Data Quality giúp định nghĩa và chạy rule kiểm tra dữ liệu. Ví dụ:

- Cột order_id không được null.
- Tổng tiền phải lớn hơn hoặc bằng 0.
- Trường event_time phải parse được.
- Tỷ lệ customer_id không hợp lệ dưới ngưỡng.
- Số lượng bản ghi không giảm bất thường so với baseline.

Kết quả kiểm tra nên được lưu và gắn với batch/pipeline để có thể truy vết. Với rule thất bại, quyết định dữ liệu sẽ bị quarantine, retry, cảnh báo hay chấp nhận có điều kiện cần được xác định trước.

### 8.3. Amazon EMR

Amazon EMR phù hợp với xử lý phân tán quy mô lớn hoặc workload cần framework như Apache Spark, Hadoop, Hive, Trino và các thành phần được hỗ trợ. EMR có thể chạy trên EC2, EKS hoặc EMR Serverless theo lựa chọn dịch vụ.

EMR hữu ích khi:

- Cần tùy chỉnh runtime/library sâu.
- Có workload Spark/Hadoop hiện hữu.
- Cần xử lý batch lớn hoặc thuật toán phân tán chuyên biệt.
- Muốn kiểm soát cluster/capacity và cách chạy job.

EMR có thể tăng chi phí nếu cluster tồn tại lâu nhưng ít sử dụng. Dùng ephemeral cluster, managed scaling hoặc serverless option phù hợp có thể giảm tài nguyên nhàn rỗi.

### 8.4. Chọn Glue hay EMR?

| Tiêu chí | AWS Glue | Amazon EMR |
|---|---|---|
| Mô hình | Dịch vụ tích hợp dữ liệu serverless | Nền tảng xử lý big data với nhiều lựa chọn triển khai |
| Quản lý hạ tầng | Ít quản lý cluster | Tùy EMR on EC2, EKS hoặc Serverless |
| Tùy chỉnh framework | Theo runtime và khả năng Glue hỗ trợ | Linh hoạt hơn với framework và cấu hình được hỗ trợ |
| Phù hợp | ETL, catalog, crawler, data quality | Spark/Hadoop/Trino workload và xử lý chuyên biệt |
| Chi phí | Theo tài nguyên/job và tính năng sử dụng | Theo compute, storage và thành phần quản lý tương ứng |

Không có lựa chọn luôn rẻ hơn. Benchmark cùng dữ liệu, cùng SLA và cùng đầu ra để so sánh tổng chi phí.

## 9. Truy vấn và tiêu thụ dữ liệu

### 9.1. Amazon Athena

Athena là dịch vụ truy vấn SQL serverless có thể đọc dữ liệu trên S3 thông qua Data Catalog và các connector/format được hỗ trợ. Người dùng không cần duy trì cluster database cho truy vấn ad hoc.

Với mô hình tính phí theo dữ liệu quét ở các workgroup phổ biến, các cách giảm chi phí gồm:

- Chuyển CSV/JSON sang Parquet hoặc ORC.
- Chỉ chọn các cột cần thiết.
- Partition theo điều kiện lọc thường dùng.
- Dùng predicate để giới hạn partition.
- Tránh SELECT * trên dataset lớn.
- Tạo curated dataset nhỏ hơn cho dashboard lặp lại.
- Dùng workgroup để áp dụng query limits và kiểm soát output location.

Athena cũng có các tùy chọn capacity/reservation và tính năng tính phí khác tùy loại engine/workgroup. Kiểm tra bảng giá hiện hành và mô hình thực tế của tổ chức.

Ví dụ truy vấn dữ liệu đơn hàng đã partition:

~~~sql
SELECT
    region,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM curated_commerce.orders
WHERE order_date >= DATE '2026-11-01'
  AND order_date < DATE '2026-12-01'
GROUP BY region
ORDER BY revenue DESC;
~~~

Truy vấn giả định table có cột order_date, region và total_amount với kiểu dữ liệu phù hợp. Hiệu quả partition pruning phụ thuộc cách partition được khai báo và predicate khớp với partition key.

### 9.2. Amazon Redshift Spectrum

Redshift Spectrum cho phép Redshift truy vấn dữ liệu external trên S3 thông qua external schema và catalog. Nó hữu ích khi muốn kết hợp dữ liệu warehouse với dataset trên lake mà không phải nạp toàn bộ dữ liệu vào Redshift.

Spectrum không làm mọi query trên S3 tự động nhanh như dữ liệu nội bộ. Hiệu năng phụ thuộc file format, partition, lượng dữ liệu quét, predicate, concurrency và thiết kế query. Dữ liệu được truy vấn thường xuyên hoặc cần latency ổn định có thể phù hợp hơn khi được mô hình hóa/nạp vào Redshift.

### 9.3. BI và data science

Curated data có thể được dùng bởi Amazon QuickSight, Redshift, notebook, SageMaker và công cụ BI/ML khác theo tích hợp và quyền truy cập. Hãy công bố dataset có owner, mô tả nghiệp vụ, freshness, chất lượng, classification và ví dụ truy vấn.

Một data product tốt nên trả lời:

- Dữ liệu mô tả điều gì?
- Nguồn và thời điểm cập nhật là gì?
- Ai sở hữu và hỗ trợ?
- Các cột có ý nghĩa và đơn vị gì?
- Có PII hoặc dữ liệu nhạy cảm không?
- SLA freshness và quality là bao nhiêu?
- Consumer được phép dùng vào mục đích nào?

## 10. Table format và data lakehouse

### 10.1. Vấn đề của file-based table

Với Parquet thuần, mỗi file là một object và metadata table thường nằm trong Glue Data Catalog. Append file đơn giản, nhưng update/delete nhiều bản ghi, đồng bộ concurrent writer, schema evolution và snapshot management đòi hỏi logic ETL riêng.

Nếu nhiều pipeline cùng ghi một dataset, việc quản lý file và metadata thủ công dễ dẫn tới duplicate, partial write hoặc query đọc trạng thái không nhất quán.

### 10.2. Apache Iceberg

Apache Iceberg là table format mở cho analytic dataset. Iceberg quản lý metadata table, manifest và snapshot để hỗ trợ các thao tác như:

- Atomic commit theo cơ chế table format.
- Schema evolution.
- Partition evolution.
- Snapshot isolation và time travel theo engine hỗ trợ.
- Update/delete/merge theo khả năng engine.
- Compaction và quản lý file data.

Trên AWS, Glue Data Catalog có thể làm catalog cho Iceberg table; Athena, EMR và các engine khác hỗ trợ Iceberg theo phiên bản và tính năng tương ứng. Cần kiểm tra compatibility matrix trước khi chọn engine hoặc tính năng cụ thể.

### 10.3. Khi nào dùng Iceberg?

Iceberg hữu ích khi:

- Dataset cần update hoặc delete thay vì chỉ append.
- Có nhiều consumer cần đọc snapshot nhất quán.
- Cần schema evolution có kiểm soát.
- Muốn quản lý partition mà không buộc consumer phụ thuộc cấu trúc folder vật lý.
- Cần time travel hoặc rollback snapshot theo khả năng engine.

Với dataset append-only đơn giản, Parquet external table có thể đủ và ít overhead hơn. Table format tạo thêm metadata và maintenance như compaction, snapshot expiration; phải có quy trình vận hành.

### 10.4. Quản lý maintenance

Với Iceberg, cần theo dõi:

- Số lượng data file và kích thước trung bình.
- Manifest growth và metadata file.
- Snapshot retention.
- Orphan files.
- Compaction và rewrite data files.
- Concurrent writer và conflict handling.

Không xóa object bằng lifecycle tùy tiện nếu object đó còn được Iceberg metadata tham chiếu. Dùng thao tác maintenance phù hợp với engine/table format để tránh làm hỏng table.

## 11. Bảo mật data lake

### 11.1. IAM và S3 security baseline

Áp dụng các biện pháp cơ bản:

- Bật S3 Block Public Access ở account và bucket trừ trường hợp công khai có chủ đích được phê duyệt.
- Dùng bucket policy giới hạn principal, VPC endpoint hoặc điều kiện TLS khi phù hợp.
- Bật Object Ownership theo mô hình bucket owner enforced để đơn giản hóa quyền sở hữu object.
- Dùng IAM role tạm thời cho workload và consumer.
- Bật versioning cho bucket cần khả năng phục hồi object.
- Kiểm soát quyền delete, lifecycle, replication và thay đổi bucket policy.
- Dùng S3 Access Points hoặc access point theo VPC cho các mô hình chia sẻ phức tạp nếu phù hợp.

Prefix không tự ngăn người dùng truy cập object. Cần xác minh IAM policy, bucket policy, Lake Formation, KMS và quyền của dịch vụ truy vấn.

### 11.2. Mã hóa

S3 hỗ trợ mã hóa phía server như SSE-S3 và SSE-KMS. Với dữ liệu nhạy cảm hoặc yêu cầu quản lý key riêng, customer managed KMS key có thể cung cấp kiểm soát key policy, audit và rotation theo chính sách.

Khi dùng SSE-KMS:

- Principal đọc object cần quyền giải mã theo policy và key policy.
- Producer cần quyền mã hóa hoặc tạo data key theo luồng ghi.
- Cross-account consumer cần cấu hình quyền KMS phù hợp.
- KMS key phải ở Region phù hợp với bucket và thao tác.
- Theo dõi request và chi phí KMS khi có số lượng object/request lớn.

Bật S3 Bucket Keys có thể giảm số request tới KMS cho một số kịch bản SSE-KMS và giảm chi phí KMS, nhưng cần kiểm tra điều kiện và tác động đến audit/permission của hệ thống.

### 11.3. Phân loại và bảo vệ dữ liệu nhạy cảm

Data lake có thể chứa PII, financial data, health data hoặc thông tin bí mật. Trước khi ingest, xác định:

- Data owner và mục đích sử dụng.
- Classification và retention.
- Có cần masking, tokenization hoặc encryption bổ sung không.
- Ai được đọc, ghi, chia sẻ hoặc export.
- Dữ liệu có được phép chuyển Region/account không.
- Cách xử lý yêu cầu xóa hoặc hạn chế sử dụng dữ liệu.

Amazon Macie có thể giúp khám phá và phân loại một số dữ liệu nhạy cảm trong S3. Đây là công cụ hỗ trợ, không thay thế data owner, quy trình classification và kiểm soát truy cập.

### 11.4. Network và private access

Với workload cần truy cập S3 từ VPC, có thể dùng S3 Gateway Endpoint để route traffic tới S3 mà không đi qua Internet Gateway hoặc NAT Gateway. Bucket policy có thể giới hạn truy cập qua VPC endpoint nếu mô hình mạng cho phép.

Với Glue, Athena và các dịch vụ managed, cần kiểm tra cách service truy cập S3 và các endpoint cần thiết. Không giả định mọi service-to-service traffic đều đi qua endpoint trong VPC của người dùng.

### 11.5. Audit

CloudTrail có thể ghi nhận các API management event và data event được cấu hình. S3 data events có thể tạo lượng log lớn và chi phí tương ứng; hãy chọn bucket/prefix hoặc loại event cần audit theo rủi ro.

Kết hợp CloudTrail, S3 server access logging hoặc CloudTrail Lake theo nhu cầu để điều tra ai đã truy cập hoặc thay đổi dữ liệu. Bảo vệ log ở account/bucket riêng với quyền xóa hạn chế.

## 12. Chất lượng, lineage và data contract

### 12.1. Data contract

Data contract là thỏa thuận giữa producer và consumer về schema, semantics, chất lượng, freshness và thay đổi. Một contract nên mô tả:

- Tên dataset và owner.
- Schema, kiểu dữ liệu, đơn vị đo và timezone.
- Khóa chính hoặc quy tắc định danh.
- Quy tắc null, duplicate và late-arriving data.
- Tần suất cập nhật và SLA freshness.
- Schema compatibility và versioning.
- Classification, retention và quyền sử dụng.

Khi producer đổi schema, cần đánh giá consumer trước khi phát hành. Thêm cột nullable thường dễ tương thích hơn đổi kiểu hoặc xóa cột, nhưng phải kiểm tra engine và consumer thực tế.

### 12.2. Data quality

Một pipeline nên kiểm tra:

- Completeness: đủ bản ghi hoặc đủ trường bắt buộc.
- Validity: giá trị nằm trong miền hợp lệ.
- Uniqueness: khóa không bị trùng theo quy tắc.
- Consistency: quan hệ giữa các cột và dataset không mâu thuẫn.
- Timeliness: dữ liệu đến đúng SLA.
- Accuracy: đối soát với nguồn hoặc số liệu kiểm soát.

Ví dụ, số lượng đơn hàng trong curated zone có thể được so sánh với số đơn từ hệ thống giao dịch trong cùng khoảng thời gian. Nếu sai lệch vượt ngưỡng, pipeline nên phát cảnh báo và giữ batch trong trạng thái cần xem xét.

### 12.3. Lineage và metadata

Lineage cho biết dữ liệu đến từ đâu, qua job nào, được biến đổi ra sao và dataset nào phụ thuộc vào nó. Có thể ghi lineage bằng metadata của pipeline, job run, catalog, log và công cụ governance được tổ chức sử dụng.

Khi có lỗi, lineage giúp xác định:

- Dataset downstream nào bị ảnh hưởng.
- Batch nào được tạo bởi pipeline version nào.
- Source file hoặc source table nào là nguyên nhân.
- Consumer nào cần được thông báo.
- Có thể chạy lại pipeline từ raw zone hay không.

Không chỉ lưu tên job. Hãy lưu execution ID, input/output location, schema version, code version, thời điểm, trạng thái quality và correlation ID.

## 13. Orchestration và vận hành pipeline

### 13.1. Điều phối job

Một pipeline data lake có thể gồm nhiều bước:

1. Chờ file hoặc CDC batch hoàn tất.
2. Validate manifest và checksum.
3. Cập nhật metadata hoặc catalog.
4. Chạy Glue ETL.
5. Kiểm tra data quality.
6. Ghi curated dataset.
7. Cập nhật partition/table metadata.
8. Phát thông báo hoàn tất cho consumer.

Có thể điều phối bằng EventBridge, AWS Step Functions, Glue Workflows hoặc Amazon Managed Workflows for Apache Airflow (MWAA) tùy độ phức tạp và cách tổ chức.

Step Functions phù hợp với workflow có trạng thái, retry và nhánh. Glue Workflows tích hợp với các thành phần Glue. MWAA phù hợp khi tổ chức đã dùng Apache Airflow và cần DAG phức tạp. Tránh xây orchestration quá nặng cho một pipeline chỉ cần vài bước.

### 13.2. Idempotency và retry

Pipeline cần chạy lại an toàn. Nếu một Glue job lỗi sau khi ghi một phần output, lần chạy tiếp theo không nên tạo dữ liệu trùng hoặc để consumer đọc trạng thái dở dang.

Các cách:

- Dùng batch ID hoặc execution ID để xác định lần chạy.
- Ghi output vào prefix tạm rồi publish khi hoàn tất.
- Dùng atomic table commit với table format phù hợp.
- Ghi manifest xác nhận tập file thuộc một batch.
- Thiết kế upsert/dedup theo khóa và event timestamp.
- Giới hạn retry và đưa batch lỗi vào quarantine.

Retry chỉ giúp xử lý lỗi tạm thời. Lỗi schema, permission hoặc dữ liệu không hợp lệ cần được phân loại và xử lý, không retry vô hạn.

### 13.3. Monitoring

Theo dõi tối thiểu:

- Ingestion latency và số file/bản ghi đến.
- Dung lượng và số object theo zone.
- Glue job duration, failure, DPU/worker usage và retry.
- DMS task latency, CDC backlog và error.
- Kinesis shard/stream metrics hoặc Firehose delivery failures.
- Athena bytes scanned, query runtime và failed query.
- Data quality pass rate và số batch bị quarantine.
- Lake Formation permission failures và thay đổi quyền.
- S3 storage class, lifecycle, replication status và request.

Amazon CloudWatch cung cấp metric, log, alarm và dashboard cho nhiều dịch vụ. Dùng EventBridge để kích hoạt thông báo hoặc workflow phản ứng khi job thất bại. Báo cáo vận hành nên hiển thị freshness và quality của dataset, không chỉ trạng thái hạ tầng.

### 13.4. Data product owner

Mỗi dataset quan trọng cần có owner chịu trách nhiệm về định nghĩa, chất lượng, quyền truy cập và SLA. Nhóm platform có thể vận hành nền tảng, nhưng không thể tự xác nhận ý nghĩa nghiệp vụ của mọi cột dữ liệu.

Catalog nên công bố mô tả, owner, domain, classification, freshness, schema và hướng dẫn sử dụng. Dataset không còn owner hoặc không còn consumer nên được rà soát để archive hoặc xóa theo chính sách.

## 14. Lifecycle, độ bền và disaster recovery

### 14.1. S3 Lifecycle

S3 Lifecycle có thể chuyển object sang storage class khác hoặc hết hạn object theo rule. Xây dựng lifecycle theo zone:

- Raw data có thể cần lưu lâu để phục vụ audit và reprocessing.
- Standardized data có thể giữ theo chu kỳ nghiệp vụ và khả năng tái tạo từ raw.
- Curated data thường cần retention theo nhu cầu báo cáo và consumer.
- Temporary output có thể có lifecycle ngắn.

Nếu bucket bật versioning, lifecycle cần xem cả current version, noncurrent version và delete marker. Xóa current version không đồng nghĩa object cũ đã được loại bỏ hoàn toàn.

### 14.2. Replication

S3 Replication có thể sao chép object sang bucket khác trong cùng Region (SRR) hoặc Region khác (CRR) theo cấu hình và điều kiện hỗ trợ. Replication hữu ích cho DR, data locality, account isolation hoặc chia sẻ dữ liệu.

Cần xem xét:

- Versioning ở source và destination.
- IAM role và bucket policy.
- KMS key policy nếu dùng SSE-KMS.
- Replication rule, prefix/tag filter và delete marker behavior.
- Replication metrics, replication time control nếu cần SLA.
- Chi phí storage, request và data transfer.

Replication không thay thế backup trong mọi tình huống. Nếu dữ liệu bị ghi đè hoặc xóa, hành vi replicate phụ thuộc cấu hình; cần versioning, Object Lock hoặc backup strategy để bảo vệ trước lỗi và thao tác độc hại.

### 14.3. Versioning và Object Lock

S3 Versioning giữ nhiều phiên bản object để hỗ trợ phục hồi khi ghi đè hoặc xóa. Versioning có thể làm tăng storage vì phiên bản cũ vẫn được lưu; cần lifecycle cho noncurrent versions.

S3 Object Lock cung cấp mô hình WORM cho object version, với chế độ Governance hoặc Compliance và retention/legal hold theo điều kiện dịch vụ. Dùng Object Lock khi có yêu cầu bất biến hoặc lưu giữ bằng chứng. Cần thử nghiệm retention và quyền bypass trước khi bật cho dữ liệu quan trọng.

### 14.4. Kiểm thử phục hồi

Một kế hoạch DR data lake nên kiểm thử:

- Khôi phục object hoặc version đã xóa/ghi đè.
- Đọc dữ liệu từ replica bucket hoặc Region dự phòng.
- Khôi phục catalog metadata và quyền governance.
- Tạo lại pipeline và credential/role cần thiết.
- Truy vấn dataset sau khi phục hồi.
- Đo thời gian phục hồi và độ mới của dữ liệu so với RPO/RTO.

Object replication thành công chưa đủ. Nếu Glue Data Catalog, Lake Formation permission hoặc KMS key không thể phục hồi, consumer vẫn có thể không truy cập được dữ liệu.

## 15. Chi phí và tối ưu data lake

### 15.1. Các nguồn chi phí chính

| Thành phần | Yếu tố chi phí |
|---|---|
| Amazon S3 | GB-month theo storage class, request, retrieval, replication và data transfer |
| AWS Glue | Job runtime, worker/DPU, crawler, Data Catalog và tính năng liên quan |
| Amazon Athena | Dữ liệu quét hoặc mô hình capacity được chọn, query và tính năng liên quan |
| Amazon EMR | Compute node/serverless capacity, storage, cluster và network |
| AWS DMS | Replication instance/serverless capacity, storage và data transfer |
| Kinesis/Data Firehose | Stream capacity, data ingestion/delivery và destination processing |
| Lake Formation | Governance tích hợp; các dịch vụ nền như S3, Glue, query vẫn có chi phí |
| CloudWatch | Log ingestion/storage, metric, alarm và query |
| KMS | API request và key theo mô hình dịch vụ |

Chi phí data lake không chỉ nằm ở S3. Một bucket rẻ nhưng pipeline liên tục chạy lại, query quét toàn bộ dataset và log lưu vô hạn có thể làm tổng chi phí cao.

### 15.2. Tối ưu S3

- Chọn storage class theo access pattern.
- Dùng lifecycle cho dữ liệu ít truy cập hoặc hết hạn.
- Dọn multipart upload chưa hoàn tất.
- Quản lý noncurrent versions và delete markers.
- Dùng compression và columnar format.
- Compact small files.
- Tránh duplicate dataset không có owner.
- Theo dõi S3 Storage Lens và inventory.

### 15.3. Tối ưu query

- Partition theo điều kiện lọc phổ biến.
- Dùng Parquet/ORC và chỉ đọc cột cần thiết.
- Dùng Athena workgroup để giới hạn bytes scanned.
- Tạo aggregate/curated table cho query lặp lại.
- Cân nhắc Redshift khi cần workload warehouse ổn định và lặp nhiều.
- Theo dõi query plan, bytes scanned và concurrency.

### 15.4. Tối ưu ETL

- Incremental processing thay vì đọc lại toàn bộ dataset.
- Dùng bookmark/checkpoint khi phù hợp.
- Chọn worker type và số worker theo benchmark.
- Gộp pipeline nhỏ khi có thể giảm overhead mà vẫn giữ ranh giới vận hành.
- Dừng cluster EMR khi không còn job.
- Thiết lập retry và timeout hợp lý.
- Tránh chạy crawler liên tục trên prefix không thay đổi.

### 15.5. FinOps cho data lake

Gắn tag hoặc cost allocation metadata cho domain, environment, owner và application. Theo dõi chi phí theo:

- Storage zone và bucket.
- Domain hoặc data product.
- Pipeline/job.
- Query workgroup.
- Account và Region.
- Producer/consumer nếu có cơ chế phân bổ.

Đo unit economics như chi phí trên mỗi TB ingest, mỗi triệu event, mỗi query hoặc mỗi data product được phục vụ. Cần cân bằng chi phí với freshness, query latency, retention và yêu cầu compliance.

## 16. Ví dụ thiết kế: data lake cho dữ liệu thương mại điện tử

### 16.1. Nguồn và yêu cầu

Một nền tảng thương mại điện tử cần phân tích đơn hàng, thanh toán, tồn kho, hành vi người dùng và log ứng dụng. Dữ liệu đến từ:

- Aurora PostgreSQL lưu đơn hàng và thanh toán.
- Ứng dụng phát event hành vi.
- Đối tác vận chuyển gửi file trạng thái giao hàng.
- S3 lưu ảnh sản phẩm.
- Hệ thống log tạo dữ liệu vận hành.

Yêu cầu:

- Giữ dữ liệu gốc để đối soát.
- Cập nhật dữ liệu đơn hàng gần thời gian thực.
- Tạo dataset doanh thu theo ngày và khu vực.
- Giới hạn quyền truy cập PII.
- Cho phép analyst truy vấn bằng SQL.
- Có khả năng phục hồi và kiểm soát chi phí.

### 16.2. Thiết kế ingest

1. DMS thực hiện full load và CDC từ Aurora vào raw zone.
2. Ứng dụng gửi event hành vi vào Kinesis Data Streams; Data Firehose buffer và ghi vào S3 raw.
3. Đối tác tải file qua Transfer Family vào landing prefix.
4. DataSync chuyển dữ liệu file từ hệ thống lưu trữ nội bộ khi cần.
5. S3 notification hoặc EventBridge kích hoạt workflow sau khi batch hoàn tất.

### 16.3. Chuẩn hóa và curated

Glue job đọc raw data:

- Chuẩn hóa timestamp về UTC và giữ timezone nguồn trong metadata khi cần.
- Chuẩn hóa currency và kiểu số.
- Deduplicate event theo event ID.
- Mask email/phone ở dataset dành cho analyst.
- Ghi Parquet theo partition ngày và region.
- Chạy quality rules về khóa, tổng tiền và số lượng bản ghi.

Curated zone có các table:

- orders_current: trạng thái đơn hàng đã xử lý CDC.
- payment_transactions: giao dịch thanh toán và đối soát.
- daily_revenue: doanh thu theo ngày, khu vực và kênh.
- customer_activity: hành vi đã loại bỏ hoặc mask định danh nhạy cảm.

Nếu cần upsert CDC và cập nhật trạng thái bảng, nhóm có thể đánh giá Iceberg table với engine hỗ trợ. Với dataset chỉ append, Parquet external table có thể đơn giản hơn.

### 16.4. Governance và query

- Glue Data Catalog lưu schema và partition.
- Lake Formation cấp quyền theo domain và LF-tag.
- Analyst truy vấn curated table qua Athena workgroup.
- Nhóm BI có thể dùng Redshift Spectrum hoặc nạp dataset cần truy vấn thường xuyên vào Redshift.
- PII chỉ được truy cập bởi role được phê duyệt; dữ liệu phân tích phổ thông dùng bản đã mask.

### 16.5. Vận hành

- CloudWatch theo dõi DMS CDC latency, Glue job, Data Firehose delivery và Athena query.
- Step Functions điều phối ingest, transform, quality và publish.
- CloudTrail ghi nhận hoạt động quản trị và truy cập được chọn.
- S3 Lifecycle chuyển raw data cũ sang storage class phù hợp theo retention.
- Versioning/replication và backup metadata được kiểm thử định kỳ.
- Cost Explorer phân bổ chi phí theo domain và môi trường.

## 17. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Xem S3 bucket là data lake hoàn chỉnh | Không có catalog, owner, quality hoặc governance | Thiết kế zone, metadata và quy trình quản trị |
| Ghi mọi dữ liệu vào một prefix | Khó phân quyền, retention và truy vấn | Tách zone/domain theo nhu cầu quản trị |
| Dùng CSV cho mọi analytics | Tốn dung lượng và bytes scanned | Chuyển dataset phân tích sang Parquet/ORC khi phù hợp |
| Partition quá chi tiết | Nhiều partition và overhead metadata | Chọn partition theo query pattern và cardinality |
| Tạo hàng triệu file nhỏ | Query chậm và tốn request/metadata | Buffer, compact và điều chỉnh số partition |
| Crawler tự suy luận schema không kiểm soát | Schema drift và table trùng | Dùng data contract và quản lý schema có version |
| Chỉ dùng IAM mà không có data governance | Quyền table/column khó quản lý | Kết hợp Lake Formation theo mô hình quyền rõ ràng |
| Consumer đọc trực tiếp raw data | Sai lệch định nghĩa, lộ PII và khó thay đổi nguồn | Công bố curated data product |
| Retry pipeline mà không idempotent | Dữ liệu trùng hoặc output dở dang | Batch ID, manifest, outbox/checkpoint và publish có kiểm soát |
| Replication được coi là backup đầy đủ | Xóa/ghi đè có thể lan sang replica theo cấu hình | Kết hợp versioning, Object Lock hoặc backup và test restore |
| Lifecycle xóa file Iceberg đang tham chiếu | Table metadata trỏ tới object không còn | Dùng maintenance của table format và retention phù hợp |
| Chỉ theo dõi trạng thái job | Dataset có thể đến muộn hoặc sai chất lượng | Theo dõi freshness, completeness và quality |

## 18. Checklist thiết kế data lake trên S3

### Trước khi triển khai

1. Xác định domain, data owner, consumer và use case.
2. Lập inventory nguồn dữ liệu, volume, format, velocity và sensitivity.
3. Xác định account, Region, bucket và zone.
4. Chọn batch, CDC hoặc streaming ingestion.
5. Định nghĩa data contract, schema và partition.
6. Chọn Glue Data Catalog, Lake Formation và mô hình IAM.
7. Thiết kế mã hóa, network, audit và retention.
8. Ước tính S3, ETL, query, streaming, network và monitoring cost.

### Khi triển khai

1. Tạo bucket/prefix và bật Block Public Access.
2. Cấu hình encryption, bucket policy, role và KMS.
3. Thiết lập ingest và raw landing.
4. Tạo catalog database/table và schema version.
5. Xây Glue/EMR transform và data quality checks.
6. Cấp quyền Lake Formation và kiểm tra quyền thực tế.
7. Tạo Athena workgroup hoặc engine tiêu thụ.
8. Thiết lập orchestration, monitoring và alert.

### Khi vận hành

1. Theo dõi freshness, completeness, quality và lineage.
2. Rà soát quyền truy cập và dữ liệu nhạy cảm.
3. Compact file và tối ưu partition.
4. Kiểm tra lifecycle, versioning và replication.
5. Đánh giá query scan, ETL runtime và storage growth.
6. Thử nghiệm restore object, catalog và pipeline.
7. Review owner, consumer, retention và chi phí theo định kỳ.

## 19. Kết luận

Amazon S3 cung cấp lớp lưu trữ mở rộng cho data lake, nhưng một kiến trúc có giá trị cần nhiều thành phần phối hợp: zone dữ liệu, ingestion, file format, partition, catalog, governance, processing, query, quality, security và operations. AWS Glue hỗ trợ catalog và ETL; Lake Formation quản trị quyền dữ liệu; Athena và Redshift Spectrum hỗ trợ truy vấn; EMR phục vụ xử lý phân tán; DMS, DataSync, Transfer Family, Kinesis và Data Firehose đưa dữ liệu vào lake theo nhiều kiểu workload.

Thiết kế tốt giữ dữ liệu gốc có thể kiểm tra, tạo standardized và curated dataset có owner, đồng thời công bố schema, chất lượng và quyền sử dụng rõ ràng. Parquet, partition và compaction giúp truy vấn hiệu quả; Lake Formation, IAM, S3 policy và KMS bảo vệ dữ liệu; lifecycle, versioning, replication và restore testing hỗ trợ lưu giữ và phục hồi.

Data lake không kết thúc khi object đã xuất hiện trong bucket. Nó là nền tảng dữ liệu được vận hành liên tục, nơi producer, platform team và consumer cùng chịu trách nhiệm về chất lượng, quyền truy cập, freshness và chi phí. Khi các trách nhiệm đó được thiết kế ngay từ đầu, S3 data lake có thể phục vụ analytics, data science và tích hợp dữ liệu trên quy mô lớn một cách an toàn và có kiểm soát.
