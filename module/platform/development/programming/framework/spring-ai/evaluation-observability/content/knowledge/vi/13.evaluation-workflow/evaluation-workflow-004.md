# Phân biệt ca đạt, không đạt, bị bỏ qua và lỗi kỹ thuật

Một batch đánh giá Spring AI có thể trả về báo cáo “90% ca thành công”, nhưng “thành công” ở đây là API trả HTTP 200, mô hình tạo được văn bản, evaluator cho điểm PASS hay toàn bộ nhiệm vụ đã được giải quyết đúng? Nếu không tách những ý nghĩa ấy, một báo cáo rất đẹp vẫn có thể che giấu câu trả lời bịa, lỗi 429 hoặc hàng chục ca bị bỏ qua.

Giả sử một chatbot RAG cho doanh nghiệp **Sao Mai** (hoàn toàn giả định) trả lời câu hỏi: “Gói Pro được hoàn phí trong bao lâu?”. Nguồn chính thức hiện hành quy định **14 ngày kể từ ngày mua**. Có ít nhất bốn khả năng:

- Model trả lời “14 ngày”, có căn cứ và trích dẫn đúng: **ca đạt (PASS)** theo tiêu chí đã xác định.
- Model trả lời “30 ngày” dù API không báo lỗi: **ca không đạt (FAIL)** về factual correctness.
- Ca không được chạy vì chưa có môi trường sandbox bắt buộc, theo quy tắc loại trừ công bố trước: **bị bỏ qua (SKIPPED)**.
- Model provider timeout và không tạo được response: **lỗi kỹ thuật (TECHNICAL_ERROR)**, chưa có nội dung hợp lệ để chấm.

Còn trường hợp model đã tạo câu trả lời nhưng **LLM judge bị timeout**? Đây không phải một ca PASS hay FAIL về chất lượng. Phần thực thi ứng dụng đã hoàn tất, còn phép chấm ở trạng thái **NOT_EVALUATED** hoặc **EVALUATOR_ERROR**.

Trong chương **Quy trình đánh giá** của module **SPRING_AI_EVALUATION_OBSERVABILITY**, phân loại trạng thái là nền tảng để đánh giá relevance, fact checking, kiểm thử RAG/tool calling, đồng thời đo metrics, traces, token, chi phí và độ trễ qua từng phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa chính xác PASS, FAIL, SKIPPED và TECHNICAL_ERROR ở cấp một ca đánh giá.
2. Phân biệt kết quả **thực thi** với kết quả **chấm chất lượng** và trạng thái của một batch.
3. Sử dụng hợp lý NOT_EVALUATED, NOT_APPLICABLE, PENDING, CANCELLED và INCONCLUSIVE.
4. Phân loại lỗi retrieval, generation, tool backend, evaluator hoặc result store.
5. Thiết kế cấu trúc kết quả có run ID, case ID, attempt ID, rubric, reason code và evidence.
6. Tính pass rate, technical completion, skip rate, evaluation coverage bằng mẫu số đúng.
7. Xác định hành vi retry, chạy lặp và xử lý ca dở dang trong batch có concurrency giới hạn.
8. Viết logic tổng hợp verdict và unit test Java kiểm tra các ranh giới trạng thái.
9. Xây release gate không để lỗi hoặc skip của ca quan trọng được tính thành PASS.
10. Liên kết FAIL/ERROR với Spring AI metrics và traces để giải thích nguyên nhân.

## 2. Câu hỏi đầu tiên: “Đạt ở lớp nào?”

Một response có thể đáp ứng hợp đồng HTTP nhưng sai nghiệp vụ. Một lời gọi tool bị từ chối quyền có thể là lỗi đối với tác vụ lấy dữ liệu nhưng lại là **hành vi mong đợi** của ca kiểm thử truy cập trái phép.

| Lớp | Điều cần kiểm | Bằng chứng |
| --- | --- | --- |
| API và xử lý phần mềm | Request có hoàn tất, đúng schema, không exception không? | HTTP/exception/parser |
| Retrieval | Đã tìm được tài liệu cần thiết trong top-k chưa? | Actual document IDs, versions |
| Answer relevance | Trả lời có đúng trọng tâm câu hỏi không? | Question, actual answer |
| Groundedness | Mệnh đề có được context model **thực sự nhận** hỗ trợ không? | Effective context, answer |
| Factual correctness | Có đúng nguồn chuẩn độc lập đã được xác minh không? | Reference facts/source, answer |
| Citation | Có dẫn đúng tài liệu hỗ trợ nội dung không? | Citation IDs, documents |
| Tool calling | Có gọi đúng tool/args/quyền, xử lý đúng kết quả không? | Actual tool events, backend state |
| Vận hành | Latency, lỗi, token/cost có đạt ngân sách không? | Metrics, traces, provider usage |
| End-to-end task | Người dùng có nhận đúng kết quả trong giới hạn dịch vụ không? | Tổng hợp nhiều lớp |

Trong một lần chạy RAG, model nói “30 ngày” dựa trên tài liệu cũ. `relevance=PASS` là khả thi vì câu trả lời đúng chủ đề; `groundedness=PASS` cũng có thể xảy ra theo context cũ, nhưng `factualCorrectness=FAIL` theo chính sách hiện hành 14 ngày.

**Không dùng một cờ success duy nhất để che các lớp đánh giá khác nhau.** Một aggregate PASS chỉ có nghĩa nếu quy tắc tổng hợp, tập metric bắt buộc và nguồn bằng chứng được nói rõ.

## 3. Bốn trạng thái tổng hợp cơ bản

| Trạng thái | Định nghĩa | Ví dụ | Không được hiểu thành |
| --- | --- | --- | --- |
| **PASS** | Ca đã chạy và các tiêu chí bắt buộc được chấm, đều đạt | Trả đúng 14 ngày, nguồn hợp lệ | Mọi khía cạnh chưa kiểm đều đúng |
| **FAIL** | Có bằng chứng xác nhận ít nhất một tiêu chí bắt buộc bị vi phạm | Answer nêu 30 ngày | Provider hay HTTP nhất thiết lỗi |
| **SKIPPED** | Ca không chạy có chủ đích theo quy tắc eligibility/skip được ghi trước | Ca sandbox-only không có môi trường phù hợp | Chất lượng đã đạt hoặc đã fail |
| **TECHNICAL_ERROR** | Ca đã được thử thực thi nhưng không tạo được output hợp lệ do sự cố kỹ thuật | Provider timeout, service unavailable | Nội dung sẽ sai nếu có output |

### 3.1. PASS phải gắn với phạm vi chấm

