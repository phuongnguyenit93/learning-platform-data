# Vai trò của Evaluation và Observability trong vòng đời ứng dụng Spring AI

Một ứng dụng Spring AI không kết thúc khi lời gọi `ChatClient` đầu tiên trả về câu trả lời trôi chảy. Sau bản demo, nhóm phát triển sẽ tiếp tục chỉnh prompt, bổ sung dữ liệu cho RAG, thay embedding model, mở rộng công cụ, tối ưu độ trễ, triển khai phiên bản mới và xử lý những trường hợp người dùng thực tế gặp lỗi. Mỗi thay đổi có thể làm chất lượng tốt hơn ở nhóm câu hỏi này nhưng kém hơn ở nhóm khác.

Giả sử chatbot nội bộ trả lời về chính sách hoàn phí. Ở bản thử nghiệm, chatbot tìm đúng tài liệu và trả lời “14 ngày”. Sau khi nhóm vận hành tăng số đoạn tài liệu truy xuất từ 3 lên 8, tỷ lệ tìm thấy nguồn có thể tăng, nhưng prompt cũng dài hơn, làm phát sinh chi phí và độ trễ lớn hơn; một số đoạn cũ hoặc không liên quan còn có thể khiến model hiểu sai. Nếu chỉ kiểm tra một câu hỏi mẫu, nhóm sẽ khó phát hiện các tác động này.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, hai nhóm kỹ thuật tạo thành vòng phản hồi xuyên suốt:

- **Evaluation (đánh giá chất lượng):** dùng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling để quyết định một phiên bản **đáp ứng yêu cầu đến đâu**.
- **Observability (khả năng quan sát):** dùng metrics, traces, logs và dữ liệu token, chi phí, độ trễ để biết **hệ thống vận hành ra sao và vì sao kết quả thay đổi**.

Đánh giá và quan sát không phải hai công việc chỉ thực hiện sau khi triển khai. Chúng cần được thiết kế từ khi đặt yêu cầu, tích hợp vào quá trình phát triển, dùng làm điều kiện phát hành, tiếp tục theo dõi trong production và cung cấp bằng chứng cho lần cải tiến tiếp theo.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Mô tả vai trò của Evaluation và Observability tại từng giai đoạn của vòng đời ứng dụng Spring AI.
2. Giải thích vì sao dữ liệu đánh giá, rubric, metadata phiên bản và quy ước thu thập telemetry cần được thiết kế sớm.
3. Phân biệt đánh giá offline, kiểm thử tích hợp, kiểm thử trước phát hành và đánh giá/lấy mẫu trong production.
4. Thiết lập các cổng chất lượng cho thay đổi prompt, model, RAG pipeline và tool calling.
5. Liên kết một lần evaluation thất bại với traces, logs và metrics để xác định nguyên nhân.
6. Đề xuất cách phát hành an toàn, theo dõi hồi quy, xử lý sự cố và bổ sung bộ dữ liệu đánh giá để tránh lỗi tái diễn.

## 2. Vòng đời ứng dụng AI là một chuỗi quyết định có phản hồi

Với ứng dụng truyền thống, phiên bản mới thường được kiểm tra bằng unit test, integration test, tải thử và theo dõi lỗi. Ứng dụng có LLM cần thêm lớp kiểm tra *hành vi và ngữ nghĩa*, bởi một lời gọi thành công về mặt kỹ thuật không đảm bảo model hiểu đúng dữ liệu hay làm đúng nhiệm vụ.

Một vòng đời thực tế có thể mô tả như sau:

~~~mermaid
flowchart TD
    A["1. Yêu cầu và rủi ro<br/>chọn tiêu chí chất lượng"] --> B["2. Dữ liệu và thiết kế<br/>dataset, nguồn, baseline"]
    B --> C["3. Phát triển<br/>prompt / model / RAG / tool"]
    C --> D["4. Đánh giá và kiểm thử<br/>offline eval + integration"]
    D --> E{"Đủ điều kiện<br/>phát hành?"}
    E -- "Chưa" --> C
    E -- "Đạt" --> F["5. Triển khai có kiểm soát<br/>staging / canary"]
    F --> G["6. Vận hành production<br/>metrics / traces / feedback"]
    G --> H{"Có hồi quy<br/>hoặc nhu cầu mới?"}
    H -- "Có" --> I["7. Điều tra và học lại<br/>root cause + test case mới"]
    I --> B
    H -- "Không" --> G
~~~

**Evaluation** xuất hiện mạnh ở các quyết định “chất lượng có đạt không?”. **Observability** xuất hiện mạnh ở các câu hỏi “trong lần chạy thực tế, điều gì đã diễn ra?”. Tuy vậy, cả hai có mặt tại nhiều điểm trên sơ đồ: trace của một ca đánh giá offline có thể giúp sửa prompt; dữ liệu lỗi từ production có thể trở thành ca đánh giá hồi quy.

### 2.1. Bản đồ trách nhiệm theo giai đoạn

| Giai đoạn | Vai trò của Evaluation | Vai trò của Observability | Quyết định được hỗ trợ |
| --- | --- | --- | --- |
| Xác định yêu cầu | Mô tả thế nào là câu trả lời đạt, các lỗi không chấp nhận | Định nghĩa SLI/SLO, phạm vi cần quan sát | Hệ thống cần đạt tiêu chí gì? |
| Chuẩn bị dữ liệu | Tạo dataset, nhãn, nguồn chuẩn, tình huống âm | Ghi phiên bản tài liệu, pipeline, dữ liệu | Có đủ cơ sở để so sánh không? |
| Phát triển | So prompt/model/retrieval/tool theo rubric | Tracing thử nghiệm, đo token và latency | Thay đổi nào đang có ích? |
| Kiểm thử tích hợp | Chạy RAG/tool end-to-end và regression | Xác định span lỗi, timeout, retry, chi phí | Phiên bản đã đủ chắc chắn chưa? |
| Trước phát hành | Chạy bộ đánh giá cố định; phân tích hồi quy | Load test, đo độ trễ phân vị, kiểm tra cấu hình telemetry | Có đạt release gate không? |
| Phát hành từng phần | Đánh giá mẫu từ canary, so theo nhóm | Theo dõi lỗi, p95, throughput, tokens, cost | Mở rộng, giữ nguyên hay rollback? |
| Vận hành | Theo dõi ca thất bại, feedback, quality drift | Dashboard, cảnh báo, trace sự cố | Có vấn đề mới phát sinh không? |
| Cải tiến | Thêm ca lỗi vào bộ hồi quy, đánh giá lại | So trace và metric trước/sau thay đổi | Đã sửa nguyên nhân và tránh tái diễn chưa? |

