# Phân biệt JavaVM dùng để truy cập JVM với JNIEnv riêng của từng luồng trong JNI

## Mục tiêu học tập

Trong Java Native Interface (JNI), **JavaVM** và **JNIEnv** đều là kiểu giao diện để mã native làm việc với Java Virtual Machine, nhưng **phạm vi sử dụng, chức năng và vòng đời của chúng khác nhau**. Nhầm lẫn hai kiểu có thể dẫn đến lỗi truy cập sai luồng, tham chiếu không hợp lệ, JNI crash, khó xử lý callback bất đồng bộ hoặc khiến tiến trình không thoát.

Sau bài này, bạn có thể:

1. Giải thích vai trò của **JavaVM \*** như một handle cấp JVM và **JNIEnv \*** như giao diện JNI của **luồng đang chạy**.
2. Xác định nguồn nhận JavaVM/JNIEnv: tham số native method, **JNI_OnLoad**, **GetJavaVM**, **GetEnv** và **AttachCurrentThread**.
3. Phân biệt luồng do **Java tạo ra** với luồng **native tạo ra**; biết lúc nào phải attach và detach.
4. Xử lý đúng các trạng thái **JNI_OK**, **JNI_EDETACHED** và **JNI_EVERSION**.
5. Thiết kế callback từ native thread về Java với **JNIEnv đúng luồng**, reference hợp lệ, class loader rõ ràng và cleanup đầy đủ.
6. Chạy ví dụ Java 17+ kết hợp C/JNI trên Linux/macOS để thấy cả luồng Java và luồng pthread native sử dụng cùng JavaVM nhưng phải lấy JNIEnv trong từng luồng.

## 1. Mô hình tư duy: một JVM, nhiều luồng, mỗi luồng một môi trường JNI hợp lệ

Giả sử ứng dụng Java gọi một thư viện C. JVM đang quản lý nhiều Java thread, còn thư viện C có thể tự tạo các luồng của hệ điều hành để xử lý công việc. Cần nhìn ranh giới JNI theo hai tầng:

~~~text
                 JVM đang hoạt động
                 JavaVM* (giao diện cấp VM)
                         |
        +----------------+----------------+
        |                |                |
 Java thread A      Java thread B    Native pthread C
  đang attached      đang attached     ban đầu DETACHED
        |                |                |
  JNIEnv* A         JNIEnv* B       AttachCurrentThread
        |                |                |
  Gọi JNI API       Gọi JNI API        JNIEnv* C
                                         |
                                    Gọi JNI API
                                         |
                                   DetachCurrentThread
~~~

**JavaVM \*** có thể được giữ ở vùng native có vòng đời được quản lý và chia sẻ giữa những luồng cần kết nối với **cùng JVM**. Nó cung cấp các thao tác cấp máy ảo như **GetEnv**, **AttachCurrentThread**, **AttachCurrentThreadAsDaemon** và **DetachCurrentThread**.

**JNIEnv \*** là giao diện để **luồng hiện tại** gọi các chức năng JNI: tra class, tạo String, đọc/ghi field, gọi Java method, kiểm tra exception và quản lý Java references. Một con trỏ JNIEnv **chỉ hợp lệ trong luồng đã nhận nó**. Tuyệt đối không chuyển con trỏ đó sang một luồng khác dù hai luồng chạy cùng tiến trình.

Đây là khác biệt về **hợp đồng luồng**, không chỉ khác tên kiểu dữ liệu. Việc hai con trỏ có trông giống nhau hay trỏ vào cùng một bảng hàm trên một JVM cụ thể không làm chúng có thể dùng thay thế tùy ý.

### Bảng so sánh cốt lõi

| Tiêu chí | **JavaVM \*** | **JNIEnv \*** |
| --- | --- | --- |
| Đại diện | Giao diện cấp một JVM hiện hữu | Giao diện JNI hợp lệ cho **luồng hiện tại** |
| Phạm vi | Dùng để quản lý việc tiếp cận VM từ các luồng | **Chỉ dùng trong luồng đã nhận** |
| Cách nhận | **JNI_OnLoad(vm, ...)** hoặc **env->GetJavaVM** (cú pháp C++), Invocation API | Tham số đầu của native method; **vm->GetEnv** khi đã attached; **AttachCurrentThread** khi cần attach |
| API đặc trưng | **GetEnv**, **AttachCurrentThread**, **DetachCurrentThread** | **FindClass**, **NewStringUTF**, **GetFieldID**, **CallVoidMethod**, **ExceptionCheck**... |
| Có thể chia sẻ giữa thread? | **Có**, trong vòng đời và phạm vi đúng của VM | **Không** |
| Có thể lưu toàn cục? | Có thể cache với kiểm soát vòng đời thư viện/VM | **Không cache toàn cục để dùng bởi nhiều thread** |
| Khi native thread chưa attached | Có thể dùng JavaVM để hỏi/truy cập bước attach | **Chưa có JNIEnv hợp lệ** để gọi API JNI |
| Khi native thread detach | JavaVM vẫn tồn tại nếu VM còn sống | JNIEnv của luồng đã detach **không được dùng tiếp** |

**JavaVM không phải java.lang.Thread**, và **JNIEnv không phải một đối tượng Java** có thể đưa vào ThreadLocal của Java để thay thế toàn bộ hợp đồng JNI. Chúng là native interface types do JVM cung cấp.

## 2. Vì sao JNIEnv gắn với luồng?

JNIEnv là con trỏ tới một cấu trúc giao diện các hàm JNI. JVM có thể gắn thêm **dữ liệu đặc thù từng luồng** vào môi trường đó: trạng thái ngoại lệ đang pending, local references, các dữ liệu phục vụ chuyển đổi Java–native và cơ chế runtime khác.

Vì vậy:

