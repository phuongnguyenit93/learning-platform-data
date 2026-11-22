# Đo thời gian của từng chặng xử lý MVC

## 1. Vì sao cần đo từng chặng?

Trong ứng dụng Model–View–Controller, một request đi qua nhiều thành phần: bộ lọc bảo mật, binding dữ liệu, Controller, Service, Model, Repository, cơ sở dữ liệu và bước render View hoặc serialize response. Người dùng chỉ nhìn thấy tổng thời gian chờ, nhưng nguyên nhân chậm có thể nằm ở bất kỳ chặng nào.

Ví dụ, trang danh sách sách mất 1,8 giây để hiển thị. Nếu chỉ đo tổng thời gian, nhóm phát triển chưa biết nên xem lại truy vấn SQL, gọi dịch vụ bên ngoài, xử lý trong Service hay render template. Đo từng chặng giúp trả lời:

- Thời gian nằm chủ yếu ở tầng nào?
- Chặng nào có độ trễ tăng khi tải cao?
- Có request nào chậm bất thường dù thời gian trung bình vẫn tốt?
- Một thay đổi tối ưu có thực sự cải thiện trải nghiệm hay chỉ chuyển chi phí sang chặng khác?

Đo thời gian là nền tảng của tối ưu hiệu năng. Hãy xác định ranh giới đo trước, dùng đồng hồ phù hợp, thu thập số liệu ở mức đủ chi tiết và so sánh trên cùng điều kiện tải.

## 2. Bản đồ các chặng của một request MVC

Một request HTML phía máy chủ có thể được chia thành các chặng sau:

~~~mermaid
flowchart TD
    A[Browser gửi request] --> B[Web server / Filter chain]
    B --> C[Security: authentication, authorization, CSRF]
    C --> D[DispatcherServlet và Handler Mapping]
    D --> E[Binding và validation]
    E --> F[Controller]
    F --> G[Application Service / Domain]
    G --> H[Repository]
    H --> I[Connection pool và Database]
    I --> H
    H --> G
    G --> F
    F --> J[View rendering / JSON serialization]
    J --> K[Response được gửi về Browser]
    K --> L[Browser parse, layout và paint]
~~~

Không phải mọi request đều đi qua tất cả các chặng. Một request bị từ chối ở security filter có thể chưa đến Controller; một API JSON không render template HTML; một trang có thể gọi thêm dịch vụ bên ngoài hoặc tải dữ liệu bất đồng bộ.

| Chặng | Nội dung có thể tiêu tốn thời gian |
|---|---|
| Web server và filter | Nhận request, TLS termination ở proxy, filter, session, logging, security |
| Routing và binding | Tìm handler, chuyển kiểu, validate request |
| Controller | Điều phối, chuyển DTO, chọn response |
| Service và Model | Quy tắc nghiệp vụ, tính toán, điều phối use case |
| Repository | Mapping, tạo truy vấn, quản lý persistence context |
| Connection pool và database | Chờ connection, thực thi SQL, lock, đọc dữ liệu và truyền kết quả |
| Dịch vụ bên ngoài | DNS, kết nối, timeout, xử lý và phản hồi từ API khác |
| View/serialization | Render template, format dữ liệu, serialize JSON |
| Network và browser | Truyền response, tải tài nguyên, parse HTML, layout, paint và chạy JavaScript |

Ranh giới đo phải được ghi rõ. Ví dụ, “thời gian repository” có thể bao gồm chờ connection, thực thi SQL và ánh xạ Entity; nó không đồng nghĩa với thời gian database chạy câu SQL.

## 3. Phân biệt thời gian phía server và thời gian người dùng cảm nhận

**Server-side latency** đo thời gian request được xử lý trong phạm vi server hoặc ứng dụng. Có thể bắt đầu ở servlet filter và kết thúc khi xử lý servlet hoàn tất.

**Client-perceived latency** đo từ lúc trình duyệt bắt đầu thao tác đến khi nội dung quan trọng có thể sử dụng. Nó còn bao gồm DNS, TCP/TLS, network, thời gian chờ server, tải tài nguyên tĩnh, JavaScript, layout và paint.

