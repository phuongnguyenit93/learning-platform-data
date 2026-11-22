# Tra cứu JVM đã tạo và hiểu giới hạn nhiều JVM trong một tiến trình

## Kết quả cần đạt

Khi một chương trình **C/C++ nhúng Java Virtual Machine (JVM)**, nó cần phân biệt hai tình huống: JVM đã chạy bên trong tiến trình hay host đang cần khởi tạo JVM lần đầu. **JNI Invocation API** cung cấp `JNI_GetCreatedJavaVMs` để tìm các JVM đã được tạo **trong chính process đang gọi**. Dù API sử dụng mảng và tham số số lượng, **tạo nhiều JVM trong cùng một process không được hỗ trợ** theo đặc tả JNI của JDK 17.

Sau bài học, bạn sẽ hiểu chính xác chữ ký và kết quả của `JNI_GetCreatedJavaVMs`, cách tra cứu trước/sau `JNI_CreateJavaVM`, lựa chọn giữa `JavaVM *` và `JNIEnv *`, lý do class loaders/threads không phải các JVM khác nhau, và cách tổ chức host native khi nhiều thành phần cùng cần Java.

## 1. JVM nằm ở đâu khi được nhúng?

Tiến trình là đơn vị chạy do hệ điều hành quản lý với không gian địa chỉ và tài nguyên riêng. Một **native executable** có thể nạp runtime JVM, khởi tạo JVM bên trong **cùng một process**, rồi gọi Java code qua JNI.

~~~text
Process A: ứng dụng native host (PID minh họa 1001)
    |
    +-- mã C/C++, native libraries
    +-- một JVM được nhúng
    |      +-- Java heap và GC
    |      +-- các Java threads
    |      +-- nhiều class loaders / modules
    |      +-- Java classes của nhiều thành phần
    +-- native threads (attach JVM khi cần gọi JNI)

Process B: java -jar worker.jar (PID minh họa 1002)
    |
    +-- một JVM khác, thuộc process B
~~~

Hai process A và B có thể mỗi process có một JVM. `JNI_GetCreatedJavaVMs` chạy trong A **không thể** tìm JVM của B, vì API không phải công cụ liệt kê JVM toàn máy. Những công cụ như `jps`, `jcmd` hoặc danh sách tiến trình hệ điều hành phục vụ nhu cầu quan sát ngoài process và có quyền truy cập khác.

Phân biệt các khái niệm:

| Khái niệm | Nó là gì? | Có tạo thêm JVM độc lập không? |
| --- | --- | --- |
| Process | Không gian địa chỉ/lifecycle do hệ điều hành quản lý | Process riêng có thể chứa JVM riêng |
| JavaVM instance | Runtime Java được tạo qua launcher/Invocation API | Không thể tạo nhiều VM cùng process theo JNI/JDK 17 |
| Java thread | Luồng thực thi code trong JVM | Không |
| Class loader | Cơ chế nạp và phân biệt identity của classes | Không |
| Module layer | Cấu hình module trong cùng runtime Java | Không |
| JNI native library | Mã native được nạp hoặc liên kết với runtime | Không |

Một JVM có thể chạy nhiều Java applications về mặt logic, nhưng các ứng dụng đó vẫn dùng chung JVM runtime và một số tài nguyên toàn cục. Class loader không đồng nghĩa có heap, GC hoặc VM startup options riêng.

## 2. Invocation API: ba hàm dễ nhầm

Các prototype do `jni.h` khai báo:

~~~c
jint JNI_GetCreatedJavaVMs(JavaVM **vmBuf,
                           jsize bufLen,
                           jsize *nVMs);

jint JNI_CreateJavaVM(JavaVM **p_vm,
                      void **p_env,
                      void *vm_args);

jint JNI_GetDefaultJavaVMInitArgs(void *vm_args);
~~~

Đoạn trên **chỉ mô tả prototype**, không phải chương trình C độc lập và không cần định nghĩa lại các hàm.

- **`JNI_GetCreatedJavaVMs`** tìm những JVM đang được Invocation API báo cáo là đã tạo trong process.
- **`JNI_CreateJavaVM`** khởi tạo JVM mới và khi thành công điền `JavaVM *` cùng `JNIEnv *` của thread khởi tạo. Theo JNI, việc tạo nhiều JVM trong một process **không được hỗ trợ**.
- **`JNI_GetDefaultJavaVMInitArgs`** có mục đích lấy thông tin khởi tạo mặc định cho phiên bản JNI yêu cầu. Trên JDK hiện đại, gọi nó không phải tiền điều kiện bắt buộc trước `JNI_CreateJavaVM`.

