# Tái nhập, lời gọi lồng nhau và aspect tự can thiệp trong AOP

## 1. Bức tranh chung: tại sao advice có thể gọi lại chính nó?

Trong **lập trình hướng khía cạnh (Aspect-Oriented Programming — AOP)**, một **aspect** đóng gói các mối quan tâm xuyên suốt như ghi log, kiểm toán, đo thời gian, kiểm tra quyền, cache hoặc quản lý trạng thái. **Pointcut** lựa chọn các **join point** được công cụ AOP hỗ trợ; **advice** thực hiện hành vi trước, sau hoặc bao quanh những điểm ấy.

AOP làm đường thực thi có thêm một hoặc nhiều lớp can thiệp. Một lời gọi tưởng như đơn giản:

```text
caller -> businessMethod()
```

có thể trở thành:

```text
caller
  -> Advice A
      -> Advice B
          -> businessMethod()
      <- Advice B
  <- Advice A
```

Khi business method tiếp tục gọi một method khác, hoặc **bản thân advice** gọi một method cũng khớp pointcut, chuỗi can thiệp có thể đi vào lại cùng aspect. Hậu quả có thể là hành vi hợp lệ, log lồng nhau, đếm sai, vòng lặp vô hạn, tràn stack, deadlock hoặc phát sinh lỗi khó truy vết.

Có ba hiện tượng cần phân biệt:

1. **Nested calls — lời gọi lồng nhau:** đang ở trong một thao tác thì gọi tiếp thao tác khác. Không nhất thiết là lỗi và không nhất thiết gọi lại cùng method.
2. **Reentrancy — tái nhập:** cùng một thành phần/logic có thể được đi vào lần nữa trước khi lần trước kết thúc, trực tiếp hoặc gián tiếp.
3. **Self-interception — aspect tự can thiệp:** một lời gọi do advice tạo ra lại khớp pointcut, khiến chính advice hoặc một chain liên quan được kích hoạt lại.

Còn một trường hợp dễ nhầm là **self-invocation bypass**: target tự gọi `this.inner()` nhưng lời gọi ấy **không đi qua proxy bên ngoài**, khiến một advice mong đợi **không chạy**. Đây gần như là vấn đề đối nghịch với self-interception: một phía can thiệp **quá nhiều**, phía kia can thiệp **không đủ**.

Bài này đi từ cơ bản tới nâng cao, trình bày cách nhận diện, thiết kế guard, kiểm soát state theo invocation, xử lý lỗi và kiểm thử. Các ví dụ Java 17 dùng để minh họa cơ chế, **không coi một engine AOP hay kiểu weaving cụ thể là chuẩn cho mọi công cụ**.

## 2. Thuật ngữ và ranh giới

| Khái niệm | Định nghĩa thực hành | Ví dụ |
| --- | --- | --- |
| **Call stack** | Chuỗi những lời gọi đang hoạt động trong một thread | `outer → inner → repository` |
| **Nested invocation** | Một invocation bắt đầu khi invocation khác chưa kết thúc | `outer` gọi `inner` |
| **Recursion** | Một thao tác quay lại cùng thao tác hoặc cùng chu trình gọi | `f → f` hoặc `f → g → f` |
| **Reentrancy** | Thành phần được đi vào lại trong lúc trạng thái lần trước còn hoạt động | Advice logging lại kích hoạt advice logging |
| **Self-invocation** | Method của object gọi một method khác trên chính receiver | `this.inner()` |
| **Self-interception** | Advice gọi thao tác mà pointcut chọn, rồi bị áp advice lần nữa | Advice → logger → cùng pointcut → advice |
| **Pointcut scope** | Tập join point được biểu thức/cấu hình lựa chọn | Execution của một nhóm method |
| **Interception boundary** | Nơi engine gắn logic advice vào đường chạy | Proxy, call site, method body hoặc loader |
| **Proceed/continuation** | Cách around advice chuyển điều khiển vào phần bên trong | `proceed()` |
| **Invocation-local context** | Thông tin riêng cho một lần gọi | Depth, trace ID, snapshot và timing |
| **Reentrancy guard** | Quy tắc ngăn hoặc phân nhánh khi đi lại vào vùng không được phép | Tránh trace logger tự kích hoạt |

**Nested call không đồng nghĩa recursion.** Ví dụ `checkout() → validate() → save()` là lồng nhau nhưng không tạo vòng.

**Recursion không mặc nhiên sai.** Hàm tính cây, parser hoặc duyệt đồ thị có thể đệ quy hợp lệ. Sai lầm nằm ở việc **advice vô tình tạo chu trình không có điều kiện dừng** hoặc trộn state giữa các mức sâu.

**Reentrancy cũng không luôn là lỗi.** Một aspect có thể có chủ đích quan sát từng lời gọi lồng nhau. Vấn đề là hợp đồng của nó có được thiết kế để xử lý nhiều lần vào đồng thời hoặc lồng nhau hay không.

## 3. Biểu đồ ba đường gọi khác nhau

### 3.1. Lời gọi lồng nhau hợp lệ

```text
Caller
  -> AOP before(outer)
      -> business outer()
          -> business inner()
      <- business outer returns
  <- AOP after(outer)
```

Tùy pointcut và cơ chế weaving, `inner` có thể nhận advice riêng hoặc không.

### 3.2. Advice tự kích hoạt do logging

```text
Caller -> service.save()
            |
            v
        LoggingAdvice
            |
            v
        logger.write()
            |
            v
       LoggingAdvice    <-- cùng pointcut lại khớp
            |
            v
        logger.write()
            |
           ...
```

Nếu không có exclusion/guard phù hợp và chu trình không có điều kiện dừng, stack có thể tiếp tục lớn cho đến khi hết tài nguyên hoặc runtime chặn.

### 3.3. Self-invocation bypass proxy

```text
Caller -> Proxy -> target.outer()
                    |
                    +--> target.this.inner()
                          |
                          +--> không đi qua Proxy
```

Ở kiểu proxy **giữ target riêng**, inner không nhất thiết được can thiệp dù caller vào outer qua proxy. Nếu weaving trực tiếp vào body của inner hoặc một subclass proxy dùng receiver khác, hành vi có thể khác.

Vì thế cần xác định **cả điểm phù hợp với pointcut lẫn đường gọi thực tế** trước khi kết luận advice thừa hay thiếu.

## 4. Lời gọi lồng nhau và chiều sâu của chain

Giả sử một aspect đo thời gian ở cả `OrderService.submit` và `Inventory.reserve`:

```text
submit()
  -> reserve()
  -> charge()
```

Nếu mỗi method đều được advice, một trace hợp lệ có thể là:

```text
enter submit, depth=0
  enter reserve, depth=1
  exit reserve, depth=1
  enter charge, depth=1
  exit charge, depth=1
exit submit, depth=0
```

**Depth** cho biết số invocation đang được theo dõi trong một ngữ cảnh thực thi cụ thể. Nó không tự đại diện cho độ sâu **nghiệp vụ** của toàn hệ thống phân tán, và cũng không phải một ID duy nhất.

### 4.1. Đếm số invocation khác đếm số request

Một request gọi ba method được advice có thể tạo ba invocation và sáu event enter/exit. Nếu báo cáo “request count” tăng ở mỗi method, hệ thống sẽ đếm thừa.

Cần phân biệt:

- **Request ID:** thao tác logic ngoài cùng.
- **Invocation/span ID:** một lần vào join point cụ thể.
- **Join-point identity:** loại/chữ ký hoặc vị trí mã được can thiệp.
- **Depth:** chỉ báo mức lồng nhau của stack/chain đang quan sát.
- **Attempt ID:** lượt thử lại khi retry.

