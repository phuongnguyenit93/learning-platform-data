# Lỗi thiếu tool response, sai ID hoặc sai thứ tự thông điệp

Trong Spring AI Tool Calling, mô hình không tự thực thi method Java. Nó phát ra **tool-call request** gồm tên, arguments và thường là một ID; ứng dụng chạy `ToolCallback` và gửi **tool response** về để mô hình tiếp tục. Nếu hai nửa này bị tách rời, ghép sai ID, đảo thứ tự hoặc một response bị mất, nhà cung cấp model có thể từ chối request, hoặc mô hình tiếp tục với lịch sử sai.

Một lỗi thường xuất hiện dưới dạng thông báo như “tool call has no corresponding tool response”, “invalid tool_call_id” hoặc “messages with role tool must follow an assistant message with tool_calls”. Chuỗi chữ và mã HTTP tùy provider; **nguyên nhân cần chẩn đoán là cấu trúc lịch sử thông điệp**, không đơn thuần là lỗi cú pháp JSON hay tool bị thiếu trong registry.

Bài này thuộc module `SPRING_AI_TOOL_CALLING`, tập trung Spring AI **2.1.0** với `@Tool`, `ToolCallback`, `ToolCallingAdvisor`, `ToolCallingManager`, `ToolContext`, `ChatModel` và Session Memory. Nhánh Spring AI 1.x/2.0.x khác nhau về nơi điều phối vòng gọi; các quy tắc ID/role cũng tùy API provider. Cần đọc message contract của đúng model và API đang dùng trước khi áp dụng một bản vá.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt ID của tool call, tên tool, ID phiên chat, request/trace ID và idempotency key.
- Nhận biết một chuỗi thông điệp hợp lệ khi model trả **một hoặc nhiều** tool calls.
- Chẩn đoán missing response, orphan response, duplicate result, wrong ID/name và wrong ordering.
- Biết vì sao callback throw, timeout, tool-call limit, streaming chưa hoàn chỉnh hoặc memory filter có thể phá cấu trúc hội thoại.
- Sử dụng `ChatClient`/`ToolCallingAdvisor` để tránh tự ghép lịch sử khi không cần thiết.
- Với `ChatModel` cấp thấp, dùng `ToolCallingManager.executeToolCalls(...)` và `ToolExecutionResult.conversationHistory()` thay vì tự lắp role/tool ID.
- Viết validator để phát hiện cặp assistant tool call – tool response không hợp lệ **trước khi gửi provider**.
- Hiểu pause/resume với `requiresConfirmation` trong Spring AI 2.1.0 và lý do không được replay một pause đã đóng.
- Giữ integrity khi stream nhiều chunks, compact history hoặc đồng thời xử lý cùng session.
- Thiết kế test regression cho nhiều tool, failure, resume và session isolation.

## Hợp đồng cơ bản: một lời gọi phải có kết quả tương ứng

Với một số chat API như OpenAI Chat Completions, chuỗi điển hình:

~~~text
USER      "Thời tiết Hà Nội và Đà Nẵng?"
ASSISTANT tool_calls=[
            {id:"call_A", name:"getWeather", arguments:{"city":"Hà Nội"}},
            {id:"call_B", name:"getWeather", arguments:{"city":"Đà Nẵng"}}
          ]
TOOL      tool_call_id="call_A"  {"temperatureC":24}
TOOL      tool_call_id="call_B"  {"temperatureC":28}
ASSISTANT "Hà Nội 24°C, Đà Nẵng 28°C."
~~~

Ở Spring AI, hai kết quả có thể nằm trong **một** `ToolResponseMessage` chứa danh sách `ToolResponse`; provider adapter sẽ chuyển sang cấu trúc protocol thích hợp.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant M as Chat Model
    participant A as Spring AI ToolCallingAdvisor
    participant T as ToolCallingManager
    participant S as Business service

    U->>A: Câu hỏi
    A->>M: User + tool definitions
    M-->>A: Assistant call_A và call_B
    A->>T: executeToolCalls
    T->>S: getWeather(Hà Nội)
    S-->>T: Kết quả A
    T->>S: getWeather(Đà Nẵng)
    S-->>T: Kết quả B
    T-->>A: Tool responses A, B
    A->>M: Assistant call_A/B + tool results A/B
    M-->>A: Câu trả lời cuối
    A-->>U: Câu trả lời
~~~

Các bất biến quan trọng trong một batch:

1. Mỗi tool response phải tham chiếu **đúng call ID** mà model đã phát trong assistant message trước đó.
2. Nếu assistant message có nhiều tool calls, phải có cách xử lý **đầy đủ cho từng call**, bao gồm trường hợp tool bị từ chối hoặc lỗi theo chính sách.
3. Không đưa một user/system/assistant message mới chen giữa batch tool calls và các kết quả còn thiếu, trừ khi protocol cụ thể cho phép một trạng thái pause/continuation khác.
4. Một call không được trả hai kết quả với cùng ID trong cùng batch.
5. Không tự tạo tool response trỏ tới một ID mà model chưa từng yêu cầu.
6. Không bỏ assistant tool-call message rồi chỉ giữ các tool responses.

**Thứ tự và hình thức đóng gói chính xác là tùy provider.** Trong Spring AI một `ToolResponseMessage` có thể chứa nhiều kết quả; trong API khác nó có thể là nhiều message `role=tool`. Điểm chung là tính toàn vẹn và liên kết giữa yêu cầu và kết quả.

## Mỗi ID dùng để làm gì?

| Định danh | Ai tạo/giữ? | Mục đích | Có thay tool call ID được không? |
|---|---|---|---|
| Tool name (`getWeather`) | Ứng dụng đăng ký | Chọn callback thực thi | Không, vì một tool gọi nhiều lần |
| Tool call ID (`call_A`) | Model/provider | Ghép một lời gọi với response | Không |
| Tool response ID/`tool_call_id` | Ứng dụng phản hồi theo call gốc | Tham chiếu lời gọi đang được đáp | Phải khớp call ID |
| Chat session/conversation ID | Ứng dụng/memory | Quản lý lịch sử nhiều turns | Không |
| Trace/request ID | Observability/backend | Theo dõi request xuyên tầng | Không |
| Operation/idempotency key | Business service | Chống side effect trùng | Không |

