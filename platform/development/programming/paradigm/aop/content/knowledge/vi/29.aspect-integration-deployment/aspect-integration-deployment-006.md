# Loại trừ mã sinh, thư viện ngoài và công cụ quan sát khi cần trong Aspect (AOP)

## Mục tiêu

Một aspect được thiết kế để thực thi một mối quan tâm xuyên suốt chương trình, ví dụ đo thời gian, ghi nhật ký, kiểm tra điều kiện, theo dõi lỗi hoặc quản lý tài nguyên. Khi điểm cắt (**pointcut**) khớp quá rộng, advice có thể chạy trên cả mã được sinh tự động, mã thư viện bên ngoài và chính cơ chế quan sát mà advice sử dụng. Kết quả có thể là log trùng, overhead lớn, lời gọi đệ quy, deadlock, mất khả năng chẩn đoán hoặc thay đổi hành vi nghiệp vụ.

Bài này tập trung vào **cách quyết định những nơi cần loại trừ, thực hiện loại trừ ở đúng tầng và xác minh không vô tình bỏ sót chức năng quan trọng** trong lập trình hướng khía cạnh (Aspect-Oriented Programming, AOP) nói chung. Bạn sẽ:

- Phân biệt **miền được áp dụng advice** với **miền được weaving/instrumentation**.
- Nhận diện trường hợp mã sinh, thư viện ngoài hoặc logger/tracer/metric collector cần được bỏ qua.
- Thiết kế **allowlist trước, exclusions có lý do rõ ràng sau**, xét đến class, method, annotation, classloader và loại join point.
- Hiểu các khác biệt giữa loại trừ lúc weaving và chỉ bỏ qua xử lý trong runtime advice.
- Kiểm thử được phạm vi, tính đúng đắn, bảo mật và hiệu năng sau khi thay đổi pointcut.

Không tồn tại một cú pháp pointcut hay quy tắc loại trừ duy nhất áp dụng cho mọi công cụ AOP. Các ví dụ về biểu thức pointcut trong bài là **mã giả**; hãy chuyển chúng sang cú pháp của cơ chế đang sử dụng.

## 1. Vì sao loại trừ là một phần của thiết kế aspect?

Các khái niệm nền:

| Khái niệm | Vai trò |
| --- | --- |
| **Join point** | Vị trí mà hệ thống AOP có thể gắn hành vi, tùy khả năng công nghệ: thực thi/gọi phương thức, truy cập trường, constructor... |
| **Pointcut** | Điều kiện chọn những join point phù hợp |
| **Advice** | Mã được thực thi trước, sau hoặc bao quanh join point được chọn |
| **Weaving** | Quá trình đưa hành vi aspect vào chương trình, có thể ở bước biên dịch, xử lý bytecode, tải class hoặc khi chạy |
| **Instrumentation** | Việc bổ sung hành vi quan sát/biến đổi cho mã; không phải mọi instrumentation đều là cùng một công nghệ AOP |
| **Exclusion** | Chính sách bỏ qua class, method, artifact, join point hoặc lần gọi theo lý do xác định |

Giả sử một aspect ghi thời gian đã được thiết kế cho thao tác nghiệp vụ `calculatePrice()`:

```text
User request
    |
    +--> calculatePrice()            ← cần đo
              |
              +--> vendorMoneyLib()   ← có thể không cần đo từng hàm
              |
              +--> metricRecorder()   ← không nên tạo metric lồng vô hạn
                        |
                        +--> encoder()
                        +--> queue()
                        +--> exporter()
```

Nếu pointcut được viết theo kiểu “mọi phương thức” thì những thao tác `encoder()`, `queue()` hoặc `exporter()` có thể cũng bị chặn. Khi chính advice gọi `metricRecorder()`, nó kích hoạt lại advice, tạo một chu trình:

```text
Advice bắt đầu
  → ghi metric
    → metricRecorder() khớp pointcut
      → advice bắt đầu
        → ghi metric
          → ...
```

Kết cục có thể là `StackOverflowError`, stack tăng, CPU bão hòa hoặc số lượng event/log tăng ngoài kiểm soát. Trường hợp khác là thư viện ngoài liên tục sinh các method nhỏ, gây tăng số lần chạy advice mà không tạo giá trị quan sát tương xứng.

**Mục tiêu loại trừ:** chỉ áp dụng advice cho những join point thực sự thuộc hợp đồng quan sát hay hành vi mà aspect chịu trách nhiệm. Loại trừ phải có nguyên nhân cụ thể, không dựa vào suy đoán rằng “mọi mã sinh” hoặc “mọi thư viện” đều không quan trọng.

## 2. Phân biệt hai tầng phạm vi: weaving và thực thi advice

Đây là khác biệt quyết định cả hiệu năng lẫn tính đúng đắn.

### 2.1. Loại trừ trước hoặc trong weaving

Tùy công nghệ, có thể cấu hình để **không biến đổi** một nhóm class/module, hoặc định nghĩa pointcut sao cho không chọn join point bên trong chúng. Tác động thường là:

- Không gắn advice vào các join point bị loại trừ.
- Giảm số vị trí phải áp dụng hoặc lưu metadata cho advice; mức giảm startup, memory và runtime tùy cơ chế.
- Tránh chặn những API lõi như logger/exporter trước cả khi chúng hoạt động.

