# Spring AOP với phương thức trả Publisher: thời điểm thực thi và trạng thái reactive

## Mục tiêu

Khi một Spring bean có phương thức trả Reactor Mono/Flux hoặc Reactive Streams Publisher, cần phân biệt **lần gọi phương thức đi qua Spring AOP proxy** và **lần subscribe vào Publisher mà phương thức trả về**. Hai thời điểm có thể cách nhau lâu, xảy ra trên thread khác nhau hoặc không bao giờ có subscribe. Vì thế advice đo thời gian, log lỗi hay quản lý trạng thái bằng cách chỉ đặt lệnh trước/sau ProceedingJoinPoint.proceed() thường không quan sát được toàn bộ công việc bất đồng bộ.

Sau bài này, có thể xác định advice nào chạy lúc trả Publisher, đặt xử lý vào đúng vòng đời subscription, lưu trạng thái an toàn khi nhiều subscriber đồng thời và kiểm thử kết quả khi hoàn tất, lỗi hoặc hủy.

## 1. Ranh giới Spring AOP proxy và reactive pipeline

Spring AOP ở chế độ proxy chặn **method execution** được gọi qua Spring-managed bean proxy. Phương thức trả Mono/Flux vẫn là một lần thực thi phương thức Java bình thường: lời gọi đi qua proxy, vào advice, tới thân phương thức, rồi trả một đối tượng Publisher.

Ví dụ:

~~~java
@Service
class BookService {
    public Mono<String> findTitle() {
        System.out.println("method body: build Mono");
        return Mono.fromSupplier(() -> {
            System.out.println("deferred work");
            return "Spring AOP";
        });
    }
}
~~~

Giả sử client nhận bean qua Spring proxy và gọi:

~~~java
Mono<String> result = bookService.findTitle(); // proxy/advice chạy tại đây
// ... thời gian trôi qua, chưa subscribe ...
String title = result.block();                  // subscribe tại đây
~~~

- Khi gọi findTitle(): thân phương thức chạy và tạo Mono; mọi logic advice thông thường bao quanh lần gọi cũng chạy. Dòng "method body: build Mono" được in ngay.
- Khi block() hoặc subscribe(): Mono.fromSupplier mới chạy supplier và in "deferred work". Spring AOP **không tự chặn một lần thứ hai** tại thời điểm này.
- Nếu không ai subscribe thì phần deferred work chưa chạy. Nhưng các hiệu ứng phụ *eager* đặt trực tiếp trong thân phương thức/advice đã xảy ra.
- Nếu hai subscriber đăng ký vào một cold Publisher, phần công việc upstream có thể chạy hai lần; **advice ở ranh giới phương thức** vẫn chỉ chạy một lần nếu chỉ gọi phương thức một lần.
- Nếu phương thức trả hot/eager Publisher, hoặc dùng cache/share, công việc và hành vi chia sẻ có thể khác. Không suy đoán mọi Publisher đều lazy, cold hay phát lại cho mỗi người subscribe.

Mô hình thời gian điển hình:

~~~text
T0  caller -> Spring proxy -> @Around.enter
T1  @Around -> proceed() -> target tạo Publisher -> trả Publisher
T2  @Around.exit -> caller nhận Publisher
    ... chưa có subscription; có thể đổi thread ...
T3  subscriber đăng ký vào Publisher
T4  upstream xử lý và phát onNext (0..n), onError hoặc onComplete
T5  subscription có thể kết thúc bằng cancel trước tín hiệu cuối
~~~

T0–T2 đo **thời gian gọi method / lắp pipeline (assembly)**. T3–T5 là **vòng đời subscription / thực thi luồng**. Với thao tác bất đồng bộ, T2 không đồng nghĩa truy vấn đã hoàn tất, kết nối đã giải phóng hay phản hồi đã gửi.

## 2. Spring advice nào nhìn thấy điều gì?

