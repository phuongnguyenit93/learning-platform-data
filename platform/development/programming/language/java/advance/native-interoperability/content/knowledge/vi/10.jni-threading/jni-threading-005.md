# Tháo luồng do mã bản địa gắn và dọn tham chiếu trước khi kết thúc

Khi Java gọi một phương thức **native**, JVM đã có thread và cung cấp **JNIEnv*** cho phương thức đó. Ngược lại, một luồng do mã C/C++ tự tạo bằng **pthread_create**, **std::thread** hoặc thư viện native phải tự **AttachCurrentThread** (hoặc **AttachCurrentThreadAsDaemon**) trước khi sử dụng JNI. Sau khi hoàn tất công việc, nếu chính luồng ấy thực hiện attach, nó phải **DetachCurrentThread** trước khi kết thúc.

**Detach không thay thế cleanup.** Trong lúc attach, worker có thể tạo local references, global references, mượn pointer của String/array, giữ Java monitor hoặc cấp phát native buffers. Phải thu hồi tài nguyên theo đúng quyền sở hữu và thứ tự, xử lý lỗi rồi mới tháo thread. Không được chuyển **JNIEnv*** giữa các thread hoặc dùng nó sau detach.

Mục tiêu học tập: giải thích *ai chịu trách nhiệm detach*, *dọn reference nào và bằng API nào*, *lúc nào Java callback được xem là đã kết thúc*, *cách xử lý lỗi*, và thực hành trên một native worker Java 17+ thực sự.

## 1. Hai đường đi Java–native

~~~text
Java tạo thread
  Java Thread.run()
    -> gọi native method bằng JNI
       -> native nhận JNIEnv* có sẵn
       -> trả tài nguyên native và local refs cần thiết
    <- native method return
  Java tiếp tục quản lý thread

Native tạo thread
  pthread_create / std::thread
    -> thread chưa gắn JVM: không có JNIEnv*
    -> AttachCurrentThread -> nhận JNIEnv* của thread này
    -> tạo và dùng JNI references
    -> Call...Method -> Java callback -> quay về native
    -> giải phóng borrowed buffers, references, locks
    -> DetachCurrentThread
    -> native thread exit
~~~

Trong trường hợp đầu, native method thường **không được tự tháo Java thread**: lúc native method đang thực thi vẫn có Java frames trên stack. Trường hợp thứ hai do native tự tạo và attach, native worker có trách nhiệm detach sau khi mọi Java methods trên call stack đã trả về. JNI specification quy định rõ **không thể detach khi Java methods vẫn còn trên call stack**.

**AttachCurrentThread** attach như non-daemon Java thread. **AttachCurrentThreadAsDaemon** attach như daemon. Gọi attach khi thread đã attach trả lại interface hiện có, *không thay đổi daemon status*. Daemon chỉ ảnh hưởng điều kiện giữ JVM sống khi shutdown; **không loại bỏ nghĩa vụ cleanup hoặc detach**.

## 2. JavaVM*, JNIEnv* và quyền sở hữu

| Thành phần | Phạm vi | Quy tắc |
| --- | --- | --- |
| **JavaVM*** | Đại diện JVM; có thể đưa tới worker khi JVM còn sống | Dùng cho **GetEnv**, **AttachCurrentThread**, **DetachCurrentThread** |
| **JNIEnv*** | Chỉ hợp lệ trên thread nhận nó | Tuyệt đối không lấy env ở thread A rồi dùng trên B |
| **jobject/jclass local ref** | Local reference chỉ hợp lệ trong thread và local frame tương ứng | Không gửi local ref qua thread |
| **NewGlobalRef** | Tạo reference có thể dùng qua các thread đã attach | Phải **DeleteGlobalRef** theo vòng đời owner |
| **NewWeakGlobalRef** | Reference yếu, không bảo đảm object còn tồn tại | Khi không cần phải **DeleteWeakGlobalRef** |
| **jmethodID/jfieldID** | ID opaque, không phải jobject reference | Không gọi **DeleteLocalRef/GlobalRef** lên ID |

