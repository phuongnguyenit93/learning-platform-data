# Quản lý flow động trong multi-tenant hoặc plugin

Trong **SPRING_INTEGRATION_RUNTIME**, một IntegrationFlow thường được khai báo thành bean khi ứng dụng khởi động. Tuy nhiên, có những hệ thống chỉ biết cấu hình tích hợp sau khi chạy: mỗi tenant có một nguồn dữ liệu hoặc thông tin kết nối riêng, một plugin được bật/tắt theo cấu hình, hoặc một đối tác chỉ hoạt động trong một khoảng thời gian. Khi đó, ứng dụng có thể đăng ký và gỡ IntegrationFlow ngay trong runtime bằng **IntegrationFlowContext**.

Quản lý flow động đòi hỏi nhiều hơn một lệnh register(). Ứng dụng cần định danh flow ổn định, tránh trùng tên bean, kiểm soát trạng thái start/stop, bảo đảm dữ liệu giữa các tenant không trộn lẫn, xử lý cập nhật cấu hình đồng thời và giải phóng tài nguyên khi tenant hoặc plugin bị gỡ. Bài này tập trung vào các quyết định đó, cùng cách vận hành khi ứng dụng có nhiều instance.

## 1. Khi nào nên dùng flow động?

Flow động phù hợp khi số lượng hoặc cấu hình tích hợp thay đổi trong thời gian ứng dụng chạy. Một số tình huống thường gặp:

- **Multi-tenant**: mỗi tenant có endpoint, thông tin xác thực, lịch poll hoặc đích gửi riêng.
- **Plugin**: module mở rộng có thể được cài, bật, tạm dừng hoặc gỡ mà không cần viết lại cấu hình toàn ứng dụng.
- **Đối tác tích hợp**: kết nối chỉ được tạo sau khi quản trị viên khai báo đối tác hoặc hoàn tất quy trình onboarding.
- **Thiết bị hoặc phiên kết nối**: một flow chỉ tồn tại khi thiết bị trực tuyến hoặc một phiên tích hợp còn hiệu lực.
- **Cấu hình thay đổi**: endpoint, bộ lọc hoặc chính sách xử lý cần được thay thế theo phiên bản cấu hình mới.

Ví dụ, một nền tảng bán hàng có nhiều tenant. Tenant A gửi đơn hàng qua HTTP, tenant B đọc đơn hàng từ SFTP, còn tenant C nhận message từ broker. Các tenant có thể dùng cùng logic nghiệp vụ ở một số bước, nhưng nguồn message, credential và lịch nhận dữ liệu khác nhau. Tạo flow riêng giúp quản lý vòng đời từng kết nối độc lập.

Không phải cứ có nhiều tenant là phải tạo nhiều flow. Nếu mọi tenant dùng cùng một giao thức, cùng cấu trúc message và cùng cách xử lý, một flow chung kết hợp router hoặc service định tuyến theo tenant thường đơn giản và tiết kiệm tài nguyên hơn. Flow động nên được chọn khi cấu trúc endpoint hoặc cấu hình runtime thực sự khác nhau.

## 2. So sánh flow tĩnh, flow động và router dùng chung

| Mô hình | Cách tổ chức | Điểm mạnh | Chi phí và giới hạn |
|---|---|---|---|
| Flow tĩnh | Khai báo IntegrationFlow bằng bean lúc khởi động | Dễ kiểm tra cấu hình, dễ quan sát, phù hợp số lượng flow cố định | Thay đổi cấu trúc thường cần cập nhật cấu hình hoặc khởi động lại |
| Flow động theo tenant/plugin | Đăng ký mỗi flow qua IntegrationFlowContext | Vòng đời từng tenant hoặc plugin độc lập; cấu hình có thể tạo khi runtime | Nhiều endpoint, channel và tài nguyên hơn; phải quản lý register/remove |
| Một flow chung + router | Một flow nhận message và định tuyến theo tenant hoặc loại plugin | Ít bean, ít endpoint, dễ mở rộng số tenant lớn khi xử lý giống nhau | Khó cô lập lịch poll, credential hoặc cấu trúc tích hợp khác biệt |

Một cách chọn thực tế:

