# Quan sát mô hình: Giới hạn dữ liệu được cung cấp bởi mô hình cục bộ hoặc endpoint tương thích

## 1. Vì sao telemetry có thể không đầy đủ?

Khi chuyển từ API mô hình được quản lý sang model chạy trên máy cá nhân, máy chủ nội bộ hoặc gateway tương thích OpenAI, ứng dụng thường vẫn gọi được model qua Spring AI. Tuy nhiên, **khả năng gửi và nhận request không đồng nghĩa với khả năng quan sát giống nhau**.

Một endpoint có thể trả văn bản và hỗ trợ streaming nhưng không trả token usage. Endpoint khác trả input/output token count nhưng không có rate-limit headers, cache breakdown, reasoning metadata hoặc model revision. Một số runtime trả thời gian nạp model và xử lý prompt; server khác chỉ trả thời gian HTTP tổng. Một trường có trong response native cũng chưa chắc được adapter ánh xạ vào metadata chuẩn của Spring AI.

Bài học thuộc chương **Quan sát mô hình** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để tìm nguyên nhân thay đổi qua các phiên bản prompt, model và pipeline.

Mục tiêu là phân biệt **trường nào provider cam kết, trường nào adapter chuyển đổi, trường nào chỉ có ở API riêng và trường nào không được cung cấp**. Nếu không phân biệt các nguồn này, dashboard có thể hiển thị số 0 giả, so sánh hai model theo hai định nghĩa khác nhau hoặc kết luận sai về chi phí và chất lượng.

Sau bài học, bạn có thể:

- Phân biệt local deployment, OpenAI-compatible và observability support.
- Hiểu dữ liệu chuẩn trong **ChatResponseMetadata**, **Usage** và **ChatGenerationMetadata**.
- Đọc token counts, finish reason, model identity và runtime timings từ Ollama.
- Hiểu giới hạn của OpenAI-compatible endpoint khi dùng **OpenAiChatModel**.
- Phân biệt trường thiếu, số 0, giá trị fallback và trường không được adapter ánh xạ.
- Đọc usage trong streaming mà không cộng lặp các chunks.
- Tách model telemetry khỏi HTTP, GPU, CPU, memory và chi phí hạ tầng.
- Thiết kế contract tests để xác minh khả năng thực tế của từng server.
- Kết hợp telemetry với relevance, fact checking và dataset để đánh giá pipeline RAG.

## 2. Bốn khả năng độc lập: local, compatible, streaming và observability

Spring AI 2.1.0 có bảng so sánh Chat Models với các cột riêng cho streaming, retry, observability, local deployment và OpenAI API compatibility. Đây là các khả năng độc lập; không thể suy ra một cột từ cột khác.

| Khả năng | Câu hỏi cần trả lời | Điều không thể suy ra |
| --- | --- | --- |
| **Local** | Model có thể chạy trên máy hoặc hạ tầng do đội ngũ quản lý không? | Không có nghĩa API trả đủ metrics |
| **OpenAI-compatible** | Service có chấp nhận một phần giao thức/JSON của OpenAI API không? | Không có nghĩa mọi field, option và error semantics giống OpenAI |
| **Streaming** | Server có thể gửi response theo nhiều phần không? | Không có nghĩa chunk nào cũng mang usage hoặc finish reason |
| **Observability** | Adapter Spring AI có instrument model operation và cung cấp metrics/traces không? | Không có nghĩa mọi trường native của server đều được xuất |

Ví dụ trong bảng Spring AI 2.1.0:

- **Ollama** được đánh dấu có hỗ trợ local, OpenAI-compatible, streaming và observability.
- **DeepSeek qua OpenAI proxy** được đánh dấu hỗ trợ local deployment và OpenAI compatibility trong bảng so sánh; cách triển khai cụ thể vẫn phụ thuộc model/server bạn chọn.
- **Groq** được đánh dấu OpenAI-compatible nhưng không phải local deployment; **Mistral, NVIDIA và Perplexity** cũng có thể được dùng qua tích hợp tương thích với những giới hạn riêng.
- **Amazon Bedrock Converse** có observability trong adapter Bedrock, nhưng không phải OpenAI-compatible endpoint.

Bảng mô tả mức hỗ trợ của các tích hợp Spring AI. Nó không phải cam kết mọi server cùng nhóm có response metadata giống nhau. Khi triển khai, cần kiểm tra cả model adapter, server/runtime, model version và cấu hình endpoint.

## 3. Ba lớp dữ liệu: native response, Spring AI metadata và host telemetry

~~~mermaid
flowchart TD
    SERVER["Local runtime / compatible inference server"]
    SERVER --> RAW["Native response / HTTP headers"]
    RAW --> ADAPTER["Spring AI provider adapter"]
    ADAPTER --> NORMAL["ChatResponse / Usage / Generation metadata"]
    SERVER --> HOST["Host and runtime metrics"]
    NORMAL --> APP["Application observations and metrics"]
    HOST --> APP
    RAW --> CONTRACT["Contract tests and raw fixtures"]
    CONTRACT --> APP
~~~

### 3.1. Native response

Đây là những trường server gửi qua HTTP hoặc SDK, ví dụ:

- **prompt_eval_count**, **eval_count** và **done_reason** của Ollama.
- **reasoning_content** của một số inference server tương thích OpenAI.
- **thought_signature** hoặc extra fields trong tool-call payload.
- **load_duration**, **eval_duration** và thông tin runtime khác.
- Các HTTP headers riêng của gateway.

Native response là bằng chứng về những gì server đã gửi. Nhưng dữ liệu chỉ hữu ích nếu client/adapter giữ lại và ứng dụng có cách truy cập.

### 3.2. Spring AI metadata

Spring AI cung cấp giao diện chung như:

- **ChatResponseMetadata**: response ID, model, rate limit, usage và prompt metadata.
- **Usage**: prompt tokens, completion tokens, total tokens và native usage nếu adapter hỗ trợ.
- **ChatGenerationMetadata**: finish reason và finish reason category.
- **ChatModel observations**: thời lượng model operation và các thuộc tính theo convention.