Ba hàm ở trên được export từ runtime JVM và không nằm trong method table của `JavaVM *`. Sau khi đã có `JavaVM *vm` hợp lệ, ứng dụng gọi các hàm như `(*vm)->GetEnv(...)`, `(*vm)->AttachCurrentThread(...)` và `(*vm)->DestroyJavaVM(...)` thông qua interface này.

## 3. Đọc đúng `JNI_GetCreatedJavaVMs`

Chữ ký chuẩn là:

~~~c
jint JNI_GetCreatedJavaVMs(JavaVM **vmBuf,
                           jsize bufLen,
                           jsize *nVMs);
~~~

| Tham số | Ý nghĩa | Quy tắc sử dụng |
| --- | --- | --- |
| `vmBuf` | Vùng output để ghi các con trỏ `JavaVM *` | Cấp một buffer hợp lệ; theo đặc tả JDK 17 không truyền NULL |
| `bufLen` | Dung lượng buffer tính bằng **số phần tử** `JavaVM *` | Không nhầm với số byte hoặc `sizeof(buffer)` |
| `nVMs` | Output: **tổng số** JVM mà API báo cáo | Dùng `jsize count` và truyền `&count` để biết số lượng; spec cho phép NULL nếu không cần count |
| Giá trị trả về `jint` | Mã trạng thái | `JNI_OK` khi thành công; lỗi JNI là số âm; kiểm trước khi dùng outputs |

Ví dụ call tối thiểu:

~~~c
#include <jni.h>

JavaVM *found[1] = { NULL };
jsize total = 0;
jint rc = JNI_GetCreatedJavaVMs(found, 1, &total);

if (rc == JNI_OK && total == 1 && found[0] != NULL) {
    /* found[0] là JavaVM * hợp lệ được API báo cáo. */
}
~~~

Đây là **snippet** cần đặt trong một hàm C được liên kết với VM runtime. Nó cố tình cấp mảng một phần tử bởi JNI/JDK thông dụng chỉ hỗ trợ **một VM trong một process**.

Ba điểm cần hiểu rõ:

1. **`nVMs` là tổng số**, còn số phần tử thực tế được ghi vào `vmBuf` không vượt `bufLen`. Trường hợp tổng số lớn hơn dung lượng buffer phải kiểm tra giới hạn, không đọc quá mảng.
2. **`bufLen` tính theo số phần tử**. Với `JavaVM *found[1]`, `sizeof(found)` là kích thước tính theo byte. Dùng `1` hoặc biểu thức `sizeof found / sizeof found[0]`.
3. **`JNI_OK` không đồng nghĩa có VM**. Có thể thành công với `total == 0` khi process chưa có VM. Ngược lại, khi API trả mã lỗi thì không dùng `total` hay `found[0]` để quyết định điều gì.

Bảng diễn giải tình huống:

| Trạng thái trong cùng process | Khi tra cứu thành công, kết quả thông thường |
| --- | --- |
| Native host vừa khởi động, chưa tạo JVM | `total == 0`; không có VM pointer để sử dụng |
| JVM đã được tạo và đang tồn tại | `total == 1`; `found[0]` chứa `JavaVM *` khi buffer có ít nhất một slot |
| Muốn một VM thứ hai | Không được hỗ trợ; kích thước buffer không thay đổi giới hạn này |
| Tra cứu lỗi | Xử lý mã trả về, không tin output chưa được xác nhận |

### Kiểu pointer trong C có ý nghĩa gì?

`JavaVM *` là con trỏ tới Invocation API interface của một VM. `JavaVM **` là pointer tới một biến hoặc mảng chứa `JavaVM *`. Ví dụ:

~~~c
JavaVM *one = NULL;       /* một slot */
JavaVM *slots[1] = {0};   /* mảng một slot */

/* Cả &one và slots đều phù hợp về kiểu cho tham số vmBuf:
   JNI_GetCreatedJavaVMs(&one, 1, &count);
   JNI_GetCreatedJavaVMs(slots, 1, &count);
*/
~~~

