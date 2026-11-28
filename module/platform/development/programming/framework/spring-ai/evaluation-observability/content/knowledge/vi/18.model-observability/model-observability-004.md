# Quan sát mô hình: Đọc token đầu vào, đầu ra và tổng mức sử dụng

## 1. Vì sao token usage quan trọng?

Một ứng dụng Spring AI có thể đưa vào mô hình nhiều dữ liệu hơn câu hỏi mà người dùng nhìn thấy: system prompt, lịch sử hội thoại, các chunk RAG, khai báo công cụ và tool results. Khi mô hình trả lời, provider cũng có thể tính token cho nội dung đầu ra, lời gọi công cụ, phần suy luận hoặc dữ liệu đa phương thức.

Muốn đánh giá thay đổi của prompt, model hay pipeline, cần quan sát ít nhất ba đại lượng:

- **Input tokens / prompt tokens:** lượng token được provider ghi nhận ở đầu vào của lời gọi.
- **Output tokens / completion tokens:** lượng token được provider ghi nhận cho phần sinh kết quả.
- **Total tokens:** tổng mức tiêu thụ được Spring AI hoặc provider báo cho lời gọi/trao đổi.

Ví dụ mô phỏng một lượt hỏi đáp RAG:

~~~text
Câu hỏi và yêu cầu hệ thống:        180 token
Ngữ cảnh từ retriever:             900 token
Lịch sử và dữ liệu khác:           120 token
-------------------------------------------
Input tokens:                    1.200 token
Output tokens:                     160 token
Total tokens:                    1.360 token
~~~

**Các số trên chỉ để minh họa**, không phải kết quả tokenizer hoặc benchmark. Số token không thể được suy ra chính xác bằng cách đếm ký tự, từ hay dòng trong Markdown.

Bài học thuộc chương **Quan sát mô hình** của module `SPRING_AI_EVALUATION_OBSERVABILITY`. Module kết hợp dataset, đánh giá relevance, fact checking, kiểm thử RAG/tool calling với metrics, traces, chi phí và độ trễ để truy nguyên nguyên nhân suy giảm chất lượng qua các phiên bản prompt, model và pipeline.

**Mục tiêu:**

1. Đọc `ChatResponseMetadata.getUsage()` và hiểu ba phương thức `getPromptTokens()`, `getCompletionTokens()`, `getTotalTokens()`.
2. Phân biệt usage thiếu, bằng 0, có một phần và được tổng hợp qua nhiều model calls.
3. Đọc cache read/write, `getNativeUsage()` và giới hạn của chúng theo provider.
4. Tránh cộng trùng các lượt tool calling, stream chunks và metric có nhãn `total`.
5. Tạo dashboard Prometheus cho token usage và nhận diện missing usage.
6. Ước lượng chi phí theo model/đơn giá mà không nhầm tổng token với hóa đơn.
7. Liên kết token với latency, quality metrics và phiên bản RAG/evaluation.

## 2. Những điều token không đo trực tiếp

| Khái niệm | Đơn vị | Phản ánh | Không đồng nghĩa |
| --- | --- | --- | --- |
| Ký tự trong câu hỏi | Code unit hoặc ký tự Unicode | Độ dài văn bản | Prompt tokens |
| Số từ | Từ ngôn ngữ tự nhiên | Độ dài diễn đạt | Tokenizer của provider |
| Prompt tokens | Token theo model/provider | Đầu vào lời gọi | Chỉ văn bản của user |
| Completion tokens | Token theo model/provider | Đầu ra lời gọi | Chỉ text hiển thị |
| Total tokens | Theo usage schema | Tổng mức sử dụng | Số API requests |
| Model operations | Số `ChatModel` calls | Hoạt động model | Số câu hỏi người dùng |
| User requests | Số yêu cầu sản phẩm | Lưu lượng nghiệp vụ | Số tool loops hoặc retries |

Một câu tiếng Việt có thể được tokenizer của hai model chia khác nhau. Token output cũng có thể gồm tool-call arguments hoặc token đặc thù mà người dùng không nhìn thấy dưới dạng một đoạn text.

### 2.1. Input thường gồm những thành phần nào?

Tùy provider và cách xây prompt:

- System instructions và các messages của hội thoại.
- Retrieval context đã đưa vào lượt RAG.
- Chat history/memory thực sự được gắn vào prompt.
- Tool definitions, function schemas và tool results.
- Trường dữ liệu có cấu trúc, hoặc multimodal input nếu model hỗ trợ.

**Không lấy riêng độ dài user question làm input token count.** Một câu hỏi 30 token có thể đi cùng context 4.000 token và danh sách tool schemas dài. Ngược lại, sự tăng token có thể do memory, không phải do retriever.

### 2.2. Output tokens có thể khác số token của câu trả lời cuối

Trong một vòng gọi công cụ, model đầu tiên có thể sinh chỉ dẫn gọi tool; lời gọi tiếp theo mới tạo câu trả lời cuối. Tổng output tokens của vòng này có thể lớn hơn token ước lượng của đoạn trả lời hiển thị. Các model có reasoning tokens hoặc output đặc thù còn có cách accounting riêng của provider.

Không suy diễn `outputTokens=0` chỉ vì phần text hiển thị rỗng. Trước hết phải xem provider usage và trạng thái gọi mô hình.

