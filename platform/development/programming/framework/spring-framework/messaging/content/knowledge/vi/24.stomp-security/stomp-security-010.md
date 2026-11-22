# Phân quyền đối tượng nghiệp vụ ngoài kiểm tra đường dẫn đích

## Mục tiêu

Trong STOMP over WebSocket, Spring Security có thể kiểm tra destination như `/app/orders/**` và yêu cầu người gửi có authority `ORDER_WRITE`. Quy tắc này hữu ích để kiểm soát loại thao tác, nhưng chưa đủ để quyết định người dùng có quyền thao tác trên một đơn hàng cụ thể hay không.

Ví dụ, hai người dùng đều có `ORDER_WRITE`. Người dùng Alice có quyền hủy đơn hàng của mình, nhưng không được hủy đơn hàng của Bob. Nếu chỉ kiểm tra destination `/app/orders/123/cancel`, Alice có thể thử thay ID thành đơn hàng của Bob. Đường dẫn vẫn khớp pattern và authority vẫn hợp lệ.

Cần thực hiện thêm **phân quyền theo đối tượng nghiệp vụ** (object-level authorization): tải hoặc truy vấn đối tượng cần thao tác, rồi kiểm tra quyền của người dùng hiện tại đối với chính đối tượng đó, trong đúng tenant, quan hệ sở hữu, vai trò và trạng thái nghiệp vụ.

Bài này trình bày hai điểm kiểm soát quan trọng:

- Với STOMP `MESSAGE` gửi vào `/app/**`, kiểm tra quyền trên đối tượng trong service nghiệp vụ, thường bằng method security.
- Với STOMP `SUBSCRIBE` tới destination đại diện cho một đối tượng như `/topic/orders/{orderId}`, kiểm tra quyền đọc đối tượng ngay trên inbound message authorization trước khi broker lưu subscription.

## 1. Destination authorization và object authorization

Hai loại kiểm tra trả lời hai câu hỏi khác nhau:

| Kiểm tra | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Ai đang kết nối? | Principal là `alice` |
| Destination authorization | Người dùng có được gửi/subscribe loại message này không? | Chỉ `ORDER_WRITE` mới gửi tới `/app/orders/**` |
| Object-level authorization | Người dùng có quyền trên bản ghi cụ thể không? | Alice chỉ được hủy đơn hàng thuộc sở hữu của Alice |
| Business rule | Thao tác có hợp lệ theo trạng thái nghiệp vụ không? | Chỉ đơn hàng đang `PENDING` mới được hủy |

Destination pattern chỉ so khớp chuỗi destination và loại message. Nó không tự tải đơn hàng, không biết người dùng có thuộc tenant của đơn hàng hay không và cũng không xác nhận trạng thái đơn hàng.

Không lấy ID đối tượng, username, tenant hoặc quyền sở hữu từ payload của client làm bằng chứng. Client có thể sửa mọi giá trị đó. Danh tính phải lấy từ `Authentication`/`Principal` đã được server xác thực; quan hệ với đối tượng phải được xác minh bằng dữ liệu phía server.

## 2. Xác định điểm kiểm tra theo loại STOMP message

STOMP có hai loại inbound message thường cần kiểm soát riêng:

- **MESSAGE**: client gửi dữ liệu vào ứng dụng, ví dụ `SEND /app/orders/{orderId}/cancel`. Spring định tuyến message này tới `@MessageMapping`; controller gọi service nghiệp vụ.
- **SUBSCRIBE**: client đăng ký nhận dữ liệu, ví dụ `SUBSCRIBE /topic/orders/{orderId}`. Broker có thể xử lý subscription trực tiếp, không đi qua một phương thức `@MessageMapping`.

Vì vậy:

- Đối với MESSAGE, destination matcher có thể kiểm tra authority tổng quát; service vẫn phải kiểm tra quyền trên đối tượng trước khi đọc hoặc thay đổi nó.
- Đối với SUBSCRIBE, cần kiểm tra quyền đọc đối tượng ngay trên message authorization. Nếu cho phép subscribe chỉ vì người dùng có role chung, người dùng có thể đăng ký topic của đối tượng thuộc về người khác.

