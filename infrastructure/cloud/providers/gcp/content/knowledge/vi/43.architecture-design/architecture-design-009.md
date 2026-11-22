# Kiến trúc data platform kết hợp BigQuery và Cloud Storage

Một nền tảng dữ liệu trên Google Cloud thường cần giải quyết hai nhu cầu khác nhau: **lưu trữ dữ liệu gốc có thể kiểm tra và tái xử lý**, đồng thời **cung cấp dữ liệu đã chuẩn hóa để truy vấn phân tích nhanh, có quản trị và kiểm soát chi phí**. Cloud Storage phù hợp với lớp lưu trữ object và data lake; BigQuery phù hợp với lớp phân tích SQL, data warehouse và các mô hình lakehouse có truy vấn dữ liệu bên ngoài.

Kết hợp hai dịch vụ giúp tổ chức tiếp nhận log, sự kiện, dữ liệu giao dịch, file từ đối tác hoặc kết quả xử lý batch theo một kiến trúc có khả năng mở rộng. Tuy nhiên, đặt file vào bucket rồi tạo một bảng BigQuery chưa đủ để hình thành data platform đáng tin cậy. Kiến trúc còn phải xác định luồng ingest, vùng dữ liệu, schema, chất lượng, danh tính, vị trí dữ liệu, quy trình truy vấn, khả năng phục hồi và phân bổ chi phí.

Bài học này xây dựng một kiến trúc tham chiếu cho data platform sử dụng **Cloud Storage làm landing/raw lake** và **BigQuery làm warehouse/analytics**, đồng thời phân biệt cách truy vấn external table, BigLake, load vào native table và cách vận hành dữ liệu batch hoặc gần thời gian thực.

## 1. Phân vai Cloud Storage và BigQuery

### Cloud Storage: lưu trữ object và dữ liệu gốc

Cloud Storage lưu object trong bucket với độ bền cao, phù hợp cho:

- File thô từ ứng dụng, đối tác, CDC, thiết bị hoặc hệ thống khác.
- Dữ liệu bán cấu trúc như JSON và định dạng cột như Parquet, Avro, ORC.
- Dữ liệu lớn hoặc ít được truy vấn nhưng cần giữ để audit, replay hoặc reprocessing.
- Các bản export, snapshot logic, tập dữ liệu trao đổi giữa hệ thống.
- Vùng lưu trữ dữ liệu ở nhiều giai đoạn như raw, quarantine và archive.

Cloud Storage **không tự cung cấp một data warehouse SQL đầy đủ** cho object. Người dùng cần engine như BigQuery hoặc một hệ thống xử lý khác để biến file thành dữ liệu có thể phân tích.

### BigQuery: lưu trữ dạng bảng và phân tích SQL

BigQuery cung cấp khả năng xử lý truy vấn phân tích quy mô lớn với SQL, quản lý dataset/table, quản trị truy cập và các lựa chọn tối ưu partition, clustering, materialized view và năng lực tính toán.

BigQuery phù hợp cho:

- Truy vấn ad hoc, BI và dashboard.
- Data marts có schema nhất quán.
- Aggregate và phân tích theo nhiều chiều.
- Các bảng cleaned/curated được sử dụng lặp lại.
- Chia sẻ dữ liệu theo dataset, table, row và column phù hợp chính sách.
- Chạy transformation theo mô hình ELT bằng SQL.

### Lớp nối giữa lake và warehouse

BigQuery có thể đọc dữ liệu đặt trong Cloud Storage qua **external tables**; **BigLake external tables** bổ sung mô hình quản trị truy cập qua connection và các khả năng quản lý dữ liệu bên ngoài được hỗ trợ. Ngoài ra, dữ liệu có thể được **load vào BigQuery native tables** để khai thác khả năng tối ưu và quản lý của warehouse.

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Giữ nguyên file gốc và tái xử lý | Cloud Storage | Độc lập với schema phân tích |
| Truy vấn một bộ Parquet không quá thường xuyên | BigQuery external table | Không cần nạp bản sao vào native table |
| Truy vấn lake với quản trị truy cập qua connection | BigLake external table | Quản lý truy cập dữ liệu bên ngoài tập trung hơn |
| Dashboard truy vấn lặp lại và join lớn | BigQuery native table | Khai thác partition, clustering và tối ưu execution |
| Nạp dữ liệu định kỳ | GCS → BigQuery load job | Đơn giản, phù hợp batch |
| Sự kiện liên tục độ trễ thấp | Pub/Sub/Dataflow → BigQuery | Ingest và chuyển đổi theo luồng |

Quyết định không nên dựa trên tên gọi "data lake" hay "lakehouse" mà dựa vào **mô hình truy vấn, độ trễ, chi phí lưu trữ, quyền dữ liệu và nhu cầu tái sử dụng**.

## 2. Kiến trúc tham chiếu từ nguồn đến phân tích

Một data platform có thể gồm sáu lớp:

1. **Sources:** ứng dụng, database giao dịch, log, file đối tác và event stream.
2. **Ingestion:** batch transfer, Pub/Sub, Dataflow hoặc CDC pipeline.
3. **Raw lake:** Cloud Storage giữ dữ liệu gốc và metadata tiếp nhận.
4. **Processing:** Dataflow, BigQuery SQL/Dataform hoặc pipeline batch chuẩn hóa.
5. **Curated warehouse:** BigQuery staging, cleaned datasets và data marts.
6. **Consumption & governance:** BI, notebook, ML, data catalog, IAM, quality và observability.

~~~mermaid
flowchart TD
    A[Applications and partners] --> B[Batch ingestion]
    C[Databases and CDC] --> D[Datastream or Dataflow]
    E[Application events] --> F[Pub/Sub]
    F --> G[Dataflow streaming]
    B --> H[Cloud Storage raw lake]
    D --> H
    G --> H
    G --> I[BigQuery staging]
    H --> J[External or BigLake tables]
    H --> K[BigQuery load jobs]
    K --> I
    I --> L[Transform and data quality]
    J --> L
    L --> M[BigQuery curated and marts]
    M --> N[BI dashboards and analytics]
    M --> O[Machine learning and downstream APIs]
    P[IAM governance metadata and lineage] -.-> H
    P -.-> M
    Q[Monitoring logging budgets] -.-> B
    Q -.-> L
    Q -.-> M
~~~

Sơ đồ này minh họa các **đường đi có thể chọn**, không yêu cầu mọi nguồn đồng thời dùng tất cả dịch vụ. Ví dụ, file CSV từ đối tác có thể đi thẳng vào Cloud Storage và sau đó qua một load job. Sự kiện cần gần thời gian thực có thể đi Pub/Sub → Dataflow → BigQuery; nếu cần khả năng replay dài hạn, pipeline cũng có thể ghi một bản raw có kiểm soát vào Cloud Storage.

