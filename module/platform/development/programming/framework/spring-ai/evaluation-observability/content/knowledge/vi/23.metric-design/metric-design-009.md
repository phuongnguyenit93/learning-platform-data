# Liên kết metric vận hành với mục tiêu nghiệp vụ

Một dashboard Spring AI có thể cho thấy model latency giảm, tool execution thành công và tỷ lệ HTTP 5xx gần bằng không. Những tín hiệu đó cho biết hệ thống đang vận hành ổn định, nhưng chưa trả lời câu hỏi sản phẩm quan tâm: người dùng có hoàn thành công việc nhanh hơn, tìm được thông tin chính xác hơn hoặc giảm số lần phải liên hệ nhân viên hỗ trợ không?

Muốn trả lời, cần liên kết **metric vận hành** với **kết quả nghiệp vụ** qua một chuỗi nguyên nhân có thể kiểm tra. Ví dụ, latency của retrieval có thể ảnh hưởng thời gian hoàn thành tác vụ; retrieval relevance có thể ảnh hưởng tỷ lệ trả lời đúng; tỷ lệ tool execution thành công có thể ảnh hưởng tỷ lệ tra cứu đơn hàng hoàn tất. Các mối liên hệ này cần được đo ở đúng đơn vị và xác minh bằng sự kiện nghiệp vụ có thẩm quyền.

Bài học thuộc chương **Thiết kế metric** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân suy giảm qua các phiên bản prompt, model và pipeline.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chuyển một mục tiêu sản phẩm thành KPI và các metric vận hành có liên quan.
2. Xây dựng KPI tree để nối business outcome với task, quality và system signals.
3. Phân biệt leading indicators, lagging indicators và guardrail metrics.
4. Chọn đúng đơn vị đo: task, session, conversation, user action, tool call hoặc evaluation case.
5. Thiết kế metric contract cho task completion, resolution time, verified success và cost per successful task.
6. Phân biệt technical success với business success có xác nhận từ source of truth.
7. Dùng cohort, funnel và segmentation có kiểm soát để tìm điểm nghẽn.
8. Viết PromQL để theo dõi tỷ lệ hoàn thành, thời gian xử lý, lỗi và chi phí trên kết quả thành công.
9. Thiết kế SLO/guardrail để không tối ưu một KPI bằng cách làm giảm chất lượng, an toàn hoặc độ tin cậy.
10. Diễn giải tương quan và attribution thận trọng khi đánh giá tác động của thay đổi model, prompt hoặc pipeline.

## 2. Bắt đầu từ mục tiêu nghiệp vụ

Metric tốt bắt đầu bằng câu hỏi nghiệp vụ cụ thể, có người chịu trách nhiệm và có cách xác minh kết quả.

Ví dụ các mục tiêu của một trợ lý Spring AI:

| Mục tiêu nghiệp vụ | Kết quả cần quan sát | Đơn vị có thể đo |
| --- | --- | --- |
| Giảm thời gian tra cứu đơn hàng | Người dùng nhận được trạng thái đúng trong thời gian ngắn hơn | Một order lookup task |
| Tăng tỷ lệ tự phục vụ | Người dùng hoàn thành yêu cầu mà không cần chuyển nhân viên | Một support task đủ điều kiện |
| Giảm chi phí mỗi tác vụ thành công | Tổng chi phí model/tool/evaluator trên một task được xác minh | Một completed task |
| Tăng chất lượng câu trả lời chính sách | Câu trả lời đúng, có căn cứ và phù hợp câu hỏi | Một answer task hoặc criterion |
| Giảm thao tác thất bại | Ít yêu cầu phải thử lại hoặc cần xử lý thủ công | Một business operation |

Không nên bắt đầu bằng “hãy đo token, latency và tool calls”. Hãy bắt đầu bằng “người dùng cần hoàn thành việc gì, thế nào là hoàn tất, và hệ thống có thể xác minh điều đó ở đâu?”.

### 2.1. Viết mục tiêu thành outcome có thể kiểm chứng

Một mục tiêu mơ hồ:

> Cải thiện trải nghiệm trợ lý AI.

Một mục tiêu có thể đo:

> Tăng tỷ lệ yêu cầu tra cứu đơn hàng được xác minh hoàn tất trong một lượt hỗ trợ, trong khi tỷ lệ trả sai trạng thái không tăng và p95 thời gian xử lý nằm trong ngân sách đã chọn.

Mục tiêu thứ hai xác định phạm vi task, kết quả được xác minh, hiệu quả một lượt hỗ trợ, guardrail chất lượng và ngân sách thời gian.

## 3. KPI tree: từ business outcome đến operational signals

KPI tree là cách phân rã một mục tiêu cấp cao thành những kết quả và yếu tố vận hành có thể đo. Nó không khẳng định mọi nhánh có quan hệ nhân quả; nó giúp đặt ra giả thuyết và chỉ ra dữ liệu cần thu thập.

Ví dụ mục tiêu “tăng tỷ lệ task được giải quyết đúng ngay lần đầu”:

~~~mermaid
flowchart TD
    A["First-contact verified resolution rate"] --> B["Task eligibility and completion"]
    A --> C["Correctness and quality"]
    A --> D["User effort"]
    B --> E["Task completion rate"]
    B --> F["Business verification rate"]
    C --> G["Groundedness / fact-check pass"]
    C --> H["Tool selection and argument accuracy"]
    D --> I["Turns per task"]
    D --> J["Time to verified resolution"]
    G --> K["Retrieval relevance and coverage"]
    H --> L["Tool execution outcome"]
    H --> M["Dependency availability"]
    J --> N["Model / retrieval / tool latency"]
~~~

