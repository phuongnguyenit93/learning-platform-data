# @SpringJUnitWebConfig cho kiểm thử web

Khi kiểm thử một ứng dụng Spring MVC, đôi khi ta cần nhiều hơn một controller được tạo trực tiếp. Ta muốn Spring nạp cấu hình web, tạo các bean MVC, đăng ký controller, converter, exception resolver và những thành phần liên quan trong một môi trường có ServletContext. **@SpringJUnitWebConfig** hỗ trợ đúng nhu cầu đó trong Spring TestContext Framework dành cho JUnit Jupiter.

Annotation này kết hợp việc tích hợp Spring với JUnit Jupiter, nạp cấu hình ứng dụng và bật ngữ cảnh web cho bài kiểm thử. Nhờ đó, test có thể nhận một WebApplicationContext được Spring quản lý rồi dùng nó để kiểm tra hành vi web, thường kết hợp với MockMvc.

Điều cần nhớ là @SpringJUnitWebConfig chuẩn bị một web application context cho kiểm thử. Nó không tự khởi động một HTTP server thật và cũng không tự tạo MockMvc. Người viết test vẫn cần chọn cấu hình ứng dụng, đăng ký các bean cần thiết và xây dựng client kiểm thử phù hợp.

## 1. @SpringJUnitWebConfig là gì?

@SpringJUnitWebConfig là composed annotation trong Spring Test, thuộc package:

~~~java
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
~~~

Nó gom các annotation thường phải khai báo cùng nhau:

- **@ExtendWith(SpringExtension.class):** kết nối Spring TestContext Framework với JUnit Jupiter. Spring có thể quản lý test instance, inject dependency vào test, chạy các callback và áp dụng các tính năng TestContext.
- **@ContextConfiguration:** chỉ định cách nạp ApplicationContext từ class cấu hình, XML resource hoặc initializer.
- **@WebAppConfiguration:** yêu cầu TestContext tạo WebApplicationContext thay vì ApplicationContext thông thường và thiết lập web resource root cho ServletContext.

Nhờ tổ hợp này, một test class có thể viết:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {
    // Spring inject WebApplicationContext và các dependency khác.
}
~~~

Thay vì khai báo riêng:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class GreetingControllerTest {
}
~~~

Hai cách thể hiện cùng mục tiêu cấu hình. Dùng @SpringJUnitWebConfig giúp test class ngắn gọn và thể hiện rõ rằng đây là một kiểm thử JUnit Jupiter cần web application context.

### 1.1. Annotation này dành cho JUnit Jupiter

@SpringJUnitWebConfig thuộc tích hợp JUnit Jupiter của Spring Test. Nó tự cung cấp SpringExtension thông qua meta-annotation, vì vậy test class không cần lặp lại @ExtendWith(SpringExtension.class).

Với JUnit 4, cách cấu hình thường dùng là @RunWith(SpringRunner.class), kết hợp @ContextConfiguration và @WebAppConfiguration. Không thể dùng @SpringJUnitWebConfig như một cách thay thế trực tiếp cho JUnit 4 runner.

### 1.2. WebApplicationContext khác ApplicationContext thông thường thế nào?

ApplicationContext quản lý bean và các dịch vụ của ứng dụng Spring. WebApplicationContext mở rộng mô hình đó cho môi trường web, gắn với ServletContext và các thành phần web cần thiết.

Trong một ứng dụng MVC, WebApplicationContext có thể chứa:

- Controller và các bean được controller sử dụng.
- RequestMappingHandlerMapping và RequestMappingHandlerAdapter.
- HttpMessageConverter để đọc request và ghi response.
- HandlerExceptionResolver để ánh xạ exception.
- LocaleResolver, ViewResolver và các thành phần MVC khác.
- Interceptor hoặc các bean web được cấu hình trong ứng dụng.

WebApplicationContext cho phép test kiểm tra cấu hình MVC trong một môi trường web mô phỏng. Nó không đồng nghĩa với việc ứng dụng đang chạy trong Tomcat, Jetty hoặc một servlet container thật.

## 2. Các thuộc tính cấu hình chính

@SpringJUnitWebConfig cung cấp các thuộc tính để chuyển cấu hình đến các annotation nền tảng mà nó kết hợp.

