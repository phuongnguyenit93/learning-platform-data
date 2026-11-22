# Dynamic flow với input channel hoặc gateway

Trong một ứng dụng Spring Integration thông thường, các `IntegrationFlow` được khai báo thành bean và được đăng ký khi Spring `ApplicationContext` khởi động. Cách này phù hợp với những luồng xử lý cố định. Nhưng có những hệ thống cần tạo hoặc gỡ flow ngay khi ứng dụng đang chạy, chẳng hạn mỗi tenant có một luồng xử lý riêng, một kết nối đối tác vừa được kích hoạt, hoặc một cấu hình nghiệp vụ được nạp từ database.

`IntegrationFlowContext` cung cấp API để đăng ký và quản lý những flow như vậy trong runtime. Sau khi đăng ký, ứng dụng có thể gửi message vào flow qua input channel hoặc gọi một gateway đã được nối với channel đó. Khi không còn cần flow, ứng dụng gỡ registration để các endpoint và component do flow tạo ra được dừng và giải phóng.

Điểm cần giữ rõ trong thiết kế là **định nghĩa flow, điểm vào của flow và đối tượng gọi flow là ba khái niệm khác nhau**. `IntegrationFlow` mô tả các bước xử lý; input channel nhận message; gateway hoặc `MessageChannel`/`MessagingTemplate` là cách phía ứng dụng gửi request vào flow.

## 1. Khi nào cần dynamic IntegrationFlow?

Flow khai báo bằng `@Bean` phù hợp khi topology ổn định và biết trước lúc khởi động. Dynamic flow phù hợp khi số lượng hoặc cấu hình flow thay đổi theo dữ liệu runtime.

Một số tình huống thường gặp:

- Mỗi tenant có endpoint, bộ lọc, mapping hoặc thông tin kết nối riêng.
- Một đối tác được bật/tắt tích hợp mà không cần khởi động lại toàn bộ ứng dụng.
- Người quản trị tạo một pipeline xử lý theo cấu hình đã lưu.
- Một tác vụ cần tạo flow tạm thời, nhận một nhóm message rồi tự gỡ flow.
- Ứng dụng cần cô lập các endpoint và channel được tạo cho từng phiên xử lý.

Không nên biến mọi khác biệt nhỏ thành một flow riêng. Nếu chỉ cần thay đổi một giá trị, một router hoặc service dùng cấu hình có thể đơn giản hơn. Dynamic flow phù hợp khi thực sự cần thay đổi topology hoặc vòng đời của các endpoint.

## 2. Các thành phần tham gia

| Thành phần | Vai trò |
|---|---|
| `IntegrationFlow` | Định nghĩa chuỗi endpoint, channel và các bước xử lý. |
| `IntegrationFlowContext` | Registry và điểm điều khiển việc đăng ký, tra cứu, gỡ dynamic flow. |
| `IntegrationFlowRegistration` | Handle đại diện cho một flow đã đăng ký; cung cấp ID, input channel và messaging template khi phù hợp. |
| Registration ID | Định danh một lần đăng ký flow trong `IntegrationFlowContext`. |
| Input channel | Điểm nhận message đầu vào của flow. |
| Gateway | API hướng nghiệp vụ để code ứng dụng gửi request và có thể nhận reply từ flow. |

Trong ứng dụng đã bật hạ tầng Spring Integration, có thể inject `IntegrationFlowContext` vào service quản lý flow:

```java
@Service
public class DynamicFlowManager {

    private final IntegrationFlowContext flowContext;

    public DynamicFlowManager(IntegrationFlowContext flowContext) {
        this.flowContext = flowContext;
    }
}
```

Thông thường, hạ tầng này được cung cấp khi cấu hình Spring Integration được kích hoạt, ví dụ qua `@EnableIntegration` hoặc cấu hình tự động tương ứng của ứng dụng Spring Boot. Không cần tự tạo một `IntegrationFlowContext` mới cho mỗi flow; các registration cần được quản lý qua context dùng chung của ứng dụng.

