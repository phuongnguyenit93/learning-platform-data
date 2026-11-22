# Callback từ luồng bản địa và cách tìm đúng lớp ứng dụng trong JNI

## 1. Vấn đề thực tế

Một ứng dụng Java có thể gọi thư viện C/C++ qua JNI, sau đó thư viện tạo một **native worker thread** bằng `pthread_create` hoặc `std::thread`. Khi có kết quả, worker muốn gọi ngược một phương thức Java để thông báo sự kiện, cập nhật trạng thái hoặc trả kết quả. Về mặt JNI, đây không phải lời gọi Java bình thường: luồng vừa tạo trong C/C++ **chưa tự động có quyền dùng JNI** và có thể **không nhìn thấy class ứng dụng qua class loader phù hợp**.

Hai nhóm vấn đề thường đi cùng nhau:

1. **Quy tắc luồng:** `JNIEnv *` thuộc về **một thread cụ thể**. Native worker phải attach vào đúng `JavaVM`, nhận `JNIEnv *` của chính nó, thực hiện callback rồi detach khi kết thúc. Không chuyển một `JNIEnv *` lấy từ Java calling thread sang worker.
2. **Quy tắc class loader:** `FindClass` dùng class loader tùy theo ngữ cảnh gọi. Trên native thread không có Java native-method frame đang hoạt động, tìm `com/example/plugin/Handler` có thể thất bại nếu class được nạp bởi **custom class loader** của plugin thay vì system class loader. Đổi thread context class loader đơn thuần không bảo đảm sửa được `FindClass`.

Thêm vào đó, native code phải giữ đúng lifetime của `jobject`/`jclass` qua các thread, không để callback chạy sau khi plugin bị dỡ, quản lý exception ném từ Java callback và quyết định rõ ai chịu trách nhiệm dừng worker.

Ví dụ bối cảnh:

```text
Java thread
  │
  └── nativeStart(callback)
         │
         ├── Lưu JavaVM*
         ├── Tạo global reference tới callback
         └── Tạo C/C++ worker thread
                    │
                    ├── AttachCurrentThread → JNIEnv* riêng
                    ├── CallVoidMethod(callback, onEvent, ...)
                    ├── Xử lý Java exception nếu có
                    ├── Xóa local refs, giải phóng trạng thái
                    └── DetachCurrentThread
```

Mục tiêu của bài là hiểu đúng cơ chế và triển khai được một callback an toàn, đặc biệt khi các class thuộc module, plugin hoặc loader riêng.

## 2. Phân biệt `JavaVM *` và `JNIEnv *`

JNI có hai interface liên quan nhưng khác vai trò.

| Interface | Ý nghĩa | Có thể dùng ở thread khác? |
| --- | --- | --- |
| `JavaVM *` | Interface tới JVM, dùng `GetEnv`, `AttachCurrentThread`, `DetachCurrentThread` | **Có thể** lưu lại và dùng ở nhiều native threads thuộc cùng VM |
| `JNIEnv *` | Interface JNI của **thread hiện tại**, dùng `FindClass`, `CallVoidMethod`, `NewGlobalRef`... | **Không**; phải nhận lại `JNIEnv *` cho mỗi attached thread |

Trong một JNI method Java gọi vào C:

```c
JNIEXPORT void JNICALL Java_demo_Bridge_start(
        JNIEnv *env, jclass declaringClass) {

    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return; /* Cần báo lỗi cho Java theo hợp đồng ứng dụng. */
    }

    /* Có thể chuyển vm tới native worker.
       KHÔNG được chuyển env sang thread khác để dùng JNI. */
}
```

Đây là **fragment minh họa**, chưa có lớp Java `demo.Bridge` hay implementation đầy đủ. Phương thức `GetJavaVM` lấy interface JVM từ `JNIEnv *` đang hợp lệ; native library cũng có thể nhận `JavaVM *` trong `JNI_OnLoad`.

### 2.1. Worker phải attach trước khi gọi Java

Cách gọi C của JNI Invocation API:

```c
JNIEnv *workerEnv = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **)&workerEnv, NULL);

if (rc == JNI_OK) {
    /* Gọi JNI qua workerEnv trên chính thread này. */

    (*vm)->DetachCurrentThread(vm);
}
```

Trong C++:

```cpp
JNIEnv *workerEnv = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void **>(&workerEnv), nullptr);

if (rc == JNI_OK) {
    // workerEnv chỉ dùng trên thread này.
    vm->DetachCurrentThread();
}
```

Sau khi attach thành công, native thread có thể gọi JNI methods và Java methods, miễn tuân thủ reference lifetime, đồng bộ hóa và pending-exception rules.

- `AttachCurrentThread` trả `JNI_OK` khi thành công; nếu thất bại, **không sử dụng** `workerEnv`.
- `DetachCurrentThread` phải được gọi **trước khi native thread do bạn attach kết thúc**, sau khi không còn Java method trên stack của thread ấy.
- Một thread đã attach gọi `AttachCurrentThread` thêm lần nữa sẽ lấy `JNIEnv *` của thread đó; việc attach lại không đổi daemon status.
- `AttachCurrentThreadAsDaemon` attach một native thread mới như daemon. Daemon/non-daemon ảnh hưởng khả năng JVM chờ thread kết thúc, **không giải quyết** vấn đề tìm class hay lifetime callback.
- `GetEnv` trả `JNI_OK` nếu current thread đã attach, `JNI_EDETACHED` nếu chưa, hoặc `JNI_EVERSION` nếu version không hỗ trợ. Nó **không tự attach**.

