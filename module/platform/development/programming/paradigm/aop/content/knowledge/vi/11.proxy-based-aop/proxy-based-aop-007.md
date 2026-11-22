# Chuỗi interceptor và cơ chế gọi tiếp trong AOP qua proxy

Khi dùng **proxy** để triển khai một phần hành vi lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), lời gọi của người dùng không đi thẳng đến đối tượng nghiệp vụ mà trước tiên đi qua một **đối tượng đại diện**. Đại diện có thể thực thi nhiều **interceptor** theo thứ tự để ghi nhận thời gian, kiểm tra quyền, giới hạn tần suất, chuyển đổi kết quả hoặc quản lý một số bối cảnh. Nhiều interceptor xếp nối nhau tạo thành **chuỗi interceptor (interceptor chain)**.

Cốt lõi của chuỗi không chỉ là gọi lần lượt các hàm. **Mỗi interceptor quyết định có chuyển tiếp lời gọi tới phần còn lại của chuỗi không, khi nào chuyển tiếp, chuyển tiếp mấy lần và làm gì với kết quả hoặc ngoại lệ.** Thao tác này thường được gọi là **`proceed()`**, **`next()`**, hoặc “invoke next” tùy công cụ. Khi điểm cuối của chuỗi đã tới, cơ chế sẽ chuyển lời gọi tới **phương thức đích**.

Để hiểu và áp dụng đúng, phải phân biệt:

- **Proxy:** nơi nhận cuộc gọi ở phía ngoài, điều phối tới interceptor hoặc target.
- **Interceptor:** một lớp chức năng có thể can thiệp quanh một lượt gọi.
- **Invocation context:** thông tin của lượt gọi, gồm phương thức, đối số, đích và trạng thái của chuỗi nếu cơ chế cung cấp.
- **Proceed/next:** bước tiếp tục tới interceptor kế tiếp hoặc đích, **không nhất thiết** là gọi thẳng phương thức nghiệp vụ.
- **Join point/pointcut:** mô hình và điều kiện chọn điểm cần can thiệp; proxy chỉ hỗ trợ một tập điểm nhất định.
- **Target:** đối tượng nghiệp vụ thực sự được gọi ở điểm cuối khi chuỗi cho phép tiếp tục.

Bài trình bày kiến thức AOP cơ bản và nâng cao **nói chung**. Không có chuẩn thống nhất cho mọi chữ ký interceptor, cách truyền đối số hoặc cho phép gọi `proceed` nhiều lần. Ví dụ dùng Java 17 và JDK dynamic proxy để tự xây một mô hình nhỏ, giúp quan sát chính xác nguyên lý mà không giả định đó là thuật toán của một framework cụ thể.

## 1. Kết quả học tập

Sau bài, bạn có thể:

1. Giải thích vì sao chuỗi interceptor là một **cấu trúc lồng nhau** chứ không chỉ là danh sách callback được chạy từ trên xuống.
2. Đọc đường đi **proxy → interceptor A → interceptor B → target**, rồi đường quay về **target → B → A → caller**.
3. Mô tả vai trò của **invocation context**: method, arguments, target, cursor và thao tác chuyển tiếp.
4. Phân biệt `proceed` một lần, không lần nào hoặc nhiều lần và tác động tới hành vi chính.
5. Phân tích việc interceptor bên ngoài/bên trong nhìn thấy kết quả và ngoại lệ ở **ranh giới riêng**.
6. Đánh giá thứ tự đặt authorization, caching, retry, transaction, timing và logging.
7. Nhận diện vấn đề **self-invocation**, gọi trực tiếp target, phương thức ngoài proxy, recursion, proxy lồng nhau và phương thức có overload.
8. Viết và chạy chương trình Java 17 có interceptor chain hoàn chỉnh, gồm nhánh thành công, retry, lỗi và bypass.
9. Kiểm thử sự bảo toàn của kết quả, ngoại lệ, số lần gọi và phạm vi can thiệp.

## 2. Chuỗi interceptor là gì?

Một phép gọi có thể được mô hình hóa:

```text
Client
  |
  v
Proxy
  |
  +--> Interceptor A: before
         |
         +--> proceed()
                |
                +--> Interceptor B: before
                       |
                       +--> proceed()
                              |
                              +--> Target.method()
                              |
                       <------+-- result / error
                       |
                  Interceptor B: after / catch / finally
                |
         <------+-- result / error
         |
     Interceptor A: after / catch / finally
  |
  v
Client receives result / error
```

Thứ tự đi xuống là **A rồi B rồi target**. Khi phần bên trong trả về, thứ tự đi lên thường là **B rồi A**. Nếu đích ném ngoại lệ, các interceptor có thể quan sát nó trên đường đi ngược và thực hiện `catch`/`finally` theo cấu trúc của từng lớp.

Đây là lý do thường có thể nói:

```text
A(B(Target))
```

thay vì nghĩ `A; B; Target; A; B` như các hàm hoàn toàn tách rời. Một interceptor có thể không chuyển tiếp, hoặc có thể chuyển tiếp nhiều lần; khi đó cấu trúc dòng điều khiển thay đổi.

### 2.1. Interceptor khác advice ở đâu?

**Advice** là khái niệm AOP chỉ hành vi bổ sung ở join point. **Interceptor** thường là một cấu trúc lập trình/runtime để triển khai hành vi đó, nhất là với method interception. Chúng có thể tương ứng gần nhau nhưng **không phải hai từ đồng nghĩa tuyệt đối** trong mọi hệ:

- Một advice có thể được weave trực tiếp vào bytecode, không dùng proxy.
- Một interceptor có thể nằm trong chain xử lý yêu cầu hay sự kiện mà không mang đầy đủ mô hình pointcut AOP.
- Một interceptor kiểu around có thể tổ chức before, after-returning, after-throwing và finally trong cùng một cấu trúc.
- Một hệ AOP có thể có nhiều loại join point hơn method call qua proxy, tùy công nghệ.

Trong phạm vi bài này, interceptor chain được xem là **một cách hiện thực AOP qua proxy**.

### 2.2. Không phải mọi lời gọi đều đi qua chuỗi

Một đối tượng `Service` có thể được giữ đồng thời dưới hai tham chiếu:

```text
original  -> Service
proxied   -> Proxy -> Interceptors -> Service
```