### Tại sao giữ raw lake?

Khi có bug ở logic chuyển đổi, dữ liệu được giữ nguyên giúp chạy lại pipeline mà không phải yêu cầu nguồn phát lại. Raw lake còn hỗ trợ truy vết: dữ liệu đầu vào nào đã tạo ra một kết quả trên báo cáo?

Tuy nhiên, raw lake không miễn trách nhiệm quản lý. Cần giới hạn quyền, phân loại thông tin nhạy cảm, thiết lập retention, gắn metadata và tránh tạo nhiều file quá nhỏ không thể quản trị.

## 3. Tách các vùng dữ liệu: raw, staging, curated và marts

Một kiến trúc rõ ràng nên tách các mức độ tin cậy của dữ liệu.

| Vùng | Vị trí gợi ý | Nội dung | Người tiêu thụ |
|---|---|---|---|
| Landing/raw | Cloud Storage bucket/prefix riêng | File gốc, schema gốc, ingestion metadata | Pipeline và data engineers |
| Quarantine | Cloud Storage bucket/prefix giới hạn | File lỗi định dạng, checksum hoặc schema | Nhóm vận hành dữ liệu |
| Staging | BigQuery dataset riêng | Dữ liệu vừa load, chưa được kiểm tra hết | ELT jobs |
| Cleaned/curated | BigQuery dataset riêng | Chuẩn hóa kiểu, deduplicate, quality checks | Data analysts, data products |
| Gold/data marts | BigQuery dataset theo miền nghiệp vụ | Bảng fact/dimension, aggregate, BI | Dashboard, consumers được cấp quyền |
| Archive | Cloud Storage storage class phù hợp | Dữ liệu cũ, ít truy vấn, phải giữ theo chính sách | Replay/audit theo yêu cầu |

Các vùng này tương tự ý tưởng bronze/silver/gold nhưng không bắt buộc phải dùng đúng tên đó. Quan trọng hơn là **một vùng chỉ chứa dữ liệu đạt mức cam kết tương ứng**.

### Không trộn raw và data mart

Nếu dashboard đọc trực tiếp file raw với schema thay đổi không kiểm soát, một file mới sai định dạng có thể làm báo cáo lỗi. Một lớp staging và quality gate giúp lỗi được cô lập trước khi dữ liệu đến người dùng.

### Trách nhiệm của từng vùng

- Raw: không sửa object gốc sau khi công bố, ghi source và thời điểm tiếp nhận.
- Staging: xác nhận file đọc được, kiểu dữ liệu có thể parse và metadata đủ.
- Curated: kiểm tra business keys, deduplication, freshness và chuẩn hóa.
- Marts: giữ hợp đồng dữ liệu ổn định cho BI và các downstream systems.

## 4. Thiết kế project, location và ranh giới môi trường

Data platform cần quyết định trước dữ liệu ở project nào, region nào và ai có quyền truy cập.

Ví dụ tổ chức:

~~~text
gcp-data-dev          : phát triển, dữ liệu tổng hợp
gcp-data-staging      : kiểm thử pipeline và hợp đồng dữ liệu
gcp-data-prod         : pipelines và bảng production
gcp-security-logging  : audit logs và giám sát theo chính sách
~~~

Trong production có thể chia project theo trách nhiệm ingestion, analytics và security. Tuy nhiên, số project nên phù hợp độ phức tạp vận hành. Tách project chỉ có giá trị khi ranh giới IAM, billing và trách nhiệm thực sự rõ ràng.

### Location compatibility

- Chọn location Cloud Storage bucket theo yêu cầu residency, latency và dữ liệu nguồn.
- Chọn location BigQuery dataset trước khi tạo bảng; vị trí dataset không thể tùy ý đổi bằng một lệnh cấu hình đơn giản.
- Với load job hoặc external table, **vị trí bucket và BigQuery dataset phải tương thích theo quy tắc location của BigQuery**. Không mặc định mọi bucket multi-region đều tương thích với mọi regional dataset bên trong.
- Với Dataflow, Pub/Sub hoặc pipeline cross-region, kiểm tra nơi xử lý, dịch chuyển dữ liệu và egress.
- Nếu dùng CMEK, vị trí key và dịch vụ được mã hóa phải tương thích theo yêu cầu từng dịch vụ.

Ví dụ, một thiết kế regional có thể đặt bucket raw và BigQuery datasets trong `asia-southeast1`, sau khi xác minh dịch vụ và chính sách cho phép. Không thiết lập region chỉ vì ở gần người dùng; yêu cầu pháp lý và hệ thống upstream cũng quan trọng.

### Tách môi trường

Không nên cho staging pipeline ghi vào bucket hoặc dataset production chỉ để tiết kiệm công tạo fixture. Hãy dùng service account, resource names, quotas và dữ liệu test riêng, rồi xác minh hạ tầng production qua IaC và release approvals.

## 5. Layout Cloud Storage: bucket, prefix và object naming

Cloud Storage dùng object name trong bucket; dấu `/` thường được dùng để tạo cấu trúc prefix có ý nghĩa.

Một quy ước dễ vận hành:

~~~text
gs://ORG-RAW-BUCKET/
  source=orders-api/
    entity=orders/
      ingest_date=2026-11-19/
        batch_id=run-8c31/
          part-00001.parquet
          part-00002.parquet
          manifest.json
  source=partner-x/
    entity=payments/
      ingest_date=2026-11-19/
        batch_id=run-6e02/
          part-00001.jsonl
~~~

Lợi ích:

- Có thể khoanh vùng dữ liệu theo nguồn, entity và batch.
- Dễ kiểm tra completeness, replay, retention và lifecycle.
- Tránh một thư mục logic chứa hàng triệu object không có cấu trúc.
- Có thể định tuyến pipeline theo prefix được biết trước.
- Dễ kiểm soát lượng dữ liệu được quét khi tạo external tables.

### Ingestion date khác event date

- `event_date`: ngày sự kiện xảy ra trong hệ thống nguồn.
- `ingest_date`: ngày data platform nhận dữ liệu.

Một đơn phát sinh ngày 15 nhưng đến ngày 19 mới được ingest là dữ liệu đến muộn. Nếu chỉ dựa vào `ingest_date` để phân tích doanh thu theo ngày bán, kết quả có thể sai. Nên giữ cả timestamp nguồn và timestamp ingest.

### Tránh object ghi dang dở và file quá nhỏ

Object cần được xem là hoàn chỉnh khi upload đã kết thúc thành công. Một batch nhiều object nên có manifest hoặc trạng thái batch hoàn tất, không chỉ dựa vào việc nhìn thấy file đầu tiên.

