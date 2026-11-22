# Nguy cơ rò rỉ bộ nhớ và giữ đối tượng ngoài ý muốn trong vòng đời aspect (AOP)

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), một **aspect** chứa mã cắt ngang (*advice*) áp dụng tại các **điểm can thiệp** (*join point*) được **pointcut** lựa chọn. Aspect có thể tồn tại suốt vòng đời ứng dụng, theo từng đối tượng, từng luồng điều khiển hoặc theo một chính sách instantiation riêng nếu công nghệ hỗ trợ. Chính sự chênh lệch giữa **vòng đời của aspect** và **vòng đời dữ liệu mà advice quan sát** tạo ra nguy cơ rò rỉ bộ nhớ (*memory leak*) hoặc giữ đối tượng lâu hơn dự kiến (*unintended retention*).

Ví dụ, một aspect dùng chung suốt ứng dụng ghi `lastRequest = request` trong field. Sau khi xử lý xong, request lẽ ra không cần thiết nữa, nhưng **aspect vẫn giữ tham chiếu mạnh tới request**. Nếu request còn giữ một payload lớn, session, user context hoặc cây đối tượng, những đối tượng ấy có thể tiếp tục *reachable* từ một gốc GC (*GC root*) và chưa được thu gom.

Nguy cơ không chỉ là một field. Listener đăng ký ở singleton event bus, `ThreadLocal` trên thread pool, cache metadata khóa theo `Class`/`ClassLoader`, callback bất đồng bộ hoặc proxy được lưu trong registry sống lâu đều có thể làm **vòng đời của một đối tượng ngắn hạn bị kéo dài**. Ngược lại, **không phải mọi đối tượng còn sống sau một lời gọi đều là leak**: cache có giới hạn và dữ liệu cần được giữ theo hợp đồng vẫn có thể là retention hợp lệ.

Bài học này trình bày **AOP tổng quát**, phân biệt chiến lược vòng đời aspect với vòng đời object/tài nguyên; đưa ra mô hình tham chiếu, cách phòng tránh, kiểm thử và ví dụ Java 17 chạy độc lập. Khả năng của mỗi cơ chế weaving/proxy, định nghĩa instance per-target/per-flow và cleanup hook khác nhau theo công nghệ; không giả định mọi AOP có cùng API hoặc tự thu hồi tài nguyên hộ người lập trình.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **memory leak**, **giữ đối tượng ngoài ý muốn**, **tăng bộ nhớ tạm thời** và **rò rỉ tài nguyên ngoài heap**.
2. Giải thích cơ chế **GC root → strong reference → aspect/proxy/context → object ngắn hạn** khiến đối tượng còn reachable.
3. Đánh giá rủi ro của singleton aspect, aspect theo đối tượng, aspect theo luồng điều khiển và các trạng thái lưu trong advice.
4. Nhận diện listener/callback chưa hủy, `ThreadLocal` trên thread pool, cache không giới hạn và class-loader retention.
5. Hiểu vì sao vòng tham chiếu đơn thuần không nhất thiết là leak trong JVM dùng tracing garbage collection.
6. Thiết kế **ownership**, lifecycle, đăng ký/hủy đăng ký, `try/finally`, `AutoCloseable` và giới hạn cache phù hợp.
7. Đọc ví dụ Java 17 cho thấy event bus giữ aspect qua listener và cách một scope `ThreadLocal` được khôi phục khi lồng nhau/throw.
8. Kiểm tra leak bằng phép đo retention và heap analysis, không dựa vào `System.gc()` để khẳng định thu hồi đúng thời điểm.
9. Giữ advice theo dõi đơn giản, ít dữ liệu nhạy cảm và không làm thay kết quả hoặc ngoại lệ nghiệp vụ.

## 2. Memory leak trong Java có nghĩa gì?

Một chương trình Java được JVM thu gom rác, nhưng GC chỉ có thể thu gom những đối tượng **không còn reachable từ các GC root** theo mô hình collector. Các GC root có thể bao gồm những tham chiếu trên stack của thread đang chạy, các trường static, JNI handle hoặc những root nội bộ khác.

Nếu một object không còn cần cho nghiệp vụ nhưng vẫn reachable từ root qua chuỗi tham chiếu, nó **không được thu gom** dù không ai trong logic mong muốn sử dụng nữa.

```text
GC ROOT (static holder)
        |
        v
Long-lived Aspect instance
        |
        +--> lastRequest
                  |
                  v
             RequestContext
                  |
                  v
              BigPayload
```

Nếu `lastRequest` vẫn trỏ tới `RequestContext` sau khi lời gọi xong, object và những object nó tham chiếu có thể còn reachable.

### 2.1. Leak không đồng nghĩa luôn tăng mãi

Một field `lastRequest` giữ **một** request cuối có thể tạo retention không mong muốn nhưng không nhất thiết làm heap tăng mãi theo số request. Ngược lại, một `List<Request>` chỉ thêm mà không xóa có thể tăng tỷ lệ thuận với số lượt gọi.

Cần phân biệt:

| Hiện tượng | Mô tả | Kết luận nên thận trọng |
| --- | --- | --- |
| **Unintended retention** | Dữ liệu đã hết nhu cầu nhưng vẫn được tham chiếu | Cần xem vòng đời và ownership |
| **Unbounded growth** | Số phần tử giữ lại tăng mà không có giới hạn phù hợp | Nguy cơ lớn dẫn tới thiếu bộ nhớ |
| **Valid cache retention** | Dữ liệu còn được giữ có chủ đích trong ngân sách | Chưa chắc là leak |
| **Temporary allocation spike** | Nhiều object được tạo trong một đợt tải | Có thể GC về sau, chưa chứng minh leak |
| **Off-heap/resource leak** | File handle, socket, direct buffer, connection không được trả đúng lúc | Có thể gây lỗi dù heap không tăng |
| **GC cycle** | A trỏ B và B trỏ A, không còn reachable từ root | JVM có thể thu gom chu trình này |

Một **vòng tham chiếu không tự tạo leak** trên JVM dùng tracing GC. Nguy cơ là **đường tham chiếu tới một GC root sống quá lâu**.

### 2.2. Không lấy việc GC chưa chạy làm bằng chứng leak

Sau một lượt request, heap có thể vẫn hiển thị vùng nhớ cũ vì JVM chưa cần thu gom hoặc vẫn giữ vùng heap đã cấp. Quan trọng là **số object còn được giữ sau những đợt GC phù hợp**, đường giữ tham chiếu, tuổi thọ/khả năng tiếp tục tăng và hợp đồng nghiệp vụ.

`System.gc()` chỉ là yêu cầu/hint trong những cấu hình JVM, không bảo đảm object đã được thu gom ngay hoặc một đối tượng cụ thể phải biến mất. Vì thế ví dụ chạy được trong bài **không đo leak bằng cách chờ WeakReference trở thành null**; nó đo cấu trúc tham chiếu và số đăng ký một cách xác định.

