# AuthenticationEventPublisher và DefaultAuthenticationEventPublisher trong Spring Security

## 1. Bài học giải quyết vấn đề gì?

Khi một hệ thống Spring Security xác thực người dùng thành công hoặc thất bại, đội phát triển thường muốn **ghi audit, tính metric, phát hiện đăng nhập bất thường hoặc kích hoạt một quy trình nghiệp vụ an toàn**. Nếu đặt tất cả logic đó vào filter HTTP, controller hoặc `AuthenticationProvider`, mã dễ bị gắn chặt với cơ chế đăng nhập và khó tái sử dụng cho form login, HTTP Basic, LDAP, JWT hay các provider tự viết.

Spring Security có cơ chế **authentication events**:

- `AuthenticationEventPublisher` là **giao diện phát sự kiện** kết quả xác thực.
- `DefaultAuthenticationEventPublisher` là **triển khai mặc định**: phát `AuthenticationSuccessEvent` khi xác thực thành công, và ánh xạ những `AuthenticationException` phổ biến thành các `AbstractAuthenticationFailureEvent` cụ thể.
- `@EventListener` hoặc `ApplicationListener` của Spring Framework **nhận sự kiện** để ghi nhận, thống kê hoặc thực hiện tác vụ phụ.

Bài này giải thích cơ chế, điểm phát sự kiện, ánh xạ exception, cách đăng ký bean, khác biệt giữa event và authentication handler, ví dụ Spring Boot Java 17+ chạy được, kiểm thử và các lưu ý bảo mật/vận hành.

**Phiên bản:** nội dung chính dùng **Spring Boot 3.5.x / Spring Security 6.5.x / Servlet**. Cả hai API được giới thiệu từ Spring Security 3.0 và vẫn có trong Spring Security 7.x, nhưng ví dụ Java dưới đây theo dependency Spring Boot 3.5. Các luồng reactive/WebFlux cần kiểm tra cách phát event riêng, không mặc định có cùng `ProviderManager`.

## 2. Sơ đồ: event xuất hiện ở tầng nào?

~~~text
Client
  |
  | Authorization: Basic ... / POST /login / provider khác
  v
Spring Security authentication filter
  |
  | tạo Authentication request (thường chưa xác thực)
  v
AuthenticationManager
  |
  v
ProviderManager  ----> AuthenticationProvider(s)
  |                           |
  |             kiểm credential / account state
  |                           |
  +<--------------------------+
  |
  +-- THÀNH CÔNG --> AuthenticationEventPublisher
  |                       |
  |                       +--> AuthenticationSuccessEvent
  |
  +-- THẤT BẠI ----> AuthenticationEventPublisher
                          |
                          +--> AuthenticationFailureBadCredentialsEvent
                          +--> AuthenticationFailureLockedEvent
                          +--> ... sự kiện lỗi khác
                                    |
                                    v
                          ApplicationEventPublisher
                                    |
                                    v
                    @EventListener / ApplicationListener
                    audit · monitoring · cảnh báo · metric
~~~

Đây là sơ đồ **luồng thông dụng khi `AuthenticationManager` dùng `ProviderManager` được cấu hình publisher**. Không phải mọi cơ chế xác thực, mọi custom manager hoặc mỗi request đều tự phát sự kiện giống nhau.

Bên cạnh đó, filter thực hiện phần **HTTP flow** (trả 401, redirect, tạo session hoặc xử lý callback). Sự kiện phục vụ **quan sát kết quả xác thực**, không quyết định HTTP response và không thay thế bước kiểm credential.

### 2.1. Một lần authentication khác một lần HTTP request

- Với **HTTP Basic**, mỗi request có credentials có thể được xác thực lại, do đó một client có thể tạo nhiều success events.
- Với **form login + session**, sau khi xác thực thành công, request tiếp theo dùng session đã lưu `SecurityContext` thường **không** chạy lại bước kiểm mật khẩu, nên không có success event mới cho từng page view.
- Với **Bearer/JWT**, việc tạo event phụ thuộc đường xác thực và manager/filter cụ thể, không tự dùng số event làm số người dùng duy nhất.
- Nếu một endpoint public được truy cập không qua authentication manager, nó không nhất thiết phát `AuthenticationSuccessEvent`.
- Nếu một filter/custom endpoint tự gán `SecurityContext` mà không đi qua publisher, bạn có thể không thấy sự kiện.

**Mốc phát event:** mô hình này tập trung vào kết quả xác thực ở tầng `AuthenticationManager`. Nó không phải bằng chứng rằng browser đã nhận cookie, người dùng đã xem trang đích hay mọi bước nghiệp vụ sau login đều thành công.

## 3. AuthenticationEventPublisher: giao diện có hai phương thức

Package:

~~~java
org.springframework.security.authentication.AuthenticationEventPublisher
~~~

Hai phương thức cốt lõi:

~~~java
void publishAuthenticationSuccess(Authentication authentication);

void publishAuthenticationFailure(
        AuthenticationException exception,
        Authentication authentication);
~~~

