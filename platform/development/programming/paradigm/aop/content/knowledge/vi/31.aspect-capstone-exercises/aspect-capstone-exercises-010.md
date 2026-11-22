# Đo chi phí, kiểm thử hồi quy và giải thích khi nên bỏ AOP

Áp dụng *aspect-oriented programming* (AOP) giúp tập trung những mối quan tâm xuyên suốt (*cross-cutting concerns*) như tracing, audit, kiểm soát quyền hoặc đo hiệu năng. Nhưng AOP cũng thêm một tầng vận hành: xác định *join point*, chọn *pointcut*, chuyển tiếp qua proxy/interceptor hoặc chạy bytecode đã *weave*, đóng gói ngữ cảnh và thực hiện *advice*. Khi một hệ thống chậm, không đủ căn cứ để kết luận “AOP gây chậm” chỉ vì thấy khung proxy trong stack trace. Cũng không đủ căn cứ để bỏ AOP chỉ vì thử nghiệm nhỏ cho thấy lời gọi trực tiếp nhanh hơn.

**Mục tiêu của bài tập tổng hợp** là xây dựng được một lập luận có bằng chứng: đo đúng phần chi phí cần quan tâm, kiểm chứng không thay đổi kết quả và side effect, sau đó quyết định **giữ, thu hẹp, thay cách triển khai hay bỏ AOP** đối với một concern cụ thể. Quyết định phải xét cả hiệu năng, độ bao phủ chính sách, tính dễ hiểu, khả năng bảo trì và các đường chạy khác nhau.

Bài học tập trung vào AOP tổng quát, không gắn vào một bộ thư viện AOP cụ thể. Ví dụ chạy được với Java 17+ dùng JDK dynamic proxy để minh họa một cơ chế. Khi ứng dụng thực dùng weaving hoặc interceptor bytecode, cần thực hiện lại phép đo và kiểm thử trên cơ chế đó.

## 1. Hiểu “chi phí AOP” trước khi đo

Một lời gọi đi qua AOP thường có các nhóm công việc:

1. **Dispatch:** lời gọi đi qua proxy, handler hoặc điểm bytecode đã chèn.
2. **Matching:** kiểm tra pointcut tĩnh hoặc động; có hệ thống giải quyết một phần khi khởi tạo.
3. **Context:** chuẩn bị metadata, đối số, trạng thái chuỗi advice, thông tin correlation.
4. **Interception:** chạy lần lượt các advice, `proceed()` và các đoạn `finally`/xử lý ngoại lệ.
5. **Nội dung advice:** ghi log, lưu audit, tra cứu quyền, đo thời gian, gửi telemetry hoặc truy vấn dữ liệu.
6. **Chi phí gián tiếp:** allocation, GC, cache locality, tranh chấp lock, blocking I/O và khả năng JIT inline đường gọi.

Nhóm 1–4 thường được gọi là *overhead cơ chế*. Nhóm 5 là công việc chức năng thực sự của concern. Hai nhóm phải được tách khi diễn giải kết quả, bởi một lời gọi chậm sau khi bật audit có thể đang thực hiện I/O cần thiết, chứ không phải proxy chậm.

| Câu hỏi | Phép so sánh hợp lệ | Điều không thể kết luận |
|---|---|---|
| Proxy/interceptor thêm bao nhiêu chi phí? | Direct + công việc tương đương so với đường AOP + cùng công việc | Không so direct không audit với AOP có audit rồi gán chênh lệch cho proxy |
| Chức năng audit tốn bao nhiêu tổng chi phí? | Cùng nghiệp vụ, tắt/bật audit có chủ đích và đo cả side effect | Không gọi đây là “overhead thuần của AOP” |
| Pointcut quá rộng gây bao nhiêu lượt thừa? | Đếm join point ứng viên, số matcher chạy và số advice thực sự chạy | Không suy từ phần trăm được chọn thành phần trăm tiết kiệm CPU |
| Đổi cơ chế proxy sang weaving có lợi không? | Giữ tập join point, kết quả và các advice giống nhau | Không so hai đường chặn khác chức năng hoặc khác số lần chạy target |
| Bỏ AOP có làm giảm rủi ro không? | Test bao phủ chức năng + vận hành + hiệu năng của phương án thay thế | Không chỉ xét ns/op, bỏ qua audit/quyền/tracing bị mất |

### Chi phí tuyệt đối, tương đối và chi phí toàn hệ thống

Giả sử một benchmark đáng tin cho cùng lượng công việc cho ra:

```text
direct  = 80 ns/op
via AOP = 112 ns/op

chênh lệch tuyệt đối = 32 ns/op
chênh lệch tương đối = (112 - 80) / 80 × 100% = 40%
```

**Đây chỉ là số minh họa phép tính, không phải thông số hiệu năng của Java hay một công cụ AOP.** 40% có thể rất đáng chú ý với một hot path gọi hàng triệu lần/giây; nhưng sẽ không có ý nghĩa tương tự với nghiệp vụ dành nhiều mili giây cho I/O. Ngược lại, một advice ghi sự kiện đồng bộ có thể chi phối p99 latency dù số lần proxy dispatch rất nhỏ.

Khi lập kế hoạch, xem **tần suất gọi × chi phí mỗi lượt**, rồi kiểm tra thông lượng và tail latency dưới tải. Nếu advice chạy 500.000 lần/giây và tạo thêm 200 byte/lượt, riêng dữ liệu tạm giả định đã tương đương khoảng 100 MB cấp phát/giây (100.000.000 byte/s, xấp xỉ 95,37 MiB/s). Đây là tốc độ cấp phát, không phải kết luận heap tăng liên tục; phần lớn object tạm có thể được GC thu hồi.

## 2. Bài tập tình huống: giữ audit, tracing và quy tắc nghiệp vụ

Một hệ thống có chức năng tính tiền mua hàng. Khi mua thành công, phải ghi dấu nghiệp vụ; khi lỗi, không được tăng số lượt mua thành công. Một chính sách tracing/audit được bổ sung tại ranh giới `buy()`. Phương thức `quote()` chỉ xem giá, không cần audit giao dịch mua hàng.

Các bất biến dùng làm tiêu chí kiểm chứng:

- `quote(3)` trả về 75.
- `buy(2)` trả về 50; tăng bộ đếm giao dịch thành công đúng một lần.
- `buy(-1)` ném `IllegalArgumentException` với thông điệp `units must be positive`; không tăng bộ đếm thành công.
- Khi có advice, `buy(2)` có tracing vào/ra và audit success đúng một lần.
- Với `buy(-1)`, tracing vào/ra vẫn xuất hiện, ghi audit failure theo chính sách minh họa.
- `quote()` không phát tracing/audit giao dịch mua.
- Biến thể có AOP không được làm đổi kết quả nghiệp vụ so với biến thể trực tiếp.

Đối với hệ thống thật, yêu cầu “audit success” có thể đòi hỏi sự kiện chỉ được xác nhận sau commit bền vững. Bài tập này đơn giản hóa thành **thành công khi phương thức đích trả về bình thường**; không suy rộng điều đó sang giao dịch phân tán hoặc I/O bất đồng bộ.

### 2.1. Chương trình Java 17+ kiểm thử hồi quy trực tiếp và qua proxy

Tạo tệp `AopRegressionDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class AopRegressionDemo {
    public interface Pricing {
        int quote(int units);
        int buy(int units);
    }

    static final class PricingCore implements Pricing {
        private final List<String> events;
        private int successfulBuys;

        PricingCore(List<String> events) {
            this.events = events;
        }

        @Override
        public int quote(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException(
                    "units must be positive"
                );
            }
            return units * 25;
        }

        @Override
        public int buy(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException(
                    "units must be positive"
                );
            }
            int amount = units * 25;
            successfulBuys++;
            events.add("BUSINESS buy=" + amount);
            return amount;
        }

        int successfulBuys() {
            return successfulBuys;
        }
    }

    record Outcome(
        int quote,
        int paid,
        String failure,
        int successfulBuys
    ) {}

    static Object invokeTarget(
            Pricing target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException exception) {
            throw exception.getCause();
        }
    }

    static Pricing instrument(
            Pricing target, List<String> events) {
        return (Pricing) Proxy.newProxyInstance(
            Pricing.class.getClassLoader(),
            new Class<?>[] { Pricing.class },
            (proxy, method, args) -> {
                // Pointcut minh họa: chỉ method buy().
                if (!method.getName().equals("buy")) {
                    return invokeTarget(target, method, args);
                }

                events.add("TRACE enter");
                try {
                    Object result = invokeTarget(
                        target, method, args
                    );
                    events.add("AUDIT success");
                    return result;
                } catch (Throwable failure) {
                    events.add("AUDIT failure");
                    throw failure;
                } finally {
                    events.add("TRACE exit");
                }
            }
        );
    }

    static Outcome scenario(Pricing service, PricingCore core) {
        int quote = service.quote(3);
        int paid = service.buy(2);
        String error = "(none)";

        try {
            service.buy(-1);
            throw new AssertionError("expected exception");
        } catch (IllegalArgumentException exception) {
            error = exception.getMessage();
        }

        return new Outcome(
            quote, paid, error, core.successfulBuys()
        );
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<String> directEvents = new ArrayList<>();
        PricingCore directCore = new PricingCore(directEvents);
        Outcome direct = scenario(directCore, directCore);

        List<String> aopEvents = new ArrayList<>();
        PricingCore aopCore = new PricingCore(aopEvents);
        Pricing withAop = instrument(aopCore, aopEvents);
        Outcome intercepted = scenario(withAop, aopCore);

        check(direct.equals(intercepted),
              "business result changed");
        check(directEvents.equals(
                  List.of("BUSINESS buy=50")),
              "unexpected direct events");
        check(aopEvents.equals(List.of(
                  "TRACE enter",
                  "BUSINESS buy=50",
                  "AUDIT success",
                  "TRACE exit",
                  "TRACE enter",
                  "AUDIT failure",
                  "TRACE exit"
              )), "incorrect advice events");

        System.out.println(
            "Same business outcome: " + direct.equals(intercepted)
        );
        System.out.println("Quote: " + intercepted.quote());
        System.out.println("Buy: " + intercepted.paid());
        System.out.println("Failure: " + intercepted.failure());
        System.out.println(
            "Successful buys: " + intercepted.successfulBuys()
        );
        System.out.println(
            "Direct events: " + directEvents.size()
        );
        System.out.println("AOP events: " + aopEvents.size());
        System.out.println("Regression: PASS");
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac AopRegressionDemo.java
java AopRegressionDemo
```

Stdout khi chương trình vượt qua mọi assertion:

```text
Same business outcome: true
Quote: 75
Buy: 50
Failure: units must be positive
Successful buys: 1
Direct events: 1
AOP events: 7
Regression: PASS
```

**Giải thích:** Hai biến thể có cùng `quote`, `paid`, thông điệp lỗi và số lượt mua thành công. Số sự kiện khác nhau **có chủ đích**: direct core chỉ ghi một sự kiện nghiệp vụ; proxy ghi thêm tracing và audit trên hai lần gọi `buy`. Assertion kiểm tra chính xác thứ tự sự kiện, bao gồm cả đường thất bại.

Bài này dùng reflection trong handler. `Method.invoke` bọc ngoại lệ từ phương thức đích trong `InvocationTargetException`; hàm `invokeTarget` mở wrapper để caller nhận nguyên nhân thực. Handler bắt `Throwable` chỉ để ghi nhận failure trước khi ném lại; đây là mẫu minh họa về luồng advice, không có nghĩa mọi hệ thống audit đều nên coi mọi throwable là một “giao dịch thất bại” cùng ngữ nghĩa.

**Giới hạn của demo:**

- Handler chọn method bằng tên `buy`; đây là pointcut đủ đơn giản cho interface chỉ có hai method. Trong hệ thống lớn, cần xét chữ ký, overload và kiểu khai báo.
- `Object` methods như `equals`, `hashCode` và `toString` chưa được định nghĩa chính sách proxy production.
- `PricingCore` và `ArrayList` dùng một luồng; ví dụ không chứng minh thread safety.
- Unit test bảo vệ những ca cụ thể; chưa chứng minh các giá trị biên hoặc đường concurrency và transaction production.
- **Số lượng sự kiện không phải benchmark hiệu năng.** Không đọc “7 lớn hơn 1” thành hệ số chi phí CPU hoặc kết luận phải bỏ AOP.

## 3. Bài tập A: lập ma trận kiểm thử hồi quy

