# Quan sát mô hình: Theo dõi thời lượng, trạng thái kết thúc và lỗi

## 1. Tại sao cần theo dõi đồng thời ba tín hiệu?

Khi ứng dụng Spring AI gọi một mô hình chat, câu hỏi vận hành không chỉ là **“mô hình phản hồi trong bao lâu?”**. Một lượt gọi hoàn thành rất nhanh vẫn có thể bị cắt giữa chừng do giới hạn token; một lượt gọi trả văn bản từ chối có thể là hành vi hợp lệ theo chính sách; và một lời gọi timeout có thể không tạo được `ChatResponse` nào để đọc lý do kết thúc.

Bởi vậy, muốn quan sát đúng `ChatModel` cần kết hợp ba nhóm thông tin:

1. **Thời lượng (duration/latency):** thao tác model mất bao lâu, đang chạy hay đã kết thúc, có độ trễ đuôi dài không?
2. **Trạng thái kết thúc của quá trình sinh (finish reason):** mô hình dừng vì hoàn tất, hết giới hạn đầu ra, yêu cầu gọi công cụ, bị lọc an toàn hay không nêu lý do?
3. **Lỗi kỹ thuật (error/exception):** có timeout, từ chối xác thực, quá quota, lỗi mạng hoặc exception do provider/SDK hay không?

Đây là nội dung của chương **Quan sát mô hình** thuộc module `SPRING_AI_EVALUATION_OBSERVABILITY`. Toàn module đặt các chỉ số này cạnh tập dữ liệu đánh giá, tiêu chí relevance, fact checking và kiểm thử luồng RAG hoặc gọi công cụ; mục tiêu là phát hiện vì sao chất lượng, chi phí hoặc latency thay đổi sau khi nâng phiên bản prompt, model và pipeline.

Ví dụ, một bộ đánh giá có thể ghi nhận tỷ lệ câu trả lời đạt giảm từ 90% xuống 75%. Từ một con số đó, chưa biết nguyên nhân là retriever lấy sai nguồn, model tạo phản hồi không phù hợp, prompt ràng buộc đầu ra quá ngắn, hay các lượt gọi judge gặp lỗi. Thời lượng, finish reason và exception giúp **khoanh vùng**, nhưng vẫn phải kiểm tra dữ liệu và phản hồi thực tế trước khi kết luận.

**Mục tiêu học tập:**

- Phân biệt `gen_ai.client.operation` với các observation `ChatClient`, tool, advisor và HTTP.
- Đọc timer `count/sum/max`, số thao tác đang chạy và histogram P95/P99.
- Đọc `ChatGenerationMetadata.getFinishReason()` và nhóm `getFinishReasonCategory()` của Spring AI 2.1.x.
- Phân loại `COMPLETED`, `TRUNCATED`, `TOOL_CALL`, `FILTERED`, `OTHER` và `UNSPECIFIED` đúng ý nghĩa.
- Tách các **kết quả mô hình hợp lệ về giao thức** khỏi **lỗi gọi model**, **lỗi chuyển đổi dữ liệu** và **lỗi chất lượng nội dung**.
- Viết Java instrumentation và kiểm thử hồi quy cho các trường hợp kết thúc khác nhau.
- Thiết kế dashboard/alerts và bảo vệ dữ liệu riêng tư trong traces/metrics.

## 2. Ba loại “kết thúc” khác nhau

Trong thực tế, một request có thể “kết thúc” theo ba tầng khác nhau.

| Tầng | Ví dụ | Ý nghĩa | Không đồng nghĩa với |
| --- | --- | --- | --- |
| **Vòng đời lời gọi model** | Micrometer timer dừng và ghi duration | Lượt `ChatModel` đã hoàn tất, lỗi hoặc bị hủy theo đường thực thi quan sát được | Câu trả lời đã đúng hoặc đủ |
| **Lý do model ngừng sinh** | `stop`, `length`, `tool_calls`, `content_filter` | Provider/model cho biết vì sao generation dừng | Thành công/thất bại của HTTP |
| **Kết quả nghiệp vụ** | `RelevancyEvaluator.isPass()`; test fact checking | Phản hồi có đáp ứng tiêu chí chất lượng không | Lời gọi provider có exception hay không |

Ví dụ:

~~~text
HTTP request:          200 OK
ChatModel operation:   0,8 giây, không exception
Finish reason:         length
Answer:                "Thời hạn hoàn trả là..."
Chất lượng:            FAIL vì câu trả lời bị cắt, thiếu thông tin
~~~

Trường hợp trên không phải lỗi giao tiếp HTTP. Model có thể trả một `ChatResponse` hợp lệ với lý do dừng `TRUNCATED`. Muốn sửa, xem giới hạn output tokens, độ dài prompt, chi phí và dữ liệu đầu vào.

Trường hợp khác:

~~~text
HTTP request:          429 Too Many Requests
ChatModel operation:   exception hoặc retry
Finish reason:         không có, vì chưa nhận generation hợp lệ
Chất lượng:            không chấm được lượt này
~~~

Không gán `finishReason="ERROR"` như thể đó là giá trị do provider trả: đây là **lỗi kỹ thuật**, cần một trạng thái riêng ở tầng ứng dụng.

~~~mermaid
flowchart TD
    U["User request / evaluation case"] --> C["ChatClient / pipeline"]
    C --> M["ChatModel: gen_ai.client.operation"]
    M --> P["Provider / gateway"]
    P --> D{"Lời gọi trả ChatResponse?"}
    D -->|"Có"| G["Generation metadata"]
    G --> F["Finish reason / category"]
    F --> V["Đánh giá nội dung và tính đầy đủ"]
    D -->|"Exception"| E["Lỗi: timeout, quota, network, auth"]
    E --> O["Ghi status lỗi và duration"]
    V --> O2["Ghi quality result và duration"]
    O --> R["Báo cáo nhiều chiều"]
    O2 --> R
~~~

Sơ đồ là mô hình phân tích do ứng dụng xây dựng. Spring AI không tự xuất sẵn tất cả trạng thái tổng hợp trong hình thành một enum.

## 3. Thời lượng được đo ở đâu?

Trong Spring AI, các implementation `ChatModel` có instrumentation tạo observation `gen_ai.client.operation` cho `call(...)` và `stream(...)`. Observation giúp Micrometer ghi duration và nối trace context với các thao tác xung quanh.

Các tầng đo phổ biến:

| Tầng quan sát | Tên thường gặp | Độ trễ phản ánh |
| --- | --- | --- |
| Request API của ứng dụng | Tên HTTP server observation tùy Spring Boot | Người dùng chờ toàn bộ request |
| `ChatClient` | `spring.ai.chat.client` | Lời gọi client, có thể bao gồm advisor |
| Advisor/RAG | `spring.ai.advisor` | Bước advisor và các thao tác con |
| Vector store | `db.vector.client.operation` | Truy vấn/ghi dữ liệu vector |
| `ChatModel` | `gen_ai.client.operation` | Thao tác gọi model theo provider |
| HTTP SDK/provider | Ví dụ `okhttp.requests` ở provider hỗ trợ | Một HTTP attempt tới API/gateway |
| Tool execution | `spring.ai.tool` | Lượt gọi công cụ ở nơi được instrument |

