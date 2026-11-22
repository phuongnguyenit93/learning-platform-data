# Loại trừ mã của chính aspect để tránh đệ quy trong AOP

## 1. Vấn đề cốt lõi

Trong **Aspect-Oriented Programming (AOP)**, một **aspect** chứa logic xử lý mối quan tâm xuyên suốt như logging, audit, metrics hoặc kiểm tra quyền. **Pointcut** lựa chọn các **join point** thuộc mô hình của công cụ; **advice** được thực thi khi một join point phù hợp xảy ra.

Một lỗi thường gặp: advice muốn quan sát rất nhiều method, nhưng **mã mà advice tự thực thi** cũng tạo ra join point phù hợp. Điều này có thể khiến aspect **tự kích hoạt chính nó** nhiều lần.

Ví dụ:

```text
Caller -> Business.save()
  -> LoggingAdvice.before()
      -> Logger.write()
          -> LoggingAdvice.before()
              -> Logger.write()
                  -> LoggingAdvice.before()
                      ...
```

Nếu không có điều kiện dừng, chuỗi có thể gây `StackOverflowError`, tăng đột biến CPU/log, hoặc bão sự kiện trong bộ ghi audit.

**Loại trừ mã của chính aspect** là một nhóm kỹ thuật ngăn những join point phát sinh từ đường hoạt động nội bộ của aspect bị advice của chính nó chọn lại ngoài ý muốn. Nhưng phải làm chính xác: loại trừ **quá hẹp** không hết đệ quy; loại trừ **quá rộng** làm mất advice của những lời gọi nghiệp vụ lồng nhau cần quan sát.

Bài tập trung vào AOP nói chung từ cơ bản đến nâng cao. Các ví dụ cú pháp **AspectJ** được nêu rõ là ví dụ **một ngôn ngữ pointcut cụ thể**, không phải quy tắc của mọi công cụ. Ví dụ Java 17 thuần cuối bài minh họa hai chiến lược lọc mà không cần công cụ weaving bên ngoài.

## 2. Mục tiêu học tập

Sau bài này, người học có thể:

1. Xác định đường đệ quy bắt đầu ở advice và quay về advice qua một hoặc nhiều helper.
2. Phân biệt **lời gọi lồng nhau hợp lệ** với **self-interception** ngoài ý muốn.
3. Phân biệt loại trừ theo **vị trí khai báo mã (lexical scope)**, theo **kiểu/nhóm method** và theo **control flow**.
4. Đọc đúng ý nghĩa của `within`, `withincode`, `adviceexecution`, `cflow` và `cflowbelow` trong cú pháp công cụ có hỗ trợ.
5. Hiểu tại sao loại trừ call site bên trong aspect có thể không loại trừ **method execution trong helper ở class khác**.
6. Dùng guard runtime phạm vi hẹp và khôi phục trạng thái khi có exception.
7. Giữ lại interception cho business call lồng nhau, không vô hiệu hóa toàn bộ advice.
8. Kiểm thử cả những điểm **phải loại** và những điểm **vẫn phải áp dụng**.
9. Thiết kế an toàn khi có nhiều aspect, callback, async, multi-thread và lỗi từ logging.

## 3. Những khái niệm phải tách bạch

| Khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **Join point** | Loại sự kiện nào có thể nhận advice: call, execution hay loại khác? |
| **Pointcut** | Tại sự kiện nào điều kiện lựa chọn đúng? |
| **Shadow** | Vị trí trong chương trình có thể tạo join point theo mô hình weaving tĩnh |
| **Advice execution** | Bản thân phần thực thi advice có được mô hình hóa thành join point không? |
| **Lexical scope** | Mã tạo join point được khai báo **ở đâu**? |
| **Control flow** | Khi join point xảy ra, stack động đang nằm **trong lời gọi nào**? |
| **Helper/sink** | Hàm phục vụ advice: log, metrics, audit writer, serializer... |
| **Self-interception** | Advice gọi một thao tác lại bị cùng advice hoặc chain liên quan chặn |
| **Recursion** | Call graph quay lại thành phần đang chạy trước khi kết thúc |
| **Reentrancy guard** | Điều kiện runtime ngăn đường tái nhập không mong muốn |
| **Self-invocation bypass** | Target gọi nội bộ mà không đi qua proxy, làm advice **không chạy** |
| **Proceed** | Around advice tiếp tục phần bên trong (nếu công cụ hỗ trợ) |

**Mọi self-interception có thể dẫn tới tái nhập**, nhưng không phải lần tái nhập nào cũng gây vòng vô hạn. Ví dụ một logger có counter giới hạn có thể thoát, song hệ thống vẫn ghi log lặp không đúng mục đích.

**Nested business calls** như `checkout → reserve → charge` có thể hoàn toàn hợp lệ; không được lọc bỏ chỉ vì chúng chạy khi advice ngoài chưa kết thúc.

## 4. Call graph giúp tìm nguồn đệ quy

Trước khi sửa pointcut, hãy vẽ tất cả cạnh mà advice tạo ra:

```text
Business.service()
    |
    v
TraceAspect.before()
    |
    +--> TraceFormatter.format(args)
    |         |
    |         +--> args.toString()
    |
    +--> AuditSink.write(event)
              |
              +--> Repository.insertAudit(event)
```

Nếu pointcut đang lựa chọn toàn bộ execution của `toString`, `write` hoặc `insertAudit`, những method đó có thể gọi lại `TraceAspect.before`.

Điểm cần xem:

- **Từ advice đi tới helper nào?**
- **Helper thuộc class/package nào?**
- **Join-point kind** của pointcut là call hay execution?
- **Vị trí lexical** của điểm được chọn có nằm trong aspect không?
- **Control flow** tại điểm ấy có bắt nguồn từ advice không?
- Có guard điều kiện dừng không?
- Có aspect thứ hai làm đường vòng trở về aspect thứ nhất không?

Không cần thấy một câu lệnh `TraceAspect.before()` gọi trực tiếp chính nó mới có recursion. Một chu trình dài qua hai ba class vẫn là recursion.

## 5. Hai vị trí khác nhau: điểm gọi và phần thực thi

Giả sử advice trong `TraceAspect` gọi `AuditSink.write`:

```text
TraceAspect code                    AuditSink code
+---------------------+             +-----------------------+
| sink.write(event) --+------------>| write(event)          |
|         ^           |             |   persist(event)      |
|       call site     |             |       ^ execution     |
+---------------------+             +-----------------------+
```

Một pointcut chọn **method-call join point** ở dòng `sink.write(event)` có thể thấy điểm ấy nằm **trong mã aspect**.

Một pointcut chọn **method-execution join point** của `AuditSink.write` lại có điểm xảy ra trong **mã được khai báo ở AuditSink**, không phải lexical body của aspect.

Vì vậy:

- Loại trừ mã **được khai báo trong aspect** có thể chặn call site bên trái.
- Nó **không tự động loại** mọi method execution của helper bên phải nếu helper thuộc class khác.
- Muốn loại cả đường helper do advice phát sinh, có thể cần điều kiện control flow hoặc exclusion chính xác hơn theo method/type.

Điểm khác biệt này đặc biệt quan trọng khi một pointcut rộng chọn `execution(* *(..))` hoặc cùng lúc chọn nhiều loại join point.

## 6. Cách phòng ngừa thứ nhất: thu hẹp pointcut theo nghiệp vụ

