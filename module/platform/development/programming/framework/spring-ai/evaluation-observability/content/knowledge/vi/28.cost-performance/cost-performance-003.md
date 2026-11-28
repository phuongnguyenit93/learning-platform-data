# Phân biệt ước lượng phía ứng dụng với hóa đơn nhà cung cấp

## 1. Hai con số trả lời hai câu hỏi khác nhau

Một ứng dụng Spring AI có thể tự tính chi phí cho từng request bằng usage metadata và bảng giá. Sau đó, nhà cung cấp gửi usage export hoặc invoice cho cả project/account trong một kỳ billing. Hai con số thường không trùng tuyệt đối.

**Ước lượng phía ứng dụng (application estimate)** trả lời: “Theo usage mà ứng dụng quan sát được và bảng giá đã cấu hình, request/case/run này dự kiến tốn bao nhiêu?”

**Chi phí nhà cung cấp (provider billed cost)** trả lời: “Nhà cung cấp ghi nhận và tính tiền những dịch vụ nào trong kỳ billing, sau tier, discount, credit, phí và thuế theo hợp đồng?”

Estimate hữu ích cho cost per request, cost per successful task, phân tích prompt/model và giới hạn ngân sách gần thời gian thực. Billing export/invoice hữu ích cho đối soát và số tiền thực phải trả. Invoice thường không có đủ chi tiết để biết chính xác từng request ứng dụng gây ra khoản phí nào.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, cần giữ hai góc nhìn này để giải thích cost regression giữa các phiên bản prompt, model, RAG, tool và evaluator. Một estimate thấp hơn invoice không tự động có nghĩa cost engine sai; một invoice cao hơn tháng trước cũng không tự động có nghĩa mỗi request đắt hơn.

### Kết quả học tập

Sau bài này, người học có thể:

1. Phân biệt application estimate, provider usage export, billing export và invoice.
2. Xác định phạm vi và độ tin cậy của từng nguồn dữ liệu.
3. Chuẩn hóa invoice lines và provider usage về schema nội bộ.
4. Ghép billing data với request/case/tenant khi có đủ bằng chứng.
5. Tách usage variance, rate variance, discount, credit, tax, FX và timing variance.
6. Xử lý các hoạt động thiếu request mapping và chi phí dùng chung.
7. Tạo reconciliation ledger có trạng thái, audit trail và quy trình điều chỉnh.
8. Đọc variance report và tìm nguyên nhân thay vì ép hai tổng số bằng nhau.

## 2. Phân biệt các nguồn dữ liệu chi phí

Không phải mọi file tải từ trang billing đều là invoice. Nhà cung cấp có thể cung cấp nhiều loại export với mức độ chi tiết và trạng thái khác nhau.

| Nguồn | Nội dung thường có | Dùng để |
|---|---|---|
| Application usage event | Token, model call, tool call, vector operation mà app quan sát | Gắn hoạt động với request/case |
| Application cost estimate | Usage event × rate catalog | Ước lượng nhanh và phân tích nội bộ |
| Provider request/usage API | Usage theo request hoặc theo model, tùy dịch vụ | Đối chiếu usage gần nguồn |
| Provider billing export | SKU, project, region, quantity, rate/amount theo billing dimension | Phân tích chi phí theo dịch vụ |
| Invoice | Gross charges, discounts, credits, taxes, fees, amount due | Đối soát số tiền phải trả |
| Payment/credit statement | Thanh toán, số dư, credits và adjustments | Đối chiếu công nợ/tiền đã thanh toán |

Provider usage API có thể chưa bao gồm discount hoặc tax. Billing export có thể tổng hợp theo SKU/ngày/project thay vì request. Invoice có thể chỉ hiển thị tổng theo service hoặc dòng phí lớn. Cần ghi chính xác loại nguồn thay vì gọi tất cả là “actual”.

### Một invoice không phải lúc nào cũng là nguồn phân bổ tốt nhất

Invoice có thể là nguồn xác nhận số tiền phải trả, nhưng thường không chứa request ID, case ID hay trace ID. Do đó:

- Dùng usage events để phân tích hành vi từng request.
- Dùng provider usage/billing export để xác minh lượng tài nguyên provider ghi nhận.
- Dùng invoice để xác minh gross/net amount và điều chỉnh thương mại.
- Dùng reconciliation ledger để nối các nguồn và ghi rõ phần nào chưa thể phân bổ.

Không tạo request-level actual cost bằng cách chia invoice tổng cho số request nếu usage/cost mix giữa các request khác nhau. Phép chia đều chỉ là allocation rule và phải được gắn nhãn.

## 3. Vì sao estimate và invoice khác nhau?

Hai nguồn có thể khác nhau ở cả usage, giá và phạm vi tính tiền.

| Nhóm nguyên nhân | Ví dụ |
|---|---|
| Usage không quan sát được | Request timeout hoặc client disconnect sau khi provider đã xử lý |
| Usage semantics | Cached tokens là subset của input hay bucket riêng |
| Retry/async | Provider ghi nhận lần thử mà ứng dụng không lưu được response usage |
| Billing unit | Token, request, image, audio minute, read unit hoặc GB-month |
| Rate | Region, service tier, batch, model alias hoặc giá hợp đồng khác |
| Tier/commitment | Volume tier hoặc committed spend áp dụng ở cấp account/kỳ |
| Commercial adjustment | Discount, credits, minimum spend, surcharge |
| Tax/FX | Thuế, tỷ giá và ngày quy đổi khác |
| Time boundary | Usage phát sinh cuối kỳ nhưng provider ghi sang kỳ khác |
| Shared resource | Cluster, storage, observability hoặc support plan dùng chung |
| Rounding | Làm tròn từng line, từng request hoặc tổng invoice |