Trong bảng, “đạt” luôn cần phạm vi rõ: tập ca nào, phiên bản dữ liệu nào, cách chấm nào, khoảng thời gian đo nào. Không nên dùng một kết quả trung bình để thay thế bằng chứng ở các nhóm rủi ro cao.

## 3. Giai đoạn 1 — Định nghĩa mục tiêu, rủi ro và chuẩn đạt

Nếu bắt đầu phát triển mà chưa xác định thế nào là đầu ra tốt, nhóm dễ tối ưu theo cảm giác: “câu trả lời nghe tự nhiên hơn” hoặc “ít token hơn”. Hai cải thiện đó có thể vô ích nếu ứng dụng vẫn trả lời sai chính sách.

Ở giai đoạn yêu cầu, hãy viết rõ:

- **Nhiệm vụ:** người dùng cần được trả lời câu hỏi, tóm tắt tài liệu, truy xuất dữ kiện hay thực hiện một hành động?
- **Nguồn sự thật:** tài liệu, database hay kết quả tool nào có thẩm quyền? Nguồn có thời hạn hiệu lực không?
- **Tiêu chí chất lượng:** relevance, tính đầy đủ, tính đúng thực tế, groundedness, trích dẫn, khả năng từ chối khi thiếu nguồn.
- **Tiêu chí hành vi:** cần gọi tool nào, ai được phép thực hiện, khi nào phải yêu cầu xác nhận, cách xử lý thất bại.
- **Tiêu chí vận hành:** availability, error rate, p95/p99 latency, time-to-first-token nếu streaming, token và chi phí.
- **Mức rủi ro:** lỗi nào chấp nhận được trong bản thử nghiệm, lỗi nào bắt buộc phải chặn phát hành.

Ví dụ giả định về chatbot hỏi đáp chính sách của dịch vụ *Sao Mai*:

| Yêu cầu | Tiêu chí kiểm chứng |
| --- | --- |
| Trả lời thời hạn hoàn phí gói Pro | Nêu **14 ngày kể từ ngày mua** theo nguồn `policy-v3` |
| Trích nguồn | Trích đúng đoạn chính sách có hiệu lực, không viện dẫn tài liệu khác |
| Không có quy định ngoại lệ | Thừa nhận thiếu dữ liệu, không tự bịa ngoại lệ |
| Đọc tình trạng đơn | Chỉ gọi `getOrderStatus` khi người dùng có quyền |
| Tạo yêu cầu hoàn phí | Backend xác thực quyền và điều kiện, có cơ chế chống thao tác lặp |
| Phản hồi đúng thời hạn | Đáp ứng SLO do nhóm xác định trên tải phù hợp |

Tất cả thông tin chính sách trong ví dụ đều **giả định phục vụ học tập**.

Một số yêu cầu phải kiểm bằng test xác định, chẳng hạn phân quyền và tính hợp lệ tham số. Các yêu cầu ngữ nghĩa nên chấm bằng dataset/rubric và có người đánh giá khi cần. Các yêu cầu vận hành cần thu tín hiệu qua thời gian. **Một kiểu kiểm thử không đủ bao phủ cả ba nhóm.**

### 3.1. Chọn chỉ số đúng với công việc

Với RAG, chỉ “câu trả lời liên quan” là chưa đủ. Cần phân biệt:

- **Retrieval hit@k / Recall@k:** hệ thống tìm thấy bằng chứng cần thiết hay không.
- **Answer relevance:** câu trả lời tập trung đúng câu hỏi hay không.
- **Groundedness (faithfulness):** phát biểu có được ngữ cảnh thực sự truy xuất hỗ trợ không.
- **Factual correctness:** phát biểu có đúng với nguồn chuẩn đã xác minh và đang có hiệu lực không.
- **Tool correctness:** có gọi đúng công cụ, đúng đối số, quyền hạn và thứ tự không.

Ví dụ: model trả lời “30 ngày” và trích một tài liệu cũ thật sự ghi “30 ngày”. Câu trả lời có thể *relevant* và *grounded* theo tài liệu truy xuất, nhưng **sai theo chính sách hiện hành 14 ngày**. Vì vậy, đánh giá ngữ cảnh chưa thể thay cho kiểm tra phiên bản nguồn.

## 4. Giai đoạn 2 — Xây dựng dữ liệu đánh giá và baseline

Một dataset tốt là nền tảng để nhận biết “phiên bản mới có tốt hơn bản cũ không?”. Nó không chỉ là danh sách câu hỏi và đáp án mẫu. Nó cần lưu **điều kiện được coi là đúng**, bằng chứng và phạm vi.

### 4.1. Thiết kế một ca đánh giá có thể lặp lại

Ví dụ record dạng JSON:

~~~json
{
  "id": "POLICY-REFUND-001",
  "datasetVersion": "policy-eval-v1",
  "question": "Gói Pro được hoàn phí trong bao lâu?",
  "expectedFacts": ["14 ngày kể từ ngày mua"],
  "forbiddenClaims": ["30 ngày", "hoàn phí vô điều kiện"],
  "referenceDocumentIds": ["policy-v3#refund-pro"],
  "expectedRetrievalIds": ["policy-v3#refund-pro"],
  "expectedBehavior": "Trả lời đúng thời hạn và dẫn nguồn",
  "tags": ["rag", "vi", "factual", "normal"],
  "sourceValidatedAt": "2026-05-18"
}
~~~

Bộ dữ liệu nên có thêm:

1. Câu hỏi thường gặp và nhiều cách diễn đạt cùng ý.
2. Câu đa bước hoặc chứa nhiều điều kiện nghiệp vụ.
3. Câu có thông tin gần giống dễ nhầm, tài liệu cũ và tài liệu mới.
4. Câu không có đủ tài liệu, cần thừa nhận giới hạn thay vì đoán.
5. Câu liên quan quyền truy cập hoặc tool không được phép thực thi.
6. Câu mà tool trả về timeout, lỗi xác thực, dữ liệu không tồn tại.
7. Câu có đầu vào chứa chỉ dẫn không đáng tin trong tài liệu retrieved (để kiểm tra cách ứng dụng xử lý nội dung gây nhiễu).

