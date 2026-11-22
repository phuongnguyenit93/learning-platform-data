# 5.6 — StackWalker và việc lấy ngăn xếp có mục đích trong mã chẩn đoán

## 1. Vấn đề: không phải lúc nào cũng cần toàn bộ stack trace

Trong ứng dụng Java, stack trace của exception thường chứa nhiều frame. Thread dump có thể chứa stack của hàng trăm thread. Nhưng trong mã chẩn đoán, nhiều khi chỉ cần biết: **method nào gọi tiện ích này**, **5 frame gần nhất là gì**, **frame đầu tiên thuộc code ứng dụng nằm ở đâu**, hoặc **class nào đã gọi một API của thư viện**.

`java.lang.StackWalker` (xuất hiện từ Java 9, có sẵn trong Java 17+) cho phép duyệt **call stack của thread đang thực thi tại đúng thời điểm gọi**, theo thứ tự từ frame gần nhất đến frame xa hơn, bằng `Stream<StackWalker.StackFrame>`. Chương trình có thể `limit`, `filter`, `map`, `findFirst` hay materialize đúng phần cần dùng.

Bài này hướng tới năm kỹ năng:

1. Giải thích call stack, stack frame và thứ tự `StackWalker` duyệt.
2. Dùng `getInstance`, `walk`, `forEach` và các thuộc tính của `StackFrame`.
3. Lấy có chọn lọc N frame, caller hoặc frame đầu tiên của package ứng dụng.
4. Hiểu `RETAIN_CLASS_REFERENCE`, `SHOW_REFLECT_FRAMES`, `SHOW_HIDDEN_FRAMES` và giới hạn của `getCallerClass()`.
5. Dùng stack có mục đích trong log/diagnostic hook mà không gây overhead lớn hoặc hiểu nhầm stack hiện tại là lịch sử request.

> **Điểm cốt lõi:** StackWalker trả lời câu hỏi **“ở điểm code này, thread hiện tại đã đi qua các method nào?”**. Nó không phải trình profiler CPU, thread dump của toàn JVM hay distributed tracing.

## 2. Stack và frame được quan sát như thế nào?

Giả sử đường gọi đồng bộ:

```text
main()
  └── entry()
        └── service()
              └── diagnose()  <- gọi StackWalker.walk(...)
```

Trong `diagnose()`, thứ tự frame mà `walk` trả về thông thường là:

```text
1. diagnose
2. service
3. entry
4. main
```

**Frame đầu** là method gọi `walk`, không phải luôn là “caller của method đang chạy”. `StackWalker` mặc định ẩn một số frame reflection/implementation; các tuỳ chọn cấu hình có thể làm các frame hiện ra khác nhau. Stack là một **snapshot tại thời điểm đang walk**, không chứa những method đã kết thúc trước đó.

Một `StackFrame` đại diện cho một lần gọi method. Các API đáng biết:

| API | Giá trị trả về | Ý nghĩa và giới hạn |
| --- | --- | --- |
| `getClassName()` | `String` | Binary class name của method ở frame, có thể chứa `$` của nested/lambda class |
| `getMethodName()` | `String` | Tên method ở điểm quan sát |
| `getFileName()` | `String` hoặc `null` | Source file nếu còn thông tin |
| `getLineNumber()` | `int` | Source line, có thể âm khi thiếu debug information |
| `getByteCodeIndex()` | `int` | Vị trí bytecode, có thể âm khi native method |
| `isNativeMethod()` | `boolean` | Method tại frame có phải native không |
| `toStackTraceElement()` | `StackTraceElement` | Cầu nối với kiểu stack trace quen thuộc |
| `getDeclaringClass()` | `Class<?>` | **Yêu cầu** cấu hình `RETAIN_CLASS_REFERENCE` |
| `getMethodType()` | `MethodType` | **Yêu cầu** `RETAIN_CLASS_REFERENCE` trên JDK 17 |
| `getDescriptor()` | `String` | JVM descriptor của method (JDK 10+) |