- Khi Java thread A gọi native method, JVM truyền một **JNIEnv hợp lệ cho A**.
- Khi Java thread B gọi cùng native method, JVM truyền một **JNIEnv hợp lệ cho B**.
- Code native gọi **GetEnv** trên JavaVM trong A chỉ lấy lại môi trường **của A**, không lấy môi trường của B.
- Một con trỏ JNIEnv từ A không được đặt trong biến global rồi dùng từ B.
- Native thread C phải có trạng thái attached trước khi gọi các hàm qua JNIEnv; **GetEnv không tự attach**.

JNI Specification bảo đảm một native method được gọi lặp lại **trên cùng Java thread** nhận cùng JNI interface pointer. Tuy nhiên, không nên viết thuật toán phụ thuộc vào địa chỉ số của JNIEnv để định danh một thread; hãy dùng cơ chế thread identity và synchronization thực sự.

### Hai chữ ký C thường gặp

~~~c
/* Native method được gọi từ Java. */
JNIEXPORT void JNICALL
Java_Demo_nativeOperation(JNIEnv *env, jobject self) {
    /* env hợp lệ trong luồng đang thực thi method này. */
    (void)self;
}

/* Hook khi thư viện JNI được JVM nạp. */
JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
~~~

Đây là **hai đoạn mô tả chữ ký**, không phải chương trình JNI độc lập. Native method instance nhận **JNIEnv \*** và **jobject self**; nếu phương thức Java khai báo **static native**, tham số thứ hai là **jclass**, không phải jobject của một instance.

**JNI_OnLoad** được truyền JavaVM, trong khi native method thường được truyền JNIEnv. Hai điểm vào bổ sung nhau: JavaVM giúp xác định VM/attach thread, JNIEnv giúp thực hiện API Java cụ thể trên thread đang attached.

### C và C++ khác cú pháp, không khác quy tắc thread

Trong **C**:

~~~c
JavaVM *vm = NULL;
jint status = (*env)->GetJavaVM(env, &vm);
~~~

Trong **C++** có thể viết:

~~~cpp
JavaVM *vm = nullptr;
jint status = env->GetJavaVM(&vm);
~~~

Đây là các snippet tương đương về mặt API. Cú pháp C thường lặp lại **env** làm đối số đầu; cú pháp C++ dùng inline member functions. Dù dùng ngôn ngữ nào, **JNIEnv vẫn là thread-specific** và JavaVM vẫn có thể được dùng để lấy/attach môi trường trong mỗi luồng.

## 3. Nhận JavaVM đúng cách

### 3.1. JNI_OnLoad: lấy VM tại thời điểm nạp thư viện

Một thư viện được nạp bởi **System.loadLibrary** có thể export **JNI_OnLoad**:

~~~c
#include <jni.h>

static JavaVM *g_vm = NULL;

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    g_vm = vm;
    return JNI_VERSION_1_6;
}
~~~

**g_vm** giữ handle JVM để các native worker được khởi tạo về sau có thể dùng. **JNI_OnLoad** trả lại phiên bản JNI tối thiểu mà thư viện yêu cầu; ví dụ yêu cầu JNI 1.6, được các JDK 17+ hỗ trợ.

Lưu ý:

1. Lưu handle JavaVM trong một biến global có thể hợp lệ **trong vòng đời JVM/thư viện**. Không dùng nó sau khi VM đã kết thúc.
2. Chỉ dùng **g_vm** khi đã nạp thư viện thành công và quy trình khởi tạo bảo đảm giá trị đã sẵn sàng. Khi có nhiều native worker, quản lý thời điểm spawn/stop và synchronization phù hợp.
3. Nếu thư viện hỗ trợ unload/hot reload, phải dừng worker và giải phóng reference/cache trước khi thư viện bị unload; không để thread chạy code từ thư viện đã biến mất.
4. **JNI_OnLoad** không phải nơi tạo và giữ một JNIEnv chung để phát cho tất cả thread.

### 3.2. GetJavaVM: lấy VM từ JNIEnv hiện tại

Trong native method đã nhận **JNIEnv \*** hợp lệ:

~~~c
JavaVM *vm = NULL;

jint status = (*env)->GetJavaVM(env, &vm);
if (status != JNI_OK || vm == NULL) {
    return; /* Ví dụ nằm trong một native method void. */
}

/* Lưu hoặc truyền vm theo lifecycle phù hợp. */
~~~

**GetJavaVM** trả về JavaVM liên kết với JNIEnv hiện tại. Nếu chỉ cần VM từ một Java callback rồi chuyển thông tin đó cho native worker, đây là hướng đúng. Hướng ngược lại không dùng phép ép kiểu: muốn có JNIEnv từ JavaVM, gọi **GetEnv** hoặc attach thread theo điều kiện.

**Sai:**

~~~c
/* CỐ Ý SAI: không được xem JavaVM như JNIEnv. */
JNIEnv *wrong = (JNIEnv *)vm;
/* Không gọi JNI API trên wrong. */
~~~

Các kiểu con trỏ không có hợp đồng layout để hoán đổi. Phép ép kiểu C khiến compiler có thể chấp nhận câu lệnh, nhưng thực thi như vậy vi phạm JNI và có thể làm crash JVM.

## 4. Nhận JNIEnv đúng cách: ba tình huống

### 4.1. Thread do Java tạo, hiện đang gọi native method

JVM **đã attach** Java thread. Native method được truyền JNIEnv hợp lệ:

~~~c
JNIEXPORT jboolean JNICALL
Java_Demo_isAttached(JNIEnv *env, jclass type) {
    (void)type;
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return JNI_FALSE;
    }

    JNIEnv *again = NULL;
    jint result = (*vm)->GetEnv(
        vm, (void **)&again, JNI_VERSION_1_6
    );

    return (result == JNI_OK && again == env)
            ? JNI_TRUE : JNI_FALSE;
}
~~~

Đây là **snippet** trong lớp Demo có khai báo **static native boolean isAttached()**. Lệnh GetEnv trả về môi trường của đúng Java thread đang gọi; không cần gọi **AttachCurrentThread**.

**Không gọi DetachCurrentThread ngay trong native method được Java gọi**. Thông thường thread này vẫn có Java frames trên stack, và nó không thuộc quyền lifecycle của đoạn mã native đó. Muốn tiếp tục gọi Java sau khi native method trả về, JVM vẫn cần thread này attached.

