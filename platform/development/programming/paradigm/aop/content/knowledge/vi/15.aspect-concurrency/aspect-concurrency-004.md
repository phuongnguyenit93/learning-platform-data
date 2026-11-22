# Trạng thái theo luồng và giới hạn với nhóm luồng trong Aspect/AOP

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming — AOP**), một **aspect** thường cần dữ liệu để thực hiện advice: mã tương quan của lượt gọi, thời điểm bắt đầu đo thời lượng, thông tin truy vết, cờ chống tái nhập, hoặc trạng thái đã mở một scope. Khi nhiều lời gọi chạy đồng thời, câu hỏi then chốt là **trạng thái nào thuộc một lời gọi, trạng thái nào thuộc một luồng (thread), và trạng thái nào được chia sẻ?**

Một lựa chọn phổ biến để giữ thông tin gắn với thread trên JVM là **`ThreadLocal<T>`**. Mỗi thread truy cập cùng một đối tượng `ThreadLocal` sẽ có **giá trị riêng của thread đó**. Nhờ vậy, một advice có thể đọc dữ liệu mà một bước bên ngoài thiết lập trên **cùng thread** mà không cần thêm tham số vào mọi phương thức. Tuy nhiên, `ThreadLocal` **không phải request scope tự động**, không phải đối tượng per-invocation và không tự truyền context qua executor, future hay mọi kiểu công việc bất đồng bộ.

Vấn đề càng quan trọng khi dùng **nhóm luồng (thread pool)**: worker thường sống lâu và được **tái sử dụng cho nhiều tác vụ khác nhau**. Nếu advice hoặc một bộ chặn đặt dữ liệu vào `ThreadLocal` mà không dọn sau khi xử lý, tác vụ sau có thể đọc dữ liệu của tác vụ trước. Đây vừa là lỗi về tính đúng, vừa là nguy cơ giữ tham chiếu trong bộ nhớ và rò rỉ dữ liệu giữa những yêu cầu.

**Nguyên tắc xuyên suốt:** lựa chọn vòng đời trạng thái theo **đơn vị công việc cần bảo vệ**, không tự đồng nhất **thread**, **lượt gọi advice**, **dynamic control flow**, **logical request** hay **transaction**. Khi phải dùng `ThreadLocal`, cần xác định chủ sở hữu scope, hỗ trợ lời gọi lồng nhau, **khôi phục/xóa trong `finally`**, và quy định rõ ranh giới async/thread pool.

Bài trình bày **Aspect/AOP cơ bản và nâng cao nói chung**. Cơ chế instantiation và weaving của mỗi công nghệ có thể khác nhau. Ví dụ dùng Java 17 và JDK dynamic proxy để minh họa một cách cài AOP qua proxy; nó không đại diện cho mọi loại join point hoặc cho một bộ bytecode weaver cụ thể.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác biệt giữa **trạng thái dùng chung của aspect instance**, **trạng thái cục bộ của một lần advice** và **trạng thái theo thread**.
2. Hiểu `ThreadLocal` lưu dữ liệu theo **danh tính thread**, không theo yêu cầu HTTP hay tác vụ nghiệp vụ.
3. Phân biệt **per-thread**, **per-control-flow**, **per-target/per-this** và **per-invocation** khi mô hình AOP hỗ trợ các chính sách tương ứng.
4. Mô tả điều gì xảy ra khi các worker thread trong pool được tái sử dụng, đặc biệt khi `set()` thiếu `remove()`.
5. Thiết kế scope theo nguyên tắc **lưu giá trị trước → thiết lập giá trị mới → thực thi → khôi phục** trên cả đường return và throw.
6. Hiểu giới hạn của `InheritableThreadLocal`, executor, callback, `CompletableFuture`, parallel processing và các mô hình bất đồng bộ.
7. Xác định khi nào cần truyền một **context snapshot** hoặc mã tương quan bất biến qua ranh giới task thay vì chia sẻ toàn bộ object mutable.
8. Nhận diện race condition do field trên singleton aspect, rò bộ nhớ qua thread pool và nguy cơ bảo mật của dữ liệu còn sót.
9. Chạy ví dụ Java 17 có JDK proxy, nested scope, lỗi nghiệp vụ, worker tái sử dụng và explicit propagation.
10. Thiết kế kiểm thử cho trạng thái theo thread, scope lồng nhau, thời điểm dọn và độ phủ join point.

## 2. Tách ba loại trạng thái trước khi chọn công cụ

### 2.1. Biến cục bộ theo một lần gọi advice

Một around advice đo thời gian có thể khai báo biến cục bộ:

```text
around invocation:
    start = monotonicClock()
    try:
        return proceed()
    finally:
        record(monotonicClock() - start)
```

Đây là **giả mã**, không phải API Java hoàn chỉnh. Biến `start` gắn với **một lần advice chạy**; hai lời gọi đồng thời không dùng cùng một biến cục bộ của cùng stack frame.

Nếu chỉ cần thời gian của một lần gọi, **biến cục bộ** thường đơn giản hơn `ThreadLocal`: không phải quản lý gắn/dỡ ngữ cảnh trên worker và không vô ý truyền dữ liệu sang những lời gọi khác.

### 2.2. Field trên aspect instance

Nếu một aspect dùng chung có:

```java
final class UnsafeAspect {
    String currentRequestId;

    void before(String id) {
        currentRequestId = id;
    }
}
```

Đây là **lớp minh họa**, không có `main` hoặc API AOP tự động. Nếu một instance được dùng bởi hai thread, A đặt `currentRequestId="A"`, B đặt `"B"`, rồi A đọc field thì có thể thấy `"B"`. Đây là race condition và rủi ro lẫn ngữ cảnh.

Một aspect dùng chung vẫn phù hợp với **trạng thái thật sự dùng chung**, ví dụ một bộ đếm thread-safe có chính sách rõ ràng; không phù hợp để tự giữ một “request hiện tại” duy nhất cho tất cả thread.

### 2.3. Trạng thái theo thread