Hãy tự thiết kế ma trận trước khi đọc bảng gợi ý. Với mỗi trường hợp, ghi ít nhất: *đầu vào, kết quả/ngoại lệ, side effect nghiệp vụ, advice mong đợi, điểm không được advice can thiệp*.

| Kịch bản | Kết quả nghiệp vụ | Side effect domain | Advice mong đợi |
|---|---|---|---|
| `quote(3)` | 75 | Không tăng mua hàng | Không audit mua, không tracing mua |
| `buy(2)` | 50 | Thành công +1 | Enter, success, exit |
| `buy(-1)` | `IllegalArgumentException` | Không tăng mua hàng | Enter, failure, exit |
| `quote(-1)` | `IllegalArgumentException` | Không tăng mua hàng | Không tạo audit giao dịch mua |
| Gọi `PricingCore.buy(2)` trực tiếp | 50 | Thành công +1 | Proxy advice không chạy |
| Gọi `Pricing` qua proxy nhiều lần | Kết quả đúng từng lượt | Số thành công chính xác | Advice đúng mỗi invocation |
| Ném lỗi do chính advice | Phụ thuộc hợp đồng lỗi | Không được giả định rollback tự động | Test riêng precedence và cleanup |
| Lời gọi lồng nhau/retry | Tùy điểm chặn và số lần chạy target | Không đếm nhầm business operation | Xác minh advice hit và target calls riêng |

### Những assertion cần thiết

1. **Giữ kết quả:** cùng input, cùng kết quả hoặc loại lỗi/thông điệp theo contract.
2. **Giữ side effect:** cùng số lần thay đổi domain và dữ liệu cuối.
3. **Chứng minh pointcut:** advice chạy ở `buy` nhưng không ở `quote`.
4. **Chứng minh thứ tự:** `TRACE enter` trước target; success/failure sau outcome; `TRACE exit` luôn chạy.
5. **Chứng minh failure path:** khi target ném lỗi, audit success không được phát.
6. **Chứng minh đường thực:** test qua chính đối tượng đã instrument; gọi thẳng target không đại diện cho đường qua proxy.
7. **Kiểm tra concurrency:** nếu đổi bộ đếm thành shared state, cần thiết kế đồng bộ hoặc thu sự kiện cách ly.
8. **Kiểm tra self-invocation và class loading:** khả năng can thiệp khác nhau giữa proxy và weaving; không suy diễn từ một demo.

**Tại sao cần negative test?** Nếu pointcut rộng ra và audit nhầm `quote`, mọi test chỉ gọi `buy` vẫn qua. Negative test khẳng định tính chọn lọc, giảm cả lỗi ngữ nghĩa lẫn overhead do chặn thừa.

## 4. Kiểm thử hồi quy khi thay AOP bằng thiết kế khác

Một lỗi thường gặp: so sánh **bản có AOP và có auditing** với **bản gọi trực tiếp nhưng bỏ auditing**, rồi tuyên bố “bỏ AOP không gây hồi quy vì kết quả số học như nhau”. Thực tế yêu cầu audit đã mất.

Phải tách hai dạng so sánh:

### 4.1. So sánh chức năng tương đương

| Biến thể | Bảo toàn policy audit/tracing? | Dùng để so sánh |
|---|---|---|
| A — target trực tiếp, không advice | Không nếu policy bắt buộc | Baseline logic domain, không phải phương án production tương đương |
| B — qua AOP, có audit/tracing | Có, nếu pointcut bao phủ | Hành vi hiện tại |
| C — explicit decorator/wrapper có cùng audit/tracing | Có nếu mọi caller qua wrapper | So sánh kiến trúc và chi phí cơ chế |
| D — viết thủ công audit/tracing ở các call site | Có nếu không bỏ sót | Chi phí bảo trì và rủi ro scattering/tangling |
| E — AOP với pointcut thu hẹp | Có nếu không bỏ sót điểm bắt buộc | Đo lợi ích giảm can thiệp thừa |

Nếu audit là bắt buộc, **B so với C** là so sánh công bằng hơn để quyết định cơ chế triển khai: cùng logic nghiệp vụ và cùng chức năng quan sát được. So B với A cho thấy chi phí tổng để có chính sách, nhưng không thể quy toàn bộ chênh lệch cho proxy.

### 4.2. Những thứ cần khớp để gọi là tương đương

- Tập đối tượng và phương thức chịu chính sách.
- Thứ tự kiểm tra quyền, audit và thực thi target.
- Ngữ nghĩa thành công/thất bại, ngoại lệ và cleanup.
- Tần suất sự kiện: mỗi attempt, mỗi invocation hay mỗi business transaction.
- Nội dung sự kiện audit, dữ liệu nhạy cảm và nơi xuất dữ liệu.
- Hành vi khi fail: audit không ghi được thì nghiệp vụ có được phép thành công?
- Vòng đời đồng bộ/bất đồng bộ, timeout và propagation context.
- Khả năng chặn self-invocation, callback, retry và các đường gọi không qua proxy.

Nếu một phương án ghi audit sau mỗi lần `Method.invoke` còn phương án khác đợi commit bền vững, đó là **hai hợp đồng khác nhau**, không nên đặt cạnh nhau như một benchmark cùng điều kiện.

## 5. Đo overhead: kế hoạch benchmark đúng

Một chương trình tự lấy `System.nanoTime()` quanh vài nghìn lời gọi thường chưa phải microbenchmark đáng tin. JVM cần warm-up, JIT có thể inline hoặc loại công việc không được dùng; thời gian đo còn chịu ảnh hưởng GC, scheduler, CPU frequency và load từ hệ thống.

Trong Java, sử dụng **JMH (Java Microbenchmark Harness)** cho thí nghiệm vi mô và kết hợp **kiểm thử tải ứng dụng** cho câu hỏi về trải nghiệm thực tế. JMH hỗ trợ warm-up, measurement iterations, forks, tiêu thụ kết quả và plugin profiler. Không lấy output minh họa của bài tập làm số benchmark.

### 5.1. Những đường cần đo

