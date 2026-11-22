# Callback từ luồng bản địa và giới hạn truy cập segment thuộc Arena riêng luồng

## 1. Vấn đề cốt lõi: native callback có thể chạy trên một thread khác

Foreign Function & Memory API (FFM) cho phép Java **gọi hàm C** (*downcall*) và cho C **gọi ngược Java** (*upcall*). Một upcall stub là một con trỏ hàm theo ABI C, được tạo bằng `Linker.upcallStub(...)` để native code có thể gọi một `MethodHandle` của Java.

Vấn đề xuất hiện khi native library tự tạo worker thread (ví dụ `pthread_create` trên Linux/macOS hoặc `CreateThread` trên Windows) rồi gọi con trỏ callback trên **worker thread đó**. Callback lúc này **không chạy trên Java thread ban đầu đã tạo arena**, mặc dù cùng một ứng dụng và cùng một JVM.

Ví dụ logic:

~~~text
Java thread MAIN
   |
   +-- Arena.ofConfined() --> MemorySegment DATA (owner = MAIN)
   |
   +-- Linker.upcallStub(targetJava, ..., Arena.ofShared())
   |                                     |
   |                                     +--> Function pointer CALLBACK
   |
   +-- FFM downcall invoke_native_thread(CALLBACK)
           |
           v
      C tạo OS worker thread
           |
           +--> CALLBACK(...)
                  |
                  v
             Java target chạy trên worker
                  |
                  +--> DATA.get(JAVA_INT, 0)
                             |
                             +--> WrongThreadException
                                  vì DATA thuộc confined arena
                                  của MAIN, không phải worker
~~~

**Điểm mấu chốt:** Upcall được phép trở lại Java **không làm một `MemorySegment` của `Arena.ofConfined()` trở nên chia sẻ được giữa threads**. Thread-confinement là quy tắc của **scope gắn với segment**, độc lập với việc mã gọi được xuất phát từ Java, JNI hay FFM.

Đường sửa thông dụng là **dùng `Arena.ofShared()` cho dữ liệu thật sự cần được truy cập từ native callback thread**, hoặc **copy giá trị cần thiết trên owner thread trước khi chuyển sang callback**. Đặc biệt, **arena quản lý upcall stub** và **arena quản lý dữ liệu callback truy cập** là hai quan hệ lifetime có thể hoàn toàn khác nhau.

Bài này tập trung vào **JDK 22+**, nơi `java.lang.foreign` đã được chuẩn hóa (JEP 454). Trên JDK 17, các ví dụ sau không biên dịch nguyên văn vì FFM API khi đó còn ở giai đoạn incubator.

### Mục tiêu

- Hiểu hành trình Java → native downcall → OS worker → Java upcall và các thread thực sự tham gia.
- Tạo `Linker.upcallStub`, `FunctionDescriptor`, `MethodHandle` đúng ABI.
- Phân biệt **thread chạy callback**, **thread sở hữu confined arena**, **scope/lifetime của upcall stub**.
- Giải thích vì sao một confined segment vẫn ném `WrongThreadException` dù callback có thể được JVM thực thi.
- Tạo ví dụ **Java 22+ và C11** với worker thread native trên Linux, macOS và Windows x64.
- Đọc đúng stdout khi callback trực tiếp thành công, callback worker với confined segment bị từ chối, và callback worker với shared segment thành công.
- Tránh uncaught exceptions trong upcall, use-after-close, callback bất đồng bộ quá hạn và deadlocks giữa thread native/Java.
- Chọn giữa shared arena, copy dữ liệu và một hàng đợi chuyển công việc về owner thread theo nhu cầu.

## 2. Hai hướng gọi phải phân biệt

FFM có hai hướng liên lạc:

| Hướng | Ai gọi ai? | API quan trọng | Thread thực thi |
| --- | --- | --- | --- |
| **Downcall** | Java → hàm native | `Linker.downcallHandle` và `MethodHandle.invokeExact` | Thường khởi đầu ở Java thread gọi downcall |
| **Upcall** | Hàm native → Java target | `Linker.upcallStub` và function pointer C | **Thread native thực tế gọi function pointer**, có thể khác thread khởi tạo |

Ví dụ chữ ký C:

~~~c
#include <stdint.h>

typedef int32_t (*callback_fn)(int32_t value);

int32_t invoke_direct(callback_fn callback, int32_t value);
int32_t invoke_native_thread(callback_fn callback, int32_t value);
~~~

Đây là **khai báo minh họa**; phần 7 sẽ cung cấp file C hoàn chỉnh.

- `invoke_direct` gọi `callback(value)` ngay trên luồng đang thực thi hàm C, thường là Java thread ban đầu đi vào downcall.
- `invoke_native_thread` tạo một **OS thread mới**, nhờ thread đó gọi `callback(value)`, đợi thread hoàn tất bằng join rồi mới trả kết quả.
- Cả hai nhận cùng kiểu **function pointer**, cùng `int32_t`; sự khác biệt là **đường đi của luồng**.

Đây là lý do callback được kiểm tra thành công trong một bài `qsort` đồng bộ **chưa chứng minh** callback sẽ truy cập được confined segment nếu native library gọi nó từ một worker thread độc lập.

### 2.1. Callback là function pointer, không phải Java native method

Trong FFM, Java tạo function pointer:

~~~java
MemorySegment stub = linker.upcallStub(
        targetMethodHandle, callbackDescriptor, arena);
~~~

Stub được truyền vào native C như một đối số pointer qua `ValueLayout.ADDRESS`. C gọi nó bằng cú pháp hàm thông thường, không cần khai báo Java method `native` tương ứng, không gọi `RegisterNatives` và không có tham số ngầm `JNIEnv *`/`jobject` ở chữ ký callback C.

Không lấy nhầm prototype của FFM callback:

~~~c
typedef int32_t (*callback_fn)(int32_t value);
~~~

với JNI native method:

~~~c
/* JNI native method nhận JNIEnv* và jobject/jclass ẩn. */
JNIEXPORT jint JNICALL Java_Package_Class_method(
        JNIEnv *env, jobject self, jint value);
~~~

Một `FunctionDescriptor` sai với C function pointer có thể gây lỗi ABI nghiêm trọng, kể cả JVM crash. Chỉ dùng kiểu/ABI đã kiểm tra phù hợp nền tảng.

## 3. Ba đối tượng có ba trách nhiệm khác nhau

**Thứ nhất — `MethodHandle target`**: quy định **mã Java nào** sẽ chạy khi native gọi callback. Target có thể được bind thêm một Java object hoặc `MemorySegment`. Bản thân target không quyết định thread ownership của vùng nhớ bị capture.

**Thứ hai — `MemorySegment stub`**: kết quả của `Linker.upcallStub(target, descriptor, arena)`. Đây là một **segment kích thước 0** mà địa chỉ là function pointer native. Stub có lifetime do arena được truyền vào `upcallStub` quyết định.

**Thứ ba — `MemorySegment data`**: vùng dữ liệu thật mà target Java có thể đọc/ghi. Data có thể được cấp phát từ **một arena khác**, với quy tắc confined/shared riêng.

Ví dụ:

~~~java
try (Arena stubArena = Arena.ofShared();
     Arena dataArena = Arena.ofConfined()) {

    MemorySegment data = dataArena.allocate(ValueLayout.JAVA_INT);

    MethodHandle target = /* MethodHandle Java capture data */;
    MemorySegment stub = Linker.nativeLinker().upcallStub(
            target,
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
            stubArena);

    // STUB thuộc shared arena.
    // DATA thuộc confined arena của Java thread hiện tại.
}
~~~

