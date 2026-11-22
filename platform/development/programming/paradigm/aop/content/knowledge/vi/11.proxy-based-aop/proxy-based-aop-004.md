# Giới hạn của lời gọi nội bộ không đi qua proxy

## 1. Bản chất của vấn đề

Trong **Aspect-Oriented Programming (AOP)**, proxy là một cách triển khai hành vi xuyên suốt: caller gọi phương thức trên **proxy**, proxy lựa chọn advice phù hợp rồi chuyển tiếp lời gọi tới **target**. Khi target đang chạy, nó có thể gọi một phương thức khác của chính mình bằng `this.inner()` hoặc bằng lời gọi `inner()` không ghi rõ receiver. Với mô hình **delegating proxy tách biệt khỏi target**, lời gọi nội bộ ấy **không tự đi qua proxy**.

Kết quả cần phân biệt:

- **Method nội bộ vẫn thực sự chạy.**
- **Proxy handler không nhận một invocation riêng cho method nội bộ.**
- **Advice được gắn với invocation qua proxy của method nội bộ có thể không chạy.**
- Advice của **method outer** vẫn có thể chạy nếu caller đã gọi outer qua proxy.

Đây là giới hạn thường được gọi là **self-invocation bypass**. Không nên diễn giải thành quy tắc tuyệt đối của mọi công cụ AOP: một cơ chế weaving trực tiếp vào bytecode của method execution có thể quan sát self-call; một số dạng class proxy cũng có dispatch khác nhau. Cần xác định rõ **loại proxy**, **receiver thực tế** và **join-point model**.

### Mục tiêu học tập

Sau bài này bạn sẽ:

1. Phân biệt target, proxy, caller, join point, pointcut, advice và handler.
2. Vẽ đường gọi qua proxy và đường gọi qua `this`.
3. Giải thích tại sao metadata/annotation hay pointcut rộng hơn không tự sửa proxy bypass.
4. Phân tích hậu quả đối với tracing, metrics, retry, cache, ranh giới giao dịch, bảo mật và exception.
5. So sánh JDK interface proxy, class-based proxy, decorator và weaving trực tiếp.
6. Chọn các phương án tổ chức lại: coordinator, collaborator được bọc, explicit boundary hoặc weaving phù hợp.
7. Chạy một chương trình Java 17 có output chính xác để chứng minh self-call, direct target call và external call khác nhau.
8. Xây dựng positive/negative tests chứng minh **target thực thi** nhưng **advice inner không thực thi** trong đường bypass.

Bài chỉ xét AOP cơ bản và nâng cao **nói chung**, không dùng cú pháp hoặc hành vi mặc định của một framework cụ thể.

## 2. Cơ chế proxy theo từng tầng

Xét mô hình đơn giản:

~~~text
Caller
  |
  v
Proxy.outer(arguments)
  |
  v
Handler / interceptor chain
  |
  +-- kiểm tra pointcut
  +-- before advice
  +-- chuyển tiếp vào target
  |
  v
Target.outer(arguments)
  |
  v
Handler nhận return / throwable
  |
  +-- after-returning / after-throwing
  |
  v
Caller nhận result / throwable
~~~

Ba quyết định độc lập cùng ảnh hưởng đến kết quả:

| Tầng | Câu hỏi | Hậu quả nếu không thỏa |
| --- | --- | --- |
| **Interception path** | Invocation có đi qua object proxy không? | Handler không nhận lời gọi. |
| **Pointcut matching** | Invocation mà handler nhận có khớp điều kiện không? | Advice cụ thể có thể không chạy, dù target vẫn chạy. |
| **Runtime occurrence** | Đường code đã đi tới lời gọi ấy chưa? | Không có sự kiện nào để quan sát. |

Một annotation `@Observed` trên method chỉ là **metadata**. Nếu handler không nhìn thấy invocation của method ấy, annotation không có cơ hội được kiểm tra bởi handler tại đường gọi đó.

### 2.1. Một target và một proxy có thể cùng tồn tại

Trong JDK dynamic proxy, caller có thể giữ object proxy triển khai interface, còn handler giữ reference tới target:

~~~text
proxyRef  -> handler -> targetRef
                         |
                         +-- target method body
~~~

Target là một object có identity riêng. Khi body của target chạy, `this` là receiver của body đó: thông thường chính target được handler ủy quyền. Do đó `this.inner()` không tự biến thành `proxyRef.inner()`.

Điều này cũng giải thích một bypass khác: nếu một thành phần giữ **targetRef** và gọi thẳng vào nó, lời gọi đó không đi qua handler. Đó là direct-target bypass, không phải self-invocation, nhưng có cùng hậu quả với advice qua proxy.

### 2.2. Method outer có advice không đồng nghĩa method inner có advice

Giả sử pointcut của proxy khớp cả `outer` và `inner`.

~~~text
Caller -> Proxy.outer()
              |
          ADVICE outer trước
              |
          Target.outer()
              |
          this.inner()  --> Target.inner()
              |             (không có Proxy.inner invocation)
              |
          ADVICE outer sau
              |
          Caller
