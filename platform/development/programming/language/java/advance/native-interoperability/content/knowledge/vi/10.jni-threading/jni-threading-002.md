# Không chia sẻ JNIEnv hoặc tham chiếu cục bộ giữa các luồng

> **Ngữ cảnh:** Java Advance → Native Interoperability → Luồng với JNI. Bài này giải thích ranh giới giữa Java thread và native thread khi dùng Java Native Interface (JNI): `JNIEnv*` thuộc luồng hiện tại, `jobject`/`jclass` dạng local reference cũng thuộc luồng và phạm vi sống của nó, còn `JavaVM*` cùng **global reference** mới là những cơ chế phù hợp khi cần giao việc cho luồng native khác.

## 1. Vấn đề cốt lõi: một JVM có nhiều luồng nhưng mỗi luồng có JNI context riêng

Khi Java gọi một phương thức `native`, JVM chuyển điều khiển sang mã C/C++ và truyền vào một con trỏ `JNIEnv*`. Con trỏ này cho phép native code gọi các hàm JNI như `FindClass`, `NewStringUTF`, `CallObjectMethod` hoặc `ExceptionCheck`.

**Quy tắc bắt buộc:** `JNIEnv*` chỉ hợp lệ với **luồng đang sở hữu nó**. Không lưu con trỏ nhận ở luồng A vào biến toàn cục rồi dùng ở luồng B. JVM có quyền gắn dữ liệu và trạng thái riêng của từng luồng vào `JNIEnv`. Cũng không được giả định pointer có thể dùng lại sau khi native thread đã `DetachCurrentThread`.

Các đối tượng Java đi qua JNI dùng **reference handle**:

- **Local reference** (`jobject`, `jstring`, `jclass`, `jarray`...): chỉ hợp lệ trong **luồng tạo ra reference** và trong **vòng đời JNI local frame**. Không chuyển nguyên local reference sang native thread khác.
- **Strong global reference:** tạo bằng `NewGlobalRef`, có thể được sử dụng từ các luồng **đã attach vào cùng JVM**, trong lúc global ref vẫn còn hiệu lực. Phải gọi `DeleteGlobalRef` đúng lúc để tránh giữ đối tượng sống quá lâu.
- **Weak global reference:** tạo bằng `NewWeakGlobalRef`; có thể mất đối tượng do GC. Muốn dùng an toàn, trước tiên nâng lên strong local/global reference bằng `NewLocalRef`/`NewGlobalRef` và kiểm tra `NULL`.
- **`JavaVM*`:** đại diện một JVM, dùng được từ các native thread khác nhau để gọi `GetEnv`, `AttachCurrentThread`, `DetachCurrentThread`. Nó **không** thay thế `JNIEnv*` khi gọi các hàm xử lý Java object.

### Sơ đồ đúng và sai

```text
LUỒNG JAVA A                 LUỒNG NATIVE B

JNIEnv *envA   --X--------->  dùng envA: SAI, envA thuộc A
jobject localA --X--------->  dùng localA: SAI, handle local thuộc A

JavaVM *vm     ------------>  AttachCurrentThread(vm, &envB)
                                  |
                                  v
                              JNIEnv *envB của B

NewGlobalRef(envA, localA)
       |
       +---- globalRef ----->  dùng globalRef qua envB: ĐÚNG
                                  |
                                  v
                              DetachCurrentThread(vm)

Luồng A: sau khi B không còn dùng globalRef,
         DeleteGlobalRef(envA, globalRef)
```

**Chia sẻ global reference không đồng nghĩa với thread-safe object.** Reference chỉ giải quyết **khả năng truy cập và giữ đối tượng không bị GC thu hồi**. Nếu đối tượng Java có trạng thái có thể thay đổi, Java Memory Model, `synchronized`, lock, atomic types hoặc message passing vẫn cần được áp dụng.

## 2. Bảng phân loại thứ gì được chuyển qua luồng khác

| Thành phần JNI | Có dùng trực tiếp ở native thread khác? | Lý do và hướng đúng |
|---|---|---|
| `JNIEnv *envA` | **Không** | Gắn với luồng A; tại B lấy `JNIEnv *envB` qua `AttachCurrentThread` hoặc `GetEnv` nếu B đã attach |
| `JavaVM *vm` | **Có** | Handle cấp JVM; dùng để attach/detach/getEnv theo luồng |
| `jobject localRef`, `jstring`, `jclass` dạng local | **Không** | Chỉ hợp lệ trong luồng/local frame của nó; tạo `NewGlobalRef` khi cần chuyển việc |
| `jobject globalRef` (strong) | **Có**, nếu còn sống | B phải attach và sử dụng cùng `JNIEnv*` riêng của B; chủ sở hữu phải xóa global ref khi không còn cần |
| `jweak weakRef` | Có điều kiện | GC có thể thu hồi đối tượng; tạo strong local/global mới và kiểm tra kết quả trước khi dùng |
| `jmethodID`, `jfieldID` | Có thể cache/chia sẻ khi hợp lệ | Chúng là ID mờ, **không phải** `jobject` và không phải local ref; gắn với vòng đời class/class loader |
| Pointer từ `GetStringUTFChars` hoặc `GetByteArrayElements` | Theo hợp đồng lease riêng, không phải `jobject` | Tuân thủ release/pinning/ownership; đừng coi pointer C là local/global Java reference; tránh dùng sai vòng đời |
| Giá trị C thuần như `int`, bản sao byte buffer | Có nếu đồng bộ đúng | Không cần JNI reference, nhưng vẫn phải quản lý memory và data race C/C++ |