Rất nhiều file Parquet nhỏ có thể làm tăng số lần liệt kê/đọc metadata và giảm hiệu quả xử lý. Pipeline nên chọn kích thước file đủ lớn theo workload và khả năng xử lý; không áp dụng một kích thước cố định cho mọi nguồn.

### Tính bất biến

Với raw dữ liệu dùng để audit/replay, ưu tiên ghi object mới thay vì ghi đè. Có thể sử dụng object generation và preconditions để tránh vô tình overwrite. Nếu bật versioning hoặc retention, phải tính cả chi phí giữ các phiên bản và cách thực thi quyền xóa.

## 6. Chọn định dạng dữ liệu và quản lý schema

Các định dạng phổ biến:

| Format | Lợi ích | Hạn chế và lưu ý |
|---|---|---|
| CSV | Đơn giản, dễ trao đổi với đối tác | Không tự biểu diễn schema/kiểu dữ liệu tốt, dễ lỗi dấu phân cách và encoding |
| JSON Lines | Dễ ghi từng sự kiện, linh hoạt schema | Kích thước lớn hơn, cần xử lý nested fields và schema drift |
| Avro | Có schema, hỗ trợ dữ liệu có cấu trúc và một số kiểu phức tạp | Cần phối hợp schema và compatibility rules |
| Parquet | Dạng cột, compression tốt, phù hợp phân tích | Không tối ưu cho sửa từng record; nhiều file nhỏ kém hiệu quả |
| ORC | Dạng cột, phù hợp một số workload phân tích | Tính tương thích phụ thuộc toolchain |

Với dữ liệu phân tích batch thường xuyên đọc một phần cột, Parquet là lựa chọn phổ biến. Với sự kiện streaming, JSON hoặc Avro có thể thuận tiện ở điểm thu nhận; sau đó pipeline có thể chuẩn hóa sang Parquet để lưu dài hạn.

### Schema evolution

Một nguồn có thể thêm cột mới, đổi kiểu `price` từ STRING sang NUMERIC hoặc đổi ý nghĩa của `status`. Cần phân loại:

- Thay đổi tương thích: thêm trường nullable hoặc optional.
- Thay đổi cần migration: đổi kiểu, xóa trường, đổi business semantics.
- Thay đổi phá hợp đồng: tái sử dụng tên trường nhưng thay ý nghĩa.

Không bật schema autodetection rồi coi mọi file mới đều chắc chắn đúng. Trong production nên quản lý schema contract, version và cơ chế xử lý trường không hợp lệ.

### Metadata ingest

Mỗi record hoặc batch nên có ít nhất:

- Source system và entity.
- Batch/run ID.
- Event timestamp và ingest timestamp.
- Schema version.
- Object URI, generation hoặc checksum khi phù hợp.
- Số lượng record kỳ vọng và thực tế.

Thông tin này giúp đối chiếu từ BigQuery về đúng file gốc.

## 7. Chọn kiến trúc ingestion theo độ trễ

### Batch ingest

Phù hợp file đối tác, daily export hoặc batch từ một hệ thống nguồn:

~~~text
Source export
  → Cloud Storage landing
  → Validate files/manifest
  → BigQuery load job
  → SQL transforms and quality gate
  → Curated tables and marts
~~~

Có thể điều phối bằng Cloud Scheduler + Workflows, Cloud Composer hoặc pipeline orchestration phù hợp. BigQuery Data Transfer Service hỗ trợ một số kiểu truyền dữ liệu từ Cloud Storage theo lịch, nhưng cần xem đúng loại nguồn và cách đặt tên file khi chọn giải pháp này.

### Streaming hoặc gần thời gian thực

~~~text
Application event → Pub/Sub → Dataflow → BigQuery
                                  └─────→ Cloud Storage raw
~~~

Với yêu cầu write trực tiếp vào BigQuery, có thể xem BigQuery Storage Write API và các connector được hỗ trợ. Streaming không có nghĩa mọi record lập tức sẵn sàng cho mọi thao tác downstream; cần định nghĩa mục tiêu freshness và cách đo thời gian từ nguồn đến bảng đích.

### CDC

Đối với database nguồn, Datastream hoặc giải pháp CDC khác có thể xuất thay đổi để đưa vào Cloud Storage/BigQuery thông qua pipeline được hỗ trợ. CDC thường có update, delete và out-of-order events; **không thể đơn giản append tất cả thay đổi rồi coi bảng kết quả là trạng thái hiện tại**.

### Khi nào cần Cloud Storage ở giữa?

Cloud Storage raw hữu ích khi cần replay, audit, trao đổi file hoặc dữ liệu gốc. Nếu ứng dụng cần analytics gần thời gian thực với độ trễ thấp, đường ghi trực tiếp Pub/Sub/Dataflow → BigQuery có thể phù hợp, đồng thời vẫn lưu bản raw bằng luồng riêng nếu nghiệp vụ yêu cầu.

## 8. BigQuery external table: truy vấn dữ liệu trên Cloud Storage

BigQuery external table cho phép khai báo schema/bảng để query file mà không nhất thiết nạp toàn bộ vào native BigQuery storage.

Ví dụ có file Parquet:

~~~text
gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/part-00001.parquet
gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/part-00002.parquet
~~~

Có thể tạo external table cho batch minh họa:

~~~sql
CREATE OR REPLACE EXTERNAL TABLE `PROJECT_ID.raw.orders_20261119_external`
OPTIONS (
  format = 'PARQUET',
  uris = [
    'gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/*.parquet'
  ]
);
~~~

BigQuery đọc schema Parquet và truy vấn từ các object tương ứng. Phải bảo đảm bucket location tương thích với BigQuery dataset và principal có quyền cần thiết.

Truy vấn:

~~~sql
SELECT
  status,
  COUNT(*) AS order_count
FROM `PROJECT_ID.raw.orders_20261119_external`
GROUP BY status
ORDER BY order_count DESC;
~~~

Ví dụ sử dụng một wildcard cho các file trong một partition date. Khi xây external table cho nhiều ngày hoặc Hive-style partitioning, nên cấu hình partition discovery/prefix theo khả năng được hỗ trợ của loại bảng, thay vì giả định một wildcard tùy ý thay được mọi cấp thư mục.

### Khi nào dùng external table?

- Khám phá và xác minh file mới.
- Đọc dữ liệu ít thường xuyên.
- Truy vấn tập dữ liệu được nhiều hệ thống chia sẻ qua Cloud Storage.
- Thực hiện data discovery hoặc kiểm tra migration.

### Giới hạn cần nhớ