Phương án tốt thường là **chọn đúng những thao tác thực sự cần advice**, thay vì bắt mọi method rồi loại ra hàng loạt.

Ví dụ mục tiêu là audit khi có thao tác ghi đơn hàng:

```text
Nên chọn:
  OrderService.submit(...)
  PaymentService.capture(...)
  InventoryService.reserve(...)

Không nhất thiết chọn:
  AuditSink.write(...)
  TraceFormatter.format(...)
  JsonEncoder.encode(...)
  Logger.debug(...)
```

Các dòng này là **mô tả lựa chọn**, không phải cú pháp DSL.

Ưu điểm:

- Tập điểm khớp nhỏ, dễ review và kiểm thử.
- Ít khả năng aspect can thiệp vào dependency của chính nó.
- Giảm lượng event và overhead.
- Ít phụ thuộc guard động.
- Dễ lập báo cáo "advised/unadvised" theo use case.

Nhược điểm:

- Khi thêm nghiệp vụ mới, cần cập nhật chính sách lựa chọn.
- Một số mối quan tâm như profiling toàn ứng dụng thực sự cần phạm vi rộng.
- Một helper có thể vừa được advice sử dụng, vừa có lời gọi trực tiếp từ nghiệp vụ cần quan sát.

Với helper dùng hai vai trò khác nhau, loại nó **vĩnh viễn** theo class có thể quá mạnh; lúc này điều kiện theo **nguồn phát sinh lời gọi** có giá trị.

## 7. Loại trừ theo vị trí lexical của mã

Một số pointcut language có điều kiện "join point nằm trong vùng mã được khai báo ở kiểu X", thường gọi là **lexical selection/exclusion**.

Ý tưởng:

```text
businessJoinPoints
AND NOT codeLexicallyInside(MyAspect)
```

Điều này hữu ích nếu advice gọi các phương thức ngay trong body aspect và những call site ấy không được phép tạo advice tiếp.

**Nhưng lexical exclusion không đồng nghĩa loại trừ mọi thao tác xảy ra trong quá trình advice đang chạy.** Một method execution của `AuditSink` được khai báo trong `AuditSink`, dù do aspect gọi tới, vẫn nằm ngoài body của `MyAspect`.

### 7.1. Lexical và dynamic khác nhau

Một vị trí source có thể được gọi trong nhiều control flow; lexical scope của nó **không đổi** khi caller thay đổi.

```text
Business -> SharedHelper.execute()   [lexical: SharedHelper]
Aspect   -> SharedHelper.execute()   [lexical: SharedHelper]
```

Cả hai có cùng execution method được khai báo trong SharedHelper. Nếu muốn chỉ bỏ lời gọi do aspect gây ra nhưng vẫn audit lời gọi từ business, điều kiện dựa **chỉ trên kiểu chứa mã** thường không đủ.

## 8. Cú pháp minh họa AspectJ: `within`

**Phần này dùng cú pháp AspectJ cụ thể**, không phải Java `javac` thuần và không áp dụng mặc nhiên cho các hệ thống AOP khác.

Với cú pháp này, `within(TypePattern)` chọn các join point được gắn với mã **được khai báo trong** những type khớp mẫu.

Mẫu minh họa:

```java
aspect TraceAspect {
    pointcut observedCalls():
        call(* *(..)) && !within(TraceAspect);

    before(): observedCalls() {
        System.out.println("observed call");
    }
}
```

Đây là **mảnh ngôn ngữ AspectJ** cần compiler/weaver tương ứng; không chạy độc lập bằng `javac TraceAspect.java`. Nó giải thích một tư tưởng: chọn lời gọi method nhưng **không chọn** call site nằm trong mã khai báo của `TraceAspect`.

Nếu advice gọi `System.out.println` ngay trong body aspect, call site đó được loại theo lexical scope.

**Giới hạn:** giả sử aspect gọi `AuditSink.write`, mà bên trong `AuditSink.write` gọi `Repository.save`. Những join point của mã trong AuditSink/Repository **không trở thành lexical code trong TraceAspect** chỉ vì được gọi từ advice. Nếu pointcut chọn execution/call ở các vị trí bên ngoài aspect, điều kiện `!within(TraceAspect)` một mình có thể không chặn hết chu trình.

### 8.1. Đừng nhầm `within` với `target`

Một pointcut lọc **kiểu của receiver/target** không giống lọc **vị trí khai báo code**. Một instance của `AuditSink` được gọi trong body aspect nhưng target type vẫn là `AuditSink`. Cần xác định bài toán đang lọc theo **đối tượng**, **vị trí source** hay **luồng thực thi**.

### 8.2. Không có công thức “loại tất cả aspect” cho mọi hệ thống

Mỗi engine có tập join-point kind khác nhau. Với proxy interface chỉ chặn lời gọi vào target được quản lý, body advice có thể không tự được proxy nếu các helper không dùng proxy ấy; nhưng nếu advice gọi một service proxy khác, vẫn có thể tạo vòng. Không được mặc định cần hay không cần `within` ở mọi engine.

## 9. Cú pháp minh họa AspectJ: `withincode`

Trong một số DSL, thay vì loại cả type, có thể loại một method hoặc constructor theo **vị trí lexical được khai báo**.

Trong AspectJ, `withincode(MethodPattern)` ràng buộc join point nằm trong code của method có chữ ký phù hợp.

Ví dụ **mảnh minh họa cú pháp đặc thù**, không phải chương trình chạy độc lập:

```java
pointcut selected():
    call(* *(..))
    && !withincode(* TraceFormatter.format(..));
```

Ý tưởng là loại các call site **nằm trong phần thân** `TraceFormatter.format` theo pattern, không tự loại mọi invocation từ xa có liên quan tới formatter.

**Cảnh báo:** đoạn trên chỉ thể hiện cơ chế lexical. Trong thiết kế thật, cần đối chiếu chữ ký, package, visibility và hạn chế compiler để bảo đảm pattern match đúng method.

### 9.1. Khi nào lexical exclusion đủ?

Nó thường đủ khi:

- Điểm đang chọn là **call site** nằm trong aspect hoặc helper được xác định.
- Vòng đệ quy chỉ được tạo bởi những call site ấy.
- Không có execution join point khác trong helper tiếp tục khớp pointcut.
- Call graph và weaving scope đã được kiểm chứng.
- Negative tests xác nhận không còn self-interception.

Nó có thể chưa đủ nếu **execution join point của helper** vẫn khớp hoặc aspect gọi qua callback/dispatcher tạo đường kiểm soát gián tiếp.

## 10. Loại trừ theo control flow

Khác với lexical filter, **control-flow exclusion** xem một join point có nằm trong quá trình thực thi của một điểm bắt đầu hay không.

Sơ đồ:

```text
Business.save()
   |
   v
TraceAspect advice starts       <-- nguồn của control flow
   |
   +--> Formatter.format()
   |       +--> input.toString()
   |
   +--> Sink.write()
           +--> Repository.append()
   |
   v
Advice ends
```

Một policy có thể nói:

> Đối với aspect tracing này, không áp trace lên những join point xảy ra **trong luồng điều khiển của chính advice đang phát trace**.

Ưu điểm:

- Bao gồm cả helper khác class được gọi sâu qua nhiều tầng.
- Không cần biết hết mọi tên helper khi call graph thay đổi.
- Có thể giữ instrumentation của cùng helper khi helper được gọi **ngoài** control flow advice.

Rủi ro:

- Có thể loại **quá nhiều** join point: một business callback được advice chủ động gọi cũng ở trong control flow ấy.
- Có thể cần guard runtime và overhead động.
- Không nhất thiết tiếp tục có hiệu lực khi công việc chuyển sang **thread/task khác**.
- Phải hiểu có bao gồm chính điểm bắt đầu hay không.
- Có thể tương tác phức tạp với nhiều aspect, recursion, proceed và exception.

**Điểm mấu chốt:** control-flow exclusion giải quyết **đường phát sinh** chứ không chỉ **vị trí khai báo code**, nhưng cần phạm vi hợp đồng rõ.

## 11. Cú pháp minh họa AspectJ: `adviceexecution` và `cflow`

Trong AspectJ có join-point designator `adviceexecution()` để lựa chọn **việc thực thi advice**. Ta có thể kết hợp với `within` để giới hạn **advice thuộc chính aspect cần bảo vệ**.

Ví dụ minh họa dựa trên ngữ nghĩa tài liệu chính thức:

```java
aspect TraceAspect {
    pointcut ownAdvice():
        adviceexecution() && within(TraceAspect);

    before(): call(* *(..)) && !cflow(ownAdvice()) {
        System.out.println("call outside this advice control flow");
    }
}
```

Đây là **AspectJ language snippet**, không phải Java standalone. Ý nghĩa:

1. `ownAdvice()` chỉ những advice-execution join point được khai báo trong `TraceAspect`.
2. `cflow(ownAdvice())` chọn các join point thuộc control flow của việc thực thi advice ấy.
3. `!cflow(ownAdvice())` loại các call join point xảy ra **trong control flow của chính advice**.
4. Nhờ có `within(TraceAspect)` trong `ownAdvice`, chính sách không tự động lấy mọi advice của **mọi aspect** làm gốc control flow.

Mô hình này có thể ngăn cả lời gọi từ advice tới logger và những lời gọi sâu hơn nảy sinh trong quá trình logger xử lý, trong phạm vi **call stack** mà công cụ mô hình hóa.

### 11.1. Vì sao cần giới hạn `ownAdvice`?

Nếu chỉ viết ý tưởng tương tự:

```java
call(* *(..)) && !cflow(adviceexecution())
```

thì có thể loại cả những join point phát sinh khi **aspect khác** đang hoạt động. Điều đó có thể tắt instrumentation hợp lệ một cách không chủ đích.

Tốt hơn phải chỉ ra **nguồn control flow nào thực sự cần tránh**: advice của chính aspect, một logger emission method, hay một nhóm callback.

### 11.2. Tránh diễn giải `cflow` như context async tự động

Trong ngữ nghĩa AspectJ, `cflow(P)` dựa vào luồng điều khiển động của những join point `P`. Không suy rằng một future/callback chạy ở thread khác vẫn mang cùng cflow như call stack đã tạo nó.

Nếu cần theo dõi logical flow qua async, phải xác định **context propagation** và ranh giới task riêng.

### 11.3. Không dùng cú pháp công cụ làm định nghĩa AOP chung

Một số engine proxy không hỗ trợ `adviceexecution` hoặc `cflow`. Khi ấy có thể phải dùng **exclusion dựa trên API/helper**, cấu hình interceptor, guard runtime hoặc thiết kế lại điểm quan sát.

## 12. `cflow` so với `cflowbelow`

Theo ngữ nghĩa của AspectJ:

- `cflow(P)` chọn các join point nằm trong control flow của `P`, **bao gồm** chính join point `P`.
- `cflowbelow(P)` chọn những join point **nằm bên dưới** trong control flow ấy, **không bao gồm** `P`.

Ví dụ:

```text
P starts                         <-- cflow(P) có P
    Q                            <-- cflow(P), cflowbelow(P)
        R                        <-- cflow(P), cflowbelow(P)
P ends
```

Trong bài toán tránh self-interception, việc bỏ qua chính root join point hoặc chỉ các descendant là một quyết định cần kiểm tra chính xác. Không thể thay `cflow` bằng `cflowbelow` theo cảm giác rằng tên gọi “dưới” an toàn hơn.

### 12.1. Phải suy theo *loại* join point

Nếu `P` là `adviceexecution()` còn pointcut cần lọc chỉ chọn `call` join point, root advice-execution join point **không đồng thời là một call join point**. Bởi vậy sự khác biệt bao gồm root có thể không hiện ra trong một số phép kết hợp, nhưng vẫn quan trọng với các tổ hợp pointcut khác.

Không nên dùng các toán tử như `call(..) && execution(..)` rồi tưởng rằng một điểm vừa là call vừa là execution. Thông thường đó là **hai loại join point khác nhau**.

## 13. Dùng exclusion theo helper: khi nào tốt hơn cflow?

Giả sử `AuditAspect` chỉ gọi một helper duy nhất `AuditSink.append` để lưu event. Nếu helper này **không bao giờ cần được aspect audit**, có thể chỉ loại nó theo kiểu/method.

Mô tả:

```text
eligibleBusinessOperations
AND NOT auditSinkMethods
```

Ưu điểm:

- Dễ đọc và dễ lập danh sách loại trừ.
- Có thể xác định ở thời điểm weaving.
- Ít logic runtime hơn một control-flow guard.
- Không loại những lời gọi nghiệp vụ khác xảy ra trong lời gọi advice.

Nhược điểm:

- Nếu `AuditSink.append` được nghiệp vụ dùng trực tiếp và **cần được audit**, loại theo kiểu làm mất coverage đó.
- Nếu helper gọi vào một service **khác** vẫn nằm trong pointcut, exclusion chỉ một helper có thể không đủ với execution join points.
- Helper mới có thể xuất hiện khi refactor, tạo đường vòng mới.

### 13.1. Phối hợp chọn hẹp và guard hẹp

Một chiến lược thực tế:

1. Chọn **nghiệp vụ** trước, không chọn toàn hệ thống vô điều kiện.
2. Loại **các helper instrumentation** nếu chúng không cần advice.
3. Chỉ bổ sung **control-flow exclusion** hoặc guard động khi có những đường tái nhập không thể mô tả an toàn bằng static scope.
4. Kiểm thử những nested business calls vẫn được advice.
5. Theo dõi số lần advice, số lần target và số lần guard skip.

Không nên đồng nhất “ít event hơn” với “đã sửa đúng” nếu mất cả event nghiệp vụ bắt buộc.

## 14. Java 17 runnable: exclusion tĩnh và control-flow guard hẹp

Java 17 không tích hợp một DSL pointcut AOP thống nhất trong ngôn ngữ. Để mô phỏng hành vi, ví dụ này dùng **JDK dynamic proxy**. Hai cơ chế được mô phỏng:

- **Static method exclusion:** method `emit` là helper phát log, nên proxy **không áp advice** cho `emit`.
- **Dynamic flow guard:** method `inspect` vẫn có thể được advice khi caller gọi trực tiếp qua proxy, **nhưng** được bỏ instrumentation khi nó được advice gọi để hỗ trợ việc phát event.

Đặc biệt, `outer` gọi `inner` qua proxy. `inner` vẫn phải được advice **ngay cả khi đã có một outer advice đang hoạt động**, tránh sai lầm “depth lớn hơn 0 thì bỏ qua mọi advice”.

