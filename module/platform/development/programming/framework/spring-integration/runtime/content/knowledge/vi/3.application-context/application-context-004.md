# Bean name, managed name và định danh runtime

Trong Spring Integration, một thành phần có thể được nhận diện bằng nhiều tên tùy nơi ta quan sát nó. Spring ApplicationContext dùng **bean name** để đăng ký và tra cứu object. Spring Integration còn có tên của component, endpoint và channel để mô tả cấu trúc message flow. Lớp quản trị runtime có thể công bố tên phục vụ metrics và vận hành. Trong khi đó, mỗi message lại có `id` và có thể có `correlationId` riêng.

Các định danh này liên quan với nhau nhưng không đồng nghĩa. Một `IntegrationFlow` có thể mang tên bean `ordersFlow`, chứa endpoint có ID `orders.persist`, đọc từ channel `orders.input`, và xử lý message có ID riêng. Khi chẩn đoán lỗi hoặc đọc runtime graph, cần biết tên nào thuộc ApplicationContext, tên nào thuộc cấu trúc Integration và tên nào chỉ thuộc một message cụ thể.

## 1. Những lớp định danh cần phân biệt

| Định danh | Phạm vi | Dùng để làm gì? | Ví dụ |
|---|---|---|---|
| Bean name | Spring `BeanFactory` / `ApplicationContext` | Đăng ký, tra cứu và inject một bean | `ordersInput`, `ordersFlow` |
| Bean alias | Spring `BeanFactory` | Tên bổ sung trỏ đến cùng một bean | `ordersInbound` là alias của `ordersInput` |
| Integration component name | Một component của Spring Integration | Nhận diện channel, endpoint hoặc component trong cấu trúc Integration | `orders.persist` |
| Endpoint ID | Một endpoint cụ thể | Đặt tên có chủ đích cho endpoint để quản trị và chẩn đoán | `orders.persist` |
| Channel name | Một `MessageChannel` trong context | Chỉ ra điểm nhận/gửi message trong flow | `orders.input` |
| Flow bean name | Spring `ApplicationContext` | Nhận diện bean mô tả flow được khai báo bằng `@Bean` | `ordersFlow` |
| Flow registration ID | `IntegrationFlowContext` | Nhận diện một flow được đăng ký động | `tenantAOrders` |
| Managed name / managed type | Bề mặt quản trị của component có hỗ trợ management | Gắn component với thông tin quản trị và metrics | Tên/loại component được công bố cho management |
| Message ID / correlation ID | Một message hoặc nhóm message | Theo dõi message đơn lẻ hoặc các message liên quan | `MessageHeaders.ID`, `correlationId` |

Một chuỗi có thể được dùng làm tên ở nhiều phạm vi, nhưng việc trùng chuỗi không làm cho các định danh trở thành một. Ví dụ `orders.input` có thể là tên bean của channel và cũng là tên mà endpoint tham chiếu khi cấu hình. Endpoint vẫn là một component khác với channel đó.

## 2. Bean name trong Spring ApplicationContext

Bean name là khóa mà Spring dùng để đăng ký bean trong `BeanFactory`. Đây là tên thường được sử dụng khi tra cứu bean theo tên, tham chiếu bean trong cấu hình hoặc phân giải một channel theo tên.

Spring có thể tạo bean name theo quy ước:

- Với class có `@Component`, `@Service`, `@Repository` hoặc stereotype tương tự, tên mặc định thường là tên class viết thường chữ đầu, ví dụ `OrderHandler` thành `orderHandler`.
- Với phương thức `@Bean`, tên mặc định là tên phương thức, ví dụ `ordersInput()` tạo bean tên `ordersInput`.
- Có thể đặt tên rõ ràng bằng thuộc tính `value`/`name` của stereotype hoặc thuộc tính `name` của `@Bean`.

Ví dụ khai báo channel và handler:

```java
@Configuration
@EnableIntegration
public class OrderIntegrationConfiguration {

    @Bean
    public MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public OrderHandler orderHandler() {
        return new OrderHandler();
    }
}
```

