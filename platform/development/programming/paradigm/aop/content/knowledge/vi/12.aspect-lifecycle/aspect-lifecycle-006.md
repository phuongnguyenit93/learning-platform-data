# Quan hệ giữa vòng đời aspect và đối tượng được can thiệp

## 1. Tư duy cốt lõi

Trong **Aspect-Oriented Programming (AOP)**, aspect mô tả hoặc hiện thực một mối quan tâm xuyên suốt (cross-cutting concern): logging, metrics, tracing, chính sách thực thi, đo thời gian, kiểm soát tài nguyên hay xử lý lỗi ở những **join point** được pointcut chọn. **Đối tượng được can thiệp** (target object) là đối tượng mà hoạt động của nó được quan sát hoặc bao quanh theo cơ chế AOP đang dùng.

Một câu hỏi dễ bị bỏ qua là:

> **Một aspect instance tồn tại bao lâu, nó được dùng chung cho những target nào, trạng thái của nó có tách biệt với từng lần gọi không, và ai chịu trách nhiệm giải phóng khi target hết vòng đời?**

Không có câu trả lời chung cho mọi công cụ AOP. Có hệ thống dùng một aspect instance cho nhiều target; có hệ thống hỗ trợ liên kết một aspect instance theo target/receiver; có hệ thống chỉ quản lý trạng thái trong một invocation; cũng có mô hình gắn trạng thái theo luồng điều khiển hoặc ngữ cảnh thực thi. Thậm chí một aspect khai báo một lần có thể được **dệt vào nhiều join point** mà không đòi hỏi tạo một object aspect Java độc lập cho mỗi lần kích hoạt.

### Mục tiêu học tập

Sau bài học, bạn sẽ:

1. Phân biệt **aspect definition**, **aspect instance**, **target**, **proxy**, **advice invocation** và **state của mỗi lượt gọi**.
2. Hiểu sự khác nhau giữa vòng đời **application/module**, **classloader**, **proxy**, **target**, **thread**, **control-flow scope** và **một invocation**.
3. Phân tích những mô hình scope thường gặp: **shared/per-system**, **per-target**, **per-receiver**, **per-control-flow**, **per-call/per-invocation** mà không mặc định mọi engine hỗ trợ chúng.
4. Biết vì sao **số aspect instances**, **số target objects**, **số proxy objects** và **số advice executions** không nhất thiết bằng nhau.
5. Hiểu ảnh hưởng đến **state, thread safety, reentrancy, memory retention, cleanup, async context, exceptions và kiểm thử**.
6. So sánh vòng đời khi dùng **proxy/decorator** với **source/bytecode weaving**.
7. Chạy một ví dụ **Java 17 tự chứa** mô phỏng shared aspect state, per-target aspect state và per-invocation state bằng JDK dynamic proxy.
8. Thiết kế một chính sách ownership rõ ràng: instance nào được tạo lúc nào, ai giữ reference, state được dọn lúc nào và điều gì được bảo đảm khi target dừng hoạt động.

**Phạm vi:** Đây là kiến thức AOP cơ bản và nâng cao **nói chung**, không suy diễn một cơ chế instantiation/lifecycle cụ thể thành chuẩn bắt buộc mọi công cụ tuân thủ.

## 2. Sáu thực thể cần phân biệt

| Thực thể | Bản chất | Có nhất thiết sống cùng target? |
| --- | --- | --- |
| **Aspect definition** | Khai báo loại hành vi và pointcut/advice, có thể là class, cấu hình hoặc mô tả dùng lúc build. | Không. |
| **Aspect instance** | Một hiện thân runtime giữ logic/state của aspect nếu mô hình cần instance. | Không. Có thể sống lâu hơn/ngắn hơn/nhiều target dùng chung. |
| **Target object** | Đối tượng thực hiện công việc chính. | Là đối tượng có vòng đời riêng của ứng dụng. |
| **Proxy/wrapper** | Đối tượng trung gian nhận lời gọi, có thể giữ target và interceptors. | Có thể có cùng hoặc khác vòng đời với target. |
| **Advice execution** | Một lần chạy hành vi advice khi có join-point occurrence phù hợp. | Có thể xảy ra nhiều lần trong đời một target. |
| **Per-invocation context** | State tạm như start time, trace ID, argument snapshot dùng cho một lượt xử lý. | Thường chỉ sống đến khi lần xử lý kết thúc; async có thể kéo dài đến task completion. |

Ví dụ: ứng dụng có **2 target**, **2 proxy**, **1 aspect instance dùng chung** và **1.000 advice executions** trong một phút. Đây không hề mâu thuẫn. Con số 1.000 là **số lần advice được thực thi**, không phải số lần tạo aspect.

### 2.1. Khai báo aspect không đồng nghĩa đã có runtime instance

Một hệ thống có thể phân tích pointcut ở compile time và chèn logic vào bytecode; một hệ thống khác tạo interceptors ở runtime; một hệ thống khác lại sinh wrapper classes. Do vậy các mốc “aspect được khai báo”, “aspect được đăng ký”, “instance được tạo”, “target được weave” và “advice được chạy” có thể khác nhau.

Không mặc định **đăng ký aspect một lần** nghĩa là đã tạo **một instance cho từng target**. Cũng không mặc định mọi lúc chạy advice cần cấp phát một instance aspect mới.

### 2.2. Aspect không phải target

Aspect thường cung cấp **chính sách xuyên suốt**, không phải bản sao của đối tượng nghiệp vụ. Nếu target bị hủy/không còn reachable, một aspect dùng chung vẫn có thể tiếp tục phục vụ những target khác. Ngược lại, một aspect được gắn riêng với target có thể không còn lý do tồn tại khi target và mapping liên kết của nó được giải phóng.

### 2.3. Interception scope không phải instance scope

Một pointcut rất rộng có thể chọn hàng trăm method, nhưng engine vẫn dùng **một aspect instance** để phục vụ tất cả. Một pointcut hẹp có thể chọn chỉ một method, nhưng method đó được gọi đồng thời bởi nhiều target và có thể cần nhiều state instances. Phân biệt:
- **Điểm nào được chọn?** Pointcut/join-point scope.
- **Aspect state thuộc về ai?** Instantiation/association scope.
- **Sự kiện nào thật sự xảy ra?** Runtime occurrence.
- **State được lưu trong bao lâu?** Lifetime/ownership.

## 3. Những vòng đời liên quan

### 3.1. Vòng đời của application hoặc module

Một aspect instance được tạo lúc application/module khởi tạo có thể phục vụ đến khi module shutdown. Nó thường phù hợp cho hành vi **stateless** hoặc state được đồng bộ hóa/giới hạn hợp lý như counters, configuration snapshot hay thread-safe metrics aggregator.

Nếu aspect giữ reference đến object request/target ngắn hạn trong một field sống suốt ứng dụng, nó có thể vô tình **kéo dài vòng đời** object ấy. Vòng đời dài có lợi cho việc tái sử dụng logic, nhưng yêu cầu kỷ luật state.

### 3.2. Vòng đời của classloader

Một engine có thể dùng cache metadata, aspect instances hoặc registry theo classloader. Với plugin/hot reload, classloader cũ có thể cần được thu hồi; một registry toàn cục giữ `Class`, `Method`, aspect instance hoặc proxy của module cũ có thể góp phần ngăn điều đó xảy ra.

