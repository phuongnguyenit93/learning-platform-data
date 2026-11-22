# Phân biệt thread-local handshake của HotSpot với biến ThreadLocal của ứng dụng Java

> **Java 10 — Handshake theo luồng.** **Thread-Local Handshakes (JEP 312)** là cơ chế **nội bộ HotSpot JVM** cho phép thực hiện một số công việc phối hợp với một hay nhiều JavaThread ở trạng thái an toàn mà **không nhất thiết phải đưa mọi luồng Java vào một global safepoint**. **`java.lang.ThreadLocal<T>`** lại là **API public của ứng dụng**, giúp mỗi Java `Thread` có một giá trị gắn riêng với khóa `ThreadLocal`. Hai cơ chế chỉ giống nhau về từ “thread-local”; chúng **không thay thế nhau, không gọi nhau và không có cùng mục đích**. Bài học sử dụng các API còn áp dụng trên JDK hiện đại, không hướng dẫn sử dụng nội bộ HotSpot không được hỗ trợ hoặc các kỹ thuật legacy.

## 1. Mục tiêu học tập

Hoàn thành bài này, bạn có thể:

1. Nêu đúng mục đích của **JEP 312 — Thread-Local Handshakes**, được đưa vào **JDK 10**, và lý do nó làm giảm nhu cầu phải dừng toàn JVM trong một số thao tác.
2. Giải thích khác biệt giữa **global safepoint**, **per-thread handshake** và **lưu dữ liệu theo luồng** qua `ThreadLocal`.
3. Xác định đâu là API **public Java SE** để ứng dụng sử dụng, đâu là **hạ tầng nội bộ của VM** không có lời gọi public như `Thread.handshake()`.
4. Dùng `ThreadLocal.withInitial`, `get`, `set` và `remove` đúng hợp đồng; biết `initialValue` có thể được gọi lại sau `remove`.
5. Hiểu `static final ThreadLocal` là **khóa dùng chung** nhưng **giá trị riêng từng thread**, không phải một biến static chia sẻ cùng giá trị giữa tất cả thread.
6. Nhận diện rủi ro **rò rỉ ngữ cảnh giữa các request** khi thread pool tái sử dụng platform thread mà ứng dụng quên `remove()`.
7. Phân biệt `ThreadLocal` với `InheritableThreadLocal`, cũng như không suy ra dữ liệu tự truyền qua `ExecutorService`, `CompletableFuture` hay thread mới.
8. Hiểu `ThreadLocal` không tự tạo synchronization, không thay `volatile`/lock và không làm một **đối tượng mutable được tham chiếu chung** trở nên thread-safe.
9. Giải thích tương quan với **virtual threads (Java 21+)** và lựa chọn **`ScopedValue` (final API từ JDK 25)** cho dữ liệu ngữ cảnh chỉ đọc có vòng đời theo scope.
10. Chạy một lab Java 17+ độc lập, xác nhận **16 dòng stdout xác định**, đồng thời phân biệt rõ phần lab chỉ chứng minh `ThreadLocal`, **không phải thí nghiệm gọi một VM handshake**.
11. Chẩn đoán sự cố safepoint/handshake bằng công cụ phù hợp với JDK nhưng không đánh đồng log JVM với `ThreadLocal` user-level.
12. Giải thích và sửa những ngộ nhận thường gặp bằng các bài tập có đáp án.

## 2. Hai khái niệm giống tên nhưng khác tầng trừu tượng

| Tiêu chí | Thread-local handshake — JEP 312 | `ThreadLocal<T>` — Java API |
| --- | --- | --- |
| Tầng hoạt động | **Bên trong HotSpot VM**, cơ chế phối hợp với JavaThread và safepoint | **Trong ứng dụng Java**, class thuộc `java.lang` |
| Xuất hiện | Tính năng JDK **10** | Class có từ **Java 1.2**; `withInitial` từ Java 8 |
| Mục đích | Thực thi một số VM callback/operation ở trạng thái luồng **safepoint-safe**, tránh VM-wide safepoint khi khả thi | Lưu và truy xuất **một giá trị riêng** cho mỗi `Thread` trên cùng khóa |
| Đối tượng thao tác | VM-internal JavaThread, VM operation, callback | `ThreadLocal<T>`, giá trị `T`, `Thread.currentThread()` |
| Đầu vào | Do VM/HotSpot lên lịch; application không cung cấp một Java `Runnable` qua public handshake API | Ứng dụng gọi `get()`, `set(value)`, `remove()` |
| Hệ quả | Có thể ảnh hưởng latency của VM coordination, scope dừng luồng, thời gian chờ safepoint | Ảnh hưởng vòng đời request state, per-thread isolation, allocation/retention |
| Có thể dừng thread? | Có thể cần target thread ở trạng thái safe trong thời gian thao tác | `get/set/remove` không mang ý nghĩa “dừng luồng khác” |
| Tự chia sẻ dữ liệu giữa thread? | Không phải cơ chế truyền user request context | **Không**; mỗi thread có giá trị riêng trừ khi tự chuyển đối tượng/tham chiếu |
| Tự dọn giá trị `ThreadLocal`? | **Không** có hợp đồng này | Ứng dụng phải `remove` ở scope thích hợp hoặc khi thread kết thúc |
| Portability | Chi tiết triển khai **phụ thuộc HotSpot và phiên bản JDK** | API public Java SE có hợp đồng Javadoc |
| Ví dụ | VM thực hiện một công việc trên một target JavaThread mà không cần mọi JavaThread cùng ở global safepoint | Worker A có `request-A`, worker B có `request-B` với cùng khóa `ThreadLocal` |

**Một câu phân biệt:** handshake là **cách VM phối hợp thực thi công việc an toàn trên thread**; `ThreadLocal` là **chỗ ứng dụng giữ trạng thái riêng của thread**. Từ “local” ở đây **không** đồng nghĩa hai cơ chế dùng chung một vùng dữ liệu, một API hoặc một cơ chế đồng bộ.

## 3. JEP 312: thread-local handshake thật sự giải quyết vấn đề gì?

### 3.1. Global safepoint là gì?

Trong HotSpot, một số công việc cần VM có trạng thái đủ ổn định để quan sát hoặc thao tác dữ liệu về thread/stack/metadata. **Global safepoint** là một dạng phối hợp để các JavaThread liên quan đạt trạng thái an toàn mà VM có thể thực hiện công việc cần thiết; các thread không tiếp tục chạy Java code tùy ý cho đến khi thao tác hoàn tất.

Sơ đồ đơn giản:

```text
Global safepoint (minh họa):
VM:       yêu cầu safepoint -> chờ A,B,C đạt trạng thái an toàn
Thread A: chạy -----------> [an toàn / chờ] ------------> chạy tiếp
Thread B: chạy ----------------> [an toàn / chờ] -------> chạy tiếp
Thread C: chạy -------> [an toàn / chờ] -----------------> chạy tiếp
VM:                         [thực hiện VM operation]
```

Đây là **mô hình khái niệm**, không phải timeline bắt buộc hay chính xác từng nhịp của mọi thuật toán GC/VM. Các thread có thể đang ở native, blocked hoặc các trạng thái khác được JVM đánh giá là safepoint-safe. Không hiểu global safepoint là “mọi thread OS luôn bị pause tại cùng đúng một instruction”.

Một global safepoint có chi phí **điều phối và chờ**; nếu thao tác thực sự chỉ cần quan sát/sửa trạng thái của **một** thread, việc đưa tất cả JavaThread vào safepoint có thể là quá rộng.

### 3.2. Handshake theo luồng: scope hẹp hơn