Với:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();
```

Thread A có thể `set("A")`, thread B có thể `set("B")`; mỗi thread đọc lại giá trị của mình. Trên **cùng thread**, nhiều phương thức hoặc advice được gọi liên tiếp có thể đọc chung context ấy.

**Giới hạn:** nếu thread A xử lý request A xong nhưng không `remove()`, rồi xử lý request C, C có thể đọc lại giá trị A. Việc không lẫn với **thread B** không có nghĩa không lẫn giữa **hai tác vụ tuần tự trên A**.

### 2.4. So sánh phạm vi

| Nơi lưu | Đơn vị gắn dữ liệu | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| Biến cục bộ của advice | Một lần advice invocation | Tách biệt tự nhiên, cleanup cùng call stack | Không tự chia sẻ qua nhiều join point |
| Tham số/context tường minh | Lượt gọi hoặc logical operation | Dễ nhìn ownership và truyền qua API | Phải chuyền dữ liệu qua các tầng cần dùng |
| Field singleton aspect | Một instance sống dài | Phù hợp trạng thái tổng hợp có đồng bộ | Nguy cơ race và giữ request ngoài ý muốn |
| `ThreadLocal` | Một thread | Thuận tiện cho call stack đồng bộ trên cùng thread | Thread pool tái sử dụng; async chuyển thread không tự thấy |
| Per-target/per-this aspect | Đối tượng tương ứng nếu mô hình hỗ trợ | State theo đối tượng | Không tương đương mỗi request |
| Per-control-flow aspect | Một dynamic flow được chọn nếu mô hình hỗ trợ | Có thể giữ state theo lần đi vào root | Không mặc định lan qua async/thread khác |
| Context theo task/request | Một đơn vị nghiệp vụ được định nghĩa | Phù hợp async khi có propagation | Phải thiết kế capture, restore, ownership, expiry |

**Không có lựa chọn tốt nhất cho mọi trạng thái.** Bắt đầu với biến cục bộ hoặc context tường minh; chỉ đưa trạng thái sang cơ chế sống dài hơn khi thật sự cần các điểm can thiệp khác nhau cùng truy cập.

## 3. Cơ chế `ThreadLocal` trong Java

Một `ThreadLocal<T>` đóng vai trò **khóa** để mỗi thread có một giá trị gắn riêng. Các thao tác cơ bản:

- `get()`: đọc giá trị liên kết với **thread hiện tại**. Với `new ThreadLocal<>()`, chưa gán thì thường nhận `null`.
- `set(value)`: thiết lập giá trị cho thread hiện tại.
- `remove()`: bỏ mapping của thread hiện tại; lần `get()` sau có thể dùng `initialValue()`/supplier nếu có.
- `ThreadLocal.withInitial(supplier)`: tạo giá trị ban đầu khi thread gọi `get()` mà chưa có giá trị, theo hợp đồng Java.

Không nên coi `get()` là tra cứu theo request ID. Nếu hai request đi qua cùng thread ở những thời điểm khác nhau, chúng có thể dùng **cùng entry của ThreadLocal** nếu code không thay/xóa đúng cách.

### 3.1. `withInitial` không biến giá trị thành per-request

Ví dụ:

```java
ThreadLocal<StringBuilder> scratch =
        ThreadLocal.withInitial(StringBuilder::new);
```

Mỗi thread có thể tạo một `StringBuilder` lần đầu, rồi **tái sử dụng cùng builder qua nhiều tác vụ** nếu không `remove()` hoặc reset. Nếu buffer chứa dữ liệu lớn của request trước, nội dung/bộ nhớ có thể tồn tại dài hơn mong muốn.

Đừng suy rằng supplier của `withInitial` chạy lại mỗi khi bắt đầu một logical request. Nó hoạt động theo trạng thái mapping của **thread**.

### 3.2. Weak key không tự bảo đảm value được giải phóng

Cách giữ entry nội bộ của JVM có thể sử dụng tham chiếu yếu tới key `ThreadLocal`, nhưng value trong entry vẫn có thể được giữ **mạnh** cho tới khi được dọn bởi hành vi của map/thread. Điều này khiến việc tạo vô hạn các `ThreadLocal` ngắn hạn trên worker lâu sống có nguy cơ giữ object ngoài ý muốn.

Không nên dựa vào việc key biến mất hoặc gọi `System.gc()` để thay `remove()`. Hành vi dọn phụ thuộc cài đặt và hoạt động tương lai của thread; **cleanup có chủ đích tại biên công việc** đáng tin hơn.

### 3.3. Không đồng nhất `set(null)` với `remove()`

`set(null)` có thể để lại một entry có value null; `remove()` xóa liên kết của thread. Với `withInitial`, kết quả `get()` sau hai thao tác này còn có thể khác nhau: sau `remove()`, supplier có thể chạy lại; sau `set(null)`, `get()` có thể trả null mà không gọi supplier.

Khi muốn dọn sạch context, dùng `remove()` theo hợp đồng. Khi cần phân biệt “không có mapping” và “giá trị null hợp lệ”, cần một biểu diễn trạng thái rõ hoặc một scope abstraction.

## 4. Vì sao nhóm luồng làm lỗi trở nên khó phát hiện?

Một nhóm luồng thường có số worker hữu hạn và tái sử dụng:

```text
Time 1: Worker-1 handles Request-A
            CONTEXT.set(A)
            returns without remove()

Time 2: Worker-1 handles Request-B
            CONTEXT.get()  -> A (stale!)

Time 3: Worker-2 handles Request-C
            CONTEXT.get()  -> null or own value
```

Request B có thể thấy dữ liệu A; Request C lại không có lỗi. Tùy task được scheduler giao cho thread nào, lỗi có thể **không ổn định**, xuất hiện ngẫu nhiên dưới tải.

Một worker thread có thể sống suốt vòng đời ứng dụng, vì vậy dữ liệu stale trong ThreadLocal có thể tiếp tục reachable tới khi được dọn hoặc worker kết thúc. Nếu value giữ request context, user data, credentials, payload, target hay resource, có thể gây **rò rỉ ngữ cảnh và giữ bộ nhớ**.

### 4.1. Cùng một pool, hai loại nguy cơ

**Nguy cơ tính đúng:** tác vụ sau đọc trạng thái cũ và áp sai correlation ID, identity hoặc thông tin kiểm tra quyền.

**Nguy cơ vòng đời:** thread còn sống giữ object mà request trước đã hoàn tất, làm nó không được GC thu gom đúng nhu cầu; nó có thể tiếp tục giữ một đồ thị dữ liệu lớn.

Cùng một lỗi thiếu teardown có thể tạo cả hai. Một heap không tăng mãi không có nghĩa không nguy hiểm: chỉ một identity sai được tái sử dụng cũng có thể gây lỗi bảo mật.

### 4.2. Không sửa bằng cách “luôn dùng nhiều thread hơn”

Tăng kích thước pool không dọn context. Nó chỉ làm lỗi phân bố khác và có thể tăng số entry được giữ. Đổi executor, restart thường xuyên hoặc dùng `System.gc()` cũng không thay thế hợp đồng scope.

Biện pháp gốc là **không giữ state request sau biên kết thúc công việc** và không coi worker là request.

## 5. Scope an toàn: lưu trước, thiết lập, khôi phục

Nếu nhiều advice hoặc phương thức trong **cùng call stack đồng bộ** cần context, hãy mô hình hóa một scope:

```text
previous = CONTEXT.get()
CONTEXT.set(current)
try:
    execute body
finally:
    if no previous:
        CONTEXT.remove()
    else:
        CONTEXT.set(previous)
```

Đây là giả mã. Nó có hai điểm mạnh:

1. Dọn state trên đường **return lẫn throw**.
2. Cho phép **nested scope** trả lại state của outer thay vì luôn xóa mọi thứ.

### 5.1. Vì sao `remove()` vô điều kiện không đủ cho nested scope?

Ví dụ:

```text
Outer starts: context = A
  Inner starts: context = B
  Inner finishes: remove()
