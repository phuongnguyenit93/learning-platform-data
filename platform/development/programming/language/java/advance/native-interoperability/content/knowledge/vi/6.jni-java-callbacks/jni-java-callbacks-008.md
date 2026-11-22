# Gọi phương thức phụ thuộc bên gọi và xử lý trường hợp không có khung Java

Trong JNI (Java Native Interface), mã C/C++ có thể gọi phương thức Java bằng **CallStaticObjectMethod**, **CallObjectMethod** và các hàm cùng họ. Tuy nhiên, một số API Java xác định kết quả hoặc quyền truy cập dựa vào **lớp Java thực sự gọi phương thức** (*caller-sensitive method*). Trên một native thread được gắn vào JVM nhưng không có khung gọi Java thích hợp, một lời gọi JNI trực tiếp tới API như vậy có thể thất bại hoặc hành xử theo quy tắc dự phòng của chính API.

Bài học tập trung vào **cơ chế caller sensitivity khi gọi Java từ JNI**, cách nhận diện bối cảnh không có Java caller frame, và cách thiết kế Java bridge để cung cấp ngữ cảnh gọi rõ ràng. Ví dụ dùng Java 17+ và JNI chuẩn; phần dựng thư viện native minh họa cụ thể trên Linux/POSIX.

## 1. Caller-sensitive method nghĩa là gì?

**Caller-sensitive** là đặc tính của một số phương thức thư viện Java: kết quả, quyền truy cập hoặc class loader mà chúng sử dụng phụ thuộc vào **danh tính lớp Java trực tiếp gọi chúng**. “Caller” ở đây không phải người dùng cuối, không phải thread ID, cũng không phải class bất kỳ được truyền trong tham số. Nó được xác định theo quy tắc của JVM và API đó đối với luồng gọi Java.

Ví dụ điển hình:

- **MethodHandles.lookup()** tạo đối tượng **MethodHandles.Lookup** với quyền tương ứng lớp gọi. Gọi nó bên trong lớp **A** tạo lookup gắn với **A**, gọi trong **B** tạo lookup gắn với **B**. Đây là quyền truy cập nhạy cảm; không được tùy ý cấp một lookup toàn quyền cho mã không tin cậy.
- **Class.forName(String)** chọn class loader dựa vào lớp gọi. Nếu không có Java caller frame, Java SE 21 quy định dùng **system class loader**. Nó có thể trả về lớp khác hoặc ném **ClassNotFoundException** tùy class loader.
- **AccessibleObject.canAccess(Object)** cần ngữ cảnh caller để đánh giá truy cập qua reflection. Khi JNI gọi trong bối cảnh không có Java caller class và cờ override access chưa được bật, kiểm tra thường chỉ chấp nhận member và declaring class công khai trong package được export vô điều kiện.
- **StackWalker.getCallerClass()** yêu cầu lớp ở khung gọi phù hợp. Khi không có caller frame, phương thức có thể ném **IllegalCallerException**; ngoài ra cần cấu hình **RETAIN_CLASS_REFERENCE**.

Lưu ý: **caller-sensitive không có nghĩa tất cả các API sẽ ném cùng một exception**. Mỗi API có hợp đồng riêng khi thiếu caller. Hãy đọc Javadoc phiên bản JDK đang chạy trước khi chọn chiến lược xử lý.

### Phân biệt caller, callee và Java frame

Với lời gọi Java thông thường:

~~~text
Java class A.method()
    |
    +--> MethodHandles.lookup()
              |
              +--> lookupClass() là A
~~~

Với native thread tự gọi JNI:

~~~text
POSIX/native thread
    |
    +--> AttachCurrentThread()
    |
    +--> JNI CallStaticObjectMethod(MethodHandles.lookup)
              |
              +--> không có khung Java caller
              +--> IllegalCallerException
~~~

Tạo một **Java bridge** thay đổi ngữ cảnh:

~~~text
POSIX/native thread
    |
    +--> AttachCurrentThread()
    |
    +--> JNI CallStaticObjectMethod(CallerBridge.lookupFromJava)
              |
              +--> Java frame CallerBridge.lookupFromJava()
                         |
                         +--> MethodHandles.lookup()
                                   |
                                   +--> caller class = CallerBridge
~~~