- Chọn **flow tĩnh** khi số luồng đã biết trước và hiếm khi thay đổi.
- Chọn **flow động** khi mỗi tenant/plugin cần một tập endpoint hoặc tài nguyên riêng và phải có lifecycle độc lập.
- Chọn **router dùng chung** khi tenant chỉ khác dữ liệu hoặc chính sách nhỏ, còn cấu trúc xử lý giống nhau.
- Có thể kết hợp: một số flow nền dùng chung, còn các adapter kết nối đối tác được đăng ký động.

Flow động giải quyết việc tạo và quản lý cấu trúc tích hợp. Nó không tự cung cấp cơ chế phân quyền tenant, lưu cấu hình, leader election, bảo đảm message hoặc đồng bộ trạng thái giữa các node.

## 3. IntegrationFlowContext và registration

### 3.1 Vai trò của IntegrationFlowContext

IntegrationFlowContext là API của Spring Integration Java DSL để đăng ký IntegrationFlow trong ApplicationContext khi ứng dụng đang chạy. API này cung cấp builder tạo registration, tra cứu registration đã đăng ký và gỡ flow theo ID.

Các thao tác cốt lõi:

1. Tạo IntegrationFlow từ cấu hình nghiệp vụ.
2. Gọi flowContext.registration(flow) để bắt đầu cấu hình registration.
3. Đặt ID duy nhất cho flow.
4. Chọn có tự khởi động sau khi đăng ký hay không.
5. Có thể bật useFlowIdAsPrefix() để prefix tên bean do flow tạo ra.
6. Gọi register() để đăng ký flow.
7. Dùng registration để lấy input channel, gửi message, kiểm tra hoặc điều khiển lifecycle.
8. Dùng flowContext.remove(id) khi cần gỡ flow và các bean được đăng ký cùng flow.

Một registration đại diện cho một IntegrationFlow đã được thêm vào runtime. Kiểu API thường dùng là IntegrationFlowContext.IntegrationFlowRegistration.

### 3.2 ID của flow phải ổn định và duy nhất

ID giúp tìm registration và gỡ đúng flow khi tenant/plugin thay đổi trạng thái. Nên tạo ID từ loại đối tượng và định danh đã chuẩn hóa, ví dụ:

- tenant-acme-orders
- tenant-northwind-sftp
- plugin-inventory-v2
- partner-bank-a-inbound

Không dùng trực tiếp một chuỗi tùy ý từ request bên ngoài làm ID. Hãy xác thực định danh tenant/plugin, giới hạn độ dài và chuẩn hóa ký tự trước khi tạo tên. Nếu ID có thể chứa dấu cách, dấu phân cách không mong muốn hoặc dữ liệu do người dùng kiểm soát, hãy chuyển nó thành dạng slug an toàn.

Không tái sử dụng cùng một ID cho hai flow đang tồn tại. Nếu cần thay thế flow, hãy thực hiện quy trình update có kiểm soát: dừng hoặc chuyển nguồn nhận message, gỡ registration cũ, sau đó đăng ký flow mới; hoặc dùng ID phiên bản mới rồi chuyển traffic theo một bước được quản lý rõ ràng.

### 3.3 useFlowIdAsPrefix tránh trùng tên bean

Một flow thường tạo ra nhiều bean nội bộ như channel, endpoint, handler và các thành phần phụ trợ. Khi đăng ký nhiều flow động, các tên bean được sinh tự động có thể trùng nhau nếu không được phân biệt.

useFlowIdAsPrefix() yêu cầu Spring Integration dùng ID flow làm prefix cho tên bean được tạo từ flow. Đây là lựa chọn hữu ích khi một ứng dụng đăng ký nhiều flow có cấu trúc tương tự.

Ví dụ, hai tenant có thể dùng cùng một cấu trúc transform → handle. Prefix theo flow ID giúp các thành phần runtime của tenant-acme-orders và tenant-northwind-orders có namespace riêng.

Prefix không thay thế ID duy nhất và cũng không tự cô lập dữ liệu. Nó giải quyết xung đột tên bean trong ApplicationContext. Ứng dụng vẫn phải định tuyến message đúng tenant và kiểm soát quyền truy cập dữ liệu.

## 4. Ví dụ: đăng ký một flow cho từng tenant

