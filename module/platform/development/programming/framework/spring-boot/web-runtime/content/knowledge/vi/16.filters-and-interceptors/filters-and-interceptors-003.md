# OncePerRequestFilter và các kiểu dispatch REQUEST, ASYNC, ERROR trong Spring Boot

## 1. Mục tiêu bài học

OncePerRequestFilter là lớp cơ sở của Spring Framework để xây dựng Servlet Filter có bảo vệ khỏi việc thực thi doFilterInternal lặp lại trong **cùng một request dispatch**. Tên lớp dễ gây hiểu lầm: một HTTP request của client có thể đi qua nhiều Servlet dispatch, ví dụ REQUEST ban đầu, ASYNC redispatch sau khi controller chạy Callable và ERROR dispatch tới error page. Vì thế cùng một logical HTTP request có thể khiến một OncePerRequestFilter chạy doFilterInternal nhiều hơn một lần nếu lập trình viên chủ động bật các loại dispatch tương ứng.

Bài thuộc chủ đề **Bộ lọc và interceptor** trong **Spring Boot - web-runtime**. Sau bài học, bạn có thể:

1. Phân biệt **logical HTTP request**, **Servlet dispatch**, **FilterChain** và **thread**.
2. Giải thích dấu hiệu **already filtered** và các hook **doFilterInternal**, **shouldNotFilter**, **shouldNotFilterAsyncDispatch**, **shouldNotFilterErrorDispatch** và **doFilterNestedErrorDispatch**.
3. Xác định khi nào có **DispatcherType.REQUEST**, **DispatcherType.ASYNC** và **DispatcherType.ERROR**, kể cả trường hợp ERROR lồng trong REQUEST.
4. Hiểu điều kiện kép: **Servlet container đăng ký dispatcher types** và **OncePerRequestFilter không skip dispatch**.
5. Dùng **FilterRegistrationBean** đúng URL patterns, dispatcher types, asyncSupported và thứ tự filter.
6. Giữ request ID ổn định qua nhiều dispatch mà không dùng sai MDC/ThreadLocal hay đếm trùng metric.
7. Chạy ứng dụng mẫu **Java 17, Spring Boot 3.5, Spring MVC, embedded Tomcat** với request đồng bộ, async Callable và sendError.
8. Viết test qua HTTP thật để xác minh request dispatch, response, correlation ID và các giới hạn error handling.

Các ví dụ dùng **Spring Boot 3.5.16 / Spring Framework 6.2 / Jakarta Servlet / Java 17**. Trong Boot 3.x, package Servlet là **jakarta.servlet**, không phải **javax.servlet** cũ của một số dự án Boot 2.x. Trên Spring WebFlux chạy Reactor Netty, bộ lọc tương ứng là **WebFilter**, không có Servlet DispatcherType như bài này.

## 2. Request và dispatch khác nhau như thế nào?

Một HTTP request của client có thể được Servlet container xử lý qua nhiều lần dispatch. Một dispatch là một lượt container đưa request vào Servlet/filter chain theo loại DispatcherType hiện hành.

### 2.1. Các DispatcherType

| DispatcherType | Ngữ cảnh | Vai trò |
|---|---|---|
| **REQUEST** | Client gửi request ban đầu | Điểm vào thông thường của Servlet Filter |
| **ASYNC** | AsyncContext.dispatch sau xử lý bất đồng bộ | Đưa async result quay về Servlet để hoàn tất |
| **ERROR** | Container chuyển tới error page/error servlet | Xử lý lỗi trong Servlet container |
| **FORWARD** | RequestDispatcher.forward | Chuyển nội bộ tới tài nguyên khác |
| **INCLUDE** | RequestDispatcher.include | Chèn nội dung tài nguyên khác |

Bài tập trung REQUEST/ASYNC/ERROR nhưng không được suy rằng Jakarta Servlet chỉ có ba giá trị. Một Filter có thể được đăng ký cho FORWARD/INCLUDE nếu có nhu cầu tương ứng.

### 2.2. Luồng REQUEST → ASYNC

~~~mermaid
flowchart TD
    A[HTTP client gửi GET /api/async] --> B[REQUEST dispatch]
    B --> C[Servlet FilterChain]
    C --> D[DispatcherServlet]
    D --> E[Controller trả Callable]
    E --> F[request.startAsync]
    F --> G[REQUEST thread kết thúc filter chain, response còn mở]
    G --> H[Callable thực thi trên executor thread]
    H --> I[Servlet container ASYNC redispatch]
    I --> J[FilterChain nếu mapping ASYNC]
    J --> K[DispatcherServlet lấy async result]
    K --> L[Ghi response và hoàn tất]
~~~

**Có một request từ phía client nhưng hai dispatch Servlet.** Nếu Filter tham gia cả REQUEST và ASYNC thì **doFilterInternal có thể được gọi ở mỗi pha**. Thread chạy Callable không phải tự thân là một Servlet dispatch; filter không tự bọc logic thực thi của Callable ở executor thread.

### 2.3. Luồng REQUEST → ERROR

~~~mermaid
flowchart TD
    A[REQUEST dispatch] --> B[Controller hoặc Servlet]
    B --> C{Lỗi được xử lý ở đâu?}
    C -->|@ExceptionHandler xử lý, trả JSON| D[Response hoàn tất ngay trong REQUEST]
    C -->|sendError hoặc lỗi chuyển về container| E[Container có error mapping?]
    E -->|Có| F[ERROR dispatch tới error page, có thể /error]
    F --> G[FilterChain nếu đăng ký ERROR]
    G --> H[Error controller/page trả response]
    E -->|Không| I[Container xử lý lỗi theo chính sách riêng]