**Bẫy tên kiểu:** `jobject` không tự cho biết nó là **local**, **global** hay **weak global**. Cả ba có thể cùng kiểu C nhưng **khác quy tắc vòng đời**. Lấy `GetObjectClass` trả về một `jclass` **local**, không phải global, dù `jclass` trông giống "metadata dùng chung".

## 3. Vòng đời của JNIEnv, JavaVM và attachment

Có hai tình huống khác nhau.

### Trường hợp A — luồng do Java tạo

Khi `new Thread(...).start()` chạy Java code rồi vào một phương thức `native`, JVM **đã attach luồng đó** và truyền `JNIEnv*` hợp lệ vào native method. Một luồng Java khác gọi cùng native method sẽ nhận JNI environment của **chính nó**.

```c
// Đoạn minh họa. Mỗi lần Java gọi native method,
// JVM cung cấp env hợp lệ cho thread đang thực hiện.
JNIEXPORT void JNICALL Java_Example_nativeWork(
        JNIEnv *env, jobject thiz) {
    // Chỉ dùng env/thiz trong thread và JNI local frame này.
}
```

Khi callback native kết thúc, JVM xử lý local frame của lần gọi đó. **Không tự `DetachCurrentThread` ngay bên trong native method do Java gọi**: luồng còn Java frames trên call stack và cơ chế attach thuộc JVM.

### Trường hợp B — luồng tự tạo bằng pthread/std::thread

Một `pthread` do native code tạo **chưa tự động attach vào JVM**. Muốn gọi JNI từ luồng đó:

1. Có `JavaVM*` hợp lệ. Từ native entrypoint đã attach, gọi `(*env)->GetJavaVM(env, &vm)`; hoặc trong mã thư viện nhận JavaVM khi `JNI_OnLoad` được gọi.
2. Trong **chính native thread mới**, gọi `(*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6)` để kiểm tra. Nếu `JNI_EDETACHED`, gọi `AttachCurrentThread` để lấy `JNIEnv*` của luồng đó.
3. Dùng **env vừa nhận trong luồng hiện tại** để thao tác Java objects; chỉ dùng những JNI references hợp lệ trên luồng này (local do nó tạo hoặc global còn sống).
4. Release local refs/bộ nhớ/lock, xử lý pending Java exceptions.
5. Nếu chính native thread đã attach, gọi `DetachCurrentThread` **trước khi thread kết thúc**, khi không còn Java methods trên call stack.

C API:

```c
// Trích đoạn minh họa bên trong một native thread.
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (rc == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(vm, (void **)&env, NULL) != JNI_OK) {
        // Không có JNIEnv hợp lệ; không gọi JNI.
        return;
    }
    // Thread này có trách nhiệm DetachCurrentThread trước khi thoát.
} else if (rc != JNI_OK) {
    // JNI_EVERSION hoặc lỗi khác: không sử dụng env.
    return;
}

// Chỉ dùng env ngay trên thread đang chạy.
// Chỉ Detach nếu thread này đã thực sự attach ở nhánh trên.
```

Đoạn trên cố ý **không phải chương trình C độc lập**, minh họa `GetEnv`/`AttachCurrentThread`. Khi một thread đã attach sẵn, gọi lại `AttachCurrentThread` sẽ lấy lại environment hiện có và **không** thay đổi daemon status. `AttachCurrentThreadAsDaemon` tạo daemon thread nếu mới attach; lựa chọn này ảnh hưởng vòng đời JVM, **không** miễn nghĩa vụ dọn tài nguyên/detach đúng quy trình.

### Cặp điều kiện quan trọng

- `JNI_OK`: có thể sử dụng `JNIEnv*` trả về của **luồng hiện tại**.
- `JNI_EDETACHED`: luồng chưa attach, cần attach nếu muốn gọi JNI.
- `JNI_EVERSION`: requested JNI version không được hỗ trợ; đừng tiếp tục như thể env hợp lệ.
- `DetachCurrentThread` không phải "xóa Java object": nó kết thúc attachment và làm local references của luồng mất hiệu lực. Global refs còn sống đến khi bị delete.
- Một native thread attach dưới dạng **non-daemon** có thể giữ JVM chưa kết thúc; quản lý startup/shutdown cẩn thận.

## 4. Hai phản ví dụ: đoạn code không được chạy

