# Đánh giá chi phí lưu trữ log, metric và trace

Khi ứng dụng Spring AI tăng traffic, chi phí observability có thể tăng nhanh dù chi phí gọi model không đổi. Mỗi request tạo log, span và metric; một thay đổi nhỏ như thêm `request_id` vào label metric có thể làm số time series tăng đột biến. Log được index để tìm kiếm nhanh thường tốn nhiều dung lượng hơn kích thước event ban đầu. Trace có nhiều span, còn hệ thống metrics có thể giữ hàng triệu mẫu mỗi ngày.

Muốn kiểm soát chi phí, cần biết dữ liệu nào đang được tạo, tốc độ ingest, kích thước sau nén, chi phí index, số bản sao, thời hạn lưu và tần suất truy vấn. Không thể chỉ lấy kích thước file log nhân số ngày retention để dự báo toàn bộ chi phí.

Sau bài học, bạn có thể:

- Ước tính dung lượng log, metric và trace từ traffic và cấu hình instrumentation.
- Phân tích cardinality của metrics và tác động của label có giá trị biến thiên cao.
- Tính chi phí ingest, index, hot storage, archive, replica và truy vấn.
- Chọn sampling, aggregation, downsampling và retention phù hợp.
- Thiết kế pipeline lọc và nén dữ liệu trước khi gửi đến observability backend.
- Đọc dashboard dung lượng để tìm nguồn tăng trưởng bất thường và tối ưu có kiểm soát.

## 1. Các thành phần tạo nên chi phí observability

Một nền tảng observability thường có nhiều khoản phí riêng. Cần xác định mô hình tính phí của backend đang sử dụng vì một số dịch vụ tính theo GB ingest, một số tính theo active series, span, dung lượng lưu hoặc truy vấn.

| Thành phần | Chi phí phát sinh từ | Yếu tố làm tăng chi phí |
|---|---|---|
| Log ingestion | Dữ liệu gửi vào backend | Nhiều event/request, event lớn, log debug, payload lặp |
| Log indexing | Phân tích và lập chỉ mục field để tìm kiếm | Nhiều field index, field có cardinality cao, index retention dài |
| Metrics ingestion | Số mẫu và active time series | Scrape interval ngắn, nhiều label, histogram bucket |
| Trace ingestion | Số trace/span được thu thập | Nhiều span/request, sampling cao, attribute lớn |
| Hot storage | Dữ liệu cần truy vấn nhanh | Retention dài, replica, index và metadata |
| Archive storage | Dữ liệu giữ lâu với tần suất truy cập thấp | Nhiều bản sao, lifecycle không xóa, truy xuất archive |
| Query/compute | Dashboard, ad hoc query, alert và export | Query rộng, nhiều dashboard refresh nhanh, scan dữ liệu lớn |
| Network/replication | Truyền dữ liệu giữa vùng hoặc cụm | Cross-region, egress, collector và replica |

Phân biệt **ingest cost** với **storage cost**. Nếu nhà cung cấp tính phí theo GB ingest, giảm retention có thể giảm dung lượng lưu nhưng không giảm phí ingest. Ngược lại, nếu tính theo active series, giảm label cardinality có thể giảm chi phí ngay cả khi tổng số request không đổi.

## 2. Ước tính dung lượng log

Log thường được tính theo số event và kích thước trung bình của mỗi event. Công thức cơ bản:

\[
V_{log/day} = R \times E \times S \times 86\,400
\]

Trong đó:

- (R): số request mỗi giây.
- (E): số event log trung bình trên một request.
- (S): kích thước trung bình mỗi event tính bằng byte.
- (86\,400): số giây trong một ngày.

Nếu có event nền không gắn với request như scheduler, health check hoặc batch job, cộng riêng lượng event đó. Cần đo kích thước event thực tế sau serialization vì JSON field name, timestamp, trace context và metadata cũng chiếm dung lượng.

### 2.1. Ví dụ tính log ingest

Giả sử dịch vụ xử lý trung bình 25 request/giây, mỗi request tạo 4 event và mỗi event có kích thước 1,2 KB:

\[
25 \times 4 \times 1.2\text{ KB} \times 86\,400
= 10.368\text{ GB/ngày}
\]

Trong 30 ngày, dữ liệu thô vào khoảng:

\[
10.368 \times 30 = 311.04\text{ GB}
\]