~~~

**Một HTTP status 404/500/503 không tự chứng minh có ERROR dispatch.** Controller trả ResponseEntity với status lỗi hoặc một @ExceptionHandler xử lý exception hoàn toàn trong Spring MVC có thể không kích hoạt Servlet ERROR dispatch.

### 2.4. Vì sao thread quan trọng?

REQUEST, ASYNC và ERROR có thể diễn ra trên các thread khác nhau. Với Callable, executor thread chạy công việc không phải thread REQUEST ban đầu, và ASYNC redispatch có thể dùng một container thread khác nữa. Vì vậy:

- **HttpServletRequest attributes** thích hợp để giữ request ID liên tục trong logical request, nếu có request wrapper/dispatch thích hợp.
- **ThreadLocal/MDC** chỉ có phạm vi thread: phải thiết lập lại ở mỗi thread tham gia và dọn trong finally.
- Một **singleton Filter field** không thích hợp để lưu requestId, status hoặc startTime theo từng request.
- Đừng dùng Thread.sleep hoặc logic blocking không kiểm soát trong filter chain vì chiếm Servlet container threads.

## 3. Cơ chế của OncePerRequestFilter

Import:

~~~java
import org.springframework.web.filter.OncePerRequestFilter;
~~~

OncePerRequestFilter kế thừa **GenericFilterBean** và hiện thực phương thức **doFilter**. Lập trình viên thường chỉ override:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    chain.doFilter(request, response);
}
~~~

Đoạn trên là phương thức trong một class kế thừa OncePerRequestFilter, chưa phải class độc lập. Để sử dụng trong Boot 3.5 cần các import từ jakarta.servlet và jakarta.servlet.http.

### 3.1. Marker already filtered

Cơ chế nội bộ (diễn giải logic, không phải source code nguyên văn):

~~~text
Servlet container gọi OncePerRequestFilter.doFilter(...)
  ├─ Nếu dispatch/request bị skip: gọi chain, không gọi doFilterInternal
  ├─ Nếu request đã có marker FILTERED:
  │    ├─ Nếu là nested ERROR: gọi doFilterNestedErrorDispatch(...)
  │    └─ Nếu không: chỉ gọi chain, tránh doFilterInternal lặp trong dispatch
  └─ Nếu chưa có marker:
       ├─ Set request attribute <filter-name>.FILTERED
       ├─ Gọi doFilterInternal(...)
       └─ finally: remove request attribute .FILTERED
~~~

Method **getAlreadyFilteredAttributeName()** xác định tên marker, mặc định dựa trên tên filter và hậu tố **.FILTERED**. Khi doFilterInternal kết thúc, marker được **gỡ trong finally**, kể cả khi ném exception.

Hệ quả quan trọng:

- Filter chỉ cố tránh **thực thi trùng trong một dispatch đang hoạt động**.
- Sau khi REQUEST dispatch thoát chain, marker không còn. ASYNC dispatch mới có thể gọi doFilterInternal lần nữa nếu không bị skip.
- ERROR dispatch mới có thể chạy tương tự; riêng nested ERROR khi marker còn tồn tại có hook riêng.
- Marker **khác với correlation ID**. Không dùng marker để lưu request state lâu dài.
- Nếu code nghiệp vụ cần đảm bảo thao tác chỉ chạy một lần cho toàn request hoặc giao dịch, phải có idempotency/transaction logic riêng. Tên class không tự đảm bảo điều đó.

### 3.2. Các hook và giá trị mặc định

| Hook | Default ở Spring Framework 6.2 | Ý nghĩa |
|---|---|---|
| **shouldNotFilter(request)** | **false** | Theo mặc định không tự skip request |
| **shouldNotFilterAsyncDispatch()** | **true** | Theo mặc định bỏ qua ASYNC redispatch |
| **shouldNotFilterErrorDispatch()** | **true** | Theo mặc định bỏ qua ERROR dispatch |
| **isAsyncDispatch(request)** | Helper | Kiểm tra dispatch hiện tại đang ở pha ASYNC |
| **isAsyncStarted(request)** | Helper | Cho biết async processing đã bắt đầu và còn pha xử lý sau |
| **doFilterNestedErrorDispatch** | Chuyển tiếp chain | Cho phép xử lý ERROR lồng khi marker đã tồn tại |

Tên **shouldNotFilter** là câu hỏi phủ định: để **lọc ASYNC**, cần **return false**:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false;
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return false;
}
~~~

Đó là override phục vụ ví dụ muốn theo dõi đủ các pha. Khi chỉ cần REQUEST, giá trị mặc định true của cả hai hook có thể là lựa chọn hợp lý.

### 3.3. Hai cổng phải cùng cho phép

**Cổng A: Servlet filter registration** phải map filter tới URL hoặc servlet và dispatcher type hiện tại. Ví dụ:

~~~java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
~~~

**Cổng B: OncePerRequestFilter** phải không skip dispatch và không bị marker ngăn doFilterInternal.

