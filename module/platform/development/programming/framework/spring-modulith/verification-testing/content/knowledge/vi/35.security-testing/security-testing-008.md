# Test cấu hình mặc định không mở quyền ngoài ý muốn

Trong ứng dụng Spring Modulith, mỗi module có thể bổ sung REST controller, endpoint nội bộ hoặc một bean cấu hình mới. Một thay đổi nhỏ như thêm `/api/orders/export`, mở rộng `requestMatchers("/api/**")` hay dùng profile kiểm thử để bỏ bộ lọc có thể vô tình cho phép truy cập chức năng chưa được cấp quyền. Bài này tập trung vào một yêu cầu có thể kiểm chứng: **mọi đường dẫn và phương thức HTTP chưa được cấp quyền tường minh phải bị từ chối theo mặc định**.

`ApplicationModules.verify()` bảo vệ cấu trúc phụ thuộc giữa module, còn `MockMvc` với Spring Security bảo vệ hợp đồng truy cập HTTP. Cần kiểm thử cả hai, vì một ứng dụng có ranh giới module hợp lệ vẫn có thể để lộ endpoint.

## 1. Định nghĩa chính xác trạng thái “mặc định không mở quyền”

Quy tắc **fail closed** ở lớp HTTP có ba phần:

1. Chỉ khai báo `permitAll()` cho đường dẫn **và phương thức** thật sự công khai; không dùng tiền tố quá rộng vì tiện.
2. Chỉ khai báo quyền nghiệp vụ cho các hành động đã biết, chẳng hạn `CUSTOMER` được xem/tạo đơn và `ADMIN` được chạy tác vụ bảo trì.
3. Kết thúc danh sách bằng `anyRequest().denyAll()` để endpoint mới, HTTP method mới và đường dẫn bị bỏ sót không được mở tự động.

Phân biệt ba tình huống trong kết quả test:

| Tình huống | Mã HTTP thường mong đợi | Điều được chứng minh |
| --- | --- | --- |
| Chưa đăng nhập vào tài nguyên yêu cầu xác thực | `401 Unauthorized` khi ứng dụng dùng HTTP Basic/Bearer | Cơ chế xác thực và entry point hoạt động |
| Đã xác thực nhưng không có quyền cần thiết | `403 Forbidden` | Chính sách phân quyền chặn đúng |
| Đã xác thực, gọi route chưa được liệt kê, dùng `denyAll` | `403 Forbidden` | Cấu hình mặc định từ chối truy cập |

Mã `401` có thể đổi thành `302` khi ứng dụng dùng form login, hoặc có định dạng lỗi riêng nếu cấu hình `AuthenticationEntryPoint`. Test phải dựa trên **cơ chế xác thực thực tế**, không mặc định mọi dự án đều trả `401`. Với request `POST` thiếu CSRF token, bộ lọc CSRF thường trả `403` **trước khi** kiểm tra quyền; do đó cần gắn token hợp lệ khi mục tiêu test là xác thực hoặc phân quyền.

## 2. Tạo chính sách mẫu có tuyến công khai hữu hạn

Giả sử ứng dụng `ShopApplication` có module `orders`; API phục vụ khách hàng và một tác vụ bảo trì nội bộ. Ví dụ dùng Spring MVC, Spring Security 6/7, HTTP Basic để mã trạng thái xác thực dễ quan sát và giữ **CSRF bật**. Trong dự án dùng JWT hoặc session, giữ nguyên ý tưởng phân quyền nhưng thay phần xác thực tương ứng.