Outer continues: context = missing (A lost)
```

Nếu inner **khôi phục A** sau khi kết thúc, outer vẫn có dữ liệu đúng. Cách dọn nên là **khôi phục trạng thái trước đó** theo ownership, không chỉ “xóa mọi context khi tôi xong”.

Nếu code chỉ cho phép một scope top-level và không bao giờ lồng, `remove()` trong `finally` thường đủ; nhưng đừng mở rộng giả định đó sang luồng điều khiển phức tạp.

### 5.2. Scope theo token và `AutoCloseable`

Trong Java có thể tạo một class scope nhận context mới, ghi lại context trước đó, rồi triển khai `AutoCloseable.close()` để khôi phục. Sử dụng `try-with-resources` sẽ giúp đường thoát rõ ràng.

Tuy nhiên, **không được tự gọi `close()` từ thread khác** với thread đã mở nếu scope dùng `ThreadLocal`: như vậy nó sẽ tác động vào ThreadLocal của **thread đang đóng**, không phải thread đã thiết lập trước đó. Một thiết kế mạnh có thể kiểm tra owner thread và thứ tự LIFO khi cho phép nested scope.

### 5.3. Nếu khởi tạo scope thất bại?

Nếu việc kiểm tra quyền, cấp context hoặc bắt đầu tài nguyên ném lỗi **trước khi scope hoạt động**, cần biết có phần nào đã được cấp và cần rollback không. Không `pop()` một stack nếu `push()` chưa thành công; không `remove()` context của parent vì một scope con không mở xong.

Không dùng một `finally` mơ hồ không biết chính xác ownership để dọn những tài nguyên do thành phần khác tạo.

## 6. Per-thread khác per-control-flow và per-invocation

Một số mô hình AOP có chính sách tạo instance **theo dynamic control flow**, ví dụ các thuật ngữ `cflow`/`percflow` trong những ngôn ngữ AOP hỗ trợ chúng. Đây **không phải** từ khóa của Java hay API chung cho mọi cơ chế.

Cần phân biệt:

- **`cflow(P)`** có thể dùng để *lọc join point* nằm trong call flow của điểm P.
- **`percflow(P)`** trong mô hình hỗ trợ có thể định nghĩa **một aspect instance cho mỗi activation** của flow P.
- **`ThreadLocal`** chỉ cung cấp **dữ liệu riêng cho thread đang chạy**; nó không tự tạo per-flow instance khi P được vào hoặc tự xóa khi P thoát.
- **Per-invocation** có thể dùng biến cục bộ trong advice; không cần ThreadLocal nếu chỉ một lần advice dùng state.

Một thread có thể thực hiện nhiều flow **tuần tự**, hoặc có flow **lồng nhau**. Vì vậy `ThreadLocal<Aspect>` đặt một giá trị duy nhất và không hỗ trợ restore có thể làm hỏng per-flow semantics khi inner kết thúc.

### 6.1. Call stack không tự đi qua biên async

```text
Thread-A: request.handle()
             |
             +--> executor.submit(task)
             |
             +--> return

Thread-B:                 task.run()
```

Task chạy trên B có **một call stack khác**. Không có quy tắc chung rằng `cflow` đồng bộ của A tự kéo dài qua B, và một ThreadLocal trong A cũng không tự có mặt trong B.

Nếu một công nghệ AOP hỗ trợ context propagation hoặc asynchronous-aware flow, cần kiểm tra ngữ nghĩa thực tế. Không dùng một ví dụ ThreadLocal để suy rộng thành hành vi của mọi bộ weaving.

### 6.2. Mục tiêu là logical request hay thread?

Một logical request có thể bao gồm nhiều task; cùng một thread có thể chạy nhiều logical request. Nếu trạng thái phải thuộc request thay vì thread, có thể nên dùng **context object tường minh** hoặc một cơ chế truyền context được thiết kế cho async, với biên dọn xác định.

ThreadLocal chỉ là **một phương tiện lưu dữ liệu trên đoạn đồng bộ trong thread**, không phải câu trả lời tự động cho lifecycle xuyên task.

## 7. `InheritableThreadLocal` và giới hạn với thread pool

Java có `InheritableThreadLocal<T>` cho phép một thread mới tạo kế thừa giá trị từ parent tại thời điểm tạo thread, theo hợp đồng tương ứng. Điều này **không đồng nghĩa** tự truyền context sang mọi task được submit cho thread pool.

Vì sao?

1. Worker trong pool có thể đã được tạo **trước khi** request có context.
2. Một worker có thể được tạo trong bối cảnh request A rồi được tái sử dụng cho B; giá trị inherited khi tạo thread không tự đổi theo từng `submit`.
3. Nếu giá trị kế thừa là một object mutable, các thread có thể chia sẻ tham chiếu tới cùng object theo mặc định hoặc theo quy tắc `childValue` của triển khai.
4. Dữ liệu nhạy cảm từ parent có thể vô tình tồn tại trên thread con lâu hơn dự kiến.

Vì thế `InheritableThreadLocal` không phải giải pháp chung cho truyền request context vào executor. Với nhóm luồng sống lâu, cần **gói công việc với context capture/restore tại thời điểm submit/run**, hoặc truyền dữ liệu rõ qua tham số.

### 7.1. Capture context khi nào?

Có ít nhất hai thời điểm:

- **Submit time:** caller tạo task khi đang giữ correlation ID; có thể snapshot ID ở thời điểm này.
- **Execution time:** worker nhận task về sau, có thể đã chạy công việc khác; đọc ThreadLocal của worker không nói gì về caller đã submit.

Một propagation wrapper đúng thường capture **metadata cần thiết từ caller tại submit**, sau đó mở scope **trong worker khi task chạy** và khôi phục state cũ khi task kết thúc.

Nếu một task được submit sau khi request scope đã đóng, việc capture lúc đó có thể ra dữ liệu khác; không nên âm thầm đoán request “gần nhất”.

### 7.2. Tránh capture toàn bộ đối tượng request

Không phải mọi thứ trong context đều nên truyền:

- Truyền **correlation ID bất biến** có thể đủ cho tracing.
- Truyền đối tượng identity/authorization phải dựa trên hợp đồng tin cậy và thời hạn hiệu lực.
- Truyền connection, lock, mutable transaction hoặc request-scoped resource sang task chạy muộn có thể làm nó bị dùng sau khi đóng.
- Truyền `ThreadLocal` value là cùng một mutable object sang nhiều worker có thể tạo race condition; việc value nằm trong ThreadLocal ở mỗi worker **không tự sao chép sâu object**.

Thiết kế propagation phải nói rõ **trường dữ liệu nào được copy**, quyền sở hữu ra sao và khi nào bị xóa.

## 8. Mô hình AOP qua proxy: trạng thái được đặt ở đâu?

Một JDK dynamic proxy có thể chặn lời gọi phương thức **qua giao diện của proxy**. Giả sử handler tạo scope:

```text
caller -> proxy handler
           |
           +--> open ThreadLocal scope
           +--> invoke target
           +--> close scope in finally
           |
        result / error