Query external table có thể phụ thuộc latency, cấu trúc file, object count, schema và dịch vụ lưu trữ bên ngoài. Không giả định performance, tính năng DML hoặc cơ chế caching giống native BigQuery table. Phải đánh giá theo workload và loại external table cụ thể.

## 9. BigLake và ranh giới quản trị truy cập

**BigLake external tables** dùng cơ chế Cloud resource connection để truy cập dữ liệu ngoài BigQuery theo danh tính được quản lý, thay vì buộc mọi người dùng SQL phải tự được cấp quyền trực tiếp đến bucket theo cách của external table truyền thống.

Ý tưởng:

~~~mermaid
flowchart LR
    A[Analyst or BI service] --> B[BigQuery table permissions]
    B --> C[BigLake external table]
    C --> D[Cloud resource connection]
    D --> E[Connection service account]
    E --> F[Cloud Storage objects]
~~~

Quy trình triển khai về nguyên tắc:

1. Tạo BigQuery connection tại location tương thích với dataset.
2. Xác định service account gắn với connection.
3. Cấp quyền đọc object tối thiểu cho service account này trên bucket/prefix phù hợp với chính sách.
4. Tạo BigLake external table tham chiếu connection và dữ liệu.
5. Cấp quyền BigQuery trên dataset/table cho đối tượng truy vấn.
6. Kiểm tra cả trường hợp được phép và bị từ chối, đồng thời bật audit logs.

Không nên cấp `roles/storage.admin` cho tất cả analysts chỉ để họ query BigLake. Quyền BigQuery, quyền dùng connection và quyền truy cập object là các lớp khác nhau.

### External table thường hay BigLake?

| Tiêu chí | External table thông thường | BigLake external table |
|---|---|---|
| Mục tiêu | Truy vấn file ngoài BigQuery | Truy vấn file ngoài BigQuery với cơ chế quản trị tích hợp hơn |
| Quyền truy cập Cloud Storage | Phụ thuộc cơ chế thông thường và principal truy vấn | Có thể ủy quyền qua connection service account |
| Quyền SQL | Dựa trên BigQuery IAM | Dựa trên BigQuery IAM và cấu hình connection |
| Chi phí/hiệu năng | Phụ thuộc định dạng, query và loại nguồn | Cần benchmark trên workload thực |
| Trường hợp điển hình | Phân tích file đơn giản | Data lake chia sẻ cho nhiều nhóm cần kiểm soát truy cập |

Tên tính năng, giới hạn caching, khả năng fine-grained access control và các định dạng được hỗ trợ có thể thay đổi theo loại bảng và phiên bản dịch vụ; hãy đối chiếu tài liệu sản phẩm trước khi chọn một khả năng làm yêu cầu bắt buộc.

## 10. Nạp vào BigQuery native tables

Khi dữ liệu được truy vấn thường xuyên hoặc tham gia nhiều phép join/aggregate, nạp vào native BigQuery table thường thuận tiện hơn để quản lý schema, partition và tối ưu truy vấn.

Ví dụ tạo dataset và load một batch Parquet:

~~~bash
bq mk --dataset --location=asia-southeast1 PROJECT_ID:staging

bq load \
  --source_format=PARQUET \
  PROJECT_ID:staging.orders_20261119 \
  "gs://ORDERS-RAW-BUCKET/source=orders-api/entity=orders/ingest_date=2026-11-19/*.parquet"
~~~

Đây là ví dụ dành cho môi trường lab; thay project, bucket, location và đường dẫn bằng dữ liệu thực tế. Nếu dataset đã tồn tại, bỏ bước tạo hoặc kiểm tra tồn tại trước khi chạy.

### Tránh append trùng khi retry

Nếu load job bị timeout ở phía orchestrator, không được mặc định job đã thất bại; nó có thể vẫn đang chạy hoặc đã hoàn tất. Chạy lại lệnh append vào cùng bảng mà không có idempotency có thể khiến dữ liệu bị nhân đôi.

Một thiết kế an toàn hơn:

- Mỗi batch có `batch_id` duy nhất.
- Load vào staging table hoặc partition tạm được quản lý riêng.
- Ghi job ID, source object generation và trạng thái hoàn thành.
- Retry dựa trên kết quả job đã có hoặc tạo một tác vụ idempotent theo batch.
- Chỉ sau khi kiểm tra completeness/quality mới publish vào curated table.
- Dùng `MERGE` hoặc chiến lược replace partition có kiểm soát khi cần cập nhật dữ liệu.

**Cloud Storage không cung cấp giao dịch phân tán chung với BigQuery**. Phải tự thiết kế điều phối để tránh trạng thái "file đã có nhưng bảng chưa cập nhật" hoặc "bảng cập nhật hai lần".

## 11. Thiết kế BigQuery partition và clustering

Native BigQuery tables có thể partition theo ngày hoặc timestamp phù hợp, đồng thời cluster theo một số cột truy vấn thường dùng.

Ví dụ tạo bảng curated:

~~~sql
CREATE TABLE IF NOT EXISTS `PROJECT_ID.curated.orders` (
  order_id STRING NOT NULL,
  order_ts TIMESTAMP,
  order_date DATE,
  customer_id STRING,
  amount NUMERIC,
  status STRING,
  updated_at TIMESTAMP
)
PARTITION BY order_date
CLUSTER BY customer_id, status
OPTIONS (
  description = 'Current curated order records'
);
~~~

### Partition theo cột nào?

- `order_date`: hợp lý nếu BI thường lọc theo ngày đặt hàng.
- `ingest_date`: có thể hợp lý nếu chủ yếu truy vấn batch được ingest và cần xử lý late arrivals.
- Một partition key khác: cần dựa vào WHERE clauses thực tế và mô hình cập nhật.

Nếu query dashboard thường chỉ xem 7 hoặc 30 ngày gần nhất, partition pruning giúp giảm dữ liệu quét. Cần chắc rằng query có điều kiện lọc cột partition.

### Clustering

Clustering theo `customer_id` hoặc `status` có thể giúp tối ưu một số bộ lọc và join, nhưng không có nghĩa mọi query đều nhanh hơn. Hiệu quả phụ thuộc kích thước bảng, độ phân bố dữ liệu và query pattern. Không cluster theo một ID gần như duy nhất nếu không có mục đích truy vấn rõ ràng.

### Tránh SELECT *

~~~sql
SELECT
  order_id,
  order_ts,
  amount
FROM `PROJECT_ID.curated.orders`
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-19';
~~~

Query chỉ chọn các cột cần thiết và lọc partition. Trong nhiều mô hình tính phí BigQuery, lượng dữ liệu được xử lý là yếu tố quan trọng; chỉ tăng số slot hoặc capacity không sửa được một query quét dư thừa.

## 12. ELT và data quality: chuyển raw thành curated