Vì thế “singleton” cần làm rõ singleton **trong phạm vi nào**: một process, một module, một classloader, một registry hay một cấu hình runtime. Không được suy rằng singleton có nghĩa duy nhất trên mọi classloader/process.

### 3.3. Vòng đời của target

Một target có thể được tạo theo request, theo một session, theo một worker hoặc sống lâu như một service. Nếu mô hình AOP gắn aspect **theo target**, số aspect instances có thể tăng khi số target tăng. Tuy nhiên, việc khởi tạo lúc nào và hủy lúc nào còn phụ thuộc cách association và ownership được hiện thực.

### 3.4. Vòng đời của proxy

Một proxy có thể chứa tham chiếu mạnh tới target và một danh sách interceptors. Nếu proxy sống lâu nhưng target về mặt nghiệp vụ đã hết hạn, target vẫn có thể **reachable** qua proxy. Đổi lại, khi proxy chỉ là wrapper dùng trong cùng service lifetime, đó có thể là ownership hoàn toàn hợp lệ.

“Proxy đã được tạo” không đồng nghĩa target body bị biến đổi, và “proxy không còn được dùng” không đảm bảo target được GC ngay nếu còn nơi khác giữ reference.

### 3.5. Vòng đời của thread/control flow

Một aspect hoặc context có thể được tổ chức theo thread hay luồng điều khiển. Đây là hai khái niệm **khác nhau**: một thread pool thread có thể xử lý nhiều requests, và một logical async task có thể chuyển qua nhiều thread. State theo thread không tự trở thành state theo logical request.

### 3.6. Vòng đời của một lần gọi

Một `around advice` có thể tạo biến local `startNanos` cho từng invocation; khi `proceed()` trả hoặc ném lỗi, state tạm thường không còn cần. Dùng local state tránh trộn thời gian bắt đầu giữa các lời gọi đồng thời và không cần thêm aspect instance cho mỗi lượt.

Nếu method trả một future còn pending, **invocation lifetime** có thể kết thúc trước **task lifetime**. State quan sát completion có thể phải sống lâu hơn lời gọi, nhưng chỉ nên giữ một snapshot tối thiểu và có chính sách cleanup rõ.

## 4. Các mô hình liên kết aspect với target

Đây là những **mô hình khái niệm** thường gặp trong nghiên cứu/triển khai AOP; tên cú pháp và điều kiện tạo instance khác nhau giữa các engine.

| Mô hình | Quan hệ với target | Đặc điểm state | Câu hỏi quan trọng |
| --- | --- | --- | --- |
| **Shared / per-system** | Một aspect instance dùng chung cho nhiều target/điểm. | Field instance chia sẻ. | Thread safety, phân nhóm target, rò reference? |
| **Per-target** | Mỗi target đủ điều kiện có state/aspect riêng. | Field theo target. | Association nào xác định target; cleanup khi target hết hạn? |
| **Per-receiver / per-this** | Liên kết với receiver ở một loại join point. | Có thể khác per-target nếu `this` và `target` khác nhau. | Join-point kind nào cung cấp receiver? |
| **Per-control-flow** | Một instance/context theo một luồng điều khiển nhất định. | State theo phiên thực thi được chọn. | Recursion, nested flow và async propagation ra sao? |
| **Per-invocation** | State hoặc instance cho mỗi lần advice chạy. | Không chia sẻ giữa lượt gọi nếu thiết kế đúng. | Cấp phát/cost và lifetime của task? |
| **Per-thread** | Một giá trị/aspect gắn với thread. | Tái sử dụng trong cùng thread. | Thread pool, `ThreadLocal` cleanup, thread migration? |

Một số động cơ AOP có primitive instantiation như per-object hoặc per-control-flow; nhiều động cơ khác **không có loại scope ấy** và người dùng phải tự hiện thực bằng wrapper, mapping hoặc context. Không viết một biểu thức scope như thể nó chắc chắn có ở mọi công cụ.

### 4.1. Shared aspect state: một instance, nhiều target

~~~text
            +-----------------+
Target A -->|                 |
            |  Shared Aspect  | --> advice on selected join points
Target B -->|                 |
            +-----------------+
~~~

Một aspect state có thể giữ cấu hình bất biến và bộ đếm tổng cho mọi target. Nếu aspect chứa field `lastRequest` mutable, request A có thể ghi đè state của B, đồng thời giữ reference đến request cũ lâu hơn mức cần thiết.

**Hợp lý khi:** concern giống nhau cho mọi target, state không cần tách theo target, hoặc state chia sẻ được thiết kế an toàn/giới hạn.

**Cẩn thận:** instance state chia sẻ giữa threads; nhiều advice executions có thể chạy đồng thời. Một counter thường `int count++` không bảo đảm atomic trong concurrent execution.

### 4.2. Per-target state: liên kết một instance theo một target

~~~text
Target A --> Aspect state A
Target B --> Aspect state B
Target C --> Aspect state C
~~~

Ví dụ: muốn đếm số invocation của **từng target**, hoặc cần gắn một context có lifetime cùng target. Cách tạo state có thể lazy khi lần đầu có join point, eager khi wrapper được tạo, hoặc do engine điều phối.

**Không được suy:** “target được tạo là aspect instance chắc chắn được tạo ngay”. Một số hệ thống chỉ cấp phát khi pointcut lần đầu cần hoặc khi một association được thiết lập.

Một mapping per-target không tự bảo đảm state được giải phóng. Nếu global `Map<Target,Aspect>` dùng strong keys và không remove, map có thể giữ target vô hạn. Nếu dùng weak keys, value cũng có thể giữ key gián tiếp; cần xem retained paths.

### 4.3. Per-this khác per-target trong những ngữ cảnh có nhiều receiver

Ở một số join-point models, `this` là đối tượng hiện hành tại vị trí gọi, còn `target` là đối tượng nhận hành vi được gọi. Với **method call join point**, hai vai trò có thể khác nhau; với **method execution**, ngữ nghĩa lại tùy runtime và công cụ.

Ví dụ ý tưởng:

~~~text
Caller C ----calls----> Target T.method()
   |
   +-- this = C ở call-site model được hỗ trợ
                     target = T
~~~

Một state gắn theo caller (per-this) **không đồng nghĩa** state gắn theo callee (per-target). Khi thiết kế per-object aspect, hãy nêu loại join point, nghĩa receiver và quy tắc identity.

### 4.4. Per-control-flow: lifetime theo phiên thực thi, không theo object cố định

Một aspect state có thể bắt đầu khi một control flow cụ thể được chọn rồi dùng cho các join point bên trong luồng ấy. Nếu cùng một target được gọi bởi hai control flows khác nhau, hai state khác nhau có thể cùng tồn tại.

~~~text
Flow 1: operation A -> helper -> target X
         [context flow-1]

Flow 2: operation B -> helper -> target X
         [context flow-2]
~~~

Cần làm rõ khi control flow **bắt đầu và kết thúc**, cơ chế nested/recursive flows và cách engine quản lý context. Đặc biệt trong ứng dụng async, một logical operation chuyển thread có thể không còn phù hợp với quan niệm call stack đơn giản; không tự cho rằng control-flow aspect đi xuyên `CompletableFuture`/executor.

### 4.5. Per-invocation: tách state mỗi lần mà không nhất thiết tạo aspect mới

Nếu chỉ cần đo thời gian:

~~~text
around:
    started = monotonicClock()
    try:
        return proceed()
    finally:
        observeDuration(monotonicClock() - started)
