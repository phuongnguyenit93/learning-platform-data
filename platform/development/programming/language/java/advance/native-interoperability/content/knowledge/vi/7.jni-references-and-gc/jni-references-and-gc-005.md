# Tạo, lưu giữ và xóa tham chiếu toàn cục trong JNI bằng `NewGlobalRef`, `DeleteGlobalRef`

## 1. Tham chiếu và GC: tại sao cần global reference?

Khi mã C/C++ giao tiếp với JVM qua Java Native Interface (JNI), một tham số Java kiểu đối tượng được truyền dưới dạng `jobject` (hoặc `jstring`, `jclass`, `jarray`...). Những giá trị này là **JNI reference** do JVM quản lý, không phải con trỏ C trực tiếp trỏ tới vị trí cố định trên Java heap. Garbage Collector (GC) có thể di chuyển đối tượng; native code vẫn dùng handle JNI hợp lệ để JVM định vị đối tượng.

Một tình huống kinh điển: Java đăng ký một listener cho thư viện C; C phải giữ listener để gọi callback **ở những lần gọi native sau**, khi hàm đăng ký đã kết thúc. Tham số `jobject` nhận ở hàm đăng ký thường là **local reference**: chỉ hợp lệ trong native frame và luồng tạo ra nó. Nếu C gán thẳng reference đó vào biến toàn cục, sau khi frame kết thúc nó không còn được bảo đảm hợp lệ.

Giải pháp JNI là hai thao tác:

- **`NewGlobalRef(env, obj)`** tạo một **strong global reference** mới. Handle này vẫn có hiệu lực qua những lần native call cho tới khi được xóa; reference mạnh giữ đối tượng reachable, ngăn GC thu gom nó chỉ vì Java không còn biến trỏ tới nó.
- **`DeleteGlobalRef(env, globalRef)`** xóa global reference do native code sở hữu. Nó giải phóng tài nguyên tham chiếu của JVM và bỏ một đường giữ object reachable. Object **không tự động bị xóa ngay**; GC chỉ có thể thu gom khi không còn strong reference khác.

Mô hình vòng đời:

```text
Java gọi register(listener)
       │ listener là local ref, hợp lệ trong native frame
       ▼
C: NewGlobalRef(env, listener)  ──► g_listener (global ref)
       │
Java register() trả về; local ref hết frame
       │
       ▼
C: giữ g_listener qua các native call; GC vẫn nhìn thấy strong root
       │
Java gọi emit() ──► C: CallVoidMethod(env, g_listener, ...)
       │
Java gọi unregister()
       ▼
C: DeleteGlobalRef(env, g_listener); g_listener = NULL
       │
GC có thể thu gom Java listener khi không còn root nào khác
```

Điểm then chốt: tạo global reference **không copy Java object**, không ghim địa chỉ heap và không tự đồng bộ nội dung object. Nó cung cấp **quy tắc sống/chết của tham chiếu** khi đi qua ranh giới Java ↔ native.

## 2. Local, strong global và weak global khác nhau thế nào?

| Đặc điểm | Local reference | Strong global reference | Weak global reference |
| --- | --- | --- | --- |
| Thường nhận/tạo từ | Tham số native, `GetObjectClass`, `NewLocalRef` | `NewGlobalRef` | `NewWeakGlobalRef` |
| Phạm vi | Native frame và **luồng hiện tại** | Qua nhiều JNI call; có thể truy cập từ luồng native gắn JVM hợp lệ | Qua nhiều JNI call nhưng đối tượng đích có thể bị GC thu gom |
| Giữ đối tượng không bị GC thu gom? | Có, trong lúc local ref hợp lệ | **Có**, tới khi xóa hoặc hết vòng đời JVM | **Không** |
| Giải phóng | `DeleteLocalRef` hoặc frame JNI kết thúc | **`DeleteGlobalRef`** | `DeleteWeakGlobalRef` |
| Nguy cơ chính | Lưu qua frame/đưa sang thread khác | Leak nếu không xóa; race khi hủy | Object đích mất giữa kiểm tra và sử dụng |

Ví dụ **sai**:

```c
static jobject g_listener = NULL;

// Sai: chỉ copy giá trị handle local, không tạo root JNI toàn cục.
g_listener = listener;
```

