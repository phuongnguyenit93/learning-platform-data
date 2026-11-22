# MockMvc: standaloneSetup và webAppContextSetup

Khi kiểm thử Spring MVC trong ứng dụng Spring Boot, `MockMvc` cho phép gửi **request mô phỏng** vào hệ thống xử lý MVC và kiểm tra HTTP status, header, response body, exception handler, binding và validation mà **không cần khởi động HTTP server trên cổng mạng thật**. Tuy nhiên, cách tạo `MockMvc` quyết định mức độ cấu hình Spring MVC đang được kiểm chứng.

Hai cách xây dựng cần phân biệt:

- **`MockMvcBuilders.standaloneSetup(controller)`**: cung cấp trực tiếp controller instance, có thể truyền mock/fake service qua constructor; dựng MVC test infrastructure theo cấu hình mặc định và những tùy chỉnh được khai báo bằng code. **Không tải ApplicationContext của ứng dụng**.
- **`MockMvcBuilders.webAppContextSetup(webApplicationContext)`**: lấy các bean và cấu hình MVC từ một `WebApplicationContext` đã được Spring TestContext tải. **Có ApplicationContext**, cho phép kiểm thử những component, interceptor, exception handler, converter và bean wiring được định nghĩa trong *context kiểm thử đang nạp*.

Sự khác biệt không chỉ là thời gian chạy. Một test `standaloneSetup` có thể xanh dù ứng dụng quên đăng ký một `HandlerInterceptor` hoặc `@ControllerAdvice`; test `webAppContextSetup` có thể phát hiện khác biệt nếu cấu hình đó thực sự có trong WebApplicationContext. Ngược lại, test standalone hữu ích để kiểm tra nhanh một controller mà không phụ thuộc vào datasource, component scanning hoặc các auto-configuration không liên quan.

**Nguyên tắc lựa chọn:** dùng **mức cấu hình hẹp nhất vẫn cung cấp đủ bằng chứng** cho hợp đồng cần bảo vệ.

## 1. MockMvc kiểm tra đường đi nào?

Với Spring MVC kiểu servlet, luồng tổng quát khi gọi `mockMvc.perform(...)`:

```text
JUnit Jupiter test
       |
       v
MockMvc.perform(MockHttpServletRequest)
       |
       v
Spring MVC DispatcherServlet (mock servlet environment)
       |
       +-- HandlerMapping / HandlerAdapter
       +-- argument binding / validation / converters
       +-- controller (và các dependency được cấp)
       +-- HandlerExceptionResolver / @ControllerAdvice
       +-- interceptor, filter nếu được đăng ký
       |
       v
MockHttpServletResponse
       |
       v
status(), header(), content(), jsonPath(), ...
```

MockMvc **có sử dụng hạ tầng MVC thật** để xử lý request mô phỏng, chứ không đơn giản gọi trực tiếp Java method trên controller. Tuy vậy, nó **không mở network socket**, không đo được TLS, reverse proxy, sự khác nhau của servlet container ở runtime hay HTTP client/connection thực.

MockMvc dành cho **Spring Web MVC (servlet stack)**. Với controller reactive của **Spring WebFlux**, hãy xem `WebTestClient` và `@WebFluxTest` thay vì suy diễn MockMvc là giải pháp mặc định cho cả hai loại ứng dụng.

Các loại kiểm tra phổ biến:

- `status().isOk()` hoặc `status().isBadRequest()`: trạng thái HTTP mà MVC tạo ra.
- `content().string(...)`: body văn bản.
- `jsonPath("$.id").value(...)`: một trường trong JSON nếu response sử dụng JSON.
- `header().string(...)` hoặc `header().doesNotExist(...)`: giá trị header.
- Kiểm tra request parameter, path variable, media type, exception mapping, HTTP filters và authentication khi được cấu hình.

**Cần phân biệt:** MockMvc có thể kiểm tra tương tác giữa controller và service thật nếu context cung cấp service thật. Nếu bạn gắn mock cho service thì assertion không còn chứng minh service/business/DB hoạt động; nó chỉ chứng minh hợp đồng MVC với phản hồi đã stub.

## 2. Bảng so sánh standaloneSetup và webAppContextSetup

| Tiêu chí | `standaloneSetup(...)` | `webAppContextSetup(...)` |
| --- | --- | --- |
| Controller được cung cấp | Instance chỉ định trực tiếp, thường `new Controller(fakeService)` | Bean controller trong WebApplicationContext |
| Cần tải Spring ApplicationContext? | **Không** | **Có** |
| Có MVC request dispatch? | Có | Có |
| Bean wiring/component scanning thật | Không tự xác minh | Có trong phạm vi context đã nạp |
| `@ControllerAdvice` toàn cục của ứng dụng | Không tự đọc từ context; cần `setControllerAdvice(...)` nếu muốn | Phát hiện các advice bean trong context |
| Interceptor/formatter/converter tùy chỉnh của ứng dụng | Không tự lấy từ WebMvcConfigurer của ứng dụng; thiết lập tương ứng bằng builder | Dùng MVC infrastructure do context cấu hình |
| Servlet filters / Spring Security | Chỉ filters được bổ sung bằng builder/configurer tương ứng | Có thể gắn filter chain từ context; cần kiểm tra cấu hình builder/test |
| Tốc độ/độ cô lập | Thường nhanh, dễ xác định lỗi | Tốn chi phí khởi tạo context, nhưng TestContext có cache |
| Phù hợp | Controller logic, routing, binding cơ bản, debug nhanh | MVC wiring/config, global advice, interceptors, converters, security với context phù hợp |
| Điều không chứng minh được | Ứng dụng đăng ký đúng MVC beans production | HTTP socket thật; cả DB/network nếu các dependency vẫn mock |

