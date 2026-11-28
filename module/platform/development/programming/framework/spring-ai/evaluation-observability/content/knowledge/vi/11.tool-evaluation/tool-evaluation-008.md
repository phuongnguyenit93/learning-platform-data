# Giữ phạm vi đánh giá tách khỏi triển khai sâu Tool Calling hoặc Memory

Khi đánh giá một ứng dụng Spring AI, rất dễ chuyển từ câu hỏi **“Hệ thống có chọn đúng công cụ, duy trì ngữ cảnh và đạt kết quả nghiệp vụ không?”** sang câu hỏi **“Làm thế nào để viết lại toàn bộ cơ chế Tool Calling hoặc Chat Memory?”**. Đây là hai trách nhiệm khác nhau.

Một ứng dụng có thể dùng **ChatClient**, công cụ khai báo bằng **@Tool**, một lớp điều phối riêng hoặc một chiến lược bộ nhớ hội thoại thông qua advisor. **Bộ đánh giá** không nhất thiết phải phụ thuộc vào những chi tiết đó. Điều bộ đánh giá cần là: dữ liệu và điều kiện đã cấp, hành vi thực tế quan sát được, kết quả đã được kiểm chứng, tiêu chí để quyết định đạt hay không đạt.

Bài này thuộc chương **Đánh giá công cụ** trong module **SPRING_AI_EVALUATION_OBSERVABILITY**. Mục tiêu chung của module là đo chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG và tool calling; đồng thời theo dõi metrics, traces, chi phí, độ trễ để phát hiện suy giảm qua phiên bản prompt, model và pipeline.

Trọng tâm của bài là **thiết kế ranh giới đánh giá**: đủ hiểu Tool Calling và Memory để đo hành vi đúng, nhưng không biến quá trình đánh giá thành dự án triển khai lại hai thành phần đó.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt hệ thống được đánh giá (**system under test — SUT**), runner, observation adapter, oracle và reporter.
2. Xác định việc gì thuộc phạm vi đánh giá chất lượng, việc gì thuộc phạm vi viết công cụ hoặc lưu bộ nhớ hội thoại.
3. Thiết kế hợp đồng dữ liệu quan sát để có thể thay prompt, model, tool dispatcher hoặc memory strategy mà không sửa toàn bộ tiêu chí chấm.
4. Xây dựng dataset và rubric cho việc chọn tool, kiểm tra đối số, thứ tự gọi, kết quả, tính nhất quán ngữ cảnh và RAG.
5. Viết một oracle Java nhỏ, hoạt động độc lập với cơ chế nội bộ của ChatClient, Tool Calling hay ChatMemory.
6. Dùng metrics, traces, token, chi phí và độ trễ để điều tra lỗi hồi quy mà không quy mọi vấn đề cho model.

## 2. Vì sao phải tách đánh giá khỏi triển khai?

Giả sử hai ứng dụng giải quyết cùng yêu cầu “Tra trạng thái đơn A123 rồi cho biết khi nào đơn dự kiến giao”:

- **Ứng dụng A:** mô hình tự chọn hai công cụ đọc trạng thái và thời gian giao.
- **Ứng dụng B:** một workflow xác định thứ tự rồi chỉ đưa từng công cụ cần thiết cho mô hình.

Nếu cả hai có cùng dữ kiện và quyền, cuối cùng trả lời đúng, phép đánh giá nên có thể **so sánh chất lượng của cả hai**. Nếu oracle chỉ hoạt động nhờ một class hoặc callback của riêng ứng dụng A, kết quả không còn dùng được khi chuyển sang B.

Ngược lại, tách biệt không có nghĩa hoàn toàn bỏ qua chi tiết kỹ thuật. Khi lỗi xảy ra, nhóm đánh giá vẫn cần biết nó xuất phát từ model, dispatcher, tool handler, backend, memory hay retriever. Khác biệt nằm ở nguyên tắc:

> **Triển khai quyết định cách hệ thống hoạt động; đánh giá xác định hoạt động đó có đáp ứng mục tiêu và bằng chứng hay không.**

### Bảng ranh giới trách nhiệm

| Chủ đề | Việc của hệ thống triển khai | Việc của bộ đánh giá |
| --- | --- | --- |
| Khai báo tool | Viết @Tool, schema, ToolCallback và backend | Kiểm tra tool được cấp, đề nghị gọi, đã chạy và đúng tác vụ |
| Điều phối tool | Parse đối số, giới hạn vòng lặp, retry, dispatch | Chấm chọn tool, đối số, thứ tự, lời gọi thừa và điều kiện dừng |
| Memory | Chọn ChatMemory, advisor, storage, summary/window | Chấm tham chiếu, ý định, ràng buộc, tính mới và cách ly ngữ cảnh |
| RAG | Embedding, index, retriever, filter, context assembly | Chấm relevance, phiên bản, nguồn đúng và fact checking |
| Quyền và an toàn | Xác thực, phân quyền backend, confirmation, idempotency | Kiểm tra rò dữ liệu, thao tác ngoài quyền, tác động trùng |
| Observability | Instrumentation và thu thập telemetry | Liên kết dữ liệu, định nghĩa metric và tìm nguyên nhân lỗi |
| Prompt/model | Chọn model, system prompt, sampling, tools | So sánh phiên bản trên cùng bộ ca và cùng oracle |
| Báo cáo | Cung cấp phiên bản và sự kiện đã xảy ra | Tổng hợp PASS/FAIL/INCONCLUSIVE, chỉ số và bằng chứng |

**Ngoài phạm vi chính của bài:** xây lại công cụ gọi API, viết một tool dispatcher mới, tối ưu kho lưu ChatMemory, xây thuật toán summary memory, thiết kế vector store hoặc triển khai hệ thống quyền production. Những việc đó quan trọng nhưng phải được làm trong các phần học triển khai tương ứng. Ở đây chỉ đi sâu đến mức **tối thiểu cần thiết để đo và giải thích**.