Trong cấu hình trên, ApplicationContext quản lý hai bean có tên `ordersInput` và `orderHandler`. Có thể tra cứu channel theo tên:

```java
MessageChannel input = context.getBean("ordersInput", MessageChannel.class);
OrderHandler handler = context.getBean("orderHandler", OrderHandler.class);
```

Tên bean cần duy nhất trong phạm vi registry tương ứng. Nếu hai cấu hình cùng đăng ký một tên, kết quả phụ thuộc chính sách đăng ký bean và cấu hình cho phép override hay không; trong môi trường không cho phép ghi đè, quá trình khởi tạo context có thể thất bại. Vì vậy, nên chọn tên phản ánh chức năng và phạm vi của bean, đặc biệt với các module được ghép vào cùng một ApplicationContext.

### Alias không tạo ra bean thứ hai

Một bean có thể có nhiều alias:

```java
@Bean(name = {"ordersInput", "ordersInbound"})
public MessageChannel ordersInput() {
    return new DirectChannel();
}
```

`ordersInput` là tên bean chính theo khai báo này; `ordersInbound` là alias. Hai tên cùng phân giải đến một object được quản lý, không phải hai channel độc lập. Có thể kiểm tra alias bằng `context.getAliases("ordersInput")`.

Alias hữu ích khi cần giữ tên tương thích trong lúc đổi quy ước đặt tên. Tuy nhiên, không nên dùng alias như thể đó là một endpoint hoặc một instance mới. Nếu hai phần của ứng dụng cần hai channel độc lập, phải khai báo hai bean channel riêng.

### Bean name, qualifier và kiểu bean

`@Qualifier` giúp Spring chọn bean phù hợp khi inject một dependency, thường kết hợp với type. Giá trị qualifier đôi khi trùng bean name, nhưng qualifier là thông tin chọn dependency; nó không tự tạo alias và cũng không đổi tên bean.

```java
@Bean
@Qualifier("priorityOrders")
public MessageChannel priorityOrdersChannel() {
    return new DirectChannel();
}
```

Khi cần kiểm tra chính xác object nào được inject, hãy xem cả kiểu bean, bean name và qualifier tại điểm cấu hình. Đừng kết luận rằng hai bean là một chỉ vì chúng có cùng kiểu hoặc cùng qualifier.

## 3. Tên của IntegrationFlow và các component được tạo từ flow

Một `IntegrationFlow` khai báo cách message đi qua channel và endpoint. Khi flow được khai báo bằng `@Bean`, tên phương thức `@Bean` trở thành bean name của flow:

```java
@Bean
public IntegrationFlow ordersFlow(OrderHandler orderHandler) {
    return IntegrationFlow.from("ordersInput")
        .handle(orderHandler, "handle")
        .get();
}
```

Trong ví dụ:

- `ordersFlow` là bean name của đối tượng mô tả flow.
- `ordersInput` là tên channel mà flow nhận message.
- `.handle(...)` khai báo một bước xử lý; khi flow được xử lý để đăng ký runtime, Spring Integration tạo và quản lý endpoint cùng handler tương ứng.
- Endpoint và các component phụ trợ có thể có tên do framework tạo dựa trên flow và cấu trúc DSL.

Vì vậy, không nên suy ra rằng bean name `ordersFlow` cũng chính là tên của endpoint xử lý. Flow là cấu hình/tổ hợp các bước; endpoint là thành phần runtime thực thi một bước trong flow.

### Tên sinh tự động và tên được đặt tường minh

Với Java DSL, một flow có thể tạo ra nhiều endpoint, channel hoặc component phụ trợ. Nếu không đặt ID, framework có thể sinh tên theo thông tin flow, loại component và vị trí của bước trong cấu trúc. Những tên tự sinh hữu ích để runtime đăng ký các component mà không bắt người viết phải đặt tên cho từng bước.