## 3. Đường đi của Usage trong Spring AI

Spring AI 2.1.0 chuẩn hóa việc đọc usage qua `org.springframework.ai.chat.metadata.Usage` được trả trong metadata của `ChatResponse`.

~~~mermaid
flowchart TD
    Q["Câu hỏi + history + RAG context"] --> P["Prompt"]
    P --> M["ChatModel.call(prompt)"]
    M --> PR["Provider / model"]
    PR --> RES["ChatResponse"]
    RES --> META["getMetadata()"]
    META --> US["getUsage(): Usage"]
    US --> IN["getPromptTokens()"]
    US --> OUT["getCompletionTokens()"]
    US --> SUM["getTotalTokens()"]
    US --> CACHE["cache read / cache write"]
    US --> NATIVE["getNativeUsage()"]
    M --> OBS["Micrometer: gen_ai.client.operation"]
    OBS --> COUNTER["gen_ai.client.token.usage"]
~~~

| Phương thức trong `Usage` | Ý nghĩa | Kiểu |
| --- | --- | --- |
| `getPromptTokens()` | Token đầu vào | `Integer` |
| `getCompletionTokens()` | Token đầu ra | `Integer` |
| `getTotalTokens()` | Tổng tokens | `Integer` |
| `getCacheReadInputTokens()` | Số token đầu vào đọc từ prompt cache khi có | `Long`, có thể `null` |
| `getCacheWriteInputTokens()` | Số token đầu vào ghi vào prompt cache khi có | `Long`, có thể `null` |
| `getNativeUsage()` | Object usage gốc của provider | `Object`, có thể `null` |

`getTotalTokens()` có cách tính mặc định từ prompt và completion tokens; tùy implementation cũng có thể phản ánh tổng do provider báo. Dữ liệu usage phản ánh **quy ước accounting của provider**, không phải phép đo khách quan về chất lượng câu trả lời.

### 3.1. Ví dụ Java với ChatModel

~~~java
import org.springframework.ai.chat.metadata.Usage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;

public final class ModelUsageInspector {

    private final ChatModel model;

    public ModelUsageInspector(ChatModel model) {
        this.model = model;
    }

    public void inspect(String question) {
        ChatResponse response = model.call(new Prompt(question));

        if (response == null || response.getMetadata() == null) {
            System.out.println("Không có ChatResponse metadata");
            return;
        }

        Usage usage = response.getMetadata().getUsage();
        if (usage == null) {
            System.out.println("Không có usage để đọc");
            return;
        }

        Integer inputTokens = usage.getPromptTokens();
        Integer outputTokens = usage.getCompletionTokens();
        Integer totalTokens = usage.getTotalTokens();

        System.out.println("Input tokens: " + inputTokens);
        System.out.println("Output tokens: " + outputTokens);
        System.out.println("Total tokens: " + totalTokens);
    }
}
~~~

Đây là **ví dụ API**, chưa phải code đã chạy với provider. Khi ứng dụng dùng Spring Boot, có thể inject một bean `ChatModel` đã cấu hình; phải có API key/endpoint hợp lệ mới gọi model thật.

### 3.2. Đọc usage từ ChatClient

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.metadata.Usage;

// chatClient là ChatClient đã cấu hình.
ChatResponse response = chatClient.prompt()
        .user("Thời hạn đổi trả đơn online là bao lâu?")
        .call()
        .chatResponse();

if (response != null && response.getMetadata() != null) {
    Usage usage = response.getMetadata().getUsage();
    if (usage != null) {
        System.out.println(usage.getPromptTokens());
        System.out.println(usage.getCompletionTokens());
        System.out.println(usage.getTotalTokens());
    }
}
~~~

Chọn `chatResponse()` để giữ metadata. Lời gọi `call().content()` chỉ trả văn bản, không cung cấp trực tiếp `ChatResponseMetadata` cho tầng code hiện tại. `ChatClient.call()` đơn thuần chưa kích hoạt model cho đến khi dùng terminal method như `chatResponse()` hoặc `content()`.

## 4. Tổng token: khi nào được cộng, khi nào không?

Một tổng chuẩn thường được hiểu là:

~~~text
total = input + output
~~~

Ví dụ:

| Phần | Số token |
| --- | ---: |
| Input | 1.200 |
| Output | 160 |
| **Total** | **1.360** |

Lỗi phổ biến là lấy `input + output + total`, tạo kết quả 2.720 — **gấp đôi** mức sử dụng thực tế trong ví dụ.

### 4.1. Nếu các số không khớp?

Giả sử provider báo:

~~~text
input  = 900
output = 100
total  = 1050
~~~

Không nên tự sửa thành 1.000 trước khi kiểm tra. Có thể có khác biệt schema, usage đa phương thức, dữ liệu được tổng hợp không cùng cấp, hoặc adapter có logic bổ sung.

Cách điều tra:

1. Xác nhận ba giá trị thuộc **cùng model call/response**.
2. Kiểm tra chúng là **mỗi lượt** hay **tổng của một vòng ChatClient**.
3. Đọc usage gốc của provider nếu có.
4. Kiểm tra provider có tính cached/reasoning tokens theo quy tắc đặc thù không.
5. Xác minh response không phải chunk stream bị cộng lặp.
6. Lưu version Spring AI, SDK, provider/model và thời điểm.

