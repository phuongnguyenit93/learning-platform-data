# Không giữ tham chiếu đối tượng lâu hơn nhu cầu xử lý

## Mục tiêu bài học

Trong **Aspect-Oriented Programming (AOP)**, advice có thể nhận hoặc truy cập nhiều dữ liệu thuộc một **join point**: đối tượng đang được gọi, target, đối số, kết quả, exception, metadata, thông tin thực thi và đối tượng biểu diễn continuation. Những dữ liệu này rất hữu ích để đo lường, kiểm tra kỹ thuật, ghi trace hoặc kết hợp hành vi. Tuy nhiên, **đọc dữ liệu trong advice không đồng nghĩa được phép lưu giữ toàn bộ đối tượng vô thời hạn**.

Một tham chiếu được giữ lâu hơn nhu cầu có thể khiến những object graph lớn không thể được thu gom rác, làm bộ nhớ tăng dần, giữ thông tin nhạy cảm lâu hơn chính sách cho phép, dẫn đến rò context giữa request hoặc khiến callback dùng dữ liệu đã hết hiệu lực.

**Quy tắc trọng tâm: chỉ giữ tham chiếu trong phạm vi và thời gian thực sự cần để hoàn thành hợp đồng của advice; nếu phải giữ lâu hơn một invocation, hãy chỉ rõ ai sở hữu, điều kiện giải phóng, giới hạn dung lượng và điều gì xảy ra khi công việc lỗi, bị hủy hoặc không bao giờ kết thúc.**

Sau bài học, bạn sẽ:

1. Hiểu mối quan hệ giữa **reachability**, vòng đời object và **memory retention** trong một chương trình có AOP.
2. Xác định những tham chiếu dễ bị giữ ngoài ý muốn: `this`, `target`, `args`, `result`, `Throwable`, join-point context, annotation, `proceed`/closure và dữ liệu gắn với thread.
3. Phân biệt **biến cục bộ của một lần gọi** với **trạng thái chia sẻ của một aspect**, collection toàn cục, cache, `ThreadLocal` và callback bất đồng bộ.
4. Thiết kế **snapshot dữ liệu tối thiểu** thay cho lưu cả object graph, giữ context đúng vòng đời đồng bộ/bất đồng bộ và cleanup bằng `finally`.
5. Hiểu khi nào `WeakReference`, weak-key map, TTL, bounded queue hoặc unregister listener có ích — và vì sao chúng không tự sửa một thiết kế giữ dữ liệu sai.
6. Chạy ví dụ Java 17 với dynamic proxy minh họa cách giữ dữ liệu tạm thời, xóa `ThreadLocal`, quan sát async completion mà không giữ lại payload và kiểm tra đường bypass proxy.
7. Lập ma trận kiểm thử để phát hiện giữ tham chiếu quá lâu, rò context, tiêu thụ bộ nhớ không giới hạn và lỗi do concurrency.

Phạm vi là **AOP nói chung**, không mặc định mọi công cụ hỗ trợ cùng loại join point hoặc cùng dạng join-point context. Ví dụ Java chỉ minh họa một kỹ thuật interception cụ thể.

## 1. Ngữ cảnh của advice chứa những gì?

Một join point có thể là một **lần method execution**, **method call**, constructor execution, field access hoặc sự kiện khác, tùy **join-point model** của công cụ. Pointcut chọn các điểm phù hợp; advice được chạy ở những điểm đó; weaving hoặc proxy quyết định cách hành vi được chèn vào chương trình.

Một advice có thể cần một phần của các dữ liệu sau:

| Dữ liệu | Ví dụ | Rủi ro khi giữ quá lâu |
| --- | --- | --- |
| **Target** | Đối tượng dịch vụ được gọi. | Target có thể tham chiếu tới cache, dependency, tài nguyên, cấu trúc domain lớn. |
| **Đối tượng `this` hoặc caller context** | Receiver hay đối tượng liên quan đến điểm gọi. | Có thể giữ cả graph do receiver/caller nắm giữ. |
| **Arguments** | Mảng đối số chứa request/payload. | Một argument có thể giữ buffer lớn, stream, thông tin người dùng hoặc document graph. |
| **Result** | Entity, DTO, stream, future hoặc iterator. | Có thể giữ bản ghi lớn, buffer, tài nguyên chưa đóng hoặc một tác vụ còn pending. |
| **Throwable** | Exception từ target/advice. | Exception có stack trace, `cause`, `suppressed`, custom fields và dữ liệu nhạy cảm. |
| **Method/signature/annotation** | Metadata dùng chọn pointcut. | Có thể liên quan class/classloader; cache không kiểm soát dễ giữ metadata lớp cũ sau reload. |
| **Join-point / proceeding context** | Object cho phép lấy args hoặc gọi `proceed`. | Thường gián tiếp nắm target, args hoặc continuation có phạm vi hẹp. |
| **Trace/request context** | Correlation ID, principal, tenant. | Giữ nguyên security/request object có thể kéo dài thời gian sống của dữ liệu riêng tư. |

**Chỉ vì một API trả về một object không có nghĩa cần lưu nó.** Trong nhiều advice chỉ ghi số liệu, dữ liệu thật sự cần giữ có thể là một `operationName`, một `requestId`, một loại lỗi và một giá trị `durationNanos` — không phải toàn bộ `args`, `target` và `Throwable`.

### 1.1. `this` và `target` không luôn đồng nghĩa

Một số mô hình AOP phân biệt đối tượng hiện tại tại nơi gọi (`this`) với đối tượng nhận thao tác (`target`), nhất là khi có proxy hoặc join point ở phía caller. Không nên suy ra chúng là cùng một instance trong mọi công cụ. Cả hai đều có thể tạo **strong reference** đến một object graph lớn.

Nếu chỉ cần nhãn kiểu hoặc danh tính ổn định, hãy chọn dữ liệu đại diện thích hợp thay vì lưu nguyên receiver. Cũng không nên tự động dùng `System.identityHashCode` như một ID toàn cục duy nhất hoặc ổn định xuyên quá trình; nó không mang hợp đồng đó.

### 1.2. Đối số không phải lúc nào cũng là dữ liệu nhẹ

Một `Object[] args` nhìn có vẻ chỉ là một mảng nhỏ. Nhưng các phần tử có thể là request body, file upload, byte array lớn, entity liên kết với session hoặc một đồ thị object. Nếu giữ **tham chiếu tới mảng**, các phần tử của nó có thể tiếp tục được giữ.

Tạo một bản sao mảng bằng `args.clone()` chỉ sao chép **container**, không deep-copy những object bên trong; bản sao vẫn giữ strong reference đến các phần tử. Muốn giảm retention, phải chọn những **giá trị nhỏ, độc lập và thật sự cần thiết**.

### 1.3. Metadata có vòng đời riêng

Trong Java, các instance `Class`, `Method` hoặc annotation được dùng trong matcher có quan hệ tới kiểu và classloader. Với ứng dụng có cơ chế nạp/reload module, một cache toàn cục giữ `Class`/`Method` của lớp cũ có thể góp phần ngăn classloader được thu hồi. Công cụ AOP có thể có cache metadata được quản lý vòng đời riêng, nhưng không vì thế mà một cache custom trong advice có quyền sống vô hạn.

