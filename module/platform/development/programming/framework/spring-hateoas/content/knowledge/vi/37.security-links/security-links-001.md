# Link theo quyền truy cập

Trong REST API có hypermedia, link cho client biết những hướng điều hướng và thao tác mà representation công bố. Nhưng không phải mọi người dùng đều có quyền thực hiện cùng một hành động trên cùng một tài nguyên. Một nhân viên có thể xem đơn hàng nhưng không được phê duyệt; người quản lý có thể phê duyệt đơn hàng thuộc chi nhánh của mình; đơn đã giao có thể không còn khả năng hủy.

Spring HATEOAS cho phép tạo link và affordance có điều kiện theo người dùng hiện tại, quyền, phạm vi tenant và trạng thái nghiệp vụ. Khi client đọc representation, nó chỉ thấy những khả năng đang được công bố cho ngữ cảnh của mình. Tuy vậy, việc ẩn link chỉ cải thiện khả năng khám phá và trải nghiệm client. Server vẫn phải xác thực và phân quyền trên từng request đến endpoint đích.

## Link phản ánh khả năng hiện tại

Giả sử API trả về một đơn hàng đang chờ phê duyệt. Người dùng có quyền phê duyệt có thể nhận representation:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    },
    "approve": {
      "href": "https://shop.example/api/orders/o-42/approval"
    }
  }
}
~~~

Người dùng chỉ có quyền đọc nhận representation không có link **approve**:

~~~json
{
  "id": "o-42",
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/o-42"
    }
  }
}
~~~

Client có thể dùng sự hiện diện của relation **approve** để quyết định có hiển thị nút phê duyệt hay không. Client không cần tự suy luận từ role name, trạng thái đơn hàng hoặc cấu trúc URL.

Điều kiện công bố link có thể phụ thuộc đồng thời vào:

- Người gọi đã xác thực hay chưa.
- Người gọi có authority hoặc role phù hợp hay không.
- Người gọi có quyền trên đúng order này hay không.
- Order có thuộc tenant, tổ chức hoặc phạm vi dữ liệu của người gọi không.
- Trạng thái nghiệp vụ hiện tại có cho phép hành động không.
- Các điều kiện khác như hạn xử lý, khóa dữ liệu hoặc workflow đang chạy.

Một role chung như MANAGER không nhất thiết đủ để phê duyệt mọi đơn hàng. Quyết định thường cần policy theo resource, tenant và trạng thái.

## Authentication và authorization

Hai khái niệm cần được phân biệt:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Người gọi là ai? | Người dùng đăng nhập có username an.nguyen. |
| Authorization | Người đó được làm gì trên tài nguyên cụ thể? | an.nguyen được xem order o-42 nhưng không được phê duyệt order thuộc chi nhánh khác. |

Spring Security cung cấp **Authentication** để biểu diễn principal và authorities của request hiện tại. Tuy nhiên, chỉ kiểm tra **hasRole("MANAGER")** thường chưa đủ cho quyền ở cấp tài nguyên. Policy có thể cần tra cứu tenant, quyền sở hữu, quan hệ tổ chức và trạng thái domain.

Không nên để assembler tự viết các quy tắc quyền phức tạp hoặc đọc trực tiếp nhiều bảng. Hãy đưa quyết định vào một policy/authorization service dùng chung, rồi gọi policy đó khi dựng representation và khi thực thi command.

## Mô hình quyết định công bố link

Một cách thiết kế dễ kiểm soát là dùng một policy service có câu hỏi rõ ràng:

~~~java
boolean canRead(Authentication authentication, UUID orderId);
boolean canApprove(Authentication authentication, UUID orderId);
boolean canCancel(Authentication authentication, UUID orderId);
~~~

Policy cần xét cả principal và tài nguyên. Ví dụ, canApprove có thể trả true khi người dùng có authority phê duyệt, thuộc đúng tenant, có quyền trên order và order vẫn ở trạng thái PENDING.

Không nên chỉ dùng kiểm tra authority MANAGER để kết luận người dùng được phép phê duyệt mọi order. Authority là một phần của quyết định; nó không thay thế kiểm tra ownership, tenant hoặc trạng thái nghiệp vụ.