Giả sử mỗi tenant có một channel đầu vào riêng về mặt runtime và cùng gọi dịch vụ xử lý đơn hàng. Tenant ID được lấy từ cấu hình đã xác thực, sau đó được gắn vào message trong flow để các bước sau có thể ghi log, correlation và kiểm tra quyền.

~~~java
public record TenantConfig(String tenantId) {
}

public interface TenantOrderService {
    OrderResult process(String tenantId, Order order);
}

@Service
public class TenantFlowManager {

    private final IntegrationFlowContext flowContext;
    private final TenantOrderService orderService;

    public TenantFlowManager(
            IntegrationFlowContext flowContext,
            TenantOrderService orderService) {
        this.flowContext = flowContext;
        this.orderService = orderService;
    }

    public IntegrationFlowContext.IntegrationFlowRegistration register(
            TenantConfig tenant) {

        String flowId = "tenant-" + tenant.tenantId() + "-orders";

        if (flowContext.getRegistrationById(flowId) != null) {
            throw new IllegalStateException(
                "Flow already registered: " + flowId);
        }

        IntegrationFlow flow = IntegrationFlow
            .from(MessageChannels.direct())
            .enrichHeaders(headers ->
                headers.header("tenantId", tenant.tenantId()))
            .<Order>handle((order, messageHeaders) ->
                orderService.process(tenant.tenantId(), order))
            .get();

        return flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();
    }
}
~~~

Ví dụ lược bỏ import và các kiểu Order/OrderResult của ứng dụng. Flow dùng DirectChannel làm input channel, gắn tenantId từ TenantConfig đã được xác thực, rồi gọi service nghiệp vụ. Tenant ID không được lấy từ một header tùy ý do client gửi lên.

Có thể khởi động registration sau khi các điều kiện phụ thuộc đã sẵn sàng:

~~~java
IntegrationFlowContext.IntegrationFlowRegistration registration =
    tenantFlowManager.register(tenantConfig);

registration.start();
~~~

Nếu flow bắt đầu bằng một MessageChannel, registration có thể cung cấp MessagingTemplate để gửi message vào flow:

~~~java
registration.getMessagingTemplate()
    .send(MessageBuilder.withPayload(order).build());
~~~

Hoặc ứng dụng có thể lấy input channel và gửi Message trực tiếp. Không phải mọi flow đều có input channel dùng cho producer; flow bắt đầu bằng inbound adapter hoặc source có cách nhận message riêng.

### 4.1 Vì sao gắn tenantId trong flow?

Tenant ID được gắn từ cấu hình đã xác thực để các bước tiếp theo có thể:

- Ghi log và metric theo tenant.
- Tạo correlation key có namespace tenant.
- Chọn chính sách retry hoặc error handling phù hợp.
- Kiểm tra dữ liệu trước khi gọi repository hoặc service.
- Gửi kết quả tới đúng đích của tenant.

Không coi header tenantId là bằng chứng phân quyền. Một message có thể được tạo từ nguồn không đáng tin cậy. Điểm vào phải xác định tenant từ danh tính đã xác thực hoặc từ adapter được cấu hình riêng, rồi mới tạo header nội bộ. Các service truy cập dữ liệu vẫn cần kiểm tra tenant boundary.

## 5. Quản lý vòng đời tenant

Một tenant thường đi qua nhiều trạng thái: chưa cấu hình, đã cấu hình, đang kích hoạt, đang chạy, tạm dừng, đang gỡ và đã gỡ. Flow manager cần ánh xạ trạng thái nghiệp vụ này tới registration.

| Trạng thái tenant | Trạng thái flow dự kiến | Hành động |
|---|---|---|
| Chưa cấu hình | Chưa có registration | Không tạo flow |
| Đã cấu hình | Đã đăng ký nhưng chưa chạy, nếu cần chờ điều kiện | Validate config và register |
| Đang kích hoạt | Registration đang được start | Mở kết nối hoặc bật endpoint |
| Đang chạy | Registration running | Nhận và xử lý message |
| Tạm dừng | Registration stopped | Dừng nhận message, giữ registration để chạy lại |
| Đang gỡ | Đang dừng và dọn tài nguyên | Ngừng nguồn, drain nếu cần, remove |
| Đã gỡ | Không còn registration | Xóa mapping và tài nguyên tenant |

