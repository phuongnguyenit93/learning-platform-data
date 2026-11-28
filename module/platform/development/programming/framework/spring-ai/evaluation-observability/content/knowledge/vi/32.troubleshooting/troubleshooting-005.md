# Số token thiếu, khác nhau hoặc bị tính trùng

> **Chương:** Chẩn đoán sự cố  
> **Module:** SPRING_AI_EVALUATION_OBSERVABILITY — đánh giá chất lượng ứng dụng Spring AI bằng tập dữ liệu, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt token do provider báo cáo, token do ứng dụng tự ước lượng và token được hệ thống billing tính phí.
2. Hiểu input, output, reasoning, cached, multimodal và embedding token có thể được thống kê theo semantics khác nhau.
3. Phân tích chênh lệch token do prompt template, chat history, RAG context, tool schema, retry, fallback và streaming.
4. Tránh cộng trùng token khi có nhiều Observation, callback, response chunk hoặc tầng wrapper cùng ghi nhận một lần gọi.
5. Trích xuất usage từ Spring AI ChatResponse và lưu token usage theo từng model invocation.
6. Thiết kế metrics có cardinality thấp và ledger chi tiết để đối chiếu theo logical run, attempt và provider request.
7. Xây dựng kiểm thử, dashboard và runbook để tìm nguyên nhân thiếu, sai lệch hoặc đếm trùng token.

## 1. Triệu chứng và phạm vi vấn đề

Một request RAG được ghi nhận 1.200 input tokens trong dashboard ứng dụng, nhưng provider báo 1.850 tokens. Một trường hợp khác, dashboard ghi 3.000 output tokens trong khi response chỉ có vài trăm từ. Khi chạy streaming, token count bằng 0 dù nội dung đã được trả về. Có lúc tổng usage tăng gấp đôi sau khi thêm một listener.

Các hiện tượng này có thể đến từ những nguyên nhân khác nhau:

- Ứng dụng chỉ đếm phần user prompt, bỏ system message, chat history, tool definitions hoặc retrieved context.
- Tokenizer cục bộ không khớp tokenizer/model version ở provider.
- Provider trả usage ở final response hoặc usage event riêng nhưng code chỉ đọc content chunks.
- Ứng dụng cộng token của mỗi streaming chunk trong khi provider gửi cumulative usage ở nhiều chunk.
- Một logical run gọi model nhiều lần vì query rewrite, rerank, tool loop, retry hoặc fallback.
- Cùng một usage được cộng ở response handler và Observation listener.
- Prompt caching, reasoning tokens hoặc multimodal payload có cách báo cáo riêng.
- Usage không có trong response nhưng code biến giá trị null thành 0 và xem đó là số đo chính xác.
- Dashboard so sánh các cửa sổ thời gian hoặc mẫu số khác nhau.

**Trước khi sửa phép tính, phải xác định token đang được đếm ở cấp nào và nguồn nào có thẩm quyền cho câu hỏi đang trả lời.** Token estimate hữu ích để lập kế hoạch; provider usage hữu ích để đối chiếu lần gọi; invoice/billing export mới là căn cứ cuối cùng cho số tiền phải trả.

## 2. Ba nguồn số liệu không nên đánh đồng

### 2.1. Tokenizer estimate ở ứng dụng

Ứng dụng có thể dùng tokenizer hoặc thuật toán ước lượng trước khi gửi request để:

- Ước lượng prompt có vượt context window không.
- Cắt bớt chat history hoặc retrieved documents.
- Chọn model theo ngân sách.
- Ước lượng chi phí trước khi gọi provider.
- Theo dõi độ dài nội dung đầu vào.

Estimate phụ thuộc model, tokenizer, version, encoding, cách serialize message và các thành phần request. Nếu tokenizer không chính xác với model/provider, con số chỉ là ước lượng.

Một bộ đếm theo ký tự hoặc từ không phải tokenizer. Quy tắc như “4 ký tự bằng 1 token” chỉ là heuristic thô, không thể dùng làm số liệu billing hoặc kết luận vi phạm context window.

### 2.2. Provider-reported usage

Provider có thể trả usage trong response metadata, response body, streaming usage event hoặc API usage endpoint. Với Spring AI, response đồng bộ thường cung cấp usage qua metadata của ChatResponse:

~~~java
ChatResponse response = chatClient.prompt()
        .user("Tóm tắt nội dung theo ba ý.")
        .call()
        .chatResponse();

var usage = response.getMetadata().getUsage();
if (usage != null) {
    Number inputTokens = usage.getPromptTokens();
    Number outputTokens = usage.getCompletionTokens();
    Number totalTokens = usage.getTotalTokens();
}
~~~

Các accessor trên là giao diện usage phổ biến của Spring AI; kiểm tra API và adapter của phiên bản đang dùng. Provider/adapter có thể không trả mọi trường, có thể trả null hoặc chỉ hỗ trợ usage với một số model/endpoint. Đừng tự gán 0 cho trường không có dữ liệu.

Provider usage thường là nguồn phù hợp nhất để đo usage của một invocation cụ thể. Tuy nhiên, cần hiểu semantics của provider: trường total có thể gồm/không gồm một số nhóm token; cached/reasoning token có thể là chi tiết con; streaming có thể yêu cầu bật tùy chọn trả usage.

### 2.3. Billing hoặc invoice usage

Số tiền cuối cùng có thể dựa trên:

- Input tokens.
- Output tokens.
- Cached input tokens.
- Reasoning tokens hoặc nhóm token riêng theo model.
- Image/audio/video usage theo đơn vị riêng.
- Embedding tokens.
- Batch/realtime pricing.
- Model, region, tier, thời điểm giá và hợp đồng.
- Credits, discounts, minimum charges hoặc các điều chỉnh khác.