Do đó, server trả response trong 150 ms không bảo đảm trang hiển thị trong 150 ms. Một trang có thể tải nhiều ảnh hoặc script, hoặc JavaScript chặn main thread sau khi HTML đã về.

Đối với API, client có thể đo thời gian từ lúc gửi request đến khi đọc xong response. Đối với trang web, có thể kết hợp browser Performance API và các chỉ số trải nghiệm như Largest Contentful Paint (LCP), Interaction to Next Paint (INP) và Cumulative Layout Shift (CLS). Các chỉ số trình duyệt bổ sung cho metrics phía server, không thay thế chúng.

## 4. Đo thời lượng bằng đồng hồ monotonic

Trong Java, dùng `System.nanoTime()` để đo khoảng thời gian đã trôi qua. Đây là đồng hồ đơn điệu phù hợp cho duration; giá trị của nó không phải thời gian lịch và không dùng để hiển thị ngày giờ.

~~~java
long startedAt = System.nanoTime();
try {
    processRequest();
} finally {
    long elapsedNanos = System.nanoTime() - startedAt;
    long elapsedMillis = elapsedNanos / 1_000_000;
    logger.debug("stage=process_request duration_ms={}", elapsedMillis);
}
~~~

`finally` bảo đảm thời lượng vẫn được ghi nhận khi thao tác phát sinh exception. Chỉ log duration khi cần chẩn đoán chi tiết; với hệ thống có lưu lượng lớn, metrics và tracing thường phù hợp hơn việc ghi một log cho mọi chặng của mọi request.

Không dùng `System.currentTimeMillis()` để đo duration vì đồng hồ hệ thống có thể được điều chỉnh. Cũng không lấy thời gian bắt đầu và kết thúc từ hai máy khác nhau rồi trừ trực tiếp nếu chưa xử lý sai lệch đồng hồ.

## 5. Đo tổng thời gian xử lý request trong Spring MVC

### Đo quanh servlet bằng Filter

Servlet Filter có thể bao quanh chuỗi xử lý servlet. Đây là vị trí phù hợp để đo thời gian server-side từ lúc request đi vào filter đến khi chuỗi xử lý trả quyền điều khiển:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestTimingFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        long startedAt = System.nanoTime();
        try {
            filterChain.doFilter(request, response);
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            log.debug(
                    "http_method={} status={} duration_ms={}",
                    request.getMethod(),
                    response.getStatus(),
                    elapsedNanos / 1_000_000.0);
        }
    }
}
~~~

Đoạn mã cần các import `Logger` và `LoggerFactory` từ SLF4J. Filter bao gồm các filter đứng sau nó và phần xử lý servlet được gọi trong `filterChain.doFilter`. Vị trí đăng ký filter trong chain ảnh hưởng đến phạm vi đo; hãy xác định rõ filter đang đứng trước hay sau Spring Security và các filter khác.

Đối với request xử lý bất đồng bộ, `doFilterInternal` có thể kết thúc khi request chuyển sang async, trong khi công việc thực tế vẫn tiếp tục. Khi đó, duration trong `finally` chỉ phản ánh lần dispatch ban đầu. Cần dùng async listener hoặc instrumentation tương thích với async lifecycle để đo đến khi hoàn tất; không xem thời gian ban đầu là toàn bộ latency.

Filter cũng không đo được thời gian trình duyệt nhận đủ byte, parse HTML hay paint. Nếu có reverse proxy hoặc load balancer, cần xem thêm metrics ở các lớp đó để tách thời gian queueing và network.

### Đo phần xử lý MVC bằng HandlerInterceptor

Spring MVC `HandlerInterceptor` có thể đo từ trước khi gọi handler đến sau khi View được render. `preHandle` lưu mốc bắt đầu; `afterCompletion` tính thời lượng:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class MvcTimingInterceptor implements HandlerInterceptor {
    private static final String STARTED_AT =
            MvcTimingInterceptor.class.getName() + ".startedAt";

    private final MeterRegistry registry;

    public MvcTimingInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        request.setAttribute(STARTED_AT, System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        Object value = request.getAttribute(STARTED_AT);
        if (!(value instanceof Long startedAt)) {
            return;
        }

        Timer.builder("mvc.stage.duration")
                .tag("stage", "handler_and_view")
                .tag("method", request.getMethod())
                .tag("status", Integer.toString(response.getStatus()))
                .register(registry)
                .record(System.nanoTime() - startedAt,
                        TimeUnit.NANOSECONDS);
    }
}
~~~