```

Các phương thức chạy đồng bộ trên cùng thread bên trong target có thể đọc ThreadLocal. Tuy nhiên:

- Caller giữ **đối tượng gốc** và gọi trực tiếp có thể bypass proxy và scope.
- **Self-invocation** `this.otherMethod()` trong target có thể không quay lại proxy; nếu scope được mở ở entry bên ngoài thì method bên trong vẫn có thể đọc context, nhưng **advice riêng của method bên trong** có thể không được kích hoạt.
- JDK proxy không tự chặn field access, constructor, private method hoặc mọi loại join point.
- Handler phải phân biệt những phương thức thuộc pointcut và tránh áp dụng scope nhầm cho `Object` methods hoặc overload khác.
- Nếu một interceptor ngoài short-circuit trước khi handler/guard cần thiết chạy, scope có thể không được mở.
- Nếu around advice gọi tiếp nhiều lần để retry, phải xác định scope mở **mỗi attempt** hay cho cả logical request.

### 8.1. Thứ tự context và retry

```text
ContextScope(Retry(Target))
```

Có thể mở một context cho logical request và giữ nó qua nhiều attempts.

```text
Retry(ContextScope(Target))
```

Có thể mở context mới cho mỗi attempt nếu phần đuôi của chain được chạy lại. Mỗi phương án có ý nghĩa khác về tracing span, timing, identity snapshot và cleanup.

Không mặc định thứ tự trong một bộ AOP; phải kiểm tra precedence của cơ chế sử dụng và **lời gọi thực tế tới `proceed`**.

### 8.2. Cleanup có được bảo đảm khi target throw?

Nếu handler dùng:

```text
scope = open()
try:
    return invokeTarget()
finally:
    scope.close()