Một helper có thể được gọi cả từ Java thread và native thread. Muốn tránh tháo nhầm attachment không do mình tạo, kiểm tra trạng thái trước khi attach:

~~~c
/*
 * Fragment chạy trong một hàm C trả về void.
 * vm là JavaVM* hợp lệ; cần bổ sung cleanup tại điểm kết thúc.
 */
JNIEnv *env = NULL;
int attached_here = 0;
jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (status == JNI_EDETACHED) {
    status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
    if (status != JNI_OK) {
        return; /* Không có JNIEnv* hợp lệ. */
    }
    attached_here = 1;
} else if (status != JNI_OK) {
    return; /* Ví dụ JNI_EVERSION. */
}

/* Gọi JNI ở đây; tất cả các đường lỗi phải đi qua cleanup. */

if (attached_here) {
    status = (*vm)->DetachCurrentThread(vm);
    /* Ứng dụng thật phải báo/xử lý status != JNI_OK. */
}
~~~

**GetEnv** trả **JNI_OK** nếu thread đã attach, **JNI_EDETACHED** nếu chưa attach, **JNI_EVERSION** nếu phiên bản JNI không được hỗ trợ. Nếu helper gọi **AttachCurrentThread** mà thread vốn đã attach, helper không tự động trở thành chủ sở hữu attachment. Lưu **attached_here** cho quy trình cleanup.

**DetachCurrentThread tác động lên thread hiện tại.** Java thread gốc không thể gọi hàm này để tháo một pthread khác từ xa; worker tự detach khi hoàn tất.

## 3. Những tài nguyên phải dọn trước khi kết thúc

| Tài nguyên | Tạo bằng | Dọn bằng |
| --- | --- | --- |
| Local reference tới **jstring**, **jclass**, **jobject**, **jarray** | **FindClass**, **NewStringUTF**, **CallObjectMethod**, v.v. | **DeleteLocalRef** hoặc **PopLocalFrame** |
| Global reference | **NewGlobalRef** | **DeleteGlobalRef** |
| Weak global reference | **NewWeakGlobalRef** | **DeleteWeakGlobalRef** |
| Pointer tạm từ Java string | **GetStringUTFChars**, **GetStringChars** | **ReleaseStringUTFChars**, **ReleaseStringChars** tương ứng |
| Primitive array elements | **GetIntArrayElements** và các biến thể | **ReleaseIntArrayElements** và đúng biến thể |
| Critical pointer | **GetPrimitiveArrayCritical**, **GetStringCritical** | Release Critical tương ứng, giữ critical region thật ngắn |
| Java monitor do native giữ | **MonitorEnter** | **MonitorExit** |
| Bộ nhớ/tài nguyên OS do native quản lý | **malloc**, **new**, file/socket/lock | **free**, **delete**, close/unlock theo đúng API native |

### 3.1. Local references và attached threads sống lâu

Trong một native method gọi từ Java, local references thông thường được thu hồi khi **native method return**. Một native-attached worker có thể chạy rất lâu không có điểm trở về Java của native invocation, nên local refs do nó tạo sẽ dễ **tích lũy cho đến detach**. Trên các runtime thông dụng, detached thread được JVM thu hồi phần còn lại, nhưng việc chờ đến đó vẫn có thể gây hết bộ nhớ hoặc reference slots.

Ví dụ sửa lỗi khi xử lý nhiều item:

~~~c
/* Fragment: env hợp lệ trên native worker đã attach. */
for (int i = 0; i < 100000; i++) {
    jstring item = (*env)->NewStringUTF(env, "value");
    if (item == NULL) {
        /* Báo lỗi, xử lý pending exception trước khi thoát. */
        break;
    }

    /* Sử dụng item trong iteration hiện tại. */

    (*env)->DeleteLocalRef(env, item);
}
~~~