Spring Security bảo vệ `clientInboundChannel`; nó không chạy authorization riêng cho từng message trên `clientOutboundChannel`. Cách quan trọng để tránh rò rỉ dữ liệu là chỉ cho phép subscription mà người dùng có quyền tạo.

## 3. Cấu hình quyền tổng quát cho STOMP

Ví dụ dùng Spring Security 7 và `AuthorizationManager`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
@EnableMethodSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages,
            OrderSubscriptionAuthorizationManager orderSubscriptionAuthorizationManager) {

        messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/topic/orders/{orderId}")
                    .access(orderSubscriptionAuthorizationManager)
                .simpMessageDestMatchers("/app/orders/**")
                    .hasAuthority("ORDER_WRITE")
                .simpTypeMatchers(SimpMessageType.MESSAGE, SimpMessageType.SUBSCRIBE)
                    .denyAll()
                .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Ý nghĩa:

- `@EnableWebSocketSecurity` bật tích hợp authorization cho STOMP message.
- `@EnableMethodSecurity` bật các annotation như `@PreAuthorize` trên service.
- `nullDestMatcher().authenticated()` yêu cầu xác thực cho các message không có destination, như CONNECT hoặc DISCONNECT.
- `simpSubscribeDestMatchers(...)` chỉ khớp loại SUBSCRIBE có destination tương ứng.
- `simpMessageDestMatchers(...)` chỉ khớp loại MESSAGE, tức client gửi vào handler ứng dụng.
- `denyAll()` từ chối các MESSAGE/SUBSCRIBE còn lại chưa có quy tắc cho phép.
- `anyMessage().denyAll()` là quy tắc cuối để không vô tình cho phép một loại message mới chưa được cấu hình.

Thứ tự các matcher quan trọng: Spring dùng quy tắc khớp đầu tiên. Đặt quy tắc cụ thể trước quy tắc từ chối tổng quát.

Đây là allowlist minh họa. Ứng dụng thực tế cần thêm từng destination công khai hoặc riêng tư theo đúng chính sách, đồng thời giữ quy tắc từ chối mặc định ở cuối.

## 4. Phân quyền object khi client gửi MESSAGE

Giả sử client gửi lệnh hủy đơn hàng tới destination:

~~~text
/app/orders/7f1d6c3e-1d5b-4d7c-9f7a-9f1d4c8c7a10/cancel
~~~

Controller nhận ID từ destination và payload lệnh:

~~~java
import java.util.UUID;
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessageController {

    private final OrderCommandService orderCommandService;

    public OrderMessageController(OrderCommandService orderCommandService) {
        this.orderCommandService = orderCommandService;
    }

    @MessageMapping("/orders/{orderId}/cancel")
    public void cancel(
            @DestinationVariable UUID orderId,
            @Payload CancelOrderCommand command) {

        orderCommandService.cancelOrder(orderId, command);
    }
}
~~~

Với cấu hình application prefix `/app`, destination thực tế từ client là `/app/orders/{orderId}/cancel`. Controller chỉ nhận ID và lệnh; không tin một trường `ownerUsername` hay `tenantId` do client gửi.

Đặt kiểm tra quyền trên service nghiệp vụ để các đường gọi khác như HTTP controller, scheduled job hoặc một service khác cũng không bỏ qua quy tắc:

~~~java
import java.util.UUID;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;

    public OrderCommandService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @PreAuthorize("@orderAccess.canCancelOrder(authentication, #orderId)")
    @Transactional
    public void cancelOrder(
            @P("orderId") UUID orderId,
            CancelOrderCommand command) {

        Order order = orderRepository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);

        // Kiểm tra lại invariant trong transaction trước khi thay đổi.
        if (order.getStatus() != OrderStatus.PENDING) {
            throw new IllegalStateException("Only pending orders can be cancelled");
        }

        order.cancel(command.reason());
    }
}
~~~

`@PreAuthorize` được đánh giá trước khi phương thức service chạy. Bean `orderAccess` kiểm tra người dùng hiện tại có quyền hủy đúng đơn hàng đó hay không. `@P("orderId")` đặt tên tham số rõ ràng để biểu thức `#orderId` hoạt động ổn định khi biên dịch.

