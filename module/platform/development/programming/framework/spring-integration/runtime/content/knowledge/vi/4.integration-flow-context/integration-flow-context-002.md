# Đăng ký IntegrationFlow bằng flow name

Trong Spring Integration, phần lớn message flow có thể khai báo tĩnh bằng một bean `IntegrationFlow`. Tuy nhiên, có những ứng dụng chỉ biết cần tạo flow nào khi đang chạy: mỗi tenant có một luồng riêng, một kết nối mới cần một pipeline xử lý riêng, hoặc cấu hình được nạp sau khi ứng dụng đã khởi động. Với các trường hợp đó, `IntegrationFlowContext` cho phép đăng ký một `IntegrationFlow` vào Spring context theo một định danh do ứng dụng chọn.

Định danh này thường được gọi là **flow ID** hoặc **flow name**. Nó giúp ứng dụng tìm và quản lý registration tương ứng, đồng thời có thể được dùng làm prefix cho tên các component mà DSL tạo ra. Hiểu đúng flow ID, component ID và input channel giúp tránh xung đột tên khi có nhiều flow động cùng tồn tại.

## 1. Flow tĩnh và flow đăng ký lúc runtime

Nếu cấu trúc flow đã biết khi cấu hình ứng dụng, khai báo bằng `@Bean` là cách đơn giản nhất:

```java
@Configuration
class OrderFlowConfiguration {

    @Bean
    IntegrationFlow orderFlow(OrderHandler handler) {
        return IntegrationFlow.from("orders.input")
            .handle(handler, "handle")
            .get();
    }
}
```

Spring khởi tạo bean, Spring Integration đăng ký các channel/endpoint của flow và context quản lý lifecycle của chúng. Không cần tự giữ một registration handle cho flow tĩnh.

Flow động phù hợp khi số lượng hoặc cấu trúc flow phụ thuộc dữ liệu runtime. Ví dụ, một hệ thống tích hợp nhiều tenant có thể đăng ký một flow xử lý đơn hàng cho từng tenant sau khi nạp cấu hình tenant. Khi tenant bị gỡ, ứng dụng hủy đúng registration của tenant đó.

| Tiêu chí | `@Bean IntegrationFlow` | `IntegrationFlowContext` |
| --- | --- | --- |
| Thời điểm tạo | Trong quá trình khởi tạo context | Bất cứ lúc nào ứng dụng chủ động đăng ký |
| Số lượng flow | Thường được xác định trong cấu hình | Có thể thay đổi theo runtime |
| Định danh | Bean name và ID của các component | Registration ID do ứng dụng đặt |
| Quản lý vòng đời | Spring context | Ứng dụng giữ `IntegrationFlowRegistration` và hủy khi cần |
| Trường hợp điển hình | Pipeline cố định của ứng dụng | Flow theo tenant, kết nối, thiết bị hoặc cấu hình runtime |

Không nên biến mọi flow tĩnh thành flow động. Đăng ký runtime bổ sung trách nhiệm lưu registration, chống trùng ID, xử lý lỗi đăng ký và dọn flow khi tài nguyên tương ứng kết thúc.

## 2. `IntegrationFlowContext` và flow ID

`IntegrationFlowContext` là registry chuyên biệt để đăng ký và gỡ các `IntegrationFlow` trong lúc ứng dụng đang chạy. Thay vì tự thêm bean definition bằng `BeanFactory` hoặc `ApplicationContext`, ứng dụng tạo flow rồi chuyển nó cho API registration:

```java
IntegrationFlowContext.IntegrationFlowRegistration registration = flowContext
    .registration(flow)
    .id("tenant-acme-orders")
    .useFlowIdAsPrefix()
    .register();
```

Các thành phần chính:

- `registration(flow)` bắt đầu cấu hình đăng ký cho một flow.
- `id(...)` đặt định danh của registration. Đây là flow ID mà ứng dụng dùng để phân biệt flow trong context.
- `useFlowIdAsPrefix()` yêu cầu dùng flow ID làm prefix cho tên các component trong flow; tùy chọn này yêu cầu phải đặt `id(...)`.
- `register()` thực hiện đăng ký và trả về `IntegrationFlowRegistration` để ứng dụng quản lý flow vừa tạo.

`id(...)` là định danh ở cấp flow registration. Nó khác ID của một endpoint cụ thể được cấu hình bên trong DSL, và cũng không tự động là tên của một channel nghiệp vụ mà hệ thống bên ngoài gửi message tới. Nếu cần đặt tên channel, hãy cấu hình channel rõ ràng trong flow hoặc dùng input channel được registration cung cấp.