## 3. Vì sao vòng đời aspect tạo nguy cơ riêng?

Trong AOP, developer thường viết advice như một đoạn “chạy thêm tại nhiều nơi”, nhưng các field của **aspect instance** có thể sống lâu hơn rất nhiều so với biến cục bộ của mỗi advice invocation.

Giả sử:

```java
class TrackingAspect {
    Object lastArguments;

    void observe(Object[] arguments) {
        lastArguments = arguments;
    }
}
```

Đây là đoạn minh họa, không phải một aspect hoàn chỉnh. Nếu `TrackingAspect` là singleton sống suốt ứng dụng, field `lastArguments` tiếp tục giữ mảng đối số và các object được mảng ấy tham chiếu **sau khi phương thức nghiệp vụ kết thúc**. Nếu array chứa request, payload hoặc kết nối, retention lan theo đồ thị object.

Sửa bằng cách giữ **thông tin nhỏ, bất biến và có chủ đích**, chẳng hạn số lượng lời gọi, loại join point hoặc một ID đã được xử lý an toàn; hoặc giữ dữ liệu trong biến cục bộ và không xuất nó sang một holder sống lâu.

### 3.1. Từng kiểu instantiation có phạm vi retention khác

| Chính sách vòng đời | Gắn instance với | Nguy cơ khi giữ state |
| --- | --- | --- |
| **Shared/singleton aspect** | Một instance dùng chung theo phạm vi công nghệ | Field có thể giữ dữ liệu từ bất kỳ request nào; nguy cơ lẫn dữ liệu concurrent |
| **Per-target/per-this** nếu hỗ trợ | Đối tượng target/`this` tương ứng | Instance sống theo quan hệ giữ target; có thể tạo vòng tham chiếu hoặc retention qua registry |
| **Per-control-flow** nếu hỗ trợ | Một activation luồng điều khiển động | Context không pop/remove khi return/throw; nested flow khôi phục sai; async propagation sai |
| **Per-type** nếu hỗ trợ | Loại/lớp tương ứng | Metadata hoặc cache có thể giữ class loader lâu sau khi cần unload |
| **Per-invocation state** trong biến cục bộ | Một lần advice chạy | Thường ngắn hơn, trừ khi escape vào callback/cache/closure |
| **Custom scope** | Token hoặc context do chương trình cấp | Ownership và teardown do chương trình định nghĩa |

Từ “per-target” **không tự bảo đảm không leak**. Một cache toàn cục ánh xạ target → aspect instance có thể giữ target sống mãi nếu khóa được giữ mạnh. Ngược lại, một aspect có field trỏ target và target trỏ aspect tạo chu trình nhưng **nếu toàn bộ chu trình không reachable từ root**, GC vẫn có thể thu gom.

### 3.2. Instance aspect không phải resource manager tự động

Khi một aspect instance hết phạm vi sử dụng, Java **không gọi một destructor đáng tin theo thời gian thực** để đóng socket hoặc file. Một công nghệ có thể cung cấp callback/lifecycle hook, nhưng phải kiểm tra hợp đồng cụ thể.

Không đồng nhất:

- **Instance không còn active ở flow:** không còn dùng cho luồng đó.
- **Instance không còn reachable:** GC có thể thu gom sau này.
- **Tài nguyên đã được đóng:** phải có hành vi `close`/release đúng quyền sở hữu.

Ba sự kiện có thể xảy ra ở **thời điểm khác nhau**.

## 4. Nguyên nhân 1: field trong aspect dùng chung giữ request

Một singleton aspect tiện cho counter/timing aggregator, nhưng không phù hợp để lưu mọi đối tượng request.

Mã nguy hiểm về mặt cấu trúc:

```java
final class UnsafeAspect {
    private final java.util.List<Object> requests =
            new java.util.ArrayList<>();

    void before(Object request) {
        requests.add(request);
    }
}
```

Đây là code minh họa **không có chương trình `main`**. Nếu `before` được gọi cho mỗi request và danh sách không có chính sách xóa/bounded retention, số phần tử tăng theo thời gian. Hơn nữa, `Object` có thể là một đồ thị dữ liệu lớn, chứ không chỉ một chuỗi ngắn.

Một hướng thiết kế tốt hơn:

```java
final class CountingAspect {
    private final java.util.concurrent.atomic.LongAdder calls =
            new java.util.concurrent.atomic.LongAdder();

    void before() {
        calls.increment();
    }

    long total() {
        return calls.sum();
    }
}
```

`LongAdder` thích hợp cho một số bộ đếm concurrent có tải cao. Giá trị `sum()` có thể không biểu diễn một snapshot tuyến tính hoàn hảo khi có các cập nhật đồng thời, nên không dùng nó làm bằng chứng giao dịch nếu cần consistency mạnh. Nhưng nó tránh việc lưu **toàn bộ request** chỉ để đếm lượt gọi.

### 4.1. Lưu “last request” vẫn có vấn đề

Một trường đơn `lastRequest` giữ lại **ít nhất một request** ngoài vòng đời cần thiết. Nếu chứa credential, dữ liệu người dùng hoặc stream, hậu quả không chỉ là bộ nhớ: còn có rủi ro riêng tư và tài nguyên bị giữ.

Nếu cần debug dữ liệu cuối cùng, hãy đặt **thời hạn, kích thước giới hạn, làm mờ thông tin nhạy cảm, quyền truy cập và mục đích sử dụng**. Không lưu `this`, `target` hoặc `args` nguyên dạng một cách vô thức.

### 4.2. Thread safety là vấn đề kèm theo

Field của aspect singleton có thể bị nhiều advice chạy đồng thời đọc/ghi. Nếu dùng một field `currentRequest`, request A có thể đọc giá trị B đã ghi; đây vừa là lỗi chức năng vừa có thể giữ tham chiếu ngoài ý muốn.

Biến cục bộ theo invocation không có cùng rủi ro chia sẻ trực tiếp; tuy vậy nếu object cục bộ **escape** vào future/listener/cache thì vòng đời của nó lại phụ thuộc holder.

## 5. Nguyên nhân 2: đăng ký listener/callback nhưng không hủy

Một advice có thể đăng ký callback để theo dõi sự kiện, timer hoặc transaction outcome:

```text
Global event bus / dispatcher (sống lâu)
     |
     v
Listener hoặc lambda được đăng ký
     |
     v
Captured aspect / target / request
     |
     v
Payload, session, closure data
```

Với callback dạng `aspect::onEvent`, đối tượng method reference thường giữ **receiver `aspect`**. Khi event bus giữ callback trong danh sách dài hạn, aspect cũng còn reachable. Nếu aspect giữ payload lớn, **cả payload bị giữ theo**.

