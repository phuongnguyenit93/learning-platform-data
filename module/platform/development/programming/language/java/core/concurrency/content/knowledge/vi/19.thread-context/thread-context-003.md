# InheritableThreadLocal và các giới hạn kế thừa trong Java Concurrency

## 1. Vì sao cần hiểu cơ chế này?

`ThreadLocal<T>` gắn một giá trị riêng với **thread hiện tại**. Hai thread dùng chung cùng một biến `ThreadLocal` nhưng mỗi thread có ánh xạ giá trị của riêng nó. Cơ chế này đôi khi được dùng để giữ request ID, correlation ID, tùy chọn ngôn ngữ hoặc một ngữ cảnh xử lý mà nhiều hàm trên cùng thread cần truy cập.

Vấn đề xuất hiện khi một công việc tạo **thread con**: `ThreadLocal` thông thường không tự truyền giá trị của thread tạo sang thread mới. `InheritableThreadLocal<T>` cung cấp cơ chế nhận **giá trị ban đầu** của thread tạo khi thread mới được khởi tạo.

Điều quan trọng nhất: **kế thừa ở đây là thao tác khởi tạo theo thời điểm tạo thread, không phải một luồng đồng bộ hóa context liên tục, không bảo đảm theo từng task và không tự xử lý dữ liệu mutable.** Nếu dùng sai trong thread pool, ứng dụng có thể đọc context cũ hoặc làm lộ dữ liệu giữa các request.

Bài học tập trung vào API và hành vi của **Java concurrency thuần**, gồm platform threads, executor và virtual threads.

### Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt `ThreadLocal` và `InheritableThreadLocal` trên cùng một ví dụ.
- Giải thích chính xác **khi nào**, **từ thread nào**, **giá trị nào** được truyền sang thread mới.
- Dùng `childValue(T parentValue)` để tạo bản sao hoặc biến đổi giá trị ban đầu.
- Nhận ra giới hạn với mutable object, thread pool, executor, luồng tạo gián tiếp và virtual threads.
- Lựa chọn truyền tham số, bọc task có cleanup hoặc tắt kế thừa khi không cần thiết.

## 2. ThreadLocal so với InheritableThreadLocal

Hai lớp đều có `get()`, `set(value)` và `remove()`, nhưng khác cách khởi tạo dữ liệu trong thread con.

| Tiêu chí | `ThreadLocal<T>` | `InheritableThreadLocal<T>` |
|---|---|---|
| Giá trị của thread hiện tại | `get()`/`set()` trên từng thread | Tương tự |
| Khi tạo thread con | Không tự nhận giá trị cha | Mặc định nhận giá trị ban đầu từ cha |
| Khi cha gọi `set()` sau thời điểm tạo con | Không truyền sang con | **Không cập nhật lại** bản sao ánh xạ ở con |
| Khi con gọi `set()` | Chỉ đổi ánh xạ ở con | Chỉ đổi ánh xạ ở con |
| Khi giá trị là object mutable | Mỗi thread giữ tham chiếu riêng nếu được set riêng | Mặc định cha và con có thể giữ **cùng tham chiếu object** |
| Thread pool tái sử dụng worker | Không tự theo context của task | Cũng **không tự theo context của task** |
| Cleanup | `remove()` khi kết thúc phạm vi dùng | `remove()` khi kết thúc phạm vi dùng |

Đừng hiểu “giá trị riêng của thread” là “object luôn được copy”. Ánh xạ `ThreadLocal → value` nằm riêng ở mỗi thread; hai ánh xạ vẫn có thể trỏ tới **chính cùng một object**.

### Ví dụ chạy được: kế thừa tại thời điểm tạo thread

**Tệp `InheritanceTiming.java` (Java 21+):**

