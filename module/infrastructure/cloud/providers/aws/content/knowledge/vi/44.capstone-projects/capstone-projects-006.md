# Xây dựng data lake từ luồng sự kiện đến dashboard phân tích

## 1. Tổng quan dự án

### 1.1. Bối cảnh

Một nền tảng bán lẻ trực tuyến muốn theo dõi hoạt động đơn hàng gần thời gian thực. Mỗi thao tác trong vòng đời đơn hàng tạo ra một sự kiện: khách hàng tạo đơn, thanh toán được chấp nhận hoặc từ chối, đơn hàng được đóng gói, giao cho đơn vị vận chuyển và giao thành công. Các hệ thống vận hành cần ghi nhận sự kiện liên tục; nhóm phân tích cần dữ liệu lịch sử có cấu trúc để trả lời câu hỏi về doanh thu, số đơn, hiệu quả thanh toán, kênh bán hàng và thời gian hoàn tất đơn.

Bạn sẽ thiết kế và triển khai một data lake trên AWS để nhận sự kiện, lưu bản gốc, chuẩn hóa dữ liệu, lập danh mục metadata, kiểm soát quyền truy cập, truy vấn bằng SQL và hiển thị kết quả trên dashboard. Dự án đi từ một producer nhỏ gửi sự kiện vào stream cho đến một bộ dashboard mà nhóm vận hành và quản lý có thể sử dụng.

Dự án dùng các dịch vụ:

- **Amazon Kinesis Data Streams** nhận sự kiện từ producer theo thời gian thực.
- **Amazon Data Firehose** đọc Kinesis stream và chuyển dữ liệu sang Amazon S3, có thể phân vùng động theo nội dung sự kiện.
- **Amazon S3** lưu các vùng dữ liệu raw, quarantine và curated.
- **AWS Glue Data Catalog và AWS Glue ETL** quản lý schema, partition và chuyển JSON thành Parquet đã chuẩn hóa.
- **AWS Lake Formation** quản lý quyền truy cập database, table và column trên data lake.
- **Amazon Athena** truy vấn dữ liệu trong S3 bằng SQL.
- **AWS Quick Sight** (trước đây là Amazon QuickSight) kết nối Athena để tạo dataset, analysis và dashboard.
- **Amazon CloudWatch và AWS CloudTrail** theo dõi vận hành và hoạt động quản trị.

### 1.2. Mục tiêu nghiệp vụ

Dashboard cuối cùng phải giúp trả lời các câu hỏi:

1. Có bao nhiêu đơn hàng được tạo theo ngày, giờ, kênh và khu vực bán hàng?
2. Tổng giá trị đơn hàng (GMV) và giá trị đơn hàng trung bình (AOV) thay đổi như thế nào?
3. Tỷ lệ thanh toán được chấp nhận so với tổng số đơn đã thanh toán là bao nhiêu?
4. Sản phẩm nào tạo ra nhiều doanh thu nhất?
5. Thời gian trung bình từ lúc tạo đơn đến lúc giao hàng là bao lâu?
6. Có bao nhiêu sự kiện bị lỗi schema hoặc không thể xử lý?
7. Dữ liệu trên dashboard trễ bao lâu so với thời điểm sự kiện phát sinh?

### 1.3. Phạm vi

**Trong phạm vi capstone**

- Xây một luồng sự kiện mẫu cho nghiệp vụ bán lẻ.
- Tạo Kinesis Data Stream và producer gửi JSON event.
- Tạo Firehose delivery stream dùng Kinesis làm source, S3 làm destination.
- Phân vùng dữ liệu S3 theo ngày sự kiện và loại sự kiện.
- Tổ chức raw, error/quarantine và curated zone.
- Dùng Glue crawler/Data Catalog và Glue ETL để chuẩn hóa, kiểm tra dữ liệu và ghi Parquet.
- Dùng Lake Formation và IAM để phân quyền.
- Tạo Athena workgroup, table/view và các truy vấn KPI.
- Tạo AWS Quick Sight dataset và dashboard.
- Thiết lập monitoring, kiểm tra chất lượng, chi phí và quy trình xử lý lỗi.

**Ngoài phạm vi phiên bản cơ bản**

- Tích hợp hệ thống thanh toán, ERP, CRM hoặc website production thật.
- Lưu thông tin thẻ thanh toán, mật khẩu, email hoặc dữ liệu định danh trực tiếp.
- Dựng data warehouse riêng bằng Amazon Redshift.
- Cam kết exactly-once end-to-end hoặc độ trễ sub-second.
- Triển khai multi-account enterprise data mesh.

Có thể mở rộng sang Apache Iceberg, Glue Streaming, Amazon Managed Service for Apache Flink, Redshift hoặc Lake Formation cross-account sau khi hoàn thành kiến trúc cơ bản.

### 1.4. Kết quả bàn giao

Khi hoàn thành, dự án cần có:

- Sơ đồ kiến trúc và data flow.
- Data contract và ít nhất bốn loại event mẫu.
- Kinesis stream và Firehose delivery stream hoạt động.
- S3 bucket có Block Public Access, encryption và các prefix data zone.
- Glue database, raw table, curated table và ETL job.
- Quy tắc chất lượng dữ liệu và vùng quarantine.
- Lake Formation grants cho data engineer và analyst.
- Athena workgroup có query result location riêng và giới hạn chi phí.
- Bộ SQL view/KPI phục vụ dashboard.
- AWS Quick Sight dashboard có filter và các biểu đồ nghiệp vụ.
- CloudWatch dashboard/alarm, runbook và checklist nghiệm thu.
- Tài liệu cleanup để xóa tài nguyên lab.

## 2. Kiến trúc tổng thể

### 2.1. Sơ đồ data flow

```mermaid
flowchart LR
  P[Web / App / Order services] -->|PutRecord(s)| K[Kinesis Data Streams]
  K -->|Kinesis source| F[Amazon Data Firehose]
  F -->|Dynamic partitioning| R[(S3 raw zone)]
  F -->|Delivery/format errors| Q[(S3 error zone)]
  R --> C[AWS Glue Crawler]
  C --> CAT[(Glue Data Catalog)]
  R --> ETL[AWS Glue ETL]
  ETL -->|Validated Parquet| U[(S3 curated zone)]
  U --> CC[AWS Glue Crawler]
  CC --> CAT
  CAT --> LF[AWS Lake Formation]
  LF --> A[Amazon Athena]
  A --> D[AWS Quick Sight]
  D --> V[Operations and business users]
  K -. metrics .-> CW[CloudWatch]
  F -. delivery metrics .-> CW
  ETL -. job logs .-> CW
  A -. query history .-> CW
  IAM[IAM / KMS / CloudTrail] -. governance .-> R
  IAM -. governance .-> CAT
  IAM -. governance .-> A
```

### 2.2. Vai trò của từng tầng

| Tầng | Thành phần | Trách nhiệm |
|---|---|---|
| Event producer | Web/app/order service | Tạo event theo data contract, gắn event ID và event timestamp |
| Ingestion | Kinesis Data Streams | Nhận, buffer và phân phối event tới consumer |
| Delivery | Amazon Data Firehose | Đọc stream, buffer, phân vùng và giao object xuống S3 |
| Raw/landing | S3 raw zone | Giữ bản ghi gần với payload gốc để audit, replay và điều tra |
| Error/quarantine | S3 error zone | Lưu record lỗi delivery, partition extraction hoặc transformation |
| Catalog | AWS Glue Data Catalog | Lưu database, table, schema và partition metadata |
| Processing | AWS Glue ETL | Chuẩn hóa kiểu dữ liệu, kiểm tra chất lượng, deduplicate trong batch và ghi Parquet |
| Governance | AWS Lake Formation + IAM | Kiểm soát quyền trên catalog và dữ liệu S3 |
| Query | Amazon Athena | Truy vấn dữ liệu bằng SQL, tạo view và tổng hợp KPI |
| BI | AWS Quick Sight | Tạo dataset, analysis, dashboard và chia sẻ insight |
| Operations | CloudWatch / CloudTrail | Theo dõi metric, log, alarm và hành động quản trị |

### 2.3. Raw, curated và quarantine zone

Dùng một S3 bucket cho lab để dễ quản lý, nhưng tách vùng dữ liệu bằng prefix:

```text
s3://<DATA_LAKE_BUCKET>/
  raw/
    event_date=YYYY-MM-DD/
      event_type=<event-type>/
        <firehose-object>
  quarantine/
    firehose/
    glue/
  curated/
    events/
      event_date=YYYY-MM-DD/
        event_type=<event-type>/
          part-....snappy.parquet
  athena-results/
  scripts/
  manifests/
```

- **Raw zone** giữ event JSON sau khi Firehose giao xuống S3. Không sửa object raw để bảo toàn bằng chứng nguồn.
- **Quarantine zone** giữ record không hợp lệ, lỗi chuyển đổi hoặc không thể phân vùng. Mỗi record cần lý do lỗi và thời điểm xử lý nếu pipeline có thể bổ sung metadata.
- **Curated zone** giữ dữ liệu đã chuẩn hóa, kiểu dữ liệu ổn định, partition phù hợp và nén Parquet.
- **Athena results** giữ kết quả query riêng, không trộn với dữ liệu đầu vào.
- **Scripts/manifests** lưu Glue ETL script, schema version và manifest triển khai.

Không đặt Athena query result trong raw hoặc curated prefix. Query result có thể chứa dữ liệu đã lọc hoặc tổng hợp, có retention và quyền truy cập khác.

### 2.4. Luồng xử lý và độ trễ

Một event đi qua các bước:

1. Producer tạo event và gọi `PutRecord`/`PutRecords`.
2. Kinesis lưu record tạm thời trong stream theo partition key.
3. Firehose đọc Kinesis source và buffer record theo size/time hint.
4. Firehose trích `event_date` và `event_type` để chọn S3 prefix.
5. Object JSON được ghi vào raw zone; record lỗi có thể đi vào error prefix.
6. Glue crawler cập nhật table/partition metadata; Glue ETL đọc object mới, chuẩn hóa và ghi Parquet.
7. Crawler hoặc quy trình cập nhật metadata làm curated table sẵn sàng cho Athena.
8. Athena truy vấn dữ liệu và AWS Quick Sight cập nhật dataset/dashboard theo chế độ kết nối.

Đây là kiến trúc **near-real-time theo micro-batch**, không phải dashboard real-time tức thời. Firehose có buffering; với dynamic partitioning, độ trễ end-to-end có thể xấp xỉ 1,5 lần buffering hint đã cấu hình. Glue ETL, crawler và chế độ refresh của dashboard còn làm tăng thời gian dữ liệu xuất hiện. Hãy đo từng đoạn thay vì cam kết một con số khi chưa benchmark.

## 3. Data contract cho event bán lẻ

### 3.1. Thiết kế event envelope

Mọi event cần dùng chung envelope để crawler và Glue ETL có thể xử lý ổn định:

| Field | Kiểu | Bắt buộc | Ý nghĩa |
|---|---|---|---|
| `event_id` | string | Có | ID duy nhất để phát hiện bản ghi trùng |
| `event_type` | string | Có | `order_created`, `payment_authorized`, `payment_declined`, `order_shipped`, `order_delivered` |
| `event_ts` | ISO-8601 UTC string | Có | Thời điểm nghiệp vụ xảy ra |
| `event_date` | `YYYY-MM-DD` | Có | Ngày UTC dùng cho dynamic partitioning |
| `schema_version` | string | Có | Phiên bản data contract |
| `order_id` | string | Có | Mã đơn hàng đã pseudonymize |
| `customer_ref` | string | Có | Mã tham chiếu khách hàng, không chứa PII |
| `channel` | string | Có | `web`, `mobile`, `marketplace`, `store` |
| `sales_region` | string | Có | Khu vực kinh doanh, ví dụ `VN-SOUTH` |
| `product_id` | string | Tùy event | SKU hoặc mã sản phẩm |
| `quantity` | integer | Tùy event | Số lượng sản phẩm |
| `unit_price` | decimal | Tùy event | Đơn giá theo currency |
| `amount` | decimal | Tùy event | Giá trị nghiệp vụ của event |
| `currency` | string | Tùy event | Mã ISO 4217, ví dụ `VND` |

Không đưa tên, số điện thoại, email, địa chỉ giao hàng, token thanh toán hoặc dữ liệu thẻ vào event demo. Nếu cần liên kết với hệ thống khách hàng, dùng surrogate ID hoặc token do hệ thống nguồn phát hành và áp dụng quyền truy cập riêng.

### 3.2. Event mẫu: tạo đơn hàng

```json
{
  "event_id": "evt-20261120-000001",
  "event_type": "order_created",
  "event_ts": "2026-11-20T07:30:00Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "product_id": "SKU-CHAIR-01",
  "quantity": 2,
  "unit_price": 1250000,
  "amount": 2500000,
  "currency": "VND"
}
```

Trong phiên bản lab, mỗi order_created là một event tổng hợp cho một đơn hàng và amount là tổng giá trị đơn. Ví dụ có một product_id để minh họa top product. Với đơn nhiều dòng hàng trong production, phát event order_line_created riêng hoặc đưa danh sách items có schema rõ ràng; khi đó top product phải tổng hợp theo line amount, còn AOV phải tính trên tổng amount theo order_id.

### 3.3. Event mẫu: thanh toán

```json
{
  "event_id": "evt-20261120-000002",
  "event_type": "payment_authorized",
  "event_ts": "2026-11-20T07:31:15Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "amount": 2500000,
  "currency": "VND"
}
```

Thanh toán bị từ chối dùng cùng envelope nhưng `event_type` là `payment_declined`; không đưa thông tin nhạy cảm của ngân hàng hoặc lý do từ chối chi tiết vào payload công khai cho analyst.

### 3.4. Event mẫu: giao hàng

```json
{
  "event_id": "evt-20261120-000003",
  "event_type": "order_shipped",
  "event_ts": "2026-11-20T10:45:00Z",
  "event_date": "2026-11-20",
  "schema_version": "1.0",
  "order_id": "ord-100045",
  "customer_ref": "cust-token-0081",
  "channel": "web",
  "sales_region": "VN-SOUTH",
  "amount": 2500000,
  "currency": "VND"
}
```

### 3.5. Quy tắc chất lượng dữ liệu

- `event_id`, `event_type`, `event_ts`, `event_date`, `schema_version` và `order_id` không được null.
- `event_type` phải thuộc danh sách đã công bố.
- `event_ts` phải parse được và có timezone; hệ thống chuẩn hóa về UTC.
- `event_date` phải khớp ngày UTC lấy từ `event_ts`.
- `quantity` phải lớn hơn 0 khi event có sản phẩm.
- `amount` không được âm; currency phải hợp lệ.
- `order_created` phải có channel, sales region, amount, product_id và quantity lớn hơn 0 trong mô hình lab một sản phẩm/đơn.
- Event thanh toán/giao hàng phải tham chiếu order ID đã tồn tại hoặc được phép đến trễ trong cửa sổ xử lý.
- `event_id` duy nhất ở cấp event logic; producer retry phải giữ nguyên event ID.
- Schema change phải tăng `schema_version` và được review trước khi triển khai.

Dữ liệu không đạt quy tắc cần được ghi nhận vào quarantine với `error_code`, `error_message`, `source_object` và thời điểm kiểm tra. Không âm thầm bỏ record lỗi vì sẽ làm sai KPI.

## 4. Chuẩn bị môi trường AWS

### 4.1. Yêu cầu

- AWS account có quyền tạo Kinesis Data Streams, Data Firehose, S3, IAM role, Glue, Lake Formation, Athena và AWS Quick Sight.
- AWS CLI v2 và Python 3.10+ trên máy phát event.
- Boto3 được cài trong virtual environment.
- Một Region có đầy đủ dịch vụ cần dùng; ví dụ lab sử dụng `ap-southeast-1`.
- Có quyền tạo IAM role/policy hoặc được administrator cấp role theo least privilege.
- Dành riêng một bucket cho data lake và một workgroup Athena cho dự án.

Không dùng root access key. Dùng IAM Identity Center hoặc role được cấp. Không commit credentials, bucket policy chứa secret hoặc dữ liệu khách hàng vào source control.

### 4.2. Khởi tạo biến môi trường

Các lệnh minh họa dùng Bash, WSL hoặc AWS CloudShell. Thay Region nếu tổ chức yêu cầu dùng Region khác:

```bash
export AWS_REGION="ap-southeast-1"
export PROJECT="retail-event-lake"
export STREAM_NAME="retail-order-events"
export FIREHOSE_NAME="retail-events-to-s3"
export GLUE_DATABASE="retail_lake"
export ATHENA_WORKGROUP="retail-analytics"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export DATA_LAKE_BUCKET="retail-event-lake-$ACCOUNT_ID-$AWS_REGION"
```

Xác minh identity và Region trước khi tạo tài nguyên:

```bash
aws sts get-caller-identity
aws configure get region
printf 'Account=%s Region=%s Bucket=%s' "$ACCOUNT_ID" "$AWS_REGION" "$DATA_LAKE_BUCKET"
```

Nếu CLI profile không có Region mặc định, truyền `--region "$AWS_REGION"` cho từng lệnh. Bucket name phải duy nhất toàn cầu; account ID và Region làm giảm khả năng trùng nhưng vẫn kiểm tra trước khi tạo.

### 4.3. Tạo S3 bucket

Tạo bucket tại Region đã chọn:

```bash
aws s3api create-bucket --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --create-bucket-configuration LocationConstraint="$AWS_REGION"
```

Bật Block Public Access ở cấp bucket:

```bash
aws s3api put-public-access-block --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Bật versioning cho khả năng phục hồi object bị ghi đè/xóa nhầm:

```bash
aws s3api put-bucket-versioning --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --versioning-configuration Status=Enabled
```

S3 tự động mã hóa object mới bằng SSE-S3 theo mặc định. Với workload yêu cầu kiểm soát key, audit hoặc tách quyền decrypt, có thể cấu hình SSE-KMS bằng customer managed key; khi đó phải cấp quyền KMS tương ứng cho Firehose, Glue, Athena và Quick Sight role cần đọc dữ liệu. Không bật SSE-KMS mà quên key policy.

Cấu hình encryption mặc định SSE-S3 một cách tường minh cho lab:

```bash
aws s3api put-bucket-encryption --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION" --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Kiểm tra bucket:

```bash
aws s3api get-public-access-block --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-versioning --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
aws s3api get-bucket-encryption --bucket "$DATA_LAKE_BUCKET" --region "$AWS_REGION"
```

Không cần tạo sẵn tất cả prefix bằng console; S3 tạo prefix khi object đầu tiên được ghi. Nếu muốn, có thể tạo placeholder folder để dễ quan sát, nhưng placeholder không phải resource riêng.

## 5. Tạo Kinesis Data Stream và producer

### 5.1. Tạo Kinesis stream

Với lab có lưu lượng thấp và thay đổi, dùng On-demand capacity mode để không phải ước lượng shard ban đầu:

```bash
aws kinesis create-stream --region "$AWS_REGION" --stream-name "$STREAM_NAME" --stream-mode-details StreamMode=ON_DEMAND
aws kinesis wait stream-exists --region "$AWS_REGION" --stream-name "$STREAM_NAME"
aws kinesis describe-stream-summary --region "$AWS_REGION" --stream-name "$STREAM_NAME"
```

Kinesis Data Streams lưu record tạm thời để consumer đọc lại. Retention mặc định là 24 giờ; có thể tăng tối đa 365 ngày với phụ phí. Chọn retention dựa trên thời gian tối đa cần để khôi phục consumer, không xem stream như kho lưu trữ lịch sử dài hạn. S3 raw zone mới là nơi lưu dữ liệu lịch sử.

Nếu cần retention 72 giờ cho lab hoặc kiểm thử recovery:

```bash
aws kinesis increase-stream-retention-period --region "$AWS_REGION" --stream-name "$STREAM_NAME" --retention-period-hours 72
```

Khi dùng On-demand mode, Kinesis tự điều chỉnh capacity theo traffic trong giới hạn của dịch vụ. Với throughput ổn định và dự đoán được, Provisioned mode có thể tối ưu chi phí hơn nếu sizing shard chính xác. Cả hai mode đều cần monitoring throttling và quota.

### 5.2. Partition key và thứ tự event

Producer gửi mỗi record với partition key. Kinesis dùng partition key để chọn shard; các record cùng partition key đi vào cùng shard. Sequence number được gán theo shard, không có thứ tự toàn cục giữa mọi shard. API PutRecords không bảo đảm thứ tự record trong cùng một batch. Nếu cần thứ tự tăng nghiêm ngặt cho cùng client/partition key, gửi tuần tự bằng PutRecord và truyền SequenceNumberForOrdering của record thành công trước đó. Trong dự án, dùng order_id làm partition key để các event của cùng đơn hàng có cơ hội nằm cùng shard.

Không dùng một giá trị partition key duy nhất cho toàn bộ event vì sẽ tạo hot shard. Cũng không dùng customer ID nếu một khách hàng có thể phát sinh lượng event vượt trội. Khi lưu lượng tăng, đo partition key distribution và write throttling để đánh giá có cần thay đổi key hoặc tăng capacity.

### 5.3. Tạo môi trường Python

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip boto3
```

Trên Windows PowerShell, kích hoạt bằng `.venv/Scripts/Activate.ps1`. Cấu hình AWS credentials theo profile hoặc IAM role mà môi trường thực thi được phép sử dụng.

### 5.4. Producer mẫu bằng Boto3

Lưu nội dung sau vào file `producer.py`. Ví dụ phát bốn event cho cùng một đơn hàng để minh họa vòng đời order:

```python
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "ap-southeast-1")
STREAM_NAME = os.getenv("STREAM_NAME", "retail-order-events")
kinesis = boto3.client("kinesis", region_name=REGION)


