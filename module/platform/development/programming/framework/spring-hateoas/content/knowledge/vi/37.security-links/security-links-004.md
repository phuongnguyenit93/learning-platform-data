# Link cho authenticated user

Một REST API có thể trả cùng một resource cho nhiều người dùng nhưng các hành động họ được phép thực hiện lại khác nhau. Người xem đơn hàng có thể chỉ được đọc trạng thái; nhân viên xử lý có thể được duyệt đơn; người quản lý có thể được hủy hoặc hoàn tiền. Hypermedia cho phép server công bố những link tương ứng với các hành động đang khả dụng cho người dùng hiện tại.

Trong Spring HATEOAS, controller hoặc assembler có thể thêm link dựa trên `Authentication`, authority và chính sách truy cập vào resource. Ví dụ, chỉ thêm link `approve` khi người dùng đã đăng nhập, có quyền `order:approve`, là chủ thể phù hợp và đơn hàng còn ở trạng thái `PENDING`.

Link chỉ giúp client khám phá hành động. Nó không cấp quyền và cũng không thay thế việc kiểm tra quyền khi request thực sự đến server. Bài học này trình bày cách tạo link theo người dùng đã xác thực, bảo vệ endpoint bằng Spring Security, kiểm soát quyền ở cấp resource, xử lý cache representation riêng tư và kiểm thử cả việc hiện link lẫn từ chối request trái phép.

## 1. Authentication và authorization trong representation

Hai khái niệm cần được tách riêng:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Người đang gửi request là ai? | Người dùng `alice` đã đăng nhập |
| Authorization | Người đó được phép làm gì trên resource này? | `alice` có quyền đọc đơn hàng 42 nhưng không được duyệt đơn |

Spring Security cung cấp đối tượng `Authentication` để biểu diễn danh tính đã xác thực và các `GrantedAuthority` tương ứng. Ứng dụng có thể dùng thông tin này để quyết định link nào nên xuất hiện trong representation.

Ví dụ một đơn hàng có thể được biểu diễn như sau:

~~~json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/orders/42"
    },
    "acme:approve": {
      "href": "https://api.example.com/api/orders/42/approval"
    }
  }
}
~~~

Người chỉ có quyền đọc nhận được `self`, trong khi người có quyền duyệt và đáp ứng điều kiện nghiệp vụ còn nhận được `acme:approve`. Cùng một URI resource có thể trả về tập link khác nhau tùy danh tính, quyền và trạng thái hiện tại.

Điều này giúp client xây giao diện dựa trên những hành động server công bố. Client không cần tự đoán quyền từ tên role hoặc tự tái hiện toàn bộ quy tắc nghiệp vụ.

## 2. Link khả dụng không phải là bằng chứng được cấp quyền

Một link action là thông tin khám phá. Client nhìn thấy link để biết server đang công bố khả năng đó ở thời điểm representation được tạo. Giữa thời điểm GET và lúc client gửi POST, quyền của người dùng hoặc trạng thái resource có thể thay đổi.

Ví dụ:

1. `alice` GET đơn hàng 42 khi đơn hàng đang `PENDING`.
2. Server công bố link `approve`.
3. Một nhân viên khác duyệt đơn hàng trước.
4. `alice` gửi POST tới link cũ.
5. Server phải kiểm tra lại trạng thái và từ chối thao tác nếu đơn hàng không còn chờ duyệt.

Vì vậy, server cần hai lớp quyết định:

- Khi tạo representation: quyết định link nào được công bố cho người dùng hiện tại.
- Khi xử lý action request: kiểm tra lại authentication, authority, quyền trên resource và điều kiện nghiệp vụ.

Không được xem việc client có thể nhìn thấy URI là quyền truy cập. Người dùng có thể lưu link cũ, tự tạo request hoặc gọi endpoint trực tiếp mà không thông qua giao diện.

## 3. Đọc Authentication trong Spring MVC

Spring MVC có thể inject `Authentication` trực tiếp vào tham số controller:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    public EntityModel<OrderDto> getOrder(
            @PathVariable Long id,
            Authentication authentication
    ) {
        Order order = orderService.getVisibleOrder(id, authentication);
        return orderAssembler.toModel(order, authentication);
    }
}
~~~

`Authentication` cung cấp `getName()`, `getAuthorities()`, `getPrincipal()` và trạng thái xác thực. Controller có thể truyền đối tượng này cho assembler hoặc policy để quyết định link.