`PASS` của metric relevance chưa đủ để công bố “chất lượng đã đạt tất cả”. Nếu test chỉ kiểm câu trả lời có nhắc đến hoàn phí, model có thể “đạt relevance” nhưng bịa số ngày. Ghi rõ tên metric và rubric version.

Đối với ca tool có tác dụng phụ, một lời đáp chính xác nhưng lệnh tool thiếu kiểm tra quyền vẫn có thể là **FAIL của hợp đồng ứng dụng**. Không lấy điểm văn phong để bù sai sót nghiêm trọng.

### 3.2. FAIL cần có căn cứ về việc không đạt

Một số ví dụ:

- Retrieval không có tài liệu bắt buộc mặc dù nhãn nguồn đầy đủ.
- Answer nêu sai thời hạn hoặc thêm ngoại lệ không có nguồn.
- Model không gọi `getOrderStatus` khi dữ liệu backend là điều kiện bắt buộc.
- Model gọi đúng tool nhưng truyền sai `orderId`.
- Response vi phạm JSON Schema đã được xác định là một metric kiểm thử.

Nên ghi `reasonCode` và evidence refs. Chỉ có chữ “FAIL” mà không biết actual answer hay document IDs thì khó sửa đúng chỗ.

### 3.3. SKIPPED là quyết định về phạm vi chạy

Ca được skip hợp lệ khi có chính sách cho phép, ví dụ job không có sandbox nên không chạy bài thử tool hoàn phí có side effect, nhưng bài đó bắt buộc phải được thực hiện ở job sandbox chuyên dụng.

**Không gọi là SKIPPED khi provider trả 429, runner timeout, fixture bất ngờ bị thiếu hoặc evaluator chấm FAIL.** Đây là lỗi/dữ liệu chưa sẵn sàng hoặc tình trạng chưa hoàn tất, không phải loại trừ hợp lệ theo kế hoạch.

### 3.4. TECHNICAL_ERROR là vấn đề thực thi

Ví dụ provider kết nối thất bại, VectorStore timeout làm pipeline không tạo được response hợp lệ, hoặc code orchestration ném exception không thể xử lý. Khi không có answer hợp lệ, không được tạo verdict “factual correctness FAIL” nếu chưa có dữ liệu để kiểm.

Nếu ứng dụng có fallback và tạo response hợp lệ như “Hiện chưa truy xuất được tài liệu”, nó có thể được ghi execution COMPLETED rồi chấm **hành vi fallback** theo rubric. Không tự gán PASS vì thông báo lỗi được viết lịch sự.

## 4. Mô hình hai trục: execution và evaluation

Một enum PASS/FAIL/SKIPPED/ERROR tiện cho dashboard tổng hợp, nhưng không diễn tả đầy đủ trường hợp **model hoàn tất, bộ chấm lỗi**. Nên tách hai trục trạng thái.

### Trục A — Execution status

| Giá trị | Ý nghĩa |
| --- | --- |
| `NOT_STARTED` | Chưa được lịch trình đưa vào thực thi |
| `SKIPPED` | Không chạy theo skip policy hợp lệ |
| `RUNNING` | Đã bắt đầu, chưa có kết quả cuối |
| `COMPLETED` | Pipeline tạo output hợp lệ về mặt kỹ thuật |
| `ERROR` | Thất bại kỹ thuật, không có output hợp lệ theo contract |
| `CANCELLED` | Bị dừng trước khi hoàn tất |

### Trục B — Metric evaluation status

| Giá trị | Ý nghĩa |
| --- | --- |
| `PENDING` | Đang chờ chấm hoặc chờ review |
| `PASS` | Đã chấm, đạt rubric |
| `FAIL` | Đã chấm, vi phạm rubric |
| `NOT_EVALUATED` | Thiếu bằng chứng hoặc evaluator không đưa ra verdict được |
| `NOT_APPLICABLE` | Metric không áp dụng cho ca theo thiết kế |
| `EVALUATOR_ERROR` *(tùy schema)* | Bộ chấm lỗi; chất lượng vẫn chưa có verdict |

Chỉ số `COMPLETED` nằm trên trục kỹ thuật; `PASS` nằm trên trục đánh giá. Không nên đổi tên chúng thành cùng một “success”.

### 4.1. Ma trận diễn giải

| Execution status | Metric status | Cách báo |
| --- | --- | --- |
| COMPLETED | PASS | Đã hoàn tất và đạt metric |
| COMPLETED | FAIL | Đã hoàn tất nhưng sai theo metric |
| COMPLETED | NOT_EVALUATED | Có output, chưa đủ kết luận |
| COMPLETED | NOT_APPLICABLE | Metric không liên quan |
| SKIPPED | Không chấm | Ca được bỏ qua theo chính sách |
| ERROR | Không chấm | Lỗi kỹ thuật, không có output để chấm |
| CANCELLED | Có thể chưa có verdict | Ca bị dừng/chưa hoàn tất |

Nếu một ca có nhiều metric bắt buộc, có thể vừa `relevance=PASS` vừa `factualCorrectness=FAIL`. Những verdict này phải được giữ riêng khi tổng hợp.

### 4.2. Vòng đời một ca

~~~mermaid
flowchart TD
  A["Selected case"] --> B{"Eligible theo plan?"}
  B -- "Không" --> S["SKIPPED + reason"]
  B -- "Có" --> C["RUNNING"]
  C --> D{"Có output hợp lệ?"}
  D -- "Lỗi kỹ thuật" --> E["ERROR + stage/code"]
  D -- "Hủy" --> K["CANCELLED"]
  D -- "Có" --> F["COMPLETED + actual evidence"]
  F --> G{"Metric có áp dụng?"}
  G -- "Không" --> NA["NOT_APPLICABLE"]
  G -- "Có" --> H{"Có đủ evidence/judge?"}
  H -- "Không" --> NE["NOT_EVALUATED + reason"]
  H -- "Có" --> I{"Đạt rubric?"}
  I -- "Đạt" --> P["PASS"]
  I -- "Không đạt" --> X["FAIL"]
~~~

Sơ đồ là mô hình khái niệm: một attempt có thể sinh nhiều metric verdict độc lập, được lưu theo `attemptId`.

## 5. SKIPPED, NOT_EVALUATED và NOT_APPLICABLE rất khác nhau

