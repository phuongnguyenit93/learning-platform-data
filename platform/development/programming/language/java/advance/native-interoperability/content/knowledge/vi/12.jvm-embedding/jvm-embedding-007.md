# DestroyJavaVM, luồng không daemon và điều kiện kết thúc máy ảo

## 1. Vì sao ứng dụng nhúng JVM không thể “tắt VM ngay lập tức”?

Với **JNI Invocation API**, một chương trình C hoặc C++ có thể tạo và điều khiển JVM ngay bên trong tiến trình native. Khác với ứng dụng chạy bằng lệnh `java`, ở đây **host native** sở hữu thời điểm tạo VM, chuyển vào Java và yêu cầu kết thúc VM.

Luồng cơ bản:

~~~text
Tiến trình native (C/C++)
       |
       | JNI_CreateJavaVM(...)
       v
JVM được khởi tạo, thread gọi được attach
       |
       | FindClass / CallStaticVoidMethod / ...
       v
Java có thể tạo các Java threads
       |
       | host yêu cầu dừng công việc
       v
DestroyJavaVM()
       |
       | chờ các non-daemon threads phù hợp kết thúc/detach
       | thực hiện quy trình shutdown của JVM
       v
DestroyJavaVM trả JNI_OK hoặc mã lỗi
       |
       v
Native host tiếp tục làm việc ngoài JVM hoặc thoát process
~~~

**`DestroyJavaVM` không phải “kill ngay tất cả Java threads”.** Lời gọi này có thể **chặn** trong khi JVM còn các thread **non-daemon** đang hoạt động. Những thread đó bao gồm:

- **Java threads** được đánh dấu non-daemon (mặc định nhiều thread do ứng dụng tạo).
- **Native OS threads đã attach JVM** theo chế độ non-daemon, chẳng hạn qua `AttachCurrentThread`.

Host phải thiết kế cách yêu cầu các thread kết thúc và giải phóng tài nguyên của chúng. Không thể kỳ vọng JVM tự đóng file, socket, database transaction, mutex hay các công việc nghiệp vụ đang bị giữ bởi thread native/Java.

Sau bài này, bạn có thể:

1. Mô tả điều kiện `DestroyJavaVM` được phép hoàn thành.
2. Phân biệt thread non-daemon, daemon và native OS thread **không attach**.
3. Hiểu khác biệt giữa `AttachCurrentThread` và `AttachCurrentThreadAsDaemon`.
4. Viết chương trình **Java 17+ + C11** có host tạo JVM, chạy Java worker non-daemon, yêu cầu dừng, rồi gọi `DestroyJavaVM`.
5. Nhận diện deadlock khi host gọi Destroy **trước** khi phát tín hiệu mà worker đang chờ.
6. Xử lý return code, shutdown hook, cleanup và giới hạn việc tạo lại JVM trong cùng process.

## 2. API: chữ ký, nơi gọi và giá trị trả về

C (từ `jni.h`):

~~~c
jint DestroyJavaVM(JavaVM *vm);
~~~

Với con trỏ `JavaVM *vm` được lấy từ `JNI_CreateJavaVM`, gọi trong C:

~~~c
jint rc = (*vm)->DestroyJavaVM(vm);
if (rc == JNI_OK) {
    /* Quy trình shutdown đã thành công. */
} else {
    /* Xử lý lỗi, không tiếp tục sử dụng JVM như thể còn hợp lệ. */
}
~~~

Trong C++:

~~~cpp
jint rc = vm->DestroyJavaVM();
~~~

Đây là các **đoạn minh họa**, không phải source độc lập.

**Giá trị trả về:** `JNI_OK` cho biết thành công; các mã lỗi JNI phù hợp là **số âm** (ví dụ `JNI_ERR`). `JNI_VERSION_1_6` là **hằng phiên bản giao diện JNI**, không phải mã trả về thành công của `DestroyJavaVM`.

**Nơi gọi:** `DestroyJavaVM` thuộc **Invocation API của `JavaVM`**, thường được gọi từ host C/C++ sở hữu JVM. Không phải một method Java của `Thread` và không thể thay bằng `System.gc()` hoặc `System.exit(0)` mà không thay đổi ngữ nghĩa.

**Đối số:** `vm` phải là con trỏ VM hợp lệ, thường nhận khi `JNI_CreateJavaVM` trả `JNI_OK`. Không truyền `NULL` và không dùng lại con trỏ VM cho các lời gọi JNI sau khi VM đã kết thúc thành công.

### 2.1. Điều kiện về thread đang gọi

Các phiên bản JNI hiện đại cho phép yêu cầu Destroy từ một thread native không nhất thiết là thread ban đầu tạo JVM.

- Nếu thread gọi **đã attach**, nó tham gia quá trình kết thúc VM; **không phải chờ chính nó tự kết thúc** rồi mới được trả về.
- Nếu thread gọi **chưa attach**, VM có thể tự attach thread đó để thực hiện yêu cầu shutdown.
- Nếu thread gọi đang có **các Java method trên call stack**, không nên gọi `DestroyJavaVM` từ ngữ cảnh đó. Đặc tả JNI hiện đại xem đây là lỗi khi thread đã attach; về mặt thiết kế, host nên gọi sau khi quay ra khỏi Java callbacks/native methods.

Ví dụ **không an toàn về kiến trúc**:

~~~text
Java main()
   |
   v
native closeEverything()
   |
   +--> DestroyJavaVM()   // vẫn còn Java method trên call stack
~~~

Hãy để Java báo “đã dừng xong” cho host, **return khỏi lời gọi Java/JNI**, rồi host gọi `DestroyJavaVM` từ lớp quản lý vòng đời native ở ngoài Java call stack.

## 3. Non-daemon là điều kiện quyết định

### 3.1. Non-daemon Java thread

