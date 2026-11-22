# Kiểm tra Principal, SecurityContext và quyền thực hiện thao tác

## 1. Biết người gọi và quyết định quyền là hai việc khác nhau

Endpoint quản trị có thể cho phép đọc một trạng thái tổng quát nhưng giới hạn người được thay đổi trạng thái đó. Ví dụ, bất kỳ ai cũng xem được cờ bảo trì của một ứng dụng thử nghiệm; tài khoản xem thông tin có tên người dùng hợp lệ nhưng chỉ người bảo trì mới được bật hoặc tắt cờ.

Để thiết kế đúng, cần phân biệt:

- **Xác thực (authentication):** xác định danh tính của người gọi.
- **Phân quyền (authorization):** quyết định danh tính đó có được thực hiện thao tác cụ thể hay không.
- **`Principal`:** biểu diễn danh tính mà cơ chế bảo mật cung cấp cho lần gọi.
- **`SecurityContext` của Actuator:** cung cấp danh tính và phép kiểm tra vai trò trong ngữ cảnh gọi endpoint.
- **`SecurityFilterChain`:** xử lý bảo mật HTTP trước khi lời gọi đến phương thức endpoint.

Một `Principal` có tên `viewer` không có nghĩa tài khoản đó được thay đổi cấu hình. Tên người dùng cũng không chứng minh người đó là quản trị viên; quyền phải đến từ chính sách và dữ liệu xác thực đáng tin cậy.

Bài này dùng **Spring Boot 3.3.13, Spring MVC và Spring Security**, với mã nguồn Java 17+. Ví dụ cùng tám kiểm thử ở dưới đã chạy trên Java 21.

## 2. Chọn đúng Principal và SecurityContext

### 2.1. Principal được cung cấp từ lời gọi HTTP

Trong một operation xuất qua web, Actuator hỗ trợ nhận `java.security.Principal` như tham số đặc biệt. Nó không phải một tham số query tên `principal` mà người dùng phải gửi.

Một phương thức minh họa, đặt trong bean web endpoint:

```java
@ReadOperation
public Map<String, Object> inspect(
        @Nullable Principal principal,
        SecurityContext securityContext) {
    return Map.of(
            "caller", principal == null ? "anonymous" : principal.getName(),
            "canChange", securityContext.getPrincipal() != null
                    && securityContext.isUserInRole("MAINTAINER"));
}
```

Đoạn trên minh họa cách dùng hai tham số; chương trình cùng cấu hình đầy đủ nằm ở phần 5. Các import quan trọng:

```java
import java.security.Principal;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.lang.Nullable;
```

`@Nullable` cho biết operation chấp nhận trường hợp không có danh tính được xác thực. Khi `principal == null`, phải xử lý nhánh đó trước khi gọi `getName()`.

Ví dụ, `principal == null ? "anonymous" : principal.getName()` có thể dùng cho thông tin hiển thị. Việc gán chuỗi `"anonymous"` chỉ tạo nhãn hiển thị, không tạo một người dùng và không cấp quyền nào.

Cơ chế truyền `Principal` và `SecurityContext` vào web operation được mô tả trong [Web Endpoint Security của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.security).

### 2.2. Hai kiểu SecurityContext có cùng tên ngắn

| Kiểu đầy đủ | Vai trò | Phương thức liên quan |
| --- | --- | --- |
| `org.springframework.boot.actuate.endpoint.SecurityContext` | Ngữ cảnh lời gọi endpoint Actuator | `getPrincipal()`, `isUserInRole(String)` |
| `org.springframework.security.core.context.SecurityContext` | Ngữ cảnh của Spring Security, chứa `Authentication` | `getAuthentication()`, `setAuthentication(...)` |

Trong chữ ký operation ở bài này, phải import **SecurityContext của Actuator**. Không thay bằng kiểu của Spring Security chỉ vì IDE gợi ý tên giống nhau.

