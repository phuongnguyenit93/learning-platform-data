# Khi nào ứng dụng cần kiểm soát từng vòng thực thi

Trong Spring AI 2.x, **ChatClient** thường là lựa chọn phù hợp nhất vì **ToolCallingAdvisor** tự điều phối vòng gọi mô hình, thực thi tool và gửi kết quả trở lại mô hình cho đến khi có câu trả lời cuối. Ứng dụng chỉ cần cung cấp tool và xử lý kết quả của yêu cầu chat.

Ứng dụng nên tự điều phối từng vòng khi vòng tool calling là một phần của workflow do chính ứng dụng sở hữu: mỗi vòng cần checkpoint, định tuyến, kiểm tra ngân sách, chờ hệ thống bên ngoài, lưu trạng thái để tiếp tục sau khi khởi động lại hoặc áp dụng quy tắc chuyển bước riêng. Spring AI cung cấp API mức thấp **ChatModel** và **ToolCallingManager** cho cách làm này.

Trước khi tự viết vòng lặp, hãy xác định đúng nhu cầu. Duyệt thao tác nhạy cảm, quan sát tiến độ, giới hạn số lần gọi và trả kết quả tool trực tiếp đều đã có cơ chế tích hợp; các nhu cầu đó không mặc nhiên đòi hỏi ứng dụng tự quản lý toàn bộ vòng lặp.

## 1. Một lượt tool calling gồm những gì?

Một lượt hội thoại có thể gồm nhiều vòng. Trong mỗi vòng, mô hình có thể trả lời trực tiếp hoặc yêu cầu gọi một hay nhiều tool:

1. Ứng dụng gửi prompt cùng tool definition cho mô hình.
2. Mô hình trả về câu trả lời cuối hoặc một danh sách tool call.
3. Nếu có tool call, ứng dụng tìm và thực thi callback tương ứng.
4. Ứng dụng thêm yêu cầu gọi tool và kết quả thực thi vào lịch sử hội thoại.
5. Ứng dụng gửi lịch sử đã cập nhật cho mô hình để mô hình quyết định bước tiếp theo.
6. Quá trình lặp lại cho đến khi mô hình không còn yêu cầu tool hoặc ứng dụng chủ động dừng.

~~~mermaid
flowchart TD
    A[Ứng dụng tạo prompt và tool set] --> B[Gọi mô hình]
    B --> C{Response có tool call?}
    C -->|Không| D[Trả câu trả lời cuối]
    C -->|Có| E[Kiểm tra điều kiện và ngân sách]
    E --> F{Cho phép vòng tiếp theo?}
    F -->|Không| G[Dừng hoặc chuyển sang xử lý lỗi]
    F -->|Có| H[ToolCallingManager thực thi callback]
    H --> I[Nhận tool result và conversation history]
    I --> J{returnDirect?}
    J -->|Có| K[Trả kết quả tool trực tiếp]
    J -->|Không| L[Tạo prompt từ lịch sử mới]
    L --> B
~~~

Một tool call là yêu cầu do mô hình tạo ra, chưa phải thao tác đã thực thi. Ứng dụng quyết định callback nào được cung cấp và **ToolCallingManager** thực hiện các callback được yêu cầu trong response. Mô hình không tự chạy mã Java hoặc truy cập database.

## 2. Ba mức điều phối trong Spring AI

Spring AI cho phép chọn mức kiểm soát theo nhu cầu:

| Mức | Thành phần | Ứng dụng chịu trách nhiệm |
| --- | --- | --- |
| Framework điều phối | **ChatClient** + **ToolCallingAdvisor** | Cung cấp tool, prompt và xử lý câu trả lời cuối |
| Advisor mở rộng | **ToolCallingAdvisor** + advisor tùy chỉnh | Bổ sung hook, quan sát, kiểm tra điều kiện hoặc thay đổi chính sách của vòng lặp |
| Ứng dụng tự điều phối | **ChatModel** + **ToolCallingManager**, hoặc **ChatClient** tắt auto advisor | Tự quyết định khi gọi mô hình, khi thực thi tool, cách lưu lịch sử và khi dừng |

**ToolCallingAdvisor** được **DefaultChatClient** tự đăng ký trong Spring AI 2.x. Advisor gọi mô hình, chuyển tool call đến **ToolCallingManager**, nối tool result vào lịch sử và lặp lại. Đây là lựa chọn mặc định cho chat, RAG và assistant thông thường.