Đánh giá theo nhóm tag giúp thấy lỗi bị che bởi điểm trung bình. Một bộ 100 câu đạt 95 câu chưa nói được nhiều nếu cả 5 câu trượt đều thuộc tình huống trả lời “không có nguồn”, vốn là nhóm quan trọng để tránh hallucination.

### 4.2. Tách bộ phát triển và bộ kiểm tra độc lập

Nếu lặp đi lặp lại việc chỉnh prompt để qua cùng 20 câu và luôn dùng 20 câu đó để công bố chất lượng, kết quả dễ bị **overfit** bộ câu hỏi. Có thể tổ chức:

- **Development set:** dùng thường xuyên khi thử prompt, model, `top-k` và cách chia tài liệu.
- **Regression set:** các lỗi đã gặp, được chạy lại sau mỗi thay đổi.
- **Held-out set:** tập ca dành cho đánh giá độc lập trước phát hành, hạn chế điều chỉnh trực tiếp theo từng đáp án.

Việc tách nên tránh các ca gần như trùng nhau xuất hiện đồng thời ở development và held-out set. Với nội dung thay đổi theo thời gian, cần cập nhật nhãn và phiên bản nguồn theo quy trình được phê duyệt, không coi đáp án cũ là chân lý vĩnh viễn.

### 4.3. Baseline là mốc kỹ thuật và chất lượng

Baseline không chỉ là “prompt đầu tiên”. Một mốc so sánh đủ tin cậy nên ghi:

~~~yaml
runId: baseline-rag-v1-2026-05-18
datasetVersion: policy-eval-v1
corpusVersion: policy-v3
indexVersion: vector-index-v1
promptVersion: answer-prompt-v2
model: model-baseline
embeddingVersion: embeddings-v1
pipelineVersion: rag-v1
retrievalTopK: 3
evaluatorVersion: judge-rubric-v1
executionEnvironment: staging
~~~

Những giá trị chỉ để minh họa cấu trúc báo cáo; tên model và phiên bản phải lấy từ hệ thống thực. Khi so sánh hai lần chạy, cần biết yếu tố nào cố định, yếu tố nào thay đổi. Đặc biệt, nếu đổi đồng thời evaluator và prompt, điểm số thay đổi có thể do cách chấm chứ chưa chắc do ứng dụng tốt hơn.

## 5. Giai đoạn 3 — Phát triển và thử nghiệm có đo lường

Đây là lúc triển khai `ChatClient`, `Advisors`, `ChatModel`, `VectorStore`, tools và phần tích hợp nghiệp vụ. Evaluation giúp chọn cấu hình; Observability giúp nhìn đường đi của từng lần gọi.

### 5.1. Đánh giá từng tầng trước khi đánh giá end-to-end

Có thể chia một pipeline RAG thành các phần:

~~~mermaid
flowchart LR
    U["User query"] --> P["Query processing"]
    P --> R["Retrieval / VectorStore"]
    R --> C["Context assembly"]
    C --> M["ChatModel"]
    M --> O["Answer + citations"]

    R -.-> ER["Retrieval evaluation"]
    O -.-> EA["Answer evaluation"]
    P -.-> TR["Trace và metrics"]
    R -.-> TR
    M -.-> TR
~~~

- Với **retrieval**, kiểm tra các nguồn có nhãn đã nằm trong `top-k` chưa, có bị bộ lọc quyền truy cập loại sai không, và có đưa tài liệu lỗi thời vào context không.
- Với **generation**, kiểm tra model đã sử dụng context ra sao, có thêm chi tiết không có bằng chứng hay không, có trả lời đầy đủ và trích nguồn đúng không.
- Với **điều phối**, xác nhận advisor và công cụ được gọi đúng trình tự, đúng dữ liệu và quyền hạn.

Nếu Recall@5 giảm sau khi thay embedding, cần điều tra retrieval. Nếu Recall@5 vẫn tốt nhưng groundedness giảm sau khi sửa prompt, có lý do để tập trung vào generation. Đây là **giả thuyết ưu tiên**, cần kiểm chứng bằng case và traces.

### 5.2. Tối ưu bằng một thay đổi có chủ đích

Ví dụ muốn cải thiện việc tìm tài liệu:

1. Chạy baseline với `top-k=3`.
2. Giữ nguyên dataset, corpus, embedding, model và rubric; chỉ thử `top-k=5`.
3. So `hit@k`, `Recall@k`, groundedness và factual correctness.
4. Quan sát input tokens, độ trễ truy xuất, độ trễ model và chi phí.
5. Xem từng ca cải thiện và hồi quy để quyết định có giữ cấu hình mới không.

Một thay đổi tăng Recall@k có thể làm context dài và nhiễu hơn. Vì vậy cần đo **chất lượng câu trả lời cuối**, không chỉ chất lượng retrieval.

### 5.3. Tổ chức đánh giá bằng Spring AI

Spring AI hỗ trợ khái niệm `Evaluator`, `EvaluationRequest`, `EvaluationResponse` và những evaluator phục vụ kiểm tra như `RelevancyEvaluator`, `FactCheckingEvaluator` (API cụ thể tùy phiên bản Spring AI). Luồng đánh giá ý tưởng:

~~~text
For each evaluation case:
    1. Đưa câu hỏi vào ứng dụng Spring AI
    2. Thu đúng các Document được retrieval trả về
    3. Thu answer thực tế và thông tin tool call
    4. Chạy kiểm tra xác định: schema, permission, tool args, source IDs
    5. Chạy evaluator: relevance, groundedness theo rubric
    6. So với facts được con người xác minh nếu cần fact correctness
    7. Lưu điểm, feedback, configVersion, traceId
Aggregate:
    - pass rate theo từng metric và từng nhóm câu hỏi
    - case mới thất bại, case đã được sửa
    - chi phí, tokens, latency
~~~

**Không truyền đáp án chuẩn vào trường tài liệu truy xuất thực tế**: làm như vậy sẽ che giấu lỗi retrieval. Giữ hai nguồn tách biệt: `retrievedDocuments` để chấm groundedness trên điều kiện thật và `referenceDocuments` để đối chiếu đúng với nguồn sự thật.

Các evaluator dùng LLM phải được kiểm soát sai số. Một model chấm có thể thiên lệch theo cách diễn đạt, lặp lại sai lầm của model trả lời, hoặc dao động giữa các lần chạy. Vì vậy, cần rubric rõ và một tập được chuyên gia gắn nhãn để kiểm tra sự nhất quán.