Để đăng ký interceptor, thêm nó vào `WebMvcConfigurer#addInterceptors`. Ví dụ cần các import Micrometer `MeterRegistry`, `Timer` và `TimeUnit` từ `java.util.concurrent`. Đoạn này tính từ sau khi Spring MVC đã chọn handler đến sau khi xử lý handler và View hoàn tất; nó không bao gồm filter chạy trước `DispatcherServlet` hoặc thời gian chờ trước khi request đến interceptor.

Ví dụ cấu hình đăng ký:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class MvcTimingConfiguration implements WebMvcConfigurer {
    private final MvcTimingInterceptor timingInterceptor;

    public MvcTimingConfiguration(MvcTimingInterceptor timingInterceptor) {
        this.timingInterceptor = timingInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(timingInterceptor);
    }
}
~~~

`afterCompletion` được gọi cho quá trình xử lý đồng bộ sau khi handler hoàn tất, kể cả khi có exception được xử lý theo pipeline MVC. Với async request, vòng đời có thể gồm nhiều dispatch; cần đo async completion riêng và tránh ghi nhận hai lần cho cùng một logical request.

## 6. Đo riêng Controller, Service và Repository

Để tìm bottleneck, tổng thời gian request là chưa đủ. Hãy đặt mốc ở các ranh giới có ý nghĩa. Không nhất thiết đo mọi dòng code; đo những thao tác có khả năng tốn thời gian hoặc có phụ thuộc bên ngoài.

### Đo thời gian một use case bằng Micrometer Timer

Spring Boot thường tích hợp Micrometer. `Timer` ghi nhận số lần thực hiện và thời lượng, từ đó có thể quan sát tổng thời gian, thời gian tối đa và phân phối duration khi cấu hình histogram phù hợp.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;

@Service
public class TimedBookQueryService {
    private final MeterRegistry registry;
    private final BookRepository books;

    public TimedBookQueryService(
            MeterRegistry registry,
            BookRepository books) {
        this.registry = registry;
        this.books = books;
    }

    public List<Book> search(String query) {
        Timer.Sample sample = Timer.start(registry);
        try {
            return books.search(query);
        } finally {
            sample.stop(Timer.builder("mvc.stage.duration")
                    .tag("stage", "service")
                    .tag("operation", "book_search")
                    .register(registry));
        }
    }
}
~~~

Ví dụ cần import `List` và các kiểu `Book`, `BookRepository`. `Timer.Sample` được dừng trong `finally`, vì vậy cả lần gọi thành công và lần gọi phát sinh exception đều được tính. `operation` là tên cố định do ứng dụng định nghĩa; không đưa từ khóa tìm kiếm, email, user ID hoặc URL chứa ID vào tag.

Để đo Repository riêng, đặt một Timer quanh lời gọi repository hoặc dùng instrumentation ở tầng JDBC/JPA. Nếu Service timer bao trùm Repository timer, hai số đo là các khoảng thời gian lồng nhau. Không cộng chúng lại để tính tổng request vì như vậy sẽ đếm trùng thời gian.

### Phân biệt thời gian Repository và thời gian SQL

Thời gian của một lời gọi repository có thể gồm:

1. Chờ lấy connection từ pool.
2. Chuẩn bị statement và bind tham số.
3. Database thực thi câu SQL, chờ lock hoặc đọc dữ liệu.
4. Truyền kết quả qua mạng.
5. ORM ánh xạ kết quả thành Entity/DTO.
6. Tải quan hệ lazy hoặc thực hiện thêm truy vấn phụ.

Để biết database thực sự chậm ở đâu, cần quan sát SQL duration ở phía driver/database, connection pool wait, số lượng query và thời gian mapping. Một phương thức repository có thể chậm do N+1 queries dù từng câu SQL riêng lẻ đều nhanh.