Trước khi sửa cost engine, hãy phân loại variance. Nếu usage quantity đúng nhưng invoice có discount cấp account, thay đổi công thức token cost sẽ làm sai dữ liệu request.

## 4. Bản đồ đối soát từ request đến invoice

~~~mermaid
flowchart TD
    A["Spring AI request / evaluation run"] --> B["Application usage events"]
    B --> C["Application cost estimate"]
    D["Provider usage API / billing export"] --> E["Normalize provider records"]
    F["Invoice lines / credit / tax"] --> E
    C --> G["Match and reconcile"]
    E --> G
    G --> H{"Attribution confidence"}
    H -->|Direct match| I["Request / call level"]
    H -->|Aggregate match| J["Project / SKU / time bucket"]
    H -->|No reliable match| K["Unattributed / shared cost"]
    I --> L["Variance classification"]
    J --> L
    K --> L
    L --> M["Adjustment events + audit"]
    M --> N["Reconciled cost report"]
~~~

Đối soát có hai tầng:

1. **Usage reconciliation:** ứng dụng quan sát bao nhiêu usage, provider ghi nhận bao nhiêu usage?
2. **Amount reconciliation:** với usage/rate và commercial adjustments đó, số tiền estimate khác invoice bao nhiêu?

Nếu chỉ so hai tổng tiền, không thể biết chênh lệch đến từ usage thiếu, rate sai, discount, tax hay khoản phí không thuộc request.

## 5. Chọn phạm vi so sánh trước khi tính variance

Một so sánh hợp lệ phải có cùng:

- Provider/account/project hoặc billing profile.
- Billing period và timezone/cutoff.
- Service/SKU/model/region khi có thể.
- Unit và usage type.
- Currency và cơ sở gross/net.
- Phạm vi discount, credit, tax và commitment.

Không so application estimate chỉ gồm token usage với invoice net gồm compute, tax và support fee rồi kết luận model estimate thấp. Hãy tạo một bridge để giải thích các lớp chi phí.

### Ba tổng số nên báo cáo

| Tổng số | Nội dung |
|---|---|
| Application estimated gross | Tổng usage app quan sát × rate catalog, trước invoice-level adjustments |
| Provider billed gross usage | Gross usage charges theo billing export/invoice lines trước discount/tax nếu nguồn cho phép |
| Provider invoice net | Số tiền sau discount/credit/fees/tax theo định nghĩa invoice |

Tên cột phải phản ánh đúng nguồn. Nếu billing export đã net discount hoặc không có gross amount, ghi rõ semantics và không tự suy ra gross.

## 6. Chuẩn hóa billing export và invoice line

Mỗi provider có schema khác nhau. Hãy giữ raw source artifact có kiểm soát, sau đó chuyển từng line sang schema nội bộ.

Ví dụ normalized billing line:

~~~yaml
providerBillingLine:
  lineId: bill-line-00091
  source:
    type: billing_export
    documentId: export-2026-11-project-a
    sourceRow: 91
  account:
    provider: provider-a
    accountId: account-a
    projectId: project-spring-ai
  period:
    start: 2026-11-01T00:00:00Z
    end: 2026-12-01T00:00:00Z
  resource:
    product: chat
    sku: model-x
    model: model-x
    region: global
    serviceTier: standard
  usage:
    quantity: 12300000
    unit: token
    usageType: input_token
  price:
    unitPrice: 2.00
    unitSize: 1000000
    currency: USD
  amount:
    gross: 24.60
    discount: 0.00
    credit: 0.00
    tax: 0.00
    net: 24.60
  billingCategory: usage
~~~

Đây là schema minh họa. Một số export không có unit price, model, request ID hoặc breakdown discount/tax ở từng line. Cho phép các trường đó null và lưu completeness/source metadata; không điền bằng suy đoán.

### Giữ nguyên raw source

Lưu các thông tin cần thiết để quay lại bản gốc:

- Provider, account/project và document/export ID.
- Invoice number hoặc billing period.
- Row/line reference.
- Import timestamp và file checksum.
- Parser/schema version.
- Currency và timezone gốc.

Raw billing export có thể chứa account identifiers và thông tin thương mại. Giới hạn quyền truy cập, mã hóa và retention theo chính sách tổ chức.

## 7. Chuẩn hóa application estimate để so sánh

Application estimate cần giữ chi tiết tương đương ở mức có thể:

| Dimension | Trường |
|---|---|
| Ownership | requestId, taskId, caseId, attemptId, runId, tenant |
| Operation | model call, embedding, vector query, tool, judge |
| Resource | provider, SKU/model, region, service tier |
| Usage | quantity, unit, usage type, occurredAt |
| Pricing | priceVersion, rateId, unit price, currency |
| Amount | gross estimate, precision, estimate status |
| Evidence | provider request ID, trace ID, usage source |

Không gộp mọi model calls trong request thành một record không có call ID. Một request có thể gọi nhiều model, nhiều tier hoặc fallback provider. Mỗi billable operation nên có usage event riêng.

### Estimate phải có status

| Status | Ý nghĩa |
|---|---|
| complete | Đã thu đủ usage cần thiết cho các operation được hỗ trợ |
| partial | Một số operation/usage chưa có dữ liệu hoặc chưa có giá |
| estimated | Có một phần usage do client ước lượng, chưa có provider confirmation |
| unpriced | Có usage nhưng không tìm được rate |
| unknown | Không xác định được usage semantics hoặc amount |

Đừng đưa partial hoặc unknown vào tổng estimate đầy đủ mà không gắn nhãn.

