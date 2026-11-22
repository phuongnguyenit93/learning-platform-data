# ASYNC dispatch, OncePerRequestFilter và tránh chạy lại sai chính sách trong Spring Security Servlet

> **Phạm vi:** Servlet 3.1+, Spring MVC, Spring Security 6.x và Spring Boot 3.x (Java 17+). Bài học phân biệt **request bất đồng bộ** với **lượt dispatch ASYNC**, giải thích hành vi thực tế của `OncePerRequestFilter`, cách đăng ký dispatcher types, xử lý `SecurityContext` qua các thread và cách ngăn những thao tác chỉ nên chạy một lần bị lặp. Các đoạn mã chạy được đặt trong một project Spring Boot; các fragment còn lại được ghi rõ là minh họa.

## 1. Vấn đề: “một HTTP request” có thể đi qua filter chain nhiều lần

Trong mô hình Servlet đồng bộ, một yêu cầu HTTP thường được xử lý trên một luồng của container:

~~~text
Client
  |
  v
Servlet container
  -> DispatcherType.REQUEST
  -> Servlet filters / Spring Security FilterChainProxy
  -> DispatcherServlet / Controller
  -> HTTP response
~~~

Với Spring MVC bất đồng bộ, controller có thể trả `Callable<T>`, `DeferredResult<T>` hoặc loại tương đương, để **giải phóng thread servlet ban đầu** trong khi kết quả chưa sẵn sàng. Khi có kết quả, container thực hiện một lượt **ASYNC dispatch** để tiếp tục xử lý response:

~~~text
Client gửi GET /api/async
          |
          v
[Servlet thread A]
  DispatcherType.REQUEST
  -> Servlet filters
  -> Spring Security filters
  -> DispatcherServlet
  -> Controller trả Callable/DeferredResult
  -> request.startAsync() / suspend
          |
          | thread A có thể được giải phóng
          v
[Worker thread B]
  Callable hoặc công việc tạo kết quả
  (không phải mặc định một Servlet filter dispatch)
          |
          | kết quả sẵn sàng
          v
[Servlet thread C]
  DispatcherType.ASYNC
  -> các filters được map cho ASYNC
  -> Spring Security FilterChainProxy nếu được đăng ký cho ASYNC
  -> DispatcherServlet hoàn tất response
          |
          v
Client nhận JSON/HTML
~~~

**Cùng một logical HTTP request có thể có nhiều lượt đi qua filter chain.** Một lượt sau có `DispatcherType.ASYNC`, không phải một HTTP request hoàn toàn mới do trình duyệt gửi. Nếu viết custom filter làm hành động có side effect (gửi audit event, ghi database, tính phí, cập nhật quota) mỗi lần nó chạy mà không hiểu dispatch, bạn có thể tạo hành động trùng.

Ngược lại, nếu một filter cần thiết lập **MDC logging context** hoặc `ThreadLocal` trên mỗi servlet thread, bỏ qua ASYNC dispatch lại có thể làm mất ngữ cảnh trong lượt hoàn tất response. Câu hỏi không phải “có chạy lại hay không?” một cách chung chung, mà là **chính sách nào được phép chạy tại dispatcher type và thread nào?**

## 2. Request, dispatch, thread và công việc nghiệp vụ không phải một khái niệm

| Khái niệm | Ví dụ | Ghi nhớ |
| --- | --- | --- |
| HTTP request | Một lần client gửi GET /api/async. | Một request có thể trải qua nhiều dispatch. |
| `DispatcherType.REQUEST` | Lượt container nhận request từ client. | Điểm vào thông thường. |
| `DispatcherType.ASYNC` | Lượt container dispatch lại request sau xử lý bất đồng bộ. | Không nhất thiết dùng cùng thread ban đầu. |
| Worker thread | `Callable.call()`, executor task hoặc callback ứng dụng. | **Không tự động** là một Servlet filter dispatch. |
| `DispatcherType.ERROR` | Lượt error dispatch do container tạo. | Có thể làm filter chạy lại nếu được đăng ký và cho phép. |
| `DispatcherType.FORWARD` / `INCLUDE` | Servlet forward/include nội bộ. | Phụ thuộc dispatcher mapping, không phải client gửi thêm request. |
| SecurityContext | `Authentication` áp dụng cho thread/request theo quy tắc Spring Security. | ThreadLocal thường không tự truyền sang thread khác. |
| Idempotency | Cách bảo đảm nghiệp vụ không bị xử lý lặp. | Không thể thay bằng một flag filter trong mọi hệ thống. |

Ví dụ có **một** HTTP request, **hai** servlet dispatches, và **một hoặc nhiều** worker tasks. Không lấy `Thread.currentThread().getId()` làm ID request: một request có thể đổi thread, còn một thread sẽ xử lý nhiều request theo thời gian.

Nếu muốn request correlation, sử dụng request ID do server/gateway tin cậy tạo, lưu nó như request attribute hoặc trong cơ chế context propagation được quản lý. Khi xử lý request async, cần phân biệt:
- **“run once for REQUEST dispatch”**;
- **“run once for each participating servlet dispatch”**;
- **“run once as a durable business operation”**.

Ba yêu cầu trên không tương đương.

## 3. OncePerRequestFilter có thực sự chỉ chạy đúng một lần?

`org.springframework.web.filter.OncePerRequestFilter` là abstract base class của **Spring Web**, nhiều filter Spring Security cũng dựa trên mô hình tương tự.

Một implementation thường ghi đè:

~~~java
@Override
protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain)
        throws ServletException, IOException {

    // Logic filter ...
    filterChain.doFilter(request, response);
}
~~~

Đây là fragment, chưa có import/class hoàn chỉnh. `OncePerRequestFilter` dùng một **request attribute đánh dấu “already filtered”** để tránh chạy lặp logic khi một filter gặp nhiều lần đi qua **cùng lượt dispatch hoặc một nhánh lồng nhau**. Nó không phải kho idempotency phân tán, không lưu trạng thái bền vững và không được hiểu cứng là “chính xác một lần trong toàn bộ thời gian sống của HTTP request”.

### 3.1. Marker được đặt và gỡ ra như thế nào?

Mô tả rút gọn:

~~~text
Filter nhận request
  |
  +--> nếu dispatcher type phải bỏ qua -> chỉ gọi filterChain.doFilter
  |
  +--> nếu marker “already filtered” đang tồn tại:
  |       -> không chạy lại doFilterInternal trong nhánh thông thường
  |
  +--> nếu chưa có marker:
          -> đặt request attribute marker
          -> gọi doFilterInternal(...)
          -> trong finally: gỡ marker
