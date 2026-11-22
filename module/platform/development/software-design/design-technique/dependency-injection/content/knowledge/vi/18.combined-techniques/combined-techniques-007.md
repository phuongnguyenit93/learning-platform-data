# Phân biệt gắn hành vi bằng decorator với cơ chế proxy của framework

Trong **Dependency Injection (DI)**, ta thường muốn bổ sung một hành vi *bao quanh* lời gọi của một dịch vụ: ghi log, thu thập metric, kiểm tra quyền, retry hoặc quản lý transaction. Hai cơ chế thường gặp là **Decorator pattern** và **proxy do framework tạo ra**. Cả hai đều có thể làm cho caller gọi một interface mà không biết lời gọi được chuyển tiếp qua bao nhiêu lớp, nhưng chúng khác nhau về **ai tạo lớp bao**, **cách hành vi được kích hoạt**, **ranh giới interception** và **khả năng kiểm soát ở composition root**.

Bài này thuộc chương **Kỹ thuật kết hợp** của module **Dependency Injection**. Ta sẽ dùng **Java 17 thuần**, constructor injection và composition root để thiết kế decorator tường minh; sau đó mô phỏng cơ chế proxy runtime bằng `java.lang.reflect.Proxy`. Từ đó, ta phân tích cách các DI container/framework gắn *cross-cutting concerns* và vì sao những lỗi như **self-invocation bypass proxy**, đặt sai thứ tự wrapper hoặc chọn sai scope có thể làm hành vi thực tế khác mong đợi.

## 1. Hai cách “bọc” một dịch vụ, nhưng hai mục tiêu tổ chức khác nhau

Giả sử ứng dụng có hợp đồng gửi thông báo:

~~~java
interface MessageSender {
    void send(String orderId, String message);
}
~~~

Một adapter thực hiện công việc gốc: gửi email, ghi hàng đợi hoặc gọi API. Ngoài ra, ứng dụng muốn ghi log quanh việc gửi.

**Decorator** là một object triển khai **cùng abstraction** với đối tượng được bọc và **nhận delegate qua constructor**. Nó thường được tạo tường minh trong composition root:

~~~java
MessageSender actual = new EmailMessageSender(/* cấu hình */);
MessageSender withLogging = new LoggingMessageSender(actual, logger);
OrderNotifier notifier = new OrderNotifier(withLogging);
~~~

Đoạn này chỉ minh họa wiring; các kiểu `EmailMessageSender`, `LoggingMessageSender` và `OrderNotifier` sẽ có phiên bản cụ thể ở ví dụ sau. Caller chỉ biết `MessageSender`.

**Framework proxy** cũng cung cấp một object đứng giữa caller và target, nhưng có thể được **framework tạo bằng JDK dynamic proxy, cơ chế subclass/proxy bytecode hoặc kỹ thuật weaving**, tùy hệ sinh thái và cấu hình. Hành vi như transaction hoặc authorization thường được gắn thông qua **interceptor/advice** mà caller không phải tự `new` một decorator cho từng class.

~~~mermaid
flowchart TD
    Caller["OrderNotifier"] --> Contract["MessageSender port"]
    Contract --> Decorator["Logging decorator: tạo tường minh"]
    Decorator --> Adapter["Adapter gửi thật"]
    Caller2["OrderNotifier khác"] --> Proxy["Proxy do container/framework cấp"]
    Proxy --> Advice["Interceptor/advice"]
    Advice --> Target["Target service"]
~~~

Hai nhánh chỉ minh họa **hai phương án**, không phải buộc phải có cả hai trong mọi ứng dụng. Một hệ thống cũng có thể **kết hợp decorator và proxy** theo thứ tự đã chọn.

## 2. Decorator: hành vi được gắn bằng object graph tường minh

Decorator có các dấu hiệu nhận diện:

1. Triển khai một interface/hợp đồng mà consumer đang sử dụng.
2. Giữ **delegate** cùng hợp đồng qua constructor injection.
3. Có thể thực hiện logic **trước**, **sau** hoặc **khi lỗi**, rồi chuyển tiếp lời gọi.
4. Việc có sử dụng decorator hay không được quyết định ở **composition root** hoặc factory cấu hình.

Ví dụ tối giản:

~~~java
final class LoggingMessageSender implements MessageSender {
    private final MessageSender delegate;
    private final EventLog log;

    LoggingMessageSender(MessageSender delegate, EventLog log) {
        this.delegate = java.util.Objects.requireNonNull(delegate);
        this.log = java.util.Objects.requireNonNull(log);
    }

