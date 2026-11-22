# Thiết kế chất lượng dữ liệu, phân vùng và tối ưu chi phí phân tích

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group, Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu. Mục tiêu là triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Trong chương **Nền tảng dữ liệu và phân tích**, bài học này kết nối ba bài toán luôn đi cùng nhau: **chất lượng dữ liệu (data quality)**, **phân vùng/lưu trữ dữ liệu phục vụ phân tích (partitioning and layout)** và **chi phí xử lý/truy vấn (analytics cost)**.

Hãy tưởng tượng công ty có hệ thống thương mại điện tử. Các đơn hàng phát sinh từ Azure SQL Database, sự kiện nhấp chuột từ ứng dụng web, thông tin sản phẩm từ API đối tác. Dữ liệu được đưa về **Azure Data Lake Storage Gen2 (ADLS Gen2)**, làm sạch và hợp nhất bằng engine xử lý như Azure Databricks, Spark/Synapse hoặc nền tảng Azure/Fabric tương thích, rồi phục vụ dashboard doanh thu, báo cáo hoàn tiền và dữ liệu huấn luyện mô hình. Chỉ một cột `order_amount` chứa chuỗi `"1,200"` thay vì decimal, một sự kiện trễ rơi sai ngày hoặc một query quét toàn bộ lake có thể làm **sai báo cáo, chậm SLA và tăng hóa đơn cloud** cùng lúc.

Sau bài học, bạn có thể:

- Thiết kế **data contracts**, kiểm tra schema, tính đầy đủ, hợp lệ, duy nhất, nhất quán, độ tươi và truy vết nguồn.
- Tổ chức luồng **bronze → silver → gold**, xác định vị trí kiểm tra chất lượng và quarantine dữ liệu lỗi.
- Xử lý **event time vs ingestion time**, late-arriving events, CDC, duplicate events và incremental/idempotent upsert.
- Chọn **Parquet, Delta Lake hoặc table format phù hợp**; hiểu partition pruning, predicate pushdown, clustering, statistics và file compaction.
- Chọn partition key/granularity theo truy vấn thực tế, tránh over-partitioning, small files và skew.
- Đọc/ghi partition với **PySpark**, truy vấn bằng **SQL**, phân biệt kỹ thuật tổng quát với tính năng tùy engine/tier.
- Tính **chi phí storage, compute, dữ liệu quét, pipeline orchestration, networking, monitoring và retention** trên Azure.
- Thiết lập data quality gates, dashboard, alert, runbook, kiểm thử hồi quy và quy trình cost governance.

## 1. Ba mục tiêu luôn phải cân bằng

Một nền tảng phân tích tốt không chỉ có truy vấn nhanh. Nó cần trả lời cùng lúc:

| Mục tiêu | Câu hỏi | Rủi ro nếu bỏ qua |
|---|---|---|
| **Đúng dữ liệu** | Doanh thu, đơn, khách hàng có chính xác và đáng tin? | Dashboard sai, quyết định kinh doanh sai, mất khả năng kiểm toán |
| **Dữ liệu đến đúng hạn** | Báo cáo 08:00 có đủ giao dịch đến thời điểm chốt? | Trễ SLA, dữ liệu stale, quyết định dựa trên snapshot chưa hoàn chỉnh |
| **Chi phí tương xứng** | Một báo cáo tốn bao nhiêu compute, bytes scanned, storage? | Quét toàn lake, chạy cluster nhàn rỗi, lưu quá nhiều bản sao |

Ba mục tiêu này có thể xung đột: lưu toàn bộ raw data vô hạn hỗ trợ audit nhưng tốn storage; partition mỗi phút nghe có vẻ giúp lọc nhanh nhưng tạo hàng triệu files; validate mọi trường trước ingest có thể làm mất thông tin gốc nếu pipeline loại dữ liệu không hợp lệ quá sớm.

**Nguyên tắc thiết kế:** dữ liệu gốc cần được bảo tồn theo retention/compliance; chất lượng được kiểm tra ở những ranh giới phù hợp; serving tables được tối ưu theo truy vấn cụ thể; chi phí phải đo được ở từng lớp.

### 1.1. Kiến trúc tham chiếu

```text
Azure SQL Database       Web events        Partner API / files
      |                       |                     |
      +-----------------------+---------------------+
                              |
                              v
               Ingestion (ADF / Event Hubs / jobs)
                              |
                              v
               ADLS Gen2 — BRONZE (raw, replayable)
                              |
                    Schema/lineage checkpoints
                              |
                              v
             SILVER (typed, deduplicated, validated)
                    |                   |
                    | valid             | invalid
                    v                   v
            Clean Delta/Parquet       Quarantine
                    |
                    v
             GOLD (curated marts, aggregates)
                    |
           +--------+----------+
           |                   |
        SQL analytics       Power BI/ML/Apps
           |                   |
           +--------+----------+
                    |
             Azure Monitor + DQ + Cost Management
```

Các tên **bronze, silver, gold** là cách tổ chức logic (medallion pattern), không bắt buộc một SKU hoặc engine duy nhất. Azure có nhiều dịch vụ xử lý, truy vấn và báo cáo; khả năng cụ thể của Azure Databricks, Azure Synapse Analytics, Microsoft Fabric, ADF, Azure SQL và các định dạng bảng có thể khác. Hãy xác định **sản phẩm, phiên bản runtime, tier và vùng** trước khi đưa một lệnh hay tối ưu hóa vào production.

### 1.2. Ví dụ KPI nghiệp vụ

Một metric `daily_paid_revenue` có thể yêu cầu:

- Chỉ tính đơn hàng thực sự **PAID**, không tính PENDING.
- Dùng **currency** đúng và quy tắc quy đổi được phiên bản hóa.
- Không đếm lặp cùng `order_id` hoặc cùng payment event.
- Trừ refund theo quy tắc kế toán được thống nhất.
- Báo cáo theo **business date** và timezone đã xác định.
- Có thời điểm **data cutoff** và trạng thái hoàn tất của kỳ.

Chỉ làm sạch kiểu dữ liệu `amount` không giải quyết đủ những vấn đề trên. Cần **hợp đồng metric, data quality, time semantics và lineage**.

## 2. Vai trò của các lớp bronze, silver, gold

| Lớp | Mục tiêu | Đặc điểm | Ví dụ |
|---|---|---|---|
| **Bronze** | Thu nhận bằng chứng gốc để replay/audit | Dữ liệu gần nguyên bản, metadata nguồn, batch ID, ingestion timestamp | JSON/Avro/CSV sự kiện gốc từ Event Hubs |
| **Silver** | Chuẩn hóa và kiểm soát chất lượng | Kiểu dữ liệu rõ, dedup, business keys, CDC/upsert, quarantine | `orders_clean` với `order_amount DECIMAL` |
| **Gold** | Cung cấp dataset/metric cho người tiêu dùng | Aggregates, dimensional model, SCD, data contracts cho BI | `daily_revenue_by_region` |

### 2.1. Vì sao không sửa trực tiếp bản bronze?

Nếu pipeline ghi đè raw event, khi logic parse schema v2 sai sẽ khó replay hoặc chứng minh dữ liệu ban đầu. Bronze nên **append/immutable theo thiết kế khi có thể**, với policy bảo mật/retention và provenance. Không giữ raw data vô thời hạn nếu quy định riêng tư yêu cầu xóa/hết hạn; immutability phải được thiết kế cùng data lifecycle và quyền data subject.

### 2.2. Silver không chỉ là đổi tên cột

Silver có thể thực hiện:

1. Parse dữ liệu theo schema/version.
2. Chuẩn hóa kiểu `decimal`, `timestamp`, business key.
3. Phân biệt null hợp lệ và null do lỗi.
4. Deduplicate theo event ID hoặc business key + version thích hợp.
5. Áp CDC/upsert/delete logic theo thứ tự phiên bản.
6. Tách records lỗi vào **quarantine** kèm reason.
7. Sinh metrics và checkpoint về số lượng, độ tươi, tỷ lệ lỗi.

Không nên tự biến invalid numeric thành 0: sẽ tạo doanh thu sai nhưng không còn dấu vết lỗi.

### 2.3. Gold là hợp đồng phục vụ

Gold có thể chứa tổng hợp ngày/tuần, star schema, semantic model hoặc feature table. Các phép tính như refund, tax, FX rate, timezone phải được thống nhất với chủ nghiệp vụ. Thay đổi definition của một KPI cần **versioning, lineage, test và thông báo cho consumers**.

### 2.4. Replay và tính lặp lại được

Một pipeline tốt có thể chạy lại batch `2026-11-19` mà **không làm dữ liệu tăng đôi**. Raw events nên có identity/offset/ingestion batch ID; silver upsert dựa vào key/version; gold được ghi bằng transaction/overwrite partition hoặc merge phù hợp. Không coi việc “job succeeded” là bằng chứng dữ liệu không bị nhân đôi.

## 3. Data quality là gì? Các chiều đo quan trọng

**Data quality (DQ)** nghĩa là dữ liệu đáp ứng những điều kiện để sử dụng đúng mục đích. Chỉ số không thể áp dụng chung mọi bảng: email trong bảng marketing và amount trong bảng kế toán có yêu cầu khác nhau.

| Chiều chất lượng | Định nghĩa | Ví dụ kiểm tra |
|---|---|---|
| **Completeness** | Đủ records/trường bắt buộc | Tỷ lệ `order_id IS NOT NULL`, có đủ partitions kỳ báo cáo |
| **Validity** | Giá trị đúng định dạng/range/domain | `amount >= 0` cho dòng bán hàng theo business rule |
| **Uniqueness** | Không trùng ở khóa cần duy nhất | `order_id` duy nhất trong current orders snapshot |
| **Consistency** | Không mâu thuẫn giữa nguồn/bảng/quy tắc | Tổng items khớp order total trong tolerance |
| **Accuracy** | Giá trị phản ánh thực tế/nguồn chuẩn | `paid_amount` khớp payment ledger đã đối soát |
| **Timeliness/Freshness** | Dữ liệu tới đủ nhanh cho mục tiêu | Partition hôm nay cập nhật trong 15 phút |
| **Referential integrity** | Khóa tham chiếu tồn tại đúng phạm vi | Mỗi `order_item.product_id` gắn một product hợp lệ |
| **Integrity/lineage** | Có thể truy vết nguồn và cách biến đổi | `source_file`, `run_id`, `schema_version` |

**Accuracy** thường không thể kiểm tra chỉ bằng biểu thức SQL trên một bảng: cần so sánh nguồn độc lập, reconciliation/đối soát hay sample review với chủ nghiệp vụ.

### 3.1. DQ rule phải có owner và severity

Ví dụ:

| Rule | Mức | Hành vi |
|---|---|---|
| `order_id` null | Blocker đối với silver orders | Quarantine row, không publish gold |
| Amount string không parse được | Blocker với giao dịch tài chính | Quarantine + incident |
| `currency` không được hỗ trợ | Blocker theo contract | Quarantine/đối soát |
| `country_code` thiếu với clickstream | Warning nếu có fallback | Ghi metric, theo dõi |
| Freshness > 30 phút | SLA breach | Alert, không đóng kỳ nếu chưa đủ |
| Phân bố số đơn một region lệch baseline 40% | Anomaly | Cần điều tra, không tự xóa dữ liệu |

Nên có **rule ID, version, owner, logic, threshold, severity, action, affected dataset và recovery procedure**. Một data test không có hành động khi fail chỉ tạo bảng màu đẹp.

### 3.2. Data quality có tính ngữ cảnh

Trong bảng `payments`, amount âm có thể là invalid. Trong bảng `ledger_entries`, số âm lại có thể biểu diễn debit/refund hợp lệ. Không sao chép `amount >= 0` cho mọi bảng mà không có business contract.

### 3.3. Phân biệt lỗi dữ liệu và biến động thị trường

Đột nhiên doanh thu giảm 40% có thể do:

- Mất dữ liệu ingest.
- Thay đổi business logic/filters.
- Chênh lệch timezone.
- Một chương trình khuyến mại kết thúc.
- Một sự kiện kinh tế hoặc vận hành thật.

Anomaly detection cần **ngữ cảnh và khả năng drill-down**, không tự sửa số liệu để khớp “trung bình lịch sử”.

## 4. Data contract và schema evolution

**Data contract** là thỏa thuận giữa producer và consumer về cấu trúc, ngữ nghĩa, kỳ vọng chất lượng và lịch cập nhật dữ liệu.

Ví dụ contract đơn hàng:

```yaml
dataset: orders_events
contractVersion: 2
owner: commerce-platform
businessTimezone: Asia/Ho_Chi_Minh
primaryEventId: event_id
eventTimeColumn: event_time_utc
fields:
  event_id: string_not_null
  order_id: string_not_null
  event_type: enum[OrderCreated,OrderPaid,OrderRefunded]
  amount: decimal_18_2_nullable
  currency: iso_currency_code
  event_time_utc: timestamp_utc
freshnessSlaMinutes: 30
retentionPolicy: follow_dataset_governance
```

Đây là **mẫu hợp đồng khái niệm**, không phải schema chuẩn để một dịch vụ Azure tự hiểu. Trong hệ thống thật, các quy tắc phải được chuyển thành schema/validation có thể thực thi và được versioned trong repository/catal­og phù hợp.

### 4.1. Schema drift và breaking change

| Thay đổi | Ảnh hưởng thường gặp | Hướng xử lý |
|---|---|---|
| Thêm optional field | Có thể backward-compatible | Cập nhật schema, test consumers |
| Đổi `amount` từ decimal thành string | Có thể breaking | Version contract và migration |
| Đổi tên `order_id` không có alias | Breaking với consumers | Deprecation window |
| Thay timezone mà không đổi contract | Sai phân vùng/ngày | Thay contract + backfill có kiểm chứng |
| Thêm event type | Consumer có thể không hiểu | Xử lý unknown type rõ |
| Xóa required field | Breaking | Thỏa thuận rollout producer/consumer |

**Schema evolution của table format không đồng nghĩa business compatibility.** Một engine cho phép thêm cột không bảo đảm Power BI measures, downstream jobs và dữ liệu lịch sử vẫn đúng.

### 4.2. Schema validation trước hoặc sau ingest?

Nếu validate quá sớm và **drop invalid events trước khi ghi raw**, khó audit. Thường nên ghi bronze theo policy, đánh dấu schema parse status, sau đó kiểm tra silver. Tuy nhiên, payload độc hại, quá lớn hoặc chứa secret không nên được ingest vô điều kiện; **ingress security/PII protection** vẫn có trước khi lưu trữ.

### 4.3. Hợp đồng thời gian: UTC và business date

Lưu `event_time_utc` dưới timestamp UTC có timezone semantics rõ. Khi báo cáo theo Việt Nam:

```text
event_time_utc = 2026-11-19 17:30:00Z
business_time  = 2026-11-20 00:30:00 Asia/Ho_Chi_Minh
business_date  = 2026-11-20
```

Không lấy date bằng cách cắt chuỗi timestamp rồi mặc định đó là business day. Cần xử lý timezone và daylight-saving khi áp dụng cho thị trường khác.

## 5. Metadata, lineage và quyền sở hữu

Mỗi dataset quan trọng cần xác định:

- **Owner:** nhóm chịu trách nhiệm tính đúng và dữ liệu nguồn.
- **Steward:** người/quy trình phê duyệt định nghĩa business và classification.
- **Schema/contract version:** theo dõi thay đổi.
- **Lineage:** nguồn → job → bảng → dashboard.
- **Freshness và retention:** nhu cầu SLA và vòng đời.
- **Classification:** PII, confidential, public, financial.
- **Quality scores và incidents:** mức tin cậy, ngày xảy ra, root cause.

