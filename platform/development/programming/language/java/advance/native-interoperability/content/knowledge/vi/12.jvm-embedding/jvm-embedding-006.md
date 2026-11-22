# Gắn các luồng của ứng dụng chủ và điều phối vòng đời của chúng khi nhúng JVM

## 1. Bối cảnh: ứng dụng C/C++ là chủ, JVM là thành phần được nhúng

Khi **nhúng JVM (embedding)**, chương trình gốc là một ứng dụng native (ví dụ server C++, phần mềm desktop, bộ xử lý media hoặc ứng dụng điều khiển thiết bị). Ứng dụng này **tự khởi tạo JVM** thông qua **JNI Invocation API**, thay vì chạy từ lệnh `java Main`. Sau khi có `JavaVM*`, nó có thể gọi các lớp và phương thức Java từ nhiều luồng native của chính mình.

Tình huống thường gặp:

- Luồng điều phối của host khởi tạo JVM, cấu hình classpath và tạo các Java object cần thiết.
- Các worker native được tạo bởi `std::thread`, `pthread`, Win32 threads hoặc native thread pool.
- Mỗi worker cần gọi Java (xử lý nghiệp vụ, kiểm tra rule, callback, logging Java...) nên phải **attach vào JVM của host**.
- Sau khi công việc hoàn tất, host yêu cầu worker ngừng nhận việc, chờ chúng trả hết Java callback, **detach đúng luồng**, dọn JNI references rồi mới **DestroyJavaVM**.

Điểm chính của bài: **đúng thao tác attach chưa đủ**. Phải thiết kế **ai tạo JVM, ai sở hữu từng thread, ai được sử dụng `JNIEnv*`, ai đóng đường nhận việc, ai chờ `join` và khi nào được DestroyJavaVM**. Sai thứ tự có thể gây deadlock lúc shutdown, rò rỉ native thread hoặc crash vì dùng JNI sau khi JVM không còn tồn tại.

> Quy tắc cốt lõi: **`JavaVM*` được chia sẻ giữa các worker trong thời gian JVM còn sống; `JNIEnv*` chỉ thuộc luồng lấy được nó. Worker native nào cần JNI thì chính worker đó attach và tự detach. Host chỉ hủy JVM khi mọi native worker có thể gọi Java đã ngừng và được thu hồi.**

## 2. Từ ứng dụng chủ tới JVM: khởi tạo một lần

### 2.1. `JNI_CreateJavaVM`

Ứng dụng native khởi tạo JVM bằng:

```cpp
jint JNI_CreateJavaVM(
        JavaVM** p_vm, void** p_env, void* vm_args);
```

Đây là **chữ ký API để minh họa**. Trong C++ có `jni.h`, bạn truyền địa chỉ của `JavaVM*`, địa chỉ của `JNIEnv*` và `JavaVMInitArgs` đã cấu hình:

```cpp
JavaVM* vm = nullptr;
JNIEnv* hostEnv = nullptr;

char classpath[] = "-Djava.class.path=.";
JavaVMOption option{};
option.optionString = classpath;

JavaVMInitArgs args{};
args.version = JNI_VERSION_1_6;
args.nOptions = 1;
args.options = &option;
args.ignoreUnrecognized = JNI_FALSE;

jint rc = JNI_CreateJavaVM(
        &vm, reinterpret_cast<void**>(&hostEnv), &args);
```

Đoạn code này là **trích đoạn trong hàm host C++**, không phải chương trình biên dịch riêng. Ví dụ hoàn chỉnh ở mục 7.

Khi thành công (`rc == JNI_OK`), luồng gọi `JNI_CreateJavaVM` trở thành **main thread của JVM** và đã được attach; `hostEnv` là `JNIEnv*` dành cho **chính luồng đó**. Không được lấy `hostEnv` rồi chia sẻ cho các worker khác.

**Hai giới hạn nền tảng:**

1. Một ứng dụng không được thiết kế như thể có thể gọi `JNI_CreateJavaVM` mỗi khi nhận một yêu cầu. JNI Invocation API **không hỗ trợ tạo nhiều JVM độc lập trong cùng một tiến trình** như một cơ chế thông thường.
2. Đừng dựa vào việc **DestroyJavaVM rồi tạo lại JVM khác** trong cùng process để tái sử dụng runtime: không phải vòng đời restart được bảo đảm cho ứng dụng nhúng. Nếu cần cách ly, cân nhắc **tiến trình riêng**, không phải liên tục dựng/hủy VM trong process chung.

Theo JNI Specification, trên một số hệ điều hành **primordial process thread** có thể có hạn chế stack hoặc cách quản lý đặc biệt. Với host production, cân nhắc tạo một **luồng điều phối có stack phù hợp** để khởi tạo và sở hữu chu kỳ JVM; ví dụ học tập ở mục 7 dùng `main` của native process để giữ cấu hình dễ hiểu.

### 2.2. Ai quản lý JVM?

Nên có một owner rõ ràng, chẳng hạn `JvmManager`, với các trạng thái:

```text
NOT_STARTED
    |
    | JNI_CreateJavaVM thành công
    v
RUNNING
    |
    | nhận yêu cầu stop/shutdown
    v
STOPPING      (không cho sinh thêm lời gọi Java mới)
    |
    | worker detach + native join
    | giải phóng global references
    v
READY_TO_DESTROY
    |
    | DestroyJavaVM
    v
STOPPED
```

Đây là **mô hình thiết kế của ứng dụng**, không phải những hằng trạng thái do JNI tự cung cấp. Phần mềm cần bảo vệ việc chuyển trạng thái bằng mutex/atomic hoặc cơ chế điều phối tương đương để worker không “vừa kịp attach” khi host đã bắt đầu shutdown.

## 3. `JavaVM*` và `JNIEnv*`: hai loại con trỏ không được nhầm