### Sai 1 — lưu JNIEnv vào biến global

```c
// ANTI-PATTERN: KHÔNG CHẠY.
static JNIEnv *cachedEnv;

JNIEXPORT void JNICALL Java_Bad_setEnv(JNIEnv *env, jclass cls) {
    cachedEnv = env;
}

// Trong một pthread khác:
jclass c = (*cachedEnv)->FindClass(cachedEnv, "java/lang/String");
// SAI: cachedEnv thuộc thread gọi setEnv, không thuộc pthread hiện tại.
```

Sửa bằng cách lưu/chuyển **`JavaVM*`**, sau đó lấy `JNIEnv*` hợp lệ trên từng thread qua Invocation API. Dù pointer số học có vẻ giống nhau giữa hai lần chạy, không thể dựa vào việc so sánh địa chỉ để phá quy tắc thread confinement.

### Sai 2 — chuyển local reference thẳng qua hàng đợi

```c
// ANTI-PATTERN: KHÔNG CHẠY.
static jobject saved;

JNIEXPORT void JNICALL Java_Bad_enqueue(JNIEnv *env, jclass cls, jobject obj) {
    saved = obj; // obj là local ref do JNI call này nhận.
}

// Thread khác:
// (*workerEnv)->CallVoidMethod(workerEnv, saved, callbackId);
// SAI: saved được tạo ở thread khác và có thể hết hạn khi native call trả về.
```

**Sửa:** ngay tại thread sở hữu local reference, tạo `jobject shared = (*env)->NewGlobalRef(env, obj)`; chuyển **shared** cho worker và chuyển quyền sở hữu rõ ràng; worker phải attach vào JVM trước khi gọi JNI. Chỉ `DeleteGlobalRef` khi mọi worker đã ngừng dùng shared. Không xóa global ref ngay sau khi đưa vào queue, vì điều đó tạo use-after-delete trong worker.

## 5. Ví dụ hoàn chỉnh: chuyển String qua pthread một cách hợp lệ

Ví dụ chạy trên **Java 17+, Linux với GCC và pthreads**. Java tạo **hai caller threads**; mỗi caller vào JNI và yêu cầu một `pthread` native đọc `String.length()`. Native method:

- Nhận `JNIEnv*` và local `jstring` trên caller.
- Gọi `GetJavaVM` để lấy VM-level handle.
- Gọi `NewGlobalRef` **trước khi tạo pthread** để đối tượng sống qua ranh giới luồng.
- Worker gọi `AttachCurrentThread` và dùng **env của chính worker**.
- Worker gọi phương thức Java `String.length()` thông qua global reference; dọn class local reference; detach.
- Caller `pthread_join` để chờ worker hoàn thành, rồi `DeleteGlobalRef`.
- Hai caller dùng **hai cấu trúc task riêng**; không chia sẻ biến trạng thái native toàn cục.

### 5.1. Tệp `JniThreadDemo.java`

```java
public final class JniThreadDemo {
    static {
        System.loadLibrary("jnithreads");
    }

    private static native int lengthOnNativeThread(String value);

    public static void main(String[] args) throws InterruptedException {
        String[] output = new String[2];

        Thread callerA = new Thread(
                () -> output[0] = "A = " + lengthOnNativeThread("Lan"),
                "caller-A");
        Thread callerB = new Thread(
                () -> output[1] = "B = " + lengthOnNativeThread("JNI"),
                "caller-B");

        callerA.start();
        callerB.start();

        callerA.join();
        callerB.join();

        // In sau join để kết quả ổn định, bất kể lịch chạy thread.
        System.out.println(output[0]);
        System.out.println(output[1]);
    }
}
```

`String` được dùng làm dữ liệu bất biến trong bài, nên không phát sinh vấn đề cạnh tranh cập nhật nội dung. Hai phần tử khác nhau của `output[]` được ghi bởi hai caller; các lệnh `join()` khiến main quan sát các cập nhật trước khi in. Nếu JNI ném exception từ một caller thread mà không tự bắt, exception sẽ do uncaught exception handler xử lý; ví dụ bình thường giả định build thành công và các JNI operations không lỗi.

### 5.2. Sinh JNI header

```bash
javac -encoding UTF-8 -h . JniThreadDemo.java
```

Lệnh tạo `JniThreadDemo.class` và `JniThreadDemo.h`. Dùng header compiler sinh để tránh sai tên symbol `Java_JniThreadDemo_lengthOnNativeThread` hoặc chữ ký tham số.

### 5.3. Tệp `JniThreadDemo.c`