```java
public class InheritanceTiming {
    private static final ThreadLocal<String> ORDINARY =
            new ThreadLocal<>();

    private static final InheritableThreadLocal<String> INHERITED =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        ORDINARY.set("ordinary-parent");
        INHERITED.set("A");

        try {
            Thread child = Thread.ofPlatform().unstarted(() -> {
                try {
                    System.out.println("child ordinary=" + ORDINARY.get());
                    System.out.println("child inherited=" + INHERITED.get());
                    INHERITED.set("CHILD");
                } finally {
                    ORDINARY.remove();
                    INHERITED.remove();
                }
            });

            // Thread con đã được TẠO; chưa được START.
            INHERITED.set("B");
            child.start();
            child.join();

            System.out.println("parent inherited=" + INHERITED.get());
        } finally {
            ORDINARY.remove();
            INHERITED.remove();
        }
    }
}
```

Biên dịch, chạy:

```bash
javac InheritanceTiming.java
java InheritanceTiming
```

Stdout chính xác:

```text
child ordinary=null
child inherited=A
parent inherited=B
```

Giải thích:

1. Cha `set("A")` vào `INHERITED`.
2. `Thread.ofPlatform().unstarted(...)` **tạo đối tượng thread mới**; lúc đó thread con nhận giá trị ban đầu `"A"`.
3. Cha đổi thành `"B"` **sau khi tạo nhưng trước khi start**. Việc này chỉ đổi ánh xạ ở cha.
4. Con bắt đầu và đọc `INHERITED.get() == "A"`; `ORDINARY.get()` là `null` vì không có giá trị khởi tạo.
5. Con `set("CHILD")` không đổi giá trị của cha. Sau `join()`, cha vẫn đọc `"B"`.

`join()` bảo đảm main chờ con in xong, vì vậy thứ tự stdout này xác định. Nếu dùng `new Thread(runnable)`, thời điểm kế thừa cũng là **tạo thread**, không phải gọi `start()`.

## 3. Cơ chế childValue: sao chép ánh xạ và biến đổi giá trị

`InheritableThreadLocal` ghi đè cách tạo dữ liệu ban đầu cho child thread qua:

```java
protected T childValue(T parentValue)
```

Theo API Java:

- Runtime lấy giá trị tương ứng từ inheritable-thread-local map của **thread đang tạo child thread**.
- `childValue(parentValue)` được gọi **trong thread tạo**, **trước khi child thread bắt đầu chạy**.
- Mặc định implementation trả về **chính `parentValue`**.
- Có thể override để tạo bản sao, biến đổi, lọc bớt hoặc ngăn một phần dữ liệu đi sang child.
- `childValue` không phải hook chạy mỗi khi `get()` ở con, và cũng không chạy sau mỗi `submit` task.

Bởi vậy, thao tác kế thừa là **snapshot các ánh xạ tại thời điểm tạo**. Snapshot này không đồng nghĩa **deep copy mọi object**. Chi phí sao chép bản đồ các mục kế thừa tăng theo số mục hiện có trên thread cha.

### Ví dụ: mutable reference mặc định và bản sao do childValue

**Tệp `MutableInheritance.java` (Java 21+):**

```java
import java.util.ArrayList;
import java.util.List;

public class MutableInheritance {
    private static final InheritableThreadLocal<List<String>> SHARED =
            new InheritableThreadLocal<>();

    private static final InheritableThreadLocal<List<String>> COPIED =
            new InheritableThreadLocal<>() {
                @Override
                protected List<String> childValue(List<String> parentValue) {
                    return parentValue == null
                            ? null
                            : new ArrayList<>(parentValue);
                }
            };

    public static void main(String[] args) throws InterruptedException {
        SHARED.set(new ArrayList<>(List.of("origin")));
        COPIED.set(new ArrayList<>(List.of("origin")));

        try {
            Thread child = Thread.ofPlatform().start(() -> {
                try {
                    SHARED.get().add("child");
                    COPIED.get().add("child");
                } finally {
                    SHARED.remove();
                    COPIED.remove();
                }
            });
            child.join();

            System.out.println("shared parent=" + SHARED.get());
            System.out.println("copied parent=" + COPIED.get());
        } finally {
            SHARED.remove();
            COPIED.remove();
        }
    }
}
```