| Thành phần | Có chia sẻ giữa thread không? | Dùng để làm gì? | Vòng đời |
| --- | --- | --- | --- |
| `JavaVM*` | **Có**, khi VM còn tồn tại | `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, `DestroyJavaVM` | Do JVM tạo; không dùng sau khi đã Destroy thành công |
| `JNIEnv*` | **Không** | Tra class/method, tạo string, gọi Java, quản lý local refs, kiểm tra Java exception | Thuộc một thread đã attach; không dùng sau detach |
| `jobject`/`jclass` local ref | Không mang xuyên thread tùy tiện | Tham chiếu tới Java object/class trong một JNI context | Hết hạn theo phạm vi local reference |
| `jobject`/`jclass` global ref | Có thể dùng từ các thread đã attach nếu còn hợp lệ | Giữ Java object/class xuyên lời gọi JNI và qua worker | Tạo bằng `NewGlobalRef`, hủy bằng `DeleteGlobalRef` trước khi VM ngừng |

Ví dụ sai:

```cpp
// Sai: hostEnv thuộc luồng khởi tạo VM.
std::thread worker([hostEnv]() {
    hostEnv->FindClass("java/lang/String");
});
```

Đây là **minh họa lỗi**, không phải code nên chạy. `JNIEnv*` thuộc thread khởi tạo; dùng nó ở worker vi phạm hợp đồng JNI. Triệu chứng có thể là crash, corruption hoặc lỗi chỉ xuất hiện khi chạy với `-Xcheck:jni`.

Ví dụ đúng về hướng sử dụng (đoạn code **bên trong native worker** đã có `JavaVM* vm` hợp lệ):

```cpp
JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), nullptr);

if (rc != JNI_OK || env == nullptr) {
    // Báo lỗi và không gọi JNI nếu chưa attach.
    return;
}

// Chỉ thread hiện tại sử dụng env.
// Hoàn tất Java calls trước khi detach.

(void)vm->DetachCurrentThread();
```

Phải bảo đảm release local resources/resolve pending exceptions ở đường đi thực tế. `DetachCurrentThread` được gọi bởi **chính worker**, không phải host “detach hộ”.

## 4. Kiểm tra trước khi attach: `GetEnv`

Host native thread có thể đã được attach bởi một thư viện khác. Cần phân biệt **borrowed attachment** với **attachment do code mình tạo**.

```cpp
JNIEnv* env = nullptr;
bool attachedHere = false;

jint rc = vm->GetEnv(
        reinterpret_cast<void**>(&env), JNI_VERSION_1_6);

if (rc == JNI_EDETACHED) {
    rc = vm->AttachCurrentThread(
            reinterpret_cast<void**>(&env), nullptr);
    if (rc == JNI_OK) {
        attachedHere = true;
    }
}

if (rc != JNI_OK || env == nullptr) {
    // JNI_EVERSION hoặc lỗi attach: dừng công việc.
    return;
}

// Thực hiện JNI trên thread này, hoàn thành mọi Java callback.

if (attachedHere) {
    (void)vm->DetachCurrentThread();
}
```

Đây là **mẫu minh họa trong thân một hàm C++ trả `void`**, không phải ví dụ độc lập. Khi triển khai, nên dùng guard/RAII để bảo đảm cleanup cho mọi đường thoát.

Giải thích trạng thái:

- `JNI_OK`: thread hiện tại **đã attached** và có thể dùng `env`.
- `JNI_EDETACHED`: thread hiện tại **chưa attached**; `GetEnv` **không tự attach**.
- `JNI_EVERSION`: phiên bản JNI yêu cầu không được JVM hỗ trợ.
- `AttachCurrentThread` thành công: tạo attachment non-daemon nếu thread chưa attached.
- Nếu đã attached, gọi attach lần nữa **không thay đổi trạng thái** và không chuyển nó từ daemon thành non-daemon hay ngược lại.

**Ownership:** nếu `GetEnv` ban đầu cho `JNI_OK`, attachment đã tồn tại. Code thư viện chỉ “mượn” `JNIEnv*` thì **không được tự detach** khi chủ sở hữu gốc vẫn cần nó. Chỉ detach nếu chính code bạn đã attach trong scope được sở hữu rõ ràng; một thread cũng không thể detach khi còn Java methods trên call stack.

## 5. Chọn non-daemon hay daemon cho thread của host

Native thread chưa attached có hai cách:

```cpp
// Tạo attachment non-daemon cho thread hiện tại.
vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), nullptr);

// Hoặc, ở một thread khác/chưa attached:
// Tạo attachment daemon cho thread hiện tại.
vm->AttachCurrentThreadAsDaemon(
        reinterpret_cast<void**>(&env), nullptr);
```

Đây là **hai lời gọi lựa chọn thay thế**, không phải lời khuyên gọi cả hai trên cùng thread. Nếu thread đã attached, lần gọi lại chỉ trả `JNIEnv*` và **không đổi daemon status**.

| Tiêu chí | `AttachCurrentThread` | `AttachCurrentThreadAsDaemon` |
| --- | --- | --- |
| Attachment lần đầu | Non-daemon | Daemon |
| Được phép gọi Java/JNI | Có | Có |
| Có thể làm `DestroyJavaVM` phải chờ | **Có** — là non-daemon thread | Bản thân daemon **không giữ JVM sống** |
| Cần dừng, giải phóng và detach | **Có** | **Có** |
| Dùng hợp lý | Worker thực hiện giao dịch/công việc phải hoàn thành | Worker nền có thể hủy nhưng vẫn có stop/cleanup rõ ràng |

**Không chọn daemon như một cách né lỗi shutdown.** Daemon chỉ thay đổi quy tắc VM chờ non-daemon user threads; nó **không tự kết thúc công việc, không tự release resource, không tự dọn global references**. Khi VM bắt đầu shutdown, daemon thread có thể chưa hoàn thành Java callback, nên ứng dụng chủ phải tự phối hợp.

Ngược lại, một native non-daemon worker chạy vòng lặp vô hạn có thể làm `DestroyJavaVM` **chờ vô thời hạn**. Chủ ứng dụng phải phát tín hiệu ngừng và đợi worker detach trước khi hủy VM.

### 5.1. `JavaVMAttachArgs` khi cần đặt tên

`AttachCurrentThread` và `AttachCurrentThreadAsDaemon` có thể nhận `JavaVMAttachArgs`:

```cpp
char workerName[] = "host-jni-worker";
JavaVMAttachArgs attachArgs{};
attachArgs.version = JNI_VERSION_1_6;
attachArgs.name = workerName;
attachArgs.group = nullptr;