Khi dùng **ChatModel** trực tiếp trong Spring AI 2.x, **chatModel.call(prompt)** chỉ gửi request và trả response. Nếu response có tool call, **ChatModel** không tự thực thi callback. Ứng dụng cần gọi **ToolCallingManager.executeToolCalls(...)** rồi gửi lịch sử mới cho mô hình.

Trong Spring AI 1.x, mỗi implementation **ChatModel** từng có vòng thực thi tool nội bộ. Vòng lặp đó đã được loại bỏ từ 2.0. Khi nâng cấp từ 1.x, không nên giả định rằng gọi **ChatModel** với tool options sẽ tự chạy tool như trước.

## 3. Khi nào nên tự kiểm soát từng vòng?

Tự điều phối hữu ích khi ứng dụng có một workflow cụ thể và cần quyết định sau mỗi response của mô hình:

- **Workflow nhiều hệ thống:** sau một tool call, ứng dụng cần gọi hệ thống khác, chờ sự kiện hoặc chuyển sang một service chuyên trách trước khi hỏi mô hình tiếp.
- **Checkpoint và khôi phục:** cần lưu trạng thái từng vòng để tiếp tục sau timeout, worker restart hoặc yêu cầu xử lý kéo dài.
- **Ngân sách theo phiên:** cần dừng dựa trên token, chi phí, thời gian, số vòng mô hình hoặc hạn mức nghiệp vụ của một phiên làm việc.
- **Điều phối theo trạng thái:** kết quả tool quyết định bước tiếp theo, chẳng hạn chuyển từ tra cứu sang kiểm tra điều kiện, yêu cầu duyệt hoặc kết thúc quy trình.
- **Tích hợp agent/workflow framework khác:** một bộ điều phối bên ngoài đã sở hữu vòng lặp, lịch chạy và cơ chế phục hồi.
- **Chính sách thực thi riêng:** cần ghi lại quyết định, áp dụng retry có điều kiện hoặc chuyển lỗi đến một nhánh xử lý riêng sau mỗi vòng.

Ví dụ, quy trình xử lý yêu cầu hoàn tiền có thể gồm tra cứu đơn hàng, xác minh trạng thái giao hàng, kiểm tra hạn mức, chờ phê duyệt và sau cùng mới gọi tool hoàn tiền. Ứng dụng cần kiểm soát thứ tự và lưu trạng thái của quy trình. Mô hình có thể đề xuất bước tiếp theo, nhưng workflow service quyết định bước nào được phép chạy.

Không nên tự điều phối chỉ vì muốn:

| Nhu cầu | Cơ chế thường phù hợp |
| --- | --- |
| Thực thi tool và trả lời bình thường | **ChatClient** mặc định |
| Ghi nhận sự kiện hoặc metrics của từng vòng | Custom advisor đặt bên trong **ToolCallingAdvisor** |
| Hiển thị tiến độ stream cho giao diện | Custom **StreamAdvisor** hoặc advisor quan sát |
| Yêu cầu con người duyệt thao tác nhạy cảm | Tool Call Confirmation trong Spring AI 2.1 |
| Giới hạn số lần gọi tool | **ToolCallingManager** limits |
| Tool có kết quả chính là câu trả lời cuối | **returnDirect** |
| Chọn điều kiện nào được xem là tool-call response | **ToolExecutionEligibilityChecker** |

Tự viết vòng lặp làm ứng dụng phải chịu trách nhiệm về lịch sử hội thoại, dừng vòng, xử lý lỗi, timeout và tính nhất quán. Chỉ chọn mức này khi các trách nhiệm đó thuộc về workflow của ứng dụng.

## 4. Ví dụ điều phối thủ công bằng ChatModel

Giả sử assistant cần tra cứu thời tiết ở nhiều thành phố. Mô hình có thể gọi tool một lần hoặc nhiều lần; sau mỗi lần thực thi, ứng dụng gửi kết quả trở lại để mô hình tổng hợp câu trả lời.

### Khai báo tool

~~~java
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;

public class WeatherTools {

    private final WeatherService weatherService;

    public WeatherTools(WeatherService weatherService) {
        this.weatherService = weatherService;
    }