**JEP 312** bổ sung hạ tầng để VM có thể thực hiện callback cho **một hoặc một nhóm JavaThread** ở trạng thái an toàn, không luôn phải dùng một global VM safepoint.

```text
Thread-local handshake (minh họa, target=B):
VM:       yêu cầu operation cho B ----> operation hoàn tất
Thread A: chạy ----------------------------------------------> chạy
Thread B: chạy -> [safepoint-safe] -> [callback] -> chạy tiếp
Thread C: chạy ----------------------------------------------> chạy
```

Một handshake operation có thể được thực hiện bởi **target JavaThread** khi nó đạt điểm kiểm tra phù hợp, hoặc trong điều kiện an toàn do một **VM thread** xử lý trong lúc target bị chặn. Chi tiết thực thi phụ thuộc version, operation và trạng thái thread.

Không suy rằng:
- Target chắc chắn “không hề bị tạm dừng”;
- Callback là một `Runnable` mà code Java được phép đăng ký;
- VM không bao giờ cần global safepoint nữa;
- Một thread đang stuck/native/blocked sẽ luôn được xử lý tức thời;
- Từ lúc có JEP 312, mọi GC/JIT/thread dump đều được thực hiện bằng handshake;
- Hiệu năng mọi workload tăng một tỷ lệ cố định.

**Mục tiêu là thu hẹp phạm vi phối hợp khi khả thi**, không phải loại bỏ mọi pause hoặc mọi cơ chế global safepoint.

### 3.3. “Thread-local” trong handshake không có nghĩa đọc hoặc ghi `ThreadLocal`

VM có thể cần tiếp cận một trạng thái thread an toàn để thực hiện công việc nội bộ, chẳng hạn xử lý các khía cạnh liên quan thread stack hoặc trạng thái runtime theo cách implementation cho phép. Không vì tên “thread-local handshake” mà suy ra VM đang:

- gọi `ThreadLocal.get()`;
- chuyển `ThreadLocal` của thread A sang thread B;
- xóa `ThreadLocalMap` ở cuối request;
- bắt đầu hay kết thúc một transaction ứng dụng;
- tạo một “thread-local database connection”;
- thay đổi thứ tự message của chương trình;
- cung cấp một Java synchronization primitive mới cho người lập trình.

**JEP 312 là thay đổi trong VM**, không phải bản cập nhật ngữ nghĩa của `java.lang.ThreadLocal`.

### 3.4. Một handshake không giống tín hiệu mạng hay giao thức HTTP

“Handshake” còn xuất hiện trong TLS/HTTP/network. Ở đây, từ này chỉ **phối hợp giữa VM và JavaThread nội bộ**. Không có socket, TLS certificate, request/response hay khóa mạng liên quan trực tiếp đến JEP 312.

Khi đọc log, nên ghi rõ **HotSpot thread-local handshake** để tránh nhầm với một handshake giao thức mạng của ứng dụng.

## 4. Global safepoint, handshake và synchronization là ba việc khác

| Cơ chế | Đối tượng điều phối | Có API công khai cho ứng dụng? | Ví dụ nhu cầu |
| --- | --- | --- | --- |
| VM-wide safepoint | Nhiều JavaThread liên quan đến một tác vụ VM | Không yêu cầu application tự gọi để VM vận hành | Một số hoạt động thu gom bộ nhớ hoặc VM-level |
| HotSpot thread-local handshake | Một hay nhiều JavaThread ở trạng thái safepoint-safe | **Không** có `Thread.handshake()` trong Java SE | Công việc VM cần một luồng cụ thể |
| `synchronized` | Quyền vào critical section trên Java monitor | **Có** | Tránh race khi nhiều thread sửa cùng object |
| `Lock`/`ReentrantLock` | Khóa do ứng dụng kiểm soát | **Có** | Mutual exclusion và coordination ở tầng Java |
| `volatile` | Quy tắc visibility/order cho biến Java | **Có** | Công bố trạng thái và coordination theo Java Memory Model |
| `CountDownLatch` / `Phaser` | Phối hợp các task/threads Java | **Có** | Chờ nhóm tác vụ đến một mốc |
| `ThreadLocal<T>` | Liên kết giá trị với thread hiện tại | **Có** | Lưu request context hoặc bộ đệm riêng trong thread |
| `ScopedValue<T>` (JDK 25+) | Liên kết dữ liệu theo **dynamic scope** | **Có** từ JDK 25 | Truyền ngữ cảnh chỉ đọc xuống call chain |

**Ngộ nhận phổ biến:** “Vì JDK 10 có handshake nên ứng dụng không cần lock nữa.” Sai. Handshake là **nội bộ VM**, không cung cấp mutual exclusion hay happens-before giữa các lệnh `x++` trên hai thread của ứng dụng.

### 4.1. Ví dụ `counter++` vẫn là race

```java
// Mã minh họa KHÔNG thread-safe.
class BadCounter {
    int counter = 0;
    void addOne() {
        counter++;
    }
}
```

`counter++` là thao tác read-modify-write không nguyên tử. JEP 312 **không thay đổi** logic này. Khi cần tăng bộ đếm dùng chung, cân nhắc `AtomicInteger.incrementAndGet()`, lock hoặc một thiết kế không chia sẻ state phù hợp workload.

`ThreadLocal<Integer>` có thể tạo **một counter khác cho từng thread**, nhưng điều đó không giải quyết bài toán “đếm tổng số request toàn hệ thống” nếu bạn chưa định nghĩa cơ chế gộp dữ liệu và tính nhất quán.

## 5. `java.lang.ThreadLocal<T>` vận hành ra sao?

### 5.1. Một khóa ThreadLocal, nhiều giá trị theo thread

`ThreadLocal<T>` là **một object khóa** mà các thread khác nhau có thể cùng tham chiếu. Khi gọi `get()`, runtime tìm **giá trị của thread hiện tại** gắn với object khóa ấy.

```java
private static final ThreadLocal<String> REQUEST_ID =
        ThreadLocal.withInitial(() -> "UNSET");
```

Đây là **khai báo field trong class**, không phải chương trình hoàn chỉnh.

- `private static final`: class giữ **một tham chiếu đến khóa ThreadLocal**, không cho gán lại field.
- `ThreadLocal.withInitial`: mỗi thread chưa có giá trị, khi lần đầu gọi `get()`, có thể chạy supplier để tạo initial value.
- `REQUEST_ID.set("A")` ở thread A **không** sửa slot của thread B.
- `REQUEST_ID.get()` ở thread B trả **giá trị của B**, không phải mặc nhiên là "A".
- `REQUEST_ID.remove()` xóa **chỉ giá trị của thread hiện tại** cho khóa đó; những thread khác không bị xóa.

Sơ đồ:

```text
Một khóa:
     REQUEST_ID (ThreadLocal<String>, static final)
            |
            +-- Thread A -> "request-A"
            |
            +-- Thread B -> "request-B"
            |
            +-- main     -> "request-main"

A.set("new-A") không đổi B hoặc main.
A.remove() không xóa slot ở B hoặc main.
```

Đó là **per-thread value storage**, không phải VM handshake.

### 5.2. Các phương thức cần nắm

| API | Hợp đồng chính | Cạm bẫy |
| --- | --- | --- |
| `new ThreadLocal<>()` | Tạo khóa với initial value mặc định `null` | `get()` có thể trả `null` nếu chưa `set` |
| `ThreadLocal.withInitial(supplier)` | Tạo khóa có initial value từ supplier | Supplier có thể được gọi **trên từng thread**, và gọi lại sau `remove` |
| `get()` | Đọc giá trị của thread hiện tại; init nếu chưa có | Không “đọc giá trị của thread khác” |
| `set(value)` | Gắn giá trị vào thread hiện tại | Không có scope auto-cleanup |
| `remove()` | Xóa giá trị của thread hiện tại | Sau đó `get()` có thể chạy initial supplier lần nữa |
| `InheritableThreadLocal<T>` | Có thể kế thừa giá trị khi thread con **được tạo** | Không phải truyền context tự động qua task pool |

