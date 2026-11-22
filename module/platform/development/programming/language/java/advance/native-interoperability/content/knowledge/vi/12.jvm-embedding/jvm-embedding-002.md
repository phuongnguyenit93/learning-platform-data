# Chuẩn bị JavaVMInitArgs, tùy chọn JVM và liên kết với thư viện JVM

## 1. Vì sao ứng dụng native cần JavaVMInitArgs?

Trong mô hình thông thường, **java launcher** khởi động JVM rồi gọi phương thức **main** của một lớp Java. Trong mô hình **nhúng JVM** (*embedding*), chương trình C/C++ là tiến trình chủ: nó tự nạp thư viện máy ảo, cấu hình JVM, gọi **JNI_CreateJavaVM**, sau đó dùng **JNIEnv** để tìm lớp và gọi phương thức Java. API thực hiện việc này là **JNI Invocation API**, được khai báo trong **jni.h**.

Luồng điển hình:

~~~text
Native host (C/C++)
       |
       |  Chọn JDK/runtime và ABI tương thích
       |  Chuẩn bị JavaVMOption[] và JavaVMInitArgs
       v
JNI_CreateJavaVM(...)
       |
       +----> JavaVM* : tay nắm JVM, dùng cho quản lý vòng đời/thread
       |
       +----> JNIEnv* : giao diện JNI chỉ hợp lệ với thread hiện tại
       |
       v
FindClass -> GetStaticMethodID -> CallStatic...Method
       |
       |  Kiểm tra Java exception, giải phóng JNI local refs
       v
DestroyJavaVM(...)
       |
       v
Native host hoàn tất
~~~

**JavaVMInitArgs** là cấu hình lúc tạo VM. Nó không phải đối tượng Java, không phải bộ nhớ heap Java và không phải cơ chế đổi toàn bộ cờ JVM tùy ý sau khi VM đã chạy. **JNI_CreateJavaVM** là ranh giới khởi tạo; vấn đề chọn thư viện nào, chuyển option nào và tìm class ở đâu phải được giải quyết trước hoặc trong lần khởi tạo đó.

**Phân biệt rõ hai hướng JNI:**

- **Java gọi native**: JVM đã chạy, Java gọi **System.loadLibrary** rồi gọi phương thức **native**; thư viện native được nạp *vào JVM hiện có*.
- **Native nhúng Java**: tiến trình C/C++ là chủ, liên kết/nạp **libjvm.so**, **jvm.dll** hoặc biến thể theo hệ điều hành rồi gọi **JNI_CreateJavaVM**. Không cần một phương thức Java **native** để khởi tạo VM.

Hai mô hình dùng cùng giao diện **JNIEnv** khi làm việc với Java object nhưng quy trình khởi tạo, đường dẫn thư viện và trách nhiệm shutdown khác nhau.

## 2. Cấu trúc JavaVMInitArgs và JavaVMOption

Các khai báo rút gọn trong JNI Invocation API:

~~~c
typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;
~~~

| Trường | Mục đích | Cách dùng |
| --- | --- | --- |
| **version** | Phiên bản JNI interface mà host yêu cầu | Ví dụ **JNI_VERSION_1_8** cho host sử dụng các API có từ JNI 8; **không** chọn Java language level |
| **nOptions** | Số phần tử hợp lệ trong **options** | Phải khớp độ dài mảng; không phải tổng số ký tự và không đếm phần tử kết thúc null |
| **options** | Con trỏ tới mảng **JavaVMOption** | Mỗi phần tử chứa một option string hoàn chỉnh |
| **ignoreUnrecognized** | Cách xử lý option không nhận diện | Thường đặt **JNI_FALSE** khi cần phát hiện sai cấu hình sớm |
| **optionString** | Tùy chọn JVM bằng chuỗi char | Ví dụ **-Djava.class.path=out**, **-Xmx128m** |
| **extraInfo** | Dữ liệu đặc biệt cho một số option hook | Đặt **NULL** cho các option chuỗi thông thường |

Điều kiện cơ bản: tất cả con trỏ phải hợp lệ tại thời điểm gọi **JNI_CreateJavaVM**; **nOptions** và mảng option phải khớp; mỗi chuỗi **optionString** phải là chuỗi C kết thúc bằng byte NUL. JNI mô tả option string dùng **mã hóa mặc định của nền tảng**; khi đường dẫn/giá trị chứa Unicode đặc biệt, cần kiểm tra cách mã hóa của runtime/OS thay vì mặc định mọi chuỗi C UTF-8 đều hoạt động như nhau.

Ví dụ khởi tạo cấu hình C17:

~~~c
#include <jni.h>
#include <stddef.h>

static char classpathOption[] = "-Djava.class.path=out";
static char modeOption[]      = "-Ddemo.mode=embedded";
static char heapOption[]      = "-Xmx128m";

static JavaVMOption options[] = {
    { classpathOption, NULL },
    { modeOption, NULL },
    { heapOption, NULL }
};

JavaVMInitArgs args = {0};
args.version = JNI_VERSION_1_8;
args.nOptions = (jint)(sizeof options / sizeof options[0]);
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
~~~