## 6. Giai đoạn 4 — Kiểm thử tích hợp và chuẩn bị phát hành

Tại bước này, mục tiêu không còn là “một prompt có vẻ tốt hơn” mà là “một phiên bản hệ thống có thể hoạt động đúng và đáp ứng các tiêu chí đã thỏa thuận”.

### 6.1. Ba nhóm kiểm tra trước phát hành

| Nhóm | Ví dụ | Vì sao cần tách |
| --- | --- | --- |
| **Software correctness** | Unit/integration/contract test, phân quyền, schema tool, retry/idempotency | LLM judge không chứng minh được tính an toàn của giao dịch |
| **Answer quality** | Dataset regression, relevance, factual correctness, groundedness, đúng trích dẫn | Test HTTP và kiểm tra exception không phát hiện thông tin bịa |
| **Operational health** | Load test, latency phân vị, error rate, token, cost | Một câu trả lời đúng vẫn có thể quá chậm hoặc quá đắt |

Chẳng hạn, tool `refundOrder` thực hiện hành động có tác dụng phụ. Cần kiểm thử quyền và tính idempotent của backend bằng test xác định; không giao việc bảo vệ giao dịch chỉ cho prompt “không được gọi nếu thiếu quyền”.

### 6.2. Release gate dựa trên rủi ro

Đặt ngưỡng **trước khi thấy kết quả candidate**. Ví dụ hoàn toàn giả định:

~~~yaml
releaseGates:
  software:
    authorizationTests: "must-pass"
    paymentToolContractTests: "must-pass"
    integrationTests: "must-pass"
  aiQuality:
    factualCorrectnessPassRate: ">= 0.98"
    groundednessPassRate: ">= 0.95"
    criticalAbstentionCases: "must-pass"
    noNewCriticalRegressions: true
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
    estimatedCostUsdPerRequest: "<= 0.01"
~~~

Những con số trên dùng để mô tả **cách đặt cổng**. Dự án thật cần căn cứ vào nghiệp vụ, mức rủi ro, độ tin cậy của dataset và điều kiện tải. Không phải ứng dụng nào cũng có cùng ngưỡng.

Một candidate không nên được “cứu” bằng điểm tổng: đạt relevance 99% **không bù được** một lỗi phân quyền cho phép gọi tool hoàn phí trái phép.

### 6.3. Trường hợp không có câu trả lời

Khi service timeout hoặc model trả lỗi, không thể bỏ các request đó khỏi mọi phép tính để làm đẹp quality pass rate. Có thể lập báo cáo riêng:

- **Technical completion rate:** tỷ lệ yêu cầu xử lý thành công về kỹ thuật.
- **Quality among completed responses:** chất lượng của những câu đã được tạo ra và chấm.
- **End-to-end task success:** tỷ lệ toàn bộ yêu cầu có được kết quả đúng trong giới hạn thời gian.

Phải hiển thị mẫu số của mỗi chỉ số. Nếu 80/100 request hoàn tất và 76/80 câu được chấm đạt, không nên chỉ công bố “quality đạt 95%” rồi làm người đọc hiểu rằng 95/100 yêu cầu người dùng được phục vụ tốt.

### 6.4. Kiểm tra độ tin cậy thống kê

Một bộ 20 câu với 19 câu đạt cho tỷ lệ 95%, nhưng một câu sai mới đã làm thay đổi tỷ lệ 5 điểm phần trăm. Cần ghi số mẫu, phân bố tag, độ tin cậy nhãn và xem xét khoảng bất định khi ra quyết định quan trọng.

Với đầu ra không xác định hoàn toàn, có thể chạy lặp một số ca khó, giữ cấu hình model và judge ổn định trong mức cho phép, đồng thời lưu mọi lần chạy thay vì chỉ chọn lần có kết quả tốt.

## 7. Giai đoạn 5 — Triển khai có kiểm soát: staging, canary, rollback

Đạt điểm offline chưa có nghĩa đã biết ứng dụng sẽ hoạt động ra sao với phân bố câu hỏi và tải thực tế. Trước khi mở rộng traffic, cần kiểm tra điều kiện production gần nhất có thể.

Các bước triển khai có kiểm soát thường gồm:

1. **Staging:** kiểm tra cấu hình thực, kết nối VectorStore, quyền tool, tracing và metrics; chạy smoke test với dữ liệu kiểm thử an toàn.
2. **Canary hoặc rollout theo tỷ lệ:** cho một phần lưu lượng đi vào phiên bản mới có gắn `releaseVersion` và theo dõi riêng.
3. **So sánh trên nhóm tương thích:** cùng loại request, tải, khung thời gian và quy tắc chọn mẫu để tránh kết luận sai.
4. **Mở rộng hoặc rollback:** thực hiện theo điều kiện đã xác định, ưu tiên chặn sự cố phân quyền và lỗi nghiêm trọng.
5. **Ghi lại quyết định:** bằng chứng nào cho phép mở rộng, phiên bản nào được phục hồi nếu có vấn đề.

### 7.1. Vì sao cần cả evaluation và observability trong canary?

Evaluation offline có bộ nhãn tốt nhưng thiếu một số kiểu câu người dùng mới. Observability phát hiện điều kiện vận hành lạ nhưng không tự biết model trả lời đúng hay sai. Vì vậy:

- **Quan sát kỹ thuật:** error rate, timeout, p95/p99 latency, rate limit, request và token usage, số lần gọi tool.
- **Kiểm tra chất lượng được lấy mẫu:** phản hồi người dùng, ca được chuyên gia xem, evaluator chạy trên một mẫu phù hợp (có xử lý dữ liệu riêng tư).
- **Kiểm tra rủi ro:** lệnh tool bị từ chối, truy cập tài liệu sai quyền, nội dung không có nguồn, hành động không được xác nhận.
- **So theo phiên bản:** dùng metadata phiên bản trong phạm vi có thể thu thập an toàn.

Không nên mặc định canary “ổn” chỉ vì không có lỗi HTTP. Phải có cách phát hiện quality regression, dù tín hiệu chất lượng thường đến chậm hơn metrics vận hành.

### 7.2. Guardrail khác với quan sát

Chặn thực thi tool không hợp lệ bằng phân quyền backend là **biện pháp bảo vệ trong hệ thống**. Theo dõi số lần chặn qua metric là **observability**. Đánh giá chatbot có cố tình yêu cầu hoặc tìm cách dùng sai tool trong tập ca thử nghiệm là **evaluation**. Ba chức năng liên kết nhưng không hoán đổi cho nhau.