Đây là minh họa lỗi, không phải chương trình hoàn chỉnh. Sau khi native method trả về, `listener` có thể mất hiệu lực; việc C vẫn lưu bit-pattern của handle không tạo quyền sử dụng tiếp.

Cách đúng về nguyên tắc:

```c
jobject saved = (*env)->NewGlobalRef(env, listener);
if (saved == NULL) {
    // Kiểm tra input null / thiếu bộ nhớ / exception theo hợp đồng.
    return;
}
// Cất saved trong trạng thái native đã xác định owner,
// rồi xóa bằng DeleteGlobalRef khi subscription kết thúc.
```

Tạo reference mới khác với gán handle; JVM ghi nhận root mạnh. Tham chiếu nguồn `listener` vẫn là local reference và sẽ được dọn theo vòng đời riêng của nó.

## 3. Hợp đồng API `NewGlobalRef` và `DeleteGlobalRef`

### 3.1. `NewGlobalRef`

Khai báo C trong JNI:

```c
jobject NewGlobalRef(JNIEnv *env, jobject obj);
```

Cú pháp gọi:

```c
jobject global = (*env)->NewGlobalRef(env, obj);
```

- `env` phải là `JNIEnv *` hợp lệ **của luồng gọi hiện tại**.
- `obj` thường là JNI local/global reference hợp lệ; `NULL` cũng được chấp nhận. Nếu `obj == NULL`, kết quả là `NULL`.
- Hàm trả **một global reference mới** tới **cùng Java object**. Nguồn không bị xóa hay thay đổi.
- Hàm có thể trả `NULL` nếu hết bộ nhớ; nếu nguồn là weak global reference đã bị thu gom, cũng không thể nâng lên strong ref. **Không giả định mọi lần trả `NULL` đều nhất thiết có Java exception pending.**
- Có thể tạo nhiều global references tới cùng object; chúng là **những quyền sở hữu tham chiếu độc lập**, cần dọn riêng.

Khi `NewGlobalRef` trên nguồn đã xác định non-null trả `NULL`, code nên bảo toàn reference cũ (nếu đang thay listener), kiểm tra `ExceptionCheck`, xử lý tình trạng thiếu tài nguyên theo chính sách của ứng dụng, rồi không tiếp tục dùng handle thất bại.

### 3.2. `DeleteGlobalRef`

Khai báo:

```c
void DeleteGlobalRef(JNIEnv *env, jobject globalRef);
```

Cách dùng thông thường:

```c
if (global != NULL) {
    (*env)->DeleteGlobalRef(env, global);
    global = NULL;
}
```

`DeleteGlobalRef(env, NULL)` được phép và không làm gì. Tuy nhiên xóa **cùng một non-null handle hai lần** là sai: sau lần xóa đầu, giá trị cũ không còn hợp lệ. Khi code giữ nhiều bản sao của handle, phải làm chúng không còn được sử dụng trước hoặc đồng thời với việc xóa.

**Không nhầm xóa reference với xóa Java object.** Nếu Java vẫn giữ listener qua một field, collection, thread hay global ref khác, nó vẫn reachable sau khi C xóa một global reference. GC cũng không hứa thời điểm thu gom đối tượng vừa hết reachable.

### 3.3. Không dùng sai loại reference

| Giá trị | Hàm xóa đúng |
| --- | --- |
| Local `jobject` | `DeleteLocalRef` (hoặc JNI frame tự dọn) |
| Strong global `jobject` do `NewGlobalRef` tạo | `DeleteGlobalRef` |
| Weak global `jweak` do `NewWeakGlobalRef` tạo | `DeleteWeakGlobalRef` |

`jmethodID` và `jfieldID` không phải `jobject`; **không** đưa chúng vào hàm xóa reference. `GetObjectRefType(env, ref)` có thể giúp phân biệt loại reference **khi ref còn hợp lệ**, nhưng không được dùng với handle đã xóa để “kiểm tra xem có còn sống hay không”.

## 4. Ví dụ hoàn chỉnh Java 17+: đăng ký listener, callback nhiều lần, rồi hủy

Ví dụ sử dụng **Java 17+ và GCC trên Linux**, gồm Java source, C source và các lệnh build/run. Nó cố ý gọi JNI **tuần tự từ một Java thread** và không có callback song song. Hành vi đa luồng được giải thích riêng ở mục 7.

### 4.1. Cấu trúc thư mục

