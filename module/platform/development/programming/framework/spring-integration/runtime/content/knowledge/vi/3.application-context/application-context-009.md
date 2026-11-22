# Không tạo vòng phụ thuộc giữa các integration component

Trong Spring Integration, một message flow được ghép từ nhiều thành phần như channel, endpoint, handler, gateway, adapter và service. Spring tạo các thành phần này thành bean trong `ApplicationContext`, sau đó kết nối chúng để message có thể đi qua flow. Nếu các bean phụ thuộc ngược lại lẫn nhau, ứng dụng có thể không khởi động được vì Spring không thể hoàn tất việc tạo đối tượng.

Vòng phụ thuộc thường xuất hiện khi một service được flow sử dụng lại inject chính `IntegrationFlow`, endpoint hoặc một component quản lý flow để gọi ngược về flow đó. Cách thiết kế an toàn là để flow phụ thuộc vào handler/service, còn service giao tiếp với các bước khác qua channel hoặc messaging gateway có ranh giới rõ ràng. Khi đó, cấu trúc message flow vẫn linh hoạt mà đồ thị tạo bean không bị khép thành vòng.

Sau bài này, bạn có thể:

- Nhận biết chu trình trong đồ thị phụ thuộc bean và phân biệt nó với vòng lặp message flow.
- Hiểu vì sao việc inject ngược `IntegrationFlow`, endpoint hoặc cấu hình flow vào service dễ tạo circular dependency.
- Thiết kế ranh giới giao tiếp bằng `MessageChannel` và messaging gateway.
- Đánh giá đúng vai trò của constructor injection, `@Lazy`, `ObjectProvider` và `@DependsOn`.
- Đọc lỗi khởi tạo bean và lần theo chuỗi phụ thuộc để sửa từ cấu trúc.

## 1. Hai loại đồ thị không nên nhầm lẫn

Khi phân tích Spring Integration, cần tách biệt **đồ thị phụ thuộc bean** với **đồ thị message flow**. Chúng mô tả hai quan hệ khác nhau.

Đồ thị phụ thuộc bean mô tả đối tượng nào cần đối tượng nào trong lúc Spring tạo và cấu hình bean. Nếu bean A cần bean B để khởi tạo, ta có cạnh `A -> B`. Một chu trình như `A -> B -> A` khiến hai bean cần nhau trước khi bean nào có thể được tạo hoàn chỉnh.

Đồ thị message flow mô tả message đi qua các channel và endpoint theo thứ tự nào. Một message có thể đi từ A sang B rồi được router đưa trở lại A. Đây là vòng lặp xử lý message; nó không tự động có nghĩa là Spring bean đang phụ thuộc vòng tròn.

```text
Đồ thị phụ thuộc bean (lúc khởi động)

OrderFlowConfig ---> OrderHandler
       ^                 |
       |                 v
       +------------- FlowFacade

Đồ thị message flow (lúc xử lý)

ordersInput ---> OrderHandler ---> inventoryInput ---> InventoryHandler
```

Ở hình trên, chu trình bean khiến việc khởi tạo gặp vấn đề. Đồ thị message flow ở dưới là một chuỗi xử lý bình thường. Một vòng message có chủ đích vẫn có thể hợp lệ nếu có điều kiện dừng; ngược lại, một chu trình bean không trở nên an toàn chỉ vì message flow được thiết kế đúng.

## 2. Vòng phụ thuộc hình thành như thế nào?

Giả sử cấu hình flow cần `OrderCoordinator` làm handler. Nhưng `OrderCoordinator` lại inject chính bean `IntegrationFlow` để gọi hoặc kiểm tra flow:

```java
@Configuration
class OrderFlowConfiguration {

    @Bean
    IntegrationFlow ordersFlow(OrderCoordinator coordinator) {
        return IntegrationFlow.from("ordersInput")
                .handle(coordinator, "process")
                .get();
    }
}

@Component
class OrderCoordinator {

    private final IntegrationFlow ordersFlow;

    OrderCoordinator(IntegrationFlow ordersFlow) {
        this.ordersFlow = ordersFlow;
    }

    public void process(Order order) {
        // Xử lý đơn hàng và gọi ngược vào flow.
    }
}
```

Spring phải tạo `ordersFlow` nên cần `OrderCoordinator`. Nhưng để tạo `OrderCoordinator`, Spring lại cần `ordersFlow`. Chu trình phụ thuộc là:

```text
ordersFlow -> OrderCoordinator -> ordersFlow
```