Ở Java, thread có thuộc tính daemon. Với thread tạo bằng `new Thread(...)`, daemon status có thể được **kế thừa từ thread tạo nó**. Vì vậy khi làm ứng dụng nhúng, tốt nhất đặt rõ trạng thái để không phụ thuộc vào ngữ cảnh:

~~~java
Thread worker = new Thread(() -> {
    // Công việc nền cần hoàn tất trước khi shutdown.
}, "important-worker");

worker.setDaemon(false);  // Non-daemon: ảnh hưởng điều kiện chờ VM shutdown.
worker.start();
~~~

Đoạn này là minh họa bên trong Java method. `setDaemon` phải gọi **trước `start()`**; đổi daemon status của thread đang chạy không hợp lệ.

Khi `DestroyJavaVM` được yêu cầu, một **non-daemon worker vẫn đang sống** có thể làm host đợi. VM không tự biết lúc nào worker hoàn thành logic nghiệp vụ của bạn. Chính bạn phải có:

- Cơ chế yêu cầu dừng (`CountDownLatch`, atomic flag, interrupt phù hợp, đóng queue/socket…).
- Cách worker thoát khỏi vòng lặp và giải phóng tài nguyên.
- Chính sách chờ với timeout hay báo lỗi ở tầng ứng dụng, đặc biệt với dịch vụ có thể treo.
- Quy tắc không tạo lại task non-daemon mới trong lúc shutdown.

### 3.2. Daemon Java thread

~~~java
Thread background = new Thread(() -> {
    // Công việc chỉ cần chạy khi JVM còn hoạt động.
}, "best-effort-worker");

background.setDaemon(true);
background.start();
~~~

**Daemon threads không giữ JVM sống** trong điều kiện kết thúc như non-daemon threads. Khi VM hoàn tất shutdown, daemon thread còn đang thực thi Java code **không được bảo đảm hoàn tất phần Java còn lại**, kể cả `finally` hoặc các thao tác ghi file chưa xong.

Daemon **không phải** chế độ “tự được dọn dẹp an toàn”. Chỉ dùng cho công việc thực sự được phép ngừng khi JVM kết thúc. Nếu công việc cần flush dữ liệu, trả transaction hoặc đóng kết nối, phải làm một bước stop/join chủ động trước shutdown.

### 3.3. Thread native được attach

Native thread của hệ điều hành **chưa attach** JVM là một OS thread độc lập: nó không có `JNIEnv *` hợp lệ và **không tự được đếm** là Java non-daemon thread. Nhưng một khi attach thành công, trạng thái thay đổi.

| Loại native thread | API attach | Tác động tới `DestroyJavaVM` |
| --- | --- | --- |
| Chưa attach JVM | Không gọi attach | Không tính như Java non-daemon thread, nhưng host vẫn phải quản lý tài nguyên của OS thread |
| Attach **non-daemon** | `AttachCurrentThread` | Có thể làm Destroy chờ đến khi detach hoặc kết thúc đúng cách |
| Attach **daemon** | `AttachCurrentThreadAsDaemon` | Không tự cản shutdown do daemon status, nhưng có thể bị ngừng Java code khi VM shutdown |
| Thread tạo bởi `JNI_CreateJavaVM` | Được VM attach như main thread | Thread gọi Destroy không phải tự kết thúc trước khi lời gọi của chính nó được hoàn tất |

Gọi `AttachCurrentThreadAsDaemon` **không chuyển** một thread đã attach non-daemon thành daemon: khi đã attach, lệnh attach tiếp thường chỉ trả `JNIEnv *` hiện tại và **không đổi daemon status**. Muốn lựa chọn trạng thái, quyết định từ lúc thread chưa attach.

Ví dụ trong **một OS worker thread độc lập**, sau khi đã nhận `JavaVM *vm` từ host (minh họa, không phải source độc lập):

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **)&env, NULL);

if (rc == JNI_OK) {
    /* Dùng env CHỈ trên chính thread này. */
    /* Hoàn thành công việc JNI, đóng resources tự sở hữu... */
    (*vm)->DetachCurrentThread(vm);
}
~~~

Cùng ý tưởng nhưng là daemon:

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThreadAsDaemon(
        vm, (void **)&env, NULL);