Chỉ sau khi xác minh mới quyết định có lỗi adapter hay không. **Không âm thầm điều chỉnh usage** để bảng tổng trông hợp lý.

### 4.2. Phân biệt số liệu provider và số liệu ước lượng

`Usage` là metadata Spring AI lấy từ provider/adapter. Nếu một provider không báo usage, bạn có thể dùng tokenizer để **ước lượng** nhưng phải gắn nhãn `ESTIMATED`, không ghi thành `PROVIDER_REPORTED`. Ước lượng có thể sai khi prompt chứa tool schemas, multimodal hay token accounting đặc thù.

## 5. Không có usage khác với 0 token

Khi xây dashboard, cần phân biệt những tình huống sau:

| Trường hợp | Ý nghĩa cần báo cáo |
| --- | --- |
| Không có `ChatResponse` vì timeout/exception | Usage chưa xác định; cần trạng thái lỗi model riêng |
| `ChatResponseMetadata` rỗng | Thiếu metadata |
| `getUsage() == null` | Không có usage được báo |
| `getUsage() instanceof EmptyUsage` | `EmptyUsage` trả các số 0, có thể là placeholder thiếu dữ liệu |
| `getPromptTokens() == null` | Không có số token đầu vào |
| `getCompletionTokens() == null` | Không có số token đầu ra |
| Provider báo 0 có bằng chứng | Cần giải thích theo API provider, không tự gán là missing |
| Stream bị hủy trước khi có usage | Usage có thể thiếu hoặc chưa đầy đủ |

Trong Spring AI có implementation `EmptyUsage` trả 0 ở các getter. Nếu chỉ dựa trên `getTotalTokens()==0`, có thể nhầm placeholder “không có thông tin” với **lượt gọi thật sự tiêu 0 token**.

### 5.1. Java: tạo bản ghi phân loại usage

Đoạn code sau **do ứng dụng tự định nghĩa**, không phải API có sẵn của Spring AI. Nó giữ nguyên `null` khi thiếu dữ liệu:

~~~java
import org.springframework.ai.chat.metadata.EmptyUsage;
import org.springframework.ai.chat.metadata.Usage;

public final class UsageReader {

    public enum Status {
        REPORTED,
        PARTIAL,
        NOT_REPORTED
    }

    public record Snapshot(
            Status status,
            Integer input,
            Integer output,
            Integer total,
            Long cacheRead,
            Long cacheWrite) {
    }

    private UsageReader() {
    }

    public static Snapshot read(Usage usage) {
        if (usage == null || usage instanceof EmptyUsage) {
            return new Snapshot(
                    Status.NOT_REPORTED, null, null, null, null, null);
        }

        Integer input = usage.getPromptTokens();
        Integer output = usage.getCompletionTokens();
        Integer total = usage.getTotalTokens();
        Long cacheRead = usage.getCacheReadInputTokens();
        Long cacheWrite = usage.getCacheWriteInputTokens();

        if (input == null && output == null && total == null) {
            return new Snapshot(
                    Status.NOT_REPORTED, null, null, null,
                    cacheRead, cacheWrite);
        }

        Status status =
                input != null && output != null && total != null
                        ? Status.REPORTED
                        : Status.PARTIAL;

        return new Snapshot(
                status, input, output, total, cacheRead, cacheWrite);
    }
}
~~~

`REPORTED` chỉ có nghĩa cả ba trường tồn tại, **không chứng minh** provider độc lập đã báo cả ba hay các giá trị chắc chắn chính xác. Nếu dự án cần kiểm toán billing, còn phải lưu nguồn usage, raw provider response và chính sách retention phù hợp.

### 5.2. Unit test không cần gọi mô hình

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.ai.chat.metadata.DefaultUsage;
import org.springframework.ai.chat.metadata.EmptyUsage;

import static org.assertj.core.api.Assertions.assertThat;

class UsageReaderTest {

    @Test
    void readsThreeStandardValues() {
        var result = UsageReader.read(
                new DefaultUsage(1200, 160, 1360));

        assertThat(result.status())
                .isEqualTo(UsageReader.Status.REPORTED);
        assertThat(result.input()).isEqualTo(1200);
        assertThat(result.output()).isEqualTo(160);
        assertThat(result.total()).isEqualTo(1360);
    }

    @Test
    void distinguishesMissingUsage() {
        assertThat(UsageReader.read(null).status())
                .isEqualTo(UsageReader.Status.NOT_REPORTED);

        var empty = UsageReader.read(new EmptyUsage());
        assertThat(empty.status())
                .isEqualTo(UsageReader.Status.NOT_REPORTED);
        assertThat(empty.total()).isNull();
    }
}
~~~

Kết quả test chỉ xác nhận **đường xử lý Java**; nó không xác nhận một provider thực sự đã gửi token chính xác. Với Spring AI dependency khác phiên bản, kiểm tra lại constructor `DefaultUsage` và kiểu `Usage` tương ứng trước khi sao chép.

## 6. Cache tokens: đọc/ghi và nguy cơ cộng trùng

Prompt caching có thể giúp giảm latency hoặc chi phí khi các đoạn prompt được tái sử dụng. Spring AI 2.1.0 cung cấp accessor chung:

~~~java
Long cacheRead = usage.getCacheReadInputTokens();
Long cacheWrite = usage.getCacheWriteInputTokens();
~~~

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `cacheRead` | Token đầu vào được đọc từ cache theo provider | Có thể được tính phí mức khác |
| `cacheWrite` | Token đầu vào được ghi vào cache | Có thể chịu giá tạo cache |
| `null` | Không hỗ trợ hoặc không có báo cáo phù hợp | Không có nghĩa bằng 0 |
| `0` | Provider/adapter ghi 0 | Cần biết có thật sự hỗ trợ metric không |

Theo bảng hỗ trợ trong tài liệu Spring AI 2.1.0, ví dụ Anthropic và AWS Bedrock hỗ trợ cache read/write, OpenAI và Google Gemini có cache read qua adapter được mô tả. Điều này **phụ thuộc phiên bản** và không nói provider nhất thiết luôn có cache hit.

### 6.1. Cache read thường không phải token bổ sung

Ví dụ:

~~~text
Input tokens:                  1200
Output tokens:                  160
Total tokens:                  1360
Cached input tokens read:       800
~~~

Không tự tính tổng là `1360 + 800 = 2160`. Với nhiều provider, cached input là một **phần của input** được định giá khác. Nếu adapter/provider có semantics khác, cần xem tài liệu usage và hóa đơn để biết chính xác.

Tương tự, không tự cộng `cacheWrite` vào input token đã báo. Một số provider tính cache creation bằng cơ chế riêng; quy tắc tính giá phải được xác nhận trước khi ước lượng tiền.

### 6.2. Không lấy phép trừ làm mặc định cho mọi provider

Đôi khi công thức chi phí là:

~~~text
input_cost =
    uncached_input_tokens * ordinary_input_rate
  + cache_read_tokens    * cache_read_rate
  + cache_write_tokens   * cache_write_rate
~~~

Nhưng đây là **khung tư duy**, chỉ dùng được nếu các nhóm tokens không chồng lấp và provider xác nhận cách tách. Không tự tạo `uncached_input_tokens = input - cache_read - cache_write` cho mọi model khi chưa biết cache accounting.

## 7. Native usage: dữ liệu chi tiết theo provider

`Usage.getNativeUsage()` cho phép lấy object usage đặc thù từ SDK khi còn tồn tại. Ngoài input/output tiêu chuẩn, provider có thể báo:

- Cached tokens theo kiểu riêng.
- Reasoning tokens trong completion.
- Audio hoặc multimodal tokens.
- Token được chấp nhận/từ chối trong một số chế độ tạo sinh.
- Các nhóm usage khác có ảnh hưởng định giá.

Tài liệu Spring AI 2.1.0 đưa ra ví dụ với OpenAI Java SDK:

~~~java
// Phần này chỉ áp dụng nếu native usage là CompletionUsage
// từ OpenAI SDK tương ứng, không phải mọi provider.
if (usage.getNativeUsage()
        instanceof com.openai.models.completions.CompletionUsage nativeUsage) {

    nativeUsage.promptTokensDetails().ifPresent(details ->
        details.cachedTokens().ifPresent(tokens ->
            System.out.println("Cached = " + tokens)));

    nativeUsage.completionTokensDetails().ifPresent(details ->
        details.reasoningTokens().ifPresent(tokens ->
            System.out.println("Reasoning = " + tokens)));
}
~~~

**Không cast mù quáng** native usage của Anthropic, Ollama hoặc gateway thành OpenAI SDK object. Object native có thể khác loại hoặc là `null`. Khi nâng SDK/provider, cũng cần đối chiếu field names và types.

### 7.1. Dữ liệu chuẩn và dữ liệu gốc phục vụ hai mục tiêu

| Mục đích | Nguồn nên dùng |
| --- | --- |
| So sánh tổng input/output nhiều provider | Các getter tiêu chuẩn của `Usage` |
| Đọc cache portable | Các getter cache của `Usage` khi hỗ trợ |
| Điều tra reasoning/audio tokens | Native usage phù hợp provider |
| Chi phí theo loại token | Usage và quy tắc billing chính thức |
| Benchmark trên cùng dataset | Usage + model/prompt versions + quality labels |

Đừng cố thay hoàn toàn số liệu usage chuẩn bằng native object khi hệ thống dùng nhiều provider; phần native có thể không ghép được giữa các calls.

## 8. Vòng tool calling: usage cuối có thể đã được cộng dồn

Trong Spring AI 2.1.0, `ChatClient` khi điều phối **tool-calling loop** có thể gọi `ChatModel` nhiều lần rồi mới tạo câu trả lời cuối. Tài liệu nêu `response.getMetadata().getUsage()` của ChatClient response đã là usage **cộng dồn qua tất cả model calls** trong trao đổi đó.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant CC as ChatClient
    participant M as ChatModel
    participant T as Tool
    U->>CC: Hỏi trạng thái đơn
    CC->>M: Model call #1
    M-->>CC: Gọi tool + usage #1
    CC->>T: getOrderStatus
    T-->>CC: Tool result
    CC->>M: Model call #2
    M-->>CC: Answer + usage #2
    CC-->>U: ChatResponse + aggregate usage
~~~

Ví dụ giả định:

| Cấp | Input | Output | Total |
| --- | ---: | ---: | ---: |
| Model call #1 | 500 | 50 | 550 |
| Model call #2 | 800 | 120 | 920 |
| **ChatClient aggregate** | **1300** | **170** | **1470** |

