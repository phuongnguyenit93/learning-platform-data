# Liên kết conversation ID và tập công cụ ở phạm vi trace

## 1. Vì sao cần liên kết conversation ID với tool set?

Một trợ lý chăm sóc khách hàng có thể xử lý nhiều lượt trong cùng một cuộc hội thoại:

- Lượt 1: người dùng hỏi tình trạng đơn hàng.
- Lượt 2: người dùng hỏi chính sách đổi trả của đơn hàng đó.
- Lượt 3: người dùng yêu cầu tạo phiếu hỗ trợ.

Mỗi lượt có thể tạo một lần gọi ChatClient, một hoặc nhiều model operations và một số tool executions. Nếu chỉ nhìn metric tổng, đội vận hành khó trả lời:

- Các trace nào thuộc cùng một cuộc hội thoại?
- Lượt nào được cung cấp tập tools nào?
- Model được gửi những tool definitions nào?
- Tool nào thực sự được gọi, ở thời điểm nào và với call ID nào?
- Một lỗi tool có ảnh hưởng tới câu trả lời cuối của lượt đó không?
- Chất lượng, latency và chi phí thay đổi ra sao khi thay tool set hoặc prompt?

Spring AI cung cấp các observation attributes để đưa **conversation ID** và **tên tools** vào phạm vi trace. Khi kết hợp với các span của ChatModel và tool execution, người vận hành có thể lần theo một lượt xử lý và đối chiếu nhiều lượt thuộc cùng một hội thoại.

Bài thuộc chương **ChatClient và advisor** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module tập trung đánh giá ứng dụng Spring AI bằng dataset, relevance, fact checking, kiểm thử RAG/tool calling và theo dõi metrics, traces, chi phí, độ trễ qua từng phiên bản prompt, model và pipeline.

Sau bài, bạn có thể:

1. Phân biệt conversation ID, trace ID, span ID, tool call ID và evaluation run ID.
2. Đọc đúng các attributes **spring.ai.chat.client.conversation.id** và **spring.ai.chat.client.tool.names**.
3. Phân biệt tập tools được truyền vào ChatClient, tool definitions gửi cho model và tool thực sự được thực thi.
4. Dùng Session Memory hoặc MemoryAdvisor để cung cấp conversation ID cho mỗi request.
5. Liên kết ChatClient, ChatModel và tool observations mà không giả định mọi span luôn được nối hoàn hảo.
6. Tránh đưa high-cardinality data hoặc nội dung nhạy cảm vào metrics và traces ngoài chủ đích.
7. Kết nối trace với dataset, prompt/model/tool-set version và kết quả đánh giá chất lượng.

> Tên observation và attributes trong bài lấy tài liệu Spring AI **2.1.0** làm mốc. API Session Memory, cấu hình provider, tracing bridge và hành vi tool calling cần được đối chiếu với release mà dự án thực tế đang dùng.

## 2. Phân biệt các loại ID trước khi thiết kế trace

Các ID sau có phạm vi khác nhau và không thể thay thế cho nhau:

| ID | Phạm vi | Vòng đời | Dùng để trả lời |
|---|---|---|---|
| conversationId / sessionId | Một cuộc hội thoại logic | Có thể kéo dài qua nhiều lượt ChatClient | Những lượt nào thuộc cùng hội thoại? |
| traceId | Một distributed trace | Thường gắn với một lần xử lý hoặc một chuỗi hoạt động liên quan | Những span nào thuộc cùng một lần thực thi? |
| spanId | Một operation cụ thể trong trace | Bắt đầu và kết thúc theo operation | Bước nào đang được đo? |
| toolCallId | Một tool call do model yêu cầu | Một lần gọi công cụ cụ thể | Kết quả tool nào trả lời đúng yêu cầu gọi nào? |
| runId | Một lần chạy pipeline/evaluation do ứng dụng định nghĩa | Theo lần chạy dataset hoặc thí nghiệm | Kết quả đánh giá nào thuộc lần chạy nào? |
| caseId | Một case trong dataset | Có thể xuất hiện trong nhiều runs | Case nào pass/fail qua các phiên bản? |

Một cuộc hội thoại có thể có nhiều trace:

~~~text
conversationId = conv-7f31

  Trace T1: user turn 1
    ChatClient
    ChatModel
    Tool lookupOrder

  Trace T2: user turn 2
    ChatClient
    ChatModel
    Tool getReturnPolicy

  Trace T3: user turn 3
    ChatClient
    ChatModel
    Tool createSupportTicket
~~~

Trong ví dụ này:

- conversationId giống nhau để nhóm ba lượt hội thoại.
- traceId khác nhau để điều tra từng lần thực thi.
- Mỗi operation có spanId riêng.
- Mỗi tool invocation có thể có toolCallId riêng.
- runId và caseId thuộc tầng đánh giá nếu ứng dụng đang chạy dataset.

**Không dùng conversation ID làm trace ID.** Nếu gán cùng một trace ID cho toàn bộ cuộc hội thoại dài ngày, trace sẽ phình to, khó tìm lỗi của từng lượt và vượt giới hạn vòng đời của tracing backend.

## 3. Quy tắc cardinality trong Spring AI

Spring AI dựa trên Micrometer Observation. Tài liệu Spring AI 2.1.0 phân loại attributes thành hai nhóm:

- **Low-cardinality keys**: được thêm vào metrics và traces.
- **High-cardinality keys**: chỉ được thêm vào traces.

