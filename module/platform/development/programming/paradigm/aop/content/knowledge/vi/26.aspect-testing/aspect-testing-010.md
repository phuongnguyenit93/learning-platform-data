# So sánh hành vi khi bật và tắt một aspect trong AOP

## 1. Bài toán: bật aspect thay đổi điều gì?

Trong lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP), aspect có thể can thiệp vào những join point đã chọn để đo thời gian, ghi log, tạo trace, kiểm tra quyền, cache, retry, quản lý giao dịch hoặc áp dụng một chính sách xuyên suốt. Một phương thức có thể giữ nguyên mã nguồn nhưng biểu hiện khi chạy khác nhau tùy aspect có được gắn và thực thi hay không.

**So sánh hành vi khi bật và tắt aspect** là phép thử để kiểm tra cả hai mặt:

1. **Tính đúng:** aspect có giữ nguyên những kết quả và bất biến bắt buộc của chương trình không?
2. **Tác động có chủ đích:** aspect có tạo đúng khác biệt đã quy định — thêm trace, từ chối quyền, giảm số lần tính toán hoặc thực hiện retry — hay không?

Không có quy tắc chung rằng bật/tắt mọi aspect phải cho kết quả hoàn toàn giống nhau. Đối với aspect chỉ quan sát, **hành vi nghiệp vụ nên tương đương**, trong khi log/metric/trace khác nhau có chủ đích. Đối với aspect kiểm soát quyền hoặc cache, kết quả một vài đường thực thi và số lần gọi target có thể khác theo hợp đồng. Một bài kiểm thử tốt phải xác định trước **cái gì phải giống, cái gì được phép khác và giới hạn sai khác**.

## 2. Ôn lại các thành phần AOP

- **Join point:** vị trí trong luồng chương trình có thể bị can thiệp, chẳng hạn method call hoặc method execution.
- **Pointcut:** biểu thức/rule chọn những join point thuộc phạm vi aspect.
- **Advice:** logic trước, sau hoặc bao quanh join point; around advice có thể quyết định có gọi proceed hay không.
- **Aspect:** tập hợp pointcut và advice cho một mối quan tâm xuyên suốt.
- **Weaving/interception:** cách gắn aspect vào chương trình: có thể là compile-time weaving, load-time weaving hoặc wrapper/proxy theo khả năng của cơ chế cụ thể.
- **Composition root:** nơi chọn implementation và lắp các lớp chính sách để cung cấp một cổng cho caller.

Cần làm rõ chính xác **bật/tắt** được hiểu ra sao:

| Cách tắt | Diễn giải | Giới hạn khi so sánh |
| --- | --- | --- |
| Không weave hoặc không lắp wrapper | Đường gọi thực sự không có advice tương ứng | Có thể dùng làm baseline chưa instrument |
| Advice vẫn có nhưng flag bỏ qua logic | Interception vẫn tồn tại; chỉ một số xử lý được vô hiệu | Không đồng nghĩa với không có overhead |
| Vẫn có advice nhưng tắt collector | Advice vẫn quan sát, bản ghi có thể không được gửi/lưu | Không chứng minh advice đã tắt |
| Dùng một loại build khác | Khác cả quá trình weaving và cấu hình | Cần xác minh hai bản build có cùng code lõi, dependency và data |

Với AOP được weave vào bytecode ở build time, tắt một flag runtime **không tự hoàn nguyên** bytecode. Nếu dùng proxy, gọi thẳng object gốc có thể bỏ qua proxy. Vì vậy, trước khi đánh giá phép thử phải xác định test đang so sánh **hai phiên bản composition** hay chỉ **hai trạng thái của flag**.

## 3. Tiêu chuẩn so sánh theo loại aspect

### 3.1. Aspect quan sát kỹ thuật

Ví dụ: logging, tracing, metrics, đo độ trễ. Bản bật và bản tắt thường phải có cùng:

- Return value và kiểu kết quả theo hợp đồng.
- Null hợp lệ, primitive, void và hành vi ngoại lệ.
- Thứ tự xử lý nghiệp vụ cần thiết.
- Số lần gọi target và số tác dụng phụ thật.
- Trạng thái domain cuối cùng và business event được xác nhận.
- Quyền truy cập vào dữ liệu, kết quả với cùng input/fixture.
- Ngữ nghĩa bất đồng bộ, cancellation và completion.