Đây là dung lượng event trước nén và index. Backend có thể lưu dữ liệu nén nhỏ hơn, nhưng cũng có thể tạo thêm index, metadata và replica. Dùng số đo từ backend để hiệu chỉnh dự báo, không mặc định mọi log có tỷ lệ nén giống nhau.

### 2.2. Những yếu tố làm log lớn bất ngờ

- Ghi toàn bộ prompt, câu hỏi, câu trả lời hoặc context RAG ở nhiều chặng.
- Ghi stack trace lặp lại ở nhiều lớp cho cùng một exception.
- Bật `DEBUG` hoặc `TRACE` trên package rộng trong production.
- Ghi từng token hoặc từng chunk của response streaming.
- Lưu object JSON lớn, header không cần thiết hoặc field lặp lại.
- Index quá nhiều field, đặc biệt field có giá trị duy nhất theo request.

Với ứng dụng Spring AI, log vận hành nên giữ metadata như `request_id`, `trace_id`, model, prompt version, index version, token usage, status và duration. Payload cần tái hiện nên có kho lưu riêng, quyền truy cập và retention phù hợp; log thường chỉ giữ `evidence_ref`.

## 3. Ước tính dung lượng metrics và cardinality

Metrics khác log: hệ thống lưu các mẫu số theo thời gian cho mỗi time series. Một time series được xác định bởi tên metric và tập label. Số active series có thể tăng rất nhanh khi thêm label mới.

Ví dụ metric `spring_ai_request_duration_seconds` với các label:

```text
model = 3 giá trị
operation = 4 giá trị
status = 3 giá trị
environment = 2 giá trị
```

Số series tối đa theo tích Descartes của các label trên là:

\[
3 \times 4 \times 3 \times 2 = 72\text{ series}
\]

Nếu thêm `tenant_id` với 5.000 giá trị, số series lý thuyết tăng lên:

\[
72 \times 5\,000 = 360\,000\text{ series}
\]

Một label tưởng như hữu ích để lọc dashboard có thể làm tăng active series hàng nghìn lần. Không dùng `request_id`, `trace_id`, `conversation_id`, email, user ID, document ID hoặc câu hỏi làm label metrics. Các giá trị này phù hợp với log hoặc trace có quyền truy cập phù hợp.

### 3.1. Tính số mẫu theo scrape interval

Với pull-based metrics, số mẫu thô mỗi ngày có thể ước tính:

\[
Samples/day = ActiveSeries \times \frac{86\,400}{ScrapeIntervalSeconds}
\]

Ví dụ có 1.500 active series và scrape mỗi 15 giây:

\[
1\,500 \times \frac{86\,400}{15} = 8.64\text{ triệu mẫu/ngày}
\]

Nếu scrape mỗi 5 giây, số mẫu tăng gấp ba. Một số backend tính phí theo active series thay vì số mẫu, nhưng scrape interval vẫn ảnh hưởng đến ingest, network và dung lượng lưu. Hãy kiểm tra mô hình tính phí cụ thể.

Nếu chỉ dùng giả định đơn giản 16 byte cho mỗi sample:

\[
8.64\text{ triệu} \times 16\text{ byte} = 138.24\text{ MB/ngày}
\]

Con số này chỉ là payload mẫu thô để minh họa phép tính. Storage engine thực tế cần thêm timestamp encoding, index, chunk metadata, replication và overhead; compression cũng có thể làm giảm dung lượng. Không dùng 16 byte/sample làm cam kết dung lượng backend.

### 3.2. Histogram làm tăng số series

Histogram thường tạo nhiều bucket cho mỗi tổ hợp label, cộng thêm series `_sum` và `_count`. Nếu một metric histogram có 12 bucket và 72 tổ hợp label, số series có thể xấp xỉ:

\[
72 \times (12 + 2) = 1\,008\text{ series}
\]

Số bucket thực tế phụ thuộc cấu hình và backend. Histogram rất hữu ích để tính percentile như p95, nhưng cần chọn bucket phù hợp SLO. Không bật histogram cho mọi metric nếu không có nhu cầu phân tích phân phối.

### 3.3. Quy tắc thiết kế label

| Label phù hợp | Label cần tránh |
|---|---|
| `model` với danh sách model giới hạn | `request_id` |
| `operation` như `chat`, `embedding`, `rerank` | `conversation_id` |
| `status` như `success`, `error`, `rate_limited` | `user_id`, email |
| `environment` như `dev`, `staging`, `prod` | `document_id`, `chunk_id` |
| `tenant_tier` như `free`, `standard`, `enterprise` | `prompt_text`, URL có ID biến thiên |
| `error_type` từ danh sách mã hữu hạn | Exception message nguyên văn |