Với load-time weaving hoặc bytecode instrumentation, cần phân biệt **lọc class được đưa vào transformer** với **lọc join point** trên class đã được xử lý. Một class có thể chứa cả method nên áp dụng và method phải loại trừ. Chính sách loại trừ toàn class sẽ ảnh hưởng cả hai.

### 2.2. Điều kiện bỏ qua trong advice

Nếu join point đã được weave hoặc đã đi qua proxy/interceptor, advice có thể kiểm tra điều kiện:

```java
// Mã giả: phụ thuộc API AOP thực tế.
if (isInternalTelemetry(joinPoint) || isExcludedInvocation(joinPoint)) {
    return proceed();
}
return observeAndProceed(joinPoint);
```

Cách này có ích khi điều kiện chỉ được biết lúc chạy: loại request, mức log, cờ sampling, caller context hoặc trạng thái chống đệ quy. Nhưng lời gọi **vẫn có thể phải đi qua interception**, tạo chi phí dispatch, kiểm tra điều kiện và lấy metadata.

Không thể khẳng định guard runtime hoàn toàn thay thế được cấu hình weaving. Ngược lại, chỉ loại trừ lúc weaving cũng chưa giải quyết hết đệ quy nếu aspect gọi API quan sát có thể kích hoạt **một join point khác vẫn được bao phủ**.

### 2.3. Quy tắc lựa chọn

- **Loại trừ tĩnh ở mức class/package/module** khi vùng đó rõ ràng nằm ngoài phạm vi, nhiều lời gọi và cần tránh chi phí interception.
- **Loại trừ ở mức method/annotation** khi chỉ một số phương thức trong class cần bỏ qua.
- **Guard runtime** khi quyết định phụ thuộc dữ liệu của từng invocation hoặc cần lớp bảo vệ chống đệ quy.
- **Kết hợp các mức** khi vừa cần tiết kiệm overhead, vừa có đường gọi đặc biệt dễ sinh vòng lặp.

Cú pháp, tên matcher và thời điểm tính pointcut khác nhau giữa các công cụ. Trước khi chọn cách thực hiện, hãy xác định cơ chế thực sự đang dùng: compile-time weaving, post-compile transformation, load-time weaving hay runtime interception/proxy.

## 3. Các nhóm đối tượng thường cần xem xét loại trừ

### 3.1. Mã được sinh tự động (generated code)

Mã sinh có thể đến từ annotation processor, compiler, công cụ tạo proxy, chuyển đổi schema, bộ mã hóa dữ liệu, RPC stub, mapper hoặc công cụ tạo binding. Mã này có thể chứa:

- Method chuyển tiếp ngắn gọi rất nhiều lần.
- Bridge/synthetic method do compiler sinh ra.
- Các lớp proxy/adapter với tên thay đổi theo bản build hoặc lúc chạy.
- Getter/setter, mapper hoặc serializer nội bộ làm tăng mạnh số event.
- Code quản lý vòng đời/bất đồng bộ không phù hợp với advice vốn giả định lời gọi nghiệp vụ bình thường.

**Nhưng không loại trừ tất cả mã sinh theo mặc định.** Ví dụ RPC stub sinh tự động có thể là ranh giới quan trọng để đo độ trễ từ ứng dụng đến hệ thống ngoài; proxy sinh ra có thể là điểm interception duy nhất của một luồng gọi. Loại trừ sai tầng có thể xóa bỏ tín hiệu giám sát mà bạn thực sự cần.

Nên phân loại theo **vai trò**, không chỉ cách mã được tạo:

| Nhóm mã sinh | Câu hỏi trước khi loại trừ |
| --- | --- |
| DTO, mapper, serialization helper | Có cần từng method nội bộ xuất hiện trong log/trace không? |
| RPC/client stub | Có cần đo ranh giới gọi từ ứng dụng sang hệ thống khác không? |
| Proxy/adapter động | Pointcut muốn chặn proxy, target hay cả hai? Có làm ghi đúp không? |
| Bridge/synthetic method | Matcher có vô tình đếm cùng một thao tác hai lần không? |
| Generated business implementation | Đây có phải logic nghiệp vụ mà aspect phải bao phủ không? |

Các dấu hiệu hỗ trợ nhận diện gồm package output riêng, metadata build, annotation có retention phù hợp và các thuộc tính reflection như `Method.isSynthetic()` hay `Method.isBridge()`. Chúng không phải dấu hiệu toàn năng:

- Một class sinh tự động chưa chắc có annotation `@Generated` ở runtime.
- Có annotation mang tên “Generated” nhưng retention không cho phép đọc qua reflection.
- `isSynthetic()` hay `isBridge()` không bao quát mọi mã do generator tạo; một method sinh ra vẫn có thể bình thường theo bytecode.
- Tên class chứa ký tự `$` không đồng nghĩa “toàn bộ class là mã sinh cần bỏ qua”; inner class do người viết cũng có ký tự này.

Để lọc tin cậy, ưu tiên thông tin đã biết từ **build artifact, source set, generator ownership hoặc classloader/module** hơn các heuristic về tên.

### 3.2. Thư viện bên ngoài (third-party libraries)

Thư viện JSON, HTTP, database driver, cryptography, logging, RPC hoặc collection có thể chạy nhiều phương thức nội bộ. Chặn mọi lời gọi nội bộ có thể gây:

- Phình số lượng span/log/metric và làm mất tín hiệu nghiệp vụ.
- Chi phí runtime đáng kể trên những method rất ngắn.
- Đụng vào code có yêu cầu reentrancy, locking, classloading hoặc initialization nhạy cảm.
- Thay đổi hành vi do advice ném ngoại lệ, trì hoãn lời gọi hoặc dùng sai contract của thư viện.
- Ghi lại dữ liệu bí mật hoặc payload nhạy cảm mà thư viện xử lý.

Thư viện thường nên được quan sát ở **ranh giới tích hợp** mà ứng dụng gọi vào, thay vì mọi implementation detail bên trong. Tuy nhiên, nếu mục tiêu là profiling, kiểm tra bảo mật hoặc quan sát latency của một API thư viện cụ thể, có thể chọn **một phần API công khai** của nó với chính sách rõ ràng.

Vì một package có thể chứa mã nhiều chủ sở hữu, không nên coi “namespace giống ứng dụng” là bằng chứng tuyệt đối cho ownership. Hãy xét phối hợp classpath artifact, package, module, classloader và metadata triển khai.

### 3.3. Công cụ quan sát và chẩn đoán (observability tooling)

Đây là nhóm đặc biệt cần chú ý vì có nguy cơ **instrumentation tự quan sát chính nó**:

- Logger, formatter, appender, encoder và bộ đẩy log.
- Tracer, span processor, context propagator, trace exporter.
- Metric registry, meter/recorder, exporter và collector.
- Profiler, agent/helper instrumentation, event dispatcher.
- Health monitor hoặc watchdog gọi lại chính code được quan sát.

Nếu không loại trừ phù hợp, một advice ghi log có thể lại chặn logger; một advice tạo span có thể lại tạo span cho hành vi xuất span; một bộ đo timing lại đo chính thao tác ghi timing. Kết quả có thể là vòng lặp, nhân bội event hoặc nhiễu số đo.

Không có nghĩa là hệ thống quan sát không bao giờ được tự quan sát. Bạn vẫn có thể cần metric riêng để giám sát queue depth, export failure, dropped records hoặc thời gian flush. **Hãy dùng đường đo riêng được giới hạn và không gọi vòng vào cùng advice**, hoặc chủ động chọn ranh giới quan sát cụ thể.

## 4. Thiết kế allowlist và exclusion list

Một chính sách dễ kiểm soát thường bắt đầu bằng **đối tượng được phép**, rồi xác định ngoại lệ. Mục tiêu là tránh một pointcut toàn cục quá rộng phải bổ sung vô số quy tắc chữa cháy.

Mã giả:

```text
shouldAdvise(joinPoint):
    if !belongsToApprovedApplicationScope(joinPoint):
        return false

    if isInternalLoggingOrTelemetry(joinPoint):
        return false

    if isExcludedGeneratedHelper(joinPoint):
        return false

    if isExcludedExternalImplementation(joinPoint):
        return false

    if hasEffectiveNoAdviceMarker(joinPoint):
        return false

    return matchesBusinessJoinPointPolicy(joinPoint)
```

Đây là **thứ tự quyết định đề xuất** cho một chính sách quan sát: ở mỗi bước, có thể loại trừ mà không gọi logic nghiệp vụ. Cần tính cả các quy tắc ưu tiên cao hơn nếu cơ chế AOP của bạn có nhiều aspect; không được tự động áp dụng cùng một chính sách loại trừ cho các aspect giữ vai trò bảo mật hoặc đảm bảo tính nhất quán.

### 4.1. Phạm vi theo package hoặc module

Ví dụ tổ chức khái niệm:

```text
app.domain.*           ← nghiệp vụ, được xem xét chặn
app.usecase.*          ← nghiệp vụ, được xem xét chặn

app.generated.mapping.* ← helper sinh tự động, loại trừ
app.telemetry.*         ← logging/tracing/metrics, loại trừ
vendor.internal.*       ← implementation thư viện, loại trừ

app.integration.rpc.*   ← chỉ chọn method ở ranh giới cần đo
```

Các chuỗi `app.*` hay `vendor.*` là **đường dẫn minh họa**, không phải các tên package thực tế của mọi ứng dụng. Nếu dùng glob/regex, hãy kiểm tra ý nghĩa `*`, `..`, tên class lồng và boundary của dấu chấm trong bộ matcher đang sử dụng. Một biểu thức quá rộng có thể vô tình khớp package khác có tên tương tự.

Không nên dựa vào quy tắc “mọi thứ không thuộc một package là thư viện ngoài”. Ứng dụng nhiều module có thể chứa code sở hữu ở nhiều namespace khác nhau.

### 4.2. Loại trừ theo annotation

Một marker như `@SkipObservation` hoặc `@NoAspect` có thể là hợp đồng rõ ràng cho những vị trí không muốn quan sát. Khi dùng marker cần xác định:

- Annotation có `RUNTIME` retention không nếu matcher kiểm tra qua reflection?
- Được áp dụng trên class, method hay cả hai?
- Có kế thừa hoặc áp dụng cho method override/interface/bridge hay không? Điều này phụ thuộc cơ chế tìm metadata.
- Một method mang marker tại implementation nhưng advice nhìn thấy chữ ký interface thì resolver có tìm đúng implementation không?
- Có được phép dùng marker để bỏ qua một kiểm tra bảo mật bắt buộc không? Cần chính sách quyền hạn riêng.

Không biến annotation thành nút tắt tất cả cross-cutting concerns. Có thể định nghĩa marker chuyên trách như `@SkipDiagnosticLogging` để bỏ log chi tiết, trong khi enforcement cần thiết vẫn hoạt động.