| Tình huống | Execution | Evaluation | Giải thích |
| --- | --- | --- | --- |
| Bài test chỉ dành cho job có sandbox | SKIPPED | Không chấm | Loại trừ trước khi chạy |
| Model trả answer, judge timeout | COMPLETED | NOT_EVALUATED | Lỗi tại giai đoạn chấm |
| Model trả answer, không lưu effective context | COMPLETED | NOT_EVALUATED cho groundedness | Thiếu bằng chứng |
| Ca chỉ hỏi đáp, không dùng tool | COMPLETED | NOT_APPLICABLE cho toolSelection | Metric không liên quan |
| Provider timeout, không trả answer | ERROR | Không chấm quality | Không có output hợp lệ |
| Batch bị kill trước khi xếp lịch ca | NOT_STARTED hoặc CANCELLED | Không chấm | Chưa hoàn tất, không phải skip |
| Answer sai so với nguồn hiện hành | COMPLETED | FAIL | Có căn cứ để xác nhận lỗi |

### 5.1. Một bản ghi SKIPPED nên có gì?

- `skipReasonCode` như `FEATURE_DISABLED_BY_PLAN` hoặc `ENVIRONMENT_NOT_SUPPORTED`.
- `runId`/`caseId` và chính sách skip version.
- Quy tắc hoặc môi trường khiến ca không đủ điều kiện.
- Giải thích ca có được chạy trong job khác không.
- Severity: skip có bao gồm ca critical không?

Một ca critical bị skip ở một job có thể chấp nhận **ở cấp job** nếu đã chạy trong job đủ điều kiện; nhưng **không được coi đã PASS ở cấp release** khi không có bằng chứng.

### 5.2. INCONCLUSIVE là tổng hợp chưa đủ bằng chứng

Nếu phần thực thi hoàn tất, không có metric bắt buộc FAIL, nhưng một metric bắt buộc `NOT_EVALUATED`, kết luận tổng hợp nên là **INCONCLUSIVE** hoặc **REVIEW_REQUIRED**, không phải PASS.

Ngược lại, nếu factual correctness đã FAIL chắc chắn còn groundedness chưa chấm, tổng hợp có thể là **FAIL**, nhưng vẫn giữ bản ghi groundedness NOT_EVALUATED để không giấu thiếu sót.

## 6. Phân loại technical errors theo giai đoạn

| Giai đoạn | Ví dụ | Cần lưu | Không nên làm |
| --- | --- | --- | --- |
| Load dataset | JSONL sai cấu trúc | Dataset ref, parse error | Skip mọi ca |
| Prepare fixture | Sandbox tool không khởi tạo | Fixture version, failure | Giả bộ tool PASS |
| VectorStore | Timeout retrieval | Error stage, trace, retry | Tự chèn nguồn chuẩn thay cho actual |
| ChatModel | Provider 429 hết retry | Provider, model, error code | Ghi SKIPPED |
| Tool backend | Kết nối thất bại | Invocation ID, status, side effect evidence | Retry tool nguy hiểm vô hạn |
| Answer parser | Không parse được output bắt buộc | Raw response ref, parser version | Chọn FAIL/ERROR theo ý thích |
| Evaluator | Judge timeout | Judge version, error | Đổi quality verdict thành FAIL |
| Result store | Không lưu được verdict | Attempt ID, persistence error | Báo batch COMPLETED |
| Batch runner | Bị hủy giữa chừng | Case đã làm/chưa làm | Gộp ca chưa chạy vào SKIPPED |

Lỗi schema/output parsing cần một **quy ước từ trước**. Nếu ứng dụng vẫn có raw output để kiểm và schema compliance là một tiêu chí xác định, có thể gán `schemaCompliance=FAIL`. Nếu parser thất bại khiến pipeline không tạo response hợp lệ theo contract, đó có thể là execution ERROR. Không lựa nhãn thuận lợi sau khi thấy kết quả.

### 6.1. Trường hợp 403 có thể là PASS

Nếu ca kiểm thử yêu cầu xác minh người dùng không có quyền xem đơn DH-999, backend từ chối `403` và chatbot giải thích đúng, thì `authorization=PASS`. Mã HTTP 403 trong ca này là **hành vi mong đợi**, không tự động là technical error.

Nếu cùng mã 403 xuất hiện khi user hợp lệ đáng lẽ được phép xem, đó có thể là vi phạm nghiệp vụ hoặc lỗi tích hợp, tùy hợp đồng. Cần đối chiếu expectation và actual events.

### 6.2. Retry không được che giấu lỗi thực thi đã xảy ra

Nếu attempt #1 gặp 429 rồi attempt #2 thành công, có thể chọn kết quả cuối theo retry policy để chấm case. Tuy nhiên, phải giữ retry count, lỗi lịch sử, tổng thời gian và token/chi phí đã phát sinh.

Không được xóa dấu vết 429 chỉ để biểu đồ technical error trông đẹp hơn.

## 7. Bốn trạng thái trong RAG

Giả sử tài liệu `policy-v3#refund-pro` đang hiệu lực quy định hoàn phí trong 14 ngày; `policy-v2#refund-pro` cũ quy định 30 ngày.

| Diễn biến thực tế | Execution | Chấm cần có |
| --- | --- | --- |
| Lấy policy-v3, answer 14 ngày, citation đúng | COMPLETED | Relevance/groundedness/factual correctness PASS |
| Lấy policy-v2 cũ, answer 30 ngày | COMPLETED | Factual correctness FAIL, retrieval freshness FAIL |
| Ca restricted được skip theo policy | SKIPPED | Không có quality verdict |
| VectorStore timeout, không có answer | ERROR | Không thể chấm answer quality |
| Lấy nguồn đúng nhưng thiếu capture effective context | COMPLETED | Groundedness NOT_EVALUATED |
| Trả lời 14 ngày nhưng không có retrieved evidence | COMPLETED | Factual fact có thể đúng; retrieval/groundedness không thể tự PASS |

Một câu trả lời “30 ngày” có thể **relevant** và **grounded theo tài liệu cũ**, nhưng sai theo nguồn hiện hành. Vì thế cần chấm riêng retrieval, relevance, groundedness, factual correctness và citation.

### 7.1. Evidence phục vụ điều tra

Với một ca RAG FAIL, thu:

- `expectedDocumentIds` và reference facts từ dataset.
- `retrievedDocumentIds`, document versions và rank từ attempt.
- `effectiveContextRefs` cho nội dung model thực sự thấy.
- Actual answer và citations.
- Prompt/model/pipeline/corpus/index versions.
- Trace ID, retriever/model spans, usage và lỗi nếu có.

Không thay actual retrieved context bằng tài liệu chuẩn trong dataset khi chấm groundedness: làm vậy che mất lỗi retrieval.

## 8. Tool calling: chấm hành vi chứ không chỉ final answer

Ca `ORDER-001`: user có quyền, backend sandbox cho biết đơn `DH-123` đang ở trạng thái `IN_TRANSIT`.

