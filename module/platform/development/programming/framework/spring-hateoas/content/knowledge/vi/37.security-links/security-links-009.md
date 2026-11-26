# Kiểm thử security link trong Spring HATEOAS

API hypermedia có thể công bố hoặc ẩn link tùy theo người dùng, quyền hạn và trạng thái tài nguyên. Ví dụ, một đơn hàng đang chờ xử lý có thể có link cancel đối với người mua sở hữu đơn hoặc nhân viên quản trị; cùng đơn hàng đó không nên công bố link hủy cho người dùng khác. Khi đơn đã giao, link hủy cũng không còn phù hợp.

Kiểm thử loại link này cần xác nhận hai việc độc lập. Representation chỉ công bố những hành động phù hợp với ngữ cảnh người dùng, còn endpoint vẫn phải thực thi authorization mỗi khi nhận request. Việc ẩn link không bảo vệ endpoint khỏi một client tự gửi HTTP request. Bài học này xây dựng ma trận kiểm thử cho link theo quyền và trạng thái, dùng Spring Security Test, MockMvc và HAL response để kiểm tra cả khả năng khám phá lẫn quyền thực thi.

## 1. Security link là gì?

Security link là link hypermedia chỉ được công bố khi người dùng hiện tại được phép hoặc đủ điều kiện thực hiện một thao tác. Link có thể phụ thuộc vào:

- Danh tính người dùng hiện tại.
- Role hoặc authority được cấp.
- Quyền sở hữu tài nguyên hoặc tenant.
- Trạng thái nghiệp vụ hiện tại.
- Các điều kiện khác như thời hạn, hạn mức hoặc trạng thái phê duyệt.

Ví dụ, representation đơn hàng có thể có link cancel khi đơn đang PENDING và người dùng có quyền hủy:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": { "href": "/orders/o-42" },
    "cancel": { "href": "/orders/o-42/cancel" }
  }
}
~~~

Nếu người dùng không phải chủ đơn và không có quyền quản trị, link cancel có thể bị bỏ khỏi representation. Nếu đơn đã SHIPPED, link cũng có thể không được công bố dù người dùng là chủ đơn.

## 2. Phân biệt discoverability và authorization

Hai cơ chế này có liên quan nhưng không thay thế nhau:

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Link visibility | Client có nên nhìn thấy thao tác này trong representation hiện tại không? | Có hoặc không có _links.cancel. |
| Authorization | Server có cho phép request thực hiện thao tác không? | POST /orders/o-42/cancel được chấp nhận hay trả 403. |
| Business validation | Thao tác có hợp lệ với trạng thái hiện tại không? | Không thể hủy đơn đã giao. |

Client có thể bỏ qua link và tự tạo request tới endpoint. Vì vậy, mọi thao tác nhạy cảm phải được bảo vệ ở server bằng Spring Security và kiểm tra quy tắc nghiệp vụ. Link chỉ giúp client khám phá những hành động phù hợp.

Một kiểm thử đầy đủ cần có cả:

1. Người dùng được phép nhìn thấy link.
2. Người dùng không được phép không nhìn thấy link.
3. Request trực tiếp từ người dùng không được phép vẫn bị từ chối.
4. Request hợp lệ được chấp nhận khi cả authorization và business state đều cho phép.

## 3. Xác định policy cho thao tác

Không nên rải điều kiện role và trạng thái vào nhiều assembler hoặc controller. Tạo một policy/service có thể được dùng chung khi tạo representation và khi thực thi thao tác.

Ví dụ policy hủy đơn:

~~~java
import org.springframework.security.authentication.AnonymousAuthenticationToken;

@Component("orderAuthorization")
public class OrderAuthorization {

    private final OrderRepository orderRepository;

