# Kiểm thử security filter và danh tính người gọi

## 1. Vì sao security phải là một phần của hợp đồng HTTP?

Trong hệ thống nhiều dịch vụ, hợp đồng không chỉ mô tả `GET /api/orders/42` trả JSON nào. Consumer còn phụ thuộc vào **ai được phép gọi API**, phải gửi thông tin xác thực ra sao và producer phản hồi thế nào khi người gọi chưa đăng nhập hoặc không có quyền. Một thay đổi security filter có thể phá vỡ consumer dù controller và DTO hoàn toàn không đổi.

Ví dụ, `Checkout Service` là consumer của `Order Service` (producer):

- Người gọi có vai trò `ORDER_READ` được xem thông tin đơn hàng.
- Không cung cấp thông tin xác thực thì API trả `401 Unauthorized`.
- Đã xác thực nhưng không có vai trò phù hợp thì API trả `403 Forbidden`.
- Khi được phép truy cập, API trả `200 OK` và body đơn hàng theo hợp đồng.

**Spring Cloud Contract** cho phép diễn đạt các trường hợp này bằng Groovy hoặc YAML DSL, sinh kiểm thử ở producer, phát hành stub đã được xác minh và để consumer chạy kiểm thử qua **Stub Runner**. Đưa các tình huống security vào CI giúp phát hiện việc vô tình mở công khai endpoint, thay đổi cách xác thực hoặc trả mã lỗi không còn tương thích.

Sau bài học, bạn có thể:

1. Phân biệt **authentication**, **authorization**, danh tính người gọi và security filter chain.
2. Viết các hợp đồng HTTP cho người gọi hợp lệ, chưa xác thực và không đủ quyền.
3. Thiết lập base test class để security filter thực sự chạy trong producer verification.
4. Phân biệt kiểm thử bằng user giả, thông tin xác thực thật trong môi trường test và stub mô phỏng.
5. Nhận diện lỗi `401`/`403` do token, role, CSRF, tenant hoặc cách cấu hình MockMvc.
6. Thiết kế quy trình CI bảo đảm security contract không bị bỏ qua.

## 2. Xác thực, phân quyền và danh tính người gọi là ba khái niệm liên quan

### 2.1. Authentication: người gọi là ai?

**Authentication (xác thực)** là bước kiểm tra chứng cứ danh tính: tên người dùng và mật khẩu, HTTP Basic, bearer token/JWT, session cookie, mTLS hoặc cơ chế do hệ thống quy định.

Sau khi xác thực thành công, Spring Security thường lưu một đối tượng `Authentication` trong `SecurityContext` của request. Từ đó có thể truy cập:

- `authentication.getName()`: định danh được Spring Security nhận diện.
- `authentication.getPrincipal()`: principal, có thể là `UserDetails`, `Jwt` hoặc kiểu riêng.
- `authentication.getAuthorities()`: các quyền/role đã được gắn cho danh tính.

Giá trị `getName()` và kiểu `principal` phụ thuộc cơ chế xác thực. Không nên giả định JWT subject, email, tên tài khoản và tenant ID luôn là cùng một trường.

### 2.2. Authorization: người gọi được làm gì?

**Authorization (phân quyền)** kiểm tra danh tính đã được xác thực có quyền làm thao tác hay truy cập tài nguyên cụ thể không. Ví dụ:

- `ROLE_ORDER_READ` được xem đơn hàng.
- `ROLE_ORDER_ADMIN` được hủy đơn hàng.
- Một người dùng chỉ được xem đơn hàng **thuộc chính mình hoặc tenant của mình**, kể cả khi có role đọc đơn hàng.

Role là điều kiện cần trong nhiều hệ thống, nhưng không phải lúc nào cũng đủ: việc truy cập `/api/orders/42` còn có thể phụ thuộc **chủ sở hữu tài nguyên** và **tenant**.

### 2.3. Security filter chain nằm ở đâu?

Với Spring Security trên Spring MVC, request đi qua `SecurityFilterChain` trước khi controller xử lý. Các filter và cơ chế liên quan có thể xác thực thông tin, khôi phục security context, thực hiện kiểm tra CSRF hoặc điều hướng lỗi truy cập.

```mermaid
sequenceDiagram
    participant C as Consumer
    participant S as Spring Security Filters
    participant A as Controller / Service
    C->>S: GET /api/orders/42 + Authorization
    alt Không xác thực được
        S-->>C: 401 (hoặc cơ chế entry point đã cấu hình)
    else Xác thực được nhưng thiếu quyền
        S-->>C: 403
    else Được phép
        S->>A: Request + Authentication/Principal
        A-->>S: Response đơn hàng
        S-->>C: 200 + JSON
    end
```

Một contract test chỉ gửi request **thẳng tới controller không qua filter** sẽ không kiểm chứng được đầy đủ các trường hợp trên.

## 3. Hiểu đúng các mã HTTP khi kiểm thử security

