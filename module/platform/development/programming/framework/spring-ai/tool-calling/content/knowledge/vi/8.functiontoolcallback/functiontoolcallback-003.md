# Tạo FunctionToolCallback từ lambda hoặc method reference

Spring AI cho phép biến một hàm Java thành tool mà không cần tạo method có annotation `@Tool`. Với `FunctionToolCallback`, bạn có thể cung cấp trực tiếp một đối tượng thuộc nhóm functional interface như `Function`, `Supplier`, `Consumer` hoặc `BiFunction`. Đối tượng đó có thể được viết bằng lambda hoặc method reference.

Cách làm này hữu ích khi logic đã nằm trong service hiện có, khi muốn tạo tool tại thời điểm cấu hình, hoặc khi cần ghép một hàm thuần túy thành callback. Spring AI đóng gói hàm cùng tên tool, mô tả và schema đầu vào thành một `ToolCallback`. Khi model yêu cầu gọi tool, ứng dụng giải mã JSON theo kiểu đầu vào, gọi hàm đã đăng ký rồi chuyển kết quả thành nội dung trả về cho model.

## Sau bài học, bạn có thể

- Phân biệt `FunctionToolCallback` với `@Tool` và `MethodToolCallback`.
- Tạo callback từ lambda và method reference.
- Chọn `Function`, `Supplier`, `Consumer` hoặc `BiFunction` theo chữ ký hàm.
- Khai báo tên, mô tả, kiểu đầu vào và schema cho callback.
- Đăng ký callback trực tiếp với `ChatClient` hoặc cung cấp nó như Spring bean.
- Dùng `ToolContext` để nhận ngữ cảnh do ứng dụng cung cấp.
- Nhận biết giới hạn kiểu dữ liệu và kiểm thử callback độc lập với model.

## FunctionToolCallback nằm ở đâu trong kiến trúc?

Spring AI cung cấp `ToolCallback` như hợp đồng chung của một tool. Callback mang hai phần:

- **ToolDefinition:** tên, mô tả và JSON Schema mà model nhìn thấy để quyết định có gọi tool hay không và phải tạo đối số như thế nào.
- **Logic thực thi:** hàm Java được gọi khi ứng dụng xử lý yêu cầu tool call.

`FunctionToolCallback` là một implementation của `ToolCallback`, chuyên đóng gói các functional interface. Nó cho phép tái sử dụng service hoặc hàm Java có sẵn mà không cần viết một class riêng chỉ để đánh dấu method.

~~~mermaid
flowchart TD
    A[Lambda hoặc method reference] --> B[FunctionToolCallback.builder]
    C[Tool name, description, inputType] --> B
    B --> D[FunctionToolCallback]
    D --> E[ToolDefinition và JSON Schema]
    E --> F[ChatClient gửi tool definition cho model]
    F --> G[Model yêu cầu tool call với JSON input]
    G --> H[ToolCallback giải mã input và gọi hàm]
    H --> I[Kết quả được chuyển thành String]
    I --> J[Ứng dụng gửi tool result về model]
~~~

Mô hình chỉ tạo yêu cầu gọi tool và đối số. Ứng dụng vẫn thực thi hàm, kiểm tra quyền và xử lý kết quả. Việc dùng lambda hoặc method reference không thay đổi ranh giới trách nhiệm này.

## Tạo callback từ Function

`Function<I, O>` nhận một đối tượng đầu vào kiểu `I` và trả về kết quả kiểu `O`. Đây là lựa chọn phổ biến khi tool cần nhận một DTO và trả về một DTO khác.

Giả sử ứng dụng đã có service tra cứu thời tiết:

~~~java
public record WeatherRequest(
        @ToolParam(description = "Tên thành phố hoặc địa điểm cần tra cứu")
        String location,
        @ToolParam(description = "Đơn vị nhiệt độ: CELSIUS hoặc FAHRENHEIT")
        TemperatureUnit unit) {
}

public record WeatherResponse(
        String location,
        double temperature,
        TemperatureUnit unit,
        String condition) {
}

public enum TemperatureUnit {
    CELSIUS,
    FAHRENHEIT
}

public class WeatherService {

    private final WeatherProvider weatherProvider;

    public WeatherService(WeatherProvider weatherProvider) {
        this.weatherProvider = weatherProvider;
    }

    public WeatherResponse getWeather(WeatherRequest request) {
        // Gọi nguồn dữ liệu thời tiết và trả về kết quả đã chuẩn hóa.
        return weatherProvider.fetch(request);
    }
}
~~~

