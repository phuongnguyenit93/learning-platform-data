# Hủy đăng ký callback, chờ lời gọi đang chạy rồi mới đóng Arena trong Java FFM

## 1. Cốt lõi của vấn đề

Trong Foreign Function & Memory API (FFM), một chương trình Java có thể dùng `Linker.upcallStub` để tạo **địa chỉ native function** cho một Java `MethodHandle`. Một thư viện C có thể giữ địa chỉ này và gọi ngược vào Java mỗi khi có sự kiện.

~~~java
// JDK 22+, trích đoạn minh họa, không phải chương trình độc lập.
MemorySegment functionPointer = linker.upcallStub(
        target,
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT),
        arena);
~~~

`functionPointer` là một `MemorySegment` đại diện **địa chỉ upcall stub**, không phải một callback registration đã được FFM tự động quản lý. Chính code Java phải truyền địa chỉ này cho thư viện C qua API đăng ký.

Khi C đã lưu pointer, tình huống nguy hiểm:

~~~text
Native worker T1                       Java controller T2
--------------------------------       -------------------------------
pointer = registered_callback;
                                       unregister_callback();
                                       arena.close();  <-- giải phóng stub
pointer(42);             <-- gọi một địa chỉ có thể đã mất hiệu lực
~~~

**Chỉ xóa callback khỏi registry không có nghĩa callback đang chạy hoặc sắp chạy đã kết thúc.** T1 có thể đã đọc và giữ pointer trước khi T2 unregister. Nếu T2 đóng Arena quá sớm, C vẫn có thể gọi một raw pointer đến vùng code đã giải phóng, dẫn đến memory corruption, crash JVM hoặc hành vi không xác định.

Quy tắc của bài:

> **Chặn lời gọi callback mới → chờ tất cả lời gọi đã được phép chạy hoàn tất → xác nhận worker/queue không còn dùng địa chỉ → mới đóng Arena.**

Ba thời điểm này phải phân biệt rõ:

| Mốc | Ý nghĩa | Có an toàn để đóng Arena? |
| --- | --- | --- |
| `unregisterRequested` | Java mới gửi yêu cầu hủy đăng ký | Không |
| `noNewCallbacks` | Native registry từ chối dispatch mới | Chưa đủ |
| `drained` / `quiescent` | Toàn bộ invocation đang chạy, đã giữ pointer hoặc đã xếp trong queue đều được xử lý xong theo contract | Có, nếu không còn người dùng tài nguyên liên quan |
| `arena.close()` | Upcall stub hết lifetime, vùng memory do arena sở hữu được giải phóng | Phải xảy ra sau drained |

**Phạm vi bài:** Java FFM đã final từ **JDK 22**, dùng Linux/x86-64 và C11/POSIX pthreads cho ví dụ chạy được. API `Linker` và `Arena` có đặc điểm riêng trên các JDK preview 19–21; mã trong bài nhắm JDK 22+.

## 2. FFM biết gì về vòng đời, và không thể biết gì?

### 2.1. Upcall stub có lifetime của Arena

Trong JDK 22, `Linker.upcallStub(target, descriptor, arena)` tạo native function pointer mà C có thể gọi. `arena` quản lý vòng đời địa chỉ stub ấy. Java gọi `arena.close()` thành công thì địa chỉ stub không còn hợp lệ để C gọi tiếp.

Tuy nhiên:

- `Linker` không tự biết **bao nhiêu native threads** đã lưu pointer.
- `Arena.close()` không tự gỡ pointer khỏi mọi registry, native queue và event loop.
- Kiểm tra scope của Java `MemorySegment` không thay thế việc kiểm tra mọi bản copy raw pointer tồn tại trong C.
- Lời gọi native qua function pointer đã bị giải phóng không nhất thiết tạo Java exception an toàn; C có thể làm JVM crash.
- Một lời gọi `unregister` trong thư viện C có thể chỉ xóa entry rồi trả ngay; semantics có đợi active callbacks hay không là vấn đề **contract của chính thư viện**.

### 2.2. Chọn `Arena.ofShared()` cho ví dụ callback từ C worker

~~~java
Arena arena = Arena.ofShared();
~~~

Một shared arena cho phép sử dụng các segments gắn với nó trong bối cảnh đa luồng và có thể đóng tường minh. Trong ví dụ, C tạo một pthread riêng để gọi Java callback, nên đây là lựa chọn đơn giản về thread ownership.

Đối chiếu:

| Arena | Vòng đời | Luồng được phép dùng segment | Vấn đề chính |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Close tường minh từ owner | Chỉ luồng tạo arena | Không phù hợp nếu việc truy cập/đóng cần diễn ra ngoài owner |
| `Arena.ofShared()` | Close tường minh | Nhiều luồng | **Vẫn phải quản lý unregister và drain** |
| `Arena.ofAuto()` | GC quyết định thời điểm thu hồi | Nhiều luồng | Không bảo đảm cleanup có deadline |
| `Arena.global()` | Sống toàn tiến trình | Nhiều luồng | Không thể close để giải phóng stub, dễ che khuất rò rỉ |

**`ofShared` không có nghĩa callback C tự động thread-safe.** Nó không bảo vệ Java state của callback, không đợi native workers và không biến một đăng ký bất đồng bộ thành lời gọi đồng bộ.

### 2.3. Đường upcall và downcall

Có hai loại FFM invocation:

