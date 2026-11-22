# Chi phí theo dõi ngữ cảnh động và phương án đơn giản hơn trong AOP

## 1. Bài toán: chỉ áp advice khi đang ở trong một luồng gọi cụ thể

Trong **Aspect-Oriented Programming (AOP)**, một pointcut có thể lựa chọn join point dựa trên những thuộc tính tương đối **tĩnh** như loại method, tên/signature, annotation hoặc vị trí lexical trong mã nguồn. Nhưng đôi khi yêu cầu lại nói về **lịch sử gọi hàm đang hoạt động ở runtime**:

- Ghi log các thao tác khi đang xử lý một lệnh nhập dữ liệu, nhưng không ghi cùng thao tác nếu nó được gọi từ nơi khác.
- Đo các lệnh truy cập tài nguyên phát sinh **trong luồng điều khiển** của một yêu cầu cha.
- Áp dụng một chính sách chỉ khi một scope nghiệp vụ cụ thể đã được kích hoạt.
- Gắn trace hoặc correlation context cho những method được gọi gián tiếp nhiều tầng.
- Phân biệt method được gọi ở top-level với cùng method được gọi do một hoạt động khác dẫn đến.

Ví dụ:

~~~text
User request
  |
  +--> importBatch()                 <-- điểm kích hoạt scope
          |
          +--> validateRow()
          |      |
          |      +--> normalize()
          |
          +--> persist()
                 |
                 +--> encode()
~~~

Nếu muốn advice cho **normalize** và **encode** chỉ khi chúng nằm trong luồng gọi động do **importBatch** khởi đầu, một pointcut dựa duy nhất vào tên method không đủ phân biệt. Cần kiểm tra **dynamic control-flow context** hoặc thay đổi thiết kế để truyền điều kiện rõ hơn.

Một số ngôn ngữ AOP, ví dụ AspectJ, cung cấp **cflow(pointcut)** và **cflowbelow(pointcut)** để match các join point nằm trong luồng điều khiển động của join point anchor. Đây là một lựa chọn biểu đạt mạnh, nhưng có thể kéo theo chi phí runtime cao hơn phương pháp nhận diện hoàn toàn tĩnh.

**Ý chính:** theo dõi ngữ cảnh động hữu ích khi điều kiện phụ thuộc lịch sử gọi đang hoạt động. Nhưng nó không miễn phí, không phải hình thức duy nhất để biểu đạt cùng yêu cầu và không tự xử lý đúng async/thread boundaries. Cần cân nhắc lợi ích biểu đạt so với overhead, tính dễ kiểm thử và khả năng bảo trì.

Bài trình bày **AOP nói chung**, không giả định một framework ứng dụng cụ thể. Các ví dụ về cflow/cflowbelow được giải thích trong ngữ cảnh một ngôn ngữ AOP hỗ trợ chúng; mã Java 17 runnable mô phỏng scope bằng ThreadLocal để minh họa cơ chế, **không tuyên bố đó là cách mọi weaver cài đặt cflow**.

## 2. Phân biệt pointcut tĩnh và điểm chọn động

| Tiêu chí | Điều kiện tĩnh/lexical | Điều kiện theo luồng điều khiển động |
|---|---|---|
| Quyết định phụ thuộc | Signature, type, annotation, source location hoặc metadata ổn định | Call stack/scope của invocation runtime |
| Có thể xác định phần lớn khi weave? | Nhiều trường hợp có | Chỉ một phần: trạng thái động vẫn cần theo dõi |
| Cùng method được gọi từ hai callers | Thường match giống nhau nếu các điều kiện tĩnh giống | Có thể khác nhau tùy scope đang active |
| Runtime state | Có thể ít hoặc không cần | Có thể cần counter, stack, scope bit, thread context |
| Chi phí | Có cơ hội tối ưu bằng static matching | Có thể tăng chi phí enter/exit/check tại nhiều điểm |
| Độ khó reasoning | Thường dễ theo code location | Cần hiểu call path, nested calls, async, recursion |
| Khả năng thay thế | Annotation, interface boundary, explicit predicate | Parameter/context, riêng service boundary, event correlation |

### 2.1. Tĩnh không có nghĩa hoàn toàn zero-cost

Một pointcut chọn được join point ở compile/weave time vẫn có thể cần advice invocation, đo thời gian, logging, reflection hoặc một runtime guard cho một điều kiện động khác. Chi phí thực phụ thuộc advice body và công nghệ weave. Không nên so sánh “static = 0, dynamic = tốn kém” như một định luật.

### 2.2. Động không đồng nghĩa chậm trong mọi tình huống

Một weaver có thể tối ưu hóa cflow bằng counter hoặc context marker, giới hạn instrumentation, cache trạng thái hay loại bỏ phần kiểm tra không cần thiết. Với số điểm được chọn ít, overhead có thể không đáng kể. **Chỉ benchmark workload thật mới cho câu trả lời đáng tin.**

## 3. Chi phí của cflow bắt đầu từ phạm vi cần theo dõi

Trong các cơ chế hỗ trợ, **`cflow(P)`** áp dụng trong dynamic control flow bắt đầu ở P, kể cả root; **`cflowbelow(P)`** chỉ chọn join point **bên dưới một P occurrence đang hoạt động**. Nếu P gọi P lần nữa, inner P vẫn có thể nằm dưới outer P. Những điều kiện này dựa vào **trạng thái runtime**, không phải chỉ vào tên/position của method.

~~~text
importBatch() [root: enter scope]
   ├─ validateRow()   ← kiểm tra scope động
   └─ persist()       ← kiểm tra scope động
importBatch() returns [exit scope]
normalize() outside  ← không thuộc scope đó
~~~

Khi tối ưu, câu hỏi quan trọng không phải chỉ “cflow hay cflowbelow”, mà là **bao nhiêu lần root phải cập nhật state**, **bao nhiêu candidate join point phải kiểm tra state** và **mỗi lượt advice phát sinh bao nhiêu công việc bổ sung**. Lời gọi async sau khi root đã kết thúc không được mặc định mang cùng call-stack flow; context propagation là lựa chọn kiến trúc riêng.

