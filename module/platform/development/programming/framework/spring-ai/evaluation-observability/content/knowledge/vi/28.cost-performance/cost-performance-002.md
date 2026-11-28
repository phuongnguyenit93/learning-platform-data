# Ước lượng chi phí từ usage với bảng giá có phiên bản

## 1. Vì sao phải quản lý bảng giá theo phiên bản?

Usage cho biết ứng dụng đã tiêu thụ bao nhiêu tài nguyên: input tokens, output tokens, cached tokens, số embedding items, số tool calls, read units hoặc GB lưu trữ. Usage tự nó chưa cho biết số tiền. Muốn ước lượng cost, cần ghép usage với đơn giá đúng nhà cung cấp, model, khu vực, loại dịch vụ, đơn vị billing và thời điểm phát sinh.

Một model có thể thay giá theo thời gian. Cùng một tên model có thể có giá khác theo region, deployment, batch mode, priority tier hoặc loại token. Provider cũng có thể thay cách tính cached input, reasoning tokens, image/audio units hoặc mức giá theo bậc. Nếu dùng một con số hiện tại để tính lại mọi request lịch sử, báo cáo sẽ sai lệch.

Trong module SPRING_AI_EVALUATION_OBSERVABILITY, bảng giá có phiên bản là nền tảng để so sánh prompt/model/pipeline qua nhiều lần evaluation. Nhóm cần trả lời được:

- Request đã tiêu thụ usage gì?
- Giá nào có hiệu lực tại thời điểm usage phát sinh?
- Phiên bản bảng giá nào đã được dùng để tính?
- Kết quả là actual, estimated, partial hay unknown?
- Khi invoice về, chênh lệch đến từ usage, giá, rounding, FX hay phí ngoài ứng dụng?

**Usage là dữ liệu đo; price catalog là dữ liệu định giá; cost event là kết quả tính có thể tái lập.** Ba loại dữ liệu cần lưu riêng và liên kết bằng ID/version.

### Kết quả học tập

Sau bài này, người học có thể:

1. Thiết kế price catalog có effective date, currency, unit và version bất biến.
2. Chuẩn hóa usage từ nhiều model/provider về một schema thống nhất.
3. Chọn đúng rate cho từng usage event tại thời điểm phát sinh.
4. Tính token cost, cached-token cost, embedding cost và non-token cost.
5. Xử lý batch pricing, tiered pricing, minimum charge, FX và rounding.
6. Lưu snapshot của price/rate được áp dụng để tái lập kết quả lịch sử.
7. Phân biệt estimated cost với actual invoice và thực hiện reconciliation.
8. Kiểm thử các trường hợp thiếu giá, trùng hiệu lực, đổi giá và usage bất thường.

## 2. Mô hình dữ liệu: usage, price và cost event

Không nên lưu duy nhất một trường totalCost trên request. Hãy phân biệt ba lớp:

| Lớp | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Usage event | Đã tiêu thụ bao nhiêu? | 2.500 input tokens, 400 output tokens |
| Price record | Một đơn vị được tính bao nhiêu trong khoảng thời gian nào? | 2 USD / 1 triệu input tokens, hiệu lực từ ngày X |
| Cost event | Usage này áp dụng rate nào và ra số tiền bao nhiêu? | 0,0082 USD, priceVersion 2026-11-v2 |

Quan hệ:

~~~mermaid
flowchart LR
    U["Usage event"] --> R["Rate resolver"]
    P["Versioned price catalog"] --> R
    C["Currency / FX table"] --> R
    R --> CE["Cost event + price snapshot"]
    CE --> L["Cost ledger"]
    I["Provider invoice / billing export"] --> REC["Reconciliation"]
    L --> REC
    REC --> REP["Variance report"]
~~~

Usage event nên bất biến sau khi đã chốt. Nếu provider gửi usage correction, ghi event điều chỉnh hoặc revision mới có quan hệ tới event gốc; không âm thầm ghi đè số đo đã dùng trong báo cáo.

Price record cũng cần bất biến theo version. Khi provider đổi giá, tạo record/version mới với ngày hiệu lực mới. Cost event lưu bản sao rate đã áp dụng để có thể tính lại hoặc audit ngay cả khi catalog được cập nhật sau này.

## 3. Định nghĩa đơn vị billing trước khi nhập giá

Đơn vị giá phải khớp chính xác với đơn vị usage. Không thể nhân token count với giá theo request, hoặc nhân GB-month với GB hiện tại mà bỏ qua thời gian lưu trữ.

| Nhóm | Đơn vị usage thường gặp | Ví dụ đơn giá |
|---|---|---|
| Chat input/output | token | USD / 1 triệu tokens |
| Cached input | cached token | USD / 1 triệu cached tokens |
| Embedding | token, item, request | USD / 1 triệu tokens hoặc USD / 1.000 items |
| Image | image, pixel bucket, resolution | USD / image hoặc tier |
| Audio | second, minute, audio token | USD / minute hoặc 1 triệu tokens |
| Reranking | query-document pair, request | USD / 1.000 pairs |
| Tool/API | request, transaction, record | USD / 1.000 calls |
| Vector database | read/write unit, operation | USD / 1 triệu units |
| Storage | GB-month, GiB-hour | USD / GB-month |
| Compute | vCPU-hour, GPU-hour, node-hour | USD / hour |
| Data transfer | GB transferred | USD / GB |

Catalog cần lưu đơn vị chuẩn hóa và hệ số quy đổi nếu provider dùng đơn vị khác. Ví dụ provider báo usage theo byte nhưng giá theo GB thập phân hoặc GiB nhị phân; phải ghi rõ cách quy đổi.

### Phân biệt token với request

Một request ChatModel có thể chứa nhiều tokens. Một request embedding có thể chứa nhiều inputs. Một batch API request có thể chứa hàng trăm items. Nếu nhà cung cấp tính theo token/item, không dùng số HTTP requests làm billable quantity.

Ngược lại, nếu API có phí cố định theo request cộng phí token, phải tạo hai charge components riêng để không bỏ sót phí request.