DTO trong ví dụ có thể được định nghĩa như sau:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record OrderDto(
        UUID id,
        String status,
        BigDecimal total) {
}
~~~

Các lớp Order, ApprovalRequest và OrderPermissionService là kiểu domain/ứng dụng do dự án định nghĩa.

## Tạo link có điều kiện trong assembler

Ví dụ sau dùng một policy service để quyết định có công bố link **approve** hay không. Relation trong ví dụ là token mở rộng **approve**; API công khai nên tài liệu hóa relation, hoặc dùng URI relation ổn định và CURIE khi cần.

~~~java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    private final OrderPolicy orderPolicy;

    OrderModelAssembler(OrderPolicy orderPolicy) {
        this.orderPolicy = orderPolicy;
    }

    EntityModel<OrderDto> toModel(
            Order order,
            Authentication authentication) {

        OrderDto dto = new OrderDto(
                order.getId(),
                order.getStatus().name(),
                order.getTotal());

        EntityModel<OrderDto> model = EntityModel.of(
                dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId())).withSelfRel());

        if (orderPolicy.canApprove(authentication, order.getId())) {
            model.add(linkTo(methodOn(OrderController.class)
                    .approve(order.getId(), null))
                    .withRel("approve"));
        }

        if (orderPolicy.canCancel(authentication, order.getId())) {
            model.add(linkTo(methodOn(OrderController.class)
                    .cancel(order.getId()))
                    .withRel("cancel"));
        }

        return model;
    }
}
~~~

**methodOn(...)** mô tả mapping controller để xây URI; nó không gọi phương thức approve hoặc cancel. Policy chỉ quyết định link nào được thêm vào representation. Nếu người dùng không đủ quyền hoặc trạng thái không phù hợp, link tương ứng không xuất hiện.

Để tránh lặp logic, cùng một policy nên được dùng ở endpoint thực thi command. Nếu assembler và endpoint có hai quy tắc khác nhau, client có thể nhìn thấy link mà request luôn bị từ chối, hoặc không nhìn thấy link dù người dùng thực sự được phép thao tác.

## Xây dựng policy theo người dùng, tenant và trạng thái

Ví dụ policy service:

~~~java
import java.util.UUID;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("orderPolicy")
class OrderPolicy {

    private final OrderPermissionService permissions;

    OrderPolicy(OrderPermissionService permissions) {
        this.permissions = permissions;
    }

    boolean canApprove(Authentication authentication, UUID orderId) {
        return permissions.canApprove(authentication, orderId);
    }

    boolean canCancel(Authentication authentication, UUID orderId) {
        return permissions.canCancel(authentication, orderId);
    }
}
~~~

**OrderPermissionService** là thành phần ứng dụng chịu trách nhiệm quyết định quyền. Nó có thể kiểm tra principal đã xác thực, authority, tenant hiện tại, phạm vi order và trạng thái workflow. Ví dụ policy logic ở dạng khái niệm:

~~~text
canApprove(user, order) =
    user is authenticated
    AND user has order:approve authority
    AND user belongs to order.tenant
    AND user is allowed to approve this order
    AND order.status == PENDING
    AND order is not locked
~~~

Việc kiểm tra trạng thái ở đây phục vụ việc công bố khả năng tại thời điểm tạo representation. Trạng thái có thể thay đổi ngay sau đó; command handler vẫn phải kiểm tra lại trước khi cập nhật.

Nếu API dùng multi-tenancy, tenant phải được xác định từ ngữ cảnh đáng tin cậy như principal hoặc tenant context đã xác thực. Không lấy tenantId từ query parameter rồi tin rằng người dùng được phép truy cập tenant đó.

## Bảo vệ endpoint đích bằng method security

Ẩn link không bảo vệ endpoint. Người dùng có thể biết URL từ log, browser history, một representation cũ hoặc một client khác rồi gửi request trực tiếp. Vì vậy, endpoint và tầng nghiệp vụ phải kiểm tra quyền độc lập.

Bật method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Áp dụng cùng policy lên command service:

~~~java
import java.util.UUID;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class OrderCommandService {

    @PreAuthorize("@orderPolicy.canApprove(authentication, #orderId)")
    public void approve(UUID orderId, ApprovalRequest request) {
        // Tải lại order, kiểm tra trạng thái và thực hiện chuyển trạng thái.
    }

    @PreAuthorize("@orderPolicy.canCancel(authentication, #orderId)")
    public void cancel(UUID orderId) {
        // Tải lại order, kiểm tra trạng thái và thực hiện hủy.
    }
}
~~~

Trong ví dụ, Spring Security đánh giá biểu thức trước khi gọi method. Policy bean được tham chiếu bằng tên orderPolicy; #orderId là tham số method. Cần bật method security và bảo đảm Spring có thể đọc tên tham số, hoặc dùng cú pháp tham chiếu tham số phù hợp với cấu hình build.

Controller chuyển request đến command service:

~~~java
import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;

@PostMapping("/api/orders/{orderId}/approval")
@ResponseStatus(HttpStatus.NO_CONTENT)
void approve(
        @PathVariable UUID orderId,
        @RequestBody ApprovalRequest request) {
    orderCommandService.approve(orderId, request);
}
~~~

Nếu policy từ chối, Spring Security chặn command theo cơ chế method security và exception translation của ứng dụng. Với REST API, cần cấu hình authentication entry point và access denied handler để trả status/body phù hợp, thường là **401** cho chưa xác thực và **403** cho đã xác thực nhưng không được phép.

Không dựa vào việc controller chỉ gọi command qua một đường đi. Nếu command có thể được gọi từ message handler, scheduled job hoặc controller khác, quy tắc quyền cần được đặt ở ranh giới nghiệp vụ phù hợp và phân biệt rõ tác vụ người dùng với tác vụ hệ thống.

### Kiểm tra lại trong transaction

Quyết định công bố link diễn ra trước thời điểm client gửi command. Trong khoảng thời gian đó, một quản trị viên khác có thể đã phê duyệt order, quyền của người dùng có thể bị thu hồi hoặc order có thể bị khóa. Đây là tình huống time-of-check to time-of-use (TOCTOU).

Vì vậy, command phải tải lại dữ liệu và kiểm tra invariant trong transaction trước khi ghi. Với workflow cạnh tranh, có thể dùng optimistic locking qua version field, hoặc khóa bản ghi phù hợp để hai request đồng thời không cùng thực hiện một chuyển trạng thái. Method security xác thực quyền gọi method; kiểm tra domain trong transaction bảo đảm trạng thái vẫn hợp lệ tại thời điểm cập nhật.

Không dùng sự hiện diện của link từ response cũ làm bằng chứng rằng hành động vẫn còn hợp lệ. Client cần xử lý status xung đột như 409 Conflict nếu trạng thái resource đã thay đổi.

## Link có điều kiện trong collection

Khi trả collection, mỗi item có thể có tập link khác nhau tùy người dùng và quyền trên từng resource. Ví dụ một người quản lý chỉ được phê duyệt order của chi nhánh mình:

~~~java
import java.util.List;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/api/orders")
CollectionModel<EntityModel<OrderDto>> all(Authentication authentication) {
    List<EntityModel<OrderDto>> items = orderQueryService
            .findVisibleTo(authentication)
            .stream()
            .map(order -> orderAssembler.toModel(order, authentication))
            .toList();

    return CollectionModel.of(items);
}
~~~

**findVisibleTo(...)** phải lọc tập tài nguyên mà principal được phép xem trước khi tạo representation. Không tải toàn bộ order rồi chỉ ẩn các link nhạy cảm: dữ liệu của order không được phép đọc cũng không nên xuất hiện trong _embedded.

Nếu policy phải kiểm tra quyền cho hàng trăm item, tránh tạo một query riêng cho từng item. N+1 authorization queries có thể làm collection chậm đáng kể. Có thể dùng query lọc theo tenant/permission, batch authorization hoặc tải trước dữ liệu policy cần thiết. Dù có tối ưu, endpoint chi tiết và command vẫn phải kiểm tra quyền trên resource được yêu cầu.

## Link và affordance theo quyền truy cập