## 3. Đăng ký một flow động

Quy trình cơ bản gồm bốn bước:

1. Tạo đối tượng `IntegrationFlow` bằng Java DSL.
2. Đăng ký flow thông qua `IntegrationFlowContext` và cấp ID ổn định.
3. Lấy registration handle để truy cập input channel hoặc messaging template.
4. Gửi message vào flow và giữ handle để gỡ flow khi cần.

Ví dụ tạo một flow biến đổi chuỗi:

```java
IntegrationFlow flow = IntegrationFlow
    .from(MessageChannels.direct())
    .<String, String>transform(String::trim)
    .<String, String>transform(String::toUpperCase)
    .get();

IntegrationFlowRegistration registration = flowContext
    .registration(flow)
    .id("uppercaseFlow")
    .useFlowIdAsPrefix()
    .register();
```

`registration(...)` tạo builder cho lần đăng ký. `.id("uppercaseFlow")` đặt registration ID. `.useFlowIdAsPrefix()` yêu cầu dùng ID của flow làm prefix cho tên các component do flow tạo ra, giúp giảm nguy cơ trùng tên khi đăng ký nhiều flow có cấu trúc giống nhau. `.register()` thực hiện đăng ký và trả về `IntegrationFlowRegistration`.

Khi đăng ký thành công, Spring Integration tạo và quản lý các component cần thiết, liên kết chúng vào context và khởi động endpoint theo cấu hình startup của flow. Nếu ID hoặc tên component xung đột, registration có thể thất bại; ứng dụng cần xử lý lỗi đăng ký thay vì giả định flow đã sẵn sàng.

## 4. Gửi message qua input channel

Với flow có input channel do registration quản lý, có thể lấy channel bằng `registration.getInputChannel()`:

```java
MessageChannel input = registration.getInputChannel();

boolean accepted = input.send(
    MessageBuilder.withPayload("  hello spring integration  ").build()
);
```

`send()` đưa message vào channel. Giá trị `true` cho biết channel đã nhận message theo semantics của channel đó; nó không tự chứng minh toàn bộ nghiệp vụ phía sau đã hoàn tất. Với `DirectChannel`, handler thường chạy ngay trên thread gửi nên exception có thể truyền về caller. Với channel bất đồng bộ hoặc queue, gửi thành công có thể chỉ có nghĩa message đã được tiếp nhận để xử lý sau.

Nếu flow sử dụng một `MessageChannel` bean đã tồn tại từ trước làm điểm vào, giữ reference của bean đó và gửi vào chính channel ấy. `getInputChannel()` đặc biệt hữu ích với input channel được tạo cùng registration; khi dùng channel bên ngoài, reference của channel bean là điểm truy cập rõ ràng.

Ví dụ với channel được khai báo sẵn:

```java
@Bean
public MessageChannel partnerInput() {
    return new DirectChannel();
}
```

Flow động có thể bắt đầu từ channel bean này:

```java
public IntegrationFlowRegistration registerPartnerFlow(
        IntegrationFlowContext flowContext,
        @Qualifier("partnerInput") MessageChannel partnerInput,
        PartnerService partnerService) {

    IntegrationFlow partnerFlow = IntegrationFlow
        .from(partnerInput)
        .handle(partnerService, "process")
        .get();

    return flowContext.registration(partnerFlow)
        .id("partnerAFlow")
        .useFlowIdAsPrefix()
        .register();
}
```

Trong ví dụ, `@Qualifier` chọn đúng channel bean nếu context có nhiều `MessageChannel`. Nếu có nhiều flow cùng subscribe một `DirectChannel`, channel có thể phân phối message giữa các subscriber theo cơ chế dispatch của nó. Vì vậy, không dùng chung một direct input channel cho nhiều flow tenant nếu yêu cầu là mỗi message phải đi đúng flow của tenant đó. Hãy tạo channel riêng cho từng registration hoặc đặt một router ở trước các flow.

## 5. Gửi request và nhận reply bằng MessagingTemplate