Tuy nhiên, tên tự sinh có thể thay đổi khi cấu trúc flow thay đổi, khi thêm/bớt bước hoặc khi cách đăng ký của phiên bản framework thay đổi. Không nên hard-code một chuỗi tên tự sinh vào code nghiệp vụ, script vận hành hoặc dashboard nếu có thể đặt ID rõ ràng.

Khi một endpoint cần được nhận diện ổn định, hãy đặt endpoint ID bằng cơ chế phù hợp với cách khai báo. Với endpoint tạo từ annotation, có thể dùng `@EndpointId`:

```java
@EndpointId("orders.persist")
@ServiceActivator(inputChannel = "orders.input")
public void persist(Order order) {
    // Lưu đơn hàng
}
```

Với endpoint khai báo qua Java DSL, có thể đặt ID trong endpoint spec:

```java
@Bean
public IntegrationFlow ordersFlow(OrderHandler handler) {
    return IntegrationFlow.from("orders.input")
        .handle(handler, "handle", endpoint -> endpoint.id("orders.persist"))
        .get();
}
```

ID tường minh làm cho log và thông tin quản trị dễ đọc hơn. Cần bảo đảm các ID không xung đột trong phạm vi registry mà chúng được đăng ký. Nếu flow có nhiều endpoint cùng loại, nên đặt ID theo chức năng hoặc vị trí nghiệp vụ, chẳng hạn `orders.validate`, `orders.persist` và `orders.publish`.

## 4. Component name và managed name trong Spring Integration

Spring Integration phân biệt bean của Spring với component mang ý nghĩa trong Integration runtime. Nhiều thành phần Integration triển khai abstraction `NamedComponent`, cho phép truy vấn thông tin như tên component và loại component. Thông tin này hữu ích khi quan sát channel, endpoint, adapter hoặc các thành phần Integration khác.

Ở mức khái niệm:

- **Component name** nhận diện một thành phần Integration, ví dụ một endpoint hoặc channel.
- **Component type** mô tả loại thành phần, ví dụ service activator, transformer hoặc direct channel.
- **Managed name/type** là thông tin nhận diện mà bề mặt management dùng cho thành phần có hỗ trợ quản trị, metrics hoặc thống kê. Với component triển khai `IntegrationManagement`, có thể đọc qua `getManagedName()` và `getManagedType()`.

Các tên này thường được liên kết với tên bean hoặc ID của endpoint để người vận hành dễ tìm component. Tuy nhiên, không nên mặc định mọi object trong ApplicationContext đều là `NamedComponent`, hoặc mọi managed name luôn bằng bean name. Một bean nghiệp vụ thông thường có thể không phải component Integration; ngược lại, một endpoint được framework tạo ra có thể có tên riêng dù handler nghiệp vụ là một bean khác.

Ví dụ về sự khác nhau giữa handler và endpoint:

```text
ApplicationContext
├── orderHandler       -> object nghiệp vụ OrderHandler
├── ordersInput        -> DirectChannel
└── ordersFlow         -> IntegrationFlow

Integration runtime
├── ordersInput        -> channel nhận message
└── orders.persist     -> endpoint gọi orderHandler.handle(...)
```

`orderHandler` là bean chứa logic nghiệp vụ. `orders.persist` là định danh của endpoint gọi logic đó. Hai thành phần có quan hệ sử dụng nhưng không phải cùng một object.

Khi cần xem tên và loại của một component, hãy dùng API mà component công bố, chẳng hạn `NamedComponent.getComponentName()` và `getComponentType()` nếu bean triển khai interface đó. `IntegrationManagement` mở rộng khả năng nhận diện cho quản trị; với component triển khai interface này, có thể đọc `getManagedName()` và `getManagedType()` để biết tên/loại được công bố cho management. Các giá trị thường được cấu hình hoặc dẫn xuất để thuận tiện cho metrics, nhưng không nên mặc định mọi bean trong context đều triển khai `IntegrationManagement` hoặc mọi managed name luôn bằng bean name. Không nên tự tách chuỗi tên do framework sinh để đoán loại component; hãy dùng metadata thay vì dựa vào định dạng chuỗi nội bộ.