Nếu cần phân tích theo tenant cụ thể, truy vấn log hoặc billing/usage store có kiểm soát. Có thể dùng tenant tier hoặc nhóm đã phân loại làm label metric.

## 4. Ước tính dung lượng trace

Một trace có thể gồm nhiều span: nhận request, truy xuất, embedding, gọi model, tool call, retry và post-processing. Kích thước trace phụ thuộc số span, attribute, event và sampling rate.

\[
V_{trace/day} = R \times P \times N_s \times S_s \times 86\,400
\]

Trong đó:

- (R): request mỗi giây.
- (P): tỷ lệ trace được giữ lại, từ 0 đến 1.
- (N_s): số span trung bình mỗi trace.
- (S_s): kích thước trung bình mỗi span.

Giả sử 25 request/giây, lấy mẫu 10% trace, mỗi trace có 8 span và mỗi span trung bình 1 KB:

\[
25 \times 0.10 \times 8 \times 1\text{ KB} \times 86\,400
= 1.728\text{ GB/ngày}
\]

Trong 30 ngày, dung lượng span thô xấp xỉ 51,84 GB. Đây chưa tính index, metadata, replica và overhead của trace backend.

### 4.1. Sampling trace có chủ đích

Head-based sampling quyết định giữ trace ngay khi bắt đầu request. Cách này đơn giản và kiểm soát dung lượng tốt, nhưng có thể bỏ lỡ trace lỗi nếu quyết định lấy mẫu không phù hợp.

Tail-based sampling quyết định sau khi collector nhận đủ trace, dựa trên status, latency hoặc attribute. Có thể giữ toàn bộ trace lỗi, trace chậm và chỉ một phần trace thành công. Đổi lại, collector cần buffer, memory và khả năng gom các span cùng trace trước khi quyết định.

Một policy tham khảo:

- Giữ 100% trace có lỗi đã phân loại hoặc vượt ngưỡng latency.
- Giữ 5–10% trace thành công theo sampling ngẫu nhiên.
- Giữ tỷ lệ cao hơn trong staging hoặc canary khi cần đánh giá release.
- Giới hạn số span, attribute và event trên mỗi trace.
- Không ghi nội dung prompt, response hoặc toàn bộ tài liệu vào span attribute.

Tỷ lệ trên chỉ là ví dụ. Nếu traffic lớn, 100% trace lỗi cũng có thể tạo tải cao khi lỗi lan rộng. Cần có giới hạn dung lượng, ưu tiên trace và cảnh báo khi collector buffer gần đầy. Không được để sampling làm mất log lỗi hoặc metric tổng hợp cần cho SLO.

## 5. Tính tổng dung lượng và chi phí lưu trữ

Sau khi ước tính ba nguồn dữ liệu, có thể tính dung lượng thô:

\[
V_{raw/day} = V_{log/day} + V_{metric/day} + V_{trace/day}
\]

Metric backend thường lưu theo block và nén theo thời gian; không phải mọi hệ thống đều có thể ước lượng bằng byte/sample cố định. Để lập ngân sách sơ bộ, có thể dùng số đo ingest và storage thực tế của backend sau một giai đoạn chạy thử.

### 5.1. Ví dụ tổng hợp

Sử dụng các giả định ở trên:

| Nguồn | Dung lượng thô/ngày | Dung lượng thô/30 ngày |
|---|---:|---:|
| Logs | 10,368 GB | 311,04 GB |
| Metrics | 0,138 GB | 4,15 GB |
| Traces | 1,728 GB | 51,84 GB |
| **Tổng** | **12,234 GB** | **367,027 GB** |

Tổng chính xác theo các số chưa làm tròn là khoảng **12,23424 GB/ngày** và **367,0272 GB/30 ngày**. Bảng được làm tròn đến ba chữ số thập phân; khi lập ngân sách hãy giữ số chính xác trong bảng tính.

### 5.2. Từ dung lượng thô đến physical storage

Dung lượng backend có thể ước tính theo:

\[
V_{physical} \approx V_{raw} \times C \times I \times R_p
\]

Trong đó:

- (C): tỷ lệ dung lượng sau nén so với dữ liệu thô.
- (I): hệ số index và metadata; nếu biểu diễn overhead theo tỷ lệ, ví dụ 0,4 thì hệ số nhân là 1,4.
- (R_p): hệ số replica hoặc bản sao lưu được tính vào storage.

Các hệ số này phụ thuộc backend, loại dữ liệu, cấu hình và cách nhà cung cấp tính phí. Với SaaS, giá ingest và retention có thể đã bao gồm một phần overhead; không nhân thêm nếu bảng giá đã tính sẵn.

### 5.3. Mô hình chi phí tổng thể

Một mô hình ngân sách tổng quát:

\[
Cost_{total} = Cost_{ingest} + Cost_{hot} + Cost_{archive} + Cost_{query} + Cost_{network}
\]

Ví dụ:

- `Cost_ingest`: GB log/trace ingest hoặc active metric series theo bảng giá.
- `Cost_hot`: GB-month ở storage có index và truy vấn nhanh.
- `Cost_archive`: GB-month ở storage rẻ hơn và phí restore/query.
- `Cost_query`: compute, scan, dashboard refresh, alert evaluation hoặc export.
- `Cost_network`: replication, cross-region transfer và egress.

Đừng lấy một mức giá GB duy nhất nhân tổng dung lượng rồi xem đó là toàn bộ hóa đơn. Hãy tách cost driver theo từng loại dữ liệu và đối chiếu với invoice/backend usage report.

## 6. Lưu trữ nóng, lạnh và retention theo mục đích

Hot storage dành cho dữ liệu cần tìm kiếm nhanh trong vận hành hằng ngày. Archive phù hợp với dữ liệu còn mục đích lưu giữ nhưng ít truy vấn. Aggregation hoặc downsampling phù hợp với metrics cần xem xu hướng dài hạn.

| Dữ liệu | Hot tier | Tier dài hạn | Cách giảm dung lượng |
|---|---|---|---|
| Logs | Event đã lọc, index field cần thiết | Archive nén hoặc xóa khi hết mục đích | Giảm event lặp, bỏ payload, giảm index field |
| Metrics | Độ phân giải đầy đủ trong cửa sổ vận hành | Downsample theo phút/giờ hoặc giữ aggregate | Giảm cardinality, scrape interval phù hợp |
| Traces | Trace lỗi/chậm và sample thành công | Thường chỉ giữ metadata tổng hợp hoặc archive có mục đích | Sampling, giới hạn span/attribute, retention ngắn |

Không phải mọi dữ liệu đều cần archive. Nếu payload hoặc trace chi tiết không còn mục đích, xóa theo policy thường phù hợp hơn lưu lạnh vô thời hạn. Bản sao, backup, export và cache cũng phải nằm trong vòng đời dữ liệu.

## 7. Tối ưu pipeline trước khi gửi dữ liệu

Giảm dữ liệu ở collector hoặc ứng dụng trước khi ingest thường rẻ hơn lọc sau khi đã trả phí ingest. Một pipeline hợp lý có thể thực hiện:

1. **Normalize:** chuẩn hóa tên field, timestamp, severity và resource attributes.
2. **Redact:** loại bỏ secret, dữ liệu cá nhân và payload không được phép.
3. **Filter:** bỏ health check hoặc event lặp không có giá trị điều tra.
4. **Aggregate:** tổng hợp event lặp thành counter/summary khi phù hợp.
5. **Sample:** áp dụng sampling có kiểm soát cho trace hoặc debug event.
6. **Batch/compress:** gom batch và nén trước khi gửi.
7. **Route:** chuyển audit, log vận hành, trace và metric đến backend hoặc tier phù hợp.

### 7.1. Giảm log mà không mất bằng chứng

Với mỗi chặng Spring AI, ghi một event hoàn tất có cấu trúc thay vì nhiều câu log trùng lặp. Ví dụ một `ai.model.completed` có thể chứa model, prompt version, token usage, finish reason, retry count và duration. Nếu cần điều tra sâu, dùng `trace_id` để mở span tương ứng.

Không ghi lại toàn bộ `ChatRequest`, `ChatResponse`, `Prompt`, message history, tool arguments hoặc retrieved document chỉ để tiện debug. Hãy dùng allowlist field. Nếu cần payload, lưu riêng và chỉ ghi `evidence_ref` trong event.

### 7.2. Giảm metrics cardinality