## 4. Price catalog cần có những trường nào?

Một rate record đủ dùng nên có:

| Trường | Ý nghĩa |
|---|---|
| priceVersion | Phiên bản catalog hoặc đợt cập nhật |
| provider | Nhà cung cấp/đối tác |
| product | Dịch vụ, ví dụ chat, embedding, rerank, vector DB |
| sku | Mã dịch vụ hoặc deployment SKU |
| model | Model/deployment alias nếu rate phụ thuộc model |
| region | Khu vực áp dụng |
| serviceTier | Standard, batch, priority hoặc tier hợp đồng |
| usageType | input, output, cached input, image, audio, request... |
| unit | Đơn vị billing |
| unitSize | Mẫu số của rate, ví dụ 1.000.000 tokens |
| unitPrice | Giá cho unitSize |
| currency | ISO 4217, ví dụ USD |
| effectiveFrom | Thời điểm bắt đầu hiệu lực |
| effectiveTo | Thời điểm hết hiệu lực, exclusive |
| source | URL/hợp đồng/billing document làm căn cứ |
| recordedAt | Thời điểm catalog ghi nhận rate |
| status | draft, approved, active, retired |

Các trường provider, product, sku, model, region, serviceTier, usageType, unit và thời điểm hiệu lực tạo nên phạm vi áp dụng của rate. Không chỉ lookup theo tên model.

### Ví dụ price record

~~~yaml
priceVersion: provider-a-2026-11-v2
rateId: chat-model-x-input-usd
provider: provider-a
product: chat
sku: model-x
model: model-x
region: global
serviceTier: standard
usageType: input_token
unit: token
unitSize: 1000000
unitPrice: 2.00
currency: USD
effectiveFrom: 2026-11-01T00:00:00Z
effectiveTo: null
recordedAt: 2026-11-03T09:30:00Z
source: https://provider.example/pricing
status: approved
~~~

URL ở ví dụ chỉ là placeholder minh họa schema. Catalog production phải trỏ đến pricing page, hợp đồng hoặc tài liệu billing thật đã được người có thẩm quyền xác nhận.

## 5. Version và thời gian hiệu lực là hai khái niệm khác nhau

priceVersion cho biết catalog snapshot nào đã được publish. effectiveFrom/effectiveTo cho biết rate áp dụng cho usage ở khoảng thời gian nào. recordedAt cho biết hệ thống biết rate đó từ khi nào.

Ví dụ:

| Price version | Effective period | Recorded at |
|---|---|---|
| catalog-2026-10 | 01/10 đến trước 15/11 | 01/10 |
| catalog-2026-11-a | 15/11 đến trước 01/12 | 17/11 |
| catalog-2026-11-b | 01/12 trở đi | 28/11 |

Nếu rate có hiệu lực từ ngày 15/11 nhưng nhóm chỉ ghi nhận thông báo ngày 17/11, usage ngày 16/11 vẫn cần áp dụng effective date 15/11 sau khi catalog được cập nhật. recordedAt hỗ trợ audit “lúc đó hệ thống đã biết gì”; effectiveFrom dùng để chọn giá cho usage.

### Hai cách báo cáo lịch sử

- **As-billed/as-known:** giữ cost event đã tính theo catalog được áp dụng lúc xử lý; không tự thay đổi kết quả cũ.
- **Restated:** tính lại lịch sử theo rate correction hoặc pricing policy được phê duyệt; tạo report/revision mới và ghi rõ lý do.

Không âm thầm sửa cost lịch sử khi provider cập nhật giá hoặc catalog được bổ sung. Báo cáo cũ phải có thể tái lập.

## 6. Quy tắc chọn rate có tính xác định

Khi một usage event đến, resolver cần tìm đúng rate:

1. Chuẩn hóa provider và SKU/model alias.
2. Xác định operation/product và usage type.
3. Xác định region, service tier, currency và billing unit.
4. Dùng occurredAt của usage để lọc effective period.
5. Chọn rate có scope cụ thể nhất trong các rate hợp lệ.
6. Nếu có nhiều rate ngang mức ưu tiên, báo ambiguity; không chọn ngẫu nhiên.
7. Lưu rateId, priceVersion, unit price và currency snapshot vào cost event.

### Ví dụ độ ưu tiên

Giả sử catalog có:

- Rate chung cho model X ở mọi region.
- Rate riêng cho model X ở region eu.
- Rate riêng cho model X, region eu, service tier batch.

Một usage event model X + eu + batch phải chọn rate có scope đầy đủ nhất nếu policy catalog quy định specificity như vậy. Không dựa vào thứ tự record trong file hoặc database query.

### Không tìm thấy rate

Nếu không có rate hợp lệ:

- Ghi usage event đầy đủ.
- Đặt cost status là unpriced hoặc unknown.
- Ghi rõ dimension nào thiếu hoặc không khớp.
- Phát cảnh báo để bổ sung catalog.
- Không dùng giá 0 vì điều đó biến “chưa biết giá” thành “miễn phí”.

## 7. Xử lý effective period và rate bị chồng lấn

Nên dùng khoảng thời gian nửa mở: effectiveFrom <= occurredAt < effectiveTo. effectiveTo = null nghĩa là chưa có ngày kết thúc.

Với cùng một scope (provider, sku, region, tier, usageType, unit), hai record active không được có effective period chồng lấn, trừ khi có một quy tắc tier/contract rõ ràng.

Ví dụ không hợp lệ:

| Rate | From | To |
|---|---|---|
| R1 | 01/11 00:00Z | 20/11 00:00Z |
| R2 | 15/11 00:00Z | 01/12 00:00Z |

Usage ngày 17/11 có thể khớp cả hai rate. Resolver không được chọn theo updatedAt hoặc record mới nhất. Catalog validation phải chặn overlap trước khi publish.

### Giá thay đổi giữa tháng

Nếu provider đổi rate ngày 15/11:

- Usage có occurredAt trước mốc hiệu lực dùng rate cũ.
- Usage từ mốc hiệu lực trở đi dùng rate mới.
- Usage event đến muộn vẫn dùng timestamp phát sinh thực tế nếu timestamp đáng tin cậy.
- Nếu invoice áp dụng mốc khác, reconciliation ghi variance và nguồn xác nhận.

## 8. Chuẩn hóa usage event từ nhiều provider

Provider có thể dùng tên trường khác nhau. Chuẩn hóa về một schema nội bộ, nhưng giữ raw provider response reference để audit khi được phép.

Ví dụ:

~~~yaml
usageEvent:
  usageEventId: use-000123
  occurredAt: 2026-11-27T10:15:30Z
  receivedAt: 2026-11-27T10:15:31Z
  owner:
    requestId: req-000456
    runId: eval-run-2026-11-27-a
    caseId: rag-return-014
    attemptId: 1
  operation:
    type: chat_generation
    callId: model-call-02
  resource:
    provider: provider-a
    sku: model-x
    model: model-x
    region: global
    serviceTier: standard
  usage:
    inputTokens: 2500
    outputTokens: 500
    cachedInputTokens: 300
    unit: token
  source:
    kind: response_metadata
    providerRequestId: vendor-req-abc
~~~

Schema này minh họa. Nếu provider báo cached tokens là phần nằm trong tổng input tokens, chuẩn hóa inputTokens thành uncached input hoặc giữ cả inputTokensTotal và cachedInputTokens với semantics rõ ràng. Không đoán semantics từ tên trường.

### Những thuộc tính không được bỏ

- occurredAt: thời điểm usage thực sự phát sinh.
- receivedAt: thời điểm ứng dụng nhận usage.
- providerRequestId: để đối soát provider nếu có.
- operationType và callId: tách các lần gọi trong một request.
- usageUnit: tránh cộng nhầm token với item hoặc request.
- usageSource: response metadata, provider usage API, invoice hoặc estimate.
- completeness: complete, partial, missing hoặc corrected.

Không ghi API key, authorization header, raw prompt hoặc tool payload vào usage event.

## 9. Chuẩn hóa token usage đúng semantics

Token fields cần định nghĩa rõ:

| Field | Ý nghĩa |
|---|---|
| inputTokensTotal | Tổng input tokens theo định nghĩa provider |
| cachedInputTokens | Phần input được billing theo cached rate |
| uncachedInputTokens | Input tokens tính theo standard input rate |
| outputTokens | Output tokens theo định nghĩa provider |
| reasoningTokens | Token reasoning nếu provider báo riêng và billing tách riêng |
| totalTokens | Tổng theo semantics provider; không nhất thiết là tổng các billable buckets |

Nếu inputTokensTotal bao gồm cached input:

\[
T_{\mathrm{uncached}} =
\max(0, T_{\mathrm{input,total}} - T_{\mathrm{cached}})
\]

Nếu provider đã báo uncachedInputTokens riêng, dùng trực tiếp giá trị đó và kiểm tra tổng nhất quán. Không trừ cached hai lần.

Một số provider gộp reasoning tokens trong output tokens, một số khác báo riêng. Chỉ thêm một charge component riêng khi bảng giá của provider thực sự tính riêng; nếu reasoning đã nằm trong output rate, cộng thêm sẽ double-count.

### Kiểm tra tính hợp lệ

- Usage không được âm.
- Cached tokens không vượt input total nếu semantics nói cached là subset.
- Total tokens phải khớp quy tắc provider, không ép mọi provider dùng cùng công thức.
- Token usage thiếu phải là null/partial, không tự gán 0.
- Một response retry có provider request ID riêng cần một usage event riêng.

## 10. Tính giá cho input, output và cached tokens

Giả sử price catalog dùng USD cho mỗi một triệu tokens:

\[
C_{\mathrm{chat}} =
\frac{
T_{\mathrm{uncached}}P_{\mathrm{input}} +
T_{\mathrm{cached}}P_{\mathrm{cached}} +
T_{\mathrm{output}}P_{\mathrm{output}}
}{1{,}000{,}000}
\]

Nếu provider không có cached rate riêng, dùng policy được công bố trong catalog (thường cached được tính như input hoặc không áp dụng); không tự suy ra.

Ví dụ giả định:

| Bucket | Usage | Rate / 1M tokens | Cost |
|---|---:|---:|---:|
| Uncached input | 2.200 | 2,00 USD | 0,004400 USD |
| Cached input | 300 | 0,50 USD | 0,000150 USD |
| Output | 500 | 8,00 USD | 0,004000 USD |
| **Total** | | | **0,008550 USD** |

Các đơn giá trên chỉ là số giả định để minh họa. Khi áp dụng thực tế, phải lấy rate từ catalog đã phê duyệt và có nguồn.

## 11. Model calls, retries và streaming

Mỗi lần gọi model cần một usage event riêng. Một request có thể:

- Gọi model để phân loại/routing.
- Gọi model tạo tool call.
- Gọi model tiếp sau tool result.
- Retry do timeout/rate limit.
- Gọi fallback model sau lỗi.

Tổng cost của request là tổng charge components của mọi provider call đã phát sinh, kể cả call lỗi nếu provider tính phí. Nếu provider không tính phí cho request bị từ chối trước khi inference, usage/invoice reconciliation sẽ xác nhận.

Với streaming, usage có thể chỉ xuất hiện ở terminal chunk hoặc response metadata cuối. Nếu client disconnect trước khi nhận usage, event có thể ở trạng thái `partial` dù provider đã xử lý một phần hoặc toàn bộ request. Khi có provider usage endpoint/billing export, reconciliation có thể bổ sung số liệu.

Không tạo usage event cuối cùng từ một token counter phía client nếu provider đã cung cấp usage chính thức. Client-side estimation chỉ nên ghi riêng là estimate và không ghi đè provider usage.

## 12. Ví dụ catalog có nhiều loại giá

Một model có thể có nhiều rate records cùng price version:

~~~yaml
priceVersion: provider-a-2026-11-v2
currency: USD
rates:
  - rateId: model-x-input-standard
    sku: model-x
    serviceTier: standard
    usageType: input_token
    unit: token
    unitSize: 1000000
    unitPrice: 2.00
    effectiveFrom: 2026-11-01T00:00:00Z
    effectiveTo: null
  - rateId: model-x-output-standard
    sku: model-x
    serviceTier: standard
    usageType: output_token
    unit: token
    unitSize: 1000000
    unitPrice: 8.00
    effectiveFrom: 2026-11-01T00:00:00Z
    effectiveTo: null
  - rateId: model-x-input-batch
    sku: model-x
    serviceTier: batch
    usageType: input_token
    unit: token
    unitSize: 1000000
    unitPrice: 1.00
    effectiveFrom: 2026-11-01T00:00:00Z
    effectiveTo: null
~~~

Catalog này chỉ minh họa cấu trúc. Production catalog cần các field scope còn lại, nguồn giá, phê duyệt, region và kiểm tra overlap.

## 13. Pricing theo bậc (tiered pricing)

Một số dịch vụ áp dụng rate khác nhau theo tổng usage trong một kỳ billing:

| Monthly usage range | Rate giả định |
|---|---:|
| 0–1 triệu units | 1,00 USD / 1.000 units |
| Trên 1–10 triệu units | 0,80 USD / 1.000 units |
| Trên 10 triệu units | 0,60 USD / 1.000 units |

Có hai kiểu tier thường gặp:

- **Graduated/marginal:** mỗi phần usage nằm trong một bậc chịu rate của bậc đó.
- **Volume:** toàn bộ usage trong kỳ được áp rate của bậc đạt được.

Không thể chọn công thức nếu chưa đọc pricing terms. Catalog cần lưu `tierMode`, ngưỡng, kỳ reset, scope (account/project/tenant) và timezone/cutoff.

Ví dụ graduated với 1,5 triệu units:

\[
C = 1{,}000{,}000 \times \frac{1.00}{1000}
+ 500{,}000 \times \frac{0.80}{1000}
= 1{,}400\ \mathrm{USD}
\]

Nếu là volume pricing, phép tính có thể khác hoàn toàn. Không suy diễn từ bảng giá có nhiều dòng; xác nhận điều khoản billing.

## 14. Batch pricing, commitment và discount

Giá batch có thể thấp hơn standard nhưng thường đi kèm SLA/processing time khác. Catalog cần phân biệt service tier và điều kiện đủ chuẩn.

Discount/commitment có thể được áp dụng ở:

- Unit price trước khi tính.
- Tổng invoice sau usage.
- Credit balance hoặc committed spend.
- Volume tier theo kỳ.
- Contract-specific discount theo project.

Không trừ discount chung vào từng request nếu provider chỉ áp dụng ở cấp invoice. Hãy lưu:

- Gross usage cost.
- Discount/credit/commitment adjustment.
- Net billed cost.

Điều này cho phép phân tích cost kỹ thuật theo rate list và cost tài chính theo số tiền thực trả.

## 15. Embedding, image và audio pricing

Không mặc định mọi model API đều tính theo text token.

### Embedding

Embedding provider có thể tính theo input tokens, số items hoặc batch. Rate phải ghi rõ model embedding, dimensions nếu ảnh hưởng billing, region và service tier.

### Image

Image usage có thể phụ thuộc số ảnh, resolution, patch/tile hoặc image tokens do provider định nghĩa. Không đổi pixel sang text tokens bằng một hệ số tự đặt.

### Audio

Audio có thể tính theo giây/phút, audio tokens, input/output modality hoặc transcription characters. Tách speech-to-text, audio understanding và text-to-speech nếu có rate khác nhau.

### Video/realtime

Realtime/video có thể có nhiều stream units và modality buckets. Dùng usage report của provider và tạo rate type riêng. Nếu chưa có usage mapping, đánh dấu unpriced/partial thay vì giả định tất cả nằm trong chat tokens.

## 16. Định giá tool, vector database và compute

Không phải usage nào cũng là token. Các dịch vụ hạ tầng thường tính theo đơn vị riêng và có thể có minimum, tier hoặc capacity reservation.

| Dịch vụ | Usage cần thu | Cách tính thường gặp |
|---|---|---|
| Tool/API | số request, records, transactions, billable operation | quantity × unit price |
| Vector DB query | read units, query units, compute time | units × rate hoặc capacity-hour |
| Vector DB write | write units, vectors inserted/updated | units × rate |
| Vector storage | GB/GiB trung bình theo thời gian | GB-month × rate |
| App compute | vCPU-hour, memory GB-hour | resource-hours × rate |
| GPU inference | GPU seconds/hours, accelerator type | GPU-hours × rate |
| Network | GB egress, inter-zone transfer | GB × rate theo route |
| Telemetry | spans/log GB ingested, retention GB-day | ingest/storage units × rate |

### Storage phải tính theo thời gian

Nếu giá là USD/GB-month và usage là GB-hours, có thể quy đổi theo quy tắc của provider:

\[
C_{\mathrm{storage}} =
\frac{\mathrm{GB\ hours}}{\mathrm{hours\ in\ billing\ month}}
\times P_{\mathrm{GB-month}}
\]

Không luôn dùng 720 giờ nếu provider tính theo số ngày thực của tháng hoặc average daily storage. Catalog phải mô tả cách tính chính thức.

### Tool subscription và minimum charges

Nếu tool/API có monthly subscription hoặc minimum spend, phần đó là fixed/shared cost. Không phân bổ tất cả vào từng request như thể provider tính per-call. Báo riêng:

- Fixed subscription/committed capacity.
- Variable usage cost.
- Overage cost.
- Credit/discount adjustment.

## 17. Currency, FX và thời điểm quy đổi

Một hệ thống có thể nhận invoice bằng USD, EUR hoặc VND, trong khi dashboard quản trị muốn hiển thị một reporting currency. Không nên đổi currency ngay khi ingest usage và vứt bỏ giá trị gốc.

Lưu:

- Original amount.
- Original currency.
- FX rate.
- FX source/provider.
- FX effective timestamp hoặc fixing date.
- Reporting currency.
- Converted amount.