Việc **AttachCurrentThread** làm thread native có thể tương tác với JVM, nhưng **không tự tạo một Java caller frame cho lời gọi caller-sensitive trực tiếp**. Java bridge thực sự gọi API tại vị trí bytecode do bạn kiểm soát; JVM từ đó có thể xác định caller class phù hợp.

## 2. Khi nào JNI không có khung Java của bên gọi?

Cần phân biệt hai tình huống vận hành:

**Tình huống 1 – Java gọi xuống native rồi native gọi ngược Java.** Một Java thread đang chạy phương thức **native** do Java gọi, nên có thể tồn tại những khung Java ở phía dưới trong ngăn xếp. Tuy nhiên, caller mà API nhạy cảm nhận diện phải tuân theo quy tắc stack walk/access của API đó. Không mặc nhiên suy rằng JNI **CallStaticObjectMethod** luôn có cùng ý nghĩa với một lệnh gọi bytecode đặt trực tiếp ở lớp Java mong muốn.

**Tình huống 2 – Native thread được tạo từ C/C++ rồi attach vào JVM.** Thread này ban đầu chưa có chuỗi gọi Java. Sau **AttachCurrentThread**, nó có **JNIEnv** hợp lệ riêng cho thread nhưng vẫn **không có Java caller class** khi gọi trực tiếp phương thức caller-sensitive. Đây là trường hợp rõ ràng mà JNI Specification cảnh báo.

Tình huống 2 thường xuất hiện trong:

- Callback từ thư viện C/C++ phát sinh ở worker thread do native quản lý;
- Engine xử lý dữ liệu, trình điều khiển, thư viện media/cryptography hoặc event loop native chủ động gọi Java;
- Mã host nhúng JVM qua Invocation API;
- Framework giữ **JavaVM*** để attach native worker thread vào đúng JVM sau đó.

Điều quan trọng nhất là **mô hình thực tế của call stack**, không phải việc đoạn C đã từng được Java gọi ở thời điểm nào khác.

## 3. Phản ứng khi không có caller frame: những ví dụ khác nhau

| API/cách sử dụng | Vì sao phụ thuộc caller | Hành vi đáng chú ý khi JNI gọi trực tiếp không có Java caller |
| --- | --- | --- |
| **MethodHandles.lookup()** | Lookup mang quyền của lớp gọi | Ném **IllegalCallerException** |
| **Class.forName(String)** | Chọn class loader theo lớp gọi | Dùng **system class loader** theo Javadoc Java SE 21 |
| **AccessibleObject.canAccess(obj)** | Kiểm tra quyền truy cập của caller | Với cờ access chưa override, truy cập chỉ thành công theo điều kiện public + package export vô điều kiện |
| **AccessibleObject.trySetAccessible()** | Cân nhắc caller/module để cho phép bỏ kiểm tra truy cập | Khi không có Java caller, không tự có quyền truy cập sâu; Javadoc giới hạn các trường hợp cho phép |
| **StackWalker.getCallerClass()** | Truy xuất caller frame | Ném **IllegalCallerException** nếu không có caller frame (đồng thời yêu cầu **RETAIN_CLASS_REFERENCE**) |

Bảng này nhằm so sánh **hợp đồng API**, không phải cam kết mọi JNI invocation trên mọi phiên bản JDK sẽ có cùng stack hoặc cùng kết quả. Với **AccessibleObject.canAccess**, nếu cờ override access đã được bật hợp lệ thì quy tắc của phương thức vẫn phải được xét đầy đủ; không thể bỏ qua tình trạng của **AccessibleObject**. **Class.forName(String, boolean, ClassLoader)** cho phép cung cấp loader rõ ràng, tránh phụ thuộc class loader ngầm của caller ở biến thể một tham số.

Nguyên tắc an toàn: một API caller-sensitive sử dụng quyền dựa trên *call site* thực tế. **JNI không cấp một cách hợp lệ để “giả mạo” caller class bằng cách ép kiểu một con trỏ hoặc chuyển tên class tùy ý**.

## 4. Thiết kế Java bridge có ngữ cảnh gọi rõ ràng

Khi native cần gọi API caller-sensitive mà không có Java frame thích hợp, tạo phương thức Java cụ thể làm điểm vào. Phương thức đó gọi API trong thân Java của chính nó. Nếu cần load class, tốt hơn là truyền **ClassLoader** có chủ đích hoặc thao tác bằng **Class<?>** đã được nhận an toàn từ Java.

Ví dụ một bridge Java:

~~~java
package demo;

import java.lang.invoke.MethodHandles;

public final class CallerBridge {
    private CallerBridge() {}

    // Khi đoạn bytecode này gọi lookup(), lookupClass() là CallerBridge.
    public static String lookupOwner() {
        return MethodHandles.lookup().lookupClass().getName();
    }

    // Có caller frame rõ ràng; có thể chọn loader tường minh.
    public static Class<?> loadWithoutInitializing(
            String binaryName, ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName(binaryName, false, loader);
    }
}
~~~

Phương thức **lookupOwner()** không trao đối tượng **Lookup** cho native; nó chỉ trả về thông tin quan sát, phù hợp cho bài thực nghiệm. Trong ứng dụng thật, nếu cần quyền lookup để gọi một member, bridge nên **thực hiện thao tác cần thiết trong Java**, xác thực tên lớp/member/yêu cầu đầu vào và chỉ trả về dữ liệu/kết quả tối thiểu. Việc trả một **Lookup** có quyền cao cho mọi native caller có thể vô tình mở rộng ranh giới quyền truy cập.

Đừng nhầm **publicLookup()** và **lookup()**:
- **MethodHandles.lookup()** phản ánh quyền của lớp gọi thực sự; nó có thể truy cập member mà lớp đó được phép truy cập.
- **MethodHandles.publicLookup()** không đòi hỏi caller có Java frame nhưng có quyền truy cập tối thiểu, phù hợp cho public member thuộc package được export vô điều kiện. Theo quy tắc của **MethodHandles.Lookup**, lookup thiếu quyền thích hợp không được dùng để tạo handle đối với caller-sensitive method.
- **lookup.in(Target.class)** hay **privateLookupIn(...)** không phải thủ thuật biến native thành một caller tùy chọn. Chúng tuân theo điều kiện về quyền lookup, accessibility và module opens/exports; không tự tạo quyền mới từ không khí.

## 5. Ví dụ end-to-end: attached POSIX thread, lời gọi JNI trực tiếp và Java bridge

Ví dụ sau chạy với **JDK 17+ trên Linux** và một C compiler có hỗ trợ **pthread**. Nó chứng minh hai cách gọi **MethodHandles.lookup()** từ cùng một native-attached thread.

**Tệp 1 — src/demo/CallerDemo.java**

~~~java
package demo;

import java.lang.invoke.MethodHandles;

public final class CallerDemo {
    static {
        System.loadLibrary("caller_demo");
    }

    private CallerDemo() {}

    // Đây là phương thức Java thường, gọi API nhạy cảm bằng bytecode.
    public static String bridgeCaller() {
        return MethodHandles.lookup().lookupClass().getName();
    }

    // JNI tạo một POSIX thread và attach nó vào JVM.
    private static native void runNativeThread();

    public static void main(String[] args) {
        String caller = MethodHandles.lookup()
                .lookupClass()
                .getName();
        System.out.println("Java main: " + caller);
        runNativeThread();
    }
}
~~~

**Tệp 2 — native/caller_demo.c**

~~~c
#include <jni.h>
#include <pthread.h>
#include <stdio.h>

struct WorkerArgs {
    JavaVM *vm;
    jclass bridge_class;  /* Global reference, không phải local ref */
};

/* Chỉ dùng trong demo để in và xử lý lỗi Java không mong đợi. */
static void print_and_clear(JNIEnv *env, const char *where) {
    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "JNI error at %s:\n", where);
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
}

