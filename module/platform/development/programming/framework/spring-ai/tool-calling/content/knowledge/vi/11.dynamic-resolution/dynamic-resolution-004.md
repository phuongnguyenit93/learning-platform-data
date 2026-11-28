# Phân biệt phân giải theo tên với quảng bá định nghĩa cho mô hình

Trong Spring AI, việc tìm một callback theo tên và việc gửi định nghĩa tool cho mô hình là hai công việc khác nhau. `ToolCallbackResolver` giúp ứng dụng tìm implementation có thể thực thi khi biết tên tool. `ToolDefinition` mô tả tool bằng tên, mô tả và JSON Schema để mô hình hiểu tool có sẵn, khi nào nên gọi và phải tạo đối số theo cấu trúc nào.

Hai công việc này có liên hệ với nhau nhưng không thay thế nhau. Ứng dụng có thể tìm được callback mà chưa đưa định nghĩa của nó vào request cho mô hình. Ngược lại, mô hình có thể nhận một định nghĩa tool nhưng callback tương ứng chưa được đăng ký hoặc không thể phân giải khi thực thi. Hiểu rõ ranh giới này giúp thiết kế luồng tool calling có thể kiểm soát, đặc biệt khi danh mục công cụ thay đổi theo người dùng, tenant hoặc tác vụ.

Bài học trình bày khái niệm chung, sau đó phân biệt API Spring AI 1.0.x với cơ chế resolution fallback trong Spring AI 2.0.

## Sau bài học, bạn có thể

- Giải thích nội dung của `ToolDefinition` và vai trò của nó trong request gửi đến model.
- Phân biệt `ToolCallbackResolver.resolve(toolName)` với việc cung cấp tool definition cho model.
- Mô tả luồng từ chọn tool, quảng bá định nghĩa, nhận tool call đến thực thi callback.
- Hiểu cách `toolNames(...)` của Spring AI 1.0.x phân giải function bean theo tên.
- Hiểu cơ chế resolution fallback của Spring AI 2.0 và vì sao mặc định cơ chế này bị tắt.
- Chọn giữa cung cấp callback tường minh, phân giải động và registry tùy chỉnh.
- Kiểm soát quyền, phạm vi tool và kiểm thử cả hai giai đoạn.

## Hai khái niệm: ToolDefinition và ToolCallbackResolver

### ToolDefinition: định nghĩa được gửi cho model

`ToolDefinition` là hợp đồng mô tả tool mà mô hình nhìn thấy. Nó gồm ba thành phần:

| Thành phần | Ý nghĩa | Model dùng để làm gì |
|---|---|---|
| `name` | Tên định danh duy nhất trong tập tool của request | Chọn tool và đặt tên trong tool call |
| `description` | Mô tả hành động và mục đích | Quyết định khi nào nên gọi tool |
| `inputSchema` | JSON Schema của tham số đầu vào | Tạo đối số JSON đúng cấu trúc |

Ví dụ định nghĩa tool tra cứu thời tiết:

~~~java
ToolDefinition definition = ToolDefinition.builder()
        .name("currentWeather")
        .description("Tra cứu thời tiết hiện tại theo tên thành phố")
        .inputSchema("""
                {
                  "type": "object",
                  "properties": {
                    "location": {
                      "type": "string",
                      "description": "Tên thành phố cần tra cứu"
                    }
                  },
                  "required": ["location"]
                }
                """)
        .build();
~~~

Định nghĩa này là thông tin gửi đến model trong chat request. Nó không tự chứa mã Java để thực thi. Model có thể dựa vào định nghĩa để trả về một tool call có tên `currentWeather` và đối số JSON như:

~~~json
{
  "location": "Da Nang"
}
~~~

Model không đọc Spring bean, không gọi trực tiếp method Java và không truy cập `ApplicationContext`. Model chỉ nhận phần định nghĩa được ứng dụng đưa vào request.

### ToolCallbackResolver: tìm implementation ở phía ứng dụng

`ToolCallbackResolver` là abstraction phía server dùng để tìm `ToolCallback` từ tên tool:

~~~java
public interface ToolCallbackResolver {

    @Nullable
    ToolCallback resolve(String toolName);
}
~~~

Kết quả của `resolve("currentWeather")` là callback có thể thực thi, hoặc `null` nếu resolver không tìm thấy tool tương ứng. Callback cung cấp cả `ToolDefinition` lẫn logic thực thi:

~~~java
public interface ToolCallback {

    ToolDefinition getToolDefinition();

    ToolMetadata getToolMetadata();

    String call(String toolInput);

    String call(String toolInput, ToolContext toolContext);
}
~~~

Resolver không phải nội dung được gửi cho model. Nó là cơ chế nội bộ giúp ứng dụng tìm implementation. Tùy cách cấu hình, resolver có thể tra cứu callback bean, registry nội bộ hoặc một nguồn tool tùy chỉnh.

### Điểm khác nhau cần nhớ

| Câu hỏi | ToolDefinition | ToolCallbackResolver |
|---|---|---|
| Nằm ở đâu? | Trong chat request gửi đến model | Trong ứng dụng Spring |
| Chứa gì? | Tên, mô tả, schema | Quy tắc tìm callback thực thi |
| Đầu vào chính | Được tạo từ tool/callback hoặc định nghĩa tùy chỉnh | Tên tool |
| Kết quả | Thông tin để model quyết định và tạo đối số | Một `ToolCallback` hoặc không tìm thấy |
| Có thực thi nghiệp vụ không? | Không | Không trực tiếp; callback được tìm thấy mới thực thi |
| Có quyết định quyền không? | Không | Không tự cấp quyền; ứng dụng/service phải kiểm tra |

Tên tool xuất hiện trong cả hai phía nhưng có vai trò khác nhau. `ToolDefinition.name()` là tên model dùng khi yêu cầu gọi tool; `resolve(name)` dùng cùng tên đó làm khóa tra cứu callback trong ứng dụng.

## Luồng hoàn chỉnh: từ định nghĩa đến thực thi

Một luồng tool calling điển hình gồm hai giai đoạn: cung cấp khả năng cho model và xử lý yêu cầu gọi tool do model trả về.

~~~mermaid
sequenceDiagram
    participant App as Ứng dụng
    participant Resolver as ToolCallbackResolver
    participant Model as Mô hình
    participant Manager as ToolCallingManager
    participant Callback as ToolCallback
    participant Service as Dịch vụ nghiệp vụ

    App->>Resolver: resolve("currentWeather")
    Resolver-->>App: ToolCallback
    App->>Model: Chat request + ToolDefinition
    Note over Model: Model thấy name, description, inputSchema
    Model-->>App: Tool call: name + JSON arguments
    App->>Manager: Xử lý tool call
    Manager->>Resolver: Tìm callback theo tên (nếu cần)
    Resolver-->>Manager: ToolCallback
    Manager->>Callback: call(toolInput, toolContext)
    Callback->>Service: Gọi nghiệp vụ
    Service-->>Callback: Kết quả
    Callback-->>Manager: Tool result
    Manager-->>Model: Tool result (nếu không returnDirect)
    Model-->>App: Câu trả lời cuối
~~~

Không phải mọi triển khai đều gọi resolver đúng hai lần như sơ đồ khái quát. Callback có thể được resolve và lưu trong danh sách request từ trước, sau đó được sử dụng trực tiếp khi thực thi. Điểm cốt lõi là định nghĩa phải được cung cấp cho model và yêu cầu thực thi phải được ánh xạ đến callback hợp lệ ở phía ứng dụng.

### Giai đoạn 1: chọn và cung cấp định nghĩa

Ứng dụng xác định tool nào phù hợp với tác vụ. Sau đó, ứng dụng cung cấp callback hoặc định nghĩa tương ứng cho model. Với callback, Spring AI lấy `ToolDefinition` từ `getToolDefinition()`. Nếu dùng tên động, cơ chế phân giải có thể tìm callback để lấy definition.

Model cần nhận được ít nhất tên, mô tả và schema để hiểu cách sử dụng tool. Chỉ gửi một chuỗi tên tool mà không có definition/schema sẽ không cung cấp đủ thông tin để model biết tool làm gì và tạo tham số thế nào.

### Giai đoạn 2: xử lý tool call

Khi model trả về tool call, ứng dụng nhận tên tool và JSON arguments. `ToolCallingManager` điều phối việc thực thi. Nó tìm callback phù hợp từ tập callback của request hoặc theo cơ chế resolver được cấu hình, gọi callback với dữ liệu đầu vào và context, rồi xử lý kết quả.