Không phải mọi `Method` giữ lại đều là memory leak: ví dụ một registry dùng suốt vòng đời ứng dụng có thể có lý do giữ metadata. Vấn đề là **vòng đời của cache có phù hợp vòng đời của class/module và có cơ chế giải phóng không**.

## 2. Vì sao strong reference có thể kéo dài sự tồn tại của đối tượng?

Trong Java và nhiều runtime có garbage collector, object chỉ có thể được xem xét thu gom khi **không còn reachable** từ các gốc được GC xét qua những đường tham chiếu liên quan. Một biến `static`, một thread còn sống, field của object lâu sống, queue, callback hoặc collection có thể giữ một **đường tham chiếu mạnh** dẫn tới object.

Sơ đồ minh họa:

```text
GC root
   |
   v
long-lived singleton aspect
   |
   v
List<Object[]> storedArguments
   |
   v
Object[] args
   |
   v
RequestPayload
   |
   +--> byte[large]
   +--> customer / document graph
   +--> nested collections
```

Mặc dù phương thức nghiệp vụ đã kết thúc, object `RequestPayload` vẫn có thể reachable thông qua `storedArguments`. GC **không thể quyết định tự xóa dữ liệu còn được chương trình giữ có chủ đích**, kể cả khi lập trình viên đã quên collection đó tồn tại.

### 2.1. Memory leak không nhất thiết là object “không bao giờ được giải phóng”

Trong môi trường managed runtime, memory leak thường biểu hiện dưới dạng **unintended retention**: object không còn cần về mặt chức năng nhưng vẫn reachable. Nếu cache được giải phóng lúc tắt ứng dụng, ta vẫn có thể coi việc tăng bộ nhớ suốt thời gian chạy dài là một vấn đề nghiêm trọng.

Một số biểu hiện:

- Heap usage sau các đợt GC vẫn tăng theo số request.
- Số object thuộc nhóm request/context/exception tồn tại lâu bất thường.
- Latency GC, pressure allocation hoặc thời gian pause tăng.
- Worker pool tái sử dụng thread nhưng context cũ vẫn hiện trong invocation mới.
- Shutdown/redeploy không thu hồi được classloader hoặc tài nguyên đi kèm.

**Không kết luận memory leak chỉ từ một snapshot heap lớn.** Cần xem retained paths, chu kỳ sống, workload và xu hướng sau các lượt xử lý ổn định. Cache được cố ý giữ có thể dùng bộ nhớ lớn nhưng vẫn bounded và đúng hợp đồng.

### 2.2. Kích thước reference nhỏ không nói được lượng bộ nhớ bị giữ

Một field chỉ chứa một tham chiếu tới một request có thể kéo theo graph lớn: request → session → danh sách document → byte arrays. Nếu lời gọi advice lưu `Throwable`, throwable có thể giữ cause, suppressed exceptions, custom fields hoặc stack trace; việc giữ chỉ một exception lâu dài vẫn có thể làm rò dữ liệu và giữ tài nguyên gián tiếp.

Vì vậy **retained size** đáng quan tâm hơn kích thước nông (*shallow size*) của chính reference.

## 3. Vòng đời đúng của dữ liệu trong advice

Hãy phân loại dữ liệu thành ba nhóm.

### 3.1. Dữ liệu chỉ cần trong invocation đồng bộ

Ví dụ:

- Thời điểm bắt đầu.
- Reference `target` và `args` để gọi tiếp.
- Tạm đọc annotation hoặc chữ ký method.
- Throwable để ghi loại lỗi và ném lại.
- Context tạm dùng khi method chưa return.

Giải pháp ưu tiên: **biến cục bộ trong method advice hoặc handler**, hạn chế đưa vào field dùng chung. Nếu cần đặt trong `ThreadLocal`, bảo đảm cleanup theo phạm vi thread và có quy tắc hỗ trợ nested invocation.

Không cần “chủ động set null mọi local variable” khi chương trình đã thoát scope hợp lý. Hạn chế reachability bằng thiết kế scope thường rõ hơn micro-optimization.

### 3.2. Dữ liệu cần cho công việc bất đồng bộ

Ví dụ:

- Trace ID, operation name, thời điểm bắt đầu để tính latency end-to-end.
- Một token tương quan hoặc deadline.
- Một snapshot metadata đã lọc dùng trong completion callback.

Không nên vì muốn đo lúc hoàn tất mà capture **toàn bộ join-point context**, `args`, request, target hoặc một `ProceedingJoinPoint`-like object trong lambda. Callback có thể sống đến khi future hoàn tất; nếu future không hoàn tất, nó có thể giữ dữ liệu rất lâu.

Thay vào đó, lấy những giá trị **độc lập, nhỏ và cần thiết**, ví dụ:

```text
String requestId
String operation
long startedNanos
```

Không phải mọi `String` đều luôn nhỏ hoặc an toàn: request ID cần chiều dài giới hạn, còn exception message hoặc body có thể chứa dữ liệu lớn/nhạy cảm. “Snapshot tối thiểu” còn bao gồm **giới hạn cardinality và chính sách riêng tư**.

### 3.3. Dữ liệu được chủ động giữ nhiều invocation

Ví dụ:

- Bộ đếm metric dạng số.
- Cấu hình pointcut.
- Cache metadata có giới hạn.
- Listener được đăng ký theo vòng đời module.
- Registry phục vụ debug có TTL và dung lượng tối đa.

Mỗi cấu trúc giữ dài hạn cần câu trả lời cụ thể:

1. Ai sở hữu?
2. Tối đa bao nhiêu phần tử hoặc bytes?
3. Khi nào loại bỏ?
4. Khi module/ứng dụng dừng, ai cleanup?
5. Nếu việc ghi hoặc hủy bị lỗi, trạng thái còn lại là gì?
6. Có chứa reference tới request/user/target không?
7. Concurrency và reentrancy có làm retention tăng bất ngờ không?

Nếu không trả lời được, đừng lưu object vào state sống dài của aspect.

## 4. Các mẫu giữ tham chiếu quá lâu thường gặp

### 4.1. Lưu mọi bộ `args` vào field/static list

Ví dụ **phản ví dụ**, không phải chương trình độc lập:

```java
static final java.util.List<Object[]> HISTORY =
        new java.util.ArrayList<>();

void recordInvocation(Object[] args) {
    HISTORY.add(args); // giữ mạnh mọi phần tử trong mảng
}
```

Với N lần gọi, collection có thể tăng cùng N. Mảng chứa request payload hoặc object có graph lớn sẽ tiếp tục được giữ. Dùng synchronized list chỉ giải quyết một phần vấn đề đồng thời, **không giải quyết vấn đề vòng đời**.

Hướng khắc phục: chỉ lưu **tổng số lần gọi**, các trường tóm tắt an toàn hoặc một mẫu lịch sử có **giới hạn + TTL**. Nếu thực sự cần bản ghi để điều tra, nên dùng hệ thống lưu log/audit có retention và kiểm soát truy cập rõ, không nhét toàn bộ object runtime vào singleton aspect.

### 4.2. Giữ `target` trong một cache theo từng request

```text
Map<requestId, targetObject>
```

Nếu các key không bao giờ bị xóa, target được giữ; target có thể giữ kết nối, buffer hoặc các dependency khác. Nếu reference tới target phải được duy trì suốt vòng đời proxy, đó có thể là **quan hệ sở hữu hợp lý**. Rủi ro xuất hiện khi một map riêng giữ bản sao reference theo mọi request **sau khi request không còn cần**.