Chạy:

```bash
javac MutableInheritance.java
java MutableInheritance
```

Stdout:

```text
shared parent=[origin, child]
copied parent=[origin]
```

`SHARED` dùng `childValue` mặc định: hai thread có ánh xạ độc lập nhưng cùng giữ **một `ArrayList`**. Con thêm phần tử nên cha cũng nhìn thấy. `COPIED` tạo `ArrayList` mới cho con, vì thế chỉnh sửa của con không đổi danh sách của cha.

**Điểm cần lưu ý:**

- `new ArrayList<>(parentValue)` là **shallow copy**: sao chép container và các tham chiếu phần tử. Nếu phần tử cũng mutable, parent và child vẫn có thể chia sẻ các object con.
- Nếu nhiều thread cùng sửa object chung mà không đồng bộ hóa, có thể xảy ra data race, mất cập nhật hoặc trạng thái hỏng. `InheritableThreadLocal` **không cung cấp synchronization**.
- Với context là immutable value (ví dụ `String`, record gồm trường immutable, identifier), chia sẻ cùng object thường đơn giản và ít rủi ro hơn.
- Có thể đưa logic kiểm tra hoặc đóng gói dữ liệu vào `childValue`, nhưng không nên thực hiện I/O chậm, side effect phức tạp hoặc thao tác dựa trên child đã start: phương thức chạy trong **thread tạo child**.

## 4. Giới hạn lớn nhất: thread pool không tạo thread mới cho mỗi task

Một request/task có thể được gọi `submit()` từ thread đang giữ context, nhưng **task không tự động trở thành “thread con” của thread submit**. Executor chạy task trên worker do nó quản lý. Với fixed pool, worker thường được tạo một lần rồi chạy nhiều task.

Điều đó dẫn tới hai lỗi:

1. **Stale context:** worker nhận ngữ cảnh lúc nó được tạo; các lần submit sau thay đổi context trên caller nhưng worker vẫn giữ giá trị cũ.
2. **Context leakage:** một task thay giá trị trong worker mà không cleanup; task tiếp theo trên cùng worker có thể nhìn thấy giá trị của task trước.

### Ví dụ thực nghiệm với một worker cố định

**Tệp `PoolInheritanceTrap.java` (Java 21+):**

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class PoolInheritanceTrap {
    private static final InheritableThreadLocal<String> CONTEXT =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool = Executors.newSingleThreadExecutor()) {
            CONTEXT.set("request-A");
            System.out.println("first=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());

            CONTEXT.set("request-B");
            System.out.println("second=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());

            pool.submit(() -> {
                CONTEXT.set("worker-overwrite");
            }).get();

            System.out.println("third=" +
                    pool.submit(() -> { return CONTEXT.get(); }).get());
        } finally {
            CONTEXT.remove();
        }
    }
}
```

Chạy:

```bash
javac PoolInheritanceTrap.java
java PoolInheritanceTrap
```

Stdout:

```text
first=request-A
second=request-A
third=worker-overwrite
```

Vì `newSingleThreadExecutor()` tạo worker khi task đầu được thực thi, worker nhận `"request-A"` tại lúc tạo. Caller đổi thành `"request-B"` nhưng worker **không được tạo lại**. Task thứ ba đổi context bên trong worker thành `"worker-overwrite"`; task tiếp theo đọc lại đúng giá trị còn sót trong worker.

Ví dụ sử dụng duy nhất một worker và chờ từng `Future.get()` để kết quả xác định. Với pool nhiều worker, mỗi worker có thể được tạo vào thời điểm khác nhau; vì vậy cùng một logic sai có thể tạo lỗi **khó tái hiện**, phụ thuộc thời điểm và lịch chạy.

**Quy tắc quan trọng:** Không giả định `InheritableThreadLocal` sẽ tự lan truyền context của từng request qua `ExecutorService.submit()`, `execute()`, `CompletableFuture.supplyAsync()` hoặc các callback bất đồng bộ. Giá trị phụ thuộc **thread nào thực sự tạo thread thực thi** và vòng đời của worker, không phụ thuộc quan hệ gọi hàm của request.

## 5. Truyền context một cách xác định cho executor

Cách rõ nhất là **truyền context thành tham số**. Một `record` immutable biểu diễn request context khiến phụ thuộc hiện rõ trong API:

```java
record RequestContext(String traceId) {}

