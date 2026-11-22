# ServerWebExchange, Principal và Locale trong tham số handler WebFlux

## 1. Bài toán và mục tiêu

Trong Spring WebFlux, một method xử lý HTTP (handler method) có thể nhận trực tiếp nhiều kiểu tham số do framework phân giải từ request hiện tại. Ba tham số quan trọng là:

- **ServerWebExchange**: cung cấp toàn bộ ngữ cảnh của một lần trao đổi HTTP, gồm request, response, attributes, session, principal và locale context.
- **Principal**: đại diện cho danh tính người dùng đã được xác thực nếu có. Việc phân giải có thể bất đồng bộ; kiểu reactive như **Mono<Principal>** giúp ghép quá trình đó vào pipeline.
- **Locale**: ngôn ngữ/vùng hiện hành của request, thường được xác định từ header **Accept-Language** thông qua **LocaleContextResolver**.

Ví dụ một endpoint cần trả thông tin người dùng hiện tại, đường dẫn request và ngôn ngữ để chọn nội dung phù hợp. Ta có thể khai báo cả ba ngay trong chữ ký method:

~~~java
@GetMapping("/profile/context")
public Mono<ProfileContext> context(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    return principal.map(user ->
        new ProfileContext(
            user.getName(),
            exchange.getRequest().getURI().getPath(),
            locale.toLanguageTag()
        )
    );
}
~~~

Đây là snippet minh họa; kiểu **ProfileContext** được định nghĩa ở ứng dụng. Spring tự phân giải các tham số được hỗ trợ khi gọi handler. Ta không cần tự lấy HttpServletRequest hoặc dùng ThreadLocal.

Sau bài học, bạn có thể:

- Phân biệt ServerWebExchange với ServerHttpRequest và ServerHttpResponse.
- Đọc request, response, attributes, session, form data và multipart theo cách reactive.
- Hiểu Principal được phân giải bất đồng bộ, có thể vắng mặt và liên hệ với Spring Security.
- Hiểu Locale được chọn qua LocaleContextResolver và header Accept-Language.
- Viết chữ ký controller đúng, phối hợp các tham số với Mono/Flux mà không block.
- Tạo cấu hình locale, bảo vệ endpoint bằng WebFlux Security và kiểm thử bằng WebTestClient.
- Tránh các lỗi như đọc body nhiều lần, dùng sai LocaleResolver của Spring MVC hoặc nhầm Principal với dữ liệu do client gửi.

## 2. Spring phân giải tham số handler như thế nào?

Trong controller dùng **@RequestMapping**, **@GetMapping**, **@PostMapping** và các annotation liên quan, Spring WebFlux có cơ chế **HandlerMethodArgumentResolver**. Cơ chế này nhận biết kiểu tham số và annotation, sau đó tạo giá trị tương ứng từ **ServerWebExchange**.

Một số resolver liên quan trực tiếp:

| Resolver | Tham số được hỗ trợ | Cách hoạt động |
| --- | --- | --- |
| **ServerWebExchangeMethodArgumentResolver** | ServerWebExchange, ServerHttpRequest, ServerHttpResponse, HttpMethod, Locale, TimeZone, ZoneId, URI builder | Đọc trực tiếp dữ liệu từ exchange |
| **PrincipalMethodArgumentResolver** | java.security.Principal và reactive wrapper tương thích | Lấy principal từ exchange theo cách bất đồng bộ |
| **RequestParamMethodArgumentResolver** | @RequestParam và simple type phù hợp | Chuyển query parameter sang kiểu Java |
| **RequestHeaderMethodArgumentResolver** | @RequestHeader | Đọc header và chuyển kiểu |
| **RequestBodyMethodArgumentResolver** | @RequestBody | Dùng HttpMessageReader/codec để đọc body |
| **ModelAttributeMethodArgumentResolver** | @ModelAttribute hoặc object phù hợp | Bind dữ liệu request vào object |

Khi framework gọi handler, nó phân giải tham số trước rồi mới invoke method. Vì thế chữ ký method là một phần của contract HTTP; kiểu tham số và annotation quyết định nguồn dữ liệu.

### 2.1. Tham số nào là giá trị trực tiếp, tham số nào nên reactive?

- **ServerWebExchange** được truyền trực tiếp như một object.
- **ServerHttpRequest** và **ServerHttpResponse** cũng được truyền trực tiếp.
- **Locale**, **TimeZone**, **ZoneId** là giá trị đồng bộ, được phân giải từ request context.
- **Principal** có thể cần chờ quá trình xác thực hoặc tra cứu security context; WebFlux hỗ trợ dạng reactive như **Mono<Principal>**.
- Các tham số đọc body, session hoặc form data có thể sử dụng reactive type vì việc phân giải có thể liên quan I/O hoặc parsing.

Không bọc mọi tham số trong Mono chỉ vì controller là reactive. Hãy sử dụng reactive wrapper tại những điểm API hỗ trợ và nơi thao tác thực sự bất đồng bộ.

### 2.2. Ví dụ chữ ký handler tổng hợp

