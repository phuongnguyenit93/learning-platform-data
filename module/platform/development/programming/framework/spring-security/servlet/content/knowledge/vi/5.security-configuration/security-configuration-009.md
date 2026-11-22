# ObjectPostProcessor và lựa chọn mở rộng ở mức thành phần trong Spring Security Servlet

## Mục tiêu học tập

Trong Spring Security Servlet, HttpSecurity tạo nên một SecurityFilterChain từ nhiều thành phần: các bộ lọc, đối tượng xác thực, bộ quản lý quyền, session/CSRF handling và các cấu hình phụ trợ. Khi cần điều chỉnh một **đối tượng do quá trình xây dựng security tạo ra**, ObjectPostProcessor là một cơ chế mở rộng ở mức đối tượng/thành phần. Nó khác việc chọn endpoint nào được phép truy cập hay thêm một filter mới vào chuỗi.

Sau bài này, bạn có thể:

- Giải thích ObjectPostProcessor<T> nhận gì, trả về gì và được gọi ở giai đoạn nào.
- Phân biệt việc thay đổi một thành phần được framework tạo ra với cấu hình toàn bộ SecurityFilterChain.
- Hiểu mối liên hệ giữa ObjectPostProcessor, HttpSecurity, AbstractHttpConfigurer/SecurityConfigurer, Spring BeanFactory và dependency injection.
- Chọn giữa các extension point công khai: Customizer/DSL, @Bean, custom AuthenticationProvider/AuthorizationManager, addFilterBefore/addFilterAfter, AbstractHttpConfigurer, ObjectPostProcessor.
- Viết ví dụ Spring Boot Servlet sử dụng postProcess(...) để hoàn thiện một custom filter có dependency được inject, rồi xác minh bằng HTTP response và kiểm thử.
- Nhận biết các nguy cơ can thiệp quá sâu, xử lý sai thứ tự filter hoặc đăng ký filter hai lần.

Phạm vi bài là Spring Boot 3.x, Spring Security 6.x ở **Servlet stack**. Ví dụ sử dụng Java 17+ và chỉ yêu cầu những API được nêu trong từng ví dụ. Không áp dụng máy móc cú pháp Servlet cho WebFlux SecurityWebFilterChain.

## 1. ObjectPostProcessor là gì?

Giao diện cốt lõi của Spring Security nằm ở package org.springframework.security.config.annotation:

~~~java
public interface ObjectPostProcessor<T> {
    <O extends T> O postProcess(O object);
}
~~~

Đây là **chữ ký giao diện rút gọn theo API**, không phải toàn bộ tệp source của thư viện. Trong chương trình, bạn import ObjectPostProcessor từ Spring Security.

ObjectPostProcessor nhận một object đã được tạo và cho phép một bước xử lý bổ sung trước khi object đó được sử dụng. Hàm phải trả về một object có kiểu tương thích với kiểu đã nhận. Cách dùng phổ biến là hoàn thiện/inject/cấu hình object rồi trả về chính nó.

Ví dụ về mục đích:

1. Framework/configurer tạo một filter hoặc thành phần security.
2. Cơ chế post-processing được gọi trên thành phần đó.
3. Post-processor có thể inject dependency, chạy bước khởi tạo hoặc cấu hình một thuộc tính mà extension point hiện tại cho phép.
4. Thành phần sau xử lý được đưa vào cấu hình security và sử dụng về sau.

**Thời điểm post-processing thuộc giai đoạn dựng cấu hình**, thường lúc khởi động và xây SecurityFilterChain bằng http.build(). Đây không phải callback chạy cho từng HTTP request. Một filter đã được post-process có thể được gọi nhiều lần theo request, nhưng bản thân postProcess(...) không mặc nhiên chạy nhiều lần cùng tần suất đó.

Không nên hiểu rằng “mọi object có @Component hoặc mọi Spring bean đều tự đi qua ObjectPostProcessor của Spring Security”. Đây là cơ chế thuộc quá trình build security, được gọi qua các builder/configurer hoặc tại extension point cụ thể. BeanPostProcessor của Spring Framework là khái niệm liên quan nhưng khác phạm vi.

## 2. ObjectPostProcessor nằm ở đâu trong vòng đời cấu hình?

Một đường đi tiêu biểu khi Spring Boot khởi tạo Spring Security Servlet:

~~~text
Spring ApplicationContext
    |
    +-- tạo/cung cấp HttpSecurity và các dependency liên quan
    |
@Bean SecurityFilterChain securityFilterChain(HttpSecurity http)
    |
    +-- áp dụng cấu hình authorizeHttpRequests, formLogin, httpBasic...
    +-- đăng ký các SecurityConfigurer cần thiết
    |