Hai tool calls **cùng tên** vẫn là hai instance khác nhau. Ví dụ hai lần `getWeather` với thành phố khác nhau phải có response gắn riêng `call_A` và `call_B`. Không dùng tên tool làm khóa ghép:

~~~text
SAI: map["getWeather"] = latestResult
ĐÚNG: map["call_A"] = HanoiResult; map["call_B"] = DaNangResult
~~~

Tool call ID do model tạo cũng **không** là business idempotency key. Khi retry một hành động như hoàn tiền, model có thể phát call ID mới cho cùng operation. Idempotency phải do service điều phối nghiệp vụ bảo vệ bằng operation ID đáng tin.

### OpenAI Chat Completions và Responses API không dùng cùng trường

Ví dụ Chat Completions dùng `tool_calls[].id` và `role:"tool"` với `tool_call_id` tương ứng. Responses API có thể dùng output item `type:"function_call"` và `call_id`, rồi gửi `type:"function_call_output"` trỏ cùng `call_id`; cách tiếp tục bằng `previous_response_id` hoặc replay input cũng khác.

Đừng copy nguyên wire-format của Chat Completions vào Responses API. Spring AI dùng abstraction `AssistantMessage.ToolCall` và `ToolResponseMessage.ToolResponse`; provider adapter chịu trách nhiệm ánh xạ. Nếu ứng dụng tự gọi HTTP provider, cần tuân đúng hợp đồng của API cụ thể.

## Ma trận lỗi phổ biến

| Triệu chứng | Lịch sử bị sai | Nguyên nhân thường gặp |
|---|---|---|
| “Missing tool response” | Có call nhưng không có result | Callback lỗi, timeout, pause chưa resolve, mất message trong store |
| “Unknown tool_call_id” | Result trỏ tới ID không có trong call trước | Tạo ID mới, ghép lệch batch, dùng stale result |
| “Duplicate tool response” | Hai results cùng call ID | Retry ghi lịch sử hai lần, hai worker cùng append |
| “Tool message before assistant tool_calls” | Result đứng trước request | Sort timestamp sai, streaming chưa ghép, serializer order |
| “User message while tool outstanding” | Chèn user turn mới khi chưa hoàn thành batch | Session concurrency, pause bỏ dở |
| “Assistant tool call appears alone after truncation” | History bị cắt mất tool results | Memory window/summary/compact sai |
| “Orphan tool result after truncation” | Giữ TOOL nhưng bỏ ASSISTANT call | Filter sai message type |
| “Tool not found” | Tên tool không có callback tương ứng | Catalog/resolver lỗi; khác với lỗi ID |
| “JSON arguments invalid” | Arguments không parse/schema sai | Conversion/validation; có thể dẫn tới missing result nếu không xử lý lỗi |
| “Provider rejects stream continuation” | Gửi delta rời rạc thay assembled call | Xử lý streaming sai |

Cần phân biệt **lỗi chọn tool** (model yêu cầu một tool không được đăng ký), **lỗi thực thi tool** (callback throw), và **lỗi message integrity** (response không tương ứng hoặc thiếu trong lịch sử). Một vấn đề có thể kéo theo vấn đề khác, nhưng cách khắc phục khác nhau.

## Phân tích ba lịch sử sai điển hình

### Lỗi 1 — Thiếu result cho một call trong batch

~~~text
ASSISTANT tool_calls=[call_A:getWeather, call_B:getWeather]
TOOL      call_A -> {"temperatureC":24}
USER      "Vậy ngày mai thì sao?"
~~~

`call_B` chưa được đáp. Nếu provider yêu cầu batch hoàn chỉnh, việc gửi thêm user message lúc này bị từ chối. Không được chữa bằng cách xóa `call_B` khỏi assistant message đã được model phát và lưu, vì có thể làm biến dạng lịch sử và audit.

**Sửa đúng đường:** hoàn tất call B nếu an toàn; nếu B thất bại và protocol cho phép error content, trả một tool response **gắn đúng ID** với trạng thái lỗi có cấu trúc. Nếu đang chờ approval, tiếp tục đúng pause/resume flow hoặc đóng pause bằng quyết định từ chối hợp lệ; không tự bịa rằng tool đã chạy.

### Lỗi 2 — Response dùng ID khác ID model đã cấp

~~~text
ASSISTANT tool_calls=[call_A:getWeather]
TOOL      tool_call_id="new-uuid-abc" -> {"temperatureC":24}
~~~

Một số orchestration code tự gọi `UUID.randomUUID()` cho mỗi response. Đây là cách làm sai vì response phải tham chiếu `call_A`. ID request/tracing có thể tạo mới, nhưng phải nằm ở metadata riêng.

**Sửa:** lấy nguyên ID từ `AssistantMessage.ToolCall.id()` rồi truyền vào phần response. Không tự “sửa” ID của message gốc sau khi provider đã phát nó. Với provider không trả ID hoặc trả ID trùng, cần dựa trên adapter/provider-specific handling được hỗ trợ, không tự đoán.

### Lỗi 3 — Memory cắt rời cặp messages

~~~text
BEFORE:
  USER        "Tra cứu đơn"
  ASSISTANT   tool_calls=[call_A:getOrder]
  TOOL        call_A -> {"status":"SHIPPED"}
  ASSISTANT   "Đã giao."

AFTER bad trimming:
  TOOL        call_A -> {"status":"SHIPPED"}
  ASSISTANT   "Đã giao."
~~~