~~~

Chỉ cần biến `started` local là đã có **state riêng cho mỗi invocation**. Không cần tạo một class `TimingAspect` mới cho mỗi lần gọi chỉ để tránh concurrent data races.

Ngược lại, nếu một engine hỗ trợ instance-per-invocation thực, việc tạo instance có thể có chi phí và lifecycle khác. **Per-invocation data** và **per-invocation aspect instance** là hai thiết kế có thể trùng nhau hoặc không.

### 4.6. Per-thread có phải per-request không?

Không. Với thread pool, thread T1 có thể xử lý request A rồi request B. Nếu một `ThreadLocal<Context>` của advice không được `remove()` hoặc restore đúng scope, request B có thể nhìn thấy context A. Một async request cũng có thể sử dụng T1 và T2; một giá trị gắn riêng T1 không tự chuyển đến T2.

Do vậy per-thread phù hợp khi **thật sự cần thread-affine state**, không phải cách mặc định để mô hình hóa mọi logical request.

## 5. Một target có thể có nhiều aspect, một aspect có thể có nhiều target

Cấu hình AOP hiếm khi là quan hệ 1:1 đơn giản.

~~~text
                         +-- Tracing aspect (shared)
Target A --> Proxy A ----|
                         +-- Metrics aspect (shared)
                         +-- State A (per-target)

                         +-- Tracing aspect (shared)
Target B --> Proxy B ----|
                         +-- Metrics aspect (shared)
                         +-- State B (per-target)
~~~

Một lần gọi trên Proxy A có thể kích hoạt cả tracing và metrics; một lần gọi trên Proxy B cũng vậy. Nếu một aspect được chia sẻ, hai target có thể cùng cập nhật số liệu tổng. Nếu một aspect có state per-target, giá trị của A và B tách biệt.

Nhưng **aspect count không quyết định advice count**: nếu A gọi cùng method 50 lần, advice có thể chạy 50 lần; nếu B chưa được gọi thì state B có thể chưa thay đổi. Nếu target A bị gọi trực tiếp bỏ qua proxy, handler có thể không ghi nhận lượt đó, dù body target vẫn chạy.

### 5.1. Thời điểm tạo proxy có thể khác thời điểm tạo target

Một wrapper có thể được tạo khi ứng dụng cấu hình dependencies, còn target đã tồn tại từ trước. Một target khác có thể được tạo theo request rồi được bọc ngay. Một proxy có thể được dùng để đại diện cho nhiều target theo routing logic, tùy cơ chế. Không nhất thiết số lượng proxy = số lượng target.

### 5.2. Aspect được dệt trước runtime có cần instance giống proxy không?

Không nhất thiết. Source/bytecode weaving có thể chèn lời gọi tới logic dùng chung, state static, hoặc một mô hình instantiation do engine quy định. Điểm được biến đổi không bắt buộc lưu reference riêng tới một object aspect cụ thể. Vì vậy khi hỏi “vòng đời aspect”, phải biết engine quản lý **cấu hình/logic** hay **aspect object chứa field**.

## 6. Ownership: ai giữ tham chiếu tới ai?

Vòng đời trong runtime có GC không chỉ phụ thuộc thời điểm constructor chạy. Nó phụ thuộc **reachability** và ownership graph.

Một proxy có thể giữ:
- Target.
- Handler.
- Các aspect/interceptor instances.
- Method metadata, annotation cache hoặc configuration.

Một aspect có thể giữ:
- Registry target → state.
- Listener/subscription.
- Context trong `ThreadLocal`.
- Callback cho future chưa hoàn tất.
- Metrics buffer/cache.
- Last arguments/result/Throwable vô tình sống lâu.

~~~text
Long-lived registry
  -> shared aspect
      -> Map<Target, PerTargetState>
          -> Target A
              -> Large object graph
~~~

Ngay cả khi business logic đã kết thúc sử dụng Target A, một strong reference trong registry vẫn có thể làm A reachable. **GC không xóa một object còn được giữ mạnh chỉ vì domain coi nó đã hết hiệu lực.**

### 6.1. “Đồng vòng đời” không tự xảy ra

Gắn state với target về mặt logic không bảo đảm state sẽ được GC đồng thời với target. Nếu global map giữ strong key là target, target có thể tiếp tục sống nhờ map. Nếu aspect state giữ reference ngược về target, việc chỉ chuyển map thành weak-key map vẫn cần kiểm tra đường giữ reference qua value.

Vòng đời đồng bộ cần được đảm bảo bởi **cách sở hữu reference**, chính sách remove/close hoặc một cấu trúc association có semantics phù hợp — không phải bởi tên “per-target”.

### 6.2. Hủy logic khác thu gom vật lý

Một object có thể được **close/dispose/unregister** tại thời điểm xác định rồi chỉ được GC ở thời điểm bất định. Với tài nguyên như file descriptor, socket hoặc listener, nên có cleanup tường minh theo hợp đồng, không đợi GC. Nếu aspect quản lý một resource dùng chung, **không được đóng nó khi một target ngắn hạn kết thúc** nếu các target khác còn cần.

### 6.3. Không giữ whole target nếu chỉ cần một định danh

Một aspect per-target có thể chỉ cần ghi metric theo **tên loại operation hoặc ID đã giới hạn**, thay vì cất target object vào long-lived map. Nếu cần phân biệt identity mỗi target, cân nhắc id được cấp rõ, weak association hoặc cleanup lifecycle hợp lệ; tránh dùng `System.identityHashCode` làm ID tuyệt đối duy nhất hay ổn định xuyên tiến trình.

## 7. Concurrency khi aspect instance được chia sẻ

Một aspect singleton/shared có thể nhận nhiều invocations đồng thời. Ví dụ sai:

~~~java
class UnsafeTimingAspect {
    long startedNanos;

    void before() {
        startedNanos = System.nanoTime();
    }

    long after() {
        return System.nanoTime() - startedNanos;
    }
}
~~~

Đây là **mã minh họa không độc lập**. Nếu thread A ghi `startedNanos`, rồi thread B ghi đè, A đo thời gian sai. Không nhất thiết cần per-target aspect để sửa: **local variable** trong around invocation sẽ tách riêng lần gọi; nếu cần bộ đếm chung thì dùng primitive concurrency thích hợp.

### 7.1. Khi nào cần synchronization?

- **Config bất biến:** có thể chia sẻ an toàn sau khi publish đúng.
- **Counters chung:** dùng `LongAdder`, atomic variables hoặc đồng bộ hóa phù hợp.
- **State có nhiều field liên quan:** cần bảo đảm invariant, không chỉ mỗi field atomic.
- **Cache:** cân nhắc thread-safe data structure, eviction và cardinality.
- **Per-target state:** vẫn có thể bị nhiều threads truy cập cùng một target; per-target không mặc nhiên thread-safe.
- **Per-invocation local state:** thường cách đơn giản nhất để tránh trộn dữ liệu giữa những lượt gọi.

### 7.2. Có per-target vẫn có race

Nếu 100 threads cùng gọi một target singleton, state riêng của target ấy vẫn dùng chung cho 100 calls. Một counter `int count++` trong per-target aspect có thể mất update. Phạm vi per-target giải quyết **phân nhóm state theo object**, không tự giải quyết **đồng bộ các operations đồng thời**.

### 7.3. Reentrancy và recursion