| Biến thể | Mục đích đo | Điều phải giữ giống |
|---|---|---|
| Direct core | Baseline đường nghiệp vụ | Input, thuật toán, output |
| Proxy với handler chuyển tiếp không có advice | Ước lượng dispatch overhead | Cùng phương thức đích |
| Proxy với pointcut không khớp | Đo chi phí matching/skip | Cùng input và đường target |
| Proxy với một advice no-op | Ước lượng chi phí chain | Không thêm side effect chức năng |
| Proxy với nhiều advice no-op | Quan sát ảnh hưởng chiều sâu | Cùng số lần gọi target |
| AOP + audit/tracing thật | Tổng chi phí phương án có chức năng | Cùng định dạng và sink khi so với phương án thay thế |
| Explicit decorator + cùng audit/tracing | So sánh cơ chế tổ chức | Same policy và side effect |
| AOP + pointcut hẹp | Đo khoản tiết kiệm từ phạm vi chọn | Giữ mọi join point bắt buộc |
| Weaving tương đương, nếu triển khai thực hỗ trợ | So sánh lựa chọn instrument | Cùng phạm vi join point và advice |

Không cần đo mọi biến thể nếu quyết định đơn giản. Nhưng để tuyên bố “proxy là nút thắt”, ít nhất cần tách **proxy rỗng** khỏi **advice có công việc thật**.

### 5.2. Đơn vị đo và điều kiện đo

Theo dõi đồng thời:

- **Latency/op:** thời gian một lời gọi; phân biệt mean với percentile trên workload rộng.
- **Throughput:** số thao tác hoàn tất mỗi đơn vị thời gian ở độ đồng thời cụ thể.
- **CPU:** thời gian CPU cho xử lý ứng dụng và overhead.
- **Allocated bytes/op:** lượng cấp phát mỗi lượt, nếu profiler hỗ trợ.
- **Allocation rate và GC:** áp lực tạo object và thời gian collection.
- **p95/p99 dưới tải:** độ trễ đuôi, nơi log đồng bộ, lock hoặc queue thường bộc lộ.
- **Advice invocations và matcher evaluations:** số lần xử lý hoặc đánh giá điều kiện thật.
- **Correctness:** exception, events và outcome; số liệu “nhanh” không có giá trị nếu chức năng bị mất.

Quy trình đo:

1. Cố định JDK, runtime flags, commit, máy test và tập input; ghi rõ cấu hình.
2. Tạo baseline với dữ liệu tránh dead-code elimination; trong JMH, trả về kết quả hoặc tiêu thụ bằng `Blackhole`.
3. Chạy warm-up đủ, measurement iterations và nhiều fork phù hợp với độ nhiễu.
4. Tránh in console, I/O filesystem và logging thay đổi giữa các biến thể thuần cơ chế.
5. Khi đo chức năng audit/tracing, dùng **cùng sink** hoặc mô hình sink tương đương. Nếu I/O là trọng tâm, đo riêng dưới tải có backpressure.
6. Sử dụng JMH GC profiler (chẳng hạn `-prof gc` khi công cụ/phiên bản hỗ trợ) để quan sát cấp phát; dùng JFR, profiler CPU/allocation hoặc heap dump khi cần tìm nút thắt.
7. Chạy load test thực tế ở ít nhất vài mức concurrency đại diện; ghi p50/p95/p99, CPU, throughput và GC.
8. Kiểm tra các assertion hồi quy sau mọi thay đổi instrument, pointcut hay tối ưu context.
9. Lặp phép đo khi thay compiler/JDK, cấu hình JVM, cơ chế weaving hoặc phân phối tải.

### 5.3. Phác thảo JMH — phụ thuộc thư viện, không phải chương trình độc lập

Một benchmark có thể đặt state của mỗi luồng chứa đối tượng đã chuẩn bị và đo hai đường có **cùng tính toán**:

```java
// MINH HỌA cấu trúc JMH, cần JMH dependency và annotation processor.
// Các tên State/Benchmark/Scope/Setup/Level là annotation/API của JMH.
@State(Scope.Thread)
public class PricingBenchmark {
    Pricing direct;
    Pricing proxiedNoOp;

    @Setup(Level.Trial)
    public void setup() {
        direct = createDirectCalculator();
        proxiedNoOp = createProxyWithoutBusinessAdvice(direct);
    }

    @Benchmark
    public int directCall() {
        return direct.quote(3);
    }

    @Benchmark
    public int proxyCall() {
        return proxiedNoOp.quote(3);
    }
}
```

Đoạn trên là **pseudocode gần Java để thiết kế benchmark**: hai hàm `create...` chưa được định nghĩa, imports/dependencies không kèm theo, nên không thể chạy độc lập. Đừng gán một con số ns/op giả định cho nó. Benchmark thực tế phải bảo đảm `direct` và `proxiedNoOp` chạy cùng logic, không lẫn side effect hoặc class layout khác ngoài yếu tố đang đo.

Cũng không được mặc định benchmark đo một call site monomorphic liên tục sẽ giống production khi proxy có nhiều kiểu, nhiều target và concurrency khác nhau.

### 5.4. Ví dụ cách đọc dữ liệu giả định

| Biến thể giả định | Mean | Allocated bytes/op | Ý nghĩa sơ bộ |
|---|---:|---:|---|
| Direct | 60 ns | 0 B | Baseline nghiệp vụ nhỏ |
| Proxy no-op | 95 ns | 32 B | Có thể có chi phí dispatch/context |
| Proxy + 3 interceptor no-op | 125 ns | 48 B | Chuỗi dài hơn có chi phí khác |
| Proxy + audit dùng I/O | 25 µs | 400 B | I/O chi phối, không nên quy hết cho dispatch |
| Decorator + cùng I/O audit | 24,8 µs | 370 B | Chênh lệch nhỏ hơn rất nhiều so với tổng I/O |

**Toàn bộ số trong bảng đều do bài học đặt ra để minh họa, không phải kết quả đo từ JVM hay thư viện thật.** Từ bảng giả định không thể suy ra decorator luôn nhanh hơn hay AOP luôn chậm. Hãy xem độ phân tán và sai số của phép đo: chênh lệch 0,2 µs trong workload có I/O có thể nằm trong nhiễu hoặc biến thiên do sink.

## 6. Bài tập B: tính chi phí và chọn nơi tối ưu

Cho dữ liệu **giả định có chủ đích** của hai loại phương thức:

```text
read() hot path:
  2.000.000 calls/second
  20 ns overhead cơ chế mỗi call, không có advice hữu ích

checkout() critical path:
  1.000 calls/second
  100 µs audit + 20 ns overhead cơ chế mỗi call
```