`SecurityContext` của Actuator có hợp đồng rõ ràng: `getPrincipal()` có thể trả `null`, `isUserInRole(role)` trả kết quả kiểm tra vai trò, và `SecurityContext.NONE` biểu diễn ngữ cảnh rỗng. Xem [API SecurityContext của Actuator](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/SecurityContext.html).

Spring Security có mô hình rộng hơn: `SecurityContextHolder` cung cấp ngữ cảnh chứa `Authentication`, từ đó có thể lấy các quyền `GrantedAuthority`. Những khái niệm này được trình bày trong [Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html). Không cần truy cập `SecurityContextHolder` chỉ để thực hiện hai phép kiểm tra mà ngữ cảnh Actuator đã cung cấp.

### 2.3. Không suy luận đăng nhập từ một phép kiểm tra thiếu ngữ cảnh

Trong cấu hình Spring Security thông thường, truy cập trực tiếp `SecurityContextHolder` có thể thấy một `AnonymousAuthenticationToken` cho người dùng ẩn danh. Vì vậy, chỉ kiểm tra `authentication != null` hoặc chỉ `authentication.isAuthenticated()` chưa đủ để phân loại người dùng thực sự đã đăng nhập.

Ở ranh giới web operation của ví dụ, dùng `Principal` và `SecurityContext.getPrincipal()` do Actuator cung cấp. Nếu xử lý sâu bằng API Spring Security, cần phân biệt anonymous bằng chính sách hoặc `AuthenticationTrustResolver`, thay vì nhìn tên `"anonymousUser"` rồi đoán.

Không ép mọi `Principal` thành `UserDetails`. Trong tích hợp Servlet của Spring Security, đối tượng `Principal` thường là `Authentication`; dữ liệu người dùng bên trong nó còn phụ thuộc cơ chế xác thực. Giữ kiểu `Principal` khi chỉ cần `getName()`.

## 3. Kiểm tra vai trò đúng theo hợp đồng

Trong ví dụ, tài khoản được tạo bằng:

```java
User.withUsername("maintainer")
        .password(encodedPassword)
        .roles("MAINTAINER")
        .build();
```

Đây là đoạn minh họa; `encodedPassword` phải là mật khẩu đã mã hóa theo cấu hình encoder. Mã hoàn chỉnh phía dưới tạo giá trị đó bằng `PasswordEncoder`.

Với cấu hình vai trò mặc định, `roles("MAINTAINER")` tạo authority `ROLE_MAINTAINER`. Trong web operation của thí nghiệm dùng:

```java
securityContext.isUserInRole("MAINTAINER")
```