StackFrame **không cung cấp** giá trị biến local, arguments, nội dung object, thời gian CPU đã tiêu thụ hoặc chủ sở hữu monitor. Một stack có nhiều frame trong code ứng dụng không phải bằng chứng về memory leak hay CPU hotspot.

## 3. API cơ bản: tạo walker, duyệt, dừng sớm

```java
StackWalker walker = StackWalker.getInstance();

String currentMethod = walker.walk(frames ->
    frames.findFirst()
          .map(StackWalker.StackFrame::getMethodName)
          .orElse("<empty>"));
```

Đây là **đoạn minh họa cần đặt trong method/class**, không phải một chương trình chạy độc lập. Khi dùng `getInstance()` mặc định, Java 17 bỏ qua các frame ẩn của reflection/JVM, trả thông tin class name/method name nhưng không giữ `Class<?>` reference.

- `walk(Function<Stream<StackFrame>, T>)` cung cấp một stream **sequential** trong lúc callback đang thực thi. Dùng các terminal operations như `findFirst`, `count`, `collect` hoặc `toList` để trả ra kết quả kiểu `T`.
- `forEach(Consumer<StackFrame>)` duyệt các frame theo thứ tự top-down, tương đương một lần `walk` rồi `stream.forEach`.
- `StackWalker` thread-safe: có thể dùng một `static final StackWalker` ở nhiều thread; **mỗi lần walk vẫn lấy stack của chính thread đã gọi**.
- Có thể tạo `getInstance(Set<Option>, int estimateDepth)`. `estimateDepth` là **gợi ý kích thước buffer**, không giới hạn số frame, và phải lớn hơn 0. Muốn giới hạn, dùng `stream.limit(n)`.
- `walk` có thể dừng sau số frame cần thiết; không phải luôn phải tạo cả mảng stack rồi mới lọc.

### 3.1. Vòng đời đặc biệt của Stream

Một `Stream<StackFrame>` được truyền vào callback **chỉ hợp lệ khi `walk` còn thực thi**. Sau khi `walk` trả về, stream đóng; tái sử dụng nó ném `IllegalStateException`.

**Sai: thoát callback với Stream**

```java
StackWalker walker = StackWalker.getInstance();
java.util.stream.Stream<StackWalker.StackFrame> invalid =
    walker.walk(stream -> stream);

// invalid.findFirst(); // IllegalStateException: stream đã đóng
```

**Đúng: lấy dữ liệu trong callback**

```java
java.util.List<StackTraceElement> snapshot = walker.walk(stream ->
    stream.limit(8)
          .map(StackWalker.StackFrame::toStackTraceElement)
          .toList());
```

`Stream.toList()` đã có từ Java 16, dùng được với Java 17. Có thể giữ danh sách/chuỗi trả về; **không** giữ stream để thao tác sau. API dùng callback vì JVM cần giữ góc nhìn stack ổn định trong quá trình duyệt; implementation có thể deoptimize/reorganize stack. `parallel()` không tạo một cơ chế đọc stack nhiều thread: `walk` thực hiện trên thread hiện tại và parallel execution không có hiệu lực như stream thông thường.

## 4. Lấy một phần stack thay vì toàn bộ

### 4.1. Lấy 5 frame gần nhất

```java
java.util.List<String> topFiveMethods = StackWalker.getInstance().walk(s ->
    s.limit(5)
     .map(f -> f.getClassName() + "#" + f.getMethodName())
     .toList());
```

Đây là đoạn code minh họa. `limit(5)` dừng việc thu thập khi đã đủ năm frame được stream đưa qua, **không** nói JVM chỉ có năm frame. Muốn lấy 1 frame, dùng `findFirst`; muốn lấy frame đầu theo điều kiện, dùng `filter(...).findFirst()`.

### 4.2. Bỏ qua frame của logging helper/framework

Ví dụ muốn tìm frame đầu thuộc package nghiệp vụ `com.acme.orders.`:

```java
String businessFrame = StackWalker.getInstance().walk(s ->
    s.filter(f -> f.getClassName().startsWith("com.acme.orders."))
     .findFirst()
     .map(f -> f.getClassName() + "#" + f.getMethodName())
     .orElse("<no-business-frame>"));
```

