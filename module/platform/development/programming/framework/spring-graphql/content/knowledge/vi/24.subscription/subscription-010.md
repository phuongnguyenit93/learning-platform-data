# Authorization cho subscription

GraphQL subscription giữ một luồng kết nối để server gửi event đến client khi dữ liệu thay đổi. Vì luồng có thể tồn tại lâu hơn một HTTP request thông thường, authorization cần được xem xét ở nhiều thời điểm: khi xác thực kết nối, khi client đăng ký một subscription operation, khi từng event được phát ra và khi các field con của event được phân giải.

Trong Spring for GraphQL, subscription thường được khai báo bằng @SubscriptionMapping và trả về Publisher, Flux hoặc kiểu stream tương thích. Spring Security có thể xác thực người gọi và bảo vệ method, còn ứng dụng phải bảo đảm mỗi subscriber chỉ nhận những event và field mà principal hiện tại được phép xem.

**Authorization lúc bắt đầu subscription chưa đủ nếu quyền có thể thay đổi trong lúc stream đang chạy.** Với dữ liệu nhạy cảm, cần kiểm tra quyền ở nguồn event hoặc trên từng event, xử lý thu hồi quyền và kết thúc subscription khi cần.

## 1. Authentication và authorization trong subscription

Hai khái niệm cần được phân biệt:

- **Authentication** xác định người gọi là ai. Ví dụ, token hợp lệ ánh xạ đến principal và các authority.
- **Authorization** quyết định principal đó được phép thực hiện hành động hoặc đọc dữ liệu nào. Ví dụ, người dùng có quyền theo dõi đơn hàng của chính mình nhưng không được theo dõi đơn hàng của tenant khác.

Một WebSocket đã được xác thực không có nghĩa mọi GraphQL operation trên kết nối đều được phép. Tương tự, người dùng có quyền mở subscription lúc đầu không có nghĩa quyền đó không thể bị thu hồi trong thời gian stream tồn tại.

Nên kiểm soát theo các lớp:

| Thời điểm | Việc cần kiểm tra |
| --- | --- |
| HTTP handshake hoặc connection initialization | Token, session, nguồn gốc kết nối và danh tính principal |
| Mỗi GraphQL operation | Principal hiện tại, quyền gọi subscription field và input như accountId/orderId |
| Khi chọn topic hoặc đăng ký nguồn event | Principal có quyền subscribe đúng resource/tenant không |
| Mỗi event được phát ra | Quyền xem event còn hiệu lực không, event có thuộc scope của principal không |
| Khi resolve field con | Quyền truy cập field nhạy cảm hoặc dữ liệu liên quan |
| Khi token hết hạn, logout hoặc quyền bị thu hồi | Ngừng phát event hoặc đóng subscription theo policy |

Không nên xem connection ID, correlation ID hoặc giá trị userId do client gửi là bằng chứng xác thực. Danh tính và quyền phải đến từ security context đã được server xác minh.

## 2. Subscription trong Spring for GraphQL

Schema có thể khai báo một subscription nhận event đơn hàng:

~~~graphql
type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type OrderEvent {
    orderId: ID!
    status: String!
    changedAt: String!
}
~~~

Một annotated controller có thể trả Flux<OrderEvent>:

~~~java
@Controller
public class OrderSubscriptionController {

    private final OrderEventService orderEventService;

    public OrderSubscriptionController(OrderEventService orderEventService) {
        this.orderEventService = orderEventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument("orderId") UUID orderId) {
        return orderEventService.eventsForOrder(orderId);
    }
}
~~~

Phương thức @SubscriptionMapping tạo publisher cho subscription. GraphQL thực thi selection set cho từng event được phát ra để tạo các GraphQL response tương ứng. Vì vậy, authorization có thể cần xuất hiện cả ở resolver subscription và resolver field con của event.

Không trả một danh sách event đã tải sẵn nếu yêu cầu là stream liên tục. Flux/Publisher biểu diễn nguồn event; mỗi subscriber có một subscription riêng và cần được gắn với principal cùng scope dữ liệu phù hợp.