### 4.3. Giữ `Throwable` để “debug về sau”

```text
List<Throwable> recentErrors
```

Cấu trúc này giữ exception object, stack trace, cause chain và custom fields. Ngay cả khi chỉ giữ “100 lỗi gần nhất”, mỗi Throwable có thể tham chiếu graph lớn; cần xem **dung lượng thực** và độ nhạy cảm. Một snapshot như `errorType`, `errorCode`, một ID/timestamp thường an toàn hơn.

Một số trường hợp điều tra cần retention tạm thời; hãy giới hạn thời gian, số lượng, redaction và cleanup khi hoàn tất phiên chẩn đoán.

### 4.4. Lưu cả result sau khi caller đã nhận

Advice chỉ cần tính `result.size()` hoặc gắn outcome label thì không nên giữ cả result DTO, stream hoặc collection trong một list dài hạn. Với dữ liệu lazy (iterator/stream/publisher), việc giữ wrapper còn có thể giữ tài nguyên chưa đóng hoặc kéo dài subscription.

### 4.5. Lambda/callback capture dữ liệu lớn

Ví dụ:

```java
Payload payload = ...; // đoạn minh họa
stage.whenComplete((value, error) -> {
    log(payload);       // closure giữ strong reference tới payload
});
```

Trong khi stage pending, callback có thể phải tồn tại và giữ `payload`. Nếu `payload` chứa byte array lớn, thời gian giữ ít nhất có thể kéo dài tới completion, trừ khi implementation có cơ chế giải phóng khác.

Cách thiết kế tốt hơn khi chỉ cần ID:

```java
String requestId = payload.id();
stage.whenComplete((value, error) -> {
    recordResult(requestId, error);
});
```

Đây là **mã minh họa**, không độc lập: các loại/hàm cần được định nghĩa ở nơi khác. Không capture `payload` trong callback đã đổi; bảo đảm `requestId` là dữ liệu ngắn, được phép dùng và không gián tiếp giữ payload. Nếu cần nguyên payload để thực hiện **nghiệp vụ**, không được xóa reference quá sớm làm logic sai; cần chốt vòng đời theo hợp đồng của task.

### 4.6. Registration mà không unregister

Một aspect có thể đăng ký listener vào event bus, scheduler hoặc registry. Nếu nguồn phát sự kiện sống dài, nó giữ callback, callback có thể giữ aspect, target hoặc state request. Sau khi module/dịch vụ hết hiệu lực, chưa unregister listener là nguồn retention phổ biến.

Cần xác định **subscription handle** hoặc cơ chế tháo đăng ký và cleanup khi scope kết thúc, kể cả sau exception/cancellation. “Dùng weak listener” không luôn đủ nếu nơi khác vẫn còn strong reference hoặc listener phải hoạt động tới khi unsubscribe rõ.

## 5. `ThreadLocal`: tiện cho advice đồng bộ nhưng cần cleanup

`ThreadLocal` cho phép một thread lưu trạng thái gắn với thread ấy. Một số advice dùng nó để mang trace context, thời điểm bắt đầu, dữ liệu đệ quy hoặc một giá trị tạm.

Rủi ro: thread trong pool thường sống **lâu hơn nhiều request**. Nếu `ThreadLocal` vẫn giữ `CallContext` sau khi lời gọi xong, context cũ có thể tiếp tục reachable theo thread và gây rò thông tin hoặc memory retention.

### 5.1. Mẫu đơn giản: đặt, dùng, xóa trong `finally`

```java
CallContext ctx = new CallContext(requestId);
CURRENT.set(ctx);
try {
    return proceed();
} finally {
    CURRENT.remove();
}
```

Đây là **đoạn khái niệm**, giả định `CURRENT`, `CallContext` và `proceed` đã có. Với một scope không lồng, `remove()` trong `finally` bảo đảm cleanup cả khi return và throw. Việc `remove()` phải xảy ra **trên đúng thread đã đặt giá trị**; gọi `remove()` từ một worker khác không xóa giá trị thread-local của thread ban đầu.

### 5.2. Nested advice/đệ quy: không được xóa bừa context của caller ngoài

Nếu cùng một `ThreadLocal` được sử dụng ở các scope lồng nhau:

```text
outer advice: set context A
    inner advice: set context B
    inner finally: remove()
outer resumes: context A đã biến mất
```

Vì vậy **mẫu `set` rồi `remove` đơn giản chỉ đủ cho scope không cần restore giá trị trước đó**.

Mẫu phục hồi hợp đồng lồng nhau:

```java
CallContext previous = CURRENT.get();
CURRENT.set(current);
try {
    return proceed();
} finally {
    if (previous == null) {
        CURRENT.remove();
    } else {
        CURRENT.set(previous);
    }
}
```

Tuy nhiên, ngay cả việc restore cũng chỉ đúng nếu scope được điều khiển nhất quán và không có luồng nào dùng chung state vượt quá hợp đồng. Với nhiều loại context, có thể dùng scope/stack có lifecycle rõ thay vì tự viết logic tùy tiện trong mọi advice.

### 5.3. Thread-local và async là hai phạm vi khác nhau

Một method trả `CompletionStage` có thể kết thúc ngay; advice `finally` trên caller thread nên cleanup scope của invocation tại thời điểm return. Nếu completion callback chạy trên thread khác, nó **không tự được kế thừa** giá trị `ThreadLocal` hiện có của caller.

Sai lầm phổ biến:

- Giữ context trong `ThreadLocal` của caller cho tới lúc stage hoàn tất — có thể rò giữa request vì thread được tái sử dụng.
- Gọi `CURRENT.remove()` trong completion callback ở thread worker và nghĩ rằng đã dọn `CURRENT` của caller — đó có thể là hai thread khác nhau.
- Capture cả `CallContext` chứa `args`/target chỉ để lấy correlation ID khi completion — kéo dài reference không cần thiết.

Nếu cần context xuyên async boundary, nên **chuyển snapshot tối thiểu theo task** và khôi phục bằng scope riêng ở thread chạy callback, rồi dọn/restore trên **chính thread đó**.

### 5.4. ThreadLocal key có thể yếu nhưng value vẫn được giữ

Trong triển khai Java thông dụng, entry của `ThreadLocalMap` dùng weak reference cho key, nhưng value vẫn là strong reference trong entry cho đến khi entry được loại bỏ/dọn thích hợp. Do đó **không thể xem weak key là lý do để bỏ qua `remove()`**. Với thread sống lâu, một value có thể bị giữ quá thời gian bạn cần.

Đừng xây chính sách bộ nhớ dựa vào “sớm muộn GC sẽ xử lý” khi chương trình tự biết chính xác lúc scope kết thúc.

## 6. Singleton aspect và trạng thái dùng chung

Một số công cụ có thể tạo instance aspect chia sẻ giữa nhiều join point hoặc nhiều thread; các cơ chế khác có lifecycle theo target, đối tượng hoặc một context cụ thể. **Không mặc định mọi aspect đều singleton**, nhưng phải phân tích lifecycle thực tế.

Nếu một aspect lâu sống có field:

```java
Object lastArgument;
Throwable lastError;
Object lastResult;
```

