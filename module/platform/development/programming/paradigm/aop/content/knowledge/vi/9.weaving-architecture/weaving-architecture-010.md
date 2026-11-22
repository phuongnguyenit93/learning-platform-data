# Dệt lặp và phát hiện hành vi bị chèn nhiều lần

## 1. Bài toán và phạm vi

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), **pointcut** chọn những *join point* có thể can thiệp, còn **advice** thực hiện hành vi bổ sung tại các điểm ấy. **Weaving** là quá trình kết hợp aspect với chương trình mục tiêu để advice có thể chạy tại join point được chọn. Ngoài weaving trong hoặc sau build, hoặc lúc nạp class, ứng dụng còn có thể dùng **proxy/interceptor** định tuyến lời gọi qua một lớp trung gian lúc runtime.

**Dệt lặp** là tình huống một quá trình weaving được áp dụng trở lại lên mã/artifact nằm trong phạm vi đã được xử lý trước đó. Nếu quy trình không được kiểm soát, cùng một hành vi cắt ngang có thể xuất hiện **hai lần hoặc nhiều lần trên một đường thực thi**. Tuy nhiên, không có quy tắc chung rằng chạy weaver hai lần nhất định sẽ chèn gấp đôi advice: một số công cụ nhận diện, từ chối, bỏ qua hoặc có quy tắc riêng với class đã được dệt.

Tương tự, **duplicate advice execution** (hành vi advice chạy trùng) **không tự chứng minh có double bytecode weaving**. Hai proxy cùng ghi trace, hai pointcut giao nhau, một method call cộng một method execution, hoặc event được gửi hai lần qua sink có thể cùng tạo triệu chứng “hai dòng log”.

Mục tiêu của bài là:

1. Phân biệt **dệt lặp thực sự**, **bọc trùng bằng proxy**, **nhiều advice hợp lệ**, **retry/recursion**, và **phân phối sự kiện trùng**.
2. Nhận biết tại tầng nào sinh ra nhiều hành vi hơn kỳ vọng.
3. Giữ riêng **số lần advice chạy** và **số lần nghiệp vụ thật sự chạy**.
4. Thiết kế pipeline weaving, registration và pointcut có thể kiểm soát.
5. Xây phép kiểm thử ngăn lỗi tái phát mà không xóa nhầm advice hợp lệ.

Một ví dụ nguy hiểm: audit được thiết kế ghi **một sự kiện cho mỗi lần đặt hàng**, nhưng vì cùng bộ audit được áp hai lần, một lần mua tạo hai dòng sự kiện. Với logic **retry**, vấn đề còn nghiêm trọng hơn: nếu tầng retry cũng bị cài trùng, nghiệp vụ có thể chạy nhiều lần. Đây là hai loại lỗi cần phân tích riêng.

## 2. Thuật ngữ quan trọng

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Join point** | Một vị trí/sự kiện mà mô hình AOP có thể can thiệp, ví dụ call hoặc execution |
| **Pointcut** | Quy tắc chọn tập join point |
| **Advice** | Hành vi được thực hiện tại điểm được chọn |
| **Weaver** | Thành phần kết hợp aspect vào chương trình, thường qua biến đổi mã/bytecode |
| **Woven artifact** | Class/JAR/binary đã qua quá trình dệt |
| **Repeated weaving** | Dệt lại artifact hoặc phạm vi đã được xử lý |
| **Duplicate advice** | Cùng hành vi cắt ngang chạy nhiều lần ngoài hợp đồng |
| **Proxy/interceptor** | Đối tượng/trình xử lý đứng trên đường gọi và chuyển tiếp tới target |
| **Instrumentation** | Cơ chế chèn hoặc kích hoạt khả năng quan sát/can thiệp |
| **Idempotence** | Áp dụng nhiều lần cho hiệu quả tương đương áp dụng một lần theo tiêu chí đã định |
| **Deduplication** | Loại trừ phần tử bị coi là trùng theo định danh và hợp đồng cụ thể |

Phải luôn ghi rõ **“trùng theo đơn vị nào?”** Một lời gọi API có thể chứa nhiều lần gọi method, nhiều join point, nhiều attempts và nhiều events. Nếu chưa xác định đơn vị quan sát, kết luận “chạy trùng” rất dễ sai.

## 3. Dệt lặp trong build pipeline

Một pipeline dễ gặp lỗi:

~~~text
Source + aspect definitions
          |
          v
     Weaver pass #1
          |
          v
     Woven classes
          |
          v
    Package / plugin
          |
          v
     Weaver pass #2
          |
          v
      Deploy / run
~~~

Nếu pass #2 được cung cấp **artifact đã dệt** như thể đó là artifact gốc, hậu quả tùy năng lực và cấu hình weaver. Có thể công cụ phát hiện marker và bỏ qua; có thể nó báo lỗi; cũng có thể pipeline vô ý tạo hành vi được cài nhiều lần.