## 3. Xác thực WebSocket handshake và connection_init

GraphQL over WebSocket thường có hai giai đoạn đáng chú ý:

1. Client thiết lập WebSocket connection qua HTTP upgrade handshake.
2. Client gửi thông điệp connection_init theo giao thức GraphQL WebSocket trước khi gửi các operation.

Nếu ứng dụng xác thực ở HTTP handshake, Spring Security có thể sử dụng cơ chế xác thực HTTP thông thường như session cookie hoặc bearer token trong header. Đây thường là cách đơn giản khi client có thể gửi thông tin xác thực ở handshake.

Một số client gửi token trong payload connection_init. Payload này chỉ là dữ liệu do client cung cấp; nó không tự trở thành principal đã xác thực. Ứng dụng cần dùng WebSocketGraphQlInterceptor hoặc cơ chế tích hợp tương ứng để xác thực token, tạo security context đáng tin cậy và gắn danh tính vào session/execution theo cách an toàn.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant C as GraphQL client
    participant WS as WebSocket endpoint
    participant SI as Security / interceptor
    participant G as GraphQL execution
    C->>WS: HTTP Upgrade + credentials
    WS->>SI: Authenticate handshake
    SI-->>WS: Authenticated session
    C->>WS: connection_init (nếu protocol dùng)
    WS->>SI: Validate init payload nếu có token
    SI-->>C: connection_ack hoặc từ chối
    C->>WS: subscription operation
    WS->>G: Execute với principal/context
    G-->>C: Subscription events
~~~

Không tin userId, tenantId, role hoặc danh sách quyền do client tự gửi trong connection payload. Nếu payload có access token, phải xác minh chữ ký, issuer, audience, expiry và các claim cần thiết như với token nhận từ HTTP header.

WebSocket connection có thể tồn tại lâu hơn thời hạn access token. Cần quyết định rõ khi token hết hạn: từ chối operation mới, kết thúc các subscription đang chạy hoặc yêu cầu client kết nối lại bằng token mới. Không nên tiếp tục cấp quyền vô thời hạn chỉ vì handshake ban đầu hợp lệ.

## 4. Xác thực từng operation trên cùng một kết nối

Một WebSocket connection có thể chạy nhiều GraphQL operation. Vì vậy, xác thực kết nối không thay thế kiểm tra ở mỗi operation. Với mỗi request, ứng dụng cần bảo đảm GraphQL execution nhận đúng principal và context.

Spring for GraphQL cung cấp WebSocketGraphQlInterceptor cho lifecycle của WebSocket và WebGraphQlInterceptor cho việc xử lý request GraphQL ở tầng web. Interceptor có thể bổ sung dữ liệu đã xác thực vào GraphQLContext để resolver dùng trong execution.

Ví dụ, sau khi principal được xác minh bởi Spring Security, resolver có thể nhận Principal hoặc đọc context:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    return orderEventService.eventsForOrder(
        orderId, principal.getName());
}
~~~

Hoặc sử dụng @ContextValue nếu interceptor đã đặt giá trị vào GraphQLContext:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        @ContextValue("tenantId") String tenantId) {

    return orderEventService.eventsForTenant(orderId, tenantId);
}
~~~

tenantId phải được suy ra từ principal hoặc token đã xác minh ở server. Không lấy một giá trị tenant từ GraphQL argument rồi dùng trực tiếp để mở stream. Argument do client gửi chỉ xác định tài nguyên mà họ muốn truy cập; service phải kiểm tra principal có quyền với tài nguyên đó.

Với WebSocket, cần phân biệt context của connection/session và context của từng GraphQL execution. Không giữ một mutable GraphQLContext dùng chung rồi thay principal cho từng operation; điều đó có thể khiến hai operation chạy đồng thời đọc nhầm danh tính. Hãy dùng cơ chế context theo execution và giữ security context theo đúng lifecycle.

## 5. Kiểm tra quyền ngay khi đăng ký subscription

Trước khi tạo publisher hoặc đăng ký với broker, server cần kiểm tra người gọi có quyền subscribe resource được yêu cầu hay không.