Đây là **pseudocode Java** vì biểu thức tạo MethodHandle được rút gọn; không phải source độc lập.

**Sai lầm cần tránh:** “Đã dùng `Arena.ofShared()` khi tạo upcall stub thì mọi `MemorySegment` được target truy cập đều shared”. Không đúng. `stubArena` chỉ quản lý **stub resource**. `dataArena` vẫn confined và chỉ owner thread được phép truy cập `data`.

Ngược lại, một stub tạo trong confined arena **cũng không phải lựa chọn tốt** khi muốn trao function pointer cho native worker không cùng owner. Trong bài thực hành, ta dùng **shared arena cho cả stub lẫn FFM library lookup**, để không nhầm lỗi của bản thân function pointer với lỗi confined data muốn minh họa.

## 4. Arena confined: owner thread là điều kiện bắt buộc

`Arena.ofConfined()` tạo arena có **owner thread**, thường chính là thread gọi phương thức factory đó. Mọi segment cấp phát từ arena này có thread-confinement:

~~~java
Arena arena = Arena.ofConfined();
MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
~~~

Trong ví dụ ngắn trên, giả sử chạy trên `main`, **chỉ owner thread** có thể dùng các phương thức memory access với `segment` và đóng arena.

Ví dụ truy cập hợp lệ:

~~~java
segment.set(ValueLayout.JAVA_INT, 0L, 32);
int value = segment.get(ValueLayout.JAVA_INT, 0L);
~~~

Ví dụ truy cập không hợp lệ:

~~~java
Thread worker = new Thread(() -> {
    segment.get(ValueLayout.JAVA_INT, 0L);
});
worker.start();
~~~

Đây là **mảnh code minh họa**, không phải chương trình hoàn chỉnh; nếu không catch exception, worker có thể in stack trace. Thread worker không sở hữu arena nên truy cập sẽ bị từ chối bằng `WrongThreadException` khi segment/scope còn sống.

Một thread native đi vào Java qua upcall cũng là **thread thực thi callback**, không được tự nhận thành owner của một confined arena đã được tạo trên `main`. Điều này vẫn đúng nếu callback sử dụng object hoặc record Java làm cầu nối tới segment đó.

### 4.1. `WrongThreadException` khác với `IllegalStateException`

| Vấn đề | Kết quả điển hình | Điều kiện |
| --- | --- | --- |
| Segment còn sống, đúng owner thread | Truy cập thành công nếu bounds/alignment hợp lệ | Confined và current thread = owner |
| Segment còn sống, **sai thread** | `WrongThreadException` | Confined và current thread khác owner |
| Arena đã close | `IllegalStateException` | Scope không còn sống |
| Truy cập vượt `byteSize()` | `IndexOutOfBoundsException` | Offset/length vượt ranh giới |
| Sai căn chỉnh | `IllegalArgumentException` | Alignment của layout/địa chỉ không đạt |

**`isAlive() == true` không suy ra thread hiện tại được phép truy cập.** Lifetime (sống/chết) và confinement (thread nào) là **hai trục kiểm tra khác nhau**. Khi cả scope đã hết hạn và thread cũng sai, không nên phụ thuộc vào thứ tự loại exception cụ thể; thiết kế phải bảo đảm cả hai điều kiện trước khi dùng.

### 4.2. `Arena.ofShared()` không phải tự động thread-safe

`Arena.ofShared()` cho phép các threads truy cập segments do nó cấp phát và cho phép close từ nhiều thread theo hợp đồng API. Nhưng:

- Không khóa tự động khi hai threads đọc/ghi cùng ô nhớ.
- Không biến thao tác `get` + `set` thành cập nhật atomic.
- Không tự giữ dữ liệu sống nếu owner đóng arena quá sớm.
- Không bảo đảm hàm C callback là thread-safe.
- Không giải quyết deadlock giữa native worker và Java thread.

Để đọc shared memory đúng, vẫn cần phân biệt **read-only sharing**, **dữ liệu được publish qua synchronization**, hoặc **atomic access** qua `VarHandle`/locking.

## 5. Thread native được JVM xử lý thế nào khi upcall?

Trong đường thực thi của FFM trên **HotSpot/OpenJDK**, một OS thread do native library tự tạo khi gọi upcall stub có thể **chưa phải Java thread được JVM attach**. FFM runtime đảm nhiệm phần nối thread đó vào JVM để chạy Java target, và implementation HotSpot đã mô tả cơ chế attach theo chế độ **daemon** và detach khi native thread kết thúc.

Lưu ý phạm vi kết luận:

- Đây là **chi tiết thực thi FFM của HotSpot/OpenJDK**, không phải lời hứa rằng mọi JVM khác sẽ dùng cùng daemon policy.
- Không cần tự gọi `AttachCurrentThread` chỉ để làm ví dụ FFM callback chạy bằng upcall stub trên HotSpot. Không tự ý `DetachCurrentThread` từ Java callback.
- Nếu bạn **chủ động viết JNI code** trên native worker, quy tắc JNI attach/detach của code đó là chủ đề riêng: `JNIEnv *` là thread-local và `AttachCurrentThread` không đồng nghĩa `AttachCurrentThreadAsDaemon`.
- Việc VM có thể thực thi Java callback **không làm confined arena chuyển owner sang thread mới**.
- Native worker có thể có context class loader khác Java thread khởi tạo; không mặc định callback sẽ tìm thấy application classes bằng tên qua ngữ cảnh class loader của thread.
- `ThreadLocal`, thread name, interrupts và Java thread context có thể khác so với Java main; không sử dụng chúng làm giả định ngầm nếu callback cần dữ liệu chính xác.

**Cách an toàn:** target MethodHandle được bind tới code Java đã xác định ở thời điểm tạo upcall stub; truyền dữ liệu bằng các kiểu primitive, Java objects an toàn để chia sẻ, hoặc shared segments có vòng đời/đồng bộ đúng.

## 6. Upcall stub không được để exception tràn ra ngoài

JDK 22 `Linker.upcallStub` quy định target **không được ném exception ra ngoài**. Nếu một exception thoát khỏi MethodHandle đích qua native callback boundary, **JVM có thể kết thúc đột ngột**; thực tế javadoc cảnh báo JVM sẽ terminate abruptly.

Vì vậy **không** viết:

~~~java
static int unsafeCallback(MemorySegment confinedData, int x) {
    return confinedData.get(ValueLayout.JAVA_INT, 0L) + x;
    // Nếu native thread không là owner -> WrongThreadException
    // sẽ đi ra khỏi Java callback: có thể làm VM terminate.
}
~~~

Đây là **một static Java method minh họa hành vi sai**, không gọi trực tiếp trong phần demo.

Thay vào đó, **chặn lỗi bên trong target và chuyển thành kết quả C hợp lệ**:

~~~java
private static final int WRONG_THREAD = -700;
private static final int CALLBACK_ERROR = -701;

static int safeCallback(MemorySegment data, int x) {
    try {
        return data.get(ValueLayout.JAVA_INT, 0L) + x;
    } catch (WrongThreadException ex) {
        return WRONG_THREAD;
    } catch (Throwable unexpected) {
        // Tuyệt đối không cho Throwable thoát qua native boundary.
        // Trong production nên ghi chẩn đoán qua kênh an toàn.
        return CALLBACK_ERROR;
    }
}
~~~

Đây là snippet Java; `MemorySegment`, `ValueLayout` cần import và cả hai constants được định nghĩa trong class. `WrongThreadException` thuộc `java.lang` ở JDK 22 nên không cần import.

