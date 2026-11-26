# Không dùng link thay authorization

## Mục tiêu

Spring HATEOAS có thể chỉ công bố những links hoặc affordances mà người dùng hiện tại có thể sử dụng. Ví dụ, API chỉ thêm relation cancel khi người gọi có quyền hủy đơn hàng và đơn hàng đang ở trạng thái cho phép hủy. Cách biểu diễn này giúp client hiểu các khả năng hiện có, nhưng nó không bảo vệ endpoint đích.

Client có thể lưu một href từ response cũ, tự tạo URI, gọi endpoint trực tiếp hoặc gửi lại request sau khi quyền và trạng thái đã thay đổi. Vì vậy, server phải xác thực và phân quyền ở mỗi request, kể cả khi link tương ứng không xuất hiện trong representation.

Sau bài học, bạn có thể:

- Phân biệt hypermedia discovery với authorization.
- Ẩn hoặc công bố action links theo quyền và trạng thái nghiệp vụ.
- Bảo vệ endpoint bằng Spring Security request authorization.
- Dùng method security và kiểm tra quyền trên từng object.
- Ngăn truy cập chéo tenant và lỗi IDOR.
- Xử lý link cũ, thay đổi trạng thái và race condition.
- Kiểm thử cả link visibility lẫn request gọi trực tiếp endpoint.

## Link mô tả khả năng, không cấp quyền

Giả sử representation của một đơn hàng có thể chứa:

~~~json
{
  "id": "order-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "/api/orders/order-42"
    },
    "cancel": {
      "href": "/api/orders/order-42/cancel"
    }
  }
}
~~~

Relation cancel cho biết API đang công bố một khả năng liên quan đến đơn hàng. Nếu người dùng không có quyền hủy hoặc đơn hàng đã được giao, server có thể bỏ relation đó khỏi representation.

Việc không có link chỉ giúp client khám phá API chính xác hơn. Nó không ngăn người dùng:

- Gọi trực tiếp URI đã biết hoặc đoán được.
- Dùng lại href đã lưu từ một response trước đó.
- Gửi request từ script hoặc HTTP client khác.
- Thay đổi ID trong URI để thử truy cập tài nguyên của người khác.
- Gửi lại thao tác sau khi trạng thái nghiệp vụ đã thay đổi.

Server phải coi mọi request là đầu vào cần kiểm tra. Quyền truy cập được quyết định tại thời điểm request đến, dựa trên principal, authority, tài nguyên cụ thể, tenant và trạng thái hiện tại.

## Hai trách nhiệm riêng biệt

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Hypermedia links/affordances | Client hiện có thể khám phá khả năng nào? | Có công bố relation cancel hay không? |
| Authentication | Request đến từ ai? | Token hoặc session xác định principal nào? |
| Authorization | Principal này có được thực hiện request trên tài nguyên này không? | Có quyền orders:cancel và có quyền với order-42 không? |
| Domain rule | Thao tác có hợp lệ ở trạng thái hiện tại không? | Đơn hàng PENDING mới có thể bị hủy. |

Các lớp này bổ sung cho nhau. Hypermedia giúp client không phải tự suy đoán thao tác. Spring Security bảo vệ đường vào HTTP và method. Domain model bảo vệ các quy tắc chuyển trạng thái.

Một relation cancel cũng không tự mô tả đầy đủ HTTP method hoặc request body. Nếu API cần công bố chi tiết thao tác, có thể dùng affordances hoặc HAL-FORMS để mô tả phương thức và input. Dù representation mô tả action chi tiết đến đâu, endpoint vẫn phải thực hiện authorization.

## Công bố action link theo quyền và trạng thái

Assembler có thể tạo self link cho mọi người dùng được phép đọc đơn hàng, sau đó chỉ thêm cancel link nếu policy cho biết thao tác hiện khả dụng:

~~~java
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
class OrderModelAssembler {

    private final OrderLinkPolicy linkPolicy;

    OrderModelAssembler(OrderLinkPolicy linkPolicy) {
        this.linkPolicy = linkPolicy;
    }

    EntityModel<OrderResponse> toModel(Order order) {

        OrderResponse response = new OrderResponse(
                order.id(),
                order.status());

        EntityModel<OrderResponse> model = EntityModel.of(
                response,
                linkTo(methodOn(OrderController.class)
                        .findById(order.id()))
                        .withSelfRel());

        if (linkPolicy.canCancel(order)) {
            Link cancel = linkTo(methodOn(OrderController.class)
                    .cancel(order.id()))
                    .withRel("cancel");
            model.add(cancel);
        }

        return model;
    }
}
~~~

Policy tập trung quyết định link có nên xuất hiện hay không:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
class OrderLinkPolicy {

    private final TenantResolver tenantResolver;