Adapter có thể chuẩn hóa một số trường, bỏ qua trường khác hoặc chuyển dữ liệu riêng vào metadata. Hai provider có cùng **ChatResponse** type không có nghĩa chúng cung cấp cùng mức chi tiết.

### 3.3. Host/runtime telemetry

Các dữ liệu sau thường nằm ngoài **ChatResponse**:

- CPU utilization, GPU utilization và GPU memory.
- RAM, VRAM, disk I/O và network throughput.
- Số model đang được nạp, số request đang chờ và queue depth.
- Container throttling, process restart, OOM và lỗi driver.
- Điện năng, chi phí máy chủ và mức sử dụng phần cứng.

**gen_ai.client.operation** đo thao tác model ở tầng Spring AI. Nó không tự động trở thành bộ giám sát GPU hoặc hệ điều hành. Muốn điều tra tài nguyên local, cần exporter hoặc telemetry riêng của host, container và inference runtime.

## 4. Đọc dữ liệu chuẩn từ ChatResponse

Spring AI cung cấp **ChatResponseMetadata** để đọc metadata mà provider adapter đã ánh xạ:

~~~java
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.ai.chat.model.ChatResponse;

ChatResponse response = chatModel.call(prompt);

ChatResponseMetadata metadata = response.getMetadata();

String responseId = metadata.getId();
String reportedModel = metadata.getModel();
Usage usage = metadata.getUsage();

Integer inputTokens = usage != null
        ? usage.getPromptTokens()
        : null;

Integer outputTokens = usage != null
        ? usage.getCompletionTokens()
        : null;

Integer totalTokens = usage != null
        ? usage.getTotalTokens()
        : null;
~~~

Đoạn code minh họa đường đọc metadata chung. Các getter có thể không có giá trị hữu ích nếu provider không gửi thông tin hoặc adapter không hỗ trợ mapping tương ứng.

### 4.1. Phân biệt raw finish reason và category

**ChatGenerationMetadata** chứa raw finish reason theo tên provider và category chuẩn hóa:

~~~java
import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.ai.chat.metadata.FinishReasonCategory;

ChatGenerationMetadata generationMetadata =
        response.getResult().getMetadata();

String rawFinishReason = generationMetadata.getFinishReason();

FinishReasonCategory category =
        generationMetadata.getFinishReasonCategory();
~~~

Các category chung trong Spring AI gồm:

| Category | Ý nghĩa |
| --- | --- |
| **COMPLETED** | Model hoàn tất câu trả lời |
| **TRUNCATED** | Câu trả lời bị cắt do giới hạn độ dài/token |
| **TOOL_CALL** | Model yêu cầu thực thi tool |
| **FILTERED** | Safety filter hoặc refusal dừng câu trả lời |
| **OTHER** | Raw reason không có nghĩa chung giữa các provider hoặc Spring AI chưa nhận diện |
| **UNSPECIFIED** | Provider không cung cấp lý do |

Raw finish reason vẫn cần được lưu khi điều tra provider cụ thể. Category giúp tổng hợp liên provider, nhưng không thể giữ toàn bộ ngữ nghĩa native.

Một provider có thể dùng cùng raw reason STOP cho cả câu trả lời bình thường và tool call. Adapter có thể cần xem cả response payload để phân loại chính xác. Vì vậy không nên viết quy tắc chung kiểu “finish reason stop thì luôn COMPLETED”.

## 5. Ollama: dữ liệu runtime có thể giàu hơn usage chuẩn

Ollama cung cấp API chat native và API tương thích OpenAI. Spring AI có adapter riêng **OllamaChatModel**, đồng thời có thể dùng **OpenAiChatModel** để gọi Ollama qua endpoint tương thích.

API native của Ollama có thể trả những trường sau trong response cuối:

| Trường Ollama | Ý nghĩa | Đơn vị |
| --- | --- | --- |
| **model** | Tên model được sử dụng | Chuỗi |
| **created_at** | Thời điểm tạo response | Timestamp |
| **done** | Đã kết thúc response/stream hay chưa | Boolean |
| **done_reason** | Lý do kết thúc theo runtime | Chuỗi |
| **prompt_eval_count** | Số token prompt được xử lý | Token |
| **eval_count** | Số token output được sinh | Token |
| **total_duration** | Thời gian xử lý tổng theo runtime | Nanosecond |
| **load_duration** | Thời gian nạp model | Nanosecond |
| **prompt_eval_duration** | Thời gian xử lý prompt | Nanosecond |
| **eval_duration** | Thời gian sinh output | Nanosecond |

Các trường này là **Ollama API fields**, không phải bộ trường bắt buộc của OpenAI-compatible protocol.

### 5.1. Cách đọc thời gian và tốc độ sinh token

Giả sử một response mẫu có:

~~~json
{
  "model": "llama3.2",
  "done": true,
  "done_reason": "stop",
  "prompt_eval_count": 800,
  "eval_count": 120,
  "total_duration": 4200000000,
  "load_duration": 300000000,
  "prompt_eval_duration": 700000000,
  "eval_duration": 2800000000
}
~~~

Đây là dữ liệu giả lập để minh họa. Từ đó có thể tính:

~~~text
Prompt tokens       = 800
Output tokens       = 120

Load duration       = 0.30 giây
Prompt eval         = 0.70 giây
Generation duration = 2.80 giây
Total duration      = 4.20 giây

Output tokens/second =
    eval_count / eval_duration * 1,000,000,000
  = 120 / 2,800,000,000 * 1,000,000,000
  ≈ 42.86 tokens/second
~~~

Không lấy **eval_count / total_duration** rồi gọi đó là tốc độ generation nếu muốn so sánh với công thức runtime Ollama. **total_duration** có thể bao gồm thời gian load và xử lý khác. Hãy giữ nguyên tên metric và công thức khi so sánh.

