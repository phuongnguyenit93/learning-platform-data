# Phân tầng dữ liệu thô, dữ liệu chuẩn hóa và dữ liệu phục vụ

## Mục tiêu học tập

Một nền tảng dữ liệu cloud thường tiếp nhận dữ liệu từ nhiều nguồn: ứng dụng giao dịch, hệ thống thanh toán, CRM, thiết bị, log, SaaS và đối tác. Dữ liệu đến có thể khác schema, định dạng, múi giờ, đơn vị đo, chất lượng và ý nghĩa nghiệp vụ. Nếu đưa dữ liệu trực tiếp vào dashboard hoặc mô hình phân tích mà không quản lý nguồn gốc và các bước biến đổi, kết quả sẽ khó tin cậy, khó tái tạo và khó điều tra.

Một cách tổ chức phổ biến là phân tầng dữ liệu thành:

- **Raw / Bronze:** dữ liệu gốc được tiếp nhận và lưu giữ với ít biến đổi, kèm metadata nguồn.
- **Standardized / Silver:** dữ liệu đã được kiểm tra, làm sạch, chuẩn hóa schema, kiểu dữ liệu, khóa và ngữ nghĩa.
- **Serving / Gold:** dữ liệu được tổ chức theo nhu cầu sử dụng cụ thể như KPI, báo cáo, dashboard, phân tích, feature hoặc API.

Các tên Bronze/Silver/Gold là cách gọi thường dùng trong kiến trúc lakehouse; không phải mọi nền tảng đều bắt buộc phải có đúng ba tầng. Điều quan trọng là xác định rõ **hợp đồng dữ liệu, mức chất lượng, nguồn chuẩn, quyền sử dụng và trách nhiệm vận hành** tại mỗi ranh giới.

Bài học thuộc chương **Nền tảng dữ liệu**, tập trung vào phân tầng dữ liệu thô, dữ liệu chuẩn hóa và dữ liệu phục vụ. Nội dung đặt các quyết định trong bối cảnh thiết kế cloud từ yêu cầu nghiệp vụ tới lựa chọn storage, compute, network, security và mô hình triển khai; đánh giá các đánh đổi về độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo Well-Architected.

Sau bài học, bạn có thể:

- Giải thích mục đích, đầu vào, đầu ra và tiêu chí hoàn thành của từng tầng dữ liệu.
- Thiết kế luồng ingestion có thể audit, replay và xử lý dữ liệu đến muộn.
- Xác định data contract, schema version, business key, event time và ingestion time.
- Thiết kế quy trình validation, cleansing, deduplication, standardization và enrichment.
- Phân biệt dữ liệu nguồn, dữ liệu chuẩn hóa và dữ liệu phục vụ quyết định nghiệp vụ.
- Chọn batch, streaming hoặc hybrid pipeline dựa trên freshness, throughput và chi phí.
- Quản lý lineage, metadata, catalog, quality rules, ownership và data contracts.
- Bảo vệ dữ liệu theo classification, tenant, retention, encryption và least privilege.
- Thiết kế partitioning, file format, compaction, incremental processing và backfill.
- Xây dựng dashboard, SLA/SLO, reconciliation và kế hoạch khôi phục.
- Đánh giá chi phí và lựa chọn lake, warehouse hoặc lakehouse phù hợp workload.

## 1. Vì sao cần phân tầng dữ liệu?

Giả sử nền tảng đặt phòng nhận dữ liệu từ ba hệ thống:

- Booking service ghi đơn và trạng thái đặt phòng.
- Payment provider gửi giao dịch, hoàn tiền và chargeback.
- CRM lưu hồ sơ khách hàng và thông tin chiến dịch.

Ba nguồn có thể dùng những quy ước khác nhau. Booking ghi thời gian UTC, CRM ghi múi giờ địa phương; payment dùng minor unit như cents, booking dùng decimal; một hệ thống biểu diễn trạng thái là PAID, hệ thống khác dùng SETTLED; mã khách hàng ở CRM không giống customer ID trong booking.

Nếu dashboard doanh thu đọc trực tiếp ba nguồn, mỗi nhóm phân tích có thể tự viết logic join, đổi tiền tệ, lọc trạng thái và loại duplicate. Kết quả dễ không nhất quán. Thay đổi schema nguồn còn có thể làm hỏng nhiều dashboard mà không có điểm kiểm soát.

Phân tầng tạo ra các ranh giới có trách nhiệm rõ:

1. Raw giữ bằng chứng về dữ liệu đã tiếp nhận và thông tin nguồn.
2. Standardized biến các bản ghi khác nhau thành cấu trúc có ngữ nghĩa thống nhất.
3. Serving biểu diễn chỉ số hoặc dataset sẵn sàng dùng theo mục đích cụ thể.

~~~mermaid
flowchart LR
    S1["Booking DB"] --> I["Ingestion"]
    S2["Payment API"] --> I
    S3["CRM"] --> I
    I --> B[("Raw / Bronze")]
    B --> T["Validate / Clean / Standardize"]
    T --> S[("Standardized / Silver")]
    S --> M["Model / Aggregate / Serve"]
    M --> G[("Serving / Gold")]
    G --> BI["BI / Dashboard"]
    G --> API["Data API"]
    G --> ML["Analytics / ML"]
~~~

Luồng có thể là batch, streaming hoặc kết hợp. Không phải mọi dữ liệu đều phải đi qua cùng một công cụ, nhưng các tầng cần có hợp đồng và lineage để biết dữ liệu bắt nguồn từ đâu và được biến đổi như thế nào.

## 2. Raw, standardized và serving khác nhau thế nào?

| Tầng | Mục đích | Mức biến đổi | Người dùng chính | Ví dụ |
| --- | --- | --- | --- | --- |
| Raw / Bronze | Giữ dữ liệu nguồn và bằng chứng tiếp nhận | Tối thiểu; thêm metadata kỹ thuật | Data engineer, auditor, pipeline | JSON event nguyên bản, CDC record, file CSV nguồn |
| Standardized / Silver | Tạo dữ liệu có schema và ngữ nghĩa nhất quán | Parse, validate, deduplicate, chuẩn hóa và liên kết | Data engineer, analyst, domain team | Booking chuẩn hóa, payment transaction sạch |
| Serving / Gold | Phục vụ câu hỏi hoặc quyết định cụ thể | Business logic, aggregate, metric, denormalization | Analyst, BI, product, API, ML | Doanh thu theo ngày, KPI occupancy |

### 2.1. Raw không có nghĩa là không có quản lý