```c
#include <jni.h>
#include <pthread.h>
#include "JniThreadDemo.h"

typedef struct {
    JavaVM *vm;
    jobject valueGlobal;  // Strong global JNI reference.
    jint length;
    int error;
} Task;

static void throwState(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *nativeWorker(void *arg) {
    Task *task = (Task *) arg;
    JNIEnv *env = NULL;  // Độc lập với JNIEnv của caller.

    if ((*task->vm)->AttachCurrentThread(
            task->vm, (void **) &env, NULL) != JNI_OK) {
        task->error = 1;
        return NULL;
    }

    jclass stringClass = (*env)->GetObjectClass(
            env, task->valueGlobal);
    if (stringClass == NULL || (*env)->ExceptionCheck(env)) {
        task->error = 2;
        goto cleanup;
    }

    jmethodID lengthId = (*env)->GetMethodID(
            env, stringClass, "length", "()I");
    if (lengthId == NULL || (*env)->ExceptionCheck(env)) {
        task->error = 3;
        goto cleanup;
    }

    // Java String.length() trả số UTF-16 code units.
    task->length = (*env)->CallIntMethod(
            env, task->valueGlobal, lengthId);
    if ((*env)->ExceptionCheck(env)) {
        task->error = 4;
    }

cleanup:
    // Exception đang pending trên worker không tự truyền sang caller.
    // Trong ví dụ, in chẩn đoán, xóa pending exception,
    // rồi báo lỗi bằng task->error.
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
    if (stringClass != NULL) {
        (*env)->DeleteLocalRef(env, stringClass);
    }
    if ((*task->vm)->DetachCurrentThread(task->vm) != JNI_OK) {
        task->error = 5;
    }
    return NULL;
}

JNIEXPORT jint JNICALL Java_JniThreadDemo_lengthOnNativeThread(
        JNIEnv *env, jclass owner, jstring value) {
    (void) owner;

    if (value == NULL) {
        throwState(env, "value must not be null");
        return 0;
    }

    // Task nằm trên stack của caller và sống đến sau pthread_join.
    Task task = {0};
    if ((*env)->GetJavaVM(env, &task.vm) != JNI_OK) {
        throwState(env, "GetJavaVM failed");
        return 0;
    }

    // Phải tạo strong global ref TRƯỚC khi chuyển sang thread khác.
    task.valueGlobal = (*env)->NewGlobalRef(env, value);
    if (task.valueGlobal == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throwState(env, "NewGlobalRef failed");
        }
        return 0;
    }

    pthread_t thread;
    if (pthread_create(&thread, NULL, nativeWorker, &task) != 0) {
        (*env)->DeleteGlobalRef(env, task.valueGlobal);
        throwState(env, "pthread_create failed");
        return 0;
    }

    // Ví dụ có một pthread joinable hợp lệ và đúng một chỗ join.
    if (pthread_join(thread, NULL) != 0) {
        // Không an toàn để bỏ Task trên stack khi worker có thể còn chạy.
        (*env)->FatalError(env, "pthread_join failed");
        return 0; // Không tới đây: FatalError chấm dứt JVM.
    }

    // Worker đã dừng sử dụng global ref: caller có thể xóa nó.
    (*env)->DeleteGlobalRef(env, task.valueGlobal);

    if (task.error != 0) {
        throwState(env, "Native worker failed");
        return 0;
    }
    return task.length;
}
```

**Phần nào làm ví dụ an toàn về reference?**

1. `value` là local `jstring` thuộc caller JNI thread. Không đưa `value` vào `Task` chuyển cho worker.
2. `NewGlobalRef` được gọi trên caller bằng **env của caller**; `task.valueGlobal` sau đó mới đưa qua `pthread_create`.
3. `JavaVM*` là handle thích hợp để worker attach. `nativeWorker` tạo biến `JNIEnv *env` **mới trên stack riêng**, nhận environment của worker từ `AttachCurrentThread`.
4. Worker dùng `task.valueGlobal` qua env của nó, nhưng `stringClass` nhận từ `GetObjectClass` lại là **local reference của worker**. Worker `DeleteLocalRef` trước khi detach; không gửi `stringClass` lại caller.
5. `pthread_join` chờ thread hoàn thành nên các kết quả `task.length` và `task.error` đã sẵn sàng, đồng thời caller biết thời điểm được phép `DeleteGlobalRef`.
6. `Task` ở stack chỉ an toàn vì code **luôn đợi thread hoàn thành**. Nếu chuyển sang xử lý bất đồng bộ mà native method trả về ngay, phải cấp phát task với lifetime riêng và xác định nơi giải phóng; không đưa địa chỉ biến stack ra ngoài hàm.

Trong bản demo, nếu bất ngờ thất bại tại `pthread_join`, code dùng `FatalError` để ngăn trường hợp trả về rồi xóa stack khi worker vẫn có thể chạy. Đây là chính sách **fail-fast cho invariant không thể phục hồi trong ví dụ đồng bộ**; ứng dụng thực cần quản lý thread/task lifetime và shutdown chắc chắn, không dựa vào abort để xử lý lỗi thường gặp.

