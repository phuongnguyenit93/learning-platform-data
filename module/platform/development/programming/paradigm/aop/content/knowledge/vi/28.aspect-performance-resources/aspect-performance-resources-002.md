# Chi phí chuyển qua advice, proxy và chuỗi interceptor

Một lời gọi phương thức được áp dụng *aspect-oriented programming* (AOP) có thể phải đi qua một hoặc nhiều lớp trung gian trước khi chạy logic nghiệp vụ. Các lớp trung gian giúp thực hiện những mối quan tâm xuyên suốt như đo thời gian, kiểm soát truy cập, theo dõi lỗi hoặc giao dịch, nhưng chúng tiêu thụ CPU, bộ nhớ và đôi khi làm thay đổi đường tối ưu hóa của JVM. Bài này phân tích **chi phí của đường gọi**, cách xác định nguồn chi phí thực sự và cách tối ưu mà vẫn bảo toàn hành vi.

## 1. Phân biệt thành phần và phạm vi chi phí

- **Join point:** vị trí trong luồng thực thi có thể được áp dụng xử lý bổ sung; ví dụ một lần gọi hoặc thực thi phương thức, tùy mô hình AOP.
- **Pointcut:** điều kiện chọn join point cần áp dụng. Một số hệ thống xác định tập điểm khớp lúc dựng proxy/weaving, số khác còn phải kiểm tra điều kiện động ở từng lần gọi.
- **Advice:** hành vi thực hiện tại join point: trước lời gọi (*before*), sau khi thành công (*after returning*), khi lỗi (*after throwing*), luôn sau khi hoàn tất (*after/finally*), hoặc bao quanh và tự quyết định tiếp tục (*around*).
- **Proxy:** đối tượng đứng trước đối tượng đích, nhận lời gọi rồi điều phối xử lý. Đây là **một** cơ chế triển khai AOP, không phải điều kiện bắt buộc của mọi AOP.
- **Interceptor:** một mắt xích nhận ngữ cảnh lời gọi, thực hiện xử lý và thường chuyển quyền cho mắt xích tiếp theo. Một advice có thể được biểu diễn bằng interceptor; ánh xạ cụ thể tùy thư viện hoặc bộ máy AOP.
- **`proceed()`:** thao tác cho một advice/interceptor kiểu around tiếp tục chuỗi hoặc đến thao tác đích. Nó không có nghĩa luôn “chạy đúng một lần”: một advice có thể bỏ qua, gọi lại nhiều lần hoặc thay đổi kết quả nếu hợp đồng cho phép.

Cần tách **chi phí cơ chế** (đi qua proxy, kiểm tra điều kiện, tạo ngữ cảnh, gọi interceptor, gọi đích) khỏi **chi phí chính nội dung advice** (ghi log, truy vấn dữ liệu, gọi dịch vụ, khóa, mã hóa...). Một advice ghi log đồng bộ có thể tốn hơn rất nhiều so với vài bước chuyển tiếp đơn giản; vì vậy không được quy mọi độ trễ cho proxy.

## 2. Đường gọi trực tiếp và đường gọi có AOP

### 2.1. Lời gọi trực tiếp

```text
Caller ────────> phương thức đích ────────> kết quả / ngoại lệ
```

Ở đường trực tiếp, JVM có cơ hội tối ưu các lệnh gọi dựa vào kiểu thực tế, tính ổn định của call site, việc khử đa hình và *inlining*. “Trực tiếp” không có nghĩa bằng 0 ns: vẫn có chi phí thực thi chương trình và logic nghiệp vụ, thậm chí lời gọi có thể được JVM inline hoàn toàn.

### 2.2. Lời gọi qua proxy và chuỗi interceptor

```text
Caller
  │
  ▼
Proxy / dispatch
  │ chuẩn bị Method, đối số hoặc Invocation context (nếu cần)
  ▼
Interceptor 1: trước ──────────────────────────────┐
  │ proceed()                                      │
  ▼                                                │
Interceptor 2: trước ──────────────────────┐       │
  │ proceed()                             │       │
  ▼                                       │       │
Gọi phương thức đích ──> trả về / ném lỗi │       │
  ▲                                       │       │
  └─ Interceptor 2: sau / xử lý lỗi <─────┘       │
             └─ Interceptor 1: sau / xử lý lỗi <───┘
  │
  ▼
Caller nhận kết quả / ngoại lệ
```