Lý do là metrics cần tập nhãn hữu hạn để tổng hợp ổn định. Nếu mỗi conversation ID tạo một nhãn riêng, số time series có thể tăng theo số người dùng và số lượt gọi.

### 3.1. Các attributes của ChatClient

Observation **spring.ai.chat.client** được ghi khi gọi ChatClient **call()** hoặc **stream()**.

| Attribute | Cardinality | Ý nghĩa |
|---|---|---|
| **gen_ai.operation.name** | Thấp | Luôn là **framework** |
| **gen_ai.system** | Thấp | Luôn là **spring_ai** |
| **spring.ai.chat.client.stream** | Thấp | **true** hoặc **false** |
| **spring.ai.kind** | Thấp | **chat_client** |
| **spring.ai.chat.client.advisors** | Cao | Danh sách advisor được cấu hình |
| **spring.ai.chat.client.conversation.id** | Cao | ID cuộc hội thoại khi dùng chat memory |
| **spring.ai.chat.client.tool.names** | Cao | Tên tools được truyền cho ChatClient |

Hai attributes cần nhớ cho bài này:

~~~text
spring.ai.chat.client.conversation.id
spring.ai.chat.client.tool.names
~~~

Chúng cho phép xem một ChatClient invocation thuộc cuộc hội thoại nào và được cung cấp những tools nào. Theo quy ước, chúng thuộc **trace**, không phải metric labels.

### 3.2. Attributes của ChatModel

Observation **gen_ai.client.operation** được ghi khi gọi ChatModel **call()** hoặc **stream()**.

Một attribute liên quan đến tập tools là:

| Attribute | Cardinality | Ý nghĩa |
|---|---|---|
| **spring.ai.model.request.tool.names** | Cao | Danh sách tool definitions được cung cấp cho model trong request |

Attribute này hữu ích khi cần so sánh danh sách tools đã được truyền cho ChatClient với danh sách definitions thực sự đi vào một model request. Hai danh sách có thể khác nhau nếu advisor bổ sung tools động, có bộ lọc hoặc có cơ chế progressive tool disclosure.

### 3.3. Attributes của tool execution

Spring AI ghi observation **spring.ai.tool** khi thực thi tool trong một tương tác chat model.

| Attribute | Cardinality | Ý nghĩa |
|---|---|---|
| **gen_ai.operation.name** | Thấp | **execute_tool** |
| **gen_ai.system** | Thấp | **spring_ai** |
| **spring.ai.kind** | Thấp | **tool_call** |
| **spring.ai.tool.definition.name** | Thấp | Tên tool |
| **spring.ai.tool.type** | Thấp | Loại tool; mặc định **function** |
| **spring.ai.tool.definition.description** | Cao | Mô tả tool |
| **spring.ai.tool.definition.schema** | Cao | Schema tham số tool |
| **spring.ai.tool.call.id** | Cao | ID tool call do model cung cấp |
| **spring.ai.tool.call.arguments** | Cao, tùy chọn | Arguments của tool call |
| **spring.ai.tool.call.result** | Cao, tùy chọn | Kết quả thực thi tool |

**spring.ai.tool.definition.name** mô tả **tool đã được thực thi**. Nó khác với **spring.ai.chat.client.tool.names**, vốn mô tả tập tools được truyền vào ChatClient.

## 4. Ba tập hợp cần phân biệt khi đọc trace

Một hệ thống tool calling có ít nhất ba góc nhìn:

1. **Tools passed to ChatClient**: tập tools ứng dụng đăng ký cho invocation.
2. **Tool definitions sent to model**: các định nghĩa model thực sự được nhận trong một model request.
3. **Tools executed**: những tool mà model yêu cầu và ứng dụng thực thi.

Ví dụ:

~~~text
ChatClient span:
  spring.ai.chat.client.tool.names =
    [lookupOrder, getShipment, getReturnPolicy]

ChatModel span:
  spring.ai.model.request.tool.names =
    [lookupOrder, getShipment, getReturnPolicy]

Tool execution spans:
  spring.ai.tool.definition.name = lookupOrder
  spring.ai.tool.definition.name = getShipment
~~~

Diễn giải:

- ChatClient được cung cấp ba tools.
- Model request có ba tool definitions.
- Model chỉ yêu cầu thực thi hai tools trong ví dụ.
- getReturnPolicy có trong tập khả dụng nhưng không có tool execution span.

**Có tên tool trong tool.names không chứng minh tool đó đã chạy.** Muốn xác nhận thực thi, xem **spring.ai.tool** observation và kết quả từ tool callback.

### 4.1. Tập tools có thể thay đổi giữa các model rounds

Một tool-calling loop có thể thực hiện nhiều model requests trong một ChatClient invocation. Advisor có thể bổ sung, loại bỏ hoặc tìm kiếm tools giữa các vòng. Vì vậy, **spring.ai.model.request.tool.names** có thể phản ánh tập definitions của từng request model, còn **spring.ai.chat.client.tool.names** phản ánh tập tools được truyền vào ChatClient invocation.

Không giả định hai attributes luôn bằng nhau khi ứng dụng có:

- Advisor thêm tools động.
- Tool Search hoặc progressive tool disclosure.
- MCP providers và tool filters.
- Tool definitions được chọn theo quyền hoặc ngữ cảnh.
- Một custom tool-calling loop.

Khi hai danh sách khác nhau, hãy kiểm tra từng model operation và các advisor thay đổi request.

## 5. Gắn conversation ID qua Session Memory trong Spring AI 2.1

