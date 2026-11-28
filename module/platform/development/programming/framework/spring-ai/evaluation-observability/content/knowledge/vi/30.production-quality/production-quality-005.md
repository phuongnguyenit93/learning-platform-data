# Chất lượng khi vận hành: Kết hợp đánh giá tự động với rà soát của con người

## 1. Vì sao cần kết hợp hai cách đánh giá?

Ứng dụng Spring AI có thể tạo ra hàng nghìn hoặc hàng triệu câu trả lời trong production. Chạy human review cho mọi interaction thường không khả thi về chi phí và thời gian. Ngược lại, chỉ dùng một LLM judge hoặc một bộ rule tự động có thể bỏ sót lỗi tinh vi, thiên lệch theo văn phong, hiểu sai kỳ vọng nghiệp vụ hoặc tự tin đưa ra verdict không có căn cứ.

Một hệ thống đánh giá đáng tin cậy cần phân công đúng vai trò:

- **Kiểm tra tự động** xử lý các điều kiện có thể xác minh bằng code, schema, source hoặc evaluator; sàng lọc số lượng lớn và tạo tín hiệu ưu tiên.
- **LLM evaluator** đánh giá những tiêu chí cần hiểu ngôn ngữ hoặc ngữ cảnh, ví dụ relevance, groundedness và completeness; kết quả phải được hiệu chuẩn trên task thực tế.
- **Con người** xác minh trường hợp mơ hồ, đánh giá tiêu chí phụ thuộc nghiệp vụ, kiểm tra lỗi evaluator và phân xử bất đồng.
- **Dataset và quy trình adjudication** biến các trường hợp đã được xác nhận thành chuẩn đánh giá có version, provenance và có thể chạy lại.

Đây là một vòng lặp bổ sung cho nhau. Human review giúp kiểm tra evaluator; evaluator giúp ưu tiên những case cần con người; deterministic checks cung cấp bằng chứng khách quan khi có thể. Không nên coi một điểm LLM judge hoặc một rating người dùng là ground truth tuyệt đối.

Bài học thuộc chương **Chất lượng khi vận hành** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

Sau bài học, bạn có thể:

- Phân biệt automated checks, LLM-as-a-judge, human review và adjudication.
- Xây dựng rubric có tiêu chí, thang điểm và ví dụ nhất quán.
- Thiết kế quy trình annotation, blind review, double annotation và xử lý bất đồng.
- Dùng RelevancyEvaluator và FactCheckingEvaluator trong Spring AI.
- Hiệu chuẩn evaluator bằng tập human-reviewed cases.
- Đo inter-annotator agreement, judge-human agreement và uncertainty.
- Chọn case cần human review theo risk, uncertainty và mức độ ảnh hưởng.
- Quản lý reviewer queue, workload, audit và quyền truy cập evidence.
- Chuyển kết quả đã xác minh thành evaluation dataset có provenance.
- Theo dõi chất lượng của evaluator và người đánh giá theo thời gian.

## 2. Bốn lớp đánh giá có vai trò khác nhau

Không phải mọi kiểm tra đều cần LLM, và không phải mọi quyết định đều nên giao cho con người.

| Lớp đánh giá | Ví dụ | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| Deterministic checks | JSON schema, citation ID tồn tại, tool status, exact match, policy rule | Kết quả tái lập, rẻ, dễ audit | Không hiểu đầy đủ ý nghĩa câu trả lời |
| LLM evaluator | Relevance, fact checking, completeness theo rubric | Mở rộng được, hiểu ngôn ngữ và context | Có thể sai, thiên lệch, thay đổi theo model/prompt |
| Human review | Đánh giá tính hữu ích, nuance nghiệp vụ, lỗi khó | Có phán đoán theo bối cảnh và có thể giải thích | Tốn thời gian, có bất đồng và fatigue |
| Adjudication | Reviewer cấp cao giải quyết bất đồng | Tạo nhãn cuối có kiểm soát | Cần quy trình, chuyên môn và audit |

### 2.1. Deterministic checks

Dùng code hoặc nguồn dữ liệu có thẩm quyền khi câu hỏi có thể kiểm tra một cách khách quan:

- Response có parse được theo JSON schema không?
- Citation ID có tồn tại trong tập retrieved documents không?
- Tool có trả status thành công không?
- Một trường bắt buộc có bị thiếu không?
- Output có vi phạm constraint như giới hạn số dòng hoặc format không?
- Một câu trả lời số học có khớp phép tính được thực thi không?
- Một claim có khớp record có version trong hệ thống nghiệp vụ không?

Ví dụ, nếu response trích dẫn document ID không nằm trong retrieval snapshot, có thể đánh dấu citation reference invalid bằng code. LLM judge không cần quyết định một ID có tồn tại hay không.

### 2.2. LLM evaluator

Dùng LLM evaluator cho những tiêu chí đòi hỏi hiểu ngữ nghĩa:

- Câu trả lời có giải quyết đúng intent không?
- Các khẳng định có được context hỗ trợ không?
- Câu trả lời có bỏ sót bước quan trọng không?
- Tool được chọn có phù hợp với yêu cầu không?
- Cách giải thích có rõ ràng với đối tượng người dùng không?

Evaluator nên trả verdict có cấu trúc, tiêu chí cụ thể và trạng thái không đủ bằng chứng. Không yêu cầu judge đoán một điểm tổng hợp duy nhất cho nhiều tiêu chí khác nhau.

### 2.3. Human review

Con người cần xem xét khi:

- Tác động sai sót cao.
- Evaluator không chắc chắn hoặc không có đủ evidence.
- Deterministic checks và LLM judge mâu thuẫn.
- User feedback và evaluator verdict không đồng thuận.
- Case thuộc task mới hoặc rubric chưa được hiệu chuẩn.
- Có nguy cơ bias, policy ambiguity hoặc lỗi nghiệp vụ tinh vi.
- Một thay đổi prompt/model làm quality score dịch chuyển bất thường.

Human review cũng cần rubric, hướng dẫn, calibration và audit. Con người không tự động đúng chỉ vì là người đánh giá.

### 2.4. Adjudication

Adjudication là bước xử lý bất đồng có quy tắc. Một adjudicator có chuyên môn xem evidence, rubric, các annotation độc lập và lý do bất đồng, sau đó ghi verdict cuối cùng hoặc đánh dấu case chưa thể kết luận.

Không nên chỉ lấy trung bình hai điểm trái ngược nếu hai reviewer đang hiểu khác nhau về tiêu chí. Cần xác định họ bất đồng vì thiếu evidence, rubric mơ hồ, chuyên môn khác nhau hay lỗi thực sự của evaluator.

## 3. Kiến trúc human–AI evaluation loop

Một pipeline thực tế có thể hoạt động như sau:

~~~mermaid
flowchart TD
    I["Production interaction"] --> D["Deterministic checks"]
    I --> L["LLM evaluator"]
    D --> R{"Rule result"}
    L --> V["Evaluator verdict + confidence/status"]
    R --> ROUTE["Review routing policy"]
    V --> ROUTE
    ROUTE -->|Routine / low risk| AUTO["Store automated result"]
    ROUTE -->|Borderline / disagreement / high risk| H["Human review queue"]
    H --> A["Independent annotation"]
    A --> AGREE{"Agreement sufficient?"}
    AGREE -->|Yes| FINAL["Final reviewed label"]
    AGREE -->|No| ADJ["Adjudication"]
    ADJ --> FINAL
    AUTO --> MON["Monitor evaluator quality"]
    FINAL --> MON
    FINAL --> DS["Versioned evaluation dataset"]
    DS --> CAL["Calibrate evaluator and rubric"]
    CAL --> L
~~~