Javadoc `ThreadLocal` còn dùng ví dụ request ID/transaction ID và mô tả giá trị per-thread có vòng đời ít nhất trong khi thread còn sống và entry còn accessible. Phần quan trọng cho vận hành là **thread pool thường sống lâu hơn request**, nên `finally { threadLocal.remove(); }` là thực hành hữu ích khi bạn kiểm soát mã đặt giá trị.

### 5.3. Giá trị riêng theo thread không đồng nghĩa object bên dưới là bản sao sâu

`ThreadLocal<List<String>>` có thể cung cấp một **tham chiếu List** cho mỗi thread, nhưng nếu supplier hoặc code gán **cùng một List object** cho nhiều thread, những thread đó vẫn chia sẻ object mutable.

Ví dụ phản mẫu:

```java
// MÃ MINH HỌA SAI: mỗi thread nhận cùng một đối tượng list.
static final java.util.List<String> SHARED =
        new java.util.ArrayList<>();

static final ThreadLocal<java.util.List<String>> WRONG =
        ThreadLocal.withInitial(() -> SHARED);
```

`WRONG` có slot per-thread, nhưng mỗi slot có thể trỏ đến cùng `SHARED`; một thread thêm phần tử vào `SHARED` vẫn ảnh hưởng những thread khác.

Cách dùng tốt hơn nếu thật sự cần buffer riêng:

```java
static final ThreadLocal<StringBuilder> BUFFER =
        ThreadLocal.withInitial(StringBuilder::new);
```

Điều này cấp **StringBuilder mới khi một thread khởi tạo slot**, không phải một bản sao theo mỗi task. Nếu worker thread sống lâu, `StringBuilder` có thể giữ capacity lớn sau request; cân nhắc `remove` hoặc dùng biến cục bộ thay vì giữ buffer quá lâu.

## 6. Tình huống thực tế: context của request và thread pool

### 6.1. Vì sao thread pool gây lỗi “dính request trước”?

`ExecutorService` thường tái sử dụng cùng platform thread để chạy nhiều task nối tiếp. Ví dụ:

```text
Một worker thread xử lý:
Task 1 -> REQUEST_ID.set("alice") -> kết thúc mà KHÔNG remove
Task 2 -> REQUEST_ID.get()         -> thấy "alice" (giá trị cũ)
Task 3 -> ...
```

Đó là **context leakage giữa tác vụ**, có thể làm sai log/tracing, tenant isolation hoặc phân quyền nếu code sử dụng context này như nguồn quyết định tin cậy.

**JEP 312 không tự xử lý chuyện đó.** HotSpot handshake không biết “request vừa kết thúc” theo semantics nghiệp vụ và không có hợp đồng gọi `ThreadLocal.remove` cho ứng dụng.

### 6.2. Pattern an toàn: set + try/finally + remove

```java
static final ThreadLocal<String> REQUEST =
        ThreadLocal.withInitial(() -> "UNSET");

static void processOneRequest(String requestId) {
    REQUEST.set(requestId);
    try {
        doBusinessWork(); // đọc REQUEST.get() trong cùng thread
    } finally {
        REQUEST.remove();
    }
}
```

**Đây là đoạn minh họa trong class**, cần định nghĩa `doBusinessWork` để biên dịch độc lập. `finally` vẫn chạy nếu `doBusinessWork` ném exception thường; nó giúp tránh giữ trạng thái request ở worker thread được dùng lại. Nếu một luồng đã có giá trị **của scope cha** trước đó, mã này **xóa giá trị cha** thay vì khôi phục; khi có nested scopes hãy thiết kế rõ chính sách `save/restore` hoặc cân nhắc `ScopedValue` cho ngữ cảnh chỉ đọc.

Không đặt `remove()` chỉ trong nhánh success. Exception và cancellation cũng là lúc cần cleanup; nếu task dừng trong trạng thái không thể thực thi Java cleanup (ví dụ process bị kill), không nên hứa `finally` có thể giải quyết mọi shutdown.

### 6.3. Tại sao `ThreadLocal` không tự lan qua `CompletableFuture`?

Một chuỗi `CompletableFuture.supplyAsync(...)` có thể được chạy trên một pool khác và một thread khác. `ThreadLocal` **không tự chuyển** giá trị của thread submit task sang worker thread.

Ví dụ:

```java
// MÃ MINH HỌA trong method: không được dựa vào context propagation.
REQUEST.set("request-123");
java.util.concurrent.CompletableFuture<String> future =
        java.util.concurrent.CompletableFuture.supplyAsync(
                () -> REQUEST.get()
        );
```

`future` không được Java SE cam kết đọc `"request-123"`. Nó sẽ đọc slot của thread được executor sử dụng, có thể là initial value hoặc một giá trị tồn tại từ trước. Đừng giải thích “JDK 10 handshake sẽ chuyển request ID qua task”; đó hoàn toàn là hai cơ chế khác nhau.

Nếu application framework hỗ trợ propagation có chủ đích, dùng contract của framework hoặc **truyền ngữ cảnh làm tham số** vào task. Với request context chỉ đọc trên JDK 25+, `ScopedValue` có thể đơn giản hóa một số trường hợp nhưng **không tự chuyển qua mọi executor tùy ý**.

### 6.4. Không dùng ThreadLocal làm kho dữ liệu toàn hệ thống

Nếu mục đích là:
- đếm tổng số request toàn ứng dụng;
- lưu cấu hình dùng chung;
- cache toàn JVM có consistency;
- trao đổi message giữa hai threads;

`ThreadLocal` thường không phù hợp: nó tách dữ liệu theo thread thay vì chia sẻ state có kiểm soát. Dùng đối tượng immutable công bố an toàn, concurrent collections, atomic types, queue hoặc service lưu trữ theo thiết kế hệ thống.

## 7. Java lab hoàn chỉnh: phân biệt per-thread state và handshake

Lab sử dụng **Java 17+ public APIs**, không dùng reflection vào HotSpot, `Unsafe` hay JNI. Nó chứng minh chính xác các hành vi:
- Main giữ `request-main`.
- Hai executor có worker thread riêng nên mỗi worker đọc initial value `UNSET`.
- Worker A và B lưu request ID khác nhau.
- Worker A được tái sử dụng nhưng không giữ context cũ khi `remove` trong `finally`.
- Cố tình quên `remove` ở một task sẽ tạo **contamination** ở task tiếp theo trên cùng worker.
- `ThreadLocal` thường không kế thừa sang thread con; `InheritableThreadLocal` có thể kế thừa ở lúc tạo child thread.
- Lab **không thể và không cố** trực tiếp gọi VM thread-local handshake.