Các kiểu đầu vào và đầu ra được công bố cho function tool cần là kiểu public và có thể serialize thành JSON. Trong dự án thật, mỗi public top-level record/class đặt trong file Java riêng tương ứng.

### Dùng lambda

Có thể viết logic trực tiếp bằng lambda:

~~~java
Function<WeatherRequest, WeatherResponse> weatherFunction =
        request -> weatherService.getWeather(request);

ToolCallback weatherTool = FunctionToolCallback
        .builder("currentWeather", weatherFunction)
        .description("Tra cứu thời tiết hiện tại tại một địa điểm và trả về nhiệt độ cùng trạng thái thời tiết")
        .inputType(WeatherRequest.class)
        .build();
~~~

Trong đó:

- `currentWeather` là tên duy nhất của tool trong tập tool được gửi cho một request.
- `weatherFunction` là logic thực thi.
- `description(...)` giúp model hiểu khi nào và vì sao nên gọi tool.
- `inputType(WeatherRequest.class)` cho Spring AI biết kiểu đầu vào để sinh JSON Schema.
- `build()` tạo đối tượng callback có thể đăng ký với `ChatClient`.

Khai báo biến có kiểu `Function<WeatherRequest, WeatherResponse>` trước khi truyền vào builder cũng giúp trình biên dịch hiểu rõ overload cần dùng. Điều này hữu ích vì `FunctionToolCallback.builder` có nhiều overload nhận các functional interface khác nhau.

### Dùng method reference

Nếu service đã có method tương thích với chữ ký `Function<I, O>`, có thể truyền method reference trực tiếp:

~~~java
Function<WeatherRequest, WeatherResponse> weatherFunction =
        weatherService::getWeather;

ToolCallback weatherTool = FunctionToolCallback
        .builder("currentWeather", weatherFunction)
        .description("Tra cứu thời tiết hiện tại tại một địa điểm")
        .inputType(WeatherRequest.class)
        .build();
~~~

`weatherService::getWeather` là bound method reference: nó giữ tham chiếu tới instance `weatherService` và gọi method `getWeather` khi function được thực thi. Không cần viết lại một lambda chỉ để chuyển tiếp cùng tham số.

Cũng có thể dùng static method reference:

~~~java
Function<WeatherRequest, WeatherResponse> weatherFunction =
        WeatherFunctions::getWeather;
~~~

Trong trường hợp này, `getWeather` là static method có chữ ký nhận `WeatherRequest` và trả về `WeatherResponse`. Cả lambda, bound method reference và static method reference đều được chuyển thành đối tượng `Function` trước khi đưa vào `FunctionToolCallback`.

## Tạo callback từ các functional interface khác

Spring AI hỗ trợ bốn dạng hàm cho function-based tool. Chọn dạng phù hợp với số lượng đầu vào và việc có cần kết quả trả về hay không.

| Functional interface | Đầu vào | Kết quả | Trường hợp sử dụng |
|---|---|---|---|
| `Function<I, O>` | Một object `I` | `O` | Tra cứu, tính toán hoặc chuyển đổi dữ liệu |
| `BiFunction<I, ToolContext, O>` | Object `I` và ngữ cảnh | `O` | Tool cần dữ liệu ngữ cảnh do ứng dụng cung cấp |
| `Consumer<I>` | Một object `I` | `Void` | Thực hiện thao tác như tạo yêu cầu hoặc ghi nhận sự kiện |
| `Supplier<O>` | Không có đầu vào | `O` | Lấy trạng thái hoặc thông tin không cần tham số |

### Supplier: tool không nhận tham số

`Supplier<O>` phù hợp khi tool không cần dữ liệu do model tạo ra, ví dụ đọc trạng thái hệ thống hiện tại:

~~~java
Supplier<SystemHealth> healthSupplier = healthService::currentHealth;

ToolCallback healthTool = FunctionToolCallback
        .builder("getSystemHealth", healthSupplier)
        .description("Lấy trạng thái tổng quan hiện tại của hệ thống")
        .inputType(Void.class)
        .build();
~~~

Với `Supplier`, đầu vào là `Void` vì model không cần tạo object JSON có trường dữ liệu. Kết quả `SystemHealth` cần là kiểu có thể serialize để gửi lại cho model.

