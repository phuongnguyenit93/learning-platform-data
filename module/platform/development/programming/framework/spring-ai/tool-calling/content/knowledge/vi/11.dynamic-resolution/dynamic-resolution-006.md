# Đánh giá cơ chế resolution fallback theo phiên bản

Trong Spring AI, **ToolCallbackResolver** tìm một callback theo tên tool mà mô hình gửi về. Cơ chế này hỗ trợ đăng ký công cụ động, nhưng hành vi phân giải đã thay đổi đáng kể giữa Spring AI 1.x và 2.x. Đặc biệt, từ **2.0.1**, fallback tới resolver cho một tool không được gắn vào request đã bị tắt theo mặc định.

Khi nâng cấp, cần phân biệt ba việc:

1. **Định nghĩa và đăng ký tool:** công cụ được tạo từ **@Tool**, **FunctionToolCallback**, **MethodToolCallback** hay một **ToolCallback** tùy chỉnh.
2. **Phân giải tên:** **ToolCallbackResolver** ánh xạ tên do mô hình gửi thành callback có thể thực thi.
3. **Resolution fallback:** khi tên tool không nằm trong tập callback đã gắn vào request, **ToolCallingManager** có được phép tìm callback đó qua resolver hay không.

Ba cơ chế này liên quan nhưng không đồng nghĩa. Một **ToolCallback** bean có thể được resolver biết đến mà vẫn không được phép thực thi trong một request nếu fallback đang tắt.

## 1. ToolCallbackResolver làm nhiệm vụ gì?

**ToolCallbackResolver** là một interface có nhiệm vụ tìm **ToolCallback** tương ứng với tên tool:

~~~java
public interface ToolCallbackResolver {

    ToolCallback resolve(String toolName);
}
~~~

Phương thức **resolve(...)** nhận tên tool và trả về callback nếu tìm thấy; nếu không có callback phù hợp, nó có thể trả về **null**. Resolver chỉ thực hiện việc tìm callback. **ToolCallingManager** mới là thành phần điều phối và gọi callback để thực thi.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Model as Mô hình
    participant Manager as ToolCallingManager
    participant Resolver as ToolCallbackResolver
    participant Callback as ToolCallback

    App->>Model: Prompt + tool definitions được cung cấp
    Model-->>Manager: Tool call chứa tên và arguments
    Manager->>Manager: Tìm trong callback của request
    alt Callback có trong request
        Manager->>Callback: call(arguments, context)
        Callback-->>Manager: Tool result
    else Callback không có trong request và fallback bật
        Manager->>Resolver: resolve(toolName)
        alt Resolver tìm thấy callback
            Resolver-->>Manager: ToolCallback
            Manager->>Callback: call(arguments, context)
            Callback-->>Manager: Tool result
        else Resolver không tìm thấy
            Resolver-->>Manager: null
            Manager-->>App: Không có callback tương ứng
        end
    else Callback không có trong request và fallback tắt
        Manager-->>App: Không phân giải/thực thi tool đó
    end
    Manager-->>Model: Gửi kết quả để mô hình tiếp tục
~~~

Đường đi thông thường là ứng dụng chủ động gắn callback vào request bằng **.tools(...)**, hoặc đặt nhóm công cụ mặc định bằng **.defaultTools(...)**. Fallback chỉ là đường dự phòng khi model trả về tên không có trong callback list của request.

## 2. Cách phân giải trong Spring AI 1.0.x và 1.1.x

Trong các phiên bản 1.x, Spring AI mặc định dùng **DelegatingToolCallbackResolver** để chuyển việc tìm kiếm qua nhiều resolver:

- **SpringBeanToolCallbackResolver** tìm các Spring bean kiểu **Function**, **Supplier**, **Consumer** hoặc **BiFunction**.
- **StaticToolCallbackResolver** tìm trong danh sách **ToolCallback** có sẵn. Với Spring Boot auto-configuration, danh sách này được tạo từ các bean kiểu **ToolCallback** trong application context.

Với function bean, tên bean được dùng làm tên tool. Có thể cung cấp tên đó cho model bằng **toolNames(...)** hoặc khai báo tên mặc định bằng **defaultToolNames(...)**:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Description;