### 5.2. Dedicated OllamaChatModel ánh xạ dữ liệu nào?

Với **OllamaChatModel**, Spring AI chuyển token counts thành **Usage** chuẩn. Adapter cũng đưa một số thông tin runtime vào **ChatResponseMetadata** dưới dạng key-value metadata, ví dụ:

- **created-at**
- **total-duration**
- **load-duration**
- **prompt-eval-duration**
- **eval-duration**
- **prompt-eval-count**
- **eval-count**
- **done**

Tên key và cách ánh xạ là chi tiết adapter. Khi nâng Spring AI, cần kiểm tra API/source của đúng version thay vì giả định các key này sẽ giống ở mọi provider.

Có thể đọc các trường metadata theo kiểu an toàn:

~~~java
import java.time.Duration;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;

ChatResponse response = ollamaChatModel.call(prompt);
ChatResponseMetadata metadata = response.getMetadata();

Object loadValue = metadata.get("load-duration");
Object promptEvalValue = metadata.get("prompt-eval-duration");
Object evalValue = metadata.get("eval-duration");
Object totalValue = metadata.get("total-duration");

Duration loadDuration =
        loadValue instanceof Duration d ? d : null;
Duration promptEvalDuration =
        promptEvalValue instanceof Duration d ? d : null;
Duration evalDuration =
        evalValue instanceof Duration d ? d : null;
Duration totalDuration =
        totalValue instanceof Duration d ? d : null;
~~~

Không ép mọi metadata value thành **Duration**: provider khác có thể không có key này hoặc dùng kiểu dữ liệu khác.

### 5.3. Ollama stream: thống kê thường nằm ở final chunk

Ollama streaming API gửi các JSON objects theo thời gian. Những chunk trung gian thường chứa message delta và **done=false**; response cuối có **done=true** và có thể mang token counts, durations cùng finish reason.

~~~mermaid
sequenceDiagram
    participant App as Spring AI application
    participant O as Ollama runtime
    App->>O: POST /api/chat stream=true
    O-->>App: chunk 1, message delta, done=false
    O-->>App: chunk 2, message delta, done=false
    O-->>App: chunk 3, message delta, done=false
    O-->>App: final chunk, done=true, usage and timing
    App->>App: Aggregate message and metadata
~~~

Khi quan sát streaming:

- Không giả định mỗi chunk đều có **prompt_eval_count** hoặc **eval_count**.
- Không cộng các giá trị usage lặp lại nếu chúng là số cộng dồn của response.
- Không kết luận token usage bằng 0 khi subscriber hủy trước final chunk.
- Nếu dùng **MessageAggregator** hoặc đường tổng hợp của adapter, đọc response cuối đã tổng hợp theo contract của adapter.
- Nếu tự xử lý raw Ollama stream, giữ trạng thái **USAGE_PENDING** cho tới khi nhận final event.

### 5.4. Local runtime timings không phải host metrics

**load_duration** giúp nhận diện thời gian nạp model, còn **prompt_eval_duration** và **eval_duration** giúp tách prefill khỏi generation. Nhưng các số liệu này không cho biết đầy đủ:

- GPU utilization trung bình và peak.
- VRAM còn trống hoặc memory fragmentation.
- CPU throttling hoặc số thread thực sự chạy.
- Queue depth và thời gian request chờ trước khi được xử lý.
- Tình trạng nhiều model cạnh tranh cùng tài nguyên.

Để hiểu vì sao một local model chậm, cần ghép response metadata với host/container/runtime metrics. Một model call có thể chậm do model load, context dài, phần cứng bận hoặc queueing; chỉ nhìn **total_duration** không đủ phân biệt.

## 6. OpenAI-compatible endpoint: giao thức chung nhưng semantics riêng

Spring AI cho phép cấu hình **OpenAiChatModel** trỏ tới một endpoint khác OpenAI, ví dụ Ollama, vLLM hoặc inference gateway. Trong Spring Boot, cấu hình base URL và model có thể có dạng:

~~~properties
spring.ai.openai.base-url=http://localhost:8000
spring.ai.openai.api-key=
spring.ai.openai.chat.model=meta-llama/Llama-3-8B-Instruct
~~~

Một số local server yêu cầu hậu tố **/v1**; URL chính xác phải theo tài liệu của server. Empty API key chỉ phù hợp khi server thực sự không yêu cầu authentication.

### 6.1. extraBody chuyển tham số riêng của server

Một server có thể hỗ trợ **top_k**, **repetition_penalty**, **min_p** hoặc **num_predict** dù OpenAI API chuẩn không định nghĩa các trường đó.

Spring AI cung cấp **extraBody** để gửi các tham số này:

~~~java
import java.util.Map;
import org.springframework.ai.openai.OpenAiChatOptions;

OpenAiChatOptions options = OpenAiChatOptions.builder()
        .model("llama3.2")
        .extraBody(Map.of(
                "num_predict", 100,
                "top_k", 40,
                "repeat_penalty", 1.1
        ))
        .build();

ChatResponse response = openAiChatModel.call(
        new Prompt("Tóm tắt nội dung sau...", options));
~~~

**extraBody** được làm phẳng vào top-level JSON request. Spring AI không xác thực các key này theo schema của inference server; chúng được gửi tới server. Vì vậy:

- Key đúng với vLLM chưa chắc đúng với Ollama.
- Một server có thể bỏ qua key không hỗ trợ.
- Server khác có thể trả HTTP 400.
- Không dùng **extraBody** với API OpenAI chính thức nếu gửi các trường không được API chấp nhận.

### 6.2. OpenAI-compatible không có nghĩa mọi response field giống nhau

Một server có thể tương thích ở request/response cơ bản nhưng khác về:

- Usage fields và cách tính input/output tokens.
- **finish_reason** và cách biểu diễn safety/refusal.
- Tool call IDs, tool argument deltas và extra payload.
- Reasoning content.
- JSON mode hoặc provider-native structured output.
- Multimodal input/output.
- Rate-limit headers.
- Error body, retryable status và timeout behavior.