## 8. Giai đoạn 6 — Quan sát production bằng metrics, traces và logs

Khi ứng dụng đã hoạt động, Observability chuyển từ công cụ gỡ lỗi sang hệ thống phát hiện xu hướng và sự cố. Spring AI tích hợp với cơ chế observation của hệ sinh thái Spring và Micrometer cho các thành phần như `ChatClient`, `ChatModel`, `VectorStore`, `Advisor` và lời gọi tool, tùy vào phiên bản và khả năng của provider.

### 8.1. Dấu vết của một request RAG có tool

~~~text
HTTP /ask
└── ChatClient
    ├── Advisor: chọn context
    │   └── VectorStore: retrieval
    ├── ChatModel: tạo response hoặc yêu cầu tool
    ├── Tool execution (khi có)
    └── ChatModel: tổng hợp kết quả tool (khi có)
~~~

Một trace có thể cho thấy request chậm ở truy xuất, gọi model hay tool. Các span có thể lồng nhau hoặc chạy song song; phải đọc quan hệ và mốc thời gian, không cộng tùy tiện tất cả duration.

### 8.2. Ba loại dữ liệu phục vụ ba loại câu hỏi

| Nguồn dữ liệu | Thông tin trả lời tốt | Không thể tự kết luận |
| --- | --- | --- |
| **Metrics** | p95 latency tăng chưa? Tokens/request thay đổi thế nào? Lỗi tool nào tăng? | Câu trả lời có đúng chính sách không |
| **Traces** | Request lỗi tại đoạn nào? Có retry? Context được lấy ở bước nào? | Một khẳng định có đúng sự thật không |
| **Logs/events** | Lỗi nào phát sinh? Mã lỗi nào? Thời điểm nào? | Tỷ lệ pass chất lượng trên toàn bộ lưu lượng |

Các metric hoạt động thường cần gồm throughput, error rate, latency (p50/p95/p99 khi có phân bố), token usage, mức chi phí và số lần retry. Với streaming, có thể đo thêm **TTFT (time to first token)**; tổng thời gian phản hồi không thay thế được TTFT.

### 8.3. Cấu hình cơ bản minh họa

Một ứng dụng Spring Boot có thể dùng Actuator và các thành phần Micrometer/OTel phù hợp để xuất dữ liệu quan sát. Ví dụ phần cấu hình an toàn, ở mức minh họa:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.1
~~~

Để có `/actuator/prometheus` cần thêm registry Prometheus tương thích và bật endpoint. Tracing cần thêm các dependency/collector/exporter tương ứng. Cách cấu hình nội dung prompt/completion hoặc tool invocation phụ thuộc phiên bản Spring AI; nên **giữ chế độ không thu nội dung nhạy cảm theo mặc định**, chỉ bật để điều tra khi có kiểm soát.

Khi xây dựng dashboard, ưu tiên tag có cardinality hữu hạn như `environment`, `releaseVersion`, `modelFamily`, `operation` và `status` (nếu đã có chính sách đặt tag). Không gắn nguyên văn prompt, user ID hoặc tài liệu nhạy cảm làm nhãn metric. Với trace và log chi tiết, áp dụng phân quyền, ẩn dữ liệu, giới hạn thời gian lưu và chính sách lấy mẫu.

### 8.4. SLI, SLO và cảnh báo

Ví dụ định nghĩa SLI vận hành:

\[
\text{Technical Success Rate}
=
\frac{\text{Số request thành công về mặt kỹ thuật}}
{\text{Tổng request hợp lệ trong phạm vi đo}}
\]

SLO có thể là “99% request tương tác hoàn thành trong 3 giây tại tải quy định”. Đây chỉ là ví dụ; cần xác định cách xử lý request streaming, lỗi client, yêu cầu bị hủy và khoảng thời gian đo.

Không tạo cảnh báo chất lượng chỉ bằng ngưỡng latency. Có thể bổ sung **quality signal** như tỷ lệ thiếu trích dẫn, tỷ lệ fail của evaluator trên mẫu được chấm, số ca được người dùng báo sai, hoặc tần suất từ chối quá mức. Các tín hiệu này có sai số và lệch mẫu; cần người đánh giá xác nhận trước khi kết luận nhiều trường hợp nghiêm trọng.

## 9. Giai đoạn 7 — Điều tra suy giảm chất lượng và sự cố

Sau khi phát hành phiên bản mới, tỷ lệ câu trả lời có căn cứ giảm. Đây là lúc hai luồng thông tin cần ghép lại.

Một quy trình điều tra thực dụng:

1. **Chứng minh có thay đổi:** so pass rate theo nhóm trên cùng rubric, số mẫu, phiên bản evaluator; kiểm tra thời điểm và quy mô suy giảm.
2. **Khoanh vùng phiên bản:** đối chiếu prompt/model/pipeline/corpus/index và thời điểm triển khai.
3. **Tìm những ca thất bại tiêu biểu:** lưu case ID, nguồn cần tìm, nguồn đã tìm, câu trả lời và trace ID trong hệ thống kiểm soát quyền.
4. **Đi theo traces:** xem truy xuất, model, tools, retry, timeout, thời lượng và các bất thường.
5. **Đặt giả thuyết có thể kiểm chứng:** lỗi từ nguồn, retrieval, prompt, model, quyền tool hay điều kiện vận hành.
6. **Thử sửa trong môi trường kiểm soát:** thay một yếu tố, chạy lại regression và đo latency/cost.
7. **Theo dõi sau sửa:** xác nhận chất lượng hồi phục mà không tạo lỗi mới ở nhóm khác.

### 9.1. Ma trận chẩn đoán theo bằng chứng

| Triệu chứng | Bằng chứng cần đối chiếu | Hướng điều tra |
| --- | --- | --- |
| Factual correctness giảm, retrieval hit@k giảm | Document IDs, corpus/index version, truy vấn VectorStore | Tài liệu, chunking, embedding, filter, `top-k` |
| Groundedness giảm, retrieval vẫn đạt | Prompt đã ghép, context thực tế, model version | Cách model diễn giải và dùng nguồn |
| Trả lời có trích dẫn nhưng sai chính sách hiện hành | Hiệu lực và phiên bản tài liệu | Quy trình cập nhật dữ liệu, tài liệu hết hạn |
| Quality ổn nhưng p95 tăng | Trace span VectorStore/model/tool, retry, token | Nút nghẽn tài nguyên hoặc prompt quá dài |
| Token tăng mạnh, cost tăng | Input/context length, số lượt gọi model/tool | Context dư, retry, vòng gọi tool, chiến lược truy xuất |
| Tool trả lỗi, model vẫn nói thành công | Tool status, response mapping, phần mềm kiểm tra hậu điều kiện | Error handling, orchestration, quy tắc nghiệp vụ |
| Lỗi chỉ xuất hiện trong một nhóm người dùng | Thống kê theo phân khúc phù hợp, quyền truy cập, nguồn tài liệu | Lệch dataset, bộ lọc, quyền hoặc dữ liệu đặc thù |