Ở cây này, verified resolution là outcome cấp sản phẩm; task completion và business verification là các bước trực tiếp tạo nên outcome; groundedness, tool selection và user effort là yếu tố chất lượng/effort; latency, retrieval và dependency availability là tín hiệu vận hành có thể giải thích một phần thay đổi.

### 3.1. Không nhầm KPI với mọi metric trong cây

Không phải tất cả node đều là KPI cấp điều hành:

- KPI: verified resolution rate.
- Supporting metric: tool selection accuracy.
- Diagnostic metric: p95 vector-store latency.
- Guardrail: unsupported answer rate.

Giữ ít KPI cấp cao để định hướng quyết định; giữ đủ metric chẩn đoán để tìm nguyên nhân.

### 3.2. Mỗi nhánh cần một giả thuyết

Ví dụ: nếu retrieval p95 tăng mạnh, task resolution time có thể tăng vì người dùng phải chờ context. Nếu retrieval relevance giảm, groundedness và verified resolution có thể giảm.

Giả thuyết cần được kiểm tra bằng cùng cohort, cùng thời gian, cùng loại task và trace/evaluation records. Một đường biểu đồ cùng tăng hoặc giảm chưa chứng minh quan hệ nhân quả.

## 4. Phân biệt leading indicators, lagging indicators và guardrails

Các loại chỉ số đóng vai trò khác nhau khi ra quyết định.

| Loại | Ý nghĩa | Ví dụ Spring AI |
| --- | --- | --- |
| Leading indicator | Tín hiệu sớm có thể dự báo kết quả sau đó | Retrieval relevance, tool argument validation |
| Lagging indicator | Kết quả nghiệp vụ đã xảy ra | Verified task completion, support escalation |
| Guardrail | Điều kiện phải giữ khi tối ưu outcome | Unsupported answer rate, p95 latency, cost ceiling |

### 4.1. Leading indicator

Leading indicator thường nằm gần pipeline:

- Retrieval recall@k trên dataset có ground truth.
- Tỷ lệ tool selection đúng.
- Tỷ lệ arguments hợp lệ.
- Tỷ lệ answer groundedness PASS.
- Tỷ lệ evaluator có verdict hợp lệ.

Các chỉ số này có thể cảnh báo sớm khi một prompt/model version thay đổi, trước khi tác động tích lũy xuất hiện trong business outcomes.

### 4.2. Lagging indicator

Lagging indicator cần sự kiện nghiệp vụ hoàn tất:

- Order lookup được xác minh đúng.
- Yêu cầu hỗ trợ được giải quyết và không phải mở lại trong cửa sổ định nghĩa.
- Người dùng hoàn thành quy trình mà không cần handoff.
- Một transaction được backend xác nhận COMMITTED.

Lagging indicators thường đáng tin hơn để đo kết quả, nhưng chậm hơn và bị ảnh hưởng bởi nhiều yếu tố bên ngoài.

### 4.3. Guardrail

Không tối ưu một KPI bằng cách làm xấu đi các yếu tố quan trọng khác. Ví dụ tăng containment rate bằng cách không cho người dùng gặp nhân viên có thể làm tăng unresolved rate.

Guardrails cho trợ lý AI có thể gồm unsupported/contradicted answer rate, business action error rate, policy violation rate, p95/p99 end-to-end latency, cost per verified successful task, handoff failure rate và privacy/security incident count.

Guardrail phải có owner, ngưỡng và hành động khi vi phạm.

## 5. Chọn đơn vị nghiệp vụ và mẫu số

Một tỷ lệ chỉ có nghĩa khi numerator và denominator cùng đơn vị, cùng phạm vi và cùng cửa sổ.

### 5.1. Task khác conversation và turn

Một conversation có thể chứa nhiều tasks. Một task có thể cần nhiều model turns, retrieval queries và tool calls.

Ví dụ người dùng mở một conversation:

1. Hỏi trạng thái đơn hàng A.
2. Hỏi đổi địa chỉ giao hàng cho đơn A.
3. Hỏi chính sách hoàn tiền.

Đây có thể là ba tasks dù chỉ có một conversation. Nếu lấy số conversations thành công chia cho số tasks, tỷ lệ sẽ sai.

### 5.2. Định nghĩa task lifecycle

Một task có thể có trạng thái:

- started: task được tạo và đủ điều kiện tính.
- in_progress: pipeline đang xử lý.
- completed: task kết thúc theo workflow.
- verified_success: source of truth xác nhận hậu điều kiện.
- failed: task kết thúc và không đạt hậu điều kiện.
- abandoned: người dùng rời đi hoặc hết thời hạn mà không có kết luận.
- not_applicable: loại task không nằm trong KPI.

completed và verified_success khác nhau. Một câu trả lời đã gửi không chứng minh business operation đã thành công.

### 5.3. Mẫu số có điều kiện eligibility

Ví dụ verified resolution rate:

\[
\text{Verified resolution rate}
\frac{\text{Eligible tasks verified successful in a mature cohort}}
{\text{Eligible tasks in that cohort with a terminal outcome}}
\]

Nếu KPI cần dùng tất cả eligible tasks đã bắt đầu làm mẫu số, hãy đợi cohort đủ thời gian để task chuyển terminal hoặc áp dụng phương pháp xử lý censoring đã định nghĩa. Không coi task còn in-progress là failure ngay lập tức. Công thức PromQL ở phần sau minh họa tỷ lệ trên terminal outcomes.

### 5.4. Cửa sổ đo và delayed outcomes

Một số outcome đến sau request: refund được xử lý sau vài phút, người dùng mở lại ticket sau 24 giờ, hoặc giao dịch chỉ được xác nhận sau khi backend reconciliation chạy.

Định nghĩa cửa sổ outcome trước khi tính KPI. “Reopen trong 7 ngày” khác “không reopen trong 24 giờ”. Đừng thay đổi cửa sổ giữa hai phiên bản rồi so sánh trực tiếp.