static String process(RequestContext context, String payload) {
    return context.traceId() + ":" + payload;
}
```

Đây là đoạn minh họa đặt trong một class; `process` nhận context trực tiếp nên không lệ thuộc thread thực thi.

Nếu phải tương tác với API hiện hữu đọc `ThreadLocal`, có thể **capture context tại thời điểm submit** rồi **bind và cleanup trong thread thực thi**. Đây là lựa chọn chủ động của ứng dụng, không phải phép màu của `InheritableThreadLocal`.

### Ví dụ hoàn chỉnh: capture, restore và cleanup

**Tệp `ExplicitContext.java` (Java 21+):**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExplicitContext {
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    private static <T> Callable<T> withTrace(
            String traceId, Callable<T> action) {
        return () -> {
            String previous = TRACE_ID.get();
            TRACE_ID.set(traceId);
            try {
                return action.call();
            } finally {
                if (previous == null) {
                    TRACE_ID.remove();
                } else {
                    TRACE_ID.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        try (ExecutorService pool = Executors.newSingleThreadExecutor()) {
            System.out.println(pool.submit(
                    withTrace("R-1", () -> "task1=" + TRACE_ID.get())).get());

            System.out.println(pool.submit(
                    withTrace("R-2", () -> "task2=" + TRACE_ID.get())).get());

            System.out.println("after=" +
                    pool.submit(() -> { return TRACE_ID.get(); }).get());
        }
    }
}
```

Chạy:

```bash
javac ExplicitContext.java
java ExplicitContext
```

Stdout:

```text
task1=R-1
task2=R-2
after=null
```

`withTrace` là task wrapper: trước khi xử lý nó bind giá trị dành cho task; trong `finally` nó trả lại trạng thái của worker. Với ví dụ này, quy ước `null` nghĩa là chưa có giá trị. Nếu ứng dụng cho phép **giá trị null có ý nghĩa riêng**, thiết kế context và quy tắc phục hồi phải thể hiện rõ trạng thái đó thay vì suy chỉ bằng `get() == null`.

Khi cần truyền **nhiều thuộc tính**, nên gói chúng vào một context immutable thay vì duy trì nhiều `ThreadLocal` riêng lẻ khó snapshot, khó phục hồi. Nếu có yêu cầu cách ly hoặc quyền truy cập dữ liệu, phải xác định chính xác task nào được phép nhận context.

### Đừng bỏ qua trường hợp lỗi

Mẫu wrapper phải dùng `finally` vì `action.call()` có thể ném exception. Với `Callable<T>`, exception tiếp tục được đưa về `Future.get()` qua `ExecutionException`; cleanup vẫn chạy. Khi sao chép context mutable, tạo bản sao phù hợp **trước** khi task dùng để tránh chia sẻ object giữa các task.

Nếu một thread pool xử lý các job từ nhiều user, dữ liệu nhận dạng, token hoặc thông tin quyền truy cập không nên được kế thừa tự động sang job không liên quan. Context truyền theo ranh giới nhiệm vụ phải được **chọn lọc rõ ràng**.

## 6. Virtual threads: vẫn có kế thừa, nhưng cần tiết chế

Virtual threads trở thành tính năng chính thức từ Java 21. Chúng cũng hỗ trợ `ThreadLocal` và `InheritableThreadLocal`. Với `Thread.Builder`, mặc định là **kế thừa inheritable-thread-local values** từ **thread tạo virtual thread**; có thể vô hiệu hóa bằng `inheritInheritableThreadLocals(false)`.