Ứng dụng chịu trách nhiệm kiểm tra đầu vào và quyền. Việc model đã nhìn thấy definition không chứng minh người dùng có quyền truy cập dữ liệu hoặc thực hiện hành động.

## Phân giải theo tên trong Spring AI 1.0.x

Trong Spring AI 1.0.x, `ChatClient` hỗ trợ `toolNames(...)` và `defaultToolNames(...)`. Ứng dụng có thể cung cấp tên tool thay vì truyền trực tiếp `ToolCallback`. Spring AI dùng `ToolCallbackResolver` để tìm callback tương ứng.

Cấu hình mặc định có `DelegatingToolCallbackResolver`, chuyển việc tìm kiếm đến các resolver cụ thể. Hai resolver thường gặp:

| Resolver | Nguồn tìm kiếm | Tên được phân giải |
|---|---|---|
| `SpringBeanToolCallbackResolver` | Spring bean kiểu `Function`, `Supplier`, `Consumer`, `BiFunction` | Tên bean |
| `StaticToolCallbackResolver` | Các bean kiểu `ToolCallback` | `ToolDefinition.name()` |

### Ví dụ function bean được phân giải theo tên

Khai báo một function bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class WeatherToolConfiguration {

    @Bean
    @Description("Tra cứu thời tiết hiện tại theo tên thành phố")
    Function<WeatherRequest, WeatherResponse> currentWeather(
            WeatherService weatherService) {
        return weatherService::getWeather;
    }
}
~~~

Tên bean mặc định là `currentWeather`. Trong Spring AI 1.0.x, có thể cung cấp tên đó cho request:

~~~java
String answer = chatClient.prompt()
        .user("Thời tiết ở Đà Nẵng hiện nay thế nào?")
        .toolNames("currentWeather")
        .call()
        .content();
~~~

Ở phía ứng dụng, `SpringBeanToolCallbackResolver` tìm function bean theo tên và tạo callback phù hợp. Callback cung cấp definition cho model và thực thi function khi tool call được xử lý. Vì vậy, tên `currentWeather` là khóa phân giải ở backend và cũng là tên tool trong definition mà model nhận được.

### Ví dụ ToolCallback bean được phân giải theo definition name

Có thể tạo callback bean tường minh:

~~~java
@Configuration(proxyBeanMethods = false)
public class WeatherCallbackConfiguration {

    @Bean
    ToolCallback currentWeatherCallback(WeatherService weatherService) {
        return FunctionToolCallback
                .builder("currentWeather", weatherService::getWeather)
                .description("Tra cứu thời tiết hiện tại theo tên thành phố")
                .inputType(WeatherRequest.class)
                .build();
    }
}
~~~

Tên bean Spring là `currentWeatherCallback`, nhưng tên tool trong definition là `currentWeather`. Khi dùng `StaticToolCallbackResolver`, tên tra cứu là `ToolDefinition.name()`, tức `currentWeather`.

Ví dụ này cho thấy bean name và tool name có thể khác nhau. Khi thiết kế registry, hãy xác định rõ resolver đang dùng loại tên nào.

### toolNames không chỉ gửi tên cho model

Cách diễn đạt “gửi tên tool cho model” dễ gây hiểu nhầm. Trong Spring AI 1.0.x, `toolNames(...)` là cách ứng dụng yêu cầu framework phân giải các tên đó thành callback. Từ callback, Spring AI có thể lấy `ToolDefinition` để đưa vào request. Model nhận định nghĩa tool, không nhận một lời hứa rằng server có một bean mang tên tương tự.

Nếu tên không resolve được, ứng dụng không thể cung cấp callback hợp lệ để xử lý yêu cầu. Nếu definition không được đưa vào request, model không có thông tin chính thức về schema và mục đích của tool.

## Cung cấp callback trực tiếp: không cần phân giải theo tên

Nếu ứng dụng đã có callback, có thể cung cấp trực tiếp cho `ChatClient`:

~~~java
ToolCallback weatherTool = FunctionToolCallback
        .builder("currentWeather", weatherService::getWeather)
        .description("Tra cứu thời tiết hiện tại theo tên thành phố")
        .inputType(WeatherRequest.class)
        .build();

String answer = chatClient.prompt()
        .user("Thời tiết ở Đà Nẵng hiện nay thế nào?")
        .toolCallbacks(weatherTool)
        .call()
        .content();