## 6. Metric contract cho business outcome

Trước khi ghi metric, mô tả event và source of truth.

| Trường | Ý nghĩa | Lưu ở đâu |
| --- | --- | --- |
| task_type | Nhóm task hữu hạn | Event và metric label |
| outcome | verified_success/failed/abandoned | Event và metric label |
| verification_source | Hệ thống xác nhận outcome | Event; metric label nếu tập hữu hạn |
| task_id | ID duy nhất của task | Business event store |
| conversation_id | Conversation chứa task | Trace/store theo policy |
| started_at | Thời điểm task bắt đầu | Event store |
| verified_at | Thời điểm xác minh outcome | Event store |
| duration | Thời gian đến outcome theo định nghĩa | Timer hoặc event store |
| model_version | Model/pipeline version | Run metadata hoặc bounded release cohort |
| prompt_version | Prompt version | Run metadata |

### 6.1. Source of truth

Chỉ thành phần có thẩm quyền mới được phát business outcome:

- Order service xác nhận trạng thái đơn hàng.
- Payment/refund service xác nhận giao dịch.
- Ticketing system xác nhận ticket được giải quyết hoặc mở lại.
- Workflow engine xác nhận bước quy trình đã commit.

Model tự nói “đã hoàn tất” không phải source of truth. Tool trả HTTP 200 cũng có thể chỉ có nghĩa request đã được nhận.

### 6.2. Event một lần và idempotency

Một task có thể được retry, queue redelivery hoặc kiểm tra lại trạng thái nhiều lần. Business outcome counter chỉ tăng khi task chuyển sang terminal state theo contract, không phải mỗi lần nhận webhook.

Dùng unique key/idempotency ở event store. Metric chỉ phản ánh event đã được commit. Không dùng Prometheus Counter để deduplicate event.

### 6.3. Outcome chưa biết

Nếu backend timeout và chưa thể xác minh transaction, trạng thái là unknown/pending_verification, không phải verified failure hoặc verified success. Đo pending/verification latency riêng và theo dõi backlog.

## 7. Kết nối operational signals với business outcome

Một bảng mapping giúp xác định metric nào giải thích được outcome và metric nào chỉ mô tả hệ thống.

| Business outcome | Quality/flow signals | Operational signals |
| --- | --- | --- |
| Verified order lookup | Answer correctness, tool selection, fact-check PASS | Model latency, order API latency, timeout rate |
| Self-service resolution | Resolution verdict, handoff decision, user effort | Token usage, tool latency, retrieval latency |
| Correct policy answer | Relevance, groundedness, citation correctness | Vector-store latency, model error, context size |
| Successful refund workflow | Argument validity, policy decision, verified transaction | Tool execution latency, dependency availability |
| Cost per successful task | Quality PASS and verified success counts | Model/token cost, retrieval cost, evaluator cost |

### 7.1. Diagnostic chain cho một task

Ví dụ một task không được xác minh hoàn tất:

1. Business event cho biết task failed hoặc pending.
2. Trace cho biết task đi qua ChatClient, retriever và tool nào.
3. Evaluation result cho biết answer relevance/groundedness.
4. Operational metrics cho biết model/tool latency, timeout và token usage.
5. Business source of truth cho biết hậu điều kiện có commit hay chưa.

Mỗi nguồn trả lời một phần. Metric tổng hợp chỉ ra nhóm cần điều tra; trace và event record giải thích một task cụ thể.

### 7.2. Không gán nguyên nhân bằng một metric đơn

Nếu verified resolution rate giảm cùng lúc với model latency tăng, có thể latency góp phần nhưng cũng có thể traffic mix thay đổi, backend nghiệp vụ lỗi hoặc rubric được cập nhật. Cần phân đoạn và kiểm tra trace trước khi kết luận.

## 8. KPI ví dụ cho trợ lý tra cứu đơn hàng

Giả sử mục tiêu là giúp người dùng biết trạng thái đơn hàng chính xác, nhanh và ít cần nhân viên hỗ trợ.

### 8.1. KPI chính

**Verified order lookup success rate**

\[
\frac{\text{Tasks có trạng thái đơn hàng được xác minh đúng trong cohort mature}}
{\text{Eligible order lookup tasks trong cohort có terminal outcome}}
\]

Định nghĩa “đúng” bằng cách đối chiếu answer với order service tại thời điểm query, có quy tắc cho trạng thái thay đổi trong lúc xử lý.

### 8.2. Supporting metrics

- Tool selection accuracy: model chọn đúng order lookup tool.
- Argument validity rate: order ID và filter hợp lệ.
- Business verification rate: kết quả trả về khớp source of truth.
- Answer factual correctness: nội dung cuối không mâu thuẫn với tool result.
- First-contact resolution: task không cần follow-up/handoff theo contract.
- Turns per task: số lượt trao đổi để hoàn tất.

### 8.3. Operational diagnostics

- order_api latency p95.
- Tool timeout/error rate.
- Model request latency p95.
- Prompt + completion tokens per task.
- Retry count per task.
- Queue/verification backlog.

### 8.4. Guardrails

- Wrong order status rate.
- Unauthorized order access count.
- Handoff failure rate.
- p95 end-to-end latency.
- Cost per verified successful lookup.

Một release chỉ cải thiện nếu KPI chính tăng hoặc đạt mục tiêu mà guardrails vẫn trong ngưỡng.

## 9. KPI ví dụ cho trợ lý hỗ trợ chính sách

Mục tiêu là tăng self-service resolution nhưng vẫn bảo đảm câu trả lời chính xác và có căn cứ.

### 9.1. Self-service resolution rate

\[
\frac{\text{Eligible support tasks trong cohort mature được xác minh giải quyết mà không handoff}}
{\text{Eligible support tasks trong cohort đã mature và có terminal outcome}}
\]