Trong mô hình ELT, dữ liệu được đưa vào staging trước rồi biến đổi bằng BigQuery SQL. Với các pipeline cần xử lý định dạng phức tạp hoặc streaming, Dataflow có thể thực hiện bước transform trước khi ghi BigQuery.

### Chuẩn hóa trường và loại bản ghi lỗi

Ví dụ bảng staging có các cột dạng text và timestamp:

~~~sql
CREATE OR REPLACE TABLE `PROJECT_ID.staging.orders_validated` AS
SELECT
  CAST(order_id AS STRING) AS order_id,
  TIMESTAMP(order_time) AS order_ts,
  DATE(TIMESTAMP(order_time)) AS order_date,
  CAST(customer_id AS STRING) AS customer_id,
  SAFE_CAST(amount AS NUMERIC) AS amount,
  CAST(status AS STRING) AS status,
  TIMESTAMP(updated_time) AS updated_at
FROM `PROJECT_ID.staging.orders_20261119`
WHERE
  order_id IS NOT NULL
  AND SAFE_CAST(amount AS NUMERIC) IS NOT NULL;
~~~

Đây là mẫu SQL minh họa: schema staging phải có các trường và kiểu cho phép các biểu thức trên. Với nguồn dễ có timestamp lỗi, nên dùng `SAFE_CAST(... AS TIMESTAMP)` và chuyển record không parse được sang bảng quarantine thay vì để toàn bộ job thất bại ngoài dự kiến.

### Quality gates

Các chỉ số cần kiểm tra:

- Số dòng đọc từ nguồn so với số dòng load.
- Tỷ lệ record lỗi schema/parse.
- Business key null hoặc trùng.
- Giá trị âm không hợp lệ, status không nằm trong tập được phép.
- Phân bố giá trị khác biệt bất thường so với các ngày trước.
- Freshness: dữ liệu mới nhất có đúng kỳ vọng?
- Tính đầy đủ của một batch và checksum/manifest.

Ví dụ kiểm tra bảng:

~~~sql
SELECT
  COUNT(*) AS row_count,
  COUNT(DISTINCT order_id) AS distinct_order_ids,
  COUNTIF(order_id IS NULL) AS null_order_ids,
  COUNTIF(amount < 0) AS negative_amounts
FROM `PROJECT_ID.staging.orders_validated`;
~~~

Đặt ngưỡng chất lượng trước khi publish. Nếu có record lỗi, pipeline có thể quarantine để sửa và replay thay vì âm thầm bỏ qua mà không ghi lại số lượng.

### Dataform và orchestration

Dataform hoặc các công cụ SQL transformation tương thích có thể quản lý dependency giữa các bảng, kiểm thử assertion và publish transformations theo quy trình version control. Orchestrator như Workflows/Cloud Composer điều phối bước phụ thuộc và retry. Dù chọn công cụ nào, pipeline phải ghi lại version của SQL, source batch và kết quả quality gate.

## 13. Incremental MERGE, deduplication và late-arriving data

Ứng dụng nguồn có thể gửi cùng record nhiều lần hoặc update một đơn hàng sau ngày tạo. Nếu mỗi batch được append vào bảng curated, downstream có thể thấy nhiều phiên bản của cùng một đơn.

### Deduplicate theo business key

Giả sử staging có nhiều bản của một order:

~~~sql
SELECT
  order_id,
  customer_id,
  order_ts,
  order_date,
  amount,
  status,
  updated_at
FROM `PROJECT_ID.staging.orders_validated`
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY order_id
  ORDER BY updated_at DESC
) = 1;
~~~

Khi nhiều record có cùng `updated_at`, cần thêm một tie-breaker xác định như source sequence, event version hoặc ingestion sequence. Chỉ order by timestamp có thể không đủ để chọn bản đúng.

### Incremental upsert bằng MERGE

~~~sql
MERGE `PROJECT_ID.curated.orders` T
USING (
  SELECT
    order_id, customer_id, order_ts, order_date,
    amount, status, updated_at
  FROM `PROJECT_ID.staging.orders_validated`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY order_id
    ORDER BY updated_at DESC
  ) = 1
) S
ON T.order_id = S.order_id
WHEN MATCHED AND S.updated_at >= T.updated_at THEN
  UPDATE SET
    customer_id = S.customer_id,
    order_ts = S.order_ts,
    order_date = S.order_date,
    amount = S.amount,
    status = S.status,
    updated_at = S.updated_at
WHEN NOT MATCHED THEN
  INSERT (order_id, customer_id, order_ts, order_date, amount, status, updated_at)
  VALUES (S.order_id, S.customer_id, S.order_ts, S.order_date, S.amount, S.status, S.updated_at);
~~~

Đây là ví dụ cho bản ghi order dạng trạng thái hiện tại. Với bảng lớn, `MERGE` theo business key có thể quét nhiều partition; cần xem xét giới hạn phạm vi ngày/partition khi nghiệp vụ cho phép, clustering và kế hoạch query. Không tự thêm điều kiện ngày vào `ON` nếu có thể khiến một order cũ bị chèn thành record mới.

### Late arrival và correction

Dữ liệu tới muộn cần chiến lược watermark và cửa sổ cập nhật. Ví dụ, mỗi lần chạy xử lý lại 3 ngày gần nhất và có batch reconciliation theo tuần. Cửa sổ phải phù hợp đặc điểm nguồn; dữ liệu correction rất muộn có thể cần workflow backfill riêng.

### Delete event và CDC

CDC delete không nên bị bỏ qua. Nếu event biểu thị bản ghi đã xóa, curated model phải xác định sẽ hard delete, soft delete hay giữ tombstone. Hành vi này phụ thuộc yêu cầu audit và hợp đồng với downstream, không đơn giản là chọn bản có `updated_at` lớn nhất.

## 14. Quản trị dữ liệu và kiểm soát truy cập

Data platform thường chứa dữ liệu tài chính, thông tin người dùng, log nhạy cảm hoặc dữ liệu nội bộ. IAM và governance cần thiết kế từ đầu.

### IAM theo lớp

| Principal | Quyền điển hình | Nguyên tắc |
|---|---|---|
| Ingestion service account | Ghi object vào bucket raw | Chỉ bucket/prefix được cho phép |
| Transformation service account | Đọc raw, chạy BigQuery jobs, ghi staging/curated | Giới hạn dataset và resource |
| Analyst | Chạy BigQuery query, xem marts | Không mặc định đọc raw hoặc staging |
| BI service account | Chỉ đọc data marts hoặc authorized views | Read-only theo nhu cầu |
| Governance/security | Xem metadata, audit và chính sách | Tách quyền truy vấn dữ liệu nội dung khi không cần |
| Pipeline deploy identity | Thay đổi cấu hình IaC/pipeline | Không dùng quyền runtime thay cho quyền deploy |

