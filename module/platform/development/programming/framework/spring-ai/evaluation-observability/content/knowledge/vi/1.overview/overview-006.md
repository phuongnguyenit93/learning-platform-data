# Ranh giới với các module Core, RAG, Tool Calling và Memory Advisors

Giả sử một ứng dụng Spring AI trả lời câu hỏi “Đơn hàng DH-123 hiện đang ở đâu?”. Ứng dụng sử dụng `ChatClient` để gọi mô hình, truy xuất một số tài liệu về quy trình giao hàng, có công cụ `getOrderStatus` và lưu lịch sử hội thoại để hiểu câu hỏi tiếp nối. Sau khi triển khai, người dùng nhận câu trả lời “đơn hàng đã giao”, trong khi backend cho biết đơn đang vận chuyển.

Để xử lý lỗi, cần biết **thành phần nào có trách nhiệm làm gì**:

- **Spring AI Core** cung cấp các abstraction và cơ chế xây dựng yêu cầu, gọi model, nhận response và điều phối thành phần.
- **RAG** đưa thông tin từ kho tài liệu bên ngoài vào ngữ cảnh cho model.
- **Tool Calling** cho phép model yêu cầu thực thi chức năng được ứng dụng cung cấp, chẳng hạn lấy trạng thái đơn hàng.
- **Memory Advisors** đưa ngữ cảnh hội thoại trước đó vào lượt tương tác hiện tại theo chính sách bộ nhớ.
- **Evaluation & Observability** kiểm tra chất lượng hành vi và ghi nhận cách hệ thống thực thi để xác định lỗi, hồi quy, độ trễ và chi phí.

Điểm then chốt: **Evaluation & Observability là lớp kiểm chứng và quan sát xuyên suốt**, không thay thế trách nhiệm triển khai của Core, RAG, Tool Calling hay Memory Advisors. Nó có thể chỉ ra lỗi ở một ranh giới, nhưng không tự biến tài liệu cũ thành tài liệu đúng, không tự sửa phân quyền của tool và không bảo đảm bộ nhớ hội thoại luôn phù hợp.

Trong module **SPRING_AI_EVALUATION_OBSERVABILITY**, người học tập trung vào dataset, relevance, fact checking, kiểm thử luồng RAG/tool calling, metrics, traces, token, chi phí và độ trễ để so sánh các phiên bản prompt, model và pipeline. Bài này làm rõ **mối quan hệ** giữa module đánh giá/quan sát với bốn nhóm chức năng nền tảng.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Giải thích trách nhiệm chính của Core, RAG, Tool Calling, Memory Advisors và Evaluation & Observability.
2. Phân biệt *thành phần tạo ra hành vi* với *thành phần đo hoặc chấm hành vi đó*.
3. Xác định dữ liệu/bằng chứng cần thu tại mỗi ranh giới để đánh giá relevance, factual correctness, groundedness và tool correctness.
4. Xác định khi nào câu trả lời sai do retrieval, generation, tool, memory hoặc mã điều phối.
5. Thiết kế test và các trường hợp hồi quy cho RAG, tool calling, bộ nhớ hội thoại và phối hợp giữa các thành phần.
6. Gắn kết quả đánh giá với metrics/traces để tìm nút thắt latency, token và chi phí mà không nhầm chúng với điểm đúng nội dung.
7. Biết loại thay đổi thuộc module nào khi cải tiến prompt, model và pipeline.

## 2. Bản đồ trách nhiệm của các module

| Nhóm chức năng | Đầu vào chính | Trách nhiệm chính | Đầu ra hoặc tác động | Không tự bảo đảm |
| --- | --- | --- | --- | --- |
| **Core** | User/system prompt, cấu hình model, yêu cầu gọi chat | Cung cấp API, cấu trúc request/response, chuyển yêu cầu tới model | `ChatResponse`, thông tin model, thông điệp sinh | Nội dung luôn đúng thực tế |
| **RAG** | Câu hỏi, kho tài liệu/index, chính sách lọc | Tìm và chuẩn bị bằng chứng bên ngoài để đưa vào context | Retrieved `Document`, prompt có context | Mọi tài liệu đều đúng, mới và được model dùng đúng |
| **Tool Calling** | Tool definition, yêu cầu gọi tool, tham số, quyền | Kết nối yêu cầu của model với chức năng ứng dụng/backend | Kết quả tool, lỗi, tác dụng phụ nếu có | Model chọn đúng tool; backend luôn cho phép an toàn |
| **Memory Advisors** | Lượt hội thoại, conversation ID, chính sách memory | Nạp/lưu ngữ cảnh các lượt trước để giữ mạch hội thoại | Lịch sử hoặc nội dung tóm tắt được đưa vào prompt | Ký ức luôn đúng, cập nhật hoặc có thẩm quyền nghiệp vụ |
| **Evaluation** | Dataset, rubric, answer, retrieved context, tool evidence | Chấm kết quả và phát hiện lỗi/hồi quy theo tiêu chí | Pass/fail, điểm số, lý do, báo cáo phiên bản | Tự tạo bằng chứng còn thiếu hoặc tự sửa lỗi |
| **Observability** | Các sự kiện/lời gọi thực thi | Đo và liên kết request, span, lỗi, usage, latency | Metrics, traces, logs, token/cost estimate | Tự kết luận câu trả lời có đúng ngữ nghĩa |

Trong triển khai thật, các phần có giao thoa: advisor có thể gọi retriever; Core có thể điều phối tool calling; Memory Advisors cũng là advisors hoạt động trong hệ sinh thái ChatClient. “Ranh giới” ở đây là **trách nhiệm kỹ thuật và câu hỏi đánh giá**, không phải khẳng định chúng luôn là các service độc lập.

### 2.1. Sơ đồ dòng thực thi và dòng kiểm chứng

~~~mermaid
flowchart TD
    U["User request"] --> C["Core: ChatClient / ChatModel"]
    C --> A["Advisor chain"]
    A --> M["Memory Advisor<br/>ngữ cảnh hội thoại"]
    A --> R["RAG Advisor / Retriever<br/>tài liệu có nguồn"]
    M --> P["Prompt cho model"]
    R --> P
    P --> L["ChatModel"]
    L --> T{"Model yêu cầu tool?"}
    T -- "Có" --> F["Tool execution<br/>backend + quyền"]
    F --> L2["Model xử lý kết quả tool"]
    T -- "Không" --> O["Final answer"]
    L2 --> O
    C -.-> X["Tracing / metrics<br/>Core, Advisors, retrieval, model, tool"]
    R -.-> X
    F -.-> X
    L -.-> X
    O --> E["Evaluation runner / sample reviewer"]
    R -.-> E
    F -.-> E
    M -.-> E
    E --> D["Chất lượng + hồi quy<br/>theo phiên bản"]
    X --> D
~~~

Sơ đồ là **sơ đồ khái niệm**. Thứ tự Advisors thực tế phụ thuộc cấu hình, và không phải mọi request đều gọi retrieval, memory hay tool. Một số thao tác có thể tạo nhiều vòng gọi model, retry hoặc chạy song song. Vì vậy cần thu **chuỗi thực tế** thay vì giả định mọi trace đều giống sơ đồ.