Với JPA, SQL có thể được thực thi muộn khi flush hoặc khi truy cập quan hệ lazy. Đo quanh `save()` hoặc `findById()` không phải lúc nào cũng bao phủ mọi câu SQL phát sinh trong transaction. Dùng tracing/instrumentation JDBC và kiểm tra query thực tế để hiểu đầy đủ.

## 7. Đo thời gian render View và serialize response

Trong ứng dụng MVC render phía máy chủ, View rendering diễn ra sau khi Controller trả về tên View hoặc `ModelAndView`. Nếu đo ở `HandlerInterceptor#afterCompletion`, thời gian thường bao gồm xử lý handler và render View, nhưng không tách riêng hai phần.

Muốn tách riêng, có thể instrument template engine, view resolver hoặc bước render cụ thể tùy framework. Trước khi thêm instrumentation tùy biến, hãy kiểm tra các metrics/traces framework đã cung cấp để tránh đo trùng.

Đối với REST API, response serialization có thể tốn thời gian nếu DTO lớn, có cấu trúc lồng sâu hoặc cần format nhiều trường. Có thể đo riêng converter/serialization nếu số liệu cho thấy đây là bottleneck. Đừng giả định thời gian Controller kết thúc là response đã được serialize và gửi xong.

Render chậm có thể do:

- Template có nhiều fragment hoặc biểu thức gọi phương thức lặp lại.
- Lazy loading phát sinh thêm truy vấn trong lúc render.
- Chuyển đổi định dạng ngày, tiền tệ hoặc nội dung lớn.
- Serialize một object graph quá sâu hoặc có quá nhiều phần tử.
- Nén response hoặc ghi response qua mạng chậm.

View Model nhỏ và rõ ràng giúp hạn chế việc template vô tình truy cập dữ liệu persistence hoặc kéo theo truy vấn bổ sung.

## 8. Metrics, logs và distributed tracing

Ba loại dữ liệu quan sát có mục đích khác nhau:

| Công cụ | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Metrics | Hệ thống đang hoạt động ra sao theo thời gian? | p95 request latency, số request/giây, lỗi theo status |
| Logs | Một sự kiện hoặc request cụ thể đã xảy ra điều gì? | Request ID, lỗi nghiệp vụ, timeout database |
| Traces | Một request đi qua các thành phần nào và mỗi chặng mất bao lâu? | HTTP server → Service → JDBC → HTTP client |

Metrics phù hợp để phát hiện xu hướng và cảnh báo. Logs cung cấp ngữ cảnh cho một sự kiện. Traces cho thấy các span lồng nhau và quan hệ giữa các dịch vụ trong cùng một request.

### Metrics mặc định của Spring Boot

Khi ứng dụng có Spring Boot Actuator và Micrometer registry phù hợp, Spring Boot có thể cung cấp HTTP server request metrics, thường được đặt tên `http.server.requests`. Timer này hỗ trợ phân tích số lượng và thời lượng request theo các tag như method, status, outcome và URI template tùy phiên bản/cấu hình.

Để xem phân phối latency, cấu hình histogram hoặc percentile phù hợp với backend metrics. Ví dụ cấu hình percentile histogram cho timer MVC tùy chỉnh:

~~~java
Timer.builder("mvc.stage.duration")
        .tag("stage", "service")
        .tag("operation", "book_search")
        .publishPercentileHistogram()
        .register(registry);
~~~

Histogram tạo thêm chuỗi thời gian và chi phí lưu trữ. Chỉ bật cho các metric cần phân tích phân phối, giữ tập tag nhỏ và đặt chính sách retention phù hợp.

### Distributed tracing

Trong hệ thống gọi nhiều dịch vụ, một request có thể đi qua gateway, MVC application, database và dịch vụ bên ngoài. Distributed tracing gắn các span với trace context để xem toàn bộ hành trình.

Ví dụ trace có thể cho thấy:

- HTTP server span: 900 ms.
- Service span: 820 ms.
- Database span: 120 ms.
- External API span: 650 ms.
- Phần còn lại: xử lý trong ứng dụng và serialization.

Các span có thể lồng nhau hoặc chạy song song; không cộng duration của mọi span để suy ra tổng latency. Dùng trace timeline và quan hệ parent-child để hiểu phần thời gian nào nằm bên trong phần nào.