```text
jni-global-reference/
├── src/
│   └── demo/
│       └── jni/
│           └── GlobalReferenceDemo.java
├── native/
│   └── globalrefdemo.c
└── build/                       # Sinh tự động khi compile
```

### 4.2. Java source: `src/demo/jni/GlobalReferenceDemo.java`

```java
package demo.jni;

public final class GlobalReferenceDemo {
    static {
        System.loadLibrary("globalrefdemo");
    }

    public static final class Receiver {
        public void onEvent(int value) {
            System.out.println("Received: " + value);
        }
    }

    // Native giữ một strong global reference tới Receiver.
    private static native void registerReceiver(Receiver receiver);

    // Native gọi lại onEvent(int) của Receiver đã đăng ký.
    private static native void emit(int value);

    // Native xóa global reference khi không còn sử dụng.
    private static native void unregisterReceiver();

    public static void main(String[] args) {
        // Không giữ Receiver trong một Java field.
        registerReceiver(new Receiver());

        try {
            emit(5);
            emit(8);
        } finally {
            // Thực hiện cả khi callback ném Java exception.
            unregisterReceiver();
        }

        System.out.println("Unregistered");
    }
}
```

Hai lệnh `emit` được gọi **sau khi `registerReceiver` trả về**. Không giữ thêm reference ở Java là cách làm rõ trách nhiệm của JNI; không dùng `System.gc()` và không dựa vào việc GC nhất định chạy để chứng minh ví dụ hoạt động.

### 4.3. Sinh JNI header bằng `javac -h`

Chuyển tới thư mục `jni-global-reference`:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/GlobalReferenceDemo.java
```

JDK tạo `build/classes/demo/jni/GlobalReferenceDemo.class` cùng header `build/headers/demo_jni_GlobalReferenceDemo.h`. Vì ba native methods là `static`, phần prototype chính trong header tương đương:

```c
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_registerReceiver
  (JNIEnv *, jclass, jobject);
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_emit
  (JNIEnv *, jclass, jint);
JNIEXPORT void JNICALL Java_demo_jni_GlobalReferenceDemo_unregisterReceiver
  (JNIEnv *, jclass);
```

Đây là **đoạn trích để giải thích**, không thay cho header hoàn chỉnh có include guard và các macro do compiler tạo.

### 4.4. C source: `native/globalrefdemo.c`

```c
#include <jni.h>
#include "demo_jni_GlobalReferenceDemo.h"

// Chỉ truy cập tuần tự, không dùng đồng thời giữa các thread.
static jobject g_receiver = NULL;    // Strong global reference.
static jmethodID g_onEvent = NULL;   // Method ID, không phải JNI reference.

static void throw_java(JNIEnv *env, const char *className,
                       const char *message) {
    jclass exceptionClass = (*env)->FindClass(env, className);
    if (exceptionClass == NULL) {
        return; // Giữ nguyên exception nếu FindClass thất bại.
    }
    (*env)->ThrowNew(env, exceptionClass, message);
    (*env)->DeleteLocalRef(env, exceptionClass);
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_registerReceiver(
        JNIEnv *env, jclass owner, jobject receiver) {
    (void)owner; // Với static native, tham số thứ hai là jclass.

    if (receiver == NULL) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "receiver must not be null");
        return;
    }

    jclass receiverClass = (*env)->GetObjectClass(env, receiver);
    if (receiverClass == NULL) {
        return;
    }

    jmethodID callback = (*env)->GetMethodID(
            env, receiverClass, "onEvent", "(I)V");
    (*env)->DeleteLocalRef(env, receiverClass);
    if (callback == NULL) {
        return; // Có thể có NoSuchMethodError pending.
    }

    // receiver là local ref. Tạo global ref khi nó còn hợp lệ.
    jobject newRef = (*env)->NewGlobalRef(env, receiver);
    if (newRef == NULL) {
        // JNI có thể trả NULL mà chưa đặt exception.
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "NewGlobalRef failed");
        }
        return;
    }

    // Chỉ xóa đăng ký cũ SAU KHI tạo thành công newRef.
    // Demo không cho phép register/emit/unregister đồng thời.
    if (g_receiver != NULL) {
        (*env)->DeleteGlobalRef(env, g_receiver);
    }
    g_receiver = newRef;
    g_onEvent = callback;
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_emit(
        JNIEnv *env, jclass owner, jint value) {
    (void)owner;

    if (g_receiver == NULL) {
        throw_java(env, "java/lang/IllegalStateException",
                   "No receiver registered");
        return;
    }

    // Global ref còn sống dù registerReceiver đã trả về.
    (*env)->CallVoidMethod(env, g_receiver, g_onEvent, value);

    // Nếu onEvent ném Java exception, native method trả về
    // với exception pending để JVM chuyển cho Java caller.
}

