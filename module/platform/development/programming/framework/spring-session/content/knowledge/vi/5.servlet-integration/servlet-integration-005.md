# AbstractHttpSessionApplicationInitializer và khởi tạo ứng dụng Servlet

Spring Session thay thế cách lưu HttpSession mặc định của Servlet bằng session được quản lý qua một repository như Redis hoặc JDBC. Để thay thế này có hiệu lực, ứng dụng phải khởi tạo đúng Spring context và đăng ký filter của Spring Session vào Servlet container trước những filter hoặc thành phần có thể truy cập session.

AbstractHttpSessionApplicationInitializer là lớp tiện ích dành cho ứng dụng Servlet dùng cấu hình Java. Nó giúp đăng ký springSessionRepositoryFilter vào Servlet container và, tùy constructor được dùng, có thể tạo luôn ContextLoaderListener để nạp cấu hình Spring. Hiểu rõ vai trò của initializer giúp tránh các lỗi phổ biến như filter không chạy, Spring Security tạo session gốc của container trước Spring Session, hoặc hai root context cùng được khởi tạo.

## 1. Vị trí của initializer trong quá trình khởi động

Một ứng dụng Servlet truyền thống được khởi động bởi Servlet container như Tomcat, Jetty hoặc một container tương thích Jakarta Servlet. Trong Servlet 3.0 trở lên, Spring cung cấp SpringServletContainerInitializer để tìm các lớp triển khai WebApplicationInitializer trên classpath và gọi phương thức onStartup(ServletContext). Vì AbstractHttpSessionApplicationInitializer triển khai WebApplicationInitializer, container có thể tự phát hiện subclass của nó khi ứng dụng được triển khai đúng cách.

Trong quá trình khởi động, các thành phần chính có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| Servlet container | Tạo ServletContext, gọi các initializer và quản lý servlet/filter/listener |
| WebApplicationInitializer | Đăng ký thành phần Servlet bằng Java trong onStartup |
| ContextLoaderListener | Tạo root WebApplicationContext và nạp cấu hình Spring cấp ứng dụng |
| @EnableRedisHttpSession hoặc @EnableJdbcHttpSession | Cấu hình repository và tạo bean filter có tên springSessionRepositoryFilter |
| AbstractHttpSessionApplicationInitializer | Đăng ký proxy của filter Spring Session vào Servlet container |
| DispatcherServlet | Nhận request MVC và điều phối tới controller |

Điều quan trọng là initializer không tự biến Redis hoặc JDBC thành kho session. Cấu hình @Enable...HttpSession tạo các bean Spring cần thiết; initializer kết nối filter đã được tạo với vòng đời request của Servlet container.

## 2. Filter nào thực sự thay thế HttpSession?

Spring Session tạo một filter tên springSessionRepositoryFilter. Filter thực tế là SessionRepositoryFilter. Khi xử lý request, filter bọc HttpServletRequest bằng một wrapper để những lời gọi như request.getSession() hoặc request.getSession(false) làm việc với session được tải từ SessionRepository.

Luồng đơn giản:

1. Trình duyệt gửi cookie chứa session ID.
2. springSessionRepositoryFilter nhận request trước các filter ứng dụng khác.
3. Filter đọc session ID và tìm session trong Redis, JDBC hoặc repository đang cấu hình.
4. Filter đưa request wrapper vào FilterChain. Wrapper cung cấp HttpSession do Spring Session quản lý.
5. Spring Security, filter ứng dụng, DispatcherServlet và controller phía sau sử dụng cùng abstraction HttpSession.
6. Khi request kết thúc, thay đổi session được lưu theo repository và chính sách flush/save đã cấu hình; response có thể mang cookie session tương ứng.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Servlet container nhận request] --> B[DelegatingFilterProxy]
    B --> C[springSessionRepositoryFilter]
    C --> D[SessionRepositoryFilter bọc HttpServletRequest]
    D --> E[Spring Security và các filter ứng dụng]
    E --> F[DispatcherServlet]
    F --> G[Controller sử dụng HttpSession]
    G --> H[Filter hoàn tất và lưu session]
    H --> I[Response gửi về trình duyệt]