~~~

Method inner vẫn có thể thực hiện I/O, thay đổi trạng thái hoặc ném exception. Nhưng **không có before/after riêng cho inner từ handler của proxy** trong đường gọi ấy. Đếm số dòng log của handler không phải là phép đếm trung thực mọi method execution.

## 3. Khi nào self-invocation bypass xảy ra?

Điều kiện cần ở mô hình delegating proxy:

1. Caller đi vào proxy cho method outer (hoặc target body được gọi bằng cách khác).
2. Execution thực sự chuyển tới **body của target**, nơi `this` trỏ về target.
3. Body gọi một method khác trên chính receiver đó.
4. Lời gọi ấy không được định tuyến qua proxy/interceptor chain.
5. Advice dành cho invocation inner nằm **trên proxy boundary**, không nằm trực tiếp trong body inner đã weave.

Nếu một trong các điều kiện đổi, cần xem lại kết quả. Ví dụ engine có thể dệt hook tại entry của `inner` thay vì chỉ tại proxy invocation.

### 3.1. Lời gọi không ghi `this` cũng có thể là self-call

~~~java
class JobService {
    void outer() {
        inner();
    }

    void inner() {
        // xử lý
    }
}
~~~

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Trong tình huống method instance thông thường, `inner()` là lời gọi trên receiver hiện tại. Không phải vì thiếu chữ `this` mà lời gọi phải qua proxy.

### 3.2. Virtual dispatch không đồng nghĩa proxy dispatch

Java có thể dispatch một lời gọi tới method được override trong subclass. Điều đó là **đa hình tại runtime**. Nếu receiver vẫn là target thật, việc chọn override không có nghĩa handler của một object proxy riêng biệt đã chạy.

### 3.3. Method reference và lambda cũng có receiver

Một callback được đăng ký bằng `this::inner` trong target thường giữ reference tới **target**. Sau đó, khi callback chạy, lời gọi vẫn đi theo receiver đã capture. Một caller khác đăng ký `proxy::inner` sẽ có call path khác. Đường gọi phải được kiểm tra tại thời điểm callback được thực thi, không chỉ tại chỗ định nghĩa method.

### 3.4. Self-call có thể xảy ra nhiều lần

Một `outer` gọi `this.inner` trong vòng lặp 100 lần có thể tạo **100 execution của inner** nhưng chỉ **1 invocation qua proxy của outer**. Nếu instrumentation chỉ trên proxy inner, số liệu proxy inner có thể bằng 0 trong kịch bản đó. Vấn đề không liên quan đến số lượng method được viết trong source.

## 4. Pointcut đúng vẫn có thể không có advice

Pointcut mô tả **điều kiện lựa chọn**. Proxy mô tả **nơi interception xảy ra**. Chúng là hai tầng khác nhau.

Giả sử predicate:

~~~text
methodName == "inner"
AND methodHasAnnotation("Tracked")
~~~

Điều kiện đó có thể đúng cho method inner được khai báo trên interface, nhưng khi target tự gọi `this.inner()`, handler không nhận event để đánh giá predicate.

Các thay đổi sau **không tự khắc phục**:

- Mở rộng predicate thành mọi method.
- Thêm annotation vào implementation.
- Đổi `private` thành `public`.
- Đổi tên method để khớp wildcard.
- Đổi thứ tự các advice vốn chỉ chạy **sau khi** proxy nhận event.

Đặc biệt, annotation trên interface method và implementation method có thể được reflection tra ở hai declaration khác nhau. Đây là một vấn đề **metadata lookup** riêng biệt; dù khắc phục đúng metadata mà call path vẫn bypass thì handler inner vẫn không chạy.

### 4.1. Dấu hiệu chẩn đoán

Nếu log xuất hiện:

~~~text
ADVICE before outer
TARGET outer
TARGET inner
ADVICE returning outer
~~~

thì kết luận đúng **chỉ khi có bằng chứng từ code/test** là inner được target gọi trực tiếp: inner đã chạy nhưng advice inner không được handler nhìn thấy. Đừng suy “không có log = method chưa chạy”, vì có thể logger bị tắt hoặc pointcut không khớp.

## 5. Ví dụ Java 17 runnable: self-call, proxy-call, external-call

Chương trình sau dùng **JDK dynamic proxy** triển khai interface `Operations`, và một target `Service` chứa hai method `outer` và `inner`.

- `outer` gọi `this.inner` bên trong target.
- Handler ghi advice cho mọi method nó nhận.
- `Coordinator` là thành phần ngoài target, giữ proxy để gọi `inner`.
- `inner("BAD")` ném exception; handler ghi lỗi theo **method đã đi qua proxy**.
- Caller gọi `target.inner("DIRECT")` để chứng minh direct-target bypass.