Nên coi việc activate/deactivate là một quy trình có trạng thái rõ ràng. Không chỉ lưu một boolean enabled trong database rồi giả định flow đã được bật hoặc tắt thành công.

### 5.1 Kích hoạt tenant

Một trình tự kích hoạt thường gồm:

1. Đọc cấu hình tenant từ nguồn tin cậy.
2. Kiểm tra tenant đang hoạt động và người yêu cầu có quyền bật tích hợp.
3. Xác thực endpoint, credential, lịch poll và chính sách xử lý.
4. Tạo IntegrationFlow cùng các thành phần cần thiết.
5. Đăng ký flow với ID ổn định và useFlowIdAsPrefix().
6. Kiểm tra các dependency như connection factory hoặc remote endpoint.
7. Gọi start() khi flow sẵn sàng nhận message.
8. Lưu trạng thái ACTIVE và ID registration sau khi thao tác thành công.

Nếu register() thành công nhưng start() thất bại, flow không nên được báo là ACTIVE. Cần ghi nhận lỗi, dừng hoặc gỡ registration tùy trạng thái và cho phép retry activation an toàn.

### 5.2 Tạm dừng tenant

Tạm dừng có nghĩa tenant sẽ không nhận công việc mới trong thời gian chờ. Nếu cần tiếp tục sau đó, giữ registration và dùng stop()/start() theo lifecycle của nó.

Tuy nhiên, dừng cả registration có thể dừng nhiều endpoint trong flow cùng lúc. Nếu yêu cầu là ngừng nguồn nhận message mới nhưng vẫn để downstream consumer xử lý backlog, hãy thiết kế source và processing thành các ranh giới lifecycle có thể điều khiển riêng. Chỉ gọi stop() trên toàn registration không tự bảo đảm queue đã được drain.

### 5.3 Gỡ tenant

Khi tenant bị xóa vĩnh viễn:

1. Ngăn tạo thêm message từ nguồn bên ngoài.
2. Xác định message đang chờ hoặc task đang xử lý.
3. Chờ drain theo chính sách và giới hạn thời gian đã chọn.
4. Dừng các endpoint còn hoạt động.
5. Gọi flowContext.remove(flowId) để gỡ registration.
6. Đóng connection, client hoặc tài nguyên riêng của tenant nếu ứng dụng sở hữu chúng.
7. Xóa mapping tenant → flow ID và tham chiếu tới registration/channel.
8. Ghi nhận trạng thái đã gỡ.

remove(id) là thao tác gỡ flow khỏi IntegrationFlowContext. Nếu cần bảo đảm xử lý message trước khi gỡ, phải thiết kế bước drain trước đó; remove không phải một cam kết xử lý hết backlog.

## 6. Quản lý plugin có thể cài, bật và gỡ

Plugin thường đóng gói một khả năng tích hợp riêng, ví dụ đọc dữ liệu từ hệ thống kho, nhận webhook từ đối tác hoặc gửi sự kiện sang một dịch vụ ngoài. Plugin manager có thể dùng IntegrationFlowContext để đưa flow của plugin vào runtime khi plugin được bật.

Một hợp đồng plugin đơn giản có thể cung cấp metadata và factory tạo flow:

~~~java
public interface IntegrationPlugin {

    String pluginId();

    IntegrationFlow createFlow(PluginRuntimeContext context);
}
~~~

PluginRuntimeContext là kiểu dữ liệu do ứng dụng định nghĩa, chứa các dependency được cấp có kiểm soát như credential đã giải mã, endpoint được phép truy cập, service nghiệp vụ hoặc policy. Không đưa toàn bộ ApplicationContext hay quyền truy cập tùy ý vào plugin nếu không cần thiết.

Plugin manager đăng ký flow theo ID có namespace:

~~~java
String flowId = "plugin-" + normalize(plugin.pluginId());

IntegrationFlow flow = plugin.createFlow(pluginRuntimeContext);

IntegrationFlowContext.IntegrationFlowRegistration registration =
    flowContext.registration(flow)
        .id(flowId)
        .useFlowIdAsPrefix()
        .autoStartup(false)
        .register();

registration.start();
~~~

Cách tổ chức này giúp mỗi plugin có một registration rõ ràng. Khi plugin bị vô hiệu hóa, manager dừng và gỡ flow theo ID tương ứng.