Mỗi interceptor kiểu around thường có pha vào và pha thoát. Khi chuỗi có `n` mắt xích và mỗi mắt xích chỉ gọi `proceed()` một lần, có khoảng `n` lần chuyển tiếp theo chiều vào và `n` lượt quay về; chi phí tạo bởi chuỗi thường tăng theo số mắt xích, nhưng **thời gian thực tế không nhất thiết tăng tuyến tính** do tối ưu JIT, nhánh điều kiện, cache, allocation và công việc riêng từng mắt xích.

Nếu mã được *weave* vào class ở thời điểm biên dịch hoặc nạp lớp, các đoạn advice có thể chạy ngay trong thân phương thức mà không tồn tại một đối tượng proxy riêng. Khi đó điểm phát sinh chi phí và khả năng inline khác sơ đồ trên. Cần xác định cơ chế thực sự được dùng trước khi lập luận về hiệu năng.

## 3. Chi phí nằm ở những bước nào?

| Bước | Chi phí có thể phát sinh mỗi lần gọi | Khi nào đáng chú ý? |
|---|---|---|
| Vào proxy và điều phối | Thêm lần gọi gián tiếp, tra cứu tuyến điều phối, kiểm tra loại phương thức | Phương thức đích cực ngắn, gọi với tần suất cao |
| Kiểm tra pointcut/điều kiện | Kiểm tra kiểu, tên, annotation, đối số hoặc ngữ cảnh | Điều kiện động phải tính lại mỗi lượt; tra cứu metadata không được cache |
| Chuẩn bị đối số | Tạo `Object[]`, boxing kiểu nguyên thủy, ép kiểu và unboxing | Gọi proxy động dùng đối số nguyên thủy trong vòng lặp nóng |
| Tạo ngữ cảnh lời gọi | Cấp phát object mang target, method, arguments, chain, chỉ số hiện tại | Tốc độ lời gọi cao; áp lực young generation/GC |
| Từng interceptor | Thêm call frame/dispatch, đọc trạng thái, chạy before/after, gọi `proceed()` | Nhiều interceptor hoặc interceptor có logic phức tạp |
| Đến phương thức đích | Gọi trực tiếp, reflection, method handle hoặc mã đã weave; mức inline khác nhau | Reflection/dispatch động trên hot path |
| Kết quả và ngoại lệ | Boxing/ép kiểu, `try/finally`, bắt/gói/mở ngoại lệ nếu có | Lỗi thường xuyên, advice xử lý/biến đổi ngoại lệ |
| Dữ liệu phụ của advice | Thread-local, đồng bộ hóa, counter, string, stack trace, I/O | Logging/tracing chi tiết, lock contention, ghi đồng bộ |

**Chi phí thiết lập và chi phí mỗi lần gọi là hai thứ khác nhau.** Sinh class proxy, phân tích metadata, xác định pointcut và dựng chuỗi thường là việc lúc khởi tạo hoặc liên kết. Chúng ảnh hưởng thời gian startup/bộ nhớ thường trú. Ngược lại, kiểm tra điều kiện động, tạo invocation context và logic advice có thể lặp lại ở mọi lần gọi. Không lấy thời gian khởi tạo proxy rồi mặc nhiên nhân lên cho mỗi lời gọi.

**Tài nguyên khác độ trễ.** Một đối tượng trung gian nhỏ có thể tạo thêm allocation dù tác động độ trễ trung bình thấp nhờ GC nhanh; khi tăng tải, allocation rate và GC pauses mới lộ rõ. Một advice lấy lock có thể làm tăng thời gian chờ và giảm thông lượng dù CPU của chính advice thấp.

## 4. Mô hình hóa overhead có điều kiện

Với cùng một phép tính nghiệp vụ và kết quả như nhau, có thể đặt:

```text
T_direct = thời gian của lời gọi trực tiếp có chạy nghiệp vụ
T_aop    = thời gian của đường qua cơ chế AOP có chạy cùng nghiệp vụ
ΔT       = T_aop - T_direct

ΔT ≈ T_dispatch + T_runtime_match + T_context
   + Σ(T_enter_i + T_advice_i + T_proceed_i + T_exit_i)
   + T_target_dispatch + T_cleanup
   - (phần chi phí gọi đích đã nằm trong T_direct)
```