Pointer `JavaVM *` không phải `jobject`: `jobject` là handle tới một **Java object** có quy tắc GC/reference khác; `JavaVM *` là interface của JVM. Với hai `JavaVM *` do cùng VM trả ra trong process, có thể so sánh các pointer đó trong ví dụ nhằm xác minh cùng VM. Không chuyển kết luận này thành quy tắc so sánh Java object bằng C pointer equality; với hai JNI object references, cần `IsSameObject`.

## 4. Thực hành đầy đủ: tra cứu VM trước và sau khi tạo

Ví dụ sau gồm **một Java class** và **một executable C**. Executable C phải chạy trong **fresh native process**, tra cứu để thấy 0 VM, tạo đúng 1 VM, tra cứu lại, kiểm tra VM pointer và gọi một Java method. **Không có** lời gọi tạo VM thứ hai.

### 4.1. Tệp Java `EmbeddedHello.java`

~~~java
public final class EmbeddedHello {
    private EmbeddedHello() {}

    public static void sayHello() {
        System.out.println("java-in-host=yes");
    }
}
~~~

Đây là class Java 17+ bình thường. Native host tìm nó từ classpath của JVM được nhúng; class sẽ được biên dịch trước khi chạy C executable.

### 4.2. Tệp C `JvmLookupDemo.c`

~~~c
#include <jni.h>
#include <stdio.h>

/* Trả mã lỗi JNI, đồng thời trả số VM và VM đầu tiên nếu có. */
static jint lookup(JavaVM **out_vm, jsize *out_count) {
    JavaVM *buffer[1] = { NULL };
    jsize count = 0;

    jint status = JNI_GetCreatedJavaVMs(buffer, 1, &count);
    if (status != JNI_OK) {
        return status;
    }
    *out_count = count;
    *out_vm = count > 0 ? buffer[0] : NULL;
    return JNI_OK;
}

int main(void) {
    JavaVM *existing = NULL;
    jsize count = -1;

    jint rc = lookup(&existing, &count);
    if (rc != JNI_OK) {
        fprintf(stderr, "first lookup failed: %d\n", (int) rc);
        return 1;
    }
    printf("before=%d\n", (int) count);

    if (count != 0) {
        fputs("Run this example in a fresh native process.\n", stderr);
        return 1;
    }

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    JavaVMOption options[1] = {
        { "-Djava.class.path=.", NULL }
    };
    JavaVMInitArgs args = {
        JNI_VERSION_1_8,
        1,
        options,
        JNI_FALSE
    };

    rc = JNI_CreateJavaVM(&vm, (void **) &env, &args);
    if (rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "create failed: %d\n", (int) rc);
        return 1;
    }

    existing = NULL;
    count = -1;
    rc = lookup(&existing, &count);
    if (rc != JNI_OK) {
        fprintf(stderr, "second lookup failed: %d\n", (int) rc);
        (*vm)->DestroyJavaVM(vm);
        return 1;
    }

    int same_vm = count == 1 && existing == vm;
    printf("after=%d\n", (int) count);
    printf("same-vm=%s\n", same_vm ? "yes" : "no");

    JNIEnv *thread_env = NULL;
    rc = (*vm)->GetEnv(vm, (void **) &thread_env, JNI_VERSION_1_8);
    int attached = rc == JNI_OK && thread_env != NULL;
    printf("thread-attached=%s\n", attached ? "yes" : "no");

    /* C stdio và System.out có buffer riêng: cố định thứ tự output. */
    fflush(stdout);

    int ok = same_vm && attached;
    if (ok) {
        jclass cls = (*env)->FindClass(env, "EmbeddedHello");
        if (cls == NULL) {
            (*env)->ExceptionDescribe(env);
            (*env)->ExceptionClear(env);
            ok = 0;
        } else {
            jmethodID method = (*env)->GetStaticMethodID(
                    env, cls, "sayHello", "()V");
            if (method == NULL) {
                (*env)->ExceptionDescribe(env);
                (*env)->ExceptionClear(env);
                ok = 0;
            } else {
                (*env)->CallStaticVoidMethod(env, cls, method);
                if ((*env)->ExceptionCheck(env)) {
                    (*env)->ExceptionDescribe(env);
                    (*env)->ExceptionClear(env);
                    ok = 0;
                }
            }
            (*env)->DeleteLocalRef(env, cls);
        }
    }

    rc = (*vm)->DestroyJavaVM(vm);
    if (rc != JNI_OK) {
        fprintf(stderr, "shutdown failed: %d\n", (int) rc);
        return 1;
    }
    return ok ? 0 : 1;
}
~~~