**Về exception:** một Java exception xuất hiện khi worker `CallIntMethod` là **pending trên worker thread**, không tự chuyển qua caller Java thread. Ví dụ ghi chẩn đoán rồi xóa exception ở worker, lưu `task.error` và caller ném `IllegalStateException` sau khi join. Ứng dụng cần giữ thông tin nguyên nhân có thể tạo một **global reference đến Throwable** ở worker, sau đó chuyển nó thành local ref/throw trên caller và dọn global ref, với quy trình ownership và locking chặt chẽ; không được đưa local exception ref thẳng sang caller.

### 5.4. Biên dịch thư viện và chạy

Giả sử `JAVA_HOME` trỏ tới JDK 17+ và GCC có sẵn:

```bash
gcc -std=c11 -fPIC -pthread -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnithreads.so JniThreadDemo.c

java -Djava.library.path=. JniThreadDemo
```

Với JDK 24+ trên classpath, nên cấp quyền JNI native access tường minh:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniThreadDemo
```

**stdout khi chạy thành công:**

```text
A = 3
B = 3
```

Output được in trên main sau hai lần `join()` của Java nên thứ tự **cố định**, dù hai caller và hai native workers có thể được scheduler chạy theo thứ tự khác nhau. Khi build trên macOS hoặc Windows, phải điều chỉnh thư viện `.dylib`/`.dll`, JNI platform headers, pthread/cơ chế tạo thread phù hợp hệ điều hành và linker flags; lệnh GCC trên đây dành riêng cho Linux.

## 6. Vì sao local reference là ranh giới thread *và* frame?

Local JNI reference là handle do JVM cấp, được quản lý qua một bảng/lifetime của luồng hiện tại. Thông thường:

- Tham số Java object được truyền vào native method là local references của lần gọi đó.
- JNI APIs như `FindClass`, `NewStringUTF`, `GetObjectClass`, `GetObjectArrayElement` trả các local references mới.
- Khi native method **trả về Java**, các local references của frame đó được tự động giải phóng.
- Trong cùng một native method, `DeleteLocalRef` cho phép dọn reference sớm; `PushLocalFrame`/`PopLocalFrame` tổ chức scope khi tạo nhiều references.
- Khi **native-created thread** đã attach và xử lý công việc lâu mà không có chu kỳ return-to-Java như native entrypoint thông thường, phải **chủ động dọn local references** (hoặc dùng local frames), vì chúng có thể tồn tại cho đến lúc detach.

Cần phân biệt **đối tượng Java** với **JNI handle**. Một đối tượng Java có thể được nhiều Java thread cùng sử dụng theo Java Memory Model, nhưng local JNI reference biểu thị đối tượng đó vẫn chỉ hợp lệ ở luồng/frame tạo ra handle. Java reference có thể được truyền qua cơ chế Java đồng bộ chuẩn, trong khi native code cần tạo JNI global reference nếu phải giữ object vượt khỏi thread/frame gốc.

### `PushLocalFrame`/`PopLocalFrame` cho worker chạy vòng lặp

```c
// Trích đoạn minh họa nằm bên trong native thread ĐÃ ATTACH.
// env và inputArray hợp lệ trong thread hiện tại.
for (jsize i = 0; i < count; ++i) {
    if ((*env)->PushLocalFrame(env, 16) != JNI_OK) {
        // Thường có OutOfMemoryError pending: dừng và xử lý lỗi.
        break;
    }

    jobject element = (*env)->GetObjectArrayElement(env, inputArray, i);
    if ((*env)->ExceptionCheck(env)) {
        (*env)->PopLocalFrame(env, NULL);
        break;
    }

    // Xử lý element bằng env của thread này.
    // KHÔNG gửi element (local) sang thread khác.

    (*env)->PopLocalFrame(env, NULL);
    // Các local references sinh bên trong frame vừa bị dọn.
}
```

Đoạn này không phải tệp C độc lập; giả định `count`/`inputArray` đã tồn tại và mọi JNI usage xảy ra trên thread hiện tại. `PopLocalFrame(env, NULL)` hủy local refs trong frame. Nếu một local reference cần sống sau `PopLocalFrame` **trong cùng thread**, có thể trả nó qua tham số `result` của `PopLocalFrame`; cơ chế đó **không** biến reference thành cross-thread global reference.

Đừng dùng `DeleteLocalRef` cho global ref hoặc `DeleteGlobalRef` cho local ref. Giữ đúng cặp New/Delete trong từng ownership path.

## 7. Ownership toàn cục và an toàn khi xử lý bất đồng bộ

Ví dụ mục 5 đợi worker bằng `pthread_join`, nên thời điểm xóa global ref rõ ràng. Trong hệ thống event loop, native thread pool hoặc SDK callback chạy bất đồng bộ, thường phải quản lý ba loại lifetime độc lập:

1. **Object JNI lifetime:** tạo `NewGlobalRef` khi queue nhận task, chuyển quyền sở hữu cho task, xóa `DeleteGlobalRef` khi task hoàn tất hoặc bị hủy an toàn.
2. **Native task lifetime:** vùng nhớ C/C++ chứa task, buffer và callback handle phải sống cho đến khi **không native worker nào còn dùng**; chỉ `free` sau một synchronization point.
3. **Thread attachment lifetime:** mỗi native worker attach một lần khi bắt đầu cần JNI; dùng env của riêng mình; detach khi thread dừng và không còn Java frames.

Ví dụ kiến trúc:

```text
Java caller
  -> JNI submit(envCaller, objLocal)
       -> NewGlobalRef(envCaller, objLocal) = objGlobal
       -> queue.push(Task{JavaVM*, objGlobal, ...})
       -> trả về Java
                         |
                         v
                 Native worker thread
                    GetEnv/AttachCurrentThread -> envWorker
                    dùng objGlobal với envWorker
                    xử lý result / callback
                    DeleteGlobalRef(envWorker, objGlobal) khi task hoàn tất
                    DetachCurrentThread khi worker kết thúc
