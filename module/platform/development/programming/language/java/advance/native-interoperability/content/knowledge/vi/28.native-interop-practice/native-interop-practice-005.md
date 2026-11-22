# Đăng ký callback Java và dừng an toàn khi thư viện gọi từ luồng nền

## 1. Bài thực hành và kết quả cần đạt

Một SDK viết bằng C/C++ thường tạo luồng nền để đọc thiết bị, nhận dữ liệu hoặc quan sát sự kiện. Sau khi Java đăng ký callback, SDK cần gọi ngược vào phương thức Java khi có sự kiện. Thách thức không nằm ở riêng lệnh `CallVoidMethod`, mà ở **vòng đời**: luồng native được gắn với JVM như thế nào, đối tượng callback còn sống hay không, và ứng dụng làm gì khi yêu cầu dừng đúng lúc một callback đang chạy.

Bài thực hành này dùng **Java 17+**, **JNI** và **C++17** để:

1. Java đăng ký một đối tượng nhận callback với thư viện native.
2. Thư viện tạo một `std::thread` nền và dùng `JavaVM` để lấy `JNIEnv` thuộc **chính luồng đó**.
3. Luồng native gọi phương thức Java `onNativeEvent(7)` đúng một lần, đưa sự kiện vào hàng đợi Java.
4. Java đợi nhận sự kiện, yêu cầu dừng, native đánh thức luồng nền, đợi `join()`, sau đó mới giải phóng `GlobalRef`.
5. Khi `close()` trả về thành công, không còn luồng native thuộc phiên đăng ký đó có thể bắt đầu callback mới.

Chương trình ví dụ chạy được trên Linux/macOS/Windows khi có trình biên dịch C++17 phù hợp. Kết quả khi chạy thành công là:

~~~text
event=7
closed
~~~

Đây là mô phỏng tối giản **một sự kiện** để kiểm chứng lifecycle. Trong SDK thật, luồng nền thường nhận nhiều sự kiện, cần queue có giới hạn, backpressure, chính sách lỗi, thời hạn chờ dừng và cơ chế quản lý nhiều listener.

## 2. Hai ranh giới quan trọng: thread và lifetime

### 2.1. `JavaVM*` không phải `JNIEnv*`

- `JavaVM*` dùng để truy cập API attach/detach JVM và có thể lưu trong trạng thái native dùng giữa các luồng trong vòng đời JVM.
- `JNIEnv*` là giao diện JNI **gắn với từng luồng**. Không giữ `JNIEnv*` lấy từ lời gọi `nativeStart()` rồi đem sang `std::thread`: đó là sử dụng sai JNI, có thể gây crash hoặc hành vi không xác định.
- Luồng do native tự tạo phải gọi `AttachCurrentThread(...)` hoặc `AttachCurrentThreadAsDaemon(...)` trước khi gọi Java, sau đó `DetachCurrentThread()` khi không còn Java frame trên stack và trước khi kết thúc luồng.
- Ví dụ dùng `AttachCurrentThreadAsDaemon` để native worker không giữ JVM sống vô hạn nếu chương trình quên dừng. **Daemon không thay thế `close()`**: vẫn phải ngừng nhận dữ liệu, đợi callback xong và giải phóng tài nguyên.

Luồng mới attach thường có **context class loader là bootstrap loader**. Trong thực tế, `FindClass("com/company/MyListener")` từ một luồng native tự tạo có thể thất bại nếu class ứng dụng không nằm ở class loader mặc định. Mẫu này giải quyết bằng cách nhận **đối tượng Java khi đăng ký**, gọi `GetObjectClass` và `GetMethodID` ngay trên luồng Java đã đăng ký, rồi lưu phương thức cùng global reference.

### 2.2. Java callback phải có quyền sống lâu hơn lời gọi đăng ký

Đối số `jobject` truyền vào native method là **local reference**. Nó chỉ được bảo đảm còn hợp lệ trong scope/thread chứa native call; không cất local reference vào một struct cho luồng khác dùng sau khi `register0` trả về.

Thay vào đó:

- Gọi `NewGlobalRef(listener)` trước khi khởi chạy worker. Global reference giữ listener được GC nhận biết cho đến khi gọi `DeleteGlobalRef`.
- Chỉ giải phóng global reference sau khi đã chặn sự kiện mới và **join xong** luồng có thể gọi callback.
- Không biến `jobject` thành một con trỏ C++ thông thường để dereference; nó là handle opaque do JNI quản lý.
- `jmethodID` là ID phương thức, **không phải** `jobject`. Trong ví dụ, listener có global reference còn sống nên class của nó không bị unload giữa chừng; phương thức đã tra cứu vẫn có thể dùng khi callback xảy ra.
- Nếu callback nhận/tạo nhiều object Java trên worker lâu sống, quản lý local references theo vòng lặp bằng `DeleteLocalRef` hoặc `PushLocalFrame`/`PopLocalFrame`. Một worker được attach lâu không tự động dọn local references sau từng vòng lặp native.

### 2.3. Bảo đảm shutdown đúng nghĩa

Chỉ đặt cờ `stopping = true` rồi trả về **chưa đủ**: một callback có thể đã vượt qua bước kiểm tra cờ và đang chạy. Muốn cam kết “không callback sau khi `close()` hoàn thành”, cần:

~~~text
Java                     Native manager                   Native worker
 | start()                  |                                 |
 |------------------------->| tạo GlobalRef / state            |
 |                          | tạo std::thread ---------------> |
 |                          |                                 | Attach JVM
 |                          |                                 | callback Java
 |<-------------------------| trả opaque handle               | đợi điều kiện stop
 | nhận event qua queue     |                                 |
 | close()                  |                                 |
 |------------------------->| đặt stop=true; notify --------> |
 |                          | join() đợi worker               | Detach JVM, thoát
 |                          |<--------------------------------|
 |                          | DeleteGlobalRef, free state     |
 |<-------------------------| trả về sau cleanup              |
~~~

Bốn quy tắc ngăn lỗi phổ biến: **(1)** không giữ native mutex trong lúc `CallVoidMethod`, **(2)** không giữ native mutex trong lúc `join`, **(3)** không cho callback đồng bộ gọi `close()` rồi join chính thread ấy, **(4)** không `DeleteGlobalRef` trước khi callback kết thúc.

Cần phân biệt: `close()` xong bảo đảm **không có lời gọi callback mới từ phiên native đó**; các sự kiện **đã enqueue vào Java trước khi close** vẫn có thể còn trong queue. Nếu API yêu cầu “xóa mọi sự kiện cũ”, phải đặt chính sách drain/drop và xử lý riêng ở tầng Java.

## 3. Tạo dự án thực hành

Trong một thư mục riêng, tạo hai tệp:

~~~text
native-callback-demo/
├── NativeCallbackDemo.java
└── native_callbacks.cpp
~~~

Lệnh biên dịch sẽ tạo `NativeCallbackDemo.class`, `NativeCallbackDemo.h` và thư viện tương ứng với hệ điều hành. Ví dụ sử dụng **một listener cho mỗi phiên đăng ký** và một `std::thread` native/phiên. Không dùng một singleton process-global cho tất cả listener; như vậy hai phiên có thể dừng độc lập.

### 3.1. Mã Java: `NativeCallbackDemo.java`

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;

public final class NativeCallbackDemo implements AutoCloseable {
    static {
        System.loadLibrary("nativecallbacks");
    }

    private static final ThreadLocal<Boolean> IN_CALLBACK =
            new ThreadLocal<>();

    private final BlockingQueue<Integer> events =
            new ArrayBlockingQueue<>(8);

    // Con trỏ native dạng opaque; Java không dereference.
    private long handle;
    private boolean closed;

    public NativeCallbackDemo() {
    }

    private static native long register0(NativeCallbackDemo receiver);
    private static native boolean unregister0(long nativeHandle);