    @Override
    public void send(String id, String message) {
        log.write("send.begin:" + id);
        try {
            delegate.send(id, message);
            log.write("send.ok:" + id);
        } catch (RuntimeException error) {
            log.write("send.error:" + id);
            throw error;
        }
    }
}
~~~

Ở đoạn minh họa này, `EventLog` là interface giả định; phần ví dụ chạy được sẽ dùng một `List<String>` để ghi trace. **Decorator không cần biết DI container tồn tại**. Nó có thể dùng trong thư viện, ứng dụng desktop, CLI hoặc bài kiểm thử Java thuần.

### Ưu điểm

- **Hiển thị rõ trong wiring:** có thể nhìn vào composition root để biết một service được bọc bởi lớp nào.
- **Dễ kiểm thử độc lập:** truyền một fake delegate, xác minh hành vi trước/sau/lỗi.
- **Hợp đồng tĩnh rõ ràng:** compiler kiểm tra decorator triển khai đúng interface.
- **Không phụ thuộc annotation hoặc cơ chế bytecode:** có thể chạy bằng Java thuần.

### Đánh đổi

- Phải viết và duy trì lớp bọc hoặc factory cho từng hợp đồng.
- Nếu interface thêm phương thức, decorator cần quyết định cách xử lý phương thức mới.
- Có nhiều decorator thì **thứ tự lắp ghép** trở thành một phần thiết kế.
- Nếu một decorator không chuyển tiếp đầy đủ hoặc xử lý lỗi sai, nó có thể làm thay đổi hợp đồng nghiệp vụ.

**Decorator không nhất thiết chỉ dành cho logging.** Nó có thể bổ sung cache, kiểm tra input, mã hóa hoặc chính sách retry khi những hành vi đó được quyết định tường minh. Tuy nhiên, việc chọn hành vi nào an toàn để bọc vẫn là trách nhiệm thiết kế, không phải ưu điểm tự động của pattern.

## 3. Framework proxy: hành vi được kích hoạt tại ranh giới interception

Trong nhiều framework hỗ trợ AOP/interceptor, container có thể **trả về proxy thay vì trả trực tiếp target**. Caller gọi method qua proxy; proxy áp dụng advice rồi ủy quyền cho target.

~~~mermaid
sequenceDiagram
    participant Client as Consumer
    participant Proxy as Framework proxy
    participant Advice as Interceptor
    participant Target as Target service

    Client->>Proxy: send(...)
    Proxy->>Advice: before / enter
    Advice->>Target: invoke send(...)
    Target-->>Advice: result / exception
    Advice-->>Proxy: after / error policy
    Proxy-->>Client: result / exception
~~~

Ví dụ về **Spring AOP**: tùy cấu hình và khả năng của target, framework có thể dùng proxy dựa trên interface (JDK dynamic proxy) hoặc proxy dựa trên class. Một lời gọi đi **qua proxy** có thể được áp dụng advice; lời gọi **nội bộ trên chính target** không nhất thiết đi qua proxy đó. Cơ chế weaving như AspectJ có thể có semantics khác, vì vậy **không áp dụng quy tắc của một cơ chế proxy cho mọi loại AOP**.

### Proxy không đồng nghĩa “đoạn mã không có thật”

Proxy vẫn là một object có identity, type và vòng đời cụ thể. Nó có thể triển khai một số interface của target hoặc là một subclass có giới hạn. Caller có thể không nhìn thấy cách proxy được tạo, nhưng **các giới hạn của runtime dispatch vẫn tồn tại**:

- **JDK dynamic proxy** hoạt động dựa trên interface; mã client chỉ thấy những giao diện được proxy triển khai.
- **Class-based proxy** thường có những hạn chế liên quan đến class/method `final`, constructor, phương thức private hoặc khả năng override, tùy công nghệ.
- **Các method được intercept** phụ thuộc cấu hình pointcut, annotation, visibility và cơ chế cụ thể.
- **Một object tạo thủ công bên ngoài container** không mặc nhiên được áp dụng interceptor cấu hình cho bean do container quản lý.

Nói “đã thêm annotation nên chắc chắn có transaction/retry” là chưa đủ. Cần xem **bean được tạo ở đâu, caller giữ reference nào, phương thức có đi qua proxy hay không**.

## 4. Bảng so sánh: Decorator và proxy do framework tạo