Tạo tệp `AspectExclusionDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AspectExclusionDemo {

    interface Actions {
        String outer(String id);
        String inner(String id);
        void emit(String message);
        String inspect(String key);
    }

    static final class Core implements Actions {
        private Actions self;

        void setSelf(Actions proxy) {
            this.self = proxy;
        }

        @Override
        public String outer(String id) {
            System.out.println("business:outer:" + id);
            return self.inner(id) + "!";
        }

        @Override
        public String inner(String id) {
            System.out.println("business:inner:" + id);
            if ("ERR".equals(id)) {
                throw new IllegalStateException("rejected");
            }
            return "done:" + id;
        }

        @Override
        public void emit(String message) {
            System.out.println("sink:" + message);
        }

        @Override
        public String inspect(String key) {
            System.out.println("business:inspect:" + key);
            return "ok:" + key;
        }
    }

    static Object callTarget(Method method, Core target,
                             Object[] arguments) throws Throwable {
        try {
            return method.invoke(target, arguments);
        } catch (InvocationTargetException wrapper) {
            throw wrapper.getCause();
        }
    }

    public static void main(String[] args) {
        Core target = new Core();

        ThreadLocal<Boolean> emitting =
                ThreadLocal.withInitial(() -> false);
        ThreadLocal<Integer> depth =
                ThreadLocal.withInitial(() -> 0);

        Actions proxy = (Actions) Proxy.newProxyInstance(
                Actions.class.getClassLoader(),
                new Class<?>[] { Actions.class },
                (Object p, Method method, Object[] arguments) -> {
                    String name = method.getName();

                    // Rule 1: helper phát event không nhận advice.
                    if ("emit".equals(name)) {
                        System.out.println("filter:static:emit");
                        return callTarget(method, target, arguments);
                    }

                    // Rule 2: không instrument inspect khi do advice phát ra.
                    if ("inspect".equals(name) && emitting.get()) {
                        System.out.println("filter:flow:inspect");
                        return callTarget(method, target, arguments);
                    }

                    int level = depth.get();
                    System.out.println("advice:before:" + name
                            + ":d=" + level);
                    depth.set(level + 1);

                    try {
                        boolean oldEmitting = emitting.get();
                        emitting.set(true);
                        try {
                            ((Actions) p).emit("enter:" + name);
                            ((Actions) p).inspect("sink-check");
                        } finally {
                            if (oldEmitting) {
                                emitting.set(true);
                            } else {
                                emitting.remove();
                            }
                        }

                        try {
                            Object result = callTarget(method, target, arguments);
                            System.out.println("advice:after:" + name);
                            return result;
                        } catch (Throwable original) {
                            System.out.println("advice:throw:" + name + ":"
                                    + original.getClass().getSimpleName());
                            throw original;
                        }
                    } finally {
                        if (level == 0) {
                            depth.remove();
                        } else {
                            depth.set(level);
                        }
                        System.out.println("advice:finally:" + name
                                + ":d=" + level);
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

        System.out.println("case:inspect-external");
        System.out.println("caller:" + proxy.inspect("external"));

        System.out.println("case:direct");
        System.out.println("caller:" + target.inner("DIRECT"));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac AspectExclusionDemo.java
java AspectExclusionDemo
```

**Đầu ra xác định:**

```text
case:ok
advice:before:outer:d=0
filter:static:emit
sink:enter:outer
filter:flow:inspect
business:inspect:sink-check
business:outer:A
advice:before:inner:d=1
filter:static:emit
sink:enter:inner
filter:flow:inspect
business:inspect:sink-check
business:inner:A
advice:after:inner
advice:finally:inner:d=1
advice:after:outer
advice:finally:outer:d=0
caller:done:A!
case:error
advice:before:outer:d=0
filter:static:emit
sink:enter:outer
filter:flow:inspect
business:inspect:sink-check
business:outer:ERR
advice:before:inner:d=1
filter:static:emit
sink:enter:inner
filter:flow:inspect
business:inspect:sink-check
business:inner:ERR
advice:throw:inner:IllegalStateException
advice:finally:inner:d=1
advice:throw:outer:IllegalStateException
advice:finally:outer:d=0
caller:error:rejected
case:inspect-external
advice:before:inspect:d=0
filter:static:emit
sink:enter:inspect
filter:flow:inspect
business:inspect:sink-check
business:inspect:external
advice:after:inspect
advice:finally:inspect:d=0
caller:ok:external
case:direct
business:inner:DIRECT
caller:done:DIRECT
```

### 14.1. Giải thích `filter:static:emit`

Handler nhận lời gọi `emit` qua proxy, nhưng filter theo tên cho phép gọi target trực tiếp và **không** phát thêm advice. Nhờ đó phát log một lần không tạo một log của chính log.

Trong production, nếu có overload/method trùng tên cần phân biệt bằng signature/metadata chính xác; filter chỉ theo tên trong demo nhằm minh họa nguyên lý, **không phải mẫu pointcut hoàn chỉnh**.

### 14.2. Giải thích `filter:flow:inspect`

Mỗi advice đặt `emitting=true` trong **phạm vi ngắn khi phát event**. Nó gọi `proxy.inspect("sink-check")`. Handler thấy method `inspect` trong đúng scope này nên **chuyển tiếp mà không instrument**.

Sau khối phát event, `emitting` được trả về trạng thái trước đó (hoặc gỡ), rồi mới chạy business. Do vậy:

- `Core.outer` gọi `self.inner` qua proxy vẫn có `advice:before:inner`.
- Caller ngoài gọi `proxy.inspect("external")` vẫn nhận advice, bởi `emitting` đã false.
- Một lời gọi trực tiếp `target.inner` không qua proxy nên **không có advice**, đúng giới hạn ví dụ.

### 14.3. Vì sao không đặt guard quanh toàn bộ `callTarget`?

Nếu giữ `emitting=true` cả khi gọi `Core.outer`, lời gọi `self.inner` có thể bị loại nhầm nếu guard áp chung cho mọi method. Thiết kế demo giới hạn guard ở **emission phase** và chỉ dùng nó để loại `inspect` trong phase đó.

Thực tế, không có nguyên tắc mọi nested business call đều phải được advice; điều quan trọng là **loại có chủ đích, theo hợp đồng**, không biến guard tránh recursion thành cách tắt toàn bộ instrumentation.

### 14.4. Lỗi và cleanup

Khi `inner("ERR")` ném `IllegalStateException`, `callTarget` bỏ lớp bọc `InvocationTargetException` của reflection và ném lại lỗi gốc. Advice trong ghi `advice:throw:inner` rồi dọn depth; advice ngoài ghi `advice:throw:outer` rồi dọn depth.

Nhờ `finally`, invocation tiếp theo `inspect("external")` bắt đầu tại `d=0`, không bị nhiễm depth từ lần lỗi.

### 14.5. Ví dụ này không chứng minh điều gì?

- JDK proxy **không dùng** `within`, `withincode` hoặc `cflow` của AspectJ; hai filter thủ công chỉ thể hiện **ý tưởng tương đương về mục tiêu**.
- Không có bytecode weaving hay parser DSL.
- Một proxy method call **không** bao mọi lời gọi direct trên target.
- `ThreadLocal` ở ví dụ không tự truyền context sang task async.
- Exclusion/guard không tạo thread safety cho target.
- Demo dùng output đơn luồng; trình tự đa luồng có thể xen kẽ.

## 15. Chọn guard runtime: biến boolean, depth hay invocation token?

### 15.1. Guard boolean cho emission ngắn

Nếu chỉ cần biết "đang ghi telemetry từ advice không?", một boolean **per-thread/per-invocation** có thể đủ cho đường thực thi đồng bộ.

