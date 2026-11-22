# Proxy, lời gọi nội bộ và trường hợp annotation không được áp dụng

## 1. Vì sao một phương thức có `@PreAuthorize` vẫn có thể chạy?

Trong Spring Boot, một endpoint của **OAuth 2.0 Resource Server** có thể đã kiểm tra Bearer access token nhưng vẫn cần bảo vệ hành động nghiệp vụ như đọc, sửa hoặc phê duyệt đơn hàng. Spring Security hỗ trợ **method security** bằng các annotation như `@PreAuthorize` và `@PostAuthorize`.

Ví dụ ý định của người phát triển:

~~~java
@Service
public class OrderApprovalService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Thao tác phê duyệt cần quyền đặc biệt.
    }
}
~~~

Nếu một controller gọi phương thức này **thông qua Spring bean đã được proxy bảo vệ**, Spring Security có cơ hội chặn lời gọi, kiểm tra `SCOPE_orders.approve` và từ chối khi không đủ quyền.

Nhưng tình huống sau rất dễ gây bất ngờ:

~~~java
@Service
public class OrderApprovalService {

    public void approveFromWorkflow(long orderId) {
        // Lời gọi nội bộ trên chính đối tượng hiện tại.
        this.approve(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Ghi trạng thái "APPROVED" vào database.
    }
}
~~~

Khi một thành phần bên ngoài gọi `approveFromWorkflow(...)` qua proxy, phương thức bên ngoài **không được bảo vệ bởi annotation riêng nào**; từ bên trong nó, lời gọi `this.approve(...)` thường chạy trực tiếp trên target object, **không quay ra proxy**. Vì vậy `@PreAuthorize` trên `approve(...)` có thể **không được thực thi** trong chế độ Spring AOP proxy mặc định.

Đây là vấn đề cốt lõi của bài học: **annotation trên mã nguồn không tự bảo đảm mọi đường đi tới phương thức đều được kiểm tra**. Cần hiểu nơi Spring AOP proxy đứng, những lời gọi nào đi qua proxy, và cách thiết kế ranh giới nghiệp vụ sao cho không có đường đi vòng ngoài ý muốn.

Bài tập trung vào **Spring Security Servlet Resource Server** (Spring MVC, Bearer JWT/opaque token) và method security kiểu **proxy** của Spring. Một số giới hạn cũng áp dụng chung cho Spring AOP như `@Transactional` hoặc `@Async`, nhưng trọng tâm ở đây là **bảo vệ nghiệp vụ**.

## 2. Hai lớp bảo vệ: HTTP request và phương thức nghiệp vụ

### 2.1. Resource Server bảo vệ ở HTTP filter chain

Với JWT access token:

~~~http
GET /api/orders/42 HTTP/1.1
Authorization: Bearer <ACCESS_TOKEN>
~~~

đường đi khái quát:

~~~mermaid
flowchart TD
    A["HTTP Request + Bearer token"] --> B["Spring SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["JwtDecoder / JWT validators"]
    D --> E{"Token hợp lệ?"}
    E -->|"Không"| F["401"]
    E -->|"Có"| G["JwtAuthenticationToken + SecurityContext"]
    G --> H["AuthorizationFilter"]
    H --> I{"HTTP policy cho phép?"}
    I -->|"Không"| J["403 hoặc challenge"]
    I -->|"Có"| K["Spring MVC Controller"]
    K --> L["Service method qua Spring AOP proxy"]
    L --> M["@PreAuthorize / method authorization"]
    M --> N["Nghiệp vụ chạy nếu hợp lệ"]
~~~

Sơ đồ mô tả các mốc chính, không phải danh sách filter cố định. Nếu dùng opaque token, nhánh xác thực có thể đi qua `OpaqueTokenIntrospector` thay `JwtDecoder`; vấn đề proxy ở tầng service vẫn giống nhau.

### 2.2. URL security không thay thế method security

Ví dụ:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().authenticated()
);
~~~

Điều này bảo vệ **HTTP request** tới đường dẫn được chỉ định. Nhưng phương thức service có thể còn được gọi từ:

- Controller khác có URL rule rộng hơn.
- GraphQL resolver hoặc API endpoint khác.
- Message listener/consumer.
- Scheduled job.
- Application event handler.
- Một service nội bộ khác.
- Một API version mới vô tình thiếu rule.

Vì thế việc đặt `@PreAuthorize` ở **service boundary** có giá trị như lớp defense in depth. Tuy nhiên, nếu service được gọi **không đi qua proxy**, annotation có thể không chạy dù đã xuất hiện trong source code.

### 2.3. Method security không thay thế token validation

Khi controller được gọi sau Bearer authentication, Spring Security có `Authentication` trong `SecurityContext`. Với JWT Resource Server, đó thường là `JwtAuthenticationToken` chứa principal `Jwt` và các authorities từ scopes.

Method security sử dụng các authorities đã được xác thực, ví dụ `SCOPE_orders.read`. Nó không nên:

- Tự Base64URL-decode JWT rồi tin raw claims.
- Nhận role từ request header chưa được xác minh.
- Bỏ issuer/audience/expiry validation.
- Coi `sub` là quyền truy cập mọi bản ghi mà không kiểm tra tenant/ownership.

**SecurityFilterChain xác minh credential và kiểm soát request; method security bổ sung policy tại ranh giới phương thức.** Cả hai cần cấu hình đúng.

## 3. Spring AOP proxy hoạt động như thế nào?

### 3.1. Proxy đứng giữa caller và target bean

Khi method security được bật, Spring có thể tạo **AOP proxy** xung quanh một Spring-managed bean có các phương thức cần bảo vệ. Caller nhận một reference đến proxy thay vì trực tiếp điều khiển mọi lời gọi trên target.

~~~text
Controller / Bean khác
        |
        v
Spring AOP proxy
        |
        +--> Method security interceptor
        |         |
        |         +--> kiểm tra @PreAuthorize
        |
        v
Target service object
        |
        v
Business method body
~~~

Nếu policy từ chối, interceptor có thể ném `AccessDeniedException` (hoặc subtype phù hợp) trước khi phương thức nghiệp vụ chạy.

### 3.2. Lời gọi bên ngoài qua proxy

Ví dụ:

~~~java
@RestController
public class OrdersController {

    private final OrderQueryService orders;

    public OrdersController(OrderQueryService orders) {
        this.orders = orders;
    }

    @GetMapping("/api/orders/{id}")
    public OrderDto get(@PathVariable long id) {
        // orders là Spring-injected service reference.
        return orders.load(id);
    }
}
~~~

Service:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto load(long id) {
        return repository.findOrderDto(id);
    }
}
~~~