Cách hoạt động:

- `lookup` dùng `JNI_GetCreatedJavaVMs` và chỉ trả pointer sau khi status là `JNI_OK`. Buffer có một slot vì môi trường này hỗ trợ tối đa một VM đang chạy mỗi process.
- `JNI_CreateJavaVM` cấp VM interface và `JNIEnv *` của thread khởi tạo; tham số `(void **) &env` tuân theo chữ ký Invocation API.
- `count == 1 && existing == vm` xác nhận đối tượng VM tra cứu lại chính là VM vừa tạo. `GetEnv` xác nhận thread khởi tạo đang attached.
- `FindClass`/`GetStaticMethodID`/`CallStaticVoidMethod` gọi Java method thật và kiểm tra exceptions. `DeleteLocalRef` giải phóng JNI local reference tạo cho class.
- Cuối cùng `DestroyJavaVM` yêu cầu kết thúc JVM. Hàm này không biến một process đã từng có JVM thành môi trường có thể **khởi tạo JVM thứ hai** một cách được bảo đảm.

### 4.3. Biên dịch và chạy trên Linux

Yêu cầu **JDK 17+** và trình biên dịch C hỗ trợ C11, biến `JAVA_HOME` trỏ tới thư mục JDK có `include/jni.h` và `lib/server/libjvm.so`. Đặt hai tệp trong cùng thư mục và chạy ở thư mục đó:

~~~bash
javac -encoding UTF-8 EmbeddedHello.java

cc -std=c11 -Wall -Wextra -Werror \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  JvmLookupDemo.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o jvm-lookup-demo

./jvm-lookup-demo
~~~

Kết quả kỳ vọng khi mọi thao tác thành công trên một **fresh native process**:

~~~text
before=0
after=1
same-vm=yes
thread-attached=yes
java-in-host=yes
~~~

Để hiểu stdout: trước `JNI_CreateJavaVM`, API không thấy VM nào trong process. Sau tạo, API trả về một VM và pointer trùng VM đã tạo. Thread đang gọi `main` được attach; Java method chạy qua JNI. `fflush(stdout)` trước lời gọi Java giúp thứ tự các dòng C và Java được ổn định trong điều kiện chạy bình thường.

**Giới hạn môi trường:** lệnh linker dùng `libjvm.so`, include directory `linux` và rpath dành riêng cho Linux. Trên Windows/macOS cần chuyển đổi đường dẫn, tên thư viện, cờ linker và cơ chế tìm thư viện của hệ điều hành. Không suy đoán ABI bằng cách thay mỗi đuôi file. Ví dụ `JAVA_HOME` không đúng hoặc thiếu JVM runtime sẽ gây lỗi compile/link/load, **không** chứng minh `count == 0`.

## 5. Giới hạn quan trọng: không tạo nhiều JVM trong cùng process

Đặc tả *JNI Invocation API* của JDK 17 nêu rõ việc **tạo nhiều VM trong một process không được hỗ trợ** ở phần mô tả cả `JNI_GetCreatedJavaVMs` và `JNI_CreateJavaVM`. Hãy hiểu điều đó như **ràng buộc kiến trúc**:

- Một thư viện native/plugin muốn chạy Java không được tự ý tạo một JVM mới nếu host process đã có JVM.
- Việc `JNI_GetCreatedJavaVMs` có tham số `vmBuf` và `bufLen` chỉ nói API biết cách ghi **một danh sách kết quả**; nó không cam kết nhiều JVM được triển khai.
- Không cố gọi `JNI_CreateJavaVM` lần hai để lấy một mã lỗi “dự kiến”. Trong code thật, lỗi có thể tùy implementation/phiên bản; phải kiểm tra mã trả về mà không dựa trên giả định cụ thể.
- Tăng `bufLen` lên 2, 10 hay 100 không cho phép tạo thêm VMs.
- Nếu process B cũng có JVM, process A không thấy JVM đó qua Invocation API của A.
- Không coi số VM “đã tạo” là số Java classes, threads, class loaders hoặc modules.

### Một JVM, nhiều class loaders: không tương đương nhiều JVM

Java có thể tạo các class loaders riêng để phân tách namespace của classes, nhưng chúng vẫn chạy trên **cùng JVM instance**. Ví dụ Java 17+ độc lập:

~~~java
public final class LoaderScopeDemo {
    public static void main(String[] args) {
        ClassLoader first = new ClassLoader(null) {};
        ClassLoader second = new ClassLoader(null) {};
        System.out.println("two-loaders=" + (first != second));
    }
}
~~~

Lệnh:

~~~bash
javac LoaderScopeDemo.java
java LoaderScopeDemo
~~~

Stdout:

~~~text
two-loaders=true
~~~

Điều được chứng minh ở đây chỉ là hai class-loader objects khác nhau. Nó **không đếm JVM**. Class loaders chia sẻ runtime JVM, không cấp hai heaps/GCs/VM options độc lập.

Nếu thực sự cần hai JVM độc lập, giải pháp thông thường là **hai processes** (ví dụ hai lệnh `java` hoặc hai native hosts) trao đổi dữ liệu bằng IPC, socket, HTTP/gRPC hoặc message queues. Mỗi process có vòng đời, bộ nhớ và cấu hình JVM riêng; kết nối giữa chúng không dùng `JavaVM *` từ process kia.

## 6. Khi JVM đã tồn tại, lấy `JavaVM *` theo cách nào?

Không phải code nào cũng cần `JNI_GetCreatedJavaVMs`.

| Bạn đang ở đâu? | Cách lấy JVM hợp lý |
| --- | --- |
| Native host trước khi quyết định khởi tạo | `JNI_GetCreatedJavaVMs` |
| Native host vừa khởi tạo thành công | Giữ `JavaVM *` do `JNI_CreateJavaVM` trả về |
| Bên trong một JNI native method đã có `JNIEnv *env` | Gọi `(*env)->GetJavaVM(env, &vm)` |
| Trong hook thư viện JNI được JVM nạp | Nhận tham số `JavaVM *vm` từ `JNI_OnLoad` |

Ví dụ đoạn **JNI method fragment**, không phải C program độc lập:

~~~c
JavaVM *vm = NULL;
jint rc = (*env)->GetJavaVM(env, &vm);
if (rc != JNI_OK || vm == NULL) {
    /* Trả lỗi theo hợp đồng của native method. */
}
~~~

Và hook trong JNI shared library:

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;
    /* VM đã tồn tại và được runtime truyền cho thư viện. */
    (void) vm;
    return JNI_VERSION_1_8;
}
~~~

`JNI_OnLoad` chỉ được runtime gọi khi thư viện JNI được load đúng quy tắc; hook không tự tạo JVM. Trong mã thư viện thật, hãy quản lý lifetime của `vm` và mọi resources liên quan.

### `JavaVM *` khác `JNIEnv *`

`JavaVM *` đại diện VM interface và có thể được chia sẻ giữa native threads khi JVM còn sống. `JNIEnv *` là JNI interface **riêng của thread hiện tại**. Khi một thread native mới muốn gọi Java code, nó phải có `JNIEnv *` của **chính thread đó**, ví dụ:

~~~c
/* Snippet: vm là JavaVM * hợp lệ. */
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **) &env, JNI_VERSION_1_8);

if (rc == JNI_EDETACHED) {
    rc = (*vm)->AttachCurrentThread(vm, (void **) &env, NULL);
    if (rc == JNI_OK) {
        /* Thread vừa được attach: dùng env cho JNI work. */
        (*vm)->DetachCurrentThread(vm);
    } else {
        /* Xử lý lỗi attach, không gọi JNI qua env NULL. */
    }
} else if (rc == JNI_OK) {
    /* Thread đã attached: dùng env; không tự detach của owner khác. */
} else {
    /* Có thể JNI_EVERSION hoặc lỗi khác. */
}
~~~

Đây là đoạn giải thích luồng, chưa phải hàm độc lập. Trong thực tế phải cleanup đúng đường thành công/lỗi, không detach khi Java frames vẫn trên stack. `GetEnv` trả `JNI_EDETACHED` trên thread chưa attach **không có nghĩa process chưa có JVM**. Chỉ cho thấy thread này chưa có JNI environment.

**Không** copy `JNIEnv *` của thread A sang thread B, và không dùng kết quả tra cứu `JavaVM *` như thể nó là `JNIEnv *`. Các native threads có thể dùng cùng VM nhưng có JNI environments riêng.

## 7. Tra cứu và tạo JVM có nguy cơ race