## 5. Channel name và endpoint ID có vai trò khác nhau

Channel là điểm giao tiếp giữa các bước trong flow. Endpoint là adapter nối một channel với một hành vi xử lý, chuyển đổi, định tuyến hoặc phát message. Vì vậy, channel name thường được dùng để định tuyến message trong cấu hình, còn endpoint ID giúp nhận diện nơi thực thi hành vi.

```text
orders.input
    |
    v
orders.validate (endpoint)
    |
    v
orders.validated
    |
    v
orders.persist (endpoint)
    |
    v
orders.saved
```

Trong sơ đồ, `orders.input`, `orders.validated` và `orders.saved` là tên channel; `orders.validate` và `orders.persist` là ID endpoint. Khi một message bị kẹt hoặc không đến được bước lưu, cần kiểm tra cả channel đang giữ/chuyển message và endpoint subscribe channel đó.

Nếu cấu hình dùng chuỗi tên channel, hãy xác minh channel có thực sự được đăng ký trong ApplicationContext và đúng kiểu channel mà flow mong đợi. Ví dụ `DirectChannel` chuyển message theo kiểu gọi đồng bộ, trong khi `QueueChannel` giữ message để consumer nhận sau. Cùng tên channel nhưng cấu hình kiểu channel khác có thể làm thay đổi thread boundary và cách exception được truyền đi.

Không nên dùng endpoint ID thay cho channel name trong thuộc tính `inputChannel`, hoặc dùng channel name như thể nó là endpoint. Hai định danh phục vụ hai vai trò khác nhau trong flow.

## 6. Định danh của IntegrationFlow đăng ký động

Khi ứng dụng cần thêm hoặc gỡ flow trong lúc chạy, `IntegrationFlowContext` cung cấp cơ chế đăng ký và quản lý flow động. Khi đăng ký, có thể cấp một ID để nhận diện registration:

```java
IntegrationFlowRegistration registration =
    flowContext.registration(dynamicOrdersFlow)
        .id("tenantAOrders")
        .register();

String registrationId = registration.getId();
```

`tenantAOrders` là ID của flow registration trong `IntegrationFlowContext`. Framework dùng registration này để quản lý vòng đời flow và các component được tạo từ flow. ID này không phải message ID, không phải correlation ID và cũng không đồng nghĩa với ID của từng endpoint bên trong flow.

Khi không chỉ định ID tường minh, cơ chế đăng ký có thể tạo ID mặc định. Với hệ thống có nhiều flow được tạo theo tenant, khách hàng hoặc cấu hình runtime, nên cấp ID có quy tắc và bảo đảm duy nhất. Trước khi đăng ký, cần xác định phạm vi duy nhất và hành vi khi ID đã tồn tại để tránh xung đột với flow đang hoạt động.

Khi gỡ flow, hãy thao tác thông qua registration tương ứng để framework dừng và giải phóng các thành phần do flow đó quản lý. Không nên tự xóa từng bean sinh ra của flow bằng cách suy đoán tên; làm như vậy có thể để lại endpoint, channel hoặc liên kết runtime không nhất quán.

## 7. Message ID và correlation ID không phải tên component

Khi message đi qua flow, Spring Messaging cung cấp metadata trong `MessageHeaders`. Hai header thường được dùng để truy vết là:

- `MessageHeaders.ID`: định danh của một message cụ thể. Nó giúp phân biệt message trong log và quá trình xử lý.
- `correlationId`: thông tin liên kết nhiều message thuộc cùng một giao dịch nghiệp vụ hoặc một nhóm xử lý. Correlation ID thường do ứng dụng hoặc cơ chế grouping đặt theo ngữ cảnh nghiệp vụ.

Ví dụ một đơn hàng có thể tạo nhiều message cho các bước kiểm tra, lưu trữ và phát sự kiện. Các message có thể có ID khác nhau nhưng cùng correlation ID để hệ thống quan sát được chúng thuộc cùng một quy trình.