**Không đánh đồng `webAppContextSetup` với `@SpringBootTest`.** Một WebApplicationContext có thể được tạo từ `@SpringJUnitWebConfig` nhỏ, `@WebMvcTest` hoặc `@SpringBootTest`. *Builder* quyết định MockMvc lấy MVC infrastructure từ đâu; *test configuration* quyết định **context rộng đến mức nào**.

## 3. Cơ chế setup: ai tạo controller, ai cung cấp hạ tầng MVC?

### 3.1. Standalone setup

Mẫu nhỏ nhất:

```java
GreetingService service = name -> "Hello, " + name + "!";
GreetingController controller = new GreetingController(service);

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .build();
```

Đây là **đoạn nằm trong method của test**, phụ thuộc những class đã được định nghĩa ở phần ví dụ. Ở đây test tự tạo controller và cấp collaborator qua constructor. Builder khởi tạo DispatcherServlet và các MVC components cần thiết cho request handling trong phạm vi test, nhưng **không tải cấu hình MVC của ứng dụng**.

Nếu ứng dụng có global exception handler, interceptor, custom `ObjectMapper` hoặc validator, builder standalone **không tự phát hiện toàn bộ cấu hình production**. Có thể bổ sung có chủ đích:

```java
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(controller)
        .setControllerAdvice(new GreetingAdvice())
        .addInterceptors(customInterceptor)
        .build();
```

Đây là snippet minh họa (`customInterceptor` phải được định nghĩa), không phải toàn bộ file Java chạy độc lập. Trong API của `StandaloneMockMvcBuilder` còn có các cách tùy chỉnh message converters, argument resolvers, conversion service, validator, view resolvers, exception resolvers… theo nhu cầu.

**Trade-off:** cấu hình thủ công giúp test nhanh và tường minh, nhưng nếu production đổi custom MVC configuration mà test quên cập nhật, test standalone có thể tiếp tục pass. Đó không phải bug của MockMvc; đó là **giới hạn của bằng chứng kiểm thử**.

### 3.2. WebApplicationContext setup

Mẫu cần `WebApplicationContext` do Spring TestContext quản lý:

```java
@Autowired
WebApplicationContext webApplicationContext;

@BeforeEach
void initMockMvc() {
    mockMvc = MockMvcBuilders
            .webAppContextSetup(webApplicationContext)
            .build();
}
```

Đoạn này nằm trong **Spring test class**, cần biến `mockMvc` và imports; không chạy độc lập nếu không có annotation/cấu hình tải WebApplicationContext. Builder dùng MVC infrastructure và bean trong context hiện tại.

**Web context rộng hay hẹp tùy cách nạp:**

- `@SpringJUnitWebConfig(TestMvcConfig.class)`: context web được tạo từ configuration chỉ định; phù hợp khi muốn kiểm chứng MVC wiring cụ thể mà không tải toàn bộ Boot.
- `@WebMvcTest(ExampleController.class)`: Spring Boot MVC slice; thường có thể `@Autowired MockMvc` trực tiếp, nhưng bản chất vẫn có WebApplicationContext của slice.
- `@SpringBootTest` + `@AutoConfigureMockMvc`: context rộng hơn, Boot cấu hình MockMvc; phù hợp khi muốn chứng minh nhiều bean production phối hợp cùng HTTP MVC. `@AutoConfigureMockMvc` thuộc Spring Boot test auto-configuration và đường import có thể thay đổi theo phiên bản.

Nếu mục tiêu là route/controller JSON trong web slice, việc inject `MockMvc` sẵn có từ `@WebMvcTest` thường gọn hơn việc tự gọi `webAppContextSetup`. Việc tự tạo builder hữu ích để hiểu nguồn cấu hình hoặc chủ động thêm `MockMvcConfigurer`.

### 3.3. Cùng một URL nhưng khác MVC configuration

Giả sử hệ thống có interceptor thêm header `X-App-Interceptor: enabled` vào mọi request.

- Controller gọi bằng `standaloneSetup` **không tự mang** interceptor từ app config → response sẽ **không có** header đó trừ khi test tự `addInterceptors(...)`.
- Controller đi qua `webAppContextSetup` với context chứa `WebMvcConfigurer.addInterceptors(...)` → header **xuất hiện**.
- Nếu web context được tạo **không chứa** WebMvcConfigurer đang muốn chứng minh, builder context cũng không giúp phát hiện header mong đợi. Phải nạp **đúng cấu hình**.

Ví dụ runnable dưới đây chứng minh sự khác biệt bằng **hai bộ test xanh** với những assertion phù hợp từng ranh giới.

## 4. Ví dụ Java 17+ runnable: controller, advice và interceptor

Ta xây endpoint `GET /greetings?name=Ada` trả text `Hello, Ada!`. Logic định dạng tên nằm trong Java thuần để có thể kiểm tra riêng. Khi tên rỗng hoặc chỉ có whitespace, service ném `IllegalArgumentException`; `@RestControllerAdvice` ánh xạ thành HTTP 400.