Nếu cần tổng token của **một trao đổi ChatClient**, dùng 1470. **Không cộng tiếp 550 và 920 vào 1470**, vì hai lượt đó đã được tính.

### 8.1. Vì sao native usage có thể bằng null sau tool loop?

Spring AI có `UsageCalculator` để gộp các token tiêu chuẩn và cache counters. Nhưng object native của provider không thể gộp xuyên nhiều phản hồi một cách tổng quát. Khi `ChatClient` đã tổng hợp usage nhiều model calls, **`getNativeUsage()` trả `null`** theo tài liệu.

Do đó:

~~~text
aggregate.getPromptTokens()      = có thể là tổng input
aggregate.getCompletionTokens()  = có thể là tổng output
aggregate.getTotalTokens()       = có thể là tổng của toàn loop
aggregate.getNativeUsage()       = null sau multi-call aggregate
~~~

**Native null không có nghĩa usage tiêu chuẩn bị thiếu.** Nếu cần native usage cho từng lượt, thu trực tiếp ở từng `ChatModel` call, rồi gắn vào các events riêng của workflow.

### 8.2. Chọn đúng cấp tổng hợp

| Cấp | Mẫu số | Cách đo |
| --- | --- | --- |
| **Model call** | Một lời gọi model | Usage của provider cho lượt đó |
| **ChatClient exchange** | Một vòng trao đổi, có thể chứa tool calls | Usage đã tổng hợp của ChatClient |
| **Evaluation case** | Một case có answer, judge, RAG/tools | Tổng do ứng dụng định nghĩa từ các phần không chồng lấp |
| **Batch/dataset** | Nhiều case | Cộng các case đã đo đủ; báo cáo missing |

Khi một case gọi thêm `RelevancyEvaluator` hoặc fact checker sau khi trả lời, lượt judge **không mặc nhiên nằm trong usage của answer ChatClient**. Để tính toàn bộ chi phí case, tính các thành phần riêng theo `workflow_role=answer`, `judge`, `embedding` ... rồi tổng hợp **không trùng lặp**.

## 9. Streaming: không cộng tokens của từng chunk một cách máy móc

Với `ChatClient.stream().chatResponse()`, ứng dụng nhận một `Flux<ChatResponse>`. Các event có thể mang một phần text hoặc metadata, và usage có thể xuất hiện khác nhau theo provider/adapter.

**Không làm như sau:**

~~~java
// Phản ví dụ: có thể NullPointerException hoặc đếm trùng
// nếu provider phát số usage cộng dồn ở nhiều chunk.
long total = chunks.stream()
        .mapToLong(c -> c.getMetadata()
                .getUsage().getTotalTokens())
        .sum();
~~~

Đây là code **sai về giả định**, không phải ví dụ sử dụng được. Một số chunk có thể không có metadata; số usage cuối có thể không phải phần tăng mới cho từng chunk.

### 9.1. Cách xử lý an toàn

1. Dùng `Flux<ChatResponse>` thay cho `Flux<String>` khi cần metadata.
2. Kiểm tra provider/SDK có gửi usage vào chunk cuối hay không.
3. Ưu tiên response đã tổng hợp bởi API/aggregator được hỗ trợ, nếu có.
4. Nếu tự gom, định nghĩa rõ logic xác định usage của **toàn lượt**, tránh cộng cùng tổng nhiều lần.
5. Với stream bị `CANCEL` hoặc `ON_ERROR`, ghi thiếu/chưa đầy đủ thay vì gán token bằng 0.
6. Đối chiếu provider billing khi đòi hỏi thông tin chi phí chính xác.

Đo `time to first token` hoặc full-stream latency là việc khác với đọc token usage. Một stream xuất text sớm không có nghĩa đã biết tổng tokens trước khi luồng kết thúc.

### 9.2. Lượt stream bị hủy có thể vẫn bị tính phí

Một client cancel giữa chừng có thể không bao giờ nhận usage đầy đủ, dù provider đã xử lý prompt và sinh một phần output. Đừng lấy số ký tự đã hiển thị làm số token chắc chắn được tính phí.

~~~text
streamStatus = CANCELLED
usageStatus = UNKNOWN_OR_PARTIAL
providerInvoice = cần đối chiếu nếu có yêu cầu kiểm toán
~~~

Các tên trạng thái là **quy ước ứng dụng minh họa**, không phải enum Spring AI.

## 10. Token usage trong Micrometer và Prometheus

Spring AI cung cấp metric `gen_ai.client.token.usage` cho các model calls được instrument. Trong Prometheus, counter thường xuất dưới tên:

~~~text
gen_ai_client_token_usage_total
~~~

Theo Spring AI Metrics Reference 2.1-SNAPSHOT, counter dùng nhãn `gen_ai_token_type`:

| Giá trị nhãn | Ý nghĩa |
| --- | --- |
| `input` | Token đầu vào |
| `output` | Token đầu ra |
| `total` | Tổng token |
| `gen_ai_operation_name=chat` | Chỉ lọc thao tác model chat |
| `gen_ai_system` | Provider do instrumentation xác định |
| `gen_ai_request_model` | Model được yêu cầu |
| `gen_ai_response_model` | Model được phản hồi báo về nếu có |

