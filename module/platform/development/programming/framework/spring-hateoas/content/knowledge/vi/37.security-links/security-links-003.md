# Link cho anonymous user

Một REST API có thể cho phép người chưa đăng nhập khám phá một phần tài nguyên, đọc tài liệu công khai hoặc tìm hiểu cách xác thực. Representation dành cho anonymous user vì vậy vẫn có thể chứa hypermedia link. Tuy nhiên, các thao tác yêu cầu danh tính hoặc quyền cụ thể chỉ nên được công bố khi caller đáp ứng điều kiện tương ứng.

Spring HATEOAS giúp xây dựng representation có link theo ngữ cảnh caller; Spring Security cung cấp thông tin xác thực và cơ chế kiểm soát truy cập. Hai phần này cần phối hợp: link phản ánh những khả năng API muốn client khám phá, còn security filter và service vẫn thực thi quyền ở mỗi request. Việc ẩn một link không thay thế authorization ở server.

## 1. Anonymous user trong Spring Security

Anonymous user là caller chưa được xác thực nhưng vẫn được phép truy cập một số endpoint công khai. Khi bật anonymous authentication, Spring Security thường đặt một `AnonymousAuthenticationToken` vào `SecurityContext`, thay vì để `Authentication` luôn là `null`.

Một chi tiết dễ gây lỗi là `AnonymousAuthenticationToken.isAuthenticated()` có thể trả về `true`. Vì vậy, không thể chỉ gọi `authentication.isAuthenticated()` để kết luận người dùng đã đăng nhập. Dùng `AuthenticationTrustResolver` để phân biệt anonymous, remember-me và fully authenticated:

```java
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
class AuthenticationState {

    private final AuthenticationTrustResolver trustResolver =
            new AuthenticationTrustResolverImpl();

    boolean isAnonymous(Authentication authentication) {
        return authentication == null || trustResolver.isAnonymous(authentication);
    }

    boolean isFullyAuthenticated(Authentication authentication) {
        return authentication != null
                && trustResolver.isFullyAuthenticated(authentication);
    }
}
```

`isAnonymous(...)` nhận diện cả trường hợp không có authentication và anonymous token. `isFullyAuthenticated(...)` hữu ích khi thao tác nhạy cảm không chấp nhận remember-me authentication. Chọn mức xác thực theo yêu cầu nghiệp vụ thay vì coi mọi trạng thái khác anonymous là tương đương.

## 2. API root vẫn có thể phục vụ anonymous user

Một API root công khai có thể trả về thông tin dịch vụ, link tài liệu và link mô tả cách xác thực. Client chưa đăng nhập vẫn khám phá được entry point mà không cần biết trước route nội bộ.

Với relation riêng của API, nên dùng extension relation URI ổn định. Ví dụ vocabulary:

```java
import org.springframework.hateoas.LinkRelation;

public final class SecurityRelations {

    public static final LinkRelation AUTHENTICATION =
            LinkRelation.of("https://api.example.test/rels/authentication");

    public static final LinkRelation REGISTRATION =
            LinkRelation.of("https://api.example.test/rels/registration");

    public static final LinkRelation CANCEL =
            LinkRelation.of("https://api.example.test/rels/cancel");

    private SecurityRelations() {
    }
}
```

Vì các relation trên là extension relation URI, HAL nên công bố chúng qua CURIE. Cấu hình namespace một lần:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.UriTemplate;
import org.springframework.hateoas.mediatype.hal.CurieProvider;
import org.springframework.hateoas.mediatype.hal.DefaultCurieProvider;

@Configuration
class HalRelationConfiguration {