if (rc == JNI_OK) {
    /* Công việc daemon, không phụ thuộc việc JVM còn chạy mãi. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

Trong code thật, phải xét return code của `DetachCurrentThread`, lỗi đang pending, và bảo đảm không còn Java frame trên stack. Không tái sử dụng `JNIEnv *` từ thread này ở thread khác. `JavaVM *` có thể được truyền cho các thread cần attach khi VM còn hoạt động và do host kiểm soát.

## 4. VM chờ ai và chờ tới thời điểm nào?

Các đặc tả JNI mô tả `DestroyJavaVM` chờ **các non-daemon threads còn lại** kết thúc; **thread hiện tại nếu là non-daemon** được loại khỏi điều kiện chờ (vì nó đang thực thi lệnh Destroy).

Cách hiểu thực dụng:

~~~text
Native host (thread A, đã attach JVM)
    |
    | DestroyJavaVM()
    v
  +-----------------+--------------------+
  | Java worker B   | attached OS worker C |
  | non-daemon      | non-daemon            |
  | vẫn hoạt động   | chưa Detach          |
  +-----------------+--------------------+
    |                                     |
    +----------- B xong, C detach --------+
                      |
                      v
          VM bắt đầu shutdown sequence
                      |
          shutdown hooks hoàn tất
                      |
                      v
             DestroyJavaVM trả về
~~~

**Điều kiện chờ không phải đếm số OS threads của cả process.** Native OS thread chưa attach không nằm trong tập Java non-daemon, nhưng nếu nó đang giữ một mutex/handle mà Java thread cần để kết thúc, nó vẫn có thể **gián tiếp** khiến `DestroyJavaVM` bị treo.

Tương tự, một daemon Java thread có thể giữ khóa mà một non-daemon worker đang chờ; vì vậy mặc dù daemon không trực tiếp cản VM shutdown, việc phụ thuộc tài nguyên giữa các thread vẫn có thể khiến non-daemon không thoát được.

Không khẳng định thời gian chờ cố định: API không có tham số timeout. Nếu thread non-daemon không bao giờ kết thúc, `DestroyJavaVM` có thể **chờ không giới hạn**. Timeout cần thiết kế **trước khi gọi Destroy**, ở tầng lifecycle của host hoặc Java.

### 4.1. “Tất cả non-daemon đã xong” không có nghĩa VM tắt ngay lập tức

Khi điều kiện non-daemon thỏa mãn, VM còn thực hiện **shutdown sequence** của Java. Những công việc liên quan có thể gồm:

- Bắt đầu các **shutdown hooks** đã đăng ký qua `Runtime.getRuntime().addShutdownHook`.
- Chờ các shutdown hooks kết thúc.
- Kết thúc việc chạy Java code còn lại và thu hồi tài nguyên VM theo khả năng của implementation.

Shutdown hook cũng có thể treo nếu bị deadlock, đợi IO hoặc chờ một thread/tài nguyên đã không còn. Do đó:

**Điều kiện non-daemon và điều kiện shutdown hooks hoàn tất là hai chặng khác nhau.** Cả hai đều ảnh hưởng thời điểm `DestroyJavaVM` có thể trả về.

Theo các đặc tả JNI hiện đại, JVM kết thúc với cách tiếp cận **best-effort** đối với việc giải phóng tài nguyên; không có bảo đảm toàn bộ memory mapping, native library hoặc handle của ứng dụng được khôi phục như trước khi JVM tồn tại.

## 5. Ví dụ thực hành Java 17+ và C11: shutdown có phối hợp

Ví dụ tạo JVM từ C, khởi động một **Java worker non-daemon**, yêu cầu worker dừng bằng `CountDownLatch`, rồi gọi `DestroyJavaVM`.

Mục tiêu quan trọng là thứ tự:

1. Native host tạo JVM.
2. Native gọi `EmbeddedLifecycle.startWorker()`.
3. Java worker non-daemon chạy, báo đã sẵn sàng và đợi tín hiệu dừng.
4. Native host in thông báo shutdown, rồi gọi `requestStop()` từ Java.
5. Worker thoát và in đã kết thúc.
6. Native host gọi `DestroyJavaVM` và chỉ in dòng cuối khi nó đã trả `JNI_OK`.

Nhờ hai `CountDownLatch`, thứ tự **stdout trong trường hợp thành công** ổn định. Chương trình không đo hay cam kết một khoảng chờ theo mili-giây; ý nghĩa là host **không chặn mất khả năng phát tín hiệu dừng** cho worker.

### 5.1. File `EmbeddedLifecycle.java`

~~~java
import java.util.concurrent.CountDownLatch;

public final class EmbeddedLifecycle {
    private static final CountDownLatch READY = new CountDownLatch(1);
    private static final CountDownLatch STOP = new CountDownLatch(1);

    private EmbeddedLifecycle() {
    }

    public static void startWorker() throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("Java: worker started");
            READY.countDown();

            try {
                STOP.await();
                System.out.println("Java: worker finished");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "example-non-daemon");

        worker.setDaemon(false);
        worker.start();

        // Host không tiếp tục trước khi worker thực sự khởi động.
        READY.await();
    }

    public static void requestStop() {
        STOP.countDown();
    }
}
~~~

**Những chỗ cần chú ý:**

- `worker.setDaemon(false)` đặt rõ ràng **non-daemon** trước `start`.
- `READY.countDown()` báo host rằng worker đã in dòng đầu và chuẩn bị đợi `STOP`.
- `STOP.await()` là một thao tác **blocking có chủ đích** của worker; nếu không có `requestStop`, worker không thể hoàn thành phần công việc bình thường.
- `requestStop` mở chốt bằng `STOP.countDown()`. Việc mở chốt không tự hủy JVM; worker cần thực sự thoát.
- `InterruptedException` được xử lý đúng tinh thần Java: khôi phục interrupt flag. Trong đường chạy bình thường của ví dụ, không có thread nào interrupt worker.
- Chương trình Java không cần method `main`. Nó được host C gọi bằng JNI `FindClass` và `CallStaticVoidMethod`.

Đây là **source Java đầy đủ** tương thích JDK 17 trở lên.

### 5.2. Biên dịch Java

Tạo thư mục làm việc `embed-jvm-lifecycle` với hai file nguồn:

~~~text
embed-jvm-lifecycle/
├── EmbeddedLifecycle.java
└── embed_host.c
~~~

Chạy từ thư mục này:

~~~bash
javac EmbeddedLifecycle.java
~~~

Sau lệnh trên sẽ có `EmbeddedLifecycle.class` (cùng các file class bổ sung do `javac` tạo nếu cần). **Không dùng lệnh `java EmbeddedLifecycle` để chạy** vì lớp này không có `main`; chương trình **native executable** mới là entry point.

### 5.3. File C đầy đủ: `embed_host.c`

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Dùng ngoài Java callback và trước khi VM shutdown.
 * Trong chế độ debug, in ngoại lệ JNI và clear pending exception.
 */
static void report_java_exception(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
}

int main(void) {
    JavaVM *vm = NULL;
    JNIEnv *env = NULL;
    jclass cls = NULL;
    jmethodID start = NULL;
    jmethodID stop = NULL;
    int worker_started = 0;
    int ok = 0;

    JavaVMOption options[1];
    options[0].optionString = "-Djava.class.path=.";
    options[0].extraInfo = NULL;

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_6;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    jint create_rc = JNI_CreateJavaVM(
            &vm, (void **)&env, &args);

    if (create_rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "Cannot create JVM: %d\n", (int)create_rc);
        return EXIT_FAILURE;
    }

    cls = (*env)->FindClass(env, "EmbeddedLifecycle");
    if (cls == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    start = (*env)->GetStaticMethodID(
            env, cls, "startWorker", "()V");
    if (start == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    stop = (*env)->GetStaticMethodID(
            env, cls, "requestStop", "()V");
    if (stop == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    worker_started = 1;
    (*env)->CallStaticVoidMethod(env, cls, start);
    if ((*env)->ExceptionCheck(env)) {
        report_java_exception(env);
        goto shutdown;
    }

    puts("Native: requesting VM shutdown");
    fflush(stdout);

    /* Phát tín hiệu DỪNG trước khi gọi DestroyJavaVM. */
    (*env)->CallStaticVoidMethod(env, cls, stop);
    if ((*env)->ExceptionCheck(env)) {
        report_java_exception(env);
        goto shutdown;
    }

    ok = 1;

shutdown:
    /* Đường lỗi: cố gắng đánh thức worker đã được khởi động.
     * Không gọi Java nếu chưa có class/method tương ứng.
     */
    if (!ok && worker_started && cls != NULL && stop != NULL) {
        (*env)->CallStaticVoidMethod(env, cls, stop);
        report_java_exception(env);
    }

    if (cls != NULL) {
        (*env)->DeleteLocalRef(env, cls);
    }

    /* Sau lời gọi này không sử dụng env/vm như VM còn sống. */
    jint destroy_rc = (*vm)->DestroyJavaVM(vm);
    if (destroy_rc != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n",
                (int)destroy_rc);
        return EXIT_FAILURE;
    }

    if (ok) {
        puts("Native: DestroyJavaVM returned JNI_OK");
        return EXIT_SUCCESS;
    }

    return EXIT_FAILURE;
}
~~~

**Đây là chương trình C11 độc lập**, không phải một JNI method export. `JNI_CreateJavaVM` được host liên kết với thư viện runtime `libjvm`/`jvm.dll` tương ứng JDK. Nó trả `JavaVM *` và `JNIEnv *` cho thread tạo VM; thread này vẫn đang điều khiển vòng đời VM.

Vì ví dụ **không có Java method trên stack của host khi gọi Destroy**, cách gọi `DestroyJavaVM` đúng ngữ cảnh hơn việc gọi nó bên trong một callback Java → native.

Giải thích lựa chọn trong C:

- `JNI_VERSION_1_6` là một mức **phiên bản Invocation/JNI API** được JDK 17 hỗ trợ; không có nghĩa chương trình đang chạy JDK 6.
- `JNI_CreateJavaVM`/`DestroyJavaVM` trả **mã trạng thái**, thành công là `JNI_OK`.
- `FindClass` dùng tên lớp nội bộ `"EmbeddedLifecycle"`; vì lớp không có package, không cần dấu `/`.
- `GetStaticMethodID` dùng descriptor `"()V"` vì cả `startWorker` và `requestStop` đều không nhận tham số và trả `void`; `throws InterruptedException` không làm đổi descriptor.
- `report_java_exception` dành cho đường lỗi, sử dụng `ExceptionDescribe` khi có pending exception. `ExceptionClear` là quyết định minh bạch ở đường chẩn đoán để cho phép cleanup; không dùng clear vô điều kiện trong luồng chạy bình thường.
- `worker_started` cho phép đường lỗi phát `requestStop` trước khi gọi Destroy nếu việc khởi động worker gặp exception sau khi thread đã chạy.
- `DeleteLocalRef` giải phóng handle local trước shutdown. Không có global reference hay worker native cần cleanup trong ví dụ.
- Sau khi `DestroyJavaVM` trả thành công, **không dùng `env` hay `vm` để gọi JNI lần nữa**.

### 5.4. Biên dịch native host trên Linux

Thiết lập `JAVA_HOME` tới thư mục gốc của JDK 17+; kiểm tra có `$JAVA_HOME/include/jni.h` và `$JAVA_HOME/lib/server/libjvm.so`.

~~~bash
cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

`-L` giúp **linker** tìm `libjvm.so` lúc build. `-Wl,-rpath,...` bổ sung đường tìm shared library cho chương trình khi chạy. Nếu hệ điều hành/toolchain có chính sách khác, cần cấu hình dynamic loader tương ứng; thư viện và executable phải có **cùng kiến trúc CPU**.

Chạy:

~~~bash
./embed_host
~~~

### 5.5. Biên dịch trên macOS

~~~bash
cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

Chạy:

~~~bash
./embed_host
~~~

Trên macOS, path thực tế và chính sách code signing/sandbox có thể ảnh hưởng khả năng nạp JVM. Kiểm tra `JAVA_HOME`, kiến trúc ARM64/x86-64 và vị trí `libjvm.dylib` của bản JDK đã cài.

### 5.6. Biên dịch trên Windows x64

Mở **x64 Native Tools Command Prompt for Visual Studio** và dùng JDK x64:

~~~bat
cl /nologo /W4 /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" embed_host.c /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_host.exe
~~~

Trước khi chạy, để Windows loader tìm được `jvm.dll`:

~~~bat
set "PATH=%JAVA_HOME%\bin\server;%JAVA_HOME%\bin;%PATH%"
embed_host.exe
~~~

Chỉ chạy các bước dành cho hệ điều hành của bạn. Cảnh báo linker hoặc missing DLL thường là vấn đề JDK path/ABI/runtime dependency, **không phải** lỗi logic `DestroyJavaVM`.

### 5.7. Stdout thành công

Khi dùng đúng source và classpath như trên, output dự kiến:

~~~text
Java: worker started
Native: requesting VM shutdown
Java: worker finished
Native: DestroyJavaVM returned JNI_OK
~~~

Giải thích thứ tự:

1. Java worker in dòng đầu rồi `READY.countDown`; host chỉ rời `startWorker` khi latch đã mở.
2. Host in “requesting VM shutdown” **trước khi** gọi `requestStop`.
3. Java worker chỉ có thể in “worker finished” **sau khi** `STOP.countDown` được thực hiện.
4. Dòng cuối chỉ in **sau khi `DestroyJavaVM` trả `JNI_OK`**.

Ví dụ này minh họa **phối hợp shutdown đúng thứ tự**. Nó không cố chứng minh `DestroyJavaVM` đã đợi đúng bao nhiêu mili-giây, bởi sau khi host phát tín hiệu dừng, worker có thể kết thúc rất nhanh. Ý nghĩa tổng quát là nếu worker **vẫn sống** khi Destroy bắt đầu, VM sẽ chưa thể hoàn tất shutdown cho đến khi điều kiện non-daemon được giải quyết.

## 6. Anti-pattern: gọi Destroy trước khi báo worker dừng

Đây là tình huống deadlock điển hình:

~~~text
Native host thread                        Java worker (non-daemon)
         |                                           |
         | startWorker()                             | STOP.await()
         |                                           |
         | DestroyJavaVM()                           | (đợi tín hiệu)
         |  -> chờ non-daemon worker kết thúc          |
         |                                           |
         | requestStop()  <-- KHÔNG BAO GIỜ TỚI      |
         |                                           |
         +-------------------- vòng chờ -------------+
~~~

Đoạn C sai về **thứ tự ý tưởng** (không phải source độc lập):

~~~c
(*env)->CallStaticVoidMethod(env, cls, start);

/* SAI: worker còn chờ STOP nhưng host vào Destroy trước. */
(*vm)->DestroyJavaVM(vm);

/* Dòng này không chạy nếu Destroy còn chờ worker. */
(*env)->CallStaticVoidMethod(env, cls, stop);
~~~

Ngoài khả năng treo, dòng cuối còn sai vì **không được dùng `JNIEnv *` sau khi Destroy hoàn tất**.

Cách đúng:

~~~c
(*env)->CallStaticVoidMethod(env, cls, start);

/* Tín hiệu dừng phải được gửi khi VM và env còn hợp lệ. */
(*env)->CallStaticVoidMethod(env, cls, stop);

/* Chỉ Destroy sau khi đã khởi phát shutdown hợp lệ. */
jint rc = (*vm)->DestroyJavaVM(vm);
~~~

Cả hai đoạn trên là mô tả thứ tự; khi dùng thực tế phải kiểm tra các JNI exceptions, trạng thái worker, và dọn references như ví dụ đầy đủ ở phần 5.

### 6.1. Worker bị kẹt trong Java không có timeout

Ví dụ Java worker vòng lặp vô hạn:

~~~java
Thread worker = new Thread(() -> {
    while (true) {
        // Không có điều kiện thoát và không có cơ chế hủy hợp lệ.
    }
}, "stuck-worker");
worker.setDaemon(false);
worker.start();
~~~

Nếu thread này vẫn non-daemon, `DestroyJavaVM` có thể không bao giờ được giải phóng. **Không dùng `Thread.stop`** như một phương án cleanup; nó không an toàn và đã bị loại bỏ khỏi thực hành Java hiện đại.

Thay vào đó, xây một vòng lặp có `volatile`/atomic stop flag, interrupt-aware wait, closeable queue, hoặc một giao thức dừng; đặt timeout **trước** lời gọi `DestroyJavaVM` nếu cần phát hiện worker không chịu thoát. Timeout kiểu `Future.get(timeout)` hay `Thread.join(timeout)` là cơ chế của tầng điều phối, **không biến `DestroyJavaVM` thành API có timeout**.

### 6.2. Attached native worker quên detach

Một native thread đã attach non-daemon như sau:

~~~c
/* Ví dụ thuật toán bên trong một OS thread tự tạo. */
JNIEnv *worker_env = NULL;
if ((*vm)->AttachCurrentThread(
        vm, (void **)&worker_env, NULL) == JNI_OK) {
    /* Worker chạy công việc JNI... */
    /* SAI: kết thúc đường code nhưng không DetachCurrentThread. */
}
~~~

Thiết kế hợp lệ phải bảo đảm thread đã attach được quản lý tới khi gọi `DetachCurrentThread` trong trạng thái phù hợp, trước khi worker OS thread chấm dứt. Một attached non-daemon thread chờ I/O, lock hoặc tín hiệu mãi có thể khiến Destroy bị chặn.

Dùng `AttachCurrentThreadAsDaemon` **không phải sửa lỗi cleanup**: daemon native thread vẫn có tài nguyên OS và có thể đang xử lý native code khi VM kết thúc; không được để nó gọi lại JVM đã kết thúc. Phải kiểm soát vòng đời thread ở host.

## 7. Shutdown hooks và những điều kiện bổ sung

Java có thể đăng ký shutdown hook:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("Java: shutdown hook")));
~~~