def make_event(event_type, order_id, amount, extra=None, occurred_at=None):
    event_time = occurred_at or datetime.now(timezone.utc)
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_ts": event_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "event_date": event_time.date().isoformat(),
        "schema_version": "1.0",
        "order_id": order_id,
        "customer_ref": "cust-token-0081",
        "channel": "web",
        "sales_region": "VN-SOUTH",
        "amount": amount,
        "currency": "VND"
    }
    if extra:
        event.update(extra)
    return event


def put_event(event, sequence_number_for_ordering=None, max_attempts=5):
    payload = json.dumps(
        event,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")

    for attempt in range(max_attempts):
        try:
            request = {
                "StreamName": STREAM_NAME,
                "Data": payload,
                "PartitionKey": event["order_id"]
            }
            if sequence_number_for_ordering:
                request["SequenceNumberForOrdering"] = sequence_number_for_ordering
            response = kinesis.put_record(**request)
            return response["SequenceNumber"]
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            retryable = {
                "ProvisionedThroughputExceededException",
                "InternalFailure",
                "KMSThrottlingException"
            }
            if code not in retryable or attempt == max_attempts - 1:
                raise
            time.sleep(min(2 ** attempt, 10))


def put_events(events):
    last_sequence_by_partition = {}
    for event in events:
        partition_key = event["order_id"]
        last_sequence_by_partition[partition_key] = put_event(
            event,
            sequence_number_for_ordering=last_sequence_by_partition.get(partition_key)
        )


if __name__ == "__main__":
    order_id = "ord-100045"
    created_at = datetime.now(timezone.utc)
    events = [
        make_event(
            "order_created",
            order_id,
            2500000,
            {
                "product_id": "SKU-CHAIR-01",
                "quantity": 2,
                "unit_price": 1250000
            },
            occurred_at=created_at
        ),
        make_event(
            "payment_authorized",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(minutes=2)
        ),
        make_event(
            "order_shipped",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(hours=3)
        ),
        make_event(
            "order_delivered",
            order_id,
            2500000,
            occurred_at=created_at + timedelta(days=1)
        )
    ]
    put_events(events)
    print(f"Published {len(events)} events for {order_id}")
```


Producer tạo `event_id` một lần trước khi gửi. Khi retry một record bị lỗi, phải giữ nguyên `event_id`; không tạo event mới cho cùng một hành động nghiệp vụ. Ví dụ tối giản ở trên retry record đã serialize và giữ nguyên payload. Trong production, thêm validation schema, structured logging, metric cho failed records và giới hạn retry/dead-letter strategy.

### 5.5. Gửi thử event

```bash
export AWS_REGION="ap-southeast-1"
export STREAM_NAME="retail-order-events"
python producer.py
```

Kiểm tra metric Kinesis như IncomingRecords, IncomingBytes, WriteProvisionedThroughputExceeded (nếu Provisioned mode) hoặc các metric throttling tương ứng. Khi chưa có producer gửi dữ liệu, stream vẫn có thể ở trạng thái ACTIVE nhưng S3 raw zone chưa có object.

## 6. Cấu hình Amazon Data Firehose giao dữ liệu xuống S3

### 6.1. Tạo service role cho Firehose

Firehose cần role để đọc Kinesis stream và ghi object vào bucket. Trust policy cho phép Firehose assume role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "firehose.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

Policy quyền cần giới hạn vào đúng Kinesis stream và bucket của dự án. Ví dụ policy rút gọn:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadKinesisSource",
      "Effect": "Allow",
      "Action": [
        "kinesis:DescribeStream",
        "kinesis:DescribeStreamSummary",
        "kinesis:GetRecords",
        "kinesis:GetShardIterator",
        "kinesis:ListShards"
      ],
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/retail-order-events"
    },
    {
      "Sid": "ListLakeBucket",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListBucket",
        "s3:ListBucketMultipartUploads"
      ],
      "Resource": "arn:aws:s3:::retail-event-lake-111122223333-ap-southeast-1"
    },
    {
      "Sid": "WriteLakeObjects",
      "Effect": "Allow",
      "Action": [
        "s3:AbortMultipartUpload",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::retail-event-lake-111122223333-ap-southeast-1/*"
    }
  ]
}
```

Thay account ID, Region, stream ARN và bucket ARN bằng giá trị thật. Trong production, bổ sung điều kiện aws:SourceAccount và aws:SourceArn phù hợp vào trust policy khi service hỗ trợ để hạn chế confused-deputy risk. Nếu Firehose dùng customer managed KMS key, bổ sung quyền KMS tối thiểu cần thiết và cập nhật key policy để role này được phép mã hóa object. Không dùng wildcard cho mọi stream/bucket trong production. Firehose có thể cần thêm quyền CloudWatch Logs nếu bật error logging; chỉ cấp các action log tương ứng khi sử dụng.

### 6.2. Tạo delivery stream

Tạo Firehose delivery stream với source là Kinesis Data Streams và destination là Amazon S3:

1. Mở Amazon Data Firehose trong Region đã chọn.
2. Chọn tạo delivery stream mới.
3. Source chọn **Amazon Kinesis Data Streams**; chọn stream `retail-order-events`.
4. Destination chọn **Amazon S3** và chọn bucket data lake.
5. Chọn service role đã tạo ở bước trước hoặc tạo role mới qua console.
6. Trong processing, bật **Dynamic partitioning** ngay lúc tạo delivery stream.
7. Thêm processor loại **Metadata extraction**.
8. Chọn JSON parsing engine `JQ-1.6`.
9. Nhập query trích khóa partition như phần tiếp theo.
10. Cấu hình S3 prefix, error prefix, buffer hints và newline delimiter.
11. Tạo stream và chờ trạng thái Active.

Dynamic partitioning chỉ có thể bật khi tạo delivery stream mới. Nếu tạo stream mà quên bật, không thể bật tính năng này về sau cho stream đó; cần tạo stream khác có dynamic partitioning.

### 6.3. Trích partition key bằng JQ

Dùng JQ expression:

```text
{
  "event_date": .event_date,
  "event_type": .event_type
}
```

Cấu hình S3 prefix:

```text
raw/event_date=!{partitionKeyFromQuery:event_date}/event_type=!{partitionKeyFromQuery:event_type}/
```

Cấu hình error output prefix:

```text
quarantine/firehose/!{firehose:error-output-type}/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/
```

Chỉ dùng field có giá trị hữu hạn và được kiểm soát làm partition key. Không partition theo `order_id`, `customer_ref`, `event_id` hoặc transaction ID vì cardinality cao sẽ tạo quá nhiều prefix và buffer nhỏ. Với dự án này, ngày và event type đủ để Athena pruning theo thời gian và nghiệp vụ.

### 6.4. Buffer và newline delimiter

Gợi ý cấu hình lab:

| Tham số | Giá trị gợi ý | Lý do |
|---|---:|---|
| Buffer size | 5 MiB | Giảm số lượng object nhỏ khi traffic đủ |
| Buffer interval | 60 giây | Cân bằng độ trễ và kích thước object |
| New line delimiter | Enabled | Mỗi JSON record trên một dòng, thuận tiện cho Glue/Athena |
| S3 compression | Không nén ở bước đầu | Đơn giản hóa kiểm tra raw; Glue sẽ ghi Parquet Snappy |

Đây là giá trị khởi đầu để benchmark. Khi traffic thấp, buffer theo thời gian sẽ tạo object nhỏ; khi traffic cao, buffer size có thể đạt trước. Với dynamic partitioning, Firehose tạo buffer riêng cho mỗi active partition. Độ trễ end-to-end có thể khoảng 1,5 lần buffering hint time do cơ chế multi-stage buffering.

### 6.5. Giới hạn active partition

Firehose có giới hạn 500 active partitions cho mỗi delivery stream trong delivery buffer theo tài liệu hiện hành; có thể gửi yêu cầu tăng quota đến mức hỗ trợ cao hơn. Nếu vượt giới hạn, record còn lại được đưa vào S3 error prefix với loại lỗi `activePartitionExceeded`.

Để tránh lỗi:

- Partition theo `event_date` và `event_type`, không theo order/customer.
- Giới hạn tập event type theo data contract.
- Theo dõi active partition count và lỗi dynamic partitioning.
- Không tạo partition theo từng phút/giây nếu traffic mỗi partition quá ít.
- Chọn buffer size/time phù hợp với số partition và lưu lượng thực tế.

### 6.6. Lưu ý về Kinesis source

Khi Kinesis Data Streams được cấu hình làm source của Firehose, producer phải ghi vào Kinesis bằng `PutRecord` hoặc `PutRecords`; các API `PutRecord`/`PutRecordBatch` của Firehose bị disable cho delivery stream đó. Firehose bắt đầu đọc Kinesis từ vị trí `LATEST` khi cấu hình source. Vì vậy, tạo Firehose, chờ Active rồi mới chạy producer trong lần thử đầu. Nếu đã gửi event trước khi tạo Firehose, các record cũ không tự động được backfill qua delivery stream này.

Một Kinesis stream có thể có nhiều consumer, nhưng mọi consumer đều chia sẻ giới hạn read của shard. Khi thêm Glue Streaming hoặc consumer khác, kiểm tra read throughput, `GetRecords` throttling và cân nhắc Enhanced Fan-Out khi cần consumer throughput độc lập.

### 6.7. Xác minh Firehose

Sau khi producer gửi event, kiểm tra:

- Firehose delivery stream ở trạng thái Active.
- S3 có object dưới prefix `raw/event_date=.../event_type=.../`.
- Error prefix không tăng bất thường.
- DeliveryToS3.Records, DeliveryToS3.Bytes và DeliveryToS3.Success được ghi nhận.
- DataFreshness và partition-related metric không tăng vượt ngưỡng đã đặt.
- Object có newline delimiter và mỗi dòng parse được thành JSON.

Có thể xem danh sách object bằng lệnh:

```bash
aws s3 ls "s3://$DATA_LAKE_BUCKET/raw/" --recursive
```

Nếu chưa có object, xác minh Firehose source ARN, service role, Kinesis stream activity, bucket policy/KMS policy, prefix extraction và buffer interval. Traffic thấp có thể cần chờ buffer interval trước khi object được giao.

## 7. Tạo Glue Data Catalog và raw table

### 7.1. Tạo Glue database

Tạo database metadata cho data lake:

```bash
aws glue create-database --region "$AWS_REGION" --database-input Name="$GLUE_DATABASE"
```

Glue Data Catalog lưu metadata table, schema và partition; dữ liệu vẫn nằm trong S3. Database trong Catalog không phải database engine lưu record.

### 7.2. Tạo crawler cho raw zone

Trong AWS Glue console:

1. Chọn Crawlers và tạo crawler `retail-raw-crawler`.
2. Data source chọn S3.
3. S3 path là `s3://<DATA_LAKE_BUCKET>/raw/`.
4. IAM role cho crawler cần quyền list/read prefix raw và quyền tạo/cập nhật table trong Glue Catalog.
5. Target database là `retail_lake`.
6. Cấu hình crawler chỉ scan raw prefix, không scan toàn bucket.
7. Chạy crawler sau khi Firehose đã tạo một số object.

Crawler suy luận schema từ JSON và phát hiện partition theo cấu trúc Hive-style `key=value`. Kiểm tra table được tạo, các cột envelope có kiểu phù hợp và partition key `event_date`, `event_type` xuất hiện trong metadata.

Nếu event type có schema khác nhau quá nhiều, crawler có thể tạo nhiều table hoặc chọn schema không mong muốn. Dùng chung envelope, giữ tên field ổn định và đưa payload riêng vào một trường JSON mở rộng nếu cần. Với schema production, nên version hóa schema và quản lý migration có kiểm soát thay vì phụ thuộc hoàn toàn vào crawler inference.

### 7.3. Kiểm tra raw table

Sau khi crawler hoàn tất, mở Athena và chọn Glue database `retail_lake`. Kiểm tra danh sách table và partition. Nếu table name do crawler tạo khác tên mong đợi, dùng đúng tên thực tế trong các bước tiếp theo hoặc đổi tên table có kiểm soát.

Athena có thể truy vấn JSON trực tiếp, nhưng JSON thường tốn dung lượng scan hơn Parquet. Raw table chủ yếu phục vụ kiểm tra, audit và đối chiếu; dashboard nên đọc curated table.

## 8. Xây dựng curated zone bằng AWS Glue ETL

### 8.1. Thiết kế transformation

Glue ETL đọc raw table từ Data Catalog và thực hiện:

1. Parse timestamp về kiểu timestamp.
2. Chuẩn hóa event type, channel và currency.
3. Kiểm tra các trường bắt buộc và giá trị số.
4. Đưa record không hợp lệ vào quarantine.
5. Loại duplicate event_id trong batch hiện tại.
6. Tạo event_date từ event_ts UTC để bảo đảm partition đúng.
7. Ghi dữ liệu hợp lệ thành Parquet nén Snappy, partition theo event_date và event_type.

Parquet dạng columnar giúp Athena chỉ đọc các cột cần thiết. Partition theo ngày giúp giảm lượng dữ liệu scan khi truy vấn khoảng thời gian. Partition theo event type hữu ích khi dashboard thường lọc loại sự kiện. Không tạo partition theo order/customer ID.

### 8.2. Tạo Glue ETL job

Trong AWS Glue console:

- Tạo job Spark với IAM role có quyền đọc raw S3, ghi curated/quarantine S3, đọc Glue Catalog và ghi CloudWatch Logs.
- Chọn Glue version và worker type phù hợp với Region và workload.
- Chọn script location trong S3 prefix scripts/.
- Thêm job parameters `--CURATED_PATH`, `--QUARANTINE_PATH` và `--job-bookmark-option job-bookmark-enable`.
- Bật job bookmarks để Glue theo dõi các object S3 đã xử lý ở source được hỗ trợ.
- Gắn metric/log và timeout theo khối lượng dữ liệu thực tế.

Đổi raw_events trong script thành đúng table name mà crawler tạo. Đường dẫn curated và quarantine phải trỏ tới prefix trong bucket dự án.

### 8.3. Glue PySpark script mẫu

Lưu script dưới tên retail_events_etl.py:

```python
import sys
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.dynamicframe import DynamicFrame
from pyspark.context import SparkContext
from pyspark.sql.functions import (
    col, to_timestamp, to_date, date_format, current_timestamp, lit
)

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "CURATED_PATH", "QUARANTINE_PATH"]
)

sc = SparkContext.getOrCreate()
glue_context = GlueContext(sc)
spark = glue_context.spark_session

job = Job(glue_context)
job.init(args["JOB_NAME"], args)

raw_dyf = glue_context.create_dynamic_frame.from_catalog(
    database="retail_lake",
    table_name="raw_events",
    transformation_ctx="raw_events_source"
)

df = raw_dyf.toDF()

df = (
    df.withColumn("event_ts", to_timestamp(col("event_ts")))
      .withColumn("amount", col("amount").cast("decimal(18,2)"))
      .withColumn("unit_price", col("unit_price").cast("decimal(18,2)"))
      .withColumn("quantity", col("quantity").cast("int"))
)

valid_types = [
    "order_created",
    "payment_authorized",
    "payment_declined",
    "order_shipped",
    "order_delivered"
]

invalid_condition = (
    col("event_id").isNull()
    | col("order_id").isNull()
    | col("event_ts").isNull()
    | col("event_type").isNull()
    | col("schema_version").isNull()
    | col("event_date").isNull()
    | col("channel").isNull()
    | col("sales_region").isNull()
    | (col("event_date") != date_format(to_date(col("event_ts")), "yyyy-MM-dd"))
    | (~col("event_type").isin(valid_types))
    | (
        (col("event_type") == "order_created")
        & (
            col("amount").isNull()
            | (col("amount") < 0)
            | col("product_id").isNull()
            | col("quantity").isNull()
            | (col("quantity") <= 0)
            | col("currency").isNull()
        )
    )
)

invalid = (
    df.filter(invalid_condition)
      .withColumn("error_code", lit("INVALID_EVENT"))
      .withColumn("error_message", lit("Required field or event type is invalid"))
      .withColumn("processed_at", current_timestamp())
)

valid = (
    df.filter(~invalid_condition)
      .dropDuplicates(["event_id"])
      .withColumn("event_date", date_format(to_date(col("event_ts")), "yyyy-MM-dd"))
      .withColumn("processing_ts", current_timestamp())
)

if invalid.limit(1).count() > 0:
    invalid.write.mode("append").json(args["QUARANTINE_PATH"])

curated_dyf = DynamicFrame.fromDF(valid, glue_context, "curated_events")

glue_context.write_dynamic_frame.from_options(
    frame=curated_dyf,
    connection_type="s3",
    connection_options={
        "path": args["CURATED_PATH"],
        "partitionKeys": ["event_date", "event_type"]
    },
    format="glueparquet",
    format_options={"compression": "snappy"},
    transformation_ctx="curated_s3_sink"
)

job.commit()
```

Đây là skeleton cho capstone; trước khi dùng production cần hoàn thiện error handling, kiểm tra schema version, xử lý amount/quantity null theo từng event type, và thêm các field audit. Nếu raw table có partition column event_date từ S3 prefix trùng với field trong JSON, xác nhận schema crawler chỉ tạo một partition key logic trong Catalog. Cập nhật script theo schema thực tế được catalog.

### 8.4. Giới hạn của deduplication và job bookmarks

dropDuplicates(["event_id"]) chỉ loại duplicate trong DataFrame của lần chạy hiện tại. Job bookmarks giúp theo dõi object source đã xử lý, nhưng không biến pipeline thành exactly-once và không tự dọn object output nếu một lần chạy ghi dữ liệu xong rồi lỗi trước khi commit bookmark.

Để tăng độ tin cậy:

- Giữ event_id ổn định qua retry ở producer.
- Bật job bookmarks và không thay đổi source path/transformation context tùy tiện.
- Ghi log số record input, valid, invalid và duplicate.
- Có run ID/processing timestamp để truy vết batch.
- Với yêu cầu upsert/dedup xuyên nhiều lần chạy, cân nhắc Apache Iceberg và MERGE theo event_id hoặc một bảng dedup state chuyên biệt.
- Thiết kế backfill vào output location riêng trước khi promote để tránh append trùng vào curated table.

### 8.5. Crawler cho curated table

Sau khi Glue ETL ghi Parquet:

1. Tạo crawler retail-curated-crawler.
2. S3 target là s3://<DATA_LAKE_BUCKET>/curated/events/.
3. Database là retail_lake.
4. Table prefix có thể đặt curated_.
5. Chạy crawler và xác minh table có format Parquet, compression Snappy, partition keys event_date và event_type.

Nếu lịch ETL chạy thường xuyên, cân nhắc cập nhật partition metadata bằng Glue API hoặc Athena partition projection để giảm chi phí crawler. Không chạy crawler toàn bucket vì nó có thể trộn raw, quarantine, curated và Athena query result thành table không mong muốn.

### 8.6. Kiểm tra dữ liệu curated

Sau crawler, dùng Athena kiểm tra số lượng record:

```sql
SELECT
    event_date,
    event_type,
    COUNT(*) AS event_count,
    COUNT(DISTINCT event_id) AS distinct_events
FROM retail_lake.curated_events
GROUP BY event_date, event_type
ORDER BY event_date DESC, event_type;
```

Đối chiếu tổng event hợp lệ với số record producer đã gửi, trừ record lỗi và duplicate được xác định. Nếu số liệu chênh lệch, kiểm tra Firehose error prefix, Glue job logs, crawler partition và job bookmark state.

## 9. Truy vấn data lake bằng Amazon Athena

### 9.1. Tạo Athena workgroup

Tạo workgroup riêng để kiểm soát vị trí lưu query result, encryption, CloudWatch metrics và bytes scanned:

```bash
aws athena create-work-group --region "$AWS_REGION" --name "$ATHENA_WORKGROUP" --description "Retail event lake analytics" --configuration '{"ResultConfiguration":{"OutputLocation":"s3://'"$DATA_LAKE_BUCKET"'/athena-results/","EncryptionConfiguration":{"EncryptionOption":"SSE_S3"}},"EnforceWorkGroupConfiguration":true,"PublishCloudWatchMetricsEnabled":true,"BytesScannedCutoffPerQuery":1073741824}'
```

Giới hạn 1 GiB trong ví dụ là guardrail cho lab; điều chỉnh theo quy mô query và ngân sách. Khi workgroup enforce configuration, query sẽ dùng output location và encryption do workgroup đặt. Người chạy query vẫn cần quyền Athena và quyền ghi/đọc S3 query result prefix.

### 9.2. Xác minh curated table

Trong Athena query editor, chọn workgroup retail-analytics và database retail_lake. Chạy:

```sql
SHOW TABLES IN retail_lake;

DESCRIBE retail_lake.curated_events;

SELECT *
FROM retail_lake.curated_events
WHERE event_date = '2026-11-20'
LIMIT 20;
```

Thay table name và ngày theo metadata thực tế. Kiểm tra partition pruning bằng cách lọc event_date; tránh query toàn bộ lịch sử khi chỉ cần một ngày.

### 9.3. View doanh thu và số đơn theo ngày

Tạo view cho event tạo đơn hàng:

```sql
CREATE OR REPLACE VIEW retail_lake.v_daily_sales AS
WITH ranked_order_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY processing_ts DESC
        ) AS row_num
    FROM retail_lake.curated_events
    WHERE event_type = 'order_created'
)
SELECT
    event_date,
    channel,
    sales_region,
    currency,
    COUNT(DISTINCT order_id) AS orders_created,
    SUM(amount) AS gross_merchandise_value,
    AVG(amount) AS average_order_value
FROM ranked_order_events
WHERE row_num = 1
GROUP BY event_date, channel, sales_region, currency;
```

GMV ở đây là tổng amount của event order_created. Nếu hệ thống có refund, cancellation, discount hoặc tax event, cần định nghĩa GMV/net revenue rõ ràng và đưa các event điều chỉnh vào logic nghiệp vụ.

### 9.4. View kết quả thanh toán

Tổng hợp event theo order ID để xác định đơn có payment authorized hoặc declined:

```sql
CREATE OR REPLACE VIEW retail_lake.v_payment_outcomes AS
WITH order_payment AS (
    SELECT
        order_id,
        MIN(CASE WHEN event_type = 'order_created' THEN event_date END) AS order_date,
        MAX(CASE WHEN event_type = 'payment_authorized' THEN 1 ELSE 0 END) AS is_authorized,
        MAX(CASE WHEN event_type = 'payment_declined' THEN 1 ELSE 0 END) AS is_declined
    FROM retail_lake.curated_events
    GROUP BY order_id
)
SELECT
    order_date,
    COUNT(*) AS orders_created,
    SUM(is_authorized) AS authorized_orders,
    SUM(is_declined) AS declined_orders,
    CAST(SUM(is_authorized) AS DOUBLE) / NULLIF(COUNT(*), 0) AS authorization_rate
FROM order_payment
WHERE order_date IS NOT NULL
GROUP BY order_date;
```

Nếu một order có nhiều lần retry thanh toán, view trên chỉ đánh dấu order đã từng được authorized/declined. Để đo tỷ lệ theo attempt, cần event/payment_attempt ID riêng và định nghĩa denominator là số lần thử thanh toán.

### 9.5. View thời gian giao hàng

Tính thời gian từ lúc tạo đơn tới lúc giao thành công:

```sql
CREATE OR REPLACE VIEW retail_lake.v_delivery_duration AS
WITH order_lifecycle AS (
    SELECT
        order_id,
        MIN(CASE WHEN event_type = 'order_created' THEN event_ts END) AS created_at,
        MIN(CASE WHEN event_type = 'order_delivered' THEN event_ts END) AS delivered_at
    FROM retail_lake.curated_events
    GROUP BY order_id
),
completed_orders AS (
    SELECT
        order_id,
        date_diff('second', created_at, delivered_at) AS delivery_seconds
    FROM order_lifecycle
    WHERE created_at IS NOT NULL
      AND delivered_at IS NOT NULL
      AND delivered_at >= created_at
)
SELECT
    COUNT(*) AS delivered_orders,
    AVG(delivery_seconds) / 3600.0 AS average_delivery_hours,
    approx_percentile(delivery_seconds, 0.5) / 3600.0 AS median_delivery_hours,
    approx_percentile(delivery_seconds, 0.95) / 3600.0 AS p95_delivery_hours
FROM completed_orders;
```

Nếu cần so sánh theo ngày/khu vực, bổ sung order_date và sales_region vào CTE, đồng thời group theo các field đó. Đơn chưa giao không được tính vào delivery duration nhưng cần một KPI riêng về backlog.

### 9.6. Top sản phẩm theo doanh thu

```sql
WITH ranked_order_events AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY event_id
            ORDER BY processing_ts DESC
        ) AS row_num
    FROM retail_lake.curated_events
    WHERE event_type = 'order_created'
      AND event_date BETWEEN '2026-11-01' AND '2026-11-30'
)
SELECT
    product_id,
    SUM(quantity) AS units_sold,
    SUM(amount) AS gross_sales
FROM ranked_order_events
WHERE row_num = 1
GROUP BY product_id
ORDER BY gross_sales DESC
LIMIT 20;
```

Trong data contract demo, một order_created chứa một product_id. Nếu một order có nhiều dòng hàng, hãy tổng hợp theo order_line event hoặc explode items trước khi tính top product; không dùng tổng order amount như thể đó là doanh thu của từng SKU.

### 9.7. Theo dõi chất lượng và độ trễ dữ liệu

Kiểm tra event thiếu field hoặc event type bất thường trong quarantine. Đối với dữ liệu curated, có thể theo dõi thời gian chênh lệch giữa processing timestamp và event timestamp:

```sql
SELECT
    event_date,
    event_type,
    approx_percentile(
        date_diff('second', event_ts, processing_ts),
        0.95
    ) AS p95_processing_lag_seconds
FROM retail_lake.curated_events
WHERE event_date >= date_format(current_date - INTERVAL '7' DAY, '%Y-%m-%d')
GROUP BY event_date, event_type
ORDER BY event_date DESC, event_type;
```

Processing lag ở đây bao gồm thời gian từ event timestamp đến Glue processing timestamp, không phải toàn bộ thời gian từ producer đến dashboard. Để đo end-to-end freshness, thêm ingestion timestamp do producer hoặc consumer ghi nhận và dashboard refresh timestamp; không suy ra thời gian Firehose delivery chỉ từ event timestamp.

### 9.8. Tối ưu Athena

- Dùng Parquet/ORC thay cho JSON/CSV cho curated analytical workload.
- Partition theo field thường dùng trong WHERE như event_date; giữ partition cardinality hợp lý.
- Chọn cột cần dùng thay vì SELECT *.
- Dùng workgroup riêng theo team/workload và đặt bytes-scanned cutoff.
- Đặt query result trong prefix riêng, bật encryption và lifecycle phù hợp.
- Kiểm tra query execution statistics để phát hiện scan quá lớn.
- Với dữ liệu lớn, cân nhắc compaction để tránh nhiều file nhỏ và partition quá nhỏ.

Athena tính phí theo lượng dữ liệu scan đối với query engine tiêu chuẩn; Parquet, compression và partition pruning giúp giảm bytes scanned. Đặt cutoff giúp dừng query vượt ngưỡng đã cấu hình nhưng không thay thế dashboard cost monitoring.

## 10. Quản trị quyền truy cập với IAM và Lake Formation

### 10.1. Tách vai trò theo trách nhiệm

Không dùng một role admin cho toàn bộ pipeline. Tạo role riêng:

| Principal/role | Quyền cần có |
|---|---|
| Producer role | Ghi record vào đúng Kinesis stream |
| Firehose service role | Đọc stream và ghi đúng S3 prefix |
| Glue crawler role | List/read raw hoặc curated prefix; cập nhật Glue Catalog |
| Glue ETL role | Đọc raw, ghi curated/quarantine, truy cập Catalog và log |
| Data lake administrator | Đăng ký S3 location, quản lý Catalog và cấp Lake Formation permissions |
| Analyst role | Chạy Athena query và đọc curated table được cấp |
| AWS Quick Sight service role | Truy cập Athena, Glue Catalog, query result bucket và data location được cấp |

Tách quyền giúp giảm blast radius. Analyst không cần quyền ghi raw/curated. Producer không cần quyền đọc S3. Firehose không cần quyền xóa bucket hoặc quản trị Glue.

### 10.2. Lake Formation quản lý metadata và data access

AWS Lake Formation dùng Glue Data Catalog làm metadata layer và cung cấp mô hình GRANT/REVOKE cho database, table và column. Một request đọc dữ liệu cần vượt qua cả kiểm tra IAM lẫn Lake Formation:

- IAM cho phép gọi API Athena, Glue và Lake Formation cần thiết.
- Lake Formation cho phép principal đọc database/table/column và data location tương ứng.
- S3/KMS policy cho phép service/principal truy cập object và giải mã dữ liệu.

Quy trình thiết lập:

1. Chọn role quản trị dữ liệu làm Lake Formation data lake administrator.
2. Đăng ký S3 location cho raw và curated prefix bằng role được Lake Formation sử dụng.
3. Xác minh role đăng ký location có quyền truy cập bucket và KMS key nếu dùng SSE-KMS.
4. Cấp DATA_LOCATION_ACCESS cho Glue ETL role trên các S3 location mà job cần đọc/ghi; cấp tương tự cho crawler role nếu crawler truy cập location đã đăng ký.
5. Cấp quyền DESCRIBE trên database và SELECT/DESCRIBE trên curated table cho analyst role.
6. Cấp các quyền tương ứng cho AWS Quick Sight service role hoặc trusted identity principal được cấu hình.
7. Cấp IAM permission lakeformation:GetDataAccess cho principal truy vấn Athena.
8. Kiểm thử bằng analyst role và Quick Sight dataset connection.

Không cấp quyền SELECT trên raw/quarantine cho tất cả analyst nếu họ chỉ cần dữ liệu đã làm sạch. Với dữ liệu nhạy cảm, dùng column-level/data filters hoặc LF-tags để phân quyền theo nhóm.

### 10.3. IAM cho Athena và S3 query result

Athena analyst thường cần:

- Quyền Athena query actions trên workgroup được phép.
- Quyền đọc Glue Data Catalog metadata cần thiết.
- Quyền lakeformation:GetDataAccess nếu bảng được quản lý bằng Lake Formation.
- Quyền đọc data location được Lake Formation/IAM cấp.
- Quyền ghi và đọc S3 query result prefix của workgroup.
- Quyền KMS encrypt/decrypt phù hợp nếu source data, catalog hoặc query result dùng SSE-KMS.

S3 query result bucket phải có Block Public Access, encryption, lifecycle và quyền truy cập tách biệt. Kết quả SQL có thể chứa dữ liệu nhạy cảm; không xem query result là vùng tạm vô hại.

### 10.4. Kiểm soát dữ liệu và audit

- Không lưu PII hoặc payment secret trong event stream.
- Dùng customer token/reference thay vì customer identity trực tiếp.
- Bật S3 Block Public Access ở account/bucket level.
- Bật encryption at rest; dùng SSE-KMS nếu cần customer-managed key và audit key usage.
- Dùng TLS cho producer và service API.
- Ghi CloudTrail management events và data events cho S3 prefix quan trọng theo chính sách audit.
- Dùng bucket versioning và lifecycle để quản lý retention; cân nhắc Object Lock khi có yêu cầu evidence immutability.
- Giới hạn quyền s3:ListBucket, s3:GetObject, s3:PutObject theo prefix.
- Không chia sẻ dashboard/dataset rộng hơn quyền dữ liệu mà Lake Formation đã cấp.

## 11. Tạo dashboard bằng AWS Quick Sight

### 11.1. Kết nối Athena

Tính đến thời điểm biên soạn, capability BI trước đây gọi là Amazon QuickSight được đặt tên AWS Quick Sight trong nền tảng AWS Quick. Các dashboard, dataset, analysis và tích hợp QuickSight hiện có tiếp tục hoạt động; API/SDK hiện hữu vẫn được duy trì.

Các bước:

1. Mở AWS Quick trong Region hỗ trợ.
2. Administrator mở phần quản lý quyền truy cập dịch vụ và cho phép kết nối Amazon Athena.
3. Cấp quyền truy cập S3 query result bucket của Athena.
4. Nếu data lake dùng SSE-KMS, cấp quyền decrypt cho Quick Sight service role theo key policy.
5. Tạo data source mới và chọn Amazon Athena.
6. Chọn workgroup retail-analytics và Glue database retail_lake.
7. Chọn các view v_daily_sales, v_payment_outcomes, v_delivery_duration và curated table cần thiết.
8. Validate connection và tạo dataset.

Nếu Lake Formation được bật, Quick Sight principal cần được grant SELECT/DESCRIBE trên table và database tương ứng. Chỉ bật quyền Athena ở Quick Sight account settings chưa đủ nếu IAM, Lake Formation, S3 hoặc KMS còn thiếu quyền.

### 11.2. Chọn Direct Query hay SPICE

| Chế độ | Cách hoạt động | Khi phù hợp |
|---|---|---|
| Direct Query | Query dữ liệu từ Athena khi dataset/analysis/dashboard được mở hoặc refresh | Dữ liệu cần mới hơn và query workload có thể đáp ứng |
| SPICE | Import snapshot dữ liệu vào in-memory engine | Dashboard cần phản hồi nhanh, số liệu có thể cập nhật theo lịch hoặc API ingestion |

Direct Query không có nghĩa dashboard tự cập nhật tức thời liên tục; dữ liệu được truy vấn lại theo hành vi mở/refresh và caching của sản phẩm. SPICE là snapshot, phải refresh theo lịch hoặc gọi ingestion API sau khi ETL hoàn tất. Chọn theo freshness SLO, độ lớn dataset, chi phí Athena và trải nghiệm người dùng.

Để dashboard lab phản ánh dữ liệu mới nhất sau khi Glue ETL chạy, chọn Direct Query trước. Nếu dùng SPICE, thiết kế bước refresh sau ETL thành công và theo dõi ingestion status.

### 11.3. Thiết kế dashboard vận hành

Tạo một dashboard tên **Retail Event Lake — Operations & Sales** gồm các khu vực:

| Visual | Dataset/view | Mục đích |
|---|---|---|
| KPI: Orders created | v_daily_sales | Số đơn được tạo |
| KPI: GMV | v_daily_sales | Tổng giá trị đơn hàng |
| KPI: Average order value | v_daily_sales | Giá trị trung bình mỗi đơn |
| Line chart: GMV by day | v_daily_sales | Xu hướng doanh thu theo thời gian |
| Bar chart: Sales by channel | v_daily_sales | So sánh web/mobile/marketplace/store |
| Bar chart: Top products | Query top product | Xếp hạng sản phẩm theo doanh thu |
| KPI/stacked bar: Payment outcomes | v_payment_outcomes | Authorized và declined orders |
| KPI: Median/P95 delivery time | v_delivery_duration | Hiệu quả fulfillment |
| Table: Data freshness | Quality/lag query | Thời điểm xử lý và độ trễ dữ liệu |

Thêm filter dùng chung:

- Khoảng thời gian (event_date).
- Sales region.
- Channel.
- Currency.
- Event type khi xem dữ liệu chi tiết.

Đặt định nghĩa KPI trong description hoặc dashboard notes. Ví dụ GMV là tổng amount của event order_created trước refund; payment authorization rate là số order có ít nhất một payment_authorized chia cho số order được tạo trong cùng cohort; delivery duration chỉ tính order có cả created và delivered timestamp.

### 11.4. Chia sẻ dashboard

Chia sẻ dashboard với nhóm vận hành và quản lý thông qua nhóm/user được tổ chức quản lý. Người xem cần quyền sử dụng dashboard và quyền truy cập dataset theo mô hình cấp quyền của AWS Quick Sight. Nếu bật row-level security, kiểm thử bằng từng persona để chắc chắn user chỉ thấy sales region hoặc business unit được phép.

Không chia sẻ dataset raw để tiện dashboard. Dashboard chỉ nên dùng curated view hoặc table có schema và quyền phù hợp.

## 12. Orchestration, monitoring và vận hành

### 12.1. Orchestrate crawler và ETL

Ở capstone cơ bản, dùng AWS Glue Workflow để điều phối:

1. Scheduled trigger chạy raw crawler theo chu kỳ.
2. Khi raw crawler hoàn tất, conditional trigger chạy Glue ETL job.
3. Khi ETL job thành công, conditional trigger chạy curated crawler.
4. Khi curated crawler thành công, đánh dấu batch sẵn sàng cho Athena/Quick Sight.
5. Nếu job/crawler thất bại, gửi notification và giữ trạng thái run để điều tra.

Chu kỳ 5–15 phút là điểm bắt đầu để thử nghiệm, không phải SLA mặc định. Thời gian phù hợp phụ thuộc tốc độ Firehose delivery, số object, crawler duration và Glue startup. Với workload lớn, tránh chạy crawler liên tục; có thể quản lý partition bằng Glue API hoặc partition projection.

Nếu cần orchestration phức tạp hơn, dùng Step Functions để quản lý retry, timeout, backfill, quality gate và refresh Quick Sight SPICE sau khi ETL thành công.

### 12.2. Theo dõi ingestion và delivery

| Dịch vụ | Metric/log cần theo dõi | Tín hiệu cần điều tra |
|---|---|---|
| Kinesis Data Streams | IncomingRecords, IncomingBytes, read/write throttling, iterator age của consumer | Producer tăng lỗi, consumer lag hoặc shard nóng |
| Data Firehose | Records/bytes delivered, delivery success/failure, data freshness, active partition errors | Object không xuất hiện, error prefix tăng hoặc delivery trễ |
| S3 | Object count/size theo prefix, 4xx/5xx request, storage growth | Raw tăng nhưng curated không tăng, nhiều file nhỏ |
| Glue Crawler | Crawler state, duration, table/partition changes | Schema drift hoặc crawler không phát hiện partition |
| Glue ETL | Job run state, duration, DPU time, error logs, input/output/invalid counts | Job fail, invalid rate tăng, runtime tăng đột biến |
| Athena | Query failures, bytes scanned, query duration, workgroup cutoff | Query scan lớn hoặc analyst bị throttling/quota |
| AWS Quick Sight | Dataset refresh/ingestion status, dashboard access errors | Dashboard stale hoặc refresh thất bại |

Tạo CloudWatch alarm cho Firehose delivery failure, Glue job failure, Kinesis throttling/iterator age và error count trong quarantine. Gửi cảnh báo đến SNS hoặc hệ thống incident management được tổ chức phê duyệt.

### 12.3. CloudTrail và audit trail

CloudTrail giúp xác định ai đã tạo/sửa/xóa stream, Firehose, bucket policy, Glue job, workgroup và quyền Lake Formation. Với S3, bật data events cho prefix cần audit theo yêu cầu bảo mật vì data events có thể làm tăng chi phí. Không log payload chứa PII; log event ID, request ID, status và metadata vận hành đủ để truy vết.

### 12.4. Data quality dashboard

Tạo một dashboard phụ hoặc khu vực Quality với các chỉ số:

- Tổng event nhận vào theo ngày.
- Tổng event ghi thành công xuống raw.
- Tổng event lỗi Firehose.
- Tổng event được Glue xử lý.
- Số event invalid/quarantine.
- Tỷ lệ event trùng event_id.
- Số partition được catalog phát hiện.
- P95 processing lag.
- Thời điểm Glue job thành công gần nhất.
- Thời điểm dataset/dashboard được refresh gần nhất.

Đặt ngưỡng theo baseline. Ví dụ, nếu invalid event rate vượt 1% trong 15 phút hoặc Firehose delivery freshness vượt SLO, gửi cảnh báo và tạm dừng publish curated data cho đến khi điều tra.

### 12.5. Runbook khi dữ liệu không xuất hiện trên dashboard

1. Kiểm tra producer log và Kinesis IncomingRecords.
2. Kiểm tra Firehose stream state, source ARN, IAM role và S3 destination.
3. Kiểm tra raw prefix và error prefix.
4. Kiểm tra dynamic partition key trong payload có null/sai format không.
5. Kiểm tra Glue crawler đã cập nhật raw table/partition chưa.
6. Kiểm tra Glue job state, CloudWatch log, bookmark và số record valid/invalid.
7. Kiểm tra curated prefix có Parquet object không.
8. Chạy Athena SELECT trên partition mới để xác minh metadata và quyền truy cập.
9. Kiểm tra Lake Formation grants, IAM, S3 query result permissions và KMS key policy.
10. Kiểm tra Quick Sight Direct Query/SPICE mode và dataset refresh/ingestion history.

Không chạy lại Glue job mù quáng khi chưa biết output đã ghi tới đâu. Job bookmarks không quản lý việc xóa output cũ; rerun có thể tạo duplicate nếu sink dùng append. Với backfill, ghi sang prefix/version mới rồi đối soát trước khi promote.

## 13. Xử lý late event, duplicate và schema evolution

### 13.1. Late-arriving event

Một event có thể đến S3 sau nhiều phút hoặc nhiều giờ do mạng, retry hoặc hệ thống nguồn offline. Dùng event_date được tính từ event_ts UTC để partition theo thời gian nghiệp vụ; record đến trễ sẽ được ghi vào partition của ngày cũ.

Cần bảo đảm Glue crawler/partition management phát hiện partition mới của ngày cũ. Nếu dùng Glue job bookmarks, theo dõi object mới thay vì chỉ xử lý ngày hiện tại. Nếu event timestamp nằm ngoài cửa sổ chấp nhận, ghi quarantine hoặc đánh dấu late event để analyst không nhầm dữ liệu vừa đến với sự kiện vừa xảy ra.

### 13.2. Duplicate event

Kinesis producer có thể retry khi timeout hoặc không nhận được response; một record có thể được gửi lại. Kinesis, Firehose và Glue pipeline không tự bảo đảm exactly-once ở cấp nghiệp vụ. Dùng event_id ổn định và thiết kế xử lý idempotent:

- Producer tạo event_id trước lần gửi đầu và giữ nguyên qua retry.
- Raw zone giữ mọi bản ghi để audit.
- Glue loại duplicate trong từng batch.
- Với dedup xuyên nhiều batch, dùng Iceberg MERGE hoặc một dedup store có khóa event_id.
- Báo cáo phải dùng distinct order_id/event_id đúng với định nghĩa metric.

### 13.3. Schema evolution

Mỗi event có schema_version. Khi thêm field optional, crawler có thể phát hiện schema mới nhưng downstream consumer vẫn cần kiểm thử. Khi đổi kiểu field, đổi tên field hoặc thay semantics, tạo version mới và triển khai chuyển đổi có kiểm soát.

Không tái sử dụng một field với ý nghĩa khác. Không đổi amount từ tổng tiền sang giá trị chiết khấu mà vẫn giữ schema version cũ. Với thay đổi phá vỡ tương thích, giữ bảng curated v1 và tạo curated v2 trong giai đoạn chuyển đổi; chỉ chuyển dashboard sau khi đối soát.

### 13.4. Replay và backfill

Kinesis Data Streams chỉ giữ record trong retention period đã cấu hình. Sau khi hết retention, dùng S3 raw zone để replay/backfill. Tách replay job với job xử lý thường xuyên; dùng output prefix/version riêng để tránh duplicate. Ghi manifest chứa input date range, source object list, code version, job run ID và output location.

## 14. Lựa chọn kiến trúc và hướng mở rộng

### 14.1. Khi nào dùng Firehose, Glue Streaming hoặc Flink?

| Công nghệ | Nên chọn khi | Đánh đổi |
|---|---|---|
| Data Firehose → S3 | Chủ yếu cần capture, buffer, partition và delivery dữ liệu | Có buffering; xử lý phức tạp nên thực hiện sau khi dữ liệu đến S3 |
| Glue Streaming | Cần ETL phức tạp trên stream bằng Spark Structured Streaming, có thể join/enrich và ghi nhiều target | Job chạy liên tục; cần vận hành checkpoint, capacity và schema |
| Managed Service for Apache Flink | Cần xử lý stateful streaming, window, event-time, aggregation và logic real-time phức tạp | Phải thiết kế state, checkpoint, parallelism và vận hành ứng dụng Flink |

Capstone cơ bản chọn Firehose vì mục tiêu chính là thu nhận và giao event vào data lake; Glue ETL xử lý batch sau đó. Nếu yêu cầu nghiệp vụ cần join nhiều stream, enrich record trước khi lưu hoặc tính rolling window theo event time, đánh giá Glue Streaming hoặc Managed Service for Apache Flink.

### 14.2. Mở rộng sang Apache Iceberg

Parquet trên S3 phù hợp với data lake append-oriented và workload đọc phân tích. Khi cần upsert, delete, time travel, schema evolution và transaction ở cấp table, cân nhắc Apache Iceberg:

- Dùng Glue Catalog làm catalog cho Iceberg table.
- ETL ghi dữ liệu theo Iceberg format.
- Dùng Athena engine hỗ trợ Iceberg để query và thao tác table.
- Dùng MERGE theo event_id để xử lý duplicate xuyên nhiều batch.
- Thiết lập compaction, snapshot retention và vacuum theo chính sách.

Iceberg không tự giải quyết mọi vấn đề chất lượng dữ liệu. Vẫn cần event ID ổn định, schema contract, data validation và quyền truy cập Lake Formation.

### 14.3. Mở rộng theo quy mô

Khi dữ liệu tăng:

- Tách account ingestion, data lake, analytics và shared services theo landing zone.
- Dùng Lake Formation cross-account sharing thay vì chia sẻ bucket policy rộng.
- Dùng LF-tags để cấp quyền theo domain, classification và persona.
- Dùng partition projection hoặc quản lý partition qua Glue API để giảm crawler overhead.
- Dùng S3 lifecycle chuyển raw cũ sang storage class phù hợp.
- Compaction file nhỏ và tối ưu Parquet row group.
- Tách workgroup Athena theo team, workload và ngân sách.
- Cân nhắc Redshift nếu cần workload BI concurrency cao hoặc semantic model phức tạp.

## 15. Kịch bản kiểm thử và nghiệm thu

### 15.1. Kiểm thử luồng thành công

| Bước | Hành động | Kết quả mong đợi |
|---|---|---|
| Producer | Gửi order_created, payment_authorized, order_shipped, order_delivered | Kinesis IncomingRecords tăng |
| Firehose | Đọc stream và ghi S3 | Object xuất hiện ở raw prefix đúng ngày/event type |
| Glue crawler | Crawl raw zone | Catalog có schema và partition |
| Glue ETL | Chạy job | Parquet xuất hiện trong curated prefix |
| Curated crawler | Crawl curated zone | Catalog có curated_events table |
| Athena | Query v_daily_sales | Trả về số đơn và GMV phù hợp với event mẫu |
| Athena | Query v_payment_outcomes | Order có payment_authorized được tính đúng |
| Athena | Query v_delivery_duration | Có delivery duration nếu order đã giao |
| AWS Quick Sight | Mở dashboard | Visual và filter hiển thị số liệu |
| Security | Truy vấn bằng analyst role | Chỉ đọc được database/table đã grant |

### 15.2. Kiểm thử lỗi

- Gửi event thiếu event_id: Glue phải đưa vào quarantine.
- Gửi event_type ngoài danh sách: Glue phải đánh dấu invalid.
- Gửi event_date không khớp event_ts: kiểm tra Firehose partition và Glue chuẩn hóa ngày; record cần được cảnh báo hoặc quarantine theo rule.
- Gửi cùng event_id hai lần: xác nhận duplicate được thống kê và không làm tăng KPI ngoài định nghĩa.
- Tạm thời thu hồi quyền S3 của Glue role trong môi trường test: Glue job phải fail rõ ràng, CloudWatch log có AccessDenied và alert được phát.
- Chặn một quyền Lake Formation của analyst: Athena phải từ chối đọc table/column tương ứng.
- Dừng Glue job: raw vẫn tiếp tục nhận event, dashboard thể hiện thời điểm dữ liệu curated gần nhất và cảnh báo freshness.
- Tạo record với event_date lùi ngày: xác minh partition cũ được phát hiện và xử lý.
- Tạo nhiều event_type không hợp lệ hoặc partition key lỗi: theo dõi Firehose error prefix và active partition metric.

Không thực hiện kiểm thử phá hoại trên account production hoặc role dùng chung. Tạo môi trường test và khôi phục quyền sau khi hoàn thành.

### 15.3. Tiêu chí nghiệm thu

Dự án được xem là hoàn thành khi:

- [ ] Producer gửi thành công ít nhất bốn loại event.
- [ ] Firehose đọc Kinesis source và giao object xuống S3.
- [ ] Raw object được phân vùng theo event_date và event_type.
- [ ] Record lỗi delivery/partition có đường điều tra qua error prefix.
- [ ] Glue crawler tạo raw table và partition metadata.
- [ ] Glue ETL ghi curated Parquet với schema ổn định.
- [ ] Invalid event được ghi vào quarantine và có error reason.
- [ ] Curated table có thể truy vấn bằng Athena.
- [ ] Có view GMV/orders, payment outcome và delivery duration.
- [ ] Athena workgroup có result location riêng, encryption và bytes-scanned guardrail.
- [ ] Lake Formation grants và IAM policy đúng persona.
- [ ] AWS Quick Sight dashboard có KPI, trend, channel, product, payment và fulfillment visual.
- [ ] Đo được ingestion lag, processing lag và dashboard refresh mode.
- [ ] Có CloudWatch alarm cho ingestion/delivery/ETL failure.
- [ ] Có runbook, cost estimate và cleanup procedure.
- [ ] Không có PII hoặc payment secret trong dataset demo.

## 16. Chi phí và FinOps

Các nhóm chi phí chính:

| Dịch vụ | Yếu tố chi phí | Cách kiểm soát |
|---|---|---|
| Kinesis Data Streams | On-demand/provisioned capacity, data retention, enhanced fan-out | Chọn mode theo traffic, theo dõi throughput và retention |
| Data Firehose | Volume delivered, format conversion/processing, data transformation | Giảm payload thừa, chọn buffer hợp lý, tránh partition explosion |
| S3 | Storage GB-month, PUT/LIST/GET request, lifecycle/replication | Partition hợp lý, Parquet compression, lifecycle và retention |
| AWS Glue | Crawler/ETL DPU time, continuous job nếu dùng streaming | Giảm crawler frequency, tối ưu worker/job duration |
| Lake Formation | Không thay thế phí S3/Glue/Athena; một số tính năng tích hợp có chi phí service liên quan | Quản lý grants gọn, không scan lại dữ liệu không cần |
| Athena | Bytes scanned và query execution | Parquet, compression, partition pruning, workgroup cutoff |
| AWS Quick Sight | User/author/reader plan, SPICE capacity/ingestion theo edition | Dùng Direct Query hoặc SPICE theo freshness/performance requirement |
| KMS/CloudWatch/CloudTrail | API request, log/metric ingestion và retention | Chỉ log cần thiết, đặt retention và alarm có chọn lọc |

Không hardcode giá trong tài liệu vì giá thay đổi theo Region, edition và thời điểm. Dùng AWS Pricing Calculator để ước tính theo số event/ngày, payload trung bình, retention, số lần ETL, TB Athena scan, số Quick Sight user và SPICE capacity. Tag mọi resource bằng Project, Environment, Owner và CostCenter.

### 16.1. Ước lượng volume

Ước tính dữ liệu raw mỗi ngày:

```text
Raw bytes/day ≈ events_per_day × average_event_size_bytes
Curated bytes/day ≈ raw bytes/day × parquet_compression_ratio
Athena scan ≈ selected_partitions × selected_columns_bytes
```

Ví dụ, 2 triệu event/ngày với payload trung bình 1 KiB tạo khoảng 2 GiB raw/ngày trước overhead. Parquet có thể giảm dung lượng đáng kể, nhưng compression ratio phụ thuộc dữ liệu và schema. Hãy đo bằng object thật thay vì dùng tỷ lệ giả định để chốt ngân sách.

## 17. Cleanup và bảo vệ tài nguyên

Sau khi nghiệm thu, xóa tài nguyên theo dependency:

1. Dừng producer để không phát sinh event mới.
2. Tắt Glue Workflow/Schedule và các crawler schedule.
3. Xóa Quick Sight dashboard/dataset/data source nếu đây chỉ là tài khoản lab.
4. Xóa Glue job, workflow, trigger, crawler và database sau khi lưu kết quả cần giữ.
5. Xóa Firehose delivery stream.
6. Xóa Kinesis Data Stream.
7. Gỡ Lake Formation grants và deregister S3 data location nếu đã đăng ký.
8. Empty S3 bucket và xóa toàn bộ object versions/delete markers vì bucket đã bật versioning.
9. Xóa Athena workgroup.
10. Xóa IAM roles/policies chỉ được tạo riêng cho lab.
11. Nếu dùng customer managed KMS key riêng, kiểm tra không còn dependency rồi mới lên lịch key deletion theo chính sách tổ chức.

Không xóa bucket hoặc KMS key dùng chung. Với bucket versioning, lệnh xóa object thông thường có thể chỉ tạo delete marker; phải xóa các version và delete marker trước khi bucket có thể xóa hoàn toàn. Lưu dashboard screenshot, SQL, job script, schema và runbook trước khi cleanup nếu cần nộp capstone.

## 18. IAM policy mẫu cho producer

Producer chỉ cần ghi event vào đúng Kinesis stream. Ví dụ identity policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublishRetailEvents",
      "Effect": "Allow",
      "Action": [
        "kinesis:PutRecord",
        "kinesis:PutRecords"
      ],
      "Resource": "arn:aws:kinesis:ap-southeast-1:111122223333:stream/retail-order-events"
    }
  ]
}
```

Thay ARN bằng stream thật. Không gắn quyền S3, Glue, Athena hoặc Lake Formation cho producer. Nếu producer chạy trên Lambda, ECS hoặc EC2, gắn policy vào execution/task/instance role; không nhúng access key vào code.

## 19. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Producer bị AccessDenied | Role thiếu PutRecord/PutRecords hoặc ARN sai Region/account | Xác minh caller identity và policy trên đúng stream |
| Kinesis IncomingRecords tăng nhưng S3 không có object | Firehose chưa Active, source sai, buffer chưa đủ thời gian hoặc role thiếu S3 permission | Kiểm tra stream state, source ARN, delivery metrics, buffer và service role |
| Firehose không đọc record đã gửi trước khi tạo delivery stream | Firehose source bắt đầu từ LATEST | Gửi lại event hoặc chạy replay từ raw/archive vào stream mới theo quy trình |
| Object vào error prefix | JQ extraction lỗi, event_date/event_type null hoặc S3/KMS permission fail | Xem error type, kiểm tra payload và role/key policy |
| Active partition exceeded | Partition key cardinality quá cao hoặc buffer quá lâu | Chỉ dùng event_date/event_type, giảm cardinality và đánh giá quota |
| Glue crawler tạo nhiều table ngoài dự kiến | Schema không đồng nhất hoặc crawler scan nhầm prefix | Giới hạn S3 target, thống nhất envelope và tách table/prefix |
| Glue job không tìm thấy table | Crawler chưa chạy, database/table name sai hoặc role thiếu Catalog permission | Kiểm tra Glue Catalog và job role |
| Glue job đọc lại dữ liệu cũ | Bookmark tắt, source path/transformation context thay đổi hoặc bookmark reset | Kiểm tra bookmark state và source object last modified |
| Curated có duplicate | Producer retry, job append sau retry hoặc dedup chỉ trong một batch | Đối soát event_id, dùng Iceberg MERGE nếu cần dedup xuyên batch |
| Athena báo HIVE_PARTITION_SCHEMA_MISMATCH | Partition có schema khác table hoặc crawler cập nhật không nhất quán | Chuẩn hóa schema, sửa partition metadata và chạy lại crawler có kiểm soát |
| Athena AccessDenied | Thiếu IAM, Lake Formation SELECT/GetDataAccess, S3 result permission hoặc KMS decrypt | Kiểm tra từng lớp authorization theo principal thực tế |
| Athena scan quá nhiều dữ liệu | Query không filter partition hoặc table còn JSON | Dùng event_date predicate, curated Parquet và chỉ chọn cột cần thiết |
| Quick Sight không kết nối Athena | Chưa bật quyền Athena/S3, sai workgroup hoặc thiếu KMS/Lake Formation grant | Validate data source và kiểm tra Quick Sight service role |
| Dashboard không có dữ liệu mới | Glue chưa ghi curated, crawler chưa cập nhật, Direct Query/SPICE refresh chưa hoàn tất | Theo dõi pipeline theo từng tầng và kiểm tra refresh history |

## 20. Câu hỏi tự kiểm tra

1. Vì sao data lake cần giữ raw zone nếu đã có curated zone?
2. Kinesis Data Streams và Data Firehose có vai trò khác nhau như thế nào?
3. Firehose đọc Kinesis stream từ vị trí nào khi cấu hình source mới?
4. Vì sao phải tạo Firehose trước khi bắt đầu producer trong lần kiểm thử đầu?
5. Dynamic partitioning cần những field nào trong event contract?
6. Vì sao không nên partition theo order_id hoặc customer_ref?
7. Dynamic partitioning ảnh hưởng độ trễ delivery và active buffer ra sao?
8. Glue Data Catalog lưu dữ liệu hay lưu metadata?
9. Vì sao nên chuyển JSON raw sang Parquet curated?
10. Glue job bookmarks giải quyết vấn đề gì và không giải quyết vấn đề gì?
11. Vì sao dropDuplicates trong một batch không bảo đảm dedup xuyên nhiều batch?
12. Lake Formation và IAM cùng tham gia authorization như thế nào?
13. Athena workgroup giúp kiểm soát query cost và output location ra sao?
14. Direct Query khác SPICE ở freshness và cách refresh như thế nào?
15. Những metric nào giúp phát hiện Firehose delivery lag?
16. Làm thế nào xử lý event đến trễ và partition ngày cũ?
17. Khi nào nên chuyển từ Firehose + batch Glue sang Glue Streaming hoặc Flink?
18. Vì sao không nên lưu PII/payment secret trong event payload?

### Gợi ý trả lời

1. Raw là bằng chứng nguồn, phục vụ audit, replay và đối soát khi transformation sai.
2. Kinesis nhận và lưu stream record tạm thời cho consumer; Firehose đọc stream, buffer và giao dữ liệu đến destination.
3. Firehose bắt đầu từ LATEST.
4. Record gửi trước thời điểm Firehose bắt đầu đọc có thể không được delivery stream mới đọc lại.
5. event_date và event_type trong thiết kế này; event phải có giá trị hợp lệ để JQ extraction thành công.
6. Cardinality cao tạo nhiều active partition và buffer nhỏ, có thể vượt quota.
7. Firehose buffer theo partition; độ trễ end-to-end có thể khoảng 1,5 lần buffering hint và active partition bị giới hạn.
8. Catalog lưu metadata/schema/partition; dữ liệu nằm trong S3 hoặc nguồn dữ liệu khác.
9. Parquet columnar và compression giảm bytes scanned, tăng hiệu quả query.
10. Bookmark theo dõi source đã xử lý để chỉ đọc object mới; không bảo đảm exactly-once và không tự quản lý cleanup sink output.
11. Duplicate có thể đến ở các object/run khác nhau; dropDuplicates chỉ xử lý tập dữ liệu đang nằm trong một DataFrame.
12. IAM cho phép API/service actions; Lake Formation cấp quyền catalog và data; S3/KMS còn phải cho phép truy cập object/key.
13. Workgroup định vị query results, encryption, publish metric và đặt bytes-scanned cutoff.
14. Direct Query đọc source khi người dùng mở/refresh; SPICE lưu snapshot và cần schedule/API ingestion để cập nhật.
15. Delivery success/failure, DataFreshness, record/byte delivered, active partition error và error prefix count.
16. Dựa trên event_ts UTC để phân vùng theo ngày nghiệp vụ, cập nhật metadata cho partition cũ và theo dõi late-event window.
17. Khi cần ETL phức tạp, enrich/join stream, stateful window hoặc latency thấp hơn buffering của Firehose.
18. Giảm rủi ro lộ dữ liệu, giảm phạm vi compliance và hạn chế quyền truy cập của analyst.

## 21. Bộ hồ sơ bàn giao capstone

Bàn giao một thư mục project có cấu trúc dễ tái tạo:

```text
retail-event-lake/
  architecture/
    data-flow.mmd
    adr-001-streaming-ingestion.md
  producer/
    producer.py
    requirements.txt
    sample-events.jsonl
  firehose/
    trust-policy.json
    firehose-s3-prefixes.md
  glue/
    retail_events_etl.py
    raw-crawler-config.md
    curated-crawler-config.md
  athena/
    create-views.sql
    validation-queries.sql
  governance/
    producer-policy.json
    role-matrix.md
    lake-formation-grants.md
  dashboard/
    dashboard-spec.md
    kpi-definitions.md
  operations/
    cloudwatch-alarms.md
    runbook.md
    cleanup.md
  README.md