Đoạn trên là **fragment chuẩn bị dữ liệu**, chưa phải chương trình có **main**. Giá trị **-Djava.class.path=out** giả định host chạy từ thư mục dự án, nơi **out/** chứa các file **.class**. Trong ứng dụng phân phối thật, đường dẫn nên được tạo từ vị trí cài đặt có kiểm soát; đừng phụ thuộc working directory ngẫu nhiên.

Tại sao dùng **JavaVMInitArgs args = {0}**? Cách này khởi tạo những trường chưa gán về 0/null, tránh dữ liệu rác. Nhưng vẫn phải gán **version**, **nOptions**, **options** và chính sách **ignoreUnrecognized** theo hợp đồng. Trong code lớn, ưu tiên để những chuỗi và mảng option tồn tại đến khi **JNI_CreateJavaVM** hoàn tất, không trỏ tới buffer đã hết vòng đời.

## 3. Chọn JNI version: không nhầm với phiên bản JDK

**JNI_VERSION_1_8**, **JNI_VERSION_1_6** hay các hằng JNI version mới hơn là **mã phiên bản giao diện native**. Chúng không yêu cầu JVM chạy bytecode Java 8 và cũng không biến JDK 21 thành JDK 8. Ví dụ chương trình Java được biên dịch bằng JDK 21 vẫn có thể được host dùng **JNI_VERSION_1_8** nếu các API JNI cần dùng tương thích.

~~~c
args.version = JNI_VERSION_1_8;
jint code = JNI_CreateJavaVM(&vm, (void **)&env, &args);
~~~

Nếu JDK đang dùng không hỗ trợ version yêu cầu, lệnh khởi tạo có thể thất bại với mã lỗi JNI thích hợp. Không đoán mã version dựa trên **java -version** rồi tự gán số tùy ý; dùng hằng được cung cấp bởi **jni.h** thuộc bộ JDK đang build và kiểm tra kết quả từ runtime.

**JNI_GetDefaultJavaVMInitArgs** là hàm tùy chọn khi cần truy vấn một cấu hình mặc định và kiểm tra version. Cách dùng:

~~~c
JavaVMInitArgs defaults = {0};
defaults.version = JNI_VERSION_1_8;

jint rc = JNI_GetDefaultJavaVMInitArgs(&defaults);
if (rc != JNI_OK) {
    /* Phiên bản JNI được yêu cầu có thể không được hỗ trợ. */
}
~~~

Đây cũng là **fragment**; ví dụ đầy đủ ở phần 6 dùng trực tiếp **JavaVMInitArgs**, đúng như hướng dẫn JNI hiện đại: không bắt buộc phải gọi **JNI_GetDefaultJavaVMInitArgs** trước **JNI_CreateJavaVM**. Không trộn trường từ một cấu hình default được lấy trước đó với một mảng options khác mà quên cập nhật **nOptions**.

## 4. Tùy chọn JVM truyền qua JavaVMOption

**JavaVMOption.optionString** chứa một option cho từng phần tử. Không phải shell command nguyên dòng, cũng không phải danh sách tách bằng dấu cách.

| Option được truyền | Ý nghĩa thực tế | Ghi chú |
| --- | --- | --- |
| **-Djava.class.path=out** | Class path để nạp lớp Java của ứng dụng | Hữu ích cho **FindClass** từ host với classpath application classes |
| **-Ddemo.mode=embedded** | System property tùy chọn của ứng dụng | Có thể đọc bằng **System.getProperty("demo.mode")** |
| **-Djava.library.path=/opt/app/native** | Đường tìm thư viện native cho các thao tác Java như **System.loadLibrary** | **Không** phải đường tìm chính **libjvm.so** của OS loader |
| **-Xms32m** | Kích thước heap ban đầu, tùy JVM | Thường dùng trên HotSpot; kiểm tra hỗ trợ và giới hạn môi trường |
| **-Xmx128m** | Kích thước heap tối đa, tùy JVM | Heap không bằng tổng bộ nhớ tiến trình: còn native memory, stack, code cache... |
| **-verbose:jni** | In thông tin JNI theo khả năng runtime | Phục vụ chẩn đoán, tăng lượng log |
| **--module-path=/opt/app/mods** | Module path trong môi trường module hỗ trợ | Cần một option string với dấu **=** |
| **--add-modules=my.module** | Chọn module root nếu cần | Kiểm tra module thực tồn tại |
| **--add-opens=java.base/java.lang=ALL-UNNAMED** | Mở package cụ thể cho reflection sâu trong phạm vi đã nêu | Chỉ cấp khi có lý do; ảnh hưởng ranh giới module |

**Option “chuẩn” của JNI Invocation API** bao gồm **-D...**, **-verbose...** và các hook đặc biệt **vfprintf**, **exit**, **abort**. Nhiều cờ **-X...** và **-XX:...** mang tính implementation-specific; đừng đặt chúng thành hợp đồng portable cho mọi JVM. Các option module trong JNI phải có dạng **--option=value**, ví dụ **--module-path=mods**, không dùng cặp chuỗi **"--module-path"**, **"mods"** như hai đối số command line.

### Khác biệt quan trọng giữa launcher và Invocation API

Lệnh shell:

~~~bash
java -cp out -Xmx128m demo.EmbeddedGreeting
~~~

được **java launcher** phân tích: **-cp** đi kèm một tham số; launcher biết phải chọn lớp Java nào để chạy. Khi dùng **JNI_CreateJavaVM**, không có launcher phân tích lệnh rồi tự tìm **main**. Host phải chuyển các VM options qua **JavaVMOption**, chẳng hạn:

~~~c
options[0].optionString = "-Djava.class.path=out";
options[1].optionString = "-Xmx128m";
~~~

Sau khi khởi tạo thành công, host **tự gọi JNI FindClass/GetStaticMethodID/Call...Method**. Không truyền nguyên **"java -cp out demo.EmbeddedGreeting"** thành một **optionString**; đây không phải giao diện gọi lệnh shell.

### ignoreUnrecognized: JNI_TRUE không có nghĩa “bỏ qua mọi thứ”

Theo JNI Invocation API, khi **ignoreUnrecognized == JNI_TRUE**, JVM được yêu cầu bỏ qua các option không nhận diện **bắt đầu bằng -X hoặc dấu gạch dưới _**. Điều này **không** đồng nghĩa mọi chuỗi không hợp lệ đều được chấp nhận; các lỗi khởi tạo, đường dẫn và hạn chế của implementation vẫn phải xử lý.

Khi **ignoreUnrecognized == JNI_FALSE**, unrecognized option gây khởi tạo thất bại (thường là **JNI_ERR**). Nên chọn **JNI_FALSE** cho hệ thống cần fail fast: lỗi gõ nhầm cấu hình JVM không nên biến thành chạy với default lặng lẽ.

**Không bỏ qua kiểm chứng ngay cả khi CreateJavaVM trả JNI_OK.** Đọc lại system properties cần thiết, phiên bản runtime, class loader/module thực tế và chạy một smoke test nhỏ để xác nhận những giá trị mà ứng dụng phụ thuộc.

## 5. Liên kết với thư viện JVM: ba thời điểm khác nhau

Một host C/C++ muốn gọi **JNI_CreateJavaVM** phải có cả header JNI, khai báo hàm và một cách tìm được implementation của JVM. Ba lớp trách nhiệm:

~~~text
Thời điểm biên dịch:
    jni.h + jni_md.h
         |
         v
    Compiler biết JavaVMInitArgs, JNI types, JNI_CreateJavaVM

Thời điểm liên kết (link):
    -ljvm / jvm.lib hoặc dlsym/GetProcAddress
         |
         v
    Linker giải quyết symbol JNI_CreateJavaVM

Thời điểm chạy:
    OS loader tìm libjvm.so / jvm.dll / libjvm.dylib
         |
         v
    JVM được nạp; JNI_CreateJavaVM mới có thể khởi tạo runtime
~~~

**Header khác thư viện:**

- **$JAVA_HOME/include/jni.h**: khai báo kiểu và hàm JNI chung.
- **$JAVA_HOME/include/linux/jni_md.h**, **include/win32/jni_md.h** hoặc **include/darwin/jni_md.h**: định nghĩa phụ thuộc ABI/OS.
- **$JAVA_HOME/lib/server/libjvm.so**: JVM runtime trên nhiều bản JDK Linux HotSpot.
- **$JAVA_HOME/lib/server/libjvm.dylib**: đường dẫn phổ biến trên macOS HotSpot.
- **%JAVA_HOME%\lib\jvm.lib**: import library dùng khi MSVC link trên Windows; **%JAVA_HOME%\bin\server\jvm.dll**: DLL được OS loader nạp khi chạy. Layout thực tế phải xác minh theo JDK distribution.

Đường dẫn thư viện **phụ thuộc JDK vendor, phiên bản, kiến trúc và bản đóng gói**. Đừng viết cứng một đường dẫn JDK toàn hệ thống cho ứng dụng phân phối. **JAVA_HOME** là quy ước môi trường giúp script tìm JDK; nó không tự động bảo đảm dynamic loader của hệ điều hành biết vị trí libjvm.

### 5.1. Link tại build time với thư viện động

Trên Linux, compiler dùng **-I** tìm header, **-L** tìm thư viện lúc link, **-ljvm** yêu cầu resolve symbol từ JVM. Khi chạy, Linux loader vẫn cần tìm **libjvm.so** qua **RPATH/RUNPATH**, cấu hình loader hoặc đường dẫn runtime phù hợp.

Một lựa chọn thường dùng cho demo là **-Wl,-rpath,...**; trên hệ thống phân phối chính thức nên cân nhắc đường dẫn tương đối từ vị trí ứng dụng, hoặc cơ chế cấu hình thư viện được quản lý. Để kiểm tra binary, có thể dùng **ldd** và **readelf -d** trên môi trường tin cậy.

### 5.2. Load thư viện tại runtime bằng API hệ điều hành

Nếu ứng dụng cho phép chọn một trong nhiều JVM cài đặt, host có thể dùng **dlopen + dlsym** (POSIX/Linux) hoặc **LoadLibrary + GetProcAddress** (Windows) để tìm **JNI_CreateJavaVM**. Lúc đó không nhất thiết link trực tiếp **-ljvm** ở build time, nhưng phải:

1. Mở đúng thư viện JVM tương thích kiến trúc/ABI;
2. Tìm symbol JNI cần thiết, xác định kiểu hàm và calling convention đúng;
3. Giữ thư viện còn sống trong toàn bộ vòng đời JVM;
4. Xử lý đầy đủ lỗi nạp DLL/dependency và dọn tài nguyên khi VM đã kết thúc.

Mã ví dụ đầy đủ dưới đây dùng **liên kết trực tiếp với thư viện động** để tập trung vào **JavaVMInitArgs**; nó không tự triển khai trình tìm JDK tùy chọn.

### 5.3. Không nhầm ba đường dẫn

| Đường dẫn | Do thành phần nào dùng? | Ví dụ |
| --- | --- | --- |
| Java classpath | Java class loader | **-Djava.class.path=out** |
| Java native library path | JVM tìm native library cho **System.loadLibrary** | **-Djava.library.path=/opt/app/native** |
| OS loader path của JVM | OS tìm **libjvm.so/jvm.dll** để host C khởi tạo VM | RPATH/RUNPATH, PATH hoặc cơ chế nạp động |

Khi gặp lỗi không tìm lớp, kiểm tra **classpath/module path**; khi gặp **UnsatisfiedLinkError** từ Java, kiểm tra native library path, dependency và ABI; khi executable C không khởi động vì thiếu **libjvm.so**, kiểm tra **OS loader path**. Sửa đường dẫn này thường **không tự sửa** vấn đề thuộc đường dẫn kia.

## 6. Ví dụ hoàn chỉnh: C khởi tạo JVM, gọi Java và hủy JVM

Ví dụ sau dành cho JDK 17+ và HotSpot-compatible distribution có các đường dẫn như mục 5. Nó truyền **ba VM option**, kiểm tra mã trả về **JNI_CreateJavaVM**, gọi phương thức Java bằng JNI rồi gọi **DestroyJavaVM**. Java class không cần có **main**, vì tiến trình C chủ động chọn method cần gọi.

### 6.1. File Java: src/demo/EmbeddedGreeting.java

~~~java
package demo;

public final class EmbeddedGreeting {
    private EmbeddedGreeting() {
    }

    public static int compute(int input) {
        String mode = System.getProperty("demo.mode", "missing");
        System.out.println("Java mode: " + mode);
        return Math.addExact(Math.multiplyExact(input, 2), 1);
    }
}
~~~

**Math.multiplyExact** và **Math.addExact** kiểm tra overflow; với input **21**, kết quả chính xác là **43**. Lời in **Java mode: embedded** chứng minh option **-Ddemo.mode=embedded** thực sự đến được JVM.

### 6.2. File C: host/embed_jvm.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Mỗi option là chuỗi C kết thúc NUL và tồn tại khi VM khởi tạo. */
static char classpath_option[] = "-Djava.class.path=out";
static char mode_option[] = "-Ddemo.mode=embedded";
static char heap_option[] = "-Xmx128m";

int main(void) {
    JavaVMOption options[] = {
        { classpath_option, NULL },
        { mode_option, NULL },
        { heap_option, NULL }
    };

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = (jint)(sizeof options / sizeof options[0]);
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    jint created = JNI_CreateJavaVM(&vm, (void **)&env, &args);
    if (created != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)created);
        return EXIT_FAILURE;
    }

    int exit_code = EXIT_FAILURE;
    jclass cls = (*env)->FindClass(env, "demo/EmbeddedGreeting");

    if (cls == NULL) {
        goto cleanup;
    }

    jmethodID compute = (*env)->GetStaticMethodID(
            env, cls, "compute", "(I)I");
    if (compute == NULL) {
        goto cleanup;
    }

    jint answer = (*env)->CallStaticIntMethod(
            env, cls, compute, (jint)21);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    printf("C result: %d\n", (int)answer);
    exit_code = EXIT_SUCCESS;

cleanup:
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
        exit_code = EXIT_FAILURE;
    }

    if (cls != NULL) {
        (*env)->DeleteLocalRef(env, cls);
    }

    jint destroyed = (*vm)->DestroyJavaVM(vm);
    if (destroyed != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n", (int)destroyed);
        exit_code = EXIT_FAILURE;
    }

    return exit_code;
}
~~~

Đây là **chương trình C17 độc lập có main**, không phải JNI native method do Java gọi. **JNI_CreateJavaVM** và **DestroyJavaVM** là hàm thuộc Invocation API; C dùng **(*env)->...** vì trong C **JNIEnv** dựa trên con trỏ tới bảng hàm. Trong C++ cú pháp tương ứng thường là **env->FindClass(...)** và **vm->DestroyJavaVM()**.

**Kiểm tra từng bước:**

