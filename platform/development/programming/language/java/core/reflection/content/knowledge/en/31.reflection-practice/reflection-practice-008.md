# Thực hành: Dynamic proxy đo thời gian xử lý và giữ nguyên ngoại lệ mã đích

## 1. Bài toán và tiêu chí hoàn thành

Một dịch vụ Java có interface `Job`. Ta muốn bọc mỗi lời gọi của dịch vụ bằng **JDK dynamic proxy** để đo thời gian thực thi, ghi kết quả thành công/thất bại và **không làm biến dạng ngoại lệ do mã đích ném ra**.

Đây là hai mối quan tâm khác nhau:

- **Đo thời gian:** lấy mốc `System.nanoTime()` trước lúc chuyển tiếp lời gọi, tính chênh lệch trong `finally` để luôn ghi nhận cả đường thành công lẫn thất bại.
- **Giữ nguyên ngoại lệ:** khi gọi mã đích bằng `Method.invoke`, Java Reflection bọc bất kỳ `Throwable` nào do method đích ném trong `InvocationTargetException`. Handler phải **lấy đúng `getCause()` và ném lại chính đối tượng đó**, nếu phù hợp với contract của interface proxy.

Sau bài học, bạn sẽ tạo được proxy, kiểm tra kết quả/identity của `IOException`, `RuntimeException` và `Error`, hiểu lúc nào `UndeclaredThrowableException` xuất hiện và nhận biết các rủi ro khi code ghi log làm thay đổi lỗi của nghiệp vụ.

**Phạm vi:** JDK 17+, `java.lang.reflect.Proxy` chỉ bọc các **interface**. Ví dụ không dùng thư viện bên ngoài; với concrete class không có interface, bạn cần một cách tiếp cận khác như decorator thủ công hoặc công cụ proxy bytecode phù hợp.

## 2. Luồng xử lý của `InvocationHandler`

Khi ứng dụng gọi `proxy.execute("A")`:

~~~text
Caller
  |
  v
Proxy implements Job
  |
  v
InvocationHandler.invoke(proxy, method, args)
  |
  +--> start = System.nanoTime()
  |
  +--> method.invoke(realTarget, args)
  |       |
  |       +--> trả về bình thường ------> return result
  |       |
  |       +--> method đích throw ------> InvocationTargetException
  |                                         |
  |                                         +--> throw ex.getCause()
  |
  +--> finally: elapsed = System.nanoTime() - start
  |              ghi nhận tên method, elapsed, trạng thái
  |
  v
Caller nhận kết quả hoặc ngoại lệ gốc
~~~

`InvocationHandler.invoke(Object proxy, Method method, Object[] args)` khai báo `throws Throwable`. Điều này cho phép handler ném lại cả checked exception, unchecked exception và `Error` mà **không cần ép chúng thành `RuntimeException`**.

Các tham số:

| Tham số | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `proxy` | Instance proxy đang được gọi | **Không** gọi lại cùng method trên `proxy` để delegate; dễ đệ quy vô hạn |
| `method` | Đối tượng `Method` tương ứng lời gọi được proxy chuyển đến | Có thể khai báo trên interface cha hoặc là method của `Object` |
| `args` | Giá trị đối số đã được đóng hộp nếu là primitive | Có thể là `null` khi method không có tham số |
| Kết quả `invoke` | Giá trị gửi về caller qua proxy | Phải tương thích kiểu trả về; method `void` nhận kết quả `null` |

Mẫu cốt lõi:

~~~java
long started = System.nanoTime();
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordTime(method, elapsedNanos);
}
~~~

Đây là **fragment**, giả định `target`, `method`, `args` và hàm `recordTime` đã tồn tại. Phần thực hành dưới đây cung cấp chương trình hoàn chỉnh.

## 3. Vì sao phải bóc `InvocationTargetException`?

`java.lang.reflect.Method.invoke` dùng Reflection gọi phương thức đích. Nếu mã đích có:

~~~java
throw new IOException("disk offline");
~~~

thì lời gọi Java trực tiếp nhận `IOException`; còn `method.invoke(target, args)` sẽ ném **`InvocationTargetException`**, với `getCause()` trỏ tới chính `IOException` gốc.