Các công cụ như **Microsoft Purview** và metadata/catalog features của từng nền tảng có thể hỗ trợ catalog, lineage, policy theo phạm vi tích hợp cụ thể. Không giả định mọi pipeline tùy biến tự được khám phá lineage đầy đủ chỉ vì đã bật một catalog.

### 5.1. Dữ liệu raw cũng cần kiểm soát truy cập

Bronze có thể chứa PII, records lỗi và dữ liệu nhạy cảm của đối tác. Cần:

1. Phân quyền **Entra ID/RBAC và ADLS Gen2 ACL** theo đường truy cập thực tế.
2. Private networking/TLS và encryption at rest theo policy.
3. Managed identity/service principal quyền tối thiểu cho pipeline.
4. Retention, deletion/subject request và audit access.
5. Không đưa credentials vào notebook/job logs.

Không tự copy raw data sang một workspace analytics mở cho mọi thành viên chỉ vì muốn điều tra data quality.

## 6. Thiết kế quy tắc DQ thành các “quality gates”

Một **quality gate** là bước kiểm tra có quyết định rõ có cho dữ liệu đi tiếp hay không:

```text
Incoming batch
     |
     v
Bronze ingest + source metadata
     |
     v
Schema validation
     |
     +-- Parse fail --> quarantine/error log
     |
     v
Type + domain checks
     |
     +-- Invalid --> quarantine + row-level reason
     |
     v
Uniqueness + reconciliation
     |
     +-- Fail threshold --> halt publish or warn
     |
     v
Silver commit
     |
     v
Gold aggregate + cross-table tests
     |
     v
Publish dashboard / watermark only after PASS
```

### 6.1. Fail-closed hay warn-only?

| Dataset | Gợi ý | Lý do |
|---|---|---|
| Thanh toán/doanh thu chính thức | Fail/hold partition khi lỗi nghiêm trọng | Tránh publish số liệu tài chính sai |
| Clickstream exploratory | Một số invalid events được quarantine nhưng valid data vẫn tiếp tục | Không để vài record hỏng chặn toàn bộ telemetry |
| Customer privacy flags | Fail-closed với dữ liệu/quyền nhạy cảm | Tránh thiếu consent dẫn đến sử dụng dữ liệu trái phép |
| Dashboard realtime “ước tính” | Publish kèm freshness/completeness badge theo business contract | Người dùng biết số liệu chưa final |

Ngưỡng phải dựa trên **mức tác động nghiệp vụ**. Ví dụ “cho phép 1% lỗi” không phù hợp nếu 1% đó chứa toàn bộ đơn có giá trị lớn.

### 6.2. Row-level và batch-level checks

- **Row-level:** null, regex, enum, range, parse timestamp.
- **Batch-level:** số record đủ, unique rate, max timestamp, source completeness.
- **Cross-dataset:** orders tổng khớp payments/refunds theo cửa sổ đối soát.
- **Temporal:** phân bố số đơn, late event rate, dữ liệu đổi bất thường.

Nên lưu **số valid/invalid, denominator, rule version, run_id, ngày dữ liệu và file nguồn**. Một tỷ lệ 99,9% không có sample size rất dễ gây hiểu nhầm.

### 6.3. Quarantine thay vì mất dữ liệu

```text
quarantine/orders_events/
  ingest_date=2026-11-20/
    invalid-records-00001.parquet
```

Record quarantine nên có `reason_code`, `source_identifier`, `ingest_time`, `raw_event_id` và metadata để replay theo policy. Hạn chế lưu toàn bộ PII trong lỗi/traces; quarantine cần security tương đương hoặc chặt hơn bronze.

## 7. Kiểm tra dữ liệu bằng SQL

Giả sử bảng silver có schema:

```text
orders_clean(
  order_id STRING,
  customer_id STRING,
  status STRING,
  amount DECIMAL(18,2),
  currency STRING,
  event_time_utc TIMESTAMP,
  business_date DATE,
  source_version BIGINT
)
```

Các ví dụ SQL ở phần này mang tính **SQL analytics khái niệm**. Tên cột/hàm, table qualifiers và cú pháp `DATE`/`CAST` cần được điều chỉnh theo Spark SQL, Synapse SQL, Azure SQL hoặc warehouse engine thực tế.

### 7.1. Kiểm tra completeness

```sql
SELECT
  COUNT(*) AS total_rows,
  SUM(CASE WHEN order_id IS NULL THEN 1 ELSE 0 END) AS null_order_ids,
  SUM(CASE WHEN customer_id IS NULL THEN 1 ELSE 0 END) AS null_customers
FROM orders_clean
WHERE business_date = DATE '2026-11-20';
```

Nếu `total_rows=0`, không tính completeness 100% bằng cách chia 0 rồi đặt 0 lỗi. Cần **gắn trạng thái NO_DATA**, đối chiếu source expected count/batch arrival và business schedule.

### 7.2. Kiểm tra uniqueness

```sql
SELECT order_id, COUNT(*) AS row_count
FROM orders_clean
WHERE business_date = DATE '2026-11-20'
GROUP BY order_id
HAVING COUNT(*) > 1;
```

**Điều kiện nghiệp vụ cần xác định:** nếu dataset chứa **event history**, một `order_id` xuất hiện nhiều lần do trạng thái thay đổi là hợp lệ; khi đó uniqueness phải là `event_id` hoặc `(order_id, source_version)`. Nếu là **current snapshot**, `order_id` có thể duy nhất toàn bảng, không chỉ trong một ngày.

### 7.3. Kiểm tra domain và range

```sql
SELECT COUNT(*) AS invalid_rows
FROM orders_clean
WHERE status NOT IN ('CREATED', 'PAID', 'REFUNDED', 'CANCELLED')
   OR currency NOT IN ('VND', 'USD', 'EUR')
   OR amount IS NULL
   OR (status = 'PAID' AND amount < 0);
```

Đây chỉ là rule giả định. `REFUNDED` có thể biểu diễn số âm hoặc positive refund amount tùy mô hình sổ cái. Business owners phải phê duyệt trước khi chạy hard gate.

### 7.4. Phát hiện tham chiếu không tồn tại

```sql
SELECT o.order_id, o.customer_id
FROM orders_clean o
LEFT JOIN customers_clean c
  ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
```

Nếu dữ liệu customers tới chậm hơn orders, lỗi referential có thể là **temporary**. Định nghĩa allowed lag, watermark, thời điểm gate và quy trình reconcile chứ không xóa đơn ngay.

### 7.5. Reconciliation tổng và count

```sql
SELECT
  business_date,
  COUNT(*) AS order_count,
  SUM(amount) AS gross_amount
FROM orders_clean
WHERE status = 'PAID'
  AND business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20'
GROUP BY business_date
ORDER BY business_date;
```

Đối chiếu với nguồn tin cậy cùng **định nghĩa metric, FX, tax, refund, timezone, cutoff**. Số row của source CDC feed có thể khác bảng current snapshot; không so hai khái niệm khác nhau rồi coi mismatch là lỗi.

### 7.6. Kiểm tra dữ liệu trễ

Nếu có `event_time_utc` và `ingest_time_utc`:

```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE
      WHEN ingest_time_utc > event_time_utc + INTERVAL 30 MINUTES
      THEN 1 ELSE 0 END) AS late_over_30m
FROM bronze_order_events
WHERE ingest_date = DATE '2026-11-20';
```

Cú pháp `INTERVAL` khác tùy engine. Điều quan trọng là đo **distribution of lateness** và đặt ngưỡng theo nguồn, không coi event đến trễ đương nhiên là dữ liệu sai.

## 8. PySpark: chuẩn hóa, tách invalid và ghi metrics

Ví dụ này có thể chạy trên **Spark runtime** phù hợp (Azure Databricks, Synapse Spark hoặc môi trường Spark khác có quyền đọc/ghi storage). Nó minh họa logic phân tích; phải chỉnh source path, schema, timezone, dependencies và security theo workspace thực tế.

### 8.1. Dữ liệu mẫu

```json
{"event_id":"evt-001","order_id":"ORD-1","amount":"120000.50","currency":"VND","status":"PAID","event_time_utc":"2026-11-20T01:23:00Z"}
{"event_id":"evt-002","order_id":null,"amount":"abc","currency":"VND","status":"PAID","event_time_utc":"2026-11-20T01:24:00Z"}
{"event_id":"evt-003","order_id":"ORD-2","amount":"90000","currency":"USD","status":"CREATED","event_time_utc":"2026-11-20T01:25:00Z"}
```

Record thứ hai có hai lỗi. Pipeline không được biến `abc` thành amount 0 rồi lặng lẽ tính vào doanh thu.

### 8.2. PySpark transform

```python
from pyspark.sql import functions as F, types as T

# Spark session đã được khởi tạo trong môi trường được cấp quyền.
spark.conf.set("spark.sql.session.timeZone", "UTC")

input_path = "abfss://bronze@STORAGE_ACCOUNT.dfs.core.windows.net/orders/events/"

schema = T.StructType([
    T.StructField("event_id", T.StringType(), True),
    T.StructField("order_id", T.StringType(), True),
    T.StructField("amount", T.StringType(), True),
    T.StructField("currency", T.StringType(), True),
    T.StructField("status", T.StringType(), True),
    T.StructField("event_time_utc", T.StringType(), True),
])

raw = spark.read.schema(schema).json(input_path)

typed = (
    raw
    .withColumn("amount_decimal", F.expr("try_cast(amount as decimal(18,2))"))
    .withColumn("event_ts", F.to_timestamp("event_time_utc"))
    .withColumn("business_date",
                F.to_date(F.from_utc_timestamp("event_ts", "Asia/Ho_Chi_Minh")))
    .withColumn(
        "reason_code",
        F.when(F.col("event_id").isNull(), F.lit("MISSING_EVENT_ID"))
         .when(F.col("order_id").isNull(), F.lit("MISSING_ORDER_ID"))
         .when(F.col("amount_decimal").isNull(), F.lit("INVALID_AMOUNT"))
         .when(F.col("event_ts").isNull(), F.lit("INVALID_TIMESTAMP"))
         .when(~F.col("currency").isin("VND", "USD", "EUR"),
               F.lit("UNKNOWN_CURRENCY"))
         .when(~F.col("status").isin("CREATED", "PAID",
                                    "REFUNDED", "CANCELLED"),
               F.lit("UNKNOWN_STATUS"))
    )
)

valid = (
    typed.filter(F.col("reason_code").isNull())
    .select("event_id", "order_id",
            F.col("amount_decimal").alias("amount"),
            "currency", "status",
            F.col("event_ts").alias("event_time_utc"),
            "business_date")
)
invalid = typed.filter(F.col("reason_code").isNotNull())

print("valid_rows =", valid.count())
print("invalid_rows =", invalid.count())
```

**Lưu ý về tính di động:** `try_cast` và parsing ISO-8601 timestamps cần phiên bản Spark SQL tương thích; một số runtime sử dụng hàm/behavior khác trong ANSI mode. Kiểm tra thật với source values, malformed strings và timezone, không giả định chạy trên mọi runtime chỉ vì cùng tên PySpark.

`reason_code` ở ví dụ lưu **lý do đầu tiên** theo thứ tự quy tắc. Một hệ thống DQ đầy đủ có thể lưu danh sách tất cả rule failures và phân biệt record-level quarantine với failed batch gate.

### 8.3. Ghi silver và quarantine

```python
silver_path = "abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean"
quarantine_path = (
    "abfss://quarantine@STORAGE_ACCOUNT.dfs.core.windows.net/orders_events"
)

# Chỉ minh họa append đối với dữ liệu events đã được dedup.
# Production cần idempotent merge/checkpoint theo event_id/source_version.
valid.write.format("parquet").mode("append").partitionBy(
    "business_date"
).save(silver_path)

invalid.write.format("parquet").mode("append").save(quarantine_path)
```

**Đừng chạy đoạn append này nhiều lần trên cùng batch nếu chưa có idempotency**: nó sẽ tạo bản sao records. Trong production, thiết kế source offset/checkpoint hoặc `MERGE` trên transactional table format phù hợp, transaction logs và batch dedup.

### 8.4. Publish gate theo tỷ lệ invalid

```python
total_rows = typed.count()
invalid_rows = invalid.count()

if total_rows == 0:
    raise RuntimeError("NO_DATA: expected batch has zero rows")

invalid_ratio = invalid_rows / total_rows
threshold = 0.005  # 0,5% chỉ là threshold minh họa

if invalid_ratio > threshold:
    raise RuntimeError(
        f"DATA_QUALITY_GATE_FAILED invalid_ratio={invalid_ratio:.4f}"
    )
```

**Thứ tự thực thi production phải được thiết kế:** ví dụ đã ghi output trước khi gate, nên **không được dùng nguyên xi để điều khiển publish**. Cần tính quality metrics và quyết định **trước khi commit/publish silver/gold**, hoặc ghi dữ liệu vào staging rồi chỉ **atomic promote/swap/merge** khi gate PASS. Nếu gate fail sau partial write, phải có checkpoint/rollback/replay để không lộ dữ liệu chưa đạt chất lượng.

### 8.5. Tối ưu chi phí chính thao tác DQ

Đoạn minh họa gọi `count()` nhiều lần, có thể kích hoạt nhiều Spark jobs/scans. Production nên:

- Tính nhiều rule metrics trong **một aggregation** khi có thể.
- Cache/persist DataFrame tạm **chỉ khi lợi hơn** và nhớ unpersist.
- Kiểm tra Spark execution plan và input scan size.
- Tách lightweight schema checks khỏi heavyweight reconciliation khi có thể.
- Chỉ publish sau gate, không chạy lại full lake scan cho cùng batch vô hạn.

Data quality không nên trở thành nguồn chi phí không kiểm soát.

## 9. Event time, processing time và late-arriving data

**Event time** là thời điểm hành vi xảy ra; **ingestion/processing time** là lúc pipeline nhìn thấy dữ liệu. Hai thời điểm có thể khác vì offline mobile app, queue backlog, retry, API batch import hoặc lỗi kết nối.

```text
Event A xảy ra:       2026-11-19 23:58 +07
Event A được ingest:  2026-11-20 00:10 +07

event_business_date   = 2026-11-19
ingestion_date        = 2026-11-20
```

Nếu phân vùng theo `ingestion_date` nhưng báo cáo theo `business_date`, những late events của ngày cũ có thể nằm trong file ngày mới. Cần hiểu rõ **partition key dùng để prune theo điều kiện gì** và chiến lược backfill/correct period.

### 9.1. Watermark trong stream processing

Một stream processor có thể dùng **watermark** để giới hạn trạng thái cần giữ cho các phép toán event-time và xử lý late events theo policy. Ví dụ:

```python
from pyspark.sql import functions as F

events = (
    input_stream
    .withWatermark("event_time_utc", "30 minutes")
)
```

Đây là **fragment** giả định `input_stream` là streaming DataFrame có cột timestamp hợp lệ. Watermark không tự động bảo đảm mọi event trễ trên 30 phút bị xóa ở mọi phép toán; hành vi phụ thuộc **operator/stateful aggregation/dedup** và microbatch progression. Cần đọc semantics runtime và test với event trễ/ngoài thứ tự.

### 9.2. Không vội đóng ngày

Một báo cáo doanh thu theo ngày có thể chọn:

- **Preliminary:** số liệu tạm trước khi nhận hết late events.
- **Finalized:** đóng kỳ theo watermark/cutoff được business phê duyệt.
- **Restated:** cập nhật kỳ đã chốt sau refund/adjustment theo phiên bản báo cáo.

Dashboard nên hiển thị **data-as-of/cutoff và trạng thái số liệu**, thay vì âm thầm thay lịch sử khiến người dùng không hiểu chênh lệch.

### 9.3. Đồng bộ giữa phân vùng và điều chỉnh muộn

Nếu partition theo `business_date`, một refund đến tháng sau cho đơn tháng trước có thể:

- Được ghi là sự kiện refund **ngày hiện tại** trong ledger.
- Hoặc khiến bảng order snapshot của ngày cũ thay đổi.

Đây là **quyết định semantic model**, không tự chọn một cách cho mọi báo cáo. Quy tắc partition, gold metric và backfill cần nhất quán với định nghĩa tài chính.

## 10. CDC, incremental loads và deduplication

**Change Data Capture (CDC)** ghi các thay đổi insert/update/delete từ nguồn như database (theo tính năng hỗ trợ). Một pipeline CDC thường có:

```text
source_database
   |
   | change log/CDC connector
   v
Bronze change events (op, PK, sequence, timestamp)
   |
   v
Dedup/order + schema validation
   |
   v
Silver current snapshot (upsert/delete)
   |
   v
Gold aggregates / change propagation
```

### 10.1. Event ID và source sequence

Một CDC change có thể có:

```json
{
  "source_table": "orders",
  "pk": "ORD-1042",
  "operation": "UPDATE",
  "source_sequence": 881243,
  "source_commit_time": "2026-11-20T10:15:00Z",
  "status": "PAID"
}
```

`source_sequence` chỉ có ý nghĩa nếu connector cung cấp một thứ tự đáng tin cậy trong **phạm vi thích hợp** (database/table/partition/log stream). Không giả định mọi nguồn cấp một sequence toàn cục. Khi cập nhật snapshot, dùng version/sequence so sánh đúng để event cũ đến trễ **không ghi đè trạng thái mới hơn**.

### 10.2. Duplicate delivery là bình thường

Một ingestion job có thể retry sau timeout và gửi lại event đã ghi vào bronze. Vì thế:

- Bronze có thể có duplicates cùng `event_id` để phục vụ audit/replay.
- Silver cần dedup theo event ID hoặc khóa + version thích hợp.
- Gold cần incremental aggregation **idempotent**, không cộng doanh thu lần hai.
- Checkpoint chỉ được tiến khi batch write thực sự đã commit an toàn.

Không chỉ dùng `dropDuplicates(["order_id"])` cho bảng history vì sẽ mất các trạng thái hợp lệ của cùng đơn.

### 10.3. Delete/tombstone phải được xử lý

CDC có thể có `DELETE`/tombstones. Nếu pipeline chỉ upsert INSERT/UPDATE, bảng gold có thể giữ record đã xóa hoặc không đáp ứng yêu cầu privacy deletion. Định nghĩa riêng:

- Hard vs soft delete semantics.
- Retention/time travel/vacuum policy.
- Cách propagate deletion tới downstream, caches, search indexes và BI.
- Quyền/trách nhiệm xử lý data subject request.

**Xóa một row ở gold không chứng minh bản sao raw/backup/time travel đã được xử lý đúng**; cần policy toàn vòng đời dữ liệu.

## 11. Idempotent batch processing

Giả sử ADF/Spark chạy lại batch `2026-11-20` vì job trước timeout sau khi ghi file nhưng trước khi pipeline nhận success. Nếu write là append không có dedup, tổng order count có thể tăng đôi.

### 11.1. Mô hình batch ID

```text
source: orders-events
batch_id: 2026-11-20T10:00Z-batch-0042
file_manifest: [file-a, file-b, file-c]
checkpoint: source offset/version
target: silver.orders_clean
status: PENDING -> VALIDATED -> COMMITTED
```

Lưu trạng thái batch/control table một cách **bền vững** và có unique key, để một batch được replay đúng cách mà không nhân đôi kết quả.

### 11.2. Transactional table format

Table formats như **Delta Lake** (khi engine hỗ trợ) có transaction log và `MERGE`/overwrite semantics giúp tổ chức atomic commits và upserts. Nhưng **nó không tự biết logical event identity** hoặc tự loại mọi duplicates. Vẫn phải định nghĩa primary/business key, dedup rule, concurrent write isolation và checkpoint.

### 11.3. Chạy backfill không phá dữ liệu mới

Backfill 6 tháng dữ liệu cần:

1. Chọn phạm vi partitions và phiên bản transformation.
2. Xác định dữ liệu đang được cập nhật realtime thế nào.
3. Tránh overwrite mất events đến trong lúc backfill.
4. Dùng staging, validation và atomic swap/merge phù hợp.
5. Recompute dependent gold metrics hoặc materialized results cần thiết.
6. Đo cost riêng của backfill, không che vào bảng chi phí daily job.
7. Lưu audit run ID, số rows trước/sau và rollback plan.

Không dùng `overwrite` toàn bảng production chỉ để sửa một partition cũ.

## 12. Phân vùng dữ liệu là gì và để làm gì?

Trong data lake, **partitioning** thường nghĩa là chia dữ liệu logic theo giá trị một hoặc vài cột, tổ chức các file theo các thư mục hoặc metadata table partition để engine có thể **bỏ qua những phần không liên quan khi đọc**.

Ví dụ bảng `orders_clean`:

```text
abfss://silver@storage.dfs.core.windows.net/orders/
  business_date=2026-11-18/
    part-0000.snappy.parquet
    part-0001.snappy.parquet
  business_date=2026-11-19/
    part-0000.snappy.parquet
  business_date=2026-11-20/
    part-0000.snappy.parquet
    part-0001.snappy.parquet
```

Với truy vấn lọc ngày `2026-11-20`, engine hỗ trợ **partition pruning** có thể chỉ scan các file thuộc partition tương ứng, thay vì đọc tất cả các ngày. Cần có metadata/path/layout phù hợp và predicate đủ rõ để optimizer áp dụng.

### 12.1. Ba cơ chế tối ưu thường bị nhầm

| Cơ chế | Lọc ở mức nào? | Ví dụ |
|---|---|---|
| **Partition pruning** | Bỏ qua partitions không thỏa filter | Chỉ chọn `business_date=2026-11-20` |
| **File/data skipping** | Bỏ qua file nhờ statistics/min-max/bloom hoặc index tùy engine | Trong một ngày, file chỉ có `customer_id` ngoài phạm vi |
| **Predicate pushdown/column pruning** | Đẩy filter/đọc cột cần thiết xuống reader/storage format | Parquet chỉ đọc `order_id` và `amount`; lọc sớm theo `status` |

Ba tính năng có thể phối hợp, nhưng **không đồng nghĩa**. Một dataset có partition theo ngày vẫn phải đọc nhiều files trong ngày nếu không có clustering/statistics hợp lý. Một `SELECT *` có thể khiến engine đọc nhiều cột không cần thiết dù pruning ngày hoạt động.

### 12.2. Logical vs physical partition

Không phải mọi hệ thống dùng thuật ngữ partition giống nhau:

- **Spark/Delta/Parquet trên ADLS:** table partition/folder layout và partitions phân tán khi thực thi Spark.
- **Azure SQL Database:** table partitioning của SQL Server engine có metadata/index/storage semantics riêng.
- **Synapse dedicated SQL pool:** distribution/partitioning và columnstore khác file partition ở lake.
- **Microsoft Fabric Warehouse/Lakehouse:** engine/table format và khả năng tối ưu theo SKU/workload.

Đừng nhầm `df.repartition(20)` của Spark (thay số partitions trong execution plan) với `write.partitionBy("business_date")` (tạo partition layout theo cột), dù cả hai ảnh hưởng số output files.

## 13. Chọn partition key theo mẫu truy vấn

**Partition key tốt** thường xuất hiện trong filters truy vấn, có cardinality hợp lý, phân phối dữ liệu tương đối ổn và không tạo quá nhiều partitions nhỏ.

Giả sử một bảng events có 2 TB dữ liệu trong 24 tháng. Nhóm phân tích thường hỏi:

```sql
SELECT country, SUM(revenue)
FROM orders_clean
WHERE business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20'
GROUP BY country;
```

Partition theo `business_date` có thể giúp chỉ quét 20 ngày; partition theo `order_id` sẽ tạo lượng partitions khổng lồ, khó quản lý và không giúp filter theo thời gian.

### 13.1. So sánh những key thường gặp

| Partition key | Lợi ích | Nguy cơ |
|---|---|---|
| `business_date` (ngày) | Hợp báo cáo theo ngày/tháng, backfill theo kỳ | Một số ngày có peak skew |
| `ingestion_date` | Dễ quản lý ingestion/backfill/retention | Báo cáo theo event date phải xử lý late data |
| `event_hour` | Phù hợp streaming khối lượng lớn và truy vấn trong giờ | Quá nhiều partitions nếu dữ liệu ít |
| `country` | Hữu ích nếu filter region, cardinality vừa | Một số quốc gia chiếm đa số data |
| `tenant_id` | Có thể prune workload tenant isolation | Số tenant lớn tạo tiny partitions/skew |
| `order_id` | Filter point lookup rõ nhưng rất nhiều distinct | Thường **không** làm lake partition key |
| `year/month/day` | Có thể giảm scan theo thời gian | Hierarchy phức tạp và viết lệch ngày/timezone |

Một câu hỏi quyết định: **bao nhiêu phần trăm queries thực sự lọc cột này?** Nếu BI hầu như luôn truy vấn ngày và country, có thể partition theo ngày rồi dùng clustering/data skipping cho country thay vì tạo `date × country × tenant` folders vô hạn.

### 13.2. Cardinality quá cao

Giả sử 200.000 tenants, mỗi tenant tạo 20 KB dữ liệu/ngày. Partition theo `tenant_id` và `business_date` có thể tạo **hàng trăm nghìn tiny partitions/files mỗi ngày**, tốn metadata/list operations và làm query planning chậm hơn lợi ích pruning.

Với workloads nhiều tenant, cân nhắc:

- Partition theo ngày/giờ phù hợp lượng dữ liệu.
- Cluster/order theo `tenant_id` hoặc sử dụng statistics/data skipping nếu engine hỗ trợ.
- Tách dữ liệu theo tenant chỉ khi có lý do **isolation/retention/compliance** và sizing thực tế.
- Thử query workload với **tenant skew**, không chỉ benchmark tenant nhỏ.

### 13.3. Cardinality quá thấp

Partition theo `status` chỉ có bốn giá trị có thể không đủ prune cho truy vấn theo thời gian; một partition PAID vẫn chứa hàng năm dữ liệu. Chọn partition key không chỉ theo độ ít giá trị mà phải bám mẫu filter thực tế và dataset growth.

### 13.4. Skew

Nếu country `VN` chiếm 90% đơn, partition country có một thư mục rất lớn và các thư mục còn lại nhỏ. Query workers có thể bị lệch: một task chậm trong khi những tasks khác rảnh.

Giải pháp có thể là partition theo ngày, thêm bucketing/clustering theo engine, adaptive query execution/salting cho joins khi thích hợp, hoặc thay bố cục dữ liệu. **Tăng số Spark executors không tự loại bỏ skew** nếu một partition data task vẫn quá lớn.

## 14. Chọn độ hạt ngày, giờ hay tháng

Không có quy tắc “partition nhỏ hơn luôn nhanh hơn”.

### 14.1. Ước lượng số partitions

Với dữ liệu hai năm:

```text
Partition theo tháng: khoảng 24
Partition theo ngày: khoảng 730
Partition theo giờ: khoảng 17.520
Partition theo phút: khoảng 1.051.200
```

Nếu một giờ chỉ có 2 MB, partition hourly gây rất nhiều tiny folders/files. Nếu mỗi ngày có 5 TB và dashboard chỉ xem 1 giờ gần nhất, partition daily có thể vẫn đọc rất nhiều dữ liệu nếu không có data skipping/clustering hỗ trợ.

### 14.2. Decision matrix

| Tốc độ/đơn vị dữ liệu | Truy vấn chính | Partition thử nghiệm |
|---|---|---|
| 5 GB/ngày | Báo cáo theo ngày/tháng | Ngày |
| 2 TB/ngày | Xem theo giờ/phân tích realtime | Ngày hoặc giờ, benchmark |
| 500 MB/tháng | Báo cáo tháng | Tháng hoặc không partition nếu table nhỏ |
| 100 GB/ngày, 200k tenants | Lọc tenant + ngày | Ngày + clustering tenant thay vì tenant folder |
| 20 GB/ngày, retention 30 ngày | Xóa theo ngày | Ngày giúp lifecycle/backfill |

Đây là gợi ý **thiết kế ban đầu**, không phải quy định engine. Kiểm tra **bytes per partition, files per partition, cost per query, query frequency và metadata overhead** để chốt.

### 14.3. Lấy business date hay UTC date?

Nếu người dùng báo cáo theo Asia/Ho_Chi_Minh, partition theo `business_date` có thể tiện cho filter. Tuy vậy, ingestion/streaming có thể dùng UTC để tránh mơ hồ timezone. Có thể lưu **cả `event_time_utc` và `business_date`**, chọn physical partition theo workload rồi dùng mapping rõ.

Không bao giờ tạo partition date từ **clock của worker** cho dữ liệu event-time mà không định nghĩa rõ: job chạy lại ngày hôm sau có thể đặt toàn bộ events ngày cũ vào thư mục ngày chạy job.

## 15. Thiết kế đường dẫn ADLS Gen2

Một layout khả thi:

```text
lake/
  bronze/
    source=orders-api/
      ingest_date=2026-11-20/
        batch-00042/
          event-part-0001.json
  silver/
    orders_clean/
      business_date=2026-11-20/
        part-00000.parquet
  gold/
    daily_revenue/
      business_month=2026-11/
        part-00000.parquet
  quarantine/
    orders_events/
      ingest_date=2026-11-20/
        invalid-part-0001.parquet
```

Trong Delta Lake, đường dẫn table root và `_delta_log` là thành phần do transaction log quản lý; không di chuyển/xóa data files thủ công chỉ vì thấy chúng dưới thư mục partition. Với Hive-style Parquet không có transaction log, quản lý atomic publish, reader consistency và metadata discovery khác nhau theo engine.

### 15.1. Chọn tên đường dẫn ổn định

Nên có:

- Environment/zone/dataset rõ để tránh ghi nhầm dev/prod.
- Partition keys theo kiểu và format thống nhất như `business_date=YYYY-MM-DD`.
- Run/batch provenance ở metadata riêng khi phù hợp.
- Không chứa email, access tokens, secret hoặc raw personal identifiers trong path.
- Storage account/container naming phù hợp quy tắc Azure.

### 15.2. Access control theo lớp

Bronze chứa raw PII có thể cần nhóm quyền chặt hơn gold aggregates. ADLS Gen2 hỗ trợ các cơ chế RBAC/ACL phù hợp theo namespace và đường truy cập. Không cấp `Storage Blob Data Owner` ở cả storage account cho một dashboard chỉ cần đọc gold aggregate; dùng managed identity và phân quyền tối thiểu.

### 15.3. Storage lifecycle và xóa theo kỳ

Partition theo ngày có thể giúp xác định dữ liệu cần expire; nhưng lifecycle policy ở Blob Storage phụ thuộc **prefix/filter/tier** và semantics của object storage. Không suy rằng tạo folder `business_date` tự động thực hiện retention và xóa transaction-log data an toàn. Với Delta tables, quy trình `VACUUM`/retention phải tương thích time travel, concurrent jobs, streaming và compliance; xóa physical files thủ công là nguy hiểm.

## 16. Parquet, CSV, JSON và table formats

### 16.1. Columnar vs row-oriented

| Định dạng | Đặc điểm | Phù hợp |
|---|---|---|
| **CSV** | Dễ trao đổi nhưng yếu về types/schema, dễ sai escaping | Ingest/trao đổi nếu contract rõ |
| **JSON/JSON Lines** | Linh hoạt, lưu nested events và schema evolution | Raw/bronze, streaming events |
| **Parquet** | Columnar, nén, statistics, đọc cột chọn lọc | Silver/gold analytics trên lake |
| **Delta Lake** | Table format dùng Parquet + transaction log và features theo engine | Incremental/upserts, schema enforcement/evolution, table management |
| **Các table format khác** | Iceberg/Hudi có metadata/transaction design riêng | Khi nền tảng/engine hỗ trợ và use case phù hợp |