Nếu client gọi `original.execute()`, chuỗi proxy không được kích hoạt. Nếu gọi `proxied.execute()`, lời gọi đi qua chuỗi tương ứng, với điều kiện phương thức được cơ chế hỗ trợ và bộ lọc cho phép.

Một **pointcut có vẻ đúng** chưa đủ bảo đảm advice chạy. Cần kiểm tra nơi cung cấp tham chiếu đối tượng, loại phương thức và đường thực thi cụ thể.

## 3. Thành phần của một invocation context

Một đối tượng ngữ cảnh lời gọi có thể mang các trường sau, tùy thiết kế:

| Dữ liệu | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| **Method/signature** | Phương thức đang được chặn, danh sách kiểu tham số | Khác kiểu runtime của đối số |
| **Arguments** | Giá trị truyền vào lần gọi | Có thể chứa null hoặc wrapper do boxing |
| **Target** | Đối tượng nghiệp vụ nhận thao tác | Không nhất thiết trùng với proxy |
| **Proxy/this context** | Đại diện hoặc ngữ cảnh bên ngoài | Ngữ nghĩa `this`/`target` phụ thuộc mô hình |
| **Interceptor list** | Những bộ chặn được áp theo thứ tự | Thứ tự quyết định khả năng quan sát |
| **Current position** | Vị trí tiếp tục trong chuỗi | Tránh quay về interceptor đang chạy ngoài ý định |
| **Proceed/next** | Tiếp tục tới phần còn lại của chuỗi | Có thể gọi target khi không còn interceptor |
| **Invocation metadata** | Tên thao tác, kiểu đích, dữ liệu phụ trợ | Không tự chứng minh dữ liệu tin cậy |
| **Context attributes** | Trạng thái theo một lượt gọi nếu có hỗ trợ | Cần an toàn khi lồng nhau/đồng thời |

Không nhất thiết phải có tất cả các trường ở một API. Một số cơ chế ẩn cursor trong closure, một số cung cấp đối tượng `MethodInvocation`, số khác dùng hàm `next` nhận đối số.

### 3.1. Chữ ký phương thức và đối số runtime khác nhau

Ví dụ một interface có:

```java
void send(Object value);
void send(String value);
```

Lời gọi `send((Object) "A")` chọn overload khai báo `send(Object)` dù đối số thực tế là `String`. Một interceptor lọc theo `args[0] instanceof String` có thể nhận kết quả khác với bộ lọc chọn chữ ký `send(String)`.

Khi interception nhằm chính sách khác nhau cho từng overload, phải kiểm tra **kiểu tham số khai báo, số lượng và thứ tự**; không suy từ giá trị runtime.

### 3.2. Primitive, boxing và null

Trong JDK dynamic proxy, một phương thức nhận `int count` vẫn có chữ ký `int.class`, nhưng khi truyền qua `Object[] args`, giá trị primitive được biểu diễn bằng `Integer`. Không nên cast một `Long` sang `Integer` chỉ vì đều là số.

Nếu phương thức không tham số, `args` có thể là `null` theo hợp đồng của `InvocationHandler`. Nếu có một tham số tham chiếu mang null, `args` có thể là mảng một phần tử `[null]`. Đây là hai trường hợp khác nhau.

Một interceptor chỉ quan sát không nên unbox `Integer null` thành `int`, vì điều đó gây `NullPointerException` do interceptor tạo ra.

## 4. Cơ chế `proceed()`: đi tiếp một tầng

Xét chuỗi có ba interceptor A, B, C:

```text
A -> B -> C -> Target
```

Tại A, khi gọi `proceed()`, hành động đúng về mặt khái niệm là **gọi phần còn lại từ B**. Tại B, gọi tiếp từ C. Tại C, gọi tiếp vào Target.

Giả mã mô hình:

```text
invoke(position, invocation):
    if position == interceptorCount:
        return targetCall(invocation.arguments)
    interceptor = interceptors[position]
    return interceptor.around(
        invocation.withNext(() -> invoke(position + 1, invocation))
    )
```

Đây là **giả mã**, không phải API Java/AOP thống nhất. Điểm cốt lõi là callback “next” **đã biết vị trí kế tiếp** để không tự đi vòng về chính interceptor hiện tại.

### 4.1. Trả về phải đi ngược toàn chuỗi

Nếu target trả `"OK"`, B có thể ghi log rồi trả lại `"OK"`; A nhận kết quả của **B(Target)**, không phải nhất thiết đọc trực tiếp giá trị từ target.

Nếu B sửa kết quả thành `"CACHED"`, A sẽ nhận `"CACHED"`. Vì vậy interceptor ở ngoài nhìn thấy **kết quả của chuỗi ở bên trong**, có thể khác kết quả gốc.

### 4.2. Ngoại lệ cũng truyền theo chiều ngược

Nếu target ném `IllegalArgumentException`, C, B và A có thể bắt hoặc truyền nó. Nhưng nếu B bắt lỗi rồi trả fallback, A có thể quan sát **đường thành công**. Nếu B tự ném lỗi từ logging, A có thể thấy lỗi ấy thay vì lỗi của target.

Không thể kết luận mọi interceptor “sẽ thấy ngoại lệ từ target” khi có interceptor bên trong chuyển đổi đường điều khiển.

### 4.3. Thứ tự `finally`

Một interceptor dạng:

```java
Object around(Invocation invocation) throws Throwable {
    acquireContext();
    try {
        return invocation.proceed();
    } finally {
        releaseContext();
    }
}
```

Đây là **đoạn minh họa**, trong đó `Invocation`, `acquireContext`, `releaseContext` thuộc mô hình giả định. Cleanup chạy khi phạm vi `try` kết thúc bình thường hoặc do ngoại lệ. Nếu `acquireContext()` ném lỗi **trước khi vào `try`**, khối finally đó chưa bảo vệ được đường lỗi ấy. Cần xác định tài nguyên nào đã chiếm giữ và phải trả.

## 5. Không gọi tiếp, gọi một lần hoặc nhiều lần

Một interceptor kiểu around có thể lựa chọn:

| Số lần chuyển tiếp | Hành vi thường gặp | Rủi ro hoặc yêu cầu |
| --- | --- | --- |
| **0** | Từ chối quyền, cache hit, trả fallback | Target không chạy; phải được phép theo hợp đồng |
| **1** | Logging, timing, tracing thông thường | Chuyển tiếp kết quả/ngoại lệ đúng |
| **Nhiều lần** | Retry có điều kiện, thử nhiều chiến lược | Có thể nhân đôi tác dụng phụ và advice bên trong |

Nếu mục tiêu chỉ là ghi log kỹ thuật, **một lần `proceed`** thường là lựa chọn an toàn. Gọi tiếp nhiều lần không đơn thuần “thực thi log nhiều lần”: nó có thể **gọi lại toàn bộ nghiệp vụ**.

### 5.1. Điểm khó: cursor thay đổi hay continuation có thể tái sử dụng?

Có hai kiểu tổ chức chuỗi đáng phân biệt:

- **Cursor có trạng thái tăng dần:** cùng một đối tượng context giữ chỉ số đang tăng. Gọi `proceed` lần hai trên context đó có thể đi tới vị trí khác, bỏ qua interceptor hoặc bị từ chối; điều này phụ thuộc triển khai.
- **Continuation cố định tới phần đuôi:** mỗi interceptor nhận một context biểu diễn đúng “phần chuỗi còn lại”. Gọi `proceed` nhiều lần có thể chạy lại phần đuôi từ cùng vị trí, nếu API cho phép.

Không được coi một ví dụ tự cài `proceed` nhiều lần là chứng minh mọi công cụ AOP có cùng tính chất. Khi làm retry thật, phải kiểm tra **hợp đồng của API tiến hành** và những side effect liên quan.

### 5.2. Retry có thể lặp interceptor bên trong

```text
Audit(Retry(Metrics(Target)))
```

Nếu `Retry` thử hai lần và mỗi lần `proceed` đi lại qua phần đuôi:

- **Audit** bao ngoài thường được kích hoạt một lần cho logical request.
- **Metrics** nằm bên trong có thể chạy hai lần, mỗi lần đo một attempt.
- **Target** có thể được gọi hai lần.

Nếu đổi thành `Retry(Audit(Metrics(Target)))`, audit cũng có thể chạy theo từng attempt. Đây là ý nghĩa của **thứ tự lồng nhau**; không có thứ tự mặc định chung cho mọi công nghệ.

## 6. Ví dụ Java 17: xây interceptor chain hoàn chỉnh

Ví dụ dưới đây cài một **mô hình chuỗi interceptor trên JDK dynamic proxy**, gồm:

- Một proxy giao diện `WorkPort` và target `WorkService`;
- Một invocation context giữ method, arguments, danh sách interceptor, vị trí kế tiếp và terminal call;
- Hai bộ `Trace` ở ngoài và trong;
- Một bộ `Retry` ở giữa, cho phép thử lại khi nhận lỗi tạm thời được định nghĩa;
- Đường thành công, một trường hợp lỗi lần đầu rồi thành công, một lỗi không retry và lời gọi bypass.

**Đây là chương trình Java 17 độc lập, không dùng thư viện AOP ngoài JDK.** Nó dạy cấu trúc chuỗi và `proceed`, không phải bộ weaving có thể chặn mọi điểm thực thi.

Lưu toàn bộ vào `InterceptorChainDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class InterceptorChainDemo {
    interface WorkPort {
        String execute(String id);
        String inspect(String id);
    }

    static final class WorkService implements WorkPort {
        private final Map<String, Integer> attempts = new HashMap<>();

        @Override
        public String execute(String id) {
            int n = attempts.merge(id, 1, Integer::sum);

            if (id.equals("again") && n == 1) {
                throw new IllegalStateException("temporary");
            }
            if (id.equals("bad")) {
                throw new IllegalArgumentException("invalid");
            }
            return "OK:" + id + "#" + n;
        }

        @Override
        public String inspect(String id) {
            return "LOOKUP:" + id;
        }
    }

    @FunctionalInterface
    interface Terminal {
        Object call() throws Throwable;
    }

    @FunctionalInterface
    interface Interceptor {
        Object intercept(Invocation invocation) throws Throwable;
    }

    static final class Invocation {
        final Method method;
        final Object[] arguments;
        final List<Interceptor> chain;
        final int nextIndex;
        final Terminal terminal;

        Invocation(Method method, Object[] arguments,
                   List<Interceptor> chain, int nextIndex,
                   Terminal terminal) {
            this.method = method;
            this.arguments = arguments;
            this.chain = chain;
            this.nextIndex = nextIndex;
            this.terminal = terminal;
        }

        Object proceed() throws Throwable {
            if (nextIndex == chain.size()) {
                return terminal.call();
            }
            Interceptor next = chain.get(nextIndex);
            Invocation remainder = new Invocation(
                    method, arguments, chain, nextIndex + 1, terminal);
            return next.intercept(remainder);
        }
    }

    static final class Trace implements Interceptor {
        private final String label;

        Trace(String label) {
            this.label = label;
        }

        @Override
        public Object intercept(Invocation invocation) throws Throwable {
            System.out.println("[" + label + "] before execute");
            try {
                Object result = invocation.proceed();
                System.out.println("[" + label + "] return " + result);
                return result;
            } catch (Throwable error) {
                System.out.println("[" + label + "] throw "
                        + error.getClass().getSimpleName());
                throw error;
            } finally {
                System.out.println("[" + label + "] finally");
            }
        }
    }

    static final class Retry implements Interceptor {
        @Override
        public Object intercept(Invocation invocation) throws Throwable {
            for (int attempt = 1; attempt <= 2; attempt++) {
                System.out.println("[RETRY] attempt " + attempt);
                try {
                    return invocation.proceed();
                } catch (IllegalStateException error) {
                    if (attempt == 2) {
                        throw error;
                    }
                    System.out.println("[RETRY] retry");
                }
            }
            throw new AssertionError("unreachable");
        }
    }

    static Object callTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    static WorkPort wrap(WorkPort target, List<Interceptor> chain) {
        return (WorkPort) Proxy.newProxyInstance(
                WorkPort.class.getClassLoader(),
                new Class<?>[] { WorkPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("execute")) {
                        return callTarget(method, target, args);
                    }
                    Object[] values = args == null
                            ? new Object[0] : args.clone();
                    Terminal terminal = () ->
                            callTarget(method, target, values);
                    Invocation first = new Invocation(
                            method, values, chain, 0, terminal);
                    return first.proceed();
                });
    }

    public static void main(String[] args) {
        WorkService service = new WorkService();
        List<Interceptor> chain = List.of(
                new Trace("OUTER"), new Retry(), new Trace("INNER"));
        WorkPort proxy = wrap(service, chain);

        System.out.println("READY");
        System.out.println("RESULT " + proxy.execute("ok"));
        System.out.println("RESULT " + proxy.execute("again"));

        try {
            proxy.execute("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR " + error.getMessage());
        }

        System.out.println("LOOKUP " + proxy.inspect("x"));
        System.out.println("DIRECT " + service.execute("direct"));
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 InterceptorChainDemo.java
java InterceptorChainDemo
```