Spring Security tích hợp với Servlet và thông thường tự áp dụng tiền tố `ROLE_` cho kiểm tra vai trò. Ý nghĩa này được giải thích trong [Servlet API integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html#servletapi-roles).

Các cách biểu đạt dưới đây cùng hướng tới vai trò trong cấu hình mặc định, nhưng thuộc những API khác nhau:

| Vị trí | Cách kiểm tra |
| --- | --- |
| Actuator SecurityContext trong ví dụ MVC | `isUserInRole("MAINTAINER")` |
| Quy tắc phân quyền Spring Security | `hasRole("MAINTAINER")` |
| So khớp authority chính xác ở Spring Security | `hasAuthority("ROLE_MAINTAINER")` |

Không suy rộng tiền tố này thành quy tắc cố định cho mọi adapter, cấu hình role prefix hoặc cơ chế gán quyền. Nếu ứng dụng dùng quyền như `maintenance:write` hoặc scope OAuth2, hãy dùng cơ chế kiểm tra authority phù hợp ở Spring Security hoặc lớp chính sách, rồi kiểm thử với cấu hình thật.

Tên người dùng, vai trò và quyền thao tác là ba khái niệm khác nhau. Tài khoản tên `maintainer` nhưng chỉ có vai trò `VIEWER` vẫn phải bị từ chối thay đổi trạng thái. Đổi tên tài khoản không phải cách cấp quyền.

## 4. Hai vị trí kiểm soát quyền

### 4.1. Quy tắc HTTP trước khi vào endpoint

`SecurityFilterChain` có thể yêu cầu đăng nhập, kiểm tra vai trò theo request và áp dụng các bảo vệ như CSRF. Nếu request bị chặn ở đây, phương thức endpoint chưa chạy.

Spring Security chọn quy tắc request đầu tiên phù hợp trong danh sách. Quy tắc cụ thể cần đứng trước quy tắc rộng. Tham khảo [Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html).

Chỉ đưa ID vào `management.endpoints.web.exposure.include` mới làm endpoint được xuất qua HTTP; đó chưa phải quy tắc cho phép mọi người gọi thao tác. Cần cấu hình bảo mật tương ứng.

### 4.2. Quyết định trong operation

Operation có thể cần thông tin người gọi để:

- Chọn dữ liệu tổng quát hoặc dữ liệu chi tiết.
- Kiểm tra quyền trước khi thực hiện một hành động.
- Ghi nhận ai đã thực hiện thay đổi.
- Áp dụng chính sách phụ thuộc dữ liệu cụ thể.

**Kiểm tra quyền phải hoàn tất trước tác động thay đổi trạng thái.** Nếu đã thay đổi rồi mới trả `403`, hệ thống vẫn thực hiện hành động trái phép dù mã HTTP trông như đã từ chối.

Một trường `canChange` trả về cho giao diện chỉ là thông tin hỗ trợ hiển thị. Khi nhận yêu cầu ghi, máy chủ phải kiểm tra lại quyền trong ngữ cảnh hiện tại. Không dùng giá trị `canChange` do trình duyệt gửi lên làm bằng chứng.

Nếu một thao tác được dùng từ nhiều điểm vào như HTTP, lịch chạy nền hoặc một API khác, đặt chính sách dùng chung ở tầng phù hợp. Chỉ cấu hình `SecurityFilterChain` không kiểm soát các lời gọi Java trực tiếp. Khi sử dụng method security như `@PreAuthorize`, cần cấu hình kích hoạt và bảo đảm lời gọi đi qua cơ chế proxy; bài này tập trung vào kiểm tra ngữ cảnh của web operation.

## 5. Chương trình hoàn chỉnh: xem trạng thái và thay đổi cờ bảo trì

### 5.1. Chính sách của thí nghiệm

| Người gọi | GET trạng thái | POST thay đổi với CSRF hợp lệ |
| --- | --- | --- |
| Chưa đăng nhập | Được xem thông tin mẫu; `canChange=false` | 401 |
| `viewer`, vai trò `VIEWER` | Thấy tên mình; `canChange=false` | 403 |
| `maintainer`, vai trò `MAINTAINER` | Thấy tên mình; `canChange=true` | 200 và thay đổi trạng thái |

Cờ bảo trì ở đây chỉ là một biến boolean trong bộ nhớ. Nó không tự dừng nhận request, không bật trang bảo trì và không thay đổi trạng thái sức khỏe ứng dụng. Ta dùng nó để quan sát thời điểm quyền được kiểm tra và tác động có xảy ra hay không.

Ví dụ chọn `@WebEndpoint` vì chính sách và cách phản hồi ở đây dành cho HTTP. Không xuất thao tác này qua JMX. Nếu dùng một endpoint chung cho nhiều kênh, cần thiết kế và kiểm thử quyền của từng kênh; một web extension hoặc HTTP filter không tự bảo vệ các lời gọi qua kênh khác.

Cấu trúc dự án độc lập:

```text
actuator-permissions-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/permissions/PermissionApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/permissions/PermissionTest.java
```

### 5.2. Dependency và phiên bản

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>actuator-permissions-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
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
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

`spring-boot-starter-security` cung cấp cơ chế bảo mật thật cho các request. `spring-security-test` cung cấp hỗ trợ tạo HTTP Basic và CSRF trong kiểm thử. Phiên bản Spring Security được quản lý theo Spring Boot 3.3.13, không tự trộn một phiên bản mới hơn vào ví dụ.

### 5.3. Ứng dụng, người dùng, filter chain và endpoint

Tạo `src/main/java/com/example/permissions/PermissionApplication.java`:

```java
package com.example.permissions;

import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.endpoint.SecurityContext;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.WebEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.lang.Nullable;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
public class PermissionApplication {
    public static void main(String[] args) {
        SpringApplication.run(PermissionApplication.class, args);
    }

    @Bean
    MaintenanceState maintenanceState() {
        return new MaintenanceState();
    }

    @Bean
    MaintenanceEndpoint maintenanceEndpoint(MaintenanceState state) {
        return new MaintenanceEndpoint(state);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                        .password(encoder.encode("viewer-local"))
                        .roles("VIEWER").build(),
                User.withUsername("maintainer")
                        .password(encoder.encode("maintainer-local"))
                        .roles("MAINTAINER").build());
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        RequestMatcher maintenance = EndpointRequest.to("maintenance");
        RequestMatcher maintenanceRead = request ->
                "GET".equals(request.getMethod()) && maintenance.matches(request);

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"), maintenanceRead).permitAll()
                .requestMatchers(EndpointRequest.toAnyEndpoint()).authenticated()
                .anyRequest().denyAll());
        http.httpBasic(withDefaults());
        return http.build();
    }

    public static class MaintenanceState {
        private final AtomicBoolean enabled = new AtomicBoolean(false);

        public boolean enabled() {
            return this.enabled.get();
        }

        public void setEnabled(boolean enabled) {
            this.enabled.set(enabled);
        }
    }

    @WebEndpoint(id = "maintenance")
    public static class MaintenanceEndpoint {
        private final MaintenanceState state;

        public MaintenanceEndpoint(MaintenanceState state) {
            this.state = state;
        }

        @ReadOperation
        public Map<String, Object> inspect(
                @Nullable Principal principal, SecurityContext securityContext) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("caller", principal == null ? "anonymous" : principal.getName());
            result.put("canChange", securityContext.getPrincipal() != null
                    && securityContext.isUserInRole("MAINTAINER"));
            result.put("maintenanceEnabled", this.state.enabled());
            return result;
        }

        @WriteOperation
        public WebEndpointResponse<Map<String, Object>> change(
                boolean enabled, SecurityContext securityContext) {
            Principal principal = securityContext.getPrincipal();
            if (principal == null) {
                return new WebEndpointResponse<>(
                        Map.of("error", "authentication_required"), 401);
            }
            if (!securityContext.isUserInRole("MAINTAINER")) {
                return new WebEndpointResponse<>(
                        Map.of("error", "forbidden"), 403);
            }

            this.state.setEnabled(enabled);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("maintenanceEnabled", this.state.enabled());
            result.put("changedBy", principal.getName());
            return new WebEndpointResponse<>(result, 200);
        }
    }
}
```

Các lớp được đặt trong một tệp để tiện chạy thử. `@Bean` đăng ký endpoint và trạng thái; chỉ có annotation trên lớp mà chưa đăng ký bean thì Actuator chưa có đối tượng để phát hiện.

**Cách đọc filter chain:**

1. `health` và GET của endpoint `maintenance` được phép truy cập.
2. Những request Actuator còn lại yêu cầu xác thực.
3. Các request ngoài phạm vi đó bị từ chối bởi `denyAll()`.
4. HTTP Basic cung cấp danh tính cho request có thông tin đăng nhập hợp lệ.
5. CSRF vẫn được bật theo cấu hình mặc định.

`maintenanceRead` kết hợp HTTP method với `EndpointRequest`, nên phân biệt được GET và POST mà không phải gắn cứng đường dẫn `/actuator` trong quy tắc phân quyền.

Đây là một filter chain bao phủ mọi request của ứng dụng mẫu. Nếu thêm controller nghiệp vụ, phải bổ sung chính sách cho chúng; quy tắc `denyAll()` sẽ từ chối những request chưa được cho phép. Khi tự khai báo filter chain, cần chịu trách nhiệm về chính sách HTTP thay vì trông chờ cấu hình mặc định bảo vệ phần còn lại.

**Cách đọc `inspect`:**

- `Principal` có thể rỗng vì GET được cho phép với người chưa đăng nhập.
- `caller` dùng danh tính thực mà cơ chế bảo mật cung cấp.
- `canChange` dựa vào ngữ cảnh và vai trò hiện tại.
- Không cần truyền `principal` hoặc `securityContext` trong URL.

**Cách đọc `change`:**

- Nhánh thiếu danh tính trả `401` trước khi thay đổi trạng thái.
- Nhánh thiếu vai trò trả `403` trước khi thay đổi trạng thái.
- Chỉ sau hai kiểm tra này mới gọi `state.setEnabled(enabled)`.
- `changedBy` lấy từ `Principal` đã được xác thực, không lấy từ JSON của người gọi.

Trong đường POST bình thường của cấu hình này, yêu cầu chưa đăng nhập đã bị filter chain chặn trước `change`. Nhánh thiếu danh tính trong phương thức là một kiểm tra bổ sung, không thay thế cơ chế xác thực HTTP. Một `WebEndpointResponse` chỉ thiết lập phản hồi; nó không tự cấu hình authentication entry point hoặc header thách thức đăng nhập.

Hai tài khoản cùng mật khẩu trong mã là dữ liệu học tập cục bộ. `PasswordEncoder` tạo dạng mật khẩu được lưu trong bộ nhớ cho thí nghiệm. Ứng dụng thật cần nguồn người dùng và thông tin bí mật được quản lý phù hợp; HTTP Basic cũng cần HTTPS khi truyền qua mạng vì Base64 không mã hóa đường truyền.

### 5.4. Cấu hình quản trị

Tạo `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
management.endpoints.web.exposure.include=health,maintenance
management.endpoints.jmx.exposure.exclude=*
management.endpoint.maintenance.cache.time-to-live=0ms
```

Chỉ expose `health` và `maintenance` qua HTTP. `maintenance` dùng `@WebEndpoint`, vốn chỉ dành cho web; cấu hình loại trừ JMX cũng làm phạm vi xuất dữ liệu của ứng dụng mẫu rõ ràng.

TTL bằng 0 giữ kết quả quan sát tức thời trong thí nghiệm. Khi kết quả phụ thuộc người gọi, phải xem xét cơ chế cache theo đúng ngữ cảnh; không tự đặt một cache toàn cục theo URL rồi dùng lại `caller` hoặc `canChange` giữa các người dùng.

## 6. Chạy và kiểm tra danh tính

Từ thư mục có `pom.xml`:

```shell
mvn package
java -jar target/actuator-permissions-demo-1.0.0.jar
```

Maven biên dịch Java cùng các dependency cần thiết. Lần đầu cần tải thư viện. Ví dụ dùng cổng mặc định `8080` và địa chỉ loopback. Nếu đổi cổng, điều chỉnh các URL sau.

### 6.1. GET chưa đăng nhập

Trong terminal khác:

```shell
curl -s -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

Phần thân JSON với trạng thái ban đầu:

```json
{"caller":"anonymous","canChange":false,"maintenanceEnabled":false}
```

Không có người dùng được xác thực nhưng GET vẫn được xử lý vì chính sách cho phép đọc thông tin mẫu. Điều này không cấp quyền ghi.

### 6.2. GET bằng tài khoản xem thông tin

```shell
curl -s -u viewer:viewer-local -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

Phần thân:

```json
{"caller":"viewer","canChange":false,"maintenanceEnabled":false}
```

Xác thực đã thành công: operation nhận đúng tên `viewer`. Quyền thay đổi vẫn là `false`.

### 6.3. GET bằng tài khoản bảo trì

```shell
curl -s -u maintainer:maintainer-local -H 'Accept: application/json' http://127.0.0.1:8080/actuator/maintenance
```

Phần thân:

```json
{"caller":"maintainer","canChange":true,"maintenanceEnabled":false}
```

Nếu dùng PowerShell có alias `curl`, có thể gọi `curl.exe` để sử dụng chương trình cURL. Trật tự trường trong các JSON trên xuất phát từ `LinkedHashMap`; khi kiểm thử API, nên xác nhận giá trị trường thay vì phụ thuộc trật tự thuộc tính JSON.

### 6.4. POST có thêm điều kiện CSRF

Ứng dụng giữ CSRF bật. Gửi POST bằng tài khoản đúng nhưng thiếu token CSRF vẫn có thể bị chặn `403` trước operation. Mã `403` đó không chứng minh người dùng thiếu vai trò.

Phần tiếp theo cung cấp kiểm thử POST đầy đủ bằng MockMvc và token CSRF hợp lệ. `with(csrf())` là hỗ trợ của môi trường kiểm thử; nó không phải một query parameter tùy ý để dùng trong cURL hoặc một cách tắt CSRF.

Ứng dụng mẫu không cung cấp luồng giao diện lấy token CSRF cho client thật. Nếu bổ sung giao diện gọi POST, cần thiết kế cách nhận token, gửi lại token và giữ ngữ cảnh phiên phù hợp. Không bỏ qua CSRF chỉ để làm cho lệnh thử thành công, đặc biệt khi thông tin xác thực có thể được trình duyệt tự gửi.

## 7. Tám kiểm thử xác nhận cả quyền và tác động

Tạo `src/test/java/com/example/permissions/PermissionTest.java`:

```java
package com.example.permissions;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PermissionTest {
    @Autowired MockMvc http;
    @Autowired PermissionApplication.MaintenanceState state;

    @BeforeEach
    void reset() {
        this.state.setEnabled(false);
    }

    @Test
    void anonymousReadHasNoPrincipalOrPermission() throws Exception {
        http.perform(get("/actuator/maintenance"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("anonymous"))
                .andExpect(jsonPath("$.canChange").value(false));
    }

    @Test
    void viewerReadHasIdentityButNoWriteRole() throws Exception {
        http.perform(get("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("viewer"))
                .andExpect(jsonPath("$.canChange").value(false));
    }

    @Test
    void maintainerReadRecognizesTheRole() throws Exception {
        http.perform(get("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caller").value("maintainer"))
                .andExpect(jsonPath("$.canChange").value(true));
    }

    @Test
    void anonymousWriteWithValidCsrfIsUnauthorized() throws Exception {
        http.perform(post("/actuator/maintenance").with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isUnauthorized());
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void viewerCannotChangeStateEvenWithCsrf() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("forbidden"));
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void maintainerWithoutCsrfCannotChangeState() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isForbidden());
        assertThat(state.enabled()).isFalse();
    }

    @Test
    void maintainerWithCsrfCanChangeState() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("maintainer", "maintainer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.maintenanceEnabled").value(true))
                .andExpect(jsonPath("$.changedBy").value("maintainer"));
        assertThat(state.enabled()).isTrue();
    }

    @Test
    void requestBodyCannotGrantTheViewerARole() throws Exception {
        http.perform(post("/actuator/maintenance")
                .with(httpBasic("viewer", "viewer-local")).with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"enabled\":true,\"role\":\"MAINTAINER\"}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error").value("forbidden"));
        assertThat(state.enabled()).isFalse();
    }
}
```

Chạy:

```shell
mvn test
```

Phần tổng kết thành công:

```text
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Các dòng log, thời gian và cảnh báo JVM có thể khác.

MockMvc đi qua filter chain bảo mật và cơ chế ánh xạ Actuator trong ngữ cảnh ứng dụng. Nó không mở cổng TCP. Các request HTTP Basic ở đây dùng hai người dùng đã khai báo, nên đồng thời kiểm tra được sự tích hợp giữa xác thực, Servlet principal và SecurityContext của Actuator.

Tài liệu [Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) mô tả cách `with(csrf())` cung cấp token hợp lệ trong kiểm thử.

Điểm cần chú ý khi đọc kết quả:

| Tình huống | Tầng quyết định chính | Kết quả |
| --- | --- | --- |
| GET ẩn danh | Quy tắc HTTP cho phép, operation nhận principal rỗng | 200, `canChange=false` |
| GET của `viewer` | Xác thực thành công, kiểm tra vai trò không đạt | 200, `canChange=false` |
| GET của `maintainer` | Danh tính và vai trò phù hợp | 200, `canChange=true` |
| POST ẩn danh có CSRF hợp lệ | Yêu cầu đăng nhập ở filter chain | 401, không thay đổi |
| POST của `viewer` có CSRF hợp lệ | Kiểm tra vai trò trong operation | 403, không thay đổi |
| POST của `maintainer` thiếu CSRF | CSRF filter | 403, không thay đổi |
| POST của `maintainer` có CSRF hợp lệ | Vượt các kiểm tra và thực hiện operation | 200, trạng thái thành `true` |
| POST của `viewer` tự thêm `role` vào JSON | Vai trò vẫn lấy từ ngữ cảnh xác thực | 403, không thay đổi |

Kiểm thử yêu cầu trái phép không chỉ nhìn mã HTTP. Mỗi trường hợp bị từ chối còn xác nhận `state.enabled()` vẫn là `false`. Nếu bỏ các kiểm tra trạng thái này, một lỗi thực hiện hành động trước khi từ chối có thể bị bỏ sót.

Ca gửi thêm `"role":"MAINTAINER"` chứng minh nội dung do client tự khai không trở thành quyền của người dùng. Trường operation nhận để đổi trạng thái là `enabled`; danh tính và vai trò đến từ hệ thống bảo mật.

## 8. Phân biệt lỗi 401, 403 và lỗi ràng buộc đầu vào

**401 trong ví dụ** thường có nghĩa request cần đăng nhập hoặc thông tin HTTP Basic không hợp lệ. GET tuy được `permitAll` nhưng nếu gửi một bộ thông tin Basic sai, quá trình xác thực vẫn có thể thất bại và trả 401.

**403 trong ví dụ** có ít nhất hai nguyên nhân độc lập:

- Request bị CSRF filter từ chối, operation chưa chạy.
- Request có đủ điều kiện đi vào operation nhưng không có vai trò `MAINTAINER`.

Vì vậy, khi điều tra một POST bị 403, lần lượt xác minh thông tin đăng nhập, token CSRF và ngữ cảnh vai trò. Có thể dùng điểm dừng tại đầu operation hoặc log sự kiện từ chối đã lược bỏ thông tin nhạy cảm để xác định request đã đến đâu. Không ghi mật khẩu, token, toàn bộ `Authorization` header hoặc toàn bộ đối tượng xác thực vào log.

Nếu request có quyền phù hợp nhưng thiếu `enabled` hoặc gửi giá trị không chuyển đổi được sang boolean, Actuator có thể trả `400` khi ánh xạ tham số. Đừng nhầm lỗi đầu vào đó với lỗi vai trò. Cấu hình biên dịch từ parent Spring Boot giữ tên tham số để JSON `enabled` được ánh xạ đúng.

## 9. Những lỗi thiết kế dễ tạo lỗ hổng

### Chỉ kiểm tra Principal khác null

Điều đó chỉ cung cấp một điều kiện về danh tính trong ngữ cảnh đang dùng. Tài khoản đã đăng nhập vẫn có thể thiếu quyền thay đổi. Phải kiểm tra chính sách phù hợp trước thao tác.

### Dùng tên người dùng làm vai trò

Điều kiện như `principal.getName().equals("admin")` gắn quyền vào một tên tài khoản. Nó không thay thế hệ thống vai trò hoặc authority và dễ sai khi đổi nhà cung cấp danh tính.

### Tin tham số role, user hoặc canChange từ client

JSON và query parameter là dữ liệu do người gọi kiểm soát. Chỉ lấy chúng làm dữ liệu nghiệp vụ đã kiểm tra; không dùng chúng để tạo danh tính đáng tin cậy hoặc tự gán vai trò.

Trong operation, `Principal` và `SecurityContext` được hạ tầng web cung cấp qua cơ chế riêng. Gửi `?principal=admin` không phải cơ chế đăng nhập.

### Import nhầm SecurityContext

Dùng kiểu `org.springframework.security.core.context.SecurityContext` ở nơi cần ngữ cảnh Actuator có thể làm mất cơ chế truyền tham số đặc biệt và dẫn đến lỗi ánh xạ đầu vào. Kiểm tra tên package đầy đủ trước khi sửa JSON hoặc thêm query parameter để chữa lỗi.

Các annotation dùng cho argument resolver của controller MVC như `@AuthenticationPrincipal` cũng không tự biến một operation Actuator thành phương thức controller. Ưu tiên hợp đồng tham số mà Actuator hỗ trợ.

### Hiểu permitAll là vô hiệu hóa bảo mật

`permitAll` cho phép truy cập theo quy tắc phân quyền request đang xét. Nó không tự gỡ HTTP Basic, CSRF hoặc các filter khác. Đây là lý do lỗi xác thực hoặc CSRF vẫn cần được xem xét riêng.

### Trả canChange rồi bỏ kiểm tra tại nơi ghi

Quyền có thể thay đổi sau khi giao diện đã đọc trạng thái. Mỗi yêu cầu ghi phải được kiểm tra lại từ ngữ cảnh của chính yêu cầu đó. Ẩn một nút trên giao diện không bảo vệ thao tác phía máy chủ.

### Kiểm tra sau khi đã thay đổi

Giữ thứ tự: lấy ngữ cảnh → kiểm tra danh tính → kiểm tra quyền → thực hiện thay đổi → tạo kết quả. Không thay đổi cờ hoặc gửi tác động ra ngoài trước nhánh từ chối.

### Dùng HTTP policy cho mọi kênh và luồng

`SecurityFilterChain` bảo vệ request đi qua chain đó. Lời gọi Java trực tiếp, JMX, tác vụ nền hoặc executor mới cần được đánh giá theo cơ chế riêng.

Ví dụ dùng `@WebEndpoint` nên không tạo một operation JMX tương ứng. Nếu mở rộng thành endpoint nhiều kênh, không coi việc HTTP đã an toàn là bằng chứng rằng mọi kênh đều an toàn.

Với code Servlet chuyển sang xử lý bất đồng bộ, ngữ cảnh bảo mật không phải một biến toàn cục có thể đọc tùy ý ở mọi thread. Cần cơ chế truyền ngữ cảnh phù hợp. Với WebFlux, không áp dụng nguyên xi suy luận dựa vào ThreadLocal của Servlet; dùng cơ chế reactive tương ứng.

## 10. Thực hành và tiêu chí kiểm tra

1. **Đổi tên tài khoản `maintainer` nhưng giữ vai trò `MAINTAINER`.** Cập nhật thông tin đăng nhập trong kiểm thử. Người dùng vẫn được thay đổi trạng thái, còn `changedBy` phản ánh tên mới.
2. **Giữ tên `maintainer` nhưng đổi vai trò thành `VIEWER`.** GET phải trả `canChange=false`; POST có CSRF hợp lệ phải trả 403 và trạng thái không đổi.
3. **Đổi chính sách đọc từ công khai sang yêu cầu đăng nhập.** Xác nhận GET ẩn danh bị chặn ở filter chain. Không cố giữ kỳ vọng principal rỗng trong một operation mà khách ẩn danh không còn được phép đi vào.
4. **Thêm trường thông tin chi tiết chỉ cho người có vai trò bảo trì.** Kiểm tra cả phần phản hồi bị ẩn với `viewer`, không chỉ trạng thái HTTP.
5. **Thêm thao tác nhạy cảm mới.** Viết ca kiểm tra người có quyền, thiếu quyền, chưa đăng nhập và lỗi CSRF nếu thao tác dùng phương thức cần bảo vệ; trong ca từ chối phải xác nhận tác động chưa xảy ra.

Trước khi hoàn tất một endpoint quản trị, hãy xác định được: ai được nhận diện trong lời gọi, chính sách nào cho phép thao tác, tầng nào từ chối request, và bằng chứng nào cho thấy yêu cầu bị từ chối không gây thay đổi.