Không nói `Parquet` tự cung cấp transaction isolation hay `MERGE` ACID: đó là khả năng **table format/engine**, không phải file Parquet riêng.

### 16.2. Column pruning

Nếu một Parquet table có 100 cột nhưng query chỉ cần `order_id` và `amount`:

```sql
SELECT order_id, amount
FROM orders_clean
WHERE business_date = DATE '2026-11-20';
```

Một Parquet reader tốt có thể đọc ít cột hơn `SELECT *`. Lợi ích thực phụ thuộc serialization, compression, statistics, engine và cấu trúc dữ liệu; với nested fields, pushdown có giới hạn riêng.

### 16.3. Nén dữ liệu

Những compression codec thường gặp là Snappy, ZSTD và các lựa chọn khác tùy engine. **Snappy** thường cân bằng tốc độ đọc/ghi; **ZSTD** có thể đạt compression ratio cao hơn nhưng tốn CPU khác nhau theo level/dataset. Cần đo **cost/GB stored + bytes scanned + compute CPU + latency** thay vì chỉ chọn file nhỏ nhất.

### 16.4. Schema enforcement và type safety

Parquet lưu schema có kiểu, nhưng data pipeline vẫn cần kiểm tra **logical/business rules**. Một cột `amount DECIMAL` hợp lệ về kiểu vẫn có thể chứa số tiền gấp 1000 lần do lỗi unit hoặc FX. DQ rules bổ sung cho schema, không thay thế nhau.

## 17. Small files: kẻ thù của phân tích trên data lake

Một table 1 TB chia thành 2 triệu files cỡ 0,5 MB có thể chậm hơn nhiều so với ít files lớn phù hợp vì:

- Metadata/file listing và task scheduling overhead lớn.
- Mỗi file mở một số I/O operations/request.
- Data skipping/statistics có thể kém hiệu quả khi layout không phù hợp.
- Transaction log/table metadata có thể phình theo nhiều file actions.
- Billing storage transactions và job orchestration tăng.

**Ngược lại, một file khổng lồ** có thể làm giảm parallelism hoặc gây memory/latency ở một số workloads. Tối ưu là **kích thước file thực tế phù hợp với engine và query**.

### 17.1. File size benchmark

Một điểm bắt đầu được dùng trong nhiều Spark analytics workloads là target file cỡ **hàng trăm MiB**, chẳng hạn 128–512 MiB, nhưng không phải ngưỡng cứng. Với streaming low latency, files nhỏ hơn có thể là trade-off chấp nhận được; với large batch scan, files lớn hơn có thể tốt hơn.

### 17.2. Compaction

**Compaction** gộp nhiều files nhỏ thành ít files lớn hơn theo partition/format semantics. Với Delta Lake và runtime hỗ trợ, có thể có lệnh `OPTIMIZE`; với Parquet thuần, có thể rewrite dataset/partition bằng Spark.

Ví dụ minh họa trên một Delta table trong environment có lệnh hỗ trợ:

```sql
OPTIMIZE silver.orders_clean
WHERE business_date >= DATE '2026-11-01';
```

**Không coi lệnh `OPTIMIZE` là SQL chuẩn dùng trong mọi Synapse/Fabric/Databricks runtime**. Trước khi chạy cần xác minh engine, table format, quyền, maintenance window và chi phí rewrite.

### 17.3. Bẫy compaction

- Compaction tiêu compute và ghi thêm data files; tối ưu quá thường xuyên có thể **tốn hơn phần tiết kiệm query**.
- Stream writers/concurrent readers cần table-format transaction semantics phù hợp.
- Không chạy compaction toàn bộ data lịch sử mỗi giờ nếu chỉ partition hôm nay biến động.
- Cần cân nhắc retention/time travel/VACUUM sau compaction.
- Data quality gates cần vẫn có hiệu lực; compaction **không sửa records sai**.

### 17.4. Vì sao partitioning làm file nhỏ hơn?

Giả sử batch mỗi 5 phút có 20 MB và dùng `partitionBy("business_date","country","tenant_id")`. Nếu một batch trải ra 500 tenants, sẽ có rất nhiều partition groups cực nhỏ. Thay vì tăng số columns partition vô hạn, hãy điều chỉnh writer, microbatch size, clustering, compaction và độ hạt.

## 18. PySpark partitionBy, repartition và coalesce

### 18.1. Ghi Parquet theo business date

```python
clean_orders = (
    source_orders
    .withColumn("business_date",
                F.to_date(F.from_utc_timestamp(
                    "event_time_utc", "Asia/Ho_Chi_Minh")))
)

(
    clean_orders.write
    .mode("append")
    .format("parquet")
    .partitionBy("business_date")
    .save("abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean")
)
```

Đây là fragment giả định `source_orders` và `F` đã có; phù hợp để minh họa **physical layout**, không đảm bảo idempotency hoặc atomic table transaction. Không chạy lại cùng batch bằng append mà không checkpoint/dedup.

### 18.2. `repartition` khác `partitionBy`

```python
balanced = clean_orders.repartition(32, "business_date")

(
    balanced.write
    .mode("append")
    .partitionBy("business_date")
    .parquet("abfss://silver@STORAGE_ACCOUNT.dfs.core.windows.net/orders_clean")
)
```

`repartition(32, "business_date")` đưa các rows có cùng hash partition key vào Spark execution partitions theo cách shuffle được engine áp dụng; **không** bảo đảm luôn tạo chính xác 32 files hoặc một file cho mỗi ngày. Số files còn phụ thuộc writers, tasks, `maxRecordsPerFile` và layout thực tế.

### 18.3. `coalesce` khi nào?

`df.coalesce(n)` thường giảm số execution partitions mà không full shuffle trong trường hợp phù hợp. Nó có thể có ích sau khi filter nhỏ dataset, nhưng nếu ép `coalesce(1)` để tạo một file duy nhất trên dữ liệu lớn, một task có thể thành bottleneck và làm tăng latency/worker memory.

### 18.4. Đếm files trước/sau tối ưu

Những metrics nên ghi cho từng batch/partition:

```text
dataset_id
business_date / partition
row_count
bytes_written
file_count
average_file_size
p50/p95 file_size
max_file_size
write_duration / compute cost
downstream scan cost / latency
```

Không tối ưu chỉ để giảm `file_count` mà bỏ qua write cost và latency đọc.

## 19. Delta Lake: transaction log, MERGE và phân vùng

**Delta Lake** là table format có transaction log và sử dụng Parquet cho data files; khi được engine hỗ trợ, nó giúp tổ chức schema enforcement, ACID transactions trên table, upserts/deletes và time travel theo cấu hình.

```text
silver/orders_clean/
  _delta_log/
    00000000000000000000.json
    00000000000000000001.json
    ...
  business_date=2026-11-19/
    part-....snappy.parquet
  business_date=2026-11-20/
    part-....snappy.parquet
```

Không nên **đọc trực tiếp tất cả data files** trong thư mục Delta bằng một Parquet reader rồi tin dữ liệu là table snapshot hợp lệ: một số file có thể đã bị loại khỏi snapshot bởi transaction log nhưng còn tồn tại vật lý phục vụ time travel/retention.

### 19.1. Tạo Delta table phân vùng

Trong engine SQL tương thích Delta:

```sql
CREATE TABLE IF NOT EXISTS silver.orders_clean (
  order_id STRING,
  customer_id STRING,
  amount DECIMAL(18,2),
  status STRING,
  event_time_utc TIMESTAMP,
  business_date DATE,
  source_version BIGINT
)
USING DELTA
PARTITIONED BY (business_date);
```

Đây là cú pháp **Delta/Spark SQL**, không phải cú pháp Azure SQL Database hoặc mọi warehouse SQL. Khi tạo managed/external table, định nghĩa location/catalog/credential theo governance của workspace.

### 19.2. Upsert bản mới nhất

Ví dụ:

```sql
MERGE INTO silver.orders_clean AS target
USING staging.orders_latest AS source
ON target.order_id = source.order_id
WHEN MATCHED
  AND source.source_version > target.source_version
THEN UPDATE SET
  target.customer_id = source.customer_id,
  target.amount = source.amount,
  target.status = source.status,
  target.event_time_utc = source.event_time_utc,
  target.business_date = source.business_date,
  target.source_version = source.source_version
WHEN NOT MATCHED THEN INSERT (
  order_id, customer_id, amount, status,
  event_time_utc, business_date, source_version
) VALUES (
  source.order_id, source.customer_id, source.amount, source.status,
  source.event_time_utc, source.business_date, source.source_version
);
```

**Điều kiện tiền đề:** `staging.orders_latest` phải có **tối đa một record cho mỗi order_id** trong batch và version ordering đáng tin cậy. Nếu source có nhiều records trùng match, `MERGE` có thể thất bại hoặc có behavior không mong muốn tùy runtime. Cần dedup trước khi merge và xử lý tombstones/deletes riêng.

### 19.3. Chú ý partition key thay đổi

Nếu `business_date` của một order được sửa vì timezone bug, `MERGE` có thể cần đọc/ghi files trên **partition cũ và mới**. Nếu bảng partition theo event date nhưng update thường xuyên thay đổi ngày, chi phí rewrite có thể tăng. Cần cân nhắc liệu current snapshot có nên partition theo date hay nên cluster theo keys thay thế.

### 19.4. Table transaction không giải quyết mọi giao dịch đa hệ thống

Một Delta commit không tự nguyên tử với:

- Azure SQL commit ở nguồn.
- Gửi Service Bus message.
- Cập nhật external search index.
- Cập nhật Power BI semantic model.

Cần orchestration, idempotent checkpoints và reconciliation giữa systems. **ACID của table format chỉ bao phủ phạm vi transactions mà engine/table thực sự hỗ trợ.**

## 20. Clustering, Z-ORDER, liquid clustering và data skipping

**Partitioning** mạnh khi query lọc partition key. Nếu trong mỗi ngày có 500 triệu rows và phần lớn queries lọc `customer_id`, có thể cần bổ sung **data clustering** để nhóm records tương tự gần nhau, cho phép optimizer bỏ qua files hiệu quả hơn.

### 20.1. Clustering khác partitioning

- **Partitioning:** chia table thành các partitions rõ ràng ở metadata/path.
- **Clustering/order:** sắp xếp/đặt dữ liệu gần nhau theo cột để hỗ trợ file skipping, thường không tạo một folder cho mỗi distinct key.
- **Statistics:** min/max/null count/cardinality hoặc dữ liệu phụ thuộc engine giúp optimizer loại files/segments.

### 20.2. Z-ORDER

Một số môi trường **Azure Databricks/Delta** hỗ trợ tối ưu bằng `ZORDER BY` theo API/runtime tương ứng. Ví dụ minh họa:

```sql
OPTIMIZE silver.orders_clean
WHERE business_date >= DATE '2026-11-01'
ZORDER BY (customer_id);
```

Đây là tối ưu **engine-specific**, có chi phí rewrite/compute. Nếu phần lớn queries không lọc `customer_id`, hiệu quả có thể nhỏ. Một dataset thường xuyên update có thể mất bớt lợi ích layout sau các writes tiếp theo.

### 20.3. Liquid clustering và các tính năng mới

Một số Databricks/Delta runtime hỗ trợ **liquid clustering** với cơ chế quản lý layout khác Z-ORDER và traditional partitioning. Các tính năng/điều kiện tương thích thay đổi theo runtime/table properties; **không phối hợp Z-ORDER và liquid clustering trên cùng table bằng giả định tùy ý**. Cần chọn một layout strategy được runtime hỗ trợ, kiểm tra write/read workloads, chi phí maintenance và kết quả benchmark.

### 20.4. Một query filter vẫn scan rất nhiều

```sql
SELECT COUNT(*)
FROM silver.orders_clean
WHERE customer_id = 'C-1042'
  AND business_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-20';
```

Với partition theo ngày, ngày được prune; clustering/data skipping theo customer có thể giúp bỏ qua nhiều files trong các ngày đó. Nhưng nếu customer xuất hiện ở nhiều files do data layout lộn xộn, statistics quá rộng, query vẫn phải đọc nhiều bytes.

### 20.5. Không gắn hai mươi cột clustering

Clustering nhiều cột không tự tốt hơn: chi phí sắp xếp tăng và locality cho từng cột có thể giảm. Chọn một số cột **thường được filter** và có data selectivity tốt, dựa trên query logs. Re-evaluate khi workload thay đổi.

## 21. Partition pruning và cách viết SQL thân thiện optimizer

### 21.1. Filter trực tiếp partition column

Ví dụ tốt:

```sql
SELECT SUM(amount)
FROM silver.orders_clean
WHERE business_date >= DATE '2026-11-01'
  AND business_date <  DATE '2026-12-01';
```

Nếu table partition theo `business_date` và engine có metadata cần thiết, optimizer có thể loại các partitions ngoài tháng 11.

### 21.2. Tránh biến đổi partition column không cần thiết

Một số biểu thức kiểu:

```sql
-- Không nên mặc định optimizer mọi engine đều prune tốt:
WHERE YEAR(business_date) = 2026
  AND MONTH(business_date) = 11
```

có thể cản khả năng nhận predicate partition trực tiếp. **Không phải mọi hàm trên partition column đều chắc chắn phá pruning**: có engine hỗ trợ expression rewrite/constant folding. Quy tắc thực tế là **xem EXPLAIN/query plan/bytes scanned**, ưu tiên range filter đơn giản nếu đáp ứng semantics.

### 21.3. Timezone conversion ngay trong WHERE

Ví dụ cần thận trọng:

```sql
WHERE TO_DATE(FROM_UTC_TIMESTAMP(event_time_utc, 'Asia/Ho_Chi_Minh'))
      = DATE '2026-11-20'
```

Nếu table partition theo `business_date`, filter trên computed timestamp có thể không được prune vào đúng partition. Thay vào đó, cân nhắc lưu `business_date` đã chuẩn hóa và:

```sql
WHERE business_date = DATE '2026-11-20'
```

Nhưng phải đảm bảo cột được tạo đúng business timezone và dữ liệu đã backfill khi rule đổi.

### 21.4. Dynamic partition pruning khi JOIN

Một số Spark/SQL engines hỗ trợ **dynamic partition pruning** khi join với một tập keys/filters nhỏ. Hiệu quả phụ thuộc statistics, join strategy và optimizer configuration. Không coi kỹ thuật này là thay thế cho partition key hợp lý; hãy dùng `EXPLAIN` và đo scan metrics.

### 21.5. EXPLAIN là bước bắt buộc của tối ưu

Với Spark SQL:

```sql
EXPLAIN FORMATTED
SELECT SUM(amount)
FROM silver.orders_clean
WHERE business_date = DATE '2026-11-20';
```

Tùy runtime, plan có thể hiển thị partition filters/pushed filters/data filters và scan nodes. **Không kết luận query scan 1 partition chỉ từ SQL text** nếu plan chưa xác nhận; view/CTE, timezone conversion hoặc không đồng bộ metadata có thể làm plan khác.

## 22. Partition pruning trong serverless analytics

Với **Azure Synapse serverless SQL pool** và những engines query files trực tiếp, chi phí có thể liên quan đến **dữ liệu xử lý/đọc** theo pricing model. Tối ưu physical layout và filter trở nên đặc biệt quan trọng.

### 22.1. Ví dụ đọc Parquet bằng OPENROWSET

Mẫu **T-SQL minh họa** cho Synapse serverless SQL:

```sql
SELECT TOP 100
    order_id, amount, business_date
FROM OPENROWSET(
    BULK 'https://STORAGE_ACCOUNT.dfs.core.windows.net/silver/orders_clean/business_date=2026-11-20/*.parquet',
    FORMAT = 'PARQUET'
) AS rows;
```

Ví dụ dùng đường dẫn mẫu và giả định workspace/identity có quyền storage; wildcard/path support, credential/authentication, schema inference và cách đọc partition columns phải được kiểm tra theo **serverless SQL engine**. Không mặc định cột `business_date` nằm trong Parquet content khi writer đặt nó chỉ ở folder partition metadata; có thể cần parse từ filepath hoặc external table definition.

### 22.2. Truy vấn đường dẫn ngày thay vì cả lake

Nếu query chỉ cần ngày 20, chọn đúng prefix/file partition có thể giảm số files/bytes đọc. Một query `BULK .../**` bao phủ hai năm dữ liệu mà chỉ lọc sau khi đọc có thể tốn hơn nhiều.

Đối với view/external table có partition metadata, kiểm tra engine hỗ trợ **partition elimination**, predicate pushdown và loại đường dẫn từ `filepath()` như thế nào. Đừng tin rằng mọi `WHERE business_date` đều làm tối ưu nếu `business_date` chỉ là virtual column không được engine nhận ra.

### 22.3. Serverless và dedicated không cùng cách tính chi phí

- **Synapse serverless SQL:** mô hình pay-per-query theo dữ liệu được xử lý, có ngưỡng/tối thiểu và pricing rules riêng tại thời điểm sử dụng.
- **Synapse dedicated SQL pool:** compute capacity/DWU, pause/resume và storage theo cấu hình; tối ưu distribution/columnstore thay vì chỉ file path.
- **Azure Databricks:** compute/DBUs và cloud resources theo workload/cluster/serverless modality, storage, SQL warehouse runtime.
- **Microsoft Fabric:** capacity/consumption và OneLake/warehouse workload theo chính sách sản phẩm.

**Không áp một công thức bytes-scanned cost cho mọi engine.** Mỗi môi trường cần dự toán theo pricing model chính thức, quan sát runtime telemetry và actual invoices.

### 22.4. Một câu `SELECT *` có thể tốn kém

```sql
-- Chỉ lấy ba cột cần cho KPI
SELECT business_date, country, SUM(amount) AS revenue
FROM gold.daily_orders
WHERE business_date >= DATE '2026-11-01'
  AND business_date <  DATE '2026-12-01'
GROUP BY business_date, country;
```

Với dữ liệu columnar, không đọc hàng trăm cột không cần thiết có thể giảm I/O. Với workload có bảng gold aggregated sẵn, query có thể rẻ hơn đọc lại toàn silver raw.

## 23. Columnstore, distribution và materialization

Nếu dữ liệu nằm trong **SQL warehouse/dedicated pool** thay vì files trực tiếp, các kỹ thuật quan trọng có thể gồm:

- **Columnstore indexes/segments:** nén dữ liệu theo cột và phục vụ scan/aggregate.
- **Data distribution/sharding:** giảm data movement trong joins/aggregations nếu distribution keys phù hợp.
- **Statistics:** giúp optimizer chọn execution plan.
- **Materialized views/aggregations:** tránh tính lại KPI lớn.
- **Partitioning của SQL table:** phục vụ partition elimination, switching/maintenance theo engine.

Các khả năng và cú pháp phụ thuộc Azure SQL Database, Synapse dedicated SQL pool, Fabric Warehouse hay dịch vụ tương tự. Không coi `HASH distribution` trong Synapse dedicated giống `PARTITIONED BY` của Delta Lake: **distribution giải quyết phân phối hàng giữa compute nodes**, còn table partitioning giải quyết một mục tiêu layout/maintenance khác.

### 23.1. Chọn distribution key

Với một fact table lớn thường join theo `customer_id`, distribution theo một key có cardinality cao và phân phối đều có thể giúp giảm data movement nếu engine/workload phù hợp. Nhưng nếu một vài customers chiếm phần lớn rows, skew có thể tạo node nóng. Hãy kiểm tra distribution skew và explain plan thay vì chọn key chỉ dựa trên tên cột.

### 23.2. Pre-aggregation

Một dashboard hỏi doanh thu theo ngày 10.000 lần/ngày có thể nên dùng bảng gold `daily_revenue` thay vì 10.000 lần quét hàng tỷ `order_events`. Nhưng gold aggregate phải được cập nhật khi:

- Có late events.
- Có refunds/corrections.
- FX rate/business logic thay đổi.
- Source backfill.

Materialization tiết kiệm compute đọc nhưng phát sinh **chi phí refresh và rủi ro stale results**. Cần đo tổng chi phí theo workload, không chỉ query latency.

### 23.3. Partition pruning và result cache

Một số engines có **query result cache** hoặc materialization tự động. Cache hit có thể khiến benchmark “rất nhanh” nhưng không phản ánh full scan của query mới; trong performance tests cần phân biệt cold/warm cache và tình trạng metadata. Tối ưu thực tế phải đo trên query patterns đủ đa dạng.

## 24. Định lượng lợi ích của phân vùng

Một mô hình giản lược:

\[
ScanReduction=1-\frac{BytesReadAfter}{BytesReadBefore}
\]

Giả sử:

```text
Dataset: 1.200 GB Parquet
Query: chỉ đọc ngày 2026-11-20
Trước tối ưu: 1.200 GB dữ liệu xử lý/scan
Sau pruning + column skipping: 24 GB

ScanReduction = 1 - 24/1200 = 98%
```

**Không tự kết luận hóa đơn giảm đúng 98%**: còn minimum billing, compute startup, metadata/list I/O, result caching, data transformations, maintenance và pricing model khác nhau. Tuy vậy, metric bytes scanned là một tín hiệu quan trọng.

### 24.1. Tại sao dữ liệu đọc ≠ kích thước table?

Một query có thể đọc ít hơn table size vì partition/column pruning, hoặc xử lý nhiều hơn do repeated scans/shuffles/uncompressed intermediates. Metrics có thể gọi là “bytes read”, “data processed”, “shuffle bytes”, “input size” với nghĩa khác nhau. **Cần thống nhất đơn vị và nguồn metric** trước khi so sánh.

### 24.2. Benchmark trước/sau

Lưu:

```text
query_id / workload
engine/runtime/version
date range/filter
table snapshot/version
data format/compression
partition key/number of partitions
file count and size distribution
bytes scanned / rows read
query duration p50/p95
compute consumption and billed cost estimate
result cache condition
result correctness checksum/row counts
```

Một tối ưu chỉ được chấp nhận khi **kết quả query vẫn đúng**, không thiếu late records hoặc bị thay timezone.

## 25. Mô hình tổng chi phí phân tích trên Azure

**Analytics cost** không chỉ là phí lưu file trên ADLS Gen2. Một kiến trúc có thể tốn tiền ở nhiều tầng, và tùy engine chi phí có cách tính hoàn toàn khác:

```text
Total Cost of Ownership (TCO)
  |
  +-- Ingestion: Event Hubs, Data Factory, connectors, networking
  +-- Storage: ADLS/OneLake, replicas, tiers, operations, snapshots
  +-- Compute: Spark jobs, SQL warehouses, Synapse, Fabric capacity
  +-- Query: data scanned / compute time / capacity usage tùy sản phẩm
  +-- Optimization: compaction, clustering, statistics, refresh
  +-- Observability: Log Analytics, data profiling, alerting
  +-- Governance/Security: catalog, encryption, private endpoints
  +-- Data movement: cross-region egress, inter-service transfers
  +-- People/operations: incidents, backfills, maintenance
```

### 25.1. Công thức dự toán khái niệm

\[
C_{month}=C_{ingest}+C_{storage}+C_{compute}
 +C_{queries}+C_{network}+C_{monitoring}+C_{maintenance}
\]

**Không cộng trùng** những thành phần đã nằm trong nhau: với một dịch vụ serverless, query compute có thể đã nằm trong giá query; với dedicated cluster, compute có thể được tính theo thời gian hoạt động dù không chạy query. Hãy điều chỉnh mô hình theo hóa đơn thực tế của SKU.

### 25.2. Đơn vị định lượng

| Thành phần | Đơn vị có thể đo | Cần chú ý |
|---|---|---|
| Data lake storage | GB/TB-month theo tier | Replication, versioning, retention và storage operations |
| Pipeline orchestration | Job/pipeline/activity runs hoặc compute usage | Activity type, data movement và integration runtime |
| Spark compute | VM/node hours, DBUs hoặc service-specific usage | Driver/executor thời gian chạy, idle/auto termination |
| Serverless SQL | Data processed/scanned per query theo bảng giá | Minimum billing/rounding và query plan |
| Dedicated SQL/warehouse | DWU/vCore/capacity-time và storage | Pause/resume, auto-stop/scale theo dịch vụ |
| Streaming | Throughput/capacity-time, retention/checkpoints | Backlog, ingress/egress, consumers |
| Monitoring | Log ingestion, retention, query/alert charges | Không log raw payload mọi event |
| Networking | Egress/zone/region transfer, gateways | Data locality và DR topology |

### 25.3. Ví dụ so sánh scan

Giả sử hệ thống chạy 2.000 truy vấn/ngày, mỗi truy vấn quét 100 GB nếu không prune. Sau khi partition và chuyển Parquet, truy vấn trung bình chỉ cần đọc 8 GB:

```text
Trước: 2.000 × 100 GB = 200.000 GB/ngày
Sau:   2.000 ×   8 GB =  16.000 GB/ngày
Giảm bytes scanned theo mô hình = 92%
```

Nếu sử dụng dịch vụ tính theo **data processed**, đây là tín hiệu chi phí mạnh; nếu dùng cluster trả theo giờ và vẫn chạy 24/7, tiết kiệm scan có thể giảm latency/capacity pressure nhưng **hóa đơn compute chưa giảm tương ứng** tới khi autoscale/auto-stop đúng cách.

### 25.4. Chi phí write cũng cần tính

Tối ưu truy vấn bằng cách viết lại toàn bộ 100 TB mỗi ngày để clustering có thể tốn hơn lợi ích từ 20 queries được tăng tốc. Tính:

\[
NetBenefit=QueryCostSaved-(RewriteCost+MaintenanceCost+AddedStorageCost)
\]

Đừng tối ưu layout chỉ bằng một benchmark query cực hiếm. Dùng **workload query frequency** và kế hoạch tăng trưởng.

## 26. Chọn compute phù hợp: batch, streaming, serverless, dedicated

### 26.1. Batch jobs

Khi dữ liệu chỉ cần cập nhật lúc 01:00 hằng ngày, chạy Spark/SQL jobs vài phút rồi tự dừng có thể tiết kiệm hơn một cluster chạy cả ngày. Cần cân nhắc startup overhead, job dependencies, tính sẵn sàng runtime và peak SLA.

### 26.2. Streaming

Streaming gần realtime có thể đòi compute chạy liên tục và state/checkpoints, làm baseline cost cao hơn batch. Chỉ chọn sub-second/second latency khi business thật sự cần; nhiều dashboard chấp nhận micro-batch 5–15 phút.

### 26.3. Serverless query

Ưu điểm: không vận hành cluster lâu dài, linh hoạt với ad-hoc analytics. Thách thức: data scanned/cost biến động theo truy vấn, concurrency/quota, cold-start/cache behavior và policy bảo mật storage.

### 26.4. Dedicated warehouse/cluster

Ưu điểm: kiểm soát capacity, performance ở workloads dự đoán được. Thách thức: phí compute khi idle nếu không pause/scale, cần quản lý concurrency và workload isolation. Lưu ý khả năng **pause/resume/auto-stop** phụ thuộc sản phẩm/tier cụ thể, không hứa tự động có trong mọi Azure service.

### 26.5. Tách interactive BI và heavy ETL

Nếu một Spark batch backfill 6 tháng dùng chung compute với dashboard giờ cao điểm, interactive queries có thể chậm. Cân nhắc **workload isolation**, resource groups/SQL warehouses/compute pools phù hợp và quotas; nhưng thêm nhiều compute có thể tăng chi phí, cần budget rõ.

### 26.6. Capacity thấp nhất chưa chắc rẻ nhất

Một cluster nhỏ chạy 9 giờ có thể tốn nhiều hoặc ít hơn cluster lớn chạy 1 giờ, tùy pricing và hiệu quả song song. Chọn từ **cost per successful workload**, không chỉ cost per node-hour.

## 27. Quản trị storage lifecycle, retention và data temperature

Không phải toàn bộ dữ liệu lake cần nằm trên tier truy cập nóng mãi mãi.

### 27.1. Phân loại theo tần suất truy cập

| Lớp | Truy cập thường gặp | Gợi ý thiết kế |
|---|---|---|
| Bronze mới trong 30 ngày | Dùng nhiều khi debugging/replay | Phù hợp tier truy cập và SLA |
| Bronze lịch sử 2 năm | Ít đọc, cần audit theo policy | Cân nhắc tier/lifecycle, restore latency |
| Silver active 90 ngày | Incremental merge và BI | Ưu tiên performance và hợp đồng query |
| Gold aggregates | Đọc thường xuyên | Storage/access path tối ưu cho serving |
| Quarantine | Chỉ điều tra/replay có kiểm soát | TTL/retention và bảo mật chặt |

Đây là mô hình tham khảo, không phải retention mặc định. Tier và lifecycle rules của Azure Blob/ADLS có **compatibility constraints, minimum retention/rehydration/operation charges** theo tier; file transaction logs/metadata của table formats cần được quản lý đặc biệt.

### 27.2. Không chuyển toàn bộ Delta data sang archive bừa bãi

Một Delta table đang được query/update cần transaction log và data files có thể đọc theo engine. Chuyển một số files sang archive/inaccessible tier mà không có plan có thể làm table snapshot/time travel bị lỗi. Chọn lifecycle **ở cấp dataset/partition đã kết thúc vòng đời** và xác minh compatibility, backup/restore và query behavior.

### 27.3. Time travel và VACUUM

Một Delta table có thể giữ data files cũ để hỗ trợ time travel/recovery theo retention config. `VACUUM` loại file không còn cần theo transaction log/retention:

- Chạy khi hiểu chính sách concurrent readers/streaming lag.
- Không đặt retention cực thấp chỉ để giảm storage và rồi làm hỏng job đang đọc snapshot cũ.
- Không coi `VACUUM` thay hoàn toàn legal deletion/privacy workflow.
- Thiết kế xóa PII xuyên raw/silver/gold/checkpoints/backups theo compliance.

### 27.4. Data lake replication và chi phí

Lựa chọn redundancy của Storage account như LRS/ZRS/GRS (theo khả năng của region/tài khoản) ảnh hưởng durability và cost; **nó không tự cho phép query dữ liệu vùng thứ hai như một active analytics source** hoặc bảo đảm đáp ứng RTO ứng dụng. DR cần thử restore/read access/compute và DNS/identity, không chỉ nhìn replication setting.

## 28. Tối ưu ingestion và orchestration

Ngay cả khi queries nhanh, pipeline có thể tốn kém vì copy dữ liệu lặp hoặc chạy full refresh không cần thiết.

### 28.1. Full load vs incremental

| Phương án | Khi phù hợp | Hạn chế |
|---|---|---|
| Full refresh | Dataset nhỏ, logic đơn giản, ít thay đổi | Quét/ghi dữ liệu cũ liên tục |
| Incremental append | Event logs bất biến | Dedup/late events/checkpoints |
| CDC upsert | Current snapshot thay đổi liên tục | Sequence, deletes, merge cost |
| Micro-batch | Gần realtime nhưng không cần mỗi event ngay | Windowing/checkpoint/latency trade-off |
| Streaming | SLO thấp, liên tục | Compute/state/ops cost và recovery phức tạp |

### 28.2. Kiểm soát vòng lặp không có dữ liệu