Vì thế provider response usage và invoice không nhất thiết giống nhau về đơn vị hoặc thời điểm tổng hợp. Provider usage giúp đối chiếu request; billing export là căn cứ đối chiếu chi phí thực tế theo chính sách provider.

### 2.4. Bảng phân biệt

| Nguồn | Mục đích | Độ tin cậy / giới hạn |
|---|---|---|
| Tokenizer estimate | Preflight, truncation, context budget | Có thể lệch tokenizer/model hoặc request serialization |
| Spring AI Usage metadata | Usage của response/invocation nếu adapter hỗ trợ | Phụ thuộc provider và endpoint; có thể thiếu trường |
| Provider usage API/log | Đối chiếu theo request/model | Có thể đến trễ, khác scope hoặc chỉ có ở một số endpoint |
| Billing export/invoice | Chi phí bị tính | Tổng hợp theo chu kỳ, price rules và điều chỉnh |

Không ghi tất cả vào một trường `tokens` duy nhất. Lưu source và loại usage để biết con số đến từ đâu.

## 3. Hiểu các nhóm token

### 3.1. Input/prompt tokens

Input tokens thường bao gồm nội dung model nhận, nhưng phạm vi thực tế phụ thuộc provider:

- System/developer instructions.
- User message.
- Assistant history được gửi lại.
- Tool/function definitions và JSON schema.
- Retrieved documents/context của RAG.
- Metadata hoặc format instructions.
- Nội dung multimodal như image/audio/video được biểu diễn hoặc xử lý theo cơ chế riêng.

Ứng dụng chỉ đếm user message sẽ thiếu nhiều thành phần trong request thực tế.

### 3.2. Output/completion tokens

Output tokens có thể bao gồm:

- Văn bản trả lời.
- Tool call name và arguments do model sinh.
- Structured output/JSON.
- Reasoning hoặc thinking tokens nếu model/provider báo cáo nhóm này.
- Các token đặc thù của model/endpoint.

Đếm số từ trong câu trả lời hiển thị không tương đương output token usage. Tool arguments có thể tiêu thụ token dù người dùng không nhìn thấy chúng trong nội dung cuối.

### 3.3. Reasoning tokens

Một số model báo cáo reasoning/thinking tokens riêng. Tùy provider, chúng có thể là phần chi tiết của output/completion usage hoặc được trình bày theo schema khác. Không tự cộng reasoning tokens vào completion nếu provider đã bao gồm chúng trong completion total; cần đọc semantics chính thức của model.

Nếu cần theo dõi reasoning riêng, lưu trường provider-native cùng tổng usage và ghi rõ quan hệ bao hàm. Không cộng trường con hai lần.

### 3.4. Cached tokens

Prompt caching có thể làm một phần input được phục vụ từ cache và có giá khác. Cached tokens thường là một phân loại của input usage, không phải lúc nào cũng là một nhóm cộng thêm vào tổng input.

Ví dụ:

~~~text
input_tokens       = 2,000
cached_input       =   800
uncached_input     = 1,200
~~~

Trong ví dụ này, nếu cached_input là phần con của input_tokens thì không tính tổng thành 2.800. Tuy nhiên, mỗi provider có thể đặt tên/semantics khác nhau; xác minh trước khi tạo công thức.

### 3.5. Multimodal tokens và đơn vị khác

Image/audio/video có thể được tính theo token, patch, frame, giây audio, chunk hoặc đơn vị provider-specific. Một số API quy đổi payload sang token nội bộ nhưng không trả tokenizer count thông thường.

Không so sánh image/audio usage với text tokens nếu chưa chuẩn hóa đơn vị. Lưu usage detail theo modality và provider-native unit khi có.

### 3.6. Embedding tokens

RAG thường có ít nhất hai loại model usage:

- EmbeddingModel xử lý query hoặc documents.
- ChatModel sinh câu trả lời.

Embedding usage không nhất thiết nằm trong ChatResponse usage. Một logical RAG run có thể gọi embedding query một lần, embedding batch khi ingest, rồi ChatModel nhiều lần. Phải đo từng model invocation và nhóm theo operation.

Ingest embedding thường là chi phí pipeline/indexing, không nên cộng vào chi phí truy vấn online nếu dashboard đang đo latency/cost per user request. Nếu báo cáo tổng chi phí vòng đời corpus, hãy tách rõ ingest và serving.

## 4. Vì sao provider và ứng dụng đếm khác nhau?

### 4.1. Prompt thực tế dài hơn phần ứng dụng nhìn thấy

Một request Spring AI có thể kết hợp:

| Thành phần | Có thể bị bỏ sót khi estimate thủ công? |
|---|---|
| System prompt | Có |
| User prompt | Thường không |
| Chat history | Có |
| Template variables đã render | Có |
| Retrieved Document content | Có |
| Document metadata/formatting | Có |
| Tool definitions/schema | Có |
| JSON/structured output instructions | Có |
| Provider wrapper/special tokens | Có |
| Image/audio payload | Có |

Đặc biệt với RAG, nội dung context có thể dài hơn câu hỏi rất nhiều. Đếm token trước khi nối retrieved documents sẽ làm estimate thấp đáng kể.

### 4.2. Chat history và prompt template

ChatClient có thể nhận system message, user message, advisors, memory hoặc prompt template. Giá trị cuối cùng gửi model có thể khác source template:

- Template variable được thay bằng nội dung thật.
- Advisor thêm context, memory hoặc instructions.
- Conversation history thêm nhiều lượt trước.
- Message role/formatting được serialize theo quy tắc adapter.
- Một số history được cắt hoặc biến đổi trước khi gọi model.