Một `ThreadLocal<Boolean>` dùng để mô phỏng scope có thể thiếu thông tin root occurrence/depth khi nested hoặc đệ quy; không đồng nhất nó với đầy đủ semantics của một pointcut engine.

## 4. Vì sao phải theo dõi runtime state?

Một điều kiện như “method encode xảy ra trong importBatch” không thể chỉ suy từ method encode vì nó có thể được gọi qua nhiều callers:

~~~text
ImportBatch -> Store -> encode
ManualEdit  -> Store -> encode
Background  -> Store -> encode
~~~

Nếu tất cả các đường đều gọi **cùng method body**, lexical execution pointcut thấy cùng một method. Để phân biệt, runtime phải biết **lần invocation hiện tại đang thuộc dynamic flow nào**.

Một cơ chế khái niệm:

~~~text
On entering anchor:
    push marker / increment active counter

At candidate nested join point:
    check if marker active

On leaving anchor:
    pop marker / decrement counter
~~~

Chi phí có thể đến từ:

1. **Instrument anchor entry/exit** để duy trì marker.
2. **Kiểm tra runtime** trên những candidate join points cần biết flow status.
3. **Lưu và phục hồi scope** khi nested/reentrant calls xảy ra.
4. **Lưu dữ liệu binding** nếu pointcut cần context như actor, ID hoặc đối số từ anchor.
5. **Đồng bộ hóa/context isolation** giữa threads hoặc execution contexts.
6. **Allocation và GC** nếu tạo scope objects, stacks, context snapshots hoặc wrappers.

Đây là **cost model khái niệm**. Không phải mọi ngôn ngữ AOP hoặc compiler nhất thiết dùng call stack đầy đủ hay một ThreadLocal ArrayDeque; một số trường hợp có thể dùng counter, bitmask, mapping hoặc weaving chuyên biệt.

## 5. Chi phí CPU: enter, check, exit

Xét:

- \(N_a\): số lần vào/ra anchor.
- \(N_c\): số lần candidate join points thực sự cần kiểm tra flow.
- \(C_e\): chi phí trung bình enter/exit marker.
- \(C_c\): chi phí trung bình mỗi lần kiểm tra membership.
- \(C_b\): chi phí advice body nếu được kích hoạt.

Một mô hình sơ bộ:

\[
T_{\text{flow}} \approx N_a C_e + N_c C_c + N_{\text{matched}} C_b
\]

Mô hình giúp tìm nguyên nhân overhead, **không phải công thức dự báo chính xác**; JIT, cache, branch prediction, contention, object allocation và compiler optimizations có thể khiến các đại lượng thay đổi theo workload.

Điểm đáng chú ý: nếu anchor chỉ chạy một lần nhưng candidate join point nằm trên hot loop với hàng triệu lần gọi, **\(N_c C_c\)** có thể chi phối overhead. Ngược lại, nếu matcher có ít candidates, dynamic tracking có thể không đáng kể so với I/O.

### 5.1. Member check O(1) hay O(depth)?

Nếu chỉ cần biết một loại anchor có đang active không, runtime có thể quản lý một **counter** theo context và kiểm tra activeCount > 0, tương tự O(1) về số stack frames.

Nếu phải tìm marker cụ thể, binding hoặc so khớp một tập flow contexts, một giải pháp đơn giản dùng stack search có thể có chi phí **O(depth)**, trong đó depth là số nested scopes. Chi phí này thay đổi theo implementation.

Không nên phát biểu “mọi cflow check luôn duyệt toàn bộ stack” hoặc “luôn O(1)” khi chưa biết code được tạo bởi weaver.

### 5.2. Chi phí ở hot methods

Các leaf methods nhỏ như getter, encoder, parser helper có thể chỉ mất ít nanoseconds tới microseconds trong một workload nhất định. Nếu advice/cflow check được chèn vào từng leaf call, phần overhead tương đối có thể lớn hơn so với một phương thức I/O chậm.

**Mức chi phí phải được đo**, không tự gán con số tuyệt đối cho mọi JVM hoặc mọi AOP engine.

## 6. Chi phí bộ nhớ, allocation và GC

Một cơ chế dynamic context có thể cần:

- Thread-local storage entry.
- Một counter hoặc stack dữ liệu theo thread.
- Các objects chứa bindings hoặc metadata của mỗi invocation.
- Context snapshot khi chuyển qua async boundary.
- Callback wrappers để restore context.
- Trace/log events nếu advice active.

Một flow scope object rất nhỏ vẫn có thể trở thành lượng allocation lớn nếu được tạo hàng triệu lần trong một hot path. Nhưng JIT có thể thực hiện escape analysis và loại bỏ một số allocations trong điều kiện thích hợp. Tránh khẳng định mọi marker gây heap allocation không tránh được.

### 6.1. Thread pools và lifetime

Nếu ThreadLocal giữ một stack/context rồi **không remove khi scope kết thúc**, worker thread trong pool có thể giữ dữ liệu cũ lâu hơn mong muốn. Điều đó gây:

- Memory retention.
- Leaked business identity/tracing metadata.
- Context nhầm giữa hai requests trên cùng worker.
- Khó debug vì lỗi phụ thuộc thread reuse.

Khi dùng scoped context tự quản, phải restore/remove trong finally. Đừng thay thế việc giải phóng đúng bằng cách chờ GC.

### 6.2. Depth lớn và recursion

Một call tree đệ quy hoặc nhiều around advice lồng nhau có thể tạo depth lớn. Stack marker thiết kế sai có thể tăng chi phí kiểm tra membership, giữ nhiều objects hoặc làm sai cách suy luận về anchor đã active.

## 7. Chi phí gỡ lỗi và độ phức tạp ngữ nghĩa

