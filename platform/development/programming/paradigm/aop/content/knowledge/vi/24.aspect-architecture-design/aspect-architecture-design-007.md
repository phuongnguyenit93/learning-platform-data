# So sánh Aspect (AOP) với Decorator, Middleware, Interceptor và Instrumentation

## 1. Vì sao cần phân biệt?

Khi muốn bổ sung ghi log, đo thời gian, kiểm tra quyền, cache, retry hoặc theo dõi lỗi vào nhiều thành phần, lập trình viên thường gặp những tên gọi: **Aspect-Oriented Programming (AOP)**, **Decorator**, **Middleware**, **Interceptor** và **Instrumentation**. Chúng có thể cùng giải quyết một vấn đề xuyên suốt (*cross-cutting concern*), nhưng **không cùng cấp độ khái niệm, không luôn cùng phạm vi can thiệp và không bảo đảm cùng khả năng kiểm soát lời gọi**.

- **AOP** là cách tổ chức chương trình theo các *concern* cắt ngang nhiều điểm thực thi: định nghĩa *join point*, *pointcut*, *advice* và cách gắn chúng vào chương trình.
- **Decorator** là mẫu thiết kế bao một đối tượng sau một giao diện tương thích để thêm hành vi qua lời gọi vào wrapper.
- **Middleware** thường là một giai đoạn trong *pipeline* xử lý request, message hoặc một tác vụ, có thể gọi chặng kế tiếp và xử lý kết quả trên đường quay về.
- **Interceptor** là một cơ chế/hook chặn một loại hoạt động nhất định, có thể chạy trước/sau hoặc quyết định tiếp tục, tùy hợp đồng.
- **Instrumentation** là kỹ thuật chèn điểm quan sát hoặc điều khiển vào chương trình/runtime, có thể thông qua bytecode, compiler, agent, profiling hook hoặc mã đo thủ công.

Những phạm trù này **có thể chồng lấn**: một bộ máy AOP có thể triển khai advice bằng interceptor, proxy hoặc bytecode instrumentation; một decorator có thể chứa logic như một advice; middleware có thể là interceptor chuyên cho pipeline. Không nên xếp chúng thành những công nghệ hoàn toàn loại trừ nhau.

Bài học nhằm giúp chọn đúng công cụ dựa trên **điểm can thiệp**, **phạm vi bao phủ**, **cách cấu hình**, **ngữ nghĩa của proceed/next**, **khả năng short-circuit**, **chi phí vận hành** và **yêu cầu về tính đúng đắn**.

## 2. Trục so sánh quan trọng nhất: can thiệp ở đâu?

Một thiết kế cần trả lời trước: **Sự kiện nào tạo ra hook?** Không thể chọn chỉ dựa vào việc muốn “thêm log”.

| Trục | Câu hỏi thiết kế |
| --- | --- |
| **Đối tượng bị chặn** | Một method của đối tượng, một request qua pipeline, một API call, hay sự kiện JVM/runtime? |
| **Đường đi được bảo vệ/quan sát** | Có buộc tất cả đường gọi đi qua wrapper/hook không? |
| **Bắt đầu/kết thúc** | Quanh lời gọi đồng bộ, toàn request, từng message, hay tới lúc tác vụ bất đồng bộ hoàn tất? |
| **Khả năng quyết định luồng** | Chỉ quan sát, biến đổi dữ liệu, gọi lại, trì hoãn, hay có thể không chạy target? |
| **Khả năng chọn điểm** | Đăng ký thủ công, chọn route, pattern method, annotation, signature, hay chèn bytecode? |
| **Ngữ cảnh** | Tham số method, request headers, principal, transaction, trace context, thread state? |
| **Chi phí/độ phức tạp** | Wrapper thủ công, registry middleware, proxy, weaving, agent hoặc profiler? |
| **Tính minh bạch** | Caller và người đọc code có nhận ra logic bổ sung không? Khả năng debug/test ra sao? |

Cùng một hoạt động `charge(order)` có thể được nhìn qua middleware của request đầu vào, interceptor ở tầng transport client, decorator của `PaymentClient`, advice tại execution của `PaymentService.charge`, hoặc instrumentation quanh lệnh I/O. **Mỗi điểm phản ánh một phạm vi khác nhau**; không thể dùng dấu “request đã trả 200” để kết luận mọi việc ở worker nền đã hoàn tất.

## 3. AOP: mô hình concern → pointcut → advice

AOP giải quyết vấn đề một chính sách lặp trên nhiều nơi trong chương trình. Các khái niệm nền tảng:

- **Aspect:** đơn vị đóng gói concern xuyên suốt và các quy tắc áp dụng.
- **Join point:** vị trí trong thực thi có thể được bộ máy AOP hỗ trợ can thiệp, ví dụ call/execution của method. Bộ máy khác nhau hỗ trợ tập join point khác nhau.
- **Pointcut:** biểu thức chọn join point cần áp chính sách.
- **Advice:** logic chạy tại join point, chẳng hạn *before*, *after returning*, *after throwing*, *after/finally* hoặc *around* theo khả năng nền tảng.
- **Weaving:** quá trình gắn advice vào join point, có thể xảy ra khi biên dịch, tải lớp hoặc tại runtime. Một số hệ thống dùng proxy thay vì biến đổi bytecode.
- **Proceed:** lời gọi tiếp tục tới advice tiếp theo hoặc target trong *around advice*, theo hợp đồng của bộ máy.