Muốn kiểm tra estimate, hãy lấy representation đã render ở đúng ranh giới model invocation, áp dụng tokenizer tương thích nếu có. Đừng estimate chỉ từ chuỗi template chưa render.

### 4.3. Tool/function schema

Khi model được phép gọi tools, request có thể chứa mô tả tool, tên, tham số và JSON schema. Chúng tiêu thụ input tokens ngay cả khi model không gọi tool trong lượt đó.

Nếu model sinh tool call, tên tool và arguments cũng có thể nằm trong output usage. Kết quả tool sau đó thường được đưa vào một request model tiếp theo, làm tăng input usage của invocation tiếp theo.

Tool execution tự thân không phải token usage của LLM. Chỉ phần nội dung được gửi tới hoặc sinh ra bởi model mới được tính token theo usage của model.

### 4.4. RAG context và document duplication

Chênh lệch có thể do:

- Nhiều chunk trùng lặp được đưa vào prompt.
- Cùng một document xuất hiện ở nhiều query branch.
- Metadata được serialize thành text.
- Reranker output và retrieved context đều được gửi model.
- Query rewrite tạo thêm một model call.
- Context được nối lại ở prompt advisor và cả service layer.

Đếm số document không đủ để suy ra token. Hai document cùng số lượng có thể chênh token rất lớn do độ dài và nội dung.

### 4.5. Tokenizer/model mismatch

Tokenizer phụ thuộc model và đôi khi phụ thuộc phiên bản model. Các yếu tố làm estimate sai:

- Dùng tokenizer của model gần giống nhưng không đúng model.
- Model alias được trỏ sang version mới.
- Special tokens và message framing khác nhau.
- Tool schema hoặc multimodal payload không được tokenizer cục bộ mô phỏng.
- Unicode, code, URL, JSON và ngôn ngữ khác nhau có phân bố token khác nhau.

Nếu context window là ràng buộc, dùng provider/model-specific tokenizer được hỗ trợ và giữ safety margin. Khi provider usage trả về, lưu sai lệch estimate để hiệu chỉnh.

### 4.6. Provider thêm nội dung nội bộ

Provider có thể áp dụng wrapper, safety instruction, metadata hoặc serialization mà ứng dụng không thấy trong prompt text. Không phải lúc nào client cũng có thể tái tạo chính xác chuỗi/token sequence cuối cùng ở server.

Đây là lý do estimate không nên được xem là authoritative billing usage.

## 5. Retry, fallback và tool loop làm tăng tổng token

### 5.1. Một logical request có thể có nhiều invocation

Ví dụ:

~~~text
Logical RAG run #R1
  1. Query rewrite          300 input + 40 output
  2. Retrieval embedding     25 input
  3. Answer generation    2,000 input + 350 output
  4. Tool call               700 input + 60 output
  5. Tool result follow-up 1,100 input + 250 output
~~~

Số liệu minh họa. Nếu dashboard chỉ ghi invocation answer generation thì tổng logical run bị thiếu. Nếu dashboard cộng cả parent operation usage và tất cả child invocation usage, có thể bị đếm trùng.

### 5.2. Retry

Khi provider timeout hoặc trả lỗi tạm thời, client có thể gửi lại request:

| Đơn vị | Số lượng |
|---|---:|
| Logical request | 1 |
| Model attempts | 2 |
| Provider requests đã xử lý | Có thể 1 hoặc 2 |
| Successful responses | 1 |

Một attempt timeout ở client vẫn có thể đã được provider xử lý và tính phí. Không thể kết luận attempt không có usage chỉ vì ứng dụng không nhận response.

Nếu retry cùng prompt hai lần và cả hai lần provider xử lý, tổng usage/cost có thể gồm cả hai. Lưu attempt riêng và tổng hợp theo logical run. Không ghi đè attempt đầu bằng response thành công của attempt sau.

### 5.3. Fallback model

Fallback từ model A sang model B tạo các invocation khác nhau, có tokenizer và giá khác nhau. Ghi model/provider thực tế của từng attempt; không gắn toàn bộ usage của run vào model cấu hình ban đầu.

### 5.4. Tool loop

Một lượt agent có thể gọi model, thực thi tool, gửi kết quả tool lại model và tiếp tục nhiều vòng. Mỗi lần gọi model có input/output usage riêng. Tổng token của logical run là tổng usage của các model invocations thực sự được provider ghi nhận, cộng theo định nghĩa usage không chồng lặp.

Không cộng output token của tool execution như thể tool là model. Không bỏ tool schema hoặc tool result trong input của lượt kế tiếp.

## 6. Streaming: usage có thể nằm ở chunk cuối hoặc event riêng

### 6.1. Content chunk không phải usage record

Streaming API thường phát nhiều chunk nội dung. Chunk có thể chỉ chứa delta text, tool-call delta hoặc metadata một phần. Provider có thể chỉ gửi usage ở:

- Chunk cuối.
- Một usage event riêng.
- Final response sau khi stream hoàn tất.
- Một endpoint khác dùng để truy vấn usage.

Nếu ứng dụng chỉ gọi `.content()` để lấy chuỗi, metadata usage có thể bị loại khỏi pipeline.

### 6.2. Không cộng cumulative usage ở mỗi chunk

Một số protocol có thể gửi snapshot usage lặp lại hoặc trường usage cumulative. Nếu code cộng mọi snapshot:

~~~text
chunk 1: total = 10
chunk 2: total = 25
chunk 3: total = 40

Sai: 10 + 25 + 40 = 75
Đúng: final cumulative usage = 40
~~~

Ngược lại, nếu protocol gửi delta usage theo từng event, cần cộng các delta đúng một lần. Phải đọc semantics của adapter/provider; không suy luận từ tên chunk.

### 6.3. Streaming không có usage

