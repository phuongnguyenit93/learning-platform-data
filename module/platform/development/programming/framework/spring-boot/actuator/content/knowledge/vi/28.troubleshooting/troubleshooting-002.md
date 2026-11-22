# Chẩn đoán lỗi 401, 403 và thao tác ghi bị chặn bởi CSRF

## 1. Hiểu đúng ba câu hỏi trước khi sửa cấu hình

Khi đọc được thông tin Actuator nhưng không đổi được mức log, vấn đề có thể nằm ở xác thực, phân quyền hoặc kiểm tra chống giả mạo yêu cầu. Ba cơ chế này trả lời ba câu hỏi khác nhau:

| Cơ chế | Câu hỏi | Dữ liệu thường được kiểm tra |
| --- | --- | --- |
| Xác thực (authentication) | Ai đang gọi? | Tên đăng nhập/mật khẩu, phiên đăng nhập hoặc access token |
| Phân quyền (authorization) | Người gọi có được thực hiện thao tác này không? | Quyền (authority), vai trò (role), endpoint và HTTP method |
| Chống giả mạo yêu cầu (CSRF protection) | Yêu cầu thay đổi trạng thái có mang bằng chứng chống giả mạo hợp lệ không? | CSRF token và dữ liệu tương ứng được lưu phía máy chủ hoặc theo cơ chế repository đã cấu hình |

CSRF là Cross-Site Request Forgery: kẻ tấn công khiến trình duyệt của nạn nhân gửi một yêu cầu ngoài ý muốn, trong khi trình duyệt có thể tự đính kèm thông tin xác thực. Một CSRF token hợp lệ không chứng minh người gọi có quyền quản trị; ngược lại, mật khẩu đúng và đủ quyền cũng không thay thế CSRF token.

Trong chương chẩn đoán sự cố Actuator, mục tiêu là tìm được tầng từ chối yêu cầu bằng bằng chứng. Bài này dùng Spring MVC/Servlet, Spring Boot 3.3.13, Spring Security 6.3.x và Java 21. Với WebFlux, nguyên tắc phân biệt vẫn có ích nhưng phải dùng API phản ứng như SecurityWebFilterChain và ServerHttpSecurity, không chép cấu hình Servlet sang.

## 2. Đọc mã HTTP như dấu hiệu, không coi là kết luận cuối cùng

| Quan sát | Giả thuyết cần kiểm tra | Phép thử tiếp theo |
| --- | --- | --- |
| GET endpoint được bảo vệ trả 401 | Chưa có hoặc không chấp nhận thông tin xác thực | Gửi lại cùng URL với tài khoản đúng; kiểm tra AuthenticationEntryPoint |
| GET trả 403 khi tài khoản đã được xác thực | Thiếu quyền, sai matcher hoặc một tầng khác từ chối | Xác nhận chain được chọn, quyền thực tế và rule ứng với GET |
| GET thành công, POST cùng endpoint trả 403 | CSRF hoặc quyền ghi riêng | Giữ nguyên người dùng, gửi token hợp lệ cùng phiên rồi thử lại |
| POST vẫn 403 sau khi token hợp lệ | Có thể thiếu quyền ghi; token cũng có thể không khớp phiên | Đối chiếu log CSRF trước, rồi kiểm tra quyền và matcher POST |
| 302 chuyển tới trang đăng nhập | Entry point đang dùng đăng nhập biểu mẫu | Xem Location và chain thay vì chỉ tìm 401 |
| 404, 405, 400 hoặc 415 | Đường dẫn, endpoint, phương thức hoặc dữ liệu gửi có thể sai | Kiểm tra mapping sau khi đã đi qua lớp bảo mật |

Với cấu hình HTTP Basic trong thí nghiệm bên dưới, GET được bảo vệ khi thiếu hoặc sai mật khẩu trả 401; người đã xác thực nhưng thiếu quyền trả 403. HTTP Basic thường gửi thêm WWW-Authenticate. Một entry point tùy biến, cấu hình đăng nhập biểu mẫu, proxy hoặc xử lý lỗi có thể làm hình thức phản hồi khác đi. Vì vậy cần giữ cả status, header, method, URL và log liên quan. [Cơ chế HTTP Basic của Spring Security](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html).