**Các span có thể lồng nhau.** Không cộng duration của `ChatClient` + `ChatModel` + HTTP span để tính tổng thời gian, vì thời gian con đã nằm trong thời gian cha. Nếu một request gọi model nhiều lần do tool calling, judge hoặc retry, hãy phân tích cả số lượng lượt gọi.

### 3.1. Duration của call khác latency người dùng cảm nhận

Một pipeline minh họa:

~~~text
HTTP /api/ask                 2.60 s
  ChatClient                  2.38 s
    Retrieval advisor         0.42 s
      Vector query            0.29 s
    ChatModel #1              0.88 s
    Tool execution            0.15 s
    ChatModel #2              0.71 s
  Application formatting      0.11 s
~~~

Đây là số liệu và cấu trúc **giả định**, không phải trace thực. Với bộ RAG có thêm `RelevancyEvaluator` chạy đồng bộ, có thể còn một lượt ChatModel của **judge**, làm tăng end-to-end latency.

Khi cần đo:

- **Latency model**: dùng `gen_ai.client.operation`.
- **Latency retrieval**: dùng observation vector store/advisor phù hợp.
- **Latency response của người dùng**: dùng span HTTP/application bao trùm toàn bộ xử lý.
- **Latency của đánh giá offline**: đo cả orchestration của bộ chấm, không chỉ model call.
- **Time to first token (TTFT)** khi streaming: cần phép đo riêng cho chunk đầu, không suy ra từ duration khi luồng kết thúc.

### 3.2. Streaming và thời lượng

Khi gọi `stream(...)`, mô hình có thể gửi token sớm nhưng tiếp tục sinh lâu. Ví dụ:

~~~text
Thời điểm subscribe:       0 ms
Chunk đầu tiên:          180 ms
Chunk cuối cùng:       1.920 ms

TTFT minh họa:            180 ms
Full-stream time:       1.920 ms
~~~

Hai đại lượng đo trải nghiệm khác nhau: người dùng có thể thấy chữ rất sớm dù luồng kéo dài. Khi lưu số liệu, cần quy định rõ timestamp bắt đầu, timestamp chunk đầu, timestamp kết thúc và đường xử lý `cancel`/`error`.

Duration observation của `ChatModel.stream(...)` **không mặc nhiên bằng TTFT**. Một số provider/SDK còn xử lý stream trên thread khác, ảnh hưởng quan hệ cha-con của HTTP spans.

## 4. Metrics mặc định: số lượt, tổng thời gian và thao tác đang chạy

Spring AI sử dụng Micrometer Observation và các meter được exporter chuyển thành series Prometheus. Tên observation gốc:

~~~text
gen_ai.client.operation
~~~

Các series Prometheus tiêu biểu:

| Series | Loại đo | Cách đọc |
| --- | --- | --- |
| `gen_ai_client_operation_seconds_count` | Timer count | Số **thao tác đã kết thúc được ghi nhận** |
| `gen_ai_client_operation_seconds_sum` | Timer sum | Tổng duration của các thao tác đã kết thúc (giây) |
| `gen_ai_client_operation_seconds_max` | Timer max | Duration lớn nhất theo cửa sổ/registry |
| `gen_ai_client_operation_active_seconds_count` | Long-task timer gauge | Số thao tác đang chạy trong phiên bản/exporter hỗ trợ |
| `gen_ai_client_operation_active_seconds_sum` | Long-task timer gauge | Tổng thời gian đã chạy của các thao tác hiện còn active |
| `gen_ai_client_operation_active_seconds_max` | Long-task timer gauge | Thao tác active lâu nhất |

Tên `active` ở vài phiên bản Spring AI/Micrometer được mô tả khác nhau. Trước khi viết query, hãy **đọc series thật tại `/actuator/prometheus`**. `_seconds_count` không chỉ đếm thành công; lượt lỗi cũng có thể được ghi duration và nhãn lỗi.

Với metrics của model, các low-cardinality keys thường có:

- `gen_ai.operation.name=chat`.
- `gen_ai.system` — nhà cung cấp do model instrumentation nhận diện.
- `gen_ai.request.model` — model được yêu cầu.
- `gen_ai.response.model` — model được phản hồi báo về khi có.
- `error` — nhãn lỗi Micrometer; trong trang metrics Spring AI 2.1-SNAPSHOT, giá trị thường là loại exception hoặc `none`.

**Không đặt `gen_ai.response.finish_reasons` ngang hàng với các nhãn timer trên.** Spring AI liệt kê finish reasons trong **high-cardinality attributes của trace**; chúng không phải một nhãn timer mặc định bảo đảm có thể lọc trực tiếp bằng Prometheus.

### 4.1. Hai phép tính cơ bản

Trên một khoảng đo:

~~~text
completed_model_calls = delta(seconds_count)

mean_model_latency_seconds =
    delta(seconds_sum) / delta(seconds_count)
~~~

Ví dụ giả định có 50 cuộc gọi đã hoàn tất tổng cộng 75 giây thời gian model:

~~~text
mean_model_latency = 75 / 50 = 1,5 giây/lượt gọi
~~~

Mean có thể che đuôi dài. Nếu 49 lượt rất nhanh và một lượt mất 30 giây, mean chưa phản ánh đủ trải nghiệm người dùng. Muốn xem P95/P99, cần phân phối duration.

## 5. PromQL: đo throughput, mean latency, error rate và P95

Những query sau là **ví dụ** dựa trên tên series Spring AI 2.1.x khi được Prometheus exporter xuất đúng các nhãn tương ứng. Không phải kết quả đã chạy trong repository.

**Số thao tác chat/giây theo provider:**

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

**Độ trễ trung bình theo provider:**

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

**Số lượt lỗi model/giây theo provider và loại exception:**

~~~promql
sum by (gen_ai_system, error) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat",
    error!="none",
    error!=""
  }[5m])
)
~~~

**Tỷ lệ lời gọi model có lỗi**, nếu timer thực sự có nhãn `error` với semantics trên:

~~~promql
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat",
    error!="none",
    error!=""
  }[5m])
)
/
sum by (gen_ai_system) (
  rate(gen_ai_client_operation_seconds_count{
    gen_ai_operation_name="chat"
  }[5m])
)
~~~

Mẫu số của phép tính là **model operations**, không phải user requests. Lỗi bị retry ở tầng SDK/gateway có thể được quan sát ở tầng HTTP attempts khác với model operation; kiểm tra khả năng đếm mỗi retry trước khi so sánh.