| Registration | Skip hook | Có ASYNC thực tế? | doFilterInternal tại ASYNC |
|---|---|---|---|
| Chỉ REQUEST | false | Có | **Không**, container không gọi Filter |
| REQUEST + ASYNC | true | Có | **Không**, OncePerRequestFilter skip |
| REQUEST + ASYNC | false | Có | **Có**, khi lượt dispatch được gọi |
| REQUEST + ASYNC + ERROR | async/error đều false | ERROR được container tạo | **Có thể chạy ERROR**, tùy loại error dispatch |

Không chỉ đặt **setAsyncSupported(true)** rồi suy rằng filter sẽ được gọi trong ASYNC. asyncSupported cho phép Servlet async, còn **setDispatcherTypes** quy định những dispatch nào container map tới filter.

Spring Boot 3.5 có cơ chế suy ra dispatcher types mặc định khi dùng FilterRegistrationBean với OncePerRequestFilter; nhưng kết quả có thể phụ thuộc phiên bản/đường đăng ký. Đối với bài học này, **luôn ghi rõ dispatcher types** để người đọc biết chính xác cấu hình.

### 3.4. isAsyncDispatch khác isAsyncStarted

- **isAsyncDispatch(request)**: nhận diện luồng dispatch async đang được xử lý.
- **isAsyncStarted(request)**: nhận diện request đã chuyển sang async và dispatch hiện tại chưa phải pha kết thúc thông thường.

Với một controller trả Callable, thông thường ở cuối REQUEST dispatch có thể thấy:

~~~text
dispatcherType=REQUEST
isAsyncDispatch=false
isAsyncStarted=true
~~~

Khi container redispatch để ghi async result, thường thấy:

~~~text
dispatcherType=ASYNC
isAsyncDispatch=true
isAsyncStarted=false
~~~

Những dòng trên mô tả trạng thái **thường gặp**, không phải stdout cố định. Async streaming hoặc cách container xử lý có thể tạo trạng thái khác. Nếu cần biết chính xác, log request.getDispatcherType và các helper trong môi trường đang chạy.

## 4. REQUEST dispatch

REQUEST là lượt xử lý ban đầu của HTTP request. Một OncePerRequestFilter mặc định thích hợp để:

- Tạo correlation/request ID từ server hoặc xác minh ID của trusted upstream.
- Đặt request attributes cho controller và các lớp downstream.
- Đặt response header trước khi body được commit.
- Quan sát method, path đã được sanitize, status và exception.
- Thực hiện chức năng HTTP-level cross-cutting theo contract.

Ví dụ trong doFilterInternal:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
response.setHeader("X-Request-Id", requestId);
chain.doFilter(request, response);
~~~

Đây chỉ là đoạn minh họa. **Không dùng cách luôn sinh UUID mới như trên khi Filter cũng chạy ASYNC/ERROR**; phần demo đầy đủ sẽ chỉ tạo ID khi request attribute chưa tồn tại.

### 4.1. Tránh log hoặc sửa response quá muộn

Filter có thể dùng finally để cleanup:

~~~java
long start = System.nanoTime();
try {
    chain.doFilter(request, response);
} finally {
    long dispatchDurationNs = System.nanoTime() - start;
}
~~~

Nhưng với REQUEST xử lý async, code sau chain.doFilter có thể chạy **trước khi HTTP response hoàn tất**. Con số đo được chỉ là thời gian dispatch hiện tại. Nếu đo tổng request latency, dùng **AsyncListener** hoặc observability đã tích hợp, không đổi tên số đo thành end-to-end duration.

### 4.2. shouldNotFilter theo đường dẫn

Có thể override:

~~~java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return request.getServletPath().startsWith("/public/");
}
~~~

Đoạn này minh họa cách skip theo request. Nhưng trong ERROR dispatch, servlet path có thể là **/error**, không còn là original request URI. Nếu bạn cần xử lý ERROR, kiểm tra **jakarta.servlet.error.request_uri** khi có, thay vì chỉ đọc servletPath.

## 5. ASYNC dispatch và Spring MVC

Spring MVC hỗ trợ **Callable**, **DeferredResult**, **WebAsyncTask**, **ResponseBodyEmitter** và **SseEmitter**. Một phương thức controller có thể trả Callable để Spring MVC thực hiện logic trong executor mà không giữ Servlet request thread chờ.

Luồng Callable:

1. REQUEST đi qua Filter, DispatcherServlet và controller.
2. Controller trả Callable; Spring MVC gọi request.startAsync và dùng AsyncTaskExecutor.
3. REQUEST thread rời FilterChain nhưng response còn mở.
4. Callable chạy trên executor thread, hoàn tất hoặc phát lỗi.
5. Spring MVC yêu cầu Servlet container ASYNC redispatch.
6. Container chạy filters đã map ASYNC; DispatcherServlet ghi result.
7. Response hoàn tất, hoặc có timeout/error/cancellation khác.

**Quan trọng:** Override shouldNotFilterAsyncDispatch(false) cho phép filter tham gia **redispatch**, không phải biến filter thành wrapper quanh code Callable ở executor thread. Muốn truyền MDC/security/request context đến Callable thread cần cơ chế executor propagation và các callback tương ứng.

### 5.1. Cấu hình nhất quán

Trong FilterRegistrationBean:

~~~java
registration.setAsyncSupported(true);
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
~~~

Trong OncePerRequestFilter subclass:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false;
}
~~~

Filter/Servlet liên quan còn phải có async support tương thích. Khi tự cấu hình web.xml hoặc container bên ngoài, đừng chỉ nhìn một bean Boot và bỏ qua cấu hình thực tế của container.