static void *worker_main(void *opaque) {
    struct WorkerArgs *args = (struct WorkerArgs *)opaque;
    JNIEnv *env = NULL;

    if ((*args->vm)->AttachCurrentThread(
            args->vm, (void **)&env, NULL) != JNI_OK) {
        fputs("AttachCurrentThread failed\n", stderr);
        return NULL;
    }

    /* MethodHandles là lớp JDK; FindClass không cần app loader. */
    jclass methods = (*env)->FindClass(
            env, "java/lang/invoke/MethodHandles");
    if (methods == NULL) {
        print_and_clear(env, "FindClass MethodHandles");
        goto detach;
    }

    jmethodID direct = (*env)->GetStaticMethodID(
            env, methods, "lookup",
            "()Ljava/lang/invoke/MethodHandles$Lookup;");
    if (direct == NULL) {
        print_and_clear(env, "GetStaticMethodID lookup");
        (*env)->DeleteLocalRef(env, methods);
        goto detach;
    }

    /* Không có Java caller frame cho lời gọi trực tiếp này. */
    jobject raw_lookup = (*env)->CallStaticObjectMethod(
            env, methods, direct);

    if ((*env)->ExceptionCheck(env)) {
        jthrowable thrown = (*env)->ExceptionOccurred(env);
        (*env)->ExceptionClear(env);  /* Xử lý exception có chủ đích */

        jclass illegal_caller = (*env)->FindClass(
                env, "java/lang/IllegalCallerException");
        if (illegal_caller != NULL) {
            jboolean expected = (*env)->IsInstanceOf(
                    env, thrown, illegal_caller);
            puts(expected
                 ? "Direct JNI: IllegalCallerException"
                 : "Direct JNI: another exception");
            (*env)->DeleteLocalRef(env, illegal_caller);
        } else {
            print_and_clear(env, "FindClass IllegalCallerException");
        }
        (*env)->DeleteLocalRef(env, thrown);
    } else {
        puts("Direct JNI: no exception (inspect JDK/stack)");
        if (raw_lookup != NULL) {
            (*env)->DeleteLocalRef(env, raw_lookup);
        }
    }
    (*env)->DeleteLocalRef(env, methods);

    /*
     * Không gọi trực tiếp lookup() nữa.
     * Gọi Java bridge trước để tạo Java caller frame.
     * bridge_class là GlobalRef được tạo ở Java thread ban đầu.
     */
    jmethodID bridge = (*env)->GetStaticMethodID(
            env, args->bridge_class, "bridgeCaller",
            "()Ljava/lang/String;");
    if (bridge == NULL) {
        print_and_clear(env, "GetStaticMethodID bridgeCaller");
        goto detach;
    }

    jstring name = (jstring)(*env)->CallStaticObjectMethod(
            env, args->bridge_class, bridge);
    if ((*env)->ExceptionCheck(env) || name == NULL) {
        print_and_clear(env, "CallStaticObjectMethod bridgeCaller");
        goto detach;
    }

    const char *utf = (*env)->GetStringUTFChars(env, name, NULL);
    if (utf != NULL) {
        printf("Via Java bridge: %s\n", utf);
        (*env)->ReleaseStringUTFChars(env, name, utf);
    } else {
        print_and_clear(env, "GetStringUTFChars");
    }
    (*env)->DeleteLocalRef(env, name);

detach:
    (*args->vm)->DetachCurrentThread(args->vm);
    return NULL;
}

/* Tên JNI ánh xạ package demo, class CallerDemo, native method. */
JNIEXPORT void JNICALL
Java_demo_CallerDemo_runNativeThread(JNIEnv *env, jclass clazz) {
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        return;
    }

    /*
     * clazz là local reference của thread đang chạy native method.
     * Chuyển thành global ref trước khi native worker dùng nó.
     */
    jclass global_class = (jclass)(*env)->NewGlobalRef(env, clazz);
    if (global_class == NULL) {
        return; /* JVM có thể đã đặt pending OutOfMemoryError */
    }

    struct WorkerArgs args = { vm, global_class };
    pthread_t thread;
    int status = pthread_create(&thread, NULL, worker_main, &args);

    if (status == 0) {
        /* Đợi worker dùng xong args và global_class rồi mới trả về. */
        (void)pthread_join(thread, NULL);
    } else {
        fprintf(stderr, "pthread_create failed: %d\n", status);
    }

    (*env)->DeleteGlobalRef(env, global_class);
}
~~~

Đây là chương trình đầy đủ minh họa đường đi **Java → JNI tạo native thread → AttachCurrentThread → JNI gọi Java**, dùng **pthread** nên phần C chỉ trực tiếp áp dụng cho Linux/POSIX, không phải mã build sẵn cho Windows. **print_and_clear** được thiết kế cho demo; trong sản phẩm thực tế phải có chính sách chuyển lỗi về nơi giám sát/caller và không tự động xóa mọi exception.

### Biên dịch và chạy trên Linux

Giả sử có **JDK 17 hoặc 21**, **gcc/clang**, **pthread** và biến môi trường **JAVA_HOME** trỏ tới thư mục JDK:

~~~bash
mkdir -p src/demo native out
# Lưu hai tệp Java và C đúng theo các đường dẫn đã ghi ở trên.

