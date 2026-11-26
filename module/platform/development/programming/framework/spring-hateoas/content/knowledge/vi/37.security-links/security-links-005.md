# Role-based affordance

Một resource HATEOAS có thể công bố những link và thao tác khác nhau tùy theo người dùng đang đăng nhập, quyền được cấp và trạng thái nghiệp vụ của resource. Ví dụ, nhân viên xử lý đơn hàng có thể thấy link `cancel`, quản lý có thể thấy `approve`, còn người chỉ có quyền đọc chỉ thấy `self` và `customer`. Đây là **role-based affordance**: representation phản ánh những khả năng mà server sẵn sàng công bố cho principal hiện tại.

Spring HATEOAS cho phép thêm link và affordance có điều kiện khi xây representation. Spring Security cung cấp `Authentication`, authorities, roles và method security để bảo vệ endpoint thực thi thao tác. Hai phần cần dùng cùng một chính sách nghiệp vụ: representation chỉ công bố affordance khi phù hợp, còn server vẫn phải xác thực và phân quyền lại ở request thực tế.

Bài học này thuộc chương **Security links** trong module **SPRING_HATEOAS**, tập trung vào cách công bố link theo role/authority, ownership và trạng thái domain; tích hợp `Authentication`, `@PreAuthorize` và Spring HATEOAS affordance; xử lý cache theo người dùng; và kiểm thử cả link visibility lẫn endpoint authorization.

Sau bài học, bạn có thể:

- Phân biệt role, authority và quyền trên từng resource.
- Công bố link và affordance có điều kiện theo `Authentication`.
- Dùng `@EnableMethodSecurity` và `@PreAuthorize` để bảo vệ action endpoint.
- Kết hợp quyền với ownership, tenant và trạng thái nghiệp vụ.
- Dùng cùng policy khi tạo representation và thực thi thao tác.
- Hiểu khác biệt giữa link HAL và affordance được biểu diễn bằng HAL-FORMS.
- Tránh xem việc ẩn link là cơ chế bảo mật.
- Cấu hình cache phù hợp khi representation thay đổi theo người dùng.
- Kiểm thử quyền bằng MockMvc, `@WithMockUser` và Spring Security Test.

## 1. Role-based affordance là gì?

Affordance mô tả một hành động có thể thực hiện liên quan tới resource. Khi quyền của người dùng khác nhau, các hành động được công bố cũng có thể khác nhau.

Ví dụ cùng một đơn hàng ở trạng thái `PENDING`:

| Người dùng | Quyền | Link/affordance có thể được công bố |
|---|---|---|
| Chủ đơn hàng | `ORDER_READ`, `ORDER_CANCEL` | `self`, `customer`, `cancel` |
| Nhân viên chỉ đọc | `ORDER_READ` | `self`, `customer` |
| Quản lý | `ORDER_READ`, `ROLE_ADMIN` | `self`, `customer`, `cancel`, `approve` |
| Người chưa đăng nhập | Không có principal hợp lệ | Tùy chính sách đọc công khai; không có action cần đăng nhập. |

Server có thể chọn không đưa relation `cancel` vào representation nếu người dùng không đủ điều kiện. Client từ đó không hiển thị nút hủy hoặc không đề xuất thao tác đó.

Việc công bố affordance là một phần của trải nghiệm hypermedia. Nó không thay thế kiểm tra bảo mật ở endpoint. Client có thể tự tạo request hoặc gọi URI đã biết từ nơi khác; server phải từ chối request không được phép ngay cả khi link không xuất hiện.

## 2. Role, authority và quyền trên resource

Spring Security dùng `GrantedAuthority` để biểu diễn quyền mà một `Authentication` sở hữu. Role thường là một quy ước đặt tên trên authority, còn authority có thể mô tả một quyền cụ thể.

| Khái niệm | Ví dụ | Cách kiểm tra |
|---|---|---|
| Role | `ROLE_ADMIN`, `ROLE_OPERATOR` | `hasRole("ADMIN")`, `hasRole("OPERATOR")` |
| Authority | `ORDER_READ`, `ORDER_CANCEL`, `ORDER_APPROVE` | `hasAuthority("ORDER_CANCEL")` |
| Quyền theo resource | Người dùng được hủy đơn hàng `42` vì là chủ đơn | Policy kiểm tra principal, entity, tenant và trạng thái. |

`hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN` do role prefix `ROLE_`. Không truyền `ROLE_ADMIN` vào `hasRole` nếu không thay đổi role prefix. `hasAuthority("ROLE_ADMIN")` so sánh chính xác chuỗi authority.

Một role như `ADMIN` có thể đại diện cho nhóm quyền lớn; authority như `ORDER_CANCEL` diễn tả một thao tác cụ thể. Ứng dụng nên chọn cách đặt tên nhất quán và tránh trộn lẫn hai quy ước trong cùng một policy.

Quyền trên resource thường cần nhiều hơn role. Một người có authority `ORDER_CANCEL` vẫn có thể chỉ được hủy đơn hàng do mình tạo. Policy thực tế có thể kết hợp:

- Authority hoặc role của principal.
- Owner hoặc người được ủy quyền trên resource.
- Tenant/organization sở hữu resource.
- Trạng thái hiện tại của resource.
- Quy tắc nghiệp vụ như thời hạn hủy hoặc trạng thái thanh toán.

## 3. Bật method security

Spring Security method security cho phép bảo vệ method bằng annotation như `@PreAuthorize`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
```

`@EnableMethodSecurity` bật các interceptor method security. Nếu ứng dụng đã bật method security trong một cấu hình khác, không cần khai báo lặp lại.

Ví dụ endpoint hủy đơn hàng chỉ cho phép principal có authority `ORDER_CANCEL` hoặc role `ADMIN` đi vào method:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping("/{id}/cancellation")
@PreAuthorize("hasAuthority('ORDER_CANCEL') or hasRole('ADMIN')")
OrderResponse cancel(
        @PathVariable Long id,
        @RequestBody CancelOrderRequest request) {
    // Gọi service để kiểm tra policy trên đơn hàng và thực hiện hủy.
}
```

Method security bảo vệ đường gọi method qua Spring proxy. Request-level authorization trong `SecurityFilterChain` vẫn cần được cấu hình phù hợp để quyết định endpoint nào public, endpoint nào cần đăng nhập và cách trả về `401`/`403`.

## 4. Lấy Authentication trong request

Trong controller MVC, Spring Security lưu `Authentication` hiện tại trong `SecurityContext`. Có thể nhận nó như một method argument:

```java
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/{id}")
EntityModel<OrderResponse> one(
        @PathVariable Long id,
        Authentication authentication) {

    Order order = orderService.findById(id);
    return orderModelAssembler.toModel(order, authentication);
}
```

Spring MVC có thể resolve `Authentication` từ security context của request. Cách này giúp truyền principal một cách tường minh tới assembler hoặc policy.

Không nên lưu `Authentication` vào field của singleton assembler hoặc service. Mỗi request có principal riêng; giữ authentication trong field có thể làm rò rỉ trạng thái giữa người dùng. Truyền authentication qua tham số method hoặc đọc từ `SecurityContextHolder` trong đúng request scope.

Với code chạy ngoài request thread, không giả định `SecurityContextHolder` luôn có principal. Background job nên nhận một định danh actor hoặc service identity tường minh, cùng chính sách ủy quyền phù hợp.

## 5. Viết policy kết hợp authority, ownership và trạng thái

Không nên lặp điều kiện quyền trong nhiều controller và assembler. Tạo một policy service để xác định người dùng có thể thực hiện hành động trên resource hay không:

```java
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.stereotype.Component;

import java.util.Set;
import java.util.stream.Collectors;

@Component
class OrderAccessPolicy {

    boolean canCancel(Authentication authentication, Order order) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        Set<String> authorities = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

        boolean administrator = authorities.contains("ROLE_ADMIN");
        boolean hasCancelAuthority = authorities.contains("ORDER_CANCEL");
        boolean isOwner = order.getOwnerUsername().equals(authentication.getName());
        boolean canManageOrder = administrator || (hasCancelAuthority && isOwner);

        return order.getStatus() == OrderStatus.PENDING && canManageOrder;
    }
}
```

Policy này chỉ cho phép hủy khi đơn hàng `PENDING`, đồng thời người dùng là quản trị viên hoặc có authority `ORDER_CANCEL` và là chủ đơn. `AnonymousAuthenticationToken` được loại trừ rõ ràng vì anonymous authentication có thể báo `isAuthenticated() == true`.

