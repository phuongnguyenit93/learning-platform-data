# Bài tập tổng hợp AOP: Đo thời gian và bảo toàn kết quả, ngoại lệ của lời gọi

## 1. Yêu cầu bài toán và tiêu chí hoàn thành

Xây dựng một **advice đo thời gian** chạy quanh phương thức nghiệp vụ. Advice ghi nhận thời lượng dù lời gọi **thành công hay ném ngoại lệ**, đồng thời bảo toàn hợp đồng của phương thức: kết quả trả về, đối tượng ngoại lệ, số lần thực thi và thứ tự xử lý.

Đây là một bài tổng hợp quan trọng vì `around advice` có quyền quyết định có thực hiện lời gọi gốc (`proceed`), thực hiện bao nhiêu lần, sửa giá trị trả về hoặc chuyển đổi ngoại lệ. Một lỗi nhỏ trong phần quan sát có thể biến một lời gọi đơn giản thành hành vi khác với logic ban đầu.

**Yêu cầu bắt buộc:**

1. Đo thời gian thực thi của lời gọi bằng một nguồn thời gian thích hợp để đo khoảng thời gian.
2. Gọi mục tiêu **đúng một lần** đối với mỗi lời gọi được chặn, trừ khi đặc tả nghiệp vụ cho phép retry rõ ràng.
3. Nếu mục tiêu trả về bình thường, advice trả về **đúng giá trị** mà mục tiêu tạo ra, kể cả `null`, giá trị primitive và tham chiếu đối tượng.
4. Nếu mục tiêu ném ngoại lệ, advice để chính ngoại lệ đó tiếp tục lan ra caller: không nuốt, không tự ý thay loại, message, cause hoặc identity.
5. Ghi số đo trên cả đường thành công và đường lỗi; phân biệt outcome để không báo một lời gọi lỗi là thành công.
6. Tránh để logging/metrics làm thay đổi kết quả nghiệp vụ; xác định rõ chính sách khi bộ ghi nhận số đo gặp sự cố.
7. Kiểm tra một trường hợp bình thường, một trường hợp trả `null`, một ngoại lệ runtime và một ngoại lệ checked (nếu API hỗ trợ).
8. Phân biệt thời gian của **method execution** với thời gian toàn bộ request, network, retry hoặc việc chờ tác vụ bất đồng bộ.

**Kết quả mong đợi:** caller quan sát hành vi giống khi không có aspect, còn hệ thống đo lường có thêm bản ghi về method, thời lượng và outcome.

## 2. Kiến thức AOP cần sử dụng

Trong lập trình hướng khía cạnh:

| Khái niệm | Áp dụng vào bài |
| --- | --- |
| Aspect | Đóng gói logic đo thời gian, tách khỏi nghiệp vụ |
| Join point | Sự kiện thực thi được quan sát, ví dụ `execution` của một method |
| Pointcut | Chọn đúng tập lời gọi cần đo, tránh bắt cả helper ghi metric |
| Around advice | Bao quanh phần nghiệp vụ và dùng `proceed` để tiếp tục thực thi |
| Advice precedence | Quyết định khoảng đo có bao gồm những advice bên trong hay không |
| Weaving hoặc interception | Cơ chế để lời gọi đi qua advice, không phải cú pháp pointcut đơn thuần |

Với một công cụ AOP có hỗ trợ weaving tại method execution, mô hình khái niệm là:

```text
caller
  |
  v
[around advice: start = nanoTime()]
  |
  +--> proceed() --> [business method]
  |                      |
  |                      +--> return value
  |                      +--> throw exception
  |
[finally: elapsed = nanoTime() - start, record sample]
  |
  +--> return đúng value ban đầu
  +--> throw đúng exception ban đầu
```

Đối với AOP dựa trên proxy, sự kiện được chặn là lời gọi đi qua **proxy boundary**. Nếu caller dùng tham chiếu target trực tiếp, lời gọi có thể bỏ qua advice. Với weaving ở method execution, phạm vi quan sát có thể bao gồm cả lời gọi nội bộ, tùy bytecode và cấu hình đã weave. Khi đánh giá bài làm, phải ghi rõ **cơ chế AOP nào đang được mô phỏng**.