~~~

**Điểm rất quan trọng:** Khi lượt `REQUEST` kết thúc bằng việc khởi tạo async, filter thường đã chạy xong phần `finally` và **gỡ marker**. Nếu container dispatch lại bằng `ASYNC` và filter được phép chạy trên dispatcher đó, `doFilterInternal` **có thể chạy một lần nữa** trên request ấy. Đây là hành vi có chủ đích, không phải lỗi của framework.

Marker dùng theo tên filter để tránh filter bị lặp trong một chuỗi; nếu đăng ký cùng logic thành **hai filter instance khác nhau**, hoặc filter được chạy ngoài Spring Security chain và trong chain, cần xem xét tên/registration để tránh tác động ngoài ý muốn.

### 3.2. shouldNotFilterAsyncDispatch()

`OncePerRequestFilter` cung cấp hook:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;
}
~~~

- **`true`**: bỏ qua `ASYNC dispatch` trong phần `doFilterInternal`; đây là **hành vi mặc định** của `OncePerRequestFilter`.
- **`false`**: cho phép logic `doFilterInternal` chạy trên **ASYNC dispatch**, với điều kiện filter mapping thực sự áp dụng cho dispatcher này.
- Override `false` **không** khiến filter tự chạy trên thread của `Callable.call()`; nó chỉ ảnh hưởng một lượt Servlet filter invocation trên ASYNC dispatch.
- Nếu có nhiều ASYNC dispatch độc lập, `doFilterInternal` có thể chạy trong mỗi lượt, không chỉ một lần duy nhất.

Nếu chỉ muốn kiểm tra/chuyển đổi request đầu vào một lần, thường giữ mặc định `true`. Nếu cần tạo logging context trong **thread container hoàn tất response**, có thể chọn `false` và bảo đảm logic được thiết kế **theo dispatch**.

### 3.3. shouldNotFilterErrorDispatch()

~~~java
@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;
}
~~~

Mặc định `OncePerRequestFilter` bỏ qua `ERROR dispatch`. Đổi thành `false` nếu chính filter cần tham gia xử lý/ghi ngữ cảnh trong error dispatch, và phải xem xét xử lý lỗi lồng nhau, `doFilterNestedErrorDispatch` cùng việc response có thể đã được commit.

Không sửa đồng loạt cả hai hook thành `false` chỉ vì “muốn filter luôn chạy”. Các filter authentication, authorization, tracing, logging và audit có **chính sách dispatcher khác nhau**.

### 3.4. shouldNotFilter(HttpServletRequest)

Một filter còn có thể override `shouldNotFilter(request)` để skip path hoặc điều kiện cụ thể:

~~~java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return request.getRequestURI().startsWith("/assets/");
}
~~~

Đây là fragment minh họa, và path-prefix matching bằng `startsWith` không phù hợp cho mọi yêu cầu security. Nếu skip một endpoint nhạy cảm, phải dùng matcher có semantics rõ ràng và test encoded/normalized path; **không dùng custom skip để lách quy tắc authorization**.

## 4. Hai lớp cấu hình: Servlet dispatcher mapping và OncePerRequestFilter hook

Một filter chỉ có cơ hội chạy trên ASYNC dispatch khi **hai điều kiện** cùng được thỏa:

1. **Bên Servlet container:** filter registration được map cho `DispatcherType.ASYNC`; filter/servlet hỗ trợ async theo cấu hình cần thiết.
2. **Bên implementation:** filter không chủ động skip `ASYNC` qua `shouldNotFilterAsyncDispatch()`/logic riêng.

Nếu filter chạy thông qua Spring Security, còn phải có:

3. **`DelegatingFilterProxy` / `FilterChainProxy` của Spring Security** được đăng ký cho `ASYNC` và security chain phù hợp được chọn ở lượt đó.

~~~text
ASYNC dispatch
  |
  +--> Servlet filter mapping có ASYNC?
  |        Không -> filter không được gọi
  |
  +--> Spring Security proxy mapping có ASYNC?
  |        Không -> SecurityFilterChain không được gọi trên lượt này
  |
  +--> Custom filter nằm trong chain phù hợp?
  |        Không -> filter không được gọi
  |
  +--> shouldNotFilterAsyncDispatch() == true?
  |        Có -> doFilterInternal không chạy
  |
  +--> Các điều kiện đều cho phép:
           doFilterInternal chạy trên ASYNC dispatch
~~~

**Chỉ override hook chưa đủ.** Ngược lại, chỉ thêm `ASYNC` vào dispatcher mapping cũng không buộc mọi `OncePerRequestFilter` chạy lại, vì một số filter chọn bỏ qua.

### 4.1. Spring Boot dispatcher-types

Trong ứng dụng Spring Boot Servlet, có thể điều khiển dispatcher types của **Spring Security filter registration** bằng cấu hình:

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request,async,error
~~~

Dạng này cho thấy `DelegatingFilterProxy` của Spring Security có thể được gọi ở các dispatch tương ứng. Luôn kiểm tra **cấu hình hiệu lực** trên phiên bản Spring Boot, việc custom servlet registration, và web container; không suy từ YAML rằng mọi filter đều chạy trên ASYNC. Khi dùng filter riêng đăng ký trực tiếp ở Servlet container, cần cấu hình dispatcher types cho **chính registration đó**.

### 4.2. Async support và IllegalStateException

Nếu một filter/servlet registration trên đường đi không hỗ trợ async, việc `startAsync()` có thể thất bại với lỗi như `IllegalStateException`. Cần kiểm tra Servlet API `isAsyncSupported()`, các registration có `asyncSupported=true`, cùng sự hỗ trợ của container.

`OncePerRequestFilter` không tự gọi `startAsync()` và không tự bật async support cho toàn bộ filter chain.

### 4.3. Tránh double registration của cùng filter

Nếu tạo một filter với `@Component` hoặc `@Bean` **và** chèn nó vào `HttpSecurity.addFilterBefore(...)`, Spring Boot có thể đăng ký nó như **Servlet filter độc lập** đồng thời Spring Security cũng gọi nó **bên trong `FilterChainProxy`**. Điều này dễ gây chẩn đoán sai, thứ tự không như dự tính hoặc chạy trùng trong các lượt dispatch.

Có hai mẫu rõ ràng:

- Tạo một **instance mới, không phải bean Servlet filter**, và thêm nó **chỉ** vào `SecurityFilterChain` bằng `http.addFilterBefore(new MyFilter(), SomeSecurityFilter.class)`. Ví dụ hoàn chỉnh ở mục 7 dùng cách này.
- Nếu cần filter là bean Spring, dùng `FilterRegistrationBean` với `setEnabled(false)` để tránh Servlet auto-registration, rồi thêm bean vào security chain. Phải test registration cụ thể theo phiên bản Boot.

Không dùng `@WebFilter`/`@Component` và `addFilterBefore` song song mà không biết có bao nhiêu filter registration thực tế. Và đừng dựa vào marker “already filtered” như cơ chế sửa mọi lỗi double registration.

## 5. Ba chính sách xử lý cần tách biệt

### 5.1. Chỉ làm ở lượt REQUEST ban đầu

Ví dụ: đọc request metadata đã được chuẩn hóa, tạo một request identifier, ghi một event “request accepted for processing” hoặc thiết lập một cờ trạng thái.

Cách đơn giản nhất thường là mặc định `shouldNotFilterAsyncDispatch() == true` và `shouldNotFilterErrorDispatch() == true`. Nếu filter vẫn tham gia các dispatcher khác, có thể kiểm tra tường minh:

~~~java
if (request.getDispatcherType() == DispatcherType.REQUEST) {
    // Chỉ làm trong lượt REQUEST; không giả định async completion là request mới.
}
~~~

Nhưng **không đặt thao tác kinh doanh không thể lặp** (chuyển tiền, cấp hàng, gửi email) ở filter chỉ vì muốn “once”. Nó không kiểm soát retries từ client, failover hay phân tán; dùng transaction, unique constraint, idempotency key và outbox theo bài toán.

### 5.2. Làm trên từng Servlet dispatch/thread tham gia

Ví dụ: thêm `traceId` vào MDC ở thread xử lý `REQUEST`, và **thiết lập lại** MDC khi container chạy `ASYNC` trên thread khác. Với loại filter này:

- override `shouldNotFilterAsyncDispatch()` trả `false`;
- thiết lập MDC **trước** `filterChain.doFilter`;
- xóa/khôi phục MDC trong `finally` để tránh rò rỉ context sang request kế tiếp trên pool thread;
- thiết lập request attribute chứa trace ID đã tạo một lần, không sinh ID mới trên mỗi dispatch;
- nếu worker thread của `Callable` cần MDC, truyền ngữ cảnh sang worker **bằng cơ chế riêng**, không suy từ filter ASYNC.

MDC là `ThreadLocal` trong logging framework phổ biến, nên việc có `traceId` ở servlet thread A không bảo đảm `traceId` tự xuất hiện ở worker thread B.

### 5.3. Chỉ làm một lần theo nghiệp vụ ở mọi dispatch/retry

Ví dụ thanh toán `POST /payments` có thể bị client retry, gateway retry hoặc business task bị thực thi nhiều lần. Request attribute trong Servlet request chỉ giúp chặn một số lặp **trong cùng request object**; nó **không** thể bảo đảm exactly-once khi request mới đến, process restart hoặc worker khác nhận việc. Cần:
- idempotency key có scope theo principal/tenant/operation;
- lưu trạng thái kết quả dưới unique constraint hoặc giao dịch;
- reject/memoize request trùng một cách xác định;
- transaction/outbox và consumer idempotent khi phát message;
- test retry, timeout, async double completion, crash/recovery.

**Không dùng “OncePerRequestFilter” như lời hứa exactly-once business semantics.**

## 6. SecurityContext qua asynchronous processing

### 6.1. SecurityContextHolder thường dùng ThreadLocal

`SecurityContextHolder` thường lưu context theo thread. Trong initial `REQUEST`, Spring Security filter chain xác thực người gọi rồi đặt `Authentication` vào context cho downstream. Khi một executor chạy công việc ở thread khác, **không nên mặc định context đó tự xuất hiện**.

~~~text
Thread A (REQUEST):
  SecurityContextHolder -> alice
          |
          +--> submit task
                     |
                     v
Thread B (pool worker):
  SecurityContextHolder -> ? (phụ thuộc cơ chế propagation)
~~~

Thao tác `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` không phải giải pháp chung cho thread pool: các thread tái sử dụng có vòng đời độc lập, có nguy cơ mang context sai khi không được dọn dẹp chính xác.

### 6.2. Callable của Spring MVC

Spring Security tích hợp với Spring MVC async `Callable` thông qua cơ chế như `WebAsyncManagerIntegrationFilter`. Nó có khả năng chuyển `SecurityContext` của request ban đầu sang thời gian thực thi `Callable` rồi dọn dẹp sau đó. Vì vậy khi dùng Spring Security web integration chuẩn, đoạn trong `Callable` có thể đọc được `Authentication` của caller.

Đừng tự diễn giải điều này thành “mọi loại async task đều có context”:
- Spring MVC `Callable` có tích hợp framework chuyên biệt.
- `DeferredResult` có thể được hoàn thành bởi thread/event từ ứng dụng; công việc tự tạo ấy không mặc nhiên được bao phủ theo cùng cách.
- `@Async`, executor tùy chỉnh, `CompletableFuture`, scheduled job, queue consumer thường cần context propagation rõ ràng khi có lý do bảo mật phù hợp.
- Trên lượt `ASYNC dispatch` ở thread container khác, Spring Security phải được đăng ký và khôi phục/security context tương ứng; đừng giả định Spring Security đã được gọi nếu dispatcher mapping không phù hợp.

### 6.3. DelegatingSecurityContextExecutor cho task tự quản lý

Spring Security có `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextRunnable` và các wrapper liên quan để thực thi công việc cùng một context được truyền có kiểm soát.

Fragment ý tưởng:

~~~java
Executor wrapped = new DelegatingSecurityContextExecutor(delegateExecutor);
wrapped.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
    // Chỉ dùng identity khi task thật sự thuộc request đã được xác thực.
});
~~~

Đây là **fragment**, cần imports và biến `delegateExecutor` do ứng dụng định nghĩa. Với constructor dùng delegate executor, wrapper có thể lấy context hiện tại khi submit task và dọn context đúng vòng đời. Không lan truyền thông tin người dùng tới job lâu dài ngoài ý định, và không giữ `SecurityContext` trong static field.

**Propagation không thay authorization.** Một worker có principal `alice` vẫn phải kiểm tra quyền khi truy cập tài nguyên; dữ liệu miền và tenant không được coi là đáng tin chỉ vì ThreadLocal có authentication.