**Tệp `VirtualInheritance.java` (Java 21+):**

```java
public class VirtualInheritance {
    private static final InheritableThreadLocal<String> REQUEST =
            new InheritableThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        REQUEST.set("parent-context");

        try {
            Thread inherited = Thread.ofVirtual().start(() -> {
                try {
                    System.out.println("default=" + REQUEST.get());
                } finally {
                    REQUEST.remove();
                }
            });
            inherited.join();

            Thread isolated = Thread.ofVirtual()
                    .inheritInheritableThreadLocals(false)
                    .start(() -> {
                        try {
                            System.out.println("isolated=" + REQUEST.get());
                        } finally {
                            REQUEST.remove();
                        }
                    });
            isolated.join();
        } finally {
            REQUEST.remove();
        }
    }
}
```

Chạy:

```bash
javac VirtualInheritance.java
java VirtualInheritance
```

Stdout:

```text
default=parent-context
isolated=null
```

Hai thao tác `join()` làm thứ tự output xác định. `isolated` không kế thừa dữ liệu vì builder đã tắt cơ chế này.

### Vì sao cần cân nhắc với virtual threads?

Virtual threads có thể rất nhiều (hàng chục nghìn hoặc hơn, tùy workload), trong khi mỗi virtual thread vẫn có thể giữ các entry thread-local và object được chúng tham chiếu. Nếu context lớn, mỗi child sao chép một map nhiều mục hoặc `childValue` tạo các bản sao mutable lớn, **chi phí bộ nhớ và tạo thread sẽ tăng đáng kể**.

Không dùng `ThreadLocal` như cache tài nguyên lớn “cho mỗi thread” khi số virtual thread có thể rất lớn. Nếu không cần truyền ngữ cảnh khi tạo thread, tắt inheritance có chủ đích. Nếu cần, truyền context nhỏ, immutable và giới hạn vòng đời.

Lưu ý thêm: thread mới kế thừa từ **thread thực sự khởi tạo nó**, không mặc định từ “request gốc” theo cách suy luận của người lập trình. Nếu thread khác chịu trách nhiệm tạo virtual thread, nguồn kế thừa chính là thread tạo đó.

## 7. Giới hạn vòng đời và các ranh giới kế thừa

### 7.1. Không phải quan hệ cha–con sống

Từ ngữ “parent/child thread” chỉ **quan hệ tại thời điểm tạo**. Nó không có nghĩa child tự động đọc những cập nhật mới của parent, không có tính năng đồng bộ giá trị hai chiều, và không có bảo đảm child kết thúc khi parent kết thúc.

Ví dụ với immutable `String`:

```text
T0: parent.set("A")
T1: tạo child       → child nhận giá trị ban đầu "A"
T2: parent.set("B") → parent="B", child="A"
T3: child.set("C")  → parent="B", child="C"
T4: parent.remove() → không tự remove ở child
```

Nếu giá trị là **cùng mutable reference**, thay đổi object được chia sẻ có thể được thread còn lại quan sát theo các quy tắc đồng bộ hóa bộ nhớ Java; tuyệt đối không coi đó là cơ chế truyền context đúng đắn.

### 7.2. Kế thừa qua nhiều thế hệ

Khi thread A tạo B, B nhận các giá trị ban đầu do A để lại (qua `childValue`). Nếu B sau đó tạo C, C nhận từ **B tại thời điểm B tạo C**, không truy ngược về A. Mỗi bước có thể áp dụng `childValue` riêng. Thread không phải được tạo bên trong logic nghiệp vụ vẫn có thể mang context nếu nó được một thread có inheritable values khởi tạo.

### 7.3. remove() không thu hồi giá trị đã kế thừa ở child

`remove()` chỉ loại ánh xạ ở **thread hiện tại**. Khi cha gọi `remove()` sau khi tạo child, giá trị đã kế thừa ở child không tự mất. Khi child sống lâu, dữ liệu có thể tiếp tục được giữ; nếu reference đến object lớn thì object chưa thể được GC chỉ vì cha đã remove.