Với ứng dụng dùng `@AuthenticationPrincipal`, controller cũng có thể nhận principal đã được chuyển đổi sang kiểu người dùng của ứng dụng. Cách này hữu ích khi policy cần user ID hoặc tenant ID đã được ánh xạ:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@GetMapping("/api/orders/{id}")
public EntityModel<OrderDto> getOrder(
        @PathVariable Long id,
        @AuthenticationPrincipal AppUserPrincipal principal
) {
    Order order = orderService.getVisibleOrder(id, principal);
    return orderAssembler.toModel(order, principal);
}
~~~

Trong một số cấu hình, request ẩn danh vẫn có `Authentication` dạng `AnonymousAuthenticationToken`; không nên chỉ kiểm tra `authentication != null` hoặc `authentication.isAuthenticated()` để kết luận người dùng đã đăng nhập. Hãy dùng authority/policy phù hợp và loại trừ anonymous authentication rõ ràng.

## 4. Đặt quy tắc quyền trong một policy riêng

Tránh viết nhiều biểu thức kiểm tra role rải rác trong controller. Có thể gom quy tắc tạo link vào một bean policy để dễ kiểm thử và tái sử dụng:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

@Component
public class OrderActionPolicy {

    public boolean canApprove(
            Authentication authentication,
            Order order
    ) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean hasAuthority = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("order:approve"::equals);

        boolean isOwner = order.getCreatedBy()
                .equals(authentication.getName());

        return hasAuthority
                && isOwner
                && order.getStatus() == OrderStatus.PENDING;
    }
}
~~~

Ví dụ policy yêu cầu đồng thời ba điều kiện: người dùng đã đăng nhập, có authority `order:approve`, và là người tạo đơn hàng đang ở trạng thái `PENDING`. Quy tắc thực tế có thể cho phép supervisor duyệt đơn của người khác hoặc kiểm tra tenant, đơn vị kinh doanh và hạn mức.

Policy trả về boolean để controller có thể quyết định có thêm link hay không. Hãy dùng cùng quy tắc nghiệp vụ khi bảo vệ action endpoint; không duy trì hai phiên bản quy tắc gần giống nhau nhưng có thể lệch theo thời gian.

## 5. Chỉ thêm action link khi người dùng đủ quyền

Spring HATEOAS cung cấp `WebMvcLinkBuilder` để tạo link từ mapping controller. Ví dụ:

Định nghĩa relation action thành hằng số để giữ vocabulary ổn định:

~~~java
import org.springframework.hateoas.LinkRelation;

public final class OrderRelations {

    public static final LinkRelation APPROVE =
            LinkRelation.of("https://api.example.com/rels/approve");

    private OrderRelations() {
    }
}
~~~

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.ResponseEntity;

@RestController
public class OrderController {

    private final OrderService orderService;
    private final OrderActionPolicy actionPolicy;

    public OrderController(
            OrderService orderService,
            OrderActionPolicy actionPolicy
    ) {
        this.orderService = orderService;
        this.actionPolicy = actionPolicy;
    }

    @GetMapping("/api/orders/{id}")
    public EntityModel<OrderDto> one(
            @PathVariable Long id,
            Authentication authentication
    ) {
        Order order = orderService.getVisibleOrder(id, authentication);

        EntityModel<OrderDto> model = EntityModel.of(
                OrderDto.from(order),
                linkTo(methodOn(OrderController.class).one(id))
                        .withSelfRel()
        );

        if (actionPolicy.canApprove(authentication, order)) {
            Link approve = linkTo(methodOn(OrderController.class)
                    .approve(id))
                    .withRel(OrderRelations.APPROVE);

            model.add(approve);
        }

        return model;
    }