Spring Boot có thể tích hợp Micrometer Observation và tracing bridge phù hợp để truyền trace context. Với tác vụ bất đồng bộ, cần truyền context qua executor hoặc dùng cơ chế context propagation; nếu mất trace context, span của task có thể tách khỏi request ban đầu.

## 9. Đọc số liệu: trung bình, p50, p95 và p99

Thời gian trung bình (average) hữu ích để xem xu hướng tổng thể nhưng có thể che giấu request chậm. Nếu 99 request mất 50 ms và một request mất 5 giây, trung bình vẫn có thể trông chấp nhận được trong khi một số người dùng gặp trải nghiệm rất tệ.

- **p50 (median):** một nửa số request nhanh hơn hoặc bằng giá trị này.
- **p95:** 95% request nhanh hơn hoặc bằng giá trị này; 5% chậm hơn.
- **p99:** 99% request nhanh hơn hoặc bằng giá trị này; 1% chậm hơn.
- **Maximum:** giá trị lớn nhất quan sát được trong khoảng thời gian đo; nhạy với outlier và số lượng mẫu.

Ví dụ:

| Chỉ số | Trước tối ưu | Sau tối ưu |
|---|---:|---:|
| p50 | 90 ms | 75 ms |
| p95 | 850 ms | 260 ms |
| p99 | 2.400 ms | 900 ms |

Trong ví dụ, cải thiện p95 và p99 lớn hơn cải thiện p50. Điều này có thể cho thấy tối ưu đã giảm những trường hợp chậm ở đuôi phân phối. Đây chỉ là số minh họa; khi so sánh thực tế, cần dùng cùng workload, thời lượng quan sát và điều kiện môi trường.

Không so sánh percentile được tính từ các nhóm mẫu quá nhỏ hoặc cửa sổ thời gian khác nhau. Với histogram metrics, percentile phía backend có thể được ước lượng từ bucket; độ chính xác phụ thuộc cấu hình bucket.

## 10. Cardinality và chi phí của instrumentation

Metrics có tag giúp phân tích theo nhóm, nhưng mỗi tổ hợp tag có thể tạo một time series. Nếu tag chứa giá trị thay đổi liên tục như user ID, email, order ID, search query hoặc raw URL, cardinality có thể tăng rất lớn.

Tag nên dùng các giá trị có tập hữu hạn hoặc giới hạn:

| Tag tốt | Tag rủi ro cao |
|---|---|
| `method=GET` | `user_id=...` |
| `status=200` | `email=...` |
| `uri=/books/{id}` | `uri=/books/938472` |
| `stage=repository` | `sql_parameter=...` |
| `operation=book_search` | `query=java+architecture...` |

Không đưa dữ liệu cá nhân hoặc bí mật vào metric tag. Nếu cần điều tra một request cụ thể, dùng trace ID hoặc correlation ID trong log/tracing với chính sách kiểm soát truy cập và retention phù hợp.

Instrumentation cũng có chi phí CPU, bộ nhớ, allocation và network export. Đo quá nhiều đoạn nhỏ hoặc tạo metric động trong vòng lặp có thể làm thay đổi chính hiệu năng đang đo. Hãy đo ở các ranh giới có giá trị, lấy mẫu tracing khi lưu lượng lớn và kiểm tra overhead trước khi triển khai rộng.

## 11. Tìm bottleneck từ kết quả đo

Giả sử request danh sách sách có các số đo:

| Chặng | Thời lượng ví dụ |
|---|---:|
| Filter và security | 18 ms |
| Binding và Controller | 12 ms |
| Service | 35 ms |
| Repository và database | 420 ms |
| Render template | 65 ms |
| Tổng server-side | 550 ms |

Trong ví dụ, Repository/database chiếm phần lớn thời gian. Hãy xem query plan, index, số lượng query, connection pool và N+1 trước khi tối ưu template hoặc Controller.

Nếu database chỉ mất 30 ms nhưng Service mất 500 ms, hãy xem tính toán, vòng lặp gọi API, lock trong ứng dụng hoặc chờ tài nguyên. Nếu server-side chỉ 100 ms nhưng LCP của trình duyệt là 3 giây, hãy kiểm tra ảnh, CSS, JavaScript, font, CDN và render blocking.

