# Kiểm thử trạng thái chéo giữa nhiều yêu cầu đồng thời trong Spring AOP

## 1. Mục tiêu và phạm vi

Khi nhiều HTTP request hoặc lời gọi dịch vụ đi qua cùng một Spring AOP proxy, **mỗi lời gọi phải giữ đúng dữ liệu ngữ cảnh của chính nó**: mã request, mã người dùng, tenant, thông tin audit, nhãn đo thời gian, correlation ID và kết quả xử lý. Bài này tập trung vào **cách thiết kế và kiểm thử tính cách ly trạng thái trong Spring Aspect**, đặc biệt khi aspect được Spring quản lý như một bean singleton. Không đi sâu vào lý thuyết AOP tổng quát.

Sau bài học, bạn có thể:

- Phân biệt dữ liệu nằm ở **biến cục bộ của advice** với dữ liệu đặt trong **field dùng chung của aspect**.
- Tái hiện một lỗi trạng thái chéo giữa hai lời gọi đồng thời bằng JUnit và các primitive đồng bộ, thay vì hy vọng lỗi xuất hiện khi chạy nhiều lần.
- Kiểm thử đúng **proxy/advice của Spring AOP**, kiểm tra trường hợp thành công, ngoại lệ và việc thu dọn context.
- Xác định giới hạn khi ứng dụng dùng thread pool, tác vụ bất đồng bộ hoặc Spring WebFlux.

**Tình huống:** request A mang correlation ID `A`, request B mang `B`. Nếu advice ghi ID hiện tại vào field `currentId` của một singleton aspect, B có thể ghi đè trong lúc A đang thực thi. Khi A tiếp tục, log hoặc audit của A lại nhận ID của B. Đây là lỗi cách ly ngữ cảnh; hệ thống có thể trả đúng kết quả nghiệp vụ mà audit vẫn sai.

## 2. Vì sao Spring Aspect dễ gặp lỗi này?

Ví dụ có lỗi:

~~~java
@Aspect
@Component
class AuditAspect {
    private String currentRequestId; // shared state trên singleton aspect

    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        currentRequestId = getRequestId();
        try {
            Object result = pjp.proceed();
            writeAudit(currentRequestId, result);
            return result;
        } finally {
            currentRequestId = null;
        }
    }

    // getRequestId và writeAudit là hàm ứng dụng, lược bỏ ở ví dụ minh họa.
}
~~~

Các lời gọi advice chạy trong các thread khác nhau nhưng thường cùng thao tác trên **một đối tượng aspect**. Field `currentRequestId` là trạng thái dùng chung. `volatile`, nếu thêm vào, chỉ hỗ trợ visibility; nó **không** biến dữ liệu thành riêng cho từng request. Đặt `synchronized` lên toàn bộ advice có thể tuần tự hóa cả đoạn nghiệp vụ, làm giảm concurrency và không phải thiết kế audit đúng đắn.

Bản sửa phù hợp cho dữ liệu chỉ sống trong một lần gọi:

~~~java
@Aspect
@Component
class AuditAspect {
    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        String requestId = getRequestId(); // biến cục bộ riêng cho mỗi invocation
        try {
            Object result = pjp.proceed();
            writeAudit(requestId, result);
            return result;
        } catch (Throwable error) {
            writeFailureAudit(requestId, error);
            throw error;
        }
    }

    // getRequestId, writeAudit, writeFailureAudit do ứng dụng triển khai.
}
~~~

Đây là **mã minh họa cách tổ chức advice**, chưa phải chương trình chạy độc lập vì các hàm tích hợp audit chưa có phần thân. Điểm cốt lõi là không giữ dữ liệu của từng request trong field aspect. Field chỉ nên chứa collaborator an toàn để dùng chung (service, repository, meter registry, cấu hình bất biến), hoặc trạng thái đã được thiết kế đồng bộ riêng với ý nghĩa dùng chung rõ ràng.