Một số flow cần trả kết quả ngay cho caller. `IntegrationFlowRegistration` cung cấp `getMessagingTemplate()` để gửi request và chờ reply theo cơ chế request/reply của Spring Messaging:

```java
Message<?> reply = registration.getMessagingTemplate()
    .sendAndReceive(
        MessageBuilder.withPayload("  hello spring integration  ").build()
    );

if (reply != null) {
    String result = (String) reply.getPayload();
}
```

`sendAndReceive()` sử dụng input channel của registration và thiết lập thông tin reply cần thiết cho request. Kết quả có thể là `null` nếu không có reply trong thời gian chờ hoặc flow không tạo reply. Cần cấu hình timeout phù hợp với SLA của nghiệp vụ và xử lý trường hợp không có kết quả.

Request/reply chỉ hoạt động khi các endpoint trong flow tạo ra reply và reply được chuyển về đúng `replyChannel`. Một handler kiểu `void` hoặc một nhánh kết thúc theo kiểu one-way không tự tạo payload trả về. Với flow bất đồng bộ, cần đặc biệt chú ý timeout, reply channel và việc caller có thể kết thúc trước khi xử lý hoàn tất.

Có thể dùng `convertSendAndReceive(...)` khi muốn Spring chuyển đổi payload reply sang kiểu mong muốn. Dù dùng cách nào, hãy xác định rõ kiểu request/reply và hành vi khi timeout; đừng coi việc gửi message vào channel là bằng chứng rằng đã nhận được kết quả nghiệp vụ.

## 6. Dùng gateway làm API gọi flow

`@MessagingGateway` cho phép cung cấp một interface nghiệp vụ để code ứng dụng gọi flow như gọi một service. Gateway gửi request đến channel được chỉ định và có thể nhận reply nếu phương thức khai báo kiểu trả về.

Trong cấu hình Java thuần, cần bật cơ chế quét gateway bằng `@IntegrationComponentScan` trên configuration class (cùng hạ tầng Spring Integration phù hợp). Với Spring Boot, hãy xác minh cấu hình scan gateway của ứng dụng thay vì giả định mọi interface có `@MessagingGateway` đều tự được tạo proxy.

Ví dụ khai báo channel ổn định và gateway:

```java
@Bean
public MessageChannel tenantOrdersInput() {
    return new DirectChannel();
}

@MessagingGateway
public interface TenantOrdersGateway {

    @Gateway(requestChannel = "tenantOrdersInput")
    OrderResult submit(OrderRequest request);
}
```

Flow có thể được đăng ký động trên channel đó:

```java
public IntegrationFlowRegistration registerTenantFlow(
        IntegrationFlowContext flowContext,
        @Qualifier("tenantOrdersInput") MessageChannel tenantOrdersInput,
        OrderService orderService) {

    IntegrationFlow tenantFlow = IntegrationFlow
        .from(tenantOrdersInput)
        .handle(orderService, "submit")
        .get();

    return flowContext.registration(tenantFlow)
        .id("tenantAOrders")
        .useFlowIdAsPrefix()
        .register();
}
```

Gateway là facade ổn định cho code nghiệp vụ; flow được gắn vào channel lúc registration được tạo. Gateway chỉ có thể gửi thành công sau khi flow đã đăng ký và endpoint đã subscribe channel. Khi flow bị gỡ, channel bean có thể vẫn tồn tại nhưng không còn subscriber của flow đó; ứng dụng cần chặn request hoặc trả trạng thái phù hợp trong thời gian flow ngừng hoạt động.

Trong ví dụ trên, `OrderService.submit` cần trả về `OrderResult` để gateway có thể nhận reply. Nếu handler chỉ ghi dữ liệu và không trả kết quả, hãy dùng phương thức gateway trả về `void` hoặc thiết kế một reply rõ ràng.

### Một gateway cho nhiều flow động

Một `@MessagingGateway` thường được cấu hình với channel ổn định. Nó không tự sinh một gateway proxy riêng cho mỗi registration động. Nếu có nhiều tenant, có hai cách thiết kế thường gặp:

- Gateway gửi vào một channel chung; một router đọc `tenantId` từ header hoặc payload rồi chuyển request đến input channel của flow tương ứng.
- Mỗi registration có input channel riêng; service quản lý flow giữ reference của channel hoặc messaging template tương ứng và chọn đúng registration theo tenant.

Không nên đăng ký nhiều flow tenant vào cùng một `DirectChannel` rồi kỳ vọng channel tự định tuyến theo tenant. Khi có nhiều subscriber, dispatch có thể phân phối message giữa các subscriber thay vì chọn subscriber dựa trên dữ liệu nghiệp vụ. Việc định tuyến phải được thể hiện rõ bằng router hoặc channel riêng.

## 7. Chọn input channel phù hợp với semantics của flow

Dynamic flow vẫn tuân theo semantics của channel trong Spring Integration. Cách chọn channel ảnh hưởng đến thread, thời điểm xử lý, back-pressure và cách quan sát lỗi.

| Channel | Cách xử lý | Hệ quả khi dùng làm điểm vào |
|---|---|---|
| `DirectChannel` | Gọi subscriber đồng bộ trên thread gửi | Phù hợp request/reply đơn giản; exception có thể quay lại caller. |
| `PublishSubscribeChannel` | Phát message đến nhiều subscriber | Dùng khi cần fan-out; cần xác định rõ có executor hay không và cách xử lý lỗi từng nhánh. |
| `QueueChannel` | Giữ message trong queue để consumer nhận sau | Producer và consumer tách rời; cần poller hoặc consumer phù hợp để lấy message. |
| `ExecutorChannel` | Gửi tác vụ qua executor | Tách thread gửi và xử lý; cần cấu hình executor, error handling và giới hạn tải. |

Không nên chọn `QueueChannel` chỉ vì muốn xử lý bất đồng bộ mà quên consumer/poller. Nếu không có consumer lấy message, message có thể nằm trong queue mà flow không tiến triển. Tương tự, `ExecutorChannel` cần executor có giới hạn hợp lý; nếu hàng đợi tác vụ tăng liên tục, dynamic flow có thể tạo thêm tải thay vì giải quyết nghẽn.

## 8. Đặt ID và tránh xung đột giữa các flow

Registration ID nhận diện flow trong `IntegrationFlowContext`, còn endpoint ID và tên channel nhận diện các component bên trong flow. Đây là những phạm vi khác nhau.

Ví dụ một tenant có registration ID `tenantAOrders`, nhưng endpoint bên trong flow vẫn có thể mang ID như `validate` hoặc `persist`. Khi tạo nhiều flow cùng cấu trúc, `.useFlowIdAsPrefix()` giúp tên component được tạo có prefix riêng theo flow ID. Nếu đặt ID tường minh cho từng endpoint hoặc channel, hãy kiểm tra quy tắc prefix và bảo đảm tên cuối cùng không xung đột với bean đã có.

Một quy ước hữu ích là:

| Đối tượng | Ví dụ |
|---|---|
| Registration ID | `tenantAOrders` |
| Input channel riêng | `tenantA.orders.input` |
| Endpoint validate | `tenantA.orders.validate` |
| Endpoint persist | `tenantA.orders.persist` |
| Correlation ID của nghiệp vụ | `ORDER-9001` |

Không dùng message ID hoặc correlation ID làm registration ID. Message ID thường thay đổi theo từng message; correlation ID gắn với một nghiệp vụ hoặc nhóm message; registration ID gắn với vòng đời của một flow đang được quản lý.

## 9. Gỡ flow và quản lý vòng đời

Khi không còn cần flow, gỡ registration bằng ID:

```java
flowContext.remove("tenantAOrders");
```

Có thể giữ `IntegrationFlowRegistration` và dùng ID từ chính handle:

```java
flowContext.remove(registration.getId());
```