Phương thức service phải được gọi qua Spring bean proxy để method security có hiệu lực. Gọi nội bộ cùng object bằng self-invocation sẽ không đi qua proxy và có thể bỏ qua interceptor.

## 5. Viết policy kiểm tra quyền trên đối tượng

Một bean policy có thể gom logic sở hữu, tenant, membership và trạng thái:

~~~java
import java.util.UUID;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderAccess")
public class OrderAccessService {

    private final OrderRepository orderRepository;

    public OrderAccessService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public boolean canCancelOrder(
            Authentication authentication,
            UUID orderId) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        return orderRepository.findByIdAndOwnerUsername(
                        orderId,
                        authentication.getName())
                .map(order -> order.getStatus() == OrderStatus.PENDING)
                .orElse(false);
    }

    public boolean canReadOrder(String username, String rawOrderId) {
        final UUID orderId;

        try {
            orderId = UUID.fromString(rawOrderId);
        }
        catch (IllegalArgumentException ex) {
            return false;
        }

        return orderRepository.existsByIdAndOwnerUsername(orderId, username);
    }
}
~~~

Các phương thức repository minh họa:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, UUID> {

    Optional<Order> findByIdAndOwnerUsername(UUID id, String ownerUsername);

    boolean existsByIdAndOwnerUsername(UUID id, String ownerUsername);
}
~~~

Ví dụ kiểm tra chủ sở hữu để dễ đọc. Trong hệ thống multi-tenant, truy vấn cần bao gồm tenant hiện tại, ví dụ `existsByIdAndOwnerUsernameAndTenantId(...)`. Nếu quyền dựa trên nhóm, dự án hoặc quan hệ chia sẻ, policy cần kiểm tra membership tương ứng. Không tải một đối tượng theo ID rồi chỉ kiểm tra role chung mà bỏ qua tenant hoặc quan hệ sở hữu.

Trả về `false` khi ID không hợp lệ, đối tượng không tồn tại hoặc người dùng không có quyền giúp tránh vô tình cho client biết một bản ghi riêng tư có tồn tại hay không. Tùy chính sách API, ứng dụng có thể ánh xạ các trường hợp này về cùng một lỗi truy cập.

## 6. Phân quyền object khi client SUBSCRIBE topic theo ID

Một subscription như `/topic/orders/{orderId}` có thể được broker xử lý trực tiếp. Vì vậy, đặt kiểm tra trong controller `@MessageMapping` là chưa đủ; controller không được gọi khi client chỉ SUBSCRIBE.

Spring Security cho phép gắn một `AuthorizationManager<MessageAuthorizationContext<?>>` vào matcher. Context chứa message và các biến đường dẫn được trích xuất từ destination pattern.

Tạo manager riêng:

~~~java
import java.util.function.Supplier;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class OrderSubscriptionAuthorizationManager
        implements AuthorizationManager<MessageAuthorizationContext<?>> {

    private final OrderAccessService orderAccess;

    public OrderSubscriptionAuthorizationManager(OrderAccessService orderAccess) {
        this.orderAccess = orderAccess;
    }

    @Override
    public AuthorizationResult authorize(
            Supplier<? extends Authentication> authentication,
            MessageAuthorizationContext<?> context) {

        Authentication current = authentication.get();
        String orderId = context.getVariables().get("orderId");

        boolean granted = current != null
                && current.isAuthenticated()
                && !(current instanceof AnonymousAuthenticationToken)
                && orderId != null
                && orderAccess.canReadOrder(current.getName(), orderId);

        return new AuthorizationDecision(granted);
    }
}
~~~

Matcher trong cấu hình bảo mật:

~~~java
.simpSubscribeDestMatchers("/topic/orders/{orderId}")
    .access(orderSubscriptionAuthorizationManager)
~~~

Spring trích xuất `orderId` từ destination theo pattern và đặt vào `context.getVariables()`. Manager lấy Authentication của người gửi, sau đó gọi policy phía server để kiểm tra user có quyền đọc đơn hàng đó không. Nếu ID thiếu, sai định dạng, không tồn tại hoặc không thuộc người dùng, manager trả quyết định từ chối.