Không gộp các danh tính này thành một biến `counter` dùng chung.

### 4.2. Duration bao gồm hay loại trừ thời gian con?

Nếu `submit()` gọi `reserve()`, duration của submit từ lúc vào đến lúc ra thường **bao gồm** thời gian reserve. Tổng durations của mọi method có thể **lớn hơn** thời gian wall-clock của request do đếm lặp thời gian lồng nhau.

Hai khái niệm:

- **Inclusive time:** từ enter đến exit, bao cả lời gọi con.
- **Exclusive/self time:** thời gian của đoạn được đo sau khi loại trừ đúng các khoảng thuộc lời gọi con phù hợp.

Muốn tính exclusive time cần một cấu trúc stack/interval nhất quán. Đừng chỉ cộng duration của tất cả span rồi gọi đó là tổng độ trễ request.

## 5. Tái nhập là thuộc tính của trạng thái, không chỉ của tên method

Hãy xem một advice:

```text
before any service method:
    beginTime = now()
```

Nếu `beginTime` là field mutable chung trên singleton aspect, invocation lồng nhau có thể ghi đè giá trị trước khi invocation ngoài kết thúc:

```text
outer enters -> beginTime = T0
inner enters -> beginTime = T1
inner exits  -> now - T1
outer exits  -> now - T1  // sai, cần T0
```

Ngay cả khi chỉ một thread, trạng thái vẫn sai. Đây là **lỗi reentrancy**, không nhất thiết cần race giữa nhiều thread.

### 5.1. Hai mức lỗi khác nhau

- **Nested-state corruption:** một thread vào lại advice trước khi advice ngoài kết thúc, làm ghi đè state.
- **Concurrent-state corruption:** hai thread độc lập sửa cùng field của aspect, làm trộn invocation và gây race.

Dùng `synchronized` có thể xử lý một số race giữa thread nhưng **không tự sửa** thiết kế snapshot sai khi lồng nhau trong cùng thread. Đồng thời, `synchronized` trên method Java có tính **reentrant** cho cùng thread, nên lock không tự chặn vòng lặp self-interception.

### 5.2. Stack theo invocation

Nếu cần giữ thời gian bắt đầu, có thể dùng ngăn xếp per-thread cho lời gọi đồng bộ, hoặc ngữ cảnh riêng cho từng invocation. Mỗi lần enter đẩy frame; mỗi lần exit lấy đúng frame của nó.

Tuy nhiên với **async**, frame có thể kết thúc trên thread khác: per-thread stack không còn đủ; cần context truyền theo task và định nghĩa completion boundary.

## 6. Aspect tự can thiệp: các nguồn tạo vòng lặp

### 6.1. Logging

Advice gọi `logger.log()`, nhưng pointcut chọn cả logger. Logger lại bị cùng advice kích hoạt.

### 6.2. Metrics

Advice đo thời gian và gọi `metrics.increment()`, còn pointcut chọn cả các method metrics. Nếu mỗi lần tăng metric lại tạo metric mới, sẽ nhân lên vô hạn hoặc tới một giới hạn ngoài ý định.

### 6.3. Audit và persistence

Audit advice ghi audit record qua repository; pointcut chọn mọi repository method, bao gồm chính thao tác ghi audit. Khi đó một lần audit có thể sinh thêm audit vô tận.

### 6.4. Security lookups

Authorization advice tra quyền bằng một service/repository nằm trong pointcut yêu cầu authorization. Nếu việc tra quyền lại cần tự kiểm quyền qua cùng đường ấy, có thể tạo **chu trình phụ thuộc**.

### 6.5. Serialization và `toString()`

Advice log `args.toString()`. Nếu `toString` hoặc getter bên trong bị intercept, logic ghi log có thể tự kích hoạt. Ngoài recursion, `toString()` còn có thể làm I/O, giữ lock hoặc lộ dữ liệu nhạy cảm.

### 6.6. Exception reporting

Advice bắt lỗi rồi gửi lỗi tới monitoring client; nếu client cũng khớp pointcut hoặc ném lỗi khác, đường xử lý exception có thể tạo **exception storm** hoặc che lỗi gốc.

Các trường hợp trên cho thấy **dependency của advice cũng nằm trên call graph**. Khi chọn pointcut, cần kiểm tra cả những method mà advice sẽ gọi, không chỉ method nghiệp vụ.

## 7. Tái nhập trực tiếp, gián tiếp và qua nhiều aspect

**Tái nhập trực tiếp:**

```text
AuditAdvice -> audit() -> AuditAdvice -> audit() -> ...
```

**Tái nhập gián tiếp:**

```text
AuditAdvice
  -> LoggingFacade
      -> Repository.saveLog
          -> AuditAdvice
```

**Chu trình qua hai aspect:**

```text
Aspect A -> helperB() -> Aspect B -> helperA() -> Aspect A
```

Không nhất thiết có một method gọi lại chính nó bằng tên. Một chu trình dài có thể qua cache, logger, serializer, callback hoặc retry.

### 7.1. Phân tích call graph

Để điều tra, đánh dấu từng cạnh:

| Cạnh | Chủ thể gọi | Thao tác được gọi | Có thể được aspect chọn? |
| --- | --- | --- | --- |
| 1 | Caller | Business.execute | Có |
| 2 | Advice | Logger.write | Có/Không theo pointcut |
| 3 | Logger | Storage.append | Có/Không |
| 4 | Storage | Hook.notify | Có/Không |
| 5 | Hook | Business.execute | Có thể tạo chu trình |

Nếu có đường từ **advice trở lại chính advice** mà không có điều kiện dừng hoặc exclusion, nguy cơ recursion tồn tại.

### 7.2. Chu trình có điều kiện dừng khác chu trình vô hạn

Một advice có thể cố ý thực hiện thao tác phụ chỉ ở mức ngoài cùng rồi bỏ qua phần phụ ở các mức lồng nhau. Khi đó có một chu trình call graph tiềm năng, nhưng **guard** ngăn tái nhập không kiểm soát.

Điều cần chứng minh là guard **đúng phạm vi** và không bỏ sót lời gọi hợp lệ khác.

## 8. Hai chiến lược chính: thu hẹp pointcut và guard runtime

### 8.1. Exclusion tĩnh

Nếu aspect dành để audit các nghiệp vụ, thường không nên chọn chính method ghi audit:

```text
include:
  business operations cần audit

exclude:
  audit sink, logger, advice helpers, instrumentation package
```

Đây là mô tả trung lập công cụ, không phải DSL chạy được.

Ưu điểm:

- Không tốn guard ở các điểm đã loại.
- Dễ lập báo cáo pointcut matched/unmatched.
- Giảm nguy cơ instrumentation gọi lại instrumentation.
- Cho phép kiểm thử tập điểm cần chọn một cách độc lập.

Giới hạn:

- Một call graph thay đổi có thể đưa helper khác vào tập khớp.
- Overload/annotation/package wildcard có thể đổi theo refactor.
- Không phải mọi chu trình được xác định hoàn toàn từ thông tin tĩnh.
- Dynamic guard vẫn có thể cần khi cùng method phục vụ cả lời gọi phụ và lời gọi nghiệp vụ.

### 8.2. Guard động

Một guard runtime có thể nhận biết đang trong **đường emission/logging của chính advice** rồi bỏ qua chỉ phần instrumentation không được tái nhập.

Mã giả:

```text
if currentlyEmittingTrace:
    invokeOriginalWithoutTrace()
else:
    currentlyEmittingTrace = true
    try:
        emitTrace()
    finally:
        currentlyEmittingTrace = false
    proceedNormally()
```

Nhưng mã giả này phải được hiện thực cẩn thận:

- Nếu biến dùng chung cho mọi thread, request khác có thể bị bỏ instrumentation.
- Nếu đặt guard quá rộng quanh toàn bộ `proceed`, những lời gọi nghiệp vụ lồng nhau hợp lệ cũng có thể bị tắt advice.
- Nếu không reset trong `finally`, một lỗi logging có thể khiến tất cả lời gọi sau bị bỏ qua.
- Nếu một helper có nhiều đường gọi khác nhau, cần phân biệt **vì sao** helper được gọi, không chỉ tên method.

**Ưu tiên loại khỏi pointcut các helper có thể xác định tĩnh**, và dùng guard để xử lý phần tái nhập thực sự động, với phạm vi tối thiểu.

## 9. Guard quá rộng làm mất các advice hợp lệ

Xem thiết kế sau:

```text
if insideAnyAdvice:
    invokeTargetDirectly()
else:
    insideAnyAdvice = true
    try:
        proceed()
    finally:
        insideAnyAdvice = false
```

Khi `outer` gọi `inner` trong lúc `outer` được advice bao, cờ `insideAnyAdvice` vẫn true. Vì vậy advice của `inner` bị bỏ qua, dù `inner` là một operation được phép và cần audit riêng.

Tức là ta “chữa” recursion bằng cách **xóa luôn nested instrumentation hợp lệ**.

Thiết kế tốt hơn:

- Tách **guard của việc phát trace/log** khỏi **ngữ cảnh depth của lời gọi nghiệp vụ**.
- Xác định những method helper mà aspect gọi trong quá trình tự quan sát.
- Chỉ bỏ qua instrumentation trên **đường tái nhập nội bộ** cần ngăn.
- Cho phép nested business invocation vẫn được chọn và ghi nhận.
- Kiểm thử cả đường self-interception lẫn nested call bình thường.

Một boolean chung tên `alreadyInAspect` thường không đủ diễn tả mọi trường hợp.

## 10. Java 17 runnable: nested advice, self-interception và guard

Ví dụ dưới sử dụng **JDK dynamic proxy** để tạo một interceptor. Nó không phải bộ dệt AOP tổng quát và không áp một DSL pointcut. Ta cố ý thiết kế:

1. `outer` được gọi qua proxy và có advice.
2. Trong `outer`, target gọi `this.local` **trực tiếp**, nên không có advice riêng cho `local`.
3. Target gọi `self.inner`, trong đó `self` trỏ tới proxy, nên `inner` tạo một invocation advice **lồng bên trong**.
4. Advice ghi trace thông qua **chính proxy** bằng `proxy.trace(...)`. Lời gọi này tái nhập handler, và một `ThreadLocal` guard bỏ qua **instrumentation của trace** chứ không tắt advice của `inner`.
5. Có đường exception từ `inner`; depth được dọn trong `finally`.
6. Một lời gọi trực tiếp target thể hiện bypass proxy.

Tạo file `NestedAdviceDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class NestedAdviceDemo {

    interface Operations {
        String outer(String id);
        String inner(String id);
        void local(String id);
        void trace(String message);
    }

    static final class Core implements Operations {
        private Operations self;

        void setSelf(Operations self) {
            this.self = self;
        }

        @Override
        public String outer(String id) {
            System.out.println("business:outer:" + id);
            this.local(id);   // Không đi qua proxy ngoài.
            return self.inner(id); // Cố ý đi qua proxy.
        }

        @Override
        public String inner(String id) {
            System.out.println("business:inner:" + id);
            if ("ERR".equals(id)) {
                throw new IllegalStateException("inner failed");
            }
            return "OK:" + id;
        }

        @Override
        public void local(String id) {
            System.out.println("business:local:" + id);
        }

        @Override
        public void trace(String message) {
            System.out.println("business:trace:" + message);
        }
    }

    public static void main(String[] args) {
        Core target = new Core();

        ThreadLocal<Integer> depth =
                ThreadLocal.withInitial(() -> 0);
        ThreadLocal<Boolean> emitting =
                ThreadLocal.withInitial(() -> false);

        Operations proxy = (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                (Object p, Method method, Object[] values) -> {
                    String name = method.getName();

                    // Chỉ bỏ instrumentation trên đường trace tự phát sinh.
                    if ("trace".equals(name) && emitting.get()) {
                        System.out.println("guard:trace-reentry");
                        try {
                            return method.invoke(target, values);
                        } catch (InvocationTargetException wrapped) {
                            throw wrapped.getCause();
                        }
                    }

                    int level = depth.get();
                    System.out.println("advice:enter:" + name
                            + ":depth=" + level);
                    depth.set(level + 1);

                    try {
                        emitting.set(true);
                        try {
                            ((Operations) p).trace(name);
                        } finally {
                            emitting.remove();
                        }

                        try {
                            Object result = method.invoke(target, values);
                            System.out.println("advice:success:" + name);
                            return result;
                        } catch (InvocationTargetException wrapped) {
                            Throwable original = wrapped.getCause();
                            System.out.println("advice:throw:" + name
                                    + ":" + original.getClass().getSimpleName());
                            throw original;
                        }
                    } finally {
                        if (level == 0) {
                            depth.remove();
                        } else {
                            depth.set(level);
                        }
                        System.out.println("advice:exit:" + name
                                + ":depth=" + level);
                    }
                }
        );

        target.setSelf(proxy);

        System.out.println("case:ok");
        System.out.println("caller:" + proxy.outer("A"));

        System.out.println("case:error");
        try {
            proxy.outer("ERR");
        } catch (IllegalStateException error) {
            System.out.println("caller:error:" + error.getMessage());
        }

        System.out.println("case:direct");
        System.out.println("caller:" + target.inner("B"));
    }
}
```

Biên dịch/chạy với JDK 17 hoặc mới hơn:

```bash
javac NestedAdviceDemo.java
java NestedAdviceDemo
```

**Đầu ra xác định:**

```text
case:ok
advice:enter:outer:depth=0
guard:trace-reentry
business:trace:outer
business:outer:A
business:local:A
advice:enter:inner:depth=1
guard:trace-reentry
business:trace:inner
business:inner:A
advice:success:inner
advice:exit:inner:depth=1
advice:success:outer
advice:exit:outer:depth=0
caller:OK:A
case:error
advice:enter:outer:depth=0
guard:trace-reentry
business:trace:outer
business:outer:ERR
business:local:ERR
advice:enter:inner:depth=1
guard:trace-reentry
business:trace:inner
business:inner:ERR
advice:throw:inner:IllegalStateException
advice:exit:inner:depth=1
advice:throw:outer:IllegalStateException
advice:exit:outer:depth=0
caller:error:inner failed
case:direct
business:inner:B
caller:OK:B
```

### 10.1. Vì sao có `guard:trace-reentry`?

Mỗi lần handler ghi event, nó cố ý gọi `((Operations) p).trace(name)` **qua chính proxy**. Điều đó lại đi vào handler. Vì cờ `emitting` đang true và method là `trace`, handler chuyển tiếp tới target **mà không phát thêm event advice**.

Nếu bỏ guard nhưng vẫn để advice cho `trace` tự gọi `trace`, sẽ có chu trình:

```text
handler(outer)
 -> proxy.trace
 -> handler(trace)
    -> proxy.trace
    -> handler(trace)
       ...
```

Không nên cố tình chạy phiên bản thiếu guard trong môi trường production để “xem nó tràn stack”.