Một pipeline chạy mỗi phút nhưng source chỉ phát sinh dữ liệu mỗi giờ tạo nhiều empty runs, startup/scheduling overhead. Có thể dùng event triggers khi hỗ trợ hoặc điều chỉnh cadence. Tuy nhiên, cần xử lý **missing event trigger** và fallback polling để không bỏ sót dữ liệu.

### 28.3. Chunk kích thước hợp lý

Gom quá ít events tạo small files; gom quá nhiều tạo batch latency cao. Chọn microbatch interval và target file size dựa trên ingest rate, stream lag, partition granularity, SLA và cluster startup cost.

### 28.4. Data movement và region placement

Di chuyển hàng TB giữa regions cho ETL hằng ngày có thể tăng network cost và latency. Đặt compute gần storage/warehouse theo security/data residency; khi có DR hoặc hợp tác đa vùng, định lượng chi phí egress và privacy requirements. Không tự bật cross-region copy cho dữ liệu nhạy cảm khi chưa có phê duyệt.

### 28.5. Pipeline retry có thể nhân đôi chi phí

Nếu ADF/Spark job scan 1 TB rồi timeout ở cuối và retry 5 lần, compute và read/scan cost có thể tăng gần theo số lần chạy; dù có idempotent output, **retry vẫn tốn tiền**. Cần:

- Checkpoint theo partition/batch.
- Thời gian chờ và retry policy dựa trên transient errors.
- Max attempts/cost cap.
- Partial progress recovery khi được engine hỗ trợ.
- Alert khi cùng batch retry quá nhiều hoặc vượt budget.

## 29. Data quality cũng phải tối ưu chi phí

DQ check có thể rất nặng: `COUNT DISTINCT` toàn bảng 50 TB, join hai datasets lớn hoặc scan full history mỗi lần chạy. Không có nghĩa bỏ DQ, mà cần thiết kế **incremental + risk-based validation**.

### 29.1. Chia tiers của kiểm tra

| Lớp kiểm tra | Khi chạy | Ví dụ |
|---|---|---|
| **Fast gate** | Mỗi batch/microbatch | Schema, null, range, event ID dedup trong batch |
| **Partition gate** | Khi partition sắp publish | Duplicate cross-batch, count/source reconciliation |
| **Cross-domain gate** | Theo kỳ/đóng báo cáo | Orders vs payments vs refunds |
| **Deep audit** | Định kỳ hoặc theo anomaly | Full history consistency, sampling nguồn |
| **Backfill validation** | Sau sửa dữ liệu | Checksums/row counts trước-sau theo partition |

### 29.2. Incremental uniqueness

Nếu cần uniqueness `order_id` toàn current snapshot, không thể chỉ kiểm tra trùng trong một microbatch. Dùng **unique constraints/indexes** khi warehouse/DB hỗ trợ enforcement, hoặc transactional `MERGE` + source dedup + kiểm tra conflicts. Nếu engine không enforce uniqueness vật lý, phải có quy trình test/gate thay thế và công nhận giới hạn.

### 29.3. Sampling không thay hard constraints

Sampling có thể phù hợp phát hiện anomaly trong clickstream, nhưng **không đủ** để bảo đảm một hóa đơn tài chính không trùng hoặc thiếu 1 trong 1 triệu giao dịch. Critical constraints cần kiểm tra đầy đủ hoặc được enforcement bởi storage/database semantics phù hợp.

### 29.4. Reuse kết quả profiling

Nếu pipeline đã tính row_count, min/max event time, null counts và invalid counts khi write, lưu các aggregates đó như batch metrics để các downstream jobs không scan lại toàn bộ files chỉ để báo quality dashboard.

### 29.5. Tránh “quality score” che lỗi nghiêm trọng

Một dataset có 99,99% completeness nhưng thiếu **10 giao dịch có giá trị lớn** không nên được coi an toàn chỉ vì score gần 100%. Dùng **critical rules/weighted impact/absolute thresholds** và trạng thái PASS/WARN/FAIL có giải thích.

## 30. Observability: theo dõi sức khỏe pipeline và chất lượng dữ liệu

**Pipeline succeeded** không có nghĩa data trustworthy. Một batch có thể hoàn tất không lỗi kỹ thuật nhưng chỉ nhận 20% records nguồn, dùng sai timezone hoặc quên join refunds. Cần quan sát **data plane** bên cạnh job/process health.

### 30.1. Tầng quan sát

```text
Data Sources
   |
   +--> source counts / max source timestamp / CDC lag
   |
   v
Ingestion & Orchestration
   |
   +--> run status / duration / retries / bytes copied
   |
   v
Bronze -> Silver -> Gold
   |
   +--> DQ metrics / quarantine / reconciliation / freshness
   +--> partition/file metrics / bytes scanned / compaction
   |
   v
Consumers
   |
   +--> report freshness / query latency / failed refresh / cost
   |
   v
Azure Monitor / Log Analytics / data catalog / Cost Management
```

### 30.2. Minimal DQ metrics

| Metric | Cách đo | Ý nghĩa |
|---|---|---|
| `rows_ingested` | Count source rows theo batch/partition | Có dữ liệu tới không? |
| `rows_valid` / `rows_invalid` | Row-level rule aggregation | Tỷ lệ lỗi là bao nhiêu? |
| `dq_rule_failures` | Count theo rule ID/severity | Rule nào đang vỡ? |
| `max_event_time` | Max timestamp event | Data time tiến triển không? |
| `source_to_silver_lag` | Silver watermark trừ source/clock theo semantics | Độ trễ trong pipeline |
| `reconciliation_delta` | Chênh lệch nguồn và đích cùng contract | Thiếu/trùng records hoặc metric |
| `quarantine_backlog` | Rows/batches chưa xử lý | Data debt vận hành |
| `partition_count` / `file_count` | Table metadata/output manifest | Small files/metadata pressure |
| `query_bytes_scanned` | Engine metrics | Pruning/column skipping hiệu quả? |
| `compute_cost_per_run` | Job cost allocation | Optimization/cost regression? |

### 30.3. Freshness là một công thức có ngữ cảnh

Một cách đo:

\[
FreshnessLag=NowUTC-MaxAvailableEventTimeUTC
\]

Nhưng nếu nguồn chỉ phát sinh giao dịch trong giờ làm việc, tối không có event mới chưa chắc là incident. Cần có **source schedule và expected arrival policy**, hoặc so sánh watermark tiến triển với SLA. Không đặt alert freshness 15 phút cho một nguồn chỉ gửi daily batch lúc 02:00.

### 30.4. Không dùng raw keys/IDs làm metric labels

Không tạo Prometheus/Log Analytics dimension cho từng `order_id` hoặc từng file path nếu cardinality tăng cực lớn. Dùng labels bounded: `dataset, rule_id, environment, layer, severity, source_type`; các ID cụ thể lưu ở row-level quarantine/ticket được bảo vệ.

### 30.5. Structured log cho pipeline

```json
{
  "timestamp": "2026-11-20T10:30:00Z",
  "environment": "production",
  "pipeline": "orders-silver-daily",
  "run_id": "run-20261120-0042",
  "dataset": "orders_clean",
  "partition": "2026-11-20",
  "rows_in": 250000,
  "rows_valid": 249975,
  "rows_quarantined": 25,
  "quality_status": "WARN",
  "schema_version": 2,
  "duration_seconds": 173,
  "bytes_read": 1342177280
}
```

Đây là log **minh họa**, không phải một định dạng tự sinh của Azure. Không log raw events, credentials, PII hay query results chứa dữ liệu nhạy cảm. Đặt retention/permission của logs theo data classification.

## 31. Azure Monitor, Cost Management và truy xuất vận hành

### 31.1. Nguồn dữ liệu giám sát

Trong Azure, mỗi dịch vụ có cơ chế metrics/logs khác nhau:

- **Azure Data Factory:** pipeline/activity/trigger run status, duration, failures; diagnostic settings khi hỗ trợ.
- **Azure Databricks:** job/run, Spark metrics, cluster/SQL warehouse usage; monitoring/telemetry phụ thuộc workspace/runtime.
- **Azure Synapse Analytics:** pipeline/Spark/SQL monitoring và query statistics theo workload.
- **ADLS Gen2:** storage capacity, availability, transactions, ingress/egress, server latency theo metric dimensions.
- **Azure SQL Database:** CPU, sessions, waits, I/O và query statistics theo tính năng.
- **Power BI/Fabric:** refresh/capacity workload metrics theo license/capacity features.
- **Azure Cost Management:** subscription/resource-group/tag cost, budgets/alerts, chargeback/showback.

Không khẳng định tất cả metrics được xuất tự động vào cùng một Log Analytics table. Cần **bật diagnostic settings**, cấu hình export/ingestion đúng nguồn và kiểm tra schema trước khi viết KQL.

### 31.2. Ví dụ KQL cho pipeline run logs do ứng dụng tự xuất

Nếu một workspace có **custom table `DataQualityRuns_CL`** do tổ chức tạo và gửi structured logs (đã xác nhận schema), một query **mẫu**:

```kusto
DataQualityRuns_CL
| where TimeGenerated > ago(24h)
| summarize
    Runs=count(),
    Failed=countif(QualityStatus_s == "FAIL"),
    Quarantined=sum(tolong(RowsQuarantined_d))
    by Dataset_s
| order by Failed desc
```

**Không có sẵn bảng/cột này theo mặc định** trên Azure. Phải tạo ingestion pipeline, xác minh `DataQualityRuns_CL` và tên cột thực tế; các cột dạng `_s`/`_d` có thể không giống trong schema DCR/table mới. Không dùng query trên để tuyên bố workspace thiếu data quality.

### 31.3. Cost tagging

Gắn resource/job metadata theo:

```text
environment = prod
business_unit = commerce
data_product = orders
cost_center = analytics-042
owner = data-platform
criticality = high
```

Tags giúp **phân bổ chi phí resource có thể tag** nhưng không phải mọi serverless query/job tự tách bill theo tag. Với shared workspace/cluster, cần bổ sung usage attribution theo job/query/user/warehouse và phân bổ theo chính sách nội bộ.

### 31.4. Budget và anomaly alerts

Một budget nên có:

- Mức ngân sách theo tháng/quý và owner.
- Ngưỡng cảnh báo theo % budget và forecast.
- Phân biệt chi phí steady-state vs one-off backfill.
- Drill-down theo dịch vụ, môi trường, workload và tags.
- Runbook: giảm chi phí gì trước và tác động SLA ra sao.

**Budget alert không tự dừng mọi Azure resources**. Nếu cần automation tự động hạn chế compute/cancel jobs khi vượt chi phí, phải thiết kế riêng có phê duyệt, không tự xóa storage hoặc ngừng pipeline quan trọng vì vượt budget nhất thời.

## 32. Runbook 1: dashboard doanh thu lệch nguồn

### 32.1. Tình huống

Dashboard gold cho ngày 20/11 báo doanh thu thấp hơn báo cáo Azure SQL nguồn 7%. Pipeline “Success”, không thấy lỗi Spark.

### 32.2. Điều tra có thứ tự

1. Xác nhận **định nghĩa KPI**: paid vs created, refund, VAT, currency, timezone, conversion rates.
2. Xác định **source cutoff và target data-as-of**: có events cuối ngày chưa được ingest không?
3. Xem `rows_ingested`, `rows_valid`, `rows_quarantined` và quality gates của partition.
4. Kiểm tra CDC lag, source watermark, batch retries và idempotent dedup logic.
5. Xem bảng silver có records kỳ cũ/kỳ mới bị đặt nhầm partition do timezone?
6. So sánh aggregates tại từng lớp bronze → silver → gold theo cùng semantic contract.
7. Xem schema changes hoặc logic transformation từ deployment gần nhất.
8. Xác định có source duplicates bị giữ hoặc legitimate order updates bị drop bởi dedup?
9. Nếu cần backfill, chạy staging + validation + controlled promote.
10. Ghi incident, root cause, affected reports và bản sửa/chú thích lại số liệu.

### 32.3. Những điều không nên làm

- Không cộng thêm một số điều chỉnh tay vào gold để khớp report mà không có audit.
- Không xóa quarantine records để pass gate.
- Không sửa timezone production mà chưa tính đến các partitions lịch sử.
- Không chạy full overwrite table khi chỉ lỗi một khoảng ngày.
- Không tuyên bố đã sửa vì pipeline run chuyển màu xanh trong khi metric reconciliation vẫn lệch.

### 32.4. Tiêu chí đóng incident

Số liệu hai nguồn khớp **trong tolerance đã được chủ nghiệp vụ phê duyệt**, row counts và event time gap được giải thích, affected partitions được revalidated, dashboard hiển thị data-as-of/status đúng, backfill run có audit và không duplicate.

## 33. Runbook 2: truy vấn quá đắt hoặc quá chậm

### 33.1. Dấu hiệu

Một báo cáo doanh thu tháng vốn mất 20 giây nay mất 6 phút; chi phí query tăng, job load DB/warehouse cao.

### 33.2. Quy trình

1. Lấy **query ID**, engine/runtime, plan và thời điểm regression.
2. Đối chiếu query text, partitions/filter, result cache và table snapshot trước/sau.
3. Kiểm tra partition pruning thực sự có xảy ra không: `EXPLAIN`, scan files/bytes.
4. Kiểm tra `SELECT *`, implicit casts, UDF/function trên partition key hoặc wildcard path.
5. Xem files/partition, size distribution và có đợt ingest tạo tiny files không.
6. Xem skew, hot partition, join strategy, shuffle và statistics.
7. Kiểm tra storage network/region, compute saturation, concurrency, cluster auto-termination.
8. Thử tối ưu **trên staging/workload test**, đo query correctness, p50/p95 và cost.
9. Chọn compaction/clustering/partition strategy phù hợp; không rewrite toàn lake mù.
10. Theo dõi chi phí cả maintenance sau tối ưu và ghi baseline mới.

### 33.3. Tối ưu sai dễ gặp

**Tăng cluster size** có thể giảm latency nhưng tăng hóa đơn; **partition theo từng tenant** có thể giảm scan một query nhưng tạo millions of files; **OPTIMIZE toàn bộ table mỗi giờ** có thể tốn compute hơn tiết kiệm. Quyết định phải dựa trên **tần suất query và tổng chi phí**.

### 33.4. Một báo cáo tối ưu có thể kiểm toán

```text
Before:
  Queries/day = 1500
  Avg scan = 80 GB
  Query p95 = 95 s
  Quality results: verified

After:
  Avg scan = 12 GB
  Query p95 = 24 s
  Compaction/maintenance = 40 compute-min/day
  Quality results: same verified aggregation

Decision:
  Keep optimization only if total recurring savings
  exceed maintenance cost and SLO improves.
```

Những số trong ví dụ là giả lập; không phải hiệu năng hay giá của một Azure SKU cụ thể.

## 34. Runbook 3: small files và partition skew

### 34.1. Kịch bản

Một streaming job tạo 2 triệu files nhỏ trong 30 ngày. File listing và query planning tốn thời gian, metadata operations tăng dù dữ liệu thực chỉ vài trăm GB.

### 34.2. Các bước

1. Đếm files và phân phối kích thước **theo dataset/partition**.
2. Xác định writer tạo file: microbatch interval, Spark partitions, `partitionBy` cardinality, file rollover config.
3. Xem một partition có file count cực lớn hay toàn table đều bị ảnh hưởng.
4. Điều chỉnh microbatch size và physical partition granularity.
5. Dùng compaction trên **affected recent partitions** với table-format semantics.
6. Kiểm tra concurrency với stream writers/readers và checkpoint.
7. Theo dõi small-file creation rate sau khi fix writer.
8. Benchmark query scans/planning latency và total cost.
9. Thiết kế maintenance schedule theo data volume, không theo giờ cứng bất kể dữ liệu.