### 2.1. Công thức đo

```text
startNs = monotonicClock()
try:
    return proceedExactlyOnce()
finally:
    elapsedNs = monotonicClock() - startNs
    record(elapsedNs, outcome)
```

`System.nanoTime()` phù hợp với việc đo **khoảng thời gian** trong một JVM. Giá trị trả về của nó có mốc tùy ý; không dùng để đổi trực tiếp thành ngày giờ. Trong khi đó, `System.currentTimeMillis()` là đồng hồ thời gian thực, có thể bị điều chỉnh, nên không thích hợp bằng cho đo duration ngắn. Tính khoảng đo bằng **hiệu hai lần `nanoTime()`**, không so sánh một timestamp tuyệt đối với timestamp từ JVM hay máy khác.

Trong ứng dụng rất dài hạn, việc trừ hai giá trị `long` có thể bị ảnh hưởng khi khoảng đo kéo dài quá khoảng xấp xỉ 292 năm; với một method invocation thông thường, cách trừ này là phù hợp. Đừng chuyển sớm sang milliseconds nếu bạn cần giữ độ phân giải nanos. **Độ phân giải đơn vị nano không đồng nghĩa độ chính xác tuyệt đối tới từng nano giây**.

### 2.2. Bảo toàn semantics quan trọng hơn log

Một `around advice` quan sát nên tương đương logic gốc trên những điều caller thấy:

- **Giá trị:** đối với reference, bảo toàn chính **tham chiếu** nếu contract yêu cầu; đối với primitive, bảo toàn giá trị theo đúng kiểu.
- **Ngoại lệ:** giữ nguyên đối tượng `Throwable` khi có thể, đặc biệt exception do mục tiêu phát sinh; không vô tình biến checked exception thành một wrapper khác.
- **Số lần:** không gọi `proceed()` hai lần chỉ vì muốn “so sánh trước/sau”; việc thực thi lại có thể nhân đôi giao dịch hoặc ghi dữ liệu.
- **Thứ tự:** không trả trước khi logic bắt buộc hoàn tất; không nuốt exception hay ném exception mới từ `finally` nếu mục tiêu đang lỗi.
- **Luồng:** đo đúng boundaries; một lời gọi method đồng bộ có thể trả về `Future`/`CompletionStage` trước khi tác vụ bất đồng bộ hoàn tất.

Không có nghĩa mọi advice phải thuần quan sát; authorization, retry hay transaction advice có thể có contract chủ động thay đổi hành vi. Bài này chỉ triển khai **timing aspect không đổi semantics**.

## 3. Vì sao phải đo trong `finally`?

Cách dễ sai:

```java
long started = System.nanoTime();
Object result = proceed();
record(System.nanoTime() - started);
return result;
```

Đây là **mảnh minh họa**: `proceed()` đại diện API của around advice chứ không phải hàm JDK có sẵn. Khi mục tiêu ném ngoại lệ, dòng `record(...)` không chạy. Kết quả là bảng metrics chỉ thống kê các lời gọi thành công và khiến latency/error data bị lệch.

Cách đúng ở mức nguyên tắc:

```java
long started = System.nanoTime();
try {
    return proceed();  // Thực thi đúng một lần.
} finally {
    long elapsedNs = System.nanoTime() - started;
    recordSafely(elapsedNs);
}
```

Trong code thực, hàm `recordSafely` còn cần có outcome. Nếu `finally` ném exception mới, exception của mục tiêu có thể bị thay thế. Vì vậy recorder nên được thiết kế **không tạo ảnh hưởng lên luồng nghiệp vụ**, hoặc có biện pháp cô lập lỗi theo yêu cầu vận hành.

Đừng ghi `return` trong `finally`: Java sẽ ưu tiên return đó, có thể bỏ qua giá trị và ngoại lệ phát sinh từ `try`. Tương tự, `throw` từ `finally` có thể che lấp lỗi ban đầu.

