# Đặt tên metric và đơn vị đo nhất quán

Một dashboard có thể chứa hàng chục biểu đồ nhưng vẫn gây hiểu lầm nếu tên metric và đơn vị đo không thống nhất. Ví dụ, nhóm A ghi thời gian model phản hồi theo mili giây, nhóm B ghi giây dưới cùng tên latency; một nhóm đếm **model requests**, nhóm khác đếm **tác vụ người dùng**; chỉ số accuracy có nơi được biểu diễn bằng 0,87, nơi khác bằng 87. Những số liệu ấy không thể so sánh trực tiếp, dù biểu đồ có vẻ hợp lý.

Đối với module **SPRING_AI_EVALUATION_OBSERVABILITY**, việc đánh giá chất lượng ứng dụng Spring AI bao gồm tập dữ liệu, tiêu chí **relevance**, **fact checking**, luồng **RAG** và **tool calling**. Metrics cần liên kết với traces, chi phí và độ trễ để giải thích nguyên nhân suy giảm khi thay prompt, model hoặc pipeline. Vì vậy, tên metric phải diễn đạt chính xác **điều gì được đo**, **một mẫu tương ứng với đối tượng nào**, **giá trị được ghi bằng đơn vị gì** và **khi nào được ghi**.

Bài này thuộc chương **Thiết kế metric** và tập trung xây dựng một **hợp đồng ngữ nghĩa metric** (metric semantic contract): quy tắc tên, đơn vị, tags, điểm ghi nhận, cách tổng hợp và kiểm tra hồi quy. Những ví dụ có tiền tố app.ai là quy ước **tự thiết kế của dự án**, không phải tên metric mặc định của Spring AI.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa một metric đủ rõ bằng **tên, loại meter, đơn vị, đối tượng đo, nguồn, thời điểm ghi, tags và quy tắc tổng hợp**.
2. Thiết kế bộ tên nhất quán cho model, tool, RAG, evaluator và trạng thái nghiệp vụ.
3. Phân biệt giây, mili giây, token, byte, document, chunk, điểm chất lượng, tỷ lệ và tiền tệ.
4. Giữ tách biệt số lần gọi model, số lần gọi tool, số tác vụ người dùng và số ca đánh giá.
5. Đăng ký Counter, Timer, DistributionSummary, Gauge qua Micrometer theo cùng một metric dictionary.
6. Hiểu vì sao tên meter trong Java có thể được đổi khi export sang Prometheus và vì sao không cộng/trung bình trực tiếp các percentile.
7. Kiểm tra schema metric và chặn các thay đổi đơn vị, mẫu số, tags gây lỗi cho dashboard hoặc báo cáo hồi quy.

## 2. Một con số chưa phải metric có thể sử dụng

Xét hai dòng:

~~~text
latency  = 350
accuracy = 0.87
~~~

Chúng thiếu các thông tin quan trọng:

- **350 là ms hay s?** Từ lúc nhận yêu cầu đến token đầu tiên, đến câu trả lời cuối hay đến khi backend hoàn tất?
- **0,87 là điểm hay tỷ lệ?** Độ liên quan của một đoạn tài liệu, hay 87% ca đạt oracle?
- **Một mẫu là gì?** Một model request, tool execution, lượt RAG, conversation turn hay toàn bộ scenario?
- **Nguồn nào phát số liệu?** Framework, backend, test runner, một evaluator hay một phép suy từ văn bản?
- **Có bao gồm ca lỗi và timeout không?** Nếu chỉ đo thành công thì p95 có thể bị thiên lệch.
- **Có thể cộng/tính rate/tính trung bình không?** Phụ thuộc loại meter và ý nghĩa.

Do đó, mỗi metric nên có một bản hợp đồng ít nhất gồm:

| Thuộc tính | Câu hỏi | Ví dụ |
| --- | --- | --- |
| name | Đại lượng nào? | app.ai.tool.execution.duration |
| meter_type | Đếm, thời lượng, phân bố hay trạng thái? | Timer |
| observation_unit | Mỗi mẫu đại diện cho gì? | Một handler invocation |
| base_unit | Giá trị có đơn vị nào? | Duration |
| start/end hoặc record_event | Ghi khi nào? | Từ dispatch đến handler kết thúc |
| tags | Các chiều phân nhóm hữu hạn nào? | tool_family, outcome |
| source_of_truth | Nguồn ghi nhận là gì? | Tool execution wrapper |
| missing_policy | Thiếu dữ liệu thì sao? | Không ghi giả bằng 0 |
| aggregation | Có thể tính chỉ số nào? | p95 từ histogram |
| contract_version | Ngữ nghĩa được quản lý ra sao? | v1 |

### Ví dụ một tác vụ có nhiều cấp quan sát

~~~mermaid
flowchart LR
    A["1 user task"] --> B["Model request 1"]
    B --> C["Tool request A"]
    B --> D["Tool request B"]
    C --> E["Model request 2"]
    D --> E
    E --> F["1 final answer"]
    F --> G["1 evaluation case-run"]
~~~

Một tác vụ ở ví dụ có **1 user task**, **2 model requests**, **2 tool requests** và **1 case-run được chấm**. Không thể dùng tất cả các số này với tên chung ai.requests rồi coi chúng có cùng mẫu số. Một lời gọi bị dispatcher từ chối thậm chí có thể khiến số **tool requests** lớn hơn số **tool executions**.

**Nguyên tắc:** tên và mô tả metric phải gắn với đúng đối tượng đo, không chỉ gắn với tên công nghệ.

## 3. Quy tắc đặt tên metric

Một quy ước đơn giản cho custom metric:

~~~text
<namespace>.<domain>.<object>.<measure>

app.ai.eval.case.completed
app.ai.eval.relevance.score
app.ai.eval.fact_check.completed
app.ai.model.request.duration
app.ai.model.token.usage
app.ai.tool.call.proposed
app.ai.tool.execution.duration
app.ai.rag.retrieval.duration
app.ai.rag.retrieval.documents
app.ai.tool.inflight
app.ai.operation.pending
~~~

Trong đó:

- **namespace:** xác định nhóm ứng dụng sở hữu metric, ví dụ app.ai.
- **domain:** eval, model, tool, rag hoặc operation.
- **object:** case, request, execution, retrieval, token...
- **measure:** completed, duration, score, usage, documents, pending...

Đây chỉ là cách đặt tên mẫu. Nếu ứng dụng đã có quy ước telemetry ở tổ chức hoặc các meter tiêu chuẩn do Spring AI/Micrometer phát ra đáp ứng đúng nhu cầu, nên **tái sử dụng** trước khi tạo metric mới.