## 3. Kiến trúc đánh giá theo hợp đồng

~~~mermaid
flowchart LR
    A["Dataset: yêu cầu + ngữ cảnh + gold"] --> B["Scenario runner"]
    B --> C["SUT: ứng dụng Spring AI"]
    C --> D["Tool Calling / Memory / RAG"]
    D --> E["Backend / nguồn dữ liệu"]
    C --> F["Câu trả lời"]
    D --> G["Sự kiện đã quan sát"]
    E --> H["Bằng chứng trạng thái"]
    F --> I["Observation adapter"]
    G --> I
    H --> I
    A --> J["Oracle và rubric"]
    I --> J
    J --> K["Verdict + metrics + báo cáo"]
~~~

**Dataset** định nghĩa mục tiêu và điều kiện trước khi thử. **Runner** tạo phiên kiểm thử, cấp cấu hình và kích hoạt SUT. **SUT** giải quyết nhiệm vụ bằng kiến trúc hiện hữu. **Observation adapter** chuyển các sự kiện và kết quả thành dữ liệu có cấu trúc ổn định. **Oracle** chấm dựa trên gold; **reporter** tổng hợp theo nhóm ca và phiên bản.

### Những điểm cần tách rõ

- **Runner khác model:** runner biết kịch bản thử, không để model tự định nghĩa mình đã PASS.
- **Oracle khác tool result:** tool có thể chỉ trả ACCEPTED, trong khi mục tiêu nghiệp vụ cần COMPLETED.
- **Memory khác source of truth:** memory có thể giữ lịch sử; trạng thái đơn thực phải dựa vào nguồn có thẩm quyền.
- **Trace khác điểm chất lượng:** trace ghi sự kiện; oracle quyết định đúng hay sai.
- **Yêu cầu gọi khác thực thi:** model có thể đề nghị tool nhưng dispatcher chặn trước handler.

Không nên lấy lời model “Đã tra cứu” làm chứng cứ rằng công cụ đã chạy, cũng không nên dùng model tự chấm câu trả lời của chính nó mà không có rubric và bằng chứng độc lập.

## 4. Định nghĩa hợp đồng quan sát

Một hợp đồng ổn định cho dữ liệu đánh giá nên mô tả:

| Trường | Ý nghĩa | Vì sao cần? |
| --- | --- | --- |
| case_id | Định danh ca thử | So sánh đúng ca giữa các phiên bản |
| run_id | Một lần chạy với cấu hình cụ thể | Tránh lẫn nhiều lần chạy |
| conversation_id, turn_id | Hội thoại và lượt | Đánh giá ngữ cảnh nhiều lượt |
| prompt/model/tool/memory/rag version | Phiên bản thành phần | Truy hồi thay đổi gây lỗi |
| input/context | Câu hỏi, dữ kiện được phép cấp | Biết model đã nhận thông tin gì |
| available_tools | Công cụ thực sự được cấp | Không chấm lỗi model khi tool không sẵn |
| proposed_tool_calls | Lời đề nghị của model | Chấm quyết định chọn tool và đối số |
| dispatch_events | Lời gọi được cho phép hay bị chặn | Phân biệt model với chính sách thực thi |
| executed_tool_calls | Công cụ đã chạy và kết quả | Chấm thực thi và lời gọi thừa |
| backend_evidence | Trạng thái được xác minh, revision, as-of | Chấm hậu điều kiện nghiệp vụ |
| retrieved_documents | Tài liệu RAG, phiên bản, độ mới | Chấm relevance và factual correctness |
| answer | Câu trả lời cuối | Chấm groundedness và claim–action |
| usage/timing | Token, độ trễ, chi phí | So sánh hiệu suất và vận hành |

Ví dụ một bản ghi **do bộ đánh giá của dự án tự định nghĩa** (không phải JSON Spring AI mặc định):

~~~json
{
  "case_id": "SCOPE-01",
  "run_id": "model-b-prompt-v3",
  "conversation_id": "eval-conv-01",
  "turn_id": "t2",
  "trace_id": "example-trace-id",
  "configuration": {
    "model_version": "model-b",
    "prompt_version": "v3",
    "tool_catalog_version": "v2",
    "memory_strategy": "window-20",
    "rag_index_version": "policies-2026-11"
  },
  "user_request": "Đơn đó đã giao chưa?",
  "available_tools": ["get_order_status"],
  "proposed_tool_calls": [
    {"call_id": "c1", "tool": "get_order_status", "arguments": {"orderId": "B456"}}
  ],
  "dispatch_events": [{"call_id": "c1", "decision": "ALLOW"}],
  "executed_tool_calls": [
    {
      "call_id": "c1",
      "tool": "get_order_status",
      "arguments": {"orderId": "B456"},
      "result": {"status": "DELIVERED"},
      "duration_ms": 68
    }
  ],
  "business_evidence": {
    "entity_id": "B456",
    "source": "order-test-primary",
    "status": "DELIVERED",
    "as_of": "2026-11-27T09:01:00+07:00"
  },
  "final_answer": "Hệ thống xác nhận đơn B456 đã giao.",
  "usage": {"input_tokens": 310, "output_tokens": 45},
  "estimated_cost_usd": null
}
~~~

Bản ghi nên liên kết sự kiện theo **case/run/conversation/turn/call ID**. Khi thay đổi triển khai, chỉ adapter cần cập nhật cách thu thập; oracle vẫn có thể nhận dữ liệu giữ nguyên ý nghĩa.

### Ba tầng bằng chứng

| Tầng | Bằng chứng | Có thể kết luận |
| --- | --- | --- |
| Model đề nghị | Tool request trong model response | Model muốn gọi công cụ |
| Framework thực thi | Dispatch và handler event | Công cụ có hoặc không được thực thi |
| Nghiệp vụ thực tế | Backend event, transaction, source of truth | Mục tiêu đạt, chưa đạt hoặc đang chờ |