Với một C function callback trả `int32_t`, hai sentinel âm ở trên là cách demo **báo lỗi qua ABI**. **Không dùng sentinel va chạm với miền kết quả hợp lệ trong sản phẩm**; có thể thiết kế thêm status code, output parameter hoặc kết quả dạng struct, hoặc ghi trạng thái lỗi vào một object thread-safe để Java đọc sau downcall.

Bắt `Throwable` là **mạng an toàn cuối cùng cho demo**. Trong hệ thống thực, hãy thiết kế handling cho `Error`/out-of-memory một cách thận trọng và không thực hiện thêm thao tác Java phức tạp khi lỗi nghiêm trọng. Mục đích là không để exception vô tình vượt qua function-pointer ABI.

## 7. Ví dụ đầy đủ: C tạo worker thread rồi gọi Java callback

Chương trình thực hành chứa:

1. Một thư viện C xuất hai hàm `invoke_direct` và `invoke_native_thread`.
2. Hai hàm nhận cùng kiểu callback: `int32_t (*)(int32_t)`.
3. Java tạo một confined data segment và một shared data segment; cả hai lưu `32`.
4. Java tạo **hai upcall stubs đều có shared lifetime**:
   - Stub A bind tới confined data.
   - Stub B bind tới shared data.
5. Java gọi ba lần:
   - `invoke_direct(stubA, 10)`: chạy trên Java main thread, đọc confined data hợp lệ → `42`.
   - `invoke_native_thread(stubA, 10)`: worker thread đọc confined data → callback bắt `WrongThreadException` và trả `-700`.
   - `invoke_native_thread(stubB, 10)`: worker thread đọc shared data → `42`.

Điều quan trọng là **C đợi worker kết thúc bằng join trước khi hàm trả**. Nhờ đó Java có thể đóng arena sau khi downcall hoàn thành mà không sợ callback sẽ còn xảy ra về sau.

### 7.1. Cấu trúc thư mục

~~~text
native-thread-ffm/
  native_thread_callback.c
  NativeThreadCallbackDemo.java

Sau khi build:
  libthread_callback.so       (Linux)
  libthread_callback.dylib    (macOS)
  thread_callback.dll         (Windows)
  NativeThreadCallbackDemo.class
~~~

Chọn một hệ điều hành để build; không cần tạo cả ba file thư viện trên cùng máy.

### 7.2. File C hoàn chỉnh: `native_thread_callback.c`

~~~c
#include <stdint.h>
#include <stdlib.h>

#if defined(_WIN32)
    #include <windows.h>
    #define EXPORT __declspec(dllexport)
#else
    #include <pthread.h>
    #define EXPORT __attribute__((visibility("default")))
#endif

/*
 * Demo chỉ dùng x64/ARM64 ABI phổ biến.
 * int32_t = Java ValueLayout.JAVA_INT (carrier int).
 * Callback KHÔNG có JNIEnv* tham số ẩn.
 */
typedef int32_t (*callback_fn)(int32_t);

typedef struct {
    callback_fn callback;
    int32_t input;
    int32_t result;
} Request;

static void run_callback(Request *request) {
    request->result = request->callback(request->input);
}

#if defined(_WIN32)

static DWORD WINAPI thread_entry(LPVOID argument) {
    run_callback((Request *) argument);
    return 0;
}

#else

static void *thread_entry(void *argument) {
    run_callback((Request *) argument);
    return NULL;
}

#endif

/* Gọi callback trực tiếp trên thread gọi xuống C. */
EXPORT int32_t invoke_direct(
        callback_fn callback, int32_t input) {
    if (callback == NULL) {
        return -500;
    }
    return callback(input);
}

/*
 * Tạo OS worker thread, cho worker gọi callback,
 * JOIN worker trước khi hàm trả để bảo đảm lifetime.
 */
EXPORT int32_t invoke_native_thread(
        callback_fn callback, int32_t input) {
    if (callback == NULL) {
        return -500;
    }

    Request request = {callback, input, -502};

#if defined(_WIN32)
    HANDLE thread = CreateThread(
            NULL, 0, thread_entry, &request, 0, NULL);

    if (thread == NULL) {
        return -501;  /* Không tạo được worker. */
    }

    DWORD waitResult = WaitForSingleObject(thread, INFINITE);
    if (waitResult != WAIT_OBJECT_0) {
        /* Không thể an toàn trả về khi thread có thể còn
           giữ con trỏ tới request nằm trên stack. */
        abort();
    }

    CloseHandle(thread);
#else
    pthread_t thread;

    if (pthread_create(
            &thread, NULL, thread_entry, &request) != 0) {
        return -501;  /* Không tạo được worker. */
    }

    if (pthread_join(thread, NULL) != 0) {
        /* Điều kiện bất thường: không return khi worker
           có thể tiếp tục dùng request trên stack. */
        abort();
    }
#endif

    return request.result;
}
~~~

#### Giải thích các quyết định trong C

- `EXPORT` đảm bảo symbol được export khỏi thư viện native: trên Windows dùng `__declspec(dllexport)`, trên Linux/macOS dùng thuộc tính visibility thông dụng của GCC/Clang.
- `int32_t` có bề rộng cố định 32 bit, thuận tiện khớp `ValueLayout.JAVA_INT`.
- `callback_fn` có **chính xác một tham số `int32_t`**, trả `int32_t`; đây là ABI contract cho upcall stub.
- `invoke_direct` **không tạo thread**: callback thường chạy trong cùng Java thread thực hiện downcall.
- `invoke_native_thread` tạo worker thật, truyền địa chỉ `Request` nằm trên stack C. Bảo đảm **join trước khi return** để không có dangling pointer tới `request`.
- Native worker không nhận `JavaVM *` hay `JNIEnv *`; demo sử dụng **FFM upcall stub**, không viết native JNI callback thủ công.
- `-500` là lỗi callback pointer rỗng; `-501` là lỗi tạo thread; `-502` chỉ là giá trị khởi tạo không được trả khi worker hoàn tất bình thường. Các mã âm này được phân biệt với `-700` (wrong thread) và `-701` (callback exception) ở phía Java.
- Các nhánh `abort()` khi join/wait thất bại là lựa chọn **fail-fast cho demo** vì không thể an toàn return và giải phóng stack frame đang có thể bị worker dùng. Ứng dụng production nên có vòng đời worker và error recovery phù hợp hơn.
- Ví dụ dùng **64-bit JDK và native compiler cùng kiến trúc**, để tránh khác biệt calling convention của Windows 32-bit.

**Không cần `jni.h` trong file C này**, vì thư viện dùng C ABI bình thường và được gọi qua FFM. Không có `JNI_OnLoad` hoặc method `Java_*`.

### 7.3. File Java hoàn chỉnh: `NativeThreadCallbackDemo.java`

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

public final class NativeThreadCallbackDemo {
    private static final int WRONG_THREAD = -700;
    private static final int CALLBACK_ERROR = -701;

    private NativeThreadCallbackDemo() {
    }

    /*
     * MethodHandle đích sẽ được bind trước tham số data,
     * để C chỉ phải truyền một int32_t.
     *
     * KHÔNG để exception thoát ra khỏi FFM upcall!
     */
    private static int readMemory(MemorySegment data, int increment) {
        try {
            int base = data.get(ValueLayout.JAVA_INT, 0L);
            return base + increment;
        } catch (WrongThreadException ex) {
            return WRONG_THREAD;
        } catch (Throwable ex) {
            return CALLBACK_ERROR;
        }
    }