### 5.1. P95/P99 cần histogram

`seconds_sum / seconds_count` không tính được percentile. Theo hướng dẫn metrics Spring AI 2.1-SNAPSHOT, có thể bật histogram cho timer:

~~~properties
management.metrics.distribution.percentiles-histogram.gen_ai.client.operation=true
~~~

Khi thực tế xuất ra `gen_ai_client_operation_seconds_bucket`:

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

Nếu không có series `_bucket`, query trên không trả kết quả hợp lệ: cần xác nhận exporter, config, histogram buckets và version trước khi tạo dashboard. Với provider chỉ có vài lượt gọi, P95 trong cửa sổ 5 phút có thể rất nhiễu.

### 5.2. Thao tác đang chạy và đã kết thúc

Dữ liệu `active` đặc biệt hữu ích để điều tra request treo:

~~~promql
sum by (gen_ai_system) (
  gen_ai_client_operation_active_seconds_count
)
~~~

Query chỉ áp dụng khi registry/exporter đang xuất đúng tên này. **`active_seconds_count` là gauge số thao tác đang chạy**, không phải số lượt hoàn tất. Một thao tác đang active lâu chưa có mặt trong số liệu duration của các thao tác đã hoàn tất. Trong môi trường có streaming dài, nên đọc cả hai loại số liệu.

## 6. Finish reason: vì sao mô hình ngừng sinh?

`ChatResponse` có thể chứa một hoặc nhiều `Generation`. Mỗi generation có `ChatGenerationMetadata`, trong đó `getFinishReason()` là tên lý do **thô** mà provider sử dụng.

Ví dụ các giá trị thô có thể gặp:

~~~text
stop
end_turn
STOP
length
max_tokens
tool_calls
content_filter
refusal
SAFETY
~~~

Các tên trên chỉ mang tính **minh họa**; không provider nào nhất thiết dùng toàn bộ. Đừng tự ánh xạ mọi chuỗi lạ thành `stop` hoặc `error`.

Spring AI **2.1.0** giới thiệu cách phân loại thống nhất `getFinishReasonCategory()`, giúp ứng dụng không phải tự xây một bảng từ `stop/end_turn/STOP/...` cho từng provider.

| `FinishReasonCategory` | Ý nghĩa | Cách phản ứng gợi ý |
| --- | --- | --- |
| `COMPLETED` | Mô hình hoàn tất câu trả lời | Vẫn kiểm thử tính đúng/đủ theo nghiệp vụ |
| `TRUNCATED` | Câu trả lời bị ngắt bởi giới hạn độ dài hoặc token | Kiểm tra giới hạn output, kích thước prompt và độ dài câu trả lời |
| `TOOL_CALL` | Mô hình yêu cầu gọi công cụ | Theo dõi tool execution và lượt model tiếp theo; **không mặc định là lỗi** |
| `FILTERED` | Safety filter chặn hoặc mô hình từ chối | Phân biệt tình huống an toàn hợp lệ với lỗi workflow |
| `OTHER` | Lý do không có ý nghĩa chung hoặc chưa được nhận diện | Lưu raw finish reason an toàn và điều tra provider |
| `UNSPECIFIED` | Provider không cung cấp lý do | Ghi thiếu dữ liệu, không suy diễn đã hoàn tất bình thường |

**Lưu ý quan trọng:** các category là trạng thái **dừng sinh**. Chúng không tương đương HTTP status, exception, nội dung đúng/sai hay quality label. `COMPLETED` chỉ nói quá trình sinh đã hoàn tất theo cách provider báo, không chứng minh lời giải đã chính xác.

### 6.1. Vì sao phải giữ cả raw reason và category?

Đối chiếu giữa nhiều provider, `COMPLETED` là nhãn chung rất hữu ích cho dashboard. Nhưng để điều tra lỗi đặc thù, cần biết provider đã trả `stop` hay `end_turn`. Ngược lại, một raw reason mới có thể được phân vào `OTHER` và cần cập nhật sự hiểu biết về API.

Một bản ghi do ứng dụng tự thiết kế:

~~~json
{
  "caseId": "rag-eval-017",
  "provider": "example-provider",
  "requestedModel": "example-model-v2",
  "rawFinishReason": "length",
  "finishCategory": "TRUNCATED",
  "modelCallSucceeded": true
}
~~~

Đây là **schema minh họa**, không phải record được Spring AI xuất nguyên dạng. Với model call lỗi trước khi nhận response, các trường finish reason/category cần để **thiếu** hoặc đánh dấu `NOT_AVAILABLE` riêng ở tầng báo cáo, không gán bừa `UNSPECIFIED` như thể model đã trả metadata trống.

### 6.2. Tool call là bước chuyển trạng thái, không phải thất bại

Trong một vòng tool calling:

~~~text
ChatModel #1 -> finishCategory=TOOL_CALL
Tool "getOrderStatus" -> success
ChatModel #2 -> finishCategory=COMPLETED
Answer -> "Đơn đang giao..."
~~~

Đây là **kịch bản** chứ không phải một trace đã chạy. Nếu dashboard coi `TOOL_CALL` là lỗi, toàn bộ các agent có công cụ sẽ bị báo sai. Phải đo riêng tỉ lệ tool success/error, số vòng gọi model và kết quả cuối cùng.

### 6.3. Filtered có phải lỗi kỹ thuật?

Không nhất thiết. Một provider có thể trả response có category `FILTERED` và hoàn tất ở tầng HTTP/SDK; khi đó gọi model không bị exception, nhưng answer có thể rỗng hoặc là lời từ chối. Với việc chuyển đổi thành entity, `ChatClient.entity(...)` có thể phát sinh `ContentFilteredException` nếu kết quả không thể chuyển đổi, theo tài liệu Spring AI 2.1.0.

Vì vậy nên phân biệt:

- `FILTERED` là lý do ngừng sinh.
- `ContentFilteredException` là exception ở bước chuyển đổi/entity, có thể liên quan content filtering.
- `RelevancyEvaluator.isPass() == false` là verdict của bộ chấm.
- `EVALUATION_ERROR` là trạng thái do ứng dụng đặt khi không hoàn tất được lượt chấm.

Không ép bốn hiện tượng này vào cùng một nhãn `ERROR`.

## 7. Java: đọc lý do kết thúc từ ChatResponse

Khi cần phân tích metadata, nên lấy `ChatResponse` thay vì chỉ lấy chuỗi `content()`.

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.metadata.ChatGenerationMetadata;
import org.springframework.stereotype.Service;

@Service
public class ObservedFinishReasonService {

    private final ChatClient chatClient;

    public ObservedFinishReasonService(ChatClient.Builder builder) {
        this.chatClient = builder.build();
    }