### 5.2. Async lifecycle và metric

| Pha | Thread | Filter có thể quan sát | Response cuối cùng? |
|---|---|---|---|
| REQUEST trước controller | Container thread | doFilterInternal REQUEST | Chưa |
| Callable chạy nền | Executor thread | Không được filter bao tự động | Chưa |
| REQUEST finally | Container thread | isAsyncStarted có thể true | Chưa |
| ASYNC redispatch | Container thread khác | doFilterInternal ASYNC nếu enabled | Có thể hoàn tất |
| Async timeout/error | Nhiều trường hợp | AsyncListener/exception dispatch tùy flow | Phụ thuộc |

Nếu cần tổng thời gian HTTP request, dùng **AsyncListener.onComplete/onTimeout/onError** hoặc instrumentation của **Micrometer Observation/Tracing**. Nếu async cycle được bắt đầu lại, phải hiểu **onStartAsync** và tránh duplicate listeners hoặc double-count metrics. Trong production, cấu hình **AsyncTaskExecutor**, timeout và queue một cách có kiểm soát.

## 6. ERROR dispatch

**ERROR dispatch** là một lượt dispatch của Servlet container tới error page, thường có đường đích **/error** trong Spring Boot Servlet MVC. Nó không được kích hoạt chỉ vì status cuối cùng là lỗi.

| Hành vi | Có chắc ERROR dispatch? | Lưu ý |
|---|---|---|
| Controller trả ResponseEntity.status(404) | Không | Có thể hoàn tất trực tiếp trong REQUEST |
| @ExceptionHandler trả ProblemDetail 500 | Không | Exception đã xử lý trong MVC |
| Controller gọi response.sendError(503) | Có thể | Container có thể dispatch error page |
| Unhandled exception thoát tới container | Có thể | Phụ thuộc resolver/error mapping |
| Reverse proxy chặn request trước ứng dụng | Không | Servlet không thấy request |
| Response đã commit rồi mới lỗi | Không bảo đảm | Không thể thay status/body tùy ý |

Để ERROR đi qua Filter, cần cả **DispatcherType.ERROR** trong registration, **shouldNotFilterErrorDispatch() trả false**, và URL pattern khớp đích error dispatch. Ví dụ registration **/api/*** ở Servlet không nhất thiết khớp route **/error**. Chọn **"/*"** trong demo để kiểm tra cả hai.

### 6.1. ERROR tách biệt

Ở nhiều container, REQUEST dispatch kết thúc, marker already-filtered bị gỡ, rồi ERROR dispatch bắt đầu qua một chain mới. Với cờ skip false và mapping ERROR thích hợp, **doFilterInternal** sẽ chạy trong lượt ERROR đó.

### 6.2. Nested ERROR

Một số container có thể tạo ERROR dispatch **lồng trong REQUEST dispatch đang hoạt động**, trên cùng thread, trong khi marker already-filtered vẫn hiện diện. Khi đó OncePerRequestFilter có hook riêng:

~~~java
@Override
protected void doFilterNestedErrorDispatch(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain)
        throws ServletException, IOException {

    // Có thể tái áp dụng request/response wrapper nếu container đã thay đổi.
    chain.doFilter(request, response);
}
~~~

Mặc định hook này chuyển tiếp FilterChain. Nó hữu ích khi một Filter đã wrap HttpServletRequest/HttpServletResponse nhưng nested ERROR dùng lại các wrapper gốc. **Không đồng nhất hook nested ERROR với doFilterInternal cho ERROR tách biệt**.

Trong nested ERROR, ThreadLocal của REQUEST có thể vẫn còn hiệu lực vì request chain chưa thoát, nên không tùy tiện xóa context dùng chung trước khi phần REQUEST bên ngoài hoàn tất.

### 6.3. Đường dẫn và error attributes

Trong ERROR dispatch, Servlet container có thể cung cấp:

~~~text
jakarta.servlet.error.request_uri
jakarta.servlet.error.status_code
jakarta.servlet.error.exception
jakarta.servlet.error.message
~~~

Không phải mọi attribute đều có mặt trong mọi loại lỗi. request.getRequestURI có thể trả **/error**, còn attribute **jakarta.servlet.error.request_uri** nói URI gốc khi được container thiết lập. Không log raw exception/request body có credential hoặc dữ liệu nhạy cảm.

### 6.4. Tránh double-count

Nếu bạn tăng bộ đếm HTTP client request ở mỗi lần doFilterInternal, một request trải qua REQUEST rồi ASYNC hoặc ERROR sẽ bị đếm nhiều lần. Có hai loại metric cần đặt tên rõ:

- **Dispatch attempts**: đếm từng REQUEST/ASYNC/ERROR dispatch.
- **Logical HTTP requests**: đếm một lần cho mỗi yêu cầu client.

Để ghi nhận metric cuối cùng một lần, dùng marker nghiệp vụ riêng trong request và callback request completion phù hợp, không dùng marker **.FILTERED** để đo tổng lifecycle.

## 7. Khi nào nên bật cả ba loại dispatch?

**Chọn chỉ REQUEST** nếu Filter chỉ làm việc cần một lần lúc bắt đầu, ví dụ thiết lập request ID vào request attribute. Việc bật thêm ASYNC/ERROR không tự làm ứng dụng an toàn hơn; có thể thêm log trùng, quá tải hoặc làm sai response.