Đây là **mẫu minh họa**, không thêm vào code thực hành ở phần 5 nên **không xuất hiện trong stdout** đã nêu.

Khi JVM bắt đầu **shutdown sequence**, hook đã đăng ký được chạy. Các hooks thường được khởi động theo thứ tự không xác định và có thể chạy đồng thời. JVM chờ hooks kết thúc; hook bị treo vì network/lock hoặc chờ resource sai vòng đời sẽ kéo dài shutdown.

Các điểm thiết kế:

- Hook nên **ngắn, hữu hạn**, tránh phụ thuộc vào thread hoặc service đã bị dừng.
- Không trông chờ hook được gọi trong mọi kiểu chấm dứt tiến trình, ví dụ crash native, bị kill không thể xử lý, mất điện hoặc `Runtime.halt`.
- Không tạo vòng chờ giữa hook và native host. Nếu hook chờ một tác vụ mà host chỉ làm sau `DestroyJavaVM`, rất dễ deadlock.
- Phân biệt **kết thúc Java threads** với **dọn tài nguyên do native host sở hữu**; host vẫn chịu trách nhiệm đóng file descriptor, mutex và thư viện khác của mình.

### 7.1. So sánh `DestroyJavaVM`, `System.exit` và `Runtime.halt`

| Cơ chế | Ai thường gọi | Ngữ nghĩa đáng chú ý |
| --- | --- | --- |
| `DestroyJavaVM` | Host C/C++ qua Invocation API | Yêu cầu kết thúc VM nhúng; chờ điều kiện non-daemon và shutdown sequence; trả mã trạng thái cho host |
| `System.exit(status)` | Java code | Khởi phát quá trình shutdown của VM/JVM process thông qua `Runtime.exit`; không phải lời gọi trả về bình thường cho host như `DestroyJavaVM` |
| `Runtime.halt(status)` | Java code | Buộc kết thúc VM/process mà **không** bảo đảm chạy shutdown hooks; dành cho tình huống đặc biệt |
| `Thread.interrupt` | Thread quản lý | Tín hiệu yêu cầu dừng/cooperative cancellation cho một thread; **không tự Destroy VM** |
| `Thread.setDaemon(true)` trước start | Nơi tạo thread | Điều chỉnh việc thread có **giữ VM sống** hay không; không cung cấp giao thức cleanup |

