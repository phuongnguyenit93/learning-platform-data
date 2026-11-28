# Quan hệ giữa dữ liệu kiểm thử, kết quả đánh giá và bằng chứng thực thi

Trong ứng dụng Spring AI, một báo cáo “92% câu trả lời đạt” chỉ có ích khi ta biết **đã hỏi gì, mong đợi gì, ứng dụng thực sự làm gì và kết luận đạt/không đạt dựa trên bằng chứng nào**. Nếu thiếu một mắt xích, nhóm phát triển dễ nhận sai nguyên nhân, tối ưu nhầm bước hoặc công bố điểm số không thể kiểm chứng.

Giả sử chatbot tra cứu chính sách được hỏi: “Gói Pro có thời hạn hoàn phí bao lâu?”. Dataset ghi đáp án đúng là **14 ngày** theo phiên bản chính sách có hiệu lực. Chatbot lại trả lời **30 ngày**. Báo cáo chỉ ghi `FAIL` thì chưa đủ để biết cần sửa gì. Nếu ta có thêm các tài liệu RAG thực sự truy xuất, prompt version, model version, lời gọi công cụ, trace và kết quả chấm, ta có thể phân biệt lỗi **thiếu bằng chứng**, **dùng tài liệu cũ**, **model hiểu sai context** hoặc **bộ chấm hoạt động không ổn định**.

Đó là quan hệ cốt lõi giữa ba loại thông tin:

1. **Dữ liệu kiểm thử (test dataset):** mô tả tình huống và tiêu chí được xem là thành công.
2. **Bằng chứng thực thi (execution evidence):** ghi lại hành vi đã xảy ra trong một lần chạy cụ thể.
3. **Kết quả đánh giá (evaluation result):** đối chiếu yêu cầu và hành vi thực tế, đưa ra nhận định đạt/không đạt cùng lý do.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, chuỗi này nối evaluation bằng dataset, relevance, fact checking, kiểm thử RAG/tool calling với observability bằng metrics, traces, chi phí và độ trễ. Nhờ đó, ta có thể so sánh các phiên bản prompt, model và pipeline bằng dữ liệu có thể truy xuất nguồn gốc.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích đúng vai trò của **dataset**, **execution evidence** và **evaluation result**, cũng như mối quan hệ giữa chúng.
- Thiết kế một ca đánh giá có câu hỏi, nguồn tham chiếu, expected behavior, rubric và phiên bản dữ liệu.
- Ghi lại tài liệu truy xuất, lời gọi model/tool, dấu vết trace và token/latency theo một lần thực thi cụ thể.
- Gắn một đánh giá relevance, groundedness hoặc factual correctness với câu trả lời và bằng chứng mà evaluator thực sự sử dụng.
- Thiết kế khóa liên kết như `caseId`, `runId`, `attemptId`, `traceId` để điều tra lỗi và so sánh phiên bản.
- Phân biệt **bằng chứng ứng dụng đã làm gì** với **bằng chứng câu trả lời đúng**.
- Phát hiện các lỗi phương pháp: dùng nhầm nguồn chuẩn thay cho context truy xuất, thiếu dữ liệu, lỗi do bộ chấm và mất khả năng tái hiện.

## 2. Ba loại thông tin: yêu cầu, sự kiện và phán đoán

### 2.1. Dữ liệu kiểm thử trả lời “điều gì nên xảy ra?”

Một ca kiểm thử định nghĩa bối cảnh, đầu vào và kỳ vọng. Nó có thể chứa thông tin như:

- Câu hỏi đầu vào và ngữ cảnh hội thoại cần thiết.
- Đáp án chuẩn, các khẳng định bắt buộc, các khẳng định bị cấm.
- Tài liệu nguồn hoặc trạng thái backend được xác minh.
- Tài liệu RAG kỳ vọng xuất hiện khi retrieval.
- Tool cần dùng, đối số, quyền thực thi, điều kiện cần xác nhận.
- Rubric đánh giá và mức độ quan trọng của lỗi.

Dataset là **đặc tả để đánh giá**, không phải ghi chép ứng dụng đã thực hiện. Trong một ca RAG, `expectedDocumentIds` nói tài liệu *nên* được tìm thấy; nó không chứng minh truy xuất *đã* tìm được tài liệu đó.

### 2.2. Bằng chứng thực thi trả lời “điều gì đã xảy ra?”

Execution evidence được ghi trong khi ứng dụng thật sự xử lý một request hoặc một lần chạy test:

- Model được gọi bằng cấu hình nào?
- Bộ truy xuất đã lấy những document ID, version và thứ tự nào?
- Model đã tạo câu trả lời và trích dẫn gì?
- Tool nào thực sự được gọi với đối số nào, có thành công không?
- Mỗi bước tốn bao lâu, có retry hoặc timeout không?
- Provider đã báo input/output token usage như thế nào?

Bằng chứng phải thuộc **đúng một execution attempt**, chứ không lấy từ lần chạy khác chỉ vì câu hỏi giống nhau.

### 2.3. Kết quả đánh giá trả lời “đã đáp ứng kỳ vọng chưa?”

Evaluation result là **kết luận có phương pháp** dựa trên tiêu chí và dữ liệu quan sát:

- `relevance = PASS`: câu trả lời đáp ứng câu hỏi.
- `groundedness = FAIL`: có khẳng định không được tài liệu truy xuất hỗ trợ.
- `factualCorrectness = FAIL`: mâu thuẫn với chính sách được xác minh.
- `toolArguments = PASS`: đối số tool đúng hợp đồng.
- `latencyBudget = FAIL`: thời gian vượt ngưỡng của bài đo.

Kết quả cần nêu **đã chấm cái gì, bằng cách nào, theo phiên bản rubric/judge nào và bằng chứng nào được sử dụng**. Điểm do LLM judge sinh ra là một phán đoán có thể sai, cần kiểm chứng ở các tình huống quan trọng.

| Câu hỏi | Loại thông tin | Ví dụ |
| --- | --- | --- |
| Đáp án mong đợi là gì? | Test dataset | “14 ngày”, nguồn `policy-v3` |
| Model thực sự trả lời gì? | Execution evidence | “30 ngày” |
| Retriever thực sự lấy nguồn nào? | Execution evidence | `policy-v2#refund` |
| Câu trả lời có đúng nguồn đang hiệu lực không? | Evaluation result | `factualCorrectness = FAIL` |
| Request chậm ở bước nào? | Execution evidence qua traces | VectorStore chiếm 1,4 giây |
| Candidate đủ điều kiện phát hành chưa? | Quyết định từ nhiều kết quả và quy tắc | Release gate không đạt |

**Phân biệt quan trọng:** dataset là chuẩn kỳ vọng; telemetry là quan sát về quá trình; evaluator là người/cơ chế đưa ra nhận định. Không loại nào tự động thay thế hai loại còn lại.

## 3. Mối quan hệ dữ liệu: một case có nhiều lần chạy

Ứng dụng AI có thể sinh các cách diễn đạt khác nhau dù cùng câu hỏi và cấu hình. Một ca kiểm thử vì vậy cần liên kết tới **nhiều lần chạy**; mỗi lần chạy có thể tạo nhiều sự kiện và nhiều kết quả đánh giá.