| Hành vi | Execution | Verdict |
| --- | --- | --- |
| Gọi `getOrderStatus("DH-123")`, dùng kết quả đúng | COMPLETED | PASS các metric bắt buộc |
| Không gọi tool nhưng đoán đúng “đang giao” | COMPLETED | FAIL tool contract |
| Gọi nhầm đơn DH-999 | COMPLETED | FAIL tool arguments/authorization nếu vi phạm |
| Backend từ chối truy cập trái quyền theo đúng policy | COMPLETED | PASS authorization case |
| Tool trả DENIED nhưng model nói “đã truy xuất thành công” | COMPLETED | FAIL tool result handling |
| Tool backend timeout không có output hợp lệ | ERROR | Không chấm answer quality |
| Ca thao tác side effect bị loại ở job không có sandbox | SKIPPED | Không có kết luận chất lượng |

Với tool có tác dụng phụ như `refundOrder`, timeout phía client không chứng minh giao dịch chưa commit. Cần idempotency key, trạng thái backend và sandbox/test doubles trước khi tự động retry.

**Kết quả tool SUCCESS chưa đủ để chấm PASS toàn bộ nghiệp vụ**: kiểm tra quyền, tham số, số lần gọi và hậu điều kiện ở hệ thống nguồn.

## 9. Mẫu số: bốn con số PASS/FAIL/SKIPPED/ERROR không cộng bừa

Giả sử bộ đánh giá có **100 ca được chọn**:

- 5 ca SKIPPED theo plan.
- 95 ca đủ điều kiện và được thử chạy.
- 6 ca TECHNICAL_ERROR, không có output hợp lệ.
- 89 ca COMPLETED.
- Trong 89 ca: 78 ca PASS, 7 ca FAIL, 4 ca NOT_EVALUATED cho ít nhất một metric bắt buộc và chưa có FAIL xác định.

~~~text
Selected:                     100
  SKIPPED:                      5
  Eligible/attempted:          95
    TECHNICAL_ERROR:            6
    COMPLETED:                 89
      Quality PASS:            78
      Quality FAIL:             7
      INCONCLUSIVE:             4
~~~

### 9.1. Các tỷ lệ có mẫu số rõ

**Skip rate trên các ca được chọn:**

\[
\mathrm{skipRate}=\frac{5}{100}=5\%.
\]

**Technical completion trên ca đủ điều kiện:**

\[
\mathrm{technicalCompletion}=\frac{89}{95}\approx93{,}7\%.
\]

**Quality pass rate trên ca được chấm đủ PASS/FAIL:**

\[
\mathrm{qualityPassRate}_{evaluated}=\frac{78}{78+7}
=\frac{78}{85}\approx91{,}8\%.
\]

**Quality evaluation coverage trên các ca COMPLETED:**

\[
\mathrm{coverage}=\frac{85}{89}\approx95{,}5\%.
\]

**Tỷ lệ ca đủ điều kiện đã được xác minh đạt end-to-end:**

\[
\mathrm{verifiedEligibleSuccess}=\frac{78}{95}
\approx82{,}1\%.
\]

Chỉ số cuối là **tỷ lệ được xác minh đạt**, không phải ước lượng chính xác rằng tất cả các ca chưa chấm đều sai. Các ca không có kết luận không được tính là thành công đã xác minh.

| Chỉ số | Giá trị | Mẫu số |
| --- | ---: | --- |
| Selected | 100 | Bộ ca chọn chạy |
| Skipped | 5 | 100 |
| Eligible | 95 | Selected trừ skip |
| Technical error | 6 | 95 |
| Completed | 89 | 95 |
| Evaluated quality | 85 | 89 completed |
| PASS/FAIL | 78/7 | 85 evaluated |
| NOT_EVALUATED | 4 | 89 completed |
| Quality pass rate | 91,8% | 85 |
| Verified eligible success | 82,1% | 95 |

Không được gọi `78/85` là “91,8% toàn bộ production request đã thành công”. Dataset, sampling, eligibility và số chưa chấm cần được giải thích riêng.

## 10. Từ các metric verdict đến kết luận tổng hợp

Một ca có thể đồng thời có nhiều kết quả:

~~~json
{
  "caseId": "REFUND-001",
  "executionStatus": "COMPLETED",
  "metricVerdicts": [
    {"name": "relevance", "status": "PASS", "required": true},
    {"name": "retrievalHitAtK", "status": "PASS", "required": true},
    {"name": "groundedness", "status": "NOT_EVALUATED", "required": true},
    {"name": "factualCorrectness", "status": "FAIL", "required": true},
    {"name": "toolSelection", "status": "NOT_APPLICABLE", "required": false}
  ],
  "aggregateStatus": "FAIL"
}
~~~

Trong trường hợp này, factual correctness FAIL đủ khiến ca tổng hợp FAIL. Groundedness chưa chấm vẫn được giữ nguyên là NOT_EVALUATED, không bị xóa khỏi báo cáo.

### 10.1. Một quy tắc tổng hợp minh bạch

Với execution `COMPLETED`:

1. Nếu **bất kỳ metric bắt buộc** nào FAIL, aggregate = `FAIL`.
2. Nếu không có FAIL, nhưng có metric bắt buộc `PENDING`, `NOT_EVALUATED`, thiếu hoàn toàn hoặc không hợp lệ, aggregate = `INCONCLUSIVE`.
3. Nếu tất cả metric bắt buộc đều PASS, aggregate = `PASS`.
4. `NOT_APPLICABLE` chỉ hợp lệ khi rubric xác nhận metric không áp dụng; đừng dùng nó để bỏ một yêu cầu bắt buộc.
5. Nếu không có metric bắt buộc nào do lỗi định nghĩa test, **không tự gán PASS**.

Với execution `ERROR` hoặc `SKIPPED`, giữ trạng thái thực thi tương ứng. Không tạo verdict chất lượng giả.

### 10.2. FAIL và NOT_EVALUATED có thể cùng tồn tại

Ví dụ ca answer nêu 30 ngày nhưng bộ thu effective context bị lỗi. `factualCorrectness=FAIL` đã có bằng chứng từ answer và nguồn chuẩn, còn `groundedness=NOT_EVALUATED` vì không có context thật.

Aggregate FAIL là đúng, **nhưng báo cáo vẫn phải nêu thiếu context**. Nếu chỉ lưu aggregate FAIL, nhóm có thể bỏ qua lỗi của hệ thống đánh giá/tracing.

### 10.3. Optional metric không đồng nghĩa không quan trọng

Một ca chỉ hỏi đáp không cần tool có thể đặt `toolSelection=NOT_APPLICABLE`, nhưng một bài test security tool là critical thì `authorization` bắt buộc. Phải xác định sự bắt buộc theo **loại ca**, không chỉ theo tên metric toàn cục.