Đừng tự ý detach một Java thread đã được JVM quản lý chỉ vì nó đang đi qua native method. Nếu một thư viện có thể được gọi từ cả Java thread và native thread, phải theo dõi **chính thread nào do mình attach** để detach đúng quyền sở hữu.

### 2.2. Local refs và global refs khi vượt qua ranh giới thread

Tham số `jobject callback` nhận từ Java là **local JNI reference** trong native method. Không được đặt thẳng nó vào một struct C, trả về Java rồi để worker đọc sau:

```c
/* SAI nếu cb là local ref từ một native call khác. */
struct Context { jobject cb; };
context.cb = cb;
/* Một thread khác dùng context.cb sau khi native call return. */
```

Hãy giữ bằng global reference:

```c
jobject globalCallback = (*env)->NewGlobalRef(env, cb);
if (globalCallback == NULL) {
    /* Nếu cb != NULL, có thể có lỗi cấp phát cần xử lý. */
    return;
}

/* Truyền globalCallback cho worker đã attach. */

/* Chỉ xóa sau khi bảo đảm worker không còn sử dụng callback. */
(*env)->DeleteGlobalRef(env, globalCallback);
```

`NewGlobalRef` tạo strong reference tới Java object và có thể dùng từ các thread đã attach thích hợp. Nó ngăn object bị GC trong lúc callback còn cần. Đổi lại, nếu quên `DeleteGlobalRef`, callback và defining class loader có thể bị giữ sống mãi, gây rò rỉ khi redeploy plugin.

**`jmethodID` không phải một `jobject`.** Có thể cache method ID để dùng trên worker, nhưng ID chỉ hợp lệ khi defining class của method còn loaded. Trong một thiết kế giữ callback bằng global ref, class của object cũng còn sống trong khoảng thời gian cần dùng; sau teardown, không dùng lại method ID của phiên bản plugin cũ.

## 3. Vì sao `FindClass` trên native worker có thể tìm sai class?

JNI `FindClass` nhận **tên class theo JNI dạng dấu gạch chéo**, ví dụ:

```c
jclass type = (*env)->FindClass(
        env, "com/example/plugin/EventHandler");
```

Tuy nhiên **tên class đúng là chưa đủ**. Phải dùng đúng class loader.

Theo JNI specification, hành vi phụ thuộc nơi gọi:

| Ngữ cảnh gọi `FindClass` | Class loader được sử dụng |
| --- | --- |
| Trong native method do một Java class khai báo | Loader gắn với **class khai báo native method** (JNI native frame hiện tại), không tự động là loader của callback object |
| Trong `JNI_OnLoad`/`JNI_OnLoad_L` | Loader của class đang nạp thư viện native |
| Qua Invocation Interface, không có current native method gắn với loader | `ClassLoader.getSystemClassLoader()` |
| Trong `JNI_OnUnload`/`JNI_OnUnload_L` | System class loader, vì loader lúc nạp có thể đã không còn tồn tại |

Native worker vừa được `AttachCurrentThread` attach rồi gọi `FindClass` không có ngữ cảnh Java native method thông thường. Trong trường hợp này JNI không tự biết phải dùng plugin loader mà Java đã chọn trước đó. Vì vậy, với class chỉ nằm trong `URLClassLoader`, OSGi loader, servlet/container loader hoặc module loader riêng, `FindClass("com/example/plugin/EventHandler")` có thể thất bại bằng `NoClassDefFoundError` hoặc lỗi tra cứu tương đương.

### 3.1. Phân biệt `FindClass` với thread context class loader

Khi attach một native thread mới, **thread context class loader** mặc định là bootstrap loader (theo JNI Invocation API). Đây là trạng thái của `Thread.currentThread().getContextClassLoader()`.

`FindClass` lại có quy tắc chọn loader riêng theo ngữ cảnh JNI như bảng trên. Vì thế, thay:

```java
Thread.currentThread().setContextClassLoader(pluginLoader);
```

chỉ ảnh hưởng Java framework **chủ động tra cứu thread context class loader**. Nó không phải phương pháp bảo đảm `FindClass` chọn đúng plugin loader, và cũng không tự đồng bộ class identity khi callback đi qua nhiều plugin.

Nếu framework cần context class loader phù hợp khi chạy Java callback, có thể đặt và **khôi phục** nó bên trong Java callback wrapper. Làm việc đó có chủ đích; không dùng nó để thay thế việc lưu đúng `Class<?>` hoặc callback object.

### 3.2. Hai class cùng tên vẫn có thể là hai kiểu khác nhau

`plugin.Handler` do `LoaderA` định nghĩa khác với `plugin.Handler` do `LoaderB` định nghĩa:

```text
LoaderA ──► plugin.Handler (Class object A)
LoaderB ──► plugin.Handler (Class object B)

Tên nhị phân giống nhau, identity class khác nhau.
```

Nếu native cache dùng khóa chỉ là chuỗi `"plugin/Handler"`, việc reload plugin có thể khiến callback bị gọi bằng method ID của phiên bản cũ, hoặc tạo `ClassCastException`/`NoSuchMethodError`/lỗi JNI nghiêm trọng. Không “sửa” lỗi bằng cách thử nhiều class loader ngẫu nhiên. Hãy **gắn cache với chính callback instance / jclass và loader có vòng đời rõ ràng**.