### Chọn flow ID

Flow ID cần ổn định và duy nhất trong phạm vi application context đang quản lý các flow đó. Registration đang dùng một ID phải được destroy trước khi ID đó được tái sử dụng cho một flow instance mới. Ví dụ:

```java
String flowId = "tenant-" + tenantKey + "-orders";
```

Một ID có cấu trúc giúp tìm registration, ghi log và gỡ đúng flow. `tenantKey` nên là khóa định danh đã được kiểm tra và chuẩn hóa; tránh đưa trực tiếp dữ liệu tùy ý từ request vào tên bean. Nếu có nhiều loại flow cho cùng tenant, thêm loại flow vào ID, chẳng hạn `tenant-acme-orders` và `tenant-acme-invoices`.

Không tái sử dụng một ID cho hai registration đang cùng tồn tại. Nếu ứng dụng cần thay flow theo cấu hình mới, hãy xác định rõ chiến lược thay thế: dừng/gỡ registration cũ rồi đăng ký phiên bản mới, hoặc tạo ID có version và chuyển traffic có kiểm soát. Tránh để hai flow cùng nhận một input vì ứng dụng quên hủy registration cũ.

## 3. Vì sao cần `useFlowIdAsPrefix()`?

Một `IntegrationFlow` có thể tạo nhiều bean bên trong: channel, message handler, endpoint, bridge và các component khác. Nếu nhiều flow động cùng dùng những tên component mặc định hoặc tên tường minh giống nhau, quá trình đăng ký có thể xung đột bean name.

Từ Spring Integration 5.0.6, tên bean được sinh cho các component trong một flow đã có cơ chế dùng flow ID làm prefix. `useFlowIdAsPrefix()` cho phép chủ động áp dụng prefix này cho các component có ID trong DSL, đặc biệt hữu ích khi đăng ký nhiều instance của cùng một flow và các instance dùng chung component ID. Ví dụ, các component của flow `tenant-acme-orders` được đặt trong namespace tên gắn với flow đó, tách biệt với component của `tenant-globex-orders`.

```java
IntegrationFlowContext.IntegrationFlowRegistration registration = flowContext
    .registration(createOrderFlow(tenant))
    .id("tenant-" + tenant.key() + "-orders")
    .useFlowIdAsPrefix()
    .register();
```

Prefix giải quyết xung đột tên component do flow tạo ra. Nó không thay thế việc thiết kế tên channel giao tiếp giữa các hệ thống. Với channel được chia sẻ có chủ đích giữa nhiều flow, hãy khai báo và quản lý channel đó như một dependency riêng. Với channel riêng của từng flow, ưu tiên để flow sở hữu channel hoặc đặt tên riêng theo tenant/flow.

Flow ID cũng không tự động làm cho payload, header hoặc correlation key trở nên riêng biệt. Nếu hai flow nhận cùng message và dùng chung store hoặc correlation key, ứng dụng vẫn phải thiết kế namespace cho dữ liệu runtime tương ứng.

## 4. Đăng ký flow và lấy input channel

Ví dụ dưới đây tạo một flow xử lý đơn hàng cho một tenant. Flow được dựng từ input channel riêng, sau đó đăng ký bằng ID có cấu trúc:

```java
@Component
final class TenantOrderFlowManager {

    private final IntegrationFlowContext flowContext;
    private final Map<String, IntegrationFlowContext.IntegrationFlowRegistration> registrations =
        new ConcurrentHashMap<>();

    TenantOrderFlowManager(IntegrationFlowContext flowContext) {
        this.flowContext = flowContext;
    }

    synchronized MessageChannel register(String tenantKey,
                                         TenantOrderHandler handler) {
        if (registrations.containsKey(tenantKey)) {
            throw new IllegalStateException("Flow already registered for tenant");
        }

        String flowId = "tenant-" + tenantKey + "-orders";
        MessageChannel input = new DirectChannel();

        IntegrationFlow flow = IntegrationFlow.from(input)
            .handle(handler, "handle")
            .get();

        IntegrationFlowContext.IntegrationFlowRegistration registration = flowContext
            .registration(flow)
            .id(flowId)
            .useFlowIdAsPrefix()
            .register();

        registrations.put(tenantKey, registration);
        return input;
    }
}
```

Trong ví dụ này:

1. Manager kiểm tra tenant đã có flow chưa.
2. Tạo input channel và dựng flow với handler đã được inject.
3. Đặt flow ID theo tenant và loại nghiệp vụ.
4. Đăng ký flow, sau đó lưu `IntegrationFlowRegistration` để quản lý vòng đời.
5. Trả input channel cho thành phần cần gửi message vào flow.