```

thì scope đóng trên đường return/throw thông thường. Nhưng nếu `open()` đã cấp một phần tài nguyên rồi lỗi trước `try`, phải có chiến lược cleanup cho cấp phát từng phần. Nếu `close()` tự ném lỗi, nó có thể **che lỗi nghiệp vụ gốc**; hợp đồng phải quy định cách xử lý.

## 9. Ví dụ Java 17 chạy độc lập: proxy, scope lồng nhau, thread pool và propagation

Chương trình sau minh họa bốn tình huống bằng **JDK thuần**:

1. Proxy mở scope theo ID của một lần gọi, rồi khôi phục context trước đó kể cả khi target ném ngoại lệ.
2. Nested scope `outer` bao một lời gọi proxy `inner`: khi lời gọi trong kết thúc, trạng thái của outer được khôi phục.
3. Một `newSingleThreadExecutor()` chạy hai task tuần tự trên **cùng worker**: task đầu cố ý để lại `ThreadLocal`, task sau nhìn thấy giá trị stale.
4. Caller giữ context `parent` và submit task: worker **không tự nhận** context ấy; một wrapper tường minh đưa correlation ID sang worker rồi dọn khi task hoàn tất.

Ví dụ chỉ minh họa dữ liệu tương quan là chuỗi, không truyền identity bảo mật hoặc transaction. Nó không phải một hệ AOP tự động biến đổi bytecode.

Lưu toàn bộ thành `ThreadStateAopDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadStateAopDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    static String current() {
        String id = CONTEXT.get();
        return id == null ? "none" : id;
    }

    static final class Scope implements AutoCloseable {
        private final String previous;
        private final Thread owner;
        private boolean closed;

        Scope(String id) {
            previous = CONTEXT.get();
            owner = Thread.currentThread();
            CONTEXT.set(id);
        }

        @Override
        public void close() {
            if (Thread.currentThread() != owner) {
                throw new IllegalStateException("wrong owner thread");
            }
            if (closed) {
                return;
            }
            closed = true;
            if (previous == null) {
                CONTEXT.remove();
            } else {
                CONTEXT.set(previous);
            }
        }
    }

    interface WorkPort {
        String handle(String id);
    }

    static final class WorkService implements WorkPort {
        @Override
        public String handle(String id) {
            System.out.println("TARGET " + id + " context=" + current());
            if ("bad".equals(id)) {
                throw new IllegalArgumentException("bad input");
            }
            return "OK:" + id;
        }
    }

    static Object callTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException wrapped) {
            throw wrapped.getCause();
        }
    }

    static WorkPort wrap(WorkPort target) {
        return (WorkPort) Proxy.newProxyInstance(
                WorkPort.class.getClassLoader(),
                new Class<?>[] { WorkPort.class },
                (proxy, method, args) -> {
                    if (!method.getName().equals("handle")
                            || method.getParameterCount() != 1
                            || method.getParameterTypes()[0] != String.class) {
                        return callTarget(method, target, args);
                    }

                    String id = (String) args[0];
                    try (Scope scope = new Scope(id)) {
                        System.out.println("ENTER " + id
                                + " context=" + current());
                        try {
                            Object result = callTarget(method, target, args);
                            System.out.println("RETURN " + id
                                    + " context=" + current());
                            return result;
                        } catch (Throwable error) {
                            System.out.println("THROW " + id + " "
                                    + error.getClass().getSimpleName());
                            throw error;
                        }
                    }
                });
    }

    public static void main(String[] args) throws Exception {
        WorkPort proxy = wrap(new WorkService());

        try (Scope outer = new Scope("outer")) {
            System.out.println("OUTER before " + current());
            System.out.println("OUTER result " + proxy.handle("inner"));
            System.out.println("OUTER after " + current());
        }
        System.out.println("MAIN after outer=" + current());

        try {
            proxy.handle("bad");
        } catch (IllegalArgumentException error) {
            System.out.println("CALLER " + error.getMessage());
        }
        System.out.println("MAIN after error=" + current());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> {
                CONTEXT.set("stale");
                System.out.println("UNSAFE set " + current());
                // Cố ý không remove() để tái hiện lỗi.
            }).get();

            pool.submit(() -> {
                System.out.println("REUSED saw " + current());
                CONTEXT.remove();
            }).get();

            try (Scope parent = new Scope("parent")) {
                System.out.println("PARENT " + current());

                pool.submit(() ->
                        System.out.println("ASYNC default " + current())
                ).get();

                String captured = current();
                pool.submit(() -> {
                    try (Scope transfer = new Scope(captured)) {
                        System.out.println("ASYNC explicit " + current());
                    }
                    System.out.println("ASYNC cleaned " + current());
                }).get();

                System.out.println("PARENT after tasks " + current());
            }
        } finally {
            pool.shutdown();
        }

        System.out.println("MAIN final " + current());
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ThreadStateAopDemo.java
java ThreadStateAopDemo
```

**Stdout dự kiến chính xác** khi chạy chương trình này:

```text
OUTER before outer
ENTER inner context=inner
TARGET inner context=inner
RETURN inner context=inner
OUTER result OK:inner
OUTER after outer
MAIN after outer=none
ENTER bad context=bad
TARGET bad context=bad
THROW bad IllegalArgumentException
CALLER bad input
MAIN after error=none
UNSAFE set stale
REUSED saw stale
PARENT parent
ASYNC default none
ASYNC explicit parent
ASYNC cleaned none
PARENT after tasks parent
MAIN final none
```

### 9.1. Vì sao `OUTER after outer` đúng?

`main` mở `Scope("outer")`, sau đó gọi `proxy.handle("inner")`. Proxy đọc `previous="outer"`, thiết lập `"inner"`, gọi target rồi đóng scope. `Scope.close()` **khôi phục `"outer"`**, không xóa toàn bộ state của main thread.

Nếu handler chỉ gọi `CONTEXT.remove()` khi `inner` kết thúc, dòng `OUTER after` sẽ sai: scope cha vẫn đang chạy nhưng dữ liệu đã bị mất.

### 9.2. Vì sao lỗi `bad` không để lại context?

`WorkService.handle("bad")` ném `IllegalArgumentException`. `callTarget` bóc `InvocationTargetException` để giữ nguyên lỗi gốc; handler ghi `THROW` rồi truyền lỗi. Dù lỗi xảy ra, `try-with-resources` vẫn gọi `Scope.close()` cho scope đã mở.

Vì trước `bad` main thread không có context, close gọi `remove()`, do đó `MAIN after error=none`.

### 9.3. Vì sao `REUSED saw stale` xuất hiện?

`Executors.newSingleThreadExecutor()` tuần tự thực hiện các task trên một worker (trừ trường hợp cần thay worker do lỗi). Trong ví dụ các task hoàn thành bình thường, và `Future.get()` giúp main đợi task trước xong mới gửi/kiểm tra tiếp.

Task thứ nhất đặt `"stale"` và cố ý **không dọn**. Task tiếp theo chạy trên worker đó và thấy giá trị cũ. Nó gọi `remove()` để những task sau bắt đầu sạch.

Phần “UNSAFE” là đoạn **cố tình sai để học**, không phải mẫu code nên dùng trong hệ thật.

### 9.4. Vì sao `ASYNC default none`?

Main thread đang giữ `"parent"` nhưng worker thread không tự thừa hưởng `ThreadLocal` thông thường. Task async đọc ThreadLocal của **chính worker**. Worker đã được dọn từ task trước, nên nó thấy `none`.

### 9.5. Vì sao explicit propagation không làm lẫn context?

Main thread capture **chuỗi correlation ID** `"parent"`, submit một task sử dụng `new Scope(captured)` **trên worker**. Worker thấy `parent` trong scope; khi task kết thúc, scope khôi phục previous của worker (ở ví dụ là null), rồi `ASYNC cleaned none`.

Main thread vẫn ở scope parent, nên `PARENT after tasks parent`; sau khi parent close, `MAIN final none`.

**Điều quan trọng:** wrapper không chuyển trực tiếp toàn bộ ThreadLocalMap và không chia sẻ một object request mutable. Nó truyền **một giá trị đơn giản, được lựa chọn có chủ đích**.

### 9.6. Vì sao `Scope` giữ `owner`?

Một `Scope` dựa trên ThreadLocal chỉ được đóng ở thread đã mở. Nếu đóng trên thread khác, nó sẽ restore dữ liệu trong ThreadLocal của **thread đang gọi close**, không phải của owner. Kiểm tra `Thread.currentThread() != owner` giúp phát hiện việc dùng sai mô hình trong ví dụ.

Ví dụ vẫn không có stack token kiểm tra thứ tự LIFO giữa nhiều scope; cần sử dụng `try-with-resources` đúng cấu trúc. Một abstraction sản xuất có thể cần chống đóng sai thứ tự, khởi tạo/đóng lặp, hủy task và logging lỗi cleanup có hệ thống.

### 9.7. Giới hạn của chương trình

- JDK dynamic proxy chỉ chặn lời gọi đi qua **giao diện `WorkPort`**; không weave bytecode của `WorkService`.
- Handler lọc phương thức `handle(String)`; lời gọi trực tiếp vào target gốc sẽ không đi qua handler.
- `Scope` là mô hình thủ công, không có bộ AOP tự lựa chọn pointcut theo annotation, field access hay constructor.
- Ví dụ chạy tuần tự trong mỗi task; không minh họa một shared mutable context được truy cập đồng thời từ hai thread.
- Correlation ID là chuỗi mô phỏng; không phải giấy phép kiểm tra quyền hay chứng nhận identity.
- `ThreadLocal` dùng giá trị null để biểu thị “không có scope” trong bản học tập; nếu null có nghĩa nghiệp vụ hợp lệ, cần type/marker rõ hơn.
- `pool.shutdown()` sau các `get()` hoàn tất giúp kết thúc executor; ứng dụng thật có lifecycle executor riêng.
- Không được kết luận mọi `ThreadLocal` đều gây leak: leak xuất hiện khi **ownership/lifetime/teardown sai**, không phải chỉ vì API tồn tại.

## 10. Khi có nhiều executor, callback và parallel processing

Không phải mọi tác vụ chạy trên thread nhận request ban đầu:

- `ExecutorService.submit`: task có thể chạy trên worker khác, ngay cả khi code được gọi bên trong một method đang có context.
- `CompletableFuture.supplyAsync`: phần việc có thể được lên lịch trên executor riêng hoặc common pool, tùy overload.
- Callback không có ràng buộc về thread nhất định theo mọi API; không được giả định thread của producer luôn chạy consumer.
- `parallelStream` có thể phân chia công việc ra nhiều worker; ThreadLocal của thread gọi không phải state tường minh cho toàn bộ tập.
- Event loop/reactive-style processing có thể xen kẽ nhiều logical requests trên ít thread; lưu request vào ThreadLocal mà không ràng buộc callback dễ dẫn đến sai context.
- Timer, scheduler hoặc message listener có thể chạy trên thread quản lý riêng.

Bất cứ khi nào luồng điều khiển **có thể đổi thread**, phải xác định rõ cơ chế capture/restore; nếu không biết task đang chạy ở đâu, không dùng `ThreadLocal.get()` làm nguồn sự thật của logical request.

### 10.1. `CompletableFuture` và thời điểm kết thúc

Một method trả `CompletableFuture<Result>` có thể trả về **trước khi** công việc hoàn tất. Nếu around advice mở ThreadLocal ở method đó và đóng scope ngay sau return, worker hoàn thành future về sau không còn call stack đồng bộ của method.

Nếu advice muốn ghi metric **thời gian hoàn thành tác vụ**, phải theo dõi completion stage hoặc cơ chế tương ứng theo hợp đồng, không chỉ đo thời gian method trả future.

### 10.2. Có nên truyền ThreadLocal qua mọi task?

Không nhất thiết. Truyền quá nhiều context có thể:

- Giữ request/session/credential ngoài vòng đời;
- Đưa dữ liệu nhạy cảm tới worker không cần dùng;
- Kéo dài tài nguyên đã đóng;
- Gây race nếu giá trị là object mutable dùng chung;
- Làm hành vi khó tái hiện khi một task chạy rất muộn;
- Khó dọn đúng nếu worker bị hủy/cancel giữa chừng.

Chỉ capture **những trường cần thiết**, ưu tiên các giá trị bất biến, xác định thời hạn và người sở hữu. Khi cần đầy đủ transaction context hoặc authorization, dùng giao thức/hợp đồng rõ, không copy tùy tiện.

## 11. ThreadLocal và an toàn bộ nhớ

Một worker sống lâu có thể giữ `ThreadLocal` value qua nhiều lượt xử lý. Nếu value tham chiếu:

```text
Thread pool worker (long-lived)
     |
     v
ThreadLocal value
     |
     v
RequestContext
     |
     +--> Large payload
     +--> Session data
     +--> Target object
     +--> Resource handle