    @Bean
    CurieProvider curieProvider() {
        return new DefaultCurieProvider(
                "acme",
                UriTemplate.of("https://api.example.test/rels/{rel}"));
    }
}
```

Với cấu hình này, HAL serialize các relation trên thành `acme:authentication`, `acme:registration` và `acme:cancel`. Client có thể mở rộng prefix `acme` qua link `curies` để lấy URI relation đầy đủ.

Relation `authentication` chỉ đến tài nguyên mô tả cách xác thực. Resource đó có thể công bố các cơ chế được hỗ trợ, URI của authorization server hoặc hướng dẫn cho client. Nó không nhất thiết là form đăng nhập HTML và cũng không nên chứa username, password hay access token.

Controller API root:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiRootController {

    private final AuthenticationState authenticationState;

    ApiRootController(AuthenticationState authenticationState) {
        this.authenticationState = authenticationState;
    }

    @GetMapping(value = "/api", produces = "application/hal+json")
    EntityModel<ApiRootRepresentation> root() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        EntityModel<ApiRootRepresentation> model = EntityModel.of(
                new ApiRootRepresentation("Order API"),
                Link.of("/auth", SecurityRelations.AUTHENTICATION));

        if (authenticationState.isAnonymous(authentication)) {
            model.add(Link.of("/register", SecurityRelations.REGISTRATION));
        }

        return model;
    }
}
```

DTO dùng trong ví dụ:

```java
public record ApiRootRepresentation(String name) {
}
```

API root được phép truy cập công khai, luôn có link mô tả authentication và chỉ công bố registration khi chính sách cho phép đăng ký mở. Controller lấy authentication hiện tại từ `SecurityContextHolder`, không đưa nó vào chữ ký handler để tránh coi thông tin bảo mật là một tham số URL khi xây dựng link.

Đường dẫn `/auth` cần trỏ đến endpoint hoặc tài liệu xác thực thật sự của ứng dụng. Với OAuth 2.0/OIDC, resource này có thể dẫn client đến authorization server hoặc metadata discovery. Với browser form login, link có thể dẫn đến trang login. Với machine-to-machine bearer token, client thường lấy token qua cơ chế cấp token đã thỏa thuận ngoài resource API. Hãy mô tả đúng flow mà hệ thống hỗ trợ.

## 3. Cấu hình security cho endpoint công khai và endpoint bảo vệ