Ứng dụng cần kiểm soát vòng đời task và cleanup tại **mỗi nơi thật sự bind hoặc giữ context**, đặc biệt với worker dùng lại.

### 7.4. initialValue và childValue khác nhau

- `initialValue()` (kế thừa từ `ThreadLocal`) cung cấp giá trị khởi đầu khi `get()` trên thread hiện tại chưa có entry.
- `childValue(parentValue)` cung cấp **giá trị ban đầu được kế thừa** lúc một child thread được tạo trong trường hợp thread tạo đang có entry tương ứng.

Nếu thread không nhận entry kế thừa, lần `get()` đầu có thể gọi `initialValue()`. Vì vậy, khi thử bật/tắt inheritance, hãy tính đến override `initialValue` hoặc `withInitial`: không nên suy luận rằng `get() == null` là cách nhận biết duy nhất cho “không kế thừa”.

## 8. Khi nào nên dùng, khi nào tránh?

**Có thể phù hợp** khi bạn thực sự tạo một số thread con có quan hệ tác vụ rõ ràng, cần chuyển **giá trị khởi tạo immutable**, không sử dụng worker reuse khó kiểm soát, và đã chủ động quản lý vòng đời.

**Nên tránh dùng làm mặc định** khi:

- Chạy trên fixed/cached thread pool hay chuỗi callback không kiểm soát thread nào thực thi.
- Context chứa object mutable phức tạp, buffer lớn, connection, transaction, tài nguyên phải đóng hoặc reference tới đồ thị object lớn.
- Hệ thống có nhiều request độc lập và có nguy cơ rò rỉ context hoặc nhầm danh tính giữa các task.
- Tạo số lượng rất lớn virtual threads mà inheritance không thực sự cần thiết.
- Muốn “tự động” bảo đảm mọi hàm async nhận đúng dữ liệu của caller: API này không đưa ra hợp đồng như vậy.

Thứ tự lựa chọn thực dụng:

1. **Truyền context thành tham số** hoặc đặt trong object biểu diễn request/job khi có thể.
2. Nếu phải dùng executor với API phụ thuộc thread-local, **capture khi submit + bind khi chạy + restore trong finally**.
3. Dùng `InheritableThreadLocal` khi chính hành vi **khởi tạo child thread** là ranh giới mong muốn và dữ liệu được kiểm soát.
4. Với Java 25+, cân nhắc **`ScopedValue`** cho ngữ cảnh đọc chủ yếu theo phạm vi gọi hàm; lưu ý semantics và yêu cầu phiên bản khác với `InheritableThreadLocal`.

`ScopedValue` là API chính thức trong Java 25 (JEP 506), cung cấp binding theo phạm vi để truyền dữ liệu một chiều qua call stack. Nó không phải cách “bật kế thừa cho mọi thread bất kỳ” và không nên lẫn với `InheritableThreadLocal`. Nếu chương trình phải tương thích Java 21, không thể sử dụng API Java 25 này mà không thay đổi runtime/source baseline.

## 9. Những hiểu nhầm thường gặp

| Nhận định sai | Thực tế |
|---|---|
| “Child đọc giá trị của parent tại lúc `start()`.” | Đọc **bản khởi tạo từ lúc child được tạo**. |
| “`InheritableThreadLocal` làm đồng bộ context cha và con.” | Không có đồng bộ giá trị liên tục hoặc hai chiều. |
| “Con gọi `set()` sẽ cập nhật parent.” | Không; mỗi thread có ánh xạ riêng. |
| “Hai thread luôn giữ hai object độc lập.” | Mặc định `childValue` trả cùng tham chiếu; mutable object có thể bị chia sẻ. |
| “Gửi request mới vào executor sẽ cập nhật worker.” | Không; worker tái sử dụng context cũ nếu không bind/cleanup. |
| “`remove()` ở parent xóa cả child.” | Chỉ xóa tại thread gọi. |
| “Virtual thread không hỗ trợ ThreadLocal.” | Có hỗ trợ; nhưng chi phí và vòng đời phải được cân nhắc. |
| “Muốn tắt inheritance phải dùng API ngoài JDK.” | Java 21 `Thread.Builder.inheritInheritableThreadLocals(false)` hỗ trợ trực tiếp. |
| “Có context nên khỏi cần truyền thông tin phân quyền.” | Context ngầm dễ bị kế thừa nhầm; quyền truy cập phải được xác nhận ở đúng ranh giới nghiệp vụ. |