javac -d out src/demo/CallerDemo.java

cc -std=c17 -Wall -Wextra -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/caller_demo.c -o libcaller_demo.so

java -Djava.library.path=. -cp out demo.CallerDemo
~~~

Với **JDK 17/21 trên Linux**, giả định build và load native library thành công, stdout dự kiến:

~~~text
Java main: demo.CallerDemo
Direct JNI: IllegalCallerException
Via Java bridge: demo.CallerDemo
~~~

Giải thích từng dòng:

1. **Java main**: **MethodHandles.lookup()** chạy trực tiếp trong **CallerDemo.main**, nên nhận caller là **demo.CallerDemo**.
2. **Direct JNI**: worker native được **AttachCurrentThread** nhưng không có Java caller frame. Theo API **MethodHandles.lookup()**, lời gọi trực tiếp ném **IllegalCallerException**. C gọi **ExceptionOccurred** rồi **ExceptionClear** vì demo chủ động xử lý ngoại lệ này.
3. **Via Java bridge**: native gọi **CallerDemo.bridgeCaller()** bằng JNI. Trong phương thức Java, **MethodHandles.lookup()** nhìn thấy class gọi thực sự là **demo.CallerDemo**, vì thế thành công.

**Lưu ý đối với stdout:** nếu thiếu thư viện, không khớp kiến trúc, compiler không hỗ trợ pthread hoặc một JNI call khác gặp lỗi, chương trình có thể báo exception/stderr hay dừng sớm. Trên Windows cần triển khai luồng native bằng API phù hợp và biên dịch thư viện theo ABI Windows. Ví dụ được thiết kế để minh họa chính xác trường hợp JDK 17/21 Linux đã nêu, không tuyên bố kết quả phổ quát cho mọi JVM.

## 6. Vì sao phải dùng JavaVM*, JNIEnv* và global reference đúng cách?

Ví dụ trên cố ý thể hiện ba quy tắc cần thiết cho native callback:

**JavaVM*** là tay nắm của VM, có thể lưu và chia sẻ cho native thread. Mỗi thread muốn dùng JNI phải lấy **JNIEnv*** của *chính thread ấy* bằng **AttachCurrentThread** hoặc API thích hợp. **JNIEnv*** là giao diện theo thread; tuyệt đối không chuyển con trỏ **JNIEnv*** nhận trong native method của thread Java sang pthread mới.

**jclass clazz** truyền vào **runNativeThread** là JNI local reference. Local reference có phạm vi gắn với thread/khung local reference, nên không thể tùy ý lưu để worker khác sử dụng. **NewGlobalRef** giúp giữ class object tồn tại và dùng hợp lệ giữa thread; cần **DeleteGlobalRef** khi không dùng nữa. Ví dụ đợi worker kết thúc bằng **pthread_join** rồi mới giải phóng global ref; đối tượng **args** đặt trên stack vẫn còn sống cho đến khi join hoàn tất.

**AttachCurrentThread** gắn native thread vào JVM; khi công việc kết thúc, **DetachCurrentThread** tháo nó ra. Một thread không được detach trong khi đang có Java method frames chạy trên stack. Ví dụ chỉ detach **sau khi** lời gọi bridge kết thúc. Trên luồng chạy lâu dài, phải cân nhắc giới hạn local reference và giải phóng các ref đã dùng; attached thread không có vòng đời dọn local refs giống một lần native method thông thường cho đến lúc detach.

Quy tắc thực hành:

~~~text
Native worker được tạo
    → AttachCurrentThread lấy JNIEnv* riêng
    → dùng global refs / JavaVM* đã quản lý vòng đời
    → tìm method đúng chữ ký JNI
    → Call...Method và kiểm tra exception
    → xử lý/ghi nhận kết quả và giải phóng local refs
    → DetachCurrentThread
    → phía sở hữu xóa global refs khi an toàn
~~~

## 7. Exception phát sinh từ phương thức caller-sensitive

Một JNI **Call...Method** có thể để lại **pending Java exception** thay vì trả về kết quả có thể sử dụng. Cần kiểm tra **ExceptionCheck()** hoặc **ExceptionOccurred()** ngay sau những điểm gọi có thể ném, trước khi dùng object trả về.

~~~c
/* Đoạn minh họa độc lập trong một native method đã có env, owner, mid. */
jobject result = (*env)->CallStaticObjectMethod(env, owner, mid);

