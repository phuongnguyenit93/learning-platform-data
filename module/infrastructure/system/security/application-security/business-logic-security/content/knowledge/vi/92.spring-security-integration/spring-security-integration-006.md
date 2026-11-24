# Spring Security test support

## 1. Mục tiêu trong bảo mật logic nghiệp vụ

Spring Security test support cung cấp công cụ tạo ngữ cảnh xác thực, gửi request qua bộ lọc bảo mật và kiểm tra kết quả trong bài kiểm thử Spring. Trong chương **Spring Security Integration**, mục tiêu sử dụng các công cụ này là chứng minh rằng người dùng chỉ thực hiện được hành động phù hợp với quyền, đối tượng và trạng thái nghiệp vụ của họ.

Một API phê duyệt đơn hàng có thể yêu cầu `order:approve`, nhưng quyền đó chưa đủ để quyết định mọi trường hợp. Người phê duyệt còn phải thuộc đúng tenant, không phải người tạo đơn và chỉ được duyệt đơn đang chờ duyệt. Hai yêu cầu đến đồng thời cũng không được tạo hai nghiệp vụ chi tiền. Đây là các business invariant: điều kiện phải luôn đúng bất kể request xuất phát từ màn hình, API trực tiếp hay một đường gọi service khác.

Sau bài học, bạn có thể:

- Chọn giữa kiểm thử quy tắc miền, method security, HTTP security và kiểm thử transaction.
- Dùng `@WithMockUser`, request post-processor, `@WithUserDetails` và principal tùy chỉnh đúng mục đích.
- Tách nguyên nhân bị từ chối do CSRF, thiếu xác thực, thiếu quyền và sai quy tắc nghiệp vụ.
- Kiểm tra cả phản hồi lẫn trạng thái dữ liệu và tác dụng phụ.
- Thiết kế tình huống thay ID, bỏ qua bước, sửa giá, phát lại và tranh chấp đồng thời.

Phạm vi ví dụ là ứng dụng Servlet với Spring MVC, JUnit Jupiter và Java 17 trở lên. Ví dụ sử dụng các API quen thuộc của Spring Security 6/7 như `SecurityFilterChain` và `@EnableMethodSecurity`; không sử dụng `WebSecurityConfigurerAdapter`. Với ứng dụng WebFlux, dùng bộ công cụ tương ứng cho `WebTestClient` và reactive security context thay vì áp dụng nguyên xi `MockMvc`.

## 2. Xác định điều cần chứng minh trước khi chọn annotation

Xét hành động:

```http
POST /orders/101/approve
```

Quy tắc ví dụ:

1. Người gọi đã xác thực và có authority `order:approve`.
2. Đơn và người gọi thuộc cùng tenant.
3. Người tạo không tự phê duyệt đơn của mình, kể cả có quyền phê duyệt.
4. Chỉ cho phép chuyển từ `SUBMITTED` sang `APPROVED`.
5. Request bị từ chối không thay đổi đơn hoặc tạo sự kiện phê duyệt.
6. Hệ thống thực tế phải bảo đảm một lần chuyển trạng thái hợp lệ không sinh tác dụng phụ trùng khi retry hoặc chạy đồng thời.

Một ma trận tình huống giúp phát hiện những tổ hợp mà kiểm thử theo vai trò đơn thuần dễ bỏ sót:

| Người gọi và điều kiện | Đối tượng/trạng thái | Kết quả trong hợp đồng ví dụ | Điều cần kiểm tra thêm |
|---|---|---|---|
| Chưa xác thực, có CSRF hợp lệ | Đơn đang chờ duyệt | `401` | Dữ liệu và sự kiện giữ nguyên |
| Đã xác thực, thiếu `order:approve` | Đơn cùng tenant | `403` | Service không thực hiện thay đổi |
| Có quyền, khác tenant | Đơn đang chờ duyệt | `403` | Không lộ dữ liệu đơn |
| Có quyền, chính là người tạo | Đơn đang chờ duyệt | `403` | Quy tắc phân tách nhiệm vụ vẫn được giữ |
| Có quyền, đúng quan hệ | Đơn `DRAFT` | `409` | Không bỏ qua bước gửi duyệt |
| Có quyền, đúng quan hệ | Đơn `SUBMITTED` | `204` | Đơn thành `APPROVED`, một sự kiện |
| Đã duyệt thành công, gửi lại | Đơn `APPROVED` | `409` trong ví dụ tối giản | Không tạo sự kiện thứ hai |
| Đã xác thực, thiếu/sai CSRF | Request thay đổi trạng thái | `403` | Bị chặn trước nghiệp vụ |
| Hai người duyệt đồng thời | Cùng đơn `SUBMITTED` | Theo hợp đồng cạnh tranh | Chỉ một lần chuyển trạng thái thành công |

Các mã HTTP trên là lựa chọn của ví dụ. Ứng dụng có thể trả `404` cho tài nguyên không được phép nhìn thấy, hoặc trả lại kết quả cũ cho một retry có idempotency key hợp lệ. Hãy kiểm thử hợp đồng cụ thể của ứng dụng; không coi mọi hệ thống đều có cùng mã phản hồi.

## 3. Các tầng kiểm thử bổ sung cho nhau

| Tầng | Cách thực hiện | Bằng chứng nhận được | Phần còn phải kiểm tra ở tầng khác |
|---|---|---|---|
| Quy tắc miền | JUnit gọi domain object hoặc policy | Chuyển trạng thái, giới hạn tiền, phân tách nhiệm vụ | Bộ lọc và proxy Spring |
| Method security | Gọi bean lấy từ Spring, có test security context | `@PreAuthorize` thực sự chặn lời gọi | Routing, CSRF và HTTP mapping |
| HTTP security | `MockMvc` với filter chain và service thật | Request đi qua xác thực giả lập, kiểm tra quyền và controller | Chữ ký token thật, giao dịch DB thật |
| Tích hợp dữ liệu | Service thật, database và transaction thật | Rollback, constraint, khóa, idempotency bền vững | Hệ thống ngoài và luồng xác thực đầy đủ |
| Luồng tích hợp xác thực | Request có credential/token thật trong môi trường test | Decoder, converter, cấu hình issuer và authority | Mọi quy tắc miền nếu chưa có tình huống tương ứng |