JNIEnv* env = nullptr;
jint rc = vm->AttachCurrentThread(
        reinterpret_cast<void**>(&env), &attachArgs);
```

Đây là đoạn code **chạy trong thread chưa attached**, với `JavaVM* vm` hợp lệ.

- `name` là tên Java thread hiển thị khi debug, theo chuẩn **modified UTF-8**; nếu không cần thì dùng `nullptr`.
- `group` có thể là global reference tới `ThreadGroup` hoặc `nullptr`; không truyền local reference từ thread khác.
- `version` là hằng giao diện JNI, **không phải** số nguyên phiên bản Java như `17`.
- Dùng attach lại trên một thread đã attached sẽ **không** thay đổi daemon status, và không nên coi đó là cơ chế đổi tên/thread group.

## 6. Điều phối vòng đời nhiều native workers

Điều quan trọng không chỉ là từng cặp attach/detach, mà là **cơ chế kiểm soát cả pool**.

### 6.1. Trình tự start đúng

1. Host khởi tạo JVM **một lần** và kiểm tra `JNI_CreateJavaVM == JNI_OK`.
2. Trên luồng khởi tạo JVM, nạp đúng Java class và method; nếu cần chuyển chúng sang worker, tạo **global references**.
3. Mở worker pool. Mỗi native worker tự attach trước lời gọi JNI đầu tiên của mình, hoặc dùng `GetEnv` để biết đã attached chưa.
4. Mỗi worker xử lý công việc trên `JNIEnv*` riêng, giải quyết Java exceptions ngay trên luồng phát sinh; không cất `JNIEnv*` trong object chia sẻ.
5. Host chỉ nhận thêm việc khi JVM đang ở trạng thái `RUNNING` và owner vẫn bảo đảm VM sống đến khi việc kết thúc.

### 6.2. Trình tự shutdown an toàn

```text
Host nhận yêu cầu shutdown
          |
          v
Đóng cổng nhận việc mới / đặt STOPPING
          |
          v
Phát stop signal cho worker pool
          |
          v
Worker đang chạy kết thúc Java calls hiện tại
          |
          v
Mỗi worker xóa local refs cần thiết, detach từ chính thread của nó
          |
          v
Host join tất cả native threads (không còn callback nào đang chạy)
          |
          v
Host xóa các global references do mình sở hữu
          |
          v
Host gọi DestroyJavaVM khi không còn worker phụ thuộc JVM
          |
          v
JVM dừng; không còn lời gọi JNI mới từ host
```

**Lý do phải khóa nguồn việc trước khi join:** nếu producer vẫn đẩy việc vào pool, worker có thể tiếp tục attach/gọi Java ngay lúc host muốn Destroy. Đồng bộ shutdown phải đảm bảo **không có attach/callback mới từ thời điểm ngắt nhận việc**.

**Lý do phải join trước `DestroyJavaVM`:** bạn muốn biết chắc mọi native worker do ứng dụng sở hữu đã dừng. Dù các worker attach daemon, host vẫn cần thu hồi thread và bộ nhớ; `DestroyJavaVM` không phải lời gọi “join hộ” native worker pool. Với non-daemon, nếu worker chưa dừng, Destroy có thể bị chặn.

### 6.3. Không ép detach hộ và không đóng JVM dưới chân worker

Một số anti-pattern:

- Host giữ danh sách `JNIEnv*` của từng worker rồi gọi `DetachCurrentThread` ở host: **sai**, vì API detach luồng **đang gọi**, không detach một thread được chọn theo pointer.
- Host đóng JVM trước, rồi native worker mới sử dụng `JavaVM*` hoặc `JNIEnv*`: **sai vòng đời**, có thể crash.
- Worker được tạo sau tín hiệu stop nhưng trước khi gọi Destroy: gây race attach-vs-shutdown.
- Host chờ worker bằng một mutex mà worker cần giữ/cấp trong Java callback: dễ deadlock; phải phân tích lock order và không giữ khóa của shutdown trong lúc chờ join nếu worker cần nó để thoát.

### 6.4. Sở hữu thread pool rõ ràng

Với worker sống lâu, mô hình thường là:

```text
worker thread start
    -> Attach once
    -> repeat:
         await native work
         call Java when needed
         clear local refs/resolve exceptions per job
         stop if shutdown requested
    -> Detach once
worker thread exit
```

Không phải cứ mỗi callback lại attach và detach; bạn có thể attach một lần cho cả **vòng đời của worker**, nhưng phải đảm bảo worker kết thúc có kiểm soát. Với thread pool do thư viện bên thứ ba sở hữu, hãy xác định khả năng đăng ký thread-start/thread-stop hooks; nếu không biết ai sở hữu attachment, dùng `GetEnv` + ownership flag và **không tự detach thread đã attached từ trước**.

### 6.5. Luồng khởi tạo JVM cũng có vòng đời

Thread gọi `JNI_CreateJavaVM` đã có `JNIEnv*` ngay từ đầu; nó có thể gọi Java mà không attach thêm. Theo đặc tả, `DestroyJavaVM` có thể được gọi từ một thread phù hợp; đừng để nhiều thread cùng tranh quyền destroy. Nên quy định một **JVM owner** duy nhất chịu trách nhiệm shutdown.

Nếu host dùng một **dedicated JVM management thread**, gửi yêu cầu khởi tạo/shutdown tới nó qua queue và dùng cơ chế barrier/future để đảm bảo worker không bắt đầu trước khi VM sẵn sàng hoặc tiếp tục sau khi VM dừng. Stack của thread khởi tạo cần đáp ứng yêu cầu môi trường.

## 7. Ví dụ đầy đủ: host C++17 nhúng JVM và điều phối hai worker

Ví dụ này tập trung vào **toàn bộ lifecycle**. Chương trình host (không có `public static void main` Java) sẽ:

1. Dùng `JNI_CreateJavaVM` để mở JVM trong cùng process.
2. Nạp lớp `EmbeddedService`, tìm Java method và tạo `jclass` global reference.
3. Tạo **hai `std::thread` native**: một attach non-daemon, một attach daemon.
4. Hai worker gọi `EmbeddedService.report(String)` qua `JNIEnv*` riêng rồi detach.
5. Host `join` cả hai, giải phóng global ref, hủy JVM và in kết quả ổn định.

Lưu ý: demo dùng thread tạo từ C++ `main` cho ngắn gọn. Với production có yêu cầu đặc biệt về primordial thread/stack, nên đặt JVM owner trên một **thread quản lý chuyên dụng** theo khuyến nghị của JNI Invocation API. Các nguyên tắc attach/stop/join/destroy bên dưới vẫn giữ nguyên.

### 7.1. Java: `EmbeddedService.java`

```java
public final class EmbeddedService {
    private EmbeddedService() {
    }

