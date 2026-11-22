# `Method.invoke` không tự chờ `Future` hoặc `CompletionStage` trả về

## 1. Bản chất của `Method.invoke` khi phương thức trả kết quả bất đồng bộ

`java.lang.reflect.Method.invoke(Object receiver, Object... args)` **gọi phương thức đích và chờ chính lời gọi phương thức đó trả về hoặc ném lỗi**. Nếu phương thức được gọi trả về `Future<T>`, `CompletionStage<T>` hoặc `CompletableFuture<T>`, giá trị trả về của `invoke` là **đối tượng Future/Stage** (dưới kiểu `Object`). `invoke` không tự gọi `get()`, `join()`, chờ completion, hay tự tách giá trị `T` bên trong.

Hãy phân biệt ba mốc:

1. **Invocation:** Reflection thực hiện kiểm tra quyền truy cập, nhận tham số, chạy thân phương thức Java.
2. **Return:** thân phương thức trả về một reference tới `Future`/`CompletionStage`. Lời gọi `Method.invoke` kết thúc ngay khi có giá trị đó, dù tác vụ đại diện bởi nó chưa xong.
3. **Completion:** tác vụ hoàn tất thành công, thất bại hoặc bị hủy sau đó; người gọi quyết định quan sát hoặc đợi kết quả bằng API async thích hợp.

Ví dụ minh họa đặt bên trong một method có `service` và `Service` hợp lệ:

```java
Method m = Service.class.getMethod("loadAsync");
Object returned = m.invoke(service); // Có thể trả về ngay một CompletionStage chưa xong
CompletionStage<?> stage = (CompletionStage<?>) returned;
Object value = stage.toCompletableFuture().join(); // Chủ động chờ nếu chưa hoàn tất
```

**Lưu ý quan trọng:** Reflection không tự tạo thread và không làm phương thức đồng bộ trở thành async. Nếu **chính thân phương thức đích** thực hiện `Thread.sleep`, truy vấn I/O chặn, hoặc `future.get()` **trước khi return**, thread thực thi `invoke` vẫn phải chờ thân phương thức đó kết thúc. Ngược lại, phương thức có thể trả một `CompletableFuture.completedFuture(value)` đã hoàn tất sẵn, nên đọc kết quả về sau không cần đợi. Việc đối tượng async đã hoàn tất hay chưa phụ thuộc vào logic của phương thức đích, không phụ thuộc Reflection.

Giá trị `Method.invoke` luôn có kiểu khai báo `Object`: Java sẽ boxing kết quả primitive; phương thức `void` cho kết quả `null`. Nếu phương thức chỉ khởi động tác vụ nền rồi return `void`, Reflection cũng chỉ nhận `null` và **không có Future nào để chờ** thông qua giá trị trả về.

## 2. Ba kiểu async thường gặp

| Kiểu | Đặc điểm | Nếu cần chờ | Nếu cần nối xử lý |
| --- | --- | --- | --- |
| `Future<T>` | Tập trung vào kết quả, `isDone`, `get`, `cancel` | `future.get()` hoặc `get(timeout, unit)` | Giao diện `Future` không định nghĩa callback composition |
| `CompletionStage<T>` | Biểu diễn giai đoạn và quan hệ phụ thuộc giữa các giai đoạn | `stage.toCompletableFuture().get()` hoặc `join()` | `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally`... |
| `CompletableFuture<T>` | Triển khai **cả** `Future<T>` và `CompletionStage<T>` | `get` hoặc `join` | Có đầy đủ các API composition |

**`Future` và `CompletionStage` không kế thừa lẫn nhau.** Ví dụ, kết quả của `ExecutorService.submit(...)` chỉ được bảo đảm có giao diện `Future`, không nhất thiết là `CompletionStage`. Một triển khai `CompletionStage` tùy chỉnh cũng không nhất thiết triển khai `Future`. `CompletableFuture` là trường hợp hỗ trợ cả hai; không nên ép một `Future<?>` bất kỳ thành `CompletableFuture<?>`.