| Vị trí trạng thái | Phạm vi tồn tại thực tế | Đánh giá |
| --- | --- | --- |
| Biến cục bộ bên trong một lần chạy advice | Riêng cho invocation đó | Phù hợp nhất cho correlation ID, thời gian bắt đầu, kết quả tạm |
| Field mutable của singleton `@Aspect` | Chia sẻ giữa các invocation đồng thời | Nguy cơ ghi đè, đọc nhầm và race |
| `ThreadLocal` / MDC | Gắn với thread hiện tại | Có thể dùng trong luồng đồng bộ, **phải thu dọn**; không tự động theo một request qua mọi thread |
| Request-scoped context của Spring MVC | Gắn với request đang hoạt động | Hữu ích trong HTTP servlet request, cần truy cập đúng scope/proxy |
| Reactor `Context` trong WebFlux | Theo chuỗi reactive/subscription | Hướng phù hợp cho ngữ cảnh reactive; không xem ThreadLocal là request context tổng quát |

## 3. Thiết kế ca kiểm thử có khả năng tái hiện lỗi

Kiểm thử thông thường gọi lần lượt A rồi B sẽ khó thấy lỗi. Một bài kiểm thử concurrent cần tổ chức thứ tự đủ rõ:

1. Tạo **một proxy service và một instance aspect dùng chung**.
2. Chạy hai lời gọi `execute("A")` và `execute("B")` ở hai worker thread.
3. Trong target service, dùng `CyclicBarrier(2)` giữ cả hai thread cho đến khi **cả hai đã đi qua đoạn ghi dữ liệu của advice**.
4. Thả barrier để cả hai quay lại advice, đọc dữ liệu mà advice đang giữ.
5. Khẳng định dữ liệu trả cho A vẫn là A và cho B vẫn là B. Chạy tương tự với advice chỉ sử dụng biến cục bộ.

Barrier tạo được lịch thực thi đủ để phơi bày race theo thiết kế. `Thread.sleep(...)` không đảm bảo hai lời gọi thực sự chồng lấn, nên dễ gây test lúc pass lúc fail.

Lưu ý: đoạn mẫu dưới đây gọi service **qua Spring AOP proxy được tạo bằng `AspectJProxyFactory`**, không tạo HTTP request thật. Nó kiểm thử trực tiếp lỗi chia sẻ trạng thái trong Spring advice. Phần sau hướng dẫn kiểm thử qua application context và HTTP boundary.

## 4. Ví dụ JUnit 5: chứng minh lỗi và kiểm tra bản sửa

