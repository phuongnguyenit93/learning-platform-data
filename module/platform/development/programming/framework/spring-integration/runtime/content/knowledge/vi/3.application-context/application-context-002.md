# IntegrationContext và lifecycle của thành phần tích hợp

Trong **SPRING_INTEGRATION_RUNTIME**, Spring Integration không chỉ mô tả message flow mà còn tạo, đăng ký, khởi động, tạm dừng và giải phóng các thành phần tham gia flow. Những thành phần này sống bên trong **Spring ApplicationContext** và tuân theo cơ chế quản lý bean cùng lifecycle của Spring.

Trong tiêu đề bài này, **IntegrationContext** là cách gọi khái quát cho phần quản lý thành phần tích hợp trong context. Khi nói đến API đăng ký flow động của Java DSL hiện đại, tên chính xác là **IntegrationFlowContext**. Một số trao đổi hoặc tài liệu cũ có thể dùng cụm IntegrationContext để nói đến khả năng quản lý flow động. Ngoài ra còn có **IntegrationContextUtils**, một lớp tiện ích để tra cứu một số bean hạ tầng từ BeanFactory; nó không phải một application context riêng.

Bài học giải thích mối quan hệ giữa ApplicationContext, IntegrationFlowContext và lifecycle của endpoint, adapter, poller cùng các tài nguyên tích hợp. Mục tiêu là biết khi nào flow tự khởi động, khi nào cần start/stop thủ công, cách quản lý flow tạo động theo nghiệp vụ và cách đóng ứng dụng an toàn.

## 1. Các lớp context trong một ứng dụng Spring Integration

### 1.1 Spring ApplicationContext là container gốc

Spring ApplicationContext quản lý vòng đời của các bean trong ứng dụng. Nó chịu trách nhiệm đọc cấu hình, tạo bean, tiêm dependency, gọi các callback khởi tạo và hủy bean khi context đóng.

Trong ứng dụng Spring Integration, các bean thường bao gồm:

- **MessageChannel**: nơi producer gửi và consumer nhận message.
- **MessageHandler**: xử lý payload hoặc message.
- **Endpoint**: kết nối channel với handler, adapter hoặc nguồn message.
- **Inbound/Outbound adapter**: kết nối flow với hệ thống bên ngoài.
- **TaskScheduler và TaskExecutor**: điều phối lịch poll và thực thi task.
- **MessageStore, MetadataStore, errorChannel**: các dịch vụ hạ tầng phục vụ lưu trữ, metadata và xử lý lỗi.

Các bean này được tạo theo cấu hình Java, annotation, XML hoặc Java DSL. ApplicationContext là nơi giữ và quản lý chúng; nó không phải một message channel và không trực tiếp xử lý từng message.

Với cấu hình Java thuần, có thể bật hạ tầng annotation và Java DSL bằng @EnableIntegration. Spring Boot cùng starter tương ứng thường tự động cấu hình phần hạ tầng cần thiết; hãy kiểm tra cấu hình thực tế của ứng dụng trước khi khai báo trùng.

### 1.2 IntegrationFlow là mô tả một luồng tích hợp

IntegrationFlow mô tả các bước xử lý message và quan hệ giữa chúng. Ví dụ:

~~~java
@Configuration
@EnableIntegration
class OrderIntegrationConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
            .handle(orderService, "process")
            .get();
    }
}
~~~

Khi bean IntegrationFlow được đăng ký trong ApplicationContext, Spring Integration phân tích flow và đăng ký các thành phần cần thiết như channel, endpoint và handler dưới dạng bean. Các endpoint thực thi flow được quản lý bởi cơ chế lifecycle của Spring.

Đối tượng flow trong Java DSL là mô hình cấu hình logic. Nó không có nghĩa toàn bộ xử lý message diễn ra bên trong một object duy nhất. Runtime có các endpoint và channel cụ thể, mỗi thành phần có trách nhiệm riêng.

### 1.3 IntegrationFlowContext quản lý flow tạo động