Tạo file **`ProxySelfCallDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxySelfCallDemo {
    interface Operations {
        String outer(String id);
        String inner(String id);
    }

    static final class Service implements Operations {
        @Override
        public String outer(String id) {
            System.out.println("TARGET outer " + id);
            String value = this.inner(id);
            System.out.println("TARGET outer completed " + value);
            return "OUT:" + value;
        }

        @Override
        public String inner(String id) {
            System.out.println("TARGET inner " + id);
            if ("BAD".equals(id)) {
                throw new IllegalStateException("inner failed");
            }
            return "OK:" + id;
        }
    }

    static Operations instrument(Operations target) {
        return (Operations) Proxy.newProxyInstance(
                Operations.class.getClassLoader(),
                new Class<?>[] { Operations.class },
                (proxy, method, args) -> {
                    System.out.println("ADVICE before " + method.getName());
                    try {
                        Object result = method.invoke(target, args);
                        System.out.println("ADVICE returning "
                                + method.getName());
                        return result;
                    } catch (InvocationTargetException wrapped) {
                        Throwable original = wrapped.getCause();
                        System.out.println("ADVICE throwing "
                                + method.getName() + " "
                                + original.getClass().getSimpleName());
                        throw original;
                    }
                }
        );
    }

    static final class Coordinator {
        private final Operations operations;

        Coordinator(Operations operations) {
            this.operations = operations;
        }

        String executeInner(String id) {
            System.out.println("COORDINATOR invoke " + id);
            return operations.inner(id);
        }
    }

    public static void main(String[] args) {
        Service target = new Service();
        Operations proxy = instrument(target);

        System.out.println("CALLER " + proxy.outer("A"));
        System.out.println("CALLER " + proxy.inner("B"));

        Coordinator coordinator = new Coordinator(proxy);
        System.out.println("CALLER " + coordinator.executeInner("C"));

        try {
            proxy.outer("BAD");
        } catch (IllegalStateException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        try {
            proxy.inner("BAD");
        } catch (IllegalStateException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        System.out.println("CALLER " + target.inner("DIRECT"));
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac ProxySelfCallDemo.java
java ProxySelfCallDemo
~~~

**Stdout đúng thứ tự:**

~~~text
ADVICE before outer
TARGET outer A
TARGET inner A
TARGET outer completed OK:A
ADVICE returning outer
CALLER OUT:OK:A
ADVICE before inner
TARGET inner B
ADVICE returning inner
CALLER OK:B
COORDINATOR invoke C
ADVICE before inner
TARGET inner C
ADVICE returning inner
CALLER OK:C
ADVICE before outer
TARGET outer BAD
TARGET inner BAD
ADVICE throwing outer IllegalStateException
CALLER caught inner failed
ADVICE before inner
TARGET inner BAD
ADVICE throwing inner IllegalStateException
CALLER caught inner failed
TARGET inner DIRECT
CALLER OK:DIRECT
~~~

### 5.1. Tại sao outer có advice nhưng self-call inner không có?

Lời gọi `proxy.outer("A")` vào handler nên in `ADVICE before outer`. Handler thực hiện `method.invoke(target, args)`, làm body `Service.outer` chạy trên receiver target. Trong body, `this.inner("A")` là một lời gọi khác nhưng **không tới handler**. Target in `TARGET inner A`, hoàn tất outer, sau đó handler in `ADVICE returning outer`.

Nếu method inner không chạy, sẽ không có dòng `TARGET inner A` và kết quả outer không thể được tạo theo code đã viết. Bài học là phân biệt **execution** với **interception**.

### 5.2. Tại sao proxy.inner khác target.inner?

`proxy.inner("B")` gọi handler → target.inner, có `ADVICE before inner` và `ADVICE returning inner`. `target.inner("DIRECT")` gọi body trực tiếp, không qua handler. **Một implementation method**, nhưng hai đường gọi với interception khác nhau.

### 5.3. Coordinator minh họa biên ngoài rõ ràng

`Coordinator` nhận một `Operations` có object thực là proxy. Khi nó gọi `operations.inner("C")`, invocation thực đi qua handler. Không cần target biết mình được proxy hóa.

Nếu coordinator được cấp nhầm object `target` thay vì `proxy`, advice vẫn bị bypass. Do đó giải pháp cấu trúc phải đi kèm **wiring/ownership** chính xác.

### 5.4. Exception từ inner qua outer được gắn nhãn outer

`proxy.outer("BAD")` gọi target.outer; inner ném `IllegalStateException` và exception thoát qua outer. `Method.invoke` trên outer bọc exception trong `InvocationTargetException`. Handler gỡ `getCause()`, ghi **`ADVICE throwing outer IllegalStateException`** rồi ném lại cause. Handler không có event inner riêng nên không có `ADVICE throwing inner` ở đường này.

`proxy.inner("BAD")` tạo invocation proxy cho inner nên handler ghi **`ADVICE throwing inner IllegalStateException`**.

### 5.5. Ví dụ này KHÔNG chứng minh điều gì?

- Không phải mọi class-based proxy đều có cùng cách dispatch.
- Không chứng minh bytecode method inner đã được weave.
- Không chặn private method, constructor, static method hoặc field access.
- Không chứng minh mọi caller bắt buộc giữ proxy.
- Không định nghĩa các pointcut DSL cho nhiều engine.
- Không triển khai transaction/caching/retry thực; chỉ mô phỏng một interceptor quan sát.

## 6. Ảnh hưởng đối với logging và tracing

Với tracing theo biên proxy, một lời gọi outer qua proxy tạo span/metric cho outer. Internal calls tới inner không nhất thiết tạo span riêng.

Ví dụ một workflow gửi 20 phần tử:

~~~text
proxy.processBatch()
  -> target.processBatch()
       -> this.processOne(item1)
       -> this.processOne(item2)
       ...
       -> this.processOne(item20)
~~~

Advice trên `processBatch` có thể ghi **một operation**, còn advice riêng của `processOne` qua proxy không được gọi cho 20 internal calls. Nếu mục tiêu là đo tổng thời gian của batch, đây có thể là **độ hạt phù hợp**. Nếu cần thời gian từng item, phải có hook tại mỗi item boundary được bảo đảm, ví dụ collaborator riêng hoặc instrumentation tường minh.

**Không nên tăng số span chỉ để “có log”.** Một hệ thống thu thập trace có thể phải giới hạn sampling/cardinality và tránh ghi nguyên arguments, kết quả hoặc dữ liệu nhạy cảm.

## 7. Ảnh hưởng đối với caching

Nếu proxy advice tại method inner tạo cache:

~~~text
Proxy.inner(key)
  -> nếu cache hit: trả cached value, không gọi target
  -> nếu miss: gọi target.inner(key), có thể lưu kết quả
~~~

thì self-call `this.inner(key)` trong target sẽ **bỏ qua lookup và store** của proxy ấy. Target có thể thực hiện I/O lại, tạo khác biệt hiệu năng và kết quả tùy consistency.

Trước khi chuyển method thành collaborator có proxy, xác định:

- Inner có phải thao tác đọc thuần hay có side effect?
- Cache key có chứa mọi yếu tố ảnh hưởng kết quả không?
- Có nhiều tenant/user, phiên bản, locale hoặc quyền dữ liệu?
- Internal call có **cần** áp dụng cache hay cố ý muốn đường uncached?
- Thay đổi kiến trúc có dẫn tới recursion do cache loader gọi lại proxy không?

Nếu caching quan trọng cho tính đúng đắn hoặc hiệu năng bắt buộc, nên làm biên cache tường minh/được bảo đảm, không chỉ giả định annotation có hiệu lực mọi đường.

## 8. Ảnh hưởng đối với retry

Advice retry quanh `inner` được gọi qua proxy có thể thử lại khi method ném một lỗi phù hợp. Nhưng khi outer tự gọi `this.inner()`, advice retry riêng đó có thể không chạy.

Một “cách sửa” thiếu suy nghĩ là đặt retry lên outer. Điều này có thể thay đổi đơn vị retry từ **một thao tác inner** thành **toàn bộ outer workflow**.

Ví dụ:
- Outer đã ghi một phần dữ liệu rồi inner thứ ba lỗi.
- Retry outer chạy lại hai bước đã thành công.
- Nếu tác vụ không idempotent, dữ liệu hoặc side effect có thể bị lặp.

Giải pháp phải xác định **attempt boundary, idempotency, timeout tổng, backoff và phân loại lỗi**. Self-invocation bypass là tín hiệu cần xem lại thiết kế retry, không phải lý do tự động chuyển annotation lên outer.

## 9. Ảnh hưởng đối với transaction

Đây là trường hợp cần diễn đạt cẩn thận. Nếu outer đã chạy trong một transaction context, self-call inner **có thể vẫn tham gia transaction đang tồn tại** dù advice mở boundary riêng cho inner không được thực hiện.

Không kết luận:

> “Self-invocation luôn khiến inner chạy ngoài transaction”.

Kết luận chính xác hơn:

> “Nếu chính sách transaction riêng của inner được lắp qua proxy invocation và inner bị gọi trực tiếp trên target, **interceptor dành riêng cho inner không được kích hoạt ở đường đó**.”

Điều này ảnh hưởng khi inner được kỳ vọng:
- Mở một unit-of-work mới.
- Có timeout/isolation hoặc propagation riêng.
- Commit/rollback ở một boundary khác outer.
- Ghi metric transaction riêng.
- Dọn resource theo scope inner.

Dù vậy, transaction thật còn phụ thuộc cơ chế lưu trữ, ngữ cảnh hiện hành và quy tắc propagation. Khi refactor, kiểm thử **commit/rollback semantics**, không chỉ đếm các advice được gọi.

## 10. Ảnh hưởng đối với lỗi và cleanup

Giả sử inner ném lỗi:

~~~text
target.outer()
    -> this.inner()
        -> throw X
    -> X thoát ra khỏi outer
~~~

Nếu outer đang chạy trong proxy invocation, after-throwing/around advice của outer có thể nhận X như **exception của lời gọi outer**. Điều đó không có nghĩa advice dành cho inner đã chạy.

Nếu outer tự bắt X và trả fallback:

~~~text
target.outer():
    try:
        return this.inner()
    catch X:
        return fallback
~~~

outer trả bình thường. Advice after-returning của outer có thể chạy; after-throwing của outer không tự thấy X đã bị bắt. Nếu cleanup/metrics phải ghi từng failure inner, nên đặt ở scope đáng tin, không phụ thuộc một proxy inner bị bypass.

Với các resource như lock, stream hoặc transaction handle, đừng dùng proxy advice làm **cơ chế giải phóng duy nhất** khi có đường gọi trực tiếp. Owner của resource cần lifecycle và `try/finally` đúng hợp đồng.

## 11. Bảo mật và các bất biến bắt buộc

Một interceptor kiểm tra quyền truy cập trước khi gọi method có thể có ích tại API boundary. Nhưng nếu target được gọi qua đường bypass, việc kiểm tra có thể không xảy ra.

Vì vậy không xem **proxy advice là bằng chứng duy nhất** rằng mọi đường truy cập dữ liệu đều đã được bảo vệ. Hãy:

1. Chọn **trusted boundary** nơi mọi request phải đi qua.
2. Bảo vệ invariant ở domain/service/data boundary cần thiết.
3. Xác định những object target có thể bị truy cập trực tiếp hay không.
4. Kiểm thử cả đường gọi ngoài và internal call.
5. Đặt chính sách logging/audit tránh lộ secrets từ arguments.
6. Nếu policy cần enforcement tuyệt đối, thiết kế sao cho không có đường bypass có khả năng làm sai trạng thái.

Giải quyết self-invocation bằng cách cố lấy proxy tham chiếu từ bên trong target có thể giúp chạy một advice cụ thể, nhưng **không thay thế threat model** và không chứng minh mọi entry point được bảo vệ.

## 12. Các lựa chọn cấu trúc để tránh bypass

### 12.1. Giữ policy ở outer nếu chỉ cần ranh giới tổng

Nếu mục tiêu chỉ là ghi một trace của toàn workflow, advice trên `outer` có thể đủ. Không cần ép helper inner thành một service độc lập chỉ vì mong có nhiều log hơn.

Ưu điểm: ít layer, ít dispatch, hợp đồng nghiệp vụ dễ đọc. Đánh đổi: không có metric/advice riêng của inner trong các self-calls.

### 12.2. Tách inner sang một collaborator được bọc

~~~text
Caller -> WorkflowService
             |
             +--> ProxiedItemWriter -> ItemWriterTarget.writeOne()
~~~

Bây giờ workflow gọi method qua một **dependency độc lập** đã được inject dưới dạng proxy. Ưu điểm:

- Trách nhiệm orchestration và thao tác được phân tách.
- Caller có một boundary rõ cho policy.
- Mock/spy và integration tests dễ xác nhận.
- Không buộc target biết đến proxy của chính mình.

Rủi ro: nếu nơi khác vẫn giữ `ItemWriterTarget` gốc, bypass vẫn xảy ra. Tách class phải đi cùng quy tắc construction/wiring.

### 12.3. Dùng coordinator bên ngoài

Như ví dụ Java: coordinator nhận `Operations proxy` và gọi `inner`, do đó advice inner được kích hoạt. Cách này phù hợp khi workflow là orchestration độc lập với thao tác.

Không cần áp dụng coordinator cho mọi helper private; chỉ tách khi biên logic và policy có ý nghĩa.

### 12.4. Dùng explicit decorator hoặc interceptor tại biên

Một decorator triển khai cùng interface và chuyển tiếp sang target. Nó giúp nhìn rõ rằng caller phải dùng wrapper. Tuy nhiên decorator **cũng có thể bị bypass** nếu caller giữ target gốc, và self-call trong target không tự quay lại decorator.

Cách tổ chức object graph và quyền sở hữu tham chiếu quan trọng hơn tên gọi “proxy” hay “decorator”.

### 12.5. Dùng weaving trực tiếp method execution khi thật sự cần

Nếu yêu cầu là “quan sát mọi execution của inner bất kể caller”, một cơ chế biến đổi source/bytecode/load time có khả năng dệt hook vào method body có thể phù hợp hơn.

Nhưng phải xác minh:
- Engine hỗ trợ method execution join point nào?
- Class thực sự nằm trong scope được weave?
- Classloader/artifact có chứa mã đã biến đổi?
- Điểm có bị loại bởi pointcut hoặc visibility/bytecode constraints?
- Có xung đột nhiều transformer hoặc recursion trong logger không?
- Có test xác nhận direct call và self-call đúng như mong muốn không?

Không khẳng định weaving tự động bắt mọi điểm chỉ vì nó mạnh hơn JDK interface proxy.

### 12.6. Proxy tham chiếu ngược trong chính target: giải pháp có giá

Target có thể được thiết kế để nhận một proxy reference của chính nó, rồi gọi `proxy.inner()` thay `this.inner()`. Nhưng cách này có thể dẫn đến:
- Vòng phụ thuộc khi khởi tạo.
- Proxy chưa sẵn sàng hoặc bị gắn sai target.
- Coupling nghiệp vụ với infrastructure AOP.
- Vấn đề nhiều instance/proxy scopes khác nhau.
- Reentrancy, recursion và lifecycle khó theo dõi.
- Test phải dựng đúng object graph phức tạp hơn.

Vì thế nên xem đây là **phương án cần cân nhắc kỹ**, không phải mẹo mặc định. Orchestrator/collaborator rõ ràng thường dễ giải thích và bảo trì hơn.

## 13. So sánh các kiểu proxy và weaving

| Cơ chế | Receiver/đường interception | Internal call có tự có advice riêng? |
| --- | --- | --- |
| **Delegating JDK interface proxy** | Proxy nhận interface invocation, handler gọi target riêng. | **Không** khi target gọi trực tiếp `this.inner()`. |
| **Explicit decorator** | Wrapper chuyển tiếp tới target. | **Không** nếu target tự gọi chính nó ngoài wrapper. |
| **Class proxy/subclass proxy** | Có thể override/dispatch theo implementation. | **Phụ thuộc engine, loại method và cách receiver được sử dụng**; phải test. |
| **Source/bytecode weaving execution hook** | Hook có thể được dệt tại method execution. | **Có thể**, nếu method đã được weave và pointcut khớp. |
| **Call-site weaving** | Hook tại vị trí gọi method đã được dệt. | **Có thể**, nếu call site nội bộ thuộc phạm vi được xử lý. |
| **Runtime instrumentation** | Phụ thuộc transformer và những điểm nó tạo ra. | Không thể kết luận chung; xem hook thực tế. |

Bảng không xếp hạng công cụ. Nếu nhu cầu chỉ là một boundary dịch vụ public, proxy có thể đủ và đơn giản. Nếu yêu cầu áp vào **mọi method execution**, cần một mô hình phù hợp hơn và chấp nhận chi phí cấu hình/QA.

### 13.1. Private, final, static và constructor là những trường hợp khác nhau

**Private:** JDK interface proxy không chặn trực tiếp private method của target vì method đó không thuộc public interface invocation qua proxy. Weaving bytecode có thể có khả năng khác.

**Final:** Proxy dựa trên subclass/override có thể bị giới hạn bởi final class/final method; delegating interface proxy có thể vẫn chặn lời gọi interface rồi ủy quyền vào một implementation final. Không đưa ra quy tắc “final luôn cấm AOP”.

**Static:** Static method không được dispatch qua instance của interface proxy như method instance. Muốn quan sát nó phải có hook khác.

**Constructor:** Target constructor thường chạy trước khi proxy tách biệt được tạo để bọc target. JDK interface proxy không tự chặn constructor execution của target.

**Default interface method:** Khi gọi qua proxy, handler có thể nhận invocation của default method; việc nó gọi tiếp default body thế nào và những lời gọi từ đó được dispatch ra sao cần test theo Java API/công cụ cụ thể, không áp nguyên sơ đồ target tách biệt của mọi trường hợp.

## 14. Self-invocation trong async và callback

Một method ngoài có thể lên lịch:

~~~java
Runnable task = this::innerTask;
executor.execute(task);
~~~

Đây là **mã minh họa không độc lập**: giả định `innerTask` và `executor` đã tồn tại. Method reference capture **target `this`**, do đó khi task được gọi ở worker, nó vẫn không tự chuyển thành proxy invocation.

Nếu callback ở nơi khác capture `proxy::innerTask`, đường gọi có thể qua proxy. Nhưng phải lưu ý:

- Tác vụ có thể chạy **sau khi outer đã trả về**.
- Around advice của outer đo tới method return chưa chắc bao toàn bộ task.
- `ThreadLocal` của caller không tự truyền qua worker.
- Callback có thể giữ request/target quá lâu nếu capture object lớn.
- Exception của task có thể được thể hiện trong `CompletionStage` thay vì ném đồng bộ.
- Cancellation/timeout của future không tự chứng minh remote operation đã dừng.

Đây là **hai chiều độc lập**: biên interception (proxy hay target) và biên thời gian (method return hay task completion). Cần giải quyết cả hai nếu muốn monitoring end-to-end.

## 15. Thiết kế kiểm thử chứng minh chính xác bypass

### 15.1. Ma trận đường gọi

| Ca | Đường gọi | Target.inner chạy? | Proxy advice inner chạy? |
| --- | --- | --- | --- |
| A | Caller → proxy.inner | Có nếu handler tiếp tục. | Có nếu pointcut khớp. |
| B | Caller → proxy.outer → target.this.inner | Có nếu outer gọi đến. | Không trong delegating proxy demo. |
| C | Caller → target.inner | Có. | Không. |
| D | Coordinator(proxy) → proxy.inner | Có. | Có nếu pointcut khớp. |
| E | proxy.outer nhưng outer không gọi inner | Không. | Không. |
| F | proxy.outer nhưng before advice ném lỗi | Có thể chưa chạy. | Không nếu inner không được gọi. |
| G | proxy.inner nhưng pointcut không khớp | Có thể chạy. | Không có advice cụ thể. |
| H | proxy.inner được cache advice trả hit | Target có thể không chạy. | Advice cache có thể đã chạy. |

Bảng nói về cơ chế proxy tách target như demo. Với engine khác phải viết ma trận lại dựa trên receiver/call path thật.

### 15.2. Bộ đếm trong target và handler

Đừng chỉ assert số dòng log. Trong test, dùng ba counters:

~~~text
outerAdviceInvocations
innerAdviceInvocations
innerTargetExecutions
~~~

Sau một lượt `proxy.outer()` gọi inner đúng một lần, kỳ vọng của demo:
- `outerAdviceInvocations = 1`
- `innerAdviceInvocations = 0`
- `innerTargetExecutions = 1`

Sau đó gọi `proxy.inner()` một lần và pointcut khớp, kỳ vọng:
- `innerAdviceInvocations = 1`
- `innerTargetExecutions = 2`

Counter target giúp phân biệt **“không chạy advice”** với **“không chạy body”**. Nếu retry, recursion hoặc vòng lặp tồn tại, cần điều chỉnh expected counts.

### 15.3. Ca lỗi và fallback

Cần test hai nhánh:
1. Inner ném lỗi thoát qua outer: advice throwing của **outer** có thể chạy, inner advice vẫn không.
2. Outer tự catch rồi trả fallback: advice returning của **outer** có thể chạy, inner advice vẫn không.

Nếu test chỉ có đường thành công, có thể không phát hiện sai lệch metric lỗi hoặc transaction.

### 15.4. Ca annotation

Khi pointcut chọn theo annotation, kiểm tra annotation ở **interface method** hay **implementation method**, retention là gì, matcher tra metadata ở đâu. Đây là kiểm thử riêng với đường gọi proxy/self-call.

### 15.5. Ca weaving khác proxy

Nếu production dùng class-based proxy hoặc bytecode weaving, phải tạo integration test với **đúng engine, loader, artifact và configuration**; không dùng kết quả demo JDK proxy để khẳng định sản phẩm khác giống nó.

### 15.6. Ca concurrency

Nếu advice giữ `lastMethod`, `lastArgs` hoặc `startTime` ở một field dùng chung, nhiều caller có thể ghi đè và tạo lỗi quan sát độc lập với self-invocation. Dùng scope cục bộ theo invocation, không giữ toàn bộ args/target lâu hơn nhu cầu và dọn context đúng trên error path.

## 16. Quy trình chẩn đoán khi production thiếu advice

1. **Xác nhận symptom:** thiếu log/metric nào? Target action có xảy ra không?
2. **Xác nhận object:** caller đang giữ proxy hay target? Đừng chỉ nhìn tên interface.
3. **Vẽ receiver:** body đang chạy với `this` nào? Có `this.inner`, callback `this::inner` hoặc target reference trực tiếp không?
4. **Xác nhận pointcut:** method thực tế có khớp matcher không, kể cả annotation/overload/override?
5. **Phân biệt class scope:** proxy được tạo cho object đó chưa; trong weaving, class đã được biến đổi chưa?
6. **Kiểm tra caller path:** direct target, self-call, collaborator được inject và async callback có đi qua wrapper không?
7. **Kiểm tra exception:** inner ném ra ngoài hay outer đã catch thành fallback? Advice nào đáng lẽ nhìn thấy lỗi?
8. **Chọn thay đổi nhỏ nhất:** chỉnh wiring, tách collaborator, thay policy boundary hoặc chọn weaving thực sự cần thiết.
9. **Xác nhận backward compatibility:** retry count, transaction context, log volume, dữ liệu riêng tư và thời gian xử lý có thay đổi ngoài ý định không?
10. **Ghi nhận evidence:** positive/negative tests, bộ đếm target/advice và sơ đồ call path trước/sau.

### 16.1. Không có advice không đồng nghĩa chỉ có một nguyên nhân

Thiếu advice còn có thể do:
- Method chưa được gọi.
- Pointcut không khớp.
- Handler bị disable.
- Caller nhận nhầm target.
- Interface/implementation metadata khác chỗ.
- Method không nằm trong interface của JDK proxy.
- Class/loader ngoài scope của weaving.
- Logging sink bị lỗi hoặc sampling loại sự kiện.
- Exception từ advice chặn target trước khi chạy.

Cần phân biệt bằng bằng chứng, không chỉ thay mọi cấu hình rồi hy vọng log xuất hiện.

## 17. Ngộ nhận thường gặp

**“Có `@Observed` nghĩa là mọi execution đều chạy advice.”** Không: metadata không tự tạo interception.

**“Public method chắc chắn được proxy khi gọi từ chính class.”** Không với delegating proxy tách target.

**“Mở rộng pointcut thành mọi method sẽ xử lý self-call bypass.”** Không nếu event không đi qua handler.

**“Không có `ADVICE inner` tức `inner` chưa chạy.”** Sai; body có thể đã chạy trên target.

**“Nếu outer có advice thì inner có advice do cùng class.”** Không; mỗi invocation phải qua biên tương ứng.

**“Inner không có interceptor giao dịch tức luôn không có transaction.”** Không; nó có thể chạy trong transaction đã được outer mở.

**“Class proxy và JDK dynamic proxy luôn giống hệt ở self-invocation.”** Không; dispatch và object model có thể khác.

**“Weaving luôn chặn được mọi method.”** Không; còn join-point model, pointcut, scope, classloader và binary.

**“Chỉ cần gắn proxy vào field của chính target.”** Có thể tạo circular dependency và coupling lớn; chưa chắc là thiết kế tốt.

**“Decorator không bị bypass vì được viết tường minh.”** Target vẫn có thể tự gọi nội bộ; caller có thể giữ target gốc.

**“Đảo order của advice sẽ sửa việc handler không được gọi.”** Không; order chỉ có hiệu lực với advice trong chain đã nhận invocation.

**“Đặt retry ở outer thay inner là tương đương.”** Không; phạm vi retry thay đổi, có nguy cơ lặp side effect.

**“Proxy advice đảm bảo tất cả security checks.”** Chỉ với những entry paths được bảo đảm; domain invariant cần trusted enforcement.

## 18. Câu hỏi vận dụng

**Câu 1.** Caller gọi `proxy.outer()`, target.outer gọi `this.inner()`; pointcut khớp cả hai. Handler nhận những method nào trong đường đó?

**Đáp án:** Handler của delegating proxy nhận invocation outer; không nhận inner riêng.

**Câu 2.** Vì sao in `TARGET inner` mà không in `ADVICE before inner` không mâu thuẫn?

**Đáp án:** Target body chạy; handler proxy không nhận internal call.

**Câu 3.** Chuyển `inner` thành public và thêm annotation có sửa được bypass không?

**Đáp án:** Không tự sửa receiver/call path. Cần bảo đảm lời gọi tới proxy hoặc dùng cơ chế hook khác.

**Câu 4.** Outer bắt `IOException` của inner và trả `"fallback"`. After-throwing của outer có chạy cho IOException đó không?

**Đáp án:** Không nếu outer kết thúc bình thường bằng fallback; exception không thoát khỏi outer invocation.

**Câu 5.** Inner cần chính sách retry độc lập. Vì sao chuyển retry lên outer có thể nguy hiểm?

**Đáp án:** Retry cả outer có thể lặp những side effect đã thành công trước inner. Cần xác định attempt/idempotency boundary.

**Câu 6.** Một `Coordinator` ngoài target nhận `Operations proxy` và gọi `inner()`. Handler có nhận không?

**Đáp án:** Có nếu caller dùng đúng proxy và method thuộc đường interceptor; sau đó pointcut quyết định advice cụ thể.

**Câu 7.** Nếu target đã nằm trong transaction context của outer, self-call inner bypass một interceptor riêng, kết luận nào đúng?

**Đáp án:** Không thể khẳng định inner nằm ngoài transaction; chỉ có thể nói interceptor riêng của inner không chạy qua đường đó.

**Câu 8.** Vì sao một engine weave trực tiếp execution inner có thể vẫn quan sát self-call?

**Đáp án:** Vì execution của inner vẫn xảy ra, và hook có thể được gắn tại entry/body inner thay vì yêu cầu caller qua proxy.

**Câu 9.** Target đăng ký callback bằng `this::inner`, gọi sau khi outer return. Có hai ranh giới nào cần xét?

**Đáp án:** Receiver/call path có bypass proxy không; và task completion xảy ra sau method return hay không.

**Câu 10.** Muốn khẳng định lỗi self-invocation bypass trong test, cần chứng minh hai điều gì?

**Đáp án:** Target.inner đã thực sự chạy và handler/advice inner không nhận invocation tương ứng, đồng thời đã loại trừ lỗi pointcut/logging.

## Kết luận

**Lời gọi nội bộ không đi qua proxy** là vấn đề về **receiver và đường interception**, không phải đơn thuần là điều kiện pointcut. Trong mô hình delegating proxy, caller gọi `proxy.outer()` thì advice outer có thể chạy; nhưng target.outer gọi `this.inner()` trên target nên inner thực thi mà không tạo invocation qua proxy cho inner.

Hướng xử lý phụ thuộc yêu cầu: đôi khi advice tổng ở outer đã đủ; đôi khi nên đưa bước inner thành collaborator có proxy hoặc một coordinator bên ngoài gọi qua proxy; đôi khi cần weaving trực tiếp method execution. Với transaction, retry, caching và bảo mật, cần phân biệt chính sách ở **outer boundary** với chính sách riêng của **inner boundary** để tránh thay đổi semantics ngoài ý định. Hãy chứng minh bằng **call path, counters và negative tests**, không chỉ dựa vào annotation hoặc sự vắng mặt của log.