## 4. Ví dụ Java 17 chạy độc lập: mô phỏng around advice bằng JDK dynamic proxy

Ví dụ sau dùng `java.lang.reflect.Proxy` để tạo một interceptor tương đương around advice. Đây là **bài thực hành AOP ở mức nguyên lý**, không yêu cầu một công cụ weaving bên ngoài. Điểm quan trọng là cơ chế **chuyển tiếp đúng return và exception**.

Lưu mã thành file **`TimingAspectExercise.java`**:

```java
import java.io.IOException;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public final class TimingAspectExercise {
    interface Service {
        String value();
        String absent();
        int divide(int left, int right);
        void read() throws IOException;
    }

    static final class RealService implements Service {
        final String expectedValue = new String("READY");
        final IOException expectedFailure = new IOException("read failed");

        @Override
        public String value() {
            return expectedValue;
        }

        @Override
        public String absent() {
            return null;
        }

        @Override
        public int divide(int left, int right) {
            return left / right;
        }

        @Override
        public void read() throws IOException {
            throw expectedFailure;
        }
    }

    record Sample(String method, boolean success, long durationNanos) {}

    static final class TimingHandler implements InvocationHandler {
        private final Service target;
        private final List<Sample> samples;

        TimingHandler(Service target, List<Sample> samples) {
            this.target = target;
            this.samples = samples;
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] args)
                throws Throwable {
            long started = System.nanoTime();
            boolean success = false;

            try {
                // Reflection trả về Object; giá trị primitive được boxing.
                Object result = method.invoke(target, args);
                success = true;
                return result;
            } catch (InvocationTargetException wrapper) {
                // Lấy đúng ngoại lệ do target ném, tránh trả wrapper.
                throw wrapper.getCause();
            } finally {
                long elapsed = System.nanoTime() - started;
                samples.add(new Sample(method.getName(), success, elapsed));
            }
        }
    }

    public static void main(String[] args) {
        RealService real = new RealService();
        List<Sample> samples = new ArrayList<>();
        Service service = (Service) Proxy.newProxyInstance(
                Service.class.getClassLoader(),
                new Class<?>[] {Service.class},
                new TimingHandler(real, samples)
        );

        String returned = service.value();
        System.out.println("same reference: "
                + (returned == real.expectedValue));

        System.out.println("null kept: " + (service.absent() == null));
        System.out.println("divide result: " + service.divide(8, 2));

        try {
            service.divide(1, 0);
        } catch (ArithmeticException error) {
            System.out.println("runtime type: "
                    + error.getClass().getSimpleName());
        }

        try {
            service.read();
        } catch (IOException error) {
            System.out.println("same checked exception: "
                    + (error == real.expectedFailure));
        }

        for (Sample sample : samples) {
            System.out.println("sample " + sample.method()
                    + " success=" + sample.success()
                    + " durationNonnegative="
                    + (sample.durationNanos() >= 0));
        }
    }
}
```

Chạy với **JDK 17 trở lên**:

```bash
javac TimingAspectExercise.java
java TimingAspectExercise
```

**Standard output** cho chương trình (thời lượng thực không được in ra vì thay đổi theo máy):

```text
same reference: true
null kept: true
divide result: 4
runtime type: ArithmeticException
same checked exception: true
sample value success=true durationNonnegative=true
sample absent success=true durationNonnegative=true
sample divide success=true durationNonnegative=true
sample divide success=false durationNonnegative=true
sample read success=false durationNonnegative=true
```

Giải thích cách bài làm giữ semantics:

1. `value()` trả lại **cùng một instance `String`** do target tạo; phép so sánh tham chiếu dùng `==` cho kết quả `true`.
2. `absent()` trả `null` nguyên trạng; advice không tự thay bằng chuỗi rỗng hay đối tượng khác.
3. `divide(8, 2)` trả `int 4`, dù `Method.invoke` boxing giá trị primitive thành `Integer` ở biên reflection. Proxy tự unbox khi trả về qua chữ ký interface.
4. `divide(1, 0)` vẫn ném `ArithmeticException`. Advice ghi `success=false` nhờ `finally`, nhưng không bắt rồi chuyển ngoại lệ thành giá trị mặc định.
5. `read()` ném checked `IOException`; Reflection bọc exception đích thành `InvocationTargetException`, do đó handler phải dùng `wrapper.getCause()` để chuyển tiếp **đúng đối tượng exception ban đầu**. Interface `Service.read() throws IOException` cho phép proxy chuyển tiếp checked exception này.
6. Mỗi method call tạo đúng **một `Sample`**. Biến `success` chỉ được gán `true` khi `method.invoke` trả bình thường; exception khiến sample ghi thất bại.
7. Số đo `durationNanos` thực nằm trong từng record `Sample`. Output cố tình chỉ kiểm tra số đo không âm để trình bày được một stdout ổn định; duration thực tùy JVM/CPU/GC và workload.

**Giới hạn ví dụ:** `List<Sample>` là `ArrayList` trong chương trình chạy tuần tự. Với concurrent requests, phải dùng collector an toàn đa luồng hoặc một hệ thống metrics phù hợp, tránh `ArrayList` chia sẻ không đồng bộ. Đo lường ở đây bao quanh **`Method.invoke`**, không nhất thiết phản ánh tổng thời gian caller gọi qua proxy hay một network request.

### 4.1. Vì sao không dùng `catch (Exception) { return null; }`?

Một lỗi phổ biến trong interceptor:

```java
try {
    return method.invoke(target, args);
} catch (Exception ignored) {
    return null; // SAI: nuốt lỗi và có thể gây NullPointerException khi unbox.
}
```

Đây là mã **cố ý sai để phân tích**, không dùng trong bài giải cuối. Với method trả primitive như `int`, `null` thậm chí có thể gây `NullPointerException` ở đoạn unboxing của proxy và che khuất `ArithmeticException` gốc. Với phương thức trả object, caller có thể tưởng `null` là kết quả nghiệp vụ hợp lệ. Vì vậy việc “đo được latency” không chứng minh advice đúng.

### 4.2. Tại sao chỉ unwrap `InvocationTargetException`?

`Method.invoke` ném `InvocationTargetException` khi **phương thức đích** ném exception. Những lỗi reflection khác như `IllegalAccessException` là lỗi sử dụng reflection/thiết lập interceptor, không phải business exception tương đương từ method đích. Bài tập yêu cầu giữ nguyên exception do target ném; không che khuất lỗi cấu hình bằng cách biến mọi exception thành nguyên nhân tùy tiện.

JDK dynamic proxy có ràng buộc với checked exception: nếu handler ném một checked exception không được khai báo bởi phương thức interface, proxy có thể bọc nó trong `UndeclaredThrowableException`. Muốn bảo toàn contract checked exception, **interface khai báo đúng `throws`** và interceptor chuyển tiếp loại phù hợp.

### 4.3. Ngoại lệ xảy ra trong metric recorder

Dòng `samples.add(...)` ở `finally` giả định collector hoạt động. Nếu chính collector ném exception, nó có thể **thay thế** giá trị trả về hoặc ngoại lệ mục tiêu. Trong hệ thống đo lường mà tính quan sát không được cản trở nghiệp vụ, dùng phương án cô lập lỗi:

```java
// Minh họa ý tưởng, giả định recorder là một đối tượng có sẵn.
try {
    recorder.record(methodName, success, elapsedNs);
} catch (RuntimeException measurementFailure) {
    // Tăng bộ đếm lỗi đo lường độc lập hoặc bỏ mẫu theo chính sách.
    // Không ném tiếp để tránh thay đổi kết quả/ngoại lệ nghiệp vụ.
}
```

Đoạn trên chỉ là **mảnh minh họa**, không phải chương trình Java biên dịch độc lập: `recorder`, `methodName`, `success` và `elapsedNs` cần được khai báo trong code thực. Không nên tùy tiện bắt `Throwable` để nuốt cả lỗi nghiêm trọng ở JVM; chính sách cần phân biệt lỗi đo lường có thể phục hồi và lỗi hệ thống. Nếu việc ghi audit là yêu cầu bắt buộc, chính sách xử lý lỗi có thể khác timing metric tùy hợp đồng nghiệp vụ.