| Trạng thái | Ý nghĩa thông thường | Ví dụ kiểm thử |
| --- | --- | --- |
| `200 OK` | Request được phép và xử lý thành công | Người dùng có `ORDER_READ` lấy đơn hàng |
| `401 Unauthorized` | Request chưa có xác thực hợp lệ theo cơ chế API | Thiếu hoặc sai thông tin HTTP Basic; token bearer không hợp lệ |
| `403 Forbidden` | Server hiểu request nhưng từ chối quyền truy cập | Đã xác thực nhưng không có `ORDER_READ`; hoặc bị chặn bởi CSRF |
| `302 Found` | Một số ứng dụng web chuyển hướng sang trang đăng nhập | Session/form login thay vì API thuần túy trả `401` |
| `404 Not Found` | Tài nguyên không tìm thấy, đôi khi được dùng để không tiết lộ sự tồn tại | Tài nguyên không thuộc phạm vi người gọi theo chính sách API |

**Không mặc định mọi request chưa đăng nhập đều trả `401`.** Hành vi thực tế phụ thuộc `AuthenticationEntryPoint`, form login, Basic/Bearer, `Accept`, cấu hình security và cả API gateway. Với API REST sử dụng HTTP Basic trong ví dụ xuyên suốt của bài, ba tình huống `200`, `401`, `403` là lựa chọn rõ ràng.

HTTP `401` trong Basic authentication thường đi kèm header `WWW-Authenticate`. Chỉ đưa header, realm hoặc thông báo lỗi vào hợp đồng nếu consumer thực sự phụ thuộc chúng; giá trị chính xác phải khớp cấu hình ứng dụng, không nên tự giả định.

## 4. Thiết kế ví dụ: `GET /api/orders/42`

Giả sử ứng dụng Spring Boot dùng Spring Security với quy tắc:

1. `GET /api/orders/**` đòi vai trò `ORDER_READ`.
2. Client xác thực bằng HTTP Basic trong môi trường ví dụ.
3. Controller trả JSON `{"orderId":42,"status":"CREATED"}` nếu dữ liệu đã được chuẩn bị.

Một cấu hình Java minh họa **chính sách bảo mật của ứng dụng**:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasRole("ORDER_READ")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đoạn cấu hình minh họa Spring Security hiện đại. Trong môi trường sản xuất, cơ chế xác thực, quy tắc đường dẫn, khả năng truy cập theo tenant và các filter khác phải được thiết kế đầy đủ. Đừng đưa tài khoản/mật khẩu thử nghiệm vào cấu hình production.

Để tái lập các kịch bản, bộ test cần có các danh tính thử nghiệm:

| Danh tính thử nghiệm | Password chỉ dùng trong test | Quyền | Kết quả mong đợi |
| --- | --- | --- | --- |
| `reader` | `password` | `ROLE_ORDER_READ` | `200` |
| `viewer` | `password` | `ROLE_VIEWER` | `403` |
| Không gửi credential | Không có | Không có | `401` |

**Lưu ý an toàn:** Các credential trong bài là **giả định, chỉ dành cho môi trường test bị cô lập**; không dùng trong hệ thống triển khai, không đăng mật khẩu thật hoặc bearer token thật vào hợp đồng/version control. Nếu dùng cơ chế sản xuất như OAuth2/JWT, nên tạo danh tính hoặc token thử nghiệm có thời hạn/phạm vi rõ ràng.

## 5. Ba hợp đồng Groovy DSL cho cùng một endpoint

Mỗi tình huống cần một hợp đồng riêng: một request hợp lệ, một request chưa xác thực, một request đã xác thực nhưng không đủ quyền.

### 5.1. Có quyền: `200 OK`

Ví dụ `get_order_authorized.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Reader hop le lay duoc don hang'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Authorization', 'Basic cmVhZGVyOnBhc3N3b3Jk')
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 42,
            status: 'CREATED'
        )
    }
}
```

Giá trị Basic trong ví dụ biểu diễn `reader:password` bằng Base64, **không phải mã hóa bảo mật**. Với HTTP Basic, thông tin xác thực phải được bảo vệ bằng HTTPS trong giao tiếp thật; test nội bộ chỉ dùng tài khoản giả.

Contract bảo vệ cả hai phía: producer test phải nhận `200` và body phù hợp khi gửi credential hợp lệ; Stub Runner có thể mô phỏng response `200` cho request khớp những điều kiện tương ứng.

### 5.2. Thiếu xác thực: `401 Unauthorized`

Ví dụ `get_order_unauthenticated.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Request khong co credential bi tu choi'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status UNAUTHORIZED()
    }
}
```

Generated producer test gửi request **không có `Authorization`**, từ đó xác minh security filter từ chối request ở mã `401` trong cấu hình Basic đã chọn. Không đưa body lỗi vào hợp đồng nếu consumer không phụ thuộc định dạng body đó.