Trong Spring AI 2.1.0, Session Memory là hướng được khuyến nghị thay cho API **ChatMemory** và **MessageChatMemoryAdvisor** cũ, vốn đã deprecated từ 2.1.0 để chuyển sang session advisors.

Session advisors gồm hai thành phần:

- **SessionTurnAdvisor**: chạy ở phạm vi một ChatClient call, bên ngoài tool-calling loop.
- **SessionMemoryAdvisor**: xử lý lịch sử ở từng model call, bên trong tool-calling loop.

**SessionAdvisors.session(sessionId)** đặt session ID vào context của request. Key **SessionMemoryAdvisor.SESSION_ID_CONTEXT_KEY** có giá trị **chat_memory_conversation_id**, bằng **MemoryAdvisor.CONVERSATION_ID**. Spring AI dùng thông tin memory này để ghi attribute **spring.ai.chat.client.conversation.id** trên ChatClient observation.

### 5.1. Đăng ký SessionAdvisors

Ví dụ cấu hình:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.session.SessionService;
import org.springframework.ai.session.advisor.SessionAdvisors;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AssistantConfiguration {

    @Bean
    ChatClient assistantChatClient(
            ChatClient.Builder builder,
            SessionService sessionService) {

        return builder
            .defaultAdvisors(
                SessionAdvisors.builder(sessionService).build()
            )
            .build();
    }
}
~~~

**SessionService** có thể được cung cấp bởi cấu hình session repository phù hợp. Spring AI có repository in-memory cho test/demo và JDBC repository cho lưu trữ lâu dài theo starter tương ứng.

**SessionAdvisors** nằm trong artifact **spring-ai-session-advisor**; các kiểu session và service cốt lõi thuộc module **spring-ai-session**. Nếu dùng starter JDBC session của Spring AI, hãy kiểm tra starter/version đã kéo đúng các module này vào dependency graph.

### 5.2. Truyền session ID ở mỗi lần gọi

~~~java
import org.springframework.ai.session.advisor.SessionAdvisors;

String answer = assistantChatClient.prompt()
    .user(question)
    .advisors(SessionAdvisors.session(conversationId))
    .call()
    .content();
~~~

Mỗi lần gọi phải cung cấp session ID. Không có session ID mặc định. Nếu thiếu, session advisor ném **IllegalStateException**; một session dùng chung cho mọi người dùng có thể làm trộn lịch sử của nhiều người.

**Nguồn của conversationId phải do ứng dụng kiểm soát.** Thông thường backend xác định session hiện tại sau khi xác thực người dùng, kiểm tra quyền sở hữu và tenant. Không lấy một ID bất kỳ do client gửi rồi dùng nó để truy cập session mà không kiểm tra quyền.

### 5.3. Conversation ID xuất hiện ở đâu?

Khi memory/session advisor được cấu hình và session ID được truyền đúng, ChatClient observation có thể mang:

~~~text
spring.ai.chat.client.conversation.id = conv-7f31
~~~

Mỗi ChatClient call trong cùng hội thoại có thể có cùng conversation ID nhưng trace ID riêng.

Nếu ứng dụng không dùng chat memory/session advisor, đừng mặc định attribute conversation ID sẽ tự xuất hiện. Một trường sessionId trong prompt hoặc message metadata không tự động thay thế context key của memory advisor.

## 6. Tương thích với ChatMemory API cũ

Một số dự án vẫn dùng **MessageChatMemoryAdvisor**. Với API cũ, conversation ID phải được truyền qua **MemoryAdvisor.CONVERSATION_ID** trong mỗi call:

~~~java
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.client.advisor.MessageChatMemoryAdvisor;
import org.springframework.ai.chat.client.advisor.api.MemoryAdvisor;

ChatClient chatClient = builder
    .defaultAdvisors(
        MessageChatMemoryAdvisor.builder(chatMemory).build()
    )
    .build();

String answer = chatClient.prompt()
    .user(userText)
    .advisors(advisors -> advisors
        .param(MemoryAdvisor.CONVERSATION_ID, conversationId))
    .call()
    .content();
~~~

Nếu không truyền parameter, Spring AI ném **IllegalArgumentException**. Không có default conversation ID.

**Lưu ý phiên bản:** tài liệu Spring AI 2.1.0 đánh dấu **MessageChatMemoryAdvisor** và API **ChatMemory** deprecated để chuyển sang session memory. Với dự án mới, ưu tiên **SessionAdvisors**; với dự án cũ, giữ đúng cơ chế ID của API hiện tại và lên kế hoạch migration theo release notes.

## 7. Truyền tập tools vào ChatClient

Tên tool được lấy từ các tool definitions mà ứng dụng đăng ký. Có thể truyền tools ở cấp ChatClient hoặc từng invocation.

Ví dụ khai báo tool:

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class OrderTools {

    @Tool(description = "Tra cứu trạng thái đơn hàng theo mã đơn")
    public String lookupOrder(
            @ToolParam(description = "Mã đơn hàng") String orderId) {
        return "Đơn hàng " + orderId + " đang được vận chuyển.";
    }

    @Tool(description = "Tra cứu chính sách đổi trả")
    public String getReturnPolicy(String productCategory) {
        return "Chính sách đổi trả cho nhóm " + productCategory;
    }
}
~~~

Truyền tools theo từng request:

~~~java
String answer = assistantChatClient.prompt()
    .user("Kiểm tra đơn A123")
    .tools(orderTools)
    .advisors(SessionAdvisors.session(conversationId))
    .call()
    .content();
~~~

Hoặc đăng ký tools mặc định khi build ChatClient:

~~~java
ChatClient assistantChatClient = builder
    .defaultTools(orderTools)
    .defaultAdvisors(
        SessionAdvisors.builder(sessionService).build()
    )
    .build();
~~~

Khi tools được truyền vào ChatClient, observation **spring.ai.chat.client** có thể ghi danh sách tên tại **spring.ai.chat.client.tool.names**.

Không cần đưa tên tools vào prompt chỉ để tạo trace attribute. Tool definitions và tool observation có cơ chế observability riêng.

### 7.1. MCP tools và tập tools động

Local **@Tool** methods và remote MCP tools đều có thể được đưa vào ChatClient thông qua **ToolCallback** hoặc **ToolCallbackProvider**. Nếu ứng dụng dùng MCP, cần chủ động truyền provider vào **.tools(...)** hoặc **.defaultTools(...)** theo cấu hình tương ứng.

Tập tools có thể khác theo request do:

- Tool provider trả về tập callback khác nhau.
- MCP tool filters giới hạn tool theo server hoặc tên.
- Advisor thêm tool theo ngữ cảnh.
- Tool Search chỉ đưa các tool đã được khám phá vào model request.
- Quyền hoặc chính sách ứng dụng quyết định tool nào được cung cấp.

Trace giúp quan sát danh sách tên ở từng ranh giới. Tuy nhiên, danh sách tên không thay thế việc kiểm tra authorization hoặc nguồn gốc của tool callback.

## 8. Đọc một trace có conversation ID và tool names

Sơ đồ dưới đây thể hiện **quan hệ logic mong muốn** khi instrumentation và context propagation tạo được cây span đầy đủ:

~~~mermaid
flowchart TD
    HTTP["HTTP request / trace T1"]
    CHAT["ChatClient span<br/>conversation.id = conv-7f31<br/>tool.names = lookupOrder, getReturnPolicy"]
    MODEL1["ChatModel operation #1<br/>model.request.tool.names = lookupOrder, getReturnPolicy"]
    TOOL1["Tool span<br/>definition.name = lookupOrder<br/>tool.call.id = call-01"]
    MODEL2["ChatModel operation #2"]
    TOOL2["Tool span<br/>definition.name = getReturnPolicy<br/>tool.call.id = call-02"]
    FINAL["Final response"]

    HTTP --> CHAT
    CHAT --> MODEL1
    MODEL1 --> TOOL1
    TOOL1 --> MODEL2
    MODEL2 --> TOOL2
    TOOL2 --> FINAL
~~~

Khi mở trace, đọc theo thứ tự:

1. Xem ChatClient span và lấy **spring.ai.chat.client.conversation.id**.
2. Xem **spring.ai.chat.client.tool.names** để biết tập tools được truyền vào invocation.
3. Mở từng ChatModel operation và so **spring.ai.model.request.tool.names**.
4. Mở từng **spring.ai.tool** span để biết tool thực sự được gọi.
5. Dùng **spring.ai.tool.call.id** để phân biệt các tool calls.
6. Đối chiếu kết quả tool và response cuối trong hệ thống log/report có quyền truy cập phù hợp.

Nếu có nhiều model rounds, có thể có nhiều ChatModel spans và tool spans trong cùng một lượt ChatClient. Đừng giả định một ChatClient invocation chỉ có một model operation.

## 9. Giới hạn quan trọng: tool spans có thể không nối liền ChatClient span

Tài liệu Spring AI 2.1.0 nêu một giới hạn triển khai: tool calling là luồng imperative/blocking, trong khi ChatClient kết hợp imperative và reactive. Điều này có thể tạo **partial hoặc interrupted Micrometer observations**; ví dụ ChatClient span và tool calling spans không được nối với nhau, và span đầu có thể còn ở trạng thái incomplete.

Điều đó có nghĩa:

- Cây span trên là mô hình logic để hiểu dữ liệu cần liên kết.
- Không phải mọi provider/stack đều bảo đảm trace viewer hiển thị đúng cây parent-child như sơ đồ.
- Không có tool span nằm dưới ChatClient span không tự chứng minh tool không được thực thi.
- Một ChatClient span chưa hoàn tất có thể là giới hạn observation của đường tool-calling, không nhất thiết là request vẫn đang chạy.
- Cần kiểm tra trace ID, span status, tool observation, log có correlation và behavior của phiên bản provider thực tế.

Spring AI ghi tool observations và truyền tracing context khi có **Tracer**, nhưng việc liên kết span còn phụ thuộc đường thực thi và context propagation. Nếu cần audit từng vòng tool, hãy lưu thêm một **runId** hoặc correlation ID ở tầng ứng dụng và đối soát bằng dữ liệu có kiểm soát.

## 10. Conversation ID không tự động trở thành ToolContext

Một lỗi thiết kế phổ biến là nghĩ rằng vì ChatClient span có conversation.id, mọi tool method cũng tự nhận được ID đó.

Hai cơ chế khác nhau:

| Cơ chế | Mục đích | Model có nhận giá trị không? |
|---|---|---|
| Observation attribute | Truy vết operation | Không phải dữ liệu prompt |
| Session/memory context | Chọn lịch sử hội thoại | Không tự động gửi ID thành nội dung model |
| **ToolContext** | Truyền dữ liệu nội bộ cho tool | Không; dữ liệu ToolContext không được gửi cho model |
| Tool arguments | Tham số do model yêu cầu | Có; model tạo các arguments này |

**ToolContext** dùng để truyền dữ liệu như tenant ID, user ID hoặc request scope đến tool method. Ví dụ:

~~~java
String answer = chatClient.prompt()
    .user("Tra cứu khách hàng 42")
    .tools(customerTools)
    .toolContext(Map.of("tenantId", tenantId))
    .call()
    .content();
~~~

Tool có thể nhận **ToolContext** để kiểm tra phạm vi dữ liệu. Các giá trị trong ToolContext được chuyển trực tiếp tới tool execution, không qua model.

### 10.1. Có nên đưa session ID vào mọi tool?

Với SessionAdvisors, **sessionIdInToolContext(true)** có thể đưa session ID vào ToolContext của mỗi tool call. Tùy chọn này mặc định tắt.

Khi bật:

- Mọi tool của invocation có thể nhìn thấy session ID.
- MCP servers có thể nhận session ID dưới dạng request metadata.
- Phạm vi dữ liệu được chia sẻ với tools rộng hơn.

Chỉ bật khi tool thực sự cần session ID và chính sách quyền riêng tư cho phép. Conversation ID trên trace không có nghĩa mọi tool cần nhận nó.

## 11. Arguments và kết quả tool: chỉ bật export khi có lý do

Theo tài liệu Spring AI 2.1.0, arguments và results của tool không được xuất ra span attributes mặc định vì có thể chứa thông tin nhạy cảm.

Property:

~~~yaml
spring:
  ai:
    tools:
      observations:
        include-content: false
~~~

**spring.ai.tools.observations.include-content** mặc định là **false**. Khi bật, tool call arguments và results có thể xuất hiện dưới dạng high-cardinality span attributes.

Những dữ liệu có thể nhạy cảm:

- Mã khách hàng, email, số điện thoại hoặc địa chỉ.
- Tenant ID, account ID và thông tin phân quyền.
- Dữ liệu đơn hàng, thanh toán hoặc hồ sơ hỗ trợ.
- Kết quả truy vấn database.
- Nội dung tài liệu nội bộ được tool trả về.
- Token, khóa truy cập hoặc thông tin cấu hình vô tình nằm trong arguments.

Không bật export toàn bộ arguments/results chỉ để điều tra một lỗi. Ưu tiên log có redaction, quyền truy cập giới hạn, retention ngắn và quy trình audit.

### 11.1. Prompt và completion cũng mặc định không được log

ChatClient có các property:

| Property | Default | Ý nghĩa |
|---|---|---|
| **spring.ai.chat.client.observations.log-prompt** | **false** | Có log prompt của ChatClient không |
| **spring.ai.chat.client.observations.log-completion** | **false** | Có log completion của ChatClient không |

Nội dung prompt và completion thường lớn, có thể chứa dữ liệu riêng tư. Nếu bật để debug, cần xác định dữ liệu nào được phép log, redaction ở đâu, ai có quyền xem và lưu bao lâu.

## 12. High cardinality không phải là metric dimension

Ví dụ một hệ thống có 100.000 conversations và mỗi conversation có 20 turns. Nếu gắn **conversation.id** vào metric label, chỉ riêng dimension này đã có thể tạo ra rất nhiều time series.

Không nên tạo metric kiểu:

~~~text
chat_requests_total{conversation_id="conv-7f31"}
tool_calls_total{conversation_id="conv-7f31", tool="lookupOrder"}
~~~

Thay vào đó:

- Dùng **conversation.id** trong traces để tìm một hội thoại.
- Dùng **spring.ai.tool.definition.name** để tổng hợp tool execution theo tên tool nếu danh mục hữu hạn.
- Dùng metrics low-cardinality cho tổng số call, latency và error rate.
- Lưu conversation/run/case identifiers trong trace hoặc evaluation store có kiểm soát.
- Dùng tool-set version hữu hạn nếu cần so sánh cấu hình qua metrics.

Một tool name đơn lẻ có thể có tập giá trị nhỏ, nhưng danh sách kết hợp nhiều tools trên mỗi request có thể tạo rất nhiều biến thể. Vì vậy **spring.ai.chat.client.tool.names** được phân loại high-cardinality.

### 12.1. Ví dụ bảng chọn nơi lưu dữ liệu

| Dữ liệu | Trace | Metrics | Evaluation store |
|---|---|---|---|
| Conversation ID | Có, high-cardinality | Không | Có nếu cần |
| Trace ID / span ID | Theo tracing system | Không làm label | Lưu làm correlation |
| Tool names list | Có, high-cardinality | Không dùng list làm label | Có theo run/version |
| Một tool name ổn định | Có | Có thể dùng low-cardinality | Có |
| Tool call ID | Có, high-cardinality | Không | Có nếu cần audit |
| Tool arguments/results | Mặc định không | Không | Chỉ lưu nếu có chính sách |
| Prompt version | Có thể thêm custom attribute | Chỉ khi tập version hữu hạn | Có |
| Dataset case ID | Trace khi cần điều tra | Không làm label | Có |

## 13. Liên kết conversation ID với evaluation run

Khi chạy evaluation dataset, một case có thể được thực thi nhiều lần với prompt/model/tool-set khác nhau.

Nên lưu các khóa liên kết ở tầng orchestration/report:

~~~json
{
  "runId": "run-2026-11-27-006",
  "caseId": "order-status-012",
  "conversationId": "conv-7f31",
  "traceId": "trace-91ab",
  "promptVersion": "prompt-v12",
  "modelVersion": "model-a",
  "toolSetVersion": "tools-v4",
  "judgeModel": "judge-b",
  "rubricVersion": "fact-v3",
  "executedTools": [
    {
      "name": "lookupOrder",
      "toolCallId": "call-01"
    }
  ],
  "quality": {
    "criterion": "factual-support",
    "status": "EVALUATED_PASS"
  }
}
~~~