**Chọn ASYNC** nếu Filter cần thiết lập context hoặc wrapping ở cả redispatch, theo dõi xử lý sau khi Callable hoàn tất, hoặc chức năng cần hoạt động trong Servlet async phase.

**Chọn ERROR** nếu cần tracing hoặc request/response wrapper ở error page dispatch. Nếu filter chỉ áp dụng cho handler route và không cần chạy tại /error, có thể không bật.

**Chọn nested ERROR hook** khi Filter có wrapper phức tạp và container tạo error dispatch lồng. Không override hook chỉ để đếm mọi HTTP lỗi, vì response 4xx/5xx không đảm bảo có error dispatch.

Với authentication, authorization, CORS, CSRF và security headers, ưu tiên **Spring Security Servlet FilterChain** đúng cấu hình và phiên bản. Custom OncePerRequestFilter nên có phạm vi rõ; không tự xem nó là cơ chế bảo mật toàn diện.

## 8. Bảng lựa chọn và chẩn đoán

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ASYNC không gọi doFilterInternal | Filter mapping thiếu ASYNC hoặc skip hook true | Set dispatcher types + override false |
| ERROR không gọi doFilterInternal | Không sinh ERROR dispatch, URL /error không khớp, hoặc skip | Xác minh container, mapping, skip flag |
| doFilterInternal chạy hai lần cho một client request | REQUEST rồi ASYNC/ERROR | Kiểm tra dispatcherType, không suy là lỗi |
| AsyncController response 200 nhưng trace chỉ REQUEST | Filter chỉ chạy REQUEST | Kiểm tra setDispatcherTypes và shouldNotFilterAsyncDispatch |
| Error response 500 nhưng trace không ERROR | Exception handled trong REQUEST | Không suy ERROR từ status |
| NESTED_ERROR xuất hiện thay vì doFilterInternal ERROR | Marker còn tồn tại khi nested dispatch | Dùng doFilterNestedErrorDispatch |
| Request ID bị đổi ở ASYNC | Sinh ID mới trong mọi doFilterInternal | Dùng request attribute ổn định |
| Metrics đếm gấp đôi | Đếm theo dispatch thay vì logical request | Phân biệt metrics per-dispatch/per-request |
| Header không xuất hiện | Đặt khi response đã commit | Đặt sớm trước chain hoặc lifecycle phù hợp |
| MDC mất trong Callable | Executor thread khác | TaskDecorator/context propagation |
| Log request body làm @RequestBody rỗng | Filter đã đọc input stream | Không consume hoặc wrapper có giới hạn |
| Filter hoạt động hai lần bất thường | Auto-registration cộng Security chain/bean khác | Chỉ đăng ký một lần |
| Spring WebFlux không dùng REQUEST/ASYNC | Reactive Netty không có Servlet filter chain | Dùng WebFilter |


## 9. Dự án Java 17 / Spring Boot 3.5 chạy được

Ví dụ minh họa một request ID ổn định qua các Servlet dispatch. Dự án dùng **spring-boot-starter-web** và embedded Tomcat, không dùng WebFlux Netty.

### 9.1. Cấu trúc project

~~~text
dispatch-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/dispatchdemo/
    │   │   ├── DispatchDemoApplication.java
    │   │   ├── DispatchAudit.java
    │   │   ├── TraceDispatchFilter.java
    │   │   ├── FilterConfig.java
    │   │   └── DemoController.java
    │   └── resources/application.yml
    └── test/java/com/example/dispatchdemo/
        └── DispatchIntegrationTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>dispatch-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Đối với production, dùng nhánh Spring Boot hiện được bảo trì phù hợp với tổ chức. Ở đây version 3.5.16 được cố định để ví dụ có dependency cụ thể.

### 9.3. DispatchDemoApplication.java

~~~java
package com.example.dispatchdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }
}
~~~

### 9.4. DispatchAudit.java

~~~java
package com.example.dispatchdemo;

import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import jakarta.servlet.DispatcherType;
import org.springframework.stereotype.Component;

@Component
public class DispatchAudit {

    private final Queue<Entry> entries = new ConcurrentLinkedQueue<>();

    public void add(
            String requestId,
            DispatcherType dispatcherType,
            String phase,
            boolean asyncStarted) {

        entries.add(new Entry(
                requestId,
                dispatcherType,
                phase,
                asyncStarted,
                Thread.currentThread().getName()));
    }

    public List<Entry> forRequest(String requestId) {
        return entries.stream()
                .filter(e -> e.requestId().equals(requestId))
                .toList();
    }

    public record Entry(
            String requestId,
            DispatcherType dispatcherType,
            String phase,
            boolean asyncStarted,
            String thread) {
    }
}
~~~

**Giải thích:** ConcurrentLinkedQueue cho phép các Servlet threads ghi sự kiện đồng thời. Đây là **in-memory audit phục vụ học và test**, không phải solution production: queue không giới hạn có thể làm tăng RAM, endpoint công khai trace có thể làm lộ thông tin. Trong production dùng logging/metrics có giới hạn và access control.