http.build()
    |
    +-- giai đoạn khởi tạo và configure các SecurityConfigurer
    +-- tạo/cấu hình các filter và security object
    +-- gọi ObjectPostProcessor khi builder/configurer yêu cầu
    +-- sắp xếp filter và dựng DefaultSecurityFilterChain
    |
FilterChainProxy sử dụng SecurityFilterChain đã được dựng
    |
HTTP request --> chọn chain --> chạy filter --> controller hoặc trả lỗi
~~~

Sơ đồ mô tả trách nhiệm, không khẳng định tất cả object đều được tạo trong cùng một bước hoặc luôn có một số lần gọi postProcess cố định.

**HttpSecurity** là builder cho một SecurityFilterChain. **AbstractHttpConfigurer** là điểm mở rộng của builder, cho phép đóng gói logic cấu hình. **ObjectPostProcessor** làm việc với một instance cụ thể do quá trình này tạo ra hoặc được đưa vào cấu hình. Spring Security cung cấp hạ tầng để autowire/initialize nhiều security object do chính nó tạo ra; cơ chế mặc định thường gắn với BeanFactory thông qua AutowireBeanFactoryObjectPostProcessor.

Có hai loại thời điểm phải phân biệt:

| Thời điểm | Công việc | Ví dụ |
| --- | --- | --- |
| Khởi tạo Spring context | Tạo bean, inject dependencies, áp dụng BeanPostProcessor cho bean | @Bean AuditLabelProvider |
| Build SecurityFilterChain | Chạy configurer, tạo filter, gọi postProcess cho object phù hợp, sắp xếp chuỗi filter | postProcess(new AuditHeaderFilter()) |
| HTTP request | Filter và AuthorizationManager xử lý request thực tế | doFilterInternal, kiểm tra Authentication |

Một object được tạo bằng new trong custom configurer **không tự trở thành một Spring bean**. Việc chủ động gọi postProcess(...) giúp object đi qua hạ tầng xử lý object của Spring Security; tùy implementation, hạ tầng này có thể dùng BeanFactory để autowire và initialize. Điều đó không đồng nghĩa object tự được đăng ký vào toàn bộ Servlet filter chain.

## 3. Những việc ObjectPostProcessor giải quyết và những việc không nên giao cho nó

### Phù hợp

ObjectPostProcessor hữu ích khi một configurer/framework **đã tạo object**, nhưng bạn cần tác động vào object đó ở điểm xử lý được hỗ trợ. Chẳng hạn:

- Hoàn thiện dependency và lifecycle của filter được tạo bằng new trong một custom SecurityConfigurer.
- Điều chỉnh một thuộc tính trên đối tượng security cụ thể mà builder/configurer chủ động đưa qua post-processing.
- Đưa logic bổ sung vào một extension point dạng post-processor đã được API hiện hành expose và tài liệu hóa.
- Xác minh hoặc ghi nhận thông tin cấu hình của object tại lúc xây chain, với chi phí và dữ liệu log phù hợp.

### Không phải công dụng mặc định

- Không phải cơ chế để chạy sau mọi HTTP request; hãy dùng Filter, HandlerInterceptor hoặc event phù hợp cho logic request.
- Không thay thế authorizeHttpRequests, hasRole/hasAuthority, SecurityContext hay AuthenticationProvider.
- Không tự động sửa tất cả filter hoặc bean trong ứng dụng chỉ vì bạn khai báo một class implements ObjectPostProcessor<T>.
- Không thay thế BeanPostProcessor của Spring Framework để can thiệp vào lifecycle của mọi bean.
- Không phải API để chỉnh sửa an toàn một SecurityFilterChain sau khi ứng dụng đã chạy và đã nhận request.
- Không tự đảm bảo thứ tự các filter. Thứ tự filter vẫn do cấu hình HttpSecurity và addFilterBefore/addFilterAfter/addFilterAt quyết định.

**Nguyên tắc lựa chọn:** dùng API cấu hình công khai ở tầng cao nhất đáp ứng đúng nhu cầu. Chỉ dùng ObjectPostProcessor khi bạn thật sự cần tùy biến/hoàn thiện một instance ở giai đoạn xây security và có extension point hỗ trợ.

## 4. Chọn extension point phù hợp