### 6.1 Ranh giới tài nguyên của plugin

Một plugin có thể tạo thêm tài nguyên như HTTP client, connection, scheduler hoặc thư viện bên thứ ba. Cần xác định ai sở hữu tài nguyên đó và ai đóng nó.

- Nếu tài nguyên là bean dùng chung của ứng dụng, không đóng nó khi chỉ gỡ một plugin.
- Nếu tài nguyên được tạo riêng cho plugin, giữ tham chiếu trong plugin registration hoặc một resource holder và đóng sau khi endpoint đã dừng.
- Nếu plugin có thread riêng, phải có cách yêu cầu dừng và chờ thread kết thúc.
- Nếu plugin tạo message store hoặc metadata riêng, xác định chính sách lưu giữ khi plugin bị gỡ.
- Nếu plugin được nạp từ mã bên ngoài, kiểm soát classloader và dependency lifecycle; remove IntegrationFlow không tự đóng mọi classloader hoặc tài nguyên plugin.

### 6.2 Cập nhật plugin hoặc cấu hình

Khi plugin thay đổi cấu hình, tránh sửa đồng thời một flow đang xử lý message nếu endpoint và tài nguyên của nó không hỗ trợ thay đổi nóng.

Một quy trình thay thế có thể là:

1. Tạo cấu hình mới và kiểm tra hợp lệ.
2. Đăng ký flow mới với ID phiên bản, ví dụ plugin-inventory-v2.
3. Khởi động và kiểm tra flow mới.
4. Chuyển nguồn message hoặc producer sang flow mới.
5. Dừng nguồn của flow cũ và drain message đang xử lý.
6. Gỡ flow cũ.
7. Cập nhật mapping plugin → flow ID hiện hành.

Cách triển khai cụ thể phụ thuộc vào loại adapter và khả năng chuyển traffic. Nếu không thể chạy song song hai phiên bản, cần một khoảng dừng có kiểm soát và quy trình rollback rõ ràng.

## 7. Chống đăng ký trùng và xử lý thao tác đồng thời

Một hệ thống multi-tenant có thể nhận hai yêu cầu activate cùng tenant gần như đồng thời. Nếu cả hai cùng kiểm tra registry trước khi register(), cả hai có thể cùng thấy chưa tồn tại và cùng cố tạo flow.

Kiểm tra getRegistrationById() hữu ích để phát hiện flow đã tồn tại, nhưng riêng thao tác kiểm tra rồi đăng ký không phải một transaction nguyên tử. Cần đồng bộ thao tác theo tenant hoặc dùng cơ chế khóa phù hợp.

Các lựa chọn:

- **Lock trong JVM**: phù hợp khi chỉ có một process quản lý tenant đó.
- **Unique constraint trong database**: bảo vệ mapping tenant → flow ID khỏi bị ghi trùng.
- **Distributed lock hoặc leader election**: dùng khi nhiều instance có thể cùng thực hiện activation.
- **Idempotency key**: nhận diện yêu cầu activate lặp lại để không tạo thêm flow.
- **State transition có version**: chỉ cho phép cập nhật khi trạng thái hiện tại vẫn là version mà request đã đọc.

Ví dụ một service đơn giản có thể serialize thao tác trong cùng JVM:

~~~java
public synchronized IntegrationFlowContext.IntegrationFlowRegistration activate(
        TenantConfig tenant) {

    String flowId = "tenant-" + tenant.tenantId() + "-orders";

    IntegrationFlowContext.IntegrationFlowRegistration existing =
        flowContext.getRegistrationById(flowId);

    if (existing != null) {
        if (!existing.isRunning()) {
            existing.start();
        }
        return existing;
    }

    IntegrationFlow flow = buildFlow(tenant);

    IntegrationFlowContext.IntegrationFlowRegistration registration =
        flowContext.registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .autoStartup(false)
            .register();

    registration.start();
    return registration;
}
~~~

synchronized chỉ đồng bộ các lời gọi qua cùng instance service trong một JVM. Nó không khóa các replica khác và không thay thế unique constraint hoặc distributed lock khi có nhiều node.