Đây là dạng retention đặc biệt dễ nhầm vì lời gọi nghiệp vụ đã kết thúc nhưng registry vẫn còn.

### 5.1. Thiết kế registration có quyền đóng

Tốt nhất API đăng ký trả về một **handle có thể hủy**:

```text
registration = bus.register(listener)
try:
    runScopedOperation()
finally:
    registration.close()
```

Đây là giả mã. Việc gọi `close` phải loại listener khỏi registry, xử lý đóng nhiều lần nếu hợp đồng yêu cầu và không làm hỏng phiên xử lý khác.

Không phải mọi listener thuộc scope ngắn: listener cấp ứng dụng tồn tại đến khi ứng dụng dừng có thể là hợp lệ. Nhưng người quản lý phải định nghĩa **lúc nào tháo đăng ký**; không thể dựa vào GC để xóa một callback đang được registry giữ mạnh.

### 5.2. Listener giữ đối tượng thông qua lambda

Ví dụ một lambda:

```java
void subscribe(EventBus bus, RequestContext request) {
    bus.onEvent(event -> audit(request, event));
}
```

Đây là **đoạn minh họa với kiểu chưa định nghĩa**. Lambda capture `request` và có thể capture receiver hoặc biến khác cần cho `audit`. Nếu `bus` sống lâu, nó có thể giữ `request` lâu theo. Việc code nằm trong advice không làm capture đó yếu đi.

Giải pháp là hủy registration đúng lifecycle hoặc truyền **dữ liệu tối thiểu không nhạy cảm** thay vì giữ nguyên request.

## 6. Nguyên nhân 3: `ThreadLocal` chưa được dọn trên thread pool

`ThreadLocal` có thể dùng để lưu context của một luồng thực thi đồng bộ:

```text
Thread pool worker
   |
   +--> ThreadLocal state
           |
           v
        Context / Aspect instance
           |
           v
       Large request graph
```

Thread pool có thể giữ thread sống qua nhiều request. Nếu advice `set(context)` nhưng quên `remove()`/khôi phục giá trị cũ, context có thể ở lại trên thread và bị request sau nhìn thấy. Vấn đề là **retention và rò rỉ ngữ cảnh**, không chỉ heap.

### 6.1. Dọn đúng trong `finally`

Mẫu căn bản khi chắc chắn **không có scope cha**:

```java
CONTEXT.set(context);
try {
    return operation.run();
} finally {
    CONTEXT.remove();
}
```

Đây là **giả mã có tên chưa định nghĩa**. `finally` bao cả đường trả về bình thường và ném ngoại lệ sau khi scope đã vào `try`. Nhưng một tình huống **scope lồng nhau** cần phức tạp hơn: nếu context cha đang tồn tại thì phải **khôi phục cha**, không xóa toàn bộ.

### 6.2. Nested scope: lưu trước và khôi phục sau

```java
Context previous = CONTEXT.get();
CONTEXT.set(current);
try {
    runBody();
} finally {
    if (previous == null) {
        CONTEXT.remove();
    } else {
        CONTEXT.set(previous);
    }
}
```

Đây là đoạn minh họa. Nó giúp outer scope sống tiếp sau khi inner scope kết thúc. Tuy nhiên, nếu `null` có thể là **giá trị context hợp lệ cần phân biệt với không có mapping**, phải có chính sách trạng thái rõ hơn hoặc cấu trúc stack; `ThreadLocal.get()==null` đơn thuần không phân biệt được hai trạng thái.

### 6.3. Vì sao `ThreadLocal` không đồng nghĩa request scope?

Một request có thể chuyển qua nhiều thread; một thread có thể xử lý nhiều request tuần tự. Với executor, giá trị `ThreadLocal` từ thread gửi tác vụ **không tự truyền** sang worker.

Kể cả khi dùng cơ chế propagation có chủ đích, phải có luật **khôi phục trạng thái trước đó trên worker và dọn ở cuối task**. Truyền nguyên instance aspect có dữ liệu mutable sang nhiều luồng cũng đòi hỏi kiểm soát concurrency.

### 6.4. Weak key của ThreadLocal không cứu được strong value

Một số cấu trúc `ThreadLocalMap` của JVM có cách giữ key yếu nhưng value mạnh. Điều đó không có nghĩa quên `remove()` là an toàn: **value vẫn có thể còn bị giữ** qua entry chưa được dọn, nhất là khi thread sống lâu.

Tránh lập luận “ThreadLocal tự được GC khi key mất”, hoặc “ThreadLocal mới cho mỗi request thì không cần cleanup”. Cách phòng tránh đáng tin là **ownership và teardown**.

## 7. Nguyên nhân 4: cache không có giới hạn trong aspect

Aspect thường cache dữ liệu để giảm chi phí reflection hoặc chọn pointcut:

- Metadata `Method`, `Class`, annotation;
- Kết quả phân tích chữ ký;
- Đối tượng proxy/target;
- Thông tin caller;
- Các kết quả nghiệp vụ;
- Idempotency keys hoặc dữ liệu tracking.

Nếu dùng một `static Map<Key, Value>` không có giới hạn, nó có thể giữ cả key và value vô hạn. Việc cache chỉ một vài metadata ở ứng dụng nhỏ có thể hoàn toàn hợp lệ; rủi ro phát sinh khi **số key tăng vô hạn, object lớn hoặc class loader cần được unload**.

### 7.1. Nguy cơ với class loader

Trong môi trường plugin, container hoặc reload:

```text
Application-wide static cache
   |
   +--> Class<?> hoặc Method
           |
           v
       Class metadata / defining ClassLoader
           |
           v
      Classes và dữ liệu có liên quan
```

Nếu cache thuộc một loader sống lâu nhưng key/value giữ lớp được nạp bởi loader ngắn hạn, lớp/loader cũ có thể không được giải phóng đúng thời điểm. Đây là **class-loader retention**, có thể ảnh hưởng heap hoặc vùng metadata, tùy cơ chế JVM.

### 7.2. `WeakHashMap` không phải bảo đảm tuyệt đối

Java có `WeakHashMap` với **weak keys**, nhưng values được giữ theo hợp đồng của map và có thể **tham chiếu ngược lại keys**. Ví dụ:

```text
WeakHashMap weak key -> strongly held value
                              |
                              +--> references the same key
```

Nếu value giữ key mạnh, key vẫn reachable từ map thông qua value; weak key **không giải quyết** vòng giữ đó.

Với cache lâu dài, cần xác định:

- Key và value có giữ đối tượng/class loader của scope ngắn hay không;
- Giá trị có thời hạn hết hạn/giới hạn kích thước;
- Cách xóa khi plugin/module/target kết thúc;
- Mức concurrency và atomicity khi tính/cache;
- Dữ liệu có thể tái tạo sau eviction không;
- Có cần một cache gắn đúng vòng đời class loader thay vì static global không.