Khi controller được Spring quản lý, `orders` thường là reference đến bean đã được AOP proxy nếu method security áp dụng. Lời gọi `orders.load(id)` đi qua security interceptor trước method body.

### 3.3. Lời gọi nội bộ không đi ra proxy

Bây giờ thêm vào cùng service:

~~~java
@Service
public class OrderQueryService {

    public OrderDto loadWithoutGuard(long id) {
        // Lời gọi cùng instance, không quay lại qua Spring proxy.
        return this.load(id);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public OrderDto load(long id) {
        return repository.findOrderDto(id);
    }
}
~~~

Nếu một controller vô tình gọi `loadWithoutGuard(...)`, method security trên `load(...)` có thể bị bỏ qua bởi **self-invocation**.

Hình dung:

~~~mermaid
flowchart TD
    A["Controller"] --> B["Spring AOP proxy của OrderQueryService"]
    B --> C["Target.loadWithoutGuard()"]
    C --> D["this.load() trực tiếp trên target"]
    D --> E["Không đi qua proxy lần hai"]
    E --> F["Guard @PreAuthorize của load() không được gọi"]
~~~

Kết luận không phải “method security luôn vô dụng” mà là: **chỉ những join point đi qua proxy mới nhận được advice trong proxy-based Spring AOP**. Khi đã ở bên trong target object, `this` là target và lời gọi trên `this` không tự quay lại proxy.

## 4. Bật method security đúng cách

### 4.1. Dependencies

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Method security cần Spring Security configuration phù hợp. Trong các ứng dụng Spring Boot hiện đại, cách phổ biến là khai báo:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

**Chỉ thêm `@PreAuthorize` trên service mà không bật method security phù hợp thì không thể mặc định annotation đã được thực thi.**

### 4.2. `@EnableMethodSecurity` hỗ trợ annotation nào?

Theo mô hình Spring Security hiện đại:

- `@PreAuthorize`: kiểm tra **trước** khi gọi phương thức.
- `@PostAuthorize`: kiểm tra **sau** khi phương thức đã chạy, có thể tham chiếu kết quả trả về.
- `@PreFilter` / `@PostFilter`: lọc collection/array/map theo cơ chế được hỗ trợ; cần cân nhắc hiệu năng và business semantics.
- `@Secured`: thường cần bật tường minh qua `securedEnabled = true`.
- Annotation JSR-250 như `@RolesAllowed`: thường cần bật tường minh qua `jsr250Enabled = true`.

Ví dụ:

~~~java
@EnableMethodSecurity(
    prePostEnabled = true,
    securedEnabled = true,
    jsr250Enabled = true
)
@Configuration
public class MethodSecurityConfig {
}
~~~

`prePostEnabled` thường được bật theo mặc định trong `@EnableMethodSecurity`. Không cần kích hoạt mọi annotation family nếu ứng dụng không sử dụng.

### 4.3. Method security và OAuth2 Resource Server vẫn là hai cấu hình riêng

Ví dụ filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

`oauth2ResourceServer(...jwt(...))` thiết lập JWT Bearer authentication; `@EnableMethodSecurity` thiết lập method interceptors. Bật một trong hai **không tự động thay thế** chức năng của thành phần còn lại.

`application.yml` minh họa:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

Issuer/audience phải khớp hợp đồng Authorization Server và API. Đặc biệt không dùng OIDC ID Token thay access token chỉ vì cả hai đều là JWT có thể xác minh chữ ký.

## 5. Trường hợp quan trọng nhất: self-invocation

### 5.1. Ví dụ lỗi phân quyền trong quy trình approval

Giả sử API có hai phương thức:

~~~java
@Service
public class ApprovalService {

    public void submitOrder(long orderId) {
        // Bước nghiệp vụ khác.
        this.approveOrder(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approveOrder(long orderId) {
        orderRepository.markApproved(orderId);
    }
}
~~~

Người phát triển có thể kỳ vọng rằng **mọi lời gọi `approveOrder`** đều bị ràng buộc bởi `SCOPE_orders.approve`. Nhưng khi `submitOrder` gọi qua `this`, interceptor của `approveOrder` có thể không chạy.

Nếu HTTP endpoint cho phép scope `orders.submit` gọi `submitOrder`, caller có thể vô tình thực hiện hành động `approve` chỉ với quyền `submit`. Đây là **privilege escalation do đường đi nội bộ**, chứ không phải lỗi JWT signature hay `JwtGrantedAuthoritiesConverter`.

### 5.2. Lý do phương thức được chú thích không tự kiểm tra

Annotation là metadata. Trong proxy mode, Spring Security thiết lập interceptor **trên lời gọi đi qua proxy**, không chèn câu lệnh `if` vào đầu mọi Java method body trên bytecode thông thường.

Cần phân biệt:

~~~text
callerBean.approvalService.approveOrder(42)
    -> proxy
    -> @PreAuthorize
    -> target.approveOrder(42)
~~~

với:

~~~text
target.submitOrder(42)
    -> this.approveOrder(42)
    -> target.approveOrder(42)
    -> không đi qua proxy
~~~

Ngay cả khi đối tượng được tạo từ Spring BeanFactory và proxy thực sự tồn tại, **self-invocation trong cùng target object vẫn không được proxy đánh chặn** theo mô hình proxy AOP mặc định.

### 5.3. Gọi `this` không phải nguyên nhân duy nhất

Các cú pháp gọi nội bộ sau đều có bản chất tương tự khi lời gọi thực hiện trên cùng target:

~~~java
approveOrder(orderId);
this.approveOrder(orderId);
privateHelperThatCallsApprove(orderId);
~~~

Điểm quyết định là đường đi tới method được bảo vệ **có đi qua AOP proxy không**, chứ không phải chỉ có từ khóa `this`.

Một helper trong cùng class gọi method được chú thích vẫn có nguy cơ bypass. Gọi một method có `@PreAuthorize` từ một method khác của cùng bean **không phải external proxy call**.

## 6. Cách sửa được ưu tiên: tách phương thức có policy sang bean riêng

Thay vì cố làm cho `this` quay về proxy, đưa hành động có policy riêng sang **một Spring-managed service khác** và inject service đó vào caller.

### 6.1. Bean thực hiện approval được bảo vệ

~~~java
package com.example.orders.service;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ProtectedOrderApprovalService {

    private final OrderRepository orders;

    public ProtectedOrderApprovalService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        orders.markApproved(orderId);
    }
}
~~~

`OrderRepository` là interface nghiệp vụ minh họa, do ứng dụng triển khai thật.

### 6.2. Bean orchestration gọi qua injected reference

~~~java
package com.example.orders.service;

import org.springframework.stereotype.Service;

@Service
public class OrderWorkflowService {