**Lưu ý quan trọng về stub:** Việc *không khai báo* header `Authorization` không phải lúc nào cũng có nghĩa WireMock mapping được sinh sẽ có điều kiện **header phải vắng mặt**. Một mapping chỉ có method/URL có thể khớp cả request có credential, gây xung đột với mapping của `200`. Khi phát hành cả ba stub cho cùng endpoint, phải kiểm tra **mapping được sinh, mức độ ưu tiên và điều kiện absence** theo phiên bản Spring Cloud Contract/WireMock đang dùng. Nếu cần diễn đạt header vắng mặt tường minh, chỉ áp dụng cú pháp matcher được phiên bản DSL hỗ trợ và xác minh bằng consumer test thực tế.

### 5.3. Đã xác thực nhưng không đủ quyền: `403 Forbidden`

Ví dụ `get_order_forbidden.groovy`:

```groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Viewer khong du role xem don hang'

    request {
        method GET()
        url '/api/orders/42'
        headers {
            header('Authorization', 'Basic dmlld2VyOnBhc3N3b3Jk')
            header('Accept', 'application/json')
        }
    }

    response {
        status FORBIDDEN()
    }
}
```

Credential ví dụ biểu diễn `viewer:password`, là danh tính tồn tại nhưng chỉ có `ROLE_VIEWER`. Khi security filter chain dùng `hasRole("ORDER_READ")`, tài khoản này đã xác thực nhưng không được truy cập.

**Đừng đánh đồng `403` với “sai password”.** Khi mật khẩu sai, HTTP Basic thường cho `401`; còn role không đủ, hoặc một chính sách bảo mật khác từ chối request đã xác thực, có thể cho `403`.

### 5.4. Vì sao ba hợp đồng phải có dữ liệu test độc lập?

| Hợp đồng | Credential trong request | Kết quả producer verification |
| --- | --- | --- |
| Authorized | `reader` với `ROLE_ORDER_READ` | `200`, đúng JSON |
| Unauthenticated | Không gửi credential | `401` |
| Forbidden | `viewer` đã xác thực nhưng thiếu role | `403` |

Nếu `viewer` không tồn tại trong môi trường test, hợp đồng thứ ba dễ trả `401` thay vì `403`, khiến test không kiểm chứng được phân quyền. Đây là lý do fixture phải tái lập được cả **trạng thái xác thực** và **tập quyền**.

## 6. Hợp đồng YAML tương đương

Với YAML DSL, request/response có cùng ý nghĩa:

```yaml
description: Reader hop le lay duoc don hang
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: "Basic cmVhZGVyOnBhc3N3b3Jk"
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: 42
    status: CREATED
```

Trường hợp bị từ chối vì role:

```yaml
description: Viewer khong du role xem don hang
request:
  method: GET
  url: /api/orders/42
  headers:
    Authorization: "Basic dmlld2VyOnBhc3N3b3Jk"
    Accept: application/json
response:
  status: 403
```

Trường hợp không xác thực:

```yaml
description: Thieu credential
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 401
```

Trong YAML, `response.status` là mã HTTP; `request.headers.Authorization` là header gửi vào producer. Không nên ghi nhầm bearer token hoặc Basic credential vào `response`.

Những ví dụ này dựa trên một API dùng Basic authentication. Nếu API thật sử dụng JWT, cookie hoặc mTLS, phải **thiết kế hợp đồng phù hợp cơ chế thật**, không sao chép Basic chỉ vì nó đơn giản hơn.

## 7. Cấu hình test base class để security filter thực sự chạy

Producer verification chỉ đáng tin khi request từ generated test đi qua **filter chain đang bảo vệ API**. Với Spring Boot MVC và Spring Security, một base class minh họa:

```java
package com.example.orders.contract;

import io.restassured.module.mockmvc.RestAssuredMockMvc;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc(addFilters = true)
@ActiveProfiles("contract")
public abstract class HttpSecurityContractBase {

    @Autowired
    protected MockMvc mockMvc;

    @BeforeEach
    protected void setupMockMvc() {
        RestAssuredMockMvc.mockMvc(mockMvc);
    }
}
```

Điểm cần chú ý:

- `@SpringBootTest` khởi động test context của producer, nơi có `SecurityFilterChain`.
- `@AutoConfigureMockMvc(addFilters = true)` yêu cầu Spring Boot đăng ký các filter của application context khi tạo MockMvc. Trong cấu hình Spring Boot phù hợp, đây thường là hành vi mặc định nhưng nên ghi tường minh ở bài kiểm thử security.
- `RestAssuredMockMvc.mockMvc(mockMvc)` kết nối client mà các generated tests ở chế độ MockMvc có thể sử dụng.
- `@ActiveProfiles("contract")` cho phép nạp credential/fixture dành riêng cho test nếu project thiết kế profile đó.

