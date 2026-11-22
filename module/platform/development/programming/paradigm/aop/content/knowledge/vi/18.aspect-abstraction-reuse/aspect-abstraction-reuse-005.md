# Tách cơ chế can thiệp khỏi dịch vụ xử lý dùng chung trong AOP

> **Mục tiêu học tập:** Thiết kế một aspect sao cho cơ chế **chọn điểm can thiệp, nhận quyền điều khiển và chuyển tiếp lời gọi** được tách khỏi phần **xử lý dùng chung**. Người học sẽ hiểu vai trò của pointcut, advice, join point adapter, dữ liệu ngữ cảnh chuẩn hóa và shared service; cách dùng lại một handler ở nhiều điểm can thiệp mà không phụ thuộc vào cú pháp weaving; cách bảo toàn return value/exception, xử lý đồng thời, phạm vi state, reentrancy, async và kiểm thử. Nội dung là AOP tổng quát cơ bản và nâng cao; các API Java 17 minh họa nguyên lý bằng chương trình tự chạy, không giả định một engine AOP hoặc ngôn ngữ pointcut cụ thể.

## 1. Bài toán: cùng một cách xử lý, nhiều ranh giới can thiệp

Giả sử một ứng dụng cần ghi lại những sự kiện kỹ thuật mỗi khi một thao tác quan trọng bắt đầu, trả kết quả hoặc thất bại. Các thao tác có thể xuất hiện ở nhiều nơi:

- Method thực thi một truy vấn dữ liệu.
- Method hoàn tất một phép tính nghiệp vụ.
- Callback được chạy sau một tác vụ bất đồng bộ.
- Một ranh giới xử lý lệnh do ứng dụng tự định nghĩa.

Nếu mỗi advice tự thực hiện định dạng log, phân loại lỗi, tạo correlation ID, kiểm tra chính sách ghi và gọi event sink, cùng một logic sẽ bị sao chép. Khi yêu cầu thay đổi cách xử lý sự kiện, người viết phải sửa nhiều aspect.

Ngược lại, nếu đưa nguyên object join point của một công cụ vào một dịch vụ xử lý chung, dịch vụ đó lại phụ thuộc vào API AOP, loại join point và cơ chế weaving. Người viết đã **chuyển chỗ sự phụ thuộc** chứ chưa tách nó.

Mục tiêu của bài:

~~~text
Nhiều ranh giới can thiệp
        |
        v
Những advice/adapter mỏng
        |
        v
Dữ liệu ngữ cảnh chuẩn hóa
        |
        v
Shared Processing Service
        |
        v
Policy / formatter / event sink / metrics backend
~~~

**Đường phụ thuộc phải đi từ cơ chế can thiệp tới hợp đồng xử lý dùng chung**, không buộc dịch vụ dùng chung phải biết pointcut engine nào gọi nó.

## 2. Phân biệt pointcut, advice và shared service

| Thành phần | Trách nhiệm | Điều không nên ôm đồm |
|---|---|---|
| **Join point** | Điểm/sự kiện runtime mà mô hình AOP hỗ trợ can thiệp | Không tự là một record xử lý nghiệp vụ tổng quát |
| **Pointcut** | Chọn những join point phù hợp | Không tự thay thế thuật toán xử lý sự kiện |
| **Weaver/interceptor** | Kết hợp advice vào đường thực thi | Không nên trở thành nơi xử lý chính sách tùy ý |
| **Advice/adapter** | Nhận invocation, rút metadata, gọi handler và chuyển tiếp | Không sao chép toàn bộ xử lý dùng chung |
| **Shared service/handler** | Áp dụng logic chuẩn hóa, phân loại, phát sự kiện hoặc thực thi một tác vụ dùng chung | Không nhất thiết biết đối tượng join point hoặc cú pháp pointcut |
| **Sink/port** | Nhận kết quả xử lý qua một hợp đồng | Không cần biết lời gọi đến từ loại weaving nào |

Từ **“dịch vụ”** trong bài chỉ một thành phần phần mềm có API rõ ràng, không nhất thiết là dịch vụ mạng hoặc một container bên ngoài.

### 2.1. Advice không phải một tầng nghiệp vụ mới mặc định

Advice là **điểm kết nối với luồng thực thi**. Nó có thể bao quanh, chặn, thay tham số, thay kết quả hoặc xử lý lỗi nếu cơ chế hỗ trợ. Tuy nhiên việc advice có quyền làm điều đó **không có nghĩa** mọi chính sách xử lý đều nên được viết trực tiếp trong advice.

Một advice dùng cho quan sát thuần túy thường cần phần thân ngắn, trong khi logic phân loại, chuẩn hóa và gửi sự kiện có thể đặt vào các thành phần dùng chung để kiểm thử độc lập.

## 3. Ba lớp hợp lý: lựa chọn, thích ứng, xử lý

**Lớp 1 — Selection/interception mechanism:** chứa định nghĩa điểm được chọn và đặc tả kiểu advice; phụ thuộc vào khả năng của hệ AOP.

**Lớp 2 — Adapter:** chuyển các dữ kiện ở join point sang một hợp đồng ổn định, ví dụ operation name, phase, outcome và một correlation key. Adapter chịu trách nhiệm ranh giới return/throw của lời gọi.

**Lớp 3 — Shared processor:** làm việc trên các DTO/value objects độc lập với engine. Bộ xử lý có thể được gọi bởi adapter A, adapter B, unit test hoặc một application component bình thường.

~~~text
AOP selector ──> MethodAdviceAdapter ─┐
                                      │
Callback wrapper ──> CallbackAdapter ─┼─> ObservationProcessor
                                      │           |
Manual invocation ────────────────────┘           v
                                                EventSink
~~~

Không phải mọi hệ thống cần đúng ba class vật lý. Đây là **phân tách trách nhiệm**, có thể hiện thực bằng vài class nhỏ hoặc nhiều module tùy quy mô.

## 4. Tại sao không cho handler nhận JoinPoint trực tiếp?

Một thiết kế coupling cao:

~~~text
SharedHandler.process(rawJoinPoint)
~~~

Handler phải biết:

- Cách engine biểu diễn signature.
- Cách lấy target và argument array.
- Các loại call/execution/constructor join points được phép.
- API proceed và trạng thái can thiệp.
- Quy tắc class loading, proxy hoặc weaving.
- Kiểu exception được API của engine bọc.
- Quyền truy cập raw arguments, có thể chứa dữ liệu nhạy cảm.

Một API ổn định hơn:

~~~text
SharedHandler.handle(
    Event(
        operation = "Catalog.load",
        phase = "FAILURE",
        failureType = "IOException",
        correlationId = "R-42"
    )
)
~~~

Event là **dữ liệu đã chuẩn hóa**. Handler có thể hoạt động khi không có môi trường weaving, giúp unit test chỉ việc tạo Event.

### 4.1. Chỉ copy metadata cần thiết

Không cần đưa cả target object, raw arguments hoặc toàn bộ Throwable tới mọi handler nếu nó chỉ cần tên operation, phase và error class. Việc thu hẹp DTO làm giảm coupling, memory retention, cardinality và nguy cơ lộ dữ liệu.

Một thiết kế chuyên sâu có thể truyền thông tin lỗi dưới dạng error record đã kiểm duyệt, đồng thời giữ Throwable gốc ở ranh giới sở hữu lỗi. Không nên tự động lưu Throwable trong một hàng đợi sống lâu chỉ để ghi metrics.