## 4. Ba cách đúng để gọi class của ứng dụng từ native worker

### Cách A — Ưu tiên: Java truyền callback object; native giữ global ref

Trong Java, thay vì yêu cầu native tự tìm `plugin.Handler`, cung cấp một interface Java ổn định:

```java
@FunctionalInterface
interface EventSink {
    void onEvent(int code);
}
```

Java tạo callback instance từ đúng plugin loader rồi truyền vào native. Trước khi tạo worker, JNI làm ba việc ở **thread Java đang gọi native method**:

1. `GetObjectClass(callback)` lấy class thực tế của object.
2. `GetMethodID(..., "onEvent", "(I)V")` lấy method ID đúng chữ ký.
3. `NewGlobalRef(callback)` tạo reference mạnh dùng qua native thread.

Worker chỉ cần `CallVoidMethod` trên global callback, kèm method ID đã tra cứu. Nó **không cần `FindClass` trên worker thread**. Phương pháp này hoạt động cho callback thuộc custom loader, miễn object/method còn hợp lệ, callback công khai đúng chữ ký và lifecycle được quản lý.

### Cách B — Truyền `Class<?>` từ Java, giữ `jclass` bằng global ref

Khi cần gọi một **static method** của plugin, phía Java có thể xác định class đúng loader rồi truyền cho JNI:

```java
Class<?> pluginHandler =
        Class.forName("plugin.Handler", true, pluginLoader);

// nativeRegisterHandler(pluginHandler) là API tự định nghĩa.
nativeRegisterHandler(pluginHandler);
```

Đây là **fragment Java**; `pluginLoader` và `nativeRegisterHandler` được định nghĩa bởi ứng dụng. Phía JNI tạo `NewGlobalRef` đối với tham số `jclass`, tra cứu `GetStaticMethodID` đúng method, rồi `CallStaticVoidMethod` trên worker. Sau khi stop worker và cleanup, xóa global class ref.

Không cache một local `jclass` từ lời gọi trước để dùng lâu dài. Một global `jclass` mạnh có thể giữ **class loader plugin** còn sống, nên teardown phải chủ động.

### Cách C — Lưu đúng `ClassLoader` rồi gọi `loadClass` (khi cần tải nhiều class động)

Khi worker không biết trước các class cần sử dụng, Java có thể truyền **loader object** và native lưu `NewGlobalRef` tới nó. Đã attach vào JVM, native có thể gọi `ClassLoader.loadClass(String)` qua JNI trên đúng loader; **tên truyền ở đây dùng dấu chấm**, ví dụ `"plugin.Handler"`, khác với `FindClass("plugin/Handler")`.

Một hướng thường dễ kiểm soát hơn là cho Java viết phương thức helper để thực hiện `Class.forName(name, initialize, pluginLoader)` và trả `Class<?>`, còn native gọi helper thông qua reference đã có. Khi làm việc với module encapsulation, visibility và security policies, các điều kiện Java thông thường vẫn có hiệu lực.

Cách C linh hoạt nhưng phức tạp hơn A/B: phải xử lý `ClassNotFoundException`, chữ ký JNI, logic load/initialize, lock loader, và vòng đời của global loader ref. Chỉ dùng khi thật sự cần dynamic class resolution.

### Chọn cách nào?

| Nhu cầu | Gợi ý |
| --- | --- |
| Native worker thông báo sự kiện cho Java | **A**, callback instance được truyền xuống |
| Native worker gọi static entry point cố định của plugin | **B**, truyền đúng `Class<?>` |
| Native cần lookup nhiều class qua một plugin loader | **C**, gọi loader đã được Java truyền |
| Cùng native core phục vụ nhiều plugin | Bridge Java chung + callback riêng từng plugin, theo vòng đời |
| Plugin có thể reload | Registry theo plugin instance/loader, stop/drain/cleanup trước khi bỏ loader cũ |

## 5. Ví dụ hoàn chỉnh: native `std::thread` callback về Java

Ví dụ dưới đây dùng **Java 17+**, JNI và C++17. Chúng ta tạo một worker thực sự bằng `std::thread`, attach nó vào JVM, gọi `onEvent(42)` trên callback Java, rồi detach. Để **stdout xác định**, phương thức Java `runOnce` đợi worker hoàn tất bằng `join` trước khi return. Trong ứng dụng thật, một worker dài hạn có thể dùng hàng đợi/scheduler, nhưng phải định nghĩa rõ stop và ownership.

Ví dụ còn xử lý trường hợp callback Java ném ngoại lệ: native worker **không thể để pending exception của thread mình tự xuất hiện trên Java caller thread**. Worker lấy object ngoại lệ, clear ở thread worker, tạo global ref để chuyển qua thread; sau `join`, JNI method gốc gọi `Throw` trên chính throwable ấy để Java caller bắt được. Đây là điểm quan trọng của callback đa luồng.

Cấu trúc thư mục:

```text
jni-callback/
├── src/
│   └── demo/
│       └── NativeEvents.java
├── native/
│   └── native_events.cpp
└── build/
    ├── classes/
    └── headers/
```

### 5.1. Java: định nghĩa callback và native entry

**Tệp `src/demo/NativeEvents.java`:**