Không tối ưu dựa trên cảm giác hoặc một request đơn lẻ. Quy trình hợp lý:

1. Xác định endpoint và hành vi người dùng đang chậm.
2. Thu thập baseline ở môi trường và workload đại diện.
3. Dùng trace để xác định chặng chiếm thời gian hoặc có biến động lớn.
4. Đo sâu hơn ở chặng nghi vấn: query, connection wait, external API, render hoặc serialization.
5. Thay đổi một nguyên nhân có bằng chứng.
6. Chạy lại cùng workload và so sánh p50/p95/p99, throughput và error rate.
7. Theo dõi sau triển khai để xác minh cải thiện trong môi trường thật.

## 12. Đo trong môi trường phát triển và tải thực tế

Đo trên máy cá nhân hữu ích để phát hiện lỗi rõ ràng, nhưng không đại diện đầy đủ cho production. JIT warm-up, cache lạnh, dữ liệu nhỏ, connection pool chưa bão hòa và số request thấp có thể tạo kết quả khác xa tải thực.

Khi benchmark hoặc load test:

- Dùng dữ liệu có kích thước và phân bố gần thực tế.
- Khởi động ứng dụng và chạy warm-up trước khi lấy mẫu.
- Tăng concurrency theo từng mức để thấy thời điểm throughput không tăng nhưng latency tăng.
- Đo cả throughput, error rate, CPU, heap/GC, thread pool và connection pool.
- Giữ cùng phiên bản code, cấu hình, database và workload khi so sánh trước/sau.
- Chạy đủ lâu để quan sát cache, GC và pool dưới tải ổn định.
- Không chạy benchmark nặng trực tiếp trên production nếu chưa có kế hoạch kiểm soát tác động.

Load test cho biết hành vi hệ thống dưới tải tổng hợp; production metrics/traces cho biết hành vi thật với phân bố request và dữ liệu thật. Cần kết hợp cả hai.

## 13. Những sai lầm thường gặp

- **Chỉ đo tổng request:** không chỉ ra chặng gây chậm.
- **Dùng đồng hồ lịch để đo duration:** đồng hồ có thể thay đổi, làm kết quả không ổn định.
- **Cộng các timer lồng nhau:** đếm trùng thời gian Service, Repository và SQL.
- **Gọi thời gian repository là thời gian SQL:** bỏ qua connection pool, mapping và truy vấn phát sinh muộn.
- **Đo `afterCompletion` rồi coi là toàn bộ client latency:** chưa bao gồm network và browser rendering.
- **Bỏ qua async lifecycle:** timer có thể dừng khi task nền vẫn chạy.
- **Chỉ nhìn average:** không phát hiện tail latency ở p95/p99.
- **Tag metric bằng ID hoặc URL thực:** tạo cardinality cao và có thể làm lộ dữ liệu.
- **Ghi log mọi đoạn nhỏ ở mức INFO:** tăng I/O và làm nhiễu log.
- **Tối ưu trước khi có baseline:** khó chứng minh thay đổi có ích.
- **Benchmark với dữ liệu quá nhỏ hoặc không warm-up:** kết quả không đại diện cho tải thực.

## 14. Kết luận

Đo thời gian từng chặng MVC giúp xác định request chậm ở filter/security, binding, Controller, Service, Repository, database, dịch vụ ngoài hay View. Dùng `System.nanoTime()` cho duration trong Java; dùng Filter để quan sát phạm vi servlet và HandlerInterceptor để quan sát handler cùng render trong MVC đồng bộ; dùng Micrometer Timer và distributed tracing để theo dõi theo thời gian và xuyên nhiều thành phần.

Khi phân tích, hãy phân biệt server latency với trải nghiệm trình duyệt, không cộng các khoảng đo lồng nhau, theo dõi p50/p95/p99 và giữ metric tag có cardinality thấp. Baseline, trace và kiểm thử tải giúp quyết định tối ưu dựa trên bằng chứng và xác minh thay đổi có cải thiện hành vi thực tế hay không.