Ví dụ service kiểm tra quyền sở hữu đơn hàng:

~~~java
public Mono<Void> assertCanReadOrder(
        String principalName, UUID orderId) {

    return orderRepository.findOwnerAndTenant(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException()))
        .flatMap(order -> {
            boolean allowed = order.ownerName().equals(principalName);
            return allowed
                ? Mono.empty()
                : Mono.error(new AccessDeniedException("Access denied"));
        });
}
~~~

Resolver kết hợp kiểm tra quyền với nguồn event:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();

    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId));
}
~~~

assertCanReadOrder được thực hiện trước khi publisher phát event. Nhờ đó, server không mở subscription cho một order mà principal không có quyền xem.

Không nên chỉ lọc event sau khi đã subscribe vào một topic rộng nếu có thể tránh được. Việc đăng ký nguồn event cần được giới hạn theo tenant/resource để tránh tiêu thụ dữ liệu không liên quan và giảm nguy cơ rò rỉ qua timing, log hoặc side channel.

## 6. Bảo vệ subscription bằng Spring Security method security

Có thể dùng method security để kiểm tra quyền gọi subscription field:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

~~~java
@Controller
public class NotificationSubscriptionController {

    private final NotificationService notificationService;

    public NotificationSubscriptionController(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @SubscriptionMapping
    @PreAuthorize("hasAuthority('notifications:read')")
    public Flux<Notification> notifications(Principal principal) {
        return notificationService.eventsForUser(principal.getName());
    }
}
~~~

@PreAuthorize kiểm tra authority trước khi method được thực thi. Với ứng dụng Spring MVC/imperative, cấu hình method security tương ứng bằng @EnableMethodSecurity. Với ứng dụng reactive, cần dùng cấu hình reactive method security phù hợp, chẳng hạn @EnableReactiveMethodSecurity, và bảo đảm SecurityContext được truyền trong Reactor Context.

Method security bảo vệ việc bắt đầu thực thi method, nhưng không tự động giải quyết mọi chính sách cho từng event trong một publisher dài hạn. Nếu quyền có thể bị thu hồi trong lúc subscription đang chạy, cần thêm kiểm tra event-time hoặc cơ chế kết thúc stream khi quyền thay đổi.

Không dùng @PreAuthorize thay cho kiểm tra quyền truy cập tài nguyên cụ thể. hasAuthority('notifications:read') chỉ xác nhận quyền tổng quát; service vẫn phải kiểm tra notification thuộc user/tenant nào.

## 7. Authorization cho từng event được phát ra

Quyền truy cập có thể thay đổi sau khi subscription bắt đầu. Ví dụ:

- Người dùng bị gỡ khỏi tenant.
- Đơn hàng được chuyển sang chủ sở hữu khác.
- Phiên đăng nhập bị thu hồi.
- Quyền xem dữ liệu nhạy cảm bị thay đổi.
- Subscription vẫn đang chạy khi access token hết hạn.

Nếu chỉ kiểm tra lúc subscribe, stream có thể tiếp tục gửi dữ liệu sau khi quyền đã mất. Với dữ liệu nhạy cảm, hãy kiểm tra quyền trên từng event hoặc dùng một cơ chế theo dõi quyền để hủy stream.

Ví dụ lọc event theo quyền hiện tại:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderUpdated(
        @Argument("orderId") UUID orderId,
        Principal principal) {

    String username = principal.getName();

    return orderAuthorization.assertCanReadOrder(username, orderId)
        .thenMany(orderEventService.eventsForOrder(orderId)
            .filterWhen(event ->
                orderAuthorization.canReadEvent(username, event)));
}
~~~

filterWhen chỉ phát event khi authorization service trả true. Event không còn được phép xem sẽ bị loại khỏi stream. Cách này ngăn gửi payload trái quyền, nhưng stream có thể vẫn tồn tại và tiếp tục kiểm tra các event sau.

Nếu policy yêu cầu đóng subscription ngay khi quyền bị thu hồi, hãy kết hợp event stream với một publisher báo thay đổi quyền hoặc session invalidation, rồi hủy/hoàn tất stream theo policy. Không chỉ bỏ event mà vẫn giữ subscription vô thời hạn nếu điều đó tiêu tốn tài nguyên hoặc không đúng hợp đồng sản phẩm.

Kiểm tra quyền trên từng event có chi phí. Có thể chọn chiến lược phù hợp:

| Chiến lược | Khi phù hợp | Giới hạn |
| --- | --- | --- |
| Kiểm tra một lần lúc subscribe | Dữ liệu ít nhạy cảm, quyền ổn định trong thời gian stream ngắn | Không phản ánh quyền bị thu hồi sau đó |
| Lọc theo từng event | Quyền/resource có thể thay đổi và cần chặn payload trái quyền | Tăng số lần gọi authorization service |
| Theo dõi quyền và hủy stream | Cần thu hồi quyền nhanh, subscription dài hạn | Cần quản lý lifecycle và tín hiệu revoke |
| Kết hợp kiểm tra event + revoke signal | Dữ liệu nhạy cảm, yêu cầu bảo vệ cao | Phức tạp hơn nhưng kiểm soát tốt hơn |

## 8. Bảo vệ tenant và topic subscription

Không để client tự chọn một topic bất kỳ rồi nhận event. Ví dụ, một subscription nhận tenantId từ argument có thể bị lạm dụng nếu service chỉ dùng ID đó để đăng ký broker:

~~~java
// Không an toàn nếu chưa kiểm tra tenantId với principal.
return eventBroker.eventsForTenant(tenantId);
~~~

Thay vào đó, lấy tenant scope từ principal đã xác thực và kiểm tra resource:

~~~java
@SubscriptionMapping
public Flux<InvoiceEvent> invoiceChanged(
        @Argument("tenantId") String requestedTenantId,
        Principal principal) {

    return tenantAuthorization.assertCanAccess(
            principal.getName(), requestedTenantId)
        .thenMany(invoiceEventService.eventsForTenant(requestedTenantId));
}
~~~

Ở ví dụ này, assertCanAccess phải xác minh membership/role từ nguồn dữ liệu tin cậy. Trong một số hệ thống, tốt hơn là bỏ tenantId khỏi argument và suy ra tenant hiện tại hoàn toàn từ principal. Chỉ cho client chọn tenant khi sản phẩm thực sự hỗ trợ chuyển tenant và server đã kiểm tra quyền.

Nếu event broker hỗ trợ topic hoặc partition theo tenant, hãy đăng ký vào đúng partition sau khi authorization thành công. Không subscribe một topic toàn hệ thống rồi chỉ dựa vào client-side filtering.

## 9. Field-level authorization cho payload event

Quyền subscribe một event không có nghĩa người dùng được xem mọi field trong payload. Ví dụ user có thể thấy trạng thái đơn hàng nhưng không được thấy địa chỉ giao hàng hoặc thông tin thanh toán.

Schema:

~~~graphql
type OrderEvent {
    orderId: ID!
    status: String!
    shippingAddress: String
    paymentReference: String
}
~~~

Có thể bảo vệ field nhạy cảm trong resolver:

~~~java
@Controller
public class OrderEventFieldController {