~~~

Ở cách này, callback đã có cả definition và logic thực thi. Ứng dụng không cần dùng tên để tìm callback trong registry cho request đó. Spring AI có thể lấy definition từ callback và gửi cho model; khi model yêu cầu gọi tool, callback đã được gắn với request.

Cách cung cấp trực tiếp thường phù hợp khi:

- Tập tool nhỏ và biết trước tại nơi xây dựng request.
- Muốn rõ ràng callback nào được cung cấp cho một tác vụ.
- Muốn tránh phụ thuộc vào tên chuỗi và resolver toàn cục.
- Cần chọn callback theo người dùng hoặc tenant trước khi gửi request.

Với Spring AI 2.x, API phổ biến trên `ChatClient` là `.tools(...)`, nhận object có method `@Tool`, `ToolCallback` hoặc provider phù hợp. Cách đăng ký tường minh này thay thế pattern function bean được phân giải qua `toolNames(...)` của 1.x.

## Spring AI 2.0: resolution fallback không phải quảng bá definition

Spring AI 2.0 thay đổi cách phân giải function bean. `SpringBeanToolCallbackResolver` và API `toolNames(...)` dùng để phân giải các bean `Function`, `Supplier`, `Consumer`, `BiFunction` theo tên đã bị loại bỏ. Function-style tool cần được đăng ký thành `ToolCallback` tường minh, thường bằng `FunctionToolCallback`.

Tuy nhiên, `ToolCallbackResolver` vẫn có vai trò trong cơ chế phân giải callback. Spring AI 2.0 có tùy chọn resolution fallback:

~~~properties
spring.ai.tools.resolution.fallback.enabled=true
~~~

Mặc định thuộc tính này là `false`. Khi bật, nếu model yêu cầu một tool không nằm trong callback list được gắn vào request, `ToolCallingManager` có thể dùng `ToolCallbackResolver` để tìm callback theo tên và thực thi nó.

Đây là cơ chế fallback lúc thực thi. Nó không có nghĩa Spring AI tự động quảng bá mọi tool mà resolver biết tới cho model. Hai việc vẫn tách biệt:

- **Quảng bá definition:** đưa `ToolDefinition` vào request để model biết tool và schema.
- **Resolution fallback:** nếu model trả về một tên tool không có trong callback list của request, backend có thể tìm callback theo tên để thực thi.

Nếu tool chưa được quảng bá, model không có schema chính thức để tạo đối số đúng. Nếu model vẫn trả về tên đó do prompt hoặc do một nguồn thông tin khác, fallback có thể cho phép backend thực thi callback. Đây là lý do cần đặc biệt cẩn trọng với fallback.

### Rủi ro khi bật fallback

Tài liệu Spring AI cảnh báo rằng khi bật fallback, mọi tool có thể truy cập qua resolver đều có khả năng được thực thi nếu model yêu cầu đúng tên, bất kể request đã gắn tool nào. Điều này có thể mở rộng quyền thực thi vượt khỏi tập tool mà ứng dụng định cung cấp cho request.

Không bật fallback chỉ để “làm cho tool tự tìm thấy”. Chỉ cân nhắc khi:

- Resolver chỉ chứa các tool đã được giới hạn theo chính sách.
- Ứng dụng kiểm tra quyền ở callback hoặc service cho mỗi lần thực thi.
- Có kiểm soát rõ ràng tên tool được phép phân giải.
- Các tool có tác động lớn yêu cầu xác nhận và cơ chế chống lặp.
- Có log và kiểm thử cho cả trường hợp tên được resolve và không resolve.

Trong phần lớn ứng dụng, cung cấp callback tường minh cho từng request dễ kiểm soát hơn. Nếu cần registry động, hãy thiết kế resolver như một điểm thực thi có kiểm soát, không xem nó là danh mục công khai an toàn mặc định.

## Ví dụ so sánh hai đường đi

Giả sử ứng dụng có tool tra cứu tài khoản `getAccountSummary`.

**Cách A: quảng bá definition và gắn callback tường minh**

~~~java
ToolCallback accountTool = FunctionToolCallback
        .builder("getAccountSummary", accountService::getSummary)
        .description("Tra cứu thông tin tài khoản mà người dùng hiện tại được phép xem")
        .inputType(AccountLookupRequest.class)
        .build();