### 4.2. Thread native chưa attach

Một thread được tạo bằng **pthread_create** (Linux/macOS), thread API của Windows hoặc thread pool trong native library thường bắt đầu ở trạng thái **JNI_EDETACHED** đối với JVM, dù cùng tiến trình:

~~~c
JNIEnv *env = NULL;
jint status = (*vm)->GetEnv(
    vm, (void **)&env, JNI_VERSION_1_6
);

if (status == JNI_EDETACHED) {
    if ((*vm)->AttachCurrentThread(
            vm, (void **)&env, NULL) != JNI_OK) {
        return; /* Chưa có JNIEnv hợp lệ. */
    }

    /* Từ đây env thuộc thread native hiện tại. */
    /* Gọi Java/JNI, giải phóng local refs và xử lý exception. */

    (*vm)->DetachCurrentThread(vm);
} else if (status == JNI_OK) {
    /* Thread đã attached; dùng env, không sở hữu việc detach. */
} else {
    /* JNI_EVERSION hoặc một lỗi khác: xử lý rõ ràng. */
}
~~~

Đây là snippet minh họa trong một **native worker**, giả định biến **JavaVM *vm** hợp lệ. Khi attach thành công, luồng native trở thành một thread có thể sử dụng JNI và Java. Nó phải detach **trước khi chính luồng đó kết thúc**; lời gọi detach không được thực hiện trên thread khác.

### 4.3. Thread native đã attach trước đó

**GetEnv** trả **JNI_OK** và JNIEnv của chính luồng đó. **AttachCurrentThread** gọi lại trên luồng đã attached sẽ trả về môi trường hiện tại mà không thực hiện một attach mới. Tuy nhiên, không nên suy luận rằng caller vừa gọi Attach thì luôn được quyền Detach.

Hãy theo dõi rõ **ownership**:

- Nếu **GetEnv == JNI_EDETACHED**, code của bạn gọi attach thành công: đánh dấu **attachedHere = true**, rồi detach trong nhánh cleanup của cùng worker.
- Nếu **GetEnv == JNI_OK**, luồng đã được người khác/JVM attach: **attachedHere = false**; sử dụng env hợp lệ rồi trả về, không detach một luồng bạn không sở hữu.
- Nếu **GetEnv == JNI_EVERSION**, JVM không hỗ trợ phiên bản JNI bạn yêu cầu; **không suy đoán** nó chỉ đơn giản là chưa attached.
- Với trạng thái khác, xử lý lỗi cụ thể thay vì truy cập một **env == NULL**.

## 5. GetEnv, AttachCurrentThread và DetachCurrentThread

### 5.1. GetEnv chỉ kiểm tra trạng thái và lấy môi trường hiện hành

Chữ ký C (từ bảng JavaVM):

~~~c
jint GetEnv(JavaVM *vm, void **env, jint version);
~~~

| Kết quả | Ý nghĩa | Hành động |
| --- | --- | --- |
| **JNI_OK** | Luồng hiện tại đã attached và phiên bản được hỗ trợ | Dùng **JNIEnv** vừa nhận trên **luồng này** |
| **JNI_EDETACHED** | Luồng hiện tại chưa attached | Nếu thật sự cần Java, gọi **AttachCurrentThread** hoặc daemon variant |
| **JNI_EVERSION** | Phiên bản JNI yêu cầu không được hỗ trợ | Xem lại hợp đồng phiên bản; không sử dụng env |
| Lỗi khác | Hoạt động không thành công | Không tiếp tục với env không được xác nhận |

**GetEnv không “lấy JNIEnv của thread khác”** và không nhận thread ID. Không có API chuẩn kiểu **GetEnv(vm, javaThreadId)**.

### 5.2. AttachCurrentThread và AttachCurrentThreadAsDaemon

~~~c
JNIEnv *env = NULL;
jint code = (*vm)->AttachCurrentThread(
    vm, (void **)&env, NULL
);
~~~

Khi thành công, native thread được attach như **non-daemon Java thread**. Có thể dùng **AttachCurrentThreadAsDaemon** nếu worker được thiết kế là daemon.

Điểm quan trọng: **daemon status** quyết định ảnh hưởng của thread lên cơ chế chờ kết thúc JVM, không làm cho JNI reference hoặc callback tự động an toàn. Một native worker non-daemon không kết thúc/detach có thể khiến JVM tiếp tục chờ khi shutdown; worker daemon không nên mặc định được bỏ qua lifecycle cleanup.

Nếu thread đã attached, gọi AttachCurrentThread hoặc AttachCurrentThreadAsDaemon lần nữa **không chuyển đổi daemon status** của nó. Vì vậy chọn daemon/non-daemon ở thời điểm attach có chủ đích, và ghi rõ tiến trình cần chờ thread kết thúc hay không.

**JavaVMAttachArgs** cho phép đặt tên và thread group trong ngữ cảnh hợp lệ, với field như **version**, **name** (modified UTF-8) và **group**. Không phải mọi ứng dụng đều cần tùy chọn này; **NULL** dùng giá trị mặc định trong ví dụ.

### 5.3. DetachCurrentThread: gọi trên chính thread được attach

~~~c
jint code = (*vm)->DetachCurrentThread(vm);
~~~

Native thread tự attach cần gọi detach sau khi đã:

1. Hoàn tất mọi lời gọi Java callback và không còn Java method đang trên stack của thread đó.
2. Dọn các local/global reference do chính nó sở hữu theo quy trình quản lý dữ liệu.
3. Xử lý các pending Java exception phát sinh trong callback, vì không có Java caller tự nhiên để nhận exception từ một native background thread.
4. Thoát khỏi critical regions/locks và các trạng thái JNI yêu cầu cleanup khác.

JNI không cho thread detach khi vẫn có **Java methods trên call stack**. Sau khi detach, con trỏ JNIEnv cũ là **không hợp lệ**. Nếu thread lại cần dùng JNI sau này, phải GetEnv/Attach lại, nhận một JNIEnv hợp lệ mới.

