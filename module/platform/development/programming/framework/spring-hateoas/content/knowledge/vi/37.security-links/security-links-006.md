# Scope-based resource

Trong REST API, một access token có thể mang các **scope** mô tả những nhóm thao tác mà client được phép yêu cầu, chẳng hạn đọc đơn hàng, tạo đơn hoặc hủy đơn. Khi Spring Security xác thực token, các scope có thể được ánh xạ thành authority để bảo vệ endpoint. Spring HATEOAS bổ sung một lớp khám phá: response chỉ công bố những link phù hợp với quyền và trạng thái của resource hiện tại.

Scope giúp xác định quyền ở mức API hoặc nhóm chức năng. Nó không tự quyết định người dùng có được truy cập mọi đơn hàng hay không. Một người có scope orders.read vẫn có thể chỉ được đọc đơn hàng thuộc tenant của mình; một người có orders.cancel vẫn không thể hủy đơn đã giao. Vì vậy, cần kết hợp scope với authorization theo từng resource, tenant và trạng thái nghiệp vụ.

## Scope là gì?

OAuth 2.0 scope là chuỗi định danh quyền được authorization server cấp cho client hoặc principal. Ví dụ một token có thể chứa:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.cancel",
  "tenant_id": "tenant-42"
}
~~~

Trong ví dụ:

- orders.read cho phép gọi các chức năng đọc đơn hàng.
- orders.cancel cho phép yêu cầu chức năng hủy đơn.
- tenant_id là claim riêng của hệ thống để xác định tenant, không phải OAuth scope.
- iss, aud, chữ ký và thời hạn token giúp resource server xác minh token được phát hành cho đúng hệ thống và còn hiệu lực.

Tên scope là một phần hợp đồng giữa authorization server, resource server và client. Nên đặt tên theo tài nguyên và hành động, dùng một quy ước nhất quán như orders.read, orders.write, orders.cancel. Scope nên đủ cụ thể để cấp quyền theo nhu cầu tối thiểu, nhưng không nên tạo scope cho từng bản ghi dữ liệu.

## Scope được ánh xạ thành authority trong Spring Security

Với Spring Security OAuth2 Resource Server, JwtAuthenticationProvider xác thực JWT và JwtGrantedAuthoritiesConverter chuyển các claim scope thành GrantedAuthority. Mặc định, converter đọc claim scope hoặc scp, tách các giá trị cách nhau bằng khoảng trắng và thêm tiền tố SCOPE_.

Ví dụ claim:

~~~json
{
  "scope": "orders.read orders.cancel"
}
~~~

được ánh xạ thành hai authority:

~~~text
SCOPE_orders.read
SCOPE_orders.cancel
~~~

Do đó, cấu hình authorization thường kiểm tra authority có tiền tố SCOPE_, không kiểm tra chuỗi scope thô trực tiếp.

## Cấu hình Resource Server nhận JWT

Thêm dependency resource server tương ứng với phiên bản Spring Boot/Spring Security của ứng dụng. Khi dùng Spring Boot, cấu hình issuer URI để Spring có thể khám phá khóa công khai và xác minh JWT:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

Khai báo security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(
                    HttpMethod.POST,
                    "/orders/*/cancellation"
                ).hasAuthority("SCOPE_orders.cancel")
                .requestMatchers(
                    HttpMethod.GET,
                    "/orders/**"
                ).hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST,
                    "/orders/**"
                ).hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Thứ tự matcher có ý nghĩa: matcher POST cho cancellation được đặt trước matcher POST tổng quát để scope orders.cancel được áp dụng cho đúng action. Các request khác phải được xác thực và chịu các quy tắc tương ứng.

Ví dụ trên minh họa bảo vệ theo HTTP method và path. Trong hệ thống thực tế, có thể tách các filter chain hoặc matcher theo API version, audience và loại resource. Cần bảo đảm JWT được kiểm tra issuer, chữ ký, thời hạn và audience theo yêu cầu của hệ thống; chỉ đọc claim scope mà không xác minh token là không đủ.

## Khi claim scope có tên khác

Một số identity provider dùng claim riêng như permissions hoặc cấu trúc claim khác. Khi đó có thể tùy chỉnh JwtGrantedAuthoritiesConverter:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
class JwtAuthorityConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter authoritiesConverter =
            new JwtGrantedAuthoritiesConverter();

        authoritiesConverter.setAuthoritiesClaimName("permissions");
        authoritiesConverter.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter authenticationConverter =
            new JwtAuthenticationConverter();
        authenticationConverter.setJwtGrantedAuthoritiesConverter(
            authoritiesConverter);

        return authenticationConverter;
    }
}
~~~