    private final ProtectedOrderApprovalService approval;

    public OrderWorkflowService(
            ProtectedOrderApprovalService approval) {
        this.approval = approval;
    }

    public void submitAndApprove(long orderId) {
        // Bước submit nếu được phép theo policy của workflow.
        approval.approve(orderId);
    }
}
~~~

Khi Spring inject bean `ProtectedOrderApprovalService`, reference thông thường đi qua proxy method security tương ứng. Nhờ tách bean, lời gọi `approval.approve(...)` từ `OrderWorkflowService` là **lời gọi xuyên bean**, có thể bị `@PreAuthorize` kiểm tra.

### 6.3. Tách bean chưa đủ nếu workflow còn có đường vòng

Nếu workflow không kiểm tra quyền submit, hoặc repository vẫn có method public mở cho những caller khác, hệ thống có thể có một đường khác bypass. Cần thiết kế:

- Mỗi public application-service entry point có policy phù hợp.
- Hành động nhạy cảm có một boundary được bảo vệ và không có “lối tắt” thay thế.
- Controller không gọi trực tiếp repository để sửa trạng thái nhạy cảm.
- Một process nội bộ cần đặc quyền hệ thống có policy/identity riêng, **không bypass** qua method không được bảo vệ.
- Test tất cả đường đi thực tế, không chỉ gọi trực tiếp một method annotated.

Đặc biệt, **internal call hợp lệ** và **internal bypass vô ý** không giống nhau: ứng dụng có thể có trusted system jobs, nhưng sự tin cậy đó phải được thể hiện bằng một authorization design rõ ràng, không dựa vào thực tế annotation không được gọi.

## 7. Giao dịch và method security: `@Transactional` cũng qua proxy

Một phương thức có thể đồng thời được bảo vệ và quản lý transaction:

~~~java
@Service
public class ProtectedOrderApprovalService {

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // Cập nhật database.
    }
}
~~~

`@Transactional` của Spring trong mô hình proxy cũng phụ thuộc lời gọi qua proxy. Vì vậy nếu gọi self-invocation:

~~~java
this.approve(orderId);
~~~

không những method security có thể không áp dụng, mà transaction advice cũng có thể bị bỏ qua.

Điều này dễ gây lỗi kép: **đường phân quyền bị bỏ qua** và **transaction boundary không có hiệu lực như tưởng tượng**.

Không nên dựa vào thứ tự interceptor cố định giữa method security và transaction advice trong mọi phiên bản/cấu hình. Nếu logic cần rollback/commit và authorization trước side effects, hãy thiết kế ranh giới service và giao dịch rõ ràng, dùng test xác minh.

### 7.1. Tại sao `@PostAuthorize` nguy hiểm với phương thức ghi?

`@PostAuthorize` chạy quyết định authorization **sau khi method invocation** đã thực thi, thường dùng khi policy cần xem `returnObject`. Ví dụ:

~~~java
@PostAuthorize(
    "returnObject == null or returnObject.ownerId == authentication.name"
)
public OrderDto findOrder(long orderId) {
    return repository.findDtoById(orderId);
}
~~~

Với một phương thức có side effect:

~~~java
@PostAuthorize("hasAuthority('SCOPE_orders.approve')")
public void approve(long orderId) {
    repository.markApproved(orderId);
}
~~~

authorization hậu kiểm có thể xảy ra **sau khi thay đổi dữ liệu đã được thực hiện**. Không chọn `@PostAuthorize` làm guard chính cho thao tác ghi dựa trên giả định chắc chắn sẽ rollback nếu access bị từ chối; rollback thực tế phụ thuộc transaction boundaries và cách interceptor được sắp xếp.

Ưu tiên `@PreAuthorize` cho quyền cần có **trước khi thực hiện thao tác**, kết hợp kiểm tra object-level quyền tại thời điểm thích hợp trong transaction. `@PostAuthorize` phù hợp hơn cho những truy vấn an toàn cần so quyền với kết quả, nhưng vẫn phải cân nhắc rủi ro truy xuất dữ liệu hoặc side effects trong method.

## 8. Trường hợp annotation không chạy vì object không do Spring quản lý

### 8.1. Dùng `new` tạo instance

Ví dụ sai:

~~~java
OrderApprovalService approval =
    new OrderApprovalService(repository);

approval.approve(orderId);
~~~

Object được tạo bằng `new` **không tự được Spring proxy**. Dù class có `@Service` hoặc method có `@PreAuthorize`, instance mới này không nhận interceptor do Spring quản lý.

Không được coi annotation trên class là một loại Java runtime check gắn vào mọi instance.

### 8.2. Khắc phục: dependency injection

~~~java
@RestController
public class ApprovalController {

    private final ProtectedOrderApprovalService approval;

    public ApprovalController(
            ProtectedOrderApprovalService approval) {
        this.approval = approval;
    }

    @PostMapping("/api/orders/{id}/approve")
    public void approve(@PathVariable long id) {
        approval.approve(id);
    }
}
~~~

Spring tạo và inject bean; security advice có thể được áp dụng khi controller gọi method qua proxy.

### 8.3. Object được tạo bởi framework khác

Nếu một thư viện, scheduler riêng, object mapper hoặc code thủ công tạo một object không đi qua Spring BeanFactory, object đó không tự nhận Spring AOP proxy. Chỉ có annotation `@Service` trong source class không đủ.

Cần xác định:

- Object có thật sự là Spring-managed bean không?
- Reference caller cầm có phải **proxy** hay raw instance?
- Method được gọi thông qua reference nào?
- Lifecycle của object có được Spring quản lý không?

Không nên “sửa” bằng cách tự tạo một proxy giả hoặc gọi validator JWT trong mọi method. Hãy thiết kế bean boundaries nhất quán.

## 9. Những phương thức khó hoặc không thể proxy trong Spring AOP

### 9.1. `private` methods

Spring AOP proxy không thể intercept lời gọi tới private method theo cách thông thường. Vì private method không được expose qua proxy interface và cũng không thể override bởi class-based proxy, annotation như sau không tạo một public authorization boundary đáng tin:

~~~java
@Service
public class OrderService {