Những role thường gặp gồm `roles/storage.objectViewer`, `roles/storage.objectCreator`, `roles/bigquery.jobUser`, `roles/bigquery.dataViewer` và `roles/bigquery.dataEditor`. Phạm vi role, quyền thao tác cụ thể và kiểu kết nối phải được xác minh cho dự án thực tế.

### Bảo vệ Cloud Storage

- Dùng uniform bucket-level access khi phù hợp.
- Bật public access prevention cho bucket nội bộ.
- Không chia sẻ bucket raw trực tiếp cho mọi analyst.
- Thiết kế lifecycle, retention và versioning phù hợp dữ liệu.
- Giới hạn service account keys, ưu tiên Workload Identity Federation và runtime identities.

### Bảo vệ BigQuery

BigQuery hỗ trợ quyền trên dataset, table/view và cơ chế kiểm soát chi tiết như row-level access policies, column-level security bằng policy tags, hoặc data masking khi khả năng của dịch vụ và chính sách cho phép.

Ví dụ, analyst có thể xem tổng doanh thu theo region mà không xem email khách hàng. Nên tạo mart/authorized view hoặc chính sách bảo vệ phù hợp, không để người dùng tự chọn `SELECT *` trên bảng raw chứa PII.

### Mã hóa và kiểm soát biên

Cloud Storage và BigQuery có mã hóa mặc định do Google Cloud cung cấp; khi tổ chức yêu cầu tự quản lý khóa, có thể cấu hình CMEK cho resource được hỗ trợ và bảo đảm IAM của key. VPC Service Controls có thể hỗ trợ giảm rủi ro exfiltration trong kiến trúc phù hợp; nó không thay thế IAM và không tự ngăn mọi đường rò rỉ dữ liệu.

## 15. Metadata, lineage và data catalog

Khi số dataset tăng, người dùng cần trả lời:

- Dữ liệu này đến từ đâu?
- Ai chịu trách nhiệm?
- Schema và ý nghĩa nghiệp vụ của các cột là gì?
- Dataset được cập nhật bao lâu một lần?
- Có chứa PII hoặc thông tin nhạy cảm không?
- Bảng nào đang được dashboard sử dụng?
- Nếu đổi tên hoặc xóa cột, consumer nào bị ảnh hưởng?

Một data catalog/governance layer, ví dụ khả năng catalog và data quality của Dataplex, có thể quản lý metadata, phân loại và hỗ trợ khám phá dữ liệu. Dữ liệu lineage cần được thu thập theo pipeline thực tế; không tự suy ra đầy đủ từ tên file.

### Metadata tối thiểu cho một data product

| Trường | Ví dụ |
|---|---|
| Data product | orders_curated |
| Owner | Commerce data team |
| Source | orders-api |
| Frequency | Mỗi 15 phút |
| Freshness objective | 99% batches sẵn trong 15 phút |
| Primary key | order_id |
| Partition key | order_date |
| Classification | Internal; có thể chứa customer identifiers |
| Data contract | Schema v2 |
| Retention | Theo chính sách dữ liệu được phê duyệt |
| Runbook | Cách xử lý batch lỗi và backfill |

Giá trị thời gian trong ví dụ là mục tiêu giả định. Hãy xác định SLO thực tế từ nhu cầu người dùng.

### Data lineage

Một dòng lineage có thể được diễn giải:

~~~text
gs://raw/.../batch_id=run-8c31/part-00001.parquet
  -> staging.orders_20261119
  -> staging.orders_validated
  -> curated.orders
  -> marts.daily_revenue
  -> BI dashboard
~~~

Khi chất lượng dashboard bất thường, lineage giúp truy ngược về job, SQL, nguồn và batch cần đối soát.

## 16. Quan sát pipeline và xác định SLO dữ liệu

Một dashboard vận hành chỉ có "job succeeded" là chưa đủ. Pipeline có thể chạy thành công nhưng nạp thiếu dữ liệu hoặc cập nhật muộn.

### Các SLI nên theo dõi

| Nhóm | Chỉ số | Điều cần phát hiện |
|---|---|---|
| Ingestion | Số batch/file đến, byte, object generation | Nguồn có giao đủ dữ liệu? |
| Freshness | Thời gian từ event đến curated table | Data có trễ? |
| Completeness | Số record expected vs ingested/curated | Có mất dữ liệu? |
| Quality | Null key, duplicate, invalid schema | Dữ liệu có đáng tin cậy? |
| Pipeline | Job duration, failure/retry, backlog | Nút thắt ở bước nào? |
| Query | Slot usage, bytes processed, latency | Truy vấn có vượt budget? |
| Security | IAM changes, access denied, sensitive access | Có truy cập bất thường? |
| Cost | Storage, compute, transfer, logging | Dữ liệu đắt do đâu? |

Một SLO minh họa:

> 99% batch đơn hàng được publish vào dataset curated trong vòng 15 phút kể từ lúc manifest được xác nhận hoàn chỉnh; 100% batch thất bại có cảnh báo và runbook.

Điểm bắt đầu/tính freshness phải rõ ràng: từ event timestamp, object finalized hay manifest ready? Nếu dùng điểm bắt đầu khác, không so sánh số liệu giữa các pipeline một cách máy móc.

### Cloud Monitoring và Cloud Logging

Thu thập logs từ Dataflow, orchestrator, BigQuery jobs và các dịch vụ ingestion. Có thể xuất custom metrics về số record, chất lượng, độ trễ và backlog. BigQuery INFORMATION_SCHEMA có nhiều metadata về jobs; phạm vi view, region và quyền IAM phải phù hợp với project đang truy vấn.

Ví dụ theo dõi job thất bại từ nguồn log:

- Pipeline run ID và batch ID.
- GCP job ID, trạng thái và mã lỗi.
- Source object URIs, generations và row count.
- Query/destination table.
- Retry count và người phụ trách.
- Timestamp bắt đầu/kết thúc.

Không đưa dữ liệu hàng khách hoặc secret payload vào log.

## 17. Tối ưu hiệu năng và chi phí của toàn platform

Tổng chi phí không chỉ gồm BigQuery query. Cần xét cả lưu object, đọc/ghi object, Dataflow/compute, chuyển vùng dữ liệu, orchestration và observability.

### BigQuery

- Chọn partition theo cách người dùng truy vấn.
- Dùng clustering khi bảng đủ lớn và filter patterns hỗ trợ.
- Tránh `SELECT *` trong query quét bảng rộng.
- Dùng aggregate/data mart hoặc materialized view khi workload phù hợp.
- Xem xét chế độ tính phí compute theo nhu cầu hoặc theo capacity/editions, tùy tổ chức.
- Dùng query dry run và quan sát bytes processed/slot usage trước khi chấp nhận query đắt.
- Thiết lập hạn mức và cảnh báo chi phí theo project/workload.