- Dùng label có miền giá trị hữu hạn.
- Không thêm label từ input người dùng hoặc ID sinh theo request.
- Giới hạn số model, operation và error type được phép xuất thành label.
- Chỉ bật histogram cho metric cần percentile.
- Tăng scrape interval với metric ít biến động nếu yêu cầu vận hành cho phép.
- Dùng recording rule để tổng hợp query tốn kém và dashboard dài hạn.

Trước khi thêm label mới, ước tính số series bằng tích số giá trị có thể có của tất cả label. Theo dõi active series và churn; một label có thể có ít giá trị cùng lúc nhưng thay đổi liên tục vẫn gây churn và tăng chi phí.

### 7.3. Tối ưu traces

- Tạo span cho operation có ý nghĩa: retrieval, model call, tool call và dependency.
- Không tạo span cho từng token hoặc từng dòng xử lý nhỏ nếu không cần.
- Giữ attribute hữu ích như model, operation, status và retry count.
- Tránh gắn prompt, response, user ID hoặc tài liệu vào span attribute.
- Dùng parent-child span và trace context thay vì sao chép metadata lớn ở mọi span.
- Áp dụng tail sampling nếu cần giữ lỗi/chậm và collector đủ năng lực.

## 8. Theo dõi ngân sách observability

Một dashboard chi phí observability nên hiển thị:

| Panel | Chỉ số |
|---|---|
| Ingest volume | GB log/ngày, spans/ngày, metric samples/ngày |
| Active cardinality | Active series, series mới, label churn |
| Storage footprint | Hot GB, archive GB, index GB, replica GB |
| Retention | Dữ liệu theo tuổi, số ngày còn giữ, backlog xóa |
| Query usage | Query count, scan bytes, dashboard refresh và query latency |
| Cost | Ingest cost, hot/archive cost, query/network cost, tổng theo service |
| Top contributors | Logger/package, service, environment hoặc dataset chiếm nhiều dung lượng |

Theo dõi cả mức hiện tại và tốc độ tăng. Ví dụ, active series tăng 30% sau một release có thể chỉ ra một label mới bị thêm vào metric. Log ingest tăng gấp đôi trong khi request rate không đổi có thể do debug logging, event duplication hoặc payload vô tình được ghi.

### 8.1. Phân bổ chi phí theo service

Để phân bổ chi phí, gắn resource attribute có miền giá trị hữu hạn như `service.name`, `environment`, `team` hoặc `deployment`. Có thể dùng tenant tier thay cho tenant ID. Tránh đưa thông tin định danh hoặc dữ liệu cá nhân vào resource attribute.

Nếu nhiều service dùng chung collector/backend, hãy xác định tỷ lệ phân bổ cho ingest, storage và query. Có thể phân bổ theo GB ingest, active series hoặc tỷ lệ query compute. Ghi rõ phương pháp phân bổ vì một service có thể tạo nhiều dữ liệu nhưng ít query, service khác tạo ít dữ liệu nhưng truy vấn nặng.

## 9. Ví dụ phân tích một đợt tăng chi phí

Sau khi triển khai release mới của trợ lý Spring AI, hóa đơn observability tăng 45% trong khi số request chỉ tăng 5%. Dashboard cho thấy:

- Log ingest tăng 70%.
- Active metric series tăng 2,5 lần.
- Trace ingest tăng 15%.
- Hot storage tăng 30%.

Điều tra lần lượt:

1. So sánh log event/request trước và sau release. Nếu tăng mạnh, kiểm tra logger mới hoặc log lặp trong retry loop.
2. So sánh schema metric. Tìm label mới có giá trị biến thiên cao như `conversation_id` hoặc `document_id`.
3. Kiểm tra trace span/request và sampling rate. Nếu tăng ít, trace không phải nguồn chi phí chính.
4. Kiểm tra index field, replica và retention để hiểu vì sao hot storage tăng.
5. Kiểm tra dashboard query có scan toàn bộ thời gian hoặc refresh quá thường xuyên không.
6. Ước tính tác động của việc bỏ label, giảm event lặp và chuyển dữ liệu cũ sang archive.
7. Triển khai thay đổi theo từng bước và theo dõi chi phí cùng khả năng điều tra sau tối ưu.

Không giảm sampling hoặc xóa log một cách mù quáng chỉ để làm hóa đơn giảm. Trước khi thay đổi, xác định tín hiệu cần cho SLO, incident response, security audit và evaluation. Sau tối ưu, kiểm tra một sự cố mô phỏng để bảo đảm người vận hành vẫn tìm được request và trace liên quan.