### 4.3. Loại trừ theo loại join point và method metadata

Tùy công nghệ AOP, pointcut có thể nhắm một hoặc nhiều loại join point. Có thể loại trừ constructor, accessor, static initializer hoặc bridge/synthetic method nếu chúng không thuộc mục tiêu, nhưng cần kiểm tra cơ chế có thực sự cung cấp những join point ấy không. Runtime proxy thông thường không thể coi như bytecode weaving toàn diện.

Kiểm tra cả overload, override, interface default method, method ẩn/có giới hạn truy cập và lời gọi nội bộ trên cùng đối tượng. Một cơ chế proxy chỉ chặn những lời gọi đi qua proxy; một cơ chế weave bytecode có thể có phạm vi khác. Nếu bảo vệ bắt buộc không được kích hoạt ở một lời gọi, đó có thể là **coverage gap do interception mechanism**, không phải do quy tắc exclusion.

## 5. Thứ tự ưu tiên của nhiều aspect và tránh advice chồng chéo

Ngay cả khi mỗi pointcut được viết đúng, nhiều aspect có thể cùng khớp một join point:

```text
Request
  → Advice tracing
    → Advice logging
      → Advice timing
        → Business method
```

Nếu logging ghi toàn bộ span, còn tracing cũng ghi span và timing tự phát metric tại cùng biên, dữ liệu có thể trùng và overhead nhân lên. Khi nhiều advice bao quanh nhau, **thứ tự bọc** quyết định cách đo duration, điều kiện nhìn thấy exception và vùng dữ liệu context có hiệu lực.

Để tránh chồng chéo:

1. Gán rõ nhiệm vụ cho từng aspect: ai tạo trace span, ai ghi business event, ai chỉ đo metric tổng hợp.
2. Chọn **một ranh giới được quan sát chuẩn** cho mỗi thao tác nếu cần sự kiện “một request”.
3. Xác định thứ tự advice theo khả năng công nghệ đang dùng; test bằng vết thực thi.
4. Loại trừ helper nội bộ của advice khác, nhưng không làm mất context cần truyền qua các tầng.
5. Đặt guard cho lời gọi lồng nhau nếu một event chỉ được ghi tại tầng ngoài cùng; phải khôi phục state sau khi thoát.

Cần tránh giải pháp “tắt mọi thứ trong công cụ quan sát” mà không đánh giá nhu cầu đo lỗi exporter, queue và backpressure. Các metric này thường có thể được phát qua cơ chế không tự đi vào cùng pointcut.

## 6. Ví dụ Java 17+: mô phỏng chính sách chỉ quan sát nghiệp vụ được chọn

Ví dụ sau dùng **JDK dynamic proxy** để minh họa logic chọn áp dụng advice. Proxy chặn lời gọi qua interface; nó không chứng minh việc loại trừ tại compile-time/load-time weaving. Dù vậy, cách đặt hợp đồng allowlist, exclusion, method marker và đếm số lần advice chạy có thể dùng để thảo luận thiết kế phạm vi trong các hình thức AOP khác.

Chính sách demo:

- Chỉ các class được đánh dấu là **application component** mới đủ điều kiện.
- Component được đánh dấu **generated helper**, **external implementation** hoặc **telemetry infrastructure** bị loại khỏi logging aspect, kể cả khi nằm trong nhóm application component.
- Một method được đánh dấu **skip observation** bị bỏ qua ngay cả khi class đủ điều kiện.
- Phần việc thật được thực thi y nguyên dù có hoặc không chạy advice.

Tạo tệp `AspectExclusionDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public class AspectExclusionDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface ApplicationComponent {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface GeneratedHelper {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface ExternalImplementation {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE)
    @interface TelemetryInfrastructure {}

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface SkipObservation {}

    interface UseCase {
        String execute(String value);
        String health();
    }

    @ApplicationComponent
    static final class BusinessUseCase implements UseCase {
        @Override
        public String execute(String value) {
            return "business:" + value;
        }

        @Override
        @SkipObservation
        public String health() {
            return "up";
        }
    }

    @ApplicationComponent
    @GeneratedHelper
    static final class GeneratedMapper implements UseCase {
        @Override
        public String execute(String value) {
            return "generated:" + value;
        }

        @Override
        public String health() {
            return "up";
        }
    }

    @ApplicationComponent
    @ExternalImplementation
    static final class ExternalAdapter implements UseCase {
        @Override
        public String execute(String value) {
            return "external:" + value;
        }

        @Override
        public String health() {
            return "up";
        }
    }

    @ApplicationComponent
    @TelemetryInfrastructure
    static final class TelemetryWorker implements UseCase {
        @Override
        public String execute(String value) {
            return "telemetry:" + value;
        }

        @Override
        public String health() {
            return "up";
        }
    }

    private static boolean shouldIntercept(Class<?> type) {
        return type.isAnnotationPresent(ApplicationComponent.class)
                && !type.isAnnotationPresent(GeneratedHelper.class)
                && !type.isAnnotationPresent(ExternalImplementation.class)
                && !type.isAnnotationPresent(TelemetryInfrastructure.class);
    }

    private static final AtomicInteger ADVICE_CALLS = new AtomicInteger();

    static UseCase wrapIfSelected(UseCase target) {
        if (!shouldIntercept(target.getClass())) {
            return target;
        }

        InvocationHandler handler = (proxy, interfaceMethod, args) -> {
            Method implementationMethod = target.getClass().getMethod(
                    interfaceMethod.getName(), interfaceMethod.getParameterTypes());

            if (!implementationMethod.isAnnotationPresent(SkipObservation.class)) {
                ADVICE_CALLS.incrementAndGet();
                System.out.println("advice:" + implementationMethod.getName());
            }

            try {
                return implementationMethod.invoke(target, args);
            } catch (InvocationTargetException failure) {
                throw failure.getCause();
            }
        };

        return (UseCase) Proxy.newProxyInstance(
                UseCase.class.getClassLoader(),
                new Class<?>[] {UseCase.class},
                handler
        );
    }

    public static void main(String[] args) {
        UseCase business = wrapIfSelected(new BusinessUseCase());
        UseCase generated = wrapIfSelected(new GeneratedMapper());
        UseCase external = wrapIfSelected(new ExternalAdapter());
        UseCase telemetry = wrapIfSelected(new TelemetryWorker());

        System.out.println("result=" + business.execute("x"));
        System.out.println("health=" + business.health());
        System.out.println("result=" + generated.execute("x"));
        System.out.println("result=" + external.execute("x"));
        System.out.println("result=" + telemetry.execute("x"));
        System.out.println("adviceCalls=" + ADVICE_CALLS.get());
    }
}
```