Raw có thể được lưu gần như nguyên bản, nhưng vẫn cần:

- Envelope hoặc manifest ghi source system, object/event ID, ingestion timestamp và schema version.
- Kiểm tra tính toàn vẹn file, checksum, kích thước và định dạng.
- Mã hóa, quyền truy cập và phân loại dữ liệu.
- Partition theo nguồn, ngày ingestion hoặc tenant khi phù hợp.
- Quản lý duplicate file, retry và late arrival.
- Retention, legal hold, archive và xóa theo chính sách.
- Theo dõi dữ liệu bị từ chối hoặc không parse được.

Raw không nên trở thành vùng chứa vô hạn không owner. Dữ liệu thô có thể chứa PII, secret hoặc payload độc hại; quyền đọc thường cần được giới hạn chặt hơn dữ liệu phục vụ.

### 2.2. Standardized không có nghĩa là xóa mọi khác biệt

Chuẩn hóa cần giữ được ý nghĩa và bằng chứng nguồn. Ví dụ đổi timestamp từ múi giờ địa phương sang UTC nhưng cần giữ source timezone hoặc raw value khi có ý nghĩa audit. Chuẩn hóa currency không được gộp USD và VND thành một số tiền duy nhất nếu không lưu currency và tỷ giá áp dụng.

Standardized layer nên thể hiện rõ:

- Các trường đã parse và kiểu dữ liệu chuẩn.
- Quy tắc null, missing, invalid và unknown.
- Khóa nghiệp vụ, khóa nguồn và identity mapping.
- Timestamp, timezone, currency, unit và precision.
- Record quality status và reason khi bị quarantine.
- Nguồn, schema version và lineage.

### 2.3. Serving không phải bản sao tùy tiện của Silver

Serving layer tổ chức dữ liệu theo một câu hỏi nghiệp vụ. Ví dụ dashboard revenue cần định nghĩa gross bookings, net revenue, refund, tax, commission và ngày ghi nhận. Một dataset customer 360 có thể cần snapshot, survivorship rule và quyền truy cập khác.

Serving data cần semantic contract: metric có tên, công thức, grain, timezone, currency, filter, freshness, owner và cách xử lý restatement. Hai dashboard cùng dùng tên “revenue” nhưng công thức khác nhau là vấn đề governance, không chỉ là vấn đề SQL.

## 3. Grain: đơn vị của mỗi dòng dữ liệu

Trước khi chuẩn hóa hay tổng hợp, phải xác định **grain** của dataset: một row đại diện cho điều gì?

Ví dụ:

- Raw booking events: một row là một event được tiếp nhận.
- Standardized bookings: một row là trạng thái chuẩn của một booking tại một thời điểm hoặc một snapshot đã xác định.
- Payment transactions: một row là một lần authorization/capture/refund/chargeback tùy contract.
- Serving daily revenue: một row là tổng hợp theo ngày, chi nhánh, currency và loại doanh thu.
- Customer activity: một row là một hoạt động của khách hoặc một customer-day summary.

Không xác định grain rõ sẽ gây double-count. Một booking có thể có nhiều payment attempt, nhiều event trạng thái và nhiều refund. Join thẳng bookings với payment events rồi sum booking amount có thể nhân số tiền theo số payment record.

### 3.1. Grain và cardinality trong phép join

Giả sử bảng booking có một row mỗi booking, bảng payment có nhiều row mỗi booking. Khi join:

~~~sql
SELECT
    b.booking_id,
    b.total_amount,
    p.payment_id,
    p.amount
FROM bookings b
JOIN payments p
  ON p.booking_id = b.booking_id;
~~~

Booking có ba payment event sẽ xuất hiện ba dòng. Nếu sum b.total_amount sau join, doanh thu booking có thể bị nhân ba. Cần aggregate payment về grain phù hợp trước khi join hoặc thiết kế model rõ quan hệ one-to-many.

### 3.2. Grain cần được ghi vào data contract

Một contract tốt trả lời:

- Một row/event đại diện cho entity, event hay snapshot nào?
- Khóa nào là unique ở grain đó?
- Có thể có nhiều phiên bản/attempt cho cùng entity không?
- Dữ liệu là current state hay history?
- Khi source gửi bản cập nhật, row cũ bị thay thế hay giữ lại?
- Aggregation được thực hiện trên grain nào?

## 4. Raw / Bronze: tiếp nhận và lưu dữ liệu nguồn

### 4.1. Quy trình ingestion

Một ingestion pipeline có thể gồm:

1. Xác thực nguồn và quyền truy cập.
2. Nhận file, event, CDC record hoặc API response.
3. Ghi payload vào storage bền vững.
4. Ghi manifest/metadata về nguồn, thời gian và phiên bản.
5. Xác minh checksum, format và schema envelope.
6. Ghi ingestion status và offset/watermark.
7. Phát hiện duplicate hoặc lưu bản gửi lại theo policy.
8. Cung cấp khả năng replay có kiểm soát.

Raw layer cần là nơi có thể giải thích “hệ thống đã nhận được gì”. Với API source không cho replay, có thể cần lưu response hoặc export snapshot theo quyền và retention để bảo vệ khả năng tái tạo.

### 4.2. Ingestion time và event time

Hai thời điểm thường khác nhau:

- **Event time:** thời điểm sự kiện xảy ra tại nguồn.
- **Ingestion time:** thời điểm nền tảng nhận được dữ liệu.

Ví dụ payment phát sinh lúc 23:58 UTC nhưng webhook đến sau 4 phút. Nếu phân vùng và báo cáo chỉ dựa vào ingestion date, payment có thể được xếp sang ngày khác so với nghiệp vụ.

Nên giữ cả hai timestamp khi có ý nghĩa. Xử lý late event phải có watermark hoặc policy cho phép cập nhật lại kỳ đã tổng hợp.

### 4.3. Raw append-only và replay

Một số pipeline giữ raw theo kiểu append-only: dữ liệu mới được thêm, không ghi đè các payload trước. Lợi ích là audit và replay; chi phí là storage tăng và phải xử lý duplicate/late data ở tầng sau.

Có thể dùng object storage với path có partition:

~~~text
raw/
  source=booking/
    ingest_date=2026-11-18/
      hour=10/
        part-00001.json
  source=payments/
    ingest_date=2026-11-18/
      hour=10/
        part-00001.json
~~~

Path là ví dụ minh họa. Partition nên phục vụ cách đọc và lifecycle; tránh tạo quá nhiều partition/file nhỏ. Không dùng tenant ID hoặc dữ liệu nhạy cảm không cần thiết trong object key nếu metadata/catalog đã đủ.