Với ứng dụng Spring Boot 3.x/Java 17+, cần có các dependency sau trong cấu hình Gradle của module Spring Boot hiện hữu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-aop` cung cấp tích hợp Spring AOP và AspectJ cần cho `@Aspect`; `spring-boot-starter-test` cung cấp JUnit Jupiter và các thành phần kiểm thử. Đoạn dependency trên giả định project đã cấu hình plugin Spring Boot cùng cơ chế quản lý phiên bản phù hợp.

Tạo file **`src/test/java/demo/AspectStateIsolationTest.java`**:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class AspectStateIsolationTest {

    // Target service chỉ phục vụ test: cả hai invocation cùng đi tới barrier.
    static class WorkService {
        private final CyclicBarrier bothInsideTarget = new CyclicBarrier(2);

        public String execute(String requestId) throws Exception {
            bothInsideTarget.await(10, TimeUnit.SECONDS);
            return requestId;
        }
    }

    @Aspect
    static class LeakyAspect {
        // Cố ý sai: field thuộc một aspect instance dùng chung.
        private volatile String currentRequestId;

        @Around("execution(* *..*.execute(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String requestId = (String) pjp.getArgs()[0];
            currentRequestId = requestId;
            pjp.proceed();
            return currentRequestId;
        }
    }

    @Aspect
    static class IsolatedAspect {
        @Around("execution(* *..*.execute(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String requestId = (String) pjp.getArgs()[0];
            pjp.proceed();
            return requestId; // giá trị local của chính invocation này
        }
    }

    private static WorkService proxyWith(Object aspect) {
        AspectJProxyFactory factory = new AspectJProxyFactory(new WorkService());
        factory.addAspect(aspect);
        return factory.getProxy();
    }

    private static Map<String, String> twoConcurrentCalls(WorkService service)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(() -> service.execute("A"));
            Future<String> b = pool.submit(() -> service.execute("B"));

            return Map.of(
                    "A", a.get(15, TimeUnit.SECONDS),
                    "B", b.get(15, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void mutableAspectFieldLeaksBetweenConcurrentCalls() throws Exception {
        Map<String, String> actual = twoConcurrentCalls(proxyWith(new LeakyAspect()));

        // Sau barrier, cả hai advice đọc cùng field chứa ID được ghi cuối.
        // Vì A và B khác nhau nên ít nhất một kết quả phải sai.
        assertNotEquals(Map.of("A", "A", "B", "B"), actual);
    }

    @Test
    void methodLocalStateStaysIsolated() throws Exception {
        Map<String, String> actual = twoConcurrentCalls(proxyWith(new IsolatedAspect()));

        assertEquals(Map.of("A", "A", "B", "B"), actual);
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.AspectStateIsolationTest
~~~

Trên Windows có thể dùng `gradlew.bat test --tests demo.AspectStateIsolationTest`.

**Kết quả có thể khẳng định:** cả hai test **PASS** nếu Spring AOP advice được áp dụng chính xác. Test đầu **chủ động kỳ vọng phát hiện lỗi** bằng `assertNotEquals`: nếu B là thread ghi cuối, map quan sát sẽ là `{A=B, B=B}`; nếu A ghi cuối, map là `{A=A, B=A}`. Không dự đoán thread nào sẽ ghi cuối hoặc thứ tự hiển thị của `Map`. Test thứ hai khẳng định map luôn là `{A=A, B=B}`. Kết quả chi tiết thời gian/đường log của Gradle khác nhau theo môi trường nên không coi chúng là stdout cố định.

Vì test dùng `AspectJProxyFactory`, nó kiểm tra AOP proxy thực, không cần khởi động web server. Target là class không `final`, method không `final`, để Spring tạo class-based proxy được. Trong ứng dụng thực, pointcut cần giới hạn chính xác tới package/annotation dịch vụ; wildcard rộng ở đây chỉ để bài test nhỏ không phụ thuộc tên module.

## 5. Kiểm thử qua Spring application context và HTTP request

Unit test ở mục 4 phơi bày chính xác lỗi chia sẻ field. Khi tích hợp vào ứng dụng, nên thêm kiểm thử qua bean thật để xác nhận hệ thống wiring cũng đúng:

- Bật Spring AOP bằng dependency và cấu hình phù hợp (chẳng hạn Spring Boot AOP auto-configuration hoặc `@EnableAspectJAutoProxy` trong cấu hình không dùng Boot).
- Lấy service từ `ApplicationContext`; kiểm tra `AopUtils.isAopProxy(service)` trong test setup và chứng minh pointcut thực sự chạy, ví dụ đếm invocation/ghi nhận event có kiểm soát.
- Gọi bean đã inject từ context; tránh `new Service()` và tránh một method trong bean tự gọi method khác của chính nó nếu đang kỳ vọng Spring proxy intercept self-invocation.
- Kiểm tra song song dữ liệu trả về và metadata do advice xử lý (correlation ID, tenant, audit event hoặc MDC), không chỉ mã HTTP 200.
- Trong test HTTP, gửi hai request đồng thời với header riêng như `X-Correlation-ID: A` và `X-Correlation-ID: B`; cho service đi qua một barrier có timeout để cố định thời điểm overlap. Kiểm tra cả response và sự kiện audit gắn với từng request.
- Dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` cùng HTTP client phù hợp nếu cần thử toàn bộ filter/controller/service/aspect; `MockMvc` cũng có thể được gọi đồng thời để kiểm tra nhiều lời gọi servlet nhưng không thay thế kiểm thử mọi thành phần của web server thật.