thì mỗi field có thể giữ object của lời gọi gần nhất **cho tới khi bị ghi đè hoặc aspect bị thu hồi**. Dù chỉ một reference, nếu object đó là payload lớn, vấn đề vẫn đáng kể. Với nhiều thread, field mutable còn có nguy cơ race và trộn dữ liệu giữa các request.

### 6.1. Trạng thái theo invocation là mặc định an toàn hơn

Thay vì:

```text
aspect.startTime = now()
...
duration = now() - aspect.startTime
```

nên dùng:

```text
startTime = now()        // local trong một invocation
...
duration = now() - startTime
```

Đây vừa là bài toán **thread safety** vừa là **scope/retention**. Một biến local không tự đảm bảo object được GC ngay, nhưng nó không bị ghim vào state chia sẻ của aspect sau khi scope kết thúc.

### 6.2. Không nhầm giữ lâu có chủ đích với rò rỉ

Một proxy thường cần giữ reference đến target trong thời gian proxy được dùng. Một registry cần giữ cấu hình matcher trong vòng đời module. Đó có thể là **ownership đúng**, không phải rò bộ nhớ.

Cần đánh giá: reference còn có **mục đích hoạt động** không? Có mất cơ hội release khi parent hết vòng đời không? Có bị nhân theo từng request mà không giới hạn không?

Mục tiêu bài này là **loại bỏ retention không có chủ đích**, không phải cực đoan xóa mọi reference trong advice.

## 7. Async callback: giữ ID nhỏ, không giữ toàn bộ join-point context

Với method đồng bộ:

```text
before -> proceed -> after/finally -> hết invocation
```

Với method bất đồng bộ:

```text
before -> proceed -> trả CompletionStage -> finally của invocation
                                      |
                                      +--> completion ở thời điểm sau
```

Nếu muốn đo task completion, callback có thể cần sống tới khi stage hoàn tất. Vì thế **một mức retention tạm thời là cần thiết**, nhưng phải được thiết kế:

- Giữ `startedNanos`, `operationName`, `traceId` dạng giá trị nhỏ thay vì cả `args`.
- Không capture `Proceed`, `target` hoặc `joinPoint` nếu callback chỉ cần số đo cuối.
- Không lưu `Throwable` vào collection vô hạn sau completion; chuyển thành error classification an toàn.
- Khi task bị cancel/timeout hoặc không complete, cần deadline, chính sách dọn dẹp và kiểm soát số pending callbacks.
- Nếu handler đăng ký callback trả về một dependent stage, phân biệt stage **gốc** và stage **phụ thuộc**; lỗi callback có thể tạo lỗi ở stage phụ thuộc, cần kênh xử lý riêng.
- Không coi completion callback luôn chạy cùng thread đã vào advice.
- Nếu result là một stream/publisher lazy, phải xét vòng đời subscription/onNext/onError/onComplete/cancel, không chỉ return của method tạo pipeline.

### 7.1. Không dùng callback chỉ để trì hoãn giải phóng của request

Ví dụ anti-pattern:

```text
onCompletion(() -> {
    logFullRequest(request);
    releaseRequestLater();
})
```

Nếu stage có nguy cơ pending lâu vô hạn, callback giữ request rất lâu. Trường hợp cần log hậu kỳ nên tạo **snapshot đã kiểm soát thông tin và kích thước ngay lúc invocation**, rồi callback giữ snapshot thay vì request object.

### 7.2. Một lambda có thể capture `this` ngoài ý muốn

Khi lambda gọi một instance method hoặc dùng field của aspect, nó có thể giữ `this`; `this` có thể liên kết tới target, cache, registry hoặc dữ liệu khác. Java compiler có cách capture biến mà lambda thực sự dùng, nhưng kết quả vẫn nên được kiểm tra bằng thiết kế: **đừng đưa nguyên `this` vào callback tồn tại lâu nếu có thể thay bằng các scalar hoặc service được sở hữu hợp lý**.

Không nhất thiết mọi capture của `this` là sai: nếu callback phải dùng một service hoạt động suốt ứng dụng, đó có thể là dependency hợp lệ. Phân biệt “callback giữ service dùng chung” và “callback giữ request-scoped object đã kết thúc”.

## 8. Ví dụ Java 17 hoàn chỉnh: cleanup dữ liệu lời gọi và quan sát completion

Chương trình sau dùng **JDK dynamic proxy theo interface**. Mục đích là minh họa việc advice tạm giữ `Payload` trong `ThreadLocal` **chỉ trong thời gian invocation**, sau đó xóa bằng `finally`, đồng thời đăng ký callback chỉ giữ `id` nhỏ để ghi kết quả async.

**Đây là ví dụ một cơ chế triển khai theo tư duy AOP**, không phải ngôn ngữ pointcut tổng quát. Nó không chặn mọi lần method execution hay mọi đường gọi trực tiếp vào target.

Tạo file **`AdviceReferenceLifetimeDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;

public class AdviceReferenceLifetimeDemo {
    static final class Payload {
        final String id;
        final byte[] bytes;

        Payload(String id, byte[] bytes) {
            this.id = id;
            this.bytes = bytes;
        }
    }

    static final class CallContext {
        final String id;
        final Payload payload;

        CallContext(String id, Payload payload) {
            this.id = id;
            this.payload = payload;
        }
    }

    static final ThreadLocal<CallContext> ACTIVE = new ThreadLocal<>();

    interface Worker {
        CompletionStage<String> work(Payload payload);
    }

    static final class TaskWorker implements Worker {
        private CompletableFuture<String> pending;

        @Override
        public CompletionStage<String> work(Payload payload) {
            if ("BAD".equals(payload.id)) {
                throw new IllegalArgumentException("bad id");
            }
            System.out.println("TARGET scheduled " + payload.id);
            pending = new CompletableFuture<>();
            return pending;
        }

        void complete(String value) {
            CompletableFuture<String> ready = pending;
            pending = null;
            ready.complete(value);
        }
    }

    static Worker instrument(Worker target) {
        return (Worker) Proxy.newProxyInstance(
                Worker.class.getClassLoader(),
                new Class<?>[] { Worker.class },
                (proxy, method, arguments) -> {
                    Payload payload = (Payload) arguments[0];
                    String id = payload.id;
                    ACTIVE.set(new CallContext(id, payload));

                    try {
                        System.out.println("ADVICE before " + id);
                        Object outcome;
                        try {
                            outcome = method.invoke(target, arguments);
                        } catch (InvocationTargetException wrapped) {
                            throw wrapped.getCause();
                        }

                        if (outcome instanceof CompletionStage<?> stage) {
                            // Callback chỉ cần id; không capture payload/context.
                            stage.whenComplete((value, failure) -> {
                                if (failure == null) {
                                    System.out.println("ASYNC complete "
                                            + id + "=" + value);
                                } else {
                                    System.out.println("ASYNC failure "
                                            + id + " "
                                            + failure.getClass().getSimpleName());
                                }
                            });
                        }

                        System.out.println("ADVICE return-handle " + id);
                        return outcome;
                    } catch (Throwable original) {
                        System.out.println("ADVICE synchronous-error "
                                + id + " "
                                + original.getClass().getSimpleName());
                        throw original;
                    } finally {
                        ACTIVE.remove();
                        System.out.println("ADVICE cleared " + id);
                    }
                }
        );
    }

    public static void main(String[] args) {
        TaskWorker target = new TaskWorker();
        Worker proxy = instrument(target);

        CompletionStage<String> task =
                proxy.work(new Payload("A", new byte[1024]));
        System.out.println("CALLER context-clear " + (ACTIVE.get() == null));
        target.complete("OK");
        System.out.println("CALLER result "
                + task.toCompletableFuture().join());

        try {
            proxy.work(new Payload("BAD", new byte[2048]));
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }
        System.out.println("CALLER context-clear " + (ACTIVE.get() == null));

        CompletionStage<String> direct =
                target.work(new Payload("DIRECT", new byte[512]));
        target.complete("DIRECT-OK");
        System.out.println("CALLER direct "
                + direct.toCompletableFuture().join());
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac AdviceReferenceLifetimeDemo.java
java AdviceReferenceLifetimeDemo
```