Một ứng dụng nhúng nghiêm túc cần thống nhất **ai sở hữu quyền shutdown**. Đừng để Java code, signal handler và nhiều native threads cùng đua nhau kết thúc VM, trong khi một thành phần khác còn gọi JNI.

## 8. Vì sao native host phải quản lý từng thread?

### 8.1. Khác biệt giữa `JavaVM *` và `JNIEnv *`

- `JavaVM *` là interface tới JVM ở cấp Invocation API, dùng để attach/detach thread và Destroy VM.
- `JNIEnv *` là interface JNI gắn với **thread hiện tại**, không chia sẻ trực tiếp sang một thread khác.
- Thread tạo VM nhận `JNIEnv *` từ `JNI_CreateJavaVM`; native worker do host tạo phải `AttachCurrentThread` hoặc `AttachCurrentThreadAsDaemon` trước khi gọi JNI.
- Một thread native đã attach phải detach đúng lúc, **không** gọi `DetachCurrentThread` nếu vẫn có Java methods trên call stack.

Sau Destroy thành công, không sử dụng lại các `JNIEnv *`, `jobject`, `jclass`, method IDs hoặc `JavaVM *` như thể chúng còn chỉ đến JVM đang hoạt động. Tài nguyên thuần C/C++ có vòng đời riêng và phải được giải phóng bằng API tương ứng.