Hai native components cùng process có thể làm:

~~~text
Thread A: lookup -> count 0
Thread B: lookup -> count 0
Thread A: JNI_CreateJavaVM(...)
Thread B: JNI_CreateJavaVM(...)    // cố tạo lần thứ hai: unsupported
~~~

Đây là tình huống điển hình của **check-then-act race**. `JNI_GetCreatedJavaVMs` là thao tác tra cứu; nó **không cung cấp mutex toàn ứng dụng** và không làm cặp lookup/create thành nguyên tử. Kiến trúc đúng cần một **owner duy nhất** để khởi tạo và shutdown JVM, phối hợp các components qua lock hoặc một state machine đồng bộ.

Ví dụ các trạng thái thiết kế:

~~~text
NOT_STARTED -> INITIALIZING -> RUNNING -> SHUTTING_DOWN -> TERMINATED
        |            |
        |            +-- khởi tạo lỗi -> FAILED
        +-- thấy VM hiện có -> RUNNING (sau khi xác định ownership)
~~~

Một thread chịu trách nhiệm transition từ `NOT_STARTED` sang `INITIALIZING`. Các threads khác chờ/quy về một VM đã được tạo theo hợp đồng host. **Không** gọi `JNI_CreateJavaVM` từ từng plugin. Nếu lookup thấy VM có sẵn do thành phần khác tạo, phải xác định **ai sở hữu JVM** và ai được phép shutdown; việc thấy pointer không tự cấp quyền sở hữu lifecycle.

### Startup options không được thay như tạo VM mới

Ví dụ host đã khởi tạo JVM với heap option `-Xmx` hoặc classpath. Plugin đến sau không thể thay các tùy chọn khởi tạo ấy bằng cách “tra cứu rồi tạo VM thứ hai”. Một JVM đang chạy có cấu hình startup của lần init ban đầu. Các thành phần phải dùng cấu hình host cung cấp, hoặc chuyển workload cần cấu hình JVM khác sang process riêng.

## 8. Shutdown không phải cơ chế restart JVM được bảo đảm

Sau khi có `JavaVM *vm`, host có thể yêu cầu shutdown bằng:

~~~c
/* Snippet: vm phải đang hợp lệ và caller là lifecycle owner. */
jint rc = (*vm)->DestroyJavaVM(vm);
if (rc != JNI_OK) {
    /* Xử lý lỗi shutdown. */
}
~~~

Theo Invocation API, shutdown phải xem xét các Java threads và native threads đã attach; `DestroyJavaVM` có thể chờ khi những **non-daemon user threads** còn chạy. Thư viện native không nên tự shutdown VM khi các thành phần khác vẫn đang sử dụng.

**Không suy ra rằng gọi `DestroyJavaVM` xong sẽ có thể `JNI_CreateJavaVM` lại trong cùng process.** Đặc tả JDK 17 ghi hạn chế về VM unloading; ngay cả khi shutdown trả về thành công trên một implementation, JNI không bảo đảm một chu trình create–destroy–recreate mới trong một process được hỗ trợ. Nếu cần môi trường JVM sạch hoàn toàn, **kết thúc process và tạo process mới**.

Các rủi ro khác khi xem JVM như thứ có thể bật/tắt tùy ý: global JNI references và native callbacks chưa dọn, native threads chưa detach, class loader/native library resources và external services còn phụ thuộc runtime. Owner phải định nghĩa trình tự shutdown của hệ thống.

## 9. Quy trình quyết định cho native host

~~~text
Native host cần Java
    |
    v
Tra cứu bằng JNI_GetCreatedJavaVMs
    |
    +-- rc != JNI_OK --> báo lỗi; không dùng output
    |
    +-- count == 1 --> nhận JavaVM * hiện có
    |                   xác minh owner + trạng thái RUNNING
    |
    +-- count == 0 --> owner duy nhất cân nhắc JNI_CreateJavaVM
                        nếu rc == JNI_OK, giữ JavaVM * cho host
                        nếu lỗi, báo nguyên nhân; không giả định VM đã tạo
    |
    v
Native threads lấy JNIEnv * riêng qua GetEnv/AttachCurrentThread
    |
    v
Gọi Java/JNI trong phạm vi runtime còn hợp lệ
    |
    v
Lifecycle owner điều phối shutdown một lần khi hệ thống kết thúc
~~~