```java
package demo;

public final class NativeEvents {
    static {
        System.loadLibrary("native_events");
    }

    private NativeEvents() {
    }

    @FunctionalInterface
    public interface EventSink {
        void onEvent(int code);
    }

    private static native void runOnce(EventSink sink);

    public static void main(String[] args) {
        runOnce(code ->
                System.out.println("callback event: " + code));

        System.out.println("native worker finished");

        try {
            runOnce(code -> {
                throw new IllegalStateException("sink failed");
            });
        } catch (IllegalStateException error) {
            System.out.println(
                    "propagated: " + error.getMessage());
        }
    }
}
```

`EventSink` là nested interface nên tên nhị phân Java của nó là `demo.NativeEvents$EventSink`; nhưng mã native **không cần tự `FindClass` tên ấy**. Nó nhận callback instance và dùng `GetObjectClass`.

### 5.2. C++: giữ đúng callback object, attach riêng và truyền lỗi có kiểm soát

**Tệp `native/native_events.cpp`:**

```cpp
#include "demo_NativeEvents.h"
#include <exception>
#include <thread>

/* Chỉ dành cho helper được gọi khi không có exception pending. */
static void throwStateError(JNIEnv* env, const char* message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    if (type == nullptr) {
        return;  // Giữ lỗi do FindClass tạo nếu có.
    }
    env->ThrowNew(type, message);
    env->DeleteLocalRef(type);
}

struct WorkerState {
    JavaVM* vm;
    jobject sinkGlobal;
    jmethodID onEvent;
    jthrowable failureGlobal;
    bool workerFailed;
};

JNIEXPORT void JNICALL Java_demo_NativeEvents_runOnce(
        JNIEnv* env, jclass /*declaringClass*/, jobject sink) {

    if (sink == nullptr) {
        jclass type = env->FindClass(
                "java/lang/IllegalArgumentException");
        if (type != nullptr) {
            env->ThrowNew(type, "sink must not be null");
            env->DeleteLocalRef(type);
        }
        return;
    }

    JavaVM* vm = nullptr;
    if (env->GetJavaVM(&vm) != JNI_OK) {
        throwStateError(env, "cannot get JavaVM");
        return;
    }

    // Tra cứu method trên CLASS THỰC của callback,
    // ngay trong native call từ Java.
    jclass sinkClass = env->GetObjectClass(sink);
    if (sinkClass == nullptr) {
        return;  // Giữ exception do JNI nếu có.
    }

    jmethodID onEvent = env->GetMethodID(
            sinkClass, "onEvent", "(I)V");
    env->DeleteLocalRef(sinkClass);

    if (onEvent == nullptr) {
        return;  // JNI có thể đã đặt exception pending.
    }

    // Local ref 'sink' không được dùng trực tiếp từ worker.
    jobject sinkGlobal = env->NewGlobalRef(sink);
    if (sinkGlobal == nullptr) {
        return;  // Có thể có OutOfMemoryError pending.
    }

    WorkerState state{
        vm, sinkGlobal, onEvent, nullptr, false
    };

    try {
        std::thread worker([&state]() {
            JNIEnv* workerEnv = nullptr;
            jint attached = state.vm->AttachCurrentThread(
                    reinterpret_cast<void**>(&workerEnv), nullptr);

            if (attached != JNI_OK) {
                state.workerFailed = true;
                return;
            }

            workerEnv->CallVoidMethod(
                    state.sinkGlobal, state.onEvent, (jint)42);

            if (workerEnv->ExceptionCheck() == JNI_TRUE) {
                // Ngoại lệ đang pending ở WORKER thread,
                // không thể tự đi lên Java caller thread.
                jthrowable original =
                        workerEnv->ExceptionOccurred();
                workerEnv->ExceptionClear();

                if (original != nullptr) {
                    // Giữ exception object qua thời điểm detach.
                    state.failureGlobal =
                            (jthrowable)workerEnv->NewGlobalRef(
                                    original);
                    workerEnv->DeleteLocalRef(original);

                    if (state.failureGlobal == nullptr) {
                        state.workerFailed = true;
                        // Trong trường hợp thiếu bộ nhớ,
                        // tránh để lỗi pending khi detach.
                        if (workerEnv->ExceptionCheck()) {
                            workerEnv->ExceptionClear();
                        }
                    }
                } else {
                    state.workerFailed = true;
                }
            }

            if (state.vm->DetachCurrentThread() != JNI_OK) {
                state.workerFailed = true;
            }
        });

        // join bảo đảm callback và worker hoàn tất trước khi
        // giải phóng sinkGlobal hoặc đọc state.
        worker.join();
    } catch (const std::exception&) {
        env->DeleteGlobalRef(sinkGlobal);
        throwStateError(env, "cannot start native worker");
        return;
    }

    if (state.failureGlobal != nullptr) {
        // Đặt chính exception object của callback thành
        // pending trên JAVA CALLER thread.
        env->Throw(state.failureGlobal);
        // DeleteGlobalRef được phép khi exception pending.
        env->DeleteGlobalRef(state.failureGlobal);
    } else if (state.workerFailed) {
        throwStateError(env, "native worker failed");
    }

    // Đến đây worker đã dừng, không còn dùng sink.
    env->DeleteGlobalRef(state.sinkGlobal);
}
```

Các điểm cần hiểu trong mã:

- `GetJavaVM` nhận interface có thể chuyển sang native thread. **Không chuyển `env` của Java caller** sang lambda.
- `GetObjectClass(sink)` và `GetMethodID` được gọi **trước** khi worker được tạo, nên method ID được lấy đúng trên runtime class của callback. Đây là cách tránh tra cứu `FindClass` sai loader trong worker.
- `NewGlobalRef(sink)` giữ Java callback sống trong lúc native thread chạy. `DeleteGlobalRef` chỉ diễn ra **sau khi worker.join()` và mọi lần truy cập callback đã kết thúc.
- `AttachCurrentThread` trả `JNIEnv *` riêng. Worker chỉ gọi Java sau khi attach thành công và gọi `DetachCurrentThread` khi callback đã hoàn tất.
- Callback Java có thể ném lỗi. `ExceptionOccurred` tạo local `jthrowable` ở worker; `ExceptionClear` xóa pending exception ở worker để tiếp tục JNI; `NewGlobalRef` giữ object Throwable qua thread boundary. Java calling thread ném lại qua `Throw`. **Không chuyển raw local `jthrowable` sang thread khác**.
- `WorkerState` nằm trên stack của JNI entry; nhờ `join`, worker không còn truy cập struct trước khi entry method kết thúc. Việc đọc cờ `workerFailed`/`failureGlobal` sau `join` có thứ tự đồng bộ phù hợp.
- Mã này phục vụ **demo một worker ngắn**. Nếu thread chạy lâu, cần struct có lifetime độc lập (heap/RAII), cơ chế stop/ownership, khóa và trạng thái shutdown; không giữ địa chỉ stack của hàm đã return.
- `std::thread` có thể thất bại khi khởi tạo; ví dụ bắt `std::exception` ngay trong entry, chuyển sang Java exception. Các lỗi hệ thống hiếm gặp trong quá trình `join` cần được xử lý riêng trong ứng dụng production có giám sát vòng đời worker; demo giả định `join` của thread joinable vừa tạo hoàn tất như dự kiến.
- Nếu thiếu bộ nhớ ngay khi chuyển ngoại lệ callback sang global ref, ví dụ báo lỗi worker tổng quát về Java; một triển khai production có thể có chính sách lỗi nghiêm trọng riêng. **Không được để C++ exception thoát trực tiếp qua JNI boundary**.

### 5.3. Build và chạy

Đứng tại thư mục `jni-callback` trên **Linux**, dùng JDK 17+ và compiler C++17 như `g++`/`clang++`. Biến `JAVA_HOME` phải trỏ tới JDK.

```bash
mkdir -p build/classes build/headers

javac -h build/headers -d build/classes \
  src/demo/NativeEvents.java

g++ -std=c++17 -O2 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native/native_events.cpp -o libnative_events.so

java -Djava.library.path=. -cp build/classes \
  demo.NativeEvents
```

`javac -h` sinh `build/headers/demo_NativeEvents.h`, có tên native symbol từ Java declaration. Trên Linux, `System.loadLibrary("native_events")` ánh xạ tên logic sang `libnative_events.so` trong đường dẫn tìm thư viện.

**Stdout dự kiến khi thao tác thành công:**

```text
callback event: 42
native worker finished
propagated: sink failed
```

Lần đầu worker gọi Java lambda và in sự kiện 42, sau đó `join` hoàn thành nên Java in dòng tiếp theo. Lần thứ hai callback cố tình ném `IllegalStateException`. JNI chuyển **chính throwable** ấy về thread gọi `runOnce`, nên Java `catch` in message.

Một số JDK mới có chính sách cấp quyền native access và có thể in cảnh báo ra **stderr**; với JDK 24+ khi chạy trên classpath có thể thêm `--enable-native-access=ALL-UNNAMED` trước `-cp` nếu cần. Quy định truy cập native không thay đổi thread/class-loader semantics. Trên Windows/macOS, tên thư viện động và lệnh compile/include khác; `pthread` cũng không phải API thread chuẩn bắt buộc trên mọi nền tảng.

## 6. Một ví dụ lỗi phổ biến: gọi `FindClass` trực tiếp trong worker

Giả sử Java plugin chạy từ một `URLClassLoader` và có class `plugin.Handler`. Mã native sau có rủi ro:

```cpp
// Fragment: đang chạy trên native-created attached thread.
jclass handler = workerEnv->FindClass("plugin/Handler");
if (handler == nullptr) {
    // Có thể không thấy class của plugin loader:
    // worker không có native-method frame tương ứng.
}
```

Trên ứng dụng chạy trực tiếp bằng classpath, code này đôi khi hoạt động vì system loader tình cờ tìm được class. Sau khi ứng dụng chuyển vào container/plugin loader, cùng code có thể thất bại. Đây là nguyên nhân khiến bug **chỉ xuất hiện trong production deployment**, không tái hiện trong demo JAR đơn giản.

Cách giải quyết bền vững hơn:

```java
// Fragment Java: pluginLoader do ứng dụng cung cấp.
Class<?> exactClass = Class.forName(
        "plugin.Handler", true, pluginLoader);

// Native API tự định nghĩa nhận Class<?> này:
nativeRegisterHandler(exactClass);
```

Native dùng `NewGlobalRef` tới `exactClass` và `GetStaticMethodID` hoặc dùng callback instance đã được Java tạo. Không còn yêu cầu worker tự chọn loader theo tên class.

### 6.1. Vì sao không cache local `jclass`?

`FindClass`/`GetObjectClass` thường trả một **local JNI reference**. Nếu gọi:

```cpp
static jclass cachedHandler = nullptr;

