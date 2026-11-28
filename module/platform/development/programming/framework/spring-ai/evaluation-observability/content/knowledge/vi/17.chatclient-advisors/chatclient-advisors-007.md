# Nhận diện nhiều lượt mô hình trong một yêu cầu ChatClient

## 1. Một lần gọi ChatClient không có nghĩa chỉ gọi model một lần

Một trợ lý hỗ trợ khách hàng nhận câu hỏi: “Đơn hàng A123 đang ở đâu và chính sách đổi trả áp dụng thế nào?”. Để trả lời, model có thể phải:

1. Đọc câu hỏi và yêu cầu tra cứu trạng thái đơn hàng.
2. Chờ tool trả kết quả vận chuyển.
3. Nhận kết quả tool và yêu cầu tra cứu chính sách đổi trả.
4. Nhận kết quả thứ hai rồi tạo câu trả lời cuối.

Ở phía ứng dụng, người dùng chỉ thực hiện một lần:

~~~java
String answer = chatClient.prompt()
    .user("Đơn hàng A123 đang ở đâu và chính sách đổi trả áp dụng thế nào?")
    .tools(orderTools, policyTools)
    .call()
    .content();
~~~

Nhưng phía model có thể đã thực hiện ba lần gọi. Một ChatClient invocation có thể bao gồm nhiều model operations, nhiều tool executions và nhiều lần chạy advisor.

Đây là lý do khi đọc traces hoặc dashboard, không thể lấy số ChatClient calls làm số model calls. Cũng không thể lấy số tool calls làm số model rounds: một response của model có thể yêu cầu nhiều tools trong cùng một round.

Bài thuộc chương **ChatClient và advisor** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá chất lượng ứng dụng Spring AI bằng dataset, relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện regression theo từng phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

- Phân biệt ChatClient invocation, model operation, model round, tool call và advisor invocation.
- Giải thích vì sao ToolCallingAdvisor tạo nhiều model calls trong một ChatClient call.
- Nhận diện các vòng lặp khác như structured-output validation và retry advisors.
- Đọc trace và đếm đúng từng operation.
- Quan sát mỗi iteration ở advisor chain, cả call và stream.
- Hiểu ảnh hưởng của vòng lặp tới token, latency, chi phí và chất lượng.
- Thiết kế evaluation records để so sánh nhiều rounds theo cùng một case.

## 2. Năm khái niệm cần phân biệt

| Khái niệm | Định nghĩa | Ví dụ |
|---|---|---|
| User turn | Một lượt người dùng gửi yêu cầu | “Tra cứu đơn A123” |
| ChatClient invocation | Một lần thực thi terminal operation của ChatClient như call() hoặc stream() | Một lần gọi service ChatClient |
| Model operation | Một lần gọi ChatModel.call() hoặc ChatModel.stream() | Một request tới model |
| Model round | Một iteration của vòng điều phối, thường chứa một model operation và có thể có tool executions | Model yêu cầu lookupOrder |
| Tool call | Một yêu cầu thực thi tool cụ thể trong response của model | lookupOrder("A123") |

Ngoài ra còn có:

- **Tool execution**: ứng dụng thực thi một tool call thông qua ToolCallback.
- **Advisor invocation**: một lần advisor thực sự được chạy trong chain.
- **Evaluation run**: một lần chạy dataset hoặc thí nghiệm do ứng dụng định nghĩa.
- **HTTP request**: request ở tầng web; có thể gọi một hoặc nhiều ChatClient invocations.

Các khái niệm này thường có quan hệ một-nhiều. Ví dụ một HTTP request có thể tạo hai ChatClient invocations; một ChatClient invocation có thể tạo bốn model operations; một model operation có thể yêu cầu ba tool calls.

## 3. Hình dung một ChatClient invocation có ba model rounds

Giả sử một yêu cầu cần hai công cụ tuần tự:

~~~text
Một HTTP request
└─ Một ChatClient invocation
   └─ ToolCallingAdvisor
      ├─ Model round 1
      │  └─ ChatModel operation #1
      │     ├─ tool call: lookupOrder(A123)
      │     └─ tool call: getShipment(A123)
      │
      ├─ Tool execution batch
      │  ├─ lookupOrder
      │  └─ getShipment
      │
      ├─ Model round 2
      │  └─ ChatModel operation #2
      │     └─ tool call: getReturnPolicy(category)
      │
      ├─ Tool execution
      │  └─ getReturnPolicy
      │
      └─ Model round 3
         └─ ChatModel operation #3
            └─ final answer
~~~

Trong ví dụ này:

| Chỉ số | Số lượng |
|---|---:|
| HTTP requests | 1 |
| ChatClient invocations | 1 |
| Model rounds | 3 |
| ChatModel operations | 3 |
| Tool calls | 3 |
| Tool executions | 3 |
| Final answer | 1 |

Model round 1 yêu cầu hai tool calls, nhưng vẫn chỉ là **một model operation**. Sau khi các tools được thực thi và kết quả được đưa trở lại model, model round 2 bắt đầu.

