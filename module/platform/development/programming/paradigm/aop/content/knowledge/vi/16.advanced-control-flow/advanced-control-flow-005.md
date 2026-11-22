# Ràng buộc dữ liệu giữa các điểm trong cùng ngữ cảnh

## 1. Từ một join point tới nhiều join point có liên hệ

Trong **Aspect-Oriented Programming (AOP)**, một **join point** là điểm/sự kiện mà mô hình AOP cho phép can thiệp, chẳng hạn một lần gọi hoặc thực thi phương thức theo khả năng của công cụ. **Pointcut** chọn những join point phù hợp; **advice** mô tả hành vi thực thi tại các điểm đó.

Bình thường, advice xử lý dữ liệu **của một join point**: tên phương thức, receiver, arguments, return value hoặc exception. Nhưng nhiều yêu cầu xuyên suốt cần gắn dữ liệu thu được ở **điểm A** với hành vi ở những **điểm B, C, D** xảy ra sau đó trong **cùng một ngữ cảnh logic**.

Ví dụ:
- Khi bắt đầu xử lý một đơn hàng, lấy `orderId`.
- Khi gọi các bước `reserveInventory`, `chargePayment`, `publishEvent` bên dưới luồng đó, ghi trace/metric với **cùng orderId**.
- Nếu xử lý đơn hàng B được lồng bên trong đơn hàng A, các join point của B phải dùng ID B; sau khi B kết thúc, các join point tiếp theo của A phải dùng lại ID A.
- Khi xử lý lỗi hoặc trả về, state của flow phải được dọn để tác vụ khác không nhận nhầm ID.

Đây là chủ đề **ràng buộc dữ liệu giữa các điểm trong cùng ngữ cảnh**: dữ liệu ở các join point không còn được xem là những mẩu thông tin độc lập; chúng được kết nối bởi **scope**, **identity** và **lifetime** của một control flow.

> **Cốt lõi:** Muốn một advice ở B dùng đúng dữ liệu thu tại A, phải xác định **A và B thuộc cùng ngữ cảnh nào**, data được **bind** ở đâu, được **truyền hoặc tra cứu** bằng cách nào, gặp flow lồng nhau và bất đồng bộ ra sao, và **khi nào dữ liệu không còn hợp lệ**.

### Mục tiêu học tập

Sau bài học, bạn có thể:
1. Phân biệt binding **argument/receiver/return/exception tại một join point** với **binding xuyên các join point** trong cùng control flow.
2. Hiểu dynamic scope, control-flow pointcut, các khái niệm thường gặp như `cflow`, `cflowbelow` và per-control-flow association ở mức **khái niệm**, không áp cú pháp của một engine thành chuẩn chung.
3. Xác định **root join point**, **descendant join points**, **context identity**, **binding key**, **scope entry/exit**, **ngữ nghĩa nested/reentrant calls**.
4. Thiết kế việc lưu/tra dữ liệu bằng context object, stack, advice state có scope hoặc propagation tường minh.
5. Hiểu tại sao ThreadLocal chỉ tự gắn với **thread**, không tự đại diện **logical request/async operation**.
6. Kiểm soát lỗi context bị trộn khi recursion, retry, callback, thread pool, cancellation và short-circuit.
7. Không biến dữ liệu do join point cung cấp thành **nguồn xác thực quyền** khi không có trusted boundary.
8. Chạy ví dụ **Java 17** dùng JDK dynamic proxy và context stack để chứng minh binding `flowId` giữa các điểm `reserve`, `charge`, nested flow và cleanup sau lỗi.
9. Lập test matrix về scope, value binding, nested flow, error/async và concurrency.

Bài xét **AOP cơ bản và nâng cao nói chung**. Một số kỹ thuật ở đây được hiện thực bằng Java thuần để minh họa semantics; đó không phải tuyên bố mọi AOP engine có cùng pointcut DSL hoặc runtime support.

## 2. “Ràng buộc dữ liệu” có hai cấp độ

### 2.1. Cấp một: binding của chính join point

Giả sử một method:

~~~java
Receipt submit(String orderId, int quantity);
~~~

Một advice ở join point tương ứng có thể cần:
- `orderId` từ argument 0.
- `quantity` từ argument 1.
- Method/receiver.
- `Receipt` sau khi trả bình thường.
- Exception nếu method ném lỗi.

Ở cấp này, ràng buộc thường diễn ra tại **một occurrence**. Công cụ AOP có thể đưa variables ấy tới advice bằng typed parameters, context object hoặc reflection, tùy công cụ.

Không phải công cụ nào cũng cung cấp đầy đủ argument names, generic types, source locations hoặc return values tại cùng loại join point. **Đừng nhầm khả năng đọc metadata của tool với dữ liệu luôn sẵn có trong mọi execution model.**

### 2.2. Cấp hai: binding xuyên nhiều join points

Giả sử một workflow:

~~~text
Workflow.execute(orderId="ORD-7")  <-- root A
  |
  +-- Inventory.reserve(sku="SKU-2")   <-- descendant B
  |
  +-- Payment.charge(amount=100)       <-- descendant C
  |
  +-- Events.publish(type="PAID")      <-- descendant D
~~~

Tại B chỉ có `sku`, tại C chỉ có `amount`, tại D chỉ có `type`. Cả ba vẫn cần `orderId="ORD-7"` từ A.

Nếu mỗi advice chỉ đọc arguments của join point đang chạy, không có lý do B/C/D **tự biết** orderId. Cần một cơ chế liên kết:
- Bind `orderId` ở entry A.
- Lưu trong **context đang active**.
- Đảm bảo B/C/D chỉ được liên hệ tới A khi nằm trong scope phù hợp.
- Tra cứu dữ liệu theo identity/scope.
- Thoát scope và dọn khi A kết thúc.

Khi thiết kế, cần phân biệt **dữ liệu nghiệp vụ phải truyền qua API** với **metadata quan sát/correlation**. Nếu `orderId` quyết định tính đúng đắn của giao dịch, việc đưa nó tường minh vào domain API có thể đáng tin hơn một context ẩn.

## 3. Control flow và “cùng ngữ cảnh” là gì?

**Control flow** có thể hiểu là chuỗi/đồ thị các bước thực thi được liên kết bởi một lần bắt đầu operation. Trong synchronous call stack, điều này thường gần với “những lời gọi diễn ra trong khi method root đang active”. Nhưng ở callback/async systems, một **logical operation** có thể tiếp tục sau khi root method đã return hoặc qua thread khác.

Các khái niệm cần tách:

| Khái niệm | Ý nghĩa | Nguy cơ nhầm lẫn |
| --- | --- | --- |
| **Root join point** | Sự kiện bắt đầu scope muốn theo dõi. | Không phải mọi lời gọi root đều tạo context mới nếu policy khác. |
| **Descendant join point** | Điểm xảy ra trong flow liên quan tới root. | Không nhất thiết đồng nghĩa cùng thread trong hệ async. |
| **Dynamic scope** | Context có hiệu lực trong khoảng execution nhất định. | Không phải lexical scope của source code. |
| **Flow identity** | ID xác định một logical operation. | Một thread xử lý nhiều operations nối tiếp. |
| **Context frame** | Data gắn với một lần vào flow, gồm ID và metadata. | Cần tách biệt khi nested/reentrant. |
| **Association rule** | Điều kiện B thuộc flow A. | Không tự suy từ tên method hoặc class. |
| **Lifetime** | Khi entry tạo, exit cleanup, task completion. | Method return khác async completion. |
| **Propagation** | Cách context chuyển qua calls/threads/queues. | `ThreadLocal` không tự vượt async boundary. |

### 3.1. Dynamic scope khác lexical scope

**Lexical scope** liên quan vị trí viết code, block, variable ở source. **Dynamic scope** liên quan flow **thực tế đang chạy** tại runtime.

Một helper method được khai báo trong class độc lập vẫn có thể chạy bên trong flow A và dùng correlation của A. Ngược lại, một method được gọi tên giống nhau nhưng chạy bên ngoài A **không được tự nhận** context của A.

### 3.2. Cùng thread chưa đủ chứng minh cùng flow

Một worker thread xử lý request A, sau đó tái sử dụng cho request B. Nếu context A không được dọn, B có thể nhận nhầm orderId của A. Đây là lỗi **context bleed**. Vì vậy không thể định nghĩa flow là “mọi thứ xảy ra trên cùng thread mãi mãi”.

### 3.3. Cùng flow có thể vượt qua nhiều threads

Một operation thực hiện `submitAsync` có thể tạo task ở executor và callback trên worker khác. Logical flow có thể giữ nguyên ID qua các chặng, nhưng ThreadLocal của caller không được tự động truyền tới worker. **Propagate context theo task** mới duy trì đúng binding.

### 3.4. Đường gọi không qua proxy có thể làm mất binding tại các điểm cần quan sát

Nếu engine chỉ chặn proxy invocation, target tự gọi `this.step()` có thể không tạo event cho handler. Dù context vẫn active, advice tương ứng **không chạy** tại step ấy. Phải tách **scope tồn tại** với **join point thực sự được intercept**.

## 4. Các kiểu control-flow pointcut và ràng buộc theo ngữ cảnh

Một số mô hình AOP nâng cao dùng khái niệm **control-flow pointcut**:
- Chọn những điểm xảy ra **trong control flow** của một điểm root.
- Trong một số ngôn ngữ/công cụ, có cách phân biệt **gồm cả root** và **chỉ các điểm bên dưới root**.
- Có thể bind dữ liệu từ root vào advice áp dụng cho những join points xuất hiện bên dưới.
- Một số mô hình có instantiation scope **per control flow** để các occurrences liên quan dùng cùng aspect state.

Những tên được gặp trong tài liệu AOP là `cflow` và `cflowbelow`. **Chúng được nêu như khái niệm**, không phải cú pháp chung mọi công cụ AOP đều hỗ trợ. Ngữ nghĩa chính xác về root, call/execution join points, data binding, nested flows, precedence và tối ưu hóa phụ thuộc engine.

### 4.1. Vì sao phân biệt gồm root và chỉ descendants?

Giả sử root là `execute(orderId)`:
- Nếu ràng buộc scope gồm root, advice có thể áp dụng ngay tại `execute`.
- Nếu chỉ áp dụng **bên dưới root**, advice được chọn tại `reserve`, `charge`, v.v., nhưng không chọn root theo chính điều kiện control-flow đó.

Khác biệt này quan trọng để tránh ghi metric root hai lần hoặc chạy policy ở điểm root khi chỉ định áp vào các bước con.

### 4.2. Join point kind vẫn quyết định data binding

Một **method-call join point** có thể thấy caller/receiver theo mô hình ở call site. Một **method-execution join point** xảy ra khi method body bắt đầu, có thể quan sát target receiver và arguments tại execution. Các engine có loại join point và semantics `this`/`target` khác nhau.

Không mặc định:
- `this` ở call point luôn là object target.
- Arguments của root có sẵn với mọi descendant bằng magic.
- Return value của root có sẵn trước khi root kết thúc.
- Một pointcut được match bằng method name đủ để suy flow identity.

### 4.3. Dữ liệu tại root có thể được giữ trong aspect state

Mô hình khái niệm:

~~~text
Root enter (orderId)
    |
    +--> create FlowContext(orderId, id, startTime)
            |
            +--> Descendant B advice: currentContext.orderId
            +--> Descendant C advice: currentContext.orderId
            +--> Descendant D advice: currentContext.orderId
    |
Root exit (normal / throw)
    |
    +--> pop/close FlowContext
~~~

Nếu context object giữ mutable fields, phải xác định nó dùng trong một thread, nhiều threads hay nhiều nested calls. Không chọn shared singleton field `currentOrderId` để biểu diễn dữ liệu của mọi flows đồng thời.

## 5. Dữ liệu nào nên bind giữa các join point?

Không phải cứ nhận được dữ liệu là nên truyền xuyên toàn bộ flow.

| Loại dữ liệu | Ví dụ | Lưu ý |
| --- | --- | --- |
| **Correlation ID** | `operationId` hoặc `traceId`. | Có thể truyền qua boundaries; giới hạn độ dài và format. |
| **Định danh nghiệp vụ** | `orderId`, `customerId`. | Không thay thế validation/authorization. |
| **Chính sách đã xác thực** | Tenant ID được trusted entrypoint xác định. | Phải bảo toàn trust boundary, chống spoofing. |
| **Timestamp** | `startedNanos`, deadline. | Monotonic time cho duration trong cùng JVM. |
| **Attempt number** | Retry attempt hiện tại. | Phân biệt per-attempt với per-logical-operation. |
| **Kết quả của bước trước** | Status từ reserve để annotate charge. | Nếu ảnh hưởng correctness, ưu tiên API/domain dataflow rõ. |
| **Error context** | Failure type, stage name. | Tránh giữ Throwable/stack/args lâu. |
| **Resource handle** | Transaction/lock/stream. | Cần owner, scope và concurrency contract rất chặt. |
| **Baggage/metadata** | Locale, trace tags. | Bounded size, không lộ secrets. |

### 5.1. Correlation khác quyền truy cập

Nếu một caller có thể tự chọn `traceId="admin"`, ID đó không chứng minh caller là admin. Tương tự `orderId` trong log không chứng minh được phép đọc/ghi order đó.

Một aspect binding dữ liệu để observability **không tự tạo security context đáng tin**. Principal/tenant phải đến từ authentication/trusted boundary, được xác thực và propagate qua những điểm đã kiểm soát.

### 5.2. Đừng đặt bí mật vào context toàn cục

Nếu context chứa access token, raw payment details hoặc object request lớn, nó có thể được ghi log, capture bởi callback hoặc giữ trong registry lâu hơn cần thiết. Dùng **ID an toàn, immutable snapshot tối thiểu, masking và TTL**.

### 5.3. Dữ liệu bất biến là lựa chọn mặc định tốt