Pipeline có thể tách thành ba luồng:

1. **Scoring:** deterministic checks và LLM evaluator chạy sau khi có response.
2. **Review:** policy quyết định case nào cần reviewer, bao nhiêu reviewer và có cần adjudication không.
3. **Learning:** nhãn cuối được dùng để hiệu chuẩn evaluator, cập nhật rubric và thêm regression cases.

### 3.1. Giữ các kết quả riêng biệt

Một interaction có thể có nhiều kết quả:

- deterministic result.
- LLM evaluator result.
- reviewer A annotation.
- reviewer B annotation.
- adjudicator verdict.
- user feedback.
- business outcome.

Lưu chúng thành các bản ghi riêng, cùng trỏ về interaction và evaluation case. Không ghi đè kết quả tự động bằng kết quả con người; cần giữ lịch sử để đo mức đồng thuận và phát hiện evaluator drift.

## 4. Xác định tiêu chí trước khi chọn evaluator

Câu hỏi “câu trả lời tốt không?” quá rộng để tạo annotation nhất quán. Cần chia thành các dimension có định nghĩa riêng.

| Dimension | Câu hỏi đánh giá | Evidence cần có |
| --- | --- | --- |
| Relevance | Câu trả lời có đáp ứng intent của câu hỏi không? | User input, conversation context, response |
| Factuality | Các claim có đúng theo nguồn có thẩm quyền không? | Retrieved documents hoặc authoritative source |
| Groundedness | Claim có được hỗ trợ bởi context đã cung cấp không? | Context snapshot, claim-to-source mapping |
| Completeness | Có thiếu bước hoặc điều kiện quan trọng không? | Task requirements, expected answer criteria |
| Citation quality | Citation có đúng, đủ và hỗ trợ claim không? | Citation references và document versions |
| Tool correctness | Tool được chọn và thực thi có phù hợp không? | Tool definitions, arguments summary, execution result |
| Safety/policy | Response có tuân thủ policy áp dụng không? | Policy version, input/output, review guidance |
| Clarity | Người dùng có thể hiểu và sử dụng câu trả lời không? | User persona, language, response |
| Task success | Công việc cuối cùng có hoàn tất đúng không? | Business outcome hoặc verified completion |

### 4.1. Relevance không đồng nghĩa factuality

Một câu trả lời có thể liên quan trực tiếp đến câu hỏi nhưng chứa thông tin sai. Ngược lại, câu trả lời có thể đúng về mặt facts nhưng không giải quyết đúng yêu cầu.

Ví dụ: người dùng hỏi “Đơn hàng của tôi đang ở đâu?”. Câu trả lời giải thích chính sách vận chuyển có thể đúng, nhưng không liên quan đến trạng thái đơn hàng cụ thể.

### 4.2. Groundedness không đồng nghĩa truthfulness toàn cục

Fact-checking dựa trên context trả lời câu hỏi “claim có được context này hỗ trợ không?”. Nếu context lỗi thời hoặc sai, một claim có thể được context hỗ trợ nhưng vẫn sai trong thế giới thực.

Vì vậy, cần ghi rõ source of truth, document version và thời điểm hiệu lực. Với thông tin nghiệp vụ, ưu tiên record có thẩm quyền hoặc API verification thay vì chỉ nhờ LLM judge.

### 4.3. Completeness phải gắn với task

Không chấm câu trả lời ngắn là incomplete chỉ vì nó ngắn. Rubric cần mô tả các thành phần bắt buộc của từng task family. Ví dụ hướng dẫn hoàn tiền có thể phải nêu điều kiện, thời hạn và bước tiếp theo; câu hỏi định nghĩa đơn giản có thể chỉ cần một câu.

## 5. Thiết kế rubric có thể áp dụng nhất quán

Rubric mô tả tiêu chí, thang điểm, evidence và cách xử lý trường hợp biên. Mỗi tiêu chí nên có:

- Tên và mục đích.
- Định nghĩa điều được đánh giá.
- Phạm vi evidence được phép dùng.
- Thang điểm và anchor cho từng mức.
- Ví dụ positive/negative/borderline.
- Quy tắc khi thiếu evidence.
- Các lỗi nghiêm trọng và điều kiện escalation.
- Version và ngày hiệu lực.

### 5.1. Ví dụ rubric relevance

| Điểm | Anchor | Diễn giải |
| ---: | --- | --- |
| 0 | Không trả lời intent | Trả lời chủ đề khác, bỏ qua yêu cầu chính |
| 1 | Chỉ liên quan một phần nhỏ | Có nhắc đúng chủ đề nhưng không giải quyết nhiệm vụ |
| 2 | Đáp ứng một phần | Trả lời phần chính nhưng bỏ sót điều kiện quan trọng |
| 3 | Đáp ứng tốt | Trả lời đúng intent, đủ các ý bắt buộc |
| 4 | Đáp ứng đầy đủ và có trọng tâm | Giải quyết rõ ràng, không thêm nội dung gây nhiễu |

### 5.2. Ví dụ rubric groundedness

| Điểm | Anchor |
| ---: | --- |
| 0 | Có claim chính không được hỗ trợ hoặc mâu thuẫn với evidence |
| 1 | Nhiều claim thiếu nguồn; một phần context bị diễn giải sai |
| 2 | Phần lớn claim được hỗ trợ nhưng còn một claim đáng kể chưa rõ |
| 3 | Các claim quan trọng được evidence hỗ trợ; không có mâu thuẫn đáng kể |
| 4 | Claim được hỗ trợ rõ ràng, citation chính xác và phạm vi kết luận phù hợp |

### 5.3. Trạng thái không thể đánh giá

Không ép mọi case thành PASS hoặc FAIL. Cho phép:

- **INSUFFICIENT_EVIDENCE:** không có nguồn đủ để xác minh.
- **NOT_APPLICABLE:** dimension không áp dụng cho task.
- **AMBIGUOUS_REQUIREMENT:** yêu cầu hoặc rubric không xác định được kỳ vọng.
- **OUT_OF_SCOPE:** case ngoài phạm vi evaluator.
- **REVIEW_REQUIRED:** cần chuyên gia hoặc adjudicator.

Đây là các trạng thái hợp lệ, không phải lỗi cần quy về FAIL. Tách chúng khỏi denominator khi tính pass rate theo định nghĩa đã công bố.

### 5.4. Viết ví dụ anchor

Rubric nên chứa case mẫu đã được adjudicate. Với mỗi anchor, lưu:

- Input và task family.
- Evidence/reference answer nếu có.
- Response.
- Điểm theo từng dimension.
- Lý do chấm và evidence references.
- Các lỗi khiến điểm bị trừ.
- Reviewer/adjudicator và rubric version.

Ví dụ anchor cần đa dạng về ngôn ngữ, độ dài, câu trả lời đúng một phần, trường hợp không đủ evidence và các edge cases thường gặp.

## 6. Thiết kế annotation protocol cho reviewer

Reviewer cần được hướng dẫn để đưa ra phán đoán nhất quán.

Một protocol nên quy định:

1. Xác định task family và dimension cần chấm.
2. Đọc câu hỏi, conversation context và response theo thứ tự thống nhất.
3. Chỉ sử dụng evidence được chỉ định trong rubric.
4. Chấm từng dimension độc lập.
5. Chọn trạng thái không đủ evidence khi cần.
6. Ghi reason code và evidence reference cho điểm thấp hoặc critical defect.
7. Không suy đoán intent hoặc dữ liệu không có trong case.
8. Đánh dấu rubric ambiguity và gửi lại người quản lý rubric.
9. Không trao đổi verdict với reviewer khác trước khi hoàn tất independent annotation.
10. Ghi thời gian, reviewer ID nội bộ và protocol version.