### 3.1. Một tên phải có một ngữ nghĩa ổn định

| Tên mơ hồ | Tên rõ hơn | Lý do |
| --- | --- | --- |
| ai.latency | app.ai.model.request.duration | Chỉ rõ thời lượng của một lần gọi model |
| ai.total | app.ai.eval.case.completed | Chỉ rõ số ca đánh giá đã có verdict |
| ai.quality | app.ai.eval.relevance.score | Chỉ rõ loại điểm đang đo |
| rag.docs | app.ai.rag.retrieval.documents | Chỉ rõ số tài liệu trả về mỗi retrieval |
| tool.fail | app.ai.tool.execution.failed | Chỉ rõ lỗi thực thi, không phải lỗi chọn tool |
| app.pending | app.ai.operation.pending | Chỉ rõ trạng thái nghiệp vụ đang chờ |

Đừng dùng cùng tên duration cho hai phép đo: **time to first token** và **time to full response**. Nếu cả hai quan trọng, cần hai metric có ngữ nghĩa rõ ràng.

### 3.2. Không nhét ID và nội dung riêng lẻ vào tên

Không nên tạo:

~~~text
app.ai.order_A123.latency
app.ai.user_U123.prompt_v45.response
app.ai.rag_document_778.relevance
~~~

Những tên này gắn với một người dùng hoặc một lần chạy, khó tổng hợp và có thể lộ dữ liệu. Dùng tags hữu hạn để phân nhóm, còn **case_id, run_id, user_id, trace_id, order_id** nằm trong dữ liệu đánh giá hoặc trace/log có kiểm soát.

### 3.3. Tên Java không phải lúc nào cũng là tên series xuất ra

Trong mã Micrometer, ứng dụng đăng ký một tên logic như:

~~~text
app.ai.model.request.duration
~~~

Khi chuyển sang Prometheus, naming convention có thể đổi dấu chấm thành gạch dưới và thêm hậu tố loại meter hoặc đơn vị như **_seconds**, **_total**, **_bucket**, **_sum** hay **_count**. Cách xuất khác nhau theo registry và phiên bản.

**Không tự gắn mọi hậu tố của Prometheus vào tên Java** rồi giả định exporter sẽ giữ nguyên. Trước khi viết dashboard, kiểm tra tên series thực tế trong endpoint metrics hoặc backend.

## 4. Đơn vị đo nhất quán

| Đại lượng | Đơn vị hợp đồng gợi ý | Ví dụ |
| --- | --- | --- |
| Thời lượng | Duration; thông thường xuất theo giây ở Prometheus | 0,750 s |
| Token usage | tokens | 1.250 tokens |
| Dung lượng | bytes | 2.048 bytes |
| Số tài liệu | documents | 5 documents |
| Số đoạn | chunks | 8 chunks |
| Số lần gọi | calls | 3 calls |
| Số ca đánh giá | cases | 100 cases |
| Relevance score | Giá trị không đơn vị trong [0,1] | 0,86 |
| Pass/error rate | Tỷ số không đơn vị trong [0,1] | 0,12 |
| Phần trăm hiển thị | % sau khi nhân tỷ số với 100 | 12% |
| Chi phí | Một tiền tệ xác định, ví dụ USD | 0,0025 USD |
| Tốc độ xử lý | requests/second hoặc cases/second | 18 cases/s |

### 4.1. Thời gian: ms, µs, ns và s

Một tool có thể trả **250 ms**, một thư viện đo **250.000.000 ns**, backend Prometheus hiển thị **0,250 seconds**. Ba con số có cùng ý nghĩa nếu được chuyển đúng:

\[
250\,\mathrm{ms}=0{,}250\,\mathrm{s}=250\,000\,000\,\mathrm{ns}
\]

Với Micrometer, dùng Timer và kiểu **Duration** hoặc API nhận thời gian kèm TimeUnit, tránh ghi một số không kèm đơn vị:

~~~java
import java.time.Duration;
import io.micrometer.core.instrument.Timer;

long elapsedMilliseconds = 250L; // đơn vị từ API nguồn
Timer timer = Timer.builder("app.ai.tool.execution.duration")
        .description("Tool handler duration")
        .register(registry);

timer.record(Duration.ofMillis(elapsedMilliseconds));
~~~

Nếu nhầm lẫn và ghi 250 theo giây, thời gian bị phóng đại **1.000 lần**. Không nên đổi đơn vị bằng cách chia/nhân thủ công ở nhiều lớp nếu một nơi chuẩn hóa có thể xử lý đầy đủ.

Khi có streaming, xác định riêng **time to first token** và **time to full response**. Khi tool gọi backend bất đồng bộ, xác định riêng thời gian **ACCEPTED** và thời gian **business completion**.

### 4.2. Điểm chất lượng khác tỷ lệ đạt

Một evaluator trả **relevance score = 0,86** cho một ca RAG. Đó là điểm trong miền 0–1, không phải bằng chứng rằng **86% ca đã chính xác**. Pass rate phải lấy từ **số ca PASS** chia cho một mẫu số đã định.

Nếu muốn hiển thị 0,86 thành 86%, dashboard được phép thực hiện phép đổi hiển thị, nhưng meter gốc vẫn phải luôn dùng một miền nhất quán. Không đưa lẫn điểm 0,86 và 86 vào cùng DistributionSummary.

Nếu evaluator thay rubric hoặc đổi từ miền 0–1 sang 0–100, phải chuyển đổi có chủ đích hoặc phiên bản hóa hợp đồng; không lặng lẽ ghi dữ liệu mới vào chuỗi cũ.

### 4.3. Documents, chunks và tokens

Trong một lần RAG, **2 tài liệu** có thể tạo **5 chunks**, tương đương **1.100 tokens** sau khi định dạng context. Đây là ba đại lượng khác nhau.

~~~text
app.ai.rag.retrieval.documents  -> sample 2
app.ai.rag.retrieval.chunks     -> sample 5
app.ai.model.token.usage       -> sample 1100
~~~

Không dùng cùng tên retrieved_items cho cả số document và số chunk. Với token, nếu model provider không trả usage, đánh dấu **unknown** hoặc thiếu quan sát; không tự điền 0.

### 4.4. Tiền tệ và chi phí ước tính

Chi phí có thể được tính từ số token cùng bảng giá model, cộng phí API ngoài nếu hợp đồng yêu cầu. Khi thiết kế metric:

1. Ghi rõ tiền tệ (ví dụ **USD**) và phạm vi phí (model-only, retrieval, tool external, end-to-end).
2. Phân biệt **estimated cost** từ **billed cost** khi đơn vị cung cấp có giá khác thực tế.
3. Không cộng USD với VND khi chưa quy đổi theo một tỷ giá và thời điểm được lưu.
4. Không dùng số đã làm tròn để làm căn cứ đối soát tài chính; metric tổng hợp không thay ledger.
5. Nếu thiếu usage hoặc đơn giá, trả **UNKNOWN**, không coi chi phí bằng 0.

Một DistributionSummary có thể nhận chi phí USD của từng request để xem tổng và phân bố, nhưng định dạng giá, làm tròn và quy tắc quy đổi phải được ghi trong metric dictionary.

## 5. Đơn vị quan sát và mẫu số

Trong một yêu cầu Spring AI, các số này có thể khác nhau:

| Đơn vị quan sát | Ví dụ | Không đồng nhất với |
| --- | --- | --- |
| User task | Một yêu cầu của người dùng | Model request |
| Conversation turn | Một lượt người dùng nói | Toàn bộ conversation |
| Model request | Một lần gọi model/provider | Tool call |
| Tool request | Model đề nghị công cụ | Tool execution |
| Tool execution | Handler thực sự chạy | Business completion |
| Retrieval | Một lần tìm kiếm dữ liệu | Số document/chunk tìm được |
| Case-run | Một ca đã chạy và chấm | Mỗi lần retry trong ca |
| Business operation | Một thao tác có operation ID | HTTP response thành công |

Ví dụ model đề nghị 3 tool calls, dispatcher chặn 1, hai handler còn lại chạy, nhưng chỉ có 1 tác động nghiệp vụ hoàn tất. Nếu đặt tất cả dưới một tên tool_success_total, ta sẽ không biết **3**, **2** và **1** khác nhau vì đâu.

### 5.1. Pass rate và coverage

Thay vì ghi một giá trị accuracy tùy ý sau mỗi lần chạy, bộ chấm có thể tạo các sự kiện verdict và tính:

\[
\text{Pass rate trên ca chấm được}
=\frac{N_\mathrm{PASS}}{N_\mathrm{PASS}+N_\mathrm{FAIL}}
\]

\[
\text{Coverage}
=\frac{N_\mathrm{PASS}+N_\mathrm{FAIL}}
{N_\mathrm{PASS}+N_\mathrm{FAIL}+N_\mathrm{INCONCLUSIVE}}
\]

Với 100 ca gồm 72 PASS, 18 FAIL và 10 INCONCLUSIVE:

- Pass rate trên ca có kết luận: **72/90 = 80%**.
- Coverage: **90/100 = 90%**.
- Verified success trên toàn tập: **72/100 = 72%**.

Ba số liệu đều đúng nhưng có **nghĩa và mẫu số khác nhau**. Dashboard phải ghi rõ tên tỷ lệ, đơn vị hiển thị và cách xử lý nhóm không thể chấm.

### 5.2. Đếm một verdict cuối cho mỗi case-run

Một ca có thể retry tool, gọi model nhiều lần hoặc chạy qua các nhánh RAG. Nếu quy tắc yêu cầu một kết quả cuối, chỉ tăng Counter **sau khi oracle đưa ra verdict cuối cùng**. Retry được đo riêng. Một lần chạy lại cùng dataset ở phiên bản model khác là **case-run mới**, không phải một bước nội bộ của case-run cũ.

Nếu cần sửa nhãn một kết quả lịch sử, dùng kho kết quả có thể tái tổng hợp thay vì cố trừ Counter (Counter không có ngữ nghĩa trừ).

## 6. Chọn meter phù hợp với tên và đơn vị

| Câu hỏi | Tên logic gợi ý | Loại meter | Đơn vị |
| --- | --- | --- | --- |
| Bao nhiêu ca có verdict cuối? | app.ai.eval.case.completed | Counter | cases |
| Bao nhiêu lần tool bị lỗi? | app.ai.tool.execution.failed | Counter | calls |
| Model phản hồi mất bao lâu? | app.ai.model.request.duration | Timer | duration |
| Tool handler mất bao lâu? | app.ai.tool.execution.duration | Timer | duration |
| Một model request dùng bao nhiêu token? | app.ai.model.token.usage | DistributionSummary | tokens/sample |
| Mỗi retrieval lấy bao nhiêu tài liệu? | app.ai.rag.retrieval.documents | DistributionSummary | documents/sample |
| Relevance score của mỗi ca? | app.ai.eval.relevance.score | DistributionSummary | score [0,1] |
| Hiện đang chạy bao nhiêu tool? | app.ai.tool.inflight | Gauge | calls đang chạy |
| Hiện còn bao nhiêu operation chờ? | app.ai.operation.pending | Gauge | operations |

**Counter** tăng khi sự kiện xảy ra; **Gauge** phản ánh trạng thái hiện tại và có thể giảm. **Timer** ghi duration, thường đã có count; không nhất thiết tạo Counter thứ hai chỉ để đếm cùng các lượt thực thi. **DistributionSummary** ghi phân bố giá trị không phải thời lượng như số token hoặc điểm số.

Một Summary nhận mỗi lượt retrieval một sample **5 documents**: đơn vị vật lý là documents, còn "documents per retrieval" là cách xác định **một sample**. Không nên ghi đơn vị chuỗi là "documents/second" khi nó thực chất là số tài liệu trả về trong một lần gọi.

## 7. Thiết kế tags và cardinality

Tags là chiều phân nhóm, không phải chỗ chứa mọi chi tiết của một yêu cầu.

| Tag | Tập giá trị hữu hạn gợi ý | Ý nghĩa |
| --- | --- | --- |
| case_type | rag, tool, multi_turn, no_tool, other | Nhóm ca |
| verdict | pass, fail, inconclusive | Kết quả oracle |
| component | model, tool, retrieval, evaluator | Thành phần |
| outcome | success, error, timeout, cancelled | Kết quả thực thi |
| tool_family | retrieval, order, payment, other | Nhóm công cụ |
| error_class | auth, validation, transient, business, other | Nhóm lỗi |
| environment | eval, staging, production | Môi trường |

Không gắn giá trị nguyên văn như **user_id, order_id, prompt, conversation_id, case_id, run_id, trace_id, URL tùy ý, tên tài liệu RAG** vào metric tags. Những giá trị này có thể tăng không giới hạn, chứa thông tin nhạy cảm và gây chi phí lớn. Lưu chúng trong trace, audit hoặc kho kết quả có phân quyền.