**Chỉ bật filter chưa chắc đã kiểm thử toàn bộ hệ thống an ninh.** Những thành phần nằm ở API gateway, reverse proxy, external identity provider hoặc hạ tầng mạng không tự xuất hiện trong MockMvc. Cần integration/E2E test bổ sung cho các ranh giới đó.

### 7.1. Hai cách cấu hình làm mất giá trị security test

Không nên dùng:

```java
@AutoConfigureMockMvc(addFilters = false)
```

trong nhóm contract tests đang muốn bảo vệ authentication/authorization. Khi bỏ filter, endpoint có thể trả `200` dù request không có credential, làm test `401` hoặc `403` không còn đại diện cho API thực.

Cũng cần thận trọng với:

```java
MockMvcBuilders.standaloneSetup(controller).build();
```

Stand-alone MockMvc chỉ cấu hình controller được đưa vào, không tự tái tạo toàn bộ Spring Security filter chain. Nó phù hợp cho nhiều unit test của controller nhưng **không tự đủ** để xác minh một security contract nếu không chủ động áp dụng các thành phần security tương ứng.

Nếu generated tests dùng test mode khác như `EXPLICIT` hay REST Assured trên server thật, base class phải setup cơ chế đó, không thể sao chép nguyên MockMvc base class rồi kỳ vọng luôn chạy.

### 7.2. Cấu hình plugin chọn đúng test base

Một cấu hình Maven minh họa:

```xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>${spring-cloud-contract.version}</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>MOCKMVC</testMode>
        <baseClassForTests>com.example.orders.contract.HttpSecurityContractBase</baseClassForTests>
    </configuration>
</plugin>
```

Phiên bản Spring Cloud Contract plugin phải phù hợp với dependency Verifier do Spring Cloud BOM quản lý; property `${spring-cloud-contract.version}` cần được định nghĩa trong POM/parent POM. Các test dependency (Spring Boot Test, Security test và Spring Cloud Contract Verifier) cũng phải có mặt trên test classpath.

Khi hệ thống có nhiều nhóm hợp đồng (HTTP public, HTTP protected, messaging), có thể dùng `baseClassMappings` để nhóm security kế thừa một base class có filter và fixture phù hợp, thay vì áp cùng một cấu hình cho mọi hợp đồng.

## 8. Chuẩn bị danh tính và quyền thử nghiệm

Hợp đồng `reader` và `viewer` chỉ chạy đúng nếu cơ chế authentication trong test context thực sự nhận hai tài khoản đó. Một giải pháp dành cho **bài thực hành cô lập** là có `UserDetailsService` test-only cung cấp tài khoản in-memory:

```java
package com.example.orders.contract;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
public class ContractUsersConfiguration {

    @Bean
    UserDetailsService contractUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}password")
                .roles("ORDER_READ")
                .build(),
            User.withUsername("viewer")
                .password("{noop}password")
                .roles("VIEWER")
                .build()
        );
    }
}
```

Trong base class, có thể dùng `@Import(ContractUsersConfiguration.class)` để đăng ký cấu hình test này, **nếu** kiến trúc bảo mật của ứng dụng đang dùng `UserDetailsService` và có thể chọn chính xác bean test đó. Nếu project đã có nhiều `AuthenticationProvider` hoặc cơ chế LDAP/OAuth2 khác, việc thêm bean không nhất thiết làm producer test xác thực qua nó; phải kiểm tra luồng thực sự.

**Chú ý:** `{noop}password` là cách viết không mã hóa dành riêng cho demo/test cô lập, không được áp dụng cho tài khoản thật. Khi dùng Basic authentication, credential xuất hiện trong hợp đồng chỉ là dữ liệu thử nghiệm. Với hệ thống có yêu cầu bảo mật cao, nên dùng test credentials được quản lý theo quy trình nội bộ, không hard-code bí mật có hiệu lực thực.

### 8.1. Role và authority không hoàn toàn đồng nghĩa

Trong Spring Security, `hasRole("ORDER_READ")` thường so khớp authority `ROLE_ORDER_READ`, còn `hasAuthority("ORDER_READ")` so khớp chính xác authority `ORDER_READ`. Nếu token JWT chứa scope `orders.read`, ứng dụng có thể chuyển nó thành `SCOPE_orders.read`, hoàn toàn khác vai trò `ROLE_ORDER_READ`.

Vì vậy, khi test `403` cần biết:

- Principal thực sự có những authority nào?
- Security rule dùng `hasRole`, `hasAuthority`, `@PreAuthorize` hay chính sách khác?
- Cơ chế xác thực có map claim JWT thành authority như mong đợi không?

Một user giả có tên đúng nhưng authority sai có thể khiến test cho `403` trong khi mục đích ban đầu là kiểm thử `200`.

### 8.2. Tài khoản test không thay thế kiểm tra danh tính gắn với tài nguyên

Ngay cả người dùng có vai trò `ORDER_READ` cũng không nhất thiết được phép xem mọi đơn hàng. Quy tắc thực tế có thể là “được xem đơn hàng thuộc tenant của mình”.