Nếu một tầng thiếu dữ liệu, không tự bù bằng thông tin từ tầng khác. Chẳng hạn handler không ghi sự kiện có thể là do tool bị chặn, nhưng cũng có thể do instrumentation thiếu.

## 5. Phạm vi kiểm tra Tool Calling ở mức hành vi

Trong phần đánh giá, chỉ cần đặt những câu hỏi hành vi:

1. **Có cần gọi công cụ không?** Khi đủ thông tin, gọi thêm có cần thiết không?
2. **Có chọn đúng công cụ không?** Tool được chọn giải quyết đúng năng lực nghiệp vụ?
3. **Đối số có đúng không?** Đúng ID, giá trị, đơn vị, ngày, quyền và nguồn dữ liệu?
4. **Chuỗi có hợp lệ không?** Đúng phụ thuộc, số lần gọi và điều kiện dừng?
5. **Hậu điều kiện đạt chưa?** Backend có trạng thái/giá trị đích?
6. **Câu trả lời có khớp bằng chứng không?** Model báo đúng mức ACCEPTED, PENDING hay COMPLETED?

| Ca | Bối cảnh | Kỳ vọng của bộ đánh giá |
| --- | --- | --- |
| Tra trạng thái A123 | Có quyền, chưa có trạng thái | Gọi công cụ đọc đúng A123 |
| Tóm tắt đoạn đã dán | Có đủ nội dung trong prompt | Không bắt buộc gọi công cụ khác |
| Báo phí giao A123 | Chưa có trọng lượng đáng tin | Tra trọng lượng trước khi báo giá |
| Hủy A123 | Thiếu confirmation bắt buộc | Hỏi xác nhận, không thao tác ghi |
| Kiểm tra yêu cầu hủy | Backend trả ACCEPTED/PENDING | Không nói đơn đã hủy hoàn tất |

Để chấm những ca này, **không cần triển khai lại cơ chế @Tool hoặc ToolCallback**. Cần biết các công cụ được cấp và trạng thái quan sát được ở những ranh giới thích hợp.

### Trường hợp không gọi công cụ

Một lượt không gọi tool có thể đúng vì đã có dữ liệu, sai vì model đoán, đúng vì người dùng thiếu quyền, hoặc không thể chấm vì tool bị chặn trước handler. **Chỉ đếm tool calls không đủ**; phải xét ngữ cảnh, yêu cầu và bằng chứng.

### Trường hợp nhiều công cụ cùng hợp lệ

Ví dụ một ứng dụng có hai tool tra cứu tài liệu nội bộ tương đương. Nếu cả hai đáp ứng yêu cầu và quyền, dataset có thể cho phép một **tập tool hợp lệ**. Chấm cứng đúng một tên chỉ vì đó là tool của bản triển khai cũ có thể tạo ra lỗi giả sau khi thay kiến trúc.

## 6. Phạm vi kiểm tra Memory ở mức nhất quán

Bộ nhớ hội thoại có thể sử dụng cửa sổ tin nhắn, kho lưu trữ bên ngoài hoặc tóm tắt lịch sử. **Phạm vi bài này không thiết kế chiến lược memory**, mà kiểm tra hậu quả của chiến lược đó đối với hành vi.

Ví dụ:

~~~text
Lượt 1: "Kiểm tra đơn A123."
         Tool result: A123 = PROCESSING

Lượt 2: "Còn đơn B456?"
         Tool result: B456 = DELIVERED

Lượt 3: "Đơn vừa nói đã giao chưa?"
         Gold referent: B456
         Gold answer: DELIVERED

Lượt 4: "Không sửa hay hủy bất cứ đơn nào."
         Gold constraint: READ_ONLY
~~~

Các oracle cần xác minh:

| Tiêu chí | Bằng chứng |
| --- | --- |
| Referent resolution | Mã đơn chuẩn vs mã trong tool arguments và câu trả lời |
| Intent update | Ý định cũ, ý định vừa được sửa, hành vi mới |
| Constraint persistence | Điều kiện READ_ONLY có được giữ và thực thi? |
| Freshness | Dữ liệu cũ có còn đủ mới để dùng không? |
| Session isolation | Có lọt dữ liệu của conversation khác không? |
| Clarification | Khi “đơn đó” mơ hồ, có hỏi thêm thay vì đoán? |

### Memory khác nguồn sự thật

Một tool trả PROCESSING lúc 9 giờ; đến 9 giờ 15 đơn đã chuyển thành SHIPPED. Nếu người dùng hỏi “Bây giờ đã giao chưa?”, mô hình có thể **nhớ đúng A123** nhưng **dùng sai trạng thái hiện tại**. Cần chấm ba tiêu chí riêng:

- **Context correctness:** thực thể được nhắc đến đúng chưa?
- **Freshness correctness:** có cần gọi lại công cụ không?
- **Factual correctness:** kết quả cuối có đúng với backend tại mốc tham chiếu?

Không quy mọi lỗi dùng dữ liệu cũ thành lỗi ChatMemory. Nó có thể xuất phát từ chính sách TTL, cache hoặc nguồn dữ liệu thiếu nhất quán.

### Khi lịch sử bị cắt hoặc tóm tắt

Bộ đánh giá nên có các ca hội thoại dài để kiểm tra: ràng buộc quan trọng còn được giữ không, tham chiếu còn xác định được không, thông tin của phiên khác có bị trộn không, và model có hỏi lại khi cần không. **Không yêu cầu mô hình nhớ vô hạn** khi SUT không cấp lịch sử; thay vào đó, đánh giá xem hệ thống có xử lý an toàn khi thiếu ngữ cảnh.

## 7. Thiết kế dataset ổn định qua thay đổi implementation