**Không gọi DetachCurrentThread “giùm” thread khác.** Hàm hoạt động trên **luồng hiện tại**.

## 6. Cấp VM và cấp thread không tương đương cấp reference

Một lỗi thiết kế đi kèm với việc lưu JNIEnv toàn cục là **lưu Java local references rồi gửi sang worker thread**.

| Thứ cần giữ | Có thể chia sẻ? | Vòng đời hợp lệ |
| --- | --- | --- |
| **JavaVM \*** | Có thể truyền giữa thread | Trong JVM lifecycle |
| **JNIEnv \*** | Không | Chỉ thread đã nhận nó, khi còn attached |
| **jobject/jclass/jstring local reference** | Không được truyền qua thread | Chỉ thread đã tạo/nhận và local scope tương ứng |
| **global reference** tạo bằng NewGlobalRef | Có thể dùng từ thread attached khác | Cho đến khi DeleteGlobalRef; còn phải bảo vệ đồng thời ở mức Java |
| **jmethodID/jfieldID** | Metadata ID, không phải Java object reference | Chỉ trong vòng đời class tương ứng; class unloading cần được xét |

### Ví dụ chuyển callback đúng cách

Giả sử Java truyền một Runnable vào native method, nhưng C muốn gọi **Runnable.run()** trên một worker sau khi native method ban đầu đã trả về.

**Sai:** lưu nguyên **jobject callback** vốn là local reference rồi dùng trên worker native. Reference có thể hết hạn khi JNI method kết thúc và vốn không hợp lệ trên thread khác.

**Đúng:** nếu thực sự cần callback bất đồng bộ, tạo một **global reference** có ownership rõ ràng:

~~~c
/* Snippet bên trong native method đang có env và callback hợp lệ. */
jobject callbackGlobal = (*env)->NewGlobalRef(env, callback);
if (callbackGlobal == NULL) {
    return;  /* Có thể đang pending OutOfMemoryError. */
}

/* Chuyển callbackGlobal và JavaVM* sang worker theo giao thức
   có đồng bộ hóa; phải DeleteGlobalRef đúng lúc khi hoàn tất. */
~~~

Trong worker đã attach, dùng **JNIEnv của chính worker** để gọi Java; khi toàn bộ callback kết thúc và không ai dùng global reference nữa, gọi **DeleteGlobalRef** trên một thread attached hợp lệ.

Global reference chỉ bảo đảm đối tượng còn được JVM nhận diện; **nó không làm Java object thread-safe**. Nếu callback chứa mutable state thì Java code vẫn phải tuân thủ synchronization, visibility và lifecycle như bình thường.

### Local references trên native-attached worker dài hạn

Trong Java-originated native method, local references được tự động dọn khi method trả về. Nhưng một worker được attach từ C và chạy vòng lặp dài có thể **không có một native method return boundary tương ứng** cho từng lần callback. Vì vậy nên **DeleteLocalRef** sau từng việc hoặc dùng **PushLocalFrame/PopLocalFrame** có kiểm tra.

Không tích lũy hàng chục nghìn **jclass/jstring/jobject** local references chỉ vì ứng dụng chưa gọi DetachCurrentThread. Có thể cạn local reference capacity và giữ lại nhiều đối tượng Java không cần thiết.

## 7. Ví dụ runnable Java 17+ và C/JNI: hai nguồn tạo thread

Ví dụ này dùng **một thư viện JNI**, kiểm tra hai tình huống:

- **Java-originated calls:** main thread và hai Java threads gọi native method; JVM truyền JNIEnv đúng thread. Native code dùng **GetJavaVM** rồi **GetEnv** để đối chiếu JNIEnv lấy lại có đúng là env của thread gọi không.
- **Native-originated thread:** JNI khởi tạo một **pthread** (POSIX). Thread mới ban đầu nhận **JNI_EDETACHED**, gọi **AttachCurrentThread**, kiểm tra GetEnv rồi **DetachCurrentThread**.

**Ví dụ runnable trên Linux/macOS**, nơi có pthread. Trên Windows, phần Java và quy tắc JNI giữ nguyên, nhưng đoạn tạo thread bằng pthread cần chuyển sang Windows native thread API; không thể chỉ đổi phần mở rộng thư viện rồi biên dịch pthread code bằng MSVC.

### Bước 1 — Viết ThreadVmDemo.java

~~~java
public final class ThreadVmDemo {
    static {
        System.loadLibrary("threadvmdemo");
    }

    private ThreadVmDemo() {
    }

    private static native boolean checkCaller();
    private static native boolean checkNativeThread();

    public static void main(String[] args) throws InterruptedException {
        // Gọi từ Java main thread đã attached.
        boolean mainOk = checkCaller();

        // Mỗi Java Thread có ngữ cảnh JNI của riêng nó.
        boolean[] results = new boolean[2];

        Thread first = new Thread(
                () -> results[0] = checkCaller(), "java-first"
        );
        Thread second = new Thread(
                () -> results[1] = checkCaller(), "java-second"
        );

        first.start();
        second.start();

        // join() bảo đảm hai kết quả đã được ghi trước khi in.
        first.join();
        second.join();

        System.out.println("main=" + mainOk);
        System.out.println("java-first=" + results[0]);
        System.out.println("java-second=" + results[1]);
        System.out.println("native-worker=" + checkNativeThread());
    }
}
~~~

**Thread.join()** tạo bảo đảm visibility cần thiết để main thấy giá trị từng phần tử sau khi thread kết thúc. Thứ tự thực thi hai worker có thể khác nhau, nhưng **thứ tự in stdout cố định**, vì main chỉ in sau khi cả hai join.

### Bước 2 — Sinh class và header JNI

~~~bash
javac -h . ThreadVmDemo.java
~~~

Lệnh tạo **ThreadVmDemo.class** và **ThreadVmDemo.h**. File header giúp bảo đảm hai JNI function names khớp phương thức native Java. Các method đều static, do đó hàm C nhận **JNIEnv \*** và **jclass**.