JNIEXPORT void JNICALL
Java_demo_jni_GlobalReferenceDemo_unregisterReceiver(
        JNIEnv *env, jclass owner) {
    (void)owner;

    if (g_receiver != NULL) {
        (*env)->DeleteGlobalRef(env, g_receiver);
        g_receiver = NULL; // Không dùng lại handle đã xóa.
    }
    g_onEvent = NULL;
}
```

Đối chiếu từng bước:

1. `registerReceiver` nhận `receiver` là local reference. Lấy `jmethodID` cho phương thức instance `onEvent(int)` qua descriptor `"(I)V"`.
2. `NewGlobalRef` tạo **global reference độc lập**, trả về `newRef`. Chỉ khi tạo thành công mới thay thế global reference cũ. Nếu tạo thất bại, đăng ký cũ còn nguyên và Java nhận lỗi theo chính sách của ví dụ.
3. `g_receiver` được lưu trong biến C `static` qua nhiều lời gọi native. Trong `emit`, `CallVoidMethod` dùng reference này gọi `Receiver.onEvent` của Java.
4. `unregisterReceiver` xóa global reference sau khi không còn cần listener, đặt `g_receiver` và ID đi kèm về `NULL`. Hàm có thể được gọi lại mà không xóa một handle đã bị hủy.
5. `try/finally` bên Java bảo đảm giải phóng khi callback thất bại. `DeleteGlobalRef` không thay việc đóng socket/file của listener nếu listener sở hữu thêm các tài nguyên đó.

### 4.5. Biên dịch thư viện và chạy

Cài JDK (có `jni.h`) và GCC; cấu hình `JAVA_HOME` tới **JDK** tương ứng. Sau bước `javac -h`, chạy trên Linux:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libglobalrefdemo.so \
  native/globalrefdemo.c

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.GlobalReferenceDemo
```

`-Ibuild/headers` để C include header `demo_jni_GlobalReferenceDemo.h`, `-Djava.library.path=build/lib` giúp JVM nạp `libglobalrefdemo.so` tương ứng với tên logic `globalrefdemo`.

**Kết quả stdout dự kiến:**

```text
Received: 5
Received: 8
Unregistered
```

Callback hoạt động qua hai JNI calls riêng. Điều này cho thấy reference được lưu và sử dụng đúng trong ví dụ, **không chứng minh đã có chu kỳ GC**. Không dùng số lần GC hay địa chỉ bộ nhớ làm điều kiện đúng của bài.

Trên **macOS**, dùng include path `$JAVA_HOME/include/darwin` và tạo thư viện `libglobalrefdemo.dylib` bằng compiler phù hợp; trên **Windows**, dùng include path `%JAVA_HOME%\include\win32` cùng compiler tương thích để tạo `globalrefdemo.dll`. Đảm bảo kiến trúc thư viện khớp kiến trúc JVM.

## 5. Hiểu thật đúng về GC và việc giữ object sống

Strong global reference là một **GC root có hiệu lực** đối với đối tượng mà nó tham chiếu. Nếu một listener còn có đường tới các object khác, cả đồ thị object reachable qua listener cũng có thể bị giữ lâu hơn mong muốn:

```text
C global reference
    └──► Java listener
             ├──► cache
             ├──► UI view / component
             ├──► executor
             └──► class loader liên quan
```

Nếu native library liên tục đăng ký listener nhưng quên `DeleteGlobalRef`, ứng dụng có thể có **JNI global reference leak**: Java không còn sử dụng các listener, nhưng chúng vẫn reachable từ native registry. Trong hệ thống plugin/hot-reload, object/class reference bị giữ lâu còn có thể ngăn class loader được thu hồi.

Ngược lại, gọi `DeleteGlobalRef` **không bắt buộc GC chạy**. Nếu Java vẫn có strong reference khác (ví dụ một static field hay một local reference trong stack), object vẫn sống. Kể cả khi không còn root nào, GC quyết định thời điểm thu gom; không dùng `System.gc()` như chứng minh chắc chắn.

