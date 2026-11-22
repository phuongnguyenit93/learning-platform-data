# Bật bảo mật mức phương thức bằng @EnableMethodSecurity

Spring Security có thể kiểm tra quyền ngay tại phương thức Java mà người dùng gọi. Cơ chế này gọi là method security. Trong ứng dụng Spring Data REST, method security giúp bảo vệ service hoặc repository theo nghiệp vụ: ví dụ chỉ người có quyền ORDER_APPROVE mới được xác nhận đơn hàng, dù phương thức đó được gọi từ REST endpoint, controller khác hay một thành phần nội bộ.

Để bật cơ chế này trong các phiên bản Spring Security hiện đại, dùng @EnableMethodSecurity trên một lớp cấu hình. Sau đó, đặt các annotation như @PreAuthorize hoặc @PostAuthorize lên phương thức cần bảo vệ. Việc kiểm tra quyền ở mức phương thức bổ sung cho bảo mật URL trong SecurityFilterChain; hai lớp bảo vệ giải quyết những phạm vi khác nhau.

## 1. Method security là gì?

Bảo mật URL kiểm tra request dựa trên HTTP method và đường dẫn. Ví dụ, GET /api/orders/** có thể yêu cầu quyền ORDER_READ, còn POST /api/orders/** yêu cầu quyền ORDER_CREATE.

Method security kiểm tra quyền tại điểm gọi một phương thức Java. Ví dụ, service có thể chỉ cho phép người dùng có ORDER_APPROVE gọi confirm():

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void confirm(Long orderId) {
        // Thực hiện quy tắc xác nhận đơn hàng.
    }
}
~~~

Nếu một người dùng không có authority ORDER_APPROVE gọi phương thức qua Spring proxy, Spring Security từ chối lời gọi trước khi phần thân phương thức chạy.

Điều này đặc biệt hữu ích khi cùng một service được gọi từ nhiều nơi. Quy tắc quyền được đặt tại phương thức nghiệp vụ, thay vì phải lặp lại trong từng controller hoặc endpoint.

## 2. Bật method security bằng @EnableMethodSecurity

Tạo lớp cấu hình Spring:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Trong Spring Security 6, @EnableMethodSecurity bật pre/post annotations theo mặc định. Vì vậy, các annotation như @PreAuthorize, @PostAuthorize, @PreFilter và @PostFilter có thể được sử dụng sau khi cấu hình này được nạp vào application context.

Các tùy chọn quan trọng:

~~~java
@Configuration
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
public class MethodSecurityConfiguration {
}
~~~

- prePostEnabled bật các annotation biểu thức như @PreAuthorize và @PostAuthorize. Giá trị mặc định là true.
- securedEnabled bật @Secured. Giá trị mặc định là false.
- jsr250Enabled bật các annotation JSR-250 như @RolesAllowed. Giá trị mặc định là false.

Chỉ bật các kiểu annotation mà ứng dụng thực sự sử dụng để cấu hình dễ hiểu. @EnableGlobalMethodSecurity là cấu hình cũ; với ứng dụng dùng Spring Security hiện đại, ưu tiên @EnableMethodSecurity.

## 3. Dùng @PreAuthorize để kiểm tra trước khi gọi phương thức

@PreAuthorize đánh giá biểu thức quyền trước khi phương thức được thực thi. Nếu biểu thức trả về false, Spring Security ném AccessDeniedException và từ chối lời gọi.

Ví dụ kiểm tra authority:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('ORDER_READ')")
    public PurchaseOrder findOrder(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Kiểm tra nghiệp vụ và chuyển trạng thái đơn hàng.
    }
}
~~~

Các biểu thức thường dùng:

| Biểu thức | Ý nghĩa |
|---|---|
| hasAuthority('ORDER_READ') | Người dùng có đúng authority ORDER_READ. |
| hasAnyAuthority('ORDER_READ', 'ORDER_ADMIN') | Có ít nhất một authority được liệt kê. |
| hasRole('ADMIN') | Có role ADMIN; mặc định được kiểm tra dưới authority ROLE_ADMIN. |
| hasAnyRole('ADMIN', 'AUDITOR') | Có ít nhất một role trong danh sách. |
| isAuthenticated() | Người gọi đã được xác thực. |
| permitAll() | Cho phép mọi người gọi phương thức. |
| denyAll() | Từ chối mọi lời gọi. |

hasAuthority so sánh tên authority chính xác. hasRole thường tự thêm tiền tố ROLE_ theo cấu hình role prefix mặc định. Ví dụ hasRole('ADMIN') tương ứng với authority ROLE_ADMIN; không truyền ROLE_ADMIN vào hasRole nếu đang dùng prefix mặc định.

Đối với quyền nghiệp vụ như ORDER_APPROVE hoặc CUSTOMER_EXPORT, hasAuthority thường rõ ràng hơn vì tên quyền được kiểm tra trực tiếp.

## 4. Kiểm tra quyền theo tham số phương thức

Biểu thức SpEL có thể tham chiếu tham số của phương thức. Điều này hữu ích khi quyền phụ thuộc vào tài nguyên cụ thể, chẳng hạn người dùng chỉ được xem đơn hàng do mình sở hữu.

Ví dụ:

~~~java
@Service
public class OrderService {

    @PreAuthorize(
        "hasAuthority('ORDER_READ_ALL') or #ownerId == authentication.name"
    )
    public List<PurchaseOrder> findOrdersFor(String ownerId) {
        return repository.findByOwnerId(ownerId);
    }
}
~~~

Trong biểu thức:

- #ownerId tham chiếu tham số ownerId.
- authentication.name là tên principal hiện tại.
- Người có ORDER_READ_ALL được xem dữ liệu của mọi chủ sở hữu; người khác chỉ được truy vấn dữ liệu của chính mình.

Để Spring nhận diện tên tham số trong biểu thức, hãy biên dịch với tùy chọn giữ tên tham số như -parameters. Có thể dùng annotation @P của Spring Security để đặt tên tường minh khi cần:

~~~java
import org.springframework.security.core.parameters.P;

@PreAuthorize("#ownerId == authentication.name")
public List<PurchaseOrder> findOrdersFor(
        @P("ownerId") String owner) {
    return repository.findByOwnerId(owner);
}
~~~

Nếu biểu thức dựa trên ID tài nguyên, không nên chỉ tin ID do client truyền vào. Service cần tải entity và kiểm tra quyền sở hữu hoặc tenant theo dữ liệu đáng tin cậy trong hệ thống.

## 5. Dùng @PostAuthorize để kiểm tra kết quả trả về

@PostAuthorize đánh giá quyền sau khi phương thức đã chạy. Biểu thức có thể tham chiếu returnObject, tức đối tượng được phương thức trả về.

Ví dụ, chỉ cho phép người dùng đọc đơn hàng nếu họ là chủ sở hữu hoặc có quyền quản trị:

~~~java
@Service
public class OrderQueryService {

    @PostAuthorize(
        "returnObject.ownerId == authentication.name or hasAuthority('ORDER_READ_ALL')"
    )
    public PurchaseOrder getById(Long id) {
        return repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException("Order not found"));
    }
}
~~~

@PostAuthorize hữu ích khi cần kiểm tra thuộc tính của đối tượng vừa tải, chẳng hạn ownerId, tenantId hoặc trạng thái truy cập.

Tuy nhiên, phương thức đã được thực thi trước khi biểu thức được đánh giá. Vì vậy, với thao tác ghi như chuyển tiền, xóa dữ liệu hoặc xác nhận đơn hàng, hãy ưu tiên @PreAuthorize để từ chối trước khi có side effect. Không dùng @PostAuthorize như lớp bảo vệ duy nhất cho một thao tác có thể thay đổi dữ liệu hoặc gọi hệ thống bên ngoài.

## 6. Dùng @PreFilter và @PostFilter cho collection

@PreFilter lọc các phần tử của tham số collection trước khi phương thức chạy. @PostFilter lọc các phần tử của collection trả về sau khi phương thức chạy.

Ví dụ @PostFilter:

~~~java
@Service
public class OrderQueryService {

    @PostFilter(
        "filterObject.ownerId == authentication.name or hasAuthority('ORDER_READ_ALL')"
    )
    public List<PurchaseOrder> findAllVisibleOrders() {
        return repository.findAll();
    }
}
~~~

filterObject đại diện cho phần tử đang được kiểm tra. Chỉ các phần tử thỏa điều kiện mới còn trong collection trả về.

Ví dụ @PreFilter:

~~~java
@PreFilter(
    "filterObject.ownerId == authentication.name",
    filterTarget = "orders"
)
public void processOrders(List<PurchaseOrder> orders) {
    // Chỉ xử lý các phần tử vượt qua điều kiện lọc.
}
~~~

Khi phương thức có nhiều tham số collection, filterTarget chỉ rõ tham số cần lọc. Nếu chỉ có một collection phù hợp, có thể không cần chỉ định filterTarget.

Các annotation filter thuận tiện cho collection nhỏ, nhưng chúng có thể lọc sau khi toàn bộ dữ liệu đã được tải vào bộ nhớ. Với collection lớn hoặc API phân trang, nên đưa điều kiện quyền vào query/database để tránh tải dữ liệu người gọi không được xem và tránh làm sai metadata tổng số trang.

## 7. Dùng @Secured và @RolesAllowed

Ngoài các annotation biểu thức, Spring Security còn hỗ trợ hai kiểu annotation dựa trên role.

**@Secured**

~~~java
@Configuration
@EnableMethodSecurity(securedEnabled = true)
public class MethodSecurityConfiguration {
}
~~~

~~~java
@Secured("ROLE_ADMIN")
public void deleteOrder(Long id) {
    repository.deleteById(id);
}
~~~

@Secured kiểm tra authority được liệt kê. Annotation này không hỗ trợ biểu thức SpEL phức tạp như @PreAuthorize.

**@RolesAllowed**

~~~java
@Configuration
@EnableMethodSecurity(jsr250Enabled = true)
public class MethodSecurityConfiguration {
}
~~~

~~~java
import jakarta.annotation.security.RolesAllowed;

@RolesAllowed({"ADMIN", "ORDER_MANAGER"})
public void exportOrders() {
    // Xuất dữ liệu đơn hàng.
}
~~~

@RolesAllowed thuộc JSR-250. Tên role được ánh xạ theo cấu hình role prefix của Spring Security; với cấu hình mặc định, các role thường tương ứng với authority có tiền tố ROLE_.

Nếu cần kiểm tra quyền theo tham số, chủ sở hữu tài nguyên hoặc kết hợp nhiều điều kiện, @PreAuthorize thường linh hoạt hơn @Secured và @RolesAllowed.

## 8. Kết hợp method security với bảo mật URL trong Spring Data REST

Một ứng dụng Spring Data REST thường có hai lớp kiểm soát:

- HTTP/request authorization giới hạn ai có thể gọi đường dẫn hoặc HTTP method.
- Method authorization giới hạn ai có thể gọi thao tác nghiệp vụ cụ thể.

Ví dụ cấu hình URL:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("ORDER_READ")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("ORDER_CREATE")
            .anyRequest().authenticated()
        )
        .build();
    }
}
~~~

Sau đó, service vẫn kiểm tra quyền nghiệp vụ:

~~~java
@PreAuthorize("hasAuthority('ORDER_APPROVE')")
@Transactional
public void approveOrder(Long id) {
    PurchaseOrder order = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Order not found"));

    order.approve();
}
~~~

Người gọi cần vượt qua kiểm tra URL để vào endpoint và kiểm tra method để thực hiện thao tác approve. Nếu một controller, scheduler hoặc service khác gọi cùng phương thức qua Spring proxy, quy tắc method security vẫn được áp dụng.

Không nên chỉ dựa vào đường dẫn REST để bảo vệ service. Một phương thức nghiệp vụ có thể được gọi từ nhiều entry point khác nhau; đặt quyền trên phương thức giúp quy tắc đi cùng thao tác nghiệp vụ.

## 9. Method security hoạt động thông qua Spring AOP proxy

Method security sử dụng interceptor và proxy của Spring để kiểm tra lời gọi phương thức. Vì vậy, lời gọi cần đi qua Spring-managed bean proxy.

Ví dụ sau có thể bỏ qua method security:

~~~java
@Service
public class OrderService {

    public void updateAndApprove(Long id) {
        approve(id); // self-invocation: gọi nội bộ trên cùng instance.
    }

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Thay đổi trạng thái đơn hàng.
    }
}
~~~

Lời gọi this.approve() từ một phương thức khác trong cùng instance không đi qua proxy, vì vậy interceptor method security có thể không được kích hoạt.

Cách xử lý thường dùng là tách thao tác được bảo vệ sang một Spring bean khác và gọi bean đó qua proxy:

~~~java
@Service
public class OrderApprovalService {

    @PreAuthorize("hasAuthority('ORDER_APPROVE')")
    public void approve(Long id) {
        // Thực hiện nghiệp vụ phê duyệt.
    }
}
~~~

Một service khác inject OrderApprovalService và gọi approve(). Lời gọi qua bean proxy sẽ đi qua cơ chế kiểm tra quyền.

Các lưu ý khác:

- Đảm bảo service được tạo và quản lý bởi Spring container.
- Tránh tự khởi tạo service bằng new nếu mong đợi method security hoạt động.
- Với proxy dựa trên interface hoặc class, kiểm tra cấu hình proxy và khả năng intercept của phương thức.
- Không dựa vào self-invocation để thực thi một kiểm tra quyền quan trọng.
- Giữ các phương thức nghiệp vụ được bảo vệ ở một ranh giới service rõ ràng.

## 10. Phân biệt xác thực và phân quyền

@EnableMethodSecurity bật kiểm tra quyền tại phương thức, nhưng không tự cấu hình cơ chế xác thực người dùng.

- **Authentication (xác thực):** xác định người gọi là ai, ví dụ thông qua session, HTTP Basic, OAuth2 Resource Server hoặc JWT.
- **Authorization (phân quyền):** quyết định người gọi có được thực hiện thao tác hay không, ví dụ ORDER_READ hoặc ORDER_APPROVE.

Method security sử dụng Authentication hiện tại trong SecurityContext để đánh giá biểu thức. Ứng dụng vẫn cần cấu hình authentication mechanism và SecurityFilterChain phù hợp.

Nếu request chưa được xác thực, cấu hình bảo mật request thường yêu cầu đăng nhập trước khi phương thức được gọi. Nếu người dùng đã xác thực nhưng không có authority phù hợp, method security từ chối lời gọi.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| @PreAuthorize không có tác dụng | Chưa bật @EnableMethodSecurity hoặc bean không đi qua proxy. | Kiểm tra cấu hình và cách inject/gọi bean. |
| @Secured không chạy | securedEnabled đang false. | Bật securedEnabled=true. |
| @RolesAllowed không chạy | jsr250Enabled đang false hoặc thiếu dependency annotation tương ứng. | Bật jsr250Enabled và kiểm tra import jakarta/javax phù hợp phiên bản. |
| hasRole luôn trả false | Nhầm role với authority hoặc tiền tố ROLE_. | Dùng hasRole('ADMIN') cho ROLE_ADMIN hoặc hasAuthority với tên chính xác. |
| #parameter không được nhận diện | Tên tham số không được giữ trong bytecode. | Biên dịch với -parameters hoặc dùng @P. |
| Gọi nội bộ không bị chặn | Self-invocation không đi qua proxy. | Tách phương thức sang bean khác và gọi qua proxy. |
| @PostFilter làm API chậm | Toàn bộ collection được tải rồi mới lọc. | Đưa điều kiện vào repository query/database. |
| Thao tác ghi đã chạy trước khi bị từ chối | Dùng @PostAuthorize cho thao tác có side effect. | Dùng @PreAuthorize để kiểm tra trước khi thực thi. |

Khi nhận AccessDeniedException, cần phân biệt lỗi từ URL authorization và method authorization. Có thể bật log phù hợp trong môi trường phát triển để xác định interceptor hoặc biểu thức nào từ chối lời gọi; tránh ghi token hoặc dữ liệu nhạy cảm vào log.

## 12. Quy trình kiểm tra method security

Với phương thức approveOrder:

1. Bật @EnableMethodSecurity trong application context.
2. Xác nhận người dùng chưa đăng nhập không thể truy cập API theo cấu hình request security.
3. Gọi phương thức với người dùng có ORDER_READ nhưng không có ORDER_APPROVE; xác nhận thao tác bị từ chối.
4. Gọi với người dùng có ORDER_APPROVE; xác nhận nghiệp vụ được thực hiện.
5. Gọi cùng service từ một controller hoặc bean khác để xác nhận lời gọi đi qua proxy.
6. Thử đường gọi nội bộ trong cùng class để nhận diện trường hợp self-invocation.
7. Nếu dùng @PostAuthorize, xác nhận returnObject được kiểm tra sau khi phương thức trả về.
8. Nếu dùng filter annotations, kiểm tra collection nhỏ và đánh giá khả năng chuyển điều kiện lọc xuống database.
9. Kiểm tra cả URL authorization và method authorization để biết lớp nào đang bảo vệ từng thao tác.

@EnableMethodSecurity bật cơ chế kiểm tra quyền ở ranh giới phương thức. Dùng @PreAuthorize để bảo vệ trước khi thực thi, @PostAuthorize để kiểm tra kết quả trả về, và các filter annotation khi cần lọc collection. Đặt quy tắc quyền gần service nghiệp vụ, bảo đảm lời gọi đi qua Spring proxy và kết hợp với bảo mật URL để bảo vệ đầy đủ các endpoint Spring Data REST.