~~~text
Java  -- downcallHandle -->  C register_callback(ptr)
Java  <-- upcall stub ---    C worker gọi ptr(event)
Java  -- downcallHandle -->  C unregister_and_drain()
Java  -- Arena.close() -->   stub hết lifetime
~~~

- `downcallHandle` tạo Java `MethodHandle` để gọi một native function.
- `upcallStub` tạo native function pointer để C gọi Java `MethodHandle`.
- `SymbolLookup.libraryLookup` tìm các C symbol trong shared library.
- `FunctionDescriptor` phải khớp **đúng** ABI: sai số/thứ tự/thể loại đối số và kiểu trả về có thể gây crash.
- Trong chương trình thật, cả downcall, upcall và library lookup có thể là restricted operations: bật native access đúng module.

## 3. Race tinh vi: copy pointer trước khi bị xóa

Giả sử native library dùng mutex chỉ để quản lý một biến callback:

~~~c
/* Anti-pattern minh họa; không phải chương trình độc lập. */
pthread_mutex_lock(&mu);
callback_fn local = registered_callback;
pthread_mutex_unlock(&mu);

/* Thread khác có thể unregister rồi close arena ở đây. */

if (local != NULL) {
    local(42);  /* Có nguy cơ dùng pointer đã mất hiệu lực. */
}
~~~

Mutex bảo vệ **việc đọc giá trị trong registry**, nhưng không bảo vệ **lifetime sau khi đã copy pointer**. Nếu Java đổi registry pointer thành NULL rồi đóng Arena, `local` vẫn giữ pointer cũ.

Mẫu đúng cần kết hợp **admission control** và **in-flight accounting**:

~~~c
/* Pseudocode: phần reservation/counter, không độc lập. */
pthread_mutex_lock(&mu);
if (!stopping && registered_callback != NULL) {
    callback_fn local = registered_callback;
    ++in_flight;       /* Reserve trước khi unlock. */
    pthread_mutex_unlock(&mu);

    local(42);         /* Callback chạy ngoài mutex. */

    pthread_mutex_lock(&mu);
    --in_flight;
    pthread_cond_broadcast(&changed);
}
pthread_mutex_unlock(&mu);
~~~

Hủy đăng ký cũng dùng **cùng mutex**:

~~~c
/* Pseudocode: unregister phải đợi counter về zero. */
pthread_mutex_lock(&mu);
stopping = 1;
registered_callback = NULL;

while (in_flight != 0) {
    pthread_cond_wait(&changed, &mu);
}
pthread_mutex_unlock(&mu);

/* Cần join/ack event sources và queued work trước khi báo drained. */
~~~

Khi worker đã được phép gọi callback, nó tăng `in_flight` **trước khi thả mutex**. Vì vậy unregister không thể quan sát `in_flight == 0` một cách sai lầm trong lúc worker đã capture pointer nhưng chưa “được tính”.

Không đợi counter bằng busy loop không có synchronization; cũng không chỉ dựa vào `volatile` C. POSIX mutex và condition variable cung cấp đồng bộ rõ ràng cho biến `in_flight`, `stopping` và `registered_callback`.

## 4. Lifecycle contract nên viết rõ trong native API

Một API đăng ký callback nên định nghĩa:

1. **Registration ownership:** ai tạo registration, ai được phép unregister, có hỗ trợ gọi nhiều lần hay không.
2. **Admission boundary:** sau thời điểm nào native library không cho phép một dispatch mới giữ pointer.
3. **Active reservation:** một callback được xem là in-flight từ **trước khi thread thả lock và giữ bản copy pointer**, không phải chỉ từ khi target Java bắt đầu.
4. **Completion:** sau khi callback thực sự return, native worker giảm counter và thông báo.
5. **Drain:** native unregister đợi active count về 0, cùng mọi native workers/queued jobs liên quan.
6. **Acknowledgement:** return success xác nhận không còn ai có thể gọi function pointer đó.
7. **Close:** Java chỉ đóng Arena chứa stub sau acknowledgement.
8. **Failure:** nếu chưa xác nhận drain, không close chỉ vì có timeout hoặc Java `Future.cancel(true)`.

State machine:

~~~text
NEW
 |
 | create stub, register pointer
 v
REGISTERED -- request stop --> STOPPING
                                  |
                                  | block new admissions
                                  | wait in-flight == 0
                                  | join/ack workers
                                  v
                               DRAINED
                                  |
                                  | arena.close()
                                  v
                                CLOSED

STOPPING -- timeout/error --> NOT_CONFIRMED (Arena retained, escalate)
~~~

**Không suy nghĩa từ tên `unregister`.** Có thư viện dùng nó để xóa listener khỏi map rồi return ngay; thư viện khác gọi nó là synchronous barrier. Phải đọc native documentation hoặc tự dựng wrapper có giao thức kiểm chứng.

## 5. Chương trình C11 hoàn chỉnh: một worker, một upcall và một drain barrier

Ví dụ gồm hai tệp: `callback_drain.c` và `CallbackDrainDemo.java`. C tạo **một pthread**, phát callback một lần với giá trị 7, rồi đợi stop; Java cố ý giữ callback chặn ở latch. Main gọi native unregister trong lúc callback đang chạy. C chỉ trả success sau khi callback return và pthread join.

### 5.1. Tệp `callback_drain.c`

~~~c
#include <pthread.h>
#include <stddef.h>

typedef void (*callback_fn)(int);

static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;

static callback_fn registered_cb = NULL;
static pthread_t worker;
static int running = 0;
static int stop_requested = 0;
static int in_flight = 0;