| Thuộc tính | Mục đích |
| --- | --- |
| classes | Các class cấu hình dùng để tạo context |
| locations | Đường dẫn resource cấu hình, thường là XML |
| initializers | Các ApplicationContextInitializer cần chạy khi tạo context |
| inheritLocations | Quy định cách kế thừa locations từ test class cha |
| inheritInitializers | Quy định cách kế thừa initializer |
| loader | Chọn ContextLoader phù hợp |
| name | Tên context trong một số cấu hình TestContext |
| resourcePath | Đường dẫn gốc tài nguyên web của @WebAppConfiguration |

Trong phần lớn dự án mới, classes là lựa chọn dễ đọc khi cấu hình bằng Java. locations vẫn hữu ích khi ứng dụng đang dùng XML hoặc cần kiểm thử một cấu hình XML hiện có.

### 2.1. Dùng classes với Java configuration

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {
}
~~~

Spring nạp WebTestConfig và các bean mà cấu hình đó khai báo. Nếu cấu hình cần import cấu hình khác, hãy dùng @Import trong configuration class hoặc khai báo cấu hình test phù hợp.

### 2.2. Dùng locations với XML

~~~java
@SpringJUnitWebConfig(
    locations = "classpath:/spring/test-web-context.xml"
)
class LegacyWebControllerTest {
}
~~~

Spring nạp resource XML theo vị trí được chỉ định. Đường dẫn classpath thường phù hợp với file nằm trong test resources. Với resource trên filesystem, hãy dùng cách biểu diễn đường dẫn phù hợp với ContextLoader và môi trường build.

Không nên khai báo đồng thời nhiều nguồn cấu hình chỉ để làm test khởi động được. Hãy chọn cấu hình phản ánh đúng phạm vi đang kiểm tra và bảo đảm các bean quan trọng được tạo theo cách ứng dụng dự kiến.

### 2.3. resourcePath và web resource root

@SpringJUnitWebConfig cho phép đặt resourcePath, thuộc tính tương ứng với @WebAppConfiguration. Mặc định, web resource root là:

~~~text
src/main/webapp
~~~

Nếu test cần một thư mục web riêng, có thể chỉ định:

~~~java
@SpringJUnitWebConfig(
    classes = WebTestConfig.class,
    resourcePath = "src/test/webapp"
)
class StaticResourceWebTest {
}
~~~

resourcePath xác định gốc tài nguyên web được dùng để tạo ServletContext mô phỏng. Nó không phải đường dẫn cấu hình bean; nhiệm vụ đó thuộc classes hoặc locations.

Hãy phân biệt:

- classes/locations: Spring lấy cấu hình nào để tạo bean và WebApplicationContext.
- resourcePath: ServletContext nhìn thấy tài nguyên web từ thư mục nào.

Nếu ứng dụng không có tài nguyên web kiểu truyền thống hoặc test không kiểm tra resource lookup, có thể giữ mặc định hoặc cấu hình resource root phù hợp với cấu trúc dự án. Không nên thay resourcePath chỉ vì muốn đổi vị trí file XML.

## 3. Chuẩn bị cấu hình web cho test

@SpringJUnitWebConfig không tự suy ra toàn bộ cấu hình MVC của ứng dụng. Test cần chỉ định một hoặc nhiều configuration class có các bean phù hợp.

Ví dụ nhỏ dưới đây sử dụng Spring MVC thuần:

~~~java
@FunctionalInterface
interface GreetingService {
    String greet(String name);
}

@RestController
@RequestMapping("/greetings")
class GreetingController {
    private final GreetingService greetingService;

    GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping(
        value = "/{name}",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    String greet(@PathVariable String name) {
        return greetingService.greet(name);
    }
}
~~~

Cấu hình web:

~~~java
@Configuration
@EnableWebMvc
class WebTestConfig {

    @Bean
    GreetingService greetingService() {
        return name -> "Hello, " + name;
    }