Nếu mock service trong bài kiểm thử controller, kết quả chỉ chứng minh phần controller và bộ lọc được nạp. Khi cần chứng minh quy tắc “không tự phê duyệt”, service hoặc policy chứa quy tắc ấy phải chạy thật. Mock một repository để cô lập method security là hợp lý; mock luôn quyết định cấp quyền rồi kết luận quyền theo đối tượng đã đúng thì không đủ bằng chứng.

## 4. Dependency và kết nối MockMvc với bảo mật

Với dự án Maven dùng Spring Boot dependency management, phần dependency test thường gồm:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Ứng dụng còn cần các dependency web và security tương ứng. Để BOM của dự án quản lý phiên bản; khi không dùng Boot, phải tự quản lý một tập phiên bản Spring tương thích. Không chọn một phiên bản `spring-security-test` tách rời bộ Spring Security đang chạy.

Với `MockMvc` dựng thủ công từ web application context, áp dụng `springSecurity()` để tích hợp bộ lọc bảo mật và hỗ trợ test security context. [Tài liệu thiết lập MockMvc của Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html).

```java
mvc = MockMvcBuilders.webAppContextSetup(context)
        .apply(springSecurity())
        .build();
```

Trong bài kiểm thử ứng dụng thực, context cần nạp **cấu hình bảo mật của ứng dụng**. Với Spring Boot, có thể nạp ứng dụng bằng `@SpringBootTest` và dựng `MockMvc` từ context như trên; hoặc dùng cơ chế tự cấu hình MockMvc phù hợp phiên bản Boot. Khi dùng một test slice như `@WebMvcTest`, phải kiểm tra những cấu hình, policy và bean nghiệp vụ nào thực sự được nạp.

Method security cần được bật riêng bằng `@EnableMethodSecurity`. Dependency Spring Security hay việc nạp Spring Boot không tự bảo đảm annotation trên service đã có hiệu lực. [Tài liệu Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html).

## 5. Ví dụ xuyên suốt: quyền phê duyệt, tenant và trạng thái

Ví dụ sau là một lớp kiểm thử độc lập về mặt cấu trúc: các bean và lớp hỗ trợ được đặt bên trong lớp test để dễ theo dõi. Đặt mã trong `ApprovalSecurityTest.java` thuộc package test của dự án. Các dependency đã nêu và dependency web/security của ứng dụng là điều kiện để biên dịch.

**Giới hạn mô hình:** kho dữ liệu dưới đây ở trong bộ nhớ, dành cho các tình huống chạy tuần tự. Nó không mô phỏng transaction, khóa dữ liệu hoặc idempotency bền vững. Vì vậy, các bài kiểm thử này không được dùng làm bằng chứng chống race condition. Phần sau sẽ chỉ ra cách kiểm tra các thuộc tính đó với database thật.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringJUnitWebConfig(ApprovalSecurityTest.TestApplication.class)
class ApprovalSecurityTest {

    @Autowired WebApplicationContext context;
    @Autowired OrderStore store;
    @Autowired ApprovalService service;
    MockMvc mvc;