    public OrderAuthorization(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public boolean canCancel(Authentication authentication, UUID orderId) {
        return orderRepository.findById(orderId)
                .map(order -> canCancel(authentication, order))
                .orElse(false);
    }

    public boolean canCancel(Authentication authentication, Order order) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        boolean administrator = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        authority.getAuthority().equals("ROLE_ADMIN"));

        boolean owner = authentication.getName()
                .equals(order.getOwnerUsername());

        return order.getStatus() == OrderStatus.PENDING
                && (administrator || owner);
    }
}
~~~

Trong ví dụ, người dùng có thể hủy đơn nếu là chủ đơn hoặc quản trị viên, và đơn vẫn đang PENDING. Policy nhận Authentication và domain object để quyết định quyền theo ngữ cảnh.

Đây chỉ là ví dụ về chính sách. Ứng dụng đa tenant cần kiểm tra tenant của principal và tenant của đơn hàng; không nên chỉ so sánh username nếu quyền sở hữu được xác định bằng customer ID hoặc tenant ID.

## 4. Chỉ thêm link khi policy cho phép

Assembler có thể dùng cùng policy để quyết định có công bố relation cancel hay không:

~~~java
@Component
class OrderModelAssembler {

    private final OrderAuthorization orderAuthorization;

    OrderModelAssembler(OrderAuthorization orderAuthorization) {
        this.orderAuthorization = orderAuthorization;
    }

    EntityModel<OrderView> toModel(Order order) {
        EntityModel<OrderView> model = EntityModel.of(
                new OrderView(order.getId(), order.getStatus().name()),
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel()
        );

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (orderAuthorization.canCancel(authentication, order)) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId())).withRel("cancel"));
        }

        return model;
    }
}
~~~

self luôn được công bố theo hợp đồng, còn cancel chỉ được thêm khi policy trả về true. Assembler không thực hiện thao tác hủy; nó chỉ mô tả khả năng hiện có của tài nguyên đối với request đang xử lý.

Nếu ứng dụng tạo representation ngoài HTTP request, hãy truyền security context hoặc một đối tượng policy context tường minh thay vì phụ thuộc mù quáng vào SecurityContextHolder. Không lưu Authentication vào field của assembler singleton vì người dùng và request thay đổi liên tục.

## 5. Bảo vệ endpoint bằng method security

Controller phải kiểm tra quyền khi thao tác được gọi, kể cả khi client không nhận được link:

~~~java
@RestController
@RequestMapping("/orders")
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{orderId}/cancel")
    @PreAuthorize("@orderAuthorization.canCancel(authentication, #orderId)")
    ResponseEntity<Void> cancel(
            @PathVariable("orderId")
            @P("orderId") UUID orderId,
            Authentication authentication) {

        orderService.cancel(orderId, authentication);
        return ResponseEntity.noContent().build();
    }
}
~~~

Trong ví dụ, policy được gọi lại tại endpoint. Overload canCancel(Authentication, UUID) tải đơn theo ID rồi dùng cùng quy tắc canCancel(Authentication, Order), vì vậy assembler và method security chia sẻ một chính sách. Phương thức được gọi từ SpEL cần public. Annotation @P("orderId") giúp Spring Security tham chiếu tên tham số rõ ràng trong biểu thức SpEL.

Bật method security trong cấu hình:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Không dựa vào việc assembler đã ẩn link để bỏ @PreAuthorize hoặc kiểm tra quyền trong service. Representation và thao tác có thể được gọi từ những client khác, request cũ hoặc URI được lưu lại từ trước.

## 6. Kiểm tra trạng thái nghiệp vụ ở thời điểm thực thi

Quyền truy cập và trạng thái tài nguyên có thể thay đổi sau khi response được gửi. Ví dụ client nhận link cancel lúc đơn đang chờ, nhưng một tiến trình khác giao hàng trước khi client gọi POST.

Service cần kiểm tra trạng thái ngay trong transaction thực hiện thao tác:

~~~java
@Transactional
public void cancel(UUID orderId, Authentication authentication) {
    Order order = repository.findById(orderId)
            .orElseThrow(() -> new OrderNotFoundException(orderId));

    if (!orderAuthorization.canCancel(authentication, order)) {
        throw new AccessDeniedException("Order cannot be cancelled by this user");
    }

    order.cancel();
}
~~~

Service gọi lại cùng policy trong transaction trước khi đổi trạng thái. Nhờ đó, thay đổi owner, tenant hoặc trạng thái giữa lúc method security kiểm tra và lúc service thực hiện sẽ được đánh giá lại. Với cập nhật đồng thời, cân nhắc optimistic locking hoặc cơ chế khóa phù hợp.

## 7. Cấu hình Spring Security cho HTTP test

Một cấu hình tối thiểu có thể yêu cầu xác thực cho endpoint đơn hàng:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/orders/**").authenticated()
                        .anyRequest().permitAll())
                .build();
    }
}
~~~

Ví dụ trên minh họa xác thực ở tầng HTTP. Method security và policy quyết định người dùng được phép thao tác trên đơn cụ thể nào. Trong ứng dụng thực tế, cấu hình filter chain cần tích hợp với cơ chế xác thực đang dùng như session, OAuth2 Resource Server hoặc SSO.

Nếu endpoint dùng POST, PUT, PATCH hoặc DELETE và CSRF đang bật, test cần gửi CSRF token hợp lệ để kiểm tra authorization ở tầng method. Nếu thiếu token, request có thể bị chặn ở CSRF filter trước khi @PreAuthorize chạy.

## 8. Dùng Spring Security Test và @WithMockUser

Spring Security Test cung cấp @WithMockUser để chạy test với một principal giả lập:

Thêm dependency test nếu dự án chưa có:

~~~gradle
testImplementation("org.springframework.security:spring-security-test")
~~~

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityLinkTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "buyer-7", roles = "CUSTOMER")
    void ownerCanSeeCancelLinkForPendingOrder() throws Exception {
        mockMvc.perform(get("/orders/{id}", pendingOrderId)
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.cancel.href")
                    .value(endsWith("/orders/" + pendingOrderId + "/cancel")));
    }
}
~~~

@WithMockUser tạo người dùng với username và authorities được khai báo. roles = "CUSTOMER" tương ứng authority ROLE_CUSTOMER. Policy trong ví dụ cần nhận ra username buyer-7 là chủ đơn fixture pendingOrderId.

Nếu ứng dụng dùng custom principal với tenant ID, customer ID hoặc claims, @WithMockUser có thể không đủ. Khi đó hãy dùng @WithUserDetails, user(...) hoặc custom @WithSecurityContext để dựng principal đúng cấu trúc production.

## 9. Kiểm thử link xuất hiện cho chủ sở hữu

Test đầu tiên xác nhận người dùng được phép nhìn thấy link khi cả quyền và trạng thái đều phù hợp:

~~~java
@Test
@WithMockUser(username = "buyer-7", roles = "CUSTOMER")
void exposesCancelLinkToOwnerWhenOrderIsPending() throws Exception {
    mockMvc.perform(get("/orders/{id}", pendingOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel.href").exists());
}
~~~

Fixture phải tạo đơn PENDING thuộc buyer-7. Nếu policy còn kiểm tra tenant hoặc quyền bổ sung, fixture cần cung cấp đúng các giá trị đó.

Không chỉ kiểm tra link tồn tại; nếu URI là một phần hợp đồng, hãy xác nhận target đúng. Tránh chỉ assert cancel xuất hiện đâu đó trong JSON vì chuỗi này có thể nằm trong payload khác.

## 10. Kiểm thử link bị ẩn với người không sở hữu

Một người dùng đã xác thực nhưng không sở hữu đơn và không có role quản trị không nên thấy link cancel:

~~~java
@Test
@WithMockUser(username = "buyer-99", roles = "CUSTOMER")
void hidesCancelLinkFromAnotherCustomer() throws Exception {
    mockMvc.perform(get("/orders/{id}", pendingOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.self.href").exists())
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
~~~

Test này giả định đơn hàng thuộc buyer-7. Self link vẫn xuất hiện vì người dùng được phép đọc đơn hàng, trong khi thao tác hủy bị ẩn. Nếu chính sách không cho người khác đọc tài nguyên, endpoint GET phải trả trạng thái phù hợp như 404 hoặc 403 theo hợp đồng thay vì trả representation thiếu link.

## 11. Kiểm thử link theo role hoặc authority

Quản trị viên có thể được phép hủy đơn dù không phải chủ sở hữu:

~~~java
@Test
@WithMockUser(username = "admin-1", roles = "ADMIN")
void exposesCancelLinkToAdministrator() throws Exception {
    mockMvc.perform(get("/orders/{id}", pendingOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel.href").exists());
}
~~~

Nếu policy dùng authority cụ thể như ORDER_CANCEL, hãy dùng authorities = "ORDER_CANCEL" thay cho roles. Spring Security phân biệt role prefix ROLE_ và authority tùy chỉnh. Test phải phản ánh chính xác cách policy kiểm tra quyền.

Đừng chỉ kiểm tra một role thành công. Hãy kiểm tra một role gần giống nhưng không có quyền cần thiết, chẳng hạn SUPPORT_READONLY, để tránh cấu hình quyền quá rộng.

## 12. Kiểm thử link theo trạng thái tài nguyên

Ngay cả chủ sở hữu cũng không nên thấy link hủy nếu đơn đã giao:

~~~java
@Test
@WithMockUser(username = "buyer-7", roles = "CUSTOMER")
void hidesCancelLinkWhenOrderHasBeenShipped() throws Exception {
    mockMvc.perform(get("/orders/{id}", shippedOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("SHIPPED"))
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
~~~

Test trạng thái nên bao phủ các state quan trọng trong domain:

| Trạng thái đơn | Link cancel | Lý do |
| --- | --- | --- |
| PENDING | Có nếu người dùng có quyền | Đơn chưa được xử lý tiếp. |
| PAID | Theo chính sách nghiệp vụ | Có thể cần hủy và hoàn tiền. |
| SHIPPED | Không | Đơn đã rời kho hoặc đang giao. |
| DELIVERED | Không | Quy trình hủy không còn phù hợp. |
| CANCELLED | Không | Thao tác đã hoàn tất. |

Ma trận trên chỉ là ví dụ. Quy tắc thật phải lấy từ domain policy của ứng dụng và được kiểm thử tường minh.

## 13. Kiểm thử request trực tiếp khi link bị ẩn

Đây là test quan trọng nhất để chứng minh authorization được bảo vệ ở server. Dù representation không công bố link cancel, người dùng vẫn có thể gửi request POST thủ công:

~~~java
@Test
@WithMockUser(username = "buyer-99", roles = "CUSTOMER")
void rejectsDirectCancelRequestFromNonOwner() throws Exception {
    mockMvc.perform(post("/orders/{id}/cancel", pendingOrderId)
            .with(csrf()))
        .andExpect(status().isForbidden());
}
~~~

.with(csrf()) cung cấp token hợp lệ để request đi qua CSRF filter và kiểm tra được method authorization. Nếu bỏ CSRF token, request POST có thể bị trả 403 trước khi policy quyền chạy; khi đó test không chứng minh được @PreAuthorize hoạt động.

Hãy kiểm tra thêm rằng service hủy đơn không được gọi khi authorization thất bại. Với mock service, dùng verify(orderService, never()).cancel(...). Với integration test, xác nhận trạng thái dữ liệu không thay đổi.

Đối chiếu với trường hợp hợp lệ:

~~~java
@Test
@WithMockUser(username = "buyer-7", roles = "CUSTOMER")
void ownerCanExecuteCancelAction() throws Exception {
    mockMvc.perform(post("/orders/{id}/cancel", pendingOrderId)
            .with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

Test thành công cần dùng đơn PENDING thuộc buyer-7 và xác nhận trạng thái sau request đã chuyển sang CANCELLED hoặc trạng thái tương ứng trong domain.

## 14. Kiểm thử anonymous và người dùng chưa xác thực

Người dùng chưa đăng nhập không nên nhận link dành riêng cho thao tác hủy. Tùy API, họ có thể không được đọc tài nguyên hoặc được xem representation công khai nhưng không có link nhạy cảm.

Ví dụ khi GET resource được cho phép với anonymous:

~~~java
@Test
@WithAnonymousUser
void anonymousDoesNotSeeCancelLink() throws Exception {
    mockMvc.perform(get("/orders/{id}", publicOrderId)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
~~~

Nếu /orders/** yêu cầu authentication như cấu hình ở trên, kết quả đúng sẽ là 401 Unauthorized hoặc redirect tới trang đăng nhập tùy cơ chế xác thực. Trong trường hợp đó, test nên xác nhận trạng thái chưa xác thực thay vì kỳ vọng response HAL.

Không để anonymous nhận dữ liệu nhạy cảm chỉ vì assembler không thêm action link. Quyền đọc representation phải được quyết định độc lập.

## 15. Kiểm thử tenant và quyền sở hữu theo dữ liệu

Trong hệ thống multi-tenant, role CUSTOMER không đủ để xác định người dùng có quyền với mọi đơn hàng. Link chỉ nên xuất hiện nếu người dùng thuộc đúng tenant và có quan hệ sở hữu hợp lệ.

Ma trận test nên bao gồm:

| Người dùng | Tenant | Chủ đơn | Kết quả link |
| --- | --- | --- | --- |
| buyer A | tenant A | buyer A, tenant A | Có nếu state cho phép. |
| buyer B | tenant A | buyer A, tenant A | Không. |
| buyer A | tenant B | buyer A, tenant A | Không nếu tenant không khớp. |
| admin A | tenant A | buyer A, tenant A | Theo quyền quản trị tenant. |
| admin B | tenant B | buyer A, tenant A | Không nếu admin không có quyền xuyên tenant. |

Test cần tạo principal có tenant/customer context thật. Nếu chỉ dùng username, test có thể bỏ sót lỗi truy cập chéo tenant. Cũng cần gửi request trực tiếp tới endpoint từ từng principal để xác nhận server áp dụng cùng policy.

## 16. Kiểm thử link và affordance cho thao tác ghi

Một HAL link thông thường chỉ cung cấp relation và href; nó không nhất thiết mô tả HTTP method hoặc request body. Nếu client cần biết thao tác là POST và có template input nào, API có thể công bố affordance hoặc HAL-FORMS template.

Khi có affordance, kiểm thử hai khía cạnh:

- Link relation như cancel chỉ xuất hiện khi policy cho phép.
- Metadata thao tác chỉ mô tả method và input hợp lệ theo hợp đồng, ví dụ POST không yêu cầu body hoặc template chứa các trường được phép.

Với HAL-FORMS, có thể kiểm tra _templates theo template name đã công bố, method và danh sách property. Tên template và JSON path phải theo cấu hình thực tế của ứng dụng; đừng giả định mọi affordance đều được serialize thành cùng một template name.

Không công bố affordance ghi dữ liệu cho người dùng không có quyền rồi chỉ dựa vào việc endpoint sẽ từ chối. Client sẽ hiểu rằng hành động đó đang được đề xuất. Đồng thời, server vẫn phải xác thực mọi request dù affordance không xuất hiện.

## 17. Kiểm thử thay đổi quyền giữa hai request

Link phản ánh quyền tại thời điểm server tạo representation. Quyền có thể thay đổi trước khi client thực hiện thao tác, ví dụ tài khoản bị khóa, role bị thu hồi hoặc đơn chuyển trạng thái.

Một test hữu ích:

1. Đăng nhập với principal được phép và GET representation.
2. Xác nhận link cancel xuất hiện.
3. Thay đổi trạng thái đơn hoặc thu hồi quyền.
4. Gửi POST tới URI đã lấy ở bước đầu.
5. Xác nhận request bị từ chối và dữ liệu không bị thay đổi.

Test này chứng minh server đánh giá lại policy khi thao tác thực sự được gọi. Không cache quyết định authorization trong link hoặc giữ một boolean quyền từ response trước đó.

## 18. Các lỗi thường gặp khi kiểm thử security link

**Cho rằng ẩn link là đủ bảo mật.** Gửi request trực tiếp tới endpoint để xác nhận server từ chối người không có quyền.

**Chỉ test role, bỏ qua ownership.** Hai người có cùng role có thể có quyền khác nhau trên từng tài nguyên.

**Chỉ test ownership, bỏ qua tenant.** Kiểm tra cả tenant của principal và tenant của resource.

**Không test trạng thái nghiệp vụ.** Chủ đơn không nhất thiết được hủy đơn ở mọi trạng thái.

**Test POST thiếu CSRF token.** Thêm .with(csrf()) khi mục tiêu là kiểm tra method authorization.

**Dùng @WithMockUser cho custom principal phức tạp.** Dùng @WithUserDetails hoặc custom security context để dựng đúng claims và tenant context.

**Chỉ kiểm tra link có tồn tại.** Kiểm tra đúng relation, href, method/template metadata nếu API công bố affordance.

**Để policy khác nhau giữa assembler và controller.** Dùng chung policy service và vẫn kiểm tra lại khi thực thi.

**Không kiểm tra quyền bị thu hồi giữa các request.** Gửi request tới link cũ sau khi quyền hoặc state thay đổi.

**Xem ẩn link là kiểm soát quyền đọc.** Authorization cho representation và authorization cho thao tác là hai quyết định riêng.

## 19. Bài tập thực hành và tiêu chí hoàn thành

Hãy xây dựng security link cho thao tác hủy đơn hàng:

1. Tạo policy OrderAuthorization kiểm tra principal, owner, tenant và trạng thái đơn.
2. Dùng policy để chỉ thêm relation cancel vào representation khi được phép.
3. Bảo vệ endpoint POST bằng @PreAuthorize và bật @EnableMethodSecurity.
4. Viết test chủ đơn có link khi đơn PENDING.
5. Viết test người dùng cùng role nhưng không sở hữu đơn không có link.
6. Viết test quản trị viên có link trong tenant được phép.
7. Viết test chủ đơn không có link khi đơn đã SHIPPED hoặc DELIVERED.
8. Gửi POST trực tiếp từ người không có quyền với CSRF token hợp lệ và xác nhận 403.
9. Xác nhận service không được gọi và dữ liệu không đổi khi authorization thất bại.
10. Kiểm thử anonymous theo chính sách đọc resource của API.
11. Thay đổi role hoặc trạng thái sau khi GET link rồi xác nhận request POST cũ bị từ chối.
12. Nếu API công bố affordance/HAL-FORMS, kiểm tra method và input metadata chỉ xuất hiện cho người dùng đủ quyền.

Bạn đã nắm được cách kiểm thử security link khi có thể xác nhận link được công bố đúng theo role, ownership, tenant và trạng thái; đồng thời chứng minh endpoint vẫn từ chối request trái phép ngay cả khi client tự tạo URI. Representation phản ánh khả năng hiện tại của người dùng, còn server là nơi thực thi authorization và kiểm tra state transition ở thời điểm thao tác.

## Tài liệu tham khảo chính thức

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security – MockMvc Support](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html)
- [Spring HATEOAS – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