Biên dịch/chạy với JDK 17 hoặc mới hơn:

```bash
javac AspectExclusionDemo.java
java AspectExclusionDemo
```

Đầu ra kỳ vọng:

```text
advice:execute
result=business:x
health=up
result=generated:x
result=external:x
result=telemetry:x
adviceCalls=1
```

**Giải thích:** `BusinessUseCase.execute()` đủ điều kiện nên kích hoạt advice một lần. `BusinessUseCase.health()` có marker `@SkipObservation` nên không được log. Ba component còn lại được trả về nguyên bản bởi `wrapIfSelected`, không đi qua proxy của ví dụ và không tạo advice event. Tất cả vẫn chạy logic nghiệp vụ.

**Giới hạn cần hiểu:** Marker `@ApplicationComponent` và các marker loại trừ là metadata **giả lập ownership trong ví dụ**, không có công cụ nào tự động gán chúng cho mã sinh hoặc thư viện ngoài. Trong thực tế, không thể yêu cầu mọi thư viện phụ thuộc đều gắn annotation của ứng dụng; thông tin build/classpath hoặc rule cấu hình sẽ phù hợp hơn. Với runtime proxy, method trên interface có thể khác method triển khai; ví dụ chủ động tìm method thực bằng reflection để kiểm tra marker. Nếu method có overload/bridge, hoặc code dùng nhiều interface và inheritance phức tạp, resolver thực tế phải được kiểm tra thêm.

Hơn nữa, ví dụ chỉ dùng điều kiện để **quyết định tạo proxy**. Trong một hệ thống weaving, muốn tiết kiệm chi phí biến đổi hoặc loại trừ đúng join point, điều kiện tương tự phải được chuyển sang điểm lọc do hệ thống đó hỗ trợ. Một lời gọi nội bộ không đi qua proxy có thể không được advice dù class đủ điều kiện; đây là thuộc tính của cơ chế proxy, không phải bằng chứng của quy tắc exclusion.

## 7. Exclusion tại compile-time, load-time và runtime: khác nhau ra sao?

| Thời điểm/cơ chế | Đơn vị lọc thường gặp | Điều cần xác minh |
| --- | --- | --- |
| Compile-time hoặc post-compile weaving | Class, member, join point theo cấu hình công nghệ | Artifact nào được weave, advice nào được áp dụng, debug symbols/metadata |
| Load-time weaving/Java agent | Class được nạp, classloader, tên class, bytecode/join point | Transformer có bỏ qua helper/tooling/agent class và vùng JVM nhạy cảm không |
| Runtime proxy/interceptor | Đối tượng được bao bọc, interface/method, predicate runtime | Lời gọi có đi qua proxy không; trường hợp self-invocation, overload và visibility |
| Guard bên trong advice | Invocation, context, loại thao tác, sampling | Có còn overhead interception không, guard có an toàn trước đệ quy không |

Không phải hệ thống nào cũng hỗ trợ mọi mức lọc, và “loại trừ package” không chắc loại trừ cả subpackage nếu cú pháp matcher không định nghĩa như vậy. Ngoài ra, class được tải bởi nhiều classloader có thể cùng tên nhưng là những `Class` khác nhau. Quy tắc dựa trên tên thuần có thể chưa đủ để xác định provenance hoặc identity.

### 7.1. Đặc biệt với load-time instrumentation

Một transformer chạy khi JVM định nghĩa class. Nếu nó biến đổi chính class của logger, agent helper hay bytecode library mà transformer đang sử dụng, có thể tạo vòng nạp class, tác động đến class initialization hoặc lỗi verifier. Vì thế cần **bộ lọc đủ sớm** trước khi phân tích/chỉnh sửa bytecode và bộ test khởi động với các cấu hình classloader cần hỗ trợ.

Lưu ý:

- Đánh giá những vùng JVM/module hoặc classloader không nên instrument bằng công cụ đang dùng.
- Loại trừ các helper classes dùng để thực hiện chính transformation.
- Kiểm tra tương thích bytecode/version, thứ tự transformer và việc nhiều công cụ instrument cùng một class.
- Đảm bảo rule vẫn đúng khi class sinh động có tên thay đổi và khi thư viện được nâng cấp.
- Không biến một bộ lọc dựa trên tiền tố chuỗi thiếu ranh giới thành điều kiện đánh trúng class có tên tương tự.