Chi phí không chỉ nằm ở CPU:

- **Khó đọc:** một method được advice ở đường gọi này nhưng không được advice ở đường gọi khác.
- **Khó dự đoán:** thêm một lớp wrapper hoặc thay cách gọi helper có thể thay dynamic flow.
- **Khó test:** phải dựng đúng call path, recursion, exception, async và nested anchors.
- **Khó quan sát:** logs không ghi rõ vì sao một pointcut match hoặc không match.
- **Tính phụ thuộc:** code nghiệp vụ có thể âm thầm dựa vào presence của một call stack scope.
- **Độ mong manh:** tách một method thành task async có thể phá dynamic-flow membership.

Đây là các chi phí bảo trì quan trọng khi quyết định có nên dùng cflow thay cho một thiết kế rõ ràng hơn.

### 7.1. Những câu hỏi reviewer nên hỏi

1. Điều kiện thật sự cần dynamic call history không?
2. Có thể mô tả điều kiện bằng một parameter hoặc explicit context không?
3. Cùng một method cần hai hành vi tùy caller hay vì API chưa phân tách trách nhiệm?
4. Có async/thread boundaries hay RPC khiến stack dynamic thay đổi không?
5. Điều kiện có thuộc policy bảo mật bắt buộc không? Có đường bypass không?
6. Có kiểm thử được anchor/candidate match và exclude anchor riêng cho cflowbelow không?
7. Có resource scopes cần restore khi exception không?

## 8. Ví dụ Java 17 runnable: context động qua ThreadLocal

Ví dụ sau **mô phỏng ý tưởng flow membership** bằng ThreadLocal stack. Nó đủ để minh họa:

- Đang ngoài scope: active=false.
- Vào anchor: active=true.
- Trong nested scope: anchor vẫn active.
- Nếu nested operation throw: finally pop scope.
- Ra khỏi anchor: active=false và ThreadLocal.remove.
- Chuyển work sang ExecutorService: worker thread **không tự kế thừa** ThreadLocal của caller.
- Truyền boolean/context tường minh: worker nhận đúng ý nghĩa do caller chuyển.

**Quan trọng:** helper Flow.active("top") chỉ minh họa membership của một marker; nó **không cài đặt toàn bộ semantics của cflow/cflowbelow**. Không đưa đoạn demo này vào production như một runtime AOP engine.