```

Nếu caller huỷ task khi worker đang xử lý, **không xóa global ref trước khi worker ngừng truy cập**. Dùng mutex/condition variable/atomics/reference counting phù hợp ở native layer, cùng hợp đồng cancellation idempotent và cleanup khi shutdown. `NewGlobalRef` chỉ giữ đối tượng sống; nó **không** cấp phát khóa và không chặn mutation cạnh tranh. Trong C/C++ không được đọc/ghi task fields từ nhiều threads mà thiếu đồng bộ.

### Weak global reference

Weak global reference phù hợp cho cache không bắt buộc giữ object sống, nhưng GC có thể xóa đối tượng bất cứ lúc nào. Thao tác kiểm tra rồi dùng weak ref trực tiếp có thể tạo race với GC. Trong worker đã attach, gọi:

```c
// Trích đoạn minh họa; weakRef là weak global reference còn được quản lý.
jobject strongLocal = (*env)->NewLocalRef(env, weakRef);
if (strongLocal != NULL) {
    // Object sống và được giữ mạnh trong phạm vi local ref này.
    // Sử dụng strongLocal trên CHÍNH thread hiện tại.
    (*env)->DeleteLocalRef(env, strongLocal);
} else {
    // Có thể object đã bị GC thu hồi (hoặc lỗi tạo ref).
    // Kiểm tra pending exception khi cần phân biệt lỗi.
}
```

Nếu worker cần giữ object qua nhiều thread, tạo strong **global** ref từ weak ref đang còn sống, tuân thủ ownership của `NewGlobalRef`. Không cache kết quả `IsSameObject(weakRef, NULL)` rồi dùng weak reference sau đó: trạng thái có thể thay đổi giữa kiểm tra và sử dụng.

## 8. Các lỗi tinh vi ngoài chuyện JNI handle

### 8.1. Global ref không làm mutable Java object thread-safe

Giả sử native workers giữ global ref đến cùng một `ArrayList` rồi gọi `add` đồng thời. Dù ref hợp lệ ở mỗi thread, `ArrayList` không tự bảo vệ trước mutation đồng thời. Ứng dụng vẫn cần đồng bộ theo Java contract, hoặc chọn collection concurrent/immutable phù hợp. Cũng cần xét visibility/happens-before nếu native code ghi bộ nhớ dùng chung với Java.

**Định nghĩa đúng:** Global reference giải quyết **GC reachability và tham chiếu hợp lệ**; lock giải quyết **đồng bộ truy cập dữ liệu**. Hai trách nhiệm độc lập.

### 8.2. Class loader khi native thread tự attach

`FindClass` trong native method có thể dùng class loader gắn với lớp khai báo native method. Nhưng native thread tự attach **không có Java caller** cho việc suy ra loader theo cách thông thường; mặc định context class loader của attached native thread là **bootstrap loader**. Vì vậy `FindClass(envWorker, "com/example/Plugin")` có thể thất bại dù class plugin tồn tại dưới custom class loader.

Cách an toàn khi cần gọi một class ứng dụng: lấy `jclass` trên Java caller có đúng loader, **tạo global ref** cho nó, trao cho worker, rồi worker dùng `GetMethodID` trên global class reference. Hoặc truyền một class loader/entrypoint có lifecycle được quản lý rõ. Không chia sẻ trực tiếp `jclass` local lấy từ `FindClass` trên caller.

### 8.3. Cached `jmethodID` không phải global reference

`jmethodID`/`jfieldID` là ID mờ, không phải `jobject`, và không dùng `NewGlobalRef` cho ID. Có thể cache khi class còn loaded nhưng cần hiểu lifecycle class loader: unload/reload có thể khiến ID cũ không hợp lệ. Nếu cache class kèm method ID, class reference cần global/weak global theo mục đích và cleanup đúng.

### 8.4. Exception là trạng thái của thread

Nếu worker gọi Java method khiến exception pending, exception đó không tự "nhảy" về thread Java caller đang `pthread_join`. Worker phải xử lý/dịch nghĩa hoặc chuyển Throwable bằng một **global reference** theo hợp đồng, rồi xóa nó. Đừng chuyển trực tiếp local `jthrowable` sang thread khác. Đừng giữ pending exception rồi gọi hàng loạt JNI functions không được phép trong trạng thái đó.

### 8.5. Daemon attachment và JVM shutdown

Native worker attach bằng `AttachCurrentThread` là **non-daemon** theo API; nếu không detach, nó có thể khiến JVM chưa shutdown. `AttachCurrentThreadAsDaemon` không giữ JVM sống giống non-daemon thread, nhưng daemon không có nghĩa tài nguyên sẽ tự dọn: khi JVM chấm dứt, công việc native có thể bị gián đoạn. Phải thiết kế graceful shutdown, stop queue, join workers, release globals trước khi thoát nếu cần tính toàn vẹn.

### 8.6. JNI trên Java virtual threads

Từ các JDK có virtual threads, call JNI và việc dùng native thread-affine state càng cần chú ý ngữ cảnh scheduler và lifecycle. Không cache `JNIEnv*` dựa vào tên thread, tên task hay Java logical thread ID. Cách chính xác vẫn là dùng **env được cung cấp tại JNI entrypoint** hoặc lấy env sau attachment trên native thread đang gọi JNI, cùng quy tắc reference ownership. Khi cần tương tác dài hạn với callback native, cân nhắc platform threads và kiểm tra hướng dẫn JDK phù hợp phiên bản đang triển khai.

## 9. Checklist trước khi chạy native worker

| Câu hỏi phải trả lời | Nếu không đạt |
|---|---|
| Worker lấy `JNIEnv*` **trên chính thread của nó**? | Không gọi JNI; attach/getEnv đúng thread |
| Có lỡ lưu `JNIEnv*` của caller vào static/queue? | Bỏ lưu, chỉ giữ `JavaVM*` |
| Object được chuyển ra ngoài native frame bằng **strong global ref**? | `NewGlobalRef` trước khi queue/start worker |
| Có nơi duy nhất sở hữu lệnh `DeleteGlobalRef`? | Thiết kế ownership, tránh double delete/leak |
| Global ref còn sống trong **toàn bộ** thời gian worker dùng? | Thêm synchronization/finish acknowledgement |
| Worker đã attach và sẽ detach đúng lúc? | Cần lifecycle quản lý và cleanup trên mọi nhánh |
| Worker tạo nhiều local refs trong vòng lặp? | `DeleteLocalRef` hoặc local frame để tránh tích tụ |
| Dữ liệu mutable được bảo vệ bởi synchronization thích hợp? | Global ref không giải quyết data race |
| Worker callback vào class ứng dụng qua class loader phù hợp? | Đưa global `jclass`/loader từ Java caller |
| Có xử lý pending exception và JNI error codes? | Tránh dùng kết quả không hợp lệ hoặc treo/error âm thầm |
| Nhiều caller có dùng chung task buffer/biến lỗi? | Mỗi request có state riêng hoặc shared state được lock |
| JNI native access được cấp theo JDK/version? | Dùng cấu hình access chính xác, test trên JVM mục tiêu |

Khi debug, chạy với `-Xcheck:jni` có thể phát hiện một số lỗi sử dụng JNI, như sai reference/thread usage. Nó không thể chứng minh toàn bộ C/C++ memory safety hoặc thay thế race detector/AddressSanitizer/ThreadSanitizer cho phần native. Bắt đầu với ví dụ có kết quả và cleanup rõ ràng, rồi mới chuyển sang thread pool bất đồng bộ.

## 10. Các lỗi phổ biến và hậu quả

| Sai lầm | Hậu quả có thể | Cách sửa |
|---|---|---|
| Dùng `JNIEnv*` từ thread A trên thread B | Crash, lỗi JNI hoặc undefined behavior | `GetEnv`/`AttachCurrentThread` trên B |
| Lưu `jobject` local sau khi JNI function trả về | Handle hết hạn, crash hoặc dữ liệu rác | `NewGlobalRef` trước khi caller frame kết thúc |
| Dùng local `jclass` từ caller trong pthread | Vi phạm thread-local reference | Tạo global class ref hoặc lookup hợp lệ ở B |
| Xóa global ref ngay sau khi enqueue | Worker có thể truy cập ref đã bị xóa | Chuyển ownership sang task; xóa sau completion/cancel an toàn |
| Không `DeleteGlobalRef` | Giữ object sống, native/JVM memory leak | Dọn global trên completion và shutdown |
| Quên `DetachCurrentThread` ở native worker | Thread resources không được dọn, JVM có thể khó shutdown | Detach thread do native tạo sau khi hoàn thành |
| Detach một Java thread trong native callback | Không hợp lệ nếu Java frames còn trên stack | JVM quản lý Java-created thread attachment |
| Native-created thread tích lũy local refs lâu | Local reference table tăng, hết tài nguyên | `DeleteLocalRef` / `PushLocalFrame` |
| Dùng global ref để chia sẻ `HashMap` mutable không lock | Data race hoặc hỏng trạng thái | Áp dụng Java/thread synchronization |
| `FindClass` trên attached worker không thấy class của app | Class loader context khác | Pass global `jclass`/class loader từ caller |
| Callback ném Java exception nhưng caller không biết | Trạng thái lỗi bị bỏ qua | Xử lý trên worker; chuyển Throwable thông qua global ref khi cần |
| Gọi `pthread_join` trong khi giữ lock mà worker cần | Deadlock | Thiết kế thứ tự lock, callback, join và timeout |

## 11. Bài tập tự kiểm tra

**Bài 1 — nhận diện sai phạm.** Một JNI method nhận `jstring name` rồi lưu `name` vào global C variable; một `pthread` khác attach và gọi `GetStringLength(envWorker, savedName)`. Có an toàn không?

**Đáp án:** **Không.** Dù worker có env đúng thread, `savedName` là local reference của caller. Phải tạo `NewGlobalRef(envCaller, name)` trước khi rời caller frame/chuyển công việc; xóa global sau khi worker dùng xong.

**Bài 2 — sửa cách lấy env.** Worker tạo bằng `pthread_create` đang giữ `JNIEnv* envCaller` từ một native callback trước đó. Nó gọi `CallVoidMethod(envCaller, ...)`. Sửa thế nào?

**Đáp án:** Giữ `JavaVM*`, trong worker dùng `GetEnv` và `AttachCurrentThread` nếu chưa attach, nhận `envWorker`; chỉ gọi JNI qua envWorker. Detach trước khi worker kết thúc nếu worker đã attach.

**Bài 3 — global ref và đồng bộ.** Hai workers đều có strong global ref hợp lệ đến cùng một mutable `ArrayList`; cả hai gọi `add` đồng thời. Reference hợp lệ có bảo đảm dữ liệu đúng không?

**Đáp án:** **Không.** Cần synchronization phù hợp hoặc chọn cấu trúc concurrent. JNI global ref quản lý reachability, không quản lý tính nhất quán của object state.

**Bài 4 — vòng đời.** Worker kết thúc, caller đã `pthread_join` thành công. Caller có thể `DeleteGlobalRef` rồi trả khỏi native method không?

**Đáp án:** **Có**, nếu không còn bất kỳ worker/task nào khác giữ quyền sử dụng global ref đó, và không còn callback bất đồng bộ đang chạy. Join tạo điểm đồng bộ chứng minh worker này đã ngừng.

**Bài 5 — class loader.** Pthread đã attach không tìm thấy `com/example/MyPlugin` bằng `FindClass`, dù class có trên application classpath và được nạp qua custom loader. Khả năng nào cần kiểm tra?

**Đáp án:** Worker không có Java caller/class loader context mong muốn; attached thread context loader mặc định có thể là bootstrap loader. Chuyển một global `jclass` hợp lệ hoặc class loader từ Java caller, quản lý đúng lifetime.

**Bài 6 — local reference management.** Một worker attach một lần, chạy 1 triệu vòng, mỗi vòng gọi `NewStringUTF` nhưng không xóa local reference. Việc detach khi thread kết thúc có đủ tốt không?

**Đáp án:** **Không.** Trong suốt vòng lặp local refs tích tụ và có thể làm hết tài nguyên trước khi detach. Dùng `DeleteLocalRef` mỗi vòng hoặc `PushLocalFrame`/`PopLocalFrame`.

## 12. Ghi nhớ và tài liệu chuẩn

Ba nguyên tắc nên thuộc lòng:

1. **`JNIEnv*` theo luồng:** mỗi thread gọi JNI cần environment riêng nhận trên thread đó; không chuyển con trỏ `JNIEnv*` cho thread khác.
2. **Local reference theo luồng/frame:** không đưa local `jobject`/`jclass` sang thread khác hoặc giữ sau khi frame kết thúc; chuyển công việc dùng **global ref**, có ownership và cleanup xác định.
3. **`JavaVM*` + attach/detach:** chính là con đường hợp lệ để native thread tương tác với JVM. Có global ref hợp lệ vẫn phải bảo đảm object thread safety và đồng bộ native data.

**Tài liệu gốc:**

- [Oracle JNI Specification — Design Overview: JNI Interface Pointers, Local and Global References](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [Oracle JNI Specification — The Invocation API: AttachCurrentThread, GetEnv, DetachCurrentThread](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html)
- [Oracle JNI Specification — JNI Functions: NewGlobalRef, DeleteGlobalRef, NewLocalRef, DeleteLocalRef, PushLocalFrame](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [Android NDK — JNI Tips: Threads và quản lý local references khi native thread attach](https://developer.android.com/ndk/guides/jni-tips)
- [Java Language Specification — Threads and Locks / Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html)
- [JEP 472 — Prepare to Restrict the Use of JNI (JDK 24)](https://openjdk.org/jeps/472)