    @Tool(
        name = "current_weather",
        description = "Tra cứu thời tiết hiện tại theo tên thành phố."
    )
    public WeatherResult currentWeather(
            @ToolParam(description = "Tên thành phố cần tra cứu") String city) {
        return weatherService.currentWeather(city);
    }
}
~~~

**WeatherService** và **WeatherResult** là các kiểu nghiệp vụ do ứng dụng định nghĩa. Phương thức tool chỉ gọi service; việc xác thực, giới hạn truy vấn và xử lý lỗi cần được thực hiện ở lớp nghiệp vụ.

### Viết vòng lặp

Đoạn mã sau minh họa vòng lặp blocking với **ChatModel**. **ToolCallingManager** có thể được inject từ Spring Boot auto-configuration. Nếu không dùng Spring Boot, có thể tạo bằng **ToolCallingManager.builder().build()**.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.model.tool.ToolCallingChatOptions;
import org.springframework.ai.model.tool.ToolCallingManager;
import org.springframework.ai.model.tool.ToolExecutionResult;
import org.springframework.ai.support.ToolCallbacks;
import org.springframework.ai.tool.ToolCallback;

public class WeatherOrchestrator {

    private static final int MAX_TOOL_ROUNDS = 6;

    private final ChatModel chatModel;
    private final ToolCallingManager toolCallingManager;
    private final ToolCallback[] tools;

    public WeatherOrchestrator(
            ChatModel chatModel,
            ToolCallingManager toolCallingManager,
            WeatherService weatherService) {
        this.chatModel = chatModel;
        this.toolCallingManager = toolCallingManager;
        this.tools = ToolCallbacks.from(new WeatherTools(weatherService));
    }

    public List<Message> answer(String question) {
        var options = ToolCallingChatOptions.builder()
            .toolCallbacks(tools)
            .build();

        Prompt prompt = new Prompt(new UserMessage(question), options);
        ChatResponse response = chatModel.call(prompt);

        int toolRounds = 0;

        while (response.hasToolCalls()) {
            if (toolRounds >= MAX_TOOL_ROUNDS) {
                throw new IllegalStateException(
                    "Đã vượt quá số vòng gọi tool cho phép."
                );
            }
            toolRounds++;

            ToolExecutionResult execution =
                toolCallingManager.executeToolCalls(prompt, response);

            if (execution.returnDirect()) {
                // Tool result là kết quả cuối; không gọi mô hình thêm.
                return execution.conversationHistory();
            }

            prompt = new Prompt(execution.conversationHistory(), options);
            response = chatModel.call(prompt);
        }

        List<Message> finalHistory =
            new ArrayList<>(prompt.getInstructions());
        finalHistory.add(response.getResult().getOutput());
        return List.copyOf(finalHistory);
    }
}
~~~

Trong ví dụ, **ToolCallbacks.from(...)** chuyển đối tượng có phương thức **@Tool** thành callback. **ToolCallingChatOptions** đưa callback vào request. **chatModel.call(...)** gửi prompt đến mô hình và trả **ChatResponse**.

Khi response có tool call, **executeToolCalls(prompt, response)** thực thi các callback được yêu cầu và trả về **ToolExecutionResult**. **conversationHistory()** chứa lịch sử trước đó, yêu cầu gọi tool của assistant và các tool response. Ứng dụng dùng danh sách này làm messages của prompt kế tiếp.

Một response có thể chứa nhiều tool call. Một lần gọi **executeToolCalls(...)** giao cả nhóm call của response cho manager xử lý; vòng lặp thủ công cho ứng dụng quyền kiểm soát giữa các vòng mô hình. Nếu cần phê duyệt từng call, hãy cấu hình confirmation policy; trong Spring AI 2.1, nếu một call trong batch cần duyệt thì toàn bộ batch đó được tạm dừng trước khi có call nào chạy.

Khi response không còn tool call, mô hình đã tạo câu trả lời cuối. Ví dụ trả về danh sách message để tầng gọi có thể lưu transcript hoặc định dạng nội dung. Nếu tool có **returnDirect = true** và tất cả tool trong vòng đó đều đặt cờ này, **ToolExecutionResult.returnDirect()** là **true**; ứng dụng trả kết quả tool trực tiếp và bỏ qua lần gọi mô hình tiếp theo.