Đây là **sơ đồ phân rã**, không phải đẳng thức đo được theo từng nanosecond. Các hạng mục tương tác với nhau; trình biên dịch JIT có thể inline, loại bỏ cấp phát hoặc thay đổi thứ tự tối ưu. Advice kiểu around có thể gọi đích 0, 1 hoặc nhiều lần; khi số lần thực thi nghiệp vụ thay đổi, việc trừ `T_aop - T_direct` **không còn là phép so sánh cùng lượng công việc**.

Một cách đánh giá tỷ lệ:

```text
overhead tương đối (%) = 100 × (T_aop - T_direct) / T_direct
```

Chỉ tính khi `T_direct > 0` và hai biến thể làm cùng công việc. Ví dụ **giả định để minh họa phép tính**, một lời gọi trực tiếp 100 ns và qua AOP 140 ns có overhead 40 ns, tương đương 40%. Nếu nghiệp vụ mất 10 ms, cùng mức phụ trội 40 ns chỉ chiếm khoảng 0,0004%. Các số trên **không phải số benchmark cho Java hoặc một thư viện AOP cụ thể**. Ngược lại, advice chứa I/O, lock hoặc chờ mạng có thể lớn hơn hẳn phần overhead cơ chế.

Cần theo dõi đồng thời *latency* (p50/p95/p99), *throughput*, CPU, allocation rate và GC. Khi tăng tải, contention và queueing khiến độ trễ cuối phân phối tăng mạnh dù trung bình tăng ít.

## 5. Độ sâu chuỗi và thứ tự advice làm thay đổi hiệu năng lẫn hành vi

Giả sử có ba advice:

```text
A (đo thời gian) -> B (kiểm tra điều kiện) -> C (ghi audit) -> nghiệp vụ
```

Nếu B quyết định chặn ngay và không gọi `proceed()`, C và nghiệp vụ đều không chạy. Không được kết luận “B nhanh hơn” bằng cách so với lời gọi cho phép đi hết chuỗi, vì hai đường có chức năng khác nhau. Nếu advice A đo cả chuỗi, thời gian của A bao gồm B, C và nghiệp vụ; cộng thời gian riêng A+B+C như các giá trị độc lập có thể **đếm trùng**.

Với dạng around:

```java
Object around(Invocation invocation) throws Throwable {
    long start = System.nanoTime();
    try {
        return invocation.proceed();
    } finally {
        long elapsed = System.nanoTime() - start;
        // Đưa elapsed vào bộ đo thích hợp; tránh I/O đồng bộ trên hot path.
    }
}
```

Đây là **mã minh họa phụ thuộc vào abstraction `Invocation` của bộ máy AOP**, không phải chương trình Java độc lập. `finally` đảm bảo phép đo diễn ra cả khi lời gọi đích ném ngoại lệ. `System.nanoTime()` phù hợp để tính khoảng thời gian trôi qua trong cùng tiến trình; phép đo cũng có overhead riêng, và cách công bố metrics có thể phát sinh contention hoặc allocation.

Phân biệt rõ:

- *Before*: chạy trước đích; nếu có lỗi hoặc chặn thì đích có thể không chạy.
- *After returning*: chỉ áp dụng trên đường hoàn thành bình thường.
- *After throwing*: áp dụng trên đường ngoại lệ.
- *After/finally*: áp dụng cả khi hoàn thành và khi ném lỗi.
- *Around*: kiểm soát việc gọi `proceed()`, kết quả và đường ngoại lệ; có khả năng thay đổi tần suất thực thi đích.

Một thao tác đơn giản ở *before* và một thao tác tương tự trong *around* không nhất thiết có cùng đường chạy, vì around thêm quyền điều khiển và có thể duy trì ngữ cảnh/trạng thái để tiếp tục chuỗi.

## 6. Ví dụ Java 17+: nhìn thấy proxy, chuỗi và lời gọi đích

Ví dụ dùng **JDK dynamic proxy** và interceptor tự xây dựng để nhìn rõ các bước. Đây chỉ là **một kiểu triển khai AOP qua proxy**, không đại diện cho hiệu năng của mọi hệ thống AOP.