`DirectChannel` chuyển message tới subscriber trong cùng thread gửi. Nếu flow cần queue hoặc xử lý bất đồng bộ, hãy chọn channel phù hợp như `QueueChannel` hoặc `ExecutorChannel`; việc đăng ký theo flow ID không tự thay đổi semantics threading của channel.

Trong một ứng dụng thực tế, cần xác thực `tenantKey` trước khi tạo ID, giới hạn số flow có thể đăng ký và bảo đảm handler được cấu hình đúng tenant. Nếu channel được tạo bên ngoài flow như ví dụ, manager phải giữ đúng tham chiếu channel tương ứng với registration.

### Lấy input channel từ registration

Khi flow khai báo input channel theo cách để registration quản lý/nhận diện input, có thể lấy channel từ registration:

```java
IntegrationFlowContext.IntegrationFlowRegistration registration = flowContext
    .registration(IntegrationFlow.from("tenant-acme.orders.input")
        .handle(orderHandler, "handle")
        .get())
    .id("tenant-acme-orders")
    .useFlowIdAsPrefix()
    .register();

MessageChannel inputChannel = registration.getInputChannel();
inputChannel.send(new GenericMessage<>(order));
```

`getInputChannel()` thuận tiện khi caller không cần biết cách flow tạo hoặc resolve input channel. Với flow bắt đầu từ một channel object đã được manager giữ sẵn, dùng chính tham chiếu đó cũng là cách hợp lệ. `getMessagingTemplate()` cung cấp `MessagingTemplate` gắn với input channel khi ứng dụng muốn gửi message qua template.

Nếu flow không có input channel theo cách registration có thể cung cấp, không giả định `getInputChannel()` luôn trả về một channel dùng được. Thiết kế flow có nguồn vào rõ ràng và kiểm tra loại flow trước khi expose API gửi message.

## 5. Quản lý nhiều flow theo tenant hoặc cấu hình

Một manager thường cần ánh xạ khóa nghiệp vụ tới registration:

```java
private final Map<String, IntegrationFlowContext.IntegrationFlowRegistration> registrations =
    new ConcurrentHashMap<>();
```

`IntegrationFlowRegistration` là interface lồng bên trong `IntegrationFlowContext`. Map giúp manager tìm registration để gửi dữ liệu, kiểm tra trạng thái quản lý hoặc gỡ flow. Khóa map nên cùng ý nghĩa với phần định danh flow, ví dụ tenant key hoặc connection key. Không nên chỉ giữ `IntegrationFlow` object mà bỏ registration handle: registration là đầu mối để gỡ các component đã được đưa vào context.

Các nguyên tắc quản lý:

- Kiểm tra trùng khóa trước khi đăng ký và xử lý trường hợp hai request đồng thời muốn tạo cùng một flow.
- Dùng ID xác định được từ tenant/loại flow; log ID khi đăng ký và hủy để truy vết.
- Lưu registration ngay sau khi đăng ký thành công.
- Nếu bước lưu registration hoặc bước cấu hình tiếp theo thất bại, hủy registration vừa tạo để tránh flow mồ côi.
- Khi tenant bị xóa hoặc kết nối kết thúc, lấy đúng registration và gọi `destroy()`.
- Đặt giới hạn số flow, theo dõi số registration đang tồn tại và dọn các flow không còn được sử dụng.

Không nên đăng ký flow mới cho từng message. Flow registration tạo endpoint và component trong context; nó là thao tác quản lý cấu trúc runtime, không phải thao tác xử lý từng message. Hãy đăng ký theo vòng đời tenant, thiết bị, kết nối hoặc cấu hình cần duy trì.

## 6. Hủy registration và vòng đời flow

Khi flow không còn cần thiết, gọi `destroy()` trên registration:

```java
synchronized void unregister(String tenantKey) {
    IntegrationFlowContext.IntegrationFlowRegistration registration =
        registrations.remove(tenantKey);

    if (registration != null) {
        registration.destroy();
    }
}
```

`destroy()` yêu cầu `IntegrationFlowContext` gỡ flow và các component được đăng ký cùng flow khỏi context, đồng thời dọn các endpoint liên quan. Đây là bước quan trọng để tránh endpoint tiếp tục nhận message và tránh giữ bean/channel không còn được sử dụng.