Đây là circular dependency ở thời điểm khởi tạo bean. Việc gọi `ordersFlow` trong phương thức `process()` chưa phải vấn đề cốt lõi; vấn đề là service giữ tham chiếu trực tiếp đến định nghĩa flow để điều phối công việc.

Các chu trình có thể dài hơn hai bean. Ví dụ `FlowConfig -> HandlerA -> GatewayB -> ServiceB -> FlowConfig`. Khi đọc stack trace, cần lần theo toàn bộ chuỗi phụ thuộc chứ không chỉ nhìn hai bean xuất hiện đầu tiên.

## 3. Flow nên phụ thuộc vào handler; handler giao tiếp qua boundary

Một `IntegrationFlow` nên chịu trách nhiệm kết nối các bước xử lý. Handler/service nên tập trung vào nghiệp vụ và chỉ phụ thuộc vào các collaborator cần thiết để thực hiện nghiệp vụ. Nếu một handler cần gửi message đến bước khác, hãy dùng channel hoặc gateway đại diện cho điểm giao tiếp đó.

Ví dụ sau tách flow definition, channel và gateway thành các bean có thể được tạo độc lập:

```java
@MessagingGateway(defaultRequestChannel = "ordersInput")
interface OrderGateway {
    void submit(Order order);
}

@Configuration
@IntegrationComponentScan
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow ordersFlow(OrderHandler orderHandler) {
        return IntegrationFlow.from("ordersInput")
                .handle(orderHandler, "handle")
                .get();
    }
}

@Component
class OrderHandler {

    private final OrderRepository repository;

    OrderHandler(OrderRepository repository) {
        this.repository = repository;
    }

    public void handle(Order order) {
        repository.save(order);
    }
}

@Service
class OrderApplicationService {

    private final OrderGateway orderGateway;

    OrderApplicationService(OrderGateway orderGateway) {
        this.orderGateway = orderGateway;
    }

    public void submit(Order order) {
        orderGateway.submit(order);
    }
}
```

Đồ thị phụ thuộc giờ có dạng:

```text
OrderFlowConfiguration ---> OrderHandler ---> OrderRepository
          |
          v
     ordersInput <--- OrderGateway <--- OrderApplicationService
```

Flow và gateway cùng sử dụng `ordersInput`, nhưng channel là một bean độc lập. `OrderHandler` không cần biết flow nào gọi nó; `OrderApplicationService` chỉ biết gateway để gửi lệnh. Không có cạnh phụ thuộc từ handler quay về flow definition.

Trong ứng dụng có nhiều channel cùng kiểu, hãy dùng tên bean rõ ràng và `@Qualifier` khi inject trực tiếp `MessageChannel` để tránh chọn nhầm channel. Gateway có thể khai báo `defaultRequestChannel` hoặc cấu hình channel ở từng phương thức bằng `@Gateway`.

Nếu một handler cần gửi tiếp sang bước kiểm tra kho, tạo một gateway khác với channel đầu vào riêng, ví dụ `InventoryGateway` gửi đến `inventoryInput`. Flow kiểm tra kho đăng ký handler trên channel đó. Handler đầu tiên chỉ phụ thuộc vào `InventoryGateway`; nó không inject `InventoryFlow` hoặc endpoint của flow kiểm tra kho.

Channel chỉ tạo được ranh giới tốt khi bean channel được tạo độc lập. Nếu factory method của channel lại cần service đang phụ thuộc ngược vào flow, chu trình vẫn còn. Hãy kiểm tra toàn bộ cạnh phụ thuộc thực tế, không chỉ đổi kiểu tham chiếu từ `IntegrationFlow` sang `MessageChannel` một cách máy móc.

## 4. Những quy tắc thiết kế giúp tránh chu trình

### 4.1. Không inject IntegrationFlow hoặc endpoint vào service nghiệp vụ

`IntegrationFlow` mô tả cách kết nối component. Service nghiệp vụ không nên giữ flow bean để tự gửi message vào đầu flow, gọi endpoint hoặc kiểm tra trạng thái endpoint. Dùng messaging gateway, channel hoặc một application service có trách nhiệm điều phối ở tầng phù hợp.

Tương tự, tránh inject implementation của consumer endpoint hoặc handler do DSL tạo vào một service khác. Các bean runtime này là chi tiết wiring của integration layer; phụ thuộc trực tiếp làm cấu trúc khởi tạo khó hiểu và dễ tạo cạnh ngược.

### 4.2. Giữ channel độc lập với service và flow

Khai báo channel như một bean hạ tầng nhỏ, không để channel factory phụ thuộc vào handler hoặc service cần channel đó. Channel là điểm nối giữa producer và consumer; nó không cần biết ai gửi hay ai xử lý message.