### Cardinality nhân theo số chiều

Giả sử tool_family có 5 giá trị, outcome có 4, environment có 3 và model_group có 4. Một metric có thể sinh **5 × 4 × 3 × 4 = 240** tổ hợp trước khi tính histogram buckets hoặc nhãn bổ sung. Nếu thêm user_id với 100.000 giá trị, cardinality có thể tăng rất mạnh.

Chỉ thêm một tag nếu có truy vấn, cảnh báo hoặc nhu cầu phân tầng rõ. Khi phải so sánh prompt/model version có hàng nghìn biến thể, nên lưu version chi tiết trong metadata run và trace; chỉ phát một nhãn release cohort hữu hạn nếu thật sự hữu ích trên dashboard.

### Phân biệt các nhãn có nghĩa khác nhau

**outcome** của tool execution có thể là success trong khi **verdict** của bộ đánh giá là fail vì câu trả lời không grounded. Không dùng một tag "status" cho cả hai khái niệm.

Chọn một bộ giá trị thống nhất, ví dụ verdict = pass | fail | inconclusive. Tránh cùng một ý nghĩa nhưng nơi dùng PASS, nơi dùng ok, nơi dùng 1, khiến truy vấn sai hoặc bỏ sót chuỗi.

## 8. Đặt tên cho từng tầng Spring AI

### 8.1. Tool request khác tool execution

Một model có thể đề nghị tool, dispatcher chặn vì quyền, và backend không thực hiện gì:

~~~text
tool.call.proposed = 1
tool.call.denied   = 1
tool.execution     = 0
~~~

Khi cần metric riêng, đặt tên thể hiện **lúc model đề nghị**, **lúc dispatcher quyết định**, và **lúc handler thực thi**. Không suy luận rằng model không từng đề nghị gọi chỉ vì thiếu event trong Java method.

### 8.2. Accepted khác completed

Một công cụ trả **ACCEPTED** cho yêu cầu hoàn tiền nhưng tiền còn PENDING:

~~~text
Accepted requests:             1
Verified completed operations: 0
Current pending operations:    1
~~~

Các phép đo này có **đơn vị và nguồn khác nhau**: số request accepted là event Counter; số business completions là Counter nghiệp vụ; pending hiện tại có thể là Gauge nếu nguồn trạng thái đáng tin. Không gọi HTTP 200 là verified success.

### 8.3. Relevance khác groundedness và fact checking

Trong RAG, tài liệu có thể liên quan đến câu hỏi nhưng đã hết hiệu lực:

- Retrieval relevance có thể cao.
- Groundedness so với đoạn trích cũ có thể cao.
- Source freshness không đạt.
- Factual correctness theo chính sách hiện hành có thể FAIL.

Đừng ghi tất cả thành một metric quality_score mà không có rubric. Nên có metric khác nhau theo tiêu chí, chẳng hạn:

~~~text
app.ai.eval.relevance.score
app.ai.eval.groundedness.score
app.ai.eval.fact_check.completed
app.ai.eval.source_freshness.completed
~~~

Score là phân bố giá trị trong miền xác định. Counter completed theo verdict chỉ đếm kết quả đánh giá. Cần giữ phiên bản rubric nếu việc chấm thay đổi.

### 8.4. Conversation turn khác trajectory

Một hội thoại có 5 lượt, trong đó 4 lượt đúng và lượt cuối gọi tool ghi dữ liệu trái ý định. **Turn accuracy** có thể 80%, nhưng **scenario success** phải FAIL nếu hợp đồng yêu cầu mọi bất biến đều đạt. Vì thế tách metric cấp lượt và cấp scenario, không dùng chung tên và mẫu số.

## 9. Metric dictionary và quản lý phiên bản

Một danh mục metric giúp đội phát triển, evaluator và vận hành thống nhất ý nghĩa trước khi viết code. Ví dụ đặc tả tự thiết kế bằng YAML (không phải cấu hình được Micrometer tự đọc):

~~~yaml
contract_version: v1
name: app.ai.eval.case.completed
meter_type: counter
base_unit: cases
observation_unit: case-run
record_at: after_final_oracle_verdict
source: evaluation_runner
tags:
  case_type: [rag, tool, multi_turn, no_tool, other]
  verdict: [pass, fail, inconclusive]
invariants:
  - Một verdict cuối cho mỗi case-run
  - Không tăng theo từng tool retry hoặc model request
  - Không gắn case_id, run_id, user_id làm metric tag
missing_data:
  - Thiếu bằng chứng thì ghi verdict inconclusive
aggregation:
  - Tính pass rate trên pass và fail có thể chấm
  - Báo riêng coverage gồm cả inconclusive
owner: evaluation_platform
~~~

### Những thay đổi dễ phá vỡ hợp đồng

- Đổi **đơn vị từ ms sang s** nhưng giữ nguyên dữ liệu cũ mà không chuyển đổi.
- Đổi đối tượng đo từ **model request** sang **user task**.
- Đổi "success" từ **HTTP 200** sang **verified business outcome**.
- Đổi miền relevance score từ **0–1** sang **0–100**.
- Đổi cách xử lý INCONCLUSIVE trong mẫu số.
- Đổi tên/ý nghĩa tags mà không cập nhật dashboard.
- Đổi cách tính chi phí từ estimated sang billed nhưng giữ cùng nghĩa.

Khi đổi ngữ nghĩa không tương thích, cần cập nhật phiên bản hợp đồng, đổi tên metric hoặc có giai đoạn chuyển tiếp rõ ràng. Không nên gộp chuỗi dữ liệu cũ và mới rồi kết luận chất lượng thay đổi do prompt/model.

## 10. Java Micrometer: đặt tên và đơn vị ngay tại điểm ghi

Ví dụ dưới đây ghi các metric tự định nghĩa ở **ranh giới quan sát của một ứng dụng Spring AI**. Lớp này không tự quyết định model phải gọi tool gì và cũng không thay thế ChatMemory. Ứng dụng cung cấp sự kiện thực thi, usage từ provider và verdict đã được oracle xác minh.