chatClient.prompt()
        .user("Cho tôi biết trạng thái tài khoản AC-102")
        .toolCallbacks(accountTool)
        .call()
        .content();
~~~

Callback chứa definition và logic. Definition được cung cấp cho model; callback được gắn với request để thực thi. Không cần name resolver cho đường đi này.

**Cách B: phân giải theo tên trong Spring AI 1.0.x**

~~~java
@Bean
@Description("Tra cứu thông tin tài khoản mà người dùng hiện tại được phép xem")
Function<AccountLookupRequest, AccountSummary> getAccountSummary(
        AccountService accountService) {
    return accountService::getSummary;
}

// Ở nơi gọi ChatClient:
chatClient.prompt()
        .user("Cho tôi biết trạng thái tài khoản AC-102")
        .toolNames("getAccountSummary")
        .call()
        .content();
~~~

Ứng dụng đưa tên bean vào request API. Spring AI dùng resolver để tìm function bean, tạo callback và lấy definition để gửi cho model. Callback thực thi function khi có tool call.

**Cách C: resolution fallback trong Spring AI 2.0**

Trong 2.0, ứng dụng đăng ký callback tường minh trong registry. Nếu bật fallback, model có thể yêu cầu một tool chưa được gắn trực tiếp vào request và resolver có thể tìm callback để thực thi. Nhưng fallback không thay thế việc thiết kế definition mà model cần biết. Nếu model cần dùng tool một cách đáng tin cậy, hãy cung cấp definition qua request.

## Quảng bá definition có đồng nghĩa cấp quyền thực thi?

Không. Đưa một `ToolDefinition` vào request chỉ cho model biết tên, mục đích và schema của tool. Nó không xác thực người dùng và không cấp quyền truy cập dữ liệu. Nếu callback được gắn với request, callback hoặc dịch vụ nghiệp vụ vẫn có thể từ chối thao tác sau khi kiểm tra quyền hoặc yêu cầu xác nhận. Nếu không có callback tương ứng và không có cơ chế resolution fallback, tool call không thể được thực thi thành công.

Một definition đơn lẻ không thực thi được nghiệp vụ. Đừng quảng bá một tool mà ứng dụng không có đường xử lý, vì model có thể yêu cầu hành động không có implementation và làm luồng hội thoại thất bại. Ngược lại, đừng để resolver mở rộng tập tool thực thi vượt khỏi chính sách đã dùng để quyết định definition nào được gửi.

Trong hệ thống có nhiều tenant hoặc nhiều nhóm quyền, nên tạo danh sách callback/definition sau khi xác định ngữ cảnh người dùng. Ví dụ, nhân viên hỗ trợ có thể được xem trạng thái đơn hàng nhưng không được gọi tool hoàn tiền. Việc bỏ definition hoàn tiền khỏi request giới hạn khả năng model nhìn thấy; service hoàn tiền vẫn phải kiểm tra quyền nếu callback có thể được gọi qua đường khác. Nếu dùng fallback, hãy kiểm tra quyền ngay tại callback/service vì tên tool có thể được resolve dù callback không nằm trong danh sách request.

## Kiểm thử riêng hai trách nhiệm

Một test kiểm tra resolver thành công không chứng minh model đã nhận definition. Một test xác nhận definition có trong request cũng không chứng minh callback thực thi đúng. Hãy kiểm tra riêng:

| Kiểm thử | Câu hỏi cần trả lời | Bằng chứng |
|---|---|---|
| Tool definition | Model được cung cấp tên, mô tả và schema nào? | Kiểm tra `ToolDefinition` gắn với request |
| Name resolution | Resolver tìm được callback nào với tên này? | Kiểm tra `resolve(name)` và callback trả về |
| Callback execution | JSON đầu vào được xử lý thế nào? | Gọi callback với fixture và kiểm tra kết quả |
| Request scope | Tool nào thực sự được cung cấp cho request? | Kiểm tra danh sách tool sau khi hợp nhất default/runtime theo version |
| Authorization | Người dùng có được thực hiện thao tác không? | Test quyền trong callback/service với user và tenant khác nhau |
| Resolution fallback | Tool ngoài callback list có được resolve không? | Test fallback tắt và bật, xác minh phạm vi được phép |

Ví dụ kiểm tra callback definition và resolver:

~~~java
@Test
void shouldExposeDefinitionAndResolveCallback() {
    ToolCallback callback = toolCallbackResolver.resolve("currentWeather");

    assertThat(callback).isNotNull();
    assertThat(callback.getToolDefinition().name())
            .isEqualTo("currentWeather");
    assertThat(callback.getToolDefinition().description())
            .contains("thời tiết");
    assertThat(callback.getToolDefinition().inputSchema())
            .contains("location");
}
~~~

Đây là ví dụ minh họa; test context cần cấu hình resolver và callback bean tương ứng. Để kiểm tra definition thực sự được gửi tới model, có thể dùng mock ChatModel hoặc mock API client và xác minh tool definitions trong request. Để kiểm tra thực thi, gọi callback riêng với JSON fixture hoặc chạy test qua `ToolCallingManager`.

## Những lỗi thường gặp

- **Coi tên tool là definition:** tên không cung cấp mô tả và schema. Model cần definition đầy đủ để biết khi nào và cách gọi tool.
- **Coi resolver là nơi quảng bá tool:** resolver tra cứu callback ở backend; nó không phải nội dung prompt tự động được gửi đến model.
- **Coi ToolDefinition là implementation:** definition chỉ mô tả; ứng dụng cần callback thực thi tương ứng.
- **Cho rằng resolver tìm thấy nghĩa là người dùng được phép:** resolver chỉ tìm implementation. Quyền phải được kiểm tra trong ứng dụng/service.
- **Bật fallback để thay cho việc cung cấp tool:** fallback của 2.0 là cơ chế thực thi dự phòng, không phải cách quảng bá schema.
- **Để fallback nhìn thấy toàn bộ callback bean:** model có thể yêu cầu tool ngoài tập dự định của request. Giới hạn resolver và kiểm tra quyền.
- **Dùng toolNames của 1.x trong Spring AI 2.0:** API này và SpringBeanToolCallbackResolver đã bị loại bỏ. Chuyển function bean thành ToolCallback rõ ràng.
- **Chỉ test resolve hoặc chỉ test schema:** hai kiểm thử xác minh hai trách nhiệm khác nhau. Kiểm tra cả definition, resolver và callback execution.

## Checklist trước khi triển khai phân giải động

- [ ] Đã xác định phiên bản Spring AI và dùng API tương ứng.
- [ ] Mỗi tool được quảng bá có tên, mô tả và input schema rõ ràng.
- [ ] Tập definition được chọn theo tác vụ, user và tenant.
- [ ] Mỗi tool definition có callback thực thi tương ứng.
- [ ] Resolver chỉ tra cứu các callback mà ứng dụng cho phép.
- [ ] Đã phân biệt bean name với `ToolDefinition.name()`.
- [ ] Không nhầm phân giải theo tên với quảng bá definition cho model.
- [ ] Nếu dùng resolution fallback 2.0, đã đánh giá rủi ro và giới hạn resolver.
- [ ] Dịch vụ nghiệp vụ vẫn kiểm tra quyền ở thời điểm thực thi.
- [ ] Có test cho definition, resolution, execution, request scope và authorization.

## Ghi nhớ khi thiết kế

`ToolDefinition` trả lời câu hỏi “model được biết những tool nào và phải gọi chúng bằng dữ liệu nào?”. `ToolCallbackResolver` trả lời câu hỏi “ứng dụng tìm implementation nào khi nhận được tên tool này?”. Model cần definition để lựa chọn và tạo đối số; backend cần callback để thực thi.

Trong Spring AI 1.0.x, `toolNames(...)` yêu cầu framework phân giải tên thành callback và dùng definition của callback trong request. Trong Spring AI 2.0, pattern function bean theo tên đã bị loại bỏ; resolution fallback mặc định tắt và chỉ là cơ chế tìm callback lúc thực thi. Hãy quảng bá đúng definition, gắn callback phù hợp với request và giữ kiểm tra quyền trong dịch vụ nghiệp vụ.

## Tài liệu tham khảo

- [Spring AI 1.0 Reference — Tool Calling](https://docs.spring.io/spring-ai/reference/1.0/api/tools.html)
- [Spring AI Current Reference — Tool Calling và Tool Resolution](https://docs.spring.io/spring-ai/reference/api/tools.html)
- [Spring AI Upgrade Notes — Tool Calling 1.x to 2.0](https://docs.spring.io/spring-ai/reference/upgrade-notes.html)