Nhưng phải kiểm tra:

- Scope đủ hẹp chưa?
- Có nested emission khi boolean đã true không?
- Có lưu/khôi phục trạng thái cũ không?
- Có lỗi ném trước cleanup không?
- Có nguy cơ guard của một task ảnh hưởng task khác không?

### 15.2. Guard theo depth

Một `depth` đếm số lần invocation đang hoạt động:

```text
enter outer -> depth 1
enter inner -> depth 2
exit inner  -> depth 1
exit outer  -> depth 0
```

Depth hữu ích cho indentation hoặc xác định root span, **không nhất thiết phù hợp để quyết định bỏ qua advice**. Nếu loại mọi invocation có `depth>1`, ta dễ bỏ cả nested business operations.

### 15.3. Invocation token và scope ownership

Khi nhiều aspect chia sẻ infrastructure, một boolean không cho biết ai đang sở hữu trạng thái guard. Một token hoặc stack scope tường minh giúp khôi phục trạng thái đúng khi có callback lồng nhau:

```text
previousState = guard.capture()
guard.enter("audit-emission")
try:
    sendAudit()
finally:
    guard.restore(previousState)
```

Đây là **mã giả**, không phải Java API chuẩn.

### 15.4. Guard toàn cục là lựa chọn nguy hiểm

Một `static boolean currentlyLogging` không được bảo vệ có thể tạo race. Kể cả đã đồng bộ, nó còn có thể khiến request của thread B **mất audit** chỉ vì thread A đang ghi log.

Guard thường phải thuộc invocation, thread hoặc logical task theo đúng hợp đồng, không tự tạo một cờ cho cả VM.

## 16. `ThreadLocal` giúp gì và không giúp gì?

Java 17 có `ThreadLocal<T>` phù hợp cho một số state **đồng bộ theo thread**.

Ưu điểm:

- Mỗi thread có giá trị guard riêng.
- Có thể giữ depth hoặc ngữ cảnh từng thread.
- Dễ dọn bằng `try/finally`.
- Tránh xung đột trực tiếp giữa thread khác nhau khi truy cập cùng cờ.

Giới hạn:

- Thread pool **tái sử dụng** thread; nếu quên `remove`, invocation sau có thể nhận trạng thái cũ.
- Nested calls trên cùng thread vẫn cần stack/local frame khi có nhiều state.
- Một logical request có thể chạy qua **nhiều thread**.
- Future/callback async không nhất thiết thấy guard/context của thread tạo task.
- `InheritableThreadLocal` không thay thế context propagation theo logical task, đặc biệt với pool.
- Biến guard có thể ngăn recursion nhưng không đảm bảo log thành công hay thread safety của target.

### 16.1. Không mang guard emission sang task nghiệp vụ

Trace ID/correlation ID có thể cần truyền sang task mới. Nhưng `emitting=true` chỉ mang ý nghĩa **đang thực hiện emission của advice tại scope hiện tại**. Sao chép cờ này sang async worker có thể khiến một tác vụ nghiệp vụ hợp lệ bị bỏ instrumentation.

Phân biệt rõ **business context** và **implementation guard**.

## 17. Exception trong guard và khôi phục trạng thái

Nếu emission helper ném exception, guard cần được reset:

```java
boolean previous = emitting.get();
emitting.set(true);
try {
    emitEvent();
} finally {
    if (previous) {
        emitting.set(true);
    } else {
        emitting.remove();
    }
}
```

Đây là **mảnh Java minh họa**; giả định `emitting` là `ThreadLocal<Boolean>` và `emitEvent` là method có thể ném lỗi.

### 17.1. Vì sao khôi phục trạng thái cũ thay vì luôn false?

Nếu có scope ngoài đã đặt guard true rồi scope trong cũng đặt true, scope trong không nên tự xóa guard của scope ngoài. Khôi phục `previous` đúng với **ownership lồng nhau**.

### 17.2. Lỗi của cleanup có thể che lỗi chính

Một `finally` ném lỗi mới có thể thay exception đang thoát theo ngữ nghĩa Java. Do đó cleanup guard nên đơn giản, không gọi I/O hoặc helper phức tạp. Nếu phát log lỗi trong finally và log lại bị advice chọn, rất dễ lặp đúng tình huống đang cần chữa.

### 17.3. Phân biệt best-effort và mandatory audit

Với metrics best-effort, lỗi exporter có thể được bắt và ghi nhận phụ để **không phá** kết quả business. Nhưng với audit bắt buộc, việc gửi audit thất bại có thể buộc chặn thao tác; hành vi này phải được thiết kế/ghi trong contract, không tùy tiện "nuốt" exception.

## 18. Khi helper trực tiếp nằm trong class aspect

Một aspect có thể tự chứa method `formatEvent` hoặc `emitEvent`. Dùng `!within(MyAspect)` cho **call sites** trong aspect có thể đủ với một số join-point selection.

Tuy nhiên cần phân biệt:

- **Call** tới `formatEvent` từ code ngoài aspect: call site ở ngoài, nên `!within(MyAspect)` có thể vẫn khớp nếu phương thức đó được gọi từ business.
- **Execution** của `formatEvent`: code được khai báo trong aspect, nên lexical filter có thể loại nó.
- **Call** do chính `formatEvent` thực hiện: call site nằm trong body aspect, có thể bị loại.
- **Execution** của `Logger.write` ở class bên ngoài: không tự bị loại bởi `!within(MyAspect)`.

Chính loại join point giải thích tại sao cùng một biểu thức lexical có thể cho kết quả khác dự đoán.

### 18.1. Không dùng exclusion thiếu chính xác theo tên method

Loại mọi method tên `log` trên toàn chương trình có thể vô tình loại một business method `OrderService.log(...)` quan trọng. Ưu tiên pattern có **declaring type**, package hoặc marker được thiết kế rõ, rồi thêm kiểm thử khi refactor.

## 19. Đệ quy do `toString`, getter hoặc serialization

Một advice muốn ghi tham số:

```text
before:
    logger.info("arg=" + arg.toString())
```

Nếu `arg.toString()` tự gọi getter/service mà pointcut đang chọn, advice có thể tiếp tục phát log từ việc chuẩn bị log.

Ngay cả khi đã loại `Logger.write`, chu trình có thể nằm ở bước **format dữ liệu** trước khi tới logger.

Biện pháp:

- Tránh gọi `toString()` của object nghiệp vụ phức tạp chỉ để trace.
- Chỉ ghi những trường đã được cho phép và có cách lấy ổn định.
- Dùng serializer/formatter nằm ngoài scope cần advice hoặc có guard riêng.
- Hạn chế độ sâu khi duyệt object graph, chống cycle và giới hạn kích thước event.
- Không thực hiện API call/IO bất ngờ trong formatter.
- Kiểm tra cả exception path của formatter khi source object có lỗi.

**Không log toàn bộ args/result theo mặc định**: ngoài recursion, còn rủi ro lộ mật khẩu, token, thông tin cá nhân và dữ liệu tài chính.

## 20. Đệ quy qua nhiều aspect

Một chu trình không nhất thiết chỉ nằm trong một aspect:

```text
AuditAspect
  -> AuthorizationService.check()
       -> SecurityAspect
            -> AuditClient.write()
                 -> AuditAspect
```

Nếu `AuditAspect` chỉ loại call trực tiếp bên trong mình, `AuditClient.write` do `SecurityAspect` khởi tạo vẫn có thể tạo đường quay về.