### Bước 3 — Tạo thread_vm_demo.c

~~~c
#include "ThreadVmDemo.h"
#include <pthread.h>

/*
 * JVM handle chung, nhận khi library được load.
 * Không lưu JNIEnv* trong global hay chuyển qua pthread.
 */
static JavaVM *g_vm = NULL;

JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    g_vm = vm;
    return JNI_VERSION_1_6;
}

/*
 * Gọi từ một Java thread bất kỳ.
 * env chỉ hợp lệ cho Java thread đang thực thi method này.
 */
JNIEXPORT jboolean JNICALL
Java_ThreadVmDemo_checkCaller(JNIEnv *env, jclass unused) {
    (void)unused;

    JavaVM *from_env = NULL;
    JNIEnv *same_thread_env = NULL;

    if ((*env)->GetJavaVM(env, &from_env) != JNI_OK) {
        return JNI_FALSE;
    }
    if (from_env != g_vm) {
        return JNI_FALSE;
    }

    jint result = (*g_vm)->GetEnv(
        g_vm, (void **)&same_thread_env, JNI_VERSION_1_6
    );

    return (result == JNI_OK && same_thread_env == env)
            ? JNI_TRUE : JNI_FALSE;
}

/* Mỗi lần chạy worker có một result struct riêng. */
typedef struct WorkerResult {
    jint before_attach;
    jint after_attach;
    jint detach_result;
    int env_matches;
} WorkerResult;

/* Hàm chạy trên pthread hoàn toàn do native code tạo. */
static void *worker_main(void *argument) {
    WorkerResult *result = (WorkerResult *)argument;

    JNIEnv *env = NULL;
    result->before_attach = (*g_vm)->GetEnv(
        g_vm, (void **)&env, JNI_VERSION_1_6
    );

    if (result->before_attach != JNI_EDETACHED) {
        return NULL;
    }

    jint attach_result = (*g_vm)->AttachCurrentThread(
        g_vm, (void **)&env, NULL
    );
    if (attach_result != JNI_OK) {
        return NULL;
    }
    if (env == NULL) {
        result->detach_result =
                (*g_vm)->DetachCurrentThread(g_vm);
        return NULL;
    }

    /* Sau attach, GetEnv trả JNIEnv của chính pthread này. */
    JNIEnv *again = NULL;
    result->after_attach = (*g_vm)->GetEnv(
        g_vm, (void **)&again, JNI_VERSION_1_6
    );

    result->env_matches =
            (result->after_attach == JNI_OK && again == env);

    /* Không giữ env hoặc reference của pthread sau detach. */
    result->detach_result =
            (*g_vm)->DetachCurrentThread(g_vm);
    return NULL;
}

/* Chạy một native worker và chờ hoàn tất. */
JNIEXPORT jboolean JNICALL
Java_ThreadVmDemo_checkNativeThread(
        JNIEnv *env, jclass unused) {
    (void)env;
    (void)unused;

    WorkerResult result = {
        JNI_ERR, JNI_ERR, JNI_ERR, 0
    };

    pthread_t native_thread;
    if (pthread_create(
            &native_thread, NULL, worker_main, &result) != 0) {
        return JNI_FALSE;
    }

    if (pthread_join(native_thread, NULL) != 0) {
        return JNI_FALSE;
    }

    return (
        result.before_attach == JNI_EDETACHED &&
        result.after_attach == JNI_OK &&
        result.env_matches &&
        result.detach_result == JNI_OK
    ) ? JNI_TRUE : JNI_FALSE;
}
~~~

### Phân tích từng phần C

**JNI_OnLoad:** nhận JavaVM của tiến trình và giữ trong **g_vm**. Tất cả worker cùng làm việc với JVM này, nhưng không sử dụng chung một JNIEnv pointer.

**checkCaller:** nhận **env** từ JVM vì Java đã gọi native method. **GetJavaVM** lấy JavaVM của env đó; **GetEnv** được gọi **trên chính Java thread hiện tại**, nên trả về cùng JNI interface pointer hợp lệ. Điều này kiểm tra sự nhất quán trong từng thread; **không hề chia sẻ env của thread main sang thread khác**.

**worker_main:** bắt đầu trên một POSIX thread không được tạo bởi JVM. **GetEnv** trả **JNI_EDETACHED** theo tình huống demo. **AttachCurrentThread** trả về **env của native worker**, và lần GetEnv sau đó trả JNI_OK với cùng env. Cuối cùng **DetachCurrentThread** chạy **trên chính native worker**, trước khi pthread kết thúc.

**checkNativeThread:** method này bắt đầu trên Java thread có env riêng, nhưng **không truyền env cho pthread**. Nó chỉ chờ pthread hoàn thành, sau đó kiểm tra các mã kết quả được lưu trong struct C. Result struct tồn tại trên stack của caller trong suốt thời gian worker chạy và được đọc sau **pthread_join**.

**Giới hạn có chủ đích:** demo dùng **pthread_join** trực tiếp trong native method để giữ vòng đời result struct ngắn và dễ kiểm chứng. Nó không phải kiến trúc cho hệ thống native worker bất đồng bộ dài hạn. Trong production, cần có thread manager, shutdown, lỗi pthread và ownership bộ nhớ phù hợp; không để một worker tiếp tục truy cập pointer vào stack sau khi caller trả về.

### Bước 4 — Build native library

Cần JDK 17+ với **JAVA_HOME** trỏ tới JDK chứa header JNI, compiler C và POSIX pthread.

**Linux, GCC:**

~~~bash
gcc -std=c11 -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  thread_vm_demo.c -o libthreadvmdemo.so
~~~

**macOS, Clang:**

~~~bash
clang -std=c11 -fPIC -dynamiclib -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  thread_vm_demo.c -o libthreadvmdemo.dylib
~~~