    public void run(long orderId) {
        approveInternal(orderId);
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    private void approveInternal(long orderId) {
        // Không dùng annotation private làm bảo vệ chính.
    }
}
~~~

Cách đúng là đưa policy lên một **method proxiable được gọi qua bean proxy** hoặc tách hành động thành service riêng.

### 9.2. `final` methods và class-based proxies

Spring AOP có thể dùng class-based proxy theo cơ chế subclass (thường nhắc tới CGLIB). Một method `final` không thể override ở subclass; vì vậy class-based proxy **không thể intercept method final đó bằng override**.

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public final void approve(long orderId) {
        // Class-based proxy không override được method final.
    }
}
~~~

Nếu cả class là `final`, subclass proxy không thể kế thừa nó theo cơ chế này.

**Sắc thái quan trọng:** không diễn giải thành “mọi final method đều không thể được bảo vệ trong tất cả cơ chế proxy”. Với **JDK interface-based proxy**, lời gọi được intercept ở method của proxy interface trước khi delegate đến target, nên quy tắc về final của target khác với class-based subclass proxy. Thiết kế ổn định vẫn là dùng các service methods public, không final, trên Spring-managed beans trừ khi đã xác định rõ proxy strategy.

### 9.3. `static` methods

Static methods không được gọi qua bean instance proxy theo mô hình Spring AOP thông thường. Không đặt `@PreAuthorize` trên static method rồi coi đó là bảo vệ runtime.

### 9.4. Non-public methods

Với **JDK interface proxy**, phần giao diện có thể expose các public interface methods. Với class-based proxies, khả năng xử lý package-private/protected methods còn tùy phiên bản Spring, visibility và kỹ thuật proxy. Vì vậy không nên khái quát rằng tất cả non-public methods đều được bảo vệ hoặc đều bị bỏ qua.

Để có contract method-security dễ dự đoán, ưu tiên:

- Public method.
- Spring-managed bean.
- Proxy strategy được xác định.
- Lời gọi từ một bean khác qua injected reference.
- Test đường đi security thực tế.

### 9.5. Bảng các trường hợp

| Trường hợp | Proxy-based method security có áp dụng? | Cần làm gì |
|---|---|---|
| Public method của Spring bean, được bean khác gọi qua proxy | Thường có | Bật `@EnableMethodSecurity` và đúng annotation |
| Public method được gọi bằng `this.method()` trong cùng target | Thường **không** | Tách bean hoặc thiết kế external proxy call |
| Private method annotated | Không có proxy interception đáng tin | Đưa guard ra public boundary |
| Static method annotated | Không có instance proxy interception | Không dùng static làm method-security boundary |
| Final method với subclass/class-based proxy | Không thể override/intercept theo cơ chế đó | Bỏ final hoặc đổi architecture |
| Final target method với JDK interface proxy | Có thể được intercept qua interface proxy | Kiểm chứng proxy type và injection |
| Instance được tạo bằng `new` | Không có Spring proxy | Dùng dependency injection/bean |
| Gọi trong constructor/khởi tạo target | Không nên kỳ vọng method advice chạy | Dời nghiệp vụ sang bean đã khởi tạo |
| Object ngoài Spring container | Không tự có proxy | Đưa vào Spring lifecycle hoặc explicit boundary khác |
| Method security chưa bật | Không | Cấu hình `@EnableMethodSecurity` |
| Annotation family chưa bật | Không nhất thiết | Bật `securedEnabled`/`jsr250Enabled` khi dùng |
| Call đi qua proxy nhưng rule thiếu quyền | Có, và bị từ chối | Kiểm tra policy/Authentication |

## 10. JDK dynamic proxy và class-based proxy

### 10.1. JDK interface proxy

Nếu service triển khai interface, Spring AOP có thể dùng JDK dynamic proxy:

~~~java
public interface OrderApprovalOperations {
    void approve(long orderId);
}

@Service
public class OrderApprovalService implements OrderApprovalOperations {

    @Override
    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void approve(long orderId) {
        // ...
    }
}
~~~

Caller nên phụ thuộc interface:

~~~java
@Service
public class OrderWorkflowService {

    private final OrderApprovalOperations approval;

    public OrderWorkflowService(OrderApprovalOperations approval) {
        this.approval = approval;
    }

    public void perform(long id) {
        approval.approve(id);
    }
}
~~~

JDK proxy expose các interface methods, không tự expose toàn bộ method chỉ có trong concrete class. Nếu inject bằng concrete implementation trong khi bean thực tế là JDK proxy chỉ triển khai interface, có thể gây lỗi type/injection.

### 10.2. Class-based proxy

Class-based proxy có thể expose các proxiable methods của concrete class theo proxy strategy. Nhưng nó không khắc phục `this.method()` self-invocation, final method hoặc private method.

Spring Boot có thể có cấu hình proxy-target-class tùy phiên bản và auto configuration; đừng dựa vào giả định chung mà không kiểm tra ứng dụng thực tế.

### 10.3. Annotation đặt trên interface hay implementation?

Spring Security method security hỗ trợ nhiều kiểu đặt annotation trên method/interface/class, có quy tắc tìm metadata qua type hierarchy. Khi interface và implementation có annotations chồng chéo, hoặc có nhiều interface mang policy khác nhau, kết quả có thể gây bất ngờ, thậm chí lỗi cấu hình.

Để dễ bảo trì:

- Chọn một quy ước rõ nơi đặt policy.
- Tránh các annotation có nghĩa xung đột trên nhiều interface.
- Không nghĩ rằng đổi proxy strategy sẽ luôn giữ nguyên mọi trường hợp metadata resolution.
- Test lời gọi qua interface reference và concrete bean như ứng dụng thực tế.

**Điều không đổi:** dù JDK hay class-based proxy, self-invocation trên target vẫn không đi qua proxy.

## 11. Kotlin và mặc định `final`

Trong Kotlin, class/method thường là `final` theo mặc định nếu không dùng `open` hoặc plugin mở class phù hợp.

Ví dụ khái niệm:

~~~kotlin
@Service
class OrderApprovalService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    fun approve(orderId: Long) {
        // ...
    }
}
~~~

Nếu class-based proxy cần subclass nhưng class/method vẫn final, interceptor có thể không được áp dụng đúng. Với Spring Boot Kotlin, thường dùng **kotlin-spring/all-open plugin** để mở các Spring-annotated classes/methods theo cấu hình.

Tuy nhiên plugin **không giải quyết self-invocation**: ngay cả method đã proxiable, lời gọi nội bộ trên `this` vẫn không đi qua proxy theo Spring AOP proxy mặc định.