static void *worker_main(void *unused) {
    (void)unused;

    pthread_mutex_lock(&mu);

    if (!stop_requested && registered_cb != NULL) {
        /*
         * Reserve callback dưới cùng mutex mà unregister dùng.
         * Sau khi ++in_flight, controller phải đợi lượt gọi này.
         */
        callback_fn cb = registered_cb;
        ++in_flight;

        pthread_mutex_unlock(&mu);
        cb(7); /* Java FFM upcall; KHÔNG giữ mutex. */
        pthread_mutex_lock(&mu);

        --in_flight;
        pthread_cond_broadcast(&cv);
    }

    /* Demo có một event duy nhất; worker chờ shutdown. */
    while (!stop_requested) {
        pthread_cond_wait(&cv, &mu);
    }

    pthread_mutex_unlock(&mu);
    return NULL;
}

/*
 * Controller đăng ký một callback trong demo.
 * Trả 0 nếu thành công; giá trị âm khi lỗi.
 */
int register_callback(callback_fn cb) {
    if (cb == NULL) {
        return -1;
    }

    pthread_mutex_lock(&mu);

    if (running) {
        pthread_mutex_unlock(&mu);
        return -2;
    }

    registered_cb = cb;
    stop_requested = 0;
    in_flight = 0;

    if (pthread_create(&worker, NULL, worker_main, NULL) != 0) {
        registered_cb = NULL;
        pthread_mutex_unlock(&mu);
        return -3;
    }

    running = 1;
    pthread_mutex_unlock(&mu);
    return 0;
}

/*
 * Chỉ được gọi bởi controller, KHÔNG trong callback/worker.
 * Chỉ một unregister caller tại một thời điểm.
 * Return 0 mới có nghĩa native đã drain và join.
 */
int unregister_and_drain(void) {
    pthread_mutex_lock(&mu);

    if (!running) {
        pthread_mutex_unlock(&mu);
        return 0;
    }

    /* Chặn mọi lượt dispatch mới ở cùng admission lock. */
    stop_requested = 1;
    registered_cb = NULL;
    pthread_cond_broadcast(&cv);

    /* Chờ callback đã reserve thực sự return. */
    while (in_flight != 0) {
        pthread_cond_wait(&cv, &mu);
    }

    pthread_t to_join = worker;
    pthread_mutex_unlock(&mu);

    /* Join ngoài mutex để worker có thể khóa mu và thoát. */
    if (pthread_join(to_join, NULL) != 0) {
        return -4;
    }

    pthread_mutex_lock(&mu);
    running = 0;
    pthread_mutex_unlock(&mu);

    return 0;
}
~~~

### 5.2. Kiểm tra logic đồng bộ của C

- `register_callback` đăng ký một callback và tạo một pthread khi mutex đang khóa. Worker sẽ phải lấy mutex trước khi quyết định dispatch.
- `worker_main` kiểm tra `stop_requested`, giữ pointer cục bộ và tăng `in_flight` dưới cùng mutex.
- Khi Java callback đang chặn, worker **không giữ mutex**; nhờ đó unregister có thể lấy mutex và đặt stop flag.
- Unregister đặt `registered_cb=NULL` để chặn những dispatch mới, rồi đợi `in_flight==0` qua `pthread_cond_wait`.
- `pthread_cond_wait` nhả mutex trong lúc đợi, cho worker cơ hội giảm counter và signal.
- Vòng `while` bắt buộc vì có thể có spurious wakeups và predicate có thể chưa thỏa.
- Khi callback return, worker giảm counter và `pthread_cond_broadcast`, rồi thấy stop requested và return.
- `pthread_join` chờ worker **thực sự chấm dứt**, không chỉ nhận stop request.
- Chỉ sau khi join thành công, `unregister_and_drain` trả `0`.

**Giới hạn demo:** API chỉ có **một registration, một native worker và một controller**. Không đồng thời gọi hai `unregister_and_drain`; hai callers có thể cố join cùng pthread. Trong library production cần trạng thái `STOPPING/DRAINED`, một shutdown owner, generation token và điều phối các controllers.

### 5.3. Build shared library trên Linux

~~~bash
cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared -pthread \
  -o libcallbackdrain.so callback_drain.c
~~~

`-pthread` là tùy chọn thích hợp cho compile/link POSIX threads với GCC/Clang. Hai functions không khai báo `static` nên, theo cấu hình visibility mặc định trên Linux, chúng có thể được tìm bằng `SymbolLookup`.

Trong production, nên kiểm tra return values của `pthread_mutex_lock`, `pthread_cond_wait` và các primitive OS, cũng như xử lý cancellation của native worker. Ví dụ dùng các primitive đã được khởi tạo tĩnh và tập trung vào contract quiescence.

## 6. Chương trình Java 22+ hoàn chỉnh: đăng ký, đợi callback, drain, rồi close