Đây là điểm khác biệt quan trọng giữa `simpSubscribeDestMatchers` và `simpMessageDestMatchers`: matcher đầu chỉ xử lý SUBSCRIBE, matcher sau chỉ xử lý MESSAGE.

## 7. Phân biệt quyền gửi lệnh và quyền đọc topic

Một người dùng có thể được phép đọc một đơn hàng nhưng không được phép hủy nó. Ngược lại, một dịch vụ quản trị có thể được phép hủy đơn hàng theo quy trình hỗ trợ nhưng không nên tự động được subscribe vào mọi topic riêng tư.

Nên định nghĩa policy theo hành động:

| Hành động | Destination / điểm gọi | Policy |
|---|---|---|
| Hủy đơn | MESSAGE `/app/orders/{id}/cancel` | Có authority gửi lệnh, là chủ đơn hoặc có quyền quản trị phù hợp, trạng thái cho phép |
| Theo dõi đơn | SUBSCRIBE `/topic/orders/{id}` | Có quyền đọc đơn hàng trong tenant |
| Nhận thông báo cá nhân | SUBSCRIBE `/user/queue/notifications` | Đúng user đã xác thực và session của user |
| Gửi message trực tiếp vào topic | MESSAGE `/topic/**` | Thường từ chối client để tránh giả mạo thông báo server |

Không dùng một hàm `hasRole("USER")` duy nhất cho tất cả hành động trên mọi đối tượng. Role chỉ mô tả năng lực tổng quát; quyền trên một bản ghi cần xét ngữ cảnh cụ thể.

## 8. Authentication và dữ liệu từ client

Trong ứng dụng web thông thường, Spring gắn `Principal` đã xác thực từ HTTP handshake vào WebSocket session và các STOMP message sau đó. Client không được tự chọn danh tính bằng cách gửi một trường `username` trong payload.

Với token authentication, ứng dụng có thể xác thực token ở STOMP CONNECT bằng `ChannelInterceptor`, sau đó gọi `StompHeaderAccessor.setUser(authentication)`. Interceptor xác thực phải chạy trước interceptor authorization để `Authentication` đã sẵn sàng khi Spring Security đánh giá message.

Ngoài ra:

- Giữ quy tắc origin phù hợp và cơ chế CSRF cho STOMP CONNECT theo cấu hình Spring Security.
- Không tin `ownerId`, `tenantId`, `role` hoặc `isAdmin` do client gửi.
- Kiểm tra quyền trên server ở mọi đường truy cập dữ liệu, kể cả REST, STOMP, batch hoặc scheduled job.
- Validate payload riêng với authorization. Dữ liệu hợp lệ về cú pháp vẫn có thể không được phép cho đối tượng đó.
- Không để client gửi MESSAGE trực tiếp vào broker destination nội bộ hoặc topic chỉ dành cho server.

## 9. Thu hồi quyền khi subscription đang hoạt động

Authorization trên SUBSCRIBE được kiểm tra tại thời điểm client đăng ký subscription. Nếu người dùng bị xóa khỏi nhóm hoặc mất quyền truy cập sau đó, subscription đã được tạo có thể vẫn tồn tại và tiếp tục nhận message.

Nếu quyền có thể thay đổi trong khi WebSocket vẫn mở, cần có cơ chế xử lý thu hồi:

1. Khi membership hoặc quyền truy cập bị thu hồi, tìm các session/subscription liên quan.
2. Gửi lệnh unsubscribe hoặc đóng session theo chính sách ứng dụng, hoặc áp dụng cơ chế broker ACL phù hợp.
3. Với dữ liệu nhạy cảm, cân nhắc kiểm tra quyền lại ở luồng phát trước khi gửi hoặc phát qua user destination phù hợp.
4. Không dựa vào kiểm tra SUBSCRIBE ban đầu như một cam kết rằng quyền sẽ tồn tại vĩnh viễn.

Spring Security không kiểm tra authorization riêng trên từng message outbound; bảo vệ subscription và xử lý thu hồi là phần quan trọng của thiết kế.

## 10. Hiệu năng và nhất quán dữ liệu