Với channel được khai báo inline trong Java DSL, hãy cân nhắc đưa channel ra thành bean riêng nếu nhiều flow hoặc gateway cần cùng tham chiếu. Điều này làm rõ ranh giới và tránh phụ thuộc ngược qua cấu hình.

### 4.3. Tách trách nhiệm điều phối khỏi xử lý nghiệp vụ

Một service vừa xử lý nghiệp vụ, vừa quản lý đăng ký flow, vừa gọi ngược endpoint thường có quá nhiều trách nhiệm. Tách thành các thành phần có vai trò rõ:

- Flow configuration kết nối channel, handler và adapter.
- Handler/application service xử lý nghiệp vụ.
- Gateway đại diện cho thao tác gửi message.
- Flow manager quản lý đăng ký động nếu ứng dụng thật sự cần tạo/gỡ flow lúc runtime.

Flow manager có thể phụ thuộc `IntegrationFlowContext` để đăng ký flow động. Handler được flow sử dụng không nên phụ thuộc ngược vào flow manager chỉ để gọi một bước khác; hãy dùng gateway/channel cho giao tiếp message.

### 4.4. Ưu tiên constructor injection

Constructor injection thể hiện rõ bean cần những dependency nào và làm chu trình dễ nhận ra ngay khi khởi động. Nếu constructor của A cần B và constructor của B cần A, Spring không thể tạo một trong hai bean trước để hoàn tất bean còn lại.

Không nên chuyển hàng loạt dependency sang field hoặc setter injection chỉ để né lỗi. Một số chu trình singleton dùng setter injection có thể được Spring xử lý bằng tham chiếu sớm trong một số cấu hình, nhưng kết quả phụ thuộc loại bean, proxy và vòng đời khởi tạo. Đối tượng có thể bị truy cập khi chưa được khởi tạo đầy đủ; prototype hoặc chu trình qua constructor vẫn không giải quyết được theo cách đó.

## 5. `@Lazy`, `ObjectProvider` và `@DependsOn` không thay thế thiết kế tốt

Khi gặp circular dependency, có một số cơ chế thường được đề xuất. Chúng có trường hợp sử dụng riêng nhưng không nên dùng như cách che giấu một đồ thị phụ thuộc sai.

| Cơ chế | Tác dụng | Giới hạn |
|---|---|---|
| `@Lazy` | Tiêm proxy và trì hoãn việc phân giải bean cho đến khi được sử dụng. | Chỉ trì hoãn thời điểm cần dependency; nếu hai component vẫn gọi qua lại hoặc gọi trong lúc khởi tạo, vấn đề có thể xuất hiện muộn hơn. |
| `ObjectProvider<T>` | Lấy bean theo yêu cầu, hỗ trợ dependency tùy chọn hoặc cần phân giải muộn. | Không loại bỏ quan hệ phụ thuộc về mặt thiết kế; gọi `getObject()` quá sớm vẫn có thể gặp chu trình. |
| Setter/field injection | Cho phép một số singleton được tạo trước rồi mới gắn dependency. | Phụ thuộc vào cơ chế early reference; khó thấy dependency và có nguy cơ dùng bean chưa sẵn sàng. |
| `@DependsOn` | Yêu cầu Spring khởi tạo một bean trước bean khác. | Chỉ quy định thứ tự khởi tạo; không thể làm cho chu trình A cần B và B cần A biến mất. |
| `@Primary` / `@Qualifier` | Chọn bean khi có nhiều ứng viên cùng kiểu. | Giải quyết mơ hồ khi chọn bean, không giải quyết circular dependency. |

`@Lazy` hoặc `ObjectProvider` phù hợp khi thật sự cần dependency tùy chọn, plugin được nạp muộn hoặc một thao tác chỉ xảy ra sau khi context đã sẵn sàng. Nếu lý do duy nhất là ứng dụng báo circular dependency, hãy quay lại tách trách nhiệm và xác định boundary trước.

Spring Boot từ phiên bản 2.6 mặc định không cho phép circular references giữa bean. Thuộc tính `spring.main.allow-circular-references` có thể thay đổi hành vi này ở các phiên bản hỗ trợ, nhưng bật lại chỉ để ứng dụng khởi động không phải cách sửa cấu trúc. Hãy kiểm tra phiên bản Spring Boot đang dùng trước khi dựa vào hành vi cụ thể.

## 6. Phân biệt vòng bean với vòng lặp message flow

