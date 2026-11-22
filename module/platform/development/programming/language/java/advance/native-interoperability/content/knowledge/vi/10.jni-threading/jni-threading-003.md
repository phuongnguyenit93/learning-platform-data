# Lấy JavaVM bằng GetJavaVM và kiểm tra trạng thái luồng bằng GetEnv

## 1. Bài toán: từ một native method, muốn biết thread hiện tại đã gắn với JVM chưa

Trong **JNI (Java Native Interface)**, một hàm C được Java gọi sẽ nhận `JNIEnv *env`. Con trỏ này giúp thread **đang gọi** thực hiện các thao tác JNI, nhưng **không phải vé truy cập JVM dùng chung giữa các thread**. Khi thư viện C tự sinh một thread bằng `pthread_create` hay `CreateThread`, thread đó không tự nhiên có một `JNIEnv *` hợp lệ. Muốn gọi Java hoặc thao tác với đối tượng Java trên thread ấy, native code phải biết **JavaVM** nào cần làm việc và trạng thái attach của **chính thread hiện tại**.

Hai API giải quyết hai câu hỏi khác nhau:

- **`GetJavaVM`**: từ `JNIEnv *` hợp lệ của một native method đang chạy, lấy `JavaVM *` đại diện JVM liên quan. `JavaVM *` dùng cho **Invocation API** (trong đó có `GetEnv`, `AttachCurrentThread` và `DetachCurrentThread`).
- **`GetEnv`**: hỏi `JavaVM *` xem **thread gọi `GetEnv` ngay lúc này** đã attach vào JVM và có thể lấy `JNIEnv *` cho phiên bản JNI yêu cầu chưa. Hàm **không tự attach**.

Bài học tập trung vào việc **lấy `JavaVM` bằng `GetJavaVM` và kiểm tra trạng thái luồng bằng `GetEnv`**, rồi đặt kết quả vào đúng luồng điều khiển native/Java. Ví dụ hoàn chỉnh có Java 17+, C11 và đường chạy cho Linux, macOS, Windows. Không dùng các bước GC hay callback phức tạp để làm nhiễu vấn đề chính.

Sau bài này, bạn có thể:

1. Phân biệt lifetime và phạm vi sử dụng của `JavaVM *` với `JNIEnv *`.
2. Gọi `(*env)->GetJavaVM(env, &vm)` trong C và giải thích vì sao `&vm` có kiểu `JavaVM **`.
3. Gọi `(*vm)->GetEnv(vm, (void **)&thread_env, JNI_VERSION_1_6)` và diễn giải đúng `JNI_OK`, `JNI_EDETACHED`, `JNI_EVERSION`.
4. Xác định khi nào chỉ cần sử dụng `JNIEnv *` hiện có, khi nào native-created thread phải `AttachCurrentThread` rồi `DetachCurrentThread`.
5. Viết kiểm thử deterministic trên Java thread và trên OS native thread; biết chỗ nào chưa thể gọi JNI.
6. Tránh lưu/chia sẻ `JNIEnv *` sai thread, detach nhầm Java-owned thread, dùng con trỏ sau detach hoặc đoán trạng thái từ `NULL`.

## 2. Mô hình đúng: JVM dùng chung, môi trường JNI gắn với thread

~~~text
                      Một Java Virtual Machine
                           JavaVM *vm
                                |
                     Invocation API function table
                     /          |           \
           GetEnv(vm,...)  AttachCurrentThread  DetachCurrentThread
                      theo THREAD GỌI hiện tại

   Java main thread           Java-created Thread          C-created OS thread
   JVM đã attach              JVM đã attach                CHƯA attach
        |                           |                           |
   JNIEnv *envA              JNIEnv *envB             GetEnv => JNI_EDETACHED
        |                           |                           |
   GetEnv => JNI_OK          GetEnv => JNI_OK          AttachCurrentThread
                                                             |
                                                        JNIEnv *envC
                                                             |
                                                        GetEnv => JNI_OK
                                                             |
                                                        DetachCurrentThread
                                                             |
                                                   GetEnv => JNI_EDETACHED
~~~

`JavaVM *` là interface tới JVM, có thể chuyển cho các native threads để chúng **tự** hỏi/attach. `JNIEnv *` là interface JNI hợp lệ **chỉ trong thread đã nhận nó**; không sao chép `envA` sang thread B hoặc thread C rồi gọi `(*envA)->...` tại đó. Một vài JVM có thể trả các giá trị con trỏ nhìn giống nhau ở một số hoàn cảnh; **không suy ra quyền dùng cross-thread từ việc so giá trị bit của pointer**.

Khi JVM gọi native method, thread đó đã attached; `JNIEnv *env` tham số đầu vào là hợp lệ trong lời gọi hiện tại. Ngược lại, thread tự tạo bằng OS API chưa attach cần dùng `JavaVM *` để hỏi trạng thái và attach trước khi chạm vào đối tượng Java.

**Điểm cốt lõi:** `GetJavaVM` trả lời “JVM nào?”, còn `GetEnv` trả lời “thread đang chạy đã có JNI environment tương thích chưa?”. Một `JavaVM *` không cấp phát `JNIEnv *` cho thread khác chỉ bằng cách chia sẻ con trỏ.

## 3. Đọc đúng prototype `GetJavaVM`

Đặc tả JNI định nghĩa:

~~~c
/* Chữ ký giao diện, không phải hàm tự triển khai. */
jint GetJavaVM(JNIEnv *env, JavaVM **vm);
~~~

Trong file C, khi đã ở bên trong một JNI method:

~~~c
/* Mảnh C nằm trong JNI method có JNIEnv *env hợp lệ. */
JavaVM *vm = NULL;
jint result = (*env)->GetJavaVM(env, &vm);