Nếu hai tool calls trong cùng một batch được thực thi song song, thời gian chờ không nhất thiết bằng tổng duration của hai tool. Số lần thực thi vẫn là hai, còn wall-clock latency phải đọc từ timeline.

## 4. ToolCallingAdvisor tạo vòng lặp model như thế nào?

Trong Spring AI 2.x, ChatClient dùng ToolCallingAdvisor để quản lý vòng đời thực thi tools trong advisor chain. DefaultChatClient tự đăng ký advisor này khi request có tools, trừ khi auto-registration bị tắt hoặc ứng dụng thay thế bằng một ToolAdvisor tùy chỉnh.

Luồng xử lý:

~~~mermaid
flowchart TD
    A["ChatClient invocation"] --> B["ToolCallingAdvisor"]
    B --> C["Gửi request tới ChatModel"]
    C --> D{"Model response có tool calls?"}
    D -->|"Không"| E["Trả final response"]
    D -->|"Có"| F["ToolCallingManager thực thi tools"]
    F --> G["Ghép tool results vào conversation history"]
    G --> H["Gọi lại downstream advisor chain"]
    H --> C
    E --> I["ChatClient trả kết quả"]
~~~

Mỗi lần quay lại ChatModel là một model operation mới. Vòng lặp tiếp tục cho đến khi ToolExecutionEligibilityChecker xác định response không cần thực thi tool nữa.

Pseudo-code mô tả ý tưởng:

~~~text
response = downstreamChain(request)

while response có tool calls
      và eligibilityChecker cho phép tiếp tục:

    toolResults = executeToolCalls(response.toolCalls)
    nextRequest = appendToolResults(conversationHistory, toolResults)
    response = downstreamChain(nextRequest)

return response
~~~

Đây là mô hình khái niệm, không phải toàn bộ implementation. ToolCallingAdvisor còn quản lý metadata, conversation history, tool errors, return-direct và các trường hợp dừng đặc biệt.

### 4.1. Mỗi iteration có một lần gọi model

Với vòng lặp tiêu chuẩn, mỗi iteration gửi một request tới ChatModel và nhận một response. Response có thể:

- Không chứa tool calls: vòng lặp kết thúc với câu trả lời model.
- Chứa một tool call: ứng dụng thực thi một tool rồi lặp lại.
- Chứa nhiều tool calls: ứng dụng thực thi các tool được yêu cầu rồi lặp lại với kết quả.
- Bị dừng bởi return-direct hoặc điều kiện eligibility tùy chỉnh.

Do đó:

~~~text
model rounds = số lần vòng điều phối gọi ChatModel
tool calls   = tổng số tool invocation được model yêu cầu
tool batches = số response có tool calls được xử lý
~~~

Không đồng nhất ba đại lượng này.

### 4.2. ToolCallingAdvisor là recursive advisor

ToolCallingAdvisor không tự gọi lại toàn bộ advisor chain từ đầu. Nó tạo sub-chain chỉ gồm các advisor nằm **sau chính nó** bằng cơ chế như CallAdvisorChain.copy(this). Vì thế:

- Advisor đứng trước ToolCallingAdvisor không bị chạy lại trong mỗi tool iteration.
- Advisor đứng sau ToolCallingAdvisor có thể chạy lại ở mỗi iteration.
- Các advisor recursive khác ở phía sau còn có thể tạo thêm lần gọi model.
- Mỗi iteration có thể quan sát request đã được bổ sung tool messages từ các vòng trước.

Đây là nền tảng để hiểu tại sao một ChatClient invocation có nhiều advisor observations cùng tên.

## 5. Một model response có thể chứa nhiều tool calls

Ví dụ model trả về hai tool calls cùng lúc:

~~~json
{
  "tool_calls": [
    {
      "id": "call-01",
      "name": "lookupOrder",
      "arguments": {"orderId": "A123"}
    },
    {
      "id": "call-02",
      "name": "getShipment",
      "arguments": {"orderId": "A123"}
    }
  ]
}
~~~

Ứng dụng thực thi cả hai theo ToolCallingManager, sau đó đưa kết quả trở lại model trong conversation history.

Trong trường hợp này:

- Một ChatModel operation đã tạo ra response.
- Một model round đã hoàn thành.
- Có hai tool calls.
- Có thể có hai tool executions.
- Nếu model cần đọc kết quả rồi trả lời, sẽ có thêm model operation ở iteration tiếp theo.

Không đếm hai tool calls thành hai model rounds. Một round có thể có zero, one hoặc many tool calls.

### 5.1. Tool execution batch khác số lượng tool calls

Một batch là nhóm tool calls đến từ cùng một response của model. Tùy implementation, các tools có thể được thực thi tuần tự hoặc song song. Vì thế nên ghi riêng:

| Trường | Ví dụ |
|---|---|
| modelRound | 1 |
| toolBatchIndex | 1 |
| toolCallCount | 2 |
| toolExecutionCount | 2 |
| modelCallIndex tiếp theo | 2 |

Các chỉ số này do ứng dụng có thể lưu trong evaluation record. Không có nghĩa Spring AI tự động xuất tất cả các field này thành metric.

## 6. Một ChatClient request có thể lặp vì nhiều lý do