| Nhu cầu | Phương án thường phù hợp | Vì sao |
| --- | --- | --- |
| Quy định URL nào cần đăng nhập hoặc authority | authorizeHttpRequests, requestMatchers, securityMatcher | Phạm vi endpoint/quyền là ý định cấu hình của chain |
| Bật HTTP Basic, form login, session, CSRF, headers | HttpSecurity DSL/Customizer | Dùng chức năng chính thức, ít phụ thuộc implementation |
| Thay nguồn user/password hoặc AuthenticationProvider | UserDetailsService, AuthenticationProvider, AuthenticationManager khi có yêu cầu | Xử lý logic xác thực ở đúng lớp trách nhiệm |
| Quy tắc quyền động, kiểm tra chính sách riêng | AuthorizationManager / method security | Phân quyền dựa trên request hoặc nghiệp vụ |
| Thêm xử lý request/response thật sự | Servlet Filter, OncePerRequestFilter và http.addFilterBefore/After | Logic thực thi theo request, có vị trí rõ |
| Đóng gói một tập cấu hình dùng lại | AbstractHttpConfigurer và http.with(...) ở Spring Security 6.2+ | Gom các thiết lập tương tác vào cấu hình riêng |
| Hoàn thiện một security object do configurer đang tạo | ObjectPostProcessor / postProcess(...) | Tác động vào instance cụ thể tại lúc build |
| Xử lý mọi bean Spring theo lifecycle chung | BeanPostProcessor / @Bean / dependency injection | Thuộc phạm vi Spring container, không riêng security |

### Thứ tự ưu tiên trong thiết kế

Nếu muốn endpoint /api/private yêu cầu quyền đọc, dùng authorizeHttpRequests trước. Nếu muốn thêm trace ID trong mỗi request, dùng filter. Nếu muốn lấy một bean hỗ trợ vào filter bạn chủ động tạo bằng new trong custom configurer, postProcess(...) có thể là bước cần thiết. Nếu muốn dùng chung một security config ở nhiều chain, đóng gói thành AbstractHttpConfigurer hoặc phương thức cấu hình rõ ràng.

**Không dùng ObjectPostProcessor để lách quy tắc securityMatcher hoặc thay thế authorization của request.** Mỗi SecurityFilterChain vẫn phải được chọn đúng; post-processing không giúp một filter chạy trong chain mà request không hề đi vào.

## 5. Ví dụ đầy đủ: postProcess một custom filter để inject dependency

Ta xây dựng một ứng dụng Spring Boot Servlet tối giản có GET /public/hello. Một custom filter sẽ thêm header X-Demo-Audit: component-extended vào response. Filter cần một dependency là AuditLabelProvider được Spring quản lý.

Điểm học chính nằm ở method configure của AuditConfigurer:

~~~java
AuditHeaderFilter filter = postProcess(new AuditHeaderFilter());
http.addFilterBefore(filter, AuthorizationFilter.class);
~~~

Dòng đầu tiên tạo filter rồi **yêu cầu ObjectPostProcessor mặc định của hạ tầng cấu hình Security xử lý object**, trong đó có autowiring dependency theo cấu hình Spring thông thường. Dòng thứ hai mới đưa filter vào SecurityFilterChain với vị trí rõ ràng. Nếu chỉ tạo bằng new rồi gọi addFilterBefore mà không có cơ chế inject dependency tương ứng, trường @Autowired của instance mới có thể chưa được khởi tạo.

### 5.1. Dependency và cấu trúc project

Ứng dụng dùng Spring Boot 3.2+ cùng Spring Security 6.2+ để có cách gọi http.with(...) trong ví dụ. Trong một project Spring Boot đã có plugin và dependency management phù hợp, cần hai starter sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ví dụ sử dụng Gradle Groovy DSL; nếu module học tập đã khai báo những dependency này thì không cần thêm lặp lại. Không thể biên dịch các file với javac thuần khi classpath chưa có thư viện Spring.

Cấu trúc tệp:

~~~text
src/main/java/dev/example/securityextension/
    SecurityExtensionApplication.java
    AuditLabelProvider.java
    AuditHeaderFilter.java
    AuditConfigurer.java
    SecurityConfig.java
    HelloController.java
src/test/java/dev/example/securityextension/
    SecurityExtensionTest.java
~~~

### 5.2. Entry point Spring Boot

Tệp SecurityExtensionApplication.java:

~~~java
package dev.example.securityextension;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityExtensionApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityExtensionApplication.class, args);
    }
}
~~~

### 5.3. Dependency do Spring quản lý

Tệp AuditLabelProvider.java:

~~~java
package dev.example.securityextension;

import org.springframework.stereotype.Component;

@Component
public class AuditLabelProvider {
    public String getLabel() {
        return "component-extended";
    }
}
~~~

AuditLabelProvider là bean bình thường của ApplicationContext. Ở ví dụ này nó chỉ trả về nhãn cố định để dễ kiểm chứng. Hệ thống thật có thể dùng service/logging hoặc quy tắc audit cụ thể; không đưa mật khẩu, token hay session ID vào header/log.

### 5.4. Filter được tạo bằng new

Tệp AuditHeaderFilter.java:

~~~java
package dev.example.securityextension;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.filter.OncePerRequestFilter;

public class AuditHeaderFilter extends OncePerRequestFilter {

    @Autowired
    private AuditLabelProvider labelProvider;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        response.setHeader("X-Demo-Audit", labelProvider.getLabel());
        chain.doFilter(request, response);
    }
}
~~~

Filter không gắn @Component và không được khai báo @Bean trong ví dụ này. Nó được tạo chủ động qua new AuditHeaderFilter() ở custom configurer rồi đi qua postProcess(...).

Đặc điểm:

- OncePerRequestFilter giúp tránh thực thi lại logic do cùng filter nhiều lần trong một request dispatch phù hợp với contract của nó; hành vi async/error dispatch cần xem riêng nếu ứng dụng có yêu cầu đó.
- Filter phải gọi chain.doFilter(...) để request được tiếp tục. Các filter sau đó vẫn có thể từ chối request.
- X-Demo-Audit là header trình diễn, không phải security header chuẩn và không cung cấp sự bảo vệ thực tế.
- Không dùng audit header để cấp quyền: quyền truy cập thuộc AuthorizationManager và các quy tắc security.

### 5.5. AbstractHttpConfigurer gọi postProcess

Tệp AuditConfigurer.java:

~~~java
package dev.example.securityextension;

import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

public class AuditConfigurer
        extends AbstractHttpConfigurer<AuditConfigurer, HttpSecurity> {

    @Override
    public void configure(HttpSecurity http) {
        AuditHeaderFilter filter = postProcess(new AuditHeaderFilter());
        http.addFilterBefore(filter, AuthorizationFilter.class);
    }
}
~~~

AbstractHttpConfigurer kế thừa khả năng postProcess object trong cơ chế SecurityConfigurer. Việc gọi postProcess(...) ở đây có ý nghĩa **hoàn thiện instance custom filter tại thời điểm xây chain**, trước khi addFilterBefore đặt filter vào đúng vị trí.

Nếu class chỉ cần constructor injection, bạn cũng có thể truyền dependency có sẵn vào constructor của filter thay vì dùng field injection. Đối với custom code do chính mình quản lý, constructor injection thường rõ ràng và dễ unit-test hơn. Ví dụ chọn @Autowired field để người học thấy rõ tác dụng của post-processing đối với object tạo bằng new.

### 5.6. Đưa configurer vào HttpSecurity

Tệp SecurityConfig.java:

~~~java
package dev.example.securityextension;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/hello").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(withDefaults())
                .with(new AuditConfigurer(), withDefaults())
                .build();
    }
}
~~~

Ở đây:

1. authorizeHttpRequests quy định /public/hello công khai, đường dẫn khác phải xác thực.
2. httpBasic bật cơ chế HTTP Basic cho request cần xác thực. Vì ví dụ chỉ thử GET công khai, không cần tạo tài khoản demo.
3. http.with(...) gắn AuditConfigurer. Cú pháp này áp dụng với Spring Security 6.2+; các phiên bản cũ hơn có API apply(...) nhưng có khác biệt deprecation/khả năng hỗ trợ. Khi nâng cấp, nên dùng API hiện hành của phiên bản đang chạy.
4. http.build() kích hoạt vòng đời cấu hình, trong đó AuditConfigurer.configure(...) tạo filter và gọi postProcess(...).
5. AuditHeaderFilter nằm **trước AuthorizationFilter** trong chain do http.addFilterBefore đặt. Nó vẫn có thể chạy với endpoint permitAll vì permitAll là quyết định authorization, không phải yêu cầu bỏ qua mọi filter.

Đây là một chain duy nhất có matcher mặc định bao quát request, không thêm các chain khác vào ví dụ để tránh lỗi ưu tiên không liên quan tới bài học.

### 5.7. Endpoint

Tệp HelloController.java:

~~~java
package dev.example.securityextension;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/public/hello")
    public String hello() {
        return "HELLO";
    }
}
~~~

### 5.8. Chạy và quan sát

Trong thư mục dự án Spring Boot đã cấu hình Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Ở môi trường Windows PowerShell thông thường, dùng ./gradlew.bat bootRun nếu wrapper được lưu dưới tên gradlew.bat. Sau khi ứng dụng khởi động trên cổng 8080 mặc định, thử:

~~~bash
curl -i http://localhost:8080/public/hello
~~~

Kết quả quan trọng cần tìm trong response (bỏ qua các header do container hoặc Spring Boot tự thêm, cũng như thời gian/ngày động):

~~~http
HTTP/1.1 200
X-Demo-Audit: component-extended

HELLO
~~~