### 6.1. Tệp `CallbackDrainDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class CallbackDrainDemo {
    private static final CountDownLatch ENTERED =
            new CountDownLatch(1);
    private static final CountDownLatch RELEASE =
            new CountDownLatch(1);
    private static final AtomicInteger RECEIVED =
            new AtomicInteger(-1);
    private static final AtomicReference<Throwable> CALLBACK_ERROR =
            new AtomicReference<>();

    /*
     * Callback tương ứng C: void (*callback_fn)(int).
     * Không để Throwable đi xuyên qua FFM upcall.
     */
    private static void onValue(int value) {
        try {
            ENTERED.countDown();
            RELEASE.await();
            RECEIVED.set(value);
        } catch (Throwable error) {
            CALLBACK_ERROR.compareAndSet(null, error);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        Arena arena = Arena.ofShared();

        MethodHandle unregister = null;
        boolean registered = false;
        boolean drained = false;

        try {
            Path path = Path.of("libcallbackdrain.so")
                    .toAbsolutePath();
            SymbolLookup lib =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle register = linker.downcallHandle(
                    lib.find("register_callback").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            unregister = linker.downcallHandle(
                    lib.find("unregister_and_drain").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));

            MethodHandle javaTarget =
                    MethodHandles.lookup().findStatic(
                            CallbackDrainDemo.class,
                            "onValue",
                            MethodType.methodType(
                                    void.class, int.class));

            MemorySegment stub = linker.upcallStub(
                    javaTarget,
                    FunctionDescriptor.ofVoid(
                            ValueLayout.JAVA_INT),
                    arena);

            int registrationCode =
                    (int) register.invokeExact(stub);
            if (registrationCode != 0) {
                throw new IllegalStateException(
                        "Register failed: " + registrationCode);
            }
            registered = true;

            /* Biết chắc callback đang chạy, không đoán thời gian. */
            if (!ENTERED.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Callback did not start");
            }

            /*
             * Main sẽ gọi unregister và có thể chặn.
             * Thread phụ nhả callback sau khoảng quan sát 100ms.
             */
            Thread releaser = new Thread(() -> {
                try {
                    Thread.sleep(100);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    RELEASE.countDown();
                }
            }, "callback-releaser");
            releaser.start();

            int stopCode = (int) unregister.invokeExact();
            if (stopCode != 0) {
                throw new IllegalStateException(
                        "Drain failed: " + stopCode);
            }
            drained = true;

            releaser.join();

            if (CALLBACK_ERROR.get() != null) {
                throw new IllegalStateException(
                        "Upcall failure", CALLBACK_ERROR.get());
            }

            System.out.println("registered=true");
            System.out.println("callbackEntered=true");
            System.out.println("unregisterStatus=0");
            System.out.println("received=" + RECEIVED.get());
            System.out.println(
                    "callbackFinishedBeforeReturn="
                    + (RECEIVED.get() == 7));
        } finally {
            /* Không để callback kẹt nếu main có lỗi. */
            RELEASE.countDown();

            /*
             * Nếu đã register mà chưa được xác nhận drained,
             * tiếp tục yêu cầu native drain trước khi close.
             * Khi C trả lỗi, không close stub mà C có thể gọi.
             */
            if (registered && !drained) {
                int code = (int) unregister.invokeExact();
                if (code != 0) {
                    throw new IllegalStateException(
                            "Drain not confirmed; Arena retained: "
                            + code);
                }
                drained = true;
            }

            if (!registered || drained) {
                arena.close();
            }
        }

        System.out.println(
                "arenaAliveAfterClose="
                + arena.scope().isAlive());
    }
}
~~~

### 6.2. Chạy Java

~~~bash
javac CallbackDrainDemo.java

java --enable-native-access=ALL-UNNAMED \
  CallbackDrainDemo
~~~

**Stdout dự kiến nếu chương trình chạy thành công trên Linux x86-64 với JDK 22+:**

~~~text
registered=true
callbackEntered=true
unregisterStatus=0
received=7
callbackFinishedBeforeReturn=true
arenaAliveAfterClose=false
~~~

Giải thích từng dòng:

- `registered=true`: C trả 0 khi nhận callback pointer và khởi tạo worker.
- `callbackEntered=true`: `ENTERED.await` xác nhận C đã đi vào `onValue`.
- `unregisterStatus=0`: native unregister đã ngăn dispatch mới, chờ callback return, join worker.
- `received=7`: callback nhận đúng đối số C truyền và ghi kết quả trước khi return.
- `callbackFinishedBeforeReturn=true`: Java có thể quan sát giá trị callback sau khi native drain hoàn tất.
- `arenaAliveAfterClose=false`: Java close arena **sau** acknowledgement, làm scope hết hiệu lực.

Trong ví dụ, `Thread.sleep(100)` chỉ giúp mô phỏng callback đang chặn đủ lâu để người học quan sát. **Độ dài 100 ms không phải cơ chế bảo đảm an toàn**. Điều tạo ra bằng chứng drain là native `in_flight`, condition variable và `pthread_join`.

### 6.3. Vì sao không dùng `try (Arena arena = ... )` đơn giản?

Với một registration callback kéo dài và bất đồng bộ, nếu code trong block ném exception, Java `try-with-resources` sẽ gọi `arena.close()` khi rời block. Nếu chưa kịp unregister/drain, đó có thể là **close quá sớm**.

Ví dụ dùng `Arena` explicit và `finally` bắt buộc yêu cầu drain trước close. Nếu native code trả lỗi không thể xác minh quiescence, ví dụ **giữ arena chưa đóng**; đây là biện pháp an toàn tương đối trước nguy cơ use-after-free, **không phải cách vận hành lý tưởng**. Production cần ghi log, watchdog và chính sách isolate/restart khi native worker không hợp tác.

### 6.4. Java callback không được ném lỗi qua C

Tài liệu `Linker.upcallStub` JDK 22 cảnh báo target method handle không nên để exception thoát ra khỏi upcall. Nếu điều đó xảy ra, JVM có thể terminate abruptly. Vì vậy:

~~~java
// Mẫu minh họa an toàn về exception boundary.
static void onEvent(int code) {
    try {
        process(code);
    } catch (Throwable error) {
        reportFailure(error); // reportFailure cũng cần không ném ra.
    }
}
~~~