### 6.1. Blind review

Nếu reviewer biết model nào tạo response hoặc biết điểm của LLM judge, họ có thể bị ảnh hưởng. Khi mục tiêu là đánh giá nội dung, ẩn các thông tin không cần thiết:

- Model/provider name.
- Prompt version.
- LLM judge score/verdict.
- Nhãn của reviewer khác.
- Candidate/control assignment nếu không cần thiết.

Giữ lại thông tin cần cho việc chấm, ví dụ policy version hoặc source timestamp nếu chúng ảnh hưởng tính đúng đắn. Blind review không có nghĩa che giấu evidence quan trọng.

### 6.2. Randomize thứ tự

Với pairwise comparison, randomize vị trí A/B để giảm position bias. Nếu cùng reviewer đánh giá nhiều response, randomize thứ tự case và cân bằng vị trí. Lưu assignment để có thể kiểm tra bias sau này.

### 6.3. Double annotation

Chọn một phần case để hai reviewer đánh giá độc lập. Có thể double annotate:

- Tập calibration ban đầu.
- Case có risk cao.
- Case borderline hoặc evaluator-human disagreement.
- Một mẫu ngẫu nhiên để theo dõi inter-annotator agreement.
- Case thuộc task family mới.

Không chỉ double annotate những case bị nghi ngờ; cần có mẫu ngẫu nhiên để ước lượng mức đồng thuận trong toàn bộ luồng review.

### 6.4. Reviewer workload

Annotation chất lượng giảm khi reviewer mệt mỏi hoặc phải đọc quá nhiều case phức tạp liên tiếp. Theo dõi:

- Số case/giờ.
- Thời gian review theo task family.
- Tỷ lệ bỏ qua hoặc thiếu evidence.
- Rework và adjudication rate.
- Chất lượng trên các batch đầu/cuối ca.
- Reviewer calibration score.

Chia batch hợp lý, có thời gian nghỉ và không đánh giá hiệu suất reviewer chỉ bằng số case hoàn thành.

## 7. Adjudication: xử lý khi các đánh giá bất đồng

Không phải mọi bất đồng đều có cùng nguyên nhân.

| Loại bất đồng | Ví dụ | Hành động |
| --- | --- | --- |
| Rubric ambiguity | “Đầy đủ” không được định nghĩa cho task | Sửa rubric và chấm lại affected cases |
| Evidence mismatch | Hai reviewer thấy hai source versions khác nhau | Khóa evidence snapshot và xác minh nguồn |
| Interpretation difference | Cùng evidence nhưng hiểu claim khác nhau | Adjudicator chuyên môn xem xét |
| Scale calibration | Reviewer dùng điểm 2 và 3 khác nhau | Recalibrate bằng anchor cases |
| Judge failure | LLM judge bỏ qua mâu thuẫn trong context | Ghi defect của evaluator và sửa judge |
| True ambiguity | Yêu cầu có nhiều cách hiểu hợp lý | Giữ trạng thái AMBIGUOUS, không ép nhãn |

### 7.1. Quy trình adjudication

1. Giữ nguyên các annotation độc lập ban đầu.
2. Tạo adjudication task có case, rubric version và evidence snapshot.
3. Hiển thị các điểm khác nhau và reason codes.
4. Adjudicator xem evidence và có thể yêu cầu chuyên gia domain.
5. Ghi verdict cuối, rationale ngắn và nguồn hỗ trợ.
6. Ghi loại bất đồng và quyết định rubric có cần cập nhật không.
7. Nếu rubric thay đổi, tạo version mới và xác định case nào cần chấm lại.

Không xóa annotation cũ sau khi adjudicate. Dữ liệu bất đồng giúp tìm ra tiêu chí chưa rõ hoặc evaluator có bias.

### 7.2. Khi không thể phân xử

Một số case thiếu source of truth hoặc yêu cầu không đủ rõ. Khi đó dùng trạng thái unresolved/ambiguous, ghi nguyên nhân và yêu cầu bổ sung dữ liệu nếu có thể. Một nhãn ép buộc có thể làm nhiễm evaluation dataset.

## 8. Đo mức đồng thuận giữa người đánh giá

Agreement statistics giúp hiểu annotation có ổn định hay không. Chọn chỉ số theo loại dữ liệu.

### 8.1. Percent agreement

Với N case được hai reviewer cùng chấm, percent agreement là tỷ lệ case có cùng nhãn:

\[
P_o = \frac{\text{Số case đồng thuận}}{N}
\]

Dễ hiểu nhưng không điều chỉnh agreement có thể xảy ra do ngẫu nhiên và phụ thuộc phân bố nhãn. Nếu 98% case là PASS, hai reviewer luôn chọn PASS có thể đạt agreement cao nhưng không phân biệt được FAIL.

### 8.2. Cohen's kappa

Với hai annotators và nhãn phân loại:

\[
\kappa = \frac{P_o-P_e}{1-P_e}
\]

Trong đó:

- \(P_o\): observed agreement.
- \(P_e\): expected agreement do phân bố nhãn của từng annotator.

Kappa hiệu chỉnh agreement theo cơ hội, nhưng nhạy với prevalence và marginal distributions. Luôn báo thêm confusion matrix, class prevalence và raw agreement.

### 8.3. Weighted Cohen's kappa

Với thang ordinal 0–4, bất đồng 0 với 4 nghiêm trọng hơn bất đồng 3 với 4. Weighted kappa gán trọng số cho khoảng cách giữa các mức.

Có thể chọn linear hoặc quadratic weights, nhưng cần công bố lựa chọn. Không thay đổi weighting scheme giữa các báo cáo mà không ghi version.

### 8.4. Krippendorff's alpha

Krippendorff's alpha hỗ trợ nhiều annotators, nhiều loại scale và dữ liệu thiếu. Một dạng tổng quát:

\[
\alpha = 1 - \frac{D_o}{D_e}
\]

Trong đó \(D_o\) là observed disagreement và \(D_e\) là disagreement kỳ vọng. Chọn distance function phù hợp với nominal, ordinal hoặc interval data.

### 8.5. Continuous scores và pairwise preferences

- Với điểm số liên tục, có thể dùng intraclass correlation (ICC) theo thiết kế annotators/items.
- Pearson/Spearman correlation đo mức liên hệ hoặc thứ hạng, nhưng correlation cao không đồng nghĩa hai reviewer cho điểm giống nhau.
- Với pairwise preference, báo tỷ lệ đồng thuận theo cặp, tie rate và position balance.

Không chọn một chỉ số duy nhất cho mọi loại rubric.

### 8.6. Không dùng ngưỡng kappa như quy luật phổ quát

Một hệ thống có thể cần mức agreement khác nhau tùy tác động sai sót, độ khó và mục đích đánh giá. Hãy xác định target trước, đo human-human agreement trên cùng task, xem confusion matrix và các loại lỗi quan trọng. Nếu agreement thấp, điều tra rubric, training, evidence và reviewer population trước khi tăng số lượng annotation.

## 9. Hiệu chuẩn LLM evaluator bằng human-reviewed cases

LLM judge cần được kiểm tra trên một tập case có nhãn human-reviewed từ đúng task distribution. Không mặc định judge model mạnh hơn model generation nên đánh giá luôn đúng.

### 9.1. Tạo calibration set

Một calibration set nên bao gồm:

- PASS rõ ràng và FAIL rõ ràng.
- Borderline cases.
- Các loại lỗi phổ biến.
- Case có nhiều ngôn ngữ hoặc task families.
- RAG context đủ và context thiếu.
- Tool success/failure.
- Cases mà deterministic checks và judge thường bất đồng.