Sơ đồ khái niệm:

~~~text
                  +-----------------------------+
Policy "audit" -->| Aspect: pointcut + advice   |
                  +--------------+--------------+
                                 |
                 +---------------+----------------+
                 |               |                |
          join point A      join point B     join point C
          method call       method exec      runtime event
                 |               |                |
             [audit]          [audit]           [audit]
~~~

Không phải mọi bộ máy AOP đều hỗ trợ cả ba loại ví dụ trong sơ đồ: **join point là tập điểm mà công cụ cụ thể cho phép**, chứ không tự động là “mọi thứ xảy ra trong chương trình”.

### Ưu điểm

AOP hữu ích khi một chính sách thực sự xuyên nhiều method/type, cần được chọn bằng pointcut, có thể quản lý nhất quán ở một nơi và thay đổi mà ít làm xáo trộn nghiệp vụ. Ví dụ: gắn measurement lên toàn bộ một tập operation, áp policy kiểm soát truy cập ở những boundary được quy định, hoặc thêm trace correlation.

### Chi phí

Logic có thể trở nên “ẩn” với người chỉ nhìn body phương thức. Pointcut quá rộng, thứ tự advice phức tạp, proxy không được sử dụng hoặc weaving chưa kích hoạt có thể khiến hành vi bất ngờ. AOP không tự bảo đảm rằng mọi method đều bị chặn hoặc transaction/caching/security thực sự đúng.

## 4. Decorator: một đối tượng bao một đối tượng khác

**Decorator** là mẫu thiết kế cấu trúc: một wrapper triển khai giao diện tương đương rồi ủy quyền cho đối tượng bên trong, thêm hành vi trước/sau lời gọi hoặc thay đổi cách trả kết quả.

~~~text
Caller --> LoggingDecorator --> CachingDecorator --> RealService
              |                     |
           ghi log               hit: trả ngay
                                 miss: gọi tiếp
~~~

Một decorator có thể thêm tracing, validation, giới hạn số lần gọi, caching hoặc biến đổi kết quả. Vì wrapper **nắm quyền gọi delegate**, nó cũng có thể không gọi delegate, gọi nhiều lần hoặc thay đổi exception nếu hợp đồng cho phép.

Điểm mạnh:

- Tường minh tại nơi tạo/lắp ráp object graph; dễ hiểu thứ tự các wrapper.
- Không cần bộ weaving hoặc runtime agent.
- Dễ viết unit test bằng fake delegate.
- Có thể dùng trong môi trường Java thuần, bất kể có framework AOP hay không.

Giới hạn:

- Mỗi wrapper thường phải triển khai/forward các method của giao diện; nhiều interface hoặc nhiều type có thể tạo boilerplate.
- Chỉ lời gọi đi qua wrapper được bảo vệ. Đoạn code giữ tham chiếu tới đối tượng gốc có thể bỏ qua decorator.
- Lời gọi nội bộ từ method của đối tượng gốc tới method khác trên cùng `this` không đi vòng qua wrapper bên ngoài.
- Nếu không tổ chức composition rõ ràng, wrapper order có thể thay đổi hành vi.
- Metadata hay join point nằm ngoài giao diện/đường delegate không tự được intercept.

**Điểm khác với AOP:** decorator là **cách bao đối tượng cụ thể**; AOP là **mô hình mô tả và áp chính sách trên tập join point**. Có thể dùng decorator để triển khai một aspect cho một interface, nhưng chỉ dùng vài decorator không mặc nhiên có ngôn ngữ pointcut hoặc weaving.

## 5. Middleware: phần tử trong pipeline xử lý

**Middleware** là một tầng trong chuỗi xử lý, thường được tổ chức kiểu:

~~~text
Request --> Auth --> Trace --> RateLimit --> Handler
                \      |         |         /
                 \----- Response <---------/
~~~

Một middleware thường nhận **context của pipeline**, thao tác request/message, sau đó gọi `next` hoặc không gọi tiếp. Nó có thể trả response lỗi sớm, thêm header, đo thời gian, xử lý exception hoặc gắn correlation ID.

Mẫu tổng quát:

~~~text
middleware(context, next):
    before(context)
    if rejected(context):
        return rejection
    result = next(context)
    after(context, result)
    return result
~~~

Đây là pseudocode. Cơ chế `next` không nhất thiết là một lời gọi đồng bộ: ở pipeline bất đồng bộ, `next` có thể trả future/promise hoặc dùng callback. Phải đọc hợp đồng của pipeline để biết “after” chạy khi return handle hay sau completion.