Tool calling là ví dụ dễ thấy nhất, nhưng không phải nguyên nhân duy nhất tạo nhiều model operations.

| Nguyên nhân | Điều kiện lặp | Ví dụ |
|---|---|---|
| ToolCallingAdvisor | Model yêu cầu tools | Tra đơn hàng, lấy dữ liệu CRM |
| Structured-output validation | Output không hợp schema | Sinh JSON rồi sửa lại |
| Retry advisor | Lỗi tạm thời hoặc output không đạt điều kiện | Retry với prompt/option khác |
| Evaluation-and-revision advisor | Judge đánh giá chưa đạt | Sinh lại câu trả lời |
| Custom recursive advisor | Điều kiện nghiệp vụ chưa hoàn thành | Gọi model tới khi có đủ dữ liệu |
| Application-level loop | Service gọi ChatClient nhiều lần | Vòng lặp do code ứng dụng quản lý |

Phải phân biệt **recursive advisor loop bên trong ChatClient** với **application loop bên ngoài ChatClient**:

- Recursive loop: thường một ChatClient invocation bao quanh nhiều model operations.
- Application loop: mỗi lần gọi ChatClient terminal method là một invocation riêng, thường có ChatClient observation riêng.

Một HTTP request có thể chứa cả hai loại vòng lặp.

## 7. Nhận diện vòng lặp bằng observation và trace

Spring AI cung cấp observations cho nhiều ranh giới:

| Observation | Phản ánh |
|---|---|
| spring.ai.chat.client | Một ChatClient call/stream invocation |
| spring.ai.advisor | Một lần thực thi advisor |
| gen_ai.client.operation | Một lần ChatModel call/stream operation |
| spring.ai.tool | Một tool execution |
| db.vector.client.operation | Một thao tác VectorStore nếu được instrument |
| gen_ai.client.token.usage | Token usage do model/provider cung cấp |

Một trace logic có thể trông như sau:

~~~text
spring.ai.chat.client                         (1 invocation)
└─ ToolCallingAdvisor
   ├─ gen_ai.client.operation                 (model round 1)
   ├─ spring.ai.tool: lookupOrder             (tool call 1)
   ├─ spring.ai.tool: getShipment             (tool call 2)
   ├─ gen_ai.client.operation                 (model round 2)
   ├─ spring.ai.tool: getReturnPolicy         (tool call 3)
   └─ gen_ai.client.operation                 (model round 3)
~~~

Cấu trúc parent-child cụ thể có thể khác theo provider, reactive context và tracing bridge. Hãy dùng tên observation, trace ID, span ID và timeline thực tế; không giả định mọi backend đều vẽ cùng một cây.

### 7.1. Đếm model rounds từ ChatModel observations

Khi một ChatClient invocation chứa nhiều gen_ai.client.operation spans, đó là dấu hiệu có nhiều model operations.

Một cách phân tích:

1. Tìm ChatClient span theo trace ID.
2. Xác định tất cả ChatModel observations có liên quan tới invocation.
3. Sắp xếp theo start time hoặc quan hệ parent-child.
4. Đối chiếu tool spans nằm giữa các model operations.
5. Xác định operation cuối là final response hay còn một vòng lặp khác.
6. So sánh với advisor spans để tìm recursive advisor gây ra các vòng.

Nếu span bị sampling hoặc trace context bị mất, count trong trace có thể không đầy đủ. Khi cần số lượng chính xác, dùng metrics/counter tại model boundary hoặc event instrumentation, không chỉ dựa vào một trace được sample.

### 7.2. Phân biệt ChatClient duration và tổng model duration

ChatClient observation đo thời gian thực hiện invocation. Model observations đo các lần gọi model. Tool observations đo tool execution.

Nếu các bước tuần tự, ChatClient duration thường bao gồm model calls, tool executions, advisor processing và overhead khác. Nếu có công việc song song, tổng durations con có thể lớn hơn wall-clock duration.

Không cộng inclusive durations của ChatClient, advisor và model thành latency tổng. Hãy đọc waterfall và critical path.

## 8. Tính số model operations trung bình trên một ChatClient invocation

Một chỉ số hữu ích là:

\[
\text{Mean model operations per invocation}
=
\frac{\text{Tổng số model operations}}
{\text{Tổng số ChatClient invocations}}
\]

Ví dụ trong một cửa sổ năm phút:

| Chỉ số | Count |
|---|---:|
| ChatClient invocations | 1.000 |
| ChatModel operations | 1.850 |
| Tool executions | 1.120 |

Khi đó:

\[
1850 / 1000 = 1.85
\]

Trung bình mỗi ChatClient invocation tạo 1,85 model operations.

Đây là tỷ lệ tổng hợp, không cho biết mỗi request có bao nhiêu rounds. Một số request có một operation, một số có năm operation. Muốn xem phân phối theo request, cần correlation/run IDs ở traces hoặc application event store.

### 8.1. Dùng metrics có cardinality hữu hạn

Có thể tạo các counters do ứng dụng quản lý:

~~~text
app.ai.chatclient.invocations
app.ai.model.operations
app.ai.tool.executions
app.ai.model.rounds
~~~

