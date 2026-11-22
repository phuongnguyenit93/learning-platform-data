# Context theo request và ranh giới vòng đời task trong Java

> **Phạm vi:** Java SE 21 và concurrency của Java nói chung. “Request” nghĩa là một đơn vị xử lý logic (yêu cầu mạng, lệnh CLI, message, hoặc một lượt xử lý job). Các ví dụ không dựa vào Spring hay một framework cụ thể.

## 1. Request context là gì?

**Request context** là bộ thông tin đi cùng một đơn vị công việc logic: `requestId` (đối chiếu log/tracing), `actorId` (người khởi tạo), `tenantId`, locale, deadline, thông tin phân quyền đã được xác minh, v.v. Một request thường đi qua nhiều phương thức và có thể tách thành nhiều tác vụ đồng thời.

~~~text
Request R-42
  │
  ├── Task A: gọi dịch vụ dữ liệu ─── worker/thread 1
  │
  └── Task B: tính kết quả phụ ───── worker/thread 2
                  │
            gom kết quả A và B
                  │
          kết thúc request R-42
~~~

**Request không đồng nghĩa với thread; task cũng không đồng nghĩa với thread.** Thread là tài nguyên thực thi, task là đơn vị công việc được đưa vào lập lịch, còn request là quan hệ nghiệp vụ chứa một hoặc nhiều task. Một worker trong thread pool có thể chạy tuần tự task của nhiều request. Cùng một request có thể chạy trên nhiều thread.

Có hai câu hỏi độc lập nhưng liên quan:

- **Propagation:** dữ liệu ngữ cảnh đi từ bước nhận request sang task/callback nào và bằng cơ chế gì?
- **Lifetime/ownership:** ai sở hữu việc tạo, chờ, kết thúc, hủy và cleanup task; khi request hết hiệu lực, công việc con còn được phép làm gì?

Lỗi propagation có thể khiến task mất `requestId` hoặc nhìn nhầm `actorId` từ request trước. Lỗi lifetime có thể khiến task tiếp tục thao tác với tài nguyên đã đóng hoặc ghi dữ liệu sau khi request đã timeout.

## 2. Phân biệt các phạm vi vòng đời

| Phạm vi | Từ đâu đến đâu? | Ví dụ |
|---|---|---|
| **Request** | Tiếp nhận → thành công, lỗi, timeout hoặc hủy theo quy tắc ứng dụng | R-42 bắt đầu, sinh A/B, tổng hợp, trả kết quả |
| **Task** | Được tạo/gửi thực thi → hoàn tất, lỗi, hoặc thật sự kết thúc sau tín hiệu hủy | `Callable` truyền cho `ExecutorService.submit` |
| **Thread** | Thread được tạo → kết thúc | Worker cố định của `newSingleThreadExecutor` |
| **Context binding** | Gắn ngữ cảnh → tháo/khôi phục binding | `ThreadLocal.set/remove`; dynamic binding của `ScopedValue` |

Ví dụ tái sử dụng worker:

~~~text
Thời gian ─────────────────────────────────────────────────────────▶
Request R1:  [nhận ─ submit task T1 ───── xong]
Task T1:                     [chạy ─ kết thúc]
Worker W:    idle ───────────[  T1  ]── idle ────[  T2  ]── idle
Request R2:                                  [nhận ─ T2 ─ kết thúc]

Nếu T1 để ThreadLocal = R1 mà không remove:
Worker W:                    [R1]─────────────[T2 thấy R1: SAI]
~~~

Thread pool không mặc nhiên xóa ngữ cảnh cho mỗi task. Tương tự, `Future.get()` giúp caller đợi task nhưng không tự định nghĩa mọi quy tắc cleanup, timeout, side effect hay propagation.

## 3. Thiết kế request context có thể chia sẻ an toàn

Một cách tốt là dùng **snapshot bất biến**, chỉ mang những trường mà task thật sự cần:

~~~java
// Minh họa kiểu dữ liệu Java 21, không phải chương trình độc lập.
record RequestContext(
        String requestId,
        String actorId,
        String tenantId
) {}
~~~

`record` tạo các field final, nhưng **không làm deep copy**: nếu một thành phần là `Map`/`List` mutable, những thread giữ cùng tham chiếu vẫn có thể cập nhật nó. Với dữ liệu tập hợp cần bất biến, cân nhắc `Map.copyOf`/`List.copyOf` và kiểm tra phần tử bên trong.

Các nguyên tắc:

1. **Càng nhỏ càng tốt:** giữ định danh và dữ liệu cần thiết; không capture toàn bộ request object, stream đang mở, connection, session có vòng đời riêng, hoặc object graph lớn.
2. **Dữ liệu tin cậy:** actor/tenant dùng để phân quyền phải được xác minh ở biên tin cậy; header tùy ý từ caller không tự trở thành quyền.
3. **Không nhầm context với thread safety:** context immutable có thể chia sẻ; một object mutable đặt trong `ThreadLocal` vẫn có thể bị race nếu nhiều thread cùng tham chiếu.
4. **Có thời hạn rõ ràng:** snapshot tồn tại trong task lâu hơn request không có nghĩa vẫn được phép thực hiện side effect dựa trên quyền hoặc trạng thái đã hết hạn.
5. **Context không thay thế cancellation hay transaction:** có `requestId` không làm timeout lan truyền và không tự rollback bất cứ thao tác nào.

Đối với API do mình kiểm soát, phương án đơn giản và rõ ràng nhất là truyền context bằng tham số:

~~~java
// Minh họa: các phương thức được định nghĩa ở ứng dụng.
Result process(RequestContext ctx) {
    Data data = load(ctx);
    return transform(ctx, data);
}
~~~

Mỗi dependency hiện rõ trong chữ ký; task không phụ thuộc thread nào chạy nó.

## 4. `ThreadLocal` gắn giá trị vào thread, không gắn vào request

`ThreadLocal<T>` cho **mỗi thread** một ô giá trị riêng. Với khai báo:

~~~java
private static final ThreadLocal<RequestContext> CURRENT =
        new ThreadLocal<>();
~~~

Các thao tác cơ bản:

- `CURRENT.set(ctx)`: gán vào thread **đang gọi**.
- `CURRENT.get()`: đọc ở thread **đang gọi**; với `new ThreadLocal<>()`, chưa set thì thường nhận `null`.
- `CURRENT.remove()`: xóa giá trị của thread **đang gọi**, không xóa ở các worker khác.
- `ThreadLocal.withInitial(supplier)`: khởi tạo giá trị riêng cho thread khi cần; không tự gắn với vòng đời request.

Ba giới hạn quan trọng:

**Không tự truyền qua executor.** `executor.submit(task)` không chép ordinary `ThreadLocal` của caller sang worker; một task có thể nhận `null` dù caller đã `set`.

**Có thể rò rỉ qua reuse.** Worker sống lâu hơn một request. Nếu task A quên `remove`, task B chạy trên cùng worker có thể nhìn thấy context A. Đó vừa là lỗi dữ liệu vừa có thể thành lỗi cách ly thông tin.

**Cleanup phải đúng thread và đúng scope.** Gọi `remove()` ở caller sau `submit` không xóa binding trên worker. `finally` phải bao công việc của chính thread đã `set`. Với scope lồng, cần khôi phục giá trị bên ngoài.

## 5. Ví dụ chạy được: task sau đọc nhầm context của task trước