Ví dụ, một server có thể trả **reasoning_content**, server khác không trả dù cả hai chạy reasoning-capable model. Một số endpoint yêu cầu replay reasoning trong hội thoại tiếp theo; endpoint khác từ chối trường đó và trả HTTP 400.

**API-compatible là mức tương thích giao thức, không phải cam kết tương đương chức năng hoặc telemetry.**

## 7. Những giới hạn thường gặp ở endpoint tương thích

### 7.1. Token usage không được trả hoặc không được ánh xạ

Một số inference server không trả **usage** trong response; một số chỉ trả usage ở final stream chunk; một số trả field riêng như **prompt_eval_count** và **eval_count**.

Khi adapter không nhận được usage:

- **ChatResponseMetadata.getUsage()** có thể thiếu hoặc chỉ có dữ liệu fallback.
- **gen_ai.client.token.usage** có thể không tăng.
- Timer model operation vẫn có thể được ghi.
- Dashboard token không tăng không chứng minh model không tiêu token.

Nếu cần thống kê usage, hãy kiểm tra response raw và mapping của adapter. Đừng tự ước lượng token từ số ký tự rồi lưu như số provider đã báo.

### 7.2. Finish reason không nhất quán

Một server có thể dùng **stop**, server khác dùng **end_turn**, **length**, **tool_calls** hoặc giá trị riêng. Có trường hợp **stop** chỉ nói stream đã dừng, không nói tại sao dừng theo nghĩa nghiệp vụ.

Spring AI có **FinishReasonCategory** để chuẩn hóa những trường hợp có thể phân loại. Tuy nhiên, nếu provider không gửi finish reason hoặc adapter không biết cách diễn giải, category có thể là **UNSPECIFIED** hoặc **OTHER**.

Hãy lưu cả raw reason và category. Khi provider có tool-call fields hoặc refusal fields riêng, kiểm tra adapter có dùng chúng để phân loại hay không.

### 7.3. Reasoning content có thể thiếu hoặc không thể replay

Với OpenAI-compatible server, **reasoning_content** là trường do inference server quyết định có xuất hay không. Spring AI có thể ánh xạ trường này thành **ReasoningPart**, nhưng không thể tạo ra dữ liệu mà server không gửi.

Có hai tình huống quan trọng:

- Một số endpoint reasoning như DeepSeek thinking mode yêu cầu gửi lại reasoning content trong assistant history; thiếu field có thể bị HTTP 400.
- Một số endpoint khác như Groq từ chối **reasoning_content**; khi đó cần tắt replay qua thuộc tính **spring.ai.openai.chat.replay-reasoning-content=false**.

Nếu reasoning không có, không kết luận model không reasoning. Có thể server ẩn nội dung, chỉ trả token count, không hỗ trợ trường hoặc adapter không ánh xạ.

### 7.4. Tool call có thể cần extra fields

Một số OpenAI-compatible provider thêm trường vào tool-call object. Ví dụ Google Gemini OpenAI-compatible endpoint có thể gửi **thought_signature** trong extra payload; field này cần được giữ khi gửi tiếp lịch sử tool call.

Spring AI có cơ chế giữ extra properties ở tool-call object trong **OpaquePayload** và replay chúng ở request sau. Tuy nhiên, tài liệu giới hạn cơ chế này cho extra fields **trên tool-call object**; extra fields nằm sâu bên trong nested function object không được bảo toàn theo cùng cách.

Khi một tool loop hoạt động ở lượt đầu nhưng HTTP 400 ở lượt tiếp theo, hãy kiểm tra tool-call history và provider-specific payload, không chỉ xem tên function và arguments.

### 7.5. Rate-limit metadata có thể không có

**ChatResponseMetadata.getRateLimit()** chỉ hữu ích khi provider/server trả headers tương ứng và adapter ánh xạ chúng. Một local server có thể không có quota hoặc rate-limit headers theo contract chung.

Spring AI dùng **EmptyRateLimit** khi thông tin rate limit không khả dụng; các accessor của nó trả 0. Cần kiểm tra **instanceof EmptyRateLimit** trước khi diễn giải số 0 là hạn mức thật hoặc số request còn lại bằng 0.

Gateway nội bộ có thể áp quota riêng dù model chạy local. Nếu gateway có rate limit, cần instrument ở tầng gateway hoặc cung cấp adapter metadata tương ứng.

### 7.6. Cache metrics có thể không được chuẩn hóa

Trong Spring AI 2.1.0, bảng usage cache metrics đánh dấu Ollama là không hỗ trợ unified cache read/write getters. Điều đó nói về **mapping trong adapter**, không chứng minh runtime không có bất kỳ cơ chế cache nội bộ nào.

Không gán **cacheReadTokens = 0** chỉ vì **getCacheReadInputTokens()** không có dữ liệu. Nếu runtime có trường cache riêng, đọc native metadata hoặc runtime API, rồi lưu với nguồn dữ liệu riêng.

## 8. Bảng giới hạn dữ liệu và cách diễn giải

| Nhóm dữ liệu | Có thể có ở local/compatible server? | Giới hạn thường gặp | Cách xử lý |
| --- | --- | --- | --- |
| Model name | Có | Có thể là alias hoặc tag latest | Lưu requested model và reported model |
| Model digest/revision | Tùy runtime | Không phải ChatResponse nào cũng có | Lưu digest/runtime version từ model inventory |
| Prompt/output tokens | Tùy API | Có thể thiếu hoặc chỉ có ở final chunk | Ghi REPORTED, MISSING hoặc PARTIAL |
| Total tokens | Tùy API/adapter | Có thể được Spring AI tính từ input + output | Lưu cách tính và nguồn |
| Finish reason | Tùy response | Raw values khác nhau | Lưu raw reason và normalized category |
| Reasoning content | Tùy model/server/parser | Có thể bị ẩn hoặc không hỗ trợ | Không suy ra từ nội dung rỗng |
| Tool call metadata | Tùy server | Extra fields có thể cần replay | Contract test multi-turn tool loop |
| HTTP status/error | Tùy transport | Error body có schema riêng | Thu HTTP span/log đã redaction |
| Rate limits | Tùy server/gateway | Có thể không có header | Phân biệt EmptyRateLimit với quota thật |
| Cache read/write | Tùy runtime/adapter | Unified getters có thể null | Giữ UNKNOWN, kiểm tra native API |
| Load/prefill/generation duration | Một số local runtime có | Tên, đơn vị và điểm bắt đầu khác nhau | Ghi provider-native timing riêng |
| CPU/GPU/VRAM | Không nằm trong ChatResponse chung | Cần host/runtime exporter | Ghép theo timestamp/instance |
| Pricing/billing | Local thường không có billing token | Compute cost nằm ở hạ tầng | Ước tính từ thời gian/tài nguyên và bảng giá nội bộ |