**Câu hỏi:**

1. Chi phí CPU cộng dồn được mô hình hóa cho overhead cơ chế ở `read()` là bao nhiêu mỗi giây?
2. Nếu thu hẹp phạm vi để `read()` không đi qua interception nữa, tối đa khoản tiết kiệm theo mô hình là bao nhiêu?
3. Trong `checkout()`, tỷ lệ 20 ns so với 100 µs khoảng bao nhiêu?
4. Nếu audit là bắt buộc, có được xóa audit để tăng tốc không?
5. Nếu audit chậm vì sink đồng bộ, nên điều tra chi phí nào trước khi đổi loại proxy?

**Lời giải:**

- `2.000.000 × 20 ns = 40.000.000 ns`, tương đương **40 ms thời gian cộng dồn mỗi giây**, tức khoảng **0,04 CPU-second/second** trong mô hình giản lược. Kết quả này **không bằng** giảm 40 ms latency cho từng lời gọi hay một bảo đảm CPU thực tế.
- Nếu có thể đưa `read()` ra khỏi interception hoàn toàn và chi phí bỏ đi thực sự là 20 ns/lượt, đó là trần tiết kiệm theo mô hình. Nếu chỉ lọc advice nhưng vẫn đi qua proxy, chi phí dispatch có thể còn.
- `100 µs = 100.000 ns`; `20/100.000 = 0,0002`, tức **0,02%** so với riêng khoản audit 100 µs. Đây là so sánh các hạng mục giả định, không phải tỷ lệ tổng request.
- Không được bỏ audit bắt buộc. Có thể sửa policy hoặc cơ chế xuất audit nếu vẫn bảo toàn đầy đủ semantics, độ bền và chính sách lỗi.
- Trước hết đo thời gian chờ I/O, serialization, queue, contention, retry và độ trễ sink. Tối ưu vài nanosecond của proxy gần như không giải quyết nguồn chậm 100 µs trong ví dụ.

### Tại sao cùng một tối ưu có giá trị khác nhau?

Ở phương thức hot path rất nhỏ, chi phí dispatch/matching dù thấp tuyệt đối vẫn có thể đáng xét do tần suất cực lớn. Với một nghiệp vụ nặng, I/O hoặc giao dịch đắt có thể chi phối. Vì vậy **tối ưu phạm vi trước** khi micro-optimize là một lựa chọn có lý: loại những join point không cần can thiệp có thể giảm nhiều invocation hơn việc thay vài lệnh trong advice.

Tuy nhiên, không thu hẹp một pointcut đến mức bỏ qua quyền truy cập hoặc audit bắt buộc; performance improvement chỉ hợp lệ khi kiểm thử hồi quy chức năng vẫn đạt.

## 7. Khi nào nên giữ AOP?

AOP thường phù hợp hơn khi:

1. **Concern thực sự xuyên suốt.** Cùng chính sách phải chạy ở nhiều biên nghiệp vụ; viết tay tạo scattering/tangling đáng kể.
2. **Tập join point định nghĩa rõ và có thể kiểm chứng.** Có ma trận nơi phải chặn và không được chặn; đội dự án có thể duy trì nó.
3. **Thứ tự advice và xử lý lỗi có hợp đồng ổn định.** Cách xếp before/around/after/finally minh bạch và test được.
4. **Cơ chế instrument đáng tin trong triển khai.** Proxy/weaving được kích hoạt đúng trên mọi đường gọi cần thiết; không có điểm bypass không kiểm soát.
5. **Chi phí đo được phù hợp mục tiêu.** CPU, latency, memory, GC và throughput nằm trong ngân sách hiệu năng.
6. **Giảm chi phí bảo trì đáng kể.** Thay policy ở một nơi thay vì sửa hàng chục vị trí; người bảo trì vẫn hiểu đường chạy.
7. **Khả năng quan sát đủ tốt.** Có log/trace/breakpoint để theo dõi advice khi có lỗi và người phát triển biết cách debug.
8. **Không có yêu cầu đặc biệt xung đột.** Ví dụ một số native image/AOT, security boundary hoặc class loader động có thể đặt ràng buộc; cần kiểm tra implementation thực.

Không cần mọi điều kiện có mức độ như nhau. Một hệ thống nhỏ có thể chỉ cần vài concern xuyên suốt và AOP vẫn rõ ràng; một hệ thống lớn cũng có thể không phù hợp nếu tập join point khó chứng minh hoặc việc instrument phá vỡ môi trường triển khai.

## 8. Khi nào nên thu hẹp hoặc thay đổi AOP trước khi bỏ?

**A. Pointcut rộng bất hợp lý**

Nếu log/tracing được chèn vào mọi getter, helper và phép tính nhỏ, trước hết xác định những điểm có giá trị. Chọn chỉ các thao tác quan trọng hoặc sampling telemetry khi được phép, dùng điều kiện tĩnh sớm và hạn chế matcher động đắt.

**B. Chuỗi advice quá sâu**

Đo từng interceptor, kiểm tra logic trùng lặp, việc clone `Object[]`, tạo metadata, map, stack trace và stringify. Có thể đơn giản hóa chain hoặc dùng một context hợp lý, nhưng phải giữ đúng thứ tự policy, retry và cleanup.

**C. Chi phí chính nằm trong nội dung advice**

Nếu profiler thấy phần lớn thời gian ở I/O, serialization, lock hoặc xuất metric, sửa đường đó có khả năng tác động hơn đổi từ reflection sang method handle. Không vội thay cơ chế intercept khi bottleneck nằm ở sink.

**D. Chỉ một số loại đối tượng cần instrument**

Một vài cơ chế proxy bọc toàn bộ interface; phương thức không khớp pointcut vẫn đi vào handler. Nếu công cụ cho phép, giảm tập đối tượng được bọc hoặc chuyển pointcut thành danh sách được xác định trước. Khi cân nhắc weaving, phải kiểm tra lại toàn bộ tập join point và hoạt động class loader.

**E. Chi phí startup hoặc footprint là vấn đề**

Với công cụ chạy ngắn, tạo proxy class, phân tích metadata hoặc biến đổi bytecode lúc nạp class có thể quan trọng hơn throughput ổn định. Cân nhắc caching hợp lý, giảm tập lớp cần instrument hoặc đường wrapper đơn giản cho một biên cụ thể.