### 10.2. Vì sao `inner` vẫn nhận advice?

Guard `emitting` chỉ được bật **trong khối phát trace** và được gỡ trước khi `method.invoke(target, values)` gọi business. Khi target.outer gọi `self.inner`, flag này đã được gỡ, nên `inner` vẫn có advice riêng.

Đây là điểm khác biệt chủ chốt giữa **guard hẹp, theo đường tự ghi trace** và **guard toàn bộ business continuation** gây bỏ sót nested advice hợp lệ.

### 10.3. Vì sao `local` không có advice?

`Core.outer` gọi `this.local(id)` trên target. Lời gọi này **không qua proxy** dù `local` có trong interface `Operations`. Vì vậy có event business nhưng không có `advice:enter:local`.

Nếu thay bằng `self.local(id)`, trong ví dụ này nó sẽ đi qua proxy, nhưng việc sửa mọi self-invocation thành tự gọi proxy không phải giải pháp tổng quát: nó có thể thay đổi semantics, tạo vòng lặp và làm rối ownership/identity. Một bộ dệt bytecode trực tiếp còn có phạm vi khác.

### 10.4. Depth và finally trên nhánh lỗi

Ở ca `ERR`, `inner` ném `IllegalStateException`. Handler của `inner` đọc `InvocationTargetException.getCause()`, ghi lỗi rồi ném nguyên nhân. Finally của `inner` khôi phục depth cho invocation ngoài trước khi finally của `outer` khôi phục về trạng thái ban đầu.

Kết quả `advice:exit:inner:depth=1` và `advice:exit:outer:depth=0` chứng minh việc **dọn context theo mức lồng nhau** dù business ném lỗi.

### 10.5. Hạn chế cần nêu của ví dụ

- Đây là **JDK interface proxy**, không phải một Aspect compiler.
- `self` được cố ý trỏ tới proxy chỉ để minh họa đường nested interception; trong ứng dụng thật việc cấp proxy self-reference cần xem lifecycle, khả năng tái nhập và ownership.
- `ThreadLocal` thích hợp để minh họa **lời gọi đồng bộ trên cùng thread**; nó không tự động mang context qua thread pool hoặc coroutine/task.
- Nếu `target.trace` thực hiện I/O và cũng gọi proxy ở đường khác, guard trong ví dụ có thể cần tinh chỉnh theo call graph thực tế.
- `Core` không được thiết kế để mutation đồng thời; ví dụ chỉ in event, không chứng minh hệ thống có thread safety.
- Không có sự bảo đảm từ ví dụ rằng mọi engine AOP cho phép cùng cơ chế proceed/override/self-call.

## 11. Mẫu thiết kế guard an toàn theo mục đích

Một guard hợp lý cần trả lời:

1. **Đang ngăn tái nhập vào thao tác nào?** Logger, audit sink, metrics exporter hay toàn bộ aspect?
2. **Tái nhập theo đường nào?** Do advice gọi helper, do business gọi lại, hay do callback bất đồng bộ?
3. **Phạm vi nào?** Một invocation, một thread, một request hay toàn tiến trình?
4. **Guard được bật từ đâu tới đâu?** Chỉ khi emit telemetry hay suốt business body?
5. **Ai dọn guard khi có exception?** `finally` hoặc cơ chế scope tương ứng.
6. **Khi guard active thì làm gì?** Bỏ log, gọi target trực tiếp, trả fallback hay báo lỗi?
7. **Một method vừa là helper vừa là business operation thì sao?** Cần dựa trên ngữ cảnh, không chỉ tên method.
8. **Có rủi ro mất audit bắt buộc không?** Nếu có, không được tùy ý skip.
9. **Có thread/task handoff không?** Nếu có, cần mô hình context khác hoặc bổ sung.

### 11.1. Cờ boolean không đủ cho nested state độc lập

Nếu advice cần nhiều mức nested mỗi mức giữ thông tin, `ThreadLocal<Boolean>` có thể chỉ biểu diễn “đang ở trong vùng X”. Một `ThreadLocal<Integer>` depth hoặc stack frame có thể phù hợp hơn khi cần **phân biệt từng invocation**.

Đừng dùng depth như cơ chế để tự động bỏ mọi invocation có `depth>0`. Đó là một chính sách riêng, có thể làm mất nested audit hợp lệ.

### 11.2. Exception trong phần đặt guard

Nếu đoạn đặt guard thành công nhưng đoạn phát log ném exception trước khi reset, một cờ còn sót sẽ làm những lời gọi sau trên cùng thread bị bỏ qua. Trong thread pool, lỗi này có thể ảnh hưởng request khác chạy trên thread được tái sử dụng.

Dùng `try/finally` để reset **ngay trong scope ngắn nhất**.

### 11.3. Tránh bỏ guard của một scope ngoài

Nếu hai scope cùng dùng một cờ boolean, scope trong gọi `remove()` có thể vô tình xóa guard do scope ngoài đang sở hữu. Cần một cơ chế **lưu và khôi phục trạng thái trước đó**, depth counter, hoặc token/scope theo stack.

Ví dụ khái niệm:

```text
previous = guard.get()
guard.set(true)
try:
    emit()
finally:
    restore(previous)
```

Việc `restore` có thể là `remove` hoặc `set(previous)` tùy trạng thái ban đầu. Nếu context có thể tái nhập nested chính phần emission, không nên thiết kế một cờ duy nhất mà không phân biệt ownership.

## 12. Vì sao ThreadLocal hữu ích nhưng không phải lời giải phổ quát?

Trong Java 17, `ThreadLocal<T>` gắn một giá trị riêng với từng thread. Với call stack **đồng bộ, không chuyển thread**, nó phù hợp để theo dõi depth hoặc guard.

Những giới hạn:

- Một thread pool có thể tái sử dụng thread cho request khác; không `remove()` đúng cách có thể làm rò context.
- Một request có thể tiếp tục ở thread khác; `ThreadLocal` hiện tại **không tự truyền** qua nhiệm vụ mới.
- Một thread có thể thực hiện nhiều logical operations nối tiếp; thread identity không phải request ID.
- Advice có thể gọi đệ quy trong cùng thread; một field `startTime` duy nhất trong ThreadLocal vẫn bị ghi đè nếu không dùng stack.
- Kích thước state lớn và vòng đời dài có thể làm tăng giữ tham chiếu không mong muốn.
- `InheritableThreadLocal` cũng không tự giải quyết semantics của thread pool, task cancellation hoặc context propagation.

### 12.1. Khi nào dùng explicit invocation context?

Nếu cần nhiều thông tin hơn một cờ:

```text
InvocationContext:
  traceId
  invocationId
  parentInvocationId
  depth
  pointcutId
  adviceId
  startedAt
  guardFlags
```

Đây là schema minh họa, không phải Java API có sẵn.

Một context riêng cho invocation có thể được truyền vào advice chain hoặc lưu trong cấu trúc scope phù hợp. Khi async, cần quyết định **context nào được kế thừa, context nào là mới, ai sở hữu vòng đời và ai cleanup**.

## 13. Lồng nhau, đệ quy và giá trị trạng thái “old”

Một aspect kiểm invariant có thể chụp snapshot `oldState` trước mỗi method. Với recursion:

```text
outer enters: old = S0
inner enters: old = S1
inner exits: compare against S1
outer exits: compare against S0
```

Nếu cả hai snapshot được lưu vào cùng một field mutable, inner ghi đè old của outer. Hậu điều kiện của outer sẽ sai dù business đúng.

Cách khắc phục:

- Snapshot đặt trong local variable của **mỗi around invocation** nếu engine cho phép.
- Hoặc một stack per invocation/thread với push/pop cân bằng.
- Hoặc context riêng được truyền theo continuation.
- Không dùng một field singleton dùng chung cho nhiều request.

### 13.1. Local variable giúp reentrancy-safe theo stack frame

Trong Java, mỗi lần gọi một method có bản local variables riêng. Nếu around advice được hiện thực là **một method invocation mới** ở mỗi lần vào, giá trị local lưu trên frame đó không bị ghi đè bởi lời gọi lồng nhau.

Tuy nhiên, object tham chiếu mà local variable giữ vẫn có thể mutable/chia sẻ. Dùng local reference không tự bảo đảm snapshot bất biến hay thread safety.

## 14. Around advice và số lần gọi proceed

Một around advice có thể điều khiển continuation:

```text
around operation:
    before
    value = proceed()
    after
    return value
```

Trong một số công cụ, quanh-advice có thể **không proceed**, hoặc **proceed nhiều lần** để retry. Không phải mọi công cụ hoặc loại join point đều có cùng quyền.

Với nested calls, cần đếm theo từng **attempt**:

```text
RetryAround
  attempt 1 -> InnerAdvice -> Business throws
  attempt 2 -> InnerAdvice -> Business returns
```

Nếu một aspect đếm “một operation” theo số lần vào InnerAdvice, nó có thể ghi **hai** event cho cùng một request logic.

### 14.1. Không để guard chặn cả lần retry hợp lệ

Một cờ `insideAspect=true` đặt quanh toàn bộ retry có thể khiến attempt 2 bỏ qua advice cần thiết. Phải quyết định chính sách được áp dụng theo:

- Logical request (một lần).
- Mỗi invocation.
- Mỗi retry attempt.
- Mỗi lần business side effect.
- Completion cuối của request.

Sự lựa chọn thuộc **hợp đồng của aspect**, không phải chi tiết tùy tiện của implementation.

### 14.2. Retry và tính idempotent

Nếu target đã thực hiện side effect rồi một after advice ném lỗi, retry từ lớp ngoài có thể lặp side effect. Guard không làm rollback. Với operation không idempotent, cần xác định điều kiện retry và cơ chế chống trùng thích hợp.

## 15. Phối hợp nhiều aspect và rủi ro tái nhập chéo

Giả sử:

```text
Audit(
    Authorization(
        Business
    )
)
```

Authorization cần đọc quyền từ repository. Repository cũng nằm trong pointcut Audit:

```text
Audit.enter(business)
  -> Authorization.checkPermission()
      -> repository.findPermissions()
          -> Audit.enter(repository)
```

Đây **có thể là nested audit hợp lệ**, nếu kiểm toán cả truy vấn quyền là chủ đích.

Nhưng nếu Audit ghi event qua `repository.saveAudit` và method này lại khớp Audit, thì có thể có **self-interception** nguy hiểm.

### 15.1. Không loại mọi repository method theo thói quen

Loại toàn bộ repository khỏi pointcut có thể mất event cần kiểm toán. Tốt hơn phân loại:

- **Audit sink writes:** helper nội bộ nên được loại khỏi instrumentation tương ứng, hoặc có guard chuyên biệt.
- **Business repository calls:** có thể vẫn cần advice.
- **Authorization lookups:** có thể audit theo một chính sách khác, tránh leak dữ liệu nhạy cảm.
- **Operational logging:** cần quy tắc dữ liệu/độ sâu riêng.

Exclusion nên **bảo toàn yêu cầu nghiệp vụ**, không chỉ làm hết stack overflow.

### 15.2. Thứ tự aspect thay đổi vòng tái nhập

Nếu một logging aspect ở ngoài security aspect, lời gọi kiểm quyền có thể tạo log trước khi quyền được xác nhận. Nếu security ở ngoài, nó có thể từ chối trước khi log bên trong bắt đầu. Muốn ghi nhận cả attempt bị từ chối, cần chọn vị trí có thể nhìn thấy nhánh ấy và bảo vệ dữ liệu nhạy cảm.

## 16. Reentrancy guard và cờ “đang trong cflow”

Một số mô hình pointcut hỗ trợ điều kiện liên quan **control flow**, thường được mô tả bằng các khái niệm như “đang ở trong luồng điều khiển do join point X khởi tạo”. Trong công cụ có hỗ trợ, nó có thể giúp chọn/bỏ chọn điểm theo call stack động.

Ví dụ **mã giả**, không phải cú pháp chung:

```text
auditBusinessPointcuts
AND NOT withinControlFlow(auditLoggerEmission)
```

Mục tiêu là không audit những lời gọi phát sinh từ chính việc ghi audit.

Các điểm cần chú ý:

- Loại theo **control flow** khác loại theo **declaring type** hoặc tên method.
- Một helper có thể được gọi cả từ business lẫn từ advice; loại theo ngữ cảnh có thể phù hợp hơn loại hoàn toàn theo class.
- Một số pointcut control-flow có overhead runtime.
- Control flow trên một call stack đồng bộ không tự tương đương **logical flow** của task bất đồng bộ.
- Một mô hình cflow có thể bao cả chính điểm bắt đầu hoặc chỉ các điểm nằm sâu bên trong; cần đọc semantics cụ thể.
- Dynamic pointcut không loại bỏ nhu cầu viết test cho recursion và bypass.

### 16.1. Phân biệt cflow và thread-local guard

Thread-local guard là cách **implementation** theo thread trong một ví dụ. Control-flow pointcut là khả năng **ngôn ngữ/engine AOP** trong một số công cụ. Hai thứ có thể cùng ý tưởng nhưng **không tương đương về ngữ nghĩa** trong mọi môi trường, đặc biệt khi có nested join points, async và class loader.

## 17. Lời gọi callback làm tái nhập một cách bất ngờ

Một business method có thể gọi callback được truyền vào:

```text
Business.execute()
  -> listener.onEvent()
      -> Business.execute()    <-- quay lại trước khi lần đầu thoát
```

Kể cả không có aspect, đây đã là **reentrancy**. AOP thêm một lớp can thiệp có thể:

- Làm callback thực hiện dưới lock của advice.
- Tăng số lần log hoặc metric.
- Gây kiểm tra state ở thời điểm object chưa ổn định.
- Kích hoạt transaction lồng nhau.
- Ném lỗi ở callback rồi được advice ngoài xử lý theo cách không ngờ.

Nếu object chỉ giữ invariant tại public method exit, callback được gọi giữa mutation có thể quan sát trạng thái trung gian. Vì vậy hợp đồng callback và điểm phát sự kiện phải rõ.

### 17.1. Không gọi callback không đáng tin dưới lock

Một advice giữ lock rồi gọi plugin callback có thể tạo chu trình khóa hoặc reentrancy. Tốt hơn cân nhắc sao chép event, thoát critical section, rồi dispatch callback theo giao thức phù hợp, nếu invariant và ordering cho phép.

## 18. Đồng bộ hóa: synchronized là reentrant nhưng không chống mọi lỗi

Java `synchronized` cho phép cùng một thread vào lại monitor mà nó đang giữ. Điều này hữu ích cho một số thiết kế recursion nhưng cũng có nghĩa:

```text
synchronized advice
  -> synchronized advice
      -> synchronized advice
          ...
```

vẫn có thể tái nhập trên **cùng thread**, không bị chặn bởi monitor.

Một số lỗi khác:

- **Deadlock:** Aspect A giữ lock X rồi gọi B lấy Y; luồng khác giữ Y rồi muốn X.
- **Lock convoy:** nhiều lời gọi nhỏ chờ cùng monitor vì advice dùng một lock toàn cục.
- **Priority inversion:** thao tác quan trọng đợi I/O logging dưới lock.
- **Callback under lock:** callback tự gọi lại method hoặc tham gia vào chu trình khóa khác.
- **Lock mismatch:** `synchronized(proxy)` không đồng nhất monitor với `synchronized(target)` trong mô hình proxy giữ target riêng.

Không nên thêm synchronized vào toàn bộ advice để “sửa recursion” mà không vẽ call graph và ownership của lock.

## 19. Transaction lồng nhau và trạng thái nghiệp vụ

Một advice giao dịch có thể mở scope khi vào method và đóng scope khi thoát. Khi method được advice gọi một operation khác cũng cần transaction, hệ thống có **nested invocation**.

Những câu hỏi phải giải quyết:

- Inner operation tham gia transaction hiện tại hay mở một scope độc lập?
- Rollback của inner có buộc outer rollback không?
- Khi inner bị short-circuit, outer transaction còn hợp lệ không?
- Retry mở transaction mới mỗi attempt hay dùng transaction cũ?
- Exception từ after advice có xảy ra **sau khi commit** không?
- Một lời gọi đi vòng proxy có bỏ qua transaction boundary mong đợi không?

**Không có câu trả lời chung**: propagation và nested transaction semantics thuộc hạ tầng giao dịch cụ thể. AOP chỉ mang cách kết hợp logic; nó không tự quyết định atomicity.

### 19.1. Không lấy “depth>0” làm bằng chứng đã có transaction

Một method được lồng trong lời gọi khác không có nghĩa nó thuộc cùng transaction hay mọi side effect đều được bảo vệ. Depth của AOP call stack và transaction state là hai loại trạng thái khác nhau.

## 20. Ngoại lệ từ advice tự can thiệp và cách bảo toàn lỗi gốc

Giả sử business ném lỗi `E1`. Advice after-throwing ghi log, nhưng logger cũng bị intercept, tạo lỗi `E2`.

```text
Business throws E1
  -> ErrorAdvice
       -> LoggingAdvice reenters
            -> Logger throws E2
  -> Caller sees E2?
```

Nếu code không quản lý rõ, caller có thể chỉ thấy E2, còn E1 bị che.

Các lựa chọn thiết kế:

- Nếu logging **best effort**, bắt đúng lỗi phụ trợ trong phạm vi logging, giữ E1.
- Nếu audit là **bắt buộc**, có thể phải công bố một lỗi tổng hợp hoặc trạng thái fail-closed, nhưng không tùy ý đánh mất thông tin E1.
- Nếu muốn wrap, giữ original trong `cause`.
- Nếu có lỗi phụ, cân nhắc `suppressed` theo ngữ nghĩa Java phù hợp.
- Không bắt `Throwable` rộng rồi trả thành công trừ khi có hợp đồng đặc biệt và lý do hợp lệ.

### 20.1. Finally và dọn guard

Một cleanup `finally` tự ném exception có thể che lỗi cũ trong Java. Vì vậy dọn context nên **đơn giản, đáng tin và ít side effect**, không đưa I/O hoặc logic phức tạp vào đó khi không cần.

### 20.2. Exception path có thể làm lệch depth

Nếu decrement depth chỉ nằm trong đường return bình thường, một exception sẽ làm depth còn cao. Invocation tiếp theo trên cùng thread có thể bị đánh nhầm là nested, hoặc bị guard bỏ qua.

Dùng `finally` để khôi phục depth, bao gồm cả khi target hoặc advice khác ném lỗi.

## 21. Lời gọi lồng nhau trong lập trình bất đồng bộ

Với method trả `CompletableFuture`, có ít nhất hai chiều “lồng nhau”:

1. **Call-stack nesting:** invocation đồng bộ trên một thread trước khi method trả.
2. **Logical-operation nesting:** một task/callback được tạo trong operation trước nhưng hoàn tất ở thread khác về sau.

Một advice after-returning quanh method trả Future có thể chạy **trước khi Future hoàn tất**. Vì vậy:

- Depth trong `ThreadLocal` được gỡ khi method trả, dù logical task vẫn hoạt động.
- Callback có thể chạy trên thread khác mà không có context gốc.
- Exception ở completion stage không nhất thiết đi qua catch đồng bộ ở call site.
- Một callback có thể tạo một operation mới, khiến concept parent-child theo logical trace khác call stack.
- Scheduler có thể thực thi callback ngay trên thread hiện tại hoặc thread khác tùy API và trạng thái stage.

### 21.1. Dùng explicit correlation context

Nếu muốn trace nghiệp vụ xuyên async:

```text
traceId = request identity
spanId = current operation
parentSpanId = creating operation
taskId = asynchronous work item
```

Khi tạo task, truyền một **snapshot context** phù hợp vào callback hoặc executor. Định nghĩa parent-child theo **lifecycle task**, không dựa duy nhất vào depth của ThreadLocal.

### 21.2. Đừng sao chép cờ guard không suy nghĩ

Nếu copy nguyên `emitting=true` sang async task, task có thể tắt instrumentation dù nó là operation nghiệp vụ độc lập. Guard cho **đường emission hiện tại** thường có lifetime ngắn và không được truyền như trace ID thông thường.

Một context propagation thiết kế tốt phân biệt thông tin **nên mang qua thread** với các guard nội bộ **không nên rò ra scope khác**.

## 22. Virtual threads và khả năng tương thích mô hình context

Java 17 là nền tảng của ví dụ runnable. Các khả năng thread mới của Java ở các phiên bản sau có thể thay đổi chiến lược hiệu năng và context propagation, nhưng **không làm biến mất vấn đề reentrancy**.

Dù dùng thread nền tảng, thread pool, virtual thread hoặc async stage, luôn cần giải đáp:

- Một logical invocation có đổi thread không?
- Guard được gắn vào thread hay logical operation?
- Có khả năng executor tái sử dụng thread không?
- Cleanup có diễn ra khi task cancel/timeout không?
- Nested business calls có được instrumentation đầy đủ không?

Tránh đồng nhất mô hình invocation với một lựa chọn scheduling cụ thể.

## 23. Hiệu năng: recursion instrumentation có thể nhân tải đột biến

Một advice tưởng như chỉ thêm một log line vào mỗi method có thể làm chi phí tăng đáng kể khi chính logger nằm trong tập bị chọn.

Ví dụ trực giác:

```text
Một business call -> 1 log
Log method lại được advice -> thêm 1 log
Mỗi log mới lại được advice -> thêm log ...
```

Với chu trình không có điều kiện dừng, không phải overhead tuyến tính; hệ thống có thể nhanh chóng cạn stack, CPU hoặc memory.

Kể cả không vô hạn, instrumentation từng nested helper cũng có thể gây:

- Quá nhiều log/event.
- Trùng thời lượng inclusive.
- Tăng allocations và GC.
- Contention trên sink/logger.
- Latency cao ở hot path.
- Lộ thêm dữ liệu từ các method không chủ ý audit.
- Giữ stack/context quá lâu.

### 23.1. Không đo overhead bằng cách in stdout trong hot loop

`System.out.println` có thể áp đảo chi phí proxy/pointcut. Muốn benchmark dispatch cần dùng workload đại diện, warm-up, đo throughput/latency và tách chi phí I/O. Tuy nhiên trong ví dụ học tập, stdout giúp kiểm **thứ tự sự kiện**, không dùng làm số đo hiệu năng production.