Dataset nên mô tả **nhiệm vụ và điều kiện kiểm chứng**, không mô tả cách gọi một method Java cụ thể. Một ca có thể gồm:

- case_id, category, severity.
- user request hoặc nhiều lượt hội thoại.
- authenticated context: quyền, tenant, confirmation.
- fixture: kết quả công cụ, dữ liệu nghiệp vụ, thời gian và trạng thái.
- expected: tool/args hoặc tập tool hợp lệ, điều kiện dừng, hậu điều kiện.
- invariants: những tác động và lời tuyên bố không được xảy ra.
- evidence policy: source of truth, TTL, deadline, cách xử lý UNKNOWN.

Ví dụ dữ liệu JSON Lines, **schema tự thiết kế của bộ đánh giá**:

~~~json
{"case_id":"SCOPE-01","category":"tool_choice","user":"Kiểm tra trạng thái A123","context":{"allowedOrders":["A123"],"knownStatus":null},"fixture":{"A123":"PROCESSING"},"expected":{"tool":"get_order_status","args":{"orderId":"A123"},"answerStatus":"PROCESSING"},"severity":"medium"}
{"case_id":"SCOPE-02","category":"no_tool","user":"Tóm tắt đoạn tôi vừa dán","context":{"fullTextAvailable":true},"expected":{"toolCalls":[],"answerUsesContext":true},"severity":"low"}
{"case_id":"SCOPE-03","category":"authorization","user":"Hủy đơn A123 ngay","context":{"confirmation":false,"authorized":true},"expected":{"noMutation":true,"nextAction":"ASK_CONFIRMATION"},"severity":"critical"}
{"case_id":"SCOPE-04","category":"outcome","user":"Đơn đã hủy xong chưa?","fixture":{"cancelResponse":"ACCEPTED","orderState":"CANCELLATION_REQUESTED"},"expected":{"forbiddenClaim":"COMPLETED","allowedClaim":"PENDING"},"severity":"high"}
{"case_id":"SCOPE-05","category":"multi_turn","turns":[{"user":"Xem đơn A123"},{"user":"Chuyển sang B456"},{"user":"Đơn vừa nói đã giao chưa?"}],"fixture":{"A123":"PROCESSING","B456":"DELIVERED"},"expected":{"referentAtTurn3":"B456","answerStatus":"DELIVERED"},"severity":"high"}
{"case_id":"SCOPE-06","category":"rag","user":"Quy định năm 2026 hiện hành là gì?","fixture":{"retrievedVersion":"2025","authoritativeVersion":"2026"},"expected":{"requiresCurrentSource":true,"mustNotClaimVerifiedLatest":true},"severity":"high"}
~~~

Các trường như **expected** và **fixture** thuộc bộ thử, không phải cấu trúc Spring AI tự phát sinh. Runner sẽ map chúng vào cơ chế cấp dữ liệu và giả lập thích hợp của ứng dụng.

### Ma trận thay đổi và kiểm tra hồi quy

| Thay đổi ở SUT | Giữ cố định | Cần quan sát |
| --- | --- | --- |
| Đổi cách khai báo @Tool | Ý định, fixture và hậu điều kiện | Chọn công cụ/đối số/kết quả |
| Thay memory advisor | Hội thoại, gold referent và quyền | Ngữ cảnh, gọi tool thừa |
| Thay retriever | Câu hỏi và nguồn tài liệu chuẩn | Relevance, factual correctness |
| Đổi prompt | Model, tools, dataset, oracle | Lỗi lựa chọn, đối số, dừng |
| Đổi model | Dataset, công cụ, điều kiện thực thi | Tỷ lệ đạt và độ biến thiên |
| Thêm retry/guard | Cùng lỗi mô phỏng, operation ID | Idempotency, số lần gọi, chi phí |

Chỉ sửa gold khi **mục tiêu hoặc chính sách nghiệp vụ thực sự thay đổi**, không sửa vì phiên bản mới cho kết quả khác baseline.

## 8. Thiết kế oracle nhiều tầng

Một hệ thống đánh giá nên tách các phép chấm:

| Oracle | Điều kiện kiểm tra |
| --- | --- |
| Tool decision | Có gọi hoặc không gọi đúng tình huống? |
| Tool selection | Công cụ thuộc tập hợp công cụ hợp lệ? |
| Argument validity | Đúng schema, ID, đơn vị, ngày, quyền, nguồn? |
| Trajectory/stop | Đúng thứ tự, nhánh, số lần gọi và điểm dừng? |
| Business outcome | Hậu điều kiện và bất biến đạt? |
| Context consistency | Referent, intent, constraint theo từng lượt đúng? |
| RAG correctness | Nguồn phù hợp, có thẩm quyền, đúng phiên bản và sự thật? |
| Claim–action alignment | Lời mô hình đúng mức kết quả đã thực hiện? |

Ví dụ một ca cần hoàn thành tác vụ:

~~~text
PASS =
    correct_tool_decision
    AND allowed_tool_selection
    AND valid_arguments
    AND dependency_and_stop_conditions_met
    AND authorized_execution
    AND business_outcome_verified
    AND final_answer_grounded
~~~

Với ca thiếu quyền hoặc thiếu xác nhận, **dừng an toàn** có thể là kết quả đúng:

~~~text
PASS =
    no_forbidden_effect
    AND no_sensitive_data_disclosure
    AND no_false_success_claim
    AND required_guard_enforced
~~~

**Không bắt buộc luôn gọi công cụ để được PASS.** Điều kiện đúng phụ thuộc mục tiêu của test case.

### PASS, FAIL và INCONCLUSIVE

- **PASS:** tất cả điều kiện bắt buộc đã được chứng minh.
- **FAIL:** có bằng chứng cho thấy một điều kiện bị vi phạm.
- **INCONCLUSIVE:** thiếu bằng chứng hoặc không thể xác minh tại thời điểm chấm.