Tạo file `AdvicePipelineDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class AdvicePipelineDemo {
    public interface PriceService {
        int discounted(int price, int discount);
    }

    static final class PriceServiceImpl implements PriceService {
        @Override
        public int discounted(int price, int discount) {
            return price - discount;
        }
    }

    @FunctionalInterface
    interface Interceptor {
        Object invoke(Invocation invocation) throws Throwable;
    }

    static final class Invocation {
        private final Object target;
        private final Method method;
        private final Object[] arguments;
        private final List<Interceptor> chain;
        private int nextIndex = 0;

        Invocation(Object target, Method method, Object[] arguments,
                   List<Interceptor> chain) {
            this.target = target;
            this.method = method;
            this.arguments = arguments;
            this.chain = chain;
        }

        Object proceed() throws Throwable {
            if (nextIndex < chain.size()) {
                return chain.get(nextIndex++).invoke(this);
            }
            try {
                return method.invoke(target, arguments);
            } catch (InvocationTargetException e) {
                throw e.getCause();
            }
        }
    }

    public static void main(String[] args) {
        PriceService direct = new PriceServiceImpl();
        AtomicInteger executedAdviceSteps = new AtomicInteger();

        List<Interceptor> chain = List.of(
            invocation -> {
                executedAdviceSteps.incrementAndGet(); // before
                return invocation.proceed();
            },
            invocation -> {
                Object result = invocation.proceed();
                executedAdviceSteps.incrementAndGet(); // after returning
                return result;
            }
        );

        PriceService decorated = (PriceService) Proxy.newProxyInstance(
            PriceService.class.getClassLoader(),
            new Class<?>[] { PriceService.class },
            (proxy, method, arguments) ->
                new Invocation(direct, method, arguments, chain).proceed()
        );

        System.out.println(direct.discounted(100, 15));
        System.out.println(decorated.discounted(100, 15));
        System.out.println(executedAdviceSteps.get());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac AdvicePipelineDemo.java
java AdvicePipelineDemo
```

Stdout chính xác:

```text
85
85
2
```

Lời gọi trực tiếp trả về 85 và không chạy advice. Lời gọi qua proxy cũng trả về 85, nhưng đi qua handler, tạo `Invocation`, vào interceptor thứ nhất, vào interceptor thứ hai, gọi đích bằng `Method.invoke` rồi đi ngược trở ra. Biến đếm bằng 2 vì mỗi interceptor tăng một lần.

Trong ví dụ này, mỗi lần gọi qua proxy *có thể* liên quan đến mảng đối số, boxing hai đối số `int` thành `Integer`, object `Invocation`, reflection và unboxing giá trị trả về. Chương trình được tạo để **quan sát luồng điều khiển**, không dùng số lần cấp phát suy ra từ mã nguồn làm kết quả đo runtime: JVM có thể loại bỏ hoặc biến đổi một số allocation khi tối ưu. Sử dụng `AtomicInteger` giúp đếm an toàn khi mở rộng sang đa luồng, nhưng bản thân phép tăng atomic cũng có chi phí; ví dụ không phải benchmark overhead tối thiểu.

Lưu ý kỹ thuật: `Invocation` giữ `nextIndex` theo **một lượt gọi**. Nếu tái sử dụng cùng một instance cho nhiều luồng/lượt gọi sẽ sai thứ tự và gây race. `InvocationTargetException` được mở để trả về nguyên nhân thực sự của lời gọi đích; nếu một ngoại lệ checked không khai báo bị thoát khỏi proxy động, cơ chế proxy Java có thể bọc nó thành `UndeclaredThrowableException`. Handler trong ví dụ cũng chưa minh họa xử lý đầy đủ các phương thức `equals`, `hashCode`, `toString` của proxy sản phẩm.

## 7. Cơ chế triển khai quyết định phần nào có chi phí

| Cách triển khai | Đường dispatch thường thấy | Đặc điểm cần đo |
|---|---|---|
| Proxy viết tay/decorator | Wrapper gọi target qua mã Java thông thường | Thêm lớp gọi và logic wrapper; JVM có thể inline nếu call site ổn định |
| Dynamic proxy cho interface | Lời gọi interface → proxy tạo lúc chạy → handler | Chuyển đối số/kết quả qua `Object`, handler dispatch; handler có thể chọn reflection hoặc gọi trực tiếp |
| Proxy sinh subclass bằng bytecode | Method override → interceptor → target hoặc phương thức gốc | Thêm dispatch/chain; hạn chế phụ thuộc final/private và khả năng override; mức inline phụ thuộc cách sinh mã |
| Weaving vào bytecode | Chèn xử lý vào join point đã chọn | Không nhất thiết có proxy/cấp phát invocation object; tăng kích thước mã, thay đổi khả năng inline và startup/class loading |
| Weaving thời gian nạp lớp | Biến đổi class khi nạp, rồi thực thi mã đã biến đổi | Có thể chuyển chi phí đáng kể về startup; runtime vẫn tốn công thực hiện advice |

