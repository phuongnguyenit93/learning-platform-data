# Ngăn quan hệ phụ thuộc vòng giữa các aspect

Khi **nhiều aspect** cùng tham gia một chương trình **Aspect-Oriented Programming (AOP)**, chúng có thể phụ thuộc nhau về thứ tự advice, dịch vụ được gọi, instance được khởi tạo hoặc callback lúc chạy. Nếu những quan hệ ấy tạo thành một **vòng phụ thuộc**, hệ thống có thể không dựng được cấu hình, không khởi tạo được đối tượng, chạy advice đệ quy vô hạn, phát sinh log storm hoặc deadlock. Chỉ sắp lại thứ tự khai báo chưa chắc xử lý được nguyên nhân.

**Mục tiêu bài học:** nhận ra những dạng chu trình khác nhau, biểu diễn quan hệ đúng ngữ nghĩa, phát hiện trước bằng **DAG/topological sort** khi thích hợp, ngăn advice tự chặn đường hỗ trợ của nó, thiết kế phụ thuộc một chiều và kiểm thử các đường thành công, lỗi, retry và bất đồng bộ. Kiến thức áp dụng cho **AOP cơ bản và nâng cao nói chung**; cú pháp pointcut, precedence và mô hình instantiation cụ thể phụ thuộc cơ chế triển khai.

## 1. Nhắc lại các thành phần liên quan

- **Join point:** điểm chương trình có thể được can thiệp, ví dụ method call hoặc method execution khi mô hình hỗ trợ.
- **Pointcut:** điều kiện lựa chọn những join point được áp dụng advice.
- **Advice:** logic before, after, around hoặc dạng khác chạy tại điểm được chọn.
- **Aspect:** đơn vị gom pointcut/advice và có thể sở hữu trạng thái hoặc dependency.
- **Weaving:** kết hợp advice vào chương trình qua biên dịch, bytecode, load-time hoặc proxy/wrapper.
- **Precedence:** thứ tự ưu tiên/phạm vi lồng nhau giữa nhiều advice cùng khớp một điểm.
- **Continuation/proceed:** khả năng một around advice cho phép phần xử lý bên trong tiếp tục.

Aspect A chọn cùng join point với aspect B **không đủ để tạo vòng**. Vòng chỉ xuất hiện khi có một đường phụ thuộc **quay trở lại node đã đi qua**, theo loại quan hệ đang xét.

Ví dụ:

~~~text
AUTH -> TRANSACTION -> AUDIT -> AUTH
~~~

Nếu mỗi mũi tên đều có nghĩa "aspect bên trái bắt buộc bao ngoài aspect bên phải", đây là vòng precedence bất khả thi. Nhưng nếu A.before, B.before rồi B.after, A.after, đó có thể là một stack lồng nhau hoàn toàn hợp lệ, không phải vòng.

## 2. Phân loại các dạng phụ thuộc vòng

| Loại vòng | Cạnh có nghĩa gì? | Hậu quả điển hình | Hướng xử lý |
| --- | --- | --- | --- |
| **Precedence** | A bắt buộc ở ngoài/ưu tiên trước B | Không có thứ tự thỏa mọi ràng buộc | Phân tích invariant, bỏ ràng buộc sai, phát hiện cycle |
| **Khởi tạo** | A cần instance của B ngay khi tạo | Constructor recursion hoặc không xây xong object | Dependency inversion, tách lõi/sink độc lập |
| **Runtime call/reentrancy** | Advice A gọi method làm A được gọi lại | StackOverflowError, log storm, timeout | Giới hạn pointcut, tách helper và sink |
| **Event/callback** | A phát event khiến listener gọi lại A | Sự kiện lặp vô hạn, queue quá tải | Event flow một chiều, dedup, termination |
| **Lock/deadlock** | A giữ L1 chờ L2, B giữ L2 chờ L1 | Nhiều thread đứng chờ | Quy định lock order, không callback trong critical section |
| **Retry/fallback** | A retry qua B, B fallback lại A | Lặp side effect, hết deadline | Attempt budget, idempotency, loại cycle |
| **Weaving/instrumentation** | Code helper được advice chặn lại | Instrumentation tự kích hoạt | Phạm vi exclude, kiểm thử bytecode và runtime |

Mỗi loại cần **bằng chứng và giải pháp riêng**. Một bộ phát hiện precedence cycle không thể tự phát hiện mọi call cycle tại runtime; một `ThreadLocal` guard không giải quyết được constructor dependency cycle.

## 3. Chu trình precedence: không có thứ tự tuyến tính hợp lệ

Quy ước rõ:

~~~text
A -> B  nghĩa là  A phải bao ngoài B
~~~

Khi có:

~~~text
AUTH -> TX
TX -> AUDIT
AUDIT -> AUTH
~~~

muốn thỏa tất cả, AUTH phải ở ngoài TX, TX ở ngoài AUDIT, rồi AUDIT ở ngoài AUTH. Không có lớp outermost hợp lệ.

**Đừng âm thầm chọn thứ tự tên lớp hoặc thứ tự build** để che lỗi. Nếu quan hệ là ràng buộc bắt buộc của bảo mật, transaction và audit, cần báo **configuration error** trước khi phục vụ request.

### 3.1 Có thể đang mô hình hóa sai một yêu cầu

Một yêu cầu như "Audit phải chạy trước khi nghiệp vụ bắt đầu và sau khi biết kết quả" **không có nghĩa** vừa có cạnh `AUDIT -> BUSINESS` vừa có cạnh `BUSINESS -> AUDIT`. Một **around advice** có thể bao nghiệp vụ:

~~~text
AUDIT.before
    BUSINESS
AUDIT.after or AUDIT.error
~~~

Đường vào và đường ra là hai pha của một wrapper; bản thân cấu trúc lồng nhau **không có cycle**.

Nếu "Transaction phải bắt đầu trước nghiệp vụ và commit sau nghiệp vụ", đó cũng thường là quan hệ **surround**, không phải hai ràng buộc precedence mâu thuẫn.

### 3.2 Partial order thay vì sắp mọi aspect

Một chương trình có thể cần:

~~~text
AUTH -> CACHE
TRANSACTION -> MUTATION
METRICS may be independent
AUDIT needs to see denied and successful outcomes
~~~

Hai dòng đầu biểu diễn vị trí, còn hai dòng sau đòi hỏi một **hợp đồng quan sát**. Không nhất thiết cần một thứ tự toàn phần cho mọi aspect. **Partial order** giúp tránh tạo cạnh không có cơ sở, giảm nguy cơ chu trình giả.

## 4. Đồ thị có hướng và phát hiện vòng

Một **directed acyclic graph (DAG)** là đồ thị có hướng **không có chu trình**. Với các cạnh "A phải đi trước B", có thể tạo một **topological order** khi đồ thị là DAG.

Ví dụ:

~~~text
AUTH -> CACHE -> TRACE
   \--------------^
~~~

Thứ tự hợp lệ: `AUTH, CACHE, TRACE`.

Ví dụ có vòng:

~~~text
A -> B
B -> C
C -> A
~~~

Bất kỳ thứ tự nào cũng phá ít nhất một cạnh.

### 4.1 DFS ba trạng thái

Một thuật toán kiểm tra vòng:
- **WHITE / 0:** chưa thăm.
- **GRAY / 1:** đang đi vào node, vẫn nằm trong recursion stack.
- **BLACK / 2:** đã duyệt xong mọi cạnh đi ra.

Khi DFS gặp một node **GRAY**, có đường quay lại node đang xử lý → **cycle**. Nếu gặp node **BLACK**, đó có thể chỉ là một **dependency chung** (hai aspect cùng cần một aspect thứ ba), không phải cycle.

Muốn báo lỗi hữu ích, giữ stack và in đường vòng: `AUTH -> TX -> AUDIT -> AUTH`, không chỉ nói "có lỗi thứ tự".

### 4.2 Thuật toán Kahn

Cách khác:
1. Tính indegree của mỗi node.
2. Đưa các node indegree=0 vào hàng đợi.
3. Lấy từng node, thêm vào kết quả, giảm indegree các node kế.
4. Nếu không thể lấy đủ số node, đồ thị có cycle.

DFS và Kahn đều có độ phức tạp `O(V + E)` với danh sách kề hợp lý, V là số node, E là số cạnh. DFS thuận tiện để hiển thị đường cycle; Kahn thuận tiện để phân tích những node còn bị khóa.

### 4.3 Chỉ chạy topological sort trên đúng đồ thị

Không nên gộp bừa:
- Cạnh precedence "A phải ngoài B".
- Cạnh dependency "A cần B để khởi tạo".
- Cạnh runtime "A có thể gọi B".
- Cạnh state "A viết vào state của B".

Một vòng gọi runtime có thể **có điều kiện dừng hợp lệ**, còn vòng precedence bắt buộc không thể thỏa trong một chuỗi tuyến tính. Phải **gắn nhãn và phân loại cạnh trước khi phân tích**.

## 5. Java 17: phát hiện vòng trước khi ghép advice

Ví dụ độc lập dùng Java 17. Mỗi `Rule` chứa tên aspect và danh sách các aspect **phải nằm bên trong nó**. `A -> B` nghĩa A bao ngoài B. DFS từ chối cycle và cạnh tới node không tồn tại, rồi tạo thứ tự topo và dựng các wrapper.