    public void inspect(String question) {
        ChatResponse response = chatClient.prompt()
                .user(question)
                .call()
                .chatResponse();

        if (response == null || response.getResult() == null) {
            System.out.println("Không có Generation để đọc metadata");
            return;
        }

        ChatGenerationMetadata metadata =
                response.getResult().getMetadata();

        if (metadata == null) {
            System.out.println("Không có finish metadata");
            return;
        }

        String rawReason = metadata.getFinishReason();

        // Spring AI 2.1.x: category chung giữa các provider.
        String category = metadata.getFinishReasonCategory() == null
                ? "UNSPECIFIED"
                : metadata.getFinishReasonCategory().name();

        System.out.println("Raw finish reason: " + rawReason);
        System.out.println("Finish category: " + category);
    }
}
~~~

Đoạn ví dụ in **chỉ metadata** để học, không ghi nội dung người dùng. Trong production nên dùng logger/telemetry có kiểm soát thay vì `System.out.println`. `getResult()` thường là generation đầu; nếu provider trả nhiều generations, cần xét từng generation, không tự khái quát rằng tất cả có chung finish reason.

### 7.1. Khi có nhiều generations

Tài liệu Spring AI 2.1.0 cung cấp `ChatResponse.hasFinishReasonCategory(...)` để kiểm tra **có generation nào** thuộc category cần tìm. Ví dụ, có thể dùng điều kiện tương tự:

~~~java
// Pseudocode định hướng: import FinishReasonCategory từ version
// Spring AI đang dùng, hoặc lấy enum qua metadata của generation.

boolean hasTruncated = response.getResults().stream()
        .anyMatch(gen -> gen.getMetadata() != null
                && gen.getMetadata().getFinishReasonCategory() != null
                && "TRUNCATED".equals(
                        gen.getMetadata()
                                .getFinishReasonCategory()
                                .name()));

System.out.println("Có generation bị cắt: " + hasTruncated);
~~~

Cần lưu ý `getFinishReasonCategory()` chỉ có trong dòng Spring AI **2.1.x trở lên** theo tài liệu phát hành; nếu dự án dùng một phiên bản cũ, hãy dùng `getFinishReason()` và mapping được kiểm thử riêng, hoặc nâng cấp dependency phù hợp.

### 7.2. Khi metadata không có

Nếu một lời gọi thành công nhưng không có finish reason, cần ghi **`UNSPECIFIED`** theo đúng semantics. Nếu **không có response do exception**, phải ghi **`MODEL_CALL_ERROR`** chứ không tự tạo một `Generation` giả có category `UNSPECIFIED`.

Không có finish reason không có nghĩa model đã bị cắt, cũng không chứng minh model đã hoàn tất bình thường. Các provider và chế độ stream khác nhau có thể báo metadata không đồng nhất.

## 8. Phân loại kết quả: lỗi model, tình trạng sinh và chất lượng

Để tránh biến mọi `FAIL` thành “lỗi AI”, nên thiết kế bảng trạng thái rõ ràng:

| Tín hiệu quan sát | Trạng thái ứng dụng đề xuất | Cần xử lý ở đâu? |
| --- | --- | --- |
| Nhận `ChatResponse`, category `COMPLETED` | `COMPLETED` | Kiểm tra nội dung theo tiêu chí nghiệp vụ |
| Có category `TRUNCATED` | `TRUNCATED` | Giới hạn output/context, tổng hợp nội dung |
| Có category `TOOL_CALL` | `TOOL_HANDOFF` | Tool runtime và model call tiếp theo |
| Có category `FILTERED` | `FILTERED` | Chính sách an toàn, flow từ chối/chuyển tiếp |
| Category `OTHER` / `UNSPECIFIED` | `UNKNOWN_FINISH` | Metadata/provider/SDK |
| Không nhận `ChatResponse` nhưng không có exception | `EMPTY_RESPONSE` | API contract, parser, client adapter |
| Timeout, auth, rate limit, HTTP error, network exception | `MODEL_CALL_ERROR` | Retry/backoff, provider và infrastructure |
| Có response nhưng bước JSON parser thất bại | `OUTPUT_PARSE_ERROR` | Structured output/parser |
| Có response, test relevance không đạt | `QUALITY_FAIL` | Answer prompt, retrieval, source và rubric judge |

**Các nhãn `TOOL_HANDOFF`, `EMPTY_RESPONSE`, `MODEL_CALL_ERROR`, `QUALITY_FAIL` là taxonomy của ứng dụng trong bài học**, không phải enum do Spring AI tự trả ở `EvaluationResponse`.

### 8.1. Một lỗi có thể đồng thời tác động nhiều tín hiệu

Giả sử answer model hoàn thành, nhưng output bị cắt (`TRUNCATED`). Sau đó một parser cố chuyển text thành JSON và ném exception. Khi đó:

- Model call có thể **không lỗi ở tầng SDK**.
- Finish reason là `TRUNCATED`.
- Bước parser có `OUTPUT_PARSE_ERROR`.
- Case nghiệp vụ có thể chưa được chấm hoặc bị đánh không đầy đủ.
- Độ trễ model và parser phải được đo **riêng**.

Nếu dashboard chỉ thấy “exception count tăng”, nhóm phát triển cần trace để biết lỗi đến từ provider hay tầng chuyển đổi.

## 9. Java thuần: bộ phân loại trạng thái để kiểm thử

Một classifier độc lập với provider giúp regression test xác minh cách dashboard diễn giải metadata. Ví dụ:

~~~java
import java.util.Locale;

public enum ChatOutcome {
    COMPLETED,
    TRUNCATED,
    TOOL_HANDOFF,
    FILTERED,
    OTHER_FINISH,
    UNSPECIFIED_FINISH,
    EMPTY_RESPONSE,
    MODEL_CALL_ERROR
}
~~~

~~~java
import java.util.Locale;

public final class ChatOutcomeClassifier {

    private ChatOutcomeClassifier() {
    }

    public static ChatOutcome classify(
            boolean responsePresent,
            boolean callFailed,
            String finishCategoryName) {

        if (callFailed) {
            return ChatOutcome.MODEL_CALL_ERROR;
        }
        if (!responsePresent) {
            return ChatOutcome.EMPTY_RESPONSE;
        }
        if (finishCategoryName == null
                || finishCategoryName.isBlank()) {
            return ChatOutcome.UNSPECIFIED_FINISH;
        }

        return switch (finishCategoryName.trim()
                .toUpperCase(Locale.ROOT)) {
            case "COMPLETED" -> ChatOutcome.COMPLETED;
            case "TRUNCATED" -> ChatOutcome.TRUNCATED;
            case "TOOL_CALL" -> ChatOutcome.TOOL_HANDOFF;
            case "FILTERED" -> ChatOutcome.FILTERED;
            case "OTHER" -> ChatOutcome.OTHER_FINISH;
            case "UNSPECIFIED" -> ChatOutcome.UNSPECIFIED_FINISH;
            default -> ChatOutcome.OTHER_FINISH;
        };
    }
}
~~~