Không đánh đồng “proxy” với “reflection”: một proxy có thể gọi đích trực tiếp, và một handler có thể dùng reflection; đó là hai quyết định khác nhau. Cũng không khẳng định weaving luôn nhanh hơn proxy hoặc ngược lại khi chưa có workload, JDK, trạng thái JIT và implementation cụ thể.

Các ràng buộc về khả năng bắt join point cũng khác nhau. Ví dụ cơ chế proxy thường chỉ thấy lời gọi thực sự đi **qua đối tượng proxy**; lời gọi nội bộ trên đối tượng đích có thể đi vòng qua interceptor. Weaving ở cấp bytecode có thể bắt những join point khác. Đây là khác biệt **tính đúng đắn** trước khi là khác biệt hiệu năng: không chọn cơ chế chỉ dựa trên vài nanosecond.

## 8. Đo chi phí bằng benchmark có kiểm soát

Không dùng một vòng `for` cộng với `System.nanoTime()` ở đầu/cuối rồi kết luận mỗi interceptor tốn bao nhiêu ns. JVM có warm-up, biên dịch JIT, escape analysis, dead-code elimination, GC và dao động CPU. Với Java, nên sử dụng **JMH (Java Microbenchmark Harness)** cho vi benchmark và thêm phép đo tải thực tế của ứng dụng.

Thiết kế ma trận phép đo với **cùng một hàm nghiệp vụ**:

| Trường hợp | Mục đích |
|---|---|
| Trực tiếp, không advice | Baseline nghiệp vụ |
| Proxy, chuỗi rỗng | Xấp xỉ overhead dispatch của cơ chế proxy |
| Proxy + 1 interceptor no-op | Phần tăng thêm khi có một mắt xích chuyển tiếp |
| Proxy + 2, 4, 8 interceptor no-op | Quan sát ảnh hưởng độ sâu chuỗi |
| Proxy + advice đo thời gian | Quan sát chi phí đo và ghi metric thực tế |
| Proxy + advice có I/O/lock | Đo hệ thống thật; tách khỏi vi benchmark overhead thuần |
| Weaving/giải pháp khác, cùng chức năng | So sánh triển khai sau khi đã xác nhận join point và ngữ nghĩa tương đương |

Quy trình khuyến nghị:

1. Dùng cùng JDK/JVM flags, máy, cấu hình CPU, input, kết quả và workload; thực hiện warm-up đủ để những đường nóng được JIT tối ưu.
2. Benchmark các biến thể trong các lượt fork riêng; dùng kết quả tính toán để JVM không loại bỏ công việc vô ích (ví dụ `Blackhole` trong JMH).
3. Dùng nhiều iteration và nhiều fork; báo cáo latency/operation kèm độ phân tán hoặc khoảng tin cậy thay vì một số đơn lẻ.
4. Đo allocation/op cùng với throughput/CPU; khi cần, profile bằng JFR/async-profiler hoặc công cụ tương đương để xác định frames, allocation và lock thực sự.
5. Với ứng dụng thực, chạy kiểm thử tải ở mức đồng thời đại diện, theo dõi p50/p95/p99, GC, tail latency và contention. So với hệ thống không bật advice **nhưng giữ cùng semantics** hoặc so với biến thể giảm chi phí hợp lệ.
6. Thử ít nhất một phương thức cực ngắn và một phương thức nghiệp vụ nặng hơn để thấy overhead tuyệt đối khác overhead tương đối. Với advice phụ thuộc I/O, dùng giả lập tải ổn định hoặc môi trường kiểm thử đủ kiểm soát.