    private static MethodHandle boundCallback(MemorySegment data)
            throws ReflectiveOperationException {
        MethodHandle target = MethodHandles.lookup().findStatic(
                NativeThreadCallbackDemo.class,
                "readMemory",
                MethodType.methodType(
                        int.class, MemorySegment.class, int.class));

        // (MemorySegment, int) -> int
        // Sau bind: (int) -> int, đúng callback_fn ở C.
        return MethodHandles.insertArguments(target, 0, data);
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        FunctionDescriptor callbackDescriptor =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.JAVA_INT);

        FunctionDescriptor invokeDescriptor =
                FunctionDescriptor.of(
                        ValueLayout.JAVA_INT,
                        ValueLayout.ADDRESS,
                        ValueLayout.JAVA_INT);

        Path path = Path.of(
                System.mapLibraryName("thread_callback"))
                .toAbsolutePath();

        /*
         * Arena shared cấp phát cả stubs và shared data.
         * Confined arena cấp phát dữ liệu CHỈ cho main.
         */
        try (Arena sharedArena = Arena.ofShared();
             Arena confinedArena = Arena.ofConfined()) {

            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, sharedArena);

            MethodHandle direct = linker.downcallHandle(
                    library.find("invoke_direct").orElseThrow(),
                    invokeDescriptor);

            MethodHandle threaded = linker.downcallHandle(
                    library.find("invoke_native_thread").orElseThrow(),
                    invokeDescriptor);

            MemorySegment confinedData =
                    confinedArena.allocate(ValueLayout.JAVA_INT);

            MemorySegment sharedData =
                    sharedArena.allocate(ValueLayout.JAVA_INT);

            confinedData.set(ValueLayout.JAVA_INT, 0L, 32);
            sharedData.set(ValueLayout.JAVA_INT, 0L, 32);

            /*
             * Cả hai STUB đều thuộc sharedArena.
             * Khác biệt chỉ nằm ở DATA mà target capture.
             */
            MemorySegment confinedStub = linker.upcallStub(
                    boundCallback(confinedData),
                    callbackDescriptor, sharedArena);

            MemorySegment sharedStub = linker.upcallStub(
                    boundCallback(sharedData),
                    callbackDescriptor, sharedArena);

            int onMainThread =
                    (int) direct.invokeExact(confinedStub, 10);

            int onWorkerConfined =
                    (int) threaded.invokeExact(confinedStub, 10);

            int onWorkerShared =
                    (int) threaded.invokeExact(sharedStub, 10);

            if (onMainThread != 42
                    || onWorkerConfined != WRONG_THREAD
                    || onWorkerShared != 42) {
                throw new IllegalStateException(
                        "Unexpected callback result");
            }

            System.out.println("direct confined=42");
            System.out.println(
                    "native thread confined=WrongThreadException caught");
            System.out.println("native thread shared=42");
        }
    }
}
~~~

#### Chỗ quan trọng nhất trong Java

**A. Cặp upcall/downcall signature**

`callbackDescriptor`:

~~~text
(int) -> int

C callback: int32_t (*callback_fn)(int32_t)
FFM callback FunctionDescriptor:
    of(JAVA_INT, JAVA_INT)
Java target sau bind:
    (int) -> int
~~~

`invokeDescriptor`:

~~~text
(MemorySegment, int) -> int

C function: int32_t invoke_native_thread(
    callback_fn callback, int32_t input)

FFM FunctionDescriptor:
    of(JAVA_INT, ADDRESS, JAVA_INT)
Java invokeExact:
    (int) threaded.invokeExact(stub, 10)
~~~

**B. Hai arenas cố ý khác biệt**

- `sharedArena` cấp phát upcall stubs và `sharedData`, đồng thời quản lý library lookup. Native thread được phép sử dụng **sharedData** khi scope còn sống.
- `confinedArena` cấp phát `confinedData` trên Java main thread. Gọi `data.get(...)` từ native worker (qua Java target) sẽ bị từ chối bởi `WrongThreadException`.
- Stub bind tới `confinedData` vẫn được tạo từ **sharedArena**. Điều này giúp quan sát đúng vấn đề **data confinement**, không lẫn với lỗi function pointer có scope confined.

**C. `MethodHandles.insertArguments` không copy vùng nhớ**

`boundCallback(confinedData)` tạo target `(int) -> int` nhưng nó chỉ bind **Java reference tới `confinedData`**. Nó không copy bytes, không đổi owner thread và không chuyển confined scope sang shared scope.

**D. Tại sao lỗi không làm JVM crash?**

`readMemory` **catch `WrongThreadException` ngay trong callback** và trả `-700` theo ABI. Không có Java exception vượt qua native function pointer. Demo cũng có fallback `catch (Throwable)` trả `-701` cho lỗi không mong đợi, thay vì để exception bay qua upcall stub.

**E. Tại sao có thể close arenas khi kết thúc khối `try`?**

C đã **join native worker trước khi trả từ downcall**. Vì vậy khi Java kết thúc lần `threaded.invokeExact(...)` cuối, không còn worker nào giữ upcall pointer của ví dụ. Hai arenas được đóng khi ra khỏi `try`; không ai còn gọi stub hoặc truy cập segments.

## 8. Biên dịch và chạy trên các nền tảng

### 8.1. Chuẩn bị

- Cài **JDK 22 trở lên**. Kiểm tra lệnh `javac -version` và `java -version` cùng trỏ tới JDK đó.
- Dùng compiler hỗ trợ C11 cùng kiến trúc CPU với JVM.
- Chạy lệnh từ thư mục chứa `NativeThreadCallbackDemo.java` và `native_thread_callback.c`.
- Không cần `javac -h` và không cần `jni.h` vì file C không có JNI native method.

Biên dịch Java:

~~~bash
javac NativeThreadCallbackDemo.java
~~~

### 8.2. Linux x64 / ARM64 (GCC hoặc Clang)

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared -pthread \
  native_thread_callback.c -o libthread_callback.so
~~~

`-pthread` bật cấu hình cần thiết cho `pthread_create`/`pthread_join`. Trên các bản Linux hiện đại, pthread có thể nằm trong libc nhưng vẫn nên dùng cờ này để build rõ ràng.

### 8.3. macOS x64 / ARM64 (Clang)

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib -pthread \
  native_thread_callback.c -o libthread_callback.dylib
~~~

### 8.4. Windows x64 (Visual Studio Developer Command Prompt)

~~~bat
cl /nologo /W4 /LD native_thread_callback.c /link /OUT:thread_callback.dll
~~~

Nhánh `#if defined(_WIN32)` dùng `CreateThread` và `WaitForSingleObject` từ Win32. Chạy trong **x64 Native Tools Command Prompt**, dùng 64-bit JDK. MSVC C có hỗ trợ định nghĩa `int32_t` trong `stdint.h`.

### 8.5. Chạy

Linux/macOS:

~~~bash
java --enable-native-access=ALL-UNNAMED NativeThreadCallbackDemo
~~~

Windows:

~~~bat
java --enable-native-access=ALL-UNNAMED NativeThreadCallbackDemo
~~~

`--enable-native-access=ALL-UNNAMED` cấp native access cho chương trình classpath, cần cho các **restricted FFM methods** như `libraryLookup`, `downcallHandle` và `upcallStub`. JDK 22 không yêu cầu `--enable-preview`.

File shared library phải nằm trong **thư mục làm việc hiện tại**, vì `Path.of(System.mapLibraryName("thread_callback")).toAbsolutePath()` xây absolute path dựa trên thư mục chạy. Ví dụ dùng FFM `libraryLookup(Path, Arena)`, nên không cần dựa vào `-Djava.library.path` để tìm file như `System.loadLibrary` của JNI.