~~~java
import java.util.Locale;
import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class AiMetricContractRecorder {

    public enum Verdict {
        PASS, FAIL, INCONCLUSIVE
    }

    private final MeterRegistry registry;
    private final AtomicInteger inFlightToolCalls =
            new AtomicInteger();

    public AiMetricContractRecorder(MeterRegistry registry) {
        this.registry = registry;

        // Một Gauge gắn với đối tượng có vòng đời đủ dài.
        Gauge.builder("app.ai.tool.inflight",
                        inFlightToolCalls, AtomicInteger::get)
                .description("Executing tool calls")
                .baseUnit("calls")
                .register(registry);
    }

    private static String caseType(String raw) {
        if ("rag".equals(raw)
                || "tool".equals(raw)
                || "multi_turn".equals(raw)
                || "no_tool".equals(raw)) {
            return raw;
        }
        return "other";
    }

    private static String toolFamily(String raw) {
        if ("retrieval".equals(raw)
                || "order".equals(raw)
                || "payment".equals(raw)) {
            return raw;
        }
        return "other";
    }

    // Một verdict cuối trên mỗi lần chạy ca.
    public void recordCaseResult(
            String rawCaseType,
            Verdict verdict
    ) {
        Counter.builder("app.ai.eval.case.completed")
                .description("Case runs with a final verdict")
                .baseUnit("cases")
                .tag("case_type", caseType(rawCaseType))
                .tag("verdict", verdict.name()
                        .toLowerCase(Locale.ROOT))
                .register(registry)
                .increment();
    }

    // Mỗi model request có thể sinh mẫu usage input/output.
    public void recordTokenUsage(
            String direction,
            long tokens
    ) {
        if (tokens < 0) {
            throw new IllegalArgumentException(
                    "Token usage must be non-negative");
        }
        if (!"input".equals(direction)
                && !"output".equals(direction)) {
            throw new IllegalArgumentException(
                    "Direction must be input or output");
        }

        DistributionSummary.builder("app.ai.model.token.usage")
                .description("Tokens per model request")
                .baseUnit("tokens")
                .tag("direction", direction)
                .register(registry)
                .record(tokens);
    }

    // Điểm relevance phải nằm trong [0, 1].
    public void recordRelevanceScore(
            String rawCaseType,
            double score
    ) {
        if (!Double.isFinite(score)
                || score < 0.0 || score > 1.0) {
            throw new IllegalArgumentException(
                    "Relevance score must be in [0, 1]");
        }

        DistributionSummary.builder("app.ai.eval.relevance.score")
                .description("Relevance score per graded sample")
                .tag("case_type", caseType(rawCaseType))
                .register(registry)
                .record(score);
    }

    // Timer đo một tool invocation đồng bộ kể cả khi xảy ra lỗi.
    public <T> T observeToolExecution(
            String rawToolFamily,
            Callable<T> operation
    ) throws Exception {
        String family = toolFamily(rawToolFamily);
        Timer.Sample sample = Timer.start(registry);
        inFlightToolCalls.incrementAndGet();

        String outcome = "success";
        try {
            return operation.call();
        } catch (Exception ex) {
            outcome = "error";
            throw ex;
        } catch (Error fatal) {
            outcome = "error";
            throw fatal;
        } finally {
            try {
                sample.stop(Timer.builder(
                                "app.ai.tool.execution.duration")
                        .description("Tool execution duration")
                        .tag("tool_family", family)
                        .tag("outcome", outcome)
                        .register(registry));
            } finally {
                inFlightToolCalls.decrementAndGet();
            }
        }
    }

    public int currentInFlight() {
        return inFlightToolCalls.get();
    }
}
~~~

Ví dụ sử dụng với registry trong bộ kiểm thử:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

var registry = new SimpleMeterRegistry();
var metrics = new AiMetricContractRecorder(registry);

String response = metrics.observeToolExecution(
        "retrieval", () -> "policy-v2026");

metrics.recordTokenUsage("input", 1200L);
metrics.recordTokenUsage("output", 150L);
metrics.recordRelevanceScore("rag", 0.86);

// Chỉ ghi verdict sau khi oracle quyết định.
metrics.recordCaseResult(
        "rag", AiMetricContractRecorder.Verdict.PASS);

double passCount = registry.find("app.ai.eval.case.completed")
        .tags("case_type", "rag", "verdict", "pass")
        .counter()
        .count();

System.out.println(response);
System.out.println("PASS count: " + passCount);
System.out.println("In-flight: " + metrics.currentInFlight());
~~~

**Kết quả mong đợi theo fixture:** Counter PASS tăng một; DistributionSummary có một mẫu input=1.200, output=150, relevance=0,86; Timer có một mẫu thời lượng thực thi; Gauge in-flight trở về 0.

**SimpleMeterRegistry** chỉ minh họa chức năng trong JVM, không tự cấu hình exporter production. Trong Spring Boot, thường tiêm **MeterRegistry** đã được ứng dụng cấu hình. Trước khi thêm custom metric, xem ứng dụng và Spring AI/Micrometer đã phát metric cùng nghĩa chưa.

### Những ranh giới quan trọng của mã

- **Counter:** ứng dụng bảo đảm một verdict cuối cho mỗi case-run. Lớp này không tự phát hiện ca trùng.
- **Summary token:** chỉ gọi khi provider thật sự có usage; thiếu usage không được giả làm 0.
- **Summary relevance:** từ chối giá trị âm, vượt 1 hoặc không hữu hạn.
- **Timer:** đo lời gọi đồng bộ và ghi cả nhánh lỗi; đo việc backend hoàn tất phải dùng nguồn nghiệp vụ khác.
- **Gauge:** AtomicInteger được giữ tham chiếu sống; việc gọi bất đồng bộ cần giảm in-flight khi công việc thực sự kết thúc.
- **Tags:** dùng tập giá trị hữu hạn, không chứa prompt, user ID hoặc tool name không được quản lý.

Trong production, error class có thể cần phân thành timeout/cancelled/business/transient, nhưng phải dùng một taxonomy thống nhất; không đưa message của exception làm tag. Khi đo nhiều request song song hoặc pipeline bất đồng bộ, cần instrumentation và correlation ID tương ứng.

## 11. Kiểm tra tên series sau khi export

Micrometer dùng tên logic trong mã Java, còn Prometheus và các backend khác có naming convention và base units riêng. Ví dụ một Timer trong mã có thể được exporter thể hiện thành các series mang hậu tố **_seconds**; một Counter có thể mang hậu tố **_total**; Summary có thể phát **_count** và **_sum**.

Các truy vấn dưới đây **chỉ minh họa cú pháp trên một bộ tên series giả định**. Cần kiểm tra endpoint export thực tế của registry đang dùng trước khi dùng trên dashboard.