    OrderLinkPolicy(TenantResolver tenantResolver) {
        this.tenantResolver = tenantResolver;
    }

    boolean canCancel(Order order) {
        Authentication authentication = SecurityContextHolder.getContext()
                .getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        boolean hasAuthority = authentication.getAuthorities().stream()
                .anyMatch(authority ->
                        authority.getAuthority().equals("orders:cancel"));
        if (!hasAuthority) {
            return false;
        }

        UUID currentTenantId = tenantResolver.tenantIdFor(authentication);

        return currentTenantId != null
                && currentTenantId.equals(order.tenantId())
                && order.isCancelable();
    }
}
~~~

Ví dụ giả định TenantResolver lấy tenant ID từ principal đã xác thực hoặc một nguồn đáng tin cậy phía server. OrderLinkPolicy đọc Authentication từ SecurityContextHolder trong request MVC hiện tại. Không lấy tenant ID do client tự gửi làm căn cứ cấp quyền.

Controller nhận Authentication từ Spring Security và truyền vào assembler:

~~~java
@GetMapping("/{id}")
EntityModel<OrderResponse> findById(@PathVariable UUID id) {

    Order order = orderService.findReadableOrder(
            id,
            tenantResolver.currentTenantId());
    return assembler.toModel(order);
}
~~~

Controller cũng ánh xạ action link tới endpoint thật:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;

@PostMapping("/{id}/cancel")
ResponseEntity<Void> cancel(@PathVariable UUID id) {
    orderCommandService.cancel(id);
    return ResponseEntity.noContent().build();
}
~~~

Ví dụ giả định controller được inject TenantResolver và OrderCommandService. Hai method này minh họa cách tạo link và endpoint tương ứng; chúng thuộc cùng controller quản lý order.

Nếu không đủ điều kiện hủy, response vẫn có self link và dữ liệu người dùng được phép đọc, nhưng không có relation cancel. Client có thể ẩn nút hủy dựa trên links. Endpoint cancel vẫn phải kiểm tra lại quyền khi được gọi.

Trong ứng dụng lớn, nên dùng chung policy hoặc authorization service cho logic hiển thị link và logic bảo vệ thao tác để tránh hai nơi diễn giải quyền khác nhau. Tuy nhiên, việc dùng chung policy không có nghĩa request authorization có thể bị bỏ qua.

## Bảo vệ endpoint ở tầng HTTP

Spring Security có thể giới hạn request dựa trên HTTP method và path:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/orders/**")
                        .hasAuthority("orders:read")
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/orders/*/cancel")
                        .hasAuthority("orders:cancel")
                        .anyRequest()
                        .authenticated())
                .build();
    }
}
~~~

Khi request POST tới đường dẫn cancel, Spring Security kiểm tra authority orders:cancel trước khi request tới controller. Người dùng chỉ có orders:read sẽ không thể hủy đơn hàng bằng cách gọi URI trực tiếp.

Thứ tự các matcher rất quan trọng: Spring Security áp dụng matcher phù hợp đầu tiên. Hãy đặt các quy tắc cụ thể trước quy tắc tổng quát. Trong ứng dụng OAuth2 Resource Server, cấu hình thêm resource server JWT hoặc cơ chế authentication thực tế của hệ thống; đoạn trên chỉ minh họa phần authorization.

Nếu dùng session/cookie authentication, CSRF protection thường cần được giữ cho các request thay đổi trạng thái. Với API stateless dùng bearer token trong Authorization header, chính sách CSRF có thể khác; hãy cấu hình dựa trên cách credential được gửi, không tắt CSRF chỉ vì endpoint trả JSON.

## Bảo vệ ở tầng method

Request matcher bảo vệ đường vào HTTP. Method security bổ sung ranh giới tại service, nơi thao tác nghiệp vụ thực sự được thực hiện:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Ví dụ service yêu cầu authority hủy đơn:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderCommandService {

    @PreAuthorize("hasAuthority('orders:cancel')")
    @Transactional
    public void cancel(UUID orderId) {
        Order order = repository.findById(orderId)
                .orElseThrow(OrderNotFoundException::new);

        orderAuthorization.requireAccessToCurrentTenant(order);
        order.cancel();
    }
}
~~~

Ví dụ rút gọn giả định repository và orderAuthorization được inject qua constructor. Policy tenant phải dùng tenant của principal đã xác thực. Domain method cancel() kiểm tra trạng thái hiện tại và từ chối chuyển trạng thái không hợp lệ.

@PreAuthorize kiểm tra authority trước khi chạy method. Kiểm tra tenant/object trong service đảm bảo người dùng có authority chung vẫn không thể thao tác lên đơn hàng của tenant khác. Domain model kiểm tra trạng thái chuyển đổi ngay trong thao tác nghiệp vụ.