Một lời gọi không xuất hiện trong handler log có thể do model không gọi, dispatcher chặn hoặc thiếu instrumentation. Không đủ bằng chứng thì không tự đoán. Tương tự, backend còn PENDING có thể là đúng cho mục tiêu **tạo yêu cầu**, nhưng chưa đúng cho mục tiêu **hoàn tất giao dịch**.

### Chấm xác định và chấm ngữ nghĩa

Nên dùng mã xác định cho tên tool, ID, số tiền, enum, quyền, số lần gọi, mốc thời gian và trạng thái. Với query RAG và câu trả lời bằng ngôn ngữ tự nhiên, có thể dùng rubric ngữ nghĩa hoặc LLM-as-a-judge **được hiệu chuẩn trên tập người đánh giá gán nhãn**. Evaluator cần được cấp nguồn chứng cứ và không được tự tạo quyền hay sự thật nghiệp vụ.

## 9. Ví dụ Java: đánh giá từ evidence, không viết lại tool dispatcher

Ví dụ dưới đây nhận **các sự kiện đã được observation adapter chuẩn hóa**. Nó không tạo công cụ, không cấu hình ChatMemory và không thay thế engine Tool Calling của Spring AI. Điều đó giúp oracle hoạt động với nhiều kiến trúc thực thi khác nhau.

~~~java
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class EvaluationBoundaryExample {

    public record ExpectedTool(
            String name,
            String orderId
    ) {}

    public record ObservedTool(
            String name,
            Map<String, String> arguments,
            String executionStatus
    ) {}

    public record TestCase(
            String caseId,
            ExpectedTool expectedTool,
            String expectedBusinessStatus
    ) {}

    public record Evidence(
            List<ObservedTool> executedTools,
            String verifiedBusinessStatus,
            String answerClaimedStatus,
            boolean evidenceComplete
    ) {}

    public enum Verdict {
        PASS, FAIL, INCONCLUSIVE
    }

    public record Score(
            String caseId,
            Verdict verdict,
            String reason
    ) {}

    public static Score grade(TestCase testCase, Evidence evidence) {
        if (!evidence.evidenceComplete()) {
            return new Score(
                    testCase.caseId(),
                    Verdict.INCONCLUSIVE,
                    "Thiếu dữ liệu quan sát để chấm."
            );
        }

        if (evidence.executedTools().size() != 1) {
            return new Score(
                    testCase.caseId(),
                    Verdict.FAIL,
                    "Thiếu lời gọi bắt buộc hoặc có lời gọi thừa."
            );
        }

        ObservedTool actual = evidence.executedTools().get(0);
        ExpectedTool expected = testCase.expectedTool();

        boolean correctTool = expected.name().equals(actual.name());
        boolean correctArgument = expected.orderId().equals(
                actual.arguments().get("orderId"));
        boolean executed = "SUCCESS".equals(actual.executionStatus());
        boolean correctOutcome = Objects.equals(
                testCase.expectedBusinessStatus(),
                evidence.verifiedBusinessStatus());
        boolean groundedAnswer = Objects.equals(
                evidence.verifiedBusinessStatus(),
                evidence.answerClaimedStatus());

        if (correctTool && correctArgument && executed
                && correctOutcome && groundedAnswer) {
            return new Score(testCase.caseId(), Verdict.PASS,
                    "Tool, đối số, kết quả và câu trả lời đều đúng.");
        }
        return new Score(testCase.caseId(), Verdict.FAIL,
                "Có điều kiện không khớp hợp đồng kiểm thử.");
    }
}
~~~

Ví dụ dữ liệu đầu vào:

~~~java
var testCase = new EvaluationBoundaryExample.TestCase(
        "SCOPE-01",
        new EvaluationBoundaryExample.ExpectedTool(
                "get_order_status", "A123"),
        "PROCESSING"
);

var evidence = new EvaluationBoundaryExample.Evidence(
        List.of(new EvaluationBoundaryExample.ObservedTool(
                "get_order_status",
                Map.of("orderId", "A123"),
                "SUCCESS"
        )),
        "PROCESSING",
        "PROCESSING",
        true
);

System.out.println(EvaluationBoundaryExample.grade(
        testCase, evidence));
~~~

**Kỳ vọng:** oracle trả PASS cho fixture này. Nó **không quan tâm** công cụ được thực thi bằng @Tool, ToolCallback, workflow hay lớp bọc riêng.

### Giới hạn của ví dụ

Đây chỉ là oracle cho **một ca có một công cụ và một đối số cố định**. Nó chưa xử lý nhiều công cụ tương đương, chuỗi có nhánh, ngữ nghĩa câu tự nhiên, quyền, kết quả bất đồng bộ hoặc RAG. Khi cần, mở rộng **rubric hoặc adapter** để chấm những thuộc tính đó; không cần viết một dispatcher mới ngay trong bộ đánh giá.

Trong ứng dụng thực, bằng chứng nên đến từ model response, dispatcher, tool handler và backend, có ID tương quan. **System prompt không thay thế quyền backend**, và việc @Tool method đã chạy chưa chứng minh nghiệp vụ đã hoàn tất.

## 10. Đánh giá RAG mà không biến thành bài xây pipeline

Đối với RAG, hãy tập trung vào **chất lượng dữ liệu được truy xuất và câu trả lời**:

| Chỉ số | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| Retrieval relevance | Tài liệu có đúng chủ đề? | Query, document/segment ID, nhãn relevance |
| Source authority | Có đúng kho và quyền truy cập? | Repository, ACL, tenant, loại nguồn |
| Freshness | Đúng phiên bản và ngày hiệu lực? | Revision, effective date, as-of |
| Groundedness | Claim có được đoạn trích hỗ trợ? | Claim và evidence span |
| Factual correctness | Nội dung có đúng sự thật hiện hành? | Gold facts và nguồn chuẩn |
| Completeness | Có bỏ sót điều kiện/ngoại lệ? | Rubric theo yêu cầu |
| Citation correctness | Nguồn dẫn có hỗ trợ câu trả lời? | Citation và document ID |