void badRegistration(JNIEnv* env, jclass clazz) {
    cachedHandler = clazz; // SAI: clazz có thể hết hạn sau JNI call.
}
```

thì thread khác dùng `cachedHandler` sau khi native method return là use-after-lifetime. Cache đúng:

```cpp
// Fragment: gọi trong JNI method với clazz hợp lệ.
jclass globalHandler =
        (jclass)env->NewGlobalRef(clazz);
if (globalHandler == nullptr) {
    return; // Có thể có Java exception pending.
}

// Gắn globalHandler với vòng đời plugin.
// Worker đã attach có thể dùng nó bằng JNI API hợp lệ.

// Sau khi stop/drain mọi worker còn sử dụng:
env->DeleteGlobalRef(globalHandler);
```

Bản global ref giữ class (và gián tiếp defining loader) có thể tiếp tục sống qua nhiều calls. Đừng biến một cache chung toàn JVM thành chỗ giữ hàng loạt plugin loaders cũ không thể được GC.

## 7. Exception trong callback thuộc về thread nào?

**Java exception pending là trạng thái của thread hiện tại.** Nếu Java callback chạy trên native worker và ném ngoại lệ, ngoại lệ đó pending trên worker. Thread Java ban đầu **không tự biết** việc này; nếu native worker chỉ `DetachCurrentThread` và kết thúc, lỗi có thể bị mất hoặc được JVM ghi ra log tùy cách triển khai.

Các chiến lược có chủ đích gồm:

1. **Callback tự xử lý lỗi trong Java** bằng `try/catch` và gửi một kết quả rõ ràng về native; hợp cho event notifications.
2. **Chuyển lỗi sang Java caller** nếu caller đang đợi worker (như `join` trong ví dụ): capture `Throwable` bằng `ExceptionOccurred`, clear pending ở worker, giữ bằng `NewGlobalRef`, rồi gọi `Throw` trên JNI caller thread sau khi join.
3. **Báo lỗi bất đồng bộ** qua `CompletableFuture`, queue, listener báo lỗi hoặc state máy ứng dụng. Không cố “ném vào” một thread Java khác tùy ý.
4. **Ghi log và tiếp tục** chỉ khi contract chấp nhận lỗi bị xử lý tại worker; không dùng `ExceptionDescribe` mà không biết nó **xóa pending exception**.

Khi `ExceptionCheck` trả true, đừng tiếp tục gọi `FindClass`, `GetMethodID` hoặc `CallVoidMethod` như thể callback đã thành công. Một tập JNI functions giới hạn được phép gọi với pending exception, gồm `ExceptionOccurred`, `ExceptionClear`, `DeleteLocalRef`, `DeleteGlobalRef` và các hàm release tài nguyên. Nếu cần API JNI mới để xây wrapper, phải clear theo kế hoạch, giữ đúng cause, rồi mới tiếp tục.

**Đừng gọi `DetachCurrentThread` khi Java frames từ callback chưa return.** Trong ví dụ, `CallVoidMethod` đã hoàn tất (dù có exception pending được capture/clear) rồi worker mới detach.

## 8. Vòng đời, đồng bộ và tránh giữ class loader plugin sống mãi

### 8.1. Vấn đề khi worker tồn tại lâu

Một plugin được tắt nhưng native thread vẫn giữ global callback reference:

```text
Native worker / native global callback ref
                    │
                    ▼
              Callback object
                    │
                    ▼
            Callback Java class
                    │
                    ▼
           Plugin ClassLoader
```

Dù ứng dụng đã `close()` `URLClassLoader` và bỏ plugin instance ở Java, global reference phía native có thể vẫn giữ plugin/class loader còn reachable. Khi reload nhiều lần, có thể xuất hiện rò rỉ Metaspace, giữ JAR/class cũ, hoặc callback chạy vào phiên bản plugin đã ngừng hoạt động.

Một vòng đời có kiểm soát thường là:

1. **Đăng ký:** Java truyền callback/class/loader thực vào JNI; native giữ strong global references cần dùng.
2. **Bắt đầu:** tạo worker và attach đúng JVM; chỉ gọi callback khi plugin ở trạng thái active.
3. **Dừng nhận việc mới:** chặn scheduling/callback mới.
4. **Drain:** đợi callback đang chạy hoàn thành hoặc hủy đúng theo hợp đồng; bảo đảm không thread nào còn sử dụng refs.
5. **Cleanup:** detach native threads đã attach, xóa global refs, hủy queue/handle và cache `jmethodID` theo phiên bản plugin.
6. **Bỏ loader:** Java gỡ listener, registry, executor và các strong references còn lại, rồi mới kỳ vọng GC có cơ hội thu hồi loader.

Không gọi `DeleteGlobalRef` ở thread A trong lúc thread B còn sử dụng callback, trừ khi có giao thức đồng bộ/ownership bảo vệ nó. Một global reference mạnh giúp giữ object sống, nhưng **không thay mutex, lock hoặc memory ordering** cho state native dùng chung.

### 8.2. Không giữ `JNIEnv *` hoặc local JNI reference trong static state

```cpp
// SAI về thread và lifetime.
static JNIEnv* globalEnv;
static jobject callbackLocal;