### 34.3. Không làm khi dùng Delta

Không tự dùng script di chuyển `part-...parquet` và xóa file cũ trong Delta table path vì có thể phá transaction log. Dùng cơ chế `OPTIMIZE`/maintenance tương thích với runtime; kiểm tra retention và snapshots trước `VACUUM`.

### 34.4. Skew khác small files

Skew có thể xảy ra ngay cả khi file sizes đẹp: một tenant chiếm 80% rows khiến một shuffle partition hoặc node làm quá nhiều công việc. Cần đo **task time, shuffle read/write, skew distribution** và xem execution plan; không chỉ compaction.

## 35. Runbook 4: backfill dữ liệu đến trễ

### 35.1. Kịch bản

Source gửi thêm 200.000 events của ngày 17/11 vào ngày 20/11. Gold đã đóng báo cáo ngày 17.

### 35.2. Quyết định chính

- Đây là **late data hợp lệ** hay duplicate replay?
- Metric có cho phép **restatement** kỳ đã đóng không?
- Partition nào cần cập nhật trong silver/gold?
- Consumers có cần thông báo số liệu thay đổi?
- Có thể chạy partial rebuild thay vì quét toàn bộ table?

### 35.3. Quy trình

1. Ghi nhận run/event IDs, source watermark và affected business dates.
2. Validate schema/rules, dedup theo logical event identity/sequence.
3. Đưa valid rows vào staging silver, invalid vào quarantine.
4. Áp idempotent merge/partition rewrite phù hợp theo transactions.
5. Recompute affected gold partitions và cross-table reconciliation.
6. Chạy DQ gate sau transform, đối chiếu source totals.
7. Publish/restate theo business approval.
8. Refresh caches/semantic model hoặc thông báo users theo contract.
9. Ghi chi phí backfill riêng và so sánh scan/written bytes.
10. Theo dõi các events late khác và điều chỉnh watermark khi thực sự cần.

### 35.4. Không tự phá SLA realtime

Một backfill 2 năm không nên dùng hết compute vốn dành cho pipeline realtime và dashboard interactive. Cần workload isolation, throttle, scheduling window hoặc compute quota theo nền tảng.

## 36. Bảo mật, data governance và riêng tư trong phân tích

Một thiết kế tối ưu chi phí **không được đánh đổi quyền truy cập dữ liệu**. Việc phân vùng, compaction, clustering và chuyển storage tier có thể thay đổi location/access pattern; chính sách bảo mật cần theo dữ liệu xuyên suốt các lớp.

### 36.1. Quyền ở từng lớp

| Thành phần | Ví dụ nguyên tắc |
|---|---|
| Bronze raw/PII | Hạn chế producer/ingestion và đội điều tra được phê duyệt |
| Silver clean | Chỉ các jobs, data owners và service principals cần thiết |
| Gold aggregates | Read access theo data product/role, che trường nhạy cảm |
| Quarantine | Quyền tối thiểu, audit chặt vì chứa payload lỗi có thể nhạy cảm |
| Catalog/lineage | Cho phép tìm metadata phù hợp nhưng không tự cấp quyền đọc dữ liệu |
| Compute identity | Managed identity/service principal được cấp scoped access |
| Diagnostics/logs | Không lưu raw sensitive payload, giới hạn retention và principal |

Đối với **ADLS Gen2**, phân quyền có thể kết hợp Azure RBAC và POSIX-like ACL theo cơ chế tài khoản/hierarchical namespace. Hãy kiểm thử **effective access** từ chính managed identity của job, không chỉ nhìn một role assignment trên portal.

### 36.2. Encryption và network isolation

- Storage/warehouse có encryption at rest theo cơ chế Azure; xem xét customer-managed keys nếu compliance yêu cầu và SKU hỗ trợ.
- Dùng TLS khi truyền dữ liệu qua mạng.
- Private endpoints/VNet integration và DNS đúng đường truyền theo dịch vụ.
- Không mở storage public endpoint hoặc SAS không giới hạn chỉ vì pipeline không kết nối được.
- Kế hoạch key rotation, access revocation và network change rollback.
- Data residency/region placement phù hợp hợp đồng/pháp lý.

### 36.3. Column-level và row-level security

Gold phục vụ nhiều bộ phận có thể cần row/column policies:

- Bộ phận sales chỉ xem doanh số region được phép.
- Analyst không xem email/phone của khách hàng.
- BI service principal chỉ có read quyền bảng gold.
- Cross-tenant query phải kiểm tra tenant isolation.

Những tính năng row-level/column-level security và masking **phụ thuộc engine/semantic layer**, không mặc định có trong Parquet files nếu ai đó có quyền đọc trực tiếp storage. **Không coi một Power BI filter là đủ bảo vệ raw storage** khi user vẫn có đường đọc ADLS.

### 36.4. Retention và data subject deletion

Một yêu cầu xóa dữ liệu khách hàng có thể ảnh hưởng:

```text
Bronze raw events
  -> Silver cleaned tables
  -> Gold marts
  -> Feature store / ML training copies
  -> BI caches / exports
  -> Backups, table time travel, quarantine
```

Cần catalog lineage và quy trình deletion/retention theo legal/privacy policies; backup/time travel giữ dữ liệu theo thời gian có thể xung đột yêu cầu xóa nếu không được quản lý. Không chỉ chạy `DELETE FROM silver` rồi kết luận mọi bản sao đã được xử lý.

### 36.5. Data exfiltration trong notebook

Một notebook Spark có thể `display()` nhiều bản ghi chứa PII, xuất CSV local hoặc ghi logs chi tiết. Cần giới hạn:

- Ai có quyền attach compute và đọc data sources.
- Khi nào được xuất dữ liệu ra external storage.
- Notebook revision/sharing/access logs.
- Secrets trong scope/Key Vault và masking output.
- Access policy cho artifact, cache, notebook result.

**Phân vùng theo tenant không tự bảo vệ dữ liệu tenant** nếu principal có quyền list/read toàn container.

## 37. Quality-as-code và CI/CD cho pipeline

### 37.1. Ba lớp kiểm thử

| Lớp | Chạy khi nào | Nội dung |
|---|---|---|
| **Unit tests** | Mỗi pull request | Parse schema, timezone, decimal, rules, mapping |
| **Integration tests** | Dev/staging sau deploy | Storage permissions, MERGE/checkpoint, job orchestration, quarantine |
| **Data regression tests** | Theo batch hoặc release | Row counts, aggregates, partition pruning, query correctness và cost |

### 37.2. Bộ fixture nhỏ nhưng đủ góc cạnh

Dữ liệu test nên có:

1. Row hợp lệ cơ bản.
2. `order_id` null.
3. `amount="abc"` và amount precision overflow.
4. Event timestamp sát 00:00 local time.
5. Duplicate event ID.
6. Update với source_version cũ đến sau version mới.
7. CDC delete/tombstone.
8. Missing customer reference tới trễ.
9. Late event sau watermark.
10. Refund/negative adjustment theo contract.
11. Tenant/currency không được hỗ trợ.
12. Empty batch và source file lỗi encoding.

Không lấy sample chỉ toàn dữ liệu “đẹp” rồi kết luận pipeline xử lý tốt production.

### 37.3. Ví dụ test PySpark

```python
# Pseudocode pytest/PySpark, giả định hàm transform_orders
# nhận DataFrame nguồn và trả về (valid, invalid).

def test_invalid_amount_goes_to_quarantine(spark):
    source = spark.createDataFrame(
        [("evt-1", "ORD-1", "not-a-number", "VND", "PAID")],
        ["event_id", "order_id", "amount", "currency", "status"]
    )
    valid, invalid = transform_orders(source)

    assert valid.count() == 0
    assert invalid.count() == 1
    assert invalid.select("reason_code").first()[0] == "INVALID_AMOUNT"
```

Đây là **pseudocode unit test**, không thể chạy độc lập vì `transform_orders` chưa được định nghĩa và thực tế cần thêm timestamp, schema/metadata fixtures. Mục đích là tách transformation thành hàm có thể test với dữ liệu nhỏ, chứ không đặt toàn bộ business logic trong một notebook cell khó kiểm thử.

### 37.4. Kiểm thử query correctness sau layout optimization

Sau thay partition/clustering/compaction:

- Row counts và distinct business keys phải phù hợp.
- Tổng tiền/checksum theo ngày/region không bị thay.
- Không mất dữ liệu do `overwrite` sai scope.
- Một query filter theo ngày phải trả cùng tập records.
- Benchmark scan bytes/latency trên cùng snapshot và data range.
- Cross-tenant access vẫn đúng policy.

**Tối ưu nhanh nhưng làm mất record không phải là tối ưu.**

### 37.5. Deploy qua môi trường

```text
Pull request (schema/rules/SQL/PySpark)
       |
       v
Static checks + unit tests + secret scan
       |
       v
Dev pipeline + synthetic dataset
       |
       v
Integration: Bronze -> Silver -> Gold + DQ gates
       |
       v
Staging: realistic volume/partition layout + cost benchmark
       |
       v
Review / approval
       |
       v
Production deploy (canary/shadow/backfill plan)
       |
       v
Monitor DQ, freshness, cost, query latency
```

Có thể dùng Azure DevOps/GitHub Actions và IaC để quản lý resources/jobs, nhưng phải cấp CI principal quyền tối thiểu. Một pipeline có quyền toàn subscription và storage secret hard-coded tạo rủi ro lớn hơn cần thiết.

### 37.6. Tránh thay schema và consumers đồng thời

Khi producer thêm breaking field change, triển khai consumers hỗ trợ cả hai phiên bản trước, sau đó cập nhật producer, backfill, deprecate old schema theo kế hoạch. Nếu rollout hai bên không đồng bộ, quarantine và reports có thể tăng lỗi dù build CI đều xanh.

## 38. Kiến trúc mẫu: phân tích thương mại điện tử trên Azure

### 38.1. Yêu cầu

Một nền tảng có:

- 50 triệu events clickstream/ngày.
- 1 triệu thay đổi order/payment state/ngày.
- Dashboard doanh thu theo ngày, thị trường, channel.
- Báo cáo gần realtime trong 15 phút; sổ doanh thu chính thức chốt sau late-data window.
- Dữ liệu raw giữ theo chính sách audit/privacy; gold phục vụ Power BI.
- Mục tiêu giảm query bytes scanned mà không giảm độ chính xác.

### 38.2. Sơ đồ đề xuất

```text
                 Azure SQL orders/payment
                         |
                      CDC/ETL
                         |
  Web/mobile -- Event Hubs -- Partner API
        |              |          |
        +--------------+----------+
                       |
                 Ingest jobs
                       |
                       v
             ADLS Gen2 Bronze (source/ingest_date)
                       |
            validate schema + provenance
                       |
                       v
              Silver Delta/Parquet
         event_id dedup, CDC merge, quarantine
                       |
            DQ checks + source reconciliation
                       |
                       v
              Gold reporting marts
         daily_paid_revenue, funnel, retention
                       |
         +-------------+---------------+
         |                             |
      SQL analytics                 Power BI
         |                             |
         +---------- Observability ----+
                       |
     Azure Monitor + catalog/lineage + Cost Management
```

### 38.3. Dataset design

| Dataset | Layer | Physical design | Chất lượng |
|---|---|---|---|
| `click_events_raw` | Bronze | Ingestion date/hour theo volume | Có event ID/source timestamp |
| `click_events_clean` | Silver | Event date hoặc ingestion date theo query pattern | Parse, dedup, consent filtering |
| `orders_cdc_raw` | Bronze | Source/batch/ingestion date | CDC sequence/operation đầy đủ |
| `orders_current` | Silver | Delta merge; partition/clustering dựa trên table size/query | Latest version, no duplicate current order |
| `daily_paid_revenue` | Gold | Business date/market nếu phân bố phù hợp | Reconciled, freshness/cutoff status |
| `dq_quarantine` | Quarantine | Source/ingestion date, restricted access | Reason, owner, replay state |

### 38.4. Phân vùng có chủ đích

Nếu clickstream có 50 triệu events/ngày và dashboard mostly daily/weekly, bắt đầu với daily partition; chỉ chia giờ khi scan/ingestion/latency benchmark cho thấy có lợi. Với orders_current current snapshot, partition theo `business_date` **có thể làm merge đắt** nếu cập nhật đơn thay đổi ngày; cân nhắc clustering theo business key và filter patterns.

### 38.5. DQ contract mẫu

```text
silver.orders_current:
  critical:
    order_id present
    one current row per order_id
    latest source_version wins
    valid status transition
    amount/currency parsable
  warning:
    country optional missing rate < threshold
  freshness:
    latest event age <= 15 minutes during operating hours
  reconciliation:
    paid total vs payment ledger per daily cutoff
  publish:
    no critical FAIL; warnings visible
```

Đây là mẫu policy, chưa phải rules thực thi. **Valid status transition** cần xây một state machine business với ngoại lệ refund/chargeback; không ép thứ tự bằng `string comparison`.

### 38.6. Cost optimization decisions

- Bronze ghi raw theo batches vừa đủ; tránh hàng triệu files nhỏ.
- Silver dùng incremental dedup/merge thay full refresh.
- Gold pre-aggregate cho queries nhiều lần.
- Tách interactive compute khỏi heavy backfill nếu cần.
- Auto-stop/pause compute ở workload không liên tục khi hỗ trợ.
- Dùng data skipping/partition pruning; inspect `EXPLAIN`.
- Hạn chế DQ full scans không cần; dùng incremental metrics.
- Theo dõi cost per successful pipeline run và per report/query.

### 38.7. Data recovery

Khi pipeline v2 có bug:

1. Dừng publish partition affected; không xóa raw.
2. Xác định source/batch IDs, table versions và range sai.
3. Sửa transformation/DQ tests trong CI.
4. Backfill từ bronze với stable event IDs và source sequence.
5. Reconcile silver/gold, xác nhận results với business owner.
6. Release và thông báo việc restatement nếu cần.

Không khôi phục từ Delta time travel snapshot cũ mà bỏ qua các events hợp lệ đã đến sau snapshot.

## 39. Bài tập thực hành

### Bài tập A — Chất lượng dữ liệu orders

Bạn nhận 100.000 order events, trong đó 100 records thiếu `order_id` và 50 records có `amount="abc"`; 20 records có cả hai lỗi. Hãy:

1. Thiết kế rules và thứ tự/quy cách gán reason.
2. Tính số unique invalid rows nếu đã biết overlap.
3. Quyết định FAIL/WARN theo mức độ ảnh hưởng, không chỉ tỷ lệ.
4. Viết SQL/PySpark tách quarantine.
5. Nêu những metadata cần để replay sau sửa lỗi.

**Hướng giải:** số invalid unique là `100 + 50 - 20 = 130` rows, nhưng tỷ lệ 0,13% **không tự chứng minh PASS** vì thiếu order ID/amount tài chính có thể là critical failure.

### Bài tập B — Partition ngày hay tenant

Một dataset có 100.000 tenants, 30 GB events/ngày và queries chủ yếu lọc theo ngày + tenant. Hãy so sánh:

- `partitionBy("business_date","tenant_id")`.
- `partitionBy("business_date")` và clustering/data skipping theo `tenant_id`.

**Hướng giải:** partition theo tenant tạo cardinality cao và tiny files; daily partition + clustering là ứng viên để benchmark, nhưng phải đo skew và query frequencies.

### Bài tập C — Truy vấn quét toàn lake

Query dashboard dùng:

```sql
SELECT *
FROM orders_clean
WHERE YEAR(business_date) = 2026
  AND MONTH(business_date) = 11;
```

Hãy đề xuất filter range và chọn cột cần thiết, kiểm tra `EXPLAIN`/bytes scanned. Giải thích vì sao không được khẳng định mọi function đều phá partition pruning.

