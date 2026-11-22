# Gắn luồng bản địa bằng AttachCurrentThread hoặc AttachCurrentThreadAsDaemon (JNI)

## 1. Khi nào một luồng native phải attach vào JVM?

Trong JNI (Java Native Interface), luồng Java gọi một phương thức `native` đã có sẵn ngữ cảnh JNI để thực thi mã C/C++. Nhưng ứng dụng cũng có thể tạo **luồng từ phía native** bằng `std::thread`, `pthread_create`, `CreateThread` hoặc thread pool của thư viện C/C++. Luồng đó không tự nhiên có quyền sử dụng `JNIEnv` để truy cập object, class hay gọi phương thức Java.

Muốn một **luồng native do thư viện tạo** gọi ngược vào Java, luồng ấy phải **gắn (attach) với JVM** bằng một trong hai hàm của **JNI Invocation API**:

- `JavaVM::AttachCurrentThread`: gắn luồng hiện tại vào JVM ở trạng thái **non-daemon (user thread)**.
- `JavaVM::AttachCurrentThreadAsDaemon`: gắn luồng hiện tại vào JVM ở trạng thái **daemon thread**.

Cả hai cung cấp một con trỏ `JNIEnv*` **thuộc đúng luồng đã gọi attach**. Khi luồng native hoàn tất công việc và không còn Java frame trong stack, nó phải gọi `JavaVM::DetachCurrentThread` trước khi kết thúc. Không nên giữ luồng mãi ở trạng thái attached chỉ vì không thấy lỗi ngay lập tức.

**Quy tắc quan trọng:** attach là thao tác của **luồng đang chạy**. Không thể gọi `AttachCurrentThread` từ luồng A để attach thay cho luồng B. Luồng nào cần truy cập JNI thì **chính luồng đó** gọi attach, nhận `JNIEnv*` riêng, rồi tự detach đúng thời điểm.

### 1.1. Mô hình thời gian

```text
Java main thread                         Native worker (std::thread)
       |                                            |
       | gọi native launch(...)                     |
       |          |                                 | (mới tạo, chưa attached)
       |          +---- tạo worker ----------------->|
       |                                            |
       |                                  JavaVM.AttachCurrentThread(...)
       |                                  hoặc AttachCurrentThreadAsDaemon(...)
       |                                            |
       |                                  nhận JNIEnv* của worker
       |                                            |
       |                                  tra cứu class/method, gọi Java
       |<---------------------- Java callback ------+
       |                                            |
       |                                  JavaVM.DetachCurrentThread()
       |                                            |
       |<---------------------- worker kết thúc -----+
       |          |
       |   join worker, hoàn tất
       |
```

Ở chiều gọi thông thường **Java → native**, JNI runtime truyền `JNIEnv*` vào hàm C. Ở chiều **native-created thread → Java**, worker phải attach trước khi được dùng API JNI.

## 2. `JavaVM*` khác `JNIEnv*` như thế nào?

| Đối tượng | Phạm vi sử dụng | Mục đích |
| --- | --- | --- |
| `JavaVM*` | Có thể lưu/chia sẻ giữa các native thread theo vòng đời JVM | Gọi `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread` |
| `JNIEnv*` | **Chỉ hợp lệ trong luồng sở hữu nó** | `FindClass`, `GetMethodID`, `Call...Method`, tạo/đọc JNI reference, kiểm tra exception |

Không truyền hoặc cache một `JNIEnv*` lấy từ thread A rồi dùng trên thread B. Mỗi thread phải lấy interface pointer của **chính mình**. Ngược lại, có thể lưu `JavaVM*` từ `JNIEnv::GetJavaVM` hoặc tham số `JNI_OnLoad` để các native worker lấy `JNIEnv*` khi cần.

Trong **C++** (JNI API theo kiểu wrapper):

```cpp
JavaVM* vm = nullptr;
jint result = env->GetJavaVM(&vm);
```

Đoạn trên là **trích đoạn nằm trong hàm JNI đã có `JNIEnv* env`**; không phải chương trình độc lập. Nếu `result == JNI_OK`, `vm` có thể được giữ để gọi các hàm Invocation API trong các luồng native khác. Không được suy luận rằng `env` ở dòng đầu có thể được giữ dùng chung.

Trong **C** thay vì cú pháp C++ `vm->...` thường có dạng:

```c
JavaVM *vm = NULL;
jint result = (*env)->GetJavaVM(env, &vm);
/* Trong native worker C: */
JNIEnv *thread_env = NULL;
jint rc = (*vm)->AttachCurrentThread(vm, (void **)&thread_env, NULL);
```