Việc gỡ registration yêu cầu framework dừng endpoint và giải phóng các component do flow đăng ký quản lý. Không nên tự tìm rồi xóa từng bean được sinh ra bằng cách đoán tên; làm vậy có thể bỏ sót endpoint, channel hoặc quan hệ phụ thuộc.

Một service quản lý flow thường lưu registration theo tenant hoặc khóa cấu hình:

```java
@Service
public class TenantFlowRegistry {

    private final IntegrationFlowContext flowContext;
    private final Map<String, IntegrationFlowRegistration> registrations =
        new ConcurrentHashMap<>();

    public TenantFlowRegistry(IntegrationFlowContext flowContext) {
        this.flowContext = flowContext;
    }

    public void remove(String tenantId) {
        IntegrationFlowRegistration registration = registrations.remove(tenantId);
        if (registration != null) {
            flowContext.remove(registration.getId());
        }
    }
}
```

Đây là phần quản lý handle tối giản; phương thức đăng ký cần bổ sung kiểm tra ID, xử lý lỗi và chính sách đồng thời phù hợp. Trong hệ thống nhiều request cùng tạo hoặc xóa flow cho một tenant, cần khóa hoặc cơ chế đồng bộ theo tenant để tránh hai registration cùng lúc hoặc xóa nhầm registration vừa được thay thế.

Trước khi gỡ flow đang nhận tải, hãy xác định cách xử lý message đang chạy và message đang chờ trong queue. Dừng nhận request mới, chờ hoặc drain các tác vụ cần hoàn tất, rồi mới gỡ registration. Không giả định rằng việc remove sẽ tự lưu lại mọi message đang nằm trong channel hoặc executor queue.

Dynamic registration là trạng thái runtime. Nếu ứng dụng restart, các flow động không tự được khôi phục chỉ vì chúng từng được đăng ký trước đó. Nếu cấu hình flow được lưu trong database hoặc cấu hình ngoài, ứng dụng cần đọc lại và đăng ký chúng trong quá trình khởi động.

## 10. Retry, transaction và error handling trong dynamic flow

Flow được đăng ký động vẫn sử dụng các cơ chế runtime thông thường của Spring Integration. Có thể gắn advice vào endpoint, cấu hình transaction cho poller hoặc consumer, chọn channel đồng bộ/bất đồng bộ và thiết lập error channel theo nhu cầu.

Một số điểm cần xác định khi tạo flow từ cấu hình runtime:

- Retry áp dụng cho endpoint nào, exception nào được retry và giới hạn bao nhiêu lần.
- Transaction bắt đầu ở bước nào; transaction có nằm trong cùng thread xử lý hay đã qua executor.
- Lỗi đồng bộ được trả về caller hay lỗi bất đồng bộ được công bố thành `ErrorMessage`.
- Error channel riêng của message có được đặt không và thành phần nào tiêu thụ nó.
- Khi hết retry, message được lưu bền vững ở đâu và ai có quyền redrive.

Ví dụ, một flow bắt đầu từ `DirectChannel` có thể truyền exception từ handler về gateway caller. Nếu đổi sang `ExecutorChannel`, handler chạy trên executor; caller có thể chỉ biết message đã được gửi, còn lỗi cần được xử lý tại error channel. Thay đổi channel khi tạo dynamic flow vì vậy có thể làm thay đổi semantics quan sát được của API.

Với request/reply, không nên để gateway chờ một thao tác có thể mất nhiều phút trong khi endpoint thực tế chạy bất đồng bộ. Hãy dùng mô hình chấp nhận request rồi trả operation ID nếu nghiệp vụ kéo dài; kết quả có thể được truy vấn hoặc phát qua callback/event sau đó.

## 11. Chẩn đoán dynamic flow trong runtime

Khi flow đăng ký thành công nhưng không xử lý message như mong đợi, hãy kiểm tra theo thứ tự:

1. **Registration có tồn tại không?** Xác minh ID đã được đăng ký và handle tương ứng chưa bị remove.
2. **Input channel có đúng không?** Đối chiếu channel được gửi vào với channel mà flow bắt đầu. Nếu dùng bean channel, xác minh cả bean name và object reference.
3. **Endpoint đã khởi động và subscribe chưa?** Một registration tồn tại chưa đủ nếu endpoint không hoạt động theo cấu hình startup hoặc bị dừng.
4. **Channel có đúng semantics không?** Kiểm tra `DirectChannel`, `QueueChannel`, `PublishSubscribeChannel` hoặc `ExecutorChannel`, cùng consumer/poller và executor liên quan.
5. **Có xung đột tên không?** Kiểm tra registration ID, prefix, endpoint ID và channel name khi tạo nhiều flow có cùng cấu trúc.
6. **Reply có được tạo không?** Kiểm tra handler có trả payload, reply channel có được giữ và gateway/template có timeout quá ngắn không.
7. **Lỗi được chuyển đi đâu?** Kiểm tra exception ở caller, error channel trong header, global `errorChannel` và error flow của poller/adapter.
8. **Gỡ flow có đúng vòng đời không?** Xác minh service không xóa registration còn đang được request khác sử dụng và không để lại handle trong registry ứng dụng.

Khi log hoạt động, nên ghi registration ID, tenant hoặc khóa cấu hình đã được làm sạch, endpoint ID, channel, message ID và correlation ID. Tránh ghi token, thông tin kết nối hoặc toàn bộ payload nhạy cảm. Với nhiều flow động, registration ID trong log giúp xác định topology nào đã xử lý message tại thời điểm phát sinh lỗi.

## 12. Những lỗi thiết kế thường gặp

- **Đăng ký flow nhưng không giữ ID hoặc handle.** Ứng dụng khó tra cứu và gỡ đúng flow khi cấu hình thay đổi.
- **Dùng một input `DirectChannel` cho nhiều tenant flow.** Message có thể được phân phối giữa các subscriber thay vì đến đúng tenant; cần router hoặc channel riêng.
- **Cho rằng gateway tự được tạo theo mỗi registration.** `IntegrationFlowContext` quản lý flow; `@MessagingGateway` là proxy riêng và cần được cấu hình với request channel phù hợp.
- **Gửi message trước khi flow được đăng ký.** Channel có thể chưa có subscriber hoặc request/reply không có nơi xử lý.
- **Dùng queue mà không có poller/consumer.** Message được giữ lại nhưng không được lấy ra xử lý.
- **Không đặt prefix hoặc ID ổn định.** Nhiều flow có cấu trúc giống nhau có thể xung đột tên component.
- **Gỡ flow khi vẫn còn request đang chạy.** Có thể làm request mới thất bại hoặc làm gián đoạn công việc đang thực thi.
- **Kỳ vọng flow tự tồn tại sau restart.** Registration động cần được tái tạo từ cấu hình lưu bền vững.
- **Không giới hạn số lượng flow.** Tạo flow theo từng request mà không có chính sách thu hồi có thể làm tăng số bean, endpoint, thread và tài nguyên kết nối.

## 13. Checklist thiết kế

Trước khi đưa dynamic flow vào vận hành, hãy xác định:

- Điều kiện nào tạo flow và điều kiện nào gỡ flow?
- Registration ID được tạo từ khóa nào và bảo đảm duy nhất ra sao?
- Input channel được tạo cùng flow hay là bean dùng chung?
- Caller gửi message trực tiếp, dùng `MessagingTemplate` hay gọi gateway?
- Flow có cần request/reply hay chỉ xác nhận đã nhận request?
- Channel và executor tạo ra thread boundary nào?
- Retry, transaction, error channel và redrive được cấu hình ở đâu?
- Message đang chạy hoặc đang chờ được xử lý thế nào khi gỡ flow?
- Flow được khôi phục từ cấu hình nào sau khi ứng dụng restart?

Khi trả lời rõ các câu hỏi này, `IntegrationFlowContext` giúp ứng dụng thay đổi topology message flow ngay trong runtime mà vẫn quản lý được điểm vào, cách gọi, định danh và vòng đời của từng flow.
