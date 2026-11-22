# Advice khi có ngoại lệ và ngữ cảnh lỗi

## 1. Vì sao advice xử lý ngoại lệ là phần cốt lõi của AOP?

Trong Aspect-Oriented Programming (**AOP**), **advice** là hành vi được kết hợp tại những **join point** do **pointcut** lựa chọn. Nhiều chính sách xuyên suốt phải phản ứng khác nhau giữa hai kết quả:

- Phương thức **trả về bình thường**: ghi số lần thành công, đo thời gian, kết thúc trace với trạng thái OK.
- Phương thức **kết thúc bằng ngoại lệ**: ghi sự kiện thất bại, gắn loại lỗi, dọn dẹp context, bảo toàn lỗi để caller quyết định cách xử lý.

Loại advice thường được gọi là **after-throwing advice** hoặc **advice khi ném ngoại lệ** phục vụ trường hợp thứ hai. Đây là khái niệm AOP tổng quát; **tên cú pháp, loại join point, khả năng lấy ngoại lệ và ngữ nghĩa thứ tự giữa các advice phụ thuộc ngôn ngữ/công cụ**. Không nên suy luận rằng mọi hệ thống AOP đều có cùng bộ API.

Sau bài học, bạn có thể:

1. Phân biệt **before**, **after-returning**, **after-throwing**, **after/finally** và **around** trên hai luồng kết thúc thành công/thất bại.
2. Xác định khi nào một exception thực sự **thoát ra khỏi join point** và khi nào nó chỉ bị bắt, xử lý bên trong target.
3. Đọc ngữ cảnh lỗi: loại exception, message, cause, suppressed exceptions, join point, đối số, correlation ID và thông tin trace; phân biệt thông tin nên/không nên ghi.
4. Viết advice quan sát lỗi nhưng **không nuốt lỗi, không đổi kiểu và không che lỗi gốc** ngoài chủ đích đã được công bố.
5. Giải thích giới hạn của proxy, reflection, weaving và điểm lỗi xảy ra trong một chuỗi nhiều advice.
6. Phân biệt một method **ném exception ngay** với một API bất đồng bộ **trả về handle rồi thất bại sau**.
7. Tự chạy ví dụ Java 17 minh họa after-throwing, cleanup, checked exception và runtime exception.

## 2. Mô hình cơ bản: join point và đường ngoại lệ

Giả sử một method `send()` được pointcut chọn. Tối giản hóa các trạng thái có thể xảy ra:

```text
caller
  |
  v
before advice
  |
  v
target.send()
  |
  +---- trả về bình thường ------> after-returning advice
  |                                   |
  |                                   v
  |                              after/finally
  |
  +---- ném ngoại lệ ra ngoài ---> after-throwing advice
                                      |
                                      v
                                 after/finally
                                      |
                                      v
                            caller nhận exception
```

Sơ đồ này minh họa **điều kiện kích hoạt**, không ấn định trật tự giữa nhiều aspect trong tất cả công cụ. Một advice riêng có thể chạy ở nhiều thời điểm, một quanh (*around*) có thể bọc các lời gọi khác nhau, và thứ tự thực tế phụ thuộc quy tắc precedence của engine.

### 2.1. Những loại advice dễ nhầm

| Loại hành vi | Điều kiện xảy ra | Giá trị sử dụng |
| --- | --- | --- |
| **Before** | Trước khi join point tiếp tục vào phần được chặn, nếu đã được chọn. | Mở trace, đánh dấu bắt đầu, ghi correlation ID. |
| **After returning** | Điểm được chọn **kết thúc bình thường**. | Ghi thành công, kiểm tra thông tin kết quả nếu công cụ hỗ trợ. |
| **After throwing** | Điểm được chọn **kết thúc bằng một ngoại lệ thoát ra**, thường có thể lọc theo loại lỗi. | Đếm lỗi, ghi error metadata, đánh dấu span thất bại. |
| **After/finally** | Điểm kết thúc bằng return **hoặc** throw theo ngữ nghĩa công cụ. | Dọn tài nguyên/context; ghi tổng thời lượng cả success/failure. |
| **Around** | Bao quanh phần được chọn, có thể gọi `proceed` hoặc tương đương. | Điều phối trước/sau, bắt ngoại lệ, quyết định xử lý tiếp có chủ đích. |

Tên `after throwing` mô tả **kết cục mà join point quan sát**. Nó không có nghĩa advice chỉ chạy khi có dòng `throw` trực tiếp trong source của target. Một method có thể gọi thư viện ném lỗi, và lỗi đó thoát qua method; ngược lại method có thể tự `throw` rồi `catch` và xử lý thành công trước khi return.

### 2.2. Ví dụ quan trọng: exception bị bắt bên trong target

```java
String load() {
    try {
        return readRemote();
    } catch (java.io.IOException ex) {
        return "cached";
    }
}
```

Nếu `readRemote()` ném `IOException` nhưng `load()` bắt lỗi và trả `"cached"`, thì **method execution của `load()` kết thúc bình thường**. After-throwing advice gắn vào **execution của `load()`** thông thường không thấy `IOException` thoát ra. After-returning advice của `load()` có thể chạy.

Một công cụ hỗ trợ join point ở **execution của `readRemote()`**, **call `readRemote()`** hoặc **exception handler** có thể quan sát sự kiện khác, nếu pointcut và weaving tương ứng được cài. Đây là lý do phải nêu **loại join point** thay vì nói mơ hồ “advice sẽ thấy mọi exception xảy ra trong hàm”.

### 2.3. Nếu before advice ném ngoại lệ thì sao?