## 5. Hướng phụ thuộc: từ adapter tới hợp đồng chung

Một kiến trúc mong muốn:

~~~text
AOP-specific advice adapter
         depends on
     SharedService port
         implemented by
  ConcreteSharedProcessor
         depends on
       Sink interfaces
~~~

Không mong muốn:

~~~text
SharedProcessor
     imports a weaver's raw JoinPoint class
     casts advice-specific subclasses
     calls proceed()
     decides weaving precedence
~~~

Việc gọi proceed, quyết định có short-circuit hay không và bảo toàn kết quả của lời gọi thuộc về **hợp đồng can thiệp**. SharedProcessor xử lý **thông điệp/đối tượng xử lý ổn định**; nếu cần điều phối nghiệp vụ, hãy tách riêng một policy rõ ràng thay vì giấu điều khiển luồng trong một method handleEvent không có mô tả.

### 5.1. Hợp đồng ổn định không nhất thiết là hợp đồng tối giản cực đoan

DTO chỉ có một String message có thể quá yếu: handler phải parse text rồi suy phase hoặc failure type. Hợp đồng tốt nên có **những trường có ý nghĩa** nhưng không mang API cụ thể của engine.

Ví dụ:

~~~text
Observation {
    eventKind
    operation
    stage
    outcome
    correlation
    errorCategory?
    elapsedNanos?
}
~~~

Những trường không cần thiết không nên tạo ra chỉ cho đẹp. Cấu trúc phụ thuộc mục tiêu quan sát hay policy đang được hiện thực.

## 6. Một concern dùng chung có thể có nhiều adapter

Cùng một EventProcessor có thể nhận:

- MethodStarted và MethodFinished từ method-execution advice.
- CallbackStarted và CallbackCompleted từ wrapper quanh callback execution.
- OperationSubmitted từ interceptor quanh scheduling API.
- JobCompleted từ một thành phần ứng dụng chủ động phát event.

Sự đa dạng đó làm rõ **reusability**: mỗi adapter biết cách trích thông tin từ **boundary của nó**, còn processor không cần biết sự kiện đến từ một join point nào.

**Không phải mọi boundary ở trên đều được mọi công cụ AOP hỗ trợ như join point.** Có thể dùng một wrapper thủ công nếu model không có join point phù hợp; nguyên tắc phân tách vẫn được giữ.

## 7. Không gắn processing service với cú pháp pointcut

Ví dụ sai ở mức thiết kế:

~~~text
Service.recordFailure(pointcutExpression, rawJoinPoint, proceedHandle)
~~~

Handler vừa phải hiểu cách chọn điểm, vừa phải tham gia quyền điều khiển. Mỗi lần thay engine, đổi loại join point hoặc đổi cách matching, handler có nguy cơ cần sửa.

Ví dụ ổn định hơn:

~~~text
Advice:
  nếu được gọi tại điểm phù hợp:
    event = mapJoinPointToEvent(...)
    sharedProcessor.accept(event)
    tiếp tục theo advice contract
~~~

Sự khác nhau: pointcut xác định **khi nào gọi**, adapter xác định **thông tin gì được gửi**, processor xác định **xử lý thông tin đó thế nào**.

## 8. Mở rộng xử lý mà không thay mọi advice

Một lợi ích của tách lớp:

- Thay event sink từ console sang collector khác: sửa implementation processor/sink.
- Thêm quy tắc redaction: sửa normalizer hoặc processor có trách nhiệm.
- Đổi cách lấy operation name ở một loại join point: sửa adapter của loại đó.
- Thay đổi pointcut chọn nhiều hoặc ít method: sửa selection mechanism.
- Thêm adapter cho callback: tái sử dụng processor đã có.

Điều kiện là **hợp đồng Event/Processor ổn định về semantics**. Nếu nhét dữ liệu không có nghĩa chung vào một field String, các thay đổi vẫn có thể lan rộng.

### 8.1. Tách trách nhiệm không đồng nghĩa phải tạo quá nhiều interface

Trong một ứng dụng nhỏ, một record Event, một interface EventProcessor, một implementation và một adapter có thể đủ. Không cần xây một bus sự kiện đa tầng nếu chưa có yêu cầu thực tế.

Mục tiêu là **giảm coupling và làm rõ ownership**, không phải tối đa hóa số class.

## 9. Quyết định để cơ chế hay dịch vụ thực hiện việc gì

| Quyết định | Nơi phù hợp hơn |
|---|---|
| Chọn method execution theo signature | Pointcut/selection |
| Trích tên operation từ signature | Adapter |
| Đếm số lần handler được gọi | Handler/metrics processing |
| Nên gọi continuation hay short-circuit? | Advice hoặc policy điều khiển riêng được chỉ định |
| Chuyển exception thành metadata an toàn | Adapter/error mapper ở boundary |
| Có cần redaction trường nhạy cảm? | Normalizer/processor theo hợp đồng |
| Sử dụng một sink hay nhiều sinks | Processor/composition |
| Ai sở hữu transaction rollback? | Contract xử lý nghiệp vụ/transaction riêng |
| Xử lý lỗi sink bằng fail-open hay fail-closed? | Policy rõ ở ranh giới giữa adapter và processor |
| Có truyền context sang worker không? | Adapter ở async boundary/context scope owner |

Bảng chỉ mô tả một cách phân quyền trách nhiệm **hợp lý**, không phải luật ép mọi ứng dụng phải có cùng cách phân lớp.

## 10. Ví dụ Java 17 số 1: advice mỏng và processor dùng chung

Chương trình hoàn chỉnh này mô phỏng một quanh advice nhận tên thao tác và một continuation. Adapter chỉ:

1. Chuyển event BEGIN cho processor.
2. Gọi phần gốc đúng một lần.
3. Báo RETURN hoặc THROW theo kết quả.
4. Trả lại đúng value hoặc ném lại đúng exception.

Processor nhận Event đã chuẩn hóa và in kết quả. Cùng processor có thể được gọi trực tiếp ở ngoài advice, chứng minh nó **không phụ thuộc vào join point API**.

**Lưu ý:** Đây là Java thuần mô phỏng advice. Không có parser pointcut, bytecode weaving hay một engine AOP tự động.

Lưu file **InterceptionSeparationDemo.java**:

~~~java
import java.io.IOException;

public class InterceptionSeparationDemo {
    record Event(String phase, String operation, String detail) {}

    interface EventProcessor {
        void handle(Event event);
    }

    static final class ConsoleProcessor implements EventProcessor {
        @Override
        public void handle(Event event) {
            System.out.println("[processor] "
                    + event.phase() + " "
                    + event.operation() + " "
                    + event.detail());
        }
    }

    @FunctionalInterface
    interface Work {
        String run() throws IOException;
    }

    static final class AdviceAdapter {
        private final EventProcessor processor;

        AdviceAdapter(EventProcessor processor) {
            this.processor = processor;
        }

        String around(String operation, Work work) throws IOException {
            processor.handle(new Event("BEGIN", operation, "-"));
            try {
                String result = work.run();
                processor.handle(
                        new Event("RETURN", operation, result));
                return result;
            } catch (IOException | RuntimeException error) {
                processor.handle(new Event(
                        "THROW", operation,
                        error.getClass().getSimpleName()
                                + ": " + error.getMessage()));
                throw error;
            }
        }
    }