## 9. Java: tạo snapshot telemetry có provenance

Một lớp ứng dụng nên giữ **giá trị** cùng **trạng thái dữ liệu** và **nguồn dữ liệu**. Ví dụ sau minh họa cách đọc một response mà không ép trường thiếu thành số 0:

~~~java
import java.time.Duration;

import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.ai.chat.metadata.ChatResponseMetadata;
import org.springframework.ai.chat.metadata.EmptyRateLimit;
import org.springframework.ai.chat.metadata.EmptyUsage;
import org.springframework.ai.chat.metadata.FinishReasonCategory;
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.ai.chat.model.ChatResponse;

public record ModelTelemetry(
        String requestedModel,
        String reportedModel,
        Integer inputTokens,
        Integer outputTokens,
        Integer totalTokens,
        String rawFinishReason,
        FinishReasonCategory finishCategory,
        Duration loadDuration,
        Duration promptEvalDuration,
        Duration evalDuration,
        Duration totalDuration,
        boolean usageReported,
        boolean rateLimitReported) {

    public static ModelTelemetry from(
            String requestedModel,
            ChatResponse response) {

        ChatResponseMetadata metadata = response.getMetadata();
        Usage usage = metadata.getUsage();

        ChatGenerationMetadata generation =
                response.getResult().getMetadata();

        Integer input = usage != null ? usage.getPromptTokens() : null;
        Integer output = usage != null ? usage.getCompletionTokens() : null;
        Integer total = usage != null ? usage.getTotalTokens() : null;
        boolean usageReported = usage != null && !(usage instanceof EmptyUsage);

        if (!usageReported) {
            input = null;
            output = null;
            total = null;
        }

        return new ModelTelemetry(
                requestedModel,
                metadata.getModel(),
                input,
                output,
                total,
                generation.getFinishReason(),
                generation.getFinishReasonCategory(),
                duration(metadata, "load-duration"),
                duration(metadata, "prompt-eval-duration"),
                duration(metadata, "eval-duration"),
                duration(metadata, "total-duration"),
                usageReported,
                !(metadata.getRateLimit() instanceof EmptyRateLimit)
        );
    }

    private static Duration duration(
            ChatResponseMetadata metadata,
            String key) {

        Object value = metadata.get(key);
        return value instanceof Duration duration ? duration : null;
    }
}
~~~

Đây là ví dụ cho Spring AI 2.1.x với các metadata key runtime của Ollama. Với provider khác, các key duration có thể không tồn tại; **null** là kết quả đúng khi không có dữ liệu.

### 9.1. Thêm trạng thái usage rõ ràng

Nếu ứng dụng cần phân tích coverage, hãy lưu thêm trạng thái:

~~~java
public enum DataStatus {
    REPORTED,
    PARTIAL,
    MISSING,
    FALLBACK,
    INVALID
}
~~~

Gợi ý phân loại:

| Trạng thái | Khi sử dụng |
| --- | --- |
| REPORTED | Provider/adapter trả đủ trường theo contract |
| PARTIAL | Có một số trường nhưng thiếu trường khác |
| MISSING | Không có trường hoặc không có usage object |
| FALLBACK | Adapter hoặc ứng dụng tự thay giá trị mặc định |
| INVALID | Giá trị sai kiểu, âm hoặc vi phạm ràng buộc |

**EmptyUsage** và **EmptyRateLimit** có các getter trả 0. Nếu không kiểm tra loại object, dashboard có thể nhầm fallback với số liệu thật. Với adapter khác, null từ raw response có thể được chuyển thành 0 trước khi tạo Usage; cần kiểm tra mapping của version đang chạy.

## 10. Streaming: lấy metadata đúng thời điểm

### 10.1. Không phải mọi chunk đều có usage

Ollama native stream gửi message deltas trước. Final chunk có thể mang usage và durations. Một OpenAI-compatible endpoint khác có thể không gửi usage cuối, hoặc chỉ gửi khi bật tùy chọn riêng của server.

Một ứng dụng streaming nên theo dõi:

- Thời điểm bắt đầu subscribe.
- Thời điểm nhận chunk đầu tiên có text.
- Các text/reasoning/tool-call deltas.
- Final chunk hoặc terminal event.
- onComplete, onError và cancel.
- Usage status cuối cùng.

### 10.2. Không cộng usage nếu chunk chứa số tích lũy

Giả sử một server phát cùng số prompt_tokens trên nhiều chunk hoặc chỉ phát usage ở final event. Nếu cộng mọi chunk, bạn sẽ đếm trùng.

Cách xử lý:

1. Xác định usage trong chunk là **delta** hay **cumulative**.
2. Chỉ cộng delta khi contract nói đó là delta.
3. Nếu usage chỉ có ở final chunk, đọc final chunk hoặc aggregate response.
4. Nếu stream bị cancel trước final event, đánh dấu PARTIAL hoặc MISSING.
5. Không suy ra usage từ số ký tự hoặc số chunks.

### 10.3. Đo TTFT và full duration riêng

**total_duration** của Ollama không giống TTFT. TTFT là khoảng thời gian từ khi bắt đầu request/subscribe tới chunk đầu tiên có nội dung người dùng nhìn thấy.