~~~java
@GetMapping("/request-info")
public Mono<Map<String, String>> requestInfo(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale,
    HttpMethod method
) {
    return principal.map(user -> Map.of(
        "user", user.getName(),
        "path", exchange.getRequest().getURI().getPath(),
        "method", method.name(),
        "locale", locale.toLanguageTag()
    ));
}
~~~

Các kiểu tham số ở đây được phân giải bởi framework. Method trả **Mono** để chờ principal rồi mới tạo response. Không gọi **block()** để lấy user trong handler.

## 3. ServerWebExchange là gì?

**ServerWebExchange** nằm trong package **org.springframework.web.server**. Nó đại diện cho toàn bộ một lần trao đổi request/response ở tầng WebFlux, tương tự một context object bao bọc request và response.

Một số phương thức thường dùng:

| Phương thức | Kết quả | Mục đích |
| --- | --- | --- |
| **getRequest()** | ServerHttpRequest | Method, URI, headers, cookies và body |
| **getResponse()** | ServerHttpResponse | Status, response headers, ghi body |
| **getAttributes()** | Map<String,Object> | Dữ liệu tạm gắn với request hiện tại |
| **getAttribute(name)** | Giá trị hoặc null | Đọc request attribute |
| **getAttributeOrDefault(name, defaultValue)** | Giá trị hoặc default | Đọc an toàn khi attribute có thể vắng mặt |
| **getSession()** | Mono<WebSession> | Lấy session bất đồng bộ |
| **getPrincipal()** | Mono<Principal> | Lấy người dùng hiện tại nếu có |
| **getLocaleContext()** | LocaleContext | Locale và có thể cả timezone |
| **getFormData()** | Mono<MultiValueMap<String,String>> | Parse form-urlencoded |
| **getMultipartData()** | Mono<MultiValueMap<String,Part>> | Parse multipart request |
| **checkNotModified(...)** | boolean | Xử lý conditional request qua ETag hoặc last-modified |
| **mutate()** | ServerWebExchange.Builder | Tạo decorator exchange với các thuộc tính được thay đổi có chủ đích |
| **getLogPrefix()** | String | Prefix hữu ích để liên kết log của exchange |

### 3.1. Đọc request và response

~~~java
@GetMapping("/inspect")
public Mono<Map<String, String>> inspect(
    ServerWebExchange exchange
) {
    ServerHttpRequest request = exchange.getRequest();
    ServerHttpResponse response = exchange.getResponse();

    response.getHeaders().set("X-Handled-By", "webflux");

    return Mono.just(Map.of(
        "method", request.getMethod().name(),
        "path", request.getURI().getPath(),
        "host", request.getHeaders().getFirst("Host")
    ));
}
~~~

Đây là snippet trong controller đã import các kiểu Spring và Reactor. Có thể đọc header, method, URI và đặt response header trước khi response được commit. **Không lưu ServerWebExchange vào singleton field** để dùng sau request; object này thuộc vòng đời một exchange.

Nếu chỉ cần một vài giá trị, dùng trực tiếp **ServerHttpRequest** hoặc **ServerHttpResponse** làm tham số có thể giúp method hẹp và dễ kiểm thử hơn. Dùng ServerWebExchange khi thực sự cần nhiều khả năng hoặc cần truy cập cả request lẫn response.

### 3.2. Request attributes

Attributes là một Map gắn với exchange hiện tại. Chúng hữu ích khi WebFilter hoặc handler trước đó đưa một giá trị tạm để tầng sau sử dụng:

~~~java
public static final String START_TIME = "app.startTime";

@GetMapping("/timing")
public Mono<String> timing(ServerWebExchange exchange) {
    Long started = exchange.getAttribute(START_TIME);

    if (started == null) {
        return Mono.just("start time unavailable");
    }

    long elapsedMillis =
        (System.nanoTime() - started) / 1_000_000;

    return Mono.just("elapsed=" + elapsedMillis + "ms");
}
~~~

Đây là snippet; WebFilter phải đặt attribute trước khi gọi filter chain. Attribute chỉ có phạm vi exchange, không phải cache dùng chung giữa các request. Tránh lưu object lớn hoặc dữ liệu nhạy cảm không cần thiết.

Ví dụ filter:

~~~java
@Component
public class RequestTimingFilter implements WebFilter {
    public static final String START_TIME = "app.startTime";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        exchange.getAttributes().put(
            START_TIME,
            System.nanoTime()
        );

        return chain.filter(exchange);
    }
}
~~~

Filter và handler cùng dùng một key tập trung để tránh lỗi chính tả. Vì attribute Map có thể thay đổi, không dùng nó như một cơ chế đồng bộ giữa nhiều thread hoặc nhiều request.

### 3.3. Session là reactive và không tự tạo session chỉ vì gọi getSession

**getSession()** trả **Mono<WebSession>**. Việc lấy session không đồng nghĩa ngay lập tức ghi một session mới xuống cookie hoặc kho session. Session chỉ cần được lưu khi có thay đổi cần lưu, chẳng hạn thêm attribute.