Trong hệ thống multi-tenant, policy cần kiểm tra tenant của principal trùng tenant của đơn hàng. Không dựa vào `ownerUsername` nếu định danh người dùng có thể đổi; nên dùng immutable user ID hoặc subject claim ổn định.

## 6. Công bố link có điều kiện trong assembler

Assembler tạo representation và chỉ thêm link `cancel` khi policy cho phép:

```java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    private final OrderAccessPolicy accessPolicy;

    OrderModelAssembler(OrderAccessPolicy accessPolicy) {
        this.accessPolicy = accessPolicy;
    }

    EntityModel<OrderResponse> toModel(
            Order order,
            Authentication authentication) {

        Link self = linkTo(methodOn(OrderController.class)
                .one(order.getId(), null)).withSelfRel();

        EntityModel<OrderResponse> model = EntityModel.of(
                OrderResponse.from(order), self);

        if (accessPolicy.canCancel(authentication, order)) {
            Link cancel = linkTo(methodOn(OrderController.class)
                    .cancel(order.getId(), null))
                    .withRel("cancel");

            model.add(cancel);
        }

        return model;
    }
}
```

Ví dụ giả định `OrderController.one(Long id, Authentication authentication)` và `OrderController.cancel(Long id, CancelOrderRequest request)` có mapping tương ứng. `methodOn(...)` chỉ cung cấp metadata mapping để dựng URI; nó không thực thi method controller. Nếu controller signature thực tế khác, điều chỉnh invocation proxy theo đúng tham số của method.

Khi người dùng không đủ điều kiện, representation không có relation `cancel`. Các relation như `self` vẫn có thể xuất hiện theo chính sách đọc của ứng dụng.

## 7. Gắn affordance vào link

Link chỉ công bố URI và relation. Affordance bổ sung mô tả hành động như HTTP method, input và output. Với Spring HATEOAS, có thể gắn affordance từ controller method:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;

if (accessPolicy.canCancel(authentication, order)) {
    var cancelInvocation = methodOn(OrderController.class)
            .cancel(order.getId(), null);

    Link cancel = linkTo(cancelInvocation)
            .withRel("cancel")
            .andAffordance(afford(cancelInvocation));

    model.add(cancel);
}
```

Method `cancel` cần khai báo mapping như `@PostMapping`, request body và response type phù hợp. Spring HATEOAS đọc metadata mapping để xây affordance.

Affordance chỉ nên được thêm khi policy cho phép. Nếu thêm affordance cho mọi người nhưng chỉ ẩn link ở một nơi khác, client có thể nhận thông tin hành động không phù hợp với principal hiện tại.

Khi áp dụng cách này vào assembler ở mục 6, thay block tạo `cancel` link đơn giản bằng block gắn affordance; không cần thêm cả hai link cùng relation nếu hợp đồng không yêu cầu hai link riêng.

## 8. HAL link và HAL-FORMS template

HAL công bố link trong `_links`. Một relation `cancel` có thể cho client biết URI đích, nhưng HAL cơ bản không mô tả đầy đủ form nhập liệu.

Khi response được serialize bằng HAL-FORMS, affordance có thể được biểu diễn thành template trong `_templates`, ví dụ:

```json
{
  "_links": {
    "self": { "href": "/orders/42" },
    "cancel": { "href": "/orders/42/cancellation" }
  },
  "_templates": {
    "cancel": {
      "method": "POST",
      "target": "/orders/42/cancellation",
      "contentType": "application/json",
      "properties": [
        {
          "name": "reason",
          "type": "text",
          "required": true,
          "maxLength": 500
        }
      ]
    }
  }
}
```

Đây là cấu trúc minh họa; tên template và các property thực tế phụ thuộc affordance model và serializer. Client cần gửi `Accept` phù hợp với media type HAL-FORMS nếu muốn nhận metadata template. Nếu chỉ nhận `application/hal+json`, client có thể thấy link nhưng không có mô tả form chi tiết.

Không xem template là bằng chứng quyền vẫn còn hiệu lực. Quyền có thể thay đổi sau khi response được tạo; server phải kiểm tra lại khi client gửi request.

## 9. Bảo vệ endpoint thực thi hành động

Ẩn link giúp client biết thao tác không được công bố trong ngữ cảnh hiện tại. Endpoint phải tự bảo vệ độc lập:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping("/{id}/cancellation")
@PreAuthorize("hasAuthority('ORDER_CANCEL') or hasRole('ADMIN')")
ResponseEntity<EntityModel<OrderResponse>> cancel(
        @PathVariable Long id,
        @RequestBody CancelOrderRequest request) {

    Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
    Order updated = orderService.cancel(authentication, id, request);
    return ResponseEntity.ok(orderModelAssembler.toModel(updated, authentication));
}
```