### 7.3. Giữ `Method` hoặc `Class` có thể có hệ quả riêng

Một `Method` tham chiếu thông tin lớp khai báo. Một cache toàn cục lưu nhiều `Method` từ class loader được tạo động có thể giữ dữ liệu liên quan lâu hơn mong muốn. Không dùng weak references một cách máy móc; **thiết kế theo ownership của lớp và phạm vi cache** đáng tin hơn.

## 8. Nguyên nhân 5: proxy, target và registry sống lâu

AOP qua proxy tạo thêm các đường tham chiếu:

```text
Long-lived registry
      |
      v
Proxy
      |
      v
Interceptor chain
      |
      +--> Target
      +--> Aspect instance
      +--> Captured context
```

Nếu một global registry giữ proxy mãi, cả interceptor chain và target mà proxy còn trỏ tới cũng có thể bị giữ. Một target còn tham chiếu về proxy tạo **chu trình**, nhưng chu trình đó không tự là leak nếu không còn đường từ GC root.

Điều quan trọng là **registry/static singleton/session map** thực sự đang nắm giữ cái gì, và khi một module hoặc đối tượng hết vòng đời, registry có được cập nhật hay không.

### 8.1. Per-target aspect cũng có thể bị giữ lâu

Một số chiến lược tạo aspect instance theo target hoặc `this`. Nếu cơ chế phải duy trì ánh xạ từ target tới instance và ánh xạ ấy có vòng đời quá dài, nó có thể giữ target hoặc aspect sống ngoài ý muốn.

Không kết luận mọi per-target policy đều dùng strong map gây leak; cách lưu instance/weak reference và teardown là **chi tiết triển khai**. Nhưng trách nhiệm kiểm tra vòng đời target và cơ chế registry vẫn cần thiết.

### 8.2. Self-invocation và đường bypass không phải leak

Gọi thẳng target hoặc `this.otherMethod()` có thể bypass proxy. Đây là **lỗi độ phủ AOP** khác với memory retention. Tuy nhiên nó có thể gián tiếp gây retention nếu advice cleanup chỉ chạy khi đi qua proxy nhưng một đường khác lại cấp tài nguyên mà không được đóng.

Cần tách câu hỏi “pointcut và cơ chế có áp đúng?” khỏi “tài nguyên/trạng thái nào đang được giữ?”. Không sửa leak bằng cách nới wildcard mà không hiểu đường thực thi.

## 9. Nguyên nhân 6: callback, future và tác vụ bất đồng bộ

Một advice có thể đăng ký callback sau khi tạo `CompletableFuture`:

```java
future.whenComplete((result, error) -> {
    // Callback này có thể capture context hoặc instance aspect.
});
```

Đây là đoạn minh họa. Khi future chưa hoàn tất và còn được giữ bởi scheduler, queue hoặc ứng dụng, callback và những object nó capture có thể còn reachable. Ngay cả khi future đã hoàn tất, **mức độ giữ lại phụ thuộc vào các tham chiếu và hiện thực của tác vụ**, không thể suy chỉ từ chữ ký `whenComplete`.

### 9.1. Completion đồng bộ khác completion thực của tác vụ

Một phương thức trả `CompletableFuture` đang pending đã **trả về bình thường**, nên advice kiểu after-returning quanh phương thức tạo future có thể chạy trước khi công việc thực sự xong. Nếu advice dọn context/tài nguyên ngay ở return, task có thể mất context hoặc dùng tài nguyên đã đóng.

Ngược lại, nếu advice giữ context mãi chỉ vì không biết khi nào future xong, nó có thể tạo leak. Phải xác định **owner của tác vụ**, callback completion và điều kiện hủy/timeout phù hợp.

### 9.2. Hủy tác vụ không tự giải phóng mọi tham chiếu

Cancel có thể không hủy ngay công việc phía dưới hoặc callback đã đăng ký. Một task bị treo có thể giữ stack, local variables, closure và những object được capture. Cần ngân sách thời gian, quy tắc cleanup và cơ chế dừng/đối soát theo tính chất tác vụ.

Không dùng một `finally` quanh **hàm lên lịch** rồi khẳng định tài nguyên của **hàm chạy bất đồng bộ** đã được trả.

## 10. Ví dụ Java 17: listener giữ aspect và cách tháo đăng ký

Ví dụ này cố ý dựng **một registry có vòng đời ứng dụng** và các aspect chứa payload minh họa. Nó chứng minh cấu trúc giữ tham chiếu qua **số listener còn đăng ký**, không dựa vào GC chạy đúng lúc.

Chương trình cũng có một mô hình **scope theo luồng** có phục hồi context cha và dọn context khi lỗi. Đây là ví dụ Java thuần mô phỏng vòng đời dữ liệu của aspect; **không phải bộ weaver AOP đầy đủ**.

Lưu vào tệp `AspectRetentionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class AspectRetentionDemo {
    static final class EventBus {
        private final List<Consumer<String>> listeners = new ArrayList<>();

        Registration register(Consumer<String> listener) {
            listeners.add(listener);
            return new Registration(this, listener);
        }

        void unregister(Consumer<String> listener) {
            listeners.remove(listener);
        }

        int count() {
            return listeners.size();
        }

        void publish(String event) {
            for (Consumer<String> listener : List.copyOf(listeners)) {
                listener.accept(event);
            }
        }
    }

    static final class Registration implements AutoCloseable {
        private EventBus bus;
        private Consumer<String> listener;

        Registration(EventBus bus, Consumer<String> listener) {
            this.bus = bus;
            this.listener = listener;
        }

        @Override
        public void close() {
            if (bus != null) {
                bus.unregister(listener);
                bus = null;
                listener = null;
            }
        }
    }

    static final class TraceAspect {
        private final String id;
        private final byte[] snapshot = new byte[64 * 1024];

        TraceAspect(String id) {
            this.id = id;
        }

        void onEvent(String event) {
            System.out.println("EVENT " + id + ":" + event);
        }

        String id() {
            return id;
        }
    }

    private static final EventBus GLOBAL_BUS = new EventBus();
    private static final ThreadLocal<TraceAspect> CURRENT =
            new ThreadLocal<>();

    static void withScope(String name, Runnable action) {
        TraceAspect previous = CURRENT.get();
        CURRENT.set(new TraceAspect(name));
        try {
            action.run();
        } finally {
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }

    public static void main(String[] args) {
        for (int i = 1; i <= 2; i++) {
            TraceAspect aspect = new TraceAspect("leaky-" + i);
            GLOBAL_BUS.register(aspect::onEvent); // Không đóng handle.
        }
        System.out.println("LEAKY retained=" + GLOBAL_BUS.count());
        GLOBAL_BUS.publish("PING");

        EventBus scopedBus = new EventBus();
        for (int i = 1; i <= 2; i++) {
            TraceAspect aspect = new TraceAspect("safe-" + i);
            try (Registration ignored =
                    scopedBus.register(aspect::onEvent)) {
                scopedBus.publish("PING");
            }
            System.out.println("SAFE retained=" + scopedBus.count());
        }

        withScope("outer", () -> {
            System.out.println("CURRENT " + CURRENT.get().id());
            withScope("inner", () ->
                    System.out.println("CURRENT " + CURRENT.get().id()));
            System.out.println("RESTORED " + CURRENT.get().id());
        });
        System.out.println("OUTSIDE "
                + (CURRENT.get() == null ? "none" : "unexpected"));

        try {
            withScope("failed", () -> {
                System.out.println("CURRENT " + CURRENT.get().id());
                throw new IllegalArgumentException("bad input");
            });
        } catch (IllegalArgumentException error) {
            System.out.println("CAUGHT " + error.getMessage());
        }
        System.out.println("AFTER_FAILURE "
                + (CURRENT.get() == null ? "none" : "unexpected"));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 AspectRetentionDemo.java
java AspectRetentionDemo
```