Chỉ dùng các tags hữu hạn như model family, mode (call/stream), outcome hoặc tool name thuộc danh mục kiểm soát. Không dùng conversation ID, trace ID, request ID hoặc case ID làm metric labels.

Metric names trên là ví dụ tùy biến, không phải tên series mặc định của Spring AI.

### 8.2. Đừng dùng trace sampling để tính count chính xác

Tracing sampling có thể chỉ lưu một phần requests. Nếu lấy số model spans từ trace store rồi chia cho ChatClient spans, kết quả có thể sai nếu sampling hoặc retention áp dụng không đồng đều.

Để tính tỷ lệ vận hành:

- Dùng Micrometer counters/observations không phụ thuộc trace sampling.
- Dùng traces để điều tra cấu trúc và nguyên nhân.
- Giữ cùng khoảng thời gian, môi trường và bộ lọc.
- Tách request lỗi, request cancel và request hoàn tất nếu SLA yêu cầu.

## 9. Quan sát từng iteration bằng advisor nằm trong tool loop

Nếu muốn quan sát mỗi vòng, có thể đặt một custom advisor sau ToolCallingAdvisor. Advisor đó được gọi lại khi ToolCallingAdvisor re-enter downstream chain.

Ví dụ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

import org.springframework.ai.chat.client.advisor.ToolCallingAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAdvisor;
import org.springframework.ai.chat.client.advisor.api.CallAdvisorChain;
import org.springframework.ai.chat.client.advisor.api.ChatClientRequest;
import org.springframework.ai.chat.client.advisor.api.ChatClientResponse;

public final class DownstreamIterationObserver implements CallAdvisor {

    private final MeterRegistry registry;

    public DownstreamIterationObserver(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public String getName() {
        return "DownstreamIterationObserver";
    }

    @Override
    public int getOrder() {
        return ToolCallingAdvisor.DEFAULT_ORDER + 100;
    }

    @Override
    public ChatClientResponse adviseCall(
            ChatClientRequest request,
            CallAdvisorChain chain) {

        long started = System.nanoTime();
        String outcome = "success";

        try {
            return chain.nextCall(request);
        }
        catch (RuntimeException exception) {
            outcome = "error";
            throw exception;
        }
        finally {
            Timer.builder("app.ai.downstream.iteration")
                .tag("advisor", getName())
                .tag("mode", "call")
                .tag("outcome", outcome)
                .register(registry)
                .record(
                    System.nanoTime() - started,
                    TimeUnit.NANOSECONDS
                );
        }
    }
}
~~~

Advisor có order lớn hơn ToolCallingAdvisor nên nằm phía trong tool loop. Mỗi lần downstream chain được gọi, timer được ghi một lần.

**Cần hiểu đúng ranh giới timer:** đây là thời gian từ observer tới hết phần chain phía sau nó, không nhất thiết là thời gian thuần của ChatModel. Nếu có advisor khác, tool operation hoặc recursive advisor sâu hơn, timer có thể bao gồm các phần đó.

Nếu một recursive advisor khác nằm sau observer, nó cũng có thể gọi lại chain và khiến observer chạy nhiều lần hơn số tool rounds. Vì vậy hãy đặt tên metric là downstream iteration, không khẳng định đây luôn là số model calls. Muốn đếm model operations chính xác, dùng observation gen_ai.client.operation.

### 9.1. Đăng ký observer

~~~java
ChatClient client = chatClientBuilder
    .defaultAdvisors(
        new DownstreamIterationObserver(meterRegistry)
    )
    .build();
~~~

ChatClient vẫn dùng ToolCallingAdvisor auto-registered. Observer được thêm vào chain để thấy mỗi lần chain phía sau tool loop được thực thi.

Không thêm một ToolCallingAdvisor thứ hai. DefaultChatClient duy trì invariant chỉ có một ToolAdvisor trong chain để tránh double execution.

## 10. Quan sát stream và từng model round

Với ChatClient.stream(), một ChatClient invocation có thể chứa nhiều model stream operations nếu tool loop lặp. Mỗi iteration trả về một Flux chunks; ToolCallingAdvisor xử lý tool-call response rồi có thể tạo stream tiếp theo.

Một advisor quan sát stream có thể ghi nhận chunks ở từng iteration:

~~~java
import reactor.core.publisher.Flux;

import org.springframework.ai.chat.client.advisor.ToolCallingAdvisor;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisor;
import org.springframework.ai.chat.client.advisor.api.StreamAdvisorChain;
import org.springframework.ai.chat.client.advisor.api.ChatClientRequest;
import org.springframework.ai.chat.client.advisor.api.ChatClientResponse;

public final class StreamIterationObserver implements StreamAdvisor {

    @Override
    public String getName() {
        return "StreamIterationObserver";
    }

    @Override
    public int getOrder() {
        return ToolCallingAdvisor.DEFAULT_ORDER + 100;
    }

    @Override
    public Flux<ChatClientResponse> adviseStream(
            ChatClientRequest request,
            StreamAdvisorChain chain) {

        return chain.nextStream(request)
            .doOnNext(chunk -> observeChunk(chunk));
    }

