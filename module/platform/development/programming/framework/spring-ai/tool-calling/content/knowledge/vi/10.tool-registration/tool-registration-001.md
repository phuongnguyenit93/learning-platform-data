# Phân biệt tạo bean, phân giải theo tên và cung cấp công cụ cho yêu cầu

Trong Spring AI, khai báo một tool, tạo object để thực thi tool và cung cấp tool cho một lần gọi hội thoại là những bước khác nhau. Một function có thể đã được Spring tạo thành bean nhưng chưa được đưa vào request. Một callback có thể đã tồn tại trong ApplicationContext nhưng model chỉ nhìn thấy nó khi ứng dụng cung cấp callback hoặc tên tool phù hợp.

Hiểu rõ ba bước này giúp tránh lỗi “đã có bean nhưng model không gọi được”, đồng thời kiểm soát được tập công cụ mà mỗi request được phép sử dụng. Bài học sử dụng API Spring AI 1.0.x, tập trung vào `@Bean`, `ToolCallbackResolver`, `toolNames(...)`, `tools(...)` và `toolCallbacks(...)`.

## Sau bài học, bạn có thể

- Phân biệt tạo Spring bean với đăng ký tool cho model.
- Tạo function tool bean bằng `@Bean` và mô tả bằng `@Description`.
- Giải thích vai trò của `SpringBeanToolCallbackResolver`, `StaticToolCallbackResolver` và `ToolCallbackResolver`.
- Phân biệt tên Spring bean với tên trong `ToolDefinition`.
- Chọn cách cung cấp tool trực tiếp hoặc phân giải theo tên cho từng request.
- Cấu hình tool mặc định cho `ChatClient` và hiểu cách tool runtime thay thế tool mặc định trong Spring AI 1.0.
- Giới hạn tool theo quyền và ngữ cảnh của người dùng.

## Ba bước cần phân biệt

Một tool thường đi qua ba bước:

1. **Tạo:** ứng dụng tạo object hoặc Spring bean chứa logic thực thi, chẳng hạn một `Function`, một class có method `@Tool`, hoặc một `ToolCallback`.
2. **Phân giải:** Spring AI tìm callback tương ứng với một tên tool. Việc này có thể diễn ra trực tiếp từ object/callback đã truyền hoặc thông qua `ToolCallbackResolver`.
3. **Cung cấp:** ứng dụng gắn object, callback hoặc tên tool vào một request cụ thể hay cấu hình mặc định của `ChatClient`. Từ đó, định nghĩa tool mới được gửi cho model.

~~~mermaid
flowchart TD
    A[Logic Java: @Tool, Function hoặc ToolCallback] --> B[Tạo object / Spring bean]
    B --> C{Cách xác định callback}
    C -->|Truyền object hoặc callback| D[Callback được tạo trực tiếp]
    C -->|Truyền tên tool| E[ToolCallbackResolver]
    E --> F[SpringBeanToolCallbackResolver]
    E --> G[StaticToolCallbackResolver]
    F --> H[ToolCallback]
    G --> H
    D --> I[Cung cấp vào ChatClient request]
    H --> I
    I --> J[ToolDefinition được gửi cho model]
    J --> K[Model yêu cầu gọi tool]
    K --> L[Ứng dụng thực thi callback]
~~~

Điểm quan trọng là bean có thể tồn tại mà chưa được cung cấp cho model. Tương tự, việc model nhận được một tool definition cũng chưa có nghĩa model được tự thực thi Java method. Ứng dụng và Spring AI mới là bên phân giải callback, kiểm tra và thực thi lời gọi.

## Tạo tool dưới dạng Spring bean

Spring quản lý object thông qua ApplicationContext. Có thể khai báo tool theo một số hình thức khác nhau, tùy cách muốn tái sử dụng và phân giải.

### Bean chứa method @Tool

Với cách khai báo bằng annotation, class có thể được đăng ký thành bean:

~~~java
@Component
public class OrderTools {

    private final OrderQueryService orderQueryService;

    public OrderTools(OrderQueryService orderQueryService) {
        this.orderQueryService = orderQueryService;
    }

    @Tool(description = "Tra cứu trạng thái của đơn hàng theo mã đơn hàng")
    public OrderStatus getOrderStatus(
            @ToolParam(description = "Mã đơn hàng cần tra cứu") String orderId) {
        return orderQueryService.getStatus(orderId);
    }
}
~~~

Spring tạo bean `OrderTools` và inject `OrderQueryService`. Tuy nhiên, chỉ có `@Component` không có nghĩa method `getOrderStatus` tự động xuất hiện trong mọi request. Ứng dụng vẫn cần cung cấp object đó qua `ChatClient`:

~~~java
String answer = chatClient.prompt()
        .user("Đơn hàng DH-1024 đang ở trạng thái nào?")
        .tools(orderTools)
        .call()
        .content();
~~~

Spring AI tạo callback từ các method có `@Tool` trên object được truyền vào. Tool chỉ có trong request này. Nếu muốn dùng cho tất cả request được tạo từ cùng builder, có thể cấu hình `defaultTools(orderTools)`.

### Bean trả về Function hoặc functional interface

Với function-based tool, Spring AI 1.0 hỗ trợ khai báo bean có kiểu `Function`, `Supplier`, `Consumer` hoặc `BiFunction`. Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class WeatherToolConfiguration {

    public static final String CURRENT_WEATHER_TOOL = "currentWeather";

    @Bean(name = CURRENT_WEATHER_TOOL)
    @Description("Tra cứu thời tiết hiện tại theo tên thành phố hoặc địa điểm")
    Function<WeatherRequest, WeatherResponse> currentWeather(
            WeatherService weatherService) {
        return weatherService::getWeather;
    }
}
~~~

Ở đây:

- `@Bean` yêu cầu Spring tạo và quản lý function bean.
- Tên bean là `currentWeather`, được chỉ định bằng hằng số `CURRENT_WEATHER_TOOL`.
- `@Description` cung cấp mô tả để model hiểu chức năng.
- `Function<WeatherRequest, WeatherResponse>` là logic thực thi.
- `WeatherService` được inject theo constructor/method parameter của bean factory method, vì vậy function dùng service do Spring quản lý.

Nếu không khai báo tên rõ ràng, tên method `@Bean` thường được dùng làm tên bean. Với function bean được phân giải động, tên bean cũng là tên tool. Vì tên này được dùng trong request, nên khai báo bằng hằng số để tránh lỗi chính tả và giúp đổi tên có kiểm soát.

`@Description` ở ví dụ là annotation của Spring Framework:

~~~java
import org.springframework.context.annotation.Description;
~~~

Nếu không có mô tả, Spring AI có thể dùng tên method làm mô tả mặc định. Trong thực tế, nên cung cấp mô tả rõ hành động, dữ liệu đầu vào và trường hợp sử dụng để model chọn tool chính xác hơn.

### Bean trả về ToolCallback

Có thể tạo sẵn `ToolCallback` bean nếu muốn kiểm soát rõ tên, schema hoặc metadata của tool:

~~~java
@Configuration(proxyBeanMethods = false)
public class WeatherCallbackConfiguration {

    @Bean
    ToolCallback currentWeatherCallback(WeatherService weatherService) {
        return FunctionToolCallback
                .builder(
                        WeatherToolConfiguration.CURRENT_WEATHER_TOOL,
                        weatherService::getWeather
                )
                .description("Tra cứu thời tiết hiện tại theo tên thành phố hoặc địa điểm")
                .inputType(WeatherRequest.class)
                .build();
    }
}
~~~