Nếu một iteration tạo nhiều references, dùng **PushLocalFrame(env, capacity)** và **PopLocalFrame(env, NULL)** có thể đơn giản hóa cleanup. Mỗi **PushLocalFrame** thành công phải có **PopLocalFrame** tương ứng trên mọi đường ra; đừng dùng local ref từ frame đã pop. **EnsureLocalCapacity** chỉ chuẩn bị dung lượng, không xóa các reference đã tạo.

**DeleteLocalRef** không đồng nghĩa giải phóng ngay Java object; nó chỉ bỏ một reference JNI, giúp GC có thể thu hồi object khi không còn strong references khác.

### 3.2. Global references không tự bị xóa khi detach

**NewGlobalRef** tạo reference mạnh giữ object Java có thể được sử dụng trên những attached threads khác. Nó tồn tại đến khi gọi **DeleteGlobalRef**, kể cả thread tạo ref đã chết. Không xóa sớm khi worker vẫn cần object, và cũng không giữ vô hạn khi callback/job kết thúc.

Một mô hình ownership rõ ràng:

~~~text
Thread Java gọi native
  -> NewGlobalRef(callbackClass)
  -> trao quyền sở hữu reference cho job
  -> native worker attach
  -> dùng callbackClass để gọi Java
  -> DeleteGlobalRef(callbackClass)
  -> DetachCurrentThread
  -> job kết thúc
~~~

Nếu worker **attach thất bại**, worker chưa có env hợp lệ để xóa ref. Thread tạo global ref phải có đường **fallback cleanup** sau khi biết worker đã kết thúc. Cần bảo đảm đúng **một lần xóa**, không double-delete và không delete khi một worker khác vẫn sử dụng reference.

**Weak global references** không giữ object sống lâu giống global ref mạnh, nhưng vẫn phải **DeleteWeakGlobalRef** để giải phóng tài nguyên quản lý. Muốn sử dụng object qua weak ref, tạo strong **NewLocalRef** và kiểm tra kết quả != NULL; chỉ kiểm tra **IsSameObject(weak, NULL)** rồi dùng tiếp weak ref không bảo đảm GC chưa làm object biến mất giữa hai thao tác.

### 3.3. Borrowed pointers và monitors có vòng đời riêng

Không nhầm **jstring local ref** với pointer trả từ **GetStringUTFChars**:

~~~c
/* Fragment: str là local ref hợp lệ. */
const char *chars = (*env)->GetStringUTFChars(env, str, NULL);
if (chars != NULL) {
    /* Sử dụng chars... */
    (*env)->ReleaseStringUTFChars(env, str, chars);
}
(*env)->DeleteLocalRef(env, str);
~~~

Phải release **chars** bằng hàm tương ứng **trước khi xóa local ref str**. Cũng vậy, **DeleteLocalRef** của **jintArray** không thay cho **ReleaseIntArrayElements**. Sau Release cuối, pointer lấy qua JNI không còn được phép sử dụng.

Nếu native đã **MonitorEnter**, hãy **MonitorExit** đúng cách trước detach. JNI spec có nói DetachCurrentThread có thể giải phóng Java monitors còn được giữ, nhưng một chương trình đúng không dựa vào hiệu ứng này để sửa lỗi quên unlock, vì có thể phá bất biến đồng bộ của ứng dụng.

## 4. Ví dụ Java 17+ và C/POSIX chạy được

Chương trình tạo một pthread từ native method. Worker tự gọi **GetEnv**, **AttachCurrentThread**, gọi ngược một static Java method ba lần, giải phóng các **jstring** local refs và UTF buffers, xóa một **jclass global ref**, rồi detach. Cuối cùng **GetEnv** xác nhận thread đã detached; Java thread chờ bằng **pthread_join**.

Ví dụ chạy trên **Linux/JDK 17+**, cần C compiler có pthread. Nó minh họa ownership/cleanup, không phải framework thread pool.

### 4.1. AttachedCleanupDemo.java