    private void observeChunk(ChatClientResponse chunk) {
        // Ghi event có kiểm soát; không log toàn bộ nội dung mặc định.
    }
}
~~~

Advisor nằm trong loop có thể quan sát từng iteration, kể cả chunks liên quan tool-call request. Tuy nhiên, caller nhận ChatClient.stream() không nhất thiết nhận mọi chunk nội bộ của tool-call response: ToolCallingAdvisor lọc các tool-call chunks khỏi stream trả về, trong khi một số provider có thể phát argument deltas để UI hiển thị tiến trình.

Không đồng nhất chunk với model round. Một round có thể phát nhiều chunks; số chunks không phải số lần gọi model.

### 10.1. Đo duration stream từ subscription tới terminal signal

Nếu muốn đo thời gian mỗi stream iteration, bắt đầu timer khi publisher được subscribe và kết thúc ở complete/error/cancel:

~~~java
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Flux;

return Flux.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return chain.nextStream(request)
        .doFinally(signal -> {
            String outcome = switch (signal) {
                case ON_COMPLETE -> "complete";
                case ON_ERROR -> "error";
                case CANCEL -> "cancel";
                default -> "other";
            };

            sample.stop(
                Timer.builder("app.ai.stream.iteration.duration")
                    .tag("outcome", outcome)
                    .register(registry)
            );
        });
});
~~~

Đây là đoạn nằm trong StreamAdvisor có registry, chain và request đã được cung cấp. Flux.defer tạo timer cho mỗi subscription; không đo thời gian chỉ để dựng publisher.

Nếu một stream bị cancel, không coi đó là model round hoàn tất bình thường. Output partial phải được đánh dấu riêng trước khi chuyển tới evaluator.

## 11. ToolCallingAdvisor hooks: một lần khởi tạo, nhiều lần iteration

Nếu cần quan sát chính xác vòng lặp, ToolCallingAdvisor cung cấp hook methods:

| Hook | Tần suất | Mục đích |
|---|---|---|
| doInitializeLoop | Một lần trước vòng đầu | Chuẩn bị trạng thái theo invocation |
| doBeforeCall | Trước mỗi model iteration | Thay đổi tools/options/context của vòng |
| doAfterCall | Sau mỗi model response | Quan sát response, metrics hoặc quyết định |
| doFinalizeLoop | Một lần sau khi vòng kết thúc | Tổng hợp kết quả và dọn trạng thái |
| doGetNextInstructionsForToolCall | Khi chuẩn bị request tiếp theo | Quyết định message/history cho vòng tiếp |

Có các hook tương ứng cho streaming như doBeforeStream, doAfterStream và doFinalizeLoopStream.

Cách nhớ:

~~~text
initialize: 1 lần
before:     N lần
after:      N lần
finalize:   1 lần
~~~

N là số iterations thực tế, bao gồm lần cuối model trả response không còn tool calls.

Đây là extension point phù hợp nếu cần đo chính xác vòng tool mà không phải tự xây lại toàn bộ tool loop. Khi subclass, cần override cả call và stream hooks nếu ứng dụng hỗ trợ hai chế độ.

## 12. Những trường hợp làm vòng lặp kết thúc sớm

Không phải mọi response có tool calls đều tạo thêm một model operation sau khi thực thi tool.

### 12.1. Return-direct

Nếu tool có metadata returnDirect = true, ToolCallingAdvisor thực thi tool rồi trả kết quả trực tiếp cho caller, không gửi tool result trở lại model.

Với một response chứa nhiều tool calls, return-direct chỉ được áp dụng nếu **tất cả** tools trong lượt đó đều có returnDirect = true. Nếu không, kết quả được gửi lại model và vòng tiếp tục.

Do đó:

- Model round có thể yêu cầu tool calls.
- Tool executions vẫn xảy ra.
- Nhưng không có model round tiếp theo.
- Kết quả cuối của ChatClient có thể đến từ tool thay vì model generation.

### 12.2. Tool call cần xác nhận

Nếu ToolCallingManager báo tool call cần con người xác nhận, ToolCallingAdvisor dừng vòng và trả response kèm metadata về những calls đang chờ quyết định.

Ứng dụng xử lý quyết định rồi gửi tool results trong một request tiếp theo. Request tiếp theo là **một ChatClient invocation mới**, không phải tiếp tục cùng invocation đã dừng.

Khi đo latency, phải tách thời gian chờ con người khỏi thời gian xử lý của một ChatClient call.

### 12.3. Tool execution eligibility checker

Mặc định ToolExecutionEligibilityChecker tiếp tục vòng nếu response có tool calls. Có thể thay checker theo provider/ứng dụng, ví dụ cần kiểm tra finish reason ngoài hasToolCalls().

Nếu checker trả false, loop kết thúc theo logic ứng dụng dù response có tool calls. Đây là trường hợp cần kiểm tra cẩn thận vì tool request có thể chưa được thực thi.

## 13. Auto-registration và user-controlled loop

Mặc định, DefaultChatClient tự đăng ký ToolCallingAdvisor khi request có tools. Ứng dụng có thể tắt cơ chế này:

~~~properties
spring.ai.chat.client.tool-calling.enabled=false
~~~

Hoặc tắt cho một call:

~~~java
chatClient.prompt()
    .user(question)
    .tools(orderTools)
    .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
    .call()
    .content();
~~~

Khi auto-registration bị tắt:

- Tool definitions vẫn có thể được gửi tới model.
- Tool calls trong response không tự được thực thi.
- Ứng dụng chịu trách nhiệm gọi ToolCallingManager và gửi kết quả lại model.
- Nếu ứng dụng gọi ChatClient lại ở mỗi vòng, mỗi lần có thể tạo một ChatClient invocation riêng.
- Advisor composition và observability của vòng tự quản lý khác với loop được framework điều phối.

Đừng so trực tiếp số ChatClient invocations giữa hai chế độ mà không tính khác biệt này. Nếu mục tiêu là quan sát từng iteration nhưng vẫn giữ framework loop, thường có thể đặt custom advisor bên trong ToolCallingAdvisor thay vì tắt auto-registration.

## 14. Lịch sử hội thoại giữa các model rounds

ToolCallingAdvisor mặc định quản lý conversation history bên trong vòng. Model round tiếp theo nhận lịch sử có:

- User message ban đầu.
- Model response chứa tool call requests.
- Tool responses từ các lần thực thi trước.
- Các model responses trung gian nếu có.

Điều này cho phép model biết những công cụ đã được gọi và kết quả đã nhận.

Nếu MemoryAdvisor được đặt bên trong tool loop, nó có thể quản lý history theo từng round. Với auto-registered ToolCallingAdvisor, DefaultChatClient nhận biết MemoryAdvisor bên trong loop và tắt internal history để tránh hai nơi cùng quản lý history. Khi tự tạo ToolCallingAdvisor, có thể dùng disableInternalConversationHistory() nếu memory advisor bên trong loop sẽ sở hữu lịch sử.

Trong Spring AI 2.1, SessionAdvisors tạo hai advisor với phạm vi khác nhau:

- SessionTurnAdvisor nằm ngoài loop, chạy một lần cho ChatClient call.
- SessionMemoryAdvisor nằm trong loop, chạy ở mỗi model call.

Điều này giải thích vì sao memory operations có thể lặp cùng model rounds nhưng session turn vẫn chỉ được xử lý một lần.

## 15. Token usage tích lũy qua nhiều model rounds

Một model round có thể dùng tokens cho:

- System prompt.
- User message.
- Conversation history.
- Tool definitions.
- Tool call arguments và tool results.
- RAG context.
- Output của model.

Khi tool loop chạy nhiều lần, model có thể gửi lại một phần lớn history ở mỗi round. Tổng input tokens có thể tăng nhanh hơn số câu hỏi người dùng.

Spring AI ToolCallingAdvisor tích lũy token usage qua các iterations; ChatResponse cuối có thể phản ánh tổng usage của nhiều model calls thay vì chỉ lượt cuối. Cần kiểm tra semantics của provider và phiên bản.

### 15.1. Không cộng usage hai lần

Có hai cách lấy usage:

1. Usage theo từng ChatModel operation từ observations/provider.
2. Usage tích lũy trên ChatResponse cuối của tool loop.

Nếu ChatResponse cuối đã là cumulative usage, không cộng thêm usage của từng model operation vào đó lần nữa. Nếu chỉ có usage từng operation, hãy tổng hợp các operations thuộc cùng invocation.

Công thức ước tính chi phí:

\[
Cost = \sum_{i=1}^{N}
\left(
InputTokens_i \times InputPrice_i
+
OutputTokens_i \times OutputPrice_i
\right)
\]

Trong đó N là số model operations thực tế. Cần giữ model/provider và bảng giá tương ứng cho từng operation, vì tool loop có thể đổi model hoặc option giữa các rounds.

Không coi tool execution count là model token count. Tool có thể chạy nhiều lần nhưng không tự tiêu thụ tokens từ model.

## 16. Latency: tổng thời gian không bằng tổng mọi span duration

Một ChatClient invocation có thể có ba model operations và hai tool executions. Nếu các bước tuần tự, tổng thời gian thường bao gồm các model calls, tool calls, advisor processing và overhead khác.

Nhưng có các trường hợp:

- Nhiều tools trong cùng batch chạy song song.
- VectorStore query chạy song song với một bước khác.
- Advisor span bao gồm downstream spans.
- Model spans có thể được lồng trong advisor spans.
- Một provider SDK có retry nội bộ nằm bên trong một model operation.

Vì vậy không cộng durations của tất cả spans như thể chúng độc lập.

### 16.1. Timeline ví dụ

~~~text
ChatClient invocation                  0 ms ---------------- 3100 ms

Model round 1                          100 ms --- 800 ms
  Tool lookupOrder                                  810 ms - 1050 ms
  Tool getShipment                                  810 ms - 1250 ms

Model round 2                         1300 ms -------- 2050 ms
  Tool getReturnPolicy                              2060 ms - 2300 ms

Model round 3                         2400 ms ---------------- 3000 ms
~~~

Trong ví dụ, hai tool calls đầu chạy song song nên tổng thời gian chờ của batch gần 440 ms, không phải 240 + 440 = 680 ms. Thời gian ChatClient khoảng 3,1 giây, không phải tổng duration của ChatClient + advisor + model + tool spans.