Đây là đoạn minh họa, thay tên package theo chương trình thật. Dùng `orElse` hoặc `Optional` khi không có frame phù hợp thay vì tạo exception thứ cấp trong lúc logging.

**Ngữ nghĩa của bộ lọc rất quan trọng:** class trong cùng package chưa chắc là tầng nghiệp vụ; một logger wrapper, adapter hoặc proxy cũng có thể thuộc package ứng dụng. Hãy xác định rõ class nào cần bỏ qua, package nào thực sự là boundary, và xử lý trường hợp caller không tồn tại.

### 4.3. Vì sao skip(n) dễ sai?

Trong chuỗi biết trước `diagnose -> service -> entry -> main`, `skip(1).findFirst()` chọn `service`. Nhưng thêm một wrapper, interceptor, lambda, dynamic proxy, reflection hoặc thay đổi code thì offset có thể khác.

Chỉ dùng `skip(n)` khi call chain là một **contract đã kiểm chứng**, chẳng hạn một method tiện ích nội bộ cố định. Với code thư viện dùng trong nhiều môi trường, lọc theo class/package và explicit context thường bền vững hơn. Đặc biệt, caller class **không** phải bằng chứng phân quyền hay danh tính người dùng.

## 5. Ba Option của StackWalker trên Java 17

| Option | Hành vi | Nên dùng khi |
| --- | --- | --- |
| Mặc định (không Option) | Ẩn reflection/implementation frames, không giữ `Class<?>` | Log tên class/method ngắn |
| `RETAIN_CLASS_REFERENCE` | Giữ `Class<?>` trong frame, cho `getDeclaringClass()`, `getMethodType()` và `getCallerClass()` | Thư viện cần class loader/resource theo caller |
| `SHOW_REFLECT_FRAMES` | Hiển thị các frame reflection vốn được ẩn | Điều tra `Method.invoke` hoặc `Constructor.newInstance` |
| `SHOW_HIDDEN_FRAMES` | Hiển thị tất cả hidden frames, gồm cả reflection và các frame implementation khác | Điều tra sâu chuỗi gọi qua VM/reflection/method handle |

Ví dụ khi thật sự cần `Class<?>`:

```java
StackWalker walker = StackWalker.getInstance(
    StackWalker.Option.RETAIN_CLASS_REFERENCE);

Class<?> topClass = walker.walk(s ->
    s.findFirst()
     .map(StackWalker.StackFrame::getDeclaringClass)
     .orElseThrow());
```

Nếu tạo walker mặc định rồi gọi `getDeclaringClass()`, kết quả là `UnsupportedOperationException`; phải bật option trước.

`SHOW_REFLECT_FRAMES` hiển thị các frame reflection bị ẩn; `SHOW_HIDDEN_FRAMES` rộng hơn và cũng hiển thị reflection frames. Số lượng và chi tiết của hidden frames có thể phụ thuộc JVM implementation; không dựa vào một frame index cố định giữa các JDK/vendor.

**Chú ý với `getCallerClass()`:** phương thức này vẫn lọc reflection frames, method handle frames và hidden frames **bất kể** `SHOW_REFLECT_FRAMES`/`SHOW_HIDDEN_FRAMES` được đặt hay không. Khi muốn xem frame reflection chi tiết, hãy dùng `walk` với option phù hợp.

### 5.1. Quyền dùng Class reference

Javadoc Java 17 quy định khi môi trường có Security Manager, tạo walker với `RETAIN_CLASS_REFERENCE` có thể kiểm tra `RuntimePermission("getStackWalkerWithClassReference")` và ném `SecurityException` nếu bị từ chối. Security Manager đã bị deprecated để loại bỏ; với ứng dụng mới, không xây dựng cơ chế bảo mật dựa vào stack inspection. Chỉ bật giữ `Class<?>` khi nghiệp vụ cần, không bật theo thói quen.

## 6. getCallerClass(): khác với lấy class của frame đầu

`StackWalker.getCallerClass()` trả về **class của caller đã gọi method đang gọi `getCallerClass()`**. Nếu có chuỗi:

```text
StackWalkerDemo.main()
    -> CallerProbe.whoCalled()
        -> CLASS_WALKER.getCallerClass()
            => StackWalkerDemo.class
```

Result là `StackWalkerDemo.class`, **không** phải `CallerProbe.class`. Đây là API thích hợp khi một thư viện cần biết class đã gọi hàm tiện ích để chọn class loader hoặc resource.

Ví dụ:

```java
private static final StackWalker CLASS_WALKER =
    StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

static Class<?> whoCalled() {
    return CLASS_WALKER.getCallerClass();
}
```

Đây là đoạn của một class tiện ích, không phải file độc lập. Dùng trong tình huống có caller thực sự. Nếu walker thiếu `RETAIN_CLASS_REFERENCE`, `getCallerClass()` ném `UnsupportedOperationException`; nếu không có caller (ví dụ gọi trực tiếp ở bottom-most frame `main`), ném `IllegalCallerException`.

Đừng dùng caller class để chứng minh ai đang đăng nhập hay service nào phát sinh request: nó chỉ biểu thị một **đường gọi của thread**, có thể bị ảnh hưởng bởi wrapper, proxy và ranh giới async.

## 7. Demo Java 17+ có thể chạy và stdout chính xác

Mục tiêu demo: duyệt bốn method trong chuỗi đồng bộ, lấy caller method theo frame, và lấy caller class của một tiện ích.

Tạo file **`StackWalkerDemo.java`**:

```java
import java.util.stream.Collectors;

public class StackWalkerDemo {
    private static final StackWalker WALKER = StackWalker.getInstance();

    static void diagnose() {
        String path = WALKER.walk(frames ->
            frames.limit(4)
                  .map(StackWalker.StackFrame::getMethodName)
                  .collect(Collectors.joining(" -> ")));
        System.out.println("path=" + path);

        String caller = WALKER.walk(frames ->
            frames.filter(f -> f.getClassName().equals(StackWalkerDemo.class.getName()))
                  .skip(1)
                  .findFirst()
                  .map(StackWalker.StackFrame::getMethodName)
                  .orElse("unknown"));
        System.out.println("callerMethod=" + caller);
    }

    static void service() { diagnose(); }
    static void entry() { service(); }

    public static void main(String[] args) {
        entry();
        System.out.println("callerClass=" + CallerProbe.whoCalled().getSimpleName());
    }
}

class CallerProbe {
    private static final StackWalker CLASS_WALKER =
        StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

    static Class<?> whoCalled() {
        return CLASS_WALKER.getCallerClass();
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac --release 17 StackWalkerDemo.java
java StackWalkerDemo
```

**Stdout chính xác của chương trình (đã biên dịch và chạy kiểm chứng):**

```text
path=diagnose -> service -> entry -> main
callerMethod=service
callerClass=StackWalkerDemo
```

Giải thích:

1. Frame đầu tiên của `walk` trong `diagnose` là `diagnose`, rồi `service`, `entry`, `main`; `limit(4)` giữ bốn frame.
2. Pipeline thứ hai lọc frame của `StackWalkerDemo`, bỏ frame `diagnose` và lấy frame tiếp theo `service`. Điều này đúng vì **call chain được biết trước**.
3. `CallerProbe.whoCalled()` dùng walker có `RETAIN_CLASS_REFERENCE`, nên `getCallerClass()` trả class của method gọi `whoCalled`, tức `StackWalkerDemo`.

Không có dữ liệu ngẫu nhiên hoặc đường dẫn riêng máy trong stdout; kết quả chỉ phụ thuộc đường gọi được xây rõ trong mã.

## 8. So sánh với Throwable, Thread và thread dump