~~~

DelegatingFilterProxy là cầu nối giữa Servlet container và Spring ApplicationContext. Container quản lý proxy như một Servlet Filter; proxy tìm bean Spring có tên tương ứng và chuyển việc xử lý request cho bean đó. Với Spring Session, tên mặc định là springSessionRepositoryFilter.

Vì filter thay thế HttpSession ở request wrapper, vị trí của nó trong filter chain có ý nghĩa quyết định. Nếu một filter chạy trước Spring Session gọi getSession(), container có thể tạo hoặc truy cập session gốc. Điều đó dẫn tới việc các thành phần phía sau quan sát trạng thái session không nhất quán. Spring Session filter cần đứng trước các filter có thể sử dụng session, đặc biệt là chuỗi filter bảo mật.

## 3. Cấu hình repository trong Spring context

Ví dụ dưới đây dùng Redis. Dependency cần có gồm Spring Session Data Redis và Spring Data Redis; phiên bản nên được quản lý bằng BOM tương thích của Spring Boot hoặc Spring Framework/Spring Session đang sử dụng.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.session.data.redis.config.annotation.web.http.EnableRedisHttpSession;

@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
public class SessionConfig {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        return new LettuceConnectionFactory("localhost", 6379);
    }
}
~~~

@EnableRedisHttpSession kích hoạt cấu hình Spring Session dựa trên Redis. Cấu hình này tạo repository và bean springSessionRepositoryFilter. RedisConnectionFactory cung cấp kết nối tới Redis. Trong production, host, port, TLS, xác thực và pool nên được cấu hình theo hạ tầng thực tế thay vì dùng địa chỉ localhost.

Nếu dùng JDBC, phần cấu hình thay bằng @EnableJdbcHttpSession và cung cấp DataSource cùng các thành phần giao dịch cần thiết. Phần khởi tạo Servlet vẫn đăng ký cùng bean filter có tên springSessionRepositoryFilter; chỉ repository phía sau filter thay đổi.

## 4. Dùng constructor có cấu hình của AbstractHttpSessionApplicationInitializer

Cách ngắn nhất cho ứng dụng Java configuration độc lập là kế thừa lớp initializer và truyền các lớp cấu hình vào constructor:

~~~java
import org.springframework.session.web.context.AbstractHttpSessionApplicationInitializer;

public class SessionInitializer
        extends AbstractHttpSessionApplicationInitializer {

    public SessionInitializer() {
        super(SessionConfig.class);
    }
}
~~~

Constructor super(SessionConfig.class) yêu cầu initializer tạo ContextLoaderListener để nạp SessionConfig vào root WebApplicationContext. Cùng lúc, initializer đăng ký DelegatingFilterProxy trỏ tới bean springSessionRepositoryFilter của context đó.

Tên subclass có thể tùy chọn; điều quan trọng là lớp được container phát hiện và thực sự kế thừa AbstractHttpSessionApplicationInitializer. Không cần tự đăng ký thêm một DelegatingFilterProxy khác cho cùng bean nếu đã dùng initializer này.

Mẫu này phù hợp khi initializer chịu trách nhiệm tạo root context. Nếu ứng dụng đã có initializer khác tạo root context, hãy dùng constructor không tham số như phần tiếp theo để tránh tạo thêm một ContextLoaderListener và một root context trùng lặp.

## 5. Kết hợp với Spring MVC đã có initializer

Một ứng dụng MVC thường có lớp kế thừa AbstractAnnotationConfigDispatcherServletInitializer để tạo root context, servlet context và đăng ký DispatcherServlet. Trong trường hợp này, cấu hình Spring Session nên được thêm vào root context hiện hữu; initializer Spring Session dùng constructor không tham số:

~~~java
import org.springframework.session.web.context.AbstractHttpSessionApplicationInitializer;

public class SpringSessionFilterInitializer
        extends AbstractHttpSessionApplicationInitializer {
    // Root context được tạo bởi MVC initializer.
}
~~~

Đưa SessionConfig vào danh sách root configuration classes của MVC initializer:

~~~java
import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class MvcInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return new Class<?>[] {
            RootConfig.class,
            SecurityConfig.class,
            SessionConfig.class
        };
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
~~~

Ở mô hình này:

- MvcInitializer tạo root context và DispatcherServlet.
- SessionConfig nằm trong root context, cùng nơi thường đặt service, repository và cấu hình bảo mật dùng chung.
- SpringSessionFilterInitializer đăng ký filter proxy nhưng không tạo thêm root context.
- WebConfig nằm trong servlet context, thường chứa controller, view resolver và cấu hình MVC.

Không đưa cùng SessionConfig vào cả root context và servlet context. Tạo nhiều bản sao của cấu hình session có thể dẫn tới nhiều bean repository hoặc lỗi trùng tên bean.

### Vì sao nên đặt cấu hình session trong root context?

Mặc định, DelegatingFilterProxy tìm bean filter trong root WebApplicationContext được gắn với ServletContext. Vì vậy, đặt SessionConfig trong root context giúp proxy tìm được springSessionRepositoryFilter theo cách thông thường. Cấu hình MVC chỉ tồn tại trong child context của DispatcherServlet có thể không được proxy tìm thấy theo mặc định.

AbstractHttpSessionApplicationInitializer có phương thức getDispatcherWebApplicationContextSuffix() để chỉ định servlet context của một DispatcherServlet khi cần tìm bean ở child context. Đây là tùy chỉnh nâng cao; chỉ dùng khi kiến trúc ứng dụng chủ ý đặt filter bean ở context đó và đã xác định đúng servlet name. Với phần lớn ứng dụng, root context là nơi dễ quản lý hơn.

## 6. Thứ tự filter và tích hợp Spring Security

Spring Session phải chạy trước mọi filter có thể gọi HttpServletRequest.getSession(). Trường hợp thường gặp nhất là springSecurityFilterChain, vì Spring Security có thể tạo session để lưu SecurityContext, request cache, CSRF state hoặc thông tin xác thực khác tùy cấu hình.

Thứ tự mong muốn:

~~~text
Request
  -> springSessionRepositoryFilter
  -> springSecurityFilterChain
  -> các filter ứng dụng khác cần HttpSession
  -> DispatcherServlet
  -> Controller
Response
~~~

AbstractHttpSessionApplicationInitializer đăng ký DelegatingFilterProxy cho springSessionRepositoryFilter trước các filter đã được đăng ký theo cơ chế mà lớp này quản lý. Tuy nhiên, thứ tự cuối cùng vẫn phụ thuộc các initializer khác và cách chúng đăng ký filter. Javadoc lưu ý rằng subclass của AbstractDispatcherServletInitializer có thể đăng ký filter của chúng trước các filter khác. Khi ứng dụng có nhiều initializer, cần sắp xếp thứ tự thực thi và kiểm tra filter chain thực tế để Spring Session đứng trước các filter truy cập session.

Không nên chỉ nhìn thứ tự khai báo bean trong Spring context để suy ra thứ tự filter. Thứ tự filter được quyết định ở Servlet container, qua filter mapping và thứ tự đăng ký. Có thể kiểm tra lúc khởi động bằng log của container/Spring và xác minh bằng integration test.

Nếu ứng dụng dùng Spring Security, kiểm tra các điểm sau:

- Cấu hình SecurityConfig và SessionConfig được nạp vào context phù hợp.
- springSessionRepositoryFilter chạy trước springSecurityFilterChain.
- Chỉ có một cơ chế chính quản lý session cho ứng dụng; tránh đăng ký thủ công thêm filter trùng với initializer.
- Đăng xuất xóa session qua Spring Security/Spring Session theo cấu hình; cookie được xóa hoặc hết hạn theo response.
- Nếu dùng kiểm soát số phiên đồng thời, kiểm tra repository có hỗ trợ sự kiện cần thiết và cấu hình listener tương ứng.