Ví dụ:

| Trường | Giá trị minh họa |
|---|---|
| Original amount | 12,50 |
| Original currency | USD |
| FX rate | 25.000 VND / USD |
| FX date | 2026-11-27 |
| Reporting currency | VND |
| Converted amount | 312.500 VND |

FX rate trên chỉ là ví dụ giả định. Trong báo cáo tài chính, dùng nguồn FX và chính sách ngày quy đổi được tổ chức phê duyệt. Có thể dùng transaction date, invoice date hoặc month-end rate; lựa chọn này phải nhất quán và được ghi lại.

Không dùng tỷ giá hiện tại để tính lại mọi giao dịch lịch sử nếu mục tiêu là actual historical spend. Nếu cần normalized comparison theo FX hiện tại, tạo một view riêng và giữ original amount.

## 18. Rounding, precision và minimum charge

Chi phí token có thể rất nhỏ. Nếu làm tròn từng call xuống hai chữ số thập phân, hàng nghìn call giá nhỏ có thể bị ghi thành 0.

Khuyến nghị:

- Lưu usage bằng số nguyên hoặc decimal chính xác theo provider.
- Lưu unit price bằng decimal, không dùng binary floating point để tính tiền.
- Tính cost với precision đủ cao (ví dụ 8–12 chữ số thập phân tùy currency/scale).
- Chỉ làm tròn ở ranh giới báo cáo/invoice theo chính sách.
- Giữ unrounded amount và rounded amount riêng khi cần đối soát.
- Ghi rounding mode và currency scale.

### Ví dụ

Một call có cost 0,000004 USD. Nếu làm tròn từng call đến cent, kết quả là 0,00 USD. Một nghìn call sẽ thành 0,00 USD nếu cộng các giá trị đã làm tròn, trong khi tổng chính xác là 0,004 USD.

Vì vậy:

1. Tính từng cost event ở precision cao.
2. Cộng các event theo kỳ/cost owner.
3. Làm tròn tổng theo chính sách reporting.
4. Đối chiếu với invoice, nơi provider có thể áp dụng rounding hoặc minimum khác.

Nếu provider có minimum charge, fixed request fee hoặc minimum billable unit, encode thành charge component riêng. Không tự ép usage thấp nhất thành một token nếu hợp đồng tính theo request.

## 19. Thuế, credits và điều chỉnh invoice

Giá list chưa chắc bằng số tiền phải trả. Invoice có thể có:

- Tax/VAT/GST.
- Credits hoặc promotional balance.
- Contractual discount.
- Commitment/annual reservation.
- Overage.
- Currency conversion fee.
- Minimum spend hoặc support plan.
- Điều chỉnh usage sau kỳ.

Giữ riêng ba lớp:

| Lớp | Ý nghĩa |
|---|---|
| Gross usage cost | Usage × list/contract rate |
| Commercial adjustments | Discount, credit, commitment, minimum, surcharge |
| Invoice total | Net amount + tax/fees theo invoice |

Không phân bổ tax hoặc discount theo request nếu chưa có policy kế toán. Có thể phân bổ theo gross usage share để showback, nhưng phải ghi rõ đây là allocated financial cost.

## 20. Thiết kế price catalog bất biến và có quy trình phê duyệt

Price catalog là dữ liệu vận hành có ảnh hưởng trực tiếp đến báo cáo tài chính. Nên quản lý như một artifact có version:

1. Thu thập pricing source chính thức hoặc hợp đồng.
2. Chuẩn hóa provider, SKU, unit, currency và scope.
3. Ghi effective period và recorded time.
4. Validate schema, overlap, missing dimensions và tier rules.
5. Review bởi owner kỹ thuật/tài chính.
6. Publish version bất biến.
7. Resolver chỉ đọc catalog ở trạng thái approved/active.
8. Ghi priceVersion/rateId vào từng cost event.

### Lifecycle gợi ý

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Validated
    Validated --> Approved
    Validated --> Draft: Validation failed
    Approved --> Active: Effective date reached
    Active --> Retired: Replaced by new version
    Retired --> [*]
~~~

Không sửa trực tiếp một version đã publish. Nếu phát hiện lỗi, tạo correction version hoặc adjustment event có liên kết version gốc.

### Phân quyền

- Người nhập giá không nhất thiết có quyền publish.
- Người duyệt xác nhận nguồn, đơn vị, currency và ngày hiệu lực.
- Resolver chỉ đọc version approved.
- Mọi thay đổi phải có audit actor, timestamp, reason và source.
- Export báo cáo phải lưu catalog version được dùng.

## 21. Bảo đảm resolver chọn rate đúng

Resolver không nên là một câu SQL chọn dòng đầu tiên. Nó cần xác minh scope, effective time, unit và status.

Pseudocode:

~~~text
resolve(usageEvent):
  validate usageEvent dimensions and unit
  candidates = catalog rates where:
    status is approved or active
    provider/product/sku match
    usageType and unit match
    region/tier match exact or allowed wildcard
    effectiveFrom <= occurredAt
    effectiveTo is null or occurredAt < effectiveTo

  if candidates is empty:
    return UNPRICED

  sort candidates by explicit specificity policy

  if top candidates have equal specificity:
    return AMBIGUOUS_RATE

  return selected rate with catalog version snapshot
~~~

### Wildcard phải được định nghĩa rõ

Catalog có thể cho phép region = global hoặc tier = any. Nhưng wildcard không tự động luôn có ưu tiên thấp nhất nếu hợp đồng có override. Xác định precedence trong policy, ví dụ exact region trước global; exact tier trước standard fallback; contract SKU trước public SKU.

Nếu hai records có cùng specificity, resolver phải dừng với lỗi ambiguity. Không lấy record có ID lớn hơn hoặc createdAt mới hơn để “chọn cho chạy”.

## 22. Tính cost bằng decimal và lưu snapshot rate

Trong Java, dùng BigDecimal cho phép tính tiền. Tránh double/float vì số thập phân như 0.1 không luôn biểu diễn chính xác ở binary floating point.

Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