### 7.1. Tệp `ThreadLocalVsHandshakeLab.java`

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ThreadLocalVsHandshakeLab {
    private static final ThreadLocal<String> CONTEXT =
            ThreadLocal.withInitial(() -> "UNSET");

    private static final InheritableThreadLocal<String> INHERITED =
            new InheritableThreadLocal<>();

    record Snapshot(String before, String inside, String after) {
    }

    static String businessHelper() {
        return CONTEXT.get();
    }

    static Snapshot handle(String request) {
        String before = CONTEXT.get();
        String inside;

        try {
            CONTEXT.set(request);
            inside = businessHelper();
        } finally {
            CONTEXT.remove();
        }

        return new Snapshot(before, inside, CONTEXT.get());
    }

    static void printSnapshot(String label, Snapshot s) {
        System.out.println(label + " before: " + s.before());
        System.out.println(label + " inside: " + s.inside());
        System.out.println(label + " after remove: " + s.after());
    }

    public static void main(String[] args) throws Exception {
        CONTEXT.set("request-main");

        // Mỗi single-thread executor có worker thread riêng.
        ExecutorService a = Executors.newSingleThreadExecutor();
        ExecutorService b = Executors.newSingleThreadExecutor();

        try {
            Future<Snapshot> one =
                    a.submit(() -> handle("request-A"));
            Future<Snapshot> two =
                    b.submit(() -> handle("request-B"));

            Snapshot first = one.get();
            Snapshot second = two.get();

            // Task thứ hai của A dùng lại cùng worker thread A.
            Snapshot reused =
                    a.submit(() -> handle("request-C")).get();

            // Chỉ main in kết quả, tránh thứ tự stdout không xác định.
            System.out.println("main initial: " + CONTEXT.get());
            printSnapshot("worker A", first);
            printSnapshot("worker B", second);
            printSnapshot("worker A reused", reused);
            System.out.println("main still: " + CONTEXT.get());

            // MINH HỌA LỖI: cố ý quên remove() trong một task.
            a.submit(() -> CONTEXT.set("LEAKED-A")).get();

            // Task sau đọc thấy giá trị để sót trên cùng worker.
            String contaminated = a.submit(() -> {
                String seen = CONTEXT.get();
                CONTEXT.remove(); // Dọn ngay sau khi chứng minh lỗi.
                return seen;
            }).get();

            System.out.println(
                    "pool contamination before cleanup: "
                            + contaminated);
            System.out.println("pool after cleanup: "
                    + a.submit(() -> CONTEXT.get()).get());

            // Child thread mới: ThreadLocal thường KHÔNG được kế thừa.
            INHERITED.set("parent-label");
            AtomicReference<String> plainInChild =
                    new AtomicReference<>();
            AtomicReference<String> inheritedInChild =
                    new AtomicReference<>();

            Thread child = new Thread(() -> {
                plainInChild.set(CONTEXT.get());
                inheritedInChild.set(INHERITED.get());
            });

            child.start();
            child.join();

            System.out.println("child plain ThreadLocal: "
                    + plainInChild.get());
            System.out.println("child inherited label: "
                    + inheritedInChild.get());
        } finally {
            INHERITED.remove();
            CONTEXT.remove();
            a.shutdown();
            b.shutdown();

            if (!a.awaitTermination(5, TimeUnit.SECONDS)) {
                a.shutdownNow();
            }
            if (!b.awaitTermination(5, TimeUnit.SECONDS)) {
                b.shutdownNow();
            }
        }

        System.out.println(
                "main after cleanup: " + CONTEXT.get());
    }
}
```

### 7.2. Biên dịch và chạy

Sử dụng **JDK 17+** được hỗ trợ/cập nhật bảo mật; không cần JDK 10 cũ:

```bash
javac ThreadLocalVsHandshakeLab.java
java ThreadLocalVsHandshakeLab
```

Code dùng `record` từ Java 16, `ExecutorService` và `ThreadLocal` public. Không có phụ thuộc Maven/Gradle hay thư viện ngoài.

### 7.3. Stdout chính xác: 16 dòng

```text
main initial: request-main
worker A before: UNSET
worker A inside: request-A
worker A after remove: UNSET
worker B before: UNSET
worker B inside: request-B
worker B after remove: UNSET
worker A reused before: UNSET
worker A reused inside: request-C
worker A reused after remove: UNSET
main still: request-main
pool contamination before cleanup: LEAKED-A
pool after cleanup: UNSET
child plain ThreadLocal: UNSET
child inherited label: parent-label
main after cleanup: UNSET
```

Đây là **16 dòng đã kiểm thử** với JDK hiện đại. Các thread có thể hoàn tất theo thứ tự khác nhau bên trong executor, nhưng **main đợi các `Future.get()` và chỉ main in snapshot**, nên thứ tự 16 dòng không phụ thuộc thứ tự scheduling. Trường hợp contamination cũng xác định vì `newSingleThreadExecutor` bảo đảm các task của executor A chạy tuần tự trên một worker, và chương trình cố tình không cleanup giữa hai task đó.

### 7.4. Phân tích output theo tình huống

**Main khác hai workers:** `main initial` là `request-main`. `worker A/B before` đều `UNSET` vì `ThreadLocal` thường không kế thừa từ main. Worker A lưu `request-A`, worker B lưu `request-B`; hai giá trị này không đè nhau.

**Sau `remove`:** `worker A after remove` và `worker B after remove` đều `UNSET`. Trong lab, gọi `get` sau `remove` sẽ kích hoạt supplier của `withInitial` trả lại `UNSET`. Đừng ngộ nhận `remove` có nghĩa `get()` sau đó bắt buộc trả null; còn tùy initial value.

**Task thứ hai của worker A:** dòng `worker A reused before: UNSET` cho thấy task sau không thấy `request-A` vì handler trước đã cleanup. Đây là lifecycle theo **task**, được ứng dụng tự đảm bảo, không phải do JVM handshake dọn.

**Lỗi contamination:** task đặc biệt `CONTEXT.set("LEAKED-A")` cố ý thiếu `finally`. Task tiếp theo trên **cùng một worker A** thấy `LEAKED-A`, sau đó gọi `remove`, nên dòng kế tiếp trở lại `UNSET`. Không bao giờ cố tình thiếu cleanup như vậy trong production.

**Main không bị thay đổi:** `main still: request-main` vì worker A/B không sửa slot ThreadLocal của main.

**Thread con:** thread mới được tạo từ main **không tự kế thừa** giá trị `CONTEXT` thông thường, nên dòng `child plain ThreadLocal: UNSET`. `INHERITED` là một `InheritableThreadLocal`; nó có `parent-label` vào lúc child thread được tạo, nên child đọc giá trị đó.

**Main sau cleanup:** `main after cleanup: UNSET`; sau `CONTEXT.remove`, lần `get` cuối sẽ tạo lại initial value. Đây là output của API `ThreadLocal`, **không phải số liệu quan sát VM handshake**.

### 7.5. Vì sao dùng `try/finally` và `Future.get()`?

- `try/finally` trong `handle` đặt nghĩa rõ “một request sở hữu context trong scope xử lý, xóa khi kết thúc”.
- `Future.get()` đợi tác vụ và đưa kết quả về main để in thứ tự ổn định. Nó **không** biến thread-local data thành dữ liệu global; giá trị được truyền lại bằng **đối tượng `Snapshot` trả về**.
- `shutdown`/`awaitTermination` giải phóng executor để demo không để thread pool tồn tại vô thời hạn.
- `AtomicReference` chỉ dùng để nhận giá trị child sau `join`; nó không phải cách JVM handshake chia sẻ context.
- `ThreadLocal.withInitial` đảm bảo trạng thái ban đầu có thể dự đoán trong ví dụ, không yêu cầu mọi ứng dụng phải dùng sentinel `"UNSET"`.

## 8. Vòng đời ThreadLocal: cleanup, nesting và rò rỉ bộ nhớ

### 8.1. Vì sao giá trị có thể tồn tại lâu hơn request?

Theo Javadoc, thread giữ một bản sao giá trị của `ThreadLocal` khi thread còn sống và entry còn accessible. Thread pool thường giữ platform thread qua hàng nghìn request. Nếu code đặt một object lớn vào `ThreadLocal` rồi không remove, object ấy có thể được giữ lại lâu hơn scope nghiệp vụ.

**Hai hậu quả cần phân biệt:**

1. **Context contamination:** request B đọc dữ liệu của request A trên worker được tái sử dụng, có thể gây lỗi logic/bảo mật.
2. **Memory retention:** một object, cache, buffer hoặc session context lớn tiếp tục được giữ qua thời gian dài, gây tăng footprint.

Không phải **mọi** use of `ThreadLocal` đều là memory leak. Một cache riêng cho worker có thể được thiết kế giữ lâu có chủ đích; vấn đề là **lifetime của value không phù hợp lifetime dữ liệu**. Nhưng không được dựa vào VM handshake để tự dọn giá trị vô chủ.

### 8.2. Trường hợp nested scopes không nên xóa context cha

Nếu application có:

```text
Outer request context = A
    |
    +-- inner operation tạm đổi context = B
    |