Middleware phù hợp khi concern chủ yếu sống ở **boundary của pipeline**: HTTP request/response, message ingestion, RPC call chain, queue processing, command pipeline. Nó thường thấy được headers, transport metadata, session/request context; nhưng không tự quan sát tất cả method Java mà handler gọi sâu bên trong.

**Giới hạn đường đi:** một scheduled job không đi qua pipeline HTTP thì middleware HTTP không chạy; một function gọi trực tiếp business service cũng có thể bỏ qua pipeline. Nếu một thao tác nhạy cảm phải luôn được bảo vệ, chỉ gắn authorization ở HTTP middleware là chưa đủ khi còn entry point khác.

Middleware có thể được cài như một chuỗi interceptor hoặc decorator của handler. Tên “middleware” nhấn mạnh **vai trò trong pipeline**, không bắt buộc một kỹ thuật bytecode cụ thể.

## 6. Interceptor: hợp đồng chặn một loại hoạt động

**Interceptor** là một tên rộng cho hook được mời chạy trước, quanh hoặc sau một hoạt động mà hệ thống quản lý: method invocation, request dispatch, database call, serialization, message send, v.v.

Một interceptor có thể:

- Nhận metadata của invocation và parameters.
- Ghi nhận trạng thái trước khi chạy.
- Quyết định có gọi `proceed()`/`next()` không nếu API hỗ trợ.
- Bọc kết quả, dịch exception hoặc thực hiện logic sau thực thi.
- Chuyển tiếp request hoặc từ chối nó.

Khái niệm này **không quy định sẵn pointcut, weaving, cách tìm tất cả call site hay phạm vi cần bảo vệ**. Một method interceptor triển khai trên dynamic proxy chỉ thấy lời gọi qua proxy. Một transport interceptor chỉ thấy request đi qua transport. Một interceptor ở compiler/runtime có thể thấy những điểm khác.

**Không phải interceptor nào cũng được quyền bỏ qua target.** Một callback chỉ đọc dữ liệu trước/sau sự kiện là observer; một quanh-invocation interceptor mới có thể short-circuit nếu API cho phép. “Interceptor” mô tả vị trí/hợp đồng hook, còn “aspect” nhấn mạnh concern và quy tắc chọn tập join point. Chúng thường phối hợp: AOP runtime phân giải pointcut rồi gọi một chuỗi method interceptors.

## 7. Instrumentation: thay đổi hoặc quan sát thực thi ở tầng kỹ thuật

**Instrumentation** là quá trình thêm mã quan sát/kiểm soát vào chương trình. Có hai dạng cần phân biệt:

1. **Instrumentation thủ công:** lập trình viên chèn log, counter, span hoặc timer tại các method/tác vụ cần theo dõi.
2. **Instrumentation tự động/động:** compiler plugin, bytecode transformer, Java agent, class-load hook, profiler hoặc tooling runtime thêm điểm quan sát vào các vùng có thể instrument.

Instrumentation có thể là **cơ chế để thực hiện AOP weaving**, nhưng cũng có thể phục vụ profiling/telemetry mà không có khái niệm aspect hay pointcut ở lớp ứng dụng. Ví dụ agent ghi lại số lần chạy method bằng bytecode instrumentation có thể hữu ích cho chẩn đoán; nó không tự là một transaction/security aspect.

### Java agent ở mức khái niệm

Trong Java, một agent có thể dùng `java.lang.instrument.Instrumentation`, với manifest thích hợp và điểm vào như `premain` hoặc `agentmain` theo chế độ cài đặt, để đăng ký `ClassFileTransformer` và biến đổi bytecode của lớp phù hợp. Việc biến đổi chính xác bị giới hạn bởi JVM/class format, class loader, module boundaries và khả năng retransformation/redefinition được hỗ trợ. **Không phải mọi phép đổi đều được phép với lớp đã load**, và không phải mọi agent có khả năng skip method hoặc sửa semantics tùy ý.

Dòng xử lý minh họa:

~~~text
JVM loads class
    |
    +--> transformer được đăng ký?
            |
            +--> chọn lớp/method có thể transform
                     |
                     +--> tạo bytecode đã instrument hợp lệ
                              |
                              +--> class được dùng để thực thi
~~~

Với lớp đã load, nếu công cụ và JVM hỗ trợ, có thể cần retransformation; chỉ đăng ký transformer sau lúc class đã được load không có nghĩa lớp ấy đương nhiên được thay đổi.

Rủi ro instrumentation:

- Bytecode hỏng hoặc không tương thích làm class không load được.
- Overhead CPU, memory allocation hoặc trace volume lớn.
- Thay đổi hành vi do thời điểm instrumentation/class loading.
- Context class loader, dynamic class generation, module access và version JVM.
- Khó debug vì logic không thấy trong source của method.
- Instrumentation sâu làm tăng bề mặt quan sát dữ liệu nhạy cảm; cần redaction và giới hạn quyền agent.