Một custom memory advisor có thể giữ “5 message cuối” bằng `subList` mà không kiểm tra turn. Vùng cắt có thể rơi giữa assistant tool call và tool response, dẫn tới orphan result.

**Sửa:** cắt theo **turn** hoặc theo cặp call/response đã đóng hoàn chỉnh; Spring AI 2.1.0 có `EventFilter.lastN(n)` theo turn boundaries và read guard của `SessionMemoryAdvisor`. Không coi `lastN(n)` là giới hạn số messages tuyệt đối.

## Nguyên tắc xử lý lỗi tool: response phải trung thực

Khi callback bị lỗi, không được tùy tiện gửi một result `{"status":"SUCCESS"}` cho đủ số lượng message. Nếu framework/configuration cho phép chuyển exception thành tool error result, trả kết quả nhỏ có cấu trúc, ví dụ:

~~~json
{
  "status": "FAILED",
  "errorCode": "UPSTREAM_TIMEOUT",
  "retryable": true,
  "operationId": "op-7",
  "sideEffectState": "UNKNOWN"
}
~~~

`UNKNOWN` có ý nghĩa quan trọng với tool ghi: timeout không chứng minh provider đã **không** commit. Cần đối soát theo operation/idempotency key trước khi retry. Không gắn `retryable=true` cho lỗi phân quyền, validation hoặc thao tác có nguy cơ lặp mà chưa có cơ chế idempotency.

Một tool `void` thành công vẫn cần result theo hợp đồng provider, ví dụ `"completed"` hoặc JSON trạng thái an toàn; “không có giá trị trả về” không đồng nghĩa bỏ luôn tool response. Với error policy Spring AI dùng `ToolExecutionExceptionProcessor`, cần cấu hình rõ lỗi được biến thành nội dung cho model hay ném ra caller; nếu ném lỗi và dừng vòng, lịch sử đang lưu có thể ở trạng thái pending và cần xử lý ở tầng session.

## Tại sao không nên tự điều phối vòng nếu ChatClient đã làm?

Trong **Spring AI 2.x**, `ChatClient` được thiết kế để chạy vòng tool calling bằng `ToolCallingAdvisor` mặc định. Nó nhận tool calls từ model, yêu cầu `ToolCallingManager` thực thi, lấy `ToolExecutionResult.conversationHistory()` và xây prompt cho iteration tiếp theo. Sử dụng đúng abstraction giảm nguy cơ tự nối sai `AssistantMessage` và `ToolResponseMessage`.

Ví dụ:

~~~java
import java.util.Map;

import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ToolContext;
import org.springframework.ai.tool.annotation.Tool;

@Component
public class WeatherTools {

    private final WeatherService weatherService;

    public WeatherTools(WeatherService weatherService) {
        this.weatherService = weatherService;
    }

    @Tool(description = "Đọc thời tiết theo thành phố")
    public WeatherSummary getWeather(String city, ToolContext ctx) {
        // weatherService kiểm tra quota và gọi upstream.
        return weatherService.find(city);
    }
}

// ChatClient có ToolCallingAdvisor auto-register trong Spring AI 2.x.
String answer = ChatClient.builder(chatModel).build()
        .prompt()
        .user("Thời tiết Hà Nội và Đà Nẵng?")
        .tools(weatherTools)
        .toolContext(Map.of("requestId", requestId))
        .call()
        .content();
~~~

`weatherTools`, `chatModel` và `requestId` là object/giá trị được ứng dụng cấp; `WeatherService` và `WeatherSummary` là service/DTO nghiệp vụ minh họa. Trong mã production, giới hạn danh mục tool theo quyền người dùng và tránh để model tự cung cấp danh tính hoặc token của backend.

**Không** vừa để `ToolCallingAdvisor` auto-execute rồi lại lấy tool calls ở vòng ngoài và tự execute một lần nữa. Việc chạy hai vòng điều phối có thể dẫn tới result trùng, tốn token hoặc side effect trùng. Spring AI 2.x bảo vệ “một `ToolAdvisor` trong chain” nhưng custom orchestrator bên ngoài vẫn có thể tự gây double execution.

### Khi dùng ChatModel trực tiếp

`ChatModel.call(prompt)` trên Spring AI 2.x chỉ trả response của model, **không tự thực thi tool**. Nếu dùng cấp thấp, chính ứng dụng phải gọi manager và đưa lịch sử đủ về model.

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.support.ToolCallbacks;

var manager = ToolCallingManager.builder().build();
var callbacks = ToolCallbacks.from(weatherTools);
var options = ToolCallingChatOptions.builder()
        .toolCallbacks(callbacks)
        .build();

Prompt prompt = new Prompt(
        "Thời tiết Hà Nội và Đà Nẵng?", options
);
ChatResponse response = chatModel.call(prompt);

while (response.hasToolCalls()) {
    ToolExecutionResult execution =
            manager.executeToolCalls(prompt, response);

    if (execution.returnDirect()) {
        // Trả kết quả trực tiếp cho caller, không gọi model nữa.
        break;
    }

    prompt = new Prompt(execution.conversationHistory(), options);
    response = chatModel.call(prompt);
}
~~~

`manager.executeToolCalls(...)` tạo lịch sử có assistant tool-call request và tool responses tương ứng. Tái sử dụng `execution.conversationHistory()` thay vì tự tạo message bằng chuỗi thủ công.

Trong ứng dụng thật cần giới hạn số lượt, deadline, retry, permission, error classification và xử lý `returnDirect`/confirmation/limits. Code minh họa phần **đúng vòng ghép lịch sử**, không phải toàn bộ orchestration production.

### Mốc thay đổi từ 1.x sang 2.x

Spring AI 1.x có internal tool execution loop trong `ChatModel` ở nhiều tích hợp; Spring AI 2.x chuyển trách nhiệm sang `ToolCallingAdvisor` của `ChatClient`. Nếu nâng cấp mà vẫn giả định `ChatModel` tự xử lý callback, tool calls có thể tồn đọng mà không có tool response. Đừng copy mã xử lý 1.x vào 2.x mà không kiểm tra lifecycle.