HTTP/1.1 200 và nhãn header/body ở trên là phần **minh họa kỳ vọng** của endpoint, không khẳng định đây là toàn bộ response byte-for-byte của mọi container. Nếu chỉ xem body bằng curl ở môi trường không có alias khác:

~~~bash
curl -s http://localhost:8080/public/hello
~~~

Body chính xác là HELLO, không có newline do controller tạo thêm.

Tại sao header xuất hiện? Vì filter có AuditLabelProvider được inject sau postProcess(...) và được thêm vào SecurityFilterChain; request /public/hello đi qua filter trước khi tới controller. Khi kiểm thử một chain cụ thể, đừng suy ra rằng header này sẽ xuất hiện ở các chain khác nếu ứng dụng có nhiều SecurityFilterChain.

**Không chạy HTTP Basic có credential thật qua HTTP ngoài localhost.** Với môi trường có mạng, luôn dùng HTTPS, và kiểm soát header/log chứa thông tin nhạy cảm.

### 5.9. Kiểm thử tự động

Thêm tệp SecurityExtensionTest.java vào đường dẫn src/test/java/dev/example/securityextension/:

~~~java
package dev.example.securityextension;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExtensionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointUsesPostProcessedFilter() throws Exception {
        mvc.perform(get("/public/hello"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Demo-Audit", "component-extended"))
                .andExpect(content().string("HELLO"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test kiểm chứng hành vi có thể quan sát được: request công khai vẫn đi qua filter custom và dependency của filter đã sẵn sàng. Nếu bỏ postProcess(new AuditHeaderFilter()) rồi thay bằng một instance tạo bằng new mà không tự truyền/inject AuditLabelProvider, test có thể thất bại do dependency null. Không chủ động đưa cấu hình thiếu injection đó lên môi trường thật.

Lưu ý: testcase này xác minh **hành vi request cuối cùng**, không đếm số lần framework gọi postProcess hoặc chứng minh mọi filter đều đã được xử lý bằng cùng callback. Muốn kiểm tra post-processing của đối tượng nào, dùng cấu hình/inspection tại build time hoặc kiểm thử đơn vị dành riêng cho component đó.

## 6. Nếu chỉ muốn custom filter, có cần ObjectPostProcessor không?

Không phải lúc nào cũng cần. Nếu bạn sở hữu filter và đã có dependency, constructor injection hoặc tạo filter thành bean phù hợp cũng là lựa chọn tốt.

Ví dụ ý tưởng constructor injection (đoạn trích, không phải toàn bộ lớp):

~~~java
public AuditHeaderFilter(AuditLabelProvider labelProvider) {
    this.labelProvider = labelProvider;
}
~~~

Khi xây configurer, có thể đưa AuditLabelProvider sẵn có vào constructor thay vì phụ thuộc vào field autowiring qua ObjectPostProcessor. Cách đó làm dependency hiển thị rõ trong constructor và thường dễ test. Khi code của framework tự xây một thành phần mà bạn không trực tiếp gọi constructor, post-processing trở nên hữu ích hơn nếu extension point của configurer cho phép.

Nếu tạo filter thành Spring bean và lại đưa bean đó vào Spring Security chain, cần nhớ **Spring Boot có thể tự đăng ký các Filter bean ở Servlet container**. Khi thêm cùng filter vào HttpSecurity, filter có nguy cơ được chạy ở hai tầng. Trong trường hợp muốn filter bean chỉ chạy trong security chain, dùng FilterRegistrationBean và setEnabled(false) để ngăn đăng ký tự động ở Servlet container rồi thêm nó đúng nơi trong HttpSecurity.

Một số filter cần chạy **trước hoặc sau các security filter**; addFilterBefore/addFilterAfter cho vị trí tương đối. ObjectPostProcessor không phải công cụ điều chỉnh thứ tự đó. Một số filter cần áp dụng toàn ứng dụng nhưng không liên quan security thì có thể là Servlet Filter cấp container, không nên ép vào SecurityFilterChain.

## 7. Tùy biến chính thành phần do Spring Security tạo ra

Phần trước minh họa custom configurer tạo object và gọi postProcess(...). Một tình huống khác là framework/configurer tạo sẵn thành phần, bạn muốn thay đổi thuộc tính của nó.

Cần làm rõ ba điều:

1. **Đúng kiểu đối tượng**: ObjectPostProcessor<AuthorizationFilter> chỉ có thể xử lý đối tượng thuộc kiểu AuthorizationFilter theo contract. Nó không tự biến thành processor của BasicAuthenticationFilter hoặc mọi Spring bean.
2. **Đúng thời điểm gắn vào lifecycle**: chỉ tạo một biến processor hoặc chỉ đánh dấu @Component cho class processor **không đủ** để đảm bảo framework áp dụng nó tới đối tượng bạn muốn. Phải đăng ký nó qua extension point được builder/configurer của phiên bản đang dùng hỗ trợ, hoặc gọi postProcess tại vị trí thực sự sở hữu vòng đời object.
3. **Đúng API thành phần**: không chỉnh fields private hoặc dựa vào thứ tự nội bộ chưa được bảo đảm. Khi framework thay thế loại filter hoặc đổi điểm mở rộng giữa các phiên bản, custom processor cũ có thể không còn chạy.

Ví dụ triển khai hợp đồng của processor chuyên biệt (class này chỉ thể hiện callback, **chưa được đăng ký vào bất cứ SecurityFilterChain nào**):

~~~java
package dev.example.securityextension;

import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.config.annotation.ObjectPostProcessor;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

public final class AuthorizationEventsProcessor
        implements ObjectPostProcessor<AuthorizationFilter> {

    private final AuthorizationEventPublisher publisher;

    public AuthorizationEventsProcessor(AuthorizationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public <O extends AuthorizationFilter> O postProcess(O filter) {
        filter.setAuthorizationEventPublisher(publisher);
        return filter;
    }
}
~~~

Mục đích của ví dụ là đọc đúng chữ ký generic: O phải là subtype của AuthorizationFilter, callback đặt publisher rồi trả về chính object đó. Class sử dụng API AuthorizationFilter có thể cần kiểm tra lại khi nâng phiên bản; **không thêm riêng class này vào project rồi cho rằng nó tự động được gọi**. Khi muốn áp dụng lên AuthorizationFilter do configurer tạo, hãy tìm extension point chính thức của đúng phiên bản Spring Security và kiểm tra bằng test rằng callback thực sự chạy.

AuthorizationEventPublisher phục vụ quan sát sự kiện quyết định phân quyền; không phải một nơi để thay thế AuthorizationManager hoặc thay đổi kết quả cấp quyền tùy ý. Ghi log mọi thành công/thất bại trong hệ thống lớn có thể gây nhiều sự kiện và chi phí, nên lựa chọn chính sách quan sát phù hợp.

### Cẩn thận với ví dụ FilterSecurityInterceptor cũ

Nhiều tài liệu dùng ObjectPostProcessor<FilterSecurityInterceptor> cùng authorizeRequests(...) hoặc ExpressionUrlAuthorizationConfigurer. Đó là mô hình authorization cũ. Với authorizeHttpRequests hiện đại, thành phần tiêu biểu là **AuthorizationFilter** và AuthorizationManager. Không sao chép máy móc hook của FilterSecurityInterceptor rồi kỳ vọng nó sửa AuthorizationFilter; hai đối tượng khác kiểu và có cơ chế cấu hình khác nhau.

Khi cần đổi policy quyền, hãy ưu tiên authorizeHttpRequests hoặc một AuthorizationManager riêng. Khi cần audit, ưu tiên event/hook công khai được hỗ trợ. Chỉ sử dụng processor gắn sâu vào thành phần khi API hợp lệ của phiên bản thực sự cung cấp con đường đó.

## 8. Phân biệt ObjectPostProcessor với BeanPostProcessor

Hai tên gần giống nên dễ nhầm.

| Cơ chế | Phạm vi | Ai gọi? | Thời điểm |
| --- | --- | --- | --- |
| ObjectPostProcessor<T> của Spring Security | Object cụ thể trong quá trình build security | Security builder/configurer hoặc code gọi postProcess | Khi cấu hình/lắp ghép security object |
| BeanPostProcessor của Spring Framework | Những bean do Spring container tạo theo bean lifecycle | BeanFactory/ApplicationContext | Quanh thời điểm khởi tạo bean |
| @Bean / @Component | Khai báo object do Spring quản lý | Spring container | Trong quá trình tạo bean |
| Servlet Filter#doFilter | Request/response thực tế | Servlet container/FilterChainProxy | Mỗi request/dispatch phù hợp |

Đối tượng do framework tạo không phải lúc nào cũng là bean trực tiếp của application. Default ObjectPostProcessor có thể sử dụng các chức năng BeanFactory để autowire và initialize một object do Spring Security tạo. Đây là **cầu nối lifecycle** quan trọng, nhưng không làm hai interface ObjectPostProcessor và BeanPostProcessor đồng nhất.

Không nên khai báo một ObjectPostProcessor<Object> toàn cục và cố sửa mọi object theo instanceof nếu một cơ chế chuyên biệt hơn đã đủ. Một processor quá rộng có thể tác động không mong muốn lên nhiều SecurityFilterChain hoặc thay đổi hành vi khi Spring Security cập nhật loại object.

## 9. Mối liên hệ với SecurityFilterChain và nhiều chain

Spring Security Servlet thường có một hoặc nhiều SecurityFilterChain. Một request được FilterChainProxy đưa vào **chain đầu tiên khớp** theo thứ tự ưu tiên. Custom configurer và post-processing của nó chỉ tác động tới chain mà cấu hình được áp dụng theo cách thiết kế.

Ví dụ minh họa phạm vi:

~~~text
@Order(1) /api/** -> chain API (có AuditConfigurer)
@Order(2) mọi request còn lại -> chain Web (không có AuditConfigurer)

GET /api/orders -> API chain -> audit filter
GET /web/home   -> Web chain -> không có audit filter từ API
~~~

Đây là minh họa cấu hình hai chain, không phải danh sách bean của ứng dụng mẫu phần 5. Nếu một configurer được gắn ở chain API thì filter của nó không tự xuất hiện ở chain web. Một processor với phạm vi toàn cục/ngữ cảnh khác lại cần kiểm tra riêng vì có thể tác động nhiều object; không giả định phạm vi chỉ từ tên class.

Để thêm configurer vào nhiều chain, phải có chủ đích và kiểm tra từng SecurityFilterChain. Cần hiểu securityMatcher, @Order, filter order và luật authorizeHttpRequests là những quyết định độc lập với object post-processing.

## 10. Cách kiểm chứng component nào đã được mở rộng

Đánh giá một thay đổi ở mức ObjectPostProcessor qua cả cấu hình và hành vi:

- **Kiểm thử kết quả public API:** /public/hello có HTTP 200, header X-Demo-Audit đúng và body HELLO. Test trong phần 5 có ý nghĩa ở đây.
- **Kiểm tra object/lifecycle khi cần:** dùng log hoặc test quan sát callback postProcess được gọi và trả về object mong đợi, thay vì tự suy đoán từ việc class processor tồn tại.
- **Kiểm tra đúng chain:** đảm bảo request thực tế khớp chain có gắn custom configurer/filter, đặc biệt khi có nhiều securityMatcher.
- **Kiểm tra filter list:** FilterChainProxy.getFilterChains() và SecurityFilterChain.getFilters() cho thấy danh sách filter đã tạo, khác với danh sách Servlet Filter của container.
- **Kiểm tra injection:** dependency trong filter phải có trước khi xử lý request; khi dùng custom processor hãy kiểm tra kiểu và thời điểm lifecycle.
- **Kiểm tra an toàn:** endpoint bảo vệ vẫn đòi authentication/authorization, CSRF/session không vô tình bị tắt, và custom filter không log credential.

Chỉ bật DEBUG/TRACE cho org.springframework.security trong môi trường phát triển khi cần. Log có thể cho biết các filter đang bảo vệ request nhưng thay đổi theo phiên bản; tránh ghi token/session ID/Authorization vào log.

Ví dụ cấu hình log để quan sát trong dev:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Không đọc một dòng log rồi kết luận postProcess(...) đã chạy nếu log chỉ chứng minh filter hiện diện. Kiểm tra trực tiếp object được tạo hoặc test kết quả như header để có bằng chứng tốt hơn.

## 11. Lỗi phổ biến và cách sửa

### Lỗi 1: Nghĩ rằng implements ObjectPostProcessor tự có tác dụng

Một class implements ObjectPostProcessor<T> nhưng không được gắn vào đúng lifecycle chỉ là một object callback chưa được gọi. Hãy tìm chính xác điểm cấu hình/builder tạo object và extension point nơi callback được đăng ký; xác minh bằng test.

### Lỗi 2: Dùng ObjectPostProcessor để điều khiển request

Code cần đọc URL, header, security context mỗi request nên nằm trong Filter/AuthorizationManager đúng trách nhiệm. postProcess(...) thực hiện ở build time, không chứa Request/Response của từng lần gọi và không nên giữ thông tin request trong state singleton.

### Lỗi 3: Nhầm postProcess với toàn bộ cơ chế Spring bean

Tạo new AuditHeaderFilter() rồi đưa thẳng vào chain sẽ không tự bảo đảm @Autowired được xử lý như khi Spring tạo bean. Nếu dùng field injection trên object mới, cần postProcess(...) hoặc một cơ chế injection hợp lệ khác. Với code tự sở hữu, constructor injection giúp hạn chế bất ngờ.

### Lỗi 4: Dùng processor sai kiểu hoặc lỗi generic

ObjectPostProcessor<AuthorizationFilter> không thay thế cho ObjectPostProcessor<FilterSecurityInterceptor>. Giữ đúng generic method <O extends T> O postProcess(O object) và trả về đối tượng tương thích. Dùng raw type/cast tùy tiện làm mất kiểm tra kiểu compile time.

### Lỗi 5: Thêm filter vào sai chain/sai vị trí

ObjectPostProcessor không quyết định FilterChainProxy sẽ chọn chain nào. Kiểm tra securityMatcher và @Order. Cần đặt filter trước/sau filter hiện có thì dùng addFilterBefore/addFilterAfter theo contract; không assume processor sẽ sửa thứ tự.

### Lỗi 6: Đăng ký filter hai lần

Filter được đánh dấu @Component hoặc @Bean rồi đồng thời thêm vào HttpSecurity có thể bị Servlet container đăng ký một lần và SecurityFilterChain sử dụng lần nữa. Phải kiểm tra đăng ký và, nếu cần, dùng FilterRegistrationBean.setEnabled(false) để vô hiệu hóa auto-registration ở tầng Servlet.

### Lỗi 7: Chỉnh sâu object nội bộ khi đã có extension point tốt hơn

Cố sửa field private, dựa vào loại filter cũ hoặc reflection có thể gãy sau upgrade. Ưu tiên DSL/Customizer, AuthenticationProvider, AuthorizationManager, filter hoặc SecurityConfigurer trước. Xác minh API của phiên bản hiện tại khi dùng ObjectPostProcessor.

### Lỗi 8: Quên kiểm tra tác động đến bảo mật

Một custom filter để audit không nên vô tình trả 200 cho request cần quyền, bỏ qua chain.doFilter hoặc nuốt AuthenticationException/AccessDeniedException. Không tắt CSRF vì muốn test nhanh một component. Nếu filter có state, thiết kế thread-safe; filter của Spring Security có thể phục vụ đồng thời nhiều request.

### Lỗi 9: Giữ state request bên trong post-processor

postProcess(...) phục vụ cấu hình object, có thể được dùng khi Spring khởi động và tạo nhiều chain. Không dùng trường mutable ở post-processor như kho lưu phiên/Authentication của tất cả request. Dữ liệu request cần được quản lý qua SecurityContext, request scope hoặc cơ chế phù hợp.

### Lỗi 10: Không tính đến thay đổi giữa Spring Security versions

Cú pháp http.with(...) áp dụng trong Spring Security 6.2+; nhiều tài liệu cũ dùng http.apply(...). Legacy authorizeRequests/FilterSecurityInterceptor không tương đương hoàn toàn với authorizeHttpRequests/AuthorizationFilter. Đọc API của đúng phiên bản đang chạy và có integration test trước khi nâng cấp.

## 12. Checklist lựa chọn và tự kiểm tra

Trước khi đưa một phần mở rộng mới vào Spring Security Servlet, trả lời:

1. Nhu cầu này chạy ở thời điểm khởi tạo cấu hình hay mỗi HTTP request?
2. Ai là owner của object cần sửa: mình tạo, Spring container tạo, hay framework/configurer tạo?
3. Có DSL/Customizer/@Bean/AuthenticationProvider/AuthorizationManager hỗ trợ trực tiếp không?
4. Nếu dùng ObjectPostProcessor, callback được đăng ký/gọi tại vị trí cụ thể nào, với kiểu generic nào?
5. Object được trả về đã có dependency đúng, không bị đăng ký thêm lần hai và được đưa vào đúng SecurityFilterChain chưa?
6. Khi có nhiều chain, request quan trọng có khớp đúng chain và đúng thứ tự filter không?
7. Bài kiểm thử nào chứng minh hành vi an toàn thay vì chỉ chứng minh class đã được tạo?

Câu hỏi luyện tập:

- ObjectPostProcessor<T> khác BeanPostProcessor ở phạm vi và thời điểm gọi như thế nào?
- Trong AuditConfigurer.configure(...), vì sao gọi postProcess(new AuditHeaderFilter()) trước khi addFilterBefore?
- Nếu filter là @Component đồng thời nằm trong SecurityFilterChain, rủi ro thực thi trùng là gì?
- Vì sao tạo class AuthorizationEventsProcessor chưa tự làm thay đổi AuthorizationFilter?
- Nếu muốn thay đổi quyền truy cập GET /admin, bạn nên dùng ObjectPostProcessor hay authorizeHttpRequests?
- Tại sao filter của chain /api/** không chạy cho request /web/home?
- Nếu chuyển từ authorizeRequests cũ sang authorizeHttpRequests, vì sao processor nhắm FilterSecurityInterceptor có thể không còn phù hợp?

**Ghi nhớ:** ObjectPostProcessor là cơ chế mở rộng **từng security object tại lúc build cấu hình**. Hãy xác định đúng owner, kiểu object và điểm gọi postProcess; dùng các API cấu hình ở mức cao hơn khi phù hợp; và luôn chứng minh kết quả qua SecurityFilterChain cùng request thật.