void registerBad(JNIEnv* env, jobject cb) {
    globalEnv = env;
    callbackLocal = cb;
}
```

`globalEnv` không hợp lệ cho worker thread; `callbackLocal` không có lifetime cross-call. Nếu thư viện cần state dài hạn, lưu `JavaVM*` và global references riêng, có synchronization/cleanup.

### 8.3. Khi native thread chỉ cần chạy logic Java, cân nhắc tạo thread từ Java

Nếu mục đích là async Java callback, một lựa chọn ít lỗi hơn là để Java quản lý `ExecutorService`/`Thread.start()` rồi native chỉ báo kết quả. Java thread đã được VM quản lý và có cơ chế thread groups, exception handlers, thread context class loader và quản lý cancellation rõ hơn. Chỉ tạo thread từ C/C++ khi native library hoặc một SDK bên ngoài thực sự áp đặt luồng riêng.

Điều này đặc biệt có lợi khi framework dựa vào context class loader hoặc security/correlation context của Java worker threads. Với native thread, bạn phải khởi tạo/khôi phục các context đó có chủ đích.

## 9. Các lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| Crash khi dùng `JNIEnv*` trong `pthread` | Dùng `JNIEnv*` lấy từ thread khác | Lưu `JavaVM*`, attach worker và lấy env riêng |
| `FindClass("plugin/Handler")` trả `NULL` trên worker | Loader mặc định không biết plugin class | Pass callback/class/loader từ Java; giữ global ref |
| Class tìm được nhưng callback method không tìm được | Sai signature JNI hoặc dùng class khác loader | Kiểm tra `javap -s`, `GetObjectClass` và loader identity |
| Callback chạy một lúc rồi crash | Local `jobject`/`jclass` bị lưu qua native return | Dùng `NewGlobalRef`; release sau stop/drain |
| Callback throw nhưng Java caller không bắt được | Pending exception nằm trên worker thread | Quy định error channel; capture+global+Throw ở caller hoặc future |
| JVM không kết thúc | Native attached non-daemon thread còn sống | Stop thread, detach; cân nhắc daemon khi phù hợp |
| Plugin vẫn không unload sau redeploy | Global JNI refs, callback/threads/registries giữ loader | Teardown explicit, dùng heap/GC roots analysis |
| Lúc Java gọi JNI thì `FindClass` chạy, từ C worker thì fail | Lookup context thay đổi theo JNI invocation path | Đừng phụ thuộc loader ngầm định của worker |
| Native deadlock chờ callback | Callback cố lấy lock Java/native mà caller đang giữ trong lúc `join` | Không giữ lock xuyên native blocking call; thiết kế asynchronous handoff |
| `GetMethodID` trả null | Không có method với tên/descriptor đúng, hoặc Java exception pending | Đọc error, kiểm tra interface và signature `(I)V` |

### 9.1. Debug loader có hệ thống

Trong Java, ghi nhận:

```java
Class<?> type = callback.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Đây là **fragment**; `callback` do ứng dụng cung cấp. Với nhiều class loader cùng tên, so sánh **identity của object loader** (không chỉ `toString()`). Phía JNI, có thể dùng `GetObjectClass` và phương thức Java `getClassLoader()` nếu thật sự cần chẩn đoán, song thường đơn giản hơn là log từ Java trước khi truyền callback.

Có thể dùng `javap -s` để kiểm tra descriptor `(I)V` hoặc các type nhiều tham số; `javac -h` để sinh đúng JNI symbol; `-Xcheck:jni` trên HotSpot để phát hiện nhiều lỗi JNI reference và thread usage. Khi debug native crash, chạy JVM với tùy chọn logging và debugger native phù hợp.

### 9.2. Một số bẫy nâng cao

**Class init và deadlock:** `FindClass` có thể dẫn tới class loading/linking/initialization trong ngữ cảnh JNI. Trên worker, một phép tra cứu bất ngờ có thể giữ class-loading lock hoặc chờ Java thread đang đồng thời chờ worker. Resolve class và method theo một giai đoạn đăng ký trên Java thread thường giảm rủi ro.

**Callback và C++ exceptions:** Nếu Java callback ném `Throwable`, JNI báo bằng pending exception, không bằng C++ `throw`. Ngược lại, không được để một `std::exception` phát sinh ở thư viện C++ thoát qua JNI frame; catch và chuyển thành Java exception phù hợp hoặc lỗi asynchronous có cấu trúc.

**Thread context:** Native-attached thread không tự thừa hưởng MDC, transaction, tracing, security context hoặc application context của Java thread đã tạo công việc. Truyền context theo tham số/event nếu cần; đừng ngầm kỳ vọng nó xuất hiện.

**Multiple JVMs:** Một native thread không thể đồng thời attach vào hai Java VMs. Không dùng `JavaVM*` thuộc tiến trình/JVM khác. Trong hầu hết ứng dụng Java thông thường chỉ có một JVM trong process, nhưng trách nhiệm giữ đúng VM vẫn là bắt buộc.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một JNI method nhận `JNIEnv* env` rồi tạo `std::thread`, sau đó lambda dùng chính `env` để gọi `CallVoidMethod`. Sai ở đâu?  
**Đáp án:** `JNIEnv*` chỉ hợp lệ trên thread đã cung cấp nó. Lambda phải gọi `AttachCurrentThread` với `JavaVM*` để nhận env của worker.