```java
package example.shop.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class AccessPolicy {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAnyRole("CUSTOMER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasRole("CUSTOMER")
                .requestMatchers(HttpMethod.POST, "/internal/orders/reindex")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Để các phép thử có phản hồi HTTP rõ ràng, giả định các route tương ứng được triển khai như sau (minh họa hợp đồng controller; trong hệ thống thực, controller gọi application service và có thể dùng cơ sở dữ liệu):

```java
package example.shop.orders;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersHttpApi {

    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/orders")
    List<String> orders() {
        return List.of("ORD-001");
    }

    @PostMapping("/api/orders")
    ResponseEntity<Void> create() {
        return ResponseEntity.status(201).build();
    }

    @PostMapping("/internal/orders/reindex")
    ResponseEntity<Void> reindex() {
        return ResponseEntity.accepted().build();
    }
}
```

Các matcher cụ thể được xử lý trước `anyRequest().denyAll()`. Nếu ai đó thêm `GET /api/orders/export` mà chưa cập nhật chính sách, người có vai trò `ADMIN` cũng bị từ chối; đây là hành vi có chủ đích. `hasRole("ADMIN")` so khớp authority `ROLE_ADMIN`; không viết `hasRole("ROLE_ADMIN")` vì Spring Security đã bổ sung tiền tố `ROLE_`. Endpoint `/internal/**` vẫn cần bảo vệ ở lớp HTTP dù URL có chữ “internal”.

## 3. Biến chính sách thành ma trận kiểm thử

Trước khi viết JUnit, ghi một ma trận kỳ vọng có cả tình huống thành công và bị từ chối. Ma trận dưới đây gắn với chính sách mẫu ở mục 2:

| Yêu cầu | Người gọi | CSRF | Kỳ vọng |
| --- | --- | --- | --- |
| `GET /api/public/ping` | Ẩn danh | Không cần | `200` |
| `GET /api/orders` | Ẩn danh | Không cần | `401` |
| `GET /api/orders` | `CUSTOMER` | Không cần | `200` |
| `POST /api/orders` | `CUSTOMER` | Hợp lệ | `201` |
| `POST /api/orders` | `ADMIN` | Hợp lệ | `403` |
| `POST /internal/orders/reindex` | `CUSTOMER` | Hợp lệ | `403` |
| `POST /internal/orders/reindex` | `ADMIN` | Hợp lệ | `202` |
| `POST /internal/orders/reindex` | `ADMIN` | Thiếu | `403` |
| `GET /api/orders/export` | `ADMIN` | Không cần | `403` |
| `POST /api/public/ping` | `ADMIN` | Hợp lệ | `403` |

Hai dòng cuối rất quan trọng: chúng kiểm tra **quy tắc mặc định** và **giới hạn phương thức**. Một test chỉ khẳng định `GET /api/public/ping` trả `200` không phát hiện việc vô tình dùng `requestMatchers("/api/public/**").permitAll()`.

Khi thay HTTP Basic bằng form login, đổi riêng oracle `401` cho người ẩn danh theo entry point. Các kỳ vọng `403` cho người đã xác thực vẫn thể hiện chính sách từ chối quyền.

## 4. Viết JUnit kiểm tra HTTP thật qua Spring Security

Dùng `@SpringBootTest` để tải cấu hình bảo mật ứng dụng và `@AutoConfigureMockMvc` để chạy request qua servlet filters. Cần dependency test Spring Security (chẳng hạn `spring-security-test`), cùng JUnit 5 và Spring Boot test. Đoạn dưới là ví dụ test chạy được khi `ShopApplication` và controller ở mục 2 đã có trong classpath.

```java
package example.shop;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
// Spring Boot 3.x:
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(classes = ShopApplication.class)
@AutoConfigureMockMvc
class DefaultAccessPolicyIT {

    @Autowired MockMvc mvc;

    @Test
    void onlyTheDeclaredPublicGetIsOpenToAnonymousUsers() throws Exception {
        mvc.perform(get("/api/public/ping"))
            .andExpect(status().isOk());
    }

    @Test
    void anonymousUsersCannotReadOrders() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void customerCanReadAndCreateAnOrder() throws Exception {
        mvc.perform(get("/api/orders")
                .with(user("alice").roles("CUSTOMER")))
            .andExpect(status().isOk());

        mvc.perform(post("/api/orders")
                .with(user("alice").roles("CUSTOMER"))
                .with(csrf()))
            .andExpect(status().isCreated());
    }

    @Test
    void customerCannotStartAdminMaintenance() throws Exception {
        mvc.perform(post("/internal/orders/reindex")
                .with(user("alice").roles("CUSTOMER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanReindexButCannotCreateCustomerOrders() throws Exception {
        mvc.perform(post("/internal/orders/reindex")
                .with(user("ops").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isAccepted());

        mvc.perform(post("/api/orders")
                .with(user("ops").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
```

`user("alice").roles("CUSTOMER")` tạo principal kiểm thử trong request; nó **không xác minh mật khẩu thật**. Các test trên xác minh đường đi qua bộ lọc và quy tắc phân quyền. Muốn kiểm chứng login, HTTP Basic hoặc JWT thật, bổ sung test riêng dùng cơ chế xác thực của sản phẩm và user/token kiểm thử do test context quản lý.

Lưu ý phiên bản: Spring Boot **4.x** chuyển `AutoConfigureMockMvc` sang `org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc` và cần test dependency Web MVC tương ứng; các ví dụ còn lại vẫn giữ ý nghĩa. Giữ cấu hình `@AutoConfigureMockMvc` mặc định áp dụng filters; không bật `addFilters = false` trong bộ test cổng bảo mật.

## 5. Cố ý gửi POST thiếu hoặc sai CSRF token

Nếu ứng dụng dùng cookie/session hoặc cách xác thực chịu ảnh hưởng của trình duyệt, CSRF là một lớp bảo vệ riêng với phân quyền. Người có `ADMIN` chưa đủ để gọi `POST` khi CSRF token vắng mặt hoặc không hợp lệ. Đặt các test sau trong lớp `DefaultAccessPolicyIT` ở mục 4:

```java
@Test
void adminWithoutCsrfTokenIsStillRejected() throws Exception {
    mvc.perform(post("/internal/orders/reindex")
            .with(user("ops").roles("ADMIN")))
        .andExpect(status().isForbidden());
}

@Test
void invalidCsrfTokenIsRejected() throws Exception {
    mvc.perform(post("/internal/orders/reindex")
            .with(user("ops").roles("ADMIN"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}
```

Đừng suy luận từ một test `POST` trả `403` rằng phân quyền đã đúng: rất có thể **chỉ CSRF đang chặn**. Vì vậy các test kiểm tra vai trò ở mục 4 cố ý dùng `with(csrf())`, còn hai test ở mục này cố ý bỏ hoặc làm sai token.

Nếu API hoàn toàn stateless và dự án chủ động tắt CSRF vì dùng Bearer token không tự được trình duyệt gửi, hãy ghi rõ mô hình đe dọa và thay kiểm thử bằng bảo vệ phù hợp; không sao chép `csrf.disable()` từ một ví dụ khác chỉ để test xanh.

## 6. Khóa các route chưa khai báo bằng regression test

Khi một module mới thêm controller hoặc thay đổi URL, lỗi phổ biến là matcher có wildcard quá rộng, ví dụ `"/api/**"` được `permitAll()`. Tạo phép thử âm có cả endpoint “chưa tồn tại” để quy định rằng mọi route mới phải được duyệt chính sách.

Thêm vào `DefaultAccessPolicyIT`:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(strings = {
    "/api/orders/export",
    "/api/admin/overview",
    "/internal/orders/debug"
})
void unlistedGetRoutesStayDeniedEvenToAdmin(String path) throws Exception {
    mvc.perform(get(path).with(user("ops").roles("ADMIN")))
        .andExpect(status().isForbidden());
}

@Test
void publicGetDoesNotMakeOtherMethodsPublic() throws Exception {
    mvc.perform(post("/api/public/ping")
            .with(user("ops").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Hai import `org.junit.jupiter.params.*` đặt cùng các import khác ở đầu lớp Java khi tích hợp. Trong bộ fixture này, `403` đến từ `denyAll` **trước khi** MVC xét có controller xử lý URL hay không. Nếu bỏ filter, route chưa tồn tại thường sẽ cho `404/405`, khiến test thất bại và cảnh báo rằng đường bảo vệ đã đổi.

Khi một endpoint mới thực sự được triển khai, cập nhật ma trận theo yêu cầu nghiệp vụ: thêm matcher tối thiểu, test người được quyền và ít nhất một nhóm người **không** được quyền. Đừng xóa test âm chỉ vì một route bắt đầu tồn tại; chuyển nó thành một test phân quyền có kỳ vọng rõ ràng.

## 7. Chặn lỗ hổng từ test profile và servlet filter bị bỏ qua

Một cấu hình production đúng vẫn có thể bị kiểm thử sai nếu test context không tải `SecurityFilterChain`. Kiểm tra các điểm sau trong dự án:

- Không đặt `@Profile("!test")` lên cấu hình bảo mật cốt lõi khi bộ test dùng `@ActiveProfiles("test")`.
- Không dùng `@AutoConfigureMockMvc(addFilters = false)` hoặc `MockMvcBuilders.standaloneSetup(controller)` trong bộ test cần kiểm chứng chính sách filter chain đầy đủ.
- Không dùng bean `SecurityFilterChain` giả với `anyRequest().permitAll()` trong cấu hình test. Nếu test cần mock dịch vụ ngoài, mock **service phụ thuộc**, không mock chính sách phân quyền.
- Nếu có nhiều `SecurityFilterChain` cùng `@Order` và `securityMatcher(...)`, thử request qua **từng phạm vi**; chain ưu tiên cao có thể bắt request trước chính sách mặc định.

Có thể thêm một assertion kiểm tra bean hạ tầng được tạo trong ngữ cảnh test:

```java
@Autowired
org.springframework.context.ApplicationContext applicationContext;

@Test
void securityFilterChainIsRegistered() {
    org.assertj.core.api.Assertions.assertThat(
        applicationContext.containsBean("springSecurityFilterChain")
    ).isTrue();
}
```

Assertion về bean là kiểm tra bổ sung; test gửi HTTP ẩn danh trong mục 4 vẫn là bằng chứng mạnh hơn rằng filter **thật sự được áp dụng** cho route cụ thể. Với Spring Security method security (`@PreAuthorize`), phải bật cấu hình method security thực tế và bổ sung test service riêng; chỉ có filter chain không đảm bảo chặn được tất cả lời gọi trực tiếp từ module khác.

## 8. Đặt kiểm thử bảo mật đúng chỗ trong Spring Modulith

`ApplicationModules` kiểm tra phụ thuộc tĩnh giữa module. Chạy nó thành một JUnit độc lập để ngăn một module mới truy cập package `internal` không được phép hoặc tạo vòng phụ thuộc:

```java
package example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundariesTest {

    @Test
    void moduleDependenciesFollowTheArchitecture() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Ngược lại, `@ApplicationModuleTest` mặc định bootstrap **chỉ module chứa test** (`STANDALONE`); có thể chọn `DIRECT_DEPENDENCIES` hoặc `ALL_DEPENDENCIES`. Nó hữu ích để test service/repository/sự kiện trong module `orders`, nhưng có thể **không nạp** cấu hình bảo mật thuộc module `security`. Vì vậy:

- Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` cho bộ test cổng truy cập HTTP cuối cùng của ứng dụng.
- Dùng `@ApplicationModuleTest` cho những kịch bản nghiệp vụ theo module, và chỉ dùng nó làm test HTTP security nếu đã xác minh chain sản xuất được tải đầy đủ.
- Dùng `ApplicationModules.of(...).verify()` riêng để bảo vệ ranh giới kiến trúc; một lần `verify()` thành công **không nói gì** về việc route có bị mở công khai hay không.

Nếu module xuất bản domain event sau một request hợp lệ, có thể kiểm tra event bằng `Scenario` trong test module, nhưng quyền HTTP vẫn phải được kiểm tra từ đầu request ở ngữ cảnh có Security filter. Đó là hai bất biến khác nhau.

## 9. Kiểm soát Actuator và nhiều filter chain

Spring Boot Actuator có tuyến quản trị nằm ngoài controller nghiệp vụ. Sau khi ứng dụng tự định nghĩa `SecurityFilterChain`, không nên giả định các quy tắc bảo mật Actuator mặc định vẫn bảo vệ theo ý muốn. Khi dùng Actuator trong **cùng servlet context**, có thể thêm matcher chuyên biệt **trước** `anyRequest().denyAll()`:

```java
// Trong authorizeHttpRequests(...) của ứng dụng có Actuator:
.requestMatchers(EndpointRequest.to("health")).permitAll()
.requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
// Các route nghiệp vụ đã liệt kê...
.anyRequest().denyAll()
```

Import `org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest` khi module Actuator có trên classpath. Mỗi endpoint còn phụ thuộc cấu hình exposure: route chưa được expose không thể xem như một endpoint quản trị đang hoạt động. Nếu health có chi tiết nhạy cảm, dùng chính sách hiển thị health detail phù hợp thay vì chỉ dựa vào `permitAll()`.

Ma trận quản trị cần xác minh ít nhất: `health` được truy cập theo đúng chủ trương; endpoint quản trị **đã expose** như `metrics`/`env` bị từ chối với người ẩn danh hoặc người thiếu `OPS`; người có `OPS` chỉ truy cập những endpoint dự kiến. Khi `management.server.port` khác cổng ứng dụng, `MockMvc` trên application context có thể không chạm vào management context: hãy kiểm thử HTTP qua **cổng quản trị thật** trong một integration test chạy server ngẫu nhiên hoặc test riêng management context.

## 10. Chốt quality gate trong CI và kiểm chứng test bắt được lỗi

Trong pipeline, chạy bộ kiểm thử truy cập cùng với `ModuleBoundariesTest` mỗi lần đổi controller, cấu hình security, khai báo module hoặc dependency Spring. Với Gradle/Maven, bước chạy test có thể là `./gradlew test` hoặc `./mvnw test` tùy build của dự án; không cần dịch chuyển test sang giai đoạn deploy mới phát hiện route mở nhầm.

Một quality gate đạt yêu cầu khi:

1. Test xác nhận ít nhất một route công khai **được phép**, một route cần đăng nhập **chặn ẩn danh**, một vai trò sai **bị 403**, và vai trò đúng **thành công**.
2. Có test `POST` với token CSRF hợp lệ và trường hợp token sai/thiếu nếu ứng dụng cần CSRF.
3. Có negative test cho route hoặc HTTP method **chưa cấp quyền** và các endpoint quản trị được expose.
4. Dùng production `SecurityFilterChain`; không có profile test tự động mở quyền, không tắt filter trong `MockMvc`.
5. `ApplicationModules.verify()` thành công, đồng thời test không xem kết quả đó là bằng chứng thay thế phân quyền HTTP.

Nên thực hiện một **mutation check có kiểm soát trên nhánh tạm**: thử đổi `anyRequest().denyAll()` thành `permitAll()` rồi chạy lại bộ test. Những test route chưa liệt kê ở mục 6 phải thất bại. Hoàn nguyên thay đổi ngay sau khi quan sát kết quả. Nếu tất cả test vẫn xanh, bộ test chưa bảo vệ được chính mục tiêu “cấu hình mặc định không mở quyền”.

**Tình huống thực hành:** nhóm `orders` thêm `GET /api/orders/export` nhưng quên cập nhật access policy. Với cấu hình `denyAll`, request bị từ chối cho đến khi team quy định vai trò hợp lệ và thêm test cho cả trường hợp được phép/bị từ chối. Như vậy một endpoint mới không trở thành API công khai chỉ vì đã được deploy.

**Tài liệu đối chiếu:** [Spring Security – MockMvc setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html), [Spring Security – CSRF tests](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html), [Spring Modulith – Integration Testing](https://docs.spring.io/spring-modulith/reference/testing.html), [Spring Modulith – Verification](https://docs.spring.io/spring-modulith/reference/verification.html).