@Configuration(proxyBeanMethods = false)
class WeatherTools {

    @Bean
    @Description("Tra cứu thời tiết hiện tại theo tên thành phố.")
    Function<WeatherRequest, WeatherResponse> currentWeather(
            WeatherService weatherService) {
        return weatherService::getWeather;
    }
}
~~~

Trong Spring AI 1.x, request có thể chọn function bean bằng tên:

~~~java
String answer = chatClient.prompt()
    .user("Thời tiết ở Đà Nẵng hiện nay thế nào?")
    .toolNames("currentWeather")
    .call()
    .content();
~~~

Phía client gửi tên tool; phía server dùng **ToolCallbackResolver** để tìm callback tương ứng. Tên tool được chọn cho request sẽ quyết định công cụ nào được đưa vào yêu cầu chat đó.

Các kiểu **WeatherRequest**, **WeatherResponse** và **WeatherService** trong ví dụ là thành phần nghiệp vụ đã có của ứng dụng.

Có thể khai báo tool mặc định bằng **defaultToolNames(...)**:

~~~java
ChatClient client = ChatClient.builder(chatModel)
    .defaultToolNames("currentWeather")
    .build();
~~~

Các tool mặc định được dùng chung cho request được tạo từ builder đó. Hãy cẩn thận với nhóm mặc định vì công cụ có thể xuất hiện trong những request không cần đến nó.

### Đặc điểm cần nhớ của 1.x

| Thành phần | Hành vi trong 1.x |
| --- | --- |
| **ToolCallbackResolver** | Phân giải tên tool thành callback |
| **DelegatingToolCallbackResolver** | Ủy quyền tìm kiếm cho nhiều resolver |
| **SpringBeanToolCallbackResolver** | Tìm function-style bean theo tên |
| **StaticToolCallbackResolver** | Tìm callback từ danh sách tĩnh, gồm các **ToolCallback** bean |
| **toolNames(...)** | Chọn function bean theo tên cho request |
| **defaultToolNames(...)** | Chọn function bean theo tên cho các request mặc định |

Trong 1.x, cách đăng ký function bean theo tên thuận tiện nhưng kém an toàn kiểu hơn việc truyền trực tiếp callback. Nếu đổi tên bean hoặc gõ sai tên trong **toolNames(...)**, lỗi chỉ xuất hiện khi chạy.

## 3. Thay đổi lớn trong Spring AI 2.0

Spring AI 2.0 loại bỏ **SpringBeanToolCallbackResolver** và API **toolNames(...)**. Mẫu đăng ký function bean thuần rồi yêu cầu model gọi theo tên bean không còn được hỗ trợ.

Ví dụ cũ:

~~~java
@Bean
@Description("Tra cứu thời tiết theo tên thành phố.")
Function<WeatherRequest, WeatherResponse> currentWeather(
        WeatherService weatherService) {
    return weatherService::getWeather;
}

// Spring AI 1.x
chatClient.prompt()
    .user("Thời tiết ở Đà Nẵng thế nào?")
    .toolNames("currentWeather")
    .call()
    .content();
~~~

Trong Spring AI 2.x, hãy đăng ký một **ToolCallback** rõ ràng:

~~~java
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.function.FunctionToolCallback;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class WeatherToolConfiguration {

    @Bean
    ToolCallback currentWeather(WeatherService weatherService) {
        return FunctionToolCallback.builder(
                "currentWeather",
                weatherService::getWeather
            )
            .description("Tra cứu thời tiết hiện tại theo tên thành phố.")
            .inputType(WeatherRequest.class)
            .build();
    }
}
~~~

Sau đó truyền callback vào request:

Giả sử bean đã được inject vào assistant service với biến **currentWeather**:

~~~java
String answer = chatClient.prompt()
    .user("Thời tiết ở Đà Nẵng thế nào?")
    .tools(currentWeather)
    .call()
    .content();
~~~