IntegrationFlowContext là API công khai để đăng ký IntegrationFlow bằng chương trình khi ứng dụng đã chạy, thay vì chỉ khai báo flow như bean trong giai đoạn cấu hình ban đầu.

Một số trường hợp phù hợp:

- Mỗi tenant có một endpoint hoặc một nhóm flow riêng.
- Danh sách kết nối đối tác chỉ được biết sau khi ứng dụng khởi động.
- Cần tạo hoặc gỡ một flow theo phiên kết nối, cấu hình hoặc trạng thái nghiệp vụ.
- Một adapter chỉ cần tồn tại trong khoảng thời gian của một tác vụ cụ thể.

IntegrationFlowContext do Spring Integration cung cấp như một bean hạ tầng. Có thể inject nó vào service quản lý flow. API này cho phép đăng ký flow, lấy registration theo ID, xem registry, lấy MessagingTemplate và gỡ flow.

~~~java
@Service
class TenantFlowManager {

    private final IntegrationFlowContext flowContext;
    private final OrderService orderService;

    TenantFlowManager(
            IntegrationFlowContext flowContext,
            OrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    IntegrationFlowContext.IntegrationFlowRegistration createFlow(String tenantId) {
        IntegrationFlow flow = IntegrationFlow.from("tenant." + tenantId + ".input")
            .handle(orderService, "process")
            .get();

        return this.flowContext.registration(flow)
            .id("tenant-" + tenantId + "-orders")
            .autoStartup(false)
            .register();
    }
}
~~~

Ví dụ đặt autoStartup(false) để registration được tạo nhưng chưa nhận message. Service có thể kiểm tra trạng thái hoặc hoàn tất cấu hình phụ thuộc trước khi gọi registration.start().

Cần phân biệt rõ:

| Thành phần | Vai trò |
|---|---|
| ApplicationContext | Container quản lý bean và lifecycle của ứng dụng |
| IntegrationFlow | Mô tả cấu trúc các bước của một message flow |
| IntegrationFlowContext | Đăng ký, tra cứu và gỡ IntegrationFlow động |
| IntegrationFlowRegistration | Đại diện cho một flow đã đăng ký; cung cấp ID, input channel và thao tác lifecycle |
| IntegrationContextUtils | Utility tra cứu một số bean hạ tầng từ BeanFactory |

### 1.4 IntegrationContextUtils không phải IntegrationFlowContext

IntegrationContextUtils là lớp tiện ích thuộc package org.springframework.integration.context. Các method của nó hỗ trợ truy cập những thành phần dùng chung từ BeanFactory, ví dụ error channel, metadata store, task scheduler và evaluation context.

Không dùng IntegrationContextUtils để đăng ký flow động. Với công việc tạo hoặc gỡ flow trong runtime, hãy dùng IntegrationFlowContext. Phân biệt tên hai API này giúp tránh nhầm lẫn khi đọc stack trace, tài liệu hoặc cấu hình cũ.

## 2. Lifecycle của Spring bean và thành phần tích hợp

### 2.1 Lifecycle cơ bản của bean

Một bean do Spring quản lý thường đi qua các giai đoạn:

1. **Đăng ký định nghĩa**: Spring đọc cấu hình và ghi nhận bean definition.
2. **Khởi tạo**: container tạo object và tiêm dependency.
3. **Khởi tạo sau tiêm dependency**: các callback như InitializingBean, @PostConstruct hoặc init method được gọi theo quy tắc của Spring.
4. **Sử dụng**: bean sẵn sàng phục vụ ứng dụng.
5. **Dừng và hủy**: khi context đóng, các bean có lifecycle hoặc destroy callback được dừng và giải phóng tài nguyên.

Không phải mọi bean đều cần start/stop. Một service xử lý nghiệp vụ thông thường có thể chỉ là object được gọi khi endpoint dispatch message. Trong khi đó, inbound adapter, polling endpoint hoặc listener kết nối với hệ thống ngoài thường cần chủ động mở, chạy và đóng tài nguyên.

### 2.2 Lifecycle và SmartLifecycle

Spring có hai abstraction thường gặp:

- **Lifecycle**: cung cấp start(), stop() và isRunning().
- **SmartLifecycle**: mở rộng Lifecycle, bổ sung autoStartup, phase và stop callback để phối hợp thứ tự khởi động/dừng.

Các message endpoint trong Spring Integration dựa trên cơ chế lifecycle này. Base class AbstractEndpoint triển khai ManageableSmartLifecycle và DisposableBean. Endpoint có thuộc tính autoStartup; mặc định là true. Nếu đặt false, endpoint không tự khởi động theo lifecycle processor và cần được start tường minh.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Cách dùng |
|---|---|---|
| autoStartup | Có tự khởi động khi context bắt đầu chạy hay không | Đặt false khi cần chờ điều kiện bên ngoài |
| phase | Điều khiển thứ tự start/stop giữa các SmartLifecycle | Sắp xếp consumer, adapter và tài nguyên phụ thuộc |
| role | Nhóm các lifecycle component để điều khiển cùng nhau | Bật/tắt một nhóm endpoint theo nghiệp vụ |
| isRunning | Cho biết component đang chạy hay đã dừng | Kiểm tra trạng thái runtime |

Lifecycle processor của ApplicationContext tự khởi động các SmartLifecycle component có autoStartup=true sau khi context được refresh. Các component có phase thấp được khởi động trước; khi dừng context, thứ tự dừng diễn ra ngược lại. Nếu nhiều component cùng phase, không nên dựa vào thứ tự không được đảm bảo giữa chúng.

### 2.3 Endpoint là ranh giới lifecycle quan trọng

Trong một IntegrationFlow, endpoint thường là thành phần quyết định flow có đang nhận message hay không. Ví dụ:

- Event-driven consumer đăng ký subscriber lên channel khi start và hủy đăng ký khi stop.
- Polling consumer bắt đầu hoặc dừng lịch poll.
- Inbound channel adapter mở hoặc đóng kết nối tới hệ thống bên ngoài.
- Outbound endpoint có thể quản lý listener, connection hoặc tài nguyên riêng tùy loại adapter.

Channel có thể vẫn tồn tại như một bean trong khi endpoint phía sau đã dừng. Tương tự, service handler có thể vẫn tồn tại trong ApplicationContext nhưng không được gọi vì endpoint không còn nhận message.

Do đó, khi điều tra flow không hoạt động, cần kiểm tra trạng thái endpoint thay vì chỉ xác nhận bean channel hoặc service đã được tạo.

## 3. ApplicationContext khởi động IntegrationFlow như thế nào?

Một flow tĩnh được khai báo bằng @Bean thường được quản lý cùng ApplicationContext. Quá trình có thể hình dung như sau:

~~~mermaid
flowchart TD
    A["ApplicationContext đọc cấu hình"] --> B["Tạo bean và inject dependency"]
    B --> C["Spring Integration xử lý IntegrationFlow"]
    C --> D["Đăng ký channel, endpoint và handler"]
    D --> E["Khởi tạo các endpoint"]
    E --> F{"autoStartup có bật?"}
    F -->|Có| G["Lifecycle processor gọi start theo phase"]
    F -->|Không| H["Endpoint chờ lệnh start"]
    G --> I["Flow sẵn sàng nhận message"]
    H --> J["Ứng dụng hoặc controller gọi start"]
    J --> I
~~~

Các bước cần hiểu:

- Cấu hình flow được Spring đọc và tạo thành các bean runtime.
- Các endpoint hoàn tất khởi tạo sau khi dependency cần thiết sẵn sàng.
- Khi context refresh hoàn tất, lifecycle processor khởi động các SmartLifecycle component đủ điều kiện.
- Endpoint đăng ký subscriber, mở adapter hoặc lên lịch poll tùy loại endpoint.
- Khi endpoint chạy, message mới bắt đầu được nhận và xử lý theo channel tương ứng.

Đây là mô hình tổng quát. Một số adapter có thêm bước kết nối tới broker, server hoặc filesystem; vì vậy thời điểm kết nối thành công có thể muộn hơn thời điểm bean được tạo.

## 4. Điều khiển endpoint bằng autoStartup và phase

### 4.1 Tắt tự khởi động

Có thể đặt autoStartup(false) cho endpoint trong Java DSL để kiểm soát thời điểm bắt đầu:

~~~java
@Bean
IntegrationFlow controlledOrderFlow(OrderService orderService) {
    return IntegrationFlow.from("orders.controlled.input")
        .handle(orderService, "process", endpoint -> endpoint
            .id("controlled-order-handler")
            .autoStartup(false)
            .phase(100))
        .get();
}
~~~

Endpoint được đăng ký trong context nhưng không tự start. Một service có thể inject endpoint bean nếu có ID phù hợp, hoặc dùng cơ chế điều khiển lifecycle được cung cấp cho endpoint, rồi gọi start() khi điều kiện đã sẵn sàng.

Không nên tắt autoStartup rồi quên gọi start. Một flow như vậy có thể xuất hiện đầy đủ trong cấu hình và bean registry nhưng vẫn không nhận message.

### 4.2 Sắp xếp thứ tự bằng phase

Phase giúp xác định thứ tự lifecycle giữa các thành phần. Spring khởi động phase thấp trước và dừng phase cao trước.

Ví dụ, nếu downstream consumer phải sẵn sàng trước inbound source, có thể cho consumer phase thấp hơn và source phase cao hơn. Khi ứng dụng đóng, inbound source được dừng trước, còn consumer được giữ chạy thêm để xử lý phần message đã nhận.

~~~mermaid
flowchart LR
    A["Start: consumer<br/>phase thấp"] --> B["Start: inbound source<br/>phase cao"]
    B --> C["Ứng dụng xử lý message"]
    C --> D["Stop: inbound source<br/>phase cao trước"]
    D --> E["Stop: consumer<br/>phase thấp sau"]
~~~

Phase không thay thế việc thiết kế shutdown. Nó chỉ điều khiển thứ tự lifecycle; muốn drain message cần thêm chiến lược dừng producer, theo dõi backlog và chờ xử lý đang chạy.

## 5. Điều khiển nhiều endpoint bằng role

Role cho phép gán nhiều endpoint vào cùng một nhóm để start/stop đồng thời. Cách này hữu ích khi ứng dụng có nhiều flow chỉ được phép hoạt động trong một điều kiện nhất định, ví dụ chỉ instance đang giữ quyền leader mới được poll thư mục dùng chung.

Trong Java DSL, endpoint có thể được gán role:

~~~java
@Bean
IntegrationFlow clusteredInboundFlow(FileOrderService service) {
    return IntegrationFlow.from(
            messageSource(),
            endpoint -> endpoint
                .poller(Pollers.fixedDelay(5000))
                .role("cluster"))
        .handle(service, "process")
        .get();
}
~~~

Ở ví dụ này, messageSource() đại diện cho bean MessageSource do ứng dụng cung cấp; role được gán cho polling endpoint đọc nguồn đó.

Có thể dùng SmartLifecycleRoleController để điều khiển nhóm:

~~~java
@Service
class ClusterFlowLifecycle {