**F. Khó gỡ lỗi do lớp trung gian**

Nếu vấn đề chính là khó quan sát, đầu tiên có thể cải thiện tài liệu sơ đồ luồng advice, naming, trace IDs, stack trace và test hợp đồng. Chỉ thay kiến trúc khi chi phí nhận thức/vận hành vẫn vượt lợi ích.

## 9. Khi nào nên bỏ AOP ở một phạm vi cụ thể?

“Bỏ AOP” ở đây nghĩa là **không còn sử dụng cơ chế can thiệp AOP cho một concern hoặc một tập join point**, rồi chuyển trách nhiệm còn cần thiết sang cách thực hiện rõ ràng khác. Đó không đồng nghĩa xóa luôn audit hoặc kiểm soát quyền.

### 9.1. Các dấu hiệu có cơ sở để bỏ

| Dấu hiệu | Vì sao AOP có thể không hợp | Phương án thay thế có thể xem xét |
|---|---|---|
| Chỉ một hoặc hai điểm gọi rõ ràng | Chi phí thiết lập/đọc cấu hình cao hơn giá trị tập trung hóa | Gọi helper tường minh hoặc decorator nhỏ |
| Concern chỉ là một bước nghiệp vụ cụ thể | Giấu luồng chính trong advice gây khó hiểu | Giữ trong service/domain workflow |
| Pointcut rất khó định nghĩa ổn định | Dễ bỏ sót hoặc chặn nhầm khi refactor tên lớp/phương thức | API tường minh và contract rõ |
| Cơ chế proxy có đường bypass quan trọng | Chính sách bắt buộc không được bảo đảm | Đặt policy ở trusted boundary hoặc giá trị/domain invariant |
| Nhiều advice thay đổi kết quả khó dự đoán | Thứ tự và propagation khó review | Composition/decorator rõ thứ tự hoặc orchestration tường minh |
| Đường hot path có overhead vượt ngân sách | Đo thực xác nhận dispatch/context là nút thắt | Wrapper chuyên biệt, direct call, weaving phù hợp hoặc bỏ intercept nơi không cần |
| Build/runtime không hỗ trợ ổn định | Instrumentation, class loader, agent hoặc môi trường đích xung đột | Mã tường minh/khả năng instrument tương thích |
| Không cần dynamic interception | Một concern cố định có thể đơn giản hơn khi truyền dependency rõ | Explicit interface/decorator/helper |

**Không được xem các dấu hiệu trên là quy tắc máy móc.** Nếu AOP đang bảo vệ một chính sách bắt buộc ở nhiều biên quan trọng, quyết định bỏ có thể tạo rủi ro lớn hơn chênh lệch benchmark.

### 9.2. Các phương án không dùng AOP

**Helper tường minh:**

```java
// Minh họa, không phải chương trình độc lập.
auditSink.record(event);
int result = checkoutService.checkout(order);
```

Cách này đơn giản nhưng phải đặt audit ở đúng thời điểm và đảm bảo mọi caller hợp lệ không bỏ qua. Nếu audit yêu cầu thành công sau commit, thứ tự mẫu trên còn chưa đáp ứng; dùng nó như ví dụ cú pháp về explicit call, không như policy hoàn chỉnh.

**Decorator quanh interface:**

```java
// Minh họa, không phải chương trình độc lập.
final class AuditedOperation implements Operation {
    private final Operation delegate;
    private final AuditSink audit;

    AuditedOperation(Operation delegate, AuditSink audit) {
        this.delegate = delegate;
        this.audit = audit;
    }

    @Override
    public Result run(Command input) {
        Result result = delegate.run(input);
        audit.success(input, result);
        return result;
    }
}
```

Đây là **đoạn minh họa** vì `Operation`, `AuditSink`, `Result` và `Command` chưa được định nghĩa. Decorator cũng là một lớp trung gian và vẫn có overhead; điểm khác là quan hệ phụ thuộc và đường gọi dễ nhìn hơn. Chưa có `finally`/failure policy trong snippet, nên không tự dùng nó để thay advice có yêu cầu audit failure/cleanup.

**Hàm domain hoặc policy object:** phù hợp với bất biến nghiệp vụ, kiểm tra trạng thái và luật tính toán. Chúng không nhất thiết là aspect chỉ vì cùng được nhiều service dùng.

**Explicit instrumentation tại biên:** phù hợp với một số ít request handler, job entry hoặc public API boundary, nơi mọi caller bắt buộc đi qua điểm đó và việc giữ biểu thức xử lý hiển thị trong code giúp review dễ hơn.

Điều quan trọng là mỗi lựa chọn phải được xem xét cả **khả năng bị bỏ qua**, **tính dễ hiểu** và **bằng chứng hồi quy**.

## 10. Bài tập C: quyết định có bỏ AOP hay không

Đánh giá bốn tình huống:

**Tình huống 1 — tracing trên hàng triệu hàm thuần**

Điều kiện: pointcut chọn tất cả getter và phép tính nhỏ; tracing chủ yếu để chẩn đoán, không phải nghĩa vụ kiểm toán. Kết quả profiling xác nhận tỷ lệ lớn sự kiện không hữu ích và tạo nhiều allocation. Giải pháp hợp lý có thể là **thu hẹp phạm vi hoặc tắt tracing ở hot path**, không nhất thiết bỏ toàn bộ AOP khỏi ứng dụng. Kiểm tra tập điểm chẩn đoán còn cần giữ.

**Tình huống 2 — audit bắt buộc cho nhiều thao tác thay đổi trạng thái**

Điều kiện: audit được triển khai tập trung, test bao phủ đủ join point, overhead trong ngân sách. Bỏ AOP khiến phải sao chép policy ở nhiều nơi và tăng rủi ro bỏ sót. Có lý do **giữ AOP**, nhưng vẫn cần kiểm thử đường bypass, đường lỗi và tính bền vững của audit.

**Tình huống 3 — một thao tác đơn giản cần log thủ công**

Điều kiện: chỉ một biên được instrument, nhiều lớp proxy khó debug, có helper rõ và đội dự án không cần mở rộng policy. Nếu kiểm thử tương đương và đo cho thấy giải pháp tường minh ít phức tạp hơn, **bỏ AOP trong phạm vi này** có thể hợp lý.