## 7. Các hook mở rộng của initializer

Trong phần lớn ứng dụng, kế thừa initializer mà không override phương thức nào là đủ. Khi cần tích hợp filter hoặc dispatcher đặc biệt, lớp cơ sở cung cấp một số hook:

| Phương thức | Vai trò |
|---|---|
| beforeSessionRepositoryFilter(ServletContext) | Được gọi trước khi đăng ký filter Spring Session |
| afterSessionRepositoryFilter(ServletContext) | Được gọi sau khi filter Spring Session đã được thêm |
| insertFilters(ServletContext, Filter...) | Đăng ký các filter được cung cấp trước các filter đã tồn tại |
| appendFilters(ServletContext, Filter...) | Đăng ký các filter được cung cấp sau các filter đã tồn tại |
| getSessionDispatcherTypes() | Tùy chỉnh các loại dispatch mà Spring Session filter tham gia |
| isAsyncSessionSupported() | Quyết định filter có khai báo hỗ trợ asynchronous processing hay không |
| getDispatcherWebApplicationContextSuffix() | Chọn servlet context để proxy tìm bean filter thay vì root context mặc định |

Theo API hiện hành, hỗ trợ async của filter được bật mặc định. Chỉ override isAsyncSessionSupported() hoặc getSessionDispatcherTypes() khi ứng dụng có yêu cầu rõ ràng về async, forward, include hoặc error dispatch. Nếu filter không tham gia đúng các dispatcher type cần thiết, request bất đồng bộ hoặc request được dispatch lại có thể quan sát hành vi session khác với request thông thường.

Ví dụ dưới đây minh họa một subclass có thể đặt cấu hình Servlet trước khi filter được đăng ký. Không nên chèn một filter tùy tiện vào vị trí này nếu nó cần Spring Session; thứ tự phải phản ánh rõ filter nào được phép truy cập session:

~~~java
import jakarta.servlet.ServletContext;
import org.springframework.session.web.context.AbstractHttpSessionApplicationInitializer;

public class SessionInitializer
        extends AbstractHttpSessionApplicationInitializer {

    public SessionInitializer() {
        super(SessionConfig.class);
    }

    @Override
    protected void beforeSessionRepositoryFilter(ServletContext servletContext) {
        // Chỉ dùng cho cấu hình Servlet cần thiết trước khi đăng ký filter.
    }
}
~~~

Các hook là điểm mở rộng trong giai đoạn khởi tạo ServletContext; chúng không phải callback chạy trên từng request. Logic nghiệp vụ hoặc xử lý session theo request nên nằm trong filter, listener hoặc service phù hợp.

## 8. Khi nào dùng initializer, khi nào dùng web.xml hoặc Spring Boot?

Có ba kiểu triển khai thường gặp:

| Kiểu ứng dụng | Cách đăng ký Spring Session |
|---|---|
| WAR dùng Servlet 3+ và cấu hình Java, không dựa vào Boot auto-configuration | Kế thừa AbstractHttpSessionApplicationInitializer |
| WAR dùng cấu hình XML hoặc container/thiết lập cần khai báo tường minh | Đăng ký ContextLoaderListener và DelegatingFilterProxy trong web.xml |
| Ứng dụng Spring Boot | Thường dùng auto-configuration của Spring Boot thông qua starter và cấu hình spring.session.*; không cần tự tạo initializer này cho luồng thông thường |

### Khai báo filter trong web.xml

Nếu không dùng Java initializer, có thể đăng ký proxy bằng web.xml:

~~~xml
<filter>
    <filter-name>springSessionRepositoryFilter</filter-name>
    <filter-class>
        org.springframework.web.filter.DelegatingFilterProxy
    </filter-class>