record TokenUsage(
        long uncachedInput,
        long cachedInput,
        long output) {}

record TokenRates(
        BigDecimal inputPerMillion,
        BigDecimal cachedPerMillion,
        BigDecimal outputPerMillion) {}

BigDecimal tokenCost(TokenUsage usage, TokenRates rates) {
    BigDecimal million = new BigDecimal("1000000");

    BigDecimal input = BigDecimal.valueOf(usage.uncachedInput())
            .multiply(rates.inputPerMillion());
    BigDecimal cached = BigDecimal.valueOf(usage.cachedInput())
            .multiply(rates.cachedPerMillion());
    BigDecimal output = BigDecimal.valueOf(usage.output())
            .multiply(rates.outputPerMillion());

    return input.add(cached).add(output).divide(million, 12, RoundingMode.HALF_EVEN);
}
~~~

Đoạn code là ví dụ rút gọn. Production code còn cần validate usage, null rates, currency consistency, effective period, provider semantics, pricing tier và minimum charge. Không thay rate bị thiếu bằng BigDecimal.ZERO.

### Cost event nên snapshot những gì?

~~~yaml
costEvent:
  costEventId: cost-000123
  usageEventId: use-000123
  calculationVersion: cost-engine-2.1.0
  priceVersion: provider-a-2026-11-v2
  rateSnapshots:
    - rateId: model-x-input-standard
      usageType: input_token
      quantity: 2200
      unit: token
      unitSize: 1000000
      unitPrice: 2.00
      currency: USD
      amountUnrounded: 0.004400000000
  total:
    amountUnrounded: 0.008550000000
    currency: USD
    amountRounded: 0.00855
  status: estimated
~~~

Snapshot giúp tái lập cost mà không cần đoán catalog version từ thời gian hiện tại. Có thể lưu rateId cùng các field đã áp dụng để audit độc lập.

## 23. Lưu trữ price catalog và ràng buộc dữ liệu

Trong relational database, một mô hình đơn giản có thể gồm:

| Bảng | Nội dung |
|---|---|
| price_catalog_version | version, status, createdAt, approvedAt, source batch |
| price_rate | scope, unit, rate, currency, effectiveFrom/to |
| usage_event | owner, operation, provider resource, usage dimensions |
| cost_event | calculation status, total, currency, engine version |
| cost_component | rate snapshot, quantity, unit price, amount |
| fx_rate | base/quote currency, rate, source, effective date |
| invoice_line | provider invoice reference, SKU, quantity, amount |
| reconciliation_item | linked usage/cost/invoice, variance, reason |

Ràng buộc nên có:

- Unique key cho rate ID trong catalog version.
- Foreign key từ cost component đến usage event và rate/catalog snapshot.
- Check constraint cho usage >= 0 và unitSize > 0.
- Currency theo mã ISO 4217.
- Effective interval hợp lệ: from < to nếu to có giá trị.
- Không overlap các rate cùng scope theo policy.
- Không publish version chưa validated/approved.

Một unique index đơn giản không luôn đủ để cấm temporal overlap. Có thể cần exclusion constraint nếu database hỗ trợ range types, hoặc validation transaction trước publish để bảo đảm không có hai writer tạo overlap đồng thời.

## 24. Estimate status và độ tin cậy của cost

Không phải cost event nào cũng có đủ usage và price. Hãy biểu diễn mức độ hoàn chỉnh:

| Status | Ý nghĩa | Có cộng vào total chính thức? |
|---|---|---|
| actual | Đối soát được với invoice/provider billing | Có, theo reporting policy |
| estimated | Usage đủ, rate có nguồn nhưng chưa invoice | Có thể, nhưng phải gắn nhãn estimate |
| partial | Chỉ tính được một số components | Không được trình bày như total đầy đủ |
| unpriced | Có usage nhưng không tìm được rate | Không; hiển thị missing amount |
| unknown | Thiếu usage hoặc không xác định được semantics | Không |
| corrected | Có adjustment/revision thay event cũ | Tùy revision được chọn |

### Coverage quan trọng hơn một total đẹp

Ví dụ cost estimate 0,10 USD nhưng chỉ có 70% components được định giá. Báo cáo phải hiển thị:

- Priced coverage: 70% theo số event, usage hoặc spend basis đã định nghĩa.
- Unpriced components: vector DB, tool API.
- Estimated components: chat usage.
- Actual components: invoice usage đã đối soát.

Không dùng coverage percentage nếu chưa định nghĩa mẫu số. Coverage theo số event khác coverage theo usage hoặc coverage theo expected spend.

## 25. Reconciliation với provider billing

Cost engine tạo estimate theo request; provider invoice thường là nguồn xác nhận số tiền tính phí. Reconciliation giúp tìm sai lệch.

Quy trình:

1. Import billing export/invoice line vào staging.
2. Chuẩn hóa provider SKU, project, region, service tier, unit, period và currency.
3. Ghép usage ledger theo provider request ID nếu provider cung cấp.
4. Nếu không có request ID, ghép theo SKU/region/time bucket/project.
5. So sánh usage quantity và gross amount.
6. Phân loại variance.
7. Ghi adjustment event; không sửa usage event gốc.
8. Publish reconciliation report theo invoice period.

### Các nhóm variance

| Variance | Nguyên nhân có thể |
|---|---|
| Usage variance | Thiếu streaming usage, retry, async call, provider-side processing |
| Rate variance | Giá hiệu lực khác, contract discount, tier |
| Unit variance | Token vs item, GB vs GiB, request fee |
| FX variance | Ngày/tỷ giá khác |
| Rounding variance | Precision/rounding theo từng line hoặc invoice |
| Tax/fee variance | VAT, surcharge, support plan |
| Timing variance | Usage phát sinh cuối kỳ nhưng invoice ghi kỳ khác |
| Unattributed variance | Usage không có request mapping hoặc SKU chưa nhận diện |

### Ví dụ đối soát