if (result != JNI_OK || vm == NULL) {
    /* Không dùng vm. Trả lỗi theo hợp đồng native method. */
    return;
}
/* vm giờ là interface JVM liên quan đến thread đang gọi. */
~~~

Giải thích các lớp con trỏ:
- `env` có kiểu `JNIEnv *` được JVM truyền vào hàm JNI; ký hiệu `(*env)->...` là cách gọi qua bảng hàm JNI **trong C**.
- `vm` là **biến** lưu giá trị `JavaVM *`.
- `&vm` là địa chỉ của biến đó, có kiểu `JavaVM **`, để `GetJavaVM` **ghi kết quả** vào.
- Giá trị trả về có kiểu `jint`. `JNI_OK` bằng `0`. Giá trị âm biểu thị lỗi, nên phải kiểm tra cả mã trả về và pointer đầu ra trước khi dùng.
- `GetJavaVM` chỉ hợp lệ khi đã có một `JNIEnv *` đúng thread. **Không thể gọi `GetJavaVM` từ thread detached bằng một `JNIEnv *` chưa tồn tại**, càng không được dùng `env` của thread khác để “lấy hộ” trong detached thread.

Cú pháp C++ JNI có dạng `env->GetJavaVM(&vm)` vì wrapper type của `JNIEnv` trong C++ hỗ trợ method-style API. **Bài này dùng mã C**, cần giữ nhất quán cú pháp `(*env)->...` và `(*vm)->...`.

Một JNI implementation có thể nhận `JavaVM *` trong hàm `JNI_OnLoad(JavaVM *, void *)`. Đây là con đường khác do JVM cung cấp, nhưng khi đang **ở bên trong native method với `JNIEnv *`**, `GetJavaVM` là cách trực tiếp đúng mục tiêu bài học. Đừng tự khởi tạo thêm một JVM chỉ để dùng `GetEnv` trong thư viện đã được một JVM nạp.

## 4. Đọc đúng prototype `GetEnv` và ba trạng thái cần nhớ

`GetEnv` nằm trên bảng chức năng Invocation API:

~~~c
/* Chữ ký đặc tả, không phải hàm tự triển khai. */
jint GetEnv(JavaVM *vm, void **env, jint version);
~~~

Trong C:

~~~c
/* vm đã thu được hợp lệ từ GetJavaVM. */
JNIEnv *thread_env = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&thread_env, JNI_VERSION_1_6);
~~~

`(void **)&thread_env` truyền **địa chỉ ô lưu pointer** cho `GetEnv`. Không truyền `(void **)thread_env` vì lúc này nó là giá trị của con trỏ (đang `NULL`); hàm cần một vị trí để ghi output. Tham số `version` là phiên bản **JNI interface** muốn dùng, không phải Java language version/bytecode target. `JNI_VERSION_1_6` được JDK 17+ hỗ trợ và đủ cho bài này.

| Mã trả về | Giá trị hằng JNI | Nghĩa của `GetEnv` | `thread_env` sau lời gọi |
|---|---|---|---|
| `JNI_OK` | `0` | Thread hiện tại **đã attach** và phiên bản JNI yêu cầu được hỗ trợ | `JNIEnv *` hợp lệ của chính thread này |
| `JNI_EDETACHED` | `-2` | Thread hiện tại **chưa attach** JVM đó | Được đặt thành `NULL` |
| `JNI_EVERSION` | `-3` | Phiên bản JNI yêu cầu không được JVM hỗ trợ | Được đặt thành `NULL` |

Nếu nhận trạng thái lỗi khác tùy nền tảng/hợp đồng API, xử lý nó là lỗi; **không coi mọi mã âm đều có nghĩa thread detached**. Không dùng `thread_env` nếu kết quả không phải `JNI_OK`. `GetEnv` chỉ kiểm tra và lấy interface khi đã attached; **không tự attach**, không đổi trạng thái thread và không tự cập nhật `JavaVM *` sang JVM khác.

### Thứ tự xử lý đúng theo trạng thái

~~~c
/* Fragment minh họa dùng trong một hàm của native-created thread.
   vm là JavaVM * hợp lệ, do caller cung cấp. */
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (rc == JNI_OK) {
    /* Thread đã attached. Dùng env nhưng KHÔNG tự detach nếu không sở hữu attach. */
} else if (rc == JNI_EDETACHED) {
    /* Đây mới là nhánh có thể gọi AttachCurrentThread nếu cần JNI. */
} else if (rc == JNI_EVERSION) {
    /* Sửa phiên bản JNI yêu cầu; đừng cố dereference env. */
} else {
    /* Lỗi khác cần được báo và xử lý. */
}
~~~

Hãy phân biệt **trạng thái** với **ownership của attach**. `JNI_OK` nói thread đang attached; nó không có nghĩa đoạn code này có quyền detach thread. Java-created thread được JVM quản lý; native library không nên tự `DetachCurrentThread` trên thread Java đó. Native-created thread do thư viện attach thành công thì chính đường đời của native worker phải detach nó.

### Phản ví dụ quan trọng: `GetEnv` không biến con trỏ chưa biết thành hợp lệ

~~~c
/* SAI — ví dụ chỉ để nhận diện anti-pattern, không chạy. */
JNIEnv *env = NULL;
(*env)->GetJavaVM(env, &vm);
~~~

Không có `JNIEnv *` hợp lệ, nên không thể dereference. Native-created thread chỉ có thể bắt đầu bằng **`JavaVM *` đã được cấp hợp lệ từ JVM thông qua một đường khác**; sau đó gọi `GetEnv` và nếu cần `AttachCurrentThread`. Nhận diện và xử lý từng giai đoạn giúp tránh crash ngay cả trước khi kiểm tra status.