Khác với bean trả về `Function`, bean này trả về một `ToolCallback` đã có `ToolDefinition`. Tên model nhìn thấy được lấy từ `ToolDefinition.name()`. Nếu cần đổi tên tool, thay tên ở builder; tên Spring bean chứa callback có thể khác tên tool.

Spring Boot auto-configuration của Spring AI 1.0 cung cấp `StaticToolCallbackResolver` với các `ToolCallback` bean trong ApplicationContext. Resolver này tra cứu callback theo tên tool trong `ToolDefinition`.

## Phân giải theo tên bằng ToolCallbackResolver

`ToolCallbackResolver` là abstraction để tìm một callback dựa trên tên:

~~~java
public interface ToolCallbackResolver {

    @Nullable
    ToolCallback resolve(String toolName);
}
~~~

Khi ứng dụng cung cấp tên thay vì callback trực tiếp, Spring AI cần tìm đúng callback để thực thi. Trong cấu hình mặc định của Spring AI 1.0, một `DelegatingToolCallbackResolver` chuyển yêu cầu lần lượt qua các resolver phù hợp.

Hai resolver quan trọng là:

| Resolver | Nguồn tìm kiếm | Cách xác định tên |
|---|---|---|
| `SpringBeanToolCallbackResolver` | Spring bean kiểu `Function`, `Supplier`, `Consumer`, `BiFunction` | Tên Spring bean |
| `StaticToolCallbackResolver` | Các bean kiểu `ToolCallback` trong ApplicationContext | `ToolDefinition.name()` của callback |

### SpringBeanToolCallbackResolver

Resolver này xử lý các functional interface bean. Ví dụ bean `currentWeather` được khai báo ở trên có thể được phân giải bằng tên:

~~~java
chatClient.prompt()
        .user("Thời tiết ở Đà Nẵng hiện nay thế nào?")
        .toolNames(WeatherToolConfiguration.CURRENT_WEATHER_TOOL)
        .call()
        .content();
~~~

Trong request, `toolNames(...)` chứa tên function bean. Resolver tìm bean tương ứng, tạo callback phù hợp và cung cấp định nghĩa tool cho model. Khi model trả về yêu cầu gọi `currentWeather`, callback tương ứng được dùng để gọi function.

Cách này phù hợp khi muốn giữ function bean trong Spring context và chỉ định tool bằng tên ở nơi tạo request. Nó cũng cho phép thay đổi tập tool được cung cấp theo ngữ cảnh mà không cần inject từng function bean vào mọi thành phần gọi hội thoại.

### StaticToolCallbackResolver

Resolver này xử lý các `ToolCallback` bean đã được tạo sẵn. Ví dụ, bean `currentWeatherCallback` ở trên trả về `FunctionToolCallback`, và tên tool của nó là `currentWeather`.

Có thể phân giải theo tên:

~~~java
chatClient.prompt()
        .user("Thời tiết ở Đà Nẵng hiện nay thế nào?")
        .toolNames(WeatherToolConfiguration.CURRENT_WEATHER_TOOL)
        .call()
        .content();
~~~

Cũng có thể inject callback và cung cấp trực tiếp:

~~~java
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.beans.factory.annotation.Qualifier;

@Service
public class WeatherAssistant {

    private final ChatClient chatClient;
    private final ToolCallback currentWeatherCallback;

    public WeatherAssistant(
            ChatModel chatModel,
            @Qualifier("currentWeatherCallback")
            ToolCallback currentWeatherCallback) {
        this.chatClient = ChatClient.create(chatModel);
        this.currentWeatherCallback = currentWeatherCallback;
    }

    public String ask(String question) {
        return chatClient.prompt()
                .user(question)
                .toolCallbacks(currentWeatherCallback)
                .call()
                .content();
    }
}
~~~

Trong trường hợp này, `toolCallbacks(...)` nhận callback cụ thể nên không cần tra cứu tên bean. Tên hiển thị với model vẫn là `ToolDefinition.name()` bên trong callback.
Nếu ứng dụng có nhiều `ToolCallback` bean, dùng `@Qualifier` hoặc inject một danh sách rồi chọn callback phù hợp để tránh lỗi không xác định được bean.