### 4.4. File format

| Format | Đặc tính | Dùng khi |
| --- | --- | --- |
| JSON | Dễ trao đổi, linh hoạt, kích thước thường lớn hơn và parse tốn hơn | API/event, raw ingestion |
| CSV | Đơn giản, dễ xuất/nhập nhưng schema yếu và xử lý quoting/null dễ sai | Trao đổi bảng cơ bản |
| Avro | Schema rõ, phù hợp event/row-oriented serialization | Event streaming, schema evolution |
| Parquet | Columnar, nén tốt, hiệu quả cho analytical scan | Standardized/serving trên data lake |
| ORC | Columnar, tối ưu một số engine/Hadoop ecosystem | Workload analytical phù hợp |
| Delta/Iceberg/Hudi table format | Quản lý transaction/metadata/version trên file data | Lakehouse table, incremental update và time travel theo khả năng format |

Không có format tốt nhất cho mọi tầng. Raw có thể giữ payload gốc đồng thời tạo bản curated columnar; standardized và serving thường có lợi từ columnar format khi query phân tích.

## 5. Standardized / Silver: làm sạch và chuẩn hóa

Silver là nơi tạo ra dataset có thể dùng lại giữa nhiều nhóm. Quy trình thường gồm parsing, type casting, validation, normalization, deduplication, identity resolution, enrichment và quarantine.

### 5.1. Chuẩn hóa kiểu dữ liệu

Ví dụ nguồn gửi:

- booking_id dưới dạng string.
- created_at ở nhiều định dạng timestamp.
- amount là string có dấu phẩy.
- status viết hoa/thường không thống nhất.
- currency thiếu ở một số record.

Silver có thể định nghĩa booking_id theo kiểu UUID, timestamp UTC, amount decimal có precision, status theo domain enum và currency theo mã chuẩn.

Không chuyển dữ liệu sai thành 0 hoặc empty string một cách im lặng. Cần phân biệt:

- Null: giá trị không có.
- Missing: field không xuất hiện trong payload.
- Invalid: field có nhưng không parse/không hợp lệ.
- Unknown: hợp lệ về kiểu nhưng chưa ánh xạ được ngữ nghĩa.
- Not applicable: field không áp dụng cho loại record đó.

### 5.2. Chuẩn hóa đơn vị và ngữ nghĩa

Ví dụ amount 100 có thể là 100 VND, 100 USD hoặc 100 cents. Chỉ số 100 không có ý nghĩa nếu không có currency và scale.

Một standardized transaction có thể gồm:

~~~json
{
  "transaction_id": "pay-981",
  "booking_id": "booking-123",
  "operation_type": "CAPTURE",
  "amount": 1250000.00,
  "currency": "VND",
  "occurred_at": "2026-11-18T09:15:00Z",
  "source_system": "payment-provider-a",
  "source_schema_version": 3,
  "quality_status": "VALID"
}
~~~

Ví dụ minh họa. Nếu quy đổi currency, phải lưu original amount/currency, converted amount/currency, exchange rate, source và effective timestamp. Không ghi đè giá trị nguồn bằng số đã quy đổi mà không có provenance.

### 5.3. Deduplication

Có thể gặp duplicate vì source retry, file gửi lại, webhook redelivery hoặc CDC replay. Dedup cần khóa phù hợp:

- Event ID nếu mỗi event có identifier ổn định.
- Source record ID + source version.
- Business key + effective version.
- Composite key theo domain contract.

Không deduplicate chỉ bằng cách chọn row mới nhất theo ingestion timestamp nếu event có thể đến sai thứ tự. Source version hoặc event sequence có thể đáng tin cậy hơn. Với event thực sự lặp hợp lệ (ví dụ hai lần thanh toán cùng số tiền), không được gộp chỉ vì payload giống nhau.

### 5.4. Quarantine và xử lý dữ liệu lỗi

Không nên để một record lỗi làm hỏng toàn batch nếu có thể cô lập lỗi. Có thể ghi:

- Raw reference hoặc object URI.
- Source ID và schema version.
- Rule ID thất bại.
- Error reason, timestamp và pipeline run ID.
- Trạng thái chờ sửa, retry hoặc chấp nhận có ngoại lệ.

Quarantine cần quyền truy cập và retention phù hợp; payload có PII vẫn phải được bảo vệ. Có quy trình sửa lỗi ở nguồn hoặc mapping rồi replay. Không tự ý sửa dữ liệu gốc mà mất dấu vết.

## 6. Data quality: định nghĩa chất lượng theo mục đích

Chất lượng không chỉ là “không có null”. Một dataset có thể không null nhưng sai currency, duplicate hoặc trễ quá SLA.

Các chiều chất lượng phổ biến:

| Chiều | Câu hỏi | Ví dụ rule |
| --- | --- | --- |
| Completeness | Trường bắt buộc có đủ không? | booking_id không null |
| Validity | Giá trị đúng miền và format không? | status thuộc enum cho phép |
| Accuracy | Giá trị phản ánh thực tế/nguồn chuẩn không? | amount đối chiếu được payment source |
| Uniqueness | Có duplicate ở grain đã định nghĩa không? | event_id unique trong source |
| Consistency | Các trường/hệ thống có mâu thuẫn không? | booking currency khớp payment contract |
| Timeliness | Dữ liệu có đến đúng hạn không? | 99% event vào Silver trong 5 phút |
| Referential integrity | Khóa tham chiếu có tồn tại không? | payment.booking_id tồn tại hoặc được quarantine |
| Freshness | Dataset được cập nhật gần đây không? | serving snapshot mới hơn watermark quy định |

### 6.1. Data quality gate

Một pipeline có thể đánh giá chất lượng ở nhiều mức:

- **Hard gate:** lỗi làm record/dataset không thể sử dụng; dừng hoặc quarantine.
- **Soft gate:** chất lượng giảm nhưng cho phép phát hành với warning và owner xác nhận.
- **Aggregate threshold:** tỷ lệ invalid/duplicate/null vượt ngưỡng thì không publish serving dataset.
- **Contract violation:** schema hoặc semantic contract bị phá vỡ; alert producer/owner.

Ví dụ quality report:

~~~text
Pipeline run: silver-bookings-2026-11-18-10
Input rows:              120,000
Valid rows:              119,760
Quarantined rows:            180
Duplicate rows:               60
Unknown status:               12
Null business key:             0
Quality pass threshold:    99.5%
Observed valid ratio:       99.8%
Result: PASS_WITH_WARNING
~~~