### Cloud Storage

- Dùng file dạng cột và compression phù hợp khi thường xuyên scan.
- Tối ưu kích thước và số object cho ingestion/query pattern.
- Chọn storage class và lifecycle theo tần suất truy cập thực.
- Cân nhắc chi phí operation, retrieval, minimum storage duration và egress khi chuyển class hoặc region.
- Tránh giữ nhiều bản raw và curated giống hệt nhau mà không có mục tiêu phục hồi hoặc quản trị.

### External so với native

Một external table có thể giảm nhu cầu sao chép dữ liệu, nhưng query lặp lại có thể phải đọc nhiều object. Native table có chi phí lưu trữ riêng nhưng có thể đem lại tốc độ và khả năng tối ưu phù hợp hơn với dashboard tần suất cao.

Hãy benchmark bằng **cùng tập dữ liệu, cùng loại truy vấn và cùng mục tiêu freshness**. Không có câu trả lời "external luôn rẻ hơn" hay "native luôn nhanh hơn" cho mọi workload.

### Chi phí trên một data product

Một KPI hữu ích là chi phí để đưa dữ liệu sạch sẵn sàng cho người dùng, ví dụ chi phí trên một triệu record valid hoặc chi phí hàng tháng của một data mart. Nếu chỉ tối ưu giá lưu raw mà pipeline phải chạy lại toàn bộ dữ liệu mỗi ngày, tổng chi phí có thể tăng.

## 18. Reliability, backup và khôi phục dữ liệu

Kiến trúc cần xử lý hai nhóm sự cố:

1. Lỗi pipeline: dữ liệu đến muộn, job fail, schema drift hoặc record trùng.
2. Lỗi dữ liệu/tài nguyên: xóa nhầm object, bảng bị overwrite, cấu hình IAM sai hoặc dữ liệu corrupted.

### Thiết kế replay và reprocessing

Giữ raw object cùng batch metadata đủ lâu để có thể:

- Tạo lại staging sau một lần load lỗi.
- Chạy lại transformation với version SQL mới.
- Backfill khoảng thời gian bị thiếu.
- Đối soát số record và checksum với nguồn.
- Truy vết dashboard về input.

Replay phải **idempotent**: không được nhân đôi dữ liệu trong curated hoặc gây phát lại side effect nghiệp vụ ngoài ý muốn.

### GCS versioning và retention

Versioning cho phép giữ các generation cũ khi object bị thay thế hoặc xóa theo cơ chế được cấu hình. Retention policy giữ object tối thiểu theo chính sách; khi khóa retention, việc thay đổi có thể bị hạn chế nghiêm ngặt. Những cơ chế này bảo vệ dữ liệu theo cách khác nhau và có thể làm tăng chi phí.

### BigQuery recovery

BigQuery có cơ chế time travel với thời gian lưu được cấu hình trong giới hạn hỗ trợ; table snapshots/copies và quy trình export có thể đóng vai trò trong khôi phục hoặc DR. Không dựa hoàn toàn vào time travel để đáp ứng yêu cầu lưu giữ dài hạn hoặc cross-region disaster recovery.

### DR và mục tiêu khôi phục

Xác định:

- RPO: có thể mất tối đa bao nhiêu dữ liệu gần đây?
- RTO: chấp nhận mất bao lâu để data product hoạt động lại?
- Cần phục hồi raw, staging hay curated trước?
- Consumer BI có thể tạm dùng phiên bản dữ liệu cũ được công bố không?
- Có tài nguyên dự phòng đúng region/đúng chính sách không?
- Khóa CMEK và IAM có sẵn khi khôi phục không?

Thực hiện restore drill trên dữ liệu thử nghiệm; backup tồn tại không có nghĩa restore chắc chắn thành công.

## 19. Infrastructure as Code, CI/CD và thay đổi schema

Để nền tảng dễ vận hành, cấu hình Cloud Storage, BigQuery datasets, IAM, connections, network và pipeline nên được quản lý theo mã khi phù hợp.

Ví dụ HCL tối giản:

~~~hcl
resource "google_storage_bucket" "raw" {
  name                        = "ORG-UNIQUE-RAW-BUCKET"
  location                    = "ASIA-SOUTHEAST1"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}

resource "google_bigquery_dataset" "curated" {
  dataset_id                 = "curated"
  location                   = "asia-southeast1"
  delete_contents_on_destroy = false
}
~~~

Tên bucket phải là duy nhất toàn cục; ví dụ không thể apply nguyên văn. Cấu hình retention, lifecycle, labels, CMEK, IAM và protection cần được thêm theo chính sách tổ chức.

### Change management

- Pull request review cho SQL transformations, schema contracts và IaC.
- Terraform plan review trước khi apply, đặc biệt với delete/replace resource.
- Unit tests cho data transformations có logic phức tạp.
- Integration tests trên dataset thử nghiệm và sample production-like.
- Data quality assertions trước khi publish.
- Rollback hoặc forward-fix được lập kế hoạch cho thay đổi schema.
- Không hardcode credential trong mã hay manifest.

Với BigQuery, thay đổi `DROP COLUMN`, đổi kiểu hoặc overwrite bảng curated có thể phá dashboard. Hãy dùng cách thêm cột tương thích ngược, view/versioned data product và migration có giai đoạn.

## 20. Tình huống thực hành: data platform cho hệ thống đơn hàng

Giả sử một hệ thống có:

- Orders API ghi giao dịch vào Cloud SQL.
- Pub/Sub gửi các sự kiện `OrderCreated` và `OrderUpdated`.
- Đối tác hằng ngày xuất file Parquet về đơn thanh toán.
- Nhóm BI cần doanh thu theo ngày, khu vực và trạng thái.
- Nhóm vận hành cần khả năng replay và đối soát dữ liệu.

### Bước 1 — Xác định data contracts

Định nghĩa schema đơn hàng, business key `order_id`, timestamp nguồn, version sự kiện, cột `amount`, `status`, `customer_id` và schema version. Đặt mục tiêu freshness và completeness cho từng nguồn.

### Bước 2 — Tạo vùng lưu trữ

Tạo bucket raw regional và dataset BigQuery cho `raw`, `staging`, `curated`, `marts` tại location tương thích. Cấu hình uniform bucket-level access, IAM và retention theo chính sách.

### Bước 3 — Batch ingest từ đối tác