Nếu content có nhưng usage null:

1. Kiểm tra provider có hỗ trợ usage trong streaming endpoint/model không.
2. Kiểm tra option/include-usage tương ứng của adapter và version.
3. Dùng API trả ChatResponse/metadata thay vì chỉ lấy content nếu cần usage.
4. Kiểm tra stream có kết thúc bình thường hay bị cancel/disconnect.
5. Kiểm tra final usage event có bị filter hoặc mất trong mapping không.
6. Nếu không có provider usage, ghi estimate với source=estimated và confidence phù hợp.

Không biến usage null thành 0 rồi báo cáo rằng request không tiêu thụ token.

### 6.4. Spring AI streaming

Với Spring AI, có thể lấy stream các ChatResponse thay vì chỉ lấy nội dung:

~~~java
Flux<ChatResponse> responses = chatClient.prompt()
        .user("Tóm tắt các nguồn đã truy xuất.")
        .stream()
        .chatResponse();
~~~

Kiểu stream cụ thể và cách adapter chuyển usage event phụ thuộc provider/version. Hãy kiểm tra toàn bộ response stream, bao gồm terminal/final event nếu adapter cung cấp. Đừng mặc định mọi chunk có usage hoặc final usage luôn nằm ở chunk cuối.

Khi ứng dụng chuyển sang `.content()`, response metadata có thể không còn được giữ. Nếu usage là yêu cầu đo lường, hãy xử lý ChatResponse ở tầng thích hợp rồi mới map thành content cho client.

### 6.5. Cancel và partial stream

Nếu client ngắt kết nối, stream bị cancel trước khi provider gửi usage cuối. Khi đó:

- Có thể đã tiêu thụ một phần input/output tokens.
- Provider có thể tính usage partial hoặc chỉ công bố sau khi hoàn tất.
- Ứng dụng có thể không nhận được final usage.
- Retry hoặc resume có thể tạo request mới.

Ghi trạng thái `usage_missing` hoặc `partial` thay vì tự suy ra usage cuối. Nếu cần ước lượng partial output, đánh dấu nguồn và phương pháp estimate rõ ràng.

## 7. Trích xuất usage trong Spring AI

### 7.1. Đồng bộ với ChatResponse

Ví dụ trích xuất metadata:

~~~java
import java.util.Optional;
import org.springframework.ai.chat.model.ChatResponse;

public record TokenUsage(
        Long inputTokens,
        Long outputTokens,
        Long reportedTotalTokens) {
}

public final class SpringAiUsageExtractor {

    public Optional<TokenUsage> extract(ChatResponse response) {
        if (response == null || response.getMetadata() == null) {
            return Optional.empty();
        }

        var usage = response.getMetadata().getUsage();
        if (usage == null) {
            return Optional.empty();
        }

        return Optional.of(new TokenUsage(
                asLong(usage.getPromptTokens()),
                asLong(usage.getCompletionTokens()),
                asLong(usage.getTotalTokens())));
    }

    private Long asLong(Number value) {
        return value == null ? null : value.longValue();
    }
}
~~~

Giữ null cho trường không được provider báo cáo. Không tự thay bằng 0. Tên package và kiểu trả về usage có thể thay đổi giữa các phiên bản; điều chỉnh theo API thực tế của Spring AI BOM đang dùng.

### 7.2. Gọi ChatClient và ghi usage

~~~java
ChatResponse response = chatClient.prompt()
        .system("Trả lời ngắn gọn và dựa trên nguồn.")
        .user(question)
        .call()
        .chatResponse();

usageExtractor.extract(response).ifPresent(usage ->
        usageRecorder.record(
                "provider-alias",
                "model-alias",
                "answer",
                usage));
~~~

Tên provider/model ở đây nên là alias cấu hình có tập giá trị hữu hạn. Không lấy tên model tùy ý từ input người dùng hoặc nhét request ID vào metric tag.

### 7.3. Ghi usage vào Micrometer

Ví dụ một counter theo hướng token:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public final class TokenUsageMetrics {
    private final MeterRegistry registry;

    public TokenUsageMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String provider,
            String model,
            String operation,
            TokenUsage usage) {
        increment(provider, model, operation,
                "input", usage.inputTokens());
        increment(provider, model, operation,
                "output", usage.outputTokens());
    }

    private void increment(
            String provider,
            String model,
            String operation,
            String direction,
            Long amount) {
        if (amount == null || amount <= 0) {
            return;
        }

        registry.counter(
                "app.ai.tokens",
                "provider", provider,
                "model", model,
                "operation", operation,
                "direction", direction)
                .increment(amount.doubleValue());
    }
}
~~~

Micrometer có thể export meter này thành counter series, thường có hậu tố _total trong Prometheus. Chỉ dùng tags có cardinality hữu hạn như provider alias, model alias, operation và direction. Không dùng conversation ID, trace ID, prompt hash, user ID, tenant ID hoặc document ID làm metric tags.

Ví dụ chỉ ghi input/output. Nếu cần cached/reasoning/modality breakdown, tạo trường riêng sau khi xác minh semantics provider và bảo đảm không cộng nhóm con vào total lần nữa.

### 7.4. Không ghi cùng usage ở nhiều tầng

Chọn một nơi làm owner ghi nhận usage cho mỗi model invocation:

- Service wrapper ghi một lần sau khi nhận response; hoặc
- Observation handler chuyên biệt ghi một lần theo lifecycle; hoặc
- Adapter/listener ghi usage theo provider response.

Nếu nhiều tầng cùng ghi counter, phải có idempotency/deduplication theo invocation key trong ledger. Metrics counter không tự biết hai lần increment có đại diện cùng một response hay không.