## 5. Giới hạn vòng lặp và ngân sách

Một vòng lặp thủ công phải có điều kiện dừng hữu hạn. Nếu mô hình liên tục yêu cầu tool, ứng dụng có thể tốn chi phí, giữ tài nguyên quá lâu hoặc lặp lại thao tác.

Nên kiểm soát ít nhất:

- Số vòng gọi mô hình tối đa trong một lượt.
- Số lần gọi cho từng tool.
- Tổng số tool call trong một lượt.
- Deadline tổng thể và timeout riêng cho mỗi lần gọi mô hình hoặc service.
- Ngân sách token hoặc chi phí nếu workflow cần giới hạn theo phiên.
- Số lần retry và điều kiện retry.

**DefaultToolCallingManager** đã có giới hạn số lần gọi theo tool và tổng số tool call. Có thể cấu hình bằng builder:

~~~java
import org.springframework.ai.model.tool.ToolCallingManager;

ToolCallingManager manager = ToolCallingManager.builder()
    .maxCallsPerTool(5)
    .maxCallsPerTool("current_weather", 3)
    .maxTotalToolCalls(12)
    .build();
~~~

Hoặc cấu hình qua Spring Boot properties:

~~~properties
spring.ai.tools.limits.max-calls-per-tool-default=5
spring.ai.tools.limits.max-calls-per-tool.current_weather=3
spring.ai.tools.limits.max-total-tool-calls=12
spring.ai.tools.limits.on-limit-exceeded=THROW
~~~

Các giới hạn của manager đếm tool call trong lượt hiện tại. Chúng không thay thế giới hạn số vòng gọi mô hình do workflow đặt ra, cũng không thay thế timeout và ngân sách token. Nếu ứng dụng cần ngân sách tổng thể, hãy theo dõi chúng ở lớp orchestrator.

Khi đạt giới hạn, chọn một hành vi rõ ràng: dừng với lỗi có thể quan sát, trả trạng thái cần can thiệp hoặc chuyển sang nhánh xử lý thay thế. Không tự động retry vô hạn.

## 6. Khi cần duyệt thao tác, hãy cân nhắc Tool Call Confirmation

Spring AI 2.1 có cơ chế xác nhận tool call. Có thể đánh dấu phương thức cần người duyệt:

~~~java
@Tool(
    description = "Hoàn tiền cho đơn hàng.",
    requiresConfirmation = true
)
public RefundResult refundOrder(
        @ToolParam(description = "Mã đơn hàng") String orderId) {
    return refundService.refund(orderId);
}
~~~

**ToolCallingManager** kiểm tra chính sách xác nhận trước khi thực thi. Nếu một tool call cần duyệt, cả batch tool call trong response đó được tạm dừng; ứng dụng nhận response cùng thông tin những call đang chờ quyết định. Sau khi người có quyền cho phép hoặc từ chối, ứng dụng gọi **executeToolCalls(prompt, reply, decisions)** và gửi tool result trở lại mô hình.

Có thể cấu hình chính sách theo metadata hoặc tên tool:

~~~java
import org.springframework.ai.model.tool.ToolCallConfirmationPolicy;
import org.springframework.ai.model.tool.ToolCallingManager;

ToolCallingManager manager = ToolCallingManager.builder()
    .toolCallConfirmationPolicy(
        ToolCallConfirmationPolicy.fromToolMetadata()
            .or(ToolCallConfirmationPolicy.forTools("delete_customer"))
    )
    .build();
~~~

Confirmation phù hợp khi nhu cầu là dừng trước hành động nhạy cảm để con người quyết định. Ứng dụng vẫn phải xác thực người duyệt, lưu quyết định, chống replay và bảo vệ tool call đang chờ trong kho dữ liệu do server kiểm soát. Không nhận nguyên **ChatResponse** đang chờ duyệt từ client rồi gửi lại manager mà không kiểm tra nguồn dữ liệu.

Tự điều phối vẫn cần thiết nếu sau khi duyệt, workflow còn phải chạy các bước khác, lưu checkpoint hoặc phối hợp với hệ thống ngoài. Confirmation xử lý điểm dừng phê duyệt; nó không thay thế toàn bộ workflow engine.

## 7. Giữ ChatClient nhưng tự thực thi tool