Cả hai đầu ra đều phù hợp tên logic **threadvmdemo** được dùng trong **System.loadLibrary("threadvmdemo")** trên nền tảng tương ứng. Nếu JVM chạy trên một kiến trúc CPU khác binary C, phải build lại cùng kiến trúc/ABI.

### Bước 5 — Chạy

~~~bash
java -Djava.library.path=. ThreadVmDemo
~~~

**Stdout chính xác khi build/load và pthread hoạt động thành công:**

~~~text
main=true
java-first=true
java-second=true
native-worker=true
~~~

Đây là kết quả theo **trạng thái JNI thực sự**, không phụ thuộc thread scheduler in theo thứ tự nào: worker Java không in trực tiếp; main chỉ in sau join.

Từ JDK 24, các phiên bản/cấu hình JNI có cơ chế restricted native access. Nếu cần cho phép native access cho ứng dụng classpath, chạy với tùy chọn phù hợp:

~~~bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. ThreadVmDemo
~~~

Trên một số cấu hình, thiếu khai báo quyền có thể tạo warning **stderr** hoặc bị từ chối theo chính sách, không phải một phần stdout ở trên. Chỉ bật quyền theo module cần sử dụng khi ứng dụng chạy ở module path.

### Bước 6 — Khi chương trình trả false hoặc lỗi

| Dấu hiệu | Gợi ý kiểm tra |
| --- | --- |
| **UnsatisfiedLinkError** trước khi in | Thiếu/sai tên thư viện, ABI hoặc dependency; kiểm tra java.library.path và binary build |
| **main=false** | JNI_OnLoad không nhận đúng VM, GetJavaVM/GetEnv thất bại, hoặc không chạy đúng thư viện |
| **java-first/second=false** | Native method gọi GetEnv thất bại hoặc trả env không đúng thread; kiểm tra JNI correctness |
| **native-worker=false** | pthread_create/join lỗi, GetEnv trước attach không có trạng thái dự kiến, Attach/Detach lỗi |
| JVM crash | Vi phạm native memory/thread API hoặc binary không tương thích; xem crash log và chạy -Xcheck:jni |

Có thể bật cơ chế kiểm tra JNI của HotSpot trên môi trường test:

~~~bash
java -Xcheck:jni -Djava.library.path=. ThreadVmDemo
~~~

Tùy JDK, kết hợp với khai báo native access thích hợp. **-Xcheck:jni** giúp phát hiện nhiều cách dùng JNI sai, nhưng không thay thế kiểm tra ownership, synchronization hoặc memory safety của code C.

## 8. Từ worker native gọi một Java callback an toàn

Ví dụ runnable trước chỉ xác minh trạng thái attach. Trong hệ thống thực, worker native thường còn cần **gọi Java method** hoặc gửi kết quả về ứng dụng.

Một callback an toàn cần đồng thời đúng bốn điều kiện:

1. **JavaVM \*** còn hợp lệ trong lifecycle hiện tại.
2. Worker có **JNIEnv \*** của chính nó, đã attached.
3. Đối tượng callback được giữ bằng reference có vòng đời phù hợp, ví dụ **global reference** nếu callback chạy sau native method ban đầu.
4. Java callback, class loader, exception và đồng bộ hóa được xử lý rõ ràng.

Snippet sau giả định **callbackGlobal** là **global reference tới một java.lang.Runnable** đã được tạo đúng cách và còn sống. Đây là **helper gọi từ native worker đã được tạo trước đó**, không phải một chương trình hoàn chỉnh; phần tạo thread/ownership callback do hệ thống điều phối.

~~~c
static void call_runnable_on_worker(
        JavaVM *vm, jobject callbackGlobal) {
    JNIEnv *env = NULL;
    int attached_here = 0;

    jint status = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_6
    );

    if (status == JNI_EDETACHED) {
        if ((*vm)->AttachCurrentThread(
                vm, (void **)&env, NULL) != JNI_OK) {
            return;
        }
        attached_here = 1;
    } else if (status != JNI_OK) {
        return; /* Ví dụ: JNI_EVERSION. */
    }

    jclass cls = (*env)->GetObjectClass(env, callbackGlobal);
    if (cls != NULL) {
        jmethodID run_id = (*env)->GetMethodID(
            env, cls, "run", "()V"
        );

        if (run_id != NULL) {
            (*env)->CallVoidMethod(
                env, callbackGlobal, run_id
            );
        }

        (*env)->DeleteLocalRef(env, cls);
    }

    /*
     * Background native thread không có Java caller
     * tự nhiên để nhận callback exception.
     * Demo chọn ghi lỗi ra stderr rồi clear để cleanup.
     */
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }

    /*
     * Hàm này KHÔNG sở hữu callbackGlobal,
     * caller chịu trách nhiệm DeleteGlobalRef sau khi
     * không còn worker nào sử dụng reference đó.
     */
    if (attached_here) {
        (*vm)->DetachCurrentThread(vm);
    }
}
~~~

**Chú ý:** đoạn code demo xử lý exception bằng **ExceptionDescribe/ExceptionClear** có chủ đích để minh họa cleanup trên native background thread. Production cần đưa lỗi tới cơ chế ghi nhận/response/monitoring phù hợp; không bỏ qua exception im lặng. Nếu caller đang ở một native method được Java gọi, **không detach** vì **attached_here = 0**.

### Vì sao callback cần global reference?

Nếu Java gọi native method và đưa vào đối tượng **Runnable callback**, tham số jobject ở native method là **local reference** của thread gọi và chỉ hợp lệ trong phạm vi đó. Native code muốn lưu qua callback bất đồng bộ phải tạo **NewGlobalRef** trước khi method trả về. Worker nhận reference này qua hàng đợi có synchronization/ownership hợp lệ, dùng env của chính mình để CallVoidMethod, sau đó reference được chủ sở hữu xóa bằng **DeleteGlobalRef** khi không còn ai dùng.

**Không dùng env của thread tạo callback** để gọi Java từ worker, kể cả khi callbackGlobal là global reference hợp lệ. Global reference và JNIEnv có hai hợp đồng riêng: reference có thể chia sẻ, còn JNIEnv vẫn bị giới hạn theo thread.