## 3. Ranh giới với Spring AI Core: thực thi yêu cầu không đồng nghĩa đánh giá kết quả

Core cung cấp các abstraction để ứng dụng Java nói chuyện với model và quản lý cấu trúc đầu vào/đầu ra. Có thể làm việc với những khái niệm như `ChatClient`, `ChatModel`, `Prompt`, `Message`, `ChatResponse`, cấu hình model và response metadata.

Ví dụ tối giản:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;

public final class SimpleAssistant {
    private final ChatClient client;

    public SimpleAssistant(ChatModel model) {
        this.client = ChatClient.builder(model).build();
    }

    public String ask(String question) {
        return client.prompt()
                .user(question)
                .call()
                .content();
    }
}
~~~

Lệnh `call().content()` có thể hoàn tất và trả về văn bản ngay cả khi văn bản chứa dữ kiện sai. Nếu có exception, đây là tín hiệu lỗi kỹ thuật; nếu không có exception, ta chỉ biết lời gọi đã hoàn thành theo hợp đồng ở cấp giao tiếp.

### 3.1. Những gì cần kiểm tra trong Core

**Kiểm thử chức năng xác định:**

- Request có được validate đúng không, có giới hạn input không?
- Cấu hình model, timeout, retry và parser đầu ra có hợp lệ không?
- Hệ thống có áp dụng đúng system instruction, các biến prompt và giới hạn response không?
- Khi model/provider lỗi, exception được chuyển thành trạng thái API thích hợp chưa?
- Các dữ liệu nhạy cảm có bị đưa vào thông điệp ngoài phạm vi được phép không?

**Đánh giá chất lượng trên Core:**

- Answer có liên quan câu hỏi không?
- Câu trả lời có tuân thủ format, ngôn ngữ và các ràng buộc nghiệp vụ không?
- Đối với tác vụ không có nguồn tham chiếu, có rubric hoặc người đánh giá phù hợp không?

**Observability trên Core:**

- Thời gian của lời gọi ChatClient và ChatModel.
- Số request lỗi, retry, timeout theo provider/model.
- Token usage, độ dài input/output, chi phí ước tính khi usage khả dụng.

Core tạo đường dẫn để **gọi model**; Evaluation & Observability tạo bằng chứng để quyết định **model và hệ thống có đáp ứng yêu cầu hay không**.

### 3.2. Một lỗi Core khác với lỗi mô hình

Giả sử ứng dụng yêu cầu đầu ra JSON nhưng hàm xử lý trả nguyên văn mà không kiểm tra schema. Nếu model trả JSON thiếu trường `status`, cần phân biệt:

- **Output của model không đáp ứng schema:** lỗi hành vi sinh, có thể được phát hiện bằng schema validator.
- **Ứng dụng chấp nhận JSON sai và thực hiện giao dịch:** lỗi phần mềm trong kiểm tra đầu vào/đầu ra, cần sửa bằng Java code.
- **Cấu hình model hoặc parsing bị lỗi:** vấn đề tại ranh giới Core/integration.
- **Request xử lý rất chậm:** observability cho biết phần thời gian bị tiêu thụ ở model, network, parser hoặc retry.

Đừng dùng một LLM judge làm bộ kiểm tra duy nhất cho những quy tắc có thể mô tả xác định bằng JSON Schema hoặc logic nghiệp vụ.

## 4. Ranh giới với RAG: nguồn tri thức khác với cơ chế đánh giá nguồn

RAG (*Retrieval-Augmented Generation*) thường gồm các bước:

1. Chuẩn bị tài liệu, chia đoạn, tạo embedding, lưu index/vector store và metadata.
2. Biểu diễn câu hỏi thành truy vấn tìm kiếm.
3. Truy xuất các đoạn tài liệu liên quan theo `top-k`, bộ lọc metadata hoặc reranking.
4. Ghép các đoạn tìm được vào prompt cho model.
5. Sinh câu trả lời và có thể kèm citation.

RAG trả lời câu hỏi: **“Cung cấp bằng chứng bên ngoài nào cho model?”**

Evaluation & Observability trả lời thêm: **“Bằng chứng ấy có đúng và đủ không? Model có sử dụng đúng không? Các bước nào gây chậm hoặc tốn chi phí?”**

### 4.1. Hai lớp đánh giá RAG khác nhau

| Lớp | Cần đánh giá | Ví dụ |
| --- | --- | --- |
| **Retrieval** | Đã tìm đúng tài liệu, đúng phiên bản, đúng quyền và đủ bằng chứng? | `policy-v3#refund` có nằm trong `top-k` hay không |
| **Generation** | Đã trả lời đúng câu hỏi và chỉ dựa trên bằng chứng được cung cấp? | Model có nêu đúng “14 ngày” và trích nguồn phù hợp? |

Nếu retriever không tìm được tài liệu cần thiết, `Recall@k` hoặc `hit@k` có thể phát hiện lỗi khi dataset có nhãn tài liệu liên quan. Nếu retriever đã trả đúng tài liệu nhưng model vẫn diễn giải sai, vấn đề có thể ở prompt, cách đưa context hoặc model.

### 4.2. Relevance, groundedness và factual correctness không tương đương

Giả sử **chính sách giả định** hiện hành `policy-v3` ghi gói Pro hoàn phí trong **14 ngày**, trong khi `policy-v2` đã hết hiệu lực ghi **30 ngày**.

| Kết quả | Relevance | Groundedness so với context thực | Factual correctness theo policy hiện hành |
| --- | --- | --- | --- |
| Model trả lời “30 ngày”, context chỉ có `policy-v2` | Có thể đạt | Có thể đạt | Không đạt |
| Model trả lời “30 ngày”, context có `policy-v3` (14 ngày) | Có thể đạt | Không đạt | Không đạt |
| Model trả lời “14 ngày”, không có nguồn nào | Có thể đạt | Chưa đủ bằng chứng để kết luận grounded | Có thể đúng về dữ kiện |
| Model trả lời “14 ngày” với `policy-v3` | Có thể đạt | Có thể đạt | Có thể đạt |

“Có thể đạt” phụ thuộc rubric, nội dung đầy đủ và evaluator. **Một câu có vẻ đúng không chứng minh retrieval đã đúng**; một câu bám sát nguồn cũ chưa chắc đúng thực tế.

### 4.3. Ranh giới quyền và dữ liệu

Hệ thống retrieval có thể có metadata như `tenantId`, `visibility` hoặc `effectiveFrom`. Việc giới hạn tài liệu theo quyền và hiệu lực phải được thực thi bằng thành phần đáng tin ở ranh giới truy cập, không chỉ bằng prompt “đừng dùng dữ liệu của người khác”.

Evaluation cần có ca kiểm tra quyền, chẳng hạn người dùng A không được truy xuất tài liệu riêng của B. Observability cần ghi dấu hiệu lọc/deny an toàn nhưng không đưa nội dung riêng tư vào metric tags.

### 4.4. Bằng chứng tối thiểu cho một ca RAG

Một lần chạy RAG nên ghi:

~~~json
{
  "attemptId": "rag-refund-001-attempt-1",
  "questionRef": "test-case:rag-refund-001",
  "retrieval": {
    "topK": 3,
    "indexVersion": "policy-index-v3",
    "documents": [
      {"id": "policy-v3#refund", "rank": 1, "effective": true},
      {"id": "faq-billing", "rank": 2, "effective": true}
    ]
  },
  "promptVersion": "answer-prompt-v5",
  "answer": "Gói Pro có thể yêu cầu hoàn phí trong 14 ngày kể từ ngày mua.",
  "citations": ["policy-v3#refund"],
  "traceId": "sample-trace-rag-001"
}
~~~

Đây là **record do nhóm tự thiết kế**, không phải JSON Spring AI tự xuất đầy đủ. Khi chấm groundedness, cần ngữ cảnh **thực sự được đưa vào model**; danh sách retrieved documents có thể khác context cuối nếu có cắt ngắn, giới hạn token hoặc biến đổi nội dung.

## 5. Ranh giới với Tool Calling: hành động có hợp đồng riêng

Tool Calling đưa dữ liệu động hoặc chức năng của ứng dụng vào luồng tương tác. Model có thể đề xuất một lời gọi tool; phía ứng dụng/tool execution cung cấp chức năng thật và trả kết quả để model tiếp tục tạo phản hồi.

Ví dụ các chức năng:

- `getOrderStatus(orderId)`: đọc trạng thái đơn hàng.
- `calculateShippingFee(address, weight)`: tính phí.
- `createSupportTicket(details)`: tạo yêu cầu hỗ trợ.
- `refundOrder(orderId)`: yêu cầu hoàn phí, có tác dụng phụ.

### 5.1. Ranh giới model và backend

**Model có thể yêu cầu** gọi một tool. **Backend mới là nơi phải áp dụng** phân quyền, xác thực, kiểm tra nghiệp vụ, xác nhận hành động nhạy cảm và idempotency. Chỉ dựa vào prompt để ngăn thao tác trái phép là không đủ.

Ví dụ, tool `refundOrder` phải kiểm tra quyền sở hữu đơn và điều kiện hoàn phí ngay tại phía tin cậy. Một câu trả lời đúng văn phong không bù được lỗi hoàn tiền hai lần.

### 5.2. Ranh giới kiểm thử với evaluation

| Tiêu chí | Dữ liệu kỳ vọng | Bằng chứng thực tế | Cơ chế kiểm |
| --- | --- | --- | --- |
| Chọn tool | `getOrderStatus` | Tool name đã gọi | Assertion |
| Đối số | `orderId=DH-123` | Tham số ở dispatcher | Schema/contract assertion |
| Phân quyền | Người dùng được phép | Kết quả enforcement ở backend | Integration/security test |
| Số lần gọi | Một lần | Tool invocation IDs | Assertion |
| Kết quả tool | `IN_TRANSIT` | Tool response | So với fixture/backend |
| Answer sau tool | “Đơn đang giao” | Final answer | Rule/rubric/evaluator |
| Hậu điều kiện | Thao tác được thực hiện đúng một lần | Trạng thái persisted ở backend | Transaction/integration test |
| Vận hành | Trong ngân sách thời gian và lỗi | Tool span, errors, retries | Metrics/traces |

Một lời gọi HTTP 200 từ ChatClient không chứng minh `refundOrder` đã commit đúng. Tool có thể thất bại, trả mã từ chối hoặc bị retry; model vẫn có thể tuyên bố sai rằng thao tác thành công. **Phải kiểm tra lời gọi thực tế và trạng thái backend**.

### 5.3. Tình huống tool không được gọi

Người dùng hỏi “Đơn DH-123 đang ở đâu?” và model trả “Đơn đang giao” nhưng không có `getOrderStatus` call.

- **Answer relevance:** câu trả lời có thể đúng chủ đề.
- **Tool-behavior correctness:** FAIL nếu yêu cầu bắt buộc tra backend.
- **Factual correctness:** chưa có căn cứ xác minh trạng thái đơn.
- **Observability:** trace/dispatcher event cho thấy thiếu tool call hoặc nhánh điều phối sai.

Nếu chỉ đánh giá response text, trường hợp “đoán trúng” có thể được tính là thành công, che mất lỗi hợp đồng.

### 5.4. Ranh giới khi đánh giá tool calling offline

Dùng test double/sandbox với trạng thái cố định để chạy các ca: tool thành công, `NOT_FOUND`, `403`, timeout, đối số thiếu, lệnh không có quyền, retry và lệnh có tác dụng phụ. Tập test nên chấm *quyết định tool, tham số, trạng thái, diễn giải kết quả* riêng.

Với hệ thống thật, log chi tiết của tool có thể chứa dữ liệu riêng tư. Chỉ lưu dữ liệu cần thiết và dùng tham chiếu đã được phân quyền để phục vụ review.

## 6. Ranh giới với Memory Advisors: ngữ cảnh hội thoại không phải nguồn sự thật

Memory Advisors hỗ trợ mô hình duy trì mạch hội thoại bằng cách nạp một phần lịch sử hoặc thông tin đã được lưu vào lượt gọi hiện tại. Điều này hữu ích với câu tiếp nối:

> Lượt 1: “Hãy giải thích ngắn gọn bằng tiếng Việt.”  
> Lượt 2: “Còn điều kiện hoàn phí thì sao?”

Nếu bộ nhớ hội thoại hoạt động theo mong đợi, model có thể hiểu người dùng vẫn muốn câu trả lời tiếng Việt và “điều kiện hoàn phí” liên quan chủ đề trước đó.

**Memory trả lời:** “Trong cuộc hội thoại này, những gì đã được nói hoặc ưu tiên trước đây có ảnh hưởng gì tới lượt hiện tại?”

**RAG trả lời:** “Tài liệu bên ngoài nào liên quan câu hỏi hiện tại và có thể làm bằng chứng?”

### 6.1. So sánh RAG và Memory Advisors

| Khía cạnh | RAG | Memory Advisors |
| --- | --- | --- |
| Nguồn chính | Kho tài liệu, index, vector store hoặc retriever | Lịch sử/tóm tắt hội thoại, bộ nhớ phiên hoặc chính sách memory |
| Mục đích | Bổ sung bằng chứng nghiệp vụ/tri thức ngoài model | Giữ ngữ cảnh, tham chiếu và sở thích của cuộc trò chuyện |
| Tính hiệu lực | Cần quản lý nguồn, version, quyền và freshness | Cần quản lý conversation ID, phạm vi, thời hạn và khả năng lưu/đọc |
| Rủi ro điển hình | Tìm thiếu, lấy nguồn cũ, truy xuất sai quyền | Lẫn lịch sử người dùng, nhớ sai, ngữ cảnh cũ lấn át câu hiện tại |
| Tiêu chí đánh giá | Retrieval hit@k, groundedness, factual correctness | Context continuity, isolation, retention, fidelity, không rò dữ liệu |
| Giá trị làm chứng cứ | Có thể là nguồn có thẩm quyền sau khi xác minh | Thường chỉ là dấu vết điều người dùng/model từng nói |