**Hướng giải:** sử dụng `business_date >= DATE '2026-11-01' AND business_date < DATE '2026-12-01'`; đo plan và query cost trên cùng snapshot.

### Bài tập D — Small files

Streaming job tạo 1.440 microbatches/ngày, mỗi batch ghi 200 files nhỏ ở các partitions, tổng 288.000 files/ngày.

**Nhiệm vụ:** thiết kế batch interval/file size/partition granularity/compaction policy; tính chi phí maintenance so với query savings; nêu cách tránh sửa file thủ công trong Delta table.

**Hướng giải:** giảm output fragmentation từ writer và compaction recent partitions bằng table-aware maintenance, benchmark file listing/task scheduling/bytes scanned, không chỉ tăng cluster size.

### Bài tập E — Late events và business date

Đơn xảy ra lúc 23:58 ngày 19/11 theo Asia/Ho_Chi_Minh, đến nguồn phân tích lúc 00:10 ngày 20/11.

**Nhiệm vụ:** xác định `business_date`, `ingestion_date`, cách partition, watermark và chính sách sửa gold nếu ngày 19 đã chốt.

**Hướng giải:** business date theo event và timezone = 19/11; ingestion date = 20/11; backfill/restatement theo contract, không cắt UTC timestamp tùy tiện.

### Bài tập F — Chọn chi phí tính toán

Một workload batch chạy 30 phút mỗi ngày, không có queries ngoài khung giờ đó. Một cấu hình dedicated compute chạy 24/7.

**Nhiệm vụ:** tính time idle, đề xuất pause/auto-stop hoặc job compute theo tính năng hỗ trợ, so sánh startup overhead/SLA và các thành phần phí khác.

**Hướng giải:** idle time rất lớn; cân nhắc workload ephemeral/serverless khi phù hợp, nhưng không khẳng định mọi service/tier auto-pause được.

### Bài tập G — DQ và cost observability

Thiết kế dashboard có quality score, rows invalid, source watermark, partition count, file count, scan bytes, compute cost, báo cáo theo dataset và layer. Chọn một alert cho **critical DQ failure** và một alert cho **cost regression**; chỉ ra owner, window, threshold và runbook.

**Hướng giải:** quality critical gate có thể chặn publish; cost regression cần so với baseline cùng workload/query volume, tránh false positive do backfill được phê duyệt.

### Bài tập H — Backfill và idempotency

Một batch order ngày 18 bị chạy lại 3 lần do timeout. Silver được viết bằng `append` và gold đếm tổng `amount`.

**Nhiệm vụ:** nêu hậu quả, sửa thiết kế bằng batch ID/checkpoint/dedup/merge hoặc partition atomic replace, đối chiếu số liệu nguồn và tạo test duplicate run.

**Hướng giải:** append nhiều lần gây double/triple count; output phải idempotent, không chỉ retry job cho tới khi xanh.

### Bài tập I — Security và retention

Quarantine có customer emails, bronze raw được giữ 5 năm nhưng data privacy policy yêu cầu xóa một user trong thời hạn nhất định.

**Nhiệm vụ:** lập lineage/deletion workflow qua bronze, silver, gold, quarantines, backups/time travel; phân quyền và audit truy cập, xem xét policy retention.

**Hướng giải:** phân loại dữ liệu và bản sao, phối hợp privacy/legal retention, không chỉ xóa một row gold rồi kết luận hoàn tất.

## 40. Câu hỏi tự kiểm tra

**1. Data quality khác schema validation ở điểm nào?** Schema validation kiểm tra cấu trúc/kiểu; DQ còn gồm completeness, uniqueness, validity, consistency, accuracy, freshness, lineage và business rules.

**2. Bronze/silver/gold có bắt buộc là ba Azure services riêng?** Không. Đó là ba lớp logic; có thể cùng storage account hoặc khác nơi lưu/truy vấn tùy governance và kiến trúc.

**3. Vì sao không biến mọi amount parse lỗi thành 0?** Sẽ đưa dữ liệu sai vào doanh thu và che nguồn gốc lỗi, làm reconciliation khó hơn.

**4. Quarantine cần lưu gì?** Record/source reference, rule failure, run/batch ID, schema version, ingest time và quyền truy cập/retention an toàn.

**5. Uniqueness `order_id` có luôn đúng với events table?** Không. Một đơn có thể có nhiều events hợp lệ; phải chọn `event_id` hoặc business key/version theo grain.

**6. Freshness 30 phút có nghĩa luôn cảnh báo sau 30 phút không có event?** Không. Phải xét lịch phát sinh của nguồn và SLA, tránh báo động khi không có event hợp lệ.

**7. Event time khác ingestion time thế nào?** Event time là lúc sự kiện xảy ra, ingestion time là khi pipeline nhận được; chúng có thể khác do backlog/offline/late events.

**8. Vì sao cần UTC và business timezone rõ ràng?** Để tránh đưa sự kiện sát nửa đêm vào ngày báo cáo sai, nhất là dữ liệu đa vùng.

**9. CDC duplicate delivery cần giải quyết ở đâu?** Trong checkpoint/bronze provenance, silver dedup/upsert và gold aggregation idempotent.

**10. Partition pruning là gì?** Bỏ qua partitions không thỏa bộ lọc khi engine nhận diện partition metadata/predicate.

**11. Partitioning và clustering khác nhau thế nào?** Partitioning chia bảng theo tập giá trị; clustering tổ chức records/files gần nhau hỗ trợ data skipping nhưng không nhất thiết tạo folder mỗi distinct key.

**12. Vì sao không partition theo `order_id`?** Cardinality rất lớn làm phát sinh partitions/files nhỏ và metadata overhead, thường không hợp workload scan analytics.

**13. Giờ luôn tốt hơn ngày vì prune chi tiết hơn?** Không. Nếu data volume thấp sẽ tạo quá nhiều tiny partitions/files; cần benchmark.

**14. `df.repartition(32)` và `write.partitionBy("business_date")` giống nhau không?** Không. Cái đầu điều chỉnh Spark execution partitions, cái sau tạo physical table partition layout theo column.

**15. Parquet khác Delta Lake ở điểm nào?** Parquet là định dạng file columnar; Delta dùng Parquet cùng transaction log/table semantics và features hỗ trợ.

**16. Một Delta table có thể đọc bằng cách liệt kê mọi `*.parquet` không?** Không nên; có files không còn thuộc snapshot hiện tại nhưng chưa bị vacuum.

**17. Small files vì sao làm query chậm?** Tăng metadata/listing, file open, scheduling và management overhead.

**18. Có nên `coalesce(1)` mọi batch để giảm số files?** Không. Có thể bóp nghẹt parallelism và tạo file quá lớn.

**19. Z-ORDER có dùng được trên mọi SQL engine không?** Không. Đó là tối ưu phụ thuộc Delta/Databricks runtime và phải xem compatibility.

**20. Một function trên partition column có chắc chắn ngăn pruning?** Không chắc; tùy optimizer. Ưu tiên predicate trực tiếp và đo `EXPLAIN`/bytes scanned.

**21. `SELECT *` có thể khiến chi phí quét tăng vì sao?** Columnar engine có thể phải đọc các cột không cần; chọn cột giúp giảm I/O.

**22. Serverless SQL và dedicated SQL có cùng cost model không?** Không. Serverless có thể tính theo data processed, dedicated thường có capacity/compute time riêng.

**23. Scan giảm 90% có tự chứng minh bill giảm 90%?** Không. Còn compute, minimum billing, maintenance, storage và pricing specifics.

**24. Vì sao pre-aggregation gold giúp tiết kiệm?** Nhiều queries BI đọc bảng tổng hợp nhỏ thay vì scan lại hàng tỷ raw rows, đổi lại có refresh/consistency cost.

**25. Có nên chạy OPTIMIZE toàn bảng hằng giờ?** Không mặc định. Compaction tiêu compute; chỉ có lợi khi phần savings vượt chi phí rewrite/maintenance.

**26. Quản lý Delta VACUUM cần lưu ý điều gì?** Retention, readers/streaming jobs, time travel, privacy deletion và transaction log semantics.

**27. Data quality 99,99% có đủ để publish báo cáo tài chính?** Không tự đủ. Một số lỗi critical có thể làm sai hàng triệu đồng dù tỷ lệ records rất nhỏ.

**28. DQ check incremental có thay full audit không?** Không. Kết hợp fast batch gates với deep reconciliation định kỳ/risk-based.

**29. Pipeline Success có chứng minh số liệu đúng?** Không. Job có thể chạy đúng kỹ thuật nhưng thiếu records hoặc tính KPI sai.

**30. Cost tag có tự phân bổ mọi query serverless trong shared workspace không?** Không. Cần usage attribution theo job/query/user/capacity khi sản phẩm hỗ trợ.

**31. Vì sao một batch phải có idempotency key/checkpoint?** Retry sau timeout có thể ghi dữ liệu lặp nếu chỉ append.

**32. Backfill 6 tháng nên làm gì trước khi chạy?** Chọn partitions, giữ concurrent writes an toàn, staging, kiểm tra quality, budget và plan rollback.

**33. Vì sao không xóa bronze để sửa gold?** Bronze giúp replay/audit và điều tra; xóa phá provenance trừ khi retention/privacy policy đòi hỏi.

**34. Bật catalog có tự tạo lineage đầy đủ không?** Không. Cần xác minh connectors, lineage capture và phần pipeline tự xây.

**35. Optimizer có tự sửa semantic business date sai không?** Không. Query nhanh vẫn có thể trả sai ngày do timezone logic.

**36. Vì sao cần owner cho từng DQ rule và alert?** Khi fail cần người quyết định block/reconcile/fix, không chỉ số liệu lỗi hiển thị.

## 41. Checklist triển khai production

### 41.1. Hợp đồng và chất lượng dữ liệu

- [ ] Mỗi dataset có owner, consumer, business grain và mục đích sử dụng.
- [ ] Có data contract/schema version và policy schema evolution.
- [ ] Đã xác định event ID, business key, source version và timezone.
- [ ] Các rules completeness, validity, uniqueness, consistency, accuracy, freshness có test.
- [ ] Rules critical có hành động fail/hold publish, không chỉ ghi log.
- [ ] Quarantine có reason, provenance, replay plan, quyền và retention an toàn.
- [ ] Có row/batch/cross-table checks và sample sizes/denominator chính xác.
- [ ] Financial metrics có reconciliation với source ledger và business cutoff.
- [ ] Không tự biến invalid amount thành zero hoặc drop raw event không có audit.
- [ ] Có KPI data-as-of/finalized/restated khi dữ liệu đến trễ.

### 41.2. Ingestion, CDC và incremental correctness

- [ ] Bronze giữ đủ source metadata và replay semantics theo policy.
- [ ] Dữ liệu source/CDC changes có sequence/offset đáng tin theo phạm vi.
- [ ] Silver dedup theo grain hợp lệ, không xóa mất state transitions.
- [ ] CDC insert/update/delete/tombstone được xử lý rõ.
- [ ] Checkpoint chỉ tiến khi target commit an toàn.
- [ ] Retry cùng batch không nhân đôi silver/gold.
- [ ] Backfill chạy staging/test và có kế hoạch coexist với stream jobs.
- [ ] Late events và watermark đã được kiểm thử với timestamp sát nửa đêm.
- [ ] Schema/metric changes có rollout/consumer compatibility plan.
- [ ] Data subject deletion có lineage qua các bản sao liên quan.

### 41.3. Partitioning và file layout

- [ ] Đã thu thập query workload, filters phổ biến và data size growth.
- [ ] Partition key/độ hạt chọn theo queries, không chỉ theo sự thuận tiện của writer.
- [ ] Đã kiểm tra cardinality, skew, hot partitions và tiny partitions.
- [ ] Đã phân biệt physical table partition với Spark execution repartition.
- [ ] Dùng Parquet/Delta/table format phù hợp engine và transaction nhu cầu.
- [ ] Kích thước files và số files/partition được theo dõi.
- [ ] Có compaction/maintenance policy với cost benefit rõ.
- [ ] Đã kiểm tra partition pruning và column pushdown bằng explain/scan metrics.
- [ ] Clustering/Z-ORDER/liquid clustering chỉ dùng theo tính năng runtime hỗ trợ.
- [ ] Không sửa/xóa physical files của transactional table thủ công.
- [ ] Time travel/VACUUM/retention tương thích với streaming readers và compliance.

### 41.4. Compute và tối ưu chi phí

- [ ] Đã xác định pricing model của đúng Azure service/tier.
- [ ] Có baseline scan bytes, query latency, run duration và recurring cost.
- [ ] Query thường dùng chọn cột/filter phù hợp; giảm `SELECT *` không cần.
- [ ] Có gold aggregates/materialization cho dashboards hot-path khi hợp lý.
- [ ] Spark/dedicated compute có auto-stop/pause/schedule nếu được hỗ trợ và phù hợp SLA.
- [ ] Incremental processing được ưu tiên khi full refresh không cần thiết.
- [ ] Compaction/backfill/quality checks được tính chi phí maintenance riêng.
- [ ] Cross-region data movement và network egress được định lượng.
- [ ] Storage lifecycle không làm data lake/table transaction logs không đọc được.
- [ ] Budget, cost tags/usage attribution và cost anomaly alert có owner.
- [ ] Dữ liệu query benchmark đảm bảo correctness và cùng snapshot.

### 41.5. Bảo mật, vận hành và phục hồi

- [ ] ADLS/data catalogs/compute identities dùng RBAC/ACL tối thiểu.
- [ ] Không để secrets, tokens, PII trong logs/notebooks/metric labels.
- [ ] Network, encryption, private endpoints và data residency có review.
- [ ] Row/column-level restrictions được thực thi ở đúng data access layer.
- [ ] Catalog/lineage đủ để xác định reports bị ảnh hưởng khi schema/quality lỗi.
- [ ] Monitoring nối nguồn → bronze → silver → gold → consumers.
- [ ] Alert DQ/freshness/cost regression có threshold, window, owner, runbook.
- [ ] Có runbook report mismatch, slow query, small files và backfill.
- [ ] Pipeline có unit/integration/regression tests, release approval và rollback.
- [ ] Đã thử missing source, empty batch, duplicate CDC, late events và corrupt files.
- [ ] Đã xác nhận không publish data không đạt critical quality gate.
- [ ] Đã diễn tập replay/backfill khi job lỗi sau partial output.

## 42. Kết luận

**Chất lượng dữ liệu, phân vùng và tối ưu chi phí phân tích** là ba phần của một thiết kế thống nhất. Data contracts, **quality gates**, quarantine, reconciliation và lineage giúp bảo đảm bảng silver/gold đủ tin cậy cho các quyết định nghiệp vụ. **Partitioning, Parquet, Delta Lake, clustering, data skipping và compaction** chỉ hiệu quả khi bám mẫu truy vấn và data volume thực tế, không tạo quá nhiều tiny files hoặc làm mất thông tin lịch sử. Các kỹ thuật như incremental processing, pre-aggregation, auto-stop compute và storage lifecycle cần được đánh giá trên **tổng chi phí**, không chỉ một query benchmark.

Với Azure, hãy dùng đúng khả năng của **ADLS Gen2, Azure Data Factory, Azure Synapse Analytics, Azure Databricks, Microsoft Fabric hoặc dịch vụ tương ứng** theo workload/tier. Đo cả **độ đúng của kết quả, thời điểm dữ liệu sẵn sàng, bytes scanned, run cost, query latency và sự cố chất lượng**. Khi pipeline có thể replay an toàn, có owner cho từng rule, công bố số liệu cùng data-as-of/cutoff và kiểm soát chi phí theo data product, nền tảng phân tích mới thực sự có thể mở rộng mà vẫn đáng tin cậy và có thể kiểm toán.