Aspect của một target có thể tự kích hoạt một method cùng pointcut khi advice gọi logger, metrics hoặc helper:

~~~text
target invocation
  -> advice
      -> metrics.record()
          -> advice
              -> metrics.record()
                  -> ...
~~~

Nếu state được dùng chung hoặc per-target, recursion vẫn có thể xảy ra. Cần tách instrumentation khỏi pointcut liên quan, định nghĩa nested scope và tránh giữ lock khi gọi `proceed()` nếu có nguy cơ deadlock.

## 8. Java 17 runnable: shared, per-target và per-invocation state

Chương trình **`AspectTargetLifetimeDemo.java`** dùng JDK dynamic proxy để mô phỏng ba scope **được thiết kế tường minh**. Đây **không phải** AOP engine hỗ trợ mọi loại per-object/per-control-flow; nó chỉ giúp nhìn thấy **ai sở hữu state** và **state nào dùng lại qua những target/lần gọi khác nhau**.

Thiết kế:

- Có hai target `RealJob("A")` và `RealJob("B")`.
- Cả hai proxy cùng nhận một `AspectState("shared")`.
- Mỗi target proxy có một state riêng: `AspectState("target-A")` hoặc `AspectState("target-B")`.
- Mỗi lần handler được gọi tạo một `AspectState("call")`.
- Các lớp advice bao nhau theo thứ tự **shared → per-target → per-call → target**.
- Một lời gọi trực tiếp vào target A minh họa bypass proxy.
- Một lời gọi ném exception minh họa cleanup/propagation của ba tầng.

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

public class AspectTargetLifetimeDemo {
    interface Job {
        String run(String id);
    }

    static final class RealJob implements Job {
        private final String name;

        RealJob(String name) {
            this.name = name;
        }

        @Override
        public String run(String id) {
            System.out.println("TARGET " + name + " " + id);
            if ("FAIL".equals(id)) {
                throw new IllegalStateException("job failed");
            }
            return name + ":" + id;
        }
    }

    @FunctionalInterface
    interface Proceed {
        Object call() throws Throwable;
    }

    static final class AspectState {
        final String scope;
        int seen;

        AspectState(String scope) {
            this.scope = scope;
        }

        Object around(String operation, Proceed next) throws Throwable {
            seen++;
            System.out.println("ADVICE " + scope + " #" + seen
                    + " " + operation);
            try {
                Object value = next.call();
                System.out.println("RETURN " + scope);
                return value;
            } catch (Throwable original) {
                System.out.println("THROW " + scope + " "
                        + original.getClass().getSimpleName());
                throw original;
            }
        }
    }