Một `jclass` là JNI reference tới class object; nếu C muốn cache class qua nhiều native calls, phải chuyển local `jclass` do `FindClass`/`GetObjectClass` trả về thành global reference hợp lệ và xóa đúng vòng đời. Những method/field IDs như `jmethodID` và `jfieldID` **không tự giữ class loaded**. Nếu class bị unload, IDs không còn bảo đảm hợp lệ.

## 6. Những lỗi ownership cần tránh

### 6.1. Tạo hai global refs thì xóa cả hai

```c
jobject first  = (*env)->NewGlobalRef(env, obj);
jobject second = (*env)->NewGlobalRef(env, obj);

// Mỗi ref tạo thành công cần DeleteGlobalRef riêng.
if (first != NULL)  (*env)->DeleteGlobalRef(env, first);
if (second != NULL) (*env)->DeleteGlobalRef(env, second);
```

Hai handle cùng trỏ tới một Java object vẫn là **hai global references cần cleanup riêng**. Xóa `first` không giải phóng `second`. Không dựa vào so sánh `first == second` để hợp nhất ownership; JNI references là opaque handles. Nếu cần so sánh danh tính Java object, dùng `IsSameObject(env, first, second)` trên **những reference còn hợp lệ**.

### 6.2. Xóa xong không được dùng lại

Sai:

```c
(*env)->DeleteGlobalRef(env, g_receiver);
// Sai: đây là handle đã bị hủy.
(*env)->CallVoidMethod(env, g_receiver, g_onEvent, (jint)42);
```

Cách bảo vệ đơn giản là đặt `g_receiver = NULL` ngay khi xóa và chặn mọi lệnh gọi về sau. Trong chương trình đa luồng, chỉ đặt `NULL` chưa đủ: một thread khác có thể đã copy handle cũ nên cần đồng bộ quanh cả quyền sử dụng lẫn thao tác xóa.

### 6.3. Không nhầm giải phóng reference với giải phóng native memory

Nếu thư viện cũng `malloc` buffer C hoặc giữ file descriptor native, các tài nguyên này phải được giải phóng bằng đúng API riêng (ví dụ `free`/`close` theo hợp đồng), không phải `DeleteGlobalRef`. Tương tự, không hy vọng JNI sẽ tự gọi `AutoCloseable.close()` trên đối tượng Java khi xóa một global reference.

### 6.4. Không giữ `JNIEnv *` qua thread

Global reference có thể được dùng trong nhiều native calls, kể cả từ một luồng native đã gắn JVM đúng cách. Nhưng `JNIEnv *` là **giao diện theo luồng**: không copy `JNIEnv *` từ thread A rồi dùng ở thread B. Thread tự tạo từ C cần `GetEnv`/`AttachCurrentThread` để lấy `JNIEnv *` riêng và `DetachCurrentThread` khi nó tự attach xong công việc.

## 7. Đa luồng: chống race giữa callback và `DeleteGlobalRef`

Ví dụ ở mục 4 **không thread-safe**: C dùng biến `static g_receiver` nhưng không có mutex. Nếu thread A đang `emit` còn thread B gọi `unregisterReceiver`, B có thể xóa global reference trước khi A dùng nó, gây **use-after-delete**. Global reference tồn tại lâu **không đồng nghĩa với việc truy cập registry an toàn giữa các thread**.

Một chiến lược đúng hơn cho hệ thống đa luồng là:

1. Bảo vệ registry (global ref và method ID của cùng listener) bằng lock/mutex.
2. Khi chuẩn bị callback, giữ lock và tạo **local snapshot** bằng `NewLocalRef(env, g_receiver)` trên luồng chuẩn bị callback; đồng thời lấy ID tương ứng. Nếu snapshot thất bại, xử lý rõ chưa đăng ký/thiếu tài nguyên.
3. **Nhả lock trước khi gọi Java** để tránh deadlock và reentrancy. Local snapshot giữ object reachable trong suốt callback, ngay cả khi thread khác đã gỡ global reference.
4. Dùng `CallVoidMethod` với snapshot, rồi `DeleteLocalRef` trên đúng luồng. Callback exception phải được xử lý hay đưa về Java caller theo hợp đồng.
5. Khi hủy, giữ cùng lock để cập nhật registry và xóa global reference. Xác định hợp đồng: callback đã bắt đầu được phép hoàn tất, hay phải đợi hết callback trước khi unregister trả về.