~~~mermaid
erDiagram
    DATASET_VERSION ||--o{ TEST_CASE : "bao gồm"
    TEST_CASE ||--o{ EXECUTION_ATTEMPT : "được chạy"
    EVALUATION_RUN ||--o{ EXECUTION_ATTEMPT : "tập hợp"
    EXECUTION_ATTEMPT ||--o{ EXECUTION_EVIDENCE : "phát sinh"
    EXECUTION_ATTEMPT ||--o{ EVALUATION_RESULT : "được chấm"
    EVALUATION_RESULT }o--o{ EXECUTION_EVIDENCE : "tham chiếu"
~~~

Đây là **mô hình lưu trữ gợi ý**, không phải bảng dữ liệu Spring AI mặc định tạo sẵn.

### 3.1. Khóa định danh và ý nghĩa

| Trường | Ý nghĩa | Quan hệ |
| --- | --- | --- |
| `datasetVersion` | Snapshot bộ ca và nhãn dùng để chấm | Một version chứa nhiều `caseId` |
| `caseId` | Trường hợp nghiệp vụ ổn định | Có thể chạy nhiều lần, nhiều phiên bản |
| `runId` | Một đợt đánh giá/batch có cấu hình xác định | Chứa nhiều attempt |
| `attemptId` | Một lượt thực thi thực tế của một case | Liên kết output, tài liệu, tool, trace và điểm chấm |
| `traceId` | Dấu vết thực thi trong hệ tracing | Giúp tìm chuỗi span của request |
| `spanId` | Một bước trong trace | Phân biệt retrieval, model, tool... |
| `documentId` + `documentVersion` | Tài liệu và phiên bản | Liên kết retrieval với nguồn |
| `toolInvocationId` | Một lần gọi tool cụ thể | Liên kết input, output, lỗi và thời gian |
| `evaluatorVersion` / `rubricVersion` | Cách chấm được sử dụng | Có thể chấm lại cùng evidence bằng bộ chấm mới |

Ví dụ: cùng `caseId=REFUND-001` được chạy trong `runId=baseline-v1` và `runId=candidate-v2`. Mỗi run có `attemptId` riêng. Khi kết luận “candidate sửa được lỗi”, ta phải so **hai attempt thật** và hai kết quả đánh giá có phương pháp chấm tương đương.

### 3.2. Không dùng một ID cho mọi mục đích

`caseId` không thể thay thế `traceId`: một ca có thể chạy 5 lần và sinh 5 trace. `runId` không thể thay thế `attemptId`: một batch có thể gồm 300 ca. `traceId` cũng không phải khóa chấm duy nhất: một execution có thể được chấm bởi relevance evaluator, fact checker và người đánh giá vào các thời điểm khác nhau.

Trong ứng dụng có retry hoặc gọi model nhiều lượt để xử lý tool, **một attempt có thể chứa nhiều model calls**. Cần ghi rõ từng lời gọi; không gộp token của một lần gọi thành token của cả pipeline.

## 4. Thiết kế dataset để kết quả đánh giá có nghĩa

Dataset kém chất lượng sẽ sinh kết quả đánh giá thiếu tin cậy, dù hệ thống telemetry hoàn chỉnh.

### 4.1. Đặc tả ca RAG

Ví dụ chính sách nội bộ của doanh nghiệp giả định *Sao Mai*: gói Pro hoàn phí trong 14 ngày kể từ ngày mua, theo tài liệu `policy-v3`. Tài liệu `policy-v2` đã hết hiệu lực từng ghi 30 ngày.

~~~json
{
  "datasetVersion": "policy-eval-v1",
  "caseId": "REFUND-001",
  "question": "Gói Pro được hoàn phí trong bao lâu?",
  "reference": {
    "documentId": "policy-v3#pro-refund",
    "effectiveFrom": "2026-05-01",
    "verifiedBy": "domain-reviewer"
  },
  "expectedFacts": [
    "Gói Pro có thời hạn hoàn phí 14 ngày kể từ ngày mua"
  ],
  "forbiddenClaims": [
    "Thời hạn hoàn phí là 30 ngày",
    "Mọi trường hợp đều được hoàn phí vô điều kiện"
  ],
  "expectedRetrievalIds": [
    "policy-v3#pro-refund"
  ],
  "expectedBehavior": {
    "answerQuestion": true,
    "citeRelevantPolicy": true,
    "doNotInventExceptions": true
  },
  "tags": ["rag", "vi", "policy-version", "factual"],
  "severity": "high",
  "rubricVersion": "refund-rubric-v1"
}
~~~

**Nguồn và thời hạn hiệu lực là một phần của “sự thật được kiểm tra”.** Câu trả lời dựa đúng `policy-v2` vẫn có thể sai với chính sách hiện hành; cần có cách phân biệt nguồn *đã truy xuất* và nguồn *đang có thẩm quyền*.

### 4.2. Ba dạng “expected” không nên trộn lẫn

- **Expected fact:** thông tin cuối cùng phải đúng, chẳng hạn “14 ngày”.
- **Expected evidence:** nguồn nào phải hỗ trợ kết luận, chẳng hạn `policy-v3#pro-refund`.
- **Expected action:** ứng dụng phải làm hoặc tránh làm gì, chẳng hạn gọi `getOrderStatus` với ID đã được xác minh.

Một chatbot có thể đạt expected fact nhờ đoán trúng, nhưng không đạt expected evidence khi không truy xuất nguồn. Một ứng dụng có thể xuất câu trả lời đúng nhưng vi phạm expected action vì không kiểm tra quyền tool.

### 4.3. Dataset bao phủ nhiều nhóm lỗi

Không chỉ lưu câu hỏi thuận lợi. Nên có các nhóm:

1. Câu hỏi đúng tài liệu, trả lời ngắn.
2. Câu cần tổng hợp nhiều đoạn có căn cứ.
3. Câu thiếu nguồn và phải thừa nhận không biết.
4. Câu có tài liệu cũ và mới mâu thuẫn.
5. Câu dễ gây nhầm số liệu, điều kiện hoặc đơn vị.
6. Câu cần gọi tool nhưng tool trả lỗi/timeout.
7. Câu không được phép gọi tool vì thiếu quyền hoặc xác nhận.
8. Câu đưa chỉ dẫn gây nhiễu vào tài liệu retrieval.

Khi báo kết quả cần tách nhóm. Một pass rate chung 96% có thể che nhóm “thiếu nguồn” chỉ đạt 60%.

### 4.4. Giữ dataset có phiên bản và có người sở hữu nhãn

Với mỗi ca, ghi nguồn tạo nhãn, người/phương pháp xác minh, thời điểm hiệu lực và lý do thay đổi. Nếu sửa expected answer từ 30 thành 14 ngày, đó phải là một **phiên bản dataset mới hoặc bản ghi thay đổi có thể truy vết**. Không âm thầm sửa nhãn rồi so điểm candidate với baseline đã chấm theo nhãn cũ.

Dữ liệu cá nhân trong case thực tế phải được ẩn hoặc thay thế bằng dữ liệu kiểm thử có kiểm soát.

## 5. Thu bằng chứng thực thi đúng chỗ trong Spring AI

Dữ liệu đánh giá chỉ có ý nghĩa khi trỏ tới **bằng chứng của chính lần chạy được chấm**. Với Spring AI, có thể bố trí điểm thu bằng chứng tại những ranh giới sau:

~~~mermaid
flowchart TD
    Q["Input + caseId + attemptId"] --> A["ChatClient / Advisors"]
    A --> R["VectorStore retrieval"]
    R --> D["Các Document trả về<br/>ID, version, rank"]
    D --> P["Prompt sau khi ghép context"]
    P --> M["ChatModel call"]
    M --> T{"Có tool call?"}
    T -- "Có" --> F["Tool invocation<br/>args, status, result"]
    F --> M2["ChatModel continuation"]
    T -- "Không" --> O["Answer + citations"]
    M2 --> O
    A -.-> E["Evidence store / trace links"]
    R -.-> E
    D -.-> E
    M -.-> E
    F -.-> E
    O -.-> E
~~~

Dấu vết cần thu có thể bao gồm:

| Ranh giới | Bằng chứng tối thiểu | Tác dụng chẩn đoán |
| --- | --- | --- |
| Nhận request | `attemptId`, loại case, thời điểm, environment, release | Phân biệt những lần chạy khác nhau |
| Trước retrieval | Query/phiên bản bước viết lại query, bộ lọc quyền, `top-k` | Kiểm tra cấu hình truy xuất |
| Sau retrieval | Document IDs, versions, rank, metadata an toàn | Xác nhận model có nhận được bằng chứng cần thiết không |
| Ghép prompt | Prompt template version, context IDs, cấu hình truncation | Tìm lỗi mất hoặc đảo thứ tự thông tin |
| Gọi ChatModel | Provider/model version, trạng thái, token usage, duration | Phân tích generation, latency và chi phí |
| Gọi tool | Tên tool, đối số đã lọc, kết quả, lỗi, thời gian, quyền | Xác nhận hành động thực sự diễn ra |
| Trả response | Answer thực tế hoặc tham chiếu lưu an toàn, citation IDs | Nối đầu ra với đánh giá |
| Telemetry | Trace ID, span IDs, metric sample/series, log links | Định vị bước lỗi/chậm |

**Cảnh báo phương pháp:** Không mặc định mọi thông tin bảng trên được Spring AI tự ghi đầy đủ. Observation/tracing có thể cung cấp dấu vết vận hành; việc lưu danh sách tài liệu RAG, phiên bản policy, rubric và nội dung câu trả lời phục vụ evaluation thường cần mã tích hợp do nhóm thiết kế. Mức hỗ trợ thay đổi theo Spring AI, provider, advisor và cấu hình.

### 5.1. Evidence về nội dung và evidence về telemetry

Có hai loại bằng chứng cần dùng đúng mục đích:

- **Bằng chứng nội dung:** các đoạn văn bản/context thực sự cho model xem, kết quả tool, câu trả lời đã tạo. Dùng để kiểm tra relevance, groundedness, factual correctness hoặc quyết định tool.
- **Bằng chứng vận hành:** span duration, status, lỗi, token usage, retry count. Dùng để biết một request đi qua các bước nào, gặp lỗi kỹ thuật gì và dùng bao nhiêu tài nguyên.

Một trace cho thấy `VectorStore query` thành công **không chứng minh truy xuất đúng tài liệu**. Muốn biết điều đó, phải có IDs hoặc snapshot của tài liệu đã truy xuất đối chiếu với dataset.

Tương tự, token usage chính xác và latency thấp **không chứng minh câu trả lời đúng nội dung**.

### 5.2. Lưu dữ liệu thế nào để kiểm chứng mà vẫn bảo vệ riêng tư?

Các prompt, câu trả lời và tool arguments có thể chứa dữ liệu nhạy cảm. Không cần đưa nguyên văn tất cả vào metric hoặc trace.

- Với **metrics**, dùng tag có số lượng giá trị hữu hạn như `releaseVersion`, `operation`, `provider` và `status`; tránh nội dung prompt và user ID.
- Với **trace**, lưu thời gian, quan hệ span, mã lỗi, tài liệu/tool ID an toàn và tham chiếu tới kho evidence có phân quyền.
- Với **evidence store**, chỉ lưu dữ liệu cần để đánh giá; có thể che nội dung nhạy cảm, mã hóa, áp dụng quyền truy cập và thời gian lưu.
- Với **tool side effects**, không chỉ dựa vào log thành công; có thể cần xác nhận trạng thái hậu điều kiện từ hệ thống nguồn trong môi trường kiểm thử.
- Với **hash**, chỉ dùng để xác định hai bản dữ liệu có giống nhau; một hash đơn lẻ không cho phép người đánh giá đọc và xác minh ngữ nghĩa nội dung.

Khi không được phép lưu raw prompt hoặc kết quả tool, cần ghi rõ **giới hạn kiểm chứng** của báo cáo; không tuyên bố đã xác thực nội dung nếu bằng chứng cần thiết không tồn tại.

## 6. Kết quả đánh giá phải tham chiếu bằng chứng nào?

Một kết quả `PASS` hoặc `FAIL` không phải là sự kiện thực thi nguyên thủy. Nó là kết quả áp dụng **tiêu chí** lên **một hoặc nhiều phần bằng chứng**.

Ví dụ bản ghi kết quả có cấu trúc:

~~~json
{
  "attemptId": "attempt-REFUND-001-v2-01",
  "caseId": "REFUND-001",
  "metric": "factualCorrectness",
  "rubricVersion": "refund-rubric-v1",
  "evaluator": {
    "type": "human-reviewed-rule",
    "version": "fact-check-v1"
  },
  "verdict": "FAIL",
  "score": 0.0,
  "reason": "Câu trả lời nêu 30 ngày, nguồn đang hiệu lực quy định 14 ngày.",
  "evidenceRefs": [
    "answer:attempt-REFUND-001-v2-01",
    "reference:policy-v3#pro-refund"
  ],
  "evaluatedAt": "2026-05-18T10:25:00Z"
}
~~~

Các trường là **đề xuất hợp đồng dữ liệu của ứng dụng**, không phải JSON bắt buộc của Spring AI. Một schema tốt giúp trả lời: Ai chấm? Dựa trên dữ liệu nào? Có đủ dữ liệu không? Kết luận có tái tạo được không?

### 6.1. Phân biệt các evaluator

| Loại kiểm tra | Nguồn phải đối chiếu | Ví dụ kết quả |
| --- | --- | --- |
| **Relevance** | Question + answer thực tế (và context nếu rubric yêu cầu) | “Trả lời đúng chủ đề” |
| **Groundedness / faithfulness** | Answer + **document thực sự truy xuất/đưa vào model** | “Khẳng định được context hỗ trợ” |
| **Factual correctness** | Answer + nguồn chuẩn độc lập đã xác minh | “Đúng chính sách hiện hành” |
| **Retrieval hit@k / Recall@k** | Retrieved IDs + nhãn document liên quan | “Có tìm được nguồn cần thiết không?” |
| **Tool selection / arguments** | Expected action + tool invocation thực tế | “Có gọi đúng tool với ID phù hợp?” |
| **Tool side effect** | Expected hậu điều kiện + trạng thái backend thực tế | “Giao dịch thực sự được tạo đúng một lần?” |
| **Latency / cost** | Threshold + duration, usage, giá áp dụng | “Có vượt giới hạn vận hành?” |

Đặc biệt, dùng nguồn chuẩn làm context cho bộ chấm groundedness sẽ **che mất lỗi retrieval**. Ngược lại, dùng tài liệu đã truy xuất để kết luận factual correctness mà không kiểm tra tính hiện hành của nó có thể làm câu trả lời dựa trên tài liệu cũ vẫn được coi là đúng.

### 6.2. Không phải mọi đánh giá đều là một số điểm

Một số tiêu chí phù hợp với `boolean` (schema valid), một số phù hợp với tỷ lệ (Recall@k), thang điểm có rubric (answer completeness), hoặc nhãn phân loại lỗi (wrong document, wrong tool, unsafe action).

Với ứng dụng thực, nên chuẩn hóa trạng thái:

- **PASS:** đủ bằng chứng và tiêu chí đạt.
- **FAIL:** đủ bằng chứng và tiêu chí không đạt.
- **UNKNOWN / NOT_EVALUATED:** thiếu dữ liệu, evaluator lỗi hoặc không có cơ sở chấm.
- **NOT_APPLICABLE:** tiêu chí không áp dụng cho ca này.

**Không tính UNKNOWN thành PASS.** Nếu thiếu danh sách tài liệu truy xuất, không thể kết luận “retrieval đạt”. Nếu evaluator timeout, đó là lỗi của **quá trình chấm**; cần báo riêng thay vì quy hết thành lỗi câu trả lời.

### 6.3. LLM-as-a-judge cũng cần truy xuất nguồn gốc

Spring AI cung cấp khái niệm `Evaluator`, `EvaluationRequest`, `EvaluationResponse` và các công cụ như `RelevancyEvaluator`, `FactCheckingEvaluator`. Các đánh giá dựa trên model có thể cho phản hồi ngữ nghĩa nhưng không phải bằng chứng tuyệt đối.

Để có thể so sánh hoặc chấm lại:

1. Ghi model/judge version, prompt và rubric version.
2. Ghi những tài liệu đầu vào thực sự gửi cho evaluator.
3. Lưu score, pass/fail, feedback và lỗi chấm nếu có.
4. Kiểm tra một bộ nhãn do con người xác minh; theo dõi trường hợp false positive/false negative.
5. Không thay đổi judge giữa hai phiên bản ứng dụng mà không ghi nhận tác động tới điểm.

Khi cần kết quả có tính xác định, ưu tiên test thông thường như kiểm tra JSON schema, tham số tool, ID tài liệu, phép tính tiền hoặc quyền truy cập.

## 7. Ví dụ RAG: kết quả nhìn giống đúng nhưng sai nguồn hiện hành

Xét một case đã định nghĩa ở mục 4:

- **Câu hỏi:** “Gói Pro được hoàn phí trong bao lâu?”
- **Nguồn chuẩn:** `policy-v3#pro-refund` ghi 14 ngày.
- **Nguồn cũ:** `policy-v2#pro-refund` ghi 30 ngày; đã hết hiệu lực.

Trong một attempt giả định:

~~~json
{
  "runId": "candidate-rag-v2",
  "attemptId": "attempt-REFUND-001-v2-01",
  "caseId": "REFUND-001",
  "configuration": {
    "promptVersion": "answer-prompt-v4",
    "modelVersion": "chat-model-v2",
    "pipelineVersion": "rag-v2",
    "corpusVersion": "policy-corpus-2026-05"
  },
  "retrieval": {
    "topK": 3,
    "documents": [
      {"id": "policy-v2#pro-refund", "rank": 1, "effective": false},
      {"id": "faq-pro-legacy", "rank": 2, "effective": false}
    ]
  },
  "answer": "Gói Pro được hoàn phí trong vòng 30 ngày.",
  "citations": ["policy-v2#pro-refund"],
  "telemetry": {
    "traceId": "trace-refund-001",
    "vectorStoreLatencyMs": 130,
    "chatModelLatencyMs": 810,
    "totalLatencyMs": 1100,
    "inputTokens": 1200,
    "outputTokens": 65
  }
}
~~~

Khi đánh giá, có thể thu được:

| Tiêu chí | Kết quả minh họa | Bằng chứng và ý nghĩa |
| --- | --- | --- |
| Answer relevance | **PASS** | Trả lời về thời hạn hoàn phí của gói Pro |
| Groundedness so với retrieved context | **Có thể PASS** | Tài liệu cũ đã truy xuất thật sự ghi 30 ngày |
| Factual correctness so với nguồn đang hiệu lực | **FAIL** | `policy-v3` ghi 14 ngày |
| Expected document hit@3 | **FAIL** | Không có `policy-v3#pro-refund` trong kết quả |
| Citation freshness | **FAIL** | Chỉ trích dẫn `policy-v2` đã hết hiệu lực |
| Technical success | **PASS** | Không có lỗi kỹ thuật trong request minh họa |
| Latency threshold 2 giây | **PASS** | Tổng thời gian 1,1 giây |

Các giá trị trên **chỉ là minh họa**, và tính pass của groundedness còn tùy rubric/judge. Bảng làm rõ vì sao chỉ xem “có trích dẫn”, “relevance đạt” hoặc “HTTP 200” sẽ bỏ qua lỗi.

### 7.1. Chuỗi suy luận có bằng chứng

**Quan sát 1:** dataset mong tìm tài liệu `policy-v3`.  
**Quan sát 2:** execution evidence cho thấy retrieval chỉ lấy `policy-v2` và FAQ cũ.  
**Quan sát 3:** model trả lời 30 ngày và dẫn `policy-v2`.  
**Kết quả:** retrieval freshness và factual correctness không đạt.  
**Giả thuyết ưu tiên:** bộ lọc tài liệu theo hiệu lực, index hoặc nguồn corpus đang có vấn đề.

Có thể kiểm chứng giả thuyết bằng cách kiểm tra metadata hiệu lực của index, bộ lọc retrieval và cách cập nhật corpus. Nếu sau khi sửa, attempt mới truy xuất `policy-v3` và trả lời 14 ngày, đó là bằng chứng cải thiện trên **case này**. Để kết luận thay đổi tốt toàn bộ hệ thống, vẫn phải chạy lại dataset theo nhóm và đo tác động đến độ trễ/chi phí.

### 7.2. Trường hợp lỗi nằm ở generation

Giả sử execution evidence khác: retrieval đã lấy `policy-v3` và câu trả lời vẫn là 30 ngày. Khi đó lỗi không còn được giải thích đơn giản bằng “không tìm thấy nguồn”. Cần kiểm tra:

- `policy-v3` có thực sự nằm trong context mà model nhận không, hay đã bị cắt khi ghép prompt?
- Prompt có chứa nhiều nguồn mâu thuẫn nhưng không nêu thứ tự ưu tiên?
- Model có bỏ qua nội dung nguồn hay diễn giải sai thời hạn?
- Lời gọi model có dùng đúng cấu hình được đánh giá?
- Evaluator có chấm đúng document và answer của **cùng attempt**?

Cùng kết quả `FAIL`, nhưng bằng chứng khác dẫn tới hướng sửa khác.

## 8. Ví dụ tool calling: bằng chứng phải xác nhận cả quyết định và hành động

Một chatbot có tool `getOrderStatus`. Ca kiểm thử yêu cầu: “Hãy cho biết tình trạng đơn DH-123 của tôi”. Dữ liệu thử nghiệm xác nhận người dùng có quyền đọc đơn và backend trả trạng thái “đang giao”.

Dataset có thể mô tả:

~~~json
{
  "caseId": "ORDER-STATUS-001",
  "input": "Đơn DH-123 đang ở đâu?",
  "principal": "test-user-A",
  "expectedToolCalls": [
    {
      "name": "getOrderStatus",
      "arguments": {"orderId": "DH-123"}
    }
  ],
  "mockToolResult": {
    "orderId": "DH-123",
    "status": "IN_TRANSIT"
  },
  "expectedAnswerFacts": ["Đơn đang giao"],
  "forbiddenBehavior": ["Invent status without tool result"]
}
~~~

Execution evidence có thể gồm:

~~~json
{
  "attemptId": "attempt-ORDER-STATUS-001-1",
  "toolCalls": [
    {
      "toolInvocationId": "tool-call-1",
      "toolName": "getOrderStatus",
      "arguments": {"orderId": "DH-123"},
      "authorization": "ALLOWED",
      "resultStatus": "SUCCESS",
      "result": {"status": "IN_TRANSIT"}
    }
  ],
  "answer": "Đơn DH-123 đang được giao.",
  "traceId": "trace-order-123"
}
~~~

Từ hai bản ghi, có thể kiểm tra độc lập:

- **Tool selection:** có gọi `getOrderStatus` không?
- **Tool arguments:** ID có đúng `DH-123` không?
- **Authorization:** có bằng chứng về quyền truy cập được xác thực ở thành phần có thẩm quyền không?
- **Tool result usage:** câu trả lời có phản ánh đúng `IN_TRANSIT` không?
- **Error handling:** nếu tool trả `NOT_FOUND` hay `403`, model có tránh báo tình trạng bịa đặt không?

Nếu model trả lời “đang giao” nhưng **không có tool call**, answer text có thể trùng expected answer. Tuy nhiên, ta vẫn phải đánh giá **không đạt hợp đồng hành vi** vì không dùng nguồn thực tế bắt buộc.

Với tool có tác dụng phụ như `refundOrder`, bằng chứng về việc **đã gửi request** không đủ để chứng minh giao dịch **đã được commit đúng một lần**. Cần thêm trạng thái hậu điều kiện được xác minh trong môi trường kiểm thử. Quyền truy cập cũng phải được enforced ở backend/tool, không chỉ dựa vào việc model “được dặn” qua prompt.

## 9. Tích hợp kết quả đánh giá với ứng dụng Spring AI

Trong thực hành, có thể dùng evaluator của Spring AI cho tiêu chí ngữ nghĩa và dùng Java/JUnit assertions cho các tiêu chí xác định.

### 9.1. Ví dụ Java: kết quả evaluator gắn với attempt

Đoạn mã minh họa dưới đây nhận sẵn danh sách `retrievedDocuments` và `actualAnswer` **đã thu trong lần chạy thật**. `Evaluator` có thể được cung cấp bằng cách cấu hình `RelevancyEvaluator` hoặc `FactCheckingEvaluator` phù hợp với phiên bản Spring AI mà dự án sử dụng.

~~~java
import java.util.List;

import org.springframework.ai.document.Document;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.Evaluator;

public final class LinkedEvaluation {

    public record Verdict(
            String attemptId,
            String caseId,
            String metric,
            String evaluatorVersion,
            String traceId,
            boolean passed,
            String feedback) {}

    public Verdict evaluate(
            Evaluator evaluator,
            String evaluatorVersion,
            String metric,
            String attemptId,
            String caseId,
            String traceId,
            String question,
            List<Document> retrievedDocuments,
            String actualAnswer) {

        EvaluationRequest request =
                new EvaluationRequest(question, retrievedDocuments, actualAnswer);

        EvaluationResponse response = evaluator.evaluate(request);

        return new Verdict(
                attemptId,
                caseId,
                metric,
                evaluatorVersion,
                traceId,
                response.isPass(),
                response.getFeedback());
    }
}
~~~

Lưu ý:

- Đoạn mã là ví dụ **liên kết metadata với kết quả chấm**, không tự tạo dataset, kết nối VectorStore hay sinh `traceId`.
- Phải lấy `retrievedDocuments` từ **đúng execution attempt**; nếu app dùng advisor thì thiết kế cách capture tại ranh giới retrieval/context.
- `traceId` phải lấy từ ngữ cảnh tracing thực tế của request, khi có trace; không được tự chế một ID rồi coi như đã ghi trace.
- `response.isPass()` biểu thị kết luận của evaluator đã chọn. Nó không mặc nhiên là factual correctness, không kiểm tra phân quyền hay thành công của một giao dịch.
- Nếu evaluator lỗi/timeout, hãy lưu trạng thái `NOT_EVALUATED` hoặc lỗi evaluator riêng; đừng tạo ra bản ghi giả với `passed=true`.

### 9.2. Các phép kiểm xác định nên đi trước

Nếu ca tool yêu cầu `getOrderStatus` với `orderId=DH-123`, nên kiểm tra bằng test Java thay vì dùng model chấm nội dung đối số:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ToolEvidenceTest {

    @Test
    void toolCallMustMatchExpectedArguments() {
        String expectedTool = "getOrderStatus";
        String expectedOrderId = "DH-123";

        // Ví dụ evidence đã được test harness thu từ tool dispatcher.
        String actualTool = "getOrderStatus";
        String actualOrderId = "DH-123";
        int invocationCount = 1;

        assertEquals(expectedTool, actualTool);
        assertEquals(expectedOrderId, actualOrderId);
        assertEquals(1, invocationCount);
    }
}
~~~

Trong dự án thực, các giá trị `actual...` phải được lấy từ spy/fake tool hoặc sự kiện dispatcher thu thập tự động; các biến gán trực tiếp ở ví dụ chỉ minh họa assertion. Với tác vụ có tác dụng phụ, cần thêm kiểm tra trạng thái backend, idempotency và quyền.

### 9.3. Tại sao cần giữ input cho evaluator?

Nhiều evaluator là **LLM-as-a-judge**: chúng dựa trên prompt chấm, rubric, answer và context. Nếu ta chỉ giữ `pass=true` mà không lưu cách cấu hình judge hoặc tham chiếu context đã chấm, khi điểm thay đổi sẽ không biết do ứng dụng hay do cách đánh giá. Cần mô tả rõ `evaluatorVersion`, `rubricVersion` và evidence refs.

## 10. Liên kết điểm chất lượng với traces, metrics, token và chi phí

Spring AI có khả năng observability thông qua cơ chế observation và Micrometer của hệ sinh thái Spring. Tùy phiên bản và cấu hình, có thể có dữ liệu đo của ChatClient, ChatModel, Advisors, VectorStore, tool calling và usage metadata do provider cung cấp.

**Cần phân biệt hai cấp dữ liệu:**

- **Per-attempt evidence:** dấu vết một request cụ thể, gồm trace/span, thời gian từng bước, số lời gọi model, token usage trả về cho từng call (nếu có).
- **Aggregate metrics:** số liệu tổng hợp như trung bình latency, p95, error rate, token tổng, pass rate theo phiên bản.

Một metric `p95 latency = 2.5 s` thuộc nhóm request được đo, **không phải** “request REFUND-001 mất 2.5 s”. Ngược lại, trace riêng của REFUND-001 có tổng thời gian 1.1 s chưa đủ để kết luận SLO toàn hệ thống đạt.

### 10.1. Độ trễ và token theo bước

Ví dụ một request RAG có tool:

~~~text
HTTP POST /ask                          2800 ms
└── ChatClient                          2650 ms
    ├── Advisor / VectorStore           350 ms
    ├── ChatModel #1                    900 ms
    ├── Tool getOrderStatus             400 ms
    └── ChatModel #2                    1000 ms
~~~

Các span có quan hệ cha–con; thời gian của span cha thường bao gồm thời gian con, không cộng trùng. Khi tính chi phí, nếu ChatModel được gọi hai lần thì token usage và chi phí model cần cộng **hai lần gọi** tương ứng; còn lần gọi tool có thể có chi phí riêng theo backend.

Chi phí model ước tính từ token và giá áp dụng, với trường hợp tính phí theo input/output token:

\[
\mathrm{cost}
=
\frac{\mathrm{inputTokens}}{10^6}\times \mathrm{priceInputPerMillion}
+
\frac{\mathrm{outputTokens}}{10^6}\times \mathrm{priceOutputPerMillion}
\]

Chẳng hạn giá **giả định** 2 USD/triệu input và 8 USD/triệu output; một request dùng tổng cộng 2.000 input và 500 output tokens có chi phí model ước tính:

\[
(2000 \times 2 + 500 \times 8) / 10^6 = 0.008\;\mathrm{USD}.
\]

Phép tính chưa bao gồm embedding, reranking, phí tool, chi phí hạ tầng, caching hoặc phí chạy evaluator. Usage provider có thể thiếu hoặc khác theo chế độ streaming, vì vậy cần ghi nguồn và giới hạn của ước tính.

### 10.2. Liên kết run quality với health dashboard

Một báo cáo có thể hiển thị:

| Thông tin | Giá trị minh họa | Nguồn |
| --- | --- | --- |
| `runId` | `candidate-rag-v2` | Evaluation orchestrator |
| Số ca đã chạy | 100 | Dataset + execution records |
| Số ca được chấm chất lượng | 96 | Evaluation results |
| Số ca không chấm được | 4 | Evaluation error/unknown |
| Factual correctness đạt | 91/96 | Kết quả chấm trên ca hợp lệ |
| Technical request success | 98/100 | Execution evidence |
| End-to-end latency p95 | 2.8 s | Phân bố các request được đo |
| Input tokens trung bình | 1.750 | Provider usage/telemetry |
| Estimated model cost/request | 0.006 USD | Usage + bảng giá phiên bản |

Nếu chỉ nói “91/96 đạt” mà bỏ 4 ca chưa chấm, người đọc có thể hiểu nhầm chất lượng trên 100 request. Nếu một ca không có output vì timeout, không thể coi là câu trả lời đúng; cần báo technical completion và end-to-end task success riêng.

**Mẫu số luôn quan trọng:** xác định rõ `denominator` của pass rate, error rate và latency.

## 11. Thiết kế kho lưu evidence và kết quả đánh giá

Có nhiều lựa chọn: tệp JSONL theo run, bảng quan hệ, object storage cho các bản ghi lớn và tracing backend cho spans. Điều quan trọng là **tính nhất quán của khóa và phiên bản**, không phụ thuộc duy nhất vào công nghệ lưu trữ.

Một cấu trúc thư mục **mang tính minh họa**, không phải yêu cầu của Spring AI:

~~~text
evaluation-results/
└── run-candidate-v2/
    ├── manifest.json
    ├── attempts.jsonl
    ├── retrieved-documents.jsonl
    ├── tool-events.jsonl
    ├── evaluator-results.jsonl
    └── metrics-summary.json
~~~

Trong `manifest.json`, lưu cấu hình bất biến của run; mỗi dòng `attempts.jsonl` chứa `caseId`, `attemptId` và `traceId`. `evaluator-results.jsonl` tham chiếu đến `attemptId` và phiên bản rubric. Không cần sao chép nội dung nhạy cảm trong mọi tệp; dùng tham chiếu tới evidence store có quyền truy cập thích hợp.

### 11.1. Các bất biến liên kết dữ liệu

Để tránh join nhầm kết quả:

1. Mỗi `attemptId` phải thuộc đúng một `runId` và một `caseId` với phiên bản dataset rõ.
2. Mỗi kết quả evaluator phải tham chiếu tới **một attempt có thật** và đúng metric.
3. Mọi document/tool evidence dùng để chấm phải thuộc đúng attempt đó hoặc là nguồn tham chiếu được chỉ rõ độc lập.
4. Khi so sánh hai run, phải ghi khác biệt cấu hình, judge và nguồn chuẩn.
5. Nếu thiếu evidence bắt buộc cho metric, trạng thái phải là `UNKNOWN` hoặc `NOT_EVALUATED`, không được gán PASS.
6. Nếu chấm lại bằng judge mới, giữ nguyên verdict cũ và tạo verdict mới mang `evaluatorVersion` khác.
7. Các phép tổng hợp không được đếm một attempt nhiều lần vì có nhiều evaluator runs.

Có thể hình dung một `UNIQUE(attemptId, metric, evaluatorVersion, evaluationRunId)` tùy thiết kế lưu trữ, giúp lưu nhiều lần chấm nhưng tránh trùng ngoài ý muốn. Nếu cần nhiều lần chạy judge cùng phiên bản, thêm `evaluationAttemptId` riêng.

### 11.2. Chấm lại mà không chạy lại model: khi nào khả thi?

Nếu đã lưu đủ answer, retrieved context, nguồn chuẩn, rubric và metadata, nhóm có thể **re-evaluate** cùng execution attempt khi thay bộ chấm. Điều này hữu ích để phát hiện sai lệch của LLM judge.

Tuy vậy, chấm lại **không tạo ra một execution mới**: không sinh trace mới của pipeline cũ, không đo lại latency thực và không chứng minh backend/tool lúc đó hoạt động thế nào nếu evidence ban đầu bị thiếu. Nếu thay corpus/index và muốn đo retrieval mới, phải chạy pipeline lại.

## 12. So sánh phiên bản bằng bằng chứng liên kết được

Giả sử nhóm so `baseline-v1` và `candidate-v2` trên cùng `datasetVersion=policy-eval-v1` và cùng rubric. Kết quả giả định:

| Chỉ số | baseline-v1 | candidate-v2 |
| --- | ---: | ---: |
| Technical completion | 99/100 | 100/100 |
| Retrieval hit@5 | 88/100 | 94/100 |
| Factual correctness trên ca chấm được | 94/99 | 93/100 |
| Groundedness trên ca chấm được | 96/99 | 95/100 |
| p95 latency | 2.1 s | 3.2 s |
| Input tokens trung bình | 1.200 | 2.050 |
| Chi phí model ước tính/request | 0.004 USD | 0.006 USD |

Nhìn tổng thể, candidate tìm được nguồn thường xuyên hơn nhưng factual correctness giảm và latency tăng. **Muốn biết vì sao**, hãy join những `caseId` chuyển từ PASS sang FAIL, truy cập `attemptId` của từng phiên bản, đối chiếu `retrievedDocumentIds`, answer và trace.

Ví dụ một ca từ PASS sang FAIL:

~~~text
caseId: REFUND-001
  baseline attempt:
    retrieved: policy-v3#pro-refund
    answer: "14 ngày"
    factualCorrectness: PASS
    totalLatencyMs: 950

  candidate attempt:
    retrieved: policy-v2#pro-refund, policy-v3#pro-refund
    answer: "30 ngày"
    factualCorrectness: FAIL
    totalLatencyMs: 1550

Hypothesis:
  Candidate đưa thêm chính sách cũ vào context,
  khiến model chọn nhầm thời hạn.
Next check:
  Phân tích thứ tự context, hiệu lực nguồn, prompt và retry.
~~~

Từ hai attempt ta có **cơ sở đặt giả thuyết**; chưa thể khẳng định nguyên nhân duy nhất nếu đồng thời thay nhiều thành phần. Nên thử tách biến hoặc tái hiện theo cấu hình cố định.

### 12.1. So sánh đúng “cùng hệ quy chiếu”

Trước khi kết luận chất lượng tăng/giảm, xác nhận:

- Cùng tập câu hỏi hoặc có cách so khớp case ổn định.
- Cùng đáp án chuẩn và hiệu lực chính sách.
- Cùng rubric/judge hoặc có báo cáo hiệu chỉnh sai khác bộ chấm.
- Đã ghi phiên bản prompt, model, embedding, corpus, index, tool và pipeline.
- Điều kiện tải/độ trễ có thể so sánh phù hợp.
- Các ca timeout, evaluator error và chưa có kết quả không bị âm thầm loại khỏi mẫu số.

Nếu không thỏa các điều kiện, báo cáo có thể vẫn hữu ích để quan sát nhưng không đủ mạnh để kết luận candidate gây ra cải thiện hoặc hồi quy.

## 13. Những tình huống bằng chứng mâu thuẫn

Không phải lúc nào dataset, execution và evaluation cũng đồng thuận. Mâu thuẫn là tín hiệu cần điều tra:

| Hiện tượng | Nguyên nhân có thể | Điều cần kiểm |
| --- | --- | --- |
| `PASS` nhưng answer trái expected facts | Rubric sai, judge bỏ sót, chấm nhầm source | Xem input judge và nhãn chuẩn |
| Retrieval hit@k là PASS nhưng không tìm thấy ID nguồn | Join nhầm attempt, version khác, tính metric sai | Kiểm tra retrieved IDs và thuật toán metric |
| Tool event ghi SUCCESS nhưng backend không có giao dịch | Chỉ ghi “request accepted”, không kiểm tra commit | Xem hậu điều kiện và trạng thái giao dịch |
| Token count bằng 0 nhưng có output dài | Provider không trả usage, lỗi mapping, metric thiếu | Xem raw usage metadata và cấu hình |
| Trace duration khác tổng thời gian API | Span lồng nhau, sampling, phần thời gian ngoài scope | Xem ranh giới đo và quan hệ span |
| Điểm chất lượng đổi dù output giống nhau | Judge/rubric/source đổi, tính bất định LLM judge | So phiên bản bộ chấm, nguồn chuẩn |
| Không có trace của một attempt | Sampling, lỗi instrument/export, không có trace context | Kiểm tra cấu hình và log liên kết |
| “Không có output” bị chấm PASS | Thiếu phân biệt technical failure với quality verdict | Quy tắc mẫu số, trạng thái NOT_EVALUATED |

Cần đặc biệt tránh **tính đúng theo cảm giác**: thấy câu trả lời trôi chảy và trace không lỗi rồi kết luận hệ thống chính xác. Ngược lại, evaluator nói FAIL không có nghĩa mọi thành phần đều lỗi; trace và evidence giúp khoanh vùng.

## 14. Độ tin cậy và giới hạn của từng bằng chứng

### 14.1. Dataset có thể sai hoặc lỗi thời

Đáp án chuẩn chưa được chuyên gia xác minh, tài liệu hết hiệu lực hoặc ví dụ không phản ánh yêu cầu thật sẽ làm evaluator kết luận sai. Vì vậy, cần chủ sở hữu nhãn và lịch cập nhật nguồn.

### 14.2. Bằng chứng thực thi có thể thiếu

Tracing lấy mẫu 10% không có nghĩa mọi request đều có trace. Một số provider có thể không cung cấp usage chi tiết, hoặc log nội dung bị tắt vì quyền riêng tư. Nếu evidence thiếu, phải nêu giới hạn, không giả định dữ liệu chưa quan sát được.

### 14.3. Evaluator cũng mắc lỗi

LLM-as-a-judge có thể thiên lệch do ngôn ngữ, độ dài câu trả lời, cách đặt prompt chấm hoặc model version. Có thể so với tập nhãn do con người đánh giá, kiểm tra consistency giữa lần chạy và thống kê false positive/false negative.

### 14.4. Chứng minh quan hệ nhân quả cần phép thử

“Sau khi tăng `top-k`, latency tăng” là quan sát có ích. Để khẳng định tăng `top-k` **gây** tăng latency, cần kiểm soát các thay đổi đi kèm, tải hệ thống và điều kiện provider; nếu không, đó chỉ là một giả thuyết hợp lý.

### 14.5. Cẩn trọng với dữ liệu nhạy cảm

Thử nghiệm trên dữ liệu production cần áp dụng quyền truy cập, loại bỏ thông tin cá nhân, quy định lưu trữ, và ưu tiên bằng chứng tối thiểu. Có thể kiểm tra hành vi tool bằng môi trường cô lập, fake/stub hoặc dữ liệu giả thay vì tái hiện thao tác thật với khách hàng.

## 15. Từ bằng chứng đến release gate

Khi một phiên bản chuẩn bị phát hành, các gate cần nêu rõ **nguồn dữ liệu**, **cách tính** và **cách xử lý kết quả chưa xác định**.

Ví dụ ngưỡng **giả định**, không phải chuẩn bắt buộc của Spring AI:

~~~yaml
releaseGates:
  datasetVersion: policy-eval-v1
  rubricVersion: policy-rubric-v1
  software:
    authorization: must-pass
    toolContract: must-pass
  quality:
    factualCorrectness:
      minPassRate: 0.98
      denominator: completed-and-evaluated-cases
    criticalCases:
      requirePass: true
    unevaluatedCases:
      maxCount: 0
  operations:
    p95LatencyMs:
      max: 2500
    technicalErrorRate:
      max: 0.01
~~~

Một pipeline cần tách kết luận:

1. **Execution chưa chạy được:** không có bằng chứng chất lượng; kết quả test execution FAIL.
2. **Execution thành công nhưng evaluator lỗi:** đánh dấu NOT_EVALUATED/UNKNOWN; chính sách gate quyết định có chặn.
3. **Evaluator có kết luận FAIL:** đánh giá chất lượng không đạt.
4. **Quality PASS nhưng tool vi phạm phân quyền:** software correctness FAIL và chặn theo gate an toàn.
5. **Quality PASS, chức năng đúng nhưng độ trễ vượt ngưỡng:** operational gate FAIL.

Nhờ giữ riêng ba loại dữ liệu, không có chỉ số tốt nào vô tình che được lỗi bắt buộc của một lớp khác.

## 16. Quy trình thực hành từ dataset tới báo cáo có thể điều tra

Hãy xây dựng chatbot Spring AI trả lời chính sách giả định *Sao Mai* bằng RAG và có một tool `getOrderStatus` chỉ đọc.

### Bước 1 — Tạo dataset có thể kiểm chứng

Tạo 12–20 ca gồm câu hỏi có nguồn, nguồn mâu thuẫn, thiếu nguồn, câu hỏi phải gọi tool và ca tool trả lỗi. Mỗi ca có `caseId`, expected facts, expected evidence, expected action và rubric.

### Bước 2 — Ghi phiên bản của run

Tạo `runId`, lưu `datasetVersion`, `promptVersion`, `modelVersion`, `corpusVersion`, `pipelineVersion` và `evaluatorVersion`. Khi chạy mỗi ca, tạo một `attemptId` duy nhất.

### Bước 3 — Thu evidence của lần chạy

Thu answer, document IDs/versions/rank, tool calls, trạng thái lỗi, traceId, latencies, token usage (khi provider cung cấp). Lưu bằng phương thức có kiểm soát dữ liệu nhạy cảm.

### Bước 4 — Chấm theo đúng nguồn

- Retrieval: đối chiếu retrieved IDs với expected retrieval.
- Relevance: so question với answer.
- Groundedness: so answer với context **thực sự đưa vào model**.
- Factual correctness: so answer với nguồn chuẩn được xác minh.
- Tool: kiểm tra chọn tool, đối số, trạng thái/hậu điều kiện.
- Operations: kiểm tra latency/cost với threshold.

### Bước 5 — Kết nối một ca FAIL với trace

Chọn một ca có factual correctness FAIL. Từ `attemptId` tìm answer và retrieved documents; qua `traceId` xem bước retrieval/model/tool có lỗi hoặc chậm. Viết giả thuyết nguyên nhân và cách kiểm chứng.

### Bước 6 — Thay một yếu tố rồi so sánh

Đổi `top-k`, prompt hoặc model, giữ các yếu tố khác có thể cố định. Chạy lại dataset với `runId` mới. Lập bảng case trước/sau và phân tích cả chất lượng, thời gian, chi phí.

### Bước 7 — Viết báo cáo có đường dẫn bằng chứng

Một báo cáo hoàn chỉnh nên cho biết:

| Mục | Điều bắt buộc |
| --- | --- |
| Phạm vi | Dataset version, số ca, nhóm rủi ro, môi trường |
| Cấu hình | Prompt, model, corpus/index, retrieval, tool, pipeline |
| Kết quả | Pass/FAIL/UNKNOWN cho từng metric, mẫu số rõ ràng |
| Hồi quy | Case ID nào đổi kết quả, vì sao |
| Bằng chứng | Attempt ID, document/tool refs, trace ID hoặc lý do không có |
| Hiệu năng | Latency phân vị, token, cost và nguồn tính |
| Kết luận | Đạt/chưa đạt gate, giới hạn phép đo, bước xác minh tiếp theo |

**Tiêu chí hoàn thành:** người khác có thể lấy một case FAIL, tìm lại bằng chứng của đúng attempt và hiểu được vì sao evaluator đưa ra verdict đó, ngay cả khi người tạo báo cáo không có mặt.

### Câu hỏi tự kiểm tra

1. Vì sao `caseId` và `traceId` không thể dùng thay thế nhau?
2. Nếu chatbot trả lời “14 ngày” mà không truy xuất chính sách, expected fact và expected evidence có thể cho hai kết quả khác nhau thế nào?
3. Nếu answer giống nhau giữa hai run nhưng điểm thay đổi, cần so sánh metadata nào trước khi kết luận model thoái hóa?
4. Khi `FactCheckingEvaluator` nhận tài liệu chuẩn thay vì tài liệu RAG thực sự tìm được, loại lỗi nào có thể bị che giấu?
5. Một trace cho thấy gọi `refundOrder` thành công. Bằng chứng bổ sung nào cần có để khẳng định giao dịch được thực hiện đúng một lần?
6. Nếu chỉ 90/100 attempt có câu trả lời và 85/90 câu được đánh giá đạt, nên báo các tỷ lệ nào để không gây hiểu nhầm?
7. Vì sao một request có latency thấp không chứng minh ứng dụng có câu trả lời đúng?
8. Nếu thay `rubricVersion` mà giữ nguyên prompt/model, có được so pass rate trực tiếp không? Cần làm gì?

## 17. Tổng kết

**Dữ liệu kiểm thử định nghĩa kỳ vọng**, **bằng chứng thực thi ghi nhận điều đã xảy ra** và **kết quả đánh giá đối chiếu hai phía theo một tiêu chí rõ ràng**. Các ID và phiên bản gắn ba nhóm dữ liệu thành chuỗi có thể kiểm chứng, chấm lại và dùng để điều tra hồi quy.

Trong Spring AI, chuỗi này đặc biệt quan trọng khi đánh giá RAG và tool calling: cùng một câu trả lời có thể liên quan nhưng sai sự thật, có vẻ đúng nhưng dùng nguồn cũ, hoặc đúng về nội dung nhưng sai về hành động. Metrics, traces, token và chi phí giải thích quá trình thực thi và mức sử dụng tài nguyên; chúng cần được liên kết với kết quả chấm thay vì bị xem như điểm chất lượng.

Một báo cáo đáng tin cậy không dừng ở “bao nhiêu phần trăm đạt”; nó cho phép truy ngược **ca nào → lần chạy nào → tài liệu/tool/model nào → bằng chứng nào → tiêu chí chấm nào → quyết định nào**. Đây là nền tảng để cải tiến prompt, model và pipeline có kiểm soát.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Boot — Production-ready Features (Actuator)](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Observations](https://docs.micrometer.io/micrometer/reference/observation.html)