Cũng cần xử lý trường hợp register thành công nhưng ghi mapping database thất bại, hoặc database ghi ACTIVE nhưng start thất bại. Có thể dùng trạng thái trung gian như REGISTERING/STARTING và một quy trình reconciliation để so sánh trạng thái lưu trữ với registry runtime.

## 8. Multi-instance: registry flow không tự chia sẻ giữa các node

IntegrationFlowContext quản lý flow trong ApplicationContext của process hiện tại. Khi ứng dụng chạy ba replica, mỗi replica có ApplicationContext và registry riêng. Đăng ký flow trên node A không tự đăng ký flow trên node B.

Điều này tạo ra một số tình huống:

- Nếu mỗi node đều đọc danh sách tenant và tự đăng ký flow, cả ba node có thể cùng mở kết nối tới cùng nguồn.
- Nếu chỉ một node được phép poll một thư mục hoặc queue, cần leader election, distributed lock hoặc cơ chế consumer group phù hợp.
- Nếu flow phải chạy trên mọi node để phục vụ traffic cục bộ, cần đăng ký trên mỗi node và bảo đảm nguồn message hỗ trợ nhiều consumer.
- Khi tenant bị tắt, cần phát sự kiện hoặc cập nhật trạng thái để mọi node liên quan dừng và gỡ flow.
- Khi một node khởi động lại, cần reconcile cấu hình bền vững với registry runtime mới tạo.

Không lưu duy nhất trạng thái ACTIVE trong database rồi cho rằng tất cả node đã start thành công. Nên theo dõi trạng thái theo node hoặc có cơ chế xác nhận activation từ từng node khi kiến trúc yêu cầu.

~~~mermaid
flowchart TD
    DB["Tenant / plugin configuration"] --> M["Activation coordinator"]
    M --> L{"Leadership / ownership"}
    L -->|Node A| A["ApplicationContext A"]
    L -->|Node B| B["ApplicationContext B"]
    A --> RA["IntegrationFlowContext A"]
    B --> RB["IntegrationFlowContext B"]
    RA --> FA["Dynamic flow A"]
    RB --> FB["Dynamic flow B"]
~~~

Sơ đồ minh họa hai cách triển khai có thể chọn: chỉ node sở hữu leader đăng ký flow, hoặc nhiều node cùng đăng ký flow nếu kiến trúc yêu cầu. Coordinator quyết định node nào được phép hoạt động; IntegrationFlowContext chỉ quản lý registration cục bộ.

## 9. Cô lập dữ liệu, credential và correlation theo tenant

Flow riêng không tự bảo đảm cô lập dữ liệu. Ranh giới tenant phải được giữ ở mọi bước có truy cập tài nguyên.

### 9.1 Tenant identity

Tenant ID phải xuất phát từ cấu hình hoặc danh tính đã xác thực. Không tin header tenantId do client tùy ý gửi. Tại điểm vào, xác định tenant rồi gắn metadata nội bộ cho các bước sau.

Mỗi service truy cập database cần giới hạn truy vấn theo tenant. Nếu dùng connection hoặc schema riêng, kiểm tra đúng credential/schema đã được gắn với registration đó.

### 9.2 Credential và đích gửi

Không ghi credential vào tên flow, log hoặc message header. Lấy secret từ secret manager hoặc nguồn bảo mật phù hợp, chỉ cấp cho adapter/handler cần sử dụng và đóng client khi flow bị gỡ.

Khi cấu hình outbound endpoint theo tenant, xác thực host, scheme và đích mạng được phép. Việc nhận một URL từ cấu hình tenant không nên tự động cho phép ứng dụng kết nối tới mọi địa chỉ.

### 9.3 Correlation và message store

Khi nhiều tenant cùng phát sinh message, correlation key nên có namespace tenant để tránh ghép message giữa hai tenant. Ví dụ một khóa logic có thể gồm tenantId + businessCorrelationId.

Nếu dùng aggregator hoặc message store, cần bảo đảm key và metadata phân biệt tenant. Nếu dùng chung store, kiểm tra cách xây dựng correlation key và quyền truy cập. Nếu dùng store riêng theo tenant, phải quản lý lifecycle và retention của store khi tenant bị xóa.

### 9.4 Error channel và retry

Lỗi của flow cần giữ được tenant context để điều tra và xử lý đúng. Ghi tenant ID, flow ID, message ID và correlation ID trong log/metric. Tránh đưa payload nhạy cảm hoặc credential vào ErrorMessage log.