Nếu handler viết sai:

~~~java
// Sai khi muốn giữ nguyên hợp đồng lỗi của Job
(proxy, method, args) -> method.invoke(target, args)
~~~

`InvocationTargetException` là **checked exception**. Nếu phương thức interface chỉ khai báo `throws IOException`, proxy không được ném một `InvocationTargetException` từ handler như checked exception hợp lệ. Khi đó lời gọi proxy thường trả ra `UndeclaredThrowableException`, và ngoại lệ nghiệp vụ bị che dưới nhiều lớp wrapper.

Đúng là:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException ex) {
    throw ex.getCause();
}
~~~

Điểm quan trọng của `throw ex.getCause()`:

1. Ném lại **đúng đối tượng `Throwable`** do method đích phát sinh; không đổi thông điệp và không tạo instance ngoại lệ mới.
2. Giữ lại cause và suppressed exceptions đã nằm trên đối tượng gốc.
3. Caller có thể tiếp tục bắt `IOException`, `IllegalStateException` hay `AssertionError` theo đúng hợp đồng.
4. Không bóc mọi `getCause()` một cách vô điều kiện. Nếu **mã đích thực sự ném một wrapper** như `CompletionException`, đó là hành vi của mã đích; interceptor không nên tự ý làm mất wrapper ấy.

`Method.invoke` có thể tự phát sinh lỗi do truyền sai đối số, quyền truy cập không đủ hoặc receiver sai. Các lỗi xảy ra **trước khi method đích chạy** không phải `InvocationTargetException` đại diện cho lỗi nghiệp vụ, và cần chẩn đoán riêng.

## 4. Chương trình đầy đủ Java 17+: proxy đo thời gian và giữ nguyên cả ba loại ngoại lệ

Tạo file **`TimedProxyDemo.java`**:

~~~java
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class TimedProxyDemo {
    public interface Job {
        String execute(String input);
        void failChecked() throws IOException;
        void failRuntime();
        void failError();
    }

    public static final class RealJob implements Job {
        final IOException checked = new IOException("disk offline");
        final IllegalStateException unchecked =
                new IllegalStateException("bad state");
        final AssertionError error = new AssertionError("fatal");

        public String execute(String input) {
            return "done:" + input;
        }

        public void failChecked() throws IOException {
            throw checked;
        }

        public void failRuntime() {
            throw unchecked;
        }

        public void failError() {
            throw error;
        }
    }

    record Sample(String method, long nanos, boolean succeeded) {}

    static <T> T timedProxy(Class<T> contract, T target, List<Sample> samples) {
        if (!contract.isInterface() || !contract.isInstance(target)) {
            throw new IllegalArgumentException("Wrong contract or target");
        }

        Object proxy = Proxy.newProxyInstance(
                contract.getClassLoader(),
                new Class<?>[] { contract },
                (self, method, args) -> {
                    // Object methods được xử lý tường minh, không đo ở ví dụ này.
                    if (method.getDeclaringClass() == Object.class) {
                        return switch (method.getName()) {
                            case "toString" ->
                                    "TimedProxy(" + contract.getSimpleName() + ")";
                            case "hashCode" -> System.identityHashCode(self);
                            case "equals" -> self == args[0];
                            default ->
                                    throw new UnsupportedOperationException(
                                            method.toString());
                        };
                    }

                    long start = System.nanoTime();
                    boolean succeeded = false;
                    try {
                        Object result = method.invoke(target, args);
                        succeeded = true;
                        return result;
                    } catch (InvocationTargetException ex) {
                        // Giữ nguyên đúng IOException, RuntimeException
                        // hoặc Error do method đích ném.
                        throw ex.getCause();
                    } finally {
                        long nanos = System.nanoTime() - start;
                        samples.add(new Sample(method.getName(), nanos, succeeded));
                    }
                });

        return contract.cast(proxy);
    }

    public static void main(String[] args) {
        RealJob target = new RealJob();
        List<Sample> samples = new ArrayList<>();
        Job proxy = timedProxy(Job.class, target, samples);

        System.out.println(proxy.execute("A"));

        try {
            proxy.failChecked();
        } catch (IOException ex) {
            System.out.println("checked preserved: "
                    + (ex == target.checked));
        }

        try {
            proxy.failRuntime();
        } catch (IllegalStateException ex) {
            System.out.println("runtime preserved: "
                    + (ex == target.unchecked));
        }

        try {
            proxy.failError();
        } catch (AssertionError ex) {
            System.out.println("error preserved: "
                    + (ex == target.error));
        }

        System.out.println(proxy);
        System.out.println("samples: " + samples.stream()
                .map(s -> s.method() + ":"
                        + (s.succeeded() ? "ok" : "fail"))
                .toList());
        System.out.println("durations recorded: " + samples.stream()
                .allMatch(s -> s.nanos() >= 0));

        for (Sample s : samples) {
            System.out.printf("timing %s: %d ns%n",
                    s.method(), s.nanos());
        }
    }
}
~~~