~~~java
public final class AttachedCleanupDemo {
    static {
        System.loadLibrary("attached_cleanup");
    }

    private AttachedCleanupDemo() {}

    private static native void runWorker();

    private static String label(int index) {
        return "job-" + index;
    }

    public static void main(String[] args) {
        System.out.println("Java: start");
        runWorker();
        System.out.println("Java: end");
    }
}
~~~

### 4.2. attached_cleanup.c

~~~c
#include <jni.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

struct Task {
    JavaVM *vm;
    jclass owner; /* Global ref, thuộc về task */
    int error;    /* 0 nếu thành công */
};

static void throw_state(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *worker_main(void *opaque) {
    struct Task *task = (struct Task *)opaque;
    JNIEnv *env = NULL;

    jint before = (*task->vm)->GetEnv(
            task->vm, (void **)&env, JNI_VERSION_1_6);
    if (before != JNI_EDETACHED) {
        task->error = 1;
        return NULL; /* Thread gốc sẽ xóa global ref. */
    }

    puts("Native: before attach = detached");
    fflush(stdout);

    jint attached = (*task->vm)->AttachCurrentThread(
            task->vm, (void **)&env, NULL);
    if (attached != JNI_OK || env == NULL) {
        task->error = 2;
        return NULL;
    }

    jmethodID label = (*env)->GetStaticMethodID(
            env, task->owner, "label", "(I)Ljava/lang/String;");
    if (label == NULL) {
        task->error = 3;
        goto cleanup_attached;
    }

    for (jint i = 0; i < 3; ++i) {
        jstring value = (jstring)(*env)->CallStaticObjectMethod(
                env, task->owner, label, i);
        if ((*env)->ExceptionCheck(env)) {
            task->error = 4;
            goto cleanup_attached;
        }
        if (value == NULL) {
            task->error = 5;
            goto cleanup_attached;
        }

        const char *chars = (*env)->GetStringUTFChars(
                env, value, NULL);
        if (chars == NULL) {
            task->error = 6;
            (*env)->DeleteLocalRef(env, value);
            goto cleanup_attached;
        }

        printf("Native: %s\n", chars);
        fflush(stdout);
        (*env)->ReleaseStringUTFChars(env, value, chars);
        (*env)->DeleteLocalRef(env, value);
    }

cleanup_attached:
    if ((*env)->ExceptionCheck(env)) {
        /* Demo ghi nhận Java exception; production có cơ chế riêng. */
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }

    (*env)->DeleteGlobalRef(env, task->owner);
    task->owner = NULL;

    jint detached = (*task->vm)->DetachCurrentThread(task->vm);
    if (detached != JNI_OK) {
        task->error = 7;
        return NULL;
    }

    /* Không sử dụng env sau khi đã detach. */
    JNIEnv *check_env = NULL;
    jint after = (*task->vm)->GetEnv(
            task->vm, (void **)&check_env, JNI_VERSION_1_6);
    if (after == JNI_EDETACHED) {
        puts("Native: after detach = detached");
        fflush(stdout);
    } else {
        task->error = 8;
    }
    return NULL;
}

JNIEXPORT void JNICALL
Java_AttachedCleanupDemo_runWorker(JNIEnv *env, jclass owner) {
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        throw_state(env, "GetJavaVM failed");
        return;
    }

    jclass global_owner = (jclass)(*env)->NewGlobalRef(env, owner);
    if (global_owner == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_state(env, "NewGlobalRef failed");
        }
        return;
    }

    struct Task task = {vm, global_owner, 0};
    pthread_t thread;
    int created = pthread_create(&thread, NULL, worker_main, &task);
    if (created != 0) {
        (*env)->DeleteGlobalRef(env, global_owner);
        throw_state(env, "pthread_create failed");
        return;
    }

    /*
     * Vì task là biến stack, phải đợi worker ngừng dùng nó.
     * Trong demo, lỗi pthread_join là lỗi hạ tầng không thể
     * an toàn tiếp tục với task đang nằm trên stack.
     */
    if (pthread_join(thread, NULL) != 0) {
        fputs("pthread_join failed\n", stderr);
        abort();
    }

    /* Fallback nếu worker không kịp attach/xóa global ref. */
    if (task.owner != NULL) {
        (*env)->DeleteGlobalRef(env, task.owner);
        task.owner = NULL;
    }

    if (task.error != 0) {
        throw_state(env, "attached worker failed");
    }
}
~~~