| Góc nhìn | Decorator tường minh | Framework proxy |
| --- | --- | --- |
| **Ai tạo?** | Composition root/factory của ứng dụng | Container/framework theo registration và cấu hình |
| **Hành vi nằm ở đâu?** | Trong lớp decorator cụ thể | Trong interceptor/advice và cấu hình interception |
| **Khi nào được kích hoạt?** | Khi caller gọi qua instance decorator | Khi lời gọi đi qua proxy tại điểm cắt được cấu hình |
| **Interface/class** | Thường triển khai cùng interface với delegate | Phụ thuộc JDK proxy, class-based proxy hoặc weaving |
| **Khả năng nhìn thấy từ wiring** | Rất rõ: `new LoggingSender(target)` | Có thể ẩn sau `getBean`, annotation hoặc cấu hình container |
| **Thay đổi thứ tự** | Đổi trật tự lồng decorator | Đổi thứ tự interceptor/advisor theo quy tắc framework |
| **Unit test thuần Java** | Có thể tạo decorator trực tiếp | Có thể test target riêng; behavior proxy cần test cấu hình hoặc proxy |
| **Self-invocation** | Phải xem method gọi qua wrapper hay trực tiếp delegate | Proxy-based AOP thường bỏ qua lời gọi nội bộ trên target |
| **Scope/lifecycle** | Do người lắp ghép quyết định | Do registration, container và ownership quy định |
| **Khả năng dùng ngoài framework** | Cao nếu chỉ dựa vào interface Java | Cần cơ chế proxy/interception tương ứng |

**Lưu ý về thuật ngữ:** decorator cũng là một hình thức *wrapper*, và một proxy thủ công cũng có thể tự viết bằng một class bình thường. Ranh giới ở đây là **cách ứng dụng chủ động gắn hành vi bằng decorator cụ thể** so với **cơ chế framework tạo proxy và áp dụng advice theo cấu hình**. Chúng không phải hai thế giới hoàn toàn không giao nhau.

## 5. Ví dụ Java 17 hoàn chỉnh: decorator, dynamic proxy và hành vi thực tế

Để quan sát thứ tự xử lý, ta sẽ tự tạo một decorator ghi `decorator.before/after/error`, rồi bọc decorator bằng JDK dynamic proxy ghi `proxy.before/after/error`. Cuối cùng, một interface khác minh họa **self-invocation** không đi qua proxy.

Ví dụ dùng `java.lang.reflect.Proxy` của JDK, không cần Spring, Byte Buddy, Mockito hoặc DI container. Nó **minh họa một đặc điểm của proxy-based interception**, không giả lập đầy đủ bất kỳ framework nào.