### 8.2. Non-daemon native thread có thể chặn shutdown mà không “chạy Java”

Ví dụ thread native:

1. Gọi `AttachCurrentThread` thành công.
2. Gọi một Java method rồi quay về C.
3. Đợi `pthread_cond_wait`/socket hoặc mutex **mà không detach**.
4. Host gọi `DestroyJavaVM`.

Thread đó vẫn được xem là **attached non-daemon** trong JVM, dù lúc này đang chạy/đợi bên native. Vì thế Destroy không thể suy rằng thread đã xong chỉ vì Java stack hiện tại trống. Host nên yêu cầu worker dừng, đánh thức, chờ detach hoặc chấm dứt rồi mới Destroy.

### 8.3. Attached daemon không bảo đảm hoàn thành công việc

Với `AttachCurrentThreadAsDaemon`, thread không tự ngăn VM shutdown. Tuy nhiên nếu VM kết thúc khi worker còn muốn gọi Java:

- Native code có thể vẫn chạy trong một khoảng thời gian tùy runtime và trạng thái thread.
- Không được tin rằng lời gọi JNI tiếp theo sẽ thành công sau khi shutdown bắt đầu/kết thúc.
- Java code đang chạy có thể bị ngừng khi VM kết thúc.
- Tài nguyên C/C++ của worker vẫn cần protocol cleanup ở cấp host.

Nếu công việc cần đảm bảo ghi dữ liệu, chọn **explicit stop + join/detach** ngay cả với daemon, thay vì coi daemon như giải pháp shutdown hoàn chỉnh.

## 9. Tối ưu luồng shutdown trong ứng dụng thật

Trước khi gọi `DestroyJavaVM`, triển khai một chuỗi trạng thái rõ ràng:

~~~text
RUNNING
   |
   | host ngừng nhận request mới
   v
QUIESCING
   |
   | báo stop, đóng input queues, hủy blocking IO hợp lệ
   v
DRAINING
   |
   | đợi Java workers kết thúc
   | đợi native-attached non-daemon workers detach
   | chặn callback JNI mới
   v
READY_TO_DESTROY
   |
   | không còn Java frame của host trên stack
   | host sở hữu VM gọi DestroyJavaVM đúng một lần
   v
DESTROYING
   |
   | VM chờ non-daemon còn lại + shutdown hooks
   v
TERMINATED
   |
   | JNI interfaces/references không còn hợp lệ
   v
Native process tiếp tục cleanup ngoài VM hoặc exit
~~~

Lưu ý: đây là **giao thức khuyến nghị của ứng dụng**, không phải các trạng thái enum được JNI Specification cung cấp.

Trong thực tế:

- Có một **owner** duy nhất chịu trách nhiệm VM lifecycle.
- Dừng nguồn request mới trước khi yêu cầu worker kết thúc.
- Phát stop signal **trước** khi đợi kết quả hoặc Destroy.
- Các worker Java có thể tham gia `Thread.join(timeout)` hoặc `ExecutorService.shutdown()`/`awaitTermination`; các native OS threads có thể được join bằng API hệ điều hành.
- Không giữ mutex mà worker cần để thoát trong khi owner đang đợi worker.
- Đối với một native worker đã attach, thông thường thực hiện **cleanup JNI → DetachCurrentThread → kết thúc thread**.
- Sau khi bắt đầu Destroy, không mở một đợt attach mới hoặc callback Java mới.
- Có log timestamps và thread names để chẩn đoán việc chờ; log cần viết ở nơi không gây block/deadlock chính luồng shutdown.

### 9.1. Timeout trước khi Destroy, không phải “timeout Destroy”