## 5. Khi nào cần attach/detach: quy tắc ownership và state machine

| Thread đang chạy | `GetEnv(JNI_VERSION_1_6)` dự kiến | Ai attach? | Ai detach? |
|---|---|---|---|
| Java `main` gọi JNI | `JNI_OK` | JVM | JVM quản lý lifecycle; **không detach trong JNI method** |
| `new Thread(...).start()` gọi JNI | `JNI_OK` | JVM | JVM quản lý; **không detach trong JNI method** |
| Thread C mới tạo chưa tương tác JNI | `JNI_EDETACHED` | Native code gọi `AttachCurrentThread` nếu cần | Native code attach phải `DetachCurrentThread` trước khi thread kết thúc |
| Native thread đã attach từ trước | `JNI_OK` | Một nơi khác đã attach | Không detach “hộ” nếu không chịu trách nhiệm ownership |
| Request phiên bản JNI không hỗ trợ | `JNI_EVERSION` | Không suy diễn rằng thread detached | Chọn interface version đúng và xử lý lỗi |

Một native worker hợp lý có vòng đời:

~~~text
Native OS thread begins
    |
    v
GetEnv(vm, &env, JNI_VERSION_1_6)
    |
    +-- JNI_OK ---------> dùng env đã có; không tự nhận ownership attach
    |
    +-- JNI_EVERSION ---> dừng/điều chỉnh version, không dùng env
    |
    +-- JNI_EDETACHED --> AttachCurrentThread(vm, &env, NULL)
                              |
                        attach failure --> trả lỗi, không dùng env
                              |
                          JNI_OK
                              |
                       thao tác JNI hợp lệ
                              |
                       cleanup references
                              |
                       DetachCurrentThread(vm)
                              |
                          worker exits
~~~

`AttachCurrentThread` có thể trả về existing `JNIEnv *` nếu thread đã attached; việc gọi lại **không cấp quyền detach** cho một caller vốn không sở hữu lifecycle của thread. Trên thread Java, nên chỉ dùng `JNIEnv *` đã được JVM truyền vào native method. Trong worker native, lưu một cờ như `attached_by_us` và chỉ detach khi đã attach thành công ở đường code này.

`AttachCurrentThreadAsDaemon` là lựa chọn để thread native được attach dưới dạng Java daemon nếu phù hợp lifecycle. `AttachCurrentThread` thường tạo non-daemon attached thread; không detach một native worker lâu dài có thể ngăn JVM shutdown bình thường. Đừng giải quyết bằng cách detach tùy tiện trên thread Java mà thư viện không tạo.

Một attached native thread có thể chạy JNI API và gọi Java, nhưng phải:
- Chỉ dùng `JNIEnv *` tại **thread được attach**, không chuyển con trỏ env qua thread khác.
- Trả về Java object refs theo đúng quy tắc local/global, dọn các local refs của native-attached thread trong vòng lặp dài (vì không có outer Java native frame tự cleanup như một Java-triggered call).
- Xử lý pending Java exceptions theo contract, không âm thầm tiếp tục JNI calls không được phép trong trạng thái pending exception.
- Không detach khi vẫn còn Java frames trên stack, monitor/resource đang cần giải phóng hoặc callbacks đang chạy.

## 6. Chương trình hoàn chỉnh Java 17+ + C11: quan sát cả Java threads và native thread

Ví dụ này có ba native methods:
1. `callingThreadStatus()` lấy `JavaVM` bằng `GetJavaVM` và gọi `GetEnv` trên Java main thread hoặc một Java-created worker thread.
2. `unsupportedVersionStatus()` gọi `GetEnv` với version cố ý không hợp lệ để nhận `JNI_EVERSION`.
3. `nativeWorkerRoundTrip()` lấy `JavaVM` qua `GetJavaVM`, tạo **một OS thread mới**, kiểm tra `JNI_EDETACHED` trước khi attach, `JNI_OK` sau attach, và `JNI_EDETACHED` trở lại sau detach.

Ví dụ sử dụng **một lần chạy đồng bộ**: Java đợi native worker hoàn tất trước khi dùng lại result. Chỉ `JavaVM *` được chuyền sang worker; `JNIEnv *` của Java caller **không** được chuyển qua thread đó.

### 6.1. Cây dự án và Java source

~~~text
jni-vm-probe/
├─ src/demo/jni/VmProbe.java
├─ native/demo_jni_VmProbe.h      # Generated by javac -h
├─ native/vm_probe.c
├─ out/demo/jni/VmProbe.class     # Generated by javac
└─ libvmprobe.so                 # Linux;
                                # macOS: libvmprobe.dylib
                                # Windows: vmprobe.dll
~~~

Tạo `src/demo/jni/VmProbe.java`:

~~~java
package demo.jni;

import java.util.concurrent.FutureTask;

public final class VmProbe {
    static {
        System.loadLibrary("vmprobe");
    }

    private VmProbe() {}

    private static native int callingThreadStatus();
    private static native int unsupportedVersionStatus();
    private static native int nativeWorkerRoundTrip();