Ví dụ khái niệm: nếu muốn loại bỏ đúng package `com.example.telemetry` và các lớp con của nó, parser hoặc matcher cần được kiểm tra về ranh giới tên. So khớp `startsWith("com.example.telemetry")` một cách tùy tiện còn có thể bỏ nhầm `com.example.telemetryBusiness`.

### 7.2. Đặc biệt với runtime proxy

Proxy có thể khiến bạn quan sát **đối tượng bọc** thay vì implementation thật. Khi viết predicate, cần làm rõ muốn kiểm tra type của proxy, interface hay class đích. Nếu kiểm tra “tên proxy có chứa một hậu tố sinh tự động”, bạn có thể loại luôn lời gọi nghiệp vụ rất quan trọng. Nếu chặn cả proxy lẫn target bằng hai tầng khác nhau, một thao tác có thể tạo hai bản ghi.

Thứ tự lựa chọn pointcut và thứ tự wrapper phải có test bao gồm lời gọi trực tiếp, lời gọi qua interface, lời gọi từ method cùng class và lời gọi nested. Không suy luận khả năng chặn lời gọi chỉ từ việc thấy annotation tồn tại.

## 8. Guard chống đệ quy cho chính công cụ quan sát

Loại trừ tĩnh nên là phòng tuyến chính. Trong một số thiết kế, vẫn cần guard theo execution context vì có những đường gọi bất ngờ đi ngược vào advice. Một cách phổ biến là guard dùng `ThreadLocal` để đánh dấu luồng hiện tại đang thực thi phần instrumentation.

Mã giả:

```java
// Mã minh họa, không phải chương trình Java độc lập.
private static final ThreadLocal<Boolean> IN_TELEMETRY =
        ThreadLocal.withInitial(() -> false);

Object around() throws Throwable {
    if (IN_TELEMETRY.get()) {
        return proceed();
    }

    IN_TELEMETRY.set(true);
    try {
        return observeAndProceed();
    } finally {
        IN_TELEMETRY.remove();
    }
}
```

**Đây chỉ là bản đơn giản**, đúng cho trường hợp không có context cũ cần phục hồi. Nếu có advice lồng nhau hoặc scope trước đó có giá trị khác, cần lưu và phục hồi **giá trị trước** thay vì luôn `remove()`. Nếu dùng thread pool mà quên dọn trong `finally`, cờ có thể vô tình làm tắt quan sát ở các request sau.

Một phiên bản phác thảo có lưu trạng thái cũ:

```java
// Mã minh họa, không phải chương trình Java độc lập.
Boolean old = REENTRY_GUARD.get();
if (Boolean.TRUE.equals(old)) {
    return proceed();
}
REENTRY_GUARD.set(Boolean.TRUE);
try {
    return observeAndProceed();
} finally {
    if (old == null) REENTRY_GUARD.remove();
    else REENTRY_GUARD.set(old);
}
```

Điểm cần thận trọng:

1. **Một guard bao trùm toàn bộ `proceed()`** có thể làm mất việc quan sát những thao tác nghiệp vụ lồng nhau, dù chúng là mục tiêu hợp lệ. Muốn chỉ chặn đệ quy từ logger/exporter, nên áp guard quanh chính đoạn phát telemetry hoặc dùng trạng thái/pointcut chính xác hơn.
2. `ThreadLocal` thông thường không tự lan truyền context sang thread khác; lời gọi bất đồng bộ có thể kích hoạt lại instrumentation ở thread khác. Nếu truyền context qua task, phải thiết kế vòng đời và cleanup rõ ràng.
3. Guard chỉ là chính sách **bỏ qua logic advice tại runtime**; nếu pointcut vẫn khớp rộng, chi phí interception vẫn có thể tồn tại.
4. Nếu instrumentation ném ngoại lệ, cleanup phải chạy trên cả đường lỗi. Hành vi fail-open hay fail-closed của advice phụ thuộc hợp đồng, không được quyết định tùy tiện.

Một hệ thống quan sát nghiêm túc thường có **đường xuất dữ liệu độc lập** không đi lại vào cùng pointcut, kết hợp exclusions cho infrastructure và guard hẹp để phòng đường gọi bất ngờ.

## 9. Không loại trừ nhầm phần bắt buộc

Exclusion là công cụ giảm rủi ro/chi phí, nhưng cũng có thể tạo **lỗ hổng phạm vi**. Một số aspect có vai trò ảnh hưởng đến tính đúng đắn hoặc an toàn, chẳng hạn kiểm tra quyền truy cập, giới hạn tài nguyên, thực thi ràng buộc hoặc đảm bảo trạng thái nhất quán.

Giả sử hệ thống có:

```text
UseCase nghiệp vụ
  → Adapter sinh tự động
    → API nhạy cảm
```

Nếu một kiểm tra bảo mật bắt buộc chỉ được gắn ở adapter mà lại loại trừ toàn bộ mã sinh, kiểm tra có thể bị bỏ qua. Ngược lại, nếu aspect logging tự động ghi mọi tham số tại adapter, thông tin nhạy cảm có thể bị phát tán. Hai mối quan tâm cần **chính sách riêng**, không gộp chung một biến “ignore all”.

Vì vậy:

- Định nghĩa mục tiêu của từng aspect và **đường bao phủ tối thiểu cần thiết**.
- Chỉ cho phép exclusion đối với các hành vi tùy chọn (ví dụ debug tracing) khi đó là chính sách đã được thiết kế.
- Với enforcement bắt buộc, xác định join point hoặc boundary tin cậy mà cơ chế interception đảm bảo đi qua.
- Viết kiểm thử âm tính (*không nên được advice*) và dương tính (*bắt buộc phải được advice*).
- Xem xét tác động của code generator, cấu hình build và thư viện được nâng cấp.

Không được sử dụng một marker dễ tùy ý gắn để bỏ qua một kiểm tra bắt buộc nếu không có ràng buộc rõ ai được phép đưa marker vào mã.

## 10. Kiểm thử exclusion: chứng minh cả hai phía

Chỉ nhìn log giảm sau khi thêm exclude là chưa đủ: có thể bạn đã loại luôn những thao tác cần quan sát. Kế hoạch kiểm thử nên phản ánh **phạm vi nghiệp vụ có chủ đích**, có ca chồng chéo và thay đổi code sinh.

| Kiểm thử | Kết quả cần xác nhận |
| --- | --- |
| Class thuộc application allowlist, không mang marker loại trừ | Advice chạy đúng số lần mong đợi |
| Class sinh tự động có helper nội bộ | Helper bị bỏ qua theo chính sách |
| Generated API quan trọng vẫn cần quan sát | Boundary được chọn vẫn có advice |
| Thư viện ngoài nhiều lời gọi nội bộ | Không phát event cho implementation detail không cần |
| Adapter gọi API thư viện đã được chọn | Event ở ranh giới vẫn được tạo |
| Logger/exporter được gọi từ advice | Không sinh recursion, stack/event tăng vô hạn |
| Method-level marker trong class hợp lệ | Chỉ method đó bị loại trừ |
| Annotation trên interface và implementation khác nhau | Quy tắc lookup thực tế khớp hợp đồng |
| Method overloaded, overridden, bridge/synthetic | Không bỏ sót hoặc ghi trùng ngoài ý muốn |
| Nhiều aspect trên cùng thao tác | Thứ tự và số bản ghi đúng theo thiết kế |
| Classloader khác hoặc class tái sinh tên mới | Chính sách ownership/provenance vẫn đúng |
| Lời gọi thành công, exception, retry, async | Không làm thay đổi kết quả, lỗi hoặc context |
| Upgrade generator, compiler, thư viện hay runtime | Snapshot phạm vi được đối chiếu và review |

### 10.1. Kiểm thử trước khi cấp quyền phát telemetry thật

Bạn có thể dùng advice test chỉ tăng bộ đếm hoặc ghi sự kiện trong buffer hữu hạn. Đừng để chính bộ đếm/buffer là mục tiêu của pointcut đang thử. Ghi lại danh sách join point được chọn và bị loại bỏ (nếu công cụ hỗ trợ) rồi so sánh với danh sách kỳ vọng.

Nên giữ một số ca mẫu: method nghiệp vụ, method mã sinh, method của thư viện, method telemetry, method annotated, method bridge/synthetic. Sau đó assert cả **đúng vị trí** và **số lần** advice chạy, không chỉ “có bất kỳ log nào”.

### 10.2. Kiểm tra hiệu năng

Với cùng workload, thử các cấu hình:

1. Không áp aspect.
2. Áp pointcut rộng có guard runtime.
3. Thu hẹp pointcut/weaving theo allowlist và exclusions.
4. Bật chính sách logging/tracing thực tế với sink/queue giống vận hành.

Theo dõi throughput, CPU, heap allocation, GC, startup, class load/transform count, kích thước bytecode nếu phù hợp, p50/p95/p99 latency, log/span throughput và dropped events. Đặc biệt đo tại luồng nhiều lời gọi helper, vì “mỗi call chỉ tốn một chút” vẫn có thể trở thành phần lớn overhead khi advice khớp quá rộng.

**Không tự giả định exclusion chắc chắn nhanh hơn**: mức chênh phụ thuộc chi phí matcher, trình biên dịch, JIT, cơ chế instrumentation, cách thiết lập sink và việc advice có thật sự chạy trước đó hay không. Đo trên môi trường và tải tương ứng.

## 11. Quy trình điều tra khi exclusion hoạt động sai

### Trường hợp A — Không loại trừ được mã sinh

Kiểm tra tuần tự:

1. Code sinh thuộc artifact/package/classloader nào khi chạy thật?
2. Quy tắc lọc áp ở transformer/class-level hay ở method-level?
3. Class đã bị weave trước khi rule được áp dụng hay không?
4. Annotation cần kiểm tra có tồn tại trong bytecode/runtime không?
5. Method đang bị bắt là bridge/synthetic/override hoặc proxy wrapper khác so với dự kiến?
6. Có một aspect khác vẫn chạy cùng loại join point?

Tránh vá nhanh bằng một pattern tên quá rộng vì có thể gây coverage gap.

### Trường hợp B — Có log/tracing lặp vô hạn

Tạo biểu đồ chuỗi gọi ngắn nhất từ stack trace hoặc tracing nội bộ (nếu có). Tìm đoạn `advice → logger/tracer/metric → advice`. Sau đó xác định chính xác join point mà infrastructure dùng để quay lại advice, thu hẹp pointcut hoặc loại trừ vùng infrastructure tương ứng. Trong lúc điều tra, hạn chế debug logging dày vì có thể khuếch đại vòng lặp.