Nhãn reference nên được tạo bởi reviewer đã calibration, và case bất đồng phải qua adjudication theo protocol.

### 9.2. Đo judge-human agreement

Có thể theo dõi:

| Metric | Ý nghĩa |
| --- | --- |
| Accuracy vs adjudicated label | Tỷ lệ verdict đúng so với reference label |
| Precision theo FAIL | Trong các case judge báo FAIL, bao nhiêu case thực sự FAIL |
| Recall theo FAIL | Trong các case thực sự FAIL, judge phát hiện bao nhiêu |
| Confusion matrix | Các loại false positive/false negative |
| Cohen's kappa | Agreement có điều chỉnh chance cho phân loại |
| Weighted kappa | Agreement cho điểm ordinal |
| Spearman correlation | Tương quan thứ hạng score nếu phù hợp |
| Calibration error | Mức độ confidence khớp với xác suất đúng |
| Coverage | Tỷ lệ case judge đưa ra verdict thay vì abstain |

Với lỗi nghiêm trọng, false negative có thể nguy hiểm hơn false positive. Chọn threshold theo chi phí của từng loại lỗi; không chỉ tối đa hóa accuracy tổng.

### 9.3. Reliability khác validity

- **Reliability:** judge có đưa ra kết quả ổn định khi lặp lại cùng điều kiện không?
- **Validity:** kết quả có phản ánh đúng tiêu chí cần đo không?

Judge có thể rất nhất quán nhưng luôn bỏ sót một loại hallucination. Consistency cao không chứng minh validity cao.

### 9.4. Kiểm tra bias của judge

Các test nên có:

- **Position bias:** đảo thứ tự A/B trong pairwise comparison.
- **Length bias:** tạo các biến thể dài/ngắn nhưng giữ nội dung chính.
- **Style bias:** đổi cách diễn đạt mà không thay đổi correctness.
- **Self-preference:** kiểm tra judge có ưu tiên output từ cùng model family/provider không.
- **Authority bias:** ẩn model names và nhãn “expert” giả.
- **Language/dialect bias:** đánh giá cùng task bằng nhiều ngôn ngữ hoặc biến thể ngôn ngữ.
- **Prompt sensitivity:** thay đổi format không liên quan để xem verdict có đảo không.

Giữ một test suite cố định để theo dõi judge sau mỗi lần đổi model hoặc judge prompt.

### 9.5. Dùng nhiều judge có giới hạn

Ensemble hoặc majority vote có thể giảm một số dao động ngẫu nhiên, nhưng nhiều judge có cùng bias vẫn có thể đồng thuận sai. Nếu dùng ensemble:

- Chọn judge có nguồn/model khác nhau khi phù hợp.
- Giữ kết quả từng judge riêng.
- Ghi rule aggregation và version.
- Escalate khi judge bất đồng hoặc đều thiếu evidence.
- Hiệu chuẩn ensemble trên human-reviewed set.

Không dùng majority vote thay thế human adjudication cho quyết định high-stakes.

### 9.6. Coverage–risk curve cho quyết định auto-accept

Khi evaluator có score hoặc confidence đã hiệu chuẩn, hãy đánh giá trade-off giữa coverage và residual risk trên held-out human-labelled set:

- **Coverage:** tỷ lệ case được auto-accept theo threshold.
- **Selective risk:** tỷ lệ lỗi trong nhóm đã auto-accept.
- **Escalation rate:** tỷ lệ case còn lại phải chuyển sang human review hoặc abstain.

Tăng threshold thường làm coverage giảm và có thể làm selective risk giảm, nhưng quan hệ thực tế cần được đo trên từng dimension và cohort. Chọn threshold theo mức rủi ro cho phép, chi phí review và confidence interval; không tối ưu coverage riêng lẻ.

## 10. Routing policy: case nào cần con người?

Không thể review mọi interaction với cùng mức độ. Dùng policy để ưu tiên theo risk, uncertainty và giá trị thông tin.

### 10.1. Các trigger phổ biến

- Deterministic check FAIL.
- LLM judge confidence thấp hoặc trả INCONCLUSIVE.
- Nhiều evaluator cho verdict khác nhau.
- Human feedback negative hoặc có correction.
- Safety/policy category nhạy cảm.
- Model/prompt/retriever mới rollout.
- Task family mới hoặc distribution drift.
- Case nằm gần threshold PASS/FAIL.
- Judge-human agreement giảm trong cohort.
- Tool có side effect hoặc giao dịch quan trọng.
- Case thuộc nhóm khiếu nại hoặc escalation.

### 10.2. Ví dụ routing matrix

| Risk/Signal | Routing |
| --- | --- |
| Schema valid, low risk, evaluator PASS rõ ràng | Lưu auto result; audit sample ngẫu nhiên |
| LLM judge FAIL rõ ràng, không high-stakes | Human review theo sample hoặc defect policy |
| Borderline score gần threshold | Double annotation |
| Evaluator và deterministic check mâu thuẫn | Human review |
| Hai reviewer bất đồng | Adjudication |
| Safety/security/high-impact case | Expert human review theo policy |
| Task family mới, chưa calibration | Human review tăng cường |
| Thiếu context/source of truth | INSUFFICIENT_EVIDENCE, không ép PASS/FAIL |

### 10.3. Escalation dựa trên confidence

Nếu evaluator cung cấp confidence score, chỉ dùng sau khi đã kiểm tra calibration. Một số model trả confidence không có nghĩa đó là xác suất đúng.

Có thể định nghĩa vùng:

- Auto-accept: score/confidence nằm trong vùng đã hiệu chuẩn và risk thấp.
- Human review: score gần decision boundary hoặc uncertainty cao.
- Critical escalation: high-risk, safety issue hoặc evidence conflict.

Threshold cần được chọn trên calibration set theo chi phí false positive/false negative, không dùng một con số chung cho mọi dimension.

### 10.4. Giữ random audit

Dù auto evaluator có confidence cao, vẫn lấy mẫu ngẫu nhiên các case đã auto-accept để human audit. Nếu chỉ review case bị judge gắn cờ, hệ thống không phát hiện được false negatives và judge blind spots.

## 11. Spring AI: dùng Evaluator cho lớp tự động

Spring AI cung cấp interface Evaluator để đánh giá response. Trong Spring AI 2.1.0, EvaluationRequest gồm:

- userText: input gốc của người dùng.
- dataList: contextual data dưới dạng List<Content>, ví dụ nội dung được retrieve trong RAG.
- responseContent: nội dung response cần đánh giá.

Các implementation có sẵn gồm RelevancyEvaluator và FactCheckingEvaluator. Chọn evaluator model phù hợp với tiêu chí; model judge không nhất thiết là model đã sinh câu trả lời.

### 11.1. RelevancyEvaluator

RelevancyEvaluator đánh giá response có liên quan tới user input xét theo context được cung cấp hay không. Evaluator sử dụng prompt template với các thành phần query, response và context; có thể tùy chỉnh template.

Dùng nó để sàng lọc relevance trong RAG. Không dùng điểm relevance thay cho fact-check hoặc citation verification.

### 11.2. FactCheckingEvaluator

FactCheckingEvaluator đánh giá claim có được hỗ trợ về mặt logic bởi context/document hay không. Có thể dùng general-purpose judge model hoặc lựa chọn model chuyên cho fact checking nếu integration hỗ trợ.

Trong Spring AI 2.1.0, FactCheckingEvaluator nhận responseContent làm claim và ghép nội dung dataList thành document context. Nếu response dài có nhiều khẳng định độc lập, hãy tách thành claims, tạo request riêng và lưu mapping claim-to-source để có verdict chi tiết. Kết quả cần được xem trong phạm vi evidence đầu vào. Nếu context thiếu hoặc lỗi thời, evaluator không thể xác minh sự thật toàn cục.