Ví dụ:

| Người gọi | Tài nguyên | Chính sách giả định | Kỳ vọng |
| --- | --- | --- | --- |
| `reader` thuộc `tenant-a` | Đơn hàng của `tenant-a` | Đủ role và đúng tenant | `200` |
| `reader` thuộc `tenant-a` | Đơn hàng của `tenant-b` | Đủ role nhưng khác tenant | `403` hoặc `404` theo API |
| `viewer` thuộc `tenant-a` | Đơn hàng của `tenant-a` | Không đủ role | `403` |

Nếu consumer cần bảo đảm không lộ dữ liệu xuyên tenant, phải viết **hợp đồng hoặc kiểm thử authorization bổ sung** cho tình huống này, không chỉ test `hasRole` ở đường dẫn tổng quát. Thông tin tenant cần được lấy từ nguồn đáng tin (ví dụ claim token đã xác minh hoặc session server-side), **không** mặc nhiên tin một header `X-Tenant-Id` do client tự khai báo.

## 9. Dùng `@WithMockUser` hay gửi credential thực qua HTTP?

Spring Security Test hỗ trợ `@WithMockUser` và các `RequestPostProcessor` như `user(...)`, `jwt(...)` để tạo security context trong test. Chúng có ích, nhưng phải hiểu **chúng kiểm thử lớp nào**.

| Cách tạo danh tính | Kiểm chứng được gì? | Giới hạn |
| --- | --- | --- |
| `@WithMockUser` | Authorization theo principal/authorities đã giả lập | Không chứng minh parser HTTP Basic, JWT decoder hoặc xác minh chữ ký token hoạt động |
| MockMvc `.with(user("reader"))` | Phân quyền cho request với user thử nghiệm | Không phải bằng chứng credential thực đã được xử lý đúng |
| MockMvc `.with(jwt())` | Quy tắc authorization dựa trên principal/claims được mô phỏng | Có thể bỏ qua phần xác minh chữ ký, issuer, audience hoặc expiry |
| Gửi Basic credential qua filter chain thật | Authentication Basic và role mapping trong test context | Chưa kiểm tra gateway/mTLS/IdP bên ngoài |
| Gửi JWT test được ký qua resource server config thật | Một phần quy trình Bearer/JWT decoder và claim mapping | Phụ thuộc test issuer/key/clock; chưa đảm bảo môi trường production IdP |

Ví dụ một kiểm thử Spring Security Test viết thủ công:

```java
@Test
@WithMockUser(username = "reader", roles = "ORDER_READ")
void readerCanAccessOrder() throws Exception {
    mockMvc.perform(get("/api/orders/42"))
        .andExpect(status().isOk());
}
```

Đây là ví dụ **kiểm tra phân quyền**. Nó không chứng minh rằng request thiếu hoặc sai header `Authorization` sẽ bị filter từ chối, vì security context đã được tạo sẵn trong test.

**Trong generated contract tests, `@WithMockUser` áp dụng ở base class có thể làm sai mục tiêu:** nếu mọi test đều được gắn sẵn principal, trường hợp “không gửi credential” vẫn có thể được xử lý như người dùng đã đăng nhập. Với các hợp đồng đang kiểm tra **authentication**, ưu tiên gửi HTTP credential thử nghiệm qua filter như consumer thật.

## 10. OAuth2/JWT: kiểm thử đúng ranh giới

Nhiều microservice sử dụng `Authorization: Bearer <token>` thay vì Basic. Khi đó cần tách ít nhất ba trường hợp:

1. **Không có bearer token:** tùy cấu hình, resource server thường trả `401`.
2. **Token hỏng, hết hạn hoặc sai issuer/audience:** cần kiểm tra đường xử lý xác thực và phản hồi đã công bố.
3. **Token hợp lệ nhưng thiếu scope/authority:** thường trả `403` ở endpoint bảo vệ bằng quyền cụ thể.

Để kiểm thử authentication thực sự, một token phải hợp lệ theo cấu hình **test decoder/verifier** hoặc được ký bằng khóa thử nghiệm mà ứng dụng test tin cậy. Đừng chép JWT sản xuất, refresh token, client secret hoặc khóa riêng thật vào hợp đồng.

Ví dụ hợp đồng có thể yêu cầu:

```groovy
request {
    method GET()
    url '/api/orders/42'
    headers {
        header('Authorization', 'Bearer TEST_TOKEN_VALUE')
    }
}
```

Đây **chỉ là đoạn mô tả**, không phải token hợp lệ hoặc contract hoàn chỉnh. Trước khi chạy test, phải thay `TEST_TOKEN_VALUE` bằng credential thử nghiệm được thiết kế có thể tái lập, phù hợp chính sách JWT của ứng dụng; nếu token tự hết hạn trong CI, cần cách cấp mới có kiểm soát hoặc dùng clock/issuer test phù hợp.