    public static void main(String[] args) throws Exception {
        int mainStatus = callingThreadStatus();

        FutureTask<Integer> result =
                new FutureTask<>(VmProbe::callingThreadStatus);
        Thread worker = new Thread(result, "java-created-worker");
        worker.start();
        int javaWorkerStatus = result.get();

        int unsupportedStatus = unsupportedVersionStatus();
        int nativeWorkerResult = nativeWorkerRoundTrip();

        if (mainStatus != 0 || javaWorkerStatus != 0
                || unsupportedStatus != -3 || nativeWorkerResult != 1) {
            throw new AssertionError(
                    "JNI status mismatch: " + mainStatus + ", "
                    + javaWorkerStatus + ", " + unsupportedStatus
                    + ", " + nativeWorkerResult);
        }

        System.out.println("javaMain=JNI_OK");
        System.out.println("javaWorker=JNI_OK");
        System.out.println("unsupportedVersion=JNI_EVERSION");
        System.out.println(
                "nativeWorker=JNI_EDETACHED -> JNI_OK -> JNI_EDETACHED");
        System.out.println("RESULT: PASS");
    }
}
~~~

`FutureTask.get()` đợi Java-created worker và chuyển exception trong worker thành `ExecutionException`, tránh việc thread phụ thất bại nhưng test vẫn PASS. `Thread` do JVM tạo đã attached khi vào native method, nên `callingThreadStatus()` dự kiến là `JNI_OK` ở cả main và Java worker. Bài cố tình không so sánh số bit của `JNIEnv *` giữa hai Java threads: việc đó không phải cách xác nhận thread ownership.

### 6.2. Sinh header từ chữ ký thật

Từ gốc `jni-vm-probe`:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/VmProbe.java
javap -s -p -classpath out demo.jni.VmProbe
~~~

Trên Windows CMD có thể dùng `mkdir src\demo\jni`, `mkdir native`, `mkdir out` rồi chạy `javac --release 17 -h native -d out src\demo\jni\VmProbe.java`; lệnh `javap` giống nhau. `-h native` tạo file header `native/demo_jni_VmProbe.h`; không gõ tay tên JNI functions.

Cả ba native methods không nhận đối số Java và trả về `int` nên descriptor bytecode của từng method đều là **`()I`**. Vì chúng là `static native`, phía C nhận `JNIEnv *` và `jclass` làm hai tham số đầu. Tên symbol do JNI quy định có dạng:

~~~c
/* Các prototype quan trọng trong generated header: */
JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_callingThreadStatus
  (JNIEnv *, jclass);

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_unsupportedVersionStatus
  (JNIEnv *, jclass);

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_nativeWorkerRoundTrip
  (JNIEnv *, jclass);
~~~

### 6.3. Source C hoàn chỉnh

Tạo `native/vm_probe.c`:

~~~c
#include "demo_jni_VmProbe.h"

#if defined(_WIN32)
#include <windows.h>
#else
#include <pthread.h>
#endif

typedef struct {
    JavaVM *vm;
    jint result;
} WorkerArgs;

static jint get_vm(JNIEnv *env, JavaVM **out_vm) {
    *out_vm = NULL;
    jint status = (*env)->GetJavaVM(env, out_vm);
    if (status != JNI_OK || *out_vm == NULL) {
        return JNI_ERR;
    }
    return JNI_OK;
}

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_callingThreadStatus(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    JNIEnv *thread_env = NULL;
    jint status = (*vm)->GetEnv(
            vm, (void **)&thread_env, JNI_VERSION_1_6);

    if (status == JNI_OK && thread_env == NULL) {
        return JNI_ERR;
    }
    return status;
}

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_unsupportedVersionStatus(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    JNIEnv *unused_env = NULL;
    /* Version không nằm trong những version JNI đã được định nghĩa. */
    return (*vm)->GetEnv(vm, (void **)&unused_env, 0x7fffffff);
}

static jint probe_native_thread(JavaVM *vm) {
    JNIEnv *env = NULL;
    jint before = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (before != JNI_EDETACHED || env != NULL) {
        return 0;
    }

    jint attach_status = (*vm)->AttachCurrentThread(
            vm, (void **)&env, NULL);
    if (attach_status != JNI_OK) {
        return 0;
    }

    /* Sau attach thành công, phải detach cả trên đường lỗi. */
    JNIEnv *again = NULL;
    jint after = (*vm)->GetEnv(
            vm, (void **)&again, JNI_VERSION_1_6);

    jint valid = (after == JNI_OK && env != NULL && again != NULL)
            ? JNI_TRUE : JNI_FALSE;
    if (valid) {
        jint version = (*again)->GetVersion(again);
        valid = (version >= JNI_VERSION_1_6)
                ? JNI_TRUE : JNI_FALSE;
    }

    jint detach_status = (*vm)->DetachCurrentThread(vm);

    /* Sau detach, chỉ dùng JavaVM; tuyệt đối không dùng env/again. */
    JNIEnv *after_detach = NULL;
    jint detached_status = (*vm)->GetEnv(
            vm, (void **)&after_detach, JNI_VERSION_1_6);

    return (valid && detach_status == JNI_OK
            && detached_status == JNI_EDETACHED
            && after_detach == NULL) ? 1 : 0;
}

#if defined(_WIN32)
static DWORD WINAPI worker_entry(LPVOID argument) {
    WorkerArgs *args = (WorkerArgs *)argument;
    args->result = probe_native_thread(args->vm);
    return 0;
}
#else
static void *worker_entry(void *argument) {
    WorkerArgs *args = (WorkerArgs *)argument;
    args->result = probe_native_thread(args->vm);
    return NULL;
}
#endif