### 9.5. TraceDispatchFilter.java

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class TraceDispatchFilter extends OncePerRequestFilter {

    public static final String REQUEST_ID =
            TraceDispatchFilter.class.getName() + ".requestId";

    private final DispatchAudit audit;

    public TraceDispatchFilter(DispatchAudit audit) {
        this.audit = audit;
    }

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = (String) request.getAttribute(REQUEST_ID);
        if (id == null) {
            id = UUID.randomUUID().toString();
            request.setAttribute(REQUEST_ID, id);
        }

        if (!response.isCommitted()) {
            response.setHeader("X-Request-Id", id);
        }

        DispatcherType type = request.getDispatcherType();
        audit.add(id, type, "ENTER", isAsyncStarted(request));

        try {
            chain.doFilter(request, response);
        } finally {
            audit.add(id, type, "EXIT", isAsyncStarted(request));
        }
    }

    @Override
    protected void doFilterNestedErrorDispatch(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = (String) request.getAttribute(REQUEST_ID);
        audit.add(id == null ? "unknown" : id,
                request.getDispatcherType(),
                "NESTED_ERROR", isAsyncStarted(request));
        chain.doFilter(request, response);
    }
}
~~~

**Giải thích chi tiết:**

- OncePerRequestFilter dùng hai override false để có thể xử lý ASYNC và ERROR.
- Dữ liệu **REQUEST_ID** lưu vào request attribute **riêng** và không bị đồng nhất với marker **.FILTERED** của base class.
- Khi ASYNC/ERROR dispatch mới chạy, nếu request attribute còn nguyên, trace ID được tái sử dụng.
- Trước chain, thêm header nếu response chưa commit.
- Queue ghi **ENTER** và **EXIT** cùng DispatcherType để quan sát các pha.
- Phương thức doFilterNestedErrorDispatch ghi **NESTED_ERROR** nếu một container chuyển ERROR ngay trong REQUEST khi marker còn tồn tại. Nếu wrapper request/response cần tái áp dụng, phải triển khai thêm logic đúng theo wrapper đó.
- Class **không gắn @Component** để tránh đăng ký hai lần. FilterRegistrationBean ở file kế tiếp là registration duy nhất.
- Filter minh họa logging/tracing, không thay Spring Security.

### 9.6. FilterConfig.java

~~~java
package com.example.dispatchdemo;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FilterConfig {

    @Bean
    public FilterRegistrationBean<TraceDispatchFilter> traceFilter(
            DispatchAudit audit) {

        FilterRegistrationBean<TraceDispatchFilter> bean =
                new FilterRegistrationBean<>(
                        new TraceDispatchFilter(audit));

        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR);
        bean.setAsyncSupported(true);
        bean.setOrder(10);
        return bean;
    }
}
~~~

**Vì sao dùng /*?** ERROR dispatch của Spring Boot Servlet MVC thường đi tới **/error**, nên registration chỉ có **/api/*** có thể bỏ qua error page. FilterConfig map **"/*"** để có cơ hội quan sát cả /api và /error.

**Vì sao setAsyncSupported(true)?** Servlet container yêu cầu filters/servlets trên async path có hỗ trợ async; điều này không tự khiến request chuyển sang async nếu controller không khởi động async.

### 9.7. DemoController.java

~~~java
package com.example.dispatchdemo;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private final DispatchAudit audit;

    public DemoController(DispatchAudit audit) {
        this.audit = audit;
    }

    @GetMapping("/api/sync")
    public Map<String, String> sync(HttpServletRequest request) {
        String id = (String) request.getAttribute(
                TraceDispatchFilter.REQUEST_ID);
        return Map.of("mode", "sync", "requestId", id);
    }

    @GetMapping("/api/async")
    public Callable<Map<String, String>> async(
            HttpServletRequest request) {

        String id = (String) request.getAttribute(
                TraceDispatchFilter.REQUEST_ID);

        return () -> Map.of("mode", "async", "requestId", id);
    }

    @GetMapping("/api/fail")
    public void fail(HttpServletResponse response)
            throws IOException {
        response.sendError(503, "Demo Servlet error");
    }

    @GetMapping("/api/trace/{id}")
    public List<DispatchAudit.Entry> trace(
            @PathVariable String id) {
        return audit.forRequest(id);
    }
}
~~~

Controller **async** trả Callable; Spring MVC chạy logic trong executor. **Không dùng HttpServletRequest trực tiếp trong Callable thread**, thay vào đó lấy requestId lúc handler chạy và capture String bất biến.

Endpoint **/api/fail** dùng sendError(503), cho embedded container xử lý error page. Không khẳng định ERROR luôn xuất hiện với mọi 503; hãy đọc audit thực tế. Endpoint **/api/trace/{id}** chỉ phục vụ bài học, **không được công khai trên production**.

### 9.8. application.yml

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 10s
~~~

Tham số request-timeout áp dụng cho Spring MVC asynchronous request handling. Production còn cần AsyncTaskExecutor có giới hạn và theo dõi timeout/queue.

### 9.9. Chạy và kiểm tra

Từ thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Request đồng bộ:

~~~bash
curl -i "http://localhost:8080/api/sync"
~~~

Mong đợi HTTP 200, header **X-Request-Id** và JSON tương tự:

~~~json
{"mode":"sync","requestId":"123e4567-e89b-12d3-a456-426614174000"}
~~~

Request ID là UUID minh họa, không phải stdout cố định. Header X-Request-Id và field requestId trong JSON phải **giống nhau**.

Request async:

~~~bash
curl -i "http://localhost:8080/api/async"
~~~

Mong đợi HTTP 200, JSON mode=async, header cùng ID. Sau đó thay ID thực vào:

~~~bash
curl -i \
  "http://localhost:8080/api/trace/123e4567-e89b-12d3-a456-426614174000"
~~~