## 5. Áp dụng vào aspect sử dụng weaving

Khi công cụ AOP hỗ trợ around advice với `proceed`, thuật toán tương đương: lấy thời gian ngay trước `proceed` và thu sample trong `finally`. Ví dụ cú pháp **AspectJ code-style** sau minh họa cho **một method trả `int` cụ thể**, cần toolchain weaving và class `demo.Calculator` phù hợp nên **không chạy độc lập bằng `javac`**:

```java
package demo;

public aspect TimingAspect {
    int around(): execution(int demo.Calculator.divide(int, int)) {
        long started = System.nanoTime();
        try {
            return proceed();
        } finally {
            long elapsed = System.nanoTime() - started;
            System.out.println("durationNanos=" + elapsed);
        }
    }
}
```

Aspect chọn join point **thực thi** `Calculator.divide(int, int)`. `proceed()` giữ nguyên giá trị `int` hoặc cho phép exception đi ra; `finally` vẫn chạy khi target ném lỗi. Dòng log in ra duration không cố định. Trong ứng dụng thực, nếu logging có thể làm thay đổi hành vi, thay bằng recorder được cô lập lỗi, không log dữ liệu nhạy cảm và không để helper cũng khớp pointcut gây đệ quy.

Lưu ý: nếu chọn pointcut có cả method trả `void` lẫn reference và primitive, cần thiết kế đúng signature của `around`/`proceed` theo quy tắc của **AOP engine cụ thể**. Không suy luận mọi công cụ tự chuyển kiểu hay chấp nhận một `Object around` cho tất cả method. Với đoạn ví dụ này, pointcut cố ý hẹp để giữ kiểu `int` rõ ràng.

### 5.1. Ý nghĩa của advice precedence

Giả sử một method có `TimingAspect` và `ValidationAspect` cùng match. Nếu timing là lớp `around` bên ngoài, khoảng đo gồm cả thời gian validation, những advice nằm trong và target. Nếu timing nằm bên trong, khoảng đo bắt đầu sau validation và không tính overhead của advice bên ngoài.

```text
Timing.before (start)
  Validation.before
    Target
  Validation.after
Timing.after (stop)
```

Đây là **mô tả nesting**, không tự suy ra thứ tự precedence của từng engine. Muốn so sánh latency giữa hai lần triển khai, thứ tự advice và vùng đo phải được định nghĩa ổn định. Đồng thời lưu ý `after` trên các advice bao ngoài sẽ chạy theo thứ tự stack unwind.

### 5.2. Chọn đúng join point

- `execution` đo sự thực thi của thân phương thức đã được weave.
- `call` đo sự kiện tại call site đã được weave, có thể bao gồm overhead khác.
- Proxy interception đo đoạn chuyển tiếp qua proxy, có thể bỏ qua self-invocation tùy loại proxy.
- Nếu method được gọi lặp qua retry, recursion hoặc callback, mỗi invocation có một duration; không gộp tùy ý thành một request duration.
- Advice `around` có thể bỏ `proceed` hoặc gọi nhiều lần, nhưng bài này yêu cầu **một lần và bảo toàn nghiệp vụ**.

Một phép test nên xác định rõ số lượng execution join point và advice invocation. Hai dòng log giống nhau không đủ chứng minh target chạy hai lần: có thể là hai advice, hai mức gọi lồng, hoặc log vào/ra.

## 6. Bài tập mở rộng để người học tự thực hành

### Bài A — bảo toàn giá trị và ngoại lệ

Từ ví dụ `TimingAspectExercise`, bổ sung method:

```java
// Mảnh code bổ sung vào interface và implementation tương ứng.
String echo(String input);
```