| Thành phần Spring AOP | Khi nào chạy đối với phương thức trả Publisher? | Không nên hiểu nhầm |
| --- | --- | --- |
| @Before | Trước lời gọi phương thức đích, khi đi qua proxy | Không phải callback trước mỗi subscription |
| @AfterReturning | Khi phương thức trả bình thường; giá trị trả về thường là đối tượng Mono/Flux/Publisher | Không phải dữ liệu onNext hay sự kiện onComplete |
| @AfterThrowing | Khi bản thân lần thực thi phương thức qua proxy ném lỗi đồng bộ | Không tự nhận onError phát ra muộn từ Publisher |
| @After | Khi lần thực thi phương thức qua proxy thoát, kể cả ném lỗi | Không đợi pipeline hoàn thành/cancel |
| @Around | Bao quanh proceed() và có thể thay Publisher trả về bằng Publisher đã gắn operator | Chỉ phần mã chạy trong advice là đồng bộ; operator bên trong Publisher có vòng đời riêng |

Ví dụ dưới đây chỉ log thời gian gọi phương thức (có ích để đo chi phí xây pipeline, **không phải** độ trễ reactive):

~~~java
@Around("execution(reactor.core.publisher.Mono demo.BookService.*(..))")
public Object assemblyTime(ProceedingJoinPoint pjp) throws Throwable {
    long start = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long nanos = System.nanoTime() - start;
        System.out.println("method/assembly ns = " + nanos);
    }
}
~~~

Nếu một Mono đã được trả thành công nhưng sau đó phát onError, @AfterReturning cho lần gọi phương thức vẫn có thể đã chạy. Hai kết quả không mâu thuẫn: một là *return bình thường của Java method*, một là *terminal signal của reactive sequence*. Tương tự, catch (Throwable) quanh proceed() chỉ bắt lỗi xảy ra ngay khi gọi method, không bắt lỗi do supplier, map, flatMap hoặc I/O phát ra lúc subscribe.

## 3. Cách viết @Around để quan sát subscription

Khi mục tiêu là đếm subscription, đo thời gian xử lý thực tế và ghi nhận trạng thái terminal, advice cần **trả lại một Publisher được trang trí bằng Reactor operators**.

Một pattern cho phương thức khai báo trả Mono:

~~~java
@Around("execution(reactor.core.publisher.Mono demo.BookService.*(..))")
public Object observeMono(ProceedingJoinPoint pjp) throws Throwable {
    Object returned = pjp.proceed(); // gọi target tại thời điểm method invocation
    if (!(returned instanceof Mono<?> source)) {
        return returned; // hợp đồng return type cần được giữ nguyên
    }

    String operation = pjp.getSignature().toShortString();

    return Mono.defer(() -> {
        long start = System.nanoTime(); // mỗi subscription có state riêng
        System.out.println("subscribed: " + operation);

        return source
            .doOnNext(value -> System.out.println("onNext: " + operation))
            .doOnError(error -> System.out.println(
                "onError: " + operation + ", " + error.getClass().getSimpleName()))
            .doFinally(signal -> {
                long elapsedNs = System.nanoTime() - start;
                System.out.println("terminal: " + operation + ", "
                    + signal + ", elapsedNs=" + elapsedNs);
            });
    });
}
~~~

Điểm cần đọc chính xác:

1. proceed() vẫn được gọi khi Spring proxy nhận lời gọi, vì vậy thân phương thức không bị hoãn sang một thời điểm khác ngoài ý muốn.
2. Mono.defer tạo mới start cho **mỗi lần subscribe**. Không để start trong field mutable của singleton @Aspect hay biến dùng chung giữa các subscriber.
3. doOnNext quan sát phần tử; một Mono rỗng có thể hoàn thành mà không phát onNext. doOnSuccess (nếu cần) có quy ước riêng cho Mono rỗng: callback có thể nhận null.
4. doOnError quan sát tín hiệu lỗi từ upstream. Khi upstream phát onError, doFinally nhận ON_ERROR; thành công nhận ON_COMPLETE; hủy nhận CANCEL.
5. doFinally hữu ích cho metrics và cleanup vì có cả cancellation. Callback doFinally là side effect, không nên dựa vào nó để sửa giá trị Publisher hoặc bảo đảm một thứ tự log tuyệt đối với thread đang chờ block().
6. Advice phải trả về kiểu tương thích với chữ ký phương thức. Không trả Flux cho phương thức khai báo Mono; không ép mọi Publisher về Mono (sẽ làm mất ngữ nghĩa nhiều phần tử).