Một lời phát biểu **trong hội thoại trước** không tự động trở thành chính sách đúng. Ví dụ người dùng từng nói “Tôi nhớ chính sách là 30 ngày”, còn tài liệu hiện hành ghi 14 ngày; memory nên hỗ trợ hiểu câu hỏi, nhưng không được ghi đè nguồn chính sách xác thực.

### 6.2. Bốn loại lỗi Memory Advisors cần thử

**Lỗi mất ngữ cảnh:** ở lượt tiếp theo, model quên chủ đề vừa trao đổi. Cần kiểm tra phạm vi history, conversation ID và chính sách lưu/nạp.

**Lỗi lẫn phiên:** thông tin của cuộc trò chuyện A xuất hiện trong câu trả lời cho B. Đây có thể là lỗi cách cô lập dữ liệu hoặc quản lý ID; test quyền/isolation là bắt buộc.

**Lỗi nhớ sai:** bản tóm tắt history làm biến dạng yêu cầu, làm câu trả lời sai. Cần đánh giá độ trung thực của nội dung memory được đưa vào prompt.

**Lỗi nhớ quá dài/quá cũ:** history tiêu tốn nhiều token, gây chậm hoặc khiến model dựa vào yêu cầu đã hết hiệu lực. Cần chính sách giới hạn và kiểm tra thứ tự ưu tiên các chỉ dẫn mới.

### 6.3. Memory không thay quyền truy cập và xác minh nghiệp vụ

Không dùng thông tin kiểu “người dùng A đã xác nhận quyền sở hữu đơn trước đây” từ memory như chứng cứ đủ để vượt kiểm tra quyền hiện tại. Tool/backend phải xác thực quyền bằng nguồn tin cậy ở thời điểm thao tác.

Tương tự, memory không phải bộ nhớ giao dịch đáng tin cho trạng thái đơn hàng theo thời gian thực. Nếu trạng thái có thể thay đổi, truy vấn tool/backend ở lượt hiện tại vẫn cần thiết.

### 6.4. Đánh giá hội thoại nhiều lượt

Một dataset multi-turn có thể chứa:

~~~yaml
caseId: MEMORY-THREAD-001
conversationId: synthetic-conversation-A
turns:
  - user: "Giải thích các chính sách sau bằng tiếng Việt, ngắn gọn."
    expectedBehavior: "Ghi nhớ phong cách trả lời trong phạm vi phiên."
  - user: "Gói Pro có thời hạn hoàn phí bao lâu?"
    referenceDocumentId: "policy-v3#refund"
    expectedBehavior: "Trả lời bằng tiếng Việt, dùng đúng nguồn hiện hành."
  - user: "Còn gói Basic?"
    expectedBehavior: "Hiểu chủ đề tiếp nối, truy xuất quy định Basic."
checks:
  - memoryContinuity
  - factualCorrectness
  - sourceCitation
  - noCrossConversationLeak
~~~

Bài test cần chạy **đúng chuỗi lượt** và reset/mô phỏng trạng thái memory giữa các ca theo thiết kế. Chấm độc lập từng câu nếu bỏ history sẽ không kiểm tra được tính liên tục hội thoại.

## 7. Năm ranh giới dữ liệu: từ yêu cầu tới kết luận

Trong thực tế, các thành phần trên nối với nhau qua những ranh giới cần quan sát:

~~~text
[User / API]
   ↓  (1) Request and conversation context
[Core ChatClient]
   ↓  (2) Memory + RAG context
[Model]
   ↔  (3) Tool calls and results
   ↓  (4) Answer, citations, usage
[Evaluation]
   ↔  (5) Execution evidence and telemetry
[Report: quality + operational health]
~~~

Mỗi ranh giới có **đặc tả**, **bằng chứng thực tế** và **phép kiểm** phù hợp:

| Ranh giới | Đặc tả cần rõ | Bằng chứng thu | Ai/cơ chế đánh giá |
| --- | --- | --- | --- |
| API → Core | Schema, phân quyền, format, timeout | Request metadata, response status | Unit/integration test |
| Context → Model | Đúng history, đúng nguồn, đúng phiên | Memory refs, document IDs, prompt assembly metadata | Memory/RAG evaluation |
| Model ↔ Tool | Tool được phép, args, result, side effects | Tool invocation, authorization, hậu điều kiện | Contract/security test |
| Model → Answer | Liên quan, có căn cứ, đúng nghiệp vụ | Answer, citations, context refs | Rubric, evaluator, human |
| Runtime → Monitoring | SLI/SLO, token/cost budget | Metrics, traces, logs, usage | Dashboard/alerts và phân tích |

**Evaluation không cần bắt mọi chi tiết vào một mô hình chấm duy nhất.** Chọn cơ chế đúng với đối tượng: kiểm tra xác định cho schema/quyền/args, kiểm tra có nhãn cho retrieval, rubric hoặc chuyên gia cho ngữ nghĩa, telemetry cho độ trễ và tài nguyên.

## 8. Sơ đồ trách nhiệm khi một kết quả sai

Giả sử chatbot trả lời sai và một request chậm. Đừng sửa prompt ngay lập tức. Hãy đặt câu hỏi tuần tự theo bằng chứng:

~~~mermaid
flowchart TD
    S["Câu trả lời sai hoặc request chậm"] --> A{"Có lỗi API / quyền / schema?"}
    A -- "Có" --> CORE["Core / application integration"]
    A -- "Không" --> B{"Có cần tài liệu ngoài?"}
    B -- "Có" --> R{"Nguồn đúng đã vào prompt?"}
    R -- "Không" --> RAG["RAG / retrieval / context assembly"]
    R -- "Có" --> G["Generation / prompt / model"]
    B -- "Không" --> C{"Có cần dữ liệu động hoặc hành động?"}
    C -- "Có" --> TOOL["Tool selection / backend / result handling"]
    C -- "Không" --> M{"Có phụ thuộc hội thoại cũ?"}
    M -- "Có" --> MEMORY["Memory state / isolation / advisor"]
    M -- "Không" --> G
    CORE --> O["Dùng traces, evidence và regression xác minh"]
    RAG --> O
    G --> O
    TOOL --> O
    MEMORY --> O
~~~

Sơ đồ là hướng **ưu tiên điều tra**, không phải cây quyết định chứng minh nguyên nhân. Một request có thể đồng thời dùng tài liệu, tool và memory; khi đó cần kiểm tra nhiều nhánh cùng lúc dựa trên trace và evidence.

### 8.1. Ma trận chẩn đoán