Lệnh biên dịch/chạy (từ thư mục chứa file):

~~~bash
javac --release 17 TimedProxyDemo.java
java TimedProxyDemo
~~~

**Phần output cố định, đã kiểm chứng với OpenJDK 21 và `javac --release 17`:**

~~~text
done:A
checked preserved: true
runtime preserved: true
error preserved: true
TimedProxy(Job)
samples: [execute:ok, failChecked:fail, failRuntime:fail, failError:fail]
durations recorded: true
~~~

Sau đó chương trình in bốn dòng đo thời gian, ví dụ:

~~~text
timing execute: 2029596 ns
timing failChecked: 1850957 ns
timing failRuntime: 164227 ns
timing failError: 69275 ns
~~~

**Các con số trên chỉ là một lần chạy**; không phải giá trị stdout cố định. Trên máy khác hoặc lần chạy khác, thời gian thay đổi theo JIT, scheduler, GC và tải hệ thống. Tính đúng của bài không phụ thuộc số nanosecond cụ thể.

## 5. Vì sao chương trình thực sự giữ nguyên ngoại lệ?

`RealJob` tạo trước ba đối tượng lỗi và giữ trong các field `checked`, `unchecked` và `error`. Các method tương ứng ném **đúng object đã tạo**, nên câu lệnh:

~~~java
ex == target.checked
~~~

chứng minh **identity** của ngoại lệ được giữ, chứ không chỉ tình cờ có cùng class hoặc thông điệp.

Bốn trường hợp:

| Lời gọi | Hành vi mã đích | Caller quan sát | Ghi thời gian |
| --- | --- | --- | --- |
| `execute("A")` | Trả về `done:A` | Nhận chuỗi kết quả | `succeeded=true` |
| `failChecked()` | Ném `IOException` | Bắt được chính `IOException` gốc | `succeeded=false` |
| `failRuntime()` | Ném `IllegalStateException` | Bắt được chính unchecked exception gốc | `succeeded=false` |
| `failError()` | Ném `AssertionError` | Bắt được chính `Error` gốc | `succeeded=false` |

Từng nhánh đều đi qua `finally`. Điều này bảo đảm ghi bản ghi ngay cả khi nghiệp vụ thất bại, **miễn là bản thân phép ghi metric không phát sinh lỗi phá vỡ luồng**. Khi dùng logger/metric backend thật, cần bảo vệ thao tác ghi khỏi lỗi mới để không che mất lỗi nghiệp vụ.

`succeeded` được đặt thành `true` **chỉ sau khi `Method.invoke` trả về bình thường**. Nó diễn tả trạng thái của **lời gọi method đích**, không chắc chắn mô tả kết quả của mọi adapter phía ngoài: proxy có thể còn cần cast/unbox giá trị trả về theo signature. Vì vậy, đừng dùng biến cờ này để tuyên bố toàn bộ request HTTP/transaction đã commit thành công.

## 6. Đo thời gian đúng cách

### 6.1. Dùng `System.nanoTime()`, không dùng đồng hồ hệ thống

`System.nanoTime()` phù hợp tính **elapsed duration**:

~~~java
long start = System.nanoTime();
try {
    return method.invoke(target, args);
} finally {
    long elapsedNanos = System.nanoTime() - start;
}
~~~