Trong code trên, `responsePresent` và `callFailed` được tầng gọi model cung cấp dựa trên **kết quả thực tế**. Không tự xác định `callFailed=true` chỉ vì finish category là `FILTERED` hoặc `TRUNCATED`.

### 9.1. Unit test không gọi LLM

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ChatOutcomeClassifierTest {

    @Test
    void normalCompletionIsNotAnAccuracyClaim() {
        assertThat(ChatOutcomeClassifier.classify(
                true, false, "COMPLETED"))
                .isEqualTo(ChatOutcome.COMPLETED);
    }

    @Test
    void truncatedOutputIsNotAnException() {
        assertThat(ChatOutcomeClassifier.classify(
                true, false, "TRUNCATED"))
                .isEqualTo(ChatOutcome.TRUNCATED);
    }

    @Test
    void toolCallIsNotTechnicalFailure() {
        assertThat(ChatOutcomeClassifier.classify(
                true, false, "TOOL_CALL"))
                .isEqualTo(ChatOutcome.TOOL_HANDOFF);
    }

    @Test
    void distinguishesFilteredAndUnspecified() {
        assertThat(ChatOutcomeClassifier.classify(
                true, false, "FILTERED"))
                .isEqualTo(ChatOutcome.FILTERED);

        assertThat(ChatOutcomeClassifier.classify(
                true, false, null))
                .isEqualTo(ChatOutcome.UNSPECIFIED_FINISH);
    }

    @Test
    void distinguishesEmptyResponseFromThrownError() {
        assertThat(ChatOutcomeClassifier.classify(
                false, false, null))
                .isEqualTo(ChatOutcome.EMPTY_RESPONSE);

        assertThat(ChatOutcomeClassifier.classify(
                false, true, null))
                .isEqualTo(ChatOutcome.MODEL_CALL_ERROR);
    }
}
~~~

Các test trên **không đòi API key hoặc provider**. Chúng bảo vệ cách phân loại ở tầng ứng dụng, không kiểm tra việc model thực có sinh đúng finish reason hay không. Muốn kiểm tra end-to-end, cần một bộ integration test riêng.

## 10. Quan sát riêng trạng thái kết thúc trong Micrometer

Các finish reasons có thể nằm trong high-cardinality attributes của trace dưới khóa `gen_ai.response.finish_reasons`. Nếu cần thống kê phần trăm `TRUNCATED` theo model, bạn không nên mặc định có label `gen_ai_response_finish_reasons` trong timer Prometheus.

Một cách chủ động là **tạo metric nghiệp vụ riêng** sau khi đọc `ChatResponse`, với tập nhãn hữu hạn:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.ai.chat.model.ChatResponse;

public final class ChatOutcomeMetrics {

    private final MeterRegistry registry;

    public ChatOutcomeMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(String role, ChatOutcome outcome) {
        registry.counter(
                "application.chat.outcome",
                "workflow_role", role,
                "outcome", outcome.name()
        ).increment();
    }
}
~~~

Ví dụ một ứng dụng chỉ cho `role` nhận `answer`, `judge` hoặc `summarizer`. Hạn chế số giá trị để không tăng cardinality vô kiểm soát. **Không đưa câu hỏi, raw response, request ID hoặc user ID làm tag metric.**

### 10.1. Vì sao metric riêng cần gắn ở đúng tầng?

Nếu bạn ghi metric ngay sau `ChatClient.call().chatResponse()`, nó phản ánh **kết quả mà client trả cho ứng dụng**, có thể đã đi qua tool loop hoặc advisor. Nếu bạn muốn đếm **từng model operation**, cần instrument tại mỗi `ChatModel` call hoặc dùng observation handler phù hợp. Hai mẫu số khác nhau:

~~~text
response_outcomes_per_user_request
model_finish_categories_per_model_call
~~~

Một request có tool calling có thể phát sinh nhiều model calls: lượt đầu `TOOL_CALL` và lượt sau `COMPLETED`. Không được so tỷ lệ hai metric khác mẫu số rồi kết luận có lỗi.

### 10.2. Tạo observation bao ngoài luồng nghiệp vụ

Có thể gắn một observation tự đặt tên để liên kết lời gọi answer model với trace của request:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;

public final class TracedAnswerOperation {

    private final ChatModel model;
    private final ObservationRegistry registry;

    public TracedAnswerOperation(
            ChatModel model, ObservationRegistry registry) {
        this.model = model;
        this.registry = registry;
    }

    public ChatResponse call(String question) {
        Observation observation = Observation
                .createNotStarted("application.answer", registry)
                .lowCardinalityKeyValue("workflow.role", "answer");

        observation.start();

        try (Observation.Scope ignored = observation.openScope()) {
            ChatResponse result = model.call(new Prompt(question));

            ChatOutcome outcome = ChatOutcomeClassifier.classify(
                    result != null && result.getResult() != null,
                    false,
                    result == null || result.getResult() == null
                    || result.getResult().getMetadata() == null
                    || result.getResult()
                             .getMetadata()
                             .getFinishReasonCategory() == null
                        ? null
                        : result.getResult().getMetadata()
                                .getFinishReasonCategory().name()
            );

            observation.lowCardinalityKeyValue(
                    "finish.category", outcome.name());

            return result;
        }
        catch (RuntimeException ex) {
            observation.error(ex);
            observation.lowCardinalityKeyValue(
                    "finish.category", "MODEL_CALL_ERROR");
            throw ex;
        }
        finally {
            observation.stop();
        }
    }
}
~~~

`application.answer` là **observation do ứng dụng tạo**, không phải tên mặc định của Spring AI. Nó giúp phân biệt answer call với judge call trong trace; `ChatModel` bên trong vẫn có observation `gen_ai.client.operation` riêng nếu implementation hỗ trợ.

Mã minh họa ghi trạng thái `MODEL_CALL_ERROR` khi có `RuntimeException` và **ném lại lỗi** để caller xử lý. Nếu ứng dụng có error policy khác, cần thiết kế bổ sung. Không bắt mọi `Throwable` rồi âm thầm trả `COMPLETED`; không chuyển exception thành `NO` của RelevancyEvaluator.

### 10.3. PromQL với metric tự định nghĩa

Giả sử counter custom trên được xuất thành `application_chat_outcome_total`, có thể tính tỷ lệ lượt trả về `TRUNCATED` trong nhóm answer theo status có đếm:

~~~promql
sum(
  rate(application_chat_outcome_total{
    workflow_role="answer",
    outcome="TRUNCATED"
  }[5m])
)
/
sum(
  rate(application_chat_outcome_total{
    workflow_role="answer"
  }[5m])
)
~~~