Các con số chỉ là ví dụ. Cần xác định mẫu số, record được loại trừ, cách tính duplicate và threshold theo mức độ rủi ro. Một tỷ lệ 99,8% có thể chấp nhận với dữ liệu clickstream nhưng không chấp nhận với ledger thanh toán.

## 7. Serving / Gold: mô hình dữ liệu phục vụ

Gold được tổ chức theo sản phẩm dữ liệu hoặc câu hỏi nghiệp vụ. Có thể là star schema, wide table, aggregate table, semantic layer, API dataset hoặc feature table.

### 7.1. Star schema cho phân tích

Ví dụ doanh thu đặt phòng:

- FactBooking: một row ở grain booking hoặc booking line.
- DimDate: ngày và thuộc tính lịch.
- DimBranch: chi nhánh.
- DimCustomer: khách hàng theo quy tắc privacy.
- DimRoom: loại phòng.
- DimChannel: kênh đặt.
- FactPayment: giao dịch thanh toán, hoàn tiền và chargeback ở grain riêng.

~~~mermaid
flowchart TB
    F[("Fact Booking")] --- D1[("Dim Date")]
    F --- D2[("Dim Branch")]
    F --- D3[("Dim Customer")]
    F --- D4[("Dim Room")]
    F --- D5[("Dim Channel")]
    P[("Fact Payment")] --- D1
    P --- D3
    P --- D2
~~~

Không join fact ở grain khác nhau mà không aggregate đúng. Booking fact và payment fact có thể có quan hệ one-to-many; việc join trực tiếp cần kiểm soát cardinality để tránh double-count.

### 7.2. Metric contract

Một chỉ số phục vụ kinh doanh cần định nghĩa:

- Tên và mô tả.
- Công thức và grain.
- Numerator/denominator.
- Filter/exclusion.
- Timezone và business date.
- Currency và conversion policy.
- Xử lý cancellation, refund, tax, fee và chargeback.
- Freshness/SLA.
- Owner và version.

Ví dụ:

~~~text
Net booking revenue
  = Captured booking amount
    - Successful refunds
    - Reversed/chargeback amount

Grain: business_date × branch_id × currency
Time basis: booking business timezone
Freshness target: 15 minutes
Owner: Finance Data Product
~~~

Đây là định nghĩa mẫu, doanh nghiệp cần xác nhận cách ghi nhận doanh thu và kế toán. Không dùng một metric “revenue” chung nếu các nhóm có quan điểm khác nhau về gross/net và thời điểm ghi nhận.

### 7.3. Data product

Serving dataset có thể được quản lý như một data product:

- Có owner và người tiêu dùng xác định.
- Có contract, schema và documentation.
- Có quality/freshness SLO.
- Có quyền truy cập và data classification.
- Có version, changelog và deprecation policy.
- Có support channel và incident process.
- Có chi phí lưu trữ/compute và capacity owner.

Không phải mọi bảng Gold đều cần product management đầy đủ; áp dụng mức governance tương xứng với mức độ dùng chung và tác động nghiệp vụ.

## 8. Data contract và schema evolution

Data contract là thỏa thuận giữa producer và consumer về cấu trúc, semantics, chất lượng, delivery và thay đổi schema. Một schema hợp lệ về mặt cú pháp vẫn có thể phá vỡ consumer nếu field đổi nghĩa.

Contract nên nêu:

- Tên dataset/topic và owner.
- Grain, primary/business key.
- Field, type, nullability, semantics và unit.
- Event time, ingestion time, timezone.
- Schema version và compatibility rule.
- Delivery mode, ordering, duplicate, retention.
- Quality rules và freshness target.
- PII classification, access policy và deletion requirement.
- Quy trình thông báo breaking change và deprecation.

### 8.1. Thay đổi tương thích

Thường dễ tương thích hơn nếu thêm field optional có default rõ. Các thay đổi rủi ro gồm rename field, đổi type, giảm precision, đổi timezone interpretation, thay enum semantics, chuyển grain hoặc thay khóa.

Ví dụ field amount chuyển từ integer minor units sang decimal major units là thay đổi semantic lớn dù tên field giữ nguyên. Consumer cũ có thể đọc số tiền sai mà không gặp lỗi parse.

### 8.2. Quy trình migration schema

1. Công bố contract/schema mới.
2. Kiểm tra consumer inventory và compatibility.
3. Deploy consumer có khả năng đọc cả version cũ/mới nếu cần.
4. Deploy producer phát version mới.
5. Theo dõi tỷ lệ dữ liệu và lỗi theo schema version.
6. Backfill hoặc chuyển đổi lịch sử khi cần.
7. Ngừng version cũ sau thời gian deprecation và xác nhận consumer đã di chuyển.

Không thay đổi raw payload đã lưu. Có thể tạo standardized v2 hoặc serving v2 song song rồi chuyển consumer sau khi đối chiếu.

## 9. Batch, streaming và hybrid pipelines

| Mô hình | Đặc tính | Khi phù hợp | Đánh đổi |
| --- | --- | --- | --- |
| Batch | Gom dữ liệu và xử lý theo lịch/đợt | Báo cáo theo giờ/ngày, backfill lớn | Độ trễ cao hơn, workload theo đợt |
| Streaming | Xử lý event liên tục | Cảnh báo, trạng thái gần thời gian thực | State, ordering, late event và vận hành phức tạp |
| Micro-batch | Xử lý các cửa sổ ngắn | Cân bằng gần realtime và hiệu quả | Có latency theo batch interval |
| Hybrid | Streaming cho freshness, batch để đối soát/rebuild | Sản phẩm dữ liệu quan trọng | Hai đường xử lý cần cùng semantics và reconciliation |

### 9.1. Batch pipeline

Một batch job có thể đọc manifest/file trong raw, validate theo schema version, transform thành standardized Parquet, chạy quality gate rồi publish Gold partition.

Cần idempotency theo run ID/business date/source snapshot, checkpoint, atomic publish hoặc staging path. Nếu job fail giữa chừng, serving consumer không nên thấy nửa partition được ghi.

### 9.2. Streaming pipeline

Streaming pipeline nhận event, parse schema, kiểm tra key/version, xử lý state/window và ghi Silver/Gold. Cần xác định event-time, watermark, late arrival, duplicate delivery, state retention, checkpoint và recovery.

Không coi streaming là luôn realtime. Queue lag, checkpoint, backpressure, sink throughput và window policy đều ảnh hưởng freshness.

### 9.3. Hybrid và reconciliation