Với Kotlin/Java, lựa chọn thiết kế tách service nghiệp vụ có trách nhiệm và gọi xuyên bean thường dễ hiểu hơn việc phụ thuộc các thủ thuật lấy proxy hiện tại.

## 12. Constructor và `@PostConstruct`: thời điểm bean chưa sẵn sàng

### 12.1. Lời gọi trong constructor

Ví dụ:

~~~java
@Service
public class OrderService {

    public OrderService() {
        initializeProtectedData();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.admin')")
    public void initializeProtectedData() {
        // Không trông cậy method security ở constructor.
    }
}
~~~

Constructor đang khởi tạo **target object** trước khi Spring hoàn tất vòng đời proxy. Không dựa vào `@PreAuthorize` để bảo vệ những lời gọi được kích hoạt từ constructor.

### 12.2. `@PostConstruct` hoặc callback lifecycle

Ví dụ:

~~~java
@PostConstruct
void init() {
    refreshPrivilegedState();
}
~~~

Nếu callback tự gọi method annotated trên chính bean trong quá trình khởi tạo, đó vẫn là **lời gọi nội bộ** và có thể xảy ra trước khi proxy/method security boundary sẵn sàng. Không dùng method security để “xác thực” một công việc khởi tạo ứng dụng không có request principal.

Nếu thực sự có bootstrapping đặc quyền, định nghĩa một quy trình trusted startup riêng với quyền hệ thống rõ ràng, không tạo đường vòng dẫn từ endpoint của user đến những công việc đó.

### 12.3. Scheduled jobs và application events

Một scheduled job hoặc event listener có thể gọi service method bảo vệ theo hai kiểu:

- Qua bean proxy: method-security interceptor có thể chạy, nhưng cần xem **SecurityContext** của thread đó.
- Trong cùng target bean hoặc không có principal: self-invocation/thiếu authentication có thể gây bypass hoặc deny.

Không suy luận “job chạy trên server nên đương nhiên được quyền admin”. Nếu batch job cần quyền đặc biệt, cần thiết kế system identity/authorization và task boundary rõ ràng, hạn chế tiếp cận từ untrusted requests.

## 13. Async execution và `SecurityContext`

Spring Security Servlet thường lưu `SecurityContext` theo ngữ cảnh thread đang xử lý request. Một service method có `@Async` hoặc một task chạy trên executor khác có thể gặp tình huống **authentication không được tự truyền sang thread mới**.

Ví dụ:

~~~java
@Service
public class OrderExportService {

    @Async
    @PreAuthorize("hasAuthority('SCOPE_orders.export')")
    public void export(long orderId) {
        // ...
    }
}
~~~

Ở trường hợp này có **hai mối quan tâm độc lập**:

1. `@Async` và `@PreAuthorize` có được gọi **qua proxy** hay không.
2. SecurityContext của caller có được **propagate** tới nơi method-security decision thực sự được thực hiện hay không.

Thứ tự advice, proxy layers và thread nào chạy evaluation có thể phụ thuộc cấu hình/phiên bản. Vì vậy không cam kết rằng chỉ thêm hai annotation sẽ tự động giữ đúng Authentication ở worker thread.

Spring Security có các cơ chế **security context propagation** như `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`, nhưng chúng phải được cấu hình phù hợp với threat model, đặc biệt khi task chạy sau khi request kết thúc.

**Không dùng một SecurityContext global/static chung cho tất cả tasks.** Nếu task cần một danh tính bền vững, có thể truyền identity DTO/authorization decision được thiết kế riêng, hoặc sử dụng một system principal đã được quản trị. Không cho task chạy với quyền cao hơn chỉ vì không còn request authentication.

## 14. Những trường hợp annotation tồn tại nhưng cơ chế bảo mật chưa được bật

### 14.1. Thiếu `@EnableMethodSecurity`

Thêm:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) {
    return repository.findDtoById(id);
}
~~~

không đảm bảo annotation hoạt động nếu ứng dụng chưa bật method security hoặc không có configuration tương đương.

Phải xác nhận config được component scan/import và Spring thực sự tạo method interceptors.

### 14.2. Dùng `@Secured` nhưng chưa bật

~~~java
@Secured("ROLE_ORDER_ADMIN")
public void deleteOrder(long id) {
    // ...
}
~~~

`@EnableMethodSecurity` có thuộc tính `securedEnabled`; trong cấu hình phổ biến nó **không tự bật `@Secured`** trừ khi được chọn tường minh.

Tương tự, `@RolesAllowed` thuộc JSR-250 cần bật `jsr250Enabled` nếu muốn sử dụng annotation family đó.

### 14.3. Annotation nằm trên helper không phải Spring bean

Một helper class được ứng dụng tự tạo:

~~~java
public class OrderPolicyHelper {

    @PreAuthorize("hasAuthority('SCOPE_orders.admin')")
    public void doAdminWork() {
        // ...
    }
}
~~~

không được AOP intercept chỉ vì chứa annotation. Muốn bảo vệ bằng Spring method security, hãy đặt method ở Spring-managed bean và gọi qua proxy; hoặc sử dụng một authorization service/programmatic authorization phù hợp cho code không chạy trong Spring context.

### 14.4. Không có authority mong đợi

Nếu proxy/annotation chạy nhưng policy từ chối, đây **không phải annotation bị bỏ qua**. Ví dụ JWT có `scope: "orders.read"` nhưng rule cần `SCOPE_orders.write`, kết quả đúng thường là **403**.

Cần phân biệt:

- **Annotation không được intercept:** phương thức có thể chạy dù thiếu quyền.
- **Annotation đã chạy và deny:** caller không có authority; exception/403 là tín hiệu bảo vệ hoạt động.
- **JWT không hợp lệ:** filter authentication trả 401 trước khi controller/service.
- **Annotation chạy trong thread không có context:** có thể deny hoặc lỗi, cần sửa context propagation.

## 15. Truy cập JWT principal trong method security

### 15.1. Authorities sau JWT conversion

JWT:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-42"
}
~~~

Thông thường Resource Server tạo authority `SCOPE_orders.read`. `@PreAuthorize` dùng:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public OrderDto load(long id) { ... }
~~~

Nếu ứng dụng tùy chỉnh `JwtAuthenticationConverter`, tên authorities có thể khác. Phải thống nhất policy với conversion; không sửa rule thành `permitAll` khi thiếu authority chỉ để request chạy.

### 15.2. Dùng identity/tenant để kiểm tra quyền dữ liệu

Một request đến:

~~~http
GET /api/orders/42
Authorization: Bearer <ACCESS_TOKEN>
~~~