## Validator Java: phát hiện lịch sử không toàn vẹn

Nếu ứng dụng tự ghép conversation history, nên kiểm tra invariants trước khi gọi provider. Ví dụ sau áp dụng cho profile **bắt buộc tool call ID không rỗng và duy nhất trong mỗi batch** (như Chat Completions). Một số provider trả call không có ID hoặc ID trùng: cần adapter riêng, không áp dụng quy tắc này máy móc.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.ToolResponseMessage;

public final class ToolMessageIntegrityValidator {

    public void validate(List<Message> messages) {
        Map<String, String> pending = new LinkedHashMap<>();

        for (int i = 0; i < messages.size(); i++) {
            Message message = messages.get(i);

            if (message instanceof AssistantMessage assistant) {
                requireClosed(pending, i, "assistant");

                for (AssistantMessage.ToolCall call
                        : assistant.getToolCalls()) {
                    String id = call.id();

                    if (id == null || id.isBlank()) {
                        throw new IllegalArgumentException(
                                "Missing call ID at message " + i
                        );
                    }
                    if (call.name() == null || call.name().isBlank()) {
                        throw new IllegalArgumentException(
                                "Missing tool name at message " + i
                        );
                    }
                    if (pending.putIfAbsent(id, call.name()) != null) {
                        throw new IllegalArgumentException(
                                "Duplicate call ID: " + id
                        );
                    }
                }
                continue;
            }

            if (message instanceof ToolResponseMessage result) {
                if (pending.isEmpty()) {
                    throw new IllegalArgumentException(
                            "Orphan tool response at message " + i
                    );
                }

                for (ToolResponseMessage.ToolResponse response
                        : result.getResponses()) {
                    String expected = pending.remove(response.id());

                    if (expected == null) {
                        throw new IllegalArgumentException(
                                "Unknown or duplicate result ID: "
                                        + response.id()
                        );
                    }
                    if (!expected.equals(response.name())) {
                        throw new IllegalArgumentException(
                                "Tool name mismatch for ID: "
                                        + response.id()
                        );
                    }
                }
                continue;
            }

            // USER / SYSTEM / other message cannot interrupt
            // an unresolved batch in this provider profile.
            requireClosed(pending, i, "other message");
        }

        requireClosed(pending, messages.size(), "end of history");
    }

    private static void requireClosed(
            Map<String, String> pending,
            int index,
            String next) {
        if (!pending.isEmpty()) {
            throw new IllegalArgumentException(
                    "Unanswered calls before " + next
                            + " at index " + index
                            + ": " + pending.keySet()
            );
        }
    }
}
~~~

Validator này có chủ đích **fail closed**:

- `pending` dùng ID, không dùng tool name.
- `putIfAbsent` phát hiện hai calls cùng ID trong một assistant response.
- `remove` phát hiện result không thuộc batch hoặc bị trả hai lần.
- Một hay nhiều `ToolResponseMessage` liên tiếp đều được chấp nhận, miễn kết quả cho mọi call xuất hiện trước message không liên quan.
- Không đòi mọi result trả theo thứ tự hoàn thành của network; nếu provider yêu cầu thứ tự cụ thể, bổ sung rule trong profile của provider.
- Không được chạy validator trên một stream chưa hoàn tất, vì lúc đó thiếu result là trạng thái tạm thời bình thường.

Spring AI 2.1.0 có `ToolResponseMessage.getResponses()` là view text; với kết quả media hoặc error flag, `getResults()`/`ToolResultPart` chứa thông tin đầy đủ hơn. Validator ID này không thay schema validation, permission, business reconciliation hay idempotency.

### Fixture tạo message thật của Spring AI 2.1

~~~java
import java.util.List;

import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.ToolResponseMessage;
import org.springframework.ai.chat.messages.UserMessage;

AssistantMessage calls = AssistantMessage.builder()
        .toolCalls(List.of(
                new AssistantMessage.ToolCall(
                        "call_A", "function",
                        "getWeather", "{\"city\":\"Hà Nội\"}"
                ),
                new AssistantMessage.ToolCall(
                        "call_B", "function",
                        "getWeather", "{\"city\":\"Đà Nẵng\"}"
                )
        ))
        .build();

ToolResponseMessage answers = ToolResponseMessage.builder()
        .responses(List.of(
                new ToolResponseMessage.ToolResponse(
                        "call_A", "getWeather",
                        "{\"temperatureC\":24}"
                ),
                new ToolResponseMessage.ToolResponse(
                        "call_B", "getWeather",
                        "{\"temperatureC\":28}"
                )
        ))
        .build();

List<Message> history = List.of(
        new UserMessage("Thời tiết Hà Nội và Đà Nẵng?"),
        calls,
        answers,
        new AssistantMessage("Hà Nội 24°C, Đà Nẵng 28°C.")
);

new ToolMessageIntegrityValidator().validate(history);
~~~

Constructor `AssistantMessage.ToolCall(id, type, name, arguments)` và `ToolResponseMessage.ToolResponse(id, name, responseData)` là API đã được tài liệu Javadoc Spring AI 2.1.0 mô tả. Provider adapter sẽ đổi các message Spring AI sang wire format cụ thể.

### Test negative cases

~~~java
@Test
void missingResponseMustFail() {
    List<Message> history = List.of(
            new UserMessage("Tra cứu"),
            proposedWithTwoCalls(),
            result("call_A", "getWeather", "{\"ok\":true}")
    );

    assertThatThrownBy(() -> validator.validate(history))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Unanswered calls");
}

@Test
void wrongIdMustFail() {
    List<Message> history = List.of(
            new UserMessage("Tra cứu"),
            proposedWithOneCall("call_A", "getWeather"),
            result("call_X", "getWeather", "{\"ok\":true}")
    );

    assertThatThrownBy(() -> validator.validate(history))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Unknown");
}