### Trường hợp C — Mất log của nghiệp vụ

Kiểm tra xem có loại trừ nguyên class thay vì helper method không; proxy có phải đối tượng mang tên “generated” nhưng trỏ tới target nghiệp vụ không; metadata của annotation được đọc trên interface hay implementation; lời gọi có thật sự đi qua cơ chế interception không; điều kiện runtime có bị treo do guard/`ThreadLocal` không được dọn không.

### Trường hợp D — Chỉ hỏng khi deploy, không hỏng khi test

Khác biệt thường xuất hiện từ classloader, packaging, trình tự nạp class, runtime instrumentation agent, bước code generation hoặc cấu hình pointcut theo environment. Tái hiện bằng build artifact gần production; ghi nhận danh sách lớp đã transform và phiên bản thư viện, tránh lộ các thông tin không cần thiết.

### Trường hợp E — Log ít hơn nhưng CPU vẫn cao

Có thể runtime guard ngăn formatter nhưng việc intercept vẫn xảy ra; hoặc CPU nằm ở pointcut matcher, reflection/metadata và các advice khác. Profiling nên phân biệt thời gian chặn lời gọi, quyết định policy, thực thi advice và viết sink. Nếu phù hợp, chuyển exclusion sang tầng weaving/selection để tránh overhead trước khi advice chạy.

## 12. Quản lý chính sách exclusion theo thời gian

Các hệ thống lớn có nhiều generator, module và integration nên xem exclusion như một phần cấu hình kiến trúc có thể kiểm tra, không phải danh sách chuỗi khó giải thích.

Một bản ghi chính sách hữu ích gồm:

| Trường | Ví dụ ý nghĩa |
| --- | --- |
| **Target** | Package/class/module/artifact/method hoặc nhóm join point |
| **Aspect áp dụng** | Logging, timing, tracing, enforcement cụ thể |
| **Decision** | Include hoặc exclude |
| **Reason** | Tránh recursion, loại helper tần suất cao, dữ liệu nhạy cảm, v.v. |
| **Owner** | Nhóm chịu trách nhiệm điều chỉnh |
| **Evidence** | Benchmark, trace, lỗi đã tái hiện hoặc test coverage |
| **Review trigger** | Nâng cấp generator, thay classloader, thêm advice mới |

Không cần hệ thống cấu hình phức tạp nếu ứng dụng nhỏ. Nhưng dù dùng code hay cấu hình, rule nên dễ đọc, có test và có cách xem tập join point cuối cùng sau khi kết hợp include/exclude.

Một chính sách có thể bắt đầu như sau (mã giả):

```text
Policy: diagnostic-timing
  include:
    - application use-case boundaries
    - selected outbound integration boundaries
  exclude:
    - telemetry infrastructure
    - generated mapping helpers
    - external library internals
    - methods explicitly marked skip-diagnostic-timing
  runtime-guard:
    - suppress recursion from emission path
  validation:
    - business coverage cases
    - no recursive telemetry cases
    - throughput and p99 comparison
```

Đây là ví dụ thiết kế, **không phải cú pháp cấu hình cụ thể**. Khi sử dụng cần chuyển rule sang khả năng thực tế của từng công cụ AOP và bổ sung chi tiết tên lớp/phạm vi thuộc ứng dụng.

## 13. Checklist review trước khi triển khai

- [ ] Xác định chính xác mục đích của aspect và join point cần quan sát.
- [ ] Có allowlist rõ ràng, không mặc định chặn toàn bộ classpath.
- [ ] Exclusion dựa trên ownership, vai trò và lý do cụ thể.
- [ ] Mã sinh được phân biệt giữa helper nội bộ với boundary quan trọng.
- [ ] Thư viện ngoài được quan sát ở ranh giới cần thiết, không tự động chặn mọi implementation detail.
- [ ] Logger, tracer, metric exporter và helper instrumentation không gọi vòng lại cùng advice.
- [ ] Đã cân nhắc exclude ở weaving/class-selection thay cho chỉ guard runtime.
- [ ] Marker annotation có retention, phạm vi và cách kế thừa/override đúng.
- [ ] Proxy, self-invocation, classloader và bridge/synthetic method đã được test theo cơ chế thực tế.
- [ ] Exclusion cho logging/tracing không vô tình tắt aspect enforcement bắt buộc.
- [ ] Có test dương tính và âm tính cho danh sách join point.
- [ ] Benchmark đo cùng workload, gồm throughput, CPU, GC, p99 và số event/log.
- [ ] Các rule có lý do, owner và điều kiện cần review khi thay đổi build/dependencies.

## Kết luận

Trong AOP, **phạm vi áp dụng advice** quan trọng không kém logic advice. Mã sinh, thư viện ngoài và công cụ quan sát đều có thể cần loại trừ để tránh recursion, overhead và dữ liệu trùng; nhưng chính những thành phần đó đôi khi lại chứa ranh giới quan trọng cần được quan sát hoặc bảo vệ.

Cách làm bền vững là bắt đầu từ mục tiêu của từng aspect, chọn allowlist vừa đủ, loại trừ chính xác ở tầng mà công nghệ AOP hỗ trợ và dùng guard runtime cho các điều kiện thật sự động. Sau cùng phải xác minh cả hai vế: **những join point cần advice vẫn được xử lý**, và **những vùng bị loại trừ không còn gây tác dụng phụ hoặc overhead không cần thiết**.