Vòng lặp message có thể là yêu cầu nghiệp vụ hợp lệ, chẳng hạn message đi qua nhiều bước kiểm tra cho đến khi đạt điều kiện hoàn tất. Nó không nhất thiết tạo circular dependency lúc Spring khởi tạo bean, vì các endpoint vẫn có thể được tạo độc lập.

Tuy nhiên, vòng message không có điều kiện dừng có thể gây tiêu thụ CPU, tăng queue vô hạn hoặc lặp xử lý cùng một nghiệp vụ. Với `DirectChannel`, message có thể quay lại handler theo kiểu gọi lồng nhau và làm tăng call stack. Với `QueueChannel` hoặc `ExecutorChannel`, message có thể liên tục được đưa lại vào hàng đợi.

Nếu flow cần quay lại bước trước, hãy thiết kế điều kiện thoát tường minh:

- Dùng header hoặc trạng thái nghiệp vụ thể hiện số lần quay lại/hop count.
- Dùng filter/router để kết thúc hoặc chuyển message sang nhánh lỗi khi vượt giới hạn.
- Dùng correlation ID để theo dõi cùng một chuỗi xử lý và idempotency key để tránh áp dụng lặp một tác động nghiệp vụ.
- Đặt giới hạn retry và phân biệt retry do lỗi tạm thời với vòng lặp điều khiển của flow.
- Ghi log các lần chuyển hướng và cung cấp đường thoát cho message không thể tiếp tục.

Không nên dựa vào message ID để giới hạn vòng lặp, vì một bước tạo message mới có thể sinh ID mới. Dùng một header nghiệp vụ ổn định hoặc trạng thái được quản lý riêng cho toàn bộ chuỗi xử lý.

## 7. Những mẫu dễ tạo phụ thuộc ngược trong Spring Integration

| Mẫu thiết kế | Rủi ro | Cách tổ chức lại |
|---|---|---|
| Handler inject `IntegrationFlow` đang chứa handler đó. | Flow cần handler để được tạo, handler lại cần flow. | Handler chỉ nhận nghiệp vụ; producer gửi qua gateway/channel. |
| Service inject consumer endpoint để gọi `start()` hoặc `stop()`. | Service nghiệp vụ phụ thuộc chi tiết lifecycle của endpoint; flow có thể phụ thuộc ngược service. | Tạo flow manager riêng, quản lý lifecycle qua API phù hợp và không để handler phụ thuộc manager. |
| Hai service gọi trực tiếp lẫn nhau. | Chu trình bean xuất hiện ngay cả khi không có flow. | Tách phần dùng chung thành service thứ ba hoặc phát message qua boundary. |
| Channel factory cần service gửi message vào chính channel đó. | Chu trình có thể đi qua factory method và service. | Channel là bean hạ tầng độc lập, không inject producer/consumer. |
| Service tra `ApplicationContext.getBean()` để lấy flow hoặc endpoint. | Dependency bị ẩn, khó lần theo và có thể phát sinh lỗi lúc runtime. | Khai báo dependency qua constructor/gateway/provider có chủ đích. |
| Nhiều endpoint cùng subscribe một channel ngoài dự kiến. | Không nhất thiết là circular dependency, nhưng có thể khiến message bị nhiều consumer nhận hoặc phân phối không như mong đợi. | Kiểm tra topology và xác định rõ fan-out hay competing consumers là mục tiêu. |

Đặc biệt, hai endpoint cùng đọc một `SubscribableChannel` không tự động tạo vòng bean. Đây là vấn đề topology và semantics phân phối message. Hãy chẩn đoán theo đúng loại quan hệ thay vì gọi mọi hiện tượng bất thường là circular dependency.

## 8. Cách chẩn đoán lỗi circular dependency

Khi ApplicationContext không khởi động, Spring thường báo `BeanCurrentlyInCreationException` hoặc một `UnsatisfiedDependencyException` có nguyên nhân lồng bên trong. Hãy đọc phần dependency path và bean name trong thông báo lỗi.

Quy trình thực tế:

1. **Tìm bean được nhắc trong lỗi.** Ghi lại bean đang được tạo và dependency mà Spring không thể phân giải.
2. **Lần theo chuỗi constructor và factory method.** Kiểm tra constructor injection, tham số của `@Bean`, `@Autowired`, gateway và các factory/provider.
3. **Vẽ đồ thị phụ thuộc.** Viết từng cạnh `A -> B` theo đúng quan hệ cần có để tạo bean; tìm điểm quay lại bean ban đầu.
4. **Xác định vai trò của từng bean.** Bean nào là flow definition, channel, endpoint, handler, gateway, service hay flow manager?
5. **Chọn một boundary để bỏ cạnh ngược.** Thay tham chiếu flow/endpoint bằng gateway hoặc channel độc lập; hoặc tách logic dùng chung thành service thứ ba.
6. **Khởi động lại context và kiểm tra message flow.** Xác nhận bean graph không còn chu trình, sau đó gửi message thử để bảo đảm topology và routing vẫn đúng.