    @PostMapping("/api/orders/{id}/approval")
    public ResponseEntity<Void> approve(@PathVariable Long id) {
        orderService.approve(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

`methodOn(...)` cho Spring HATEOAS đọc mapping của handler method để dựng URI; nó không thực thi action `approve`. `OrderRelations.APPROVE` là relation đã được định nghĩa tập trung, chẳng hạn extension relation `https://api.example.com/rels/approve` và được serialize bằng CURIE nếu ứng dụng cấu hình HAL CURIE.

`getVisibleOrder(...)`, `OrderDto.from(...)`, `OrderRelations` và các kiểu domain là thành phần của ứng dụng. Việc tải đơn hàng cũng cần áp dụng quy tắc đọc dữ liệu để người dùng không nhìn thấy resource ngoài phạm vi của họ.

Nếu policy trả về `false`, representation không có link `approve`. Client có thể ẩn nút duyệt hoặc hiển thị giao diện chỉ đọc mà không cần tự suy luận authority.

## 6. Bảo vệ action bằng method security

Bảo vệ link trong representation chưa đủ. Phương thức thực hiện hành động cần được bảo vệ độc lập bằng Spring Security. Với method security hiện đại, bật annotation bằng `@EnableMethodSecurity`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Sau đó, đặt `@PreAuthorize` trên service method:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @Transactional
    @PreAuthorize("@orderAuthorization.canApprove(authentication, #orderId)")
    public void approve(@P("orderId") Long orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);

        order.approve();
    }
}
~~~

Bean `orderAuthorization` được tham chiếu trong SpEL sẽ tải resource và kiểm tra cùng quy tắc quyền trước khi phương thức được gọi:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderAuthorization")
public class OrderAuthorization {

    private final OrderRepository orderRepository;
    private final OrderActionPolicy actionPolicy;

    public OrderAuthorization(
            OrderRepository orderRepository,
            OrderActionPolicy actionPolicy
    ) {
        this.orderRepository = orderRepository;
        this.actionPolicy = actionPolicy;
    }

    public boolean canApprove(
            Authentication authentication,
            Long orderId
    ) {
        return orderRepository.findById(orderId)
                .filter(order -> actionPolicy.canApprove(authentication, order))
                .isPresent();
    }
}
~~~

Khi policy từ chối, Spring Security chặn lời gọi service và ném lỗi truy cập bị từ chối. Với HTTP request, exception translation của Spring Security chuyển kết quả thành response phù hợp theo cấu hình, thường là `403 Forbidden` cho người dùng đã xác thực nhưng không đủ quyền.

Method security không tự bật chỉ vì đã thêm Spring Boot Security starter. Cần khai báo `@EnableMethodSecurity` trong application context. Ngoài ra, annotation bảo vệ lời gọi đi qua Spring proxy; gọi một method được bảo vệ từ method khác trong cùng object (self-invocation) có thể bỏ qua proxy. Đặt ranh giới bảo vệ ở một service bean được gọi từ bên ngoài.

## 7. Kết hợp request-level security và method-level security

Request-level authorization bảo vệ bề mặt HTTP; method-level authorization bảo vệ thao tác nghiệp vụ. Có thể cấu hình `SecurityFilterChain` để cho phép GET resource công khai và yêu cầu đăng nhập cho các thao tác ghi:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .permitAll()
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .authenticated()
                        .anyRequest().denyAll()
                )
                .build();
    }
}
~~~

Đây là cấu hình minh họa cho API cho phép xem representation công khai nhưng chỉ người dùng đã đăng nhập mới được gửi POST. Service method vẫn kiểm tra quyền `order:approve` và quyền trên chính đơn hàng. Nếu API không cho phép anonymous đọc, hãy yêu cầu `authenticated()` cho GET hoặc áp dụng policy phù hợp.

Khi dùng annotation method security, những method không có annotation không tự động được bảo vệ. Hãy duy trì rule bao quát ở `HttpSecurity` thay vì để các route mới mặc định được truy cập ngoài ý muốn. Điều kiện `anyRequest().denyAll()` trong ví dụ yêu cầu ứng dụng khai báo rõ các route khác cần cho phép.

## 8. Phân biệt 401 và 403

Hai response thường gặp có ý nghĩa khác nhau:

| Status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `401 Unauthorized` | Request chưa có thông tin xác thực hợp lệ | Token thiếu, sai hoặc hết hạn |
| `403 Forbidden` | Đã xác thực nhưng không được phép thực hiện thao tác | Người dùng thiếu authority `order:approve` |

Tên `401 Unauthorized` trong HTTP dễ gây nhầm lẫn, nhưng ý nghĩa thực tế là cần xác thực hợp lệ. Với ứng dụng web dùng form login, request ẩn danh có thể bị chuyển hướng tới trang đăng nhập thay vì trả JSON 401; API thường cấu hình authentication entry point để trả response phù hợp.