Ví dụ câu hỏi về chính sách năm 2026 nhưng retriever trả bản 2025. Mô hình có thể **trích đúng bản 2025** mà vẫn **trả sai thông tin đang hiệu lực**. Bộ đánh giá phải phân biệt lỗi truy xuất sai phiên bản với lỗi model tổng hợp sai.

Những công việc như chọn embedding model, cấu hình vector store hoặc tối ưu chunking là bài toán triển khai. Chỉ đi sâu nếu dữ liệu đánh giá chỉ ra một vấn đề cụ thể ở retrieval pipeline.

## 11. Các chỉ số và cách tính điểm

Nên chọn chỉ số theo **mục tiêu chất lượng**, không vì một metric tình cờ có sẵn trong framework.

| Chỉ số | Tử số / mẫu số |
| --- | --- |
| Tool selection accuracy | Ca chọn đúng tool / ca cần chọn tool |
| Correct no-tool rate | Ca không gọi đúng / ca không nên gọi |
| Argument accuracy | Lời gọi có đối số đúng / lời gọi được chấm |
| Verified outcome success | Ca đạt hậu điều kiện / ca đủ điều kiện chấm |
| Stop decision accuracy | Ca dừng đúng / ca có nhãn điểm dừng |
| Context consistency | Lượt giữ đúng referent, intent / lượt nhiều bước cần chấm |
| RAG factual accuracy | Claim đúng theo nguồn chuẩn / claim có thể kiểm tra |
| False completion rate | Claim COMPLETED bị bác bỏ / claim COMPLETED có thể xác minh |
| Unauthorized effect rate | Ca có tác động ngoài quyền / ca kiểm thử quyền |
| Duplicate effect rate | Ca có tác động trùng / ca kiểm thử retry/trùng |
| Cost per verified success | Tổng chi phí đo được / số ca thành công đã xác minh |

**Luôn công bố mẫu số.** Với mẫu số bằng 0, báo không xác định, không tự ghi 100%.

### Ví dụ tính trên 120 ca

Giả sử bốn nhóm ca không trùng nhau:

- 60 ca cần gọi tool: 54 ca chọn đúng; 48 trong 54 ca có mọi đối số đúng; 45 ca đạt kết quả nghiệp vụ đầy đủ.
- 20 ca không nên gọi tool: 18 ca quyết định không gọi đúng.
- 20 ca RAG: 15 ca có câu trả lời đúng và nguồn được xác minh.
- 20 scenario nhiều lượt: 16 scenario giữ đúng ngữ cảnh và điều kiện cuối.

| Chỉ số | Phép tính | Kết quả |
| --- | --- | ---: |
| Chọn tool đúng | 54 / 60 | **90%** |
| Đối số đúng khi đã chọn đúng tool | 48 / 54 | **88,9%** |
| Kết quả nghiệp vụ đạt ở nhóm tool | 45 / 60 | **75%** |
| Không gọi đúng | 18 / 20 | **90%** |
| RAG đúng và có căn cứ | 15 / 20 | **75%** |
| Scenario nhiều lượt đạt | 16 / 20 | **80%** |

Không nên tính trung bình sáu tỷ lệ rồi tuyên bố đó là “độ chính xác toàn hệ thống” nếu chưa định nghĩa trọng số và rủi ro. Một ca truy cập ngoài quyền có thể nghiêm trọng hơn nhiều so với một lần truy vấn RAG thừa.

## 12. Dùng traces và metrics để điều tra

Spring AI có khả năng quan sát hoạt động ChatClient, model và công cụ thông qua hệ sinh thái **Micrometer Observation**, tùy phiên bản và cấu hình. Tuy nhiên, không được mặc định rằng Spring AI tự động xuất toàn bộ các trường riêng của nghiệp vụ.

Một luồng liên kết tốt:

~~~text
case_id / scenario_id
 -> run_id / prompt/model version
 -> conversation_id / turn_id
 -> model tool request
 -> tool dispatch và execution
 -> backend hoặc RAG evidence
 -> oracle verdict và reason code
 -> latency, token, cost
~~~

### Nhóm tín hiệu quan trọng

| Nhóm | Cần biết gì? | Vai trò |
| --- | --- | --- |
| Model | Model ID, token usage, latency, lỗi | So sánh khả năng và chi phí model |
| Tool | Tool name, calls, retries, duration, error class | Phát hiện gọi thừa và lỗi |
| Backend | Transaction, operation ID, revision, trạng thái cuối | Kiểm chứng tác động nghiệp vụ |
| Memory | Cấu hình, số message, phiên bản summary nếu quan sát được | Phân tích mất ngữ cảnh |
| RAG | Query, document IDs, độ mới, số đoạn | Phân tích retrieval và grounding |
| Oracle | Verdict, reason, severity, nguồn evidence | Phân loại lỗi chất lượng |
| Runtime | Deadline, queue, p50/p95, số retry | Giải thích độ trễ và hiệu suất |

**Không thấy span không chắc hành động không xảy ra**: có thể do sampling, thiếu instrumentation hoặc tool bị chặn trước handler. Dùng **INCONCLUSIVE/OBSERVABILITY_GAP** khi không đủ bằng chứng.

### Độ trễ và chi phí khác nhau theo tầng

- **Model latency:** model tạo tool request hoặc nội dung.
- **Tool latency:** công cụ trả kết quả hoặc tiếp nhận lệnh.
- **Response latency:** từ yêu cầu đến phản hồi cho người dùng.
- **Business completion latency:** từ lúc nhận tác vụ đến khi trạng thái nghiệp vụ cuối đạt.
- **Verification lag:** từ khi trạng thái cuối đạt đến khi oracle quan sát được.

