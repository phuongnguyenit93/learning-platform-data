# Kiểm soát xung đột bean và hiểu điều kiện cấu hình tự động ngừng áp dụng trong Spring Security reactive

## 1. Mục tiêu bài học

Khi khởi tạo Spring Boot + Spring WebFlux + Spring Security, ứng dụng thường đã có cấu hình bảo mật mặc định dù bạn chưa tạo bean bảo mật nào. Sau khi thêm một bean của riêng mình, một phần cấu hình mặc định có thể **nhường quyền (back off)**. Đôi khi ứng dụng vẫn khởi động nhưng endpoint hoạt động khác mong đợi; đôi khi quá trình tạo ApplicationContext thất bại vì bean trùng tên hoặc vì có nhiều bean cùng kiểu.

Bài này giúp bạn:

1. Hiểu cách Spring Boot đánh giá điều kiện auto-configuration, đặc biệt `@ConditionalOnMissingBean`, `@ConditionalOnClass` và `@ConditionalOnWebApplication`.
2. Phân biệt cấu hình **chuỗi WebFilter bảo mật**, cấu hình **nguồn người dùng/xác thực** và việc **bật hạ tầng Spring Security reactive**.
3. Biết bean nào làm cấu hình mặc định ngừng áp dụng, bean nào **không** tác động tới phần còn lại.
4. Nhận diện ba nhóm sự cố khác nhau: **trùng bean name**, **nhiều bean type gây mơ hồ khi inject**, và **điều kiện auto-config không khớp**.
5. Chạy được một ví dụ Java 17+ và xem báo cáo điều kiện để xác minh thay đổi.

**Trọng tâm:** Hãy điều tra **kiểu bean**, **điều kiện được đánh giá** và **SecurityWebFilterChain thực tế** trước khi sửa cấu hình. Sự tồn tại của một bean custom không có nghĩa toàn bộ Spring Security tự động bị tắt.

## 2. Bức tranh tổng thể: từ classpath tới bean đang chạy

Spring Boot bắt đầu từ các thư viện trên classpath và trạng thái ApplicationContext. Một lớp auto-configuration thường có điều kiện kiểu:

~~~java
// Ví dụ MINH HỌA cấu trúc, không phải mã nguồn đầy đủ của Spring Boot
@AutoConfiguration
@ConditionalOnClass(SomeSecurityType.class)
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
class ExampleReactiveAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ExampleService.class)
    ExampleService exampleService() {
        return new DefaultExampleService();
    }
}
~~~

Những class `SomeSecurityType`, `ExampleService`, `DefaultExampleService` ở ví dụ này là **tên giả định để minh họa cơ chế**, không dùng để biên dịch. Có bốn ý:

- `@AutoConfiguration` đánh dấu cấu hình do Boot đóng góp. Ứng dụng bật tự động cấu hình thông qua `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.
- `@ConditionalOnClass` chỉ áp dụng khi các class cần thiết xuất hiện trên classpath.
- `@ConditionalOnWebApplication(type = REACTIVE)` chỉ áp dụng với ứng dụng web reactive.
- `@ConditionalOnMissingBean` chỉ tạo phần mặc định nếu **chưa có bean đáp ứng tiêu chí**. Tiêu chí có thể là class/interface, tên bean, annotation hoặc nhiều điều kiện kết hợp.

**Back off** nghĩa là Boot **không đăng ký một phần cấu hình mặc định do điều kiện không đạt**, để bean do ứng dụng cung cấp đảm nhận trách nhiệm đó. Nó khác với việc xóa bean đang chạy, vô hiệu hóa cả framework hoặc tự động hợp nhất các rule.

Các điều kiện được kiểm tra ở thời điểm xử lý bean definitions. `@ConditionalOnMissingBean` đặc biệt phù hợp với **auto-configuration được xử lý sau bean do người dùng khai báo**; không nên tùy tiện gắn nó lên mọi `@Configuration` thông thường rồi mặc định rằng thứ tự đăng ký bean sẽ luôn giống nhau.

## 3. Ba tầng cấu hình riêng trong Spring Security WebFlux

Đây là phần quan trọng nhất để tránh nhầm lẫn:

| Tầng | Thành phần thường thấy | Đảm nhiệm | Khi bạn thay đổi |
| --- | --- | --- | --- |
| **Hạ tầng web security** | `WebFilterChainProxy`, `@EnableWebFluxSecurity`, các `WebFilter` | Gắn Spring Security vào WebFlux và điều phối các security chain | Bean proxy custom có tác động ở cấp hạ tầng; đây là can thiệp nâng cao |
| **Chính sách HTTP request** | `SecurityWebFilterChain` tạo từ `ServerHttpSecurity` | HTTP Basic, form login, JWT, matcher và authorization rules | Tự định nghĩa chuỗi/rule của ứng dụng; phải bảo vệ đầy đủ route liên quan |
| **Nguồn danh tính và xác thực** | `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` | Tải user, kiểm tra credentials và tạo Authentication | Thay cơ chế user mặc định; không tự viết lại các rule URL |

Một số mối quan hệ cần nhớ:

- Có `SecurityWebFilterChain` custom **không đồng nghĩa** đã cung cấp `ReactiveUserDetailsService` custom.
- Có `ReactiveUserDetailsService` custom **không đồng nghĩa** đã cung cấp rule `/admin/**` hay cho phép `/public`.
- Có một `WebFilterChainProxy` là chuyện khác với có một `SecurityWebFilterChain`: **proxy** chọn và thực thi **các chain**.
- Spring Security reactive dùng `SecurityWebFilterChain` và `ServerHttpSecurity`. Các tên `SecurityFilterChain` và `HttpSecurity` là API Servlet, không thay thế trực tiếp được trong WebFlux.

### 3.1. Những lớp auto-configuration đáng biết

Theo tài liệu Spring Boot 4.x:

- `ReactiveWebSecurityAutoConfiguration` hỗ trợ bật cấu hình Spring Security cho web reactive. Nó gắn với các điều kiện classpath và loại ứng dụng; tài liệu API nói rằng phần kích hoạt tự động sẽ nhường quyền nếu ứng dụng tự cấu hình bean `WebFilterChainProxy`.
- `ReactiveUserDetailsServiceAutoConfiguration` có thể cung cấp `ReactiveUserDetailsService` in-memory mặc định và user `user` với mật khẩu phát sinh phục vụ phát triển. Nó kiểm tra sự tồn tại của những bean liên quan đến authentication, ví dụ `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, `ReactiveAuthenticationManagerResolver` và `ReactiveJwtDecoder`, cùng các điều kiện khác.
- Khi thêm Spring Boot Actuator, `ReactiveManagementWebSecurityAutoConfiguration` có điều kiện thiếu `SecurityWebFilterChain` và `WebFilterChainProxy`; nó có thể nhường quyền cho chain do ứng dụng tạo, nên bạn cần tự xét quyền cho actuator endpoint.

**Đọc đúng mức độ:** không nên kết luận toàn bộ auto-configuration chỉ từ một annotation hoặc một điều kiện. Nhiều lớp config có điều kiện lồng nhau, liên quan đến classpath, web application type, bean definitions và property.

### 3.2. Một bảng trạng thái hữu ích

Giả định dự án là **WebFlux reactive**, có Spring Security starter và không có cấu hình nâng cao khác:

| Bạn khai báo | Rule HTTP nào được dùng? | Nguồn user mặc định của Boot? |
| --- | --- | --- |
| Không tự khai báo security bean | Chính sách mặc định yêu cầu xác thực | Thường có user `user` và password sinh ra |
| Chỉ khai báo `SecurityWebFilterChain` | Rule bạn khai báo áp dụng theo matcher | **Vẫn có thể tồn tại** vì chưa thay nguồn authentication |
| Chỉ khai báo `MapReactiveUserDetailsService` | Chính sách HTTP mặc định vẫn áp dụng | **Back off** đối với nguồn user mặc định; dùng user bạn cung cấp |
| Khai báo cả chain và `ReactiveUserDetailsService` | Rule bạn khai báo | User bạn cung cấp |
| Khai báo `ReactiveAuthenticationManager` custom | Các chain vẫn phải được cấu hình phù hợp | Cấu hình user mặc định thường back off theo điều kiện authentication |
| Tự khai báo `WebFilterChainProxy` | Phụ thuộc cách proxy được xây dựng | Không tự tắt `ReactiveUserDetailsService` vì đó là quyết định khác |

Bảng nêu hành vi thông thường. Nếu project có OAuth2 Client, Resource Server, SAML, cấu hình security library khác hoặc property đặc biệt, kết quả phải được xác nhận bằng **Conditions Evaluation Report** của chính ứng dụng.

## 4. Những điều kiện thường dẫn tới auto-config back off

### 4.1. @ConditionalOnMissingBean: kiểm tra sự vắng mặt của bean

Ví dụ ứng dụng khai báo:

~~~java
@Bean
MapReactiveUserDetailsService applicationUsers() {
    UserDetails user = User.withUsername("learner")
            .password("{noop}learner123")
            .roles("USER")
            .build();
    return new MapReactiveUserDetailsService(user);
}
~~~

Đây là **method cần đặt trong `@Configuration` hoặc `@SpringBootApplication`, có các import Spring Security phù hợp**, không phải chương trình độc lập. `MapReactiveUserDetailsService` triển khai `ReactiveUserDetailsService`, nên điều kiện “chưa có bean `ReactiveUserDetailsService`” sẽ không còn thỏa mãn. Boot không cần tạo user in-memory mặc định nữa.

Điểm dễ sai: nếu không thấy log “Using generated security password” sau khi thêm bean này, đó **không tự chứng minh** Spring Security đã bị tắt; có thể chỉ là **nguồn user mặc định** đã được thay bằng nguồn bạn định nghĩa.

### 4.2. @ConditionalOnClass: dependency làm thay đổi điều kiện

Khi thêm dependency OAuth2 Client, OAuth2 Resource Server hoặc SAML2 Service Provider, nguồn xác thực mặc định có thể back off theo chính sách của Spring Boot. Đây không phải “xung đột bean” theo nghĩa trùng tên. Với JWT resource server, Spring Security có thể cần `ReactiveJwtDecoder` cùng các cấu hình issuer/JWK phù hợp; đừng mặc định HTTP Basic còn user ngẫu nhiên để login như trước.

Một dependency nằm trong pom nhưng **không có trong runtimeClasspath** cũng không thỏa mãn điều kiện classpath. Ngược lại, các starter có thể đưa class vào transitively làm điều kiện đổi kết quả. Hãy đọc `mvn dependency:tree` hoặc `gradlew dependencies`.

### 4.3. @ConditionalOnWebApplication: Servlet hay reactive?

Một ứng dụng gắn `spring-boot-starter-webflux` chưa chắc đang chạy ở chế độ reactive nếu còn thêm MVC starter và Boot chọn servlet web application type. Khi đó, các cấu hình có điều kiện `REACTIVE` sẽ không được áp dụng như kỳ vọng. Kiểm tra classpath, loại ApplicationContext và web application type trước khi tạo thêm bean bảo mật “để chữa 404/401”.

Không cố sửa bằng cách thêm song song `SecurityFilterChain` và `SecurityWebFilterChain` khi chưa xác định stack đang được sử dụng.

### 4.4. @ConditionalOnProperty: property không phải chìa khóa vạn năng

Một số auto-configuration có điều kiện theo property. Nhưng không thể suy ra rằng đặt một property tên tùy ý như `spring.security.enabled=false` sẽ tắt an toàn mọi cấu hình bảo mật. Hãy tra **property được tài liệu của đúng phiên bản công bố** và đọc Conditions Report; với Spring Security, một custom security chain thường là cách rõ ràng hơn để thiết lập policy HTTP.

### 4.5. Thứ tự bean definition và classpath

Các điều kiện có thể bị ảnh hưởng bởi:

- Bean khai báo trong module nội bộ nhưng được quét bằng `@ComponentScan`.
- Bean đến từ thư viện thứ ba có `@AutoConfiguration`.
- Một class `@Configuration` bị `@Import` nhiều lần hoặc một bean cùng tên được khai báo ở hai cấu hình.
- `@Primary`, `@Qualifier`, `@Order` được dùng ở các nơi khác nhau nhưng không mang cùng ý nghĩa.
- Các bean bị thay đổi do test slice, `@Profile`, `@ConditionalOnProperty` hoặc profile môi trường.

Vì vậy, xem cấu hình cuối cùng từ ApplicationContext đáng tin hơn việc chỉ nhìn một file Java.

## 5. Phân biệt các loại xung đột bean

### 5.1. Hai bean trùng tên: định nghĩa đè nhau

Ví dụ **cấu hình sai để nhận diện**:

~~~java
@Configuration
class FirstSecurityConfig {
    @Bean("securityPolicy")
    String policyA() {
        return "A";
    }
}

@Configuration
class SecondSecurityConfig {
    @Bean("securityPolicy")
    String policyB() {
        return "B";
    }
}
~~~

Đoạn này thiếu import và class khởi động, chỉ để minh họa. Cùng bean name `securityPolicy` được đăng ký hai lần. Spring Boot mặc định đặt `spring.main.allow-bean-definition-overriding=false`; với hai bean definitions cạnh tranh tên, quá trình đăng ký có thể ném `BeanDefinitionOverrideException`. Một số tình huống cấu hình Java có quy tắc đặc biệt về override, nên hãy đọc exception thực tế thay vì đoán từ hai tên method.

**Cách xử lý:** xác định bean nào có quyền sở hữu cấu hình, loại khai báo trùng hoặc đổi tên nếu **thật sự cần cả hai**. Không bật `spring.main.allow-bean-definition-overriding=true` chỉ để “cho app chạy”: điều đó có thể giấu nhầm lẫn về bean nào cuối cùng có hiệu lực.

### 5.2. Nhiều bean cùng type: không biết inject bean nào

Một service yêu cầu chính xác một `SomeInterface`, nhưng context có hai implementation mà không có lựa chọn rõ ràng, có thể gặp `NoUniqueBeanDefinitionException` hoặc lỗi dependency injection liên quan.

Để chọn bean **tại một injection point**, có thể dùng `@Qualifier("beanName")` hoặc `@Primary` khi đúng ngữ nghĩa. Ví dụ minh họa ngắn:

~~~java
@Service
class ReportService {
    private final ReportPolicy policy;

    ReportService(@Qualifier("strictPolicy") ReportPolicy policy) {
        this.policy = policy;
    }
}
~~~

Đây là **đoạn code minh họa**, giả định `ReportPolicy` và bean tên `strictPolicy` đã được định nghĩa. Nó không đại diện cho việc chọn security chain khi nhận HTTP request.

**Đặc biệt:** việc có **nhiều bean `SecurityWebFilterChain` không tự động là lỗi**. Spring Security hỗ trợ nhiều chain để bảo vệ nhóm URL khác nhau. Khi đó cần `@Order` và `securityMatcher(...)` thích hợp. `@Primary` không thay thế cơ chế chọn security chain theo request.

### 5.3. Back off: không phải exception

Khi điều kiện `@ConditionalOnMissingBean` không đạt, Boot thường chỉ ghi “negative match” trong Conditions Report, **không ném exception**. Ứng dụng có thể khởi động bình thường, nhưng giờ đã chạy theo cấu hình custom. Nếu custom chain quên một URL hoặc mất rule phân quyền actuator, ứng dụng có thể thay đổi hành vi bảo mật mà không có lỗi startup.

### 5.4. Có bean nhưng sai web stack

Bean `SecurityFilterChain` của Servlet không thể thay thế `SecurityWebFilterChain` của WebFlux. Bean cấu hình “tồn tại” về mặt ApplicationContext nhưng không có nghĩa request reactive đang đi qua nó. Chọn đúng package và loại web application.

## 6. Ví dụ thực hành Java 17+: custom chain và custom user

Ví dụ sau thể hiện hai quyết định độc lập: **tự thiết lập policy HTTP** và **tự cung cấp user service**, đồng thời giúp so sánh kết quả khi bỏ từng bean.

### 6.1. Tạo project

Dùng [Spring Initializr](https://start.spring.io/) chọn Maven, Java 17+, Spring Boot **4.1.2** (hoặc bản patch ổn định tương thích đang được hỗ trợ), group `com.example`, artifact `reactive-beans-demo`. Thêm **Spring Reactive Web** và **Spring Security**.

File `pom.xml` hoàn chỉnh tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-beans-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Để Maven/BOM của Boot quản lý Spring Security, Spring Framework và Reactor, không thêm `<version>` riêng cho từng module. Với Spring Boot 3.5.x, hãy dùng đúng parent/BOM nhánh 3.5 tương ứng và xác minh các API trên bản đang sử dụng.

### 6.2. Mã Java hoàn chỉnh

Tạo file `src/main/java/com/example/reactivebeans/ReactiveBeansDemoApplication.java`:

~~~java
package com.example.reactivebeans;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveBeansDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveBeansDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .pathMatchers("/profile").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService applicationUsers() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learner123")
                .roles("USER")
                .build();
        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("ADMIN")
                .build();
        return new MapReactiveUserDetailsService(learner, admin);
    }

    @RestController
    static class ExampleController {

        @GetMapping("/public")
        Mono<String> publicEndpoint() {
            return Mono.just("PUBLIC_OK");
        }

        @GetMapping("/profile")
        Mono<String> profile() {
            return ReactiveSecurityContextHolder.getContext()
                    .map(SecurityContext::getAuthentication)
                    .map(Authentication::getName)
                    .map(name -> "PROFILE:" + name);
        }

        @GetMapping("/admin")
        Mono<String> adminEndpoint() {
            return Mono.just("ADMIN_OK");
        }
    }
}
~~~

**Vì sao mã này có ý nghĩa đối với back off?**

1. `@SpringBootApplication` bật auto-configuration, dùng đúng reactive web stack.
2. `applicationSecurity()` cung cấp **`SecurityWebFilterChain`**: bạn xác định rule truy cập và HTTP Basic. Ứng dụng không còn dựa vào chính sách URL mặc định cho các matcher liên quan.
3. `applicationUsers()` cung cấp **`MapReactiveUserDetailsService`**, là một `ReactiveUserDetailsService`: Boot không tạo nguồn user in-memory mặc định nữa khi điều kiện thiếu bean không còn thỏa mãn.
4. Không cần tự tạo `WebFilterChainProxy`. Boot và Spring Security vẫn quản lý hạ tầng filter cần thiết.
5. Không cần `@EnableWebFluxSecurity` trong ứng dụng Spring Boot WebFlux thông thường vì Boot có thể tự kích hoạt. Nếu dùng cấu hình Spring Security bên ngoài Boot hoặc cấu hình hạ tầng thủ công, yêu cầu có thể khác.
6. `"{noop}"` chỉ để học trên máy local. Trong production phải lưu password bằng encoder phù hợp, dùng HTTPS và không hard-code credentials.
7. Controller `profile()` dùng Reactor Context để lấy authentication, thay vì `SecurityContextHolder` kiểu ThreadLocal.

### 6.3. Chạy project và quan sát kết quả

Nếu project có Maven wrapper do Spring Initializr tạo:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Trên Windows, thay bằng `.\mvnw.cmd clean package` và `.\mvnw.cmd spring-boot:run`. Nếu không có wrapper, sử dụng Maven đã cài: `mvn clean package` và `mvn spring-boot:run`.

Với server trên `http://localhost:8080`, ở terminal khác chạy:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:learner123 http://localhost:8080/profile
curl -i -u learner:learner123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/not-found
~~~

Kết quả mong đợi:

| Request | HTTP status | Nội dung đáng chú ý | Lý do |
| --- | --- | --- | --- |
| `/public`, anonymous | **200** | `PUBLIC_OK` | `permitAll` |
| `/profile`, anonymous | **401** | Tùy cấu hình HTTP Basic | Cần xác thực |
| `/profile`, learner | **200** | `PROFILE:learner` | Có user từ `applicationUsers()` |
| `/admin`, learner | **403** | Tùy cấu hình | Thiếu `ROLE_ADMIN` |
| `/admin`, admin | **200** | `ADMIN_OK` | Đủ quyền |
| `/not-found`, admin | **403** | Tùy cấu hình | `denyAll` chặn trước khi tìm handler |

Hai request thành công có body dạng văn bản chính xác như bảng trong ví dụ. Header, response body của 401/403 và cách content negotiation có thể khác nhau tùy version. Các lệnh GET không cần điều chỉnh CSRF; việc thêm HTTP POST/PUT/DELETE yêu cầu xét token CSRF theo mô hình xác thực.

### 6.4. Hai thử nghiệm nhỏ để nhìn rõ back off

Thực hiện trong **bản sao project thực hành**, mỗi lần chỉ thay một bean rồi build/chạy lại.

**Thử nghiệm A — bỏ riêng method `applicationUsers()`.** Giữ `applicationSecurity()`. Khi không có nguồn xác thực tùy chỉnh khác, Boot có thể tạo lại user `user` và mật khẩu ngẫu nhiên phục vụ phát triển. Nhưng các rule `/public`, `/profile`, `/admin` vẫn do custom chain quyết định. Credential `learner:learner123` không còn tồn tại.

**Thử nghiệm B — khôi phục `applicationUsers()`, bỏ riêng method `applicationSecurity()`.** Boot và Spring Security dùng chính sách bảo mật web mặc định cho ứng dụng. User `learner` và `admin` vẫn được cung cấp vì bean `MapReactiveUserDetailsService` vẫn còn. `/public` không còn được `permitAll` bởi custom policy, nên anonymous thường không truy cập được. Hành vi authentication challenge/redirect phụ thuộc `Accept` header và cơ chế mặc định.

**Kết luận từ hai thử nghiệm:** thay **nguồn user** và thay **rule URL** là hai quyết định độc lập. Chỉ xem việc log password biến mất hoặc một endpoint đổi status là chưa đủ để nói rằng “auto-configuration đã tắt hết”.

## 7. Nhiều SecurityWebFilterChain: khi nào hợp lệ và khi nào có rủi ro?

Spring Security WebFlux hỗ trợ nhiều `SecurityWebFilterChain`, ví dụ bảo vệ `/api/**` bằng JWT nhưng bảo vệ trang web bằng session/HTTP Basic. Mỗi request được so khớp với các chain theo **thứ tự**; chain phù hợp có ưu tiên cao được dùng.

Ví dụ **class cấu hình thay thế** cho method `applicationSecurity()` ở phần 6 (không thêm cả hai cùng lúc):

~~~java
package com.example.reactivebeans;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration(proxyBeanMethods = false)
public class MultiChainConfiguration {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher("/api/**"))
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
~~~

Tên file là `src/main/java/com/example/reactivebeans/MultiChainConfiguration.java`. Thay thế `applicationSecurity()` ở lớp chính bằng class này, **giữ `applicationUsers()`** nếu muốn xác thực bằng user của ví dụ. Các endpoint `/profile` và `/admin` sẽ bị fallback `denyAll` chặn ở cấu hình mới; điều đó là **chủ ý minh họa**, không phải cấu hình bảo vệ các endpoint của bài trước. Muốn cho chúng hoạt động phải định nghĩa rule thích hợp trước `denyAll`.

Bài học ở đây:

- Hai bean `SecurityWebFilterChain` với **tên khác nhau** có thể cùng tồn tại: Spring Security dùng `@Order` và `securityMatcher` để chọn chain. Không sửa bằng `@Primary` vì request routing không dùng @Primary để chọn chain.
- Nếu **cả hai chain cùng match mọi URL**, chain ưu tiên cao có thể che phủ chain còn lại.
- Nếu **không có chain nào match** một URL, request có thể nằm ngoài vùng bảo vệ của Spring Security. Nên có fallback chain với policy rõ ràng.
- `@Order` điều khiển thứ tự xem xét chain, còn thứ tự `pathMatchers(...)` bên trong một chain điều khiển quy tắc authorization. Đây là hai cấp khác nhau.
- Spring Security WebFlux dùng `ServerWebExchangeMatcher`. Đừng sao chép `RequestMatcher` dành Servlet mà không đổi sang API reactive.

## 8. Actuator: lỗi bảo mật dễ xuất hiện khi thay chain

Nếu dự án thêm Spring Boot Actuator, ngoài endpoint ứng dụng còn có endpoint vận hành như `/actuator/health`, `/actuator/info`, `/actuator/metrics`, `/actuator/conditions` (khả năng HTTP truy cập phụ thuộc vào exposure, availability và quyền).

Theo tài liệu và API Spring Boot, `ReactiveManagementWebSecurityAutoConfiguration` thường **nhường quyền khi người dùng cung cấp `SecurityWebFilterChain` hoặc `WebFilterChainProxy`**. Khi tự định nghĩa chain, bạn phải xác định chính sách actuator cần thiết. Không suy ra các rule actuator “tự động được giữ nguyên” sau khi thay chain.

Gợi ý cấu hình khi thực sự có starter Actuator: dùng `EndpointRequest` dành reactive để match endpoint quản trị theo id, ví dụ:

~~~java
import org.springframework.boot.security.autoconfigure.web.reactive.EndpointRequest;

// Bên trong authorizeExchange:
.matchers(EndpointRequest.to("health")).permitAll()
.matchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
.anyExchange().authenticated()
~~~

Đây là **đoạn cấu hình bổ sung**, không phải file Java chạy độc lập. Đặt các matcher theo thứ tự cụ thể trước rộng; cần các import tương ứng và thêm `spring-boot-starter-actuator`. Ngoài HTTP authorization, vẫn phải cấu hình endpoint nào được expose, giới hạn truy cập qua mạng và xem xét port management riêng. Không tự expose `conditions`, `env` hoặc dữ liệu nhạy cảm trên mạng công khai.

## 9. Chẩn đoán: Conditions Evaluation Report là nguồn đáng tin

### 9.1. Xem báo cáo điều kiện với --debug

Spring Boot hỗ trợ hiển thị báo cáo điều kiện của auto-configuration. Trong dự án Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Trên Windows dùng `.\mvnw.cmd spring-boot:run -Dspring-boot.run.arguments=--debug`, hoặc khi chạy JAR:

~~~bash
java -jar target/reactive-beans-demo-0.0.1-SNAPSHOT.jar --debug
~~~

Báo cáo thường có các nhóm như **Positive matches** (điều kiện đạt), **Negative matches** (không đạt), **Exclusions** và **Unconditional classes**, tùy phiên bản/log format. Tìm:

- `ReactiveWebSecurityAutoConfiguration`
- `ReactiveUserDetailsServiceAutoConfiguration`
- `ReactiveManagementWebSecurityAutoConfiguration` nếu dùng actuator
- Điều kiện `OnBeanCondition`, `OnClassCondition`, `OnWebApplicationCondition` và thông tin bean hoặc class làm điều kiện thay đổi.

Chỉ đọc phần báo cáo ứng dụng của mình sau startup; đừng kết luận từ một ảnh log của project khác. Bật debug trong môi trường dev hoặc test và xử lý log theo chính sách bảo mật dữ liệu.

### 9.2. Đọc tín hiệu từ lỗi startup

| Lỗi/tín hiệu | Câu hỏi phải trả lời | Hướng xử lý |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Có hai bean cùng tên? đến từ class nào? | Loại hoặc đổi tên definition ngoài ý muốn |
| `NoUniqueBeanDefinitionException` | Ai đang inject một bean nhưng có nhiều ứng viên type đó? | `@Qualifier`/`@Primary` đúng nơi; nếu là security chain thì xem cơ chế chain matching |
| `NoSuchBeanDefinitionException` | Bean mong đợi không được tạo do điều kiện, profile hay thiếu starter? | Đọc Conditions Report, classpath và bean definitions |
| Không thấy generated password | Có `ReactiveUserDetailsService` hoặc authentication manager/JWT decoder custom? | Xác minh nguồn authentication; không kết luận security đã tắt |
| `/public` trả 401 sau khi thêm chain | Rule `permitAll` có trong chain được chọn không? | Kiểm tra `securityMatcher`, `@Order` và matcher trong `authorizeExchange` |
| Endpoint admin/actuator đổi kết quả | Management security auto-config đã back off? | Tự xác định chính sách actuator trên chain |
| Có cả MVC và WebFlux starters | ApplicationContext thực sự là servlet hay reactive? | Chọn stack rõ ràng và dùng đúng API bảo mật |
| 401/403 không như dự kiến | Lỗi authentication, authorization hay CSRF/filter khác? | Test từng request, kiểm tra authorities và filter chain |

**Cảnh báo về phương pháp:** một tên exception gợi ý hướng điều tra, không phải bằng chứng duy nhất. Đọc nguyên stack trace, bean name và các condition liên quan. Nếu thay đổi classpath hoặc profile, chạy lại báo cáo vì kết quả được tính cho context hiện tại.

### 9.3. Khi có Spring Boot Actuator

Trong môi trường phát triển, có thể dùng endpoint `conditions` của Actuator nếu phiên bản hỗ trợ và endpoint được expose, có quyền truy cập. Nó cho biết điều kiện auto-configuration match hay không match. Hãy bảo vệ endpoint đó bằng chính sách security rõ ràng, chỉ cho môi trường hoặc tài khoản có thẩm quyền truy cập; việc thêm starter không mặc định expose tất cả endpoint.

### 9.4. Đọc dependency graph

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Đối với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
~~~

Trên Windows thay `./mvnw` và `./gradlew` bằng các wrapper tương ứng `.\mvnw.cmd`, `.\gradlew.bat`. Các lệnh giúp xác nhận có đúng các module Spring Security reactive, WebFlux, OAuth2, các BOM và phiên bản đã resolve. Một `spring-security-oauth2-resource-server` xuất hiện transitively có thể làm điều kiện khác kết quả so với project chỉ có starter security cơ bản.

## 10. Khi nào dùng @Qualifier, @Primary, @Order hay @ConditionalOnMissingBean?

| Công cụ | Giải quyết vấn đề gì? | Khi nào không nên dùng? |
| --- | --- | --- |
| `@Qualifier` | Chọn bean cụ thể tại injection point khi nhiều bean cùng type | Không dùng để định tuyến HTTP request tới `SecurityWebFilterChain` |
| `@Primary` | Đặt lựa chọn ưu tiên khi inject bean theo type | Không thay thứ tự chọn chain của Spring Security |
| `@Order` | Xếp thứ tự collection/filter/chain theo cơ chế tương ứng | Không giải quyết trùng **bean name** |
| `@ConditionalOnMissingBean` | Cho phép một auto-config bean nhường quyền khi ứng dụng đã cung cấp bean phù hợp | Không coi là “vá lỗi duplicate” cho mọi cấu hình thủ công |
| `@ConditionalOnProperty` | Cho phép bật/tắt cấu hình **đã khai báo điều kiện** bằng property chính xác | Không invent property không được hỗ trợ |
| `@Profile` | Chỉ đăng ký bean ở profile tương ứng | Không đảm bảo hai cấu hình cùng profile không xung đột |
| `@SpringBootApplication(exclude=...)` | Loại bỏ một auto-configuration class khi có lý do và phạm vi xác định | Không dùng để “tắt hết security” khi chỉ cần sửa rule |
| `@EnableWebFluxSecurity` | Bật hỗ trợ cấu hình Spring Security WebFlux khi cần | Không tạo thêm vô điều kiện nếu Boot đã lo hạ tầng |

**Ưu tiên thiết kế:** chỉ có một nơi sở hữu các bean “hệ thống” quan trọng; tách các security chain theo mục đích rõ ràng; tạo bean nguồn authentication bằng một cách được kiểm soát. Khi nâng cấp Spring Boot/Security, chạy lại integration tests và Conditions Report.

## 11. Bài tập tình huống

### Tình huống A — “Tôi thêm custom SecurityWebFilterChain, vì sao vẫn có user mặc định?”

Vì `SecurityWebFilterChain` quyết định **HTTP rules**, không phải một implementation của `ReactiveUserDetailsService` hay `ReactiveAuthenticationManager`. Hãy định nghĩa nguồn user/authentication phù hợp nếu muốn thay thông tin đăng nhập mặc định. Kiểm tra Conditions Report trước khi kết luận.

### Tình huống B — “Tôi thêm MapReactiveUserDetailsService, vì sao /public vẫn bị yêu cầu đăng nhập?”

Vì nguồn user custom chỉ thay **authentication data**; policy mặc định có thể vẫn yêu cầu xác thực mọi request. Hãy khai báo `SecurityWebFilterChain` có `pathMatchers("/public").permitAll()` và rule catchall có chủ đích.

### Tình huống C — “Hai SecurityWebFilterChain có phải lỗi không?”

Không. Nhiều chain là tính năng bình thường của WebFlux Security. Kiểm tra `@Order` và `securityMatcher`, cùng fallback chain, để đảm bảo mọi route cần thiết đều được bảo vệ. Nếu hai @Bean method có **cùng tên** thì lại là vấn đề bean definition khác.

### Tình huống D — “Tôi thêm OAuth2 Resource Server và mật khẩu mặc định biến mất.”

Các module authentication đặc thù có thể làm điều kiện tạo user mặc định không còn đạt. Kiểm tra classpath, `ReactiveJwtDecoder`, các config OAuth2 và điều kiện của `ReactiveUserDetailsServiceAutoConfiguration`. Thiết lập cơ chế auth phù hợp thay vì cố bật user mặc định bằng cách thêm bean ngẫu nhiên.

### Tình huống E — “Ứng dụng khởi động, nhưng /actuator/** mất rule cũ.”

Một custom `SecurityWebFilterChain` có thể làm management security auto-configuration nhường quyền. Kiểm tra exposure của actuator, `EndpointRequest` và rule cụ thể trên chain; tạo test cho các endpoint quản trị thay vì chỉ test URL ứng dụng.

### Tình huống F — “Đặt allow-bean-definition-overriding=true là xong?”

Nó chỉ cho phép một số hình thức bean name overriding; không đảm bảo đúng security chain hoặc policy, và có thể che lấp nguồn cấu hình sai. Hãy sửa bean ownership, tên và điều kiện thực tế.

## 12. Checklist trước khi đưa vào môi trường chạy

1. Dự án đang thực sự chạy **Reactive WebFlux**, sử dụng `ServerHttpSecurity` và `SecurityWebFilterChain`.
2. Có chính sách HTTP rõ ràng, gồm route công khai, route yêu cầu role và rule cuối; nếu có nhiều chain thì thứ tự và matcher không bỏ sót URL.
3. Có **nguồn authentication** mong muốn, không dựa vào user/password ngẫu nhiên của Boot cho production.
4. Không có bean name trùng ngoài ý muốn, và không có injection ambiguity không được giải quyết.
5. Các property/profiles/dependency tạo điều kiện auto-config được xác nhận bằng Conditions Report.
6. Nếu có Actuator, xác định rõ exposure, management port và authorization cho từng endpoint.
7. Test lại anonymous, user hợp lệ, user không đủ quyền, request sai path/method và các flow CSRF/OAuth2/JWT được dùng.
8. Không dùng `{noop}` hoặc credential hard-code khi triển khai thật; không bật bean overriding để che cấu hình không rõ nguồn.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Có bean `SecurityWebFilterChain` custom nhưng không có `ReactiveUserDetailsService` custom. User mặc định có nhất thiết biến mất?

**Đáp án:** Không. Cấu hình user mặc định có điều kiện riêng và có thể vẫn được tạo nếu các điều kiện khác thỏa mãn.

**Câu 2.** Vì sao `@Primary` không phải cách ưu tiên một security chain cho `/api/**`?

**Đáp án:** `@Primary` ưu tiên một ứng viên khi inject bean, còn WebFlux Security chọn chain theo `@Order` và `securityMatcher` của từng request.

**Câu 3.** Conditions Report ghi `ReactiveUserDetailsServiceAutoConfiguration` không match do đã có bean tương ứng. Đó có phải lỗi startup?

**Đáp án:** Không nhất thiết. Đây có thể là hành vi back off có chủ đích. Chỉ coi là lỗi khi bean custom hoặc hành vi auth thực tế không đáp ứng yêu cầu.

**Câu 4.** Vì sao cùng một cấu hình có thể chạy WebFlux trên project A nhưng không tác dụng trên project B?

**Đáp án:** Khác classpath, web application type, profile, bean definitions hoặc conditions; phải xác minh context đang chạy.

**Câu 5.** Thêm chain custom rồi actuator endpoint không còn được bảo vệ như trước, cần xem gì?

**Đáp án:** Auto-config bảo mật actuator đã back off hay chưa, matcher của chain, `EndpointRequest`, exposure/port và integration tests.

## 14. Tài liệu chính thức

- [Spring Boot — Spring Security / WebFlux Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Auto-configuration và Conditions Report](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Creating your own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ReactiveWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/web/reactive/ReactiveWebSecurityAutoConfiguration.html)
- [Spring Boot API — ReactiveUserDetailsServiceAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/ReactiveUserDetailsServiceAutoConfiguration.html)
- [Spring Boot API — ReactiveManagementWebSecurityAutoConfiguration](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/ReactiveManagementWebSecurityAutoConfiguration.html)
- [Spring Boot — Actuator Endpoints và Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Security — WebFlux Security và Multiple Chains](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