### 11.3. Ví dụ Java

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.content.Content;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;
import org.springframework.ai.evaluation.RelevancyEvaluator;
import org.springframework.ai.evaluation.FactCheckingEvaluator;

import java.util.List;

public class AutomaticEvaluationService {

    public record EvaluationSummary(
            boolean relevancePass,
            boolean factCheckPass) {
    }

    private final RelevancyEvaluator relevancyEvaluator;
    private final FactCheckingEvaluator factCheckingEvaluator;

    public AutomaticEvaluationService(ChatModel judgeModel) {
        this.relevancyEvaluator =
                new RelevancyEvaluator(ChatClient.builder(judgeModel));

        this.factCheckingEvaluator =
                new FactCheckingEvaluator(ChatClient.builder(judgeModel));
    }

    public EvaluationSummary evaluate(
            String userText,
            List<Content> retrievedContext,
            String responseContent) {

        EvaluationRequest request = new EvaluationRequest(
                userText,
                retrievedContext,
                responseContent);

        EvaluationResponse relevance =
                relevancyEvaluator.evaluate(request);

        EvaluationResponse factCheck =
                factCheckingEvaluator.evaluate(request);

        return new EvaluationSummary(
                relevance.isPass(),
                factCheck.isPass());
    }
}
~~~

Đây là skeleton minh họa cho API Spring AI 2.1.0; cách tạo ChatModel, bean lifecycle và constructor có thể điều chỉnh theo cấu hình ứng dụng. Spring AI 2.1.0 dùng List<Content> trong EvaluationRequest và tạo FactCheckingEvaluator qua constructor nhận ChatClient.Builder; kiểm tra kiểu context thực tế do RAG advisor cung cấp trước khi truyền vào. EvaluationResponse.isPass() là verdict nhị phân của evaluator; các trạng thái INCONCLUSIVE, INSUFFICIENT_EVIDENCE hoặc ERROR cần được wrapper/application workflow quản lý riêng. Không gọi evaluator trong request path nếu latency/cost không phù hợp; có thể chuyển sang worker bất đồng bộ sau khi lưu evaluation snapshot.

### 11.4. Custom evaluator

Khi cần tiêu chí riêng, có thể triển khai Evaluator hoặc tùy chỉnh prompt template của evaluator có sẵn. Rubric custom nên yêu cầu output có schema rõ, ví dụ verdict, reason code và evidence references.

Không để evaluator tự tạo nhãn không có trong taxonomy. Validate output trước khi lưu; nếu parse thất bại, ghi evaluator error hoặc INCONCLUSIVE thay vì mặc định PASS.

## 12. Human review service và dữ liệu annotation

Human review là workflow do ứng dụng xây dựng. Spring AI cung cấp evaluator tự động, còn queue, reviewer assignment, audit và adjudication cần được quản lý ở application layer.

### 12.1. Evaluation case

Một case nên tham chiếu interaction snapshot và chứa những thông tin cần cho reviewer:

~~~json
{
  "evaluationCaseId": "case-01JABC",
  "interactionId": "interaction-7f4b",
  "assistantTurnId": "turn-03",
  "taskFamily": "RAG_QA",
  "rubricVersion": "support-quality-v5",
  "evidenceSnapshotRef": "evidence-opaque-17",
  "promptVersion": "support-v18",
  "modelRevision": "model-rev-42",
  "retrieverVersion": "retriever-v8",
  "reviewStatus": "PENDING",
  "priority": "HIGH",
  "createdAt": "2026-11-27T12:00:00Z"
}
~~~

Các ID và version trong ví dụ là giả lập. Không đưa raw prompt, customer data hoặc toàn bộ document text vào queue message. Reviewer UI tải evidence từ secure store sau khi xác thực quyền.

### 12.2. Annotation record

Mỗi reviewer tạo một record độc lập:

~~~json
{
  "annotationId": "annotation-01JDEF",
  "evaluationCaseId": "case-01JABC",
  "reviewerRef": "reviewer-opaque-3",
  "protocolVersion": "annotation-v4",
  "rubricVersion": "support-quality-v5",
  "scores": {
    "relevance": 3,
    "groundedness": 1,
    "completeness": 2
  },
  "reasonCodes": [
    "UNSUPPORTED_CLAIM"
  ],
  "evidenceRefs": [
    "document-chunk-ref-12"
  ],
  "status": "SUBMITTED",
  "submittedAt": "2026-11-27T12:10:00Z"
}
~~~

Giữ reviewer identity ở dạng reference được kiểm soát. Annotation record nên append-only hoặc versioned; sửa điểm phải tạo revision có audit trail.

### 12.3. Adjudication record

~~~json
{
  "adjudicationId": "adj-01JGHI",
  "evaluationCaseId": "case-01JABC",
  "annotationIds": [
    "annotation-01JDEF",
    "annotation-01JKLM"
  ],
  "adjudicatorRef": "expert-opaque-1",
  "finalLabels": {
    "relevance": 3,
    "groundedness": 1,
    "completeness": 2
  },
  "resolution": "CONFIRMED_DEFECT",
  "reason": "Một claim chính không được source hỗ trợ.",
  "rubricVersion": "support-quality-v5",
  "resolvedAt": "2026-11-27T12:30:00Z"
}
~~~

Final labels phải liên kết với rubric và evidence version đã dùng. Nếu case vẫn mơ hồ, lưu UNRESOLVED hoặc AMBIGUOUS thay vì tạo nhãn giả chính xác.

## 13. Queue, assignment và vận hành reviewer

Một review queue production cần:

- Priority theo risk, severity và age.
- Assignment theo chuyên môn, ngôn ngữ và tenant/data access scope.
- Lease/claim để tránh hai reviewer vô tình sửa cùng một task.
- Deadline/SLA và escalation khi quá hạn.
- Double annotation policy.
- Adjudication queue riêng.
- Idempotency khi reviewer submit lại do network retry.
- Audit trail cho mọi lần mở evidence, thay đổi score và export.
- Queue age, backlog, throughput và reviewer workload metrics.

### 13.1. Không phân công chỉ theo số lượng

Reviewer cần được phân theo năng lực domain. Một case pháp lý hoặc policy nội bộ không nên giao cho người không có quyền hoặc không có chuyên môn phù hợp.

Nếu reviewer không đủ context hoặc không có expertise, họ có thể trả UNABLE_TO_ASSESS và chuyển case sang nhóm phù hợp.

### 13.2. Tách review và adjudication

Reviewer ban đầu nên chấm độc lập. Adjudicator xem các kết quả sau khi đã submit. Nếu reviewer nhìn thấy điểm của người khác trước, họ có thể bị anchor vào kết quả đó và agreement metrics sẽ không còn đo annotation độc lập.

### 13.3. Theo dõi reviewer calibration

Định kỳ chèn anchor cases đã adjudicate vào batch review. Reviewer chấm anchor mà không biết đó là case calibration. So kết quả với expected labels và feedback về rubric.

Không dùng một batch nhỏ làm cơ sở duy nhất để xếp hạng nhân sự. Mục đích chính là phát hiện protocol chưa rõ và nhu cầu đào tạo.

### 13.4. Ví dụ service nhận annotation