~~~java
@GetMapping("/session/visit")
public Mono<String> visit(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> {
            Integer count = session.getAttribute("visits");
            int next = count == null ? 1 : count + 1;
            session.getAttributes().put("visits", next);
            return "visits=" + next;
        });
}
~~~

Đây là snippet minh họa; **WebSession.getAttribute** và **getAttributes** được dùng để đọc/ghi session. Việc cập nhật session phải nằm trong pipeline reactive. Không gọi **subscribe()** thủ công và không block để chờ session.

Nếu nhiều request đồng thời cập nhật cùng một session, cần cân nhắc tính nhất quán và khả năng cập nhật đua. Session không phải kho lưu trữ giao dịch tổng quát; không nên dùng nó làm nơi giữ trạng thái nghiệp vụ lớn.

### 3.4. Đọc form data

Với Content-Type **application/x-www-form-urlencoded**, exchange cung cấp:

~~~java
@PostMapping("/form")
public Mono<String> form(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(data -> {
            String name = data.getFirst("name");
            return "name=" + (name == null ? "" : name);
        });
}
~~~

**getFormData()** trả Mono của MultiValueMap. Framework parse toàn bộ form body và cache kết quả trong exchange; vì vậy có thể gọi phương thức này nhiều lần mà không đọc lại body gốc. Tuy nhiên, parsing vẫn có giới hạn bộ nhớ/codec và không nên coi form lớn là vô hạn.

### 3.5. Đọc multipart data

Với **multipart/form-data**, API:

~~~java
@PostMapping("/upload-info")
public Mono<String> uploadInfo(ServerWebExchange exchange) {
    return exchange.getMultipartData()
        .map(parts -> "partCount=" + parts.size());
}
~~~

**getMultipartData()** parse request thành MultiValueMap và cache map. Nhưng nội dung của từng **Part** không được cache theo cùng cách; body của part chỉ có thể đọc một lần theo hợp đồng. Nếu cần xử lý file lớn theo streaming, cân nhắc **Flux<PartEvent>** hoặc API streaming tương ứng thay vì gom toàn bộ part vào map.

Không đọc request body nhiều lần qua các đường khác nhau nếu chưa hiểu cách codec tiêu thụ body. Một body đã được đọc bởi resolver hoặc filter có thể không còn sẵn cho một consumer độc lập.

## 4. Principal trong handler method

**java.security.Principal** là interface chuẩn Java mô tả danh tính của một thực thể đã được xác định. Trong WebFlux, Principal đại diện cho người dùng hiện tại nếu request đã được xác thực bởi server hoặc security infrastructure.

API trên exchange:

~~~java
Mono<Principal> principal = exchange.getPrincipal();
~~~

API trong chữ ký handler:

~~~java
@GetMapping("/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal
        .map(Principal::getName)
        .defaultIfEmpty("anonymous");
}
~~~

**PrincipalMethodArgumentResolver** phân giải Principal theo cách bất đồng bộ. Trong chữ ký method, **Mono<Principal>** cho phép compose trực tiếp với pipeline mà không chặn thread.

### 4.1. Vì sao Principal có thể vắng mặt?

Không phải mọi request đều được xác thực. Nếu ứng dụng không có authentication hoặc không có principal cho request, Publisher có thể hoàn tất rỗng. Vì vậy:

~~~java
return principal
    .map(Principal::getName)
    .defaultIfEmpty("anonymous");
~~~

được dùng khi endpoint thực sự cho phép truy cập ẩn danh. Nếu endpoint yêu cầu xác thực, hãy cấu hình authorization để chặn request chưa đăng nhập thay vì tự gán danh tính giả.

**Cẩn thận với anonymous authentication:** khi Spring Security bật cơ chế anonymous, request chưa đăng nhập có thể có một Authentication đại diện cho anonymous user. Khi đó giá trị principal có thể là tên như **anonymousUser** tùy cấu hình. Không giả định mọi trường hợp không đăng nhập đều là Mono.empty().

### 4.2. Principal khác với Authentication và UserDetails

- **Principal** là abstraction Java đơn giản, thường chỉ cần **getName()**.
- **Authentication** của Spring Security mô tả trạng thái xác thực, principal, credentials và authorities.
- **UserDetails** là mô hình thông tin người dùng mà một số cơ chế xác thực sử dụng.
- **@AuthenticationPrincipal** của Spring Security có thể dùng khi cần lấy principal theo kiểu ứng dụng cụ thể thay vì chỉ dùng java.security.Principal.

Một Authentication đã xác thực thường triển khai Principal, nhưng không phải Principal nào cũng là Authentication. Không ép kiểu Principal sang Authentication nếu không kiểm tra loại và contract.

Ví dụ chỉ cần username:

~~~java
@GetMapping("/username")
public Mono<String> username(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
~~~

Nếu cần authorities hoặc authentication state, hãy dùng API Spring Security phù hợp thay vì cố lấy tất cả từ getName().

### 4.3. Principal đến từ đâu trong Spring Security WebFlux?

Spring Security reactive sử dụng **WebFilter** và **Reactor Context** để duy trì SecurityContext trong chuỗi reactive. Khi request được xác thực, security filter chain đưa Authentication vào reactive security context; WebFlux có thể phân giải Principal cho handler.

Ở tầng service, nếu không muốn thêm Principal vào mọi chữ ký method, có thể truy cập security context bằng **ReactiveSecurityContextHolder**:

~~~java
Mono<String> currentUsername =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Đoạn này yêu cầu Spring Security WebFlux và các import tương ứng. Nó phải được sử dụng trong một Publisher reactive để Context được duy trì. Không dùng **SecurityContextHolder** theo kiểu ThreadLocal imperative trong một pipeline reactive như thể thread sẽ không thay đổi.

### 4.4. Không lấy Principal từ header tự khai báo

Header như **X-User**, **X-Principal** hoặc query parameter **user=alice** chỉ là dữ liệu do client gửi. Chúng không chứng minh người gửi là alice. Chỉ sử dụng identity đã được xác thực bởi Spring Security, gateway tin cậy với hợp đồng rõ ràng hoặc một cơ chế xác thực phù hợp.

Correlation ID và Principal cũng có mục đích khác nhau: correlation ID liên kết log/request; Principal thể hiện danh tính đã xác thực. Không dùng cái này thay cái kia.

## 5. Locale và LocaleContext

**java.util.Locale** mô tả ngôn ngữ, quốc gia/vùng và các quy ước định dạng liên quan. Ví dụ:

- **vi-VN**: tiếng Việt tại Việt Nam.
- **en-US**: tiếng Anh theo quy ước Hoa Kỳ.
- **en-GB**: tiếng Anh theo quy ước Vương quốc Anh.
- **ja-JP**: tiếng Nhật tại Nhật Bản.

Trong WebFlux, handler có thể nhận trực tiếp:

~~~java
@GetMapping("/language")
public String language(Locale locale) {
    return locale.toLanguageTag();
}
~~~

Locale là tham số đồng bộ; không cần **Mono<Locale>**. Nó được phân giải thông qua **LocaleContextResolver** đã cấu hình cho ứng dụng.

### 5.1. AcceptHeaderLocaleContextResolver

Trong cấu hình WebFlux thông thường, resolver mặc định là **AcceptHeaderLocaleContextResolver**. Nó xem xét header HTTP:

~~~http
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.8
~~~

Resolver đối chiếu locale được client yêu cầu với danh sách **supported locales** mà ứng dụng cấu hình. Nếu không có match, resolver dùng default locale nếu đã cấu hình; nếu không, nó có thể dùng locale được yêu cầu đầu tiên theo quy tắc của resolver.

Điều quan trọng: chỉ gửi **Accept-Language** không có nghĩa ứng dụng tự dịch nội dung. Locale chỉ cung cấp ngữ cảnh; controller/service cần sử dụng MessageSource, resource bundle hoặc logic i18n để chọn thông báo.

### 5.2. Cấu hình locale được hỗ trợ

~~~java
@Configuration
public class LocaleConfiguration {

    @Bean
    public LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
            new AcceptHeaderLocaleContextResolver();

        resolver.setSupportedLocales(List.of(
            Locale.ENGLISH,
            Locale.forLanguageTag("vi-VN"),
            Locale.forLanguageTag("ja-JP")
        ));

        resolver.setDefaultLocale(Locale.ENGLISH);
        return resolver;
    }
}
~~~

Cấu hình này giới hạn các locale ứng dụng chủ động hỗ trợ và chọn English khi không có match. Nếu muốn chấp nhận locale chỉ có mã ngôn ngữ như **vi**, hãy thêm **Locale.forLanguageTag("vi")** vào danh sách supported locales. Resolver đối chiếu language và country theo quy tắc; không giả định vi-VN tự động khớp với mọi biến thể vi-*.

### 5.3. Đọc LocaleContext và timezone

**exchange.getLocaleContext()** trả LocaleContext hiện hành. Nếu resolver cung cấp một **TimeZoneAwareLocaleContext**, có thể lấy thêm timezone:

~~~java
LocaleContext context = exchange.getLocaleContext();
Locale locale = context.getLocale();

TimeZone timeZone = null;
if (context instanceof TimeZoneAwareLocaleContext aware) {
    timeZone = aware.getTimeZone();
}
~~~

Đây là snippet Java 17. LocaleContext có thể không chứa timezone; cần kiểm tra trước khi truy cập. Trong chữ ký handler, WebFlux cũng hỗ trợ **TimeZone** và **ZoneId** khi có resolver phù hợp.

Locale và timezone là hai khái niệm riêng: locale ảnh hưởng ngôn ngữ/định dạng, timezone ảnh hưởng cách diễn giải thời điểm. Không dùng Locale để suy ra timezone một cách cứng nhắc.

### 5.4. Dùng Locale với MessageSource

Trong Spring, có thể dùng **MessageSource** để lấy thông báo theo locale:

~~~java
@Service
public class GreetingService {
    private final MessageSource messages;

    public GreetingService(MessageSource messages) {
        this.messages = messages;
    }

    public String greeting(Locale locale) {
        return messages.getMessage(
            "greeting",
            null,
            "Hello",
            locale
        );
    }
}
~~~

Ví dụ file resource:

~~~properties
# messages.properties
greeting=Hello

# messages_vi.properties
greeting=Xin chào

# messages_ja.properties
greeting=こんにちは
~~~

Trong cấu hình mặc định của Spring Boot, resource bundle có thể được phát hiện theo tên messages; tùy dự án, cần cấu hình basename nếu dùng vị trí/tên khác. Controller có thể nhận Locale rồi truyền vào service, hoặc service nhận locale như một tham số rõ ràng để dễ test.

**Đừng dựa vào Locale.getDefault() của JVM** nếu muốn phản ánh ngôn ngữ từng request. Locale của JVM là cấu hình process; Locale được resolver xác định là ngữ cảnh của request hiện tại.

## 6. Kết hợp ServerWebExchange, Principal và Locale

Một handler có thể sử dụng cả ba tham số theo vai trò khác nhau:

~~~java
@RestController
@RequestMapping("/api")
public class RequestContextController {

    @GetMapping("/context")
    public Mono<Map<String, String>> context(
        ServerWebExchange exchange,
        Mono<Principal> principal,
        Locale locale
    ) {
        return principal.map(user -> Map.of(
            "username", user.getName(),
            "method", exchange.getRequest().getMethod().name(),
            "path", exchange.getRequest().getURI().getPath(),
            "language", locale.toLanguageTag()
        ));
    }
}
~~~

- **ServerWebExchange** cung cấp thông tin request và response.
- **Mono<Principal>** cho phép đợi danh tính hiện tại.
- **Locale** cung cấp ngôn ngữ/vùng để chọn nội dung.
- **Mono<Map<...>>** là kết quả được phát sau khi principal được phân giải.

Nếu endpoint cho phép anonymous:

~~~java
@GetMapping("/public-context")
public Mono<Map<String, String>> publicContext(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    return principal
        .map(Principal::getName)
        .defaultIfEmpty("anonymous")
        .map(name -> Map.of(
            "user", name,
            "path", exchange.getRequest().getURI().getPath(),
            "language", locale.toLanguageTag()
        ));
}
~~~

Đây là snippet; nếu Spring Security anonymous filter cung cấp anonymous Authentication, tên có thể là anonymousUser thay vì chuỗi fallback. Nếu API cần một định dạng duy nhất, chuẩn hóa principal name theo chính sách ứng dụng.

### 6.1. Chỉ lấy phần cần thiết

Nếu method chỉ cần tên người dùng, nhận **Mono<Principal>** là đủ. Nếu chỉ cần path, nhận **ServerHttpRequest** hoặc dùng **@PathVariable**. Nếu chỉ cần Locale, nhận trực tiếp Locale.

Không nhận ServerWebExchange trong mọi controller method theo thói quen. Một chữ ký hẹp giúp code dễ hiểu, dễ unit test và giảm nguy cơ handler phụ thuộc quá nhiều vào chi tiết HTTP.

### 6.2. Chụp giá trị request trước khi xử lý dài

Nếu cần truyền metadata xuống service, có thể đọc một lần rồi compose:

~~~java
public Mono<LocalizedProfile> profile(
    ServerWebExchange exchange,
    Mono<Principal> principal,
    Locale locale
) {
    String path = exchange.getRequest().getURI().getPath();

    return principal.flatMap(user ->
        profileService.find(user.getName())
            .map(profile ->
                new LocalizedProfile(
                    profile.id(),
                    user.getName(),
                    locale.toLanguageTag(),
                    path
                )
            )
    );
}
~~~

Các kiểu **Profile**, **LocalizedProfile** và service là thành phần ứng dụng. Việc lấy path và locale là đồng bộ; việc lấy Principal và profile vẫn nằm trong reactive chain. Không cần dùng ThreadLocal để giữ các giá trị này.

## 7. Ứng dụng Java 17+ chạy được với Spring Boot và WebFlux Security

Ví dụ hoàn chỉnh sau có một endpoint được bảo vệ bằng HTTP Basic. Nó minh họa:

- **ServerWebExchange** đọc method/path.
- **Mono<Principal>** lấy username đã xác thực.
- **Locale** nhận theo Accept-Language.
- **LocaleContextResolver** giới hạn locale hỗ trợ.
- **WebFlux Security** đưa authentication vào reactive request context.
- **WebTestClient** kiểm tra response.

Cấu trúc:

~~~text
handler-arguments-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/handlerargs/
    │   │       ├── HandlerArgumentsApplication.java
    │   │       ├── RequestContextController.java
    │   │       ├── SecurityConfiguration.java
    │   │       └── LocaleConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/handlerargs/
                └── RequestContextControllerTest.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>handler-arguments-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Spring Boot quản lý các phiên bản Spring Framework, Spring Security và Reactor tương thích. Không thêm spring-boot-starter-web cho ví dụ WebFlux thuần này.