**Được khác:** lượng log, số span, nhãn metric, bộ đếm nội bộ của recorder và overhead. Đừng đòi hai bản có thời gian chạy bằng nhau; instrumentation vốn tiêu tốn tài nguyên. Nếu collector chỉ best-effort, lỗi collector không được che kết quả hoặc lỗi từ nghiệp vụ.

### 3.2. Aspect kiểm soát truy cập

Bật aspect authorization có thể khiến yêu cầu thiếu quyền bị từ chối trước khi target chạy, trong khi baseline không gắn policy có thể thực thi. Đây là khác biệt có chủ đích trong **fixture kiểm thử cô lập**, không phải lý do để tắt lớp bảo vệ bắt buộc trên hệ thống thực.

Kiểm thử phải phân biệt:

- ALLOW: đúng quyền thì đi vào target và cho kết quả hợp lệ.
- DENY: không đủ quyền thì target được gọi zero lần, lỗi đúng hợp đồng.
- Phạm vi: những entry point bắt buộc phải có enforcement đều thực sự đi qua advice.
- Tính đúng trên từng tài nguyên: quyền tổng quát không thay thế kiểm tra tenant/owner/ACL tại biên giới dữ liệu.

### 3.3. Aspect cache

Khi bật cache, cache hit có thể không gọi target; khi tắt, mỗi yêu cầu có thể thực thi phép tính. Do đó **số lần target chạy không nhất thiết bằng nhau**. Phải so kết quả theo cùng tenant, quyền, phiên bản dữ liệu, khóa cache, TTL và invalidation. Với thao tác có tác dụng phụ, việc bỏ qua target do cache hit có thể vi phạm hợp đồng, cần loại khỏi phạm vi cache hoặc thiết kế lại.

### 3.4. Aspect retry, timeout, transaction và audit

- Retry có thể tạo nhiều attempt, nhưng phải đúng giới hạn và idempotency.
- Timeout có thể phát sinh lỗi có chủ đích khi vượt deadline.
- Transaction có thể thay đổi trạng thái commit/rollback và thời điểm quan sát lỗi.
- Audit bắt buộc có thể là một phần hợp đồng nghiệp vụ chứ không chỉ telemetry best-effort.

Với các policy này, phép thử cần so **điều kiện và tác động cuối**, không chỉ giá trị trả về.

## 4. Differential test: một bộ tình huống, hai chế độ

Mô hình:

~~~text
            Cùng bộ tình huống
                    |
             +------+------+
             |             |
             v             v
        Aspect TẮT    Aspect BẬT
             |             |
          Target        Advice
             |             |
             |          Target
             v             v
      Domain snapshot  Domain snapshot
             |             |
             +------+------+
                    |
             So sánh theo
              hợp đồng
                    |
           So telemetry riêng
~~~

**Domain snapshot** có thể chứa result, exception, số lần cập nhật DB, số business event logic, trạng thái tài nguyên, số lượt gửi lệnh nghiệp vụ. **Technical snapshot** có thể chứa danh sách advice, trace, metric, số attempt và thông tin về overhead.

Để phép thử có ý nghĩa:

1. Dùng **cùng input và policy**: tham số, danh tính, tenant, locale, quyền và version.
2. Dùng **hai fixture trạng thái tương đương nhưng độc lập**; không để mode chạy trước làm thay đổi dữ liệu của mode sau.
3. Cố định những yếu tố phi xác định có thể kiểm soát: clock, random seed, response từ dependency giả, network failure injection.
4. Chọn **tiêu chuẩn so sánh có ý nghĩa** thay vì so toàn bộ log text hoặc timestamp.
5. Chạy cả happy path lẫn exception, null, void, nhiều lượt gọi và đường không match pointcut.
6. Tách so sánh tính đúng và so sánh hiệu năng thành những phép thử riêng.
7. Kiểm cả lời gọi qua interception thực chứ không chỉ gọi trực tiếp code lõi.

Có thể biểu diễn một invariant của aspect chỉ quan sát:

~~~text
businessSnapshot(runWithoutAspect, sameInput)
==
businessSnapshot(runWithAspect, sameInput)

telemetryWithoutAspect != telemetryWithAspect
~~~

Bất biến này **không** áp dụng một cách máy móc cho aspect cố ý chặn lời gọi, cache hoặc retry.

## 5. Ví dụ Java 17 chạy được: bật/tắt aspect trace

Ví dụ dùng **Java dynamic proxy** để mô phỏng một around advice quanh interface method. Trong chế độ tắt, caller nhận trực tiếp Core. Trong chế độ bật, caller nhận proxy do TraceHandler điều khiển, ghi một sự kiện enter và một sự kiện return/throw cho mỗi lời gọi.

**Đặc điểm được kiểm tra:** kiểu int, String bình thường, null hợp lệ, void có side effect, checked IOException, unchecked IllegalArgumentException, số lần gọi target, số lần cập nhật và log quan sát. Đây là minh họa cơ chế interception bằng Java chuẩn; **không khẳng định** mọi cơ chế weaving AOP đều hoạt động giống dynamic proxy.

Tạo tệp **AspectSwitchDemo.java**:

~~~java
import java.io.IOException;
import java.lang.reflect.*;
import java.util.*;

public class AspectSwitchDemo {
    interface Service {
        int calculate(int value);
        String lookup(boolean found);
        void update();
        String checked() throws IOException;
        String invalid();
    }

    static final class Core implements Service {
        final IOException io = new IOException("disk");
        final IllegalArgumentException bad =
                new IllegalArgumentException("bad");
        int calls, updates;

        public int calculate(int value) {
            calls++;
            return value * 2;
        }

        public String lookup(boolean found) {
            calls++;
            return found ? "item" : null;
        }

        public void update() {
            calls++;
            updates++;
        }

        public String checked() throws IOException {
            calls++;
            throw io;
        }

        public String invalid() {
            calls++;
            throw bad;
        }
    }

    static final class TraceHandler implements InvocationHandler {
        final Service target;
        final List<String> events = new ArrayList<>();

        TraceHandler(Service target) { this.target = target; }

        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            events.add("enter:" + method.getName());
            try {
                Object value = method.invoke(target, args);
                String kind = method.getReturnType() == void.class
                        ? "void"
                        : value == null ? "null" : "value";
                events.add("return:" + method.getName() + ":" + kind);
                return value;
            } catch (InvocationTargetException ex) {
                Throwable cause = ex.getCause();
                events.add("throw:" + method.getName() + ":"
                        + cause.getClass().getSimpleName());
                throw cause;
            }
        }
    }

    record Snapshot(List<String> outcomes, int calls, int updates) {}

    static Snapshot exercise(Service port, Core core) {
        List<String> results = new ArrayList<>();
        results.add("int=" + port.calculate(3));
        results.add("null=" + port.lookup(false));
        results.add("value=" + port.lookup(true));
        port.update();
        results.add("void=done");

        try {
            port.checked();
            throw new AssertionError("missing IOException");
        } catch (IOException ex) {
            results.add("checked-same=" + (ex == core.io));
        }
        try {
            port.invalid();
            throw new AssertionError("missing IllegalArgumentException");
        } catch (IllegalArgumentException ex) {
            results.add("runtime-same=" + (ex == core.bad));
        }

        return new Snapshot(
                List.copyOf(results), core.calls, core.updates);
    }

    public static void main(String[] args) {
        Core raw = new Core();
        Core decorated = new Core();
        TraceHandler handler = new TraceHandler(decorated);

        Service wrapped = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[]{Service.class}, handler);

        Snapshot before = exercise(raw, raw);
        Snapshot after = exercise(wrapped, decorated);

        System.out.println("same-behavior=" + before.equals(after));
        System.out.println("calls=" + before.calls() + "/"
                + after.calls());
        System.out.println("updates=" + before.updates() + "/"
                + after.updates());
        System.out.println("without-aspect-traces=0");
        System.out.println("with-aspect-traces="
                + handler.events.size());
        System.out.println("first=" + handler.events.get(0));
        System.out.println("last=" + handler.events.get(
                handler.events.size() - 1));
        System.out.println("outcomes=" + after.outcomes());
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 AspectSwitchDemo.java
java AspectSwitchDemo
~~~