Không vừa increment usage trong response handler, vừa increment trong doOnNext cho cùng ChatResponse, vừa tổng hợp lại ở parent RAG span.

## 8. Tách logical run, model invocation và attempt

### 8.1. Ba cấp định danh

| Cấp | Ý nghĩa | Ví dụ |
|---|---|---|
| Logical run | Một tác vụ RAG/agent được đánh giá | Một câu hỏi người dùng |
| Model invocation | Một lần gửi request đến một model endpoint | Query rewrite, answer generation |
| Attempt | Một lần thử gửi invocation, bao gồm retry | Lần đầu timeout, lần hai thành công |

Một logical run có thể có nhiều invocations; một invocation có thể có nhiều attempts. Usage nên gắn vào attempt/response thực tế rồi tổng hợp lên invocation và logical run theo chính sách.

### 8.2. Ledger chi tiết

Một bảng ledger có thể gồm:

| Field | Mục đích |
|---|---|
| logical_run_ref | Opaque reference của lượt RAG/evaluation |
| invocation_ref | Định danh một model call |
| attempt_number | Số lần thử |
| provider_request_ref | ID provider nếu có và được phép lưu |
| provider/model | Model thực tế đã xử lý |
| operation | rewrite, embedding, answer, tool_followup, rerank |
| usage_source | provider, estimate, billing_export |
| input/output/total | Usage theo semantics đã xác định |
| cached/reasoning/modality | Chi tiết native nếu provider hỗ trợ |
| status | success, timeout, error, cancelled, usage_missing |
| timestamp | Thời điểm UTC của invocation/response |
| price_version | Phiên bản bảng giá dùng để estimate cost |

Ledger cần ACL, retention và redaction phù hợp. Không lưu raw prompt, retrieved documents hoặc tool arguments chỉ để đếm token.

### 8.3. Idempotency và duplicate response

Nếu cùng một response được xử lý qua nhiều callback, cần khóa deduplication. Có thể dùng invocation reference + attempt number + provider request ID nếu các giá trị này ổn định và không nhạy cảm.

Đừng dùng trace ID làm idempotency key duy nhất nếu một trace có nhiều model invocations. Trace ID định danh toàn bộ trace, không phải một request tới model.

Nếu provider không trả request ID, tạo invocation reference ở ứng dụng trước khi gửi. Khi retry, tạo attempt mới nhưng giữ cùng logical invocation reference hoặc liên kết theo model của hệ thống.

### 8.4. Tổng hợp logical run

Ví dụ:

~~~text
logical_run R1
  invocation rewrite / attempt 1: 120 input + 30 output
  invocation answer  / attempt 1: timeout, usage missing
  invocation answer  / attempt 2: 1,800 input + 260 output
  invocation tool-followup / attempt 1: 900 input + 80 output
~~~

Tổng usage được provider xác nhận tối thiểu là các invocation có usage đã biết. Attempt timeout được đánh dấu unknown, không tự gán 0. Nếu provider billing export sau đó xác nhận attempt timeout đã được xử lý và tính phí, reconcile ledger bằng evidence đó.

## 9. Đối chiếu token với chi phí

### 9.1. Token count không phải cost

Cost có thể được tính theo từng loại usage:

~~~text
estimated_cost =
    input_tokens  * input_price_per_token
  + output_tokens * output_price_per_token
  + cached_tokens * cached_input_price_per_token
  + modality_units * modality_price_per_unit
~~~

Đây là công thức minh họa. Không cộng cached tokens thêm lần nữa nếu chúng đã nằm trong input_tokens; cần tách uncached/cached theo semantics bảng giá. Reasoning tokens cũng cần xác minh có nằm trong output price hay có mức riêng.

### 9.2. Price version

Giá model có thể thay đổi theo:

- Provider và model version.
- Input/output/cached token tier.
- Region hoặc endpoint.
- Batch/realtime mode.
- Context length tier.
- Contract/discount/credits.
- Thời điểm phát sinh usage.

Khi ước lượng cost, lưu price_version hoặc effective date. Nếu dùng bảng giá hiện tại để tính lại usage cũ, kết quả có thể sai.

### 9.3. Đối chiếu ba lớp

| Lớp | Câu hỏi |
|---|---|
| Application usage | Ứng dụng ghi nhận bao nhiêu token cho từng invocation? |
| Provider usage | Provider báo bao nhiêu usage cho request đã xử lý? |
| Billing export | Provider tính bao nhiêu tiền/đơn vị trong chu kỳ? |

So sánh theo cùng model, project/tenant, thời gian và usage category. Billing có thể tổng hợp trễ hoặc áp dụng điều chỉnh; không kỳ vọng dashboard online khớp invoice tức thời.

## 10. Metrics và dashboard

### 10.1. Metric names gợi ý

| Metric | Type | Ý nghĩa |
|---|---|---|
| app.ai.tokens | Counter | Token input/output được ghi nhận |
| app.ai.invocations | Counter | Số model invocations |
| app.ai.usage.missing | Counter | Số response không có usage |
| app.ai.usage.estimated | Counter | Số invocation chỉ có estimate |
| app.ai.usage.discrepancy | DistributionSummary | Sai lệch estimate so với provider |
| app.ai.retry.attempts | Counter | Số attempt retry |
| app.ai.usage.reconciliation.delay | Timer | Thời gian chờ provider/billing reconciliation |

Tên và kiểu metric cần thống nhất với registry conventions. Đừng ghi usage_missing bằng token=0; đó là trạng thái dữ liệu khác với usage thật bằng 0.

### 10.2. PromQL token throughput

Input tokens mỗi giây theo model:

~~~promql
sum by (model) (
  rate(app_ai_tokens_total{direction="input"}[5m])
)
~~~

Output tokens mỗi giây:

~~~promql
sum by (model) (
  rate(app_ai_tokens_total{direction="output"}[5m])
)
~~~

Token usage theo operation:

~~~promql
sum by (operation, direction) (
  increase(app_ai_tokens_total[1h])
)
~~~

Tên series thực tế phụ thuộc Micrometer Prometheus naming convention. Xác minh labels và suffix từ endpoint trước khi dùng query.

### 10.3. Tỷ lệ thiếu usage

Nếu có invocation counter và usage missing counter cùng scope:

~~~promql
sum(rate(app_ai_usage_missing_total[15m]))
/
sum(rate(app_ai_invocations_total[15m]))
~~~

Đảm bảo cả hai counter đếm cùng đơn vị invocation và cùng cohort. Nếu usage missing được đếm theo response chunk còn invocations đếm theo logical run, tỷ lệ này không có ý nghĩa.

### 10.4. Estimate discrepancy

Có thể theo dõi sai lệch tương đối:

~~~text
relative_difference =
  (provider_reported_input - estimated_input)
  / max(provider_reported_input, 1)
~~~

Phân tích theo model/provider/operation và tokenizer version. Không dùng một ngưỡng chung cho mọi model hoặc multimodal request. Giữ cả estimate và provider usage để có thể hiệu chỉnh estimator.

### 10.5. Dashboard nên chia nhóm

| Nhóm | Panels |
|---|---|
| Volume | Input/output tokens, invocation count, tokens per logical run |
| Data quality | Usage missing, estimated-only, discrepancy distribution |
| Execution | Attempts, retries, fallback, tool calls, streaming cancellations |
| Cost | Estimated cost by model/operation/price version |
| Provider reconciliation | Provider usage vs application usage vs billing export |
| RAG evaluation | Tokens per answer, context tokens, Recall@K, relevance, latency |

Metrics tổng hợp không đủ để điều tra một run cụ thể. Dùng ledger/evaluation evidence có quyền truy cập phù hợp để drill down bằng opaque reference.

## 11. Nguyên nhân tính trùng token

### 11.1. Đếm cùng response ở nhiều tầng

Một response có thể được ghi ở:

- ChatModel service wrapper.
- ChatClient advisor.
- Observation handler.
- Listener/callback.
- Streaming finalizer.
- Parent RAG aggregation.

Nếu tất cả cùng increment counter, token bị nhân lên. Chọn một owner cho mỗi invocation và chỉ aggregate parent từ ledger, không ghi lại usage của child thành một invocation mới.

### 11.2. Cộng mọi streaming chunk

Nếu mỗi chunk mang cumulative usage, cộng tất cả chunk sẽ tính lặp. Nếu chunk chỉ mang delta usage, phải cộng delta. Nếu chỉ final chunk mang usage, chỉ ghi final usage.

Đừng giả định semantics; lưu fixture response của provider ở test và kiểm tra adapter mapping.

### 11.3. Cộng total cùng input và output

Ví dụ:

~~~text
input_tokens  = 1,000
output_tokens =   200
total_tokens  = 1,200
~~~

Nếu total đã bằng input + output, không cộng cả ba thành 2.400. total_tokens thường là tổng được provider báo cáo; input/output là thành phần. Có thể có trường hợp provider định nghĩa thêm nhóm token, nên vẫn phải theo semantics cụ thể.

### 11.4. Cộng cached/reasoning tokens lần hai

Nếu cached tokens là subset của input và reasoning là subset của completion, cộng chúng vào tổng một lần nữa sẽ double count. Lưu detail để phân tích giá, nhưng đánh dấu quan hệ included_in hoặc semantics tương đương.

### 11.5. Cộng estimate và provider usage

Không cộng tokenizer estimate với provider usage cho cùng invocation. Estimate là dự đoán, provider usage là kết quả đo. Có thể lưu cả hai để tính sai lệch, nhưng tổng token thực tế chỉ dùng một nguồn theo policy.

### 11.6. Retry/fallback không phải duplicate

Hai attempt thực sự được provider xử lý có thể tiêu thụ hai lần usage. Đây là usage phát sinh thật, không phải duplicate do instrumentation. Phải giữ attempt riêng để phân biệt retry cost với lỗi ghi trùng.

## 12. Bảo đảm chất lượng dữ liệu usage

### 12.1. Invariants

Với usage thông thường, có thể kiểm tra:

- Token counts không âm.
- Provider/model/operation có giá trị hợp lệ.
- Mỗi invocation/attempt có tối đa một authoritative usage snapshot, trừ protocol incremental đã định nghĩa.
- Total và component counts tuân theo semantics provider.
- Usage source được ghi rõ.
- Missing không bị chuyển thành zero.
- Logical run aggregate không cộng lặp parent và child records.
- Retry attempts được tách riêng.
- Token units của text, image, audio và video không bị trộn.

Không ép total = input + output cho mọi provider nếu usage có reasoning/cached/modality categories với semantics riêng. Nếu kiểm tra invariant, phải cấu hình theo model/provider schema.

### 12.2. Kiểm thử fixtures

Tạo fixtures cho:

1. Đồng bộ response có đầy đủ prompt/completion/total.
2. Response thiếu usage.
3. Usage chỉ có prompt hoặc chỉ completion.
4. Cached tokens là subset của input.
5. Reasoning detail nằm trong completion.
6. Streaming chỉ có usage ở final event.
7. Streaming gửi cumulative usage nhiều lần.
8. Streaming gửi delta usage.
9. Stream bị cancel trước final event.
10. Retry timeout rồi success.
11. Fallback sang model khác.
12. Tool call và follow-up invocation.

Fixture phải phản ánh payload/semantics adapter thực tế. Không tự tạo giả định rằng mọi provider gửi cùng schema.