Những dấu hiệu nên kiểm tra:

- Build đã dệt lúc compile, bước packaging lại áp binary weaving lên cùng output.
- Module con xuất bản class đã dệt, module tổng hợp lại xử lý chính class đó.
- Build cache lưu **woven output** ở đường dẫn mà job sau tưởng là **raw output**.
- Class được dệt trước khi đóng JAR, sau đó deployment pipeline cũng dệt.
- Có hai plugin/agent độc lập cùng cài một chính sách trên cùng ranh giới.

**Phòng ngừa:** phân định rõ thư mục/artifact nguồn chưa dệt và output đã dệt; chỉ định một chủ sở hữu bước weaving; dùng build tái lập; ghi version công cụ, input và output; kiểm thử artifact phát hành chứ không chỉ source.

**Lưu ý về hash:** checksum thay đổi chưa chứng minh double weaving, vì thay đổi metadata, timestamps hoặc compiler cũng có thể thay file. Hãy kết hợp provenance của pipeline, phân tích class và phép đếm runtime.

## 4. Compile-time, binary, load-time và runtime không cùng một loại rủi ro

| Kiểu áp dụng | Thời điểm | Nguồn chồng lấn tiêu biểu | Cách kiểm |
| --- | --- | --- | --- |
| **Compile-time weaving** | Trong build/compile | Dệt tiếp khi package | Đối chiếu output sau build với input |
| **Binary/post-compile weaving** | Sau biên dịch, trước chạy | Dệt lại JAR đã dệt | Kiểm soát nguồn class và các bước pipeline |
| **Load-time weaving** | Khi JVM định nghĩa class | Artifact đã woven lại qua transformer | Kiểm tra cấu hình load/classloader/transformer |
| **Retransformation/redefinition** | Class đã nạp, khi công cụ/JVM hỗ trợ | Nhiều transformer/cơ chế instrument tương tự | Theo dõi class definitions, transformer chain |
| **Runtime proxy/interceptor** | Khi lời gọi đi qua wrapper | Proxy lồng proxy hoặc handler đăng ký hai lần | Kiểm tra object graph và chuỗi interceptor |

**Load-time weaving không đồng nghĩa runtime proxy.** LTW thường biến đổi bytecode khi class được định nghĩa, còn proxy có thể can thiệp mà không sửa bytecode target. Hai cơ chế ấy có thể cùng tồn tại và tạo hai lớp hành vi trên cùng operation.

Một class đã được woven ở build có thể được load bình thường. Nếu còn một agent instrument class ở load-time, cần xác định rõ agent đó có định nghĩa điểm can thiệp chồng lấn với mã đã dệt không.

Không được khẳng định **mọi lần retransformation tự động xếp thêm advice lên bytecode lần trước**. Quy tắc transformer, bytecode được JVM cung cấp khi retransformation, và các thay đổi được phép phụ thuộc hợp đồng Java Instrumentation cùng triển khai công cụ. Muốn biết có chèn trùng hay không phải **quan sát bytecode hoặc số handler thực tế**, không đoán theo số lần yêu cầu retransform.

## 5. Double instrumentation dù không có double weaving

Một tình huống khác:

~~~text
Caller
  |
  v
Proxy AUDIT
  |
  v
Woven target AUDIT
  |
  v
Business execution
~~~

Nếu cả hai tầng đều ghi **cùng một logical audit event**, một lời gọi caller có thể dẫn tới hai events. Nhưng có thể hệ thống cố ý có:

- Audit tại **API call boundary**.
- Audit tại **method execution** bên trong.
- Metrics ở mỗi attempt do retry.
- Trace span ở cả request cấp cao và hoạt động con.

Chúng chỉ là lỗi khi **vi phạm hợp đồng số lần và ngữ nghĩa**. Đừng tắt một tầng chỉ vì thấy hai thông báo trông giống nhau; trước hết phải nhận diện **aspect ID, advice ID, join point kind, operation ID, phase** và **business execution count**.

## 6. Proxy bị bọc hai lần: ca dễ kiểm chứng

Khi một factory bọc cùng hành vi qua hai lần:

~~~text
raw = Business()
p1  = trace(raw)
p2  = trace(p1)

caller -> p2 -> p1 -> raw
~~~

Nếu mỗi proxy chuyển tiếp một lần:

~~~text
TRACE before (outer)
TRACE before (inner)
BUSINESS execute
TRACE after  (inner)
TRACE after  (outer)
~~~

Một **business execution** nhưng **hai lần advice entry**. Điều này có thể làm audit và metrics sai mà không làm tăng số lượng transaction.