Hai cách gọi trên thực hiện cùng chức năng nhưng khác cú pháp wrapper trong `jni.h`.

## 3. Phân biệt AttachCurrentThread với AttachCurrentThreadAsDaemon

| Tiêu chí | `AttachCurrentThread` | `AttachCurrentThreadAsDaemon` |
| --- | --- | --- |
| Trạng thái **lần attach đầu tiên** | Non-daemon | Daemon |
| Con trỏ nhận được | `JNIEnv*` của thread hiện tại | `JNIEnv*` của thread hiện tại |
| Khả năng gọi Java/JNI | Có | Có |
| Thread đã attached? | Trả lại `JNIEnv*` hiện có; không đổi daemon status | Cũng trả lại `JNIEnv*` hiện có; không đổi daemon status |
| Ảnh hưởng shutdown JVM | Non-daemon thread có thể làm JVM phải chờ trước khi kết thúc | Daemon thread **không giữ JVM sống chỉ vì còn chạy** |
| Cleanup | Phải detach trước khi native thread kết thúc | Cũng phải detach trước khi native thread kết thúc |
| Dùng điển hình | Worker phải hoàn thành công việc quan trọng trước shutdown | Worker nền mà hệ thống có quy trình hủy/shutdown riêng |

**Daemon không có nghĩa “thread được giải phóng tự động”.** Nó chỉ ảnh hưởng quy tắc **JVM còn phải chờ non-daemon threads hay không**. Luồng daemon vẫn phải được quản lý tài nguyên, báo lỗi, dừng và detach. Nếu JVM đang shutdown trong khi daemon native thread còn muốn gọi Java, không được giả định callback vẫn hoạt động bình thường.

### 3.1. Chọn đúng ngay từ lần attach đầu tiên

Nếu thread chưa attached:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&threadEnv), nullptr);
```

Tạo attachment non-daemon.

Nếu thread chưa attached và bạn muốn daemon:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&threadEnv), nullptr);
```

Tạo attachment daemon.

Trong hai ví dụ trên, `vm` là `JavaVM*` hợp lệ và code chạy **trong native thread cần attach**. Sau lời gọi phải kiểm tra `rc == JNI_OK` và `threadEnv != nullptr` trước khi dùng `threadEnv`.

**Trường hợp đã attached:** JNI quy định gọi lại attach trả chính `JNIEnv*` hiện tại và **không chuyển đổi** non-daemon thành daemon hoặc ngược lại. Vì vậy nếu đã gọi `AttachCurrentThread`, sau đó gọi `AttachCurrentThreadAsDaemon` **không biến thread ấy thành daemon**; muốn chọn khác, thiết kế lifecycle từ đầu (không detach/re-attach khi còn Java frames).

### 3.2. Tình huống shutdown cụ thể

Giả sử Java `main` kết thúc nhưng vẫn có một native worker đã được attach:

- Nếu worker là **non-daemon**, JVM sẽ tính nó vào các non-daemon threads có thể ngăn tiến trình Java kết thúc cho đến khi thread thoát/detach theo vòng đời thích hợp.
- Nếu worker là **daemon**, chỉ sự tồn tại của nó không giữ JVM tiếp tục chạy. JVM có thể bắt đầu shutdown trong khi nó chưa xong.
- Một lệnh `std::thread::join()` ở phía Java/JNI lại **chờ worker kết thúc một cách chủ động**, bất kể worker attach dưới dạng daemon hay non-daemon. Vì vậy cần phân biệt **đợi do chương trình gọi join** với **quy tắc duy trì JVM của daemon status**.

Không chọn daemon chỉ để “chữa” lỗi rò rỉ thread; điều đúng là thiết kế stop signal, hủy tài nguyên và detach rõ ràng.

## 4. Vòng đời attach → dùng JNI → detach

Quy trình cho một worker do C/C++ tạo:

1. Lấy hoặc lưu `JavaVM*` trong bối cảnh JNI hợp lệ.
2. Tạo native worker. **Trong thân của worker**, gọi `AttachCurrentThread` hoặc `AttachCurrentThreadAsDaemon`, tùy nhu cầu.
3. Kiểm tra mã trả về; chỉ khi `JNI_OK` mới dùng `JNIEnv*` nhận được.
4. Khi cần, lưu `jobject`/`jclass` dùng qua nhiều luồng bằng **global reference**, không mang local reference từ luồng khác sang.
5. Tra cứu phương thức, gọi Java, kiểm tra và xử lý Java exception đang chờ.
6. Đảm bảo mọi Java method đã trở về native, mọi resource JNI liên quan đã được giải quyết và không còn Java frame đang chạy trên stack của worker.
7. Gọi `DetachCurrentThread` từ **chính worker** trước khi native worker kết thúc. Sau detach, không dùng `JNIEnv*` cũ.