## 24. Quy trình điều tra khi log lặp vô hạn

1. **Dừng hoặc cô lập luồng lỗi** trong môi trường an toàn nếu hệ thống đang tạo storm.
2. **Xác định điểm vào ban đầu**: business method nào khiến advice bắt đầu?
3. **Tìm chuỗi lặp** trong stack trace: advice → logger/metric/audit → advice.
4. **Vẽ call graph** của các helper mà advice gọi.
5. **Đối chiếu pointcut và weaving scope**: logger/helper có bị chọn ngoài ý định?
6. **Kiểm tra thứ tự aspect**: advice khác có gọi helper tạo vòng không?
7. **Kiểm tra around continuation**: có gọi `proceed` nhiều lần không?
8. **Kiểm tra guard**: có đặt đúng vị trí, reset bằng finally và scope đủ hẹp không?
9. **Kiểm tra self-invocation**: lời gọi nào qua proxy, lời nào trực tiếp?
10. **Tạo test nhỏ** chỉ chạy một operation và thu event vào bộ đệm.
11. **Kiểm thử đường lỗi**: logging sink failure, target exception, cleanup.
12. **So sánh before/after** bằng tập join point được match, sự kiện và số lần target chạy.

Không thử “sửa” bằng cách tăng stack size rồi coi hệ thống an toàn. Tăng tài nguyên có thể chỉ trì hoãn việc cạn kiệt do vòng lặp.

### 24.1. Dấu hiệu trong stack trace

Có thể thấy một mẫu frame lặp:

```text
Interceptor.invoke(...)
Logger.write(...)
Interceptor.invoke(...)
Logger.write(...)
...
```

Đây là **stack trace giả lập mang tính minh họa**, không phải output cam kết của JDK. Tên class/frame cụ thể phụ thuộc proxy/weaver, compiler và runtime.

## 25. Quy trình điều tra khi nested advice bị thiếu

1. Xác định method ngoài và trong có thuộc tập pointcut không.
2. Xác định receiver ở lời gọi trong: proxy, target hay subclass instance.
3. Kiểm tra có sử dụng `this.inner()` trên target riêng không.
4. Kiểm tra guard có bỏ **mọi depth>0** hay không.
5. Kiểm tra exclusion quá rộng có loại helper nghiệp vụ không.
6. Kiểm tra dynamic guard theo args/type/control flow.
7. Kiểm tra around ngoài có gọi `proceed` không.
8. Kiểm tra error/short-circuit có dừng đường đi trước inner không.
9. Kiểm tra class loader hoặc bytecode weaving coverage nếu không dùng proxy.
10. Dùng event collector khẳng định **số lần vào mỗi join point**, không chỉ sự tồn tại của một log.

Có lúc thiếu nested advice là **đúng yêu cầu** để tránh duplicate audit. Nhưng quyết định ấy phải được mô tả như một chính sách intentional, không là hệ quả vô tình của một cờ guard.

## 26. Ma trận kiểm thử tái nhập và lời gọi lồng nhau

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Một method qua proxy | Advice enter/exit đúng một lần |
| Outer gọi inner qua proxy | Inner có advice nếu policy yêu cầu |
| Outer gọi `this.inner` trên raw target | Hiểu và xác nhận bypass nếu dùng interface delegation |
| Advice gọi logger cũng thuộc pointcut | Không có infinite self-interception |
| Guard đang phát trace | Chỉ skip đường trace tự phát sinh |
| Business nested khi không phát trace | Không bị guard loại nhầm |
| Target ném exception | Depth/guard được cleanup, lỗi gốc giữ đúng |
| Logger ném exception | Chính sách lỗi phụ trợ được áp dụng, guard không kẹt |
| Một invocation sau exception | Depth trở về 0/giá trị nền |
| Direct raw target call | Không tạo proxy advice ngoài ý định |
| Recursion hợp lệ nhiều mức | Context từng frame độc lập |
| Hai thread đồng thời | Không trộn trace/depth/request state |
| Async continuation ở thread khác | Context được truyền theo task nếu yêu cầu |
| Retry nhiều attempt | Đếm đúng logical request và attempts |
| Multiple aspects | Không tạo vòng audit ↔ security/metrics |
| Callback reenters operation | Không phá invariant, lock hoặc state |
| Instrumentation helper đổi tên | Exclusion/test vẫn phát hiện chu trình mới |
| Disable guard trong test kiểm soát | Chỉ dùng mô phỏng/cấu trúc kiểm tra an toàn, không chạy vòng vô hạn thật |

### 26.1. Test theo event sequence

Trong một test đồng bộ, thu event vào danh sách:

```text
outer.enter[0]
  inner.enter[1]
  inner.exit[1]
outer.exit[0]
```

Nếu guard chỉ chặn trace self-interception, các event outer và inner vẫn hiện diện. Ngoài thứ tự, cần assert:

- Số lần target thật chạy.
- Số lần advice phát trace.
- Số lần guard skip.
- Không để depth lệch sau lỗi.
- Không có event extra do helper tự kích hoạt.

### 26.2. Test idempotency của cleanup

Nếu cleanup được gọi lặp do lỗi hoặc retry, nó phải bảo toàn tính nhất quán. Ví dụ `ThreadLocal.remove()` không ném lỗi vì chưa có giá trị trong tình huống thông thường, nhưng một callback cleanup tùy chỉnh có thể không idempotent. Hãy thiết kế lifecycle rõ.

### 26.3. Tránh unit test chỉ kiểm kết quả return

Một operation có thể trả đúng `"OK"` dù advice log bị nhân đôi mười lần hoặc audit bị bỏ qua ở nested call. Cần test **hành vi aspect** độc lập với kết quả nghiệp vụ.

## 27. Những sai lầm phổ biến

**“Lời gọi lồng nhau là recursion.”** Không. Recursion cần chu trình gọi; nested call đơn giản không nhất thiết quay lại cùng method.

**“Mọi recursion đều là bug.”** Không. Recursion có điểm dừng và state đúng là hợp lệ.

**“Aspect tự can thiệp chỉ xảy ra khi advice gọi chính method của nó.”** Không. Chu trình có thể qua logger, repository, callback hoặc aspect khác.

**“Một cờ boolean global giải quyết tái nhập.”** Nguy hiểm: nó có thể làm thread khác bỏ qua advice và tạo race.

**“Chỉ dùng synchronized là chặn được self-interception.”** Sai: Java monitor có tính reentrant với cùng thread.

**“Bật guard suốt proceed là an toàn.”** Có thể làm mất nested business advice hợp lệ.

**“Guard chỉ cần set true mà không reset nếu exception.”** Sai: context còn kẹt sẽ gây lỗi lâu dài trên thread tái sử dụng.

**“ThreadLocal tự truyền đúng qua mọi async task.”** Sai. Context propagation phải thiết kế theo task/thread boundary.

**“Thấy depth=2 nghĩa là cùng một request ở mọi trường hợp.”** Không. Depth không phải trace ID; retry và async có semantics khác.

**“Self-invocation luôn đi qua advice.”** Không với proxy delegation vào target riêng; receiver quyết định đường gọi.

**“Self-invocation luôn bỏ qua advice.”** Cũng không đúng cho mọi kỹ thuật weaving hoặc subclass receiver.

**“Loại toàn bộ helper khỏi pointcut là luôn tốt.”** Chưa chắc: có helper thật sự cần audit. Phạm vi phải dựa vào chính sách.

**“Ngoại lệ từ logger có thể tùy ý thay business exception.”** Không nếu hợp đồng là observability best effort; phải giữ primary cause theo policy.