**Nếu API trả tổng count lớn hơn 1** trên một môi trường/implementation đặc biệt, đừng áp logic tự động lựa chọn VM tùy ý vào mã được thiết kế cho JDK 17 phổ biến. Điều đó nằm ngoài hợp đồng hỗ trợ nhiều JVM trong một process; hãy xem đây là môi trường ngoài giả định, xác minh tài liệu/runtime và từ chối vận hành nếu chưa có thiết kế chính xác.

## 10. Lỗi thường gặp và cách khắc phục

| Lỗi hoặc suy đoán | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Có mảng `JavaVM **` nên tạo được nhiều JVM” | Đụng giới hạn unsupported multiple VMs | Một JVM mỗi process; dùng process khác khi cần runtime độc lập |
| Truyền `sizeof(buffer)` cho `bufLen` | Kích thước tính byte, không phải số phần tử | Dùng `sizeof(buffer) / sizeof(buffer[0])` |
| Đọc `found[0]` khi `count == 0` | Đọc slot chưa mang VM hợp lệ | Kiểm `JNI_OK`, count và buffer trước |
| Bỏ qua return code của lookup/create | Xử lý output chưa xác minh | Dừng và báo mã JNI lỗi |
| Coi `count == 0` là lời hứa create thành công | Race, thiếu tài nguyên, sai VM options | Dùng owner/lock, kiểm return của create |
| Dùng `JNIEnv *` từ thread khác | Vi phạm tính theo thread của JNI environment | `GetEnv` hoặc attach đúng thread |
| Gọi `JNI_CreateJavaVM` từ plugin được Java load | Đang cố tạo JVM thứ hai | Nhận VM trong `JNI_OnLoad` hoặc `GetJavaVM` |
| Lưu `JavaVM *` rồi dùng sau Destroy | VM interface hết vòng đời được phép dùng | Ràng buộc lifetime theo lifecycle owner |
| Cố gọi Destroy–Create để “reset JVM” | Restart trong process không được bảo đảm | Tạo process mới cho runtime mới |
| Dùng count để đo Java threads hoặc class loaders | Hai loại đối tượng khác nhau | Dùng các API/metrics đúng cấp độ |
| Dùng JNI lookup để tìm JVM của process khác | API scope theo process | Dùng OS tools để quan sát, IPC để tương tác |
| Plugin tự Destroy JVM host đang sử dụng | Có thể làm hỏng toàn bộ host | Chỉ lifecycle owner được shutdown |

### Phân tích vài tình huống

**Trường hợp A: `count == 1` nhưng `GetEnv` báo `JNI_EDETACHED`.** Hai kết quả có thể hoàn toàn đúng cùng lúc: JVM tồn tại trong process, còn thread đang gọi chưa được attach. Cần lấy `JNIEnv *` bằng `AttachCurrentThread`, không tạo VM khác.

**Trường hợp B: executable C link lỗi `undefined reference to JNI_CreateJavaVM`.** Chỉ include `jni.h` chưa đủ: executable phải link tới implementation JNI Invocation API trong VM runtime (ví dụ `libjvm.so` với JDK/Linux tương ứng). Đây là lỗi build/link, không cho biết process có JVM hay không.

**Trường hợp C: C executable chạy được nhưng `FindClass` không tìm thấy Java class.** Kiểm tra classpath truyền qua `JavaVMInitArgs`, vị trí chạy executable và `javac` đã tạo `.class`. Đừng tạo JVM khác chỉ để đổi classpath; cần cấu hình owner chính xác lúc init hoặc dùng class-loading strategy có hợp đồng.

**Trường hợp D: Native plugin trong ứng dụng Java đã có `JNIEnv *env`.** Cách lấy VM trực tiếp bằng `GetJavaVM` từ JNI environment hoặc tham số `JNI_OnLoad` thường thích hợp hơn một lần enumeration. Plugin không tạo VM thứ hai.

**Trường hợp E: Muốn 2 workloads có `-Xmx` khác nhau và GC độc lập.** Class loaders/threads trong cùng JVM không đáp ứng cách ly VM như vậy. Hai processes với hai runtime configs là lựa chọn thích hợp; trao đổi dữ liệu qua IPC/network.

## 11. Câu hỏi tự kiểm tra

**1.** `JNI_GetCreatedJavaVMs` trả `JNI_OK` và `nVMs == 0`. Điều đó có nghĩa là JVM chưa được báo cáo trong process, hay máy tính không có JVM?