Stdout dự kiến chính xác:

```text
READY
[OUTER] before execute
[RETRY] attempt 1
[INNER] before execute
[INNER] return OK:ok#1
[INNER] finally
[OUTER] return OK:ok#1
[OUTER] finally
RESULT OK:ok#1
[OUTER] before execute
[RETRY] attempt 1
[INNER] before execute
[INNER] throw IllegalStateException
[INNER] finally
[RETRY] retry
[RETRY] attempt 2
[INNER] before execute
[INNER] return OK:again#2
[INNER] finally
[OUTER] return OK:again#2
[OUTER] finally
RESULT OK:again#2
[OUTER] before execute
[RETRY] attempt 1
[INNER] before execute
[INNER] throw IllegalArgumentException
[INNER] finally
[OUTER] throw IllegalArgumentException
[OUTER] finally
ERROR invalid
LOOKUP LOOKUP:x
DIRECT OK:direct#1
```

### 6.1. Lắp chuỗi và bắt đầu lời gọi là hai mốc khác nhau

`List.of(new Trace(...), new Retry(), ...)` tạo danh sách interceptor; `wrap(service, chain)` tạo proxy. Tại thời điểm đó **không có advice nào được kích hoạt**. `READY` xuất hiện trước những dòng `[OUTER]` và `[INNER]`.

Khi `proxy.execute("ok")` xảy ra, handler của proxy mới tạo `Invocation` và gọi `first.proceed()`. Đây là bước bắt đầu duyệt chuỗi.

### 6.2. Vì sao OUTER và INNER chạy theo thứ tự đảo chiều khi trả về?

Vì danh sách được lắp là `OUTER -> RETRY -> INNER -> target`. OUTER gọi tiếp sang RETRY; RETRY gọi sang INNER; INNER gọi target. Sau khi target trả kết quả, INNER xử lý `return/finally` trước rồi OUTER nhận kết quả.

Dòng `[OUTER] return OK:ok#1` không đến ngay sau `[OUTER] before`, vì OUTER phải đợi **toàn bộ phần chuỗi bên trong**.

### 6.3. Vì sao INNER chạy hai lần nhưng OUTER chỉ một lần ở `again`?

`Retry` nhận một context với `nextIndex` trỏ tới INNER. Context là đối tượng giữ **vị trí kế tiếp cố định** trong chương trình mẫu. Mỗi lần Retry gọi `invocation.proceed()`, một `Invocation remainder` mới được tạo bắt đầu tại INNER. Do đó hai attempt đi qua INNER và target hai lần.

OUTER đã chạy `proceed()` **một lần** để vào Retry; nó chỉ nhận kết quả sau khi Retry hoàn thành. Vì vậy OUTER ghi một `before` và một `return/finally` cho logical request `again`.

Mô hình này cố ý cho phép gọi tiếp phần đuôi nhiều lần. Một thư viện AOP khác có thể quản lý cursor/continuation theo luật khác; không được suy ra từ Java mẫu rằng API cụ thể chắc chắn hỗ trợ retry bằng `proceed` tương tự.

### 6.4. Nhánh lỗi `bad` khác `again` ra sao?

Target ném `IllegalArgumentException("invalid")` với id `bad`. Retry chỉ bắt `IllegalStateException`, nên **không retry** lỗi này. INNER ghi `throw` và `finally`; ngoại lệ đi tiếp qua Retry và OUTER; OUTER cũng ghi `throw/finally`.

Người gọi nhận đúng thông điệp `invalid`. Ví dụ chỉ minh họa chọn loại lỗi; trong hệ thật, **không được suy rằng mọi `IllegalStateException` đều là lỗi tạm thời có thể retry**. Phải xét hợp đồng và khả năng có tác dụng phụ.

### 6.5. Hai đường không kích hoạt chuỗi

`proxy.inspect("x")` vẫn tới handler proxy nhưng được chuyển tiếp thẳng vì điều kiện trong mẫu chỉ chọn `execute`. Nó cho kết quả `LOOKUP:x` và **không có log interceptor**.

`service.execute("direct")` gọi thẳng target gốc, bỏ qua proxy và toàn bộ chuỗi. Nó trả `OK:direct#1` mà không có log `[OUTER]`. Đây là giới hạn riêng của **AOP qua proxy**, không phải kết luận mọi bytecode weaver sẽ có cùng hành vi.

### 6.6. Chú ý về trạng thái trong ví dụ

`HashMap` lưu số attempt theo id chỉ để mô phỏng một thao tác tạm lỗi lần đầu. Chương trình chạy tuần tự. Nó **không** bảo đảm an toàn đa luồng hoặc chống trùng nghiệp vụ. Trong phần mềm thật, cần trạng thái phù hợp với concurrency và nơi sở hữu hiệu ứng nghiệp vụ.

`args.clone()` tạo bản sao nông của mảng đối số, không biến các đối tượng tham chiếu bên trong thành bất biến. Terminal trong mẫu gọi target bằng mảng đã chọn một lần; ví dụ **không hỗ trợ sửa đối số bằng `proceed(newArgs)`**. Nếu muốn thêm tính năng thay đối số, phải có hợp đồng xác thực số/kiểu tham số rõ ràng.

## 7. Vì sao invocation context cần biết “phần còn lại”?

Một cách triển khai dễ sai là giữ một **cursor mutable chung**:

```text
class Invocation:
    index = 0

    proceed():
        current = chain[index]
        index++
        return current.invoke(this)
```