JNIEXPORT jint JNICALL Java_demo_jni_VmProbe_nativeWorkerRoundTrip(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    JavaVM *vm = NULL;
    if (get_vm(env, &vm) != JNI_OK) {
        return JNI_ERR;
    }

    WorkerArgs args = {vm, 0};

#if defined(_WIN32)
    HANDLE thread = CreateThread(
            NULL, 0, worker_entry, &args, 0, NULL);
    if (thread == NULL) {
        return JNI_ERR;
    }

    DWORD wait_status = WaitForSingleObject(thread, INFINITE);
    CloseHandle(thread);
    if (wait_status != WAIT_OBJECT_0) {
        return JNI_ERR;
    }
#else
    pthread_t thread;
    if (pthread_create(&thread, NULL, worker_entry, &args) != 0) {
        return JNI_ERR;
    }
    if (pthread_join(thread, NULL) != 0) {
        return JNI_ERR;
    }
#endif

    return args.result;
}
~~~

Toàn bộ file được biên dịch như C (không phải C++). `WorkerArgs` đặt trên stack của **JNI caller**, và caller **join/wait** native worker trước khi đọc `args.result`; do vậy thông thường context vẫn còn sống trong suốt worker. Demo dùng một worker ngắn hạn; trong hệ thống thật, phải xây xử lý lỗi chờ thread và ownership của context đủ an toàn cho các đường lỗi hiếm, vì nếu một thao tác join/wait thất bại khi worker vẫn có thể chạy thì **không được giải phóng context trên stack và để worker còn tham chiếu tới nó**. Có thể dùng context heap + giao thức hoàn thành để xử lý trường hợp đó.

Phân tích những phép gọi chính:
1. `get_vm(env, &vm)` thực hiện `GetJavaVM` từ đúng Java-caller `JNIEnv *`. `JavaVM *vm` hợp lệ được đưa vào `WorkerArgs`.
2. `callingThreadStatus` thực hiện `GetEnv` ngay trong thread do JVM gọi: kết quả `JNI_OK` khi version được hỗ trợ, và output `thread_env` không null.
3. `unsupportedVersionStatus` yêu cầu một code version cố tình không được hỗ trợ (`0x7fffffff`); kỳ vọng `JNI_EVERSION`, không phải `JNI_EDETACHED`. Thí nghiệm này cho thấy **trạng thái attach và tương thích version là hai điều khác nhau**.
4. `worker_entry` là entry point của **OS thread mới**. Nó chỉ được cung cấp `JavaVM *`, không nhận `JNIEnv *` của Java thread.
5. `probe_native_thread` hỏi `GetEnv` trước khi attach: `JNI_EDETACHED`. Sau `AttachCurrentThread` thành công, gọi lại `GetEnv`: `JNI_OK` và một `JNIEnv *` hợp lệ; lúc đó mới gọi `GetVersion` qua env.
6. Sau `DetachCurrentThread`, mọi `JNIEnv *` vừa nhận từ worker trở thành không được phép dùng. Thao tác kiểm tra lại `GetEnv` sau detach vẫn hợp lệ vì nó gọi qua **`JavaVM *`**, không qua env cũ.
7. Khi `AttachCurrentThread` đã thành công, code thực hiện detach kể cả khi `GetEnv` hoặc kiểm tra version sau attach không đạt, tránh native thread kết thúc mà bỏ quên attach.
8. Java chỉ nhận một mã kiểm thử `1` khi native worker đã trải qua đúng trạng thái và cleanup. Mọi mã khác làm Java ném `AssertionError`, vì thế không thể in `RESULT: PASS` khi bước native thất bại.

**Giới hạn quan trọng:** với một native worker dài hạn, nếu `GetEnv` lúc đầu đã là `JNI_OK` vì thread được nơi khác attach, không được dùng hàm minh họa này như một hàm “detach hộ”: code trên chủ động **yêu cầu trạng thái ban đầu phải là detached** và chỉ attach khi đúng điều kiện. Trên thread đã attached từ trước, phải có một helper đa nhánh tách `borrowed env` khỏi `attached_by_us env`.

### 6.4. Lệnh build và chạy theo nền tảng

**Linux** (GCC/Clang, JDK 17+, có pthreads):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o libvmprobe.so native/vm_probe.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

Nếu `JAVA_HOME` đã được đặt đúng gốc JDK thì không cần dòng `export`. `-pthread` yêu cầu biên dịch và liên kết phù hợp với thư viện luồng POSIX. `-Djava.library.path=.` tìm `libvmprobe.so` tại working directory; `-cp out` tìm `VmProbe.class` theo package.

**macOS** (Clang, Xcode Command Line Tools):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"

cc -std=c11 -Wall -Wextra -pedantic -fPIC -dynamiclib -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o libvmprobe.dylib native/vm_probe.c

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

Chọn compiler target tương thích JVM: arm64 với arm64 trên Apple Silicon, x86-64 với x86-64 khi JVM chạy tương ứng.

**Windows** (MSVC Developer Command Prompt, cùng kiến trúc với JVM):

~~~bat
javac --release 17 -h native -d out src\demo\jni\VmProbe.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\vm_probe.c /Fe:vmprobe.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.VmProbe
~~~

Dấu `^` là nối dòng trong **CMD**; không dùng nguyên dòng lệnh này trong PowerShell. `/LD` tạo DLL; `CreateThread` là API Windows, còn `pthread_create` thuộc nhánh POSIX. Không cần liên kết ứng dụng Java với `libjvm` để chạy chương trình JNI này, vì JVM cung cấp `JNIEnv *` qua native call.

### 6.5. Output dự kiến và điều gì thật sự được chứng minh

Nếu có đúng JDK, compiler, headers, architecture và thư viện được nạp, chương trình sẽ in:

~~~text
javaMain=JNI_OK
javaWorker=JNI_OK
unsupportedVersion=JNI_EVERSION
nativeWorker=JNI_EDETACHED -> JNI_OK -> JNI_EDETACHED
RESULT: PASS
~~~