Không nhất thiết phải bỏ **ChatClient** để tự kiểm soát vòng. Nếu muốn giữ advisor chain khác nhưng tự thực thi tool, có thể tắt auto-registration của **ToolCallingAdvisor** cho một request:

Giả sử **weatherTools** là đối tượng tool đã được inject vào service:

~~~java
ChatClientResponse response = chatClient.prompt()
    .user(question)
    .tools(weatherTools)
    .advisors(AdvisorParams.toolCallingAdvisorAutoRegister(false))
    .call()
    .chatClientResponse();
~~~

Khi tắt auto-registration, tool definition vẫn được gửi đến mô hình nhưng tool call trong response không tự động được thực thi. Ứng dụng kiểm tra **response.chatResponse().hasToolCalls()**, gọi **ToolCallingManager.executeToolCalls(...)**, rồi gửi **conversationHistory()** vào request tiếp theo. Mỗi request tiếp tục tắt auto-registration để tránh advisor tự chạy vòng lặp.

Có thể tắt auto-registration cho toàn bộ **ChatClient** auto-configured bằng:

~~~properties
spring.ai.chat.client.tool-calling.enabled=false
~~~

Chỉ nên dùng cấu hình toàn cục khi ứng dụng thật sự muốn tự quản lý mọi lượt gọi. Nếu chỉ một workflow cần quyền kiểm soát đặc biệt, hãy tắt theo từng request để những request khác vẫn dùng cơ chế mặc định.

## 8. Quan sát từng vòng mà không tự viết vòng lặp

Một lý do thường gặp để muốn tự điều phối là cần gửi tiến độ tới UI, ghi audit log hoặc đo thời gian của từng vòng. Với những nhu cầu quan sát này, có thể đặt custom advisor bên trong **ToolCallingAdvisor**.

Mặc định **ToolCallingAdvisor.DEFAULT_ORDER** là **Ordered.HIGHEST_PRECEDENCE + 300**. Advisor có order lớn hơn sẽ chạy bên trong vòng tool calling và được gọi lại ở mỗi vòng. Ví dụ, một advisor order **HIGHEST_PRECEDENCE + 400** có thể quan sát request/response của từng vòng rồi phát sự kiện sang SSE hoặc WebSocket.

**ToolCallingAdvisor** cũng có hook và **ToolExecutionEligibilityChecker** để tùy chỉnh điều kiện một response có được xem là tool-call response hay không. Hãy dùng extension point này khi cần tùy chỉnh hành vi của advisor nhưng vẫn muốn framework giữ trách nhiệm lặp và quản lý lịch sử.

Tự viết vòng lặp chỉ để ghi log thường làm tăng mã điều phối và trách nhiệm phục hồi mà không đem lại quyền kiểm soát cần thiết.

## 9. Điều phối streaming

Với **ChatModel.stream(prompt)**, mỗi vòng trả về nhiều chunk. Ứng dụng phải tổng hợp chunk của một vòng trước khi kiểm tra response cuối có tool call hay không. Không thực thi tool từ một mảnh JSON arguments chưa hoàn chỉnh.

Mẫu xử lý:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.ai.chat.model.MessageAggregator;

AtomicReference<ChatResponse> aggregated = new AtomicReference<>();

new MessageAggregator().aggregate(
    chatModel.stream(prompt)
        .doOnNext(chunk -> forwardToClient(chunk)),
    aggregated::set
).collectList().block();

ChatResponse response = aggregated.get();
if (response.hasToolCalls()) {
    ToolExecutionResult result =
        toolCallingManager.executeToolCalls(prompt, response);
    prompt = new Prompt(result.conversationHistory(), options);
}
~~~

Đoạn mã trên thể hiện một vòng streaming; đặt nó trong vòng điều phối có giới hạn để xử lý các vòng tiếp theo. Trong ứng dụng reactive, tránh chặn thread event loop bằng **.block()**; chọn cách subscribe/compose phù hợp với runtime và quản lý cancellation, backpressure cũng như deadline.

Nếu chỉ muốn stream tiến độ của vòng tool calling mà vẫn giữ **ChatClient**, hãy dùng custom **StreamAdvisor** bên trong **ToolCallingAdvisor**. Tài liệu Spring AI có mẫu dùng **ChatClientMessageAggregator** để tổng hợp từng vòng và phát chunk ra ngoài khi ứng dụng thật sự cần user-controlled streaming.