Phải định nghĩa task được coi là giải quyết: user confirmation, workflow state hoặc không reopen trong một cửa sổ quan sát. Không mặc định im lặng sau câu trả lời là thành công.

### 9.2. Supporting quality metrics

- Retrieval recall@k trên dataset có relevant-document ground truth.
- Context relevance.
- Answer relevance.
- Groundedness/faithfulness.
- Citation correctness.
- Unsupported answer rate.
- Correct handoff rate khi evidence không đủ.

### 9.3. Operational metrics

- Retrieval latency và vector-store error rate.
- Model latency, token usage và provider errors.
- Context tokens per task.
- Tool call count và tool execution duration.

### 9.4. Guardrail

Không tối ưu containment bằng cách ép trả lời mọi câu hỏi. Nếu evidence yếu hoặc policy yêu cầu escalation, handoff đúng là kết quả an toàn. Theo dõi unsupported answer và incorrect refusal/handoff riêng.

## 10. Tính efficiency metrics theo kết quả thành công

Chi phí trung bình mỗi request không trả lời được chi phí để tạo ra một kết quả nghiệp vụ có ích.

### 10.1. Cost per verified successful task

\[
\text{Cost per verified success}
=\frac{\text{Tổng chi phí của các task trong cohort}}
{\text{Số task verified successful trong cohort}}
\]

Tử số có thể gồm model input/output token cost, tool/API usage cost, retrieval/vector database cost phân bổ theo chính sách và evaluator/judge cost nếu tính vào cost-to-serve.

Phải định nghĩa cost allocation. Nếu một shared retrieval query phục vụ nhiều tasks, cách phân bổ chi phí cần nhất quán.

### 10.2. Cost per successful task không phải cost per request

Một task có thể tạo nhiều model calls và tool calls. Nếu một task cần 3 model calls nhưng chỉ hoàn tất sau lần thứ ba, chi phí của cả 3 attempts thuộc task đó.

Không lấy chi phí của final call chia cho task count nếu muốn đo end-to-end cost.

### 10.3. Cost với zero verified successes

Nếu cohort có chi phí nhưng không có verified success, cost per success không xác định vì mẫu số bằng 0. Không hiển thị cost per success bằng 0 hoặc một số vô hạn được diễn giải sai. Hiển thị N/A và đồng thời xem failure rate/cost incurred.

### 10.4. Time per verified successful task

Có thể đo từ task started đến verified_at. Không chỉ cộng model latency; thời gian chờ user, tool, queue và business verification có thể chiếm phần lớn.

Báo p50/p95 để tránh mean che giấu tail. Cần thống nhất có tính thời gian người dùng chờ phản hồi hay chỉ server processing time.

## 11. Phân tích funnel và điểm rơi trong task lifecycle

Funnel giúp xác định task thất bại ở bước nào. Mỗi bước phải có event rõ ràng và cùng một cohort.

Ví dụ funnel order lookup:

~~~text
Eligible task started           10,000
Assistant response produced      9,700
Tool selected correctly          9,300
Order service response received  9,100
Answer verified correct          8,850
Task verified successful         8,600
~~~

Các tỷ lệ chuyển bước:

- Response production / started = 97%.
- Correct tool selection / started = 93%.
- Order service response / correct selection ≈ 97,85%.
- Correct answer / service response ≈ 97,25%.
- Verified task success / started = 86%.

Các số liệu chỉ minh họa. Khi tính funnel thực tế, dùng task ID trong event store để nối bước và xử lý nhiều attempts; đừng cộng các Counter độc lập rồi giả định mỗi event thuộc một task duy nhất.

### 11.1. Funnel không nhất thiết là một chuỗi tuyến tính

Một task có thể:

- Không cần tool.
- Gọi nhiều tools.
- Retry một tool.
- Handoff sang nhân viên.
- Được xác minh sau khi request đã kết thúc.

Vì vậy, định nghĩa các nhánh hợp lệ và điều kiện eligibility. Với task không cần tool, không tính thiếu tool call là failure.

### 11.2. Tách task attempts và terminal outcomes

Đo attempts để biết pipeline retry bao nhiêu lần. Đo terminal outcome một lần cho mỗi task để biết kết quả cuối. Không dùng attempt count làm mẫu số cho task success rate.

### 11.3. Thời gian ở từng bước

Đo:

- Time to first response.
- Retrieval duration.
- Model generation duration.
- Tool execution duration.
- Queue wait duration.
- Time to business verification.
- End-to-end time to verified resolution.

Các duration phải có ranh giới bắt đầu/kết thúc rõ ràng. Tổng các component durations có thể lớn hơn wall-clock task duration nếu có xử lý song song.

## 12. Phân đoạn và cohort để so sánh công bằng

Business outcomes thay đổi theo loại task, traffic source, độ khó và thời điểm. Một aggregate rate có thể thay đổi chỉ vì mix task thay đổi.

### 12.1. Cohort theo task type

Phân đoạn theo taxonomy hữu hạn:

- order_lookup.
- policy_question.
- refund_request.
- account_support.
- other.

So sánh model/prompt theo từng nhóm giúp tránh một nhóm task dễ hơn che lấp regression ở nhóm khó.

### 12.2. Cohort theo release

Để đánh giá rollout, có thể so sánh:

- baseline release.
- canary release.
- stable release.

Release cohort phải là một tập nhỏ và có thời hạn. Lưu build/prompt/model version chi tiết trong evaluation run metadata; chỉ đưa release channel hoặc version có cardinality được kiểm soát vào metric label khi thực sự cần.

### 12.3. Cohort theo thời gian

So sánh cùng weekday/hour nếu traffic có tính mùa vụ. Đối với ticket reopen hoặc task resolution delayed, chỉ so những cohort đã đủ cửa sổ quan sát.