Đây là schema do ứng dụng thiết kế, không phải JSON tự động do Spring AI xuất.

Cách liên kết:

- **conversationId**: nhóm nhiều lượt trong cùng cuộc hội thoại.
- **traceId**: mở đúng distributed trace của lượt thực thi.
- **runId**: xác định lần chạy evaluation hoặc experiment.
- **caseId**: xác định case trong dataset.
- **toolCallId**: xác định một lần model yêu cầu tool cụ thể.
- **toolSetVersion**: cho biết tập tool definitions được cấu hình ở phiên bản nào.

Không đưa tất cả các khóa này vào metrics. Hãy giữ dữ liệu chi tiết trong trace/report và dùng metrics cho thống kê tổng hợp.

### 13.1. So sánh tool set qua các phiên bản

Ví dụ hai phiên bản:

| Phiên bản | Tools được cung cấp | Tools thực thi | Factuality pass rate |
|---|---|---|---:|
| **tools-v3** | lookupOrder, getShipment | lookupOrder | 91% |
| **tools-v4** | lookupOrder, getShipment, getReturnPolicy | lookupOrder, getReturnPolicy | 95% |

Số liệu chỉ minh họa. Để giải thích pass rate tăng, mở các traces tương ứng, xác nhận model thực sự được cung cấp tool definitions nào và kết quả tool nào được dùng làm bằng chứng.

Nếu chỉ so danh sách tools đã đăng ký, bạn chưa biết model có gọi chúng hay không. Nếu chỉ so tool execution spans, bạn có thể bỏ qua tools được cung cấp nhưng không được chọn.

## 14. Khi cần custom trace attributes

Các attributes có sẵn của Spring AI bao phủ conversation ID, advisors và tool names. Ứng dụng có thể cần thêm thông tin như:

- runId
- caseId
- promptVersion
- retrieverVersion
- toolSetVersion
- judgeVersion

Không mặc định message metadata hoặc một biến Java bất kỳ sẽ tự xuất hiện trong span. Nếu cần custom attributes, dùng extension point observability phù hợp như **ChatClientObservationConvention** hoặc instrumentation tại tầng orchestration; sau đó xác minh attribute thực tế trong backend tracing.

Quy tắc thiết kế:

1. Attribute cần tập giá trị hữu hạn và có ích cho thống kê có thể cân nhắc cho metrics.
2. ID duy nhất theo từng run/case chỉ nên ở traces hoặc evaluation store.
3. Không thêm raw prompt, tool arguments hoặc user identity vào custom attributes.
4. Dùng tên/version rõ ràng để tránh nhầm model version với tool-set version.
5. Giữ cùng convention giữa môi trường test, staging và production.

## 15. Cấu hình tracing và kiểm tra observability

Spring AI dựa trên Spring Boot Actuator và Micrometer. Để xem metrics/traces, ứng dụng cần registry, tracing bridge và exporter tương ứng với backend đang sử dụng.

Ví dụ cấu hình endpoint metrics và giữ nội dung nhạy cảm tắt:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus

spring:
  ai:
    chat:
      client:
        observations:
          log-prompt: false
          log-completion: false
    tools:
      observations:
        include-content: false
~~~

Đoạn YAML trên không tự cài tracing exporter hoặc bật distributed tracing. Hãy thêm các dependency và cấu hình Micrometer Tracing phù hợp với Spring Boot/backend đang dùng.

Trong Spring Boot, ưu tiên dùng **ChatClient.Builder** đã auto-configure. Nếu tự tạo ChatClient bằng **ChatClient.create(chatModel)** hoặc **ChatClient.builder(chatModel)** mà không cấu hình lại observability, có thể bỏ qua các customizers và wiring observability của Boot. Khi có nhiều ChatModel, dùng **ChatClientBuilderConfigurer** và các convention tương ứng để giữ cấu hình.

## 16. Quy trình điều tra một tool call cụ thể

Giả sử người dùng báo “Tôi hỏi đơn A123 nhưng hệ thống trả thông tin đơn khác”.

Thực hiện theo trình tự:

1. Tìm ChatClient trace theo conversation ID hoặc trace ID đã lưu.
2. Xác nhận **spring.ai.chat.client.tool.names** để biết tools được cung cấp.
3. Mở từng ChatModel operation, kiểm tra **spring.ai.model.request.tool.names**.
4. Tìm tool execution spans và đọc **spring.ai.tool.definition.name**.
5. Dùng **spring.ai.tool.call.id** để xác định tool call cần điều tra.
6. Nếu arguments/results không được export, đối chiếu audit log hoặc execution record đã redaction.
7. Xác nhận tool nhận đúng arguments, tenant/user context và trả đúng dữ liệu.
8. Đối chiếu câu trả lời cuối với tool result và dataset expected answer.
9. Lưu kết luận vào evaluation report cùng runId, caseId và version.

Nếu ChatClient span và tool spans bị tách do giới hạn imperative tool-calling observations, hãy đối chiếu thêm trace ID, tool call ID, application correlation ID và log có kiểm soát. Không kết luận tool không chạy chỉ vì trace viewer không vẽ nó dưới ChatClient span.

## 17. Kiểm thử conversation ID và tool set

Một bộ integration test nên xác nhận cả dữ liệu được cấu hình lẫn hành vi thực tế.