Outer cần tiếp tục thấy context = A
```

thì inner gọi `remove` rồi return sẽ **không tự khôi phục A**. Một hướng xử lý khi buộc dùng `ThreadLocal` là lưu giá trị trước khi đổi rồi khôi phục trong `finally`:

```java
String previous = CONTEXT.get();
CONTEXT.set("inner-context");
try {
    doInnerWork();
} finally {
    CONTEXT.set(previous);
}
```

Đây là **mã minh họa đặt trong class có `CONTEXT` và `doInnerWork`**. Nó đúng nếu ứng dụng chủ ý coi `previous` là giá trị cần khôi phục, nhưng **không phân biệt** trạng thái “chưa có entry” và “entry có giá trị initial giống previous”. Khi cần biểu diễn chính xác “absent vs present”, phải thiết kế context wrapper/lifecycle phù hợp. Với ngữ cảnh **chỉ đọc** trên JDK 25+, `ScopedValue` tránh một số rủi ro reassign/cleanup.

### 8.3. Không giữ thông tin nhạy cảm lâu hơn cần thiết

Đừng đặt mật khẩu, access token, dữ liệu tenant hoặc thông tin nhạy cảm trong `ThreadLocal` rồi giả định JVM sẽ tự xóa an toàn khi request kết thúc. `remove()` giúp bỏ tham chiếu trong thread hiện tại nhưng không cam kết xóa byte trong heap, stack, log hay core dump. Cần áp dụng nguyên tắc tối thiểu hóa dữ liệu, vòng đời ngắn, phân quyền và policy bảo mật của ứng dụng.

Một **request ID không bí mật** là ví dụ dễ hiểu hơn cho bài học; production phải xem thông tin nào được phép lưu/log và bao lâu.

### 8.4. Không thao tác ThreadLocal của thread khác bằng cách “chuyển sang handshake”

Public `ThreadLocal.get/set/remove` thao tác trên **thread đang gọi**. Không có API Java SE `ThreadLocal.removeFrom(otherThread)` cho mục đích này. Handshake nội bộ VM **không** cung cấp quyền sửa các biến ứng dụng thuộc thread khác.

Nếu cần cleanup theo task, đặt logic cleanup **bên trong chính task chạy trên worker**, hoặc dùng framework quản lý context theo request với hợp đồng rõ ràng.

## 9. `InheritableThreadLocal` không phải cơ chế truyền mọi task

`InheritableThreadLocal<T>` mở rộng `ThreadLocal<T>` để giá trị từ parent có thể được kế thừa khi **tạo** child thread. Mặc định, child thường có **cùng tham chiếu value** với parent; nếu muốn biến đổi có thể override `childValue`.

### 9.1. Khác biệt tại thời điểm tạo child

Ví dụ:

```java
static final InheritableThreadLocal<String> LABEL =
        new InheritableThreadLocal<>();

LABEL.set("parent");
Thread child = new Thread(() -> {
    System.out.println(LABEL.get());  // Có thể là "parent".
});
child.start();
child.join();
LABEL.remove();
```

Đây là **mã minh họa trong phương thức/class**; muốn chạy độc lập phải thêm class, `main throws Exception` hoặc xử lý `InterruptedException`.

### 9.2. Với thread pool, thời điểm tạo worker khác thời điểm submit task

Một `ExecutorService` có thể đã tạo worker thread trước khi request đến. Sau đó parent sửa `InheritableThreadLocal` tại lúc submit, **không có nghĩa** worker sẵn có tự nhận giá trị mới. Worker có thể kế thừa một value tại thời điểm thread **ban đầu được tạo**, rồi dùng nó cho các task đến sau, gây hiểu nhầm hoặc lộ context.

Đừng dùng `InheritableThreadLocal` để truyền principal/request context qua mọi thread pool mà không có framework propagation contract rõ ràng.

### 9.3. Kế thừa một object mutable có thể chia sẻ tham chiếu

Nếu parent đặt một `ArrayList` mutable vào `InheritableThreadLocal`, child có thể nhận **cùng một object reference**. Điều đó không tự bảo đảm thread safety. Nếu cần truyền dữ liệu, ưu tiên snapshot immutable, copy dữ liệu hoặc cơ chế synchronization phù hợp.

## 10. Virtual threads và ScopedValue trên JDK hiện đại

### 10.1. Virtual threads (JDK 21+) vẫn có ThreadLocal, nhưng đừng nhầm tầng VM

Theo Java SE 25, **virtual thread** là một Java `Thread` được JVM scheduling trên một tập **carrier platform threads**. Khi code chạy bên trong virtual thread gọi `Thread.currentThread()`, kết quả là object **virtual thread**, không phải một API để lấy carrier và tùy ý sửa state của carrier.

`ThreadLocal` vẫn được **hỗ trợ** trên virtual threads, nhưng:
- Số lượng virtual threads có thể rất lớn; một value lớn được cấp cho **mỗi** virtual thread có thể tốn bộ nhớ.
- Không sử dụng `ThreadLocal` như một thủ thuật “pin request vào đúng OS thread”.
- Virtual thread có thể mount/unmount lên carrier khác; không xem thread-local handshake của **HotSpot JavaThread nội bộ** là lời hứa rằng ứng dụng có thể trực tiếp điều khiển mọi virtual thread qua một callback.
- Không suy ra `ThreadLocal` của virtual thread tự gắn vào carrier và chảy sang virtual thread khác.

**Nói đúng tầng:** JEP 312 mô tả hạ tầng phối hợp với **HotSpot JavaThread**; còn `java.lang.Thread` ngày nay có cả platform threads và virtual threads. Hai mô hình không nhất thiết có ánh xạ một-một, và Java SE public API không bộc lộ thao tác handshake này cho ứng dụng.

### 10.2. ScopedValue là lựa chọn hiện đại cho context chỉ đọc (JDK 25+)

**JEP 506** đưa `ScopedValue` thành API final từ **JDK 25**, hướng tới việc truyền **dữ liệu ngữ cảnh không bị gán lại tùy ý** xuống call chain trong dynamic scope, thường hữu ích hơn `ThreadLocal` khi context chỉ cần đọc.

Ví dụ **chỉ biên dịch/chạy trên JDK 25+**, không phải phần của lab Java 17:

```java
public class ScopedRequestExample {
    private static final ScopedValue<String> REQUEST =
            ScopedValue.newInstance();

    static void businessHelper() {
        System.out.println(REQUEST.get());
    }

