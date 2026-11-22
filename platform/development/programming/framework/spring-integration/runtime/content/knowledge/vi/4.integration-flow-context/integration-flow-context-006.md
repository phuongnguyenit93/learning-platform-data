# Chọn lúc đăng ký flow trong ứng dụng

Một `IntegrationFlow` có thể được khai báo cố định cùng Spring ApplicationContext hoặc được tạo và đăng ký khi ứng dụng đang chạy. Lựa chọn này quyết định thời điểm endpoint xuất hiện, lúc nào consumer bắt đầu nhận message, dependency nào phải sẵn sàng và ai chịu trách nhiệm dừng, gỡ flow.

`IntegrationFlowContext` phục vụ trường hợp cần đăng ký flow động. Tuy nhiên, đăng ký động không phải lựa chọn mặc định cho mọi flow. Nếu topology đã biết khi viết ứng dụng và luôn tồn tại, khai báo flow bằng `@Bean` thường dễ quản lý hơn. Chỉ nên đăng ký lúc runtime khi thời điểm hoặc cấu trúc flow thực sự phụ thuộc vào cấu hình, tenant, đối tác hay một sự kiện trong vòng đời nghiệp vụ.

## 1. Hai cách đưa IntegrationFlow vào ApplicationContext

### Flow tĩnh bằng @Bean

Khi topology ổn định, khai báo flow như một bean:

~~~java
@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.input")
                .handle(orderService, "process")
                .get();
    }
}
~~~

Spring tạo và đăng ký flow trong quá trình khởi tạo ApplicationContext. Các endpoint thuộc flow tham gia vòng đời bean và lifecycle của Spring Integration. Cách này phù hợp khi ứng dụng luôn có cùng các channel, handler và quy tắc định tuyến sau mỗi lần khởi động.

Ưu điểm là cấu hình thể hiện rõ trong mã nguồn, dependency được inject theo cách thông thường, lỗi cấu hình thường xuất hiện ngay lúc khởi động và Spring quản lý vòng đời endpoint. Không cần tự lưu registration ID hoặc viết logic gỡ flow khi ứng dụng tắt.

### Flow động bằng IntegrationFlowContext

Khi flow chỉ tồn tại sau một điều kiện runtime, có thể xây dựng đối tượng `IntegrationFlow` rồi đăng ký bằng `IntegrationFlowContext`:

~~~java
IntegrationFlow flow = IntegrationFlow.from(MessageChannels.direct())
        .handle((payload, headers) -> partnerService.process(partnerId, payload))
        .get();

IntegrationFlowRegistration registration = flowContext.registration(flow)
        .id("partner-" + partnerId)
        .useFlowIdAsPrefix()
        .register();
~~~

`registration(...)` tạo builder cho lần đăng ký. `id(...)` đặt ID ổn định để tra cứu và gỡ flow; `useFlowIdAsPrefix()` giúp tên các component được tạo trong flow có prefix riêng, giảm nguy cơ trùng tên khi đăng ký nhiều flow có cấu trúc giống nhau. `register()` đưa flow và các component liên quan vào Integration context, đồng thời trả về `IntegrationFlowRegistration` để thao tác với flow vừa đăng ký.

Registration cung cấp các khả năng như lấy input channel, truy cập flow và điều khiển lifecycle. Ví dụ, khi flow dùng input channel được tạo từ DSL, có thể gửi message qua `registration.getInputChannel()`. Khi không còn cần flow, dùng `IntegrationFlowContext.remove(flowId)` để gỡ registration cùng các bean do registration quản lý.

## 2. Chọn thời điểm dựa trên vòng đời ứng dụng

Thời điểm đăng ký nên được quyết định từ hai câu hỏi: dữ liệu nào cần có để xây dựng flow và nguồn message nào có thể bắt đầu gửi ngay khi flow hoạt động?