**Stdout kỳ vọng:**

```text
ADVICE before A
TARGET scheduled A
ADVICE return-handle A
ADVICE cleared A
CALLER context-clear true
ASYNC complete A=OK
CALLER result OK
ADVICE before BAD
ADVICE synchronous-error BAD IllegalArgumentException
ADVICE cleared BAD
CALLER caught bad id
CALLER context-clear true
TARGET scheduled DIRECT
CALLER direct DIRECT-OK
```

### 8.1. Đường A: dùng payload trong invocation, chỉ giữ ID trong callback

1. Caller gọi `proxy.work` với `Payload("A", byte[1024])`.
2. Handler tạo `CallContext` chứa một reference đến payload, lưu trong `ACTIVE` để phục vụ **invocation hiện tại**.
3. Target in `TARGET scheduled A`, tạo future pending và trả handle.
4. Handler đăng ký `whenComplete` chỉ dùng local `String id`, không truy cập `payload`, `arguments`, `CallContext` hay `ACTIVE` trong callback.
5. Handler in `ADVICE return-handle A`, sau đó `finally` xóa thread-local và in `ADVICE cleared A`.
6. Caller kiểm tra `ACTIVE.get() == null`, in `true` vì scope của invocation trên thread này đã được dọn.
7. `target.complete("OK")` làm stage hoàn tất. Callback in `ASYNC complete A=OK`; caller `join` đọc kết quả.

**Giới hạn suy luận:** Kiểm tra `ACTIVE.get() == null` chứng minh thread-local của **thread đang chạy demo** được dọn sau invocation; nó **không chứng minh payload đã được GC**. Payload vẫn có thể reachable từ những chỗ khác và GC không chạy theo lịch do code mong muốn. Quan trọng là callback không cần giữ payload để tạo dòng log.

### 8.2. Đường BAD: cleanup phải chạy khi ném lỗi

`proxy.work("BAD")` khiến target ném `IllegalArgumentException` đồng bộ. `Method.invoke` bọc lỗi target thành `InvocationTargetException`, handler gỡ cause và ném lại. Nhánh `catch` in `ADVICE synchronous-error BAD IllegalArgumentException`. `finally` vẫn chạy, xóa `ACTIVE` và in `ADVICE cleared BAD`.

Nếu chỉ đặt `ACTIVE.remove()` sau lời gọi target mà không dùng `finally`, nhánh lỗi có thể làm context còn lại trong thread-local. Với thread pool, điều này đặc biệt nguy hiểm khi thread được dùng lại bởi request khác.

### 8.3. Đường DIRECT: chỉ proxy invocation mới đi qua handler

`target.work("DIRECT")` gọi thẳng target, không có dòng ADVICE. Target vẫn lên lịch future và hoàn tất được. Đây là giới hạn **đường gọi qua proxy**, không phải quy tắc mọi công cụ AOP đều có. Không thể dùng sự vắng mặt của log từ proxy để khẳng định không có tác vụ chạy.

### 8.4. `TaskWorker.pending` cũng là một reference — tại sao hợp lệ trong demo?

Target giữ future trong field `pending` **để có cách hoàn tất chính task đó**. `complete` lấy reference rồi đặt field về `null` trước khi gọi `ready.complete(value)`. Đây là ví dụ retention có **mục đích và điểm giải phóng rõ ràng**.

Nhưng thiết kế đó chỉ hỗ trợ **một job pending tại một thời điểm**; nếu `work` được gọi đồng thời, reference có thể bị ghi đè. Trong ứng dụng thật cần quản lý nhiều job bằng registry/queue có ràng buộc dung lượng, đồng bộ hóa, timeout/cancel và cleanup cho mọi terminal path. Không sao chép nguyên demo vào xử lý concurrent production.

### 8.5. Vì sao callback chỉ giữ ID?

Nếu callback ghi `payload.bytes.length` hoặc `context.payload`, nó sẽ giữ reference tới payload cho tới khi callback không còn cần. Để ghi completion status của task, chỉ cần ID nhỏ và loại outcome. Dữ liệu `byte[1024]` không phục vụ công việc quan sát completion, nên không nên để callback giữ nó.

Lưu ý nếu ID chứa dữ liệu nhạy cảm hoặc quá dài, cần sanitize/giới hạn từ trước. Và vì `whenComplete` trả một **dependent stage**, ví dụ bỏ qua dependent stage này chỉ để tập trung vào retention; trong production cần quan tâm lỗi của chính callback instrumentation.

### 8.6. Không suy từ ví dụ thành “cứ xóa mọi context trong finally”

Demo không có nested invocation trên cùng thread, nên `ACTIVE.remove()` là đúng. Nếu một advice bên trong dùng cùng `ThreadLocal` và ghi đè context cũ, cần **restore giá trị trước đó** hoặc dùng scope stack có lifecycle rõ như mục 5.2. Nếu async worker cần thông tin context, phải truyền snapshot vào worker và quản lý scope ở worker, không giữ thread-local caller mở tới completion.

## 9. Snapshot dữ liệu tối thiểu: thu cái cần dùng, không thu cả object graph

Giả sử mục tiêu của advice là ghi số liệu:

```text
operation="save"
durationMs=12
outcome="failure"
errorType="IOException"
traceId="a1b2"
```

Không có lý do tự động giữ toàn bộ đối tượng `Customer`, `HttpRequest`, byte buffer hay `Throwable` lâu hơn invocation chỉ để tạo những trường đó.

### 9.1. Thiết kế bản ghi nhỏ, ổn định và an toàn

Các thuộc tính tốt:

- **Immutable:** tránh giữ tham chiếu tới object mutable bị thay đổi sau đó.
- **Scalar hoặc dữ liệu đã rút gọn:** operation name, enum status, timestamp, count, bounded identifier.
- **Không chứa bí mật:** không lưu token, mật khẩu, thông tin nhận dạng không được phép, toàn bộ request/response.
- **Giới hạn độ dài/cardinality:** không lấy raw exception message hoặc path người dùng làm nhãn metric không giới hạn.
- **Có vòng đời:** được đẩy tới sink hoặc bị loại khi queue đầy theo chính sách rõ.
- **Không phụ thuộc target còn sống:** record có thể tồn tại mà không cần giữ object nghiệp vụ.

Trong Java, một `record` có các field `String`, `long`, enum có thể là cấu trúc tiện cho snapshot, nhưng phải bảo đảm các `String`/field thật sự nhỏ và không giữ object không cần thiết.

### 9.2. Không deep-copy toàn bộ object chỉ vì sợ strong references