### 12.3. Kiểm tra idempotency

Gửi cùng một usage event qua consumer hai lần trong test và xác minh ledger chỉ lưu một authoritative record cho cùng invocation/attempt. Nếu metrics counter không thể rollback, hãy phát metrics sau khi ledger đã chấp nhận record hoặc dùng một pipeline aggregation idempotent.

Không tạo deduplication key bằng prompt hash; prompt có thể nhạy cảm và hai invocation hợp lệ có prompt giống nhau.

## 13. Runbook chẩn đoán theo thứ tự

1. **Xác định cấp đo:** logical run, model invocation hay attempt?
2. **Xác định nguồn:** tokenizer estimate, Spring AI usage metadata, provider usage API hay billing export?
3. **Kiểm tra response đồng bộ:** usage có null không, field nào có giá trị?
4. **Kiểm tra prompt thực tế:** system, user, history, advisor, RAG context, tool schema và structured output.
5. **Kiểm tra model/tokenizer:** alias/version, tokenizer version và multimodal support.
6. **Kiểm tra streaming:** final usage event, cumulative/delta semantics, cancellation và mapping sang ChatResponse.
7. **Kiểm tra invocation graph:** rewrite, embedding, answer, tool loop, retry và fallback.
8. **Kiểm tra double counting:** response handler, listener, observation, chunk consumer và parent aggregation.
9. **Kiểm tra total/detail semantics:** cached/reasoning/modality có phải subset hay cộng thêm?
10. **Đối chiếu provider:** request reference, model thực tế, usage và thời gian UTC.
11. **Đối chiếu billing:** price version, usage category, project/tenant và chu kỳ invoice.
12. **Thêm fixture/regression test:** giữ nguyên các trường hợp đã phát hiện.

### 13.1. Ma trận triệu chứng

| Triệu chứng | Nguyên nhân có khả năng | Bằng chứng cần xem |
|---|---|---|
| App estimate thấp hơn provider | Bỏ system/history/RAG/tool schema hoặc tokenizer lệch | Rendered request, tokenizer/model version |
| Provider usage null | Adapter/endpoint không hỗ trợ, stream thiếu final usage | Response metadata, provider options, terminal event |
| Streaming count bằng 0 | Chỉ lấy content, bỏ ChatResponse metadata | Stream type và final usage event |
| Token count tăng theo số chunk | Cộng cumulative snapshot hoặc đếm chunk như token | Chunk fixture và usage semantics |
| Token count gần gấp đôi sau thêm listener | Hai tầng ghi cùng invocation | Listener registration, response handler, metric owner |
| Total bằng input+output nhưng dashboard gấp đôi | Cộng total với components | Aggregation formula |
| RAG run có token thấp bất thường | Bỏ query rewrite/tool follow-up/embedding hoặc context | Invocation graph và operation ledger |
| Retry làm cost tăng | Provider đã xử lý attempt trước dù client timeout | Attempt IDs, provider request usage |
| Embedding cost không nằm trong RAG cost | Đang đo ChatModel riêng | Embedding usage và cost scope |
| Cached token làm total tăng bất thường | Cached usage bị cộng thêm dù là subset | Provider usage schema |
| Model fallback có sai lệch lớn | Dùng tokenizer/price của model ban đầu | Actual model per attempt |
| Billing khác provider response usage | Pricing tier, delayed billing, modality hoặc adjustment | Billing export và price version |
| Request thứ hai ghi usage request đầu | Mutable accumulator/callback state bị dùng chung | Concurrency test, invocation key |

## 14. Những sai lầm thường gặp

1. **Dùng số từ/ký tự làm token count chính xác.** Tokenizer phụ thuộc model và serialization.
2. **Chỉ đếm user message.** System, history, RAG context và tool schema cũng có thể được gửi.
3. **Coi estimate là provider usage.** Hai nguồn có mục đích khác nhau.
4. **Biến usage null thành 0.** Không có dữ liệu không đồng nghĩa không tiêu thụ token.
5. **Chỉ đọc content trong streaming.** Metadata/final usage event có thể bị bỏ.
6. **Cộng mọi usage snapshot ở từng chunk.** Cumulative usage sẽ bị cộng lặp.
7. **Cộng total với input và output.** Total thường đã bao gồm các thành phần.
8. **Cộng cached/reasoning detail lần nữa.** Các trường này có thể là subset.
9. **Bỏ qua retry/fallback.** Một logical run có thể tạo nhiều provider requests có phí.
10. **Gộp embedding vào ChatModel usage.** Đây là operation/model usage riêng.
11. **Coi tool execution là token usage.** Tool chỉ tiêu thụ model tokens khi nội dung được gửi/sinh bởi model.
12. **Ghi usage ở nhiều listener.** Cùng response có thể increment counter nhiều lần.
13. **Gắn run ID hoặc prompt hash vào metric labels.** Cardinality và privacy tăng mạnh.
14. **So sánh hai cửa sổ thời gian khác nhau.** Counter và provider reports cần cùng scope/time window.
15. **Dùng giá hiện tại để tính lại cost lịch sử.** Cần price version/effective date.
16. **Coi timeout client là provider không tính phí.** Request có thể đã được xử lý.
17. **Ép total bằng input + output cho mọi modality/model.** Usage schema có thể có semantics khác.

## 15. Bài thực hành tự luyện

**Bối cảnh:** Dashboard ghi một logical RAG run có 2.400 tokens. Provider usage cho answer call là 3.100 tokens. Sau khi bật streaming và thêm usage listener, dashboard tăng lên khoảng 6.000 tokens. Run có query rewrite, retrieval embedding, tool call và một lần retry.

Yêu cầu:

1. Lập invocation graph cho query rewrite, embedding, answer, tool call và follow-up.
2. Ghi logical run reference, invocation reference và attempt number riêng.
3. Lấy ChatResponse usage metadata cho call đồng bộ và đánh dấu field null.
4. Với streaming, giữ ChatResponse stream và kiểm tra final usage event/cumulative semantics.
5. So sánh estimate trên prompt đã render với provider-reported input usage.
6. Đếm system prompt, chat history, retrieved context, tool schema và structured output.
7. Tách embedding usage khỏi ChatModel usage.
8. Kiểm tra retry attempt có được provider xử lý dù client timeout không.
9. Tìm listener/service wrapper đang ghi cùng một response nhiều lần.
10. Kiểm tra total, input/output, cached/reasoning có bị cộng lặp không.
11. Ghi metrics bằng tags hữu hạn; lưu drill-down trong ledger có ACL.
12. Đối chiếu provider usage và billing export theo model, price version và thời gian.
13. Viết fixtures cho missing usage, streaming final event, cumulative usage và retry.
14. Kiểm tra logical run total không cộng lại parent và child records.

**Câu hỏi tự kiểm tra:**

- Tokenizer estimate, provider usage và billing usage khác nhau thế nào?
- Vì sao chỉ đếm user message làm input token thấp hơn provider?
- Tool schema và tool result được tính ở invocation nào?
- Cached tokens có nên cộng thêm vào input total không?
- Khi reasoning tokens là subset của completion, làm sao tránh double count?
- Vì sao usage có thể không xuất hiện trong content chunk?
- Cần làm gì nếu stream bị cancel trước final usage event?
- Một timeout retry có thể vẫn bị provider tính phí không?
- Vì sao một logical run cần nhiều invocation records?
- Làm thế nào phân biệt duplicate instrumentation với hai attempts thật?

## 16. Checklist triển khai

- [ ] Mỗi usage record xác định source: provider, estimate hoặc billing export.
- [ ] Phân biệt logical run, model invocation và attempt.
- [ ] Lưu provider/model/operation thực tế của từng invocation.
- [ ] Đọc ChatResponse metadata usage và giữ null cho trường thiếu.
- [ ] Không dùng estimate làm authoritative billing usage.
- [ ] Estimate trên prompt đã render, gồm system/history/RAG/tool schema khi có.
- [ ] Tokenizer khớp model/version hoặc ghi rõ estimate confidence.
- [ ] Streaming giữ ChatResponse metadata và xử lý final/delta/cumulative usage theo provider semantics.
- [ ] Cancel/partial stream được đánh dấu usage_missing/partial thay vì 0.
- [ ] Embedding usage được đo riêng với ChatModel usage.
- [ ] Retry/fallback/tool loops được lưu thành invocations/attempts riêng.
- [ ] Chỉ có một owner ghi usage cho mỗi invocation hoặc có deduplication.
- [ ] Total không bị cộng lại với input/output.
- [ ] Cached/reasoning/modality detail có semantics bao hàm rõ ràng.
- [ ] Metrics tags có cardinality thấp; không chứa prompt/user/tenant/run/trace ID.
- [ ] Ledger có ACL, retention và redaction phù hợp.
- [ ] Dashboard so cùng scope, model, operation và time window.
- [ ] Cost estimate lưu price version và được reconcile với billing export.
- [ ] Có fixtures cho sync, streaming, missing usage, retries, fallback và tool loop.
- [ ] Có cảnh báo khi usage missing/discrepancy tăng bất thường.

## Tổng kết

Token thiếu, khác nhau hoặc bị tính trùng thường xuất phát từ việc trộn ba nguồn: tokenizer estimate, provider-reported usage và billing. Estimate có ích cho preflight nhưng có thể bỏ sót system prompt, history, RAG context, tool schema, multimodal payload hoặc khác tokenizer. Provider usage phù hợp để đối chiếu invocation nếu adapter/endpoint trả đủ metadata. Billing export là căn cứ cuối cùng cho chi phí theo price rules và chu kỳ của provider.

Trong Spring AI, hãy đọc usage từ ChatResponse metadata khi có, giữ null cho trường không được cung cấp và xử lý streaming ở cấp ChatResponse/final usage event thay vì chỉ lấy content. Tách logical run, model invocation và attempt để phản ánh query rewrite, embedding, tool loop, retry và fallback. Chọn một owner ghi usage cho mỗi invocation; không cộng cumulative chunks, total với input/output hoặc cached/reasoning subsets lần hai. Cuối cùng, dùng metrics có cardinality thấp và ledger có kiểm soát truy cập để đối chiếu provider usage, estimate và billing theo cùng model, thời gian và price version.

## Tài liệu tham khảo

- [Spring AI — Chat Models](https://docs.spring.io/spring-ai/reference/api/chatmodel.html): ChatResponse, metadata và usage.
- [Spring AI — Chat Client](https://docs.spring.io/spring-ai/reference/api/chatclient.html): ChatClient call/streaming APIs.
- [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): metrics và observations của ChatClient/ChatModel/EmbeddingModel.
- [Spring AI — Embedding Models](https://docs.spring.io/spring-ai/reference/api/embeddings.html): embedding API và response metadata.
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): counter semantics và rate aggregation.
- [Micrometer — Meter Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html): meter registration và registry behavior.
- [OpenTelemetry — GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/): attributes cho model, operation và token usage.
- [OpenAI API — Usage](https://platform.openai.com/docs/guides/usage): provider usage reporting và cách đọc usage theo API.
- [OpenAI API — Pricing](https://openai.com/api/pricing/): pricing theo model và usage category.
- [tiktoken](https://github.com/openai/tiktoken): tokenizer và giới hạn của token estimation theo encoding/model.