### 6.4. Authentication và MDC là hai context khác nhau

`WebAsyncManagerIntegrationFilter` hỗ trợ **Spring SecurityContext** cho `Callable`, nhưng không tự bảo đảm MDC logging correlation của mọi thư viện. Nếu cần MDC trong worker thread, dùng `TaskDecorator`, wrapper executor hoặc observability context propagation phù hợp rồi cleanup sau công việc.

Không đặt MDC ở thread A rồi kỳ vọng `shouldNotFilterAsyncDispatch(false)` đi vào thread B khi `Callable.call()` đang chạy. Filter ASYNC chạy trên một **Servlet dispatch**, thường là luồng hoàn tất response, không phải nơi chạy công việc background.

## 7. Ví dụ hoàn chỉnh Spring Boot 3 + Java 17

Ví dụ xây một endpoint bảo vệ bằng HTTP Basic, trả `Callable` để Spring MVC xử lý bất đồng bộ. `AsyncTraceFilter` chỉ được đăng ký **bên trong SecurityFilterChain**, tham gia cả `REQUEST` và `ASYNC` dispatch để tạo MDC trên từng servlet thread. Nó **không** thực hiện nghiệp vụ khi chạy lại.

Chúng ta sẽ đếm:
- số lần đi qua `REQUEST` và `ASYNC`;
- một marker `initialWork` chỉ đặt trong `REQUEST` và chỉ một lần trên cùng request;
- một trace ID được giữ qua các dispatch.

Các bộ đếm **chỉ phục vụ test/minh họa**, không phải cơ chế idempotency production.

### 7.1. Cấu trúc project Maven

~~~text
async-filter-demo/
  pom.xml
  src/
    main/
      java/com/example/asyncfilter/
        AsyncFilterApplication.java
        AsyncTraceFilter.java
        SecurityConfig.java
        AsyncController.java
      resources/
        application.yml
    test/
      java/com/example/asyncfilter/
        AsyncFilterTest.java
~~~

Các file Java có cùng package `com.example.asyncfilter`. Maven starter dependencies chứa Spring Web, Security và test. Dùng một bản Spring Boot 3.x cụ thể như `3.3.5` để làm điểm tham chiếu Java 17, không khẳng định là bản mới nhất tại thời điểm đọc.

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>async-filter-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
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
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
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

### 7.2. Application entrypoint

**`src/main/java/com/example/asyncfilter/AsyncFilterApplication.java`:**

~~~java
package com.example.asyncfilter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AsyncFilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(AsyncFilterApplication.class, args);
    }
}
~~~

### 7.3. Dispatcher types của Spring Security registration

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    filter:
      dispatcher-types: request,async,error
~~~

Thiết lập này bảo đảm bước đăng ký Spring Security ở Servlet container xem xét các dispatcher types nói trên trong cấu hình Spring Boot tương thích. **Một custom OncePerRequestFilter vẫn có quyền skip** theo các hook. Ví dụ bỏ qua `ERROR` trong `AsyncTraceFilter` để không có side effect không mong muốn trong error rendering.

Khi dùng container tự đăng ký `DelegatingFilterProxy` hoặc Spring Security cấu hình không qua Spring Boot, cần kiểm tra dispatcher mapping bằng cơ chế registration tương đương; `application.yml` ở đây không thay thế việc quản lý hệ thống ngoài Spring Boot.

### 7.4. AsyncTraceFilter: chạy lại ASYNC nhưng không lặp policy REQUEST

**`src/main/java/com/example/asyncfilter/AsyncTraceFilter.java`:**

~~~java
package com.example.asyncfilter;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AsyncTraceFilter extends OncePerRequestFilter {

    static final String TRACE_ID =
        AsyncTraceFilter.class.getName() + ".traceId";

    static final String REQUEST_VISITS =
        AsyncTraceFilter.class.getName() + ".requestVisits";

    static final String ASYNC_VISITS =
        AsyncTraceFilter.class.getName() + ".asyncVisits";

    static final String INITIAL_MARKER =
        AsyncTraceFilter.class.getName() + ".initialOnly";

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        // Cho phép doFilterInternal chạy trong ASYNC dispatch.
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        // ERROR dispatch có chính sách riêng; ví dụ này bỏ qua.
        return true;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String traceId = (String) request.getAttribute(TRACE_ID);
        if (traceId == null) {
            traceId = UUID.randomUUID().toString();
            request.setAttribute(TRACE_ID, traceId);
        }

        DispatcherType dispatch = request.getDispatcherType();

        if (dispatch == DispatcherType.REQUEST) {
            increment(request, REQUEST_VISITS);

            // Chính sách chỉ cho lượt REQUEST ban đầu.
            // Marker chỉ minh họa; KHÔNG bảo đảm exactly-once nghiệp vụ.
            if (request.getAttribute(INITIAL_MARKER) == null) {
                request.setAttribute(INITIAL_MARKER, Boolean.TRUE);
            }
        } else if (dispatch == DispatcherType.ASYNC) {
            // Trên lượt ASYNC, chỉ làm việc an toàn theo dispatch.
            increment(request, ASYNC_VISITS);
        }

        // MDC gắn với thread; phải set/cleanup trên MỖI dispatch.
        String priorTrace = MDC.get("traceId");
        MDC.put("traceId", traceId);
        try {
            chain.doFilter(request, response);
        } finally {
            if (priorTrace == null) {
                MDC.remove("traceId");
            } else {
                MDC.put("traceId", priorTrace);
            }
        }
    }

    private static void increment(
            HttpServletRequest request, String attribute) {

        Integer before = (Integer) request.getAttribute(attribute);
        request.setAttribute(attribute,
            before == null ? 1 : before + 1);
    }
}
~~~

**Giải thích kỹ:**

1. `shouldNotFilterAsyncDispatch() == false` là **quyết định có chủ đích** vì mục tiêu của filter là đặt MDC trên mỗi servlet dispatch.
2. `TRACE_ID` được tạo một lần và giữ trong request attributes, nên hai lượt dispatch của cùng request chia sẻ ID. Nếu cần correlation với gateway, chỉ nhận external request ID khi gateway đã kiểm soát/sanitize, không tin input header không xác thực.
3. `INITIAL_MARKER` chỉ được đặt khi `DispatcherType.REQUEST`. Nếu filter gặp `ASYNC`, nó **không xử lý lại** thao tác initial-only.
4. Bộ đếm `REQUEST_VISITS` và `ASYNC_VISITS` giúp test quan sát **mấy lượt filter thật sự chạy**. Chúng không dùng làm trạng thái ứng dụng.
5. MDC được phục hồi/xóa trong `finally`, tránh làm bẩn thread pool. Nếu servlet thread trước đó đã có một trace context hợp lệ, ví dụ giữ nguyên giá trị cũ sau filter; không xóa bừa context do lớp ngoài quản lý.
6. Có thể có nhiều nested dispatch/error conditions, nhiều filter instances hoặc chain khác nhau trong hệ thống thực; test phải bao phủ **registration thực tế** của sản phẩm.
7. Filter này **không tạo Authentication** và **không có quyền bỏ qua AuthorizationFilter**; trách nhiệm security thuộc chain.