| Triệu chứng | Phạm vi nghi vấn chính | Bằng chứng cần có |
| --- | --- | --- |
| JSON đầu ra thiếu trường bắt buộc và parser bỏ qua | Core/validation + generation | Output thực, schema, parser/exception |
| RAG không tìm thấy chính sách đang có hiệu lực | Retrieval, index, metadata filter | Retrieved IDs/versions, query, filter |
| RAG tìm đúng nguồn nhưng model vẫn bịa số | Generation/prompt/model | Context thật, answer, rubric groundedness |
| Model gọi nhầm `refundOrder` thay vì `getOrderStatus` | Tool selection + prompt/tool descriptions | Tool name/args, câu hỏi, quyền |
| Tool trả `403` nhưng model nói “thành công” | Tool result interpretation + backend contract | Tool status, answer, traces |
| Câu hỏi tiếp nối quên người dùng muốn tiếng Việt | Memory/Advisor hoặc prompt | Lịch sử, memory injected, answer |
| Dữ liệu phiên A xuất hiện trong phiên B | Memory isolation/authorization | Conversation scope, access records |
| p95 tăng sau khi tăng `top-k` | Retrieval + model input length | Retrieval/model spans, token usage |
| Cost tăng sau khi thêm tool | Tool cycles + model retries | Số model calls, tool events, usage |
| HTTP 200 và traces đẹp nhưng câu sai | Answer quality | Dataset, answer, context, source chuẩn |

## 9. Kết nối các module bằng một bộ dữ liệu đánh giá

Một ca đánh giá có thể đặt yêu cầu cho **nhiều module cùng lúc**, nhưng nên ghi rõ kỳ vọng ở từng ranh giới.

Ví dụ bộ test cho ứng dụng giả định “Sao Mai”:

~~~json
{
  "datasetVersion": "assistant-integration-v1",
  "cases": [
    {
      "caseId": "CORE-FORMAT-001",
      "question": "Hãy trả trạng thái ở định dạng JSON.",
      "checks": ["jsonSchema", "technicalCompletion"]
    },
    {
      "caseId": "RAG-POLICY-001",
      "question": "Gói Pro được hoàn phí trong bao lâu?",
      "expectedDocuments": ["policy-v3#refund"],
      "expectedFacts": ["14 ngày kể từ ngày mua"],
      "checks": ["retrievalHitAtK", "groundedness", "factualCorrectness"]
    },
    {
      "caseId": "TOOL-ORDER-001",
      "question": "Kiểm tra đơn DH-123 của tôi.",
      "expectedTool": "getOrderStatus",
      "expectedToolArgs": {"orderId": "DH-123"},
      "checks": ["authorization", "toolSelection", "toolArgs", "toolResultUse"]
    },
    {
      "caseId": "MEMORY-FOLLOWUP-001",
      "conversationScenario": "Tiếp nối yêu cầu trả lời tiếng Việt ở lượt trước.",
      "checks": ["conversationContinuity", "conversationIsolation"]
    }
  ]
}
~~~

Bộ dữ liệu trên chỉ là **hợp đồng minh họa**, không phải định dạng mặc định Spring AI tự tạo. Ngoài tiêu chí riêng của từng module, cần gắn `runId`, `caseId`, `attemptId`, `traceId`, phiên bản prompt/model/corpus/index/tool/schema/memory và rubric.

### 9.1. Bằng chứng theo từng attempt

~~~json
{
  "runId": "candidate-v2-offline",
  "caseId": "RAG-POLICY-001",
  "attemptId": "candidate-v2-RAG-POLICY-001-1",
  "runtimeVersions": {
    "prompt": "policy-prompt-v4",
    "model": "model-candidate",
    "pipeline": "rag-v2",
    "corpus": "policy-v3",
    "memoryPolicy": "session-history-v1"
  },
  "execution": {
    "retrievedDocumentIds": ["policy-v2#refund"],
    "toolInvocationIds": [],
    "answer": "Gói Pro được hoàn phí trong 30 ngày.",
    "traceId": "trace-rag-policy-001"
  },
  "evaluations": [
    {
      "metric": "retrievalHitAt3",
      "verdict": "FAIL",
      "rubricVersion": "retrieval-rubric-v1"
    },
    {
      "metric": "factualCorrectness",
      "verdict": "FAIL",
      "rubricVersion": "policy-rubric-v1"
    }
  ]
}
~~~

Trong trường hợp này, nếu Spring AI được gọi thành công nhưng retrieval đưa tài liệu cũ, report có thể gợi ý thay đổi **RAG corpus/index/filter**. Không thể chỉ từ hai verdict trên kết luận ChatModel “kém” hoặc Memory Advisors “lỗi”.

### 9.2. Vì sao phải dùng ID đúng loại?

- `caseId` là yêu cầu kiểm thử, có thể lặp lại nhiều lần.
- `attemptId` là một execution cụ thể.
- `traceId` giúp tìm đường đi của execution ở tracing backend.
- `documentId` và version giúp kiểm tra nguồn nào đã được tìm.
- `toolInvocationId` cho biết từng công cụ đã chạy thế nào.
- `rubricVersion`/`judgeVersion` giúp phân biệt ứng dụng thay đổi với bộ chấm thay đổi.

Một request có thể có nhiều lời gọi ChatModel do tool calling và retry. Token/cost phải tính theo các lời gọi thực tế; không coi một trace tương đương đúng một lần gọi model.

## 10. Thiết kế evaluator không lấn sang trách nhiệm module chức năng

Các evaluator trong Spring AI, chẳng hạn `RelevancyEvaluator` và `FactCheckingEvaluator`, hỗ trợ chấm một số khía cạnh ngữ nghĩa của câu trả lời. Tuy nhiên, chúng không thay thế kiểm tra hợp đồng hệ thống.

### 10.1. Chọn phép kiểm theo ranh giới

| Điều cần xác minh | Cách làm nên ưu tiên | Tại sao |
| --- | --- | --- |
| JSON hợp lệ | JSON Schema validator | Xác định, nhanh, không cần model chấm |
| Quyền truy cập | Backend/security integration test | Quyết định bảo mật phải dựa trên chính sách tin cậy |
| Tool arguments | Schema + assertion | So chính xác tên/giá trị |
| Retrieved document IDs | So với nhãn tài liệu | Kiểm được hit@k/Recall@k |
| Answer relevance | Rubric + evaluator/chuyên gia | Cần hiểu ngữ nghĩa |
| Groundedness | Answer + context thật + evaluator/chuyên gia | Phải kiểm sự hỗ trợ của bằng chứng |
| Factual correctness | Answer + nguồn chuẩn đã xác minh | Context truy xuất có thể sai |
| Memory continuity | Multi-turn test + rubric | Cần xem lịch sử qua nhiều lượt |
| Memory isolation | Kiểm thử cô lập/ủy quyền | Không phải chỉ số ngữ nghĩa |
| Latency/cost | Timer/trace/usage/bảng giá | Đây là đo vận hành |

### 10.2. Đừng đưa dữ liệu lý tưởng thay cho thực tế

Khi chấm groundedness của một câu trả lời RAG, nếu thay `retrievedDocuments` của attempt bằng tài liệu chuẩn trong dataset thì sẽ bỏ qua lỗi truy xuất. Tương tự, khi kiểm thử tool calling, đừng dùng `expectedToolResult` làm “kết quả tool thực tế” nếu tool đã trả lỗi; như vậy sẽ làm model trông có vẻ đã được cung cấp dữ liệu đúng.

Phân biệt trong test harness:

~~~text
Expectation:
  expectedDocuments
  expectedTool / expectedArguments
  expectedFacts / expectedBehavior

Actual execution:
  retrievedDocuments
  actualToolInvocations / actualToolResults
  actualAnswer / citations
  trace / usage / timings