**Stdout chính xác của ví dụ:**

~~~text
same-behavior=true
calls=6/6
updates=1/1
without-aspect-traces=0
with-aspect-traces=12
first=enter:calculate
last=throw:invalid:IllegalArgumentException
outcomes=[int=6, null=null, value=item, void=done, checked-same=true, runtime-same=true]
~~~

Mã ví dụ đã được **biên dịch bằng javac --release 17 và chạy thành công trong môi trường JDK 21**. Kết quả không in số đo thời gian ngẫu nhiên nên có thể đối chiếu chính xác.

### Giải thích

- Snapshot của hai mode có cùng danh sách kết quả, sáu lần gọi target và một lần update. Record so sánh giá trị theo các thành phần và danh sách List.copyOf.
- Giá trị int 6 được proxy trả đúng dù InvocationHandler dùng kiểu Object trung gian.
- lookup(false) trả null bình thường, lookup(true) trả "item"; recorder vẫn phân biệt return:null và return:value.
- update() là void nhưng có tác dụng phụ đúng một lần; interceptor không tự xem void như nullable result.
- IOException và IllegalArgumentException giữ **cùng instance trong từng Core**, do handler unwrap InvocationTargetException rồi ném lại cause.
- Với sáu lượt gọi, mỗi lượt được ghi một enter và một return/throw; vì vậy mode bật có 12 sự kiện kỹ thuật.
- Mode tắt không có TraceHandler; nó không sinh event kỹ thuật từ aspect.

Trong ví dụ hai Core được khởi tạo riêng để không làm lẫn side effect. Danh sách events dùng ArrayList chỉ an toàn trong bài test tuần tự; ứng dụng đồng thời cần collector thread-safe. Proxy chỉ chặn lời gọi đi qua chính proxy, không bao phủ lời gọi trực tiếp vào Core hoặc mọi loại join point.

## 6. Kiểm thử pointcut và khả năng bật/tắt thực tế

**Khác biệt log** chưa chắc chứng minh pointcut đã áp dụng đúng tập join point. Cần những phép thử:

- **Match:** advice chạy tại method/call/execution được quy định.
- **Non-match:** advice không chạy tại những join point nằm ngoài phạm vi.
- **Giới hạn cơ chế:** xác định self-invocation, static method, private method và lời gọi trực tiếp có được interception hay không theo công nghệ weaving đang dùng.
- **Composition:** đối tượng được caller thật nhận là bản đã lắp advice, không phải tham chiếu vô tình tới target gốc.
- **Tắt ở mức nào:** tắt registration, tắt logic advice hay tắt exporter phải được phân biệt trong test.
- **Thứ tự:** khi nhiều aspect cùng áp dụng, kiểm thứ tự enter/exit, nhánh exception và lúc policy được quyết định.
- **Khả năng tái lập:** cùng cấu hình, cùng đầu vào phải cho cùng hành vi logic.

Ví dụ, một phương thức bên trong Core gọi trực tiếp một phương thức khác trên cùng Core có thể bypass dynamic proxy. Nhưng không được áp dụng kết luận ấy cho mọi cơ chế AOP: weaving vào method execution có thể có tập join point khác. Vì thế chỉ kết luận từ cơ chế **được cấu hình và kiểm thử**.

## 7. Kiểm chứng tương đương có điều kiện bằng differential oracle

Bài kiểm thử kiểu trả về, `null` và ngoại lệ đã mô tả các contract theo từng method. Ở đây bài toán khác: **cùng một kịch bản chạy hai chế độ cấu hình**, rồi phân loại sự khác nhau thành **được phép** hoặc **hồi quy**.

Không nên so sánh toàn bộ log hay timestamp bằng chuỗi thô. Thay vào đó, dùng một `Outcome` thử nghiệm ghi nhận các thành phần quan trọng:

| Thuộc tính của phép chạy | Aspect TẮT và BẬT khi chỉ quan sát | Nếu aspect có chủ đích thay hành vi |
| --- | --- | --- |
| Giá trị trả về và runtime type | Tương đương theo contract, có thể cần cùng identity | So theo quy tắc biến đổi được công bố |
| `null`, primitive, `void` | Giữ cùng ngữ nghĩa; không gây lỗi unboxing | Cần từng expected outcome rõ |
| Loại, cause và identity của exception | Không đổi theo hợp đồng observer | Map/wrap lỗi phải được khai báo |
| Số lần target và domain side effects | Cùng số lần nếu observer chỉ quan sát | Cache/retry/guard có thể thay đổi có chủ đích |
| Context, lock, resource còn sống sau scope | Cùng postcondition cleanup | Scope bổ sung phải được dọn và không lộ sang request khác |
| Traces, logs, metrics | Khác nhau **theo đúng sơ đồ event** của observer | So theo riêng từng concern |
| Thời lượng | Không yêu cầu hai số nanosecond bằng nhau | Benchmark overhead trong phép đo riêng |

### 7.1. Chuẩn hóa phép so sánh nhưng không xóa tín hiệu lỗi

Một phép đo thực hành có thể dùng recorder đồng bộ và dữ liệu kịch bản quyết định:

~~~text
for each scenario in [normal, null, primitive, void, checkedError, uncheckedError]:
    off = runWithAspectDisabled(freshFixtureFor(scenario))
    on  = runWithAspectEnabled(freshFixtureFor(scenario))

    assert sameContractualBusinessOutcome(off, on)
    assert sameRequiredDomainEffects(off, on)
    assert on.traceEvents == expectedEventsFor(scenario)
    assert off.traceEvents == []
    assert noLeakedContextOrResources(off, on)
~~~

Đây là **mã giả**: hai fixture phải được dựng độc lập và có cùng trạng thái ban đầu. Nếu chạy OFF rồi ON trên cùng database hoặc đối tượng mutable, phép chạy trước có thể làm thay đổi phép chạy sau; đó là lỗi thiết kế thí nghiệm, không phải lỗi aspect. Nếu mỗi lần cần ID mới, hãy so sánh các thuộc tính nghiệp vụ ổn định hoặc chuẩn hóa chỉ những trường được phép biến đổi — **không loại bỏ toàn bộ difference** chỉ để test pass.

### 7.2. Failure injection là phần bắt buộc của phép đối chiếu

Với một observer best-effort, ép bộ ghi telemetry ném lỗi trong nhánh target trả bình thường, trả `null` và ném ngoại lệ; caller vẫn phải nhận outcome gốc theo policy. Nếu aspect là enforcement hoặc audit bắt buộc, kết quả có thể khác, nhưng **phải có bảng expected và tiêu chí lỗi riêng**, không áp quy tắc “mọi sink failure đều được nuốt”.

Nếu caller nhận `CompletionStage`, hãy phân biệt outcome ở **thời điểm method trả handle** và ở **thời điểm stage hoàn tất**. Phép so sánh khi bật/tắt phải chọn đúng mốc cần quan sát và kiểm tra callback/cleanup ở mốc đó.

### 7.3. Đánh giá đúng mức bằng chứng

Nếu bật aspect khiến event mong đợi xuất hiện nhưng kết quả nghiệp vụ vẫn đúng, điều đó chứng minh một phần semantics, **chưa chứng minh pointcut match đủ mọi đường**. Vẫn cần test positive/negative và weaving thật ở các join point quan trọng. Ngược lại, nếu ON/OFF giống hệt nhau và hoàn toàn không có event ở ON, có thể aspect đã bị tắt hoặc test đi qua raw target — test không được tự tuyên bố “transparent aspect” khi chưa có positive canary.

## 8. Số lần proceed và tác dụng phụ

**Proceed count** là chỉ báo quan trọng nhưng phải diễn giải theo policy:

| Aspect | Khi bật có thể thế nào? | Điều cần kiểm |
| --- | --- | --- |
| Metrics/tracing | Mỗi lời gọi được phép qua target đúng một lần | Không nhân đôi side effect |
| Authorization | Từ chối trước target | Zero proceed khi DENY |
| Cache | Cache hit không cần target | Kết quả đúng key, TTL, tenant, quyền |
| Retry | Có nhiều attempt | Bounded retries, idempotency, kết quả cuối |
| Circuit breaker | Từ chối khi circuit open | Đúng state và exception contract |
| Transaction | Có ranh giới commit/rollback | Dữ liệu lưu bền nhất quán |