Đây là **stdout của đường chạy thành công** được suy ra từ các assertion trong mã Java. Nếu một trạng thái không đúng, Java ném `AssertionError` thay vì in các dòng trên; nếu thư viện không nạp được thì chương trình ném `UnsatisfiedLinkError` trước khi chạy các kiểm tra. Output `nativeWorker` cho biết các giai đoạn đã được C kiểm tra và Java đã xác nhận `1`, chứ không phải transcript C tự in ba code status.

Lưu ý rằng `JNI_VERSION_1_6` ở các lệnh `GetEnv` hoàn toàn hợp lệ trên JDK 17+. `JNI_EVERSION` ở ví dụ là **lỗi có chủ đích** từ version code `0x7fffffff`, không phải sự cố do JDK 17 chưa hỗ trợ một API Java mới. Ví dụ dùng Java 17 làm target compilation, nhưng định nghĩa JNI native API được đọc từ `jni.h` của **JDK đang build** và binary phải khớp nền tảng khi thực thi.

## 7. Vì sao cách kiểm tra `GetEnv` này có ý nghĩa trong hệ thống thật?

Native library thường được JVM gọi qua Java wrapper, sau đó khởi tạo worker threads riêng để poll socket, theo dõi thiết bị, thực hiện tính toán, hoặc callback về Java. Worker ấy không nhận `JNIEnv *` từ một JVM-native method, nên không thể “cất env của main thread” để tái sử dụng. Thay vào đó:

~~~text
Java calls init()
   |
   +-- native method có JNIEnv *env
   |      GetJavaVM(env, &vm)
   |      tạo native context lưu vm (trong JVM lifetime)
   |      khởi động native workers
   |
   +-- worker C dùng vm:
          GetEnv(vm, &env, version)
             |
             +-- JNI_OK       -> sử dụng env của thread hiện tại
             +-- JNI_EDETACHED-> AttachCurrentThread; nhớ ownership
             +-- JNI_EVERSION -> báo lỗi/cập nhật yêu cầu version
          ...
          gọi Java API/callback nếu hợp lệ
          dọn local/global references
          detach nếu chính mình attach
~~~

Để mã hóa contract này, có thể dùng pattern RAII ở C++ hoặc helper đối xứng trong C. Dưới đây là **mã giả C dạng fragment** cho một hàm worker có thể **được gọi cả trên thread đã attached và detached**, không phải file có thể biên dịch/chạy độc lập:

~~~c
JNIEnv *env = NULL;
int attached_by_us = 0;

jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
if (status == JNI_EDETACHED) {
    status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
    if (status != JNI_OK) {
        /* Báo lỗi và dừng trước bất kỳ JNI call nào. */
        return;
    }
    attached_by_us = 1;
} else if (status != JNI_OK) {
    /* JNI_EVERSION hoặc lỗi khác: không được dùng env. */
    return;
}

/* Chỉ tới đây khi env hợp lệ cho thread hiện tại.
   Thực hiện JNI work, giải phóng local refs, xử lý exceptions. */

if (attached_by_us) {
    (*vm)->DetachCurrentThread(vm);
}
~~~

Trong ứng dụng, **mọi nhánh return/goto/exception sau attach** phải đi qua một nơi cleanup chung trước khi thread kết thúc. Nếu native code trả về giữa chừng mà bỏ `DetachCurrentThread`, attached thread có thể kéo dài resource lifetime và ngăn VM shutdown. Nếu code detach ngay sau khi spawn một asynchronous callback đang cần env, callback sẽ dùng invalid env; phải quản lý thời điểm công việc kết thúc trước khi detach.

Một số kiến trúc chỉ cần `GetEnv` mà không cần attach: chẳng hạn thư viện đăng ký một số callback được gọi **từ Java-created threads** qua JNI. Nếu `GetEnv` đã `JNI_OK`, dùng env hiện có. Không phải mọi native entry point đều cần gọi `AttachCurrentThread`.

## 8. Các lỗi phổ biến khi sử dụng `GetJavaVM` / `GetEnv`

| Sai lầm | Kết quả có thể xảy ra | Cách đúng |
|---|---|---|
| Lưu `JNIEnv *env` từ Java main để thread C khác dùng | Sai thread, crash/undefined behavior | Chuyển **`JavaVM *`**, worker gọi `GetEnv` và nếu cần `AttachCurrentThread` |
| Gọi `GetEnv` rồi mặc định `env != NULL` mà không kiểm tra mã status | Dùng `NULL` ở thread detached/unsupported JNI version | Kiểm tra `JNI_OK` trước mọi JNI call |
| Nghĩ `GetEnv` tự attach khi bị `JNI_EDETACHED` | Không có interface hợp lệ, code gọi JNI lỗi | Chỉ attach bằng `AttachCurrentThread`/daemon variant |
| Truyền `(void **)env` thay vì `(void **)&env` | Output được ghi vào địa chỉ sai | Truyền **địa chỉ** biến con trỏ |
| Gọi `(*env)->GetJavaVM` với `env == NULL` | Dereference NULL | Chỉ gọi từ JNI method hoặc attached thread có env hợp lệ |
| Xử lý `JNI_EVERSION` giống `JNI_EDETACHED` | Che giấu version mismatch | Chọn phiên bản JNI được hỗ trợ hoặc báo lỗi |
| Gọi `DetachCurrentThread` ngay trong Java native method | Phá lifecycle của JVM-owned Java thread | Chỉ detach native thread mà code thực sự đã attach |
| Tự động detach bất cứ khi nào `GetEnv==JNI_OK` | Detach thread không do code sở hữu | Dùng cờ `attached_by_us` |
| Dùng `JNIEnv *` sau `DetachCurrentThread` | Invalid environment | Bỏ env cũ; attach lại hợp lệ nếu worker còn cần JNI |
| Để native non-daemon worker attached vĩnh viễn | Giữ tài nguyên/ảnh hưởng shutdown | Thiết kế stop/join/detach, hoặc daemon attach nếu phù hợp |
| Dùng JNI local refs suốt vòng lặp dài của native-attached worker | Tràn local ref table/resource | `DeleteLocalRef`, `PushLocalFrame`/`PopLocalFrame` |
| Dùng `JavaVM *` sau JVM shutdown/unload | Invalid JVM lifetime | Dừng native worker và cleanup trước teardown |
| Truyền địa chỉ con trỏ JNI qua Java `long` mà không contract | ABI/lifetime/provenance không rõ | Dùng JNI handoff qua native context/`JavaVM *` trong native code |