**Câu 2.** `FindClass("com/app/PluginHandler")` thành công khi gọi từ Java native method, nhưng thất bại trên native-attached worker. Có phải vì tên class sai?  
**Đáp án:** Chưa chắc. `FindClass` có thể dùng class loader khác khi không có native method frame. Hãy truyền đúng callback hoặc `Class<?>` từ Java thay vì phụ thuộc lookup ngầm định.

**Câu 3.** Có thể lưu `jobject callback` do JNI nhận làm local ref sang biến global C rồi dùng sau vài phút?  
**Đáp án:** Không. Phải tạo `NewGlobalRef` và chỉ `DeleteGlobalRef` sau khi worker chắc chắn không còn dùng callback.

**Câu 4.** Worker callback Java ném `IllegalStateException`. Tại sao Java caller thread chưa thấy exception?  
**Đáp án:** Pending exception gắn với worker thread. Phải có kênh truyền lỗi; khi caller đang đợi, capture `Throwable` trên worker, chuyển thành global ref, rồi `Throw` trên caller sau khi join là một phương án.

**Câu 5.** Gọi `Thread.currentThread().setContextClassLoader(loader)` trên worker có bảo đảm `FindClass` dùng loader đó?  
**Đáp án:** Không. `FindClass` có quy tắc class loader theo JNI call context; context class loader chỉ ảnh hưởng Java code/framework chủ động tra cứu nó.

**Câu 6.** Cache `jmethodID` theo tên method có an toàn sau khi plugin class loader unload và reload không?  
**Đáp án:** Không. ID gắn với declaring class đã nạp; sau khi class unload, ID không còn hợp lệ. Mỗi phiên bản class/loader phải có lifecycle đăng ký và cleanup rõ.

**Câu 7.** Native thread đã attach nhưng không bao giờ detach; có tác động gì?  
**Đáp án:** Có thể giữ resources và khiến JVM chờ thread non-daemon. Cần stop/detach theo lifecycle; thread mới attach daemon nếu phù hợp không làm mất nghĩa vụ cleanup.

**Câu 8.** Lợi ích của `GetObjectClass(callback)` + `GetMethodID` + global ref khi đăng ký là gì?  
**Đáp án:** Dùng chính class thực tế của callback Java, giải quyết đúng loader, giữ object sống trong thời gian worker cần, giảm phụ thuộc `FindClass` ở native thread.

## 11. Checklist khi triển khai production

- [ ] Xác định thread nào tạo từ Java, thread nào do native library tạo; chỉ detach thread mình thực sự attach.
- [ ] Mọi native worker gọi JNI đều có `JNIEnv*` **của chính thread đó**; giữ `JavaVM*` thay vì chia sẻ env.
- [ ] Callback và class/loader cần dùng sau native method return được giữ bằng **global JNI reference** có owner và điểm hủy rõ.
- [ ] Resolve class/method tại registration trên đúng Java/class-loader context; kiểm tra JNI method signatures và pending exceptions.
- [ ] Tránh `FindClass` cho app/plugin class từ native worker nếu không chủ động xác định đúng loader.
- [ ] Callback Java throw thì có **error channel** rõ (caller, future, queue hoặc listener), không nuốt lỗi im lặng.
- [ ] Worker có stop/drain/join hoặc protocol shutdown; không xóa global refs khi còn callback đang chạy.
- [ ] Không giữ lock có thể tạo vòng chờ khi Java caller và native worker gọi qua lại.
- [ ] Sau stop, dọn references/threads/native handles/caches và bỏ references giữ plugin loader cũ.
- [ ] Kiểm thử cả case Java classpath đơn giản **và** app được nạp qua class loader thực (container/plugin), bao gồm reload.

## 12. Ghi nhớ và tài liệu đối chiếu

- **`JavaVM*` gắn với VM; `JNIEnv*` gắn với thread.** Native thread phải attach trước mọi JNI call và detach khi kết thúc.
- **`FindClass` chọn loader theo ngữ cảnh JNI**, không mặc định theo loader mong muốn của plugin hay thread context class loader.
- Đối với callback, **truyền instance hoặc `Class<?>` từ Java rồi giữ global ref** là cách dễ xác định đúng class identity.
- **Local refs không vượt lifetime native frame**, còn global refs phải được delete theo lifecycle để tránh leak và class-loader retention.
- **Exception pending là thread-local**; muốn Java caller nhận lỗi từ worker phải có cơ chế handoff rõ.
- **Stop/drain trước khi xóa global refs**, giữ đồng bộ và không để native callbacks tiếp tục chạy vào plugin đã dỡ.

Nguồn chính thức:

- [Oracle JNI Specification — Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `AttachCurrentThread`, `DetachCurrentThread`, `GetEnv`, thread context loader và quy tắc thread.
- [Oracle JNI Specification — Functions: FindClass (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): cách `FindClass` chọn class loader từ current native method hoặc Invocation Interface.
- [Oracle JNI Specification — Functions: Object/Global Reference/Method Operations](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, `GetObjectClass`, `GetMethodID` và `CallVoidMethod`.
- [Oracle JNI Specification — Design Overview (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): class-name conventions, Java/native exceptions và reference lifetime.
- [Android NDK — JNI Tips (Google)](https://developer.android.com/ndk/guides/jni-tips): kinh nghiệm callback, attached threads và class-loader lookup trên runtime Android; xem như ví dụ hệ sinh thái, không dùng thay chuẩn JNI Java SE.