Tạo tệp **`RequestContextDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class RequestContextDemo {
    private record RequestContext(String requestId, String actor) {}

    private static final ThreadLocal<RequestContext> CURRENT =
            new ThreadLocal<>();

    private static String currentId() {
        RequestContext ctx = CURRENT.get();
        return ctx == null ? "none" : ctx.requestId();
    }

    // Chỉ dùng khi wrapper sở hữu binding ở boundary task ngoài cùng.
    private static <T> Callable<T> bound(
            RequestContext context, Callable<T> body) {
        return () -> {
            CURRENT.set(context);
            try {
                return body.call();
            } finally {
                CURRENT.remove();
            }
        };
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool =
                     Executors.newSingleThreadExecutor()) {

            // Cố tình SAI: set context nhưng quên remove.
            System.out.println("unsafe-1=" + pool.submit(() -> {
                CURRENT.set(new RequestContext("req-1", "alice"));
                return currentId();
            }).get());

            // Task mới, cùng worker nên thấy giá trị cũ.
            System.out.println("unsafe-2=" +
                    pool.submit(RequestContextDemo::currentId).get());

            // Xóa vết sót trên chính worker để tiếp tục demo.
            pool.submit(() -> {
                CURRENT.remove();
                return null;
            }).get();

            // ĐÚNG ở task boundary: bind rồi cleanup bằng finally.
            System.out.println("safe-3=" + pool.submit(
                    bound(new RequestContext("req-3", "bob"),
                            RequestContextDemo::currentId)).get());

            System.out.println("after-3=" +
                    pool.submit(RequestContextDemo::currentId).get());
        }
    }
}
~~~

Chạy trên **JDK 21**:

~~~bash
javac --release 21 RequestContextDemo.java
java RequestContextDemo
~~~

Output khi không có lỗi:

~~~text
unsafe-1=req-1
unsafe-2=req-1
safe-3=req-3
after-3=none
~~~

`newSingleThreadExecutor` đảm bảo một worker xử lý tuần tự task. Hai lệnh `get()` chờ từng task nên output luôn theo thứ tự đã nêu. Task đầu cố ý để sót `req-1`; task hai đọc lại được giá trị cũ dù không thuộc request đó. Sau khi xóa vết sót, task bọc bằng `bound` gán `req-3` và `remove` trong `finally`. Task kế tiếp thấy `none`.

**`bound` được thiết kế cho task ngoài cùng**, nơi nó có quyền sở hữu binding và cần đảm bảo worker sạch sau task. Nếu đặt wrapper này lồng vào đoạn mã cùng thread có một context hợp lệ ở scope ngoài, `remove` sẽ xóa luôn binding của scope đó. Vì vậy phải phân biệt cleanup boundary ngoài cùng với nested scope.

## 6. Xử lý nested scope đúng cách

Giả sử request đang có context X và một lời gọi con muốn tạm thời xử lý trong context Y trên **cùng thread**. Sau khi lời gọi con thoát, X phải được phục hồi:

~~~java
// Minh họa trong lớp có CURRENT; không phải chương trình độc lập.
RequestContext previous = CURRENT.get();
CURRENT.set(innerContext);
try {
    executeInnerWork();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
~~~

Đây là chính sách **save/restore** cho scope lồng. Nó không thay thế việc làm sạch worker ở boundary ngoài cùng: nếu thread trước đó đã mang dữ liệu rò rỉ, save/restore chỉ đưa dữ liệu rò rỉ trở lại. Tại task boundary, cần chủ động bảo đảm không có context của request khác còn bám sau khi task kết thúc.

`remove` rõ ý nghĩa hơn `set(null)` vì xóa binding thay vì chỉ gán giá trị null. Cũng cần xử lý exception: nếu `executeInnerWork()` ném lỗi, khối `finally` vẫn phục hồi trạng thái.

## 7. Chuyển context qua `ExecutorService` và `CompletableFuture`

**Truyền snapshot tường minh** là giải pháp ưu tiên khi API cho phép:

~~~java
// Mã minh họa: ctx đã được xác minh, executor và work được cung cấp.
RequestContext ctx = currentRequestSnapshot;
Future<Result> future = executor.submit(() -> work(ctx));
Result result = future.get();
~~~

Lambda capture cùng `ctx` bất biến; không đòi thread worker phải kế thừa ambient context. Nếu API cũ chỉ biết đọc `ThreadLocal`, hãy bọc **từng task** bằng wrapper ở mục 5 hoặc wrapper có save/restore phù hợp ownership.

Với `CompletableFuture`:

~~~java
// Minh họa: lookup và format nhận RequestContext rõ ràng.
CompletableFuture<String> pipeline =
        CompletableFuture.supplyAsync(
                () -> lookup(ctx), ioExecutor)
        .thenApply(value -> format(ctx, value));
~~~

Các trường hợp dễ nhầm:

- `supplyAsync(..., executor)` chạy supplier ở executor chỉ định, không tự copy ordinary `ThreadLocal` từ caller.
- `thenApply` không đảm bảo luôn chạy trên đúng worker hoặc thread caller; thread thực thi phụ thuộc trạng thái hoàn tất của stage.
- `thenApplyAsync` không có executor thường chạy trong `ForkJoinPool.commonPool()` theo hợp đồng Java 21, có ngoại lệ khi mức song song mặc định quá thấp.
- `thenCompose`, `whenComplete`, `exceptionally` và callback timeout có thể nằm ở các boundary khác. Callback nào cần context thì phải nhận nó rõ ràng hoặc được bind đúng phạm vi.
- `get()/join()` chỉ chờ hoặc lấy kết quả; chúng không tự đồng bộ tất cả child tasks và không tự dọn bất kỳ `ThreadLocal` nào ở thread thực thi.

Nếu context gắn với quyền truy cập, tránh giả định việc log đúng `requestId` nghĩa là toàn bộ authorization đã đúng; task cần nhận đúng principal/tenant đã xác minh theo chính sách ứng dụng.

## 8. `InheritableThreadLocal` không phải cơ chế propagation theo request

`InheritableThreadLocal` cho phép **child thread nhận giá trị khởi tạo từ parent tại lúc child thread được tạo** (có tùy chọn kiểm soát inheritance). Đây không phải một bản copy mới mỗi khi task được submit vào executor.

~~~text
Request A đặt context=A
  └─ Tạo worker W → W có thể kế thừa A
Request B đặt context=B
  └─ Submit task lên W đã tồn tại → W không tự cập nhật thành B
~~~

Nếu giá trị ban đầu là một object mutable, inheritance mặc định thường truyền cùng reference, không phải deep copy. Có thể override `childValue` để thay đổi giá trị child nhưng vẫn cần quản lý dữ liệu và ownership.

Bởi vậy không dùng `InheritableThreadLocal` như giải pháp mặc định cho request trong thread pools. Tính năng kế thừa cũng không thay thế quy tắc cleanup khi request kết thúc.

## 9. Virtual threads trên JDK 21 và task lifetime

Virtual threads (JEP 444) đã là tính năng ổn định ở Java 21. Chúng vẫn là `java.lang.Thread`; `ThreadLocal` được gắn với **virtual thread**, không gắn với carrier thread trong JVM.

~~~java
// Ví dụ minh họa trong lớp có process(ctx), cần import java.util.concurrent.
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> process(ctx));
    System.out.println(future.get());
}
~~~

`newVirtualThreadPerTaskExecutor()` tạo virtual thread mới cho mỗi task, nên khác fixed platform-thread pool ở việc không cố tái sử dụng một worker cho các task kế tiếp. Tuy nhiên:

- Ordinary `ThreadLocal` trên caller **không tự động** được truyền vào task mới.
- Virtual thread mới có thể nhận `InheritableThreadLocal` tùy cấu hình khi tạo thread; inheritance vẫn không đồng nghĩa với request lifetime.
- `ThreadLocal` chứa cache/object lớn theo từng virtual thread có thể tốn bộ nhớ đáng kể nếu số virtual thread rất lớn.
- Một task chạy trong virtual thread vẫn có thể sống quá request nếu không có quyết định join/hủy/ownership rõ ràng.
- Chia sẻ mutable object qua nhiều virtual thread vẫn cần thread-safety như thường.

**Thread-per-task** chỉ mô tả cách cấp thread; không tự biến các tác vụ rời rạc thành một cấu trúc cha–con có vòng đời kết thúc cùng request.

## 10. `ScopedValue` trong Java 21: context có phạm vi động (preview)

JDK 21 giới thiệu `ScopedValue` (JEP 446) ở trạng thái **preview**. Thay vì một biến mutable `set/get/remove`, ta bind giá trị cho một **dynamic scope** của lời gọi. Khi scope kết thúc, binding tự phục hồi, kể cả khi có exception. Nó phù hợp thông tin cần truyền một chiều, phần lớn chỉ đọc.

Tạo tệp **`ScopedContextDemo.java`** trên **JDK 21**:

~~~java
public class ScopedContextDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
            System.out.println("inside=" + REQUEST_ID.get());

            ScopedValue.where(REQUEST_ID, "req-inner").run(() -> {
                System.out.println("nested=" + REQUEST_ID.get());
            });

            System.out.println("restored=" + REQUEST_ID.get());
        });

        System.out.println("outside=" + REQUEST_ID.isBound());
    }
}
~~~

Chạy với preview của **đúng JDK 21**:

~~~bash
javac --enable-preview --release 21 ScopedContextDemo.java
java --enable-preview ScopedContextDemo
~~~

Output:

~~~text
inside=req-42
nested=req-inner
restored=req-42
outside=false
~~~

Giải thích:

- `ScopedValue.newInstance()` tạo key, ban đầu chưa bind.
- `ScopedValue.where(KEY, value).run(body)` bind giá trị trong đoạn thực thi body và các phương thức đồng bộ gọi bên trong có quyền truy cập key.
- Scope trong có thể rebind tạm; khi thoát, scope ngoài nhận lại `req-42`.
- Thoát outer scope, `isBound()` trả về false. Đọc `get()` khi chưa bind sẽ không trả một requestId hợp lệ.
- `ScopedValue` không tự lan qua **arbitrary executor tasks**. Khi dùng kết hợp `StructuredTaskScope`, binding được kế thừa vào child threads do task scope quản lý theo quy tắc của API.
- Giá trị được bind có thể là reference tới object mutable; chính `ScopedValue` không biến object này thành immutable.

**Lưu ý phiên bản:** cả `ScopedValue` và `StructuredTaskScope` đều còn preview ở JDK 21. API/cú pháp của các JDK mới hơn có thể khác; không biên dịch snippet JDK 21 bằng cách suy đoán từ JDK hiện tại mà thiếu kiểm tra.

## 11. Ranh giới task cha–con: Structured Concurrency (preview ở Java 21)

Một request thường fork hai tác vụ rồi cần cùng kết quả:

~~~text
Request (cha)
  ├─ tạo context bất biến
  ├─ mở task scope
  │   ├─ fork A → thành công hoặc lỗi
  │   ├─ fork B → thành công hoặc lỗi
  │   ├─ join / xử lý lỗi, hủy nếu cần
  │   └─ close, kết thúc tác vụ con
  └─ tổng hợp, kết thúc request
~~~

`StructuredTaskScope` (JEP 453) hướng tới việc ràng buộc vòng đời task con vào scope mà người gọi sở hữu. Trong Java 21, đây là preview API, có các chính sách như `ShutdownOnFailure` và `ShutdownOnSuccess`. Khi tạo task scope trong binding `ScopedValue` phù hợp, các task fork bằng scope đó có thể kế thừa bindings một cách có cấu trúc.

Điểm quan trọng:

1. **Fork không phải hoàn tất.** Caller cần join, đọc kết quả/lỗi và đóng scope.
2. **Hủy chỉ là yêu cầu.** `shutdown` có thể gửi interrupt đến subtasks chưa hoàn thành; mã không hợp tác với interrupt hoặc native I/O có thể tiếp tục. Khi `close`, scope chờ các child threads kết thúc theo hợp đồng API.
3. **Không tự rollback side effect.** Task đã ghi file, gửi message hoặc gọi một dịch vụ ngoài trước khi bị hủy thì cần giao thức bù trừ/idempotency riêng.
4. **Không phải mọi task đều là child request.** Một job được phép tồn tại sau request phải có owner, deadline, retry và cleanup độc lập; không giữ tham chiếu tới object request đã hết vòng đời.

Trong ứng dụng Java 21 không dùng preview, vẫn có thể áp dụng **các nguyên tắc cấu trúc** này qua `ExecutorService` và `Future`: duy trì danh sách future của các tác vụ, đợi đủ kết quả, xử lý lỗi, hủy phần còn lại và đóng executor/resource. Nhưng phải viết chính sách đó một cách tường minh.

## 12. Deadline, timeout và cancellation phải được xử lý riêng

Ví dụ request có deadline 300 ms; A chạy 100 ms, B đang gọi I/O 2 giây:

~~~text
T0  Request R-42 bắt đầu, deadline = T0 + 300 ms
T1  Fork task A và task B
T2  Task A hoàn tất; B vẫn đang đợi
T3  Request timeout; caller gửi tín hiệu cancel cho B
T4  B thực sự dừng và dọn tài nguyên? Phụ thuộc API/code
~~~

Không được đồng nhất ba sự kiện **caller hết chờ**, **cancel được yêu cầu** và **task thực sự đã kết thúc**. Ví dụ `Future.get(timeout, unit)` có thể ném `TimeoutException` nhưng không tự hủy future bên dưới. `Future.cancel(true)` yêu cầu interrupt nếu task đang chạy; không đảm bảo I/O/native call ngừng ngay hoặc side effect chưa xảy ra.

Một thiết kế tốt cần:

- Tính deadline từ entry, truyền deadline hoặc ngân sách còn lại qua API; đặt timeout cụ thể cho I/O để không đợi vô hạn.
- Hủy các task con không còn cần và bảo đảm code hợp tác với interruption khi phù hợp.
- Dùng `try/finally` hoặc `try-with-resources` để giải phóng resource và context binding.
- Chỉ công bố kết quả khi request còn hiệu lực; với side effect không thể hủy hoàn toàn, xác định idempotency hoặc cơ chế bù trừ.
- Nếu chuyển sang job nền, chỉ truyền snapshot tối thiểu và thiết lập lifecycle riêng; không giữ request stream hay transaction đã đóng.

**Context propagation không đồng nghĩa với cancellation propagation**: mang theo `requestId` không khiến task tự hiểu deadline.

## 13. Bảng lựa chọn công cụ

| Cách làm | Phù hợp khi | Hạn chế chính |
|---|---|---|
| **Truyền `RequestContext` như tham số** | API do mình kiểm soát, task/callback qua nhiều thread | Cần chuyển tiếp qua một số tầng phương thức |
| **`ThreadLocal` + bind/cleanup** | API legacy yêu cầu context ambient trên thread hiện tại | Dễ bỏ sót cleanup và rò rỉ khi worker tái sử dụng |
| **`InheritableThreadLocal`** | Thực sự cần truyền giá trị lúc tạo child thread | Không đi theo task submission; reference mutable có thể bị chia sẻ |
| **`ScopedValue` (21 preview)** | Context bất biến, đọc một chiều, scope rõ ràng | Preview; không tự qua arbitrary executor |
| **`StructuredTaskScope` (21 preview)** | Task A/B là child logic của một request, cần join/lỗi/cancel thống nhất | Preview; interrupt không tự dừng mọi tác vụ và không rollback side effect |
| **Virtual thread per task** | Nhiều tác vụ chờ I/O, muốn mô hình blocking đơn giản | Không tự quản lý request context hay quan hệ cha–con |

Phần lớn pipeline có thể bắt đầu bằng **immutable context + truyền tham số tường minh**. Chỉ dùng state ambient khi thư viện/API hoặc cấu trúc lời gọi có lý do cụ thể và ownership được xác định.

## 14. Kiểm thử và các lỗi thường gặp

### Kiểm thử ranh giới

1. **Worker reuse:** dùng `newSingleThreadExecutor`; lần lượt chạy R1 rồi R2, xác minh R2 không thấy context R1.
2. **Đổi thread:** submit từ caller vào worker; kiểm tra trường nào được capture, trường nào không tự propagate.
3. **Nested scope:** bind X, tạm bind Y, cố tình ném exception; sau đó bảo đảm X được phục hồi.
4. **Concurrent tasks:** hai task cùng đọc immutable context; thử thay một field bằng mutable collection để nhận diện shared-state race.
5. **Cancellation:** kiểm tra timeout khi task đang ngủ/chờ I/O; phân biệt thời điểm hủy được yêu cầu và thời điểm tài nguyên thực sự đóng.
6. **Request kết thúc trước:** đảm bảo child task không vô chủ, hoặc được chuyển thành job nền có owner mới.

### Những hiểu lầm cần loại bỏ

| Sai lầm | Cách hiểu đúng |
|---|---|
| “Một request luôn có một thread.” | Request có thể dùng nhiều task/thread; worker có thể xử lý nhiều request. |
| “`ThreadLocal.set` ở thread tiếp nhận sẽ có trên executor worker.” | Ordinary `ThreadLocal` không tự truyền qua `submit`. |
| “`remove()` ở thread cha dọn được context worker.” | Nó chỉ xóa giá trị của thread đang gọi. |
| “`InheritableThreadLocal` theo mỗi task.” | Nó liên quan đến lúc **tạo thread**, không phải mỗi lần submit. |
| “`finally { remove(); }` luôn đúng trong mọi scope.” | Với nested scope phải khôi phục binding ngoài; với task ngoài cùng cần cleanup đầy đủ. |
| “Record chứa Map thì tự thread-safe.” | Record không deep-copy mutable objects. |
| “`thenApply` luôn chạy trên thread cố định.” | Completion stage có thể do thread khác thực thi tùy trạng thái và cách hoàn tất. |
| “Virtual thread tự kế thừa toàn bộ request context.” | Thread-local, inheritance và lifetime vẫn có quy tắc riêng. |
| “ScopedValue tự sang mọi executor.” | Binding theo dynamic scope, child inheritance có cấu trúc qua `StructuredTaskScope`. |
| “`cancel(true)` đã dừng task.” | Đó là yêu cầu hủy/interrupt, phụ thuộc code và I/O thực thi. |
| “Trả response rồi thì mọi task con biến mất.” | Task có thể tiếp tục nếu chưa được join/cancel hoặc giao cho owner riêng. |

## 15. Ghi nhớ

**Context theo request là dữ liệu và quyền sử dụng gắn với vòng đời logic của request, chứ không phải thuộc tính của một OS thread.** Khi task chuyển qua `ExecutorService`, `CompletableFuture` hoặc virtual thread, cần truyền context có chủ đích; khi task kết thúc, cleanup phải đúng thread/scope. Với nhóm task con, cần xác định rõ ai join, xử lý lỗi, cancel và đóng tài nguyên.

Java 21 cung cấp `ThreadLocal` ổn định, virtual threads ổn định và các lựa chọn preview `ScopedValue`/`StructuredTaskScope`. Hãy bắt đầu bằng context bất biến, truyền tường minh, và giới hạn vòng đời task trước khi dùng cơ chế ambient.

## Tài liệu tham khảo

- [Java SE 21 — ThreadLocal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 21 — InheritableThreadLocal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html)
- [Java SE 21 — CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444)
- [JEP 446 — Scoped Values (Preview)](https://openjdk.org/jeps/446)
- [Java SE 21 — ScopedValue.Carrier API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [JEP 453 — Structured Concurrency (Preview)](https://openjdk.org/jeps/453)
- [Java SE 21 — Structured Concurrency](https://docs.oracle.com/en/java/javase/21/core/structured-concurrency.html)