Có thể dùng streaming để cập nhật Gold gần realtime, sau đó nightly batch tính lại từ nguồn lịch sử để đối soát. Hai pipeline phải dùng cùng business definition hoặc ghi rõ sự khác biệt; nếu không, dashboard ban ngày và báo cáo cuối ngày có thể cho số khác nhau mà không giải thích được.

## 10. Incremental processing, watermark và late-arriving data

Đọc lại toàn bộ raw mỗi lần có thể tốn compute và network. Incremental pipeline chỉ xử lý phần mới/thay đổi theo offset, CDC position, updated_at, event sequence hoặc watermark.

Một pipeline cần lưu:

- Source watermark/offset cuối cùng đã commit.
- Run ID và input snapshot.
- Khoảng dữ liệu đã xử lý.
- Số bản ghi nhận, bỏ qua, quarantine.
- Version logic/transform code.
- Thời gian bắt đầu/kết thúc và trạng thái.

### 10.1. Watermark

Watermark biểu diễn mốc mà pipeline tin rằng dữ liệu trước mốc đó đã được quan sát đủ theo policy. Watermark không đảm bảo không còn late data; cần định nghĩa allowed lateness và cơ chế sửa lại partition cũ.

Ví dụ, báo cáo ngày D có thể tạm đóng lúc 03:00 ngày D+1, nhưng payment provider có thể gửi chargeback sau nhiều ngày. Vì vậy cần phân biệt provisional metrics và finalized/restated metrics.

### 10.2. Late event và restatement

Khi late event đến:

- Nếu partition chưa chốt, áp dụng vào partition đang mở.
- Nếu partition đã chốt, tạo correction/restatement hoặc ghi delta theo policy.
- Giữ audit biết chỉ số thay đổi từ phiên bản nào và vì sao.
- Thông báo consumer nếu con số lịch sử có thể thay đổi.

Không cập nhật âm thầm số liệu đã phát hành nếu nghiệp vụ yêu cầu truy vết.

## 11. File layout, partitioning và compaction

Data lake thường lưu nhiều file theo dataset/table, partition và thời gian. Layout ảnh hưởng scan cost, query latency, list operation và khả năng quản lý.

### 11.1. Chọn partition key

Partition có thể theo event_date, ingestion_date, tenant hoặc domain dimension. Cần chọn dựa trên filter phổ biến và cardinality.

- Partition quá rộng: query quét nhiều dữ liệu.
- Partition quá nhỏ/quá nhiều: metadata tăng, nhiều file nhỏ và planning chậm.
- Partition theo tenant có cardinality rất cao có thể tạo nhiều directory/partition.
- Không partition theo customer ID nếu phần lớn query không filter theo đó.
- Cần xử lý dữ liệu đến muộn ghi vào partition cũ.

### 11.2. Small files problem

Streaming hoặc nhiều worker có thể tạo hàng nghìn file nhỏ. Query engine phải đọc metadata và mở nhiều file; chi phí request và planning tăng.

Compaction gom file nhỏ thành file lớn hơn theo target phù hợp với engine/storage. Cần tránh compaction đồng thời với writer gây conflict, và không rewrite quá nhiều dữ liệu khi lợi ích thấp.

### 11.3. Columnar layout và predicate pushdown

Parquet/ORC cho phép đọc các column cần thiết và tận dụng statistics/encoding/compression. Partition pruning và predicate pushdown giảm lượng dữ liệu scan khi query filter phù hợp. Tuy nhiên query engine và table format có semantics riêng; benchmark với schema, file size và query thật.

## 12. Lake, warehouse và lakehouse

| Kiến trúc | Điểm mạnh | Hạn chế/cân nhắc |
| --- | --- | --- |
| Data lake | Lưu dữ liệu đa dạng, chi phí object storage, phù hợp raw và large-scale processing | Cần tự quản lý catalog, schema, quality, transaction và governance |
| Data warehouse | SQL/BI, concurrency và semantic analytics được quản lý tốt | Chi phí compute/storage, ingestion và portability tùy dịch vụ |
| Lakehouse | Kết hợp object storage với table format/catalog/transaction cho dữ liệu phân tích | Cần quản lý engine compatibility, metadata, compaction và transaction semantics |

Lakehouse thường dùng table format như Delta Lake, Apache Iceberg hoặc Apache Hudi để bổ sung metadata, snapshot/version, schema evolution và transaction semantics trên object storage. Khả năng cụ thể tùy format, engine, catalog và phiên bản; không nên giả định mọi tính năng được hỗ trợ giống nhau.

Có thể dùng raw trên object storage, Silver/Gold dưới dạng lakehouse table, và warehouse/serving engine phục vụ BI. Một nền tảng có thể kết hợp nhiều loại storage thay vì buộc tất cả vào một dịch vụ.

## 13. Governance, catalog và lineage

### 13.1. Metadata catalog

Catalog giúp người dùng tìm dataset, hiểu schema, owner, quality, classification và quyền truy cập. Metadata nên có:

- Business name và technical name.
- Description, domain và owner/steward.
- Grain, schema, field semantics và example.
- Source system và upstream dependencies.
- Update frequency/freshness.
- Quality score và known limitations.
- Classification, retention và access request process.
- Dashboard/model/API consumer.

Không biến catalog thành danh sách bảng chỉ có tên. Metadata cần được cập nhật tự động từ pipeline và có người chịu trách nhiệm phần ngữ nghĩa.

### 13.2. Data lineage

Lineage mô tả dữ liệu đi từ nguồn qua ingestion, transform, dataset trung gian đến dashboard/API/model. Có thể có:

- **Table-level lineage:** bảng nào phụ thuộc bảng nào.
- **Column-level lineage:** cột đầu ra bắt nguồn từ cột/biểu thức nào.
- **Run-level lineage:** run nào tạo ra partition/file/version nào.
- **Business lineage:** metric nào ảnh hưởng quyết định nghiệp vụ nào.

Khi metric sai, lineage giúp khoanh vùng upstream source hoặc transformation. Khi thay đổi field, lineage giúp tìm consumer bị ảnh hưởng.

### 13.3. Ownership và stewardship

Mỗi dataset quan trọng cần owner có quyền quyết định về contract, quality threshold, access và deprecation; steward/domain expert hiểu semantics; platform team vận hành storage/compute/governance. Không để “data team” chung chung là owner cho mọi định nghĩa nghiệp vụ.

## 14. Bảo mật và privacy theo từng tầng