## 10. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ tính dung lượng log thô | Bỏ sót index, replica, metadata và query cost | Đo physical storage và invoice thực tế |
| Dùng ID duy nhất làm metric label | Cardinality tăng rất nhanh | Đưa ID vào log/trace; metric dùng label hữu hạn |
| Scrape quá thường xuyên | Tăng sample và network không cần thiết | Chọn interval theo nhu cầu freshness |
| Bật mọi histogram bucket | Nhân số active series | Chỉ bật histogram cho SLO/percentile cần thiết |
| Giữ 100% trace thành công ở traffic lớn | Trace ingest và storage tăng cao | Sampling có chủ đích, giữ lỗi/chậm theo policy |
| Ghi prompt và context vào mọi span | Span lớn, rủi ro dữ liệu và chi phí cao | Dùng metadata và evidence reference |
| Chỉ giảm retention | Giảm storage nhưng không nhất thiết giảm ingest | Tối ưu nguồn phát và mô hình billing |
| Archive nhưng không đặt lifecycle | Dữ liệu tiếp tục tích lũy | Đặt thời hạn cuối và kiểm tra xóa |
| Tối ưu chi phí mà không kiểm thử điều tra | Mất bằng chứng khi xảy ra incident | Thực hiện incident drill sau mỗi thay đổi lớn |

## 11. Bài tập thực hành

Một ứng dụng Spring AI xử lý 25 request/giây. Mỗi request tạo 4 log event, trung bình 1,2 KB/event. Hệ thống có 1.500 active metric series, scrape interval 15 giây. Mỗi request tạo 8 span, mỗi span trung bình 1 KB và trace sampling hiện tại là 10%.

Hãy thực hiện:

1. Tính log ingest thô mỗi ngày và dung lượng 30 ngày.
2. Tính số metric samples mỗi ngày. Nếu giả định 16 byte/sample, ước tính dung lượng thô trước overhead.
3. Tính trace ingest mỗi ngày và 30 ngày.
4. Tính tổng dung lượng thô, sau đó liệt kê các yếu tố cần cộng thêm để ước tính physical storage.
5. Đề xuất thay đổi để giảm 30% chi phí mà vẫn giữ được trace lỗi, metric SLO và bằng chứng điều tra.
6. Xác định label metric có rủi ro cardinality cao và thay thế bằng cách nào.
7. Xây dựng dashboard theo dõi ingest, active series, hot/archive storage, retention và query cost.
8. Đề xuất một incident drill để xác minh tối ưu không làm mất khả năng truy vết.

**Tiêu chí tự kiểm tra:** mọi phép tính có đơn vị và giả định rõ ràng; phân biệt raw ingest với physical storage; nhận diện được cardinality, index, replica và query cost; và mỗi biện pháp tiết kiệm đều có cách kiểm tra ảnh hưởng đến chất lượng observability.

## 12. Checklist trước khi đưa observability vào production

- [ ] Đã đo request rate, event/request, span/request và active metric series.
- [ ] Đã ước tính log, metric và trace ingest theo ngày/tháng.
- [ ] Đã kiểm tra mô hình billing: ingest, active series, storage, query và network.
- [ ] Metrics labels có cardinality hữu hạn và không chứa ID request/user.
- [ ] Histogram chỉ bật cho metric cần percentile.
- [ ] Trace sampling giữ lỗi/chậm theo policy và có giới hạn collector buffer.
- [ ] Log và span không chứa payload nhạy cảm hoặc dữ liệu lặp không cần thiết.
- [ ] Compression, batch, index field và replica đã được tính trong dự báo.
- [ ] Hot/archive tier có lifecycle và thời hạn xóa cuối cùng.
- [ ] Dashboard hiển thị ingest, active series, storage, retention và cost theo service.
- [ ] Có cảnh báo cho ingest spike, cardinality churn và backlog xóa.
- [ ] Có incident drill sau khi thay đổi sampling, retention hoặc schema metric.

Chi phí observability được quyết định từ lúc dữ liệu được tạo, không chỉ ở bước lưu trữ. Khi đo đúng log event rate, metric cardinality, span volume và chi phí backend, nhóm phát triển có thể giảm dữ liệu thừa, chọn tier và sampling phù hợp, đồng thời giữ đủ bằng chứng để vận hành và đánh giá chất lượng ứng dụng Spring AI.