~~~java
@Transactional
public void submitAnnotation(
        ReviewerPrincipal reviewer,
        AnnotationSubmission submission) {

    ReviewTask task = reviewTaskRepository
            .findByCaseIdAndAssignedReviewer(
                    submission.evaluationCaseId(),
                    reviewer.subjectRef())
            .orElseThrow(ReviewAccessDeniedException::new);

    if (!task.isOpen() || task.isLeaseExpired()) {
        throw new ReviewTaskUnavailableException();
    }

    Rubric rubric = rubricRepository.getVersion(
            task.rubricVersion());
    rubric.validate(submission.scores(), submission.reasonCodes());

    annotationRepository.insertIfAbsent(
            AnnotationRecord.from(reviewer, task, submission));
    reviewTaskRepository.markSubmitted(task.id());
    outboxRepository.enqueueAnnotationSubmitted(task.id());
}
~~~

Đây là service skeleton; principal, repository, rubric và exception là kiểu do ứng dụng định nghĩa. Transaction phải khóa hoặc kiểm tra version của review task để tránh hai submit cạnh tranh, xác minh assignment/lease, validate score theo đúng rubric version và chống submit trùng bằng annotation ID hoặc idempotency key. Adjudication nên là command riêng, chỉ cho role được phân quyền và không sửa các annotation gốc.

## 14. Đánh giá chính evaluator và rubric

Khi human labels đã đủ tin cậy, dùng chúng để kiểm tra judge model.

### 14.1. Calibration workflow

1. Lấy mẫu representative và risk cases theo policy.
2. Human reviewers chấm độc lập theo rubric.
3. Adjudicate các bất đồng quan trọng.
4. Chia calibration set và held-out judge test set.
5. Chạy LLM evaluator trên đúng evidence snapshot.
6. Tính confusion matrix, agreement, precision/recall và calibration.
7. Phân tích lỗi theo task family, language, source quality và model revision.
8. Điều chỉnh prompt/threshold hoặc thay evaluator.
9. Chạy lại trên held-out set.
10. Phê duyệt version và tiếp tục audit production.

Không dùng cùng một case để vừa tối ưu judge prompt vừa báo cáo kết quả cuối mà không ghi nhận leakage. Giữ held-out cases để ước lượng khả năng tổng quát hóa.

### 14.2. Reliability tests

Chạy lại cùng case nhiều lần hoặc với perturbations không làm thay đổi ý nghĩa:

- Thay thứ tự đoạn context.
- Thay format JSON/Markdown của input.
- Thay tên model thành alias trung tính.
- Đổi vị trí response trong pairwise comparison.
- Thêm whitespace hoặc formatting changes.
- Dùng seed/temperature được kiểm soát nếu provider hỗ trợ.

Nếu verdict thay đổi mạnh vì perturbation không liên quan, judge có vấn đề về consistency.

### 14.3. Validity tests

Đưa vào những case có ground truth hoặc evidence rõ:

- Claim mâu thuẫn với source.
- Citation trỏ tới chunk sai.
- Response bỏ sót điều kiện bắt buộc.
- Tool result trả lỗi nhưng answer nói thành công.
- Response đúng sự thật nhưng không trả lời intent.
- Context thiếu evidence và đáp án cần abstain.

Kiểm tra judge có nhận ra đúng dimension hay đang dùng một tiêu chí thay cho tiêu chí khác.

### 14.4. Judge drift

Judge model hoặc prompt của judge cũng có thể thay đổi. Ghi:

- Judge provider/model/revision.
- Judge prompt/rubric version.
- Decoding parameters.
- Evaluation dataset version.
- Calibration set version.
- Human agreement metrics.
- Bias audit results.
- Effective date và deployment cohort.

Khi judge được nâng cấp, chạy lại anchor set trước khi so sánh score dài hạn.

## 15. Bias và failure modes của LLM judge

| Failure mode | Biểu hiện | Cách kiểm tra/giảm thiểu |
| --- | --- | --- |
| Position bias | Ưu tiên response xuất hiện đầu hoặc cuối | Swap A/B và cân bằng vị trí |
| Verbosity bias | Ưu tiên câu trả lời dài | So nội dung tương đương ở nhiều độ dài |
| Self-preference | Ưu tiên output cùng model family | Blind model identity, cross-judge audit |
| Style bias | Ưu tiên văn phong trôi chảy dù sai | Tách style khỏi factuality/relevance |
| Authority bias | Tin nhãn “expert” hoặc source không được xác minh | Ẩn nhãn không liên quan và kiểm tra source |
| Prompt sensitivity | Verdict đổi vì format hoặc wording nhỏ | Perturbation tests |
| Context neglect | Bỏ qua đoạn evidence mâu thuẫn | Yêu cầu claim-level evidence references |
| Overconfidence | Trả PASS dù evidence thiếu | Cho phép INCONCLUSIVE/ABSTAIN |
| Prompt injection | Nội dung trong document yêu cầu judge bỏ rubric | Xem retrieved text là dữ liệu không tin cậy; cố định system rubric |
| Scale compression | Dồn điểm vào một khoảng hẹp | Calibration và anchor examples |

LLM judge nên đưa ra verdict, reason code và evidence references. Phần giải thích bằng ngôn ngữ tự nhiên giúp reviewer hiểu lý do, nhưng bản thân lời giải thích không chứng minh verdict đúng. Hãy xác minh evidence references.

## 16. Chọn human review theo risk và uncertainty

Một policy có thể kết hợp:

- Risk score từ task family và hậu quả sai.
- Deterministic failures.
- LLM evaluator score và abstain status.
- Disagreement giữa các evaluators.
- Drift signal hoặc model rollout.
- User feedback và business outcome.
- Sampling quota cho random audit.

Ví dụ:

~~~text
IF safety_or_high_impact = true
    route = EXPERT_HUMAN_REVIEW
ELSE IF deterministic_check = FAIL
    route = HUMAN_REVIEW
ELSE IF judge_status = INCONCLUSIVE
    route = HUMAN_REVIEW
ELSE IF judge_confidence is borderline
    route = DOUBLE_ANNOTATION
ELSE IF judge_and_rule_disagree
    route = ADJUDICATION
ELSE IF random_audit_selected
    route = HUMAN_AUDIT
ELSE
    route = AUTOMATED_RESULT_ONLY
~~~

Đây là logic minh họa. Confidence threshold phải được hiệu chuẩn; nếu evaluator không cung cấp confidence đáng tin cậy, dùng disagreement, score margin, repeated-run variance hoặc uncertainty proxy đã kiểm tra.

### 16.1. Risk tier

Có thể phân loại:

- **Low:** câu hỏi thông tin phổ thông, không có hành động hoặc hậu quả lớn.
- **Medium:** tư vấn nghiệp vụ nội bộ, RAG theo policy, tác vụ có thể sửa lại.
- **High:** quyền lợi tài chính, pháp lý, an toàn, dữ liệu nhạy cảm hoặc tool có side effect quan trọng.

Risk tier cần do product/domain owner định nghĩa. Không suy ra mức risk chỉ từ một LLM score.

### 16.2. Random audit vẫn bắt buộc

Nếu chỉ review những case evaluator đánh dấu, false negatives sẽ không xuất hiện trong review queue. Lấy mẫu ngẫu nhiên các case được auto-pass giúp ước lượng tỷ lệ judge bỏ sót lỗi. Oversample borderline/high-risk để điều tra nhưng giữ inclusion probability khi tính tỷ lệ population.

## 17. Human review và privacy

Reviewer có thể nhìn thấy prompt, response, retrieved documents và tool result. Đây là dữ liệu có thể chứa thông tin cá nhân, bí mật kinh doanh hoặc credentials.

Áp dụng:

- Chỉ cấp quyền cho reviewer theo tenant, task và purpose.
- Redact PII/secrets trước khi hiển thị nếu không cần thiết.
- Mask dữ liệu không liên quan tới dimension đang chấm.
- Audit mở, tải, export và adjudication evidence.
- Mã hóa evidence store và transport.
- Giới hạn thời gian giữ raw snapshots.
- Tách reviewer identity khỏi analytics export.
- Không đưa raw prompt/response vào metric labels.
- Có quy trình xử lý data deletion/retention.
- Không dùng annotation để huấn luyện hoặc chia sẻ ngoài mục đích đã được cho phép.