Raw thường chứa nhiều dữ liệu gốc nhất, bao gồm trường nhạy cảm hoặc payload chưa lọc. Standardized và serving có thể giảm dữ liệu không cần thiết nhưng vẫn có rủi ro tái nhận dạng hoặc lộ thông tin qua aggregate nhỏ.

Nguyên tắc:

1. **Classification:** phân loại public, internal, confidential, restricted hoặc mô hình tương đương.
2. **Least privilege:** tách role raw ingestion, transform, serving reader, analyst và administrator.
3. **Encryption:** mã hóa in transit và at rest; quản lý key/rotation.
4. **Data minimization:** Silver/Gold chỉ giữ trường cần dùng.
5. **Masking/tokenization:** che định danh hoặc dữ liệu nhạy cảm cho consumer không cần giá trị gốc.
6. **Tenant isolation:** partition/filter/authorization phải được kiểm chứng, không chỉ dựa folder path.
7. **Audit:** theo dõi ai đọc, xuất, thay đổi policy hoặc replay.
8. **Retention/deletion:** áp dụng lifecycle và propagate deletion qua raw, Silver, Gold, cache, index, backup theo nghĩa vụ.
9. **Secrets:** không đưa token, password hoặc credential vào raw event hoặc log.
10. **Egress control:** giới hạn đường dữ liệu ra ngoài và quản lý chia sẻ dataset.

Masking một trường trong dashboard không đồng nghĩa dữ liệu đã được xóa khỏi raw hoặc file archive. Cần quy trình xóa/ẩn dữ liệu xuyên tất cả bản sao và có bằng chứng hoàn thành.

## 15. Data reliability: backfill, replay và disaster recovery

Pipeline có thể lỗi do schema change, network, quota, storage, code bug hoặc downstream unavailable. Phải có khả năng phục hồi mà không tạo dữ liệu sai hoặc đè mất kết quả tốt.

### 15.1. Idempotent pipeline

Một pipeline idempotent khi chạy lại cùng input/version tạo kết quả tương đương, không nhân đôi dữ liệu. Kỹ thuật có thể gồm:

- Unique business key và source version.
- MERGE/upsert theo key.
- Partition overwrite có kiểm soát từ input snapshot xác định.
- Run ID và manifest.
- Atomic publish/commit của table format.
- Checkpoint chỉ advance sau khi output commit.
- Deduplication theo event identity và domain semantics.

Tránh append cùng file/batch mỗi lần retry mà không có run dedup hoặc commit protocol.

### 15.2. Backfill

Backfill cần xác định khoảng thời gian/key range, snapshot input, version transform, partition scope, capacity, chi phí, tác động production và cách đối soát. Có thể dùng compute riêng hoặc giới hạn tốc độ để không làm ảnh hưởng pipeline live.

### 15.3. Disaster recovery

Cần xác định RPO/RTO cho raw, standardized, serving và metadata/catalog. Raw có thể cần replication/object versioning; table metadata và catalog cần backup; serving có thể rebuild từ Silver nếu thời gian và nguồn cho phép.

Không coi “có file Parquet” đồng nghĩa có thể khôi phục table. Cần cả manifest, schema, transaction metadata, catalog, encryption key và code/config version.

## 16. Observability: freshness, quality và pipeline health

Một pipeline xanh không bảo đảm dữ liệu hữu ích. Job có thể exit 0 nhưng đọc nhầm partition, mất 30% record hoặc publish dataset cũ.

Theo dõi theo tầng:

| Tầng | Metrics | Câu hỏi |
| --- | --- | --- |
| Ingestion / Raw | Source lag, file count/size, checksum failure, ingest delay, duplicate | Dữ liệu nguồn đã đến đủ và toàn vẹn chưa? |
| Standardized / Silver | Input/output rows, valid/quarantined/duplicate, schema failure, transform duration | Dữ liệu có sạch và đúng contract không? |
| Serving / Gold | Freshness, row count, metric totals, publication version, query latency | Consumer có dataset mới và đúng không? |
| Platform | CPU/memory, storage, IO, queue lag, network, quota | Nút thắt hạ tầng ở đâu? |
| Governance | Access denied, policy violation, PII scan, retention status | Dữ liệu có được bảo vệ đúng không? |
| Cost | Storage by tier, scan bytes, compute hours, egress, cost per product | Chi phí tăng vì đâu? |

### 16.1. Freshness và completeness

Freshness có thể đo bằng thời gian từ event time hoặc source update đến khi dataset serving được publish. Phải nói rõ timestamp nào được dùng.

Completeness cần đối chiếu manifest/source count, watermark, sequence gap hoặc control total. Nếu source không cung cấp tổng số kỳ vọng, có thể dùng reconciliation dựa trên các quy tắc domain và cửa sổ quan sát.

### 16.2. Data reconciliation

Ví dụ đối chiếu:

- Số booking theo business date giữa nguồn và Silver.
- Tổng captured amount theo currency giữa payment provider và standardized payments.
- Tổng refund/chargeback theo kỳ.
- Số row/partition và maximum source version.
- Tổng doanh thu trong Gold so với phép tính độc lập trên Silver.

Một chênh lệch không nhất thiết là lỗi nếu có timing hoặc business rule khác; cần phân loại expected lag, late event, adjustment và defect.

### 16.3. Alert có hành động

- Không có file/source event trong cửa sổ kỳ vọng.
- Ingestion lag vượt SLA.
- Schema contract break hoặc quarantine rate tăng.
- Quality gate không đạt.
- Serving dataset cũ hơn freshness SLO.
- Reconciliation mismatch vượt threshold.
- Backfill/rebuild tiêu thụ quá capacity hoặc vượt budget.
- Storage/metadata small files tăng bất thường.
- Policy scan phát hiện trường nhạy cảm không được phép ở Gold.

Mỗi alert phải có owner, severity, dashboard và runbook. Alert không có hành động cụ thể sẽ tạo nhiễu.

## 17. Chi phí và tối ưu hóa storage/compute

Chi phí data platform gồm:

- Object storage, versioning, replication và request.
- Compute cho ingestion, transformation, streaming và query.
- Warehouse/serverless SQL scan bytes hoặc capacity.
- Broker, catalog, metadata service và orchestration.
- Network transfer, cross-region/cross-zone và egress.
- Logs, metrics, traces và audit retention.
- Backup, archive, restore test và disaster recovery.
- Data governance, scanning và security services.
- Nhân lực vận hành, quality incident và data product support.

### 17.1. Storage lifecycle

Có thể chia dữ liệu theo hot/warm/cold/archive:

- Raw mới hoặc dataset cần query thường xuyên ở storage tier có latency phù hợp.
- Dữ liệu lịch sử ít truy cập chuyển sang lớp tiết kiệm hơn nếu retrieval delay phù hợp.
- Raw archive giữ theo retention/audit; không giữ mọi bản sao vô thời hạn.
- Serving aggregate chỉ giữ lịch sử và grain cần thiết.
- Temporary/staging/quarantine có TTL và owner.

Lifecycle policy phải tính đến table format, snapshot, delete marker, legal hold và chi phí retrieval. Không xóa file trực tiếp nếu còn được tham chiếu trong transaction metadata/snapshot của lakehouse table.

### 17.2. Compute optimization

- Dùng incremental processing thay vì full scan nếu semantics cho phép.
- Chọn partition/columnar format để giảm scan.
- Compact small files theo lịch và threshold.
- Tách compute interactive BI khỏi backfill lớn khi cần isolation.
- Autoscale theo queue lag/query concurrency nhưng có quota và cost guardrail.
- Dừng tài nguyên dev/test khi không sử dụng.
- Dùng spot/preemptible compute cho job có checkpoint và khả năng retry.
- Giới hạn query scan và workload nặng theo tenant/team.

### 17.3. Cost per data product

~~~text
Cost per published data product
  = (Storage + ingestion + transformation + query
     + network + observability + governance cost)
    / Number of valid published data products or business uses
~~~

Có thể theo dõi cost per million records, cost per TB scanned, cost per dashboard/query hoặc chi phí theo domain/team. Chọn denominator phản ánh giá trị thực, tránh tối ưu chỉ số rẻ nhưng làm mất freshness hoặc chất lượng.

## 18. Case study: nền tảng đặt phòng đa nguồn

### 18.1. Bối cảnh

Một nền tảng đặt phòng nhận booking event liên tục, payment transaction từ provider, customer profile từ CRM và file đối soát hằng ngày. Ban điều hành cần dashboard occupancy/revenue gần thời gian thực; Finance cần số liệu cuối ngày có đối soát; bộ phận vận hành cần tìm kiếm booking theo nhiều tiêu chí.

Yêu cầu giả định:

- Booking list cập nhật trong 2 phút.
- Dashboard vận hành có freshness p95 dưới 5 phút.
- Báo cáo tài chính cuối ngày được chốt sau reconciliation.
- Không double-count payment capture/refund.
- Dữ liệu khách hàng nhạy cảm chỉ hiển thị cho role được cấp phép.
- Có thể tái tạo serving data từ nguồn được quản lý khi logic metric thay đổi.

### 18.2. Thiết kế ba tầng

**Raw / Bronze**

- Booking event append-only với source event ID, event time, ingestion time và schema version.
- Payment webhook/file lưu raw reference, checksum, provider ID và ingestion batch.
- CRM snapshot có source export timestamp.
- Dữ liệu lỗi format được đưa quarantine có metadata và quyền hạn chế.

**Standardized / Silver**

- Booking được map vào booking_id, tenant_id, booking status, business timezone và source version thống nhất.
- Payment được chuẩn hóa operation type, amount decimal, currency, provider transaction ID và state.
- Refund/chargeback được giữ ở grain riêng, liên kết booking/payment bằng business key.
- Customer identity mapping được quản lý với lineage và policy.
- Dedup dựa event/source ID và source version; late event cập nhật theo rule.

**Serving / Gold**

- Booking operational view phục vụ tìm kiếm/list.
- Daily occupancy aggregate theo branch, date, room type.
- Revenue model theo business date, branch và currency, phân biệt capture, refund và chargeback.
- Finance daily close dataset có reconciliation status và version đã chốt.

~~~mermaid
flowchart TB
    subgraph SOURCES["Sources"]
      B["Booking events"]
      P["Payment provider"]
      C["CRM exports"]
      F["Daily reconciliation files"]
    end
    B --> RAW[("Raw / Bronze")]
    P --> RAW
    C --> RAW
    F --> RAW
    RAW --> SILVER["Parse / validate / standardize / deduplicate"]
    SILVER --> STD[("Standardized / Silver")]
    STD --> OPS["Operational booking projection"]
    STD --> REV["Revenue / occupancy model"]
    STD --> FIN["Finance reconciliation model"]
    OPS --> GOLD[("Serving / Gold")]
    REV --> GOLD
    FIN --> GOLD
    GOLD --> DASH["Dashboard / BI"]
    GOLD --> API["Search and data APIs"]
~~~

### 18.3. Xử lý payment đến muộn

Webhook capture có event time 23:58 nhưng đến 00:04. Raw ghi ingestion date ngày mới, vẫn giữ event time ngày trước. Silver deduplicate theo provider transaction ID và operation type. Gold revenue model cập nhật partition business date phù hợp hoặc ghi adjustment/restatement theo policy. Finance close dataset ghi version và reconciliation status; số liệu đã phát hành có thể được restate có audit thay vì âm thầm ghi đè.

### 18.4. Xử lý thay đổi metric

Finance thay đổi định nghĩa net revenue để phân biệt chargeback đã xác nhận và đang tranh chấp. Không sửa trực tiếp metric cũ mà không version. Tạo metric contract v2, build serving v2 song song, so sánh kết quả với sample/control totals, thông báo consumer và chuyển dashboard sau phê duyệt. Giữ version v1 theo retention đã cam kết.

### 18.5. Kiểm soát bảo mật

Raw payment/CRM chỉ nhóm pipeline có quyền truy cập; Silver loại hoặc token hóa field không cần cho phân tích; Gold chỉ phát hành dimension/metric cần thiết. Query API thực thi tenant scope và role. Export, access và schema changes có audit. Deletion request được propagate tới các bản sao và index theo policy.

## 19. Khi nào phân tầng nên đơn giản hay tách sâu?

| Dấu hiệu | Cách tiếp cận có thể phù hợp |
| --- | --- |
| Một nguồn, vài dashboard, volume nhỏ | Một pipeline curated đơn giản, giữ raw snapshot nếu cần audit |
| Nhiều nguồn/schema và nhiều consumer | Raw + standardized dùng chung, serving theo domain |
| BI query làm ảnh hưởng transaction system | Tách data platform và serving store |
| Cần audit/replay và thay đổi logic thường xuyên | Raw immutable có retention và lineage |
| Freshness vài giây là yêu cầu quan trọng | Streaming/micro-batch và serving projection |
| Finance cần số liệu chốt có đối soát | Batch close, watermark, reconciliation và restatement version |
| Đội vận hành nhỏ, ít năng lực data engineering | Managed ingestion/warehouse, giảm số tầng/tool |
| Schema và ownership không rõ | Làm rõ data contracts/owners trước khi tách nhiều store |