Stdout được xác định theo chương trình:

```text
LEAKY retained=2
EVENT leaky-1:PING
EVENT leaky-2:PING
EVENT safe-1:PING
SAFE retained=0
EVENT safe-2:PING
SAFE retained=0
CURRENT outer
CURRENT inner
RESTORED outer
OUTSIDE none
CURRENT failed
CAUGHT bad input
AFTER_FAILURE none
```

### 10.1. Vì sao `GLOBAL_BUS` giữ aspect?

`GLOBAL_BUS` là static, còn `listeners` là danh sách strong references. Một callback tạo từ `aspect::onEvent` giữ receiver aspect. Đường giữ:

```text
Static GLOBAL_BUS
   -> EventBus.listeners
      -> Consumer callback
         -> TraceAspect
            -> byte[] snapshot
```

Trong vòng lặp “leaky”, code không giữ `Registration` trả về để đóng; listener vẫn tồn tại trong `GLOBAL_BUS`. Sau vòng lặp, biến cục bộ `aspect` không còn là lý do chính khiến đối tượng bị giữ: **registry sống lâu vẫn giữ callback**.

`LEAKY retained=2` **không đo số byte leak thực tế** và không chứng minh JVM đã hoặc chưa chạy GC. Nó cho thấy registry đang giữ hai đăng ký, mỗi callback có đường tham chiếu tới một aspect có snapshot.

### 10.2. Vì sao khối `try-with-resources` tránh giữ listener ngoài scope?

`scopedBus.register(...)` trả một `Registration` triển khai `AutoCloseable`. Khi `try` kết thúc, Java gọi `close()` kể cả khi thân try ném lỗi trong những đường điều khiển được bảo vệ. `close()` xóa đúng callback khỏi list.

Vì vậy mỗi vòng lặp in `SAFE retained=0`. Không cần gọi `System.gc()`, và không có tuyên bố object đã được giải phóng tức thì; chỉ có bảo đảm quan sát được là **registry không còn giữ listener đã đóng**.

### 10.3. Vì sao `Registration.close()` idempotent trong ví dụ?

Sau lần đóng đầu, nó đặt `bus=null` và `listener=null`. Nếu bị gọi lại, nhánh `if (bus != null)` không chạy, tránh unregister hai lần. Đây là một thiết kế tiện lợi cho **handle hủy đăng ký**.

Nếu event bus thật có listener cùng danh tính được đăng ký nhiều lần, concurrency hoặc yêu cầu đóng theo token, cần thiết kế API registration mạnh hơn là `List.remove(listener)`; ví dụ chỉ chạy tuần tự và mỗi listener là một callback riêng.

### 10.4. Vì sao scope inner trả lại outer?

`withScope` lưu `previous=CURRENT.get()` trước khi thay context. Khi inner kết thúc, finally đặt lại `previous=outer`, nên dòng `RESTORED outer` đúng. Khi outer kết thúc mà không có previous, code gọi `CURRENT.remove()`.

Nếu inner luôn gọi `CURRENT.remove()`, outer bị mất context trước khi hoàn tất. Nếu không cleanup khi có ngoại lệ, dòng `AFTER_FAILURE` có thể nhìn thấy state cũ trên thread tái sử dụng.

### 10.5. Điểm hạn chế cần nhớ

- Ví dụ không có AOP compiler, pointcut language, bytecode weaving hoặc proxy tự động.
- `snapshot` chỉ minh họa đồ thị giữ bộ nhớ, không là dữ liệu nghiệp vụ.
- Không dùng GC để xác nhận lifetime vật lý của object.
- `EventBus` dùng `ArrayList`, không an toàn cho thay đổi đăng ký đồng thời; chương trình chỉ chạy tuần tự.
- `ThreadLocal` chỉ chứng minh cơ chế context theo thread và nested scope; không có propagation sang executor/async.
- Cleanup registration không tự hủy effect ngoài hệ thống, file hoặc giao dịch; mỗi tài nguyên có hợp đồng riêng.
- Trong chương trình thật, không nên giữ thông tin nhạy cảm trong snapshot hoặc dump chúng vào log.

## 11. Dùng strong, weak và soft reference thế nào?

Java có một số loại tham chiếu với ngữ nghĩa khác nhau. Cần hiểu chúng trước khi định thay mọi field aspect thành `WeakReference`.

| Loại | Ý nghĩa khái quát | Lưu ý |
| --- | --- | --- |
| **Strong reference** | Giữ object reachable theo cách thông thường | Phù hợp khi object thực sự thuộc vòng đời holder |
| **WeakReference** | Không tự giữ object sống chỉ nhờ weak ref | Có thể được clear khi GC quyết định; không dùng cho dữ liệu bắt buộc phải tồn tại |
| **SoftReference** | Có thể được collector giải phóng theo chính sách bộ nhớ | Không thay thế cache có ngân sách và chính sách eviction |
| **PhantomReference** | Phục vụ cơ chế quan sát giai đoạn thu gom với `ReferenceQueue` | Không phải handle đóng tài nguyên đồng bộ, phải thiết kế phối hợp phù hợp |

Nếu dữ liệu phải còn tồn tại cho một nghiệp vụ đang xử lý, chuyển sang weak ref có thể làm **mất dữ liệu hợp lệ bất ngờ**. Nếu dữ liệu không còn cần, loại bỏ strong reference ở **đúng ownership boundary** thường đơn giản và đúng hơn.

### 11.1. Không dùng weak reference như cách né cleanup

Một callback trong registry không được tháo đăng ký vẫn có thể tiêu thụ tài nguyên hoặc chạy logic không mong muốn, ngay cả khi nó chỉ giữ weak ref tới target. Nếu listener được gọi sau khi target đã biến mất, cần xử lý kết quả null; listener bản thân nó có thể tiếp tục nằm trong registry mãi.