**Vì sao ví dụ giữ đúng vòng đời?**

- **runWorker** chạy trên Java thread gốc, nhận **JNIEnv*** từ JVM và chỉ dùng nó trên thread này.
- **GetJavaVM** lấy **JavaVM***; **NewGlobalRef** chuyển local **owner** thành global reference để pthread dùng hợp lệ.
- Pthread gọi **AttachCurrentThread** và có **JNIEnv*** của chính nó. Native callback qua **CallStaticObjectMethod** đã trở về trước khi detach.
- **GetStringUTFChars** được trả bằng **ReleaseStringUTFChars**; **jstring value** được **DeleteLocalRef** trong từng iteration.
- Worker **DeleteGlobalRef** trước detach. Nếu nó không attach thành công, Java-entry thread xóa global ref sau khi join, tránh leak/double-delete.
- Worker báo lỗi qua **task.error**; Java-entry native method chuyển thành exception cho Java caller. Pending exception trên worker được xử lý trước khi dọn tham chiếu.
- Sau detach, worker không dùng **JNIEnv*** nữa; kiểm tra trạng thái chỉ dùng **JavaVM* -> GetEnv**.

**Lưu ý về pthread_join:** đoạn demo dùng task trên stack và join một pthread joinable. Nếu pthread_join bất ngờ thất bại, nó dừng tiến trình để tránh trả về khi worker có thể vẫn đang truy cập địa chỉ stack. Sản phẩm thực tế nên dùng task trên heap, event/lifecycle management, cancellation policy và graceful shutdown phù hợp.

### 4.3. Biên dịch trên Linux

Lưu hai file **AttachedCleanupDemo.java** và **attached_cleanup.c** vào cùng thư mục, đặt **JAVA_HOME** tới JDK 17+ phù hợp kiến trúc compiler:

~~~bash
javac -h . AttachedCleanupDemo.java

cc -std=c17 -Wall -Wextra -Wpedantic -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  attached_cleanup.c -o libattached_cleanup.so

java -Xcheck:jni -Djava.library.path=. AttachedCleanupDemo
~~~

**javac -h .** tạo header để đối chiếu tên JNI export **Java_AttachedCleanupDemo_runWorker** và chữ ký hàm. **System.loadLibrary("attached_cleanup")** trên Linux tìm shared library theo quy ước như **libattached_cleanup.so**. Cần biên dịch theo ABI/JDK mục tiêu; trên Windows thay API thread và cách xây dựng DLL.

**Stdout chính xác ở nhánh thành công:**

~~~text
Java: start
Native: before attach = detached
Native: job-0
Native: job-1
Native: job-2
Native: after detach = detached
Java: end
~~~

Thứ tự là xác định bởi **pthread_join** và **fflush(stdout)**. Trên đường lỗi có thể xuất hiện stderr/Java exception hoặc ít dòng stdout hơn; kết quả trên chỉ dành cho trường hợp tạo/attach/callback/detach đều thành công.

## 5. Kiểm soát các đường lỗi và exception

Các hàm **GetStaticMethodID**, **Call...Method**, **NewStringUTF**, **NewGlobalRef** có thể gây lỗi hoặc tạo pending Java exception. Không được dùng object trả về khi lỗi và tiếp tục gọi JNI tùy ý trong lúc exception còn pending.

Quy trình cho native-attached worker:

~~~text
AttachCurrentThread thành công
       |
       v