Tạo tệp **DynamicFlowCostDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class DynamicFlowCostDemo {
    static final class Flow {
        private static final ThreadLocal<ArrayDeque<String>> STACK =
                new ThreadLocal<>();

        static void within(String name, Runnable body) {
            ArrayDeque<String> stack = STACK.get();
            if (stack == null) {
                stack = new ArrayDeque<>();
                STACK.set(stack);
            }
            stack.push(name);
            try {
                body.run();
            } finally {
                String removed = stack.pop();
                if (!removed.equals(name)) {
                    throw new IllegalStateException("mismatched scope");
                }
                if (stack.isEmpty()) {
                    STACK.remove();
                }
            }
        }

        static boolean active(String name) {
            ArrayDeque<String> stack = STACK.get();
            return stack != null && stack.contains(name);
        }

        static int depth() {
            ArrayDeque<String> stack = STACK.get();
            return stack == null ? 0 : stack.size();
        }
    }

    static void leaf(String label) {
        System.out.println("leaf:" + label
                + " cflow(top)=" + Flow.active("top")
                + " depth=" + Flow.depth());
    }

    static void explicitLeaf(String label, boolean underTop) {
        System.out.println("explicit:" + label + " underTop=" + underTop);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            leaf("outside");
            Flow.within("top", () -> {
                System.out.println("top: active=" + Flow.active("top")
                        + " depth=" + Flow.depth());
                leaf("inside");
                Flow.within("nested", () -> leaf("nested"));
                try {
                    Flow.within("fail", () -> {
                        leaf("before-error");
                        throw new IllegalStateException("boom");
                    });
                } catch (IllegalStateException e) {
                    System.out.println("caught=" + e.getMessage());
                }
                leaf("restored");
                try {
                    Future<Boolean> worker =
                            pool.submit(() -> Flow.active("top"));
                    System.out.println("worker: cflow(top)=" + worker.get());
                    Future<?> explicit = pool.submit(() ->
                            explicitLeaf("worker", true));
                    explicit.get();
                } catch (Exception e) {
                    throw new IllegalStateException(e);
                }
            });
            leaf("after");
            System.out.println("final-depth=" + Flow.depth());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy trên JDK 17:

~~~bash
javac --release 17 DynamicFlowCostDemo.java
java DynamicFlowCostDemo
~~~

**Stdout chính xác đã được kiểm chứng:**

~~~text
leaf:outside cflow(top)=false depth=0
top: active=true depth=1
leaf:inside cflow(top)=true depth=1
leaf:nested cflow(top)=true depth=2
leaf:before-error cflow(top)=true depth=2
caught=boom
leaf:restored cflow(top)=true depth=1
worker: cflow(top)=false
explicit:worker underTop=true
leaf:after cflow(top)=false depth=0
final-depth=0
~~~

### 8.1. Outside và inside

Trước khi Flow.within("top") được gọi, ThreadLocal chưa có stack nên active("top") false. Sau push("top"), nó true; depth là 1.

### 8.2. Nested context và recursion

Trong Flow.within("nested"), stack có ["nested", "top"]; active("top") true, depth 2. Việc một marker cũ vẫn active khi có marker mới bên trên là điều ta muốn quan sát ở một flow-membership demo.

Nếu dùng cflowbelow thật, cần thêm logic nhận diện current join point và anchor activation, không chỉ tìm marker trong stack.

### 8.3. Exception không làm rò context

Inside scope "fail", body throw "boom"; finally pop fail, khôi phục top. Vì vậy ngay sau catch, active("top") vẫn true và depth về 1. Khi top scope kết thúc, pop cuối cùng rồi remove ThreadLocal, depth về 0.

### 8.4. Async worker không có marker

Executor worker chạy trên thread khác, nên Flow.active("top") false dù caller vẫn đang trong top scope. Đây là kết quả **của mô hình ThreadLocal ở demo**, không tuyên bố mọi AOP engine luôn tạo worker có semantics giống vậy. Một hệ thống async-aware có thể truyền context bằng cơ chế khác.

### 8.5. Phương án truyền tường minh

Caller truyền underTop=true cho task, nên worker in **explicit:worker underTop=true** mà không cần flow stack. Trong thực tế nên dùng **một immutable context object** có các thuộc tính cần thiết thay vì truyền một boolean mơ hồ nếu có nhiều điều kiện.

### 8.6. Kết quả này không phải benchmark

Ví dụ có println và Future.get, không đo overhead hiệu năng. Số depth là minh họa kỹ thuật chứ không phải duration. Không dùng số dòng output để suy dynamic pointcuts tốn bao nhiêu nanoseconds.

## 9. Phương án đơn giản hơn 1: pointcut tĩnh theo type/method/annotation

Nếu yêu cầu chỉ là “log mọi lời gọi vào những operation xử lý import”, bạn có thể chọn **method execution** hoặc **annotation** phù hợp ở một entrypoint thay vì kiểm tra cflow ở từng helper.

~~~text
@ObservedImport
importBatch()
    -> validate()
    -> persist()
~~~

Đoạn này là sơ đồ, không phải Java runnable với một annotation đã định nghĩa.

Một static matcher có thể áp advice cho **importBatch** một lần:

- Ghi start timestamp.
- Ghi result/failure.
- Ghi số bản ghi xử lý.
- Kết thúc trong finally.

Nếu không cần log từng helper, đây có thể là giải pháp **nhỏ hơn, dễ test hơn và ít candidate checks hơn**.

### 9.1. Hạn chế của phương án tĩnh

Nếu business requirement thực sự cần chặn riêng normalize() chỉ khi nó được gọi gián tiếp từ importBatch(), static method matcher **không đủ thông tin** để phân biệt call paths. Không được thay yêu cầu mà không xem semantics. Có thể cần refactor service boundary hoặc explicit context.

### 9.2. Annotation không tự bằng dynamic control flow

Annotation đặt ở entrypoint là metadata tĩnh. Nếu helper cần biết nó đang xử lý một operation có annotation ở ancestor, vẫn phải có context propagation hoặc một cơ chế khác, trừ khi bạn chỉ cần quan sát entrypoint.

## 10. Phương án đơn giản hơn 2: truyền context qua tham số

Thay vì để helper đoán lịch sử call stack, bạn có thể truyền context tường minh.

~~~java
record OperationContext(String correlationId,
                        boolean importMode) {}

void normalize(String row, OperationContext context) {
    if (context.importMode()) {
        // Hành vi được chọn theo context đã truyền.
    }
}
~~~

Đây là snippet minh họa, cần class/import context và phần thân đầy đủ nếu muốn biên dịch độc lập.

Lợi ích:

- Dễ nhìn dependency từ signature.
- Test trực tiếp từng mode.
- Không phụ thuộc hình dạng call stack.
- Dễ chuyển qua Executor/CompletableFuture hoặc RPC khi đã thiết kế serialization/bảo mật.
- Có thể dùng immutable context và giảm hidden mutable state.
- Không cần instrument mọi candidate pointcut.

Chi phí đánh đổi:

- Phải cập nhật signatures hoặc truyền qua nhiều cấp.
- Có thể làm API dài nếu context quá lớn.
- Caller có thể truyền context giả nếu đó là thông tin bảo mật không được xác thực.
- Dữ liệu context có thể nhạy cảm và cần policy rõ.

**Không chuyển authorization từ một nguồn tin cậy sang một boolean caller tự kiểm soát** khi nó quyết định quyền truy cập. Explicit parameter là lựa chọn kỹ thuật biểu đạt context, không tự thay thế authentication/trust boundary.

### 10.1. Context object thay vì nhiều flags

Nếu nghiệp vụ cần correlationId, tenant, operationKind, traceSpanId, actor và policyVersion, dùng một immutable record/DTO hợp lý hơn bảy boolean rời rạc. Tuy nhiên chỉ đưa các fields thật sự cần thiết; không biến context object thành một “global mutable bag”.

## 11. Phương án đơn giản hơn 3: tách boundary nghiệp vụ

Khi cùng một helper phải xử lý hai hành vi khác nhau tùy call origin, có thể refactor thành hai explicit operations:

~~~text
ImportService.normalizeForImport(...)
EditService.normalizeForEdit(...)
        |
        v
PureNormalizer.normalize(...)
~~~

Thay vì chọn method PureNormalizer.normalize bằng cflow(importBatch), mỗi entrypoint quyết định behavior/correlation một lần rồi chuyển tham số cần thiết xuống pure helper.

Lợi ích:

- Tách trách nhiệm rõ, dễ unit test.
- Core helper có thể trở nên pure/stateless.
- Tránh phụ thuộc vào stack layout.
- Dễ đánh giá đúng các đường async, batch, scheduled.
- Có thể giảm số join points cần instrument.

Đánh đổi: thêm API/layer, có thể gây duplication nếu refactor không tốt; nếu nhiều cross-cutting concerns thực sự không thuộc service boundary nào, AOP vẫn có giá trị.

### 11.1. Không lặp mã chỉ để loại bỏ cflow bằng mọi giá

Một đích thiết kế tốt là **rõ semantics với mức lặp hợp lý**. Nếu việc tách boundary tạo hàng chục wrappers khó duy trì, một dynamic aspect đã được kiểm chứng có thể hợp lý hơn.

## 12. Phương án đơn giản hơn 4: một outer around advice

Nếu chỉ cần biết **một operation hoàn tất thế nào**, thay vì ghi từng inner join point, đặt một around advice ở entrypoint:

~~~text
Around(importBatch):
    start timer
    try:
        result = proceed()
        record completion
        return result
    catch:
        record failure
        rethrow
    finally:
        release scope
~~~

Đây là giả mã, không phải Java độc lập. Một advice như thế đo **toàn bộ thời gian từ entry đến return của continuation mà nó bao**, trong phạm vi synchronous boundary.

Nếu cần đếm records hoặc bytes xử lý, core có thể trả một **summary object** cho outer advice. Không cần cflow instrumentation ở mỗi normalize/encode call.

### 12.1. Khi một boundary chưa đủ

Nếu nghiệp vụ yêu cầu độ trễ từng bước hoặc danh sách các lệnh I/O cụ thể, một outer timer không cho thông tin đó. Có thể thêm một số **explicit spans** tại những đoạn thật sự có ý nghĩa thay vì instrument tất cả inner methods.

## 13. Phương án đơn giản hơn 5: scoped ThreadLocal khi API không thể đổi

Khi phải tích hợp thư viện sâu không nhận context param, một ThreadLocal scope có thể là thỏa hiệp:

~~~text
enter:
    previous = context.get()
    context.set(current)
try:
    proceed()
finally:
    restore previous / remove
~~~

Nếu đây là nhu cầu **truyền một request context giữa các helper trên cùng thread**, scoped ThreadLocal có thể đơn giản hơn một pointcut cflow phức tạp và cho phép helper đọc context chủ động.

Nhưng ThreadLocal **vẫn có overhead và hidden dependency**, không được mô tả là zero-cost hoặc hoàn toàn thay thế được cflow.

### 13.1. Những giới hạn

- Context theo thread, không tự theo một async task trên thread khác.
- Cần restore nested scopes trong finally.
- Thread pool reuse có thể gây leak nếu quên remove.
- Một ThreadLocal chứa mutable shared object vẫn có data race.
- Nếu chỉ cần truy vấn marker cho một condition, stack search có thể đắt hơn counter.
- Nếu nhiều nested scopes mang các values khác nhau, cần semantics của stack/binding rõ.

### 13.2. An toàn khi exception

Một scope utility cần đảm bảo pop/restore khi body throw; demo đã minh họa điều này. Nếu stack.pop hoặc cleanup itself throw, exception gốc có thể bị che; code production cần ownership và error policy phù hợp.

## 14. Phương án đơn giản hơn 6: event/correlation thay cho dynamic stack

Đôi khi yêu cầu ban đầu không phải “có đang trong call stack importBatch không” mà là “mọi event thuộc cùng một logical operation phải có correlation ID”.

Logical operation có thể vượt qua:

- Executor workers.
- Reactive/async continuations.
- Message queues.
- HTTP/RPC boundaries.
- Retries hoặc resumed tasks.

Dynamic call stack là đại diện thiếu chính xác cho logical operation nếu execution phân tán qua nhiều threads/processes.

Một phương án là tạo **correlation context** ở entrypoint, truyền rõ qua các boundaries và ghi structured events:

~~~text
Request creates correlationId = X
  -> sync method event tagged X
  -> enqueue job with validated X
  -> worker event tagged X
  -> remote service event tagged X
~~~

Cách này cần context propagation/security validation, có thể có serialization và truyền dữ liệu; đổi lại không phụ thuộc synchronous call stack.

**Đừng tự tin rằng một trace ID là bằng chứng một method nằm bên dưới cflow anchor.** Correlation là quan hệ logic, còn cflow là quan hệ của active dynamic execution context theo ngôn ngữ AOP.

## 15. So sánh các phương án

| Yêu cầu | Giải pháp thường cân nhắc | Chi phí/giới hạn |
|---|---|---|
| Log toàn operation | Static entrypoint pointcut + around | Không thấy từng inner method |
| Helper cần cờ mode | Explicit parameter/immutable context | Signatures có thể phình |
| Hai workflow có behavior khác | Tách service boundary + pure helper | Thêm API/refactor |
| Library không nhận context param, synchronous thread | Scoped ThreadLocal | Hidden context, cleanup, thread affinity |
| Theo dõi dynamic ancestor join point chính xác | cflow/cflowbelow của engine | Runtime instrumentation và test semantics |
| Correlation qua async/messaging | Explicit correlation propagation | Serialization/trust/observability policy |
| Chỉ đo vài nested phases | Explicit spans/events | Instrument thủ công tại điểm cần |
| Security policy dựa quyền thực | Authorized policy/context từ nguồn tin cậy | Không tin boolean tùy ý của caller |
| Công việc rất nóng/call count lớn | Static matching/refactor hoặc optimized flow | Phải benchmark trước/sau |
| Scope lồng nhau có bindings khác | AOP binding hoặc scoped context object | Semantics nested/recursion phức tạp |

Đây là bảng **định hướng**, không phải quyết định mặc định cho mọi dự án.

## 16. Những yếu tố làm overhead tăng nhanh

### 16.1. Candidate density

Càng nhiều method có thể là candidate cho một dynamic pointcut, càng nhiều lần cần runtime check nếu weaver không loại trừ được chúng từ trước. Có thể giảm candidate set bằng type/package/signature constraints nếu ngôn ngữ AOP hỗ trợ.

### 16.2. Nested anchors

Nhiều dynamic scopes hoạt động cùng lúc có thể đòi hỏi counters riêng, marker bindings hoặc stack nhiều tầng. Nếu một pointcut chỉ cần biết số anchor activations đang active, counter có thể đủ; nếu cần binding của anchor gần nhất, phải giữ thông tin sâu hơn.

### 16.3. Lời gọi cực nhỏ

Một getter vài phép toán có thể không xứng với check/interceptor trên mọi invocation. Nhưng không suy từ source lines: JIT inlining và code generation ảnh hưởng cost đáng kể.

### 16.4. Allocation và boxing

Nếu mỗi match tạo context object, đóng gói primitive hoặc ghi event, allocation có thể đáng kể. Phải phân biệt cost **flow tracking** với cost **logging/serialization**. Tối ưu flow marker nhưng giữ một expensive logger trong hot path có thể không cải thiện đáng kể.

### 16.5. Lock/contention

Nếu dynamic context được lưu trong một shared global map có locking, cost có thể tệ hơn thread-confined state. Nhưng ThreadLocal context lại có các chi phí và propagation constraints riêng. Không đánh đồng “shared” và “thread-local” như hai implementation duy nhất.

### 16.6. Async handoff

Capture/restore context ở mỗi task có chi phí wrapper/allocation, và phải xác định security, tracing, cancellation semantics. Không nên mô phỏng sync cflow như một stack liên tục xuyên thread boundaries nếu ngôn ngữ AOP không định nghĩa điều đó.

## 17. Benchmark công bằng: đo thứ gì?

Một benchmark hợp lý cần trả lời:

1. **Baseline không advice:** cùng nghiệp vụ không dùng dynamic pointcut.
2. **Static advice:** chọn method bằng pointcut tĩnh, cùng advice body.
3. **Dynamic flow advice:** điều kiện cflow/cflowbelow, cùng advice body.
4. **Explicit context:** truy vấn context được truyền, cùng nghiệp vụ quan sát.
5. **Scoped ThreadLocal:** context marker tự quản, cùng độ sâu/candidate count.

Các workloads cần thay đổi:

- Số candidate join points trên một request.
- Số anchor activations.
- Depth của nested scopes.
- Tỷ lệ match/không match.
- Tỷ lệ ngoại lệ hoặc short-circuit.
- Sync versus async boundary.
- Số threads và contention.
- Khối lượng advice body (empty/no-op, counters, logging, I/O).

Chỉ khi so apples-to-apples mới đo được **mức chi phí tăng thêm** do dynamic tracking thay vì do code log khác nhau.

### 17.1. Dùng JMH cho microbenchmark

Để benchmark Java hot paths, JMH có công cụ thiết kế cho warmup, forks, đo throughput/latency và hạn chế dead-code elimination. Cần tránh:

- Đo bằng System.out.println trong vòng lặp.
- Dùng một lần currentTimeMillis rồi coi là accurate.
- Để JIT loại bỏ hoàn toàn work của benchmark.
- So code khác behavior.
- Quên allocation rate, GC và multithreaded scenarios.
- Tổng quát hóa kết quả máy local thành số cố định cho mọi deployments.

### 17.2. End-to-end profiling

Trong hệ thống thật, có thể dùng CPU profiler, allocation profiler, async profiler và tracing phù hợp để xem:

- Thời gian enter/exit flow scope.
- Thời gian pointcut match/check.
- Advice body (logging, serializer, network).
- Allocations thuộc scope/binding.
- GC pressure, p95/p99 latency.
- Lock contention và thread scheduling.

Không nên tối ưu cflow trước khi chứng minh nó nằm trong hot path đáng kể.

### 17.3. Các chỉ số cần báo

Một báo cáo benchmark tốt nêu JDK, hardware, OS, loại engine/weaver, số join points, input size, depth, concurrency, warmup, forks, time unit, confidence interval và test harness. Nếu không có số thực đo, **đừng bịa mức overhead % hoặc nanoseconds**.

## 18. Test correctness cho cflow/cflowbelow

Một test suite nên phân biệt các tình huống:

| Tình huống | Điểm cần xác minh |
|---|---|
| Candidate gọi ngoài anchor | Không match dynamic flow |
| Candidate gọi trong anchor | Match theo cflow yêu cầu |
| Chính anchor join point | Phân biệt cflow với cflowbelow |
| Nested helper | Membership còn active |
| Anchor tự đệ quy | Activation identity và depth |
| Hai anchor lồng nhau | Binding của anchor nào được chọn |
| Target throw | Scope được cleanup trong finally |
| Advice throw trước proceed | Không rò marker |
| Advice throw sau proceed | Marker vẫn cleanup |
| Around short-circuit | Không giả định inner points chạy |
| Around retry/proceed nhiều lần | Số invocations và bindings đúng |
| Thread pool boundary | Không tự suy context được truyền |
| Async completion sau anchor return | Không nhầm stack với logical task |
| Multiple aspect scopes | Precedence và cleanup LIFO |
| Static filter + cflow | Filter không loại nhầm candidates |
| Unmatched hot method | Không thực hiện advice ngoài ý muốn |
| Context leak qua reused thread | Request mới không thấy marker cũ |
| cflowbelow dưới cùng anchor | Kiểm tra excluded anchor đúng semantics |

**Chạy cả negative tests** rất quan trọng. Chỉ thấy advice chạy trong một flow đúng không chứng minh nó **không chạy sai** ở flow khác.

## 19. Tính đúng và an toàn: cflow không phải security boundary tự đủ

Một runtime flow marker có thể bị bypass nếu:

- Caller gọi trực tiếp target ở một đường không đi qua anchor mong muốn.
- Proxy-based interception không quan sát self-invocation ở những method nhất định.
- Call tree được tách ra async và marker không được propagate.
- Exception làm scope restore sai.
- Reentrant flow trộn thông tin hai anchors.
- Code không đáng tin điều khiển được boolean context dùng thay security policy.

Nếu advice mang tính bảo mật bắt buộc, chỉ dùng “đang trong luồng gọi X” không tự xác minh quyền của actor. Cần authentication, authorization và kiểm tra resource invariant ở boundary đáng tin.

### 19.1. Context binding có thể chứa dữ liệu nhạy cảm

Flow binding có thể lưu user ID, tenant ID hoặc token. Không log/copy context indiscriminately vào shared caches, task queues hoặc diagnostic errors. Chọn context fields tối thiểu và phân biệt trusted versus untrusted sources.

## 20. Retry, transaction và lifecycle

Giả sử dynamic flow scope bao một transaction/retry chain:

~~~text
FlowAnchor(
    Retry(
        Transaction(
            Business
        )
    )
)
~~~

Nếu retry gọi proceed ba lần, FlowAnchor có thể chỉ push một marker cho toàn request, nhưng Business có thể execute ba lần. Một cflow pointcut trên nested operations có thể match ở cả ba attempts; metrics bên trong có thể ghi ba events.

Nếu thay thứ tự:

~~~text
Retry(
    FlowAnchor(
        Transaction(
            Business
        )
    )
)
~~~

Mỗi attempt có thể enter/exit một flow scope riêng. Chi phí tracking và ngữ nghĩa correlation khác nhau. Nếu binding chứa attempt ID, scope per-attempt có thể rõ hơn.

### 20.1. Transaction scope khác flow scope

Transaction state có isolation, commit/rollback rules và thread/resource ownership. Chỉ vì một cflow marker active không chứng minh DB transaction vẫn mở, hoặc một async task đã nằm trong cùng transaction. Các contexts có vòng đời và guarantees khác nhau.

### 20.2. Lỗi khi cleanup

Scope marker phải được restore/pop trong finally khi continuation throw. Nhưng finally itself có thể throw, che lỗi target. Một helper production nên có invariants rõ, nested restoration, error handling phù hợp và tests với failure injection.

## 21. Reentrancy và recursion

Cflow có thể trở nên khó reasoning khi anchor gọi lại chính nó hoặc một advice kích hoạt method nằm trong pointcut của nó.

~~~text
importBatch()
  -> helper()
      -> importBatch()       <-- nested anchor
          -> helper()
~~~

Nếu theo dõi bằng boolean active, không thể phân biệt depth 1 và 2. Nếu scope trong set false khi rời nested anchor, outer anchor vẫn đang hoạt động nhưng marker bị tắt sai. Vì vậy counter/stack với enter++ và exit-- theo LIFO có lợi hơn boolean naive trong nested/recursive scenarios.

Một ThreadLocal stack như demo có thể xử lý nested markers đơn giản, nhưng còn cần semantics chính xác nếu pointcut bind arguments của từng anchor.

### 21.1. Advice tự instrument helper của nó

Một logging advice gọi logger.write(), mà logger.write() cũng được pointcut chọn, có thể gây recursion vô hạn. Cần exclude infrastructure join points, hoặc dùng một reentrancy guard được restore trong finally.

Đây là vấn đề độc lập với cflow overhead, nhưng dynamic flow tracking làm call paths khó đọc hơn nếu scope markers cũng bị advice reenter.

## 22. Quy trình quyết định có dùng cflow không

1. **Viết requirement chính xác:** đang cần lexical location, runtime ancestry hay logical correlation?
2. **Xác định anchor join point:** call hay execution, loại method nào, cflow hay cflowbelow?
3. **Kiểm tra alternative rẻ hơn:** static pointcut, một outer around, explicit context hoặc refactor service boundary.
4. **Xác định số candidates:** những hot methods nào phải kiểm tra runtime?
5. **Vẽ nested/recursive flows:** có binding cần lưu và restore không?
6. **Vẽ async boundaries:** stack flow có kết thúc trước task không?
7. **Định nghĩa error semantics:** marker cleanup khi target/advice throw.
8. **Thiết kế context trust/ownership:** không lộ dữ liệu nhạy cảm.
9. **Viết positive/negative tests:** cả anchor match và excluded anchor của cflowbelow.
10. **Đo baseline:** so static/dynamic/explicit context với cùng business behavior.
11. **Tối ưu điểm nóng được chứng minh:** thu hẹp candidate set hoặc giảm dynamic checks.
12. **Ghi kiến trúc rõ:** khi nào pointcut này cần dynamic control flow, rủi ro còn lại và phương án fallback.

Không chọn một phương án chỉ vì ngắn code nhất. Một annotation gắn ở entrypoint có thể không thay được một policy thật sự dựa trên call ancestry; ngược lại, dùng cflow chỉ để đo tổng thời gian request thường là quá phức tạp.

## 23. Những lỗi thường gặp

**Lỗi 1 — Cflow giống call stack history vĩnh viễn.** Sai: nó gắn với dynamic flow đang active, không ghi nhớ mọi lời gọi trong quá khứ.

**Lỗi 2 — Cflowbelow chỉ cần kiểm tra boolean active.** Không đủ để exclude anchor join point chính xác.

**Lỗi 3 — Mọi cflow check phải duyệt toàn bộ Java stack.** Implementation có thể dùng counter/optimized instrumentation.

**Lỗi 4 — Mọi cflow check luôn O(1).** Các bindings/scopes/stack searches có thể phức tạp hơn.

**Lỗi 5 — ThreadLocal tự theo Executor workers.** Không đúng mặc định.

**Lỗi 6 — Dùng InheritableThreadLocal giải quyết hoàn toàn thread pools.** Worker reuse và timing làm kết quả dễ sai.

**Lỗi 7 — Quên pop/remove sau exception.** Dẫn đến context leak sang request khác.

**Lỗi 8 — Dùng một boolean cho recursive anchors.** Nested scope exit có thể tắt marker khi outer scope vẫn active.

**Lỗi 9 — Đo bằng println rồi kết luận overhead của cflow.** Logging I/O che gần hết overhead tracking.

**Lỗi 10 — Static matcher không có runtime cost.** Advice body và runtime guards khác vẫn có thể tốn.

**Lỗi 11 — Dùng cflow cho mọi helper thay vì instrument một operation boundary.** Có thể làm tăng candidate checks và khó bảo trì.

**Lỗi 12 — Truyền mutable context object cho async workers không synchronization.** Có thể tạo data race.

**Lỗi 13 — Coi correlation ID tương đương cflow ancestry.** Một ID có thể trải qua threads/processes ngoài call stack.

**Lỗi 14 — Coi cflow là authentication/authorization.** Dynamic ancestry không tự chứng minh caller có quyền.

**Lỗi 15 — Không test negative flows.** Advice có thể match sai ở những callers khác.

**Lỗi 16 — So overhead mà không giữ advice body giống nhau.** Benchmark không cô lập dynamic tracking.

**Lỗi 17 — Rely vào type/name của helper để suy logical operation.** Cùng helper có thể được gọi từ nhiều flows.

**Lỗi 18 — Retry không ảnh hưởng metric.** Retry có thể chạy nested pointcuts nhiều lần.

**Lỗi 19 — Context không cần restore khi nested scopes.** Outer context có thể bị xóa hoặc thay bằng inner value.

**Lỗi 20 — Java ThreadLocal stack demo là implementation cflow chuẩn.** Nó chỉ minh họa membership, không có compiler join point semantics.

## 24. Câu hỏi ôn tập và đáp án

**Câu 1.** Vì sao method encode có thể match pointcut ở lần gọi này nhưng không match ở lần khác?

**Đáp:** Vì dynamic control flow đang active khác nhau, dù method body giống nhau.

**Câu 2.** Cflowbelow khác cflow ở điểm nào?

**Đáp:** Theo semantics của ngôn ngữ hỗ trợ, cflowbelow loại chính anchor join point và chọn các join points bên dưới; cflow gồm anchor.

**Câu 3.** Vì sao boolean active có thể sai với recursive anchors?

**Đáp:** Nested anchor exit có thể set false trong khi outer anchor vẫn active. Cần counter/stack đúng scope.

**Câu 4.** Chi phí cflow đến từ đâu?

**Đáp:** Anchor enter/exit tracking, runtime membership checks, bindings/context storage, allocations/GC nếu có và advice body.

**Câu 5.** Có bắt buộc implementation duyệt Java stack để check cflow?

**Đáp:** Không. Có thể dùng counter, marker hoặc optimized weaving; phụ thuộc engine.

**Câu 6.** Vì sao dynamic pointcut ở hot helper có thể tốn đáng kể?

**Đáp:** Vì rất nhiều candidate invocations phải chạy runtime check dù chỉ ít flow matches.

**Câu 7.** Khi chỉ cần đo tổng thời gian importBatch, cần cflow ở normalize không?

**Đáp:** Thường không; một outer around advice ở importBatch có thể đủ.

**Câu 8.** Khi helper cần biết importMode, giải pháp nào dễ unit test hơn?

**Đáp:** Truyền một explicit immutable context hoặc parameter nếu thiết kế API cho phép.

**Câu 9.** ThreadLocal context có tự đi qua ExecutorService không?

**Đáp:** Không mặc định. Cần capture/transfer context theo API và restore worker scope.

**Câu 10.** Trong demo vì sao worker cflow(top)=false?

**Đáp:** Worker chạy thread khác và không nhận ThreadLocal marker từ caller.

**Câu 11.** Vì sao Flow.within dùng finally?

**Đáp:** Để pop marker khi body return hoặc throw, tránh giữ state cũ trên reused thread.

**Câu 12.** Cflow có bảo đảm mọi async task sinh bởi importBatch vẫn được match không?

**Đáp:** Không có bảo đảm chung; phải xem language/runtime async context semantics.

**Câu 13.** Một correlation ID bằng nhau chứng minh cùng dynamic call stack không?

**Đáp:** Không. Đó là logical grouping, có thể vượt qua các threads/processes.

**Câu 14.** Cần benchmark những phiên bản nào để so overhead?

**Đáp:** Baseline, static pointcut cùng advice body, dynamic cflow cùng advice body, explicit context và scoped marker nếu liên quan.

**Câu 15.** Vì sao test đúng một case trong anchor chưa đủ?

**Đáp:** Cần đảm bảo các cases ngoài anchor không bị advice chọn nhầm và nested/exception paths đúng.

**Câu 16.** Có thể dùng boolean importMode được caller tự gửi để cấp quyền bảo mật không?

**Đáp:** Không nếu caller không đáng tin. Authorization cần dữ liệu và policy có nguồn tin cậy.

## 25. Sơ đồ tổng kết

~~~text
Requirement: chỉ chạy advice trong luồng import?
                        |
                        v
          Cần biết call ancestry thật?
             /                    \
           KHÔNG                   CÓ
            |                      |
            v                      v
 Static pointcut /         Có thể refactor hoặc
 outer around advice       truyền context rõ?
            |                 /          \
            v               CÓ            KHÔNG
          Ít flow         Explicit        cflow /
          checks          context         cflowbelow
                              |                 |
                              v                 v
                     Dễ qua async        Phải theo dõi flow
                     và kiểm thử         runtime + nested
                              |                 |
                              +--------+--------+
                                       |
                                       v
                        Test failure/recursion/async
                        Measure actual CPU/alloc/GC
                        Preserve security and context
~~~

**Kết luận:** theo dõi ngữ cảnh động bằng cflow/cflowbelow là công cụ diễn đạt mạnh khi advice thật sự cần biết ancestry của join point đang active. Nhưng nó có thể thêm runtime checks, state tracking, allocation và độ phức tạp nested/async. Hãy cân nhắc static pointcuts, một outer around advice, explicit immutable context hoặc refactor boundary trước khi chọn dynamic flow. Nếu vẫn cần cflow, phải làm rõ semantics của anchor/cflowbelow, giảm candidate set, bảo đảm cleanup và **đo overhead trên workload thực** thay vì đưa ra con số không có bằng chứng.

## Tài liệu tham khảo

- [AspectJ Programming Guide](https://eclipse.dev/aspectj/doc/latest/progguide/progguide.html): cflow, cflowbelow, pointcut, advice và dynamic control flow trong một ngôn ngữ AOP cụ thể.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): thread-specific state và lifecycle.
- [Java SE 17 — ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html): stack/deque operations dùng trong demo.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): task execution và worker threads.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): task completion và get.
- [JMH — Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/): thiết kế microbenchmark đáng tin cho JVM.