Đăng ký converter trong resource server:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.jwtAuthenticationConverter(
        jwtAuthenticationConverter)))
~~~

Đoạn cấu hình cần được đặt trong bean SecurityFilterChain và inject converter qua constructor hoặc method parameter. Nếu claim permissions chứa một collection các chuỗi, converter có thể chuyển từng phần tử thành authority. Nếu identity provider phát cấu trúc lồng nhau hoặc giá trị không phải chuỗi, cần triển khai converter phù hợp thay vì giả định cấu trúc mặc định.

Không tùy tiện đổi authority prefix giữa các môi trường. Scope name và cách ánh xạ phải được thống nhất với authorization server và test contract.

## Phân biệt scope, role và quyền trên resource

Ba khái niệm thường được kết hợp nhưng giải quyết các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Scope | Client/principal được gọi nhóm chức năng API nào? | orders.read, orders.cancel |
| Role | Người dùng thuộc nhóm chức năng hoặc trách nhiệm nào? | ROLE_SUPPORT, ROLE_MANAGER |
| Resource permission | Người dùng có quyền trên bản ghi cụ thể nào? | Chỉ đọc đơn hàng thuộc tenant của mình |

Một scope không nhất thiết tương đương một role. Scope thường được cấp cho access token theo client, user và authorization grant. Role là phân loại người dùng hoặc nhóm. Resource permission cần kiểm tra thuộc tính của bản ghi, tenant, chủ sở hữu và trạng thái nghiệp vụ.

Không dùng orders.read để thay thế mọi kiểm tra quyền sở hữu. Nếu chỉ kiểm tra scope ở endpoint GET /orders/{id}, người dùng có scope đọc có thể thử thay ID để truy cập đơn hàng của tenant khác.

## Bảo vệ một resource cụ thể

Bật method security để kiểm tra quyền ở tầng controller hoặc service:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Ví dụ policy kiểm tra scope và tenant:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderAuthorization")
class OrderAuthorization {

    private final OrderRepository orderRepository;
    private final TenantResolver tenantResolver;

    OrderAuthorization(
            OrderRepository orderRepository,
            TenantResolver tenantResolver) {
        this.orderRepository = orderRepository;
        this.tenantResolver = tenantResolver;
    }

    public boolean canRead(Authentication authentication, UUID orderId) {
        if (!hasScope(authentication, "orders.read")) {
            return false;
        }

        return orderRepository.existsByIdAndTenantId(
            orderId,
            tenantResolver.tenantId(authentication)
        );
    }

    public boolean canCancel(Authentication authentication, UUID orderId) {
        if (!hasScope(authentication, "orders.cancel")) {
            return false;
        }

        return orderRepository.findByIdAndTenantId(
                orderId,
                tenantResolver.tenantId(authentication))
            .filter(order -> order.getStatus() == OrderStatus.PENDING)
            .isPresent();
    }

    private boolean hasScope(Authentication authentication, String scope) {
        String requiredAuthority = "SCOPE_" + scope;

        return authentication.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals(requiredAuthority));
    }
}
~~~

TenantResolver là thành phần của ứng dụng, lấy tenant đã được xác thực từ claim hoặc principal. Không lấy tenant ID từ query parameter do client tự gửi làm căn cứ duy nhất để cấp quyền. Các phương thức repository minh họa truy vấn có điều kiện tenant; cần khai báo chúng trong repository thực tế.

Đặt policy trên endpoint:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/orders/{id}")
@PreAuthorize("@orderAuthorization.canRead(authentication, #id)")
EntityModel<OrderRepresentation> one(@P("id") @PathVariable UUID id) {
    // Tải representation và tạo link.
}
~~~

@P("id") giúp đặt tên tham số rõ ràng trong biểu thức method security. Có thể dùng tên tham số được biên dịch với tùy chọn -parameters, nhưng annotation tường minh tránh phụ thuộc cấu hình compiler.

Với các thao tác thay đổi dữ liệu, nên đặt authorization ở service/application layer hoặc bảo vệ cả service method để mọi đường gọi đều chịu cùng policy. Không chỉ bảo vệ controller nếu cùng nghiệp vụ còn được gọi từ message listener, scheduler hoặc một API khác.

## Lọc collection theo tenant ngay trong truy vấn

Scope orders.read có thể cho phép truy cập collection, nhưng collection vẫn phải chỉ chứa các đơn hàng mà principal được phép thấy. Hãy áp dụng tenant/ownership filter ngay trong truy vấn:

~~~java
import java.util.UUID;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

interface OrderRepository extends JpaRepository<Order, UUID> {

    Page<Order> findAllByTenantId(UUID tenantId, Pageable pageable);

    boolean existsByIdAndTenantId(UUID id, UUID tenantId);

    Optional<Order> findByIdAndTenantId(UUID id, UUID tenantId);
}
~~~

Controller lấy tenant từ principal đã xác thực và gọi truy vấn có giới hạn:

~~~java
import java.util.UUID;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.PagedModel;
import org.springframework.security.core.Authentication;

@GetMapping("/orders")
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
PagedModel<EntityModel<OrderRepresentation>> all(
        Pageable pageable,
        Authentication authentication) {

    UUID tenantId = tenantResolver.tenantId(authentication);
    Page<Order> orders = orderRepository.findAllByTenantId(
        tenantId, pageable);

    return orderAssembler.toModel(orders, authentication);
}
~~~

Ở đây `toModel(Page<Order>, Authentication)` là method collection riêng của assembler: nó chuyển từng phần tử bằng policy có điều kiện rồi tạo `PagedModel` cùng metadata và navigation links. Method này cần được triển khai trong ứng dụng; ví dụ tập trung vào điểm quan trọng là truy vấn đã lọc tenant trước khi phân trang.

Không tải toàn bộ đơn hàng rồi lọc bằng Java sau khi truy vấn. Cách đó có thể làm lộ dữ liệu qua tổng số phần tử, metadata phân trang, log, cache hoặc lỗi trong quá trình lọc. Với pagination, truy vấn cần áp dụng tenant predicate trước khi tính total count và tạo page metadata.

@PostFilter có thể hữu ích với collection nhỏ trong một số trường hợp, nhưng không phù hợp để thay thế truy vấn có điều kiện tenant cho dữ liệu phân trang lớn. Bộ lọc sau khi truy vấn có thể gây sai metadata và tốn bộ nhớ.

## Chỉ công bố link khi scope và trạng thái cho phép

Spring HATEOAS giúp response mô tả các khả năng hiện có. Ví dụ đơn hàng đang PENDING chỉ có link hủy khi người dùng vừa có scope orders.cancel, vừa được phép thao tác trên đơn hàng đó.

Tạo relation riêng cho hành động:

~~~java
import org.springframework.hateoas.LinkRelation;

final class OrderRelations {

    static final LinkRelation CANCEL =
        LinkRelation.of(
            "https://api.example.com/rels/cancel-order");

    private OrderRelations() {
    }
}
~~~

Assembler nhận Authentication và policy để thêm link có điều kiện:

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

record OrderRepresentation(UUID id, String status) {
    static OrderRepresentation from(Order order) {
        return new OrderRepresentation(order.getId(), order.getStatus().name());
    }
}

@Component
class OrderModelAssembler {

    private final OrderAuthorization orderAuthorization;

    OrderModelAssembler(OrderAuthorization orderAuthorization) {
        this.orderAuthorization = orderAuthorization;
    }

    EntityModel<OrderRepresentation> toModel(
            Order order,
            Authentication authentication) {

        EntityModel<OrderRepresentation> model =
            EntityModel.of(OrderRepresentation.from(order));

        model.add(linkTo(
            methodOn(OrderController.class).one(order.getId())
        ).withSelfRel());

        if (orderAuthorization.canCancel(authentication, order.getId())) {
            model.add(linkTo(
                methodOn(OrderWorkflowController.class)
                    .cancel(order.getId())
            ).withRel(OrderRelations.CANCEL));
        }

        return model;
    }
}
~~~

Ví dụ trên dùng cùng policy canCancel cho việc hiển thị link. Trong ứng dụng thực tế, nên tránh truy vấn database lặp lại khi tạo một collection lớn; có thể tải quyền/trạng thái cần thiết trong projection hoặc query phù hợp. Nếu policy phụ thuộc trạng thái thay đổi nhanh, response chỉ phản ánh quyết định tại thời điểm tạo representation.

Khi người dùng không có scope hoặc đơn hàng không ở trạng thái cho phép hủy, relation cancel không được công bố. Client có thể dựa vào sự hiện diện của link để bật nút Hủy. Khi link không có, client nên ẩn hoặc vô hiệu hóa thao tác.

Link HAL cơ bản mang relation và href; nó không tự mô tả đầy đủ HTTP method hoặc schema của request body. Nếu client cần khám phá method POST và các trường đầu vào của thao tác hủy, có thể gắn affordance và serialize bằng HAL-FORMS. Dù dùng HAL hay HAL-FORMS, endpoint vẫn phải thực hiện authorization khi nhận request.