Không được coi `@WithMockUser` hay `.with(jwt())` là thay thế hoàn toàn cho bài kiểm thử signature/issuer/audience/expiry. Chúng rất hữu ích cho authorization, nhưng bài kiểm thử authentication cần đi qua chuỗi giải mã và xác minh phù hợp.

### 10.1. Có nên khẳng định toàn bộ body lỗi của JWT?

Chỉ khi consumer thật sự cần một schema lỗi ổn định. Hành vi `WWW-Authenticate`, mã lỗi, thông điệp và body của `401`/`403` có thể phụ thuộc Spring Security, `AuthenticationEntryPoint`, `AccessDeniedHandler` hoặc handler riêng. Thay vì khóa một thông điệp tiếng Anh có thể đổi theo phiên bản, hãy bảo vệ mã HTTP và trường error code được thỏa thuận với consumer.

## 11. CSRF có thể làm nhầm kết quả `403`

Spring Security thường bật bảo vệ **CSRF** cho các thao tác thay đổi trạng thái khi ứng dụng dùng session/cookie. Request `POST`, `PUT`, `PATCH`, `DELETE` không có CSRF token hợp lệ có thể bị từ chối `403`, **ngay cả khi principal có quyền**.

Ví dụ:

```text
POST /api/orders/42/cancel
Authorization: Basic <credential hợp lệ>
Content-Type: application/json

{}
```

Nếu test trả `403`, không nên kết luận ngay rằng role bị thiếu. Cần xác định do **CSRF**, chính sách phân quyền hay vấn đề xác thực.

Với một API stateless chỉ chấp nhận bearer token và không dùng cookie tự động trong browser, chính sách CSRF có thể được thiết kế khác. **Không tắt CSRF chỉ để làm contract test xanh**. Khi bảo vệ CSRF là một phần giao diện, phải chuẩn bị token/cookie hợp lệ trong test và thêm các trường hợp thiếu token nếu consumer cần xử lý lỗi đó.

Spring Security Test có thể cấp CSRF test token cho MockMvc với `.with(csrf())`; cách đó hỗ trợ một số kiểm thử tích hợp nhưng **không tự động xuất hiện trong generated contract tests**. Nếu producer test từ DSL gửi HTTP request thông thường, cần cấu hình base class hoặc dữ liệu request phù hợp với cách CSRF thực sự vận hành.

## 12. Stub Runner có kiểm tra security filter thật không?

**Không.** Stub Runner có thể sử dụng WireMock để mô phỏng phản hồi `200`, `401`, `403` từ những hợp đồng đã mô tả. Nó không tự khởi động security filter chain hay xác minh credential bằng `AuthenticationManager` của producer.

```mermaid
flowchart TD
    A["Hợp đồng HTTP security"] --> B["Sinh producer verification"]
    A --> C["Sinh HTTP stubs"]
    B --> D["Gửi request qua Spring Security filters thực trong test"]
    D --> E["Xác minh status/header/body"]
    E --> F{"Producer verification đạt?"}
    F -->|Không| G["Chặn build/publish stub"]
    F -->|Có| H["Phát hành stub đã kiểm chứng"]
    C --> H
    H --> I["Consumer dùng Stub Runner"]
    I --> J["Kiểm thử client gửi credential và xử lý 200/401/403"]
```

Hai mặt kiểm thử khác nhau:

| Producer verification | Consumer test với Stub Runner |
| --- | --- |
| Gửi request tới application context có security filters | Gửi request tới stub server |
| Xác minh producer áp dụng authentication/authorization như đã cam kết | Xác minh consumer có gửi đúng header và xử lý các response mẫu |
| Phát hiện filter vô tình bị tắt, role mapping thay đổi hoặc response sai | Phát hiện client bỏ header hoặc không xử lý tình huống `401`/`403` |
| Không tự kiểm tra mọi consumer | Không tự chứng minh producer hiện tại còn áp dụng đúng security policy |

**Cảnh báo matcher:** Nếu nhiều stub cùng dùng `GET /api/orders/42` nhưng một mapping `401` không ràng buộc việc thiếu header, các mapping có thể chồng lấn. Phải kiểm tra stub mapping thực tế, độ ưu tiên và consumer tests cho cả ba tình huống; không mặc nhiên suy rằng WireMock phân biệt đúng chỉ dựa vào tên tệp hợp đồng.

## 13. Khi nào nên kiểm thử security ở tầng nào?

Không phải mọi yêu cầu security đều được bảo vệ tốt nhất bằng contract test. Một chiến lược nhiều lớp:

| Mục tiêu | Loại kiểm thử phù hợp |
| --- | --- |
| API trả `401` khi thiếu credential | Producer contract test đi qua filter thật |
| API trả `403` khi thiếu role/scope | Producer contract test + Spring Security integration test |
| Consumer thêm `Authorization` header vào request | Consumer contract test bằng HTTP client thực với Stub Runner |
| JWT ký sai hoặc hết hạn bị từ chối | Security integration test với decoder/verifier thật trong test |
| Người dùng không truy cập đơn hàng người khác | Authorization/service test và các hợp đồng tiêu biểu |
| CSRF/session/cookie hoạt động đúng | Spring MVC/security integration test với request state thực |
| Gateway, mTLS, reverse proxy, IdP hoạt động | Integration/E2E test trong hạ tầng phù hợp |
| Chống brute force, rate limit, log bảo mật | Test bảo mật/vận hành chuyên biệt |

Contract test giúp phát hiện **đứt giao diện** trong những tương tác đã mô tả, không thay thế kiểm thử xâm nhập, threat modeling hoặc đánh giá bảo mật toàn hệ thống.

## 14. Những lỗi phổ biến và cách chẩn đoán

### Lỗi 1: Request không có credential vẫn trả `200`

**Khả năng:** MockMvc không đăng ký security filters, endpoint bị `permitAll`, base class đã gắn `@WithMockUser`, hoặc test mode chỉ chạy controller.

**Xử lý:** Xem `SecurityFilterChain`, `@AutoConfigureMockMvc(addFilters = true)`, profile và base class; chạy thử cả request không có header. Đừng sửa hợp đồng `401` thành `200` chỉ để test xanh nếu API yêu cầu xác thực.

### Lỗi 2: Test kỳ vọng `403` nhưng nhận `401`

**Khả năng:** User `viewer` chưa tồn tại, credential không đúng, password encoder không khớp, hoặc token không được verifier chấp nhận.

**Xử lý:** Xác nhận request đã **xác thực thành công** trước khi kiểm tra role. Kiểm tra log authentication và authorities của principal trong môi trường test, không ghi lộ secret.

### Lỗi 3: Test kỳ vọng `401` nhưng nhận `302`

**Khả năng:** Ứng dụng dùng form login hoặc entry point chuyển hướng; `Accept` và cấu hình security ảnh hưởng hành vi.

**Xử lý:** Xác minh giao diện API thực sự cam kết JSON/HTTP status nào. Với API stateless, cấu hình security/entry point cho đúng yêu cầu thay vì đổi contract theo kết quả vô tình.

### Lỗi 4: Request có role hợp lệ nhưng nhận `403`

**Khả năng:** Sai prefix `ROLE_`, thiếu scope, chính sách tenant/owner, CSRF token hoặc method security.

**Xử lý:** Xem `Authentication.authorities`, `hasRole`/`hasAuthority`, log AccessDeniedHandler và loại request. Với POST, kiểm tra CSRF trước khi thay role.

### Lỗi 5: Consumer test luôn nhận `401` dù gửi credential hợp lệ

**Khả năng:** Stub `401` có matcher quá rộng và trùng URL với stub `200`; không có absence matcher/priority phù hợp.

**Xử lý:** Xem generated WireMock mappings và log unmatched/near-miss. Xác định request thực tế có header gì và mapping nào được ưu tiên; thêm điều kiện khớp chính xác phù hợp phiên bản DSL.

### Lỗi 6: Contract test xanh nhưng truy cập chéo tenant vẫn được phép

**Khả năng:** Hợp đồng chỉ kiểm tra role, chưa bao gồm quyền sở hữu tài nguyên hoặc tenant. `X-Tenant-Id` không được đối chiếu với principal đáng tin.

**Xử lý:** Thêm kiểm thử authorization ở lớp service và hợp đồng tiêu biểu cho tài nguyên khác tenant; không dựa riêng vào role rộng.

### Lỗi 7: CI xanh nhưng không chạy generated tests

**Khả năng:** Plugin không sinh test, test class không được discover, task/goal bị skip hoặc nhóm hợp đồng bị loại khỏi quá trình build.

**Xử lý:** Kiểm tra output generator, số lượng test sinh ra và số test đã chạy; chặn pipeline khi nhóm security quan trọng đột ngột có 0 test.

## 15. Quy trình thực hành đầy đủ

Một nhóm triển khai security contract nên:

1. **Chốt chính sách API:** xác định danh tính, loại credential, role/scope, tenant và status `200`/`401`/`403` cho từng tình huống.
2. **Viết hợp đồng phân biệt các trạng thái:** mỗi request có input rõ ràng; tránh các stub mappings chồng lấn.
3. **Chuẩn bị fixture xác thực:** có tài khoản/token hợp lệ và user thiếu quyền; không dùng credential thật hoặc secret production.
4. **Cấu hình base test đúng:** Spring context chứa security filters, MockMvc đăng ký filters, không áp `@WithMockUser` cho mọi bài kiểm thử authentication.
5. **Sinh và chạy producer contract tests:** xác nhận request đã đi qua filter và response status/header/body đúng cam kết.
6. **Thực hiện kiểm thử âm tính có chủ đích:** bỏ credential, dùng credential sai, thiếu role và thử truy cập chéo tenant nếu API yêu cầu.
7. **Xem generated stub mappings:** đặc biệt các tình huống cùng method/URL nhưng khác Authorization.
8. **Chỉ phát hành stub sau khi verification đạt:** consumer dùng Stub Runner kiểm tra client gửi credential và xử lý response.
9. **Tích hợp CI:** ghim phiên bản Spring Boot/Cloud/Contract, kiểm tra test count, phân loại lỗi xác thực/phân quyền và chặn phát hành khi API không tương thích.