Service cần tải lại resource và gọi cùng policy trước khi thay đổi trạng thái:

```java
Order cancel(Authentication authentication, Long id, CancelOrderRequest request) {
    Order order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    if (!accessPolicy.canCancel(authentication, order)) {
        throw new AccessDeniedException("Không được phép hủy đơn hàng này");
    }

    order.cancel(request.reason());
    return orderRepository.save(order);
}
```

`@PreAuthorize` chặn principal không có authority/role cơ bản. Service kiểm tra lại ownership, tenant và trạng thái để bảo vệ cả những đường gọi service khác trong ứng dụng. Nếu trạng thái đã thay đổi sau khi client đọc link, service từ chối thao tác thay vì tin vào representation cũ.

Trong ứng dụng thực tế, xử lý exception nên ánh xạ `AccessDeniedException` và lỗi domain sang response HTTP phù hợp, ví dụ `403 Forbidden` hoặc `409 Conflict`. Không trả thông tin nội bộ của policy trong error body nếu điều đó làm lộ dữ liệu.

## 10. Quyền theo resource không chỉ là role

Một người có authority `ORDER_CANCEL` không nhất thiết được hủy mọi đơn hàng. Ví dụ:

| Điều kiện | Kết quả |
|---|---|
| Có `ORDER_CANCEL`, là owner, trạng thái `PENDING` | Có thể hủy. |
| Có `ORDER_CANCEL`, không phải owner, không phải admin | Không thể hủy. |
| Có `ROLE_ADMIN`, trạng thái `PENDING` | Có thể hủy theo policy mẫu. |
| Có `ROLE_ADMIN`, trạng thái `SHIPPED` | Không thể hủy theo policy mẫu. |
| Có `ORDER_CANCEL`, là owner, trạng thái `CANCELLED` | Không thể hủy lần nữa. |

Điều này cho thấy authorization là quyết định trên principal và resource, không chỉ là so sánh một role. Với quyền theo tenant, project hoặc organization, hãy đưa các điều kiện đó vào policy/service và kiểm thử riêng.

## 11. Không đưa tên role vào relation

Relation nên mô tả semantics của hành động hoặc tài nguyên, ví dụ `approve`, `cancel`, `refund`. Không tạo relation kiểu `admin-cancel` chỉ vì chỉ admin mới thấy link.

Ví dụ, cùng relation `approve` có thể được công bố cho nhiều role khác nhau nếu họ có cùng khả năng nghiệp vụ. Client không cần biết tên role nội bộ của server; client chỉ cần biết thao tác nào được công bố.

Tên role và authority là chi tiết của policy bảo mật. Relation là hợp đồng hypermedia. Giữ hai khái niệm tách biệt giúp server thay đổi mô hình phân quyền mà không phải đổi relation và code client.

## 12. Xử lý người dùng anonymous

Một endpoint đọc có thể public trong khi action yêu cầu đăng nhập. Khi đó representation dành cho anonymous user có thể chứa `self` và các link công khai nhưng không chứa `cancel` hoặc `approve`.

Khi kiểm tra authentication, cần lưu ý anonymous authentication của Spring Security có thể được biểu diễn bằng `AnonymousAuthenticationToken` và `isAuthenticated()` vẫn có thể là `true`. Policy mẫu ở mục 5 đã loại trừ token anonymous.

Nếu API không cho phép anonymous đọc resource, request có thể bị từ chối ở security filter trước khi controller tạo representation. Khi đó client nhận `401 Unauthorized` hoặc hành vi authentication entry point đã cấu hình, thay vì một representation thiếu action link.

## 13. Cache response thay đổi theo người dùng