### 16.2. P95 của ChatClient và model operations

P95 ChatClient latency và P95 model-operation latency là hai phân phối khác nhau. Không lấy:

~~~text
P95(ChatClient) - P95(ChatModel)
~~~

để suy ra P95 tool overhead. Các percentile có thể lấy từ những requests khác nhau, và một ChatClient có nhiều model operations.

Nếu muốn tính phần latency ngoài model, hãy ghép các khoảng start/end theo từng trace/invocation, xác định overlap và critical path rồi tính percentile trên kết quả per-invocation.

## 17. Gắn model rounds với evaluation dataset

Một evaluation case có thể tạo một ChatClient invocation và nhiều model operations. Để điều tra regression, lưu correlation data ở tầng evaluation orchestration:

~~~json
{
  "runId": "eval-run-007",
  "caseId": "order-status-012",
  "chatClientInvocation": 1,
  "traceId": "trace-91ab",
  "promptVersion": "prompt-v12",
  "modelVersion": "model-a",
  "toolSetVersion": "tools-v4",
  "modelRounds": [
    {
      "round": 1,
      "modelOperation": 1,
      "toolCalls": ["lookupOrder", "getShipment"]
    },
    {
      "round": 2,
      "modelOperation": 2,
      "toolCalls": ["getReturnPolicy"]
    },
    {
      "round": 3,
      "modelOperation": 3,
      "toolCalls": []
    }
  ],
  "quality": {
    "relevance": "PASS",
    "factuality": "PASS",
    "toolSelection": "PASS"
  }
}
~~~

Đây là schema do ứng dụng định nghĩa, không phải JSON tự động do Spring AI xuất.

### 17.1. Chấm tool selection riêng với final answer

Một câu trả lời cuối đúng không chứng minh tất cả tool calls đều đúng. Evaluation nên tách:

- Tool selection: model chọn đúng tool cần dùng không?
- Tool arguments: tham số có đúng với user intent và quyền truy cập không?
- Tool result handling: model có sử dụng kết quả đúng không?
- Final answer relevance: câu trả lời có đáp ứng câu hỏi không?
- Factuality: các khẳng định có được evidence hỗ trợ không?
- Efficiency: có gọi tool/model dư thừa không?

Nếu số model rounds tăng từ hai lên năm sau khi đổi prompt, hãy kiểm tra tool loop và retry traces. Có thể câu trả lời vẫn đúng nhưng chi phí/latency tăng mạnh.

### 17.2. Phát hiện regression theo round

Giữ cùng dataset và so sánh:

| Chỉ số | Version A | Version B |
|---|---:|---:|
| Mean model operations / ChatClient | 1.7 | 2.8 |
| Mean tool executions / ChatClient | 0.9 | 1.6 |
| P95 ChatClient latency | 2.1 s | 3.8 s |
| Mean input tokens / case | 2.400 | 4.100 |
| Factuality pass rate | 93% | 94% |
| Tool selection pass rate | 96% | 91% |

Các số chỉ minh họa. Version B cải thiện factuality nhẹ nhưng dùng nhiều model calls, tokens và tool executions hơn. Đây có thể là trade-off không phù hợp nếu budget latency/cost chặt.

Không kết luận prompt mới kém chỉ từ round count. Phải xem chất lượng, tool behavior, model/provider, RAG index và rubric/judge versions.

## 18. Kiểm thử một ChatClient invocation có nhiều model rounds

Một integration test nên dùng model fixture deterministic để kiểm tra số model operations và tool executions.

Kịch bản:

~~~text
Model response #1:
  tool call lookupOrder("A123")

Tool result:
  status = SHIPPED

Model response #2:
  tool call getReturnPolicy("electronics")

Tool result:
  returnWindowDays = 14

Model response #3:
  final answer
~~~

Assertions mong đợi:

~~~text
chatClientInvocationCount == 1
modelOperationCount       == 3
toolExecutionCount        == 2
finalAnswerCount          == 1
~~~

Đây là test scenario; fixture ChatModel/ToolCallingManager cụ thể phụ thuộc provider và API phiên bản.

### 18.1. Các trường hợp cần kiểm thử bổ sung

| Case | Kết quả mong đợi |
|---|---|
| Model trả final ngay round đầu | 1 model operation, 0 tool executions |
| Một response yêu cầu hai tools | 1 model operation, 2 tool executions |
| Tool result dẫn tới model gọi tool khác | Nhiều model operations trong một ChatClient invocation |
| returnDirect tool | Tool execution nhưng không có model round tiếp theo |
| Tool confirmation required | Loop tạm dừng, app tiếp tục bằng invocation mới |
| Tool execution lỗi | Outcome lỗi được ghi, không coi là final answer thành công |
| Structured-output retry | Downstream model operation lặp dù không có tool call |
| Stream cancel | Output partial và cancellation được phân loại riêng |
| Auto-registration tắt | App tự điều phối; có thể nhiều ChatClient invocations |
| Memory advisor nằm trong loop | Memory chạy theo từng round, history không bị ghi trùng |