Trong chương trình đầy đủ, `onValue` catch `Throwable` và lưu lỗi vào `AtomicReference` để thread điều phối kiểm tra **sau drain**. C nhận callback return bình thường và có thể giảm `in_flight` đúng protocol.

Trong ứng dụng thực, nên làm Java callback ngắn và tránh các hành động có thể chặn vô hạn. Nếu callback chỉ enqueue một job Java, cần giải quyết **lifetime của dữ liệu dùng bởi job**: job có thể tiếp tục chạy sau khi upcall return.

## 7. Giải thích chữ ký C và FFM

C header của demo:

~~~c
typedef void (*callback_fn)(int);
int register_callback(callback_fn callback);
int unregister_and_drain(void);
~~~

Java descriptor:

~~~java
// JDK 22+, trích đoạn, chưa phải file chạy độc lập.
FunctionDescriptor callbackSignature =
        FunctionDescriptor.ofVoid(ValueLayout.JAVA_INT);

FunctionDescriptor registerSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS);

FunctionDescriptor unregisterSignature =
        FunctionDescriptor.of(ValueLayout.JAVA_INT);
~~~

| C signature | FFM descriptor | Java MethodHandle type |
| --- | --- | --- |
| `void callback(int)` | `ofVoid(JAVA_INT)` | `(int)void` |
| `int register_callback(callback_fn)` | `of(JAVA_INT, ADDRESS)` | `(MemorySegment)int` |
| `int unregister_and_drain(void)` | `of(JAVA_INT)` | `()int` |

Không nhầm **pointer tới function** với callback result. `ValueLayout.ADDRESS` dùng để truyền function pointer; `ofVoid(JAVA_INT)` mô tả **chữ ký mà pointer ấy trỏ tới**.

Vì `SymbolLookup.libraryLookup` dùng cùng Arena với `upcallStub`, việc close còn có thể giải phóng/unload library lookup khi native library không còn được sử dụng. Do đó thứ tự unregister-drain-close bảo vệ **cả stub lẫn library lifetime**.

## 8. Vì sao phải unlock trước khi gọi callback?

Anti-pattern:

~~~c
/* Sai: giữ mutex xuyên qua user callback. */
pthread_mutex_lock(&mu);
registered_cb(7);
pthread_mutex_unlock(&mu);
~~~

Java callback có thể gọi lại API C cần chính mutex đó, tạo **reentrancy deadlock**. Controller unregister cũng cần mutex để cập nhật state và có thể bị block vô hạn. Callback có thể chờ một future mà future đang chờ unregister, gây vòng phụ thuộc khó phát hiện.

Thứ tự đúng:

1. Lock.
2. Kiểm tra state cho phép dispatch.
3. Tăng counter và capture pointer.
4. Unlock.
5. Gọi Java callback.
6. Lock.
7. Giảm counter, signal.
8. Unlock.

Nếu Java callback tự gọi **synchronous `unregister_and_drain` trên chính registration đang chạy**, vẫn có thể deadlock: unregister chờ counter về zero, nhưng counter chỉ giảm **sau khi callback return**, trong khi callback đang chờ unregister return.

**Sửa:** callback chỉ **gửi requestStop không chặn** tới một controller khác rồi return; controller mới thực hiện drain và close sau khi callback đã thoát.

## 9. Unregister có thể chỉ là “chặn thêm”, không phải “đã xong”

Nhiều C libraries cung cấp API kiểu:

~~~text
remove_listener(handle)       // Ngăn phát sinh dispatch mới.
wait_for_idle(handle)         // Chờ callbacks đã dispatch xong.
destroy_registration(handle)  // Giải phóng context.
close_arena()                 // Java giải phóng upcall stub.
~~~

Không thể giả định `remove_listener` có sẵn `wait_for_idle` ở bên trong. Ngay cả thư viện có API `stop_stream()` cũng có thể:

- Stop event producer, nhưng worker pool vẫn có items chờ.
- Remove callback khỏi map, nhưng một thread đã lấy pointer cũ.
- Hủy listener mới, nhưng callback đã được gửi sang một executor khác.
- Chờ thread chính, nhưng C thread phụ vẫn giữ user-data.
- Trả về “stop requested”, không phải “stopped”.

Nếu thư viện không có drain API, đôi khi phải viết wrapper C quản lý **admission + in-flight counter + join/ack**. Java không thể kiểm tra một cách đầy đủ các C raw pointers chỉ bằng việc xem `Thread.isAlive()` của một Java thread.

## 10. Hệ thống nhiều native threads và registration generations

Trong demo, **một callback** được gọi trên **một worker**; `pthread_join` xác nhận worker đó đã thoát. Với nhiều native threads, cần duy trì registration state:

~~~text
Registration {
  id, generation
  state = ACTIVE | STOPPING | DRAINED
  callbackPointer
  activeCount
  nativeQueue
  workerHandles
  userDataPointer
}
~~~

Protocol an toàn cho mỗi registration:

~~~text
admit(event):
  lock
  if state != ACTIVE: reject
  activeCount++
  capture pointer and generation
  unlock

  invoke callback (without lock)

  lock
  activeCount--
  if state == STOPPING and activeCount == 0: notify
  unlock

stop_and_drain():
  lock
  state = STOPPING
  stop accepting new events
  remove pointer from registry
  while activeCount != 0: condition_wait()
  unlock
  join/fence remaining event sources and queues
  return DRAINED