**Tình huống 4 — proxy can thiệp sai khi self-invocation**

Điều kiện: chính sách quyền bắt buộc phải áp trên một lời gọi nội bộ nhưng cơ chế proxy hiện dùng chỉ nhìn thấy lời gọi qua proxy bên ngoài. Không thể “tối ưu” bằng cách bỏ hẳn kiểm tra. Phải **đặt policy tại biên đáng tin**, thay tổ chức đường gọi hoặc chọn cơ chế instrument đáp ứng join point bắt buộc, rồi kiểm thử không thể bypass.

### Đáp án tóm tắt theo tiêu chí

| Tình huống | Hướng quyết định | Bằng chứng buộc phải có |
|---|---|---|
| Tracing quá rộng | Thu hẹp, sampling có điều kiện hoặc tắt tại điểm thừa | Tần suất, hiệu năng, không mất telemetry bắt buộc |
| Audit xuyên suốt, đúng và rẻ | Giữ | Coverage join point, audit behavior, SLO |
| Một điểm gọi, nhiều phức tạp | Cân nhắc decorator/helper tường minh | Cùng chức năng, chi phí và độ rõ ràng |
| Proxy bỏ sót chính sách quyền | Sửa ranh giới/cơ chế; không bỏ policy | Test đường bypass và xử lý lỗi |

## 11. Ma trận quyết định đủ bằng chứng

Khi cần đưa ra quyết định kỹ thuật, dùng bảng so sánh trên cùng các tiêu chí:

| Tiêu chí | Giữ AOP | Thu hẹp/đổi cơ chế AOP | Bỏ AOP tại phạm vi đang xét |
|---|---|---|---|
| Chức năng bắt buộc | Giữ nguyên | Phải giữ nguyên | Chuyển sang nơi thực thi khác và test |
| Độ bao phủ chính sách | Phụ thuộc pointcut hiện tại | Phải có ma trận mới | Phải chứng minh mọi caller qua biên thay thế |
| Hiệu năng | Theo baseline thực tế | Lợi ích đo được sau thay đổi | So với phương án cùng semantics |
| Khả năng debug | Có thể khó do chain/proxy | Có thể đơn giản hơn | Thường đường gọi rõ hơn, tùy thiết kế |
| Bảo trì | Tốt khi concern xuyên suốt | Tốt khi giảm interception thừa | Tốt khi phạm vi nhỏ, kém nếu code lại phân tán |
| Tính di động triển khai | Phụ thuộc runtime instrument | Thay cơ chế có rủi ro mới | Có thể giảm lệ thuộc vào agent/weaving |
| Rủi ro hồi quy | Có baseline hiện tại | Pointcut/ordering thay đổi | Khả năng bỏ sót side effect và thứ tự |
| Kiểm chứng | Test nghiệp vụ + advice coverage | Test lại tập join point | Test policy tại mọi đường gọi thay thế |

Không bắt buộc dùng thang điểm số giả tạo. Viết rõ tiêu chí nào là **ràng buộc không được vi phạm** (ví dụ bảo mật, audit hoặc độ tin cậy giao dịch), tiêu chí nào là **mục tiêu tối ưu** (latency, bộ nhớ, startup) và tiêu chí nào là **chi phí bảo trì**.

## 12. Chiến lược chuyển đổi an toàn khi quyết định bỏ AOP

1. **Định nghĩa phạm vi:** concern nào và những join point nào sẽ thay thế, còn những aspect nào giữ lại.
2. **Chụp baseline chức năng:** tập input quan trọng, kết quả, lỗi, side effects, số lượt advice và thứ tự sự kiện.
3. **Tạo phương án tường minh:** decorator, helper, policy object hoặc workflow được chọn; code review thấy rõ nơi thực thi policy.
4. **Kiểm tra mọi caller:** lời gọi bên ngoài, nội bộ, callback, async, retry, chạy song song và đường lỗi theo đúng hợp đồng.
5. **Xác minh không còn hai cơ chế cùng xử lý:** nếu AOP vẫn bật trên wrapper mới, có thể audit/tracing lặp hai lần. Cần kế hoạch gỡ bỏ theo đúng phạm vi.
6. **So sánh chức năng tương đương:** kết quả, loại ngoại lệ, audit payload, thời điểm, transactional outcome, cleanup và bảo vệ dữ liệu.
7. **Đo lại:** CPU, throughput, allocation, p95/p99, GC, startup và số sự kiện. Không kết luận từ một mẫu chạy đơn lẻ.
8. **Có tiêu chí dừng và hoàn tác:** nếu mất policy bắt buộc, lỗi concurrency hoặc SLO xấu đi, chưa được coi thay đổi thành công.

Một số nơi có thể chuyển đổi dần theo từng loại operation để giảm phạm vi thử nghiệm, nhưng phải đặc biệt chú ý **đường chạy đồng thời của cơ chế cũ và mới**. Audit trùng hai lần cũng có thể là lỗi nghiệp vụ nghiêm trọng giống như thiếu một lần.

## 13. Những lỗi thường gặp khi đo và quyết định