- Giá trị đơn lẻ của `nanoTime()` **không phải** mốc thời gian lịch; không chuyển trực tiếp sang ngày giờ.
- Dùng phép **lấy hiệu** hai lần đọc trong cùng JVM; tuyệt đối không so sánh timestamp `nanoTime` giữa hai JVM.
- Đây là số nanosecond theo đơn vị biểu diễn, **không bảo đảm độ phân giải phần cứng là một nanosecond**.
- Đặt mốc trước `method.invoke` nghĩa là thời gian bao gồm **chi phí gọi thông qua Reflection và dispatch bên trong method**, không thuần CPU time của nghiệp vụ.
- Với lời gọi async trả về `CompletableFuture` hay `Mono`, thời gian này có thể chỉ là thời gian **khởi tạo công việc**; để đo tới completion cần hook vào thời điểm tác vụ thực sự hoàn thành.

Đổi đơn vị để hiển thị (không tự làm tròn sai bằng phép chia kiểu double):

~~~java
long micros = java.util.concurrent.TimeUnit.NANOSECONDS.toMicros(elapsedNanos);
long millis = java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(elapsedNanos);
~~~

Câu lệnh này là fragment cần biến `elapsedNanos`. Dùng clock đo elapsed để quan sát hoạt động; dùng `Instant.now()` hoặc logging timestamp nếu muốn ghi **thời điểm sự kiện**.

### 6.2. `finally` cần thiết nhưng không miễn nhiễm lỗi

Đặt phép ghi log trong `finally` sẽ chạy dù target trả về hoặc ném lỗi. Tuy nhiên, nếu `samples.add(...)`, backend metric hoặc logger **tự ném ngoại lệ**, ngoại lệ mới từ `finally` có thể **ghi đè** kết quả/ngoại lệ của nghiệp vụ.

Để bảo đảm không che lỗi vì lỗi ghi log trong tình huống thông thường, có thể tách một sink *best effort*:

~~~java
// Fragment bên trong finally, giả sử metricSink.record(...) có sẵn.
long elapsed = System.nanoTime() - start;
try {
    metricSink.record(method.getName(), elapsed, succeeded);
} catch (RuntimeException loggingFailure) {
    // Ghi lỗi của chính telemetry sang kênh an toàn khác nếu có.
    // Không ném lỗi logger đè lên exception nghiệp vụ.
}
~~~

Đây chỉ là **mẫu chính sách**: trong sản phẩm phải chủ động quyết định cách phát hiện và giám sát lỗi telemetry; không nên im lặng mãi khi hệ thống ghi log hỏng. Bắt `RuntimeException` ở đây không bảo đảm chống mọi `Error` nghiêm trọng (ví dụ thiếu bộ nhớ), và cũng không phải lời hứa tuyệt đối rằng không có cách nào che lỗi gốc.

Trong demo một thread, `ArrayList` là đủ. Nếu proxy được gọi đồng thời, **không dùng chung `ArrayList` không đồng bộ**; hãy chọn `ConcurrentLinkedQueue<Sample>`, `CopyOnWriteArrayList` (chỉ nếu tần suất ghi phù hợp), hoặc hệ thống metrics thread-safe.

## 7. Quy tắc của checked exception ở ranh giới proxy

`InvocationHandler.invoke` có thể `throw Throwable`, nhưng class proxy được sinh ra phải tuân thủ hợp đồng của **interface method**.

| Handler ném | Method interface khai báo | Caller nhận |
| --- | --- | --- |
| `IOException` | `throws IOException` (hoặc superclass phù hợp) | `IOException` gốc |
| `IOException` | Không khai báo checked exception phù hợp | `UndeclaredThrowableException` bọc `IOException` |
| `IllegalStateException` | Có hoặc không có `throws` | Unchecked exception gốc |
| `AssertionError` | Có hoặc không có `throws` | `Error` gốc |
| `InvocationTargetException` chưa bóc | Chỉ `throws IOException` | Thường `UndeclaredThrowableException` bọc `InvocationTargetException` |

Vì thế **bóc wrapper của Reflection là điều kiện cần, chưa phải điều kiện đủ** để mọi checked exception đi ra như ban đầu. Interface phải cho phép loại exception ấy.

Ví dụ một handler cố tình ném checked exception không được khai báo:

~~~java
interface NoChecked {
    void work();
}

NoChecked proxy = (NoChecked) Proxy.newProxyInstance(
        NoChecked.class.getClassLoader(),
        new Class<?>[] { NoChecked.class },
        (p, m, a) -> { throw new java.io.IOException("I/O"); });

try {
    proxy.work();
} catch (java.lang.reflect.UndeclaredThrowableException ex) {
    System.out.println(ex.getUndeclaredThrowable().getClass().getSimpleName());
}
~~~

Đây là **fragment Java 17+** để đặt trong method thích hợp với `Proxy` được import hoặc fully-qualified. Nó in `IOException`; `getUndeclaredThrowable()` tham chiếu tới checked exception mà handler đã ném.

Nếu một proxy cài đặt **nhiều interface có cùng tên/tham số**, tập checked exception được phép là những loại thỏa mãn `throws` của **tất cả** lời khai báo trùng liên quan, không chỉ interface đứng đầu danh sách. Điều này có thể khiến exception bị `UndeclaredThrowableException` bọc ngay cả khi một interface riêng lẻ khai báo nó.

**Khuyến nghị:** viết proxy theo contract interface rõ ràng; đừng “sửa” trường hợp ngoại lệ không được khai báo bằng ép tất cả lỗi thành `RuntimeException` nếu mục tiêu là giữ nguyên ngữ nghĩa mã đích.

## 8. Xử lý `equals`, `hashCode` và `toString`

JDK dynamic proxy cũng điều hướng ba method public, non-final của `Object` vào `InvocationHandler`. Với chúng, `method.getDeclaringClass() == Object.class`.

Nếu handler dùng:

~~~java
return method.invoke(proxy, args); // Sai: lại gọi chính proxy!
~~~

thì lần gọi mới lại chạy vào cùng handler và có thể dẫn đến đệ quy/`StackOverflowError`.

Demo chọn một chính sách **proxy identity**:

- `equals(other)` trả `self == other`.
- `hashCode()` trả `System.identityHashCode(self)`.
- `toString()` trả `TimedProxy(Job)`.
- Không đo các lời gọi `Object` này; danh sách `Sample` chỉ chứa method nghiệp vụ.