Cần thiết kế **graph phụ thuộc của instrumentation**:

- Sink/logging adapter nên nằm ở lớp hạ tầng ít phụ thuộc aspect chính sách.
- Tránh để kiểm quyền của audit sink lại phụ thuộc việc audit chính nó trừ khi có một protocol bootstrap rõ ràng.
- Chọn policy cho thao tác nội bộ, khác policy cho operation public.
- Đánh dấu event theo nguồn và guard scope khi cần.
- Kiểm thử các chu trình A → B → A, không chỉ A → A.

### 20.1. Loại mọi join point khi có bất kỳ advice nào đang chạy là quá mạnh

Nếu loại toàn bộ `cflow(adviceexecution())` không ràng buộc aspect nguồn, một advice metrics có thể vô tình tắt security advice của business nested call. Các yêu cầu quan trọng về bảo mật hoặc kiểm toán không được phép biến mất chỉ vì một telemetry advice khác đang hoạt động.

## 21. Phân biệt self-interception và self-invocation bypass

Hai hiện tượng dễ bị đánh đồng:

**Self-interception:**

```text
Advice -> helper -> advice -> helper ...
```

Hệ thống bị can thiệp **quá nhiều**.

**Self-invocation bypass (trong một số proxy):**

```text
Caller -> Proxy -> Target.outer()
                    |
                    +-> this.inner()
                        (không qua proxy)
```

Hệ thống bị can thiệp **quá ít**.

Nếu khắc phục self-interception bằng guard chung `skipWhenNested`, ta có thể làm self-invocation bypass còn trầm trọng hơn hoặc tạo thêm đường bỏ audit.

Giải pháp phải xác định:

- **Receiver** của lời gọi (proxy hay target).
- **Loại join point**.
- **Điểm kích hoạt advice**.
- **Nguồn control flow**.
- **Mục tiêu coverage** của chính sách.

## 22. Callback, event bus và reentrancy bất ngờ

Một advice có thể công bố event lên event bus. Listener có thể gọi lại business service được aspect quan sát:

```text
TraceAdvice
  -> EventBus.publish()
      -> Listener.onEvent()
          -> BusinessService.execute()
              -> TraceAdvice
```

Nếu listener đồng bộ, call stack vẫn nằm trong advice emission. Nếu event bus chạy bất đồng bộ, listener có thể chạy sau khi advice ban đầu kết thúc hoặc trên thread khác.

Có hai vấn đề:

1. Bỏ mọi lời gọi xuất phát trong control flow advice có thể làm **mất business event hợp lệ** ở listener đồng bộ.
2. Dựa hoàn toàn vào ThreadLocal guard có thể **không chặn** listener bất đồng bộ, vì guard không được mang sang thread khác.

Đừng tự động coi cả hai là lỗi. Cần quyết định **event handler có là operation độc lập cần audit hay không**, và đặt instrumentation ở boundary phù hợp.

### 22.1. Event loop cần đường xử lý không quay lại publisher vô hạn

Nếu sự kiện audit tạo ra một sự kiện audit khác, hệ thống có thể sinh event storm ngay cả khi không có recursion trên một call stack duy nhất. Một guard chỉ dựa trên `cflow` không tự chặn được vòng lặp **bất đồng bộ qua queue**.

Có thể cần event type/source marker, idempotency key, deduplication, giới hạn attempts, cấu trúc luồng dữ liệu không chu trình hoặc chính sách sink riêng.

## 23. Trong code có nhiều `proceed` hoặc retry

Một around advice có thể gọi continuation hơn một lần nếu engine cho phép:

```text
RetryAround
  -> proceed attempt 1
  -> proceed attempt 2
```

Một trace aspect bên trong có thể chạy ở cả hai attempts. Nếu guard được bật quá lâu ở RetryAround, lần 2 có thể bị bỏ instrumentation. Nếu guard chỉ ở trace emission, mỗi attempt vẫn có trace riêng.

Phân biệt các sự kiện:

- **Logical request**: thao tác mà caller muốn thực hiện.
- **Attempt**: một lần chạy continuation.
- **Advice invocation**: một lần vào advice.
- **Business execution**: một lần thân method thực sự chạy.
- **Emission**: một lần gửi event phụ trợ.

Không dùng số log lines để khẳng định số lần business thành công. Một lần business có thể tạo nhiều event; một advice có thể không proceed; một retry có thể tạo thêm business executions.

### 23.1. Retry lỗi sinh sau side effect

Nếu business hoàn tất rồi after advice hoặc sink ném lỗi, một retry ngoài có thể thực hiện business thêm lần nữa. Loại trừ recursion không sửa được rủi ro retry này; cần kiểm soát loại lỗi được retry và idempotency của operation.

## 24. Exception và nguồn lỗi trong vòng instrumentation

Giả sử:

```text
Business throws E1
  -> ErrorAdvice.log(E1)
       -> Logger throws E2
```

Nếu handler không quản lý, caller có thể thấy **E2 thay E1**. Nhưng đối với một logging aspect **best effort**, hợp đồng có thể yêu cầu luôn truyền E1.

Các hướng xử lý:

- Bắt lỗi sink trong phạm vi chỉ xử lý logging.
- Không để việc ghi lỗi quay lại pointcut mà chính nó đang tạo.
- Khi cần chuyển đổi lỗi, lưu `cause` hoặc `suppressed` theo policy.
- Không tự ném `Throwable` mới trong cleanup guard nếu không cần.
- Đảm bảo guard được reset ngay cả khi `proceed` hoặc sink thất bại.
- Không nuốt `Error` hoặc exception thuộc miền nghiệp vụ ngoài chủ đích chỉ để giảm log.

### 24.1. `finally` không phải một event audit bền vững

`finally` giúp dọn state trong control flow bình thường của Java, nhưng không bảo đảm event đã được ghi bền vững hoặc tất cả tiến trình luôn chạy cleanup trong mọi tình huống VM/process bị dừng bất thường.

## 25. Constructor, static initializer và initialization side effects

Một số mô hình AOP có thể chọn constructor call/execution, class initialization hoặc các loại join point khác. Nếu aspect rộng chạy ngay trong quá trình khởi tạo hạ tầng logging, nó có thể tạo **bootstrap cycle**:

```text
Aspect.initialize()
  -> Logger.initialize()
       -> AdviceTriggeredDuringInitialization()
            -> Logger.initialize() ...
```

Những vấn đề bổ sung:

- Singleton/aspect instance chưa khởi tạo hoàn chỉnh.
- Helper dependency chưa sẵn sàng.
- Static initialization lock có thể ảnh hưởng liveness.
- Class loader và module có thể làm điều kiện chọn không như khi runtime ổn định.
- Logging trong constructor có thể gọi `toString`/getter trên object chưa hoàn tất init.

**Không áp dụng bừa exclusion dành cho method call vào constructor**: mỗi join-point kind có ngữ nghĩa riêng. Tốt hơn xác định bootstrap boundary và không cho helper instrumentation phụ thuộc ngược vào service chưa sẵn sàng.

## 26. Gỡ lỗi khi guard hoạt động quá mạnh

Các dấu hiệu:

- Không còn đệ quy, nhưng mất log của inner business method.
- `depth=1` hoặc `depth>0` dẫn đến skip mọi thứ.
- Request A làm request B không được instrument.
- Sau một lỗi sink, tất cả invocation sau trên thread pool mất trace.
- Một aspect bảo mật không chạy khi metrics aspect đang có hoạt động.
- Khi tách event bus thành async, số event thay đổi bất thường.

