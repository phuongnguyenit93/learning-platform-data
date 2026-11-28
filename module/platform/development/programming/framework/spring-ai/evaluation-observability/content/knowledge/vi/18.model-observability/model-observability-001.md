# Quan sát mô hình: Phép quan sát thao tác ChatModel theo nhà cung cấp

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring AI có thể dùng OpenAI để tạo câu trả lời, Anthropic làm mô hình đối chiếu, Ollama để thử nghiệm tại chỗ hoặc một provider khác để chạy tác vụ chuyên biệt. Khi người dùng phản ánh rằng ứng dụng chậm, chi phí tăng hoặc chất lượng suy giảm, cần biết **lượt gọi ChatModel nào chậm hoặc lỗi, nó đi tới nhà cung cấp nào và tiêu thụ bao nhiêu tài nguyên**.

Spring AI dựa trên Micrometer Observation để theo dõi các thao tác AI. Ở tầng mô hình chat, các implementation có hỗ trợ instrumentation tạo observation mang tên `gen_ai.client.operation` khi thực hiện `ChatModel.call(...)` hoặc `ChatModel.stream(...)`. Observation có thể sinh **metrics** để tổng hợp thời gian, lưu lượng, token và **traces** để xem trình tự các bước của một request.

Bài này nằm trong chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`, nơi việc đo metrics, traces, chi phí và độ trễ được kết hợp với dataset, đánh giá relevance, fact checking và kiểm thử RAG/tool calling. Mục tiêu không chỉ là xem biểu đồ provider mà còn là **dùng quan sát để truy nguyên các thay đổi giữa phiên bản prompt, model và pipeline**.

Sau bài học, bạn có thể:

1. Phân biệt quan sát ở tầng `ChatClient`, `ChatModel`, advisor, tool và HTTP.
2. Hiểu các thuộc tính provider/model, operation, latency, lỗi và token usage.
3. Bật Micrometer/Actuator/Prometheus/tracing trong Spring Boot và thực hiện lời gọi `ChatModel` có instrument.
4. So sánh hoạt động của nhiều nhà cung cấp mà không nhầm metadata thiếu với số 0.
5. Đọc truy vấn PromQL và trace để phân tích các nguyên nhân latency/chi phí.
6. Kết hợp observability với bộ đánh giá chất lượng RAG và giữ an toàn dữ liệu nội dung.

## 2. Tầng ChatModel nằm ở đâu trong luồng xử lý?

`ChatClient` là API tiện lợi để dựng prompt và điều phối advisor; `ChatModel` là API phía dưới để tương tác với model của provider. Một request có thể được quan sát ở nhiều tầng:

~~~mermaid
flowchart TD
    U["User request hoặc một case đánh giá"] --> C["ChatClient: spring.ai.chat.client"]
    C --> AD["Advisor / RAG / tool"]
    AD --> CM["ChatModel: gen_ai.client.operation"]
    CM --> SDK["Provider SDK / transport"]
    SDK --> P["AI provider / inference server"]
    C --> OBS["ObservationRegistry"]
    AD --> OBS
    CM --> OBS
    OBS --> MET["MeterRegistry: metrics"]
    OBS --> TR["Tracer: spans và trace"]
    MET --> PROM["Prometheus / dashboard"]
    TR --> BACK["OTLP / trace backend"]
~~~

Sơ đồ biểu diễn một **luồng điển hình**, không bắt buộc tất cả thành phần luôn tồn tại. Khi gọi thẳng `ChatModel.call(...)` sẽ không có span `ChatClient`. Với tool calling, mô hình có thể được gọi nhiều lượt; với RAG, vector store và advisor cũng phát sinh observation. Một số SDK/provider không tạo span HTTP ở cùng vị trí.

| Tầng | Observation thường gặp | Vấn đề được đo |
| --- | --- | --- |
| `ChatClient` | `spring.ai.chat.client` | Độ trễ lời gọi client, bao gồm các bước xử lý liên quan |
| `ChatModel` | `gen_ai.client.operation` | Độ trễ thực thi model theo provider/model, request và response metadata |
| Advisor | `spring.ai.advisor` | Thời gian và cấu hình advisor như retrieval hoặc memory |
| Tool calling | `spring.ai.tool` | Thời gian xử lý và tình trạng thao tác công cụ |
| Vector store | `db.vector.client.operation` | Thao tác query/add/delete với kho vector |
| HTTP/SDK | Ví dụ `okhttp.requests` khi provider hỗ trợ | Trạng thái giao tiếp HTTP, network hoặc request tới gateway |

**Không cộng tất cả duration trong một trace** để ra tổng thời gian trả lời: các span thường lồng nhau, nên cộng sẽ bị đếm trùng. Nếu muốn so sánh tốc độ **lượt gọi mô hình**, hãy dùng duration của `gen_ai.client.operation`; nếu muốn đo thời gian phản hồi **mà người dùng thấy**, phải đo ở tầng request/client bao trùm toàn bộ pipeline.

### 2.1. Hai ý nghĩa khác nhau của gen_ai.system

Trong Spring AI 2.1.0, ở `spring.ai.chat.client`, khóa `gen_ai.system` mang giá trị `spring_ai`: đây là **framework client**.

Ở `gen_ai.client.operation`, `gen_ai.system` mang tên **provider do implementation xác định**. Vì thế, khi xem độ trễ “theo nhà cung cấp”, chọn metric/span của `ChatModel`, không nhóm nhãn `gen_ai.system=spring_ai` từ tầng `ChatClient` rồi kết luận tất cả model thuộc cùng provider.

## 3. Nội dung của một ChatModel observation

Theo tài liệu observability của Spring AI 2.1.0, observation `gen_ai.client.operation` được ghi khi gọi `call(...)` hoặc `stream(...)` của `ChatModel` và đo khoảng thời gian thao tác hoàn tất.

~~~text
ChatModel.call(prompt)
    |
    +-- Observation: gen_ai.client.operation
         gen_ai.operation.name = chat
         gen_ai.system = <provider>
         gen_ai.request.model = <requested-model>
         |
         +-- Provider execution
         |    gen_ai.response.model = <reported-model>
         |    gen_ai.response.id = <nếu có>
         |    gen_ai.usage.*_tokens = <nếu có>
         |
         +-- Duration + error / trace context
~~~

Đây là **sơ đồ thuộc tính**, không phải log được tạo nguyên văn. Thuộc tính có thực sự xuất hiện hay không phụ thuộc model implementation, provider API và đường xuất telemetry.

### 3.1. Low-cardinality key: dùng cho metrics và traces

| Khóa observation | Ý nghĩa | Sử dụng |
| --- | --- | --- |
| `gen_ai.operation.name` | Loại thao tác, với model chat thường là `chat` | Lọc riêng chat, không lẫn embedding/image |
| `gen_ai.system` | Provider do model instrumentation báo cáo | So sánh operation/latency/token giữa provider |
| `gen_ai.request.model` | Model được yêu cầu | Phân tích theo cấu hình model |
| `gen_ai.response.model` | Model được báo trong phản hồi | Nhận diện alias, gateway hoặc model thực tế |

Tên model trong request và response **có thể khác** nếu sử dụng alias hoặc routing. Một số provider không báo đủ metadata; không nên tự điền giá trị theo suy đoán.

Các low-cardinality key có thể thành **nhãn metrics**. Do đó tránh đưa request ID, order ID, email, user ID hay nguyên prompt vào đây: giá trị quá đa dạng gây bùng nổ số chuỗi thời gian trong Prometheus và có thể lộ thông tin nhạy cảm.

### 3.2. High-cardinality key: thông tin chi tiết trong traces

Các thuộc tính sau được Spring AI Reference liệt kê cho `ChatModel`:

| Nhóm | Ví dụ thuộc tính |
| --- | --- |
| Tham số model | `gen_ai.request.temperature`, `gen_ai.request.top_p`, `gen_ai.request.max_tokens`, `gen_ai.request.top_k` |
| Stream | `gen_ai.request.stream`, khi có |
| Kết quả | `gen_ai.response.id`, `gen_ai.response.finish_reasons` |
| Token | `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens` |
| Provider cache | `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens` |
| Tool definitions | `spring.ai.model.request.tool.names` |

Không phải provider nào cũng hỗ trợ tất cả tham số hay metadata. `top_k` có thể không tồn tại với một model; token cache có thể không được trả cho từng request; một phản hồi lỗi có thể không chứa usage.

Trong Micrometer, thuộc tính high-cardinality chủ yếu dùng **traces**, không mặc nhiên thành nhãn của timer. Nếu muốn tổng hợp số token trong Prometheus, hãy dùng **metric token usage chuyên dụng** thay vì mong rằng `gen_ai.usage.input_tokens` là một label của timer.

### 3.3. Duration và lỗi nói gì?

- Operation duration cho biết **mất bao lâu ở tầng gọi model**, không phải toàn bộ thời gian truy xuất RAG.
- Nếu model call ném exception, quan sát có thể gắn error/exception theo Micrometer instrumentation.
- Một phản hồi HTTP thành công vẫn có thể **hallucinate** hoặc trượt tiêu chí relevance.
- `RelevancyEvaluator.isPass() == false` là kết quả đánh giá nội dung, **không đồng nghĩa** provider call lỗi.

Cần có hai nhóm số liệu độc lập: **operational health** và **answer quality**.

## 4. Quan sát theo nhà cung cấp: điểm chung và khác biệt

Provider là đối tượng được gắn vào `gen_ai.system` của một `ChatModel` đã instrument. Nhưng cùng quy ước observation không đảm bảo mọi provider có cùng các trường usage, HTTP span hoặc chế độ stream.

| Provider | Điều nên quan sát | Những điều cần xác minh |
| --- | --- | --- |
| **OpenAI** | Model operation, duration, request/response model, usage khi báo cáo | HTTP-layer `okhttp.requests`, async stream, token cache, các lỗi HTTP |
| **Anthropic** | Model operation, token/response metadata khi có | Cách provider tính cache tokens và việc sử dụng async client tùy chỉnh |
| **Ollama** | Lượt gọi model chạy local, request model và độ trễ | Cold start, model loading, mức độ có sẵn usage, cấu hình local server |
| **Azure OpenAI** | Model operation của implementation tương ứng | Deployment alias, model phản hồi, region, quota, endpoint |
| **Custom/other provider** | Tùy mức tích hợp của lớp `ChatModel` | Có `ObservationRegistry`, convention, handlers và tracing hay không |

Đây là **danh sách kiểm tra**, không phải cam kết rằng mọi phiên bản SDK/provider hỗ trợ đầy đủ mọi thuộc tính. Khi triển khai, kiểm tra phiên bản Spring AI, starter và metadata trả về của chính model đang dùng.

### 4.1. HTTP spans theo provider có thể khác

Tài liệu Spring AI 2.1.0 nêu OpenAI và Anthropic còn có HTTP-layer observations `okhttp.requests`. Với gọi đồng bộ, có thể thấy HTTP span dưới `gen_ai.client.operation`; riêng **OpenAI streaming** có hạn chế quan hệ cha-con vì đường gọi async chuyển thread. Một số cách cấu hình Anthropic async client cũng có ngoại lệ.

Vì vậy:

- **Có model span nhưng thiếu HTTP child span** không nhất thiết chứng minh request không gửi đi.
- HTTP status, retry và trace context cần được xác minh với SDK/provider được cấu hình.
- Không trộn duration của HTTP attempt với duration của operation nếu chúng lồng nhau.
- Đối với provider tự viết hoặc không dùng OkHttp, tên/khả năng xuất HTTP span có thể khác hoàn toàn.

### 4.2. Provider metadata chưa chắc tương đương nhau

Hai provider có thể khác về cách đếm input/output, cached tokens, thinking tokens, cách hoàn tất stream và response model name. Lượt gọi lỗi hoặc stream bị hủy có thể không có usage.

Vì thế, khi so sánh “chi phí token giữa provider A và B”, phải ghi rõ phần dữ liệu **có được báo cáo** và phần **không có**. Không biến “usage missing” thành 0 để rồi kết luận model tiết kiệm hơn.

## 5. Bật Micrometer Observation trong ứng dụng Spring Boot

Trong ứng dụng Spring Boot, Spring AI phối hợp với `ObservationRegistry`, Micrometer và Actuator. Muốn xem metrics hoặc traces, ứng dụng cần đúng starter và exporter.

Ví dụ dependencies Gradle cho **Spring Boot 4.x / Spring AI 2.1.x**:

~~~groovy
dependencies {
    implementation 'org.springframework.ai:spring-ai-starter-model-openai'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Nếu muốn xuất traces bằng OpenTelemetry/OTLP trên Boot 4.x.
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Đoạn trên **giả định** dự án đã dùng BOM quản lý phiên bản tương thích. Nếu chạy Spring Boot 3.x hoặc phiên bản khác, phải dùng dependencies tracing/OTLP tương ứng của phiên bản đó; không áp dụng một cách máy móc cấu hình của Boot 4.

Ví dụ `application.yml`:

~~~yaml
spring:
  application:
    name: spring-ai-evaluation-observability
  ai:
    model:
      chat: openai
    openai:
      chat:
        options:
          model: example-model-id

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
~~~

Ở đây `example-model-id` là **placeholder phải đổi thành model hợp lệ**. Khóa API được cung cấp an toàn qua biến môi trường `SPRING_AI_OPENAI_API_KEY` hoặc secret management phù hợp, không đưa khóa thật vào ví dụ hay repository. Tỷ lệ sampling `1.0` chỉ thuận tiện cho **môi trường học/thử nghiệm**; production thường cần sampling thấp hơn hoặc chiến lược phù hợp lưu lượng.

Cấu hình trên không tự tạo Prometheus server, Grafana hay trace backend. Trên Boot 4.x, xem nhóm cấu hình `management.opentelemetry.tracing.export.otlp.*` của tài liệu chính thức để kết nối exporter OTLP với nơi nhận traces.

### 5.1. Ba điều kiện để thấy telemetry

1. **Instrumentation thật sự chạy:** gọi `ChatModel` của provider đã được tích hợp observation. Mock/stub không được instrument có thể không có model span.
2. **Registry/exporter:** metrics cần meter registry; tracing cần tracer/bridge và nơi nhận.
3. **Endpoint hoặc backend có thể truy cập:** Prometheus cần scrape ứng dụng, trace collector phải nhận dữ liệu.

Chỉ thêm `spring-boot-starter-actuator` không tự bảo đảm dashboard ngoài ứng dụng đã có dữ liệu. Đặc biệt với `ChatModel` được tạo thủ công ngoài Spring Boot auto-configuration, cần xác minh `ObservationRegistry` có được truyền vào builder hoặc được liên kết đúng chưa.

### 5.2. Lưu ý khi bật Actuator

Không nên mở mọi endpoint actuator công khai. `/actuator/prometheus` có thể chứa thông tin công nghệ nội bộ, tên model và provider; chỉ cho hệ thống giám sát được phép truy cập. Quản lý khóa provider bằng environment hoặc secret manager; không ghi trực tiếp trong file bài học, log hoặc code ví dụ.

## 6. Ví dụ Java: gọi ChatModel và xem Usage

Khi muốn xem rõ vòng đời một model operation, có thể inject `ChatModel` và gọi trực tiếp:

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.stereotype.Service;

@Service
public class ObservedChatService {

    private final ChatModel chatModel;

    public ObservedChatService(ChatModel chatModel) {
        this.chatModel = chatModel;
    }

    public String answer(String question) {
        ChatResponse response = chatModel.call(new Prompt(question));

        if (response == null
                || response.getResult() == null
                || response.getResult().getOutput() == null) {
            throw new IllegalStateException("ChatModel không trả phản hồi");
        }

        if (response.getMetadata() != null) {
            Usage usage = response.getMetadata().getUsage();
            if (usage != null) {
                Integer input = usage.getPromptTokens();
                Integer output = usage.getCompletionTokens();
                Integer total = usage.getTotalTokens();

                // Có thể dùng cho báo cáo chi phí của ứng dụng.
                // KHÔNG tự tăng lại token counter đã được Spring AI ghi.
                inspectUsage(input, output, total);
            }
        }

        return response.getResult().getOutput().getText();
    }

    private void inspectUsage(
            Integer input, Integer output, Integer total) {
        // Đây là vị trí minh họa để xử lý metadata an toàn.
    }
}
~~~

Spring AI có `ChatResponseMetadata.getUsage()` và các getter `getPromptTokens()`, `getCompletionTokens()`, `getTotalTokens()`. Nếu provider không trả dữ liệu, không được diễn giải giá trị thiếu là “0 token”.

Khi model bean được instrument, lời gọi `chatModel.call(...)` là đường tạo `gen_ai.client.operation`. Mã `inspectUsage(...)` không có tác dụng đo tự động: Spring AI đã có metric token usage riêng cho những provider báo cáo usage. Nếu tự tăng lần nữa trong cùng registry, số liệu có thể bị **đếm trùng**.

### 6.1. Khi dùng ChatClient thay vì ChatModel trực tiếp

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.stereotype.Service;

@Service
public class ObservedChatClientService {

    private final ChatClient client;

    public ObservedChatClientService(ChatClient.Builder builder) {
        this.client = builder.build();
    }

    public String answer(String question) {
        ChatResponse response = client.prompt()
                .user(question)
                .call()
                .chatResponse();

        if (response == null || response.getResult() == null) {
            throw new IllegalStateException("Không có ChatResponse");
        }
        return response.getResult().getOutput().getText();
    }
}
~~~

Ở cấu hình phù hợp, lời gọi này có **ChatClient observation** và **ChatModel observation**. Thêm advisor, tool và vector store có thể xuất thêm span. Vì các span lồng nhau, cần dùng đúng tầng để đo latency và tránh cộng trùng.

### 6.2. Nhiều provider trong cùng ứng dụng

Nếu có nhiều bean `ChatModel`, hãy phân biệt rõ vai trò:

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class AnswerAndJudgeModels {

    private final ChatModel answerModel;
    private final ChatModel judgeModel;

    public AnswerAndJudgeModels(
            @Qualifier("answerChatModel") ChatModel answerModel,
            @Qualifier("judgeChatModel") ChatModel judgeModel) {

        this.answerModel = answerModel;
        this.judgeModel = judgeModel;
    }
}
~~~

Ví dụ **giả định bean đã được khai báo** ở chỗ khác. `gen_ai.system` chỉ phân biệt provider chứ không tự nói một lượt gọi đang đóng vai trò **answer** hay **judge**. Nếu cả hai gọi cùng provider, cần liên kết qua workflow span hoặc một chiều metadata ở tầng ứng dụng.

## 7. Tạo observation nghiệp vụ bao quanh evaluator

Spring AI đã instrument `ChatModel`, nhưng không tự biết lượt gọi nào thuộc **đánh giá relevance** của bộ dữ liệu. Có thể tạo observation riêng ở tầng nghiệp vụ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.ai.chat.evaluation.RelevancyEvaluator;
import org.springframework.ai.evaluation.EvaluationRequest;
import org.springframework.ai.evaluation.EvaluationResponse;

public final class ObservedRelevanceService {

    private final RelevancyEvaluator evaluator;
    private final ObservationRegistry registry;

    public ObservedRelevanceService(
            RelevancyEvaluator evaluator,
            ObservationRegistry registry) {
        this.evaluator = evaluator;
        this.registry = registry;
    }

    public EvaluationResponse evaluate(EvaluationRequest request) {
        return Observation
                .createNotStarted("quality.evaluation", registry)
                .lowCardinalityKeyValue("evaluation.kind", "relevancy")
                .observe(() -> evaluator.evaluate(request));
    }
}
~~~

`quality.evaluation` là **observation do ứng dụng tự đặt tên**, không phải tên có sẵn của Spring AI. Tùy trace context, span model của judge có thể xuất hiện bên dưới observation này, giúp phân biệt lượt chấm với lượt sinh câu trả lời.

Không gắn `caseId`, user ID hoặc prompt làm **low-cardinality label** vì dễ gây bùng nổ số series và rò rỉ dữ liệu. `evaluation.kind=relevancy` chỉ có ít giá trị và phù hợp hơn. Nếu cần đánh dấu phiên bản dataset, dùng tập giá trị kiểm soát được, không tạo một nhãn riêng cho mọi case.

**Lưu ý:** đoạn code không tự tạo metric `relevance_pass_rate`; ứng dụng vẫn phải thu thập kết quả `EvaluationResponse.isPass()` và trạng thái lỗi judge qua phép đo chất lượng riêng.

## 8. Kiểm tra metric và traces bằng Actuator

Sau khi ứng dụng đã chạy và có ít nhất một lời gọi model, kiểm tra:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/gen_ai.client.operation
curl -s http://localhost:8080/actuator/prometheus
~~~

Đây là **lệnh hướng dẫn tự thực hiện**, không phải kết quả đã chạy. Với Windows có thể dùng `curl.exe` hoặc `Invoke-RestMethod`. Endpoint chỉ truy cập được khi Actuator và registry đã cấu hình, có quyền truy cập phù hợp.

### 8.1. Các Prometheus series liên quan ChatModel

Theo Spring AI Reference 2.1.0:

| Tên series / loại | Ý nghĩa |
| --- | --- |
| `gen_ai_client_operation_seconds_count` | Số thao tác model hoàn tất |
| `gen_ai_client_operation_seconds_sum` | Tổng duration của model calls (giây) |
| `gen_ai_client_operation_seconds_max` | Duration lớn nhất được ghi trong cửa sổ quan sát |
| `gen_ai_client_token_usage_total` | Token counter theo loại input/output/total |
| `gen_ai_client_operation_active_*` | Thao tác đang chạy, tùy registry/version có suffix khác nhau |

`gen_ai.client.operation` là **tên observation/meter cơ sở**; Prometheus biến dấu chấm thành gạch dưới và thêm hậu tố. Đối với long task timer, tài liệu các phiên bản có khác biệt ở cách trình bày tên series `active`; tốt nhất xem output `/actuator/prometheus` thực tế rồi mới viết query.

### 8.2. Các nhãn metric

Khi xuất Prometheus, tên nhãn có thể như:

~~~text
gen_ai_operation_name
gen_ai_system
gen_ai_request_model
gen_ai_response_model
gen_ai_token_type
error
~~~

Nhãn `error` và cách chuẩn hóa tên phụ thuộc convention/registry; cần kiểm chứng từ thực tế. Ví dụ minh họa:

~~~text
gen_ai_client_operation_seconds_count{
  gen_ai_operation_name="chat",
  gen_ai_system="openai",
  gen_ai_request_model="example-model-id",
  gen_ai_response_model="example-model-id",
  error="none"
} 12
~~~

**Không phải dữ liệu đã đo:** số `12` và model name chỉ thể hiện cách đọc. Đặc biệt, số model calls thường khác số request người dùng vì tool calling, retries, RAG orchestration và judge tạo các lượt gọi bổ sung.

## 9. PromQL: so sánh mô hình theo nhà cung cấp

Dưới đây là các query mẫu dành cho Prometheus khi đã xác nhận tên series và label như tài liệu Spring AI 2.1.x.

**Lượt gọi ChatModel mỗi giây theo provider:**

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

**Độ trễ trung bình (giây) theo provider:**

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_sum{
    gen_ai_operation_name="chat"
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

**Số token đầu vào/đầu ra mỗi giây theo model:**

~~~promql
sum by (gen_ai_system, gen_ai_request_model, gen_ai_token_type) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type!="total"
  }[5m])
)
~~~

**Tỷ lệ exception của model call** khi timer có nhãn `error`:

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat",
    error!="none"
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

Các truy vấn chỉ phù hợp nếu dữ liệu đã có các label đó. `error!="none"` không đo sai nội dung, mà chỉ nhóm thao tác có nhãn lỗi ở tầng model. Một phản hồi hallucination vẫn có thể có `error="none"`.

### 9.1. Không cộng input + output + total

Metric `gen_ai_client_token_usage_total` có thể có các giá trị `gen_ai_token_type=input`, `output` và `total`. Vì `total` thường đã là tổng input và output, **không cộng cả ba**. Chọn một trong hai cách:

- Cộng `input` và `output`.
- Chỉ dùng `total`, nếu provider báo đầy đủ và định nghĩa tổng nhất quán.

Nếu một provider không báo usage, counter không tăng cho lượt đó; điều này không chứng minh lời gọi không dùng token. Trong dashboard, nên có cờ hoặc báo cáo **missing usage** để tránh so sánh sai.

### 9.2. P95 cần histogram

`seconds_sum / seconds_count` chỉ cho **trung bình**, không phải P95. Spring Boot không luôn bật histogram buckets mặc định cho timer. Tài liệu metrics Spring AI 2.1-SNAPSHOT hướng dẫn cấu hình:

~~~properties
management.metrics.distribution.percentiles-histogram.gen_ai.client.operation=true
~~~

Khi exporter thật sự có series `gen_ai_client_operation_seconds_bucket`, truy vấn:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, gen_ai_system) (
    rate(gen_ai_client_operation_seconds_bucket{
      gen_ai_operation_name="chat"
    }[5m])
  )
)
~~~

Nếu không có `_bucket`, query P95 trên không hoạt động; kiểm tra registry, cấu hình histogram và cách đặt tên thực tế trước khi triển khai dashboard. Với provider ít traffic, P95 ngắn hạn có thể biến động mạnh do kích thước mẫu nhỏ.

## 10. Phân tích trace để xác định latency

Metrics nói “provider nào chậm?”, traces giúp trả lời “**request cụ thể này** chậm ở bước nào?”.

Ví dụ trace giả lập:

~~~text
POST /api/ask                                  1.85 s
  spring.ai.chat.client                        1.71 s
    spring.ai.advisor: retrieval               0.32 s
      db.vector.client.operation               0.25 s
    gen_ai.client.operation (chat/openai)      1.24 s
      okhttp.requests                          1.17 s
    spring.ai.tool (nếu có)                    0.07 s
~~~

Không coi sơ đồ số liệu này là một trace đã chạy; quan hệ cha-con tùy luồng thực tế, tool có thể gọi sau một lần chạy model khác, và HTTP span không phải lúc nào cũng nested trong streaming.

Để phân tích một span model:

1. Xem `gen_ai.system` và model trong request/response.
2. Xem duration và exception; đối chiếu với latency end-to-end.
3. Xem usage input/output/total nếu có.
4. Kiểm tra tool calls, advisor và vector store trong cùng trace.
5. Kiểm tra HTTP-layer spans khi SDK/provider hỗ trợ.
6. Đối chiếu cấu hình prompt/model và kích thước context của case đang chậm.

Nếu **ChatClient chậm nhưng model nhanh**, kiểm tra retrieval hoặc tool. Nếu **model chậm và số input tokens tăng**, kiểm tra context RAG, chat memory và tool schema. Nếu **provider HTTP lỗi hoặc retry**, xem quota, network và backoff. Không kết luận nguyên nhân chỉ từ một số trung bình.

### 10.1. Streaming và time to first token

Độ trễ operation của `stream(...)` có thể phản ánh thời gian hoàn tất stream, không đồng nhất với **time to first token (TTFT)**. Muốn đo TTFT, cần instrument thời điểm subscription, chunk đầu tiên và chunk cuối ở tầng ứng dụng.

Spring AI 2.1.0 cũng nêu một hạn chế về HTTP span của **OpenAI streaming** do chuyển thread. Thiếu quan hệ cha-con HTTP/model không đủ chứng minh có sự cố mạng hay provider chưa được gọi.

## 11. Token usage, chi phí và giới hạn đối chiếu

Spring AI mô tả `ChatResponseMetadata.getUsage()` với:

~~~java
Integer promptTokens = usage.getPromptTokens();
Integer completionTokens = usage.getCompletionTokens();
Integer totalTokens = usage.getTotalTokens();
~~~

Đây là usage provider **báo cáo**, không phải độ dài ký tự hay số từ trong prompt.

Công thức ước lượng giá đơn giản cho model tính phí theo token:

~~~text
estimated_cost =
    input_tokens  / 1_000_000 * input_price_per_million
  + output_tokens / 1_000_000 * output_price_per_million
~~~

Công thức chỉ là **khung minh họa**, không phải bảng giá của một nhà cung cấp. Provider có thể tính khác theo cached input, reasoning tokens, request type, khu vực, model version, gateway hoặc gói dịch vụ.

Khi so sánh chi phí giữa provider, lưu:

| Dữ liệu | Tại sao cần |
| --- | --- |
| Provider, model request và model response | Có thể dùng alias hoặc router |
| Input/output/total usage | Xác định tài nguyên được báo cáo |
| Cache read/write usage | Có thể có giá khác input bình thường |
| Giá tại thời điểm đo | Bảng giá thay đổi qua thời gian |
| Số lần retry và model calls | Một user request có thể gọi nhiều lần |
| Missing usage | Tránh coi thiếu dữ liệu là chi phí bằng 0 |
| Vai trò answer/judge | Tách chi phí sản phẩm và chi phí evaluation |

### 11.1. Một user request có thể tạo nhiều model operations

~~~text
Một yêu cầu RAG cần truy vấn và chấm:
  - Một lượt tạo embedding cho query
  - Một lượt tra vector store
  - Một lượt ChatModel sinh câu trả lời
  - Có thể thêm tool calling và lượt ChatModel thứ hai
  - Một lượt ChatModel cho RelevancyEvaluator
  - Có thể thêm lượt ChatModel cho FactCheckingEvaluator
~~~

Đây là kịch bản minh họa, không phải pipeline mặc định của mọi ứng dụng. Vì vậy **số model operations khác số user requests**. Cùng provider có thể phục vụ answer và judge; nhãn provider không tự phân biệt vai trò.

## 12. Liên hệ observability với chất lượng RAG và đánh giá

Khi đổi prompt, model hoặc provider, muốn kết luận “chất lượng tăng nhưng chi phí chấp nhận được”, hãy đo riêng:

- **Chất lượng:** Relevancy pass rate, groundedness, fact checking, nhãn chuyên gia.
- **Tính vận hành:** model call error rate, duration, token usage, retry.
- **Pipeline:** retrieval latency, source coverage, tool-call latency và end-to-end latency.
- **Chi phí:** token và bảng giá theo phiên bản; tách answer/embedding/judge.
- **Khả năng tái hiện:** dataset version, answer prompt version, judge prompt version, model/provider và retriever config.

Một bảng kết quả giả lập:

| Chỉ số | Pipeline A | Pipeline B |
| --- | ---: | ---: |
| Relevance pass trên 100 case | 82 | 87 |
| Mean model-call latency | 0,72 s | 0,58 s |
| Model calls trung bình mỗi case | 1,0 | 1,6 |
| Input tokens trung bình mỗi case | 1.100 | 1.900 |
| Output tokens trung bình mỗi case | 130 | 230 |
| Lỗi kỹ thuật ở tầng model | 0,5% | 2,0% |

Dữ liệu chỉ để minh họa. B có pass rate cao và mean latency **mỗi call** thấp hơn, nhưng **nhiều calls, tokens và lỗi** hơn. Không thể suy ra end-to-end latency hoặc tổng chi phí thấp hơn chỉ từ mean latency của model.

Để so sánh **answer model/provider**, giữ judge model/rubric và dataset cố định. Nếu cùng lúc đổi judge, sự thay đổi pass rate có thể là do **thước đo đã thay đổi**.

### 12.1. Cách điều tra khi sau khi đổi model thì độ trễ tăng

1. Xác nhận dataset và số case không đổi.
2. Kiểm tra `gen_ai.system`, `request.model` và `response.model` của từng call.
3. So số model calls/request, có tool call hoặc retry phát sinh không.
4. So distribution của duration, không chỉ trung bình.
5. So input/output tokens và cache usage.
6. Dùng trace để xem retrieval, generation, tool hay HTTP/network chậm.
7. Đối chiếu quality label để tránh tối ưu latency làm giảm độ đúng.
8. Ghi chính xác các thay đổi về prompt, pipeline, model và provider.

## 13. Sampling, cardinality và bảo vệ dữ liệu

### 13.1. Trace sampling

Tài liệu Spring Boot nêu tracing có sampling để hạn chế chi phí; bật xác suất `1.0` cho demo giúp dễ nhìn toàn bộ trace, nhưng production cần cấu hình theo tải và chính sách dữ liệu. Metrics tổng hợp và traces được sample có thể khác về độ bao phủ; đừng lấy một vài trace làm mẫu số chính để kết luận tỷ lệ lỗi toàn hệ thống.

### 13.2. Cardinality

Nhãn metrics nên dùng tập giá trị có giới hạn như:

~~~text
gen_ai_system = openai | anthropic | ollama
gen_ai_operation_name = chat
evaluation_kind = relevance | fact_checking
model_version = một tập phiên bản được kiểm soát
~~~

Tuyệt đối tránh low-cardinality tag chứa raw prompt, response, request ID duy nhất, số điện thoại, email hay mã đơn hàng. Chúng gây bùng nổ series và có thể rò rỉ dữ liệu.

### 13.3. Logging prompt và completion

Spring AI 2.1.0 **không xuất nội dung chat prompt/completion mặc định**. Những cờ được tài liệu mô tả gồm:

~~~properties
spring.ai.chat.observations.log-prompt=false
spring.ai.chat.observations.log-completion=false
spring.ai.chat.observations.include-error-logging=false

spring.ai.chat.client.observations.log-prompt=false
spring.ai.chat.client.observations.log-completion=false
~~~

Chỉ bật ghi nội dung trong môi trường được phê duyệt, có redaction và quy tắc phân quyền/lưu giữ. Việc có trace ID không làm cho dữ liệu prompt trở nên an toàn để xuất tự do.

## 14. Những vấn đề thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Không thấy `gen_ai.client.operation` | Chưa gọi model thật, mock model, hoặc không có instrumentation | Kiểm tra bean `ChatModel`, starter, registry và một lời gọi thực |
| Có model metric nhưng không có trace | Thiếu tracer/exporter/backend hoặc sampling | Kiểm tra OTLP, sampling và log exporter |
| Có `spring.ai.chat.client` nhưng thiếu model span | Luồng chưa gọi model, model custom không instrument | Kiểm tra code path và provider |
| Thiếu token counter | Provider không báo usage hoặc mapping khác | Xem `ChatResponseMetadata.getUsage()` |
| `request.model` khác `response.model` | Alias, deployment hoặc routing | Đối chiếu model config và provider response |
| Provider local rất chậm lần đầu | Cold start / model loading | Xem lần đầu so với warmed-up |
| Có model span nhưng không có HTTP child | SDK khác hoặc giới hạn streaming | Xem tài liệu provider và context propagation |
| P95 query không có kết quả | Không có histogram buckets | Bật histogram và kiểm tra `_bucket` |
| Số calls lớn hơn số user requests | Tool, judge, retry, fan-out | Xem trace tree và workflow |
| Chi phí dashboard lệch hóa đơn | Missing usage, double count, cache, retries | Kiểm tra usage và bảng giá thực tế |
| Relevance giảm nhưng model error = 0 | Trả lời hợp lệ về mặt API nhưng sai nội dung | Điều tra context, prompt, output và judge |

## 15. Bài tập thực hành

### Bài 1. Nhận diện span của provider

Bật observability với một provider được hỗ trợ. Gửi một request ngắn và một request dài qua `ChatModel.call(...)`. Xác định `gen_ai.client.operation`, `gen_ai.system`, request/response model, duration và usage. Ghi những thuộc tính provider không cung cấp.

### Bài 2. So sánh hai provider

Chạy cùng 20 case qua hai provider/model. Ghi mean/P95 latency, token usage, error rate và verdict relevance. Giữ bộ chấm cố định và đánh giá cả các case sai, không chỉ tổng pass rate.

### Bài 3. Phân biệt ChatClient và ChatModel

Thêm một advisor truy vấn vector store. Đọc trace và xác định span ChatClient, advisor, vector store và ChatModel. Giải thích vì sao không thể cộng duration của tất cả span để thành thời gian request.

### Bài 4. Tách chi phí model trả lời và model chấm

Bọc `RelevancyEvaluator.evaluate(...)` bằng `quality.evaluation`. Trên cùng một dataset, phân tích số call và token của answer model so với judge model. Cho biết tại sao `gen_ai.system` không đủ để phân biệt khi dùng cùng provider.

### Bài 5. Xây dashboard Prometheus

Tạo panel số lần gọi/giây theo provider, độ trễ trung bình, P95 (khi có histogram), token usage và error rate. Ghi đúng series/label quan sát được từ ứng dụng; không đoán tên các nhãn chưa tồn tại.

### Bài 6. Thử khả năng bảo mật

Kiểm tra prompt/completion logging mặc định tắt. Viết chính sách nội bộ cho lần bật tạm thời trong môi trường test: dữ liệu giả, redaction, phân quyền, thời hạn lưu và thao tác tắt lại.

## 16. Tổng kết

Ở Spring AI, các thao tác `ChatModel.call(...)` hoặc `stream(...)` của implementation được hỗ trợ được quan sát bằng `gen_ai.client.operation`. Những tín hiệu như `gen_ai.system`, tên model yêu cầu/phản hồi, duration, error và token usage (khi có) giúp phân tích hành vi theo **nhà cung cấp**.

Điểm quan trọng là chọn đúng tầng đo: `ChatClient` đo workflow, còn `ChatModel` đo model provider execution. Không phải mọi provider đều báo token/HTTP trace giống nhau; streaming có những giới hạn riêng, và **observability không tự thay thế việc kiểm thử chất lượng**.

Khi đối chiếu traces/metrics với dataset, prompt/model version, RAG context và kết quả `RelevancyEvaluator` hoặc fact checking, bạn có thể phát hiện suy giảm từ **retrieval, generation, model provider, judge** hay **hạ tầng**. Hãy giữ phép đo minh bạch, tránh đếm trùng và không xuất dữ liệu nhạy cảm ngoài phạm vi cho phép.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): `gen_ai.client.operation`, keys, token usage và giới hạn provider/streaming.
- [Spring AI — Chat Response Metadata / Usage](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): `ChatResponseMetadata` và API `Usage`.
- [Spring AI — OpenAI Chat](https://docs.spring.io/spring-ai/reference/api/chat/openai-chat.html): model-layer/HTTP-layer observations.
- [Spring AI — Anthropic Chat](https://docs.spring.io/spring-ai/reference/api/chat/anthropic-chat.html): instrumentation của provider và client.
- [Spring AI 2.1-SNAPSHOT — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): Prometheus names, PromQL, token labels, histogram.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling và OTLP.