Spring Security quyết định endpoint nào anonymous user được truy cập. Ví dụ cấu hình API stateless:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api", "/api/**", "/auth", "/register", "/orders/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api", "/auth", "/register", "/orders/**").permitAll()
                        .requestMatchers(HttpMethod.POST, "/register").permitAll()
                        .requestMatchers("/orders/**").authenticated()
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Đây là ví dụ API dùng HTTP Basic để minh họa xác thực stateless; production có thể dùng OAuth 2.0 Resource Server với bearer token. HTTP Basic vẫn có thể được browser tự động gửi kèm request, vì vậy không nên suy luận rằng stateless đồng nghĩa với không có rủi ro CSRF. Ví dụ giữ CSRF protection mặc định. `permitAll()` chỉ cho phép request đến endpoint công khai; nó không tự quyết định representation nào nên trả về hoặc link nào nên xuất hiện.

Nếu ứng dụng dùng cookie/session authentication, cần xem xét CSRF protection cho các request thay đổi trạng thái. Không tắt CSRF chỉ vì endpoint có dạng REST. Với bearer token stateless được gửi qua `Authorization` header và không tự động gắn bởi browser, chính sách CSRF có thể khác; hãy cấu hình theo cơ chế credential thực tế.

## 4. Chỉ công bố link hành động khi caller được phép

Giả sử anonymous user có thể xem một bản tóm tắt công khai của đơn hàng, nhưng chỉ người dùng được phép mới có thể hủy đơn. Một policy dùng chung có thể quyết định khả năng hủy:

```java
import java.util.UUID;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

enum OrderStatus {
    PENDING, PAID, SHIPPED, CANCELLED
}

record Order(UUID id, String ownerUsername, OrderStatus status) {
}

record OrderRepresentation(UUID id, String status) {

    static OrderRepresentation from(Order order) {
        return new OrderRepresentation(order.id(), order.status().name());
    }
}

record CancelOrderRequest(String reason) {
}

@Component
class OrderAccessPolicy {

    private final AuthenticationTrustResolver trustResolver =
            new AuthenticationTrustResolverImpl();

    boolean canCancel(Authentication authentication, Order order) {
        if (authentication == null || trustResolver.isAnonymous(authentication)) {
            return false;
        }

        boolean hasAuthority = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        authority.getAuthority().equals("ORDER_CANCEL"));

        boolean ownsOrder = order.ownerUsername().equals(authentication.getName());

        return hasAuthority
                && ownsOrder
                && order.status() == OrderStatus.PENDING;
    }
}
```

Policy kiểm tra bốn điều kiện: caller đã xác thực, có authority `ORDER_CANCEL`, là chủ sở hữu đơn hàng và đơn hàng còn ở trạng thái `PENDING`. Hệ thống thực tế có thể có quyền của nhân viên hỗ trợ hoặc quy tắc phân quyền theo tenant; hãy đặt các quy tắc đó trong policy nghiệp vụ có thể tái sử dụng.

Assembler dùng cùng policy để tạo representation:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.stereotype.Component;
import org.springframework.security.core.Authentication;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    private final OrderAccessPolicy accessPolicy;

    OrderModelAssembler(OrderAccessPolicy accessPolicy) {
        this.accessPolicy = accessPolicy;
    }

    EntityModel<OrderRepresentation> toModel(
            Order order, Authentication authentication) {
        EntityModel<OrderRepresentation> model = EntityModel.of(
                OrderRepresentation.from(order),
                linkTo(methodOn(OrderController.class)
                        .one(order.id())).withSelfRel());

        if (accessPolicy.canCancel(authentication, order)) {
            model.add(linkTo(methodOn(OrderCommandController.class)
                    .cancel(order.id(), null))
                    .withRel(SecurityRelations.CANCEL)
                    .andAffordance(afford(methodOn(OrderCommandController.class)
                            .cancel(order.id(), null))));
        }

        return model;
    }
}
```

Khi anonymous user đọc được public summary, representation chỉ có link `self` và các link công khai. Khi chủ sở hữu đã xác thực và có authority phù hợp, representation có thêm `cancel` cùng affordance của command. Việc dùng chung `OrderAccessPolicy` giúp logic tạo link và logic thực thi hành động nhất quán hơn.

Client nhận `application/hal+json` sẽ thấy link; client nhận `application/prs.hal-forms+json` có thể đọc thêm metadata của affordance. Hãy thương lượng HAL-FORMS khi client cần biết method và input của thao tác `POST`.

`Order`, `OrderStatus`, `OrderRepresentation.from(...)`, `OrderController` và `OrderCommandController` là các kiểu domain/ứng dụng giả định. Ví dụ tập trung vào cách truyền `Authentication` vào assembler và áp dụng policy; thay bằng model thật của ứng dụng.

Service contract tối thiểu cho các ví dụ:

```java
import java.util.UUID;

import org.springframework.security.core.Authentication;

interface OrderService {
    Order getReadable(UUID id, Authentication authentication);

    Order cancelIfAllowed(
            UUID id, CancelOrderRequest request, Authentication authentication);
}
```

Controller đọc resource có thể lấy authentication từ `SecurityContextHolder` rồi truyền cả hai vào service và assembler:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @GetMapping(value = "/orders/{id}", produces = {
            "application/hal+json", "application/prs.hal-forms+json"})
    EntityModel<OrderRepresentation> one(@PathVariable UUID id) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        Order order = orderService.getReadable(id, authentication);
        return assembler.toModel(order, authentication);
    }
}
```

## 5. Không để link làm lộ sự tồn tại của resource

Ẩn link hành động không đủ nếu chính representation đã tiết lộ dữ liệu nhạy cảm. Trước khi tạo `EntityModel`, service phải quyết định caller có quyền đọc resource hay chỉ được xem public projection.

Một cách tách rõ là có hai truy vấn hoặc projection:

- `findPublicSummary(id)` chỉ trả các field được phép công khai cho mọi người.
- `findVisibleTo(id, authentication)` kiểm tra quyền và trả representation chi tiết cho caller được phép.

Nếu API không muốn tiết lộ một resource riêng tư có tồn tại hay không, có thể trả `404 Not Found` cho cả trường hợp không tồn tại và không được phép xem, theo chính sách bảo mật nhất quán. Nếu resource được công khai nhưng một hành động bị cấm, `403 Forbidden` có thể phù hợp hơn.

Không tạo representation đầy đủ rồi chỉ xóa link nhạy cảm ở cuối. Dữ liệu trong body, embedded resource, error message và metadata cũng phải tuân theo chính sách truy cập.

## 6. Link authentication không phải token hay quyền truy cập

Một link `authentication` chỉ giúp client khám phá nơi hoặc cách xác thực. Nó không cấp quyền, không chứng minh danh tính và không nên mang credential trong query string.

Không thiết kế link dạng:

```text
/login?username=alice&password=secret
```

URL có thể bị ghi vào browser history, access log, proxy log, analytics và referrer. Gửi credential qua cơ chế xác thực phù hợp, ví dụ OAuth 2.0/OIDC authorization flow hoặc `Authorization` header theo hợp đồng API.

Không đưa access token vào `href`, URI template hoặc relation metadata. Nếu response có link đến authorization server, client vẫn phải thực hiện flow và kiểm tra issuer, audience, redirect URI, state/nonce theo giao thức tương ứng.

## 7. Anonymous, remember-me và fully authenticated

Không phải mọi authentication không anonymous đều có cùng mức tin cậy. Spring Security có thể phân biệt:

| Trạng thái | Ý nghĩa | Ví dụ chính sách |
| --- | --- | --- |
| Anonymous | Chưa xác thực danh tính | Chỉ public resource và authentication discovery |
| Remember-me | Đăng nhập được khôi phục bằng remember-me token | Cho phép đọc thông thường, yêu cầu xác thực mạnh hơn cho thao tác nhạy cảm |
| Fully authenticated | Caller đã xác thực đầy đủ theo cơ chế hiện tại | Có thể đủ điều kiện cho thao tác cần đăng nhập đầy đủ, nếu authority và domain policy cũng cho phép |

`AuthenticationTrustResolver.isFullyAuthenticated(...)` trả về false cho anonymous và remember-me authentication. Tuy nhiên, fully authenticated không tự đồng nghĩa với có quyền nghiệp vụ. Vẫn phải kiểm tra authority, ownership, tenant và trạng thái resource.

Ví dụ, một thao tác thay đổi địa chỉ thanh toán có thể yêu cầu fully authenticated; còn đọc thông tin đơn hàng có thể chấp nhận remember-me. Đừng dùng một điều kiện đăng nhập chung cho mọi hành động.

## 8. Bảo vệ command endpoint độc lập với link

Command endpoint phải tự kiểm tra authorization. Có thể dùng method security cho authority tổng quát và kiểm tra điều kiện resource trong service:

```java
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.http.MediaType;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderCommandController {

    private final OrderService orderService;
    private final OrderModelAssembler assembler;

    OrderCommandController(OrderService orderService, OrderModelAssembler assembler) {
        this.orderService = orderService;
        this.assembler = assembler;
    }

    @PreAuthorize("hasAuthority('ORDER_CANCEL')")
    @PostMapping(value = "/orders/{id}/cancellations",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = {"application/hal+json", "application/prs.hal-forms+json"})
    EntityModel<OrderRepresentation> cancel(
            @PathVariable UUID id,
            @RequestBody CancelOrderRequest request) {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        Order updated = orderService.cancelIfAllowed(id, request, authentication);
        return assembler.toModel(updated, authentication);
    }
}
```

`@EnableMethodSecurity` đã được bật trong cấu hình ở phần trước. `OrderService.cancelIfAllowed(...)` nên dùng lại `OrderAccessPolicy.canCancel(...)` để kiểm tra authority, chủ sở hữu và trạng thái; đồng thời kiểm tra điều kiện đồng thời trước khi ghi dữ liệu. Nếu client đã nhận link `cancel` nhưng trạng thái thay đổi trước khi gửi request, endpoint phải từ chối thao tác theo trạng thái mới.

Không coi URL là capability token. Bất kỳ ai cũng có thể sao chép một `href`; server phải xác thực và phân quyền lại ở mỗi request.

## 9. Cache representation phụ thuộc caller

Nếu representation của anonymous user khác representation của người đã đăng nhập, response có thể chứa link khác nhau theo caller. Shared cache không được trả representation của người này cho người khác.

Với representation cá nhân hóa, cân nhắc:

```http
Cache-Control: private
Vary: Authorization, Cookie
```

`private` ngăn shared cache lưu response như một representation dùng chung; `Vary` giúp cache phân biệt request theo các header liên quan khi chính sách cache cho phép. Với dữ liệu nhạy cảm, có thể dùng `Cache-Control: no-store`. `Vary` không thay thế authorization và không biến response riêng tư thành an toàn để cache công khai.

Representation công khai, giống nhau cho mọi caller, có thể có cache policy riêng. Không đánh dấu response chứa link cá nhân hóa là `public` chỉ vì body DTO không có dữ liệu nhạy cảm; chính link cũng tiết lộ khả năng và ngữ cảnh quyền của caller.

## 10. Kiểm thử anonymous và authenticated user

Spring Security Test cung cấp `@WithAnonymousUser` và `@WithMockUser` để đặt security context cho MockMvc test. Ví dụ kiểm tra API root công khai:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.security.core.Authentication;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.http.MediaType;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AnonymousLinksTest {

    private static final UUID ORDER_ID =
            UUID.fromString("a6a1f2b4-1f0d-4a7c-8e12-123456789abc");
    private static final Order PENDING_ORDER =
            new Order(ORDER_ID, "alice", OrderStatus.PENDING);

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;

    @Test
    @WithAnonymousUser
    void anonymousCanDiscoverAuthentication() throws Exception {
        mockMvc.perform(get("/api").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$._links['acme:authentication'].href")
                        .exists())
                .andExpect(jsonPath(
                        "$._links['acme:registration'].href")
                        .exists());
    }
}
```

JSONPath ở trên kiểm tra tên relation đã được rút gọn bằng CURIE prefix `acme` theo cấu hình ở phần trước.

Kiểm tra link hành động chỉ xuất hiện với user có quyền:

Thêm hai method sau vào `AnonymousLinksTest` ở phần trước:

```java
@Test
@WithAnonymousUser
void anonymousDoesNotReceiveCancelLink() throws Exception {
    given(orderService.getReadable(eq(ORDER_ID), any(Authentication.class)))
            .willReturn(PENDING_ORDER);

    mockMvc.perform(get("/orders/{id}", ORDER_ID)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links['acme:cancel']").doesNotExist());
}

@Test
@WithMockUser(username = "alice", authorities = "ORDER_CANCEL")
void authorizedOwnerReceivesCancelLink() throws Exception {
    given(orderService.getReadable(eq(ORDER_ID), any(Authentication.class)))
            .willReturn(PENDING_ORDER);

    mockMvc.perform(get("/orders/{id}", ORDER_ID)
                    .accept(MediaTypes.HAL_FORMS_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links['acme:cancel'].href").exists())
            .andExpect(jsonPath("$._templates").exists());
}
```

Hai test giả định `ORDER_ID` thuộc sở hữu của `alice`, service trả đơn hàng `PENDING` và endpoint cho phép anonymous đọc public summary. Nếu API không công khai resource đó, test anonymous phải mong đợi `401` hoặc `404` theo chính sách, thay vì mong đợi một representation.

`@MockitoBean` có từ Spring Framework 6.2. Với phiên bản Spring Boot/Spring Framework cũ hơn, thay bằng `@MockBean` nếu dự án đang sử dụng annotation đó.

## 11. Kiểm thử endpoint vẫn từ chối request trái phép

Ẩn link chỉ là một phần của contract. Cần test trực tiếp command endpoint để bảo đảm anonymous user không thể thực hiện hành động bằng cách tự tạo URL:

```java
@Test
@WithAnonymousUser
void anonymousCannotCancelOrderDirectly() throws Exception {
    mockMvc.perform(post("/orders/{id}/cancellations", ORDER_ID)
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"reason\":\"Requested by caller\"}"))
            .andExpect(status().isUnauthorized());
}
```

Status code phụ thuộc `AuthenticationEntryPoint` và cấu hình security. REST API stateless thường trả `401 Unauthorized`; form-login application có thể redirect đến trang đăng nhập (`302`). Hãy kiểm tra response đúng với hợp đồng API đang triển khai.

User đã xác thực nhưng thiếu authority thường nhận `403 Forbidden`:

```java
@Test
@WithMockUser(username = "alice", authorities = "ORDER_READ")
void authenticatedUserWithoutCancelAuthorityIsForbidden() throws Exception {
    mockMvc.perform(post("/orders/{id}/cancellations", ORDER_ID)
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"reason\":\"Requested by caller\"}"))
            .andExpect(status().isForbidden());
}
```

Nếu CSRF được bật và request dùng cookie/session authentication, thêm `.with(csrf())` cho test POST hợp lệ hoặc test quyền tương ứng. Một request thiếu CSRF token có thể bị từ chối trước khi đi đến authorization logic. Với API bearer token stateless, cấu hình CSRF theo đúng threat model của ứng dụng.

## 12. Anonymous link và content negotiation

API root có thể công khai HAL cho anonymous user, nhưng trang login HTML và representation API có thể dùng media type khác nhau. Không giả định mọi link xác thực đều dẫn đến một response HAL.

- Link tới authentication metadata có thể trả `application/hal+json`.
- Trang đăng nhập cho browser có thể trả `text/html`.
- OAuth2 authorization endpoint thường thực hiện redirect theo giao thức.
- Token endpoint nhận request theo hợp đồng OAuth2, không phải form tùy ý của resource API.

Client nên đọc relation và theo link với `Accept` phù hợp cho tài nguyên đích. Nếu link dẫn đến một origin hoặc media type khác, client cần áp dụng quy tắc giao thức tương ứng.

## 13. Lỗi thường gặp

**Dùng `isAuthenticated()` để nhận diện user đã đăng nhập:** anonymous token cũng có thể trả true. Dùng `AuthenticationTrustResolver`.

**Công bố mọi action cho anonymous user:** client nhìn thấy khả năng không được phép. Dùng policy để tạo link theo caller và trạng thái domain.

**Tin rằng ẩn link là đủ bảo mật:** client có thể gọi URL trực tiếp. Bảo vệ endpoint và service bằng authorization thực sự.

**Đưa password hoặc token vào query string:** URL có thể bị lưu trong log và history. Dùng giao thức xác thực và header phù hợp.

**Trả toàn bộ resource rồi chỉ bỏ link nhạy cảm:** body hoặc embedded resource vẫn có thể làm lộ dữ liệu. Tạo public projection riêng và kiểm tra quyền đọc trước khi serialize.

**Dùng relation không có semantics rõ ràng:** client khó khám phá authentication flow. Dùng relation được tài liệu hóa và URI ổn định cho custom relation.

**Cache chung representation cá nhân hóa:** link của một user có thể bị trả cho caller khác. Dùng private/no-store và cấu hình cache variation phù hợp.

**Chỉ test representation mà không test command endpoint:** link bị ẩn nhưng server vẫn có thể cho phép request trái phép. Test cả link lẫn request trực tiếp.

## 14. Checklist thiết kế link cho anonymous user

- Xác định endpoint nào thực sự công khai.
- Phân biệt anonymous, remember-me và fully authenticated.
- Dùng `AuthenticationTrustResolver`, không chỉ dựa vào `isAuthenticated()`.
- Công bố link authentication hoặc registration có ý nghĩa và đích hợp lệ.
- Không đưa credential vào `href` hoặc query parameter.
- Tạo public projection riêng khi anonymous chỉ được xem một phần dữ liệu.
- Chỉ thêm action link khi caller có quyền và trạng thái domain cho phép.
- Dùng cùng policy giữa link assembler và service authorization.
- Bảo vệ command endpoint kể cả khi link không được công bố.
- Kiểm thử anonymous, user có quyền và user thiếu quyền.
- Kiểm thử response status theo AuthenticationEntryPoint thực tế.
- Bảo vệ representation cá nhân hóa khỏi shared cache.
- Kiểm tra content negotiation của authentication resource và API resource.

Link cho anonymous user giúp API vẫn có thể khám phá được từ điểm bắt đầu công khai, đồng thời biểu diễn đúng những khả năng mà caller hiện tại được phép thấy. Khi Spring HATEOAS tạo link theo `Authentication` và policy domain, còn Spring Security bảo vệ mọi endpoint độc lập, client có thể điều hướng phù hợp mà không biến hypermedia thành một lỗ hổng phân quyền.

## Tài liệu tham khảo

- [Spring Security Reference – Anonymous Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/anonymous.html)
- [Spring Security Reference – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Security Reference – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring HATEOAS Reference – Representation models and links](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