Nếu hàm `AttachCurrentThread` thất bại, chưa có attachment thành công để detach. Nếu worker vốn **đã attached từ trước**, phải biết ai sở hữu attachment đó; không tự detach một thread đang phục vụ Java framework khác chỉ vì bạn gọi `GetEnv` hay gọi attach thêm lần nữa.

### 4.1. Điều kiện detach có thể dễ bị quên

JNI Specification quy định một thread **không thể detach chính nó khi vẫn còn Java methods trên call stack**. Ví dụ:

- Đúng: native worker attach → gọi Java callback → callback trả về native → native worker detach.
- Sai: yêu cầu detach trong lúc Java callback vẫn đang chạy trên cùng stack (hoặc gọi detach trước khi xử lý hết call stack Java lồng nhau).

Nếu native thread thoát mà vẫn attached, tài nguyên JVM liên quan đến thread có thể bị giữ lại hoặc hành vi không theo hợp đồng API. Native worker cần cleanup ngay cả ở nhánh thất bại. Không coi detach là thao tác tùy chọn.

## 5. GetEnv: kiểm tra thread đã attached hay chưa

`JavaVM::GetEnv` **không tự attach**. Nó tra trạng thái attachment của **luồng hiện tại** đối với một phiên bản JNI yêu cầu:

```cpp
JNIEnv* threadEnv = nullptr;
jint rc = vm->GetEnv(
        reinterpret_cast<void**>(&threadEnv),
        JNI_VERSION_1_6);

if (rc == JNI_OK) {
    // Luồng đã attached; threadEnv hợp lệ ở chính luồng này.
} else if (rc == JNI_EDETACHED) {
    // Luồng chưa attached; có thể tự attach nếu cần.
} else if (rc == JNI_EVERSION) {
    // JVM không hỗ trợ JNI version đã yêu cầu.
}
```

Đây là **đoạn minh họa C++ đặt trong code có `JavaVM* vm` hợp lệ**. `JNI_VERSION_1_6` được JDK 17 hỗ trợ và thường dùng trong ví dụ JNI; không có nghĩa chương trình Java bắt buộc chạy Java 6.

Một mẫu sở hữu attachment hữu ích:

```cpp
JNIEnv* env = nullptr;
bool attachedHere = false;

jint status = vm->GetEnv(
        reinterpret_cast<void**>(&env), JNI_VERSION_1_6);

if (status == JNI_EDETACHED) {
    status = vm->AttachCurrentThread(
            reinterpret_cast<void**>(&env), nullptr);
    if (status == JNI_OK) {
        attachedHere = true;
    }
}
if (status != JNI_OK || env == nullptr) {
    // Báo lỗi cho phía sở hữu công việc.
    return;
}

// Truy cập JNI bằng env ở đúng thread này.
// ... Hoàn tất mọi callback Java và giải quyết exception ...

if (attachedHere) {
    (void) vm->DetachCurrentThread();
}
```

Mẫu này **không phải chương trình độc lập**; trong mã thực tế nên đưa cleanup vào cấu trúc bảo đảm chạy ở mọi đường thoát, ví dụ RAII guard trong C++. Nó tránh detach một thread đã attached từ trước do Java/runtime quản lý.

## 6. Ví dụ hoàn chỉnh Java 17 + C++17: native thread gọi lại Java

Ví dụ cho thấy **hai lần attach khác nhau**, một non-daemon và một daemon. Java gọi một JNI entry point để tạo `std::thread`; chính `std::thread` gọi một callback Java, rồi detach. JNI entry point gọi `join()` trước khi trả về, nên thứ tự stdout ổn định.

Ví dụ sử dụng C++17 thay cho `pthread` để thống nhất logic đa nền tảng; build riêng cho Linux, macOS và Windows. Thư viện phải được biên dịch đúng OS/CPU/JDK headers.

### 6.1. Tệp `NativeAttachDemo.java`