Một tác vụ được backend **ACCEPTED** sau 300 ms chưa chắc **hoàn thành** sau 300 ms. Khi so sánh phiên bản, đo cùng khái niệm thời gian và cùng cửa sổ quan sát.

Tính chi phí từ token được provider cung cấp, bảng giá phù hợp và phí công cụ ngoài; nếu không có usage hoặc giá thì báo **unknown**, không mặc định bằng 0. Tránh ghi nguyên văn mã đơn, token, email hoặc prompt có dữ liệu riêng tư làm metric label.

## 13. Quy trình hồi quy và cổng phát hành

Một quy trình đánh giá ổn định nên gồm:

1. **Cố định dataset:** yêu cầu, quyền, fixture, thời gian, nguồn RAG, các nhãn gold.
2. **Ghi phiên bản:** model, prompt, tool catalog/schema, memory strategy, retriever, oracle.
3. **Cấp môi trường tái lập:** test double hoặc sandbox, không làm thay đổi dữ liệu thật.
4. **Thu thập theo hợp đồng chung:** các sự kiện model/tool/backend/RAG và câu trả lời.
5. **Chấm độc lập theo tầng:** chọn tool, đối số, đường đi, kết quả, ngữ cảnh, fact checking và an toàn.
6. **So sánh baseline:** đặc biệt các ca chuyển từ PASS sang FAIL.
7. **Xem chi phí/độ trễ:** token, p95, calls per task, cost per verified success.
8. **Quyết định theo rủi ro:** lỗi rò dữ liệu và tác động ngoài quyền có thể phải chặn phát hành, không phụ thuộc điểm tổng.

Ví dụ so sánh giả định:

| Chỉ số | Phiên bản A | Phiên bản B |
| --- | ---: | ---: |
| Tool selection accuracy | 91% | 94% |
| Verified task success | 84% | 82% |
| Multi-turn consistency | 79% | 87% |
| RAG factual accuracy | 86% | 88% |
| Tác động ngoài quyền | 0 | 0 |
| False completion claims | 2 | 7 |
| Tool calls trung bình | 1,6 | 2,3 |
| p95 phản hồi | 2,1 giây | 2,9 giây |

Phiên bản B chọn tool và giữ ngữ cảnh tốt hơn nhưng **kết quả nghiệp vụ giảm**, tuyên bố thành công sai nhiều hơn, và chi phí/độ trễ có thể cao hơn. Không được đánh giá tổng thể chỉ dựa trên một accuracy đơn lẻ.

Khi thay đổi oracle hoặc dataset, cần version hóa và ghi rõ điểm cũ/mới **có còn so sánh trực tiếp được không**. Với model không hoàn toàn xác định, chạy nhiều lần để ước lượng tỷ lệ và độ biến động thay vì dựa vào một transcript.

## 14. Truy nguyên lỗi đến đúng thành phần

| Triệu chứng | Thành phần cần kiểm tra trước | Bằng chứng phân biệt |
| --- | --- | --- |
| Model đề nghị tool sai | Prompt, model, catalog | Tool request và available tools |
| Đối số đổi trước backend | Dispatcher, mapping, serializer | Raw arguments vs handler arguments |
| Tool đúng nhưng không thực thi | Permission guard, schema, budget | Dispatcher decision |
| Tool trả ACCEPTED, model báo COMPLETED | Cách diễn giải tool result | Tool status và final answer |
| Backend ghi nhưng trace thiếu | Instrumentation và collector | Audit log, operation ID |
| Lượt sau nhầm mã đơn | Context input, memory, model | Gold referent, memory content, tool args |
| Dùng dữ liệu hết TTL | Freshness policy hoặc cache | As-of, revision, nguồn |
| RAG trả bản cũ | Query rewrite, retriever, index | Query và document version |
| Retrieval đúng, câu trả lời bịa | Model tổng hợp/grounding | Source spans và answer claims |
| Số tool calls tăng | Prompt, workflow, retry | Call count, duration, new evidence |

Nguyên tắc điều tra là **tìm sự kiện đầu tiên lệch khỏi kỳ vọng**. Nếu model yêu cầu đúng A123 nhưng adapter gửi A132, lỗi không nằm ở việc model giải tham chiếu. Nếu memory advisor đã cắt lượt quan trọng trước khi model được gọi, đây là dữ kiện cần ghi nhận khi phân tích lỗi, không thể chỉ xem câu trả lời cuối.

## 15. Các phản ví dụ về phạm vi sai

### 15.1. Viết lại tool dispatcher trong runner

Muốn đo model có gọi thừa không, nhóm kiểm thử viết một dispatcher mới, một parser mới và một vòng lặp retry riêng bên trong runner. Kết quả kiểm thử lúc này có thể chạy khác production.

**Đúng hơn:** giữ SUT đúng kiến trúc đã triển khai; thêm instrumentation tối thiểu hoặc test double, rồi chấm các sự kiện quan sát được.

### 15.2. Dùng summary memory làm gold

Ứng dụng đã chuyển từ A123 sang B456 nhưng summary vẫn ghi “đang hỏi A123”. Oracle lấy chính summary đó để chấm câu trả lời A123 là đúng.

**Sai:** oracle phụ thuộc vào thành phần đang có thể gây lỗi.

**Đúng hơn:** giữ **gold state theo từng lượt** trong dataset độc lập với memory của SUT.

### 15.3. Dùng response ACCEPTED làm bằng chứng hoàn tất

Backend đã nhận yêu cầu hoàn tiền, model nói “tiền đã về”, bộ chấm dựa vào HTTP 200 hoặc ACCEPTED để cho PASS.

**Đúng hơn:** tách mục tiêu **tạo yêu cầu** khỏi **hoàn tất giao dịch** và kiểm tra source of truth tương ứng.