Cơ chế phòng ngừa hợp lý là **idempotent registration**: biết một đối tượng đã chứa **chính xác cùng chính sách instrumentation** hay chưa. Tuy nhiên, không được cấm mọi trường hợp proxy lồng nhau — các tầng security, tracing và caching khác trách nhiệm là hoàn toàn hợp lệ.

Một lỗi hay gặp là xây một lớp `proxy factory` nhiều lần ở hai tầng hệ thống mà mỗi lần factory không biết ai đã áp chính sách trước đó. Tốt hơn nên có **một nơi chịu trách nhiệm lắp interceptor chain**, có contract và phép kiểm đếm.

## 7. Pointcut giao nhau và nhiều advice cùng khớp

Ví dụ mô tả:

~~~text
P1 = publicApiOperations
P2 = annotatedAuditedOperations

operationX vừa public vừa annotated
=> P1 match và P2 match
~~~

Nếu cả hai advice đều ghi một event `ORDER_SUCCESS` theo cùng policy, có thể xảy ra duplicate logical event, dù mỗi advice được dệt **đúng một lần**.

Nếu mục tiêu muốn hai tập không trùng, có thể mô tả (pseudocode, không phải cú pháp chung của mọi engine):

~~~text
regularAudit = P1 AND NOT P2
criticalAudit = P2
~~~

Cách này chỉ phù hợp nếu bộ lọc thực sự có nghĩa và engine hỗ trợ các phép ghép. Một giải pháp khác là **một named pointcut chung và một handler audit duy nhất**, trong khi những advice khác như metrics, tracing vẫn có thể dùng tập điểm tương tự nhưng thực hiện mục tiêu khác.

Một điều cần nhớ: một named pointcut được nhiều advice tham chiếu **không tự khiến các advice bị gộp**. Nếu hai advice khác nhau cùng khớp, chúng có thể đều chạy như thiết kế.

## 8. Vì sao hai dòng log chưa chứng minh dệt lặp?

| Hiện tượng | Vì sao thấy nhiều sự kiện? | Dấu hiệu phân biệt |
| --- | --- | --- |
| Before và after | Một lời gọi có hai phase | Phase khác nhau |
| Method call và execution | Hai join point hợp lệ | Kind khác nhau |
| Nested call | Parent gọi child đều khớp | Parent/child invocation |
| Recursion | Phương thức chạy ở nhiều cấp | Depth/call ID khác |
| Retry | Business chạy nhiều attempt | Attempt number tăng |
| Hai aspect khác mục đích | Audit, metrics, trace cùng ghi log | Advice identity khác |
| Bridge/synthetic method | JVM có nhiều method bodies trong chuỗi gọi | Signature/bridge flag |
| Hai classloader | Hai runtime classes cùng binary name | Loader identity khác |
| Event gửi lại | Một event qua queue/exporter nhiều lần | Event ID trùng, advice entry không tăng |
| Log appender trùng | Một log record được xuất hai sink | Một log source, hai output |
| Advice bọc proxy lặp | Một target, nhiều tầng cùng handler | Advice count tăng, target count không tăng |

**Nguyên tắc chẩn đoán:** cần nhiều số đếm độc lập, không chỉ lượng dữ liệu xuất hiện trong dashboard.

## 9. Bốn tầng cần đếm và liên kết

Để phân biệt đúng, định nghĩa tối thiểu:

1. **Logical operation:** một yêu cầu nghiệp vụ end-to-end.
2. **Invocation/attempt:** một lần thực hiện một lời gọi cụ thể hoặc một lần retry.
3. **Advice entry:** một lần một advice thực sự được kích hoạt.
4. **Event delivery:** một sự kiện được tạo, gửi, lưu hoặc xuất ra dashboard.

Cùng một logical order có thể có một invocation, hai advice entries và một business execution. Hoặc có hai invocations vì retry, hai business executions, và số advice entries tùy vị trí của advice trong chuỗi wrapper.

Một bộ log chẩn đoán có kiểm soát có thể chứa:

| Trường | Mục đích |
| --- | --- |
| `logicalOperationId` | Xác định yêu cầu nghiệp vụ |
| `invocationId` / `attempt` | Xác định lời gọi hoặc lượt thử |
| `aspectId` / `adviceId` | Xác định hành vi được cài |
| `joinPointKind` | Call, execution, constructor, v.v. |
| `methodSignature` | Phân biệt overload |
| `phase` | BEFORE, RETURNING, THROWING, FINALLY |
| `parentSpanId` | Biết một event nằm trong lời gọi cha nào |
| `instrumentationLayer` | Proxy, woven artifact, agent |
| `classloaderIdentity` | Biết class bản nào được thực thi |
| `artifactVersion` | Đối chiếu đúng bản build |
| `eventId` | Phân biệt event nhân bản từ transport |

Không phải mọi engine cung cấp đủ metadata. Các ID phục vụ quan sát nên là **ID kỹ thuật không nhạy cảm**; không đưa mật khẩu, token, thông tin cá nhân hoặc toàn bộ payload vào nhãn metric.