    static Object invokeTarget(Job target, Method method, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static Job proxied(Job target, AspectState shared, AspectState perTarget) {
        return (Job) Proxy.newProxyInstance(
                Job.class.getClassLoader(),
                new Class<?>[] { Job.class },
                (proxy, method, args) -> {
                    AspectState perCall = new AspectState("call");
                    return shared.around(method.getName(),
                            () -> perTarget.around(method.getName(),
                                    () -> perCall.around(method.getName(),
                                            () -> invokeTarget(target, method, args))));
                }
        );
    }

    public static void main(String[] args) {
        RealJob targetA = new RealJob("A");
        RealJob targetB = new RealJob("B");

        AspectState shared = new AspectState("shared");
        AspectState stateA = new AspectState("target-A");
        AspectState stateB = new AspectState("target-B");

        Job proxyA = proxied(targetA, shared, stateA);
        Job proxyB = proxied(targetB, shared, stateB);

        System.out.println("CALLER " + proxyA.run("first"));
        System.out.println("CALLER " + proxyB.run("second"));

        try {
            proxyA.run("FAIL");
        } catch (IllegalStateException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        System.out.println("CALLER " + targetA.run("DIRECT"));
        System.out.println("COUNTS shared=" + shared.seen
                + " A=" + stateA.seen
                + " B=" + stateB.seen);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac AspectTargetLifetimeDemo.java
java AspectTargetLifetimeDemo
~~~

Stdout kỳ vọng:

~~~text
ADVICE shared #1 run
ADVICE target-A #1 run
ADVICE call #1 run
TARGET A first
RETURN call
RETURN target-A
RETURN shared
CALLER A:first
ADVICE shared #2 run
ADVICE target-B #1 run
ADVICE call #1 run
TARGET B second
RETURN call
RETURN target-B
RETURN shared
CALLER B:second
ADVICE shared #3 run
ADVICE target-A #2 run
ADVICE call #1 run
TARGET A FAIL
THROW call IllegalStateException
THROW target-A IllegalStateException
THROW shared IllegalStateException
CALLER caught job failed
TARGET A DIRECT
CALLER A:DIRECT
COUNTS shared=3 A=2 B=1
~~~

### 8.1. Vì sao `shared.seen` tăng từ 1 tới 3?

Hai proxy dùng chung **cùng một tham chiếu `shared`**. Ba invocation qua proxy (`A:first`, `B:second`, `A:FAIL`) đều vào `shared.around`, nên counter lần lượt là 1, 2, 3. Không phải chương trình tạo ba aspect shared instances; đây là **ba lần gọi trên một instance**.

### 8.2. Vì sao per-target A và B đếm tách biệt?

`stateA` được đưa vào `proxyA`, `stateB` được đưa vào `proxyB`. Chỉ hai lời gọi qua proxy A nên `stateA.seen=2`; chỉ một lời gọi qua proxy B nên `stateB.seen=1`. Hai target có identity khác nhau, và bài mô phỏng một state owner riêng cho mỗi proxy-target association.

**Lưu ý:** Code này không có registry tự động tìm aspect theo target. Việc gắn per-target được lập trình tường minh ngay lúc gọi `proxied`; một AOP engine thật có thể dùng chiến lược association khác.

### 8.3. Vì sao per-call luôn in `#1`?

Mỗi lần handler nhận một invocation, nó tạo **một `new AspectState("call")` mới**. Mỗi instance chỉ được dùng cho lượt gọi đó nên `seen` bắt đầu 0 và trở thành 1. Đây là **mô phỏng instance-per-invocation**, không phải đề xuất cần tạo aspect mới cho mọi call trong production.

Nếu chỉ đo duration, một biến local `startedNanos` thường đủ và tiết kiệm cấp phát hơn.

### 8.4. Vì sao một lỗi tạo ba dòng THROW?

Các advice được lồng như:

~~~text
shared.around(
    targetA.around(
        call.around(
            target.run("FAIL")
        )
    )
)
~~~

Target ném `IllegalStateException`. Tầng `call` bắt để quan sát rồi ném lại; tầng `target-A` bắt cùng lỗi rồi ném lại; tầng `shared` cũng làm thế. Do đó có **ba log THROW cho một exception crossing ba boundaries**.

Đây không tự tương đương ba failure nghiệp vụ độc lập. Khi đo metric, phải xác định muốn đếm **attempt**, **advice boundary** hay **logical operation**, tránh trùng chỉ vì nhiều aspect cùng quan sát một lỗi.

### 8.5. `targetA.run("DIRECT")` có làm shared count tăng không?

Không. Đây là lời gọi **bỏ qua proxy**, nên cả ba tầng handler/advice không chạy; target vẫn trả `A:DIRECT`. Vì thế cuối chương trình counters là `shared=3, A=2, B=1`, không tính direct call.

Giới hạn này thuộc **JDK delegating proxy demo**. Không suy rằng bytecode weaving trực tiếp vào method execution cũng bỏ qua direct-target call.

### 8.6. Vì sao demo không dùng nhiều threads?

`AspectState.seen` là `int` mutable không có synchronization. Trong **chương trình tuần tự** này, output là xác định và dùng để dạy về scope. Nếu dùng nhiều threads trên cùng `shared` hoặc một `perTarget`, `seen++` có thể race. Trong ứng dụng thực, cần bộ đếm phù hợp concurrency như `LongAdder` hoặc `AtomicInteger` và kiểm soát các bất biến phức tạp hơn.

### 8.7. Demo không thể chứng minh GC hoặc automatic disposal

Việc tạo `AspectState("call")` mỗi lần chỉ minh họa **association/usage scope**. Không có `finalize`, `System.gc()` hay kiểm tra “object đã được thu hồi”: GC không có thời gian chạy xác định. Ngoài ra, `shared`, `stateA`, `stateB`, proxy và target còn các reference trong `main`. Không thể dùng dòng COUNTS làm bằng chứng đối tượng đã bị dọn khỏi heap.

## 9. Vòng đời khi dùng proxy so với weaving

### 9.1. Delegating proxy

Một proxy handler thường giữ reference tới target và các interceptors. Cấu trúc có thể là:

~~~text
Application object graph
  -> Proxy
      -> Handler
          -> Target
          -> Aspect A (shared hoặc per-proxy)
          -> Aspect B
~~~

Nếu proxy vẫn reachable, target thường vẫn reachable qua handler. Nếu một shared aspect nằm trong global registry, nó có thể tồn tại kể cả khi một proxy cụ thể không còn sử dụng.

Lúc target được tạo, chưa chắc proxy đã có. Lúc proxy được dựng, chưa chắc aspect object được tạo tại cùng thời điểm (có thể đã có/shared). Khi proxy được GC, aspect shared không nhất thiết cũng được GC.

### 9.2. Class-based proxy

Một số cơ chế tạo subclass/code-generated proxy. Association giữa interceptor, proxy instance và target body có thể khác delegating interface proxy. Đặc biệt self-invocation, `final` methods, `private` methods và receiver semantics phải được kiểm tra theo engine cụ thể.

Không viết định luật “mọi class proxy đều có một aspect instance trên mỗi object”. Thông tin đó thuộc mô hình tạo instance và cách engine lắp interceptor.

### 9.3. Weaving ở source/bytecode/load time

Một weaver có thể chèn logic advice vào target method hoặc call site. Khi đó target class có thể mang hook dù không có object proxy độc lập. Aspect instance có thể được tạo và quản lý ở một registry khác, có thể dùng chung hoặc theo scope.

Vì vậy **vòng đời của target class đã được weave** và **vòng đời của aspect instance** không bắt buộc liên kết qua quan hệ proxy → handler → target.

### 9.4. Load-time instrumentation và classloader lifecycle

Một class được transformer biến đổi lúc load không có nghĩa transformer instance sống cùng mọi target instance. Transformer có thể chỉ thực hiện một bước biến đổi và các target được tạo nhiều lần về sau. Ngoài ra, registry aspect/method metadata giữ reference tới classloader cũ có thể ảnh hưởng unload plugin.

## 10. Thời điểm bắt đầu và kết thúc association

Thay vì đoán, hãy đưa việc quản lý scope thành bốn câu hỏi độc lập:

1. **Creation trigger:** tạo aspect state khi đăng ký aspect, tạo target, tạo proxy, lần đầu pointcut khớp, hay mỗi invocation?
2. **Association key:** cùng state được dùng cho cái gì — process/module, target identity, receiver identity, thread, control flow, invocation ID?
3. **Lifetime boundary:** khi nào association không còn có nghĩa — hết request, đóng target, unload module, task completed/cancelled, application shutdown?
4. **Cleanup owner:** ai thực hiện remove/unregister/close và xử lý lỗi cleanup?

### 10.1. Eager và lazy creation

**Eager:** tạo state ngay khi target/proxy/registry được dựng. Dễ nhận thấy số object và có thể phát hiện lỗi sớm, nhưng tạo state cho những target không bao giờ có join point được chọn.

**Lazy:** tạo khi lần đầu một occurrence thỏa điều kiện. Tiết kiệm khởi tạo nhưng cần xử lý race ở first-use, đặc biệt khi nhiều thread cùng gọi target lần đầu. Hai thread có thể đều thử tạo state; engine hoặc registry phải xác định semantics atomic/publish.

### 10.2. Cleanup không chỉ là xóa một map entry

Nếu aspect per-target đăng ký listener hoặc mở resource, khi association kết thúc cần tháo listener, cancel task, đóng resource hoặc flush trạng thái phù hợp. Không được chỉ xóa mapping mà bỏ quên những external registrations vẫn giữ reference tới aspect và target.

### 10.3. Target shutdown không luôn gọi aspect shutdown

Một target có thể bị thu hồi bởi GC mà không có callback user-level xác định. Không dựa vào `finalize` làm lifecycle hook đáng tin; Java finalization đã bị deprecated và không bảo đảm chạy đúng thời điểm. Với tài nguyên cần cleanup, hãy đặt **close/dispose** rõ ràng hoặc dùng owner cấp cao hơn.

### 10.4. Aspect shared shutdown không thể phụ thuộc target cuối một cách mơ hồ

Nếu aspect shared phục vụ nhiều targets, nó không nên đóng metrics exporter khi target A kết thúc trong lúc B còn dùng. Cần xác định shutdown ở cấp module/application, reference counting nếu thực sự cần, hoặc một owner độc lập quản lý resource shared.

## 11. Một số chiến lược giữ per-target state

### 11.1. Trạng thái nằm trong wrapper

Một decorator/proxy object giữ state cho target mà nó bọc. Nếu chỉ một proxy cho mỗi target và object graph được quản lý, đây là cách đơn giản. Nhưng nếu tạo hai proxy riêng cho **cùng target**, bạn có thể có hai state độc lập dù cùng target. Khi cần state “per-target identity”, mapping ở wrapper có thể không đáp ứng đúng mong muốn.

### 11.2. Registry map theo target identity

Một map có thể tra state theo object target:

~~~text
TargetIdentity -> AspectState
~~~

Cần xem:
- Identity hay equality? Hai target khác nhau nhưng `equals()` bằng nhau có nên chia state?
- Keys mạnh hay yếu?
- Values có giữ lại target?
- Khi nào xóa entry?
- Registry có thread-safe và bounded không?
- Có nhiều classloader/module cùng đăng ký không?

Dùng `WeakHashMap` theo equality không tự tương đương identity-based weak association; còn value mạnh tham chiếu về key có thể làm key không được thu hồi. Nếu cần identity semantics, phải chọn cấu trúc phù hợp và test.

### 11.3. State được tạo khi target constructor chạy

Một số hệ thống có thể gắn state cùng lúc object được tạo hoặc lúc hook constructor được gọi. Nhưng không phải mọi proxy AOP chặn constructor; với JDK interface proxy, target constructor đã chạy trước khi proxy bọc target.

Do vậy không thể nói “per-target aspect được khởi tạo trong constructor target” như một quy tắc chung. Đây là quyết định engine/application.

### 11.4. Cần identity ổn định cho task lẫn target

Nếu target là đối tượng sống dài phục vụ nhiều tasks, một aspect per-target không đủ để phân biệt task A/B đang chạy đồng thời. Có thể cần kết hợp **per-target shared config** với **per-invocation context**:

~~~text
Target-associated aspect:
    immutable policy
    bounded metrics state

Each invocation:
    trace ID
    startedNanos
    error/outcome
~~~

Đây thường là lựa chọn tốt hơn việc đưa `currentRequest` hoặc `lastStart` vào field dùng chung của per-target aspect.

## 12. Async: target lifetime, invocation lifetime và task lifetime

Một method có thể trả `CompletionStage<Result>` ngay rồi tác vụ hoàn tất sau:

~~~text
T0 target method invoked
T1 around advice begins
T2 method returns stage          <-- invocation boundary ends
T3 worker processes task
T4 stage completes               <-- task boundary ends
T5 callback records final outcome
~~~

Mốc T0–T5 minh họa, không phải thứ tự bắt buộc: stage có thể hoàn tất trước T2 hoặc callback có thể chạy trên thread khác.

### 12.1. Aspect per-target vẫn có thể phục vụ nhiều tasks đồng thời

Một service singleton có thể trả nhiều futures. Aspect instance per-target cũng là **một** instance, nhưng mỗi task cần trace ID/timer/outcome riêng. Nếu dùng field `currentFuture` hoặc `startTime`, tasks sẽ ghi đè state của nhau.

### 12.2. Per-call state có thể cần sống sau method return

Nếu chỉ đo invocation latency, cleanup khi `proceed()` return stage có thể đúng. Nếu cần end-to-end latency, một snapshot tối thiểu (`startNanos`, `operationId`) phải được giữ tới completion.

Không capture toàn bộ join-point object, arguments, target hay request nếu callback chỉ cần một ID và timestamp. Nếu future không bao giờ complete, callback có thể giữ dữ liệu lâu; cần timeout/deadline, quota và monitoring.

### 12.3. Thread-local không tự kéo dài theo task

Một `ThreadLocal` của around advice trên caller thread nên được dọn/restore trong scope tương ứng. Worker thread không tự nhận giá trị đó. Gọi `ThreadLocal.remove()` ở completion callback trên worker **không dọn giá trị của caller thread**.

Với task context, dùng propagation được abstraction hỗ trợ hoặc snapshot/restore trên mỗi thread đúng vòng đời; không để request context tồn tại trong thread pool chỉ vì chờ future.

### 12.4. Cancellation khác object disposal

Một future bị cancel có thể hoàn tất trạng thái cancelled nhưng underlying I/O hoặc task đã gửi đi chưa chắc dừng. Việc bỏ callback, đóng resource và release aspect state phải căn theo **hợp đồng cancellation và ownership thực tế**, không chỉ trạng thái một handle.

## 13. Error path và trạng thái của aspect

### 13.1. Exception không tự hủy aspect shared

Nếu một invocation trên target A ném `IllegalStateException`, shared aspect vẫn có thể dùng tiếp cho target B. Advice có thể ghi failure rồi rethrow; điều này không có nghĩa aspect instance đã kết thúc vòng đời.

Trong ví dụ Java 17, sau `proxyA.run("FAIL")`, `shared.seen=3`; B vẫn là state riêng của một target khác. Mục đích của `catch` trong aspect là quan sát/làm chính sách, không nhất thiết là disposal.

### 13.2. Lỗi có thể để lại state sai nếu không cleanup

Nếu aspect ghi `ThreadLocal`, mở span hoặc lock trước `proceed()`, target ném lỗi rồi code chỉ cleanup ở nhánh return thì resource/context có thể rò. Dùng `finally` hoặc scope abstraction phù hợp để dọn trên cả return và throw.

### 13.3. Lỗi của chính advice có thể che lỗi target

Nếu target ném lỗi và logger/cleanup trong advice cũng ném lỗi, caller có thể thấy lỗi instrumentation thay vì lỗi gốc. Chính sách best-effort observability thường ưu tiên giữ exception target; audit bắt buộc có thể đòi hợp đồng khác. Dù chọn chính sách nào, phải nói rõ ai chịu trách nhiệm và test error path.

### 13.4. Mutable state sau một failure

State của per-target aspect có thể sống qua hàng nghìn invocations, gồm cả failure. Nếu một lần gọi làm state rơi vào trạng thái “đang xử lý” mà không reset, các lần sau có thể bị ảnh hưởng.

Thiết kế phải phân biệt:
- **State lịch sử có chủ đích:** count, rolling metrics, bounded errors.
- **State tạm của invocation:** start time, currently active request.
- **State tài nguyên:** open/closed, reference count, listener registrations.

Không gom tất cả vào một mutable field có tuổi thọ dài chỉ vì “aspect quản lý nó”.

## 14. Những vấn đề memory retention và classloader

### 14.1. Shared aspect giữ target ngoài ý định

Một aspect lâu sống có field:

~~~java
Object lastTarget;
Object lastArguments;
Throwable lastError;
~~~

Đây là minh họa về nguy cơ, không phải chương trình độc lập. Dù chỉ một reference, nó có thể giữ cả object graph lớn. Nếu có `List<Object[]>` lưu mọi args, retention có thể tăng theo số invocation.

Nên snapshot dữ liệu tối thiểu như operation name, error type, bounded ID hoặc aggregate metric thay vì lưu target/request/Throwable khi không cần.

### 14.2. Per-target association dùng strong keys

~~~text
GlobalRegistry
   -> Map<Target,AspectState>
         -> Target
         -> State
~~~

Nếu không có chính sách remove, mỗi target mới có thể ở lại. Dù code về mặt khái niệm “per-target”, vòng đời thực có thể trở thành **per-application-retained-forever**.

### 14.3. Proxy và aspect có thể tạo reference cycle

Ví dụ proxy giữ handler, handler giữ target, target giữ proxy tham chiếu ngược. Một cycle trong GC tracing **không tự là leak** nếu toàn bộ cycle không còn reachable từ GC roots. Vấn đề là một registry hoặc thread sống dài vẫn nắm một node của cycle khiến cả graph còn reachable.

Không sửa vấn đề bằng cách cực đoan “không bao giờ có cycle”, mà bằng ownership/cleanup đúng.

### 14.4. Plugin unload

Một aspect registry static ở host giữ metadata `Class` hoặc proxy từ plugin classloader cũ có thể làm classloader cũ không được thu hồi. Nếu hệ thống cho phép unload/reload, cần lifecycle hook để remove registration/cache và kiểm tra retained paths.

### 14.5. Đừng đánh đồng `close` với GC

Một aspect/target được close theo hợp đồng có thể vẫn reachable và chưa GC. Điều cần test deterministic là **resource đã đóng**, listener đã unregister, registry entry đã remove và count pending tasks đã giảm. Đừng viết assertion bắt `System.gc()` phải dọn đúng trong một khoảng ngắn.

## 15. Chọn scope theo yêu cầu thay vì theo thói quen

| Nhu cầu | Scope nên cân nhắc | Vì sao | Điều phải kiểm tra |
| --- | --- | --- | --- |
| Cấu hình bất biến dùng chung mọi service. | Shared/module scope. | Ít duplication, rõ ownership. | Safe publication, module lifetime. |
| Đếm tổng số lần gọi của nhiều target. | Shared counter. | Định nghĩa metric tổng. | Concurrency, cardinality. |
| Đếm riêng mỗi target identity. | Per-target association hoặc key ổn định. | Tách metric theo object. | Identity vs equality, cleanup. |
| Đo duration của mỗi lời gọi. | Local per-invocation state. | Không trộn các invocations. | Error/finally và async boundary. |
| Trace theo logical request qua nhiều methods. | Control-flow/task context. | Tương quan nhiều join points. | Recursion, executor, context propagation. |
| Một resource sống suốt module. | Owner cấp module/shared. | Không đóng khi một target dừng. | Shutdown và reference ownership. |
| Resource riêng target. | Per-target owner với close rõ. | Đồng nhất resource với target. | Dispose khi target không còn dùng. |
| Dữ liệu dùng tới completion của future. | Task-scoped minimal snapshot. | Duration/outcome end-to-end. | Timeout, cancellation, pending retention. |
| Policy tạm dùng trên thread. | Scoped ThreadLocal nếu thực sự cần. | Context nội bộ thread. | Remove/restore và thread pool. |

Không nên tạo per-target aspect chỉ vì method thuộc một class, cũng không nên dùng singleton chỉ vì dễ cấu hình. Chọn dựa trên **đơn vị ý nghĩa của state** và **các ràng buộc thực thi**.

### 15.1. Những câu hỏi chọn nhanh

- State của advice có phụ thuộc **target identity** không?
- Hai target có cần nhìn cùng counter/cache không?
- Hai concurrent invocations của cùng target có cần state độc lập không?
- Có async task sống lâu hơn method call không?
- Có plugin/module unload hoặc short-lived targets không?
- Có những đường caller bypass proxy không?
- Cleanup có liên quan tài nguyên external hay chỉ là giá trị GC-managed?

Nếu câu trả lời là “state chỉ đo một lượt gọi”, ưu tiên state local. Nếu “mỗi target có một bộ dữ liệu riêng”, cân nhắc per-target nhưng vẫn cần cleanup. Nếu “cả ứng dụng cùng dùng một policy”, shared instance có thể đủ khi thread-safe.

## 16. Bộ kiểm thử vòng đời cần có

### 16.1. Positive tests về scope

1. Tạo target A và target B, cùng shared aspect; gọi A, B, A và assert shared counter tăng 3.
2. Tạo per-target state riêng; assert A đếm 2, B đếm 1.
3. Với per-call state, assert mỗi lượt có context mới và không mang dữ liệu lượt trước.
4. Gọi target trực tiếp không qua proxy; assert handler state không đổi trong mô hình JDK proxy.
5. Tạo hai proxy cho **cùng target** nếu có thể; xác nhận semantics per-proxy có khác per-target identity dự kiến hay không.

### 16.2. Error/cleanup tests

- Target throw: advice có ghi failure đúng và truyền exception phù hợp không?
- Cleanup trong `finally` có chạy cả success/failure?
- Advice logging tự lỗi có che lỗi target ngoài chủ đích không?
- Sau failure, shared/per-target state có tiếp tục hợp lệ cho lần gọi sau?
- Nếu nested/reentrant advice, context trước được restore đúng không?

### 16.3. Concurrency tests

- Nhiều threads gọi chung một shared aspect.
- Nhiều threads gọi **cùng** target có per-target aspect.
- Một target xử lý nhiều async tasks đồng thời.
- Lazy per-target state được tạo khi nhiều threads cùng gọi lần đầu.
- Registry không giữ entries tăng vô hạn và không race.

Dùng synchronization/latches để kiểm soát test, không dựa vào `Thread.sleep` như bằng chứng đủ về interleaving. Một test tuần tự pass không chứng minh `int++` an toàn concurrent.

### 16.4. Lifecycle/ownership tests

- Đóng một target không đóng resource shared cần dùng cho target khác.
- Registry xóa state khi target/module được dispose theo hợp đồng.
- Unregister listener/subscription trên complete/error/cancel/shutdown.
- Pending future có deadline/quota, không giữ toàn bộ request object graph.
- Classloader của plugin không bị registry host giữ sau unload.
- Không giả định có deterministic GC; kiểm tra owner/registration/counters và dùng profiler khi cần.

### 16.5. Advice execution không phải aspect construction count

Instrument hai bộ đếm:
- **Aspect instances created**.
- **Advice invocations executed**.

Với 1 shared instance và 100 calls, kết quả có thể là 1 instance, 100 invocations. Nếu muốn per-target, nên đo số association theo target và số lần advice trên mỗi association. Đếm log constructor thay cho log advice sẽ gây suy luận sai.

## 17. Quy trình chẩn đoán khi vòng đời sai mong đợi

### Tình huống A — “State của A bị lẫn sang B”

Kiểm tra có dùng shared aspect instance nhưng lại lưu `currentTarget`, `lastResult` hoặc `startedNanos` trong field không. Nếu thật sự cần per-target association, xác định key đúng. Nếu chỉ cần per-call state, chuyển field thành local.

### Tình huống B — “State của target tăng mãi và không giải phóng”

Kiểm tra registry static, strong-key map, listeners, callbacks, proxy references và pending tasks. Tìm retained path từ GC roots. Không chỉ nhìn số object aspect để kết luận GC lỗi.

### Tình huống C — “Aspect được tạo hai lần cho một target”

Có thể có hai proxy riêng cho cùng target, hai registries, hai classloaders, duplicated configuration hoặc một association rule không theo target identity. Cần vẽ object graph và đo identity, không giả định chỉ dựa tên class.

### Tình huống D — “Target bị đóng nhưng aspect vẫn còn”

Nếu aspect shared phục vụ B/C, nó **nên còn**. Nếu state per-target A vẫn được giữ do mapping/listener, đó có thể là retention cần sửa. Trước khi báo leak, xác định scope được thiết kế và nghĩa của “còn”.

### Tình huống E — “Thread khác đọc nhầm context”

Có thể đang dùng `ThreadLocal` với pool thread và không remove/restore, hoặc callback async không được context propagation. Per-target aspect không tự sửa context của từng task.

### Tình huống F — “Một target gọi trực tiếp nhưng metric không tăng”

Nếu metric nằm trong proxy handler mà code bypass proxy, target body chạy nhưng advice không. Đây là **interception path mismatch**, không phải nhất thiết aspect instance đã hết vòng đời. Kiểm tra wiring và self-invocation.

### Tình huống G — “Nhiều log lỗi cho một exception”

Nhiều advice nested có thể cùng catch/rethrow một error. Đây có thể là nhiều event quan sát cho một failure, không phải nhiều aspect objects mới được tạo. Thiết kế metric phân biệt failure theo boundary/attempt/logical operation.

## 18. Sai lầm thường gặp

**“Một aspect class luôn có đúng một object cho cả JVM.”** Không. Phụ thuộc mô hình instantiation và phạm vi classloader/module.

**“Aspect instance được tạo khi target constructor chạy.”** Không mặc định. Có thể eager, lazy, lúc tạo proxy hoặc do registry/weaver quản lý.

**“Một target luôn có một proxy.”** Không. Có thể không có, có nhiều wrappers hoặc chung một routing proxy tùy cấu trúc.

**“Per-target aspect là thread-safe.”** Không. Một target có thể bị nhiều threads gọi đồng thời.

**“Per-thread state đồng nghĩa per-request state.”** Không với thread pool và async tasks.

**“Có 1.000 advice calls nghĩa là có 1.000 aspect instances.”** Không. Một instance có thể phục vụ nhiều calls.

**“Nếu target bị GC thì aspect shared cũng bị GC.”** Không nếu aspect được owner cấp cao hơn giữ để phục vụ target khác.

**“Per-target association chắc chắn biến mất cùng target.”** Không nếu registry giữ mạnh cả hai.

**“Object cycle luôn là leak.”** Không nếu cycle không còn reachable từ GC roots; vấn đề là đường reference còn sống.

**“Dùng WeakHashMap bảo đảm không giữ target.”** Không nếu value còn strong reference ngược key hoặc nơi khác giữ key.

**“Method trả future nghĩa là invocation state đã bao cả task.”** Không; cần tách method return và completion.

**“Tạo per-call aspect mới là cách duy nhất để state không bị trộn.”** Không. Local variables hoặc scoped context thường là lựa chọn đơn giản hơn.

**“Aspect dùng chung giữ `lastRequest` là vô hại.”** Không nếu request lớn, có dữ liệu riêng tư hoặc concurrency.

**“`finalize` là sự kiện shutdown đáng tin.”** Không. Cleanup quan trọng cần cơ chế tường minh.

**“Dùng proxy có thể bảo đảm mọi call đều có advice.”** Không nếu caller giữ target gốc hoặc self-call không đi qua proxy.

## 19. Bài tập vận dụng có đáp án

### Bài 1 — Hai target, một aspect

Có A, B và một aspect shared có biến đếm. A được gọi 3 lần, B 2 lần, tất cả đi qua handler. Counter của shared có thể là bao nhiêu?

**Đáp án:** 5 nếu mỗi invocation khớp và advice đếm đúng một lần. Không cần 5 aspect instances.

### Bài 2 — Hai proxy bọc cùng target

Tạo proxy P1, P2 cùng bọc target T nhưng mỗi proxy được cấp một `AspectState` mới. Đây có chắc là “per-target identity” không?

**Đáp án:** Không. Hai proxy sở hữu hai state dù cùng target. Đây là association theo proxy/wrapper trong thiết kế đó. Muốn per-target identity cần mapping/ownership bảo đảm cùng T dùng cùng state.

### Bài 3 — Per-target nhưng concurrency

Một target T được 50 threads gọi, aspect per-target có field `int seen` và `seen++`. Có bảo đảm seen tăng đúng 50 không?

**Đáp án:** Không; `seen++` không atomic. Scope per-target không tự cung cấp thread safety.

### Bài 4 — Shared duration

Một shared aspect đặt `startTime` trong field rồi tính duration khi method return. Vì sao sai?

**Đáp án:** Hai concurrent invocations có thể ghi đè start time. Đặt timestamp trong local state của mỗi invocation hoặc scope tương ứng.

### Bài 5 — Target hết hạn nhưng map còn

Một global map chứa `target → aspectState`. Không xóa entry. Target có tự được GC vì request đã hết không?

**Đáp án:** Không thể giả định; strong-key map có thể giữ target reachable. Cần lifecycle/eviction phù hợp.

### Bài 6 — ThreadLocal trong pool

Một thread xử lý request A rồi request B; advice quên `remove()`. Rủi ro nào?

**Đáp án:** B có thể nhìn thấy context A, rò dữ liệu/metric và giữ object của A lâu hơn cần thiết. Với nested scopes phải restore previous value đúng cách.

### Bài 7 — Async completion

Method trả `CompletionStage` ngay, nhưng task hoàn tất sau 2 giây. State nào nên tồn tại tới completion?

**Đáp án:** Nếu đo end-to-end, giữ snapshot nhỏ như ID/timestamp/outcome context đến terminal event; không mặc định giữ toàn bộ args, target hoặc ThreadLocal của caller.

### Bài 8 — Một exception, ba log THROW

Tại sao ví dụ có `THROW call`, `THROW target-A` và `THROW shared` dù target chỉ ném một lỗi?

**Đáp án:** Lỗi thoát qua ba advice nested. Các tầng quan sát cùng Throwable; không phải ba failure độc lập.

### Bài 9 — Direct target call

Gọi target A trực tiếp sau khi tạo proxy A; vì sao `shared.seen` không tăng?

**Đáp án:** Đường gọi không qua JDK dynamic proxy handler, nên advice ở handler không nhận invocation.

### Bài 10 — Plugin unload

Một registry ở host giữ `Method` thuộc plugin classloader đã unload về mặt logic. Hậu quả có thể là gì?

**Đáp án:** Registry có thể giữ metadata/classloader cũ reachable, ảnh hưởng khả năng thu hồi bộ nhớ. Cần scope cache và cleanup khi plugin dừng.

## 20. Checklist thiết kế vòng đời aspect

1. **Định nghĩa:** Aspect là cấu hình/logic được dệt hay runtime object có state?
2. **Creation:** Instance được tạo lúc nào và trigger nào quyết định?
3. **Association:** State gắn với application, module, target, receiver, thread, control flow hay invocation?
4. **Identity:** Per-target xác định theo object identity hay equality?
5. **Ownership:** Ai giữ reference đến aspect, target, proxy và registries?
6. **Cleanup:** Ai thực hiện `close/remove/unregister` và ở mốc nào?
7. **GC:** Có strong references làm target sống ngoài nhu cầu không?
8. **Concurrency:** Aspect shared/per-target có nhận nhiều calls đồng thời không?
9. **Per-call data:** Time/trace/error nằm ở local context hay bị đưa vào shared fields?
10. **Reentrancy:** Có nested advice, recursion và restore context đúng không?
11. **Async:** Invocation return và task completion có khác nhau không?
12. **Thread:** Có dùng `ThreadLocal` với thread pool và executor không?
13. **Exceptions:** Advice failure/target failure có cleanup và bảo toàn contract?
14. **Proxy path:** Mọi caller cần advice có thật đi qua proxy không?
15. **Weaving:** Nếu không dùng proxy, class/join point có thực sự được weave?
16. **Observability:** Có tách instances count, associations count và advice executions count?
17. **Perf:** Số instances/cache entries và allocations có phù hợp tải thực?
18. **Lifecycle tests:** Có kiểm tra success, error, shutdown, unload, concurrent và async?
19. **Security:** Có vô tình giữ request/target/Throwable chứa dữ liệu nhạy cảm?
20. **Compatibility:** Scope và association có thay đổi khi thêm proxy, module, classloader hoặc engine version?

## Kết luận

**Vòng đời của aspect và vòng đời của đối tượng được can thiệp không mặc định trùng nhau.** Một aspect instance có thể dùng chung cho nhiều target; một target có thể được liên kết với state riêng; nhiều advice invocations có thể chạy trên cùng một instance; và per-invocation state có thể được quản lý bằng local variables mà không cần tạo instance mới.

Thiết kế đúng bắt đầu từ câu hỏi **state thuộc về đơn vị nào** — ứng dụng, target, receiver, logical flow, thread hay invocation — rồi xác định **creation trigger, association key, owner, cleanup và concurrency contract**. Với proxy, còn phải chứng minh invocation đi qua handler; với weaving, phải xác nhận engine thực sự cài hook trên join point phù hợp. Với async, phải tách kết thúc method call khỏi kết thúc tác vụ. Một mô hình lifecycle rõ giúp tránh state bị trộn, memory retention, rò context và các giả định sai về việc “aspect được tạo/hủy cùng target”.