Không phải mọi dataset cần đủ ba tầng vật lý. Có thể một tầng là schema riêng, table format riêng hoặc logical view. Mức độ tách phụ thuộc risk, volume, access pattern, freshness, compliance và đội ngũ.

## 20. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng raw trực tiếp cho dashboard | Query lặp logic, kết quả không thống nhất | Chuẩn hóa và định nghĩa serving metric |
| Coi Silver là bản sao đã đổi tên | Không có contract/quality | Xác định type, key, semantic và rule |
| Gold không ghi grain/công thức | Double-count và số liệu tranh cãi | Metric contract và reconciliation |
| Ghi đè raw payload | Mất audit/replay | Immutable/append-only hoặc versioned capture |
| Dùng ingestion date thay event time | Ghi nhận sai kỳ nghiệp vụ | Giữ cả event time và ingestion time |
| Dedup theo payload giống nhau | Gộp hai giao dịch hợp lệ | Business key/source event identity |
| Không xử lý late data | Báo cáo lịch sử thiếu hoặc sai | Watermark, allowed lateness và restatement |
| Một job append lại khi retry | Nhân đôi record | Idempotent write, run ID và commit protocol |
| Tạo quá nhiều file nhỏ | Metadata/query overhead | Compaction và partition hợp lý |
| Copy PII vào mọi serving store | Tăng risk và deletion cost | Data minimization, masking và lineage |
| Không có owner/lineage | Incident không ai xử lý | Dataset owner, catalog và dependency map |
| Rebuild không giới hạn trên production | Cạn compute/storage/IO | Isolate, throttle, budget và backfill plan |

## 21. Bài tập thực hành

Một công ty bán lẻ có ba nguồn: POS gửi giao dịch gần realtime, ERP gửi sản phẩm/tồn kho mỗi giờ và CRM gửi khách hàng mỗi ngày. Ban giám đốc cần dashboard doanh thu theo cửa hàng cập nhật trong 5 phút; Finance cần báo cáo chốt cuối ngày có đối soát; marketing cần phân tích khách hàng theo chiến dịch. Dữ liệu có PII và nhiều currency.

Hãy thực hiện:

1. Xác định raw, standardized và serving dataset cho từng nguồn; ghi grain và business key.
2. Thiết kế data contract cho POS transaction gồm event time, ingestion time, currency, operation type và schema version.
3. Nêu validation, normalization, dedup và quarantine rules cho Silver.
4. Thiết kế Gold metric gross sales, net sales, refund và daily close; định nghĩa currency/timezone.
5. Chọn batch/stream/hybrid cho dashboard 5 phút và báo cáo cuối ngày.
6. Thiết kế watermark và late-arrival/restatement cho giao dịch POS đến muộn.
7. Chọn partition key và file format; giải thích cách tránh small files.
8. Xây lineage từ POS tới Gold dashboard và chỉ ra owner tại mỗi ranh giới.
9. Thiết kế classification/access policy để marketing không đọc raw PII không cần thiết.
10. Đề xuất quality gate, reconciliation và ít nhất sáu cảnh báo có runbook.
11. Lập TCO cho raw retention, compute, storage, query, network và observability.
12. Viết ADR lựa chọn lake/warehouse/lakehouse và điều kiện đánh giá lại.

**Gợi ý tự đánh giá:** Bài làm đạt khi xác định được grain, source of truth, business key, metric semantics, freshness, late data policy, quyền truy cập và bằng chứng đối soát. Chỉ vẽ ba hộp Bronze/Silver/Gold chưa phải thiết kế data platform hoàn chỉnh.

## 22. Checklist trước production

- [ ] Mỗi tầng có mục đích, owner, contract, grain và consumer rõ ràng.
- [ ] Raw có source metadata, event/ingestion time, schema version, checksum và retention.
- [ ] Raw payload và quarantine được phân loại, mã hóa và giới hạn quyền.
- [ ] Silver có type, timezone, unit, identity mapping, dedup và quality rules.
- [ ] Invalid record có reason, owner và replay/fix process.
- [ ] Gold có metric contract, grain, formula, currency, timezone, freshness và version.
- [ ] Fact tables có grain rõ, tránh join nhân bản và double-count.
- [ ] Schema evolution có compatibility test, deprecation và migration plan.
- [ ] Batch/stream pipeline có checkpoint, watermark, backfill và idempotency.
- [ ] Late event/restatement có policy và audit.
- [ ] Partition/file layout được benchmark; small files có compaction plan.
- [ ] Catalog, lineage và dependency map được cập nhật.
- [ ] Tenant isolation, masking, deletion propagation và audit được kiểm thử.
- [ ] Có reconciliation source-to-standardized-to-serving.
- [ ] Dashboard theo dõi freshness, completeness, quality, lag, cost và query latency.
- [ ] Có RPO/RTO, backup/restore và rebuild test cho data/metadata.
- [ ] TCO tính storage, compute, query, network, observability, governance và operations.

## 23. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi khi thiết kế data layers |
| --- | --- |
| **Operational Excellence** | Dataset có owner, contract, lineage, quality gate, runbook, backfill và release process không? |
| **Security** | Raw/Silver/Gold có classification, least privilege, encryption, tenant isolation, retention và deletion đúng không? |
| **Reliability** | Ingestion, transformation và serving có idempotency, checkpoint, replay, reconciliation và recovery không? |
| **Performance Efficiency** | Grain, file format, partitioning, compaction, incremental processing và query engine có phù hợp access pattern không? |
| **Cost Optimization** | Retention, storage tier, scan bytes, compute, egress và cost per data product có được theo dõi không? |
| **Sustainability** | Có tránh full refresh, xử lý trùng, scan dữ liệu thừa và giữ bản sao không cần thiết không? |

**Kết luận:** Raw giữ bằng chứng dữ liệu đã nhận; standardized tạo ngữ nghĩa và chất lượng thống nhất; serving biến dữ liệu thành sản phẩm phục vụ quyết định. Ba tầng chỉ hữu ích khi có grain, contract, ownership, lineage, quality, freshness và quyền truy cập rõ ràng. Hãy chọn mức tách vật lý và công nghệ theo workload, năng lực vận hành và chi phí; thiết kế luồng để có thể đối soát, replay và rebuild, đồng thời bảo vệ dữ liệu từ ingestion tới consumer theo tinh thần Well-Architected.