Evaluation:
  retrievalVerdict
  toolVerdict
  answerVerdict
  operationalVerdict
~~~

Để tìm nguyên nhân, **không trộn expectation vào actual**.

## 11. Tổ chức kiểm thử tích hợp với Spring AI

### 11.1. Unit và contract tests của từng module

- **Core:** request validation, parser, fallback, cấu hình timeout.
- **RAG:** kiểm tra bộ lọc tài liệu, quyền truy xuất, số lượng và phiên bản document.
- **Tool Calling:** schema, quyền, xử lý lỗi, idempotency, hậu điều kiện.
- **Memory Advisors:** scope theo conversation, reset phiên, không lộ chéo thông tin.
- **Evaluation code:** tính đúng score/rubric, báo lỗi khi thiếu evidence, số mẫu đúng.

Các phép kiểm xác định nên chạy nhanh và không phụ thuộc model ngoài khi có thể.

### 11.2. Integration tests qua luồng đầy đủ

Một ca tích hợp có thể hỏi thông tin đơn hàng cần nhớ ngữ cảnh và gọi tool:

> Lượt 1: “Tôi muốn tất cả câu trả lời bằng tiếng Việt.”  
> Lượt 2: “Đơn DH-123 hiện thế nào?”  
> Backend giả lập: `getOrderStatus("DH-123")` trả `IN_TRANSIT`.

Yêu cầu cùng lúc:

1. Memory giữ được ngôn ngữ mong muốn trong phạm vi hội thoại.
2. Model/dispatcher gọi đúng tool, đúng order ID.
3. Tool backend xác thực quyền rồi trả trạng thái.
4. Model diễn giải `IN_TRANSIT` thành “đang giao”, không tự nói “đã giao”.
5. Telemetry ghi được thời gian và trạng thái của các bước.
6. Evaluation lưu verdict cho từng tiêu chí, không chỉ một điểm tổng.

### 11.3. Mô hình lưu kết quả đơn giản trong Java

Ví dụ sau minh họa cách **giữ tách biệt bằng chứng thực thi với kết quả chấm**. Đây là kiểu dữ liệu do test harness tự định nghĩa, không phải class Spring AI tự sinh.

~~~java
import java.util.List;
import java.util.Map;

public final class EvaluationRecords {

    public record ExecutionEvidence(
            String attemptId,
            String traceId,
            String answer,
            List<String> retrievedDocumentIds,
            List<String> toolNames,
            Map<String, String> safeMetadata) {}

    public record EvaluationVerdict(
            String attemptId,
            String metric,
            String rubricVersion,
            String verdict,
            String reason) {}

    public static EvaluationVerdict checkRetrieval(
            ExecutionEvidence evidence,
            String expectedDocumentId) {

        boolean found = evidence.retrievedDocumentIds()
                .contains(expectedDocumentId);

        return new EvaluationVerdict(
                evidence.attemptId(),
                "retrievalHit",
                "retrieval-rubric-v1",
                found ? "PASS" : "FAIL",
                found ? "Đã tìm nguồn cần thiết" : "Thiếu nguồn cần thiết");
    }

    public static EvaluationVerdict checkToolSelection(
            ExecutionEvidence evidence,
            String expectedTool) {

        boolean called = evidence.toolNames().contains(expectedTool);

        return new EvaluationVerdict(
                evidence.attemptId(),
                "toolSelection",
                "tool-rubric-v1",
                called ? "PASS" : "FAIL",
                called ? "Đã gọi đúng loại tool" : "Không có tool kỳ vọng");
    }
}
~~~

Code trên chỉ kiểm tra **một phần hợp đồng**: có document/tool theo tên. Đánh giá tool đầy đủ cần kiểm tra đối số, thứ tự, số lần gọi, kết quả, quyền và hậu điều kiện. Tương tự, một document đúng ID có thể có nội dung cũ hoặc không thực sự được ghép vào prompt; cần thêm kiểm tra phiên bản và context.

### 11.4. Kiểm thử AI có tính xác suất

Cùng dữ liệu, model có thể tạo lời đáp khác nhau. Đừng cố biến mọi ca thành phép so chuỗi tuyệt đối. Với những ràng buộc xác định, dùng assertions; với ngữ nghĩa, dùng rubric và evaluator đã được kiểm chứng. Khi quyết định phát hành quan trọng, chạy lặp ca khó hoặc dùng mẫu đủ lớn và báo bất định thay vì diễn giải chênh lệch 1–2 điểm từ vài ca.

## 12. Observability là cầu nối điều tra, không phải công cụ sinh câu trả lời

Trong hệ sinh thái Spring AI, cơ chế observation và Micrometer có thể hỗ trợ đo các thành phần `ChatClient`, `ChatModel`, `Advisors`, `VectorStore` và tool calling, tùy phiên bản, provider và cấu hình. Spring Boot Actuator và registry/tracing backend cung cấp đường thu thập/xuất telemetry.

Một trace logic của request có RAG, memory và tool:

~~~text
HTTP POST /chat                                 3.6 s
└── ChatClient                                   3.4 s
    ├── Memory advisor: load conversation       0.1 s
    ├── Retrieval advisor / VectorStore          0.5 s
    ├── ChatModel #1                             1.0 s
    ├── Tool getOrderStatus                       0.7 s
    └── ChatModel #2                             1.1 s
~~~

Thứ tự và tên span chỉ mang tính minh họa. Mỗi span có thể chứa span con; không cộng thời gian cha và con như hai khoản độc lập. Nếu có streaming, cần phân biệt **time to first token** và **total completion latency** khi chúng ảnh hưởng trải nghiệm.

### 12.1. Bốn câu hỏi cần bốn loại dữ liệu

| Câu hỏi | Nguồn dữ liệu phù hợp |
| --- | --- |
| Model trả lời đúng chưa? | Dataset/reference + answer + rubric + reviewer |
| Retriever đã đưa tài liệu gì vào prompt? | Captured document/context evidence |
| Tool đã chạy và thực hiện thay đổi đúng chưa? | Dispatcher events + backend state |
| Request chậm, tốn token hoặc chi phí vì đâu? | Traces, metrics, usage và bảng giá |

**Trace thành công không phải chứng nhận chất lượng**; evaluator PASS cũng không phải chứng nhận phân quyền backend; retrieval hit@k cao không chứng minh model dùng đúng bằng chứng.

### 12.2. Một thay đổi có thể chạm nhiều module

Ví dụ tăng `top-k` từ 3 lên 8 trong RAG:

- Có thể tăng recall của retrieval.
- Có thể kéo dài context, tăng input tokens và chi phí ChatModel.
- Có thể khiến prompt bị cắt do giới hạn context.
- Có thể đưa thêm tài liệu cũ hoặc nhiễu, làm groundedness/factual correctness kém hơn.
- Có thể tăng latency ở VectorStore và ChatModel.
- Nếu có Memory Advisor, context dài hơn còn cạnh tranh với ngân sách token của lịch sử hội thoại.

Vì vậy, cần đánh giá cả chất lượng và vận hành, phân tích từng nhóm case và lưu phiên bản pipeline. Không chỉ dựa vào một metric retrieval hoặc một biểu đồ token.