Ví dụ before advice kiểm tra hoặc ghi log rồi ném lỗi **trước khi target bắt đầu**. Caller có thể thấy lời gọi thất bại dù target không được chạy. Tuy nhiên, after-throwing advice gắn chính xác vào **target execution** và advice bao ngoài cùng chuỗi có thể nhìn thấy các điểm lỗi khác nhau. Thứ tự và vùng bao phủ quyết định advice nào chạy khi chính một advice khác lỗi.

Không nên tuyên bố “mọi advice after-throwing chắc chắn bắt mọi lỗi trong chain”. Hãy vẽ các lớp advice và kiểm thử trên engine thật.

## 3. Những loại lỗi và trạng thái cần phân biệt

### 3.1. Lỗi từ target

Đây là lỗi sinh ra trong phần nghiệp vụ hoặc do hàm mà target gọi, rồi **không được xử lý trước khi thoát khỏi join point**.

Ví dụ:

```java
void dispatch(String id) {
    if (id == null) {
        throw new IllegalArgumentException("missing id");
    }
    // xử lý
}
```

Advice quan sát có thể ghi `IllegalArgumentException`, nhưng không nên thay quyết định xử lý nghiệp vụ của caller. Nếu phải chuyển đổi loại lỗi, cần hợp đồng được công bố về kiểu và thông tin cause.

### 3.2. Lỗi từ chính advice

Lời gọi `metrics.recordFailure(ex)` có thể ném exception nếu backend đo lường gặp sự cố. Nếu advice ném lỗi mới khi target đã ném lỗi cũ, caller có nguy cơ chỉ thấy **lỗi của hệ thống đo lường**, còn lỗi gốc bị che.

Do đó phải có chính sách rõ:

- **Best-effort observability:** lỗi ghi log/metric thường không được thay đổi kết quả nghiệp vụ; có thể bắt và báo qua kênh dự phòng được kiểm soát.
- **Chính sách bắt buộc:** một sự kiện audit phải được lưu bền vững có thể yêu cầu thất bại nếu ghi không thành công; đây là quyết định có ảnh hưởng đến hợp đồng, transaction và bảo đảm dữ liệu.
- **Không nuốt lỗi gốc:** advice không được lặng lẽ trả về thành công trừ khi chức năng recovery được thiết kế và kiểm thử có chủ đích.

### 3.3. Lỗi từ cơ chế can thiệp

Lỗi khi tạo proxy, tìm method, resolve metadata, weave bytecode, load class hoặc xác định pointcut không nhất thiết là lỗi target. Việc gán tất cả exception cho cùng nhóm “thao tác nghiệp vụ thất bại” có thể làm sai metric và chẩn đoán.

Ví dụ với Java reflection, `Method.invoke` dùng `InvocationTargetException` để bao ngoại lệ do target method ném. Nếu lời gọi reflection thất bại **trước khi vào target**, loại lỗi có thể khác. Advice cần biết nguồn lỗi nào đang quan sát để tránh gỡ cause sai hoặc báo cáo sai.

### 3.4. Lỗi bất đồng bộ

Một API có thể trả về `CompletableFuture`/promise ngay mà không ném exception, sau đó future hoàn thành thất bại. **Return của method** và **completion của công việc** là hai mốc khác nhau:

```text
method submit() trả CompletableFuture   -> return bình thường
                                        -> tác vụ chạy sau
                                        -> future hoàn tất exceptionally
```

Một after-throwing advice đặt tại **execution của `submit()`** không tự quan sát failure đến sau trong future. Muốn ghi thất bại end-to-end cần hook/callback tại sự kiện completion, với xử lý cancellation và các dạng wrapping exception theo abstraction bất đồng bộ đang dùng.

## 4. Ngữ nghĩa after-throwing: chọn theo kết cục và loại lỗi

### 4.1. Phân biệt “throw xảy ra” và “throw thoát ra”

Một `throw` có thể được xử lý ngay trong target:

```java
int parseOrDefault(String value) {
    try {
        return Integer.parseInt(value);
    } catch (NumberFormatException ex) {
        return 0;
    }
}
```

`parseOrDefault("xyz")` vẫn **trả về 0 bình thường**. Advice after-throwing trên execution của `parseOrDefault` không nên ghi “method này ném NumberFormatException ra ngoài”. Nếu muốn thống kê số lần fallback, hãy thêm tín hiệu tường minh ở logic xử lý hoặc quan sát join point phù hợp khác nếu công cụ hỗ trợ.

Trong những mô hình có *exception handler join point*, điểm bắt lỗi là một loại điểm khác; nó không đồng nghĩa với after-throwing trên toàn bộ execution.

### 4.2. Lọc exception theo kiểu

Nhiều hệ thống AOP hỗ trợ điều kiện để advice chỉ phản ứng với một loại ngoại lệ hoặc nhóm kế thừa:

```text
join point: execution of operation
when throwing: IOException
advice: recordTechnicalFailure(...)
```

Đây là **giả mã**, không phải cú pháp chung. Cần xác minh cơ chế lọc có dùng quan hệ subtype hay chỉ exact type, và có hỗ trợ binding đối tượng exception hay không.

Nếu một method ném `IllegalArgumentException` nhưng pointcut/advice chỉ nhận `IOException`, advice đó có thể **không chạy**, dù lời gọi vẫn thất bại. Từ việc không có log after-throwing **không thể suy ra method thành công**.

### 4.3. Matching thuộc điểm nào: call, execution hay proxy invocation?

- **Method execution:** Theo dõi exception thoát khỏi lần thực thi body theo mô hình hỗ trợ.
- **Method call:** Theo dõi exception mà một điểm gọi cụ thể quan sát, nếu công cụ có call join point.
- **Proxy invocation:** Theo dõi exception đi qua wrapper/proxy handler, không tự bao gồm lời gọi bypass proxy.
- **Constructor / field / handler join point:** Chỉ có thể dùng nếu công cụ cung cấp đúng loại điểm đó.