Phác thảo **pseudocode, không phải chương trình C độc lập** (các hàm lock và xử lý lỗi cần cài đặt):

```c
lock(registry_mutex);
jobject local = (*env)->NewLocalRef(env, g_receiver);
jmethodID id = g_onEvent;
unlock(registry_mutex);

if (local == NULL) {
    handle_missing_listener_or_allocation_error();
    return;
}

(*env)->CallVoidMethod(env, local, id, value);
(*env)->DeleteLocalRef(env, local);
```

Tất cả thao tác đăng ký, gỡ đăng ký và gọi callback phải theo **cùng quy tắc lock**. Nếu unregister dùng mutex còn callback bỏ qua, race vẫn còn. Đồng thời, không truyền `local` sang thread khác: local references chỉ hợp lệ trên thread tạo chúng.

Khi C tự tạo native worker thread để phát callback, phải attach worker tới JVM trước khi có `JNIEnv *` hợp lệ, sau đó lấy snapshot theo luồng đó. Với thread C tự attach, nên xóa local references khi không cần vì chúng có thể tồn tại đến lúc detach, khác với native frame ngắn do Java gọi vào.

## 8. Khi nào dùng weak global reference?

`NewGlobalRef` phù hợp khi native code **phải sở hữu** listener: một khi đăng ký thành công, callback còn được phép xảy ra cho tới unregister. Nhưng nếu chỉ muốn một **cache không giữ object sống**, strong global reference có thể giữ heap quá lâu. Có thể cân nhắc `NewWeakGlobalRef` và xóa bằng `DeleteWeakGlobalRef`.

Weak global reference **không ngăn GC thu gom** đối tượng đích. Vì thế không nên:

```c
// Không an toàn: object có thể bị GC sau khi kiểm tra.
if (!(*env)->IsSameObject(env, weak, NULL)) {
    // ... dùng weak ở bước sau mà không giữ strong reference ...
}
```

Để dùng an toàn, tạo **strong local reference** bằng `NewLocalRef(env, weak)`, kiểm tra `NULL`, dùng local reference hợp lệ trong thao tác, rồi `DeleteLocalRef` khi hoàn tất. Nếu trả `NULL`, object có thể đã bị thu gom hoặc có lỗi cấp phát; không tiếp tục gọi method trên `NULL`.

Đó là cách giải quyết mục tiêu **không giữ cache sống vô hạn**. Nó không thay thế trách nhiệm dọn strong global reference bằng `DeleteGlobalRef` của một registration có ownership thực sự.

## 9. Chẩn đoán rò rỉ và lỗi tham chiếu

| Biểu hiện | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Listener/Activity/class loader không được GC thu gom | Native vẫn giữ strong global reference | Kiểm kê register/unregister và global roots, gọi `DeleteGlobalRef` đúng vòng đời |
| Crash sau native method return | Giữ `jobject` local trong biến static | Tạo `NewGlobalRef` trước khi native frame kết thúc |
| Crash sau unregister | Callback dùng handle đã xóa | Ngừng dispatch, đồng bộ unregister, dùng local snapshot khi đa luồng |
| Listener vẫn sống sau `DeleteGlobalRef` | Java/GC root khác vẫn giữ object | Kiểm tra retained references; không mặc định GC ngay |
| `NewGlobalRef` trả `NULL` | Input `null`, thiếu bộ nhớ, weak ref đã mất đích | Kiểm tra input/exception, tránh ghi đè trạng thái hợp lệ |
| JNI báo dùng sai reference | Gọi `DeleteLocalRef` thay cho `DeleteGlobalRef` hoặc dùng ID như ref | Phân biệt rõ local/global/weak và member ID |
| Native worker thread gọi JNI lỗi | Dùng `JNIEnv *` của thread khác, chưa attach | Lấy `JNIEnv *` của thread hiện tại qua `GetEnv`/`AttachCurrentThread` |
| Heap tăng sau nhiều lượt đăng ký/hủy | Mỗi `NewGlobalRef` không có `DeleteGlobalRef` tương ứng | Đếm số handle còn sở hữu và kiểm thử chu kỳ teardown |
| Không tìm thấy callback method | Sai name/descriptor hoặc class loader | Đối chiếu `GetMethodID`, `"(I)V"`, class thực tế |