Trường hợp đặc biệt: nếu proceed() ném Throwable **ngay tại thời điểm gọi phương thức**, khối advice ở trên chưa tạo được wrapper; đó là lỗi đồng bộ, vẫn nên cho Spring xử lý theo đường lỗi đồng bộ hoặc quan sát riêng bằng try/catch quanh proceed(). Không âm thầm biến mọi lỗi đồng bộ thành onError nếu không chủ đích thay đổi hợp đồng API.

### Biến thể với Flux

Với phương thức khai báo Flux, sử dụng Flux.defer và các operator cùng ý nghĩa:

~~~java
@Around("execution(reactor.core.publisher.Flux demo.StreamService.*(..))")
public Object observeFlux(ProceedingJoinPoint pjp) throws Throwable {
    Flux<?> source = (Flux<?>) pjp.proceed();
    String operation = pjp.getSignature().toShortString();

    return Flux.defer(() -> {
        long start = System.nanoTime();
        return source
            .doOnSubscribe(s -> System.out.println("subscribe " + operation))
            .doOnError(e -> System.out.println("error " + operation))
            .doFinally(signal -> System.out.println(
                operation + ": " + signal + " after "
                + (System.nanoTime() - start) + " ns"));
    });
}
~~~

Với chữ ký trả org.reactivestreams.Publisher<T>, có thể dùng Flux.from(source) **khi tương thích với hợp đồng**. Cần xét riêng đối tượng trả về Mono, Flux, publisher tùy biến, empty/null (trong API reactive thường cần tránh null), khả năng nhiều phần tử, backpressure và yêu cầu giữ identity/behavior; đừng áp một phép ép kiểu Mono/Flux không an toàn cho mọi endpoint.

## 4. Ví dụ chạy được: Spring proxy + Mono trả về trước khi chạy công việc

Ví dụ độc lập sau dùng Java 17, Spring Framework 6.1, Reactor Core và Spring AOP kiểu @AspectJ (proxy của Spring, không cần AspectJ weaving). Cấu trúc:

~~~text
reactive-aop-demo/
├── pom.xml
└── src/main/java/demo/App.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-aop-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.1.15</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22.1</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration><mainClass>demo.App</mainClass></configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/App.java**

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            GreetingService service = context.getBean(GreetingService.class);

            System.out.println("A. call through proxy");
            Mono<String> mono = service.greet("Ada");
            System.out.println("B. method returned");
            String value = mono.block();
            System.out.println("C. value = " + value);
        }
    }
}

@Component
class GreetingService {
    public Mono<String> greet(String name) {
        System.out.println("target: build Mono");
        return Mono.fromSupplier(() -> {
            System.out.println("source: compute");
            return "Hello " + name;
        });
    }
}

@Aspect
@Component
class ReactiveObservationAspect {
    @Around("execution(reactor.core.publisher.Mono demo.GreetingService.greet(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("advice: enter");
        Mono<?> source = (Mono<?>) pjp.proceed();
        System.out.println("advice: wrap Publisher");

        return Mono.defer(() -> {
            System.out.println("pipeline: subscribe");
            return source
                .doOnNext(value -> System.out.println("pipeline: onNext"))
                .doOnError(error -> System.out.println("pipeline: onError"))
                .doFinally(signal ->
                    System.out.println("pipeline: finally " + signal));
        });
    }
}
~~~

Tại thư mục dự án, chạy:

~~~bash
mvn -q compile exec:java
~~~

Phần thứ tự có ý nghĩa ở output (bỏ qua mọi log khởi động của thư viện) là:

~~~text
A. call through proxy
advice: enter
target: build Mono
advice: wrap Publisher
B. method returned
pipeline: subscribe
source: compute
pipeline: onNext
~~~