1. **So direct không làm audit với AOP có audit:** đang so khác chức năng, không cô lập proxy overhead.
2. **Đếm số log rồi suy ra CPU:** số sự kiện không quy đổi trực tiếp sang ns/op hoặc allocation.
3. **Chỉ đo trung bình:** tail latency, GC pauses và contention có thể quyết định chất lượng hệ thống.
4. **Chạy benchmark không warm-up:** đo startup/JIT compilation lẫn với steady-state nếu mục tiêu là throughput nóng.
5. **Dead-code elimination hoặc constant folding:** benchmark có thể đo đường tối ưu khác thực tế nếu kết quả bị bỏ.
6. **Tắt logger trong một biến thể:** so khác công việc; cần so cùng cơ chế đầu ra khi muốn cô lập overhead.
7. **Không báo sai số:** chênh lệch nhỏ trong nhiễu đo không đủ căn cứ thay kiến trúc.
8. **Dùng benchmark trên một call site để kết luận mọi đường:** JVM JIT xử lý call site đa hình khác nhau.
9. **Tin rằng mọi AOP dùng reflection:** proxy gọi trực tiếp hoặc weaving có đặc điểm khác, phải đo đúng implementation.
10. **Coi pointcut match là đảm bảo mọi đường cần chặn:** lời gọi có thể đi vòng proxy hoặc không thuộc join point được hỗ trợ.
11. **Xóa audit để có kết quả nhanh:** gây mất chức năng nếu audit bắt buộc; cần phương án tương đương.
12. **Bỏ advice mà không tính thứ tự:** after/finally, error precedence và transaction semantics có thể đổi.
13. **Thay bằng helper copy ở nhiều nơi:** có thể tái tạo scattering/tangling và nguy cơ bỏ sót khi thêm method.
14. **Chỉ kiểm tra happy path:** không phát hiện audit success nhầm khi lỗi, thiếu cleanup hoặc retry nhiều lần.
15. **Bỏ qua chi phí di trú và bảo trì:** một tiết kiệm nhỏ có thể không bù rủi ro triển khai và khó review.
16. **Tối ưu khi chưa xác định nút thắt:** nếu bottleneck nằm ở I/O hay lock trong advice, đổi dispatch hiếm khi là giải pháp chính.
17. **Giữ AOP bất kể mức độ phức tạp:** khi chỉ còn một policy nhỏ ở một ranh giới rõ, code tường minh có thể tốt hơn.
18. **Giả định decorator luôn không có overhead:** decorator cũng thêm dispatch và logic; lợi ích phải dựa trên độ rõ ràng, semantics và số đo.

## 14. Bài tập cuối: báo cáo quyết định kiến trúc

Hãy viết một báo cáo ngắn về một concern đang dùng AOP theo mẫu sau, điền **số liệu đo thật của hệ thống**, không thay số giả định của bài học bằng “kết quả đo”:

```text
Concern:
Mục tiêu nghiệp vụ và chính sách bắt buộc:
Join point phải chặn:
Join point phải loại trừ:
Cơ chế AOP hiện dùng:
Test hồi quy đã chạy:
Trạng thái outcome / side effects / exception:
Benchmark (JDK, flags, workload, iterations, forks):
Baseline direct + same behavior:
AOP + same behavior:
Phần chênh lệch CPU/latency/allocated bytes:
p95/p99 dưới tải:
Bottleneck được profiler xác nhận:
Giải pháp thay thế được so sánh:
Rủi ro bỏ sót policy:
Quyết định: giữ / thu hẹp / đổi cơ chế / bỏ ở phạm vi này
Lý do và giới hạn của bằng chứng:
Kế hoạch triển khai, theo dõi và rollback:
```

**Tiêu chí đạt bài:**

- Có phép đo đúng đơn vị và có cách tái hiện.
- Tách chi phí interception khỏi chi phí công việc của advice.
- Có cả test tích cực, test phủ định và failure path.
- Có bằng chứng giữ hoặc chuyển giao đủ các chức năng bắt buộc.
- So sánh phương án thay thế bằng cùng tập chức năng.
- Quyết định được giải thích dựa trên workload và ràng buộc thật, không dựa vào cảm tính “AOP là tốt/xấu”.
- Không tự đưa kết quả số học minh họa thành kết luận về Java/JIT ở mọi môi trường.

## 15. Câu hỏi tự kiểm tra

**1. Khi AOP có audit còn direct không có audit, chênh lệch thời gian có phải là chi phí proxy không?** Không. Nó bao gồm cả chi phí chức năng audit. Muốn cô lập cơ chế phải so với phương án không AOP nhưng vẫn thực hiện audit tương đương.

**2. Giảm 95% số lượt advice có đồng nghĩa giảm 95% latency không?** Không. Có thể vẫn phải kiểm tra pointcut và đi qua proxy; logic nghiệp vụ và I/O còn chi phối tổng latency.

**3. Khi nào nên giữ AOP dù có overhead?** Khi concern thực sự xuyên suốt, độ bao phủ đúng, chi phí trong ngân sách và việc tập trung hóa policy mang lại giá trị bảo trì/độ tin cậy.

**4. Khi nào nên thay bằng decorator hoặc helper?** Khi phạm vi nhỏ, đường gọi rõ, cách tường minh dễ bảo trì hơn và test chứng minh cùng chức năng mà chi phí phù hợp.

**5. Tại sao phép thử hồi quy phải kiểm tra exception và số event?** Vì advice có thể vô tình nuốt lỗi, ghi audit success sai, nhân đôi event hoặc bỏ cleanup dù giá trị trả về ở happy path vẫn đúng.

**6. AOP trên hot path gây tăng allocation thì chắc chắn phải bỏ?** Không. Đầu tiên đo bằng profiler, thu hẹp pointcut, giảm cấp phát không cần thiết hoặc chọn cơ chế phù hợp; quyết định cuối còn phụ thuộc correctness và lợi ích bảo trì.

**7. Nếu handler không áp advice cho `quote()`, proxy có còn overhead không?** Có thể còn vì lời gọi vẫn đi qua handler/matcher. Muốn biết khoản thực phải đo đúng triển khai.

**8. Vì sao test qua chính đối tượng đã instrument quan trọng?** Test chỉ gọi trực tiếp target có thể không đi qua advice; khi đó code nghiệp vụ được phủ nhưng chính sách cross-cutting chưa được kiểm chứng.

**9. Có nên bỏ audit bắt buộc nếu nó gây tăng p99?** Không được bỏ chỉ để giảm latency. Cần tối ưu sink, đường ghi, cấu hình chính sách hoặc thiết kế khác vẫn bảo đảm yêu cầu audit và failure handling.

**10. Báo cáo quyết định nên dẫn chứng gì?** Tập join point mong đợi, kết quả test regression, benchmark có điều kiện tái hiện, profile CPU/allocation, p95/p99, so sánh phương án cùng semantics và các rủi ro triển khai.

**Kết luận thực hành:** AOP là một công cụ tổ chức chính sách xuyên suốt. Đánh giá nó bằng **độ đúng đắn, độ bao phủ và số liệu đo thật**. Nếu AOP giải quyết scattering/tangling mà chi phí chấp nhận được, nên giữ; nếu pointcut quá rộng, ưu tiên thu hẹp; nếu một concern đơn giản, không cần can thiệp động và phương án tường minh dễ kiểm chứng hơn, có thể bỏ AOP **tại phạm vi đó**. Mọi quyết định đều phải bảo toàn những hành vi mà người dùng và hệ thống phụ thuộc vào.