| Tham số | Vai trò | Điểm cần hiểu |
| --- | --- | --- |
| `authentication` khi thành công | Đối tượng `Authentication` đã xác thực, có principal và authorities | Không tự log toàn bộ object; có thể chứa details nhạy cảm |
| `exception` khi thất bại | Lý do `AuthenticationException` của provider/manager | Chọn loại failure event; không nên gửi message chi tiết cho client |
| `authentication` khi thất bại | Authentication request gốc hoặc đang xử lý | Có thể chứa **raw credentials**, không ghi log nguyên object |

Publisher không có phương thức “xác minh mật khẩu” hay “đăng nhập người dùng”. Nó **không** tự đưa authorities vào `SecurityContext`; đó là trách nhiệm của authentication flow và providers.

### 3.1. Vì sao tách interface khỏi implementation?

Một custom `AuthenticationEventPublisher` có thể chuyển kết quả vào Spring Application Events, metrics collector hoặc audit pipeline. Tuy nhiên phải giữ semantics, không nuốt lỗi bảo mật quan trọng, không tái sử dụng credentials và không tự phát success giả khi quá trình authenticate chưa thành công.

Triển khai mặc định phù hợp hầu hết ứng dụng vì có mapping lỗi chuẩn và dùng cơ chế event quen thuộc của Spring Framework.

## 4. DefaultAuthenticationEventPublisher hoạt động như thế nào?

Class:

~~~java
org.springframework.security.authentication.DefaultAuthenticationEventPublisher
~~~

Class này implements `AuthenticationEventPublisher` và `ApplicationEventPublisherAware`. Khi được truyền `ApplicationEventPublisher` hoặc được Spring inject đúng cách, nó có thể phát các event qua application context.

Ví dụ bean đúng theo Spring Security:

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    return new DefaultAuthenticationEventPublisher(applicationEvents);
}
~~~

Đây là **mảnh cấu hình** cần đặt trong một class `@Configuration`/`@SpringBootApplication` với import tương ứng. Bài lab ở mục 7 đưa ra chương trình hoàn chỉnh.

**Phân biệt hai publisher:**

- `AuthenticationEventPublisher`: interface của **Spring Security**, nhận thành công/thất bại authentication.
- `ApplicationEventPublisher`: interface của **Spring Framework**, phát sự kiện cho hệ thống listener nói chung.

`DefaultAuthenticationEventPublisher` là lớp **nối hai thế giới**: biến kết quả authentication thành event Spring để listener sử dụng.

### 4.1. Xác thực thành công

Sau khi `ProviderManager.authenticate(...)` có kết quả thành công, nó gọi publisher với đối tượng `Authentication`, từ đó mặc định phát:

~~~text
AuthenticationSuccessEvent
~~~

Listener có thể truy cập:

~~~java
@EventListener
void onSuccess(AuthenticationSuccessEvent event) {
    Authentication authentication = event.getAuthentication();
    // Đã xác thực; lấy metadata tối thiểu để audit.
}
~~~

Không dùng event này thay cho quyết định cấp quyền. Quyền truy cập còn được kiểm ở authorization phase; một authentication thành công không có nghĩa mọi endpoint đều `permitAll`.

### 4.2. Xác thực thất bại

Với failure, publisher xem **class chính xác** của `AuthenticationException` rồi chọn loại event theo mapping.

Bảng mặc định trong tài liệu Spring Security 6.5:

| Exception được phát sinh | Event mặc định |
| --- | --- |
| `BadCredentialsException` | `AuthenticationFailureBadCredentialsEvent` |
| `UsernameNotFoundException` | `AuthenticationFailureBadCredentialsEvent` |
| `AccountExpiredException` | `AuthenticationFailureExpiredEvent` |
| `ProviderNotFoundException` | `AuthenticationFailureProviderNotFoundEvent` |
| `DisabledException` | `AuthenticationFailureDisabledEvent` |
| `LockedException` | `AuthenticationFailureLockedEvent` |
| `AuthenticationServiceException` | `AuthenticationFailureServiceExceptionEvent` |
| `CredentialsExpiredException` | `AuthenticationFailureCredentialsExpiredEvent` |
| `InvalidBearerTokenException` | `AuthenticationFailureBadCredentialsEvent` |

Không phải mọi `AuthenticationException` đều được map. Nếu exception không nằm trong map và không có fallback, có thể **không phát failure event** dù authentication vẫn thất bại và request bị từ chối.

**Lưu ý:** `UsernameNotFoundException` và `BadCredentialsException` cùng map vào bad credentials event. `DaoAuthenticationProvider` thông thường có thể che lỗi user không tồn tại bằng lỗi bad credentials, tránh phân biệt “user không có” với “password sai” trên phản hồi bên ngoài.

## 5. Bẫy quan trọng: exception mapping là EXACT CLASS

`DefaultAuthenticationEventPublisher` so khớp **class thực tế** của exception, không tự dùng cơ chế “is-a” theo toàn bộ class hierarchy.

Ví dụ:

~~~java
class CustomBadCredentialsException
        extends BadCredentialsException {
    CustomBadCredentialsException(String message) {
        super(message);
    }
}
~~~

Nếu publisher chỉ có mapping mặc định cho `BadCredentialsException.class`:

~~~text
new BadCredentialsException(...)        → mapped
new CustomBadCredentialsException(...)  → KHÔNG tự mapped
~~~