## 10. Quản lý lịch sử, context và tính nhất quán

Mỗi vòng tiếp theo phải nhận đủ ngữ cảnh cần thiết:

- User message ban đầu.
- Các assistant message chứa tool call.
- Tool response tương ứng với từng tool call.
- Những thông tin hệ thống hoặc ngữ cảnh nghiệp vụ cần duy trì.

**ToolExecutionResult.conversationHistory()** giúp xây dựng lịch sử tiếp theo mà không phải tự ghép thủ công từng tool response. Nếu tự quản lý transcript, phải giữ đúng thứ tự và liên kết tool call với tool response theo ID.

**ToolContext** dành cho dữ liệu không gửi cho mô hình, như tenant ID hoặc user ID. Khi dùng **ChatModel**, truyền context qua **ToolCallingChatOptions.toolContext(...)**. Lấy giá trị từ security context hoặc phiên đã xác thực; không để mô hình tự quyết định tenant hoặc quyền truy cập.

~~~java
import java.util.Map;

var options = ToolCallingChatOptions.builder()
    .toolCallbacks(tools)
    .toolContext(Map.of("tenantId", authenticatedTenantId))
    .build();
~~~

Trong ví dụ, **authenticatedTenantId** phải đến từ phiên đã xác thực của ứng dụng. Tool đọc giá trị đó qua tham số **ToolContext**; trường tenant không xuất hiện trong schema đầu vào của mô hình.

Với workflow kéo dài, nên lưu checkpoint gồm:

- ID hội thoại hoặc workflow.
- Prompt/history đã được xác thực và phiên bản schema.
- Số vòng, số lần gọi tool và ngân sách còn lại.
- Trạng thái từng bước nghiệp vụ.
- Kết quả tool đã hoàn tất và ID giao dịch liên quan.
- Trạng thái chờ duyệt hoặc chờ hệ thống ngoài.

Lưu trạng thái ở nơi ứng dụng kiểm soát và bảo vệ dữ liệu. Không dùng một biến field mutable trên singleton bean để giữ history của nhiều request đồng thời.

## 11. Retry, timeout và thao tác lặp

Khi tool gọi dịch vụ bên ngoài, có thể xảy ra timeout sau khi dịch vụ đã thực hiện thao tác nhưng trước khi ứng dụng nhận được kết quả. Nếu retry mù quáng, thao tác có thể bị thực hiện hai lần.

Đối với thao tác ghi:

- Dùng idempotency key hoặc transaction ID do ứng dụng quản lý.
- Kiểm tra trạng thái trước khi retry.
- Phân biệt lỗi chắc chắn chưa thực thi với lỗi không rõ kết quả.
- Ghi nhận kết quả từng tool call để workflow có thể phục hồi.
- Yêu cầu xác nhận hoặc phê duyệt trước các thao tác có tác động lớn.

Không yêu cầu mô hình lặp lại một tool call chỉ vì request trước bị timeout. Trước tiên cần xác định callback đã thực hiện nghiệp vụ hay chưa.

## 12. Ma trận kiểm thử

Kiểm thử vòng điều phối cần bao gồm cả đường kết thúc bình thường và các tình huống dừng:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Response không có tool call | Trả câu trả lời cuối, không gọi manager |
| Một tool call | Callback chạy đúng một lần, lịch sử có tool response |
| Nhiều tool call trong một vòng | Mọi kết quả được gắn đúng tool call |
| Nhiều vòng liên tiếp | Mỗi vòng dùng history của vòng trước |
| Tool có **returnDirect** | Không gọi mô hình thêm khi tất cả tool trong vòng đều return direct |
| Vượt số vòng tối đa | Orchestrator dừng theo chính sách |
| Vượt tool-call limit | Manager trả lỗi hoặc error response theo cấu hình |
| Tool timeout | Workflow áp dụng timeout/retry và không làm mất trạng thái |
| Người dùng từ chối xác nhận | Tool không chạy và quyết định được lưu |
| Request bị hủy | Không tiếp tục gọi mô hình hoặc tool sau khi cancellation có hiệu lực |
| Hai request đồng thời | Không trộn lẫn history hoặc ToolContext |
| Tool result không hợp lệ | Ứng dụng xử lý lỗi và không gửi dữ liệu nhạy cảm vào hội thoại |