Link cho biết một target có ý nghĩa gì. Affordance có thể mô tả thêm cách thực hiện thao tác như HTTP method, input type và template. Khi một hành động không khả dụng, không công bố cả link/affordance tương ứng.

Ví dụ, nếu order có thể phê duyệt và người dùng có quyền, representation có thể cung cấp link **approve** cùng affordance nhận **ApprovalRequest**. Nếu không, cả hai đều vắng mặt. Khi serialize bằng HAL-FORMS, template có thể hiển thị input để client dựng form.

Không nên công bố affordance rồi chỉ ẩn nút ở giao diện. Bất kỳ client nào cũng có thể gửi request thủ công. Endpoint vẫn cần authorization và validation. Cũng không nên dùng affordance để gửi dữ liệu nhạy cảm mà principal không được phép đọc.

Một hành động có thể bị ẩn vì hai lý do khác nhau:

- **Không được phép:** principal không có quyền trên resource.
- **Không hợp lệ ở trạng thái hiện tại:** người dùng có quyền chung nhưng resource chưa thể thực hiện hành động.

Có thể dùng một policy method tổng hợp canApprove cho cả hai điều kiện, hoặc tách policy quyền và policy workflow để hiển thị lý do phù hợp. Nếu cần giải thích vì sao hành động không khả dụng, hãy công bố thông tin an toàn, không tiết lộ quyền của người khác hoặc quy tắc nội bộ nhạy cảm.

## Ẩn link không phải ranh giới bảo mật

Đây là nguyên tắc quan trọng nhất khi thiết kế security links:

> Link vắng mặt không thay thế authorization ở server.

Một client có thể:

- Gọi trực tiếp URI mà nó đã biết.
- Dùng link được lưu từ response cũ.
- Sửa request bằng công cụ HTTP.
- Gửi request bằng một client không tuân thủ giao diện hypermedia.
- Theo link khi quyền hoặc trạng thái resource đã thay đổi.

Vì vậy, endpoint phải kiểm tra authentication, authorization, tenant scope và business state ở thời điểm thực thi. Không coi URI là bí mật; không coi link là capability bảo mật trừ khi API được thiết kế theo một mô hình capability riêng với token khó giả mạo và quy tắc vòng đời rõ ràng.

Nếu người dùng chưa đăng nhập, request thường nhận **401 Unauthorized**. Nếu đã đăng nhập nhưng không đủ quyền, request thường nhận **403 Forbidden**. Một số API trả **404 Not Found** để không tiết lộ sự tồn tại của tài nguyên cho người không có quyền; đây là quyết định chính sách cần áp dụng nhất quán.

## Tránh rò rỉ thông tin qua link

Link và relation cũng là dữ liệu. Một representation có thể vô tình tiết lộ:

- URI của chức năng quản trị hoặc tài nguyên thuộc tenant khác.
- Sự tồn tại của workflow chỉ dành cho một nhóm người dùng.
- ID hoặc tên resource mà principal không được phép biết.
- Tên relation nội bộ tiết lộ quy trình hoặc hệ thống backend.
- Hành động có thể thực hiện trên một resource mà người gọi không được phép xem.

Hãy kiểm tra quyền đọc resource trước khi tạo representation, sau đó mới quyết định các link hành động. Với tài nguyên nhạy cảm, cân nhắc cùng một chính sách 404 cho cả truy cập trực tiếp và traversal qua link để tránh resource enumeration.

Không đưa token truy cập, session secret hoặc thông tin xác thực vào href. Link phải là URI điều hướng; thông tin xác thực được gửi qua cơ chế HTTP phù hợp như Authorization header hoặc cookie bảo mật.

## Cache representation phụ thuộc người dùng

Khi tập link thay đổi theo principal, cùng một URI có thể trả representation khác nhau cho hai người dùng. Ví dụ, người quản lý thấy link approve, còn người xem chỉ thấy self. Nếu response cá nhân hóa bị lưu trong shared cache và phát lại cho người khác, cache có thể làm lộ link hoặc dữ liệu không phù hợp.

Với representation phụ thuộc quyền, cần chọn chính sách cache phù hợp:

- Dùng **Cache-Control: private** khi chỉ cho phép cache riêng ở client.
- Dùng **Cache-Control: no-store** nếu response chứa dữ liệu nhạy cảm hoặc không nên lưu.
- Nếu cho phép cache, bảo đảm cache key phân biệt đúng ngữ cảnh xác thực và các header ảnh hưởng representation.
- Không dùng ETag chung cho các representation khác nhau theo principal.

Ví dụ controller có thể đặt cache policy cho response cá nhân hóa:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;

return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(orderAssembler.toModel(order, authentication));
~~~

Không nên chỉ thêm **Vary: Authorization** rồi mặc định mọi reverse proxy sẽ cache an toàn. Hãy kiểm tra chính sách cache thực tế của CDN, gateway và proxy. Với dữ liệu nhạy cảm, private hoặc no-store thường là lựa chọn dễ kiểm soát hơn.

## Security links trong Spring Security request flow

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Security filter chain]
    B --> C{Authenticated?}
    C -- No --> D[401 / authentication entry point]
    C -- Yes --> E[Controller]
    E --> F[Load resource within visible scope]
    F --> G[Policy evaluates principal, tenant and state]
    G --> H[Assembler adds only permitted links]
    H --> I[HAL response]
    I --> J[Client follows action link]
    J --> K[Security filter chain again]
    K --> L[Method security and domain validation]
    L --> M[Execute command or return 403/404/409]
~~~

Mỗi request mới lại đi qua security filter chain. Khi client theo link approve, server phải đánh giá quyền tại request mới; quyền có thể đã bị thu hồi hoặc order đã chuyển sang trạng thái khác kể từ lần GET trước.

## Phân biệt security filter, request authorization và method security

Các lớp bảo vệ bổ sung cho nhau:

| Lớp | Phạm vi | Ví dụ |
| --- | --- | --- |
| Security filter chain | Bảo vệ request theo URL, HTTP method, authentication và policy tổng quát. | Yêu cầu đăng nhập cho /api/**. |
| Request authorization | Quy tắc truy cập ở cấp endpoint. | Chỉ authority order:read mới được GET collection. |
| Method security | Quy tắc ở cấp service method hoặc command. | @PreAuthorize kiểm tra quyền phê duyệt đúng order. |
| Domain validation | Điều kiện trạng thái và invariant nghiệp vụ. | Không phê duyệt order đã bị hủy. |

Không nên chỉ bảo vệ URL bằng matcher rồi bỏ qua kiểm tra ở tầng nghiệp vụ nếu cùng command được gọi từ nhiều nơi. Ngược lại, method security cũng không thay thế việc cấu hình endpoint, CSRF, CORS và các bảo vệ HTTP khác.

Với browser session và các request thay đổi trạng thái như POST/PATCH/DELETE, cần xem xét CSRF protection. CORS chỉ kiểm soát nguồn trình duyệt được phép gọi; CORS không phải cơ chế authorization. API phải dùng HTTPS để bảo vệ dữ liệu và credential trên đường truyền.

## Kiểm thử link theo quyền truy cập

Kiểm thử cần xác nhận cả hai điều:

1. Representation chỉ công bố link khi policy cho phép.
2. Endpoint vẫn từ chối request trực tiếp khi policy không cho phép.

Ví dụ MockMvc với Spring Security Test:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderSecurityLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "approver", authorities = "order:approve")
    void exposesApproveLinkWhenPolicyAllows() throws Exception {
        mockMvc.perform(get("/api/orders/o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.approve.href").exists());
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "order:read")
    void hidesApproveLinkWhenPolicyDenies() throws Exception {
        mockMvc.perform(get("/api/orders/o-42")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._links.approve").doesNotExist());
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "order:read")
    void rejectsDirectApprovalRequest() throws Exception {
        mockMvc.perform(post("/api/orders/o-42/approval")
                        .with(csrf())
                        .contentType("application/json")
                        .content("{\"comment\":\"Đã kiểm tra\"}"))
                .andExpect(status().isForbidden());
    }
}
~~~

Các test giả định fixture có order o-42 ở trạng thái PENDING, policy cho approver phê duyệt và từ chối viewer, đồng thời REST security handler trả 403 cho người dùng đã xác thực nhưng không đủ quyền. Nếu cấu hình ứng dụng dùng 404 để che giấu sự tồn tại resource, điều chỉnh assertion theo hợp đồng đã chọn.

Để chạy các test này, dự án cần dependency **spring-security-test**. Test với **@WithMockUser** kiểm tra authorities trong SecurityContext; nó không tự mô phỏng tenant hoặc ownership. Hãy bổ sung test policy cho tenant khác, resource không thuộc người dùng và trạng thái không cho phép.

### Những trường hợp nên có trong bộ test

- Người dùng được quyền đọc nhưng không được quyền phê duyệt: link approve vắng mặt.
- Người dùng được quyền phê duyệt trên đúng tenant: link xuất hiện nếu trạng thái cho phép.
- Người dùng có authority nhưng order thuộc tenant khác: không có link và request trực tiếp bị từ chối.
- Order đã chuyển trạng thái: link approve vắng mặt; request cũ vẫn bị từ chối.
- Người dùng chưa xác thực: endpoint được bảo vệ trả challenge/status phù hợp.
- Collection chỉ chứa resource mà người dùng được phép đọc.
- Cache header không cho shared cache lưu representation cá nhân hóa nếu policy yêu cầu.

## Lỗi thường gặp

| Vấn đề | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nghĩ ẩn link là đủ bảo mật | Người dùng vẫn gọi trực tiếp URL đã biết. | Bảo vệ endpoint và service bằng authorization. |
| Chỉ kiểm tra role chung | Có thể truy cập order của tenant hoặc chi nhánh khác. | Policy kiểm tra principal, resource, tenant và state. |
| Assembler và endpoint dùng hai policy khác nhau | Link hiển thị nhưng thao tác luôn bị từ chối, hoặc ngược lại. | Dùng chung policy service và vẫn đánh giá lại lúc command. |
| Trả cả resource không được phép xem nhưng chỉ ẩn link | Rò rỉ dữ liệu qua _embedded hoặc field. | Lọc collection theo quyền đọc trước khi serialize. |
| Kiểm tra quyền cho từng item bằng query riêng | Collection phát sinh N+1 authorization queries. | Batch permission check hoặc lọc trong query phù hợp. |
| Cache chung response có link theo người dùng | Người khác có thể nhận representation không thuộc quyền của họ. | Dùng private/no-store hoặc cache key phân biệt principal. |
| Đưa credential vào href | Token có thể lộ qua log, history hoặc referrer. | Gửi credential qua cơ chế xác thực HTTP an toàn. |
| Coi CORS là authorization | Request ngoài trình duyệt hoặc client khác vẫn có thể gọi API. | Dùng Spring Security và policy ở server. |
| Không kiểm tra trạng thái khi thực thi | Link cũ có thể được dùng sau khi workflow thay đổi. | Kiểm tra lại state và quyền trong command transaction. |

## Nguyên tắc thiết kế

- Chỉ công bố link/affordance khi người dùng hiện tại được phép và hành động phù hợp với trạng thái resource.
- Đưa quyết định vào policy service có thể tái sử dụng, thay vì rải role check trong assembler.
- Xét principal, authority, ownership, tenant và business state.
- Lọc resource theo quyền đọc trước khi tạo collection representation.
- Bảo vệ endpoint đích bằng request authorization và method security.
- Đánh giá lại quyền và trạng thái tại thời điểm thực thi command.
- Không xem link vắng mặt là ranh giới bảo mật; không xem URI là bí mật.
- Tránh rò rỉ link, relation, ID hoặc metadata của resource không được phép xem.
- Chọn cache policy an toàn cho representation phụ thuộc người dùng.
- Kiểm thử cả sự hiện diện/vắng mặt của link và việc endpoint từ chối request trực tiếp.

Link theo quyền truy cập làm cho hypermedia phản ánh các khả năng hiện tại của người dùng trên từng tài nguyên. Spring HATEOAS cho phép assembler công bố link và affordance có điều kiện; Spring Security cùng policy ở tầng nghiệp vụ bảo vệ request thực tế. Khi hai phần dùng chung quy tắc, client có thể điều hướng chính xác hơn mà server vẫn kiểm soát quyền ở mọi request.