| Kịch bản | Điều cần xác minh |
|---|---|
| Hai lượt dùng cùng session ID | Cùng spring.ai.chat.client.conversation.id, hai lần gọi được truy vết riêng |
| Hai session ID khác nhau | Lịch sử không bị trộn |
| Thiếu session ID | Session advisor từ chối request theo contract |
| ChatClient nhận hai tools | spring.ai.chat.client.tool.names phản ánh tools được truyền |
| Model nhận tool definitions | spring.ai.model.request.tool.names phản ánh definitions của request |
| Model chỉ gọi một tool | Chỉ có tool execution tương ứng, không suy ra mọi tool đều chạy |
| Một tool được gọi nhiều lần | Các tool call IDs phân biệt được từng lần |
| Tool content export tắt | Arguments/results không xuất hiện trong span attributes |
| Tool execution lỗi | Tool observation/log phản ánh lỗi theo instrumentation |
| Dùng MCP tools | Tên tools, provider/filter và tool execution được đối chiếu |

### 17.1. Kiểm tra hai lượt cùng conversation

Kịch bản test:

~~~text
Call 1:
  conversationId = conv-test-01
  traceId = trace-A
  tool.names = [lookupOrder]

Call 2:
  conversationId = conv-test-01
  traceId = trace-B
  tool.names = [lookupOrder, getReturnPolicy]

Expected:
  conversation.id giống nhau
  trace.id khác nhau
  tool.names phản ánh tập của từng invocation
~~~

Test này chứng minh conversation grouping và per-call trace khác nhau. Nó không yêu cầu hai lượt phải dùng cùng tập tools.

### 17.2. Kiểm tra không trộn hội thoại

Tạo hai session IDs khác nhau, gọi ChatClient xen kẽ:

~~~text
User A -> session-A -> trace-1
User B -> session-B -> trace-2
User A -> session-A -> trace-3
~~~

Kiểm tra:

- Trace 1 và trace 3 cùng conversation ID.
- Trace 2 mang conversation ID khác.
- Memory của User A không chứa message riêng của User B.
- Authorization ở tầng session/service xác nhận chủ sở hữu trước khi truy cập lịch sử.

Đây là test bảo vệ dữ liệu quan trọng hơn việc chỉ kiểm tra span attribute.

## 18. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng conversation ID làm trace ID | Gộp nhiều lượt thành một trace dài | Một conversation ID, nhiều trace IDs |
| Không truyền ID vào memory advisor | Không có đúng conversation context hoặc runtime exception | Truyền session/conversation ID ở mọi call |
| Dùng một session mặc định cho mọi người | Trộn lịch sử nhiều người dùng | Session ID riêng, kiểm tra owner/tenant |
| Đưa conversation ID vào metric label | Cardinality tăng theo số hội thoại | Chỉ dùng trong trace/evaluation store |
| Coi tool.names là danh sách tool đã chạy | Nhầm tool khả dụng với tool thực thi | Xem spring.ai.tool spans |
| Coi tool execution span là toàn bộ tool set | Bỏ sót tools đã cung cấp nhưng không được gọi | So ChatClient và ChatModel attributes |
| Coi tool.call.id là conversation ID | Nhầm một lần gọi với một cuộc hội thoại | Phân biệt ID theo phạm vi |
| Giả định mọi tool span đều là child của ChatClient | Chẩn đoán sai khi observation bị ngắt | Kiểm tra trace limitation và correlation khác |
| Bật export arguments/results toàn cục | Có thể lộ PII, secrets và dữ liệu nghiệp vụ | Mặc định tắt, redaction và giới hạn quyền |
| Cho rằng ToolContext tự xuất hiện trong prompt | Lộ dữ liệu nội bộ hoặc thiết kế sai | ToolContext là dữ liệu nội bộ của tool |
| Cho rằng message metadata tự thành trace attribute | Không tìm được thuộc tính trong backend | Dùng built-in attributes/custom convention |
| Chỉ lưu trace ID, không lưu run/case ID | Khó đối chiếu evaluation dataset | Lưu correlation trong report store |
| Tìm lỗi chỉ bằng aggregate metrics | Không xác định được tool call cụ thể | Drill down theo trace và tool call ID |

## 19. Bài tập tự kiểm tra

### Bài 1 — Một conversation, ba traces

Một người dùng có ba lượt hỏi, mỗi lượt gọi ChatClient một lần. Conversation ID có cần thay đổi sau mỗi lượt không?

**Đáp án:** Không. Nếu vẫn cùng một session, conversation ID giữ nguyên; mỗi lượt có trace ID riêng để điều tra từng lần thực thi.

### Bài 2 — Tool names không có nghĩa tool đã chạy

ChatClient span ghi [lookupOrder, getShipment], nhưng chỉ có một spring.ai.tool span mang tên lookupOrder. Có phải thiếu trace của getShipment?

**Đáp án:** Chưa có cơ sở kết luận. Danh sách ChatClient mô tả tools được cung cấp; tool span mô tả tool thực thi. Model có thể không chọn getShipment.

### Bài 3 — Vì sao model request tool names khác ChatClient tool names?

ChatClient có ba tool names nhưng model request chỉ có hai definitions. Có thể do đâu?

**Đáp án:** Kiểm tra advisor thay đổi tool set, tool filters, progressive tool disclosure hoặc cơ chế cung cấp tools động. Hai attributes thuộc hai ranh giới khác nhau.

### Bài 4 — Có nên dùng conversation ID làm metric tag?

Một hệ thống có hàng triệu conversations. Có nên tạo counter với label conversation ID?