## 11. Schema kết quả: ghi trạng thái và nguyên nhân riêng

Một record cần giữ các định danh và bằng chứng để phân biệt thất bại của ứng dụng với thất bại của evaluator.

~~~json
{
  "runId": "candidate-policy-v2",
  "caseId": "REFUND-001",
  "attemptId": "candidate-policy-v2-REFUND-001-1",
  "datasetVersion": "policy-eval-v3",
  "promptVersion": "prompt-v5",
  "modelVersion": "model-candidate",
  "pipelineVersion": "rag-v2",
  "execution": {
    "status": "COMPLETED",
    "errorStage": null,
    "errorCode": null,
    "traceId": "trace-id-if-present",
    "totalLatencyMs": 1570
  },
  "evaluation": {
    "aggregateStatus": "FAIL",
    "rubricVersion": "policy-rubric-v3",
    "judgeVersion": "judge-v2",
    "metrics": [
      {
        "name": "factualCorrectness",
        "status": "FAIL",
        "reasonCode": "WRONG_POLICY_WINDOW",
        "evidenceRefs": [
          "answer:candidate-policy-v2-REFUND-001-1",
          "reference:policy-v3#refund"
        ]
      },
      {
        "name": "groundedness",
        "status": "NOT_EVALUATED",
        "reasonCode": "EFFECTIVE_CONTEXT_UNAVAILABLE",
        "evidenceRefs": []
      }
    ]
  },
  "usage": {
    "inputTokens": 1400,
    "outputTokens": 120
  }
}
~~~

Đây là **schema do nhóm tự thiết kế**, không phải định dạng Spring AI bắt buộc. Giá trị và ID chỉ minh họa. `traceId` không được tự đặt nếu không có trace thực trong backend.

### 11.1. Các reason code nên có

| Reason code | Loại | Tại sao dùng |
| --- | --- | --- |
| `WRONG_REFERENCE_FACT` | Quality FAIL | Dữ kiện mâu thuẫn nguồn |
| `REQUIRED_SOURCE_MISSING` | Retrieval FAIL | Không lấy được document bắt buộc |
| `TOOL_ARGUMENT_MISMATCH` | Tool FAIL | Sai đối số |
| `FEATURE_DISABLED_BY_PLAN` | SKIPPED | Skip theo chính sách |
| `PROVIDER_TIMEOUT` | Technical ERROR | Không có output hợp lệ |
| `RATE_LIMIT_EXHAUSTED` | Technical ERROR | Hết retry sau 429 |
| `JUDGE_TIMEOUT` | Evaluation ERROR | Bộ chấm không hoàn tất |
| `EFFECTIVE_CONTEXT_UNAVAILABLE` | Evidence gap | Không thể chấm groundedness |

Nên tách `reasonCode` ngắn và ổn định khỏi `feedback` cho con người. Không dùng raw exception messages làm label của metrics hoặc đưa dữ liệu cá nhân/bí mật vào reason.

### 11.2. Lịch sử retry là dữ liệu, không phải rác

Một case có thể có attempt #1 gặp timeout, attempt #2 trả lời hợp lệ. Run policy có thể chấp nhận attempt #2 để xét quality, nhưng không được xóa attempt #1. Các báo cáo vận hành cần biết tổng retry, tổng latency nhìn từ người dùng và chi phí có thể phát sinh trong những lần gọi thất bại.

Với tool có side effect, mọi retry phải tuân theo quyền và tính idempotent ở backend.

## 12. Java: cấu trúc hai trục và quy tắc tổng hợp

Ví dụ sau dùng Java 17+ để định nghĩa trạng thái **độc lập với model provider**. Đây là logic cho test harness, không phải API Spring AI tự tạo.

~~~java
import java.util.List;
import java.util.Objects;

public final class CaseOutcomes {

    public enum ExecutionStatus {
        NOT_STARTED, SKIPPED, RUNNING, COMPLETED, ERROR, CANCELLED
    }

    public enum MetricStatus {
        PENDING, PASS, FAIL, NOT_EVALUATED, NOT_APPLICABLE
    }

    public enum AggregateStatus {
        PASS, FAIL, SKIPPED, TECHNICAL_ERROR,
        INCONCLUSIVE, CANCELLED
    }

    public record MetricVerdict(
            String metric,
            MetricStatus status,
            boolean required,
            String reasonCode) {

        public MetricVerdict {
            Objects.requireNonNull(metric, "metric");
            Objects.requireNonNull(status, "status");
        }
    }

    public record CaseResult(
            String runId,
            String caseId,
            String attemptId,
            ExecutionStatus executionStatus,
            String executionReasonCode,
            List<MetricVerdict> metrics) {

        public CaseResult {
            Objects.requireNonNull(runId, "runId");
            Objects.requireNonNull(caseId, "caseId");
            Objects.requireNonNull(attemptId, "attemptId");
            Objects.requireNonNull(executionStatus, "executionStatus");
            metrics = List.copyOf(Objects.requireNonNull(metrics));
        }
    }

    public static AggregateStatus aggregate(CaseResult result) {
        return switch (result.executionStatus()) {
            case SKIPPED -> AggregateStatus.SKIPPED;
            case ERROR -> AggregateStatus.TECHNICAL_ERROR;
            case CANCELLED -> AggregateStatus.CANCELLED;
            case NOT_STARTED, RUNNING -> AggregateStatus.INCONCLUSIVE;
            case COMPLETED -> aggregateCompleted(result.metrics());
        };
    }

    private static AggregateStatus aggregateCompleted(
            List<MetricVerdict> metrics) {

        List<MetricVerdict> required = metrics.stream()
                .filter(MetricVerdict::required)
                .toList();

        // Không có metric bắt buộc: định nghĩa test chưa đủ.
        if (required.isEmpty()) {
            return AggregateStatus.INCONCLUSIVE;
        }

        if (required.stream().anyMatch(
                m -> m.status() == MetricStatus.FAIL)) {
            return AggregateStatus.FAIL;
        }

        // PASS chỉ khi tất cả metric bắt buộc đã PASS.
        if (required.stream().allMatch(
                m -> m.status() == MetricStatus.PASS)) {
            return AggregateStatus.PASS;
        }

        return AggregateStatus.INCONCLUSIVE;
    }

    private CaseOutcomes() {}
}
~~~

### 12.1. Logic này bảo đảm điều gì?

- Thất bại thực thi được giữ là `TECHNICAL_ERROR`, không tự biến thành quality FAIL.
- SKIPPED và CANCELLED là hai trạng thái riêng.
- Một required metric FAIL làm case tổng hợp FAIL.
- Có required metric chưa chấm mà không có FAIL khác → INCONCLUSIVE.
- Chỉ khi mọi required metric PASS thì ca COMPLETED mới có aggregate PASS.
- Không có required metric không thể tự PASS.