**Một liên hệ thời gian không tự chứng minh nguyên nhân.** Ví dụ, cùng lúc đổi prompt và model không thể chỉ từ việc tỷ lệ fail tăng mà biết yếu tố nào gây lỗi. Cần thử từng thay đổi hoặc có thiết kế so sánh đủ kiểm soát.

### 9.2. Ví dụ điều tra request sai có trace

Giả sử case `POLICY-REFUND-001` trước đó trả lời đúng, nay nói “30 ngày”. Trace cho thấy `VectorStore` trả hai đoạn: một đoạn thuộc `policy-v2` (cũ, 30 ngày) và một đoạn thuộc `policy-v3` (14 ngày). Nếu prompt đặt tài liệu cũ lên trước và không nêu cách chọn phiên bản, model có thể dựa vào nguồn sai.

Nhóm cần:

- Kiểm tra quy tắc chọn tài liệu đang có hiệu lực và metadata index.
- Thêm bài kiểm tra chỉ chấp nhận nguồn phiên bản hiện hành trong ngữ cảnh thuộc phạm vi yêu cầu.
- Kiểm tra prompt có hướng dẫn xử lý nguồn mâu thuẫn.
- Chạy lại dataset, đo cả chất lượng lẫn độ trễ nếu bổ sung bước lọc/rerank.

Observability giúp thấy **đã lấy hai nguồn nào**, Evaluation xác nhận **hành vi sau sửa có đạt không**.

## 10. Giai đoạn 8 — Phản hồi production quay trở lại dataset

Production cung cấp những tình huống mà nhóm không dự đoán hết: câu hỏi viết tắt, lỗi chính tả, ngôn ngữ trộn, tài liệu không rõ, những trường hợp người dùng cần xác nhận trước khi hành động.

Mỗi ca chất lượng kém có giá trị học tập nếu được biến thành phép kiểm tái sử dụng:

~~~mermaid
flowchart LR
    P["Production sample<br/>feedback / alert"] --> T["Phân loại lỗi"]
    T --> V["Chuyên gia xác minh<br/>nguồn và kỳ vọng"]
    V --> D["Cập nhật dataset<br/>và rubric"]
    D --> E["Chạy regression<br/>trên candidate"]
    E --> R["Rollout có đo lường"]
    R --> P
~~~

Quy trình nên có ranh giới dữ liệu:

1. Lấy mẫu có tiêu chí, hạn chế dữ liệu nhạy cảm.
2. Xác minh sự cố là lỗi thật, phân loại theo retrieval/generation/tool/operations.
3. Chuẩn hóa câu hỏi, loại bỏ thông tin định danh và dữ liệu mật.
4. Gắn nguồn tham chiếu, phiên bản, tiêu chí đạt và lý do từ chối nếu cần.
5. Đưa vào regression set, đánh dấu ngày nguồn có hiệu lực.
6. Chạy lại với các thay đổi tương lai để tránh hồi quy.

Không nên coi phản hồi “không thích” của người dùng là nhãn sai tuyệt đối: người dùng có thể không hài lòng vì câu trả lời từ chối yêu cầu không phù hợp, trong khi hành vi đó thực sự đúng. Các ca quan trọng phải được rà soát.

### 10.1. Khi nào cần đánh giá lại dù chưa đổi code?

Chất lượng có thể thay đổi mà không cần triển khai code mới:

- Kho tài liệu được bổ sung hoặc bị xóa; có thay đổi hiệu lực chính sách.
- Index/vector store được rebuild, bộ lọc dữ liệu thay đổi.
- Nhà cung cấp thay phiên bản model hoặc thay đổi giới hạn/rate limit.
- Phân bố câu hỏi của người dùng thay đổi.
- Tool backend có schema/hành vi mới.
- Giá token hoặc cấu trúc chi phí thay đổi.

Vì vậy, cần đánh giá theo **phiên bản dữ liệu, prompt, model, công cụ và pipeline**, đồng thời đo lại chất lượng theo nhịp phù hợp với tần suất thay đổi và mức rủi ro nghiệp vụ.

## 11. Ví dụ xuyên suốt: thay đổi RAG từ v1 sang v2

Nhóm muốn cải thiện khả năng tìm thấy chính sách trong chatbot *Sao Mai*. Phiên bản `rag-v1` dùng `top-k=3`. Candidate `rag-v2` dùng `top-k=5`, giữ các thành phần còn lại tương đương trong lần thử đầu.

Dataset có 100 ca (đã gắn nhãn) gồm: 60 ca thông thường, 20 ca điều kiện nhiều bước, 10 ca thiếu nguồn và 10 ca cố tình gây nhầm tài liệu phiên bản.

Các số liệu dưới đây **giả định** để minh họa cách ra quyết định:

| Chỉ số trên cùng dataset | rag-v1 | rag-v2 | Diễn giải |
| --- | ---: | ---: | --- |
| Retrieval hit@5 | 87% | 94% | Tìm thấy nguồn chuẩn thường xuyên hơn |
| Answer relevance đạt | 92% | 95% | Cải thiện khả năng trả lời đúng trọng tâm |
| Groundedness đạt | 96% | 94% | Có tín hiệu giảm chất lượng dựa trên nguồn |
| Factual correctness đạt | 95% | 93% | Có ca trả lời sai sự thật/quy định |
| p95 end-to-end latency | 2,1 giây | 3,0 giây | Chậm hơn |
| Input tokens trung bình | 1.200 | 2.100 | Prompt dài hơn |
| Chi phí model ước tính/request | 0,004 USD | 0,006 USD | Tăng 50% |

**Không thể chỉ tuyên bố v2 “tốt hơn” vì hit@5 và relevance tăng.** Cần xem 2 nhóm ca factual correctness và groundedness giảm, đồng thời kiểm tra ngưỡng latency/cost.