Lưu toàn bộ mã vào `Main.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

record Delivery(String orderId, String message) {}

interface MessageSender {
    void send(String orderId, String message);
}

final class RecordingSender implements MessageSender {
    private final List<String> trace;
    private final List<Delivery> delivered = new ArrayList<>();
    private boolean failOnSend;

    RecordingSender(List<String> trace) {
        this.trace = Objects.requireNonNull(trace, "trace");
    }

    void setFailOnSend(boolean value) {
        failOnSend = value;
    }

    @Override
    public void send(String orderId, String message) {
        if (failOnSend) {
            trace.add("adapter.fail:" + orderId);
            throw new IllegalStateException("Delivery unavailable");
        }
        delivered.add(new Delivery(orderId, message));
        trace.add("adapter.send:" + orderId);
    }

    List<Delivery> delivered() {
        return List.copyOf(delivered);
    }
}

final class LoggingSender implements MessageSender {
    private final MessageSender delegate;
    private final List<String> trace;

    LoggingSender(MessageSender delegate, List<String> trace) {
        this.delegate = Objects.requireNonNull(delegate, "delegate");
        this.trace = Objects.requireNonNull(trace, "trace");
    }

    @Override
    public void send(String orderId, String message) {
        trace.add("decorator.before:" + orderId);
        try {
            delegate.send(orderId, message);
            trace.add("decorator.after:" + orderId);
        } catch (RuntimeException error) {
            trace.add("decorator.error:" + orderId);
            throw error;
        }
    }
}

// Mô phỏng cơ chế framework proxy bằng API chuẩn của JDK.
// Chỉ bọc interface và theo dõi các lời gọi đi qua proxy.
final class TraceProxy {
    private TraceProxy() {}

    static <T> T wrap(Class<T> port, T target, List<String> trace) {
        Objects.requireNonNull(port, "port");
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(trace, "trace");
        if (!port.isInterface() || !port.isInstance(target)) {
            throw new IllegalArgumentException("Expected compatible interface");
        }

        Object proxy = Proxy.newProxyInstance(
                port.getClassLoader(),
                new Class<?>[] {port},
                (self, method, args) -> {
                    // Các method thuộc Object cần semantics riêng.
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "equals" -> self == args[0];
                            case "hashCode" -> System.identityHashCode(self);
                            case "toString" -> "TraceProxy("
                                    + port.getSimpleName() + ")";
                            default -> throw new UnsupportedOperationException(
                                    method.getName());
                        };
                    }

                    trace.add("proxy.before:" + method.getName());
                    try {
                        Object result = method.invoke(target, args);
                        trace.add("proxy.after:" + method.getName());
                        return result;
                    } catch (InvocationTargetException error) {
                        trace.add("proxy.error:" + method.getName());
                        // Không để caller nhận nhầm wrapper reflection.
                        throw error.getCause();
                    }
                });
        return port.cast(proxy);
    }
}

final class OrderNotifier {
    private final MessageSender sender;

    OrderNotifier(MessageSender sender) {
        this.sender = Objects.requireNonNull(sender, "sender");
    }

    void notifyCustomer(String orderId, String message) {
        sender.send(orderId, message);
    }
}

interface BatchJob {
    void runOne(String id);
    void runBatch(String id);
}

final class PlainBatchJob implements BatchJob {
    private final List<String> trace;

    PlainBatchJob(List<String> trace) {
        this.trace = trace;
    }

    @Override
    public void runOne(String id) {
        trace.add("job.one:" + id);
    }

    @Override
    public void runBatch(String id) {
        trace.add("job.batch:" + id);
        runOne(id); // Gọi trên chính target, không quay qua proxy.
    }
}

public class Main {
    public static void main(String[] args) {
        List<String> trace = new ArrayList<>();
        RecordingSender adapter = new RecordingSender(trace);

        // Composition root: chọn thứ tự lắp ghép rõ ràng.
        MessageSender decorated = new LoggingSender(adapter, trace);
        MessageSender observed = TraceProxy.wrap(
                MessageSender.class, decorated, trace);
        OrderNotifier notifier = new OrderNotifier(observed);

        notifier.notifyCustomer("O-1", "ready");

        check(adapter.delivered().equals(
                List.of(new Delivery("O-1", "ready"))),
                "Thông báo phải được chuyển đến adapter đúng một lần");
        check(trace.equals(List.of(
                "proxy.before:send",
                "decorator.before:O-1",
                "adapter.send:O-1",
                "decorator.after:O-1",
                "proxy.after:send"
        )), "Sai thứ tự wrapper: " + trace);

        check(observed != decorated && decorated != adapter,
                "Proxy, decorator và target là các reference riêng");

        // Lỗi từ target vẫn đi qua decorator và proxy.
        trace.clear();
        adapter.setFailOnSend(true);
        boolean failed = false;
        try {
            notifier.notifyCustomer("O-2", "ready");
        } catch (IllegalStateException expected) {
            failed = true;
        }
        check(failed, "Phải chuyển đúng lỗi từ adapter ra caller");
        check(adapter.delivered().size() == 1,
                "Lỗi không được tạo thêm một lần gửi thành công");
        check(trace.equals(List.of(
                "proxy.before:send",
                "decorator.before:O-2",
                "adapter.fail:O-2",
                "decorator.error:O-2",
                "proxy.error:send"
        )), "Sai luồng lỗi của wrapper: " + trace);

        // Self-invocation: runBatch gọi runOne trên chính target.
        trace.clear();
        BatchJob job = TraceProxy.wrap(
                BatchJob.class, new PlainBatchJob(trace), trace);
        job.runBatch("B-1");
        check(trace.equals(List.of(
                "proxy.before:runBatch",
                "job.batch:B-1",
                "job.one:B-1",
                "proxy.after:runBatch"
        )), "Lời gọi nội bộ không được đi qua proxy: " + trace);

        // Lời gọi runOne từ ngoài qua proxy lại được intercept.
        trace.clear();
        job.runOne("B-2");
        check(trace.equals(List.of(
                "proxy.before:runOne",
                "job.one:B-2",
                "proxy.after:runOne"
        )), "Lời gọi công khai qua proxy phải được intercept");

        System.out.println("PASS");
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 Main.java
java Main
~~~

Kết quả mong đợi:

~~~text
PASS
~~~

Ví dụ kiểm tra ba điều khác nhau:

1. **Kết quả nghiệp vụ:** thông báo được đưa tới adapter đúng nội dung; khi adapter lỗi, không có lần gửi thành công mới.
2. **Thứ tự kết hợp:** caller đi qua proxy trước, rồi decorator, rồi adapter; đường trả về chạy ngược lại.
3. **Ranh giới interception:** `job.runBatch(...)` đi qua proxy, nhưng `runOne(...)` được gọi **nội bộ trong target** không sinh một cặp `proxy.before/after:runOne` mới.

Ở đây trace được kiểm tra chi tiết vì **mục đích bài thực hành chính là quan sát wrapper/interceptor**. Trong unit test của nghiệp vụ, thường nên ưu tiên **kết quả và side effect có ý nghĩa** thay vì gắn cứng vào số lượng hoặc thứ tự mọi lời gọi nội bộ.

### Vì sao TraceProxy xử lý Object methods và ngoại lệ?

`java.lang.reflect.Proxy` chuyển những lời gọi phù hợp qua `InvocationHandler`. Một proxy thực tế cần cân nhắc `equals`, `hashCode` và `toString` để tránh semantics bất ngờ. Ví dụ này dùng **identity semantics của chính proxy**; nó không khẳng định đây là chính sách duy nhất hợp lệ cho mọi framework.

Ngoài ra, `Method.invoke(...)` bọc lỗi ném từ target trong `InvocationTargetException`. Ví dụ **mở wrapper đó và ném nguyên nhân gốc** để caller nhận đúng `IllegalStateException`. Nếu không xử lý, hành vi ngoại lệ có thể khác với lời gọi trực tiếp. Các framework có thể có chính sách chuyển đổi ngoại lệ và invocation riêng; cần xem hợp đồng thực tế.

**Không nên dùng proxy reflection này cho production.** Nó không giải quyết đầy đủ vấn đề method accessibility, default methods, checked exceptions, async, object identity/lifecycle, annotation, transaction hoặc class-based interception. Nó chỉ là một mô hình tối thiểu giúp học cách lời gọi đi qua điểm chặn.

## 6. Self-invocation: lý do annotation có thể “không chạy”

Đây là điểm dễ gây nhầm nhất khi bắt đầu dùng proxy-based AOP. Giả sử một service có hai phương thức:

~~~java
// Sơ đồ ý tưởng, annotation chỉ minh họa cho framework phù hợp.
class AccountService {
    void transfer() {
        debit(); // this.debit() trên target.
    }

    @Transactional
    void debit() {
        // cập nhật tài khoản
    }
}
~~~

Nếu framework dùng **proxy interception** và caller gọi `transfer()` **qua proxy**, advice gắn với `transfer()` (nếu phù hợp) có thể chạy. Tuy nhiên, khi **target tự gọi `this.debit()`**, lời gọi không đi qua proxy bên ngoài, nên advice gắn riêng với `debit()` có thể **không được kích hoạt**.

Trong Spring proxy-based AOP, đây là hiện tượng *self-invocation bypasses advice*. Nó không có nghĩa annotation sai về cú pháp hay DI “không hoạt động”; nguyên nhân nằm ở **đường đi của lời gọi**.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy
    participant Target
    Caller->>Proxy: transfer()
    Proxy->>Target: transfer()
    Target->>Target: this.debit()
    Note over Target: Không đi qua proxy tại debit()
    Target-->>Proxy: return
    Proxy-->>Caller: return
~~~

Cần phân biệt:

- **Gọi từ consumer qua proxy:** có thể kích hoạt interceptor của phương thức phù hợp.
- **Gọi trực tiếp trên target:** có thể bỏ qua proxy.
- **Gọi một method khác trên chính target:** cũng có thể bypass advice khi proxy là điểm chặn duy nhất.
- **Weaving ở mức bytecode** có thể can thiệp theo cách khác; quy tắc self-invocation của proxy **không phải định luật cho mọi cơ chế AOP**.

### Cách xử lý có chủ đích

Nếu cần một chính sách như transaction hoặc retry bảo vệ từng thao tác, hãy cân nhắc:

1. **Đặt ranh giới giao dịch ở phương thức được caller gọi qua proxy.** Nếu `transfer()` là use case cần transaction, khai báo và kiểm tra policy tại ranh giới đó.
2. **Tách trách nhiệm sang một collaborator khác** rồi inject nó; lời gọi từ service này sang service khác qua proxy có thể kích hoạt advice phù hợp.
3. **Chọn API tường minh** như template/transaction runner/decorator khi muốn ranh giới hành vi dễ nhìn trong mã.
4. **Chỉ dùng cơ chế gọi lại proxy/self-injection** nếu hiểu rõ sự phụ thuộc vào framework và có test chứng minh. Nó không phải giải pháp mặc định cho mọi self-invocation.

Đặc biệt, **retry** một phương thức có side effect không phải lúc nào cũng an toàn. Proxy có chạy advice không chỉ là câu hỏi kỹ thuật; cần thêm điều kiện **idempotency** và hợp đồng lỗi.

## 7. Thứ tự wrapper quyết định phạm vi hành vi

Decorator và proxy có thể được kết hợp:

~~~text
Caller → Proxy(metrics) → Decorator(logging) → Adapter
~~~

hoặc:

~~~text
Caller → Decorator(logging) → Proxy(metrics) → Adapter
~~~

Hai cách có thể tạo **trace khác nhau**, kể cả khi kết quả gửi giống nhau.

Ví dụ, nếu logging đứng bên ngoài retry, một lời gọi nghiệp vụ có thể được log một lần dù bên trong retry gửi nhiều lần. Nếu logging đứng bên trong retry, mỗi lần thử lại có thể được log riêng. Nếu transaction bao ngoài retry hoặc ngược lại, ranh giới transaction cũng có thể thay đổi đáng kể. Vì thế, **thứ tự không chỉ là hình thức** khi các lớp bọc có tác dụng phụ hoặc chính sách lỗi.

Một bảng tư duy:

| Hành vi | Khi đứng ngoài một lớp retry | Khi đứng bên trong lớp retry |
| --- | --- | --- |
| Logging | Có thể ghi một lần cho toàn bộ lời gọi | Có thể ghi cho từng lần thử |
| Metrics | Có thể đo tổng thời gian bao gồm retry | Có thể đo mỗi lần thử độc lập |
| Transaction | Có thể giữ một transaction qua nhiều lần thử, có rủi ro tùy công nghệ | Có thể tạo transaction riêng cho từng attempt |
| Authorization | Kiểm tra trước toàn bộ quá trình | Có thể kiểm tra lại mỗi attempt |

Đây là **khả năng** phụ thuộc implementation, không phải cam kết mặc định của mọi framework. Trong Spring hoặc các container khác, cần xem **thứ tự advisor/interceptor** và quy tắc proxy chain của hệ thống đang sử dụng. Trong DI thủ công, đọc các lệnh tạo wrapper ở composition root thường đủ để biết thứ tự.

## 8. Scope, identity và vòng đời: ai sở hữu lớp bọc và target?

Một lớp bọc và target là **hai object khác nhau**. DI container có thể cấp một proxy singleton-scoped cho consumer, trong khi cơ chế bên trong tham chiếu tới một target có scope khác thông qua provider. Đây là một chiến lược riêng của framework; không thể suy rằng mọi proxy và target luôn cùng instance hoặc cùng scope.

Hãy xác định:

- **Scope của consumer:** nhận proxy/decorator mỗi request hay dùng chung toàn ứng dụng?
- **Scope của wrapper/proxy:** một instance chung hay tạo mới?
- **Scope của target:** stateful theo request, stateless dùng chung hay tạo mới theo lời gọi?
- **Thread safety:** interceptor có giữ bộ đếm, cache hoặc state mutable không? Có đồng bộ hóa phù hợp không?
- **Ownership:** nếu target giữ socket/file/pool, ai có trách nhiệm đóng và khi nào?
- **Identity:** consumer so sánh `proxy == target` có thể sai dù chúng cùng thực thi một hợp đồng.

### Tránh đóng tài nguyên hai lần

Một decorator do composition root tạo để bọc HTTP client **không nên tự ý đóng client** khi consumer vẫn sử dụng ở nơi khác. Nếu wrapper thực hiện `AutoCloseable` và nhận ownership của target, phải **công bố rõ việc chuyển giao**; nếu chỉ mượn delegate, wrapper không được đóng delegate.

Với framework proxy, object lifecycle nên được quản lý theo registration và contract của framework; đừng gọi `close()` trên bean dùng chung sau mỗi request chỉ vì nó được truy cập qua proxy. Trong DI thủ công, composition root/lifecycle manager chịu trách nhiệm điều phối những resource ứng dụng sở hữu.

### Không biến một dependency ngắn hạn thành singleton chỉ để proxy hoạt động

Một service toàn ứng dụng có thể dùng proxy/provider để lấy request context hiện hành; nhưng giữ trực tiếp **request context của lần đầu** trong trường singleton sẽ làm lẫn trạng thái và truy cập resource đã hết scope. Proxy không tự sửa được một thiết kế scope sai.

## 9. Khi nào nên chọn decorator, khi nào nên chọn framework proxy?

**Ưu tiên decorator tường minh** khi hành vi gắn với một port cụ thể, cần thấy rõ trong composition root, muốn dùng ngoài framework hoặc muốn unit test thuần Java dễ kiểm soát. Ví dụ: `CachingCatalogRepository` bọc `CatalogRepository`, hoặc `LoggingPaymentGateway` bao một cổng thanh toán có hợp đồng rõ.

**Cân nhắc framework proxy** khi có một chính sách cắt ngang lặp lại trên nhiều component và framework đã cung cấp lifecycle, pointcut, thứ tự interceptor và công cụ tích hợp phù hợp. Ví dụ: transaction của một tầng dịch vụ, authorization ở ranh giới được định nghĩa, hoặc giám sát được tích hợp trong framework.

**Kết hợp cả hai** khi muốn logic riêng cho một port được đóng gói bằng decorator, còn chính sách hạ tầng chung được áp dụng bởi container. Khi làm vậy, vẫn phải chỉ rõ **thứ tự áp dụng**, scope và các trường hợp bypass.

**Tránh áp dụng cơ chế chỉ vì ngắn mã.** Một annotation transaction chỉ có giá trị khi lời gọi thực sự đi qua cơ chế intercept tương ứng, transaction manager được cấu hình đúng và nghiệp vụ hiểu rõ ranh giới commit/rollback.

## 10. Kiểm thử: tách kết quả nghiệp vụ khỏi cơ chế gắn hành vi

Có ba nhóm test bổ sung cho nhau:

1. **Unit test của target:** truyền fake dependency qua constructor, kiểm tra giá trị trả về, trạng thái và side effect hợp đồng. Không cần DI container.
2. **Unit test của decorator:** truyền fake delegate, kiểm tra delegate nhận đúng input, output/exception được bảo toàn và hành vi bổ sung được thực hiện khi cần.
3. **Integration test của proxy/configuration:** tạo context/framework thực, gọi qua reference mà consumer nhận và kiểm tra advice/transaction/retry/authorization được kích hoạt đúng ở ranh giới mong đợi.

Một test dùng `new AccountService(...)` không thể chứng minh `@Transactional` hoạt động, vì object ấy có thể **không được framework proxy**. Muốn kiểm chứng chính sách proxy, test cần lấy đúng bean/proxy từ container hoặc dùng cơ chế interception thực được cấu hình.

| Câu hỏi kiểm thử | Test phù hợp |
| --- | --- |
| Đơn hàng được xử lý đúng dữ liệu? | Unit test target với fake |
| Decorator ghi event đúng khi delegate lỗi? | Unit test decorator |
| Consumer thật có nhận proxy đã cấu hình? | Wiring/integration test |
| Self-invocation có đi qua advice không? | Test đường gọi qua proxy và nội bộ |
| Transaction có rollback khi lỗi được công bố? | Integration test với transaction manager và lưu trữ phù hợp |
| Hai wrapper có đang đóng nhầm cùng resource? | Test lifecycle và ownership |

Trong ví dụ `Main.java`, ta cố ý assert trace vì **bài học cần chứng minh thứ tự wrapper và interception**. Trong test của `OrderNotifier`, yêu cầu quan trọng hơn thường là “thông báo đúng được gửi, lỗi được chuyển ra” thay vì “proxy.before được ghi đúng một dòng”.

## 11. Những lỗi thiết kế và hiểu nhầm cần tránh

### 11.1. Gọi target trực tiếp rồi mong framework advice chạy

~~~java
// Minh họa ý tưởng; target ở đây là object thuần.
AccountService target = new AccountService();
target.transfer(); // Không bảo đảm có proxy/interceptor.
~~~

Một service do `new` tạo bên ngoài container không mặc nhiên chịu các chính sách AOP đăng ký cho managed bean.

### 11.2. Đặt annotation lên method rồi gọi qua this

Trong proxy-based AOP, `this.someMethod()` thường không đi qua proxy. Kiểm tra lại **ranh giới gọi**, không chỉ chú thích trên method.

### 11.3. Tin rằng interface proxy là subclass của implementation

JDK dynamic proxy triển khai interface; nó **không phải instance của concrete target class**. Nếu injection yêu cầu concrete class nhưng container cấp JDK proxy chỉ triển khai interface, có thể phát sinh vấn đề về kiểu. Thiết kế consumer phụ thuộc vào abstraction phù hợp.

### 11.4. Dùng decorator nhưng quên chuyển tiếp đầy đủ hợp đồng

Decorator có thể nuốt exception, gửi hai lần hoặc thay đổi input ngoài ý muốn. Test phải kiểm chứng **hành vi công khai**, không chỉ log.

### 11.5. Gắn retry mà không xem xét idempotency

Một proxy hoặc decorator có thể chạy lại lời gọi thanh toán. Nếu không có idempotency key và chính sách lỗi phù hợp, retry có thể gây double charge. Kỹ thuật gắn hành vi không thay thế quyết định nghiệp vụ.

### 11.6. Không quan tâm thứ tự interceptor

Metrics ngoài retry đo tổng thời gian, metrics trong retry đo từng lần thử; transaction quanh retry khác transaction trên từng attempt. Xác minh thứ tự đã cấu hình và hậu quả vận hành.

### 11.7. Giữ state request trong interceptor singleton

Một interceptor dùng chung không nên giữ thông tin người dùng/request trước đó trong trường mutable mà không có cơ chế cô lập. Scope và thread safety vẫn cần được thiết kế.

### 11.8. Lẫn lộn ownership của wrapper và target

Proxy/decorator không tự có quyền đóng mọi tài nguyên mà target sử dụng. Dọn dẹp phải tuân theo hợp đồng của composition root hoặc DI container, tránh đóng sớm và đóng hai lần.

## 12. Bài tập thực hành

**Bài 1 — Viết decorator:** bổ sung `MetricsSender` triển khai `MessageSender`, nhận delegate và recorder, ghi số lần thành công/thất bại. Chứng minh `OrderNotifier` không cần sửa khi thay `RecordingSender` bằng chuỗi wrapper.

**Bài 2 — Đổi thứ tự:** thay wiring thành `LoggingSender(TraceProxy.wrap(adapter))`. Dự đoán trace cho thành công và lỗi; so sánh với kết quả của ví dụ `Main.java` và giải thích sự khác biệt.

**Bài 3 — Tìm self-invocation:** một service có `createInvoice()` gọi `saveInvoice()` trong chính class; chỉ `saveInvoice()` được cấu hình transaction advice qua proxy. Phân tích vì sao transaction có thể không được kích hoạt khi gọi `createInvoice()` qua proxy và đề xuất thay đổi ranh giới hoặc tách collaborator.

**Bài 4 — Scope/lifecycle:** composition root tạo pool dùng chung, một decorator log mỗi request và một proxy framework bọc service. Xác định owner của pool, scope của logger có state request và ai đóng từng resource.

**Bài 5 — Chọn test:** phân biệt unit test cần assert kết quả gửi thông báo với integration test cần assert transaction advice thực sự chạy qua container. Giải thích vì sao `new` target trong unit test không chứng minh annotation AOP.

## 13. Tự kiểm tra hiểu bài

**Câu 1.** Decorator có bắt buộc phải dùng DI container không? **Không.** Có thể tạo bằng `new` và constructor injection tại composition root.

**Câu 2.** Proxy của framework có phải lúc nào cũng là JDK dynamic proxy không? **Không.** Tùy framework và cấu hình, có thể dùng interface-based proxy, class-based proxy hoặc các cơ chế interception/weaving khác.

**Câu 3.** Vì sao một method có advice vẫn không được intercept khi gọi nội bộ trên target? **Vì** trong proxy-based AOP, lời gọi `this.method()` không đi qua reference proxy bên ngoài; cơ chế weaving có thể khác.

**Câu 4.** Thứ tự của logging và retry có ảnh hưởng không? **Có thể có.** Logging bên ngoài có thể ghi một lượt cho toàn bộ nghiệp vụ, bên trong có thể ghi cho từng attempt; phải kiểm tra implementation cụ thể.

**Câu 5.** Unit test target bằng fake có chứng minh transaction annotation được áp dụng không? **Không.** Cần test ở ranh giới container/proxy thực sự áp dụng advice.

**Câu 6.** Có thể đặt decorator trước hoặc sau proxy không? **Có**, nếu các hợp đồng và cấu hình cho phép; nhưng thứ tự có thể thay đổi semantics của lỗi, metrics, retry, transaction và ownership.

## Ghi nhớ

- **Decorator** là một wrapper tường minh, thường triển khai cùng interface và nhận delegate qua constructor. Composition root quyết định lúc nào bọc và bọc theo thứ tự nào.
- **Framework proxy** chặn lời gọi tại ranh giới proxy theo cấu hình interceptor/advice. Không phải mọi lời gọi tới target đều đi qua proxy, đặc biệt **self-invocation** trong proxy-based AOP.
- **Hai cơ chế đều có thể gắn hành vi cắt ngang**, nhưng khác nhau ở quyền kiểm soát lắp ghép, khả năng quan sát, yêu cầu runtime và phạm vi interception.
- **Thứ tự wrapper, scope, thread safety và ownership** có thể làm thay đổi kết quả, lỗi và vòng đời tài nguyên; không chỉ là chi tiết cấu hình.
- **Dùng Java thuần để hiểu constructor injection và decorator trước**, rồi kiểm thử chính sách proxy/framework ở đúng ranh giới container khi mở rộng hệ thống.