JNI call và kiểm tra return / ExceptionCheck
       |
       +--- thành công --- xử lý dữ liệu
       |
       +--- thất bại ---- ghi/đóng gói lỗi
       |                   xử lý pending exception có chủ đích
       v
Release borrowed pointers / DeleteLocalRef
       |
DeleteGlobalRef / DeleteWeakGlobalRef theo ownership
       |
Release monitors / native locks / buffers
       |
DetachCurrentThread
       |
Báo trạng thái cho job owner, kết thúc native thread
~~~

**ExceptionCheck** là cách kiểm tra pending exception mà không tạo local ref. **ExceptionOccurred** tạo local reference tới Throwable, nên nếu giữ nó để xem xét phải dọn reference thích hợp. **ExceptionClear** xóa trạng thái exception; chỉ thực hiện khi đã quyết định log/chuyển lỗi, đừng nuốt lỗi im lặng. **ExceptionDescribe** hữu ích cho demo/chẩn đoán, nhưng không thay thế một cơ chế truyền lỗi trong production.

Nếu thread native do JNI attach không có Java caller đang đợi nhận exception trực tiếp, việc để exception pending rồi detach **không tự ném exception vào Java thread khác**. JNI specification cho phép VM báo sự tồn tại của pending exception khi detach. Hãy truyền mã lỗi/thông điệp hoặc thực hiện callback lỗi được kiểm soát trong khi attachment còn hợp lệ.

Ngược lại, một native method được Java gọi có thể return với pending exception để Java caller nhận lỗi theo hợp đồng; **không detach** Java caller thread trong tình huống này.

## 6. PushLocalFrame/PopLocalFrame trong worker dài hạn

Một native worker có thể xử lý hàng trăm nghìn object. Nếu mỗi vòng tạo local refs và chờ detach cuối cùng mới giải phóng, JVM có thể tốn nhiều tài nguyên giữ references hoặc objects sống.

~~~c
/* Fragment trên một attached worker, xử lý local refs theo từng lô. */
for (int i = 0; i < 100000; ++i) {
    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        /* Có thể thiếu tài nguyên hoặc có pending exception. */
        break;
    }

    jstring value = (*env)->NewStringUTF(env, "temporary");
    if (value != NULL) {
        /* Dùng value trong phạm vi local frame này. */
    }

    (*env)->PopLocalFrame(env, NULL);

    if ((*env)->ExceptionCheck(env)) {
        break; /* Rẽ tới error/cleanup của worker thực tế. */
    }
}
~~~

**PushLocalFrame** với capacity dương tạo một frame mới; **PopLocalFrame** loại bỏ mọi local refs thuộc frame ấy. Trên nhánh lỗi vẫn phải pop nếu push đã thành công; không dùng ref đã pop. Muốn giữ một local ref khi pop phải dùng biến thể **PopLocalFrame(env, result)**, nhận ref mới thuộc frame cha và quản lý nó. **EnsureLocalCapacity** không thực hiện dọn ref.

Trong ví dụ chính, mỗi callback chỉ tạo một **jstring**, nên **DeleteLocalRef** ngay sau sử dụng rõ ràng hơn.

## 7. Daemon attachment, shutdown và native cancellation

### Daemon không miễn cleanup

**AttachCurrentThread** tạo non-daemon thread và có thể giữ JVM chờ shutdown cho tới khi worker kết thúc. **AttachCurrentThreadAsDaemon** không tự giữ JVM sống, nhưng native worker vẫn phải detach và tránh JNI calls khi VM đã kết thúc.

Khi shutdown một native thread pool, nên ngừng nhận việc, ra tín hiệu dừng, đợi callback Java đang chạy trả về, dọn tài nguyên từng worker, detach từng worker, rồi giải phóng các global registrations hoặc native library resources thuộc pool.

### Native cancellation có thể bỏ qua cleanup