## 8. Xác định billing period và timezone

Application thường ghi timestamp UTC cho request; invoice có thể dùng billing timezone hoặc cutoff riêng. Hai mốc cần phân biệt:

- occurredAt: hoạt động phát sinh ở ứng dụng/provider.
- billingPeriod: kỳ provider phân bổ usage và charge vào invoice.

Không tự giả định billing period luôn là tháng UTC từ ngày đầu đến ngày cuối. Provider có thể dùng account timezone, daily aggregation, invoice anniversary hoặc delayed settlement.

### Quy tắc thực hành

1. Giữ timestamp UTC của application usage.
2. Giữ nguyên billing period và timezone do provider cung cấp.
3. Lưu invoiceDate, servicePeriodStart, servicePeriodEnd riêng.
4. Ghi nhận late-arriving events và adjustment lines.
5. Không ép usage event vào kỳ theo receivedAt nếu provider dùng occurredAt hoặc service period khác.

Một request lúc 23:59 theo giờ Việt Nam có thể thuộc ngày UTC trước đó. Chỉ dùng timezone của billing account khi tổng hợp invoice; không sửa timestamp gốc.

## 9. Những trường hợp usage phía ứng dụng bị thiếu

Application usage capture có thể bỏ sót chi phí trong các tình huống:

- App timeout trong khi provider tiếp tục xử lý.
- Client đóng kết nối khi streaming chưa kết thúc.
- Process crash trước khi persist usage metadata.
- Retry được thực hiện ở SDK, gateway hoặc provider mà app không nhìn thấy từng attempt.
- Batch job được gửi async và kết quả usage đến muộn.
- Fallback hoặc secondary model được gọi ở tầng proxy.
- Provider tính phí cho input processing dù response cuối không được trả về.
- Embedding/re-index chạy bởi worker hoặc pipeline khác.

### Cách giảm thiếu hụt

- Persist provider request ID và operation start event trước khi gọi provider.
- Ghi trạng thái started, completed, failed, timed_out, usage_pending.
- Dùng outbox/event persistence để giảm nguy cơ mất usage khi process crash.
- Reconcile định kỳ với provider usage/billing API.
- Đối chiếu tổng usage theo SKU/project/time bucket.
- Giữ estimate chưa hoàn chỉnh ở trạng thái partial cho tới khi có dữ liệu.

Không giả định mọi timeout đều bị tính phí hoặc không bị tính phí. Provider usage/billing là bằng chứng xác nhận.

## 10. Ghép application events với provider records

Độ chính xác của attribution phụ thuộc các khóa có sẵn.

| Phương pháp ghép | Độ tin cậy thường gặp | Điều kiện |
|---|---|---|
| Provider request ID | Cao | Cùng ID được lưu ở app và provider export |
| Batch/job ID | Cao đến trung bình | Provider export có batch ID, app giữ mapping item |
| Resource/project tag | Trung bình | Tài nguyên hoặc request được gắn tag ổn định |
| SKU + region + time bucket | Thấp đến trung bình | Có thể chỉ ghép aggregate, không xác định request |
| Tổng invoice / tổng application estimate | Thấp cho attribution | Chỉ so được tổng trong cùng scope |

Không ép một billing line tổng hợp thành danh sách request cụ thể. Nếu chỉ có project/SKU/day aggregate, kết quả attribution đúng là project-level hoặc day-level.

### Matching confidence

Mỗi match nên ghi:

- matchMethod: provider_request_id, batch_id, resource_tag, aggregate_bucket hoặc manual.
- confidence: direct, strong, aggregate, weak, unmatched.
- matchedDimensions: provider, project, SKU, region, period, unit.
- unmatchedReason: thiếu request ID, unit mismatch, time window mismatch...
- reviewStatus: pending, accepted, rejected.

Confidence là chất lượng bằng chứng ghép, không phải xác suất thống kê trừ khi có mô hình được hiệu chuẩn riêng.

## 11. Khi nào không thể phân bổ invoice về từng request?

Một invoice line có thể tổng hợp 4 triệu tokens cho model X trong cả tháng. Nếu provider không cung cấp request-level usage, app có thể có 3,9 triệu tokens đã quan sát. Chênh lệch 100.000 tokens chưa thể gán chính xác cho một request nào.

Trong trường hợp này:

1. Ghi usage variance ở scope SKU/project/billing period.
2. Kiểm tra app usage capture có bỏ sót provider calls hay không.
3. Nếu cần showback, phân bổ phần variance theo một policy được công bố.
4. Gắn nhãn phần được phân bổ là allocated, không phải direct actual.
5. Giữ nguyên aggregate invoice line để audit.

Các policy phân bổ có thể dựa trên usage observed, token share, request count, tenant resource share hoặc workload units. Chọn policy theo cost driver phù hợp. Không dùng request count cho mọi dịch vụ nếu cost chủ yếu phụ thuộc token/compute/storage.

## 12. Bảng variance: đo chênh lệch có ý nghĩa

Với cùng scope và currency:

\[
\Delta C = C_{\mathrm{provider}} - C_{\mathrm{application}}
\]

Relative variance:

\[
\mathrm{Variance\%} =
\frac{C_{\mathrm{provider}} - C_{\mathrm{application}}}
{C_{\mathrm{application}}} \times 100\%
\]

Nếu application estimate bằng 0, không chia cho 0; hiển thị variance tuyệt đối và trạng thái not_applicable cho percentage.

Đừng chỉ hiển thị variance tổng. Cần breakdown theo:

- Provider/SKU/model/region.
- Usage type và unit.
- Project/tenant nếu attribution đủ tin cậy.
- Billing period.
- Variance category.
- Match confidence.