Có thể dùng weak listener khi kiến trúc thật cần và API hỗ trợ, nhưng **hủy đăng ký rõ ràng** vẫn là cơ chế dễ kiểm chứng.

### 11.2. Weak-key cache có vòng tham chiếu qua value

Với `WeakHashMap<K,V>`, key có thể yếu nhưng value thường được map giữ mạnh. Nếu V chứa K thì vẫn có đường mạnh từ map qua value tới K. Người lập trình phải kiểm tra **toàn bộ đồ thị tham chiếu**, không chỉ loại map.

## 12. Làm sao chẩn đoán leak trong ứng dụng AOP?

Một cách chẩn đoán có hệ thống:

1. **Xác định triệu chứng:** tăng heap dùng sau GC, tăng số instance/registrations, độ trễ GC, OOME hay tài nguyên ngoài heap bị cạn.
2. **Tạo workload lặp lại có kiểm soát:** cùng tập request, số vòng tăng, không thay ngẫu nhiên dữ liệu.
3. **Chờ điều kiện ổn định hợp lý:** phân biệt object ngắn hạn với object còn sống thật.
4. **Đo retained objects:** số instance aspect, request context, payload, callback, proxy, cache entry và thread local value.
5. **Lấy heap dump ở môi trường phù hợp:** chú ý dữ liệu nhạy cảm trong dump.
6. **Tìm paths to GC roots:** từ object lẽ ra đã chết theo registry/static field/thread/callback/class loader nào.
7. **Xem dominator tree/retained size:** holder nào chịu trách nhiệm giữ toàn bộ đồ thị lớn.
8. **Kiểm tra sau teardown:** registration đã close? scope đã remove? cache đã evict? module có unload?
9. **Sửa theo owner thực sự:** không chỉ `System.gc()`, đặt object thành null ở một nơi không sở hữu ref hoặc tăng heap.
10. **Chạy lại workload:** so sánh cùng thông số và giữ regression test.

### 12.1. Công cụ chẩn đoán thường gặp trong JVM

Có thể dùng **Java Flight Recorder (JFR)**, công cụ phân tích heap dump, Java Mission Control hoặc các lệnh JDK như `jcmd` theo khả năng môi trường. Ví dụ cú pháp tổng quát trên JDK phù hợp:

```bash
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump heap.hprof
```

`<PID>` là placeholder cần thay bằng PID thực; đây là **lệnh mẫu để chẩn đoán**, không phải đoạn tự chạy nguyên văn. Tên tùy chọn, quyền truy cập và tác động của lệnh cần kiểm tra theo JDK/JVM đang sử dụng. Heap dump có thể chứa token, thông tin cá nhân hoặc dữ liệu nghiệp vụ; chỉ tạo/lưu/chia sẻ theo chính sách bảo mật và ngân sách vận hành phù hợp.

**Class histogram** cho biết số object/byte theo lớp tại thời điểm chụp, nhưng không tự giải thích **ai đang giữ** chúng. Heap analysis với **path to GC root** và **retained size** giúp truy ra registry/cache/aspect tương ứng.

### 12.2. “Retained size” khác “shallow size”

Một object `TraceAspect` có thể có **shallow size** nhỏ nhưng giữ `byte[]`, request và nhiều object khác. **Retained size** là khái niệm về lượng bộ nhớ có thể trở thành không reachable nếu bỏ một holder khỏi đồ thị (tùy phép phân tích/dominator). Vì thế tìm object có retained size lớn thường hữu ích hơn chỉ nhìn kích thước instance aspect.

### 12.3. Đo theo baseline và chu kỳ lặp

Một bài test tốt có thể:

- Tạo N lần request/bắt đầu và kết thúc scope;
- Kiểm tra số registration sau mỗi vòng phải về **0** nếu không có listener dài hạn;
- Kiểm tra cache không vượt ngân sách được thiết kế;
- Kiểm tra context thread pool không rò sang công việc tiếp theo;
- Chụp/so sánh heap trên nhiều chu kỳ sau khi hệ thống đã khởi động ổn định.

Đừng suy từ một ảnh heap đơn lẻ rằng mọi object lớn đều bị leak. Hãy gắn **kỳ vọng lifetime** với các bằng chứng retention cụ thể.

## 13. Thiết kế ownership rõ ràng để tránh leak

Nguyên tắc thực hành: **cơ chế nào tạo/đăng ký/giữ object thì phải biết điều kiện kết thúc quyền sở hữu của nó**.

| Đối tượng hoặc mối liên kết | Ai thường sở hữu? | Hành vi kết thúc cần cân nhắc |
| --- | --- | --- |
| Listener theo lần gọi | Advice/scope đã đăng ký | `unregister` hoặc `Registration.close()` |
| Context theo thread | Scope mở context | Khôi phục parent hoặc `ThreadLocal.remove()` |
| Cache metadata toàn ứng dụng | Thành phần quản lý cache | Evict theo giới hạn/thời hạn, hủy theo module |
| Proxy của một target | Container/registry tạo proxy | Bỏ tham chiếu khi target không còn được dùng |
| Callback async | Chủ tác vụ và pipeline completion | Kết thúc/cancel theo hợp đồng, tháo callback khi phù hợp |
| Connection/file/lock | Code đã acquire | `close`/`unlock` trên mọi đường thoát hợp lệ |
| Instance aspect per-flow | Cơ chế instantiation/scope | Dỡ binding sau return/throw, xử lý nested/async |

Không phải mọi object phải có `close()`. Một đối tượng Java thuần chỉ cần **không bị giữ mạnh ngoài vòng đời cần thiết**; tài nguyên hữu hạn phải đóng theo hợp đồng riêng.

### 13.1. Đặt state tại mức vòng đời tối thiểu đủ dùng

Nếu advice chỉ cần đo thời gian của **một lần gọi**:

```text
around:
    start = monotonicClock()
    try:
        return proceed()
    finally:
        recordElapsed(monotonicClock() - start)
```

Đây là giả mã. `start` có thể là **biến cục bộ**, không cần field trên singleton aspect. Khi lời gọi kết thúc, biến cục bộ không tự bị giữ tiếp trừ khi nó được capture/escape.

Nếu nhiều join point trong một dynamic flow cần chia sẻ state, per-flow scope có thể phù hợp **khi công nghệ hỗ trợ**, nhưng phải có lifecycle và cleanup đúng.

### 13.2. Tách dữ liệu quan sát khỏi dữ liệu gốc

Thay vì lưu `RequestContext`, đôi khi chỉ cần:

- Tên thao tác đã allowlist;
- Mã tương quan có quy tắc retention rõ;
- Bộ đếm hoặc tổng thời gian;
- Nhãn lỗi mức cao không chứa payload;
- Giá trị đã được rút gọn/ẩn danh theo chính sách.