~~~text
request_started_at
first_visible_chunk_at
stream_completed_at

TTFT = first_visible_chunk_at - request_started_at
Full stream duration = stream_completed_at - request_started_at
~~~

Nếu stream không có chunk hiển thị, TTFT có thể là null hoặc trạng thái không hoàn tất. Đừng ghi 0.

## 11. Metrics và traces: dữ liệu chung vẫn có thể thiếu

Spring AI có thể tạo model observation **gen_ai.client.operation** và token counter **gen_ai.client.token.usage** cho các provider được hỗ trợ. Metric model duration vẫn có thể tồn tại khi token usage không được provider trả.

| Telemetry | Có thể quan sát ở Spring AI | Giới hạn |
| --- | --- | --- |
| Model operation duration | Có ở adapter có observability | Không tự chia load/prefill/generation |
| Model/provider tags | Có | Model tag có thể là alias |
| Input/output/total token counter | Khi usage có dữ liệu | Không có usage thì counter không tăng |
| Finish reason | Khi adapter nhận và ánh xạ | Raw reason có thể khác provider |
| HTTP request span | Phụ thuộc adapter/transport | Không suy ra mọi local endpoint dùng cùng HTTP span name |
| Host/GPU metrics | Không phải model observation chung | Cần exporter riêng |
| Cache metrics | Phụ thuộc provider mapping | Không có getter không đồng nghĩa cache runtime không tồn tại |

### 11.1. Tách model operation khỏi endpoint request

Một request của người dùng có thể gọi model nhiều lần do tool loop, retry hoặc evaluator. Cũng có thể một model operation tạo nhiều HTTP attempts do retry nội bộ SDK.

Khi làm dashboard:

- ChatClient operation: đếm workflow ở tầng framework.
- gen_ai.client.operation: đếm model invocations.
- HTTP client observation: đếm HTTP attempts nếu adapter có instrument.
- spring.ai.tool: đếm tool executions.
- Host metrics: đo tài nguyên runtime/instance.

Không dùng số model calls thay cho số user requests. Không cộng duration parent-child. Không so HTTP attempt count của hai provider nếu một bên có HTTP instrumentation riêng còn bên kia không có.

### 11.2. Theo dõi usage coverage

Một counter ứng dụng có thể giúp thấy bao nhiêu model calls thực sự có usage:

~~~text
application.model.usage.calls{status="REPORTED"}
application.model.usage.calls{status="PARTIAL"}
application.model.usage.calls{status="MISSING"}
application.model.usage.calls{status="FALLBACK"}
~~~

Các tên trên là metric do ứng dụng tự định nghĩa, không phải metric mặc định Spring AI. Dùng tags có cardinality thấp như provider, model_family, transport và status; tránh request ID, user ID hoặc raw model alias do người dùng nhập.

Nếu counter được xuất thành **application_model_usage_calls_total** với label **provider** và **status**, có thể tính tỷ lệ calls có usage như sau:

~~~promql
sum by (provider) (
  rate(application_model_usage_calls_total{status="REPORTED"}[5m])
)
/
sum by (provider) (
  rate(application_model_usage_calls_total{
    status=~"REPORTED|PARTIAL|MISSING|FALLBACK"
  }[5m])
)
~~~

Đây là tỷ lệ coverage của bộ đếm ứng dụng, không phải metric có sẵn của Spring AI. Nếu mẫu số bằng 0 hoặc không có series, dashboard phải hiển thị “không đủ dữ liệu” thay vì 0%.

## 12. Kiểm thử contract cho từng endpoint

Đừng chỉ kiểm thử rằng **chatModel.call()** trả về một chuỗi. Hãy kiểm tra contract dữ liệu mà pipeline quan sát cần.

### 12.1. Bộ fixture response

| Fixture | Nội dung cần có |
| --- | --- |
| Success đầy đủ | Model name, usage, finish reason, response ID |
| Success thiếu usage | Text có nhưng không có input/output counts |
| Usage một phần | Chỉ có input hoặc output |
| Finish reason không chuẩn | Raw reason riêng của server |
| Tool call | Tool-call ID, name, arguments và extra fields nếu có |
| Reasoning | Có/không có reasoning_content hoặc native thinking |
| Stream hoàn tất | Các delta và final usage event |
| Stream hủy | Chỉ có một phần chunks, không có final event |
| HTTP error | Status code và error body của server |
| Rate limit | Có/không có rate-limit headers |

### 12.2. Ví dụ kiểm tra usage không bị giả thành 0

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.metadata.EmptyUsage;
import org.springframework.ai.chat.metadata.Usage;

class UsageCoverageTest {

    @Test
    void distinguishesMissingUsageObject() {
        Usage usage = new EmptyUsage();

        assertThat(usage.getPromptTokens()).isZero();
        assertThat(usage.getCompletionTokens()).isZero();

        // Zero từ EmptyUsage không phải bằng chứng provider
        // thực sự đã báo một lượt tiêu thụ bằng zero.
        assertThat(usage).isInstanceOf(EmptyUsage.class);
    }
}
~~~

Test này xác nhận semantics của EmptyUsage; integration test cần xác minh adapter/server thật có trả usage hay không.

### 12.3. Contract test cho endpoint tương thích

Với local inference server hoặc gateway, kiểm tra:

1. Request body có các trường chuẩn mà server yêu cầu.
2. extraBody có được chuyển tới đúng top-level key không.
3. Server phản hồi HTTP 400 khi nhận một key không hỗ trợ hay bỏ qua nó.
4. ChatResponseMetadata.getModel() có phản ánh model được báo hay chỉ là alias cấu hình.
5. Usage có đủ prompt/output/total hay không.
6. Finish reason được ánh xạ đúng category.
7. Tool-call history có giữ các extra fields cần thiết không.
8. Streaming có final usage event không.
9. Timeout, retry và HTTP errors được quan sát đúng.
10. RateLimit/Cache fields có dữ liệu hay chỉ là placeholder.