| Thời điểm | Khi phù hợp | Điều cần kiểm soát |
|---|---|---|
| Khai báo `@Bean` lúc context khởi tạo | Topology cố định, dependency đã có trong context | Dependency injection và thứ tự lifecycle của endpoint |
| `ApplicationRunner` hoặc `CommandLineRunner` | Cần đọc cấu hình ban đầu từ database hoặc file sau khi context refresh | Đăng ký xong trước khi ứng dụng báo ready; phối hợp với inbound endpoint đã auto-start |
| `ApplicationReadyEvent` | Flow chỉ cần có sau khi các runner hoàn tất và ứng dụng gần đạt trạng thái sẵn sàng | Nếu flow nhận message đầu vào, phải bảo đảm nguồn gửi chưa phát message trước khi listener đăng ký xong |
| Sự kiện nghiệp vụ hoặc quản trị | Tenant được kích hoạt, đối tác được cấu hình hoặc tính năng được bật khi runtime | Đăng ký idempotent, ID duy nhất, cleanup khi cấu hình bị gỡ |
| Một thao tác quản trị rõ ràng | Người vận hành chủ động bật/tắt một tích hợp | Phân quyền, xác thực đầu vào và trạng thái đăng ký có thể quan sát |

Không nên đăng ký flow trong constructor. Tại thời điểm đó, các callback aware và một phần quá trình cấu hình bean chưa hoàn tất. `@PostConstruct` cũng không phải điểm mặc định tốt cho đăng ký động: nó chạy trong quá trình tạo bean, trước khi toàn bộ context và các lifecycle component chắc chắn đã sẵn sàng.

Nếu flow phải tồn tại trước khi ứng dụng nhận traffic, `ApplicationRunner` thường là điểm dễ hiểu: context đã refresh, các dependency đã được inject và runner chạy trước `ApplicationReadyEvent`. Tuy vậy, một inbound adapter triển khai `SmartLifecycle` có thể đã tự start trong quá trình refresh. Nếu nguồn đó có thể phát message ngay, runner đăng ký flow có thể đến sau message đầu tiên. Khi cần thứ tự nghiêm ngặt, hãy giữ inbound endpoint ở trạng thái chưa start, đăng ký và start flow trước, rồi mới start nguồn nhận message; hoặc điều phối các thành phần bằng lifecycle phase phù hợp.

`ContextRefreshedEvent` không nên được dùng một cách máy móc cho mọi lần đăng ký. Sự kiện này có thể được phát nhiều lần trong ứng dụng có parent/child context hoặc khi context refresh. Nếu dùng listener, phải xác định đúng context cần xử lý và làm cho thao tác đăng ký có tính idempotent.

## 3. Trình tự khởi động để không mất message

Với một flow động làm consumer cho inbound source, thứ tự mong muốn thường là:

~~~mermaid
sequenceDiagram
    participant App as ApplicationContext
    participant Config as Configuration Store
    participant Flow as IntegrationFlowContext
    participant Source as Inbound Adapter
    App->>Config: Đọc cấu hình tích hợp cần bật
    Config-->>App: Danh sách cấu hình hợp lệ
    App->>Flow: Tạo và register các IntegrationFlow
    Flow-->>App: Trả IntegrationFlowRegistration
    App->>Flow: start() các flow đã kiểm tra
    App->>Source: start() nguồn nhận message
    Source->>Flow: Gửi message vào input channel
~~~

Nếu nguồn nhận message đã chạy trước bước đăng ký, message có thể đến khi chưa có subscriber. Kết quả phụ thuộc loại channel và cách nguồn gửi: gửi đồng bộ có thể thất bại vì chưa có consumer; queue có thể giữ message chờ; broker có thể retry hoặc giữ message theo semantics của broker. Không nên dựa vào may rủi đó. Hãy chủ động định nghĩa thứ tự start và chính sách khi flow chưa sẵn sàng.

Có thể tách đăng ký và khởi động thành hai pha bằng `autoStartup(false)`:

~~~java
IntegrationFlowRegistration registration = flowContext.registration(flow)
        .id(flowId)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();