Nếu cùng một URL trả link khác nhau tùy principal, response là user-specific representation. Shared cache không được dùng response của người dùng A cho người dùng B.

Với dữ liệu nhạy cảm hoặc affordance phụ thuộc quyền, cân nhắc:

- `Cache-Control: private` để ngăn shared proxy cache lưu response cho nhiều người dùng.
- `Cache-Control: no-store` khi response không nên được lưu ở bất kỳ cache nào.
- `Vary: Authorization` nếu representation phụ thuộc header Authorization và cache có thể lưu response theo header đó.
- Với session cookie, cấu hình cache theo cơ chế xác thực thực tế; `Vary: Cookie` có thể tạo nhiều cache variant và cần cân nhắc cẩn thận.

Không mặc định rằng thêm `Vary: Authorization` là đủ cho mọi hệ thống. Hãy kiểm tra cache layer thực tế, cookie/session, CDN và reverse proxy. Với response nhạy cảm, `private, no-store` thường là lựa chọn rõ ràng hơn.

Nếu cache response theo user, kiểm thử header cache và xác nhận hai principal khác nhau không nhận cùng một representation đã cache. Không cache representation có affordance nhạy cảm trong shared cache nếu chưa có cơ chế phân vùng cache đáng tin cậy.

## 14. Kiểm thử role-based link bằng MockMvc

Spring Security Test cung cấp `@WithMockUser` để thiết lập principal và authorities cho test. Ví dụ chủ đơn hàng có quyền hủy:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderRoleAffordanceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "alice", authorities = {"ORDER_READ", "ORDER_CANCEL"})
    void ownerWithCancelAuthoritySeesCancelLink() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.cancel.href").exists());
    }

    @Test
    @WithMockUser(username = "bob", authorities = {"ORDER_READ", "ORDER_CANCEL"})
    void nonOwnerDoesNotSeeCancelLink() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.cancel").doesNotExist());
    }

    @Test
    @WithMockUser(username = "alice", authorities = "ORDER_READ")
    void readOnlyUserDoesNotSeeCancelLink() throws Exception {
        mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.cancel").doesNotExist());
    }
}
```

Test giả định fixture của đơn hàng `42` có owner là `alice` và trạng thái `PENDING`. `bob` có cùng authority `ORDER_CANCEL` nhưng không phải owner nên policy không công bố link. Nếu dùng `roles = "ADMIN"`, Spring Security tạo authority `ROLE_ADMIN` theo role prefix mặc định.

## 15. Kiểm thử endpoint dù link bị ẩn

Một test quan trọng là gọi trực tiếp endpoint với principal không có quyền. Kết quả phải bị từ chối ngay cả khi client biết URL:

```java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
@WithMockUser(username = "alice", authorities = "ORDER_READ")
void readOnlyUserCannotCallCancelEndpointDirectly() throws Exception {
    mockMvc.perform(post("/orders/42/cancellation")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"reason\":\"Changed my mind\"}"))
            .andExpect(status().isForbidden());
}
```

`csrf()` được thêm vì Spring Security bật CSRF protection cho các request thay đổi trạng thái trong cấu hình mặc định. Nếu ứng dụng cấu hình CSRF khác, test phải phản ánh cấu hình thực tế. Nếu authentication entry point hoặc access denied handler trả response tùy chỉnh, hãy kiểm tra status và error body theo hợp đồng đã công bố.

Nên có test riêng cho người có authority nhưng không phải owner: method-level `@PreAuthorize` cho qua authority cơ bản, nhưng policy ở service phải trả `403`. Điều đó chứng minh ownership được kiểm tra tại thao tác thực tế.

## 16. Kiểm thử trạng thái domain

Ngay cả principal có quyền cũng không được thấy link khi trạng thái không phù hợp:

```java
@Test
@WithMockUser(username = "alice", authorities = {"ORDER_READ", "ORDER_CANCEL"})
void ownerDoesNotSeeCancelLinkAfterShipment() throws Exception {
    // Fixture đặt đơn hàng 42 ở trạng thái SHIPPED.
    mockMvc.perform(get("/orders/42").accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
```

Kiểm thử tối thiểu nên bao gồm owner hợp lệ, user không phải owner, user thiếu authority, admin, anonymous (nếu endpoint đọc public) và resource ở trạng thái không cho phép. Nếu policy có tenant, thêm scenario cùng tenant và khác tenant.

## 17. Kiểm thử affordance trong HAL-FORMS

Nếu API công bố form template, test cần yêu cầu media type HAL-FORMS và xác nhận template chỉ xuất hiện với principal phù hợp:

```java
import static org.hamcrest.Matchers.endsWith;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;

mockMvc.perform(get("/orders/42")
                .accept(MediaTypes.HAL_FORMS_JSON))
        .andExpect(status().isOk())
        .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_FORMS_JSON))
        .andExpect(jsonPath("$._templates.cancel.method").value("POST"))
        .andExpect(jsonPath("$._templates.cancel.target")
                .value(endsWith("/orders/42/cancellation")));