if ((*env)->ExceptionCheck(env)) {
    /* Có pending Java exception: đừng sử dụng result. */
    /* Lựa chọn A: return về Java để JVM ném exception. */
    return;
}

/* Chỉ sử dụng result nếu hợp đồng phương thức cho phép và đã kiểm tra. */
~~~

Đoạn trên là **fragment** cho hàm JNI có kiểu trả về **void**; trong hàm trả về giá trị khác cần dùng cách return tương ứng. Không được áp dụng fragment này nguyên xi bên trong một **pthread worker** không có Java caller để nhận ngoại lệ: worker phải có chính sách rõ ràng để xử lý, ghi nhận, chuyển qua callback Java phù hợp hoặc báo lỗi tới chủ sở hữu công việc.

Hai lựa chọn xử lý khác nhau:

- **Để exception pending và trả về native method do Java gọi**: JVM có thể chuyển exception lên Java caller. Không gọi tiếp các JNI API không được phép sử dụng khi đang có exception pending.
- **Tự xử lý exception trong native**: đọc ngoại lệ với **ExceptionOccurred**, làm sạch với **ExceptionClear**, ghi log/đóng gói kết quả lỗi rồi tiếp tục khi trạng thái đã hợp lệ. Không xóa lặng lẽ mọi exception; **OutOfMemoryError**, lỗi linkage và lỗi dữ liệu khác cần xử lý đúng mức.

Trong demo, việc xóa **IllegalCallerException** sau khi phân loại là chủ đích để tiếp tục chạy đường bridge. **ExceptionDescribe** cũng có thể in stack trace phục vụ chẩn đoán nhưng không nên xem là phương thức xử lý production hoàn chỉnh.

Khi sử dụng **MethodHandles.lookup()**, kiểm tra loại lỗi thật sự; không bắt mọi **RuntimeException** rồi mặc định “thiếu caller”. Lỗi do package/module, chữ ký member, null input hoặc ClassLoader có thể có nguyên nhân độc lập.

## 8. Tương tác với class loader và quyền truy cập module

Một tình huống dễ nhầm: native worker gọi **FindClass("com/example/Plugin")** và không tìm thấy dù class tồn tại trong ứng dụng.

Theo JNI Specification, **FindClass** từ native method bình thường thường dùng class loader của lớp khai báo native method. Khi gọi trong ngữ cảnh Invocation Interface mà không có native method/class loader gắn với Java stack, nó dùng **system class loader**. Các lớp do plugin loader/custom loader nạp có thể không được system loader nhìn thấy.

Đây là vấn đề liên quan nhưng **không đồng nhất** với caller sensitivity:

- **Caller-sensitive** là đặc tính của phương thức Java được gọi, chẳng hạn **Class.forName(String)** dùng class loader của caller.
- **JNI FindClass** là hàm JNI dùng quy tắc chọn loader riêng tùy bối cảnh native method/Invocation Interface.
- **Thread.currentThread().getContextClassLoader()** là một thuộc tính thread có thể cấu hình; nó **không tự động đồng nghĩa** với caller class loader và không biến một native call thành bytecode call từ lớp Java tùy chọn.

Cách giải quyết có chủ đích:

1. Truyền **Class<?>** đã được Java resolve vào native, tạo **global ref** khi cần giữ qua thread và gọi method trên chính class đó;
2. Truyền một **ClassLoader** được phép dùng rồi gọi **Class.forName(name, false, loader)** qua Java bridge;
3. Đặt thao tác chọn loader trong Java bridge thuộc đúng module/lớp cần chịu trách nhiệm;
4. Kiểm tra **module exports/opens**, access level và quyền của **MethodHandles.Lookup** thay vì dùng phản chiếu để vượt kiểm tra hợp lệ.

Ví dụ **Class.forName(String)** có thể không throw chỉ vì thiếu caller; nó dùng system loader và có thể *load sai bản class* khi ứng dụng có nhiều class loader. Nếu cùng binary name tồn tại ở nhiều loader, **Class<?>** của chúng là các identity khác nhau; hậu quả có thể là **ClassCastException**, **LinkageError** hoặc lỗi không tìm thấy class. Đây là lý do phải xác định loader như một phần hợp đồng native ↔ Java.

## 9. Không biến Java bridge thành điểm nâng quyền tùy tiện