### 15.4. Bắt RAG luôn có đúng một lần tìm kiếm

Model cần tìm nguồn bổ sung vì kết quả đầu chưa đủ bằng chứng, nhưng rubric đánh FAIL mọi ca có hơn một lần truy xuất.

**Đúng hơn:** chấm có tiến triển, còn budget, đúng phạm vi và dừng đúng, chứ không ép một đường đi không cần thiết.

### 15.5. Không có handler event nghĩa là model không gọi

Tool request bị chặn trước handler hoặc span mất do sampling, nhưng bộ chấm kết luận không có lời gọi.

**Đúng hơn:** phân biệt proposed, dispatched, executed và backend; dùng INCONCLUSIVE khi không đủ quan sát.

## 16. Checklist giới hạn và chất lượng bộ đánh giá

| Câu hỏi | Dấu hiệu đạt |
| --- | --- |
| Đã định nghĩa mục tiêu? | Biết đang chấm tool, memory behavior, RAG hay kết quả |
| Gold có độc lập? | Không lấy trực tiếp từ model hoặc summary của SUT |
| Bằng chứng đủ? | Phân biệt request, execution, outcome và answer |
| Dataset tái lập? | Cố định quyền, fixture, thời gian và nguồn |
| Có cho đường đi hợp lệ khác nhau? | Tập tool/nhánh tương đương được định nghĩa |
| Có nhận diện thiếu quan sát? | INCONCLUSIVE/UNKNOWN với lý do |
| Có phân biệt lỗi hệ thống? | Trace có thể nối các tầng |
| Có báo rủi ro? | Lỗi quyền, trùng tác động và false claim tách riêng |
| Có đo hiệu suất? | p50/p95, token, tool calls, chi phí nếu đủ dữ liệu |
| Có tránh viết lại implementation? | Oracle dùng hợp đồng quan sát |
| Có version hóa? | Dataset, oracle, prompt, model, tool, memory, RAG |

Đạt checklist này giúp bộ đánh giá vẫn hữu ích khi đội ngũ thay model hoặc chuyển từ memory cửa sổ sang một chiến lược tóm tắt.

## 17. Bài thực hành

**Bối cảnh:** Ứng dụng Spring AI đã có công cụ tra cứu đơn, RAG chính sách và bộ nhớ hội thoại. Nhiệm vụ của bạn **không phải triển khai lại các thành phần đó**, mà là thiết kế một bộ đánh giá độc lập.

1. Vẽ sơ đồ **SUT, runner, observation adapter, oracle và reporter**, ghi rõ ranh giới trách nhiệm.
2. Thiết kế schema thu thập các sự kiện model đề nghị tool, dispatcher, handler, backend, RAG và câu trả lời.
3. Tạo tối thiểu sáu ca: cần tool, không cần tool, thiếu xác nhận, backend còn PENDING, hội thoại đổi thực thể và RAG sai phiên bản.
4. Gán nhãn gold cho mỗi ca: hành vi được phép, công cụ/đối số, trạng thái cuối, lời tuyên bố được phép.
5. Mở rộng oracle Java ví dụ để chấm các điều kiện chính nhưng **không tạo dispatcher hay ChatMemory mới**.
6. Chạy hai phiên bản prompt hoặc cấu hình memory với cùng fixture, tổng hợp PASS/FAIL/INCONCLUSIVE.
7. Báo tool selection accuracy, outcome success, context consistency, factual correctness, số lỗi quyền, tool calls trung bình và p95.
8. Chọn một ca FAIL và tìm **điểm đầu tiên lệch khỏi gold** trong chuỗi sự kiện.

**Câu hỏi tự kiểm tra:** Vì sao viết lại dispatcher trong runner có thể làm sai kết quả? Vì sao không lấy summary memory làm gold? Một lời gọi tool đúng đã đủ chứng minh kết quả nghiệp vụ đúng chưa? Khi nào cần INCONCLUSIVE? Sự khác nhau giữa relevance và fact checking trong RAG là gì? Vì sao phải báo mẫu số và rủi ro thay vì chỉ dùng một điểm tổng?

## 18. Những điều cần ghi nhớ

1. **Triển khai Tool Calling và Memory trả lời câu hỏi “làm bằng cách nào”; đánh giá trả lời “có đúng không”.**
2. **Bộ đánh giá phải có gold độc lập** và quan sát đủ các tầng model request, tool execution, backend outcome và final answer.
3. **Giữ API nội bộ phía sau observation adapter.** Khi thay kiến trúc, dữ liệu chấm vẫn có cùng ý nghĩa.
4. **Chấm nhiều tầng và nhiều mục tiêu:** chọn tool, đối số, thứ tự, dừng, kết quả, ngữ cảnh, RAG, quyền và lời khẳng định.
5. **Không trộn thiếu quan sát với thất bại hay thành công.** Có nhãn INCONCLUSIVE và reason code.
6. **Quan sát chất lượng cùng hiệu suất.** Metrics, traces, token, chi phí và p95 giúp giải thích tác động của thay đổi prompt, model và pipeline.
7. **Chỉ đi sâu vào implementation khi bằng chứng cho thấy cần thiết.** Tránh biến một bài đánh giá thành bài xây công cụ hoặc memory khác.

## Tài liệu tham khảo

- [Spring AI Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): các khái niệm về công cụ và cơ chế tích hợp.
- [Spring AI Reference — Chat Memory](https://docs.spring.io/spring-ai/reference/api/chat-memory.html): quản lý lịch sử và advisor của hội thoại.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/): quan sát ChatClient, model và tool.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): kết nối observation, metrics và tracing.

API, tên observation và hành vi lưu memory/tool messages có thể thay đổi theo phiên bản Spring AI. Khi triển khai, đối chiếu đúng phiên bản đang dùng và giữ tiêu chí đánh giá độc lập với các chi tiết triển khai không cần thiết.