và token có `tenant_id = tenant-42`. Scope `orders.read` chưa tự chứng minh order 42 thuộc tenant đó hoặc user có quyền trên order.

Method security có thể hỏi một policy bean:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_orders.read') " +
    "and @orderPolicy.canRead(authentication, #orderId)"
)
public OrderDto loadOrder(long orderId) {
    return repository.findOrderDto(orderId);
}
~~~

Policy:

~~~java
package com.example.orders.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component("orderPolicy")
public class OrderPolicy {

    private final OrderAccessRepository access;

    public OrderPolicy(OrderAccessRepository access) {
        this.access = access;
    }

    public boolean canRead(Authentication auth, long orderId) {
        if (auth == null
                || !(auth.getPrincipal() instanceof Jwt jwt)) {
            return false;
        }

        String subject = jwt.getSubject();
        Object tenantClaim = jwt.getClaim("tenant_id");

        if (subject == null || subject.isBlank()
                || !(tenantClaim instanceof String tenant)
                || tenant.isBlank()) {
            return false;
        }

        return access.canReadOrder(subject, tenant, orderId);
    }
}
~~~

`OrderAccessRepository` là thành phần nghiệp vụ minh họa. Nó phải kiểm tra quyền hiện thời/owner/tenant theo dữ liệu đáng tin, không chỉ so order ID do client gửi.

**Một method-level policy muốn bảo vệ đọc dữ liệu phải được gọi qua proxy.** Nếu một method khác trong cùng service gọi `this.loadOrder(...)`, cả việc kiểm tra scope lẫn `orderPolicy.canRead(...)` trong annotation có thể bị bỏ qua.

### 15.3. Parameter names trong SpEL

Biểu thức `#orderId` cần Spring Security resolve tên tham số method. Với Java, tùy build có thể cần compiler option `-parameters`, hoặc cách khai báo parameter names được framework hỗ trợ.

Nếu sai tên tham số, expression có thể nhận null và deny/throw, gây lỗi khó tìm. Kiểm thử method security bằng **Spring bean thật**, không chỉ compile source.

### 15.4. Với client credentials token

`sub` trong access token không phải lúc nào cũng là người dùng. Với client credentials, subject có thể đại diện cho client/service theo profile. Nếu policy cần xác định *người dùng thực*, phải phân biệt token type/grant và claims đúng hợp đồng.

Không tự biến machine principal thành owner của một order người dùng, hoặc tin `email`/`preferred_username` là identity key bảo mật.

## 16. Cách giải quyết self-invocation: ưu tiên và đánh đổi

### 16.1. Cách 1 — Tách bean (khuyến nghị)

~~~text
Controller
  |
  v
OrderWorkflowService proxy/bean
  |
  v
ProtectedOrderApprovalService proxy
  |
  v
@PreAuthorize -> approve()
~~~

Ưu điểm:

- Rõ trách nhiệm nghiệp vụ.
- Test dễ.
- Không phụ thuộc chi tiết proxy đang dùng.
- Dễ ghép transaction/authorization boundaries.
- Giảm nguy cơ gọi nhầm helper không được bảo vệ.

Hạn chế: thêm một số class/bean, cần thiết kế domain boundaries hợp lý.

### 16.2. Cách 2 — Di chuyển guard lên public entry point

Nếu một workflow **luôn** được phép chạy toàn bộ hoặc bị từ chối toàn bộ, có thể bảo vệ method bên ngoài:

~~~java
@Service
public class ApprovalWorkflowService {

    @PreAuthorize("hasAuthority('SCOPE_orders.approve')")
    public void submitAndApprove(long orderId) {
        prepare(orderId);
        approveInternal(orderId);
    }

    private void approveInternal(long orderId) {
        // Không dùng private method này như boundary riêng.
    }
}
~~~

Điều này hợp lệ **chỉ nếu tất cả đường vào public workflow đều đòi cùng quyền** và không còn public method khác có thể gọi `approveInternal` không được bảo vệ.

Ưu điểm là đơn giản. Rủi ro là sau này có thêm một public entry point mà quên áp quyền. Vì vậy test và code review cần xác định đường đi đến side effects nhạy cảm.

### 16.3. Cách 3 — Self-injection hoặc gọi proxy qua context

Một số dự án dùng self-injection qua interface proxy hoặc `AopContext.currentProxy()`. Những cách này có thể làm lời gọi nội bộ quay qua proxy nếu được cấu hình đúng, nhưng thường:

- Tăng coupling vào AOP infrastructure.
- Dễ tạo circular dependency hoặc vấn đề bean initialization.
- Làm code khó đọc/test.
- Có thể không hoạt động nếu cấu hình expose-proxy/proxy strategy thay đổi.
- Che một domain design chưa rõ ràng.

Không xem đây là mặc định để sửa self-invocation. **Tách bean hoặc chuyển policy ra entry point rõ ràng** thường là lựa chọn dễ bảo trì hơn.

### 16.4. Cách 4 — AspectJ weaving

Spring AOP proxy là mô hình mặc định. **AspectJ weaving** về mặt kỹ thuật có thể xử lý các join points như self-invocation mà proxy không chặn, nếu ứng dụng được tích hợp và cấu hình đầy đủ.

Tuy nhiên không thể chỉ thêm `@EnableMethodSecurity` rồi mặc định có weaving. Phải có dependencies, weaving setup và khả năng tương thích với interceptor/method security mà ứng dụng sử dụng.

Vì độ phức tạp vận hành/test, chỉ cân nhắc AspectJ nếu có lý do kiến trúc rõ. Không nên giới thiệu như một “annotation fix” không cần cấu hình.

## 17. Kiểm thử để chứng minh annotation thực sự chạy

### 17.1. Không unit test bằng `new Service()` nếu muốn kiểm tra AOP

Ví dụ:

~~~java
OrderApprovalService service =
    new OrderApprovalService(repository);

service.approve(42);
~~~

Đây là **unit test method body**, không phải test Spring proxy. Việc `@PreAuthorize` không có hiệu lực trong test này không chứng minh Spring Security sai; object đã không đi qua Spring context.

Tương tự, một Mockito mock thay thế hoàn toàn service có thể không chạy method security của method thật.

### 17.2. Test qua Spring-managed bean

Ví dụ integration test:

~~~java
package com.example.orders.security;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

@SpringBootTest
class OrderApprovalSecurityTest {

    @Autowired
    ProtectedOrderApprovalService approval;