~~~

Các ràng buộc:

- **Counter phải tăng trước khi thả admission lock.** Nếu tăng lúc bắt đầu gọi Java, có khoảng race khi worker đã giữ pointer nhưng chưa được tính.
- **Generation token** ngăn callback cũ bị dùng như callback của registration mới sau khi numeric ID/địa chỉ bị tái sử dụng (ABA problem).
- Callback đã **xếp trong queue** nhưng chưa chạy có thể được tính trong active reservations hoặc phải được cancel+ack theo contract. Không bỏ qua queued work.
- `user_data` có thể là pointer tới native buffer hoặc Java-owned state: giữ sống cả user-data tới drain, không chỉ upcall stub.
- Để hỗ trợ **nhiều controller unregister đồng thời**, native state phải bảo đảm chỉ một owner thực hiện stop/join; các caller khác chờ trạng thái DRAINED thay vì cùng join một pthread.
- Một atomic pointer store sang NULL chưa giải quyết memory reclamation của mọi readers đã giữ pointer. Lock-free algorithms cần reference counting/hazard pointers/epochs hoặc cơ chế an toàn tương đương.

Với callbacks thực hiện song song, phải tính tất cả active invocations và có synchronization đủ mạnh. `Arena.ofShared()` cho phép access đa luồng nhưng **không tự biến Java/native shared state thành thread-safe**.

## 11. Thứ tự giải phóng nhiều tài nguyên

Ngoài stub, callback có thể sử dụng:

- Native library loaded qua `SymbolLookup.libraryLookup(path, arena)`.
- `void* user_data` và buffers được cấp bằng Arena.
- Native context/registration handle của thư viện.
- Java target object và state mà callback capture.
- Worker pool, timers, event loop hoặc queues.
- Các Java tasks do callback enqueue, còn giữ reference tới native memory.

Một thứ tự thường an toàn:

~~~text
1. Ngừng nhận event mới và phát yêu cầu unregister.
2. Chặn native dispatch admissions theo synchronization.
3. Chờ những callbacks đã giữ pointer thực sự return.
4. Join/ack mọi event source và native worker liên quan.
5. Dọn native registration/context trong lúc thư viện còn loaded.
6. Đợi Java tasks đang dùng shared native data hoặc copy dữ liệu trước.
7. Close Arena sở hữu upcall stub và native buffers.
8. Close library Arena nếu khác (sau khi hết downcalls/users).
9. Release Java owner references.
~~~

Thứ tự 5–8 phải điều chỉnh theo contract thực tế; điểm bất biến là **không có native thread nào dùng callback pointer hay library code sau khi chúng bị giải phóng/unload**. Ví dụ dùng chung một Arena để trình tự nhìn thấy rõ nhất.

**Không** dùng `Arena.global()` như một phương án “chữa cháy” chung: callback pointer sẽ không bị thu hồi nhưng registry/event sources có thể vẫn dispatch và các native resources có thể leak đến cuối tiến trình.

## 12. Timeout: hết giờ đợi khác hoàn tất drain

Một hệ thống thực có thể đặt deadline cho shutdown. Nếu callback bị treo trong I/O hoặc deadlock, `unregister_and_drain` có thể chờ mãi. Nhưng hết thời gian chờ không chứng minh callback đã an toàn để giải phóng.

| Kết quả | Ý nghĩa | Có được close stub? |
| --- | --- | --- |
| `DRAINED` | Native đã xác nhận không còn user của callback | Có, theo ownership |
| `STOPPING` | Đã chặn admission nhưng còn active | Chưa |
| `WAIT_TIMED_OUT` | Supervisor hết thời gian nhưng không có quiescence ack | **Không** |
| `FAILED` | Native API báo lỗi, không chứng minh state | **Không**, trừ khi có chứng minh độc lập |
| `CANCEL_REQUESTED` | Chỉ phát tín hiệu hủy | **Không** |

Một `Future.cancel(true)` ở Java cũng không tự dừng native C thread đang chờ callback return. Java `Thread.interrupt()` không có contract “kill C function tại bất kỳ instruction”. Nếu callback chặn mãi, sửa đường blocking: cooperative cancellation, timeout trong chính native I/O, wake-up condition hoặc **process isolation**.

Với thư viện native không hợp tác, cách an toàn hơn đôi khi là giữ Arena sống và đánh dấu lỗi/leak tạm thời, sau đó restart/cô lập process. **Đóng Arena tùy tiện khi C còn raw pointer có thể gây crash cả JVM**, nên không coi close sau timeout là “cleanup”.

## 13. Các lỗi đặc trưng cần tránh

### Lỗi 1 — unregister xong close ngay

~~~java
// Sai nếu unregister chỉ remove pointer khỏi registry.
int rc = (int) unregister.invokeExact();
arena.close();
~~~

Phải hiểu rõ contract return: `rc == 0` có thực sự bao hàm **drain và quiescence** không?

### Lỗi 2 — chờ một số mili giây rồi đoán callback đã xong

~~~java
// Sai: thời gian không phải synchronization.
unregister.invokeExact();
Thread.sleep(500);
arena.close();
~~~

Callback có thể chặn I/O, bị hoãn bởi scheduler hoặc còn queued. Chỉ tín hiệu xác nhận đúng protocol mới cho phép close.

### Lỗi 3 — không tăng in-flight khi capture pointer

~~~c
/* Sai vì có khoảng trống giữa copy pointer và counter. */
callback_fn cb = registered_cb;
/* unregister có thể đóng stub ở đây */
++in_flight;
~~~