Khi user đã đăng nhập nhưng không đủ quyền, không nên trả representation giả vờ thao tác đã thành công. Hãy trả lỗi nhất quán với hợp đồng API. Với resource không được phép tiết lộ sự tồn tại, ứng dụng có thể chọn phản hồi `404 Not Found` theo chính sách bảo mật, nhưng phải áp dụng nhất quán và tránh rò rỉ qua timing hoặc message.

## 9. Quyền ở cấp resource và tenant

Chỉ kiểm tra role chung như `ROLE_USER` hoặc `ROLE_ADMIN` thường chưa đủ. Người dùng có thể có quyền `order:read` nhưng chỉ được đọc đơn thuộc tenant của họ. Tương tự, hai người cùng có authority `order:approve` nhưng chỉ được duyệt các đơn thuộc nhóm được phân công.

Policy nên xét nhiều yếu tố:

- Danh tính người dùng hoặc subject ID.
- Authority cần thiết cho action.
- Owner, assignee hoặc nhóm phụ trách resource.
- Tenant hoặc phạm vi tổ chức.
- Trạng thái nghiệp vụ tại thời điểm kiểm tra.
- Hạn mức, thời hạn hoặc điều kiện phê duyệt.

Không lấy `id` do client gửi làm bằng chứng người đó sở hữu resource. Hãy tải resource ở server và so sánh với identity/tenant đã xác thực. Các kiểm tra này cần được thực hiện lại khi action endpoint xử lý request.

## 10. Không để assembler tự lấy SecurityContext toàn cục

Có thể đọc danh tính qua `SecurityContextHolder`, nhưng assembler sẽ khó kiểm thử và phụ thuộc vào thread context nếu tự lấy global state. Cách rõ ràng hơn là truyền `Authentication` hoặc principal vào phương thức dựng model:

~~~java
public EntityModel<OrderDto> toModel(
        Order order,
        Authentication authentication
) {
    EntityModel<OrderDto> model = EntityModel.of(
            OrderDto.from(order),
            linkTo(methodOn(OrderController.class)
                    .one(order.getId()))
                    .withSelfRel()
    );

    if (actionPolicy.canApprove(authentication, order)) {
        model.add(linkTo(methodOn(OrderController.class)
                .approve(order.getId()))
                .withRel(OrderRelations.APPROVE));
    }

    return model;
}
~~~

Controller lấy `Authentication` từ request rồi truyền cho assembler. Cách này làm dependency rõ ràng, dễ viết unit test cho từng người dùng và tránh phụ thuộc ngầm vào thread-local context trong tác vụ bất đồng bộ.

Nếu representation được tạo trong background job, message listener hoặc scheduled task, không giả định có người dùng HTTP hiện tại. Hãy truyền rõ service identity hoặc policy context phù hợp, hoặc tạo representation không cá nhân hóa nếu không có user context.

## 11. Link theo quyền không được làm lộ thông tin nhạy cảm

Khi tạo representation, chỉ công bố những link và metadata phù hợp với người dùng:

- Không đưa tên role nội bộ, rule SpEL hoặc lý do từ chối chi tiết vào `title` hay URI.
- Không đưa access token, session ID, secret hoặc thông tin phân quyền vào link.
- Không công bố link đến resource mà người dùng không được phép đọc chỉ để client tự nhận lỗi.
- Không dùng việc ẩn link làm cơ chế che giấu dữ liệu trong payload.
- Không serialize entity chứa field nhạy cảm chỉ vì client không có link tới action liên quan.

Quyền đọc representation và quyền thực hiện action là hai quyết định riêng. Người dùng có thể được xem một số thông tin đơn hàng nhưng không được xem địa chỉ giao hàng hoặc thông tin thanh toán. Hãy giới hạn payload bằng DTO/projection phù hợp và áp dụng authorization cho từng resource.

## 12. Cache representation được cá nhân hóa

Nếu HAL representation thay đổi theo người dùng, response có thể khác nhau dù URI giống nhau. Ví dụ `alice` thấy link `approve`, còn `bob` không thấy. Cache dùng chung mà lưu response của một người rồi trả cho người khác có thể làm lộ khả năng hoặc metadata không phù hợp.

Với representation chứa link phụ thuộc identity hoặc quyền, hãy cân nhắc:

~~~http
Cache-Control: private
~~~

Nếu dữ liệu nhạy cảm hoặc quyền thay đổi thường xuyên, có thể dùng:

~~~http
Cache-Control: no-store
~~~