Quy trình:

1. Ghi rõ **join point phải được advice**.
2. Ghi rõ **join point cần loại**.
3. Phân biệt static exclusion với runtime guard.
4. Rà soát scope đặt guard: chỉ emission hay toàn continuation?
5. Kiểm tra guard có được reset khi exception không.
6. Kiểm tra state được lưu per thread, per invocation hay global.
7. Kiểm tra callback cùng thread và callback async.
8. Kiểm tra thứ tự aspect và việc một advice khác gọi helper.
9. Dùng event collector đếm **business / advised / excluded** riêng.
10. Chạy negative test và positive test sau mỗi thay đổi pointcut.

Đừng coi số log giảm là bằng chứng đã sửa đúng nếu số event cần thiết cũng giảm.

## 27. Gỡ lỗi khi exclusion quá yếu

Các dấu hiệu:

- Stack trace có mẫu `Advice → Logger → Advice → Logger` lặp.
- Tăng CPU/memory dù business rất ít việc.
- Một request tạo hàng trăm event giống nhau.
- Pointcut chỉ loại `within(Aspect)` nhưng helper execution trong class khác vẫn khớp.
- Cơ chế guard đang false khi helper không nằm trong scope guard dự kiến.
- Vòng async tiếp diễn sau khi call stack ban đầu đã kết thúc.

Quy trình:

1. Xác định join-point kind trong stack: call hay execution.
2. Xác định **lexical declaring type** ở điểm bị advice chọn.
3. Vẽ đường từ advice tới helper và quay lại.
4. Rà soát liệu `!within` có loại đúng **vị trí code** chứ không phải chỉ **type receiver**.
5. Xác định control flow root nên dùng: own advice execution hay emission helper.
6. Kiểm tra `cflow`/`cflowbelow` và root inclusion theo ngữ nghĩa engine.
7. Chọn exclusion tĩnh chính xác nếu có thể.
8. Thêm guard động hẹp khi cần, với rollback state qua `finally`.
9. Không thử lỗi bằng vòng lặp vô hạn thật trong production.
10. Kiểm thử regression khi nâng cấp/đổi helper.

## 28. Ma trận kiểm thử bắt buộc

| Test | Mong đợi |
| --- | --- |
| Caller gọi business qua interception boundary | Advice chạy đúng số lần |
| Advice tự gọi logger/helper bị loại | Không kích hoạt advice của chính nó ngoài ý định |
| Helper được gọi trực tiếp từ business | Có/không được instrument đúng theo hợp đồng |
| Business outer gọi inner qua proxy | Inner vẫn được advice nếu nằm trong scope |
| Raw target gọi nội bộ `this.inner` | Phản ánh đúng giới hạn cơ chế proxy |
| Helper ở class khác | Lexical exclusion không bị hiểu nhầm là dynamic exclusion |
| Advice gọi helper qua nhiều tầng | Control-flow guard/exclusion chặn đúng chu trình |
| Aspect A gọi helper kích hoạt Aspect B | Không tạo vòng A → B → A ngoài ý muốn |
| Sink ném exception | Guard được dọn, primary error xử lý theo policy |
| Business ném exception | Không rò depth hoặc context |
| Invocation kế tiếp trên cùng thread | Guard trở về trạng thái bình thường |
| Hai thread đồng thời | Không trộn guard; không bỏ audit thread khác |
| Retry gọi proceed nhiều lần | Trace theo request/attempt đúng yêu cầu |
| Callback đồng bộ | Không loại business event hợp lệ nếu policy yêu cầu |
| Callback bất đồng bộ | Không phụ thuộc sai vào cùng call stack/thread |
| Init/constructor | Không tạo bootstrap cycle |
| Pointcut đổi khi refactor | Positive/negative tests phát hiện coverage đổi |
| Method overload/helper mới | Không loại nhầm method nghiệp vụ do tên giống |
| Logging args/toString | Không đệ quy, không lộ dữ liệu nhạy cảm |
| Excessive instrumentation | Event volume và overhead nằm trong phạm vi đã chấp nhận |

### 28.1. Kiểm thử điều cần loại và điều phải giữ

Để bảo đảm bài toán được giải quyết, test phải có **hai phía**:

- **Negative test:** join point của sink/helper nội bộ không tạo thêm advice.
- **Positive test:** nested business join point phù hợp vẫn tạo advice.

Chỉ test “không bị StackOverflowError” là chưa đủ; một guard tắt toàn bộ aspect cũng có thể làm test ấy PASS.

### 28.2. Không dựa vào timestamp làm định danh invocation

Trong logging concurrent, timestamp có thể trùng hoặc log xen kẽ. Nên có invocation ID, parent ID, attempt ID khi cần, và phân biệt emitter thread với task identity.

## 29. Các hiểu nhầm thường gặp

**“Loại `within(MyAspect)` luôn ngăn mọi self-interception.”** Không. Nó là điều kiện lexical; execution của helper class khác có thể vẫn khớp.

**“Loại code của aspect đồng nghĩa loại mọi method aspect từng gọi tới.”** Không. Phải xem call site, execution và control flow.

**“Điều kiện `!cflow(adviceexecution())` luôn là tốt nhất.”** Không. Nó có thể loại quá rộng, bao cả những điểm phát sinh từ các aspect khác; cần giới hạn nguồn và kiểm thử.

**“`cflow` và `cflowbelow` giống hệt.”** Không. Theo AspectJ, khác nhau về việc bao gồm root join point.

**“`call` và `execution` là cùng một join point.”** Không. Chúng đại diện cho các ranh giới khác nhau ở những công cụ có hỗ trợ cả hai.

**“Một guard `insideAspect` global đủ an toàn.”** Không. Nó gây race và có thể tắt advice ở các thread khác.

**“Bỏ mọi lời gọi nested sẽ hết lỗi.”** Có thể hết recursion nhưng cũng bỏ mất logging, security hoặc audit của business inner.

**“`synchronized` tự chặn recursion.”** Không. Java monitor cho phép reentry cùng thread.

**“ThreadLocal tự truyền qua mọi callback bất đồng bộ.”** Không. Phải xác định task context propagation.

**“Không thấy advice của inner thì inner không chạy.”** Sai khi target tự gọi qua `this` mà không đi qua proxy.

**“Aspect chỉ logging không ảnh hưởng kết quả.”** Không chắc nếu formatter/logger ném lỗi hoặc thay đổi state/timing.

**“Log nhiều lần chứng minh business chạy nhiều lần.”** Không. Cần đếm business invocation riêng advice events.

**“Exclusion ở một điểm đã đủ cho mọi phiên bản thư viện.”** Không. Call graph và helper class có thể thay khi refactor.

**“Một lời gọi helper là vô hại vì nó không thuộc domain logic.”** Chưa chắc. Nó có thể có side effect, khóa, I/O và trigger các aspect khác.

## 30. Bài tập có giải thích

### Bài 1: log chính log

Một advice chọn mọi method-call join point và gọi `System.out.println` trong body. Vì sao có thể xảy ra recursion?

**Đáp án:** Lời gọi `println` từ chính advice cũng thuộc tập điểm được chọn, khiến advice chạy lại rồi gọi `println` tiếp. Với DSL hỗ trợ lexical exclusion, có thể loại call site nằm trong aspect; hoặc thu hẹp tập call phù hợp.

### Bài 2: lexical exclusion không đủ