### 11.1. Số ca PASS mỗi giây

~~~promql
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict="pass"}[5m]
))
~~~

Đơn vị kết quả là **cases/second**, không phải pass rate. Tính pass rate trên ca có verdict xác định:

~~~promql
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict="pass"}[5m]
))
/
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict=~"pass|fail"}[5m]
))
~~~

Phải xử lý mẫu số bằng 0 và chọn cùng case_type/environment ở cả tử và mẫu. Nếu mẫu số thay đổi vì nhóm INCONCLUSIVE tăng, cần xem thêm coverage.

### 11.2. Coverage

~~~promql
sum(rate(
  app_ai_eval_case_completed_cases_total{verdict=~"pass|fail"}[5m]
))
/
sum(rate(app_ai_eval_case_completed_cases_total[5m]))
~~~

Giá trị gốc là **tỷ số trong [0,1]**; nếu dashboard muốn hiển thị phần trăm thì nhân 100 và ghi nhãn %. Không được hiển thị giá trị 0,9 với nhãn 0,9%.

### 11.3. p95 thời gian tool từ histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, tool_family) (
    rate(app_ai_tool_execution_duration_seconds_bucket[5m])
  )
)
~~~

Truy vấn chỉ có kết quả nếu histogram buckets được cấu hình và export. Đơn vị của kết quả minh họa là **giây**. Đừng nhân thành milliseconds rồi để nhãn giây. Nếu histogram chưa được bật, cần cấu hình tại Timer có chủ đích theo SLO và ngân sách lưu trữ.

Không lấy trung bình các giá trị p95 từng instance để ra p95 chung. Có thể tổng hợp **histogram buckets** theo những chiều hợp lệ rồi ước lượng quantile, trong khi các percentile đã tính riêng thường không cộng gộp trực tiếp được.

### 11.4. Token trung bình trên một model request

Với một Summary có baseUnit=tokens, exporter có thể tạo các series mang hậu tố tương tự:

~~~promql
sum(rate(
  app_ai_model_token_usage_tokens_sum{direction="input"}[5m]
))
/
sum(rate(
  app_ai_model_token_usage_tokens_count{direction="input"}[5m]
))
~~~

Tử số là **tokens/second**; mẫu số là **requests/second của các mẫu có usage**. Thương số là **tokens/request**. Nếu nhiều provider requests không có token usage, phép đo không đại diện cho toàn bộ lưu lượng: cần báo **usage coverage**.

### 11.5. Gauge in-flight

~~~promql
sum(app_ai_tool_inflight_calls)
~~~

Gauge là **số lời gọi đang chạy lúc scrape**, không phải số request đã hoàn tất trong 5 phút. Một burst ngắn nằm giữa hai lần scrape có thể không xuất hiện trên biểu đồ.

## 12. Đặt tên metric chất lượng theo đúng rubric

### Các kết quả PASS/FAIL

~~~text
app.ai.eval.case.completed{case_type="rag",verdict="pass"}
app.ai.eval.case.completed{case_type="rag",verdict="fail"}
app.ai.eval.case.completed{case_type="rag",verdict="inconclusive"}
~~~

Nếu cần đếm nguyên nhân lỗi, tạo một định nghĩa riêng, chẳng hạn **app.ai.eval.case.error** với tag error_class. Một ca có thể có hai lỗi cùng lúc. Khi đó Counter error đếm **số lần ghi nhận loại lỗi**, không đồng nghĩa **số ca FAIL duy nhất**. Metric dictionary phải nói rõ đơn vị sự kiện.

### Các điểm số liên tục

Relevance, groundedness và một số thước đo fact checking có thể được evaluator biểu diễn bằng số. Nhưng mỗi điểm phải có **rubric, thang và đơn vị quan sát**:

~~~text
app.ai.eval.relevance.score   -> 0.92
app.ai.eval.relevance.score   -> 0.75
app.ai.eval.relevance.score   -> 0.31
~~~

Một sample ở đây là **điểm của một ca**, nếu hợp đồng nói vậy. Không lẫn điểm **cặp query-document** với điểm **toàn câu trả lời**. Khi evaluator chỉ trả PASS/FAIL, không tự chế một phân bố score liên tục rồi dùng cùng tên metric.

### Những mẫu số cần phân biệt

| Chỉ số | Mẫu số đúng |
| --- | --- |
| Tool-choice accuracy | Số ca cần chọn công cụ |
| No-tool correctness | Số ca không nên gọi công cụ |
| Argument accuracy | Số lời gọi cần chấm đối số |
| Grounded answer rate | Số claim có đủ bằng chứng để chấm |
| Factual correctness rate | Số ca PASS + FAIL fact checking |
| Multi-turn trajectory success | Số scenario được chấm |
| Verified task success | Số tác vụ đủ điều kiện kiểm chứng |
| Cost per verified success | Số tác vụ thành công đã xác minh |

Chỉ số **tool execution success** không được dùng thay **verified task success**. Một tool có thể chạy thành công nhưng model trả lời sai, hoặc backend mới trả trạng thái ACCEPTED chứ chưa hoàn tất nghiệp vụ.

## 13. Liên hệ metrics, traces và source of truth

Metric trả lời “có bao nhiêu, nhanh hay chậm, phân bố thế nào”; trace cho biết “yêu cầu cụ thể đi qua những bước gì”; backend/audit cho biết “hành động nào thật sự xảy ra”; oracle kết luận có đáp ứng mục tiêu và bất biến không.

~~~mermaid
flowchart LR
    A["Case-run và phiên bản"] --> B["Spring AI model / tool / RAG"]
    B --> C["Micrometer metrics"]
    B --> D["Traces, events và call IDs"]
    B --> E["Backend / nguồn tài liệu"]
    E --> F["Oracle đánh giá"]
    D --> F
    F --> G["Quality report"]
    C --> G
~~~

Ví dụ dashboard cho thấy **p95 retrieval tăng** đồng thời **fact-check PASS giảm**. Đây là tín hiệu cần điều tra, chưa chứng minh quan hệ nhân quả. Mở traces của ca lỗi để xác định:

1. Model có chọn đúng query và tool không?
2. Retriever lấy nguồn và phiên bản tài liệu nào?
3. Thời gian tăng ở network, retriever, tool handler hay model?
4. Câu trả lời sai do nguồn sai, do tổng hợp sai hay do rubric evaluator đổi?
5. Có retry, gọi thừa hoặc timeout không được tính vào Timer không?