`private` ngăn shared cache lưu response, nhưng vẫn cho phép cache riêng của client. `no-store` yêu cầu cache không lưu response. Nếu hệ thống có cache theo header xác thực hoặc cookie, cần thiết kế cache key và `Vary` phù hợp; chỉ thêm `Vary` không thay thế cấu hình cache an toàn.

Không cache một representation đã cá nhân hóa trong cache dùng chung theo URI đơn thuần. Cần cân nhắc thời gian hiệu lực của authority, membership, ownership và trạng thái nghiệp vụ khi chọn chính sách cache.

## 13. CSRF khi action link dùng POST

Nếu API dùng session cookie để xác thực trình duyệt, POST/PUT/PATCH/DELETE thường cần bảo vệ CSRF. Việc action link được công bố trong HAL không tự làm request an toàn khỏi CSRF.

Với ứng dụng browser dùng cookie, hãy giữ CSRF protection và cung cấp token theo cách mà client gửi được trong request. Chỉ tắt CSRF khi đã đánh giá mô hình xác thực và threat model phù hợp, ví dụ API stateless dùng bearer token trong header và không tự động gửi credential theo cơ chế cookie.

Không dùng GET để thực hiện thao tác thay đổi trạng thái như approve hoặc refund chỉ vì client dễ theo link GET. Action thay đổi dữ liệu cần HTTP method có semantics phù hợp và được bảo vệ.

## 14. Kiểm thử policy quyết định link

Policy có thể được kiểm thử độc lập bằng các trường hợp người dùng và trạng thái khác nhau:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

class OrderActionPolicyTest {

    private final OrderActionPolicy policy = new OrderActionPolicy();

    @Test
    void allowsOwnerWithApproveAuthorityForPendingOrder() {
        var authentication = new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                List.of(new SimpleGrantedAuthority("order:approve"))
        );
        Order order = Order.pending(42L, "alice");

        assertThat(policy.canApprove(authentication, order)).isTrue();
    }

    @Test
    void hidesApproveForUserWithoutAuthority() {
        var authentication = new UsernamePasswordAuthenticationToken(
                "alice",
                "n/a",
                List.of(new SimpleGrantedAuthority("order:read"))
        );
        Order order = Order.pending(42L, "alice");

        assertThat(policy.canApprove(authentication, order)).isFalse();
    }

    @Test
    void hidesApproveForNonOwner() {
        var authentication = new UsernamePasswordAuthenticationToken(
                "bob",
                "n/a",
                List.of(new SimpleGrantedAuthority("order:approve"))
        );
        Order order = Order.pending(42L, "alice");

        assertThat(policy.canApprove(authentication, order)).isFalse();
    }
}
~~~

`Order.pending(...)` là factory method minh họa của domain model. Trong ứng dụng thật, hãy tạo entity với trạng thái và owner tương ứng. Có thể bổ sung trường hợp anonymous token, đơn hàng đã duyệt, sai tenant và người quản lý có quyền đặc biệt.

## 15. Kiểm thử link xuất hiện và biến mất bằng MockMvc

Integration test nên kiểm tra representation theo hai danh tính khác nhau. Ví dụ dưới đây giả định controller nhận `Authentication` và chỉ thêm `acme:approve` khi policy trả về `true`:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@Import(WebSecurityConfiguration.class)
class OrderLinksSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    OrderService orderService;

    @MockBean
    OrderActionPolicy actionPolicy;

    @Test
    void exposesApproveLinkToAuthorizedUser() throws Exception {
        Order order = Order.pending(42L, "alice");
        when(orderService.getVisibleOrder(eq(42L), any()))
                .thenReturn(order);
        when(actionPolicy.canApprove(any(), eq(order)))
                .thenReturn(true);

        mockMvc.perform(get("/api/orders/42")
                        .with(user("alice").authorities(
                                new SimpleGrantedAuthority("order:approve")
                        )))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['acme:approve'].href").exists());
    }

    @Test
    void omitsApproveLinkForReadOnlyUser() throws Exception {
        Order order = Order.pending(42L, "alice");
        when(orderService.getVisibleOrder(eq(42L), any()))
                .thenReturn(order);
        when(actionPolicy.canApprove(any(), eq(order)))
                .thenReturn(false);

        mockMvc.perform(get("/api/orders/42")
                        .with(user("alice").authorities(
                                new SimpleGrantedAuthority("order:read")
                        )))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links['acme:approve']").doesNotExist());
    }
}
~~~

