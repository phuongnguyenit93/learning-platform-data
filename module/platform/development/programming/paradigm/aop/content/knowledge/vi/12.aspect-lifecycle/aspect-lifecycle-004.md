# Thời điểm tạo, khởi tạo và giải phóng aspect

## 1. Vì sao cần hiểu vòng đời của aspect?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **aspect** tổ chức các mối quan tâm cắt ngang như ghi audit, đo thời gian, kiểm soát truy cập và tracing. **Pointcut** chọn những *join point* có thể can thiệp; **advice** mô tả hành vi được thực thi tại đó. Tuy nhiên, khái niệm “một aspect” không tự nói rõ **đối tượng chứa trạng thái advice tồn tại trong bao lâu, được tạo lúc nào và được giải phóng bởi ai**.

Đây là ba việc khác nhau:

1. **Tạo (creation/instantiation):** có một instance của thành phần aspect, interceptor hoặc state holder; các field nhận giá trị mặc định và constructor hoặc cơ chế tương đương có thể chạy.
2. **Khởi tạo (initialization):** chuẩn bị cấu hình, các phụ thuộc và tài nguyên cần dùng cho advice, ví dụ bộ đếm, sink metrics hoặc trạng thái theo target. Việc này có thể nằm trong constructor hoặc một bước riêng.
3. **Giải phóng (disposal/cleanup):** ngừng tiếp nhận thao tác mới khi thích hợp, đóng tài nguyên, flush có kiểm soát, loại đăng ký interceptor và loại bỏ tham chiếu sở hữu. Đây **không đồng nghĩa chỉ chờ garbage collection (GC)**.

**Không có một vòng đời duy nhất áp dụng cho tất cả công cụ AOP.** Một engine weaving có thể hỗ trợ một instance dùng chung, instance gắn với từng đối tượng, hoặc một phạm vi điều khiển động; một proxy có thể được tạo mỗi khi factory chạy; một advice không có trạng thái có thể không cần instance đặc biệt. Phải đọc mô hình instantiation và ownership thực tế của công nghệ đang sử dụng.

### Tình huống mở đầu

Một hệ thống đo thời gian gọi `paymentService.pay()` nhiều lần. Nếu aspect lưu `startedAt` trong field dùng chung, hai request đồng thời có thể ghi đè mốc nhau. Nếu tạo một metrics client cho **mỗi invocation** nhưng không đóng nó, hệ thống rò tài nguyên. Nếu đóng shared metrics client ngay khi một target được dừng, các target khác có thể bị lỗi. Cả ba đều là lỗi **chọn sai vòng đời và chủ sở hữu** hơn là lỗi cú pháp pointcut.

Bài này tập trung vào **vòng đời aspect AOP nói chung**: thời điểm instance được tạo, initialization, trạng thái, phạm vi, threading, dọn dẹp, proxy/weaving, classloader, bất đồng bộ và kiểm thử. Ví dụ Java 17 chạy độc lập là **mô phỏng các phạm vi quản lý vòng đời bằng JDK proxy**, không tự nhận là bộ bytecode weaver.

## 2. Năm mốc thời gian dễ bị nhập làm một

Một luồng AOP có thể trải qua những mốc:

~~~text
T0: Định nghĩa aspect, pointcut và advice trong source/config
 |
T1: Kết hợp AOP: build-time weaving / load-time weaving / tạo proxy
 |
T2: Tạo một aspect instance hoặc state holder, nếu mô hình yêu cầu
 |
T3: Khởi tạo tài nguyên, hoàn tất registration và sẵn sàng nhận call
 |
T4: Join point xuất hiện -> advice thực thi (nhiều lần)
 |
T5: Ngừng sử dụng phạm vi, cleanup/disposal; GC có thể diễn ra muộn hơn
~~~

**Thời điểm weaving không bắt buộc là thời điểm tạo aspect instance.** Compile-time weaving có thể hoàn tất trước khi chương trình chạy; mã đã dệt chỉ tạo instance hay gọi advice khi một class được khởi tạo hoặc một join point xuất hiện. Load-time weaving có thể biến đổi class trước lúc chạy method; việc biến đổi bytecode cũng không tự có nghĩa “constructor của aspect chạy đúng một lần lúc class load”.

Ở chiều khác, một proxy có thể được tạo lúc khởi động nhưng chỉ **gọi advice** khi request đến. Một proxy được factory tạo theo yêu cầu có thể được tạo muộn hơn. Một aspect **stateless** có thể dùng hàm static hoặc object shared mà không có tài nguyên cần đóng.

Vì vậy, phải tách tối thiểu bốn câu hỏi:

- **Installation:** pointcut và advice được lắp/biên dịch/dệt vào đường chạy vào lúc nào?
- **Instantiation:** khi nào và bao nhiêu instance/state holder được tạo?
- **Invocation:** một advice thực sự chạy bao nhiêu lần, trong phạm vi nào?
- **Disposal:** sự kiện nào kết thúc quyền sở hữu và ai chịu trách nhiệm cleanup?

Không trả lời những câu này bằng suy đoán dựa trên từ “Aspect” hoặc từ “singleton”. **Scope phụ thuộc engine và cách cấu hình**, không phải một quy tắc phổ quát của AOP.

## 3. Vòng đời cơ bản và ý nghĩa các giai đoạn

| Giai đoạn | Hoạt động có thể xảy ra | Rủi ro nếu hiểu sai |
| --- | --- | --- |
| **Definition** | Viết pointcut, advice, luật thứ tự | Tưởng định nghĩa đã tự chạy advice |
| **Installation/weaving** | Biến đổi bytecode, tạo proxy, đăng ký interceptor | Pointcut không được đưa vào đúng đường gọi |
| **Creation** | Cấp phát instance, thiết lập field mặc định | Tạo nhiều instance ngoài dự kiến |
| **Initialization** | Constructor, inject dependency, mở tài nguyên có giới hạn | Object bị đưa ra dùng trước khi sẵn sàng |
| **Activation** | Advice chạy tại join point | Nhầm số lần advice với số instance |
| **Operation** | Nhiều lời gọi, đồng thời, retry, nested invocation | State dùng chung bị ghi đè hoặc không thread-safe |
| **Deactivation** | Ngừng chọn/gọi advice, ngừng tạo request mới | In-flight call vẫn còn dùng tài nguyên |
| **Disposal** | Cleanup, close, flush, unregister | Rò tài nguyên, mất dữ liệu hoặc đóng quá sớm |
| **GC/unloading** | JVM thu gom object/classloader khi không còn giữ | Không phải lời hứa thời điểm cleanup |

Một constructor chạy đúng một lần **cho mỗi object được tạo**, nhưng có thể có nhiều object. Một advice `before` có thể chạy hàng nghìn lần trên **cùng aspect instance**. Ngược lại, một per-invocation state có thể được tạo mỗi lần advice chạy. Nếu cần kiểm chứng, đếm **constructor, advice entries và close** độc lập.