Chặn admission và reserve phải nguyên tử đối với unregister.

### Lỗi 4 — giữ mutex khi gọi user callback

Callback có thể re-enter thư viện hoặc chờ controller đang cần mutex, gây deadlock. Unlock trước khi gọi; mọi đường hoàn tất phải giảm counter.

### Lỗi 5 — callback tự synchronous unregister nó

Đây là self-deadlock: unregister chờ callback hiện tại kết thúc; callback lại đợi unregister. Callback chỉ phát request async, controller xử lý drain sau.

### Lỗi 6 — dùng `try-with-resources` một cách thiếu kiểm soát

~~~java
// Sai nếu callback sống dài hơn scope block và có lỗi giữa chừng.
try (Arena arena = Arena.ofShared()) {
    nativeRegister.invokeExact(stub);
    operationThatMayThrow();
} // Có thể close trước khi unregister/drain.
~~~

Với registration bất đồng bộ dài hạn, dùng lifecycle/finally đảm bảo native quiescence trước khi close, hoặc abstraction `AutoCloseable` có close đúng protocol.

### Lỗi 7 — tin Java latch cho một callback đồng nghĩa toàn registry idle

Một callback đã return không chứng minh các workers khác/queue khác không còn pointer. Native registry cần tự đưa acknowledgement cho **toàn bộ registration**.

### Lỗi 8 — exception vượt qua FFM upcall

~~~java
// Sai: JVM có thể terminate abruptly khi exception thoát qua upcall.
static void badCallback(int value) {
    throw new IllegalStateException("unexpected");
}
~~~

Bọc callback, ghi nhận lỗi qua cơ chế phù hợp và để C nhận return theo ABI đã công bố.

### Lỗi 9 — giải phóng buffer user-data trước stub

Ngay cả khi stub còn sống, callback có thể dereference `void* user_data` đã bị free. Dọn **cả stub, user-data và native context** sau khi các users đã kết thúc.

### Lỗi 10 — hai controllers cùng unregister/join

Một pthread không được join đồng thời bởi hai controllers không điều phối. Áp dụng single owner hoặc state machine bảo đảm một thread thực hiện drain, những thread khác chờ kết quả.

## 14. Cách viết API Java quản lý registration rõ ràng

Thay vì để caller tự gọi `nativeUnregister()` và `arena.close()` rải rác, có thể đóng gói ownership:

~~~java
// Pseudocode thiết kế: KHÔNG phải chương trình Java chạy độc lập.
final class NativeCallbackRegistration implements AutoCloseable {
    // Holds: Arena arena, MemorySegment stub,
    // nativeHandle, state, lock and an unregister/drain function.

    public void close() {
        // (1) Serialize concurrent close attempts.
        // (2) Native unregister: stop admission.
        // (3) Await all in-flight callbacks and worker acknowledgement.
        // (4) If and only if DRAINED, close arena.
        // (5) Mark CLOSED. Otherwise report failure, retain resources.
    }
}
~~~

`AutoCloseable` chỉ hữu ích nếu `close()` **thực hiện đúng protocol**. Nếu native API chỉ remove callback nhưng không drain, việc đưa nó vào `close()` không tạo thêm quiescence.

Có thể dùng một kết quả rõ ràng hơn boolean:

| State | Trạng thái dành cho caller |
| --- | --- |
| `REGISTERED` | Callback có thể còn được dispatch |
| `STOPPING` | Đã chặn sự kiện mới, đang chờ active |
| `DRAINED` | Native xác nhận không có người dùng pointer |
| `CLOSED` | Arena đã đóng thành công |
| `FAILED_NOT_DRAINED` | Không được coi shutdown thành công |

Không dùng `Future.cancel(true)` hoặc `Thread.isInterrupted()` như shortcut để nhảy thẳng từ REGISTERED sang CLOSED.

## 15. Kiểm thử lifecycle/race trong CI

| Test | Kỳ vọng |
| --- | --- |
| Unregister khi callback chưa được gọi | Native ngăn dispatch, drain rồi trả thành công |
| Unregister khi callback đang chặn | Không return success trước khi callback return |
| Unregister sau khi worker capture pointer, trước khi gọi | Reservation đã tăng, drain đợi đúng |
| Nhiều callbacks chạy đồng thời | Active counter về zero sau tất cả |
| Callback return rất nhanh | Không lost wakeup hoặc active counter âm |
| Callback re-enter thư viện | Không deadlock do giữ registry mutex |
| Callback yêu cầu stop chính nó | Chỉ request async; không chờ chính mình |
| Callback báo lỗi Java | Exception được xử lý bên trong, không vượt qua upcall |
| Unregister trả native error | Arena chưa close nếu không có drain guarantee |
| Chờ drain quá deadline | Báo WAIT_TIMED_OUT, không close |
| Generation mới đăng ký sau generation cũ | Không nhận callback cũ vào registration mới |
| Java task enqueue từ callback | Task còn dùng native data cũng phải finish/copy |
| Native library bị unload | Không còn worker thực thi code trong thư viện |
| Shared Arena đóng khi còn người dùng | Phải ngăn bằng lifecycle protocol, không dựa vào GC |

**Trọng tâm test của bài** được thực hiện trực tiếp qua hai chương trình: Java chờ `ENTERED` để xác nhận callback C→Java đã bắt đầu, giữ nó bằng `RELEASE`, gọi native unregister, chỉ close Arena sau khi unregister đợi active count và join thành công.

## 16. Checklist review trước khi merge