Nếu dùng Testcontainers hoặc Docker Compose, có thể chạy inference server trong môi trường CI để kiểm tra contract ở mỗi lần nâng phiên bản. Giữ lại raw fixture đã redaction để so sánh thay đổi response schema.

## 13. Xây capability matrix theo server thực tế

Một bảng cấu hình nên ghi rõ khả năng đã kiểm thử thay vì chỉ ghi tên model:

| Provider/endpoint | Transport | Usage | Finish reason | Stream usage | Reasoning | Tool extras | Host metrics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ollama native | Ollama API | Prompt/eval counts nếu response có | done_reason | Final event | Thinking tùy model/runtime | Tool fields theo API | Exporter host/runtime |
| Ollama OpenAI-compatible | OpenAI Chat Completions | Phụ thuộc compatibility mapping | Raw reason tùy server | Phụ thuộc server | Có thể có reasoning field | Có thể khác native API | Exporter host/runtime |
| vLLM | OpenAI-compatible | Theo cấu hình/version server | Theo API/parser | Theo streaming contract | Có parser thì có thể trả reasoning | Extra fields tùy version | vLLM + host metrics |
| DeepSeek endpoint | OpenAI-compatible | Theo response/API model | Theo provider | Theo endpoint | Thinking mode có thể yêu cầu replay | Theo API contract | Provider/gateway metrics |
| Custom gateway | Contract riêng | Do gateway chuyển tiếp/chuẩn hóa | Do gateway chuyển tiếp/chuẩn hóa | Do gateway | Có thể redaction/loại bỏ | Có thể mất payload | Gateway exporter |

Bảng là mẫu để điền bằng kết quả integration test. Không coi các ô “tùy server” là lỗi; đó là lời nhắc cần xác minh trước khi đưa field vào dashboard hoặc cost calculation.

## 14. Gắn model identity và runtime version vào kết quả

Tên model có thể là alias hoặc tag di động như latest. Khi model local được cập nhật, cùng alias có thể trỏ tới weights, quantization hoặc template khác.

Nên lưu tối thiểu:

- provider: ollama, vllm, custom gateway...
- endpoint_id: tên cấu hình endpoint, không phải URL chứa secret.
- requested_model: model string gửi trong request.
- reported_model: model string server trả về.
- model_digest hoặc revision nếu runtime cung cấp.
- quantization và context settings nếu có.
- runtime_version: phiên bản Ollama/vLLM/gateway.
- spring_ai_version: phiên bản adapter.
- prompt_version, retriever_version, dataset_version.
- transport: native provider API hay OpenAI-compatible.

Những trường này giúp phân biệt suy giảm chất lượng do prompt, weights, quantization, runtime hoặc adapter upgrade.

## 15. Liên hệ với relevance, fact checking và chi phí RAG

Model telemetry cho biết một lần gọi sử dụng bao nhiêu token và mất bao lâu theo số liệu được cung cấp. Nó **không đánh giá** câu trả lời có liên quan, có căn cứ hay có đúng sự thật.

Khi so sánh một local model với endpoint tương thích, giữ cùng dataset và rubric:

| Chỉ số | Nguồn | Câu hỏi |
| --- | --- | --- |
| Input/output tokens | Provider usage hoặc adapter mapping | Mỗi model call dùng bao nhiêu token? |
| Prompt eval/generation duration | Runtime native metadata nếu có | Thời gian nằm ở prefill hay decode? |
| P95/P99 latency | Model observations | Phân phối thời gian có thay đổi không? |
| Relevance pass rate | Relevancy evaluator | Câu trả lời có tập trung vào câu hỏi không? |
| Fact-check pass rate | Grounding/evaluator dataset | Các khẳng định có được hỗ trợ bởi nguồn không? |
| Retrieval coverage | Vector store/retrieval traces | Context có chứa tài liệu cần thiết không? |
| Host resource usage | CPU/GPU/memory exporter | Model có bị giới hạn tài nguyên không? |
| Estimated compute cost | Bảng giá nội bộ và runtime metrics | Chi phí local cho mỗi case là bao nhiêu? |

Với local model, có thể không có hóa đơn theo token. Nhưng chi phí không bằng 0: cần tính chi phí máy chủ/GPU, điện năng, khấu hao, vận hành và concurrency. Hãy ghi rõ đó là **ước lượng nội bộ**, không phải provider billing.

Một pipeline RAG có thể có nhiều model calls: embedding, answer, tool call, judge và fact-check. Usage của answer không tự bao gồm các lượt judge hoặc embedding độc lập. Tách role trước khi cộng tổng chi phí cho một evaluation case.

## 16. Các lỗi diễn giải thường gặp

| Triệu chứng | Kết luận sai dễ gặp | Cách hiểu đúng |
| --- | --- | --- |
| getUsage() thiếu | Model không dùng token | Provider/adapter không cung cấp usage |
| Token count bằng 0 | Request miễn phí hoặc prompt rỗng | Kiểm tra EmptyUsage, fallback và raw response |
| Không có cache getter | Runtime không dùng cache | Adapter không map unified cache metrics |
| Không có rate-limit headers | Server không giới hạn request | Gateway có thể áp quota riêng |
| HTTP 200 | Câu trả lời đúng | Chỉ chứng minh HTTP request thành công |
| finish_reason=stop | Câu trả lời luôn hoàn chỉnh | Xem tool calls, refusal và provider mapping |
| Không có reasoning content | Model không reasoning | Server có thể ẩn hoặc không xuất trường |
| Stream không có usage | Stream không tiêu token | Final event có thể thiếu hoặc subscriber hủy sớm |
| total_duration cao | Model decode chậm | Có thể do load, prefill, queue hoặc host contention |
| Model name không đổi | Weights không đổi | Alias có thể trỏ tới revision khác |
| Không thấy GPU metrics trong trace | Model không dùng GPU | Host metrics nằm ngoài ChatResponse |
| Endpoint OpenAI-compatible | Mọi option hoạt động như OpenAI | Server có subset và extension riêng |
| Tool call lần đầu chạy được, lượt tiếp theo lỗi | Tool schema sai | Có thể mất provider-specific payload trong history |