`DestroyJavaVM` **không nhận timeout**. Nếu yêu cầu hệ thống “phải tắt trong 5 giây”, ứng dụng cần thiết kế:

1. Gửi stop request và ngừng tạo việc mới.
2. Dùng cơ chế timeout ở mức Java/native worker để kiểm tra đã dừng.
3. Nếu có worker không dừng, ghi rõ lý do và kích hoạt chính sách escalation ở **host supervisor**, ví dụ cô lập công việc trong process khác.
4. Chỉ gọi `DestroyJavaVM` khi biết những phụ thuộc quan trọng đã được giải quyết hoặc chấp nhận điều kiện chờ của JVM.

Không nên kill bừa OS thread đang attach JVM, hay tự `free` bộ nhớ VM, vì có thể phá hỏng cả tiến trình. Khi cần “restart JVM” đáng tin, tách JVM vào **process con** thường an toàn hơn cố tháo JVM trong process lâu sống.

## 10. Trả mã và xử lý lỗi `DestroyJavaVM`

Trong C:

~~~c
jint status = (*vm)->DestroyJavaVM(vm);
if (status == JNI_OK) {
    puts("VM shutdown completed");
} else {
    fprintf(stderr, "VM shutdown failed: %d\n", (int)status);
}
~~~

Đây là đoạn minh họa, giả định `vm` hợp lệ và gọi đúng thời điểm.

Các điểm cần kiểm tra:

| Trạng thái | Ý nghĩa | Hành động |
| --- | --- | --- |
| `JNI_OK` | VM hoàn tất quy trình kết thúc theo implementation | Không dùng JNI VM/references sau đó; tiếp tục cleanup native host |
| Mã JNI lỗi âm | VM không thể hoàn thành đúng yêu cầu | Ghi mã, tránh tiếp tục như thể VM đã kết thúc sạch; xem JNI spec/JVM logs |
| Lời gọi chưa trả về | Thường còn non-daemon thread/hook chưa kết thúc hoặc đang kẹt | Chẩn đoán luồng chờ và quan hệ tài nguyên; không có timeout nội tại |
| Host crash | Có thể do dùng sai con trỏ, JNI lifetime/ABI hoặc native memory | Kiểm tra native crash logs, toolchain, ownership; không quy mọi crash cho Destroy |

**Quan trọng:** `DestroyJavaVM` trả thành công **không** có nghĩa tất cả native OS threads trong process đã bị join, mọi file descriptor đã đóng hoặc mọi native library đã được gỡ khỏi process. Những tài nguyên do host C/C++ sở hữu cần được quản lý riêng.

### 10.1. JVM destroy không đồng nghĩa “tạo lại một JVM”

Với các JDK/HotSpot phổ biến, **không có hợp đồng hỗ trợ tạo nhiều JVM trong một process**. Đặc tả JNI JDK 17 còn nêu giới hạn rõ: việc tạo nhiều VM trong một process không được hỗ trợ; tài liệu lịch sử cũng lưu ý việc unload VM không được hỗ trợ đầy đủ.

Vì vậy:

- Không thiết kế vòng lặp `CreateJavaVM → DestroyJavaVM → CreateJavaVM` và mặc định nó sẽ hoạt động.
- Không dùng `DestroyJavaVM` để hứa hẹn mọi trạng thái VM đã bị xóa tuyệt đối và libjvm có thể unload/reload an toàn.
- Nếu sản phẩm đòi khởi động/dừng JVM nhiều lần, xem xét **mỗi lần một process khác**; native supervisor có thể quản lý process đó.

Bài thực hành ở phần 5 tạo **duy nhất một VM** rồi Destroy và kết thúc chương trình; không thử khởi tạo VM thứ hai.

## 11. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `DestroyJavaVM` chờ vô hạn | Java non-daemon worker chưa thoát; native-attached non-daemon thread chưa detach; shutdown hook kẹt | Phát stop trước Destroy; kiểm tra dump threads và shutdown logs |
| Host chờ Destroy nhưng worker cần host mở latch | Vòng chờ trong giao thức dừng | Đảo thứ tự: mở latch/cancel task rồi mới Destroy |
| Dùng `AttachCurrentThreadAsDaemon` nhưng vẫn thấy tài nguyên bị rò rỉ | Daemon chỉ ảnh hưởng điều kiện shutdown, không tự đóng socket/handle | Explicit cleanup + detach/join theo owner |
| `AttachCurrentThreadAsDaemon` không làm thread hiện tại thành daemon | Thread đã attach non-daemon trước đó | Chọn daemon status từ lần attach đầu tiên |
| Java worker kết thúc nhưng Destroy còn chờ | Có attached native thread non-daemon khác, shutdown hook hoặc thread Java khác | Kiểm tra **tất cả** sources of non-daemon threads, không chỉ một worker |
| Không thể gọi JNI sau khi Destroy | `JNIEnv *`/VM references hết lifetime | Cấm callbacks và sử dụng JNI sau trạng thái TERMINATED |
| Lỗi trong `JNI_CreateJavaVM` | Sai JDK path/ABI, JNI version hoặc options | Kiểm tra mã trả về, libjvm, JDK architecture và option strings |
| Java callback vẫn nằm trên stack lúc Destroy | Host gọi shutdown trong native method mà Java đã gọi | Thoát khỏi callback rồi host mới Destroy |
| `System.exit` làm native host không chạy cleanup như mong muốn | Hai cơ chế shutdown có quyền sở hữu khác nhau | Định nghĩa owner ở host, không dùng `System.exit` để thay Destroy |
| Thử tạo JVM lần hai thất bại | Multi-VM/re-init trong cùng process không được hỗ trợ | Chạy JVM trong process con khi cần restart |

### 11.1. Cách chẩn đoán thread không chịu thoát