Không dùng Supplier cho một thao tác cần tham số mà chỉ vì muốn bỏ schema. Nếu model phải chọn một tài nguyên, mã định danh hoặc bộ lọc, hãy mô hình hóa đầu vào bằng một request DTO.

### Consumer: tool thực hiện thao tác không cần kết quả

`Consumer<I>` nhận một object và không trả về giá trị nghiệp vụ:

~~~java
public record CreateTicketRequest(
        String subject,
        String description,
        String priority) {
}

Consumer<CreateTicketRequest> createTicket =
        ticketService::createTicket;

ToolCallback createTicketTool = FunctionToolCallback
        .builder("createSupportTicket", createTicket)
        .description("Tạo yêu cầu hỗ trợ mới với tiêu đề, mô tả và mức độ ưu tiên")
        .inputType(CreateTicketRequest.class)
        .build();
~~~

Consumer phù hợp với thao tác có hiệu ứng phụ. Vì không có kết quả nghiệp vụ, callback không trả một object kết quả cho model. Nếu model cần biết mã ticket mới tạo hoặc trạng thái xử lý, nên dùng `Function<CreateTicketRequest, TicketCreated>` để trả một DTO kết quả rõ ràng.

Với thao tác ghi dữ liệu, ứng dụng phải xác thực quyền, kiểm tra dữ liệu và xử lý tính lặp an toàn. Một tool call có thể được yêu cầu lại do retry hoặc do model tiếp tục hội thoại; cần có idempotency key hoặc cơ chế chống tạo bản ghi trùng khi nghiệp vụ yêu cầu.

### BiFunction: nhận ToolContext

`BiFunction<I, ToolContext, O>` nhận thêm `ToolContext` bên cạnh đối số JSON. Context được ứng dụng cung cấp khi thực thi tool, không phải trường JSON do model tự khai báo.

~~~java
public record AccountLookupRequest(String accountId) {
}

public record AccountSummary(
        String accountId,
        String displayName,
        String status) {
}

BiFunction<AccountLookupRequest, ToolContext, AccountSummary> accountLookup =
        (request, toolContext) -> {
            String tenantId = (String) toolContext.getContext().get("tenantId");

            return accountService.getSummaryForTenant(
                    request.accountId(),
                    tenantId
            );
        };

ToolCallback accountTool = FunctionToolCallback
        .builder("getAccountSummary", accountLookup)
        .description("Tra cứu thông tin tóm tắt của tài khoản trong tenant hiện tại")
        .inputType(AccountLookupRequest.class)
        .build();
~~~

`ToolContext` hữu ích cho tenant, user ID đã xác thực, locale hoặc correlation ID. Ứng dụng phải tạo context từ nguồn đáng tin cậy. Không lấy danh tính hay quyền truy cập từ đối số mà model tạo ra. Dịch vụ nghiệp vụ vẫn phải kiểm tra người dùng hiện tại có được xem tài khoản hay không.

## inputType và JSON Schema

Builder cần biết kiểu dữ liệu đầu vào để sinh schema. Với `Function`, `Consumer` và `BiFunction`, kiểu đầu vào thường là một DTO hoặc record. Với `Supplier`, đầu vào là `Void`.

~~~java
FunctionToolCallback.builder("currentWeather", weatherService::getWeather)
        .description("Tra cứu thời tiết theo địa điểm")
        .inputType(WeatherRequest.class)
        .build();
~~~

Spring AI dùng `inputType` để tạo JSON Schema. Model nhìn thấy tên property, kiểu dữ liệu và metadata được hỗ trợ từ các annotation trên kiểu dữ liệu, chẳng hạn `@ToolParam`, Jackson hoặc Swagger. Vì vậy, request DTO nên:

- Là kiểu public.
- Có cấu trúc dữ liệu rõ ràng và có thể deserialize.
- Dùng tên trường có ý nghĩa.
- Mô tả định dạng, đơn vị và miền giá trị của từng trường.
- Chỉ đánh dấu trường optional khi ứng dụng thật sự cho phép bỏ qua.

Nếu cần schema khác với schema được sinh từ kiểu đầu vào, builder có thể nhận `inputSchema(...)` để cung cấp JSON Schema tường minh. Khi dùng cách này, schema phải khớp với kiểu dữ liệu và logic function; ứng dụng vẫn cần validation ở phía server.

Đối với kiểu generic, builder hỗ trợ truyền `ParameterizedTypeReference` vào `inputType(...)` để giữ thông tin kiểu khi Java type erasure làm mất tham số generic. Tuy nhiên, FunctionToolCallback vẫn có các giới hạn về kiểu dữ liệu đầu vào và đầu ra; không phải mọi kiểu generic đều được hỗ trợ.