## 4. Scope quyết định số instance và vòng đời

Các mô hình quản lý aspect/state có thể được khái quát như sau. Tên gọi cụ thể ở các engine có thể khác; chỉ dùng chúng như **kiểu phạm vi kiến trúc**, không khẳng định API của mọi thư viện.

| Scope/strategy | Một instance tồn tại cho | Mốc tạo điển hình | Mốc giải phóng có thể có |
| --- | --- | --- | --- |
| **Application/global** | Một vùng ứng dụng hoặc một registry | Startup hoặc lần dùng đầu tiên | Shutdown/đóng registry |
| **Per-type / classloader** | Một class hoặc một classloader scope | Lúc initialization của class hoặc lazy lookup | Classloader scope kết thúc; cleanup tường minh nếu có tài nguyên |
| **Per-target** | Một đối tượng nghiệp vụ được quản lý | Khi target được instrument hoặc proxy được tạo | Khi target/handle bị bỏ đăng ký, đóng hoặc được thu hồi |
| **Per-proxy** | Một wrapper được tạo riêng | Khi factory tạo proxy | Khi wrapper owner đóng/hủy |
| **Per-invocation** | Một lần advice/join point invocation | Khi vào phạm vi gọi | `finally` hoặc sau khi completion theo định nghĩa |
| **Per-control-flow** | Một chuỗi lời gọi động có điểm bắt đầu/chấm dứt | Khi vào luồng điều khiển đã chọn | Khi rời luồng, kể cả exceptional exit |
| **Pooled / keyed** | Một tập instance tái sử dụng hoặc theo khóa | Tạo trước hoặc theo nhu cầu | Khi pool/key hết hạn và không còn người dùng |
| **Stateless/static** | Có thể không cần instance trạng thái riêng | Tùy cách biên dịch/gọi | Thường không có cleanup gắn với state, nhưng dependency bên ngoài vẫn có |

**Một instance per target không có nghĩa một invocation.** Target có thể nhận nhiều request. **Một instance shared không có nghĩa advice chỉ chạy một lần.** Instance và invocation là hai trục riêng.

### 4.1. Global hoặc singleton-like aspect

Một state holder chung có thể tiết kiệm khởi tạo tài nguyên đắt tiền và tập trung metrics. Nó cũng là nơi nguy hiểm khi lưu dữ liệu gắn với **một lời gọi** trong field mutable:

~~~java
// Pseudocode cấu trúc có vấn đề: một field dùng chung
class SharedTimer {
    long startedAt;

    void before() {
        startedAt = System.nanoTime();
    }

    void after() {
        record(System.nanoTime() - startedAt);
    }
}
~~~

Đây là **đoạn minh họa không độc lập** vì `record` chưa được định nghĩa. Nếu hai thread chạy `before` xen kẽ, chúng có thể dùng sai mốc thời gian. Hãy lưu dữ liệu theo invocation trong local variable, context đúng scope hoặc cấu trúc concurrency phù hợp. Với bộ đếm chia sẻ, `AtomicLong`/`LongAdder` có thể cần thiết, nhưng lựa chọn còn tùy số liệu và mức chính xác.

### 4.2. Per-target aspect

Một per-target aspect có thể giữ cấu hình liên quan đối tượng được quan sát: tenant policy, danh tính kỹ thuật của target, hoặc tài nguyên riêng. Nhưng per-target state có thể dẫn tới:

- Số instance tăng theo số target, không theo số request.
- Một target được tái sử dụng nhiều lần sẽ dùng chung state, nên cần thread-safety.
- Nếu registry nắm tham chiếu mạnh tới target mãi, target có thể không được GC.
- Nếu aspect giữ target, dùng `WeakHashMap<Target,Aspect>` **không luôn tránh rò rỉ**: value aspect có tham chiếu ngược mạnh tới key target có thể tạo đường giữ sống qua map.
- Khi target được đóng, phải quản lý reference count/in-flight calls trước khi giải phóng resource.
- Khi proxy lồng nhau, “mỗi target” có thể được hiểu là object bên trong hay proxy bên ngoài — phải xác định bằng ownership.

### 4.3. Per-invocation aspect hoặc context

Mỗi lời gọi tạo một scope riêng giúp tránh lẫn dữ liệu khi đồng thời và recursion. Nhưng không cần tạo client mạng, thread pool hoặc resource đắt tiền **mỗi lần** nếu có thể dùng shared client thread-safe. Thông thường, context ngắn hạn chứa start time, invocation ID, counters riêng, trong khi sink metrics là dependency sống dài hơn.

Mẫu:

~~~java
long start = System.nanoTime();
try {
    return proceed();
} finally {
    recordElapsed(System.nanoTime() - start);
}
~~~

Đây là pseudocode Java minh họa, không độc lập (`proceed`/`recordElapsed` phải được cung cấp). `start` là local variable theo lần gọi, tránh chia sẻ qua thread. Nếu `recordElapsed` ném lỗi trong `finally`, nó có thể che result/exception gốc: phải định nghĩa lỗi sink theo chính sách phù hợp.

### 4.4. Per-control-flow

Một scope theo luồng điều khiển động có thể bắt đầu khi bước xử lý chính diễn ra rồi bao gồm các join point lồng trong nó. Khái niệm này có thể mang tên riêng ở những công nghệ AOP khác nhau. Nó **không tự đồng nghĩa per-thread** và cũng không đảm bảo bám theo asynchronous continuation qua thread khác.

Ví dụ:

~~~text
enter checkout() -> context A created
  validate()     -> uses context A
  reserve()      -> uses context A
leave checkout() -> context A disposed

enter checkout() again -> context B created
~~~

Nếu `checkout` gọi lại chính nó (recursion), thiết kế phải xác định một scope cho luồng ngoài hay scope lồng riêng; không có quy tắc chung. Nếu công việc chuyển sang executor thread, context propagation cần được thiết kế rõ, không dựa vào `ThreadLocal` tự động đi qua mọi thread.

## 5. “Khi nào aspect được tạo?” phụ thuộc runtime thực tế

Một số chiến lược có thể gặp:

- **Eager creation:** registry/factory tạo các instance lúc startup để phát hiện lỗi cấu hình sớm.
- **Lazy creation:** instance được tạo khi có lần gọi/target đầu tiên cần advice.
- **On-demand proxy:** wrapper được tạo khi factory cần cấp một đối tượng cho caller.
- **Class initialization:** static holder được JVM khởi tạo ở sự kiện class initialization, không phải chắc chắn ngay khi file class được nạp.
- **Instrumented code lookup:** mã đã woven truy xuất aspect instance từ một registry hoặc factory; thời điểm registry tạo instance phụ thuộc thiết kế.
- **Per-flow creation:** instance được tạo khi luồng điều khiển liên quan được khởi đầu.
- **Explicit ownership:** người gọi tạo một đối tượng advice hoặc handler và truyền nó vào factory; lifecycle theo code quản lý đối tượng.