</filter>

<filter-mapping>
    <filter-name>springSessionRepositoryFilter</filter-name>
    <url-pattern>/*</url-pattern>
</filter-mapping>
~~~

Root Spring context vẫn phải nạp cấu hình có bean tên springSessionRepositoryFilter. Đoạn XML chỉ đăng ký proxy và mapping; nó không tự tạo repository hay cấu hình Redis/JDBC. Nếu ứng dụng vừa khai báo proxy trong web.xml vừa dùng AbstractHttpSessionApplicationInitializer để đăng ký cùng filter, có nguy cơ filter bị đăng ký hai lần.

### Spring Boot

Trong ứng dụng Spring Boot, starter phù hợp thường kích hoạt auto-configuration cho repository và filter. Ví dụ, thêm Spring Session Data Redis sẽ cho phép Boot cấu hình session dựa trên Redis khi các điều kiện auto-configuration được thỏa mãn. Nếu có nhiều implementation trên classpath, cần chọn store type theo cấu hình Boot của phiên bản đang dùng.

Boot quản lý Servlet context và filter registration thông qua cơ chế auto-configuration. Vì vậy, không nên thêm AbstractHttpSessionApplicationInitializer theo thói quen của ứng dụng WAR Java configuration cổ điển. Chỉ dùng khi đang chủ động kiểm soát một Servlet deployment đặc thù và hiểu rõ cơ chế đăng ký filter của Boot.

## 9. Các lỗi khởi tạo thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ứng dụng vẫn tạo session cục bộ dù đã thêm dependency | Filter chưa được đăng ký, không được gọi hoặc không áp dụng cho URL request | Kiểm tra initializer được phát hiện, filter mapping và log khởi động |
| Lỗi không tìm thấy bean springSessionRepositoryFilter | @EnableRedisHttpSession/@EnableJdbcHttpSession chưa được nạp hoặc nằm trong context mà proxy không tìm kiếm | Kiểm tra root context và tên bean |
| Spring Security thấy session khác với controller | Spring Session filter chạy sau security filter hoặc có filter tạo session trước nó | Kiểm tra thứ tự đăng ký và mọi lời gọi getSession() trong filter |
| Có hai session hoặc hai cookie hành xử không nhất quán | Đăng ký proxy trùng, cấu hình repository trùng hoặc vừa dùng auto-configuration vừa tự đăng ký | Kiểm tra danh sách filter, initializer và cấu hình |
| Lỗi kết nối Redis/JDBC ngay khi request cần session | Thiếu RedisConnectionFactory, DataSource, sai endpoint hoặc thông tin xác thực | Kiểm tra bean kết nối và log repository |
| MVC chạy nhưng filter không tìm được cấu hình | Session config chỉ nằm trong servlet child context trong khi proxy tìm root context | Chuyển cấu hình vào root context hoặc cấu hình suffix đúng có chủ đích |
| Request async hoặc error dispatch có session không như mong đợi | Dispatcher type hoặc async support của filter không phù hợp | Kiểm tra getSessionDispatcherTypes() và isAsyncSessionSupported() |

Một quy trình chẩn đoán có thứ tự sẽ tiết kiệm thời gian:

1. Xác nhận container có phát hiện initializer.
2. Xác nhận Spring root context khởi động thành công.
3. Xác nhận bean springSessionRepositoryFilter tồn tại đúng một lần.
4. Xác nhận proxy được mapping tới /* và được gọi trước filter bảo mật.
5. Xác nhận repository có thể kết nối tới Redis/JDBC.
6. Gửi hai request liên tiếp với cùng client cookie và xác nhận session được dùng lại.
7. Kiểm tra cookie response, session ID và dữ liệu trong kho bằng công cụ vận hành phù hợp; không ghi session ID thật vào log.

## 10. Kiểm thử tích hợp quá trình khởi tạo

Unit test cho controller có thể dùng MockHttpSession, nhưng nó không xác minh Servlet container đã đăng ký filter đúng cách. Đối với ứng dụng WAR dùng initializer, cần có integration test chạy với embedded hoặc test Servlet container tương thích.

Các kiểm tra có giá trị:

- Khi ứng dụng khởi động, root context có bean springSessionRepositoryFilter và repository tương ứng.
- Một request tạo session nhận cookie session từ Spring Session.
- Request kế tiếp gửi lại cookie và đọc được cùng session attribute.
- Thay đổi attribute được lưu vào Redis/JDBC theo cấu hình.
- Spring Security sử dụng cùng session đã được Spring Session bọc.
- Request async, forward hoặc error dispatch vẫn đi qua filter theo dispatcher types đã cấu hình.
- Khi đăng xuất, session bị xóa khỏi repository và client nhận response xóa/điều chỉnh cookie theo chính sách.
- Hai instance của ứng dụng có thể tiếp tục cùng session khi cùng kết nối tới một repository dùng chung.

Có thể tạo endpoint kiểm thử đơn giản:

~~~java
import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
public class SessionProbeController {

    @GetMapping("/session/probe")
    public Map<String, Object> probe(HttpSession session) {
        Integer count = (Integer) session.getAttribute("probe.count");
        count = (count == null) ? 1 : count + 1;

        session.setAttribute("probe.count", count);

        return Map.of(
            "sessionId", session.getId(),
            "count", count
        );
    }
}
~~~

Gọi endpoint hai lần bằng cùng cookie sẽ làm count tăng từ 1 lên 2. Nếu gọi request thứ hai qua instance khác nhưng vẫn dùng cùng repository chia sẻ, kết quả tiếp tục tăng. Endpoint này chỉ dành cho môi trường kiểm thử: không đưa session ID vào response của endpoint production hoặc log công khai.

## 11. Checklist trước khi triển khai

Trước khi đưa ứng dụng Servlet sử dụng Spring Session lên môi trường thật, hãy xác nhận:

- Phiên bản Servlet API tương thích với phiên bản Spring Session và Spring Framework. Các dòng Spring Session hiện đại dùng Jakarta Servlet (jakarta.servlet); dự án cũ dùng javax.servlet phải theo đúng dòng phiên bản tương ứng.
- Container có khả năng tự phát hiện WebApplicationInitializer nếu dùng Java initializer.
- Đúng một root context chịu trách nhiệm nạp SessionConfig.
- Bean filter có tên springSessionRepositoryFilter được tạo.
- Filter được đăng ký đúng URL pattern, dispatcher type và async support.
- Spring Session filter chạy trước mọi filter cần HttpSession, đặc biệt là Spring Security.
- Chỉ có một đường đăng ký filter, tránh trùng giữa Java initializer, web.xml và Boot auto-configuration.
- Kết nối repository, TTL, cookie, serializer và chính sách logout đã được kiểm thử.
- Integration test xác nhận cùng một session tồn tại qua nhiều request và nhiều instance.

AbstractHttpSessionApplicationInitializer là cầu nối ở giai đoạn khởi động: nó đăng ký filter Spring Session vào Servlet container và có thể giúp nạp root context. Khi cấu hình repository được nạp đúng context và filter chạy đúng thứ tự, ứng dụng Servlet có thể tiếp tục sử dụng HttpSession quen thuộc trong controller và Spring Security, trong khi dữ liệu phiên được quản lý tập trung bởi Redis, JDBC hoặc repository đã chọn.

## Tài liệu tham khảo

- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)
- [AbstractHttpSessionApplicationInitializer Javadoc](https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/web/context/AbstractHttpSessionApplicationInitializer.html)
- [Spring Framework — Servlet Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/container-config.html)
- [SpringServletContainerInitializer Javadoc](https://docs.spring.io/spring-framework/docs/5.3.12/javadoc-api/org/springframework/web/SpringServletContainerInitializer.html)