Hủy flow không đồng nghĩa với việc mọi message đang xử lý ở hệ thống ngoài đã được hoàn tất. Nếu flow dùng queue, executor hoặc adapter bất đồng bộ, ứng dụng cần xác định chính sách drain, timeout và xử lý message đang bay trước khi destroy. Với `DirectChannel`, việc gửi và xử lý thường diễn ra đồng bộ trong thread gửi, nhưng downstream vẫn có thể chuyển sang executor hoặc queue.

Manager nên làm thao tác gỡ có tính nhất quán: lấy registration khỏi registry quản lý, ngăn request mới gửi vào flow, thực hiện chính sách dừng/drain của ứng dụng, rồi gọi `destroy()`. Nếu destroy thất bại, cần ghi nhận lỗi và có cơ chế vận hành để phát hiện registration còn sót.

Khi toàn bộ `ApplicationContext` đóng, Spring quản lý lifecycle các bean còn đăng ký. Tuy vậy, manager vẫn nên gỡ dynamic flow khi vòng đời tenant/kết nối kết thúc, thay vì trông chờ đến lúc ứng dụng shutdown.

## 7. Cấu hình registration và component ID

`IntegrationFlowContext` cung cấp builder để cấu hình registration trước khi gọi `register()`. Các lựa chọn thường dùng gồm:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `id(flowId)` | Đặt ID cho registration. |
| `useFlowIdAsPrefix()` | Dùng flow ID làm prefix cho tên component do flow tạo ra. |
| `autoStartup(boolean)` | Kiểm soát việc flow có tự khởi động sau khi đăng ký hay không; mặc định là `true`. |
| `register()` | Thực hiện đăng ký và trả về registration handle. |

Ví dụ trì hoãn thời điểm khởi động:

```java
IntegrationFlowContext.IntegrationFlowRegistration registration = flowContext
    .registration(flow)
    .id("tenant-acme-orders")
    .useFlowIdAsPrefix()
    .autoStartup(false)
    .register();

// Sau khi ứng dụng hoàn tất bước chuẩn bị cần thiết:
registration.start();
```

`IntegrationFlowRegistration` cung cấp `start()` và `stop()` để điều khiển lifecycle của registration. `autoStartup(false)` chỉ nên dùng khi ứng dụng có kế hoạch gọi `start()` ở thời điểm phù hợp. Đừng hiểu stop/start là cách pause/resume message an toàn cho mọi channel: hành vi gửi message khi endpoint chưa start còn phụ thuộc loại channel và topology của flow. Khi không cần flow nữa, gọi `destroy()` để gỡ registration và các component phụ thuộc.

ID của registration, ID của endpoint và tên channel có thể cùng xuất hiện trong log nhưng phục vụ các mục đích khác nhau:

| Định danh | Phạm vi | Ví dụ |
| --- | --- | --- |
| Flow ID | Toàn bộ dynamic flow registration | `tenant-acme-orders` |
| Component ID | Một endpoint/handler cụ thể trong flow | `validateOrder`, `persistOrder` |
| Channel name | Điểm giao tiếp message giữa các endpoint | `orders.input`, `orders.validated` |
| Correlation ID | Một nhóm message trong một lần xử lý | `order-run-81` |

Không dùng flow ID thay correlation ID. Một flow có thể xử lý hàng nghìn order; correlation ID phải phân biệt từng lần xử lý order trong flow đó.

## 8. Thay thế flow khi cấu hình thay đổi

Giả sử tenant thay đổi endpoint đích hoặc quy tắc xử lý. Có hai chiến lược thường gặp:

**Thay tại chỗ:** ngăn nhận công việc mới, drain hoặc xử lý phần message đang chạy, destroy registration cũ, sau đó đăng ký flow mới với cùng flow ID. Cách này đơn giản nhưng cần có khoảng thời gian flow không hoạt động hoặc một cơ chế điều phối traffic.

**Đăng ký phiên bản song song:** tạo flow mới với ID có version, ví dụ `tenant-acme-orders-v2`, kiểm tra flow mới sẵn sàng, chuyển nguồn gửi sang input channel mới, sau đó drain và destroy flow cũ `tenant-acme-orders-v1`. Cách này cho phép chuyển đổi có kiểm soát nhưng manager phải quản lý cả hai registration trong giai đoạn chuyển tiếp.

Không đăng ký hai flow cùng một ID để mong flow mới ghi đè flow cũ. Hãy hủy registration cũ hoặc dùng ID phiên bản riêng, rồi chủ động chuyển traffic.

## 9. Quan sát và chẩn đoán registration