### 12.4. Tránh Simpson's paradox

Giả sử release B cải thiện success rate trong cả hai nhóm task đơn giản và phức tạp, nhưng tỷ trọng task phức tạp tăng mạnh. Aggregate success rate của B vẫn có thể thấp hơn A. Xem breakdown theo task_type và cân nhắc chuẩn hóa theo một task mix cố định trước khi kết luận.

### 12.5. Không đưa cohort ID vô hạn vào Prometheus

Mỗi campaign, user, conversation hoặc experiment assignment có thể tạo một label value mới. Những ID này thuộc event store/analytics warehouse. Metric backend nên giữ dimensions có cardinality thấp và được quản lý.

## 13. Attribution: nối task với model, prompt và pipeline

Khi business outcome thay đổi, cần biết task đã đi qua phiên bản nào. Nhưng attribution phải có contract và không làm nổ cardinality.

### 13.1. Lưu lineage ở task/run record

Một task record có thể lưu:

- model provider/model family và model version.
- prompt template/version.
- retrieval index/config version.
- embedding model version.
- reranker version.
- tool schema/policy version.
- application build/release.
- evaluator model/rubric version.

Các giá trị chi tiết thuộc evaluation/business event store hoặc trace attributes. Metric chỉ giữ release cohort/version có kiểm soát nếu cần dashboard so sánh.

### 13.2. Task có nhiều model calls

Một task có thể gọi nhiều model versions hoặc prompt variants. Đừng gán một model version duy nhất nếu task thực sự dùng nhiều phiên bản.

Có thể:

- Lưu danh sách attempts trong trace/run record.
- Xác định version chịu trách nhiệm cho final answer theo quy tắc rõ.
- Dùng attempt-level metrics cho từng model call.
- Dùng task-level outcome cho business success.

Không trộn model-call denominator với task-level numerator.

### 13.3. Correlation ID để drill down

Dùng trace ID/task reference để liên kết business event, evaluation record, logs và traces. Những ID này không phải metric labels. Dashboard có thể dẫn đến query/log explorer theo trace reference nếu hệ thống hỗ trợ.

### 13.4. Attribution không đồng nghĩa causal proof

Nếu release mới có verified success thấp hơn, chưa đủ để kết luận model mới gây ra regression. Traffic mix, backend dependencies, user behavior, policy changes và evaluator calibration đều có thể thay đổi.

Muốn ước lượng tác động nhân quả, dùng canary/randomized assignment hoặc thiết kế quasi-experiment phù hợp, giữ các điều kiện khác ổn định và kiểm tra sample size. Theo dõi guardrails trong suốt thử nghiệm.

## 14. Instrumentation Java cho business outcomes

Business metric nên được ghi ở điểm outcome đã được xác minh. Ví dụ dưới đây dùng MeterRegistry và taxonomy enum hữu hạn.

### 14.1. BusinessOutcomeMetrics

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public final class BusinessOutcomeMetrics {

    public enum TaskType {
        ORDER_LOOKUP("order_lookup"),
        POLICY_QUESTION("policy_question"),
        REFUND_REQUEST("refund_request"),
        OTHER("other");

        private final String tag;

        TaskType(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    public enum Outcome {
        VERIFIED_SUCCESS("verified_success"),
        FAILED("failed"),
        ABANDONED("abandoned");

        private final String tag;

        Outcome(String tag) {
            this.tag = tag;
        }

        public String tag() {
            return tag;
        }
    }

    private final MeterRegistry registry;

    public BusinessOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordTerminalOutcome(
            TaskType taskType,
            Outcome outcome
    ) {
        Counter.builder("app.ai.business.task.outcome")
                .tag("task_type", taskType.tag())
                .tag("outcome", outcome.tag())
                .register(registry)
                .increment();
    }

    public void recordVerifiedResolutionDuration(
            TaskType taskType,
            Duration duration
    ) {
        if (duration == null || duration.isNegative()) {
            throw new IllegalArgumentException(
                    "Task duration must be non-negative");
        }

        Timer.builder("app.ai.business.task.time_to_verified_success")
                .tag("task_type", taskType.tag())
                .register(registry)
                .record(duration);
    }
}
~~~

### 14.2. Ghi ở business verification boundary

Gọi recordTerminalOutcome(VERIFIED_SUCCESS) sau khi source of truth xác nhận trạng thái cuối. Nếu backend chỉ trả ACCEPTED/PENDING, không ghi verified success; theo dõi trạng thái pending bằng Gauge/backlog snapshot hoặc một transition metric riêng nếu contract yêu cầu.

Nếu một task được kiểm tra lại nhiều lần, event store phải bảo đảm chỉ có một terminal transition hợp lệ. Meter recorder nên được gọi sau khi transaction/event commit thành công hoặc qua transactional outbox để tránh mất event khi process crash.

### 14.3. Đừng dùng enum outcome cho trạng thái chưa terminal như terminal failure

Trạng thái đang chờ xác minh không thuộc enum terminal outcome ở ví dụ. Nếu cần đo số task pending hiện tại, dùng Gauge/backlog snapshot hoặc query event store. Nếu dùng Counter, đặt tên là transition/event counter và chỉ tăng theo mỗi transition; không gọi nó là terminal outcomes.

Để giữ ví dụ rõ ràng, production implementation nên tách:

- task started Counter.
- task terminal outcome Counter chỉ cho verified_success/failed/abandoned.
- pending verification Gauge hoặc transition Counter.
- Timer từ started đến verified terminal outcome.

## 15. PromQL nối business outcomes với operational signals

Tên metric Prometheus dưới đây là ví dụ theo quy tắc chuẩn hóa phổ biến của Micrometer. Kiểm tra exposition của registry thực tế, vì tên và hậu tố có thể thay đổi theo registry/configuration.

### 15.1. Verified success rate

~~~promql
sum by (task_type) (
  rate(app_ai_business_task_outcome_total{
    outcome="verified_success"
  }[15m])
)
/
sum by (task_type) (
  rate(app_ai_business_task_outcome_total{
    outcome=~"verified_success|failed|abandoned"
  }[15m])
)
~~~

Mẫu số chỉ gồm task đã đi đến trạng thái cuối theo contract. Không đưa pending verification vào mẫu số như failure. Nếu chưa có terminal task trong cửa sổ, kết quả phải là No data/N/A chứ không phải 100%.

### 15.2. Task outcome volume

~~~promql
sum by (task_type, outcome) (
  increase(app_ai_business_task_outcome_total[1h])
)
~~~

Giúp xem số task theo outcome trong một giờ. Chỉ dùng increase khi có đủ samples và series được export ổn định.

### 15.3. Time to verified success p95

Nếu Timer histogram được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, task_type) (
    rate(app_ai_business_task_time_to_verified_success_seconds_bucket[15m])
  )
)
~~~