**Lưu ý:** hàm trên là **bộ tổng hợp**, chưa phải bộ validate dữ liệu toàn diện. Hệ thống thực cần đảm bảo `caseId`/`attemptId` duy nhất, kiểm metric bắt buộc đúng theo rubric và không lưu những trạng thái mâu thuẫn.

### 12.2. Adapter chấm bằng Spring AI

Spring AI cung cấp các khái niệm `Evaluator`, `EvaluationRequest`, `EvaluationResponse` và các evaluator cho relevance/fact checking tùy phiên bản. Ví dụ sau nhận evaluator đã được cấu hình, dữ liệu câu trả lời thực và các document thật:

~~~java
import java.util.List;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

public final class SpringAiVerdictAdapter {

    public CaseOutcomes.MetricVerdict scoreGroundedness(
            Evaluator evaluator,
            String question,
            List<Document> effectiveDocuments,
            String actualAnswer) {

        if (question == null || actualAnswer == null
                || effectiveDocuments == null) {
            return new CaseOutcomes.MetricVerdict(
                    "groundedness",
                    CaseOutcomes.MetricStatus.NOT_EVALUATED,
                    true,
                    "EVIDENCE_UNAVAILABLE");
        }

        try {
            EvaluationRequest request = new EvaluationRequest(
                    question, effectiveDocuments, actualAnswer);

            EvaluationResponse response = evaluator.evaluate(request);

            return new CaseOutcomes.MetricVerdict(
                    "groundedness",
                    response.isPass()
                            ? CaseOutcomes.MetricStatus.PASS
                            : CaseOutcomes.MetricStatus.FAIL,
                    true,
                    response.isPass()
                            ? "GROUNDED"
                            : "UNSUPPORTED_CLAIMS");
        } catch (RuntimeException evaluationError) {
            // Lỗi judge không phải là verdict FAIL về nội dung.
            return new CaseOutcomes.MetricVerdict(
                    "groundedness",
                    CaseOutcomes.MetricStatus.NOT_EVALUATED,
                    true,
                    "EVALUATOR_ERROR");
        }
    }
}
~~~

Mã minh họa chỉ chấm một metric và xử lý một số loại lỗi. `effectiveDocuments` phải phản ánh **đúng context đã đưa vào model**. Nếu ứng dụng có bước lọc/nén/cắt context hoặc dùng advisor, cần capture tại đúng ranh giới. `response.isPass()` chỉ là kết luận của evaluator tương ứng, không tự chứng minh factual correctness theo nguồn chuẩn độc lập.

Nếu bộ chấm ném exception, execution của ứng dụng vẫn có thể là COMPLETED; hệ đánh giá lưu `NOT_EVALUATED` cùng `judgeVersion`, lỗi đã được chuẩn hóa và evidence refs.

## 13. Kiểm thử JUnit cho ranh giới PASS/FAIL/SKIPPED/ERROR

Không cần gọi model thật để kiểm thử logic tổng hợp trạng thái.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;

class CaseOutcomesTest {

    private CaseOutcomes.CaseResult result(
            CaseOutcomes.ExecutionStatus execution,
            CaseOutcomes.MetricStatus metric) {

        return new CaseOutcomes.CaseResult(
                "run-1",
                "case-1",
                "attempt-1",
                execution,
                null,
                List.of(new CaseOutcomes.MetricVerdict(
                        "factualCorrectness", metric, true, null)));
    }

    @Test
    void wrongAnswerIsQualityFailEvenIfExecutionCompleted() {
        assertEquals(CaseOutcomes.AggregateStatus.FAIL,
                CaseOutcomes.aggregate(result(
                        CaseOutcomes.ExecutionStatus.COMPLETED,
                        CaseOutcomes.MetricStatus.FAIL)));
    }

    @Test
    void providerTimeoutIsTechnicalError() {
        assertEquals(CaseOutcomes.AggregateStatus.TECHNICAL_ERROR,
                CaseOutcomes.aggregate(result(
                        CaseOutcomes.ExecutionStatus.ERROR,
                        CaseOutcomes.MetricStatus.NOT_EVALUATED)));
    }

    @Test
    void plannedSkipIsNotPass() {
        assertEquals(CaseOutcomes.AggregateStatus.SKIPPED,
                CaseOutcomes.aggregate(result(
                        CaseOutcomes.ExecutionStatus.SKIPPED,
                        CaseOutcomes.MetricStatus.NOT_APPLICABLE)));
    }

    @Test
    void judgeErrorCannotBecomePass() {
        assertEquals(CaseOutcomes.AggregateStatus.INCONCLUSIVE,
                CaseOutcomes.aggregate(result(
                        CaseOutcomes.ExecutionStatus.COMPLETED,
                        CaseOutcomes.MetricStatus.NOT_EVALUATED)));
    }

    @Test
    void completedWithPassingRequiredMetricPasses() {
        assertEquals(CaseOutcomes.AggregateStatus.PASS,
                CaseOutcomes.aggregate(result(
                        CaseOutcomes.ExecutionStatus.COMPLETED,
                        CaseOutcomes.MetricStatus.PASS)));
    }
}
~~~

Các test này kiểm **hàm phân loại**, không khẳng định chatbot trả lời đúng. Khi tích hợp, còn cần test retrieval/document IDs, tool permission/backend, thời gian, schema và quá trình chấm.

### 13.1. Những test biên khác

- Hai metric bắt buộc: một FAIL, một NOT_EVALUATED → aggregate FAIL nhưng giữ cả hai verdict.
- Không có required metric → INCONCLUSIVE.
- Một metric required đánh NOT_APPLICABLE dù nghiệp vụ bắt buộc → kiểm lỗi test definition.
- Một ca SKIPPED là critical → release gate chặn hoặc yêu cầu chạy tại job khác.
- Retry sau timeout → giữ các attempt và chi phí.
- Batch bị hủy → không gán SKIPPED cho những ca chưa lập lịch.

## 14. Chạy lặp khác retry để hồi phục lỗi

**Retry kỹ thuật** dùng khi provider tạm lỗi và chính sách cho phép thử lại. **Repeated evaluation** dùng khi muốn đo tính biến thiên của model/evaluator bằng nhiều attempt có chủ đích.

Ví dụ cùng case được chạy 5 lần, có 3 PASS và 2 FAIL. Không được chọn một PASS để báo “100% đúng”. Tỷ lệ quan sát được là:

\[
\mathrm{passRate}_{repeats}=\frac{3}{5}=60\%.
\]