```text
orders.validate
    | Message ID: M-101, correlationId: ORDER-9001
    v
orders.persist
    | Message ID: M-102, correlationId: ORDER-9001
    v
orders.publish
    | Message ID: M-103, correlationId: ORDER-9001
```

Trong ví dụ, endpoint ID vẫn là `orders.validate`, `orders.persist` và `orders.publish`. Message ID thay đổi theo từng message; correlation ID giữ quan hệ giữa các message của cùng đơn hàng. Không nên dùng message ID làm tên bean hoặc endpoint, vì message được tạo liên tục và vòng đời của nó khác vòng đời ApplicationContext.

Trong hệ thống có aggregator hoặc resequencer, correlation strategy còn quyết định message nào thuộc cùng một message group. Khi đó correlation ID ảnh hưởng đến việc nhóm và hoàn tất message group; nó vẫn không đổi tên bean hay component runtime.

## 8. Quan sát định danh trong runtime

Khi chẩn đoán, hãy quan sát từng lớp định danh từ phạm vi rộng đến hẹp.

### Kiểm tra bean name và alias

Có thể liệt kê tên bean trong ApplicationContext và tìm bean theo type:

```java
String[] beanNames = context.getBeanDefinitionNames();
String[] channelNames = context.getBeanNamesForType(MessageChannel.class);
String[] aliases = context.getAliases("ordersInput");
```

Các lệnh này giúp xác nhận bean đã được đăng ký, tên nào là alias và những channel nào tồn tại theo type. Với bean được tạo bởi factory hoặc cơ chế đăng ký đặc biệt, cần phân biệt danh sách bean definition với các singleton đã có trong context; hai khái niệm này không phải lúc nào cũng cùng phạm vi.

### Kiểm tra metadata của component

Với bean triển khai `NamedComponent`, có thể đọc component name và component type từ chính object:

```java
Object candidate = context.getBean("orders.persist");
if (candidate instanceof NamedComponent named) {
    String componentName = named.getComponentName();
    String componentType = named.getComponentType();
}
```

Đoạn code minh họa cách kiểm tra có điều kiện; tên bean dùng để tra cứu vẫn phải là tên đã được đăng ký trong context của ứng dụng. Không phải mọi endpoint đều có thể được tra cứu bằng một ID tùy ý nếu cấu hình hoặc cơ chế đăng ký của endpoint không đưa nó vào registry theo tên đó.

### Kiểm tra Integration graph và management

Khi bật cơ chế quan sát graph của Spring Integration, runtime graph có thể cung cấp danh sách node, loại component và liên kết giữa các node. Đây là cách hữu ích để xem một endpoint kết nối với channel nào và phát hiện những component không nằm trong đường đi dự kiến.

Nếu ứng dụng bật `IntegrationGraphServer` hoặc expose graph qua management endpoint, hãy dùng dữ liệu graph để đối chiếu tên component và topology thực tế. Tương tự, metrics của Integration có thể gắn thông tin component vào dữ liệu thống kê. Việc graph hoặc metrics có sẵn phụ thuộc cấu hình management, actuator và phiên bản ứng dụng; chỉ có bean name không đồng nghĩa graph endpoint đã được bật.

## 9. Quy tắc đặt tên cho flow dễ vận hành

Nên đặt tên dựa trên chức năng và giữ nhất quán giữa các module:

| Thành phần | Quy tắc gợi ý | Ví dụ |
|---|---|---|
| Channel bean | Tên mô tả dữ liệu và hướng đi | `orders.input`, `orders.validated` |
| IntegrationFlow bean | Tên mô tả flow nghiệp vụ | `ordersFlow` |
| Endpoint ID | Tên nghiệp vụ + hành động | `orders.validate`, `orders.persist` |
| Dynamic flow registration ID | Tên tenant/đối tượng + flow | `tenantAOrders` |
| Handler bean | Tên class nghiệp vụ theo quy ước Spring | `orderHandler` |
| Correlation ID | Khóa nghiệp vụ dùng để liên kết các message | `ORDER-9001` |

