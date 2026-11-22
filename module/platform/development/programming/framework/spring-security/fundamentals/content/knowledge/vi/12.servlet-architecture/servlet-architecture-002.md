# DelegatingFilterProxy nối Servlet Container với Spring bean

## 1. Vì sao Spring Security cần một lớp cầu nối?

Một HTTP request đi vào ứng dụng Spring Boot/Spring MVC qua **Servlet Container** như Tomcat, Jetty hoặc Undertow (tùy cấu hình), trước khi được DispatcherServlet chuyển vào Controller. Ở phía Servlet Container, các Servlet Filter được đăng ký và gọi theo **Servlet API**. Trong khi đó, nhiều thành phần của Spring Security được cấu hình dưới dạng **Spring bean** bên trong ApplicationContext.

Đây là hai mô hình quản lý khác nhau:

- **Servlet Container** hiểu đăng ký Filter, URL mapping, dispatcher types, thứ tự filter và các callback Servlet lifecycle.
- **Spring ApplicationContext** hiểu bean name, dependency injection, cấu hình, lifecycle của bean, profile và các component framework.
- **Spring Security** cần chạy một chuỗi các filter bảo mật đã được Spring cấu hình trước khi request đi tới Controller.

**DelegatingFilterProxy** giải quyết khoảng cách này. Nó là một Servlet Filter do **Spring Framework** cung cấp, được Servlet Container gọi như filter bình thường, nhưng khi hoạt động nó **tìm một Spring bean triển khai Filter rồi chuyển lời gọi doFilter(...) đến bean đó**.

Với Spring Security Servlet, bean đích thường có tên **springSecurityFilterChain**, có kiểu thực tế là **FilterChainProxy**. FilterChainProxy chọn một **SecurityFilterChain** phù hợp và chạy các security filters của chain đó. Nhờ vậy, Servlet Container chỉ cần biết một cổng vào, còn cách xây dựng và sắp xếp chuỗi bảo mật được Spring quản lý.

**Thông điệp cốt lõi:** DelegatingFilterProxy **không trực tiếp kiểm tra mật khẩu, không tự quyết định ROLE_ADMIN và không phải danh sách security filters**. Nó chủ yếu là **cầu nối** để Servlet Container gọi một bean Filter của Spring.

Bài thuộc nhóm **Kiến trúc Servlet** của module **Spring Security - fundamentals**. Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**, áp dụng namespace **jakarta.servlet**. Cú pháp web.xml minh họa thêm cho hệ Servlet truyền thống.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Vẽ lại đường đi từ Servlet Container, DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain đến DispatcherServlet.
2. Giải thích vì sao Servlet Container không thể tự quản lý toàn bộ Spring Security beans.
3. Hiểu ý nghĩa **springSecurityFilterChain**, **targetBeanName** và việc tìm bean theo tên.
4. Phân biệt lifecycle của Servlet Filter và lifecycle của Spring bean.
5. Giải thích vì sao Spring Boot thường không cần khai báo DelegatingFilterProxy hay web.xml bằng tay.
6. Phân biệt FilterChainProxy với SecurityFilterChain và quy tắc **first matching chain**.
7. Nhận ra filter cấp Servlet Container khác với filter nằm trong chuỗi Spring Security.
8. Chạy một ứng dụng Boot chứng minh hai cấp filter bằng HTTP headers và embedded-server tests.
9. Tránh lỗi filter chạy hai lần khi đăng ký cùng một filter bean ở cả Servlet Container và Spring Security.
10. Debug trường hợp bean không tìm thấy, request đi sai chain, security filter không chạy, thứ tự sai hoặc endpoint vô tình không được bảo vệ.

## 2. Trước hết: Servlet Filter bình thường làm gì?

Servlet API định nghĩa interface **jakarta.servlet.Filter**. Container tạo filter chain cho request, lần lượt gọi các Filter rồi tới Servlet phù hợp. Với Spring MVC, Servlet xử lý chính thường là **DispatcherServlet**.

Hình dung:

~~~text
Browser hoặc API client
        |
        v
Tomcat / Servlet Container
        |
        v
[Container Filter A]
        |
        v
[Container Filter B]
        |
        v
[Servlet: DispatcherServlet]
        |
        v
Spring MVC HandlerMapping
        |
        v
@RestController
~~~

Một filter có quyền:

- Đọc thông tin request và response.
- Bổ sung hoặc thay đổi wrapper request/response.
- Ghi headers bảo mật.
- Từ chối yêu cầu và trả HTTP response ngay.
- Thực hiện logic trước hoặc sau khi các thành phần phía sau xử lý.
- Gọi **chain.doFilter(request, response)** để chuyển quyền cho thành phần kế tiếp.

Ví dụ Servlet Filter tối giản:

~~~java
import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class AuditFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {
        // Việc cần làm trước khi chuyển tiếp.
        chain.doFilter(request, response);
        // Việc cần làm sau khi xử lý downstream hoàn tất.
    }
}
~~~

Đây là **file lớp Java độc lập khi được đặt đúng tên AuditFilter.java trong dự án có Jakarta Servlet API**; nó chỉ minh họa contract Filter, chưa được đăng ký và không phải toàn bộ ứng dụng có server.

**Nếu filter không gọi chain.doFilter**, các filter/Servlet phía sau không được gọi theo nhánh đó. Một authentication filter có thể làm vậy khi credential sai; response 401 có thể được tạo **trước khi Controller chạy**. Vì thế thứ tự filter là một phần quan trọng của kiến trúc bảo mật.

### 2.1. Lifecycle của Servlet Filter

Servlet Container quản lý việc đăng ký và lifecycle **init(FilterConfig)**, **doFilter(...)**, **destroy()** của filter container. Filter có thể được tạo qua web.xml, ServletContext registration hoặc cơ chế auto-registration của Spring Boot.

Container không mặc nhiên biết một Spring bean cần inject DataSource, UserDetailsService, AuthenticationManager hay AuthenticationProvider như thế nào. Nó chỉ thấy một class Filter được đăng ký.

### 2.2. Lifecycle của Spring bean

ApplicationContext tạo và nối dependencies cho Spring beans, gọi các callback lifecycle liên quan và giải phóng bean khi context đóng. Spring Security thường cần nhiều bean phối hợp: SecurityFilterChain, PasswordEncoder, UserDetailsService, AuthenticationManager, AuthenticationProvider, SecurityContextRepository...

Nếu phải tạo toàn bộ các filter trực tiếp qua Servlet Container, việc cấu hình dependency injection và bảo mật nhiều chuỗi trở nên phức tạp. DelegatingFilterProxy cho phép Filter container **ủy quyền** vào Spring context.

## 3. Sơ đồ nối hai thế giới

~~~text
HTTP request
   |
   v
+-----------------------------------------------+
| Servlet Container (Tomcat)                    |
|                                               |
|   Servlet FilterChain                         |
|      |                                        |
|      +-- Other container filters              |
|      |                                        |
|      +-- DelegatingFilterProxy                |
|                  |                            |
+------------------|----------------------------+
                   |
                   | find bean by name
                   | "springSecurityFilterChain"
                   v