### Khi nào cần resolver tùy chỉnh?

Resolver mặc định đáp ứng hai nguồn phổ biến: function bean và ToolCallback bean. Nếu ứng dụng cần tra cứu callback từ registry riêng, cơ sở dữ liệu, dịch vụ từ xa hoặc danh mục tool theo tenant, có thể triển khai `ToolCallbackResolver` riêng hoặc cấu hình chuỗi resolver phù hợp.

Ví dụ một cấu hình resolver tĩnh:

~~~java
@Bean
ToolCallbackResolver toolCallbackResolver(List<ToolCallback> callbacks) {
    return new StaticToolCallbackResolver(callbacks);
}
~~~

Đây là cách thay thế resolver mặc định bằng một resolver dùng danh sách callback đã cung cấp. Nếu ứng dụng cần cả function bean và callback bean, cấu hình resolver phải giữ hoặc kết hợp các chiến lược tương ứng; không vô tình loại bỏ resolver cần thiết khi thay bean auto-configured.

Không nên tự viết resolver chỉ để tránh truyền một callback trực tiếp. Resolver tùy chỉnh hữu ích khi có yêu cầu phân giải động thực sự, chẳng hạn chọn tool theo tenant, module hoặc registry được quản trị tập trung.

## Cung cấp tool trực tiếp cho một request

Trong Spring AI 1.0, `ChatClient` có các cách cung cấp tool theo loại đối tượng:

| API | Nhận đầu vào | Dùng khi |
|---|---|---|
| `.tools(...)` | Object có method `@Tool` | Muốn Spring AI tạo callback từ tool object |
| `.toolCallbacks(...)` | `ToolCallback` đã tạo | Muốn cung cấp callback cụ thể |
| `.toolNames(...)` | Tên tool | Muốn resolver phân giải callback lúc chạy |

Ví dụ với object có `@Tool`:

~~~java
chatClient.prompt()
        .user("Tra cứu đơn hàng DH-1024")
        .tools(orderTools)
        .call()
        .content();
~~~

Ví dụ với callback đã tạo:

~~~java
chatClient.prompt()
        .user("Tra cứu thời tiết tại Đà Nẵng")
        .toolCallbacks(currentWeatherCallback)
        .call()
        .content();
~~~

Ví dụ với tên function bean:

~~~java
chatClient.prompt()
        .user("Tra cứu thời tiết tại Đà Nẵng")
        .toolNames(WeatherToolConfiguration.CURRENT_WEATHER_TOOL)
        .call()
        .content();
~~~

Các tool cung cấp ở cấp request chỉ có hiệu lực cho lần gọi đó. Đây là lựa chọn phù hợp khi mỗi tác vụ, người dùng hoặc vai trò cần một tập công cụ khác nhau.

## Cung cấp tool mặc định cho ChatClient

Nếu một tập tool được dùng chung cho các request được tạo từ cùng `ChatClient.Builder`, có thể cấu hình ở cấp builder:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultTools(orderTools)
        .defaultToolCallbacks(currentWeatherCallback)
        .defaultToolNames(WeatherToolConfiguration.CURRENT_WEATHER_TOOL)
        .build();
~~~

Các phương thức default tương ứng với ba cách cung cấp tool ở cấp request:

- `defaultTools(...)`: tool object có method `@Tool`.
- `defaultToolCallbacks(...)`: callback đã tạo.
- `defaultToolNames(...)`: tên được resolver phân giải.

Default tools được chia sẻ giữa các request được tạo từ cùng builder. Điều này tiện cho những tool thực sự cần dùng rộng rãi, chẳng hạn công cụ tra cứu thời gian hoặc thông tin công khai. Tuy nhiên, công cụ ghi dữ liệu, quản trị hoặc có tác động lớn không nên tự động xuất hiện trong mọi request.