**Cẩn thận khi suy luận:** benchmark chỉ gọi proxy một lần trong cùng call site có thể được JVM tối ưu khác thực tế đa hình; đo với logging bật có thể chủ yếu đo thiết bị lưu trữ. Trộn mọi loại lời gọi vào một số trung bình sẽ che các hot path quan trọng. Việc thêm advice đo thời gian tự tạo ra chi phí quan sát; nếu ghi metrics vào một counter chung gây tranh chấp, chi phí tăng theo số luồng.

## 9. Tối ưu theo nguyên nhân đã đo

**Giảm số join point thực sự cần can thiệp.** Giới hạn pointcut vào phương thức cần thiết, không tự động áp dụng advice lên mọi getter hoặc hàm cực ngắn. Nếu bộ máy cho phép, phân giải metadata/điều kiện tĩnh lúc khởi tạo và cache kết quả; chỉ kiểm tra điều kiện động khi bắt buộc.

**Giữ chuỗi gọn và đúng thứ tự.** Gộp logic thực sự liên quan khi có lợi và không làm mất khả năng bảo trì; loại bỏ advice trùng lặp. Đặt kiểm tra chặn sớm trước các bước tốn chi phí nếu ngữ nghĩa cho phép. Tuy nhiên, thay đổi thứ tự *audit*, kiểm tra quyền hoặc dọn dẹp tài nguyên có thể làm sai kết quả hoặc làm mất bằng chứng cần thiết.

**Giảm cấp phát trên hot path.** Tái sử dụng metadata bất biến như mô tả phương thức, tập interceptor và matcher; tránh tạo chuỗi log, stack trace, context lồng nhau hoặc `Object[]` mới nếu API triển khai có đường không cấp phát. Không chia sẻ invocation state chứa chỉ số `proceed()` giữa các lần gọi hoặc thread.

**Giảm chi phí advice trước khi thay cơ chế AOP.** Nếu profiler cho thấy chậm ở I/O, format log, truy cập ThreadLocal, đồng bộ hoặc xuất telemetry, tối ưu chính nơi đó: lọc log theo cấp trước khi format, dùng batch/buffer thích hợp, hạn chế lock toàn cục và tránh chép context không cần thiết. Khi chuyển sang bất đồng bộ phải đánh giá mất dữ liệu, thứ tự sự kiện và backpressure; đó là thay đổi hành vi, không đơn thuần tiết kiệm CPU.

**Đánh giá dispatch và khả năng JIT.** Nếu overhead thuần chiếm tỷ lệ lớn với hàm rất ngắn, cân nhắc giảm chiều sâu interceptor, dùng wrapper chuyên biệt, proxy sinh mã hoặc weaving khi phù hợp với join point và khả năng bảo trì. Đừng mặc định reflection luôn chậm nhất: `Method.invoke` được JVM tối ưu theo cơ chế phụ thuộc phiên bản, và MethodHandle cũng cần cấu hình call site thích hợp; đo trên JDK mục tiêu.

**Theo dõi startup và footprint.** Precompute/caching nhiều metadata giúp giảm chi phí mỗi lần gọi nhưng dùng thêm bộ nhớ lúc tồn tại; tạo proxy/weave nhiều class làm tăng chi phí lúc khởi tạo và có thể ảnh hưởng code cache/metaspace. Với tác vụ chạy ngắn, startup có thể quan trọng hơn throughput dài hạn.

## 10. Sai lầm thường gặp và cách tránh