Đây là **giả mã nguy cơ**, không phải API Java hoàn chỉnh. Nếu một interceptor gọi `proceed` lần đầu, cursor được tăng qua phần đuôi. Khi nó gọi `proceed` lần hai, cursor có thể đã tới terminal hoặc vượt quá cuối chuỗi; lúc đó phần interceptor bên trong **không được chạy lại như lần đầu**.

Tùy mục tiêu, công cụ có thể:

- Không cho phép proceed nhiều lần;
- Coi cursor là trạng thái dùng một lần;
- Sao chép context hoặc tạo continuation mới cho mỗi lần;
- Cung cấp API riêng để thực thi lại phần đuôi.

**Bài học:** không xây retry bằng cách đoán cursor sẽ “tự quay về”. Phải hiểu cơ chế triển khai và kiểm thử số lần chạy của **từng interceptor** lẫn target.

### 7.1. Vì sao ví dụ dùng `nextIndex` bất biến?

Trong ví dụ, context được đưa cho Retry giữ chỉ số bắt đầu từ INNER. Khi `proceed()`, nó **tạo context mới** cho INNER với chỉ số kế tiếp đã tăng. Bản context gốc của Retry không thay `nextIndex`. Nhờ vậy, nếu Retry gọi tiếp lần hai, cùng phần đuôi được duyệt lại.

Đây là lựa chọn để trình bày ngữ nghĩa retry một cách rõ ràng, chứ không phải yêu cầu bắt buộc của mọi hệ AOP.

### 7.2. Context theo lần gọi không phải biến toàn cục

Mỗi lời gọi tới proxy trong ví dụ tạo một `Invocation` mới. Trạng thái `nextIndex` và mảng `values` thuộc lần gọi ấy. Nếu thay bằng field dùng chung trên interceptor singleton để lưu “phương thức hiện tại” hoặc “đối số hiện tại”, hai luồng có thể ghi đè dữ liệu của nhau.

Ngay cả khi danh sách interceptor là bất biến, **nội dung đối tượng interceptor** vẫn có thể chứa trạng thái mutable. Thread safety phải được bảo đảm theo thiết kế, không thể suy từ việc dùng `List.of` là mọi thành phần đều an toàn đồng thời.

## 8. Thứ tự interceptor: thay đổi hành vi, không chỉ thay log

Xét ba chính sách:

- **Authorization:** từ chối người gọi không đủ quyền.
- **Cache:** trả dữ liệu đã có mà không gọi target.
- **Audit:** ghi sự kiện phù hợp với yêu cầu.

Nếu sắp:

```text
Cache(Authorization(Target))
```

một cache hit có thể **trả ngay**, không gọi `proceed`, do đó logic Authorization bên trong **không chạy**. Nếu chính sách yêu cầu xác thực **mọi** lượt truy cập, thứ tự này có thể sai.

Ngược lại:

```text
Authorization(Cache(Target))
```

kiểm tra quyền có cơ hội chạy trước cache. Dù vậy, vẫn cần xét dữ liệu cache có được phân vùng theo người dùng/quyền không.

### 8.1. Retry và transaction

```text
Retry(Transaction(Target))
Transaction(Retry(Target))
```

Trong cấu trúc đầu, mỗi attempt có thể mở một phạm vi transaction mới nếu interceptor Transaction được chạy lại. Trong cấu trúc sau, nhiều attempt có thể nằm trong cùng một phạm vi transaction.

Không có phương án đúng chung: trạng thái transaction sau lỗi, điều kiện retry và các tác dụng phụ bên ngoài đều ảnh hưởng. Một số lỗi khiến transaction hiện tại không thể tiếp tục; retry trong phạm vi cũ có thể không an toàn.

### 8.2. Timing và metrics

```text
Timer(Retry(Target)) -> thường đo toàn bộ yêu cầu gồm retry
Retry(Timer(Target)) -> Timer có thể đo từng attempt
```

Khi báo cáo, nên phân biệt **logical requests**, **attempts** và **effects đã cam kết**. Hai lần gọi tiếp có thể tạo hai tác dụng phụ; một log thành công ở interceptor ngoài không chứng minh chỉ một hiệu ứng.

### 8.3. Tracing và context

Một interceptor có thể tạo trace span trước `proceed`, đóng span trong `finally`. Nếu nằm ngoài retry, nó quan sát cả yêu cầu; nếu nằm trong retry, nó có thể tạo span theo từng attempt. Cần quản lý bối cảnh theo đúng vòng đời và tránh lưu context từng lượt gọi vào field global có thể bị các luồng khác ghi đè.

Khi tác vụ bất đồng bộ chuyển sang thread khác, ngữ cảnh không tự truyền chỉ vì `proceed` đã chạy trong luồng ban đầu.

## 9. Giá trị trả về, ngoại lệ và nghĩa vụ bảo toàn

Một interceptor dùng để **quan sát** không nên tự sửa hợp đồng. Cấu trúc khái niệm:

```text
before(context)
try:
    result = proceed()
    afterReturning(result)
    return result
catch error:
    afterThrowing(error)
    throw error
finally:
    cleanup()
```

Đây là **giả mã AOP**, không phải chương trình độc lập. Nếu `afterReturning` hay `cleanup` tự ném lỗi, kết quả/lỗi nhìn từ interceptor ngoài có thể đổi; vì thế cần chính sách xử lý lỗi hệ quan sát.

### 9.1. Return bình thường khác thành công nghiệp vụ

Một target có thể trả `Result.failure("DECLINED")` mà không ném ngoại lệ. Với interceptor, đó là **đường return bình thường**. Nó không tự xác nhận thanh toán thành công. Advice kiểm toán phải dựa trên hợp đồng kết quả hoặc trạng thái nghiệp vụ, không chỉ nhánh return/throw.

### 9.2. Ngoại lệ bị bọc khi dùng reflection

Trong mã ví dụ, `Method.invoke` có thể bọc lỗi của phương thức đích trong `InvocationTargetException`. Hàm `callTarget` lấy `wrapper.getCause()` để chuyển tiếp lỗi gốc. Vì vậy interceptor nhìn thấy `IllegalArgumentException` chứ không chỉ thấy wrapper reflection.