Một class con có tên gần giống hoặc kế thừa class đã được map **không tự tạo event**. Đây là lý do phổ biến khiến listener không nhận failure event từ custom provider.

### 5.1. Bổ sung exception mapping

API được hỗ trợ:

~~~java
setAdditionalExceptionMappings(
    Map<Class<? extends AuthenticationException>,
        Class<? extends AbstractAuthenticationFailureEvent>>
)
~~~

Ví dụ bean **minh họa** (cần class custom ở trên và import Spring Security):

~~~java
@Bean
AuthenticationEventPublisher authenticationEventPublisher(
        ApplicationEventPublisher applicationEvents) {
    var publisher =
        new DefaultAuthenticationEventPublisher(applicationEvents);

    publisher.setAdditionalExceptionMappings(Map.of(
        CustomBadCredentialsException.class,
        AuthenticationFailureBadCredentialsEvent.class
    ));

    return publisher;
}
~~~

Bản map mới **hợp nhất** với các mapping mặc định, không đòi viết lại toàn bộ danh sách. Spring Security 6.5 hỗ trợ overload dùng `Map<Class, Class>`. Overload cũ nhận `Properties` đã **deprecated**; không sử dụng trong code mới.

Event class phải là concrete subclass của `AbstractAuthenticationFailureEvent` và có constructor phù hợp:

~~~java
MyFailureEvent(Authentication authentication,
               AuthenticationException exception)
~~~

Nếu tạo event type riêng, listener có thể lọc theo class đó. Với lỗi nghiệp vụ tùy chỉnh, phải cân nhắc exception nào thật sự là authentication failure thay vì lỗi authorization hay lỗi hệ thống ngoài authentication.

### 5.2. Fallback cho exception chưa map

Publisher có thêm:

~~~java
setDefaultAuthenticationFailureEvent(
    Class<? extends AbstractAuthenticationFailureEvent> eventClass)
~~~

Tùy code/version và contract, có thể dùng fallback khi exception không có mapping. Để có loại event rõ ràng, có thể định nghĩa concrete subclass:

~~~java
// Mảnh class minh họa; đặt trong file Java cùng package/import.
public class UnmappedAuthenticationFailureEvent
        extends AbstractAuthenticationFailureEvent {

    public UnmappedAuthenticationFailureEvent(
            Authentication authentication,
            AuthenticationException exception) {
        super(authentication, exception);
    }
}
~~~

Và cấu hình:

~~~java
publisher.setDefaultAuthenticationFailureEvent(
    UnmappedAuthenticationFailureEvent.class);
~~~

Điều này hữu ích khi cần **không bỏ sót failure audit**. Đừng map mọi loại exception chưa biết sang `AuthenticationFailureBadCredentialsEvent` nếu chúng có thể là sự cố hệ thống, tài khoản bị khóa hoặc tình huống cần vận hành xử lý khác.

**Phân biệt:** nếu không có event, điều đó chưa chứng minh authentication thành công. Có thể do thiếu publisher, custom exception chưa map, luồng không đi qua manager đã được nối publisher hoặc subscriber không hoạt động.

## 6. Spring Boot có tự đăng ký publisher không?

Trong **Spring Boot 3.5**, Security Auto-Configuration thường cung cấp một bean `DefaultAuthenticationEventPublisher` theo điều kiện **chưa có bean `AuthenticationEventPublisher` khác**. Vì vậy trong project Boot chuẩn, bạn **có thể không cần** viết bean publisher để có events.

Nhưng cần phân biệt:

| Trường hợp | Điều cần lưu ý |
| --- | --- |
| Boot + Spring Security theo auto-configuration chuẩn | Boot có thể tạo `DefaultAuthenticationEventPublisher` và đăng ký cho authentication manager được framework cấu hình |
| Tự tạo bean `AuthenticationEventPublisher` | Bean của bạn thay default conditional bean của Boot; phải có mapping/behavior đúng |
| Tự `new ProviderManager(provider)` | **Mặc định không tự phát event**; cần gọi `setAuthenticationEventPublisher(...)` |
| Dùng parent `AuthenticationManager` | Tránh cấu hình parent và child cùng phát một kết quả thành **event trùng** |
| Custom filter không gọi AuthenticationManager | Publisher có thể không được gọi |
| Tự bắt AuthenticationException nhưng nuốt lỗi ở tầng trước manager | Có thể không có event đúng kết quả mong đợi |
| Không dùng Spring Boot | Theo tài liệu Spring Security, chủ động đăng ký publisher bean và nối với manager thích hợp |

Trong Spring Security, `ProviderManager` có publisher mặc định không làm gì nếu bạn **tạo manager thủ công**. Tạo bean publisher **không tự động nối** nó vào mọi `ProviderManager` được tạo bằng `new` ở nơi khác.

Hình thức nối rõ ràng:

~~~java
DaoAuthenticationProvider provider =
    new DaoAuthenticationProvider(userDetailsService);
provider.setPasswordEncoder(passwordEncoder);

ProviderManager manager = new ProviderManager(provider);
manager.setAuthenticationEventPublisher(authenticationEventPublisher);
~~~