## 19. Lỗi thường gặp khi đếm model rounds

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Một ChatClient call = một model call | ToolCallingAdvisor có thể gọi model nhiều lần | Đếm gen_ai.client.operation |
| Một tool call = một model round | Một response có thể chứa nhiều tool calls | Đếm model response và tool executions riêng |
| Một tool batch = nhiều model rounds | Nhiều tools có thể được xử lý từ cùng response | Dùng model operation boundary |
| Advisor invocation = model operation | Advisor có thể short-circuit hoặc gọi nhiều lần | Dùng model observation để đếm model calls |
| ChatClient span count = user turn count | Một HTTP request có thể có nhiều ChatClient calls | Theo dõi tầng web/user turn riêng |
| Trace không có child model span nghĩa là không gọi model | Sampling/context propagation có thể làm thiếu spans | Đối chiếu metrics và logs |
| Stream chunks = model rounds | Một round phát nhiều chunks | Đếm ChatModel stream operations |
| Cộng ChatResponse cumulative usage với per-round usage | Double count tokens | Chọn một nguồn usage nhất quán |
| Cộng mọi span duration | Span cha bao gồm span con | Phân tích waterfall/critical path |
| Không tính retry advisor | Retry có thể tạo thêm model operations | Gắn retry/iteration metadata |
| Đếm tool được cung cấp như tool đã thực thi | Tool definitions không chứng minh model chọn tool | Kiểm tra tool observations |
| Bỏ qua returnDirect | Tool có thể kết thúc loop mà không gọi model lần nữa | Kiểm tra ToolExecutionResult |
| Gộp manual loop với framework loop | Khác số ChatClient invocations | Ghi rõ loop owner và boundary |

## 20. Checklist vận hành

- [ ] Đã phân biệt user turn, HTTP request, ChatClient invocation, model operation, model round và tool execution?
- [ ] Biết ToolCallingAdvisor được auto-register hay đã bị thay thế/tắt?
- [ ] Đã kiểm tra advisor order và recursive advisors khác?
- [ ] Đã xác định một model response có thể yêu cầu nhiều tool calls?
- [ ] Đã phân biệt tool call batch với model round?
- [ ] Đã quan sát model operations bằng gen_ai.client.operation?
- [ ] Đã quan sát tools bằng spring.ai.tool?
- [ ] Đã kiểm tra returnDirect, confirmation và eligibility checker?
- [ ] Đã xử lý call và stream, complete/error/cancel?
- [ ] Đã biết observer custom nằm trước hay sau các recursive advisors?
- [ ] Đã tránh cộng trùng nested span durations?
- [ ] Đã tính token usage tích lũy mà không double count?
- [ ] Đã liên kết runId/caseId/traceId và model/tool versions?
- [ ] Đã đánh giá tool selection, arguments, relevance và factuality?
- [ ] Đã so sánh latency, rounds, token và cost trên cùng dataset?
- [ ] Đã kiểm tra trace sampling và context propagation trước khi kết luận thiếu model call?

## 21. Tổng kết và tài liệu tham khảo

Một lần gọi ChatClient có thể bao gồm nhiều model rounds vì ToolCallingAdvisor và các recursive advisors gọi lại downstream chain. Mỗi model round thường tương ứng một ChatModel operation; một response có thể chứa nhiều tool calls. Vì vậy, cần đếm riêng ChatClient invocations, model operations, tool calls, tool executions và advisor invocations.

Để nhận diện chính xác, dùng spring.ai.chat.client cho ranh giới invocation, gen_ai.client.operation cho model calls, spring.ai.tool cho tool executions và advisor observations để hiểu chain. Kết hợp trace timeline với metrics counts, token usage và evaluation dataset. Khi thay đổi prompt, model hoặc advisor order, so sánh số rounds cùng relevance, factuality, tool correctness, latency và cost để biết thay đổi có thực sự cải thiện pipeline hay không.

**Tài liệu chính thức:**

1. [Spring AI — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html): tool loop, builder, eligibility checker, hooks, return-direct, conversation history và user-controlled streaming.
2. [Spring AI — Recursive Advisors](https://docs.spring.io/spring-ai/reference/api/advisors-recursive.html): sub-chain, CallAdvisorChain.copy(this) và các dạng recursive advisor.
3. [Spring AI — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): tool calling loop, tool execution, stream arguments, memory ordering và custom ToolAdvisor.
4. [Spring AI — ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): ChatClient call/stream, auto-registration và tool-calling advisor order property.
5. [Spring AI — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient, Advisor, ChatModel, tool observations và token usage.
6. [Spring AI — Session Memory / ChatClient Integration](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html): SessionTurnAdvisor và SessionMemoryAdvisor ở hai phạm vi khác nhau.
7. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): registry, tracing bridge, exporter, histogram và sampling.

*Các số rounds, latency, tokens, tool batches và evaluation records trong bài là ví dụ giảng dạy. Số operations thực tế phụ thuộc model response, advisor order, retry/validation logic, tool eligibility, return-direct, provider và cách ứng dụng điều phối. Hãy kiểm tra traces và metrics trên đúng release đang triển khai trước khi đặt SLA hoặc budget.*