**pthread_cancel**, process termination hoặc C++ exception không được bắt có thể khiến luồng đi qua nhánh không gọi cleanup bình thường. Với C, tập trung các đường lỗi về label **cleanup**; với C++ có thể dùng RAII guard để release JNI resources và detach khi phù hợp.

Nếu ứng dụng cần hủy worker, ưu tiên cooperative stop và bảo đảm cleanup handlers được gọi trên thread đúng và khi JVM còn khả dụng. Không xem destructor, TLS destructor hoặc **JNI_OnUnload** là phép màu khắc phục mọi trường hợp kết thúc bất thường. Không để một native library bị unload khi worker vẫn có thể thực thi code từ library hoặc gọi ngược Java.

### Đừng dựa vào DetachCurrentThread để unlock

Spec mô tả Java monitors còn giữ có thể được giải phóng khi detach, nhưng một chương trình đúng phải **MonitorExit** theo lock ownership trước detach. Native mutex, file handles và malloc buffers không nằm trong trách nhiệm JVM; phải release bằng đúng API native.

## 8. Những sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách làm tốt |
| --- | --- | --- |
| Native pthread exit mà không detach | Vi phạm quy tắc vòng đời JNI thread | Detach trên chính pthread trước exit |
| Mang **JNIEnv*** từ thread Java sang pthread | Interface phụ thuộc thread | Attach/GetEnv trên từng thread |
| Helper detach bất cứ khi nào AttachCurrentThread trả JNI_OK | Thread có thể vốn đã attach | GetEnv trước và theo dõi **attached_here** |
| Detach khi callback Java còn trên stack | Spec không cho phép detach với Java methods đang chạy | Đợi callback quay về native |
| Xóa **jclass local ref** rồi dùng nó trên worker | Local reference không dùng qua thread | Tạo **NewGlobalRef**, xóa khi mọi worker xong |
| Đợi detach mới dọn mọi local refs | Worker dài hạn tích lũy refs | DeleteLocalRef/PopLocalFrame trong từng vòng |
| Nghĩ detach sẽ xóa global/weak global refs | Global refs có lifecycle riêng | DeleteGlobalRef/DeleteWeakGlobalRef đúng owner |
| DeleteLocalRef của String thay cho ReleaseStringUTFChars | Borrowed pointer cần release riêng | Release chars trước xóa String ref |
| Dùng env cũ sau detach | Interface đã không còn hợp lệ | Không gọi JNI, attach lại nếu cần |
| Clear mọi pending exception không báo lỗi | Mất nguyên nhân thất bại | Chuyển/ghi nhận lỗi trước cleanup |
| Daemon worker không cần detach | Daemon chỉ thay đổi shutdown policy | Cleanup và detach như thường |
| Quên native mutex/free/socket | JNI không sở hữu tài nguyên OS | Cleanup theo API native |
| Delete global ref khi worker khác vẫn sử dụng | Dangling reference, có thể crash | Đồng bộ owner/handoff và delete ở cuối đời |

## 9. Tình huống áp dụng

**Native SDK callback trên thread riêng.** SDK tạo pthread, mỗi sự kiện cần báo Java. Attach worker một lần khi nó bắt đầu sử dụng JNI, lưu đúng **JavaVM*** và global callback ref, xóa local refs trong mỗi sự kiện, xử lý exception, detach trước khi SDK worker exit. Nếu SDK có thể gọi lại sau shutdown, đăng ký stop và dừng callback trước giải phóng global refs.

**Thư viện media chạy worker hàng giờ.** Từng frame có thể tạo jbyteArray, jstring hoặc jobject local refs. Không chờ đến cuối buổi để detach rồi mới dọn; dùng **DeleteLocalRef/PopLocalFrame** theo frame. Borrowed primitive arrays phải release riêng và critical regions phải ngắn.

**Plugin tạo thread pool rồi JVM shutdown.** Non-daemon attached threads có thể làm JVM chờ; daemon threads không bảo đảm nốt phần việc sẽ chạy xong. Thiết kế stop/join/cleanup trước VM teardown, không để global refs trỏ tới class loader không còn cần thiết.