```

thì các object liên quan có thể còn reachable ngoài thời gian cần thiết. Đây có thể là **unintended retention**, dù heap không nhất thiết tăng mãi: một field giữ request gần nhất có thể chỉ giữ một đồ thị lớn, còn một map không giới hạn có thể giữ hàng nghìn đồ thị.

Để điều tra:

1. Tạo workload tuần tự nhiều task trên cùng pool.
2. Kiểm tra rằng sau mỗi task, **context cục bộ của task không còn tồn tại**.
3. Quan sát số lượng object còn sống và paths to GC roots bằng công cụ heap analysis khi cần.
4. Tìm ThreadLocalMap, callback, registry hoặc cache đang giữ value.
5. Sửa tại nơi **thiết lập scope** hoặc nơi capture object, không chỉ gọi `System.gc()`.

Một reference cycle không tự là memory leak trong tracing GC nếu không còn reachable từ root. Vấn đề là đường tham chiếu mạnh từ worker sống lâu tới dữ liệu đã hết vòng đời.

### 11.1. `ThreadLocal.remove()` có giải quyết mọi tài nguyên không?

Không. Nó bỏ liên kết giá trị trong ThreadLocal của thread hiện tại. Nếu value chứa một socket/file/transaction còn mở, chỉ remove mapping **không tự đóng tài nguyên**.

Hợp đồng phải nêu ai thực hiện `close()`, `rollback()`, `unlock()` hoặc hủy registration nếu cần. Thứ tự cleanup cũng quan trọng: tài nguyên phải được đóng đúng owner và không còn được task async dùng.

### 11.2. Scope kéo dài quá lâu

Nếu code mở một scope bao quanh toàn bộ vòng lặp worker:

```text
openScope(requestA)
while (workerAlive):
    processNextTask()
closeScope()
```

scope đã bị đặt sai ranh giới. Mỗi task B/C sẽ vẫn nhìn thấy dữ liệu A. Đối với dữ liệu per-task, cần scope riêng **cho mỗi lượt thực thi**, không phải scope theo vòng đời worker.

## 12. ThreadLocal không tự bảo đảm an toàn đồng thời

Dù từng thread có giá trị riêng, **giá trị đó có thể là cùng một object** nếu chương trình đưa cùng tham chiếu vào nhiều thread.

Ví dụ:

```text
SharedMutableContext shared = ...
Thread A: TL.set(shared)
Thread B: TL.set(shared)
```

Đây là giả mã. A và B đọc `TL.get()` trên thread của mình, nhưng cả hai đều nhận **cùng object `shared`**. Các phép ghi vào field mutable của object đó vẫn cần đồng bộ hoặc một thiết kế sở hữu duy nhất.

`ThreadLocal` bảo vệ **mapping theo thread**, không tự bảo vệ **nội dung mutable** được các thread chia sẻ bằng tham chiếu.

### 12.1. Aspect singleton và `ThreadLocal`

Một aspect instance dùng chung có thể giữ field:

```java
private final ThreadLocal<String> requestId =
        new ThreadLocal<>();
```

Các thread có entry riêng, nhưng cần làm rõ:

- Field `ThreadLocal` sống theo aspect instance và có thể rất lâu;
- Mỗi thread được set phải được restore/remove theo scope;
- Không được trao nhầm context của thread sang async worker;
- Nếu aspect tạo một `ThreadLocal` mới cho **mỗi invocation** và không cleanup, có thể tăng số key/value rác trên worker;
- Nếu nhiều aspect cần cùng context, nên có abstraction ownership chung, không để mỗi aspect tự remove state do aspect khác đặt.

Một lựa chọn kiến trúc là một **scope/interceptor ngoài cùng** sở hữu việc thiết lập/dọn context, những advice bên trong chỉ **đọc** thông qua API có hợp đồng rõ. Việc ghi hoặc thay đổi context nên giới hạn cho những thành phần được phép.

### 12.2. Dữ liệu bảo mật tuyệt đối không lấy từ ThreadLocal stale

Nếu `currentUser` hoặc `authorized` được để lại từ request trước, request sau có thể được xử lý dưới danh tính/quyền sai. Không nên coi một cờ trong ThreadLocal là quyết định bảo mật đáng tin nếu nó có thể được set bởi luồng không xác thực hoặc có đường bypass.

Với chính sách bắt buộc, xác thực/ủy quyền phải được bảo vệ tại ranh giới đáng tin cậy, dùng dữ liệu có nguồn gốc và thời hạn rõ, và thất bại an toàn khi context thiếu/không hợp lệ.

## 13. Context propagation và owner

Một wrapper propagation có thể thực hiện bốn bước:

```text
Caller at submit:
    captured = immutableSnapshot(allowedContextFields)

Worker at run:
    previous = context.current()
    context.install(captured)
    try:
        task.run()
    finally:
        context.restore(previous)
```

Đây là giả mã; không phải API chuẩn của AOP. Những câu hỏi phải có đáp án:

- **Capture khi nào?** lúc tạo task hay lúc submit?
- **Điều gì được copy?** correlation ID, tenant, identity hay object mutable?
- **Điều gì không được copy?** session lớn, stream, lock, open transaction?
- **Thời hạn là gì?** task chạy sau khi request đã kết thúc có còn hợp lệ không?
- **Ai dọn?** wrapper, scheduler hay task body?
- **Scope lồng nhau?** restore previous hay remove?
- **Nhiều task con?** chia sẻ parent metadata và độc lập state từng task ra sao?
- **Task bị cancel trước khi run?** có cần hủy callback/retention của snapshot không?
- **Task lỗi?** wrapper có cleanup trong `finally` không?
- **Worker đã có context của một task trước?** phải khôi phục context trước đó theo ownership.

### 13.1. Không chuyển một mutable request object nguyên vẹn

Nếu một `RequestContext` chứa danh tính, thông tin giao dịch, payload và connection rồi được capture trong `Runnable`, nó có thể ở lại trong queue cho tới khi task chạy hoặc bị hủy. Nếu queue trì hoãn, payload bị giữ lâu. Nếu task được phân nhánh, mutable data có thể bị dùng đồng thời.

Chỉ dùng context tối thiểu; đặt chính sách giới hạn queue/deadline và giải phóng những registration/closure khi task không còn cần.

### 13.2. Task scope khác thread scope

Ở thread pool, một worker có thể thực thi nhiều task lần lượt. Một wrapper đúng phải mở context cho **mỗi lần task chạy**, không set một lần khi worker được tạo.

Một task có thể có nested subtasks; nếu chạy trực tiếp trên cùng thread, scope nested phải được khôi phục; nếu chạy thread khác, cần truyền context riêng theo hợp đồng. Không dùng các khái niệm này thay cho nhau.

## 14. AOP per-control-flow và `cflow` cần được diễn giải riêng

Một số mô hình AOP có pointcut theo **dynamic control flow** và cơ chế tạo aspect instance theo flow. Điều đó khác với lưu một giá trị trong ThreadLocal thuần.

```text
Root.handle(A)                 -> Flow F1
   |
   +-- child.method()          -> advice dùng flow F1
   |
   +-- Root.handle(B)          -> có thể tạo nested F2
         |
         +-- child.method()    -> advice theo F2
   |
   +-- child.method()          -> trở lại F1