Không dùng request attribute làm khóa nghiệp vụ bền vững: khi client gửi HTTP request mới hoặc hệ thống restart, marker không còn. Việc “đã xử lý request” ở lớp này hoàn toàn khác việc “đã ghi chuyển khoản vào database đúng một lần”.

### 7.5. SecurityConfig: chỉ đăng ký filter trong SecurityFilterChain

**`src/main/java/com/example/asyncfilter/SecurityConfig.java`:**

~~~java
package com.example.asyncfilter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    UserDetailsService userDetailsService() {
        // Chỉ dùng cho bài tập; mật khẩu cố định không phù hợp production.
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}demo-pass")
                .roles("USER")
                .build());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/async").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .addFilterBefore(
                new AsyncTraceFilter(),
                AuthorizationFilter.class)
            .build();
    }
}
~~~

**Chú ý về vị trí và registration:**

- `AsyncTraceFilter` được tạo bằng `new` **trong security chain**, không phải `@Bean`/`@Component`. Vì vậy nó không bị Spring Boot tự đăng ký thành **một Servlet filter thứ hai**.
- `addFilterBefore(..., AuthorizationFilter.class)` xác định vị trí custom filter tương đối với một filter bảo mật đã biết. Những filter trước nó vẫn có thể từ chối/short-circuit request; đừng xem việc custom filter có log hay không là bằng chứng duy nhất rằng SecurityFilterChain đã chạy.
- `httpBasic()` xác thực username/password cho bài tập. Ứng dụng production nên dùng IdP/password encoder và transport đúng threat model; HTTP Basic phải qua HTTPS.
- Các endpoint khác bị `denyAll()`, tránh vô tình để đường phụ không có rule.
- `STATELESS` không đồng nghĩa “mọi thread tự có SecurityContext”. Nó chỉ nói về chiến lược session/security context của chain; async context cần xử lý riêng.
- Ví dụ chỉ có GET endpoint nên không tắt CSRF. Nếu mở POST/PUT/DELETE, phải đánh giá CSRF khi client là browser dùng cookie/Basic credentials.
- Spring Security có các filter riêng với async/error policies riêng. **Không kết luận** vì custom filter có `shouldNotFilterAsyncDispatch(false)` mà toàn bộ authentication hoặc authorization đều chỉ/luôn chạy lại chính xác số lần tương tự.

Trong demo, `{noop}demo-pass` cho phép nhập password trong bài tập để đơn giản. **Không dùng `{noop}` và password hardcoded trên production**; thay bằng encoder phù hợp, vault/IdP và HTTPS.

### 7.6. Controller: Callable chạy ở worker thread

**`src/main/java/com/example/asyncfilter/AsyncController.java`:**

~~~java
package com.example.asyncfilter;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.Callable;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AsyncController {

    @GetMapping("/api/async")
    public Callable<Map<String, String>> async(Principal principal) {

        // Đọc principal tại initial REQUEST thread.
        String requestUser = principal.getName();

        // Spring MVC thực thi Callable qua async executor.
        return () -> {
            Authentication current = SecurityContextHolder
                .getContext().getAuthentication();

            // Với Spring Security MVC integration chuẩn,
            // context của Callable được chuyển phù hợp.
            String workerUser = current == null
                ? "missing" : current.getName();

            return Map.of(
                "requestUser", requestUser,
                "workerUser", workerUser,
                "result", "done");
        };
    }
}
~~~

Controller này không tự gọi `startAsync()` vì Spring MVC thực hiện quản lý async khi trả `Callable`. Không dùng `Thread.sleep` để chứng minh async: Spring MVC đã chọn đường xử lý bất đồng bộ dựa trên loại return value.

`workerUser` giúp kiểm tra có `SecurityContext` trong **Callable** qua Spring Security MVC integration. Điều này **không nói** rằng MDC từ filter ban đầu cũng được truyền tới worker. Nếu cần MDC trong Callable, thêm context propagation/tracing thích hợp.

Một response JSON điển hình khi dùng đúng Basic account:

~~~json
{
  "requestUser": "alice",
  "workerUser": "alice",
  "result": "done"
}
~~~

Vị trí thuộc tính trong JSON có thể khác nhau; điều được test là giá trị, không phải thứ tự.

### 7.7. Build và chạy