Cho `echo("x")` trả một reference được cung cấp bởi implementation và `echo(null)` trả `null`. Viết assert với `==` cho reference nếu contract yêu cầu identity; so nội dung bằng `equals` trong trường hợp chỉ cần equality. Sau đó thêm method ném checked exception có subtype, xác nhận type và identity đi đến caller không đổi.

**Tiêu chí đạt:** 5 ca hiện có vẫn qua, thêm các trường hợp `echo` đúng, số sample bằng số invocation, không có exception bị wrap không mong muốn.

### Bài B — exception và cleanup

Cố tình chuyển `samples.add` ra phía sau `method.invoke` thay vì `finally`. Chạy lại ca `divide(1,0)` và `read()`: số sample giảm, cho thấy phương pháp chỉ đo success đã bỏ qua request lỗi. Khôi phục `finally`, rồi mô phỏng recorder ném `IllegalStateException` để thấy nó có thể che business exception nếu không được cách ly.

**Tiêu chí đạt:** ghi được cả success và failure mà vẫn giữ nguyên ngoại lệ của target. Không giải quyết bằng `return null` hay `return 0` khi gặp lỗi.

### Bài C — proxy, pointcut và weaving

Thu hẹp interceptor để chỉ đo `divide`; giữ `value`/`absent`/`read` hoạt động bình thường qua proxy. Tiếp theo gọi trực tiếp `real.divide(8, 2)` để thấy đường raw target không được đo. Nếu triển khai bằng weaving tại method execution, hãy so sánh và giải thích vì sao đường raw target **có thể** được quan sát nếu class tương ứng đã được weave.

**Tiêu chí đạt:** giải thích bằng **điểm đi qua interception**, tránh đánh đồng pointcut không match với lời gọi không qua proxy.

### Bài D — thống kê theo outcome

Tính count, số mẫu success/failure, min/max và trung bình duration từ `List<Sample>`. Chỉ dùng dữ liệu sample để đo method; không gắn patient/user/payment ID vào nhãn metric. Với histogram production, tránh lưu mọi sample vô hạn trong RAM.

Có thể dùng `LongSummaryStatistics` cho tập duration đơn giản, nhưng phải hiểu trung bình không thay thế percentile và không trực tiếp thể hiện tail latency. Mọi so sánh p95/p99 cần đủ mẫu và cùng phân phối workload.

### Bài E — concurrency và async

Cho nhiều thread gọi proxy; thay `ArrayList` bằng collector an toàn đa luồng và kiểm tra số sample không bị mất. Tiếp theo thử một method trả `CompletableFuture`: advice `around` đồng bộ chỉ đo tới thời điểm **trả về future**, chưa chắc đo tới khi future hoàn thành. Nếu yêu cầu đo toàn bộ tác vụ async, cần gắn completion callback riêng, đo từ lúc bắt đầu đến khi completion và chuyển tiếp nguyên trạng success/exception/cancellation theo contract.

**Tiêu chí đạt:** không race condition, không rò trạng thái luồng, không tự thay exception completion hoặc thay đổi cách cancellation lan truyền.

## 7. Kiểm thử đầy đủ về tính tương đương

Bảng kiểm thử sau giúp chứng minh bộ đo không thay đổi lời gọi:

| Trường hợp | Hành vi khi gọi target trực tiếp | Hành vi sau khi áp advice | Sample |
| --- | --- | --- | --- |
| Trả đối tượng | Cùng reference được trả về | Giữ identity, không clone | success |
| Trả `null` | `null` | Vẫn `null` | success |
| Trả primitive | Giá trị chính xác | Vẫn đúng giá trị | success |
| `void` bình thường | Không ném exception | Không ném exception | success |
| Runtime exception | Exception đúng type/message/cause | Cùng exception gốc nếu cơ chế cho phép | failure |
| Checked exception | Exception khai báo bởi method | Không bị đổi thành wrapper khác | failure |
| Lời gọi lặp hoặc đồng thời | Một execution cho mỗi lần nghiệp vụ gọi | Advice và sample có số lần tương ứng | một sample/invocation |
| Ném lỗi trong metric recorder | Nghiệp vụ không phụ thuộc metrics | Theo chính sách cô lập lỗi đo lường, không che kết quả | có thể bỏ sample |
| Async return | Trả về task/future | Không làm đổi future; thời gian đến completion cần đo riêng | xác định scope |