Nếu một số exception chưa được ghi thành counter outcome, tỷ lệ trên **không đại diện toàn bộ attempts**. Cần có mẫu số rõ ràng và ghi outcome `MODEL_CALL_ERROR` ở nhánh catch nếu muốn báo cáo theo attempts. Không đo bằng việc đếm high-cardinality trace field từ một tập traces bị sampling rồi giả định đó là tỷ lệ trên toàn traffic.

## 11. Phân biệt nhóm lỗi kỹ thuật

| Lỗi | Dấu hiệu vận hành | Đường xử lý thường gặp | Lưu ý |
| --- | --- | --- | --- |
| **Timeout** | Duration cao, exception hoặc request bị hủy | Kiểm tra network/provider, deadline, retry có giới hạn | Timeout không có nghĩa model sinh `TRUNCATED` |
| **Rate limit / quota** | HTTP 429 hoặc exception provider tương ứng | Backoff, quota, phân phối tải | Lỗi có thể được retry trước khi app nhận kết quả |
| **Authentication/authorization** | HTTP 401/403 hoặc exception | Kiểm tra secret, quyền, endpoint | Không retry liên tục với credential sai |
| **Transport/network** | Connect/reset/SSL/DNS exception | Quan sát HTTP span, gateway, network | Có thể không có `ChatResponse` |
| **Request validation** | 400, invalid model/options/schema | Sửa input, API version hoặc model options | Không nhầm lỗi cấu hình với answer quality |
| **Content filtering** | Response có `FILTERED` hoặc exception ở bước entity conversion | Chính sách an toàn, fallback hợp lệ | Không tự xem là sự cố provider |
| **Output parsing** | Có response nhưng JSON/entity conversion thất bại | Sửa schema, template hoặc parser | Model call có thể đã kết thúc bình thường |
| **Tool failure** | Tool ném exception hoặc trả dữ liệu sai | Xem `spring.ai.tool` và flow | `TOOL_CALL` của model không phải lỗi |
| **Evaluation judge failure** | Judge timeout, thiếu verdict, format sai | Tách `EVALUATION_ERROR` khỏi `QUALITY_FAIL` | Không làm sai pass rate của bộ dữ liệu |

Đối với retry, có ít nhất **hai tầng cần phân biệt**:

- **Provider/SDK HTTP attempts:** có thể nhiều request mạng cho một model call.
- **Model invocation attempts của ứng dụng:** caller quyết định gọi lại toàn bộ `ChatModel`, tạo nhiều model operations.

Hai tầng không nhất thiết xuất cùng một loại span hoặc count. Khi điều tra, giữ attempt ID và duration từng tầng thay vì giả định một user request tương ứng đúng một HTTP request.

## 12. Streaming: nhận chunk, cancel và lỗi trên luồng

Khi dùng `stream()`, có ít nhất bốn khả năng:

1. Luồng hoàn tất sau khi nhận đủ chunk.
2. Provider gửi một finish reason ở chunk nào đó.
3. Subscriber **hủy** luồng trước khi provider hoàn tất.
4. Publisher phát `onError` do kết nối/provider hoặc xử lý nội bộ.

Đặc biệt, theo tài liệu Spring AI 2.1.0, **finish reason category của từng chunk được xác định theo nội dung chunk đó**. Nếu provider rải một hành vi từ chối hoặc một tool call qua nhiều chunk, category của **chunk cuối** hoặc **response gom lại** không nhất thiết thể hiện đầy đủ trạng thái ngữ nghĩa của toàn luồng.

Không nên chỉ đọc metadata của chunk cuối rồi báo “tất cả stream đều COMPLETED”. Nếu cần kiểm toán trạng thái cuối của một vòng streaming, phải có **chiến lược tổng hợp sự kiện** rõ ràng, và tách `CANCELLED` khỏi `FAILED` hoặc `COMPLETED`.

### 12.1. Ví dụ Java đo TTFT và lifecycle

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatResponse;

import reactor.core.publisher.Flux;

public final class StreamTimingService {

    private final ChatClient client;

    public StreamTimingService(ChatClient client) {
        this.client = client;
    }

    public Flux<ChatResponse> stream(String question) {
        return Flux.defer(() -> {
            long startedNanos = System.nanoTime();
            AtomicBoolean seenFirstChunk = new AtomicBoolean(false);

            return client.prompt()
                    .user(question)
                    .stream()
                    .chatResponse()
                    .doOnNext(chunk -> {
                        if (seenFirstChunk.compareAndSet(false, true)) {
                            long ttftMs = TimeUnit.NANOSECONDS.toMillis(
                                    System.nanoTime() - startedNanos);

                            recordFirstChunkLatency(ttftMs);
                        }
                    })
                    .doOnError(ex -> recordStreamError(ex.getClass().getSimpleName()))
                    .doFinally(signal -> {
                        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                                System.nanoTime() - startedNanos);
                        recordStreamEnd(signal.name(), elapsedMs);
                    });
        });
    }

    private void recordFirstChunkLatency(long milliseconds) {
        // Ghi vào timer/histogram custom; không ghi nội dung chunk.
    }

    private void recordStreamError(String errorClass) {
        // Phân loại lỗi có giới hạn cardinality.
    }

    private void recordStreamEnd(String signalType, long elapsedMs) {
        // onComplete, onError và cancel là tín hiệu khác nhau.
    }
}
~~~

Ví dụ này đo **thời gian tới `ChatResponse` chunk đầu**, không nhất thiết chính xác là **token văn bản đầu tiên**: một chunk có thể chứa metadata hoặc thông tin tool mà chưa có text. Muốn đo TTFT về **văn bản hiển thị**, chỉ ghi mốc khi chunk thật sự chứa text mà UI sử dụng.

`doFinally(...)` cho phép thấy `CANCEL` khác với `ON_COMPLETE` và `ON_ERROR`; nó không tự đảm bảo Spring AI/model instrumentation ghi cùng một trạng thái vào timer mặc định. Cần kiểm tra luồng thực tế, nhất là khi client disconnect hoặc người dùng bấm dừng.

## 13. Kết hợp với RelevancyEvaluator và fact checking

Cùng một bộ dữ liệu RAG có thể có ba bộ tín hiệu:

| Nhóm | Dữ liệu | Ví dụ |
| --- | --- | --- |
| **Model operation** | Duration, provider/model, exception, finish reason | `TRUNCATED`, 2,4 giây, không exception |
| **Đầu vào RAG** | Câu hỏi, context, nguồn/version, tool output | Retriever lấy nhầm chính sách cũ |
| **Đánh giá chất lượng** | `RelevancyEvaluator.isPass()`, groundedness/claim verification | Phản hồi không đáp ứng đúng câu hỏi |

Một case `TRUNCATED` có thể làm `RelevancyEvaluator` trả `false` vì response thiếu ý, nhưng **không nên mặc định** mọi `TRUNCATED` đều `QUALITY_FAIL`; có trường hợp phần đầu đã chứa câu trả lời đủ. Phán quyết chất lượng cần rubric và nhãn đúng.