Một bản sao sâu toàn bộ request có thể tiêu tốn **nhiều bộ nhớ hơn**, tạo chi phí CPU và giữ thông tin nhạy cảm lâu hơn. Cách tốt thường là **chiếu dữ liệu (projection)** xuống tập trường cần thiết chứ không copy toàn bộ.

Nếu thực sự cần dữ liệu cho tác vụ async, cần đảm bảo dữ liệu vẫn còn hiệu lực tới khi tác vụ sử dụng xong. “Giảm giữ tham chiếu” không có nghĩa được làm hỏng correctness bằng cách bỏ reference khi target còn đang cần.

## 10. Các cấu trúc giữ lâu có chủ đích: cache, metrics, queue, listener

### 10.1. Cache phải có chính sách

Một cache key/value có thể giữ reference gián tiếp lớn. Chính sách tối thiểu:

- **Dung lượng tối đa** (số phần tử và khi cần ước lượng byte).
- **Eviction** dựa trên nhu cầu (LRU/TinyLFU hoặc chính sách khác).
- **TTL hoặc invalidation** phù hợp tính đúng đắn dữ liệu.
- **Bounded concurrency** khi nhiều request miss cùng lúc.
- **Cleanup** khi module ngừng hoạt động.
- **Định nghĩa ownership**: cache giữ dữ liệu đã snapshot hay object nghiệp vụ sống lâu?

TTL không tự hạn chế số phần tử tăng trong khoảng thời gian trước khi hết hạn; ngược lại eviction không giải quyết dữ liệu đã lỗi thời. Có thể cần cả hai.

### 10.2. Metrics nên giữ số liệu, không giữ invocation object

Một `LongAdder` đếm lỗi có thể phù hợp hơn collection lưu mọi Throwable. Histogram thời gian xử lý có thể phù hợp hơn danh sách mọi `startTime/finishTime` nếu bài toán chỉ cần phân phối.

Cảnh giác **cardinality**: gắn user ID hoặc message tự do làm metric label có thể tạo hàng triệu time series, một dạng retention/áp lực tài nguyên ở hệ thống đo lường dù advice không trực tiếp giữ object Java.

### 10.3. Queue quan sát phải bounded

Nếu advice đưa snapshot vào queue cho worker ghi log mà producer nhanh hơn consumer, queue không giới hạn sẽ giữ record tăng mãi. Cần chính sách backpressure, bounded buffer, drop/sampling hoặc xử lý lỗi phù hợp tầm quan trọng của telemetry.

Nếu chính sách là audit bắt buộc, “drop khi đầy” có thể không hợp lệ. Khi đó phải xây hợp đồng hệ thống rõ về giao dịch, lưu bền và phản hồi thất bại, không che bằng một collection in-memory.

### 10.4. Listener/subscription phải có scope

Một listener gắn vào global event bus có thể giữ object làm callback, bao gồm target hoặc request graph. Cần unregister khi scope kết thúc; nếu task dài hạn, có thể cần handle/cancellation token và deadline.

Với publisher/stream, phải theo dõi cả **subscription completion, error và cancellation**, không chỉ return của method tạo stream.

## 11. Weak references: công cụ bổ sung, không phải câu thần chú chống leak

Java có `WeakReference`, `SoftReference`, `PhantomReference` và reference queue với những hợp đồng khác nhau. Trong bài toán “không giữ một object sống chỉ vì cache quan sát nó”, weak reference có thể hữu ích, nhưng phải hiểu rõ giới hạn.

### 11.1. `WeakReference` không kéo dài lifetime như strong reference

Nếu chỉ còn weak reference tới một object, GC có thể thu hồi object đó. Nhưng:

- Không có bảo đảm GC sẽ chạy **ngay lập tức** tại thời điểm bạn muốn.
- `ref.get()` có thể trả object hoặc `null`, nên code phải chấp nhận mất đối tượng.
- Nếu còn strong reference ở nơi khác, weak reference không giúp object được thu hồi.
- Weak reference không thay thế việc **unregister listener**, đóng stream hoặc giải phóng tài nguyên ngoại vi đúng vòng đời.

Đừng viết test đòi `System.gc()` phải dọn object trong một khoảng mili giây cố định: GC không có hợp đồng như vậy.

### 11.2. Weak-key map vẫn có thể giữ key gián tiếp

`WeakHashMap<K,V>` sử dụng weak keys, nhưng **value được giữ mạnh** khi entry còn tồn tại. Nếu value lại tham chiếu mạnh về key, key có thể tiếp tục reachable qua map → value → key, làm mất lợi ích mong đợi.

Ví dụ ý tưởng nguy hiểm:

```text
WeakHashMap<Key, Value>
Value.key --> Key  // strong reference quay về key
```

Cần kiểm tra object graph thực, không chỉ thấy chữ “Weak” trong tên cấu trúc mà tin rằng hết memory leak.

### 11.3. `SoftReference` không phải cache eviction policy đầy đủ

Soft references phụ thuộc quyết định GC và áp lực bộ nhớ, không cho độ trễ eviction/TTL/budget rõ ràng. Với hệ thống production, một bounded cache có chính sách cụ thể thường dễ kiểm soát hơn cache dựa hoàn toàn vào hy vọng GC.

### 11.4. Reference queue và cleanup

Nếu dùng weak/phantom references cần theo dõi object bị thu hồi, một `ReferenceQueue` có thể hỗ trợ phát hiện các reference được enqueue. Tuy nhiên cleanup tài nguyên ngoại vi quan trọng nên có **owner và close/unregister rõ**, không dựa vào thời điểm GC không xác định để thực hiện hành vi nghiệp vụ đúng hạn.

## 12. Async, timeout và công việc không bao giờ kết thúc

Một callback được đăng ký trên future có thể giữ snapshot hoặc closure đến khi future hoàn tất. Nếu stage **không bao giờ complete**, callback có thể còn gắn với stage lâu bất thường.

Cần thiết kế:

1. **Deadline/timeout** cho logical task nếu nghiệp vụ cho phép.
2. **Cancellation propagation** xuống tác vụ thật khi abstraction hỗ trợ; chỉ cancel handle không luôn dừng I/O nền.
3. **Giới hạn pending tasks** và số callback được đăng ký.
4. **Cleanup ở terminal event**: success, failure hoặc cancellation.
5. **Giám sát orphaned tasks** và backlog để phát hiện tăng retention.
6. **Không capture request graph** nếu chỉ cần tên operation/ID để ghi outcome.
7. **Phân biệt timeout signal với tác vụ thật đã dừng**; tài nguyên có thể cần cleanup bổ sung.

Nếu task cần giữ payload tới lúc thực thi xong, hãy gắn ownership payload vào **task có vòng đời rõ**, không mượn một biến `ThreadLocal` của invocation rồi để nó tồn tại vô hạn.

### 12.1. Phân biệt dữ liệu do advice giữ và dữ liệu do task cần

Một task bất đồng bộ thực sự cần `Payload` để xử lý có thể giữ reference tới payload tới khi kết thúc; đây là retention **phục vụ nghiệp vụ**. Advice đo completion chỉ cần request ID không nên tự giữ **thêm** một reference tới payload nếu điều đó không cần thiết. Sau khi task hoàn tất, cả task owner và advice callback đều cần có cơ chế giải phóng phù hợp.

### 12.2. `CompletionStage` gốc và dependent stage

`whenComplete` trả một stage phụ thuộc. Nếu callback của advice ném exception:

- **Stage phụ thuộc** có thể bị lỗi theo hợp đồng của CompletionStage.
- Nếu advice **trả dependent stage** cho caller, lỗi instrumentation có thể đổi outcome caller quan sát.
- Nếu advice **trả stage gốc** và bỏ dependent stage, outcome caller có thể không đổi nhưng lỗi callback không được báo rõ ở nơi khác.

Để giữ hợp đồng của target, phải chọn stage trả ra và chính sách xử lý lỗi callback có chủ đích; cả hai quyết định đều liên quan đến vòng đời object và sự tồn tại của callback.

## 13. Nhận diện memory retention trong hệ thống có aspect

### 13.1. Quan sát xu hướng theo workload

Một phép thử có ý nghĩa có thể:

1. Khởi động cùng cấu hình và làm nóng ứng dụng.
2. Thực thi N request có payload cỡ xác định.
3. Chờ các task hoàn tất và cleanup theo hợp đồng.
4. Lặp chu kỳ nhiều lần ở tốc độ tương tự.
5. Theo dõi số context còn active, queue depth, cache entries, pending futures và heap/GC theo thời gian.
6. Chụp heap dump hoặc dùng profiler được phép để xem **retained path** nếu dữ liệu tăng bất thường.
7. So sánh khi bật/tắt instrumentation theo một thiết kế kiểm soát được.

Không kết luận chỉ vì một lần đo `Runtime.freeMemory()` giảm: runtime có thể giữ heap đã cấp phát để tái sử dụng và GC hoạt động theo thời điểm không xác định.

### 13.2. Tìm GC roots và retained paths

Nếu profiler chỉ ra:

```text
Thread worker
  -> ThreadLocalMap entry
  -> CallContext
  -> Payload
  -> large byte[]
```

thì việc thiếu cleanup của thread-local là giả thuyết có cơ sở. Nếu đường là:

```text
static aspect
  -> List<Throwable>
  -> CustomError
  -> originalRequest
```

thì lỗi đến từ collection sống dài. Nếu đường là:

```text
pending CompletableFuture
  -> completion callback
  -> captured Payload
```

cần hỏi payload có thực sự cần trong callback và task có deadline không.

**Điều cần sửa là đường sở hữu và vòng đời, không phải chỉ gọi `System.gc()`.**

### 13.3. Đừng xem `WeakReference.get() == null` là phép kiểm tra duy nhất

Dùng weak reference có thể hỗ trợ thí nghiệm trong điều kiện thích hợp, nhưng GC không xác định thời điểm. Một bộ test ổn định hơn có thể kiểm tra **số phần tử registry bằng 0 sau completion**, **ThreadLocal được xóa**, **listener đã unregister**, **queue không vượt cap** và **tham chiếu không được capture trong callback** qua review/profiler. Các kiểm chứng này đánh giá thiết kế deterministic hơn là buộc GC chạy.

## 14. Tính đúng đắn, bảo mật và concurrency

### 14.1. Giảm retention không được phá correctness

Nếu around advice cần retry hoặc tiếp tục sau I/O, có thể phải giữ đối số cho tới khi continuation thực hiện; giải phóng quá sớm có thể làm mất dữ liệu cần cho nghiệp vụ. Mục tiêu không phải “không giữ bất cứ gì” mà là “không giữ **lâu hơn thời gian cần thiết**”.

Ví dụ, một input stream đang được dùng phải sống đến khi đọc xong, nhưng sau khi đóng và hết scope thì không nên bị lưu trong một map debug vô hạn.

### 14.2. Dữ liệu nhạy cảm trong logs và metrics

Giữ reference quá lâu cũng là vấn đề riêng tư. Một Throwable có thể chứa input lỗi; argument có thể là token hoặc file y tế; target có thể giữ thông tin người dùng. Khi telemetry cần ghi một điều gì đó, dùng allowlist field an toàn, redaction và thời hạn lưu.

Không xây correlation ID bằng cách nối toàn bộ email, số điện thoại hoặc request body. Một identifier ngắn và opaque thường phù hợp hơn. Với metrics, tránh nhãn cardinality cao gây tăng lưu trữ.

### 14.3. Concurrency, race và aspect state

Nếu aspect dùng `HashMap` không đồng bộ để lưu mọi context đang chạy, nhiều thread có thể gây race, dữ liệu mất hoặc cấu trúc bị hỏng. Nếu chuyển sang `ConcurrentHashMap`, race cấu trúc có thể giảm nhưng không tự tạo **eviction**, timeout và ownership. Chính sách vòng đời vẫn phải rõ.

### 14.4. Reentrancy và lời gọi lồng nhau

Một advice có thể kích hoạt method cũng khớp pointcut (ví dụ logger gọi một method đã được instrument). Nếu cùng `ThreadLocal` được ghi đè bởi lời gọi trong, cần stack/restore như mục 5.2. Không đơn giản `remove()` rồi coi giá trị của tầng ngoài đã được khôi phục.

### 14.5. Proxy, weaving và đối tượng nào được giữ

JDK dynamic proxy có handler giữ reference đến target vì đó là quan hệ cần thiết để proxy làm việc. Class proxy hoặc code weaving có biểu diễn khác. Một advice có thể nhận join-point object sống ngắn; một engine có thể tự quản lý metadata caching; tất cả phải được xem theo hợp đồng và implementation cụ thể.

**Đừng suy rằng cứ có AOP là có memory leak.** Memory retention xuất hiện khi application/advice/tool giữ reference không phù hợp với vòng đời dự kiến. Cần tách trách nhiệm và kiểm chứng thay vì đổ mọi vấn đề bộ nhớ cho khái niệm AOP.

## 15. Checklist review một advice

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Advice cần dữ liệu gì? | Liệt kê từng field thực sự dùng trong before, after, error và async callback. |
| Dữ liệu thuộc scope nào? | Một invocation, một task, một request, một thread, một module hay toàn ứng dụng? |
| Có lưu `args`, `result`, `target` hay `Throwable` không? | Nếu có, chứng minh thời hạn giữ và chủ sở hữu. |
| `ThreadLocal` có cleanup đúng thread không? | Kiểm tra success/throw/nested invocation và propagation async. |
| Có callback capture cả context không? | Đổi sang immutable snapshot tối thiểu khi có thể. |
| Có cache/list/registry tăng theo request không? | Đặt giới hạn, TTL, eviction, metrics cho số phần tử. |
| Listener/subscription có tháo đăng ký không? | Đảm bảo cleanup ở complete/error/cancel/shutdown. |
| Future có thể pending mãi không? | Có deadline, giám sát pending và giới hạn tài nguyên không? |
| Weak reference có bị value giữ ngược key không? | Xem retained paths, đừng tin chỉ vào tên API. |
| Context có dữ liệu nhạy cảm không? | Dùng allowlist, redaction, giới hạn thời gian lưu. |
| Có nhiều thread/nested call không? | Kiểm tra thread safety, restore context và callback lifecycle. |
| Có chứng minh được retention hợp lý không? | Dùng integration tests, counters, profiler/heap dump khi cần. |

## 16. Ca kiểm thử gợi ý

### Ca 1 — Cleanup sau success

Gọi method qua advice, target return bình thường. Sau khi advice kết thúc, assert context tạm của thread **đã được xóa hoặc restore** đúng như scope được thiết kế.

### Ca 2 — Cleanup sau exception