Một context kiểu `record FlowId(String value)` hoặc record lưu correlation ID/tenant đã xác thực giúp giảm race. State cần tăng đếm hoặc thay đổi ở các join point nên có owner và synchronization rõ. Không biến cả context thành mutable `Map<String,Object>` không kiểm soát nếu có thể thiết kế schema typed.

## 6. Mô hình ràng buộc: capture → associate → read → close

Một quy trình đáng tin có bốn giai đoạn:

1. **Capture tại A:** đọc dữ liệu từ occurrence root, validate dạng và xác định flow identity.
2. **Associate:** tạo một context frame hoặc chọn context đang có theo chính sách nested/reentrancy.
3. **Read tại B/C/D:** xác minh join point thuộc đúng scope, tra đúng context và dùng dữ liệu mà không mutate bừa bãi.
4. **Close:** khi root scope kết thúc theo semantics đã công bố, pop/restore context và dọn resource, kể cả khi error.

Một bước bổ sung thường cần với async là **propagate** context snapshot từ task cha sang task con có chủ đích, rồi close/restore tại mỗi worker boundary.

### 6.1. Validation ở root

Nếu root nhận `orderId=null`, cần quyết định:
- Từ chối operation trước khi mở context?
- Sinh internal correlation ID riêng nhưng vẫn giữ domain ID nullable?
- Trả failure rõ ràng?

Không tự chuyển `null` thành `"unknown"` rồi để policy nghiệp vụ dùng nó như orderId hợp lệ.

### 6.2. Association key

Không dùng ID chuỗi đơn thuần làm bằng chứng “hai operations là một flow”: hai invocations có thể cùng orderId nhưng là hai attempts độc lập. Thường cần một **flow occurrence ID** khác `orderId` domain.

### 6.3. Không đọc context ngoài scope

Một advice tại descendant có thể:
- **Reject** nếu không có context (khi binding là bắt buộc).
- **Skip instrumentation** nếu context là optional observability.
- Tạo context mới nếu contract cho phép (nhưng phải tránh biến mọi helper thành root).

Chính sách phải rõ, test được, không âm thầm mượn context từ request trước.

## 7. Nested flows, recursion và stack ngữ cảnh

Một flow A có thể mở flow B trước khi A kết thúc:

~~~text
A begin / context A
  A.step1             -> A
  B begin / context B
    B.step1           -> B
  B end / pop B
  A.step2             -> A (phải restore)
A end / pop A
~~~

Nếu dùng một field global `currentId`, B ghi đè A. Sau khi B kết thúc, A.step2 có thể bị gán nhãn B. Nếu dùng một `ThreadLocal<String>` nhưng không lưu giá trị trước khi vào B, lỗi tương tự vẫn xảy ra ở **cùng thread**.

### 7.1. Stack thay vì single current slot

Một **stack các frames** cho phép:
- Push context mới khi vào nested scope.
- Đọc top frame cho chính sách “innermost wins”.
- Pop khi exit và khôi phục parent.
- Đọc ancestor khi chính sách cần quan sát cả flow ngoài.
- Dọn ThreadLocal khi stack trống.

Không phải mọi use case cần stack: nếu API cấm nested operation, có thể reject ngay entry B. Nhưng một mô hình hỗ trợ nesting phải **quy định rõ B độc lập hay kế thừa A**.

### 7.2. Innermost vs ancestor semantics

Khi B nằm trong A:
- **Innermost binding:** B.step dùng ID B, A.step sau B dùng A.
- **Ancestor binding:** một cross-cutting observer của A có thể còn muốn quan sát B.step như hoạt động thuộc flow A ở cấp cao.
- **All active flows:** advice có thể cần biết cả A và B cho tracing span tree.

Đó là các policy khác nhau. Không chỉ có một “context hiện hành” chung đúng cho mọi concern. Có thể lưu một parent pointer hoặc một scoped stack snapshot tùy nhu cầu.

### 7.3. Recursion

Nếu `process(id)` gọi lại `process(id)` đệ quy, hai occurrences có thể cùng **domain ID** nhưng là hai frames khác nhau. Bám theo string `id` sẽ không phân biệt được các mức recursion. Một scope design có thể:
- Tạo frame mới cho mỗi occurrence.
- Dùng cùng logical frame khi recursion được định nghĩa là một operation.
- Gắn child frame chứa parent ID và depth.

Phải nói rõ trước khi viết advice.

### 7.4. Exception phải restore parent context

Nếu B ném exception, `finally` của B vẫn cần pop B. Nếu A bắt lỗi của B và tiếp tục, A.step2 phải lấy context A, không phải B. Nếu A cũng ném lỗi ra ngoài, `finally` của A phải pop A. Đây là lý do các scope APIs thường cần một biên `try/finally`.

## 8. Reentrancy, retry và scope association

### 8.1. Một advice có thể kích hoạt join point khác

Ví dụ advice ghi metric bằng cách gọi `MetricsExporter.record()`, và pointcut lại chọn chính `record`. Một context stack đúng vẫn không tự ngăn **vòng đệ quy instrumentation**. Cần loại trừ các điểm instrumentation hoặc có guard scoped với cleanup.

### 8.2. Retry tạo những điểm lặp lại trong một flow

Một operation `charge` có thể được retry ba lần:
- **Logical flow ID** vẫn là một.
- **Attempt ID** phải khác nhau nếu muốn đo từng lượt.
- Data của attempt trước không được ghi đè dữ liệu logical flow sai phạm vi.

Một thiết kế hay dùng hai tầng:
- Flow context: `operationId`, `tenantId`, `deadline`.
- Attempt context: `attemptNumber`, `startedNanos`, `failureType`.

Nếu aspect metric nằm trong retry, nó có thể chạy mỗi attempt; nếu ngoài retry, có thể đo một logical operation. Ordering phải tường minh, không suy từ tên class.

### 8.3. Không gọi continuation nhiều lần nếu engine không hỗ trợ

Một số around-advice models cho phép `proceed` nhiều lần, số khác có hạn chế. Đừng mặc định mọi AOP engine triển khai retry bằng cách gọi lại continuation như một function tự do.

Ngay cả khi kỹ thuật cho phép, business operation phải có idempotency/attempt semantics phù hợp.

## 9. Java 17 runnable: bind flow ID giữa reserve và charge

Ví dụ sau cố ý dùng **Java thuần** để minh họa cơ chế control-flow data binding, không dựa vào một AOP engine cụ thể:

- `FlowScope.run(flowId, action)` đại diện **điểm root mở ngữ cảnh**.
- `FlowScope` dùng `ThreadLocal<Deque<Frame>>` quản lý stack context của synchronous flow.
- `Steps` là interface cho hai bước `reserve` và `charge`.
- JDK dynamic proxy chặn mỗi lời gọi qua proxy, đọc **top context frame**, tăng step count và ghi log gồm `flowId`.
- `run("A")` mở flow A, sau đó `run("B")` lồng trong A: B dùng ID B, quay lại A thì A dùng ID A.
- Flow C ném lỗi từ target: `finally` vẫn pop context.
- Lời gọi tới proxy sau khi không còn flow bị từ chối thay vì mượn context rác.