```java
public final class NativeAttachDemo {
    static {
        System.loadLibrary("nativeattachdemo");
    }

    private NativeAttachDemo() {
    }

    // Được triển khai trong NativeAttachDemo.cpp.
    private static native void launch(boolean daemon);

    // Worker native sau khi attached sẽ gọi phương thức này.
    private static void onNativeThread() {
        System.out.println(
                "callback: daemon=" + Thread.currentThread().isDaemon());
    }

    public static void main(String[] args) {
        launch(false);  // AttachCurrentThread (non-daemon).
        launch(true);   // AttachCurrentThreadAsDaemon.
        System.out.println("finished");
    }
}
```

`Thread.currentThread()` ở đây chính là đối tượng `java.lang.Thread` đại diện cho luồng native đã attached. Phương thức `isDaemon()` phản ánh cách **lần attach đầu tiên** của native worker được thực hiện.

### 6.2. Sinh JNI header từ Java

Trong thư mục chứa `NativeAttachDemo.java`, chạy bằng JDK 17+:

```bash
javac -h . NativeAttachDemo.java
```

Kết quả là `NativeAttachDemo.class` và `NativeAttachDemo.h`. Header xác nhận JNI native symbol `Java_NativeAttachDemo_launch`, tham số `JNIEnv*`, `jclass` và `jboolean`. Không tự đoán tên symbol khi class/package thay đổi; sử dụng header do `javac -h` sinh ra.

### 6.3. Tệp `NativeAttachDemo.cpp`

```cpp
#include "NativeAttachDemo.h"

#include <atomic>
#include <exception>
#include <thread>

static void throwIllegalState(JNIEnv* env, const char* message) {
    jclass errorClass = env->FindClass("java/lang/IllegalStateException");
    if (errorClass != nullptr) {
        env->ThrowNew(errorClass, message);
        env->DeleteLocalRef(errorClass);
    }
}

extern "C" JNIEXPORT void JNICALL
Java_NativeAttachDemo_launch(
        JNIEnv* callerEnv, jclass javaClass, jboolean daemon) {

    // Java gọi native: callerEnv chỉ thuộc thread gọi từ Java.
    JavaVM* vm = nullptr;
    if (callerEnv->GetJavaVM(&vm) != JNI_OK || vm == nullptr) {
        throwIllegalState(callerEnv, "Cannot obtain JavaVM");
        return;
    }

    // Local jclass chỉ có hiệu lực trong ngữ cảnh JNI gọi vào.
    // Global reference mới được giữ an toàn qua native thread.
    jclass globalClass = static_cast<jclass>(
            callerEnv->NewGlobalRef(javaClass));
    if (globalClass == nullptr) {
        return;  // JVM có thể đã đặt OutOfMemoryError.
    }

    std::atomic<int> workerStatus{0};

    try {
        std::thread worker([vm, globalClass, daemon, &workerStatus]() {
            JNIEnv* workerEnv = nullptr;
            char name[] = "jni-native-worker";

            JavaVMAttachArgs args{};
            args.version = JNI_VERSION_1_6;
            args.name = name;
            args.group = nullptr;

            jint attached = (daemon == JNI_TRUE)
                    ? vm->AttachCurrentThreadAsDaemon(
                            reinterpret_cast<void**>(&workerEnv), &args)
                    : vm->AttachCurrentThread(
                            reinterpret_cast<void**>(&workerEnv), &args);

            if (attached != JNI_OK || workerEnv == nullptr) {
                workerStatus.store(1);
                return;
            }

            // JNI lookup và callback đều chạy trong worker đã attached.
            jmethodID callback = workerEnv->GetStaticMethodID(
                    globalClass, "onNativeThread", "()V");

            if (callback != nullptr) {
                workerEnv->CallStaticVoidMethod(globalClass, callback);
            }

            if (workerEnv->ExceptionCheck()) {
                // Demo: ghi chi tiết ở stderr và báo lỗi về caller.
                // Trong sản phẩm thật có thể chuyển throwable qua
                // global reference hoặc gửi lỗi lên event queue.
                workerEnv->ExceptionDescribe();
                workerEnv->ExceptionClear();
                workerStatus.store(2);
            } else if (callback == nullptr) {
                workerStatus.store(2);
            }

            // Đảm bảo Java callback đã quay về C++ trước detach.
            if (vm->DetachCurrentThread() != JNI_OK) {
                workerStatus.store(3);
            }
            // workerEnv không được dùng nữa từ thời điểm này.
        });

        // Cả hai chế độ đều chờ worker kết thúc cho ví dụ xác định.
        worker.join();
    } catch (const std::exception&) {
        callerEnv->DeleteGlobalRef(globalClass);
        throwIllegalState(callerEnv, "Cannot create/join native worker");
        return;
    }

    // Worker đã kết thúc, không còn dùng globalClass.
    callerEnv->DeleteGlobalRef(globalClass);

    if (workerStatus.load() != 0) {
        throwIllegalState(callerEnv, "Native worker failed");
    }
}
```