Có thể dùng phương thức được đánh dấu **@Tool** thay cho **FunctionToolCallback** nếu muốn khai báo công cụ theo kiểu annotation. Điểm quan trọng của 2.0 là công cụ cần được biểu diễn bằng **ToolCallback** hoặc đối tượng có phương thức **@Tool**, thay vì một function bean thuần chỉ được tra cứu bằng tên.

### Resolver mặc định trong 2.0

**ToolCallbackResolver** vẫn tồn tại. Resolver mặc định dùng **StaticToolCallbackResolver** với các bean kiểu **ToolCallback** trong application context. Vì vậy, thay đổi trong 2.0 không có nghĩa là Spring AI bỏ khả năng phân giải tên; phần bị loại bỏ là cơ chế tìm raw **Function**/**Supplier**/**Consumer**/**BiFunction** bean bằng **SpringBeanToolCallbackResolver** và API **toolNames(...)**.

## 4. Thay đổi từ Spring AI 2.0.1: fallback tắt theo mặc định

Một thay đổi độc lập với việc loại bỏ **SpringBeanToolCallbackResolver** xuất hiện từ **2.0.1**: **DefaultToolCallingManager** không còn tự động tìm và thực thi callback toàn cục khi model yêu cầu một tool không nằm trong callback list của request.

Trước thay đổi này, manager có thể fallback tới **ToolCallbackResolver** ở cấp ứng dụng. Resolver mặc định được xây dựng từ các **ToolCallback** bean, nên một callback bean có thể được thực thi dù request hiện tại không đính kèm nó.

Từ 2.0.1:

- Chỉ các tool được gắn vào request bằng **.tools(...)**, **.defaultTools(...)** hoặc **ToolCallingChatOptions.toolCallbacks(...)** mới được thực thi theo mặc định.
- Một tool chỉ được resolver biết đến nhưng không được gắn vào request sẽ không được thực thi theo đường fallback mặc định.
- Có thể chủ động khôi phục hành vi cũ bằng property hoặc builder option.

Property cấu hình:

~~~properties
spring.ai.tools.resolution.fallback.enabled=false
~~~

Đây là giá trị mặc định từ 2.0.1 và trong Spring AI 2.1. Nếu thật sự cần cho phép fallback:

~~~properties
spring.ai.tools.resolution.fallback.enabled=true
~~~

Khi tự tạo **ToolCallingManager**, có thể bật cùng hành vi qua builder:

~~~java
ToolCallingManager toolCallingManager = ToolCallingManager.builder()
    .toolCallbackResolver(toolCallbackResolver)
    .resolutionFallbackEnabled(true)
    .build();
~~~

Nếu không gọi **.resolutionFallbackEnabled(true)**, builder dùng mặc định **false**.

## 5. Bảng đánh giá hành vi theo phiên bản

| Phiên bản | Resolver mặc định | Đăng ký function bean theo tên | Cách xử lý tool không gắn request |
| --- | --- | --- | --- |
| 1.0.x | **DelegatingToolCallbackResolver**: Spring bean resolver + static resolver | Có; dùng **toolNames(...)** và **defaultToolNames(...)** | Client chọn tên tool tường minh; không dùng property fallback của 2.x |
| 1.1.x | Như 1.0.x | Có; **toolNames(...)** vẫn được hỗ trợ | Cùng mô hình chọn tên tool tường minh của 1.x |
| 2.0.0 | **StaticToolCallbackResolver** cho **ToolCallback** bean | Không; **SpringBeanToolCallbackResolver** và **toolNames(...)** đã bị loại bỏ | Hành vi fallback cũ vẫn còn trước thay đổi 2.0.1 |
| 2.0.1+ | Resolver cho **ToolCallback** đã đăng ký | Không | Tắt theo mặc định; có thể bật lại bằng property/builder |
| 2.1.0 | **StaticToolCallbackResolver** với **ToolCallback** bean và **ToolCallbackProvider** bean (trừ MCP provider) | Không | Tắt theo mặc định |

Hai mốc 2.0 cần được đọc riêng:

1. **2.0.0:** thay đổi cách định nghĩa và đăng ký tool; bỏ resolver dành cho function bean thuần và bỏ **toolNames(...)**.
2. **2.0.1:** thay đổi quyền fallback; callback đã biết bởi resolver nhưng không gắn vào request không còn tự động được thực thi.

Không nên gộp hai thay đổi này thành một. Ứng dụng có thể đã migrate đúng sang **ToolCallback** bean ở 2.0.0 nhưng vẫn dựa vào fallback toàn cục; khi nâng lên 2.0.1, hành vi thực thi sẽ thay đổi nếu chưa gắn callback vào request.

## 6. Phân biệt callback được resolver biết đến và callback được phép chạy

Hãy xem xét ứng dụng có ba công cụ:

- **lookupOrder**: tra cứu đơn hàng.
- **refundOrder**: hoàn tiền.
- **deleteCustomer**: xóa hồ sơ khách hàng.

Giả sử cả ba đều là **ToolCallback** bean và đều được resolver mặc định biết đến. Một request chỉ đính kèm **lookupOrder**.

| Trạng thái | Fallback tắt | Fallback bật |
| --- | --- | --- |
| Model gọi **lookupOrder** | Callback có trong request nên được thực thi | Callback có trong request nên được thực thi |
| Model gọi **refundOrder** | Không được tìm qua resolver để thực thi | Có thể được resolver tìm và thực thi |
| Model gọi **deleteCustomer** | Không được tìm qua resolver để thực thi | Có thể được resolver tìm và thực thi |
| Model gọi tên không tồn tại | Không tìm thấy callback | Resolver cũng không tìm thấy callback |

Fallback bật có nghĩa là mọi tool có thể truy cập qua resolver đều có khả năng được thực thi khi model gửi đúng tên, kể cả tool có tác động phá hủy. Nó không tự kiểm tra vai trò người dùng, quyền trên tài nguyên hoặc sự phù hợp của tool với request hiện tại.

Một chi tiết quan trọng: fallback không tự thêm definition của tool bị thiếu vào prompt. Nó chỉ cung cấp đường tìm callback sau khi manager nhận được tên tool trong response. Vì vậy, đừng xem fallback là cơ chế khám phá tool hoặc cách thay thế việc gửi tool definition cho model.

## 7. Tại sao fallback mặc định bị tắt?

Khi một request chỉ đính kèm một tập công cụ, ứng dụng thường đang giới hạn khả năng mà model được phép yêu cầu trong lượt đó. Nếu manager có thể fallback tới mọi **ToolCallback** bean toàn cục, ranh giới này bị mở rộng.

Ví dụ:

- Request tra cứu chỉ cần quyền đọc nhưng resolver toàn cục cũng chứa tool cập nhật và xóa.
- Model trả về tên tool không nằm trong request, do nhầm lẫn hoặc do nội dung hội thoại trước đó.
- Manager tìm được callback trong resolver và thực thi dù ứng dụng không chủ định cung cấp công cụ đó cho request hiện tại.

Đây là lý do fallback bị tắt theo mặc định từ 2.0.1. Chỉ bật lại khi ứng dụng kiểm soát chặt tập tool mà resolver có thể trả về và có cơ chế xác thực, phân quyền ở thời điểm thực thi.

Ngay cả khi fallback tắt, việc gắn tool vào request cũng không thay thế authorization. Callback có trong request vẫn phải xác minh người dùng có quyền đọc hoặc thay đổi tài nguyên cụ thể. Tên tool và việc model đã yêu cầu gọi tool không phải là bằng chứng về quyền.

## 8. Resolver mặc định trong Spring AI 2.1

Trong Spring AI 2.1, resolver mặc định được cấu hình từ:

- Các bean kiểu **ToolCallback** trong application context.
- Các callback do bean kiểu **ToolCallbackProvider** cung cấp.

MCP provider là ngoại lệ: Spring AI không tự liệt kê chúng trong resolver mặc định vì việc gọi **getToolCallbacks()** có thể gây network round-trip đến từng MCP server ngay khi khởi động. Nếu ứng dụng dùng MCP tools, hãy inject provider và gắn rõ vào **ChatClient** bằng **.tools(...)** hoặc **.defaultTools(...)**.

Có thể khai báo một resolver tùy chỉnh khi cần chiến lược khác, ví dụ tra cứu từ registry trong database, classpath hoặc dịch vụ từ xa:

~~~java
import java.util.List;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.resolution.StaticToolCallbackResolver;
import org.springframework.ai.tool.resolution.ToolCallbackResolver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ToolResolverConfiguration {

    @Bean
    ToolCallbackResolver toolCallbackResolver(
            List<ToolCallback> toolCallbacks) {
        return new StaticToolCallbackResolver(toolCallbacks);
    }
}
~~~

Đoạn mã trên minh họa cách tạo resolver từ danh sách callback tĩnh. Nếu cần nguồn động, hãy triển khai **ToolCallbackResolver** để tra cứu theo tên và trả về callback tương ứng hoặc **null**:

~~~java
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.resolution.ToolCallbackResolver;
import org.springframework.stereotype.Component;

@Component
public class RegistryToolCallbackResolver implements ToolCallbackResolver {

    private final ToolRegistry toolRegistry;

    public RegistryToolCallbackResolver(ToolRegistry toolRegistry) {
        this.toolRegistry = toolRegistry;
    }

    @Override
    public ToolCallback resolve(String toolName) {
        return toolRegistry.findCallback(toolName).orElse(null);
    }
}
~~~

**ToolRegistry** trong ví dụ là interface nghiệp vụ do ứng dụng định nghĩa. Resolver không nên thực thi nghiệp vụ trong **resolve(...)**; nó chỉ tìm callback. Callback được trả về mới xử lý đối số và gọi service.

Khi cung cấp resolver tùy chỉnh, hãy xác định rõ chiến lược thay thế resolver auto-configured theo cấu hình Spring của phiên bản đang dùng. Không tạo nhiều resolver bean cùng vai trò mà không có quy tắc chọn rõ ràng.

## 9. Khác biệt về vòng thực thi ChatModel giữa 1.x và 2.x

Ngoài resolver, Spring AI 2.0 còn thay đổi nơi điều phối vòng tool calling:

- Trong 1.x, các implementation **ChatModel** có vòng thực thi tool nội bộ thông qua **ToolCallingManager**.
- Từ 2.0, **ChatClient** dùng **ToolCallingAdvisor** để điều phối vòng gọi tool.
- Nếu gọi **ChatModel** trực tiếp trong 2.x, response có thể chứa tool call nhưng ứng dụng phải tự điều phối vòng lặp, thường thông qua **ToolCallingManager**.

Thay đổi này không phải là resolution fallback. Một ứng dụng có thể dùng **ChatClient** và **ToolCallingAdvisor** nhưng vẫn cấu hình fallback; ngược lại, có thể tự điều phối **ChatModel** trực tiếp với fallback tắt.

Với phần lớn ứng dụng, dùng **ChatClient** và đính kèm callback rõ ràng là đường đi dễ kiểm soát:

~~~java
String answer = ChatClient.create(chatModel)
    .prompt()
    .user(question)
    .tools(orderReadTools)
    .call()
    .content();
~~~

Nếu tự tạo **ToolCallingManager**, cần cấu hình cả **ToolCallbackResolver** và **resolutionFallbackEnabled(...)** theo chính sách của ứng dụng. Đừng cho rằng việc truyền resolver vào manager đồng nghĩa fallback đã bật.

## 10. Chiến lược migration từ 1.x lên 2.x

Khi nâng cấp, thực hiện theo thứ tự:

1. **Tìm API cũ:** tìm **toolNames(...)**, **defaultToolNames(...)**, **SpringBeanToolCallbackResolver** và các bean trả về **Function**, **Supplier**, **Consumer** hoặc **BiFunction** được dùng làm tool.
2. **Tạo callback tường minh:** chuyển function bean thành **FunctionToolCallback** bean; hoặc chuyển logic sang phương thức **@Tool**.
3. **Gắn callback vào request:** dùng **.tools(...)** hoặc **.defaultTools(...)** theo đúng phạm vi sử dụng.
4. **Đánh giá fallback:** kiểm tra ứng dụng có phụ thuộc vào việc thực thi tool toàn cục dù request không gắn callback hay không.
5. **Giữ fallback tắt nếu không có yêu cầu rõ:** không bật **spring.ai.tools.resolution.fallback.enabled** chỉ để khắc phục việc quên đính kèm callback.
6. **Kiểm tra quyền trong callback:** xác thực danh tính và quyền trên từng tài nguyên tại service nghiệp vụ.
7. **Kiểm thử lại các đường gọi:** bao gồm tool có trong request, tool chỉ có trong resolver, tool không tồn tại và tool bị từ chối quyền.

Ví dụ cấu hình khuyến nghị cho ứng dụng muốn giới hạn tool theo từng request:

~~~properties
# Mặc định từ Spring AI 2.0.1+: chỉ thực thi tool được gắn vào request
spring.ai.tools.resolution.fallback.enabled=false
~~~

Nếu cần hành vi fallback vì một kiến trúc đặc biệt, hãy ghi rõ lý do, giới hạn các callback mà resolver có thể trả về và thêm kiểm thử bảo mật cho từng loại tool.

## 11. Kiểm thử resolver và fallback

Nên kiểm tra riêng resolver và quyết định fallback của manager.

| Ca kiểm thử | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Resolver tìm thấy tool | Gọi **resolve("lookupOrder")** với tên đã đăng ký | Trả đúng callback |
| Resolver không tìm thấy tool | Gọi với tên không tồn tại | Trả **null** |
| Tool có trong request | Fallback tắt, callback được gắn vào request | Callback vẫn được thực thi |
| Tool không có trong request | Fallback tắt, resolver biết tool | Không thực thi callback toàn cục |
| Tool không có trong request | Fallback bật, resolver biết tool | Manager có thể phân giải và thực thi callback |
| Tool không tồn tại | Fallback bật, resolver trả **null** | Không có callback để thực thi; lỗi được xử lý theo luồng tool calling |
| Tool nhạy cảm không được cấp quyền | Callback được tìm thấy nhưng người dùng thiếu quyền | Service từ chối thực thi nghiệp vụ |
| Callback từ provider | Provider được đăng ký trong context | Resolver mặc định nhận callback theo quy tắc của phiên bản |
| MCP provider | MCP provider được cấu hình | Inject và gắn provider rõ ràng vào request/client |

Với kiểm thử tích hợp, hãy dùng callback có bộ đếm hoặc mock service để xác nhận nó có thực sự được gọi hay không. Chỉ kiểm tra câu trả lời cuối của model là chưa đủ, vì model có thể trả lời theo nhiều cách và có thể không gọi tool trong một lần chạy.

Khi kiểm tra fallback, cần bảo đảm request thực sự không chứa callback đang thử nghiệm. Nếu vô tình gắn callback qua **.defaultTools(...)**, ca kiểm thử sẽ không chứng minh được hành vi fallback.

## 12. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| **toolNames(...)** không biên dịch ở 2.x | API đã bị loại bỏ | Tạo **ToolCallback** rõ ràng và truyền bằng **.tools(...)** |
| Function bean không được tìm thấy ở 2.x | **SpringBeanToolCallbackResolver** đã bị loại bỏ | Dùng **FunctionToolCallback** bean |
| ToolCallback bean tồn tại nhưng không chạy | Callback không được gắn vào request và fallback đang tắt | Truyền callback/provider qua **.tools(...)** hoặc **.defaultTools(...)** |
| Resolver trả **null** | Tên model gửi không khớp hoặc callback chưa được đăng ký | Kiểm tra tên tool, registry và callback provider |
| Tool không xuất hiện trong request | Chưa gắn callback hoặc provider vào ChatClient | Kiểm tra **.tools(...)** và **.defaultTools(...)** |
| Tool mặc định không được gọi khi thêm tool runtime ở 1.x | Với API name-based 1.x, runtime tool names có thể thay thế default tool names | Kiểm tra quy tắc override của phiên bản; không áp dụng máy móc quy tắc 2.x |
| Tool nhạy cảm chạy dù request không đính kèm | Fallback được bật và resolver có callback đó | Tắt fallback hoặc giới hạn registry và quyền thực thi |
| MCP tool không xuất hiện trong resolver mặc định 2.1 | MCP provider không được eager-list vào resolver | Inject provider MCP và truyền rõ qua **.tools(...)** hoặc **.defaultTools(...)** |

Khi đọc ví dụ trên Internet, luôn kiểm tra tài liệu đúng nhánh phiên bản. Ví dụ 1.1 dùng **toolNames(...)** có thể hoàn toàn đúng với 1.1.8 nhưng không còn biên dịch trên 2.x.

## 13. Nguyên tắc lựa chọn

- Ưu tiên gắn callback tường minh vào request bằng **.tools(...)** khi tập công cụ thay đổi theo tác vụ hoặc quyền người dùng.
- Chỉ dùng **.defaultTools(...)** cho những công cụ thực sự phù hợp với mọi request của client.
- Dùng **ToolCallbackResolver** tùy chỉnh khi cần tra cứu theo tên từ registry động; không triển khai resolver chỉ để né việc đăng ký callback rõ ràng.
- Giữ resolution fallback tắt theo mặc định từ 2.0.1 trở đi.
- Nếu bật fallback, giới hạn tập callback resolver có thể trả về và xác thực quyền trong callback/service.
- Không xem việc resolver tìm thấy callback là bằng chứng người dùng được phép gọi callback đó.
- Kiểm thử theo đúng phiên bản Spring AI được khóa trong dependency management.

## Bài thực hành

Một ứng dụng đang chạy Spring AI 1.1.8 có bean **Function<CustomerQuery, CustomerProfile>** tên **customerProfile**, và request gọi **.toolNames("customerProfile")**. Ứng dụng cần nâng lên Spring AI 2.1.

Hãy thực hiện:

1. Chuyển function bean thành **FunctionToolCallback** bean có tên **customerProfile**, mô tả và **inputType(CustomerQuery.class)**.
2. Thay **.toolNames("customerProfile")** bằng **.tools(customerProfileCallback)**.
3. Tạo một tool **deleteCustomer** có quyền cao nhưng không gắn nó vào request tra cứu.
4. Xác nhận với fallback mặc định tắt, model không thể thực thi **deleteCustomer** chỉ vì callback tồn tại trong application context.
5. Thử bật fallback trong một cấu hình kiểm thử riêng và quan sát callback có thể được phân giải khi model trả đúng tên.
6. Bổ sung kiểm tra quyền ở service để kể cả khi callback được tìm thấy, người dùng không có quyền vẫn không thể xóa khách hàng.

Sau khi hoàn thành, hãy giải thích vì sao **ToolCallbackResolver** vẫn tồn tại trong 2.1 dù fallback mặc định đã tắt, và vì sao không nên bật fallback chỉ để giữ nguyên hành vi của một ứng dụng 1.x.

## Ghi nhớ

Trong Spring AI 1.x, **DelegatingToolCallbackResolver** có thể tìm cả function-style bean và **ToolCallback** bean; **toolNames(...)** cho phép chọn công cụ theo tên. Spring AI 2.0 bỏ **SpringBeanToolCallbackResolver** và **toolNames(...)**, yêu cầu đăng ký callback rõ ràng. Từ 2.0.1, fallback tới resolver cho tool không gắn vào request bị tắt mặc định; 2.1 tiếp tục giữ mặc định này. Hãy ưu tiên **.tools(...)** và **.defaultTools(...)** để thể hiện tập công cụ được phép dùng trong request. Chỉ bật fallback khi có nhu cầu kiến trúc rõ ràng, resolver được kiểm soát và callback vẫn xác thực quyền ở runtime.

## Tài liệu tham khảo

- [Spring AI 1.0.9 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 1.1.8 — Tool Calling](https://docs.spring.io/spring-ai/reference/1.1/api/tools.html)
- [Spring AI 2.0.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/2.0/api/tools.html)
- [Spring AI 2.1.0 — Tool Calling](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI Upgrade Notes — Tool Resolution Fallback](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)