Không suy ra rằng mọi 403 đều có nghĩa là 'đã đăng nhập nhưng thiếu role'. Với chuỗi lọc mặc định của Servlet, CsrfFilter được đặt trước BasicAuthenticationFilter và AuthorizationFilter. POST thiếu token có thể bị chặn trước khi mật khẩu được xử lý, kể cả khi gửi sai mật khẩu hoặc chưa gửi thông tin xác thực. Sơ đồ rút gọn cho các filter liên quan là:

```text
Yêu cầu đến đúng host/cổng/path
  -> chọn SecurityFilterChain đầu tiên khớp
  -> CsrfFilter: có cần token, token có hợp lệ?
  -> BasicAuthenticationFilter: kiểm tra Basic nếu được gửi
  -> AuthorizationFilter: xét quyền
  -> thao tác Actuator
```

Thứ tự trên có thể đối chiếu trong [FilterOrderRegistration của Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/config/src/main/java/org/springframework/security/config/annotation/web/builders/FilterOrderRegistration.java). Sơ đồ bỏ qua nhiều filter trung gian và không mô tả mọi cơ chế đăng nhập. Điều cần rút ra là: thay đổi thông tin xác thực chưa chắc tác động tới kết quả nếu một filter phía trước vẫn đang từ chối. CsrfFilter xử lý trường hợp thiếu/sai token bằng AccessDeniedHandler và dừng chuỗi. [Mã nguồn CsrfFilter của Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/web/src/main/java/org/springframework/security/web/csrf/CsrfFilter.java).

## 3. Tách khả năng truy cập endpoint khỏi quyền gọi

Trước khi sửa rule, ghi lại endpoint ID, HTTP method, URL thực tế, management port và các đường dẫn gốc đang có hiệu lực. Với mặc định, endpoint loggers dùng /actuator/loggers; reverse proxy hoặc cấu hình management có thể thay đổi URL nhìn từ bên ngoài.