Chỉ Timer này mới đo khoảng từ task start đến verified success nếu code ghi đúng duration. Nó không tương đương model latency hoặc server request latency.

### 15.4. Operational tool error rate

~~~promql
sum by (tool_family) (
  rate(app_ai_tool_execution_total{outcome="error"}[5m])
)
/
sum by (tool_family) (
  rate(app_ai_tool_execution_total[5m])
)
~~~

Metric này giúp giải thích một phần business failure. Tool error rate tăng không đồng nghĩa business failure tăng cùng tỷ lệ; có thể retry hoặc fallback thành công.

### 15.5. Cost per verified success

Giả sử ứng dụng có Counter tổng cost đã quy đổi sang cùng currency/unit cho từng task cohort:

~~~promql
sum by (task_type) (
  rate(app_ai_business_task_cost_amount_total[1h])
)
/
sum by (task_type) (
  rate(app_ai_business_task_outcome_total{
    outcome="verified_success"
  }[1h])
)
~~~

Chỉ hợp lệ nếu numerator và denominator đã được tổng hợp trên cùng cohort task đã hoàn tất, cùng task_type và cùng currency. Một cửa sổ rate theo thời gian phát sinh cost và một cửa sổ rate theo thời điểm verification có thể không cùng cohort khi outcome đến trễ; hai Counter độc lập trong Prometheus không tự tạo được quan hệ task-level. Với billing chính xác hoặc phân bổ theo run phức tạp, tính KPI bằng join task records trong warehouse/evaluation store thường phù hợp hơn Prometheus.

### 15.6. So sánh business outcome với retrieval latency

Có thể hiển thị verified success rate cạnh retrieval p95 theo cùng task_type và cohort. Tránh join trực tiếp các series có labels khác nhau nếu không có mapping rõ; PromQL vector matching không thay thế mô hình attribution trong event store.

## 16. SLO và guardrail từ mục tiêu nghiệp vụ

SLO nên mô tả trải nghiệm/kết quả có ý nghĩa, nhưng cần dữ liệu đủ tin cậy để đo.

### 16.1. Ví dụ SLO

Một trợ lý order lookup có thể đặt mục tiêu nội bộ:

- 99% request được xử lý trong ngân sách latency kỹ thuật.
- 95% eligible tasks trong cohort mature được xác minh trạng thái đúng trong cửa sổ đã định.
- Unsupported answer rate dưới ngưỡng rủi ro đã duyệt.
- Cost per verified success không vượt ngân sách.

Các con số trên chỉ là ví dụ. Chọn target dựa trên baseline, nhu cầu người dùng, rủi ro nghiệp vụ và khả năng vận hành.

### 16.2. Business SLI và operational SLI

| SLI | Đo lường | Nguồn |
| --- | --- | --- |
| Verified success | Task verified_success / eligible terminal tasks | Business event store |
| Correctness | Correct answers / evaluated answers có kết luận | Evaluation store |
| Latency | Task start đến verified outcome | Timer/event timestamps |
| Availability | Request thành công / request hợp lệ | HTTP/Actuator metrics |
| Cost efficiency | Cost / verified successful task | Cost ledger + business events |

Business SLI có thể chậm do delayed outcomes. Operational SLI cung cấp tín hiệu sớm và điều tra nguyên nhân.

### 16.3. Error budget và quality budget

Nếu verified success SLO bị vi phạm, release có thể cần dừng rollout dù latency kỹ thuật vẫn tốt. Nếu evaluator coverage thấp, quality SLI chưa đủ tin cậy để đánh giá release; cần khôi phục evaluator hoặc giảm tốc độ rollout.

Không dùng một error budget kỹ thuật duy nhất để đại diện cho quality risk.

### 16.4. Guardrail phải đo cả hành động an toàn

Một handoff đúng policy không nên tính là model failure. Một từ chối an toàn khi thiếu evidence có thể là outcome tốt. Hãy phân biệt:

- correct refusal.
- correct handoff.
- incorrect refusal.
- failed handoff.
- unsupported answer.

Điều này ngăn KPI tự phục vụ khuyến khích hệ thống trả lời bừa thay vì chuyển người phù hợp.

## 17. Sampling, representativeness và missing outcomes

Online evaluation thường chỉ chấm một phần traffic để giới hạn cost. Kết quả sample không tự động đại diện toàn bộ traffic.

### 17.1. Ghi tỷ lệ sampling

Lưu sampling policy/version và sample rate trong evaluation run metadata. Nếu sampling phụ thuộc task type hoặc risk score, báo cáo theo từng strata.

Ví dụ chỉ chấm 10% tasks thông thường nhưng 100% refund tasks. Aggregate quality score không thể coi như random sample đơn giản nếu chưa điều chỉnh weighting.