**Đáp án:** Chỉ nói về **process hiện tại**. Máy có thể có các Java processes khác.

**2.** Buffer `JavaVM *vms[1]` cần `bufLen` bằng bao nhiêu? Có dùng `sizeof(vms)` không?

**Đáp án:** Bằng **1** hoặc `sizeof vms / sizeof vms[0]`. `sizeof(vms)` tính bằng byte.

**3.** Vì sao prototype nhận danh sách mà vẫn không được gọi `JNI_CreateJavaVM` hai lần trong cùng process?

**Đáp án:** Signature chung không hứa khả năng triển khai nhiều VM; đặc tả JNI/JDK 17 nói rõ **multiple VMs in one process unsupported**.

**4.** Có VM nhưng native worker thread gọi `GetEnv` được `JNI_EDETACHED`; xử lý?

**Đáp án:** Thread này chưa attach. Gọi `AttachCurrentThread`, dùng `JNIEnv *` được trả riêng cho thread, rồi detach khi công việc kết thúc nếu chính code này là owner attach.

**5.** Hai class loaders có đồng nghĩa hai JVM không?

**Đáp án:** Không. Cùng JVM vẫn có thể có nhiều class loaders với class identity khác nhau.

**6.** `DestroyJavaVM` thành công có cho phép chắc chắn tạo lại VM trong cùng process không?

**Đáp án:** Không. Không có bảo đảm restart/recreate JVM trong cùng process từ Invocation API; nếu cần JVM mới sạch, tạo process mới.

**7.** Một thư viện JNI được Java launcher load cần JVM; dùng `JNI_CreateJavaVM` hay `JNI_OnLoad`/`GetJavaVM`?

**Đáp án:** JVM đã tồn tại; nên dùng `JNI_OnLoad(JavaVM *vm,...)` hoặc `(*env)->GetJavaVM` từ native method đang chạy.

**8.** Tại sao `JNI_GetCreatedJavaVMs` không thể cho ứng dụng native trong process A điều khiển JVM process B?

**Đáp án:** Nó chỉ báo các VM trong process A. `JavaVM *` là pointer thuộc process, không phải handle điều khiển JVM qua ranh giới hệ điều hành; cần IPC/network khi tương tác giữa processes.

## Checklist thực hành

- [ ] Phân biệt process, JVM, Java thread và class loader.
- [ ] `JNI_GetCreatedJavaVMs` nhận buffer `JavaVM *` hợp lệ, `bufLen` tính theo số phần tử, `nVMs` là `jsize *`.
- [ ] Kiểm `JNI_OK`, count và giới hạn buffer trước khi dùng pointer.
- [ ] Chỉ có một owner thực hiện khởi tạo JVM và điều phối lookup/create để tránh race.
- [ ] Khi JVM đã tồn tại, tái sử dụng VM hợp lệ; không tạo JVM thứ hai trong process.
- [ ] Chỉ dùng `JNIEnv *` trên đúng thread; kiểm `JNI_EDETACHED` và attach/detach theo ownership.
- [ ] Thiết lập classpath, JNI version và VM startup options trước khi tạo JVM.
- [ ] Shutdown theo owner, không dựa vào khả năng Destroy–Create trong process.
- [ ] Khi cần nhiều JVM độc lập, thiết kế nhiều processes và giao thức liên tiến trình.
- [ ] Kiểm chứng build/run đúng OS, JDK, compiler, ABI mục tiêu; không suy từ prototype sang một hỗ trợ chưa có.

## Tài liệu chính thức

- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): các mục `JNI_GetCreatedJavaVMs`, `JNI_CreateJavaVM`, `DestroyJavaVM`, `GetEnv`, `AttachCurrentThread` và giới hạn nhiều JVM trong process.
- [Oracle Java SE 17 — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JavaVM`, `JNIEnv`, `jint`, `jsize`.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): thao tác JNI từ môi trường thread đang attached.
- [Oracle Java SE 17 — Java Compiler](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): biên dịch chương trình Java mẫu.

**Ghi nhớ:** `JNI_GetCreatedJavaVMs` chỉ **tra cứu JVM của process hiện tại**. Dùng đúng `JavaVM *` để quản lý VM, `JNIEnv *` riêng cho từng thread, một lifecycle owner cho process, và tạo **process khác** nếu cần một JVM độc lập.