## Endpoint vẫn phải kiểm tra quyền khi request đến

Ẩn link không phải là biện pháp bảo mật. Client có thể lưu URL cũ, tự dựng URI hoặc gọi endpoint trực tiếp. Endpoint hủy phải thực hiện kiểm tra tương tự:

~~~java
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/orders/{id}/cancellation")
@PreAuthorize("@orderAuthorization.canCancel(authentication, #id)")
ResponseEntity<Void> cancel(@P("id") @PathVariable UUID id) {
    orderWorkflowService.cancel(id);
    return ResponseEntity.noContent().build();
}
~~~

Service cần xác nhận lại trạng thái trong transaction trước khi cập nhật để tránh race condition. Ví dụ đơn hàng có thể đã chuyển sang SHIPPED sau khi representation được tạo nhưng trước khi client gọi link cancel. Kiểm tra lúc tạo link chỉ là hướng dẫn điều hướng; kiểm tra lúc thực thi mới quyết định request có được chấp nhận hay không.

Nếu policy trả false, Spring Security thường từ chối request bằng 403 Forbidden đối với principal đã xác thực nhưng thiếu quyền. Với resource không tồn tại hoặc thuộc tenant khác, hệ thống có thể chủ ý trả 404 để không tiết lộ sự tồn tại của resource; lựa chọn này cần nhất quán với chính sách API.

## 401, 403 và link bị ẩn

Ba trạng thái có ý nghĩa khác nhau:

| Tình huống | Hành vi thường thấy |
| --- | --- |
| Không có token hoặc token không hợp lệ | 401 Unauthorized |
| Token hợp lệ nhưng thiếu scope cần thiết | 403 Forbidden |
| Có scope nhưng không có quyền trên resource cụ thể | 403 hoặc 404 theo chính sách bảo vệ thông tin |
| Có quyền đọc nhưng không có scope hủy | GET vẫn thành công; link cancel không xuất hiện |
| Có quyền đọc và hủy, resource đang PENDING | GET thành công; link cancel được công bố |
| Link đã từng được thấy nhưng trạng thái đã đổi | POST bị kiểm tra lại và có thể bị từ chối |

Không trả 401 chỉ vì thiếu scope nếu token đã được xác thực thành công. 401 thường chỉ ra lỗi xác thực; 403 chỉ ra principal đã được nhận diện nhưng không được phép thực hiện thao tác.

## Kiểm thử scope và link bằng MockMvc

Thêm spring-security-test để tạo JWT principal trong MockMvc. Request post processor jwt() cho phép đặt authority như resource server đã ánh xạ:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.MediaTypes;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void exposesCancelLinkWhenPrincipalHasScopeAndOrderIsPending()
        throws Exception {

    mockMvc.perform(get("/orders/{id}", PENDING_ORDER_ID)
            .with(jwt().jwt(jwt -> jwt.claim(
                "tenant_id", CURRENT_TENANT_ID.toString()))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"),
                    new SimpleGrantedAuthority("SCOPE_orders.cancel")))
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/cancel-order'].href")
            .exists());
}
~~~

Request không có token cũng phải bị chặn ở resource server:

~~~java
@Test
void rejectsReadWithoutAuthentication() throws Exception {
    mockMvc.perform(get("/orders/{id}", PENDING_ORDER_ID)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isUnauthorized());
}
~~~

Kiểm tra người dùng chỉ có quyền đọc:

~~~java
@Test
void omitsCancelLinkWhenPrincipalHasOnlyReadScope()
        throws Exception {

    mockMvc.perform(get("/orders/{id}", PENDING_ORDER_ID)
            .with(jwt().jwt(jwt -> jwt.claim(
                "tenant_id", CURRENT_TENANT_ID.toString()))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")))
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/cancel-order']")
            .doesNotExist());
}
~~~

Ngay cả khi principal có cả hai scope, link vẫn phải vắng mặt nếu trạng thái đơn hàng không cho phép hủy:

~~~java
@Test
void omitsCancelLinkForCompletedOrderEvenWithCancelScope()
        throws Exception {

    mockMvc.perform(get("/orders/{id}", COMPLETED_ORDER_ID)
            .with(jwt().jwt(jwt -> jwt.claim(
                "tenant_id", CURRENT_TENANT_ID.toString()))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"),
                    new SimpleGrantedAuthority("SCOPE_orders.cancel")))
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$._links['https://api.example.com/rels/cancel-order']")
            .doesNotExist());
}
~~~