Cấu hình WebApplicationContext còn cài một interceptor ghi header `X-App-Interceptor: enabled`. Standalone test không cài interceptor, để làm rõ builder này không tự nạp `WebMvcConfigurer` của ứng dụng.

**Bộ files:**

```text
src/
├── main/java/example/testing/mockmvc/
│   ├── GreetingText.java
│   ├── GreetingTextDemo.java
│   ├── GreetingController.java
│   └── GreetingAdvice.java
└── test/java/example/testing/mockmvc/
    ├── GreetingStandaloneTest.java
    └── GreetingWebContextTest.java
```

### 4.1. Logic Java thuần: GreetingText.java

Tạo `src/main/java/example/testing/mockmvc/GreetingText.java`:

```java
package example.testing.mockmvc;

public final class GreetingText {
    private GreetingText() {
    }

    public static String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Hello, " + name.strip() + "!";
    }
}
```

`String.isBlank()` và `strip()` có từ Java 11; project dùng Java 17+. Chúng phân biệt chuỗi không có ký tự hữu ích với chuỗi có whitespace xung quanh. Bài này cố ý giữ logic thuần nhỏ, tránh phụ thuộc database/remote API để tập trung vào MVC setup.

### 4.2. Controller thật: GreetingController.java

Tạo `src/main/java/example/testing/mockmvc/GreetingController.java`:

```java
package example.testing.mockmvc;

import java.util.Objects;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = Objects.requireNonNull(
                service, "service");
    }

    @GetMapping(
            path = "/greetings",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String greet(@RequestParam("name") String name) {
        return service.greet(name);
    }
}

@FunctionalInterface
interface GreetingService {
    String greet(String name);
}
```

File Java có một top-level type `public` là `GreetingController`; interface `GreetingService` có phạm vi package-private. Hai test đặt trong package `example.testing.mockmvc` nên dùng được interface này. Nếu project lớn cần adapter ở package khác, tách interface thành file `public` thích hợp.

Không gắn `@Service` lên `GreetingService` vì nó chỉ là interface. Trong standalone test, ta tự truyền một lambda. Trong web context test, Spring tạo bean `GreetingService` bằng `@Bean`. **Cùng một controller production, hai cách cung cấp collaborator**, nhờ vậy test thực sự so sánh hai builder.

### 4.3. Exception handler: GreetingAdvice.java

Tạo `src/main/java/example/testing/mockmvc/GreetingAdvice.java`:

```java
package example.testing.mockmvc;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GreetingAdvice {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> badName(
            IllegalArgumentException exception) {
        return ResponseEntity.badRequest()
                .contentType(MediaType.TEXT_PLAIN)
                .body(exception.getMessage());
    }
}
```

`GreetingAdvice` là class thật có annotation Spring. **Trong standalone mode**, test phải đăng ký tường minh bằng `setControllerAdvice(new GreetingAdvice())`. **Trong web context mode**, test đăng ký nó như Spring bean để MVC exception resolver phát hiện.

Không nên nghĩ mọi exception mặc định thành HTTP 400. Nếu `IllegalArgumentException` từ service không được `@ExceptionHandler`/cơ chế xử lý phù hợp tiếp nhận, nó có thể nổi lên làm `MockMvc.perform(...)` ném exception, hoặc được xử lý khác theo cấu hình. Test cần kiểm tra chính exception mapping muốn bảo vệ.

### 4.4. Standalone test đầy đủ

Tạo `src/test/java/example/testing/mockmvc/GreetingStandaloneTest.java`:

```java
package example.testing.mockmvc;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GreetingStandaloneTest {
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        GreetingService service = GreetingText::greet;
        GreetingController controller =
                new GreetingController(service);

        mvc = MockMvcBuilders
                .standaloneSetup(controller)
                .setControllerAdvice(new GreetingAdvice())
                .build();
    }

    @Test
    void returnsTextWithoutApplicationInterceptor()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " Ada "))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"))
                .andExpect(header()
                        .doesNotExist("X-App-Interceptor"));
    }

    @Test
    void mapsBlankNameWithExplicitlyRegisteredAdvice()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " "))
                .andExpect(status().isBadRequest())
                .andExpect(content()
                        .string("name must not be blank"));
    }
}
```

**Hai điểm kiểm thử:**

1. Controller thật và `GreetingText` thật chạy qua MockMvc, trả nội dung đã trim như yêu cầu; header của interceptor **không tồn tại** vì test chưa đăng ký interceptor đó.
2. Với tham số là một dấu cách, logic ném `IllegalArgumentException`. Vì test đã `setControllerAdvice(...)`, MVC chuyển exception thành **400 + text message**. Điều này chứng minh handler được đăng ký *trong setup riêng của test*, **không chứng minh production có advice bean**.

Test này **không sử dụng** `@SpringBootTest`, `@WebMvcTest`, `@SpringJUnitWebConfig` hay `@Autowired`. Không có Spring ApplicationContext nhưng vẫn dùng Spring MVC test infrastructure.

### 4.5. WebApplicationContext test đầy đủ

Tạo `src/test/java/example/testing/mockmvc/GreetingWebContextTest.java`:

```java
package example.testing.mockmvc;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.web.SpringJUnitWebConfig;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringJUnitWebConfig(GreetingWebContextTest.WebConfig.class)
class GreetingWebContextTest {

    @Autowired
    private WebApplicationContext webApplicationContext;

    private MockMvc mvc;

    @BeforeEach
    void setup() {
        mvc = MockMvcBuilders
                .webAppContextSetup(webApplicationContext)
                .build();
    }

    @Test
    void appliesInterceptorDefinedInWebContext()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " Ada "))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello, Ada!"))
                .andExpect(header()
                        .string("X-App-Interceptor", "enabled"));
    }

    @Test
    void discoversAdviceBeanAndAppliesInterceptor()
            throws Exception {
        mvc.perform(get("/greetings")
                        .param("name", " "))
                .andExpect(status().isBadRequest())
                .andExpect(content()
                        .string("name must not be blank"))
                .andExpect(header()
                        .string("X-App-Interceptor", "enabled"));
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebMvc
    static class WebConfig implements WebMvcConfigurer {

        @Bean
        GreetingService greetingService() {
            return GreetingText::greet;
        }

        @Bean
        GreetingController greetingController(
                GreetingService service) {
            return new GreetingController(service);
        }

        @Bean
        GreetingAdvice greetingAdvice() {
            return new GreetingAdvice();
        }

        @Override
        public void addInterceptors(
                InterceptorRegistry registry) {
            registry.addInterceptor(new HandlerInterceptor() {
                @Override
                public boolean preHandle(
                        HttpServletRequest request,
                        HttpServletResponse response,
                        Object handler) {
                    response.setHeader(
                            "X-App-Interceptor", "enabled");
                    return true;
                }
            });
        }
    }
}
```

**Tại sao đoạn này dùng được với Spring Framework 6.x / Spring Boot 3.x?**

- `@SpringJUnitWebConfig` kết hợp Spring TestContext với JUnit Jupiter và cấu hình web application context.
- `@EnableWebMvc` đưa MVC infrastructure vào context thử nghiệm. `WebConfig implements WebMvcConfigurer` để cấu hình interceptor.
- `@Bean GreetingController` cung cấp **controller bean thật**; `@Bean GreetingAdvice` cung cấp **global exception advice bean**; `@Bean GreetingService` nối service vào controller.
- `MockMvcBuilders.webAppContextSetup(webApplicationContext)` lấy chính cấu hình MVC của context đó thay vì tự thiết lập một controller rời.
- `HandlerInterceptor.preHandle(...)` thêm header vào response trước khi controller xử lý. Khi lỗi blank name được advice chuyển thành HTTP 400, interceptor vẫn đã chạy, nên header vẫn xuất hiện.

Ở đây import servlet sử dụng namespace **`jakarta.servlet.*`** (Spring Framework 6 / Boot 3+) chứ không phải `javax.servlet.*` của các hệ Spring cũ. Nếu đang dùng Spring Framework 7 / Spring Boot 4, ý nghĩa builder vẫn vậy nhưng cần giữ bộ dependencies/Jakarta Servlet và plugin test tương thích với phiên bản đang sử dụng.

**Lưu ý quan trọng:** context trong ví dụ chỉ nạp `WebConfig` do test khai báo. Nó kiểm chứng **cấu hình của WebConfig này**, không tự chứng minh cả ứng dụng production có cùng interceptor, advice và service wiring. Nếu muốn kiểm tra config production, nạp đúng config/profile ứng dụng bằng test slice hoặc full integration thích hợp.

### 4.6. Cấu hình dependencies và chạy test