Đây là **mã hoàn chỉnh của một shared library JNI** dùng trong ví dụ này; không cần `JNI_OnLoad` vì `JavaVM*` được lấy bằng `callerEnv->GetJavaVM(&vm)` ngay khi Java gọi native method.

Điểm cần hiểu:

- `callerEnv` thuộc **Java calling thread**. Nó chỉ được dùng ở ngoài lambda; worker **không sử dụng** nó.
- `vm` thuộc JVM và có thể chia sẻ giữa các thread trong thời gian JVM tồn tại. Worker dùng `vm` để attach rồi nhận `workerEnv` của riêng mình.
- `javaClass` là **local reference** của cuộc gọi ban đầu. `NewGlobalRef` tạo `globalClass` có thể dùng trong worker; xóa bằng `DeleteGlobalRef` khi `join` hoàn tất.
- `GetStaticMethodID` và `CallStaticVoidMethod` diễn ra sau attach. Callback có descriptor `()V` vì không có tham số và trả `void`.
- `ExceptionCheck` được gọi trong worker vì exception của callback thuộc **JNI environment trên worker đó**, không tự động bật ra như Java exception trong thread gọi `launch`. Ví dụ ghi stderr và chuyển thành `IllegalStateException` chung ở thread gọi ban đầu; production code cần truyền nguyên nhân rõ ràng hơn nếu cần.
- `DetachCurrentThread` chạy **trong worker**, sau khi callback đã kết thúc; `std::thread::join` chạy trên thread gọi ban đầu để đồng bộ vòng đời.
- `workerStatus` là atomic để trao đổi trạng thái lỗi giữa hai thread; thứ tự kết quả thông thường không phụ thuộc tốc độ scheduler.

### 6.4. Biên dịch và chạy trên Linux

Cần JDK 17+ với `JAVA_HOME` đúng, trình biên dịch `g++` và hỗ trợ pthread:

```bash
javac -h . NativeAttachDemo.java

g++ -std=c++17 -shared -fPIC -pthread \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    NativeAttachDemo.cpp -o libnativeattachdemo.so

java -Djava.library.path=. NativeAttachDemo
```

### 6.5. Biên dịch và chạy trên macOS

Cần JDK 17+ với `JAVA_HOME` đúng và Clang/Xcode Command Line Tools:

```bash
javac -h . NativeAttachDemo.java

clang++ -std=c++17 -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    NativeAttachDemo.cpp -o libnativeattachdemo.dylib

java -Djava.library.path=. NativeAttachDemo
```

### 6.6. Biên dịch và chạy trên Windows

Mở Developer Command Prompt for Visual Studio tương ứng với kiến trúc của JDK (ví dụ x64). Cấu hình `JAVA_HOME` và chạy với `cmd.exe`:

```bat
javac -h . NativeAttachDemo.java

cl /nologo /std:c++17 /EHsc /LD ^
    /I"%JAVA_HOME%\include" ^
    /I"%JAVA_HOME%\include\win32" ^
    NativeAttachDemo.cpp /link /OUT:nativeattachdemo.dll

java -Djava.library.path=. NativeAttachDemo
```

Dòng `^` trong ví dụ Windows là ký tự nối dòng của `cmd.exe`; nếu chạy trong PowerShell, dùng một dòng lệnh `cl` hoặc cú pháp PowerShell thích hợp.

### 6.7. Đầu ra và phân tích

Nếu biên dịch, nạp library và callback thành công, **stdout chính xác** của cả hai lần attach là:

```text
callback: daemon=false
callback: daemon=true
finished
```

Giải thích:

1. `launch(false)` tạo một worker mới. Worker gọi `AttachCurrentThread`, nên `Thread.currentThread().isDaemon()` trong callback là `false`.
2. Worker thứ nhất detach và kết thúc, `join` trả về.
3. `launch(true)` tạo một worker mới khác, gọi `AttachCurrentThreadAsDaemon`, nên callback in `true`.
4. Worker thứ hai detach, `join` trả về; Java in `finished`.

Vì mỗi lần `launch` đợi `join`, thứ tự dòng luôn ổn định trên đường đi thành công. **Đừng lấy ví dụ này làm bằng chứng rằng daemon thread tự được join hoặc tự detach**: cả hai hành động đều do chương trình viết rõ.