1. Đối tác upload file Parquet theo `source=partner/entity=payments/ingest_date=...`.
2. Ingest workflow xác minh batch manifest, checksum và schema.
3. File lỗi được chuyển sang quarantine có ghi lý do.
4. File hợp lệ được load vào staging table theo batch ID.
5. Quality gate đối chiếu record count và giá trị nghiệp vụ.

### Bước 4 — Ingest sự kiện

Pub/Sub nhận events, Dataflow chuẩn hóa và ghi về BigQuery staging; có thể lưu raw events về Cloud Storage để replay nếu chính sách yêu cầu. Mọi event cần có event ID và event timestamp, và consumer phải xử lý được redelivery/out-of-order.

### Bước 5 — Curate và deduplicate

BigQuery SQL/Dataform:

- Chuẩn hóa kiểu và timezone.
- Deduplicate theo `order_id`/event version.
- Áp dụng update/delete từ CDC nếu có.
- Chuyển record không hợp lệ sang quarantine.
- Publish bảng `curated.orders` sau khi quality gate đạt.

### Bước 6 — Tạo mart doanh thu

Ví dụ:

~~~sql
CREATE OR REPLACE TABLE `PROJECT_ID.marts.daily_revenue`
PARTITION BY order_date
AS
SELECT
  order_date,
  status,
  COUNT(*) AS order_count,
  SUM(amount) AS total_amount
FROM `PROJECT_ID.curated.orders`
WHERE amount IS NOT NULL
GROUP BY order_date, status;
~~~

Nếu dùng bảng này cho nhiều năm dữ liệu, cân nhắc incremental update theo partition thay vì `CREATE OR REPLACE` toàn bảng mỗi lần. Đồng thời cần định nghĩa rõ các trạng thái nào tính vào doanh thu thực tế, tránh đếm cả đơn đã hủy.

### Bước 7 — Phân quyền và quan sát

- Data engineering identity có quyền ghi staging/curated.
- Analyst chỉ đọc marts và views đã được phê duyệt.
- Không cho BI service account đọc trực tiếp raw PII.
- Dashboard theo dõi freshness, completeness, failed jobs và BigQuery cost.
- Alerts kích hoạt khi thiếu batch, tỷ lệ record lỗi vượt ngưỡng hoặc data product không được cập nhật đúng SLA.

### Bước 8 — Kiểm chứng phục hồi

Giả lập một batch load thất bại. Dùng raw object và manifest để chạy lại cùng batch, xác minh curated không trùng. Tiếp theo, thay đổi schema ở một file lab và kiểm tra quarantine/alert hoạt động trước khi đưa nguồn mới vào production.

## 21. Những lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách cải thiện |
|---|---|---|
| BI query trực tiếp toàn bộ JSON raw | Chậm, schema drift và tốn scan | Chuẩn hóa Parquet hoặc native curated tables |
| Ghi đè file raw không theo dõi generation | Khó audit/replay | Object bất biến và batch manifest |
| Chỉ quản lý ngày ingest | Phân tích sai event date và late arrivals | Lưu event time, ingest time và watermark |
| Một service account có quyền trên mọi project | Rủi ro lộ hoặc phá dữ liệu | Tách identity theo workload và môi trường |
| Không kiểm tra location | Load/external query lỗi hoặc chi phí chuyển vùng | Quy hoạch region/dataset trước |
| Blind append sau retry | Record trùng | Idempotent load và MERGE theo business key |
| Dashboard đọc bảng staging | Chất lượng dữ liệu chưa được bảo đảm | Publish curated sau quality gate |
| Truy vấn `SELECT *` trên bảng rất lớn | Tăng bytes processed | Chỉ chọn cột, partition pruning, marts |
| Mọi file chỉ vài KB | Tăng overhead metadata/queries | Batch và compact file phù hợp |
| Không lưu schema version | Downstream bị phá khi nguồn thay đổi | Data contract và schema evolution |
| Không thử restore | Chỉ biết có backup, chưa biết khôi phục được | Định kỳ diễn tập replay/restore |
| Chỉ theo dõi job succeeded | Không thấy thiếu/trễ record | SLI về freshness, completeness và correctness |

## 22. Checklist kiến trúc trước khi đưa vào production

### Quy hoạch và dữ liệu nguồn

- [ ] Xác định nguồn, format, volume, tần suất và độ trễ yêu cầu.
- [ ] Có data contracts, business keys và schema version.
- [ ] Đã chọn location tương thích cho bucket, BigQuery dataset và pipeline.
- [ ] Đã xác định dữ liệu nhạy cảm, owner và retention.
- [ ] Chọn batch, streaming hoặc CDC dựa trên nhu cầu thật.

### Cloud Storage và ingestion

- [ ] Bucket có IAM tối thiểu, public access prevention phù hợp.
- [ ] Raw object có naming convention, batch ID và metadata.
- [ ] Có manifest/completeness check và quarantine.
- [ ] Có cơ chế dedup và retry không làm nạp trùng.
- [ ] Có chính sách lifecycle/retention và kiểm soát chi phí.

### BigQuery và transformation

- [ ] Đã chọn external/BigLake/native theo query pattern.
- [ ] Query được kiểm tra partition pruning và projected columns.
- [ ] Schema và transformation được version control.
- [ ] Curated tables có quality gates và cơ chế late-arrival.
- [ ] Dashboard chỉ dùng data marts hoặc views ổn định.
- [ ] SQL/ETL jobs có log, job ID và lineage truy vết được.

### Security và governance

- [ ] Tách service accounts ingestion, transformation và consumption.
- [ ] IAM đúng cấp bucket/dataset/table/connection.
- [ ] Có row/column protection khi dữ liệu cần.
- [ ] Credential không hardcode, logs không chứa PII/secret không cần thiết.
- [ ] Audit logs, catalog, data owner và policy exceptions được quản lý.

### SRE, chi phí và khôi phục

- [ ] Có SLO freshness/completeness/correctness và cảnh báo.
- [ ] Có budget, cost allocation và query cost review.
- [ ] Có quy trình backfill, replay, quarantine và rollback.
- [ ] Đã thử restore dữ liệu trong môi trường an toàn.
- [ ] Có runbook cho missing batch, schema drift và truy vấn quá tải.
- [ ] IaC và SQL change được review trước khi triển khai.

Một data platform kết hợp **Cloud Storage + BigQuery** hoạt động tốt khi phân chia rõ dữ liệu gốc và dữ liệu phục vụ phân tích, chọn đường ingestion phù hợp, giữ hợp đồng schema, quản trị truy cập từ bucket đến bảng và đo chất lượng bằng các SLI dữ liệu. Với thiết kế này, tổ chức vừa có nền tảng lưu trữ linh hoạt để audit/replay, vừa có warehouse mạnh để phục vụ BI và các bài toán phân tích trên Google Cloud.