## Đăng ký FunctionToolCallback với ChatClient

Sau khi tạo callback, có thể truyền trực tiếp vào request của `ChatClient`. Trong Spring AI 1.0, dùng `toolCallbacks(...)` cho callback đã tạo:

~~~java
String answer = ChatClient.create(chatModel)
        .prompt()
        .user("Thời tiết tại Đà Nẵng hiện nay thế nào?")
        .toolCallbacks(weatherTool)
        .call()
        .content();
~~~

Tool chỉ có hiệu lực với request này. Khi model yêu cầu gọi `currentWeather`, Spring AI tìm callback tương ứng, chuyển JSON đầu vào thành `WeatherRequest`, gọi function và gửi kết quả trở lại luồng hội thoại.

Nếu muốn tái sử dụng callback trong nhiều request, có thể khai báo nó thành Spring bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class WeatherToolConfiguration {

    @Bean
    ToolCallback currentWeatherTool(WeatherService weatherService) {
        return FunctionToolCallback
                .builder("currentWeather", weatherService::getWeather)
                .description("Tra cứu thời tiết hiện tại tại một địa điểm")
                .inputType(WeatherRequest.class)
                .build();
    }
}
~~~

Sau đó inject callback vào thành phần tạo hội thoại:

~~~java
@Service
public class WeatherAssistant {

    private final ChatClient chatClient;
    private final ToolCallback currentWeatherTool;

    public WeatherAssistant(
            ChatModel chatModel,
            ToolCallback currentWeatherTool) {
        this.chatClient = ChatClient.create(chatModel);
        this.currentWeatherTool = currentWeatherTool;
    }

    public String ask(String question) {
        return chatClient.prompt()
                .user(question)
                .toolCallbacks(currentWeatherTool)
                .call()
                .content();
    }
}
~~~

Đăng ký bean giúp Spring quản lý vòng đời callback và dependency được inject vào function. Khi dùng nhiều callback, có thể inject danh sách hoặc truyền tập callback phù hợp cho từng request. Chỉ cung cấp những tool cần thiết cho tác vụ hiện tại.

## Tùy chỉnh mô tả, schema và kết quả

Một callback cần tên duy nhất trong tập tool được cung cấp cho model. Tên nên mô tả hành động, dùng định dạng ổn định và tránh thay đổi tùy tiện vì model sẽ tham chiếu đến tên này trong yêu cầu tool call.

Mô tả tool cần nói rõ:

- Tool thực hiện hành động gì.
- Khi nào nên dùng tool.
- Dữ liệu đầu vào đại diện cho điều gì.
- Các giới hạn quan trọng như đơn vị, phạm vi hoặc điều kiện.

Builder hỗ trợ các cấu hình chính:

- `description(...)`: mô tả mục đích tool.
- `inputType(...)`: kiểu dữ liệu đầu vào để sinh schema.
- `inputSchema(...)`: schema JSON tường minh nếu cần.
- `toolMetadata(...)`: metadata điều khiển cách xử lý kết quả, ví dụ `returnDirect`.
- `toolCallResultConverter(...)`: converter tùy chỉnh để chuyển kết quả thành chuỗi gửi về model.

Mặc định Spring AI dùng converter để serialize kết quả function thành chuỗi. Nếu trả về DTO, hãy giữ cấu trúc kết quả nhỏ, rõ nghĩa và không chứa dữ liệu nhạy cảm không cần thiết. Một kết quả có cấu trúc giúp model diễn giải đúng hơn và giúp ứng dụng kiểm thử dễ hơn.

Ví dụ cấu hình trả kết quả trực tiếp cho caller:

~~~java
ToolMetadata metadata = ToolMetadata.builder()
        .returnDirect(true)
        .build();

ToolCallback weatherTool = FunctionToolCallback
        .builder("currentWeather", weatherService::getWeather)
        .description("Tra cứu thời tiết hiện tại tại một địa điểm")
        .inputType(WeatherRequest.class)
        .toolMetadata(metadata)
        .build();
~~~

Mặc định tool result được gửi lại cho model để model tạo câu trả lời cuối. Với `returnDirect(true)`, kết quả được trả trực tiếp cho caller theo cơ chế điều phối của Spring AI. Chỉ bật khi luồng ứng dụng thực sự muốn kết thúc vòng suy luận tại kết quả tool.