**Đáp án:** Không. Conversation ID là high-cardinality và chỉ nên xuất trong traces theo quy ước Spring AI. Metrics nên tổng hợp theo các chiều hữu hạn.

### Bài 5 — Tool arguments không thấy trong trace

Một tool span có tên tool và call ID nhưng không có arguments/result. Có thể do đâu?

**Đáp án:** spring.ai.tools.observations.include-content mặc định false. Arguments/results không được xuất mặc định vì lý do nhạy cảm.

### Bài 6 — Session ID có tự tới tool không?

ChatClient trace có conversation ID. Tool method không nhận được session ID. Đây có phải lỗi tracing?

**Đáp án:** Không. Trace attribute và ToolContext là hai cơ chế khác nhau. Muốn tool nhận session ID phải truyền context theo API/cấu hình phù hợp; sessionIdInToolContext(true) là lựa chọn riêng và mặc định tắt.

### Bài 7 — Tool span không nằm dưới ChatClient span

Trace viewer cho thấy tool observation không được nối dưới ChatClient span. Có thể kết luận tool không chạy?

**Đáp án:** Không. Spring AI 2.1.0 có giới hạn partial/interrupted observations với imperative tool calling. Kiểm tra tool observation, trace IDs, call IDs và log correlation.

### Bài 8 — Liên kết evaluation case

Một case dataset được chạy với hai prompt versions và hai tool sets. Cần giữ những khóa nào để so sánh?

**Đáp án:** Ít nhất caseId, runId, conversationId nếu dùng session, traceId, prompt version, model version, tool-set version và rubric/judge version. Lưu các khóa chi tiết trong report store, không làm metric labels duy nhất.

## 20. Checklist triển khai

- [ ] Đã phân biệt conversation ID, trace ID, span ID, tool call ID, run ID và case ID?
- [ ] Có session/conversation ID ổn định cho mỗi cuộc hội thoại?
- [ ] Backend xác thực quyền sở hữu session và tenant trước khi dùng ID?
- [ ] Memory/session advisor nhận ID ở mọi ChatClient call?
- [ ] Đã kiểm tra spring.ai.chat.client.conversation.id trong trace?
- [ ] Đã kiểm tra spring.ai.chat.client.tool.names phản ánh tập tools truyền vào?
- [ ] Đã so với spring.ai.model.request.tool.names ở từng model request?
- [ ] Đã phân biệt tools được cung cấp với tools thực sự có spring.ai.tool execution span?
- [ ] Có dùng spring.ai.tool.call.id để phân biệt từng tool invocation?
- [ ] Không dùng conversation ID hoặc tool-name list làm metric labels?
- [ ] spring.ai.tools.observations.include-content giữ tắt nếu không có nhu cầu được kiểm soát?
- [ ] Prompt/completion logging mặc định tắt hoặc có redaction và retention?
- [ ] Không giả định conversation ID tự được chuyển vào ToolContext?
- [ ] Đã kiểm tra giới hạn trace nesting của imperative tool calling?
- [ ] Có run ID/case ID để liên kết trace với dataset evaluation?
- [ ] Có integration test cho nhiều turns, nhiều tool calls và session isolation?

## 21. Tổng kết và tài liệu tham khảo

Spring AI cung cấp hai attributes quan trọng ở ChatClient trace: **spring.ai.chat.client.conversation.id** và **spring.ai.chat.client.tool.names**. Chúng cho biết một invocation thuộc cuộc hội thoại nào và được cung cấp tập tools nào. ChatModel trace có **spring.ai.model.request.tool.names** để thể hiện tool definitions được gửi cho model; tool execution observation **spring.ai.tool** ghi tên tool và call ID của từng lần thực thi.

Hãy dùng conversation ID để nhóm nhiều lượt, trace ID để điều tra một lần xử lý, và tool call ID để phân biệt từng lần gọi công cụ. Đưa high-cardinality identifiers vào traces/report có kiểm soát; giữ metrics ở các chiều hữu hạn. Khi trace tool calling bị ngắt, đối chiếu thêm tool observations và correlation data thay vì kết luận từ một cây span chưa đầy đủ.

**Tài liệu chính thức:**

1. [Spring AI 2.1.0 — Observability](https://docs.spring.io/spring-ai/reference/observability/): ChatClient conversation ID, tool names, model request tool names, tool observation attributes và cấu hình include-content.
2. [Spring AI 2.1.0 — ChatClient API](https://docs.spring.io/spring-ai/reference/api/chatclient.html): truyền advisors, tools, auto-configuration, memory ID và implementation notes về tool calling.
3. [Spring AI 2.1.0 — Session Memory](https://docs.spring.io/spring-ai/reference/api/session.html): session, SessionService, repository và cách lưu lịch sử.
4. [Spring AI 2.1.0 — ChatClient Integration](https://docs.spring.io/spring-ai/reference/api/session/chat-client.html): SessionAdvisors, session ID context key, memory advisor và tool context.
5. [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html): tool definitions, tool context, tool execution, arguments/results và tracing.
6. [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): registry, tracing bridge, exporter và sampling.

*Các sơ đồ trace, run records và test scenarios trong bài là ví dụ giảng dạy. Cấu trúc span thực tế phụ thuộc Spring AI, provider, tracing bridge và cách tool được thực thi. Hãy kiểm tra trace thật trên release đang chạy, bảo vệ conversation IDs và tool data, rồi mới dùng dữ liệu đó để kết luận về chất lượng hoặc chi phí.*