Lưu các object gốc có thể giữ toàn bộ đồ thị dữ liệu và làm tăng rủi ro lộ thông tin từ heap dump/log.

## 14. Mối liên hệ với pointcut và phạm vi weaving

Một aspect có thể có pointcut rộng áp vào hàng nghìn join point. Điều này tăng **số lần đăng ký hoặc capture object** nếu advice thực hiện thao tác đó mỗi lần.

Mở rộng pointcut mà không thay lifecycle cleanup có thể biến leak nhỏ thành leak đáng kể. Vì vậy cần kiểm tra:

- Những loại join point nào được chọn (method execution/call/field access nếu được hỗ trợ);
- Advice chạy bao nhiêu lần trên một logical request;
- Around advice có `proceed` nhiều lần hay không;
- Có nhiều aspect/ proxy chồng lên nhau không;
- Đường nào bypass cleanup do không qua proxy hoặc lớp chưa được weave;
- Nếu có exception ở before advice, scope cleanup đã được thiết lập chưa.

Đừng cố “sửa leak” chỉ bằng giảm tần suất log mà không xóa **đường giữ tham chiếu mạnh**.

### 14.1. Around advice và retry

```text
Retry(RegisterListener(Target))
RegisterListener(Retry(Target))
```

Hai cấu trúc có thể có số lượt đăng ký khác nhau. Trong cấu trúc đầu, mỗi attempt có thể đăng ký một listener; nếu quên close, số listener giữ lại tăng theo attempts. Trong cấu trúc sau, một scope bên ngoài có thể đăng ký một lần cho toàn yêu cầu nếu hiện thực như vậy.

Thứ tự chỉ là mô hình minh họa; công nghệ có quy tắc precedence riêng. Điều quan trọng là **mỗi lần register thành công phải có teardown đúng số lần và đúng owner**.

### 14.2. Exception và rò tài nguyên

Một advice cấp context, sau đó gọi `proceed()`. Nếu target ném lỗi, cleanup chỉ đặt trong after-returning sẽ không được gọi. Một hành vi kiểu `finally`/after-always phù hợp hơn khi cần giải phóng tài nguyên cho cả return lẫn throw.

Nhưng nếu cấp phát tài nguyên xảy ra **trước khi vào vùng bảo vệ**, lỗi ngay trong cấp phát có thể làm thiếu cleanup. Quy tắc **acquire → enter protected scope → use → cleanup** phải tính cả cấp phát từng phần.

## 15. Concurrent invocation: không lẫn state giữa hai người gọi

Aspect singleton thường được dùng đồng thời. Nếu nó giữ một mảng `Object[] lastArgs` hoặc `Request current` trong field, invocation A và B có thể ghi đè lẫn nhau.

```text
Thread A: before(A) -> aspect.current = A
Thread B: before(B) -> aspect.current = B
Thread A: after()  -> reads B (wrong)
```

Đây là lỗi **race condition/logic** ngay cả khi GC chưa gặp vấn đề. Nếu A và B chứa dữ liệu nhạy cảm, việc lưu state chung còn có thể gây rò rỉ thông tin xuyên người dùng.

Cách thiết kế:

- Dùng biến cục bộ cho dữ liệu theo lần gọi;
- Dùng một context scope với teardown rõ khi cần nhiều join point chia sẻ dữ liệu;
- Dùng cấu trúc concurrent phù hợp cho số liệu **thật sự toàn cục**;
- Giảm object capture và ràng buộc retention;
- Kiểm tra listener/registration có thể close đúng dưới cạnh tranh;
- Không chia sẻ `ArrayList` mutable như EventBus trong ví dụ cho nhiều thread nếu chưa đồng bộ.

## 16. Kiểm thử lifecycle và leak theo tình huống

| Tình huống | Điều cần xác minh |
| --- | --- |
| 1.000 lần gọi bình thường | Không còn 1.000 listener/contexts nếu chỉ cần tạm thời |
| Target ném ngoại lệ | Context và registration được dọn |
| Before advice ném lỗi | Tài nguyên cấp trước lỗi được hoàn tác đúng |
| Nested scope | Inner kết thúc không xóa context outer |
| Thread pool lặp request | Không còn context từ request trước |
| Async task được hủy/timeout | Callback/tài nguyên được xử lý đúng ownership |
| Singleton aspect có field | Không giữ `args`/`target` quá vòng đời |
| Per-target aspect | Không có registry dài hạn giữ các target đã hết hạn |
| Per-flow aspect | Dỡ binding khi root return/throw theo công nghệ |
| Proxy registry | Hủy tham chiếu proxy/target đúng teardown |
| Hot reload module/plugin | Không giữ class loader cũ qua cache/listener |
| Cache nhiều key | Không tăng vượt giới hạn/TTL |
| Weak-key cache | Value không giữ ngược key không cần thiết |
| Retry nhiều attempts | Số register/close cân bằng cho từng attempt |
| Advice chỉ ghi log | Không đổi giá trị/ngoại lệ nghiệp vụ |
| Load cao và concurrency | Không lẫn context, không có race ở cleanup |

### 16.1. Các phép assert hữu ích

Với event bus có API `listenerCount()`, có thể kiểm tra:

```text
before = listenerCount()
openScope(); runOperation(); closeScope()
assert listenerCount() == before
```

Đây là **giả mã**. Với request scope trên thread pool, sau khi task hoàn tất có thể gửi một task kiểm tra trong cùng worker theo một mô hình test phù hợp để bảo đảm context không tồn tại. Khi test memory retention, đối chiếu **path to root** còn mạnh hơn chỉ đếm object.

### 16.2. Khi nào không nên assert object đã được GC?

Nếu test yêu cầu “sau `close()`, `WeakReference.get()` phải thành null trong 50 ms”, test có thể **flaky** vì GC không hứa chạy trong khoảng đó. Thay vào đó, kiểm tra **liên kết đăng ký đã được tháo**, map/scope có kích thước đúng và heap graph không còn đường mạnh sau teardown trong công cụ kiểm tra phù hợp.

Weak references và ReferenceQueue hữu ích cho một số test/phân tích, nhưng cần thiết kế tránh biến thời gian GC thành tiêu chuẩn hành vi cứng.