    public static String report(String label) {
        return label + ":daemon=" + Thread.currentThread().isDaemon();
    }
}
```

Java ở đây là **một lớp dịch vụ**, không cần có `main` vì **ứng dụng C++ là chương trình khởi động**. `report` trả chuỗi; bản thân Java không in ra stdout, do đó mọi dòng output của chương trình host có thể được sắp thứ tự chủ động.

### 7.2. C++ host: `EmbeddedHost.cpp`

```cpp
#include <jni.h>

#include <functional>
#include <iostream>
#include <string>
#include <system_error>
#include <thread>

struct JobResult {
    bool ok = false;
    std::string text;
};

// Chạy trên native thread do std::thread tạo.
static void runWorker(JavaVM* vm,
                      jclass serviceClass,
                      jmethodID reportMethod,
                      const char* label,
                      bool daemon,
                      JobResult* out) {
    JNIEnv* env = nullptr;

    // Worker mới tạo phải chưa attached.
    jint before = vm->GetEnv(
            reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
    if (before != JNI_EDETACHED) {
        out->text = "unexpected thread attachment state";
        return;
    }

    jint attachStatus = daemon
            ? vm->AttachCurrentThreadAsDaemon(
                    reinterpret_cast<void**>(&env), nullptr)
            : vm->AttachCurrentThread(
                    reinterpret_cast<void**>(&env), nullptr);

    if (attachStatus != JNI_OK || env == nullptr) {
        out->text = "attach failed";
        return;
    }

    // Từ đây chỉ env thuộc worker này được dùng.
    jstring jlabel = env->NewStringUTF(label);
    jstring reply = nullptr;

    if (jlabel != nullptr) {
        reply = static_cast<jstring>(env->CallStaticObjectMethod(
                serviceClass, reportMethod, jlabel));

        if (!env->ExceptionCheck() && reply != nullptr) {
            const char* chars = env->GetStringUTFChars(reply, nullptr);
            if (chars != nullptr) {
                out->text = chars; // Copy sang std::string thuộc host.
                out->ok = true;
                env->ReleaseStringUTFChars(reply, chars);
            }
        }
    }

    if (env->ExceptionCheck()) {
        // Java exception không tự chuyển sang thread gọi trong C++.
        // Demo ghi stderr và đánh dấu thất bại.
        env->ExceptionDescribe();
        env->ExceptionClear();
        out->ok = false;
        out->text = "Java callback failed";
    }

    if (reply != nullptr) {
        env->DeleteLocalRef(reply);
    }
    if (jlabel != nullptr) {
        env->DeleteLocalRef(jlabel);
    }

    // Java callback đã về C++; không còn Java frame hoạt động.
    if (vm->DetachCurrentThread() != JNI_OK) {
        out->ok = false;
        out->text = "detach failed";
    }
    // env hết hiệu lực sau detach.
}

int main() {
    char classpath[] = "-Djava.class.path=.";
    JavaVMOption option{};
    option.optionString = classpath;

    JavaVMInitArgs args{};
    args.version = JNI_VERSION_1_6;
    args.nOptions = 1;
    args.options = &option;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM* vm = nullptr;
    JNIEnv* ownerEnv = nullptr;

    jint created = JNI_CreateJavaVM(
            &vm, reinterpret_cast<void**>(&ownerEnv), &args);

    if (created != JNI_OK || vm == nullptr || ownerEnv == nullptr) {
        std::cerr << "JNI_CreateJavaVM failed\n";
        return 1;
    }

    // Tìm Java class trên luồng owner đã attached.
    jclass localClass = ownerEnv->FindClass("EmbeddedService");
    if (localClass == nullptr) {
        ownerEnv->ExceptionDescribe();
        ownerEnv->ExceptionClear();
        vm->DestroyJavaVM();
        return 1;
    }

    // Global ref được dùng an toàn trên các worker đã attached.
    jclass serviceClass = static_cast<jclass>(
            ownerEnv->NewGlobalRef(localClass));
    ownerEnv->DeleteLocalRef(localClass);

    if (serviceClass == nullptr) {
        if (ownerEnv->ExceptionCheck()) {
            ownerEnv->ExceptionDescribe();
            ownerEnv->ExceptionClear();
        }
        vm->DestroyJavaVM();
        return 1;
    }

    jmethodID reportMethod = ownerEnv->GetStaticMethodID(
            serviceClass,
            "report",
            "(Ljava/lang/String;)Ljava/lang/String;");

    if (reportMethod == nullptr) {
        if (ownerEnv->ExceptionCheck()) {
            ownerEnv->ExceptionDescribe();
            ownerEnv->ExceptionClear();
        }
        ownerEnv->DeleteGlobalRef(serviceClass);
        vm->DestroyJavaVM();
        return 1;
    }

    JobResult jobs[2];
    std::thread threads[2];

    // Tạo native workers. Khi một thread constructor thất bại,
    // vẫn phải join các worker đã tạo trước khi destroy VM.
    try {
        threads[0] = std::thread(
                runWorker, vm, serviceClass, reportMethod,
                "job-A", false, &jobs[0]);
        threads[1] = std::thread(
                runWorker, vm, serviceClass, reportMethod,
                "job-B", true, &jobs[1]);
    } catch (const std::system_error& ex) {
        for (auto& thread : threads) {
            if (thread.joinable()) {
                thread.join();
            }
        }
        ownerEnv->DeleteGlobalRef(serviceClass);
        vm->DestroyJavaVM();
        std::cerr << "Cannot start workers: " << ex.what() << '\n';
        return 1;
    }

    // Join là chờ native threads; không phụ thuộc daemon status.
    for (auto& thread : threads) {
        thread.join();
    }

    // Chỉ đọc kết quả sau join, không có concurrent write nữa.
    bool allOk = jobs[0].ok && jobs[1].ok;

    if (allOk) {
        std::cout << jobs[0].text << '\n';
        std::cout << jobs[1].text << '\n';
    } else {
        std::cerr << "One or more workers failed\n";
    }

    // Không worker nào còn sử dụng class/method hoặc JavaVM.
    ownerEnv->DeleteGlobalRef(serviceClass);

    jint destroyed = vm->DestroyJavaVM();
    if (destroyed != JNI_OK) {
        std::cerr << "DestroyJavaVM failed\n";
        return 1;
    }

    if (!allOk) {
        return 1;
    }
    std::cout << "shutdown=ok\n";
    return 0;
}
```

**Chìa khóa thiết kế trong ví dụ:**

- `JNI_CreateJavaVM` trả `ownerEnv` cho native `main`; nó **không** được truyền sang `runWorker`.
- `runWorker` nhận `JavaVM* vm` dùng chung và gọi `GetEnv` để kiểm tra thread chưa attached; tiếp theo tự attach theo flag `daemon`.
- `serviceClass` là **global reference** tạo trước khi worker chạy; local `jclass` từ `FindClass` được xóa sớm, không đem local ref đi qua luồng.
- `reportMethod` là `jmethodID` được tra cứu từ class tương ứng và dùng trong thời gian `serviceClass` còn được giữ sống. Nó không phải `JNIEnv*` nên không có quy tắc “mỗi thread một method ID”.
- Từng worker tạo và xóa **local references của chính mình** (`jlabel`, `reply`), giải phóng chuỗi `GetStringUTFChars` đúng hàm `ReleaseStringUTFChars` và kiểm tra Java exception.
- Worker tự detach sau khi Java method đã trả về. `ownerEnv` **không** gọi detach hộ.
- `std::thread::join` đưa cả hai worker về trạng thái dừng trước khi xóa `serviceClass`; sau đó mới hủy JVM.
- Kết quả native được đặt vào hai `JobResult` khác nhau; host chỉ in sau `join`, nên không phụ thuộc lịch scheduler khi hiển thị output.

Đây là **ví dụ nhỏ dùng để học lifecycle**. Nó không triển khai hệ thống retry/restart VM, pool nhận việc liên tục, hoặc hệ thống truyền toàn bộ Java throwable xuyên thread; production code nên bổ sung wrapper quản lý resource và chiến lược dừng khi tiến trình bị interrupt/kill.

### 7.3. Biên dịch Java

Đặt `EmbeddedService.java` và `EmbeddedHost.cpp` trong cùng một thư mục, chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 EmbeddedService.java
```

Lệnh tạo `EmbeddedService.class`. Không cần `javac -h` ở đây vì **Java không khai báo phương thức `native`**: hướng gọi là C++ host **→ Java static method** qua JNI Invocation API. Ngược lại, nếu Java khai báo `native` và muốn có symbol JNI ở thư viện C/C++, lúc đó `javac -h` mới cần.

### 7.4. Linux — g++/HotSpot JDK

Giả sử `JAVA_HOME` trỏ tới thư mục JDK 17+ có `include` và `lib/server/libjvm.so`:

```bash
javac -encoding UTF-8 EmbeddedService.java

g++ -std=c++17 -O2 -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  EmbeddedHost.cpp \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embedded-host

./embedded-host
```

`-I` giúp compiler tìm `jni.h` và header đặc thù Linux; `-L` chỉ thư mục chứa thư viện JVM; `-ljvm` link JVM Invocation API. `-Wl,-rpath,...` nhúng một đường tìm `libjvm.so` lúc chạy. Có thể chọn cách quản lý dynamic loader khác theo packaging nhưng phải bảo đảm hệ điều hành tìm đúng `libjvm.so` cùng JDK.

### 7.5. macOS — clang++/JDK

Giả sử JDK có `lib/server/libjvm.dylib`:

```bash
javac -encoding UTF-8 EmbeddedService.java

clang++ -std=c++17 -O2 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  EmbeddedHost.cpp \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embedded-host

./embedded-host
```

Trên macOS, vị trí JDK có thể được xác định bằng `/usr/libexec/java_home` nếu đã cài JDK phù hợp. Không cố dùng thư viện JVM từ JDK khác kiến trúc với compiler/host.

### 7.6. Windows — MSVC

Mở **x64 Native Tools Command Prompt** hoặc Developer Command Prompt đúng kiến trúc JDK, trỏ `JAVA_HOME` tới JDK và chạy trong thư mục có hai tệp nguồn:

```bat
javac -encoding UTF-8 EmbeddedService.java

cl /nologo /std:c++17 /EHsc ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  EmbeddedHost.cpp ^
  /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embedded-host.exe

set "PATH=%JAVA_HOME%\bin\server;%PATH%"
embedded-host.exe
```

`jvm.lib` là **import library** dùng lúc link; lúc chạy Windows cần tìm `jvm.dll` tương ứng (với layout JDK phổ biến tại `%JAVA_HOME%\bin\server`). Lệnh `set PATH` áp dụng cho **cmd.exe**; PowerShell có cú pháp biến môi trường khác. Kiến trúc 64 bit/32 bit của host, JDK và JVM native library phải tương thích.

### 7.7. Stdout chính xác khi thành công

```text
job-A:daemon=false
job-B:daemon=true
shutdown=ok
```

Giải thích:

- `job-A` được attach bằng `AttachCurrentThread`, vì vậy `Thread.currentThread().isDaemon()` trong Java trả `false`.
- `job-B` được attach bằng `AttachCurrentThreadAsDaemon`, vì vậy Java trả `true`.
- Hai worker chạy song song, nhưng **host chỉ in sau khi đã join cả hai** và in theo thứ tự index, nên đầu ra chuẩn trên đường đi thành công cố định.
- Dòng `shutdown=ok` chỉ được in sau khi `DestroyJavaVM` trả `JNI_OK`.

Lệnh ví dụ không phụ thuộc JNI symbols dạng `Java_package_Class_method` vì không có Java→native declaration. Nếu lệnh chạy báo không tìm thấy class, kiểm tra **working directory** vì `-Djava.class.path=.` được cấu hình trong host. Nếu liên kết JVM thất bại, kiểm tra `JAVA_HOME`, dynamic loader, ABI và đúng thư viện `jvm` của JDK.

## 8. Class loader và references khi luồng host gọi Java

### 8.1. `FindClass` trên native-created worker thường khó hơn tưởng tượng

Một luồng được attach từ phía native **không có Java caller trên call stack**. Theo JNI Invocation API, context class loader khi attach mặc định là **bootstrap class loader**. Việc gọi:

```cpp
// Minh họa trên worker đã attached.
jclass type = env->FindClass("com/example/Plugin");
```

có thể thất bại nếu lớp `Plugin` do application/custom class loader nạp và không thể tìm theo quy tắc lookup tại vị trí đó. Đừng giả định chỉ cần `AttachCurrentThread` là worker có cùng classpath/loader context với bất kỳ Java thread nào khác.

Một cách thiết kế ổn định là **resolve class khi đang ở context đã biết**, giữ `jclass` bằng global ref rồi truyền vào worker. Đó là lý do `EmbeddedHost.cpp` gọi `FindClass("EmbeddedService")` **trên luồng JVM owner**, tạo `NewGlobalRef` và chỉ sau đó mới tạo worker.

Nếu ứng dụng có nhiều plugin class loaders hoặc hot reload Java modules, cần quản lý vòng đời của class và loader tương ứng. Một global ref giữ class/loader sống; nếu không giải phóng, việc unload class loader sẽ bị ảnh hưởng.

### 8.2. Phân biệt local/global/weak global

- **Local ref**: thường thuộc JNI call/thread context; không chuyển sang native thread khác để dùng sau khi context kết thúc.
- **Global ref**: tạo `NewGlobalRef`, dùng được ở các attached threads trong thời gian còn sống; là strong reference nên có thể giữ object/class sống ngoài ý muốn.
- **Weak global ref**: dùng khi cần giữ tham chiếu yếu, nhưng có thể bị GC xóa, nên phải kiểm tra/lấy strong local reference đúng cách trước khi dùng.

Đừng biến toàn bộ Java object trong dự án thành global refs; chỉ giữ những object thật sự cần cho callback dài hơn phạm vi JNI call và luôn thiết lập rõ **owner dọn ref**.

### 8.3. Không cache `JNIEnv*` trong singleton

Một lỗi kiến trúc thường thấy là singleton `JniBridge` có trường `JNIEnv* env`. Khi nhiều worker gọi vào, singleton trả cùng env cho các thread khác nhau. **Sai**. Singleton manager có thể giữ **`JavaVM* vm`**, còn worker dùng `GetEnv` hoặc attach để lấy `JNIEnv*` của riêng mình.

Một mẫu API hữu ích:

```cpp
// Chỉ là chữ ký thiết kế, không phải chương trình C++ độc lập.
class JvmManager {
public:
    JavaVM* vm() const;
    bool isStopping() const;
    // JNI context phải lấy theo current thread.
};
```

Trạng thái `isStopping()` phải được đồng bộ đúng cách nếu nhiều thread gọi, và `vm()` chỉ được dùng nếu owner còn bảo đảm JVM sống (ví dụ bằng một lease/reference-counted lifecycle token có hợp đồng rõ).

## 9. Lỗi Java, lỗi attach và cách xử lý trên biên thread

### 9.1. Java exception không tự xuất hiện ở thread owner

Nếu worker native gọi:

```cpp
env->CallStaticVoidMethod(serviceClass, method);
```

và Java ném exception, **pending exception thuộc `JNIEnv*` của worker**. Nó **không tự trở thành exception trong thread C++ host** hay được ném vào Java thread khác. Worker phải phát hiện bằng `ExceptionCheck`, báo/ghi lỗi, xử lý hoặc chuyển throwable theo cơ chế có chủ đích, rồi giải phóng local resources và detach khi hợp lệ.

Ở demo, `ExceptionDescribe` in stack trace ra stderr; `ExceptionClear` được gọi có chủ đích để cleanup tiếp. Ứng dụng production có thể dùng message queue, result object hoặc callback thất bại về Java qua một đường đã định nghĩa. **Không clear exception im lặng rồi báo công việc thành công**.

### 9.2. Attach thất bại

`AttachCurrentThread`/`AttachCurrentThreadAsDaemon` trả mã như `JNI_OK` hoặc lỗi âm. Nếu không thành công hoặc `env == nullptr`, không được gọi JNI qua env. Worker trả trạng thái lỗi cho host. Host vẫn phải quyết định có retry, hủy job hay shutdown, và không được gọi detach nếu chính worker chưa attach thành công.

### 9.3. Detach chỉ khi Java callback đã kết thúc

Thread không thể gọi `DetachCurrentThread` khi còn Java methods trên call stack của chính nó. Do đó trình tự hợp lệ là:

```text
native worker
  -> attach
  -> CallStaticObjectMethod
      -> Java report(...)
      <- report trả về
  -> release string/local references
  -> detach
  -> return khỏi std::thread
```

Nếu code Java gọi ngược native rồi native cố detach ngay trong lời gọi lồng nhau đó, vẫn còn Java frame đang chạy, nên không hợp lệ.

### 9.4. Thread stack và JNI callback sâu

Native worker có stack size do **hệ điều hành/native threading API** quyết định. Nếu callback Java đi sâu hoặc dùng recursion, stack quá nhỏ có thể gây `StackOverflowError` hay lỗi hệ thống. Với ứng dụng nhúng, phải chọn stack size phù hợp, đo với workload thực và kiểm soát recursion. Đây cũng là một lý do JNI Specification khuyến nghị cân nhắc tránh dùng primordial thread để khởi tạo VM trên vài OS.

## 10. Shutdown, deadlock và bài toán tranh chấp

### 10.1. `DestroyJavaVM` không phải công cụ hủy tất cả native threads

Theo JNI Invocation API, JVM phải chờ điều kiện liên quan các **non-daemon user threads** trước khi hoàn tất destroy. Những luồng này bao gồm cả **Java threads** và **native threads đã attach non-daemon**.

**Hệ quả:** nếu một worker non-daemon vẫn chạy và không detach, lời gọi destroy có thể **treo chờ**. Ngược lại, daemon worker không buộc VM chờ, nhưng có thể vẫn có tài nguyên native chưa được dọn. Vì vậy host nên **ngừng nhận việc, signaling stop, đợi worker detach/join, rồi destroy** cho cả hai loại thread.

Đừng dùng shutdown JVM để thay thế shutdown native subsystem. Với host có các Java threads được tạo bên trong Java, các luồng Java non-daemon đó cũng phải có cơ chế dừng; chỉ join native workers là chưa chắc đủ nếu Java workers vẫn sống.

### 10.2. Race: worker attach đúng lúc host destroy

Nếu chỉ dùng biến bool thường và không đồng bộ, host có thể nhìn thấy “không có worker” trong khi một native thread vừa được tạo nhưng chưa kịp attach. Host gọi `DestroyJavaVM`, worker sau đó cố attach vào JVM đang dừng.

**Giải pháp thiết kế:**

- Có trạng thái `RUNNING/STOPPING` được bảo vệ bằng mutex hoặc atomic đúng memory ordering.
- Mỗi job/worker nhận một **quyền sử dụng JVM** (lifecycle lease) khi owner còn `RUNNING`; không cấp lease mới sau `STOPPING`.
- Owner chờ toàn bộ lease đang hoạt động kết thúc và mọi native worker join trước `DestroyJavaVM`.
- Một khi `STOPPING`, các callback mới không được phép bắt đầu, trừ những callback dọn cuối đã được owner quản lý và bảo đảm VM còn sống.

Bản demo tạo các worker ngay sau khi VM ready rồi `join` rõ ràng, nên không phải giải quyết queue/lease phức tạp; production cần cơ chế này nếu pool nhận việc liên tục.

### 10.3. Deadlock do chờ không đúng khóa

Giả sử host giữ mutex `shutdownLock` khi gọi `join`, trong khi worker cần khóa đó để cập nhật “đã dừng”. Worker chờ lock, host chờ worker: **deadlock**.

Quy tắc thực hành: phát stop signal khi giữ lock nếu cần, **nhả lock trước `join`**, rồi mới lấy lại lock để cập nhật trạng thái tổng. Tương tự, tránh giữ khóa native lâu khi callback Java có thể gọi ngược native và tranh cùng khóa.

### 10.4. Lỗi “Destroy rồi init lại”

Một số ứng dụng giả định có thể gọi `JNI_CreateJavaVM`/`DestroyJavaVM` theo mỗi session và khởi tạo VM mới. JNI Invocation API không thiết kế đa JVM độc lập trong một process. Nếu sản phẩm cần restart Java runtime thường xuyên, hãy xem mô hình **host spawn một Java subprocess** hoặc một service Java riêng, nơi process lifetime là ranh giới cô lập và restart thực sự.

### 10.5. Dùng `std::thread::detach()` khác hoàn toàn JNI `DetachCurrentThread`

Hai cái tên giống nhau nhưng chức năng khác:

| API | Ý nghĩa |
| --- | --- |
| `std::thread::detach()` | **Bỏ quyền join** của C++ thread object; thread hệ điều hành vẫn chạy độc lập |
| `JavaVM::DetachCurrentThread()` | **Gỡ attachment JNI của luồng hiện tại khỏi JVM** |

Một worker có thể bị C++ thread object `detach()` nhưng **vẫn attached vào JVM**; hoặc đã JNI-detach nhưng C++ thread vẫn joinable. Tránh dùng `std::thread::detach()` cho worker cần host quản lý shutdown, trừ khi bạn có cơ chế vòng đời chặt chẽ khác.

## 11. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Hướng khắc phục |
| --- | --- | --- |
| Dùng `JNIEnv*` do host nhận từ `JNI_CreateJavaVM` trong worker | `JNIEnv*` chỉ dành cho current thread | Worker gọi `AttachCurrentThread` hoặc `GetEnv` để lấy env riêng |
| Gọi `GetEnv` mà không xử lý `JNI_EDETACHED` | `GetEnv` không attach | Attach đúng thread, kiểm tra `JNI_OK` |
| Dùng `AttachCurrentThreadAsDaemon` để đổi trạng thái thread đã attached | Gọi attach lại không đổi daemon status | Chọn daemon/non-daemon trước attachment đầu tiên |
| Đem `jclass` local ref từ host sang worker | Local JNI reference không có vòng đời xuyên thread thích hợp | Tạo `NewGlobalRef`, dọn `DeleteGlobalRef` sau join |
| Worker gọi `FindClass` nhưng không thấy class ứng dụng | Không có Java caller, loader context khác | Resolve class đúng context rồi truyền global ref |
| Quên `ReleaseStringUTFChars` hoặc `DeleteLocalRef` | Rò rỉ resource native/JNI | Cleanup per-job/per-thread có bảo đảm |
| Worker lỗi Java nhưng không kiểm tra pending exception | Kết quả giả thành công, JNI state không hợp lệ | `ExceptionCheck`, log/chuyển lỗi và cleanup |
| Worker không gọi `DetachCurrentThread` trước exit | Thread attachment không được dọn đúng | Dùng cleanup guard của worker |
| Host gọi detach hộ worker | JNI detach luôn áp dụng current thread | Để worker tự detach trước khi kết thúc |
| Host gọi `DestroyJavaVM` trước join | Worker có thể dùng JVM sau shutdown | Stop, detach, join, hủy JVM theo thứ tự |
| Non-daemon worker vô hạn không dừng | Destroy có thể chờ mãi | Có stop signal và thời hạn shutdown phù hợp |
| Chỉ đổi worker thành daemon để né treo | Daemon có thể bị bỏ dở khi VM dừng | Vẫn cần stop/join/resource cleanup |
| Không khóa cổng tạo việc khi shutdown | Race worker attach trong lúc Destroy | RUNNING→STOPPING atomic, chờ active jobs |
| Dùng `std::thread::detach` thay `DetachCurrentThread` | Hai API không liên quan | Quản lý cả C++ thread lifecycle và JNI attachment |
| Chạy `embedded-host` không tìm thấy JVM library | Thiếu runtime loader path/link library | Kiểm tra `JAVA_HOME`, `libjvm`/`jvm.dll` và ABI |
| `FindClass("EmbeddedService")` thất bại | Sai classpath/current working directory | `-Djava.class.path=.` và build class trong đúng thư mục |

## 12. Bài tập mở rộng để hiểu cách điều phối

### Bài tập 1 — Thêm worker thứ ba

Tạo worker `job-C` attach non-daemon và gọi Java như hai worker đầu. Thêm một slot riêng trong mảng `JobResult`, tạo thread rồi `join` tất cả. Quan sát stdout chỉ được in sau khi cả ba worker hoàn thành. **Đừng** cho cả ba thread ghi cùng một `std::string` không đồng bộ.

### Bài tập 2 — Mô phỏng worker mất nhiều thời gian

Cho một worker native ngủ một khoảng ngắn trước Java callback, rồi join. Quan sát rằng host vẫn không gọi `DestroyJavaVM` trước khi worker trả về và detach. Không thêm sleep để “giải quyết race”; sleep chỉ để quan sát, còn bảo đảm đến từ join và thứ tự shutdown.

### Bài tập 3 — Native worker pool sống lâu

Thay mỗi worker “một job rồi exit” bằng vòng lặp lấy job từ queue. Thiết kế trạng thái STOPPING để từ chối job mới, wake các worker đang chờ, xử lý hết job đang chạy hoặc hủy theo chính sách, rồi detach từng worker. Sử dụng condition variable cho stop signal, tránh polling vô hạn.

### Bài tập 4 — Java callback ném exception

Đổi Java `report` để có điều kiện ném `IllegalStateException`. Kiểm chứng native worker gọi `ExceptionCheck`, không báo `ok=true`, và vẫn detach. Host phải nhận trạng thái lỗi rõ ràng, không để exception âm thầm biến mất ở worker.

### Bài tập 5 — Kiểm chứng JNI thread rules

Chạy thử với `-Xcheck:jni` như một option bổ sung cho `JNI_CreateJavaVM` nếu JVM hỗ trợ. Xác minh chương trình **không** dùng env khác thread, không dùng local ref hết hạn và không bỏ release. Mục đích của bài tập là dùng công cụ kiểm tra lỗi, không thay thế phân tích ownership và lifecycle.

## 13. Checklist thiết kế trước khi triển khai

1. Ai là **JVM owner**? Ai được gọi `JNI_CreateJavaVM` và `DestroyJavaVM`?
2. Có đảm bảo **một JVM sống một chu kỳ rõ ràng**, không tạo nhiều JVM/giả định restart trong một process?
3. Worker nào do native tạo? Mỗi worker có `JNIEnv*` riêng sau `AttachCurrentThread`/`AttachCurrentThreadAsDaemon` chưa?
4. Có kiểm tra `GetEnv` và quyền sở hữu attachment để tránh detach nhầm thread của bên thứ ba?
5. Các Java class/object qua thread có dùng **global ref** đúng cách, với class loader phù hợp?
6. Có kiểm tra null, JNI error codes, pending Java exceptions và cleanup từng local ref/chuỗi được lấy?
7. Worker có detach **trong chính thread của nó**, sau khi Java callback kết thúc không?
8. Host có đóng cổng nhận việc trước khi stop, đồng bộ active jobs, và chờ mọi native thread `join`?
9. Có xóa mọi global refs sau khi worker ngừng dùng và **trước khi** destroy JVM?
10. Có xét Java-created non-daemon threads, GC, stack size, class loaders và native ABI/loader paths?
11. Có đo đường đi thất bại và shutdown trong integration tests, không chỉ happy path?
12. Có tránh dùng `JavaVM*`/`JNIEnv*` sau khi VM đã destroy?

## Tài liệu chính thức

- [Oracle Java 17 — JNI Specification: Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_CreateJavaVM`, `GetEnv`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, `DestroyJavaVM` và cảnh báo liên quan primordial thread.
- [Oracle Java 17 — JNI Specification: JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `FindClass`, `GetStaticMethodID`, `CallStaticObjectMethod`, `NewGlobalRef`, `DeleteGlobalRef`, quản lý local refs, chuỗi và Java exceptions.
- [Oracle Java 17 — JNI Specification: JNI Types](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `JNIEnv`, `JavaVM`, `jclass`, `jobject` và các kiểu dữ liệu khác.
- [Oracle Java 17 — Thread.isDaemon](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#isDaemon()): xác nhận trạng thái daemon qua Java callback.
- [Oracle Java 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tạo class file cho JVM được nhúng.