```

Nếu công nghệ hỗ trợ **per-control-flow instantiation**, chính sách xác định khi nào có instance F1/F2 và advice thuộc instance nào. `ThreadLocal` có thể được một công cụ sử dụng bên trong, nhưng **không phải bằng chứng mọi công nghệ triển khai per-flow bằng ThreadLocal**.

### 14.1. Truyền context không tự kéo dài một dynamic control flow

Một wrapper chuyển trace ID từ thread A sang B chỉ chuyển dữ liệu đã chọn; nó **không** tự làm cho call stack ở B trở thành phần bên dưới method execution root trên A trong ngữ nghĩa của một pointcut `cflow` truyền thống.

Nếu cần theo dõi logical operation xuyên async, phải dùng mô hình propagation hỗ trợ, không chỉ tạo một chuỗi giống nhau ở hai thread rồi coi đó là native `cflow`.

### 14.2. Scope per-thread vs per-invocation với lời gọi lồng nhau

Nếu một advice đọc ThreadLocal trong scope outer rồi nested advice ghi một ID khác, nó phải khôi phục outer. Nhưng một aspect per-invocation có thể giữ mỗi ID trong **biến cục bộ** của lời gọi và không cần ThreadLocal. Chỉ chọn per-thread khi có nhiều thành phần **trên cùng thread** cần truy cập context mà không tiện chuyền tham số.

## 15. Những sai lầm dễ gặp

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Coi ThreadLocal là request scope | Context stale ở worker tái sử dụng | Tách scope theo từng task/request, teardown rõ |
| Quên `remove()` sau `set()` | Lẫn dữ liệu và giữ object | `finally`/try-with-resources |
| Inner scope luôn gọi `remove()` | Mất outer context | Lưu và khôi phục previous |
| Dùng `set(null)` như tương đương `remove()` | Để lại entry/khác `withInitial` | Dùng remove khi muốn xóa mapping |
| Dùng `InheritableThreadLocal` để truyền request qua pool | Giá trị kế thừa lúc tạo worker, không theo submit | Snapshot + scope trong task |
| Cho rằng ThreadLocal bảo vệ mutable value | Hai thread vẫn có thể chia sẻ cùng object | Immutable snapshot hoặc đồng bộ rõ |
| Lưu identity trong field singleton aspect | Race, lẫn quyền, retention | Context per-invocation đáng tin |
| Mở scope khi tạo worker thay vì khi chạy task | Task sau thừa hưởng context cũ | Scope trên từng `Runnable/Callable` |
| Tạo ThreadLocal mới liên tục và bỏ quên | Stale entries/value giữ bộ nhớ | Tái sử dụng key có owner, cleanup đầy đủ |
| Thay ThreadLocal bằng static global | Lẫn giữa các thread | Thiết kế theo ownership, không dùng state chung tùy tiện |
| Propagate cả request mutable sang async | Race, giữ payload/tài nguyên | Chỉ dữ liệu tối thiểu, TTL/ownership rõ |
| Đóng scope ở thread khác | Khôi phục sai ThreadLocal | Gắn owner thread và đóng đúng thread |
| Tưởng proxy tự bao phủ self-invocation | Advice mong đợi không chạy | Kiểm tra đường gọi/proxy/weaver thực |
| Chỉ test đường thành công | Rò context khi throw | Test return, throw, cancel/timeout |
| Chỉ quan sát tổng heap | Khó thấy retention hoặc lẫn identity | Kiểm tra context thực tế và path to GC root |
| Tưởng cùng correlation ID nghĩa là cùng request hợp lệ | Dữ liệu stale/tampering | Xác minh nguồn gốc, phạm vi và thời hạn |
| Dùng future return làm completion | Dọn quá sớm hoặc đo sai | Theo dõi completion stage thực tế |

## 16. Ma trận kiểm thử gợi ý

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Lời gọi qua proxy trên thread chính | Scope mở, target thấy context, scope đóng |
| Target trả về bình thường | Result giữ nguyên, ThreadLocal restore |
| Target ném ngoại lệ | Lỗi gốc được truyền, context không rò |
| Nested scope | Inner tạm thay state; outer được khôi phục |
| Hai request tuần tự trên một worker | Request sau không nhìn thấy state cũ |
| Nhiều worker đồng thời | Mỗi thread có mapping riêng, không dùng chung mutable value trái hợp đồng |
| Cố ý quên cleanup | Regression test phát hiện giá trị stale |
| Worker task không có propagation | Không mặc định thấy context của caller |
| Propagation được bật rõ | Worker thấy snapshot được cấp, sau task sạch |
| Caller sau submit | Scope gốc không bị worker sửa |
| Dùng `InheritableThreadLocal` với pool | Không dựa vào inheritance per submit |
| `withInitial` + `remove()` | Giá trị được khởi tạo lại theo hợp đồng |
| Async completion sau return | Không dùng context đã hết hạn hoặc resource đóng |
| Task bị cancel/timeout | Snapshot/callback và cleanup theo lifecycle thực |
| Lời gọi trực tiếp target | Không tự nhận advice của proxy |
| Self-invocation | Hiểu điểm nào bypass interception |
| Nhiều overload cùng tên | Bộ lọc chữ ký không chọn sai |
| Dữ liệu quyền bắt buộc | Không chấp nhận context thiếu/stale |
| Hoán đổi thứ tự retry/context scope | Phạm vi per-attempt/per-request đúng |
| Heap sau workload | Không giữ request graph qua worker sống lâu trái ý định |

### 16.1. Test nên kiểm tra giá trị, không dựa vào timing GC

Một test rõ ràng với `newSingleThreadExecutor()` có thể đặt giá trị ở task thứ nhất và đọc nó ở task thứ hai. Dùng `Future.get()` để buộc thứ tự, không cần `Thread.sleep()`.

Đối với memory leak, test hành vi có thể kiểm tra `ThreadLocal` đã được dọn và registry/callback đã được tháo; heap dump/path to GC root hữu ích khi phân tích retention, nhưng **không** dùng việc gọi `System.gc()` rồi chờ object biến mất trong khoảng thời gian cứng làm tiêu chí duy nhất.

### 16.2. Test giá trị trước và sau nested scope

Một bộ test tối thiểu:

```text
Set A
  scope B:
    assert current == B
  close B
  assert current == A