| Công cụ/API | Câu hỏi trả lời | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| `StackWalker.walk(...)` | Thread hiện tại đang ở chuỗi method nào **tại đây**? | Chọn frame, lọc, dừng sớm, giữ `Class<?>` khi cần | Không có lịch sử, không đọc thread khác |
| `Thread.currentThread().getStackTrace()` | Snapshot stack thread hiện tại? | Có sẵn `StackTraceElement[]`, dễ dùng | Thường tạo array rồi mới lọc; không có các Option của StackWalker |
| `new Throwable().getStackTrace()` | Stack tại lúc tạo Throwable? | Có thể ghi một snapshot riêng | Tạo Throwable để chụp stack có chi phí |
| `exception.getStackTrace()` | Stack đã ghi trong exception lúc exception được tạo/fill? | Truy điểm phát sinh exception | Không phải stack tại điểm bắt exception sau đó |
| `ThreadMXBean` hoặc `jcmd <pid> Thread.print -l` | Nhiều thread đang ở đâu và đợi gì? | Điều tra contention, deadlock, thread pool | Không phải lấy caller tinh gọn trong code |
| JFR, profiler | Trong một khoảng thời gian event/CPU sample/lock/GC như thế nào? | Giải thích xu hướng và hotspots | Không mang ngữ nghĩa caller tại method cụ thể |

**Ví dụ:** một exception được tạo trong `Repository.load()` nhưng được log ở `Controller.handle()`. `exception.getStackTrace()` phản ánh stack đã lưu trước đó; `StackWalker.walk` trong `Controller.handle` phản ánh stack hiện tại. Hai thông tin hỗ trợ nhau nhưng không luôn trùng nhau. Khi ghi lỗi, hãy giữ cause chain của exception; StackWalker chỉ bổ sung một breadcrumb nếu cần.

**Thread khác:** `StackWalker` không có `walk(Thread other)`; để quan sát worker khác cần `ThreadMXBean`, API thread snapshots hoặc thread dump/JFR phù hợp. `StackWalker` không cho trạng thái `BLOCKED`/`WAITING` của toàn JVM hay xác định monitor owner.

## 9. Những tình huống dùng thực tế

### A. Cảnh báo API cũ và ghi caller

Một thư viện muốn cảnh báo chỉ khi một đường gọi deprecated được sử dụng. Thay vì ghi toàn bộ stack, có thể tìm class/method đầu tiên thuộc package ứng dụng:

```java
static String callerLabel() {
    return StackWalker.getInstance().walk(s ->
        s.filter(f -> f.getClassName().startsWith("com.example.app."))
         .findFirst()
         .map(f -> f.getClassName() + "#" + f.getMethodName())
         .orElse("unknown"));
}
```

Đoạn code minh họa cần cấu hình package thực. Nếu package chứa cả tiện ích logging, cần lọc bỏ tiện ích đó hoặc dùng một boundary được định nghĩa rõ. Chỉ log khi điều kiện bất thường hoặc logging level được bật để tránh overhead trên mọi request.

### B. Breadcrumb 6 frame khi phát hiện dữ liệu bất thường

```java
private static final StackWalker SHORT_WALKER = StackWalker.getInstance();

static String shortStack() {
    return SHORT_WALKER.walk(s ->
        s.limit(6)
         .map(f -> f.getClassName() + "#" + f.getMethodName())
         .collect(java.util.stream.Collectors.joining(" <- ")));
}
```

Đoạn này không chạy độc lập. Dấu `<-` chỉ phân tách theo thứ tự top-down, không phải causal timeline. Một breadcrumb ngắn giúp định vị vị trí phát hiện vấn đề; nó **không giải thích** nguyên nhân hệ thống đã chậm bao lâu.

### C. Chọn ClassLoader phục vụ resource

Một thư viện plugin có thể cần class loader của caller:

```java
private static final StackWalker CLASS_WALKER =
    StackWalker.getInstance(StackWalker.Option.RETAIN_CLASS_REFERENCE);

static ClassLoader callingLoader() {
    return CLASS_WALKER.getCallerClass().getClassLoader();
}
```

Đây là code minh họa, yêu cầu contract rằng caller của `callingLoader` chính là lớp sở hữu tài nguyên. `ClassLoader` có thể `null` với bootstrap class; `getCallerClass` cũng có những ngoại lệ đã nêu. Việc chọn class loader phải đi cùng chính sách module/security đúng đắn, không dùng caller class làm authentication principal.

### D. Callback/async: vì sao không thấy HTTP caller?

`CompletableFuture`, executor và event loop có thể chuyển công việc sang thread khác:

```text
request-thread: Controller -> enqueue(task)
                                  |
                                  v
worker-thread:  Executor -> Runnable.run() -> process()
```

StackWalker được gọi trong `process()` chỉ thấy call chain **trên worker-thread**, không tự nối với `Controller` đã enqueue trước đó trên request-thread. Hãy truyền correlation ID/trace context qua ranh giới async và dùng logging/tracing/JFR để tái dựng luồng nghiệp vụ. Không coi stack hiện tại là lịch sử request.

## 10. Hiệu năng và thiết kế diagnostic hook

Stack walking có chi phí CPU và allocation; `StackWalker` giúp dừng sớm nhưng **không** cam kết zero overhead. Chi phí thực tế phụ thuộc số frame duyệt, pipeline, format string, JDK, JIT và tần suất gọi.

Quy tắc áp dụng:

- Ưu tiên `findFirst`/`limit` thay vì luôn `toList` toàn bộ stack.
- Tái sử dụng `static final StackWalker` khi cấu hình không đổi.
- Chỉ bật truy xuất stack trong nhánh bất thường, sampling hoặc log level phù hợp; tránh xử lý stack trên mọi hot-path request.
- Khi chỉ cần String class/method, không bật `RETAIN_CLASS_REFERENCE` hay `SHOW_HIDDEN_FRAMES`.
- Giới hạn số frame và độ dài chuỗi trước khi gửi tới hệ thống log.
- Nếu dùng cho observability quan trọng, đo overhead trong workload thật; `StackWalker` không thay thế metrics hay JFR profiling.
- Tránh tạo exception mới trong chính diagnostic hook: `Optional` và fallback giúp log lỗi mà không che lỗi nghiệp vụ.

### 10.1. Bảo mật và tính đúng đắn

Tên class/method và stack frame có thể làm lộ cấu trúc nội bộ ứng dụng. Không tự động ghi tất cả stack vào log công khai, và không gắn payload hay secret vào breadcrumb. `StackWalker` không cho local values; nếu bổ sung request context, phải redaction theo quy định.

Stack inspection **không phải cơ chế phân quyền**: reflection, proxy, bytecode instrumentation, coroutine-like abstraction và thread boundaries có thể thay đổi frame mà code nhìn thấy. Muốn biết danh tính người dùng hoặc nguồn request phải dùng security context/tracing chuẩn.

## 11. Những lỗi phổ biến

| Sai lầm | Lý do sai | Cách xử lý |
| --- | --- | --- |
| “Frame đầu là caller trực tiếp.” | Frame đầu là method đang gọi `walk`. | Hiểu thứ tự top-down; xác định boundary. |
| “Có thể trả Stream từ walk để đọc sau.” | Stream đóng khi `walk` trả về. | Materialize kết quả trong callback. |
| “estimateDepth=5 giới hạn 5 frame.” | Chỉ là gợi ý về buffer. | Dùng `limit(5)`. |
| “getDeclaringClass luôn dùng được.” | Cần `RETAIN_CLASS_REFERENCE`. | Bật option hoặc dùng tên String. |
| “getCallerClass trả class của method chứa lời gọi.” | Nó trả **caller của method** gọi `getCallerClass`. | Kiểm chứng bằng call chain rõ ràng. |
| “SHOW_HIDDEN_FRAMES làm getCallerClass trả hidden frames.” | `getCallerClass` lọc các frame này bất kể option. | Dùng `walk` khi cần inspect hidden frames. |
| “getLineNumber luôn có dòng hợp lệ.” | Có thể âm khi thiếu debug info. | Fallback class/method; không đoán dòng. |
| “StackWalker nhìn thấy tất cả thread.” | Chỉ current thread. | ThreadMXBean/thread dump cho thread khác. |
| “Stack ở worker chứa controller đã enqueue task.” | Async chuyển thread làm đứt call stack. | Propagate trace ID, tracing/log. |
| “Thread xuất hiện ở method X nên CPU hotspot là X.” | Snapshot không chứa CPU sampling/time. | JFR/CPU profiler. |
| “skip(2) luôn bỏ hai tầng framework.” | Frame count thay đổi theo proxy/reflection/JDK. | Lọc theo contract, test tình huống thật. |
| “Thu stack mọi request không đáng kể.” | Tần suất cao gây overhead. | Gate/sampling/benchmark. |
| “Caller class là danh tính bảo mật.” | Call stack không phải identity đã xác thực. | Dùng auth/security context riêng. |