### 11.1. Hành động của từng giai đoạn

- **Thiết kế:** xác định mục tiêu chính là tìm đúng nguồn, nhưng không chấp nhận tăng lỗi về thời hạn chính sách.
- **Thử nghiệm offline:** so từng case, phát hiện 4 ca bị thêm tài liệu cũ vào context và model chọn nhầm.
- **Quan sát:** trace và usage cho thấy số đoạn truy xuất và token tăng, ChatModel mất thêm thời gian.
- **Khắc phục:** thử bộ lọc phiên bản nguồn hiện hành trước retrieval hoặc rerank; không tăng context vô điều kiện.
- **Regression:** chạy lại cả 100 ca và các trường hợp mới phát hiện.
- **Phát hành:** chỉ mở rộng canary nếu chất lượng, lỗi nghiệp vụ, latency/cost đạt tiêu chí đã thỏa thuận.

Đây là một ví dụ về **trade-off**: cải thiện một chỉ số thành phần có thể làm xấu kết quả cuối cùng. Lý do cần vòng đời đo lường là để đánh giá ảnh hưởng thực tế, không tối ưu chỉ số đơn lẻ.

## 12. Thiết kế một bản ghi chung để liên hệ Evaluation với Observability

Có thể lưu mỗi kết quả đánh giá dưới dạng record có ID lần chạy và tham chiếu trace, thay vì chỉ lưu một bảng điểm tổng:

~~~json
{
  "runId": "eval-rag-v2-2026-05-18",
  "caseId": "POLICY-REFUND-001",
  "datasetVersion": "policy-eval-v1",
  "promptVersion": "answer-prompt-v2",
  "modelVersion": "model-baseline",
  "pipelineVersion": "rag-v2",
  "corpusVersion": "policy-v3",
  "retrievedDocumentIds": ["policy-v2#refund-pro", "policy-v3#refund-pro"],
  "evaluation": {
    "relevancePass": true,
    "groundednessPass": false,
    "factualCorrectnessPass": false,
    "reason": "Chọn chính sách cũ và trả lời sai thời hạn"
  },
  "operations": {
    "technicalSuccess": true,
    "totalLatencyMs": 1710,
    "inputTokens": 1950,
    "outputTokens": 162,
    "estimatedCostUsd": 0.006
  },
  "traceId": "example-trace-id"
}
~~~

Cấu trúc trên là **đề xuất record do nhóm tự định nghĩa**, không phải định dạng API mà Spring AI tự sinh. Các con số đều minh họa. Trong hệ thống thật, tránh lưu câu hỏi nguyên văn hoặc nội dung riêng tư nếu không cần. Trace ID chỉ nên cho phép người có quyền tra cứu.

### 12.1. Các chỉ số cần báo cáo cùng nhau

Nên trình bày theo **ba lớp**:

- **Chất lượng:** số ca, pass rate từng rubric, phân nhóm lỗi, retrieval metrics, factual correctness, ca hồi quy nghiêm trọng.
- **Thực thi:** tỷ lệ thành công kỹ thuật, lỗi theo bước, kết quả tool, p50/p95/p99, TTFT nếu dùng streaming.
- **Nguồn lực:** input/output tokens, số lượt gọi model, chi phí ước tính/request và chi phí trên một nhiệm vụ thành công.

Với các phép đo tỷ lệ, ghi rõ mẫu số. Với latency, ghi phương pháp đo và khoảng thời gian. Với chi phí, tách giá model và chi phí khác; phí thực có thể phụ thuộc cache, embedding, tool và hạ tầng.

## 13. Tổ chức CI/CD và lịch đánh giá

Không phải mọi kiểm tra đều cần chạy sau từng commit với cùng cường độ. Chọn mức phù hợp để có phản hồi nhanh và vẫn bắt được lỗi quan trọng:

| Sự kiện | Kiểm tra phù hợp | Mục đích |
| --- | --- | --- |
| Mỗi thay đổi mã | Unit/contract tests, lint, một tập smoke evaluation nhỏ | Phát hiện lỗi đơn giản sớm |
| Đổi prompt/model/top-k | Regression dataset, so với baseline, đo token/latency | Xác định chất lượng và chi phí bị ảnh hưởng |
| Đổi dữ liệu/index | Retrieval evaluation, nhãn tài liệu, kiểm tra quyền | Phát hiện thiếu hoặc sai nguồn |
| Trước phát hành | Full evaluation, ca rủi ro cao, integration/load tests | Đạt release gates |
| Trong canary | Metrics, tracing, mẫu đánh giá chất lượng, cảnh báo | Quyết định mở rộng hay rollback |
| Định kỳ trên production | Sampling/human review, quality trends, kiểm tra nguồn mới | Phát hiện drift và tình huống mới |
| Sau sự cố | Root-cause analysis, thêm case hồi quy, chạy lại | Tránh lỗi tái diễn |

Một số phép đánh giá bằng LLM có chi phí và độ trễ đáng kể. Có thể tổ chức tầng **smoke nhỏ, regression vừa, full release**; tuy nhiên, các ca bắt buộc liên quan phân quyền hoặc hành động nguy hiểm phải được kiểm tra ở mức phù hợp trong mỗi lần phát hành.

### 13.1. Phân chia trách nhiệm trong nhóm

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| Product / nghiệp vụ | Xác định mức chất lượng chấp nhận, các trường hợp nghiêm trọng |
| Chuyên gia miền dữ liệu | Xác nhận đáp án chuẩn, hiệu lực nguồn, rubric |
| Lập trình viên Spring AI | Viết pipeline, tests, tích hợp evaluator và tracing |
| QA / evaluation owner | Duy trì dataset, phân tích hồi quy và độ tin cậy của bộ chấm |
| Platform / SRE | Theo dõi SLO, metrics/traces, cảnh báo và rollback |
| Security / privacy | Quy tắc quyền tool, bảo vệ dữ liệu trong telemetry và tập đánh giá |

Trong nhóm nhỏ, một người có thể đảm nhiệm nhiều vai trò; trách nhiệm và tiêu chí kiểm chứng vẫn nên được thể hiện rõ.

## 14. Những sai lầm làm đứt vòng phản hồi

**Chỉ đánh giá một lần trước khi demo.** Sau khi dữ liệu hoặc prompt thay đổi, kết quả cũ không còn đại diện cho cấu hình mới. Cần chạy lại những ca liên quan và theo dõi regression.