    @Test
    @WithMockUser(authorities = "SCOPE_orders.read")
    void deniesWhenApproveScopeMissing() {
        assertThatThrownBy(() -> approval.approve(42))
            .isInstanceOf(AccessDeniedException.class);
    }
}
~~~

Đây là ví dụ test ý tưởng: dự án cần `spring-security-test` và các beans/repository test phù hợp để Spring context khởi tạo. Khi policy hoạt động, lời gọi phải bị deny **trước khi phương thức ghi dữ liệu chạy**.

Import/test helper:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 17.3. Test đường đi self-invocation

Cần test **public entry points thực tế** thay vì chỉ gọi method annotated trực tiếp.

Ví dụ anti-pattern ban đầu:

~~~java
public void submitAndApprove(long id) {
    this.approve(id);
}

@PreAuthorize("hasAuthority('SCOPE_orders.approve')")
public void approve(long id) {
    repository.markApproved(id);
}
~~~

Nếu test chỉ gọi `approval.approve(...)` qua proxy, nó sẽ thấy bảo vệ hoạt động. Nhưng endpoint thực tế lại gọi `submitAndApprove(...)`, có thể bypass.

Vì thế test cần gọi `submitAndApprove(...)` trong một context thiếu `SCOPE_orders.approve` và xác nhận **không có side effect approval**. Nếu thấy database được cập nhật, đó là dấu hiệu đường đi nội bộ bypass.

Trong kiến trúc sau khi tách bean, test tương tự phải cho thấy lời gọi qua injected `ProtectedOrderApprovalService` bị từ chối.

### 17.4. Ma trận kiểm thử

| Tình huống | Điều cần xác minh |
|---|---|
| Không bật `@EnableMethodSecurity` | Phát hiện cấu hình thiếu, không đưa vào production |
| Gọi annotated method qua Spring bean proxy | Thiếu authority bị deny |
| Gọi cùng method qua `this.method()` | Không dựa vào annotation ở method con; test phát hiện bypass |
| Object tạo bằng `new` | Không coi annotation là runtime guard |
| Private annotated method | Không sử dụng như security boundary |
| Final method dưới class-based proxy | Xác định khả năng intercept; tránh kiến trúc này |
| JDK proxy và interface injection | Caller thực sự gọi qua interface proxy |
| Annotation có nhưng auth thiếu scope | Deny; thường 403 khi qua HTTP |
| Token Bearer sai signature/issuer/audience | 401 trước method invocation |
| JWT đúng nhưng tenant/owner không phù hợp | Deny theo policy |
| Method được gọi từ scheduled/async thread | Authentication context đúng hoặc fail closed |
| `@PostAuthorize` cho method có side effects | Không dùng như guard ghi chính |
| Controller khác hoặc message listener gọi service | Vẫn đi qua protected boundary |

### 17.5. `@WithMockUser` không kiểm tra JWT decoder

`@WithMockUser` có thể tạo mock Authentication với authorities cho method-security tests. Nó **không** xác minh JWT signature, issuer, audience, Bearer header hay `JwtAuthenticationConverter`.

Để kiểm tra toàn bộ Resource Server, cần thêm integration tests gửi **JWT test thực** qua security filter chain, với issuer/test signing keys/JWKS phù hợp. Cần phân biệt:

- **Token invalid** → authentication failure, thường 401.
- **Token valid but insufficient scope** → method/HTTP authorization failure, thường 403.
- **Annotation bypass** → method body chạy dù thiếu authority, thường là security bug.

## 18. Chẩn đoán khi annotation có vẻ không được áp dụng

### 18.1. Câu hỏi đầu tiên: request có đi qua Spring proxy không?

Một trình tự chẩn đoán hữu ích:

1. Đã bật `@EnableMethodSecurity` ở cấu hình Spring được load chưa?
2. Annotation family có bật không? Ví dụ `@Secured`, JSR-250.
3. Service có phải **Spring-managed bean** không?
4. Caller có nhận bean từ DI hay tạo bằng `new`?
5. Method được gọi từ bean khác qua proxy, hay từ `this.method()`?
6. Method có `private`, `static`, `final`, hoặc class là `final` không?
7. Proxy là interface-based hay class-based?
8. Có gọi method khi constructor/`@PostConstruct` đang chạy không?
9. Với async/scheduled task, SecurityContext có tồn tại và đúng principal không?
10. Test có thực sự gọi đường đi cần bảo vệ và đo side effect không?

Không nên khắc phục vấn đề bằng cách tăng quyền cho token hoặc bỏ `@PreAuthorize`.

### 18.2. Có thể quan sát AOP proxy trong môi trường phát triển

Một đoạn diagnostic tạm thời:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(orderApprovalService);
boolean jdk = AopUtils.isJdkDynamicProxy(orderApprovalService);
boolean cglib = AopUtils.isCglibProxy(orderApprovalService);
~~~

Các helper chỉ giúp xác định **reference hiện tại** có phải AOP proxy và loại proxy; chúng không tự chứng minh một phương thức cụ thể đã được method-security advisor chặn. Phải kết hợp test thiếu quyền và quan sát side effects.

Không đưa chi tiết proxy internals hoặc principal/claims nhạy cảm vào log production khi không cần thiết.

### 18.3. Bật log ở local/dev

`application.yml` có thể bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.aop: DEBUG
~~~

Mức log và nội dung hiển thị tùy phiên bản. Nếu cần sâu hơn có thể điều chỉnh logging trong môi trường test, nhưng không bật verbose logs lâu dài ở production khi chưa đánh giá rủi ro lộ token, headers, claims hoặc request metadata.

### 18.4. Phân biệt bị chặn với không chạy

Giả sử endpoint trả 403 và controller không được gọi. Đây có thể là HTTP `AuthorizationFilter` đã từ chối trước service; điều đó **không xác nhận method security đã chạy**.

Muốn chứng minh service guard, test gọi service qua **Spring-managed proxy** trong context có Authentication nhưng thiếu authority, và xác nhận method body không được thực hiện. Đồng thời test cả route nội bộ mà production có thể gọi.

### 18.5. 200 response không chứng minh guard đã chạy

Một request đủ quyền có thể trả 200 trong cả hai tình huống:

- Method security hoạt động và cho phép.
- Method security bị bypass nhưng nghiệp vụ vẫn chạy.

Vì vậy test quan trọng nhất là **negative test**: thiếu scope, sai tenant, caller không có quyền vẫn bị từ chối và không tạo side effect.

## 19. Ví dụ tổng hợp: bảo vệ đọc đơn hàng không bị self-invocation bypass

### 19.1. Thiết kế không an toàn