### Ví dụ phân loại nhanh

| Kết quả | Khả năng cần kiểm tra |
|---|---|
| Provider usage > app usage, rate giống nhau | Missing events, retry/async, usage semantics |
| Usage bằng nhau, provider gross > estimate | Rate, tier, minimum fee hoặc SKU mapping |
| Gross gần bằng, invoice net thấp hơn | Discount/credit |
| Invoice net cao hơn gross estimate | Tax, fee, shared resource hoặc adjustment |
| Tổng tháng đúng nhưng ngày lệch | Timezone, late arrival, billing cutoff |
| Một project lệch, project khác bù lại | Mapping account/project/tenant hoặc cross-project resource |
## 13. Phân rã variance thành usage và rate

Khi application và provider dùng cùng đơn vị, cùng scope và cùng gross basis, có thể tách chênh lệch:

\[
C_{\mathrm{app}} = Q_{\mathrm{app}} \times P_{\mathrm{app}}
\]

\[
C_{\mathrm{provider}} = Q_{\mathrm{provider}} \times P_{\mathrm{provider}}
\]

Một phép phân rã:

\[
\Delta C =
(Q_{\mathrm{provider}}-Q_{\mathrm{app}})P_{\mathrm{app}}
+Q_{\mathrm{provider}}(P_{\mathrm{provider}}-P_{\mathrm{app}})
\]

Thành phần đầu là usage variance được định giá theo app rate; thành phần sau là rate variance trên provider quantity. Cách phân rã này có tính phụ thuộc thứ tự. Có thể dùng một thứ tự khác, nhưng phải thống nhất và ghi trong report.

Nếu đơn vị, SKU hoặc service tier khác nhau, không áp dụng công thức trực tiếp. Trước hết phải normalize về cùng billable unit và scope. Nếu không thể normalize, phân loại là mapping/unit variance.

### Ví dụ

Application ghi nhận 10 triệu input tokens với rate 2 USD/1M, nên estimate là 20 USD. Provider ghi nhận 10,2 triệu tokens ở cùng rate:

- Usage variance: (10,2M - 10M) × 2 / 1M = 0,40 USD.
- Rate variance: 0 USD.
- Provider gross: 20,40 USD.

Nếu provider quantity vẫn là 10,2M nhưng rate thực tế là 2,10 USD/1M:

- Usage variance: 0,40 USD.
- Rate variance: 10,2M × (2,10 - 2,00) / 1M = 1,02 USD.
- Provider gross: 21,42 USD.

Phân rã này giúp xác định có cần sửa usage capture hay price catalog.

## 14. Tách gross usage khỏi invoice net

Invoice net thường bao gồm nhiều lớp:

\[
C_{\mathrm{invoice\ net}} =
C_{\mathrm{gross\ usage}}
- D_{\mathrm{discount}}
- Cr_{\mathrm{credit}}
+ F_{\mathrm{fees}}
+ T_{\mathrm{tax}}
+ A_{\mathrm{adjustments}}
\]

Các dấu và tên component phải khớp semantics của provider. Một số invoice ghi discount thành số âm, một số ghi thành khoản giảm riêng. Không cộng/trừ lần nữa nếu amount line đã là net.

### Invoice bridge

| Bước | Khoản | Ý nghĩa |
|---|---|---|
| 1 | Application estimated gross | Usage app × rate catalog |
| 2 | Usage/rate variance | Chênh lệch so với provider gross usage |
| 3 | Provider gross usage | Gross charges theo provider |
| 4 | Discounts/credits | Giảm trừ cấp SKU/project/account |
| 5 | Fees/commitment/minimum | Khoản cố định hoặc thương mại |
| 6 | Tax/FX | Thuế và chuyển đổi tiền tệ theo invoice |
| 7 | Invoice net | Số tiền cuối cùng theo định nghĩa invoice |

Nếu invoice có support subscription, reserved capacity hoặc fixed fee, không phân bổ vào token rate. Giữ thành fixed/shared charge và chọn allocation policy riêng.

## 15. Ví dụ đầy đủ: estimate khác invoice vì nhiều nguyên nhân

Giả sử ứng dụng ước lượng cho một billing period:

| Dịch vụ | Application usage | Rate | Estimate |
|---|---:|---:|---:|
| Chat input | 12,0M tokens | 2,00 USD / 1M | 24,00 USD |
| Chat output | 1,5M tokens | 8,00 USD / 1M | 12,00 USD |
| Embedding | 2,0M tokens | 0,10 USD / 1M | 0,20 USD |
| Vector query | 80.000 operations | 0,0002 USD | 16,00 USD |
| Tool API | 5.000 calls | 0,001 USD | 5,00 USD |
| **Tổng** | | | **57,20 USD** |

Provider billing export ghi nhận:

| Dịch vụ | Provider usage | Rate | Provider gross |
|---|---:|---:|---:|
| Chat input | 12,3M tokens | 2,00 USD / 1M | 24,60 USD |
| Chat output | 1,55M tokens | 8,00 USD / 1M | 12,40 USD |
| Embedding | 2,0M tokens | 0,10 USD / 1M | 0,20 USD |
| Vector query | 82.000 operations | 0,0002 USD | 16,40 USD |
| Tool API | 5.100 calls | 0,001 USD | 5,10 USD |
| **Tổng** | | | **58,70 USD** |

Usage/rate variance là 1,50 USD:

- Chat input: +0,60 USD.
- Chat output: +0,40 USD.
- Embedding: 0 USD.
- Vector query: +0,40 USD.
- Tool API: +0,10 USD.

Invoice sau đó ghi:

| Khoản | Amount |
|---|---:|
| Provider gross usage | 58,70 USD |
| Account discount | -2,00 USD |
| Promotional credit | -0,50 USD |
| Tax 10% trên 56,20 USD | +5,62 USD |
| **Invoice net** | **61,82 USD** |

Bridge:

\[
57.20 + 1.50 - 2.00 - 0.50 + 5.62 = 61.82\ \mathrm{USD}
\]

Application estimate thấp hơn invoice net 4,62 USD. Nhưng chỉ 1,50 USD là usage/rate variance; 3,12 USD còn lại đến từ discount/credit/tax bridge so với gross estimate. Không nên sửa token pricing để bù khoản thuế hoặc discount cấp account.

Các số liệu và đơn giá trong ví dụ hoàn toàn giả định, dùng để minh họa cách phân loại variance; không phải bảng giá của nhà cung cấp.

## 16. Nhận diện các loại invoice line

Billing export có thể chứa nhiều category. Chuẩn hóa category trước khi tính:

| Category | Ví dụ | Xử lý |
|---|---|---|
| Usage | Token, embedding, vector query, API call | So với usage events |
| Fixed subscription | Support plan, reserved capacity, base fee | Shared/fixed cost |
| Discount | Volume discount, contract discount | Adjustment giảm |
| Credit | Promotional/committed credit | Credit balance/adjustment |
| Tax | VAT/GST/sales tax | Financial layer |
| Refund/credit memo | Hoàn tiền hoặc điều chỉnh kỳ trước | Adjustment có reference |
| Overage | Vượt quota/commitment | Usage hoặc surcharge tùy contract |
| Unclassified | SKU chưa nhận diện | Quarantine để review |

Không bỏ dòng lạ chỉ vì không map được về model. Một khoản phí chưa nhận diện cần xuất hiện trong report dưới dạng unclassified/unattributed, kèm owner xử lý.

## 17. Ingest billing export an toàn và có thể chạy lại

Billing exports thường được tải định kỳ hoặc nhận từ object storage/API. Ingestion cần idempotent để import lại file không nhân đôi cost.

### Các bước ingestion

1. Lưu raw file/response vào vùng staging có kiểm soát.
2. Tính checksum và ghi source document ID.
3. Xác định schema/version của provider export.
4. Parse và validate currency, period, SKU, unit, quantity, amount.
5. Chuẩn hóa về provider billing line.
6. Dedupe theo provider line ID hoặc composite key được xác định.
7. Ghi line mới và revision/correction riêng.
8. Gửi record không hợp lệ vào quarantine.
9. Ghi import report: rows read, accepted, rejected, duplicates, corrected.

### Idempotency key

Ưu tiên provider line ID ổn định. Nếu không có, tạo composite key từ source document, row identity, account, SKU, period, quantity và amount theo schema. Không dùng riêng amount làm khóa vì nhiều lines có thể có cùng giá trị.

Nếu provider gửi file điều chỉnh thay thế file cũ, phải nhận diện document revision và quy tắc replace/correction. Không cộng cả bản cũ và bản thay thế như hai khoản mới.

### Import report

~~~yaml
billingImport:
  importId: import-2026-11-a
  provider: provider-a
  documentId: export-2026-11-project-a
  schemaVersion: provider-export-v3
  checksum: sha256:example-checksum
  importedAt: 2026-12-02T03:00:00Z
  counts:
    rowsRead: 1250
    accepted: 1238
    rejected: 4
    duplicates: 8
    corrected: 0
  status: partial
~~~

Checksum và số liệu trong ví dụ chỉ minh họa cấu trúc. Nếu một phần row bị reject, import status phải phản ánh partial thay vì báo complete.

## 18. Quản lý late-arriving usage và invoice adjustments

Provider có thể cập nhật usage sau khi request kết thúc hoặc phát hành credit memo ở kỳ sau. Vì vậy, reconciliation cần hỗ trợ trạng thái mở và revision.

### Các trạng thái gợi ý

| Status | Ý nghĩa |
|---|---|
| pending | Chưa đủ provider data hoặc invoice |
| matched | Usage/amount khớp trong tolerance |
| variance_open | Có chênh lệch chưa phân loại |
| explained | Chênh lệch đã có nguyên nhân và bằng chứng |
| adjusted | Đã ghi adjustment/revision |
| closed | Kỳ được chốt theo policy |

Không xóa variance khi kỳ đã close. Nếu provider phát hành adjustment sau đó, mở một reconciliation revision mới liên kết kỳ gốc.

### Cutoff và grace period

Đặt grace period để chờ usage export/invoice hoàn tất trước khi chốt. Ví dụ:

- Daily usage report: tạm chốt sau 48 giờ.
- Monthly invoice: chốt sau khi invoice và adjustment window đã hoàn tất.

Các khoảng thời gian này chỉ là policy ví dụ. Chọn theo độ trễ thực tế của provider. Báo cáo trước cutoff cần mang nhãn provisional.

## 19. Reconciliation ledger và audit trail

Một reconciliation item nên giữ quan hệ tới cả estimate và provider line:

~~~yaml
reconciliationItem:
  reconciliationId: rec-2026-11-model-x
  scope:
    provider: provider-a
    projectId: project-spring-ai
    sku: model-x
    region: global
    period: 2026-11
    usageType: input_token
  application:
    quantity: 12000000
    amountGross: 24.00
    currency: USD
    priceVersion: catalog-2026-11-v1
  provider:
    quantity: 12300000
    amountGross: 24.60
    currency: USD
    sourceLineIds:
      - bill-line-00091
  variance:
    quantity: 300000
    amount: 0.60
    category: usage_variance
  match:
    method: aggregate_bucket
    confidence: aggregate
  status: explained
  explanation: Provider ghi nhận thêm usage chưa có request mapping.
  reviewedBy: finance-ops
  reviewedAt: 2026-12-03T09:00:00Z