Tuy nhiên lỗi phát sinh **ngay trong interceptor** (ép kiểu sai, dereference null hoặc logging) không nhất thiết đến từ target. Hệ chẩn đoán nên phân biệt tầng phát sinh lỗi.

### 9.3. `void` và primitive return

Khi JDK dynamic proxy chặn phương thức trả `int`, handler vẫn trả `Object`; runtime proxy cần unbox từ wrapper phù hợp. Handler trả `null` cho `int` có thể gây `NullPointerException`; trả sai kiểu có thể gây `ClassCastException`. Phương thức `void` có quy ước return riêng ở API handler.

Một interceptor quanh không được tự trả `null` như giá trị mặc định cho mọi phương thức mà không xem chữ ký.

### 9.4. `finally` cũng có giới hạn

Cleanup trong `finally` chạy khi điều khiển rời `try` theo return/throw thông thường, nhưng không chứng minh tài nguyên đã được cấp thành công trước đó, và không bảo đảm chạy khi tiến trình bị dừng cưỡng bức. Nếu cleanup ném lỗi mới, nó có thể che lỗi nghiệp vụ. Với tài nguyên `AutoCloseable`, try-with-resources có thể hỗ trợ quản lý lỗi đóng và suppressed exception tốt hơn khi áp dụng đúng.

## 10. Cache, short circuit và chặn `proceed`

Một interceptor có thể không gọi tiếp khi đã có kết quả được phép dùng:

```text
intercept(invocation):
    if hasAuthorizedCachedResult(invocation):
        return cachedResult
    return proceed()
```

Đây là giả mã. Điều cần kiểm tra:

1. Cache hit có hợp lệ với **quyền, tenant và trạng thái** của yêu cầu không?
2. Có nghĩa vụ nghiệp vụ nào bắt buộc phải chạy dù cache hit không?
3. Interceptor ở bên trong bị bỏ qua có chứa kiểm toán/bảo mật bắt buộc không?
4. Giá trị trả về cache có tương thích với chữ ký và hợp đồng không?
5. Nếu target có tác dụng phụ, việc không gọi target có làm sai nghiệp vụ không?

**Không gọi `proceed` là một quyết định thay đổi luồng thực thi**, không phải tối ưu “miễn phí”. Với phương thức ghi dữ liệu, short circuit có thể rất nguy hiểm nếu không được định nghĩa là một cách xử lý hợp lệ.

## 11. Nhiều lần `proceed` và nguy cơ lặp tác dụng phụ

Một interceptor retry có thể gọi phần đuôi nhiều lần khi thấy lỗi. Nhưng timeout không chứng minh lần thử trước chưa tạo hiệu ứng.

Ví dụ:

```text
Attempt 1:
    Server creates payment record
    Network response is lost
    Client observes timeout

Attempt 2:
    Same logical request sent again
    Server may create second payment record
```

Một phép retry an toàn có thể đòi **idempotency key** bền vững tại nơi sở hữu hiệu ứng, chính sách phát hiện trùng và đối soát kết quả không chắc chắn.

Không nên bắt mọi `RuntimeException` rồi retry; lỗi dữ liệu không hợp lệ, lỗi bảo mật hoặc lỗi đã commit có ý nghĩa khác nhau. Cần định nghĩa:

- Lỗi nào được phép retry;
- Tổng số attempts và deadline;
- Backoff/jitter nếu phù hợp;
- Key gắn với logical request, không đổi theo từng attempt;
- Cách xử lý “in progress”, xung đột payload và kết quả không rõ;
- Ranh giới transaction và vòng đời resource theo từng attempt;
- Dấu vết tách biệt request, attempt và effect thực sự.

Ví dụ Java ở trên dùng `IllegalStateException` chỉ làm **tín hiệu tạm lỗi giả lập**. Nó không triển khai cơ chế retry an toàn cho thanh toán hay hệ phân tán.

## 12. Proxy bypass, self-invocation và recursion

### 12.1. Lời gọi trực tiếp target

Nếu mã giữ `target` bên cạnh `proxy`, lời gọi `target.execute()` bỏ qua bộ chặn trên proxy. Đây là lý do phải đảm bảo những thành phần cần chính sách được cấp **tham chiếu proxy phù hợp**, không phải đối tượng gốc.

### 12.2. Self-invocation

Trong nhiều mô hình proxy bao quanh đối tượng đích, khi một phương thức của target gọi `this.otherMethod()`, lời gọi nội bộ đi trực tiếp trên `this` và **không quay lại proxy**. Dù `otherMethod` có tên/chữ ký khớp điều kiện, chuỗi interceptor của proxy có thể không chạy.

Khả năng này khác giữa các kiểu proxy và bytecode weaving. Không nên tự chữa bằng cách nới pointcut; cần hiểu **đường gọi** đang bypass.

### 12.3. Gọi chính proxy từ interceptor

Một lỗi thiết kế nguy hiểm là interceptor gọi lại `proxy.execute()` thay vì `invocation.proceed()`:

```text
proxy.execute()
  -> interceptor
       -> proxy.execute()
            -> interceptor
                 -> ...
```

Lời gọi có thể bắt đầu lại **từ đầu chuỗi**, gây đệ quy vô hạn hoặc nhân số lần side effect. `proceed` đúng nghĩa là **đi tới phần còn lại**, không phải tự gọi lại điểm vào bên ngoài.

### 12.4. Proxy lồng nhau

Hai proxy độc lập bọc cùng target có thể tạo nhiều tầng intercept hơn dự kiến. Nếu mỗi tầng đều có retry hoặc logging, số lần thực thi có thể tăng. Cần phân biệt **hai interceptor trong một chain** với **hai chain do hai proxy khác nhau**; thứ tự và phạm vi có thể khác.

## 13. Những khác biệt giữa công nghệ AOP cần kiểm chứng

Các cơ chế dựa trên proxy khác nhau có thể:

- Hỗ trợ proxy **giao diện** hay **lớp**;
- Chặn được những loại phương thức nào;
- Cung cấp named pointcut, annotation matching hoặc lọc chữ ký ở đâu;
- Cho phép thay đối số trong `proceed` hay không;
- Cho phép gọi tiếp nhiều lần hay từ chối;
- Quản lý **cursor** bằng mutable state hay continuation mới;
- Có quy tắc riêng khi phương thức generic tạo bridge methods;
- Quy định thứ tự interceptor từ cấu hình hoặc registration;
- Bọc và truyền ngoại lệ theo hợp đồng API riêng;
- Xử lý phương thức của `Object`, default method và class loader theo cách riêng.