~~~java
@Service
public class OrderFacade {

    public OrderDto getOrder(long orderId) {
        // Dù caller chỉ có quyền authenticated, policy bên dưới có thể bị bypass.
        return this.readProtected(orderId);
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto readProtected(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

Nếu `getOrder` không có policy tương đương, request từ một endpoint chỉ cần `authenticated()` có thể đi tới readProtected không qua advice.

### 19.2. Thiết kế tách bean với business boundary rõ ràng

~~~java
@Service
public class ProtectedOrderQueryService {

    private final OrderRepository repository;

    public ProtectedOrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.read') " +
        "and @orderPolicy.canRead(authentication, #orderId)"
    )
    public OrderDto load(long orderId) {
        return repository.findOrderDto(orderId);
    }
}
~~~

Facade:

~~~java
@Service
public class OrderFacade {

    private final ProtectedOrderQueryService query;

    public OrderFacade(ProtectedOrderQueryService query) {
        this.query = query;
    }

    public OrderDto getOrder(long orderId) {
        return query.load(orderId);
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrderFacade facade;

    public OrdersController(OrderFacade facade) {
        this.facade = facade;
    }

    @GetMapping("/{id}")
    public OrderDto get(@PathVariable long id) {
        return facade.getOrder(id);
    }
}
~~~

Trong hệ thống thật, mỗi class cần imports tương ứng (`Service`, `PreAuthorize`, `RestController`, `RequestMapping`, `GetMapping`, `PathVariable`); các kiểu `OrderDto`, `OrderRepository` phải do ứng dụng định nghĩa.

Đường gọi:

~~~text
HTTP Controller
    |
    v
OrderFacade bean
    |
    v
ProtectedOrderQueryService proxy
    |
    +-- @PreAuthorize:
    |      SCOPE_orders.read
    |      AND orderPolicy.canRead(...)
    |
    v
Target load(orderId)
    |
    v
Repository
~~~

Bất kể controller có quyền nào khác, service query không trả dữ liệu khi thiếu scope hoặc policy order từ chối, **miễn lời gọi thực sự đi qua proxy** và không có đường vòng truy xuất repository nhạy cảm.

### 19.3. Lưu ý về data leakage và TOCTOU

Ngay cả với `@PreAuthorize`, một policy kiểm tra owner/tenant rồi sau đó service load bản ghi trong transaction khác có thể có **time-of-check/time-of-use** nếu dữ liệu ownership thay đổi đồng thời. Với nghiệp vụ nhạy cảm, nên thiết kế truy vấn ràng buộc tenant/owner trong cùng transaction và kiểm tra điều kiện ở database/service đúng thời điểm.

Method security là một **authorization boundary**, không thay thế chính sách dữ liệu, isolation và transaction correctness.

## 20. Những ngộ nhận cần tránh

### “Annotation có trên method nghĩa là mọi lời gọi đều bị kiểm tra”

Không đúng trong proxy mode. Lời gọi phải đi qua AOP proxy hoặc được xử lý bởi một cơ chế interception khác đã được triển khai đầy đủ.

### “Đã inject service bằng Spring thì self-invocation cũng được intercept”

Không đúng. Bean có proxy nhưng `this.method()` chạy trên target, không đi ra proxy.

### “`@PreAuthorize` trên private method bảo vệ logic private”

Không. Private method không phải điểm cắt đáng tin cho Spring AOP proxy.

### “Dùng class-based proxy sẽ giải quyết self-invocation”

Không. CGLIB/class-based proxy cũng có giới hạn self-invocation theo mô hình Spring AOP proxy thông thường.

### “Kotlin final method vẫn luôn được intercept”

Không nên giả định. Class-based proxies cần khả năng subclass/override; xem cấu hình all-open/kotlin-spring và test thực tế.

### “Method security tự chạy trong object được tạo bằng `new`”

Không. Instance ngoài Spring BeanFactory không tự nhận proxy.

### “`@PostAuthorize` bảo vệ mọi thao tác ghi trước side effects”

Không. Nó quyết định sau method invocation, nên không phải guard chính cho những hành động cần chặn trước thay đổi trạng thái.

### “Method security có thể thay issuer/audience validation”

Không. JWT phải được xác minh trước khi claims/authorities được tin.

### “Đủ scope nghĩa là sở hữu mọi order”

Không. Phải kiểm tra tenant, ownership/ACL và entitlement nghiệp vụ.

### “Test method trực tiếp bằng `new` là đã test security”

Không. Cần test qua Spring-managed proxy với negative cases.

### “Nếu HTTP rule trả 403 thì method security chắc chắn hoạt động”

Không. HTTP filter có thể từ chối trước khi service được gọi; cần test riêng method guard.

## 21. Những điểm cần ghi nhớ

- `@EnableMethodSecurity` bật method-security infrastructure; annotation trên source code **không tự hoạt động** nếu cấu hình không kích hoạt đúng.
- Trong **Spring AOP proxy mode**, lời gọi được bảo vệ khi đi **từ caller qua proxy tới target method**. `this.method()` ở cùng target bean **không quay lại proxy**.
- Các trường hợp cần cảnh giác: self-invocation, object tạo bằng `new`, private/static methods, final methods với class-based proxy, constructors, lifecycle callbacks, async threads, multiple proxy types và annotation family chưa bật.
- **Giải pháp ưu tiên** cho hành động nghiệp vụ có policy riêng là **tách method được bảo vệ sang Spring bean khác** rồi gọi qua injected reference, hoặc bảo vệ một public entry point phù hợp với toàn bộ workflow.
- `@PreAuthorize` thích hợp để kiểm tra quyền **trước side effect**; `@PostAuthorize` có ngữ nghĩa hậu kiểm, không dùng tùy tiện cho thao tác ghi.
- HTTP security và method security bổ sung cho nhau. Bearer token phải đúng issuer, audience, signature, time và token profile; method security dùng Authentication/authorities đã tin cậy và còn cần kiểm tra tenant/owner.
- Kiểm thử **đường đi production thực** và **negative cases** mới phát hiện annotation bị bypass; test chỉ với caller đủ quyền hoặc test bằng `new` là chưa đủ.
- Không khắc phục bypass bằng cách tăng scope, bỏ validation hoặc cho service tin input do client tự khai báo.

### Tài liệu tham khảo

- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Framework Reference — Spring AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Security Reference — Servlet Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security API — EnableMethodSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html)
- [Spring Security API — PreAuthorize](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/prepost/PreAuthorize.html)
- [Spring Framework API — AopUtils](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aop/support/AopUtils.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)

