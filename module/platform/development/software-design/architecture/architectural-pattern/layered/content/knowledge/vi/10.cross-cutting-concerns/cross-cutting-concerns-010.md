# Sử dụng middleware, filter, interceptor và decorator đúng trách nhiệm

Một request trong ứng dụng thường cần nhiều xử lý bên cạnh nghiệp vụ chính: xác thực, ghi log, đo thời gian, gắn mã tương quan, kiểm tra quyền truy cập, xử lý lỗi hoặc cache. Nếu chép những xử lý này vào từng controller và service, mã nguồn bị lặp và các endpoint có thể áp dụng quy tắc không nhất quán. Nếu gom tất cả vào một thành phần duy nhất, thành phần đó lại trở nên khó hiểu và khó kiểm thử.

Middleware, filter, interceptor và decorator là những cơ chế thường dùng để tổ chức các mối quan tâm xuyên tầng. Chúng có điểm chung là bổ sung xử lý quanh một luồng chính, nhưng khác nhau về vị trí, hợp đồng và phạm vi. Chọn đúng cơ chế giúp giữ kiến trúc phân tầng rõ ràng: giao tiếp HTTP được xử lý gần biên HTTP, hook của MVC chỉ làm việc với vòng đời handler, còn hành vi bổ sung cho một dịch vụ ứng dụng có thể được đóng gói bằng decorator.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED, mục tiêu là học tổ chức phần mềm theo kiến trúc phân tầng. Bài này dùng Java và Spring để minh họa, đồng thời giải thích middleware như một khái niệm pipeline tổng quát. Không phải mọi ứng dụng đều cần cả bốn cơ chế; hãy chọn dựa trên điểm cần can thiệp và trách nhiệm thực tế.

## 1. Mối quan tâm xuyên tầng và pipeline xử lý

Một mối quan tâm xuyên tầng (cross-cutting concern) ảnh hưởng đến nhiều thành phần hoặc nhiều ca sử dụng, dù không phải logic nghiệp vụ cốt lõi. Ví dụ:

- Ghi log và tạo mã tương quan để lần theo một request qua nhiều thành phần.
- Đo thời gian, thu thập metrics và tracing.
- Xác thực danh tính và kiểm tra quyền truy cập.
- Áp dụng CORS, giới hạn tốc độ hoặc chuẩn hóa header HTTP.
- Chuyển exception thành phản hồi theo hợp đồng giao tiếp.
- Cache kết quả, retry hoặc ghi audit quanh một dịch vụ cụ thể.

Các mối quan tâm này không có cùng phạm vi. CORS và header HTTP thuộc biên giao tiếp; kiểm tra quyền theo endpoint có thể thuộc security filter chain; cache kết quả truy vấn thuộc hành vi của một dịch vụ; còn quy tắc như “khách hàng không được đặt quá số lượng cho phép” vẫn là logic nghiệp vụ.

Pipeline là cách tổ chức nhiều bước xử lý thành một chuỗi. Mỗi bước có thể thực hiện công việc trước khi chuyển quyền điều khiển cho bước tiếp theo, và có thể thực hiện công việc sau khi bước tiếp theo trả về. Một bước cũng có thể từ chối request và kết thúc chuỗi sớm.

~~~mermaid
flowchart LR
    R["Request"] --> M["Middleware / Filter chain"]
    M --> I["MVC Interceptor"]
    I --> C["Controller"]
    C --> S["Application service"]
    S --> D["Domain / ports"]
    D --> O["Response"]
    O --> I
    I --> M
    M --> X["Client"]
~~~

Sơ đồ khái quát thứ tự đi vào và quay ra. Trong Spring MVC, servlet filter bao quanh DispatcherServlet; HandlerInterceptor được gọi trong vòng đời xử lý handler của MVC; decorator bao quanh một đối tượng cộng tác cụ thể và không nhất thiết xuất hiện như một bước HTTP. Sơ đồ không có nghĩa mọi concern đều nên được triển khai ở tất cả các điểm.

## 2. Middleware — khái niệm pipeline ở biên xử lý