Đây là mảnh cấu hình trong một bean/method với các biến đã được inject. Chỉ tạo **một** publisher phù hợp cho manager theo thiết kế, không vừa tự gọi `publishAuthenticationSuccess(...)` trong provider vừa để `ProviderManager` phát lại cùng event.

## 7. Ví dụ Spring Boot 3.5 / Java 17+ có thể chạy

Ví dụ sau cố tình cấu hình **publisher và ProviderManager tường minh** để nhìn rõ ranh giới. Giao diện truy cập là HTTP Basic cho dễ thử bằng `curl`; trong production dùng HTTPS. Đây là chương trình demo Servlet, không có dependency OAuth/LDAP.

Mục tiêu:

- User demo `observer` / password `lab-password` được hash bằng BCrypt.
- Request đến `/me` xác thực qua `DaoAuthenticationProvider`.
- `ProviderManager` phát event thành công hoặc lỗi nhờ publisher đã được gắn.
- Listener Spring `@EventListener` ghi **tên loại event** vào log, không ghi username, mật khẩu, Basic header hoặc token.
- Không tự log nguyên `Authentication` hay exception message.

### 7.1. Maven project

Cấu trúc:

~~~text
authentication-events-demo/
├── pom.xml
└── src/main/
    └── java/
        └── demo/
            └── events/
                └── AuthenticationEventsDemoApplication.java
~~~