Không sử dụng các thuộc tính của **JDK dynamic proxy** trong ví dụ để suy ra mọi hệ AOP đều giống nhau. Với chính sách quan trọng, hãy dùng tài liệu và test của công nghệ sẽ triển khai.

## 14. Thiết kế interceptor thực tế

### 14.1. Rõ ràng về trách nhiệm

Một interceptor nên có mục tiêu rõ: kiểm tra quyền, ghi timing, trace, cache, retry hoặc chuyển đổi. Nếu một interceptor vừa cấp phát tài nguyên, retry, đổi lỗi và ghi kiểm toán, việc xác định thứ tự/đường lỗi trở nên khó.

Tách chính sách không có nghĩa chúng hoàn toàn độc lập: chúng cần **hợp đồng kết hợp** về thứ tự, kết quả và lifecycle.

### 14.2. Không lưu dữ liệu invocation vào field dùng chung

Tránh mô hình:

```java
class BadInterceptor {
    String currentId;
    // before: currentId = requestId
    // after:  log(currentId)
}
```

Đây là **mã minh họa không độc lập**. Nếu nhiều luồng dùng cùng interceptor instance, lần gọi A có thể đọc `currentId` của lần B. Tham số cục bộ/context theo lần gọi an toàn về mặt phân tách hơn; vẫn cần xem các đối tượng mutable được tham chiếu bên trong.

### 14.3. Không thay dữ liệu chỉ để ghi log

Nếu policy chỉ đo thời gian, interceptor không nên thay đối số, gọi target nhiều lần hoặc đổi kết quả. Nếu policy thực sự muốn biến đổi đầu vào, phải kiểm tra kiểu, quyền, chuẩn hóa và hợp đồng nghiệp vụ của thao tác.

Việc `args.clone()` chỉ nhân bản **mảng** chứ không tự làm các đối tượng trong mảng bất biến. Một interceptor có thể làm thay đổi đối tượng mutable của caller nếu viết vào trạng thái của chúng.

### 14.4. Chọn đúng phương thức và overload

Điều kiện `method.getName().equals("execute")` đủ cho ví dụ chỉ có một overload tên đó. Trong hệ thống có `execute(String)`, `execute(Object)` và `execute(String,int)`, bộ lọc tên đơn thuần quá rộng. Nên lọc thêm kiểu khai báo và số lượng/thứ tự tham số khi chính sách nhắm một overload.

## 15. Kiểm thử đúng chuỗi, không chỉ kết quả cuối

Bảng test gợi ý:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Một lần thành công | OUTER before → INNER before → target → INNER return/finally → OUTER return/finally |
| Target ném lỗi không retry | Cả INNER/OUTER xử lý lỗi; lỗi gốc được giữ |
| Retry một lần | INNER/target chạy hai lần theo ngữ nghĩa continuation; OUTER một lần |
| Interceptor không gọi tiếp | Target và interceptor bên trong không chạy |
| Interceptor gọi tiếp nhiều lần | Số lần chạy từng thành phần đúng; không phát sinh hiệu ứng ngoài ý định |
| Phương thức ngoài pointcut | Không vào chuỗi không liên quan |
| Gọi trực tiếp target | Không nhận advice của proxy |
| Self-invocation | Xác nhận đường gọi có bypass không |
| Có nhiều overload | Pointcut không khớp sai |
| Trả primitive/`null`/`void` | Kết quả qua proxy đúng kiểu |
| `InvocationTargetException` | Ngoại lệ gốc được chuyển tiếp |
| `finally` hoặc logging tự lỗi | Không che lỗi gốc trái hợp đồng |
| Nhiều thread | Không lẫn context/cursor giữa các lượt gọi |
| Cache trả sớm | Những chính sách bắt buộc không bị bypass |
| Retry ngoài/ trong transaction | Scope tài nguyên và số attempt đúng |

### 15.1. Tại sao chỉ so kết quả không đủ?

Nếu người gọi nhận `OK` sau hai lần thử, một test chỉ xác minh `equals("OK")` vẫn có thể đạt khi nghiệp vụ đã ghi dữ liệu hai lần. Cần đo **số lần gọi target, số attempt và số hiệu ứng đã xác nhận**.

Ngoài ra nên thử ca âm: một phương thức không thuộc pointcut **không** được nhận log/advice. Điều này giúp phát hiện bộ lọc quá rộng và thứ tự cấu hình sai.

### 15.2. Cách chẩn đoán khi log thiếu

1. Kiểm tra người gọi giữ **proxy hay target gốc**.
2. Xác minh phương thức có nằm trong tập proxy/interceptor hỗ trợ không.
3. Xác minh bộ lọc chữ ký/đối số đã khớp.
4. Kiểm tra interceptor bên ngoài có trả sớm mà không gọi `proceed` không.
5. Xác định số tầng proxy và thứ tự chuỗi thực tế.
6. Kiểm tra self-invocation hoặc lời gọi qua trường `this`.
7. Kiểm tra nhánh lỗi có chặn trước khi advice bên trong được thiết lập không.
8. Kiểm tra lỗi ở chính logging/binding có làm đứt luồng trước target không.
9. Dùng test tích hợp để phân biệt **khớp pointcut**, **đi qua proxy** và **advice thực sự chạy**.