    @SchemaMapping(typeName = "OrderEvent", field = "paymentReference")
    @PreAuthorize("hasAuthority('orders:payment:read')")
    public String paymentReference(OrderEvent event) {
        return event.paymentReference();
    }
}
~~~

Đối với reactive method security, dùng cấu hình reactive phù hợp nếu method trả publisher. Nếu field trả giá trị đồng bộ nhưng được resolve trong một reactive execution, vẫn cần kiểm tra cách security context được cung cấp trong stack thực tế.

Một lựa chọn khác là không đưa dữ liệu nhạy cảm vào event DTO nếu subscription không cần nó. Payload nhỏ hơn giúp giảm nguy cơ rò rỉ, giảm serialization và làm rõ contract. Khi field nhạy cảm chỉ được thêm theo quyền, cần test cả trường hợp được phép và bị từ chối.

## 10. SecurityContext trong reactive subscription

Subscription thường sử dụng Flux và reactive execution. Trong Spring Security reactive, SecurityContext được lưu trong Reactor Context thay vì dựa đơn thuần vào ThreadLocal.

Vì vậy:

- Giữ xử lý authorization trong reactive chain.
- Tránh gọi block() để lấy principal hoặc kết quả kiểm tra quyền.
- Không lưu Authentication vào static field hoặc singleton mutable field.
- Không giả định một callback chạy trên thread khác vẫn nhìn thấy ThreadLocal.
- Khi chuyển sang CompletableFuture hoặc executor thủ công, cần cơ chế context propagation hoặc truyền dữ liệu đã xác thực một cách tường minh.

Ví dụ giữ authorization trong reactive chain:

~~~java
return notificationService.eventsForUser(principal.getName())
    .filterWhen(event ->
        authorizationService.canRead(principal, event));
~~~

filterWhen trên Flux nhận predicate trả Mono<Boolean> và chỉ phát event khi predicate cho kết quả true. Không dùng subscribe() bên trong resolver để tự tách luồng, vì GraphQL cần quản lý publisher được trả về để thực thi, xử lý lỗi và hủy subscription.

Nếu resolver nhận Principal, hãy sử dụng principal đã được Spring Security xác thực. Không lấy username từ argument rồi coi đó là danh tính hiện tại.

## 11. Token hết hạn, logout và thu hồi quyền

WebSocket connection có thể tồn tại lâu hơn token. Cần có policy rõ ràng cho các tình huống:

| Sự kiện | Hành vi đề xuất |
| --- | --- |
| Token hết hạn trước operation mới | Từ chối operation hoặc yêu cầu kết nối lại |
| Token hết hạn khi subscription đang chạy | Kết thúc stream hoặc yêu cầu re-authentication theo policy |
| Người dùng logout | Hủy subscription gắn với session/principal nếu yêu cầu logout có hiệu lực ngay |
| User bị gỡ khỏi tenant | Ngừng phát event thuộc tenant đó |
| Role bị thu hồi | Áp dụng lại policy cho event/field tiếp theo và hủy subscription nếu cần |
| Connection bị đóng | Hủy publisher và giải phóng broker listener/tài nguyên |

Một cách triển khai là lưu liên kết giữa principal/session và các subscription đang hoạt động để có thể gửi tín hiệu revoke. Cách khác là dùng một publisher thông báo thay đổi quyền và kết hợp với stream event. Thiết kế cụ thể phụ thuộc vào hạ tầng broker và yêu cầu thời gian thu hồi.

Không nên chỉ kiểm tra token một lần khi connection được mở rồi bỏ qua expiry. Nếu token có claim quyền thay đổi, cần quyết định dùng snapshot quyền tại thời điểm subscribe hay đọc trạng thái quyền hiện tại. Với dữ liệu nhạy cảm, policy thường cần phản ánh việc thu hồi trong thời gian hợp lý.

## 12. Dùng WebSocketGraphQlInterceptor và WebGraphQlInterceptor

Spring for GraphQL cung cấp các interceptor ở tầng web:

- WebGraphQlInterceptor can thiệp vào từng WebGraphQlRequest trước/sau GraphQL execution.
- WebSocketGraphQlInterceptor bổ sung lifecycle hook cho WebSocket, như connection initialization và đóng connection, đồng thời tham gia xử lý operation.

Có thể dùng interceptor để xác thực token từ connection initialization payload, thiết lập principal/context và kiểm tra metadata của từng operation. Tuy nhiên, interceptor không nên trở thành nơi duy nhất chứa mọi quy tắc authorization nghiệp vụ. Kiểm tra quyền resource nên được đặt trong application service hoặc policy component để REST, GraphQL và message consumer có thể dùng chung.

Mô hình trách nhiệm:

| Thành phần | Trách nhiệm |
| --- | --- |
| Spring Security handshake/filter | Xác thực kết nối HTTP và bảo vệ endpoint |
| WebSocketGraphQlInterceptor | Xử lý connection init/close và metadata của WebSocket |
| WebGraphQlInterceptor | Bổ sung/kiểm tra context cho từng GraphQL request |
| @PreAuthorize / method security | Bảo vệ quyền gọi resolver/method |
| Authorization service | Kiểm tra quyền theo user, tenant và resource |
| Subscription publisher pipeline | Lọc event, xử lý revoke và cancellation |
| @SchemaMapping hoặc field resolver | Bảo vệ field nhạy cảm trong payload |

Nếu dùng token trong connection_init, không log payload thô. Chỉ đưa principal và claim đã xác thực vào context; không giữ access token trong GraphQLContext nếu resolver không cần token gốc.

## 13. Cancellation và giải phóng tài nguyên

Subscription có thể tồn tại nhiều phút hoặc nhiều giờ. Khi client ngắt kết nối, hủy operation hoặc quyền bị thu hồi, publisher cần dừng việc tiêu thụ event và giải phóng tài nguyên.

Ví dụ ghi nhận lifecycle:

~~~java
@SubscriptionMapping
public Flux<Notification> notifications(Principal principal) {
    String username = principal.getName();

    return notificationService.eventsForUser(username)
        .doFinally(signal ->
            log.debug("Notification subscription ended: user={}, signal={}",
                username, signal));
}
~~~

doFinally có thể dùng để ghi nhận complete, error hoặc cancel. Nếu service đăng ký listener trực tiếp vào broker, hãy bảo đảm publisher thực hiện cleanup khi subscriber cancel, chẳng hạn bằng Flux.create/Flux.push với callback cleanup hoặc API reactive của broker.

Không tạo subscription nền bằng cách gọi subscribe() bên trong controller. Khi đó GraphQL không còn quản lý được publisher con, backpressure, lỗi hoặc cancellation của nó.

## 14. Kiểm thử authorization cho subscription

Kiểm thử query/mutation thông thường chưa đủ để chứng minh subscription an toàn. Cần kiểm tra handshake, connection init, operation, event stream và cancellation. Spring for GraphQL cung cấp WebSocketGraphQlTester để kiểm thử subscription qua WebSocket; có thể kết hợp StepVerifier để kiểm tra các event được phát ra.

Ví dụ kiểm thử stream:

~~~java
Flux<OrderEventView> events = tester.document("""
        subscription($orderId: ID!) {
            orderUpdated(orderId: $orderId) {
                orderId
                status
            }
        }
        """)
    .variable("orderId", "order-01")
    .executeSubscription()
    .toFlux("orderUpdated", OrderEventView.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.orderId().equals("order-01"))
    .thenCancel()
    .verify();
~~~

Đây là ví dụ minh họa; cách tạo tester và cấu hình credentials phụ thuộc test setup cùng phiên bản Spring for GraphQL. Trong test thực tế, hãy dùng principal/token tương ứng và một publisher test có thể điều khiển event.

Các trường hợp nên kiểm thử:

1. Kết nối không có token bị từ chối nếu endpoint yêu cầu authentication.
2. Token không hợp lệ trong handshake hoặc connection initialization không tạo principal giả.
3. Principal có authority được phép đăng ký subscription.
4. Principal thiếu authority bị từ chối trước khi đăng ký broker listener.
5. User không có quyền với order/tenant không nhận được event.
6. Event bị loại hoặc subscription bị hủy khi quyền bị thu hồi.
7. Field nhạy cảm bị bảo vệ ngay cả khi client đưa field đó vào selection set.
8. Hai user trên cùng endpoint không đọc chéo dữ liệu hoặc cache.
9. Token hết hạn và logout có hành vi đúng policy.
10. Client cancel hoặc disconnect làm publisher giải phóng listener.
11. Lỗi authorization không tiết lộ resource có tồn tại hay không.
12. WebSocket origin và credential handling tuân thủ cấu hình bảo mật.

Để test thu hồi quyền, phát một event hợp lệ, thay đổi quyền trong test, rồi phát event tiếp theo. Xác nhận event thứ hai không được gửi và stream được kết thúc nếu policy yêu cầu đóng subscription.

## 15. Lỗi thường gặp

| Sai lầm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Chỉ xác thực WebSocket handshake | Operation mới có thể dùng context/quyền không còn hợp lệ | Xác thực và kiểm tra authorization theo từng operation |
| Tin userId/tenantId trong connection payload | Client giả mạo danh tính hoặc tenant | Xác minh token và suy ra principal từ server security context |
| Chỉ kiểm tra quyền khi subscribe | Quyền bị thu hồi nhưng stream tiếp tục gửi dữ liệu | Kiểm tra event-time hoặc dùng revoke signal |
| Subscribe topic toàn hệ thống rồi lọc ở client | Dữ liệu trái quyền có thể rò rỉ | Giới hạn topic/query ở server theo tenant/resource |
| Chỉ dùng authority tổng quát | User có quyền đọc loại dữ liệu nhưng không sở hữu resource cụ thể | Kiểm tra quyền theo resource trong service |
| Bỏ qua field-level authorization | Event hợp lệ nhưng field nhạy cảm bị lộ | Bảo vệ nested field hoặc loại field khỏi payload |
| Dùng ThreadLocal trong reactive flow | Principal/context bị mất hoặc lẫn giữa request | Dùng Reactor Context, GraphQLContext và truyền tường minh |
| Không xử lý token expiry | Connection sống lâu tiếp tục hoạt động sau expiry | Định nghĩa re-authentication hoặc terminate policy |
| Tự gọi subscribe() trong controller | GraphQL không quản lý cancellation/backpressure | Trả Publisher cho GraphQL |
| Không cleanup khi disconnect | Listener/broker consumer bị rò rỉ | Hủy nguồn event khi publisher cancel |
| Dùng DataLoader cache lâu mà không refresh | Field con có thể trả dữ liệu/quyền cũ | Đặt cache policy và invalidate/refresh phù hợp với event |

## 16. Checklist trước khi đưa subscription lên production

- WebSocket/SSE endpoint có authentication và origin policy phù hợp.
- Token từ handshake hoặc connection_init được xác minh; không tin claim do client tự khai báo.
- Mỗi operation có principal và GraphQLContext đúng scope.
- Subscription field kiểm tra authority và quyền trên resource.
- Nguồn event được giới hạn theo tenant/resource ở server.
- Event-time authorization được dùng khi quyền có thể thay đổi.
- Field nhạy cảm trong payload có authorization riêng.
- Token expiry, logout và permission revoke có hành vi đã định nghĩa.
- Publisher cleanup khi complete, error hoặc cancel.
- DataLoader/cache không chia sẻ giữa principal và có chính sách freshness.
- Log không chứa token hoặc connection payload nhạy cảm.
- Có test cho unauthorized, cross-tenant, revoked access và cancellation.

## 17. Nguyên tắc thiết kế

Xác thực connection ở đúng transport boundary, nhưng tiếp tục kiểm tra quyền cho từng GraphQL operation. Trước khi đăng ký nguồn event, xác minh principal có quyền với resource và tenant được yêu cầu. Với stream nhạy cảm hoặc quyền có thể thay đổi, kiểm tra từng event hoặc theo dõi tín hiệu thu hồi để dừng subscription. Bảo vệ cả field con của payload, vì quyền nhận event không đồng nghĩa quyền đọc mọi dữ liệu bên trong event.

Giữ security context theo đúng execution và reactive lifecycle; không dùng mutable singleton state hoặc ThreadLocal tùy tiện. Truyền principal/tenant đã xác thực vào service, giới hạn topic ở server, quản lý token expiry, cancellation và cache. Dùng WebSocketGraphQlTester cùng StepVerifier để kiểm thử cả dữ liệu được phép, dữ liệu bị từ chối và vòng đời subscription.

Trong Spring for GraphQL, subscription là một luồng thực thi kéo dài. Authorization vì thế phải bảo vệ toàn bộ vòng đời của luồng, từ lúc kết nối và đăng ký đến từng event, field con và thời điểm hủy.