Kết quả "C. value = Hello Ada" xuất hiện sau khi block() đã lấy được giá trị. Callback "pipeline: finally onComplete" cũng chạy khi chuỗi kết thúc, nhưng không nên phụ thuộc vào thứ tự chính xác của dòng log này so với dòng C trong mọi cách lập lịch/thread. Thay block() bằng việc chỉ giữ biến mono: sẽ chỉ thấy các log đến "B. method returned", vì Mono từ supplier chưa có subscriber.

Ví dụ này cố ý đo thời điểm subscription thông qua Mono.defer. Nó không gọi subscribe() trong advice: quyền subscribe thuộc về downstream (ví dụ tầng WebFlux), nơi quyết định demand, xử lý lỗi và cancellation.

## 5. Trạng thái và đồng thời: một lời gọi, nhiều subscriptions

Giả sử:

~~~java
Mono<String> onePublisher = service.greet("Ada");
Mono<String> first = onePublisher;
Mono<String> second = onePublisher;
~~~

Lúc khai báo onePublisher, Spring proxy chạy **một lần**. Nếu first và second được subscribe độc lập, Mono.defer trong wrapper chạy **hai lần**, mỗi lần có start riêng. Với publisher cold từ supplier, công việc có thể thực hiện hai lần; với publisher được cache/hot, số lần thực thi upstream có thể khác. Trạng thái advice nên phản ánh đúng đại lượng đang đo:

| Đại lượng | Nơi đếm phù hợp | Ý nghĩa |
| --- | --- | --- |
| Số lần bean method được gọi qua proxy | Thân @Before/@Around trước proceed() | Invocation count |
| Chi phí tạo/trả Publisher | Trước và sau proceed() | Assembly time |
| Số lần subscribe vào Publisher đã trả | Mono.defer/Flux.defer hoặc doOnSubscribe phù hợp | Subscription count |
| Thời gian một subscription tồn tại | Bắt đầu mỗi subscription, kết thúc ở doFinally | Subscription duration |
| Số onNext/onError/onComplete/cancel | Reactor operator tương ứng | Reactive signal count |

Trong hệ thống concurrent, @Aspect thường là Spring singleton. Field như "long startNanos" trên @Aspect bị ghi đè giữa nhiều invocation và nhiều subscriber; dùng biến local của invocation nếu đo assembly và biến local **bên trong defer** nếu đo subscription. Khi ghi counters/metrics dùng cơ chế thread-safe (LongAdder, AtomicLong, metrics recorder); đừng cập nhật một HashMap thường từ nhiều callback concurrent.

Reactive có thể đổi thread do scheduler hoặc I/O callback. ThreadLocal và MDC được thiết lập trong @Around lúc method được gọi **không mặc nhiên có mặt** trong onNext/onError ở thread khác. Nếu cần correlation id/request context, ưu tiên Reactor Context và cơ chế context propagation được cấu hình của hệ sinh thái Spring, thay vì giả định ThreadLocal lan truyền tự động:

~~~java
return Mono.deferContextual(context -> {
    String requestId = context.getOrDefault("requestId", "unknown");
    return source.doOnError(error ->
        logger.warn("requestId={} failed", requestId, error));
});
~~~

Mã trên minh họa việc lấy context theo subscriber; logger và source là các biến đã tồn tại trong method/advice tương ứng. Chỉ đọc context tại assembly bằng ThreadLocal rồi giữ làm state toàn cục dễ gắn nhầm request khi có concurrent subscriptions. Nếu ứng dụng có cơ chế bridge Reactor Context ↔ MDC, kiểm tra chính sách propagating context thực tế của ứng dụng.

## 6. Completion, lỗi, cancellation và ngữ nghĩa đo thời gian

Trong reactive flow, "method returns" khác với các tín hiệu sau:

- onNext mang dữ liệu (Mono tối đa một phần tử, Flux có thể nhiều phần tử).
- onComplete xác nhận Publisher kết thúc bình thường; Mono rỗng vẫn có onComplete.
- onError kết thúc luồng bằng lỗi; callback @AfterThrowing của Spring AOP cho lần trả Publisher không thay thế doOnError.
- cancel là hành động downstream yêu cầu hủy subscription; upstream có thể đang xử lý tài nguyên/tác vụ, và việc hủy không đồng nghĩa mọi tác vụ ngoại vi đã bị dừng tức thì.