## 13. Các lỗi xuyên module và thứ tự ưu tiên kiểm tra

### 13.1. Sai chính sách: RAG hay Memory?

Người dùng từng nói “Tôi tưởng hoàn phí trong 30 ngày”, nhưng tài liệu hiện hành quy định 14 ngày. Bot tiếp tục dùng con số 30 ngày.

Thử kiểm tra:

1. Tài liệu nguồn `policy-v3` có được truy xuất và đưa vào prompt chưa?
2. Memory Advisor có đưa lại nhận định “30 ngày” của người dùng không?
3. Prompt có nêu rõ tài liệu chính thức được ưu tiên hơn nhận định trước đó không?
4. Model có chọn sai thông tin ngay cả khi nguồn đúng đã có không?
5. Bộ đánh giá đã so với phiên bản nguồn chính xác chưa?

Không đủ bằng chứng để khẳng định lỗi thuộc RAG hay Memory chỉ từ câu trả lời cuối.

### 13.2. Trả lời trạng thái đơn sai: Tool hay Generation?

Nếu `getOrderStatus` trả `IN_TRANSIT` nhưng chatbot nói “DELIVERED”:

- Tool/backend có thể hoạt động đúng; lỗi nằm ở cách model diễn giải output.
- Hoặc tool thực tế đã trả dữ liệu cũ/sai, cần kiểm tra backend.
- Hoặc attempt không hề gọi tool; model đoán.
- Hoặc history chứa trạng thái cũ và bị ưu tiên hơn kết quả mới.

Vì vậy phải lưu actual tool result và answer của cùng attempt, không chỉ expected result.

### 13.3. Độ trễ tăng: module nào gây ra?

Nếu p95 request tăng từ 2,0 lên 4,0 giây sau khi thêm Memory Advisor và Tool Calling, xem:

- Thời gian tải history và kích thước context.
- Số lời gọi ChatModel trước/sau tool.
- Thời gian tool backend, timeout hoặc retry.
- Thời gian retrieval và số kết quả.
- Input/output token usage theo từng model call.
- Tải, provider rate limit và điều kiện mạng.

Trace giúp hình thành giả thuyết; thực nghiệm có kiểm soát giúp xác nhận nguyên nhân.

### 13.4. Dữ liệu riêng tư bị lộ: không thể chỉ đánh giá ngữ nghĩa

Nếu tài liệu của tenant B xuất hiện ở phiên A, cần sửa chính sách truy cập tại retriever/backend hoặc memory store theo thực tế. LLM judge có thể nhận diện một câu trả lời có nguy cơ lộ dữ liệu, nhưng **kiểm tra quyền phải enforced bằng mã và hệ thống tin cậy**. Cần ca hồi quy truy cập chéo và xác minh không có dữ liệu nhạy cảm lưu ngoài phạm vi trong telemetry.

## 14. Release gates cho hệ thống kết hợp bốn module

Một ứng dụng có nhiều thành phần nên thiết kế **cổng phát hành riêng theo ranh giới** thay vì gom thành một điểm trung bình.

| Gate | Ví dụ điều kiện | Bằng chứng |
| --- | --- | --- |
| Core correctness | Schema/validation/error handling đạt | Unit/integration tests |
| RAG evidence | Hit@k/factuality/groundedness trên dataset đủ mức | IDs, source versions, evaluator verdict |
| Tool contract | Quyền, đối số, side effects và xử lý lỗi đạt | Tool/backend tests |
| Memory isolation | Không lộ history giữa các phiên, giữ đúng context | Multi-turn tests |
| Answer quality | Relevance, correctness, refusal phù hợp | Rubric + dataset + review |
| Operational health | Error rate, latency p95, token/cost trong ngân sách | Metrics, traces, usage |

Ví dụ ngưỡng cho **bài tập giả định**:

~~~yaml
releaseGates:
  core:
    schemaAndAuthorization: must-pass
  rag:
    factualCorrectnessPassRate: ">= 0.98"
    criticalSourceCases: must-pass
  toolCalling:
    authorizationAndIdempotency: must-pass
  memory:
    crossConversationIsolation: must-pass
  aiQuality:
    groundednessPassRate: ">= 0.95"
  operations:
    p95LatencyMs: "<= 2500"
    technicalErrorRate: "<= 0.01"
~~~

Các ngưỡng đều phải xác định theo sản phẩm thật và bộ dữ liệu có chất lượng phù hợp; không phải mặc định hay yêu cầu của Spring AI. Nếu evaluator không chạy được hoặc thiếu bằng chứng, cần báo `UNKNOWN/NOT_EVALUATED`; không tự coi là PASS.

## 15. Ranh giới khi cập nhật prompt, model và pipeline

Khi một phiên bản mới suy giảm, hãy hỏi “thành phần nào đã đổi?” trước khi đưa ra kết luận.

| Thay đổi | Module tác động trực tiếp | Đánh giá cần chạy lại |
| --- | --- | --- |
| Sửa template system/user prompt | Core/generation | Relevance, format, factuality, refusal |
| Đổi model/provider | Core/model | Quality, tool choices, latency, cost |
| Đổi chunk size/embedding | RAG/index | Retrieval và end-to-end answer quality |
| Đổi `top-k`/reranking | RAG/context | Hit@k, groundedness, latency/tokens |
| Đổi tool schema/description | Tool Calling | Selection, args, error handling, downstream answer |
| Đổi tool backend | Tool Calling/business integration | Contracts, quyền, side effects |
| Đổi window/tóm tắt history | Memory Advisors | Multi-turn fidelity, isolation, token budget |
| Đổi rubric/judge | Evaluation | Độ ổn định điểm chấm, hiệu chỉnh so với nhãn chuẩn |
| Đổi telemetry sampling | Observability | Độ bao phủ trace và khả năng so sánh metrics |

Một bản phát hành có thể thay đổi nhiều phần. Để giải thích tác động, lưu `promptVersion`, `modelVersion`, `corpus/indexVersion`, `toolSchemaVersion`, `memoryPolicyVersion`, `pipelineVersion`, `datasetVersion`, `rubricVersion` và điều kiện tải. Nếu thay đồng thời model và judge, pass rate thay đổi chưa chứng minh model tốt/xấu hơn.

## 16. Thực hành: lập bản đồ lỗi tích hợp Spring AI

**Bối cảnh:** tạo chatbot nội bộ giả định dùng Spring AI Core, RAG theo chính sách hoàn phí, Tool Calling đọc trạng thái đơn và Memory Advisors ghi nhớ ngôn ngữ ưu tiên trong cuộc trò chuyện. Tài liệu chính sách có hai phiên bản: `policy-v2` cũ (30 ngày) và `policy-v3` hiện hành (14 ngày).

### 16.1. Tạo bộ case đại diện