**Lưu ý JDK 24+:** Một số cấu hình/JDK có thể cảnh báo hoặc hạn chế native access theo cơ chế đưa vào từ JDK 24 (JEP 472). Khi chạy classpath trên JDK có hỗ trợ, có thể cấp quyền tường minh:

```bash
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. NativeAttachDemo
```

Lệnh này dùng cho các JDK hỗ trợ tùy chọn đó; với JDK 17, sử dụng lệnh chạy gốc ở trên. Thông báo cảnh báo của JVM, nếu có, thường thuộc stderr và không phải stdout của ví dụ.

## 7. JavaVMAttachArgs: đặt tên và ThreadGroup cho native worker

Tham số cuối của attach có thể là `nullptr` để JVM dùng mặc định, hoặc là một cấu trúc `JavaVMAttachArgs`:

```cpp
char name[] = "camera-callback";

JavaVMAttachArgs args{};
args.version = JNI_VERSION_1_6;
args.name = name;
args.group = nullptr;

JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&env), &args);
```

Đây là **đoạn code sử dụng trong native thread**, với `JavaVM* vm` đã hợp lệ.

- `version`: phiên bản JNI được chỉ định trong cấu trúc. Đừng nhầm với Java language level hoặc số phiên bản JVM (`17` không phải giá trị để gán trực tiếp).
- `name`: tên dùng cho Java thread đại diện; dữ liệu tên theo quy ước **modified UTF-8** của JNI. Dùng mảng char hợp lệ trong thời gian attach; nếu không cần tên, đặt `nullptr`.
- `group`: reference toàn cục (`global reference`) tới `ThreadGroup` hoặc `nullptr` nếu dùng mặc định. Không truyền local reference từ thread khác vào.
- Nếu thread **đã attached**, gọi attach lại chỉ trả interface pointer hiện có; không dùng attach lần hai như API thay tên, group hoặc daemon status.

Trên thread vừa được attach, context class loader ban đầu theo đặc tả là **bootstrap loader**. Do đó nếu code native callback dùng `FindClass` để tìm lớp ứng dụng tùy ý, kết quả có thể không như mong muốn khi không có Java calling frame.

## 8. Class loader và reference: lỗi thường xảy ra sau khi attach thành công

### 8.1. `FindClass` không thấy class ứng dụng

Một native-created thread sau attach không có Java caller để xác định loader giống cuộc gọi Java→native. Vì vậy code:

```cpp
jclass cls = env->FindClass("com/example/MyCallback");
```

có thể thất bại dù `MyCallback.class` nằm trên classpath của một class loader ứng dụng đặc biệt.

**Cách làm đáng tin trong nhiều trường hợp:** từ thread Java đã biết đúng class, tạo **`NewGlobalRef` cho `jclass` hoặc object callback**; đưa global reference đó vào worker như ví dụ `NativeAttachDemo`. Có thể cache `jmethodID` sau khi tra cứu class đúng, miễn vẫn quản lý vòng đời class/loader tương ứng. Trong hệ thống plugin/class loader phức tạp, cũng có thể thiết lập context class loader phù hợp một cách có chủ đích, nhưng không nên trông chờ mặc định đúng.

### 8.2. Local JNI reference không sống xuyên thread

`jobject`, `jclass` nhận trong một JNI method thường là **local reference** của ngữ cảnh hiện tại. Việc capture thẳng local ref vào `std::thread` rồi dùng sau khi hàm native trả về có thể dẫn đến reference đã hết hiệu lực. Khi cần truy cập từ worker:

1. Gọi `NewGlobalRef` trước khi chuyển quyền sử dụng.
2. Cho worker dùng global ref trong suốt vòng đời hợp lệ.
3. Gọi `DeleteGlobalRef` khi chắc chắn không thread nào còn dùng.

Không phải tất cả JVM objects đều nên bị giữ bằng global ref mãi mãi; reference giữ mạnh còn có thể ngăn GC thu gom đối tượng.

### 8.3. Không gọi Java khi thread chưa attach

Ví dụ sai:

```cpp
// SAI: callerEnv lấy từ Java thread khác!
std::thread worker([callerEnv]() {
    callerEnv->FindClass("java/lang/String");
});
```

Đây là mã **minh họa lỗi**, không phải ví dụ để chạy. `callerEnv` thuộc thread gọi Java; đem pointer đó sang worker là vi phạm hợp đồng JNI, có thể gây lỗi khó đoán hoặc crash.