Tạo file `AspectCycleDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AspectCycleDemo {
    record Rule(String name, List<String> mustWrap) {}

    @FunctionalInterface
    interface Action {
        String run(String id);
    }

    static void visit(
            String name,
            Map<String, List<String>> graph,
            Map<String, Integer> state,
            List<String> path,
            List<String> finished) {
        int current = state.getOrDefault(name, 0);

        if (current == 1) {
            int begin = path.indexOf(name);
            List<String> cycle =
                    new ArrayList<>(path.subList(begin, path.size()));
            cycle.add(name);
            throw new IllegalArgumentException(
                    "cycle " + String.join(" -> ", cycle));
        }
        if (current == 2) {
            return;
        }

        state.put(name, 1);
        path.add(name);
        for (String inner : graph.get(name)) {
            if (!graph.containsKey(inner)) {
                throw new IllegalArgumentException(
                        "unknown aspect " + inner);
            }
            visit(inner, graph, state, path, finished);
        }
        path.remove(path.size() - 1);
        state.put(name, 2);
        finished.add(name);
    }

    static List<String> resolve(List<Rule> rules) {
        Map<String, List<String>> graph = new LinkedHashMap<>();
        for (Rule rule : rules) {
            if (graph.putIfAbsent(
                    rule.name(), List.copyOf(rule.mustWrap())) != null) {
                throw new IllegalArgumentException(
                        "duplicate aspect " + rule.name());
            }
        }

        Map<String, Integer> state = new HashMap<>();
        List<String> finished = new ArrayList<>();
        for (String name : graph.keySet()) {
            visit(name, graph, state, new ArrayList<>(), finished);
        }
        Collections.reverse(finished);
        return List.copyOf(finished);
    }

    static Action wrap(String name, Action next) {
        return id -> {
            System.out.println(name + " before");
            try {
                String result = next.run(id);
                System.out.println(name + " after");
                return result;
            } catch (RuntimeException error) {
                System.out.println(name + " error");
                throw error;
            } finally {
                System.out.println(name + " finally");
            }
        };
    }

    static Action chain(List<String> outerFirst) {
        Action current = id -> {
            System.out.println("BUSINESS " + id);
            if ("fail".equals(id)) {
                throw new IllegalStateException("failure");
            }
            return "done:" + id;
        };
        for (int i = outerFirst.size() - 1; i >= 0; i--) {
            current = wrap(outerFirst.get(i), current);
        }
        return current;
    }

    static void scenario(Action action, String id) {
        System.out.println("CASE " + id);
        try {
            System.out.println("RESULT " + action.run(id));
        } catch (RuntimeException error) {
            System.out.println("CALLER "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        List<Rule> valid = List.of(
                new Rule("AUTH", List.of("CACHE", "TRACE")),
                new Rule("CACHE", List.of("TRACE")),
                new Rule("TRACE", List.of()));

        List<String> order = resolve(valid);
        System.out.println("ORDER " + String.join(">", order));
        Action action = chain(order);
        scenario(action, "ok");
        scenario(action, "fail");

        System.out.println("CASE cycle");
        try {
            resolve(List.of(
                    new Rule("X", List.of("Y")),
                    new Rule("Y", List.of("Z")),
                    new Rule("Z", List.of("X"))));
        } catch (IllegalArgumentException error) {
            System.out.println("REJECT " + error.getMessage());
        }

        System.out.println("CASE unknown");
        try {
            resolve(List.of(
                    new Rule("AUDIT", List.of("MISSING"))));
        } catch (IllegalArgumentException error) {
            System.out.println("REJECT " + error.getMessage());
        }
    }
}
~~~

Chạy bằng **JDK 17 trở lên**:

~~~bash
javac AspectCycleDemo.java
java AspectCycleDemo
~~~

Stdout chính xác của ví dụ:

~~~text
ORDER AUTH>CACHE>TRACE
CASE ok
AUTH before
CACHE before
TRACE before
BUSINESS ok
TRACE after
TRACE finally
CACHE after
CACHE finally
AUTH after
AUTH finally
RESULT done:ok
CASE fail
AUTH before
CACHE before
TRACE before
BUSINESS fail
TRACE error
TRACE finally
CACHE error
CACHE finally
AUTH error
AUTH finally
CALLER IllegalStateException
CASE cycle
REJECT cycle X -> Y -> Z -> X
CASE unknown
REJECT unknown aspect MISSING
~~~

### 5.1 Vì sao kết quả `AUTH>CACHE>TRACE`?

DFS với các cạnh:

~~~text
AUTH -> CACHE
AUTH -> TRACE
CACHE -> TRACE
~~~

đưa TRACE vào danh sách hoàn tất trước CACHE và AUTH; đảo danh sách này được thứ tự topo `AUTH, CACHE, TRACE`. Builder dựng wrapper **từ trong ra ngoài**:

~~~text
current = Business
current = TRACE(current)
current = CACHE(current)
current = AUTH(current)
~~~

Khi gọi `action.run("ok")`, AUTH.before chạy đầu tiên và AUTH.finally chạy cuối cùng. Đây là ngữ nghĩa của **wrapper mô phỏng**, không phải một quy tắc số priority chung cho mọi bộ AOP.

### 5.2 Vì sao `X -> Y -> Z -> X` bị từ chối?

DFS bắt đầu với X, đi tới Y, Z, rồi thấy X **đang nằm trên stack** (GRAY). Chu trình được báo tường minh; chương trình không tạo wrapper từ cấu hình trái ngược.

Lỗi `unknown aspect MISSING` phát sinh vì một ràng buộc tới node không có trong danh sách. Không âm thầm bỏ qua cạnh bị thiếu, tránh tạo chain khác mục đích.

### 5.3 Giới hạn ví dụ

- `Rule` là cấu trúc của chương trình demo, **không phải cú pháp pointcut/precedence phổ quát**.
- Chương trình dùng Java wrapper; không dệt bytecode bằng công cụ AOP.
- Nó phát hiện **vòng precedence tĩnh**, không tự phát hiện vòng constructor/service hoặc đệ quy runtime.
- Mỗi wrapper gọi `next.run` đúng một lần. Một around advice thật có thể short-circuit hoặc retry nếu mô hình hỗ trợ.
- Các nhãn AUTH/CACHE/TRACE chỉ để mô phỏng thứ tự; không chứa kiểm tra quyền, cache, hay truyền trace thật.
- Nếu một mô hình AOP có quy tắc ưu tiên khác cho before/after độc lập, không suy thứ tự đó từ chương trình wrapper.

## 6. Vòng khởi tạo: aspect A cần B, B lại cần A

Ví dụ:

~~~text
AuditAspect constructor -> MetricsService
MetricsService constructor -> TracingAspect
TracingAspect constructor -> AuditAspect
~~~

Nếu mọi dependency đều cần **ngay khi xây dựng object**, không thể hoàn tất A khi chưa có B, không thể có B khi chưa có C, và không thể có C khi chưa có A. Một hệ thống có thể phát hiện lỗi lúc khởi tạo, hoặc thiếu kiểm tra khiến lời gọi constructor lặp.

### 6.1 Sửa bằng tách dependency một chiều

Một kiến trúc tốt hơn:

~~~text
AuditAspect ------MetricsAspect -----+--> DiagnosticsSink
TracingAspect ----/
~~~

Mỗi aspect phụ thuộc vào một interface **nhận sự kiện tối thiểu**. `DiagnosticsSink` không được gọi ngược vào các method mà những aspect này chặn.

Ví dụ abstraction:

~~~java
interface MetricRecorder {
    void count(String eventName);
}
~~~

Đây là **mảnh khai báo**, không phải chương trình độc lập. Một implementation có thể gửi metric qua bộ đệm hoặc hệ thống quan sát, nhưng phải có hợp đồng không tạo đệ quy về chính aspect phát dữ liệu.

### 6.2 Lazy injection không phải phép xóa vòng

Nếu hoãn khởi tạo B đến khi invocation đầu tiên gọi vào A, nhưng A vẫn gọi B và B vẫn gọi A, chu trình runtime **vẫn còn**. Lazy có thể thay **thời điểm phát sinh lỗi**, không thay ý nghĩa đường phụ thuộc.

Một phương án đúng cần **đổi cấu trúc cạnh**: đưa logic chung xuống một dịch vụ cấp thấp, chuyển tương tác sang event một chiều hoặc tách trách nhiệm.

### 6.3 Tránh nghiệp vụ trong constructor

Aspect constructor không nên tùy tiện gửi audit, gọi API, kích hoạt weaving hoặc truy cập một service đang ở trạng thái **chưa sẵn sàng**. Bootstrap nên tập trung vào cấu hình dependency. Giai đoạn xử lý request có thể khởi động sau khi các thành phần cần thiết đã được xây dựng và kiểm tra.

## 7. Vòng runtime: advice tự gọi lại chính nó

Một nguy cơ phổ biến là pointcut quá rộng:

~~~text
Service.handle()
   -> LoggingAdvice
        -> LogService.write()
             -> LoggingAdvice
                  -> LogService.write()
                       -> ...
~~~

Nếu `LogService.write` cũng là method được pointcut LoggingAdvice chọn, chính việc ghi log kích hoạt một lượt ghi log mới. Đây là **reentrancy/call cycle**, dù precedence DAG không có lỗi.

Tác động có thể gồm:
- `StackOverflowError`, CPU tăng và log storm.
- Nhiều event cho một invocation khiến metrics sai.
- Tăng latency hoặc timeouts.
- Lộ dữ liệu nếu log tiếp tục in arguments/context nhạy cảm.
- Exception từ bộ log che mất lỗi gốc của nghiệp vụ.
- Nguy cơ OOM khi một sự kiện phát ra nhiều sự kiện khác.

### 7.1 Ngăn bằng giới hạn pointcut

Ưu tiên chỉ chọn **ranh giới nghiệp vụ cần quan sát**, và tách:
- Mã helper của advice.
- Bộ ghi log/metric hoặc exporter.
- Hạ tầng dispatch event.
- InvocationHandler/proxy internals.
- Thao tác quản lý aspect và lifecycle.

Ví dụ giả mã scope:

~~~text
include: application.publicBusinessOperations
exclude: logging.sinks, tracing.exporters,
         metrics.collectors, aspect.helpers
~~~

Không có cú pháp chung để biểu diễn hai dòng trên; cần dùng quy tắc của công cụ thực tế. **Loại infrastructure khỏi logging advice** không có nghĩa cho phép infrastructure bỏ qua các yêu cầu bảo mật bắt buộc ở ranh giới khác.

### 7.2 Đừng gọi proxy chính nó để “proceed”

Một handler có thể mắc lỗi:

~~~text
handle(proxy.method):
    return proxy.method()
~~~

Nếu `proxy.method` lại gọi chính handler, ta có vòng vô hạn. Một proxy kiểu delegation thường phải gọi **target hoặc interceptor kế tiếp**. Nếu cần retry, phải có số lần thử hữu hạn và tránh lặp side effects.

### 7.3 Self-invocation khác vòng phụ thuộc

Trong mô hình proxy delegation:

~~~text
Client -> Proxy.outer() -> Target.outer()
                                  |
                                  +--> this.inner() trên target
~~~

Lời gọi `this.inner()` có thể **bypass proxy**, khiến advice cho inner không chạy. Đây là vấn đề **thiếu coverage**, không phải reentrancy. Ngược lại, khi handler gọi `proxy.outer()` từ chính handler, mới có nguy cơ **tự tái nhập**.

Một cơ chế subclass proxy có thể có dispatch khác; phải phân tích đường gọi thật, không đồng nhất mọi proxy hoặc mọi loại method execution.

## 8. Sử dụng guard đúng mức, không che lỗi bảo mật

Một guard theo thread có thể chặn **logging advice** tự ghi log khi đang ở trong đường log:

~~~text
if alreadyLoggingOnCurrentThread:
    proceedWithoutThisOptionalLog()
else:
    markLogging()
    try:
        recordMinimalEvent()
        proceed()
    finally:
        restorePreviousMark()
~~~

Đây là **giả mã**. Guard thích hợp **chỉ khi được phép bỏ log phụ trợ của invocation tái nhập**. Nó không thay điểm cắt, không kiểm tra cycle tĩnh và không tự xử lý các đường async chuyển thread.

**Không dùng guard để tự bỏ qua authorization, validation hoặc audit bắt buộc.** Một policy bảo mật chỉ cần xuất hiện ở lần gọi tái nhập là đủ để việc skip trở thành lỗ hổng. Kiểm soát quyền phải dựa trên ranh giới đáng tin và được kiểm thử cả đường direct/proxy call.

### 8.1 ThreadLocal và async

`ThreadLocal` bảo vệ trạng thái **của một Java thread**, không tự đi theo một request logic qua executor hoặc remote call. Nếu vòng event được chuyển qua thread/process khác, guard có thể không còn thấy marker. Cần một thiết kế theo **logical flow**, hop limit hoặc event deduplication phù hợp khi thật sự cần; đồng thời đảm bảo không truyền token/PII không cần thiết.

### 8.2 Guard phải khôi phục trạng thái

Với nested calls, đơn giản `set(false)` trong `finally` có thể xóa marker của một phạm vi ngoài nếu không xem xét giá trị trước đó. Cần **snapshot và restore**, hoặc dùng cơ chế scope/stack phù hợp. Điều này quan trọng khi thread pool tái sử dụng thread.

## 9. Event và callback tạo cycle gián tiếp

Không phải mọi vòng đều trực tiếp:

~~~text
Aspect A updates Store
Store notifies Listener B
Listener B calls Service C
Service C passes through Aspect A
Aspect A updates Store again
~~~

Chu trình này có thể chạy **đồng bộ hoặc bất đồng bộ**. Nếu dùng hàng đợi, stack có thể không tràn nhưng số lượng event vẫn tăng không giới hạn.

Biện pháp:
- Xác định event nào được phép **phát sinh event thứ cấp**.
- Dùng event ID/correlation và deduplication theo hợp đồng.
- Không cho listener phát lại cùng loại event về nguồn mà không có điều kiện dừng.
- Áp dụng deadline, retry budget và TTL cho workflow.
- Tránh callback không kiểm soát trong khi giữ lock.
- Có giới hạn queue/backpressure và cảnh báo số event trên một business operation.
- Kiểm tra thất bại của sink không gọi lại **chính sink bị lỗi** để báo lỗi mãi.

### 9.1 Cycle qua khóa

Nếu:
- Thread 1 giữ `L1`, advice A gọi B và chờ `L2`.
- Thread 2 giữ `L2`, advice B gọi A và chờ `L1`.

Đó là **wait-for cycle**, có thể gây deadlock. Cần thống nhất thứ tự lấy khóa, không gọi callback tùy ý khi giữ lock, rút ngắn critical section và test concurrency. Precedence order trong một request không bảo đảm thứ tự khóa giữa nhiều thread.

## 10. Không nhầm vòng với các tương tác đúng

### 10.1 Nhiều aspect cùng khớp một điểm

~~~text
Authorization(Business)
Tracing(Business)
~~~

Hai aspect cùng chọn business không chứng minh có cycle. Chỉ khi có một **quan hệ quay lại** (ví dụ Tracing gọi method bị Tracing chọn lại) hoặc các ràng buộc precedence trái ngược mới có vấn đề vòng.

### 10.2 Advice trước/sau theo hai chiều

Trong chuỗi:

~~~text
A(B(C(Business)))
~~~

đường vào `A.before -> B.before -> C.before`, còn khi kết thúc thành công `C.after -> B.after -> A.after`. Đó là kết quả tự nhiên của lời gọi lồng nhau.

### 10.3 Node phụ thuộc chung

Đồ thị:

~~~text
A -> C
B -> C
C -> (none)
~~~

không chứa cycle; hai node cùng phụ thuộc C. DFS phải phân biệt gặp node **đã xong** với gặp node **đang thăm**.

### 10.4 Đệ quy hợp lệ có base case

Một thuật toán tìm kiếm đệ quy có thể quay lại cùng function theo chiều sâu giảm dần và dừng khi đạt điều kiện cơ sở. AOP không cấm mọi recursion; cần xác định **termination invariant**, chiều sâu và nguy cơ advice nhân đôi quan sát. Nhưng một advice log gọi logger mà logger lại kích hoạt chính advice thường không có base case nghiệp vụ hữu ích.

## 11. Phân tích đặc biệt với retry, fallback và transaction

Giả sử:

~~~text
Retry(Transaction(Business))
Transaction(Retry(Business))
~~~

Đây không phải cycle chỉ vì Retry và Transaction bao nhau. Hai cấu trúc khác nhau về **ranh giới transaction cho mỗi attempt**. Nếu retry được cài để gọi continuation lại nhiều lần, cần kiểm soát idempotency.

Vòng xuất hiện khi:
- Retry A gọi fallback B.
- Fallback B lại gọi endpoint bị Retry A chọn.
- Không có giới hạn attempts/hop/deadline.

Hoặc một ErrorTranslator khi gặp lỗi gửi event tới một service mà chính nó chặn, làm sinh lỗi và event lặp.

Một thiết kế đúng cần:
1. Phân loại lỗi có thể retry.
2. Giới hạn số lần và tổng thời gian.
3. Chặn lặp side effect nhạy cảm.
4. Đảm bảo rollback/commit theo hợp đồng.
5. Phát audit/metric theo đơn vị **request** hay **attempt** đã định nghĩa.
6. Kiểm tra không có dependency ngược qua logging/error reporting.

## 12. Khi có nhiều cơ chế weaving

Compile-time/post-compile weaving có thể thêm helper vào bytecode. Nếu một weaver khác có pointcut quá rộng, nó có thể chọn helper đã thêm và tạo instrumentation lặp. Một load-time agent hoặc proxy runtime cũng có thể chặn đường đi tới helper theo cấu hình.

**Không tự khẳng định** mọi weaver đều nhận diện helper là join point; điều đó phụ thuộc ngôn ngữ pointcut và quy tắc loại trừ synthetic/generated methods.

Các bước kiểm chứng:
- Xác nhận **tập join point thực tế** được chọn.
- Phân biệt method `call` và `execution` nếu nền tảng hỗ trợ.
- Kiểm tra code helper do weaver sinh có bị chọn lại không.
- Kiểm tra class loader, artifact và phiên bản công cụ.
- Giữ đầu vào unwoven; không reweave tùy tiện nếu chưa rõ hợp đồng.
- Đếm số lần advice chạy tại một business event để phát hiện instrument hai lần.
- So sánh clean/incremental build khi thay pointcut/precedence.

Việc đảo thứ tự đọc file hoặc build **không tự làm hợp lệ** chu trình precedence vốn bất khả thi. Nếu ba ràng buộc vẫn mâu thuẫn, phải sửa ràng buộc chứ không đổi thứ tự compiler.

## 13. Cách thiết kế không vòng

### 13.1 Tách theo lớp phụ thuộc một chiều

~~~text
Business operations
         |
         v
Interception / policy boundary
         |
         v
Small recorder / validation interfaces
         |
         v
Independent infrastructure sinks
~~~

Những component tầng dưới không được gọi lại ranh giới tầng trên qua đường bị instrument tương tự, trừ khi có hành vi tái nhập được thiết kế và kiểm chứng.

### 13.2 Extract service dùng chung

Nếu aspect A gọi B vì cần format dữ liệu, còn B gọi A vì cần audit, thường nên trích một formatter hoặc event publisher riêng:

~~~text
A ---> SharedFormatter <--- B
A ---> SafeEventSink  <--- B
~~~

A và B phụ thuộc **xuống dưới**, không trực tiếp gọi lẫn nhau để giải quyết việc của mình.

### 13.3 Hợp nhất những bất biến không thể tách

Nếu hai aspect đều yêu cầu "tôi phải ở ngoài aspect kia" để quản lý cùng một transaction hoặc tài nguyên, có thể đây là một quy tắc điều phối quá gắn chặt để phân thành hai wrappers độc lập. Cân nhắc một orchestrator giữ ownership tài nguyên, hoặc chuyển logic bất biến vào tầng nghiệp vụ cốt lõi rồi để aspect chỉ quan sát.

Không gom mọi concern thành một giant aspect theo thói quen; chỉ hợp nhất nơi **không thể giải quan hệ phụ thuộc bằng ranh giới rõ ràng**.

### 13.4 Fail fast và chính sách rollback

Một builder nên từ chối:
- Đồ thị precedence có chu trình.
- Dependency construction không thể giải quyết.
- Aspect/rule tham chiếu node không tồn tại.
- Configuration để logging advice instrument chính logger theo đường vòng nguy hiểm đã biết.
- Retry không có termination policy.
- Priority tie mà thứ tự có ảnh hưởng an ninh nhưng chưa được giải quyết.

Lỗi nên chỉ rõ **đường vòng**, rule liên quan và đề xuất tách dependency. Giữ cấu hình đã chạy đúng trước đó để rollback nếu một bản mới tạo vòng.

## 14. Ma trận kiểm thử

| Tình huống | Điều phải chứng minh |
| --- | --- |
| Precedence DAG hợp lệ | Sinh order thỏa mọi cạnh |
| A→B→C→A | Từ chối và báo đường cycle |
| A→C và B→C | Không nhận nhầm là cycle |
| Cạnh trỏ node thiếu | Từ chối cấu hình |
| Tên aspect trùng | Không ghi đè âm thầm |
| Construction cycle | Phát hiện trước xử lý request |
| Logging self-observation | Không StackOverflowError/log storm |
| Proxy handler gọi proxy chính nó | Không reentry ngoài dự kiến |
| Self-invocation trên target | Không nhầm bypass với recursion |
| Event listener callback | Không phát event vô hạn |
| Retry/fallback | Attempts hữu hạn, side effects an toàn |
| Cache hit/authorization deny | Không bypass nghĩa vụ bảo mật |
| Exception/finally | Không che lỗi gốc, cleanup chạy |
| Concurrency/locks | Không deadlock do wait-for cycle |
| Async callback | Không quên giới hạn theo logical flow |
| Multiple weaving tools | Không instrument helper hoặc lặp advice ngoài ý định |
| Build/redeploy | Phiên bản precedence mới thật sự được dùng |
| Diagnostic logging | Không thu thập token/PII không cần thiết |

**Test chống vòng** nên dùng dữ liệu giả và giới hạn hữu hạn về số lời gọi/event để fail sớm. Không cần cố ý chạy đến `StackOverflowError` mới chứng minh có recursion. Với logger, có thể assert **một invocation nghiệp vụ tạo số event cố định**; với precedence, assert thứ tự advice và đường lỗi; với locks, dùng kiểm thử concurrency thích hợp.

## 15. Checklist kiểm tra trước production

- [ ] Xác định chính xác mỗi aspect, pointcut, advice type và vòng đời instance.
- [ ] Phân loại cạnh precedence, constructor, runtime call, callback, state và lock riêng biệt.
- [ ] Với precedence, xây DAG và tìm cycle bằng DFS/Kahn.
- [ ] In đường vòng cụ thể trong thông báo lỗi; không chọn thứ tự ngẫu nhiên.
- [ ] Phân biệt before/after nesting với cycle thật.
- [ ] Kiểm tra scope pointcut không chọn helper của chính advice gây reentry.
- [ ] Kiểm tra logging/metric sinks là dependency một chiều.
- [ ] Không để proxy handler gọi lại chính proxy khi nó cần chuyển tiếp vào target.
- [ ] Không dùng suppression guard để bỏ qua authorization hoặc audit bắt buộc.
- [ ] Xác định termination của retry, fallback, event dispatch và async workflow.
- [ ] Không gọi callback chưa kiểm soát trong lúc giữ lock.
- [ ] Bảo đảm event ID, dedup, TTL, quota và backpressure khi cần.
- [ ] Test nhiều aspects cùng match, short-circuit, error/finally và direct/proxy paths.
- [ ] Kiểm tra class loader, weaving scope và generated/bridge methods theo mô hình thực tế.
- [ ] Test clean/incremental build và artifact/runtime configuration.
- [ ] Đo overhead, log volume, stack depth và số event/attempt cho một request.
- [ ] Giữ khả năng rollback về graph và cấu hình đã xác minh.

## 16. Câu hỏi ôn tập

**Câu 1.** A phải bao ngoài B, B ngoài C, C lại ngoài A. Thay tên class có giải được không?

**Đáp:** không. Đây là cycle precedence. Cần sửa quan hệ bắt buộc/kiến trúc.

**Câu 2.** A và B cùng phụ thuộc C có phải cycle không?

**Đáp:** không. Hai cạnh hội tụ ở C không quay lại A hoặc B.

**Câu 3.** Logging advice ghi qua một method cũng được chính pointcut chọn. Tại sao nguy hiểm?

**Đáp:** việc ghi log lại kích hoạt advice, làm event được ghi lặp đến khi cạn tài nguyên. Cần sửa scope hoặc tách sink không được instrument.

**Câu 4.** Dùng một cờ `ThreadLocal` để bỏ qua advice đang tái nhập có đủ bảo vệ vòng qua event bus không?

**Đáp:** không. Event có thể chạy trên thread/process khác. Ngoài ra không được dùng guard để bỏ qua kiểm tra bảo mật bắt buộc.

**Câu 5.** A.before -> B.before -> B.after -> A.after có phải vòng dependency?

**Đáp:** không. Đây là ngữ nghĩa bình thường của hai around wrappers lồng nhau.

**Câu 6.** Vì sao một builder nên phát hiện cạnh tới aspect không tồn tại?

**Đáp:** nếu bỏ cạnh đi, chuỗi tạo ra có thể vi phạm invariant; cần báo cấu hình không hợp lệ thay vì âm thầm thay ý định.

**Câu 7.** Vòng A gọi B, B gọi A qua callback nhưng không nằm trong constructor có được bộ kiểm tra dependency khởi tạo phát hiện chắc chắn không?

**Đáp:** không. Phải kiểm tra runtime interaction graph và đường callback.

**Câu 8.** Hai aspect lấy khóa theo thứ tự khác nhau, điều gì có thể xảy ra?

**Đáp:** deadlock vì mỗi thread giữ một khóa và chờ khóa còn lại. Dùng thống nhất lock order và tránh callback trong critical section.

## 17. Kết luận

**Ngăn quan hệ phụ thuộc vòng giữa các aspect** không có nghĩa "cấm mọi lồng nhau" mà là **ngăn các ràng buộc bất khả thi và các đường gọi không có điểm dừng đáng tin**. Có ba câu hỏi phải trả lời đúng:

1. **Thứ tự bắt buộc có thỏa được không?** Nếu là precedence, hãy kiểm tra DAG và fail fast khi có cycle.
2. **Các aspect có phụ thuộc vòng khi tạo object không?** Nếu có, tách một interface/service nền độc lập và hướng dependency một chiều.
3. **Khi chạy, một advice có gọi lại chính điểm bị nó chặn không?** Nếu có, sửa scope/helper/sink, xác định termination và bảo vệ các nghĩa vụ không được phép bỏ.

Sau khi loại vòng, hãy kiểm chứng **tập join point, thứ tự advice, exception, short-circuit, retry, event, concurrency và kết quả nghiệp vụ**. Một sơ đồ dependency sạch mới là điều kiện cần; bài test runtime đúng và bảo toàn an ninh mới chứng minh được kiến trúc phối hợp nhiều aspect đáng tin cậy.