Instrumentation phù hợp khi cần bao phủ một tập method lớn mà khó sửa source hoặc cần quan sát sâu ở runtime. Nhưng nếu chỉ muốn thêm logic cho một interface do chính mình kiểm soát, decorator/interceptor đơn giản hơn thường dễ kiểm chứng.

## 8. Bảng so sánh tổng hợp

| Tiêu chí | AOP | Decorator | Middleware | Interceptor | Instrumentation |
| --- | --- | --- | --- | --- | --- |
| **Bản chất** | Mô hình tách cross-cutting concern bằng pointcut/advice | Mẫu bao đối tượng cùng giao diện | Thành phần pipeline | Hợp đồng hook quanh một hoạt động | Kỹ thuật chèn điểm quan sát/điều khiển |
| **Điểm áp dụng** | Join point do nền tảng hỗ trợ | Lời gọi qua wrapper | Chặng request/message/job pipeline | Điểm mà host phát hook | Vị trí source/bytecode/runtime được instrument |
| **Cách chọn phạm vi** | Pointcut, metadata, quy tắc | Lắp wrapper cụ thể | Đăng ký pipeline/route | Đăng ký hook/selector tùy host | Chọn lớp/method/event/bytecode |
| **Short-circuit** | Có nếu around advice/hệ thống hỗ trợ | Có khi wrapper quyết định không delegate | Có nếu pipeline cho phép không gọi next | Phụ thuộc interceptor contract | Phụ thuộc loại instrumentation/hook |
| **Self-invocation** | Proxy-based có thể bỏ qua; weaving tùy join point | Đường gọi nội bộ của delegate bỏ wrapper | Không liên quan trực tiếp method nội bộ | Tùy host/proxy | Tùy điểm instrument |
| **Lời gọi không qua boundary** | Không được chặn nếu ngoài pointcut/interception | Bỏ qua wrapper | Không đi qua pipeline | Host không kích hoạt hook | Ngoài vùng instrument |
| **Phụ thuộc runtime** | Proxy, weaving hoặc cơ chế khác | Chủ yếu composition object | Pipeline host | Interceptor host | Tooling/JVM/compiler/agent |
| **Quan sát sâu trong hàm** | Tùy join point mà bộ máy hỗ trợ | Không tự động | Không tự động | Tùy loại hook | Có thể nếu cơ chế hỗ trợ |
| **Độ rõ của luồng gọi** | Logic có thể ẩn bởi pointcut/weaving | Thứ tự wrapper tương đối tường minh | Chuỗi pipeline thường rõ | Tùy registry/hook | Có thể khó truy vết từ source |
| **Phù hợp** | Policy xuyên nhiều điểm | Mở rộng một object/interface | Xử lý đầu/cuối pipeline | Hook vào tầng có API | Tracing/profiling/weaving sâu |

Bảng mô tả **khuynh hướng phổ biến**, không phải giới hạn tuyệt đối. Chẳng hạn một middleware cho request có thể được viết như một decorator của handler; một aspect có thể được thực thi bằng một chuỗi interceptors; instrumentation có thể đóng vai trò weaving cho AOP.

## 9. Ví dụ Java 17: cùng chức năng log theo ba cơ chế

Ví dụ độc lập sau cho thấy rõ **decorator**, **method interceptor qua dynamic proxy** và **middleware pipeline**. Cả ba đều ghi log trước/sau, nhưng điểm điều khiển khác nhau.