- [ ] Đã hiểu native API unregister chỉ remove hay có bảo đảm drain?
- [ ] Có admission lock/state để chặn callback mới không?
- [ ] Worker reserve in-flight trước khi thả lock và giữ pointer?
- [ ] Mọi đường callback return đều release reservation + notify?
- [ ] Có native queues, timers, worker pools khác còn giữ pointer không?
- [ ] Callback có thể chạy từ C-created threads không; Arena có phù hợp?
- [ ] C registry mutex có được thả trước khi gọi Java không?
- [ ] Callback có thể tự đồng bộ unregister và gây self-deadlock không?
- [ ] Java upcall target bắt exceptions và không để `Throwable` thoát không?
- [ ] `FunctionDescriptor` khớp chính xác C function-pointer ABI?
- [ ] Native registration chỉ được unregister bởi một owner tại một thời điểm?
- [ ] Có test concurrent unregister/re-register và generation reuse?
- [ ] Có chờ queued Java tasks sử dụng native data không?
- [ ] Có xác nhận native worker đã terminate trước khi library bị unload?
- [ ] Có giữ stub và user-data alive tới sau drain không?
- [ ] Failure/timeout có ngăn `arena.close()` nếu chưa có ack không?
- [ ] Đã bật `--enable-native-access` cho downcall/upcall/library lookup?
- [ ] Có test callback in-flight đúng lúc controller muốn close?
- [ ] Đã đo và log thời gian request-stop, drained, arena-close?
- [ ] Khi không thể cancel native, có escalation/isolation chính xác?

## 17. Câu hỏi tự kiểm tra

1. Tại sao `registered_cb = NULL` không đủ để chứng minh callback đã dừng?
2. In-flight counter phải tăng vào thời điểm nào?
3. Tại sao không giữ `pthread_mutex` trong lúc gọi Java callback?
4. Vì sao `pthread_cond_wait` phải nằm trong vòng `while` kiểm predicate?
5. `pthread_join` bổ sung bảo đảm gì cho demo một worker?
6. Java `Arena.close()` có thể tự xóa raw pointer tồn tại trong C không?
7. Nếu callback từ thread C khác, tại sao `Arena.ofShared()` thuận tiện trong ví dụ?
8. Callback Java có thể ném `Throwable` qua upcall stub không?
9. Trong ví dụ, vì sao `ENTERED.await` quan trọng hơn một `Thread.sleep` trước unregister?
10. `unregisterStatus=0` là bằng chứng gì theo hợp đồng C đã viết?
11. Nếu native unregister trả -4, có được close Arena như đã drain không?
12. Vì sao một callback không được đồng bộ unregister chính registration hiện tại?
13. Khi native library chỉ có `removeListener`, Java còn cần primitive nào?
14. `Future.cancel(true)` có bảo đảm native worker đã rời callback không?
15. Nếu Java callback enqueue task dùng native buffer rồi return, có thể close buffer ngay không?
16. Tại sao phải cân nhắc việc unload library gắn với `SymbolLookup.libraryLookup`?
17. Vì sao generation token hữu ích khi reuse callback registration ID?
18. `Arena.global()` có sửa bản chất race của native registry không?

**Đáp án gợi ý:** (1) worker đã capture pointer hoặc đang chạy; (2) khi được cấp quyền dispatch, dưới admission lock; (3) tránh deadlock/reentrancy; (4) chống spurious wakeup và recheck condition; (5) worker thực sự kết thúc; (6) không; (7) lifetime/access đa luồng, vẫn cần drain; (8) không, có thể khiến JVM terminate; (9) xác nhận callback đã bắt đầu; (10) native đã chặn admission, chờ active zero, join thành công; (11) không; (12) self-deadlock vì chờ chính callback return; (13) drain/fence/ack in-flight; (14) không; (15) chưa, phải copy hoặc đợi task hoàn thành; (16) worker không được còn chạy code library; (17) ngăn callback cũ bị gán nhầm registration mới; (18) không, chỉ giữ stub sống lâu hơn và có nguy cơ leak.

## 18. Tài liệu chuẩn

- [Oracle JDK 22 — `Linker.upcallStub` và cảnh báo lifetime/exception](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html)
- [Oracle JDK 22 — `Arena`: shared/confined và `close()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Oracle JDK 22 — `SymbolLookup.libraryLookup` và vòng đời native library](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html)
- [Oracle JDK 22 — `FunctionDescriptor`: `of`, `ofVoid`, carrier types](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454)
- [Oracle Java SE 22 — `CountDownLatch`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Open Group/POSIX — `pthread_cond_wait`](https://pubs.opengroup.org/onlinepubs/9699919799/functions/pthread_cond_wait.html)
- [OpenJDK — FFM asynchronous upcall tests](https://github.com/openjdk/jdk/blob/master/test/jdk/java/foreign/TestUpcallAsync.java)

**Kết luận:** Khi native library đã giữ địa chỉ callback FFM, **hủy đăng ký** không tương đương **hết mọi lời gọi callback**. Hãy chặn admission, đếm và drain in-flight invocations, đợi tất cả native workers/queued jobs hoàn tất rồi mới `arena.close()`. Dùng một barrier/ack có hợp đồng rõ ràng; không dựa vào `sleep`, `Future.cancel` hoặc riêng việc pointer registry thành NULL. Nếu chưa chứng minh quiescence, giữ Arena sống và xử lý lỗi bằng chính sách vận hành thay vì đóng một upcall stub mà C còn có thể gọi.