Ví dụ một thao tác trừ tồn kho có thể trả cùng kết quả hiển thị nhưng bị gọi hai lần và làm lệch số dư. Vì thế so sánh chỉ return value là không đủ: cần assert trạng thái DB, event nghiệp vụ, số lần phát message và số lần thực thi quan trọng.

Một business event logic không phải một metric invocation: retry có thể có ba attempt nhưng chỉ được tạo một sự kiện nghiệp vụ sau idempotency. Tách hai loại thông tin trong snapshot.

## 9. So sánh khi nhiều aspect phối hợp

Một chuỗi như sau:

~~~text
caller -> Authorization -> Metrics -> Cache -> Core
~~~

có ý nghĩa khác với:

~~~text
caller -> Cache -> Authorization -> Metrics -> Core
~~~

Nếu cache trả kết quả trước authorization mà không có kiểm tra tương đương, một người dùng có thể nhận dữ liệu không được phép qua cache hit. Đồng thời metrics bên ngoài/ở trong cache sẽ đếm số request khác nhau.

Test tổ hợp nên kiểm:

- DENY xảy ra trước khi dữ liệu nhạy cảm được tiết lộ.
- Cache key và policy dùng đúng ngữ cảnh và quyền.
- Tracing ghi một yêu cầu tổng hay từng retry attempt theo thiết kế.
- Retry ở trong hay ngoài transaction, có làm trùng side effect không.
- Exception translation làm thay đổi loại lỗi ở lớp quan sát nào.
- Khi tắt **một** aspect, các aspect còn lại giữ hợp đồng và thứ tự như mong đợi.

Một List<String> trong fixture có thể ghi thứ tự enter/exit của advice để so sánh chính xác, nhưng không nên vô tình ghi token, mật khẩu, thông tin tài khoản hoặc payload nhạy cảm.

## 10. Tác vụ bất đồng bộ và timing

Nếu phương thức trả Future hoặc CompletionStage, bản tắt và bản bật có thể cùng **trả handle thành công** trong khi tác vụ xử lý sau đó thất bại.

Tách hai loại phép thử:

**Return-boundary:** aspect giữ kiểu handle, không gọi join()/get() để ép thành đồng bộ, không thay đổi bất ngờ cancellation hoặc timeout.

**Completion-boundary:** cả hai mode hoàn tất bằng cùng giá trị hợp lệ, null bình thường, exceptional completion hoặc cancellation theo hợp đồng. Callback ghi trace không được làm thất bại stage mà caller sử dụng chỉ vì collector lỗi.

Nếu có đo thời gian, phân biệt submission latency, queue wait, execution duration và end-to-end completion latency. Cùng một lời gọi async có thể có kết quả thời gian khác nhau dù nghiệp vụ giống nhau. Không assert thời gian chính xác hoặc thứ tự callback không được đảm bảo.

## 11. Hiệu năng phải được đo riêng với tính đúng

Bật aspect có thể tăng CPU, allocation, latency, I/O logging và cardinality metric. Một bài test correctness không nên thất bại chỉ vì nanoTime dao động một chút.

Để đánh giá overhead:

- Chạy workload tương đương với cùng dữ liệu, số luồng và cấu hình.
- Warm-up JVM; sử dụng công cụ benchmark và đủ vòng đo thay vì một lần đo đơn lẻ.
- Báo số liệu có phân phối, ví dụ p50/p95/p99 latency, throughput hoặc allocation.
- Tách thay đổi do cache hit/miss, GC, network, collector và việc sampling.
- Xác định overhead budget; không đánh đồng performance với correctness.
- Với retry/cache, cải thiện hoặc giảm hiệu năng có thể là mục đích, nhưng **chỉ có giá trị khi kết quả còn đúng**.

Ví dụ Java trong bài không in duration nên stdout có tính xác định. Khi cần benchmarking, hãy bổ sung phép thử riêng với tiêu chí thống kê phù hợp.

## 12. Ma trận kiểm thử hồi quy