Khi kiểm thử, có thể chạy JVM với `-Xcheck:jni` như ví dụ. Nó giúp phát hiện một số lỗi JNI nhưng **không thay thế** kiểm tra race, native memory và retained objects. Dùng công cụ heap/GC roots để xác định liệu object còn được JNI global reference giữ sống; chú ý cả references nằm trong class loader của hệ thống plugin.

Trong ứng dụng có nhiều listener, nên thiết kế **native subscription handle** riêng cho từng đăng ký và API `close/unregister` idempotent, tránh một biến static duy nhất nếu cần nhiều subscription song song. `try/finally` hoặc `AutoCloseable` ở Java giúp thể hiện trách nhiệm teardown, nhưng phải khớp ownership mà C thực sự thực hiện.

## 10. Checklist thực hành

Trước khi đưa JNI global reference vào code dài hạn, tự kiểm tra:

1. **Nguồn hợp lệ:** `jobject` gốc còn sống tại thời điểm `NewGlobalRef` được gọi.
2. **Thất bại được xử lý:** nếu `NewGlobalRef` trả `NULL`, chương trình không lưu/call như thể thành công; không làm mất đăng ký cũ khi replace thất bại.
3. **Owner rõ ràng:** ai lưu handle, ai chịu trách nhiệm gọi `DeleteGlobalRef`, trong tình huống nào và bao nhiêu lần.
4. **Callback đúng luồng:** mỗi thread có `JNIEnv *` hợp lệ; local reference không bị chuyển sang thread khác.
5. **Hủy an toàn:** ngăn callback sử dụng handle đã xóa; đồng bộ registry và chính sách callback đang chạy.
6. **Không leak:** mỗi global reference tạo thành công được xóa; không giữ listener/class loader lâu hơn mong muốn.
7. **Không lẫn khái niệm:** xóa global reference không đồng nghĩa GC đã chạy, cũng không có nghĩa Java object được đóng hoặc bộ nhớ C được giải phóng.

## 11. Câu hỏi ôn tập

1. Vì sao `static jobject saved = listener;` có thể chạy “ổn” trong vài lần thử nhưng là thiết kế JNI sai nếu muốn dùng `saved` sau khi native method trả về?
2. `NewGlobalRef` có copy Java object hay tạo một handle JNI mới trỏ tới cùng object? Việc này ảnh hưởng GC thế nào?
3. Nếu tạo hai global references tới cùng Java listener rồi chỉ xóa một, listener có chắc đủ điều kiện để GC thu gom chưa? Giải thích.
4. Sau khi gọi `DeleteGlobalRef`, điều gì chắc chắn xảy ra với reference, điều gì **không chắc chắn** xảy ra với Java object?
5. Trong ví dụ Java/C, vì sao `emit(8)` vẫn gọi được Java `onEvent` dù `registerReceiver` đã kết thúc? Khi nào C xóa reference?
6. Nếu thread B unregister đúng lúc thread A emit, vì sao chỉ đặt `g_receiver = NULL` không đủ? Mô tả quy trình mutex và `NewLocalRef` an toàn.
7. Trong trường hợp nào nên dùng weak global reference thay vì strong global? Vì sao cần nâng weak thành local ref trước khi dùng?
8. Native thread được C tạo muốn callback Java qua global reference cần làm gì với `JavaVM` và `JNIEnv`?
9. Một native plugin giữ global `jclass` sau khi module Java được unload về mặt nghiệp vụ. Vì sao class loader có thể vẫn được giữ reachable và cần cleanup ở đâu?

**Ghi nhớ:** `NewGlobalRef` tạo **strong JNI reference tồn tại qua nhiều native calls**; `DeleteGlobalRef` chấm dứt **quyền sở hữu tham chiếu đó**. Cần ghép đúng create/delete, quản lý GC reachability, kiểm soát race khi callback và dùng `JNIEnv` đúng luồng.

### Tài liệu chính thức

- [JNI Specification JDK 21 — Design Overview: Global and Local References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [JNI Specification JDK 21 — JNI Functions: NewGlobalRef, DeleteGlobalRef, NewLocalRef, Weak Global References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [JNI Specification JDK 21 — Invocation API: AttachCurrentThread / DetachCurrentThread](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