| Khoản | Cost engine | Invoice | Variance |
|---|---:|---:|---:|
| Model usage | 120,00 USD | 121,20 USD | +1,20 USD |
| Embedding | 10,00 USD | 10,00 USD | 0 |
| Tool API | 5,00 USD | 5,50 USD | +0,50 USD |
| **Tổng** | **135,00 USD** | **136,70 USD** | **+1,70 USD** |

Số liệu giả định. Điều tra model variance theo cached tokens, retry, tier/region, price effective date và rounding. Tool variance có thể đến từ request bị timeout nhưng provider vẫn tính phí hoặc minimum billing.

## 26. Thay đổi giá mà không phá lịch sử

Khi provider thông báo giá mới:

1. Tạo price catalog version mới.
2. Giữ nguyên version cũ và effective period cũ.
3. Nhập rate mới cùng source và ngày hiệu lực.
4. Kiểm tra overlap và gap.
5. Review khác biệt trước/sau.
6. Phê duyệt rồi publish.
7. Chọn version mới cho usage có occurredAt trong effective period.
8. Không sửa cost events đã chốt; nếu cần restatement, tạo revision mới.

### Báo cáo trước và sau ngày đổi giá

Một dashboard có thể hiển thị:

- Actual/estimated cost theo rate đã áp dụng lúc phát sinh.
- Normalized cost nếu toàn bộ usage được tính theo catalog mới nhất.
- Delta do thay đổi usage.
- Delta do thay đổi price.

Hai cách nhìn trả lời câu hỏi khác nhau. Actual historical cost phục vụ tài chính; normalized cost giúp so sánh hiệu quả kỹ thuật khi rate thay đổi.

## 27. Ngăn lỗi định giá phổ biến

| Lỗi | Hậu quả | Kiểm soát |
|---|---|---|
| Chọn rate hiện tại cho usage lịch sử | Sai cost theo kỳ | Effective period và price snapshot |
| Lookup chỉ theo model name | Nhầm region/tier/deployment | Match đầy đủ scope |
| Cached tokens bị tính hai lần | Overestimate | Chuẩn hóa subset semantics |
| Reasoning tokens cộng vào output dù đã bao gồm | Double-count | Theo billing semantics |
| Missing rate đổi thành 0 | Underestimate | Unpriced status và alert |
| Làm tròn từng call quá sớm | Tổng cost bị thấp | Precision cao, round ở reporting boundary |
| Dùng float/double | Sai số thập phân | BigDecimal/decimal |
| Tiered pricing tính sai mode | Sai hóa đơn | Lưu graduated/volume terms |
| Invoice discount phân bổ tùy tiện | Sai chargeback | Tách gross, adjustment và net |
| FX dùng tỷ giá hiện tại cho lịch sử | Sai reporting | Lưu FX source/date/rate |
| Reprice lịch sử âm thầm | Không audit được | Immutable version và restatement |
| Usage thiếu nhưng mặc định 0 | Che khuất dữ liệu thiếu | completeness/status rõ ràng |

## 28. Kiểm thử price catalog và cost resolver

Không chỉ test công thức happy path. Phần dễ gây sai tiền thường là chọn rate, hiệu lực thời gian, unit, tier và rounding.

### Ma trận kiểm thử

| Case | Input | Kết quả mong đợi |
|---|---|---|
| Exact scope | Model/region/tier khớp | Chọn đúng rate cụ thể |
| Global fallback | Không có region-specific rate | Chọn global nếu policy cho phép |
| Effective boundary | occurredAt đúng effectiveFrom | Rate mới có hiệu lực |
| Exclusive end | occurredAt đúng effectiveTo | Không dùng rate cũ |
| Overlap | Hai rate cùng scope cùng hiệu lực | Publish fail hoặc resolver ambiguity |
| Gap | Không có rate tại thời điểm usage | Unpriced |
| Unknown model | SKU chưa catalog | Unpriced, không cost 0 |
| Cached subset | Cached là phần của input total | Trừ đúng một lần |
| Negative usage | Token count âm | Validation fail |
| Tiered graduated | Usage đi qua nhiều bậc | Tính từng phần theo rate |
| Tiered volume | Đạt một bậc | Áp đúng volume policy |
| Currency | USD usage, reporting VND | FX source/date được lưu |
| Rounding | Nhiều event nhỏ | Cộng precision cao trước khi round |
| Retry | Nhiều provider request IDs | Mỗi attempt là usage event riêng |
| Correction | Provider gửi usage revised | Tạo adjustment/revision liên kết event gốc |

### Unit test công thức BigDecimal

~~~java
@Test
void calculatesTokenBucketsWithoutRoundingEachCall() {
    TokenUsage usage = new TokenUsage(2200, 300, 500);
    TokenRates rates = new TokenRates(
            new BigDecimal("2.00"),
            new BigDecimal("0.50"),
            new BigDecimal("8.00"));

    BigDecimal cost = tokenCost(usage, rates);

    assertThat(cost).isEqualByComparingTo("0.008550000000");
}
~~~

Test này minh họa công thức cho ba buckets. Production tests cần thêm provider usage adapter, price resolver, tier calculation, FX và invoice reconciliation.

## 29. Ví dụ đầy đủ: định giá một request có nhiều hoạt động

Giả sử một request trong evaluation run thực hiện:

1. Query embedding: 40 tokens.
2. Vector query: 1 operation.
3. ChatModel call đầu: 1.800 uncached input, 200 cached input, 120 output tokens.
4. Tool read-only: 1 billable API call.
5. ChatModel follow-up: 2.200 uncached input, 300 output tokens.
6. Judge call: 1.500 input, 200 output tokens.

Giả sử price catalog minh họa:

| Rate | Đơn giá giả định |
|---|---:|
| Chat uncached input | 2,00 USD / 1M tokens |
| Chat cached input | 0,50 USD / 1M tokens |
| Chat output | 8,00 USD / 1M tokens |
| Query embedding | 0,10 USD / 1M tokens |
| Judge input | 1,00 USD / 1M tokens |
| Judge output | 4,00 USD / 1M tokens |
| Vector query | 0,0002 USD / operation |
| Tool API | 0,001 USD / call |