Từ thư mục có `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn test
mvn spring-boot:run
~~~

Gọi endpoint:

~~~bash
curl -i -u alice:demo-pass \
  "http://localhost:8080/api/async"
~~~

Kỳ vọng: status 200 và body có `requestUser=alice`, `workerUser=alice`, `result=done`. Một request không có credential đến endpoint được bảo vệ thường nhận HTTP 401. Cần **HTTPS** nếu dùng Basic với thông tin đăng nhập thật; URL http localhost chỉ dành cho phát triển.

## 8. Kiểm thử async dispatch bằng MockMvc

Spring MVC `MockMvc` có thể kiểm tra **bắt đầu async** và **dispatch lần hai** bằng `asyncDispatch`. Cần phân biệt test chỉ gọi `mvc.perform(get(...))` với test chờ kết quả và dispatch lại; nếu chỉ có bước đầu, thường chưa quan sát response JSON cuối cùng.

**`src/test/java/com/example/asyncfilter/AsyncFilterTest.java`:**

~~~java
package com.example.asyncfilter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AsyncFilterTest {

    @Autowired
    MockMvc mvc;

    @Test
    void unauthenticatedRequestIsRejected() throws Exception {
        mvc.perform(get("/api/async"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void asyncDispatchReentersTraceFilterWithoutRepeatingInitialPolicy()
            throws Exception {

        MvcResult started = mvc.perform(
                get("/api/async")
                    .with(httpBasic("alice", "demo-pass")))
            .andExpect(request().asyncStarted())
            .andExpect(request().attribute(
                AsyncTraceFilter.REQUEST_VISITS, 1))
            .andReturn();

        mvc.perform(asyncDispatch(started))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.requestUser").value("alice"))
            .andExpect(jsonPath("$.workerUser").value("alice"))
            .andExpect(jsonPath("$.result").value("done"))
            .andExpect(request().attribute(
                AsyncTraceFilter.REQUEST_VISITS, 1))
            .andExpect(request().attribute(
                AsyncTraceFilter.ASYNC_VISITS, 1))
            .andExpect(request().attribute(
                AsyncTraceFilter.INITIAL_MARKER, true));
    }
}
~~~

Ý nghĩa test:

- `request().asyncStarted()` cho biết Spring MVC đã đi vào xử lý bất đồng bộ, không chỉ trả sync response.
- `asyncDispatch(started)` mô phỏng phần container dispatch lại sau khi `Callable` có kết quả.
- Giá trị `REQUEST_VISITS=1` và `ASYNC_VISITS=1` là kỳ vọng **của cấu hình demo** nơi security filter chain thực sự tham gia ASYNC và custom filter override skip flag. Không phải bảo đảm chung cho mọi container/proxy/custom registration.
- `INITIAL_MARKER=true` xác nhận phần initial-only vẫn được đánh dấu, không bị filter xóa để làm lại trên ASYNC.
- `workerUser=alice` minh họa Spring Security MVC `Callable` context integration, **không** tự kiểm chứng toàn bộ `@Async`, `DeferredResult` hoặc queue tasks.

Nếu test `ASYNC_VISITS` vẫn trống dù controller async thành công, cần xác minh dispatcher mapping của **MockMvc filter registration**, Spring Security filter chain, `shouldNotFilterAsyncDispatch` và môi trường test. Đừng sửa test bằng cách ép một request attribute ASYNC visits thủ công — như vậy sẽ che mất lỗi registration.

### 8.1. Unit test trực tiếp hook của OncePerRequestFilter

Để tách vấn đề filter hook khỏi cả Spring Security chain, có thể dùng `MockHttpServletRequest`, `MockHttpServletResponse` và `MockFilterChain` từ `spring-test`. Test sau kiểm tra hành vi ở `DispatcherType.ASYNC` với một filter đã bật cho ASYNC. Đây là **fragment JUnit** trong package cùng demo, cần đặt trong class test cùng các imports:

~~~java
MockHttpServletRequest req = new MockHttpServletRequest();
req.setDispatcherType(DispatcherType.ASYNC);

new AsyncTraceFilter().doFilter(
    req,
    new MockHttpServletResponse(),
    new MockFilterChain());

assertEquals(1,
    req.getAttribute(AsyncTraceFilter.ASYNC_VISITS));
~~~

Dùng unit test để kiểm tra hook; dùng integration test `MockMvc` để kiểm tra Spring MVC, security chain và lời gọi `asyncDispatch` thực sự. Cuối cùng, muốn xác minh Servlet container production mapping và reverse proxy, cần một test HTTP chạy server thật.

## 9. Không nên cho phép ASYNC dispatch bypass authorization một cách tùy tiện

Một số developer thấy error status trong lượt ASYNC và thử cấu hình:

~~~java
// FRAGMENT minh họa, không phải recommendation mặc định:
authorize.requestMatchers("/api/**").authenticated();
authorize.dispatcherTypeMatchers(DispatcherType.ASYNC).permitAll();
~~~

Đoạn trên **không phải một chain đầy đủ**; thứ tự matcher và builder cần đặt đúng theo API/version. Bản chất cần xem xét: liệu có nên cấp quyền khác cho ASYNC dispatch vì request ban đầu đã được kiểm tra, hay đang vô tình bỏ qua một chính sách cần áp dụng trong giai đoạn dispatch?

Những điều phải kiểm tra:

1. Request ban đầu có qua authentication/authorization cần thiết không?
2. API có thể tạo asynchronous dispatch bằng đường nào, và phần response có lộ dữ liệu khi chưa được cấp quyền không?
3. Security filter registration có áp dụng cho `ASYNC` và cơ chế bảo lưu context có đúng không?
4. Có nhiều `SecurityFilterChain` theo path/dispatcher không? Lượt ASYNC còn khớp chain mong muốn không?
5. Có custom filters dựa vào session, ThreadLocal hoặc request body chỉ hợp lệ ở initial REQUEST không?

**Không thêm `permitAll` cho mọi ASYNC chỉ để làm test pass** mà chưa giải thích trust boundary. Quy tắc dispatcher-type authorization có thể hợp lý trong một kiến trúc cụ thể, nhưng phải có test chứng minh initial authorization, context và endpoint response không bị bypass.

### Authentication và authorization có nhất thiết chạy hai lần?

Không có một câu trả lời đúng cho mọi app. Security filters có chính sách riêng; `FilterChainProxy` có thể được gọi ở nhiều dispatch và một số filter skip async/error. Một số lớp authorization có thể xét lại đường đi trong lượt tiếp theo; một số authentication mechanisms dùng context đã được lưu/khôi phục.

**Chính sách tốt:** tránh đặt quyết định cấp quyền trong custom log filter; cấu hình authorization trong Spring Security, phân tách rule theo dispatcher/path khi thực sự cần, và test toàn bộ lifecycle `REQUEST -> worker -> ASYNC` trên version bạn triển khai.

## 10. ERROR dispatch và nested dispatch

Async task có thể ném exception, timeout hoặc bị hủy. Spring MVC/Servlet container có cơ chế error handling/dispatch khác nhau; filter có thể gặp `DispatcherType.ERROR` hoặc response error được xử lý trong MVC tùy nguồn lỗi.

- `OncePerRequestFilter.shouldNotFilterErrorDispatch()` mặc định `true`: custom filter thường **không chạy lại phần doFilterInternal** ở error dispatch.
- Nếu override `false`, phải kiểm tra filter được map cho `ERROR` ở container, tránh side effects và chú ý **nested ERROR dispatch**.
- Một số container có thể thực hiện error dispatch lồng trong chuỗi trước khi marker của lần chạy trước được gỡ. `OncePerRequestFilter` có `doFilterNestedErrorDispatch` cho trường hợp này; không giả định nó hoàn toàn giống một lượt độc lập.
- Có thể có response đã committed hoặc error response do proxy/container tạo trước Spring MVC; custom filter không phải nơi phù hợp để “reset” response một cách tùy ý.
- Tránh ghi audit business event thêm lần nữa vì error dispatch; ghi lỗi vận hành riêng bằng logging/metrics đã lọc.

Ví dụ, nếu API có `Callable` ném exception, request có thể đi vào MVC exception handler mà không đi qua error dispatch riêng của container. Phải quan sát **dispatcher type thực tế**, không suy đoán từ HTTP 500.

## 11. Khác biệt của DeferredResult, CompletableFuture, @Async

| Kiểu công việc | Thread chạy nghiệp vụ | SecurityContext propagation | Có ASYNC dispatch? |
| --- | --- | --- | --- |
| Spring MVC `Callable` | Executor do MVC quản lý. | Spring Security MVC integration hỗ trợ Callable. | Thường có khi hoàn tất. |
| Spring MVC `DeferredResult` | Ứng dụng tự quyết định thread/callback hoàn thành kết quả. | Không tự giả định context truyền tới thread producer; dùng wrapper phù hợp. | Thường có khi kết quả được set. |
| Controller trả `CompletableFuture` | Executor/callback tùy cách tạo future. | Không mặc nhiên do OncePerRequestFilter truyền. | MVC có thể dùng async processing, tùy return value handler. |
| `@Async` ở service | TaskExecutor của Spring. | Cần thiết kế propagation nếu task cần caller context. | Không phải tự động một Servlet dispatch nếu nằm ngoài request lifecycle. |
| Queue consumer/scheduled task | Worker độc lập. | Không có end-user security context mặc định. | Không có HTTP Servlet dispatch trừ khi kết quả gắn với request qua cơ chế riêng. |

Không dùng `InheritableThreadLocal` như cách phổ quát cho thread pool; có thể mang context sai sang task tiếp theo. Không giữ `HttpServletRequest` để dùng lâu sau khi request hoàn tất: lifecycle/attributes không bảo đảm cho background jobs lâu dài. Truyền immutable actor ID hoặc correlation ID, chỉ propagate security context khi có ngữ nghĩa rõ và cleanup chính xác.

### DeferredResult minh họa (fragment)

~~~java
@GetMapping("/api/deferred")
public DeferredResult<String> deferred(Principal principal) {
    DeferredResult<String> result = new DeferredResult<>();

    String stableUser = principal.getName();
    trustedExecutor.execute(() -> {
        // Không tự động có SecurityContextHolder của request ở đây.
        result.setResult("hello " + stableUser);
    });

    return result;
}
~~~

Fragment yêu cầu `trustedExecutor` được inject, `DeferredResult`/`Principal` imports và proper timeout/error handling. Nó **cố tình chụp** một chuỗi đã xác thực trước khi chuyển thread, không truy cập SecurityContextHolder ở task. Với tác vụ cần quyền mới nhất, service vẫn phải kiểm policy phù hợp.

## 12. Chẩn đoán những lỗi async/filter thường gặp

| Triệu chứng | Nguyên nhân cần xét | Hướng xử lý |
| --- | --- | --- |
| Filter chạy hai lần cho một HTTP request | Có REQUEST và ASYNC dispatch; hoặc double registration. | Log dispatcher type và filter identity, so sánh chain vs servlet registration. |
| `shouldNotFilterAsyncDispatch(false)` nhưng không thấy ASYNC | Filter registration thiếu `DispatcherType.ASYNC`, security proxy không mapped cho ASYNC, hoặc không có async dispatch thật. | Kiểm dispatcher mapping, `asyncDispatch` và filter selection. |
| Một audit event bị ghi hai lần | Logic có side effect nằm trong filter chạy cả REQUEST và ASYNC. | Chuyển side effect sang service/outbox; nếu chỉ initial request, guard REQUEST. |
| MDC trace biến mất ở lượt hoàn tất response | MDC chỉ set ở REQUEST thread. | Re-establish MDC trên ASYNC dispatch, clear/restore trong finally. |
| MDC biến mất trong `Callable.call()` | Worker thread không chạy cùng Servlet filter. | TaskDecorator/wrapped executor; không nhầm với SecurityContext propagation. |
| SecurityContext mất trong custom executor | ThreadLocal không tự truyền. | `DelegatingSecurityContextExecutor` hoặc explicit actor propagation có cleanup. |
| `Callable` chạy nhưng HTTP response chưa xong trong MockMvc | Chưa gọi `asyncDispatch(result)`. | Test hai bước, quan sát `asyncStarted` và response cuối. |
| Start async lỗi IllegalStateException | Một filter/servlet registration không hỗ trợ async. | Kiểm `asyncSupported` của registration và container. |
| Một custom filter lúc chạy lúc không | SecurityChain matcher hoặc filter order/short-circuit khác nhau. | Kiểm request matcher, dispatch, order, registration. |
| ASYNC dispatch bị 403/401 khác REQUEST | SecurityContext/registration/authorization rules khác dispatch. | Test đúng lifecycle, xác minh config thay vì bật permitAll đại trà. |
| ERROR tạo thêm log/audit ngoài ý muốn | Filter mapped ERROR và không skip. | Thiết kế `shouldNotFilterErrorDispatch`/nested error policy. |
| Filter là @Component và addFilterBefore | Double registration hoặc thứ tự ngoài dự kiến. | Chỉ đăng ký ở một nơi; có thể disable Servlet registration nếu dùng bean. |
| Request ID khác giữa REQUEST và ASYNC | Tạo ID mới theo thread/dispatch. | Lưu một ID ổn định ở request attribute/gateway context đã tin. |
| Thông tin user sai giữa nhiều async tasks | Context bị rò ở ThreadLocal/thread pool. | Wrapper cleanup, không dùng static context hoặc inherited thread local tùy tiện. |
| POST bị xử lý trùng dù filter REQUEST-only | Client/gateway retry hoặc message redelivery. | Idempotency key, unique constraint, transaction/outbox. |

### Checklist debug theo thứ tự

1. Lấy một request ID đã sanitize để ghép log xuyên REQUEST, worker và ASYNC.
2. Ghi dispatcher type (`request.getDispatcherType()`), tên filter và thread name trong môi trường test, tránh log token/cookie.
3. Xác nhận controller trả `Callable`/`DeferredResult` và request thật sự async.
4. Kiểm Servlet registration cho REQUEST/ASYNC/ERROR; với Spring Security kiểm `DelegatingFilterProxy` và `FilterChainProxy`.
5. Kiểm `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch` của từng filter **liên quan**, không chỉ filter tự viết.
6. Kiểm xem filter có bị đăng ký hai nơi hay không.
7. Kiểm `SecurityContext` trong worker thread và Servlet async dispatch **riêng biệt**.
8. Nếu có side effects, quyết định chúng thuộc “request once”, “dispatch each”, hay “business exactly-once”, rồi đặt chúng đúng tầng.
9. Test MockMvc hai giai đoạn và một integration test với Servlet container thật khi vấn đề phụ thuộc registration.
10. Không sửa authorization thành `permitAll` hoặc disable CSRF chỉ để che lỗi async.

## 13. Câu hỏi tự kiểm tra

1. **ASYNC dispatch có đồng nghĩa HTTP request mới từ client không?** Không. Nó thường là lượt container tiếp tục xử lý cùng request sau khi công việc async hoàn tất.
2. **`OncePerRequestFilter` có thể gọi `doFilterInternal` hai lần trong một logical HTTP request không?** Có, khi filter tham gia cả REQUEST và ASYNC dispatch và cấu hình không skip ASYNC.
3. **Default `shouldNotFilterAsyncDispatch()` là gì?** `true`: bỏ qua ASYNC dispatch.
4. **Nếu override trả `false`, filter chắc chắn chạy trên ASYNC chưa?** Chưa. Servlet/security proxy registration phải map dispatcher type đó và filter phải thuộc chain đang được gọi.
5. **Marker “already filtered” có bảo đảm exactly-once payment không?** Không. Marker chỉ là state tạm trong request, không chống retries/partition hoặc worker khác.
6. **Làm thế nào tránh ghi audit event initial-only hai lần?** Chạy ở REQUEST dispatch, không làm lại ở ASYNC; cho nghiệp vụ quan trọng cần idempotency/outbox bền vững.
7. **MDC trên Servlet thread ban đầu có tự vào Callable worker không?** Không nên mặc định; cần observability context propagation riêng.
8. **Spring Security xử lý `SecurityContext` của Callable ra sao?** Có tích hợp Spring MVC `Callable` thông qua các thành phần như WebAsyncManagerIntegrationFilter; không suy rộng sang mọi executor/DeferredResult.
9. **`@Async` service có tạo ASYNC Servlet dispatch không?** Không tự nó. `@Async` là cơ chế chạy task; Servlet async dispatch phụ thuộc request/return value lifecycle.
10. **Vì sao không nên dùng `@Component` rồi lại `addFilterBefore`?** Có thể tạo hai registration với order/dispatcher types khác nhau; filter có thể chạy trùng hoặc khó đoán.
11. **Error dispatch giống ASYNC dispatch không?** Không. ERROR có mục tiêu và hook `shouldNotFilterErrorDispatch` riêng, có thể nested.
12. **Vì sao `DispatcherType.ASYNC permitAll` cần được xem xét kỹ?** Có thể làm thay đổi authorization policy của giai đoạn hoàn tất response; phải chứng minh initial request đã được bảo vệ và không tạo bypass.
13. **Nếu một filter cần MDC trên cả REQUEST và ASYNC, nên làm gì?** Bật xử lý ASYNC cho filter/registration, thiết lập MDC trên từng dispatch và restore/clear trong finally.
14. **Khi nào cần idempotency key thay vì request attribute?** Khi yêu cầu nghiệp vụ phải chống lặp giữa các HTTP requests, retries hoặc xử lý phân tán.
15. **Trong MockMvc, vì sao phải gọi `asyncDispatch(MvcResult)`?** Để mô phỏng lượt container dispatch lại và kiểm tra response cuối cùng cùng các filter chạy trên ASYNC.
16. **Nếu `Callable` đọc đúng Authentication nhưng một `CompletableFuture` không thấy SecurityContext, đây có phải mâu thuẫn không?** Không; các mô hình async có cơ chế context propagation khác nhau.

## 14. Bài tập thực hành có lời giải định hướng

**Bài 1 — Chỉ chạy initial REQUEST:** Tạo `InitialRequestFilter extends OncePerRequestFilter` mặc định không override async/error hooks. Trong `doFilterInternal`, ghi một marker; kiểm tra với `MockMvc asyncDispatch` marker vẫn còn trên request và filter không ghi thêm lần nữa. **Định hướng:** phân biệt marker do filter tự tạo với marker nội bộ “already filtered” có thể được gỡ trong finally.

**Bài 2 — Gắn correlation ID cho mọi Servlet dispatch:** Áp dụng `AsyncTraceFilter` ở mục 7. Quan sát `REQUEST_VISITS` và `ASYNC_VISITS` sau hai bước test. **Định hướng:** chỉ sinh trace ID mới khi request attribute chưa có; MDC phải được set và restore trong try/finally cho mỗi dispatch.

**Bài 3 — Cố tình tạo lỗi:** Đặt thao tác `auditRepository.save(...)` không có guard bên trong `doFilterInternal` với async hook false. **Định hướng:** thấy nó có thể chạy lại ở ASYNC; sửa bằng policy REQUEST-only cho audit request-start, hoặc chuyển nghiệp vụ quan trọng vào service/outbox idempotent.

**Bài 4 — DeferredResult:** Tạo một `DeferredResult` được hoàn thành từ custom executor và kiểm tra `SecurityContextHolder`. **Định hướng:** không suy từ kết quả Callable; dùng wrapper/decorator đúng hoặc truyền actor ID đã được xác thực.

**Bài 5 — Double registration:** Biến `AsyncTraceFilter` thành `@Component` nhưng vẫn thêm `addFilterBefore`, rồi kiểm tra registrations/log. **Định hướng:** loại một registration, không cố giấu lỗi bằng tăng marker hoặc đổi filter order tùy tiện.

**Bài 6 — Test security:** Xác nhận request GET /api/async không đăng nhập bị 401, đăng nhập đúng có `Callable` và response cuối 200; thử đổi dispatcher registration để quan sát hiệu ứng. **Định hướng:** không dùng “permitAll ASYNC” như phương án sửa tự động; kiểm tra lifecycle và context.

**Ghi nhớ:** `OncePerRequestFilter` giúp tránh thực thi lặp **trong phạm vi dispatch mà nó kiểm soát**, còn Servlet async có thể tạo **lượt ASYNC dispatch mới** trên thread khác. Đừng đánh đồng *một HTTP request* với *một filter invocation*, *một thread* hoặc *một business operation*. Cấu hình đúng dispatcher mapping, quyết định rõ hook ASYNC/ERROR cho từng filter, truyền `SecurityContext` và MDC bằng cơ chế phù hợp, và bảo vệ thao tác nghiệp vụ bằng idempotency thực sự khi cần.