Nếu một lần chạy bị 429 rồi retry thành công, quality của output cuối có thể PASS; tuy nhiên technical reliability, latency và cost phải phản ánh cả quá trình retry.

Trong tool calling có side effect, không retry mù quáng sau timeout. Timeout ở client không chứng minh giao dịch backend đã thất bại; cần idempotency/hậu điều kiện ở phía tin cậy.

## 15. Batch có concurrency giới hạn: chưa chạy không phải SKIPPED

Với bộ 1.000 ca được chạy đồng thời tối đa 8 attempt, tại một thời điểm có thể có:

| Trạng thái quan sát | Số ca |
| --- | ---: |
| Đã có terminal PASS/FAIL quality | 720 |
| COMPLETED nhưng chờ judge | 80 |
| RUNNING | 25 |
| NOT_STARTED | 150 |
| SKIPPED theo plan | 15 |
| ERROR | 10 |
| **Tổng** | **1.000** |

Không nên báo tỷ lệ PASS cuối cùng khi 150 ca chưa bắt đầu và 80 ca đang chờ chấm.

### 15.1. Trạng thái batch khác trạng thái từng ca

| Run status | Ý nghĩa |
| --- | --- |
| `CREATED` | Có run manifest, dataset và cấu hình |
| `RUNNING` | Batch đang thực thi |
| `COMPLETED` | Mọi ca trong plan có terminal execution outcome được ghi bền vững theo hợp đồng |
| `PARTIAL` | Một số ca chưa được xử lý/ghi kết quả do run dừng giữa chừng |
| `FAILED` | Runner không thể hoàn tất vì lỗi nghiêm trọng |
| `CANCELLED` | Chủ động dừng |

Run `COMPLETED` **không có nghĩa mọi ca PASS**. Nó chỉ xác nhận quá trình thực thi đã được ghi đủ kết quả ở cấp run; việc đánh giá/chấm và release gate là những bước tiếp theo.

### 15.2. Không dùng SKIPPED để làm đẹp điểm

Nếu baseline có 2 ca skip, candidate có 100 ca skip trong cùng dataset, pass rate trên phần còn lại có thể trông tăng dù candidate không cải thiện. Báo cáo cần so danh sách skip theo run, skip reason và nhóm rủi ro.

## 16. Release gate dựa trên chất lượng và coverage

Ví dụ điều kiện phát hành **giả định**, không phải mặc định của Spring AI:

~~~yaml
releaseGate:
  datasetVersion: policy-eval-v3
  rubricVersion: policy-rubric-v2
  coverage:
    criticalCasesSkipped: 0
    criticalCasesNotEvaluated: 0
    minEligibleTechnicalCompletion: 0.99
  aiQuality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    criticalCases: must-pass
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
  toolSafety:
    authorizationAndIdempotency: must-pass
~~~

### 16.1. Ca nào chặn phát hành?

| Tình huống | Quyết định gợi ý |
| --- | --- |
| Một critical factual correctness FAIL | BLOCK |
| Một critical test về quyền SKIPPED ở mọi job | BLOCK |
| Critical case COMPLETED nhưng judge lỗi | BLOCK hoặc yêu cầu review trước khi mở |
| Technical error rate vượt ngưỡng | BLOCK |
| Optional test SKIPPED theo plan được duyệt | Có thể chấp nhận |
| Noncritical quality FAIL | Theo severity/pass rate đã xác định trước |
| p95 latency vượt ngân sách bắt buộc | BLOCK |
| Tool authorization FAIL | BLOCK |

Trong hệ thống rủi ro cao, **thiếu bằng chứng có thể là lý do chặn phát hành** mà không cần gán FAIL cho factual correctness chưa được kiểm. Đây là phân biệt quan trọng giữa **quyết định release** và **kết quả đánh giá một metric**.

## 17. Dùng observability để phân biệt FAIL với ERROR

Spring AI có cơ chế observation dựa trên hệ sinh thái Spring/Micrometer; tùy phiên bản, provider và cấu hình, có thể thu metrics/traces cho `ChatClient`, `ChatModel`, `VectorStore`, Advisors và tool calling.

### 17.1. Trace kỹ thuật thành công nhưng quality FAIL

~~~text
HTTP /ask                        1.250 ms [success]
└── ChatClient                   1.100 ms [success]
    ├── VectorStore retrieval     150 ms [success]
    └── ChatModel                 800 ms [success]

Answer: "30 ngày"
Factual correctness: FAIL
~~~

Đây là ví dụ, không phải trace đã đo thật. Tracing cho biết đường đi thành công; muốn biết answer sai vì sao cần retrieved/effective context, nguồn tham chiếu và rubric.

### 17.2. Trace technical ERROR

~~~text
HTTP /ask                       25.000 ms [error]
└── ChatClient                  24.800 ms [error]
    ├── VectorStore retrieval     150 ms [success]
    └── ChatModel               24.400 ms [timeout]

Execution: ERROR / PROVIDER_TIMEOUT
Factual correctness: NOT_EVALUATED
~~~

Lỗi thuộc runtime/provider. Không có answer để chấm, cần điều tra timeout, rate limit, retry và độ trễ thay vì sửa factual rubric.

### 17.3. Lỗi evaluator sau khi đã tạo answer

~~~text
Generation: COMPLETED, answer persisted
Scoring: judge model timeout

Execution: COMPLETED
Groundedness: NOT_EVALUATED
Reason: JUDGE_TIMEOUT
~~~

Có thể chạy lại judge trên cùng evidence nếu đã lưu đầy đủ. Không cần gọi lại model sinh answer chỉ để xử lý một lỗi bộ chấm.

### 17.4. Các tín hiệu nên theo dõi

- Count theo `executionStatus`, `metricStatus`, `errorStage` và `skipReasonCode`.
- Technical completion rate và judge success/coverage.
- p50/p95/p99 latency, retry, timeout, 429, số lần gọi model/tool.
- Token usage và chi phí ước tính, gồm cả attempt có lỗi khi provider có tính phí.
- Quality pass rate theo dataset version, nhóm rủi ro, prompt/model/pipeline và rubric.
- Tỷ lệ critical cases chưa chấm hoặc bị skip.

Không đưa raw question, user ID, case ID có số lượng rất lớn hoặc trace ID làm metric tags. Dùng thông tin định danh trong evidence store/trace có phân quyền; metrics dùng nhãn có cardinality hữu hạn.

## 18. Bài thực hành phân loại và tổng hợp

**Bối cảnh:** một chatbot Spring AI trả lời chính sách bằng RAG và dùng `getOrderStatus` để đọc trạng thái đơn. Hãy tạo 30 ca gồm câu có nguồn, câu thiếu nguồn, nguồn cũ/mới mâu thuẫn, tool call thành công, tool bị deny và lỗi mô phỏng.