| Nhóm | Tình huống | Điều cần khẳng định |
| --- | --- | --- |
| Happy path | Giá trị trả về hợp lệ | Cùng business output nếu aspect chỉ quan sát |
| Null | Return null | Không bị đổi thành exception |
| Primitive | int/boolean | Không cast/unbox sai |
| Void | Side effect | Đúng số lượt thực thi |
| Checked error | IOException | Type/cause/identity chính xác |
| Unchecked/Error | Exception hoặc Error | Không nuốt lỗi |
| Collector | Sink ném lỗi | Không che kết quả nếu best-effort |
| Pointcut match | Join point nằm trong rule | Advice thật sự chạy |
| Pointcut non-match | Join point ngoài rule | Không can thiệp |
| Self-invocation | Lời gọi nội bộ | Đúng giới hạn interception |
| Authorization | ALLOW / DENY | Policy đúng, không bypass |
| Cache | Hit / miss / invalidation | Không dùng dữ liệu sai ngữ cảnh |
| Retry | 1 lỗi rồi thành công | Attempt count và idempotency đúng |
| Async | Success / null / error / cancel | Quan sát đúng completion |
| Composition | Hai hoặc nhiều aspects | Thứ tự và kết quả hợp đồng đúng |
| Performance | Workload ổn định | Overhead được đo riêng |

## 13. Sai lầm thường gặp

1. **Chỉ nhìn log rồi cho rằng aspect đúng:** log có thể được ghi ở sai join point hoặc target không được gọi.
2. **Dùng cùng fixture mutable cho hai mode liên tiếp:** mode trước ảnh hưởng trạng thái mode sau; phải reset hoặc tạo fixture riêng.
3. **Đòi mọi loại aspect không làm thay đổi call count:** cache/retry/authorization vốn làm thay đổi theo policy.
4. **So output console tuyệt đối:** phần trace/log được phép khác; chỉ so domain snapshot và technical snapshot theo mục đích.
5. **Tắt collector rồi gọi là tắt aspect:** advice vẫn có thể chạy, tốn chi phí hoặc thay đổi hành vi.
6. **Test chỉ thành công bình thường:** bỏ sót null, void, exception, Error, async cancellation.
7. **Chỉ gọi class lõi trong unit test:** không chứng minh pointcut/weaving được lắp đúng.
8. **Không kiểm lỗi từ advice:** metric sink có thể che lỗi nghiệp vụ gốc.
9. **Không xét việc bật aspect bảo mật là bắt buộc:** thử nghiệm tắt enforcement phải nằm trong fixture cô lập, không ảnh hưởng hệ thống thật.
10. **Dùng ngưỡng thời gian quá chặt trong unit test:** gây test không ổn định vì scheduling và GC.

## 14. Checklist thiết kế phép so sánh

1. Xác định mục đích aspect: quan sát hay thay đổi chính sách.
2. Ghi rõ chính xác bật/tắt ở mức weaving, wrapper, advice flag hay collector.
3. Xác định join point, pointcut và đường gọi thực tế.
4. Lập bảng các đại lượng **phải bằng nhau** và **được phép khác**.
5. Tạo hai fixture độc lập nhưng có cùng trạng thái ban đầu.
6. Dùng cùng input và dependency response có thể tái lập.
7. So sánh return, null, void, exception, trạng thái domain và số lần side effect.
8. Xác nhận advice chạy đúng pointcut và không chạy ngoài phạm vi.
9. Kiểm proceed count, transaction, cache và retry theo policy.
10. Thử collector failure, cancellation, concurrency và các đường lỗi.
11. Kiểm tích hợp composition/weaving thật.
12. Đo overhead riêng; đưa kiểm thử hồi quy vào build/CI.

**Kết luận:** Bật/tắt một aspect là phép thử về **hợp đồng thực thi**. Với aspect quan sát, giá trị nghiệp vụ và tác dụng phụ nên tương đương, chỉ dữ liệu quan sát khác theo thiết kế. Với aspect chính sách, khác biệt phải được giải thích bằng chính sách và kiểm chứng bằng trạng thái cuối, lỗi, quyền và số lượt gọi. Kết hợp differential test, kiểm thử pointcut và kiểm thử tích hợp là cách phát hiện những thay đổi hành vi âm thầm do AOP gây ra.