Một decorator khác có thể chọn delegate các lời gọi `Object` sang target, nhưng phải cân nhắc **đẳng thức đối xứng, transitivity** và hash contract. Không mặc định `target.equals(proxy)` sẽ đúng nếu proxy.equals(target)` do handler tùy biến quyết định; nhất quán `equals`/`hashCode` mới là điều quan trọng.

## 9. Không làm mất thông tin lỗi khi log

Một interceptor quan sát lỗi cần tách **nguyên nhân nghiệp vụ** khỏi **lỗi của chính hệ thống đo**.

Những điều nên làm:

1. **Không tạo lại exception** chỉ để log: `throw new IOException(ex.getMessage())` làm mất identity, stack trace gốc và có thể mất cause/suppressed.
2. **Không dùng `throw new RuntimeException(ex)`** nếu interface có hợp đồng checked exception mà caller cần bắt trực tiếp.
3. **Không viết `catch (Exception ex) { return null; }`**: nó vừa nuốt lỗi, vừa gây `NullPointerException` về sau nếu method trả primitive.
4. **Không quên `finally`**: nếu chỉ ghi metric sau `return method.invoke(...)`, nhánh throw sẽ không được đo.
5. **Tránh log dữ liệu nhạy cảm trong `args` hoặc return value**; bài thực hành chỉ ghi tên method và thời lượng.
6. **Không tự gọi lại method nghiệp vụ** để “thử lại timing” trừ khi retry là contract độc lập, được quyết định tường minh. Gọi hai lần có thể nhân đôi side effect.
7. **Không đóng nhãn “thành công” cho tác vụ bất đồng bộ** chỉ vì trả về một future; kết quả có thể thất bại sau đó.

Khi cần correlation trong ứng dụng có nhiều request, thêm một trace/request id vào metric, nhưng đừng dùng `proxy.toString()` trong chính handler để sinh log message.

## 10. Sai lầm đặc trưng khi dùng `Method.invoke`

### 10.1. Gọi trên sai receiver

`method` do proxy chuyển vào thường là method trên một **interface**. `target` phải implement interface tương ứng; nếu truyền instance sai, Reflection có thể ném `IllegalArgumentException`. Hàm `timedProxy` kiểm tra trước bằng:

~~~java
contract.isInterface() && contract.isInstance(target)
~~~

để phát hiện cấu hình sai trước khi bắt đầu tạo proxy. Điều kiện này không thay thế toàn bộ kiểm tra class loader, interface visibility/module hoặc method accessibility.

### 10.2. Method overload và nhận dạng metric

`method.getName()` đủ để trình bày ví dụ nhưng **không phân biệt** các overload như `run(String)` và `run(int)`. Với telemetry chuẩn, key có thể cần:

~~~java
String signature =
        method.getDeclaringClass().getName()
        + "#" + method.getName()
        + java.util.Arrays.toString(method.getParameterTypes());
~~~

Đây là fragment; có thể thêm return type hoặc module/classloader identity trong hệ thống nhiều loại proxy nếu định danh metric thực sự cần các thông tin đó. Tránh tạo label độc nhất theo input mỗi request vì cardinality cao làm metrics backend tốn bộ nhớ.

### 10.3. `null` và kiểu primitive

Khi method interface không nhận đối số, `args` có thể `null`; `Method.invoke(target, args)` dùng mảng đối số null hợp lệ cho phương thức không tham số. Khi method trả `void`, Reflection trả `null`. Ngược lại, nếu handler trả `null` cho method proxy khai báo trả `int`, proxy có thể ném `NullPointerException` trong unboxing; đây là lỗi adapter, không phải exception gốc của method đích.

### 10.4. Quyền truy cập

`Method.invoke` vẫn tuân thủ Java access checks và JPMS encapsulation. Tạo proxy không tự mở private package hay bỏ qua `IllegalAccessException`. Trường hợp dùng public interface nhưng implementation/lookup ở module khác cần bảo đảm receiver, declaring type và visibility thích hợp. Bài demo cố ý dùng `public interface Job` và `public static final class RealJob` để tránh nhiễu do quyền truy cập.

## 11. Kiểm thử có giá trị thực tế

Thay vì chỉ so sánh tên class của exception, hãy kiểm tra **object identity** và dữ liệu đo:

| Ca | Điều cần xác minh |
| --- | --- |
| Lời gọi trả về | Giá trị đúng và có đúng một bản ghi timing thành công |
| Checked exception khai báo | Caller bắt trực tiếp đúng loại, `caught == original` |
| Runtime exception | Caller bắt đúng object gốc, không bị bọc |
| `Error` | Caller nhận đúng `Error`, timing vẫn được ghi |
| `Object.toString` | Không đệ quy vô hạn, theo chính sách log đã định |
| Lỗi ở metric sink | Không được thay exception nghiệp vụ trong các trường hợp backend logging lỗi có thể xử lý |
| Hai method overload | Metric key phân biệt được nếu yêu cầu quan sát theo signature |
| Gọi đồng thời | Data sink và counter thread-safe, không mất record |
| Có nhiều interface với method trùng | Checked exception phải hợp lệ với mọi contract |

Trong demo, câu `checked preserved: true` là bằng chứng mạnh hơn việc in `IOException`. Đối với benchmark hiệu năng, đo nhiều lần và sử dụng **JMH** khi cần kết luận định lượng; ví dụ ngắn chỉ chứng minh luồng logic đo, không phải số nanosecond ổn định hay mức chi phí của proxy.

## 12. Tình huống nâng cao và giới hạn lựa chọn

**Nested proxies:** Nếu target lại là một proxy khác, tổng thời gian ở lớp ngoài bao gồm lớp trong. Nếu lớp trong thay đổi/wrap exception, outer handler chỉ nhìn thấy exception thực tế target proxy đã ném; không thể bảo đảm khôi phục một “ngoại lệ sâu hơn” nếu không biết hợp đồng nhiều lớp.

**Default methods:** Lời gọi default method trên interface cũng được đưa đến handler. `Method.invoke(target,args)` chỉ đúng khi bạn **cố ý delegate tới target** implement interface phù hợp. Nếu muốn chạy default body **trên chính proxy** theo Java 17, xem `InvocationHandler.invokeDefault` và các điều kiện truy cập/override riêng; không gọi lại default method trên proxy như lệnh delegate.

**`MethodHandle`:** Có thể dùng `MethodHandle` thay `Method.invoke` cho một số đường gọi sau khi xây lookup/access thích hợp. MethodHandle thường truyền exception từ target mà không bọc `InvocationTargetException` theo cơ chế của `Method.invoke`, nhưng bạn vẫn phải giữ nguyên contract exception, đo timing, và xử lý adapter errors.

**Spring AOP:** Có thể đo thời gian bằng around advice với `ProceedingJoinPoint.proceed()`, nơi exception từ join point có thể được truyền ra qua `throws Throwable`. Cách unwrap khác nhau giữa proxy/advice; **không áp dụng vô điều kiện** quy tắc bóc `InvocationTargetException` ở mọi framework, chỉ dùng khi chính bạn gọi `Method.invoke`.

**Async/reactive:** Muốn đo thời gian nghiệp vụ hoàn tất chứ không chỉ thời gian trả về future/reactive publisher, cần thiết kế metric lúc completion/error/subscribe phù hợp với mô hình concurrency. Không được “block” async chỉ để tái sử dụng interceptor đồng bộ của ví dụ.

## 13. Câu hỏi tự kiểm tra

1. Vì sao `method.invoke` khiến caller thấy exception lạ nếu handler không unwrap? Vì ngoại lệ từ method đích bị bọc trong `InvocationTargetException`, và proxy có thể bọc tiếp thành `UndeclaredThrowableException`.
2. Đâu là cách giữ nguyên throwable gốc? **`catch (InvocationTargetException ex) { throw ex.getCause(); }`**.
3. Vì sao không thể bảo đảm giữ checked exception khi interface không có `throws` phù hợp? Vì bytecode proxy phải tôn trọng hợp đồng checked exception của interface; trường hợp không hợp lệ bị bọc thành `UndeclaredThrowableException`.
4. Dùng `System.nanoTime()` để lấy “ngày giờ gọi method” có đúng không? **Không**; nó dùng đo khoảng thời gian bằng phép trừ, không phải wall-clock timestamp.
5. Vì sao ghi metric trong `finally`? Để ghi cả nhánh return và nhánh exception. Nhưng phải hạn chế lỗi của chính metric sink che lỗi chính.
6. Kiểm tra `ex == target.checked` xác minh điều gì? **Cùng identity Throwable**, không chỉ cùng class hoặc nội dung thông báo.
7. Có nên gọi `method.invoke(proxy, args)` từ handler không? **Không**, vì có thể lặp lại handler vô hạn. Delegate vào `target`.
8. Dùng `ArrayList` chung để ghi timing từ nhiều thread an toàn không? **Không**; dùng cấu trúc đồng thời hoặc recorder có cơ chế thread safety.
9. Vì sao thời gian đo không luôn là thời gian “method thật” thuần túy? Vì khoảng đo bao gồm cả Reflective Invocation và overhead liên quan; phương thức async có thể hoàn thành sau.
10. Tại sao `toString`/`equals`/`hashCode` cần chính sách riêng? Vì ba method này cũng được JDK proxy điều hướng qua handler.

## 14. Tài liệu tham khảo chính thức Java 17

- [Oracle Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): cách dispatch method, xử lý `Object` methods và giới hạn checked exception.
- [Oracle Java SE 17 — InvocationHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html): hợp đồng `invoke` và `invokeDefault`.
- [Oracle Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` và hành vi bọc exception.
- [Oracle Java SE 17 — InvocationTargetException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): `getCause()` trả ngoại lệ của method đích.
- [Oracle Java SE 17 — UndeclaredThrowableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html): wrapper cho checked exception không được interface khai báo.

**Ghi nhớ:** Dynamic proxy có thể đo thời gian và chuyển tiếp minh bạch khi handler dùng `System.nanoTime()` trong `try/finally`, gọi **target thật**, và **ném lại đúng `InvocationTargetException.getCause()`**. Ngoại lệ checked vẫn phải được interface cho phép; metric/logging không được làm mất kết quả hoặc throwable của nghiệp vụ.