// Kiểm tra dependency và trạng thái cần thiết trước khi nhận message.
registration.start();
~~~

`autoStartup(false)` giúp ứng dụng đăng ký flow trước nhưng chưa chủ động start các endpoint theo lifecycle của registration. Chỉ gọi `start()` khi dependency và đường vào đã sẵn sàng. Nếu muốn giữ flow ở trạng thái đăng ký nhưng chưa nhận traffic, đừng expose input channel cho producer trước thời điểm đó.

Với yêu cầu điều phối startup phức tạp, có thể dùng `SmartLifecycle` để quản lý start/stop và phase. Phase quyết định thứ tự các lifecycle component được start và stop; hãy chọn phase dựa trên quan hệ phụ thuộc thực tế, rồi xác minh thứ tự bằng log khi ứng dụng khởi động. Đừng giả định thứ tự chỉ từ thứ tự khai báo các method `@Bean`.

## 4. Đăng ký flow khi cấu hình runtime thay đổi

Một trường hợp điển hình là mỗi đối tác có một flow riêng, hoặc một tenant chỉ có flow sau khi được kích hoạt. Flow được tạo khi cấu hình đã hợp lệ, không cần tạo lại ở mỗi message.

~~~java
@Component
public class PartnerFlowRegistrar {

    private final IntegrationFlowContext flowContext;
    private final PartnerService partnerService;
    private final Map<String, IntegrationFlowRegistration> registrations =
            new HashMap<>();

    public PartnerFlowRegistrar(IntegrationFlowContext flowContext,
                                PartnerService partnerService) {
        this.flowContext = flowContext;
        this.partnerService = partnerService;
    }

    public synchronized IntegrationFlowRegistration register(String partnerId) {
        String flowId = "partner-" + partnerId;
        IntegrationFlowRegistration existing = registrations.get(flowId);
        if (existing != null) {
            return existing;
        }

        IntegrationFlow flow = IntegrationFlow.from(MessageChannels.direct())
                .handle((payload, headers) ->
                        partnerService.process(partnerId, payload))
                .get();

        IntegrationFlowRegistration registration = flowContext.registration(flow)
                .id(flowId)
                .useFlowIdAsPrefix()
                .autoStartup(false)
                .register();

        registrations.put(flowId, registration);
        registration.start();
        return registration;
    }

    public synchronized void unregister(String partnerId) {
        String flowId = "partner-" + partnerId;
        if (registrations.remove(flowId) != null) {
            flowContext.remove(flowId);
        }
    }
}
~~~

Ví dụ dùng `synchronized` để hai sự kiện kích hoạt cùng đối tác không đồng thời tạo hai registration cùng ID trong instance này. Ứng dụng nhiều instance vẫn cần quy tắc phân công rõ ràng: nếu mọi instance đều nhận sự kiện tenant activated và cùng tạo consumer, có thể phát sinh xử lý trùng. Hãy quyết định flow thuộc về một instance, một nhóm instance hay tất cả instance; dùng distributed lock, partition hoặc cơ chế điều phối phù hợp nếu chỉ một instance được phép sở hữu consumer.

Trong ví dụ, `registrations` là registry trong bộ nhớ của registrar. Khi ứng dụng khởi động lại, map sẽ trống; ứng dụng phải đọc lại danh sách đối tác đang hoạt động từ nguồn cấu hình bền vững và đăng ký lại. Không xem map trong bộ nhớ là nguồn dữ liệu chính về trạng thái tích hợp.

ID flow phải ổn định và duy nhất trong context. Nếu ID được tạo từ mã tenant hoặc partner bên ngoài, hãy chuẩn hóa ký tự và giới hạn độ dài trước khi dùng làm bean name. Không dùng tên ngẫu nhiên mỗi lần restart nếu không cần nhiều phiên bản đồng thời; ID ổn định giúp quan sát, kiểm tra và gỡ đúng flow.

## 5. Chọn thời điểm theo từng tình huống

### Topology luôn có khi ứng dụng chạy