    // JNI gọi phương thức này trên attached native worker thread.
    private void onNativeEvent(int value) {
        IN_CALLBACK.set(Boolean.TRUE);
        try {
            // Callback ngắn: chỉ chuyển sự kiện sang queue Java.
            if (!events.offer(value)) {
                throw new IllegalStateException("Event queue is full");
            }
        } finally {
            IN_CALLBACK.remove();
        }
    }

    public synchronized void start() {
        if (closed || handle != 0L) {
            throw new IllegalStateException(
                    "Already started or closed");
        }
        handle = register0(this);
        if (handle == 0L) {
            throw new IllegalStateException("Registration failed");
        }
    }

    public Integer pollEvent(long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }

    @Override
    public synchronized void close() {
        // Chặn self-join nếu callback bị sửa để trực tiếp gọi close().
        if (Boolean.TRUE.equals(IN_CALLBACK.get())) {
            throw new IllegalStateException(
                    "Close from a separate Java owner thread");
        }
        if (closed) {
            return; // close nhiều lần không giải phóng hai lần.
        }
        closed = true;
        long oldHandle = handle;
        handle = 0L;
        if (oldHandle != 0L && unregister0(oldHandle)) {
            throw new IllegalStateException(
                    "Native callback or attach failed; see stderr");
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        try (NativeCallbackDemo demo = new NativeCallbackDemo()) {
            demo.start();
            Integer value = demo.pollEvent(10, TimeUnit.SECONDS);
            if (value == null) {
                throw new IllegalStateException("Callback timed out");
            }
            System.out.println("event=" + value);
        }
        System.out.println("closed");
    }
}
~~~

**Ý nghĩa của các quyết định trong Java:**

- `start()` và `close()` được `synchronized` để tránh hai Java thread cùng khởi tạo/giải phóng handle. Không giữ monitor này trong `onNativeEvent`, nên worker không phải chờ một khóa đang bị `close()` giữ khi nó `join`.
- `onNativeEvent` không gọi trực tiếp code nghiệp vụ chậm, không giữ native lock, không chờ UI/HTTP/DB và không gọi `close()`. Nó chỉ `offer` vào queue; luồng Java sở hữu component quyết định khi nào xử lý hoặc dừng.
- Queue giới hạn 8 phần tử giúp biểu lộ vấn đề **backpressure**. Khi queue đầy, phương thức throw; native cần phát hiện ngoại lệ thay vì tiếp tục gọi JNI khi vẫn có pending exception.
- `handle` có thể thay đổi từ giá trị opaque sang 0 khi đóng. Không truyền handle đó cho một API native bất kỳ sau khi đã đóng.
- `try-with-resources` luôn gọi `close()` khi thoát khối, kể cả khi chờ callback bị timeout hoặc có `InterruptedException`. Nếu việc dừng có thể chặn lâu trong ứng dụng thật, nên xây API shutdown có timeout/cancellation và chính sách xử lý riêng.
- Trong bản minh họa, callback Java không được public cho user tự override. Nếu cung cấp callback của bên thứ ba, phải định nghĩa rõ luồng thực thi và chuyển xử lý dài sang executor phù hợp.

### 3.2. Mã native: `native_callbacks.cpp`

~~~cpp
#include "NativeCallbackDemo.h"

#include <condition_variable>
#include <cstdint>
#include <exception>
#include <mutex>
#include <thread>

struct WorkerState {
    JavaVM* vm = nullptr;
    jobject receiver = nullptr;    // JNI global reference
    jmethodID onEvent = nullptr;
    std::thread worker;
    std::mutex mutex;
    std::condition_variable wake;
    bool stopping = false;
    bool callbackFailed = false;
};

static void throwState(JNIEnv* env, const char* message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

static void workerLoop(WorkerState* state) {
    JNIEnv* env = nullptr;
    if (state->vm->AttachCurrentThreadAsDaemon(
            reinterpret_cast<void**>(&env), nullptr) != JNI_OK) {
        std::lock_guard<std::mutex> guard(state->mutex);
        state->callbackFailed = true;
        return;
    }

    bool shouldDeliver;
    {
        std::lock_guard<std::mutex> guard(state->mutex);
        shouldDeliver = !state->stopping;
    }

    if (shouldDeliver) {
        // Không giữ mutex khi nhảy từ native sang Java.
        env->CallVoidMethod(state->receiver, state->onEvent, 7);

        if (env->ExceptionCheck()) {
            // Demo: ghi lỗi + xóa pending exception để detach an toàn.
            // Production: gửi lỗi đến Java/error channel có cấu trúc.
            env->ExceptionDescribe();
            env->ExceptionClear();
            std::lock_guard<std::mutex> guard(state->mutex);
            state->callbackFailed = true;
        }
    }

    {
        std::unique_lock<std::mutex> lock(state->mutex);
        state->wake.wait(lock, [state] {
            return state->stopping;
        });
    }

    // Chỉ detach sau khi callback Java đã trả về.
    state->vm->DetachCurrentThread();
}

extern "C" JNIEXPORT jlong JNICALL
Java_NativeCallbackDemo_register0(
        JNIEnv* env, jclass, jobject listener) {
    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        throwState(env, "Cannot obtain JavaVM");
        return 0;
    }

    jclass type = env->GetObjectClass(listener);
    if (type == nullptr) {
        return 0; // Pending exception từ JNI.
    }
    jmethodID method =
            env->GetMethodID(type, "onNativeEvent", "(I)V");
    env->DeleteLocalRef(type);
    if (method == nullptr) {
        return 0; // Ví dụ NoSuchMethodError đang pending.
    }

    jobject global = env->NewGlobalRef(listener);
    if (global == nullptr) {
        return 0; // Thường do OutOfMemoryError.
    }

    WorkerState* state = nullptr;
    try {
        state = new WorkerState();
        state->vm = vm;
        state->receiver = global;
        state->onEvent = method;
        state->worker = std::thread([state] {
            workerLoop(state);
        });
        return static_cast<jlong>(
                reinterpret_cast<std::intptr_t>(state));
    } catch (const std::exception&) {
        // Chưa có worker joinable khi std::thread constructor fail.
        delete state;
        env->DeleteGlobalRef(global);
        throwState(env, "Cannot start native worker");
        return 0;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_NativeCallbackDemo_unregister0(
        JNIEnv* env, jclass, jlong rawHandle) {
    if (rawHandle == 0) {
        return JNI_FALSE;
    }
    auto* state = reinterpret_cast<WorkerState*>(
            static_cast<std::intptr_t>(rawHandle));

    {
        std::lock_guard<std::mutex> guard(state->mutex);
        state->stopping = true;
    }
    state->wake.notify_one();

    // Caller là Java owner thread, không phải callback thread.
    // Join ở ngoài mutex, đợi mọi CallVoidMethod hoàn tất.
    try {
        state->worker.join();
    } catch (const std::exception&) {
        // Không free state/global ref nếu chưa bảo đảm worker đã dừng.
        throwState(env, "Cannot join native worker");
        return JNI_FALSE;
    }

    bool failed = state->callbackFailed;
    env->DeleteGlobalRef(state->receiver);
    delete state;
    return failed ? JNI_TRUE : JNI_FALSE;
}
~~~

Phần native cố tình không gọi `FindClass` cho class ứng dụng trong `workerLoop`. Listener và `jmethodID` đã được lấy trong `register0` khi Java gọi vào. C++ worker chỉ sử dụng `JavaVM*`, global reference và `JNIEnv*` nhận được **sau khi attach chính nó**.

Mã sử dụng `std::mutex`/`std::condition_variable` để worker không busy-spin. Thao tác `wait(lock, predicate)` tránh mất tín hiệu nếu `close()` đặt `stopping=true` **trước** khi worker tới điểm chờ. Trong mọi thứ tự xen kẽ:

- Nếu close xảy ra trước bước kiểm tra `shouldDeliver`, callback có thể bị bỏ qua.
- Nếu worker đã quyết định giao callback, close có thể chờ đến khi callback thực sự hoàn tất.
- Worker chỉ thoát vòng chờ khi thấy `stopping`; sau đó `DetachCurrentThread` và chấm dứt.
- `unregister0` gọi `join` trước khi `DeleteGlobalRef` và xóa `WorkerState`, tránh **use-after-free**.
- Callback Java có ngoại lệ: native dùng `ExceptionCheck` → `ExceptionDescribe` → `ExceptionClear`, ghi cờ `callbackFailed`. Sau cleanup, `close()` báo lỗi nếu cờ đó đúng. Không im lặng bỏ pending Java exception.
- Nếu attach thất bại, worker đánh dấu `callbackFailed` và kết thúc; `unregister0` vẫn `join`, dọn global reference rồi báo lại lỗi.

**Giới hạn có chủ ý của ví dụ:** nhánh thất bại cực hiếm khi chính `std::thread::join()` throw sẽ dừng cleanup để tránh xóa tài nguyên có thể còn được worker dùng; ứng dụng production cần cơ chế quản lý trạng thái lỗi, retry/diagnostics và ownership chuyên biệt. Mẫu sử dụng đúng quy ước rằng `close()` chỉ được gọi từ luồng Java sở hữu phiên, không trực tiếp từ native callback. `IN_CALLBACK` ngăn đường gọi `close()` đồng bộ từ callback của ví dụ.

## 4. Biên dịch và chạy

Cần **JDK 17 trở lên**, một C++17 compiler và biến môi trường `JAVA_HOME` trỏ tới đúng JDK. Đặt `NativeCallbackDemo.java` và `native_callbacks.cpp` trong cùng thư mục và chạy lệnh tại đó.

### 4.1. Linux (GCC/Clang C++)

~~~bash
javac -h . NativeCallbackDemo.java
g++ -std=c++17 -O2 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  native_callbacks.cpp -o libnativecallbacks.so
java -Djava.library.path=. NativeCallbackDemo
~~~

`javac -h .` sinh `NativeCallbackDemo.h` định nghĩa hai JNI symbols `Java_NativeCallbackDemo_register0` và `Java_NativeCallbackDemo_unregister0`; `g++` tạo đúng binary `libnativecallbacks.so` để Java load qua `System.loadLibrary("nativecallbacks")`.

### 4.2. macOS (Clang)

~~~bash
javac -h . NativeCallbackDemo.java
clang++ -std=c++17 -O2 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  native_callbacks.cpp -o libnativecallbacks.dylib
java -Djava.library.path=. NativeCallbackDemo
~~~

### 4.3. Windows (MSVC x64 Native Tools Command Prompt)

~~~bat
javac -h . NativeCallbackDemo.java
cl /std:c++17 /EHsc /O2 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" native_callbacks.cpp /link /OUT:nativecallbacks.dll
java -Djava.library.path=. NativeCallbackDemo
~~~

Windows phải dùng compiler phù hợp kiến trúc JVM (x64 ↔ x64, ARM64 ↔ ARM64). Trên các hệ điều hành, nếu thư viện không được tìm thấy, kiểm tra working directory, `java.library.path`, tên binary và dependency động. Nếu có `UnsatisfiedLinkError` dù file tồn tại, cần kiểm tra symbol JNI, định dạng thư viện, ABI và các thư viện mà nó phụ thuộc.

### 4.4. JVM native access từ JDK 24

Từ **JDK 24**, JEP 472 đưa bước nạp thư viện JNI và binding native method vào cơ chế restricted native access. Khi dùng code ở unnamed module (class path), chạy bằng:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  --illegal-native-access=deny \
  -Djava.library.path=. NativeCallbackDemo
~~~

Trên Windows dùng lệnh một dòng tương đương:

~~~bat
java --enable-native-access=ALL-UNNAMED --illegal-native-access=deny -Djava.library.path=. NativeCallbackDemo
~~~

Các cờ `--illegal-native-access=deny`/`--enable-native-access` này áp dụng cho **JDK 24+** trong ngữ cảnh JNI restrictions; không thêm `--illegal-native-access` vào lệnh JDK 17/21 vì JDK cũ không nhận option đó. Khi chuyển thành named module, cấp quyền cho **module thực sự gọi restricted operations** thay vì mở `ALL-UNNAMED` cho toàn bộ class path.

### 4.5. Stdout khi thành công

~~~text
event=7
closed
~~~

Hai dòng không phụ thuộc scheduler trong **đường thành công**: native phát đúng một sự kiện có giá trị `7`, Java chỉ in sau khi lấy sự kiện từ queue; dòng `closed` chỉ in sau khi `try-with-resources` gọi `close()` xong. Nếu attach hoặc callback lỗi, hay máy quá tải khiến đợi 10 giây hết hạn, chương trình có exception/diagnostic thay vì hai dòng trên. Không giả định thời gian callback đến là cố định.

## 5. Kiểm thử race dừng sớm và cleanup

### 5.1. Đóng ngay sau khi đăng ký

Tạo thêm `EarlyCloseCheck.java`:

~~~java
public final class EarlyCloseCheck {
    public static void main(String[] args) {
        for (int i = 0; i < 200; i++) {
            try (NativeCallbackDemo demo =
                         new NativeCallbackDemo()) {
                demo.start();
                // Có thể close trước hoặc sau khi worker callback.
            }
        }
        System.out.println("early_close_ok");
    }
}
~~~

Biên dịch và chạy (JDK 17–23):

~~~bash
javac EarlyCloseCheck.java
java -Djava.library.path=. EarlyCloseCheck
~~~

Trên JDK 24+, thêm cờ native access như mục 4.4. Output khi thành công là:

~~~text
early_close_ok
~~~

Thử nghiệm này có ích để bắt race `start() → close()`, hỏng `join()` hoặc crash vì giải phóng global reference quá sớm. Chạy nhiều lần và kết hợp `-Xcheck:jni` (HotSpot) trong phiên kiểm tra, đồng thời dùng công cụ memory/thread sanitizer thích hợp với native build khi khả dụng. **Một lần pass không chứng minh hết race condition**; muốn quan sát chính xác còn cần fault injection và biến thể có nhiều producer/consumer thread.

### 5.2. Gọi `close()` hai lần

`close()` được viết idempotent. Sau lần đầu, `closed=true` và `handle=0`. Lần hai trả về mà không gọi `unregister0` nữa. Điều này ngăn double-free. Tuy nhiên API vẫn cần bảo vệ khi phía native bị gọi trực tiếp với con trỏ đã giải phóng: không công khai native handle cho bên ngoài, và mọi đường lifecycle phải đi qua Java owner có đồng bộ.

### 5.3. Dừng khi callback đang thực thi

Trong thực tế, native worker có thể đã qua `shouldDeliver` khi thread khác gọi `close()`. Vì native không giữ mutex qua `CallVoidMethod`, lệnh đóng có thể đặt cờ `stopping` rồi chờ `join`. Worker hoàn thành callback, quan sát cờ, detach và thoát. Điều này tạo **barrier**: sau khi close trả về, global reference không còn bị worker dùng.

Nếu callback Java cố khóa monitor của `close()` hoặc gọi `close()` trực tiếp, có thể deadlock/self-join. Mẫu dùng queue và không đồng bộ callback trên monitor owner, đồng thời cấm `close()` từ cùng callback thread. Khi SDK có callback bên ngoài do người dùng đăng ký, nên dispatch trên executor Java tách biệt và thiết kế `stopAsync()` nếu callback có thể yêu cầu hủy đăng ký.

## 6. Checklist quản lý callback trong dự án thật

| Vấn đề | Sai lầm thường gặp | Thiết kế an toàn |
| --- | --- | --- |
| Chuyển qua JVM từ native thread | Dùng `JNIEnv*` lấy từ thread khác | Lưu `JavaVM*`, attach native worker, dùng `JNIEnv*` riêng, detach khi thoát |
| Giữ Java callback | Giữ local `jobject` sau khi native method trả về | `NewGlobalRef` lúc đăng ký, `DeleteGlobalRef` sau khi worker dừng |
| Tra cứu callback class | `FindClass` ở native worker rồi không thấy class app | `GetObjectClass`/`GetMethodID` trên Java caller khi đăng ký, lưu ID và global ref |
| Xử lý sự kiện | Làm I/O chậm trong `CallVoidMethod` | Chuyển dữ liệu sang bounded queue/executor, xác định backpressure |
| Callback ném exception | Tiếp tục JNI với pending exception hoặc xóa rồi quên lỗi | `ExceptionCheck`, log/chuyển error đến owner, clear đúng chỗ và dừng/đánh dấu thất bại |
| Giải phóng listener | Delete global ref khi callback chưa trả về | Signal stop → ngăn công việc mới → `join` → delete global ref |
| Đồng bộ | Giữ mutex native trong khi callback/`join` | Giữ mutex ngắn để cập nhật trạng thái, nhả trước khi gọi Java/đợi worker |
| Chạy `close()` trong callback | Worker đợi `join` chính nó hoặc đợi lock Java | Cấm self-close đồng bộ; gửi yêu cầu dừng sang owner/executor |
| Nhiều đăng ký | Một static global listener cho mọi phiên | Mỗi phiên có handle riêng, state riêng, đóng một lần |
| JVM shutdown | Ỷ lại daemon thread/`JNI_OnUnload` | Đóng trước khi lifecycle JVM kết thúc; ngăn SDK phát callback muộn |
| Cấu hình JDK mới | Không cấp native access khi cần | Kiểm thử JDK 24+ với `--illegal-native-access=deny` và `--enable-native-access` đúng module |
| Kiểm thử | Chỉ xác minh callback đã nhận | Kiểm thử stop sớm, stop sau callback, lỗi attach, callback exception, queue đầy và nhiều lần đăng ký |

### Khi thư viện có nhiều sự kiện và nhiều worker

Mẫu một sự kiện đã đủ để kiểm chứng giao thức attach/callback/stop. Nếu mở rộng thành SDK liên tục, cần thiết kế bổ sung:

- Dùng **producer-count hoặc in-flight callback counter** và điều kiện `inFlight == 0` (hoặc join toàn bộ worker) trước khi delete refs. Một cờ `stopping` không đồng nghĩa mọi callback kết thúc.
- Nếu nhiều callback chạy song song, định nghĩa có hay không bảo đảm thứ tự; sự kiện nhận không nên bị đảo do scheduling mà không được mô tả.
- Không giữ một `JNIEnv*` duy nhất trong state dùng chung. Mỗi worker attach lấy env riêng. Nếu JNI đã được gọi trên một Java-created thread (Java→native), có thể dùng env của invocation đó, không attach/detach tùy tiện luồng do JVM quản lý.
- Với callback có payload lớn, cân nhắc pin/copy buffer, vòng đời memory segment và quy tắc ownership. Không đưa con trỏ native đã free sang Java queue.
- Bounded queue cần chính sách rõ: block producer, drop oldest/newest, coalesce events hoặc báo lỗi. Blocking callback có thể làm stop mất thời gian hoặc deadlock nếu consumer bị dừng trước. Demo chủ động dùng `offer` không block.
- Lưu lỗi dưới dạng structured status và cung cấp API đọc lỗi; `ExceptionDescribe` chỉ hợp lý để quan sát đơn giản, không phải giao thức logging/telemetry production.
- Đối với native SDK có API cancel/stop **blocking vô hạn**, không có bảo đảm `join` kết thúc. Cần có hợp đồng dừng worker, timeout/cancellation theo API SDK và xử lý khi không thể ngắt nguồn sự kiện.

## 7. Chẩn đoán lỗi thường gặp

**`UnsatisfiedLinkError: no nativecallbacks in java.library.path`**: JVM không tìm thấy binary. Xem `-Djava.library.path=.`, working directory, tên file và architecture. Nếu tên đúng nhưng load vẫn lỗi, xem dependency native hoặc exported JNI symbols.

**`UnsatisfiedLinkError: 'long NativeCallbackDemo.register0(...)'`**: Thư viện load được nhưng JVM không tìm được hàm JNI tương ứng. Kiểm tra `javac -h`, class/package, chữ ký native, `extern "C"` để tránh C++ name mangling và tên hàm được export.

**`NoSuchMethodError: onNativeEvent(I)V`**: `GetMethodID` không tìm được instance callback đúng signature. Với `(I)V`, tham số là một `int` và kiểu trả về là `void`. Nếu đổi sang `long` sẽ là `(J)V`; nếu phương thức static phải dùng `GetStaticMethodID` và `CallStaticVoidMethod`.

**JVM crash sau một lúc chạy**: Nghi cache `JNIEnv*` qua thread, dùng local reference khi native call đã trả về, free state/global ref trước khi callback dừng, sai ABI hoặc race trong thư viện C++.

**Không thấy event/timeout**: Kiểm tra attach JVM, cờ `stopping`, lỗi callback/queue, Java thread có chặn sự kiện hay không; bật `-Xcheck:jni` trên HotSpot trong phiên chẩn đoán. Đừng tăng timeout để che lỗi deadlock thực sự.

**Ứng dụng không thoát**: Native worker chưa nhận tín hiệu dừng, `join()` đợi thread bị kẹt, hoặc attach non-daemon chưa detach. Ghi stack dump Java và native; giải phóng khóa trước khi gọi callback/đợi worker và đảm bảo native API đang block có cơ chế đánh thức.

**JDK 24+ cảnh báo hoặc `IllegalCallerException`**: Tách khỏi lỗi threading. Đối chiếu module có thao tác restricted, thêm `--enable-native-access` phù hợp ở **JVM khởi chạy thật**; nếu dùng `--illegal-native-access=deny` mà thiếu quyền, ngay bước load/binding có thể bị chặn.

## 8. Bài tập mở rộng và tiêu chí đạt

1. Thay giá trị cố định `7` bằng một event có số thứ tự tăng trong vòng lặp worker. Thêm cờ dừng, giới hạn queue, thiết kế backpressure; kiểm tra không có callback mới sau `close()` và không rò global reference.
2. Cho một event cố tình gây ngoại lệ Java. Xác minh `ExceptionCheck` phát hiện đúng, native không dùng JNI bừa khi exception pending, lỗi được truyền về Java owner sau khi dọn tài nguyên.
3. Tạo hai `NativeCallbackDemo` độc lập; dừng phiên thứ nhất nhưng phiên thứ hai vẫn hoạt động. So sánh với thiết kế dùng một singleton native listener.
4. Thử stress `start() → close()` liên tục, chạy dưới `-Xcheck:jni` và native thread/memory sanitizer khi có thể. Ghi các loại lỗi đã bắt được.
5. Mở rộng thành callback không đồng bộ được dispatch sang `ExecutorService` Java; kiểm tra rằng việc shutdown executor và shutdown native worker có thứ tự rõ ràng, không khóa chéo.

**Tiêu chí hoàn thành:** (a) callback từ native background thread vào Java thành công, (b) không dùng `JNIEnv*` sai thread, (c) listener sống nhờ `GlobalRef` đến khi worker chấm dứt, (d) `close()` bảo đảm join xong mới free, (e) không deadlock khi callback và shutdown cạnh tranh, (f) lỗi callback/attach được phát hiện, (g) chạy được cả normal và early-close test trên JDK/platform đã chọn.

## Tài liệu tham khảo chính thức

- Oracle JNI Specification — *Invocation API*, `AttachCurrentThreadAsDaemon`/`DetachCurrentThread`: https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html
- Oracle JNI Specification — *Design Overview*, local/global references và method IDs: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle JNI Specification — *JNI Functions*, `NewGlobalRef`, `DeleteGlobalRef`, `CallVoidMethod` và exception handling: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- OpenJDK JEP 472 — Native access restrictions từ JDK 24: https://openjdk.org/jeps/472

**Ghi nhớ:** đăng ký callback thành công chỉ là nửa đầu của tích hợp JNI. Nửa còn lại là **giao thức dừng có ranh giới**: signal stop, cho callback đang chạy kết thúc, join native worker, detach, rồi mới giải phóng global reference và trạng thái native.