Không đưa **trace_id, prompt, tài liệu nội bộ, mã khách hàng hoặc mã đơn** vào metric tags để tạo khả năng truy nguyên. Dùng kho trace và audit có phân quyền. Khi một span bị sampling hoặc instrumentation thiếu, không tự kết luận model không gọi tool; đánh dấu thiếu quan sát nếu không đủ bằng chứng.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Cùng metric nhưng một nơi ghi ms, nơi khác ghi s | Độ trễ sai 1.000 lần | Dùng Timer và chuẩn hóa đơn vị từ nguồn |
| Score lúc ghi 0,85, lúc ghi 85 | Trung bình không có nghĩa | Chốt miền [0,1], kiểm tra giá trị |
| Gộp document count và chunk count | Không so sánh được RAG | Hai tên metric riêng |
| Ghi PASS cho từng model retry | Tỷ lệ thành công bị sai mẫu số | Một verdict cuối cho case-run |
| Dùng Counter để đo queue depth | Không phản ánh sự giảm của hàng đợi | Dùng Gauge đọc trạng thái |
| Ghi timeout thành latency 0 | p95 giả thấp | Ghi duration thật ở cả nhánh lỗi |
| Đếm HTTP 200 là business completed | Verified success ảo | Dùng oracle/backend source of truth |
| Không có relevance thì ghi score=0 | Điểm trung bình giảm giả | Tách missing và INCONCLUSIVE |
| Gắn user_id/order_id vào tags | Bùng nổ series, rò thông tin | Chỉ dùng danh mục hữu hạn |
| Lấy trung bình p95 của nhiều instance | p95 gộp sai | Tổng hợp histogram buckets hợp lệ |
| Đổi tên hoặc tag mà không cập nhật alert | Cảnh báo biến mất | Version metric contract, test exporter |
| Cost không phân biệt USD/VND | Sai tổng chi phí | Ghi tiền tệ và nguyên tắc quy đổi |
| Thay rubric nhưng giữ series cũ | Xu hướng quality sai | Ghi evaluator version và migration |
| Tag error_class là exception message | Cardinality và dữ liệu nhạy cảm tăng | Chuẩn hóa lỗi thành nhóm hữu hạn |

## 15. Kiểm thử hợp đồng metric như kiểm thử API

Metric là một giao diện dữ liệu mà dashboard, alert, CI và báo cáo sử dụng. Một thay đổi đơn vị hoặc ngữ nghĩa âm thầm có thể gây hỏng vận hành dù code ứng dụng vẫn chạy.

### 15.1. Bộ kiểm thử tối thiểu

| Ca | Input | Điều cần xác minh |
| --- | --- | --- |
| Verdict | Ba ca PASS riêng | Counter PASS tăng đúng 3 |
| Retry | Một case-run có hai retry | Chỉ một verdict cuối; retries đo riêng |
| Token | 1.200 input và 150 output | Hai nhóm direction cùng đơn vị tokens |
| Duration | Tool mất 250 ms | Timer thể hiện 0,250 s khi đọc theo giây |
| Relevance | Điểm 0,86 | Summary nhận đúng một sample |
| Điểm ngoài miền | 86 hoặc NaN | Bị từ chối, không làm méo phân bố |
| Không có usage | Provider không trả token | Không tạo sample bằng 0 giả |
| In-flight | Hai tool bắt đầu, một kết thúc | Gauge từ 0 lên 2 rồi giảm về 1 |
| New user ID | Một người dùng mới xuất hiện | Không tạo metric series riêng theo user |
| Timeout | Tool timeout sau 2 giây | Timer ghi duration và nhãn outcome phù hợp |
| Evaluation missing | Backend/source unavailable | INCONCLUSIVE, không tự chấm FAIL |

### 15.2. Test ở hai tầng

**Tầng đơn vị:** dùng SimpleMeterRegistry để kiểm tra tên logic, count, tổng mẫu, kiểu meter và tags, không cần hệ thống giám sát production.

**Tầng tích hợp:** cấu hình exporter thật trên môi trường kiểm thử, kiểm tra hậu tố tên, đơn vị, histogram buckets và quy tắc chuyển đổi. Không chỉ suy tên Prometheus từ tên Java nếu chưa nhìn các series thực.

Khi thay đổi instrumentation, chạy lại test của hợp đồng cũ và kiểm tra dashboard/alert quan trọng. Các tên được công bố trong ứng dụng nên được quản lý như schema API, không tùy ý đổi vì sở thích đặt tên.

### 15.3. Ví dụ một thay đổi phá vỡ tương thích

~~~text
Phiên bản hợp đồng A:
  metric = app.ai.model.request.duration
  unit = duration
  observation_unit = one provider/model request

Phiên bản hợp đồng B:
  metric = app.ai.model.request.duration
  unit = duration
  observation_unit = complete user task
~~~

Tên và đơn vị đều giữ nguyên nhưng **đối tượng đo đã đổi**. Nếu đổ hai loại dữ liệu vào cùng series, dashboard có thể báo model chậm hơn dù model không thay đổi. Cần đặt tên task end-to-end duration riêng hoặc migration có version và thời điểm rõ ràng.

## 16. Quy trình đánh giá hồi quy giữa prompt, model và pipeline

Một bộ báo cáo hữu ích nên liên kết **ba lớp chỉ số**:

1. **Chất lượng:** tool-choice accuracy, verified outcome, relevance, groundedness, fact checking, thành công hội thoại nhiều lượt.
2. **Vận hành:** độ trễ model/tool/retrieval p50/p95, retry, lỗi, số tool calls và in-flight/queue.
3. **Nguồn lực:** input/output tokens, chi phí mỗi request, chi phí trên mỗi verified success.

Ví dụ hai phiên bản trên **cùng tập 200 ca** với cùng fixture, quyền, oracle và thời gian tham chiếu:

| Metric và đơn vị | Prompt A | Prompt B |
| --- | ---: | ---: |
| Verified task pass rate (%) | 82% | 85% |
| Fact-check pass rate trên ca chấm được (%) | 91% | 89% |
| Tool executions/user task (calls/task) | 1,8 | 2,4 |
| Model input tokens/request | 820 | 1.150 |
| Model request p95 (s) | 1,6 | 2,1 |
| RAG retrieval p95 (s) | 0,28 | 0,31 |
| Cost/verified success (USD) | 0,011 | 0,016 |

Phiên bản B có tỷ lệ hoàn thành tốt hơn nhưng **fact-check kém hơn**, số tool calls nhiều hơn và chi phí/độ trễ tăng. Không thể quyết định chỉ từ một điểm tổng. Hãy xem các ca lỗi, đặc biệt lỗi ngoài quyền, sai fact checking hoặc tác động trùng.