    @Bean
    GreetingController greetingController(
            GreetingService greetingService) {
        return new GreetingController(greetingService);
    }
}
~~~

@EnableWebMvc đăng ký hạ tầng Spring MVC cần thiết. GreetingController được đăng ký như một bean để MVC có thể phát hiện các mapping. Trong dự án thật, cấu hình có thể dùng @ComponentScan, @Import hoặc cấu hình web hiện có thay cho cách khai báo tường minh này.

Không cần tạo một cấu hình mới chỉ dành cho test nếu ứng dụng đã có cấu hình web phù hợp và test có thể nạp nó một cách an toàn. Tuy nhiên, test slice hoặc test context nhỏ thường có thể dùng một cấu hình tối thiểu để tập trung vào hành vi đang kiểm tra.

## 4. Ví dụ kiểm thử controller với MockMvc

Một cách dùng phổ biến là nạp WebApplicationContext bằng @SpringJUnitWebConfig, sau đó tạo MockMvc từ context đó.

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

@SpringJUnitWebConfig(classes = WebTestConfig.class)
class GreetingControllerTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
    }

    @Test
    void returns_greeting_for_requested_name() throws Exception {
        mockMvc.perform(get("/greetings/{name}", "An"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN
            ))
            .andExpect(content().string("Hello, An"));
    }
}
~~~

Ví dụ sử dụng MockMvc để gửi request qua MVC infrastructure đã được nạp trong WebApplicationContext. Test xác nhận:

1. URL được ánh xạ đến controller.
2. Path variable được binding thành tham số name.
3. Controller gọi service và tạo nội dung phản hồi.
4. Spring MVC trả HTTP 200 cùng content type và body theo hợp đồng.

MockMvc không mở cổng TCP và không gửi request qua mạng. Nó thực hiện xử lý request trong môi trường servlet mô phỏng, giúp kiểm tra MVC stack mà không cần khởi động server.

### 4.1. Vì sao dùng webAppContextSetup?

MockMvcBuilders có nhiều cách dựng MockMvc. Hai cách thường gặp:

| Cách dựng | Phạm vi |
| --- | --- |
| webAppContextSetup(WebApplicationContext) | Dùng WebApplicationContext đã nạp, phù hợp khi muốn kiểm tra cấu hình MVC và các bean web của context |
| standaloneSetup(controller) | Tạo MVC infrastructure cho controller được chỉ định, phù hợp với kiểm thử controller độc lập và cấu hình tối thiểu |

Khi dùng @SpringJUnitWebConfig, webAppContextSetup tận dụng chính WebApplicationContext mà TestContext đã tạo. Nó giúp test đi qua các mapping, converter, resolver và cấu hình được đăng ký trong context.

standaloneSetup không cần @SpringJUnitWebConfig trong nhiều trường hợp, vì test có thể tạo controller trực tiếp. Cách này nhanh và gọn nhưng không chứng minh rằng cấu hình MVC trong ứng dụng được nạp đúng.

### 4.2. Kiểm tra request không hợp lệ

Giả sử controller nhận một request body và dùng Bean Validation:

~~~java
public record CreateGreetingRequest(
    @NotBlank String name
) {}

@RestController
@RequestMapping("/api/greetings")
class GreetingApiController {

    @PostMapping
    ResponseEntity<String> create(
            @Valid @RequestBody CreateGreetingRequest request) {
        return ResponseEntity.ok("Hello, " + request.name());
    }
}
~~~

Một web context test có thể gửi body không hợp lệ:

~~~java
mockMvc.perform(post("/api/greetings")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {"name": ""}
            """))
    .andExpect(status().isBadRequest());
~~~

Để ví dụ này chạy, classpath cần có validation provider phù hợp và cấu hình MVC cần đăng ký các thành phần cần thiết. Trong Spring Boot, starter validation thường cung cấp dependency liên quan. Với Spring Framework thuần, cần khai báo provider và các dependency phù hợp.

Test trên chỉ kiểm tra status. Nếu API đã cam kết cấu trúc lỗi, hãy kiểm tra cả field, error code hoặc message ổn định theo hợp đồng. Không nên kiểm tra toàn bộ nội dung exception nội bộ nếu nó không phải dữ liệu API cam kết.

### 4.3. Kiểm tra exception mapping

Một WebApplicationContext có thể chứa @ControllerAdvice hoặc HandlerExceptionResolver. Dùng webAppContextSetup giúp test xác minh exception được chuyển thành response theo cấu hình MVC đã nạp.

Ví dụ:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<String> handleIllegalArgument(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest().body(exception.getMessage());
    }
}
~~~

Test có thể cấu hình controller ném IllegalArgumentException và kiểm tra status cùng response body. Mục tiêu là chứng minh exception đi qua MVC exception resolution trong context, không chỉ chứng minh một method Java bắt exception.

## 5. WebApplicationContext và ServletContext trong test

Với @SpringJUnitWebConfig, test có thể inject các đối tượng web:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
class WebContextTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    @Autowired
    ServletContext servletContext;

    @Test
    void loads_a_web_application_context() {
        assertThat(webApplicationContext).isNotNull();
        assertThat(servletContext).isNotNull();
        assertThat(webApplicationContext.getServletContext())
            .isSameAs(servletContext);
    }
}
~~~

ServletContext trong môi trường này thường là MockServletContext do Spring Test cung cấp. Nó mô phỏng các khả năng cần cho kiểm thử web, chẳng hạn truy cập tài nguyên và metadata servlet. Nó không phải ServletContext của một Tomcat đang chạy.

Việc inject WebApplicationContext hữu ích khi cần:

- Dựng MockMvc từ toàn bộ MVC context.
- Truy cập bean cấu hình web.
- Kiểm tra servlet context resource.
- Kiểm tra interceptor, converter hoặc exception resolver được đăng ký.
- Tạo một thành phần kiểm thử cần WebApplicationContext.

Không nên assertion rằng context đã khởi động thành công là đủ để kết luận mọi endpoint đúng. Cần gửi request hoặc kiểm tra hành vi cụ thể theo mục tiêu test.

## 6. Kết hợp với các annotation của TestContext Framework

@SpringJUnitWebConfig là một điểm bắt đầu. Nó có thể được kết hợp với các annotation khác của Spring TestContext để điều khiển môi trường.

### 6.1. @ActiveProfiles

Nếu ứng dụng có cấu hình profile riêng, @ActiveProfiles chỉ định profile được kích hoạt trong test:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
@ActiveProfiles("test")
class ProfiledWebTest {
}
~~~

Bean hoặc property được chọn theo profile sẽ được áp dụng khi tạo context. Hãy chỉ dùng profile test có cấu hình cần thiết, tránh đưa thông tin xác thực production hoặc endpoint bên ngoài vào test.

### 6.2. @TestPropertySource

@TestPropertySource có thể cung cấp property riêng cho test:

~~~java
@SpringJUnitWebConfig(classes = WebTestConfig.class)
@TestPropertySource(properties = {
    "app.web.greeting-prefix=Hello",
    "app.web.feature-enabled=true"
})
class GreetingConfigurationTest {
}
~~~

Property được nạp vào Environment của TestContext. Nếu muốn kiểm tra việc bind vào @ConfigurationProperties hoặc @Value, hãy inject bean và xác nhận hành vi sử dụng giá trị đó.

### 6.3. @DirtiesContext

TestContext Framework cache ApplicationContext để tái sử dụng giữa các test có cùng cấu hình. Nếu test làm thay đổi context theo cách không thể khôi phục và ảnh hưởng các test khác, @DirtiesContext có thể đánh dấu context cần loại khỏi cache.

Không nên dùng @DirtiesContext như một cách dọn dữ liệu thông thường. Với database state, hãy dùng transaction, fixture và cleanup đúng ranh giới. @DirtiesContext làm context phải được tạo lại, có thể khiến suite chậm đáng kể.

### 6.4. @ContextHierarchy

Một số ứng dụng web có root context và servlet-specific context. @ContextHierarchy cho phép mô tả nhiều cấp ApplicationContext khi kiến trúc ứng dụng cần chúng.

Ví dụ về mặt khái niệm:

~~~java
@ContextHierarchy({
    @ContextConfiguration(classes = RootConfig.class),
    @ContextConfiguration(classes = WebConfig.class)
})
@WebAppConfiguration
@ExtendWith(SpringExtension.class)
class HierarchicalWebContextTest {
}
~~~

Nếu không cần hierarchy, không nên thêm nó chỉ vì ứng dụng có nhiều package cấu hình. Một context đơn giản thường dễ hiểu và dễ cache hơn.

## 7. Phân biệt @SpringJUnitWebConfig với các lựa chọn khác

Các annotation kiểm thử web của Spring có mục tiêu khác nhau. Chọn đúng annotation giúp test có phạm vi rõ ràng.

| Lựa chọn | Nguồn | Mục tiêu | Có tự tạo MockMvc không? | Có server thật không? |
| --- | --- | --- | --- | --- |
| @SpringJUnitWebConfig | Spring Framework Test | Nạp WebApplicationContext theo cấu hình chỉ định cho JUnit Jupiter | Không | Không |
| @SpringJUnitConfig | Spring Framework Test | Nạp ApplicationContext thông thường cho JUnit Jupiter | Không | Không |
| @WebAppConfiguration + @ContextConfiguration | Spring Framework Test | Khai báo riêng web context và cấu hình context | Không | Không |
| @WebMvcTest | Spring Boot Test | MVC slice với auto-configuration và giới hạn bean theo web layer | Tùy cấu hình Boot test; thường dùng MockMvc | Không |
| @SpringBootTest + @AutoConfigureMockMvc | Spring Boot Test | Nạp Boot application context và cấu hình MockMvc | Có | Không |
| @SpringBootTest với RANDOM_PORT | Spring Boot Test | Chạy ứng dụng qua embedded web server | Không cần MockMvc | Có |

### 7.1. So với @SpringJUnitConfig

@SpringJUnitConfig kết hợp SpringExtension và ContextConfiguration để tạo ApplicationContext thông thường. Nó phù hợp với service, repository test có cấu hình Spring nhưng không cần WebApplicationContext.

@SpringJUnitWebConfig bổ sung web application context. Nếu test cần ServletContext, MVC infrastructure hoặc MockMvc được dựng từ WebApplicationContext, hãy dùng annotation web.

Không nên dùng @SpringJUnitWebConfig cho một service unit test chỉ vì class nằm trong ứng dụng web. Việc tạo web context làm test nặng hơn mà không tăng bằng chứng nếu hành vi không liên quan đến web.

### 7.2. So với @WebAppConfiguration và @ContextConfiguration

Có thể khai báo ba annotation riêng:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = WebTestConfig.class)
@WebAppConfiguration
class ExplicitWebContextTest {
}
~~~

@SpringJUnitWebConfig là cách viết gọn cho tổ hợp thường gặp này và cung cấp alias để cấu hình các thuộc tính của annotation nền tảng. Khi cần hiểu rõ từng phần, cách khai báo tường minh vẫn hữu ích trong tài liệu hoặc test có cấu hình đặc biệt.

### 7.3. So với @WebMvcTest

@WebMvcTest là annotation thuộc Spring Boot Test. Nó tạo một slice tập trung vào MVC và áp dụng auto-configuration của Spring Boot, thường chỉ nạp các bean thuộc phạm vi web cần thiết. Các collaborator của controller thường được thay bằng mock.

@SpringJUnitWebConfig thuộc Spring Framework TestContext Framework. Nó nạp WebApplicationContext theo classes hoặc locations được chỉ định. Nó không tự áp dụng quy tắc slice của Spring Boot và không tự giới hạn bean theo cùng cách @WebMvcTest.

Chọn @WebMvcTest khi muốn kiểm tra MVC slice của một ứng dụng Spring Boot. Chọn @SpringJUnitWebConfig khi muốn cấu hình web context rõ ràng bằng Spring TestContext, đặc biệt trong ứng dụng Spring MVC không phụ thuộc Boot hoặc khi cần một context web tùy chỉnh.

### 7.4. So với @SpringBootTest

@SpringBootTest khởi tạo Spring Boot application context theo cấu hình ứng dụng. Khi kết hợp @AutoConfigureMockMvc, test có thể dùng MockMvc mà không mở server. Khi dùng webEnvironment = RANDOM_PORT, Spring Boot khởi động embedded server trên cổng ngẫu nhiên.

@SpringJUnitWebConfig không khởi động Spring Boot application theo cơ chế @SpringBootTest. Nó nạp cấu hình Spring được chỉ định và tạo web context cho TestContext. Nếu mục tiêu là kiểm tra auto-configuration của Boot, application properties, server startup hoặc toàn bộ wiring của Boot application, hãy dùng công cụ Boot phù hợp.

## 8. @SpringJUnitWebConfig không tự khởi động HTTP server

Đây là điểm dễ nhầm khi bắt đầu dùng annotation này.

@WebAppConfiguration làm cho TestContext tạo WebApplicationContext và ServletContext mô phỏng. MockMvc gửi request trực tiếp qua Spring MVC test infrastructure. Không có socket TCP được mở và không có HTTP request thật đi qua mạng.

Nếu cần kiểm tra:

- Port binding.
- Embedded Tomcat/Jetty/Undertow.
- Servlet container behavior.
- HTTP connector, compression hoặc network timeout.
- TLS hoặc reverse proxy integration.

thì một WebApplicationContext cùng MockMvc không đủ. Hãy dùng @SpringBootTest(webEnvironment = RANDOM_PORT) hoặc dựng môi trường container/server thích hợp.

Ngược lại, nếu cần xác minh mapping, validation, converter, exception handler hoặc interceptor, MockMvc thường cung cấp bằng chứng phù hợp mà không cần server thật.

## 9. Cấu hình phụ thuộc và test double

@SpringJUnitWebConfig không quy định mọi collaborator phải là bean thật. Test có thể kết hợp context thật với các bean giả lập tại ranh giới thích hợp.

Ví dụ, controller thật và MVC infrastructure thật có thể dùng một service giả lập để kiểm tra response mapping. Có thể đăng ký bean test bằng @TestConfiguration hoặc dùng cơ chế bean override phù hợp phiên bản Spring.

~~~java
@TestConfiguration
class GreetingTestBeans {

    @Bean
    @Primary
    GreetingService greetingService() {
        return name -> "Test greeting for " + name;
    }
}
~~~

Sau đó import cấu hình vào test:

~~~java
@SpringJUnitWebConfig(classes = {
    WebTestConfig.class,
    GreetingTestBeans.class
})
class GreetingControllerWithTestServiceTest {
}
~~~

Trong ví dụ này, nếu cả WebTestConfig và GreetingTestBeans cùng đăng ký một bean GreetingService với cùng điều kiện, cần hiểu rõ quy tắc chọn bean. @Primary giúp Spring ưu tiên bean test khi inject theo type, nhưng việc có hai bean cùng tồn tại vẫn có thể ảnh hưởng các điểm inject theo tên hoặc collection. Một cách khác là tạo cấu hình test riêng chỉ đăng ký đúng bean cần thiết.

Nếu test muốn kiểm tra toàn bộ application behavior, không thay service thật chỉ để đơn giản hóa setup. Nếu mục tiêu chỉ là controller contract, thay service là hợp lý vì test không tuyên bố kiểm tra nghiệp vụ service.

## 10. Context caching và tính độc lập của test

Spring TestContext Framework cache ApplicationContext giữa các test khi cấu hình tương đương. Điều này giúp giảm thời gian khởi tạo. @SpringJUnitWebConfig tham gia vào cơ chế đó thông qua metadata cấu hình context.

Để test chạy ổn định:

- Không thay đổi bean definition hoặc singleton state dùng chung giữa các test.
- Tạo dữ liệu kiểm thử độc lập.
- Dọn database state bằng transaction hoặc cleanup phù hợp.
- Tránh thay đổi ServletContext toàn cục mà không khôi phục.
- Chỉ dùng @DirtiesContext khi test thực sự làm context không thể tái sử dụng.

Nếu một test cần thay property hoặc bean khác với test còn lại, TestContext có thể tạo context khác do cấu hình khác nhau. Điều này đúng về mặt cô lập nhưng có thể làm suite tốn thời gian. Hãy tổ chức test theo nhóm cấu hình ổn định khi có thể.

### 10.1. Không chia sẻ MockMvc mutable setup tùy tiện

MockMvc thường có thể được tạo một lần từ WebApplicationContext và dùng lại nếu cấu hình bất biến. Nếu test cần filter, default request hoặc custom builder khác nhau, hãy tạo cấu hình riêng hoặc dựng instance riêng cho nhóm test.

Không thay đổi state của một object dùng chung giữa các test chạy song song. Với các test có mutable fake hoặc mock state, hãy tạo mới theo từng test hoặc dùng lifecycle phù hợp.

### 10.2. Transaction trong web test

TestContext có thể quản lý transaction cho test method khi có cấu hình transaction phù hợp. Tuy nhiên, MockMvc và server thật có ranh giới thực thi khác nhau.

Với MockMvc, request thường được xử lý trong cùng tiến trình và thread gọi test. Tùy cách transaction được thiết lập, thao tác persistence có thể tham gia vào transaction test. Với server chạy trên cổng ngẫu nhiên, request được xử lý ở server thread và transaction của test ở client thread không tự động bao trùm transaction của request.

Vì vậy, đừng giả định rằng @Transactional trên test method sẽ rollback mọi thay đổi do HTTP request tới server thật tạo ra. Hãy xác định transaction boundary và kiểm tra dữ liệu sau request theo đúng môi trường.

## 11. Kiểm thử resource và servlet-specific behavior

Một lý do khác để dùng @SpringJUnitWebConfig là kiểm thử hành vi phụ thuộc ServletContext hoặc web resource root.

Ví dụ ứng dụng có thể đọc một tài nguyên từ ServletContext, sử dụng cấu hình servlet hoặc cần một thành phần được khởi tạo trong web context. Khi đó:

1. Chọn resourcePath phù hợp.
2. Đặt tài nguyên kiểm thử trong thư mục tương ứng.
3. Nạp WebApplicationContext bằng @SpringJUnitWebConfig.
4. Inject ServletContext hoặc bean cần kiểm tra.
5. Kiểm tra hành vi qua API web/resource thay vì chỉ assertion context đã tồn tại.

Không nên dùng resourcePath để thay thế classpath resource của Spring. Resource trong classpath, file cấu hình bean và web resource của ServletContext có cách phân giải khác nhau.

Nếu ứng dụng hiện đại phục vụ static resource từ một frontend riêng hoặc từ CDN, test ServletContext resource có thể không còn phản ánh đường đi production. Hãy chỉ kiểm tra web resource khi đó là trách nhiệm thật của ứng dụng Spring.

## 12. Các lỗi thường gặp

### Thiếu cấu hình bean cho controller

@SpringJUnitWebConfig tạo WebApplicationContext nhưng không tự tìm mọi class trong project nếu configuration không khai báo component scan hoặc bean. Khi request trả 404, hãy kiểm tra controller đã được đăng ký và RequestMappingHandlerMapping đã nhận mapping chưa.

### Nhầm resourcePath với locations

locations trỏ đến cấu hình context. resourcePath trỏ đến web application root của ServletContext. Đổi sai thuộc tính có thể khiến Spring không tìm được cấu hình hoặc resource.

### Nghĩ rằng annotation tự tạo MockMvc

@SpringJUnitWebConfig chỉ nạp web context. Test cần tự dựng MockMvc bằng webAppContextSetup hoặc dùng một cấu hình test khác cung cấp client phù hợp.

### Dùng @SpringJUnitWebConfig để kiểm tra Boot auto-configuration

Annotation này thuộc Spring Framework Test và không tự kích hoạt quy trình @SpringBootTest. Nếu mục tiêu là Boot auto-configuration hoặc server startup, hãy dùng annotation của Spring Boot Test.

### Dùng MockMvc để kết luận network/server behavior

MockMvc không kiểm tra port, socket, TLS hoặc servlet container đang chạy. Hãy dùng RANDOM_PORT hoặc server/container thật khi đó là mục tiêu.

### Nạp quá nhiều cấu hình

Một context lớn làm test chậm và khiến lỗi khó khoanh vùng. Chỉ nạp cấu hình cần cho hành vi đang kiểm tra. Nếu test cần toàn bộ ứng dụng, hãy thể hiện rõ đó là integration test.

### Mock nhầm phần cần kiểm tra

Nếu đang kiểm tra exception resolver nhưng thay controller hoặc resolver bằng mock, test có thể bỏ qua phần quan trọng. Hãy giữ thật thành phần thuộc mục tiêu và thay những collaborator nằm ngoài phạm vi.

### Quên dependency web hoặc servlet

Spring MVC cần dependency tương ứng và Servlet API phù hợp. Nếu thiếu classpath, WebApplicationContext hoặc MVC infrastructure có thể không được tạo. Hãy kiểm tra dependency của module test và phiên bản Spring đang dùng.

## 13. Quy trình xây dựng một web test với @SpringJUnitWebConfig

Có thể áp dụng quy trình sau:

**Bước 1 – Xác định mục tiêu.** Làm rõ test cần kiểm tra controller mapping, validation, exception handling, interceptor, resource hay toàn bộ HTTP server.

**Bước 2 – Chọn tầng.** Nếu cần Spring WebApplicationContext và MVC infrastructure nhưng không cần Boot auto-configuration, cân nhắc @SpringJUnitWebConfig. Nếu cần Boot MVC slice, cân nhắc @WebMvcTest. Nếu cần server thật, dùng @SpringBootTest với RANDOM_PORT hoặc môi trường tương đương.

**Bước 3 – Chọn cấu hình context.** Dùng classes cho Java configuration hoặc locations cho XML. Chỉ nạp các bean cần thiết.

**Bước 4 – Chọn resourcePath.** Giữ mặc định nếu phù hợp; đổi khi test cần một web resource root riêng.

**Bước 5 – Inject WebApplicationContext.** Dùng @Autowired để nhận context do TestContext quản lý.

**Bước 6 – Dựng MockMvc.** Dùng MockMvcBuilders.webAppContextSetup nếu muốn kiểm tra MVC configuration đã nạp.

**Bước 7 – Chuẩn bị dữ liệu và collaborator.** Dùng fixture, test bean hoặc mock tại ranh giới phù hợp. Giữ thật thành phần mà test cần chứng minh.

**Bước 8 – Gửi request và assertion.** Kiểm tra status, header, response body, exception mapping và side effect thuộc hợp đồng.

**Bước 9 – Xác nhận giới hạn.** Ghi rõ test có chạy server thật không, có dùng database thật không và collaborator nào được thay thế.

## 14. Ví dụ cấu trúc test hoàn chỉnh

Một cấu trúc đơn giản có thể như sau:

~~~text
src
├── main
│   ├── java
│   │   └── example
│   │       ├── GreetingController.java
│   │       ├── GreetingService.java
│   │       └── WebConfig.java
│   └── webapp
└── test
    ├── java
    │   └── example
    │       ├── WebTestConfig.java
    │       └── GreetingControllerTest.java
    └── resources
        └── spring
            └── test-web-context.xml
~~~

Trong thực tế, test có thể nạp cấu hình production nếu cấu hình đó không kéo theo phụ thuộc không phù hợp. Hoặc test có thể import một cấu hình hẹp để kiểm tra riêng web contract. Điều quan trọng là cấu hình test phải thể hiện rõ những bean và infrastructure nào đang tham gia.

## 15. Đánh giá một @SpringJUnitWebConfig test

Khi đọc hoặc review một test class, hãy tự hỏi:

- Vì sao test cần WebApplicationContext?
- Cấu hình classes hoặc locations có đúng với phạm vi không?
- resourcePath có cần thay đổi không?
- Test có cần MockMvc hay chỉ cần context?
- MockMvc được dựng từ WebApplicationContext hay standalone controller?
- Controller, converter, resolver và interceptor nào đang chạy thật?
- Collaborator nào bị thay thế và lý do là gì?
- Test có đang kiểm tra MVC behavior hay vô tình tuyên bố kiểm tra server/network behavior?
- Test có phụ thuộc state dùng chung hoặc làm bẩn context cache không?
- Assertion có xác nhận hợp đồng quan sát được không?

Một test class có thể rất ngắn nhưng vẫn có giá trị nếu ranh giới rõ. Ngược lại, một test nạp toàn bộ context và gửi request vẫn có thể yếu nếu chỉ xác nhận status mà không kiểm tra kết quả quan trọng.

## Kết luận

@SpringJUnitWebConfig là composed annotation dành cho JUnit Jupiter, kết hợp SpringExtension, ContextConfiguration và WebAppConfiguration để tạo WebApplicationContext cho kiểm thử. Nó hữu ích khi test cần cấu hình web của Spring Framework và muốn sử dụng TestContext injection, lifecycle cùng các khả năng của MVC infrastructure.

Hãy nhớ rằng annotation này không tự tạo MockMvc và không khởi động HTTP server thật. Khi kết hợp với MockMvcBuilders.webAppContextSetup, test có thể kiểm tra mapping, binding, validation, exception handling và cấu hình MVC trong web context mô phỏng. Nếu mục tiêu là Boot auto-configuration, embedded server hoặc network behavior, hãy chọn công cụ Spring Boot Test hoặc môi trường server phù hợp. Việc xác định đúng ranh giới giúp bài kiểm thử tạo ra bằng chứng rõ ràng và tránh nhầm lẫn về những gì nó thực sự đã kiểm tra.