Với project **Spring Boot 3.4/3.5 + Java 17+** đã có plugin và dependency management, phần liên quan trong `build.gradle` (Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình bổ sung**, không phải `build.gradle` độc lập. `spring-boot-starter-web` mang Spring MVC và servlet APIs phù hợp; starter test trong cấu hình thông dụng cung cấp JUnit Jupiter cùng Spring Test.

Chạy riêng hai test classes:

```bash
./gradlew test --tests example.testing.mockmvc.GreetingStandaloneTest
./gradlew test --tests example.testing.mockmvc.GreetingWebContextTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.mockmvc.GreetingStandaloneTest"
.\gradlew.bat test --tests "example.testing.mockmvc.GreetingWebContextTest"
```

**Kỳ vọng:** mỗi class có **2 test methods**, tổng **4 tests** đều pass nếu project và dependencies được cấu hình đúng. Test standalone không khởi tạo ApplicationContext; web-context tests khởi tạo một context web nhỏ. Không khẳng định stdout Gradle cố định vì runner, plugins và cấu hình logging có thể hiển thị khác nhau.

Nếu `GreetingWebContextTest` báo không tìm thấy bean, hãy kiểm tra `@SpringJUnitWebConfig(WebConfig.class)`, `@Bean` và package type. Nếu context báo thiếu MVC infrastructure, kiểm tra `@EnableWebMvc`. Nếu test status/header sai, đối chiếu lớp interceptor/advice thực tế được context nạp.

### 4.7. Chạy logic Java thuần bằng javac/java

Ví dụ này có một phần không phụ thuộc Spring: `GreetingText`. Tạo `src/main/java/example/testing/mockmvc/GreetingTextDemo.java`:

```java
package example.testing.mockmvc;

public class GreetingTextDemo {
    public static void main(String[] args) {
        System.out.println(GreetingText.greet(" Ada "));

        try {
            GreetingText.greet(" ");
        } catch (IllegalArgumentException e) {
            System.out.println(e.getMessage());
        }
    }
}
```

Biên dịch và chạy ở thư mục gốc project (cần JDK 17+):

```bash
javac -d out src/main/java/example/testing/mockmvc/GreetingText.java src/main/java/example/testing/mockmvc/GreetingTextDemo.java
java -cp out example.testing.mockmvc.GreetingTextDemo
```

**Stdout chính xác:**

```text
Hello, Ada!
name must not be blank
```

Đây chỉ là **demo Java thuần**, không kiểm tra MockMvc. Những hành vi `standaloneSetup` và `webAppContextSetup` được kiểm chứng bằng Gradle/JUnit + Spring Test ở mục trước. Các file `GreetingController.java`/`GreetingAdvice.java` không thể biên dịch với `javac` trần nếu thiếu Spring dependencies trên classpath.

## 5. Khi nào standaloneSetup là lựa chọn tốt?

### 5.1. Test controller tập trung và nhanh

Nếu mục tiêu là:

- Controller nhận `@RequestParam` và chọn đúng argument để gọi service.
- HTTP method/path mapping nội bộ của controller.
- Status/body cho các tình huống được `@ExceptionHandler` chỉ định trong test.
- Request binding đơn giản, path variable, query string hoặc headers.
- Kiểm tra output controller với collaborator đã stub.

Thì standalone có thể giảm thời gian bootstrap, không yêu cầu app configuration và làm test dễ đọc. Controller được dựng bằng constructor injection, thường dùng `Mockito.mock(...)` hoặc fake, không nhất thiết cần Spring dependency injection.

Ví dụ với Mockito trong **một test method minh họa**:

```java
GreetingService service =
        org.mockito.Mockito.mock(GreetingService.class);
org.mockito.Mockito.when(service.greet("Ada"))
        .thenReturn("Hello, Ada!");

MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new GreetingController(service))
        .build();

mvc.perform(get("/greetings").param("name", "Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello, Ada!"));

org.mockito.Mockito.verify(service).greet("Ada");
```

Đoạn trên giả định test method có `throws Exception` và đã static import request/assertion builders. Nó không đòi Spring context. Tuy nhiên, đừng kết luận service production hoạt động: lời gọi `service.greet` là Mockito stub.

### 5.2. Cấu hình rõ những phần cần thiết

Trong standalone, có thể đăng ký:

- `setControllerAdvice(...)` cho controller advice/cách xử lý lỗi.
- `addInterceptors(...)` cho một hoặc nhiều MVC interceptors.
- `addFilters(...)` cho servlet filters cần thiết.
- `setMessageConverters(...)` cho chuyển đổi request/response theo cấu hình cụ thể.
- `setValidator(...)` cho validation khi cần kiểm soát chính xác behavior.
- Cấu hình argument resolvers, conversion service, handler exception resolvers, formatters hoặc view resolvers theo API của builder.

Nhưng **càng cấu hình thủ công nhiều, càng có rủi ro khác production**. Nếu bài test chính là xác minh các tùy chỉnh MVC đó đã được đăng ký/áp dụng trong ứng dụng, nên sử dụng WebApplicationContext thay vì sao chép config vào standalone builder rồi test chính bản sao.

### 5.3. Các bằng chứng standalone không cung cấp

- Không phát hiện `@ControllerAdvice` hoặc `WebMvcConfigurer` của production nếu bạn không cài chúng.
- Không chứng minh bean discovery, qualifiers, profiles hay auto-configuration production.
- Không chứng minh Spring Security filter chain nếu bạn chưa đăng ký nó.
- Không chứng minh transaction proxy, repository, DB hoặc HTTP client adapter chạy thật khi collaborator là mock.
- Không chứng minh request đi qua servlet container/network thực tế.

Standalone **không sai** khi thiếu những điều này; nó đang bảo vệ một hợp đồng hẹp hơn.

## 6. Khi nào webAppContextSetup đáng giá hơn?

### 6.1. Khi cần xác minh MVC configuration có trong context

Hãy dùng context setup khi câu hỏi là:

- Ứng dụng có tự phát hiện global `@RestControllerAdvice` không?
- `WebMvcConfigurer.addInterceptors(...)` có thực sự được dùng không?
- Custom converters/formatters/argument resolvers, validation configuration, locale/timezone hay exception resolvers có hoạt động như cấu hình?
- Controller đang nhận đúng service bean, qualifiers và profile không?
- URL mappings của nhiều controllers có xung đột không?
- Cấu hình Spring Security filter chain, authorization/CSRF ở MVC boundary có đúng không?

Builder web context lấy bean và MVC config từ TestContext **được nạp**. Để phát hiện lỗi production config, phải bảo đảm context thử nghiệm nạp config production tương ứng, không chỉ một test `WebConfig` đơn giản tự viết.

### 6.2. Không nhất thiết tải full Spring Boot context

Ví dụ trên dùng `@SpringJUnitWebConfig(WebConfig.class)` và `@EnableWebMvc` để có một web context tối thiểu. Đây là một **integration test hẹp của MVC configuration**, không có DB hoặc bean auto-config không cần thiết.

Trong Spring Boot, `@WebMvcTest` thường là lựa chọn tiện hơn cho web slice. Nó cấu hình MVC test infrastructure của Boot và cho phép inject `MockMvc`; controller collaborator ngoài slice có thể được cung cấp qua `@MockitoBean`. Nhưng slice có thể **không chứa** mọi component service/DB/config ngoài MVC, nên vẫn phải giới hạn kết luận.

`@SpringBootTest` + `@AutoConfigureMockMvc` phù hợp khi muốn đưa nhiều bean ứng dụng vào cùng đường đi request, nhưng chi phí cao hơn và có thể cần hạ tầng bổ sung. Nếu mục tiêu vẫn chỉ là “controller map HTTP status đúng”, full context có thể quá rộng.

### 6.3. So sánh thực nghiệm với một interceptor

Hai test ở mục 4 đưa ra bằng chứng khác nhau:

| Test | Controller/service | Advice | Interceptor |
| --- | --- | --- | --- |
| `GreetingStandaloneTest` | Tạo bằng Java `new` / method reference | Đăng ký bằng `setControllerAdvice` | **Không** cài → header không có |
| `GreetingWebContextTest` | Bean từ WebApplicationContext | Bean từ context, MVC phát hiện | `WebMvcConfigurer` cài → header `enabled` |

Cả hai đều đúng với **setup của mình**. Nếu một test standalone bắt đầu kiểm tra header `X-App-Interceptor` nhưng không `addInterceptors`, nó sẽ fail vì test setup chưa có interceptor, **không chứng minh cấu hình production sai**. Ngược lại, nếu production bắt buộc có header nhưng bạn chỉ chạy standalone, việc test xanh mà header không có là **lỗ hổng phạm vi test**.

## 7. MockMvc, Spring Security và servlet filters

Spring Security không tự có mặt trong một `standaloneSetup` tối giản, kể cả controller source được annotate bảo mật. Method security và servlet security filter cũng là hai cơ chế khác nhau; cần chọn test boundary đúng.

Để tích hợp Spring Security với `webAppContextSetup` có context chứa filter chain tương ứng và dependency `spring-security-test`, mẫu tài liệu Spring Security là:

```java
mockMvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .apply(springSecurity())
        .build();
```

**Đây là snippet trong Spring Security test, không phải phần của test runnable ở mục 4.** Nó cần static import `org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity`, context có security filter chain và Spring Security test dependencies. `springSecurity()` thêm Spring Security `FilterChainProxy` và test SecurityContext integration thích hợp.

Nếu dùng `@WebMvcTest`/`@SpringBootTest` cùng `@AutoConfigureMockMvc`, Boot có thể đã cấu hình filters tùy thuộc cài đặt. **Không tự thêm cùng một filter chain nhiều lần** khi đã được gắn bởi cơ chế khác; kiểm tra hiện trạng config và loại test trước khi tùy chỉnh builder.

Khi kiểm tra HTTP authorization hoặc CSRF, gửi request có/cố ý không có authentication/CSRF token và assert 401/403/response theo cấu hình thực. Một test standalone không cài filters mà nhận 200 **không có nghĩa endpoint an toàn trước request không được xác thực**. Ngược lại, một test trả 403 do CSRF không tự chứng minh method security đúng.

`MockMvc` chỉ thực hiện request theo mock servlet infrastructure, nên nếu hợp đồng quan tâm network stack, TLS termination, reverse proxy headers, connection timeout hoặc deployed servlet container, cần integration/end-to-end test qua HTTP thật (chẳng hạn `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng client phù hợp).

## 8. Exception handling, validation và JSON: các điểm dễ lệch

### 8.1. @ControllerAdvice không tự xuất hiện trong standalone

Nếu controller ném exception và production xử lý bằng `@RestControllerAdvice`, standalone test phải bổ sung advice khi muốn test HTTP error response tương ứng. Nếu bạn *tự tạo* advice trong test, điều đó chỉ chứng minh bản advice ấy hoạt động, **không chứng minh Spring production đã scan và đăng ký nó**.

Web context test có thể xác minh advice bean thực sự được Spring MVC resolver phát hiện. Khi advice bị giới hạn theo package hoặc assignableTypes, phải nạp đúng controller/advice để kiểm tra rule chọn advice.

### 8.2. @Valid/@Validated phụ thuộc validation infrastructure

Các annotation Bean Validation có thể hoạt động trong một MVC setup có provider phù hợp trên classpath, nhưng custom `Validator`, group sequence, message source hay conversion rules của ứng dụng **không tự được copy** sang standalone test.

Nếu mục tiêu là custom validation đã được đăng ký, dùng web context phù hợp hoặc cấu hình standalone tương đương một cách tường minh. Trong Spring Boot 3, Bean Validation thường cần dependency riêng như `spring-boot-starter-validation`; không nên mặc định cứ có Spring Web MVC thì mọi constraint annotations đã được thực thi.

### 8.3. Message converters và ObjectMapper

HTTP JSON không chỉ phụ thuộc code controller:

- Jackson module registration, naming strategy, date/time serialization, unknown-property handling.
- Request body conversion, `Content-Type` và `Accept` negotiation.
- Cách trả HTTP 400 cho lỗi parse/binding.
- Custom converters hoặc argument resolvers.

Standalone builder dùng những defaults dựa trên classpath và thiết lập cụ thể; nó **không tự dùng `ObjectMapper` bean do Spring Boot ứng dụng custom**. Nếu JSON contract là rủi ro quan trọng, web context hoặc JSON slice test với cấu hình thật có giá trị hơn. Đừng dùng serializer tự tạo trong test rồi kết luận production ObjectMapper đã đúng.

### 8.4. Servlet Filter khác HandlerInterceptor

- **Filter** thuộc servlet chain, có thể chạy trước khi request vào Spring MVC `DispatcherServlet`; thường dùng cho security, tracing, request wrappers.
- **HandlerInterceptor** thuộc Spring MVC handler execution chain, được cấu hình qua `WebMvcConfigurer.addInterceptors` hoặc cơ chế MVC tương ứng.
- `@ControllerAdvice` thuộc exception handling của MVC, không tự thay thế mọi filter-level exception mapping.

Đừng nhầm gọi `addInterceptors(...)` với thêm `springSecurityFilterChain`. Kiểm chứng đúng layer: HTTP security filters thường cần filter chain từ context; header do MVC interceptor có thể được test bằng setup của bài.

## 9. Một số chức năng MockMvc dùng chung cho hai builder

Cả standalone và web context setup đều có thể dùng cùng API request/assertion:

```java
mvc.perform(get("/greetings").param("name", "Ada"))
        .andExpect(status().isOk())
        .andExpect(content().string("Hello, Ada!"));
```

Đây là snippet trong test method có `mvc` và imports phù hợp.

**Các kỹ thuật hữu ích:**

- `perform(get("/path").param("key", "value"))` mô phỏng Servlet request parameter. Giá trị ở `param(...)` đã là chuỗi được cung cấp cho parameter API, **khác** trường hợp tự tạo query string rồi đi qua URL decoding.
- `perform(post("/path").contentType(MediaType.APPLICATION_JSON).content(json))` mô phỏng body JSON khi endpoint yêu cầu; response phải có converter tương ứng trong setup.
- `andExpect(status().isOk())`, `andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))`, `andExpect(jsonPath("$.name").value("..."))` kiểm tra response quan sát được.
- `andDo(print())` hỗ trợ chẩn đoán request/response khi test fail; không nên in dữ liệu nhạy cảm ở CI logs.
- `defaultRequest(...)` hoặc `alwaysExpect(...)` có thể thiết lập mặc định cho nhiều test qua builder khi phù hợp. Đừng để default che mất trường hợp riêng cần test.

**Async controller:** với controller trả `Callable`, `DeferredResult` hoặc cơ chế async servlet tương ứng, có thể cần kiểm tra `request().asyncStarted()` và sau đó `asyncDispatch(...)` để assert response hoàn chỉnh. Dạng setup standalone/context không làm mọi async test tự chờ hoàn tất nếu test chưa thực hiện bước dispatch cần thiết.

**Multipart:** MockMvc cung cấp request builder dành cho file upload, nhưng nó mô phỏng multipart request; không chứng minh streaming/network upload qua servlet container thật.

**Views/templates:** các controller trả view name có thể cần view resolver; standalone sẽ cần cấu hình tương ứng, còn web context dùng view resolvers đã nạp. Nếu chỉ test status/string API như ví dụ, không cần cấu hình template engine.

## 10. Hiệu năng, độ ổn định và quản lý context

**Standalone setup** không khởi tạo ApplicationContext, nên thường có feedback nhanh, dễ tạo mỗi controller từ constructor và không bị ảnh hưởng bởi datasource/cache/server ngoại vi. Tuy nhiên, lỗi configuration của production sẽ bị bỏ qua trừ khi có test ở mức rộng hơn.

**Web context setup** dùng Spring TestContext để tải cấu hình. Context có thể được **cache và tái sử dụng** giữa các test classes có cùng cấu hình nhằm giảm thời gian khởi tạo. Nhưng cache context không tự dọn:

- Database rows.
- Singleton mutable fields.
- Shared caches.
- Static state hoặc external resources.
- Authentication/security context nếu test cấu hình sai lifecycle.

Dùng fixture/cleanup độc lập; tránh phụ thuộc thứ tự test. `@DirtiesContext` có thể buộc reload context khi thật sự cần, nhưng không nên là cách khắc phục mặc định khi test không quản lý dữ liệu.

**Điều quan trọng:** `MockMvcBuilders.webAppContextSetup(wac)` xây MockMvc từ context **đã có**; chi phí khởi tạo ApplicationContext chủ yếu do Spring TestContext trước đó, không phải vì chính lời gọi builder lúc `@BeforeEach`. Vì vậy có thể reuse context nhưng vẫn tạo một MockMvc instance mới theo test setup.

Nếu một MVC test cần real DB, cache hay HTTP client, hãy cân nhắc tách test theo rủi ro. Không nên vô tình biến test header/status thành full integration test tốn kém chỉ vì controller gọi service có nhiều dependency.

## 11. Những lỗi thường gặp

**1. Dùng standalone rồi suy ra production MVC config đúng.** Standalone không nạp `@ControllerAdvice`/interceptor/configuration của ứng dụng. Nó chỉ chứng minh controller với setup đã đăng ký trong test.

**2. Tưởng standalone chỉ gọi controller method trực tiếp.** Nó vẫn chạy DispatcherServlet và MVC request infrastructure trong môi trường mock; khác với `controller.greet(...)` thuần Java.

**3. Tưởng webAppContextSetup luôn là full Spring Boot.** Nó chỉ dùng WebApplicationContext được nạp. Nếu context chỉ chứa một cấu hình test nhỏ, kết luận cũng hẹp tương ứng.

**4. Quên `@ControllerAdvice` trong standalone.** Test error path có thể ném exception thay vì trả 400/JSON như production. Gắn `setControllerAdvice(...)` khi cần kiểm tra contract error mapping.

**5. Dùng controller `new` với `webAppContextSetup` rồi tưởng builder lấy instance đó.** Context builder lấy controller **bean** từ context. Muốn test instance thủ công, dùng standalone builder.

**6. Quên `@EnableWebMvc` hoặc không nạp MVC configuration trong custom WebApplicationContext.** Test có thể không có mappings/interceptors đúng kỳ vọng. Với `@SpringBootTest`/`@WebMvcTest`, Boot tự cấu hình MVC theo các quy tắc khác; không thêm `@EnableWebMvc` vào production config bừa bãi vì nó có thể làm thay đổi Boot MVC auto-configuration.

**7. Mock service rồi kết luận service hoặc DB đã chạy.** `@MockitoBean`/Mockito stubbing không chứng minh logic/DB thật. Giữ SUT phù hợp thật ở ranh giới cần kiểm tra.

**8. Security filter chain không được gắn.** Test pass 200 không chứng minh endpoint được bảo vệ. Kiểm tra builder/configurer/filter chain khi hợp đồng là security.

**9. Tắt filters để test pass rồi tuyên bố đã kiểm chứng authentication/CSRF.** Hãy kiểm tra security ở tầng có filter chain đúng, không thay đổi setup để bỏ qua hành vi cần test.

**10. Dùng custom ObjectMapper/validator trong test khác production.** Cùng controller code vẫn có thể serialize hoặc validate khác nhau. Test có context/config phù hợp giúp bắt sự khác biệt.

**11. Dùng MockMvc để chứng minh network/TLS thực.** Mock servlet environment không có cổng HTTP thật. Dùng integration test qua HTTP client khi cần.

**12. Test header của interceptor ở standalone nhưng không cài interceptor.** Đó là lỗi setup đối với mục tiêu đã chọn, không phải bằng chứng bean production thiếu interceptor.

**13. Không quản lý dữ liệu/beans dùng chung trong context.** Context cache có thể giữ mutable singleton, DB/cache; test fail theo thứ tự. Dọn fixture đúng boundary và cách ly khi chạy song song.

**14. Gộp mọi test thành full-context để khỏi suy nghĩ scope.** Điều này làm suite chậm và che khu vực lỗi. Giữ test standalone cho logic controller hẹp, context tests cho MVC config, full integration cho các flow thực sự cần.

## 12. Checklist lựa chọn MockMvc setup

Trước khi viết:

- Hợp đồng cần chứng minh là **logic controller** hay **MVC configuration được Spring nạp**?
- Có cần global `@ControllerAdvice`, `WebMvcConfigurer`, converters, custom validator, security filter hoặc bean wiring **thực** không?
- Nếu dùng standalone, đã đăng ký tường minh những MVC components cần kiểm tra chưa?
- Nếu dùng web context, test đang nạp cấu hình nào: `@SpringJUnitWebConfig` tối thiểu, `@WebMvcTest` slice hay `@SpringBootTest`?
- Controller và service là instance thật hay mock? Kết luận từ test đã giới hạn đúng phạm vi chưa?
- MockMvc đã có security filters chưa, hay cần `springSecurity()` và đúng dependencies?
- Mục tiêu có cần HTTP server/port thật không? Nếu có, MockMvc chưa đủ.

Khi chạy:

- Request có đúng method, path, `Content-Type`, `Accept` và params cần thiết?
- Response assertion có kiểm tra **status + body/header** thay vì chỉ một giá trị được stub?
- Với error case, có xác minh MVC handler/advice của setup đang dùng?
- Với custom interceptor, có assertion chứng minh interceptor thật đã chạy?
- Khi test fail, nguyên nhân do controller logic, test setup, MVC configuration hay dependency ngoài scope?

Sau khi test xanh:

- Có một test dùng context để bảo vệ những cấu hình quan trọng mà standalone không thể bảo vệ không?
- Test có đang suy diễn DB/transaction/security/network từ một MockMvc setup thiếu các phần ấy không?
- Context/fixture có cô lập để test không phụ thuộc thứ tự và không gây flakiness không?
- Nếu thay đổi controller advice, interceptor hoặc converter production, bộ test nào sẽ đỏ? Nếu không có test nào, cần thêm bằng chứng ở context phù hợp.

**Ghi nhớ:** `standaloneSetup` cho **feedback nhanh với controller và cấu hình MVC được khai báo trực tiếp trong test**. `webAppContextSetup` cho **bằng chứng mạnh hơn về MVC wiring và configuration của WebApplicationContext đang nạp**. Cả hai đều chạy request trên mock servlet infrastructure, **không mở HTTP server thực**. Chọn builder theo điều cần chứng minh và chọn context theo phạm vi cấu hình mà bạn thực sự muốn bảo vệ.

## 13. Tài liệu tham khảo

- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): sự khác nhau giữa standalone và WebApplicationContext.
- [Spring Framework — MockMvc Performing Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): cách tạo request, tham số và thiết lập request mặc định.
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `springSecurity()` và filter chain trong MVC tests.