Tệp `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>authentication-events-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

Dùng parent BOM của Spring Boot để lấy Spring Security 6.5 phù hợp. Mã ví dụ không cần một “event starter” thứ ba; Spring Framework Application Events đã nằm trong hệ sinh thái Boot/Security.

### 7.2. Java hoàn chỉnh

Tệp `src/main/java/demo/events/AuthenticationEventsDemoApplication.java`:

~~~java
package demo.events;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationEventPublisher;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.DefaultAuthenticationEventPublisher;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authentication.event.AbstractAuthenticationFailureEvent;
import org.springframework.security.authentication.event.AuthenticationSuccessEvent;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthenticationEventsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthenticationEventsDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("observer")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build());
    }

    @Bean
    AuthenticationEventPublisher authenticationEventPublisher(
            ApplicationEventPublisher events) {
        return new DefaultAuthenticationEventPublisher(events);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder,
            AuthenticationEventPublisher publisher) {
        var dao = new DaoAuthenticationProvider(users);
        dao.setPasswordEncoder(encoder);

        var manager = new ProviderManager(dao);
        manager.setAuthenticationEventPublisher(publisher);
        return manager;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager)
            throws Exception {

        http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class Api {

        @GetMapping("/health")
        String health() {
            return "Authentication events demo ready";
        }

        @GetMapping("/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("user", authentication.getName());
        }
    }

    @Component
    static class SecurityEventListener {
        private static final Logger log =
            LoggerFactory.getLogger(SecurityEventListener.class);

        @EventListener
        void onSuccess(AuthenticationSuccessEvent event) {
            // Không log credential, toàn bộ Authentication
            // hoặc thông tin định danh nhạy cảm.
            log.info("AUTH_SUCCESS eventType={}",
                event.getClass().getSimpleName());
        }

        @EventListener
        void onFailure(AbstractAuthenticationFailureEvent event) {
            log.warn("AUTH_FAILURE eventType={} exceptionType={}",
                event.getClass().getSimpleName(),
                event.getException().getClass().getSimpleName());
        }
    }
}
~~~

### 7.3. Giải thích các bean

1. `PasswordEncoder` là BCrypt; user demo được mã hóa lúc ứng dụng khởi động, không dùng `{noop}` trong store.
2. `DaoAuthenticationProvider` kiểm mật khẩu của `UserDetailsService` và tạo authenticated token.
3. `ProviderManager` tự tạo được **gắn chính xác một** `AuthenticationEventPublisher` bằng `setAuthenticationEventPublisher(...)`.
4. Bean `DefaultAuthenticationEventPublisher` lấy `ApplicationEventPublisher` của Spring Framework qua constructor.
5. `HttpSecurity.authenticationManager(manager)` bảo đảm HTTP Basic flow sử dụng manager vừa cấu hình, thay vì suy đoán auto-configuration sẽ tự nối manager nào.
6. `@EventListener` là subscriber; không tham gia kiểm mật khẩu và không trả 401/200 cho client.
7. `/health` public để kiểm khởi động; `/me` cần xác thực. `anyRequest().denyAll()` không cho thêm route bất ngờ.
8. Static nested `@Component` được component scan của Spring Boot phát hiện khi nằm trong package ứng dụng.

**Thận trọng với các hệ đã có manager/filter khác:** không bê nguyên manager bean này vào một ứng dụng nhiều authentication providers/SSO/JWT nếu chưa kiểm tra cấu hình. Bài lab cô lập chỉ dùng Dao provider.

### 7.4. Chạy

Với Java 17+ và Maven đã cài, chạy tại thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Hoặc nếu project có Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows có thể dùng `mvnw.cmd spring-boot:run`.

Kiểm tra ứng dụng:

~~~bash
curl -i http://127.0.0.1:8080/health
~~~

Phản hồi dự kiến có HTTP 200 và body:

~~~text
Authentication events demo ready
~~~

Đăng nhập đúng vào endpoint cần xác thực:

~~~bash
curl -i --user observer:lab-password http://127.0.0.1:8080/me
~~~

Ví dụ response body:

~~~json
{"user":"observer"}
~~~

Trong server log thường xuất hiện:

~~~text
AUTH_SUCCESS eventType=AuthenticationSuccessEvent
~~~

Thử sai mật khẩu:

~~~bash
curl -i --user observer:wrong-password http://127.0.0.1:8080/me
~~~

Dự kiến HTTP 401; log listener nhận một failure event loại:

~~~text
AUTH_FAILURE eventType=AuthenticationFailureBadCredentialsEvent exceptionType=BadCredentialsException
~~~

**Các log dòng trên là phần nội dung nhận diện**, không bao gồm prefix timestamp/logger/thread mà Spring Boot sẽ bổ sung. Số lần event phụ thuộc số lần gọi thực và filter chain. Nếu copy password vào terminal, coi đây chỉ là **lab credential**, không dùng với tài khoản thật; shell history và process list có thể làm lộ credentials. Chạy production qua HTTPS và secrets an toàn.

### 7.5. Tại sao không thấy event cho mỗi request?

Khi dùng Basic, request có header hợp lệ thường được kiểm mỗi lần, nhưng có thể bị ảnh hưởng bởi session/security-context caching hoặc cơ chế filter được cấu hình thêm. Với form login, request tiếp theo trên session thường không cần xác thực lại. **Đếm event không phải đếm request, không phải số người đăng nhập đang online.**

## 8. Ví dụ Java 17 độc lập: vì sao subclass không được map?

Để hiểu chính xác quy tắc mapping mà không cần chạy Spring Boot, chương trình sau mô phỏng **exact class lookup** bằng Java `Map.get(exception.getClass())`.

**Đây chỉ là demo Java Collection** — không phải bản triển khai `DefaultAuthenticationEventPublisher` và không tự phát Spring Application Events.

Tạo `ExactExceptionMappingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ExactExceptionMappingDemo {

    static class BadCredentials extends RuntimeException {}
    static class CustomBadCredentials extends BadCredentials {}

    public static void main(String[] args) {
        Map<Class<?>, String> mapping = new HashMap<>();
        mapping.put(BadCredentials.class,
                "AuthenticationFailureBadCredentialsEvent");

        System.out.println("base=" +
            mapping.get(new BadCredentials().getClass()));
        System.out.println("subclass=" +
            mapping.get(new CustomBadCredentials().getClass()));

        mapping.put(CustomBadCredentials.class,
                "AuthenticationFailureBadCredentialsEvent");

        System.out.println("afterMapping=" +
            mapping.get(new CustomBadCredentials().getClass()));
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac --release 17 ExactExceptionMappingDemo.java
java ExactExceptionMappingDemo
~~~

**Stdout chính xác:**

~~~text
base=AuthenticationFailureBadCredentialsEvent
subclass=null
afterMapping=AuthenticationFailureBadCredentialsEvent
~~~

Dòng thứ hai cho thấy class con không được ánh xạ chỉ nhờ kế thừa. Dòng thứ ba minh họa lợi ích của `setAdditionalExceptionMappings(...)` trong publisher thật.

## 9. Event khác SuccessHandler / FailureHandler / AccessDeniedHandler

Các extension point này xử lý việc **khác nhau**:

| Thành phần | Được gọi trong ngữ cảnh nào? | Nhiệm vụ phù hợp |
| --- | --- | --- |
| `AuthenticationEventPublisher` | Xử lý kết quả authentication (thường qua manager) | Phát success/failure event |
| `@EventListener(AuthenticationSuccessEvent)` | Spring Application Event đã được phát | Audit, metrics, phát hiện bất thường |
| `AuthenticationSuccessHandler` | Filter đăng nhập tương tác thành công | HTTP redirect, response, saved request |
| `AuthenticationFailureHandler` | Filter đăng nhập tương tác thất bại | Redirect `?error`, phản hồi HTTP |
| `AuthenticationEntryPoint` | Request cần authentication chưa có | 401 challenge hoặc redirect tới login |
| `AccessDeniedHandler` | Request đã xác thực nhưng thiếu quyền | Phản hồi 403/quy tắc xử lý từ chối |
| `AuthorizationDeniedEvent` / method authorization events | Quyết định authorization khi được bật | Phân tích vi phạm quyền, không phải lỗi mật khẩu |
| `InteractiveAuthenticationSuccessEvent` | Một số interactive authentication flow | Theo dõi hoàn tất đăng nhập tương tác |

**Hai sự kiện success không giống nhau:** `InteractiveAuthenticationSuccessEvent` không kế thừa `AuthenticationSuccessEvent`, nhằm tránh listener của loại này nhận trùng như thể đây cùng một lớp event. Không đếm cả hai cộng lại mà mặc định coi là hai lần người dùng đăng nhập.

Một HTTP 403 do thiếu `ROLE_ADMIN` thường **không** có nghĩa là `BadCredentialsException` hay `AuthenticationFailureBadCredentialsEvent`, vì user có thể đã xác thực đúng nhưng không có quyền.

### 9.1. AuthenticationFailureEvent và AuthenticationException

Danh sách class failure ở mục 4 là những subtype của `AbstractAuthenticationFailureEvent`. Mỗi event failure giữ exception gốc qua `getException()`. Trong listener:

~~~java
@EventListener
void onFailure(AbstractAuthenticationFailureEvent event) {
    String reasonType =
        event.getException().getClass().getSimpleName();
    // Ghi category/metric đã chuẩn hóa, không log stacktrace
    // hoặc username/raw credentials tùy tiện.
}
~~~

Không cần (và không nên) trả nguyên `event.getException().getMessage()` về client; message có thể mô tả nội bộ hoặc chứa dữ liệu không nên tiết lộ.

## 10. Bảo mật: event có thể chứa dữ liệu nhạy cảm

Đối tượng `Authentication` có thể chứa:

- Username/principal và authorities.
- `credentials` như raw password trong authentication request **trước khi bị xóa**.
- `details` như địa chỉ IP hoặc session ID.
- Bearer token hoặc thông tin do provider/filter đặt trong details.
- Exception chứa message và cause với dữ liệu môi trường.

Do đó:

1. **Không log `Authentication.toString()`, `getCredentials()`, toàn bộ exception hoặc raw event object** nếu chưa có chiến lược masking được kiểm tra.
2. Ưu tiên metadata tối thiểu: loại event, phương thức auth, category lỗi, timestamp server, correlation ID, user ID nội bộ đã được bảo vệ khi có.
3. Username trong failure event có thể do client nhập bất kỳ; không dùng làm khóa khóa tài khoản mà thiếu rate-limit theo IP/device/user và chống enumeration/DoS.
4. Nếu có địa chỉ IP, lấy theo trusted reverse-proxy chain; không tin header `X-Forwarded-For` từ Internet.
5. Log/metrics cần retention, phân quyền truy cập, giới hạn PII và chống log injection.
6. Không đưa password, OTP, Authorization header, cookie hoặc private key vào tracing/exporter.
7. Giới hạn cardinality: metrics không nên mang label username hoặc token vì vừa rò dữ liệu vừa làm hệ thống monitoring quá tải.

### 10.1. Event listener đồng bộ hay bất đồng bộ?

Thông thường Spring Application Events được xử lý **đồng bộ** nếu không cấu hình executor phù hợp. Vì vậy listener chạy chậm có thể tăng thời gian đăng nhập; một listener ném exception không được xử lý có thể ảnh hưởng authentication flow hoặc phản hồi HTTP theo nơi phát event.

Với audit quan trọng:

- Thu thập payload **đã sanitize** và tối thiểu.
- Dùng queue/outbox khi cần xử lý tác vụ chậm; giới hạn dung lượng và có retry/backpressure/idempotency.
- Không gửi raw `Authentication`/password tới message broker.
- Quy định **fail closed/fail open** phù hợp với mức quan trọng của audit, nhưng đừng để listener phụ tình cờ phá mọi login vì dịch vụ metric chậm.
- Đừng phát success event giả để “giải quyết” thiếu event trong log.

Event của Spring không tự cung cấp lịch sử audit bền vững sau khi process restart. Nếu cần điều tra bảo mật, phải có log/metric/audit store với policy lưu trữ và kiểm soát thích hợp.

## 11. Bài toán monitoring và phát hiện tấn công

Các nhóm quan sát phù hợp:

| Metric/sự kiện | Mục đích | Cảnh báo |
| --- | --- | --- |
| Success count theo auth method và service | Đánh giá lưu lượng authentication | Không dùng làm số người duy nhất |
| Failure bad credentials | Phát hiện password spraying/brute-force | Tránh label username thô |
| Failure locked/disabled/expired | Theo dõi trạng thái account và hỗ trợ vận hành | Phân biệt với bad password |
| Failure service exception | Sự cố DB/LDAP/IdP hoặc provider | Tránh hiểu nhầm là credential tấn công |
| Provider not found | Sai wiring/config authentication manager | Cần kiểm tra manager/providers |
| Success sau nhiều failure | Tín hiệu bất thường theo risk policy | Không tự kết luận tài khoản đã bị chiếm |
| Event không xuất hiện đột ngột | Instrumentation bị lỗi, manager bị thay đổi | So với request/authentication telemetry |

Ví dụ một chiến lược detection:

~~~text
Nếu cùng nguồn có nhiều failure trong khoảng ngắn:
  → tăng risk score, rate-limit, captcha hoặc step-up theo policy.

Nếu có nhiều failure rồi success:
  → audit thêm; không tự thông báo "tấn công thành công"
    khi chưa đối chiếu identity, session, IP và device.

Nếu xuất hiện AuthenticationFailureServiceExceptionEvent:
  → kiểm sức khỏe provider/LDAP/DB trước khi khóa user.
~~~

Đó là **pseudocode nghiệp vụ**, không phải các event Spring tự thực hiện sẵn. `DefaultAuthenticationEventPublisher` **không** tự khóa tài khoản, không tự rate limit, không cấp quyền hoặc gửi email; nó phát event cho consumer.

## 12. Tránh duplicate events khi có nhiều AuthenticationManager

Một ứng dụng có thể có:

~~~text
Child ProviderManager
    |
    +-- Provider A
    +-- Provider B
    |
    +--> Parent AuthenticationManager
~~~

Theo Javadoc, `ProviderManager` có thể phát event kể cả khi kết quả/exception đến từ **parent**. Nếu parent cũng được cấu hình tự phát cùng event, subscriber có thể nhận **hai events cho một authentication attempt**.

Do đó:

- Xác định nơi **sở hữu việc phát event** trong manager hierarchy.
- Tránh parent và child cùng gắn publisher cho cùng kết quả nếu không mong đợi duplication.
- Không tự gọi publisher trong custom provider rồi để manager gọi thêm.
- Khi có nhiều security filter chains, test mỗi chain và manager được dùng.
- Với queue/audit, sử dụng correlation/deduplication nếu hạ tầng có thể gửi lại.

Vì `ProviderManager` mặc định dùng publisher rỗng trong trường hợp tự new, có hai thái cực: **không event nào** hoặc **event trùng**. Cả hai cần kiểm tra bằng integration test thay vì suy đoán từ bean count.

## 13. Kiểm thử đúng mức

### 13.1. Unit test publisher

Có thể khởi tạo publisher với một fake `ApplicationEventPublisher` và gọi:

~~~java
var publisher = new DefaultAuthenticationEventPublisher(events);
publisher.publishAuthenticationSuccess(verifiedAuthentication);
publisher.publishAuthenticationFailure(
    new BadCredentialsException("bad credentials"),
    authenticationRequest);
~~~

Đây là **đoạn kiểm thử minh họa**, cần biến `events`, `verifiedAuthentication` và `authenticationRequest` được cung cấp bởi test. Khi bắt events, xác nhận:

- Success tạo `AuthenticationSuccessEvent`.
- Failure `BadCredentialsException` tạo `AuthenticationFailureBadCredentialsEvent`.
- Exception subclass chưa map không có event khi không cấu hình fallback.
- Sau khi bổ sung map class con, publisher phát đúng event class.
- Fallback cho exception chưa map chỉ hoạt động sau khi được cấu hình.

Không dùng mock Authentication chứa password thật khi assertion/log test có thể in ra dữ liệu đó.

### 13.2. Integration test Spring Boot

Một bộ test nên kiểm cả manager wiring và subscriber:

1. GET `/health` không credentials trả 200.
2. GET `/me` không credentials bị từ chối (thông thường 401).
3. GET `/me` với user/password đúng được 200 và listener ghi success.
4. GET `/me` với password sai được 401 và listener ghi `AuthenticationFailureBadCredentialsEvent`.
5. Nếu khai báo custom provider phát `CustomBadCredentialsException`, thêm mapping và kiểm event xuất hiện.
6. Nếu tự tạo `ProviderManager` mà không set publisher, test phải phát hiện không có event.
7. Nếu dùng parent manager, kiểm success/failure không bị nhân đôi.
8. Không nhầm truy cập 403 thiếu role với password failure.
9. Không có password/Bearer token/raw exception message trong log hoặc metrics.
10. Listener lỗi không được làm authentication thực thi trái chính sách; quản lý failure handling.

**Lưu ý:** khi test bằng `MockMvc` và `spring-security-test` helper như `with(user(...))`, một số helper chỉ **đặt sẵn Authentication trong SecurityContext** thay vì chạy qua `AuthenticationManager`. Những test như vậy không chứng minh publisher hoạt động. Với integration test cần đi qua endpoint/manager thật.

### 13.3. Khi test event không tới listener

Kiểm tra theo thứ tự:

1. Đã có `DefaultAuthenticationEventPublisher` bean hoặc một publisher đúng trong application context?
2. `ProviderManager` thật sự xử lý request đó là manager nào?
3. Manager có được gọi `setAuthenticationEventPublisher(...)` chưa (nếu tự tạo)?
4. Request đang được authenticate mới hay đang dùng session/authentication đã cache?
5. Failure exception có đúng class được map không?
6. Listener có `@Component`/`@EventListener` và được component scan?
7. Có parent/child manager, event duplicate hoặc event chỉ xuất hiện ở manager khác?
8. Có filter khác/bypass/custom login endpoint tạo session mà không qua manager?
9. Có proxy/lớp OAuth2 login khác đang xác thực ở nơi khác, chỉ truyền principal về?
10. Listener có đang throw exception hoặc queue/monitor bị mất dữ liệu?

## 14. Những lỗi hiểu nhầm thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| “Đã có `@EventListener` thì chắc chắn sẽ có event” | Cần publisher phát event và manager/filter chạy qua nó |
| “Spring Security always emits event cho mọi request” | Event gắn authentication attempt, không phải mọi GET |
| “Default publisher tự xử lý mọi subclass của BadCredentials” | **Exact exception class matching**; subclass cần map/fallback |
| “Event failure nghĩa user chưa có trong database” | Lỗi có thể do password, locked, disabled, provider unavailable, token invalid |
| “Success event bằng request đã được ủy quyền” | Authorization vẫn có thể 403 |
| “AccessDeniedHandler phát AuthenticationFailureEvent” | 403 authorization khác authentication failure |
| “Một Custom ProviderManager sẽ dùng bean event publisher tự động” | Cần wiring thủ công nếu manager tự new |
| “Mọi exception bắt được đều là AuthenticationFailure” | Lỗi nghiệp vụ không thuộc authentication stage |
| “Bật async @EventListener làm audit bền vững” | Queue/in-memory vẫn có thể mất dữ liệu; cần persistence/độ bền riêng |
| “Logger ghi toàn bộ Authentication là tiện nhất” | Rất dễ lộ credentials/details/token |
| “Có event success nghĩa session logout đã thành công” | Logout là lifecycle khác; cần event/handler phù hợp |
| “HTTP Basic success mỗi request nghĩa user login lại nhiều lần” | Basic thường kiểm credentials trên request; không đồng nghĩa login tương tác |
| “Chỉ tạo Bean nhưng parent manager cũng phát thì không sao” | Có thể duplicate event |
| “Tạo AuthenticationSuccessEvent cho mọi HTTP 200” | HTTP 200 không bảo đảm authentication vừa diễn ra |

## 15. Checklist triển khai production

**Cấu hình và contract**

- [ ] Xác định chính xác AuthenticationManager và AuthenticationProvider đang xử lý mỗi login path.
- [ ] Có publisher đúng, nối với manager tự tạo.
- [ ] Default mapping phù hợp; custom exceptions được map theo **exact class**.
- [ ] Tách authn event khỏi authz denied events và HTTP handlers.
- [ ] Không tạo duplicate event qua parent/child manager hoặc custom provider.
- [ ] Có test success/failure thật ở từng loại authentication quan trọng.

**Bảo mật và quyền riêng tư**

- [ ] Không log password, session cookie, Bearer token, raw Authentication hoặc exception message tùy ý.
- [ ] Audit record dùng dữ liệu đã sanitize, có PII retention/access control.
- [ ] Rate limiting và account protection do security policy thực hiện riêng, không chỉ qua event.
- [ ] Không tạo cross-account lockout chỉ dựa vào username do attacker nhập.
- [ ] Mọi hành động tự động từ event được xác minh risk policy, tránh spam/DoS.
- [ ] Listener không làm lộ dữ liệu người dùng qua telemetry labels.

**Vận hành**

- [ ] Kiểm việc listener chạy đồng bộ và ảnh hưởng login latency.
- [ ] Với audit quan trọng, có queue/outbox/retry/backpressure/dedup phù hợp.
- [ ] Có monitoring cảnh báo khi event volume về 0 hoặc tăng bất thường.
- [ ] Phân biệt lỗi xác thực với sự cố provider/service.
- [ ] Có trace/correlation ID cho nhiều instance và nhiều auth flows.
- [ ] Biết giới hạn: Spring Application Events không tự là durable audit store.

## 16. Câu hỏi tự kiểm tra

1. `AuthenticationEventPublisher` và `ApplicationEventPublisher` khác nhau ở đâu?
2. `DefaultAuthenticationEventPublisher` làm gì khi `ProviderManager` trả authentication thành công?
3. Một `BadCredentialsException` được map thành event nào?
4. Vì sao custom exception kế thừa `BadCredentialsException` có thể không phát event?
5. Muốn bổ sung mapping lỗi custom, sử dụng API nào? Vì sao nên dùng Map overload?
6. Tại sao custom `new ProviderManager(...)` có thể không phát event dù trong context đã có publisher bean?
7. Sự khác nhau giữa `AuthenticationSuccessEvent` và `InteractiveAuthenticationSuccessEvent` là gì?
8. HTTP 403 thiếu role có nghĩa đã phát `AuthenticationFailureBadCredentialsEvent` không?
9. Vì sao không nên log toàn bộ `event.getAuthentication()` ở failure listener?
10. Tại sao listener đồng bộ nặng có thể làm chậm login?
11. Một lần đăng nhập form có session và nhiều GET tiếp theo nên có bao nhiêu success events?
12. Khi parent và child manager cùng phát event, vấn đề nào xuất hiện?
13. Vì sao test dùng `with(user(...))` không nhất thiết kiểm publisher?
14. Event giúp audit nhưng có tự lưu bền vững khi ứng dụng restart không?

**Kết luận:** `AuthenticationEventPublisher` là hợp đồng phát kết quả authentication, `DefaultAuthenticationEventPublisher` là cầu nối từ `ProviderManager` sang **Spring Application Events**, với mapping lỗi chuẩn **theo class chính xác**. Muốn quan sát đáng tin cần **wiring manager đúng, listener phù hợp, không duplicate, không log credentials và kiểm thử từng authentication flow**.

## 17. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Authentication Events](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/events.html)
- [Spring Security 6.5 — AuthenticationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/AuthenticationEventPublisher.html)
- [Spring Security 6.5 — DefaultAuthenticationEventPublisher API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/DefaultAuthenticationEventPublisher.html)
- [Spring Security 6.5 — ProviderManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html)
- [Spring Security 6.5 — AuthenticationFailureBadCredentialsEvent](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/event/AuthenticationFailureBadCredentialsEvent.html)
- [Spring Boot 3.5 — Spring Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Framework — Annotation-driven event listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation)