Và kiểm tra endpoint không thể bị gọi trực tiếp nếu thiếu scope hủy:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void rejectsDirectCancellationWithoutCancelScope() throws Exception {
    mockMvc.perform(post(
            "/orders/{id}/cancellation", PENDING_ORDER_ID)
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isForbidden());
}
~~~

Các test giả định fixture PENDING_ORDER_ID thuộc tenant của principal và service/policy được cấu hình trong test context. Request post processor jwt() tạo principal test; nó không kiểm tra chữ ký JWT thật. Cần có integration test riêng cho decoder/issuer, claim mapping và cấu hình audience của resource server.

Nếu ứng dụng dùng CSRF protection với session hoặc cookie authentication, POST test cần token CSRF hợp lệ. Với API stateless chỉ xác thực bằng bearer token trong Authorization header, cấu hình CSRF phải phù hợp với mô hình xác thực; không tắt CSRF một cách máy móc cho ứng dụng có cookie session.

## Kiểm thử tenant isolation

Kiểm thử scope không đủ nếu dữ liệu còn được phân vùng theo tenant. Hãy xác nhận principal có scope đọc nhưng không thể truy cập resource của tenant khác:

~~~java
@Test
void doesNotExposeAnotherTenantsOrder() throws Exception {
    mockMvc.perform(get("/orders/{id}", OTHER_TENANT_ORDER_ID)
            .with(jwt().jwt(jwt -> jwt.claim(
                "tenant_id", CURRENT_TENANT_ID.toString()))
                .authorities(new SimpleGrantedAuthority("SCOPE_orders.read")))
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isNotFound());
}
~~~

Test dùng 404 theo chính sách che giấu resource. Nếu API công khai lựa chọn 403, hãy xác nhận 403 nhất quán. Quan trọng là response không chứa representation, embedded data hoặc link tới resource ngoài tenant.

## Khi dùng Spring Data REST

Nếu repository được export trực tiếp bằng Spring Data REST, scope matcher ở URL có thể bảo vệ cả nhóm endpoint, nhưng vẫn cần kiểm tra method exposure và quyền theo bản ghi. Có thể dùng method security trên repository method, query theo tenant hoặc custom controller/service để áp dụng policy.

Không export một repository nhạy cảm chỉ vì endpoint đã yêu cầu SCOPE_orders.read. Scope đó không tự lọc kết quả findAll() theo tenant. Nếu không thể bảo đảm mọi đường truy cập repository đều áp dụng cùng điều kiện, hãy giới hạn export hoặc thay bằng endpoint có authorization rõ ràng.

RepresentationModelProcessor có thể bổ sung link cho representation Spring Data REST, nhưng processor chỉ điều khiển discoverability. Endpoint repository và custom action vẫn cần kiểm tra quyền ở request time.

## Những lỗi thường gặp

- **Nhầm scope với tenant permission:** orders.read không cho phép đọc mọi đơn hàng.
- **Kiểm tra scope bằng chuỗi sai prefix:** Spring Security thường ánh xạ thành SCOPE_orders.read.
- **Tin claim từ token chưa xác minh:** resource server phải xác minh chữ ký, issuer, expiry và audience.
- **Chỉ ẩn link:** endpoint vẫn có thể bị gọi trực tiếp; luôn bảo vệ request.
- **Chỉ bảo vệ item endpoint:** collection có thể làm lộ dữ liệu tenant khác hoặc metadata tổng số.
- **Lọc sau khi phân trang:** tổng số phần tử và page metadata có thể tiết lộ dữ liệu.
- **Dùng @PostFilter cho tập dữ liệu lớn:** gây truy vấn dư thừa và sai metadata phân trang.
- **Chỉ kiểm tra quyền lúc tạo link:** trạng thái có thể đổi trước khi hành động được thực thi.
- **Đưa scope vào tên relation:** relation mô tả ngữ nghĩa link, còn scope quyết định quyền; không tạo relation khác nhau chỉ để thay thế authorization.
- **Đồng nhất 401 và 403:** xác thực thất bại khác với principal đã xác thực nhưng thiếu quyền.

Scope-based resource kết hợp ba lớp: xác thực token và ánh xạ scope thành authority, authorization theo resource/tenant/trạng thái, và công bố link phù hợp qua Spring HATEOAS. Scope bảo vệ nhóm chức năng API; policy bảo vệ từng resource; link giúp client khám phá hành động có thể thực hiện. Chỉ endpoint/service mới thực thi quyết định bảo mật cuối cùng khi request đến.

## Tài liệu tham khảo

- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring HATEOAS – Reference Documentation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [RFC 6749 – The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
- [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