### Một lỗi đặc biệt khó phát hiện: trộn cú pháp C và C++

Trong C, gọi:

~~~c
jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);
~~~

Trong C++ JNI headers có wrapper gọi:

~~~cpp
jint status = vm->GetEnv((void **)&env, JNI_VERSION_1_6);
~~~

Hai cách tương đương về chức năng nhưng **không tự do tráo cho nhau trong source C/C++**. Khi chuyển `.c` thành `.cpp`, dùng cú pháp đúng với type trong file đó, và dùng generated header giúp tránh C++ name mangling đối với JNI exported methods.

### Một lỗi nữa: suy diễn từ Java thread name

Tên `Thread.currentThread().getName()` không chứng minh một OS native thread đã attach hay chưa. JNI status kiểm tra trực tiếp bằng `GetEnv`. Tương tự, `JavaVM *` có thể tồn tại và hợp lệ ngay cả khi **thread hiện tại** đang detached; chính vì vậy `GetEnv` có ý nghĩa.

## 9. Diagnostic theo thứ tự khi ví dụ không chạy

### A. Chưa tạo được header hoặc native binary

- `javac: file not found`: kiểm tra `src/demo/jni/VmProbe.java`, package và working directory.
- Không có `native/demo_jni_VmProbe.h`: kiểm tra `-h native` và ba method `native`.
- C báo `jni.h: No such file or directory`: `JAVA_HOME` phải là JDK, bổ sung include cho gốc và platform.
- Lỗi signature `conflicting types`: triển khai theo generated header, đủ hai tham số ẩn `JNIEnv *` và `jclass`.
- `pthread.h` không tồn tại trên Windows/MSVC: code phải đi vào nhánh `_WIN32` với `windows.h`; không dùng flag POSIX trên MSVC.

### B. Có file binary nhưng JVM không nạp được

- `UnsatisfiedLinkError: no vmprobe in java.library.path`: kiểm tra `libvmprobe.so`/`libvmprobe.dylib`/`vmprobe.dll` và `-Djava.library.path=.`.
- `wrong ELF class` / sai architecture: đối chiếu OS/CPU/JVM/toolchain.
- `UnsatisfiedLinkError` lúc gọi một trong ba native methods: so `javap -s -p`, generated header và exported symbols. Một thư viện có thể load được nhưng thiếu native method đúng tên.
- Nếu lỗi từ native loader **thiếu thư viện phụ thuộc**, dùng `ldd libvmprobe.so` (Linux), `otool -L libvmprobe.dylib` (macOS) hoặc `dumpbin /DEPENDENTS vmprobe.dll` (Windows) khi phù hợp. Đừng nhầm classpath Java với native library search path.

### C. Nạp được nhưng mã trạng thái sai

Nếu assertion hiển thị chẳng hạn `JNI status mismatch: 0, 0, -3, 0`, hai Java threads và unsupported version check đã đạt nhưng native round trip trả `0`. Hãy xem:
- Native-created thread có thật sự mới/detached không?
- `GetEnv` đã nhận `JNI_EDETACHED` và output `env==NULL` trước attach chưa?
- `AttachCurrentThread` có trả `JNI_OK` không, và `env` có khác NULL không?
- `GetEnv` sau attach có `JNI_OK` không?
- `DetachCurrentThread` có được gọi sau khi JNI work hoàn tất không?
- Lệnh join/wait có thực sự đợi thread kết thúc và source binary có được build lại?

Không thay bằng “in mỗi địa chỉ `JNIEnv *`”, vì địa chỉ không phải hợp đồng. Để điều tra, log **mã status và thread identifier** tại đúng các mốc, tránh in thông tin nhạy cảm/lifetime không kiểm soát. Khi native code có nhiều JNI calls, thử `-Xcheck:jni` trên HotSpot để phát hiện một phần lỗi dùng JNI sai; công cụ không bảo đảm bắt mọi race hay lifetime bug.

## 10. Tình huống production: lưu `JavaVM *` và shutdown đúng

Một native module tạo worker bất đồng bộ thường thu `JavaVM *` một lần trong JNI initialization, rồi giữ nó trong native context. Việc lưu `JavaVM *` có ý nghĩa **trong lifetime của JVM đó**; không gọi `free(vm)` và không coi nó hợp lệ sau khi JVM đã dừng. Worker phải được stop/join và các JNI refs/native resources phải dọn trước khi context bị giải phóng.

### Các quyết định phải ghi trong contract của native subsystem