@Test
void resultBeforeCallMustFail() {
    List<Message> history = List.of(
            new UserMessage("Tra cứu"),
            result("call_A", "getWeather", "{\"ok\":true}"),
            proposedWithOneCall("call_A", "getWeather")
    );

    assertThatThrownBy(() -> validator.validate(history))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("Orphan");
}

@Test
void duplicateResultMustFail() {
    List<Message> history = List.of(
            new UserMessage("Tra cứu"),
            proposedWithOneCall("call_A", "getWeather"),
            ToolResponseMessage.builder()
                    .responses(List.of(
                            new ToolResponseMessage.ToolResponse(
                                    "call_A", "getWeather", "OK"
                            ),
                            new ToolResponseMessage.ToolResponse(
                                    "call_A", "getWeather", "OK"
                            )
                    ))
                    .build()
    );

    assertThatThrownBy(() -> validator.validate(history))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("duplicate");
}
~~~

`validator` là instance của `ToolMessageIntegrityValidator`. Các helper `proposedWithTwoCalls()`, `proposedWithOneCall(...)` do fixture tạo bằng builder ở trên; `result(...)` có thể triển khai:

~~~java
static ToolResponseMessage result(
        String id, String name, String data) {
    return ToolResponseMessage.builder()
            .responses(List.of(
                    new ToolResponseMessage.ToolResponse(id, name, data)
            ))
            .build();
}
~~~

Bổ sung test response có ID đúng nhưng **name khác**, hai calls trùng ID, response bị lặp qua hai `ToolResponseMessage`, `null`/blank ID và một user message chen vào khi vẫn còn call chưa được trả.

### Không tự động “chữa” một batch bằng thông tin không kiểm chứng

Không lấy một callback result cũ rồi gắn sang ID hiện tại để làm validator PASS. Một kết quả stale có thể thuộc resource/tenant khác. Nếu phải phục hồi từ sự cố, chỉ sử dụng kết quả thực được ghi lại cùng call/operation và có provenance; với side effect, cần kiểm tra trạng thái nguồn trước khi quyết định hoàn thành hay retry.

## Streaming: tool call chưa hoàn chỉnh không phải tool call có thể chạy

Với streaming, response có thể đến theo từng phần:

~~~text
CHUNK 1: index=0, id=call_A, name=getWeather, arguments="{\"city\":"
CHUNK 2: index=0, arguments="\"Hà"
CHUNK 3: index=0, arguments=" Nội\"}"
END: assistant tool-call message hoàn chỉnh
~~~

Một số provider chỉ gửi ID, tên hoặc loại call ở chunk đầu; các chunk sau chứa thêm argument fragments. Nếu ứng dụng gọi tool ngay khi thấy chunk 1, các lỗi có thể xảy ra:

- Arguments là JSON chưa đóng.
- Còn call khác trong cùng response chưa được stream tới.
- Ứng dụng ghi tool response trước khi assistant tool-call message hoàn chỉnh.
- ID/result của tool được nối sai nếu ghép theo chunk arrival thay vì index/call ID.
- Stream bị cancel giữa chừng làm batch chỉ có một phần.

**Quy tắc:** với custom loop, aggregate đủ response theo contract provider, xác minh kết thúc của iteration, rồi mới dùng `ToolCallingManager.executeToolCalls(...)`. Không biến mỗi chunk thành một message history độc lập.

Ví dụ một iteration theo tài liệu `ChatModel` cấp thấp:

~~~java
AtomicReference<ChatResponse> aggregated = new AtomicReference<>();

new MessageAggregator().aggregate(
        chatModel.stream(prompt)
                .doOnNext(chunk -> forwardToSse(chunk)),
        aggregated::set
).blockLast();

ChatResponse complete = aggregated.get();

if (complete == null) {
    throw new IllegalStateException("Stream ended without response");
}

if (complete.hasToolCalls()) {
    ToolExecutionResult result =
            toolCallingManager.executeToolCalls(prompt, complete);

    if (!result.returnDirect()) {
        prompt = new Prompt(
                result.conversationHistory(), chatOptions
        );
    }
}
~~~

Đoạn code mô tả **một lượt** chứ không phải vòng `while` đầy đủ. Các kiểu `MessageAggregator`, `ChatResponse`, `ToolExecutionResult` phải import theo Spring AI BOM đang dùng; `forwardToSse` là hàm của ứng dụng. Nếu không có nhu cầu đặc biệt, dùng `ChatClient.stream()` để `ToolCallingAdvisor` quản lý lifecycle.

Khi stream thất bại trước aggregation, không tự trả “success” cho một call ID nhìn thấy ở chunk đầu. Đối với tool đã khởi chạy ở downstream trước lúc kết nối ngắt, trạng thái có thể là `UNKNOWN`: cần business reconciliation.

## Session Memory 2.1.0: bảo vệ cặp call/result

Khi lịch sử được lưu giữa nhiều requests, một tool call có thể trở thành orphan sau khi filter, trimming hoặc ghi đồng thời. Spring AI **2.1.0** có các biện pháp cụ thể:

- `EventFilter.lastN(n)` giữ **toàn turn**, mở rộng cửa sổ về đầu turn khi cắt giữa các events.
- `SessionMemoryAdvisor` có **read guard**: assistant tool call không có đủ tool messages trả lời ngay sau nó, hoặc tool result không gắn call trước, sẽ bị loại khỏi **prompt view** và ghi `WARN`.
- `SessionMemoryAdvisor`/`SessionTurnAdvisor` bảo đảm tool-call/tool-response messages được lưu theo lifecycle của session, kể cả những trường hợp loop kết thúc không có model round tiếp theo như return-direct hoặc tool-call limit.
- Khi user turn mới đến mà turn trước còn calls mở, `SessionTurnAdvisor` có thể thêm `UNANSWERED_TOOL_RESULT` với ý nghĩa “No result was recorded for this tool call.” để history không còn message thiếu kết quả.