    public static void main(String[] args) {
        ScopedValue.where(REQUEST, "request-42")
                .run(ScopedRequestExample::businessHelper);
        // Sau run(), binding ngoài scope này không còn hiệu lực.
    }
}
```

Kết quả khi chạy trên JDK 25+:

```text
request-42
```

- `ScopedValue.where(...).run(...)` tạo **binding có thời hạn theo scope thực thi**.
- Code ở xa trong cùng call chain có thể dùng `REQUEST.get()` khi binding còn hiệu lực.
- Khi scope kết thúc bình thường hoặc do exception, binding được tháo theo hợp đồng; không cần code tự `remove()` như `ThreadLocal`.
- API cho phép **nested rebinding** theo scope, khôi phục binding cha sau khi inner scope kết thúc.
- Muốn truyền binding qua child thread, phải theo **mô hình structured task** mà API hỗ trợ; **không** tự kỳ vọng propagation qua mọi executor bất kỳ.
- Đối tượng được bound vẫn phải được đối xử an toàn nếu mutable; “không thể gán lại binding từ callee” **không** tự biến object thành immutable.

**Không dùng `ScopedValue` chỉ vì tên có “scope” để giải thích JEP 312:** đây vẫn là **API truyền ngữ cảnh của ứng dụng**, không phải công cụ kích hoạt VM handshake.

### 10.3. Chọn ThreadLocal, ScopedValue hay tham số method?

| Nhu cầu | Lựa chọn nên xem xét | Lưu ý |
| --- | --- | --- |
| Một request ID chỉ đọc xuyên call chain trên JDK 25+ | `ScopedValue` hoặc tham số explicit | Lifetime rõ, ít rủi ro quên cleanup |
| Dữ liệu mutable riêng cho một worker thread trong thời gian dài có kiểm soát | `ThreadLocal` | Có thiết kế vòng đời và cleanup |
| Truyền dữ liệu tới một service khác trong cùng JVM | Tham số method/object context | Rõ nguồn và ownership |
| Truyền context tới task của executor khác | Tham số được capture hoặc propagation của framework | `ThreadLocal` thường không tự đi theo |
| Đồng bộ đối tượng shared giữa nhiều threads | Locks, atomics, concurrent collections | Không phải `ThreadLocal` hoặc handshake |
| Điều khiển VM ở safepoint-safe state | **Do HotSpot quyết định** | Không có public Java application API cho JEP 312 |

`ThreadLocal` **chưa bị xóa khỏi Java SE hoặc vô hiệu hóa** khi có `ScopedValue`. Lựa chọn phụ thuộc đặc điểm dữ liệu và phiên bản JDK tối thiểu mà sản phẩm thật sự hỗ trợ.

## 11. Chẩn đoán: khi nào quan sát handshake, khi nào debug ThreadLocal?

### 11.1. Vấn đề VM latency / safepoint

Nếu ứng dụng gặp pause dài và nghi nguyên nhân do VM coordination, hãy:
- Ghi chính xác **JDK distribution/build**, GC, flags, OS, CPU quota và workload.
- Khảo sát unified logging của HotSpot với các tag còn hỗ trợ trên bản đang chạy.
- Để xem các tag thực sự có thể sử dụng, chạy:

```bash
java -Xlog:help
```

- Một dạng log thường dùng cho **global safepoint** trên HotSpot:

```bash
java -Xlog:safepoint=info -jar application.jar
```

Đây là **template yêu cầu có file `application.jar` phù hợp**. Log `safepoint` giúp quan sát một số hoạt động safepoint nhưng **không** có nghĩa mọi thread-local handshake đều sẽ được báo thành một global safepoint event. Đừng kiểm tra “không thấy log safepoint” rồi kết luận “JVM đã không làm gì hoặc không thể có handshake”.

Tùy phiên bản, có thể có các tag/diagnostics riêng cho handshake. Hãy xem `-Xlog:help` và JDK documentation của runtime đang chạy; **không bịa tên tag/cờ cụ thể** để buộc ứng dụng gọi handshake. Tài liệu JEP/HotSpot source hoặc JFR diagnostics có thể hữu ích cho chuyên gia VM, nhưng các event/implementation detail không phải hợp đồng Java SE public.

### 11.2. Vấn đề request ID hoặc tenant “nhảy” giữa task

Nếu triệu chứng là:
- request A xuất hiện ID của request B trong log;
- worker reuse đọc một object của task trước;
- memory giữ lại một context rất lớn dù request đã xong;

thì kiểm tra **mã ứng dụng và framework**:
1. Có `ThreadLocal.set(...)` được gọi không?
2. Có `remove()` trong `finally` ở boundary đủ rộng không?
3. Có nested scope gây mất context cha không?
4. Có async/ExecutorService boundary chuyển sang thread khác không?
5. Có sử dụng `InheritableThreadLocal` không phù hợp với pool không?
6. Có shared mutable value ở nhiều thread-local slots không?
7. Có test chắc chắn cho pool reuse không?

Đây là lỗi **lifecycle/context propagation** của ứng dụng. Không tìm cách “tuning HotSpot handshake” để chữa việc thiếu `remove`.

### 11.3. Công cụ nào kiểm tra điều gì?

| Công cụ/phương pháp | Phù hợp cho | Không tự chứng minh |
| --- | --- | --- |
| `-Xlog:safepoint=info` | Hoạt động global safepoint theo log HotSpot | Mọi thread-local handshake và ThreadLocal value |
| `java -Xlog:help` | Những unified log tags hợp lệ trên JVM này | Kết quả performance tốt/xấu |
| JFR recordings | Sự kiện VM/JVM và một số runtime activities theo version/config | Nội dung mọi `ThreadLocal` ứng dụng |
| `jcmd <pid> Thread.print` | Thread dumps và stack traces theo HotSpot support | Mọi giá trị `ThreadLocal` hiện có |
| Unit tests với executor reuse | Bug context rò qua task, cleanup đúng | JVM đã thực thi bao nhiêu handshake |
| Structured logs + request IDs | Tính đúng đắn của context nghiệp vụ | Giao thức safepoint nội bộ |
| Heap analysis nếu được phép | Nguồn memory retention liên quan object | Nguyên nhân VM pause nếu chỉ xem một snapshot |

Đừng ghi toàn bộ secret/token trong `ThreadLocal` vào log chỉ để debug. Có thể kiểm thử với request ID giả lập và dữ liệu nhạy cảm đã được redaction.

## 12. Tại sao JEP 312 không thay đổi Java Memory Model hay API ThreadLocal?

JEP 312 nói về **nội bộ JVM** khi nó cần thực hiện các thao tác ở trạng thái luồng đủ an toàn. Nó **không** sửa hợp đồng synchronization của Java:

- `volatile` vẫn cần khi dùng một shared flag mà nhiều threads đọc/ghi theo JMM.
- `synchronized`, `Lock` và các atomic classes vẫn là công cụ tương ứng cho mutual exclusion/visibility.
- `ThreadLocal` vẫn cung cấp per-thread slots, không phải shared-memory communication.
- `Future.get()`, `Thread.join()`, executor/task boundaries có hợp đồng đồng bộ riêng; không suy ra chúng dùng một handshake của VM mà ứng dụng điều khiển được.
- `Thread.sleep()`, `Thread.yield()` hoặc `Object.wait()` **không** phải một API “yêu cầu JEP 312 handshake”.
- `Thread.onSpinWait()` chỉ là spin-wait hint, không tự làm chương trình ngừng cho handshake hay thay Java synchronization.
- Virtual threads được scheduling bởi runtime, nhưng không làm `ThreadLocal` thành bản sao của HotSpot handshake state.

### 12.1. Ví dụ sử dụng concurrent collections

Nếu muốn nhiều threads cùng cập nhật một map request-count:

```java
java.util.concurrent.ConcurrentHashMap<String,
        java.util.concurrent.atomic.LongAdder> counts =
        new java.util.concurrent.ConcurrentHashMap<>();