Một số nguyên tắc thực tế:

1. Đặt tên tường minh cho channel và endpoint được tham chiếu từ nhiều nơi hoặc được dùng trong dashboard, log và cảnh báo.
2. Giữ tên tự sinh cho component nội bộ không cần tham chiếu ổn định từ bên ngoài.
3. Tránh đặt cùng một chuỗi cho nhiều vai trò khác nhau nếu điều đó khiến log khó phân biệt, ví dụ dùng `orders` cho cả flow, channel và endpoint.
4. Đặt ID registration động theo một quy tắc duy nhất và kiểm tra trùng trước khi đăng ký.
5. Không đưa dữ liệu nhạy cảm hoặc thông tin cá nhân vào bean name, endpoint ID hay correlation ID vì các giá trị này có thể xuất hiện trong log và metrics.
6. Khi đổi tên bean hoặc endpoint đã được hệ thống khác tham chiếu, hãy xem đó là thay đổi cấu hình có ảnh hưởng đến dependency, monitoring và vận hành.

## 10. Chẩn đoán lỗi định danh thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` hoặc không tìm thấy bean theo tên | Sai bean name, chỉ có alias khác, cấu hình chưa được import hoặc bean chưa được đăng ký | Kiểm tra bean definition names, aliases, package scan và cấu hình `@Import`. |
| `NoSuchBeanDefinitionException` khi tham chiếu channel | Chuỗi channel name không trỏ đến channel bean đã đăng ký | Kiểm tra `MessageChannel` beans và tên trong `from(...)`, `inputChannel` hoặc `.channel(...)`. |
| Nhiều endpoint có tên khó đọc | Dùng tên tự sinh hoặc flow có nhiều bước tương tự | Đặt ID tường minh cho endpoint quan trọng và xem metadata component. |
| Runtime graph không có component mong đợi | Flow chưa được đăng ký, endpoint không khởi động hoặc graph management chưa được bật | Kiểm tra startup, trạng thái endpoint, flow registration và cấu hình graph. |
| Đăng ký dynamic flow thất bại | Registration ID bị trùng hoặc flow tạo ra component xung đột | Kiểm tra ID hiện có và quy tắc đặt tên của các flow động. |
| Log có message ID khác nhau dù cùng một nghiệp vụ | Các bước tạo message mới trong cùng quy trình | Dùng correlation ID để nối các message thuộc cùng nghiệp vụ. |

Khi đọc log, nên ghi đồng thời endpoint/component name, channel, message ID và correlation ID nếu có. Nhờ đó có thể phân biệt lỗi thuộc cấu hình runtime với lỗi thuộc một message cụ thể. Tránh chỉ ghi một chuỗi chung như `orders`, vì không thể biết nó đang nói đến bean, channel, endpoint hay nghiệp vụ.

## 11. Cách suy nghĩ khi đọc một message flow

Khi nhìn vào một flow, hãy lần lượt trả lời bốn câu hỏi:

1. **Spring đang quản lý object nào?** Xác định bean name, type và alias trong ApplicationContext.
2. **Integration runtime đang vận hành component nào?** Xác định channel, endpoint, component name/type và flow registration.
3. **Component nối với nhau ra sao?** Dùng topology của flow hoặc runtime graph để tìm channel đầu vào, đầu ra và endpoint xử lý.
4. **Message nào đang được xử lý?** Dùng message ID và correlation ID để theo dõi từng message và nhóm message nghiệp vụ.

Khi phân biệt được bốn lớp này, việc tra cứu bean, đọc log, quan sát metrics và điều tra topology trở nên rõ ràng. Bean name giúp tìm object trong Spring container; component và endpoint name giúp nhận diện cấu trúc Integration; managed metadata phục vụ vận hành; còn message ID và correlation ID giúp theo dõi dữ liệu đang chạy qua flow.