| Case | Đầu vào | Kỳ vọng chính |
| --- | --- | --- |
| `CORE-001` | Yêu cầu output JSON | JSON đúng schema |
| `RAG-001` | “Gói Pro hoàn phí trong bao lâu?” | Trả 14 ngày theo `policy-v3` |
| `RAG-002` | “Có được hoàn sau 60 ngày vì ngoại lệ không?” | Không tự bịa ngoại lệ |
| `TOOL-001` | “Trạng thái đơn DH-123?” | Gọi `getOrderStatus` đúng ID, diễn giải kết quả |
| `TOOL-002` | Người không có quyền tra đơn khác | Backend từ chối; không lộ dữ liệu |
| `MEM-001` | Lượt 1 yêu cầu tiếng Việt; lượt 2 hỏi tiếp | Giữ đúng ngữ cảnh/language |
| `MEM-002` | Hai conversation ID khác nhau | Không lẫn lịch sử |
| `INTEGRATION-001` | Hỏi tiếp về đơn cần tool và ngữ cảnh | Memory + tool + answer cùng đạt |

### 16.2. Thu bằng chứng cho từng attempt

Cần ghi:

1. `caseId`, `runId`, `attemptId`, versions của cấu hình.
2. Actual answer và citation IDs.
3. Retrieved documents, versions, rank và context cuối cùng đưa cho model.
4. Tool name, arguments, authorization, result, lỗi và hậu điều kiện phù hợp.
5. Memory reference hoặc snapshot đã xử lý dữ liệu riêng tư được đưa vào lượt hiện tại.
6. Trace ID, timings, token usage và số model/tool calls.
7. Verdict theo từng metric, rubric version, lý do và trạng thái thiếu bằng chứng.

### 16.3. Cố ý tạo ba lỗi trong môi trường kiểm thử

**Lỗi A:** bộ lọc retrieval lấy `policy-v2` thay `policy-v3`. Dự đoán metric nào fail, và dùng document IDs/traces để xác minh.

**Lỗi B:** tool giả lập trả `403` nhưng model vẫn nói “đơn đang giao”. Phân biệt lỗi điều phối/diễn giải với lỗi backend và kiểm tra sự kiện tool.

**Lỗi C:** conversation A muốn trả lời tiếng Việt, nhưng message từ conversation B bị nạp vào A. Kiểm tra conversation isolation và đánh dấu đây là lỗi chức năng/quyền quan trọng.

Sau từng lỗi, sửa đúng thành phần, chạy lại case hồi quy rồi đo tác động lên toàn bộ pipeline.

### 16.4. So sánh hiệu quả thay đổi

Thử tăng `top-k` từ 3 lên 5, giữ các biến khác nếu có thể. Lập báo cáo:

| Câu hỏi | Bằng chứng |
| --- | --- |
| Retrieval tốt hơn không? | Hit@k/Recall@k và document IDs |
| Câu trả lời chính xác hơn không? | Factual correctness/groundedness trên dataset |
| Tool vẫn làm đúng không? | Invocation events, contract tests |
| Memory còn hoạt động đúng không? | Multi-turn cases, isolation tests |
| Request chậm ở đâu? | Span times retrieval/model/tool/memory |
| Chi phí có tăng không? | Input/output tokens, số model calls, giá áp dụng |
| Có thể phát hành không? | Gate theo từng ranh giới, rủi ro và ca hồi quy |

**Tiêu chí hoàn thành:** với mỗi ca fail, báo cáo chỉ ra thành phần nghi vấn, bằng chứng actual, expected, phép kiểm phù hợp và cách kiểm chứng đã sửa. Cần có ít nhất một ví dụ “request trả HTTP 200 nhưng quality FAIL” và một ví dụ “answer đúng nhưng contract tool FAIL”.

## 17. Những hiểu lầm cần tránh

**“RAG tốt thì câu trả lời chắc chắn đúng.”** RAG chỉ cung cấp ngữ cảnh; model vẫn có thể diễn giải sai, context có thể lỗi thời hoặc tài liệu không đủ.

**“Memory cũng là RAG nên dùng cùng metric.”** Cả hai có thể nạp context, nhưng Memory chủ yếu lưu lịch sử hội thoại còn RAG truy xuất nguồn tri thức. Đánh giá memory cần multi-turn continuity, isolation và tính trung thực của history, ngoài correctness của câu trả lời.

**“Tool Calling do model quyết định nên model chịu trách nhiệm bảo mật.”** Model có thể đề xuất tool; backend phải kiểm tra quyền, điều kiện nghiệp vụ và hậu điều kiện trước/đúng lúc thực thi.

**“Core trả response thành công nghĩa là tính đúng của phần mềm và nội dung đều đạt.”** Thành công giao tiếp không chứng minh hợp đồng hành vi, sự thật hay quyền truy cập.

**“Có trace nghĩa là đã chứng minh groundedness.”** Trace cho thấy các bước thực thi; groundedness cần answer và context thực sự cung cấp.

**“Một evaluator PASS đủ cho mọi module.”** Relevance không thay kiểm tra factual correctness, retrieval, tool authorization, memory isolation hay độ trễ.

**“Chỉ cần sửa prompt để khắc phục mọi lỗi.”** Lỗi index stale, backend authorization, session isolation hay retry idempotency cần được khắc phục tại phần có trách nhiệm.

**“Muốn đánh giá đầy đủ phải log mọi nội dung.”** Cần thu bằng chứng tối thiểu, có phân quyền và chính sách retention; tránh đưa raw prompt, tài liệu nhạy cảm hoặc user ID vào metric labels. Nếu không thể lưu bằng chứng nội dung, phải nêu giới hạn của phép chấm.

## 18. Ghi nhớ

- **Core** là nền gọi model và điều phối lời nhắn; **RAG** bổ sung bằng chứng; **Tool Calling** nối model với dữ liệu động/hành động; **Memory Advisors** duy trì ngữ cảnh hội thoại.
- **Evaluation** đánh giá đúng/sai theo dataset và rubric; **Observability** đo cách hệ thống thực thi, lỗi, latency, token và chi phí.
- Một ca fail cần được truy ngược bằng `caseId → attemptId → documents/memory/tool/model evidence → evaluator verdict → traceId` để phân biệt lỗi.
- Groundedness phải dựa trên **context thực tế**; factual correctness phải dựa trên **nguồn chuẩn đã được xác minh**. Một trong hai không tự thay thế cái còn lại.
- Bảo mật tool, phân quyền tài liệu và cô lập memory là hợp đồng phải **thực thi bằng phần mềm đáng tin**, bên cạnh đo lường và cảnh báo.
- Đánh giá phiên bản mới phải xem **chất lượng đầu ra, tính đúng hành vi và sức khỏe vận hành** trên cùng một phạm vi đo có phiên bản rõ.

### Tài liệu tham khảo chính thức

- [Spring AI — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html)
- [Spring AI — Chat Model API](https://docs.spring.io/spring-ai/reference/api/chatmodel.html)
- [Spring AI — Advisors API](https://docs.spring.io/spring-ai/reference/api/advisors.html)
- [Spring AI — Retrieval Augmented Generation](https://docs.spring.io/spring-ai/reference/api/retrieval-augmented-generation.html)
- [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI — Chat Memory](https://docs.spring.io/spring-ai/reference/api/chat-memory.html)
- [Spring AI — Evaluation Testing](https://docs.spring.io/spring-ai/reference/api/testing.html)
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/)