`Future.isDone() == true` **không có nghĩa tác vụ thành công**: nó cũng trả `true` khi bị hủy hoặc hoàn tất thất bại. Phải quan sát kết quả, lỗi hoặc trạng thái hủy theo API cụ thể.

## 3. Ví dụ đầy đủ Java 17+: `invoke` không chờ completion

Lưu toàn bộ chương trình sau trong tệp **`ReflectAsyncDemo.java`**, không khai báo `package`.

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Future;

public class ReflectAsyncDemo {
    private static final CompletableFuture<String> pendingFuture =
            new CompletableFuture<>();
    private static final CompletableFuture<String> pendingStage =
            new CompletableFuture<>();

    public static Future<String> findLater() {
        return pendingFuture;
    }

    public static CompletionStage<String> loadLater() {
        return pendingStage;
    }

    public static CompletionStage<String> failedLater() {
        return CompletableFuture.failedFuture(
                new IllegalStateException("async-failure"));
    }

    public static CompletionStage<String> failBeforeReturn() {
        throw new IllegalArgumentException("sync-failure");
    }

    public static void main(String[] args) throws Exception {
        Method find = ReflectAsyncDemo.class.getMethod("findLater");
        Method load = ReflectAsyncDemo.class.getMethod("loadLater");

        Object rawFuture = find.invoke(null);
        Object rawStage = load.invoke(null);

        System.out.println("Future result: " + (rawFuture instanceof Future<?>));
        System.out.println("Stage result: "
                + (rawStage instanceof CompletionStage<?>));

        Future<?> future = (Future<?>) rawFuture;
        CompletionStage<?> stage = (CompletionStage<?>) rawStage;
        System.out.println("Future done before completion: " + future.isDone());
        System.out.println("Stage done before completion: "
                + stage.toCompletableFuture().isDone());

        pendingFuture.complete("future-ok");
        pendingStage.complete("stage-ok");

        System.out.println("Future get: " + future.get());
        System.out.println("Stage join: " + stage.toCompletableFuture().join());

        CompletionStage<?> failed = (CompletionStage<?>)
                ReflectAsyncDemo.class.getMethod("failedLater").invoke(null);
        System.out.println("Invoke returned failed stage: " + (failed != null));
        try {
            failed.toCompletableFuture().join();
        } catch (CompletionException ex) {
            System.out.println("Async cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            ReflectAsyncDemo.class.getMethod("failBeforeReturn").invoke(null);
        } catch (InvocationTargetException ex) {
            System.out.println("Sync cause: "
                    + ex.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac ReflectAsyncDemo.java
java ReflectAsyncDemo
```

Kết quả xác định:

```text
Future result: true
Stage result: true
Future done before completion: false
Stage done before completion: false
Future get: future-ok
Stage join: stage-ok
Invoke returned failed stage: true
Async cause: IllegalStateException
Sync cause: IllegalArgumentException
```

**Tại sao kết quả này chứng minh `invoke` không tự chờ?** Hai `CompletableFuture` được khởi tạo ở trạng thái **chưa hoàn tất**, và **chỉ có lệnh `complete(...)` ở phần dưới mới hoàn tất chúng**. Sau khi chạy `find.invoke(null)` và `load.invoke(null)`, chương trình vẫn đi tiếp tới `isDone()` và nhận cả hai là `false`. Nếu `Method.invoke` tự chờ completion, chương trình sẽ không thể đi tới những lệnh `complete` nằm ở phía sau trong cùng thread.

Hai lời gọi `get`/`join` diễn ra **sau** `complete`, vì vậy chúng đọc kết quả ngay. Nếu chuyển `join` lên trước `complete` cùng thread, chương trình có thể tự chờ vô hạn.

`find.invoke(null)` và `load.invoke(null)` dùng receiver `null` vì method là `static`. Đối với method instance, phải truyền instance của declaring class hoặc kiểu tương thích.

Chương trình cũng cố ý tách hai tình huống lỗi: method `failedLater` **trả về stage thành công xét về lời gọi trực tiếp**, nhưng stage đã hoàn tất ngoại lệ; method `failBeforeReturn` ném lỗi **trước khi trả giá trị**. Hai tình huống có đường chuyển lỗi khác nhau, được trình bày ở phần tiếp theo.

## 4. `InvocationTargetException` khác lỗi completion

### 4.1. Ngoại lệ ngay lúc gọi method qua reflection

Nếu code **bên trong phương thức đích** ném lỗi trước khi return, `Method.invoke` bọc ngoại lệ đó trong `java.lang.reflect.InvocationTargetException`. Đây là cơ chế của Reflection, không phụ thuộc phương thức khai báo trả `Future` hay không.

```java
// Mảnh minh họa trong method, với method/receiver đã được định nghĩa.
try {
    Object result = method.invoke(receiver);
} catch (InvocationTargetException ex) {
    Throwable original = ex.getCause();
    System.err.println("Method itself failed: " + original);
}
```

Ví dụ, nếu thân method tự gọi `future.get()` và nhận `ExecutionException` **trước khi return**, `Method.invoke` cũng có thể bao bọc `ExecutionException` trong `InvocationTargetException` vì đó là ngoại lệ thoát trực tiếp từ thân method.

Các lỗi gọi khác gồm `IllegalAccessException` (không đủ quyền truy cập method) hoặc `IllegalArgumentException` (receiver/đối số không phù hợp); không nên nhầm chúng với trạng thái của async result.

### 4.2. Ngoại lệ xảy ra khi Future/Stage hoàn tất

Nếu method trả về một `Future` hoặc `CompletionStage` bình thường, rồi công việc đại diện bởi đối tượng đó thất bại, **`Method.invoke` đã kết thúc**. Nó không thể bọc một lỗi phát sinh về sau vào một `InvocationTargetException` mới. Khi người gọi lấy completion, các API async phản ánh trạng thái tương ứng:

| Cách quan sát | Thành công | Thất bại | Bị hủy |
| --- | --- | --- | --- |
| `Future.get()` | Trả giá trị; có thể chờ | `ExecutionException` chứa cause | `CancellationException` |
| `Future.get(timeout, unit)` | Trả giá trị nếu kịp hạn | `ExecutionException` chứa cause | `CancellationException`; quá thời gian có `TimeoutException` |
| `CompletableFuture.join()` | Trả giá trị; có thể chờ | Thường ném `CompletionException` có cause | `CancellationException` |
| `CompletionStage.whenComplete(...)` | Nhận value | Nhận throwable để xử lý | Có thể nhận tình huống bị hủy như exceptional completion tùy stage |

`Future.get` khai báo `InterruptedException` và `ExecutionException` (thêm `TimeoutException` ở biến thể timeout). `CompletableFuture.join` không khai báo checked exceptions, thường dùng `CompletionException`/`CancellationException`. Nếu cần phục hồi tốt với việc ngắt thread, `get` phù hợp hơn để xử lý `InterruptedException` có chủ đích. Khi bắt `InterruptedException` mà không ném tiếp, thông thường nên phục hồi interrupt flag bằng `Thread.currentThread().interrupt()`.

**Hai tầng lỗi phải được theo dõi độc lập:** Reflection invocation có thể thành công nhưng Future/Stage thất bại; hoặc invocation thất bại trước cả khi có Future/Stage để theo dõi.

## 5. Chọn xử lý bất đồng bộ hay chờ có chủ đích

### 5.1. Tiếp tục pipeline không chặn bằng `CompletionStage`

Khi ứng dụng không cần kết quả ngay trong thread hiện tại, có thể giữ đối tượng stage và đăng ký xử lý:

```java
// Mảnh minh họa trong method; Service/service do ứng dụng định nghĩa.
Method method = Service.class.getMethod("loadAsync");
Object returned = method.invoke(service);

if (returned instanceof CompletionStage<?> stage) {
    stage.whenComplete((value, failure) -> {
        if (failure != null) {
            System.err.println("Async failed: " + failure);
        } else {
            System.out.println("Async value: " + value);
        }
    });
}
```

`whenComplete` đăng ký một action thực hiện khi stage hoàn tất. Nếu stage **đã hoàn tất**, callback không có hậu tố `Async` có thể chạy ngay trên thread gọi đăng ký; nếu stage hoàn tất sau, callback có thể chạy trên thread đang hoàn tất stage. Vì vậy “không gọi `get/join`” không có nghĩa mọi callback chắc chắn chạy trên thread khác. Khi cần điều khiển nơi callback chạy, cân nhắc `whenCompleteAsync(..., executor)` hoặc những API `*Async` tương ứng.

Nếu có nhiều bước phụ thuộc nhau, dùng:

- `thenApply` để biến đổi `T` thành `U`.
- `thenCompose` khi hàm biến đổi tự trả `CompletionStage<U>` và cần ghép một pipeline phẳng.
- `thenAccept` nếu chỉ tiêu thụ kết quả mà không trả giá trị mới.
- `exceptionally`, `handle` hoặc `whenComplete` để xử lý/quan sát completion bất thường, tùy semantics mong muốn.

Không vứt bỏ stage nếu caller cần nhận kết quả, xử lý lỗi hoặc thực hiện cancellation. `Method.invoke` không quản lý vòng đời async result hộ ứng dụng.

### 5.2. Chờ trong thread hiện tại khi nghiệp vụ bắt buộc

Có thể dùng hai nhánh theo **kiểu của đối tượng thực tế**:

```java
// Mảnh minh họa: cần các import java.util.concurrent.*;
// xử lý ReflectiveOperationException, InterruptedException,
// ExecutionException và TimeoutException theo hợp đồng method.
Object returned = method.invoke(receiver);

if (returned instanceof CompletionStage<?> stage) {
    Object value = stage.toCompletableFuture().get(3, TimeUnit.SECONDS);
    System.out.println(value);
} else if (returned instanceof Future<?> future) {
    Object value = future.get(3, TimeUnit.SECONDS);
    System.out.println(value);
} else {
    System.out.println(returned);
}
```

Với `CompletionStage`, giao diện không khai báo `get` hay `join`; gọi `toCompletableFuture()` để có một `CompletableFuture` theo hợp đồng completion. Khi cần giới hạn thời gian, `get(timeout, unit)` có thể báo `TimeoutException`. Timeout ở phía **đang chờ** không tự bảo đảm tác vụ nền đã dừng; muốn hủy cần dùng cơ chế cancellation phù hợp và hiểu semantics của implementation.

Kiểm tra `CompletionStage` trước `Future` là cách chọn nhánh rõ ràng vì một `CompletableFuture` triển khai **cả hai**. Việc chờ có thể block thread: tránh `get/join` trực tiếp trên UI thread, event-loop hoặc executor có số thread hạn chế nếu tác vụ cần chính thread đó để hoàn tất.

### 5.3. Khi nào `isDone` hữu ích?

`isDone` có thể dùng để **kiểm tra nhanh** trạng thái của `Future` nhưng không chờ. Tuy nhiên, `isDone == false` không nói tác vụ “vẫn đang chạy” hay “chưa được lên lịch”; `isDone == true` không bảo đảm thành công. Nếu ứng dụng cần kết quả có độ tin cậy, vẫn cần lấy completion hoặc đăng ký callback. Tránh kiểm tra `isDone` lặp liên tục trong vòng bận (busy spin) gây lãng phí CPU.

## 6. Một adapter rõ chính sách: `invokeRaw` và `invokeAndWait`

Khi xây dựng bộ gọi động (plugin dispatcher, test runner, serializer adapter), nên thể hiện rõ hợp đồng chờ của caller. Đoạn sau là **class hợp lệ có thể biên dịch** nếu lưu vào tệp `InvocationAdapter.java`:

```java
import java.lang.reflect.Method;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

public final class InvocationAdapter {
    public static Object invokeRaw(Method method, Object receiver,
                                   Object... args)
            throws ReflectiveOperationException {
        return method.invoke(receiver, args);
    }

    public static Object invokeAndWait(Method method, Object receiver,
                                       Object... args)
            throws ReflectiveOperationException, InterruptedException,
                   ExecutionException {
        Object returned = method.invoke(receiver, args);

        if (returned instanceof CompletionStage<?> stage) {
            return stage.toCompletableFuture().get();
        }
        if (returned instanceof Future<?> future) {
            return future.get();
        }
        return returned;
    }
}
```

**Ý nghĩa:**

- `invokeRaw` giữ nguyên semantics của `Method.invoke`: trả thẳng kết quả method, kể cả đối tượng async chưa hoàn tất.
- `invokeAndWait` là **hành vi do ứng dụng tự cài đặt**, lấy completion nếu kết quả runtime triển khai `CompletionStage` hoặc `Future`. Method thông thường thì trả giá trị như cũ.
- `method.invoke(...)` có thể ném `InvocationTargetException` (kế thừa `ReflectiveOperationException`) khi phương thức đích ném trực tiếp. `get` có thể ném `ExecutionException`, `InterruptedException`; đây là hai giai đoạn lỗi khác nhau.
- Đoạn đơn giản không đặt timeout. API production nên quy định **timeout/deadline, interruption, cancellation và nơi thực thi**. Không tự động biến mọi đường gọi Reflection thành thao tác chờ không giới hạn.

Một điểm thiết kế: method có thể khai báo return type là `Object` nhưng thực tế trả một `CompletionStage`. `instanceof` trên **giá trị runtime** sẽ nhận diện được trường hợp này; không nên chỉ dựa vào metadata chữ ký để quyết định “đợi hay không”.

## 7. Vai trò của `Method.getReturnType()` và generic return type

Reflection cho phép xem **kiểu trả về đã khai báo**, ví dụ:

```java
Class<?> declared = method.getReturnType();
boolean returnsStageType =
        CompletionStage.class.isAssignableFrom(declared);
boolean returnsFutureType =
        Future.class.isAssignableFrom(declared);
```

Đây là mảnh minh họa đặt trong method có biến `method` hợp lệ. Hai kiểm tra này trả lời: chữ ký **có khai báo kiểu thuộc họ Stage/Future hay không?** Chúng không cho biết runtime result đã hoàn tất, thành công hay lỗi. Nếu method khai báo `Object` nhưng trả `CompletableFuture`, `getReturnType()` vẫn là `Object.class`; sau khi gọi nên kiểm tra chính reference bằng `instanceof`.

`getGenericReturnType()` có thể cung cấp `Type` của chữ ký, ví dụ `CompletionStage<String>` khi metadata generic được giữ lại, nhưng **không biến `invoke` thành lời gọi có khả năng đợi completion**. Generic type không chứa trạng thái runtime của tác vụ.

Những trường hợp biên cần nhớ:

- `void method()` có thể khởi động một tác vụ nền nhưng `invoke` trả `null`; không thể suy ra Future từ giá trị này.
- `Future<T>` có thể đã completed trước khi `invoke` kết thúc: `get` khi ấy trả ngay.
- Một method trả `Future<T>` nhưng **chờ Future bên trong rồi mới return** vẫn khiến `invoke` chờ thân method; đó không phải khả năng “tự đợi Future” của Reflection.
- Method instance cần đúng receiver; static method có thể truyền receiver là `null`. Sai receiver/đối số gây lỗi gọi đồng bộ.
- Nếu method được gọi ném lỗi trực tiếp trước khi trả Future, caller chỉ có `InvocationTargetException`; không có async result mới từ lần gọi đó.

## 8. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| `String s = (String) method.invoke(target)` khi method trả `Future<String>` | Giá trị Reflection nhận là **Future**, không phải `String` bên trong | Nhận `Future<?>`/`CompletionStage<?>` rồi giải quyết kết quả theo hợp đồng |
| Nghĩ `invoke` tự chờ cho đến khi Future xong | `invoke` chỉ chờ **thân method return** | Đợi bằng `get/join` nếu bắt buộc hoặc nối pipeline |
| Nghĩ `Method.invoke` luôn trả ngay | Method đích có thể tự block trước khi return | Phân tích thân method và nơi xảy ra chờ |
| Nhầm `InvocationTargetException` với lỗi bất đồng bộ | Lỗi completion xuất hiện sau khi method return và qua đối tượng async | Theo dõi cả hai tầng lỗi |
| Ép mọi `Future` thành `CompletableFuture` | Hai kiểu không tương đương; implement khác có thể không kế thừa CF | Kiểm tra runtime types, xử lý từng hợp đồng |
| Gọi `join` trên event-loop rồi cần event-loop đó hoàn tất Future | Có thể deadlock | Dùng composition hoặc executor riêng, tránh blocking cùng luồng |
| Thấy `isDone() == true` và tin rằng tác vụ thành công | Done gồm cả thất bại/hủy | Dùng `get/join` hoặc error callback để phân loại |
| Bỏ qua giá trị trả về async | Không còn đường theo dõi lỗi hoặc kết quả | Trả về stage, đăng ký callback, hoặc quản lý task lifecycle rõ ràng |

### Minh họa một deadlock đơn giản

```java
CompletableFuture<String> pending = new CompletableFuture<>();
System.out.println(pending.join()); // Chờ đến khi pending được hoàn tất
pending.complete("done");          // Không thể tới được trên cùng thread
```

Đây là **mảnh mã minh họa**, không phải chương trình độc lập. Nếu không có thread khác thực hiện `complete`, `join` chờ mãi và dòng bên dưới không được chạy. Nếu một framework đặt `get/join` trong callback trên chính thread/event-loop cần chạy công việc hoàn tất, vấn đề tương tự có thể xuất hiện.

## 9. Câu hỏi tự kiểm tra

1. `Method.invoke` gọi method trả `Future<String>` chưa hoàn tất. Reference trả về có kiểu runtime gì và `(String) invoke(...)` sai ở đâu?
2. Tại sao `invoke` vẫn có thể block lâu dù method trả `CompletableFuture`?
3. Method A ném `IllegalStateException` trước `return`. Method B trả stage rồi stage hoàn tất lỗi `IllegalStateException`. Hai đường báo lỗi tới caller khác nhau ra sao?
4. So sánh `future.get()` với `stage.thenApply(...)` về hành vi chờ và thời điểm callback chạy.
5. `CompletableFuture` có thể phù hợp với cả nhánh `Future` và `CompletionStage` trong `instanceof` hay không? Nên ưu tiên nhánh nào khi muốn composition?
6. Method khai báo kiểu trả `Object` nhưng runtime trả `CompletionStage<?>`. Vì sao chỉ xem `getReturnType()` chưa đủ?
7. Một method trả `void` nhưng bắt đầu tác vụ nền. Làm thế nào thiết kế API để caller có thể chờ hoặc theo dõi kết quả?
8. Vì sao nên đặt timeout và quy định interruption/cancellation nếu ứng dụng quyết định đợi completion?

**Ghi nhớ:** `Method.invoke` đồng bộ hóa **lời gọi method trực tiếp**, còn trạng thái hoàn tất của `Future`/`CompletionStage` là **một hợp đồng độc lập**. Kết quả bất đồng bộ chỉ được chờ/quan sát khi caller chủ động thực hiện `get`, `join` hoặc đăng ký composition phù hợp. Luôn phân biệt lỗi của method khi đang chạy qua Reflection (`InvocationTargetException`) với lỗi của tác vụ trả về (`ExecutionException`, `CompletionException`, `CancellationException`).

## 10. Tham khảo chính thức

- [Java SE 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)): giá trị trả về và ngoại lệ do method được gọi ném ra.
- [Java SE 17 — `Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, timeout, cancellation, `isDone`.
- [Java SE 17 — `CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): phối hợp các giai đoạn và xử lý completion.
- [Java SE 17 — `CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `get`, `join`, xử lý lỗi và triển khai cả `Future`/`CompletionStage`.
- [Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): lỗi của thân method qua Reflection.