Tạo tệp **`FlowDataBindingDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.ArrayDeque;
import java.util.Deque;

public class FlowDataBindingDemo {
    interface Steps {
        void reserve(String sku);
        void charge(int amount);
    }

    static final class Target implements Steps {
        @Override
        public void reserve(String sku) {
            System.out.println("TARGET reserve " + sku);
            if ("FAIL".equals(sku)) {
                throw new IllegalArgumentException("reservation failed");
            }
        }

        @Override
        public void charge(int amount) {
            System.out.println("TARGET charge " + amount);
        }
    }

    static final class FlowScope {
        static final class Frame {
            final String flowId;
            int steps;

            Frame(String flowId) {
                this.flowId = flowId;
            }
        }

        private static final ThreadLocal<Deque<Frame>> ACTIVE =
                new ThreadLocal<>();

        static Frame requireCurrent() {
            Deque<Frame> stack = ACTIVE.get();
            if (stack == null || stack.isEmpty()) {
                throw new IllegalStateException("no active flow");
            }
            return stack.peek();
        }

        static void run(String flowId, Runnable action) {
            if (flowId == null || flowId.isBlank()) {
                throw new IllegalArgumentException("invalid flow ID");
            }
            Deque<Frame> stack = ACTIVE.get();
            if (stack == null) {
                stack = new ArrayDeque<>();
                ACTIVE.set(stack);
            }

            Frame frame = new Frame(flowId);
            stack.push(frame);
            System.out.println("BEGIN " + flowId);
            try {
                action.run();
            } finally {
                Frame popped = stack.pop();
                System.out.println("END " + popped.flowId
                        + " steps=" + popped.steps);
                if (stack.isEmpty()) {
                    ACTIVE.remove();
                }
            }
        }
    }

    static Steps observed(Steps target) {
        return (Steps) Proxy.newProxyInstance(
                Steps.class.getClassLoader(),
                new Class<?>[] { Steps.class },
                (proxy, method, args) -> {
                    FlowScope.Frame frame = FlowScope.requireCurrent();
                    int step = ++frame.steps;
                    System.out.println("BIND " + frame.flowId + " "
                            + method.getName() + " arg=" + args[0]
                            + " step=" + step);
                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException wrapped) {
                        throw wrapped.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        Steps steps = observed(new Target());

        FlowScope.run("A", () -> {
            steps.reserve("SKU-A");
            FlowScope.run("B", () -> steps.charge(20));
            steps.charge(10);
        });

        try {
            FlowScope.run("C", () -> steps.reserve("FAIL"));
        } catch (IllegalArgumentException failure) {
            System.out.println("FLOW failed " + failure.getMessage());
        }

        try {
            steps.charge(5);
        } catch (IllegalStateException failure) {
            System.out.println("OUTSIDE blocked " + failure.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac FlowDataBindingDemo.java
java FlowDataBindingDemo
~~~

**Stdout kỳ vọng, chính xác theo thứ tự của ví dụ tuần tự:**

~~~text
BEGIN A
BIND A reserve arg=SKU-A step=1
TARGET reserve SKU-A
BEGIN B
BIND B charge arg=20 step=1
TARGET charge 20
END B steps=1
BIND A charge arg=10 step=2
TARGET charge 10
END A steps=2
BEGIN C
BIND C reserve arg=FAIL step=1
TARGET reserve FAIL
END C steps=1
FLOW failed reservation failed
OUTSIDE blocked no active flow
~~~

### 9.1. Điều gì được bind tại root A?

`FlowScope.run("A")` tạo `Frame(flowId="A", steps=0)` và push vào stack của thread. Root là **API tạo scope tường minh** trong demo. Một engine control-flow AOP có thể làm vai trò tương tự bằng advice ở root join point nếu hỗ trợ.

Ở `steps.reserve("SKU-A")`, target chỉ nhận SKU-A; proxy advice tra `Frame` và bind thêm ID A cho log. Không có chuyện `reserve` tự nhận parameter `flowId` từ chữ ký của nó.

### 9.2. Vì sao nested B không làm A mất ID?

Khi vào `FlowScope.run("B")`, stack lúc đó có A. Push B khiến B thành top frame; `charge(20)` dùng B và step của B tăng lên 1. Khi B exit, `finally` pop B; A trở lại top, nên `charge(10)` dùng A và step A tăng từ 1 lên 2.

**Giá trị quan trọng không chỉ là ID**, mà là một **context occurrence** với lifecycle độc lập.

### 9.3. Vì sao error không làm context C rò ra ngoài?

`reserve("FAIL")` thực thi target rồi ném `IllegalArgumentException`. Reflective invocation bọc lỗi trong `InvocationTargetException`, proxy handler gỡ cause và ném lại. `FlowScope.run` vẫn vào `finally`, pop C và `ACTIVE.remove()` khi stack trống. Caller in `FLOW failed reservation failed`.

Nếu thiếu cleanup, lời gọi sau flow C có thể nhận nhầm ID C; ví dụ cho thấy sau khi flow đã đóng, proxy từ chối `charge(5)` với `no active flow`.

### 9.4. Step count là state theo frame, không phải global counter

A có hai steps, B có một, C có một. Biến `steps` thuộc **Frame** của flow hiện hành, không nằm trong shared static field `currentSteps`. Vì thế một nested flow không ghi đè counter của parent.

**Giới hạn:** Frame mutable chỉ an toàn dưới giả định code demo chạy synchronous trên một thread. Nếu cùng một logical frame được chia cho nhiều threads, `++frame.steps` không thread-safe; cần synchronization hoặc aggregate phù hợp.

### 9.5. Demo minh họa điều gì và không minh họa điều gì?

**Có thể kết luận:**
- Một root scope có thể cung cấp dữ liệu cho advice của các join points khác.
- Stack context hỗ trợ nested flows và restore parent.
- `finally` cần cho cleanup trên lỗi.
- Proxy có thể enrich log bằng flow ID dù target method không nhận ID ấy.
- Không có active flow thì policy có thể reject thay vì dùng ID cũ.

**Không thể kết luận:**
- Mọi AOP engine có pointcut cú pháp `cflow`.
- ThreadLocal tự propagate qua executor, HTTP client hoặc message broker.
- Direct target call và self-invocation luôn được proxy handler nhìn thấy.
- Flow ID là principal/security authorization token.
- Một mutable Frame có thể chia sẻ vô điều kiện giữa nhiều threads.
- Context binding tự giải quyết transaction/rollback của target.
- JDK proxy trong ví dụ tự động weave method bodies.

## 10. Những cách mang context từ A tới B

### 10.1. Truyền tường minh bằng parameters

~~~java
// Mã minh họa, không phải chương trình độc lập.
void reserve(String orderId, String sku);
void charge(String orderId, int amount);
~~~

Ưu điểm:
- Data dependency hiển thị rõ trong API.
- Compiler và tests thấy những arguments bắt buộc.
- Dễ chuyển qua threads, queues, remote boundaries bằng serialization có kiểm soát.
- Tránh hidden ambient state.

Đánh đổi:
- Nhiều methods phải chuyển parameter mà bản thân chúng không dùng nghiệp vụ.
- Một số metadata observability có thể làm API domain dài không cần thiết.

**Khuyến nghị:** Với dữ liệu quyết định correctness hoặc security, thường nên ưu tiên API/message contract tường minh hoặc trusted context service có hợp đồng rõ, không dựa độc nhất vào interception ẩn.

### 10.2. Per-control-flow aspect state

Một engine hỗ trợ instantiation/association theo flow có thể giữ `orderId` trong một aspect object dành riêng cho flow occurrence. Descendant advice tra aspect instance tương ứng.

Ưu điểm: mô hình hóa trực tiếp “một context cho mỗi flow”. Nhưng:
- Khả năng hỗ trợ tùy engine.
- Need cleanup/association identity rõ.
- Nested flows có thể tạo nhiều instances.
- Async propagation không tự miễn phí.
- Memory retention nếu lifecycle owner giữ state ngoài dự kiến.

### 10.3. ThreadLocal scope stack

Như demo: tốt cho synchronous stack-scoped context trong cùng thread. Cần:
- `try/finally` ở cả success/failure.
- Push/pop hoặc save/restore đúng khi nested.
- Remove khi root exit, tránh thread pool bleed.
- Không dùng như storage lâu dài cho task pending.
- Không dùng ID từ untrusted input làm principal.

### 10.4. Scoped contextual API

Một số môi trường có abstraction scoped context hoặc context propagation riêng. Ý tưởng là tạo scope cho một callback/task rồi khôi phục previous scope, không cần mỗi method nhận thêm argument. **Khả năng và lifetime cụ thể tùy nền tảng**; đừng suy rằng context của synchronous lexical scope sẽ tự chạy theo bất kỳ async callback nào.

### 10.5. Message headers / trace propagation

Qua queue hoặc RPC boundary, có thể truyền correlation ID và một tập metadata nhỏ qua headers/payload. Receiver phải:
- Validate format và trust level.
- Quyết định accept/create flow ID.
- Không truyền secrets tùy tiện.
- Đặt scope trong consumer execution.
- Cleanup sau message handling.
- Cân nhắc retries và message redelivery.

Đó là propagation **bằng dữ liệu**, khác với `ThreadLocal` in-process.

## 11. Bất đồng bộ: một logical flow có thể không còn trên call stack

Tình huống:

~~~text
Thread T1: Root A enters
           creates future/task
           root method returns
Thread T2: task executes B
Thread T3: callback executes C
~~~

Nếu một control-flow pointcut chỉ định nghĩa bằng synchronous call stack, B/C có thể **không còn nằm trong dynamic scope** của root A tại thời điểm chạy. Muốn tiếp tục dùng cùng correlation, phải có **quy tắc nối logical task**.

### 11.1. Capture/restore per task

Mô hình:
1. Tại task creation, lấy immutable snapshot của ID/tenant/trace metadata đã được xác thực.
2. Truyền snapshot theo một task wrapper hoặc message.
3. Khi worker bắt đầu, mở context scope với snapshot.
4. Chạy task.
5. Trong `finally`, restore/remove context cũ của worker.
6. Nếu task spawn tasks khác, quyết định propagate hoặc tạo child span/flow.

Không sao chép nguyên mutable stack đang dùng ở thread cha rồi share giữa threads mà không phân tích concurrency. Dùng một **immutable parent snapshot** cộng child frames riêng, hoặc cơ chế thread-safe được thiết kế theo logical-flow semantics.

### 11.2. Context không đồng nghĩa ThreadLocal snapshot

`ThreadLocal` là cơ chế truy cập state từ **thread hiện hành**. Context snapshot là dữ liệu độc lập có thể truyền rõ. Nhầm hai thứ dẫn tới:
- Async callback không thấy dữ liệu.
- Worker reuse giữ dữ liệu cũ.
- Concurrent tasks cùng sửa một mutable frame.
- Cleanup trên thread khác không xóa ThreadLocal của thread gốc.

### 11.3. Return handle khác completion

Nếu root method trả `CompletionStage<T>`, **scope method invocation** kết thúc khi trả handle, nhưng **logical operation** có thể tiếp tục tới completion. Nếu muốn ghi duration tới task completion, một immutable snapshot và callback observer có thể sống tới khi stage terminal. Không giữ caller ThreadLocal mở vô thời hạn để chờ stage.

### 11.4. Cancellation, timeout và context cleanup

Một task bị cancel/timeout không có nghĩa remote side effect đã dừng. Nếu registry giữ flow states cho tasks pending, phải có owner, deadline, cleanup ở terminal events và giới hạn số entries. Timeout observer không tự bảo đảm context không bị giữ bởi một callback/worker khác còn reachable.

## 12. Thread pool, nested scope và tránh context bleed

Một thread pool có thể chạy A rồi B trên cùng worker:

~~~text
T1 starts A -> context=A
T1 ends A   -> context removed
T1 starts B -> context=B (không phải A)
~~~

Nếu advice chỉ set context mà không restore/remove, B có thể ghi log theo A. Đây không chỉ là thiếu chính xác telemetry mà có thể **rò dữ liệu tenant/user** nếu một policy lầm dùng context đó để ra quyết định.

### 12.1. Restore previous context, không chỉ remove vô điều kiện

Trong nested scope, B đóng xong thì A vẫn active. Nếu B luôn `ThreadLocal.remove()` mà không restore A, advice sau B trong A bị mất liên kết. Stack hoặc save-previous semantics là cần thiết.

### 12.2. Kiểm thử bằng single-thread executor

Để phát hiện bleed, dùng một single-thread executor và hai tasks nối tiếp:
- Task A mở context rồi cố ý ném lỗi.
- Task B kiểm tra lúc bắt đầu không thấy context A.
- Nếu B có context riêng, kiểm B nhận đúng ID B.

Dùng hai threads ngẫu nhiên có thể che lỗi vì task B không chạy cùng worker T1.

### 12.3. Context propagation phải có giới hạn

Không truyền toàn bộ request object, access token, Throwable và mutable object graphs chỉ để ghi correlation ID. Càng nhiều dữ liệu mang theo, càng dễ memory retention và privacy leakage.

## 13. Nhận diện join points cùng flow bằng những tiêu chí nào?

Đừng dựa độc nhất vào **method name** hoặc **object target**:
- Cùng method có thể được gọi bởi nhiều flows.
- Cùng target singleton phục vụ nhiều users đồng thời.
- Một flow có thể gọi nhiều targets.
- Một target có thể thuộc cả parent flow và child flow theo logic.
- Một operation ID có thể lặp qua retries/redelivery.
- Một thread có thể dùng lại cho nhiều operations.

Các tiêu chí thường cần phối hợp:
- **Flow occurrence identity** do root tạo.
- **Scope entry/exit** xác định lifetime.
- **Parent-child relationship** khi nesting hoặc async task fork.
- **Receiver/arguments** của join point hiện hành.
- **Pointcut matching** xác định loại event được can thiệp.
- **Trust boundary** cho fields có tính bảo mật.
- **Explicit propagation** qua async/network.

### 13.1. “Cùng ngữ cảnh” không nhất thiết mọi advice dùng chung mọi field

Tracing muốn parent/child span IDs; metrics muốn aggregate theo logical operation; authorization cần principal đã xác thực; transaction management cần resource ownership và propagation semantics riêng. Không nên xây một context object không kiểu với mọi field rồi cho mọi aspect mutate tùy ý.

### 13.2. Key collision và nested identity

Hai flows có cùng `orderId` không nên bị tự động nhập vào cùng state map. Nếu muốn association theo **logical operation**, dùng unique occurrence/correlation ID riêng; `orderId` là **thuộc tính domain**. Nếu muốn aggregate metrics theo orderId, đó là phép group có ý nghĩa khác và cần giới hạn cardinality.

## 14. Data binding với return và exception xảy ra ở những thời điểm khác nhau

Arguments và receiver của root thường có trước body. Return value chỉ xuất hiện khi method return bình thường; exception có thể xuất hiện khi throw. Descendant B xảy ra **trước khi root hoàn tất**, nên advice B không thể mặc định đọc return value cuối của A.

### 14.1. Binding dữ liệu sớm

Nếu B cần `orderId` từ root args, capture ở entry và lưu vào flow frame. Đừng chờ after-returning của root rồi hy vọng B ở trong body đã nhận được value đó.

### 14.2. Binding dữ liệu từ bước trước

Nếu `reserve` trả `reservationId` rồi `charge` cần ID ấy, có hai hướng:
- **Truyền tường minh** `reservationId` qua domain API.
- Gắn nó vào một flow context typed và có owner, nếu policy cho phép.

Vì đây là **dependency nghiệp vụ**, truyền tường minh thường có lợi cho correctness, transaction tests và khả năng chạy qua threads. Hidden context phù hợp hơn với metadata correlation hoặc concern xuyên suốt.

### 14.3. After-throwing và lỗi bị bắt bên trong

Nếu B ném lỗi nhưng root A bắt rồi return fallback, advice after-throwing của A có thể không nhìn thấy lỗi B. Muốn ghi attempt failure, phải observe tại B hoặc trong scope nhận exception trước khi nó bị catch.

Một flow context có thể giữ failure metadata, nhưng không được để một exception cũ khiến đoạn A tiếp tục thành công bị gắn “failed” không chính xác. Tách **attempt-level** và **final logical outcome**.

## 15. Bảo toàn kiểu dữ liệu và ý nghĩa binding

### 15.1. Định danh phải typed/validated

Một `Map<String,Object>` dùng chung cho `"id"` dễ nhầm orderId với traceId hay tenantId. Dùng typed context fields hoặc value objects để không vô tình ép kiểu/ghi đè.

### 15.2. Không chuyển absence thành success

Nếu không có context, trả string `"unknown"` có thể hợp với logger nhưng không được mang nghĩa ID nghiệp vụ đã được xác minh. Nếu ID bắt buộc, reject bằng lỗi rõ. Nếu optional, ghi nhận absence minh bạch.

### 15.3. Kết quả của advice không được thay đổi ngoài ý định

Một advice chỉ enrich log bằng flowId nên vẫn trả nguyên result của target, truyền exception gốc và không mutate arguments, trừ khi có chính sách transformation đã được công bố. Nếu advice short-circuit hoặc retry, số lần target chạy có thể thay đổi và phải được test.

### 15.4. Không biến exception thành giá trị giả

Một method trả `int` có thể trả `0` hợp lệ. Nếu advice mất context và tự return 0 thay vì báo lỗi, caller có thể tin rằng operation thành công với result 0. Binding failure khác business result.

### 15.5. Mutable context và dữ liệu đồng thời

Nếu nhiều threads cập nhật chung một counter trong flow context, `count++` không atomic. Local per-thread frames giúp tách state nhưng không tự tổng hợp đúng khi một logical flow phân nhánh. Cần hợp đồng merge và primitive đồng bộ phù hợp.

## 16. Ranh giới bảo mật và tính đáng tin cậy của context

### 16.1. Correlation metadata không phải authorization

`tenantId` gửi qua header từ client có thể giả mạo. Nếu một aspect trích tenantId từ header rồi cho tất cả descendant advice dùng nó như sự thật xác thực, ứng dụng có nguy cơ cross-tenant access.

Thiết kế đúng cần:
1. Xác thực tại trusted entrypoint.
2. Xác định principal/tenant được ủy quyền.
3. Tạo trusted context snapshot.
4. Chỉ propagate fields tối thiểu cần thiết.
5. Không cho untrusted data overwrite trusted fields ở descendant.
6. Kiểm tra invariant bảo mật tại boundary thích hợp, kể cả đường bypass proxy.

### 16.2. Không để aspect “thay” validation domain

Một log advice có `orderId` không chứng minh các bước `charge` hoặc `ship` được phép tác động tới order đó. Domain/service layer vẫn phải bảo đảm owner, trạng thái và transaction invariants.

### 16.3. Không log secrets

Khi bind arguments ở join point, dễ vô tình log token, password, card number hoặc payload nhạy cảm. Chọn fields có kiểm soát, masking và bounded sizes. Tránh biến context thành một bảng lưu toàn bộ invocation arguments/results.

### 16.4. Context injection từ external systems

Qua message/RPC, nếu cần chấp nhận trace headers từ caller, tách **external correlation** khỏi **internal authoritative identity**. Không phải trace ID hợp lệ về format là bằng chứng tính xác thực; trust policy phải độc lập với observability.

## 17. Nhiều aspects dùng chung ngữ cảnh: thiết kế owner và precedence

Giả sử có:
- Root binder tạo context.
- Trace advice đọc flowId.
- Metrics advice đọc attemptId.
- Security advice đọc trusted principal.
- Error advice ghi outcome.

Nếu các advice có thứ tự không rõ hoặc scope owner không được phân định, có thể xảy ra:
- Trace chạy trước khi binder tạo frame.
- Metrics đọc attemptId sau khi retry đã pop attempt context.
- Security đọc field untrusted bị overwritten.
- Error observer đóng scope trước khi outer advice đọc final outcome.
- Cleanup chạy hai lần khiến stack underflow.

### 17.1. Xác định lifecycle owner

Một thành phần nên có trách nhiệm mở/đóng root scope rõ ràng. Các descendants chủ yếu **đọc** hoặc tạo child context dưới sự điều phối có chính sách, không tùy tiện pop root frame.

### 17.2. Precedence theo yêu cầu thực tế

Nếu binder là advice bao ngoài descendants, nó cần tạo context **trước khi** descendants chạy và đóng **sau khi** chúng hoàn thành synchronous scope.

~~~text
FlowBinder.before
  -> Trace.before
     -> Step target
     <- Trace.after
FlowBinder.finally: close
~~~

Đây là sơ đồ ngữ nghĩa, không phải cú pháp ordering chung cho mọi AOP engine. Với async task, binder cần kế hoạch completion/propagation tách biệt.

### 17.3. Không dựa vào classpath/order tình cờ

Thứ tự đăng ký, classloader discovery hoặc tên class không phải hợp đồng precedence chung. Nếu engine cung cấp ordering primitives, khai tường minh và integration-test effective order.

## 18. Chi phí và giới hạn của control-flow matching

Chọn join points dựa trên call stack/dynamic flow có thể có thêm chi phí so với kiểm tra chữ ký method tĩnh:
- Theo dõi entry/exit root.
- Tra scope/current frame tại descendant.
- Quản lý nested stack hoặc association.
- Mang context qua async.
- Tạo labels và ghi metadata cho nhiều events.
- Kết hợp với những pointcuts khác khi advisor chain lớn.

Không đoán một con số overhead áp dụng mọi engine. Cần benchmark trên artifact/runtime thật và chọn đúng độ hạt:
- Chỉ bind những join points cần correlation.
- Chỉ mang fields tối thiểu.
- Tránh stack walk sâu hoặc reflection lặp lại khi có thể cache metadata an toàn.
- Tránh log theo mọi item nếu cardinality/throughput không phù hợp.
- Không capture Throwable/arguments lớn trong context lâu sống.

### 18.1. Khi nào explicit arguments tốt hơn?

Nếu `orderId` chỉ cần cho hai methods domain, truyền parameter có thể rõ, nhanh và dễ test hơn hidden flow context. Nếu concern xuyên suốt ở hàng chục services cần trace correlation mà business code không nên nhận tham số chỉ để log, scoped context có thể hợp lý.

Không chọn AOP chỉ vì muốn tránh viết parameter; chọn vì có một **cross-cutting boundary** và hợp đồng propagation rõ.

## 19. Ma trận kiểm thử data binding xuyên join points

| Ca | Thực thi | Kỳ vọng |
| --- | --- | --- |
| **Basic flow** | A → B → C. | B/C lấy đúng dữ liệu từ A. |
| **Outside flow** | Gọi B khi chưa có root. | Reject/skip theo policy; không dùng context cũ. |
| **Nested flow** | A → B(scope) → A. | B dùng B, A được restore sau B. |
| **Nested failure** | B ném lỗi, A catch tiếp tục. | B cleanup; A vẫn đúng ID. |
| **Recursive root** | Root gọi chính root. | Frames/occurrences không bị trộn. |
| **Concurrent flows** | Thread T1=A, T2=B. | A/B không lộ dữ liệu của nhau. |
| **Thread reuse** | Worker A rồi worker B. | B không thấy stale context A. |
| **Async child** | A spawn task trên worker khác. | Context được propagate có chủ đích, không phụ thuộc ThreadLocal tự động. |
| **Async failure** | Child hoàn tất exceptional. | Cleanup/metrics đúng terminal outcome. |
| **Cancellation** | Task bị cancel giữa chừng. | Lifecycle xử lý đúng, không giữ entry vô hạn. |
| **Retry** | B chạy nhiều attempts. | Logical ID ổn định, attempt ID tách. |
| **Short-circuit** | Advice cache return sớm. | Không giả định descendant đã chạy; scope vẫn đóng. |
| **Proxy bypass** | Target tự gọi helper. | Không suy handler nhận invocation chưa đi qua proxy. |
| **Trust** | External user giả tenantId. | Trusted identity không bị override. |
| **Data type** | Root có ID null/invalid. | Không tạo false-valid binding. |
| **Resource** | Context chứa handle. | Owner close đúng và không use-after-close. |
| **Leak** | Nhiều flows liên tiếp. | Stack/registry về trạng thái sạch. |
| **Multi-aspect** | Binder+Trace+Metrics. | Precedence đúng; không double-pop. |

### 19.1. Unit test cho stack

Nếu dùng mô hình giống Java demo, assert:
- Entry root có một top frame.
- Nested entry có hai frames, top là nested.
- Nested exit trả lại top parent.
- Exception vẫn giảm stack depth.
- Root exit làm `ThreadLocal` hết value.
- Ngoài scope, `requireCurrent()` ném đúng lỗi.

### 19.2. Integration test cho engine thật

Một demo JDK proxy không chứng minh control-flow pointcut trong engine khác hoạt động giống hệt. Với công cụ AOP thực, kiểm tra:
- Join-point kind được hỗ trợ.
- Phạm vi root và descendants.
- Include/exclude root.
- Nested scope semantics.
- Data binding từ arguments/root.
- Classloader/weaving/proxy coverage.
- Ordering và error handling.
- Concurrent và async behavior.

### 19.3. Kiểm thử với trạng thái bị lỗi có chủ đích

Inject exception ở:
- Ngay sau tạo frame.
- Trong descendant advice.
- Trong target.
- Trong nested root.
- Trong callback/completion observer.

Sau mỗi case, xác minh context vẫn được restore/close và không che lỗi gốc nếu policy quan sát là best effort.

## 20. Lỗi thường gặp

**“Các methods cùng nằm trong một class nghĩa là chúng dùng chung flow ID.”** Không. Cùng class không xác định dynamic operation.

**“Cùng thread tức cùng request.”** Không với thread pools và tái sử dụng threads.

**“ThreadLocal tự theo request qua CompletableFuture.”** Không. Phải propagate explicitly hoặc qua abstraction có hỗ trợ.

**“Một field `currentOrderId` trong shared aspect là đủ.”** Không với concurrent/nested invocations.

**“Nếu ThreadLocal được dùng thì nested calls tự restore parent.”** Không nếu chỉ set giá trị mới và remove mà không save/stack previous context.

**“Aspect instance per-target nghĩa là per-flow.”** Không. Một target có thể phục vụ nhiều flows đồng thời.

**“`cflow` và `cflowbelow` là cú pháp chuẩn mọi AOP engine.”** Không. Đây là những tên khái niệm được một số mô hình/công cụ sử dụng; cần xem engine cụ thể.

**“Data bind tại root tự động có sẵn tại mọi method descendant.”** Không. Cần association và propagation; event phải được interception.

**“Có correlation ID là đã xác thực principal.”** Không. Correlation và authorization là hai hợp đồng riêng.

**“Cùng orderId nghĩa là cùng invocation.”** Không. Retry/recursion và nhiều operations có thể cùng domain ID.

**“Root return nghĩa là mọi async child đã complete.”** Không. Method return-handle khác logical task completion.

**“Có context thì mọi bước phải được phép ghi vào nó.”** Không. Fields phải có owner, type và mutability policy.

**“Lưu toàn bộ request object giúp tiện debug.”** Có thể gây privacy leak và memory retention; giữ snapshot tối thiểu.

**“Bắt mọi exception rồi return default sẽ giúp cleanup.”** Không. Cleanup dùng `finally`; nuốt lỗi làm thay đổi contract.

**“Đặt một lock quanh toàn flow sẽ luôn an toàn hơn.”** Có thể serialize quá rộng, deadlock hoặc không bao async; chọn synchronization theo invariant.

**“Không thấy log của descendant nghĩa là descendant không chạy.”** Không. Có thể proxy bypass hoặc pointcut không khớp.

**“Chỉ cần test flow thành công.”** Không. Nested/failure/async/cancel/concurrency mới dễ phơi lộ lỗi context.

## 21. Bài tập vận dụng kèm đáp án

### Bài 1 — Root A và step B

`execute("O-1")` gọi `reserve("SKU-9")`. Step advice cần order ID. Nó có thể đọc từ argument của reserve không?

**Đáp án:** Không nếu `reserve` chỉ nhận SKU. Cần root bind ID vào context và descendant advice tra đúng scope, hoặc truyền orderId tường minh trong API.

### Bài 2 — Nested B

Flow A mở B rồi sau B tiếp tục A. Nếu giữ một ThreadLocal String và B overwrite mà không restore A, điều gì xảy ra?

**Đáp án:** Step tiếp theo của A có thể mang ID B hoặc mất context; dùng stack/save-and-restore trong finally.

### Bài 3 — Một orderId, hai attempts

Một charge bị retry, cùng orderId nhưng attempts khác nhau. Dữ liệu nào nên giữ và dữ liệu nào đổi?

**Đáp án:** Logical flow/order ID có thể giữ; attempt number/attempt ID, start time và failure state cần tách cho từng attempt.

### Bài 4 — Sau exception

Flow C ném lỗi từ target. Lời gọi không có root ngay sau đó vẫn thấy ID C. Đây là lỗi gì?

**Đáp án:** Scope cleanup không đúng, dẫn đến context bleed. `finally` phải pop/remove/restore.

### Bài 5 — Async worker

Root trên T1 tạo future chạy T2. T2 đọc `ThreadLocal` thấy null. Có phải ThreadLocal hỏng?

**Đáp án:** Không. ThreadLocal thuộc T1; phải explicit propagate immutable snapshot và mở scope trên T2.

### Bài 6 — Parent và child

Một observer của A cần nhìn mọi steps trong nested B, nhưng step business B phải lấy B. Có thể chỉ dùng top context không?

**Đáp án:** Không nếu cùng lúc cần cả hai viewpoints. Cần parent chain/active stack và quy tắc đọc riêng cho từng concern.

### Bài 7 — Tenant do caller gửi

Một user tự gửi header `tenantId="other"`. Advice gắn tenant này vào context rồi dùng để phân quyền. Sai ở đâu?

**Đáp án:** Trusted identity bị lấy từ dữ liệu chưa xác thực; phải xác thực/ủy quyền ở trusted boundary.

### Bài 8 — Return value của root

Một descendant B xảy ra bên trong root A trước khi A return. Nó có thể dựa vào return value cuối của A không?

**Đáp án:** Không mặc định: return của A chưa có. Nếu cần dữ liệu sớm, capture ở root entry hoặc từ một bước đã hoàn thành.

### Bài 9 — Binding và self-invocation

Target tự gọi `this.inner()`, proxy handler chỉ chặn những lời gọi qua proxy. Vì sao advice inner không log flowId dù ThreadLocal còn active?

**Đáp án:** Handler của proxy không nhận invocation inner; context existence và interception coverage là hai điều kiện riêng.

### Bài 10 — Kiểm chứng flow ID

Có `orderId="O-1"` ở hai requests đồng thời. Dùng `orderId` làm duy nhất key cho context map có an toàn không?

**Đáp án:** Không nếu hai occurrences cần state riêng. Dùng flow occurrence identity và xem orderId là thuộc tính domain.

### Bài 11 — Counter chung async

Một flow fork ra ba workers cùng cập nhật `frame.steps++`. Code có an toàn không?

**Đáp án:** Không, phép tăng trên mutable frame shared có race. Dùng counter/thread-safe aggregation và hợp đồng merge hoặc child frames tách biệt.

### Bài 12 — Context leak trong executor

A throw trên worker, B chạy tiếp cùng worker. B nhận ID A. Test nào bắt lỗi ổn định?

**Đáp án:** Single-thread executor chạy A rồi B nối tiếp, assert B không nhận context A; kiểm cleanup trên error path.

## 22. Checklist thiết kế binding giữa các join points

1. **Root:** Điểm nào tạo flow context và do cơ chế nào intercept?
2. **Join-point types:** Chọn call hay execution; có support root/descendants không?
3. **Scope semantics:** Root có được tính là một điểm được chọn không?
4. **Data source:** Arguments/metadata của root nào là authoritative?
5. **Identity:** Flow occurrence ID tách với domain ID chưa?
6. **Binding key:** Có typed key/record tránh nhầm field không?
7. **Owner:** Ai tạo, ghi, đọc, đóng context?
8. **Nested policy:** Top frame, parent frame hay tất cả ancestors?
9. **Reentrancy:** Recursion có tạo frame mới hay share logical flow?
10. **Concurrent flows:** Hai threads và hai targets có isolation không?
11. **Thread reuse:** Có restore/remove ở mọi exit path không?
12. **Async:** Context snapshot được propagate theo task/queue/RPC thế nào?
13. **Error:** Lỗi ở root/descendant có cleanup và không che exception gốc?
14. **Retry:** Logical ID và attempt ID có phân biệt không?
15. **Completion:** Scope tính tới method return hay async task complete?
16. **Security:** Tenant/principal đến từ trusted boundary, không bị spoof?
17. **Privacy:** Metadata tối thiểu, không log secrets/raw args?
18. **State mutation:** Có synchronization nếu nhiều workers sửa cùng context?
19. **Memory:** Registry/context/task references có TTL và cleanup?
20. **Coverage:** Proxy bypass hoặc weaving scope có làm thiếu descendant events?
21. **Order:** Binder có mở scope trước reader advice và đóng sau đúng mốc?
22. **Testing:** Nested, throw, async, cancel, concurrent, outside-flow đều có test?
23. **Portability:** Những semantics nào phụ thuộc engine AOP cụ thể?
24. **Performance:** Binding lookup, stack tracking, context propagation và metrics overhead đã đo?

## Kết luận

**Ràng buộc dữ liệu giữa các điểm trong cùng ngữ cảnh** là cách nối những join points riêng lẻ thành một luồng quan sát hoặc điều phối có identity chung. Root capture dữ liệu, một cơ chế association đặt dữ liệu vào đúng dynamic scope, các descendant advice tra cứu theo scope ấy, và cleanup/restore kết thúc vòng đời của context trên mọi nhánh success/failure.

Điểm quan trọng nhất không phải chọn một cấu trúc lưu trữ, mà là **định nghĩa đúng “cùng ngữ cảnh”**. Nested flows cần stack hoặc parent relation; concurrent flows cần isolation; async tasks cần explicit propagation; retries cần tách logical-operation data với attempt data; security context cần trusted source; context có data mutable cần owner và synchronization rõ. Với proxy, context có thể tồn tại nhưng join point vẫn không được handler quan sát nếu call path bypass proxy. Với weaving, phạm vi và loại join point quyết định độ phủ. Một giải pháp AOP tốt chỉ làm dữ liệu “đi theo flow” **khi scope, trust và lifecycle thật sự hợp lệ**, không để dữ liệu cũ hoặc dữ liệu của flow khác rò sang lời gọi kế tiếp.