### 17.2. Coverage

Theo dõi:

\[
\text{Evaluation coverage}
=\frac{\text{Eligible tasks có verdict hợp lệ}}
{\text{Eligible tasks được chọn để đánh giá}}
\]

Phân biệt selected-for-evaluation với completed-evaluation. Evaluator timeout làm coverage giảm; nó không làm quality verdict tự động FAIL.

### 17.3. Delayed verification và censoring

Nếu cohort mới chưa đủ 7 ngày để biết ticket có reopen không, cohort đó chưa mature. Không so nó với cohort cũ đã đủ cửa sổ 7 ngày như thể cả hai có cùng dữ liệu.

Có thể hiển thị:

- mature cohort outcomes.
- pending verification.
- evaluator incomplete.
- not eligible/not sampled.

Đừng loại bỏ missing outcome mà không công bố coverage.

### 17.4. Weighting khi task mix khác nhau

Nếu muốn so hai release trên cùng task mix, xác định trọng số chuẩn theo business mix hoặc dataset chuẩn. Tính tỷ lệ theo strata trước, sau đó mới tổng hợp có trọng số. Công bố weighting method vì nó thay đổi ý nghĩa KPI.

## 18. Tương quan, attribution và thử nghiệm rollout

Metric liên kết giúp hình thành giả thuyết; thử nghiệm giúp đánh giá thay đổi.

### 18.1. Trước/sau không đủ để kết luận

Ví dụ sau khi đổi model:

- Verified success rate tăng.
- Token cost giảm.
- Traffic chuyển sang nhiều task đơn giản hơn.

Không thể kết luận model mới tạo ra toàn bộ cải thiện nếu không kiểm soát task mix.

### 18.2. Canary hoặc randomized assignment

Nếu phù hợp, phân bổ một phần eligible tasks vào baseline và candidate:

- Cùng task taxonomy.
- Cùng eligibility rules.
- Cùng business verification.
- Cùng rubric/evaluator version.
- Cùng thời gian/cửa sổ quan sát.

So sánh primary KPI và guardrails. Với task có delayed outcomes, chỉ chốt kết luận sau khi cohort đủ mature.

### 18.3. Không để evaluator version thay đổi cùng lúc nếu đang đo model

Nếu đổi cả answer model lẫn judge model, business/quality metric có thể thay đổi do judge calibration. Cố định evaluator/rubric hoặc chạy calibration bridge trên human-labeled set.

### 18.4. Statistical uncertainty

Một thay đổi nhỏ trên sample size thấp có thể chỉ là nhiễu. Báo numerator, denominator, confidence interval hoặc uncertainty phù hợp; tránh chỉ hiển thị phần trăm đã làm tròn.

## 19. Kiểm thử metric contract

Test cần xác minh metric chỉ tăng khi event có thẩm quyền được commit và đúng đơn vị.

### 19.1. Unit test với SimpleMeterRegistry

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

import java.time.Duration;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class BusinessOutcomeMetricsTest {

    @Test
    void recordsVerifiedSuccessAndNotAnAttempt() {
        var registry = new SimpleMeterRegistry();
        var metrics = new BusinessOutcomeMetrics(registry);

        // Chỉ gọi sau khi source of truth đã xác minh task.
        metrics.recordTerminalOutcome(
                BusinessOutcomeMetrics.TaskType.ORDER_LOOKUP,
                BusinessOutcomeMetrics.Outcome.VERIFIED_SUCCESS);

        var success = registry.find("app.ai.business.task.outcome")
                .tag("task_type", "order_lookup")
                .tag("outcome", "verified_success")
                .counter();
        var failure = registry.find("app.ai.business.task.outcome")
                .tag("task_type", "order_lookup")
                .tag("outcome", "failed")
                .counter();

        assertEquals(1.0, success.count(), 0.000001);
        assertNull(failure);
    }

    @Test
    void recordsTimeToVerifiedOutcomeSeparately() {
        var registry = new SimpleMeterRegistry();
        var metrics = new BusinessOutcomeMetrics(registry);

        metrics.recordVerifiedResolutionDuration(
                BusinessOutcomeMetrics.TaskType.ORDER_LOOKUP,
                Duration.ofMillis(420));

        var timer = registry.find(
                        "app.ai.business.task.time_to_verified_success")
                .tag("task_type", "order_lookup")
                .timer();

        assertEquals(1L, timer.count());
        assertEquals(420.0, timer.totalTime(java.util.concurrent.TimeUnit.MILLISECONDS),
                0.001);
    }
}
~~~

Test giả định class metrics cùng package hoặc đã import; thêm import java.time.Duration cho fixture duration.

### 19.2. Integration test với business event store

1. Tạo một task và phát event started.
2. Giả lập tool trả ACCEPTED/PENDING.
3. Xác nhận chưa có verified_success.
4. Giả lập source of truth chuyển sang terminal success.
5. Xác nhận business outcome counter tăng đúng một.
6. Gửi lại cùng webhook/event.
7. Xác nhận idempotency ngăn metric tăng lần thứ hai.
8. Kiểm tra trace/task record liên kết được operational metrics và evaluation evidence.

### 19.3. Test task không cần tool

Tạo task chat-only không có tool expected. Xác nhận task có thể verified success mà không tăng tool execution count và không bị tính tool-selection failure.

### 19.4. Test delayed outcome

Giả lập task còn pending verification. Xác nhận dashboard không coi nó là failed terminal task và không đưa vào denominator terminal success rate nếu contract định nghĩa như vậy.

## 20. Bài thực hành

**Bối cảnh:** một trợ lý Spring AI xử lý ba loại tác vụ: tra cứu đơn hàng, hỏi chính sách và yêu cầu hoàn tiền. Sản phẩm muốn tăng tỷ lệ tự phục vụ, giảm thời gian giải quyết và giữ chi phí ở mức hợp lý.