counts.computeIfAbsent("endpoint-A",
        key -> new java.util.concurrent.atomic.LongAdder())
        .increment();
```

Đây là ví dụ **dùng API public** cho shared counters. Nó không yêu cầu truy cập internal handshake và không sử dụng `ThreadLocal` để “lưu chung” bản đồ đếm.

### 12.2. Per-thread không có nghĩa “không có race” với object được giữ chung

Nếu A và B cùng `ThreadLocal.set(sharedObject)` thì A/B có **entry riêng**, nhưng cùng reference object. Nếu object mutable không có synchronization, các phép ghi có thể race.

Một cách test:
- Dùng `ThreadLocal.withInitial(ArrayList::new)` để mỗi thread nhận object riêng.
- Hoặc dùng một immutable record/config snapshot và không mutate.
- Nếu thật sự cần chia sẻ object mutable, thiết kế synchronization theo JMM.

**Handshake nội bộ không bảo vệ một `ArrayList` dùng chung.**

## 13. Các lỗi hay gặp — đối chiếu nhanh

| Nhận định sai | Vì sao sai | Cách nói/thiết kế đúng |
| --- | --- | --- |
| “Java 10 thêm `ThreadLocal`” | `ThreadLocal` có từ Java 1.2 | Java 10 thêm **VM Thread-Local Handshakes (JEP 312)** |
| “Gọi `ThreadLocal.get()` tức thực hiện handshake” | Đây chỉ là API đọc slot của thread hiện tại | Không có public handshake call tương ứng |
| “Handshake xóa request ID khi task kết thúc” | VM không biết lifecycle request | `remove`/scoped context do app quản lý |
| “`static final ThreadLocal` là một value global” | Static field giữ key; slots là per thread | Mỗi thread đọc/ghi value riêng |
| “Worker B sẽ thấy A.set(...)” | Không tự chia sẻ per-thread state | Truyền context rõ ràng qua task nếu cần |
| “Handshake thay được `synchronized`/`volatile`” | Không phải ứng dụng synchronization API | Dùng JMM primitives phù hợp |
| “`remove()` khiến `get()` mãi trả null” | `withInitial` có thể reinitialize | Hiểu contract của `initialValue` |
| “Gửi `CompletableFuture` là tự truyền ThreadLocal” | Executor có thể dùng thread khác | Context propagation explicit/framework |
| “`InheritableThreadLocal` luôn truyền mỗi request” | Chỉ kế thừa khi tạo child thread, pool reuse khác | Tránh dùng nó làm propagation mặc định |
| “ThreadLocal khiến mọi object trong nó thread-safe” | Các slot có thể chứa cùng mutable reference | Không share mutable object thiếu synchronization |
| “Global safepoint không còn tồn tại từ JDK 10” | VM vẫn dùng khi operation cần | Handshake chỉ thu hẹp một số trường hợp |
| “Handshake không pause bất kỳ thread nào” | Target cần trạng thái an toàn, có thể bị chặn | Không cam kết zero-pause |
| “`-Xlog:safepoint` đo tất cả handshake” | Đó là log về safepoint theo tag/version | Kiểm tra diagnostics hỗ trợ và scope event |
| “Virtual thread luôn có một carrier cố định” | Có thể mount/unmount và đổi carrier | Không dựa vào carrier thread identity |
| “`ScopedValue` là API của JEP 312” | `ScopedValue` là Java API JDK 25 (JEP 506) | Phân biệt phạm vi và lịch sử |
| “`ScopedValue` thay thế mọi use case ThreadLocal” | Scoped value hướng tới ngữ cảnh scope/read-only | ThreadLocal còn phù hợp với một số per-thread mutable state |
| “Nhìn thread dump là đọc được mọi ThreadLocal value” | Thread dumps chủ yếu mô tả stack/trạng thái | Dùng instrumentation an toàn ở app |
| “Task pool không có leak vì các task đã kết thúc” | Worker thread tiếp tục sống | Cleanup trong task boundary bằng `finally` |

## 14. Bài tập tự luyện có đáp án

### Bài 1 — Xác định API Java 10

**Đề:** JEP 312 đưa class `java.lang.ThreadLocal` vào JDK 10 phải không?

**Đáp án:** Không. `ThreadLocal` có từ Java 1.2. JEP 312 bổ sung **HotSpot thread-local handshakes** để phối hợp VM operations mà không luôn cần global safepoint.

### Bài 2 — “Local” đang chỉ điều gì?

**Đề:** Trong hai câu “thread-local handshake” và “ThreadLocal value”, thread-local có đồng nghĩa với cùng một cơ chế lưu trữ dữ liệu không?

**Đáp án:** Không. Handshake là phạm vi VM phối hợp với thread; `ThreadLocal` là bản đồ giá trị ứng dụng theo thread.

### Bài 3 — Đọc giá trị trên hai workers

**Đề:** A gọi `CONTEXT.set("A")`, B chưa từng gọi `set`, cùng khóa tạo bằng `withInitial(() -> "UNSET")`. B.get() trả gì?

**Đáp án:** Trả `UNSET` nếu B chưa có slot và supplier hợp lệ. Không trả `A`, vì A/B có slot riêng.

### Bài 4 — Ngữ nghĩa `static final`

**Đề:** Tại sao `static final ThreadLocal<String> CONTEXT` không khiến mọi thread đọc cùng một `String`?

**Đáp án:** `static final` giữ một reference key duy nhất trong class, nhưng các value được gắn theo **thread hiện tại**. Không phải một biến static String global.

### Bài 5 — Reinitialization sau remove

**Đề:** Với `ThreadLocal.withInitial(() -> "EMPTY")`, sau `set("X");remove();get();` kết quả là gì?

**Đáp án:** `EMPTY`, vì `remove` xóa entry của thread hiện tại; `get` sau đó khởi tạo lại bằng supplier.

### Bài 6 — Task pool contamination

**Đề:** Task 1 set request ID nhưng không remove; Task 2 chạy trên **đúng worker thread đó** và gọi get. Có thể thấy ID cũ không?

**Đáp án:** Có. Đó là leak state giữa task do thread reuse, không phải handshake. Dùng `try/finally remove` trong task boundary hoặc context mechanism có lifecycle rõ.

### Bài 7 — Hai thread và mutable object chung

**Đề:** A/B đều giữ chung một `ArrayList` qua các slot ThreadLocal riêng. Có thread-safe không?

**Đáp án:** Không tự động. Các slot giữ cùng reference; phải tránh share mutable object hoặc dùng synchronization/concurrent structure phù hợp.

### Bài 8 — VM handshake có thay lock?

**Đề:** Một shared `int counter` được hai threads tăng bằng `counter++`. JEP 312 có bảo đảm không race?

**Đáp án:** Không. Sử dụng atomic counter hoặc lock theo Java Memory Model. Handshake nội bộ VM không biến read-modify-write thành atomic.

### Bài 9 — Global safepoint còn cần không?

**Đề:** Từ JDK 10 mọi hoạt động VM đều có thể dùng một handshake thay cho global safepoint?

**Đáp án:** Không. Một số công việc vẫn cần coordination toàn VM hoặc theo cơ chế khác. Handshake chỉ giúp thu hẹp phạm vi khi phù hợp.

### Bài 10 — Ai thực thi callback của handshake?

**Đề:** Callback VM handshake nhất thiết phải là một Java `Runnable` do target thread gọi không?

**Đáp án:** Không. Nó là VM-internal operation; theo JEP/HotSpot, có thể được thực hiện bởi target JavaThread hoặc VM thread khi target ở trạng thái an toàn theo điều kiện triển khai. Không có public Java `Runnable` handshake API cho ứng dụng.

### Bài 11 — Async propagation

**Đề:** `ThreadLocal` của caller có tự xuất hiện trong task `CompletableFuture.supplyAsync` không?

**Đáp án:** Không có cam kết đó. Task thường chạy trong worker thread khác. Phải truyền dữ liệu rõ ràng hoặc dùng propagation được framework hỗ trợ.

### Bài 12 — Thread con và kế thừa

**Đề:** Một child thread mới luôn kế thừa `ThreadLocal` bình thường của parent?

**Đáp án:** Không. `ThreadLocal` không tự kế thừa. `InheritableThreadLocal` có cơ chế riêng ở lúc **tạo** child, nhưng không phải cách mặc định để truyền context qua thread pool.

### Bài 13 — Virtual threads

**Đề:** Virtual thread của JDK 21+ chạy trên carrier platform thread nên `ThreadLocal.get()` của code trong virtual thread có chắc đọc slot của carrier không?

**Đáp án:** Không. Public `Thread.currentThread()` trong code đang chạy virtual thread tham chiếu chính virtual thread, và ThreadLocal được hỗ trợ theo semantics Java thread. Không dựa vào carrier identity để truyền request context.

### Bài 14 — ScopedValue so với ThreadLocal

**Đề:** Trong JDK 25, cần truyền một request ID chỉ đọc sâu xuống call chain. Vì sao cân nhắc `ScopedValue`?

**Đáp án:** Binding có vòng đời theo dynamic scope, không tùy ý gán lại từ callee, được tháo khi scope kết thúc. Nó giảm một số nguy cơ quên `remove`; vẫn phải tuân quy tắc khi truyền qua child tasks/threads.

### Bài 15 — Chọn công cụ chẩn đoán

**Đề:** Log `-Xlog:safepoint=info` không có dòng nào liên quan request ID. Có chứng minh `ThreadLocal` đang sạch không?

**Đáp án:** Không. Safepoint logging không quan sát trực tiếp toàn bộ per-thread values của ứng dụng. Kiểm tra task lifecycle, set/remove, framework propagation và viết tests thread pool reuse.

### Bài 16 — Output lab

**Đề:** Lab có dòng `pool contamination before cleanup: LEAKED-A`. Dòng đó chứng minh VM đã dùng Thread-Local Handshake để chuyển state từ task 1 sang task 2 không?

**Đáp án:** Không. Dòng này xuất hiện vì **hai task chạy trên cùng một worker thread được tái sử dụng**, và task đầu cố tình quên remove. Đó là semantics của `ThreadLocal` cộng với thread pool.

## 15. Checklist review

- [ ] Nêu đúng JEP **312** và phiên bản **JDK 10** cho VM Thread-Local Handshakes.
- [ ] Nêu đúng `ThreadLocal` có từ **Java 1.2**, không gắn lịch sử sai sang JDK 10.
- [ ] Phân biệt VM-internal JavaThread với Java application-visible `Thread` và virtual threads.
- [ ] Không có ví dụ “`Thread.handshake()`” như public API.
- [ ] Giải thích global safepoint và handshake theo phạm vi, không hứa zero-pause hoặc bỏ hoàn toàn safepoint.
- [ ] Không gán công dụng quản lý request context hay cleanup cho JEP 312.
- [ ] Khi cần application context, biết `ThreadLocal.withInitial/get/set/remove`.
- [ ] Hiểu `static final` giữ key nhưng mỗi thread có riêng value.
- [ ] Dùng `try/finally` để cleanup giá trị theo vòng đời task khi phù hợp.
- [ ] Xem xét nested scope save/restore hoặc `ScopedValue`, không xóa nhầm context cha.
- [ ] Test worker thread **reuse**, async boundary và thread inheritance riêng.
- [ ] Không dùng `InheritableThreadLocal` để giả định truyền mỗi request qua executor pool.
- [ ] Không giữ token/object lớn trong ThreadLocal qua thời gian dài mà thiếu policy.
- [ ] Không nhầm per-thread slot với deep copy hoặc an toàn của shared mutable values.
- [ ] Không thay locks/atomics/volatile bằng một biến `ThreadLocal` khi dữ liệu cần chia sẻ.
- [ ] Với virtual threads, không dựa vào carrier identity hay mapping 1:1 với OS thread.
- [ ] Với JDK 25+ có thể dùng `ScopedValue` cho data flow chỉ đọc, biết đây là JEP **506**, **không phải JEP 312**.
- [ ] Khi debug VM, đọc `-Xlog:help` của bản JDK rồi dùng diagnostics phù hợp.
- [ ] Khi debug request leakage, kiểm tra code app, `finally/remove` và task boundaries.
- [ ] Chạy `ThreadLocalVsHandshakeLab.java` trên JDK 17+ và đối chiếu **chính xác 16 dòng stdout**.
- [ ] Không khẳng định một demo ứng dụng Java có thể trực tiếp gọi VM handshake.

## 16. Kết luận

**Thread-local handshake và `ThreadLocal` không phải hai tên của cùng một tính năng.** JEP 312 của Java 10 giúp **HotSpot VM phối hợp công việc trên các thread ở trạng thái an toàn**, giảm việc phải dùng global safepoint trong những trường hợp thích hợp. Nó là **cơ chế nội bộ VM**; không có lời gọi public để ứng dụng đặt request ID, kích hoạt handshake hay tự động xóa thread-local values.

**`ThreadLocal<T>` là API ứng dụng vẫn còn được dùng trên Java hiện đại**, cung cấp mỗi thread một giá trị riêng. Nó hữu ích cho một số trạng thái per-thread nhưng có vấn đề vòng đời khi thread pool tái sử dụng worker; cần cleanup trong `finally`, propagation có chủ đích và thiết kế tránh shared mutable state. Với dữ liệu ngữ cảnh chỉ đọc và vòng đời rõ, **`ScopedValue` trên JDK 25+** là lựa chọn đáng cân nhắc — nhưng cũng là **API ứng dụng**, không phải VM handshake.

## 17. Tài liệu chính thức và nguồn kiểm chứng

- [OpenJDK JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312): động cơ, phạm vi và cơ chế callback nội bộ trên JavaThread của HotSpot từ JDK 10.
- [OpenJDK, HotSpot handshake.hpp — ví dụ mã nguồn VM](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp): minh họa hạ tầng phối hợp thread trong mã C++ HotSpot hiện đại, không phải public Java API.
- [Oracle Java SE 25 API — java.lang.ThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html): `get`, `set`, `remove`, `withInitial` và per-thread value lifetime.
- [Oracle Java SE 25 API — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/InheritableThreadLocal.html): kế thừa giá trị tại thời điểm tạo thread và `childValue`.
- [Oracle Java SE 25 API — java.lang.Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): platform threads, virtual threads, semantics của `Thread.currentThread()` và kế thừa thread locals.
- [Oracle Java SE 25 Core Libraries Guide — Thread-Local Variables](https://docs.oracle.com/en/java/javase/25/core/thread-local-variables.html): mục đích, rủi ro về mutability, unbounded lifetime và inheritance.
- [OpenJDK JEP 506 — Scoped Values](https://openjdk.org/jeps/506): API final trong JDK 25 cho context có dynamic scope, định hướng thay thế một số use cases ThreadLocal.
- [Oracle Java SE 25 API — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): `where(...).run(...)`, `newInstance`, lifecycle và child-task inheritance có cấu trúc.
- [Oracle Java SE 25 — The java Command / Unified JVM Logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): `-Xlog:help`, `-Xlog:safepoint=info` và quy tắc log tags theo runtime.
- [Oracle Java SE 25 API — ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): execution, task completion, shutdown và memory-consistency effects.