## 17. Lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách tránh |
| --- | --- | --- |
| Lưu `Object[] args` vào singleton aspect | Giữ payload/request theo GC root sống lâu | Chỉ lưu dữ liệu tối thiểu hoặc scope-local |
| Thêm mọi request vào list để debug | Tăng không giới hạn | Dùng bounded buffer/metrics |
| Listener đăng ký nhưng không unregister | Event bus giữ callback và captured context | Registration handle + teardown |
| Quên `ThreadLocal.remove()` | Thread pool giữ state/nhầm request | `try/finally`, restore parent |
| Inner scope dùng `remove()` vô điều kiện | Mất outer context | Lưu previous và khôi phục |
| Tin weak key luôn tránh leak | Value có thể giữ ngược key | Kiểm tra graph mạnh, ownership |
| Coi reference cycle tự tạo leak | Chẩn đoán sai nguyên nhân | Xem path tới GC root |
| Cache `Class`/`Method` mãi trong global map | Có thể giữ class loader cũ | Cache theo đúng loader/lifecycle và eviction |
| Giữ proxy trong static registry không dọn | Giữ target/interceptors/graph | Gỡ proxy theo lifecycle |
| Capture request trong future lâu sống | Giữ dữ liệu/tài nguyên quá lâu | Dùng context tối thiểu, completion/cancel |
| Dùng `System.gc()` để “sửa leak” | Không xóa strong reference | Loại bỏ đường giữ ngoài ý muốn |
| Tưởng flow kết thúc tức object biến mất | Nhầm deactivation với GC | Phân biệt logical scope với object reachability |
| Dựa vào GC để đóng file/socket | Không bảo đảm thời điểm đóng | `AutoCloseable`/finally đúng scope |
| Chỉ test đường thành công | Leak trên throw/before failure | Test mọi đường thoát |
| Chỉ tăng heap limit | Che triệu chứng không sửa nguồn giữ | Phân tích retained size/path to root |
| Log nguyên object để chẩn đoán leak | Rò dữ liệu và tăng overhead | Rút gọn, làm mờ dữ liệu, giới hạn quyền |

## 18. Bài tập vận dụng có đáp án

### Bài 1 — Singleton giữ request

Một singleton aspect có field `lastRequest` được gán ở mỗi lời gọi. Sau khi lời gọi cuối kết thúc, request ấy có chắc sẵn sàng để GC không?

**Đáp án:** Không. Nếu aspect còn sống và field vẫn trỏ tới request, request còn reachable; đồ thị các đối tượng request giữ cũng có thể còn reachable. Không nhất thiết leak tăng vô hạn, nhưng đó có thể là retention ngoài ý muốn.

### Bài 2 — Listener method reference

`GLOBAL_BUS.register(aspect::onEvent)` được gọi cho mỗi request mà không lưu handle. Vì sao các aspect không biến mất khi biến cục bộ kết thúc?

**Đáp án:** Event bus giữ callback, callback giữ receiver aspect. Đường mạnh từ global bus khiến aspect vẫn reachable. Cần hủy đăng ký theo đúng vòng đời.

### Bài 3 — Thread pool

Một advice `CONTEXT.set(request)` nhưng quên `remove()`. Thread được pool tái sử dụng. Nguy cơ nào xuất hiện?

**Đáp án:** Request cũ có thể bị giữ và request mới có thể đọc nhầm context cũ. Cleanup nên nằm trong `finally` và xử lý restore parent nếu có nested scope.

### Bài 4 — Cycle

Target có field trỏ proxy, proxy trỏ target. Có phải chắc chắn memory leak không?

**Đáp án:** Không. Chu trình tự nó có thể được tracing GC thu gom nếu không còn reachable từ GC roots. Nếu một registry sống lâu vẫn giữ proxy thì cả chu trình có thể tiếp tục được giữ.

### Bài 5 — WeakHashMap

`WeakHashMap<Class<?>, Metadata>` có value `Metadata` giữ lại chính key `Class<?>`. Weak keys bảo đảm class được thu gom không?

**Đáp án:** Không. Map giữ value mạnh; value trỏ ngược key tạo đường strong reference tới class. Cần xem object graph đầy đủ, giới hạn cache và lifecycle class loader.

### Bài 6 — Flow kết thúc

Một aspect per-control-flow được dỡ khỏi activation khi root trả về. Object phải bị GC ngay và tự đóng connection không?

**Đáp án:** Không. Dỡ scope là hành vi logic; GC không bảo đảm thời điểm và tài nguyên ngoài heap cần cleanup theo hợp đồng riêng.

### Bài 7 — Async

Advice tạo callback future có capture cả request. Future pending rất lâu. Điều gì có thể bị giữ?

**Đáp án:** Callback có thể tiếp tục giữ request và các object liên quan chừng nào nó còn reachable qua future/task/queue. Cần xét thời hạn task, việc hủy/completion và dữ liệu tối thiểu cần capture.

### Bài 8 — Debug leak

Heap histogram hiển thị nhiều instance `RequestContext`. Có thể kết luận singleton aspect là nguyên nhân không?

**Đáp án:** Chưa. Histogram chỉ cho số object theo lớp; cần tìm **paths to GC roots** và holder/dominator thực sự. Nguồn giữ có thể là cache, listener, queue, ThreadLocal hoặc một phần nghiệp vụ khác.

### Bài 9 — Bảo đảm cleanup

Advice `register()` rồi gọi target; chỉ unregister trong after-returning. Khi target ném lỗi sẽ ra sao?

**Đáp án:** After-returning không chạy ở nhánh throw, nên có nguy cơ không unregister. Dùng finally/after-always hoặc handle có teardown rõ trên những đường thoát đã được bảo vệ.

### Bài 10 — Retry và registration

Cấu trúc `Retry(Register(Target))` có hai attempts. Nếu mỗi Register tạo listener nhưng không close, số listener có thể tăng bao nhiêu?

**Đáp án:** Trong mô hình retry gọi lại phần đuôi hai lần, có thể thêm hai listener cho một logical request. Cần cleanup cho **mỗi attempt** hoặc tổ chức một scope ngoài đúng trách nhiệm.

## 19. Ghi nhớ

- **Aspect instance và dữ liệu nó giữ có thể có vòng đời rất khác nhau.** Một holder sống lâu có thể giữ object ngắn hạn ngoài ý muốn.
- **GC dựa trên reachability từ roots**; reference cycle không tự là leak, còn static/listener/ThreadLocal/cache/proxy có thể tạo đường mạnh.
- Singleton/per-target/per-flow là **chiến lược lifecycle**, không tự bảo đảm thu hồi object hoặc đóng tài nguyên.
- **Listener phải được hủy đăng ký đúng lúc**; `ThreadLocal` phải remove/restore; cache cần giới hạn và ownership; async callback cần scope rõ.
- **WeakReference/WeakHashMap không thay thế teardown có chủ đích**, và `System.gc()` không sửa được đường giữ mạnh.
- Với Java 17, ưu tiên **biến cục bộ, `try/finally`, `AutoCloseable` và dữ liệu quan sát tối thiểu** cho các scope ngắn.
- Để chứng minh nguồn leak, hãy tìm **path to GC root và retained size** với workload kiểm soát, không chỉ nhìn con số heap tổng.
- Advice chỉ để quan sát phải giữ **kết quả, ngoại lệ và số lần chạy nghiệp vụ**, không tích trữ request/target không cần thiết hoặc log dữ liệu nhạy cảm.