- Log đúng tên các **Java non-daemon** worker còn chạy, nhiệm vụ của chúng và tín hiệu dừng đã phát hay chưa.
- Kiểm tra native-attached threads có thực hiện `DetachCurrentThread` ở mọi nhánh thoát hay không.
- Kiểm tra những khóa mà shutdown hook/worker cần đã bị host giữ khi gọi Destroy hay chưa.
- Tùy JVM, dùng thread dump (ví dụ `jcmd <pid> Thread.print` hoặc tín hiệu phù hợp) **khi VM vẫn đang hoạt động** để quan sát Java stack và lock. Không trông chờ công cụ này chạy được sau VM shutdown hoàn tất.
- Nếu chỉ thấy một Java thread đã thoát, **không** vội kết luận tất cả điều kiện kết thúc VM đã thỏa: phải xét cả native threads đã attach và shutdown hooks.
- Dùng timeout tại tầng quản lý công việc để thu thập lý do, thay vì treo vô thời hạn trong `DestroyJavaVM` rồi mất khả năng phát stop signal.

## 12. Đối chiếu những khái niệm hay nhầm

| Khái niệm | Không nên hiểu thành |
| --- | --- |
| `DestroyJavaVM` | “Tương đương kill process ngay” |
| Non-daemon | “Thread tự bị JVM terminate khi host muốn thoát” |
| Daemon | “Mọi việc sẽ được flush/cleanup tự động” |
| `AttachCurrentThread` | “Chỉ đăng ký JNI, không ảnh hưởng việc shutdown” |
| `AttachCurrentThreadAsDaemon` | “Có thể chuyển thread đã attach non-daemon thành daemon” |
| `DetachCurrentThread` | “Có thể gọi khi vẫn còn Java call frames” |
| `JNI_OK` | “Có thể tiếp tục dùng JNIEnv sau Destroy” |
| Thread native chưa attach | “JVM sẽ tự join/đóng mọi tài nguyên của nó” |
| Shutdown hooks | “Luôn được gọi kể cả crash hoặc Runtime.halt” |
| Destroy thành công | “Chắc chắn tạo lại JVM mới trong cùng process được” |

## 13. Câu hỏi ôn tập và tình huống thực tế

**Câu 1.** JVM đã được host C tạo. Java có một non-daemon thread đang đợi `CountDownLatch.await()`. Host gọi `DestroyJavaVM` nhưng không ai mở latch. Điều gì xảy ra?

**Đáp án:** Lời gọi có thể chờ vô hạn vì thread non-daemon không kết thúc. Phải thiết kế lối thoát của worker và gửi tín hiệu trước khi host chờ shutdown.

**Câu 2.** Một native OS thread gọi `AttachCurrentThread` rồi chờ socket, không detach. Java threads đã thoát hết. `DestroyJavaVM` có chắc trả về không?

**Đáp án:** Không. Native thread **đã attach non-daemon** cũng nằm trong điều kiện chờ và cần hoàn tất/detach.

**Câu 3.** Gọi `AttachCurrentThreadAsDaemon` trên thread vốn đã attach bằng `AttachCurrentThread` có biến nó thành daemon không?

**Đáp án:** Không. Khi thread đã attach, lệnh attach tiếp không đổi daemon status.

**Câu 4.** `DestroyJavaVM` có buộc phải được gọi từ đúng thread đã gọi `JNI_CreateJavaVM` không?

**Đáp án:** Không theo Invocation API hiện đại. Tuy nhiên lời gọi phải có ngữ cảnh hợp lệ và thiết kế lifecycle đúng; không thực hiện khi còn Java methods trên call stack của thread gọi.

**Câu 5.** Sau `DestroyJavaVM` trả `JNI_OK`, có nên dùng `env->FindClass` và khởi tạo JVM mới trong cùng process?

**Đáp án:** Không. JNI interfaces cũ không còn hợp lệ; việc tạo lại hoặc nhiều VM trong một process không phải kịch bản được hỗ trợ đáng tin.

**Câu 6.** Một Java daemon thread còn ghi log thì JVM có chờ nó hoàn tất giống non-daemon không?

**Đáp án:** Không. Daemon không cản VM shutdown; muốn chắc log được flush phải có cơ chế dừng/đợi chủ động.

**Câu 7.** `DestroyJavaVM` chờ đến lúc không còn non-daemon thread khác. Nó có thể còn chờ điều gì?

**Đáp án:** Shutdown sequence, trong đó có shutdown hooks; các hook bị treo cũng có thể khiến VM không kết thúc.

**Câu 8.** Vì sao nên để native host sở hữu shutdown thay vì để Java callback gọi `DestroyJavaVM`?

**Đáp án:** Host có thể chờ cho Java call stack quay về, ngăn callback mới, phát stop và kiểm soát toàn bộ Java/native threads. Gọi Destroy ngay trong callback Java → native có ngữ cảnh stack không phù hợp và dễ tạo deadlock.

## 14. Tài liệu kỹ thuật

- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_CreateJavaVM`, `DestroyJavaVM`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, return code và giới hạn multiple VMs.
- [Oracle Java SE 21 — JNI Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html): diễn giải chi tiết hơn về ngữ cảnh thread gọi Destroy, non-daemon threads, shutdown sequence và native threads còn chạy khi VM kết thúc.
- [Java SE 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt` và shutdown hooks.
- [Java SE 17 — Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon status, `join` và `interrupt`.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ việc báo đã sẵn sàng và gửi tín hiệu dừng.
- [Java Virtual Machine Specification — JVM Termination](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.7): điều kiện kết thúc VM và khác biệt giữa daemon/non-daemon threads.

**Quy tắc cần nhớ:** Quản lý thread theo thứ tự **ngừng nhận việc → báo dừng → đợi Java non-daemon và native-attached workers hoàn tất/detach → rời khỏi Java call stack → gọi `DestroyJavaVM` → kiểm tra `JNI_OK`**. `DestroyJavaVM` là bước cuối của một giao thức shutdown, không phải công cụ sửa một giao thức shutdown đã bị treo.