### Quy tắc thay thế giữa default và runtime trong Spring AI 1.0

Trong Spring AI 1.0, nếu request cung cấp tool ở runtime, tập runtime sẽ thay thế toàn bộ tập tool mặc định; không tự động nối thêm vào default. Ví dụ:

~~~java
ChatClient chatClient = ChatClient.builder(chatModel)
        .defaultToolNames("currentWeather")
        .build();

// Request này chỉ cung cấp orderLookup.
// Không giả định currentWeather vẫn được giữ lại.
String answer = chatClient.prompt()
        .user("Tra cứu đơn hàng DH-1024")
        .toolNames("orderLookup")
        .call()
        .content();
~~~

Nếu một request cần cả tool mặc định và tool bổ sung, hãy cung cấp đầy đủ danh sách mong muốn ở cấp request:

~~~java
String answer = chatClient.prompt()
        .user("Tra cứu thời tiết và trạng thái đơn hàng")
        .toolNames(
                WeatherToolConfiguration.CURRENT_WEATHER_TOOL,
                OrderToolConfiguration.ORDER_LOOKUP_TOOL
        )
        .call()
        .content();
~~~

Điều này giúp tập tool gửi cho model được xác định rõ ở đúng nơi gọi. Hãy kiểm tra lại quy tắc override theo phiên bản Spring AI đang dùng trước khi nâng cấp vì API và cách đăng ký tool thay đổi giữa các major version.

## Bean name và tool name không phải lúc nào cũng giống nhau

Hai loại tên có ý nghĩa khác nhau:

- **Bean name:** định danh object trong Spring ApplicationContext. Với function bean được `SpringBeanToolCallbackResolver` xử lý, bean name cũng là tên tool.
- **Tool name:** định danh trong `ToolDefinition` mà model nhìn thấy. Với `ToolCallback` bean, tên này lấy từ `ToolDefinition.name()`.

Ví dụ:

~~~java
@Bean("weatherFunctionBean")
@Description("Tra cứu thời tiết hiện tại")
Function<WeatherRequest, WeatherResponse> currentWeather(
        WeatherService weatherService) {
    return weatherService::getWeather;
}
~~~

Function bean trên có bean name là `weatherFunctionBean`, vì vậy khi dùng dynamic resolution phải cung cấp đúng tên:

~~~java
chatClient.prompt()
        .user("Thời tiết tại Hà Nội thế nào?")
        .toolNames("weatherFunctionBean")
        .call()
        .content();
~~~

Trong khi đó, nếu bean trả về `ToolCallback` có `ToolDefinition.name()` là `currentWeather`, tên tool dùng để phân giải là `currentWeather`, kể cả tên Spring bean chứa callback là `weatherCallbackBean`.

Hãy thống nhất tên bằng hằng số nếu tên được dùng ở nhiều nơi:

~~~java
public final class ToolNames {

    public static final String CURRENT_WEATHER = "currentWeather";
    public static final String ORDER_LOOKUP = "orderLookup";

    private ToolNames() {
    }
}
~~~

Với function bean, dùng hằng số làm tên `@Bean`. Với FunctionToolCallback, dùng hằng số làm tên truyền vào builder. Khi gọi `toolNames(...)`, dùng cùng hằng số đó. Cách này giảm lỗi chính tả do tên là chuỗi và lỗi chỉ xuất hiện lúc phân giải runtime.

## Giới hạn tập tool theo request và quyền truy cập

Việc một function bean tồn tại trong ApplicationContext không có nghĩa mọi người dùng đều được phép gọi nó. Việc resolver tìm được callback cũng không phải là bước phân quyền.

Ứng dụng nên quyết định tập tool theo danh tính đã xác thực và tác vụ hiện tại:

1. Xác thực người dùng ở tầng web hoặc application service.
2. Xác định các tool mà vai trò hoặc tenant được phép sử dụng.
3. Cung cấp đúng object, callback hoặc tên tool cho request.
4. Khi callback thực thi, dịch vụ nghiệp vụ tiếp tục kiểm tra quyền trên tài nguyên cụ thể.
5. Ghi nhận tool name, user/tenant đã xác thực, kết quả và mã tương quan theo chính sách log.

Không dựa vào tên tool do model yêu cầu để cấp quyền. Model chỉ có thể yêu cầu một tool trong tập ứng dụng đã cung cấp; backend vẫn phải kiểm tra người dùng có được xem hoặc thay đổi dữ liệu hay không.

Với thao tác nhạy cảm, hãy ưu tiên cung cấp tool theo request sau khi ứng dụng xác định ngữ cảnh. Tránh đặt tool xóa dữ liệu, hoàn tiền, thay đổi quyền hoặc gửi giao dịch vào default list dùng chung. Nếu dùng dynamic resolution, hãy giới hạn tên tool có thể được cung cấp và bảo đảm resolver không mở ra một danh mục rộng hơn chính sách ứng dụng.

## Chú ý tương thích phiên bản

Các ví dụ `toolNames(...)`, `defaultToolNames(...)` và `SpringBeanToolCallbackResolver` trong bài thuộc API Spring AI 1.0.x. Spring AI 2.0 đã loại bỏ `SpringBeanToolCallbackResolver` và API `toolNames()` vốn dùng để phân giải các bean `Function`/`Supplier`/`Consumer` theo tên. Khi nâng cấp lên 2.x, cần chuyển sang đăng ký `ToolCallback` tường minh hoặc object có method `@Tool`, theo hướng dẫn migration của phiên bản đó.

Do vậy, trước khi sao chép ví dụ, hãy kiểm tra version Spring AI trong BOM của dự án và dùng đúng tài liệu tương ứng. Không trộn code đăng ký tool của 1.0 với hướng dẫn 2.x.

## Kiểm thử việc tạo, phân giải và cung cấp tool

Nên kiểm tra riêng ba bước để xác định lỗi nằm ở đâu:

- **Kiểm thử tạo bean:** ApplicationContext có bean đúng tên và đúng kiểu hay không; dependency đã được inject chưa; mô tả có tồn tại không.
- **Kiểm thử phân giải:** `ToolCallbackResolver.resolve(name)` trả về callback đúng hay `null`; tool name có trùng hoặc sai chính tả không.
- **Kiểm thử cung cấp:** request có chứa đúng tên hoặc callback cần thiết; schema được gửi cho model có đúng không; tool không liên quan có bị đưa vào ngoài ý muốn không.

Ví dụ kiểm tra function bean trong Spring context:

~~~java
@SpringBootTest
class WeatherToolRegistrationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void shouldRegisterWeatherFunctionBean() {
        Function<WeatherRequest, WeatherResponse> function =
                applicationContext.getBean(
                        WeatherToolConfiguration.CURRENT_WEATHER_TOOL,
                        Function.class
                );

        assertThat(function).isNotNull();
    }
}
~~~

Với resolver, có thể kiểm tra callback theo tên:

~~~java
@Autowired
ToolCallbackResolver toolCallbackResolver;

@Test
void shouldResolveWeatherToolByName() {
    ToolCallback callback = toolCallbackResolver.resolve(
            WeatherToolConfiguration.CURRENT_WEATHER_TOOL
    );

    assertThat(callback).isNotNull();
    assertThat(callback.getToolDefinition().name())
            .isEqualTo(WeatherToolConfiguration.CURRENT_WEATHER_TOOL);
}
~~~