~~~

Đây là schema minh họa. Không đưa thông tin cá nhân hoặc credential vào explanation. Có thể dùng owner/team alias và link đến hệ thống chứng từ có phân quyền.

### Audit trail phải trả lời

- Ai import và ai review?
- Dữ liệu nguồn nào được sử dụng?
- Parser và matching rule version nào chạy?
- Estimate được tính bằng rate/calculation version nào?
- Variance ban đầu là bao nhiêu?
- Adjustment nào đã được thêm, ai phê duyệt và vì sao?
- Kỳ nào đã được chốt, có revision sau chốt hay không?

## 20. Tolerance và ngưỡng variance

Không phải mọi chênh lệch nhỏ đều cần điều tra thủ công. Nhưng tolerance phải dựa trên đơn vị, mức tiền và risk.

Có thể định nghĩa:

- Absolute tolerance: số tiền chênh lệch tối đa.
- Relative tolerance: phần trăm chênh lệch so với estimate/provider amount.
- Quantity tolerance: usage delta tối đa theo unit.
- Timing tolerance: chấp nhận late usage trong grace period.
- Attribution tolerance: mức độ match cần có trước khi phân bổ.

Ví dụ policy:

~~~yaml
reconciliationPolicy:
  modelUsage:
    absoluteToleranceUsd: 0.05
    relativeTolerancePercent: 1.0
    quantityTolerancePercent: 0.5
  billingPeriod:
    gracePeriodHours: 48
  attribution:
    allowRequestLevelOnlyWhen:
      - provider_request_id
      - batch_item_mapping
~~~

Đây là policy minh họa. Không áp dụng một ngưỡng tiền nhỏ cho mọi tenant/service nếu volume và rủi ro khác nhau. Với khoản thuế, credit hoặc fixed fee, dùng category-specific rules.

### Đừng dùng tolerance để che lỗi hệ thống

Nếu 5% provider usage luôn thiếu do SDK retry không được ghi nhận, variance dưới ngưỡng có thể vẫn tích lũy thành khoản lớn. Theo dõi trend theo ngày/kỳ và số lượng unmatched events, không chỉ đóng từng line dưới tolerance.

## 21. Phân bổ shared cost sau khi đối soát

Invoice có thể chứa fixed fee, storage, support plan, cluster capacity hoặc observability platform dùng chung. Các khoản này không có một request cụ thể gây ra.

Một số driver:

| Shared cost | Allocation driver phù hợp |
|---|---|
| Vector storage | GB-month hoặc vectors/tenant |
| Dedicated compute | CPU/GPU hours hoặc reserved capacity share |
| Shared cluster | Query/read/write units hoặc workload share |
| Observability ingest | Span/log bytes hoặc service share |
| Support plan | Theo project/contract hoặc phân bổ cố định |
| Network egress | GB transfer theo tenant/service |

Allocation cần ghi policy version, kỳ, denominator và source. Khi tenant mới được thêm hoặc dữ liệu lịch sử thay đổi, không âm thầm sửa các kỳ đã chốt; tạo restatement nếu policy cho phép.

### Direct, matched aggregate và allocated

Giữ ba loại attribution riêng:

- `direct`: provider line ghép được với request/provider request ID.
- `aggregate`: ghép được ở project/SKU/period nhưng không có request-level mapping.
- `allocated`: chi phí dùng chung được phân bổ theo policy.

Không cộng chúng vào cùng một cột mà không có nhãn. Một report có thể hiển thị tổng cost theo tenant, nhưng cần cho người đọc biết phần nào direct và phần nào allocated.
## 22. Quy trình reconciliation theo từng kỳ

Một quy trình có thể chạy hàng ngày ở mức provisional và chạy lại khi invoice được phát hành:

1. Chọn provider account/project và billing period.
2. Chờ provider export đến cutoff/grace period đã định nghĩa.
3. Import application usage/cost events và provider billing lines.
4. Chuẩn hóa dimensions, units, timestamps và currencies.
5. Ghép trực tiếp theo provider request ID/batch ID khi có.
6. Ghép aggregate theo SKU, project, region, usage type và period.
7. So usage quantities trước, amount sau.
8. Phân loại usage/rate/unit/timing/discount/credit/tax/FX/shared variance.
9. Ghi adjustment và review các khoản vượt tolerance.
10. Publish report provisional hoặc closed cùng source/version metadata.

### Không bắt đầu bằng invoice total

Hãy đối chiếu từ chi tiết lên tổng:

- Usage quantity theo SKU/unit.
- Gross usage amount.
- Commercial adjustments.
- Invoice net và tax.

Nếu tổng không khớp, drill-down theo category. Điều này giảm nguy cơ một khoản credit lớn che mất usage event bị thiếu ở một model.

## 23. Pseudocode cho matching và reconciliation

Ví dụ quy trình tổng quát:

~~~text
for each providerBillingLine:
  validate source and normalize dimensions

  directMatches = find application events by providerRequestId

  if directMatches are complete and unique:
    match with confidence DIRECT
  else:
    aggregateMatches = aggregate application events by:
      account, project, sku, region, usageType, unit, billingPeriod

    if dimensions and period are compatible:
      match aggregate with confidence AGGREGATE
    else:
      mark UNMATCHED and record reason

  compare provider quantity with application quantity
  compare gross amount only after unit/rate scope is aligned
  classify variance
  persist reconciliation item and source references