    @BeforeEach
    void prepare() {
        store.reset();
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:read")
    void methodCallWithoutApproveAuthorityDoesNotWrite() {
        var before = store.snapshot();

        assertThatThrownBy(() -> service.approve(101L))
                .isInstanceOf(AccessDeniedException.class);

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-b", authorities = "order:approve")
    void approverFromAnotherTenantDoesNotWrite() {
        var before = store.snapshot();

        assertThatThrownBy(() -> service.approve(101L))
                .isInstanceOf(AccessDeniedException.class);

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "creator-a", authorities = "order:approve")
    void creatorCannotApproveOwnOrder() {
        var before = store.snapshot();

        assertThatThrownBy(() -> service.approve(101L))
                .isInstanceOf(AccessDeniedException.class);

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void draftCannotSkipSubmission() {
        var before = store.snapshot();

        assertThatThrownBy(() -> service.approve(103L))
                .isInstanceOf(OrderStateConflict.class);

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void repeatedApprovalDoesNotCreateSecondEvent() {
        service.approve(101L);
        var afterFirstApproval = store.snapshot();

        assertThatThrownBy(() -> service.approve(101L))
                .isInstanceOf(OrderStateConflict.class);

        assertThat(store.snapshot()).isEqualTo(afterFirstApproval);
        assertThat(store.require(101L).state()).isEqualTo(State.APPROVED);
        assertThat(store.events()).containsExactly(101L);
    }

    @Test
    void anonymousRequestWithValidCsrfGets401() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/101/approve").with(csrf()))
                .andExpect(status().isUnauthorized());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:read")
    void validCsrfDoesNotGrantApproveAuthority() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/101/approve").with(csrf()))
                .andExpect(status().isForbidden());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void missingCsrfRejectsEvenAnApprover() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/101/approve"))
                .andExpect(status().isForbidden());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void invalidCsrfDoesNotWrite() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/101/approve")
                    .with(csrf().useInvalidToken()))
                .andExpect(status().isForbidden());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    void changingRequestIdentityCannotCrossTenant() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/101/approve")
                    .with(user("approver-b")
                        .authorities(() -> "order:approve"))
                    .with(csrf()))
                .andExpect(status().isForbidden());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void draftRequestGetsConflict() throws Exception {
        var before = store.snapshot();

        mvc.perform(post("/orders/103/approve").with(csrf()))
                .andExpect(status().isConflict());

        assertThat(store.snapshot()).isEqualTo(before);
        assertThat(store.events()).isEmpty();
    }

    @Test
    @WithMockUser(username = "approver-a", authorities = "order:approve")
    void eligibleApproverGets204AndExactlyOneEvent() throws Exception {
        var otherOrderBefore = store.require(103L);

        mvc.perform(post("/orders/101/approve").with(csrf()))
                .andExpect(status().isNoContent());

        assertThat(store.require(101L).state()).isEqualTo(State.APPROVED);
        assertThat(store.require(103L)).isEqualTo(otherOrderBefore);
        assertThat(store.events()).containsExactly(101L);
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    @EnableMethodSecurity
    static class TestApplication {

        @Bean
        SecurityFilterChain security(HttpSecurity http) throws Exception {
            // CSRF giữ cấu hình mặc định: được bật.
            // Quyền order:approve được kiểm tra tại service.
            return http
                    .authorizeHttpRequests(requests -> requests
                        .requestMatchers(HttpMethod.POST, "/orders/*/approve")
                            .authenticated()
                        .anyRequest().denyAll())
                    .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(
                            new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
                    .build();
        }

        @Bean OrderStore orderStore() { return new OrderStore(); }

        @Bean
        ApprovalService approvalService(OrderStore store) {
            return new ApprovalService(store);
        }

        @Bean
        ApprovalController approvalController(ApprovalService service) {
            return new ApprovalController(service);
        }
    }

    public static class ApprovalService {
        private final OrderStore store;

        public ApprovalService(OrderStore store) {
            this.store = store;
        }

        @PreAuthorize("hasAuthority('order:approve')")
        public void approve(long orderId) {
            var authentication = SecurityContextHolder.getContext()
                    .getAuthentication();
            String subject = authentication.getName();
            String tenant = store.tenantOf(subject);
            Order order = store.require(orderId);

            if (tenant == null || !Objects.equals(tenant, order.tenantId())) {
                throw new AccessDeniedException("Không được thao tác đơn");
            }
            if (Objects.equals(subject, order.createdBy())) {
                throw new AccessDeniedException("Không được tự phê duyệt");
            }
            if (order.state() != State.SUBMITTED) {
                throw new OrderStateConflict();
            }

            store.save(new Order(order.id(), order.tenantId(),
                    order.createdBy(), State.APPROVED));
            store.recordApproval(order.id());
        }
    }

    @RestController
    public static class ApprovalController {
        private final ApprovalService service;

        public ApprovalController(ApprovalService service) {
            this.service = service;
        }

        @PostMapping("/orders/{id}/approve")
        @ResponseStatus(HttpStatus.NO_CONTENT)
        public void approve(@PathVariable("id") long id) {
            service.approve(id);
        }
    }

    enum State { DRAFT, SUBMITTED, APPROVED }

    record Order(long id, String tenantId, String createdBy, State state) {}

    @ResponseStatus(HttpStatus.CONFLICT)
    public static class OrderStateConflict extends RuntimeException {}

    public static class OrderStore {
        private final Map<Long, Order> orders = new HashMap<>();
        private final List<Long> approvalEvents = new ArrayList<>();
        private final Map<String, String> tenantBySubject = Map.of(
                "creator-a", "tenant-a",
                "approver-a", "tenant-a",
                "approver-b", "tenant-b");

        void reset() {
            orders.clear();
            approvalEvents.clear();
            save(new Order(101L, "tenant-a", "creator-a", State.SUBMITTED));
            save(new Order(103L, "tenant-a", "creator-a", State.DRAFT));
        }

        String tenantOf(String subject) { return tenantBySubject.get(subject); }

        Order require(long id) {
            Order order = orders.get(id);
            if (order == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND);
            }
            return order;
        }

        void save(Order order) { orders.put(order.id(), order); }
        void recordApproval(long id) { approvalEvents.add(id); }
        Map<Long, Order> snapshot() { return Map.copyOf(orders); }
        List<Long> events() { return List.copyOf(approvalEvents); }
    }
}
```

Các điểm thiết kế đáng chú ý:

- `service` được tiêm từ Spring nên lời gọi đi qua proxy method security. Nếu thay bằng `new ApprovalService(store)`, annotation không tự thực thi.
- Tenant được tra bằng subject trong dữ liệu phía server của ví dụ. Request không được tự chọn tenant đáng tin cậy bằng một trường JSON hay header tùy ý.
- Endpoint chỉ yêu cầu xác thực ở tầng HTTP; điều này khiến bài kiểm thử thiếu authority thực sự phụ thuộc vào bảo vệ ở service.
- Snapshot dùng record bất biến và bản sao collection. Nếu lưu tham chiếu tới một entity khả biến làm giá trị “trước”, entity đó có thể bị sửa cùng lúc với giá trị “sau” và che mất lỗi.
- Cấu hình `TestApplication` là cấu hình của ứng dụng minh họa này. Khi chuyển sang dự án thực, hãy nạp chain và service thật thay vì chép một chain dễ vượt qua chỉ để test xanh.
- Ví dụ mặc định chạy tuần tự. Nếu bật chạy test song song, cần cô lập kho dữ liệu theo test hoặc cơ chế fixture phù hợp; các test cùng reset một singleton sẽ can thiệp nhau.

Trong sản phẩm, kiểm tra tenant thường nằm trong truy vấn có phạm vi hoặc trong policy kết hợp dữ liệu. Quy tắc trạng thái và việc ghi thay đổi cần nằm trong cùng ranh giới giao dịch phù hợp. Những lựa chọn đó không được mô phỏng bằng `HashMap` ở ví dụ này.

## 6. Chọn danh tính giả lập đúng với câu hỏi kiểm thử

### 6.1. `@WithMockUser`: kiểm thử quyết định sau xác thực

`@WithMockUser` tạo ngữ cảnh đã xác thực cho test; người dùng đó không cần tồn tại trong database. Principal mặc định là kiểu `User` của Spring Security. Vì vậy nó phù hợp khi mã dựa trên username/authority, nhưng không thay thế một principal riêng có `accountId` và `tenantId`. [Tài liệu Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html).

Phân biệt role và authority:

```java
@WithMockUser(roles = "APPROVER")
// Tạo authority ROLE_APPROVER.

@WithMockUser(authorities = "order:approve")
// Tạo authority chính xác order:approve.
```

`roles` tự thêm tiền tố `ROLE_`; `authorities` không thêm tiền tố. Chọn cách tương ứng với `hasRole('APPROVER')` hoặc `hasAuthority('order:approve')` trong cấu hình. Không cấu hình đồng thời `roles` tùy chỉnh và `authorities` cho cùng annotation. [API `WithMockUser`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithMockUser.html).

Annotation này không chứng minh mật khẩu hợp lệ, tài khoản còn hoạt động, token có chữ ký đúng hay quyền đã được đọc đúng từ cơ sở dữ liệu. Các thuộc tính đó cần bài kiểm thử qua cơ chế xác thực thực tế.

### 6.2. `user(...)`: thay người gọi theo từng request

Request post-processor hữu ích khi một test có nhiều người gọi:

```java
mvc.perform(post("/orders/101/approve")
        .with(user("approver-a").authorities(() -> "order:approve"))
        .with(csrf()));
```

`user(...)` có thể nhận một `UserDetails` tùy chỉnh; `authentication(...)` cho phép đưa vào một `Authentication` phù hợp mô hình ứng dụng. Các tiện ích này cần được dùng với MockMvc đã tích hợp Spring Security. [Tài liệu chạy request dưới một người dùng](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html).

Ưu tiên danh tính viết rõ ở từng tình huống nhạy cảm. Một default user có quyền quản trị cho toàn bộ lớp test có thể làm các trường hợp thiếu quyền vô tình chạy với quá nhiều quyền.

### 6.3. `@WithUserDetails`: dùng principal do ứng dụng tải

Nếu ứng dụng có `UserDetailsService` trả về principal riêng, có thể sử dụng:

```java
@WithUserDetails(
        value = "approver-a",
        userDetailsServiceBeanName = "businessUserDetailsService",
        setupBefore = TestExecutionEvent.TEST_EXECUTION)
```

Người dùng phải tồn tại khi security context được tạo. `TEST_EXECUTION` dời việc dựng context tới sau `@BeforeEach`, hữu ích khi fixture người dùng được tạo tại đó. Cần import `WithUserDetails` và `TestExecutionEvent` từ `org.springframework.security.test.context.support`. Cách này tải dữ liệu người dùng nhưng vẫn không chạy luồng kiểm tra mật khẩu. [API `WithUserDetails`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithUserDetails.html).

## 7. Principal nghiệp vụ tùy chỉnh với `@WithSecurityContext`

Khi controller hoặc policy nhận trực tiếp principal có tenant, hãy dựng đúng kiểu principal. Ví dụ sau là bộ hỗ trợ riêng cho một ứng dụng dùng `BusinessPrincipal`; nó không thay đổi ví dụ `ApprovalSecurityTest` ở trên.

```java
import java.security.Principal;

public record BusinessPrincipal(String subject, String tenantId)
        implements Principal {
    @Override
    public String getName() {
        return subject;
    }
}
```

Annotation test:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.Target;

import org.springframework.security.test.context.support.WithSecurityContext;

import static java.lang.annotation.ElementType.METHOD;
import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Retention(RUNTIME)
@Target({TYPE, METHOD})
@WithSecurityContext(factory = BusinessUserContextFactory.class)
public @interface WithBusinessUser {
    String subject();
    String tenantId();
    String[] authorities() default {};
}
```

Factory:

```java
import java.util.Arrays;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithSecurityContextFactory;

public class BusinessUserContextFactory
        implements WithSecurityContextFactory<WithBusinessUser> {

    @Override
    public SecurityContext createSecurityContext(WithBusinessUser user) {
        var principal = new BusinessPrincipal(user.subject(), user.tenantId());
        var authorities = Arrays.stream(user.authorities())
                .map(SimpleGrantedAuthority::new)
                .toList();
        var authentication = UsernamePasswordAuthenticationToken.authenticated(
                principal, "unused-in-test", authorities);

        var context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        return context;
    }
}
```

Sau đó đặt `@WithBusinessUser(subject = "approver-a", tenantId = "tenant-a", authorities = "order:approve")` lên test có Spring TestContext hỗ trợ. Mỗi public type ở các đoạn trên đặt trong tệp Java tương ứng của mã test. `@WithSecurityContext` liên kết annotation tùy chỉnh với factory tạo context. [API `WithSecurityContext`](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/support/WithSecurityContext.html).

Factory phải cho phép mô tả danh tính khác tenant và danh tính thiếu quyền. Nếu factory luôn gán một tenant hoặc tự thêm quyền phê duyệt, nó sẽ làm mất khả năng biểu diễn tình huống tấn công.

Danh tính được factory tạo là một giả định đầu vào của test. Cần kiểm thử riêng nơi ứng dụng chuyển token hoặc dữ liệu tài khoản thành `BusinessPrincipal`, bao gồm trường hợp thiếu tenant, subject không được ánh xạ và tài khoản bị vô hiệu hóa.

## 8. CSRF: bảo đảm request bị chặn vì đúng nguyên nhân

Với endpoint thuộc phạm vi bảo vệ CSRF, request thay đổi trạng thái cần token hợp lệ. `csrf()` thêm token test; có thể dùng `csrf().asHeader()` hoặc `csrf().useInvalidToken()` cho những tình huống tương ứng. [Tài liệu kiểm thử CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html).

Một kết quả `403` chưa cho biết quy tắc quyền theo đối tượng đã được kiểm tra. Ví dụ, test gửi request khác tenant nhưng quên CSRF có thể xanh ngay tại `CsrfFilter`; service chứa lỗi bỏ kiểm tra tenant vẫn chưa được chạy.

Tách điều kiện đầu vào để chỉ còn một nguyên nhân chính:

| Điều cần kiểm tra | Xác thực/quyền | CSRF | Đối tượng/trạng thái |
|---|---|---|---|
| Thiếu xác thực | Anonymous | Hợp lệ nếu chain yêu cầu | Đối tượng hợp lệ |
| Thiếu quyền | Đã xác thực, thiếu đúng quyền đang xét | Hợp lệ | Cùng tenant, đúng trạng thái |
| Sai tenant | Đã xác thực, đủ quyền | Hợp lệ | Khác tenant, đúng trạng thái |
| Sai trạng thái | Đã xác thực, đủ quyền và đúng quan hệ | Hợp lệ | Trạng thái cấm |
| Thiếu CSRF | Đã xác thực, đủ quyền | Không có | Đối tượng hợp lệ |

Giữ một tình huống thành công với dữ liệu gần giống tình huống bị từ chối. Nó chứng minh endpoint và fixture có khả năng đi tới nghiệp vụ; lỗi cấu hình khiến mọi request đều bị chặn sẽ khó bị nhầm là bảo mật tốt.

Không tắt CSRF riêng trong cấu hình test chỉ để vượt qua lỗi `403`. Nếu sản phẩm chủ động không dùng CSRF cho một nhóm API, bài kiểm thử phải nạp cùng chính sách đó và có lý do kiến trúc tương ứng. Chỉ có nhãn “stateless” không đủ để kết luận: cần xét credential có được trình duyệt tự gửi, chẳng hạn cookie, hay không.

Tiện ích `csrf()` không chứng minh frontend đã lấy và gửi token đúng. Với luồng dùng trình duyệt/session, nên có một bài kiểm thử tích hợp lấy token theo cơ chế thực tế rồi gửi request tiếp theo cùng session hoặc cookie cần thiết.

## 9. JWT: phân biệt quyền được giả lập và xác thực token thật

Trong bài kiểm thử resource server có principal kiểu `Jwt`, dùng `jwt()` để dựng danh tính phù hợp. Đoạn sau thuộc một context đã cấu hình resource server của ứng dụng và có fixture đơn tương ứng, không phải một bước cấu hình JWT cho `TestApplication` ở phần 5.

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

// Bên trong test có MockMvc đã tích hợp Spring Security:
mvc.perform(post("/orders/101/approve")
        .with(jwt()
            .jwt(builder -> builder
                .subject("approver-a")
                .claim("tenant_id", "tenant-a"))
            .authorities(new SimpleGrantedAuthority("order:approve")))
        .with(csrf()))
    .andExpect(status().isNoContent());
```

`jwt()` tạo authentication dùng JWT giả lập. Việc gán trực tiếp authorities phù hợp để kiểm thử quyết định nghiệp vụ sau xác thực, nhưng không kiểm tra chữ ký hay việc converter thật ánh xạ claim thành quyền. Token hết hạn giả lập theo cách này cũng không chứng minh decoder sẽ từ chối token hết hạn. [Tài liệu kiểm thử OAuth 2.0 và JWT](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html#testing-jwt-authentication).

Trong resource server, scope thường được ánh xạ thành authority có tiền tố `SCOPE_`; `order:approve` và `SCOPE_order:approve` là hai chuỗi khác nhau. Nếu ứng dụng dùng converter riêng, cần kiểm thử converter và cấu hình nối nó vào quá trình xác thực. [Tài liệu Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).

Nên tổ chức ba nhóm bằng chứng:

| Nhóm | Cách cấp danh tính | Câu hỏi được trả lời |
|---|---|---|
| Quyền sau xác thực | `jwt()` hoặc authentication phù hợp | Subject, tenant và authorities này được làm gì? |
| Tích hợp filter và converter | Header bearer, decoder kiểm soát trong test, converter thật | Request có đi qua nhánh xác thực và tạo đúng principal/quyền không? |
| Xác minh token | Header bearer với token được ký bằng khóa test, decoder và validator thật | Chữ ký, thời gian, issuer, audience theo cấu hình có được kiểm tra không? |

Khi test nhánh bearer thật, không đồng thời gắn `@WithMockUser`, `user(...)` hoặc `jwt()` cho request đó. Một danh tính được cài sẵn có thể làm mục tiêu kiểm thử bị mơ hồ. Các tình huống cần có gồm token hợp lệ, chữ ký sai, hết hạn, issuer sai, audience không phù hợp khi ứng dụng yêu cầu audience, và thiếu claim nghiệp vụ bắt buộc.

Tenant lấy từ JWT chỉ đáng tin theo chính sách xác thực và phân quyền đã thiết kế. Nếu người dùng có thể chọn tenant qua một header, vẫn cần chứng minh họ là thành viên hợp lệ của tenant được chọn; không chỉ so sánh hai chuỗi do client cùng kiểm soát.

## 10. Kiểm tra trạng thái và tác dụng phụ sau request

Một test bảo mật logic nên có ba phần: điều kiện trước rõ ràng, hành động tấn công cụ thể và quan sát hậu quả.

Với một lần phê duyệt bị từ chối, nên quan sát:

- Trạng thái, version, số tiền, người tạo và người duyệt của đơn.
- Số bản ghi phê duyệt, bản ghi giữ hạn mức hoặc bút toán liên quan.
- Sự kiện outbox, lệnh thanh toán và thông báo có thể kích hoạt tác vụ bên ngoài.
- Nội dung phản hồi có tiết lộ dữ liệu người khác hay không.

Audit log có thể ghi lại lần truy cập bị từ chối. Vì thế, “không có tác dụng phụ nghiệp vụ” không có nghĩa là cấm mọi bản ghi audit. Hãy phân biệt `APPROVAL_DENIED` phục vụ giám sát với `ORDER_APPROVED` có thể kích hoạt chi tiền.

Trong ví dụ ở phần 5, `snapshot()` so sánh toàn bộ đơn và `events()` quan sát sự kiện của mô hình. Khi thay bằng JPA, cần đọc lại dữ liệu từ nguồn có thể phản ánh trạng thái lưu trữ thực, tránh chỉ kiểm tra entity đang nằm trong persistence context.

`authenticated()` và `unauthenticated()` giúp kiểm tra trạng thái xác thực của kết quả MockMvc. Chúng không chứng minh người dùng đã được phép thao tác một đối tượng cụ thể. [Tài liệu SecurityMockMvcResultMatchers](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/result-matchers.html).

Ví dụ bổ sung trong test phê duyệt hợp lệ ở phần 5:

```java
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;

mvc.perform(post("/orders/101/approve").with(csrf()))
        .andExpect(status().isNoContent())
        .andExpect(authenticated().withUsername("approver-a"));
```

Đoạn này giả định annotation tạo người dùng như test gốc. Vẫn phải kiểm tra đơn và sự kiện như trước. Với lỗi nghiệp vụ, nên xác nhận mã lỗi ổn định do ứng dụng quy định, chẳng hạn `ORDER_NOT_SUBMITTED`, thay vì chỉ một chuỗi thông báo có thể thay đổi theo ngôn ngữ.

## 11. Kiểm thử transaction và chống thay đổi dở dang

Trong hệ thống phê duyệt thực, một giao dịch có thể gồm:

```text
Đọc đơn có cơ chế kiểm soát tranh chấp
  -> kiểm tra tenant và quan hệ người gọi
  -> kiểm tra trạng thái và giới hạn nghiệp vụ
  -> ghi trạng thái APPROVED
  -> ghi bản ghi phê duyệt
  -> ghi sự kiện vào outbox
  -> commit
```

Hãy kiểm thử lỗi tại điểm sau một thay đổi nhưng trước khi hoàn thành toàn bộ giao dịch. Chẳng hạn, cố ý làm thao tác ghi outbox thất bại rồi kiểm tra rằng đơn và bản ghi phê duyệt đều không được commit. Đây là tình huống mà một phản hồi lỗi có thể che giấu thay đổi đã lưu một phần.

Một bài kiểm thử tích hợp cần có ranh giới cụ thể:

1. Tạo fixture và commit trong giao dịch chuẩn bị.
2. Gọi bean service thật qua proxy hoặc gửi request qua context thật.
3. Gây lỗi có kiểm soát trong giao dịch nghiệp vụ, không thay service bằng mock.
4. Kết thúc giao dịch nghiệp vụ.
5. Mở giao dịch đọc mới để kiểm tra trạng thái bền vững và số bản ghi.

`@Transactional` trên test có thể khiến lời gọi ứng dụng tham gia giao dịch do test quản lý. Khi đó, bạn chưa quan sát được cùng một thời điểm commit như request ngoài thực tế. Ngoài ra, giao dịch test gắn với thread; không tự bao bọc giao dịch ở một HTTP server thread hoặc worker thread khác. [Tài liệu Transaction Management trong Spring TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html).

Với JPA, `flush()` giúp đẩy SQL và phát hiện một số lỗi constraint, nhưng không thay thế hoàn toàn kiểm tra commit. Khi cần kiểm tra kết quả sau giao dịch, dùng cách quản lý transaction rõ ràng, chẳng hạn `TransactionTemplate`, và đọc lại trong một giao dịch độc lập. Tránh bọc toàn bộ tình huống quan sát commit trong một transaction test rồi chỉ dựa vào rollback tự động để dọn dữ liệu.

Đối với thao tác gọi hệ thống ngoài, rollback database không tự thu hồi một lệnh thanh toán đã gửi. Bài kiểm thử nên quan sát ranh giới gửi lệnh và thiết kế outbox/idempotency tương ứng. Nếu test chỉ đếm lời gọi một mock client, nó chưa chứng minh bên nhận sẽ không xử lý trùng sau retry.

## 12. Idempotency: yêu cầu trùng không được lặp tác dụng phụ

Test `repeatedApprovalDoesNotCreateSecondEvent` chỉ chứng minh lần duyệt thứ hai bị từ chối theo state machine trong một luồng tuần tự. Hệ thống có hỗ trợ idempotency key có thể chọn trả lại kết quả trước đó thay vì `409`.

Ví dụ giao thức của một API thanh toán:

```http
POST /orders/101/pay
Idempotency-Key: pay-101-attempt-1
Content-Type: application/json

{"paymentMethodId":"pm-01"}
```

Đối với thiết kế này, phạm vi key cần được định nghĩa rõ, chẳng hạn tenant, chủ thể hoặc tài khoản, loại thao tác và key. Nếu chỉ dùng key toàn cục do client cung cấp, hai tenant có thể va chạm hoặc đọc nhầm kết quả của nhau.

| Tình huống | Kết quả cần xác định trong hợp đồng | Bất biến cần quan sát |
|---|---|---|
| Cùng key, cùng nội dung, cùng phạm vi | Trả lại cùng kết quả nghiệp vụ | Một payment intent và một hiệu ứng tài chính |
| Cùng key, nội dung khác | Từ chối xung đột | Nội dung cũ và kết quả cũ không bị thay |
| Key giống nhau, tenant khác | Xử lý độc lập hoặc từ chối theo phạm vi đã định | Không lộ response hoặc tái sử dụng giao dịch của tenant khác |
| Hai request cùng key đến đồng thời | Một request giành quyền xử lý, request kia xử lý theo trạng thái key | Không có hai tác vụ nghiệp vụ |
| Request đầu đang xử lý | Trả trạng thái chờ hoặc lỗi retry theo hợp đồng | Không mở một tác vụ thứ hai |
| Response bị mất sau commit, client retry | Khôi phục kết quả đã ghi | Không thu tiền lần nữa |
| Key hết hạn hoặc được sử dụng lại | Theo thời hạn và quy tắc miền đã công bố | State machine vẫn bảo vệ thao tác đã hoàn tất |

Kiểm thử fingerprint của request cần bao gồm các trường làm thay đổi ý nghĩa nghiệp vụ; chỉ băm một phần payload có thể khiến hai lệnh khác nhau bị coi là giống nhau. Cũng cần xác định cách chuẩn hóa request để khác biệt không quan trọng về biểu diễn không vô tình làm thay đổi danh tính lệnh.

Quyền truy cập phải được kiểm tra khi retry lấy kết quả cũ. Một key hợp lệ không thay thế quyền xem đơn hay kết quả thanh toán. Hãy thêm tình huống người dùng bị thu hồi quyền giữa lần gọi đầu và lần phát lại, rồi kiểm tra hành vi theo chính sách đã chọn.

Spring Security test support cung cấp danh tính và request cho các tình huống này. Tính duy nhất của key, việc chiếm quyền xử lý và dữ liệu sau commit phải được kiểm tra qua implementation thật và database có constraint tương ứng.

## 13. Tranh chấp đồng thời: bảo vệ invariant dưới nhiều request

Hai test gọi tuần tự không mô phỏng tình huống cả hai transaction đều đọc thấy `SUBMITTED` trước khi ghi. Khi đó, kiểm tra trạng thái đúng về mặt câu lệnh vẫn có thể dẫn đến hai sự kiện nếu ranh giới đồng bộ không đúng.

Những cơ chế có thể được dùng gồm optimistic locking bằng version, khóa bi quan, cập nhật có điều kiện theo trạng thái, hoặc unique constraint cho một nghiệp vụ. Ví dụ cập nhật có điều kiện cần xem xét số hàng được sửa:

```sql
UPDATE orders
SET status = 'APPROVED', version = version + 1
WHERE id = :order_id
  AND tenant_id = :tenant_id
  AND status = 'SUBMITTED'
  AND version = :expected_version;
```

Đây là minh họa một điều kiện ghi, không phải toàn bộ cơ chế cấp quyền. Quy tắc người tạo không tự duyệt và các điều kiện nghiệp vụ khác vẫn cần được áp dụng trong thiết kế giao dịch. Một câu lệnh sửa được `0` hàng phải được xử lý theo hợp đồng, không tiếp tục phát sự kiện như đã duyệt thành công.

Để kiểm thử cạnh tranh có ý nghĩa:

1. Dùng database cùng loại và cấu hình tranh chấp đủ gần môi trường triển khai.
2. Tạo một đơn `SUBMITTED` rồi commit fixture.
3. Mở hai lời gọi có transaction độc lập và ngữ cảnh người gọi rõ ràng.
4. Dùng latch hoặc barrier tại điểm phù hợp để phối hợp thực thi; không dựa vào `sleep` để hy vọng xảy ra race.
5. Thu thập kết quả cả hai lời gọi, bao gồm lỗi version hoặc lỗi cạnh tranh đã được ánh xạ.
6. Sau khi cả hai kết thúc, đọc lại bằng transaction mới và kiểm tra một chuyển trạng thái cùng đúng số sự kiện/bút toán.

Điểm đặt barrier phải phù hợp chiến lược khóa. Nếu lời gọi thứ nhất đang giữ khóa hàng mà lại chờ lời gọi thứ hai vượt qua cùng khóa để tới barrier, test có thể tự tạo deadlock. Phối hợp tại đầu lời gọi, hoặc tại một hook trước bước giành khóa, tùy mục tiêu kiểm thử.

Security context của thread test không tự trở thành danh tính của mọi thread trong executor. Có thể dùng request đã xác thực riêng cho từng lời gọi hoặc cơ chế truyền context được cấu hình phù hợp; nếu gán context thủ công trong worker thì phải dọn trong `finally`. Đừng lấy một lỗi thiếu authentication ở thread phụ làm bằng chứng khóa nghiệp vụ đã hoạt động.

## 14. Các tình huống tấn công logic nên mở rộng

### 14.1. Thay ID và thay tenant

Với cùng một người gọi có `order:approve`, lần lượt thử đơn của mình, đơn người khác cùng tenant nếu chính sách cho phép, đơn tenant khác và ID không tồn tại. Kiểm tra cả phản hồi và việc đơn mục tiêu thực tế có bị thay đổi hay không.

Tenant, owner hoặc trạng thái gửi trong body không được ghi đè giá trị đáng tin cậy chỉ vì client cung cấp chúng. Nếu endpoint nhận `X-Tenant-Id`, hãy kiểm thử thành viên tenant và cách server xác lập tenant đang hoạt động.

### 14.2. Bỏ qua bước phê duyệt

Tấn công có thể gọi thẳng `approve`, `pay` hoặc `ship` mà không đi qua bước trước đó trên giao diện. Dựng fixture từng trạng thái và gọi trực tiếp endpoint cuối, thay vì chỉ kiểm thử hành trình người dùng hợp lệ.

Hãy xét trạng thái sau thao tác thất bại, trạng thái bị hủy và trạng thái đã kết thúc. Một điều kiện kiểu “khác `DRAFT` thì được duyệt” có thể cho phép duyệt cả đơn `CANCELLED`; cách kiểm tra chỉ chấp nhận tập trạng thái hợp lệ giúp biểu diễn quy tắc rõ hơn.

### 14.3. Sửa giá và gán trường ngoài ý muốn

Mở rộng mô hình đơn để có giá và tổng tiền do server tính. Sau đó gửi các trường như `unitPrice`, `discount`, `approvedBy`, `ownerId` hoặc `status` nếu chúng không thuộc quyền điều khiển của client. API phải từ chối hoặc bỏ qua theo hợp đồng, và dữ liệu lưu phải giữ đúng invariant.

Một test cho giá nên kiểm tra giá được chốt theo thời điểm nào, nguồn giá nào đáng tin cậy, giới hạn giảm giá và cách làm tròn. Spring Security chỉ quyết định quyền gọi; việc server tính lại tổng tiền vẫn là trách nhiệm nghiệp vụ.

### 14.4. Thu hồi quyền và thay đổi quan hệ

Thử tình huống quyền phê duyệt hoặc quan hệ sở hữu thay đổi giữa hai thao tác. Nếu quyền được nhúng trong token, cần xác định cửa sổ hiệu lực và cơ chế thu hồi mà hệ thống thực sự hỗ trợ. Bài kiểm thử phải phản ánh chính sách này thay vì giả định mọi thay đổi quyền có hiệu lực tức thì.

### 14.5. Thao tác hàng loạt

Với batch gồm nhiều ID, thêm một ID khác tenant hoặc sai trạng thái vào giữa danh sách. Xác định trước toàn bộ batch rollback hay cho phép thành công từng phần; sau đó kiểm tra từng đối tượng, từng tác dụng phụ và nội dung báo lỗi. Kiểm tra quyền trên ID đầu tiên không bảo vệ toàn bộ danh sách.

## 15. Những lỗi làm kiểm thử xanh nhưng thiếu bằng chứng

| Lỗi | Điều thực tế được kiểm tra | Cách điều chỉnh |
|---|---|---|
| Dựng service bằng `new` rồi tin `@PreAuthorize` | Nội dung method, không phải proxy | Gọi bean từ Spring context |
| Tắt filter của MockMvc | Controller không có lớp bảo vệ HTTP đó | Dùng chain thật cho bài kiểm thử security |
| Thiếu CSRF khi muốn kiểm tra quyền | Nhánh chặn CSRF | Thêm token hợp lệ và dữ liệu nghiệp vụ hợp lệ |
| Mock service hoặc policy đang cần chứng minh | Kịch bản trả về của mock | Cho thành phần quyết định chạy thật |
| Chỉ có user quyền quản trị | Một tập quyền quá rộng | Thêm actor đủ quyền tối thiểu và actor thiếu quyền |
| Dùng `roles = "ROLE_APPROVER"` | Authority bị gán tiền tố ngoài ý muốn | Dùng `roles = "APPROVER"` hoặc authority chính xác |
| Gán JWT authorities trực tiếp rồi kết luận converter đúng | Quyết định dựa trên quyền đã cài sẵn | Test converter và nhánh bearer riêng |
| Chỉ kiểm tra `403` | Mã phản hồi của một lớp nào đó | Giữ các điều kiện khác hợp lệ, kiểm tra trạng thái và tác dụng phụ |
| Chỉ đọc entity đang được quản lý | Trạng thái trong bộ nhớ của ORM | Đọc sau ranh giới transaction phù hợp |
| Dùng kho trong bộ nhớ để kết luận chống race | Một mô hình không có hành vi khóa DB | Dùng transaction độc lập và database thực |
| Test thành công phụ thuộc test chạy trước | Dữ liệu rò rỉ giữa các test | Tạo fixture độc lập và dọn theo phạm vi |

Method security dựa trên Spring AOP. Một lời gọi nội bộ kiểu `this.approve(...)` trong cùng đối tượng không đi qua proxy theo mô hình proxy thông thường; annotation trên method được gọi có thể không được áp dụng theo cách người viết mong đợi. Cần kiểm thử đường gọi thực tế và tổ chức ranh giới bean phù hợp. [Tài liệu Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html).

Không tự đặt `SecurityContextHolder` cho toàn bộ bộ test rồi để lại trạng thái dùng chung. Nếu phải dựng context thủ công, tạo context mới và dọn sau mỗi phạm vi sử dụng; với annotation test, giữ cơ chế Spring TestContext tiêu chuẩn hoạt động. Khi cấu hình riêng test execution listeners, cần bảo đảm không vô tình loại bỏ hỗ trợ security context.

Nếu ứng dụng có nhiều `SecurityFilterChain`, thêm tình huống cho từng nhóm URL quan trọng để xác nhận request khớp đúng chain. Một bộ test chỉ dùng URL thuộc chain bảo vệ chặt không chứng minh endpoint tương tự ở chain khác được bảo vệ giống nhau.

## 16. Quy trình áp dụng vào một chức năng thực tế

1. Viết hành động và các invariant bằng ngôn ngữ nghiệp vụ: ai được làm, với đối tượng nào, ở trạng thái nào, trong giới hạn nào.
2. Liệt kê actor và quan hệ dữ liệu, bao gồm người thiếu quyền, khác tenant, người tạo và người được ủy quyền nếu có.
3. Chọn tầng kiểm thử cho từng invariant; giữ service/policy thật ở nơi cần chứng minh quyết định.
4. Nạp cấu hình security thực tế và có một tình huống hợp lệ để xác nhận đường đi hoạt động.
5. Thêm mỗi tình huống bị từ chối với các điều kiện còn lại hợp lệ.
6. Quan sát phản hồi, dữ liệu và tác dụng phụ, bao gồm việc không tiết lộ nội dung ngoài quyền.
7. Bổ sung retry và cạnh tranh bằng ranh giới transaction thực; không suy diễn từ mô hình trong bộ nhớ.
8. Giữ fixture độc lập, danh tính rõ ràng và tên test diễn đạt invariant.

Các bài tự thực hành phù hợp với ví dụ:

- Thêm tình huống HTTP cho `creator-a` tự duyệt và đối chiếu với kiểm thử gọi service.
- Đổi chính sách che giấu đơn khác tenant sang `404`, sau đó thống nhất nội dung phản hồi cho ID không được nhìn thấy.
- Thay `OrderStore` bằng repository thật, thêm version và outbox trong cùng transaction; kiểm tra lỗi ghi outbox không để lại đơn đã duyệt.
- Thêm idempotency key cho một hành động thanh toán, kiểm tra cùng key với payload khác và hai request đến đồng thời.
- Thêm trường tiền do server quyết định và kiểm thử request cố sửa giá sau khi đơn đã gửi duyệt.

Một bộ kiểm thử hữu ích phải liên kết được mỗi kết luận với bằng chứng tương ứng: danh tính nào đã được giả lập, lớp bảo vệ nào đã chạy và invariant nào đã được quan sát sau khi thao tác kết thúc.