Cùng một exception có thể đi qua nhiều điểm được chọn. Nếu advice ghi metric tại cả call và execution, một lỗi nghiệp vụ có thể tạo **nhiều bản ghi**. Cần quyết định xem metric đếm **exception crossing a boundary**, **invocation failure** hay **logical operation failure**.

## 5. Ngữ cảnh lỗi gồm những gì?

Một bản ghi lỗi tốt phục vụ chẩn đoán, nhưng không làm lộ dữ liệu và không vô tình sửa hành vi. Cần phân loại theo nguồn.

### 5.1. Ngữ cảnh của join point

Tùy khả năng công cụ, advice có thể có:

- **Kind:** method call, method execution hoặc sự kiện khác.
- **Signature:** tên phương thức, loại khai báo, kiểu tham số/return.
- **Target/this:** tham chiếu đối tượng đích hoặc đối tượng nhận lời gọi; hai khái niệm có thể khác ở call point hoặc proxy.
- **Arguments:** các tham số đã bind ở thời điểm join point xảy ra.
- **Annotation/metadata:** marker, mức giám sát hoặc chính sách được đặt tại declaration.
- **Location:** source/bytecode location nếu engine có thông tin vị trí.
- **Timing:** mốc bắt đầu và kết thúc, số lần thử, attempt ID.

**Không phải mọi engine đưa tất cả trường này cho advice.** Đừng đọc tên method từ stack trace rồi giả định nó tương đương metadata chính thức của join point. Stack trace có thể thay đổi theo inlining, reflection, mã sinh và trạng thái debug symbols.

### 5.2. Ngữ cảnh của exception

Trong Java, các thông tin hay dùng gồm:

| Trường | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `ex.getClass().getName()` | Tên loại exception. | Thường phù hợp làm nhóm lỗi có cardinality thấp hơn message tự do. |
| `ex.getMessage()` | Nội dung lỗi do mã tạo ra. | Có thể chứa dữ liệu riêng tư, input, token hoặc đường dẫn. Cần lọc/sanitize trước khi ghi. |
| `ex.getCause()` | Ngoại lệ nguồn được liên kết với lỗi hiện tại. | Có thể có chuỗi cause; cần tránh lặp vô hạn khi tự duyệt cấu trúc tùy biến. |
| `ex.getSuppressed()` | Các lỗi phụ được ghi nhận bên cạnh lỗi chính. | Quan trọng trong cleanup/try-with-resources; không thay thế exception gốc. |
| `ex.getStackTrace()` | Những frame thể hiện đường đi dẫn đến Throwable theo runtime. | Có chi phí và dữ liệu nhạy cảm; log chọn lọc, không mặc định in toàn bộ mọi lượt. |

Một Throwable có thể được bọc nhiều lớp. Đừng chỉ nhìn `getMessage()` của lớp ngoài rồi kết luận nguyên nhân gốc; cũng đừng tự ý gỡ mọi lớp wrapping, vì lớp wrapper có thể là một phần của **hợp đồng API**.

### 5.3. Ngữ cảnh nghiệp vụ và tracing

Một sự kiện lỗi hữu ích thường cần:

- **Operation name:** tên ổn định cho thao tác đang quan sát.
- **Correlation/trace ID:** liên kết các log của cùng request hoặc tác vụ.
- **Attempt ID:** phân biệt mỗi lần thử trong retry với một logical operation.
- **Result category:** validation, transient I/O, timeout, cancellation hoặc lỗi không phân loại.
- **Thời gian / môi trường:** mốc timestamp, service/module/version ở mức cần thiết.
- **Outcome:** success/failure/cancelled, **được định nghĩa thống nhất**.

Không nên lưu nguyên body request, mật khẩu, khóa API, thẻ thanh toán, dữ liệu y tế hoặc thông tin nhận dạng không cần thiết. Có thể dùng danh mục allowlist cho metadata được phép ghi. Nếu phải ghi message từ exception, cần đánh giá khả năng message chứa input người dùng.

### 5.4. Ngữ cảnh trên thread không tự theo tác vụ async

Một `ThreadLocal` correlation ID có thể hoạt động trong cùng thread, nhưng không tự bảo đảm truyền sang executor, callback hoặc coroutine. Advice lỗi ở thread khác có thể ghi mất trace ID hoặc giữ nhầm context nếu lifecycle không được quản lý. Với hệ thống bất đồng bộ, hãy thiết kế cơ chế truyền và dọn context theo abstraction của hệ thống, kiểm tra cả đường success, failure và cancellation.

## 6. Bảo toàn lỗi: nguyên tắc quan trọng nhất với advice quan sát

### 6.1. Mặc định nên truyền tiếp exception gốc

Trong một advice chỉ nhằm quan sát, hành vi mong muốn thường là:

```text
try:
    return proceed()
catch error:
    recordErrorBestEffort(error)
    throw same error
```

Giả mã trên chỉ diễn đạt ý tưởng. `proceed()`, bind exception, thứ tự advice và cách truyền tiếp tùy công cụ.

Nếu aspect biến `IOException` thành `RuntimeException` mà không có hợp đồng rõ, caller có thể mất khả năng xử lý lỗi đã dự kiến. Nếu aspect nuốt lỗi rồi trả một giá trị mặc định, metric “thành công” có thể tăng trong khi thao tác thực tế đã thất bại. Nếu một method được khai báo checked exception, việc chuyển đổi cần tuân thủ hợp đồng compile/runtime của Java.

### 6.2. Đừng để logging che exception gốc