+------------------------------------------------+
| Spring ApplicationContext                      |
|                                                |
| Bean "springSecurityFilterChain"               |
|        |                                       |
|        v                                       |
|   FilterChainProxy  (implements Filter)        |
|        |                                       |
|        +-- SecurityFilterChain /api/**         |
|        |      [security filter 1, ...]         |
|        |                                       |
|        +-- SecurityFilterChain fallback        |
|               [security filter A, ...]         |
+------------------------------------------------+
                   |
                   | return to original chain
                   v
           DispatcherServlet
                   |
                   v
             @RestController
~~~

**Một số lớp xuất hiện cùng tên “filter” nhưng thuộc các cấp khác nhau**. Đây là lý do cần phân biệt chúng trước khi debug.

| Đối tượng | Nằm ở đâu? | Ai gọi/chọn? | Trách nhiệm chính |
| --- | --- | --- | --- |
| Servlet Filter | Container's filter chain | Servlet Container | Xử lý request/response trong Servlet lifecycle |
| DelegatingFilterProxy | Container's filter chain | Servlet Container | Tìm Spring bean Filter và chuyển lời gọi |
| FilterChainProxy | Spring ApplicationContext | DelegatingFilterProxy | Quản lý/chọn security filter chain và áp dụng các bước hạ tầng Spring Security |
| SecurityFilterChain | Danh sách filter + matcher | FilterChainProxy | Mô tả filters bảo mật cho request phù hợp |
| Security filter | Trong SecurityFilterChain | FilterChainProxy's virtual chain | CSRF, authentication, authorization, headers, session... |
| DispatcherServlet | Servlet của Spring MVC | Container filter chain | Chọn Controller/Handler sau khi qua các filters |

**FilterChainProxy là một Filter, còn SecurityFilterChain không phải một Servlet Filter đăng ký trực tiếp cho Tomcat.** Bean SecurityFilterChain được Spring Security dùng để cấu hình danh sách filter; nó không phải object mà DelegatingFilterProxy trực tiếp gọi theo tên.

### 3.1. Bản chất của việc "delegate"

Pseudo-code rút gọn:

~~~java
public void doFilter(ServletRequest req,
        ServletResponse res,
        FilterChain chain) throws IOException, ServletException {

    Filter springFilter = lookupSpringBean("springSecurityFilterChain");
    springFilter.doFilter(req, res, chain);
}
~~~

Đây chỉ là **pseudo-code giải thích**, không phải source chính xác của DelegatingFilterProxy. Implementation thật còn quản lý ApplicationContext, lazy lookup, đồng bộ truy xuất bean, lifecycle, cấu hình tên target, exception và việc tái sử dụng delegate.

Điểm đáng nhớ: **delegate.doFilter(...) được gọi với cùng request, response và FilterChain từ Servlet Container**. Khi FilterChainProxy và các filter bảo mật hoàn tất rồi chuyển tiếp, request mới tiếp tục đi qua phần còn lại của container chain/DispatcherServlet nếu không bị chặn.

### 3.2. DelegatingFilterProxy không có một Spring bean mới mỗi request

Nó có thể **tìm bean theo cách trì hoãn (lazy lookup)** khi context sẵn sàng và giữ tham chiếu delegate đã tìm được. Không tạo một instance FilterChainProxy mới cho mỗi HTTP request và không dựng lại toàn bộ Spring Security bean graph ở mỗi lần gọi.

Việc trì hoãn lookup hữu ích bởi Servlet Container có thể cần đăng ký filter trước khi quá trình khởi tạo Spring ApplicationContext hoàn tất. Proxy đứng ở biên container–Spring, còn object thật được tra khi có thể truy cập context.

## 4. springSecurityFilterChain: tên bean đích chứ không phải tên Controller

Trong cách tích hợp Servlet truyền thống, tên **springSecurityFilterChain** thường được dùng cho cả:

- **filter-name** của DelegatingFilterProxy trong Servlet Container.
- **tên Spring bean** của FilterChainProxy do Spring Security dựng.

Tại sao hai tên cần khớp? Mặc định DelegatingFilterProxy dùng **filter-name** để xác định bean mà nó sẽ delegate tới, trừ khi **targetBeanName** được cấu hình riêng.

Ví dụ nếu container đăng ký một DelegatingFilterProxy tên **springSecurityFilterChain**, proxy có thể tìm Spring bean cùng tên. Bean đó phải implement **jakarta.servlet.Filter** (với Spring Framework 6/Boot 3).

Nếu đổi tên filter thành **mySecurityBridge** mà không chỉ định target bean name, proxy có thể tìm bean mySecurityBridge thay vì springSecurityFilterChain và không tìm thấy. Không sửa bằng cách đổi tên SecurityFilterChain method tùy tiện; cần hiểu sự khác biệt giữa **bean bridge** và **bean cấu hình từng security chain**.

### 4.1. targetBeanName là gì?

DelegatingFilterProxy có cấu hình targetBeanName để chọn tên Spring bean cần gọi, độc lập với tên đăng ký container. Trong web.xml, có thể chỉ định init-param **targetBeanName**.

Ví dụ cấu hình truyền thống:

~~~xml
<filter>
    <filter-name>mySecurityBridge</filter-name>
    <filter-class>
        org.springframework.web.filter.DelegatingFilterProxy
    </filter-class>
    <init-param>
        <param-name>targetBeanName</param-name>
        <param-value>springSecurityFilterChain</param-value>
    </init-param>
</filter>

<filter-mapping>
    <filter-name>mySecurityBridge</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

Đây là **fragment cần nằm trong web.xml hợp lệ của một ứng dụng Servlet truyền thống**, không phải file web.xml hoàn chỉnh. Trong Boot executable jar thông thường, **không cần viết fragment này**.

Nếu filter-name đã là springSecurityFilterChain, thường không cần init-param targetBeanName. Việc đổi tên này chỉ hữu ích khi có cấu hình đặc biệt hoặc một ứng dụng legacy đang dùng filter-name riêng.

### 4.2. Sơ đồ sai tên bean

~~~text
Servlet filter-name = myProxy
targetBeanName      = không chỉ định
Spring Filter bean  = springSecurityFilterChain

DelegatingFilterProxy cố tìm "myProxy"
      |
      v
Không có bean Filter tên "myProxy"
      |
      v
Lỗi cấu hình/khởi tạo hoặc lần xử lý request
~~~

**Cần xem thông báo lỗi thực tế** vì thời điểm lookup bean tùy cách khởi tạo và trạng thái context. Không khẳng định lỗi luôn xảy ra tại startup hoặc luôn là HTTP 500; bean lookup có thể được thực hiện khi có request.

### 4.3. DelegatingFilterProxy không chỉ dành cho Spring Security

Bất kỳ **Spring bean implements Filter** nào cũng có thể là target. Spring Security sử dụng cơ chế này như cổng vào phổ biến, nhưng DelegatingFilterProxy là class của **Spring Framework**, không phải filter “đặc biệt chỉ nhận mật khẩu”.

Ví dụ một bean Filter khác có thể được container delegate với tên riêng; tuy nhiên không nên tự tạo thêm nhiều DelegatingFilterProxy cho từng security filter của Spring Security nếu FilterChainProxy đã quản lý các filter đó.

## 5. Lifecycle: ai gọi init và destroy?

Đây là khác biệt dễ bị bỏ sót khi viết custom Servlet Filter.

| Công việc | Đối tượng được quản lý |
| --- | --- |
| Container khởi tạo Filter đã đăng ký | DelegatingFilterProxy |
| Spring tạo bean FilterChainProxy | Spring ApplicationContext |
| Spring nối dependencies cho filters/beans | ApplicationContext |
| DelegatingFilterProxy tìm target và gọi doFilter | Khi có request |
| Spring đóng context/bean lifecycle | ApplicationContext |
| Container dọn filter proxy | Servlet Container |

Theo Javadoc của **DelegatingFilterProxy**, thuộc tính **targetFilterLifecycle** mặc định là **false**. Nghĩa là **init/destroy của Servlet Filter mặc định không được delegate tới target Spring bean theo cách container gọi proxy**. Cách dùng điển hình để Spring ApplicationContext quản lý lifecycle của bean target.

Nếu đặt targetFilterLifecycle=true, proxy có thể chuyển Servlet Filter init/destroy cho target theo lifecycle container; đó là tùy chọn cho trường hợp rất cụ thể và cần tránh xung đột với lifecycle đã được Spring quản lý.

~~~xml
<init-param>
    <param-name>targetFilterLifecycle</param-name>
    <param-value>true</param-value>
</init-param>
~~~

Đây là **fragment cấu hình legacy minh họa**, không phải cấu hình khuyến nghị mặc định. Đừng bật chỉ vì một custom filter có @PostConstruct hoặc muốn log vòng đời; Spring đã có bean lifecycle riêng.

### 5.1. FilterChainProxy không gọi init/destroy cho mọi security filter

Spring Security **không dựa vào Servlet Container để gọi từng filter nội bộ của SecurityFilterChain**. FilterChainProxy cũng không gọi standard Filter lifecycle methods cho từng filter trong danh sách theo cách container khởi tạo chúng. Hãy sử dụng Spring bean initialization hoặc cơ chế lifecycle phù hợp khi tạo custom security filters.

Không cấu hình mỗi security filter như một Servlet Filter độc lập trong web.xml để “đảm bảo init được gọi”. Làm vậy có thể phá thứ tự, mất lợi ích HttpFirewall và tạo filter chạy ngoài security chain.

### 5.2. Khi nào dùng Filter bean và khi nào dùng new Filter?

Trong Spring Boot, một custom Filter được khai báo @Component hoặc @Bean có thể bị **auto-register với Servlet Container**. Nếu bạn cũng chèn nó vào SecurityFilterChain bằng http.addFilterBefore/After, cùng filter có thể chạy ở **hai cấp**.

Vì vậy khi chỉ muốn một filter nội bộ của Spring Security, thường có thể tạo bằng new CustomFilter(...) khi cấu hình HttpSecurity, hoặc nếu cần bean injection thì khai báo bean và **tắt container registration** bằng FilterRegistrationBean disabled. Phần 11 có ví dụ.

## 6. Boot 3 khác gì ứng dụng Servlet truyền thống?

### 6.1. Trong ứng dụng Boot executable jar

Với **spring-boot-starter-security** và cấu hình Servlet Security hợp lệ, Spring Boot thường tự đăng ký một DelegatingFilterProxy vào embedded Servlet Container thông qua cơ chế **DelegatingFilterProxyRegistrationBean** hướng tới bean **springSecurityFilterChain**.

Bạn chỉ cần khai báo SecurityFilterChain bean cho policy của ứng dụng:

~~~java
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **snippet trong class cấu hình có imports** và bean HttpSecurity. Bạn không cần tự viết **new DelegatingFilterProxy()**, không cần web.xml và thường không cần khai báo FilterRegistrationBean cho Spring Security.

**Spring Boot SecurityAutoConfiguration, WebSecurityConfiguration và SecurityFilterAutoConfiguration** có trách nhiệm khác nhau trong quá trình tạo beans và đăng ký filter. Đừng nhầm “tôi khai báo SecurityFilterChain bean” với “tôi tự đăng ký servlet filter”. Boot nối hai phần hạ tầng theo auto-configuration.

### 6.2. Chuyện gì xảy ra khi thêm SecurityFilterChain bean?

Spring Boot thường back off khỏi default web security policy khi bạn định nghĩa SecurityFilterChain của riêng mình, nhưng **cơ chế cầu nối Servlet Container → springSecurityFilterChain vẫn cần hoạt động**.

Không nên thêm thủ công một DelegatingFilterProxy thứ hai chỉ vì đã viết bean SecurityFilterChain mới. Làm vậy có thể khiến security processing chạy lặp lại hoặc tạo thứ tự khó hiểu.

### 6.3. Legacy WAR và web.xml

Trong một ứng dụng WAR cấu hình Servlet cổ điển, có thể thấy:

~~~xml
<filter>
    <filter-name>springSecurityFilterChain</filter-name>
    <filter-class>
        org.springframework.web.filter.DelegatingFilterProxy
    </filter-class>
</filter>
<filter-mapping>
    <filter-name>springSecurityFilterChain</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

Đây là **đoạn web.xml**, không phải Spring bean definition. Nó yêu cầu Servlet Container gọi proxy cho request khớp /*. Spring ApplicationContext phải có Filter bean tên springSecurityFilterChain.

Ứng dụng Servlet hiện đại có thể dùng **AbstractSecurityWebApplicationInitializer** hoặc cách đăng ký chương trình thay vì web.xml. Nhưng **không vừa cấu hình web.xml vừa auto-register cùng proxy lần nữa** nếu không cố ý thiết kế/tính toán toàn bộ registration.

### 6.4. Kiểm tra đúng bean

Trong Spring context bạn có thể dùng:

~~~java
Object bean = applicationContext.getBean(
    "springSecurityFilterChain");

System.out.println(bean.getClass().getName());
~~~

Đây là snippet trong một method đã có ApplicationContext. Trong cấu hình tiêu chuẩn, bạn kỳ vọng một implementation của **FilterChainProxy**. Tuy nhiên, kiểm tra Spring bean **không tự chứng minh Servlet Container đã đăng ký DelegatingFilterProxy**; cần runtime container inspection hoặc integration test qua HTTP thật.

### 6.5. Điều khiển thứ tự đăng ký trong Boot

Spring Boot có các tham số cấu hình thứ tự registration filter, gồm **spring.security.filter.order** trong các phiên bản hỗ trợ. Nó điều chỉnh **vị trí filter bảo mật tại cấp Servlet Container**, không phải thứ tự từng security filter nội bộ.

Muốn thay thứ tự nội bộ, dùng HttpSecurity DSL như addFilterBefore/After/At với quyết định có lý do. Đừng dùng filter order container để sửa vấn đề “BasicAuthenticationFilter chạy trước AuthorizationFilter” vì thứ tự ấy nằm **bên trong FilterChainProxy**.

## 7. FilterChainProxy và SecurityFilterChain: hai tầng tiếp theo

DelegatingFilterProxy chỉ đưa request vào Spring bean. Tầng còn lại là trách nhiệm của **FilterChainProxy**.

FilterChainProxy chứa danh sách các **SecurityFilterChain**. Mỗi SecurityFilterChain có RequestMatcher và danh sách Filter; FilterChainProxy xét theo thứ tự và chọn **chain đầu tiên khớp request**.

~~~text
DelegatingFilterProxy
       |
       v
FilterChainProxy
       |
       +-- Chain 1: securityMatcher("/api/**") ?
       |         YES -> chạy filters của Chain 1, DỪNG xét chain
       |
       +-- Chain 2: securityMatcher("/admin/**") ?
       |         YES -> chạy filters của Chain 2
       |
       +-- Chain 3: fallback (any request) ?
                 YES -> chạy filters fallback
~~~

**Không cộng dồn filters của tất cả các SecurityFilterChain khớp.** Chỉ chain đầu tiên được chọn trong cấu hình thông thường. Vì thế thứ tự **@Order** và securityMatcher quan trọng khi có nhiều chain.

### 7.1. securityMatcher khác requestMatchers trong authorizeHttpRequests

- **securityMatcher(...)** xác định **phạm vi của cả SecurityFilterChain**.
- **requestMatchers(...)** trong authorizeHttpRequests xác định **authorization rule** cho những request đã đi vào chain đó.

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
~~~

Đây là **snippet gồm hai bean trong class cấu hình**, chưa phải một project hoàn chỉnh. Spring Security cung cấp HttpSecurity builder cho mỗi chain. Chain api được ưu tiên với /api/**; fallback denyAll cho request khác.

Nếu không có chain nào khớp, **Spring Security không bảo vệ request bằng security filters**. Servlet Container vẫn có thể chạy DelegatingFilterProxy và FilterChainProxy, nhưng không có SecurityFilterChain áp dụng. Đây là khác biệt lớn giữa “Spring Security có trong classpath” và “tất cả URL đều được bảo vệ”.

### 7.2. permitAll khác bỏ qua FilterChainProxy

Một rule **permitAll()** cho phép request về mặt authorization, nhưng nó **không có nghĩa request bỏ qua toàn bộ security filters**. FilterChainProxy vẫn có thể chạy headers, CSRF, security context, authentication filter và các thành phần khác theo cấu hình.

Ngược lại, bỏ qua bảo mật qua **WebSecurityCustomizer.ignoring(...)** hoặc thiếu chain phù hợp có thể khiến request không nhận các cơ chế bảo vệ do Spring Security cung cấp. Với endpoint public thông thường, dùng **permitAll** và chain fallback phù hợp thường có lợi hơn.

### 7.3. FilterChainProxy còn cung cấp gì ngoài chọn chain?

Theo tài liệu chính thức, FilterChainProxy là cổng vào trung tâm và có thể:

- Áp dụng **HttpFirewall** để kiểm soát/bình thường hóa các chi tiết request phục vụ matching.
- Quản lý request/response đi qua virtual filter chain.
- Giữ thứ tự security filters nhất quán.
- Phối hợp với các filter quản lý vòng đời SecurityContext.
- Là điểm hữu ích để debug Spring Security.

**Không cho từng security filter tự đăng ký Servlet Container** để thay FilterChainProxy. Làm vậy mất khả năng chọn chain linh hoạt, có thể bỏ qua HttpFirewall hoặc thứ tự bảo mật cần thiết.

## 8. So sánh Servlet Filter và Spring Security filter

| Đặc điểm | Filter cấp Servlet Container | Filter trong SecurityFilterChain |
| --- | --- | --- |
| Đăng ký | web.xml, ServletContext hoặc FilterRegistrationBean | HttpSecurity, SecurityFilterChain |
| Ai chọn filter? | Servlet Container theo URL/dispatcher mapping | FilterChainProxy theo RequestMatcher |
| Thứ tự | Registration order ở Container | Thứ tự Security Filter Chain |
| Dependency injection | Có thể qua Spring Boot bean, nhưng phải quản lý registration | Thường do Spring Security hoặc cấu hình HttpSecurity cung cấp |
| Chạy khi request không khớp chain bảo mật? | Có thể vẫn chạy theo container mapping | Không chạy nếu không có SecurityFilterChain tương ứng |
| Lifecycle init/destroy | Container chịu trách nhiệm Filter registration | Không mặc nhiên được container gọi cho từng security filter |
| Ví dụ | Logging/tracing Servlet Filter | CsrfFilter, BasicAuthenticationFilter, AuthorizationFilter |
| Cách debug | Container registration, order, dispatcher type | Spring Security DEBUG, matcher, filter list |

### 8.1. Một request thực tế đi qua hai loại filter

Giả sử có một **ContainerProbeFilter** và một **SecurityProbeFilter**:

~~~text
GET /private
    |
    v
ContainerProbeFilter (container-level)
    |  thêm X-Lab-Container-Filter: hit
    v
DelegatingFilterProxy (container-level)
    |
    v
FilterChainProxy (Spring bean)
    |
    v
SecurityProbeFilter (security-chain-level)
    |  thêm X-Lab-Security-Filter: hit
    v
BasicAuthenticationFilter
    |
    v
AuthorizationFilter
    |
    +-- đủ credentials/quyền -> Controller, 200
    |
    +-- không đủ credentials -> 401
~~~

Sơ đồ chỉ nêu các phần cần thiết của bài; giữa chúng còn nhiều filter. Trong code, SecurityProbeFilter sẽ được đặt trước BasicAuthenticationFilter; với request nào đã bị một filter trước đó chặn, header probe có thể không xuất hiện. Vì vậy **đừng dùng một header minh họa làm bằng chứng tuyệt đối mọi request đều qua mọi filter**.

### 8.2. Tại sao không dùng một custom filter tự xử lý mọi thứ?

Servlet Filter có thể làm rất nhiều việc, nhưng Spring Security có cấu trúc chuẩn cho credential verification, SecurityContext, CSRF, exception handling và authorization. Tự tạo một filter duy nhất so Basic header bằng cách String.equals và cấp role từ request dễ tạo lỗ hổng.

Hãy dùng authentication mechanisms có sẵn trừ khi có yêu cầu đặc biệt đã được đánh giá, rồi thêm custom filter đúng vị trí nếu thật sự cần.

## 9. Ứng dụng Spring Boot 3.x có thể chạy và quan sát hai cấp filter

Để thấy rõ proxy bridge bằng **dấu hiệu từ HTTP response**, ta tạo:

1. **ContainerProbeFilter** đăng ký bằng FilterRegistrationBean, ở cấp Servlet Container.
2. **SecurityProbeFilter** chỉ được thêm bằng HttpSecurity.addFilterBefore(...), ở bên trong SecurityFilterChain.
3. **SecurityFilterChain** yêu cầu authentication cho /private và role ADMIN cho /admin.
4. **Controller** trả những chuỗi rất ngắn, không xuất Authentication object.
5. **Integration test qua embedded server** xác minh HTTP response có cả hai probe headers.

**Mục đích:** thấy Servlet Filter và Security Filter khác nơi đăng ký, không phải tự dựng DelegatingFilterProxy; Boot tự tạo bridge giữa container và bean springSecurityFilterChain.

### 9.1. Tạo dự án và dependencies

Tạo project Java 17+, Spring Boot 3.x, Gradle Groovy DSL và Gradle Wrapper qua Spring Initializr với các starter Spring Web, Spring Security và Spring Boot Starter Test.

Trong phần dependencies của **build.gradle**:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là **phần dependencies của project có Spring Boot plugin, Java toolchain và dependency management**, không phải toàn bộ file build.gradle chạy độc lập.

### 9.2. File Java hoàn chỉnh

Tạo file **src/main/java/com/example/filterbridge/FilterBridgeApplication.java**:

~~~java
package com.example.filterbridge;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterBridgeApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterBridgeApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("local-learn-123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("local-admin-123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    FilterRegistrationBean<ContainerProbeFilter> containerProbe() {
        FilterRegistrationBean<ContainerProbeFilter> registration =
            new FilterRegistrationBean<>(new ContainerProbeFilter());

        registration.setName("containerProbe");
        registration.addUrlPatterns("/*");

        // Cố ý đặt trước Spring Security ở cấp container
        // trong cấu hình Boot mặc định của thí nghiệm.
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);

        return registration;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            // new: không tạo một Filter bean để Boot auto-register.
            .addFilterBefore(
                new SecurityProbeFilter(),
                BasicAuthenticationFilter.class
            )
            .build();
    }
}

// Do Servlet Container gọi theo FilterRegistrationBean.
final class ContainerProbeFilter implements Filter {

    @Override
    public void doFilter(ServletRequest request,
            ServletResponse response,
            FilterChain chain) throws IOException, ServletException {

        ((HttpServletResponse) response).setHeader(
            "X-Lab-Container-Filter", "hit");

        chain.doFilter(request, response);
    }
}

// Chỉ FilterChainProxy gọi, sau khi chain đã được chọn.
final class SecurityProbeFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        response.setHeader("X-Lab-Security-Filter", "hit");
        chain.doFilter(request, response);
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

**Tính độc lập:** Đây là **một file Java hoàn chỉnh trong project Boot**; public class FilterBridgeApplication có tên trùng file, các class phụ package-private cùng package. Java 17 và Spring Security 6.x dùng **jakarta.servlet** chứ không dùng javax.servlet. Nếu chép vào Boot 2.x phải xét version/namespace khác, không đổi import tùy tiện.

### 9.3. Giải thích từng thành phần

**ContainerProbeFilter:**

- Implements jakarta.servlet.Filter.
- Được FilterRegistrationBean đăng ký với Servlet Container cho /*.
- Thêm header X-Lab-Container-Filter=hit rồi gọi chain.doFilter.
- Không nằm trong danh sách các Spring Security filters do HttpSecurity tạo.

**SecurityProbeFilter:**

- Extends OncePerRequestFilter.
- Được **new** trong SecurityFilterChain, không phải Spring bean auto-registered ở Servlet Container.
- Đặt **trước BasicAuthenticationFilter** bởi addFilterBefore.
- Thêm X-Lab-Security-Filter=hit rồi gọi filter chain.

**SecurityFilterChain:**

- /public: permitAll, vẫn đi qua security filter chain.
- /private: cần Authentication hợp lệ.
- /admin: cần ROLE_ADMIN.
- httpBasic nhận Authorization header và dùng manager/provider thông thường để kiểm chứng.
- formLogin bị tắt để tránh login page/redirect trong bài.
- Không thêm/đăng ký DelegatingFilterProxy bằng tay.

**UserDetailsService + PasswordEncoder:**

- InMemoryUserDetailsManager chỉ giữ tài khoản local cho demo.
- Password được BCrypt encode trước khi đưa vào user store.
- Đăng nhập thật vẫn đi qua AuthenticationManager/DaoAuthenticationProvider thích hợp.
- Raw password trong demo chỉ dùng trên localhost cô lập; không dùng account/mật khẩu mẫu ở môi trường được deploy.

### 9.4. Vì sao cả hai header có thể xuất hiện trên /public?

Vì **permitAll** không bỏ qua Servlet filters hoặc SecurityFilterChain. Một GET /public bình thường vẫn đi qua:

1. ContainerProbeFilter.
2. DelegatingFilterProxy → bean springSecurityFilterChain.
3. FilterChainProxy và SecurityProbeFilter.
4. Controller /public.

Trong cấu hình ví dụ, hai header:

~~~http
X-Lab-Container-Filter: hit
X-Lab-Security-Filter: hit
~~~

Chúng chỉ là **dấu hiệu phục vụ lab**, không phải headers bảo mật do Spring Security chuẩn yêu cầu. Không dùng chúng như cơ chế authentication/authorization, không giữ trong production nếu không cần.

### 9.5. Chạy thử

Ở thư mục project có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng **.\gradlew.bat bootRun**. Giả sử server ở http://localhost:8080:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner http://localhost:8080/private
curl -i -u learner http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
~~~

Với **curl -u learner** hoặc **curl -u admin** không kèm dấu hai chấm và password ở command line, curl có thể hỏi password qua terminal. Nhập password demo tương ứng theo source khi được hỏi; dùng **curl.exe** trên PowerShell nếu curl là alias.

HTTP Basic sử dụng Base64, **không bảo vệ credential nếu không có TLS**. Trên mạng thật phải dùng HTTPS. Không gửi password thật qua URL, log hoặc shell history.

### 9.6. Kết quả HTTP dự kiến

| Request | HTTP status | Body dự kiến | Ý nghĩa |
| --- | --- | --- | --- |
| GET /public anonymous | **200** | public OK | permitAll, chain vẫn chạy |
| GET /private anonymous | **401** | tùy Basic entry point | Chưa xác thực |
| GET /private learner đúng password | **200** | hello learner | Authentication thành công |
| GET /admin learner đúng password | **403** | tùy handler | Đã xác thực, thiếu ROLE_ADMIN |
| GET /admin admin đúng password | **200** | admin OK | Có ROLE_ADMIN |

Hai header X-Lab-* dự kiến xuất hiện trên những đường đi bình thường đi qua cả hai probe filters. Không khẳng định mọi error dispatch, request bị firewall chặn hoặc exception xảy ra ở filter trước probe cũng sẽ có cả hai header.

Bảng là **kỳ vọng suy ra từ mã**, không phải log đo từ một server đã chạy trong bài viết này. Thứ tự filter container và Spring Security có thể thay đổi khi ứng dụng thêm registration khác; luôn kiểm tra actual runtime.

## 10. Test qua embedded Servlet Container thay vì chỉ MockMvc

MockMvc rất hữu ích khi kiểm thử SecurityFilterChain và Controller, nhưng **không nhất thiết chạy toàn bộ cơ chế đăng ký Servlet Filter của embedded Tomcat** như một HTTP server thật.

Để xác nhận **hai filter cấp khác nhau cùng được thực thi**, dùng integration test có **webEnvironment=RANDOM_PORT**. Spring Boot dựng embedded server trên cổng ngẫu nhiên; TestRestTemplate gửi HTTP thật qua container.

Tạo file **src/test/java/com/example/filterbridge/FilterBridgeApplicationTest.java**:

~~~java
package com.example.filterbridge;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.FilterChainProxy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterBridgeApplicationTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    ApplicationContext context;

    @Test
    void springSecurityFilterChainIsFilterChainProxyBean() {
        assertInstanceOf(FilterChainProxy.class,
            context.getBean("springSecurityFilterChain"));
    }

    @Test
    void realHttpRequestPassesBothFilterLayers() {
        ResponseEntity<String> response =
            rest.getForEntity("/public", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("public OK", response.getBody());

        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Container-Filter"));
        assertEquals("hit", response.getHeaders()
            .getFirst("X-Lab-Security-Filter"));
    }

    @Test
    void authenticationAndAuthorizationRemainCorrect() {
        ResponseEntity<String> anonymous =
            rest.getForEntity("/private", String.class);
        assertEquals(HttpStatus.UNAUTHORIZED,
            anonymous.getStatusCode());

        ResponseEntity<String> learner =
            rest.withBasicAuth("learner", "local-learn-123")
                .getForEntity("/private", String.class);

        assertEquals(HttpStatus.OK, learner.getStatusCode());
        assertEquals("hello learner", learner.getBody());

        ResponseEntity<String> forbidden =
            rest.withBasicAuth("learner", "local-learn-123")
                .getForEntity("/admin", String.class);
        assertEquals(HttpStatus.FORBIDDEN,
            forbidden.getStatusCode());

        ResponseEntity<String> admin =
            rest.withBasicAuth("admin", "local-admin-123")
                .getForEntity("/admin", String.class);
        assertEquals(HttpStatus.OK, admin.getStatusCode());
        assertEquals("admin OK", admin.getBody());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Trên PowerShell: **.\gradlew.bat test**.

### 10.1. Test chứng minh những gì?

- Spring context có bean **springSecurityFilterChain** là FilterChainProxy.
- HTTP request thật qua embedded server nhận header từ **ContainerProbeFilter**.
- Cùng request nhận header từ **SecurityProbeFilter** bên trong security chain.
- /public vẫn chạy cả hai tầng dù permitAll.
- HTTP Basic + hasRole phân biệt 401 thiếu authentication, 403 thiếu role và 200 thành công.

### 10.2. Test chưa chứng minh những gì?

- Chưa chứng minh security chain bảo vệ tất cả URL mới khi thêm nhiều chains; phải test matching riêng.
- Chưa kiểm tra mọi dispatcher type ASYNC/ERROR hoặc các Servlet filters bên thứ ba.
- Chưa kiểm tra proxy/load balancer trong production.
- Chưa kiểm tra sự kiện lifecycle init/destroy của mọi filter.
- Chưa chứng minh không có custom filter nào khác được auto-register hai lần.
- Chưa đánh giá CSRF với POST/PUT/DELETE; demo chỉ gồm endpoint GET.
- Chưa kiểm tra session persistence/logout/MFA/authorization theo resource.

**Không coi test HTTP headers của lab là một bảo đảm bảo mật toàn diện.** Nó chỉ cho thấy đường đi cần quan sát trong cấu hình đã thiết lập.

## 11. Lỗi phổ biến: custom Filter bean bị gọi hai lần

Một lỗi hay xảy ra trong Spring Boot:

1. Developer tạo **@Component MyFilter extends OncePerRequestFilter** hoặc **@Bean MyFilter**.
2. Spring Boot thấy Filter bean và auto-register nó với Servlet Container.
3. Developer cũng dùng **http.addFilterBefore(myFilter, BasicAuthenticationFilter.class)**.
4. Filter có thể bị gọi ở cả cấp Container và trong SecurityFilterChain, thứ tự khác nhau.

Hậu quả có thể gồm:

- Log/audit duplicated, tăng tải hoặc side effects lặp lại.
- Filter chạy trước khi SecurityContext được khôi phục.
- CORS/CSRF/authorization kiểm tra sai thời điểm.
- Header bị ghi đè, response bị commit sớm.
- Debug thấy “filter không chạy” do OncePerRequestFilter nhận diện request already-filtered trong một nhánh, nhưng việc đăng ký vẫn sai.
- Hành vi khác giữa REQUEST và ERROR dispatch.

### 11.1. Cách tránh đơn giản nhất

Nếu filter chỉ dành cho Spring Security, tạo instance trong HttpSecurity thay vì khai báo như một bean được Boot auto-register:

~~~java
http.addFilterBefore(
    new SecurityProbeFilter(),
    BasicAuthenticationFilter.class
);
~~~

Trong ứng dụng demo, SecurityProbeFilter không phải @Component và không có @Bean tương ứng, nên nó **không tự xuất hiện ở container chain**.

### 11.2. Khi filter cần dependency injection như một Spring bean

Bạn có thể tạo bean filter và tạo **FilterRegistrationBean disabled** để Boot không đăng ký lại ở container:

~~~java
@Bean
MySecurityFilter mySecurityFilter(MyService service) {
    return new MySecurityFilter(service);
}

@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {

    FilterRegistrationBean<MySecurityFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}

@Bean
SecurityFilterChain security(HttpSecurity http,
        MySecurityFilter filter) throws Exception {

    http.addFilterBefore(
        filter, BasicAuthenticationFilter.class);

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là **snippet thiết kế** đặt trong @Configuration có imports phù hợp; MySecurityFilter và MyService là hai class ứng dụng phải tự định nghĩa. Không phải một file Java chạy độc lập. Ý nghĩa của disabled registration: filter bean vẫn tồn tại cho dependency injection, nhưng **không tự được Servlet Container đăng ký qua Boot**; HttpSecurity là đường đưa nó vào security chain.

### 11.3. Đừng tự đăng ký BasicAuthenticationFilter ở container

BasicAuthenticationFilter phụ thuộc AuthenticationManager và security context/exception handling; Spring Security DSL đã cung cấp cách bật HTTP Basic đúng vị trí bằng **httpBasic(Customizer.withDefaults())**.

Không lấy BasicAuthenticationFilter ra để @Component hoặc tạo một FilterRegistrationBean container chỉ vì muốn “chạy sớm hơn”. Tương tự với AuthorizationFilter, CsrfFilter và các security filters tiêu chuẩn; hãy cấu hình qua HttpSecurity và theo kiến trúc FilterChainProxy.

### 11.4. Điều gì xảy ra nếu addFilterAt trùng filter DSL?

HttpSecurity có addFilterBefore, addFilterAfter và addFilterAt. Khi thay một filter tại vị trí của filter chuẩn, phải kiểm tra version và thành phần khác đã thêm filter cùng vị trí chưa. Không cấu hình httpBasic(...) rồi tiếp tục thêm một BasicAuthenticationFilter thay thế tùy ý mà không hiểu chain; một số cấu hình có thể bị từ chối hoặc hoạt động không như dự tính.

## 12. Legacy Servlet WAR và Spring Boot: đọc đúng nơi đăng ký

| Mô hình | Cách đăng ký bridge | Đặc điểm |
| --- | --- | --- |
| Servlet WAR với web.xml | filter-name/filter-class DelegatingFilterProxy + mapping | Cần Spring bean target cùng tên hoặc targetBeanName |
| Servlet WAR không XML | AbstractSecurityWebApplicationInitializer hoặc programmatic registration | Cần tránh đăng ký trùng |
| Boot embedded server | Auto-configuration đăng ký DelegatingFilterProxyRegistrationBean | Thường chỉ viết SecurityFilterChain |
| Custom filter container-only | FilterRegistrationBean hoặc @Component Filter | Không mặc nhiên nằm trong SecurityFilterChain |
| Custom filter security-only | HttpSecurity.addFilterBefore/After/At | Không tự đăng ký container lần hai |
| Reactive WebFlux | WebFilterChainProxy/SecurityWebFilterChain và Reactor context | **Không dùng DelegatingFilterProxy Servlet** |

### 12.1. WebFlux không dùng chuỗi Servlet Filter

Nếu ứng dụng chọn Spring WebFlux/reactive stack, kiến trúc security khác: **WebFilter** và SecurityWebFilterChain, không phải Jakarta Servlet Filter. Đừng sao chép DelegatingFilterProxy hoặc FilterRegistrationBean Servlet vào ứng dụng reactive rồi kỳ vọng HttpSecurity sẽ xử lý request.

Bài chỉ nói tới Servlet stack. Với một ứng dụng trộn dependencies Web + WebFlux, cần xác định web application type thực tế trước khi chọn API.

### 12.2. Dispatcher types REQUEST, ERROR và ASYNC

Servlet Filter registration có thể giới hạn theo dispatcher type. Request HTTP đầu tiên thường có dispatcher type REQUEST; một exception có thể dẫn đến ERROR dispatch, hoặc async dispatch có thể xảy ra trong quá trình xử lý bất đồng bộ.

Vì vậy:

- Không mặc định custom filter sẽ chạy trong mọi ERROR/ASYNC dispatch.
- Khi chỉnh registration ở cấp container, kiểm tra dispatcher types phù hợp theo framework version.
- Với OncePerRequestFilter, còn có cơ chế kiểm soát xử lý async/error dispatch; tên “once” không đồng nghĩa “chính xác một lần cho mọi hoạt động của cả HTTP request và mọi dispatch”.
- Với authentication và SecurityContext, phải dùng cơ chế context propagation/clearing phù hợp trong async workload.

Một header chỉ được thêm ở REQUEST dispatch không phải bằng chứng filter sẽ luôn chạy ở ERROR dispatch. Dùng integration test có dispatcher type cần thiết nếu policy phụ thuộc điều đó.

## 13. Debug DelegatingFilterProxy và FilterChainProxy theo từng lớp

Khi request bị 401/403 không mong muốn hoặc lộ endpoint, nên debug theo ranh giới:

~~~text
A. Servlet Container có gọi filter bridge không?
             |
             v
B. DelegatingFilterProxy có tìm đúng bean target không?
             |
             v
C. FilterChainProxy có nhận request và chọn chain đúng không?
             |
             v
D. Trong chain đó, filter cần thiết có mặt/thứ tự đúng không?
             |
             v
E. Authentication filter có nhận đúng credential không?
             |
             v
F. Authorization rule có cho phép request không?
             |
             v
G. Request có tới DispatcherServlet/Controller không?
~~~

### 13.1. Bước A — xác minh container registration

Kiểm tra Boot startup logs, embedded server registration hoặc ServletContext.getFilterRegistrations() trong môi trường test. Đừng chỉ xem Spring bean SecurityFilterChain rồi kết luận Servlet Container đã gọi security bridge.

Nếu ứng dụng WAR có web.xml, kiểm tra filter-mapping /*, tên filter, dispatcher types và thứ tự. Nếu có WebApplicationInitializer cùng web.xml, xác minh không đăng ký trùng.

### 13.2. Bước B — bean target có đúng tên?

Trong Spring context, tên thường là **springSecurityFilterChain**. Kiểm tra bằng ApplicationContext.getBean(...), hoặc xem lỗi lookup delegate của DelegatingFilterProxy. Không tìm bean có thể do context khởi tạo sai, filter-name khác targetBeanName hoặc ApplicationContext không phải nơi chứa bean đó.

Đừng “sửa nhanh” bằng cách tạo Spring bean tên springSecurityFilterChain kiểu khác thay FilterChainProxy; điều đó có thể vô hiệu hóa toàn bộ security architecture.

### 13.3. Bước C — FilterChainProxy chọn chain nào?

Với nhiều chains, kiểm tra **@Order**, **securityMatcher**, RequestMatcher và fallback. Nếu route mới không khớp chain nào, Spring Security có thể không bảo vệ nó. Nếu chain /api/** khớp trước fallback, các rules của fallback không tự áp lên /api/**.

Dùng logs/diagnostics phù hợp và integration tests cho từng route, phương thức GET/POST, request có/không có credential, và status 200/401/403.

### 13.4. Bước D — filter list và thứ tự

Bật logging phù hợp trong môi trường thử có kiểm soát, ví dụ:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
~~~

Đây là **snippet cấu hình logging chỉ để điều tra trên môi trường thử**. Tên logger và mức thông tin cụ thể có thể thay đổi theo phiên bản. Tài liệu Spring Security mô tả khả năng in danh sách filters ở startup khi DEBUG.

Không bật TRACE rộng ở production để log Authorization, Cookie, credentials hoặc request body. Một filter có thể chạy sai vị trí nếu bạn dựa vào đăng ký container thay vì HttpSecurity.

### 13.5. Bước E — authentication

FilterChainProxy đã chạy nhưng request vẫn 401 có thể là behavior đúng: credential thiếu/sai, HTTP Basic không bật, session/token không hợp lệ, UserDetailsService/PasswordEncoder cấu hình sai.

DelegatingFilterProxy không xác minh password, nên không sửa bằng cách thay targetBeanName hoặc thêm bridge thứ hai nếu manager/provider mới là nguyên nhân.

### 13.6. Bước F — authorization

Một user đã xác thực có ROLE_USER gọi /admin cần ROLE_ADMIN thường nhận 403. 403 không đồng nghĩa DelegatingFilterProxy bị lỗi. Có thể còn CSRF, CORS hoặc business permission; cần xác định filter/handler nào từ chối.

### 13.7. Bước G — request không đến Controller

Nếu một filter bảo mật từ chối request và không gọi phần còn lại của chain, DispatcherServlet không chạy. Đừng dựa vào việc breakpoint trong @RestController không hit để kết luận Servlet Container hoặc DelegatingFilterProxy không hoạt động.

## 14. Bảng triệu chứng và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
| --- | --- | --- |
| Có SecurityFilterChain bean nhưng URL vẫn không được bảo vệ | Bridge registration sai hoặc không có chain khớp | Container registrations và securityMatcher |
| Bean springSecurityFilterChain không tìm thấy | Spring context/auto config lỗi | ApplicationContext, classpath, @EnableWebSecurity |
| DFP tìm tên myProxy thay vì springSecurityFilterChain | filter-name khác, không set targetBeanName | web.xml hoặc registration target name |
| App startup fail vì duplicate filter registrations | web.xml và Boot/initializer cùng đăng ký | Loại bỏ bridge thừa |
| Custom filter được gọi hai lần | Bean auto-registration + HttpSecurity.addFilter | Tắt container registration hoặc chỉ new trong chain |
| Custom filter có Authentication=null | Chạy trước context/authentication filter | Xem vị trí trong FilterChainProxy |
| URL /api/** dùng rule web fallback | @Order/securityMatcher không như dự định | Kiểm tra first matching chain |
| Endpoint public có Basic header sai bị 401 | Authentication filter vẫn chạy trước permitAll | Phân biệt authentication failure với authorization |
| GET /admin 403 dù login đúng | Thiếu ROLE_ADMIN | Kiểm tra granted authorities và hasRole |
| POST 403 trước Controller | CSRF token thiếu/sai | CsrfFilter và client token |
| Error page không có header probe | DispatcherType/early short circuit | Kiểm tra ERROR dispatch |
| Async task không thấy SecurityContext | ThreadLocal không tự propagate | Dùng context propagation phù hợp |
| Filter order container đổi nhưng order nội bộ không đổi | Chỉnh nhầm cấp filter | HttpSecurity order vs FilterRegistrationBean |
| Request vào /unknown 401/403 thay vì 404 | Security filter chặn trước MVC | Kiểm tra rule anyRequest |
| WebFlux app không thấy DelegatingFilterProxy | Không phải Servlet stack | Xem WebFilterChainProxy/SecurityWebFilterChain |

### 14.1. Không tạo filter proxy mới để “sửa” 401/403

Nếu request đã đi qua FilterChainProxy và Authn/Authz trả 401/403 có chủ đích, thêm DelegatingFilterProxy có thể chỉ làm tăng số lần xử lý. Phải tìm đúng lớp đang chịu trách nhiệm từ chối.

### 14.2. Đừng đẩy logic phân quyền vào container filter tự viết

Một container-level filter có thể chạy trước khi SecurityContext được khôi phục hoặc trước AuthenticationFilter. Nếu muốn dựa vào authorities/tenant quyền sở hữu, cân nhắc đặt logic vào method security/service hoặc custom security filter sau các bước cần thiết.

### 14.3. Tại sao permitAll và ignoring không giống nhau?

Nếu request permitAll, FilterChainProxy vẫn chọn chain; filter headers/CSRF/context có thể chạy. Nếu bạn loại trừ bằng ignoring hoặc không có chain match, nhiều bảo vệ Spring Security không được áp dụng. Đừng dùng ignoring cho endpoint public chỉ để giảm một vài dòng log mà bỏ qua các security headers cần thiết.

## 15. Vấn đề hiệu năng và observability

DelegatingFilterProxy tồn tại để chuyển lời gọi vào một bean đã được Spring quản lý. Nó không yêu cầu container tạo lại các security filters hoặc UserDetailsService cho mọi request. Tốc độ xử lý thực tế thường phụ thuộc authentication/token validation, database lookups, session, serialization, network và các custom filters.

Các điểm cần chú ý:

- **Filter bean state:** một filter có thể xử lý nhiều requests đồng thời, tránh lưu user/session hiện hành vào instance fields hoặc biến static.
- **SecurityContext:** quản lý theo request/session hoặc token, không dùng một biến toàn cục đại diện “currentUser”.
- **Filter order:** log/tracing container và security filters có thể đo các khoảng thời gian khác nhau; hiểu tầng nào chạy trước khi diễn giải số liệu.
- **Exception behavior:** filter có thể dừng chain sớm, nên response 401/403 có thể không mang các marker được thêm bởi filter đặt sau.
- **Sensitive data:** không log raw Authorization, Cookie, password, JWT, refresh token hay nguyên Authentication object.
- **Distributed apps:** proxy/load balancer/session store có thể thay behavior; đừng mặc định integration test embedded server phản ánh 100% production.

Nếu cần correlation, dùng request ID/timing metadata đã được kiểm soát, không đem credentials vào log. Một Servlet Filter tracing bên ngoài security chain cần kiểm tra các dispatcher types và exception handling để không ghi response nhạy cảm.

## 16. Checklist khi áp dụng kiến trúc Servlet Security

- [ ] Xác định ứng dụng thực sự dùng **Servlet** chứ không phải WebFlux.
- [ ] Spring Boot có bean springSecurityFilterChain/FilterChainProxy hợp lệ.
- [ ] Container chỉ có **một đăng ký bridge dự kiến** cho cùng security processing path.
- [ ] Không tự thêm DelegatingFilterProxy nếu Boot đã auto-register.
- [ ] Không nhầm SecurityFilterChain bean với một Servlet Filter.
- [ ] Nếu legacy web.xml, filter-name hoặc targetBeanName trỏ đúng bean.
- [ ] Hiểu targetFilterLifecycle mặc định false; không tự bật true khi không cần.
- [ ] Với nhiều chains, @Order và securityMatcher rõ ràng, có fallback phù hợp.
- [ ] Không để các URL ngoài toàn bộ SecurityFilterChain ngoài ý muốn.
- [ ] Dùng permitAll cho endpoint public cần hưởng security filters.
- [ ] Custom security filter không đồng thời auto-register ở Servlet Container.
- [ ] Custom filter được đặt trước/sau filter phù hợp dựa trên nhu cầu context/authentication.
- [ ] Không tạo Authentication đáng tin từ dữ liệu người dùng chưa xác minh.
- [ ] Có tests GET/POST, anonymous/authenticated/forbidden và route mới.
- [ ] Có test qua embedded Servlet Container khi cần kiểm tra registration thực.
- [ ] Kiểm tra CSRF/session/ERROR/ASYNC dispatcher behavior theo thực tế.
- [ ] Tránh in Authorization, cookie, token, password hay whole SecurityContext khi debug.
- [ ] Sau deploy, so sánh container registrations, security chain logs và integration test thực tế.

## 17. Tự kiểm tra kiến thức

**Câu 1.** DelegatingFilterProxy thuộc Spring Framework hay riêng Spring Security?  
**Đáp:** Spring Framework. Nó là Servlet Filter có khả năng delegate tới một Spring bean implements Filter.

**Câu 2.** Ai gọi DelegatingFilterProxy.doFilter?  
**Đáp:** Servlet Container thông qua Servlet FilterChain.

**Câu 3.** Bean target thường có tên nào trong Spring Security?  
**Đáp:** springSecurityFilterChain.

**Câu 4.** Bean springSecurityFilterChain thường là class gì?  
**Đáp:** FilterChainProxy, một Filter do Spring Security quản lý.

**Câu 5.** SecurityFilterChain có phải một Servlet Filter được Tomcat gọi trực tiếp không?  
**Đáp:** Không. Nó mô tả matcher và các security filters để FilterChainProxy sử dụng.

**Câu 6.** FilterChainProxy chạy tất cả SecurityFilterChain khớp cùng một request không?  
**Đáp:** Không. Nó chọn chain đầu tiên phù hợp theo thứ tự.

**Câu 7.** targetBeanName dùng làm gì?  
**Đáp:** Chỉ định tên bean Filter mà DelegatingFilterProxy sẽ tìm trong Spring context.

**Câu 8.** Nếu targetBeanName không được cấu hình, proxy thường dựa vào tên nào?  
**Đáp:** Servlet filter-name.

**Câu 9.** targetFilterLifecycle mặc định true hay false?  
**Đáp:** False, do target bean thường được Spring quản lý lifecycle.

**Câu 10.** Với Boot embedded jar, cần tự tạo DelegatingFilterProxy bean mỗi lần viết SecurityFilterChain không?  
**Đáp:** Không. Boot thường tự đăng ký bridge.

**Câu 11.** Vì sao một @Component Filter thêm vào HttpSecurity có thể chạy hai lần?  
**Đáp:** Boot có thể auto-register Filter bean ở cấp Servlet Container, còn HttpSecurity thêm nó vào security chain.

**Câu 12.** Làm thế nào để giữ Filter bean cho DI mà không cho Boot register nó ngoài security chain?  
**Đáp:** Khai báo FilterRegistrationBean cho bean đó và setEnabled(false).

**Câu 13.** permitAll có loại bỏ security filter chain không?  
**Đáp:** Không. Nó là rule authorization; các security filters vẫn có thể chạy.

**Câu 14.** Nếu không có SecurityFilterChain nào khớp request thì sao?  
**Đáp:** Spring Security không áp security filters cho request đó; endpoint có thể không được bảo vệ.

**Câu 15.** Test MockMvc đủ để kết luận embedded Servlet Container đã gọi DelegatingFilterProxy chưa?  
**Đáp:** Không mặc nhiên. Dùng integration test qua embedded server hoặc kiểm tra ServletContext registration.

**Câu 16.** Chỉnh spring.security.filter.order có đổi thứ tự BasicAuthenticationFilter và AuthorizationFilter không?  
**Đáp:** Không. Nó liên quan cấp Servlet Container, còn thứ tự security filters nằm trong FilterChainProxy.

**Câu 17.** Basic header sai trên endpoint permitAll có thể trả 401 không?  
**Đáp:** Có thể, vì authentication filter có thể cố xác thực credential do client gửi.

**Câu 18.** Khi một filter chặn request và không gọi chain.doFilter, Controller có chạy không?  
**Đáp:** Không, các downstream filters/Servlet không được gọi theo nhánh đó.

**Câu 19.** Spring Security WebFlux có dùng DelegatingFilterProxy Servlet không?  
**Đáp:** Không. WebFlux sử dụng WebFilter/WebFilterChainProxy và SecurityWebFilterChain.

## 18. Nguồn tham khảo chính thức

- Spring Security — Servlet Architecture, DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, custom filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Framework 6.1 — DelegatingFilterProxy API: https://docs.spring.io/spring-framework/docs/6.1.9/javadoc-api/org/springframework/web/filter/DelegatingFilterProxy.html
- Spring Security — FilterChainProxy API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security — HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — XML Namespace web.xml registration: https://docs.spring.io/spring-security/reference/servlet/configuration/xml-namespace.html
- Spring Boot — Embedded Web Servers and Filter registration: https://docs.spring.io/spring-boot/how-to/webserver.html
- Spring Boot — Spring Security auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