Đo một yêu cầu WebFlux bằng đồng hồ đặt trước proceed() rồi dừng ngay sau proceed() thường chỉ đo việc tạo pipeline. Dùng defer + doFinally giúp đo thời gian mỗi subscription, bao gồm khoảng chờ dữ liệu khi subscription thực sự bắt đầu. Chọn rõ định nghĩa latency: **từ lúc method invocation**, **từ lúc subscribe**, **đến phần tử đầu tiên**, hay **đến terminal**. Chúng là các metric khác nhau; tên metric không nên đánh đồng.

Operator doFinally là nơi hợp lý để quan sát ON_COMPLETE, ON_ERROR và CANCEL; với resource thực sự, dùng API quản lý tài nguyên đúng ngữ nghĩa reactive (ví dụ usingWhen) thay vì dựa vào finally của method tạo Publisher. Đặt doOnError gần upstream chỉ ghi lỗi, không tự xử lý/phục hồi lỗi; nếu pipeline có onErrorResume ở downstream thì kết quả cuối cùng của toàn chuỗi có thể là thành công. Vị trí operator trong chuỗi ảnh hưởng đại lượng được quan sát.

Với Flux không kết thúc (stream dài hạn, SSE), duration đến terminal có thể rất dài hoặc chỉ dừng khi cancel; nên bổ sung chỉ số "time to first signal" khi đó mới là nhu cầu thực tế. Nếu publisher chưa bao giờ có subscriber, metrics subscription không được tạo, nhưng invocation metrics vẫn được ghi.

## 7. Spring-managed transaction advice và Reactor Context

Một trường hợp quan trọng trong Spring là @Transactional. Spring dùng TransactionInterceptor dựa trên AOP proxy. Với **ReactiveTransactionManager** và phương thức trả reactive type phù hợp, Spring sử dụng nhánh giao dịch reactive; ngữ cảnh giao dịch được truyền bằng **Reactor Context** gắn với reactive pipeline, thay vì dựa vào thread-bound transaction của PlatformTransactionManager.

Do đó:

- Không kết luận transaction đã commit chỉ vì một @AfterReturning quan sát thấy phương thức trả Mono thành công.
- Không lấy transaction state bằng ThreadLocal tùy ý trong callback reactive rồi giả định nó luôn đúng trên mọi scheduler.
- Không mở/đóng transaction thủ công quanh proceed() và cho rằng nó tự bao phủ toàn bộ pipeline; phần làm việc với DB có thể diễn ra sau khi proceed() trả về.
- Nếu phối hợp nhiều aspect (metrics, authorization, transactional advice), cân nhắc thứ tự advisor/@Order và vị trí các operator, vì lớp wrapper của mỗi interceptor ảnh hưởng vị trí quan sát tín hiệu.
- Quy tắc giao dịch cụ thể còn phụ thuộc transaction manager đã cấu hình, kiểu trả về và cách pipeline được subscribe. Không coi mọi @Transactional trên Mono là reactive transaction nếu ứng dụng chỉ có imperative manager.

Phần này chỉ giải thích hệ quả tại ranh giới Spring AOP; cấu hình transaction và thiết kế dữ liệu reactive thuộc phạm vi bài transaction/WebFlux riêng.

## 8. Các lỗi thường gặp và cách sửa