Dùng `@Bean`. Ví dụ: flow nhận đơn hàng, kiểm tra dữ liệu, lưu database và phát event luôn tồn tại. Đưa cấu hình vào ApplicationContext để dependency và lifecycle được quản lý nhất quán.

### Topology phụ thuộc cấu hình có sẵn khi khởi động

Đọc cấu hình trong `ApplicationRunner`, kiểm tra tính hợp lệ rồi đăng ký flow. Cách này phù hợp khi danh sách tenant hoặc đối tác được lưu trong database và có thể thay đổi giữa các lần triển khai. Nếu inbound source có thể phát message ngay trong lúc runner chạy, phải điều phối việc start source như phần trước.

### Topology thay đổi trong lúc ứng dụng đang hoạt động

Dùng service quản lý flow và gọi `IntegrationFlowContext` khi có sự kiện cấu hình. Ví dụ: đối tác được kích hoạt thì đăng ký flow; đối tác bị vô hiệu hóa thì dừng và gỡ flow. Hành động cần idempotent vì event có thể được phát lại hoặc xử lý lại.

### Flow chỉ cần cho một thao tác ngắn hạn

Hãy cân nhắc dùng một flow ổn định với router hoặc cấu hình thay đổi thay vì tạo và hủy flow liên tục. Đăng ký flow có chi phí tạo bean, endpoint và lifecycle; tạo flow theo từng request dễ gây rò rỉ component, tăng số lượng bean và làm runtime khó quan sát. Chỉ dùng flow tạm thời khi có ranh giới vòng đời rõ ràng và cơ chế cleanup đáng tin cậy.

## 6. Thay đổi cấu hình và gỡ flow an toàn

Khi cấu hình của một flow thay đổi, đừng chỉ đăng ký một flow mới với ID khác rồi bỏ quên flow cũ. Cần xác định chiến lược thay thế:

1. Ngừng nhận message mới vào flow cũ hoặc chuyển nguồn sang một điểm vào khác.
2. Xử lý hoặc chờ các message đang chạy theo chính sách drain đã chọn.
3. Dừng và gỡ registration cũ bằng `IntegrationFlowContext.remove(flowId)`.
4. Đăng ký flow mới với cấu hình đã kiểm tra.
5. Start flow mới và chuyển traffic vào nó.

Nếu yêu cầu không được gián đoạn, có thể đăng ký flow phiên bản mới song song với ID và input riêng, kiểm tra nó trước rồi chuyển producer hoặc router sang phiên bản mới. Chỉ gỡ flow cũ sau khi không còn message cần xử lý. Tránh để hai flow cùng nhận một nguồn message nếu thao tác phía sau không idempotent.

Gỡ flow không tự giải quyết mọi trạng thái nghiệp vụ bên ngoài flow. Message đang nằm trong broker, queue hoặc MessageStore cần được xử lý theo chính sách của chính thành phần lưu trữ đó. Trước khi xóa registration, hãy xác định message đang ở đâu, có cần drain hay chuyển tiếp không và ai chịu trách nhiệm với message chưa hoàn tất.

## 7. Các lỗi thường gặp khi chọn sai thời điểm

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Message đến trước khi flow có consumer | Inbound adapter start trước registration | Đăng ký/start flow trước source hoặc giữ source `autoStartup(false)` |
| Đăng ký flow thất bại do tên bean trùng | ID hoặc tên component không duy nhất | Dùng flow ID ổn định, prefix tên component và kiểm tra duplicate trước khi register |
| Cùng tenant có nhiều flow | Event lặp, nhiều thread hoặc nhiều instance cùng đăng ký | Idempotency trong instance và cơ chế ownership phân tán nếu cần |
| Flow không xuất hiện sau khi bật tenant | Listener không nhận event, cấu hình chưa hợp lệ hoặc đăng ký lỗi | Log flow ID, trạng thái đăng ký, lỗi tạo bean và trạng thái start |
| Tắt tenant nhưng message vẫn được xử lý | Registration chưa được remove hoặc message đã nằm trong queue/broker | Gỡ flow và xử lý riêng message còn tồn đọng theo semantics của nguồn |
| Số lượng bean tăng theo thời gian | Tạo flow theo request hoặc không cleanup | Chỉ đăng ký theo đơn vị cấu hình có vòng đời rõ ràng; gỡ khi không còn sử dụng |
| Ứng dụng báo ready nhưng flow chưa sẵn sàng | Đăng ký ở thời điểm quá muộn hoặc không tham gia readiness | Đăng ký trong runner hoặc đưa trạng thái flow vào cơ chế readiness của ứng dụng |