Tương tự, một lượt `FILTERED` có thể là hành vi từ chối phù hợp với chính sách. Nếu benchmark không phân biệt câu hỏi hợp lệ và câu hỏi cần từ chối, báo cáo chất lượng sẽ dễ bị diễn giải sai.

### 13.1. Dataset cần lưu thêm gì?

Gợi ý record do ứng dụng tự thiết kế:

~~~json
{
  "caseId": "return-policy-2026-033",
  "datasetVersion": "rag-eval-v5",
  "answerPromptVersion": "prompt-v9",
  "answerModelVersion": "answer-model-v4",
  "judgeModelVersion": "judge-model-v2",
  "retrieverVersion": "retriever-v7",
  "answerCallDurationMs": 1180,
  "answerRawFinishReason": "length",
  "answerFinishCategory": "TRUNCATED",
  "answerModelError": null,
  "judgeCallDurationMs": 340,
  "judgeCallStatus": "SUCCESS",
  "relevancePass": false
}
~~~

Đây là **JSON giả định**, không phải output mặc định của Spring AI. Các trường trạng thái nên được ghi cùng định nghĩa mẫu số, trạng thái missing, version và nguồn dữ liệu.

### 13.2. Phân tích kết quả theo nhóm

Một dashboard hữu ích có thể trả lời:

- Tỷ lệ `QUALITY_FAIL` có tăng riêng ở các câu trả lời `TRUNCATED` không?
- Có nhiều `FILTERED` hơn ở một bản model hoặc prompt mới không?
- Những case judge timeout có đang bị đưa nhầm vào denominator của relevance pass rate không?
- Sau khi giảm `max_tokens` để tiết kiệm chi phí, tỷ lệ `TRUNCATED` và số lượt retry có tăng không?
- Một số case chậm có nhiều retrieval chunks hoặc tool calls hơn không?

Phân tích theo **bằng chứng quan sát**: giữ judge model/rubric cố định khi so sánh answer model và giữ dataset, source context phù hợp. Không kết luận câu trả lời “đúng” chỉ vì `finishCategory=COMPLETED`.

## 14. Thiết kế cảnh báo vận hành theo hành vi, không chỉ số thô

Giả sử nhóm đặt các ngưỡng vận hành minh họa:

| Signal | Ngưỡng thử nghiệm | Hành động |
| --- | --- | --- |
| Model call error rate | Trên 3% trong 10 phút | Kiểm tra provider/network/quota |
| P95 model duration | Trên 4 giây trong 10 phút | Xem histogram và traces chậm |
| TRUNCATED rate | Trên 5% trong một dataset ổn định | Xem `max_tokens`, output length, prompt |
| FILTERED rate | Tăng đột biến so với baseline | Kiểm tra nhóm câu hỏi, chính sách an toàn |
| Tool handoff loop | Số vòng gọi model mỗi request tăng cao | Xem tool output, giới hạn vòng agent |
| Missing finish metadata | Bất thường sau nâng cấp SDK/provider | Kiểm tra mapping response và stream |

Các ngưỡng là **số liệu để thảo luận**, không phải SLO áp dụng sẵn. Cần hiệu chuẩn bằng tải thực tế và nghiệp vụ. Cảnh báo `FILTERED` nhiều không đồng nghĩa provider hỏng hoặc cần tìm cách vô hiệu hóa lớp bảo vệ.

### 14.1. Tránh alert sai khi ít traffic

Khi chỉ có vài lượt gọi, một exception có thể làm tỷ lệ lỗi tăng 50%. Một alert tốt thường dùng:

- Tối thiểu số sample trong cửa sổ.
- Tỷ lệ lỗi kèm số lỗi tuyệt đối.
- Các phân nhóm provider/model đã kiểm soát.
- Độ trễ p95 có histogram và đủ mẫu.
- Thời gian duy trì ngưỡng, không báo động bởi một điểm dữ liệu duy nhất.

Đối với bộ đánh giá offline, nên thêm cảnh báo **job completion/error** và đối chiếu thời gian chạy suite; một histogram online không thể tự nói một batch có đủ case đã hoàn tất chưa.

## 15. Bảo mật và hạn chế của dữ liệu quan sát

Spring AI **không xuất prompt/completion content mặc định** vì chúng có thể chứa dữ liệu riêng tư. Các cờ liên quan theo tài liệu:

~~~properties
spring.ai.chat.observations.log-prompt=false
spring.ai.chat.observations.log-completion=false
spring.ai.chat.observations.include-error-logging=false

spring.ai.chat.client.observations.log-prompt=false
spring.ai.chat.client.observations.log-completion=false
~~~

Muốn bật để debug, phải đánh giá chính sách dữ liệu, phân quyền, redaction, thời hạn lưu và phạm vi môi trường. **Exception messages** có thể vô tình chứa request fragment, endpoint hoặc thông tin nhạy cảm; không ghi raw message vào low-cardinality label.

Nguyên tắc:

1. Metric label chỉ chứa tập giá trị nhỏ như provider, model family, workflow role hoặc finish category.
2. Trace có thể chứa response ID và raw finish reason ở mức kiểm soát; không tự đưa tài liệu RAG hoặc PII vào attribute.
3. Với lỗi provider, thu loại exception và trace ID; chỉ lưu stack trace/full error ở nơi có chính sách phù hợp.
4. Không xem `gen_ai.response.finish_reasons` có mặt trong mọi provider/stream; metadata thiếu phải được ghi rõ.
5. Nếu traces bị sampling, không dùng chúng như mẫu số duy nhất để tính tỷ lệ lỗi cho toàn bộ production.

## 16. Lỗi thường gặp và cách điều tra

| Triệu chứng | Nhầm lẫn phổ biến | Cách điều tra |
| --- | --- | --- |
| `gen_ai.client.operation` có thời lượng nhưng không có `finish_reasons` | Tưởng model không chạy | Kiểm tra provider metadata, ChatResponse và exporter |
| P95 không hiển thị | Dùng `sum/count` hoặc chưa bật histogram | Kiểm tra `_bucket` và registry |
| Timer count tăng dù user không nhận câu trả lời | Cho rằng count chỉ đếm thành công | Kiểm tra nhãn `error`, timeout và cancel |
| `TRUNCATED` xuất hiện nhiều | Coi là HTTP error | Kiểm tra output limit và prompt/context length |
| `TOOL_CALL` tăng | Coi là mô hình từ chối trả lời | Xem tool loop và các model calls tiếp theo |
| `FILTERED` nhưng `error=none` | Coi dữ liệu mâu thuẫn | Finish reason và exception đo hai khía cạnh khác |
| Có exception nhưng không có finish reason | Tự gán `UNSPECIFIED` | Ghi `MODEL_CALL_ERROR` vì chưa có generation hợp lệ |
| ChatModel nhanh nhưng request chậm | Chỉ tối ưu model | Kiểm tra RAG, tool, parser và toàn bộ trace |
| Stream phản hồi sớm nhưng operation lâu | Nhầm TTFT với full-stream duration | Đo chunk đầu và stream-end riêng |
| Error rate tăng sau đổi provider | Gộp lỗi model và chất lượng | Xem quota, credential, network và input validity |
| Pass rate RAG giảm nhưng model call thành công | Quy kết provider hỏng | Kiểm tra chất lượng nguồn, generation và judge |
| Có lỗi parsing JSON sau `COMPLETED` | Coi lỗi provider | Tách postprocessing/parser khỏi model call |