Generation chat:

\[
C_{\mathrm{chat}} =
\frac{(1800+2200)\times2 + 200\times0.5 + (120+300)\times8}
{1{,}000{,}000}
= 0.01146\ \mathrm{USD}
\]

Query embedding:

\[
C_{\mathrm{embedding}} = 40 \times 0.10 / 1{,}000{,}000
= 0.000004\ \mathrm{USD}
\]

Judge:

\[
C_{\mathrm{judge}} =
(1500\times1 + 200\times4)/1{,}000{,}000
= 0.0023\ \mathrm{USD}
\]

Vector query + tool:

\[
C_{\mathrm{non-token}} = 0.0002 + 0.001 = 0.0012\ \mathrm{USD}
\]

Tổng phần đã có rate:

\[
C_{\mathrm{priced}} = 0.01146 + 0.000004 + 0.0023 + 0.0012
= 0.014964\ \mathrm{USD}
\]

Tổng trên vẫn có thể là estimated nếu chưa đối soát invoice. Document-ingest allocation, infrastructure, observability và tax chưa được đưa vào ví dụ; phải hiển thị rõ phần chưa tính.

## 30. Bài thực hành: xây price catalog có version

Hãy xây một catalog nhỏ cho một pipeline Spring AI gồm chat model, embedding model, vector store và một tool API.

1. Tạo version đầu tiên với nguồn giá chính thức/hợp đồng và ngày hiệu lực.
2. Tạo rate records riêng cho input, output, cached input và embedding.
3. Tạo rate theo request/unit cho vector query và tool API.
4. Chuẩn hóa usage events từ response metadata/provider.
5. Implement resolver có exact scope, global fallback và effective period.
6. Tạo cost events có rate snapshot và calculation version.
7. Tính tổng cost theo request, case và evaluation run.
8. Tạo catalog version mới với rate thay đổi giữa kỳ.
9. Replay usage events trước/sau mốc đổi giá và xác nhận rate được chọn đúng.
10. Tạo một rate overlap và xác nhận catalog validation từ chối.
11. Tạo một SKU không có giá và xác nhận status unpriced, không phải zero.
12. Import invoice giả lập và ghi reconciliation variance.
13. Xuất báo cáo actual/estimated/partial cùng coverage.

### Câu hỏi tự kiểm

**Câu 1:** Usage event phát sinh ngày 14/11, nhưng giá mới được ghi vào catalog ngày 17/11 và có hiệu lực từ 15/11. Nên chọn rate nào?

Nếu thông báo và effective date được xác minh hợp lệ, usage ngày 14/11 vẫn dùng rate cũ. Usage từ 15/11 dùng rate mới, dù catalog chỉ được ghi nhận ngày 17/11.

**Câu 2:** Không tìm thấy rate cho một SKU. Có nên ghi cost bằng 0 để dashboard không trống?

Không. Ghi unpriced/unknown và báo coverage; zero có nghĩa là đã xác nhận miễn phí.

**Câu 3:** Cached input tokens đã nằm trong input total. Cần làm gì trước khi tính?

Tách uncached input bằng cách trừ cached đúng một lần hoặc dùng bucket semantics provider đã báo riêng.

**Câu 4:** Provider áp dụng volume tier cho toàn bộ usage của tháng. Có thể tính từng request bằng graduated marginal rates không?

Không. Cần tính theo volume pricing terms và có thể phân bổ adjustment sau khi chốt kỳ.

**Câu 5:** Vì sao cost event cần lưu priceVersion và rate snapshot?

Để tái lập số tiền, audit rate đã dùng và bảo vệ báo cáo lịch sử khi catalog thay đổi.

## 31. Checklist trước khi publish một bảng giá

- [ ] Có source chính thức/hợp đồng và người xác nhận.
- [ ] Provider, product, SKU/model, region và service tier được chuẩn hóa.
- [ ] Usage type, unit và unit size khớp dữ liệu usage.
- [ ] Currency được lưu theo ISO 4217.
- [ ] Effective period dùng timezone rõ ràng và khoảng thời gian không mơ hồ.
- [ ] Không có rate overlap trong cùng scope trừ khi tier/contract policy định nghĩa.
- [ ] Graduated/volume pricing được phân biệt.
- [ ] Cached/reasoning/image/audio token semantics được xác nhận.
- [ ] Minimum charge, request fee, discount, commitment và tax được tách đúng lớp.
- [ ] Resolver có quy tắc specificity/wildcard xác định.
- [ ] Missing rate thành unpriced, không thành zero.
- [ ] Cost engine dùng decimal và rounding policy được công bố.
- [ ] FX có source, effective date và original amount.
- [ ] Cost event snapshot priceVersion, rateId và calculationVersion.
- [ ] Catalog version đã validate, review và approve trước khi active.
- [ ] Lịch sử không bị ghi đè khi provider đổi giá.
- [ ] Có unit tests cho boundary, overlap, gap, tier, cached usage và retry.
- [ ] Có reconciliation với provider billing/invoice.
- [ ] Report phân biệt actual, estimated, partial, unpriced và unknown.

### Tài liệu chính thức để đối chiếu

- Spring AI Chat Models: https://docs.spring.io/spring-ai/reference/api/chatmodel.html
- Spring AI Embeddings: https://docs.spring.io/spring-ai/reference/api/embeddings.html
- Spring AI Observability: https://docs.spring.io/spring-ai/reference/observability/
- OpenTelemetry GenAI semantic conventions: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- Java BigDecimal API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html

**Kết luận:** một cost estimate chỉ đáng tin khi usage semantics, rate scope, effective time, currency và cách làm tròn đều rõ ràng. Giữ catalog bất biến theo version, lưu snapshot rate trên từng cost event và đối soát với invoice. Nhờ vậy, nhóm có thể giải thích vì sao một request hoặc evaluation run tốn tiền, so sánh lịch sử công bằng và cập nhật giá mà không làm mất khả năng audit.