Lưu toàn bộ mã dưới tên **`MechanismComparisonDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class MechanismComparisonDemo {
    interface PriceService {
        int quote(String sku, int base);
    }

    static final class PriceServiceImpl implements PriceService {
        @Override
        public int quote(String sku, int base) {
            System.out.println("[service] quote " + sku);
            return base + 3;
        }
    }

    static final class LoggingDecorator implements PriceService {
        private final PriceService delegate;

        LoggingDecorator(PriceService delegate) {
            this.delegate = delegate;
        }

        @Override
        public int quote(String sku, int base) {
            System.out.println("[decorator] before");
            int result = delegate.quote(sku, base);
            System.out.println("[decorator] after");
            return result;
        }
    }

    @FunctionalInterface
    interface MethodInterceptor {
        Object invoke(Invocation invocation) throws Throwable;
    }

    record Invocation(Object target, Method method, Object[] arguments) {
        Object proceed() throws Throwable {
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException ex) {
                throw ex.getCause();
            }
        }
    }

    static PriceService withInterceptor(
            PriceService target, MethodInterceptor interceptor) {
        return (PriceService) Proxy.newProxyInstance(
                PriceService.class.getClassLoader(),
                new Class<?>[]{ PriceService.class },
                (proxy, method, args) ->
                        interceptor.invoke(new Invocation(target, method, args)));
    }

    record Request(String path) {}

    record Response(int status, String body) {}

    @FunctionalInterface
    interface Handler {
        Response handle(Request request);
    }

    @FunctionalInterface
    interface Middleware {
        Handler wrap(Handler next);
    }

    public static void main(String[] args) {
        System.out.println("=== Decorator ===");
        PriceService decorated =
                new LoggingDecorator(new PriceServiceImpl());
        System.out.println("result=" + decorated.quote("A", 10));

        System.out.println("=== Interceptor ===");
        PriceService intercepted = withInterceptor(
                new PriceServiceImpl(),
                invocation -> {
                    System.out.println("[interceptor] before");
                    Object value = invocation.proceed();
                    System.out.println("[interceptor] after");
                    return value;
                });
        System.out.println("result=" + intercepted.quote("B", 20));

        System.out.println("=== Middleware ===");
        Handler terminal = request -> {
            System.out.println("[handler] " + request.path());
            return new Response(200, "ok");
        };
        Middleware logging = next -> request -> {
            System.out.println("[middleware] before");
            Response response = next.handle(request);
            System.out.println("[middleware] after");
            return response;
        };
        Handler pipeline = logging.wrap(terminal);
        Response response = pipeline.handle(new Request("/items"));
        System.out.println("status=" + response.status());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MechanismComparisonDemo.java
java MechanismComparisonDemo
~~~

Đầu ra chính xác:

~~~text
=== Decorator ===
[decorator] before
[service] quote A
[decorator] after
result=13
=== Interceptor ===
[interceptor] before
[service] quote B
[interceptor] after
result=23
=== Middleware ===
[middleware] before
[handler] /items
[middleware] after
status=200
~~~

**Phân tích từng phần:**

- `LoggingDecorator` tự triển khai `PriceService` rồi gọi `delegate.quote(...)`. Đây là **object composition**: caller nhận một đối tượng bọc cụ thể, không có pointcut tự động.
- `MethodInterceptor` là hợp đồng hook. Dynamic proxy giữ vai trò **cơ chế interception** cho method trên `PriceService` được gọi qua proxy; `Invocation.proceed()` gọi target bằng reflection và unwrap `InvocationTargetException`. Mã ví dụ không định nghĩa một pointcut đa lớp; nếu thêm bộ chọn method và nhiều advice, nó có thể là cơ sở của một AOP runtime nhỏ.
- `Middleware` nhận `Handler next`, trả một `Handler` mới và xử lý trước/sau `next.handle(...)`. Đây là **pipeline composition**: middleware thấy `Request/Response`, không tự thấy những method sâu bên trong service.
- Cả ba in “before/after” vì ba lời gọi đều **đồng bộ**, target return bình thường. Nếu target ném exception, dòng “after” như viết ở đây không chạy; cần `try/finally` cho cleanup hoặc `catch` cho failure logging tùy policy.
- `PriceServiceImpl` không có phương thức nào gọi method khác trên chính nó trong demo. Nếu có *self-invocation*, việc gọi qua decorator/proxy bên ngoài không tự áp hook vào đường gọi nội bộ.
- Ví dụ không dùng agent. Instrumentation bytecode thực sự cần build/manifest/hook và bảo đảm tương thích runtime riêng; dùng mã giả để “giả làm” agent sẽ dễ tạo cảm giác sai về mức bao phủ.

Từ góc nhìn AOP, một *around advice* có thể có hình dạng khá giống `MethodInterceptor`, nhưng AOP còn yêu cầu **quy tắc chọn join point** và cơ chế gắn advice vào các điểm được chọn. Vì vậy không nên nói dynamic proxy và AOP là hai lựa chọn hoàn toàn độc lập.

## 10. Có thể short-circuit ở đâu?

Mọi cơ chế cho phép bao quanh lời gọi đều **có thể** bỏ qua chặng kế tiếp nếu contract cho phép. Tuy nhiên, thời điểm và ý nghĩa khác nhau:

| Chỗ short-circuit | Ví dụ | Điều sẽ bị bỏ qua |
| --- | --- | --- |
| Decorator của service | Cache hit trả giá trị từ wrapper | Delegate và mọi logic bên trong nó |
| Around advice tại method | Policy deny hoặc cache hit không gọi proceed | Advice phía trong và target theo thứ tự nesting |
| Middleware ở pipeline | Thiếu token trả 401 sớm | Middleware phía trong và handler phía sau |
| Method interceptor | Từ chối invocation | Target method nếu hook kiểm soát proceed |
| Instrumented hook | Có thể từ chối/đổi return nếu hook cho phép | Phụ thuộc điểm chèn; không mặc nhiên được quyền skip |

Một profiler chỉ quan sát stack sample **không có cơ chế short-circuit method**. Một observer chạy sau sự kiện cũng không thể quay lại ngăn việc target đã xảy ra. Hãy đọc đúng contract của tool/hook, đừng suy khả năng từ nhãn “instrumentation” hay “interceptor”.

Với middleware trả response sớm, có thể bỏ qua luôn metrics/audit ở các tầng **phía trong**. Với aspect caching bao ngoài security advice, cache hit có thể bỏ qua authorization ở phía trong. Thứ tự phải được thiết kế theo quy định **chính sách nào bắt buộc chạy trên mọi lời gọi**.

## 11. Phân biệt “phạm vi lời gọi” và “phạm vi yêu cầu”

Middleware của một HTTP request thường quan sát đường request từ lúc vào pipeline đến lúc pipeline tạo response. Một method advice đo từ lúc một method được gọi tới lúc method return. Instrumentation của một lệnh I/O có thể đo đến lúc hệ điều hành trả trạng thái hoặc đến completion thực tế tùy API.

Ví dụ:

~~~text
HTTP middleware start
   +-- trace interceptor
       +-- service method advice
           +-- schedule background job
           +-- return CompletionStage
       +-- method advice returns
   +-- HTTP pipeline returns handle/response
background worker later completes
HTTP middleware completion? -> depends on its async contract
~~~

**Không đồng nhất các mốc.** Với method trả `CompletionStage<T>`, after-returning advice chạy khi có stage, không phải khi computation hoàn tất. Nếu middleware chỉ quan sát return của handler, nó có thể ghi “xử lý xong” quá sớm. Nếu middleware pipeline được thiết kế để đợi stage/terminal signal thì thời gian quan sát khác. Instrumentation đo method exit cũng không tự đo completion của task phát sinh ở luồng khác.

Cần đặt tên rõ:

- `method.return_latency`: đến khi method trả handle.
- `operation.completion_latency`: tới khi contract báo công việc xong.
- `request.pipeline_latency`: theo thời điểm pipeline/host xác nhận hoàn tất.
- `resource.operation_latency`: theo hợp đồng của thao tác tài nguyên được instrument.

Với publisher/lazy stream, việc trả publisher chưa chắc bắt đầu thực thi; subscription, onNext, onComplete/onError và cancellation là những mốc riêng. Không chọn bừa một hook trên method return rồi gọi đó là toàn bộ stream latency.

## 12. Chọn theo vị trí của concern

### 12.1. Cross-cutting concern trên nhiều phương thức

Nếu cần một policy nhất quán áp trên tập method độc lập, chẳng hạn đo latency của mọi command theo naming hoặc metadata, **AOP** với pointcut/advice thường phù hợp. Chú ý proxy/weaving coverage, method visibility, self-invocation và ordering.

Nếu chỉ một hoặc vài interface cần chức năng bổ sung, **decorator** có thể rõ ràng và dễ test hơn, đặc biệt khi object graph do ứng dụng tạo và kiểm soát.

### 12.2. Concern của giao thức hoặc pipeline

Nếu cần đọc header, chặn request không hợp lệ, gắn request ID, chuẩn hóa response hoặc xử lý error của route, **middleware** phù hợp vì nhận được context ở đúng tầng pipeline. Không để middleware giao thức thay thế các kiểm tra resource-level bắt buộc khi cùng nghiệp vụ còn có entry path khác.

Nếu host đã có **interceptor API** ổn định ở transport, ORM, serializer, method invocation, client API, hãy dùng đúng extension point thay vì thêm lớp instrumentation sâu hơn chỉ vì muốn “không sửa source”.

### 12.3. Quan sát hệ thống sâu hoặc thư viện không kiểm soát source

**Instrumentation** hữu ích để profiling, tracing call graph, đo allocation, chèn hooks vào thư viện hoặc áp policy quan sát runtime rộng. Nên đánh giá overhead, rủi ro tương thích, quyền agent, class loading và khả năng bảo trì. Không dùng bytecode transformation chỉ để thêm hai dòng log ở một interface nội bộ nếu decorator là đủ.

### 12.4. Chính sách bảo mật và giao dịch

Kiểm tra quyền hoặc transaction không chỉ là câu hỏi “có hook chưa?”. Một điểm enforcement có hiệu lực phải bao phủ **mọi đường tới hành động cần bảo vệ**, được thực thi trước side effect và có context đáng tin cậy. Chọn proxy AOP, decorator hay middleware đều có thể bị bypass nếu caller giữ raw target hoặc có đường gọi trực tiếp resource.

Một transaction advice cũng không tự tạo tính nguyên tử: còn cần transaction manager và tài nguyên hỗ trợ; một method return handle bất đồng bộ không chứng minh transaction của worker đã hoàn tất. Đặt enforcement/transaction ở nơi có hợp đồng và ownership phù hợp quan trọng hơn tên kỹ thuật.

## 13. Những giới hạn Java cần nhớ

### 13.1. Proxy, method visibility và self-invocation

Với **interface dynamic proxy**, chỉ các method gọi qua interface proxy được interceptor quan sát. Lời gọi trực tiếp implementation hoặc lời gọi nội bộ `this.method()` có thể bỏ qua proxy ngoài. Subclass proxy có giới hạn đối với method không thể override và những đường gọi không qua wrapper. Bytecode weaving tại execution join point có thể intercept trong trường hợp khác, nhưng chỉ nếu công cụ thật sự cấu hình đúng.

Không nên nói “AOP luôn bỏ qua self-invocation”: đó là giới hạn điển hình của **proxy-based interception**, không phải định nghĩa chung của AOP.

### 13.2. Exception và kiểu trả về

Decorator và middleware thường dùng lời gọi Java trực tiếp. Reflective interceptor có thể gặp `InvocationTargetException` và cần truyền đúng `cause` cho caller. Dynamic proxy có các quy tắc Java về checked exception: ném checked exception không khai báo qua một method interface có thể dẫn tới wrapper runtime. Các hook không được tự thay lỗi nghiệp vụ bằng giá trị thành công ngoài ý muốn.

Nếu short-circuit, giá trị phải tương thích return type và contract. Không được trả `null` cho primitive return, trả một object sai kiểu hoặc làm mất cancellation/exception semantics của stage.

### 13.3. Thread context và async

Logging/tracing/authorization context có thể được giữ trong `ThreadLocal` nhưng không tự lan qua executor hay callbacks. Decorator, middleware, interceptor, advice và instrumentation đều phải quan tâm propagation và cleanup. Hook chạy trong một thread chỉ chứng minh trạng thái trong scope đó; nếu worker tiếp tục ở thread khác, cần thiết kế context lifecycle phù hợp.

### 13.4. Thứ tự và nested interception

Có thể có nhiều decorator lồng nhau, nhiều middleware trong pipeline, nhiều interceptors trong registry và nhiều advice với pointcut trùng. Outer wrapper chạy trước trên đường đi vào, thường chạy sau trên đường đi ra, nhưng short-circuit và exception làm thay đổi đường đi. Phải vẽ chuỗi thực tế, thay vì chỉ nói “cùng có log trước/sau nên như nhau”.

## 14. Ví dụ phân tích một kiến trúc thực tế

Giả sử hệ thống nhận request để lấy báo cáo, dùng service nội bộ và gọi thư viện tạo PDF:

~~~text
Client
  |
  v
Request pipeline
  +-- Middleware: request ID
  +-- Middleware: authenticate
  +-- Middleware: rate limit
  |
  v
ReportHandler
  |
  v
ReportService facade
  +-- AOP advice: authorization + metrics
  +-- Decorator: caching of safe report summary
  |
  v
PDF rendering library
  +-- Instrumentation: measure allocation/CPU
  |
  v
Storage client interceptor
  +-- record retries / endpoint latency
~~~

Từng lớp có lý do riêng:

- Middleware gắn với request boundary, truy cập headers và danh tính ở đầu vào.
- Security advice ở service boundary vẫn cần vì service có thể còn được gọi từ batch/CLI/message consumer.
- Decorator cache thuộc interface cụ thể, có logic key/invalidation riêng và chỉ short-circuit nếu không bỏ security bắt buộc.
- Instrumentation đo phần thư viện không tiện sửa source; agent cần kiểm soát overhead.
- Client interceptor theo dõi outbound I/O, không đồng nhất một lần retry với toàn bộ use-case thành công.

**Phạm vi cùng tồn tại** phải được xem xét để tránh double-count metrics. Ví dụ request latency và method latency là hai chỉ số khác, có thể lồng nhau. Một trace có thể có span cho cả pipeline và service nhưng không được tạo correlation giả rằng mọi hoạt động ở worker nền đều kết thúc cùng lúc.

## 15. Mô hình quyết định lựa chọn

Hãy đánh giá theo thứ tự:

1. **Sự kiện cần can thiệp thực sự là gì?** Method call, object operation, inbound request, outbound RPC hay runtime event?
2. **Ai sở hữu đối tượng/pipeline?** Có thể tự tạo wrapper và kiểm soát mọi caller hay không?
3. **Phạm vi cần bao phủ rộng đến đâu?** Một interface, một nhóm method, toàn giao thức hay mọi thư viện?
4. **Có cần quyền kiểm soát proceed/next không?** Chỉ quan sát sau sự kiện khác với cho phép short-circuit/retry.
5. **Có thể xuất hiện lời gọi bypass?** Raw target, self-invocation, direct resource access, job background, reflection hoặc agent chưa instrument?
6. **Cần dữ liệu context gì?** Request headers, method args, identity/tenant, transaction, JVM state?
7. **Chính sách có đòi tính đúng đắn mạnh?** Authorization và transaction cần được bảo đảm ở enforcement boundary, không chỉ nhờ vị trí hook tiện lợi.
8. **Chi phí vận hành có tương xứng không?** Complexity của weaving/agent so với decorator hoặc middleware?
9. **Async lifecycle kết thúc ở đâu?** Return handle, completion stage, terminal event hay resource callback?
10. **Cách kiểm thử coverage là gì?** Có case âm tính chứng minh lời gọi không qua hook sẽ bị phát hiện/chặn đúng không?

### Một số quy tắc chọn nhanh

| Nhu cầu | Điểm khởi đầu phù hợp | Lý do |
| --- | --- | --- |
| Thêm logging cho một interface tự quản lý | Decorator | Dễ nhìn, rõ delegate, test đơn giản |
| Áp policy lặp trên nhiều method theo quy tắc | AOP | Pointcut/advice đóng gói concern |
| Chặn request thiếu token trước routing | Middleware của request pipeline | Có context/next ở đúng boundary |
| Theo dõi method do thư viện đã có interceptor API công bố | Interceptor của thư viện | Dùng đúng extension point |
| Profiling thư viện/JVM không thể sửa source | Instrumentation | Có thể quan sát tầng thấp hoặc diện rộng |
| Cache với quyền bỏ qua target tại join point | Around advice hoặc decorator | Cần điều khiển proceed/delegate |
| Quan sát outbound client retries | Client interceptor | Gắn với mỗi attempt hoặc logical call theo host |
| Authorization của thao tác nhạy cảm từ nhiều entry point | Enforcement ở service/resource với coverage kiểm chứng | Tránh chỉ bảo vệ một đường request |

Không có câu trả lời tuyệt đối rằng AOP “mạnh hơn” decorator hay instrumentation “tốt hơn” middleware. Các cơ chế khác nhau về **boundary** và **hợp đồng**, không tạo một thang bậc tuyến tính.

## 16. Sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “AOP = dynamic proxy” | AOP là mô hình; proxy chỉ là một cách triển khai | Xác định join points, pointcuts và cơ chế áp |
| “Interceptor luôn là AOP” | Nhiều hook chỉ ở một API/pipeline | Interceptor có thể là thành phần của AOP, không bắt buộc |
| “Middleware chỉ là logging decorator” | Middleware mang request/message context và pipeline semantics | Xem contract next, lifecycle, order |
| “Instrumentation chỉ là log thủ công” | Có thể dùng agent, compiler, bytecode hoặc runtime hooks | Phân biệt manual/automatic instrumentation |
| “Agent có thể chặn tất cả method” | Giới hạn class loader, module, bytecode, hook và JVM | Xác minh coverage và quyền hook |
| “AOP bảo vệ mọi lời gọi nội bộ” | Proxy có thể bỏ qua self-invocation | Kiểm tra kỹ thuật interception thật |
| “Thêm cache ngoài auth luôn an toàn” | Cache hit có thể không gọi auth phía trong | Thiết kế ordering và security boundary |
| “After advice luôn chạy khi task xong” | Method return có thể chỉ trả future | Tách method exit và async completion |
| “Đổi exception giúp thống nhất lỗi” | Có thể che cause/đổi hợp đồng | Giữ semantics lỗi và stack trace |
| “Có pointcut thì mọi nơi được instrument” | Pointcut có thể sai hoặc weaving chưa kích hoạt | Kiểm thử runtime coverage |
| “Cùng in before/after tức là hai kỹ thuật tương đương” | Phạm vi, context và khả năng bypass khác nhau | So sánh đường đi và contract thực tế |
| “Thêm nhiều hook càng an toàn” | Có thể duplicate logging, deadlock hoặc overhead | Kiến trúc enforcement và ownership rõ |

## 17. Checklist kiểm chứng thiết kế

- **Boundary:** đã xác định method, object, pipeline hay runtime event chưa?
- **Selection:** pointcut/registration chọn đúng các điểm cần áp chưa?
- **Execution:** đã chứng minh hook thực sự chạy trong đường gọi production chưa?
- **Bypass:** raw target, self-invocation, callback, CLI/job hoặc direct resource có đi vòng không?
- **Semantics:** `proceed`/`next` được gọi đúng số lần, đúng thời điểm, đúng exception/return contract không?
- **Ordering:** những kiểm tra bắt buộc có chạy cả khi cache/fallback trả sớm không?
- **Async:** metric và cleanup có bám đúng completion signal theo contract không?
- **State/context:** thread-safety, correlation ID, principal và transaction scope có đúng không?
- **Overhead:** latency, memory, class loading và số lượng sự kiện có được đo thực tế không?
- **Maintainability:** người bảo trì có tìm được nơi policy được gắn, thay đổi và kiểm thử không?
- **Safety:** nếu pointcut hoặc instrumentation không áp được, cơ chế bảo vệ quan trọng có fail closed hoặc có kiểm soát bổ sung không?
- **Verification:** có kiểm thử kết quả và đường đi, không chỉ assert rằng một dòng log xuất hiện không?

## 18. Kết luận

**AOP** là mô hình tổ chức logic xuyên suốt qua join point/pointcut/advice. **Decorator** là wrapper object. **Middleware** là một chặng trong pipeline. **Interceptor** là hợp đồng hook quanh một hoạt động. **Instrumentation** là kỹ thuật chèn hoặc thu thập tín hiệu thực thi, có thể được dùng để triển khai AOP.

Chúng có thể kết hợp: một AOP runtime dùng interceptors; một middleware có hình thức decorator của handler; instrumentation có thể thực hiện weaving; decorator có thể biểu diễn một concern. Điều quyết định lựa chọn không phải tên gọi mà là **hook có thực sự bao phủ đường gọi cần xử lý, có đủ quyền điều khiển luồng và có bảo toàn ngữ nghĩa nghiệp vụ hay không**.