Đây là ví dụ *chỉ minh họa ý tưởng*, không phải chương trình độc lập:

```java
try {
    return proceed();
} catch (Throwable original) {
    try {
        recordError(original);
    } catch (RuntimeException telemetryFailure) {
        // Chính sách minh họa: bỏ qua lỗi telemetry để giữ lỗi gốc.
    }
    throw original;
}
```

Khi hiện thực thật, cần chú ý loại Throwable có thể được ném theo hợp đồng của around advice và cơ chế build. Đoạn này giả định `proceed` và phương thức bao quanh cho phép ném `Throwable`.

Không mặc định bắt mọi `Throwable` của mã ứng dụng rồi tiếp tục chạy như thường. `Error` trên Java có thể chỉ ra sự cố nghiêm trọng, như cạn bộ nhớ; các chính sách telemetry nên tránh cấp phát hoặc thao tác phức tạp trong những tình huống đó. Việc bắt để **quan sát rồi ném lại ngay** khác với việc **nuốt và phục hồi**.

### 6.3. Đừng để `finally` thay kết cục ngoài ý định

```java
try {
    return compute();
} finally {
    cleanup();
}
```

Nếu `compute()` ném lỗi và `cleanup()` cũng ném lỗi, lỗi cleanup có thể trở thành lỗi được caller quan sát, che đi lỗi compute. Advice sau cùng cũng có rủi ro tương tự. Đối với thao tác cleanup đặc biệt quan trọng, cần thiết kế cách **ưu tiên lỗi gốc**, đính kèm lỗi phụ, hoặc bảo đảm cleanup không ném ngoại lệ ngoài hợp đồng.

Trong Java, **try-with-resources** có quy tắc *suppressed exceptions* để giữ lỗi chính từ thân `try` khi đóng tài nguyên cũng lỗi. Nếu tự viết around advice tương tự, cần chú ý `Throwable.addSuppressed` và các điều kiện biên; không tùy tiện thay ngữ nghĩa thư viện hoặc tự nuốt mọi lỗi cleanup.

## 7. Thực hành Java 17: quan sát after-throwing và context qua dynamic proxy

Ví dụ sau dùng **Java JDK dynamic proxy** để mô phỏng một cơ chế AOP dựa trên interface. Annotation `@Observed` được đặt trên method của interface. Handler chọn những lời gọi qua proxy có marker, in hành vi trước, sau khi trả về, sau khi ném lỗi và khi cleanup.

**Giới hạn:** Đây không phải bộ máy AOP toàn diện. Handler chỉ chặn lời gọi **đi qua proxy** và dùng `Method` của interface để đọc annotation. Nó không tự can thiệp field access, constructor, lời gọi trực tiếp đến target hoặc self-invocation.

Tạo file **`ErrorAdviceDemo.java`**:

```java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ErrorAdviceDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Observed { }

    interface Sender {
        @Observed
        String send(String id) throws IOException;
        String health();
    }

    static final class RealSender implements Sender {
        @Override
        public String send(String id) throws IOException {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            if ("NETWORK".equals(id)) {
                throw new IOException("remote unavailable");
            }
            System.out.println("TARGET send " + id);
            return "SENT " + id;
        }

        @Override
        public String health() {
            System.out.println("TARGET health");
            return "UP";
        }
    }

    static Sender observed(Sender target) {
        return (Sender) Proxy.newProxyInstance(
                Sender.class.getClassLoader(),
                new Class<?>[] { Sender.class },
                (proxy, method, args) -> {
                    boolean selected = method.isAnnotationPresent(Observed.class);
                    if (selected) {
                        System.out.println("ADVICE before " + method.getName());
                    }

                    try {
                        Object result = method.invoke(target, args);
                        if (selected) {
                            System.out.println("ADVICE returning " + method.getName());
                        }
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        if (selected) {
                            System.out.println("ADVICE throwing "
                                    + original.getClass().getSimpleName()
                                    + ": " + original.getMessage());
                        }
                        throw original;
                    } finally {
                        if (selected) {
                            System.out.println("ADVICE finally " + method.getName());
                        }
                    }
                }
        );
    }

    public static void main(String[] args) throws IOException {
        Sender target = new RealSender();
        Sender proxy = observed(target);

        System.out.println("RESULT " + proxy.send("OK"));
        System.out.println("RESULT " + proxy.health());

        try {
            proxy.send("NETWORK");
        } catch (IOException ex) {
            System.out.println("CALLER IOException: " + ex.getMessage());
        }

        try {
            proxy.send("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER IllegalArgumentException: "
                    + ex.getMessage());
        }

        System.out.println("RESULT " + target.send("DIRECT"));
    }
}
```

Biên dịch và chạy:

```bash
javac ErrorAdviceDemo.java
java ErrorAdviceDemo
```

Kết quả **đúng thứ tự**:

```text
ADVICE before send
TARGET send OK
ADVICE returning send
ADVICE finally send
RESULT SENT OK
TARGET health
RESULT UP
ADVICE before send
ADVICE throwing IOException: remote unavailable
ADVICE finally send
CALLER IOException: remote unavailable
ADVICE before send
ADVICE throwing IllegalArgumentException: id required
ADVICE finally send
CALLER IllegalArgumentException: id required
TARGET send DIRECT
RESULT SENT DIRECT
```

### 7.1. Phân tích theo ba đường

**Đường trả về thành công:** `proxy.send("OK")` chạy before → target → returning → finally. `IOException` và `IllegalArgumentException` không có ở đường này nên không có `ADVICE throwing`.