Trong embedded Tomcat với configuration trên, thường thấy entry **REQUEST ENTER**, **REQUEST EXIT** và **ASYNC ENTER**, **ASYNC EXIT** có cùng request ID. Thread name và isAsyncStarted có thể khác nhau theo runtime/timing.

Gọi error:

~~~bash
curl -i "http://localhost:8080/api/fail"
~~~

Mong đợi **503 Service Unavailable**. Nếu embedded container tạo ERROR dispatch tới /error, trace sẽ có **DispatcherType.ERROR**; nếu tạo nested ERROR, hook có thể ghi **NESTED_ERROR**. Body error có thể thay đổi theo Spring Boot error attributes và Accept. Không suy từ status 503 rằng nhất thiết phải có ERROR entry.


## 10. Integration tests qua embedded Tomcat thật

Bộ test dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** với **JDK 17 HttpClient**, không phụ thuộc vào cổng 8080. Đây là HTTP socket thật, giúp quan sát DispatcherType sát với container hơn MockMvc thuần.

Tạo file **src/test/java/com/example/dispatchdemo/DispatchIntegrationTest.java**:

~~~java
package com.example.dispatchdemo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.servlet.DispatcherType;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class DispatchIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    DispatchAudit audit;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://localhost:" + port + path))
                .GET()
                .build();

        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    @Test
    void syncRunsThroughRequestDispatch() throws Exception {
        HttpResponse<String> response = get("/api/sync");

        assertThat(response.statusCode()).isEqualTo(200);
        String id = response.headers()
                .firstValue("X-Request-Id").orElseThrow();
        JsonNode body = mapper.readTree(response.body());

        assertThat(body.get("mode").asText()).isEqualTo("sync");
        assertThat(body.get("requestId").asText()).isEqualTo(id);

        List<DispatchAudit.Entry> entries = audit.forRequest(id);
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("ENTER"));
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("EXIT"));
    }

    @Test
    void asyncRunsThroughRequestAndAsyncDispatch()
            throws Exception {
        HttpResponse<String> response = get("/api/async");

        assertThat(response.statusCode()).isEqualTo(200);
        String id = response.headers()
                .firstValue("X-Request-Id").orElseThrow();
        JsonNode body = mapper.readTree(response.body());

        assertThat(body.get("mode").asText()).isEqualTo("async");
        assertThat(body.get("requestId").asText()).isEqualTo(id);

        List<DispatchAudit.Entry> entries = audit.forRequest(id);
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.REQUEST
                        && e.phase().equals("ENTER"));
        assertThat(entries).anyMatch(e ->
                e.dispatcherType() == DispatcherType.ASYNC
                        && e.phase().equals("ENTER"));
    }

    @Test
    void sendErrorReturns503() throws Exception {
        HttpResponse<String> response = get("/api/fail");
        assertThat(response.statusCode()).isEqualTo(503);

        // Nếu muốn assert DispatcherType.ERROR:
        // xác nhận embedded Servlet container đã thực hiện
        // ERROR dispatch (khác với HTTP status lỗi thuần).
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Khi test đạt, Maven kết thúc exit code 0. Import **com.fasterxml.jackson.databind.ObjectMapper** có sẵn từ spring-boot-starter-web. Các test không cố định UUID/thread name, vì chúng biến đổi theo request và môi trường.

### 10.1. Bổ sung xác minh ERROR dispatch

Nếu bạn đã xác nhận embedded Tomcat thực sự dispatch tới Boot **/error**, trong test sendErrorReturns503 có thể bổ sung:

~~~java
String id = response.headers()
        .firstValue("X-Request-Id").orElseThrow();

assertThat(audit.forRequest(id)).anyMatch(e ->
        e.dispatcherType() == DispatcherType.ERROR
                || e.phase().equals("NESTED_ERROR"));
~~~

Đây là **đoạn bổ sung vào test method**, không phải chương trình độc lập. Nếu nó không đạt, kiểm tra error page mapping, container và liệu response có đi vào ERROR dispatch hay chỉ được xử lý trong REQUEST.

### 10.2. Thử thay đổi cờ skip

Bật lại default:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;
}
~~~

Khi chạy lại test async, HTTP response vẫn có thể 200 nhưng **doFilterInternal ASYNC không được gọi**. Điều này chứng minh Servlet async lifecycle vẫn hoạt động; chỉ có filter tự skip.

Nếu thay registration chỉ còn **DispatcherType.REQUEST**, dù shouldNotFilterAsyncDispatch trả false, Servlet container **không gọi filter ở ASYNC**. Cả hai cổng cấu hình phải phù hợp.

### 10.3. MockMvc khác HTTP container thật

MockMvc có thể kiểm tra logic Callable bằng:

~~~java
MvcResult start = mockMvc.perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(start))
        .andExpect(status().isOk());
~~~

Đây là **đoạn minh họa trong một test class có MockMvc/static imports**. Nó không tự tái hiện đầy đủ FilterRegistrationBean mappings, embedded Servlet container ERROR page hoặc mọi điều kiện response commit. Với mục đích đánh giá REQUEST/ASYNC/ERROR dispatch, ưu tiên HTTP integration test qua embedded server.

## 11. Những lưu ý production

### 11.1. MDC và ThreadLocal

Nếu đặt MDC theo request trong Filter, phải dọn theo từng thread:

~~~java
String previous = MDC.get("requestId");
try {
    MDC.put("requestId", requestId);
    chain.doFilter(request, response);
} finally {
    if (previous == null) {
        MDC.remove("requestId");
    } else {
        MDC.put("requestId", previous);
    }
}
~~~