Blind review cần cân bằng với quyền truy cập evidence: ẩn model identity nhưng vẫn cung cấp source version cần thiết để đánh giá tính đúng đắn.

## 18. Metrics và dashboard cho human–AI evaluation

Các metric sau là ví dụ do ứng dụng tự định nghĩa, không phải metric mặc định Spring AI:

| Metric | Ý nghĩa |
| --- | --- |
| ai_eval_auto_runs_total | Số evaluator runs theo status |
| ai_eval_auto_pass_total | Số automated PASS |
| ai_eval_auto_fail_total | Số automated FAIL |
| ai_eval_human_cases_total | Số cases được gửi human review |
| ai_eval_human_annotations_total | Số annotation đã submit |
| ai_eval_adjudications_total | Số case cần adjudication |
| ai_eval_human_queue_oldest_age_seconds | Tuổi case lâu nhất trong queue |
| ai_eval_human_review_duration_seconds | Thời gian review |
| ai_eval_human_agreement_ratio | Tỷ lệ agreement quan sát |
| ai_eval_judge_human_agreement | Agreement judge-human theo dimension |
| ai_eval_judge_false_negative_total | Số lỗi judge bỏ sót trên audited sample |
| ai_eval_review_escalations_total | Số case được escalate |
| ai_eval_anchor_accuracy | Accuracy trên calibration anchors |

Đây là metric ứng dụng. Với agreement, calibration và weighted estimates, nên tính trong analytics pipeline hoặc batch job; Prometheus chỉ nhận các aggregate đã được tính.

### 18.1. Tỷ lệ case được chuyển human review

~~~promql
sum(rate(ai_eval_human_cases_total[1h]))
/
sum(rate(ai_eval_auto_runs_total[1h]))
~~~

Đây là tỷ lệ routing trên automated evaluation runs. Nếu denominator bằng 0 hoặc chưa có series, hiển thị không đủ dữ liệu.

### 18.2. Queue age

~~~promql
max(ai_eval_human_queue_oldest_age_seconds)
~~~

Queue age tăng liên tục có thể cho thấy reviewer capacity thấp, assignment lỗi hoặc lượng case escalate tăng.

### 18.3. Human review throughput

~~~promql
sum(rate(ai_eval_human_annotations_total[1h]))
~~~

Đọc cùng queue depth, case complexity và reviewer workload. Throughput tăng không nhất thiết là chất lượng annotation tăng.

### 18.4. Agreement theo dimension

~~~promql
ai_eval_judge_human_agreement{dimension="relevance"}
~~~

Metric này nên được export từ batch calculation với dataset window, rubric version và sample size được quản lý. Không tính agreement bằng cách chia hai counter tổng mà không giữ pairing giữa judge và human labels.

ai_eval_human_agreement_ratio là raw observed agreement. Nếu cần chance-corrected agreement, export riêng Cohen's kappa/weighted kappa hoặc Krippendorff's alpha cùng scale, annotator count, cohort và sample size; không đổi tên raw ratio thành kappa.

### 18.5. Dashboard cần hiển thị

- Automated PASS/FAIL/INCONCLUSIVE theo dimension.
- Human review rate và random audit coverage.
- Queue depth, oldest age, throughput và SLA.
- Double annotation và adjudication rate.
- Human-human agreement và judge-human agreement.
- False positive/false negative của judge.
- Judge calibration và bias audit theo task family.
- Quality score theo model/prompt/retriever version.
- Reviewer workload và anchor calibration performance.
- Sample count, inclusion probability và uncertainty.

Không hiển thị một con số agreement duy nhất mà bỏ qua dimension, rubric version và sample size.

## 19. Từ adjudicated labels tới evaluation dataset

Một case chỉ nên trở thành benchmark label khi:

- Input/context/evidence snapshot có thể nhận diện.
- Rubric version đã được xác định.
- Reviewer protocol đã được tuân thủ.
- Bất đồng quan trọng đã được adjudicate.
- Final label có evidence hoặc rationale đủ kiểm tra.
- Data rights và retention cho phép sử dụng.
- Dataset split và provenance đã được ghi.

### 19.1. Dataset record

~~~json
{
  "caseId": "eval-case-001",
  "datasetVersion": "support-quality-v12",
  "source": {
    "interactionId": "interaction-7f4b",
    "samplingPolicyVersion": "production-review-v4"
  },
  "rubricVersion": "support-quality-v5",
  "inputSnapshotRef": "input-opaque-1",
  "contextSnapshotRef": "context-opaque-1",
  "responseSnapshotRef": "response-opaque-1",
  "labels": {
    "relevance": 3,
    "groundedness": 1,
    "completeness": 2
  },
  "labelStatus": "ADJUDICATED",
  "adjudicationRef": "adj-01JGHI",
  "split": "VALIDATION"
}
~~~

Dữ liệu ví dụ là giả lập. Không nhúng raw content vào dataset manifest nếu có thể dùng secure references. Dataset materialization cần áp dụng quyền truy cập và retention của evidence gốc.

### 19.2. Tránh data leakage

Nếu dùng case để sửa prompt hoặc judge, đánh dấu case đã được dùng trong development. Không đưa âm thầm cùng case vào held-out test set. Giữ development, calibration, validation và test sets riêng theo mục đích.

### 19.3. Recalibration theo thời gian

Khi task distribution, model, rubric hoặc source corpus thay đổi, calibration set có thể không còn đại diện. Lấy mẫu mới, human review và so judge performance theo cohort. Giữ anchor set cố định để đo tính liên tục, đồng thời bổ sung recent cases để đo khả năng thích nghi.

## 20. Các tình huống production thường gặp

### 20.1. LLM judge PASS nhưng reviewer FAIL

Triệu chứng: judge đánh giá groundedness PASS nhưng reviewer phát hiện một claim không có source.

Điều tra:

1. Mở evidence snapshot và xác định claim bị bỏ sót.
2. Kiểm tra judge prompt có yêu cầu claim-level verification không.
3. Xác định source có mâu thuẫn hoặc bị cắt khỏi context không.
4. Ghi false negative của judge.
5. Thêm anchor case và cập nhật calibration set.
6. Chạy lại held-out set trước khi deploy judge prompt mới.

### 20.2. Hai reviewer bất đồng về relevance

Một reviewer chấm 2, người kia chấm 4.

Điều tra:

1. Kiểm tra họ có cùng task intent và conversation context không.
2. Đối chiếu anchor examples trong rubric.
3. Xác định rubric có định nghĩa rõ “đáp ứng một phần” không.
4. Adjudicator đưa ra verdict hoặc đánh dấu ambiguous.
5. Cập nhật rubric nếu bất đồng xuất phát từ định nghĩa thiếu rõ ràng.
6. Re-annotate các case liên quan nếu thay đổi ảnh hưởng nhãn cũ.

### 20.3. Judge score tăng sau khi đổi judge model

Không kết luận generation quality đã cải thiện. Có thể judge model mới chấm dễ hơn hoặc thay đổi scale.

- Chạy old và new judge trên cùng anchor set.
- So human agreement, confusion matrix và calibration.
- Giữ human labels làm reference.
- Recalculate trend bằng judge version cố định nếu cần.
- Ghi rõ điểm trước/sau không trực tiếp so sánh nếu rubric/judge scale đã đổi.

### 20.4. Review queue tăng đột biến

Kiểm tra:

- Model rollout có tạo nhiều borderline cases không?
- Evaluator timeout hoặc parse error có bị route nhầm thành review không?
- Random audit rate có bị thay đổi không?
- Reviewer assignment có bị nghẽn theo language/domain không?
- Queue có duplicate case do retry không?

Giữ status phân biệt PENDING, ASSIGNED, SUBMITTED, ADJUDICATION, RESOLVED và BLOCKED. Không giảm review rate một cách mù quáng chỉ để xóa backlog.

### 20.5. Human-human agreement thấp nhưng judge-human cao

Có thể judge đồng thuận với reviewer population cụ thể nhưng reviewer protocol chưa rõ hoặc một nhóm reviewer có bias chung. Xem confusion matrix, subgroup agreement và anchor cases. Không coi judge-human agreement cao là bằng chứng đủ nếu human-human reliability chưa được hiểu.

## 21. Quy trình triển khai từng bước

1. Xác định task families và dimensions cần đánh giá.
2. Chọn deterministic checks cho điều kiện có thể xác minh bằng code/source.
3. Viết rubric, anchors, reason codes và trạng thái inconclusive.
4. Chọn LLM evaluators phù hợp, version hóa model và prompt.
5. Tạo calibration set có human-reviewed/adjudicated labels.
6. Đo judge-human agreement, confusion matrix, precision/recall và bias.
7. Xác định routing policy theo risk, uncertainty và disagreement.
8. Xây evaluation case store và secure evidence references.
9. Tạo reviewer queue, assignment, blind review và double annotation.
10. Xây adjudication workflow và audit trail.
11. Theo dõi reviewer calibration, queue SLA và workload.
12. Chuyển adjudicated cases thành dataset có provenance.
13. Tách calibration/development/validation/test sets.
14. Recalibrate evaluator sau thay đổi model, prompt, rubric hoặc traffic.
15. Theo dõi automated/human metrics và random audit liên tục.

## 22. Checklist kiểm thử production

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| JSON output không parse được | Deterministic schema check FAIL |
| Relevance judge PASS nhưng context không hỗ trợ claim | Case có thể được human audit và ghi judge false negative |
| Context thiếu evidence | Evaluator có thể trả INCONCLUSIVE |
| Hai reviewer chấm độc lập | Không nhìn thấy verdict của nhau trước khi submit |
| Pairwise comparison | Vị trí A/B được randomize và ghi lại |
| Hai reviewer bất đồng | Tạo adjudication task, giữ nguyên annotation gốc |
| Rubric thay đổi | Version mới, affected cases được xác định |
| Judge model thay đổi | Chạy lại anchor/calibration set |
| Judge score tăng nhưng human labels không đổi | Dashboard không kết luận generation quality tăng |
| High-risk task | Expert review theo policy |
| Reviewer không có quyền tenant | Không thể mở evidence |
| Evidence hết retention | Reviewer thấy trạng thái unavailable, không lấy snapshot hiện tại thay thế |
| Reviewer sửa annotation | Có revision và audit trail |
| Queue event bị gửi duplicate | Idempotency không tạo case trùng |
| Random audit auto-pass | Phát hiện false negatives ngoài nhóm flagged |
| Dataset case đã dùng để tuning | Không được đưa âm thầm vào held-out test |
| Reviewer workload tăng | Queue/SLA alert và assignment policy hoạt động |

## 23. Bài tập thực hành

### Bài 1. Viết rubric relevance và groundedness

Tạo rubric 0–4 cho hai dimension. Viết ít nhất ba anchor cases gồm PASS, FAIL và borderline. Để hai reviewer độc lập chấm và ghi lại các điểm bất đồng.

### Bài 2. Tích hợp RelevancyEvaluator

Tạo EvaluationRequest với user input, retrieved Content objects và response. Chạy RelevancyEvaluator và lưu verdict cùng evaluator model/prompt version. Đối chiếu với human labels.

### Bài 3. Tích hợp FactCheckingEvaluator

Tạo response có một claim không được hỗ trợ bởi context. Chạy FactCheckingEvaluator và kiểm tra case context thiếu có được xử lý như INCONCLUSIVE theo workflow ứng dụng hay không.

### Bài 4. Xây double annotation và adjudication

Tạo reviewer queue cho 100 cases. Chọn một phần để double annotate. Tính raw agreement và Cohen's kappa; kiểm tra confusion matrix và adjudicate các case bất đồng.

### Bài 5. Hiệu chuẩn LLM judge

Dùng tập human-reviewed cases để đo precision, recall, judge-human agreement và false-negative rate. Thử một thay đổi prompt judge, so sánh trên held-out set và ghi version.

### Bài 6. Bias audit

Tạo pairwise response pairs rồi đảo vị trí A/B. Tạo các biến thể dài/ngắn giữ nguyên nội dung. Kiểm tra position bias và verbosity bias của judge.

### Bài 7. Routing policy

Thiết kế rule route case theo high risk, low confidence, disagreement, deterministic failure và random audit. Mô phỏng một đợt model rollout làm tăng borderline cases.

### Bài 8. Dataset governance

Chuyển một defect đã adjudicate thành evaluation case có evidence references, rubric version, reviewer records và dataset split. Xác minh case dùng để sửa prompt không lọt vào held-out test set.

## 24. Tổng kết

Kết hợp đánh giá tự động với rà soát của con người giúp hệ thống vừa xử lý được quy mô production vừa duy trì độ tin cậy:

- Deterministic checks xác minh điều kiện có thể kiểm tra bằng code hoặc nguồn có thẩm quyền.
- LLM evaluator mở rộng đánh giá relevance, fact checking và tiêu chí ngôn ngữ, nhưng phải được hiệu chuẩn.
- Human review xử lý case khó, rủi ro cao, borderline và disagreement.
- Adjudication tạo nhãn cuối có evidence và audit trail.
- Rubric, anchor cases và annotation protocol giúp reviewer chấm nhất quán.
- Cohen's kappa, weighted kappa, Krippendorff's alpha, ICC và confusion matrix đo agreement theo đúng loại dữ liệu.
- Judge cần được kiểm tra cả reliability, validity, calibration và bias.
- Random audit phát hiện false negatives mà routing theo judge không thấy.
- Spring AI cung cấp Evaluator, RelevancyEvaluator và FactCheckingEvaluator; queue, reviewer workflow và governance do ứng dụng xây dựng.
- Adjudicated labels trở thành evaluation dataset có version, provenance và split rõ ràng.
- High-impact decisions cần expert human oversight; không giao quyết định cuối cho LLM judge đơn độc.

Mục tiêu không phải để con người chấm lại mọi output. Mục tiêu là dùng tự động hóa đúng chỗ, đưa con người vào đúng thời điểm và liên tục kiểm tra cả chất lượng ứng dụng lẫn chất lượng của chính hệ thống đánh giá.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html): Evaluator, EvaluationRequest, RelevancyEvaluator, FactCheckingEvaluator và custom prompt templates.
- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient/ChatModel observations, metrics, traces và privacy defaults.
- [Human Evaluation of Large Language Models: A Review and Protocol Selection Framework (2026)](https://www.mdpi.com/2673-2688/7/5/174): rubric design, blinding, randomization, calibration, reliability statistics và risk-based human oversight.
- [Large Language Models as Judges: Recent Advances in Evaluation, Critique, Preference Modeling, and Feedback (2026)](https://link.springer.com/article/10.1007/s10462-026-11652-0): LLM judge bias, reliability, calibration, meta-evaluation và human collaboration.
- [Reliability without Validity: A Systematic, Large-Scale Evaluation of LLM-as-a-Judge Models (2026)](https://escholarship.org/content/qt5gx838hq/qt5gx838hq.pdf): khác biệt giữa consistency và bias, position effects và cách đánh giá judge.