**Class loading khác class initialization.** Trong Java, một lớp có thể được nạp/định nghĩa nhưng chưa thực hiện static initialization. Cần tránh kết luận “load-time weaver đã biến đổi class thì constructor mọi aspect đã chạy”.

Tương tự, class đã dệt ở compile-time **không nhất thiết** tạo aspect instance ngay lúc JVM khởi động. Việc weaving tạo khả năng can thiệp; việc tạo instance do mã/hợp đồng runtime quyết định.

## 6. Constructor, khởi tạo và trạng thái sẵn sàng

Một instance được tạo không có nghĩa nó đã sẵn sàng sử dụng. Có thể có các bước:

~~~text
allocate
  -> initialize fields
  -> run constructor
  -> wire validated dependencies
  -> register for interception
  -> expose to callers
~~~

Đây là một **lifecycle thiết kế**, không phải quy tắc bắt buộc của Java hay mọi engine. Thứ tự Java object construction có những quy tắc riêng về superclass/field initializers, nhưng ở mức ứng dụng cần quan tâm **không công bố instance khi chưa hoàn tất khởi tạo**.

### 6.1. Khởi tạo tài nguyên sớm hay muộn?

**Sớm:** có thể fail-fast nếu thiếu endpoint metrics hay cấu hình, nhưng kéo dài startup và có thể cấp phát resource không dùng đến.

**Muộn:** giảm công việc startup, nhưng lỗi khởi tạo có thể xuất hiện ngay trên request đầu tiên. Nếu nhiều thread đồng thời cùng lazy-create, cần đảm bảo chỉ một object được tạo hoặc có cách xử lý nhiều lần đúng; đừng dùng cờ boolean không đồng bộ rồi giả định an toàn.

### 6.2. Không để `this` thoát khi constructor chưa kết thúc

Đăng ký một callback/interceptor mang `this` với hệ thống khác trong constructor trước khi tất cả field được khởi tạo có thể làm thread khác gọi advice trên một object chưa sẵn sàng. Nếu có khả năng callback chạy ngay, thiết kế nên tách `construct`, `initialize`, `register` với điều kiện sẵn sàng rõ ràng.

### 6.3. Constructor bị lỗi

Nếu constructor hoặc init hook ném ngoại lệ:

- Target/registry không nên công bố instance chưa hoàn tất.
- Những tài nguyên đã cấp phát trước lúc lỗi phải có cleanup phù hợp, ví dụ try/catch hoặc resource ownership cục bộ.
- Không tự đánh dấu aspect “đã init” nếu bước init chưa thành công.
- Cần rõ retry khởi tạo có được phép không: đối với stateful resource, retry có thể cần cleanup từ lần thất bại trước.

## 7. Phân biệt vòng đời aspect với vòng đời target, proxy và join point

Bốn đối tượng/hiện tượng có thể không sống cùng khoảng thời gian:

~~~text
Application lifespan:   |---------------------------------------|
Global aspect:          |---------------------------close------|
Target #1:                  |-------------|
Proxy for target #1:        |---------------close|
Invocation #1:                 |-|
Invocation #2:                       |-|
Target #2:                             |-------------|
~~~

- Target có thể được tạo trước proxy.
- Proxy có thể bị ngừng sử dụng trước khi target bị GC.
- Aspect shared có thể phục vụ nhiều target và sống lâu hơn chúng.
- Aspect per-target có thể được tạo cùng proxy và đóng cùng owner của proxy.
- Per-invocation scope mở/đóng **nhiều lần** khi target còn tồn tại.
- Join point là **điểm thực thi**, không phải một Java object buộc phải có lifecycle riêng.

Trong một engine bytecode weaving, khái niệm “proxy instance” có thể hoàn toàn không tồn tại ở đường gọi. Đừng thiết kế disposal chỉ dựa trên việc “proxy đã chết” nếu advice được cài vào class và dùng state registry độc lập.

## 8. Ví dụ Java 17 chạy độc lập: ba phạm vi, hai target, ba lời gọi

Chương trình dùng **JDK interface proxy**, **không** dùng bytecode weaving. Nó mô phỏng ba phạm vi nhằm kiểm chứng thời điểm tạo và dọn dẹp:

1. `GlobalTrace` được tạo một lần, được cả hai target sử dụng, và đóng ở cuối vùng ứng dụng.
2. `TargetAspect` được tạo riêng khi một `ManagedJob` được thiết lập, gắn với một target.
3. `InvocationScope` được tạo **mỗi lần lời gọi đi qua proxy**, đóng ngay sau lời gọi bằng `try-with-resources`, kể cả khi target ném exception.

Code còn minh họa `AtomicBoolean` để `close()` của `ManagedJob` là idempotent theo phạm vi demo; `Method.invoke` bóc `InvocationTargetException` để giữ nguyên ngoại lệ nghiệp vụ. Ví dụ chạy **tuần tự** và đóng owner sau khi tất cả invocation kết thúc. Trong ứng dụng đồng thời, chỉ cờ `closed` **không** đủ để xử lý graceful shutdown; phải chờ các lời gọi đang chạy kết thúc trước khi đóng resource chúng dùng.