### Phần A — Chọn business outcome

1. Định nghĩa eligible task cho từng task type.
2. Xác định source of truth để xác nhận thành công.
3. Định nghĩa terminal states và pending verification.
4. Chọn cửa sổ để xác định task được giải quyết hay bị mở lại.
5. Xác định ai sở hữu KPI và ai chịu trách nhiệm về source event.

### Phần B — Xây KPI tree

1. Chọn một primary KPI.
2. Chọn 3–5 supporting metrics.
3. Chọn operational diagnostics cho model, retriever, tool và queue.
4. Chọn ít nhất ba guardrails.
5. Vẽ Mermaid KPI tree và ghi giả thuyết cho từng nhánh.

### Phần C — Metric contract

1. Chọn đơn vị task/conversation/turn.
2. Định nghĩa numerator và denominator.
3. Chọn event ghi một lần và idempotency key.
4. Quy định label taxonomy hữu hạn.
5. Xác định dữ liệu nào lưu trong event store/trace thay vì metric labels.

### Phần D — PromQL

1. Tính verified success rate theo task_type.
2. Tính terminal outcome volume theo giờ.
3. Tính p95 time to verified success.
4. Tính tool error rate.
5. Tính cost per verified success và xử lý mẫu số bằng 0.

### Phần E — Đọc kết quả rollout

Candidate release cho kết quả:

- Verified success tăng từ 84% lên 88%.
- Tool error rate giảm từ 3% xuống 2%.
- p95 task resolution time tăng từ 4,2 giây lên 5,1 giây.
- Cost per verified success giảm 8%.
- Unsupported answer rate tăng từ 0,7% lên 1,4%.
- Candidate có tỷ trọng task chính sách cao hơn baseline.

Hãy trả lời:

1. Có thể kết luận candidate tốt hơn không?
2. Guardrail nào cần điều tra trước khi rollout rộng?
3. Cần chuẩn hóa task mix thế nào?
4. Cần xem trace/evaluation record nào để tìm nguyên nhân p95 tăng?
5. Cần bao nhiêu dữ liệu và cửa sổ quan sát nào trước khi quyết định?

### Câu hỏi tự kiểm tra

- Vì sao latency thấp không chứng minh business outcome tốt?
- KPI tree giúp ích gì khi điều tra regression?
- Leading indicator khác lagging indicator thế nào?
- Vì sao task khác conversation và model turn?
- Source of truth nào được quyền phát verified_success?
- Khi nào pending verification không nên nằm trong denominator?
- Cost per successful task khác cost per request ở đâu?
- Làm sao tránh Simpson's paradox khi task mix thay đổi?
- Vì sao run ID không nên là Prometheus label?
- Correlation giữa retrieval latency và resolution rate có chứng minh nhân quả không?
- Tại sao phải giữ unsupported answer rate làm guardrail?
- Làm sao xử lý delayed outcomes và evaluator coverage thấp?

## 21. Những điều cần ghi nhớ

1. **Bắt đầu từ outcome nghiệp vụ.** Định nghĩa việc người dùng cần hoàn thành và cách source of truth xác minh.
2. **Dùng KPI tree để nối outcome với quality và operational signals.** Các nhánh là giả thuyết cần kiểm tra, không phải quan hệ nhân quả mặc định.
3. **Tách leading indicators, lagging indicators và guardrails.** Một KPI tốt không được cải thiện bằng cách làm xấu đi correctness, safety hoặc cost.
4. **Chọn đúng đơn vị và mẫu số.** Task, conversation, turn, attempt và evaluation case không thể thay thế cho nhau.
5. **Business success phải có bằng chứng.** Model response hoặc HTTP 200 không đủ để xác nhận hậu điều kiện nghiệp vụ.
6. **Ghi outcome đúng một lần.** Dùng idempotency/event store hoặc transactional outbox; metric không phải nguồn deduplicate.
7. **Nối metric với trace và event record.** Metrics tổng hợp để phát hiện; trace/evaluation record để giải thích.
8. **Cost per success tính toàn bộ chi phí của task.** Khi denominator bằng zero, kết quả là N/A.
9. **Cohort và task mix ảnh hưởng aggregate KPI.** Phân đoạn và chuẩn hóa trước khi so sánh release.
10. **Attribution không tự chứng minh causal impact.** Dùng canary/randomized assignment hoặc thiết kế thử nghiệm phù hợp.
11. **Sampling và delayed outcomes phải công khai.** Theo dõi coverage, maturity và uncertainty.
12. **Giữ guardrails trong suốt rollout.** Verified success, quality, latency, safety và cost cần được xem cùng nhau.

## Tài liệu tham khảo

- [Google SRE Workbook — Implementing SLOs](https://sre.google/workbook/implementing-slos/): chuyển mục tiêu reliability thành SLI/SLO.
- [Google SRE Book — Service Level Objectives](https://sre.google/sre-book/service-level-objectives/): lựa chọn chỉ số và mục tiêu dịch vụ.
- [Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/): chọn metric và instrumentation.
- [Prometheus — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): phân vị và histogram.
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): đếm event tích lũy.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): đo thời gian và số lần thực thi.
- [Micrometer Reference — Gauges](https://docs.micrometer.io/micrometer/reference/concepts/gauges.html): đo trạng thái tức thời.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): registry và custom metrics.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): traces và metrics của ChatClient/model/tool.
- [OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/): semantics và aggregation của measurements.

**Lưu ý phiên bản:** tên metric Prometheus, histogram export, Spring AI observations và Micrometer APIs phụ thuộc phiên bản/configuration. Các metric app.ai trong bài là custom examples. Trước khi triển khai, xác minh scrape exposition, event contract, source of truth và cửa sổ đo trong môi trường thực tế.