### 7.1. Điều gì có thể xác nhận bằng unit test?

- Dùng target giả có counter để xác nhận **mỗi intercepted invocation gọi target đúng một lần**.
- Dùng tham chiếu object riêng để xác nhận return **identity**.
- Dùng một exception instance riêng để assert `caught == expected`; kiểm cả checked và unchecked.
- Xác nhận sample xuất hiện dù target ném exception; sample có đúng method name và outcome.
- Dùng recorder cố ý ném lỗi để test chính sách cách ly telemetry.
- Với thời lượng, kiểm ≥ 0 cho lời gọi ngắn và tránh assert một số nano/milli giây chính xác vì hệ điều hành, JIT và GC gây nhiễu.

### 7.2. Điều gì nên xác nhận bằng integration test?

- Aspect/weaver/proxy thực sự được cấu hình và pointcut match đúng nơi.
- Gọi từ caller thực có đi qua interception boundary hay không.
- Advice precedence đúng như ý định; thời gian được đo bao gồm/loại trừ các advice khác theo cấu hình.
- Method có annotation, overload, generic bridge hoặc bytecode sinh bởi compiler có bị khớp ngoài phạm vi không.
- Kết quả của class/JAR **sau weaving** đúng với artifact chạy thật.
- Khi concurrency, sampling, export và logging hoạt động, không xuất hiện deadlock, recursion hay overhead vượt ngân sách.

## 8. Những bẫy nâng cao

### 8.1. Đừng dùng `System.currentTimeMillis()` để so duration rất ngắn

`currentTimeMillis()` là wall clock, thích hợp cho timestamp để đối chiếu lịch, còn `nanoTime()` thích hợp cho elapsed time. Nếu cần cả hai, ghi timestamp riêng và duration riêng. Không tính latency bằng timestamp gửi từ hai máy khác nhau khi đồng hồ chưa được đồng bộ hoặc độ chính xác clock không đủ.

### 8.2. Một lời gọi nhìn từ ngoài có thể tạo nhiều sample

Một request có thể đi qua nhiều method và join point; around advice khác cũng có thể ghi thời gian. Recursion, retries và nested calls không nhất thiết là lỗi. Để tổng hợp, dùng `traceId`/`spanId` hoặc invocation ID, và phân biệt **exclusive time** (chỉ phần tự chạy) với **inclusive time** (bao gồm lời gọi con). Bài tập cơ bản đo inclusive elapsed tại boundary đã chọn.

### 8.3. Logging có thể gây lời gọi đệ quy

Nếu pointcut bắt cả method ghi log, serializer, metric exporter hoặc `toString()` của đối tượng, advice đo thời gian có thể kích hoạt chính nó. Thu hẹp pointcut, loại trừ helper hoặc dùng reentrancy guard có scope rõ. Guard theo `ThreadLocal` phải giải phóng trong `finally`; nó không tự truyền qua async task.

### 8.4. Đo thời gian không có nghĩa hệ thống ít overhead

`System.nanoTime()` có chi phí, còn việc dựng chuỗi, lấy stack trace, ghi sync log hoặc export metrics có thể tốn hơn nhiều. Bản đo cũng có thể ảnh hưởng tốc độ ứng dụng. Cần đánh giá overhead với workload thật, sampling phù hợp, collector giới hạn dung lượng và nhãn cardinality thấp.

### 8.5. Ngoại lệ từ advice khác cũng nằm trong phạm vi đo tùy nesting

Nếu một advice ở phía trong ném lỗi **trước khi target chạy**, timing advice ở ngoài vẫn ghi failure cho lời gọi vào chain, mặc dù thân nghiệp vụ chưa được thực hiện. Vì thế metric “execution latency” phải mô tả rõ đo **target body** hay **interception chain**. Kết quả còn phụ thuộc việc pointcut chọn `call`, `execution` hoặc lời gọi qua proxy.