## 8. Quan sát và kiểm tra trạng thái đăng ký

Mỗi lần đăng ký hoặc gỡ flow nên có log cấu trúc gồm flow ID, lý do thay đổi, tenant/partner đã được che hoặc mã hóa theo chính sách, thời điểm và kết quả. Không ghi credential hoặc toàn bộ cấu hình kết nối vào log.

Khi vận hành, cần phân biệt ít nhất bốn trạng thái:

- **Chưa đăng ký:** chưa có registration trong `IntegrationFlowContext`.
- **Đã đăng ký, chưa start:** flow và endpoint đã được tạo nhưng chưa nhận message theo lifecycle.
- **Đang hoạt động:** registration đã start; cần kiểm tra thêm channel, consumer và dependency phía sau.
- **Đã gỡ:** registration đã được remove; message còn ở broker/queue vẫn có vòng đời riêng.

Có thể tra registration bằng ID qua `IntegrationFlowContext` và xem input channel của registration. Kết hợp Integration Graph, log của endpoint và metric để xác nhận topology runtime. Chỉ nhìn thấy registration không chứng minh message đang được xử lý thành công; cần kiểm tra consumer có hoạt động, backlog có tăng và error flow có nhận lỗi hay không.

Nên theo dõi số lượng flow đang đăng ký, số flow đang start, số lần đăng ký thất bại, thời gian đăng ký và số lần gỡ. Với flow theo tenant, các metric này giúp phát hiện trường hợp event lặp làm tăng số component hoặc một nhóm tenant không được kích hoạt đúng cách.

## 9. Checklist quyết định thời điểm đăng ký

- [ ] Topology có cố định trong mọi lần chạy không? Nếu có, ưu tiên khai báo `@Bean`.
- [ ] Nếu flow động, đã biết điều kiện nào làm flow cần xuất hiện và điều kiện nào làm flow phải bị gỡ chưa?
- [ ] Dependency và cấu hình cần thiết đã sẵn sàng trước khi gọi `register()` chưa?
- [ ] Inbound source có thể phát message trước khi flow start không?
- [ ] Có cần `autoStartup(false)` để tách đăng ký khỏi khởi động không?
- [ ] Flow ID có ổn định, duy nhất và an toàn khi dùng làm bean name không?
- [ ] Sự kiện lặp hoặc nhiều thread có thể tạo registration trùng không?
- [ ] Khi cập nhật hoặc vô hiệu hóa cấu hình, ai dừng flow và xử lý message còn tồn đọng?
- [ ] Sau restart, ứng dụng có thể dựng lại các flow đang hoạt động từ nguồn cấu hình bền vững không?
- [ ] Log, metric và Integration Graph có giúp biết flow đã đăng ký, đã start hay đã gỡ không?

Hãy chọn thời điểm đăng ký từ vòng đời thật của topology và nguồn message. Flow tĩnh nên thuộc cấu hình ApplicationContext; flow động nên được tạo khi cấu hình đã hợp lệ và trước khi producer có thể gửi message vào nó. Khi đã đăng ký, ứng dụng cần giữ được ID, trạng thái start/stop và quy tắc cleanup để vòng đời của flow không tách rời vòng đời nghiệp vụ.

## Tài liệu tham khảo

- [Spring Integration Reference: Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration API: IntegrationFlowContext](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Boot Reference: Application Events and Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Framework Reference: Lifecycle callbacks and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