**Đường checked exception:** `proxy.send("NETWORK")` đi vào target, target ném `IOException`. Reflection tạo `InvocationTargetException` làm wrapper. Handler lấy `wrapped.getCause()`, ghi loại và message, rồi **ném đúng exception gốc**. Vì `Sender.send` khai báo `throws IOException`, proxy có thể truyền checked exception này đến caller đúng hợp đồng. `finally` vẫn chạy.

**Đường runtime exception:** `proxy.send("")` ném `IllegalArgumentException`. Handler xử lý tương tự, caller thấy đúng loại runtime exception. Không có dòng `TARGET send ...` vì lỗi validation xảy ra trước lúc ghi dòng đó.

**Đường không được chọn:** `proxy.health()` đi qua handler nhưng `Observed` không có trên method `health`, nên không in dòng ADVICE. `target.send("DIRECT")` gọi trực tiếp target, không qua proxy nên cũng không in ADVICE dù method interface được đánh dấu.

### 7.2. Tại sao không catch tất cả exception rồi gọi là “lỗi target”?

Handler chỉ catch `InvocationTargetException` để nhận diện lỗi **phát sinh từ phần được `Method.invoke` gọi**. Nếu `method.invoke` thất bại do điều kiện reflection/infrastructure khác, catch block trên không gắn nhãn nhầm lỗi đó là lỗi nghiệp vụ. `finally` vẫn chạy cho các ngoại lệ được ném bên trong `try`; vì vậy demo dùng nó để minh họa cleanup. Trong hệ thống thật, cần phân loại lỗi infrastructure/advice riêng để không đo sai tỷ lệ lỗi target.

Ví dụ cũng **không** xử lý sự cố khi chính lệnh `System.out.println` bên trong advice thất bại. Nếu cần cam kết “telemetry không ảnh hưởng chức năng”, code thực tế phải đặt kênh ghi an toàn và chính sách lỗi phù hợp thay vì coi `println` là luôn thành công.

### 7.3. Checked exceptions và dynamic proxy

Java dynamic proxy có quy tắc quan trọng: một checked exception thoát khỏi `InvocationHandler` mà **không được khai báo** bởi method interface thích hợp có thể bị bọc trong `java.lang.reflect.UndeclaredThrowableException`. Vì vậy không được giả định mọi `Throwable` do handler ném đều đến caller cùng lớp ngoại lệ gốc.

Trong demo, `IOException` **được khai báo** bởi `send(String)`, còn `IllegalArgumentException` là unchecked exception, nên cách truyền lỗi là hợp lệ. Nếu thay `throws IOException` bằng một interface không khai báo checked exception tương ứng, cần kiểm thử kiểu caller thực sự nhận.

### 7.4. Lưu ý về tên class, runtime và annotation

- Tên tệp phải là `ErrorAdviceDemo.java` vì class public tương ứng là `ErrorAdviceDemo`.
- Annotation `@Observed` có `RetentionPolicy.RUNTIME` để reflection tra cứu được.
- Annotation đặt ở **interface method** và handler đọc `Method` nhận từ proxy theo interface. Nếu chỉ chuyển marker sang implementation, phép `method.isAnnotationPresent(Observed.class)` trong ví dụ **không tự tra cứu declaration khác**.
- Code sử dụng tính năng Java phổ biến, tương thích JDK 17 trở lên, không cần thư viện AOP ngoài JDK.

### 7.5. Bài thực hành mở rộng

Hãy thử lần lượt, mỗi lần dự đoán stdout trước khi chạy:

1. Bỏ `@Observed` khỏi interface method `send`: handler vẫn gọi target, nhưng không in dòng ADVICE.
2. Gọi `target.send("NETWORK")` trong `try/catch`: caller nhận `IOException` nhưng không có advice vì bỏ qua proxy.
3. Đổi điều kiện target để một nhánh **catch IOException nội bộ và trả fallback**: after-throwing của proxy không chạy ở nhánh fallback; after-returning có thể chạy.
4. Viết một handler khác ghi lỗi sau khi catch rồi trả giá trị giả: đánh giá vì sao đó là **thay đổi hợp đồng**, không còn quan sát thuần.
5. Thêm một advice/wrapper ngoài proxy: thử nghiệm thứ tự log khi lỗi target phát sinh và khi một tầng advice tự ném lỗi.

## 8. Around advice và quy tắc “proceed”

Một số mô hình AOP có **around advice**, cho phép bao quanh phần thực thi qua thao tác thường gọi `proceed`. Giả mã:

```text
around selected join point:
    context = startContext()
    try:
        result = proceed()
        context.markSuccess()
        return result
    catch error:
        context.markFailure(error)
        throw same error
    finally:
        context.close()
```

**Điểm cần nhớ:**

- `proceed` có thể tiếp tục vào advice bên trong rồi mới tới target; không nhất thiết gọi thẳng target.
- Việc gọi `proceed` 0 lần, 1 lần hay nhiều lần tùy năng lực engine và ý định thiết kế; có thể khiến target không chạy hoặc chạy lặp.
- `catch` trong around có thể quan sát lỗi thoát từ **các tầng nằm bên trong**, gồm cả target và advice khác, không chỉ exception được ném ở source của target.
- Advice có thể chuyển exception thành kết quả hoặc chuyển kiểu, nhưng đây là thay đổi ngữ nghĩa phải có hợp đồng và ca kiểm thử.
- `finally` là nơi phù hợp để đóng context nếu việc cleanup không làm hỏng exception gốc.

### 8.1. Đếm lỗi và retry

Nếu một around advice gọi `proceed` nhiều lần để retry, after-throwing ở bên trong có thể ghi **mỗi attempt lỗi**, trong khi advice ngoài cùng chỉ thấy lần cuối thành công. Hai bộ đếm có nghĩa khác nhau:

- **Attempt failure count:** số lần thử thất bại.
- **Logical operation failure count:** số thao tác cuối cùng thất bại sau mọi lần thử.