### 16.1. Quy trình gỡ lỗi một case cụ thể

1. Lấy **trace ID/case ID** từ tầng ứng dụng, không lấy PII làm nhãn metric.
2. Xác định có bao nhiêu lần `ChatModel` được gọi, gồm answer, tool loops và judge.
3. Kiểm tra duration từng model call, thời gian active, các retry và HTTP spans nếu có.
4. Nếu nhận response, đọc `getFinishReason()` và category của từng generation.
5. Nếu có exception, ghi nguồn exception; không điền finish reason giả.
6. Nếu output `TRUNCATED`, kiểm tra output limit, token usage và dữ liệu RAG.
7. Nếu `TOOL_CALL`, xem tool results và model call tiếp theo.
8. Nếu `FILTERED`, xem chính sách và tình huống có cần từ chối hợp lệ không.
9. Đối chiếu chất lượng với nhãn chuyên gia, `RelevancyEvaluator` và fact checking.
10. Lưu điều kiện tái hiện: dataset, prompt/model version, provider, pipeline và giới hạn cấu hình.

## 17. Bài tập thực hành

### Bài 1. Đọc thời lượng

Bật Actuator và Prometheus cho một ứng dụng Spring AI. Thực hiện ít nhất 20 lượt `ChatModel.call(...)`. Xác định `gen_ai_client_operation_seconds_count`, `_sum` và `_max`; tính mean latency theo provider. Ghi rõ vì sao mean không phải P95.

### Bài 2. Xây P95

Bật histogram cho `gen_ai.client.operation`; xác minh `gen_ai_client_operation_seconds_bucket` xuất hiện. Chạy query `histogram_quantile` để lấy P95 theo provider. Giải thích trường hợp biểu đồ rỗng hoặc ít mẫu.

### Bài 3. Phân tích finish reasons

Dùng `ChatClient.call().chatResponse()` để đọc raw finish reason và category. Tạo các tình huống `COMPLETED`, `TRUNCATED` hoặc `TOOL_CALL` nếu provider hỗ trợ. Không ép provider phải trả một token/finish reason mà nó không hỗ trợ.

### Bài 4. Kiểm thử classifier

Viết và chạy các unit test của `ChatOutcomeClassifier` cho `COMPLETED`, `TRUNCATED`, `TOOL_CALL`, `FILTERED`, `UNSPECIFIED`, response rỗng và exception. Kiểm tra lỗi model có mức ưu tiên đúng và không biến `TOOL_CALL` thành error.

### Bài 5. Streaming và cancel

Đo latency đến chunk đầu, full-stream duration và `doFinally` signal cho `ON_COMPLETE`, `ON_ERROR`, `CANCEL`. Thử client hủy luồng giữa chừng; giải thích vì sao không thể suy ra trạng thái cuối chỉ từ metadata của chunk cuối.

### Bài 6. Liên kết với đánh giá RAG

Trên cùng 30 case và một judge ổn định, giảm giới hạn output tokens của answer model. Theo dõi tỷ lệ `TRUNCATED`, độ trễ, token, relevance pass rate và tình trạng thiếu ý của câu trả lời. Phân biệt tác động lên chi phí với tác động lên chất lượng.

### Bài 7. Lập bảng xử lý sự cố

Cho ba tình huống: (a) timeout trước khi nhận response, (b) response `FILTERED` và HTTP thành công, (c) response `COMPLETED` nhưng JSON parser lỗi. Gán riêng trạng thái model call, finish category, lỗi parser và kết quả nghiệp vụ.

## 18. Tổng kết

Muốn theo dõi `ChatModel` trong Spring AI, cần tách **duration**, **finish reason** và **exception**:

- `gen_ai.client.operation` cùng các timer `count/sum/max`, số thao tác active và histogram giúp đo latency và lưu lượng theo provider/model.
- `ChatGenerationMetadata.getFinishReason()` giữ tên thô của provider; từ Spring AI 2.1.x, `getFinishReasonCategory()` giúp phân loại nhất quán thành `COMPLETED`, `TRUNCATED`, `TOOL_CALL`, `FILTERED`, `OTHER` hoặc `UNSPECIFIED`.
- Timeout, rate limit, xác thực, network và lỗi SDK là **lỗi kỹ thuật**; chúng có thể xảy ra trước khi có bất kỳ finish reason nào. Lỗi parser và chất lượng nội dung là các tầng khác.

**Một model call không có exception chưa chắc trả lời đúng; một kết quả `TRUNCATED` chưa chắc là HTTP error; `TOOL_CALL` không phải thất bại.** Khi liên kết trạng thái của từng lượt gọi với kết quả relevance/fact checking, thông tin context của RAG, traces và token/chi phí, ứng dụng mới có thể phân biệt nguyên nhân suy giảm do model/provider, cấu hình, retrieval, tool hoặc chính bộ chấm.

## Tài liệu tham khảo

- [Spring AI Reference — Observability](https://docs.spring.io/spring-ai/reference/observability/index.html): `gen_ai.client.operation`, duration, các thuộc tính high-cardinality `gen_ai.response.finish_reasons`, error logging và traces.
- [Spring AI Reference — Chat Client API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): `ChatResponse`, `ChatGenerationMetadata.getFinishReason()`, `getFinishReasonCategory()`, `ContentFilteredException` và streaming.
- [Spring AI Release 2.1.0 GA (20/11/2026)](https://spring.io/blog/2026/11/20/spring-ai-2-1-0-GA-available-now/): thay đổi về finish reason categories giữa các provider.
- [Spring AI 2.1-SNAPSHOT — Metrics Reference](https://docs.spring.io/spring-ai/reference/2.1-SNAPSHOT/observability/metrics.html): timer/long-task timer Prometheus, nhãn `error`, token usage, histogram và ví dụ PromQL.
- [Spring AI Reference — Chat Response Metadata](https://docs.spring.io/spring-ai/reference/api/usage-handling.html): `ChatResponseMetadata`, `Usage` và thông tin token/provider.
- [Spring Boot Reference — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Actuator, Micrometer, tracing, sampling và exporter.