## 16. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Nghĩ interceptor chạy tuyến tính một chiều | Không hiểu thứ tự after/catch/finally | Xem cấu trúc lồng `A(B(Target))` |
| Nghĩ `proceed` luôn gọi ngay target | Bỏ qua interceptor bên trong | Hiểu `proceed` gọi **phần còn lại của chuỗi** |
| Chia sẻ cursor mutable không kiểm soát | Retry bỏ qua lớp trong hoặc vào sai vị trí | Tuân thủ API, dùng continuation đúng |
| Gọi proxy từ trong interceptor | Dễ đệ quy vô hạn | Gọi `proceed`/next chuẩn |
| Dùng `proceed` nhiều lần cho logging | Có thể nhân đôi tác dụng phụ | Mặc định một lần với advice quan sát |
| Retry mọi lỗi | Thử lại lỗi vĩnh viễn, tạo tải | Lọc lỗi và có giới hạn/đối soát |
| Đặt Cache trước Authorization không xét quyền | Có thể trả dữ liệu mà bỏ kiểm tra | Xác định precedence bảo mật |
| Không xác minh proxy reference | Lời gọi bypass advice | Quản lý cấp phát đối tượng rõ ràng |
| Nhầm overload theo kiểu runtime | Áp chính sách sai phương thức | Kiểm tra chữ ký khai báo |
| Nuốt exception rồi trả null | Đổi hợp đồng, có thể lỗi primitive | Bảo toàn lỗi hoặc quy định fallback rõ |
| Lưu request ID trong field singleton | Lẫn dữ liệu nhiều luồng | Dùng context theo lần gọi |
| Cho rằng log success nghĩa là chỉ một effect | Bỏ sót double commit | Kiểm tra trạng thái nghiệp vụ |
| Coi proxy như bytecode weaving | Tưởng chặn mọi field/constructor | Xác minh loại join point hỗ trợ |

## 17. Bài tập vận dụng có đáp án

### Bài 1 — Thứ tự đi và về

Chuỗi `A(B(C(Target)))` gồm ba interceptor đều ghi trước và sau, mỗi lớp gọi tiếp một lần. Nếu Target trả bình thường, thứ tự là gì?

**Đáp án:** A-before, B-before, C-before, Target, C-after, B-after, A-after. Đây là cấu trúc lồng, không phải A-before, B-before, C-before, A-after, B-after, C-after.

### Bài 2 — Short circuit

Một interceptor cache trả kết quả mà không gọi `proceed`. Những thành phần nào chạy?

**Đáp án:** Các interceptor **bên ngoài cache** có thể chạy và nhận giá trị cache; các interceptor **bên trong** và target không chạy cho lượt đó. Nếu kiểm tra quyền nằm bên trong cache thì có nguy cơ bị bỏ qua.

### Bài 3 — Retry và phạm vi

Với `Audit(Retry(Metrics(Target)))`, Retry gọi tiếp hai lần và continuation cho phép chạy lại phần đuôi. Audit và Metrics chạy mấy lần?

**Đáp án:** Audit thường có một lượt kích hoạt ở ngoài; Metrics có thể chạy hai lần theo từng attempt; Target cũng có thể chạy hai lần. Phải xác minh API proceed của công nghệ đang dùng.

### Bài 4 — Lỗi sau commit

Target tạo giao dịch rồi timeout. Interceptor retry gọi `proceed` lại. Vì sao không thể kết luận an toàn?

**Đáp án:** Timeout có thể xuất hiện sau khi giao dịch đã tạo effect. Lần thử tiếp có thể tạo effect thứ hai. Cần idempotency ở nơi sở hữu effect và đối soát kết quả không chắc chắn.

### Bài 5 — Gọi proxy từ chính advice

Interceptor tự gọi `proxy.execute()` thay vì `invocation.proceed()`. Điều gì dễ xảy ra?

**Đáp án:** Lời gọi bắt đầu lại từ điểm vào ngoài, kích hoạt chính interceptor và có nguy cơ đệ quy hoặc lặp xử lý. `proceed` cần chỉ tới phần chuỗi kế tiếp.

### Bài 6 — Context đồng thời

Một interceptor singleton giữ `currentMethod` và `currentArgs` trong field để dùng sau lời gọi. Vì sao không an toàn?

**Đáp án:** Hai luồng có thể ghi đè dữ liệu cùng field. Nên giữ trạng thái theo từng invocation hoặc dùng cơ chế truyền context có vòng đời, đồng thời phải xét các đối tượng mutable bên trong.

### Bài 7 — Ngoại lệ được khôi phục

Một interceptor bên trong bắt lỗi đích rồi trả fallback. Interceptor ngoài sẽ nhất thiết thấy after-throwing không?

**Đáp án:** Không. Với ranh giới interceptor ngoài, phần bên trong đã **trả về bình thường** nhờ fallback, nên interceptor ngoài có thể thấy nhánh return. Phải xét ranh giới thực thi từng interceptor.

### Bài 8 — Proxy bypass

Dịch vụ có phương thức `outer()` gọi `this.inner()`. Một proxy bao đối tượng đích có chắc chặn lời gọi inner không?

**Đáp án:** Không. Trong nhiều mô hình proxy, self-invocation đi trực tiếp trên target và không đi lại qua proxy. Cần kiểm tra công nghệ hoặc thay đổi ranh giới gọi phù hợp.

### Bài 9 — Phân biệt context

JDK proxy nhận đối số `int` qua mảng `Object[]`. Loại giá trị thường thấy ở phần tử mảng và loại chữ ký khai báo là gì?

**Đáp án:** Phần tử mảng dùng wrapper `Integer`, còn `Method.getParameterTypes()` vẫn thể hiện `int.class`. Không đồng nhất boxing với overload.

## 18. Ghi nhớ

- **Proxy là điểm vào**, interceptor là các lớp can thiệp, `proceed` là bước sang **phần còn lại của chuỗi**.
- Chuỗi có cấu trúc **lồng nhau**, nên thứ tự before và after thường ngược nhau.
- **Invocation context** thuộc một lượt gọi và mang method/arguments/đích/vị trí tiếp tục theo mô hình hỗ trợ.
- Interceptor có thể trả sớm, gọi tiếp một lần hoặc nhiều lần **nếu API cho phép**; mỗi lựa chọn thay đổi hành vi quan sát.
- **Retry có thể chạy lại các interceptor bên trong và target**, dẫn tới tác dụng phụ lặp; phải xét idempotency và ranh giới nghiệp vụ.
- **Thứ tự interceptor là một phần hợp đồng**: cache, quyền truy cập, retry, transaction, timing và kiểm toán có thể đổi nghĩa khi hoán vị.
- **Proxy có đường bypass** khi gọi target trực tiếp hoặc self-invocation không qua đại diện; không mặc định nó chặn constructor/field access.
- Advice quan sát nên giữ nguyên **đối số, kết quả, ngoại lệ và số lần thực thi**; kiểm thử dương và âm trên đường gọi thật.