## 10. Ví dụ Java 17: chứng minh advice chạy hai lần nhưng nghiệp vụ một lần

Ví dụ độc lập dùng **JDK dynamic proxy** và `AtomicInteger`. Đây là cách mô phỏng **double interception**, **không phải bộ bytecode weaver**.

- `wrap(wrap(raw, stats), stats)` bọc target hai lần bằng cùng `TraceHandler`.
- `wrapOnce` tránh lặp khi **proxy ngoài cùng** đã mang `TraceHandler` của ví dụ.
- So sánh `adviceEntries` và `Core.calls` cho biết chính xác hai hiện tượng.
- Ngoại lệ từ target được bóc khỏi `InvocationTargetException` rồi ném lại.

Tạo file `DuplicateAdviceDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicInteger;

public final class DuplicateAdviceDemo {
    interface Work {
        String execute(String id);
    }

    static final class Core implements Work {
        final AtomicInteger calls = new AtomicInteger();

        @Override
        public String execute(String id) {
            calls.incrementAndGet();
            System.out.println("BUSINESS execute " + id);
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("invalid id");
            }
            return "ok:" + id;
        }
    }

    static final class Stats {
        final AtomicInteger adviceEntries = new AtomicInteger();
    }

    static final class TraceHandler implements InvocationHandler {
        final Work target;
        final Stats stats;

        TraceHandler(Work target, Stats stats) {
            this.target = target;
            this.stats = stats;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            stats.adviceEntries.incrementAndGet();
            System.out.println("TRACE before " + method.getName());
            try {
                Object result = method.invoke(target, args);
                System.out.println("TRACE returning " + method.getName());
                return result;
            } catch (InvocationTargetException wrapped) {
                Throwable original = wrapped.getCause();
                System.out.println("TRACE throwing "
                        + original.getClass().getSimpleName());
                throw original;
            }
        }
    }

    static Work wrap(Work target, Stats stats) {
        return (Work) Proxy.newProxyInstance(
                Work.class.getClassLoader(),
                new Class<?>[]{Work.class},
                new TraceHandler(target, stats));
    }

    static Work wrapOnce(Work target, Stats stats) {
        if (Proxy.isProxyClass(target.getClass())
                && Proxy.getInvocationHandler(target) instanceof TraceHandler) {
            return target;
        }
        return wrap(target, stats);
    }

    public static void main(String[] args) {
        Core raw = new Core();
        Stats duplicateStats = new Stats();
        Work duplicated = wrap(wrap(raw, duplicateStats), duplicateStats);

        System.out.println("DOUBLE_RESULT " + duplicated.execute("A"));
        System.out.println("DOUBLE_COUNTS advice="
                + duplicateStats.adviceEntries.get()
                + " business=" + raw.calls.get());

        Core protectedCore = new Core();
        Stats protectedStats = new Stats();
        Work first = wrapOnce(protectedCore, protectedStats);
        Work second = wrapOnce(first, protectedStats);
        System.out.println("SAME_PROXY " + (first == second));
        System.out.println("ONCE_RESULT " + second.execute("B"));
        try {
            second.execute("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        System.out.println("ONCE_COUNTS advice="
                + protectedStats.adviceEntries.get()
                + " business=" + protectedCore.calls.get());
    }
}
~~~

Biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac --release 17 -encoding UTF-8 DuplicateAdviceDemo.java
java DuplicateAdviceDemo
~~~

Stdout đã xác minh bằng chạy thực:

~~~text
TRACE before execute
TRACE before execute
BUSINESS execute A
TRACE returning execute
TRACE returning execute
DOUBLE_RESULT ok:A
DOUBLE_COUNTS advice=2 business=1
SAME_PROXY true
TRACE before execute
BUSINESS execute B
TRACE returning execute
ONCE_RESULT ok:B
TRACE before execute
BUSINESS execute bad
TRACE throwing IllegalArgumentException
CALLER invalid id
ONCE_COUNTS advice=2 business=2
~~~

### 10.1. Vì sao `DOUBLE_COUNTS advice=2 business=1`?

Lần gọi `duplicated.execute("A")` đi qua proxy ngoài, proxy trong, rồi mới đến Core. Hai `TraceHandler` đều tăng counter, còn `Core.execute()` chỉ chạy một lần vì mỗi handler gọi target đúng một lần.

Trong bài toán audit, hai `TRACE before` có thể là sai vì cùng một logical event phát hai lần; nhưng **business call count** không nhân đôi. Nếu một `around` khác cố ý retry, ta sẽ phải kiểm thêm số lần `proceed`, vì target có thể chạy lại.

### 10.2. Ý nghĩa của `SAME_PROXY true`

`wrapOnce` nhận dạng proxy **ngoài cùng** do `TraceHandler` của ví dụ tạo nên không tạo thêm wrapper. Hai lượt gọi khác nhau — `execute("B")` và `execute("bad")` — có **hai advice entries và hai business invocations**, đúng mỗi lần một entry.

Nhưng `wrapOnce` **không phải giải pháp phát hiện weaving phổ quát**:

- Nó không phát hiện bytecode đã được dệt.
- Nó không nhìn xuyên một proxy handler loại khác để biết có `TraceHandler` bên trong.
- Hai handler cùng class có thể có **cấu hình nghiệp vụ khác nhau**, nên không nhất thiết trùng.
- Một thư viện proxy khác có thể không sử dụng JDK `Proxy`.
- Class đã được instrument ở load-time cũng không được nhận diện từ kiểu proxy ngoài cùng.

Bài học là **kiểm soát tầng registration và policy identity**, không chỉ dùng `instanceof` để quyết định mọi trường hợp.

### 10.3. Lỗi và hợp đồng caller

`execute("bad")` ném `IllegalArgumentException`. Reflection `Method.invoke()` bọc nguyên nhân trong `InvocationTargetException`; handler bóc `getCause()` và ném lại ngoại lệ gốc. Việc chống instrumentation lặp **không được tự đổi loại lỗi, giá trị trả về hoặc số lần nghiệp vụ**.

## 11. Cơ chế phòng ngừa repeated weaving

Các chiến lược cần chọn theo kiến trúc:

| Chiến lược | Áp dụng ở đâu | Lưu ý |
| --- | --- | --- |
| **Một điểm ownership** | Build/registration | Chỉ một bước có trách nhiệm cho mỗi phạm vi |
| **Separate raw và woven artifacts** | Build pipeline | Không dùng output đã dệt làm input raw |
| **Clean, reproducible build** | CI | Kiểm soát cache và artifact provenance |
| **Weaver marker nếu được hỗ trợ** | Bytecode/build | Marker phải có ngữ nghĩa version/policy rõ |
| **Idempotent registration** | Proxy factory | Không thêm cùng handler/policy hai lần |
| **Mutually exclusive pointcuts** | Aspect definition | Tránh hai policy cùng tạo một event |
| **Behavior contract test** | Integration test | Đếm advice và target độc lập |
| **Event-level idempotency key** | Event sink | Bảo vệ transport at-least-once, không sửa bytecode |
| **Instrumentation inventory** | Production observability | Biết class/agent/proxy nào đang hoạt động |

### Marker có thể sai ở đâu?

Một weaver có thể đặt metadata “đã xử lý”. Nhưng marker chỉ hữu ích khi công cụ xác định rõ:

- Nó đại diện cho **weaver version** nào?
- Nó bao phủ toàn class hay chỉ một tập join point?
- Khi pointcut thay đổi, class có được dệt bổ sung không?
- Nếu pass đầu tiên thất bại giữa chừng, marker có phản ánh trạng thái không?
- Nếu agent khác chèn instrumentation, marker có phát hiện được không?
- Khi class được load từ classloader khác, identity có còn phù hợp không?

**Idempotent weaving là hợp đồng cần kiểm thử**, không phải thuộc tính tự nhiên của mọi class file. Không thêm marker bytecode thủ công nếu chưa biết engine và verifier chấp nhận.

## 12. Load-time weaving, retransformation và đăng ký transformer

Một hệ thống dùng Java agent có thể đăng ký một hoặc nhiều `ClassFileTransformer`. Trong quá trình class loading hoặc một số hoạt động retransformation/redefinition, các transformer được áp dụng theo quy tắc của Java Instrumentation.

Rủi ro cần kiểm tra:

1. Cùng transformer được đăng ký nhiều lần ngoài dự định.
2. Hai agent khác nhau instrument cùng bytecode với **chính sách trùng**.
3. Class đã qua build-time weaving nhưng vẫn bị runtime transformer instrument.
4. Pipeline transformer có nhiều bước cùng chèn một đoạn đo/audit.
5. Cache trạng thái theo **class name** nhưng không phân biệt classloader.
6. Cơ chế reload/retransform không cập nhật policy theo điều nhóm vận hành tin tưởng.

Cần đặc biệt tránh phát biểu: “gọi retransform N lần nghĩa là advice bị xếp N lớp.” Điều này **không mặc định đúng** vì bytecode nguồn và thứ tự áp dụng transformer trong retransformation có contract riêng. Muốn kết luận phải kiểm tra transformer count, class bytes tương ứng và số lần advice entry thật trong môi trường có kiểm soát.

## 13. Bridge, synthetic method và gọi lồng

Java compiler có thể sinh **bridge method** để hỗ trợ generic erasure và covariant return. Ví dụ:

~~~java
class Parent<T> {
    T value() { return null; }
}

class Child extends Parent<String> {
    @Override
    String value() { return "x"; }
}
~~~

Đây là đoạn minh họa Java, không phải chương trình độc lập có `main`. Một compiler có thể sinh method bridge bên cạnh implementation. Nếu cả bridge và implementation đều là execution join points được pointcut chọn, cùng một đường gọi có thể kích hoạt advice ở **hai method khác nhau** mà **không có class nào được dệt hai lần**.

Khi nghi ngờ, kiểm tra:

- `Method.isBridge()`, `Method.isSynthetic()`.
- Method descriptor và declaring type, không chỉ method name.
- Mô hình join point: method call, execution hay cả hai?
- Đường gọi bridge tới implementation.
- Quy tắc công cụ để bỏ qua/gom các method synthetic.
- Số event kỳ vọng theo **JVM method execution** hay **logical Java API call**.

Tương tự, đệ quy và self-invocation có thể tạo nhiều executions hợp lệ. Nếu dùng proxy ngoài, self-invocation có thể bypass proxy; nếu class đã bytecode woven tại execution join point, các lần gọi nội bộ có thể được quan sát. Đây là **khác biệt độ phủ**, không tự phải lỗi dệt lặp.

## 14. Retry, proceed và số lần target thực thi

Trong AOP, một **around advice** có thể điều khiển `proceed` tùy chính sách. Với retry hợp lệ:

~~~text
Caller
  |
RetryAdvice
  +--> proceed attempt #1 -> error
  +--> proceed attempt #2 -> success
  |
result
~~~

Nếu timer/audit nằm **trong** retry, chúng có thể chạy ở mỗi attempt; nếu nằm **ngoài**, chúng có thể chỉ chạy một lần cho toàn request. Đây là hệ quả vị trí advice, không nhất thiết do dệt trùng.

Một lỗi khác nghiêm trọng là một around advice **vô tình gọi `proceed` hai lần** dù không có retry policy. Lúc đó business execution count cũng có thể nhân đôi. Chẩn đoán cần phân biệt:

- **Double advice wrapping:** advice=2, target=1.
- **Proceed gọi lặp:** target có thể =2.
- **Retry theo hợp đồng:** target=2 hoặc hơn, attempt ID khác.
- **Redelivery ở queue:** logical operation/event id có thể lặp ngoài ranh giới method.

Đừng khắc phục bằng cách chỉ lọc log trùng ở cuối hệ thống nếu side effect nghiệp vụ đã xảy ra nhiều lần.

## 15. Nhiều classloader và nhiều version

Trong JVM, class identity không chỉ là tên đầy đủ mà còn liên quan đến **classloader định nghĩa**. Hai class có cùng binary name nhưng được nạp bởi hai loaders có thể là hai runtime classes riêng.

Một cache instrumentation dùng duy nhất `"com.example.Service"` làm key có thể:

- Bỏ qua classloader thứ hai vì class cùng tên ở loader thứ nhất đã được đánh dấu.
- Báo sai “đã dệt trùng” dù thực tế là hai class khác nhau.
- Đọc nhầm phiên bản bytecode hoặc agent policy.
- Giữ tham chiếu mạnh tới loader cũ, gây rò rỉ bộ nhớ sau reload.

Một công cụ chẩn đoán nên quan sát **classloader identity, module, code source và artifact version** khi cần. Tuy nhiên, đừng đưa mọi thông tin này thành nhãn metric có cardinality vô hạn; lưu ở trace/debug có kiểm soát.

## 16. Phân biệt duplicate advice với duplicate delivery

Giả sử chỉ có một advice entry:

~~~text
Advice -> Event E-42 -> Queue -> Consumer #1
                             -> redelivery -> Consumer #1 again
~~~

Dashboard hoặc DB có thể chứa hai record `E-42` dù advice chỉ chạy một lần. Lỗi ở **delivery/consumer** chứ không phải weaving. Một hệ thống at-least-once có thể cần **idempotency key** tại consumer/sink, nhưng cách xử lý ấy **không giải quyết** trường hợp advice bị bọc hai lần trước khi event được tạo.

Ngược lại, nếu hai advice entries tạo hai event IDs khác nhau mà mang cùng một logical audit meaning, key event ID đơn thuần sẽ không phát hiện semantic duplication. Có thể cần một khóa chính sách như `(logicalOperationId, eventType, phase)` theo hợp đồng nghiệp vụ.

Tuy nhiên, không được dedup một cách mù quáng theo `methodName` hoặc timestamp: hai lời gọi đồng thời hợp lệ có thể có cùng tên hoặc xảy ra trong cùng milli giây.

## 17. Quy trình chẩn đoán thực tế

**Bước 1 — Đặt hợp đồng rõ:** ví dụ “một `AuditOrderCompleted` cho mỗi logical order thành công”, “một timer cho mỗi attempt” hoặc “một trace span cho mỗi method execution”.

**Bước 2 — Tạo ca tối thiểu:** một method, input xác định, không retry/async nếu đang tìm trùng instrumentation, kết quả và exception rõ.

**Bước 3 — Đếm độc lập:** mỗi aspect/advice entry, mỗi target execution, event được tạo, event đến sink. Không suy diễn từ log.

**Bước 4 — Xác minh join point:** call hay execution? Có bridge/synthetic? Overload? Các method lồng nhau? Pointcut chồng lấn?

**Bước 5 — Liệt kê mọi tầng instrumentation:** compile-time/binary weaving, LTW agent, retransformation, proxy factories và interceptors.

**Bước 6 — Kiểm tra artifact và class đã load:** cùng class file có đi qua hai bước build không, có marker của weaver không, classloader nào đang dùng, version nào được deploy?

**Bước 7 — Cô lập trong môi trường kiểm thử:** chỉ proxy, chỉ bytecode weaving, chỉ agent, rồi kết hợp để xác định tầng tạo duplicate. Không vô hiệu hóa bảo vệ hoặc audit bắt buộc trên production chỉ để thử.

**Bước 8 — Sửa nơi phát sinh:** build lỗi thì sửa pipeline; proxy bọc trùng thì sửa registration; pointcut giao nhau thì sửa ownership; delivery trùng thì sửa consumer/idempotency.

**Bước 9 — Regression test:** sau sửa, xác nhận đúng một policy application theo contract và return/exception/target call count vẫn đúng.

## 18. Bảng test tối thiểu

| Trường hợp | Kỳ vọng |
| --- | --- |
| Build sạch và weaving một lần | Một policy application trên join point dự kiến |
| Thử weaving lại cùng artifact | Công cụ xử lý rõ, không âm thầm tạo duplicate behavior |
| Proxy chỉ bọc một lần | Một advice entry cho một lời gọi |
| Proxy vô tình bọc hai lần | Test phát hiện `advice=2, business=1` |
| Idempotent registration trong ví dụ | Trả cùng proxy và không bọc thêm |
| Hai pointcut giao nhau | Test đúng hai policies nếu có chủ đích |
| Call + execution join point | Phân biệt kind và scope |
| Bridge/synthetic method | Kiểm tra ngữ nghĩa khi method chuyển tiếp |
| Retry | Đếm theo attempt, không nhầm với double weaving |
| Target ném ngoại lệ | Lỗi gốc được giữ nguyên |
| Target gọi trực tiếp bỏ qua proxy | Không kỳ vọng proxy advice nếu không có tầng khác |
| Load-time agent + artifact woven | Kiểm tra chồng lấn thực tế |
| Hai classloader | Không nhầm cùng tên thành cùng class |
| Queue redelivery | Nhận diện bằng event ID/sink, không đổ lỗi cho advice |
| Concurrent calls | Counts thread-safe và IDs phân biệt invocation |

Ví dụ assertion độc lập:

~~~text
given: one selected invocation, no retry
when:  instrumented.execute("A")
then:
    auditEntries == 1
    businessExecutions == 1
    callerResult == "ok:A"
~~~

Đây là pseudocode để mô tả hợp đồng. Nếu hai advice hợp lệ cùng khớp, hãy giữ hai counter theo **policy identity**, không gộp chúng vào một con số rồi mặc định một trong hai là lỗi.

## 19. Những cách sửa sai dễ gây hậu quả

- **Cờ `static boolean alreadyRan`:** sau lần gọi đầu, mọi lời gọi sau có thể bị bỏ qua; còn có race giữa threads.
- **`ThreadLocal` guard không cleanup:** trạng thái rò sang request sau trong thread pool. Nếu có guard, phải khôi phục trong `finally` và phân biệt nested calls.
- **Loại mọi proxy thứ hai:** có thể bỏ mất security/caching/tracing hợp lệ.
- **Dedup theo method name:** overload có chữ ký khác nhau, đồng thời các lần gọi độc lập cũng có cùng tên.
- **Dedup theo timestamp:** trùng thời gian không chứng minh trùng invocation.
- **Chỉ dedup ở log sink:** side effect của advice vẫn chạy hai lần trước khi vào sink.
- **Giữ marker không có version:** thay đổi pointcut có thể bị bỏ qua sai hoặc class chỉ được instrument một phần.
- **Cho rằng agent đã khởi động nghĩa là mọi class đều đã weaving:** classloader, thứ tự nạp lớp, phạm vi và transformer capability có thể giới hạn.
- **Tắt một advice mà chưa xem precedence:** có thể làm mất cả audit của denial hoặc metrics ở nhánh exception.
- **Sửa retry bằng cách bỏ mọi lời gọi lặp:** có thể phá chính sách khôi phục vốn được thiết kế và kiểm thử.
- **Log toàn bộ args/return để tìm trùng:** rò dữ liệu, overhead và nhãn có độ phân biệt quá lớn.

## 20. Nâng cao: tính idempotent đúng tầng

Cần phân biệt ba hợp đồng idempotence:

1. **Build idempotence:** chạy pipeline build/weaving lại với cùng đầu vào phù hợp tạo artifact có behavior tương đương, không chèn trùng ngoài ý định.
2. **Instrumentation registration idempotence:** đăng ký cùng handler/policy nhiều lần không tạo thêm lớp tương đương.
3. **Event processing idempotence:** xử lý cùng event nhiều lần không tạo thêm tác dụng phụ bên lưu trữ ngoài hợp đồng.

Ba tầng này **không thay thế nhau**. Một sink dedup hoàn hảo không loại bỏ overhead của hai advice ở đầu nguồn. Một factory `wrapOnce` không phát hiện class woven trùng ở bytecode. Một weaver có marker không ngăn event bị queue redeliver.

Khi định danh chính sách, có thể thiết kế một khóa theo `(instrumentationId, policyVersion, joinPointIdentity)` cho phạm vi static, cộng `invocationId` hoặc `logicalOperationId` khi đo runtime. Khóa cụ thể tùy hợp đồng: event `before` và `after` khác phase không được xóa nhầm; hai attempts retry có thể cần được giữ riêng.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Một method in hai dòng TRACE có chứng minh nó bị dệt bytecode hai lần không?  
**Trả lời:** Không. Có thể là hai proxy, hai advice, nhiều join points hoặc trùng ở sink. Phải đo riêng advice entries và target invocations, đồng thời kiểm tra cơ chế instrumentation.

**Câu 2.** Hai proxy cùng ghi audit bao quanh target, mỗi proxy chuyển tiếp đúng một lần. Target có chạy hai lần không?  
**Trả lời:** Không nhất thiết; ví dụ Java cho thấy advice chạy hai lần, target chạy một lần.

**Câu 3.** Tại sao không thể khẳng định retransformation hai lần luôn chèn advice hai lần?  
**Trả lời:** Vì bytecode được cung cấp và cách transformer hoạt động tuân theo hợp đồng JVM và công cụ; cần kiểm nghiệm thực tế.

**Câu 4.** Vì sao bridge method có thể gây cảm giác advice chạy trùng?  
**Trả lời:** Cùng đường gọi có thể đi qua bridge và implementation là hai execution join points, dù mỗi method chỉ được instrument một lần.

**Câu 5.** Khi advice chạy hai lần nhưng target một lần, nơi ưu tiên sửa là gì?  
**Trả lời:** Kiểm tra proxy nesting, policy registration, weaving scope hoặc overlapping pointcuts, không tự sửa nghiệp vụ để tránh chạy lặp.

**Câu 6.** Nếu một event ID xuất hiện hai lần ở DB nhưng advice count chỉ một, suy luận gì?  
**Trả lời:** Có thể lỗi ở event delivery, consumer hoặc exporter; chưa có bằng chứng double weaving.

**Câu 7.** Một cờ global `alreadyExecuted` có sửa an toàn double advice không?  
**Trả lời:** Không. Nó bỏ qua các lời gọi độc lập, không an toàn đồng thời và không phản ánh policy/invocation identity.

**Câu 8.** Có nên coi hai advice cùng khớp cùng một join point là lỗi không?  
**Trả lời:** Chỉ khi vi phạm hợp đồng của chúng. Audit và metrics cùng chạy có thể đúng; hai lần tạo cùng một audit event ngoài ý định mới là lỗi.

## 22. Tổng kết

**Dệt lặp** có thể tạo ra hành vi cắt ngang bị chèn nhiều lần, nhưng **duplicate advice** còn có thể đến từ proxy lồng nhau, pointcut chồng lấn, nhiều tầng instrumentation, bridge methods hoặc một chuỗi join points hợp lệ. **Hai log giống nhau không đủ chứng minh nguồn lỗi.** Phải xác định ý nghĩa của một operation/invocation/attempt, đếm advice entry và business execution độc lập, và lần theo toàn bộ pipeline build, class loading, proxy registration và event delivery.

Thiết kế vững chắc gồm **ownership rõ cho mỗi chính sách**, tách raw/woven artifacts, kiểm soát weaver/transformer, idempotent registration đúng phạm vi, pointcut có ý nghĩa, metadata chẩn đoán không nhạy cảm và integration tests trên đường gọi thực. Mục tiêu không phải cấm mọi lời gọi có nhiều advice, mà là bảo đảm **mỗi hành vi cắt ngang được áp dụng đúng số lần theo hợp đồng**, giữ nguyên kết quả và ngoại lệ nghiệp vụ, đồng thời duy trì số liệu audit/metrics trung thực.