~~~

Đây là pseudocode. Hệ thống thật cần xử lý partial matches, một provider line bao phủ nhiều app events, một app event được chia thành nhiều provider lines, late events, corrections và duplicated source documents.

### Matching cardinality

Không mặc định quan hệ luôn là một-một:

- Một app request có thể tạo nhiều provider calls.
- Một provider batch line có thể đại diện nhiều items.
- Một invoice line có thể tổng hợp nhiều ngày hoặc nhiều project.
- Một app event có thể có nhiều adjustment lines.

Thiết kế matching table dạng many-to-many khi nguồn dữ liệu yêu cầu. Lưu allocated quantity/amount và quy tắc phân bổ; tổng phân bổ phải bằng lượng/amount của parent line trong tolerance.

## 24. Kiểm tra tính đầy đủ và chất lượng dữ liệu

Trước khi chốt report, kiểm tra:

| Kiểm tra | Phát hiện |
|---|---|
| Source coverage | Thiếu file hoặc billing account |
| Period coverage | Thiếu ngày/giờ trong kỳ |
| SKU coverage | SKU mới chưa được map |
| Unit consistency | Token/item/GB/GiB bị nhầm |
| Currency consistency | Cộng nhiều currency mà chưa quy đổi |
| Duplicate lines | Import lặp hoặc file revision bị cộng hai lần |
| Negative quantities | Credit/refund bị hiểu sai thành usage âm |
| Missing price | Không có unit rate hoặc amount |
| Unmatched usage | App/provider không ghép được |
| Unexplained variance | Có delta chưa phân loại |
| Invoice completeness | Chưa có tax/credit/final invoice lines |

### Negative amount không nhất thiết là lỗi

Credit memo, refund và adjustment có thể có amount âm. Đừng áp validation quantity/amount >= 0 cho mọi invoice category. Validate theo billing category và semantics của provider.

## 25. Đối soát khi provider không cung cấp request-level usage

Nhiều dịch vụ chỉ cung cấp usage aggregate. Khi đó, mục tiêu là chứng minh tổng usage/cost ở đúng scope, không tạo mapping giả.

Ví dụ provider chỉ cung cấp:

- Model X, project A, region global, tháng 11: 12,3M input tokens.
- Model X, project A, region global, tháng 11: 1,55M output tokens.

Application có thể tổng hợp usage theo cùng dimensions:

- 12,0M input tokens.
- 1,50M output tokens.

Có thể kết luận app capture thiếu 0,3M input và 0,05M output trong scope tháng đó, nếu unit/semantics/time window khớp. Không thể kết luận request cụ thể nào thiếu usage.

### Điều tra aggregate variance

1. Chia theo ngày để xác định ngày bắt đầu lệch.
2. Chia theo model/SKU/region/service tier.
3. Kiểm tra retries, streaming disconnects và SDK-level retry.
4. Kiểm tra worker/background jobs ngoài HTTP request.
5. Kiểm tra provider proxy/gateway hoặc deployment alias.
6. Kiểm tra app event persistence và late arrivals.
7. Ghi phần còn lại là unattributed nếu không đủ evidence.

Nếu cần chargeback request-level, phân bổ aggregate variance theo policy. Báo cáo phải cho biết đó là allocation, không phải provider direct match.

## 26. Xử lý account-level discount và commitment

Discount có thể không gắn với một SKU cụ thể. Ví dụ provider áp dụng committed spend discount trên toàn account hoặc cấp credit vào cuối tháng.

Tách:

- Public/list rate estimate.
- Contract rate theo SKU/service.
- Account-level discount.
- Commitment fee hoặc unused commitment.
- Credit balance/credit memo.
- Net invoice.

Nếu hợp đồng đã có discounted unit rate, dùng contract rate trong provider gross estimate và không trừ lại discount lần nữa. Nếu discount chỉ xuất hiện ở invoice tổng, giữ thành adjustment cấp account và phân bổ riêng nếu business cần showback.

### Unused commitment

Committed spend có thể tạo chi phí cố định dù usage thấp hơn cam kết. Phần unused commitment không phải token usage của một request. Ghi thành fixed commercial cost, sau đó phân bổ theo project/tenant policy nếu cần.

## 27. Report cho kỹ thuật và tài chính

Hai nhóm cần góc nhìn khác nhau nhưng phải dùng cùng ledger và source references.

| Báo cáo kỹ thuật | Báo cáo tài chính/FinOps |
|---|---|
| Usage observed vs provider usage | Invoice gross/net |
| Cost per request/case/run | Actual spend theo account/project |
| Cost by model/operation | Cost by SKU/service/region |
| Missing usage events | Unattributed invoice lines |
| Retry/streaming/tool variance | Discount, credit, tax, fees |
| Cost per successful task | Budget, commitment, variance to forecast |
| Estimate confidence | Reconciliation status and approval |

### Những chỉ số nên theo dõi

- Application estimate / provider gross ratio.
- Usage capture coverage theo provider/SKU/unit.
- Unmatched billing amount.
- Unpriced usage amount.
- Variance absolute và relative.
- Variance theo category.
- Late-arriving usage volume.
- Duplicate/rejected billing rows.
- Tỷ lệ cost direct / aggregate / allocated.
- Số ngày từ billing period end đến close.

Đừng chỉ theo dõi tổng variance %. Một tỷ lệ nhỏ trên account lớn có thể là khoản tiền đáng kể; một tỷ lệ cao trên dịch vụ nhỏ có thể chỉ là rounding hoặc minimum fee.

## 28. Bảo vệ dữ liệu và phân quyền trong reconciliation