```

Đây là assertion cho user đủ quyền và trạng thái `PENDING`. Với user không có quyền, test cần xác nhận template `cancel` không được công bố. Nếu serializer đặt template dưới tên khác hoặc dùng template mặc định, hãy kiểm tra cấu trúc response thực tế và giữ test đồng bộ với hợp đồng HAL-FORMS của ứng dụng.

## 18. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ẩn link mà không bảo vệ endpoint | Người dùng vẫn có thể gọi URI trực tiếp. | Dùng request authorization, `@PreAuthorize` và kiểm tra policy ở service. |
| Chỉ kiểm tra role, bỏ qua ownership | Người có role thao tác trên resource không thuộc quyền. | Kiểm tra principal với owner, tenant và resource state. |
| Lưu Authentication trong field singleton | Có thể rò rỉ principal giữa request. | Truyền Authentication qua tham số hoặc đọc request context đúng lúc. |
| Dùng `hasRole("ROLE_ADMIN")` | Role prefix có thể bị thêm hai lần. | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")`. |
| Nhầm role với authority | Policy không khớp chuỗi GrantedAuthority thực tế. | Chọn `hasRole` hoặc `hasAuthority` nhất quán. |
| Công bố affordance không điều kiện | Client thấy thao tác mà principal không đủ quyền. | Dùng policy trước khi thêm link/affordance. |
| Tin representation cũ | Quyền hoặc trạng thái có thể thay đổi sau khi link được tạo. | Re-authorize ở mỗi request thực thi. |
| Cache chung response theo người dùng | User khác có thể nhận affordance nhạy cảm. | Dùng private/no-store và cấu hình cache variation phù hợp. |
| Dùng relation mang tên role | Client bị gắn với mô hình phân quyền nội bộ. | Đặt relation theo semantics hành động. |
| Chỉ test link, không test endpoint | Không phát hiện lỗ hổng direct invocation. | Test cả visibility và request bị từ chối. |

## 19. Quy trình thiết kế role-based affordance

1. Xác định hành động và relation semantics, ví dụ `cancel`, `approve`, `refund`.
2. Xác định quyền cần thiết bằng role hoặc authority.
3. Xác định điều kiện resource: owner, tenant, trạng thái và các giới hạn nghiệp vụ.
4. Tập trung điều kiện vào access policy có thể tái sử dụng.
5. Truyền `Authentication` tới assembler và chỉ thêm link khi policy cho phép.
6. Gắn affordance khi cần mô tả method, input và output; chọn media type có khả năng biểu diễn phù hợp.
7. Bảo vệ endpoint bằng request authorization và method security.
8. Kiểm tra policy lại trong service trước khi thay đổi domain state.
9. Cấu hình cache để không chia sẻ representation phụ thuộc người dùng giữa các principal.
10. Kiểm thử link cho từng role, owner, tenant và trạng thái; đồng thời gọi trực tiếp endpoint để xác nhận server từ chối đúng.

Role-based affordance giúp representation phản ánh những hành động phù hợp với người dùng và resource hiện tại. Khi link visibility dùng chung policy với service authorization, còn endpoint luôn kiểm tra quyền khi nhận request, hypermedia trở thành một lớp hướng dẫn điều hướng đáng tin cậy mà không làm suy yếu ranh giới bảo mật của ứng dụng.

## Tài liệu tham khảo

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security – Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security – Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring HATEOAS – Affordances](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#server.affordances)
- [Spring HATEOAS – HAL-FORMS](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#mediatypes.hal-forms)