### 8.6. Stdout chính xác khi chạy thành công

~~~text
direct confined=42
native thread confined=WrongThreadException caught
native thread shared=42
~~~

Giải thích:

1. `direct` gọi C đồng bộ rồi C gọi stub ngay trên thread Java main; `confinedData.get` được phép, đọc `32 + 10 = 42`.
2. `threaded` tạo native OS thread; callback chạy trên thread mới và cố đọc `confinedData` do Java main sở hữu; Java FFM ném `WrongThreadException`, target catch rồi trả `-700`; main in dòng “caught”.
3. Lần tiếp theo native worker đọc `sharedData` thuộc `Arena.ofShared()`, nên nhận `32 + 10 = 42`; C join worker trước khi trả về.
4. Tất cả output được **in ở Java main sau khi downcalls trả**, tránh thứ tự stdout không xác định do chạy nhiều threads.

Nếu môi trường không hỗ trợ tạo OS thread hoặc C/Java ABI khác dự kiến, chương trình **không** in ba dòng trên mà đi vào nhánh lỗi. Không coi stdout debug của một lỗi bất kỳ là kết quả thành công.

## 9. Vì sao không tạo confined upcall stub cho worker?

Một lập trình viên có thể viết:

~~~java
try (Arena confined = Arena.ofConfined()) {
    MemorySegment stub = linker.upcallStub(
            target, callbackDescriptor, confined);

    // Đưa stub tới một C worker thread tự tạo...
}
~~~

Đây là snippet minh họa, thiếu biến `linker` và `target`; **không dùng cho demo worker**.

`Linker.upcallStub` nhận Arena để quản lý **lifetime của function pointer**. Javadoc của JDK 22 quy định tạo stub bằng confined arena từ thread không phải owner có thể ném `WrongThreadException`; stub cũng không còn hợp lệ sau khi arena đó đóng.

Do đó với callback được dùng từ native worker thread, nên dùng **shared arena có vòng đời đủ dài** cho function pointer, và bảo đảm worker hoàn tất trước khi đóng. Điều này tránh phụ thuộc ngẫu nhiên vào confinement/closure của chính upcall stub.

**Nhưng chuyển stub sang shared không đủ để sửa target truy cập confined data**. Cần thay đổi ownership của data hoặc cách chuyển dữ liệu.

## 10. Hai cách sửa đúng lỗi confined data

### 10.1. Phương án A: cấp phát dữ liệu trong `Arena.ofShared()`

Đây là cách áp dụng trong demo phần 7.

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_INT);
    value.set(ValueLayout.JAVA_INT, 0L, 32);

    MethodHandle target = /* bind value vào callback */;
    MemorySegment stub = linker.upcallStub(
            target, descriptor, arena);

    // C worker được phép truy cập value qua callback,
    // miễn còn sống và được đồng bộ đúng.
}
~~~

Đây là **pseudocode Java** (phần tạo MethodHandle được rút gọn).

Cần quản lý thêm:

- **Không đóng arena** khi bất kỳ callback nào vẫn có thể xảy ra.
- Nếu Java main và native callback đồng thời **ghi/đọc cùng dữ liệu**, dùng synchronization hoặc `VarHandle` access modes phù hợp, không chỉ dựa vào tính “shared”.
- Nếu C có nhiều worker threads, xác định lifecycle và in-flight callback count rõ ràng.
- Nếu C lưu pointer vào biến global, phải có API `unregister/stop` và ack trước `arena.close()`.
- Shared arena giúp **quyền truy cập qua thread** hợp lệ, không xác nhận callback protocol đúng.

### 10.2. Phương án B: copy giá trị sang Java primitive trước khi upcall

Nếu callback chỉ cần một vài scalar, cách an toàn và dễ kiểm soát hơn là **đọc từ confined segment trên owner thread trước**, rồi bind **giá trị primitive** vào target:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandle;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// Đoạn nằm trong một method của owner thread.
int base = confinedData.get(ValueLayout.JAVA_INT, 0L);

MethodHandle add = MethodHandles.lookup().findStatic(
        MyCallbacks.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));

// static int add(int base, int increment) { return base + increment; }
MethodHandle target = MethodHandles.insertArguments(add, 0, base);

// target chỉ mang Java int, không giữ confined segment.
~~~

Đây là **snippet minh họa**, `MyCallbacks` chỉ là tên class giả định. Trong code thực, định nghĩa method `add` và tạo upcall stub bằng `Arena.ofShared()` đủ sống cho native callback.

Ưu điểm:

- Native worker callback không đọc confined data.
- Không mở quyền chia sẻ native memory không cần thiết.
- Dữ liệu primitive đã được **copy** tại thời điểm bind (snapshot), vì thế thay đổi confined segment sau đó **không tự cập nhật callback**.
- Giảm nguy cơ lỗi temporal bounds/close của native data khi callback bất đồng bộ.

Nếu callback cần lượng dữ liệu lớn hoặc cần cập nhật qua lại, copy toàn bộ mỗi lần có thể tốn chi phí; cân nhắc shared arena hoặc message queue.

### 10.3. Phương án C: chuyển công việc về owner thread

Nếu yêu cầu bắt buộc xử lý một confined segment **trên đúng owner Java thread**, callback trên native worker không nên dùng segment trực tiếp. Thay vào đó:

~~~text
Native worker gọi upcall
       |
       v
Java callback nhận event/primitive/immutable payload
       |
       v
Đưa task vào thread-safe queue của owner
       |
       v
Callback trả status nhanh cho C (không đợi owner nếu có vòng chờ)
       |
       v
Java owner thread xử lý queue
       |
       v
Owner đọc/ghi confined segment hợp lệ
~~~

Đây là **sơ đồ giao thức**, không phải một API FFM tự làm sẵn. Java `BlockingQueue` hoặc event loop có thể dùng để điều phối, nhưng phải thiết kế **lifecycle và backpressure** cho phù hợp.

**Cảnh báo deadlock:** nếu Java owner đang chặn trong `invoke_native_thread` đợi `pthread_join`, trong khi callback của worker **đợi owner xử lý queue và trả kết quả đồng bộ**, cả hai có thể chờ nhau vô hạn. Khi dùng queue trong trường hợp này, callback nên trả nhanh và owner xử lý **sau khi downcall trả**, hoặc kiến trúc phải cho phép owner xử lý event trong lúc native chạy.

## 11. Callback bất đồng bộ: lifetime thường nguy hiểm hơn thread ownership

Trong demo, `invoke_native_thread` **join worker trước khi trả**, nên Java đóng arena an toàn sau downcall. Một native API thực tế có thể khác:

~~~c
/* API mô tả ý tưởng, không có implementation trong demo. */
void register_callback(callback_fn cb);
void launch_background_job(void);
void unregister_callback_and_wait(void);
~~~

Nếu Java làm:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment stub = linker.upcallStub(
            target, descriptor, arena);
    // native_register_callback(stub);
    // native_launch_background_job();
} // arena.close() trong lúc native worker có thể gọi callback!
~~~

Đoạn này là **pseudocode nguy hiểm**. Sau khi Arena đóng, function pointer của upcall stub không còn hợp lệ; nếu C gọi nó muộn hơn có thể gây **crash hoặc memory corruption** chứ không chỉ một Java exception dễ xử lý.

Giao thức đúng:

~~~text
Java tạo shared arena
    |
    +-- tạo stub, dữ liệu callback cần thiết
    +-- register callback với native library
    +-- start native worker(s)
    |
    +-- normal operation: callbacks có thể đến
    |
    +-- stop accepting work / begin shutdown
    +-- unregister callback hoặc gửi stop
    +-- chờ native xác nhận không còn in-flight callback
    +-- join workers / release native registrations
    |
    +-- arena.close() sau cùng
~~~

Một shared Arena là **bộ quản lý lifetime**, không phải magic reference counter tự biết bên C còn lưu pointer hay không. Java chỉ được close sau khi đã nhận đủ tín hiệu hoàn tất từ native layer.

### 11.1. Callback trên thread mới có tự bị JVM “join” không?

Không nên dựa vào điều đó. FFM runtime có thể attach worker để chạy Java, nhưng **JVM không sở hữu giao thức vòng đời của OS worker mà native library tạo**. Worker có thể chạy lâu hơn lời gọi downcall, hoặc outlive Java scope nếu native library không cung cấp stop/join hợp lệ.

Việc một thread được attach theo chế độ daemon trong HotSpot **không bảo đảm công việc native được hoàn tất trước JVM shutdown**. Thiết kế production phải chủ động stop workers, chờ callbacks hoàn thành và giải phóng stub trước khi unload library/VM.

### 11.2. Đừng đóng shared arena để “hủy callback đang chạy”

`Arena.close()` không tương đương một phép hủy thread. Nếu callback/downcall đang truy cập segment, close có thể bị từ chối bằng `IllegalStateException` theo quy tắc temporal safety, hoặc native code có thể dùng pointer không còn hợp lệ. Cần hủy/đợi ở **protocol layer**, không dùng memory deallocation làm tín hiệu shutdown.

## 12. Upcall nhận pointer native: vấn đề ownership khác

Phần demo chỉ truyền `int32_t` nên không phải xử lý raw pointers. Thực tế callback thường nhận một `void *` hoặc `struct *` do C cung cấp:

~~~c
/* Ví dụ ABI minh họa, không thuộc file C chạy ở phần 7. */
typedef int32_t (*read_fn)(const int32_t *ptr);
~~~

Ở Java, descriptor có thể sử dụng:

~~~java
FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS.withTargetLayout(
                ValueLayout.JAVA_INT));
~~~

Khi foreign code gọi upcall stub với một pointer argument như vậy, target Java nhận `MemorySegment` đại diện pointer có kích thước theo target layout, ví dụ 4 bytes cho một `int32_t`. Javadoc Linker JDK 22 mô tả segment của pointer argument có một **scope luôn sống** (global scope) thay vì tự kế thừa Arena mà C đã cấp phát con trỏ.

**Điều này rất quan trọng:**

- “Java nhận được `MemorySegment`” **không chứng minh** vùng C pointer còn hợp lệ lâu dài.
- Scope của segment pointer argument **không quản lý** thời điểm C có thể `free(ptr)`.
- Callback phải kiểm tra null pointer, ABI/size và đọc/copy trong thời gian native bảo đảm buffer còn sống.
- Không giữ pointer segment để dùng sau callback trừ khi native API có ownership contract rõ ràng, hoặc copy nội dung sang Java-managed memory/shared arena phù hợp.
- Trên native worker, pointer segment argument có thể không bị confined như Java segment do `Arena.ofConfined()` tạo; **nguồn gốc scope khác nhau**, không nên khái quát “mọi segment đều do Java arena tạo”.

Nếu C truyền pointer tới buffer trên stack native worker, con trỏ có thể hết hạn ngay khi C function trả. Đừng nhầm lifetime của Java wrapper với lifetime của native allocation.

## 13. JNI AttachCurrentThread khác đường upcall FFM

Nếu dùng JNI truyền thống từ một native OS thread, phải attach thread trước khi gọi JNI:

~~~c
/* JNI pseudocode, không thuộc FFM C demo. */
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **) &env, NULL);
if (rc == JNI_OK) {
    /* Gọi JNI từ ĐÚNG thread này. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

Code này thuộc **JNI Invocation API**, cần `JavaVM *vm` hợp lệ và không có Java frames trên stack khi detach. `JNIEnv *` là **thread-specific**; không sao chép từ Java main/JNI worker khác. `AttachCurrentThreadAsDaemon` khác `AttachCurrentThread` về daemon status của thread vừa attach.

Với upcall stub FFM:

~~~text
Java tạo MethodHandle + FunctionDescriptor
     |
     v
Linker.upcallStub(...) -> C function pointer
     |
     v
Native OS worker gọi function pointer
     |
     v
FFM runtime/VM transition đưa worker vào Java target
~~~

Trong trường hợp HotSpot/OpenJDK, FFM runtime thực hiện attach cho worker chưa attach (theo implementation). Bạn **không** phải khai báo callback FFM như JNI method hay tự truyền `JNIEnv *` vào `FunctionDescriptor` nếu C ABI thật sự chỉ có `int32_t(int32_t)`.

**Sai lầm phổ biến:** nghĩ rằng “FFM đã attach native worker thì confined segment của Java main sẽ dùng được”. Không. **Thread attachment** chỉ làm VM có thể chạy Java code; **confinement** vẫn chỉ cho owner thread của Arena truy cập segment.

## 14. Thread identity, virtual threads và callback context

Upcall từ C worker chạy trong ngữ cảnh **carrier OS thread/native thread** đã đi vào JVM. Đừng giả định:

- Callback sẽ chạy trên `Thread.currentThread()` giống main.
- Callback sẽ chạy trên cùng virtual thread đã tạo stub.
- `ThreadLocal` của caller Java được copy sang callback.
- Context class loader của callback giống caller Java.
- Java transaction/security/logging context tự động được propagation.
- Một callback native worker sẽ được sắp lịch trên Executor/Java thread mà bạn đã tạo sẵn.

Nếu muốn giữ một context nghiệp vụ, hãy **truyền context rõ ràng** qua object được bind trong MethodHandle, hoặc qua mã ID/token có mapping thread-safe với vòng đời xác định.

Với nhiều concurrent callbacks, target cũng phải hỗ trợ **reentrancy**. Ví dụ callback ghi vào `ArrayList` không synchronized từ nhiều OS threads có thể gây race; thay bằng concurrent queue hoặc event loop, hoặc đồng bộ có kiểm soát.

### 14.1. Context class loader và class lookup

Một native-attached thread thường không có Java application call stack “phía trên” giống Java main. Nếu callback cần load class hoặc tài nguyên phụ thuộc class loader, nên giữ `Class<?>` hoặc một class loader phù hợp **từ Java context rõ ràng**, không dựa ngẫu nhiên vào thread context class loader của OS worker.

Đặc biệt với plugin/hot reload, target MethodHandle hoặc Java object được bind có thể **giữ class loader reachable** lâu hơn dự kiến. Phải dọn native registration và release stubs/handlers cùng vòng đời plugin.

## 15. Đồng bộ dữ liệu và visibility khi dùng shared arena

Trong demo, Java main ghi `32` vào `sharedData` **trước khi** yêu cầu C tạo worker; worker chỉ đọc. C dùng `pthread_create`/`pthread_join` (hoặc Win32 thread creation/wait) để tổ chức thread lifecycle rõ ràng.

Với chương trình phức tạp hơn, không được khẳng định mọi inter-thread read/write sẽ có visibility thích hợp chỉ vì `Arena.ofShared()`. Một arena shared cho phép truy cập từ nhiều thread nhưng **không áp đặt memory-ordering** cho thuật toán.

Khi callback cập nhật dữ liệu:

~~~java
// Minh họa ý tưởng; DATA được tạo từ Arena.ofShared().
int current = sharedData.get(ValueLayout.JAVA_INT, 0L);
sharedData.set(ValueLayout.JAVA_INT, 0L, current + 1);
~~~

Phép đọc rồi ghi trên **hai thao tác** không phải atomic read-modify-write; hai callbacks đồng thời có thể làm mất cập nhật.

Nếu cần atomic counter, dùng VarHandle với access mode phù hợp:

~~~java
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

VarHandle intVar = ValueLayout.JAVA_INT.varHandle();

// Trên segment có alignment đúng, thuộc scope shared còn sống:
int previous = (int) intVar.getAndAdd(sharedData, 0L, 1);
~~~

Đây là snippet, không phải source độc lập. Kiểm tra `intVar.isAccessModeSupported(VarHandle.AccessMode.GET_AND_ADD)` khi cần hỗ trợ layout/ABI khác nhau.

**Hai lớp an toàn tách biệt:**

1. **Spatial/temporal/thread access:** MemorySegment, Arena scope, bounds và `WrongThreadException`.
2. **Dữ liệu đồng thời:** atomic VarHandle, locks, happens-before và native synchronization.

Thiết kế callback đúng phải đáp ứng **cả hai**.

## 16. Những anti-pattern phổ biến

### 16.1. Đổi riêng Arena của stub, nhưng không đổi Arena của data

~~~text
Arena.ofShared() -> upcall stub        [đúng hướng]
Arena.ofConfined() -> captured data    [vẫn chỉ main được đọc]
Native worker -> callback -> data.get  [WrongThreadException]
~~~

**Cách sửa:** dùng shared data hoặc chuyển snapshot/việc truy cập về owner thread.

### 16.2. Bắt exception sau khi `invokeExact` thay vì trong upcall

~~~java
try {
    // C worker gọi target Java có thể ném WrongThreadException.
    // (int) downcall.invokeExact(stub, 10);
} catch (WrongThreadException ex) {
    // KHÔNG đủ để bảo vệ upcall: exception không được phép
    // thoát qua native function-pointer boundary.
}
~~~

Đây là pseudocode minh họa lỗi. Catch ở Java **bên ngoài downcall** không thay cho catch **bên trong target callback**. Với FFM upcall, một exception thoát target có thể khiến JVM terminate đột ngột trước khi caller Java nhận được nó.

### 16.3. Native giữ callback pointer sau khi Java đã close arena

~~~text
Java register(callback)
Java close arena
native worker callback(...)  -> function pointer đã hết lifetime
~~~

Đây có thể là **JVM crash**. Cần `unregister + wait for completion` trước close.

### 16.4. Native worker chờ Java main, Java main chờ native worker

~~~text
MAIN:
  downcall invoke_native_thread(...)
     -> C pthread_join(worker)

WORKER:
  upcall callback(...)
     -> chờ MAIN xử lý một task đồng bộ

MAIN không thể xử lý task vì đang chờ join.
WORKER không thể return vì đang chờ MAIN.
=> deadlock
~~~

Sửa bằng cách callback trả nhanh và đưa dữ liệu vào queue, hoặc dùng kiến trúc không giữ Java main chặn trong synchronous downcall trong lúc cần xử lý callback.

### 16.5. Dùng confined arena từ native thread dù không có shared mutable data

Khi callback chỉ cần một scalar `int`, **không nhất thiết chia sẻ native memory**. Đọc scalar ở owner trước, bind vào MethodHandle hoặc đưa qua Java object immutable; giảm rủi ro đúng chủ đề hơn việc chuyển mọi thứ sang shared.

### 16.6. Nghĩ rằng thread đã attach VM thì tự được phép close mọi arena

`Arena.ofConfined()` chỉ owner thread tạo arena mới có quyền close. Một thread native upcall, dù có thể chạy Java, gọi `confinedArena.close()` từ thread không phải owner sẽ ném `WrongThreadException`. Đừng chuyển trách nhiệm cleanup sang callback ngẫu nhiên; owner xử lý sau khi các callbacks hoàn tất.

## 17. Bảng chẩn đoán và sửa lỗi

| Hiện tượng | Nguyên nhân thường gặp | Khắc phục |
| --- | --- | --- |
| Callback từ main đọc được data, callback từ C worker thất bại | Captured segment thuộc `Arena.ofConfined()` của main | Shared arena hoặc copy primitive/queue về owner |
| `WrongThreadException` | Truy cập/close confined scope từ thread khác | Kiểm tra owner thread và data arena thực tế |
| `IllegalStateException` khi dùng segment | Arena đã close, hoặc lifetime race | Không dùng sau close; chờ mọi worker hoàn thành |
| JVM dừng bất ngờ khi upcall | Java exception thoát khỏi target, hoặc ABI sai/function pointer invalid | Catch trong target; xác minh descriptor/prototype và lifetime |
| Callback từ C không chạy | Stub pointer sai/hết hạn, native không gọi, thread không tạo được | Kiểm tra export, status codes, C create/join, Arena scope |
| `WrongMethodTypeException` tại `invokeExact` | Java types không khớp MethodHandle descriptor | Kiểm tra `MethodHandle.type()`, carrier `int`/`MemorySegment` |
| `IllegalArgumentException` khi tạo stub | Target MethodHandle type không khớp FunctionDescriptor | Dùng `MethodType.methodType(int.class,int.class)` sau bind |
| `IllegalCallerException` / native-access warning | Restricted FFM API chưa được cấp native access | `--enable-native-access=ALL-UNNAMED` hoặc module cụ thể |
| `UnsatisfiedLinkError` / không load được C library | Sai `Path`, file name, architecture, dynamic dependencies | Build OS đúng, `System.mapLibraryName`, làm việc cùng thư mục |
| Callback báo giá trị sai | C `int32_t` không khớp descriptor/ABI hoặc data race | Kiểm tra C typedef, alignment, synchronization |
| Đóng arena bị lỗi trong lúc callback chạy | Close concurrent với in-flight accesses/downcalls | Stop/unregister/join trước khi close |
| Java main bị treo chờ C worker | Callback chờ main trong khi main chờ join | Đổi sang event queue asynchronous/owner event loop |
| Lỗi chỉ khi plugin unload | Stub/target/class loader còn được native giữ | Lifetime management, unregister, class loader references |
| Native worker vẫn chạy khi JVM kết thúc | Tin rằng attach daemon bảo đảm native cleanup | Explicit shutdown, join và stop trước VM teardown |
| Shared arena nhưng mất kết quả cập nhật | `get`+`set` không atomic | VarHandle atomic/lock và data publication đúng |
| Java object còn giữ MemorySegment nhưng không dùng được | Scope đã đóng | Lifetime của segment không bằng lifetime của Java reference |

### 17.1. Kiểm tra symbol export

Linux:

~~~bash
nm -D libthread_callback.so
~~~

macOS:

~~~bash
nm -gU libthread_callback.dylib
~~~

Windows x64 Developer Command Prompt:

~~~bat
dumpbin /exports thread_callback.dll
~~~

Đối với thư viện demo, cần thấy `invoke_direct` và `invoke_native_thread` là symbols export. Tên/decoration thực tế theo OS/ABI; với 64-bit C ABI được chọn, tên không có C++ name mangling.

Không cần tìm `JNI_OnLoad` trong demo vì đây là FFM-only library. Nếu dùng C++ để xuất function, dùng `extern "C"` để tránh name mangling và kiểm tra convention.

## 18. Checklist thiết kế callback native thread ở production

Trước khi đưa một function pointer Java cho native library, kiểm tra:

- **Ai gọi callback?** Ngay trong downcall hay OS worker tạo riêng? Bao nhiêu threads có thể gọi đồng thời?
- **Thread nào sở hữu confined arena?** Target có capture segment confined của thread khác không?
- **Arena của upcall stub** là shared và đủ sống cho mọi lần native callback hay chưa?
- **Arena của captured data** có cùng thread policy thực sự cần thiết không? Đừng đánh đồng nó với stub arena.
- **Có dữ liệu cần copy trước không?** Scalar/immutable data có thể giúp tránh chia sẻ native memory.
- **Java target có catch exception tại boundary không?** Có status/error channel để báo native không?
- **C FunctionDescriptor** có khớp chính xác pointer/function signature, C integer width và calling convention không?
- **Native worker lifetime** có stop/join hoặc unregister+ack trước khi close stub arena không?
- **Close** có thể chạy cạnh tranh với callback đang dùng segment không?
- **Callback có chờ owner Java thread không?** Owner có đang blocked trong downcall đợi worker không?
- **Thread context** như class loader, ThreadLocal hay MDC có cần truyền rõ ràng không?
- **Callback data đồng thời** có atomic/locks/synchronization đúng ngoài việc dùng `Arena.ofShared()` chưa?
- **FFM pointer arguments** có ownership/lifetime từ C xác định không, hay chỉ là raw pointer với scope global?
- **Error paths** khi native thread creation thất bại có khiến Java đóng arena an toàn và ghi được diagnostic không?
- **VM shutdown** có đợi worker native và in-flight callback kết thúc trước khi teardown native libraries không?
- **Native access flag** và các giới hạn security/integrity của JDK đích đã được cấu hình chưa?

## 19. Câu hỏi ôn tập có đáp án

**1.** Java main tạo `Arena.ofConfined()`, cấp phát `MemorySegment data`, rồi đưa một callback bound tới data cho một OS worker native. Vì sao callback vẫn lỗi dù JVM chạy được Java code từ worker?

**Đáp án:** JVM attach/transition cho phép worker **thực thi Java**, nhưng không chuyển **quyền sở hữu confined arena**. `data.get` từ worker vi phạm confinement và ném `WrongThreadException`.

**2.** `upcallStub(target, desc, Arena.ofShared())` có tự biến mọi captured MemorySegment thành shared không?

**Đáp án:** Không. Stub thuộc arena được truyền khi tạo, còn captured segments giữ scope/owner thread của **arena đã cấp phát chúng**.

**3.** Trong demo, tại sao `invoke_direct(stubA, 10)` trả 42 còn `invoke_native_thread(stubA, 10)` trả -700?

**Đáp án:** Direct callback chạy ngay trong Java main thread, đúng owner của confined data. Native-thread callback chạy trên OS worker khác, nên target catch `WrongThreadException` và trả sentinel -700.

**4.** Nếu native callback làm Java target ném exception mà không catch, liệu caller Java bao quanh downcall bằng `try/catch` có đủ không?

**Đáp án:** Không. JDK 22 quy định exception không được thoát upcall target; JVM có thể chấm dứt đột ngột. Catch cần nằm **bên trong target** hoặc được bọc bằng MethodHandle combinator thích hợp.

**5.** `Arena.ofShared()` có giúp hai callbacks tăng cùng một counter không mất cập nhật nếu mỗi callback tự `get` rồi `set` không?

**Đáp án:** Không. Shared chỉ cho phép truy cập đa thread; phải dùng atomic mode như `VarHandle.getAndAdd` hoặc synchronization thích hợp.

**6.** Tại sao ví dụ không đóng arena ngay sau khi C tạo worker rồi trả về?

**Đáp án:** C **không** trả về cho Java trước khi worker join. Nhờ đó Java chỉ close khi không còn native callback pending. Với async API thực, phải có unregister/stop/join riêng.

**7.** Một callback nhận pointer C trong một argument Java `MemorySegment` có nghĩa pointer đó được Java Arena quản lý lifetime không?

**Đáp án:** Không. Pointer argument của upcall có scope theo hợp đồng linker, thường global/always alive, nhưng C vẫn sở hữu raw allocation; Java phải tuân theo lifetime native đã quy định.

**8.** Vì sao có thể dùng copy primitive thay vì shared segment?

**Đáp án:** Nếu callback chỉ cần giá trị scalar đã biết, owner đọc trên thread hợp lệ rồi bind giá trị vào target; worker không truy cập confined segment và tránh mở rộng ownership không cần thiết.

**9.** Một callback trên OS worker đặt task vào queue và đợi owner xử lý, trong khi owner bị chặn bởi `pthread_join`. Sẽ xảy ra điều gì?

**Đáp án:** Deadlock: owner chờ worker, worker chờ owner. Dùng protocol không cần đáp ứng đồng bộ hoặc để owner xử lý queue ngoài lời gọi đang chặn.

**10.** FFM upcall từ native thread có đòi Java tự gọi `AttachCurrentThread` và lưu `JNIEnv *` toàn cục không?

**Đáp án:** Không trong ví dụ FFM của HotSpot; FFM runtime xử lý transition/attach. `JNIEnv *` là JNI API gắn với thread, không dùng làm global; quy tắc attach riêng chỉ áp dụng khi chính native JNI code gọi JNI trực tiếp.

**11.** Nếu Java vẫn giữ object `stub` nhưng arena đã đóng, C có thể dùng địa chỉ đó an toàn không?

**Đáp án:** Không. Lifetime của upcall function pointer gắn với arena scope, không phải chỉ với Java reference. Gọi pointer sau close có thể crash.

**12.** Trong ví dụ, vì sao cần `-pthread` trên Linux/macOS nhưng không cần `jni.h`?

**Đáp án:** C tạo worker bằng POSIX threads, nên cần build/link đúng môi trường threading. Thư viện FFM-only không dùng JNI function types/methods nên không cần header JNI.

## 20. Tài liệu tham khảo kỹ thuật

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): downcall/upcall, `upcallStub`, lifetime, pointer arguments, cảnh báo exception không được thoát callback và restricted native access.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared owner thread, `WrongThreadException`, `close` và temporal safety.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): thread access checks, scope, bounds và segment validity.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): kiểu ABI của callback C và Java MethodHandle.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): `libraryLookup(Path, Arena)` và quản lý library resource.
- [Oracle Java SE 22 — JNI Invocation API](https://docs.oracle.com/en/java/javase/22/docs/specs/jni/invocation.html): JNI `AttachCurrentThread`, `AttachCurrentThreadAsDaemon` và giới hạn `JNIEnv *`.
- [Dev.java — FFM Upcalls](https://dev.java/learn/api/io/ffm/upcall/): giải thích chuyển Java MethodHandle thành C function pointer.
- [OpenJDK — Foreign Linker Implementation Overview](https://cr.openjdk.org/~jvernee/docs/FL_Overview.html): mô tả chi tiết implementer về **upcalls từ non-Java native threads**, attach daemon và detach trên thread death.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): chuẩn hóa FFM trong Java 22.

**Kết luận:** Native worker có thể gọi lại Java qua FFM `Linker.upcallStub`, nhưng **thread chạy callback không tự trở thành owner** của một segment do `Arena.ofConfined()` trên thread khác cấp phát. Cần quản lý **riêng** lifetime của stub và dữ liệu, **catch exceptions bên trong callback**, dùng shared memory hoặc copy/queue khi vượt thread boundary, và **chờ mọi native workers/callbacks hoàn thành trước khi close arena**.