## 16. Bài tập tự kiểm tra

Giả sử `Inventory Service` có `GET /api/inventory/sku-1`, sử dụng HTTP Basic:

- `stock-reader` có `ROLE_STOCK_READ` được trả `200` và body `{"sku":"sku-1","available":12}`.
- `support-user` đã xác thực nhưng không có `STOCK_READ`, nhận `403`.
- Không có credential, nhận `401`.
- Hệ thống cũng có API `POST /api/inventory/reserve` có bảo vệ CSRF theo chính sách đã công bố.

Hãy thực hành:

1. Viết ba hợp đồng HTTP riêng cho `200`, `401`, `403` bằng Groovy hoặc YAML DSL.
2. Với `401`, vì sao việc **không khai báo Authorization header** trong hợp đồng chưa chắc tạo được stub chỉ khớp request thiếu header?
3. Nếu generated producer test cho `403` trả `401`, bạn sẽ kiểm tra credential hay role trước?
4. Vì sao `@AutoConfigureMockMvc(addFilters = false)` làm mất giá trị của bài kiểm thử security?
5. Nếu `POST /api/inventory/reserve` trả `403` với user đủ quyền, ngoài role bạn cần kiểm tra điều gì?
6. Nếu `stock-reader` truy cập tồn kho tenant khác, hợp đồng mới cần mô tả thêm chính sách nào?

**Gợi ý đáp án:**

| Câu | Ý chính |
| --- | --- |
| 1 | Các contract tách rõ credential và status; `200` kiểm tra thêm body |
| 2 | Stub mapping có thể chỉ khớp method/URL, cần điều kiện thiếu header tường minh nếu phiên bản hỗ trợ và kiểm tra mapping |
| 3 | Xác nhận user **đã xác thực**; chỉ khi xác thực thành công mới có ý nghĩa kiểm tra thiếu quyền |
| 4 | Request có thể bypass security filter, không còn bảo vệ authentication/authorization |
| 5 | Kiểm tra CSRF token, cùng các rule/handler khác đang áp dụng |
| 6 | Quyền sở hữu tài nguyên/tenant gắn với danh tính đã được xác minh, không tin tenant client tự khai báo |

### Thử nghiệm âm tính nên có trong CI

Sau khi có producer tests, chủ động kiểm tra các tình huống sai (trong nhánh thử nghiệm hoặc môi trường test cô lập): vô tình mở `permitAll`, loại một role bắt buộc, tắt filter hoặc đổi đường dẫn bảo vệ. Những thay đổi đó phải khiến bài kiểm thử tương ứng **thất bại**. Nếu vẫn xanh, cần xem lại base class, số lượng generated tests và các điều kiện DSL đã được thực thi.

## 17. Checklist trước khi merge

- Contract có phân biệt đúng **chưa xác thực** và **đã xác thực nhưng không đủ quyền**?
- Các credential, token và danh tính trong test có phải dữ liệu giả, không phải secret còn hiệu lực?
- `SecurityFilterChain` thực sự tham gia producer verification, không bị tắt bởi MockMvc hay profile?
- Base class không tự gắn `@WithMockUser` cho tình huống cần kiểm tra credential vắng mặt?
- `hasRole`/`hasAuthority` và prefix `ROLE_`/`SCOPE_` có khớp fixture test?
- Các ca POST/PUT/DELETE có xem xét CSRF theo chính sách API?
- Quyền theo tài nguyên/tenant đã được kiểm tra ngoài role khi nghiệp vụ yêu cầu?
- Nhiều stub cùng endpoint có matcher rõ ràng, không vô tình để mapping `401` khớp request hợp lệ?
- CI có chạy generated producer tests và chỉ phát hành stub đã xác minh cho consumer qua Stub Runner?

**Tài liệu tham khảo để đối chiếu theo phiên bản:**

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html).
- [Spring Cloud Contract — Contract Verifier](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html).
- [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html).
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

**Ghi nhớ:** Một hợp đồng HTTP có yếu tố bảo mật phải xác minh **request đi qua security filter thực**, **principal/authorities được nhận diện đúng**, và **response tương ứng với chính sách truy cập**. Với Spring Cloud Contract, mô tả riêng các tình huống `200`, `401`, `403`, chuẩn bị dữ liệu test cô lập, kiểm tra generated producer tests và stub mappings, rồi tích hợp cả producer verification lẫn consumer tests vào CI. Một Stub Runner trả `403` không tự chứng minh producer thật đang phân quyền đúng.