Đoạn này chỉ minh họa khi đã có biến requestId và import MDC. **Callable chạy trong executor thread không tự có MDC** của REQUEST thread. Nếu cần, dùng task decorator/context propagation và dọn thread pool đúng cách.

### 11.2. Request body và response wrappers

Đọc ServletInputStream trong filter trước controller có thể khiến **@RequestBody** đọc body rỗng. **ContentCachingRequestWrapper** chỉ cache khi dữ liệu đã được đọc, không tự biến mọi input stream thành nguồn có thể đọc lại vô hạn. Tránh log raw body, token, password, Cookie hoặc file upload.

Nếu filter dùng request/response wrapper, hãy kiểm thử ERROR nested, ASYNC redispatch và response commit; doFilterNestedErrorDispatch tồn tại để giúp xử lý trường hợp một số container quay lại request/response gốc ở nested ERROR.

### 11.3. Security order và registration trùng

Spring Security Servlet dùng **DelegatingFilterProxy**, **FilterChainProxy**, **SecurityFilterChain**. Nếu custom Filter đồng thời là Spring bean tự auto-register và được thêm vào SecurityFilterChain, nó có thể chạy hai lần theo registration khác nhau. Cần kiểm tra registration và có thể dùng **FilterRegistrationBean.setEnabled(false)** cho filter chỉ thuộc Security chain.

Không dùng một custom OncePerRequestFilter làm authorization chính mà không hiểu dispatcher types, URL matching, security chain và CSRF. Dùng Spring Security policy chính thức cho Servlet stack.

### 11.4. Timeout, async executor, error mapping

- Cấu hình executor cho MVC async Callable và giới hạn concurrency/queue.
- Đặt timeout có chủ đích và theo dõi exception/timeout/cancellation.
- Không đo thời gian toàn HTTP chỉ bằng finally của REQUEST dispatch.
- Trong ERROR dispatch, original URI có thể là request attribute **jakarta.servlet.error.request_uri**.
- Không tự giả định một 404/500 tạo ERROR; phải quan sát DispatcherType thực.
- Nếu response đã commit, không cố sửa status/body/header trong filter lúc quá muộn.
- Khi cần một số đo request duy nhất, dùng Micrometer Observation/Tracing hoặc AsyncListener phù hợp.

## 12. Checklist QA

- [ ] Đã phân biệt logical request và Servlet dispatch.
- [ ] Biết default shouldNotFilterAsyncDispatch/shouldNotFilterErrorDispatch đều true.
- [ ] Nếu cần ASYNC, đã map DispatcherType.ASYNC và override skip=false.
- [ ] Nếu cần ERROR, đã map DispatcherType.ERROR, URL /error và override skip=false.
- [ ] Filter hỗ trợ async khi ứng dụng xử lý Servlet async.
- [ ] Không dùng marker .FILTERED như marker nghiệp vụ tồn tại toàn request.
- [ ] Correlation ID được lưu một lần vào request attribute và dùng lại khi redispatch.
- [ ] Có xử lý doFilterNestedErrorDispatch khi cần áp lại wrapper.
- [ ] Không đếm logical client request nhiều lần theo dispatch.
- [ ] Không nhầm một HTTP status lỗi với container ERROR dispatch.
- [ ] MDC, ThreadLocal và executor propagation được quản lý đúng lifecycle.
- [ ] Không đặt header/body sau commit hoặc đọc request body hai lần.
- [ ] Không đăng ký filter trùng trong container/Spring Security.
- [ ] Đã test sync, Callable async, sendError, error handling và timeout phù hợp.
- [ ] Production không công khai endpoint audit hay giữ queue trace vô hạn.

## 13. Tài liệu chính thức

1. **Spring Framework 6.2 OncePerRequestFilter Javadoc**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
2. **Spring Framework 6.2 MVC Filters**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html
3. **Spring Framework 6.2 Asynchronous Requests**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html
4. **Spring Boot 3.5 Embedded Web Servers, Filter registration**: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
5. **Spring Boot 3.5 FilterRegistrationBean API**: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html
6. **Jakarta Servlet 6 DispatcherType API**: https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype
7. **Spring Security Servlet Architecture**: https://docs.spring.io/spring-security/reference/servlet/architecture.html
8. **Spring Boot 3.5.16 Maven artifact**: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-parent/3.5.16

## 14. Kết luận

**OncePerRequestFilter** không cam kết chỉ chạy đúng một lần cho toàn bộ HTTP request. Nó dùng request attribute **already filtered** để ngăn doFilterInternal lặp trong một dispatch, trong khi REQUEST, ASYNC và ERROR có thể là các dispatch khác nhau của cùng một logical request.

Theo Spring Framework 6.2, base class mặc định **skip ASYNC và ERROR**. Để tham gia các dispatch này, cần cả **Servlet dispatcher mapping tương ứng** và override cờ skip thành **false**. Với ERROR lồng khi marker còn tồn tại, xử lý bằng **doFilterNestedErrorDispatch** thay vì giả định doFilterInternal sẽ chạy lần thứ hai.

Khi triển khai, lưu correlation ID ổn định trong request attribute, phân biệt metrics theo dispatch và logical request, xử lý ThreadLocal/async đúng vòng đời, và kiểm thử response đã commit cùng error mapping của Servlet container thực tế.