Trong Spring Boot 3.3, endpoint cần được bật và được expose qua HTTP mới có thao tác HTTP tương ứng. Mở exposure không cấp quyền truy cập. Ngược lại, permitAll không tự tạo mapping cho endpoint đang tắt hoặc không được expose. Nếu tự khai báo SecurityFilterChain, phải chịu trách nhiệm cấu hình bảo mật cho cả Actuator lẫn phần ứng dụng còn lại vì cấu hình bảo mật tự động tương ứng sẽ nhường quyền. [Actuator endpoints và bảo mật trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Một 401/403 cũng không chứng minh URL có mapping hợp lệ: filter có thể từ chối trước khi Spring MVC tra mapping. Đừng đổi một URL sai thành permitAll rồi kết luận đã sửa được endpoint.

Các bẫy thường gặp khi đọc cấu hình:

- securityMatcher quyết định cả chain có áp dụng hay không; requestMatchers trong authorizeHttpRequests chọn rule bên trong chain đã được chọn.
- Khi có nhiều chain, chain đầu tiên khớp theo thứ tự được sử dụng. Rule rộng ở chain ưu tiên cao có thể khiến chain Actuator không bao giờ được chọn.
- Trong cùng phần phân quyền, đặt rule cụ thể trước rule bao quát; kiểm tra cả method đọc và ghi.
- hasRole("OPS") tương ứng với authority ROLE_OPS. hasAuthority("OPS") tìm đúng chuỗi OPS; hai cách viết không tương đương. Với quy ước tiền tố mặc định, không viết hasRole("ROLE_OPS").
- Cấu hình hiển thị chi tiết health không thay thế rule bảo vệ URL. Đọc được health cũng không chứng minh có quyền đọc hoặc ghi loggers.

Để tránh phụ thuộc cứng vào /actuator khi nhận diện endpoint, Spring Boot cung cấp EndpointRequest. Ví dụ bên dưới kết hợp matcher endpoint với method thay vì áp dụng quyền quản trị cho mọi POST trong ứng dụng. [Chọn nhiều SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances).

## 4. Vì sao POST cần CSRF token dù GET đã thành công?

CSRF protection mặc định bỏ qua GET, HEAD, OPTIONS và TRACE; các phương thức còn lại, trong đó có POST, PUT, PATCH và DELETE, cần được kiểm tra nếu không có ngoại lệ. Điều này giả định các thao tác dùng phương thức an toàn không thay đổi trạng thái nghiệp vụ. Không chuyển thao tác đổi mức log hoặc tắt ứng dụng sang GET để vượt kiểm tra.

Ví dụ, xem cấu hình logger là thao tác đọc; đặt configuredLevel là thao tác ghi. Quyền đọc và quyền ghi có thể khác nhau. Ngoài kiểm tra quyền, thao tác ghi còn phải thỏa mãn CSRF khi cơ chế này đang bật.

Mặc định phía Servlet dùng HttpSessionCsrfTokenRepository. Với mô hình đó, cần giữ cả phiên chứa token dự kiến và token gửi trong yêu cầu. Chỉ gửi JSESSIONID mà không gửi token, hoặc sao chép token sang một cookie jar mới, đều không đủ. [Cấu hình repository mặc định trong Spring Security 6.3.10](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/config/src/main/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.java).

Trong Spring Security 6, token có thể được nạp trì hoãn; một GET bất kỳ không bảo đảm đã tạo session/token. Giá trị token được công bố cho client mặc định còn có lớp che ngẫu nhiên chống BREACH. Vì vậy nên lấy token qua cơ chế được ứng dụng hỗ trợ và dùng headerName trả về; không tự đoán token từ một cookie hoặc giải mã giá trị theo hình dạng quan sát được. Bài thực hành cung cấp một controller /csrf để chủ động lấy token; đây là controller của ví dụ, không phải endpoint Actuator có sẵn. [CSRF cho ứng dụng Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

## 5. Thí nghiệm độc lập: tạo đủ 401, 403 do quyền và 403 do CSRF

Thí nghiệm chạy tại máy cá nhân với HTTP Basic, giữ CSRF bật và hai tài khoản:

| Tài khoản | Mật khẩu minh họa | Vai trò | Quyền trong thí nghiệm |
| --- | --- | --- | --- |
| viewer | viewer-pass | VIEWER | Đọc loggers, lấy CSRF token |
| ops | ops-pass | OPS | Đọc và sửa loggers, lấy CSRF token |

Health được đọc không cần đăng nhập; các endpoint khác ngoài health và loggers bị từ chối. Tài khoản cố định và {noop} chỉ phục vụ thực hành trên địa chỉ loopback. Khi triển khai thực tế cần hệ thống quản lý danh tính/mật khẩu phù hợp và HTTPS cho HTTP Basic.

### 5.1. Tạo dự án

Dùng JDK 21, Maven 3.6.3 trở lên và Python 3 để chạy phần kiểm chứng. Cần kết nối tới kho Maven nếu chưa có dependency trong bộ nhớ đệm. Đây là dự án Spring Boot có dependency, vì vậy chạy bằng Maven thay vì javac một tệp riêng lẻ.

```text
actuator-security-lab/
├── pom.xml
├── verify.py
└── src/main/
    ├── java/example/lab/ActuatorSecurityLab.java
    └── resources/application.properties
```

Tệp pom.xml:

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
    <groupId>example</groupId>
    <artifactId>actuator-security-lab</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>
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
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp src/main/resources/application.properties:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,loggers
management.endpoint.health.show-details=never
```

Tệp src/main/java/example/lab/ActuatorSecurityLab.java:

```java
package example.lab;

import java.util.Map;
import jakarta.servlet.DispatcherType;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootApplication
@RestController
public class ActuatorSecurityLab {
    public static void main(String[] args) {
        SpringApplication.run(ActuatorSecurityLab.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer").password("{noop}viewer-pass")
                .roles("VIEWER").build(),
            User.withUsername("ops").password("{noop}ops-pass")
                .roles("OPS").build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain actuator(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .requestMatchers(new AndRequestMatcher(
                EndpointRequest.to("loggers"),
                request -> "GET".equals(request.getMethod())
            )).hasAnyRole("VIEWER", "OPS")
            .requestMatchers(new AndRequestMatcher(
                EndpointRequest.to("loggers"),
                request -> "POST".equals(request.getMethod())
            )).hasRole("OPS")
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        http.csrf(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain application(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers(HttpMethod.GET, "/csrf").authenticated()
            .anyRequest().denyAll()
        );
        http.httpBasic(withDefaults());
        http.csrf(withDefaults());
        return http.build();
    }

    @GetMapping("/csrf")
    public Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }
}
```

Chain thứ nhất chỉ xét Actuator. Chain thứ hai nhận phần còn lại và cho người đã xác thực lấy token. Hai chain dùng repository CSRF mặc định với cùng HttpSession. Cho phép DispatcherType.ERROR giúp bước dựng phản hồi lỗi không bị rule denyAll từ chối lần nữa; một yêu cầu REQUEST trực tiếp tới /error vẫn không được cấp quyền bởi rule này.

Khởi động từ thư mục gốc của dự án:

```shell
mvn spring-boot:run
```

Giữ tiến trình chạy và mở terminal thứ hai tại cùng thư mục. Đảm bảo cổng 8080 đang được ứng dụng này sử dụng, không phải một dịch vụ khác.

### 5.2. Kiểm chứng bằng client giữ đúng cookie và token

Tệp verify.py dùng thư viện chuẩn Python, không cần cài requests hay jq. Mỗi người dùng có một cookie jar riêng. Thông tin Basic được gửi rõ ràng trên từng yêu cầu, còn cookie jar giữ phiên CSRF; hai việc này có vai trò riêng.

```python
import base64
import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE = "http://127.0.0.1:8080"
LOGGER = "/actuator/loggers/example.lab.probe"


def client():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def call(opener, method, path, credentials=None, payload=None, token=None):
    headers = {}
    if credentials is not None:
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        headers["Authorization"] = "Basic " + encoded
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers[token["headerName"]] = token["token"]
    request = Request(BASE + path, data=data, headers=headers, method=method)
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.read()


def expect(label, expected, result):
    status, body = result
    assert status == expected, (label, expected, status, body)
    print(f"{label}: {status}")
    return body


anon = client()
viewer = client()
ops = client()
viewer_auth = "viewer:viewer-pass"
ops_auth = "ops:ops-pass"
change = {"configuredLevel": "DEBUG"}

expect("anonymous GET health", 200, call(anon, "GET", "/actuator/health"))
expect("anonymous GET loggers", 401, call(anon, "GET", "/actuator/loggers"))
expect("wrong password GET loggers", 401,
       call(client(), "GET", "/actuator/loggers", "ops:wrong-pass"))
expect("viewer GET loggers", 200,
       call(viewer, "GET", "/actuator/loggers", viewer_auth))
expect("anonymous POST without CSRF", 403,
       call(anon, "POST", LOGGER, payload=change))
expect("ops POST without CSRF", 403,
       call(ops, "POST", LOGGER, ops_auth, change))

status, body = call(viewer, "GET", "/csrf", viewer_auth)
assert status == 200, (status, body)
viewer_token = json.loads(body)
expect("viewer POST with valid CSRF", 403,
       call(viewer, "POST", LOGGER, viewer_auth, change, viewer_token))

status, body = call(ops, "GET", "/csrf", ops_auth)
assert status == 200, (status, body)
ops_token = json.loads(body)
invalid_token = dict(ops_token, token="invalid-token")
expect("ops POST with invalid CSRF", 403,
       call(ops, "POST", LOGGER, ops_auth, change, invalid_token))
expect("ops POST with valid CSRF", 204,
       call(ops, "POST", LOGGER, ops_auth, change, ops_token))

body = expect("ops GET changed logger", 200,
              call(ops, "GET", LOGGER, ops_auth))
assert json.loads(body)["configuredLevel"] == "DEBUG", body
print("configuredLevel=DEBUG")

expect("ops POST reset logger", 204,
       call(ops, "POST", LOGGER, ops_auth, {}, ops_token))
status, body = call(ops, "GET", LOGGER, ops_auth)
assert status == 200 and json.loads(body).get("configuredLevel") is None, body
print("configuredLevel reset")
```

Chạy:

```shell
python verify.py
```

Stdout khi dùng đúng cấu hình ở trên và ứng dụng khởi động thành công:

```text
anonymous GET health: 200
anonymous GET loggers: 401
wrong password GET loggers: 401
viewer GET loggers: 200
anonymous POST without CSRF: 403
ops POST without CSRF: 403
viewer POST with valid CSRF: 403
ops POST with invalid CSRF: 403
ops POST with valid CSRF: 204
ops GET changed logger: 200
configuredLevel=DEBUG
ops POST reset logger: 204
configuredLevel reset
```

204 nghĩa là thao tác ghi thành công và không có nội dung phản hồi, không phải lỗi vì không có JSON. Script đọc lại logger để xác nhận hiệu ứng thực tế, rồi gửi {} để xóa mức cấu hình riêng của logger thử nghiệm. Xóa configuredLevel cho phép logger trở lại mức kế thừa, không đồng nghĩa tắt logging. [Hợp đồng đọc, cập nhật và xóa mức log của endpoint loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

### 5.3. Rút nguyên nhân từ các phép thử có kiểm soát

- GET 401 chuyển thành 200 khi bổ sung đúng tài khoản: bằng chứng nghiêng về xác thực, không cần đổi exposure hoặc CSRF.
- Cùng tài khoản ops, POST thiếu token là 403 nhưng POST có token cùng phiên là 204: token là điều kiện còn thiếu trong thí nghiệm này.
- Viewer lấy được token nhưng POST vẫn 403, trong khi ops thực hiện được cùng thao tác: token không cấp quyền OPS. Xác nhận log không còn báo lỗi CSRF rồi kiểm tra phân quyền.
- POST không đăng nhập vẫn 403: đây là ví dụ cụ thể phản bác cách suy luận '403 luôn chứng minh đã đăng nhập'.
- Token sai và token thiếu đều có thể tạo 403. Chỉ nhìn mã HTTP không phân biệt được hai trường hợp hoặc phân biệt chúng với lỗi quyền.

Không chuyển token lấy bằng cookie jar viewer sang jar ops để so sánh quyền; khi thay cả người dùng lẫn phiên/token, phép thử sẽ trộn hai nguyên nhân.

## 6. Quy trình chẩn đoán trên ứng dụng đang có sự cố

### Bước 1: Giữ nguyên yêu cầu gốc và xác định nơi trả lỗi

Ghi lại thời điểm, method, host, port, đường dẫn, status và header phản hồi; che thông tin xác thực trước khi chia sẻ. Kiểm tra liệu 401/403 được sinh bởi Spring Security, reverse proxy, ingress hay một bộ lọc tự viết. Nếu không có log ứng dụng tương ứng, trước hết kiểm tra tuyến đi của yêu cầu.

Có thể dùng lệnh sau để quan sát status/header của phép đọc, không tự động theo redirect:

```shell
curl -i http://127.0.0.1:8080/actuator/loggers
curl -i -u viewer:viewer-pass http://127.0.0.1:8080/actuator/loggers
```

Trên Windows dùng curl.exe nếu tên curl đang trỏ tới một lệnh khác. Tài khoản trong lệnh chỉ là dữ liệu của thí nghiệm. Với hệ thống thực, dùng cách cấp thông tin xác thực phù hợp để tránh đưa bí mật vào lịch sử terminal hoặc báo cáo.

### Bước 2: Kiểm tra URL, exposure và chain thực sự được chọn

Đối chiếu profile đang bật, cấu hình management và cấu hình proxy có hiệu lực. Nếu Actuator chạy ở cổng riêng, thử đúng cổng; đừng gửi CSRF token tới một dịch vụ khác chỉ vì URL đều có /actuator. Với cookie có cờ Secure, client phải dùng HTTPS; host và path cũng ảnh hưởng việc gửi cookie.

Đọc các bean SecurityFilterChain theo thứ tự. Tìm chain đầu tiên khớp yêu cầu thực tế và rule đầu tiên khớp bên trong nó. Không kết luận từ một đoạn cấu hình chưa được kích hoạt hoặc từ source code của profile khác.

### Bước 3: Dùng phép đọc để thu hẹp lỗi xác thực

Chọn GET của endpoint đang cần chẩn đoán, giữ nguyên URL và thay một yếu tố: không có thông tin xác thực, sai thông tin, rồi đúng thông tin. Nếu dùng bearer token, kiểm tra token còn hạn, issuer/audience và ánh xạ quyền theo cơ chế resource server của ứng dụng; không thay bằng tài khoản Basic nếu chain không hỗ trợ Basic.

Không dùng GET health công khai làm bằng chứng tài khoản đã được xác thực. Cũng không suy ra Basic thành công chỉ vì đã có cookie phiên: xác minh Authentication và authorities thực tế ở phía máy chủ trong môi trường kiểm tra.

### Bước 4: Đối chiếu quyền của chính thao tác bị lỗi

Kiểm tra quyền thực tế, tiền tố ROLE_, chữ hoa/chữ thường, endpoint matcher và method matcher. Nếu có method security, bộ lọc tùy biến hoặc rule trong proxy, chúng có thể tiếp tục từ chối sau khi rule URL đã cho qua.

Một tài khoản được đọc metrics hoặc loggers không mặc nhiên được đổi mức log. Sửa theo nhu cầu vận hành thực tế, giữ riêng quyền đọc và quyền thay đổi trạng thái.

### Bước 5: Với thao tác ghi, kiểm tra vòng đời CSRF

Xác minh từng điểm thay vì thêm đại một header:

1. Chain này có bật CSRF và yêu cầu này có thuộc phạm vi kiểm tra không?
2. Token lấy từ cơ chế nào: session repository, cookie repository hay cách tùy biến?
3. Token đã được tạo và công bố thật chưa? Một GET không đọc token có thể chưa làm việc đó.
4. Client có gửi lại đúng cookie phiên và token với đúng headerName không?
5. Phiên có hết hạn, ứng dụng có khởi động lại, hoặc đăng nhập/đăng xuất có làm token cũ mất hiệu lực không?
6. Nếu có nhiều instance, session có được chia sẻ/định tuyến đúng không? Token dự kiến có tồn tại tại instance nhận POST không?

Với CookieCsrfTokenRepository, không mặc định lấy token giống ví dụ session. Cần tuân theo hợp đồng cookie/header và request handler đang cấu hình; tích hợp SPA trong Spring Security 6 có yêu cầu riêng về token được che. Tránh trộn cách đọc token của hai repository.

### Bước 6: Bật log tạm thời và đọc đúng lần từ chối đầu tiên

Trong môi trường kiểm tra có thể thêm tạm cấu hình sau, rồi khởi động lại nếu không có cơ chế đổi mức log khác:

```properties
logging.level.org.springframework.security=TRACE
```

Quan sát chain được chọn, các filter được gọi và điểm từ chối của đúng yêu cầu. Dòng chứa Invalid CSRF token là bằng chứng về CSRF; muốn phân biệt chính xác trường hợp thiếu token dự kiến với token không khớp, có thể kiểm tra MissingCsrfTokenException hoặc InvalidCsrfTokenException qua debugger/handler trong môi trường phát triển. Tên exception phụ thuộc trạng thái repository, không chỉ phụ thuộc việc header có trống hay không.

Đừng chỉ đọc lỗi của dispatch /error ở cuối rồi bỏ qua nguyên nhân gốc trước đó. Không ghi mật khẩu, Authorization header, session cookie hay CSRF token vào log để 'dễ debug'. Hạ mức log sau khi thu đủ bằng chứng.

### Bước 7: Kiểm chứng lại cả điều được phép và điều phải bị chặn

Sau khi sửa, thử lại ít nhất một yêu cầu hợp lệ, một tài khoản thiếu quyền, một trường hợp thiếu/sai token nếu vẫn bảo vệ CSRF và một yêu cầu không đăng nhập. Xác nhận thao tác thực sự có hiệu lực bằng phép đọc lại; không dừng ở việc status đã chuyển từ 403 sang 2xx.

Nếu lỗi chuyển sang 400/415, kiểm tra JSON, tên tham số và Content-Type. Nếu 405, kiểm tra method mà operation hỗ trợ. Việc đi qua lớp bảo mật không bảo đảm dữ liệu đầu vào đã đúng.

## 7. Chọn cách sửa theo mô hình client

### 7.1. Có trình duyệt hoặc thông tin xác thực tự được đính kèm

Giữ CSRF protection và sửa việc lấy/gửi token cùng đúng phiên. Điều này đặc biệt cần khi dùng phiên đăng nhập hoặc cookie; HTTP Basic trên trình duyệt cũng có thể tham gia cơ chế tự gửi thông tin xác thực. Không coi 'stateless', 'REST', 'JSON' hoặc 'chỉ vừa thử bằng curl' là bằng chứng đủ để bỏ CSRF. [CSRF và các ứng dụng dùng thông tin xác thực tự động](https://raw.githubusercontent.com/spring-projects/spring-security/6.3.10/docs/modules/ROOT/pages/features/exploits/csrf.adoc).

CORS và CSRF xử lý vấn đề khác nhau. CORS chi phối việc trình duyệt cho phép truy cập phản hồi giữa các origin; nó không thay thế bằng chứng chống giả mạo của thao tác ghi. Chỉ nới CORS thường không sửa được POST bị CsrfFilter từ chối.

### 7.2. API quản trị thực sự chỉ dùng cho máy với cơ chế xác thực phù hợp

Chỉ cân nhắc ngoại lệ CSRF khi đã đánh giá mô hình xác thực: client chủ động gắn credential, endpoint không dựa vào credential mà trình duyệt tự gửi, và phạm vi truy cập được thiết kế cho vận hành. Ví dụ token trong Authorization được client chủ động gắn khác với token đặt trong cookie tự gửi.

Nếu quyết định kiến trúc đã cho phép miễn CSRF cho riêng thao tác ghi loggers, đoạn sau minh họa cách thu hẹp ngoại lệ. Đây là đoạn bổ sung vào chain Actuator hiện có, không phải chương trình độc lập và không áp dụng vào thí nghiệm ở phần 5:

```java
http.csrf(csrf -> csrf.ignoringRequestMatchers(
    new AndRequestMatcher(
        EndpointRequest.to("loggers"),
        request -> "POST".equals(request.getMethod())
    )
));
```

Ngoại lệ trên không bỏ xác thực hay cấp quyền OPS. Nó cũng không chứng minh cấu hình Basic của thí nghiệm phù hợp để được miễn CSRF trong môi trường có trình duyệt. Sau quyết định miễn, phải kiểm thử tài khoản thiếu quyền vẫn bị chặn và các tuyến ứng dụng còn lại vẫn được bảo vệ như dự kiến.

Không mở permitAll cho mọi endpoint, không tắt CSRF toàn ứng dụng chỉ để hết một lỗi POST, và không mở shutdown làm phép thử đầu tiên. Thay đổi mức log của một logger riêng giúp quan sát được thao tác ghi với tác động có thể khôi phục.

## 8. Bài tập tự kiểm tra

1. Ops gửi đúng mật khẩu nhưng không có token và nhận 403. Có thể kết luận mật khẩu đã được kiểm tra thành công không? Giải thích dựa vào thứ tự filter.
2. Viewer có token hợp lệ cùng phiên nhưng vẫn không đổi được mức log. Điều kiện nào còn thiếu trong thí nghiệm?
3. Lấy token bằng jar A, gửi POST bằng jar B. Vì sao bổ sung đúng header chưa chắc sửa được lỗi?
4. Sau khi thêm token, POST trả 415. Nên kiểm tra dữ liệu gửi hay tiếp tục thay role?
5. Một chain có matcher rộng được đặt trước chain Actuator. Vì sao sửa rule trong chain Actuator có thể không thay đổi kết quả?

Hướng đối chiếu: câu 1 chưa đủ bằng chứng vì CsrfFilter có thể chặn trước BasicAuthenticationFilter; câu 2 thiếu ROLE_OPS; câu 3 thiếu phiên tương ứng với token dự kiến; câu 4 kiểm tra Content-Type/hợp đồng dữ liệu khi đã xác nhận bảo mật cho qua; câu 5 chain đầu tiên khớp đã nhận yêu cầu.

Khi kết thúc chẩn đoán, cần mô tả được yêu cầu nào bị từ chối, tầng nào từ chối, bằng chứng nào xác nhận và phép thử nào cho thấy bản sửa vừa cho phép đúng thao tác vừa giữ được giới hạn truy cập.