1. **options[]** gồm classpath, property tùy chỉnh và giới hạn heap.
2. **args** được zero-initialize và gán các trường bắt buộc; **ignoreUnrecognized=JNI_FALSE** giúp bắt lỗi option.
3. **JNI_CreateJavaVM** trả **JavaVM*** và **JNIEnv*** của thread gọi. Khi tạo thất bại, không được dùng hai pointer như thể VM đã tồn tại.
4. **FindClass("demo/EmbeddedGreeting")** dùng **tên lớp nội bộ JVM** với dấu **/**. File class phải ở **out/demo/EmbeddedGreeting.class**.
5. **GetStaticMethodID** với descriptor **(I)I**: nhận một **int**, trả một **int**. Phương thức Java là **static**; không dùng **CallIntMethod** dành cho đối tượng.
6. **CallStaticIntMethod** gọi Java, rồi **ExceptionCheck** xác định có Java exception hay không. Giá trị trả về không được tin cậy nếu có pending exception.
7. Nhánh cleanup in exception bằng **ExceptionDescribe**, xóa pending exception có chủ đích rồi **DeleteLocalRef** để giải phóng class reference và **DestroyJavaVM**.
8. Code gọi **DestroyJavaVM** cả khi tìm lớp hoặc method thất bại sau khi VM được tạo thành công. Nếu tạo VM thất bại trước đó, code không gọi Destroy.

Code dùng một lời gọi Java ngắn, không tạo worker thread hay shutdown hook chạy lâu. Với ứng dụng thật, cần thiết kế ownership và shutdown khi nhiều thread Java/native cùng sử dụng VM.

### 6.3. Build trên Linux: compile Java, link C với libjvm.so

Từ thư mục dự án chứa **src/demo/EmbeddedGreeting.java** và **host/embed_jvm.c**:

~~~bash
# JAVA_HOME trỏ đến thư mục JDK 17+ (cùng kiến trúc với C compiler).
mkdir -p out

javac -d out src/demo/EmbeddedGreeting.java

cc -std=c17 -Wall -Wextra -Wpedantic \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  host/embed_jvm.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_jvm

./embed_jvm
~~~

Lưu ý: **-ljvm** xuất hiện sau object/source cần symbol để tương thích các chính sách linker. Flag **-Wl,-rpath,...** nhúng đường tìm JVM vào executable trong ví dụ Linux; việc dùng đường dẫn tuyệt đối của môi trường build có thể không phù hợp khi chuyển executable sang máy khác. Với hệ thống phân phối, chọn đường dẫn được quản lý và xác minh bằng công cụ loader.

Một stdout **đúng và có thể dự đoán** khi build/run thành công, không có log runtime bổ sung:

~~~text
Java mode: embedded
C result: 43
~~~

Nếu môi trường định nghĩa **JAVA_TOOL_OPTIONS** hoặc có log JVM, có thể xuất hiện thông báo bổ sung trên stderr/stdout. Hai dòng trên là kết quả chính của chương trình, không phải toàn bộ output bắt buộc trong mọi môi trường.

### 6.4. Gợi ý tương đương trên Windows (MSVC)

Với JDK HotSpot Windows x64 và MSVC Developer Command Prompt cùng kiến trúc, link thông qua **jvm.lib** rồi bảo đảm **jvm.dll** cùng các dependency của JDK được loader tìm thấy:

~~~bat
mkdir out
javac -d out src\demo\EmbeddedGreeting.java

cl /nologo /W4 ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  host\embed_jvm.c ^
  /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_jvm.exe

set "PATH=%JAVA_HOME%\bin\server;%JAVA_HOME%\bin;%PATH%"
embed_jvm.exe
~~~

Các dòng có dấu **^** dành cho **cmd.exe**, không phải PowerShell. Nếu JDK distribution bố trí **jvm.lib/jvm.dll** khác đường dẫn trên thì phải tìm đúng vị trí trước khi build/run. Runtime **jvm.dll** không được thay bằng một DLL bất kỳ có tên giống; ABI/kiến trúc và các runtime dependency phải khớp. Trên macOS, header phụ thuộc nền tảng thường ở **include/darwin**, JVM library thường ở **lib/server/libjvm.dylib**; linker và loader dùng quy tắc **dyld**, cần cấu hình riêng theo distribution.

**Phân biệt:** host C nhúng JVM liên kết với **jvm.lib/libjvm.so**; không vì thế cần tạo một **libEmbeddedGreeting.so**. Lớp **EmbeddedGreeting** của ví dụ là Java bình thường, không khai báo phương thức **native**.

## 7. JNI_GetCreatedJavaVMs, giới hạn một VM và vòng đời

Invocation API cung cấp:

~~~c
jint JNI_GetCreatedJavaVMs(
        JavaVM **vmBuf, jsize bufLen, jsize *nVMs);
~~~

Nó cho biết các Java VM đang được tạo/đã tạo trong tiến trình, nhưng chuẩn JNI **không hỗ trợ tạo nhiều JVM độc lập trong cùng một process**. Việc gọi lại **JNI_CreateJavaVM** khi VM đã chạy không phải cách mở một “Java instance” mới để cách ly tenant hay cấu hình. Khi cần nhiều cấu hình JVM độc lập, dùng các **tiến trình OS riêng** là hướng thiết kế rõ ràng hơn.

**DestroyJavaVM** không nhất thiết trả về ngay: nó có thể chờ các **non-daemon threads** kết thúc, bao gồm cả native threads đã attach theo loại non-daemon. Không gọi destroy khi vẫn còn Java worker/attached native worker chưa được quản lý. Đóng JVM không phải cách bảo đảm có thể khởi tạo lại JVM thành công trong cùng process; nhiều implementation không hỗ trợ chu kỳ create–destroy–create được mong đợi.

Tài liệu Invocation API cũng khuyên không nên tạo VM trực tiếp trên **primordial process thread** ở một số OS do vấn đề stack và xử lý thread; với host production, có thể tạo một **native thread chuyên dụng** đủ stack để khởi tạo và điều phối VM. Ví dụ ở mục 6 chọn **main** để dễ thực hành, không áp đặt cách tổ chức thread cho host production.

## 8. JavaVM* khác JNIEnv*: lỗi luồng thường gặp

Khi JVM đã được tạo:

- **JavaVM*** là tay nắm VM có thể được lưu theo phạm vi quản lý của ứng dụng; dùng để **AttachCurrentThread**, **GetEnv**, **DetachCurrentThread**, **DestroyJavaVM**.
- **JNIEnv*** chỉ hợp lệ trong **thread đang sở hữu nó**. Không lưu **JNIEnv*** từ thread tạo VM rồi truyền trực tiếp sang worker native khác.
- Native worker muốn gọi Java phải lấy **JNIEnv*** riêng qua **AttachCurrentThread**, và **DetachCurrentThread** trước khi thread kết thúc nếu nó do native attach.
- **AttachCurrentThreadAsDaemon** tạo trạng thái daemon, có ảnh hưởng đến chờ shutdown. Nếu thread đã attach, gọi attach thêm lần nữa không tự đổi daemon status.

Hình dung:

~~~text
Thread A: JNI_CreateJavaVM -> (vm, envA)
             |
             | vm có thể truyền theo chính sách host
             v
Thread B: AttachCurrentThread(vm, &envB)
             |
             +--> dùng envB để gọi JNI trong Thread B
             |
             +--> DetachCurrentThread(vm)
~~~

**Không** dùng **envA** ở Thread B. Cũng không dùng một **jclass/jobject local reference** được tạo trong Thread A ở Thread B khi chưa tạo reference có vòng đời phù hợp, thường là **NewGlobalRef**. Đây là quy tắc quản lý JNI độc lập với việc classpath và JavaVMInitArgs được cấu hình đúng.

## 9. Tùy chọn thực tế: classpath, module path, native library path

### 9.1. Lớp Java không tìm thấy

Host gọi:

~~~c
jclass cls = (*env)->FindClass(env, "demo/EmbeddedGreeting");
~~~

Nếu lớp được biên dịch trong **out/demo/EmbeddedGreeting.class** mà host chạy từ thư mục khác, option **-Djava.class.path=out** trỏ tới một vị trí tương đối khác. Khi đó **FindClass** có thể trả **NULL** và tạo pending **NoClassDefFoundError**. Để tránh:

1. Kiểm tra Java class output thực sự tồn tại;
2. Dùng classpath theo đường tuyệt đối hoặc gắn với vị trí cài đặt;
3. Kiểm tra phần tên nội bộ **demo/EmbeddedGreeting** khớp **package demo**;
4. Kiểm tra **ExceptionDescribe** trên lỗi thật, không cố cast **NULL** thành reference hợp lệ.

Trên Linux, dấu phân cách nhiều mục classpath thường là **:**; Windows thường là **;**. **-Djava.class.path=out:lib/a.jar** không được dùng nguyên xi trên Windows. Java launcher và module system có thêm những quy tắc riêng; đừng suy ra classpath từ **PATH** của hệ điều hành.

### 9.2. Module options và quyền truy cập

Trong ứng dụng Java có module, có thể cần **--module-path=mods** cùng **--add-modules=...** để resolve module mục tiêu, hoặc các option **--add-opens/--add-exports** khi thật cần. Với JNI Invocation API, mỗi option module phải là **một optionString có dấu =**, chẳng hạn:

~~~c
static char module_path[] = "--module-path=/opt/app/mods";
static char add_module[] = "--add-modules=example.module";
static char opens[] = "--add-opens=java.base/java.lang=ALL-UNNAMED";
~~~

Đây là **các chuỗi option minh họa**, không thuộc chương trình Java đơn giản ở mục 6. Không sao chép **--add-opens** vào mọi ứng dụng để “chữa tất cả IllegalAccessException”: phải hiểu module nào, package nào và đối tượng nhận quyền nào. Mở package không giải quyết việc sai **FindClass** hoặc JVM library chưa nạp.

### 9.3. Đường dẫn native khác đường dẫn JVM

**-Djava.library.path** ảnh hưởng tới việc Java tìm native libraries qua **System.loadLibrary**, nhưng không giải quyết lỗi native executable không tìm thấy **libjvm.so/jvm.dll** trước khi vào **main**. Với Linux, dùng **ldd ./embed_jvm** hoặc **readelf -d ./embed_jvm** để xem dependency/RUNPATH. Với Windows, dùng công cụ phân tích DLL dependency và kiểm tra **PATH**. Chỉ kiểm tra những binary tin cậy khi dùng công cụ loader.

## 10. Phát hiện và xử lý lỗi khi khởi tạo

**JNI_CreateJavaVM** trả **jint**: **JNI_OK** khi thành công, một mã âm thích hợp khi thất bại. Một số hằng lỗi JNI thông dụng được khai báo trong **jni.h**:

| Mã | Ý nghĩa |
| --- | --- |
| **JNI_OK** | Thành công |
| **JNI_ERR** | Lỗi tổng quát |
| **JNI_EDETACHED** | Thread hiện tại chưa attach khi gọi API yêu cầu attachment, thường gặp với **GetEnv** |
| **JNI_EVERSION** | Phiên bản JNI yêu cầu không được hỗ trợ |
| **JNI_ENOMEM** | Không đủ bộ nhớ |
| **JNI_EEXIST** | VM đã tồn tại trong bối cảnh trả lỗi thích hợp |
| **JNI_EINVAL** | Đối số không hợp lệ |

Không dựa vào một mã cụ thể như chẩn đoán duy nhất cho mọi JVM. In cả mã lỗi, option và thông báo runtime; khi khởi tạo thất bại chưa có **JNIEnv** hợp lệ để gọi **ExceptionDescribe**. Một lỗi JVM initialization có thể xuất hiện trên stderr, log VM hoặc qua cơ chế diagnostics của implementation.

Khi VM đã tạo và lời gọi **FindClass/GetStaticMethodID/CallStatic...Method** thất bại, có thể có **pending Java exception**. Code mẫu ở mục 6 sử dụng **ExceptionCheck/ExceptionDescribe/ExceptionClear** để in lỗi và cleanup. **ExceptionClear** trong ví dụ là quyết định của native host; trong ứng dụng có Java caller, có trường hợp nên giữ exception pending để JVM ném nó về Java thay vì xóa lặng lẽ.

### Bảng triệu chứng và kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Bước xác minh |
| --- | --- | --- |
| Compiler báo không thấy **jni.h** | Thiếu đường **-I** hoặc dùng JRE không có header | Kiểm tra JDK, **JAVA_HOME/include**, header theo OS |
| Linker **undefined reference to JNI_CreateJavaVM** | Thiếu **-ljvm**, sai vị trí hoặc thứ tự tham số link | Kiểm tra **-L**, **-ljvm**, symbol và kiến trúc |
| Linux: **libjvm.so: cannot open shared object file** | Runtime linker không tìm thấy JVM | Kiểm tra RUNPATH/RPATH, phân phối JDK và dependency |
| Windows: **jvm.dll was not found** | DLL hoặc dependency không nằm trên loader search path | Kiểm tra **PATH**, JDK bitness, DLL dependency |
| **JNI_CreateJavaVM** trả lỗi | Option sai, version không hỗ trợ, thiếu bộ nhớ, xung đột VM | Log option, return code, xác minh trên runtime mục tiêu |
| **NoClassDefFoundError** khi **FindClass** | Classpath/module path sai hoặc lớp không hợp lệ | Kiểm tra package, đường dẫn, **-Djava.class.path** |
| **NoSuchMethodError** khi **GetStaticMethodID** | Tên method/static/descriptor sai | Kiểm tra descriptor, **javap -s** nếu cần |
| Java exception sau **CallStaticIntMethod** | Logic Java ném lỗi (ví dụ overflow) | **ExceptionCheck/ExceptionDescribe** và truyền/ghi lỗi phù hợp |
| **DestroyJavaVM** chờ lâu | Non-daemon thread còn hoạt động | Phân tích thread lifecycle, đảm bảo các worker kết thúc/detach |
| Chạy trên máy khác lỗi nạp JVM | RPATH cố định, sai kiến trúc, thiếu dependency hoặc JDK khác | Đóng gói/chọn runtime tương thích, chạy integration smoke test |

## 11. Hạn chế và quyết định kiến trúc trước khi nhúng JVM

### 11.1. Một tiến trình không phải sandbox đa JVM

Chuẩn JNI không hỗ trợ tạo nhiều VM độc lập trong một process. Nếu muốn cách ly tenant, classpath, giới hạn heap và phiên bản JDK hoàn toàn khác nhau, tạo các process riêng và kết nối bằng IPC/RPC có thể dễ quản lý hơn. **ClassLoader** tạo namespace lớp bên trong một VM nhưng không biến chúng thành nhiều JVM độc lập.

### 11.2. Heap max khác tổng bộ nhớ native host

**-Xmx128m** giới hạn heap Java theo HotSpot, không giới hạn toàn bộ process. Cần tính cả native allocations của host, JNI global refs, direct buffers, thread stacks, metaspace, JIT code cache và các thành phần runtime khác. Chọn heap chỉ dựa theo tổng RAM của máy và bỏ qua native host có thể dẫn tới memory pressure hay lỗi khởi tạo.

### 11.3. Startup options có tác động bảo mật/vận hành

Nếu host nhận option từ file cấu hình hoặc đầu vào người dùng, cần kiểm soát những cờ có thể load agent, mở package, đổi classpath hoặc load native code. Những option này có thể làm thay đổi mã được chạy trong process native. Không coi **ignoreUnrecognized=JNI_TRUE** là cách kiểm tra hợp lệ của option.

Với HotSpot, **JAVA_TOOL_OPTIONS** có thể tác động đến tùy chọn khi **JNI_CreateJavaVM** chạy, đặc biệt phục vụ agent/diagnostics; trong một số điều kiện runtime hạn chế biến này. Khác với **JDK_JAVA_OPTIONS**, vốn chủ yếu được **java launcher** phân tích, môi trường của một ứng dụng embedded có thể chịu ảnh hưởng từ các biến cấu hình JVM. Khi debug “tại sao nhận option ngoài dự kiến”, hãy kiểm tra môi trường khởi chạy tiến trình chứ không chỉ nhìn mảng **options[]**.

### 11.4. Version/ABI của header, libjvm và host

Sử dụng header từ JDK tương thích runtime được link/load. Một thư viện JVM 64-bit không thể nạp vào native process 32-bit. Compiler/ABI, OS, calling convention và dependency phải khớp. Không chọn JDK dựa trên chuỗi version đơn thuần rồi bỏ qua platform.

### 11.5. Shutdown là hợp đồng vòng đời

Chỉ gọi **DestroyJavaVM** khi đã quy định rõ ai sở hữu VM, ai dừng Java workers, khi nào các native threads detach, và những callbacks/shutdown hooks nào còn hoạt động. Nếu host phải chạy hàng tuần, đôi khi vòng đời JVM kéo dài cùng tiến trình là thiết kế phù hợp; không nhất thiết create/destroy cho mỗi request. Trong code production, hãy kiểm tra mã trả về destroy và có đường dọn tài nguyên ngay cả khi Java code ném exception.

## 12. Tự kiểm tra hiểu bài

**Câu 1.** Dùng **args.version=JNI_VERSION_1_8** rồi biên dịch class bằng JDK 21 thì host có tự động dùng ngữ nghĩa Java 8 không?

**Đáp án:** Không. Version trong **JavaVMInitArgs** là yêu cầu về JNI interface. Java class file, Java language level và phiên bản JVM runtime là khía cạnh riêng. VM vẫn phải có khả năng nạp bytecode đã biên dịch.

**Câu 2.** Đã truyền **-Djava.library.path=/opt/native**, nhưng native executable báo thiếu **libjvm.so** trước khi chạy. Vì sao?

**Đáp án:** Đây là lỗi OS loader tìm thư viện JVM, xảy ra trước khi JavaVMInitArgs được xử lý. **java.library.path** thuộc cơ chế Java nạp thư viện native; cần sửa RPATH/RUNPATH, library search path hoặc cơ chế nạp JVM của host.

**Câu 3.** Vì sao **-cp** và **out** không nên được truyền như hai JavaVMOption rồi kỳ vọng host tìm lớp Java?

**Đáp án:** Đó là cách java launcher nhận command line, không phải hợp đồng tùy chọn Invocation API. Với classpath truyền vào VM từ native, ví dụ dùng **-Djava.class.path=out** như một option string và gọi **FindClass** sau startup.

**Câu 4.** **ignoreUnrecognized=JNI_TRUE** có bảo đảm bỏ qua mọi option sai tên không?

**Đáp án:** Không. JNI định nghĩa việc bỏ qua những unknown options với tiền tố **-X** hoặc **_**; các lỗi khác và chính sách implementation vẫn áp dụng. Nên dùng **JNI_FALSE** khi muốn fail fast.

**Câu 5.** Đã tạo VM trong Thread A, có thể chuyển **JNIEnv*** từ A cho Thread B để gọi Java không?

**Đáp án:** Không. **JNIEnv*** chỉ hợp lệ trong thread tương ứng. B dùng **JavaVM*** để attach và lấy **JNIEnv*** của riêng mình, sau đó detach trước khi kết thúc.

**Câu 6.** **DestroyJavaVM** đã được gọi nhưng chưa trả về, có thể liên quan điều gì?

**Đáp án:** JVM có thể đang chờ non-daemon threads kết thúc; native threads được attach làm non-daemon cũng có thể giữ VM sống. Phải thiết kế shutdown và detach có trình tự, thay vì ép hủy bất chấp threads còn hoạt động.

## Tài liệu chuẩn để tra cứu

- Oracle JNI Specification (Java SE 21), **The Invocation API**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html
- Oracle JNI Specification, **JNI Types and Data Structures**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html
- Oracle JNI Specification, **JNI Functions**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- Oracle JNI Specification, **Design Overview: Compiling, Loading and Linking Native Methods**: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- Oracle Java 21 **java launcher**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Oracle Java 22 Troubleshooting, **JAVA_TOOL_OPTIONS**: https://docs.oracle.com/en/java/javase/22/troubleshoot/environment-variables-and-system-properties.html

**Ghi nhớ:** Host nhúng JVM phải giải quyết **ba lớp khác nhau**: chuẩn bị đúng **JavaVMInitArgs/options**, liên kết và nạp đúng **thư viện JVM**, rồi dùng đúng **JNIEnv/JavaVM lifecycle** để gọi Java và kết thúc. Cấu hình classpath, VM option và đường dẫn loader sai thường biểu hiện như những lỗi khác nhau; xác minh từng lớp giúp tìm đúng nguyên nhân.