Billing exports có thể chứa account ID, project, contract SKU, negotiated rate, invoice number và thông tin thương mại nhạy cảm.

Nguyên tắc:

- Chỉ người có quyền FinOps/Finance mới đọc invoice và negotiated rates.
- Kỹ sư có thể xem normalized usage/variance đã được giới hạn theo project.
- Không đưa API keys, payment credentials hoặc raw request payload vào billing ledger.
- Giữ raw invoice/export ở storage có encryption, access logging và retention phù hợp.
- Tách PII/customer identity khỏi billing identifiers nếu không cần.
- Audit mọi lần export report, điều chỉnh và phê duyệt kỳ.

Không cần đưa prompt/completion vào reconciliation. Provider request ID, SKU, quantity, time bucket và cost owner thường đủ để ghép usage.

## 29. Bài thực hành: đối soát một tháng usage Spring AI

Chuẩn bị dữ liệu tổng hợp:

- Application usage events cho chat input/output, embedding, vector query và tool calls.
- Application estimate dùng price catalog có version.
- Provider billing export theo project/SKU/region/period.
- Invoice có discount, credit, tax và một fixed fee.
- Một số event timeout, retry hoặc đến muộn.

Thực hiện:

1. Import raw billing export với checksum và idempotency key.
2. Chuẩn hóa application usage và provider lines.
3. Ghép request-level bằng provider request ID khi có.
4. Ghép aggregate theo project/SKU/region/unit/period khi không có request ID.
5. Kiểm tra usage quantity trước khi so amount.
6. Tính gross usage variance và phân loại usage/rate/unit variance.
7. Tạo invoice bridge cho discount, credit, fixed fee và tax.
8. Đánh dấu unpriced/unmatched/allocated lines.
9. Chạy import lần hai và xác nhận không duplicate.
10. Nhập một correction/credit memo và tạo reconciliation revision.
11. Chốt report provisional rồi closed sau grace period.
12. Xuất hai view: kỹ thuật (cost per task/model) và tài chính (invoice by account/SKU).

### Câu hỏi tự kiểm

**Câu 1:** Application estimate 100 USD, invoice net 95 USD. Có thể kết luận app tính thừa 5 USD không?

Chưa. Invoice net có thể đã trừ discount/credit hoặc chưa gồm một khoản estimate phân bổ. So sánh application gross với provider gross trước, sau đó mới bridge commercial adjustments.

**Câu 2:** Provider billing export chỉ có usage theo SKU/tháng. Có thể phân bổ chính xác cho từng request không?

Không. Chỉ có thể đối soát ở aggregate scope; request-level allocation cần policy và phải được gắn nhãn allocated.

**Câu 3:** Request timeout trước khi nhận usage metadata. Có thể bỏ request khỏi cost report không?

Không nên bỏ. Ghi operation và provider request ID/status, đánh dấu usage pending/partial rồi đối chiếu provider usage/billing.

**Câu 4:** Invoice có một dòng discount cấp account. Có nên trừ đều discount vào từng model call?

Chỉ khi tổ chức định nghĩa allocation policy. Discount gốc vẫn là adjustment cấp account; phần chia cho request là allocated.

**Câu 5:** Import lại cùng billing export có được cộng lại amount không?

Không. Ingestion phải idempotent theo provider line/document revision; import lại cùng source không được tạo charge duplicate.

## 30. Checklist trước khi chốt reconciliation

- [ ] Phân biệt application estimate, provider usage export, billing export và invoice.
- [ ] So sánh cùng account/project, billing period, SKU, region, unit, currency và gross/net basis.
- [ ] Giữ raw source reference, checksum, parser version và import timestamp.
- [ ] Ingestion idempotent; duplicate/revision được nhận diện.
- [ ] Application usage có provider request ID/call ID khi nguồn cung cấp.
- [ ] Usage event late/timeout/streaming/batch có status riêng.
- [ ] Provider lines được normalize; field thiếu để null thay vì đoán.
- [ ] Usage variance được tính trước amount variance.
- [ ] Rate variance chỉ tính sau khi unit/scope khớp.
- [ ] Discount, credit, commitment, fixed fee, tax và FX được tách riêng.
- [ ] Shared cost có allocation policy/version/denominator.
- [ ] Direct, aggregate, allocated và unmatched được phân biệt.
- [ ] Matching confidence phản ánh chất lượng bằng chứng.
- [ ] Tolerance theo amount, quantity, timing và category được định nghĩa.
- [ ] Unpriced/unmatched variance được hiển thị, không đổi thành zero.
- [ ] Correction/credit memo tạo revision, không ghi đè lịch sử.
- [ ] Invoice net được đối chiếu với invoice document và period.
- [ ] Báo cáo provisional/closed được phân biệt.
- [ ] Có audit actor, source, rule version, explanation và approval.
- [ ] Báo cáo kỹ thuật và tài chính dùng chung nguồn reconciliation.

### Tài liệu tham khảo để triển khai

- OpenCost Specification: https://opencost.io/docs/specification/
- FinOps Framework: https://www.finops.org/framework/
- FinOps FOCUS Specification: https://focus.finops.org/
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/

**Kết luận:** application estimate giúp giải thích chi phí ở cấp request và pipeline; provider billing/invoice xác nhận usage và số tiền ở phạm vi mà nhà cung cấp hỗ trợ. Hãy đối chiếu usage trước, amount sau; tách gross usage khỏi discount, credit, tax và fixed fees; chỉ ghép request khi có bằng chứng. Với dữ liệu aggregate hoặc shared, ghi rõ allocation và confidence. Cách làm này giúp cost report vừa hữu ích cho kỹ thuật vừa có thể audit và đối soát với tài chính.