**Provider không trả token usage thì lượt gọi đó không làm tăng counter token usage.** Timer `gen_ai.client.operation` vẫn có thể đếm lời gọi. Vì vậy, dashboard cần phân biệt “không có usage” và “usage bằng 0”.

### 10.1. Khác biệt giữa response usage và metric

- `response.getMetadata().getUsage()` là số token cho **một response/trao đổi**.
- `gen_ai_client_token_usage_total` là **counter tích lũy** của các model calls theo tags và thời gian.

Không đưa cả token counter lẫn usage ChatClient aggregate vào một số tổng mà không chọn cấp đo. Nếu model calls bên dưới ChatClient đã được counter ghi nhận, usage ChatClient tổng hợp không phải một lượt token mới.

Các thuộc tính như `gen_ai.usage.input_tokens` trong traces thuộc nhóm high-cardinality observation details; **không mặc nhiên là label của timer**. Muốn biểu đồ token, dùng metric token usage chuyên dụng.

## 11. PromQL: đọc input, output và total

Với Spring Boot Actuator và Prometheus registry được cấu hình:

~~~bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/prometheus
~~~

Đây là **lệnh hướng dẫn tự kiểm tra**, không phải kết quả chạy trong workspace. Kiểm tra series thật trước khi chép PromQL, vì version/registry có thể chuẩn hóa tên nhãn khác nhau.

**Token input và output mỗi phút theo model:**

~~~promql
sum by (gen_ai_system, gen_ai_request_model, gen_ai_token_type) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type=~"input|output"
  }[5m])
) * 60
~~~

**Tổng token mỗi phút theo model:**

~~~promql
sum by (gen_ai_system, gen_ai_request_model) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="total"
  }[5m])
) * 60
~~~

Chỉ sử dụng series `total` khi provider báo đúng; nếu không có total nhưng có input/output, có thể tổng hợp từ hai loại. **Không cộng input + output + total.**

### 11.1. Tỷ lệ input/output

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="input"
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="output"
  }[5m])
)
~~~

Tỷ lệ cao thường là dấu hiệu prompt/context dài so với output, nhưng chưa chứng minh retriever kém. Mẫu số `output` có thể bằng 0 hoặc không có series, khi đó biểu đồ cần hiển thị “không đủ dữ liệu”.