Đúng: capture `JavaVM*` (có vòng đời hợp lệ), attach trong worker, rồi sử dụng `JNIEnv*` mới trả về ở chính worker ấy.

## 9. Exception, shutdown và cleanup trong ứng dụng thật

### 9.1. Khi Java callback ném exception

Nếu Java method được gọi qua `Call...Method` ném exception, **JNIEnv của native worker** sẽ có pending exception. Không được coi nó tự động truyền sang thread đã tạo worker ở phía Java. Lựa chọn xử lý:

- Phát hiện bằng `ExceptionCheck()`.
- Thu thập nguyên nhân và chuyển về cơ chế báo lỗi của sản phẩm (log, callback lỗi riêng, event queue, future/promise). Nếu dùng `jthrowable` vượt qua thread, phải quản lý reference phù hợp.
- Chỉ `ExceptionClear()` khi **đã chủ động quyết định cách xử lý**; không xóa exception âm thầm.
- Cleanup và detach đúng thứ tự khi không còn Java call trên stack.

Trong ví dụ trên, `ExceptionDescribe` ghi chẩn đoán vào stderr và exception được clear có chủ đích để worker detach; thread gọi ban đầu nhận một `IllegalStateException` tổng quát nếu worker báo lỗi. Đây là đường đi giáo dục, không phải cơ chế bảo toàn stack trace xuyên thread đầy đủ.

### 9.2. Cần dừng native workers trước khi JVM rời đi

Đặc biệt với daemon worker, cần có trình tự hủy:

1. Java hoặc native owner phát tín hiệu dừng.
2. Worker ngừng tạo callback mới, thoát vòng lặp, dọn resource JNI.
3. Worker detach và kết thúc native thread.
4. Owner join hoặc chờ hoàn tất khi còn JVM hợp lệ; xóa global references của các object/class đã cache.

Không gọi attach/callback sau khi VM đã shutdown. Không nhầm “daemon không chặn shutdown” với “daemon chắc chắn được Java đợi chạy xong”.

### 9.3. Không detach một Java-created thread tùy tiện

Khi Java gọi xuống một native method, thread đang **attached** sẵn. Đừng gọi `DetachCurrentThread` trong native method đó: Java frame vẫn còn trên call stack và việc detach trong hoàn cảnh đó không hợp lệ. Chỉ detach các native-created threads mà code của bạn thực sự sở hữu, sau khi Java callback trở lại C/C++.

### 9.4. Performance và thread pool

Attach/detach có chi phí runtime; tạo rồi phá native thread cho mỗi sự kiện nhỏ có thể quá tốn kém. Với workload dày đặc, có thể dùng native thread pool: mỗi worker attach một lần khi bắt đầu, xử lý callback trong vòng đời phù hợp, rồi detach khi thread kết thúc. Nhưng:

- Đừng để **non-daemon worker vô hạn** chặn JVM thoát.
- Đừng giữ JNI local references hoặc Java objects toàn cục lâu không cần thiết.
- Đừng giữ callback trên daemon worker hoạt động sau shutdown.
- Đo latency, GC, số lượng thread và khả năng dừng sạch theo môi trường chạy thực.

## 10. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao nguy hiểm? | Cách đúng |
| --- | --- | --- |
| Dùng `JNIEnv*` của Java thread trong native worker | `JNIEnv*` chỉ hợp lệ ở thread sở hữu | Chia sẻ `JavaVM*`, attach worker để lấy `JNIEnv*` riêng |
| Gọi `GetEnv` rồi nghĩ JVM sẽ tự attach | `GetEnv` có thể trả `JNI_EDETACHED` | Nếu detached, gọi Attach phù hợp rồi tự quản lý detach |
| Không kiểm tra kết quả Attach | `JNIEnv*` có thể chưa hợp lệ | Chỉ sử dụng nếu `rc == JNI_OK` và pointer không null |
| Attach AsDaemon sau Attach để đổi trạng thái | Attach lại trên thread đã attached không đổi daemon status | Chọn đúng loại trước lần attach đầu |
| Gọi `DetachCurrentThread` từ thread khác | Detach là của chính thread hiện tại | Worker tự detach trong chính thân worker |
| Detach khi Java callback chưa trả về | Không thể detach nếu còn Java frame trên stack | Đợi callback trở lại C/C++ rồi detach |
| Quên detach khi native worker kết thúc | Rò rỉ tài nguyên/vòng đời JVM sai | Thiết kế cleanup cho mọi nhánh thành công và lỗi |
| Capture local `jobject` từ luồng khác | Local ref không được dùng tùy tiện xuyên thread/lifetime | `NewGlobalRef` và `DeleteGlobalRef` theo ownership |
| `FindClass` trong attached worker không thấy lớp ứng dụng | Context class loader có thể khác, thường bootstrap | Đưa `jclass`/object global ref từ loader đúng |
| Bỏ qua Java exception sau callback | Lỗi có thể nằm trong worker env; tiếp tục JNI sai | `ExceptionCheck` và truyền/báo lỗi rõ ràng |
| Dùng daemon để “khỏi phải cleanup” | Daemon chỉ ảnh hưởng giữ JVM sống | Quản lý stop, join, reference và detach |
| Dùng non-daemon vô hạn không có stop | JVM có thể không thể shutdown | Có cơ chế dừng worker và detach |
| Giữ `JavaVM*` rồi dùng sau shutdown | Vòng đời JVM đã kết thúc | Đồng bộ shutdown trước khi VM dừng |