Có thể đặt kiểm tra object-level trong biểu thức @PreAuthorize, ví dụ gọi một bean policy với authentication và orderId. Dù chọn cách nào, thao tác nhạy cảm vẫn nên kiểm tra các invariant có thể thay đổi trong transaction thực hiện lệnh. Đừng dựa vào kết quả policy đã tính trước đó khi trạng thái hoặc quyền sở hữu có thể thay đổi đồng thời.

## Ngăn IDOR và truy cập chéo tenant

IDOR (Insecure Direct Object Reference) xảy ra khi server xác thực người dùng nhưng không kiểm tra họ có quyền với object được tham chiếu hay không. Ví dụ người dùng có quyền orders:read thay ID trong /api/orders/{id} để đọc đơn hàng của tenant khác.

Không đủ nếu chỉ kiểm tra:

~~~java
@PreAuthorize("hasAuthority('orders:read')")
Order findById(UUID id) {
    return repository.findById(id).orElseThrow();
}
~~~

Authority orders:read chỉ nói rằng principal có quyền đọc một số đơn hàng. Nó chưa chứng minh principal được đọc mọi đơn hàng.

Hãy ràng buộc truy vấn với phạm vi dữ liệu của principal:

~~~java
Order findReadableOrder(UUID orderId, UUID currentTenantId) {
    return repository.findByIdAndTenantId(orderId, currentTenantId)
            .orElseThrow(OrderNotFoundException::new);
}
~~~

currentTenantId phải được lấy từ security context hoặc thành phần tin cậy phía server. Không nhận tenant ID từ query parameter hay request body rồi dùng nó làm phạm vi truy cập mà không xác minh.

Có thể dùng authorization policy kiểm tra owner, tenant, vai trò và trạng thái. Với dữ liệu nhạy cảm, truy vấn có scope ngay từ repository thường dễ kiểm soát hơn việc tải mọi object rồi mới lọc ở controller.

## Link cũ và race condition

Giả sử một response lúc 10:00 có relation cancel vì đơn hàng đang PENDING. Trước khi client gọi link, một tiến trình khác đã xác nhận đơn hàng. Link trong response cũ vẫn tồn tại trong bộ nhớ client, nhưng thao tác hủy hiện không còn hợp lệ.

Server phải đánh giá lại ở thời điểm nhận request:

1. Xác thực principal.
2. Kiểm tra authority cần thiết.
3. Tải object trong phạm vi tenant/owner được phép.
4. Kiểm tra trạng thái hiện tại và điều kiện chuyển trạng thái.
5. Thực hiện thay đổi trong transaction.

Nếu cần bảo vệ trước cập nhật đồng thời, dùng optimistic locking với @Version hoặc một câu lệnh cập nhật có điều kiện theo trạng thái hiện tại. Việc chỉ kiểm tra trạng thái khi tạo link không bảo vệ được thao tác khỏi race condition.

Links có thể thay đổi theo quyền và trạng thái, vì vậy response cá nhân hóa cần chính sách cache phù hợp. Tránh đưa representation có links riêng của người dùng vào shared cache công khai. Tùy cơ chế xác thực, dùng Cache-Control: private hoặc no-store và Vary phù hợp; với dữ liệu nhạy cảm, no-store thường là lựa chọn rõ ràng.

## Phản hồi khi request không được phép

Với API cấu hình authentication entry point trả status HTTP, Spring Security thường phân biệt:

| Tình huống | HTTP status thường dùng | Ý nghĩa |
|---|---:|---|
| Chưa xác thực | 401 Unauthorized | Client cần xác thực hợp lệ. |
| Đã xác thực nhưng thiếu authority | 403 Forbidden | Principal không được phép thực hiện thao tác. |
| Tài nguyên không tồn tại | 404 Not Found | Không tìm thấy tài nguyên. |

Một số API cố ý trả 404 thay cho 403 khi cần che giấu sự tồn tại của object mà người gọi không được phép biết. Đây là chính sách chống rò rỉ thông tin ở cấp tài nguyên; phải áp dụng nhất quán và không nên dùng 404 một cách ngẫu nhiên.

Không trả 200 chỉ vì controller đã bỏ action link. Nếu client gọi trực tiếp endpoint không được phép, server phải trả status lỗi thích hợp và không thực hiện thao tác.

## Kiểm thử link visibility và authorization riêng biệt

Kiểm thử representation có thể xác minh người đọc chỉ thấy links được phép:

~~~java
import org.junit.jupiter.api.Test;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.security.test.context.support.WithMockUser;