### 8.6. Cẩn thận với `InterruptedException`, cancellation và thời hạn

Không tự nuốt `InterruptedException`. Nếu advice cần bắt ngoại lệ để ghi outcome, hãy ném lại theo contract; nếu can thiệp vào interrupt status phải hiểu API đang dùng. Khi gặp `CancellationException` hoặc future bị cancel, không tự chuyển thành success. Bài đo thời gian không được vô tình làm thay đổi chính sách timeout/cancellation.

### 8.7. Phân biệt giám sát với benchmarking

Một lần chạy đo được 120 ns không có nghĩa method luôn mất 120 ns. JIT warmup, tiered compilation, CPU scheduling, GC, cache, dead-code elimination và contention khiến microbenchmark rất dễ sai. Dùng công cụ benchmark chuyên dụng khi cần số liệu hiệu năng chính xác, và dùng observability trong hệ thống thực để theo dõi latency theo workload.

## 9. Quy trình giải bài mẫu

1. **Viết contract của target** gồm return type, các ngoại lệ có thể ném, số lần gọi dự kiến và hành vi khi `null`.
2. **Chọn join point rõ ràng**; không chọn wildcard toàn hệ thống từ đầu.
3. **Đưa mốc bắt đầu vào trước khi chuyển tiếp**; không làm logging hoặc network I/O tốn kém ngay trước mốc nếu muốn đo phạm vi hợp lý.
4. **Gọi `proceed` hoặc target đúng một lần**; chuyển tiếp toàn bộ tham số và giữ nguyên kết quả.
5. **Đánh dấu outcome:** bình thường thì success, ném lỗi thì failure; không gán success trước khi target kết thúc.
6. **Dùng `finally`** lấy thời lượng và ghi sample, nhưng tách lỗi metric recorder khỏi luồng nghiệp vụ khi được yêu cầu bảo toàn semantics.
7. **Test cả success và failure**; đặc biệt assert identity của reference và exception.
8. **Kiểm thử đúng AOP engine** trong build/runtime; không coi ví dụ proxy JDK là mô hình duy nhất.
9. **Đọc số liệu đúng ngữ cảnh**: đồng bộ hay async, inclusive hay exclusive, có advice khác nằm trong phạm vi đo hay không.

## 10. Checklist tự đánh giá

- [ ] Đã mô tả đúng vấn đề: đo duration **và** không thay đổi return/exception.
- [ ] Dùng `System.nanoTime()` như một nguồn elapsed time, lấy hiệu đúng hai mốc.
- [ ] Advice/handler gọi target đúng một lần trong trường hợp thông thường.
- [ ] Có `finally` để ghi sample trên cả return và throw.
- [ ] Dùng outcome thành công/thất bại chính xác; không báo success khi target ném lỗi.
- [ ] Không nuốt, đổi loại, sửa message, mất cause hoặc thay identity ngoại lệ đích.
- [ ] Không tự biến `null` thành giá trị khác, không hỏng boxing/unboxing primitive.
- [ ] Nếu dùng JDK reflection, đã unwrap `InvocationTargetException` đúng chỗ.
- [ ] Recorder được xử lý theo chính sách không phá contract nghiệp vụ.
- [ ] Phân biệt proxy interception với weaving tại `execution` và biết nơi lời gọi có thể bypass.
- [ ] Đã chạy code Java 17, kiểm tra stdout và test các nhánh trả về, runtime/checked exception.
- [ ] Đã định nghĩa phạm vi thời gian đo trong advice chain và khi trả asynchronous result.
- [ ] Không đưa helper đo/log vào pointcut gây recursion; không tạo metrics có cardinality quá cao.

**Tiêu chuẩn của một timing aspect đúng:** với mọi input và mọi nhánh thực thi được hỗ trợ, nếu bỏ phần ghi nhận sample đi thì caller vẫn nhận **cùng giá trị hoặc cùng ngoại lệ**, và mục tiêu không chạy thêm lần nào do việc đo thời gian.