Khi một dynamic flow không nhận message hoặc vẫn hoạt động sau khi tenant đã bị gỡ, cần kiểm tra cả registry lẫn message path.

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Đăng ký flow thất bại do trùng tên | Flow ID hoặc component bean name đã được dùng. | Kiểm tra ID đang tồn tại; dùng ID duy nhất và `useFlowIdAsPrefix()`. |
| Flow được đăng ký nhưng không nhận message | Caller gửi sai input channel, input channel không được nối tới flow hoặc endpoint chưa start. | Kiểm tra `registration.getInputChannel()`, channel topology và cấu hình auto-startup. |
| Hai tenant nhận nhầm message | Chia sẻ input channel ngoài ý muốn hoặc định tuyến tenant sai. | Dùng input channel riêng hoặc router kiểm tra tenant key; kiểm tra header và log. |
| Flow cũ tiếp tục nhận message | Registration cũ chưa được destroy hoặc còn nguồn gửi vào channel chung. | Tra cứu registration theo tenant và gọi `destroy()`; kiểm tra các producer còn hoạt động. |
| Số bean/endpoint tăng liên tục | Đăng ký lặp theo request/message hoặc quên cleanup. | Chỉ đăng ký theo lifecycle tài nguyên; theo dõi registration count và gỡ flow hết hạn. |
| Đăng ký mới thất bại khi cập nhật cấu hình | Flow cũ còn giữ ID hoặc component name. | Thực hiện quy trình thay thế có kiểm soát hoặc dùng versioned ID. |
| Message mất khi hủy flow | Hủy registration trong lúc queue/executor còn message đang chờ. | Thiết kế drain, timeout và chính sách chuyển/loại message trước khi destroy. |

Nên ghi log tối thiểu các trường: flow ID, tenant/resource key, thời điểm register/destroy, input channel, phiên bản cấu hình và kết quả thao tác. Metric hữu ích gồm số registration hiện tại, số lần đăng ký thất bại, số flow bị hủy, tuổi registration và số message đang chờ ở channel có queue.

`IntegrationFlowContext` là registry trong application context của process hiện tại. Việc đăng ký flow trên một instance không tự động tạo flow tương ứng trên các instance khác trong cluster. Nếu ứng dụng chạy nhiều node, mỗi node cần nhận cấu hình và thực hiện đăng ký theo chiến lược nhất quán; việc định tuyến message tới node có flow phù hợp là trách nhiệm của kiến trúc triển khai.

## 10. Quy trình đăng ký một flow bằng tên

1. Xác định vì sao flow phải được tạo trong runtime; nếu cấu trúc cố định, khai báo bằng `@Bean`.
2. Chọn khóa tài nguyên ổn định và tạo flow ID duy nhất theo tài nguyên cùng loại nghiệp vụ.
3. Dựng `IntegrationFlow` với input channel, handler và các dependency đã được inject.
4. Gọi `flowContext.registration(flow).id(flowId).useFlowIdAsPrefix().register()`.
5. Lưu `IntegrationFlowRegistration` theo khóa tài nguyên; expose input channel hoặc messaging template cho producer phù hợp.
6. Theo dõi đăng ký, lỗi và số lượng flow đang tồn tại.
7. Khi tài nguyên kết thúc, chặn message mới, áp dụng drain policy rồi gọi `registration.destroy()`.
8. Khi thay cấu hình, dùng quy trình thay thế hoặc versioned ID và chuyển traffic rõ ràng.

## 11. Điểm cần nhớ

- `IntegrationFlowContext` đăng ký flow trong lúc ứng dụng đang chạy; `IntegrationFlowRegistration` là handle để ứng dụng quản lý flow đó.
- `.id(flowId)` đặt định danh của registration. Flow ID khác component ID, channel name và correlation ID.
- `.useFlowIdAsPrefix()` giúp tên component nội bộ của các flow động không va chạm.
- Lưu registration sau khi đăng ký và gọi `destroy()` khi tenant/kết nối/cấu hình không còn cần flow.
- Không đăng ký flow theo từng message; registration thuộc vòng đời tài nguyên hoặc cấu hình runtime.
- Flow động chỉ tồn tại trong application context nơi nó được đăng ký; cluster nhiều node cần chiến lược đăng ký và định tuyến riêng.

## Tài liệu tham khảo

- [Spring Integration Reference — Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html)
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Integration API — IntegrationFlowContext](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/context/IntegrationFlowContext.html)
- [Spring Integration API — IntegrationFlowRegistration](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/context/IntegrationFlowContext.IntegrationFlowRegistration.html)