1. **“Mỗi advice thêm đúng X ns.”** Không có hằng số phổ quát: chi phí phụ thuộc JVM/JIT, implementation, kiểu đối số, workload, chiều sâu chuỗi và tác vụ của advice.
2. **“Proxy luôn dùng reflection.”** Proxy là lớp điều phối, còn reflection chỉ là một cách gọi đích. Hãy đọc đường thực thi hoặc profile.
3. **“Không có allocation vì source code chỉ gọi method.”** Proxy và advice có thể tạo mảng đối số, boxing, closure hoặc invocation context; ngược lại một số allocation có thể được JIT khử. Chỉ profiler mới xác nhận.
4. **“Đổi thứ tự interceptor chỉ là tối ưu.”** Thứ tự ảnh hưởng kiểm tra quyền, tracing, giao dịch, xử lý lỗi và các cleanup callback. Hãy kiểm chứng ngữ nghĩa trước và sau thay đổi.
5. **“Thêm `try/finally` là tương đương after returning.”** `finally` chạy kể cả khi ném lỗi; after returning thì không. Có thể thay đổi side effect hoặc exception flow.
6. **“Đo thời gian quanh advice rồi cộng mọi đồng hồ lại.”** Các khoảng đo lồng nhau thường chồng lấp; tổng có thể đếm trùng toàn bộ thời gian nghiệp vụ.
7. **“Truy cập nội bộ cũng chắc chắn đi qua proxy.”** Nếu lời gọi không qua proxy, advice có thể không chạy. Kiểm thử các đường gọi được phép bắt.
8. **“Benchmark nhanh là xong.”** JIT, dead-code elimination, GC và độ đồng thời làm kết quả biến động. Luôn có baseline và số liệu thực tế.
9. **“Ghi log/trace nhiều mà chỉ tốn một lần gọi advice.”** Chuyển tiếp qua interceptor thường rẻ hơn đáng kể so với I/O, serialization, lock hoặc gửi dữ liệu ra ngoài; cần phân tích từng nguồn.
10. **“Bỏ interceptor no-op chắc chắn giảm CPU.”** Nếu JIT đã inline/khử bỏ đường đơn giản, lợi ích thực đo có thể nhỏ; mọi tối ưu cần thử lại trên hot path.

## 11. Tình huống suy luận thực tế

**Tình huống A — getter được gọi hàng triệu lần:** hàm đích gần như không làm gì, chuỗi interceptor dài tạo thêm context/boxing. Trước tiên kiểm tra advice nào thực sự cần ở join point này, thử giảm matcher động và độ sâu chuỗi, đo allocation/op và CPU. Lợi ích tương đối có thể rõ.

**Tình huống B — thao tác lưu dữ liệu mất vài chục mili giây:** cơ chế dispatch của một proxy thường không chi phối tổng thời gian. Nếu tracing chậm, kiểm tra nơi xuất dữ liệu, lock, format và I/O, không vội đổi proxy.

**Tình huống C — p99 tăng khi tải cao:** nhìn vào GC, allocation rate, khối đồng bộ và đường xuất log/metrics. Độ trễ đuôi lớn có thể do contention hoặc queueing trong advice, dù vi benchmark từng interceptor cho thấy mức trung bình thấp.

**Tình huống D — chuyển từ proxy sang weaving:** ngoài phép đo latency, cần xác nhận số join point bị bắt, thứ tự advice, self-invocation, exception semantics, startup và độ khó debug. Nếu phạm vi can thiệp đổi, số liệu chỉ có ý nghĩa khi mô tả rõ khác biệt.

## 12. Câu hỏi tự kiểm tra

1. **Vì sao hai lời gọi trả cùng kết quả mà benchmark chưa chắc tương đương?** Vì advice còn side effect, có thể chặn/gọi lại, thay đổi exception flow hoặc tranh chấp tài nguyên; phải so sánh cả ngữ nghĩa và khối lượng công việc.
2. **Thêm bốn interceptor no-op có bắt buộc thêm bốn lần cấp phát?** Không. Số cấp phát do implementation quyết định; nhiều interceptor có thể dùng chung một context và JIT còn có thể khử cấp phát.
3. **Mức overhead 40% có luôn đáng lo hơn 1%?** Không. Cần nhìn thời gian tuyệt đối, tần suất, tài nguyên và SLO của đường gọi; 40% của vài chục ns có thể kém quan trọng hơn 1% của thao tác nhiều giây.
4. **Vì sao cần đo proxy rỗng riêng với proxy có advice?** Để ước lượng phần điều phối cơ bản trước khi quy chi phí tăng thêm cho độ sâu chuỗi và nội dung advice.
5. **Khi nào không nên tối ưu bằng cách bỏ advice?** Khi advice đang thực thi yêu cầu chức năng hoặc an toàn như kiểm tra quyền, ghi audit bắt buộc, giải phóng tài nguyên, đảm bảo giao dịch hay xử lý ngoại lệ.

**Điểm cần nhớ:** Đánh giá overhead AOP theo **đường thực thi thật**, tách chi phí dispatch/chain khỏi chi phí nội dung advice, đo ở cả mức từng lời gọi và khi hệ thống chịu tải, rồi tối ưu dựa trên nguyên nhân đã được quan sát mà vẫn giữ nguyên hành vi cần thiết.