**“Log trùng nghĩa business đã chạy trùng.”** Không nhất thiết: một operation có thể được advice nhiều tầng mà body chỉ chạy một lần. Cần đếm riêng business invocation.

**“Không có log inner nghĩa inner không chạy.”** Sai khi inner được gọi trực tiếp target hoặc bị guard/exclusion loại.

**“Chỉnh wildcard là sửa được mọi recursion.”** Nếu chu trình nằm ở runtime condition/retry hoặc nhiều aspect, cần phân tích call graph và scope.

## 28. Bài tập có đáp án

### Bài 1 — Logger tự kích hoạt

Advice dùng `logger.write()`, pointcut lại chọn mọi execution của method có tên `write` trong package chứa logger. Có thể xảy ra gì?

**Đáp án:** logger có thể bị cùng advice kích hoạt lại, tạo recursion hoặc event storm. Cần giới hạn pointcut, loại đúng logger helper hoặc guard đường emission.

### Bài 2 — Nested calls có bị mất vì guard?

Một interceptor đặt `active=true` trước `proceed` và mọi method sau thấy active đều bỏ advice. `outer` gọi `inner` qua proxy. `inner` có được audit không?

**Đáp án:** Có thể **không**, vì cờ quá rộng. Nếu business policy cần audit inner, phải thu hẹp guard vào đường tự can thiệp, không tắt toàn bộ nested instrumentation.

### Bài 3 — Timer bị ghi đè

Aspect singleton dùng field `startTime`; outer và inner đều được advice. Vì sao duration outer có thể sai?

**Đáp án:** inner ghi đè mốc outer. Mỗi invocation cần local snapshot hoặc frame/context riêng.

### Bài 4 — `synchronized`

Advice đồng bộ hóa trên một monitor nhưng tự gọi lại cùng advice trong một thread. Monitor có tự ngăn recursion không?

**Đáp án:** Không. Java monitor là reentrant theo thread. Vẫn cần exclusion/guard/điểm dừng.

### Bài 5 — Handler lỗi rồi depth không trở về 0

Code chỉ giảm depth sau khi `proceed` trả bình thường. Nếu business ném lỗi, request sau sẽ thế nào?

**Đáp án:** Depth còn sai, có thể bị coi là nested và lọc nhầm. Cleanup cần trong `finally`.

### Bài 6 — Proxy và `this.inner()`

Caller qua interface proxy gọi `target.outer()`; bên trong target gọi `this.inner()`. Handler của proxy có chắc nhận `inner` không?

**Đáp án:** Không trong mô hình proxy ủy quyền vào target riêng. Lời gọi nội bộ chạy trên target, không quay lại proxy.

### Bài 7 — Cflow và async

Một pointcut loại những thao tác “đang trong call stack của logging”. Một callback async chạy ở thread khác. Có thể giả định bộ lọc cflow thấy cùng stack không?

**Đáp án:** Không. Logical async flow và đồng bộ call stack khác nhau. Phải xem semantics công cụ và context propagation.

### Bài 8 — Retry và số lần side effect

Retry ngoài chạy `proceed` hai lần. Inner advice ghi “save succeeded” mỗi attempt. Có thể có bao nhiêu audit event và business execution?

**Đáp án:** Tùy nơi audit nằm, có thể có hai lần inner advice và hai business attempts. Contract phải phân biệt logical request và attempt, tránh giả định đúng một lần.

### Bài 9 — Callback tái nhập dưới lock

Business giữ lock rồi gọi plugin callback; callback gọi ngược business. Nguy cơ?

**Đáp án:** Reentrancy vào trạng thái chưa ổn định, đệ quy không dừng hoặc deadlock qua lock khác. Phải xác định callback boundary và thiết kế trạng thái/lock phù hợp.

### Bài 10 — Trace guard cần truyền sang Future?

Một advice set `emitting=true` khi ghi log đồng bộ rồi tạo async task nghiệp vụ. Có nên truyền cờ này sang task?

**Đáp án:** Thường không. Đây là guard nội bộ cho đường emission ngắn, không phải thuộc tính nghiệp vụ. Trace ID hoặc correlation context có thể cần truyền, nhưng guard phải đúng vòng đời.

## 29. Checklist thiết kế AOP an toàn với tái nhập

- [ ] Hiểu rõ call graph gồm cả method mà **advice tự gọi**.
- [ ] Phân biệt nested call, recursion, reentrancy và self-invocation bypass.
- [ ] Xác định join-point kind, pointcut scope và interception boundary.
- [ ] Không đưa logger/audit sink/metrics helper vào pointcut ngoài chủ đích.
- [ ] Exclusion dựa trên chính sách và có kiểm thử, không chỉ wildcard tùy tiện.
- [ ] Guard runtime chỉ ngăn đường tái nhập cần thiết.
- [ ] Không tắt mọi nested business advice bằng một cờ “inside aspect”.
- [ ] Dùng state per invocation/frame khi cần depth, timing, snapshot.
- [ ] Không lưu mutable per-call state vào singleton field chung.
- [ ] Dọn guard và depth bằng `finally` ngay cả khi có exception.
- [ ] Nếu guard lồng nhau, khôi phục đúng state scope ngoài.
- [ ] Dùng `ThreadLocal` với cleanup và hiểu giới hạn thread pool/async.
- [ ] Không coi thread ID/depth là correlation ID duy nhất.
- [ ] Có policy rõ với logging/audit sink failure và primary exception.
- [ ] Không ghi dữ liệu nhạy cảm trong telemetry để debug recursion.
- [ ] Có test một lời gọi đơn, nested call, self-call qua proxy/direct.
- [ ] Có test business error và logger error.
- [ ] Có test hai thread chạy đồng thời và task async khi phù hợp.
- [ ] Có test retry/proceed nhiều lần và idempotency.
- [ ] Có test callback dưới lock hoặc trong transaction nếu tồn tại.
- [ ] Có test nhiều aspect kết hợp tránh vòng A → B → A.
- [ ] Có trace riêng cho business count, advice count và guard skip.
- [ ] Đo overhead trên workload thật, không chỉ dựa vào stdout demo.
- [ ] Biết rollback/disable instrumentation khi phát sinh recursion storm.
- [ ] Đã mô tả những nested invocation bị bỏ qua **có chủ đích** trong hợp đồng aspect.

## 30. Kết luận

**Tái nhập** xảy ra khi cùng logic được đi vào lần nữa trước khi lần trước hoàn tất; **lời gọi lồng nhau** là hình thức tổ chức call stack hợp lệ, còn **aspect tự can thiệp** là tình huống advice kích hoạt một đường gọi lại bị aspect chọn. Ba khái niệm liên quan nhưng không đồng nhất. Đồng thời, với proxy dựa trên target riêng, một `this.inner()` có thể **bypass** interception — vấn đề trái chiều với self-interception quá mức.

Để thiết kế đúng, hãy đặt câu hỏi: **ai gọi ai, receiver nào thực sự chạy, join point nào được chọn, state thuộc invocation nào và guard cần chặn chính xác đường nào?** Ưu tiên pointcut rõ ràng, loại trừ helper nội bộ có căn cứ, dùng guard hẹp được dọn trong `finally`, quản lý state theo frame/invocation, và tách context cho async.

Một hệ thống AOP đáng tin không chỉ tránh stack overflow; nó còn **giữ đủ nested advice hợp lệ**, không đếm trùng request, không che lỗi gốc, không rò ngữ cảnh giữa thread và có kiểm thử chứng minh cả những đường **phải được can thiệp** lẫn những đường **cố ý không can thiệp**.