Bridge tạo ra một caller hợp lệ, nhưng **caller đó chính là lớp Java chứa bridge**, không phải một danh tính bất kỳ mà native yêu cầu. Đặt bridge ở package/module nào sẽ quyết định quyền truy cập của nó.

Một thiết kế an toàn thường làm như sau:

~~~java
package demo;

import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class SafeBridge {
    private SafeBridge() {}

    /*
     * Ví dụ kiểm soát thao tác cụ thể: chỉ gọi phương thức public được
     * lựa chọn trước, không nhận tên member tùy ý từ native/untrusted code.
     */
    public static int twice(int value) {
        return Math.multiplyExact(value, 2);
    }

    // Chỉ để minh họa: lookup gắn với SafeBridge.
    public static Class<?> lookupIdentity() {
        return MethodHandles.lookup().lookupClass();
    }
}
~~~

Đây là **Java-only fragment** không tự load thư viện native. **twice** minh họa ranh giới hẹp có contract rõ ràng, còn **lookupIdentity** cho thấy caller Java thực sự. **Math.multiplyExact** ném **ArithmeticException** khi overflow, phản ánh quy tắc kiểm tra lỗi thay vì trả kết quả wrap ngầm.

Tránh các phản mẫu:
- Bridge công khai nhận tên class/member rồi dùng một **Lookup** toàn quyền để đọc/ghi mọi private member mà không kiểm tra chính sách;
- Native lưu **Lookup** quyền cao và phát tán nó cho plugin không tin cậy;
- Gọi **setAccessible(true)** hoặc **privateLookupIn** như một cách mặc nhiên vượt module encapsulation;
- Dùng **publicLookup()** rồi giả định có thể gọi mọi API caller-sensitive hoặc mọi member không public;
- Coi sự xuất hiện của một Java frame bất kỳ là bằng chứng cho quyền của *lớp Java được kỳ vọng*. Caller thực tế phải được kiểm tra ở vị trí API thực thi.

Caller sensitivity là một phần của **quy tắc quyền truy cập của Java**. Java bridge hợp lệ có thể giải quyết việc thiếu caller frame, nhưng không phải công cụ để cấp đặc quyền vượt quá hợp đồng và policy của ứng dụng.

## 10. Quy trình debug khi native gọi Java không như mong đợi

Khi một phương thức chạy được từ Java nhưng hỏng khi gọi từ JNI, lần lượt kiểm tra:

| Dấu hiệu | Câu hỏi cần xác minh | Hành động |
| --- | --- | --- |
| **IllegalCallerException** khi gọi **MethodHandles.lookup()** | Thread có được attach từ native và đang thiếu Java caller frame không? | Gọi qua Java bridge hoặc dùng **publicLookup()** nếu chỉ cần public access |
| **ClassNotFoundException** hoặc **NoClassDefFoundError** | Loader nào đang được sử dụng? Có custom module/class loader không? | Truyền **Class<?>/ClassLoader** đúng nguồn; tránh suy luận từ tên class |
| **NoSuchMethodError** từ **GetMethodID/GetStaticMethodID** | JNI descriptor đúng package, tên, static/instance và kiểu trả về chưa? | Dùng tên nhị phân và chữ ký chính xác; kiểm tra exception pending |
| **IllegalAccessException** hoặc access bị từ chối | Caller lookup class, module export/open và access modifier là gì? | Chỉnh contract/bridge/module config một cách có chủ đích |
| **canAccess** trả false | Đang chạy dưới caller nào; cờ access và module exports thế nào? | Kiểm tra Javadoc; không coi false là thiếu JNI attachment |
| Native crash hoặc lỗi ngẫu nhiên | **JNIEnv*** có bị dùng sai thread? Local ref có bị dùng xuyên thread? | Dùng **AttachCurrentThread**, **NewGlobalRef** và đúng vòng đời |
| JNI Call trả null hoặc không có kết quả | Có pending Java exception không? | Gọi **ExceptionCheck/ExceptionOccurred** trước khi sử dụng kết quả |