close A
assert current == none
```

Đây là giả mã. Cần bổ sung đường throw: nếu scope B ném lỗi, trạng thái A vẫn được khôi phục, lỗi gốc vẫn tới caller và không có context B còn sống ở worker.

## 17. Tài nguyên, bảo mật và vận hành

### 17.1. Không lưu đối tượng nhạy cảm nếu chỉ cần correlation ID

Một aspect tracing có thể chỉ cần correlation ID đã chuẩn hóa. Lưu cả token đăng nhập, `HttpRequest`, credential, payload hay connection trong ThreadLocal sẽ mở rộng đồ thị retention và rủi ro heap dump/log.

Metadata quan sát nên được allowlist, hạn chế độ dài, có TTL/owner theo logical task và được xử lý theo chính sách riêng tư. Correlation ID không phải chứng cứ ủy quyền.

### 17.2. Readiness và cleanup lỗi

Nếu cơ chế mở scope bắt buộc không thể hoạt động, cần có chính sách có được đi tiếp target hay không. Đặc biệt với guard bảo mật, không thể âm thầm bỏ qua khi hệ thống AOP hoặc proxy không được cấu hình đúng.

Nếu thao tác cleanup có lỗi, cần phân loại: lỗi observer có thể được cô lập để không che ngoại lệ target, còn lỗi giải phóng transaction/lock có thể tạo trạng thái chưa chắc chắn. Không có một `catch(Throwable)` đúng cho mọi tình huống.

### 17.3. Đo trạng thái theo đơn vị phù hợp

Đừng dùng “số thread hiện có” làm số request đang xử lý. Một worker có thể tuần tự làm nhiều task; một task có thể fan out sang nhiều thread. Các chỉ số hữu ích thường là **số scope được mở/đóng**, số task thiếu context bắt buộc, số lần stale context bị phát hiện, số propagation bị từ chối và số resource còn mở.

Không ghi toàn bộ ThreadLocal values để debug: nó có thể chứa dữ liệu nhạy cảm và bản ghi quá lớn.

## 18. Bài tập vận dụng có đáp án

### Bài 1 — Hai tác vụ, một worker

Task A đặt `CURRENT.set("A")` rồi kết thúc. Task B được pool giao cho đúng worker ấy và gọi `CURRENT.get()`. Có chắc thấy null không?

**Đáp án:** Không. Nếu A không remove/restore, B có thể thấy `"A"`. Thread pool tái sử dụng thread, trong khi ThreadLocal gắn với thread chứ không gắn với mỗi task.

### Bài 2 — Nested scope

Outer đặt context `A`. Inner đặt `B` rồi đóng. Nếu inner chỉ gọi `remove()`, điều gì sai?

**Đáp án:** State A của outer bị mất. Cần lưu previous trước khi set B, sau khi inner kết thúc phải restore A; chỉ remove nếu trước đó thật sự không có scope.

### Bài 3 — Worker async

Main thread giữ correlation ID `Q-7`, rồi submit task sang `ExecutorService`. ThreadLocal thông thường có tự xuất hiện trong worker không?

**Đáp án:** Không. Phải truyền snapshot dữ liệu cần thiết và mở scope trên worker, sau đó cleanup/restore khi task kết thúc.

### Bài 4 — InheritableThreadLocal

Một worker của thread pool được tạo trước request. Request A sau đó `set("A")` vào `InheritableThreadLocal` trên thread gọi và submit task. Worker có chắc thấy A không?

**Đáp án:** Không. Kế thừa giá trị gắn với lúc **thread được tạo**, không tự cập nhật theo mỗi task submit. Pool tái sử dụng làm giả định ấy sai.

### Bài 5 — Shared object

Thread A và B đều `TL.set(sharedMutableContext)`. Mỗi thread có mapping riêng. Có cần bảo vệ race khi sửa field trong `sharedMutableContext` không?

**Đáp án:** Có. Mapping riêng không tạo bản sao của object. Cả hai vẫn giữ cùng tham chiếu và có thể ghi/đọc đè lên nhau.

### Bài 6 — Lỗi nghiệp vụ

Around advice mở scope, target ném lỗi. Nếu dọn context chỉ ở nhánh after-returning, hậu quả?

**Đáp án:** Nhánh throw không gọi after-returning, nên context có thể bị giữ trong worker. Dùng finally/teardown tương ứng và truyền lỗi gốc.

### Bài 7 — Dữ liệu quyền

Một ThreadLocal còn giữ `authorized=true` từ task trước. Có được xem nó là quyền của task hiện tại không?

**Đáp án:** Không. Đây là dữ liệu stale không có nguồn xác thực hợp lệ cho task hiện tại. Bảo vệ effect bằng guard đáng tin, phân biệt thiếu/không hợp lệ, và dọn context theo scope.

### Bài 8 — Per-flow hay per-thread?

Một thread xử lý hai lời gọi root riêng biệt. Nếu muốn aspect instance riêng cho từng root, chỉ dùng một `ThreadLocal<Aspect>` set một lần khi worker sinh ra có đủ không?

**Đáp án:** Không. Phải tạo/kích hoạt/khôi phục instance theo từng **root activation**, không theo cả vòng đời worker. Nếu công nghệ hỗ trợ per-control-flow, dùng hợp đồng đó; nếu không, tự quản lý context scope rõ ràng.

### Bài 9 — Dùng `set(null)`

Một `ThreadLocal` tạo bằng `withInitial`. Sau `set(null)`, gọi `get()` có giống sau `remove()` rồi `get()` không?

**Đáp án:** Không nhất thiết. `set(null)` để value null; `remove()` bỏ mapping và lần `get()` sau có thể gọi supplier để tạo giá trị mới.

### Bài 10 — Proxy bypass

Một aspect qua JDK proxy mở ThreadLocal khi `WorkPort.handle` được gọi, nhưng người dùng gọi trực tiếp `new WorkService().handle()`. Có scope của proxy không?

**Đáp án:** Không. Đường gọi trực tiếp target bỏ qua handler của proxy. Cần kiểm tra đường cấp tham chiếu và loại join point được cơ chế hỗ trợ; không dùng ThreadLocal như bằng chứng mọi lời gọi đã được can thiệp.

### Bài 11 — Khối async trả future

Một advice mở scope, gọi method trả `CompletableFuture`, rồi đóng scope ở after-returning. Tác vụ future chạy muộn trên worker có nằm trong scope đó không?

**Đáp án:** Không thể mặc định. Method đã trả future nhưng tác vụ chưa chắc hoàn thành; cần context propagation và lifecycle theo completion/worker phù hợp.

## 19. Ghi nhớ

- **Trạng thái theo thread không đồng nghĩa trạng thái theo request, flow hay invocation.** Thread có thể phục vụ nhiều task, còn một request có thể dùng nhiều thread.
- **`ThreadLocal` tách mapping theo thread**, không tự deep-copy value mutable và không tự truyền giá trị sang executor.
- **Nhóm luồng tái sử dụng worker**: quên restore/remove gây context stale, lẫn dữ liệu bảo mật và giữ object ngoài ý muốn.
- **Nested scope phải khôi phục trạng thái cha**; cleanup sau return/throw là một phần hợp đồng của advice.
- **`InheritableThreadLocal` không giải quyết propagation per-task của thread pool** và có nguy cơ copy tham chiếu mutable sai phạm vi.
- Khi có async, **capture dữ liệu tối thiểu từ caller và cài scope trên worker khi task chạy**, rồi restore/cleanup.
- Chỉ dùng trạng thái theo thread khi nhiều điểm trên **cùng synchronous call stack** thật sự cần đọc chung context; ưu tiên **biến cục bộ và context tường minh** nếu đủ.
- AOP qua proxy có **đường bypass**, và bytecode weaving có mô hình điểm can thiệp riêng; không xem một giá trị ThreadLocal là bằng chứng chính sách đã áp ở mọi đường.
- Với chính sách quan trọng, phải kiểm thử **đúng scope, lỗi, nested calls, thread reuse, propagation, memory retention và độ phủ join point**.