@Test
@WithMockUser(authorities = "orders:read")
void readerDoesNotSeeCancelLink() throws Exception {
    mockMvc.perform(get("/api/orders/{id}", orderId)
                    .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.href").exists())
            .andExpect(jsonPath("$._links.cancel").doesNotExist());
}
~~~

Test trên chỉ xác minh khả năng khám phá. Cần có test riêng chứng minh người đọc không thể gọi endpoint bằng cách tự tạo URI:

~~~java
import org.junit.jupiter.api.Test;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
@WithMockUser(authorities = "orders:read")
void readerCannotCancelByCallingUriDirectly() throws Exception {
    mockMvc.perform(post("/api/orders/{id}/cancel", orderId)
                    .with(csrf()))
            .andExpect(status().isForbidden());
}
~~~

Ví dụ dùng CSRF token vì cấu hình mặc định của Spring Security bật CSRF cho request thay đổi trạng thái. Nếu API dùng bearer token stateless và cấu hình CSRF khác, test cần gửi credential theo đúng cơ chế của ứng dụng.

Ngoài ra, cần kiểm thử:

- Người dùng có orders:cancel nhưng thuộc tenant khác không thể hủy object.
- Người dùng cùng tenant nhưng đơn hàng đã ở trạng thái không thể hủy bị từ chối.
- User không có authentication bị từ chối theo chính sách 401.
- User có authority đúng và sở hữu tài nguyên có thể thực hiện thao tác.
- Request được gửi lại bằng link cũ vẫn bị kiểm tra theo quyền và trạng thái hiện tại.
- Service không thực hiện thay đổi dữ liệu khi authorization thất bại.
- Links cá nhân hóa không bị cache và trả cho principal khác.

Với OAuth2 Resource Server, dùng test post processor jwt() để tạo JWT giả lập với authorities tương ứng. Với session-based authentication, @WithMockUser hoặc user() phù hợp hơn. Dùng cơ chế test phản ánh đúng cách ứng dụng xác thực trong production.

## Những lỗi thường gặp

- **Coi link ẩn là bảo mật:** người dùng vẫn có thể tự gửi request tới URI đích; bảo vệ endpoint bằng Spring Security.
- **Chỉ kiểm tra role ở controller:** service có thể được gọi từ luồng khác; bảo vệ method nghiệp vụ và object cụ thể.
- **Chỉ kiểm tra authority chung:** quyền orders:read không đồng nghĩa quyền đọc mọi đơn hàng; phải kiểm tra tenant hoặc owner.
- **Tin tenant ID từ client:** lấy phạm vi dữ liệu từ principal đã xác thực hoặc nguồn tin cậy phía server.
- **Chỉ kiểm tra trạng thái khi tạo link:** trạng thái có thể đổi trước khi request tới; kiểm tra lại trong transaction.
- **Dùng link cũ như bằng chứng được phép:** href không phải capability token trừ khi hệ thống thiết kế một cơ chế token riêng; link HATEOAS thông thường không cấp quyền.
- **Chỉ test link không xuất hiện:** test thêm request gọi trực tiếp endpoint và xác nhận 401/403 phù hợp.
- **Dùng 404 không nhất quán:** chỉ che giấu sự tồn tại tài nguyên khi đó là chính sách bảo mật có chủ đích.
- **Cache representation cá nhân hóa công khai:** thiết lập Cache-Control và Vary theo cơ chế authentication; dùng no-store cho dữ liệu nhạy cảm.
- **Tắt CSRF chỉ vì API trả JSON:** lựa chọn CSRF theo cách credential được gửi và trạng thái của ứng dụng.

## Quy trình thiết kế security-aware links

1. Xác định relation/affordance nào có ích cho client trong trạng thái hiện tại.
2. Dùng policy để quyết định có công bố action link hay không dựa trên principal, tenant, object và trạng thái.
3. Bảo vệ HTTP endpoint bằng request authorization trong SecurityFilterChain.
4. Bảo vệ service method bằng method security cho các thao tác nhạy cảm.
5. Kiểm tra quyền trên object và tenant ở server; không dựa vào ID hoặc tenant do client tự khai báo.
6. Kiểm tra lại trạng thái và invariant trong transaction thực hiện thao tác.
7. Thiết lập status code, cache policy và CSRF phù hợp.
8. Kiểm thử cả representation links lẫn request trực tiếp tới endpoint khi link bị ẩn hoặc đã cũ.

Hypermedia giúp client biết thao tác nào đang được công bố trong ngữ cảnh hiện tại. Authorization quyết định request có được phép thực hiện hay không tại thời điểm server nhận nó. Khi giữ hai trách nhiệm này riêng biệt, API vừa dễ khám phá vừa bảo vệ được dữ liệu và nghiệp vụ trước request trực tiếp, link cũ, truy cập chéo tenant và thay đổi trạng thái đồng thời.

## Tài liệu tham khảo

- Spring Security Reference Documentation, Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security Reference Documentation, Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security Reference Documentation, Testing: https://docs.spring.io/spring-security/reference/servlet/test/index.html
- Spring HATEOAS Reference Documentation, Affordances: https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.affordances