Các test trên minh họa cách kiểm tra; trong dự án thực tế, cần khai báo đầy đủ bean `ToolCallbackResolver` và các dependency liên quan trong test context. Nếu muốn kiểm tra hành vi model, thêm integration test riêng. Không cần gọi model thật chỉ để xác minh Spring đã tạo bean hoặc resolver tìm được callback.

## Những lỗi thường gặp

- **Cho rằng @Bean tự động cung cấp tool cho mọi request:** bean chỉ là object trong ApplicationContext. Ứng dụng vẫn phải cung cấp tool bằng API phù hợp.
- **Nhầm @Tool component với function bean:** `SpringBeanToolCallbackResolver` xử lý function-family bean; object có method `@Tool` thường được truyền bằng `.tools(object)` hoặc `.defaultTools(object)`.
- **Dùng tên method thay vì tên bean:** function bean được phân giải theo bean name. Nếu `@Bean("...")` đặt tên tường minh, phải dùng đúng tên đó.
- **Nhầm bean name với ToolDefinition.name:** ToolCallback bean được định danh theo tên trong definition khi dùng static resolver.
- **Đặt tên tool không nhất quán:** lỗi chuỗi chỉ xuất hiện lúc runtime. Dùng hằng số cho tên dùng chung.
- **Đưa toàn bộ tool vào default list:** tool nhạy cảm có thể xuất hiện trong request không phù hợp. Chọn tool theo từng request.
- **Giả định runtime tools nối thêm vào defaults:** trong Spring AI 1.0, runtime tools thay thế defaults. Cung cấp danh sách đầy đủ nếu cần kết hợp.
- **Thay resolver mặc định nhưng bỏ mất resolver cần thiết:** cấu hình resolver tùy chỉnh phải giữ những nguồn phân giải mà ứng dụng cần.
- **Cho rằng resolver là lớp phân quyền:** callback resolve thành công không chứng minh người dùng có quyền truy cập tài nguyên.

## Checklist trước khi cung cấp tool

- [ ] Bean được tạo đúng tên và kiểu.
- [ ] Function bean có `@Description` đủ rõ hoặc callback có ToolDefinition description phù hợp.
- [ ] Tool name duy nhất trong tập tool của request.
- [ ] Đã chọn cung cấp object, callback hay tên theo nhu cầu.
- [ ] Nếu dùng `toolNames`, resolver có thể tìm được callback.
- [ ] Nếu dùng ToolCallback bean, `ToolDefinition.name()` khớp tên được phân giải.
- [ ] Tập tool của request phù hợp với người dùng, tenant và tác vụ.
- [ ] Đã hiểu quy tắc default/runtime override của phiên bản đang dùng.
- [ ] Dịch vụ nghiệp vụ vẫn kiểm tra quyền khi callback được thực thi.
- [ ] Có test cho tạo bean, phân giải và cung cấp tool.

## Ghi nhớ khi thiết kế

Tạo bean là bước đăng ký object vào Spring ApplicationContext. Phân giải theo tên là bước tìm `ToolCallback` tương ứng thông qua `ToolCallbackResolver`. Cung cấp tool là bước gắn object, callback hoặc tên vào request để model biết những khả năng nào đang có.

Trong Spring AI 1.0.x, function bean được phân giải theo Spring bean name; `ToolCallback` bean được phân giải theo `ToolDefinition.name()`. Có thể cung cấp tool trực tiếp bằng `.tools(...)` hoặc `.toolCallbacks(...)`, hay dùng `.toolNames(...)` để phân giải động. Hãy chọn phạm vi theo từng request khi quyền hoặc mục đích khác nhau, và luôn giữ bước kiểm tra quyền trong dịch vụ nghiệp vụ.

## Tài liệu tham khảo

- [Spring AI 1.0.9 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI 1.0.9 API — ChatClient.Builder](https://docs.spring.io/spring-ai/docs/1.0.9/api/org/springframework/ai/chat/client/ChatClient.Builder.html)
- [Spring AI Upgrade Notes — Tool registration changes in 2.0](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