**Chỉ quan sát lỗi HTTP hoặc CPU.** Chatbot có thể trả lời rất nhanh nhưng bịa thông tin. Observability cần kết hợp dữ liệu chất lượng có nhãn để thấy lỗi ngữ nghĩa.

**Không lưu phiên bản dữ liệu và evaluator.** Nếu điểm pass rate thay đổi mà không biết prompt, corpus hay rubric nào đã đổi, không thể so sánh có ý nghĩa.

**Lấy tài liệu chuẩn thay cho tài liệu truy xuất khi chấm groundedness.** Điều này làm mất bằng chứng retrieval failure, khiến hệ thống có vẻ tốt hơn thực tế.

**Chấm bằng LLM rồi coi điểm là sự thật tuyệt đối.** Model chấm cũng có sai số; phải có rubric, ca kiểm tra do con người xác minh và phân tích những trường hợp bất đồng.

**Trộn chất lượng với hiệu năng thành điểm trung bình.** Vi phạm phân quyền nghiêm trọng không thể được bù bằng một request nhanh hoặc một điểm relevance cao.

**Ghi mọi prompt, completion và tool arguments vào telemetry không kiểm soát.** Những dữ liệu này có thể chứa thông tin riêng tư và nhạy cảm; cần giới hạn thu thập, che dữ liệu và phân quyền.

**Bỏ qua các request thất bại khi tính kết quả.** Nếu chỉ chấm những câu trả lời hoàn tất, có thể che mất tình trạng timeout/lỗi của người dùng. Cần báo tỷ lệ hoàn tất kỹ thuật và chất lượng trên mẫu đã chấm, đồng thời đo thành công end-to-end khi cần.

**Đổi nhiều thành phần cùng lúc rồi kết luận một thành phần gây lỗi.** Cần lưu phiên bản và thử nghiệm có kiểm soát để phân biệt nguyên nhân.

## 15. Bài thực hành — Thiết kế vòng đời đánh giá cho một chatbot Spring AI

**Bối cảnh:** chatbot RAG giúp nhân viên tra cứu chính sách nội bộ; ngoài hỏi đáp, ứng dụng có tool chỉ đọc `getOrderStatus`. Mục tiêu là học cách gắn Evaluation và Observability vào từng giai đoạn, chưa cần hạ tầng sản xuất hoàn chỉnh.

### Phần A: Chuẩn bị

1. Viết ít nhất 15 case gồm câu thông thường, câu hỏi đa điều kiện, câu không có nguồn, câu có nguồn cũ và câu bắt buộc sử dụng tool.
2. Xác định nguồn/đáp án chuẩn và rubric: relevance, groundedness, factual correctness, đúng hành vi tool.
3. Đặt điều kiện vượt qua có thể đo được và lập baseline với `top-k=3`.
4. Ghi metadata của mỗi lần chạy: `runId`, dataset, corpus/index, prompt, model, pipeline và judge version.

### Phần B: Chạy thử và thu dấu vết

1. Chạy ứng dụng cho từng case; lưu câu trả lời, ID tài liệu được retrieval trả về và tên/kết quả tool nếu có.
2. Đánh giá từng case bằng quy tắc xác định và evaluator phù hợp; kiểm tra ngẫu nhiên một số case bằng tay.
3. Thu thời gian retrieval, thời gian model, tổng thời gian, số lần gọi tool và token usage nếu provider hỗ trợ.
4. Kết nối kết quả fail với trace ID nếu hạ tầng tracing đã có.

### Phần C: Gây thay đổi và giải thích

Thử tăng `top-k` từ 3 lên 5, giữ các thành phần còn lại và chạy lại. Báo cáo:

| Câu hỏi cần trả lời | Bằng chứng nên dùng |
| --- | --- |
| Nguồn cần thiết có được truy xuất thường xuyên hơn không? | Hit@k / Recall@k và ID tài liệu |
| Câu trả lời có chính xác hơn không? | Factual correctness, groundedness, ca pass/fail |
| Request chậm hơn ở bước nào? | Trace span retrieval/model; latency phân vị |
| Token/chi phí có tăng không? | Usage và mô hình giá tương ứng |
| Candidate có thể phát hành không? | Release gates và các ca hồi quy nghiêm trọng |

**Kết quả mong đợi:** một báo cáo so sánh baseline/candidate có lý do chọn hoặc từ chối phát hành, ghi rõ giới hạn phép đo và ít nhất một case được bổ sung vào regression set.

### Câu hỏi tự kiểm tra

1. Tại sao nên định nghĩa rubric và nguồn chuẩn trước khi chỉnh prompt?
2. Một canary đạt p95 dưới 2 giây nhưng tăng tỷ lệ trả lời sai. Nhóm nên xem các dữ liệu nào trước khi mở rộng?
3. Khi một lời gọi tool trả về lỗi 403 nhưng chatbot báo thành công, Evaluation và Observability giúp xử lý khác nhau thế nào?
4. Vì sao cần lưu phiên bản của bộ chấm và dataset bên cạnh phiên bản ứng dụng?
5. Khi policy database thay đổi mà code giữ nguyên, có cần chạy lại evaluation không? Vì sao?
6. Nếu chỉ 60/100 request hoàn thành và 57/60 câu trong số đó được chấm đạt, công bố “95% yêu cầu thành công” có chính xác không?

## 16. Kết luận

Vai trò cốt lõi của **Evaluation** là cung cấp bằng chứng định lượng và định tính về *chất lượng đầu ra và hành vi* của ứng dụng Spring AI trước và sau mỗi thay đổi. **Observability** cung cấp bằng chứng về *quá trình thực thi, trạng thái vận hành và mức sử dụng tài nguyên* để phát hiện xu hướng, khoanh vùng sự cố và giải thích tác động của thay đổi.

Khi được kết nối bằng dataset, rubric, metadata phiên bản và trace ID, hai hoạt động tạo ra vòng lặp cải tiến liên tục: **định nghĩa đúng → đo baseline → thay đổi có kiểm soát → kiểm thử → phát hành → quan sát → điều tra → bổ sung hồi quy**. Nhờ đó, quyết định đổi prompt, model hoặc pipeline dựa trên cả **chất lượng, độ trễ và chi phí**, thay vì chỉ dựa vào một vài câu trả lời ấn tượng trong bản demo.

### Tài liệu tham khảo

- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring Boot — Production-ready Features (Actuator)](https://docs.spring.io/spring-boot/reference/actuator/index.html)
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