### 7.2. Application class

Tệp **HandlerArgumentsApplication.java**:

~~~java
package com.example.handlerargs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HandlerArgumentsApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            HandlerArgumentsApplication.class,
            args
        );
    }
}
~~~

### 7.3. Controller nhận ba tham số

Tệp **RequestContextController.java**:

~~~java
package com.example.handlerargs;

import java.security.Principal;
import java.util.Locale;
import java.util.Map;

import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class RequestContextController {

    public record RequestInfo(
        String principal,
        String method,
        String path,
        String locale
    ) {}

    @GetMapping("/request-info")
    public Mono<RequestInfo> requestInfo(
        ServerWebExchange exchange,
        Mono<Principal> principal,
        Locale locale
    ) {
        HttpMethod method = exchange.getRequest().getMethod();

        return principal.map(user ->
            new RequestInfo(
                user.getName(),
                method.name(),
                exchange.getRequest().getURI().getPath(),
                locale.toLanguageTag()
            )
        );
    }
}
~~~

Endpoint yêu cầu principal vì security configuration ở phần sau bảo vệ mọi request. Nếu bỏ authentication requirement, hãy quyết định rõ cách xử lý Mono.empty hoặc anonymous principal.

### 7.4. SecurityConfiguration

Tệp **SecurityConfiguration.java**:

~~~java
package com.example.handlerargs;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.web.server.ServerHttpSecurity;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
        ServerHttpSecurity http
    ) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges ->
                exchanges.anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
            .password("{noop}secret")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
~~~

**{noop}secret chỉ dành cho ví dụ học tập local.** Nó không mã hóa mật khẩu và không phù hợp môi trường thật. Production phải dùng PasswordEncoder thích hợp, kho user an toàn, HTTPS và chính sách xác thực/ủy quyền phù hợp.

### 7.5. LocaleConfiguration

Tệp **LocaleConfiguration.java**:

~~~java
package com.example.handlerargs;

import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.i18n.AcceptHeaderLocaleContextResolver;
import org.springframework.web.server.i18n.LocaleContextResolver;

@Configuration
public class LocaleConfiguration {

    @Bean
    LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
            new AcceptHeaderLocaleContextResolver();

        resolver.setSupportedLocales(List.of(
            Locale.ENGLISH,
            Locale.forLanguageTag("vi-VN")
        ));
        resolver.setDefaultLocale(Locale.ENGLISH);

        return resolver;
    }
}
~~~

Resolver này chấp nhận English và Vietnamese (Việt Nam). Khi client gửi **Accept-Language: vi-VN**, locale được phân giải là vi-VN. Nếu header thiếu hoặc không có locale hỗ trợ phù hợp, default locale là English.

### 7.6. application.properties

~~~properties
spring.application.name=handler-arguments-demo
server.port=8080
logging.level.com.example.handlerargs=INFO
~~~

### 7.7. Kiểm thử bằng WebTestClient

Tệp **RequestContextControllerTest.java**:

~~~java
package com.example.handlerargs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class RequestContextControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void resolvesExchangePrincipalAndLocale() {
        client.get()
            .uri("/api/request-info")
            .headers(headers ->
                headers.setBasicAuth("alice", "secret")
            )
            .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.principal").isEqualTo("alice")
            .jsonPath("$.method").isEqualTo("GET")
            .jsonPath("$.path").isEqualTo("/api/request-info")
            .jsonPath("$.locale").isEqualTo("vi-VN");
    }

    @Test
    void rejectsRequestWithoutAuthentication() {
        client.get()
            .uri("/api/request-info")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

Test dùng HTTP Basic để xác thực và gửi Accept-Language riêng. Spring Boot chạy server trên cổng ngẫu nhiên nên không cần phụ thuộc cổng 8080 trong test.

### 7.8. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Gọi endpoint với user demo:

~~~bash
curl -i -u alice:secret \
  -H "Accept-Language: vi-VN" \
  http://localhost:8080/api/request-info
~~~

Response body dự kiến:

~~~json
{
  "principal": "alice",
  "method": "GET",
  "path": "/api/request-info",
  "locale": "vi-VN"
}
~~~

Không gửi credentials thì endpoint trả **401 Unauthorized** theo security chain trong ví dụ.

Lưu ý: response body ở trên là dạng minh họa đã format; thứ tự field hoặc khoảng trắng JSON không phải contract. Các giá trị principal, method, path và locale mới là điều cần kiểm tra.

## 8. Sử dụng Principal ở tầng service

Nếu service được gọi từ nhiều controller và cần biết user hiện tại, có hai cách phổ biến.

### Cách 1: truyền Principal hoặc username tường minh

~~~java
public Mono<Account> findAccount(
    String accountId,
    String username
) {
    return repository.findVisibleTo(accountId, username);
}
~~~

Cách này làm dependency rõ ràng và dễ unit test. Controller đọc principal rồi truyền tên người dùng vào service.

### Cách 2: đọc ReactiveSecurityContextHolder trong pipeline

~~~java
public Mono<Account> currentAccount(String accountId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(username ->
            repository.findVisibleTo(accountId, username)
        );
}
~~~

Cách này phù hợp khi service cần security context từ reactive subscription mà không muốn truyền thêm tham số qua nhiều tầng. Service phải trả Publisher reactive để security context được duy trì.

**Không dùng SecurityContextHolder.getContext() theo kiểu imperative** để đọc authentication trong WebFlux. Security context reactive được gắn với Reactor Context, không được đảm bảo nằm trên cùng thread.

## 9. Locale trong xử lý nghiệp vụ và định dạng

### 9.1. Locale ảnh hưởng cách hiển thị, không thay đổi dữ liệu gốc

Ví dụ số **1234.56** có thể hiển thị khác nhau theo locale; ngày tháng cũng có thể dùng thứ tự khác. Không nên lưu chuỗi đã format làm dữ liệu gốc. Hãy lưu số, thời điểm và tiền tệ theo kiểu phù hợp rồi format ở tầng trình bày theo locale.

Ví dụ:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(locale);
String display = format.format(1234.56);
~~~

Đây là snippet Java sử dụng **java.text.NumberFormat**. Locale không tự xác định currency cho mọi nghiệp vụ; tiền tệ cần mã ISO và quy tắc nghiệp vụ riêng.

### 9.2. Locale của request và locale của JVM khác nhau

- **Locale của request** được resolver xác định từ header hoặc cấu hình ứng dụng.
- **Locale.getDefault()** là locale mặc định của JVM/process.
- **LocaleContextHolder** là cơ chế gắn LocaleContext với thread trong một số integration; không tự thay thế cách truyền Locale trong reactive pipeline nếu chưa cấu hình context propagation.

Ưu tiên nhận Locale từ handler hoặc truyền nó tường minh vào service cần format. Không đặt một static Locale mutable theo request vì nhiều request có thể chạy đồng thời với ngôn ngữ khác nhau.

### 9.3. Kiểm thử nhiều locale

Nên có test cho:

- Accept-Language khớp một locale hỗ trợ.
- Header không có.
- Header chứa locale không được hỗ trợ.
- Header có nhiều locale và quality value.
- Locale chỉ có language trong khi ứng dụng chỉ hỗ trợ language-country.
- Default locale được cấu hình.

Không giả định **vi** và **vi-VN** luôn tương đương trong danh sách supported locales. Nếu cần hỗ trợ cả hai, khai báo cả hai hoặc xây dựng resolver theo chính sách của ứng dụng.

## 10. Những lỗi thường gặp

| Hiện tượng / hiểu nhầm | Cách hiểu và cách sửa |
| --- | --- |
| Dùng HttpServletRequest trong WebFlux | Đây là API Servlet. Dùng **ServerWebExchange** hoặc **ServerHttpRequest**. |
| Bọc ServerWebExchange trong Mono | Không cần. Exchange là tham số trực tiếp; các thao tác async như getSession trả Mono. |
| Gọi principal.block() trong controller | Chặn thread và phá mô hình reactive. Dùng **Mono<Principal>** rồi map/flatMap. |
| Giả định mọi request có Principal | Có request chưa xác thực hoặc cấu hình anonymous. Bảo vệ endpoint hoặc xử lý empty/anonymous rõ ràng. |
| Tin header X-User là danh tính | Header client tự gửi không phải authentication. Dùng Spring Security hoặc identity provider đáng tin cậy. |
| Ép Principal thành Authentication | Không phải mọi Principal đều là Authentication. Kiểm tra contract hoặc dùng API Spring Security phù hợp. |
| Đọc SecurityContextHolder như MVC | WebFlux dùng **ReactiveSecurityContextHolder** và Reactor Context. |
| Dùng Locale.getDefault() để chọn ngôn ngữ từng request | Đây là locale của JVM. Nhận **Locale** từ handler hoặc LocaleContextResolver. |
| Dùng LocaleResolver của Spring MVC | WebFlux sử dụng **LocaleContextResolver** trong package web.server.i18n. |
| Gửi Accept-Language nhưng không cấu hình nội dung dịch | Resolver chỉ cung cấp locale; cần MessageSource/resource bundle để dịch. |
| Chỉ hỗ trợ vi-VN nhưng mong vi tự match | Quy tắc matching dựa trên supported locales; khai báo language-only locale nếu cần. |
| Gọi getFormData rồi đọc lại raw body như chưa từng tiêu thụ | Form parsing đọc body và cache map; thiết kế một đường đọc rõ ràng. |
| Giả định multipart content được cache hoàn toàn | Map parts được cache, nhưng nội dung từng part có thể chỉ đọc một lần. |
| Giữ ServerWebExchange trong singleton | Exchange thuộc một request; lưu reference có thể gây rò dữ liệu và lỗi concurrency. |
| Ghi attribute để chia sẻ giữa các request | Attributes chỉ thuộc exchange hiện tại. Dùng kho chia sẻ có kiểm soát nếu thật sự cần. |
| Tạo session chỉ để đọc dữ liệu | getSession không tự lưu session nếu không có thay đổi; cân nhắc có thật sự cần session. |
| Subscribe thủ công khi xử lý session/principal | Tách tác vụ khỏi request pipeline; compose Publisher và trả về. |
| Dùng Locale để suy ra timezone | Locale và timezone khác nhau; dùng TimeZone/ZoneId hoặc LocaleContext phù hợp. |

## 11. Checklist thiết kế handler method

Trước khi thêm tham số, hãy tự hỏi:

1. Có cần toàn bộ exchange hay chỉ request/response?
2. Có cần đọc request attributes/session không?
3. Principal có luôn tồn tại không, và endpoint có yêu cầu xác thực không?
4. Có cần Mono<Principal> để compose bất đồng bộ không?
5. Locale được lấy từ Accept-Language hay từ một resolver tùy chỉnh?
6. Supported locales và default locale đã được định nghĩa chưa?
7. Có cần TimeZone/ZoneId riêng ngoài Locale không?
8. Body form/multipart có được đọc một lần và đúng giới hạn không?
9. Service có nhận dữ liệu tường minh hay dùng ReactiveSecurityContextHolder?
10. Có đang dùng API Servlet hoặc ThreadLocal không phù hợp trong WebFlux?
11. Có test cho authenticated/unauthenticated và nhiều locale không?
12. Có ghi log mà không lộ dữ liệu nhạy cảm hoặc credentials không?

## 12. Bài tập thực hành

**Bài 1 — Đọc exchange:** Tạo GET /api/inspect nhận ServerWebExchange và trả method, path, host, Accept-Language. Kiểm tra request có và không có header.

**Bài 2 — Principal:** Tạo endpoint GET /api/me nhận Mono<Principal>. Bảo vệ endpoint bằng HTTP Basic; gọi với user hợp lệ và không có credentials. Quan sát 200 và 401.

**Bài 3 — Anonymous:** Cho phép một endpoint public. Xử lý Mono<Principal> empty hoặc anonymous Authentication theo đúng cấu hình. Không tự coi một header là danh tính.

**Bài 4 — Locale:** Cấu hình AcceptHeaderLocaleContextResolver chỉ hỗ trợ en và vi-VN, default English. Thử Accept-Language: vi-VN, en-US và fr-FR.

**Bài 5 — MessageSource:** Tạo messages.properties và messages_vi.properties, truyền Locale vào MessageSource để trả greeting đúng ngôn ngữ.

**Bài 6 — Session:** Tạo endpoint tăng bộ đếm trong WebSession. Gửi nhiều request có cùng cookie session và quan sát giá trị. Kiểm tra behavior khi xóa cookie.

**Bài 7 — Form data:** Gửi application/x-www-form-urlencoded và đọc exchange.getFormData(). Kiểm tra giá trị thiếu và nhiều giá trị cùng key.

**Bài 8 — Multipart:** Nhận multipart form có file. So sánh getMultipartData với cách xử lý streaming PartEvent; chú ý vòng đời và việc đọc nội dung part.

**Bài 9 — Service security:** Viết service dùng ReactiveSecurityContextHolder và so sánh với cách controller truyền username vào service. Chọn cách dễ test và rõ contract hơn.

**Bài 10 — WebTestClient:** Viết test xác thực, path, method, locale và trường hợp thiếu credentials. Test không nên phụ thuộc cổng cố định hoặc thứ tự JSON field.

## 13. Ghi nhớ

**ServerWebExchange** là context đầy đủ của một request/response; **Principal** là danh tính đã được xác thực nếu có và nên được compose theo kiểu reactive; **Locale** là ngữ cảnh ngôn ngữ/vùng được phân giải từ cấu hình request, thường qua Accept-Language.

Trong handler method, dùng **ServerWebExchange** khi cần toàn bộ request/response hoặc session/attributes, **Mono<Principal>** khi cần danh tính bất đồng bộ, và **Locale** trực tiếp để xử lý nội dung đa ngôn ngữ. Giữ các giá trị trong đúng vòng đời request, không block, không tin dữ liệu identity do client tự gửi và kiểm thử cả trường hợp thiếu principal/locale.

## 14. Tài liệu tham khảo

- Spring Framework Reference — WebFlux Controller Method Arguments: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html
- Spring Framework 6.1 API — ServerWebExchange: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework 6.1 API — PrincipalMethodArgumentResolver: https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/web/reactive/result/method/annotation/PrincipalMethodArgumentResolver.html
- Spring Framework 6.1 API — AcceptHeaderLocaleContextResolver: https://docs.spring.io/spring-framework/docs/6.1.0-M1/javadoc-api/org/springframework/web/server/i18n/AcceptHeaderLocaleContextResolver.html
- Spring Framework Reference — WebFlux Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security Reference — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security Reference — Reactive Method Security and ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Framework Reference — MessageSource and Internationalization: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