Ví dụ lỗi có thể thể hiện chuỗi như sau:

```text
Error creating bean with name 'ordersFlow'
  -> constructor/factory method needs 'orderCoordinator'
  -> bean 'orderCoordinator' needs 'flowFacade'
  -> bean 'flowFacade' needs 'ordersFlow'

Circular path:
ordersFlow -> orderCoordinator -> flowFacade -> ordersFlow
```

Tên bean và cách trình bày thực tế thay đổi theo phiên bản Spring và cách khai báo. Hãy dựa vào chuỗi dependency mà exception cung cấp, không giả định mọi lỗi `UnsatisfiedDependencyException` đều là circular dependency; lỗi đó cũng có thể do thiếu bean, sai qualifier hoặc lỗi tạo dependency khác.

Integration Graph giúp quan sát các integration component và quan hệ message flow. Nó hữu ích để phát hiện topology message đi vòng hoặc endpoint được nối không đúng, nhưng không thay thế dependency path của Spring bean factory. Khi lỗi xảy ra trước khi context hoàn tất, Integration Graph thậm chí có thể chưa sẵn sàng để truy vấn.

## 9. Checklist thiết kế trước khi thêm component

Trước khi thêm một handler, gateway hoặc flow mới, hãy tự kiểm tra:

- Flow chỉ kết nối component; service nghiệp vụ không cần giữ tham chiếu tới flow definition hoặc endpoint.
- Channel dùng chung được tạo độc lập, không cần service gửi/nhận message để khởi tạo.
- Gateway thể hiện rõ điểm gửi message và channel đích.
- Handler chỉ phụ thuộc vào service/repository hoặc gateway mà nó thực sự cần.
- Flow manager quản lý registration động ở một nơi; handler không gọi ngược manager để điều khiển flow chứa nó.
- Constructor injection cho thấy rõ dependency graph; không dùng `@Lazy` hoặc setter injection chỉ để che lỗi.
- Nếu message flow có vòng lặp, điều kiện dừng, giới hạn số vòng và cách xử lý message lỗi đã được xác định.
- Kiểm tra cả dependency graph lúc khởi tạo lẫn message topology lúc chạy.

## 10. Tự kiểm tra

**Tình huống:** `ordersFlow` dùng `OrderHandler`. `OrderHandler` inject `OrderFlowManager`, còn `OrderFlowManager` inject `IntegrationFlow` có tên `ordersFlow` để gọi lại flow khi cần xử lý tiếp.

1. Chu trình phụ thuộc bean là gì?
2. Vì sao thay `IntegrationFlow` bằng `MessageChannel` có thể giải quyết vấn đề nếu channel là bean độc lập?
3. Nếu message từ `OrderHandler` được gửi qua channel quay lại `ordersInput`, đó là loại vòng nào?
4. Cần cơ chế gì để vòng message không chạy vô hạn?

**Gợi ý trả lời:** (1) `ordersFlow -> OrderHandler -> OrderFlowManager -> ordersFlow`. (2) Flow và producer cùng tham chiếu một channel độc lập; channel không cần tạo flow hay service nên không khép chu trình bean. (3) Đó là vòng lặp message flow, không tự động là circular dependency của bean. (4) Cần điều kiện thoát như hop count, filter/router, trạng thái nghiệp vụ, giới hạn retry và xử lý lỗi.

**Bài tập thiết kế:** Tách một flow xử lý đơn hàng thành hai bước: xác thực và kiểm tra kho. Tạo channel đầu vào riêng cho mỗi bước và gateway để bước xác thực gửi sang bước kiểm tra kho. Vẽ đồ thị bean dependency và message flow. Xác nhận đồ thị bean không có chu trình; sau đó kiểm tra message đi qua hai bước đúng một lần theo yêu cầu nghiệp vụ.

## Tài liệu tham khảo

- [Spring Framework Reference — Dependencies and Configuration in Detail](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html)
- [Spring Framework Reference — Using `@Lazy`](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Boot 2.6 Release Notes — Circular References Prohibited by Default](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.6-Release-Notes#circular-references-prohibited-by-default)