| Cách làm có lỗi | Hệ quả | Hướng sửa trong Spring AOP |
| --- | --- | --- |
| Log "request success" trong @AfterReturning khi nhận Mono | Báo thành công trước khi pipeline có thể phát onError | Phân biệt "Publisher returned" với doOnComplete/doOnError |
| Dùng try/catch quanh proceed() để bắt mọi lỗi async | Bỏ sót onError phát ra khi subscribe | Quan sát doOnError trong Publisher; bắt đồng bộ riêng |
| Đặt mutable startTime ở field của @Aspect | Race khi nhiều request/subscriber | Local theo invocation hoặc local mỗi defer |
| Gọi block()/subscribe() bên trong advice | Chiếm quyền thực thi của WebFlux, thêm subscription, có thể block event loop | Trả Publisher được decorate; để downstream subscribe |
| Gọi proceed() từ callback của Mono.defer mà không xét chủ đích | Dịch việc chạy method và chuỗi advice sang subscription; có thể chạy nhiều lần | Thông thường proceed() khi invocation, chỉ defer các callbacks reactive |
| Trả Flux từ advice cho method khai báo Mono | Sai return contract, có thể ClassCastException | Giữ nguyên Mono/Flux tương ứng |
| Cho rằng publisher nào cũng cold | Đo sai side effects, duplicate work, timing | Biết rõ cold/hot/cache/share của publisher nguồn |
| Tin vào MDC/ThreadLocal xuyên scheduler | Sai request id hoặc mất context | Reactor Context và propagation được cấu hình |
| Dùng @After để release tài nguyên async | Đóng trước khi subscriber dùng xong | Quản lý resource theo reactive lifecycle |
| Gọi nội bộ this.otherMethod() và mong advice chạy | Self-invocation bỏ qua Spring proxy | Gọi qua bean proxy hợp lệ hoặc tổ chức lại bean boundary |
| Target là final class/final method dùng class-based proxy | Proxy khó/không thể advice method như mong muốn | Dùng kiểu bean/proxy phù hợp, kiểm tra proxying constraints |

## 9. Checklist kiểm thử

Kiểm thử đúng ranh giới Spring AOP phải **lấy bean từ Spring context**, không tự new target. Kiểm thử ít nhất các tình huống sau:

1. **Chưa subscribe:** gọi method, xác nhận advice invocation đã chạy; deferred supplier và subscription observer chưa chạy.
2. **Subscribe một lần:** xác nhận upstream phát giá trị, observer thấy tín hiệu; lỗi không bị biến thành success.
3. **Subscribe hai lần vào cùng Publisher:** advice invocation một lần, observer subscription hai lần; đối chiếu tính cold/hot/cached của nguồn.
4. **Lỗi đồng bộ:** method ném ngay trước khi trả Publisher; quan sát qua Spring advice lỗi đồng bộ.
5. **Lỗi reactive:** method trả Mono.error(...) bình thường; nhận onError trong pipeline nhưng @AfterThrowing không bị gọi chỉ bởi terminal error này.
6. **Mono.empty():** không có onNext nhưng có complete; mã đo duration vẫn dừng.
7. **Cancellation:** subscription bị dispose/cancel; doFinally nhận CANCEL khi cancellation đi qua operator đó.
8. **Concurrency:** nhiều subscription trên các scheduler, không chia sẻ timestamp hoặc request id sai.
9. **Proxy boundary:** gọi từ bean bên ngoài qua Spring proxy; so sánh self-invocation nếu cần xác định vì sao advice không kích hoạt.

Với Reactor Test có thể dùng StepVerifier để xác nhận completion/error/cancel và dùng AtomicInteger/LongAdder để đếm invocation, subscription, terminal. Tránh assert thứ tự tuyệt đối của log hoặc thời gian nanosecond; đồng bộ qua tín hiệu reactive và điều kiện kiểm thử có thể quan sát.

## Ghi nhớ

**Spring AOP chặn lần gọi phương thức trả Publisher; Reactive Streams điều khiển công việc theo subscription và signal.** Với Mono/Flux lazy, việc Spring advice thấy một đối tượng trả về không có nghĩa công việc upstream đã hoàn tất. Muốn quan sát tiến trình thực, gắn Reactor operators vào Publisher được trả về, quản lý state theo từng subscription và phân biệt rạch ròi lỗi đồng bộ của method với onError bất đồng bộ của pipeline.

Tài liệu chính thức:
- Spring Framework — Declaring Advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — TransactionInterceptor và giao dịch reactive: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Reactor — Error handling và doFinally: https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html