## 10. Checklist kiểm tra khi review code concurrency

- [ ] Xác định rõ thread **tạo** thread mới, không chỉ thread **gửi task**.
- [ ] Nếu là executor, xác định worker được tạo lúc nào và có tái sử dụng không.
- [ ] Phân biệt `ThreadLocal` thường và `InheritableThreadLocal`; không giả định cùng hành vi.
- [ ] Chỉ kế thừa dữ liệu thực sự cần; ưu tiên immutable hoặc `childValue` sao chép đúng độ sâu cần thiết.
- [ ] Mọi bind có phạm vi rõ và cleanup `finally` tại nơi sử dụng.
- [ ] Không lưu mật khẩu, token, đối tượng request lớn hoặc connection lâu dài trong context ngầm.
- [ ] Có kiểm thử nhiều task liên tiếp trên **cùng một worker** để phát hiện stale context và leakage.
- [ ] Với virtual threads, cân nhắc `inheritInheritableThreadLocals(false)` khi không cần.
- [ ] Xác nhận version JDK nếu dùng `Thread.ofVirtual()` (Java 21+) hoặc `ScopedValue` (Java 25+).

## 11. Tự luyện

**Câu 1.** Parent `set("A")` rồi tạo child bằng `unstarted(...)`, sau đó `set("B")` và mới gọi `start()`. Nếu dùng `InheritableThreadLocal<String>`, child nhận gì? Vì sao?

**Câu 2.** Một `newSingleThreadExecutor()` xử lý task của user A rồi task của user B. Nếu worker kế thừa user A lúc tạo, tại sao task B có thể thấy user A dù caller đã thay context?

**Câu 3.** Vì sao `childValue(parentValue)` trả `new ArrayList<>(parentValue)` có thể vẫn chưa đủ khi danh sách chứa các mutable object?

**Câu 4.** `remove()` ở parent có bảo đảm dữ liệu đã kế thừa không còn tồn tại ở child đang chạy không?

**Câu 5.** Khi cần truyền correlation ID qua executor dùng lại worker, cách nào có lifecycle dễ kiểm soát hơn: dựa vào kế thừa lúc tạo worker, hay capture–bind–finally–restore trong mỗi task?

**Gợi ý đáp án:** (1) `"A"`, vì kế thừa lúc **tạo**; (2) worker được tái sử dụng và không tự cập nhật theo task; (3) shallow copy vẫn chia sẻ phần tử; (4) không; (5) capture–bind–restore theo mỗi task hoặc truyền tham số.

## Tài liệu Java chính thức

- [InheritableThreadLocal (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): ý nghĩa kế thừa và `childValue`.
- [Thread.Builder (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html): tạo thread, thời điểm kế thừa và `inheritInheritableThreadLocals(boolean)`.
- [Executors (Java SE 21 API)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): executor và worker management.
- [JEP 444 – Virtual Threads](https://openjdk.org/jeps/444): virtual threads và lưu ý về thread-local data.
- [JEP 506 – Scoped Values](https://openjdk.org/jeps/506): API ngữ cảnh theo phạm vi hoàn thiện trong Java 25.

> **Nguyên tắc cốt lõi:** `InheritableThreadLocal` chỉ chuyển **giá trị ban đầu khi tạo thread con**. Khi code đi qua executor, thread pool hoặc context mutable, bạn phải quản lý việc truyền và dọn dẹp dữ liệu theo đúng **vòng đời task**.