## 9. Class loader khi một native worker tự attach

Có một rủi ro ít rõ ràng: **native thread mới được attach thường có thread context class loader mặc định là bootstrap loader**. Khi gọi **FindClass** từ một luồng không có Java native method frame đang active, JNI không nhất thiết tìm class qua loader của module/plugin đã gọi một method trước đó. Theo JNI Invocation API, trường hợp FindClass không có current native method thường sử dụng **system class loader**, vốn có thể không nhìn thấy class từ custom/module/plugin class loader.

Vì vậy, cùng một lệnh:

~~~c
jclass cls = (*env)->FindClass(
    env, "com/example/plugin/Callback"
);
~~~

có thể hoạt động khi được gọi từ native method của một class Java cụ thể, nhưng thất bại trên native background thread nếu lớp chỉ có trong custom class loader.

Các hướng xử lý:

- Java caller **truyền đối tượng callback hoặc Class** vào JNI trong bối cảnh class loader phù hợp.
- Khi cần dùng lâu, native code tạo **global reference** tới Class/callback đã được Java cung cấp, rồi giải phóng theo lifecycle.
- Hoặc lưu **ClassLoader** có kiểm soát và gọi **loadClass** thông qua JNI trên worker đúng thread; tránh lệ thuộc vào FindClass mặc định.
- Nếu cần tìm system classes như **java/lang/String**, xử lý riêng, nhưng không vì thế kết luận mọi application class đều có thể FindClass từ bất kỳ native thread.

Caching jclass global reference cũng có tác động class loader unloading. Trong hệ thống plugin/hot reload phải có đường **DeleteGlobalRef** và dừng native worker trước unload; nếu không sẽ giữ class loader còn sống hoặc để lại callback trỏ vào code đã biến mất.

## 10. Thread safety, synchronization và bất biến nghiệp vụ

Việc mỗi thread có JNIEnv hợp lệ **không làm dữ liệu Java được chia sẻ trở nên thread-safe**.

Ví dụ một native callback dùng **SetIntField** ghi cùng field của một đối tượng được nhiều thread truy cập. Dù mỗi thread gọi SetIntField qua JNIEnv riêng và đúng loại field, vẫn có thể xảy ra race condition. Tương tự, hai thread native cùng gọi Java method thay đổi một List không đồng bộ có thể làm state không nhất quán.

Cần quản lý ba cấp:

| Cấp | Câu hỏi kiểm tra |
| --- | --- |
| **JNI thread affinity** | JNIEnv đang dùng có được cấp cho chính thread này không? |
| **JNI reference lifecycle** | jobject/jclass là local hay global? Vẫn còn hợp lệ và không bị xóa sớm không? |
| **Java data synchronization** | Các thread cùng đọc/ghi state Java có lock, volatile, atomic hoặc thiết kế bất biến phù hợp không? |

**JavaVM không phải mutex** và **JNIEnv không phải lock**. Chúng chỉ là các giao diện giúp thực hiện tác vụ JNI đúng ngữ cảnh.

### Callback bất đồng bộ cần giao thức shutdown

Nếu native library tạo thread sống lâu:

1. Khởi tạo VM handle/callback global reference trước khi worker bắt đầu.
2. Worker attach đúng cách, xử lý request, dọn local references sau mỗi lượt.
3. Khi ứng dụng tắt, dừng nhận việc mới, thông báo hủy/chấm dứt worker và chờ worker kết thúc.
4. Worker giải phóng JNI resources thuộc mình, xử lý callback exception rồi detach.
5. Chủ sở hữu xóa global references khi chắc chắn không còn worker dùng chúng.
6. Chỉ sau đó cho phép class loader/native library unload hoặc quá trình JVM shutdown hoàn tất.

Không để g_vm hoặc callback reference trở thành pointer treo chỉ vì thread được cấu hình daemon. Daemon ảnh hưởng việc chờ shutdown, **không hủy bỏ yêu cầu cleanup**.

## 11. Lỗi phổ biến và nguyên nhân trực tiếp

| Cách viết sai | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| **static JNIEnv *g_env;** rồi dùng trên mọi thread | Dùng JNI interface của thread khác; có thể crash | Cache JavaVM, lấy JNIEnv trên từng thread |
| Truyền **JNIEnv \*** từ native method sang pthread | JNI pointer hết phạm vi thread ban đầu | Chuyển **JavaVM \***; pthread GetEnv/Attach |
| Gọi **GetEnv** rồi mặc định env luôn có giá trị | JNI_EDETACHED trả env không hợp lệ | Kiểm tra status và attach khi cần |
| Mọi lỗi GetEnv đều dẫn đến Attach | JNI_EVERSION không phải “chưa attached” | Phân biệt JNI_EDETACHED/JNI_EVERSION |
| Gọi **DetachCurrentThread** trong native method do Java gọi | Thread Java vẫn có Java frame; sai ownership | Không detach Java-originated thread |
| Gọi attach lặp lại rồi detach vô điều kiện | Có thể detach thread do caller/JVM sở hữu | Theo dõi **attached_here** |
| Gọi DetachCurrentThread trên thread A để dọn thread B | Hàm chỉ tác động current thread | Worker B tự detach |
| Dùng **jobject local** trên worker sau native call | Local reference sai thread/hết lifetime | NewGlobalRef và DeleteGlobalRef đúng lifecycle |
| Cache jclass local để dùng sau này | Reference hết hạn hoặc sai thread | Global class reference có cleanup |
| Tạo nhiều local refs trên worker lâu dài | Tích lũy handles/GC roots | DeleteLocalRef hoặc local frames |
| Gọi **FindClass** cho plugin class từ native worker rồi giả định luôn thấy | Class loader context khác | Truyền Class/callback, cache global ref hoặc đúng ClassLoader |
| Bỏ qua pending exception trong CallVoidMethod | Worker tiếp tục JNI trong trạng thái lỗi | Check, xử lý/ghi nhận/clear có chủ đích |
| Giữ native non-daemon worker không có shutdown | JVM chờ thread kết thúc | Có stop/join/detach hoặc chọn daemon có trách nhiệm |
| Dùng global reference như cơ chế đồng bộ | Vẫn có Java state race | Dùng lock/volatile/atomic/immutable state phù hợp |
| So sánh số địa chỉ JNIEnv từ hai thread để nhận diện thread | Pointer value không phải thread ID hợp đồng | Dùng thread identity chính thức và lifecycle |