## 12. Ngoại lệ và các giới hạn API cần nhớ

| Điều kiện | Hành vi Java 17 | Cách tránh |
| --- | --- | --- |
| `getDeclaringClass()` hoặc `getMethodType()` khi thiếu `RETAIN_CLASS_REFERENCE` | `UnsupportedOperationException` | Cấu hình walker phù hợp trước |
| `getCallerClass()` với walker thiếu `RETAIN_CLASS_REFERENCE` | `UnsupportedOperationException` | Dùng option Class reference |
| `getCallerClass()` khi không có caller | `IllegalCallerException` | Dùng API có fallback hoặc định nghĩa contract |
| Tiếp tục dùng `Stream<StackFrame>` sau callback | `IllegalStateException` | Chỉ trả giá trị/list/string từ `walk` |
| `estimateDepth <= 0` | `IllegalArgumentException` | Dùng số dương |
| `getLineNumber() < 0`, `getFileName() == null` | Thiếu source/debug metadata | Dùng class/method và fallback |
| Security Manager từ chối quyền Class reference | Có thể `SecurityException` | Chỉ dùng option khi cần, tôn trọng policy |
| Không tìm được frame sau `filter` | `Optional.empty()` | Xử lý bằng `orElse` hoặc báo thiếu ngữ cảnh |
| Reflection/hidden frame thay đổi giữa runtime | Stack depth/chi tiết có thể khác | Không hard-code vị trí frame trên mọi JDK |

## 13. Checklist đưa vào code chẩn đoán

- [ ] Xác định rõ mục đích lấy stack: caller, frame ứng dụng đầu tiên hay N frame gần nhất.
- [ ] Đặt `walk` ở đúng điểm quan sát, hiểu **chỉ current thread**.
- [ ] Dùng pipeline có điểm dừng, fallback cho kết quả rỗng.
- [ ] Chọn `Option` tối thiểu và hiểu tác động của hidden/reflect frames.
- [ ] Không để `Stream<StackFrame>` thoát khỏi callback; materialize ngay trong `walk`.
- [ ] Khi dùng `getCallerClass()`, xác nhận caller thật sự tồn tại và được hiểu đúng.
- [ ] Tránh lấy stack liên tục trên hot path; đo overhead với tải thực tế.
- [ ] Không dùng stack để suy ra user identity, CPU hotspot hoặc full async causal chain.
- [ ] Ghi log vừa đủ, redaction thông tin nhạy cảm.
- [ ] Kiểm thử code với proxy/reflection/async mà ứng dụng dùng.

## 14. Tài liệu tham khảo chính thức Java 17

- [Oracle — StackWalker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.html): `getInstance`, `walk`, Stream lifetime, `forEach`, `getCallerClass`.
- [Oracle — StackWalker.Option](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.Option.html): `RETAIN_CLASS_REFERENCE`, `SHOW_REFLECT_FRAMES`, `SHOW_HIDDEN_FRAMES`.
- [Oracle — StackWalker.StackFrame](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StackWalker.StackFrame.html): tên class/method, source/line, bytecode, Class reference.
- [Oracle — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `getStackTrace` và các thao tác liên quan.
- [Oracle — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): `getStackTrace` của exception.
- [Oracle — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `Thread.print` để chẩn đoán stack của tiến trình JVM đang chạy từ bên ngoài.

**Ghi nhớ:** `StackWalker` tối ưu việc lấy **thông tin đường gọi có mục đích** tại chính điểm mã đang chạy. Lấy ít frame, có quy tắc lọc và fallback rõ ràng thường hữu ích hơn dump toàn bộ stack; với thread khác, bất đồng bộ, CPU và các vấn đề JVM-wide, cần kết hợp thread dump, logs, metrics và JFR.