## 17. Quy trình điều tra khi telemetry local thiếu

1. Xác định adapter đang dùng: OllamaChatModel, OpenAiChatModel với local base URL hay custom provider.
2. Ghi phiên bản Spring AI, runtime và model revision.
3. Lưu một raw response fixture đã redaction từ call thành công.
4. Kiểm tra các trường raw có trong response hay không.
5. Kiểm tra adapter có ánh xạ trường đó vào ChatResponseMetadata, Usage hoặc ChatGenerationMetadata không.
6. Với streaming, kiểm tra final chunk và trạng thái subscriber.
7. Phân biệt null, EmptyUsage, EmptyRateLimit, fallback và số 0 được provider báo.
8. Kiểm tra HTTP status, retry, timeout và error schema.
9. Bổ sung host/runtime metrics nếu cần điều tra CPU/GPU/memory.
10. Chạy contract tests trước khi thay đổi dashboard hoặc cost model.
11. Gắn usage_status và telemetry_source vào bản ghi evaluation.
12. Chỉ kết luận “không có dữ liệu” hoặc “server không hỗ trợ” khi đã kiểm tra cả native response và adapter mapping.

## 18. Bài tập thực hành

### Bài 1. So sánh Ollama native và OpenAI-compatible

Chạy cùng model Ollama qua OllamaChatModel và OpenAiChatModel trỏ tới endpoint tương thích. So sánh ChatResponseMetadata, Usage, finish reason, runtime durations và trace attributes. Ghi lại trường nào có ở một đường gọi nhưng thiếu ở đường còn lại.

### Bài 2. Kiểm tra streaming final chunk

Gọi Ollama bằng stream=true. Ghi các chunk trung gian và final event. Xác nhận token counts/durations chỉ xuất hiện ở đâu, rồi so sánh với response aggregate của Spring AI. Thử cancel trước final event và kiểm tra usage status.

### Bài 3. Endpoint vLLM với extraBody

Cấu hình top_k, repetition_penalty và một custom key bằng extraBody. Xác minh server chấp nhận, bỏ qua hay từ chối key không hợp lệ. Ghi rõ request options nào là chuẩn và options nào là extension của server.

### Bài 4. Reasoning và multi-turn history

Dùng một endpoint có reasoning mode và một endpoint không hỗ trợ reasoning. Kiểm tra AssistantMessage.getReasoning(), replay reasoning ở lượt tiếp theo và hành vi HTTP 400 khi field bắt buộc bị thiếu hoặc bị endpoint từ chối. Không dùng sự vắng mặt của reasoning text làm thước đo chất lượng.

### Bài 5. Tool-call extra payload

Dùng endpoint tương thích có extra field như thought_signature. Thực hiện tool loop nhiều lượt, xác minh payload còn trong assistant message history và được gửi lại. Thử fixture mất extra fields để quan sát lỗi.

### Bài 6. Usage coverage dashboard

Tạo metrics ứng dụng cho REPORTED, PARTIAL, MISSING, FALLBACK. So sánh token usage theo provider nhưng chỉ tính mean/cost trên tập có coverage hợp lệ. Hiển thị coverage bên cạnh token totals.

### Bài 7. RAG evaluation

Chạy cùng dataset với một local model và một hosted/compatible endpoint. Giữ prompt, retriever, topK, judge model và rubric cố định. So relevance, fact-check pass rate, latency, input/output usage và host resources. Giải thích trường hợp token usage thiếu mà vẫn có model duration.

## 19. Tổng kết

Khi dùng mô hình cục bộ hoặc endpoint tương thích, giới hạn quan trọng nhất là **dữ liệu quan sát phụ thuộc vào response contract và adapter mapping**:

- Local deployment, OpenAI compatibility, streaming và observability là các khả năng độc lập.
- ChatResponseMetadata, Usage và ChatGenerationMetadata chỉ cung cấp dữ liệu mà provider/adapter đã trả và ánh xạ.
- Ollama có thể trả token counts và runtime durations ở final response; các trường đó không thay thế host/GPU telemetry.
- OpenAI-compatible endpoint có thể hỗ trợ một phần giao thức, nhưng reasoning, tool payload, usage, finish reason và extra parameters vẫn phụ thuộc server.
- null, EmptyUsage, EmptyRateLimit, fallback và số 0 phải được phân biệt.
- Không có token usage hoặc cache fields không có nghĩa model không tiêu thụ tài nguyên.
- Để so sánh local model và endpoint tương thích, hãy lưu model/runtime versions, chạy contract tests và công khai coverage của telemetry.
- Kết hợp vận hành với relevance, fact checking, retrieval coverage và dataset để đánh giá chất lượng thực.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — Chat Models Comparison](https://docs.spring.io/spring-ai/reference/api/chat/comparison.html): các cột observability, local deployment, streaming và OpenAI API compatibility.
- [Spring AI 2.1.0 — Ollama Chat](https://docs.spring.io/spring-ai/reference/api/chat/ollama-chat.html): OllamaChatModel, cấu hình, streaming, reasoning và structured output.
- [Spring AI 2.1.0 — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): local OpenAI-compatible endpoint, extraBody, reasoning content, tool-call extra properties và HTTP observations.
- [Spring AI 2.1.0 — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): ChatResponseMetadata, Usage, RateLimit, EmptyRateLimit và cache usage support.
- [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): ChatClient/ChatModel observations, metrics, token usage và privacy defaults.
- [Ollama API — Chat completion](https://github.com/ollama/ollama/blob/main/docs/api.md): native response fields, streaming final event, prompt/eval counts và runtime durations.
- [Ollama API — OpenAPI schema](https://github.com/ollama/ollama/blob/main/docs/openapi.yaml): schema của chat/generate response và các trường runtime.