Đây là cơ chế **bảo vệ prompt**, không phải cam kết side effect chưa xảy ra. Nếu lỗi diễn ra sau khi thanh toán commit nhưng trước khi result được ghi vào session, neutral result chỉ nói rằng session **không có bản ghi kết quả**. Cần đối soát payment/ledger theo operation ID.

### Vì sao lastN(3) có thể trả hơn ba events?

~~~text
LOG:
  USER       U1
  ASSISTANT  A1
  USER       U2
  ASSISTANT  tool call_A
  TOOL       result_A
  ASSISTANT  answer_A

EventFilter.lastN(3) => thường mở rộng về U2
để không cắt rời tool-call/result và câu hỏi của lượt.
~~~

Vì vậy `lastN(n)` là cửa sổ được mở rộng theo turn, **không phải hard count bằng n**. Nếu ứng dụng tự implement trimming, chỉ cắt tại boundary giữa các turns đã đóng. Đừng xóa tool message riêng lẻ để tiết kiệm token.

### Read guard cũng có giới hạn

Không dựa vào read guard để “sửa sạch” storage gốc rồi coi mọi thứ là PASS. Nó chỉ chọn một view hợp lệ hơn để gửi model và log cảnh báo. Nếu một phần tool response bị mất hoặc message bị trùng trong repository, cần xác định nguyên nhân ghi dữ liệu, retry và concurrency ở phía ứng dụng.

Các sự cố khó nhận thấy:

- Cùng một session nhận hai request đồng thời. Request sau nhìn thấy call đang chạy của request trước như một call bị bỏ dở, thêm neutral result, rồi result thật tới tạo **hai responses cho một call**.
- Pending confirmation không được xử lý, user gửi input mới. Session đóng pending calls bằng neutral result; sau đó client gửi approval cũ sẽ tạo kết quả trùng.
- Kết quả của chỉ **một phần** batch được gửi lại trong resume. Read guard có thể bỏ call và những tool results chưa đủ khỏi prompt.
- Memory filter custom vô tình ẩn `MessageType.TOOL` nhưng vẫn đưa assistant tool calls vào view.

**Giải pháp trọng tâm:** serialize/lock các requests cùng một session; lưu pause state đáng tin, xử lý trọn batch và tránh resume sau khi pause bị đóng.

## Pause/resume với requiresConfirmation: điểm dễ sai ID

Từ Spring AI **2.1.0**, tool có `@Tool(requiresConfirmation = true)` có thể khiến vòng tạm dừng trước khi chạy batch. `ToolCallingManager` kiểm tra toàn bộ calls của assistant response; nếu có call cần approval, **không call nào trong response đó được thực thi trước quyết định**.

Ứng dụng nhận paused `ChatResponse`, lấy danh sách calls và cho người có quyền quyết định. Khi resume, dùng **đúng paused reply đã lưu** và `ToolCallingManager.executeToolCalls(prompt, reply, decisions)`, không gửi một assistant message giả có ID mới.

Ví dụ:

~~~java
ChatResponse paused = chatClient.prompt()
        .user("Đặt chuyến bay VX205")
        .call()
        .chatResponse();

List<String> awaiting =
        ToolCallDecisions.awaitingDecision(paused);

if (!awaiting.isEmpty()) {
    AssistantMessage assistant =
            paused.getResult().getOutput();

    List<String> keys =
            ToolCallDecisions.toolCallKeys(assistant);

    // Hiển thị tên, arguments, keys cho người có quyền.
    // Lưu paused response ở server-side store chống sửa.
    // Chỉ khi có quyết định hợp lệ mới tiếp tục.
}
~~~

Một reply có ba calls thì decisions phải bao phủ **tất cả ba calls**, kể cả call không yêu cầu approval. Nếu từ chối một call, manager tạo thông điệp từ chối gắn chính ID của call đó thay vì chạy callback; nhờ vậy batch vẫn có result đầy đủ.

### ID trống hoặc trùng: chỉ được xử lý theo contract hỗ trợ

Tài liệu Spring AI 2.1.0 về confirmation quy định `ToolCallDecisions.toolCallKeys(...)` dùng call ID nếu hợp lệ, nhưng khi provider trả call thiếu ID hoặc trùng ID, dùng **vị trí** trong paused reply như `#0`, `#1` làm **decision key**.

Điều này **không có nghĩa** có thể gửi wire response tới provider với `tool_call_id="#0"`. Position key chỉ là khóa quyết định **nội bộ** của confirmation, còn reply và tool results vẫn mang các ID như model cung cấp. Cần bảo toàn reply gốc và để provider adapter xử lý.

Khi lưu pause state:

- Lưu reply gốc ở server-side store người dùng không thể chỉnh.
- Ghi version/session/operation ID và chính sách approval.
- Dùng **cùng thứ tự calls** khi ra quyết định theo positional keys.
- Không nhận tool call arguments hoặc approval decisions từ client rồi chạy trực tiếp khi chưa xác minh.
- Gắn một marker “resolved” để resume chỉ chạy **một lần**; tool ghi cần idempotency.
- Nếu user gửi turn mới và pause đã được đóng, không resume lại.

### Memory nằm ngoài vòng có thể thiếu lịch sử trước pause

Một turn có thể đọc dữ liệu bằng tool A ở vòng đầu, rồi pause ở tool B. Nếu memory advisor nằm **ngoài** tool loop, các rounds cũ có thể chỉ tồn tại trong lịch sử nội bộ của advisor và không được đưa vào request resume. Model có thể mất dữ liệu A mà nó vừa dựa vào để chọn B.

Nếu ứng dụng cần pause/resume nhiều vòng, dùng memory advisor **bên trong** tool loop hoặc session memory 2.1.0 để lưu các tool calls/results cần thiết. Đồng thời kiểm tra repository bảo toàn message parts/IDs. Không “fix” thiếu lịch sử bằng cách chỉ chép tool result A không có assistant call A tương ứng.