| Vấn đề | Câu hỏi thiết kế |
|---|---|
| JVM lifetime | Ai đảm bảo JVM còn sống khi worker gọi `GetEnv`/`AttachCurrentThread`? |
| Attach ownership | Thread do Java tạo hay native tạo? Chỗ nào gọi `AttachCurrentThread`, chỗ nào phải detach? |
| Callback | Nếu callback vào Java, exception được kiểm tra/xử lý ở đâu? |
| Local reference lifetime | Worker có vòng lặp dài không? Có `DeleteLocalRef`/local frames? |
| Class loading | Attached native thread có thể có context class loader ban đầu là bootstrap loader; lookup application class qua `FindClass` có thể cần xử lý class loader rõ ràng |
| Termination | Khi JVM shutdown, có stop flag, join, timeout và không bắt đầu callback mới không? |
| Resource ownership | `JavaVM *` không phải object cần `free`; global refs cần `DeleteGlobalRef`; native allocations cần cleanup của chính chúng |

Với native worker đã attached mà gọi Java static/object methods, cần bảo đảm class/method IDs đã được resolve đúng; `jclass` là JNI reference có lifetime và nếu cache lâu phải dùng global ref phù hợp. Không gửi local ref của Java caller cho worker như con trỏ chia sẻ. Các chủ đề reference ownership/callback có thêm nguyên tắc riêng, nhưng **bước mở khóa đầu tiên luôn là trạng thái thread từ `GetEnv`**.

## 11. Checklist nghiệm thu cho `GetJavaVM` và `GetEnv`

- [ ] Có `JNIEnv *` hợp lệ từ JNI method hoặc thread đã attached trước khi gọi `GetJavaVM`.
- [ ] Gọi `(*env)->GetJavaVM(env, &vm)` và kiểm tra `JNI_OK` cùng `vm != NULL`.
- [ ] Chỉ chuyển `JavaVM *` sang native worker, không chuyển `JNIEnv *` của Java caller.
- [ ] Gọi `GetEnv` với `(void **)&env` và phiên bản hỗ trợ, ví dụ `JNI_VERSION_1_6`.
- [ ] Phân nhánh `JNI_OK` (đã attached), `JNI_EDETACHED` (chưa attached) và `JNI_EVERSION` (không hỗ trợ version).
- [ ] `GetEnv` không tự attach; chỉ dùng `env` khi trạng thái cho phép.
- [ ] Native worker attach thành công mới dùng JNI, sau đó detach **chỉ khi worker/code sở hữu attach**.
- [ ] Không detach Java-owned thread; không dùng `JNIEnv *` sau detach hoặc cross-thread.
- [ ] JNI local refs, Java exceptions và callback lifetime được quản lý trước khi detach.
- [ ] Java class/header/C export/binary cùng version; Java và native tests cho expected status đã đạt.
- [ ] Shutdown dừng/join native workers trước khi JVM/context bị giải phóng.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Native method có `JNIEnv *env`, muốn một pthread khác gọi Java. Có thể lưu `env` vào biến global không?  
**Trả lời:** Không. `JNIEnv *` gắn với thread hiện tại. Lấy `JavaVM *` bằng `GetJavaVM` rồi worker gọi `GetEnv`; nếu detached thì attach và dùng env do chính worker nhận được.

**Câu 2.** Trên Java `new Thread(...)` đi vào native method, `GetEnv` trả gì?  
**Trả lời:** Với JNI version hỗ trợ và thread đang thực thi JNI method, thread này đã attached nên `JNI_OK` cùng `JNIEnv *` hợp lệ cho thread đó.

**Câu 3.** Một C-created thread nhận `JNI_EDETACHED`. Sau khi gọi `GetEnv` có thể gọi `GetVersion` qua env chưa?  
**Trả lời:** Chưa. `GetEnv` không attach và output env bị đặt thành NULL. Cần `AttachCurrentThread` thành công rồi mới thực hiện JNI calls.

**Câu 4.** Vì sao version `0x7fffffff` trong demo tạo `JNI_EVERSION` dù thread Java đang attached?  
**Trả lời:** `GetEnv` có hai điều kiện: thread đã attached **và** JNI interface version được hỗ trợ. Giá trị thử nghiệm cố tình không hỗ trợ, nên trả `JNI_EVERSION`. Nó không có nghĩa Java bytecode không tương thích.

**Câu 5.** Gọi `GetEnv` trả `JNI_OK`, vậy luôn detach khi xong có đúng không?  
**Trả lời:** Không. `JNI_OK` chỉ mô tả trạng thái; caller có thể đang “mượn” attach do JVM/nơi khác quản lý. Chỉ detach native thread do chính code đó attach theo hợp đồng lifecycle.

**Câu 6.** Sau `DetachCurrentThread`, có thể dùng lại pointer `JNIEnv *env` cũ để lấy `JavaVM` không?  
**Trả lời:** Không. Env cũ đã hết hiệu lực. Nếu vẫn còn `JavaVM *` hợp lệ và worker cần JNI tiếp, phải kiểm tra/attach lại theo quy trình; không dereference env cũ.

## 13. Tổng kết và tài liệu kỹ thuật

**`GetJavaVM`** lấy interface JVM từ một `JNIEnv *` **đã hợp lệ**; **`GetEnv`** hỏi trạng thái **của thread hiện tại**, có thể trả `JNI_OK`, `JNI_EDETACHED` hoặc `JNI_EVERSION`. Có `JavaVM *` không có nghĩa mọi thread tự có `JNIEnv *`. Hãy quyết định rõ ai sở hữu thao tác attach/detach, không dùng env sai thread, không tiếp tục JNI calls sau detach và dọn references/callbacks trước khi kết thúc native worker.

Tham khảo chính thức: [Oracle JNI Functions — GetJavaVM](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html), [Oracle JNI Invocation API — GetEnv, AttachCurrentThread, DetachCurrentThread](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html), [Oracle JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html). Các quy tắc về version, trạng thái thread và ABI nên đối chiếu trực tiếp với `jni.h` và JVM/toolchain đang chạy.