Aspect gọi `AuditSink.write`. Sink gọi `DatabaseClient.insert`. Pointcut chọn execution của `DatabaseClient.insert` và chỉ loại `!within(AuditAspect)`. Có chắc ngăn recursion không?

**Đáp án:** Không. Execution được khai báo trong DatabaseClient, nằm ngoài AuditAspect về lexical scope. Cần xem dynamic control flow hoặc exclusion chính xác của helper execution.

### Bài 3: business và advice cùng dùng helper

`SharedHelper.process` được cả business lẫn advice gọi. Muốn chỉ loại lời gọi do advice phát sinh nên chọn loại trừ nào?

**Đáp án:** Một điều kiện theo **nguồn control flow** hoặc guard đúng scope có thể phù hợp hơn loại toàn bộ helper. Cần xác định ngữ nghĩa engine và test cả hai đường.

### Bài 4: bỏ tất cả invocation có depth > 0

Outer và inner là hai operation được audit. Nếu guard bỏ mọi invocation nested, kết quả?

**Đáp án:** Advice của inner bị bỏ dù yêu cầu audit có thể đòi ghi nó. Chỉ loại đường phát event phụ trợ gây recursion.

### Bài 5: một lỗi sink để lại guard

Logger ném exception giữa lúc `emitting=true` và code không có `finally`. Request sau chạy trên cùng thread pool sẽ ra sao?

**Đáp án:** Guard còn kẹt, có thể làm request sau mất instrumentation. Cần cleanup theo scope trong `finally`.

### Bài 6: khác biệt `cflow`/`cflowbelow`

Với AspectJ, nếu pointcut `P` xác định một root join point, `cflowbelow(P)` có chọn chính root đó không?

**Đáp án:** Không. `cflow(P)` gồm root và descendants, còn `cflowbelow(P)` không gồm root.

### Bài 7: hai aspect

AuditAspect gọi SecurityService; SecurityAspect gọi AuditSink; AuditSink lại bị AuditAspect chọn. Có thể có recursion không?

**Đáp án:** Có thể tạo chu trình nhiều aspect. Cần vẽ dependency graph, bảo vệ sink và phân biệt operation nào thật sự phải audit.

### Bài 8: self-invocation bypass

Caller đi qua interface proxy để gọi target.outer; target gọi `this.inner()`. Có chắc inner nhận advice không?

**Đáp án:** Không với proxy delegation vào target riêng, vì lời gọi nội bộ không quay qua proxy. Điều này khác self-interception.

### Bài 9: async event bus

Advice ghi event vào queue; consumer ở thread khác xử lý và lại ghi event. Guard `ThreadLocal` của producer có chặn chu trình này không?

**Đáp án:** Không thể giả định. Chu trình có thể đi qua queue/task khác. Cần thiết kế event type/source marker, idempotency/deduplication hoặc cấu trúc luồng không tạo vòng.

### Bài 10: hoàn tất sau retry

Retry gọi business hai lần, nhưng logger ghi ba event. Có thể kết luận business chạy ba lần không?

**Đáp án:** Không. Số event không tương đương số business execution. Cần correlation request/attempt và counter cụ thể.

## 31. Checklist áp dụng trước khi bật aspect trong môi trường thực

- [ ] Xác định đúng **join-point kind** và weaving/proxy boundary.
- [ ] Viết rõ tập operation cần advice và tập phải loại.
- [ ] Vẽ call graph từ advice tới logger/metrics/audit/helper/formatter.
- [ ] Kiểm tra code tự aspect có tạo join point phù hợp hay không.
- [ ] Phân biệt lexical exclusion với control-flow exclusion.
- [ ] Với AspectJ, đối chiếu chính xác `within`/`withincode`/`adviceexecution`/`cflow`/`cflowbelow`.
- [ ] Không dựa vào cú pháp của một DSL khi engine không hỗ trợ.
- [ ] Ưu tiên pointcut nghiệp vụ hẹp trước wildcard bao mọi method.
- [ ] Exclusion của helper có căn cứ, không loại nhầm business method.
- [ ] Guard runtime chỉ bao emission/helper cần ngăn tái nhập.
- [ ] Không dùng cờ global để tắt advice của thread khác.
- [ ] Có cleanup bằng `finally`, bảo toàn scope lồng nhau.
- [ ] Dùng local frame/snapshot per invocation cho thông tin depth/timing.
- [ ] Không dùng depth để tự động bỏ mọi nested business calls.
- [ ] Kiểm thử cả self-interception và self-invocation bypass.
- [ ] Có test exception từ sink và từ business.
- [ ] Không làm mất lỗi gốc khi logger/formatter thất bại ngoài ý định.
- [ ] Không lấy `toString`, reflection hay serialization quá rộng để ghi log.
- [ ] Kiểm tra callback đồng bộ và event loop bất đồng bộ.
- [ ] Có chính sách riêng cho async context/correlation và guard propagation.
- [ ] Kiểm tra chu trình A → B → A giữa nhiều aspect.
- [ ] Kiểm tra constructor/static initialization nếu pointcut bao chúng.
- [ ] Có test số lần advice, số business invocation và số guard skip riêng.
- [ ] Có test concurrency và thread-pool reuse.
- [ ] Xác định retry attempts và idempotency trước khi kết hợp aspect.
- [ ] Theo dõi event volume, latency, memory và lỗi liên quan instrumentation.
- [ ] Có đường rollback/disable aspect khi xuất hiện event storm.
- [ ] Không coi "không còn stack overflow" là đủ nếu mất audit nghiệp vụ.

## 32. Tài liệu đối chiếu

Những tài liệu sau mô tả **ngữ nghĩa của một công cụ AOP cụ thể**, giúp hiểu rõ các mẫu lexical và control-flow exclusion. Khi dùng công cụ khác, cần đối chiếu tài liệu tương ứng:

- [Eclipse AspectJ — Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): giải thích `within`, `withincode`, `adviceexecution`, `cflow` và `cflowbelow`.
- [Eclipse AspectJ — Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): có ví dụ `!within` nhằm ngăn lời gọi trong advice tự tạo recursion.
- [Eclipse AspectJ — Debugging Pointcuts](https://eclipse.dev/aspectj/doc/latest/pdguide/pointcuts.html): cách kiểm từng phần pointcut, các lỗi về join-point kind, lexical scope và runtime constraints.
- [Java SE 17 — Proxy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): JDK dynamic proxy, giao diện và invocation handler.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): state theo thread và vòng đời cleanup.

## 33. Kết luận

**Tránh đệ quy do aspect tự can thiệp không chỉ là đặt một cờ "đang trong advice".** Cần nhận diện đúng **nguồn của join point**, **loại điểm được chọn**, **vị trí khai báo mã** và **control flow đang hoạt động**.

Loại trừ theo lexical code hữu ích cho call site hoặc join point nằm trong aspect. Nhưng khi advice gọi helper ở class khác, **execution join point của helper** có thể vẫn được chọn; khi đó cần một exclusion đúng helper hoặc một điều kiện dựa control flow. Các công cụ hỗ trợ `adviceexecution` và `cflow` có thể diễn đạt những ranh giới này trực tiếp; các mô hình proxy khác có thể cần handler guard.

Giải pháp chất lượng vừa **chặn được đường tự phát event quay lại advice**, vừa **giữ được nested business advice cần thiết**, dọn trạng thái khi lỗi, không làm mất audit bảo mật và có kiểm thử dương/âm chứng minh đúng coverage.