Dùng **javap -s** hoặc **javac -h** để kiểm tra descriptor và tên JNI khi build. Với phương thức bridge **public static String bridgeCaller()**, descriptor là **()Ljava/lang/String;**; với **MethodHandles.lookup()**, descriptor là **()Ljava/lang/invoke/MethodHandles$Lookup;**. Trong JNI, tên lớp dùng dấu **/** thay cho dấu **.**, nested class dùng dấu **$** trong descriptor. Sai descriptor khác hoàn toàn với lỗi do thiếu caller frame, dù cả hai cùng xảy ra ở lời gọi JNI.

Có thể kiểm tra Java bridge đơn giản mà không cần native:

~~~java
import java.lang.invoke.MethodHandles;

public class CallerIdentity {
    static final class One {
        static String inspect() {
            return MethodHandles.lookup().lookupClass().getSimpleName();
        }
    }
    static final class Two {
        static String inspect() {
            return MethodHandles.lookup().lookupClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println(One.inspect());
        System.out.println(Two.inspect());
    }
}
~~~

Lưu thành **CallerIdentity.java**, chạy:

~~~bash
javac CallerIdentity.java
java CallerIdentity
~~~

Stdout:

~~~text
One
Two
~~~

Cả hai nhánh đều gọi **MethodHandles.lookup()** nhưng mỗi lời gọi được viết trong **bytecode của một class khác nhau**, nên kết quả phụ thuộc đúng class gọi. Đây là bằng chứng Java-only về cơ chế caller-sensitive; nó **không** thay thế thí nghiệm native-attached thread trong mục 5.

## 11. Câu hỏi tự kiểm tra

**1.** Native worker đã gọi **AttachCurrentThread** thành công. Có thể coi nó như một Java caller cho **MethodHandles.lookup()** chưa?

**Đáp án:** Chưa. Attach cung cấp **JNIEnv*** và liên kết thread với VM; nó không tự tạo khung Java gọi **lookup()**. Gọi trực tiếp từ JNI attached thread thiếu frame sẽ ném **IllegalCallerException** theo Javadoc.

**2.** Tại sao đi qua **CallerDemo.bridgeCaller()** lại hoạt động?

**Đáp án:** **bridgeCaller** là phương thức Java thực sự được thực thi. Lệnh gọi **MethodHandles.lookup()** nằm trong bytecode của lớp **CallerDemo**, nên JVM biết caller class tương ứng. Kết quả **Lookup** hoặc thao tác phụ thuộc quyền của **CallerDemo**, không phải native thread.

**3.** Nếu thiếu caller class, mọi API caller-sensitive đều ném **IllegalCallerException**?

**Đáp án:** Không. **Class.forName(String)** có quy tắc dùng system class loader khi không có caller frame. **AccessibleObject.canAccess** có các quy tắc truy cập riêng. Luôn kiểm tra Javadoc của từng phương thức.

**4.** Tại sao không thể chuyển **JNIEnv*** từ Java thread sang một pthread rồi gọi **CallStaticObjectMethod**?

**Đáp án:** **JNIEnv*** chỉ hợp lệ cho thread đã sở hữu nó. Native worker cần gọi **AttachCurrentThread** để lấy **JNIEnv*** riêng; đối tượng Java muốn dùng xuyên thread phải có reference phù hợp, thường là global reference.

**5.** Java bridge nằm trong module A có thể tự nhận quyền private của module B bằng **MethodHandles.lookup()**?

**Đáp án:** Không. Lookup phản ánh quyền của lớp bridge và module rules; **privateLookupIn**, nếu được dùng, cũng kiểm tra điều kiện truy cập/module opens. Thiết kế bridge phải xác thực thao tác và không phát tán capability nhạy cảm.

## Tài liệu tham khảo chính thức

- JNI Design Overview — **Calling Caller-Sensitive Methods**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- JNI Invocation API — **AttachCurrentThread**, **DetachCurrentThread**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html
- JNI Functions — **FindClass**, **Call...Method**, **ExceptionCheck**, **NewGlobalRef**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- **MethodHandles.lookup()** — hành vi khi không có caller frame: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.html
- **Class.forName(String)** và class loader khi không có Java caller: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- **AccessibleObject.canAccess** và module access: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- **StackWalker.getCallerClass**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/StackWalker.html

**Ghi nhớ:** Native có thể gọi Java thông qua JNI, nhưng **quyền và ngữ nghĩa caller-sensitive phụ thuộc khung gọi Java thật**. Khi caller frame vắng mặt, mỗi API quyết định cách xử lý riêng. Một Java bridge có trách nhiệm, có caller class rõ ràng và giới hạn quyền hợp lý là cách thiết kế dễ kiểm chứng cho native callback.