Một kiểm thử tốt phải có tín hiệu **advice đã thực sự chạy**. Nếu pointcut không match hoặc lời gọi bỏ qua proxy, một test chỉ kiểm tra business output có thể PASS dù phần aspect hoàn toàn không được thực thi.

Với nhiều hơn hai request, có thể chạy 10–100 task qua một proxy, gán ID duy nhất, thu thập dữ liệu theo ID và kiểm tra ánh xạ một-một. Đây là stress test bổ sung để phát hiện đường đi khác; nó không thay thế ca barrier có lịch thực thi kiểm soát.

## 6. Kiểm thử cleanup khi có ngoại lệ và thread pool tái sử dụng

Một lỗi khác là advice gán `ThreadLocal` hoặc MDC nhưng quên xóa. Trong servlet MVC đồng bộ, thread từ pool có thể phục vụ request kế tiếp; metadata cũ có thể xuất hiện trong log của request mới. Mẫu chuẩn nên khôi phục **giá trị trước đó**, kể cả khi target ném exception:

~~~java
@Aspect
@Component
class CorrelationAspect {
    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object withCorrelation(ProceedingJoinPoint pjp) throws Throwable {
        String previous = org.slf4j.MDC.get("requestId");
        String current = resolveRequestId(); // hàm tích hợp của ứng dụng
        try {
            org.slf4j.MDC.put("requestId", current);
            return pjp.proceed();
        } finally {
            if (previous == null) {
                org.slf4j.MDC.remove("requestId");
            } else {
                org.slf4j.MDC.put("requestId", previous);
            }
        }
    }

    // resolveRequestId được ứng dụng triển khai.
}
~~~

Đoạn này là **mã minh họa**. Nó thể hiện phạm vi cleanup trong `finally`, không phải cơ chế tự động truyền MDC tới task bất đồng bộ.

Bộ test nên có các trường hợp sau:

| Ca kiểm thử | Thiết lập | Điều phải xác minh |
| --- | --- | --- |
| Hai lời gọi thành công cùng lúc | A, B và barrier ở target | Không nhầm ID/tenant/audit giữa A và B |
| A thành công, B ném exception | Hai request chạy xen kẽ, một đường lỗi | Advice không làm mất exception, audit lỗi đúng ID |
| Hai task nối tiếp trên **cùng một worker thread** | Executor một thread; request thứ nhất có ID, request sau không có | Không còn MDC/ThreadLocal cũ sau request đầu |
| Advice gọi lồng nhau | Có giá trị context bên ngoài; advice bên trong thay tạm | Giá trị ngoài được khôi phục khi thoát |
| Target bị hủy hoặc timeout | Tạo lỗi có kiểm soát, thread được trả về pool | Cleanup trong `finally` vẫn chạy nếu control flow thực sự thoát khỏi advice |
| Lời gọi bỏ qua proxy | Self-invocation hay đối tượng `new` trực tiếp | Test phát hiện advice không chạy, không báo isolation pass giả |

Không nên viết test chỉ đọc MDC ở thread của JUnit rồi suy luận về MDC trên worker khác: MDC thường gắn với từng thread. Phải quan sát ở chính thread xử lý hoặc thu event có request ID trước khi worker kết thúc. Với phép thử tái sử dụng thread, chọn executor một thread, thu lại MDC trong callable thứ hai và kết thúc executor ở `finally`.

## 7. ThreadLocal, @Async và WebFlux: chọn đúng ranh giới test

**Servlet MVC đồng bộ:** một request thường chạy trên một worker thread ở đoạn synchronous pipeline; ThreadLocal/MDC có thể phù hợp cho logging, với điều kiện giữ phạm vi rõ ràng, xử lý các dispatch bất đồng bộ và luôn cleanup.