Để so sánh công bằng:

- Giữ **cùng dataset, dữ liệu tool và nguồn RAG**, hoặc công bố rõ chênh lệch.
- Ghi phiên bản prompt, model, tool schema, memory policy, retriever, evaluator và metric contract.
- Chạy nhiều lần với model có tính ngẫu nhiên nếu cần ước lượng mức biến động.
- Báo số ca PASS/FAIL/INCONCLUSIVE, mẫu số và khoảng thời gian đo.
- Tách latency phản hồi khỏi thời gian hoàn tất nghiệp vụ bất đồng bộ.
- Dùng trace của các ca hồi quy để tìm **điểm đầu tiên lệch khỏi gold**.

Nếu metric contract, đơn vị hoặc rubric đã đổi, điểm cũ và mới có thể **không so sánh trực tiếp được**. Việc thay đổi số liệu quan sát có thể do instrumentation chứ không do model thực sự tốt/xấu hơn.

## 17. Bài thực hành

**Bối cảnh:** Bạn xây dựng dashboard cho trợ lý Spring AI có công cụ tra trạng thái đơn và RAG tìm chính sách nội bộ. Bộ đánh giá có ca tool, no-tool, multi-turn và fact checking.

### Phần A — Thiết kế dictionary

1. Đề xuất tên cho số ca PASS, tool latency, model latency, token usage, document/retrieval, relevance score và in-flight calls.
2. Với mỗi tên, ghi **loại meter, đơn vị gốc, đơn vị quan sát, event, tags, nguồn và missing policy**.
3. Chọn một miền score và lý giải cách dashboard hiển thị phần trăm.
4. Nêu một thay đổi sẽ phá vỡ tương thích dù không đổi tên metric.

### Phần B — Kiểm tra đơn vị

1. Dùng Timer ghi tool mất 250 ms; kiểm tra kết quả khi đọc theo giây.
2. Tạo ca ghi nhầm 250 seconds và giải thích lỗi trong biểu đồ p95.
3. Ghi relevance=0,86, sau đó thử ghi 86; kiểm tra bộ recorder từ chối.
4. Một retrieval trả hai documents nhưng năm chunks. Tạo hai sample ở hai metric riêng.
5. Không có token usage: kiểm tra không xuất hiện sample token=0 giả.

### Phần C — Tags và exporter

1. Chuẩn hóa case_type, verdict, outcome, tool_family thành tập giá trị hữu hạn.
2. Tạo 100 lượt dùng 100 order IDs khác nhau. Kiểm tra không tăng series theo order ID.
3. Bật histogram có chủ đích cho tool latency; xác nhận tên series và đơn vị tại exporter thực.
4. Tạo ca lỗi timeout; xác nhận Timer vẫn ghi sample và outcome khác success.
5. Đo in-flight khi hai lời gọi chạy, một lời gọi kết thúc và một lời gọi ném lỗi.

### Phần D — Báo cáo hồi quy

1. Chạy hai phiên bản prompt trên cùng tập ca và fixture.
2. Tính pass rate kèm coverage; đừng loại INCONCLUSIVE mà không nói rõ.
3. Báo model/tool p95, token/request, calls/task và cost/verified success.
4. Xem một ca có p95 tăng, lần theo trace để tìm model, retriever, handler hoặc backend chịu trách nhiệm.
5. Mô phỏng việc đổi nghĩa duration từ model request sang user task. Viết đề xuất migration metric.

**Câu hỏi tự kiểm tra:** Vì sao tên latency chưa đủ để xác định đại lượng? Relevance 0,85 có phải 85% ca đúng không? Documents khác chunks thế nào? Counter có thể thể hiện số request đang chạy không? Vì sao không dùng prompt làm metric label? Khi nào cần nhãn INCONCLUSIVE? Vì sao p95 của các instance không được lấy trung bình? Vì sao phải phân biệt estimated cost với billed cost? Khi đổi rubric evaluator, điều gì phải được version hóa?

## 18. Những điều cần ghi nhớ

1. **Một metric có hợp đồng rõ:** tên, loại meter, đối tượng đo, đơn vị, thời điểm ghi, tags, nguồn và phép tổng hợp.
2. **Tên phải phản ánh đúng hành vi:** model request, tool request, tool execution, backend operation và case-run khác nhau.
3. **Đơn vị thống nhất từ nguồn tới dashboard:** dùng Timer cho duration, đơn vị riêng cho tokens/documents/chunks và miền số rõ cho score.
4. **Tỷ lệ là kết quả từ tử số/mẫu số có định nghĩa.** Score relevance không tự là pass rate.
5. **Tags hữu hạn và không chứa dữ liệu nhạy cảm.** ID chi tiết thuộc trace/audit hoặc kho đánh giá, không thuộc metric labels.
6. **Tên Java có thể được exporter chuyển đổi.** Kiểm tra base units, hậu tố series và histogram trước khi viết truy vấn.
7. **Metric dictionary cần được version hóa.** Thay đổi ngữ nghĩa, đơn vị, rubric hoặc mẫu số không được làm âm thầm.
8. **Metrics bổ sung cho traces và oracle.** Biểu đồ phát hiện vấn đề; sự kiện và nguồn sự thật giải thích nguyên nhân suy giảm chất lượng.

## Tài liệu tham khảo

- [Micrometer Reference — Meter Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): khái niệm meter và cách tổ chức registry.
- [Micrometer Reference — Naming Meters](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): tên meter, base units và naming conventions.
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm sự kiện và khi nào nên dùng counter.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo duration và phân bố thời gian.
- [Micrometer Reference — Distribution Summaries](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html): đo giá trị số không phải thời gian.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): giá trị tức thời và vòng đời đối tượng.
- [Micrometer Reference — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): histogram, percentile và quy tắc tổng hợp.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): khả năng quan sát các thành phần Spring AI.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate và histogram_quantile.

**Lưu ý phiên bản:** tên meter sẵn có, hậu tố exporter, cấu hình histogram, dữ liệu token usage và chi tiết observation có thể thay đổi theo Spring AI, Micrometer, Spring Boot hoặc backend metrics. Khi áp dụng, hãy kiểm tra phiên bản thư viện, endpoint xuất dữ liệu và hợp đồng nghiệp vụ; các tên app.ai trong bài chỉ là ví dụ do dự án tự định nghĩa.