Object-level authorization có thể cần truy vấn database cho mỗi message hoặc subscription. Để giữ hiệu năng:

- Dùng truy vấn hẹp như `existsByIdAndOwnerUsernameAndTenantId` thay vì tải toàn bộ graph entity.
- Đánh index cho các cột ID, owner, tenant và membership được dùng trong policy.
- Chỉ cache quyết định quyền khi có chiến lược invalidation rõ ràng; cache cũ có thể giữ quyền đã bị thu hồi.
- Với thao tác ghi, thực hiện kiểm tra trạng thái và thay đổi dữ liệu trong cùng transaction; cân nhắc optimistic/pessimistic locking nếu có tranh chấp.
- Trả về quyết định deny khi không thể xác minh quyền. Lỗi database hoặc policy service không nên tự động biến thành allow.

Đặc biệt, kiểm tra trong `@PreAuthorize` và thao tác ghi trong service có thể xảy ra cách nhau. Vì vậy, service vẫn cần bảo vệ các invariant nghiệp vụ trong transaction để tránh trạng thái thay đổi giữa lúc authorize và lúc update.

## 11. Kiểm thử phân quyền object-level

Một bộ test hữu ích cần kiểm tra cả đường đi được phép và bị từ chối:

| Tình huống | Kết quả mong đợi |
|---|---|
| Alice có `ORDER_WRITE`, là chủ đơn PENDING | Cho phép MESSAGE hủy đơn |
| Alice có `ORDER_WRITE`, nhưng đơn thuộc Bob | Từ chối MESSAGE dù destination khớp |
| Alice là chủ đơn nhưng đơn đã SHIPPED | Từ chối hủy do business rule |
| Alice subscribe topic của đơn mình | Cho phép SUBSCRIBE |
| Alice subscribe topic của đơn Bob | Từ chối SUBSCRIBE |
| User không đăng nhập hoặc anonymous | Từ chối destination riêng tư |
| ID sai định dạng hoặc không tồn tại | Từ chối |
| Client gửi MESSAGE trực tiếp tới `/topic/orders/**` | Từ chối |
| Membership bị thu hồi sau khi subscribe | Hệ thống thực hiện quy trình thu hồi subscription hoặc session |

Nên có:

- Unit test cho `OrderAccessService` với chủ sở hữu, người ngoài, tenant khác và trạng thái đơn hàng.
- Unit test cho `OrderSubscriptionAuthorizationManager` với path variable thiếu, authentication null và các kết quả policy khác nhau.
- Integration test STOMP xác minh MESSAGE bị chặn trước controller khi thiếu authority và SUBSCRIBE bị chặn trước broker khi không có quyền đọc.
- Test method security gọi service qua Spring proxy để chắc chắn `@PreAuthorize` thực sự được thực thi.

Chỉ test destination matcher không đủ để chứng minh object-level authorization đúng. Cần test bằng hai danh tính khác nhau và các đối tượng có quan hệ sở hữu khác nhau.

## Ghi nhớ

- Destination authorization kiểm tra loại message và đường dẫn; object-level authorization kiểm tra quyền trên bản ghi thực tế.
- Client không được quyết định chủ sở hữu, tenant hoặc danh tính bằng payload.
- Với MESSAGE vào `/app/**`, kiểm tra quyền đối tượng ở service nghiệp vụ, ví dụ `@PreAuthorize`.
- Với SUBSCRIBE tới topic theo ID, dùng custom `AuthorizationManager<MessageAuthorizationContext<?>>` và `context.getVariables()`.
- Tách quyền đọc, quyền ghi và business rule theo từng hành động.
- Spring Security kiểm tra inbound channel; phải bảo vệ subscription để kiểm soát dữ liệu outbound.
- Khi quyền bị thu hồi, xử lý cả các subscription đang tồn tại.
- Với thao tác ghi, kiểm tra lại invariant trong transaction để tránh race condition.

## Tài liệu tham khảo

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/7.0/servlet/integrations/websocket.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/method-security.html)
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/architecture.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/7.0/web/websocket/stomp/handle-annotations.html)
- [MessageAuthorizationContext API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/messaging/access/intercept/MessageAuthorizationContext.html)