## 11. Hỏi đáp kiểm tra kiến thức

**1. Native thread đã có `JavaVM*` thì có cần attach không?** Nếu thread chưa attached và muốn gọi JNI, **có**. `JavaVM*` cho phép **lấy** environment; nó không thay thế `JNIEnv*`.

**2. `GetEnv` trả `JNI_EDETACHED` có phải lỗi nghiêm trọng không?** Không nhất thiết. Nó cho biết **thread hiện tại chưa attached**. Nếu cần làm JNI, gọi Attach tương ứng rồi kiểm tra kết quả.

**3. Gọi `AttachCurrentThreadAsDaemon` trên thread đang non-daemon sẽ đổi thành daemon chứ?** Không. Với thread đã attached, attach chỉ trả interface pointer hiện tại và giữ nguyên daemon status.

**4. Có thể dùng một `JNIEnv*` cho toàn bộ native thread pool không?** Không. Mỗi thread trong pool cần environment của riêng nó và cleanup thích hợp.

**5. Daemon native worker có bắt buộc `DetachCurrentThread` không?** Có. Quy tắc detach không được bỏ qua vì daemon status.

**6. Lúc worker gọi `CallStaticVoidMethod` xong, có thể detach ngay không?** Có thể sau khi callback đã trở về native và những điều kiện cleanup/exception cần thiết được đáp ứng; không được detach khi Java method vẫn còn trên call stack.

**7. Vì sao ví dụ chỉ in stdout theo đúng thứ tự dù có tạo native thread?** Vì `launch` gọi `join()` cho mỗi worker trước khi trở lại Java. Điều này không phải tính chất tự động của daemon.

**8. Vì sao `FindClass("app/MyClass")` có thể thất bại sau attach?** Context class loader của newly attached thread không tự giống application class loader; cần truyền class/global ref hoặc cấu hình lookup phù hợp.

## 12. Checklist khi đưa vào sản phẩm

1. Xác định thread do **Java** hay **native** tạo và ai sở hữu attachment.
2. Lưu/chia sẻ đúng `JavaVM*`, **không chia sẻ `JNIEnv*`**.
3. Nếu cần, gọi `GetEnv` để phân biệt `JNI_OK` / `JNI_EDETACHED` / `JNI_EVERSION`.
4. Chọn **non-daemon** hoặc **daemon** theo yêu cầu sống/chết của ứng dụng **trước lần attach đầu**.
5. Kiểm tra mã `JNI_OK`, dùng đúng `JNIEnv*` trên thread đã attach.
6. Dùng **global references** cho dữ liệu qua thread, chú ý class loader và JNI exception.
7. Kết thúc callback Java trước khi detach; không detach thread do Java/runtime sở hữu.
8. Dọn tài nguyên, release global ref, **detach trong chính worker**, không dùng env sau đó.
9. Thiết kế stop/join khi shutdown JVM, nhất là native daemon worker.
10. Dùng test và monitoring cho đường đi thành công, attach thất bại, callback lỗi, Java shutdown và resource leaks.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — JNI Specification, Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): các hàm `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `GetEnv` và `DetachCurrentThread`.
- [Oracle Java 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `GetJavaVM`, local/global references, method lookup, Java callbacks và exception handling.
- [Oracle Java 17 — JNI Types](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JNIEnv`, `jobject`, `jclass`, chữ ký JNI.
- [Oracle Java 17 — Thread.isDaemon](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#isDaemon()): cách đọc trạng thái daemon của thread trong Java.
- [OpenJDK JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472): cơ chế cảnh báo/quyền native access cho JNI từ JDK 24.