Middleware là một thành phần nằm trong pipeline, nhận ngữ cảnh request hoặc message, thực hiện xử lý trước/sau và chuyển quyền cho thành phần tiếp theo. Middleware có thể:

- Bổ sung dữ liệu vào ngữ cảnh, ví dụ correlation ID.
- Kiểm tra điều kiện và từ chối xử lý.
- Đo thời gian trước và sau bước tiếp theo.
- Bắt lỗi ở một ranh giới chung rồi chuẩn hóa kết quả.
- Chuyển request đến bước kế tiếp trong pipeline.

Middleware là khái niệm kiến trúc, không phải tên của một API Java duy nhất. Trong ứng dụng web Java Servlet, Filter thường đóng vai trò middleware cho HTTP request. Một số framework khác có middleware pipeline riêng; trong ứng dụng message-driven, consumer middleware có thể bao quanh bước nhận và xử lý message.

Ví dụ pipeline khái quát:

~~~java
public interface Middleware {
    Response invoke(Request request, Next next);
}

@FunctionalInterface
public interface Next {
    Response handle(Request request);
}
~~~

Một middleware đo thời gian có thể gọi bước kế tiếp rồi ghi nhận thời lượng:

~~~java
public class TimingMiddleware implements Middleware {
    private final Metrics metrics;

    public TimingMiddleware(Metrics metrics) {
        this.metrics = metrics;
    }

    @Override
    public Response invoke(Request request, Next next) {
        long started = System.nanoTime();
        try {
            return next.handle(request);
        } finally {
            metrics.record(
                "request.duration",
                System.nanoTime() - started
            );
        }
    }
}
~~~

Đây là mô hình minh họa, không phải API middleware chuẩn của Spring. Ý chính là middleware bao quanh một bước tiếp theo và có thể thực hiện công việc trong cả hai chiều của pipeline.

Thứ tự middleware có ý nghĩa. Ví dụ, request ID nên được thiết lập trước khi các bước logging cần ghi nó; một middleware xử lý lỗi ở ngoài có thể bắt lỗi phát sinh từ các bước ở trong. Nếu thay đổi thứ tự, dữ liệu log hoặc phạm vi xử lý lỗi có thể thay đổi. Hãy khai báo thứ tự rõ ràng và kiểm thử các trường hợp từ chối sớm, exception và request bình thường.

## 3. Filter — can thiệp ở biên Servlet/HTTP

Trong Java Servlet, Filter nhận HttpServletRequest và HttpServletResponse trước hoặc sau servlet đích. Một filter có thể sửa header, kiểm tra request, ghi log, gắn thông tin vào request context hoặc chặn request trước khi nó tới DispatcherServlet.

Các ứng dụng Spring Boot có thể dùng OncePerRequestFilter để tạo một filter thường chỉ chạy một lần cho một lần dispatch phù hợp. Ví dụ sau tạo mã tương quan cho request, đưa mã đó vào MDC để log có thể đính kèm và trả mã trong response:

~~~java
@Component
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String requestId = UUID.randomUUID().toString();
        MDC.put("requestId", requestId);
        response.setHeader("X-Request-Id", requestId);

        try {
            filterChain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Khối finally rất quan trọng. Servlet container thường tái sử dụng thread; nếu không xóa giá trị MDC, request sau có thể ghi log bằng request ID của request trước. Trong hệ thống cần chấp nhận request ID do gateway truyền vào, hãy kiểm tra định dạng và độ dài trước khi dùng; không nên tin mù quáng một header tùy ý từ client.

Filter có thể kết thúc chuỗi mà không gọi filterChain.doFilter, chẳng hạn khi request không đáp ứng điều kiện ở biên HTTP. Nó cũng có thể bọc request/response để đọc hoặc biến đổi nội dung, nhưng việc đọc body cần chú ý stream chỉ đọc một lần và kích thước payload.

### 3.1. Filter phù hợp với việc gì?

Filter phù hợp khi xử lý không cần biết controller hoặc handler MVC cụ thể:

- Gắn request ID, logging ở biên, metrics tổng quát.
- Chuẩn hóa header hoặc xử lý CORS.
- Áp dụng các quy tắc HTTP trước khi vào MVC.
- Bọc request/response hoặc chặn request theo điều kiện chung.
- Security filter chain để xác thực và phân quyền ở biên bảo mật.

Với Spring Security, nên cấu hình các bộ lọc bảo mật chuyên dụng trong SecurityFilterChain. Không nên tự viết một filter đơn giản để thay thế toàn bộ cơ chế xác thực, quản lý session, CSRF, exception translation và authorization của framework.

Filter không nên tự thực hiện quy tắc nghiệp vụ như kiểm tra tồn kho, tính giá hoặc quyết định một đơn hàng có được chấp nhận hay không. Filter cũng không nên truy cập repository để thay controller gọi use case; làm như vậy sẽ đưa nghiệp vụ vào biên HTTP và làm luồng xử lý khó lần theo.

## 4. Interceptor — hook trong vòng đời handler MVC

Spring MVC cung cấp HandlerInterceptor để can thiệp quanh việc thực thi handler sau khi DispatcherServlet đã tìm được handler phù hợp. Interceptor biết thông tin handler và có thể truy cập request/response, nên phù hợp với xử lý gắn với vòng đời MVC.

Ba hook chính:

- preHandle chạy trước handler. Trả về false sẽ ngăn handler được gọi; interceptor cần tự hoàn tất phản hồi nếu chặn request.
- postHandle chạy sau handler thành công nhưng trước bước render view. Với REST response được ghi qua HttpMessageConverter, thời điểm này không nên được hiểu là một hook tổng quát để sửa response body đã serialize.
- afterCompletion chạy sau khi request hoàn tất xử lý, kể cả khi có exception được chuyển qua lifecycle MVC; có thể dùng để dọn context hoặc ghi nhận kết quả cuối.

Ví dụ interceptor ghi nhận thời điểm bắt đầu và thời lượng xử lý handler:

~~~java
@Component
public class HandlerTimingInterceptor implements HandlerInterceptor {
    private static final String START_ATTR = "handlerStartedAt";

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        request.setAttribute(START_ATTR, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception ex) {
        Object value = request.getAttribute(START_ATTR);
        if (value instanceof Long started) {
            long elapsed = System.nanoTime() - started;
            // Gửi elapsed, status và loại handler đến metrics.
        }
    }
}
~~~

Đăng ký interceptor với MVC:

~~~java
@Configuration
public class WebMvcConfiguration implements WebMvcConfigurer {
    private final HandlerTimingInterceptor timingInterceptor;

    public WebMvcConfiguration(HandlerTimingInterceptor timingInterceptor) {
        this.timingInterceptor = timingInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(timingInterceptor)
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/health");
    }
}
~~~

### 4.1. Interceptor phù hợp với việc gì?

Interceptor hữu ích khi concern phụ thuộc vào handler MVC:

- Ghi nhận loại handler hoặc endpoint đang được gọi.
- Gắn metadata phục vụ audit hoặc metrics theo handler.
- Kiểm tra một điều kiện giao tiếp gắn với nhóm endpoint.
- Đo thời gian riêng cho phần xử lý handler.

Interceptor không thay thế filter cho mọi concern. Ví dụ, filter có thể chạy trước DispatcherServlet và áp dụng cho cả tài nguyên không phải controller MVC; interceptor chỉ tham gia khi MVC đã chọn handler. Nếu cần xác thực và phân quyền, Spring Security filter chain thường là nơi thích hợp hơn. Interceptor cũng không phải nơi tốt để triển khai giao dịch nghiệp vụ hoặc kiểm tra quyền sở hữu tài nguyên phức tạp; hãy để application service hoặc security authorization phù hợp đảm nhiệm.

Với xử lý bất đồng bộ, async dispatch và nhiều lần dispatch, vòng đời hook có thể khác so với request đồng bộ đơn giản. Nếu metrics phải đo toàn bộ thời gian bao gồm async completion, cần hiểu rõ async lifecycle của Servlet và cấu hình interceptor/filter tương ứng, không giả định afterCompletion luôn là thời điểm hoàn tất mọi công việc nền.

## 5. Decorator — bổ sung hành vi quanh một abstraction

Decorator là mẫu thiết kế cấu trúc: một đối tượng triển khai cùng interface với đối tượng được bọc, giữ tham chiếu đến đối tượng đó và bổ sung hành vi trước/sau khi ủy quyền lời gọi. Khác với filter/interceptor gắn vào lifecycle HTTP/MVC, decorator bao quanh một dependency cụ thể. Nó có thể được dùng trong ứng dụng web, tác vụ nền hoặc unit test mà không cần có request HTTP.

Giả sử ứng dụng có cổng truy vấn thông tin sản phẩm:

~~~java
public interface ProductCatalog {
    Optional<Product> findBySku(String sku);
}

public class JpaProductCatalog implements ProductCatalog {
    private final ProductJpaRepository repository;

    public JpaProductCatalog(ProductJpaRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<Product> findBySku(String sku) {
        return repository.findBySku(sku).map(ProductEntity::toDomain);
    }
}
~~~

Có thể thêm decorator ghi thời gian mà không sửa lớp JPA:

~~~java
public class TimingProductCatalog implements ProductCatalog {
    private final ProductCatalog delegate;
    private final Metrics metrics;

    public TimingProductCatalog(ProductCatalog delegate, Metrics metrics) {
        this.delegate = delegate;
        this.metrics = metrics;
    }

    @Override
    public Optional<Product> findBySku(String sku) {
        long started = System.nanoTime();
        try {
            return delegate.findBySku(sku);
        } finally {
            metrics.record(
                "catalog.lookup.duration",
                System.nanoTime() - started
            );
        }
    }
}
~~~

Decorator thực hiện cùng interface ProductCatalog nên client không cần biết nó đang gọi trực tiếp JpaProductCatalog hay TimingProductCatalog. Có thể xếp nhiều decorator:

~~~java
ProductCatalog catalog =
    new TimingProductCatalog(
        new CachingProductCatalog(
            new JpaProductCatalog(repository),
            cache
        ),
        metrics
    );
~~~

Trong cấu trúc này, cache kiểm tra trước khi gọi adapter; timing đo toàn bộ thời gian mà decorator bên trong sử dụng. Nếu đổi thứ tự, phạm vi thời gian được đo và phần công việc được cache cũng thay đổi. Vì vậy, thứ tự decorator là một quyết định có ý nghĩa.

Decorator phù hợp với cache, metrics, audit, retry có chính sách rõ ràng hoặc ghi log quanh một dịch vụ. Nó cũng có thể dùng để thay thế dependency bằng fake trong kiểm thử. Decorator không nên biến thành nơi chứa logic nghiệp vụ mới hoặc thay đổi ngầm ý nghĩa của hợp đồng.

### 5.1. Lắp ráp decorator

Trong Spring, có thể lắp ráp decorator tường minh ở cấu hình:

~~~java
@Configuration
public class CatalogConfiguration {

    @Bean
    ProductCatalog productCatalog(
            JpaProductCatalog jpaCatalog,
            Metrics metrics) {
        return new TimingProductCatalog(jpaCatalog, metrics);
    }
}
~~~

Đây là ví dụ giản lược về composition. Cần bảo đảm chỉ có một bean ProductCatalog phù hợp để inject hoặc dùng qualifier/primary rõ ràng. Nếu vừa component-scan adapter như ProductCatalog vừa khai báo decorator bean cùng kiểu mà không cấu hình lựa chọn, Spring có thể báo nhiều bean ứng viên. Một cách khác là khai báo implementation bên trong cấu hình và chỉ expose decorator ra ngoài.

## 6. So sánh bốn cơ chế

| Cơ chế | Điểm can thiệp | Ngữ cảnh biết được | Ví dụ phù hợp |
|---|---|---|---|
| Middleware | Một bước trong pipeline tổng quát | Request/message và bước tiếp theo | Đo thời gian, xử lý lỗi chung, thêm metadata |
| Servlet Filter | Biên Servlet trước/sau servlet | HttpServletRequest/Response, FilterChain | Request ID, header, CORS, security chain |
| Spring MVC HandlerInterceptor | Vòng đời handler sau khi MVC định tuyến | Handler, request/response, hook MVC | Metrics theo endpoint, metadata theo handler |
| Decorator | Quanh một dependency theo interface | Hợp đồng của dịch vụ được bọc | Cache, metrics, audit hoặc retry quanh repository/service |

Middleware là khái niệm rộng; Filter là một cơ chế cụ thể trong Servlet có thể đảm nhận vai trò middleware HTTP. HandlerInterceptor là hook riêng của Spring MVC. Decorator là mẫu thiết kế áp dụng cho một đối tượng cộng tác. Chúng có thể cùng xuất hiện trong một ứng dụng nhưng không thay thế nhau một cách máy móc.

## 7. Chọn đúng vị trí theo trách nhiệm

Khi cần thêm một concern, hãy bắt đầu bằng câu hỏi nó cần biết điều gì:

- Nếu chỉ cần biết request HTTP và cần chạy trước khi MVC chọn handler, cân nhắc Filter.
- Nếu cần biết handler MVC nào đang được gọi và can thiệp quanh lifecycle của handler, cân nhắc HandlerInterceptor.
- Nếu cần bọc một dịch vụ theo hợp đồng Java để bổ sung cache, metrics hoặc audit ở mọi nơi sử dụng dịch vụ đó, cân nhắc Decorator.
- Nếu concern thuộc pipeline tổng quát của một framework hoặc message processing, dùng middleware mechanism mà framework cung cấp.
- Nếu đó là quy tắc nghiệp vụ, đặt ở tầng miền hoặc application service theo quyền sở hữu; đừng chuyển nó thành filter chỉ vì muốn áp dụng ở nhiều endpoint.

Ví dụ, request ID thường phù hợp với filter vì cần có trước khi controller chạy và cần hiện diện trong log của toàn bộ request. Metrics theo loại controller có thể phù hợp với interceptor. Cache truy vấn danh mục có thể phù hợp với decorator của ProductCatalog vì dịch vụ đó có thể được gọi từ HTTP controller, job nền hoặc message consumer.

## 8. Thứ tự, phạm vi và vòng đời

Các cơ chế bao quanh luồng đều nhạy với thứ tự và phạm vi:

- Filter có thứ tự trong servlet filter chain. Filter ngoài có thể bao quanh toàn bộ thời gian thực thi của các filter trong và DispatcherServlet.
- Interceptor được đăng ký theo MVC configuration và có thể áp dụng theo path pattern hoặc ngoại lệ. Nhiều interceptor sẽ có thứ tự preHandle và các hook quay ra tương ứng.
- Decorator được xếp theo thứ tự composition. Lớp ngoài cùng nhận lời gọi trước và có thể xử lý kết quả hoặc exception từ lớp bên trong.
- Middleware pipeline có thứ tự do framework hoặc cấu hình ứng dụng quyết định.

Hãy kiểm tra cả đường thành công lẫn đường lỗi. Nếu bước tiếp theo ném exception, khối finally vẫn có thể dọn context và ghi metrics. Nếu một bước từ chối request, các bước phía sau không được gọi. Với context gắn vào thread như MDC, luôn dọn ở finally; với tác vụ bất đồng bộ, cần truyền context rõ ràng thay vì giả định thread-local tự đi theo.

Đừng để một concern bị thực hiện nhiều lần ngoài ý muốn. Ví dụ, nếu cả filter và interceptor đều ghi một bản log access hoàn chỉnh, mỗi request có thể tạo hai bản ghi trùng lặp. Nếu cả decorator lẫn service đều retry, số lần gọi có thể nhân lên. Hãy xác định một nơi sở hữu hành vi và quy định rõ các concern nào chỉ quan sát, concern nào có quyền chặn hoặc thử lại.

## 9. Các lỗi thường gặp

- **Đưa nghiệp vụ vào Filter:** filter truy vấn database để kiểm tra tồn kho hoặc tính phí. Điều này làm HTTP layer nắm giữ chính sách nghiệp vụ và khó tái sử dụng từ nguồn gọi khác.
- **Dùng Interceptor thay Spring Security:** tự kiểm tra token hoặc quyền trong interceptor có thể bỏ sót tài nguyên, async dispatch hoặc các đường truy cập không qua MVC. Dùng security filter chain và authorization mechanism thích hợp.
- **Dùng Interceptor để sửa mọi response body:** postHandle không phải hook chung để chỉnh body REST đã được serialize. Dùng HttpMessageConverter, ResponseBodyAdvice hoặc một abstraction đúng với mục tiêu nếu thực sự cần biến đổi body.
- **Để Filter đọc body mà không xử lý stream:** controller có thể không đọc được body nữa. Nếu cần đọc lại, phải dùng cơ chế wrapper/caching phù hợp và giới hạn kích thước.
- **Decorator thay đổi hợp đồng:** cache trả dữ liệu cũ quá thời hạn hoặc retry một thao tác không idempotent có thể làm sai kết quả. Hành vi bổ sung phải tôn trọng semantics của interface.
- **Lắp ráp bean không rõ ràng:** có nhiều implementation hoặc decorator cùng kiểu nhưng không có quy tắc chọn, dẫn đến lỗi khởi động hoặc inject sai bean.
- **Không dọn context:** MDC hoặc ThreadLocal bị giữ lại sau request và rò sang request khác trên cùng thread.
- **Tạo một interceptor khổng lồ:** gom logging, auth, transaction, cache, audit và business validation vào một lớp khiến thay đổi một concern ảnh hưởng tất cả phần còn lại.

## 10. Kiểm thử các mối quan tâm xuyên tầng

Kiểm thử nên xác nhận đúng điểm can thiệp và đúng phạm vi:

| Thành phần | Cách kiểm thử | Điều cần xác nhận |
|---|---|---|
| Filter | Mock request/response và FilterChain hoặc dùng integration test Servlet | Header được thiết lập, chain được gọi đúng, context được dọn kể cả khi có exception |
| HandlerInterceptor | Gọi MVC test với handler phù hợp | preHandle, afterCompletion và path exclusion hoạt động đúng |
| Decorator | Unit test với delegate giả lập | Delegate được gọi đúng, kết quả/exception được giữ, metrics/cache/audit theo hợp đồng |
| Middleware pipeline | Test chuỗi nhiều middleware | Thứ tự chạy, short-circuit, xử lý lỗi và finally đúng |
| Tích hợp toàn ứng dụng | Gửi request qua Spring test context | Filter, interceptor, controller và service được lắp ráp đúng, không lặp xử lý ngoài ý muốn |

Không nên chỉ kiểm thử rằng một method đã được gọi. Hãy kiểm tra các trường hợp quan trọng: request bị chặn, delegate ném exception, response đã commit, async dispatch, cache hit/miss hoặc nhiều request chạy trên cùng thread pool. Với concern bảo mật, cần kiểm thử cả trường hợp được phép và bị từ chối, bao gồm các đường dẫn và phương thức HTTP liên quan.

## 11. Checklist trước khi thêm một cơ chế

Trước khi viết filter, interceptor, middleware hoặc decorator, hãy trả lời:

1. Concern này thuộc biên HTTP, vòng đời MVC, pipeline tổng quát hay một dịch vụ cụ thể?
2. Nó cần biết request, handler hay chỉ một interface Java?
3. Nó có quyền chặn luồng, sửa dữ liệu, thử lại hay chỉ quan sát?
4. Thứ tự chạy với các bước khác có ảnh hưởng đến kết quả không?
5. Context và tài nguyên được dọn thế nào khi có exception hoặc async dispatch?
6. Có nguy cơ xử lý trùng, retry lặp hoặc làm thay đổi semantics của hợp đồng không?
7. Có test cho đường thành công, đường lỗi và trường hợp bị short-circuit không?

Middleware, filter, interceptor và decorator đều giúp tách mối quan tâm xuyên tầng khỏi logic chính, nhưng mỗi cơ chế có một điểm can thiệp riêng. Đặt xử lý đúng điểm giúp code dễ hiểu, dễ kiểm thử và giữ cho các tầng trong kiến trúc phân tầng tập trung vào trách nhiệm mà chúng sở hữu.