```

README phải ghi Region, account-specific ARN cần thay, lệnh triển khai, data contract, thứ tự chạy crawler/job, query sample, dashboard refresh mode, cost assumptions và cleanup. Không commit credential, account secret, data thật hoặc file Athena query result có dữ liệu nhạy cảm.

## 22. Tài liệu tham khảo chính thức

- [Amazon Kinesis Data Streams — Developer Guide](https://docs.aws.amazon.com/streams/latest/dev/introduction.html)
- [Kinesis Data Streams key concepts and retention](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Change the Kinesis Data Streams retention period](https://docs.aws.amazon.com/streams/latest/dev/kinesis-extended-retention.html)
- [Kinesis PutRecord API and sequence ordering](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecord.html)
- [Kinesis PutRecords API and ordering limitations](https://docs.aws.amazon.com/kinesis/latest/APIReference/API_PutRecords.html)
- [Configure Kinesis Data Streams as a Data Firehose source](https://docs.aws.amazon.com/firehose/latest/dev/writing-with-kinesis-streams.html)
- [Amazon Data Firehose dynamic partitioning](https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning.html)
- [Enable dynamic partitioning in Data Firehose](https://docs.aws.amazon.com/firehose/latest/dev/dynamic-partitioning-enable.html)
- [Buffer data for dynamic partitioning](https://docs.aws.amazon.com/firehose/latest/dev/buffering.html)
- [Amazon S3 data protection and encryption](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html)
- [AWS Glue Data Catalog best practices](https://docs.aws.amazon.com/glue/latest/dg/best-practice-catalog.html)
- [AWS Glue streaming ETL](https://docs.aws.amazon.com/glue/latest/dg/streaming-chapter.html)
- [AWS Glue job bookmarks](https://docs.aws.amazon.com/glue/latest/dg/monitor-continuations.html)
- [AWS Glue triggers and workflow dependencies](https://docs.aws.amazon.com/glue/latest/dg/about-triggers.html)
- [AWS Lake Formation permissions overview](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-overview.html)
- [Using AWS Lake Formation with Amazon Athena](https://docs.aws.amazon.com/lake-formation/latest/dg/athena-lf.html)
- [Manage Lake Formation and Athena user permissions](https://docs.aws.amazon.com/athena/latest/ug/lf-athena-user-permissions.html)
- [Amazon Athena workgroups](https://docs.aws.amazon.com/athena/latest/ug/workgroups-create-update-delete.html)
- [Specify Athena query result location using a workgroup](https://docs.aws.amazon.com/athena/latest/ug/query-results-specify-location-workgroup.html)
- [AWS Quick Sight supported data sources](https://docs.aws.amazon.com/quick/latest/userguide/supported-data-sources.html)
- [Authorize AWS Quick Sight connections to Athena](https://docs.aws.amazon.com/quick/latest/userguide/athena.html)
- [Refresh data in AWS Quick Sight](https://docs.aws.amazon.com/quick/latest/userguide/refreshing-data.html)
- [AWS Quick is now AWS Quick — November 9, 2026](https://aws.amazon.com/about-aws/whats-new/2026/11/amazon-quick-aws-quick/)