Hãy chọn metric cần đo và vị trí đặt advice theo ý nghĩa ấy. Đối với tác vụ có side effect (gửi tiền, tạo hóa đơn, phát sự kiện), tự động retry từ aspect có thể thực hiện thao tác nhiều lần và gây sai dữ liệu nếu thiếu idempotency, backoff, timeout và điều kiện retry hợp lệ.

## 9. Nhiều advice: ai nhìn thấy lỗi nào?

Giả sử có hai advice around A và B bao quanh một target:

```text
A.before
  B.before
    target()
  B.after / B.catch
A.after / A.catch
```

Khi target ném lỗi:

1. B ở tầng trong có thể ghi nhận lỗi trước.
2. Nếu B **ném tiếp lỗi**, A có thể ghi nhận cùng lỗi.
3. Nếu B **bắt rồi trả fallback**, A có thể thấy kết thúc bình thường.
4. Nếu B **thay lỗi gốc bằng lỗi mới**, A sẽ thấy loại lỗi do B ném ra.
5. Nếu A ghi lỗi sau B, cùng một logical failure có thể tạo **hai bản ghi** ở các tầng quan sát.

Thứ tự A/B không được suy từ thứ tự xuất hiện của file source; nó do cơ chế AOP và cấu hình precedence quyết định. Khi có nhiều aspect, nên định nghĩa rõ:

- Advice nào chịu trách nhiệm logging, tracing, transaction hoặc retry?
- Có bao nhiêu bản ghi cho **một attempt** hoặc **một logical operation**?
- Lớp nào có quyền biến đổi exception?
- Advice nằm trong hay ngoài transaction boundary và điểm commit?
- Nếu advice ném lỗi, những advice phía ngoài có quan sát được không?

### 9.1. Ví dụ ngữ nghĩa transaction

Một method có thể **trả về bình thường** nhưng giao dịch chưa commit. Nếu advice “success” nằm ở bên trong transaction boundary, log success có thể xuất hiện **trước** khi commit thất bại ở tầng ngoài. Để ghi nhận thành công bền vững, phải quan sát đúng mốc commit/outbox hoặc cơ chế giao dịch được công bố; after-returning của một method không tự chứng minh dữ liệu đã được lưu bền vững.

Điểm này là một ví dụ điển hình tại sao **join point và thứ tự advice** quyết định ngữ nghĩa quan sát lỗi.

## 10. Ngữ cảnh lỗi trong logging, tracing và audit

### 10.1. Một cấu trúc bản ghi gợi ý

Một sự kiện lỗi có thể chứa trường:

```text
event = "operation_failed"
operation = "payment-authorize"
outcome = "failure"
error.type = "IOException"
error.category = "dependency"
trace_id = "<id được truyền trong context>"
attempt = 2
duration_ms = <số đo đã tính>
```

Đây là **mẫu dữ liệu minh họa**, không phải chuẩn bắt buộc hoặc output của chương trình Java ở trên. Ở môi trường thực tế, `trace_id` phải đến từ context hợp lệ; không tự phát sinh một ID mới riêng cho mỗi tầng advice rồi phá mất khả năng tương quan.

Không nên dùng toàn bộ `error.message` làm nhãn metric vì thường làm cardinality tăng rất cao và có thể chứa dữ liệu người dùng. Với metric, ưu tiên loại lỗi/nhóm thao tác có số giá trị được kiểm soát; với log chi tiết, áp quy tắc redaction và retention.

### 10.2. Phân biệt audit và log lỗi

**Log lỗi** thường phục vụ chẩn đoán và có thể là best-effort. **Audit** có thể là bằng chứng bắt buộc cho một hành động nhạy cảm, cần kiểm soát độ bền, thứ tự, chống sửa và quan hệ với transaction.

Nếu policy yêu cầu audit phải được ghi thành công trước khi thao tác được coi là hoàn tất, một aspect chỉ gọi logger không tự tạo bảo đảm đó. Cần thiết kế hợp đồng lưu trữ/transaction phù hợp. Advice có thể là điểm kích hoạt, nhưng không thay thế thiết kế tính nhất quán dữ liệu.

### 10.3. Không ghi dữ liệu nhạy cảm từ exception

Ngoại lệ có thể chứa SQL text, đường dẫn nội bộ, token, thông tin người dùng và dữ liệu request. Không tự động serialize toàn bộ arguments, target hoặc stack trace ở mọi lỗi. Hãy dùng allowlist trường an toàn và bộ lọc/redaction; kiểm soát ai được truy cập log và thời gian lưu.

### 10.4. Phân loại và mức độ cảnh báo

Không phải ngoại lệ nào cũng là sự cố vận hành cần báo động. `IllegalArgumentException` do input không hợp lệ có thể là vấn đề phía caller; `IOException` từ dependency có thể là lỗi hạ tầng; cancellation có thể là hành vi mong đợi. Phân loại dựa trên hợp đồng API và ngữ cảnh, không chỉ tên exception.

Nếu đo tỷ lệ lỗi, định nghĩa mẫu số: tổng invocation, tổng request, tổng attempt hay tổng logical operation. Không trộn kết quả của các lớp advice khác nhau vào một chỉ số mà không có quy tắc chống trùng.

## 11. Bất đồng bộ: failure sau khi method trả về

Xét API trả `CompletionStage<String>`:

```java
CompletionStage<String> fetchAsync(String key)
```

Có ít nhất ba trường hợp:

1. **Ném lỗi đồng bộ trước khi return:** execution của `fetchAsync` kết thúc bằng throw; after-throwing tương ứng có thể chạy.
2. **Return một stage đã hoàn tất exceptionally:** lời gọi `fetchAsync` **trả về bình thường** một đối tượng stage; lỗi thuộc trạng thái completion của stage.
3. **Return stage chưa hoàn tất, sau đó lỗi:** cũng là normal method return, rồi future failure xảy ra muộn hơn.

Một advice muốn quan sát **lỗi cuối cùng của tác vụ** phải đăng ký hook vào completion bằng abstraction phù hợp, chẳng hạn `whenComplete` của `CompletionStage` trong Java; đồng thời tránh đổi kết quả/cancellation hoặc tạo side effect không mong muốn. Ví dụ khái niệm:

```java
CompletionStage<String> stage = fetchAsync(key);
stage.whenComplete((value, failure) -> {
    if (failure != null) {
        // ghi nhận kết quả bất đồng bộ; cân nhắc wrapping exception
    }
});
```

Đoạn trên là **mã minh họa không độc lập**, giả định `fetchAsync` và `key` đã tồn tại; không dùng như một chương trình chạy trực tiếp. `whenComplete` và các combinator có quy tắc về lỗi callback và stage phụ thuộc; cần xử lý riêng nếu mục tiêu là tuyệt đối không đổi semantics. Ngoài ra, biểu diễn lỗi từ `join()`, `get()` hoặc chain async có thể có wrapper; không tự gỡ/đổi exception tùy tiện.

## 12. Tính đúng đắn khi gắn advice theo pointcut

Một advice after-throwing tốt không chỉ có logic catch đúng; nó còn phải **được áp dụng đúng nơi**.

### 12.1. Kiểm thử điểm được chọn và điểm bị loại

- **Positive:** method được pointcut chọn ném exception ra ngoài; advice failure ghi nhận đúng một occurrence theo hợp đồng.
- **Negative thành công:** cùng method trả bình thường; không ghi failure.
- **Negative không khớp pointcut:** method khác ném lỗi; không được advice này xử lý.
- **Bị bắt nội bộ:** target bắt lỗi và trả fallback; after-throwing trên target execution không chạy.
- **Direct target:** khi dùng proxy, lời gọi bypass proxy không chạy handler.
- **Self-invocation:** proxy đơn giản có thể không chặn lời gọi method khác trên `this`; weaving có thể khác.
- **Lỗi trước target:** before advice hoặc cơ chế tạo proxy lỗi; cần xác định tầng after-throwing nào thấy.
- **Nhiều advice:** thứ tự, đếm trùng, thay exception và truyền tiếp được kiểm thử.
- **Checked exception:** caller nhận loại đúng hay `UndeclaredThrowableException` ở biên dynamic proxy.
- **Async:** phân biệt lỗi đồng bộ và stage hoàn thành exceptionally.
- **Telemetry failure:** lỗi logger/metrics có che mất lỗi gốc không?

### 12.2. Ma trận ca kiểm thử cụ thể

| Tình huống | Target execution kết thúc | Advice failure kỳ vọng | Caller kỳ vọng |
| --- | --- | --- | --- |
| Method được chọn trả `"OK"` | Bình thường | Không chạy. | Nhận `"OK"`. |
| Method được chọn ném `IOException` | Ném ra ngoài. | Chạy, nếu matcher cho phép kiểu này. | Nhận exception theo hợp đồng. |
| Method được chọn ném `IllegalArgumentException` | Ném ra ngoài. | Chạy nếu không chỉ lọc `IOException`. | Nhận runtime exception. |
| Target catch exception và return fallback | Bình thường. | Không chạy đối với execution đó. | Nhận fallback. |
| Method không thuộc pointcut ném lỗi | Ném ra ngoài. | Advice cụ thể này không chạy. | Vẫn nhận lỗi theo đường thường. |
| Proxy bị bypass | Target có thể ném. | Handler của proxy không chạy. | Nhận exception trực tiếp từ target. |
| Method trả stage rồi stage lỗi | Method return bình thường. | After-throwing đồng bộ không tự chạy. | Xử lý lỗi tại stage. |
| Advice logging tự ném | Có thể target đã lỗi. | Phụ thuộc vùng advice/cơ chế. | Cần chính sách để không che lỗi gốc ngoài chủ đích. |

## 13. Sai lầm thường gặp và cách sửa

**Sai lầm 1 — “Có `throw` trong source thì after-throwing chắc chắn chạy”.** Sai nếu exception bị bắt bên trong trước khi thoát khỏi join point. Hãy đặt đúng loại điểm và vẽ đường truyền lỗi.

**Sai lầm 2 — “After-finally và after-throwing như nhau”.** After/finally liên quan đến cả hai kết cục, còn after-throwing nhắm kết cục exception. Với cleanup cần tính cả success/failure.

**Sai lầm 3 — “Advice ghi lỗi thì nên nuốt exception để request không thất bại”.** Đây là thay đổi hợp đồng. Với logging/metrics quan sát, mặc định giữ lỗi gốc và để caller quyết định.

**Sai lầm 4 — “Dùng `ex.getMessage()` làm mã lỗi duy nhất”.** Message có thể đổi theo input, phiên bản và chứa bí mật. Dùng classification ổn định và metadata đã lọc.

**Sai lầm 5 — “Một lỗi chỉ tạo một bản ghi after-throwing”.** Nếu nhiều advice, nhiều join point hoặc nhiều lần thử cùng quan sát, số bản ghi có thể lớn hơn một. Phải định nghĩa phạm vi đếm và correlation.

**Sai lầm 6 — “Advice after-throwing bao mọi lỗi hệ thống”.** Sai nếu điểm không được chọn, đường gọi bypass proxy, lỗi phát sinh ngoài vùng hook hoặc loại exception không match.