## Tránh replay và duplicate side effect khi chữa history

Sửa một thiếu sót giao thức không được tạo side effect thứ hai. Xét:

~~~text
T0: ASSISTANT call_A = createRefund(op-7)
T1: callback gửi request tới payment provider
T2: payment provider COMMITTED refund RF-9001
T3: callback mất mạng, không lưu được tool response
T4: system phát hiện missing response
~~~

Ở T4, gọi lại `createRefund` với operation ID mới là **sai**. Có thể đã hoàn tiền thành công. Phục hồi đúng là:

1. Tra cứu transaction theo operation ID/idempotency key cũ.
2. Nếu xác nhận đã commit, dựng **result trung thực** tham chiếu trạng thái authoritative và call ID đã ghi nhận.
3. Nếu chưa chắc, trả `UNKNOWN`/`RECONCILIATION_REQUIRED`, không tuyên bố thất bại tuyệt đối hay thành công.
4. Nếu chắc chắn chưa commit và retry được phép, dùng cùng operation ID/idempotency key.
5. Cập nhật session một cách nguyên tử để tránh result cũ và result mới cùng tồn tại.

Tool call ID dùng ghép protocol, **không** phải khóa lũy đẳng. Authorization và approval vẫn phải được service kiểm tra tại thời điểm quyết định thao tác.

## Runbook chẩn đoán lỗi production

Khi provider báo missing/wrong tool response, không nên thử xóa ngẫu nhiên các message. Dùng quy trình:

1. **Khoanh vùng:** lỗi từ Spring AI adapter, HTTP provider, MCP server hay session repository? Ghi HTTP status, error code, version provider/BOM.
2. **Xác định turn:** session ID, request ID, model iteration, trace ID. Không dùng ID hiển thị của user thay security principal.
3. **Thu cấu trúc messages an toàn:** role, số tool calls/results, call ID, tool name, vị trí, checksum arguments/result. Không cần log raw PII.
4. **Tìm batch mở:** assistant message nào chứa calls chưa có đủ tool responses ngay sau?
5. **Kiểm tra ID:** trùng/blank ID, result ID không thuộc batch, name mismatch, stale result.
6. **Kiểm tra thứ tự:** user/system/assistant message có chen trước khi batch được đóng không? Tool response có đứng trước assistant call không?
7. **Kiểm tra failure:** callback exception, timeout, limit, returnDirect, confirmation hoặc streaming cancel?
8. **Kiểm tra memory:** trimming/compaction/filter đã bỏ half-message hay hai writers ghi chồng không?
9. **Kiểm tra side effect:** với tool ghi, đối soát transaction trước khi tạo result hoặc retry.
10. **Phục hồi có điều kiện:** dùng manager/session API chính thức; không bịa ID hoặc tạo success result. Sau sửa, chạy validator và test regression tương ứng.

### Log đủ để truy vết nhưng không lộ dữ liệu

Một event quan sát có thể gồm:

~~~json
{
  "traceId": "tr-1024",
  "sessionIdHash": "hashed-session",
  "round": 3,
  "messageIndex": 7,
  "toolName": "createRefund",
  "callId": "call_A",
  "phase": "TOOL_RESULT_APPENDED",
  "resultBytes": 124,
  "status": "RECORDED",
  "operationIdHash": "hashed-operation"
}
~~~

Không log raw JSON arguments, tool results, access token, số tài khoản hay content nhạy cảm mặc định. Với telemetry, hash/sanitize ID theo chính sách của ứng dụng, giảm cardinality và có retention.

Nếu bật `logging.level.org.springframework.ai=DEBUG` để điều tra, phải xem xét phạm vi log, thời gian bật và redaction trước khi dùng production. Spring AI observability mặc định không xuất arguments/results để giảm nguy cơ rò rỉ.

## Regression test theo lớp

| Test | Điều kiện PASS |
|---|---|
| Một call, một result | ID và tool name khớp |
| Nhiều calls cùng tên | Mỗi call có một ID/result riêng |
| Thiếu result thứ hai | Validator từ chối trước provider |
| Result trỏ ID lạ | Validator từ chối |
| Hai responses cùng ID | Validator từ chối |
| Tool result xuất hiện trước assistant call | Validator từ chối |
| User turn chen vào batch mở | Từ chối hoặc xử lý pause đúng flow |
| Callback throw | Error policy rõ, không tạo success giả |
| Timeout sau commit | Đối soát, không tạo duplicate refund |
| Stream tool arguments chia chunks | Chỉ execute sau aggregation hoàn chỉnh |
| Stream bị hủy | Không tự chép partial call thành completed |
| Memory window cắt giữa turn | Active view vẫn hợp lệ hoặc guard loại an toàn |
| Hai requests cùng session | Application lock/serialization ngăn interleaving |
| Confirmation allow/deny | Quyết định đầy đủ cho tất cả call IDs |
| Pause resume lần hai | Bị chặn hoặc idempotent |
| Wrong tenant | Không có side effect và không rò data |
| ReturnDirect | Không ép một model round mới khi đã kết thúc hợp lệ |
| Call limit | Không làm biến mất partial results/metadata |

### Fake model integration test

Với Spring AI `ChatModel` test double, lập trình phản hồi theo chuỗi:

1. Vòng 1 trả assistant message có hai `ToolCall`.
2. Tool A thành công và tool B trả error theo policy.
3. Vòng 2 nhận lịch sử có cả hai responses gắn đúng ID.
4. Model tạo câu trả lời đã kiểm tra.
5. Assert chỉ một lần execution cho mỗi callback (trừ retry có policy).
6. Assert không mất ID, không có duplicate messages và đúng `ToolContext`.