Tạo file `AspectLifecycleDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.atomic.AtomicBoolean;

public final class AspectLifecycleDemo {
    interface Job { String run(int units); }

    static final class Core implements Job {
        public String run(int units) {
            System.out.println("BUSINESS run " + units);
            if (units <= 0) throw new IllegalArgumentException("units must be positive");
            return "ok:" + units;
        }
    }

    static final class GlobalTrace implements AutoCloseable {
        GlobalTrace() { System.out.println("GLOBAL create+init"); }
        void before() { System.out.println("GLOBAL before"); }
        public void close() { System.out.println("GLOBAL close"); }
    }

    static final class TargetAspect implements AutoCloseable {
        final String name;
        TargetAspect(String name) {
            this.name = name;
            System.out.println("TARGET create+init " + name);
        }
        void before() { System.out.println("TARGET before " + name); }
        void returning() { System.out.println("TARGET returning " + name); }
        void throwing(Throwable t) {
            System.out.println("TARGET throwing " + name + " " + t.getClass().getSimpleName());
        }
        public void close() { System.out.println("TARGET close " + name); }
    }

    static final class InvocationScope implements AutoCloseable {
        final String name;
        InvocationScope(String name) {
            this.name = name;
            System.out.println("CALL open " + name);
        }
        public void close() { System.out.println("CALL release " + name); }
    }

    static final class ManagedJob implements AutoCloseable {
        final TargetAspect aspect;
        final Job proxy;
        final AtomicBoolean closed = new AtomicBoolean();
        ManagedJob(String name, Job target, GlobalTrace global) {
            aspect = new TargetAspect(name);
            proxy = (Job) Proxy.newProxyInstance(
                    Job.class.getClassLoader(),
                    new Class<?>[]{Job.class},
                    (p, method, args) -> {
                        if (closed.get()) throw new IllegalStateException("proxy closed");
                        try (InvocationScope scope = new InvocationScope(name)) {
                            global.before();
                            aspect.before();
                            try {
                                Object result = invoke(target, method, args);
                                aspect.returning();
                                return result;
                            } catch (Throwable error) {
                                aspect.throwing(error);
                                throw error;
                            }
                        }
                    });
        }
        Job api() { return proxy; }
        public void close() {
            if (closed.compareAndSet(false, true)) aspect.close();
        }
    }

    static Object invoke(Job target, Method method, Object[] args) throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException error) {
            throw error.getCause();
        }
    }

    public static void main(String[] args) {
        try (GlobalTrace global = new GlobalTrace()) {
            try (ManagedJob first = new ManagedJob("A", new Core(), global);
                 ManagedJob second = new ManagedJob("B", new Core(), global)) {
                System.out.println("CALLER " + first.api().run(2));
                try {
                    second.api().run(0);
                } catch (IllegalArgumentException error) {
                    System.out.println("CALLER " + error.getMessage());
                }
                System.out.println("CALLER " + first.api().run(1));
            }
        }
    }
}
~~~

Lệnh với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 AspectLifecycleDemo.java
java AspectLifecycleDemo
~~~

Đầu ra đã xác minh bằng biên dịch và chạy chương trình thật:

~~~text
GLOBAL create+init
TARGET create+init A
TARGET create+init B
CALL open A
GLOBAL before
TARGET before A
BUSINESS run 2
TARGET returning A
CALL release A
CALLER ok:2
CALL open B
GLOBAL before
TARGET before B
BUSINESS run 0
TARGET throwing B IllegalArgumentException
CALL release B
CALLER units must be positive
CALL open A
GLOBAL before
TARGET before A
BUSINESS run 1
TARGET returning A
CALL release A
CALLER ok:1
TARGET close B
TARGET close A
GLOBAL close
~~~

### 8.1. Vì sao có một `GLOBAL` nhưng hai `TARGET`?

`main()` tạo một `GlobalTrace` trong try-with-resources ngoài. Hai `ManagedJob` dùng cùng đối tượng ấy, nên chỉ xuất hiện **một** dòng `GLOBAL create+init`. Constructor của mỗi `ManagedJob` lại tạo một `TargetAspect` riêng, nên có `TARGET create+init A` và `TARGET create+init B`.

Ba lần gọi `run()` không tạo thêm `GlobalTrace` hay `TargetAspect`. **Số lần advice thực thi không nhất thiết bằng số instance aspect.**

### 8.2. Vì sao có ba lần `CALL open` và ba lần `CALL release`?

Mỗi lần lời gọi qua proxy tạo một `InvocationScope` mới. Hai lần của A và một lần của B tương ứng ba scopes. `try-with-resources` đóng scope khi rời khối, kể cả ở lần `run(0)` ném `IllegalArgumentException`.

Đây là mô phỏng **per-invocation context** thông qua Java object lifetime, không khẳng định mọi AOP engine tạo một Java object cho mỗi join point.

### 8.3. Vì sao `TARGET close B` xuất hiện trước `TARGET close A`?

Trong Java try-with-resources, các resources cùng danh sách được đóng **theo thứ tự ngược thứ tự khai báo**. `second` được tạo sau `first` nhưng đóng trước `first`. Sau khi phạm vi trong kết thúc, `GlobalTrace` ở phạm vi ngoài mới được đóng.

Vì sao quan trọng? Nếu `TargetAspect` dựa vào `GlobalTrace` như shared sink, target aspects cần được đóng trong khi sink còn sống. Cấu trúc owner scopes của ví dụ sắp xếp việc đóng theo cách ấy.

### 8.4. Ngoại lệ nghiệp vụ có bị thay đổi không?

Không. `Core.run(0)` ném `IllegalArgumentException`; `invoke()` bóc `InvocationTargetException` do Reflection sinh ra; handler ghi `TARGET throwing`, `InvocationScope.close()` chạy, rồi caller bắt đúng loại exception gốc. **Không cần catch và nuốt ngoại lệ nghiệp vụ chỉ để cleanup.**

Lưu ý: nếu `close()` của resource cũng ném exception, Java try-with-resources có cơ chế **suppressed exceptions** khi đã có lỗi chính. Một implementation cleanup có side effect phức tạp phải kiểm thử cả lỗi disposal, tránh giả định close luôn vô hại.

### 8.5. Giới hạn minh họa của demo

- Instance lifetime được code chủ động quản lý; không chứng minh một weaver cụ thể hỗ trợ `per-target` hay `per-control-flow` bằng ngôn ngữ pointcut.
- `GlobalTrace` không thực sự là singleton JVM; chỉ là một object được tạo một lần trong ví dụ. Chạy `main()` hai lần sẽ tạo hai object.
- Proxy chỉ thấy lời gọi đi qua `api()`; target gọi trực tiếp sẽ không có scope/advice do proxy này tạo.
- `AtomicBoolean` giúp `close` idempotent trong code demo nhưng **không ngăn một invocation đã qua cổng kiểm tra đồng thời với việc close**.
- `TargetAspect.throwing()` chỉ in loại lỗi; code không biến đổi result hoặc exception của target.
- Việc in log sync là để học; production nên xem xét chi phí I/O, dữ liệu nhạy cảm và thread safety.
- Nếu một phương thức trả `CompletableFuture`, `InvocationScope` trong handler này sẽ đóng khi Future được **trả về**, không chờ tác vụ bên trong hoàn tất.

## 9. Khởi tạo với lazy instance: chi phí và tính an toàn

Nếu một aspect instance được tạo **lần đầu khi join point khớp**, cần xem:

1. Cùng một lần khớp có thể xảy ra trên nhiều thread cùng lúc không?
2. Factory có đảm bảo single initialization cho phạm vi intended không?
3. Nếu init thất bại, có retry lần sau hay ghi nhớ trạng thái failed?
4. Nếu target biến mất trước lần gọi đầu, liệu aspect có cần được tạo không?
5. Nếu policy bị tắt rồi bật lại, object cũ được tái sử dụng hay tạo mới?
6. Nếu aspect có tài nguyên đóng, ai nắm ownership khi factory tạo lazy?

Mô hình double-checked locking chỉ an toàn khi thực hiện đúng quy tắc Java Memory Model, ví dụ field `volatile` cùng quy trình initialization phù hợp. Nếu không có nhu cầu học/viết primitive concurrency, nên ưu tiên một lazy holder/factory đã có bảo đảm rõ ràng.

Tránh để advice tự kiểm tra `if (client == null) client = new Client()` trên một field dùng chung mà không đồng bộ. Hai request có thể tạo hai clients, leak một client, hoặc công bố instance chưa khởi tạo đầy đủ.

## 10. Cleanup: GC không thay thế `close()`

Java **garbage collection** quyết định thu gom bộ nhớ của các object không còn reachable. GC không hứa thời điểm chính xác object được thu hồi. Tài nguyên như socket, file descriptor, thread, executor, batch buffer hoặc subscription nên có **đường đóng tường minh** khi cần.

Các khái niệm cần phân biệt:

- **Object unreachable:** chương trình không còn đường tham chiếu mạnh có thể truy cập object.
- **Resource disposed:** socket/file/client/subscription đã được đóng theo hợp đồng.
- **Classloader unloadable:** toàn bộ classloader và các class liên quan không còn bị giữ sống.
- **Advice deactivated:** không còn lời gọi mới kích hoạt advice theo registry/pointcut.
- **In-flight invocation completed:** các lời gọi đã bắt đầu dùng tài nguyên đã thực sự kết thúc.

Một aspect có thể bị deactivated nhưng còn in-flight calls. Nếu đóng resource ngay tại thời điểm deactivation, lời gọi đang chạy có thể mất sink hoặc context. Vì vậy, với shutdown thực tế thường cần:

~~~text
STOP_ACCEPTING_NEW_CALLS
        |
WAIT_FOR_IN_FLIGHT_TO_FINISH (with bounded deadline)
        |
FLUSH / CLOSE PER-TARGET RESOURCES
        |
CLOSE SHARED RESOURCES
        |
UNREGISTER / RELEASE REFERENCES
~~~

Đây là **quy trình ý niệm**; triển khai chính xác phụ thuộc resource và cơ chế registration. Không được mặc định `AtomicBoolean closed` tự triển khai toàn bộ trình tự graceful shutdown.

## 11. Sở hữu tài nguyên: ai tạo thì ai đóng?

Một nguyên tắc hữu ích là gắn trách nhiệm cleanup với **owner** đã thiết lập vòng đời:

| Resource | Scope phù hợp có thể cân nhắc | Owner/disposal điển hình |
| --- | --- | --- |
| Metrics client chia sẻ | Application/global | Application registry hoặc service manager |
| Tham số cấu hình riêng target | Per-target | Target proxy manager hoặc factory |
| Stopwatch start time | Per-invocation | Local scope, kết thúc trong `finally` |
| Trace span | Per-invocation / async task | Span owner, kết thúc đúng sự kiện completion |
| Subscription/listener | Per-target hoặc application | Thành phần đã đăng ký subscription |
| Executor/thread pool | Thường scope dài được chia sẻ có kiểm soát | Executor owner gọi shutdown |
| Buffer batch logs | Theo sink instance | Sink owner flush rồi close |
| Security context | Theo request/control-flow | Request context owner, có cleanup chính xác |

Không để per-invocation advice tự đóng một client dùng chung: request sau sẽ gặp lỗi. Cũng không để per-target aspect giữ **một request context mãi trong field**, vì target có thể phục vụ nhiều requests khác nhau.

### 11.1. Có thể có nhiều owners cùng gọi close?

Nên thiết kế **một owner logic rõ ràng**. Nếu hoàn cảnh có khả năng `close()` được gọi nhiều lần, `close` nên có hợp đồng idempotent hoặc xử lý repeat call rõ; song idempotent `close` không đồng nghĩa với việc an toàn khi bị gọi đồng thời cùng `use()`.

### 11.2. Khi cleanup cũng thất bại

Nếu đang rời advice vì exception nghiệp vụ mà `close()` ném thêm lỗi, cần giữ ngữ nghĩa lỗi gốc. Try-with-resources hỗ trợ suppressed exception trong những trường hợp thích hợp. Nếu tự viết `finally`, phải xem lỗi cleanup có thể che lỗi ban đầu hay không.

Đối với observability sink theo chính sách **fail-open**, có thể ghi lỗi cleanup ra kênh riêng và không làm hỏng nghiệp vụ; nếu policy có tính bắt buộc, cần định nghĩa failure semantics rõ. Không catch mọi `Throwable` rồi âm thầm bỏ qua.

## 12. Concurrency: aspect instance dùng chung không đồng nghĩa thread-safe

Nếu một aspect phục vụ nhiều target hoặc nhiều invocations, **các field mutable** có thể bị truy cập đồng thời. Một số quy tắc:

- **State theo invocation:** lưu trong local variables của advice, hoặc object context không chia sẻ tùy tiện.
- **State theo target:** tạo riêng per-target nhưng vẫn cần bảo vệ nếu cùng target bị gọi nhiều thread.
- **Shared counters:** dùng atomic/concurrent data structures phù hợp.
- **Immutable configuration:** ưu tiên cấu hình bất biến được công bố an toàn.
- **External clients:** chỉ chia sẻ nếu library contract cho phép concurrent calls.
- **Shutdown:** không chỉ set boolean và đóng sink; phải phân định rõ các invocation đang chạy.
- **Recursion:** một advice instance có thể được tái nhập (reentrant) trên cùng thread, nên field `currentInvocation` dùng chung cũng có nguy cơ hỏng dù không có multithreading.
- **ThreadLocal:** cần cleanup trong `finally` khi dùng thread pool; không tự truyền qua task async/thread khác.

### Mốc bắt đầu đo thời gian

Sai lầm:

~~~java
class SharedTimingState {
    long started;
    void enter() { started = System.nanoTime(); }
    long exit() { return System.nanoTime() - started; }
}
~~~

Đây là ví dụ logic có thể gặp lỗi; không có chương trình test độc lập. Nếu thread A gọi `enter`, thread B ghi `started` sau đó thread A gọi `exit`, elapsed của A dùng mốc của B.

Cách đúng về scope là `long started` cục bộ trong một lần `around` hoặc một đối tượng per-invocation đúng hợp đồng. Không nhất thiết tạo mới cả **aspect instance** để có state per-invocation; aspect shared có thể dùng local variables.

## 13. Aspect theo control-flow và vấn đề `ThreadLocal`

Một control-flow scope có thể gắn với hoạt động đang diễn ra, ví dụ “trong thời gian xử lý giao dịch X”. Nhưng Java có:

- Nested method calls.
- Recursion.
- Thread pools.
- `CompletableFuture` và callback.
- Virtual threads hoặc execution contexts khác, tùy JDK.
- Cancellation, timeout, exceptional completion.

Một `ThreadLocal` chỉ gắn state với thread cụ thể; nó không tự thể hiện “ngữ cảnh logic X” xuyên mọi scheduler và async boundary. Nếu dùng `ThreadLocal` để mô phỏng control-flow, cần đảm bảo:

~~~java
Context previous = context.get();
try {
    context.set(current);
    runWork();
} finally {
    if (previous == null) context.remove();
    else context.set(previous);
}
~~~

Đây là **mã Java minh họa không độc lập** vì `Context`, `context` và `runWork()` chưa được định nghĩa. Kỹ thuật “lưu previous/khôi phục trong finally” quan trọng khi có nested context. Nhưng nó **chưa giải quyết** việc truyền context qua thread khác; muốn làm điều đó phải thiết kế propagation riêng theo executor/task semantics.

Đặc biệt, không được để một control-flow aspect giả định luôn kết thúc khi một method trả Future. **Method return** có thể xảy ra trước **task completion**.

## 14. Bất đồng bộ: thời điểm giải phóng nào mới đúng?

Giả sử:

~~~java
CompletableFuture<String> loadAsync() {
    return CompletableFuture.supplyAsync(() -> compute());
}
~~~

Đoạn này là **minh họa chưa độc lập** vì `compute()` chưa được định nghĩa.

Nếu around advice mở một invocation scope trước `proceed` và đóng trong `finally` ngay khi `proceed` trả `CompletableFuture`, nó đã dọn dẹp scope của **method return**, không phải scope của **tác vụ đến khi hoàn tất**.

Muốn quản lý lifecycle dài đến completion:

1. Phải định nghĩa completion event rõ: successful, exceptional hoặc cancellation.
2. Gắn callback/handle thích hợp vào Future hoặc abstraction bất đồng bộ tương ứng.
3. Không đóng tài nguyên mà callback còn cần trước completion.
4. Đảm bảo cleanup được thực hiện đúng một lần nếu completion và cancellation race.
5. Xác định ai sở hữu tài nguyên nếu caller hủy/bỏ Future.
6. Tránh block `join()` trong after-returning chỉ để đóng resource; làm vậy có thể phá API async.

Ví dụ minh họa:

~~~java
long start = System.nanoTime();
CompletableFuture<String> future = startAsync();
future.whenComplete((result, error) -> {
    long nanos = System.nanoTime() - start;
    observeCompletion(result, error, nanos);
});
~~~

Đây không phải một chương trình độc lập (`startAsync` và `observeCompletion` cần được triển khai). `whenComplete` trả một stage mới; lỗi do callback có thể ảnh hưởng stage phụ thuộc. Nếu giữ tài nguyên cho callback, cần đảm bảo completion callback đó không bị mất theo policy và luôn có nơi quản lý lỗi của chính callback.

**Không gộp** hai nghĩa “vòng đời invocation của method” và “vòng đời operation bất đồng bộ”; lựa chọn phụ thuộc metric/audit mà aspect chịu trách nhiệm.

## 15. Proxy, weaving và vòng đời đối tượng không đồng nhất

### 15.1. Với proxy

Factory thường sở hữu hoặc cấp proxy; state handler có thể gắn với proxy, target hoặc một registry riêng. Phạm vi quan sát bị giới hạn bởi **đường caller dùng proxy**.

Nếu caller giữ target raw và gọi trực tiếp, handler proxy không có invocation nào để mở/đóng context. Một target có thể tiếp tục tồn tại sau khi proxy bị đóng. Phải quy định rõ `close()` tác động tới proxy/handler, target thật hay cả hai, tránh đóng một target shared ngoài ý định.

### 15.2. Với code/bytecode weaving

Advice có thể được gắn vào method execution hoặc join point khác khi class được dệt. Một method woven có thể chạy dù không có wrapper proxy. Trạng thái advice có thể nằm trong field được sinh, registry, helper class hoặc cấu trúc engine quản lý.

Vì thế không nên khẳng định “mỗi target được weaving sẽ tự có constructor aspect riêng”. Một weaver có thể tạo instance per-object, dùng singleton hoặc không lưu state, tùy mô hình instantiation hỗ trợ.

### 15.3. Với load-time weaving

Class transformation thường xảy ra trước khi JVM định nghĩa class. Nhưng aspect instance có thể được tạo muộn hơn. Nếu class đã nạp trước khi transformer được thiết lập, nó có thể không được instrument bởi LTW thông thường; hỗ trợ retransformation/redefinition nếu có là cơ chế riêng có giới hạn.

### 15.4. Với nhiều classloaders

Trong JVM, class identity gắn với **tên class và defining classloader**. Nếu một holder static được khai báo trong class do hai classloaders khác nhau định nghĩa, có thể tồn tại những copies riêng của class và static state. Do đó từ “một singleton cho cả JVM” thường quá mạnh: hãy nói **một instance trong registry/classloader scope cụ thể** theo khả năng thực tế.

Nếu một registry toàn cục nắm tham chiếu mạnh tới classloader hoặc class từ plugin đã gỡ, việc unload có thể bị cản. Cleanup đúng cần unregister aspect/transformer/callback và loại những reference không còn cần.

## 16. Tính tuần tự và thứ tự teardown

Một hệ thống có nhiều tầng:

~~~text
Application
  SharedMetrics
    TargetAspect #1
      InvocationScope #A
    TargetAspect #2
      InvocationScope #B
~~~

Nếu `InvocationScope` còn ghi metrics lúc đóng, shared sink phải **còn sống** cho tới khi mọi scope liên quan hoàn tất. Thứ tự đóng hợp lý thường là:

1. Dừng admission/lời gọi mới.
2. Đợi các calls đang chạy hoàn tất hoặc tới deadline đã xác định.
3. Đóng các per-invocation/per-flow contexts còn sở hữu.
4. Đóng các per-target registrations/aspects.
5. Flush và đóng shared services.
6. Bỏ đăng ký và giải phóng tham chiếu còn lại.

Đây là quy trình **mang tính thiết kế**; có resource cần đóng theo thứ tự khác. Điều quan trọng là tạo **dependency graph**: nếu A cần B trong `close()`, đừng đóng B trước A.

Trong ví dụ `AspectLifecycleDemo`, resource list của try-with-resources tự đóng theo thứ tự ngược: target B rồi target A, cuối cùng global. Điều đó chứng minh trật tự cleanup **do owner scopes quyết định**, không phải mặc nhiên JVM luôn đóng aspects theo cùng một thứ tự.

## 17. Rủi ro memory leak và quản lý registry

Một registry instance per-target có thể trở thành nơi giữ sống target vô hạn.

Những mối nguy:

- `Map<Target, Aspect>` là map thường, giữ mạnh cả key và value.
- `WeakHashMap<Target, Aspect>` nhưng aspect value giữ lại chính target key; weak key không còn đủ giúp entry biến mất nếu value reachable qua map lại tham chiếu ngược key.
- Handler đăng ký với event bus toàn cục nhưng không unregister.
- `ThreadLocal` giữ context trên thread pool lâu dài.
- Static cache có key classloader hoặc `Class<?>` làm plugin classloader không unload.
- Future callbacks giữ tham chiếu tới target, aspect và payload tới khi hoàn tất; nếu Future không bao giờ complete, chúng có thể ở lại.
- Một aspect tạo executor/thread mới và không shutdown.
- Một proxy bị quên dispose dù giữ subscription/resource.

**Giải pháp tốt nhất bắt đầu bằng ownership và scope**, không chỉ thêm weak reference. Xác định điều gì tạo instance, ai biết khi nào target không dùng nữa, và khi nào một reference cần được loại khỏi registry.

## 18. Khi nào cần có `close()` hay disposal hook?

Không phải aspect nào cũng cần cleanup riêng.

**Không có tài nguyên:** advice chỉ đọc tham số và ghi counter thread-safe vào một sink đã được application sở hữu thì per-invocation scope có thể kết thúc khi method return; không cần tạo `AutoCloseable` mỗi lần.

**Có tài nguyên riêng:** nếu aspect sở hữu file, socket, listener, subscription hoặc buffer riêng, cần quy tắc dọn dẹp rõ. `AutoCloseable` là một lựa chọn Java thuận tiện nhưng không phải API bắt buộc của mọi AOP engine.

**Có tài nguyên chia sẻ:** aspect chỉ **mượn** một metrics client thì không tự đóng client khi một target hoàn tất. Application owner đóng nó vào shutdown.

**Có asynchronous work:** nếu advice mở span cho task kéo dài, phải đóng ở completion/cancellation theo contract thay vì return của method tạo task.

Với retry/timeout/cancellation, hãy xác định event nào làm scope kết thúc để tránh close hai lần hoặc leak.

## 19. Kiểm thử vòng đời theo scope

Nên có **ba bộ đếm khác nhau**:

- `createdCount`: số instance/state holders tạo thành công.
- `adviceEntryCount`: số lần advice được gọi.
- `closedCount`: số instance/resource đóng đúng hợp đồng.

Ví dụ, nếu có một global, hai targets và ba invocations:

| Scope | Tạo dự kiến | Kích hoạt dự kiến | Đóng dự kiến |
| --- | ---: | ---: | ---: |
| GlobalTrace | 1 | 3 lần `before` | 1 |
| TargetAspect A | 1 | 2 lần `before` | 1 |
| TargetAspect B | 1 | 1 lần `before` | 1 |
| InvocationScope | 3 | 3 | 3 |

Cần nhớ “một advice đã in log” không phải bằng chứng nó chỉ có một instance. Muốn kiểm tra scope, đưa định danh **instance** và **invocation** khác nhau vào test, tránh dùng object `hashCode` làm bằng chứng tuyệt đối về danh tính.

### 19.1. Ma trận test quan trọng

| Ca thử | Kỳ vọng |
| --- | --- |
| Tạo factory nhưng chưa gọi method | Đúng policy eager/lazy, không phát sinh advice invocation |
| Gọi một target hai lần | Per-target instance tái sử dụng nếu scope yêu cầu |
| Tạo hai targets | Hai per-target states độc lập, shared dependency không bị tạo lại |
| Method thành công | Open/close invocation cân bằng, return được bảo toàn |
| Method ném exception | Close vẫn chạy, ngoại lệ gốc không mất |
| Advice có lỗi khi init | Không public instance chưa sẵn sàng; cleanup tài nguyên đã mở |
| Close được gọi hai lần | Theo hợp đồng idempotence, không đóng tài nguyên hai lần |
| Close đồng thời với invocation | Quy tắc ngừng tiếp nhận và chờ in-flight rõ ràng |
| Lời gọi đệ quy | Nested contexts không ghi đè state |
| Nhiều thread cùng target | Shared/per-target state được đồng bộ đúng |
| Truy cập bằng raw target bỏ qua proxy | Không mong đợi proxy advice thực thi |
| Method trả Future chưa xong | Scope method return và scope task completion được phân biệt |
| Classloader bị gỡ | Registry và callback không giữ references cũ |
| Bật/tắt aspect runtime | Không leak registration/state sau mỗi lần thay cấu hình |
| Shutdown | Per-target đóng trước shared sink nếu cần |
| Two advice có chung tài nguyên | Không đóng shared resource bởi advice không sở hữu |

### 19.2. Test với lỗi disposal

Cần thử trường hợp close resource thất bại, đặc biệt khi target đã ném exception. Với try-with-resources của Java, có thể kiểm tra lỗi chính và `getSuppressed()` để hiểu ngoại lệ dọn dẹp. Nếu tự viết `finally`, cần đảm bảo policy không vô tình che nguyên nhân nghiệp vụ.

### 19.3. Test lazy initialization dưới concurrency

Nhiều request đồng thời gọi lần đầu có thể bộc lộ race không xảy ra khi test đơn luồng. Sử dụng concurrency test với barrier hoặc latch phù hợp để xác nhận chỉ số lượng instance mong muốn được tạo và không ai nhận được object khởi tạo dở. Không dùng `Thread.sleep()` ngắn rồi khẳng định đó là test race đầy đủ.

## 20. Thực hành thiết kế an toàn

Một quy trình áp dụng được:

1. **Định nghĩa policy scope:** application, per-target, per-invocation hay per-flow; đừng chọn theo tên annotation.
2. **Xác định chủ sở hữu:** ai tạo aspect/state holder và ai gọi dispose?
3. **Tách installation khỏi instance creation:** weaver/proxy được thiết lập lúc nào và state được tạo lúc nào?
4. **Liệt kê phụ thuộc và tài nguyên:** thành phần nào shared, thành phần nào owned?
5. **Chọn init eager hay lazy:** cân nhắc startup, lỗi init và số instance.
6. **Giữ data theo invocation ở scope ngắn:** local vars/context, không field global mutable.
7. **Định nghĩa concurrency và reentrancy:** nếu per-target được chia sẻ giữa threads, đồng bộ ra sao?
8. **Chọn shutdown protocol:** chặn invocation mới, đợi in-flight, đóng từ scope nhỏ tới owner lớn.
9. **Phân biệt method return với async completion:** scope cần đóng khi nào?
10. **Kiểm soát classloader/registry:** unregister callbacks, dọn caches và tránh reference cycles qua maps.
11. **Bảo toàn behavior nghiệp vụ:** advice chỉ quan sát không đổi return, ngoại lệ hay số lần target được gọi.
12. **Integration test chính đường can thiệp:** một unit test gọi method advice không chứng minh proxy/weaving gắn đúng.
13. **Ghi metrics cho lifecycle:** số instances được tạo/đóng, active scopes, queues, errors và resource usage.
14. **Kiểm thử khi bật/tắt/redeploy:** không để handler cũ sống song song với handler mới ngoài ý định.

Với hệ thống lớn, nên có một **lifecycle owner registry** rõ ràng thay vì để mỗi advice tự mở và đóng tài nguyên một cách phân tán.

## 21. Các lỗi hiểu sai thường gặp

1. **“Weaving xảy ra tại build nên aspect instance cũng được tạo ở build.”** Không đúng; đó là hai thời điểm khác nhau.
2. **“Có một aspect definition thì chỉ có một instance.”** Phụ thuộc scope và engine.
3. **“Một aspect singleton chỉ chạy một lần.”** Instance shared có thể được gọi hàng nghìn lần.
4. **“Per-target có nghĩa per-invocation.”** Target thường có nhiều calls.
5. **“Constructor chạy xong thì mọi dependency đã sẵn sàng.”** Có thể còn init/registration riêng.
6. **“GC sẽ tự gọi close ngay khi không còn dùng.”** GC không bảo đảm cleanup tài nguyên đúng lúc.
7. **“Một `WeakHashMap` luôn tránh leak per-target state.”** Không đúng khi value giữ key hoặc có reference khác.
8. **“Một flag closed là đủ cho graceful shutdown.”** Không; còn in-flight invocations và race với cleanup.
9. **“ThreadLocal tự theo context qua Future và executor.”** Không tự động trong mọi đường async.
10. **“Method trả Future là task đã hoàn tất.”** Không; scope theo completion có thể dài hơn.
11. **“Mọi exception được ghi trong advice là lỗi từ target.”** Có thể là lỗi init, sink hoặc cleanup.
12. **“Một aspect shared có thể lưu `startedAt` dùng chung.”** Không an toàn với concurrency/reentrancy.
13. **“Dùng proxy là thay đổi target bytecode và lifecycle target.”** Không bắt buộc; wrapper có owner riêng.
14. **“LTW khởi tạo mọi aspect ngay khi classload.”** Không có quy tắc chung.
15. **“Một instance đóng thì shared metrics client nên đóng theo.”** Chỉ owner của shared client được quyết định.
16. **“Chạy unit test advice đủ chứng minh lifecycle thật.”** Cần integration test với đường proxy/weaving và container/application owner thực tế.
17. **“Classloader không liên quan singleton.”** Static state của classes từ các defining loaders khác nhau có thể tách biệt.
18. **“Đóng aspect không cần xét lỗi cleanup.”** Cleanup có thể ném exception và che lỗi chính hoặc gây mất dữ liệu.
19. **“Phạm vi per-control-flow chỉ là per-thread.”** Context logic và thread vật lý không phải luôn cùng một phạm vi.
20. **“Số events bằng số aspect instances.”** Events, advice entries, target invocations và created instances là các số đếm khác nhau.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Aspect được dệt tại compile-time, constructor instance chạy khi nào?  
**Trả lời:** Tùy cơ chế instantiation runtime của công cụ; không mặc định chạy trong lúc build.

**Câu 2.** Một instance global, hai target, ba lời gọi: số lần advice chạy có nhất thiết bằng một không?  
**Trả lời:** Không. Instance được tạo một lần nhưng advice có thể chạy ba lần hoặc theo số join points đã chọn.

**Câu 3.** Per-target aspect có luôn an toàn thread không?  
**Trả lời:** Không. Hai thread có thể đồng thời gọi cùng target và cùng aspect state.

**Câu 4.** Vì sao không để stopwatch start time trong field của một shared aspect?  
**Trả lời:** Calls đồng thời hoặc reentrant có thể ghi đè mốc, tính elapsed sai. Dùng local/per-invocation context.

**Câu 5.** Một aspect sở hữu socket. GC có phải là cơ chế dispose đủ tin cậy không?  
**Trả lời:** Không. Nên có lifecycle owner và đóng tường minh theo hợp đồng.

**Câu 6.** Tại sao `Target close B` trước `Target close A` trong ví dụ?  
**Trả lời:** Java try-with-resources đóng resources theo thứ tự ngược khai báo, khi ra khỏi scope.

**Câu 7.** Ngoại lệ target có làm `InvocationScope` không được đóng không?  
**Trả lời:** Không trong ví dụ: try-with-resources đảm bảo close khi rời khối theo cơ chế Java bình thường.

**Câu 8.** Có thể dùng một `AtomicBoolean closed` rồi ngay lập tức đóng sink trong ứng dụng nhiều thread không?  
**Trả lời:** Chưa đủ. Invocation đã bắt đầu có thể còn đang dùng sink; cần chính sách chờ in-flight và đồng bộ.

**Câu 9.** Với `CompletableFuture`, nên đóng context khi method return hay khi task complete?  
**Trả lời:** Phụ thuộc ý nghĩa scope. Nếu đo method return thì đóng khi return; nếu đo toàn task thì quản lý tới completion/cancellation.

**Câu 10.** `WeakHashMap<Target,Aspect>` có tự tránh leak nếu `Aspect` giữ mạnh `Target` không?  
**Trả lời:** Không chắc; value có thể giữ key reachable qua map. Cần xem toàn bộ đường tham chiếu.

**Câu 11.** Tại sao một class static holder có thể không phải singleton chung cả JVM?  
**Trả lời:** Class được định nghĩa riêng bởi những classloaders khác nhau có thể có static state riêng.

**Câu 12.** Làm sao chứng minh lifecycle đúng trong hệ AOP thật?  
**Trả lời:** Đếm creation/advice entry/disposal riêng, chạy integration tests qua đúng proxy/weaving, bao gồm success, throw, lazy init, concurrency, shutdown, async và bypass.

## 23. Tổng kết

**Vòng đời aspect không chỉ là lúc advice chạy.** Cần phân biệt rõ **thời điểm cài đặt pointcut/weaving**, **lúc tạo instance**, **lúc khởi tạo tài nguyên**, **số lần lời gọi kích hoạt advice**, và **lúc giải phóng scope/tài nguyên**. Các scope ứng dụng, per-target, per-invocation, per-control-flow hay stateless có điểm mạnh và rủi ro khác nhau; không có quy tắc khởi tạo/huỷ chung cho mọi engine AOP.

Thiết kế đúng phải xuất phát từ **ownership**: state per-invocation nằm ở phạm vi ngắn; per-target state được quản lý theo target; shared resources sống tới khi mọi consumer kết thúc. Cleanup cần tường minh và an toàn trước lỗi/đồng thời, không phó mặc cho GC. Với async, phân biệt method return và task completion; với weaving/proxy, kiểm chứng instance lifecycle thực tế và đường join point đã được can thiệp. **Bằng chứng tốt nhất là integration tests đo riêng creation, advice invocation và disposal, đồng thời xác minh result/exception và số lần nghiệp vụ không đổi ngoài hợp đồng**.