    private final SmartLifecycleRoleController roleController;

    ClusterFlowLifecycle(SmartLifecycleRoleController roleController) {
        this.roleController = roleController;
    }

    void onLeadershipGranted() {
        roleController.startLifecyclesInRole("cluster");
    }

    void onLeadershipRevoked() {
        roleController.stopLifecyclesInRole("cluster");
    }
}
~~~

Khi dùng leadership election, endpoint thuộc role cần đặt autoStartup(false) để context không tự khởi động trước khi ứng dụng xác định instance nào được quyền hoạt động. Nếu không, nhiều instance có thể cùng poll hoặc tiêu thụ một nguồn dữ liệu trong khoảng thời gian chưa xác định leader.

Role không phải security role hay phân quyền người dùng. Đây là nhãn lifecycle để nhóm các SmartLifecycle component.

## 6. Đăng ký và quản lý IntegrationFlow động

### 6.1 Khi nào nên tạo flow động?

Flow tĩnh phù hợp khi cấu trúc tích hợp được biết lúc phát triển hoặc lúc khởi động ứng dụng. Flow động phù hợp khi số lượng hoặc cấu hình flow thay đổi theo nghiệp vụ trong runtime.

Ví dụ một hệ thống kết nối nhiều tenant. Mỗi tenant có thể có một channel đầu vào và một handler cấu hình theo tenant. Khi tenant được kích hoạt, ứng dụng đăng ký flow; khi tenant bị vô hiệu hóa, ứng dụng dừng và gỡ flow tương ứng.

Không nên tạo flow động cho mọi message hoặc mọi request ngắn hạn nếu một flow tĩnh có thể phục vụ nhiều message. Mỗi flow động có thể tạo thêm endpoint, channel, bean và tài nguyên bên ngoài. Số lượng flow tăng không kiểm soát làm tăng chi phí bộ nhớ, thread và quản lý kết nối.

### 6.2 Đăng ký flow

IntegrationFlowContext cung cấp builder để cấu hình registration. Các bước thường là:

1. Tạo đối tượng IntegrationFlow theo cấu hình nghiệp vụ.
2. Đặt ID ổn định và duy nhất trong phạm vi ApplicationContext.
3. Chọn autoStartup phù hợp.
4. Gọi register() để thêm flow và các bean phụ thuộc vào context.
5. Lưu lại IntegrationFlowRegistration hoặc ID để quản lý về sau.

~~~java
IntegrationFlow flow = IntegrationFlow.from("tenant.acme.orders")
    .handle(orderService, "process")
    .get();

IntegrationFlowContext.IntegrationFlowRegistration registration =
    flowContext.registration(flow)
        .id("tenant-acme-orders")
        .autoStartup(false)
        .register();

registration.start();
~~~

Khi đăng ký với autoStartup mặc định, registration sẽ tự khởi động flow sau khi đăng ký thành công. Khi đặt false, ứng dụng phải gọi start() rõ ràng.

Flow động được đăng ký sau giai đoạn khởi tạo bean thông thường, vì vậy không chờ lifecycle processor của ApplicationContext đưa nó vào đợt tự khởi động ban đầu. IntegrationFlowContext quản lý thao tác đăng ký và khởi động flow: registration mặc định tự start sau khi register(), còn autoStartup(false) yêu cầu ứng dụng gọi start() khi sẵn sàng.

Registration có thể cung cấp input channel và MessagingTemplate để gửi message vào flow nếu flow bắt đầu bằng MessageChannel:

~~~java
MessageChannel input = registration.getInputChannel();
MessagingTemplate template = registration.getMessagingTemplate();

template.send(MessageBuilder.withPayload(order).build());
~~~

Không phải flow nào cũng có input channel để gửi trực tiếp. Nếu flow bắt đầu bằng inbound adapter hoặc source, MessagingTemplate không thể tự tạo một điểm vào message tùy ý cho flow đó.

### 6.3 Tạm dừng, chạy lại và gỡ flow

Có ba thao tác có ý nghĩa khác nhau:

| Thao tác | Ý nghĩa | Khi dùng |
|---|---|---|
| start() | Khởi động các thành phần lifecycle của registration | Bật flow đã đăng ký nhưng đang dừng |
| stop() | Dừng hoạt động của flow nhưng giữ registration và bean | Tạm ngừng xử lý để chờ điều kiện |
| remove(id) hoặc destroy() | Hủy flow và các bean phụ thuộc, dọn registry liên quan | Tenant hoặc kết nối không còn cần flow |

Ví dụ quản lý vòng đời:

~~~java
void disableTenant(String flowId) {
    IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.getRegistrationById(flowId);

    if (registration == null) {
        return;
    }

    registration.stop();
    flowContext.remove(flowId);
}
~~~

Nếu chỉ tạm ngừng tenant, gọi stop() và giữ registration để có thể start() lại. Khi tenant bị xóa vĩnh viễn, gọi remove(id) để hủy flow và các bean phụ thuộc. Không giữ tham chiếu tới channel, handler hoặc registration đã bị gỡ nếu không còn mục đích sử dụng.

### 6.4 Quản lý ID và registry

ID của flow được dùng để tìm registration và quản lý bean được tạo từ flow. Nên dùng ID có ý nghĩa nghiệp vụ, ổn định và không trùng với flow khác trong cùng context.

Ví dụ:

- tenant-acme-orders
- partner-bank-a-inbound
- device-gateway-42

Lưu ID ở nơi quản lý vòng đời của đối tượng nghiệp vụ. Không cần quét toàn bộ ApplicationContext để đoán flow nào thuộc tenant nào.

IntegrationFlowContext cung cấp getRegistry() và getRegistrationById() để quan sát các registration. Registry này hữu ích khi chẩn đoán flow động bị bỏ quên hoặc chưa được gỡ.

Khi tạo nhiều flow, cần giới hạn số lượng, xác định thời điểm hết hạn và có đường gỡ flow rõ ràng. Đăng ký thành công không có nghĩa tài nguyên sẽ tự biến mất khi nghiệp vụ kết thúc.

## 7. Dừng ứng dụng và giải phóng tài nguyên

### 7.1 Dừng context

Khi ApplicationContext đóng, Spring lifecycle processor dừng các SmartLifecycle component theo thứ tự phase ngược với lúc khởi động. Sau đó các destroy callback của bean được gọi theo cơ chế của Spring.

Đối với Spring Integration, điều này thường bao gồm:

- Dừng inbound adapter để ngừng nhận message mới.
- Dừng polling endpoint để không tạo thêm lượt poll.
- Hủy đăng ký consumer khỏi channel khi endpoint dừng.
- Dừng các thành phần quản lý kết nối hoặc listener.
- Giải phóng bean và tài nguyên được quản lý cùng context.

Bean service thông thường vẫn tuân theo lifecycle bean của Spring, nhưng không nhất thiết có start/stop. Không nên gọi start/stop tùy tiện trên mọi bean; chỉ điều khiển các đối tượng có hợp đồng lifecycle tương ứng.

### 7.2 Graceful shutdown và message đang xử lý

Dừng endpoint không tự động đảm bảo mọi message đã được xử lý xong. Với QueueChannel, message có thể còn trong queue. Với ExecutorChannel, task có thể đang chờ hoặc đang chạy trong executor. Với adapter kết nối bên ngoài, việc đóng socket hoặc session có thể ảnh hưởng tới thao tác đang diễn ra.

Một trình tự shutdown có kiểm soát thường là:

1. Ngừng nhận công việc mới từ nguồn bên ngoài.
2. Giữ downstream consumer hoạt động trong thời gian cần thiết để xử lý message đã nhận.
3. Theo dõi backlog, số task đang chạy và thời gian xử lý còn lại.
4. Dừng consumer sau khi đạt điều kiện drain hoặc hết thời gian chờ đã định.
5. Đóng executor, connection factory, session và tài nguyên liên quan.

Nếu dùng ThreadPoolTaskExecutor do ứng dụng khai báo, cấu hình chính sách shutdown phù hợp, ví dụ chờ task hoàn thành trong một khoảng thời gian. Cần xác định rõ điều gì xảy ra khi hết thời gian chờ: task còn lại bị ngắt, bị bỏ hay được xử lý lại sau khi ứng dụng khởi động.

Đối với message cần bảo đảm không mất khi process dừng đột ngột, hãy dùng cơ chế lưu trữ bền vững hoặc broker phù hợp. Queue trong bộ nhớ và thao tác stop thông thường không tạo ra bảo đảm durability.

### 7.3 stop khác destroy

stop là thao tác thay đổi trạng thái hoạt động. Bean và cấu hình vẫn tồn tại nên có thể khởi động lại nếu loại component hỗ trợ.

destroy hoặc remove là thao tác kết thúc vòng đời của registration và các bean phụ thuộc. Sau khi gỡ, ứng dụng cần đăng ký flow mới nếu muốn sử dụng lại.

Một lỗi thường gặp là chỉ stop flow rồi bỏ quên registration. Flow đã ngừng nhận message nhưng các bean, registry entry hoặc tài nguyên vẫn còn được tham chiếu. Nếu nghiệp vụ kết thúc vĩnh viễn, cần thực hiện remove/destroy và giải phóng các tham chiếu do ứng dụng tự giữ.

## 8. Kiểm tra trạng thái lifecycle trong runtime

Khi một flow không xử lý message, hãy kiểm tra theo các lớp:

| Câu hỏi | Nơi cần kiểm tra |
|---|---|
| ApplicationContext đã refresh thành công chưa? | Startup log, trạng thái ứng dụng |
| Flow đã được đăng ký chưa? | Bean registry hoặc IntegrationFlowContext registry |
| Endpoint có tồn tại không? | Bean name, endpoint ID, Integration Graph |
| Endpoint có đang chạy không? | isRunning(), lifecycle management |
| Endpoint có được auto-start không? | autoStartup và lệnh start() |
| Flow động có bị stop hoặc remove không? | IntegrationFlowRegistration và flowContext |
| Adapter có kết nối được hệ thống ngoài không? | Log kết nối, health và trạng thái adapter |
| Có message đang chờ không? | Queue depth, broker backlog, executor queue |
| Tài nguyên có bị giữ sau khi gỡ flow không? | Thread dump, connection metrics và heap dump |

Một quy trình chẩn đoán:

1. Xác định flow là bean tĩnh hay flow đăng ký động.
2. Với flow tĩnh, kiểm tra bean definition và endpoint ID trong context.
3. Với flow động, kiểm tra flowContext.getRegistrationById(id) và registry.
4. Kiểm tra isRunning, autoStartup và phase của endpoint.
5. Kiểm tra adapter, poller hoặc subscriber đã được kích hoạt chưa.
6. Nếu flow đã stop, xác định đó là tạm dừng có chủ đích hay lỗi lifecycle.
7. Nếu flow đã remove, tìm nơi ứng dụng còn giữ reference tới registration, channel hoặc bean phụ thuộc.
8. Đối chiếu log start/stop/destroy để xác định component nào chưa hoàn tất vòng đời.

Khi sử dụng Spring Boot Actuator và Spring Integration management phù hợp, integration graph và các metric có thể hỗ trợ quan sát thành phần tích hợp. Chúng bổ sung thông tin runtime nhưng không thay thế việc kiểm tra lifecycle và registry.

## 9. Tình huống thực tế: bật và gỡ flow của một tenant

Giả sử một tenant có thể được kích hoạt hoặc vô hiệu hóa khi ứng dụng đang chạy. TenantManager chịu trách nhiệm tạo flow và lưu ID của registration.

~~~mermaid
flowchart TD
    A["Tenant được kích hoạt"] --> B["Tạo IntegrationFlow"]
    B --> C["Đăng ký qua IntegrationFlowContext"]
    C --> D{"Cấu hình đã sẵn sàng?"}
    D -->|Chưa| E["Giữ registration ở trạng thái stopped"]
    D -->|Rồi| F["registration.start()"]
    F --> G["Flow nhận và xử lý message"]
    G --> H["Tenant bị vô hiệu hóa"]
    H --> I["Ngừng nguồn message"]
    I --> J["Chờ xử lý đang chạy / drain"]
    J --> K["flowContext.remove(id)"]
    K --> L["Giải phóng registration và bean phụ thuộc"]
~~~

Các điểm cần bảo đảm:

- ID của tenant phải ánh xạ tới đúng flow.
- Không đăng ký trùng flow cho cùng một tenant nếu nghiệp vụ chỉ cho phép một flow.
- Nếu đăng ký flow thất bại giữa chừng, service cần xử lý lỗi và không lưu một registration chưa hoàn chỉnh.
- Nếu tenant chỉ tạm khóa, dùng stop; nếu xóa tenant, gỡ flow.
- Khi remove, xóa các tham chiếu do TenantManager giữ tới channel và registration.
- Khi ứng dụng đóng, các flow động vẫn phải được dừng và giải phóng theo lifecycle của context.

Ví dụ này cũng cho thấy IntegrationFlowContext là công cụ quản lý cấu trúc flow trong runtime; nó không thay thế hệ thống lưu cấu hình tenant, cơ chế leader election, bảo đảm message hay quy trình retry.

## 10. Những nhầm lẫn cần tránh

- **ApplicationContext không phải IntegrationFlowContext**: ApplicationContext quản lý toàn bộ bean; IntegrationFlowContext chuyên quản lý IntegrationFlow đăng ký động.
- **IntegrationFlow không phải endpoint đơn lẻ**: flow mô tả một chuỗi thành phần; runtime có nhiều channel, endpoint và handler.
- **Tạo bean không đồng nghĩa endpoint đã chạy**: endpoint có thể bị tắt autoStartup hoặc chưa được start.
- **stop không đồng nghĩa remove**: stop giữ registration và bean; remove/destroy hủy flow cùng bean phụ thuộc.
- **IntegrationContextUtils không đăng ký flow**: đây là utility truy cập các bean hạ tầng từ BeanFactory.
- **autoStartup=false không tự bật lại**: ứng dụng phải gọi start hoặc dùng controller lifecycle phù hợp.
- **phase không phải độ ưu tiên xử lý message**: phase điều khiển thứ tự lifecycle start/stop, không điều khiển thứ tự message trong channel.
- **role không phải phân quyền**: role gom các SmartLifecycle component để điều khiển hoạt động theo nhóm.
- **Dừng endpoint không bảo đảm queue đã rỗng**: cần chiến lược drain và shutdown riêng.
- **Gỡ flow không xóa reference do ứng dụng giữ**: cần bỏ các tham chiếu tới registration, channel và tài nguyên đã gỡ.

## 11. Tự kiểm tra

1. ApplicationContext đã tạo channel và handler nhưng flow không nhận message. Bạn sẽ kiểm tra endpoint lifecycle và autoStartup như thế nào?
2. Điểm khác nhau giữa IntegrationFlowContext và IntegrationContextUtils là gì? API nào dùng để đăng ký flow động?
3. Một flow đăng ký động có autoStartup(false). Sau khi register(), vì sao flow chưa xử lý message và cần gọi thao tác nào?
4. Khi tenant bị tạm khóa, nên dùng stop() hay remove()? Khi tenant bị xóa vĩnh viễn, nên dùng thao tác nào?
5. Vì sao dừng một polling endpoint chưa chắc đã xử lý hết message trong queue?
6. Nếu downstream consumer phải sẵn sàng trước inbound source và được dừng sau inbound source, nên tổ chức phase theo nguyên tắc nào?
7. Khi nhiều endpoint phải chỉ chạy trên instance đang giữ leadership, có thể dùng role và SmartLifecycleRoleController ra sao?

## Tài liệu tham khảo

- [Spring Integration — IntegrationFlowContext API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Integration — StandardIntegrationFlow API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/StandardIntegrationFlow.html)
- [Spring Integration — AbstractEndpoint API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/endpoint/AbstractEndpoint.html)
- [Spring Integration — Endpoint Roles](https://docs.spring.io/spring-integration/reference/endpoint-roles.html)
- [Spring Integration — IntegrationContextUtils API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/context/IntegrationContextUtils.html)

## Kết luận

ApplicationContext quản lý bean và lifecycle chung của ứng dụng. Các endpoint Spring Integration tham gia lifecycle đó để đăng ký subscriber, khởi động poller hoặc adapter và giải phóng tài nguyên khi dừng. Với flow tĩnh, Spring quản lý các bean được khai báo trong context; với flow tạo động, IntegrationFlowContext cung cấp registration để start, stop, tra cứu và remove flow. Nắm rõ sự khác nhau giữa khởi tạo, start, stop và destroy giúp kiểm soát trạng thái runtime, tránh endpoint bị bỏ quên và đóng ứng dụng có trật tự.