## Giới hạn kiểu dữ liệu của FunctionToolCallback

Trong Spring AI 1.0, input và output của function tool phải là `Void` hoặc POJO có thể serialize. Function và các kiểu input/output cần là public. Các kiểu sau hiện không được hỗ trợ làm input hoặc output của function tool:

- Kiểu primitive trực tiếp như `int`, `long`, `boolean`; hãy bọc trong DTO hoặc dùng kiểu wrapper phù hợp.
- `Optional`.
- Các kiểu collection như `List`, `Map`, array hoặc `Set`.
- Kiểu bất đồng bộ như `CompletableFuture` và `Future`.
- Kiểu reactive như `Mono`, `Flux` và `Flow`.

Ví dụ, không khai báo:

~~~java
Function<String, List<Product>> searchProducts;
~~~

Thay vào đó, bọc đầu vào và đầu ra bằng public DTO:

~~~java
public record ProductSearchRequest(String keyword, Integer limit) {
}

public record ProductSearchResponse(List<Product> products) {
}

Function<ProductSearchRequest, ProductSearchResponse> searchProducts =
        request -> productService.search(request);
~~~

Cách bọc này giúp function có hợp đồng dữ liệu rõ ràng và có thể sinh schema phù hợp. Nếu use case cần collection hoặc primitive trực tiếp làm tham số/giá trị trả về, method-based tool qua `@Tool` hoặc `MethodToolCallback` có thể phù hợp hơn.

## Khi nào nên dùng lambda, method reference hoặc @Tool?

| Cách khai báo | Phù hợp khi | Ưu điểm |
|---|---|---|
| Lambda | Cần viết logic ngắn tại nơi cấu hình hoặc kết hợp nhiều bước nhỏ | Dễ tùy biến và đóng gói logic |
| Bound method reference | Service đã có method đúng chữ ký | Tái sử dụng method, ít mã chuyển tiếp |
| Static method reference | Logic tiện ích không cần instance | Không cần giữ object service |
| `@Tool` | Muốn đánh dấu trực tiếp method do mình quản lý | Dễ đọc, gắn schema với method |
| `MethodToolCallback` | Cần tạo callback từ `java.lang.reflect.Method` | Kiểm soát method và object tường minh |
| `FunctionToolCallback` | Muốn dùng functional interface, lambda hoặc method reference | Tạo tool từ logic hàm sẵn có |

Hãy dùng lambda khi logic thực sự ngắn và thuộc riêng cấu hình tool. Nếu logic đã có trong service, method reference thường giúp tránh lặp lại. Nếu method có nhiều dependency, hãy để service được Spring quản lý rồi truyền bound method reference của service đó. Nếu method cần schema tham số phong phú, primitive hoặc collection, hãy cân nhắc method-based tool.

## Kiểm thử FunctionToolCallback

Không cần gọi model thật để kiểm tra function. Có thể kiểm thử function như một hàm Java, sau đó kiểm tra callback có tên, mô tả và schema như mong đợi.

Ví dụ unit test cho logic service:

~~~java
@Test
void shouldReturnWeatherForRequestedLocation() {
    WeatherRequest request =
            new WeatherRequest("Da Nang", TemperatureUnit.CELSIUS);

    WeatherResponse response = weatherService.getWeather(request);

    assertThat(response.location()).isEqualTo("Da Nang");
    assertThat(response.unit()).isEqualTo(TemperatureUnit.CELSIUS);
}
~~~

Có thể kiểm tra metadata callback:

~~~java
@Test
void shouldExposeToolDefinition() {
    ToolCallback callback = FunctionToolCallback
            .builder("currentWeather", weatherService::getWeather)
            .description("Tra cứu thời tiết hiện tại tại một địa điểm")
            .inputType(WeatherRequest.class)
            .build();

    ToolDefinition definition = callback.getToolDefinition();

    assertThat(definition.name()).isEqualTo("currentWeather");
    assertThat(definition.description())
            .contains("Tra cứu thời tiết");
    assertThat(definition.inputSchema()).contains("location");
}
~~~

Một nhóm kiểm thử đầy đủ nên bao gồm:

- Đầu vào hợp lệ và kết quả function mong đợi.
- Thiếu trường bắt buộc, sai kiểu hoặc giá trị ngoài phạm vi.
- Callback được tạo đúng tên và mô tả.
- Schema được sinh từ đúng `inputType`.
- Function ném lỗi và lớp điều phối xử lý lỗi theo chính sách.
- `ToolContext` cung cấp đúng tenant hoặc danh tính từ ứng dụng.
- Tool không thể truy cập dữ liệu ngoài phạm vi quyền của người dùng.
- Callback không tạo tác dụng phụ trùng lặp khi request bị retry.

Integration test với model thật có thể xác minh model chọn tool và tạo đối số phù hợp. Tuy nhiên, unit test function và test callback vẫn cần độc lập để phân biệt lỗi nghiệp vụ với lỗi do model chọn tool hoặc sinh JSON.

## Những lỗi thường gặp

- **Quên `inputType(...)`:** builder cần kiểu đầu vào để sinh schema. Khai báo rõ kiểu DTO hoặc `Void.class` cho tool không có input.
- **Dùng primitive hoặc collection trực tiếp:** function tool trong Spring AI 1.0 yêu cầu `Void` hoặc POJO có thể serialize. Hãy bọc dữ liệu vào DTO.
- **Lambda không rõ kiểu:** builder có nhiều overload. Gán lambda vào biến có kiểu `Function`, `Consumer`, `Supplier` hoặc `BiFunction` trước khi truyền.
- **Mô tả tool quá ngắn:** model có thể chọn sai hoặc không chọn tool. Viết mô tả về hành động, phạm vi và điều kiện sử dụng.
- **Dùng method reference sai chữ ký:** kiểu tham số và kết quả của method phải tương thích với functional interface đã chọn.
- **Trả về object quá lớn:** model nhận nhiều dữ liệu không cần thiết. Tạo DTO kết quả nhỏ và có cấu trúc.
- **Đưa quyền vào input DTO:** model có thể tạo hoặc sửa userId, tenantId. Lấy danh tính từ ngữ cảnh do ứng dụng xác thực.
- **Dùng Consumer cho thao tác cần xác nhận kết quả:** Consumer không có kết quả nghiệp vụ. Dùng Function nếu cần trả mã định danh hoặc trạng thái.
- **Đăng ký quá nhiều tool mặc định:** tool có thể xuất hiện trong request không liên quan. Chọn callback theo từng tác vụ và kiểm tra quyền ở backend.

## Checklist trước khi đăng ký tool

- [ ] Tên tool duy nhất trong tập tool của request.
- [ ] Mô tả nói rõ hành động và khi nào nên dùng.
- [ ] Functional interface khớp chữ ký lambda hoặc method reference.
- [ ] `inputType` được khai báo và là kiểu được hỗ trợ.
- [ ] Input/output là `Void` hoặc POJO public có thể serialize.
- [ ] Schema thể hiện đúng trường bắt buộc, tùy chọn và định dạng.
- [ ] Function gọi service nghiệp vụ, không chứa logic quyền bị bỏ qua.
- [ ] Dữ liệu nhạy cảm được lấy từ principal hoặc ToolContext đáng tin cậy.
- [ ] Kết quả trả về nhỏ, có cấu trúc và không lộ secret.
- [ ] Có unit test cho function và test cho ToolDefinition/schema.

## Ghi nhớ khi thiết kế

`FunctionToolCallback` biến một functional interface thành tool có định nghĩa và logic thực thi. Với `Function`, `Consumer`, `Supplier` và `BiFunction`, builder nhận tên, function, mô tả và kiểu đầu vào để sinh JSON Schema. Lambda phù hợp khi cần ghép logic tại chỗ; method reference phù hợp khi muốn tái sử dụng method đã có trong service.

Hãy ưu tiên DTO public có thể serialize, mô tả rõ mục đích tool, kiểm tra dữ liệu và quyền ở phía ứng dụng, rồi đăng ký callback theo đúng phạm vi request. Khi làm được điều đó, function hiện có có thể trở thành tool Spring AI mà không phải thay đổi trách nhiệm nghiệp vụ của nó.

## Tài liệu tham khảo

- [Spring AI 1.0 Reference — Functions as Tools](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html#_functions_as_tools)
- [Spring AI 1.0.1 API — FunctionToolCallback](https://docs.spring.io/spring-ai/docs/1.0.1/api/org/springframework/ai/tool/function/FunctionToolCallback.html)
- [Spring AI 1.0.1 API — FunctionToolCallback.Builder](https://docs.spring.io/spring-ai/docs/1.0.1/api/org/springframework/ai/tool/function/FunctionToolCallback.Builder.html)