Retry policy nên phù hợp với loại lỗi và tenant. Một tenant gặp lỗi từ hệ thống ngoài không nên chiếm hết worker hoặc làm nghẽn các tenant khác. Có thể dùng executor/queue riêng, giới hạn concurrency hoặc circuit breaker theo tenant khi yêu cầu cách ly tải cao.

Nếu dùng error channel chung, message lỗi cần giữ metadata nhận diện flow/tenant và handler xử lý lỗi phải xác thực lại trước khi truy cập dữ liệu. Với tenant có yêu cầu cô lập cao, cân nhắc error handling riêng theo flow hoặc adapter.

## 10. Tài nguyên và giới hạn khi số lượng flow tăng

Mỗi flow động có thể tạo channel, endpoint, handler adapter, scheduler task hoặc connection. Vì vậy, số lượng tenant/plugin tăng sẽ làm tăng tài nguyên runtime.

Cần theo dõi:

- Số registration hiện có và số registration đang chạy.
- Số endpoint, channel và adapter được tạo theo flow.
- Số thread, executor active count và queue depth.
- Số connection tới broker, database, HTTP server hoặc SFTP.
- Tỷ lệ lỗi khi register/start/stop/remove.
- Thời gian activate/deactivate và số lần retry.
- Số registration bị bỏ quên sau khi tenant/plugin đã bị xóa.

Không tạo một thread pool lớn riêng cho từng tenant nếu các flow có thể dùng executor được quản lý chung. Ngược lại, nếu cần cách ly tải, hãy đặt giới hạn rõ ràng thay vì dùng một pool không giới hạn.

Với hàng nghìn tenant có cấu trúc giống nhau, một flow chung và router thường dễ vận hành hơn hàng nghìn endpoint động. Có thể chia thành nhóm flow theo giao thức hoặc loại đối tác, rồi định tuyến theo tenant trong mỗi nhóm.

## 11. Kiểm thử và quan sát flow động

Flow động cần được kiểm tra cả đường thành công và vòng đời lỗi. Các trường hợp quan trọng:

| Tình huống | Điều cần xác minh |
|---|---|
| Activate tenant lần đầu | Một registration được tạo, đúng ID và trạng thái running |
| Activate lặp lại | Không tạo flow trùng |
| Hai request activate đồng thời | Chỉ một registration hợp lệ được giữ |
| Cấu hình tenant không hợp lệ | Không để lại registration hoặc tài nguyên dang dở |
| start thất bại | Trạng thái không bị ghi nhầm thành ACTIVE |
| Tạm dừng rồi chạy lại | Registration vẫn tồn tại và hoạt động lại đúng |
| Deactivate tenant | Flow được dừng/gỡ và tham chiếu được giải phóng |
| Hai tenant gửi cùng correlation ID | Message không bị aggregate hoặc ghi dữ liệu chéo |
| Plugin được cập nhật | Flow mới hoạt động trước khi flow cũ bị gỡ theo quy trình |
| Nhiều replica | Chỉ node được phép mới mở nguồn độc quyền |

Trong runtime, có thể dùng IntegrationFlowContext.getRegistry() và getRegistrationById(id) để kiểm tra registration. Kết hợp với integration graph, log lifecycle và metric của adapter/executor để xác định flow đã đăng ký, đã start hay đang gặp lỗi kết nối.

Một số thông tin nên ghi trong log có cấu trúc:

- tenantId hoặc pluginId đã được xác thực.
- flowId và phiên bản cấu hình.
- thao tác register/start/stop/remove.
- message ID và correlation ID.
- tên endpoint hoặc adapter gặp lỗi.
- node/process đang sở hữu flow.
- thời điểm bắt đầu và kết thúc thao tác lifecycle.

Không ghi secret, token hoặc toàn bộ payload nhạy cảm. Khi flow bị remove, giữ audit event cần thiết để điều tra nhưng xóa hoặc ẩn dữ liệu theo chính sách retention.

## 12. Quy trình vận hành mẫu