### Bước 1 — Chuẩn hóa trạng thái

Định nghĩa enum execution và evaluation, các reason codes và quy tắc aggregate đã học. Lưu `runId`, `caseId`, `attemptId`, dataset/prompt/model/corpus/rubric versions.

### Bước 2 — Mô phỏng bốn nhóm tình huống

- PASS: answer đúng 14 ngày, đúng nguồn.
- FAIL: answer sai thời hạn, sai tool arguments hoặc tự bịa ngoại lệ.
- SKIPPED: ca được loại từ đầu theo feature/environment policy.
- TECHNICAL_ERROR: provider timeout, 429 hết retry hoặc VectorStore unavailable.

Thêm hai tình huống khó: một ca chấm không được do judge timeout, một ca tool 403 là **hành vi bảo mật đúng**.

### Bước 3 — Thu evidence thật

Với RAG, ghi retrieved documents và effective context. Với tool, ghi actual invocation name/args/status, backend authorization/hậu điều kiện. Ghi errorStage, latency, token và trace ID khi có.

### Bước 4 — Chấm metric độc lập

Chấm relevance, groundedness, factual correctness, retrieval và tool correctness. Nếu không có bằng chứng, dùng NOT_EVALUATED với reason code. Không thay actual context bằng reference context để ép chấm.

### Bước 5 — Tổng hợp và báo cáo

Tạo bảng counts PASS, FAIL, SKIPPED, TECHNICAL_ERROR, INCONCLUSIVE; tính technical completion, evaluated quality pass rate, evaluation coverage và verified success. Chỉ rõ mẫu số của từng tỷ lệ.

### Bước 6 — Kiểm release gate

Định nghĩa ca critical, minimum coverage và ngưỡng kỹ thuật. Xác minh một critical SKIPPED hoặc NOT_EVALUATED không bị coi là PASS.

### Checklist nghiệm thu

- [ ] Execution và evaluation được lưu riêng theo từng ca.
- [ ] Có lý do rõ cho SKIPPED và ERROR.
- [ ] FAIL có evidence, metric và rubric version.
- [ ] NOT_EVALUATED khác NOT_APPLICABLE.
- [ ] Không có metric bắt buộc nào tự PASS khi thiếu bằng chứng.
- [ ] Các ca chưa chạy/chưa hoàn tất không biến thành SKIPPED.
- [ ] Retry history không bị xóa.
- [ ] Báo cáo mọi mẫu số và số ca thiếu nhãn.
- [ ] Có ít nhất một ca HTTP thành công nhưng quality FAIL.
- [ ] Có ít nhất một ca tool 403 nhưng authorization PASS.
- [ ] Có trace hoặc lý do không có trace cho ca điều tra.
- [ ] Critical release gates không bị vượt qua nhờ skip.

### Câu hỏi tự kiểm tra

1. Vì sao HTTP 200 không thể thay cho verdict factual correctness?
2. Model trả answer nhưng judge timeout: execution và evaluation status là gì?
3. Provider trả 429 và hết retry: đây là SKIPPED hay TECHNICAL_ERROR?
4. Tool từ chối 403 khi người dùng không có quyền: khi nào case là PASS?
5. NOT_APPLICABLE khác NOT_EVALUATED ở điểm nào?
6. Trong 100 ca có 5 skip, 6 technical error, 78 PASS, 7 FAIL, 4 chưa chấm, quality pass rate và technical completion được tính thế nào?
7. Vì sao retry thành công vẫn cần lưu lỗi và chi phí của attempt trước?
8. Một answer grounded vào tài liệu cũ nhưng sai nguồn hiện hành nên được chấm ra sao?
9. Nếu mọi critical cases đều bị skip, có được phát hành dựa trên pass rate của các ca khác không?
10. Có thể chặn phát hành vì judge không chấm được mà vẫn không gán factual FAIL không?
11. Vì sao các ca chưa được lập lịch khi batch bị hủy không phải SKIPPED?
12. Nếu một required metric FAIL và một required metric chưa chấm, aggregate là gì và evidence nào phải giữ?

## 19. Những sai lầm phổ biến

**Gom mọi kết quả vào success boolean.** Mất khác biệt giữa câu trả lời sai, provider timeout, judge lỗi và skip.

**Cho mọi 4xx là technical error.** Với security test, 403 có thể là hành vi mong đợi.

**Cho mọi exception là quality FAIL.** Khi không có answer, chất lượng chưa thể chấm; khi judge lỗi, ứng dụng có thể đã hoạt động bình thường.

**Không có FAIL đồng nghĩa PASS.** Nếu mọi ca bị skip hoặc chưa chấm, hoàn toàn thiếu bằng chứng đạt.

**Loại các ca khó khỏi mẫu rồi công bố tỷ lệ PASS cao.** Skip cần policy, reason và gate coverage.

**Chỉ công bố một phần trăm không có mẫu số.** Tỷ lệ trên tập đã chấm không đại diện tự động cho toàn dataset hoặc production.

**Xóa retry sau khi thành công.** Làm sai số liệu reliability, latency và cost.

**Dùng tài liệu chuẩn thay cho context thực khi chấm groundedness.** Che giấu lỗi retrieval.

**Đồng nhất trace success với factual correctness.** Trace mô tả runtime, không phải source of truth.

**Đặt release gate sau khi nhìn thấy điểm.** Các ngưỡng và tiêu chí critical phải được xác định trước.

## 20. Tổng kết

**PASS** là ca đã có bằng chứng và đạt các tiêu chí bắt buộc. **FAIL** là ca đã có bằng chứng về việc không đạt. **SKIPPED** là ca không chạy có chủ đích theo chính sách. **TECHNICAL_ERROR** là thất bại thực thi chưa tạo output hợp lệ để chấm.

Để báo cáo chính xác trong Spring AI, cần giữ cả **execution status** và **evaluation status theo từng metric**. Một request hoàn tất nhưng LLM judge timeout nên được báo `COMPLETED + NOT_EVALUATED`, không ép thành PASS hoặc FAIL ngữ nghĩa. Các trạng thái NOT_APPLICABLE, PENDING, CANCELLED và INCONCLUSIVE cũng có ý nghĩa riêng.

Khi đếm batch hoặc so prompt/model/pipeline, luôn công bố mẫu số, số ca skip, technical errors và các verdict chưa có kết luận. Kết hợp evidence RAG/tool, rubric, traces, metrics, token và chi phí giúp tìm đúng nguyên nhân sự cố và đặt release gate không bị đánh lừa bởi một điểm PASS trung bình đẹp.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring Boot — Actuator](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/)