**Helper native dùng trong cả Java và C callbacks.** Luôn **GetEnv** để biết đã attach hay chưa. Chỉ người thật sự attach mới detach; trên Java caller thread thì chỉ dọn resources thuộc invocation rồi return.

## 10. Câu hỏi tự kiểm tra

**1.** Java Thread đang gọi một native method. Native method có nên **DetachCurrentThread** trước khi return?

**Đáp án:** Không. Thread do JVM quản lý và vẫn có Java frames trên stack. Hãy release resources thuộc native method rồi return về Java.

**2.** Một pthread dùng **AttachCurrentThread**, gọi Java, xong native thread kết thúc. Chỉ cần OS tự hủy thread?

**Đáp án:** Không. JNI spec yêu cầu native-attached thread gọi **DetachCurrentThread** trước khi kết thúc.

**3.** Sau **NewGlobalRef**, native worker đã detach. Object Java được global ref giữ có tự hết reference không?

**Đáp án:** Không. Global reference phải được **DeleteGlobalRef** đúng lúc theo owner; detach không tự xóa global ref.

**4.** Vì sao local **jstring** tạo trong vòng lặp 100.000 lần nên được xóa ngay?

**Đáp án:** Attached native worker lâu dài có thể giữ local refs cho tới detach, dẫn tới tiêu tốn reference slots, giữ objects khỏi GC và rủi ro bộ nhớ.

**5.** Helper chạy trên thread mà **GetEnv** đã trả **JNI_OK**. Nó có được detach khi xong không?

**Đáp án:** Thường không; attachment thuộc bên đã gắn thread trước đó. Helper chỉ nên detach nếu chính nó đã attach sau **JNI_EDETACHED**.

**6.** Có thể gọi **DetachCurrentThread** trong lúc một **CallStaticObjectMethod** còn đang chạy Java không?

**Đáp án:** Không, cần đợi Java callback trả về native để không còn Java method frames trên stack.

**7.** Native worker đã lấy **const char*** từ **GetStringUTFChars** rồi xóa local ref của jstring. Có coi buffer đã được trả không?

**Đáp án:** Không. Phải **ReleaseStringUTFChars** đúng cặp khi jstring còn hợp lệ, sau đó mới **DeleteLocalRef**.

**8.** Sau khi detach, có thể dùng lại **JNIEnv*** cũ để tạo local ref không?

**Đáp án:** Không. Chỉ dùng JNIEnv* khi thread đang attached và đó là interface của chính thread; nếu phải tiếp tục dùng JNI, attach lại hợp lệ.

## Tài liệu tham khảo

- [JNI Specification Java SE 21 — Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html): AttachCurrentThread, AttachCurrentThreadAsDaemon, GetEnv, DetachCurrentThread, shutdown.
- [JNI Specification Java SE 21 — Global and Local References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#global-and-local-references): NewGlobalRef/DeleteGlobalRef, DeleteLocalRef, PushLocalFrame, PopLocalFrame.
- [JNI Specification Java SE 21 — Weak Global References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#weak-global-references): NewWeakGlobalRef, NewLocalRef, DeleteWeakGlobalRef.
- [JNI Specification Java SE 21 — Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#exceptions): ExceptionCheck, ExceptionOccurred, ExceptionClear, ExceptionDescribe.
- [Android NDK — JNI tips](https://developer.android.com/ndk/guides/jni-tips): kinh nghiệm giữ reference và cleanup trên attached native worker; các quy định Android riêng cần được phân biệt với chuẩn Java SE.

**Ghi nhớ:** *luồng nào tự attach thì luồng đó tự detach khi hoàn tất*, còn mỗi JNI reference và borrowed pointer có owner/cleanup riêng. Dọn tài nguyên khi chúng hết cần thiết, xử lý pending exception có chủ đích, chờ Java callback hoàn tất, và tuyệt đối không dùng JNIEnv* sau detach.