## 12. Checklist trước khi đưa JNI đa luồng vào production

- [ ] Đã tách rõ nơi giữ **JavaVM \*** với nơi lấy **JNIEnv \*** theo current thread.
- [ ] Không lưu hoặc chia sẻ JNIEnv qua nhiều thread; không đưa JNIEnv vào global queue cho native worker.
- [ ] Java-originated native methods dùng **env được JVM truyền**, không detach thread này.
- [ ] Native-created worker gọi **GetEnv**, xử lý đủ **JNI_OK/JNI_EDETACHED/JNI_EVERSION**.
- [ ] Worker chỉ gọi **AttachCurrentThread** hoặc **AttachCurrentThreadAsDaemon** khi cần; theo dõi **attached_here**.
- [ ] Detach chạy trên **chính worker**, sau callback và dọn tài nguyên, trước khi thread chấm dứt.
- [ ] JNI_OnLoad hoặc GetJavaVM cung cấp handle JVM được quản lý theo vòng đời thư viện.
- [ ] Các callback bất đồng bộ nhận **global references** hợp lệ; không dùng local ref từ thread khác.
- [ ] Mỗi worker dọn local refs/frames và xử lý pending exception đúng phạm vi.
- [ ] Class loader của callback/Class được kiểm soát, đặc biệt với plugin/hot reload.
- [ ] Java state được chia sẻ có chính sách synchronization và memory visibility rõ.
- [ ] Có cơ chế stop/join các worker, cleanup global refs và native library lifecycle.
- [ ] Có test khi thiếu library, attach thất bại, nhiều Java worker gọi JNI cùng lúc và native worker shutdown.
- [ ] Đã chạy -Xcheck:jni và smoke test trên từng OS/CPU/ABI/JDK được hỗ trợ.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Có thể lưu **JavaVM \*** vào biến global để các native worker cùng sử dụng không?

**Đáp án:** Có, nếu handle thuộc JVM hiện tại, được khởi tạo đúng và chỉ dùng khi VM/thư viện còn sống. Mỗi worker dùng JavaVM đó để lấy hoặc attach **JNIEnv của riêng mình**.

**Câu 2.** Vì sao không được lưu **JNIEnv \*** từ Java thread A rồi gửi sang pthread B?

**Đáp án:** JNIEnv chỉ hợp lệ trong thread đã nhận nó. B phải dùng JavaVM để **GetEnv/AttachCurrentThread**, lấy JNIEnv hợp lệ cho B.

**Câu 3.** **GetEnv** có tự attach một native thread chưa attached không?

**Đáp án:** Không. Nó trả **JNI_EDETACHED** và không cho JNIEnv dùng được; cần gọi **AttachCurrentThread** hoặc daemon variant nếu B cần sử dụng Java/JNI.

**Câu 4.** Một native method do Java gọi có nên gọi **DetachCurrentThread** trong finally không?

**Đáp án:** Không. Java thread đã được JVM attach và còn Java frames; native method không sở hữu việc detach thread đó.

**Câu 5.** AttachCurrentThread được gọi trên một thread đã attached có biến thread đó thành non-daemon không?

**Đáp án:** Không. Trên thread đã attached, nó trả existing JNIEnv và không đổi trạng thái daemon hiện tại.

**Câu 6.** Để gọi Java Runnable từ native worker sau khi native method ban đầu trả về, cần những gì?

**Đáp án:** JavaVM hợp lệ, JNIEnv của worker đã attached, một **global reference** hợp lệ đến Runnable, callback qua API JNI đúng luồng, xử lý exception, dọn reference và detach theo ownership.

**Câu 7.** Gọi **GetEnv** trả **JNI_EVERSION**. Có nên coi là JNI_EDETACHED rồi attach ngay?

**Đáp án:** Không. JNI_EVERSION nói rằng JNI version yêu cầu không được hỗ trợ. Phải sửa phiên bản/hợp đồng trước, không tiếp tục với env chưa hợp lệ.

**Câu 8.** Vì sao **FindClass** tìm thấy class plugin ở một JNI method nhưng có thể không tìm thấy từ native pthread?

**Đáp án:** Native pthread tự attach không nhất thiết có class loader context của Java caller/plugin. Cần cung cấp Class/callback trong đúng bối cảnh, dùng global ref hoặc class loader được quản lý.

**Câu 9.** Hai thread đã có JNIEnv hợp lệ có thể đồng thời ghi một field Java mà không cần đồng bộ không?

**Đáp án:** Quy tắc JNIEnv đúng thread không bảo đảm an toàn dữ liệu. Các thao tác Java state vẫn phải dùng synchronization, atomic hoặc mô hình dữ liệu phù hợp.

## Tài liệu tham khảo chính thức

- [Oracle JNI Specification — Invocation API: Attaching, Detaching, GetEnv, daemon threads và JNI_OnLoad](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — Design Overview: JNI interface pointer và quy tắc local/global references](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions: GetJavaVM, FindClass và quản lý references](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Oracle javac — tạo native header bằng javac -h](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).

**Điều cốt lõi:** **JavaVM là cổng tiếp cận JVM có thể chia sẻ trong phạm vi vòng đời hợp lệ; JNIEnv là môi trường JNI chỉ hợp lệ cho luồng đang sở hữu nó**. Thread Java gọi native đã được attach và nhận env tự động. Native-created thread phải lấy env của chính nó bằng GetEnv/AttachCurrentThread, quản lý references/callback đúng cách và detach khi kết thúc. Phân biệt hai cấp này là nền tảng để JNI đa luồng vận hành an toàn.