    static String load(String key) throws IOException {
        System.out.println("[core] load " + key);
        if (key.equals("missing")) {
            throw new IOException("not found");
        }
        return "data-" + key;
    }

    public static void main(String[] args) {
        EventProcessor processor = new ConsoleProcessor();
        AdviceAdapter adapter = new AdviceAdapter(processor);

        try {
            String value = adapter.around(
                    "Catalog.load", () -> load("ok"));
            System.out.println("[caller] " + value);
        } catch (IOException error) {
            System.out.println("[caller] " + error.getMessage());
        }

        try {
            adapter.around(
                    "Catalog.load", () -> load("missing"));
        } catch (IOException error) {
            System.out.println("[caller] "
                    + error.getClass().getSimpleName()
                    + ": " + error.getMessage());
        }

        processor.handle(
                new Event("MANUAL", "Maintenance", "ready"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac InterceptionSeparationDemo.java
java InterceptionSeparationDemo
~~~

**Stdout chính xác:**

~~~text
[processor] BEGIN Catalog.load -
[core] load ok
[processor] RETURN Catalog.load data-ok
[caller] data-ok
[processor] BEGIN Catalog.load -
[core] load missing
[processor] THROW Catalog.load IOException: not found
[caller] IOException: not found
[processor] MANUAL Maintenance ready
~~~

### 10.1. Vì sao processor không cần biết join point?

ConsoleProcessor chỉ xử lý Event. Nó không dùng method signature API, target, proxy, continuation hoặc bộ dệt nào. Một unit test có thể gọi processor.handle(new Event(...)) mà không dựng môi trường AOP.

Đây là **reusability theo hợp đồng xử lý**, không phải chỉ việc nhiều advice cùng copy/paste một đoạn log.

### 10.2. Vì sao adapter nên giữ nhiệm vụ chuyển tiếp?

AdviceAdapter có trách nhiệm gọi work.run và giữ return/throw contract. Nếu handler tự gọi work.run, handler sẽ phụ thuộc cơ chế continuation và phải hiểu từng loại điểm can thiệp.

Đối với **observer thuần**, việc handler không điều khiển proceed giúp tránh lỗi gọi phần gốc hai lần hoặc vô tình không gọi phần gốc.

### 10.3. Processor có thể được gọi ngoài AOP

Dòng MANUAL Maintenance ready được phát trực tiếp từ main thông qua cùng EventProcessor. Đó là bằng chứng cụ thể rằng logic xử lý **dùng lại được ở một ranh giới không có AOP**.

Trong ứng dụng thật, một event thủ công nên có phân loại để tránh lẫn với method execution event; ví dụ có eventKind tường minh.

### 10.4. Giới hạn liên quan lỗi của processor

ConsoleProcessor trong ví dụ không cố tình ném lỗi. Nếu processor.handle tự ném RuntimeException ở nhánh RETURN, catch của adapter có thể bắt **lỗi processor** như thể đó là lỗi từ work, rồi tiếp tục gọi processor để phát THROW. Nếu processor lại lỗi, exception khác có thể che exception đầu.

Điều này cho thấy: **tách class thôi chưa đủ; phải thiết kế ranh giới lỗi của observer với lời gọi nghiệp vụ**. Phần sau xây dựng một chính sách best-effort rõ ràng để tránh gây false failure hoặc masking ngoài dự kiến.

## 11. Đừng lẫn “độc lập về API” với “độc lập về failure”

Một handler không dùng JoinPoint nhưng vẫn có thể:

- Ném RuntimeException từ sink.
- Block trong I/O.
- Gây deadlock nếu callback gọi lại điểm đang được advice.
- Dùng shared mutable state không an toàn.
- Đọc dữ liệu nhạy cảm không phù hợp.
- Kéo dài thời gian của mọi method được quan sát.

Vì vậy còn cần ranh giới về **failure policy, latency policy và state ownership**, bên cạnh ranh giới loại dữ liệu.

## 12. Một processor có thể chuyên về policy nhưng không nên tùy ý thay business outcome

Shared service có thể:

- Phân loại event.
- Chuẩn hóa operation naming.
- Kiểm duyệt metadata.
- Ghi metric.
- Xử lý event hợp lệ/không hợp lệ.
- Gửi tới một hoặc nhiều event sinks.
- Quản lý batching hoặc buffering khi được thiết kế.

Nếu nó phải **quyết định business operation có được tiếp tục hay không**, đó không còn là một event processor quan sát thuần. Một cách rõ ràng hơn là định nghĩa một **PolicyDecision** làm kết quả của policy service, rồi để advice diễn giải quyết định và gọi/không gọi continuation theo hợp đồng can thiệp.

Ví dụ khái niệm:

~~~text
Advice:
    input = normalize(joinPointContext)
    decision = policy.evaluate(input)
    if decision is REJECT:
        return or throw according to API contract
    else:
        proceed exactly once
~~~

Cần giữ khác biệt giữa **side-effect observation handler** và **control policy service**. Hai loại có thể cùng được chia sẻ, nhưng không nên dùng một tên handle chung mơ hồ che đi quyền thay đổi luồng thực thi.

## 13. Contract của event phải có semantics rõ

Các trường thường hữu ích:

| Trường | Ý nghĩa | Nguồn phù hợp |
|---|---|---|
| eventKind | Invocation, callback, submission... | Adapter |
| operation | Tên ổn định mô tả việc được xử lý | Adapter/normalizer |
| phase | BEGIN, RETURN, THROW, COMPLETE... | Advice boundary |
| outcome | SUCCESS, FAILURE, RECOVERED... theo hợp đồng | Owner của outcome |
| correlationId | Tương quan giữa nhiều events | Context scope |
| errorCategory | Nhóm lỗi đã chuẩn hóa | Error mapper |
| elapsedNanos | Duration ở ranh giới đo xác định | Timer owner |
| attempt | Lần thử của retry nếu có | Retry owner |

Không phải event nào cũng có đủ các trường. Nên định nghĩa **schema version** hoặc vài event types riêng khi semantics khác nhau rõ rệt, thay vì bắt tất cả vào một record khổng lồ với nhiều null không được mô tả.

Một processor dễ tái sử dụng vì nó nhận **hợp đồng có ý nghĩa ổn định**, không phải vì nó nhận Object rồi tự đoán mọi thứ bằng instanceof.

## 14. Shared service có thể dùng lại ở nhiều loại adapter

Một adapter cho method execution biết cách gọi continuation của method. Một adapter cho callback execution biết cách gọi callback. Chúng có thể khác nhau về method signature và exception model, nhưng tạo cùng loại Observation cho một shared handler.

~~~text
MethodAdapter:
  before target.run()
  after target.run()

CallbackAdapter:
  before callback.run()
  after callback.run()

Both:
  SharedProcessor.handle(Observation)
~~~

Không nên gom cả hai vào một advice khổng lồ kiểm tra “nếu là callback thì làm A, nếu là method thì làm B” khi ranh giới return/throw khác nhau. Tách các **adapter nhỏ**, dùng cùng **processor chung**.

## 15. Ví dụ Java 17 số 2: một service, hai loại adapter

Chương trình sau có:

- Một **SharedObservationService** ghi sự kiện theo cấu trúc.
- Một **MethodAdapter** gọi một supplier rồi phát BEGIN/RETURN/THROW.
- Một **CallbackAdapter** chạy một Runnable rồi phát BEGIN/RETURN/THROW.
- Một bộ nhớ event để in lại, chứng minh tất cả sự kiện đi qua cùng service.

Callback trong ví dụ được **gọi đồng bộ có chủ đích** để stdout xác định; nó minh họa **ranh giới thực thi callback**, không mô phỏng một hệ lập lịch async.

Lưu file **SharedHandlerReuseDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class SharedHandlerReuseDemo {
    record Observation(String source, String operation, String phase) {}

    interface ObservationService {
        void accept(Observation event);
    }

    static final class SharedObservationService
            implements ObservationService {
        private final List<Observation> events = new ArrayList<>();

        @Override
        public void accept(Observation event) {
            events.add(event);
        }

        void printSnapshot() {
            for (Observation event : List.copyOf(events)) {
                System.out.println("[event] "
                        + event.source() + " "
                        + event.operation() + " "
                        + event.phase());
            }
        }
    }

    static final class MethodAdapter {
        private final ObservationService service;

        MethodAdapter(ObservationService service) {
            this.service = service;
        }

        String invoke(String name, Supplier<String> operation) {
            service.accept(new Observation("METHOD", name, "BEGIN"));
            try {
                String result = operation.get();
                service.accept(
                        new Observation("METHOD", name, "RETURN"));
                return result;
            } catch (RuntimeException error) {
                service.accept(new Observation(
                        "METHOD", name,
                        "THROW:" + error.getClass().getSimpleName()));
                throw error;
            }
        }
    }

    static final class CallbackAdapter {
        private final ObservationService service;

        CallbackAdapter(ObservationService service) {
            this.service = service;
        }

        void invoke(String name, Runnable callback) {
            service.accept(new Observation("CALLBACK", name, "BEGIN"));
            try {
                callback.run();
                service.accept(
                        new Observation("CALLBACK", name, "RETURN"));
            } catch (RuntimeException error) {
                service.accept(new Observation(
                        "CALLBACK", name,
                        "THROW:" + error.getClass().getSimpleName()));
                throw error;
            }
        }
    }

    public static void main(String[] args) {
        SharedObservationService service =
                new SharedObservationService();
        MethodAdapter methods = new MethodAdapter(service);
        CallbackAdapter callbacks = new CallbackAdapter(service);

        String value = methods.invoke("Catalog.find", () -> {
            System.out.println("[target] find");
            return "item-1";
        });

        callbacks.invoke("onComplete", () ->
                System.out.println("[callback] got " + value));

        try {
            callbacks.invoke("onError", () -> {
                throw new IllegalStateException("callback failed");
            });
        } catch (IllegalStateException error) {
            System.out.println("[caller] " + error.getMessage());
        }

        service.printSnapshot();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SharedHandlerReuseDemo.java
java SharedHandlerReuseDemo
~~~

**Stdout chính xác:**

~~~text
[target] find
[callback] got item-1
[caller] callback failed
[event] METHOD Catalog.find BEGIN
[event] METHOD Catalog.find RETURN
[event] CALLBACK onComplete BEGIN
[event] CALLBACK onComplete RETURN
[event] CALLBACK onError BEGIN
[event] CALLBACK onError THROW:IllegalStateException
~~~

### 15.1. Một service không cần biết lời gọi gốc ra sao

ObservationService chỉ có accept(Observation). Nó không gọi Supplier.get hoặc Runnable.run và không phụ thuộc vào một JoinPoint object. Hai adapter tự chịu trách nhiệm **tiếp tục thao tác đúng contract** của mình.

### 15.2. Cùng service giữ một luồng event

Cả MethodAdapter và CallbackAdapter sử dụng **cùng instance** SharedObservationService. Vì vậy printSnapshot in cả sự kiện METHOD và CALLBACK, theo thứ tự các invocation được gọi trong demo.

Trong môi trường đồng thời, ArrayList chưa phải thread safe. Dùng một implementation handler có concurrency model phù hợp hoặc serialize access nếu nhiều thread cùng gọi accept.

### 15.3. Callback registration và callback execution vẫn phải tách

Ở ví dụ, callbacks.invoke thực sự gọi Runnable.run, do đó event CALLBACK BEGIN/RETURN phản ánh **thời điểm callback được thực thi**. Một advice chỉ thấy method dùng để **đăng ký callback** không tự có cùng semantics.

Nếu callback chạy trên executor, adapter/handler phải được đặt ở boundary callback thực thi, đồng thời quản lý context/cancellation tương ứng.

### 15.4. Đừng cho handler tự quyết định gọi continuation

Nếu SharedObservationService nhận luôn Runnable rồi tự gọi run, nó có thể trở thành tầng điều phối, khó biết ai có quyền retry hoặc short-circuit. Trong minh họa, **adapter giữ quyền gọi** và handler **chỉ xử lý Observation**.

Nếu yêu cầu thật sự là policy orchestration, nên tạo interface riêng như ExecutionPolicy hoặc RetryCoordinator với hợp đồng rõ.

## 16. Chú ý lỗi của service ở đường thành công

Hai chương trình minh họa dùng handler bình thường, nên một lối viết đơn giản là:

~~~text
try:
    result = proceed()
    processor.handle(RETURN)
    return result
catch:
    processor.handle(THROW)
    rethrow
~~~

Nhưng nếu processor.handle(RETURN) tự ném lỗi, catch có thể tưởng đó là lỗi từ proceed và phát THROW giả. Lúc đó một **failure của observer** bị ghi như failure của business operation.

Một cách khắc phục là **giới hạn try/catch quanh đúng lời gọi Original**:

~~~text
try:
    result = proceed()
catch businessError:
    safelyObserve(THROW, businessError)
    throw businessError

safelyObserve(RETURN, null)
return result
~~~

Phân tách hai loại failure giúp metric không báo “business operation failed” chỉ vì sink lỗi.

### 16.1. Không tự chọn fail-open cho mọi concern

Nếu service chỉ gửi metrics best-effort, có thể quyết định bỏ qua lỗi sink (sau khi chẩn đoán bằng kênh phù hợp). Nếu service thực thi kiểm soát an toàn hoặc audit bắt buộc, một chính sách fail-closed có thể được yêu cầu.

Vì vậy failure isolation là **hợp đồng rõ**, không chỉ catch(RuntimeException) rồi luôn nuốt. Cần phân biệt **lỗi hệ thống quan sát** với **lỗi nghiệp vụ** trong cả log, metrics và kết quả caller.

## 17. Bảo toàn exception và return value

Một advice quan sát thuần nên bảo toàn:

1. **Số lần Original được gọi**: đúng một lần khi không có chính sách điều khiển khác.
2. **Giá trị trả về**: cùng dữ liệu, không tự thay thành fallback.
3. **Loại và identity của exception** khi đã thỏa contract.
4. **Cause và suppressed** nếu có chuyển loại/cleanup.
5. **Các side effects của Original**: không lặp do advice vô tình retry.

Một handler muốn ghi message về exception có thể nhận một ErrorSummary đã chuẩn hóa, trong khi adapter vẫn ném lại lỗi gốc. Đừng bắt tất cả Exception rồi trả null chỉ để handler không phải xử lý lỗi.

### 17.1. Error cũng là đường điều khiển cần cân nhắc

Một observer có thể chọn dùng finally để cleanup/ghi duration, nhưng không nên bắt Throwable rồi cố biến mọi lỗi VM thành success. Trong tình huống tài nguyên cạn, chính logger có thể không hoạt động. Không có bảo đảm một sự kiện quan sát được phát thành công sau mọi dạng lỗi.

## 18. Một adapter không nên vừa sở hữu fallback vừa sở hữu metric policy

Nếu cùng một advice:

- Validate input.
- Retry.
- Chuyển exception thành fallback.
- Đo latency.
- Redact arguments.
- Gửi event.
- Mở transaction.

thì chỉ tách một class ObservationService chưa đủ làm thiết kế dễ hiểu. Cần chia **mối quan tâm** thành những hợp đồng có ownership:

~~~text
Guard decision
Retry policy
Transaction boundary
Observation
Error mapping
~~~

Mỗi phần nên có trách nhiệm rõ; precedence giữa các aspect cần phản ánh ngữ nghĩa, không dựa vào thứ tự tên class. Shared processor không nên dần trở thành một nơi chứa mọi chính sách không liên quan.

## 19. Tách xử lý chung khỏi business service

Một bài toán dễ hiểu sai: “Tách cơ chế can thiệp khỏi dịch vụ xử lý dùng chung” **không có nghĩa phải chuyển thuật toán nghiệp vụ vào aspect**.

Dịch vụ nghiệp vụ vẫn nên thể hiện nghiệp vụ:

~~~text
CatalogService.load
PaymentService.pay
InventoryService.reserve
~~~

Shared ObservationProcessor xử lý **quan sát**, không tự quyết định số tiền thanh toán hay tồn kho, trừ khi một API policy được thiết kế chuyên biệt yêu cầu điều đó.

Một aspect không nên biến toàn bộ business code thành callback để đưa vào một “universal service” khó đọc. AOP thích hợp cho những chức năng xuyên suốt có ranh giới lựa chọn rõ.

## 20. Shared service không bắt buộc là singleton

Việc nhiều adapter tái sử dụng một interface không buộc mọi invocation chia sẻ **cùng instance**.

Các scope có thể có:

| Scope của processor | Khi phù hợp | Nguy cơ |
|---|---|---|
| Stateless singleton | Xử lý thuần hoặc đẩy qua thread-safe sink | Phải bảo đảm thread safety |
| Per-request | Bộ tích lũy trong một logical request | Cần propagation và cleanup |
| Per-invocation | State tạm riêng mỗi lời gọi | Tạo nhiều objects nếu hot path |
| Per-target | State gắn object đích | Không đồng nghĩa per-request |
| Per-thread | State theo worker thread | Thread pool reuse và async boundary |
| External shared store | Events được lưu ngoài process | Backpressure, idempotency, failure semantics |

**Reuse về interface/implementation không đồng nghĩa share mutable state vô điều kiện.**

Một processor stateless có thể được nhiều adapter dùng chung mà không tạo nguy cơ trộn request. Một processor tích lũy List<Event> như ví dụ thứ hai cần được giới hạn concurrency và lifetime.

## 21. Concurrency và quyền sở hữu state

Nếu nhiều threads gọi shared handler đồng thời, phải biết những object nào mutable:

- Bộ đếm sự kiện.
- Hàng đợi.
- Cache metadata.
- Bộ lọc sampling.
- Bộ định dạng có buffer nội bộ.
- Correlation maps.
- Batch accumulator.
- Các kết nối/sessions tới sink.

Một handler dùng HashMap hoặc ArrayList không thread safe trong demo tuần tự không tự thành thread safe khi được gọi từ các advice của server nhiều thread.

Các cách thiết kế:

- Stateless processor với immutable events.
- Thread-safe queue hoặc collection phù hợp.
- Serial executor với bounded capacity.
- Lock có phạm vi được xác định.
- Per-invocation buffers nếu thật sự cần.
- Backpressure hoặc sampling khi khối lượng tăng.

Không che rủi ro bằng synchronized toàn bộ handler nếu việc ghi I/O chậm hoặc có khả năng gọi lại các điểm được advice: điều đó có thể gây contention hoặc deadlock.

## 22. Context propagation không thuộc processor một cách tùy tiện

Adapter ở ranh giới can thiệp biết:

- Điểm nào đang được gọi.
- Thread/scope hiện tại.
- Có continuation hay không.
- Khi nào method return hoặc Future được trả.

Shared handler thường không nên tự đọc một ThreadLocal không được khai báo trong hợp đồng rồi suy requestId; như vậy hidden dependency có thể khiến unit test sai và async callbacks mất correlation.

Tốt hơn là adapter hoặc context extractor tạo một **immutable context snapshot đã được kiểm duyệt**, rồi đưa vào Event.

~~~text
Advice extracts ContextSnapshot
        |
        v
Observation(Event, ContextSnapshot)
        |
        v
SharedProcessor
~~~

Với async, việc một method trả Future không nghĩa công việc đã hoàn tất. Adapter cho scheduling và adapter cho completion là những boundary khác nhau; processor chỉ nhận event đã chỉ rõ loại.

## 23. Nested calls và reentrancy

Giả sử processor ghi sự kiện bằng cách gọi một method mà pointcut cũng chọn:

~~~text
Advice for businessMethod
   -> SharedProcessor.handle
      -> EventSink.write
         -> Advice for EventSink.write
            -> SharedProcessor.handle
               -> ...
~~~

Điều này có thể tạo vòng recursion không mong muốn.

Một số giải pháp:

- Loại trừ các method hạ tầng của processor/sink khỏi pointcut nếu mô hình cho phép.
- Tránh để handler gọi lại trực tiếp same intercepted operation.
- Dùng một guard reentrancy được quản lý theo execution scope khi cần.
- Đảm bảo guard được phục hồi trong finally, kể cả lỗi.
- Kiểm thử nested invocations và lời gọi từ nhiều threads.

Một boolean static chung như isLogging có thể vô tình chặn sự kiện của **thread khác**, vì vậy không nên dùng làm guard per-invocation thiếu thiết kế.

## 24. Đừng nhầm callback registration với callback execution

Khi một API đăng ký callback, advice quanh **registration** chỉ biết callback được đưa vào hệ thống. Nó không tự biết callback:

- Đã bắt đầu chạy.
- Đã hoàn tất.
- Đã ném lỗi.
- Bị hủy trước khi chạy.
- Chạy trên thread nào.
- Có bị gọi qua một wrapper khác hay không.

Nếu shared processor dùng chung cho METHOD và CALLBACK, các adapter cần đặt **eventKind** và **phase** đúng. Không được gọi một event REGISTRATION là CALLBACK_SUCCESS.

Một callback wrapper có thể tạo event ở thời điểm thực thi; nhưng không được hứa mọi công cụ AOP tự can thiệp lambda/async callback nếu không có join point model phù hợp.

## 25. Timing service và sự khác nhau về boundary

Một DurationProcessor chỉ tính đúng latency khi adapter cung cấp hai mốc tương ứng:

~~~text
Method execution:
   enter method -> return/throw method

Async task:
   task starts -> task completes

Logical request:
   request accepted -> final completion
~~~

Nếu một method trả CompletableFuture, thời điểm return handle khác thời điểm future completion. Dịch vụ dùng chung có thể xử lý DurationEvent từ cả ba loại, nhưng **adapter phải ghi đúng loại và interval**.

Tốt hơn dùng nguồn thời gian monotonic để đo duration trong process; không dùng timestamp wall-clock tùy tiện rồi coi mọi chênh lệch đều là latency đáng tin.

Handler không nên tự lấy System.nanoTime ở thời điểm batch processing và nghĩ đó là thời điểm task thực sự kết thúc. Nếu event bị buffer, thời điểm handler nhận event có thể trễ hơn ranh giới sự kiện.

## 26. Trạng thái per-request và vòng đời context

Nếu cần correlation ID, processor có thể nhận nó qua Event. Không nên lưu currentRequestId trong một singleton processor field vì nhiều requests có thể chạy đồng thời.

ThreadLocal có thể phù hợp trong call stack đồng bộ nhưng:

- Cần remove/restore khi scope kết thúc.
- Thread pool tái sử dụng thread.
- Async work có thể chạy thread khác.
- Nested scope phải restore previous.
- Cancellation và failure paths phải có cleanup thích hợp.

**Một service xử lý dùng chung không tự là context owner.** Nếu nó chỉ nhận Event có correlation ID tường minh, code và test thường dễ kiểm chứng hơn.

## 27. Adapter có thể chuẩn hóa dữ liệu, processor có thể chuẩn hóa chính sách

Có hai kiểu chuẩn hóa không nên trộn:

**Chuẩn hóa kỹ thuật (adapter):**

- Tên phương thức thành operation code.
- Signature thành metadata định dạng trung lập.
- Một lỗi runtime thành error category/summary.
- Method execution thành eventKind METHOD.
- Callback execution thành eventKind CALLBACK.

**Chuẩn hóa chính sách (processor):**

- Lọc những event không cần lưu.
- Tính mức độ ưu tiên kỹ thuật.
- Redact theo dữ liệu đã được phân loại.
- Áp dụng sampling.
- Định tuyến event theo loại.
- Tổng hợp metrics hoặc chuyển sang sink phù hợp.

Vị trí cụ thể của một phép chuẩn hóa phụ thuộc hệ thống; nguyên tắc là **adapter biết cơ chế, processor biết chính sách xử lý chung**.

## 28. Fail-open và fail-closed phải là lựa chọn có chủ đích

Một observation processor ghi metrics lỗi có thể chọn fail-open: nếu metric sink lỗi, không làm hỏng business operation. Một audit bắt buộc có thể chọn fail-closed, nhưng cần một **contract tường minh** và thử nghiệm đặc biệt.

Nguy cơ của processor dùng chung:

- Nếu nó ném lỗi sau business success, caller có thể thấy failure mới.
- Nếu nó ném lỗi trong catch/finally, lỗi processor có thể che lỗi gốc.
- Nếu nó block quá lâu, tất cả intercepted calls chậm theo.
- Nếu có policy retry sink không giới hạn, một business call có thể kẹt.
- Nếu nó nuốt mọi Throwable, có thể che sự cố nghiêm trọng.

Một lời giải kiến trúc hợp lý thường có **ObserverFailurePolicy** hoặc cơ chế tương đương để phân biệt lỗi handler với lỗi continuation. Không có một chính sách chung áp dụng được cho logging best-effort và an toàn/kiểm toán bắt buộc.

## 29. Khi xử lý bất đồng bộ, tránh truyền raw JoinPoint qua hàng đợi

Một advice có thể phát event vào queue để processor chạy sau. Nếu đẩy **nguyên object join point**, target hoặc argument array mutable sang queue:

- Dữ liệu có thể bị thay đổi trước khi handler xử lý.
- Raw arguments có thể chứa token hoặc thông tin riêng tư.
- Target có thể bị giữ tham chiếu lâu hơn yêu cầu.
- Hệ xử lý phải phụ thuộc API engine.
- Nếu join point chỉ hợp lệ trong một execution scope, dùng muộn có thể sai hợp đồng.

Nên tạo **immutable snapshot** ngay tại ranh giới can thiệp, chỉ bao gồm những trường có ý nghĩa, đã redaction và an toàn để chuyển qua thread.

Nếu event sink bất đồng bộ, cần biết sự kiện nào phải đảm bảo durable delivery và chính sách overflow/backpressure ra sao. Một phương thức accept() trả bình thường chưa chắc event đã được ghi bền vững.

## 30. Versioning hợp đồng giữa adapters và processor

Khi số adapter tăng, Event contract trở thành một giao diện chung. Nếu muốn thêm phase CANCELLED hoặc field callbackId:

- Xác định nghĩa và default của field mới.
- Không làm handler cũ hiểu nhầm CANCELLED thành FAILURE.
- Phân biệt unknown value với empty value.
- Duy trì mapping nhất quán giữa các adapter.
- Có test schema compatibility.
- Nếu event được gửi qua network hoặc lưu dài hạn, cần cân nhắc version.

Không chỉ đổi String phase ở một advice rồi để processor khác parse bằng điều kiện mơ hồ. Một enum hoặc kiểu event được tài liệu hóa có thể làm lỗi hiện sớm hơn; nếu sự kiện cần tương thích nhiều phiên bản, thiết kế serialization/schema rõ.

## 31. Tách kiểm thử service và kiểm thử adapter

Một lợi ích lớn là có **hai tầng test độc lập**.

**Test SharedProcessor:**

- Với Event BEGIN/RETURN/THROW cho trước, processor tạo output chính xác.
- Policy redaction đúng.
- Không phát event ngoài allowlist.
- Concurrent calls có behavior phù hợp.
- Handler failures theo fail-open/fail-closed contract.
- Không cần dựng join point engine.

**Test Adapter:**

- Pointcut/join point phù hợp.
- Trích operation metadata đúng.
- Tạo đúng phase.
- Gọi continuation đúng số lần.
- Bảo toàn return/throw của Original.
- Truyền context snapshot đúng.
- Không để scope rò ở exceptional path.
- Không phát callback-completion khi chỉ quan sát callback registration.

**Integration test:** bật đúng các aspects/engines có thật rồi xác minh end-to-end wiring, selection, ordering và độ bao phủ của proxy/weaving.

## 32. Mock handler để kiểm tra advice chính xác

Khi adapter chỉ phụ thuộc vào interface EventProcessor, test có thể cung cấp một spy implementation ghi Event vào List hoặc tăng counter.

Một test có thể assert:

~~~text
originalCount == 1

observedEvents:
  BEGIN
  RETURN

returnedValue == originalValue
~~~

Ở exceptional case:

~~~text
original throws E
observedEvents:
  BEGIN
  THROW
caller receives same E
~~~

Đây là pseudocode cho assertions, không phải Java runnable snippet.

Cần kiểm tra cả chuyện **service được gọi sai thứ tự** hoặc một event trùng do retry, nested advice, reflection wrapper, double proxy.

## 33. Testing processor mà không cần AOP

Một processor nhận Event có thể được test trực tiếp:

~~~text
given:
  Event(kind="METHOD", operation="Catalog.load", phase="THROW")

when:
  processor.handle(event)

then:
  sink stores expected safe classification
~~~

Nhờ vậy người học có thể kiểm tra thuật toán xử lý, phân loại lỗi hoặc schema mà không cần chạy bytecode weaving.

Điều này không phủ nhận integration test: nó chỉ làm unit test **nhanh hơn và ít coupling hơn**. Các giới hạn của pointcut scope và callback path vẫn cần được xác minh khi các lớp được kết hợp thật.

## 34. Kiểm thử nhiều adapter dùng cùng handler

Phải kiểm tra:

1. Adapter A cho METHOD và adapter B cho CALLBACK cùng gọi một processor.
2. Event.source/eventKind được gắn đúng.
3. Không lẫn completion của task với registration.
4. Handler không cần kiểu dữ liệu cụ thể của AOP engine.
5. Event của hai adapter không trùng key ngoài ý muốn.
6. Nếu service có shared state, đồng thời không gây race.
7. Nếu processor lọc event, hai adapter hiểu cùng một schema.
8. Nếu một adapter bị short-circuit, handler không bịa event Original đã chạy.
9. Nếu một adapter retry, số events được giải thích theo request/attempt.
10. Nếu callback bị hủy, có event đúng nghĩa và không giả SUCCESS.

Một handler tái sử dụng được không chỉ khi **code compile**, mà còn khi **semantics không mâu thuẫn** giữa các nguồn sự kiện.

## 35. Perf: chi phí của adapter và processor

Tách lớp có thể cải thiện bảo trì nhưng không tự đảm bảo nhanh. Chi phí có thể gồm:

- Pointcut dynamic matching.
- Interceptor dispatch.
- Tạo DTO/immutable snapshot.
- Đọc reflection signature.
- Định dạng string.
- Ghi queue và lock.
- Event serialization.
- I/O tới sink.
- GC pressure.
- Retry/backpressure.

Một phương thức hot path được gọi hàng triệu lần có thể không phù hợp gửi event giàu metadata mỗi invocation.

Các cách tối ưu hợp lý:

- Điểm chọn đủ hẹp.
- Cache metadata tĩnh đúng vòng đời.
- Tránh dựng strings nếu event bị sampling bỏ qua.
- Dùng snapshot tối thiểu.
- Có bounded queue/backpressure.
- Tránh log raw arguments.
- Đo chi phí với tất cả aspects đang bật.
- Phân biệt latency của business path và thời gian xử lý ở background.

Không đổ lỗi mọi overhead cho “AOP” nếu nguồn chính là một handler làm I/O đồng bộ.

## 36. Khi nào không cần AOP?

Nếu chỉ có một lời gọi nghiệp vụ cần handler, gọi shared service trực tiếp có thể đơn giản hơn:

~~~text
BusinessService:
  eventProcessor.handle(...)
  doWork()
~~~

Nhưng nếu cùng concern xuất hiện ở nhiều ranh giới và muốn tránh lặp code kết nối, advice có thể là lựa chọn hợp lý.

Không nên dùng AOP chỉ để gọi một service dùng chung mà ứng dụng vốn đã có một API rõ và kiểm soát được. Mấu chốt là **có lợi ích của một selection/interception layer hay không**.

## 37. Những phản ví dụ quan trọng

**Phản ví dụ 1 — Processor nhận raw join point.** Không thật sự độc lập khỏi AOP engine; đổi engine có thể phải sửa processor.

**Phản ví dụ 2 — Advice chỉ có một dòng nhưng mọi logic nằm trong static utility phụ thuộc ThreadLocal.** Vẫn có hidden dependency, khó test và dễ rò context.

**Phản ví dụ 3 — Handler tự gọi proceed.** Handler nay sở hữu control flow; khó dùng cho callback với hợp đồng khác.

**Phản ví dụ 4 — Processor chứa currentUser mutable singleton field.** Nhiều requests có thể trộn dữ liệu.

**Phản ví dụ 5 — Tách class rồi bắt mọi exception và trả null.** Hợp đồng nghiệp vụ vẫn bị phá.

**Phản ví dụ 6 — Processor ghi cùng một loại event cho callback registration và execution.** Số liệu không có ý nghĩa.

**Phản ví dụ 7 — Shared service tự đọc toàn bộ raw arguments.** Tăng coupling và nguy cơ bảo mật.

**Phản ví dụ 8 — AOP pointcut quan sát method submit được coi là đo xong async task.** Ranh giới sai.

**Phản ví dụ 9 — Hai adapters cùng có retry policy ẩn.** Original có thể chạy nhiều lần ngoài dự kiến.

**Phản ví dụ 10 — Handler lưu events bằng ArrayList rồi dùng từ nhiều worker.** Không có thread safety dù interface rất sạch.

**Phản ví dụ 11 — Sink exception xảy ra sau work.run rồi bị log như business THROW.** Dữ liệu telemetry báo sai và có thể che kết quả gốc.

**Phản ví dụ 12 — Một pointcut quá rộng chọn cả processor.handle.** Tạo reentrancy/recursion.

**Phản ví dụ 13 — DTO chỉ gồm một String.** Processor phải parse văn bản không có schema, không ổn định khi tái sử dụng.

**Phản ví dụ 14 — EventProcessor dùng để kiểm tra quyền và bị đặt ở vị trí chỉ quan sát sau khi nghiệp vụ chạy.** Policy bắt buộc cần đúng boundary, không chỉ chung interface.

**Phản ví dụ 15 — Đo throughput của handler riêng rồi suy toàn bộ overhead trong weaving là như vậy.** Cần đo cả điểm can thiệp thực tế và khối lượng event.

## 38. Bảng chọn kiến trúc theo nhu cầu

| Nhu cầu | Cách tiếp cận nên xem xét |
|---|---|
| Chỉ thêm log ở nhiều method | Thin advice + shared observation handler |
| Xử lý một event ở cả advice và ứng dụng thường | Shared EventProcessor độc lập AOP |
| Nhiều loại join point có metadata khác | Adapter riêng + Event DTO chuẩn |
| Chặn lời gọi theo policy | Policy service + advice điều phối rõ |
| Retry với điều kiện nghiệp vụ | Retry coordinator có hợp đồng idempotency |
| Async callback instrumentation | Wrapper/adapter ở callback execution boundary |
| Context propagation | Snapshot + scope owner ở từng thread/boundary |
| Cần hiệu năng trên hot path | Sampling, bounded queue, tối giản DTO, đo thực tế |
| Ghi audit bắt buộc | Failure/consistency policy tường minh |
| Đang có chỉ một nơi dùng handler | Gọi service trực tiếp có thể đơn giản hơn |

Bảng chỉ định hướng quyết định, không quy định một engine hoặc syntax cụ thể.

## 39. Ma trận kiểm thử hoàn chỉnh

| Ca | Điều cần xác minh |
|---|---|
| Một method khớp pointcut | Adapter vào đúng ranh giới |
| Method không khớp | Handler không nhận event ngoài ý muốn |
| Original trả bình thường | Giá trị được giữ nguyên |
| Original ném checked exception | Caller nhận tín hiệu lỗi đúng contract |
| Original ném RuntimeException | Không bị nuốt |
| Shared processor lỗi khi RETURN | Không gán nhầm là business failure |
| Shared processor lỗi khi THROW | Không che primary ngoài policy |
| Pointcut chọn cả EventSink | Không gây vòng advice vô hạn |
| Hai adapters dùng cùng processor | Schema thống nhất |
| Callback đăng ký mà chưa chạy | Không phát CALLBACK_RETURN giả |
| Async task thất bại sau method return | Completion được quan sát tại boundary phù hợp |
| Retry nhiều attempts | Event count phân biệt request/attempt |
| Nested scope | Context cha được phục hồi |
| Thread pool tái sử dụng | Không có stale context |
| Handler stateless singleton | Concurrent calls đúng |
| Handler có mutable cache | Thread safety và lifecycle phù hợp |
| Queue đầy | Backpressure/failure policy rõ |
| Dữ liệu nhạy cảm | Redaction/allowlist hiệu lực |
| Woven/proxy path khác nhau | Adapter coverage được chứng minh |
| Original bị gọi qua đường không có advice | Không tuyên bố luôn được quan sát |

## 40. Checklist xây một shared handling service

- [ ] Có định nghĩa rõ đó là **observation**, **policy** hay **orchestration** service.
- [ ] Không buộc handler import raw join point types khi không cần.
- [ ] Advice giữ việc gọi continuation/proceed theo hợp đồng.
- [ ] DTO có semantics ổn định, không chỉ một String mơ hồ.
- [ ] Có eventKind/phase rõ cho những boundary khác nhau.
- [ ] Handler được gọi lại ở nhiều adapter mà không copy code.
- [ ] Không giữ raw target/arguments/Throwable không cần thiết.
- [ ] Return value và exception của Original được bảo toàn nếu là observer.
- [ ] Có failure policy riêng cho handler/sink.
- [ ] Không log handler failure thành business failure.
- [ ] Có policy cho processor latency, queue và backpressure.
- [ ] Không có singleton mutable request state không an toàn.
- [ ] Có context propagation và cleanup cho async path.
- [ ] Pointcut loại trừ mã hạ tầng tạo recursion khi cần.
- [ ] Có tests processor độc lập khỏi AOP.
- [ ] Có tests adapter trên normal/exceptional paths.
- [ ] Có integration tests cho proxy/weaving/scheduling path thật.
- [ ] Có metrics và audit semantics rõ: request, attempt, task hay callback.

## 41. Bài tập tự kiểm tra

### Câu 1 — Vị trí của proceed

SharedObservationService muốn xử lý Event. Nên để nó gọi proceed trực tiếp không?

**Đáp án:** nếu service chỉ quan sát, không nên. Advice/adapter chịu trách nhiệm continuation và gửi Event đến processor. Nếu yêu cầu điều phối, tạo một interface policy/orchestrator có hợp đồng riêng.

### Câu 2 — Cùng logic trên hai điểm can thiệp

Một method-execution advice và một callback adapter đều cần chuẩn hóa Event. Có nên copy/paste toàn bộ xử lý vào mỗi adapter?

**Đáp án:** không. Mỗi adapter chuyển metadata đặc thù sang một DTO chuẩn rồi gọi shared processor.

### Câu 3 — Raw join point trong handler

Tại sao SharedProcessor.handle(rawJoinPoint) có thể làm giảm tái sử dụng?

**Đáp án:** processor phụ thuộc API công cụ, loại điểm và vòng đời join point. Một DTO chuẩn làm processor độc lập hơn.

### Câu 4 — Proxy và target

Một adapter chỉ chạy khi caller đi qua proxy. Có thể khẳng định mọi call trực tiếp tới target đều được quan sát không?

**Đáp án:** không. Phải kiểm thử interception scope thực tế.

### Câu 5 — Lỗi của processor

Original trả thành công, nhưng processor ghi RETURN tự ném RuntimeException. Có được log business THROW không?

**Đáp án:** không nếu đó chỉ là lỗi observer. Cần phân biệt nguồn lỗi và áp dụng failure policy đã định.

### Câu 6 — Async completion

Method trả Future bình thường, nhưng task lỗi sau đó. Event METHOD_RETURN có phải task success không?

**Đáp án:** không. Task completion cần event riêng ở đúng boundary.

### Câu 7 — Singleton service

Một EventProcessor singleton lưu currentRequestId trong field mutable. Nguy cơ?

**Đáp án:** nhiều requests/threads dùng chung state và trộn dữ liệu; nên truyền context theo Event hoặc scope thích hợp.

### Câu 8 — Handler ArrayList

Một SharedObservationService dùng ArrayList để ghi events, nhiều threads gọi accept đồng thời. Có chắc đúng không?

**Đáp án:** không. ArrayList không bảo đảm an toàn cho writes đồng thời; cần thiết kế state/collection phù hợp.

### Câu 9 — Xử lý policy

Một policy service trả REJECT. Ai cần chịu trách nhiệm không gọi continuation?

**Đáp án:** advice hoặc một lớp điều phối có hợp đồng rõ với pointcut/interception boundary; không giấu trong một observation handler.

### Câu 10 — Reentrancy

Processor gửi event bằng một method cũng bị cùng pointcut chọn. Có thể xảy ra gì?

**Đáp án:** vòng advice/processor lặp lại vô hạn. Cần scope exclusion hoặc guard reentrancy phù hợp.

### Câu 11 — Dữ liệu event

Handler chỉ cần phase và operation. Có nên chuyển toàn bộ mảng args chưa kiểm duyệt?

**Đáp án:** không. Chỉ dùng snapshot tối thiểu, đã lọc dữ liệu nhạy cảm.

### Câu 12 — Unit test

Có thể kiểm tra phân loại Event mà không chạy weaving không?

**Đáp án:** có, nếu processor nhận DTO/interface ổn định. Nhưng vẫn cần integration test cho điểm can thiệp và thứ tự thực tế.

### Câu 13 — Request vs attempt

Một retry khiến Original chạy ba lần. Handler nhận ba event FAILURE và một event REQUEST_COMPLETE. Số sự kiện có chắc sai?

**Đáp án:** không; nếu loại sự kiện khác nhau theo attempt/request thì có thể đúng. Cần tên và định nghĩa rõ.

### Câu 14 — Khi nào không cần advice?

Chỉ có một method muốn dùng SharedProcessor và không cần chọn điểm tự động. Có bắt buộc dùng AOP không?

**Đáp án:** không. Gọi service trực tiếp thường đơn giản hơn.

## 42. Tổng kết

**Tách cơ chế can thiệp khỏi dịch vụ xử lý dùng chung** là một cách tổ chức AOP để pointcut/weaver chỉ quyết định **khi nào và ở đâu advice được vào**, advice/adapter quyết định **cách chuyển dữ liệu và giữ hợp đồng lời gọi**, còn shared processor quyết định **cách xử lý dữ liệu đã chuẩn hóa**.

Những nguyên tắc quan trọng:

- **Chọn điểm khác xử lý sự kiện.** Pointcut và processor không nên bị trộn vào một class lớn.
- **Advice mỏng nhưng có trách nhiệm.** Nó phải bảo toàn return/throw và không gọi Original sai số lần.
- **Dùng DTO trung lập thay raw JoinPoint** khi logic xử lý không thực sự cần API engine.
- **Một shared service có thể phục vụ nhiều adapters**, kể cả một đường gọi trực tiếp không dùng AOP.
- **Reusability không tự bảo đảm thread safety.** State, vòng đời và concurrency cần hợp đồng rõ.
- **Failure của observation service không phải business failure.** Phải có fail-open/fail-closed policy có chủ đích.
- **Async registration, execution và completion là những boundary khác nhau.** Dùng eventKind/phase phù hợp.
- **Pointcut nên tránh can thiệp chính hạ tầng xử lý sự kiện** nếu nó tạo recursion.
- **Kiểm thử chia tầng**: processor độc lập, adapter theo contract, rồi integration trong runtime thật.
- **Không tự dùng AOP ở mọi nơi**: khi gọi trực tiếp một service là rõ ràng hơn thì đó có thể là lựa chọn hợp lý.

**Câu hỏi tự đánh giá thiết kế:** *Nếu ngày mai thay công cụ can thiệp hoặc thêm một loại join point mới, tôi có thể giữ nguyên dịch vụ xử lý dùng chung và chỉ sửa hoặc thêm một adapter mỏng hay không?*