Test này minh họa phần kiểm tra link. `WebMvcTest` có thể cần import thêm cấu hình HAL, assembler và security tùy cấu trúc ứng dụng. Dependency test `spring-security-test` cần có để dùng request postprocessor `user(...)`.

## 16. Kiểm thử method security trên action service

Hãy kiểm thử service method được bảo vệ để xác nhận người dùng không thể thực hiện thao tác chỉ bằng cách tự tạo URL hoặc gọi service trực tiếp:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class OrderServiceAuthorizationTest {

    @Autowired
    OrderService orderService;

    @Test
    @WithMockUser(username = "alice", authorities = "order:read")
    void deniesApproveWhenUserHasOnlyReadAuthority() {
        assertThatThrownBy(() -> orderService.approve(42L))
                .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Test cần bật `@EnableMethodSecurity` và đăng ký bean `orderAuthorization`. Vì policy được thực thi trước thân method, request bị từ chối ngay cả khi client biết URL hoặc gọi service qua một đường khác trong application context.

Trong HTTP integration test với session cookie, request POST cũng cần CSRF token, ví dụ dùng request postprocessor `csrf()` của Spring Security Test. Nếu request-level rule chặn anonymous trước method security, hãy kiểm thử riêng cả status HTTP và service method để xác nhận đúng lớp bảo vệ đang hoạt động. Kiểm thử anonymous để xác nhận endpoint trả 401 hoặc chuyển hướng đăng nhập theo cấu hình authentication entry point.

## 17. Những lỗi thường gặp

**Chỉ ẩn link mà không bảo vệ endpoint.** Client có thể gọi URI trực tiếp. Bảo vệ service method hoặc controller bằng Spring Security.

**Chỉ kiểm tra role chung.** Kiểm tra cả owner, tenant, assignment và trạng thái resource khi nghiệp vụ yêu cầu.

**Coi `Authentication.isAuthenticated()` là đủ để loại anonymous.** Anonymous authentication có thể được đánh dấu authenticated. Kiểm tra anonymous token hoặc dùng policy nhận diện principal phù hợp.

**Đặt toàn bộ logic quyền trong controller.** Tách policy ra bean để dùng lại khi tạo link và khi kiểm tra action.

**Đọc `SecurityContextHolder` ngầm trong assembler.** Truyền `Authentication` hoặc principal vào assembler để dependency rõ ràng và dễ test.

**Tin vào link cũ.** Quyền và trạng thái có thể thay đổi sau GET. Kiểm tra lại khi action request đến.

**Để lộ field nhạy cảm dù link đã bị ẩn.** Giới hạn payload bằng DTO/projection và authorization cho resource đọc.

**Cache chung response riêng tư.** Link có thể khác theo user. Dùng cache policy phù hợp, chẳng hạn `private` hoặc `no-store`.

**Tắt CSRF chỉ vì API có hypermedia.** Action link không thay đổi threat model của cookie-based authentication.

**Không có rule mặc định cho endpoint mới.** Duy trì catch-all authorization rule trong `HttpSecurity`, vì method không gắn annotation không tự được bảo vệ.

## 18. Ghi nhớ

Spring HATEOAS có thể tạo representation riêng theo người dùng bằng cách thêm hoặc bỏ link dựa trên `Authentication`, `GrantedAuthority`, quyền sở hữu, tenant và trạng thái nghiệp vụ. Hãy đặt logic này trong policy có thể kiểm thử và truyền `Authentication` rõ ràng vào controller hoặc assembler.

Link chỉ công bố khả năng tại thời điểm tạo representation. Nó không phải bằng chứng được cấp quyền và không thay thế authorization tại endpoint. Bật `@EnableMethodSecurity`, dùng `@PreAuthorize` hoặc authorization service để kiểm tra lại action khi request đến, đồng thời duy trì request-level security rule bao quát.

Representation cá nhân hóa cần cache policy an toàn; action POST trong ứng dụng cookie-based cần tiếp tục được bảo vệ bằng CSRF. Kiểm thử cả link xuất hiện/biến mất theo user lẫn endpoint từ chối request trái phép để bảo đảm client và server cùng tuân thủ chính sách truy cập.

## Tài liệu tham khảo

- [Spring Security Reference – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference – Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html)
- [Spring Security Reference – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security API – Authentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html)
- [Spring HATEOAS Reference – Link building](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.link-builder)
- [Spring HATEOAS Reference – Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.representation-models)