Target ném lỗi, advice quan sát và ném lại. Assert lỗi gốc tới caller và context tạm không còn ở thread đó. Đây là ca bắt buộc để kiểm chứng `finally`.

### Ca 3 — Nested advice

Outer đặt context A, inner đặt context B rồi kết thúc. Assert outer tiếp tục thấy context A. Với scope stack/restore, inner không được xóa context của outer.

### Ca 4 — Async pending

Target trả future chưa hoàn tất. Ngay sau return, assert thread-local của caller đã cleanup; callback chỉ giữ snapshot cần thiết. Đừng assert payload đã được GC.

### Ca 5 — Async terminal

Hoàn tất future thành công, lỗi hoặc cancel. Assert pending count/registry/subscription được giải phóng theo chính sách, không tăng qua nhiều vòng test.

### Ca 6 — Never-completing task

Giữ một stage pending vượt deadline được thiết kế. Assert cơ chế timeout/cancellation/quota không để giữ vô hạn toàn bộ request graph. Tránh kỳ vọng cancellation tự dừng mọi I/O nếu abstraction không hứa.

### Ca 7 — High-volume workload

Thực thi nhiều request nối tiếp và song song với payload cỡ lớn. Assert queue/cache size trong giới hạn, metric không tạo nhãn vô hạn, và retained paths không cho thấy collection static giữ mọi argument.

### Ca 8 — Proxy bypass

Gọi target trực tiếp, xác nhận handler proxy không ghi trạng thái. Dữ liệu do target giữ theo hợp đồng nghiệp vụ vẫn có thể tồn tại; cần phân biệt retention của target với retention do advice tạo ra.

### Ca 9 — Listener registration

Tạo scope, đăng ký listener có callback, kết thúc scope rồi unregister. Assert registry không còn listener; đừng dùng GC như cơ chế duy nhất kiểm tra unsubscribe.

## 17. Các ngộ nhận thường gặp

**“Garbage collector sẽ tự sửa mọi memory leak.”** Sai. GC không giải phóng object vẫn reachable qua strong references sống dài.

**“Mảng `Object[]` nhỏ thì lưu `args` không sao.”** Sai. Các phần tử có thể dẫn tới graph lớn.

**“Sao chép `args.clone()` giải quyết retention.”** Sai. Đó là shallow copy và vẫn giữ các phần tử.

**“Chỉ dùng một field `lastError` nên không thể leak.”** Sai. Một Throwable có thể giữ nhiều dữ liệu và sống suốt đời aspect.

**“`ThreadLocal` tách theo thread nên không cần `remove()`.”** Sai. Thread pool sống lâu, value có thể tồn tại xuyên request.

**“`remove()` trong callback async sẽ dọn context của thread gọi method.”** Không nếu callback ở thread khác. Thread-local thuộc thread cụ thể.

**“`finally { remove(); }` luôn đúng kể cả nested scope.”** Chưa đủ; có thể cần restore previous context.

**“Callback chỉ cần request ID thì cứ capture nguyên request cũng được.”** Không nên. Capture nguyên request kéo dài tuổi thọ object graph ngoài nhu cầu quan sát.

**“Dùng `WeakHashMap` thì key chắc chắn được giải phóng.”** Không nếu value hoặc một nơi khác còn strong reference về key.

**“Bộ nhớ tăng trong một lần chạy nghĩa là chắc chắn leak.”** Không. Cần xem workload, GC, heap policy và retained paths.

**“Cache không giới hạn là giải pháp tăng hiệu năng.”** Không. Retention vô hạn có thể gây áp lực heap, GC và rủi ro dữ liệu.

**“Không nên giữ bất kỳ reference nào trong advice.”** Quá cực đoan. Reference cần thiết trong invocation, task hoặc lifetime của proxy là hợp lệ; vấn đề là thiếu giới hạn và điểm kết thúc.

## 18. Tự đánh giá

**1.** Một singleton aspect lưu mọi `args` trong `ArrayList<Object[]>`. Vì sao memory có thể tăng dù target kết thúc?

**Đáp án:** List giữ mảng đối số, mảng giữ các phần tử, các phần tử có thể giữ object graph; target kết thúc không cắt đường strong reference từ singleton.

**2.** `args.clone()` có giải quyết khi một argument là `byte[10_000_000]` không?

**Đáp án:** Không. Mảng `Object[]` mới vẫn tham chiếu cùng byte array.

**3.** Advice chỉ cần một ID để ghi completion của future. Nên capture request hay ID?

**Đáp án:** Chỉ snapshot ID đã được giới hạn/sanitize nếu đủ. Tránh capture request object và context lớn không cần thiết.

**4.** Caller thread dùng `ThreadLocal`, callback chạy ở worker thread và gọi `remove()`. Caller có chắc sạch context không?

**Đáp án:** Không. `remove` tác động lên thread đang chạy callback, không phải tự động lên thread caller.

**5.** Với nested advice, inner xóa thread-local trong `finally` có đủ không?

**Đáp án:** Nếu outer cũng có context trong cùng slot, phải restore giá trị trước đó hoặc dùng scope stack hợp lệ; xóa đơn thuần có thể làm mất outer context.

**6.** `WeakHashMap` có key yếu nhưng value giữ reference tới key. Key có chắc được thu hồi không?

**Đáp án:** Không; đường map → value → key có thể duy trì strong reachability của key.

**7.** Vì sao `System.gc()` không phải assertion ổn định cho memory leak test?

**Đáp án:** GC không có lịch chạy và kết quả thu gom xác định theo thời điểm, kể cả khi đã được gợi ý gọi GC.

**8.** Proxy giữ reference tới target suốt thời gian proxy còn dùng. Điều đó có luôn là leak không?

**Đáp án:** Không. Nếu target là thành phần mà proxy cần điều phối, đó là quan hệ sở hữu hợp lệ; phải giải phóng khi proxy/module hết nhu cầu.

**9.** Future pending mãi và callback capture request lớn. Rủi ro là gì?

**Đáp án:** Khi stage/callback còn reachable, request graph có thể bị giữ lâu, ngoài ra số pending stages có thể tăng không giới hạn nếu thiếu timeout/quota/cleanup.

**10.** Một aspect ghi metric bằng cách lưu message của mọi Throwable làm nhãn. Vấn đề nào xuất hiện?

**Đáp án:** Message có thể chứa dữ liệu nhạy cảm, độ dài bất thường và cardinality cao; cần phân loại lỗi ổn định, redaction và giới hạn.

## Kết luận

Trong AOP, advice thường nhận những dữ liệu rất giàu ngữ cảnh nhưng **không sở hữu chúng vô thời hạn**. Dữ liệu của một join point nên được sử dụng trong **scope ngắn nhất phù hợp**; đối với async, chỉ giữ những snapshot nhỏ cần thiết đến completion; đối với state dài hạn, phải có **ownership, giới hạn, chính sách giải phóng và kiểm thử**. Đặc biệt chú ý các đường giữ mạnh qua `args`, target, result, Throwable, singleton aspect, `ThreadLocal`, callback, cache và listener. GC không thể sửa một thiết kế vẫn cố giữ object reachable. Cách áp dụng an toàn là dùng local scope hoặc cleanup/restore trong `finally`, không capture toàn bộ context cho tác vụ hậu kỳ, giữ đúng dữ liệu cho nghiệp vụ và chứng minh vòng đời qua test/profiler.