**`@Async`, `CompletableFuture`, executor:** luồng thực thi có thể chuyển sang thread khác. ThreadLocal/MDC của thread gọi không tự động truyền sang worker. Khi thật sự cần propagation, dùng cơ chế được kiểm soát như `TaskDecorator`/wrapper chụp và khôi phục context; test phải chứng minh cả propagation **và** cleanup ở thread thực thi. Việc dùng virtual thread không loại bỏ nhu cầu xác định lifetime của context.

**Spring WebFlux/Reactor:** một request không tương đương một thread cố định. Không dựa vào mutable field của aspect hoặc MDC ThreadLocal như nguồn ngữ cảnh chính cho toàn chuỗi reactive. Với reactive context, ưu tiên `Reactor Context` và các cơ chế context propagation chính thức; kiểm thử qua việc subscribe, đổi scheduler, lỗi, hủy subscription khi có giá trị học tập. Advice `@Around` trả `Mono`/`Flux` có thể kết thúc khi **publisher được tạo**, trước khi pipeline thực thi; muốn ghi nhận kết quả cuối phải dùng operator thích hợp trên publisher, không mặc định coi `pjp.proceed()` là lúc dữ liệu đã được phát ra.

**Request scope:** một bean `@RequestScope` tạo đối tượng theo request web đang hoạt động; nếu aspect singleton cần collaborator theo request, thường inject scoped proxy/provider thay vì chép request ID vào field. Kiểm thử request scope phải chạy trong môi trường có request context hợp lệ.

## 8. Những sai lầm thường gặp khi viết test

1. **Gọi target trực tiếp** khiến advice không chạy; nếu đang kiểm thử Spring AOP thì bắt buộc đi qua proxy.
2. **Tạo aspect mới cho mỗi task** làm mất tình huống singleton dùng chung cần thử; ít nhất một case phải có nhiều task trên cùng proxy/aspect instance.
3. **Chỉ dùng sleep hoặc tăng số lượng thread** mà không tạo overlap có kiểm soát; test dễ pass ngẫu nhiên.
4. **Thấy lỗi biến mất sau khi thêm volatile rồi kết luận an toàn**: visibility không tạo isolation.
5. **Không kiểm tra MDC/ThreadLocal sau exception** khiến lỗi xuất hiện ở request tiếp theo trên thread pool.
6. **Chỉ assert business response** trong khi lỗi nằm trong logging, audit, tenant routing hoặc tracing metadata.
7. **Dùng một barrier không timeout** có thể làm CI treo nếu một nhánh lỗi trước khi tới điểm đồng bộ.
8. **Nhầm mô hình reactive với servlet**: chuyển thread/scheduler làm suy luận theo thread hiện tại sai.

## 9. Checklist áp dụng vào dự án

- Xác định `@Aspect` có field mutable nào lưu dữ liệu phụ thuộc invocation/request không; các field này là ứng viên kiểm tra đầu tiên.
- Ghi rõ nguồn request ID/tenant và điểm advice lấy, truyền, log, audit, cleanup.
- Tạo ít nhất một test deterministic với 2 concurrent calls đi qua **cùng Spring AOP proxy**, dùng barrier hoặc latch có timeout.
- Assert kết quả **theo từng request ID**, bao gồm cả audit/logging metadata; xác nhận advice thực sự khớp pointcut.
- Thêm case ngoại lệ, nested invocation và reuse worker thread nếu hệ thống có ThreadLocal/MDC.
- Nếu có `@Async` hoặc Reactor, xây dựng test truyền ngữ cảnh riêng cho mô hình thực thi tương ứng.
- Đảm bảo thread pool được shutdown và mọi primitive đồng bộ đều có timeout để test dừng khi lỗi.

**Tiêu chí hoàn thành:** Với một aspect đúng, hai yêu cầu có ngữ cảnh A/B dù chạy xen kẽ vẫn sinh dữ liệu A/B đúng chủ sở hữu; khi xảy ra lỗi, advice giữ nguyên exception và thu dọn context; khi đổi thread, việc truyền ngữ cảnh được kiểm thử theo cơ chế mà ứng dụng thực sự dùng.