### 11.2. Token trung bình trên tất cả model calls

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_token_usage_total{
    gen_ai_operation_name="chat",
    gen_ai_token_type="total"
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

**Cảnh báo về coverage:** tử số chỉ tăng khi provider báo usage, mẫu số có thể đếm cả những calls không có usage. Vì vậy phép chia này đo **token báo cáo được trên một model call hoàn tất**, không phải trung bình chính xác token sử dụng của mọi calls nếu missing rate đáng kể.

Nếu muốn `average_token_per_reported_call`, phải thu thêm bộ đếm **số calls có usage hợp lệ** ở tầng ứng dụng hoặc hệ thống quan sát phù hợp.

## 12. Ước lượng chi phí mà không nhầm với hóa đơn

Với provider định giá theo triệu token:

~~~text
estimated_cost =
    input_tokens / 1_000_000 * input_price_per_million
  + output_tokens / 1_000_000 * output_price_per_million
~~~

Ví dụ **giá hoàn toàn giả định**:

| Loại | Giá |
| --- | ---: |
| Input | 1,50 USD / triệu token |
| Output | 6,00 USD / triệu token |

Với 1.200 input, 160 output:

~~~text
Input  = 1200 / 1_000_000 * 1.50 = 0.00180 USD
Output =  160 / 1_000_000 * 6.00 = 0.00096 USD
Tổng ước tính                   = 0.00276 USD
~~~

Các mức giá trên **không phải giá thực tế của bất kỳ provider nào**.

### 12.1. Những lý do ước tính khác hóa đơn

- Cache read/write có đơn giá riêng.
- Reasoning, audio, image hoặc output đặc thù được tính khác.
- Retry, tool calling, một request gọi nhiều model.
- Provider không báo đầy đủ usage cho cuộc gọi lỗi/hủy stream.
- Model alias hoặc model response khác với tên cấu hình.
- Khu vực, tài khoản, pricing tier, thời điểm và làm tròn.

Để truy vết chi phí, hãy lưu phiên bản bảng giá, provider/model, usage provenance và tình trạng missing. **Không dùng `totalTokens` với một mức đơn giá duy nhất** khi input/output có giá khác.

## 13. Ghép usage với chất lượng RAG và độ trễ

Một số tình huống đáng điều tra:

| Tín hiệu | Giả thuyết | Cần xem thêm |
| --- | --- | --- |
| Input tokens tăng sau đổi RAG | `topK`, chunk size hoặc chat history tăng | Document context, retriever config, prompt version |
| Output tăng | Model giải thích dài hơn hoặc có tool calls | Answer, tool events, finish reason |
| Total tăng mà pass rate không tăng | Context dư thừa hoặc pipeline chưa hiệu quả | Relevance, fact checking, nhãn chuyên gia |
| Tokens giảm, quality giảm | Cắt mất chunk quan trọng hoặc giới hạn output | Retrieval coverage, `TRUNCATED` |
| Latency tăng, tokens ổn định | Provider/network/concurrency/retry thay đổi | Traces, HTTP, runtime metrics |
| Cost tăng, tokens không đổi | Giá/model/cache mix thay đổi | Pricing version, cache breakdown |
| Usage ChatClient lớn hơn call cuối | Có tool loop | Các child model calls, aggregate logic |

Ví dụ thử trên cùng 50 case:

| Chỉ số giả lập | Pipeline A | Pipeline B |
| --- | ---: | ---: |
| Mean input tokens/case | 1.100 | 1.850 |
| Mean output tokens/case | 150 | 145 |
| Relevance pass rate | 82% | 84% |
| P95 model latency | 1,4 giây | 2,2 giây |
| Retrieval source coverage | 88% | 89% |

Pipeline B sử dụng nhiều input hơn để đổi lấy cải thiện chất lượng nhỏ trong dữ liệu minh họa. Không thể kết luận B “không đáng tiền” trước khi xem ý nghĩa nghiệp vụ của các case cải thiện, giá model và độ bất định của judge.

Khi **so sánh answer prompt/model**, cố định judge model/rubric và dataset. Nếu thay judge cùng lúc, pass rate có thể đổi do **thước đo**, không phải answer model.

### 13.1. Trường hợp vừa trả lời vừa chấm

Một case RAG có thể có:

~~~text
1 user request
  - Embedding query
  - Vector search
  - ChatModel answer #1
  - Có thể ChatModel answer #2 sau tool call
  - RelevancyEvaluator judge model call
  - Có thể FactCheckingEvaluator judge model call
~~~

Không có một con số `ChatModel.getUsage()` duy nhất bao gồm **tất cả** các bước trên. Hãy gắn vai trò `answer`, `judge`, `embedding` và quy ước tổng riêng cho case. Đừng lẫn **chi phí trả lời online** với **chi phí chấm offline**.

## 14. Bản ghi usage nên chứa những gì?

Ví dụ JSON do ứng dụng tự thiết kế:

~~~json
{
  "caseId": "return-policy-047",
  "datasetVersion": "rag-eval-v6",
  "workflowRole": "answer",
  "provider": "example-provider",
  "requestedModel": "chat-alias-v2",
  "reportedModel": "chat-model-revision-A",
  "promptVersion": "answer-prompt-v9",
  "retrieverVersion": "retriever-v5",
  "usageStatus": "REPORTED",
  "inputTokens": 1200,
  "outputTokens": 160,
  "totalTokens": 1360,
  "cacheReadInputTokens": 800,
  "cacheWriteInputTokens": null,
  "latencyMs": 1130,
  "finishCategory": "COMPLETED"
}
~~~

Đây **không phải payload Spring AI tự xuất**. Các trường `caseId`, dataset, role và versions do tầng workflow cung cấp.

Các nguyên tắc lưu dữ liệu:

1. Gắn usage vào **đúng lời gọi model** hoặc đúng aggregate exchange.
2. Lưu usage source/status: reported, partial, missing, estimated.
3. Với aggregate tool loop, không cộng lại với các child model calls.
4. Với case evaluation, giữ answer và judge usage tách biệt.
5. Đánh dấu streaming cancel/error và độ tin cậy của usage.
6. Lưu model request/response, provider và pricing version.
7. Không đưa raw prompt, PII và tài liệu nội bộ vào metrics chỉ để đo token.

## 15. Chất lượng dữ liệu và bảo mật telemetry

Nhãn metric nên có tập giá trị giới hạn như `gen_ai.system`, `gen_ai.operation.name`, `gen_ai.token.type`, `workflow.role` hoặc nhóm model đã kiểm soát.

**Không dùng** user ID, email, số điện thoại, order ID, API key, request UUID, raw prompt hoặc raw response làm low-cardinality metric labels. Điều đó vừa có nguy cơ rò rỉ dữ liệu vừa gây bùng nổ số time series.

Spring AI mặc định không xuất nội dung prompt và completion, vì có thể nhạy cảm. Không cần bật ghi nội dung để đọc token usage:

~~~properties
spring.ai.chat.observations.log-prompt=false
spring.ai.chat.observations.log-completion=false
spring.ai.chat.client.observations.log-prompt=false
spring.ai.chat.client.observations.log-completion=false
~~~

Nếu thật sự cần log chi tiết để điều tra một lỗi, hãy dùng test data không nhạy cảm, redaction, quyền truy cập và chính sách lưu giữ phù hợp.

### 15.1. Theo dõi độ đầy đủ của dữ liệu usage

Một ứng dụng có thể bổ sung metrics riêng:

| Metric ứng dụng tự định nghĩa | Mục đích |
| --- | --- |
| `usage_reported_calls` | Số calls có usage đầy đủ |
| `usage_partial_calls` | Số calls chỉ có một phần số liệu |
| `usage_missing_calls` | Số calls không có usage |
| `usage_inconsistent_calls` | Dữ liệu khác định nghĩa kỳ vọng |
| `usage_aggregated_exchanges` | Trao đổi ChatClient đã gộp nhiều calls |
| `pricing_rule_missing` | Không có giá áp dụng cho model/thời điểm |

Các tên này chỉ là **thiết kế gợi ý**, không phải metric mặc định của Spring AI. Dashboard token phải cho biết **tỷ lệ calls có usage**, tránh đọc thiếu thành rẻ.

## 16. Lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `getUsage() == null` | Provider/adapter không báo | Ghi missing, đọc model metadata |
| Tổng bằng 0 ở mọi lượt | `EmptyUsage` hoặc mock | Kiểm tra kiểu usage và đường gọi thực |
| Total gấp đôi | Cộng input + output + total | Chọn total **hoặc** input + output |
| Tool loop bị tính đôi | Cộng ChatClient aggregate với child calls | Chọn đúng cấp tính |
| `getNativeUsage() == null` sau tool loop | Native object không gộp được | Đọc native ở từng ChatModel call |
| Token cache làm tổng tăng bất thường | Cộng cache read/write lên tổng | Xem provider cache accounting |
| Stream token tăng theo số chunk | Cộng usage từ mọi chunk | Dùng aggregate hợp lệ |
| Stream bị cancel, usage thiếu | Không có metadata cuối | Ghi `UNKNOWN_OR_PARTIAL`, đối chiếu billing |
| Token metric ít hơn số thực | Provider thiếu usage hoặc calls lỗi | Theo dõi coverage và retries |
| Output text ngắn nhưng output tokens cao | Reasoning/tool/multimodal | Kiểm tra native usage và request |
| Input tăng sau đổi RAG | Thêm context/history/tool schema | So versions và số chunk |
| Cost tăng dù tokens ổn định | Giá/alias/cache thay đổi | Đối chiếu pricing và model identity |
| Pass rate giảm dù token không đổi | Lỗi ngữ nghĩa hoặc judge drift | Dataset, source, answer và judge |
| PromQL không có series | Chưa cài exporter, chưa gọi model hoặc thiếu usage | Xem `/actuator/prometheus` |

## 17. Bài tập thực hành

### Bài 1. Đọc ba trường Usage

Tạo một service gọi `ChatModel.call(new Prompt(...))` và đọc `getPromptTokens()`, `getCompletionTokens()`, `getTotalTokens()`. Ghi lại khi provider không có usage thay vì tự mặc định 0.

### Bài 2. Viết unit test UsageReader

Dùng `new DefaultUsage(1200, 160, 1360)` và `new EmptyUsage()`. Thử trường hợp usage thiếu, số liệu một phần, ba trường không khớp và có cache tokens. Thiết kế bước kiểm tra thay vì sửa usage âm thầm.

### Bài 3. Kiểm thử tool calling

Cấu hình `ChatClient` với một tool lấy thông tin đơn hàng. Đọc usage cuối từ `chatResponse()` và đối chiếu với các lượt ChatModel riêng nếu có instrumentation. Giải thích vì sao **không cộng tổng hai cấp**.

### Bài 4. Streaming

Đo một stream hoàn tất và một stream bị hủy. Kiểm tra khi nào metadata usage xuất hiện, có lặp lại trong các chunk hay không. Nêu cách tránh tính trùng và cách biểu diễn missing/partial.

### Bài 5. Xây dashboard Prometheus

Tạo panel input, output, total tokens/phút theo provider/model. Chỉ dùng các nhãn và series thực xuất từ ứng dụng. Thêm biểu đồ usage coverage nếu có metric riêng.

### Bài 6. Đo RAG

Chạy 30 case có nhãn chuyên gia, giữ judge model/rubric cố định, thay `topK` hoặc chunk size. So input/output/total usage, source coverage, relevance pass rate và latency. Phân tích những case tốn thêm token mà chất lượng không cải thiện.

### Bài 7. Ước lượng chi phí

Với giá giả định input 1,50 USD/triệu token và output 6 USD/triệu token, tính chi phí 1.200 input + 160 output. Sau đó giả định 800 input tokens được đọc cache; nêu rõ quy tắc provider trước khi tính giảm chi phí.

## 18. Tổng kết

Trong Spring AI, đọc usage từ `ChatResponseMetadata.getUsage()` với ba trường chính:

- `getPromptTokens()` — token đầu vào.
- `getCompletionTokens()` — token đầu ra.
- `getTotalTokens()` — tổng mức sử dụng.

Cache read/write và native usage bổ sung chi tiết khi provider hỗ trợ. **Số 0 khác với thiếu dữ liệu; tổng token khác với input + output + total; usage của ChatClient tool loop khác với usage của từng model call.**

Metric `gen_ai.client.token.usage` và `gen_ai_client_token_usage_total` giúp giám sát theo provider/model, nhưng chúng chỉ phản ánh các lượt provider có báo usage. Khi kết hợp với dataset, relevance, fact checking, RAG context, traces, latency và bảng giá theo phiên bản, bạn có thể đánh giá liệu tăng token có cải thiện chất lượng hay chỉ làm pipeline tốn tài nguyên hơn.

## Tài liệu tham khảo

- [Spring AI 2.1.0 Reference — Chat Response Metadata / Usage](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): các API `Usage`, cache metrics, native usage và usage cộng dồn trong tool calling.
- [Spring AI 2.1.0 API — Usage](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/metadata/Usage.html): kiểu dữ liệu và semantics của các phương thức.
- [Spring AI API — EmptyUsage](https://docs.spring.io/spring-ai/docs/current/api/org/springframework/ai/chat/metadata/EmptyUsage.html): implementation trả các giá trị 0, cần phân biệt dữ liệu thiếu.
- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): metrics/traces cho `ChatModel`.
- [Spring AI 2.1-SNAPSHOT — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): counter `gen_ai_client_token_usage_total`, token type tags, PromQL.
- [Spring AI Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): `chatResponse()`, streaming và metadata.