Một flow manager có thể tổ chức thành các thao tác nghiệp vụ rõ ràng:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu activate/deactivate"] --> B["Xác thực tenant/plugin"]
    B --> C["Kiểm tra trạng thái và quyền sở hữu"]
    C --> D{"Thao tác"}
    D -->|Activate| E["Validate config và credential"]
    E --> F["Tạo IntegrationFlow"]
    F --> G["Register với ID + bean prefix"]
    G --> H["Start và kiểm tra trạng thái"]
    H --> I["Ghi nhận ACTIVE"]
    D -->|Pause| J["Stop theo ranh giới lifecycle"]
    J --> K["Giữ registration để resume"]
    D -->|Remove| L["Ngừng ingress và drain"]
    L --> M["Stop và remove registration"]
    M --> N["Đóng tài nguyên, xóa mapping"]
~~~

Nên tách các bước validate, register, start và ghi trạng thái thành các bước có thể quan sát và retry. Nếu một bước thất bại, hệ thống cần biết registration đang ở trạng thái nào để có thể tiếp tục hoặc rollback. Tránh một hàm activate dài chỉ bắt exception rồi trả về thành công.

## 13. Những nhầm lẫn cần tránh

- **IntegrationFlowContext không phải tenant manager**: nó đăng ký/gỡ flow; ứng dụng vẫn phải quản lý tenant, quyền và cấu hình.
- **ID duy nhất không đồng nghĩa cô lập dữ liệu**: ID và bean prefix chỉ phân biệt thành phần runtime.
- **useFlowIdAsPrefix() không thay thế ID**: mỗi flow vẫn cần ID ổn định và không trùng.
- **getRegistrationById() rồi register() không nguyên tử**: cần khóa hoặc cơ chế idempotency khi có yêu cầu đồng thời.
- **stop() không đồng nghĩa drain**: phải có kế hoạch xử lý message đang chờ và task đang chạy.
- **remove() không tự đóng mọi tài nguyên bên ngoài**: ứng dụng phải quản lý client, thread và tài nguyên do plugin sở hữu.
- **Registry là cục bộ theo ApplicationContext**: nhiều replica cần cơ chế điều phối riêng.
- **Flow riêng không tự bảo đảm bảo mật tenant**: tenant identity, repository query, credential và correlation đều phải được cô lập.
- **Nhiều flow không phải lúc nào cũng tốt hơn**: với số tenant lớn và logic giống nhau, router dùng chung thường dễ mở rộng hơn.
- **Ghi ACTIVE trước khi start thành công tạo trạng thái sai**: cập nhật trạng thái sau khi xác minh registration đã chạy.

## 14. Tự kiểm tra

1. Khi nào nên tạo một IntegrationFlow cho mỗi tenant, và khi nào nên dùng một flow chung với router?
2. useFlowIdAsPrefix() giải quyết vấn đề gì? Vì sao vẫn cần ID duy nhất cho mỗi registration?
3. Vì sao kiểm tra getRegistrationById() trước register() chưa đủ để chống hai request activate đồng thời?
4. Nếu một tenant chỉ tạm dừng tích hợp, nên giữ registration hay remove? Khi tenant bị xóa vĩnh viễn thì sao?
5. Một ứng dụng chạy ba replica. Vì sao đăng ký flow trên node A không làm flow xuất hiện trên node B?
6. Làm thế nào để bảo đảm correlation ID giống nhau của hai tenant không khiến aggregator ghép nhầm message?
7. Khi plugin bị gỡ, cần đóng những tài nguyên nào ngoài việc remove IntegrationFlow?
8. Vì sao stop() toàn registration chưa chắc đáp ứng yêu cầu drain queue trước shutdown?

## Kết luận

IntegrationFlowContext cho phép ứng dụng đăng ký và gỡ flow ngay trong runtime, phù hợp với tenant, đối tác hoặc plugin có cấu hình và vòng đời riêng. Để vận hành an toàn, mỗi flow cần ID ổn định, bean prefix riêng, quy trình activate/deactivate có trạng thái, cơ chế chống đăng ký trùng và kế hoạch dọn tài nguyên. Với nhiều replica, phải điều phối quyền sở hữu flow ở cấp hệ thống vì registry chỉ tồn tại trong ApplicationContext của từng process. Khi số lượng tenant lớn nhưng cấu trúc xử lý giống nhau, hãy cân nhắc flow dùng chung với router để giảm chi phí endpoint và tài nguyên runtime.