Nên mock **ChatModel** để tạo chuỗi response xác định: response đầu yêu cầu tool A, response thứ hai yêu cầu tool B, response cuối không có tool call. Dùng spy hoặc mock callback để xác minh số lần thực thi và thứ tự. Các test này kiểm tra logic điều phối mà không phụ thuộc vào biến động của mô hình thật.

## 13. Checklist lựa chọn kiến trúc

Trước khi tự viết vòng lặp, hãy trả lời:

- Ứng dụng có thực sự cần quyết định sau mỗi response của mô hình không?
- **ToolCallingAdvisor** và custom advisor có đáp ứng được yêu cầu không?
- Tool Call Confirmation có xử lý được điểm dừng phê duyệt không?
- Giới hạn tool call có thể cấu hình ngay trong **ToolCallingManager** không?
- Workflow có cần checkpoint, resume, routing hoặc ngân sách riêng không?
- Ai sở hữu lịch sử hội thoại và trạng thái chờ?
- Có giới hạn số vòng, timeout, cancellation và retry không?
- Các thao tác ghi có idempotency và authorization không?
- Có kiểm thử cho tool call nhiều vòng, lỗi và request đồng thời không?

Nếu phần lớn yêu cầu chỉ là thực thi tool thông thường, hãy để **ChatClient** quản lý vòng lặp. Nếu ứng dụng đã có workflow engine hoặc cần sở hữu rõ ràng từng bước, dùng **ChatModel** và **ToolCallingManager** để tự điều phối.

## Bài thực hành

Xây dựng workflow kiểm tra điều kiện hoàn tiền cho một đơn hàng. Mô hình có thể yêu cầu:

1. Tra cứu trạng thái đơn hàng.
2. Tra cứu trạng thái giao hàng.
3. Kiểm tra chính sách hoàn tiền.
4. Đề xuất hoàn tiền hoặc giải thích lý do không đủ điều kiện.

Ứng dụng phải quyết định thứ tự bước, dừng khi thiếu dữ liệu, giới hạn tối đa năm vòng gọi mô hình, lưu checkpoint sau mỗi tool result và yêu cầu người có quyền xác nhận trước khi thực hiện hoàn tiền.

Hãy triển khai hai phiên bản:

- Phiên bản dùng **ChatClient** và **ToolCallingAdvisor** mặc định, với **requiresConfirmation** cho tool hoàn tiền.
- Phiên bản dùng **ChatModel** và **ToolCallingManager** để workflow service tự kiểm soát vòng, checkpoint và điều kiện chuyển bước.

So sánh số thành phần ứng dụng phải quản lý, khả năng khôi phục sau lỗi và mức độ kiểm soát. Chọn phiên bản đáp ứng được yêu cầu nghiệp vụ với ít trách nhiệm vận hành hơn.

## Ghi nhớ

**ChatClient** cùng **ToolCallingAdvisor** là lựa chọn mặc định cho phần lớn ứng dụng vì framework tự quản lý vòng gọi mô hình và thực thi tool. Tự điều phối bằng **ChatModel** và **ToolCallingManager** khi vòng lặp thuộc về một workflow hoặc orchestrator riêng cần checkpoint, routing, ngân sách, phục hồi hoặc điều kiện dừng đặc thù. Với nhu cầu quan sát, duyệt thao tác và giới hạn số lần gọi, hãy cân nhắc custom advisor, Tool Call Confirmation và manager limits trước khi tự viết toàn bộ vòng lặp.

## Tài liệu tham khảo

- [Spring AI 2.1 — ChatModel Tool Calling](https://docs.spring.io/spring-ai/reference/2.1/api/tools/chatmodel-tool-calling.html)
- [Spring AI 2.1 — ToolCallingAdvisor](https://docs.spring.io/spring-ai/reference/2.1/api/tools/tool-calling-advisor.html)
- [Spring AI — Tool Call Confirmation](https://docs.spring.io/spring-ai/reference/api/tools/tool-call-confirmation.html)
- [Spring AI — Tool Specification Reference](https://docs.spring.io/spring-ai/reference/2.1/api/tools/reference.html)