Làm thêm case streaming bằng cách chia arguments thành nhiều chunks. Test này nên chạy qua `ChatClient` để xác minh `ToolCallingAdvisor`, không chỉ gọi method nghiệp vụ trực tiếp. Với `ChatModel` cấp thấp, test `manager.executeToolCalls(...)` rồi dùng `result.conversationHistory()` để kiểm tra cấu trúc.

### Session integration test

Dùng session repository test:

- Seed một turn với tool call + result rồi gọi `EventFilter.lastN(1)`; view không bị cắt giữa pair.
- Seed orphan tool result và kiểm tra read guard cảnh báo/loại khỏi prompt.
- Seed paused call; thử user input mới để kiểm tra neutral unanswered result đúng semantics.
- Test resume sau user turn mới bị chặn bởi workflow ứng dụng.
- Gửi hai requests cùng session và xác minh lock/serialize.
- Test bất biến idempotency ở service khi một result bị ghi muộn.

**Không** chạy tool ghi thật trên tài khoản sản xuất để thử missing response; dùng sandbox/test database có assertion trạng thái.

## Các nhầm lẫn cần tránh

- **Coi tool name là tool call ID:** một tool có thể được gọi nhiều lần trong một response.
- **Tự tạo UUID mới làm response ID:** ID phải tham chiếu lời gọi tương ứng từ model.
- **Chỉ trả kết quả cho call thành công:** call lỗi/từ chối cũng cần response theo chính sách, hoặc dừng vòng đúng cách.
- **Bỏ hẳn response vì tool trả `void`:** không hợp lệ với provider đòi result.
- **Execute streaming delta ngay:** arguments và batch chưa hoàn chỉnh.
- **Bỏ assistant call nhưng giữ tool result khi compact:** tạo orphan result.
- **Tắt lịch sử của ToolCallingAdvisor không có memory thay thế:** model mất kết quả vòng trước.
- **Chạy hai requests đồng thời trên cùng session:** có thể ghi interleaving/duplicate result.
- **Dùng positional decision key `#0` như tool_call_id wire:** đó chỉ là key nội bộ của confirmation.
- **Tự tin tool chưa chạy vì SessionTurnAdvisor ghi neutral marker:** ledger có thể đã commit.
- **Dùng call ID làm idempotency key:** retry khác call ID vẫn có thể là cùng operation nghiệp vụ.
- **Cho rằng chỉ cần sửa prompt:** lỗi ID/ordering là hợp đồng message và orchestration phía ứng dụng.
- **Nhầm Chat Completions với Responses API:** chúng có wire-format và continuation khác nhau.

## Checklist trước khi phát hành

- [ ] Biết provider/API cụ thể và quy tắc role/ID/ordering tương ứng.
- [ ] Mọi assistant tool call được ghép với đúng result ID.
- [ ] Nhiều calls trong một batch được xử lý đầy đủ.
- [ ] Không có orphan, duplicate response hoặc message chen vào batch mở.
- [ ] Với `ChatClient` chỉ có một vòng điều phối `ToolCallingAdvisor`.
- [ ] Với `ChatModel` trực tiếp dùng `ToolCallingManager` và `conversationHistory()`.
- [ ] Streaming chỉ execute sau khi có aggregated response hoàn chỉnh.
- [ ] Memory filter/compaction bảo toàn turn boundaries và call/result pairs.
- [ ] Requests cùng session được serialize, không ghi đồng thời.
- [ ] Pause/resume dùng stored reply, decisions đầy đủ và approver đáng tin.
- [ ] Không resume pause đã đóng bằng user turn mới.
- [ ] Không tự tạo success result khi lỗi/timeout; đối soát side effect.
- [ ] Có operation ID/idempotency key riêng cho tool ghi.
- [ ] Trace chỉ ghi metadata an toàn và có correlation IDs.
- [ ] Có unit/integration tests cho missing, wrong, duplicate, ordering và recovery.
- [ ] Không mở rộng quyền tool khi thử khôi phục một message lỗi.

## Ghi nhớ

Tool Calling thành công không chỉ là gọi đúng Java method. Mô hình tạo **assistant tool call**, ứng dụng thực thi và phải nối **tool response đúng ID, đúng batch và đúng thứ tự** trước khi mô hình tiếp tục. Lỗi missing response, wrong ID và wrong ordering chủ yếu nằm ở ranh giới orchestration, streaming và session history.

Trong Spring AI 2.x, ưu tiên `ChatClient` với `ToolCallingAdvisor`; nếu dùng `ChatModel` thấp hơn, hãy tái sử dụng `ToolExecutionResult.conversationHistory()`. Session Memory 2.1.0 giúp bảo vệ active view và có neutral result cho pending call bị bỏ dở, nhưng không tự xác minh side effect: với tool ghi, luôn đối soát nguồn nghiệp vụ và giữ idempotency.

## Tài liệu tham khảo

- [Spring AI 2.1.0 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/api/tools/tool-calling-advisor.html)
- [Spring AI 2.1.0 — ChatModel Tool Calling / Manual Loop](https://docs.spring.io/spring-ai/reference/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI 2.1.0 — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI 2.1.0 — Session ChatClient Integration / Tool-call Integrity](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html)
- [Spring AI 2.1.0 — Session Event Filtering](https://docs.spring.io/spring-ai/reference/api/session/event-filter.html)
- [Spring AI 2.1.0 — Session Concepts](https://docs.spring.io/spring-ai/reference/api/session/concepts.html)
- [Spring AI 2.1.x Javadoc — AssistantMessage.ToolCall](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/AssistantMessage.ToolCall.html)
- [Spring AI 2.1.x Javadoc — ToolResponseMessage.ToolResponse](https://docs.spring.io/spring-ai/docs/2.1.x/api/org/springframework/ai/chat/messages/ToolResponseMessage.ToolResponse.html)
- [OpenAI API — Function Calling (Chat Completions vs Responses)](https://developers.openai.com/api/docs/guides/function-calling)