**Sai lầm 7 — “`finally` luôn an toàn”.** Cleanup có thể ném lỗi và che lỗi gốc. Cần chính sách bảo toàn lỗi chính và xử lý lỗi phụ.

**Sai lầm 8 — “Method async trả future nghĩa là thành công”.** Nó chỉ có thể cho biết thao tác tạo/gửi task đã trả về; trạng thái cuối cần quan sát completion.

**Sai lầm 9 — “Exception do reflection bọc là loại lỗi nghiệp vụ mới”.** Với `Method.invoke`, `InvocationTargetException` là wrapper cho lỗi target; gỡ wrapper phải có hiểu biết về hợp đồng gọi và loại checked exception.

**Sai lầm 10 — “Hễ có annotation thì advice chạy”.** Annotation chỉ là metadata. Cần matcher, loại join point và cơ chế weaving/proxy thực sự đi qua lời gọi.

## 14. Tự kiểm tra kiến thức

**Câu 1.** `process()` bắt `IOException` từ `read()` rồi trả dữ liệu cache. After-throwing trên execution của `process` có chạy không?

**Đáp án:** Không đối với `IOException` đã được xử lý nội bộ, vì execution của `process` trả về bình thường. Một advice trên điểm khác, nếu được hỗ trợ, có thể quan sát lỗi của `read`.

**Câu 2.** Vì sao advice after-throwing nên được thiết kế để truyền lại đúng Throwable gốc?

**Đáp án:** Để giữ hợp đồng của target, khả năng xử lý của caller, chain cause và phân loại lỗi; chuyển/nuốt lỗi là thay đổi hành vi cần chủ đích.

**Câu 3.** Method interface khai báo `throws IOException`. JDK proxy handler nhận `InvocationTargetException` từ `Method.invoke`. Làm gì để caller nhận `IOException`?

**Đáp án:** Lấy `getCause()` là IOException và ném tiếp cause đó. Nếu tự ném checked exception không được method interface khai báo, proxy có thể bọc thành `UndeclaredThrowableException`.

**Câu 4.** Lỗi của chính logger xảy ra trong `finally` sau khi target ném lỗi. Rủi ro lớn nhất là gì?

**Đáp án:** Exception logger có thể che lỗi target, khiến caller và metric nhận sai nguyên nhân.

**Câu 5.** Khi target tự catch rồi retry ba lần trước khi return thành công, after-throwing gắn execution của toàn bộ target có ghi ba lỗi attempt không?

**Đáp án:** Không, nếu các lỗi attempt đều được bắt nội bộ và execution cuối cùng trả bình thường. Muốn đếm attempt phải đặt hook ở phạm vi phù hợp hoặc phát metric tường minh tại cơ chế retry.

**Câu 6.** Một `CompletableFuture` được return bình thường rồi hoàn thành exceptionally. Advice failure trên execution method có đủ để phát hiện không?

**Đáp án:** Không. Cần quan sát trạng thái completion của future; không đồng nhất return bình thường với tác vụ thành công.

**Câu 7.** Vì sao cần trace ID và attempt ID khác nhau khi quan sát lỗi?

**Đáp án:** Trace ID liên kết nhiều sự kiện của cùng request/luồng, còn attempt ID phân biệt các lượt thử khi retry. Một logical operation có thể gồm nhiều attempts.

**Câu 8.** Nếu hai around advice đều ghi exception nhưng advice trong chuyển lỗi thành kết quả fallback, advice ngoài sẽ nhìn thấy gì?

**Đáp án:** Tùy thứ tự/lớp bao; nếu tầng trong catch và return fallback, tầng ngoài thường quan sát kết thúc bình thường thay vì lỗi target đã bị xử lý.

## 15. Checklist trước khi áp dụng vào hệ thống thật

1. **Ranh giới:** Join point nào được chọn? Method call hay execution, proxy hay weaving?
2. **Kết cục:** Có phân biệt return, throw, cancellation và async completion không?
3. **Kiểu lỗi:** After-throwing quan sát Throwable nào? Có lọc theo exception class không?
4. **Ngữ cảnh:** Method/target/arguments/metadata/correlation ID được engine hỗ trợ ở đâu?
5. **Riêng tư:** Có loại bỏ bí mật, dữ liệu nhạy cảm và message chưa kiểm soát không?
6. **Bảo toàn hợp đồng:** Advice có đổi result, exception, cause hoặc timing một cách không mong muốn không?
7. **Lỗi của advice:** Logging/metrics/audit failure được xử lý theo policy rõ ràng chưa?
8. **Cleanup:** Có giữ lỗi gốc và giải phóng tài nguyên trên cả success/failure không?
9. **Thứ tự:** Nhiều advice, transaction, retry và audit có thứ tự đúng mục đích không?
10. **Kiểm thử:** Đủ ca success, target throw, target catch nội bộ, bypass, advice throw, async và checked exception chưa?

## Kết luận

**Advice khi có ngoại lệ** giúp tập trung chính sách quan sát và xử lý kỹ thuật cho các join point **kết thúc bằng lỗi thoát ra ngoài**. Nhưng muốn dùng đúng phải xác định rõ **loại join point**, **đường exception thực sự đi qua**, **ngữ cảnh có thể truy cập** và **hợp đồng cần bảo toàn**. After-throwing không đồng nghĩa “mọi lệnh throw trong source”, after/finally không đồng nghĩa chỉ lỗi, và kết quả method async không đồng nghĩa trạng thái cuối của công việc. Một thiết kế đáng tin là thiết kế biết rõ nơi advice chạy, nơi nó không chạy, giữ nguyên exception gốc khi chỉ quan sát, bảo vệ dữ liệu nhạy cảm và có bộ kiểm thử xác nhận cả success lẫn failure.
