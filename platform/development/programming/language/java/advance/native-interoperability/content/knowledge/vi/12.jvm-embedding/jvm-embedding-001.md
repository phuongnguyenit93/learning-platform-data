# Khi nào ứng dụng C/C++ cần tạo JVM thay vì được Java gọi vào?

## Mục tiêu học tập

Một ứng dụng có thể kết hợp Java và C/C++ theo hai hướng khác nhau: **Java khởi chạy trước rồi gọi native code**, hoặc **ứng dụng C/C++ khởi chạy trước và tự tạo Java Virtual Machine (JVM) để thực thi Java code**. Hai hướng đều có thể sử dụng Java Native Interface (JNI), nhưng khác nhau ở **quyền kiểm soát tiến trình, thời điểm tạo JVM, cấu hình runtime, quản lý luồng, xử lý lỗi và vận hành**.

Sau bài này, bạn sẽ:

1. Nhận diện thời điểm phù hợp để **nhúng JVM (embedded JVM)** vào một ứng dụng C/C++ bằng **JNI Invocation API**.
2. Phân biệt hướng **Java → native (JNI hoặc Foreign Function & Memory API)** với hướng **native host → JVM → Java**.
3. Dùng các API trọng tâm **JNI_CreateJavaVM**, **JavaVMInitArgs**, **JavaVMOption**, **JNIEnv**, **JavaVM** và **DestroyJavaVM** đúng vai trò.
4. Đánh giá chi phí khởi động, tài nguyên, độ ổn định, khả chuyển, đóng gói, class loader và vòng đời ứng dụng trước khi chọn kiến trúc.
5. Biên dịch ví dụ **Java 17+ và C**: chương trình C tạo JVM, tìm một lớp Java, gọi phương thức static và kết thúc JVM có kiểm soát.
6. Nhận biết các lỗi thiết kế: tạo JVM mỗi request, cố tạo nhiều JVM trong cùng process, quên attach native thread, gọi JNI bằng local reference hết hạn và shutdown khi vẫn có non-daemon thread.

## 1. Hai hướng tích hợp khác nhau ở đâu?

Trước tiên cần xác định **ai sở hữu tiến trình và ai gọi ai**.

### Hướng A — Java là ứng dụng chính, Java gọi thư viện C/C++

~~~text
[OS khởi chạy java / Java service]
                |
                v
             [JVM]
                |
           Java code
                |
        JNI / FFM API
                |
                v
        [C/C++ native library]
~~~

Java host thường có **main()** viết bằng Java, hoặc được container như ứng dụng Java server khởi động. JVM đã tồn tại. Khi cần truy cập một C API, driver, codec hay thư viện tăng tốc, Java gọi xuống native code. JNI native method tự động nhận **JNIEnv \*** từ JVM; không cần tự gọi **JNI_CreateJavaVM**.

Ví dụ Java gọi native (chỉ là skeleton, cần thư viện có implementation thực):

~~~java
public final class JavaOwnsProcess {
    static {
        System.loadLibrary("native_math");
    }

    private static native int nativeMultiply(int a, int b);

    public static void main(String[] args) {
        System.out.println(nativeMultiply(6, 7));
    }
}
~~~

Đây là **đoạn cấu trúc**, không thể chạy độc lập vì chưa cung cấp binary **native_math** và JNI implementation. Trong hướng này, **Java là điểm điều phối vòng đời**; thư viện C/C++ chỉ cung cấp tính năng theo lời gọi Java. Nếu phía C muốn gọi ngược Java trong cùng lời gọi, nó đã có JNIEnv của Java thread hiện tại.

### Hướng B — C/C++ là ứng dụng chính, native host tạo JVM

~~~text
[OS khởi chạy C/C++ executable]
                  |
             native host
                  |
          JNI_CreateJavaVM()
                  |
                  v
              [JVM nằm
          trong cùng process]
                  |
       JNI FindClass / Call...
                  |
               Java code
                  |
          trả kết quả về C/C++
~~~

Ứng dụng **C/C++ quyết định khi nào cần Java**, tạo JVM qua **Invocation API**, nhận **JavaVM \*** và **JNIEnv \*** của luồng khởi tạo, rồi gọi code Java qua JNI. JVM được nạp vào **cùng process**. JVM không tự mở một tiến trình Java riêng chỉ vì JNI_CreateJavaVM được gọi.

Ví dụ điển hình: một ứng dụng C++ desktop lâu đời có mô-đun nghiệp vụ viết bằng Java; sản phẩm bắt buộc giữ **C++ main loop, UI hoặc engine** làm entry point và cần chạy một số thành phần Java bên trong tiến trình đó.

**Quy tắc quan trọng:** Nếu JVM đã chạy và một native method được **Java gọi vào**, không tạo một JVM thứ hai để “quay lại gọi Java”. Native method đã nhận JNIEnv và có thể dùng chính JVM hiện hữu. Nếu một native worker thread cần gọi Java sau đó, phải lấy **JNIEnv cho worker** bằng JavaVM/GetEnv/AttachCurrentThread, không tạo VM mới.

## 2. Khi nào C/C++ nên chủ động tạo JVM?

Hãy xem embedding như **quyết định kiến trúc**, thay vì chỉ là lựa chọn API.

### 2.1. Native host bắt buộc kiểm soát vòng đời sản phẩm

Ví dụ: một ứng dụng C++ đã có **main()**, event loop, giao diện người dùng, vòng lặp mô phỏng hoặc pipeline tác vụ native. Đổi toàn bộ entry point sang Java rất tốn kém hoặc không phù hợp yêu cầu phân phối. Một thành phần Java lại thực sự cần thiết cho chức năng sản phẩm.

Nhúng JVM cho phép giữ native host làm **process owner**, đồng thời gọi Java component qua một adapter có hợp đồng rõ ràng.

Quyết định này phù hợp nếu native host thật sự cần:

- Điều phối **startup/shutdown** của sản phẩm và chọn lúc Java component hoạt động.
- Tái sử dụng một thư viện Java phức tạp hoặc mô-đun đã ổn định, thay vì viết lại bằng C/C++.
- Duy trì vòng đời, cấu hình hoặc điểm tích hợp native mà tổ chức đã sở hữu.
- Chấp nhận JVM như một dependency và một runtime sống trong cùng process.

### 2.2. Có Java component mà native code phải gọi trực tiếp, thường xuyên

Một thư viện Java có thể cung cấp bộ xử lý quy tắc, định dạng dữ liệu, thuật toán hoặc mô-đun tương tác với hệ sinh thái Java. Nếu native host liên tục gọi các API này và mô hình gọi khá nhỏ, việc giữ một JVM trong process có thể tránh một số chi phí **khởi động tiến trình riêng và IPC/serialization**.

Tuy nhiên, **JNI crossing vẫn có chi phí**: chuyển kiểu, copy dữ liệu, quản lý references, tìm method/field và đồng bộ hóa thread. Không nên chọn embedding chỉ vì giả định “in-process luôn nhanh hơn”; phải đo workload thực tế.

### 2.3. Một sản phẩm native cần cơ chế mở rộng dựa trên Java

Ví dụ: ứng dụng có lõi C++ nhưng bên thứ ba cung cấp plugin Java. Host có thể khởi tạo JVM một lần, tải plugin thông qua **class loader** được thiết kế cho hệ thống, rồi gọi các entry point có version rõ ràng.

Kiến trúc này chỉ hợp lý nếu có kế hoạch:

- Quản lý **class loader**, phụ thuộc, version và vòng đời plugin.
- Giới hạn API giao tiếp và quyền của plugin; không coi Java sandbox truyền thống là một biện pháp bảo mật đầy đủ.
- Tải/dỡ plugin mà không giả định có thể tạo/hủy JVM tùy ý nhiều lần.
- Chặn hoặc cô lập extension không tin cậy khi độ an toàn của process là yêu cầu quan trọng.

### 2.4. Không thể đổi cơ chế khởi động của hệ thống tích hợp

Một số native host được nạp bởi môi trường chuyên biệt: phần mềm CAD, đồ họa, thiết bị hoặc phần mềm công nghiệp có plugin SDK C/C++. Host luôn khởi động theo cách riêng, nhưng plugin cần một thành phần Java.

Khi **host thực sự cho phép nhúng JVM** và tài nguyên/dependency được kiểm soát, Invocation API có thể là cầu nối. Trước khi chọn, phải xác minh host chưa có JVM, chính sách nạp shared library, thread/stack, class loader, JDK distribution và quyền khởi tạo runtime trong process. Nếu plugin chạy trong một ứng dụng đã có JVM, ưu tiên sử dụng JVM hiện hữu qua cơ chế của host.

## 3. Khi nào nên để Java gọi C/C++?

Các trường hợp sau thường phù hợp hướng **Java host → native** hơn:

| Ngữ cảnh | Hướng thường phù hợp | Lý do |
| --- | --- | --- |
| Java/Spring service đang chạy, cần dùng C library để tăng tốc | Java gọi JNI/FFM | JVM đã có; Java điều phối service, lifecycle và cấu hình |
| Ứng dụng Java cần driver, codec hoặc API hệ điều hành | Java gọi native | Native là một khả năng phụ của ứng dụng Java |
| Ứng dụng Java có yêu cầu đi cùng một JDK/runtime đã biết | Java gọi native | Bớt một lớp bootstrap VM do C tự quản |
| Ứng dụng C++ điều phối GUI/engine và chỉ cần một Java rules engine | C/C++ nhúng JVM hoặc dùng Java service riêng | Native host là entry point không thay được |
| C++ host dùng module Java rất hiếm, độc lập và crash phải được cô lập | Java **process riêng** qua IPC | Cách ly sự cố và mở rộng/deploy độc lập có thể quan trọng hơn chi phí IPC |
| Một chương trình C nhỏ chỉ muốn gọi một phép tính đơn giản đã có thư viện C | C thuần | Không đáng mang theo JVM chỉ cho tính năng có phương án native đơn giản |

Nếu phần mềm chủ yếu viết bằng Java và dùng native code như **implementation detail**, việc tạo một JVM từ C thường thêm trách nhiệm không cần thiết: lựa chọn Java home, memory, GC, classpath/module path, lifecycle và đóng gói.

Ngược lại, nếu native host là thành phần chính và Java chỉ là một mô-đun cần gọi, embedding có thể hợp lý.

## 4. Embedding JVM so với chạy Java ở tiến trình riêng

Một ứng dụng C/C++ **không bắt buộc phải nhúng JVM** chỉ để sử dụng một thư viện Java. Có thể khởi chạy một tiến trình Java riêng và trao đổi qua stdin/stdout, pipes, sockets, HTTP/gRPC hoặc giao thức IPC.

| Tiêu chí | JVM nhúng **cùng process** | Java chạy **process riêng** |
| --- | --- | --- |
| Ai khởi chạy Java runtime? | Native host gọi **JNI_CreateJavaVM** | Native host/OS khởi chạy **java** hoặc service Java |
| Giao tiếp | JNI, shared address space | IPC/network protocol |
| Latency per call | Có thể thấp hơn khi gọi API nhỏ và chuẩn hóa dữ liệu | Có thêm serialization, context switch hoặc network |
| Crash của JVM/native | Có thể làm sập **cùng process** | Có ranh giới lỗi riêng, có thể restart worker Java |
| Quản lý heap/GC | JVM cùng chia sẻ tài nguyên process | Heap Java thuộc process riêng, giám sát dễ tách |
| Triển khai/upgrade | Native host phải mang thư viện VM và binary đúng OS/ABI | Có thể cập nhật Java service độc lập |
| Security isolation | Ranh giới process không tồn tại | Có thể áp user, sandbox, container, quota |
| Class loading | Host phải quản JVM/classloader | Java process tự tổ chức classpath/modules |
| Debugging | C/C++ + JVM trong một tiến trình; mixed stack | Log/tracing giữa hai process |
| Shutdown | Native host phải phối hợp **DestroyJavaVM**, Java threads | Quản lifecycle của Java process, health check và signal |

Đừng xem embedding là “không copy dữ liệu”: JNI vẫn có thể cần **marshalling**, chuyển String, bộ nhớ hoặc tạo references. Cũng không xem process riêng là “luôn chậm”; với request đủ lớn, batch API hoặc sự cô lập trong production, IPC có thể là phương án tốt hơn.

**Gợi ý quyết định:** Nếu mục tiêu chính là **cô lập sự cố của plugin không đáng tin**, một **Java process riêng** thường đáng cân nhắc. Nếu cần native host kiểm soát sâu hệ thống và gọi một thành phần Java tin cậy rất thường xuyên, embedding đáng benchmark.

## 5. Invocation API: tạo VM khác gì JNI native method?

JNI Specification chia các chức năng thành hai phần liên quan:

1. **JNI functions** gọi qua **JNIEnv \*** để thao tác đối tượng, lớp, field, method và exception.
2. **Invocation API** để một ứng dụng native tạo và quản lý VM, gồm **JNI_CreateJavaVM**, **DestroyJavaVM**, **GetEnv**, **AttachCurrentThread**...

### Các kiểu dữ liệu cốt lõi

~~~c
JavaVM *jvm = NULL;
JNIEnv *env = NULL;

JavaVMOption options[1];
JavaVMInitArgs args;
~~~

- **JavaVM \***: handle cho JVM, dùng để yêu cầu attach/detach và các thao tác vòng đời VM.
- **JNIEnv \***: giao diện JNI hợp lệ **chỉ cho thread hiện tại**; để gọi FindClass, GetStaticMethodID, CallStaticIntMethod v.v.
- **JavaVMOption**: mỗi cấu hình JVM được biểu diễn bằng **optionString** (và extraInfo cho trường hợp đặc biệt).
- **JavaVMInitArgs**: phiên bản JNI mong muốn, danh sách options và quy tắc xử lý option không được nhận diện.

Ví dụ cấu hình tối thiểu:

~~~c
JavaVMOption options[1];
options[0].optionString = "-Djava.class.path=.";
options[0].extraInfo = NULL;

JavaVMInitArgs args;
args.version = JNI_VERSION_1_8;
args.nOptions = 1;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;
~~~

Giải nghĩa:

- **-Djava.class.path=.** khiến classpath chứa thư mục làm việc hiện tại; phù hợp demo có file .class ở đó. Trong sản phẩm cần dùng đường dẫn tuyệt đối/đóng gói có kiểm soát.
- **JNI_VERSION_1_8** yêu cầu giao diện JNI phiên bản 1.8; không có nghĩa code Java bị giới hạn ở Java 8. JDK 17+ vẫn hỗ trợ giao diện JNI này.
- **JNI_FALSE** giúp fail khi gặp option không nhận diện thay vì âm thầm bỏ qua; hành vi cụ thể còn theo quy định của Invocation API và phiên bản VM.
- Các tham số hiệu năng như heap size, GC, module options và system properties cần được xác định theo **JDK thực tế dùng triển khai**. Không nên sao chép tùy chọn từ một JDK khác mà không kiểm thử.

### Lời gọi tạo JVM

~~~c
jint status = JNI_CreateJavaVM(
    &jvm,
    (void **)&env,
    &args
);
~~~

Nếu **status == JNI_OK**, JVM đã khởi tạo thành công, và **env là JNIEnv của chính thread đã gọi JNI_CreateJavaVM**. Thread này được xem là **main thread của JVM** theo Invocation API.

Nếu status khác JNI_OK, không được gọi FindClass hoặc các JNI functions bằng một env chưa hợp lệ. Ghi lại mã lỗi, kiểm tra dependency libjvm, runtime options, giới hạn tài nguyên và phiên bản JNI.

Các lỗi JNI cấp VM có thể được biểu diễn bởi **JNI_ERR, JNI_EVERSION, JNI_ENOMEM, JNI_EEXIST hoặc JNI_EINVAL** tùy tình huống/implementation. Không tự giả định một mã âm cụ thể luôn chỉ về một nguyên nhân duy nhất.

## 6. Một chương trình C gọi JVM cần chuẩn bị những gì?

### 6.1. JDK/JVM binary phù hợp với native host

Ứng dụng C/C++ phải **liên kết hoặc nạp động thư viện VM** của JDK/Java runtime tương ứng, ví dụ **libjvm.so**, **libjvm.dylib** hoặc **jvm.dll** trên các nền tảng thông dụng. Chỉ có Java source/JAR không đủ để nhúng runtime.

Cần kiểm soát:

- **Kiến trúc OS/CPU và ABI:** C executable 64-bit cần một JVM binary tương thích, đúng hệ điều hành/kiến trúc.
- **Thư viện phụ thuộc:** OS loader phải tìm được libjvm và những dependency bậc hai.
- **Phiên bản/JDK distribution:** cấu hình, flags, Java APIs và chính sách runtime phải được kiểm thử trên phiên bản phát hành.
- **Quy trình deploy:** native executable, JVM runtime, Java classes/JAR, libraries và cấu hình đi cùng nhau trong một artifact/vùng deploy đã kiểm chứng.
- **Tài nguyên process:** heap, native memory, thread stacks, JVM code cache, GC, JIT và native host dùng chung giới hạn bộ nhớ của một process.

Khi nhúng VM, sản phẩm trở thành **sản phẩm phân phối cả một Java runtime**, trừ khi môi trường triển khai đã có và hỗ trợ runtime được cam kết. Cần xem xét điều khoản phân phối JDK/runtime và cập nhật bảo mật theo nhà cung cấp.

### 6.2. Classpath và module path

Để gọi **FindClass("com/example/Engine")**, JVM phải nhìn thấy class này theo **class loader context** tại thời điểm tìm. Với ví dụ không package, option **-Djava.class.path=.** cho phép FindClass("EmbeddedRule") tìm class trong thư mục hiện tại.

Trong sản phẩm, hãy xác định:

- Class có thuộc **classpath** hay module path?
- Host cần module nào; có khai báo **--module-path** và **--add-modules** tương ứng không?
- Những dependency của Java component có được cung cấp đúng version/đường dẫn?
- Có class loader tùy biến của plugin không? Nếu có, FindClass từ native thread có thể không giải quyết class theo context bạn mong muốn.
- Đường dẫn tương đối có đổi ý nghĩa khi service chạy từ thư mục làm việc khác không?

Một vấn đề deployment phổ biến là **native code tạo VM thành công** nhưng **FindClass** không thấy class Java vì classpath sai. Đây là lỗi class loading, không phải bằng chứng JNI_CreateJavaVM thất bại.

### 6.3. Chọn một nơi quản lý VM

Ứng dụng nên có một **VM manager** ở ranh giới native host, chịu trách nhiệm:

1. Khởi tạo VM **một lần**.
2. Chứa JavaVM \* và các handles cần thiết.
3. Cung cấp API gọi Java cho các native worker bằng **JNIEnv riêng của mỗi thread**.
4. Theo dõi trạng thái initialized, ready, stopping, stopped và lỗi bootstrap.
5. Ngăn request mới, hoàn tất callback/worker, dọn reference rồi shutdown.

Tránh để mỗi mô-đun C tự gọi JNI_CreateJavaVM. **JNI Specification không hỗ trợ tạo nhiều JVM trong cùng process**. **JNI_GetCreatedJavaVMs** có thể truy vấn VM đã tạo, nhưng việc tìm thấy VM không tự động cấp quyền lifecycle hay giải quyết class loader/ownership; host vẫn phải có giao thức ai sở hữu VM.

## 7. Ví dụ đầy đủ: C host tạo JVM và gọi Java 17+

Ví dụ này cố ý nhỏ, có kết quả deterministic, không yêu cầu một thư viện JNI riêng chứa native method. **Native executable là chương trình chủ**, liên kết tới **libjvm** để tạo VM; sau đó gọi một Java static method bằng JNI.

Chạy trên **JDK 17+**, với C compiler và JNI headers của JDK mục tiêu.

### Bước 1 — Tạo EmbeddedRule.java

~~~java
public final class EmbeddedRule {
    private EmbeddedRule() {
    }

    public static int calculate(int units) {
        if (units < 0) {
            throw new IllegalArgumentException("units must be nonnegative");
        }
        return units * 3 + 7;
    }
}
~~~

Method có chữ ký JVM **(I)I**, nghĩa là nhận một **int** và trả một **int**. Demo gọi **calculate(5)**, nên kết quả là **5 × 3 + 7 = 22**. Đây là class Java hoàn chỉnh, **không khai báo native method** vì hướng gọi là C → Java.

Biên dịch từ thư mục lưu file:

~~~bash
javac EmbeddedRule.java
~~~

Khi chạy C host ở phần sau, thư mục làm việc phải chứa **EmbeddedRule.class**, vì JVM demo dùng **-Djava.class.path=.**.

### Bước 2 — Tạo embed_host.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Chẩn đoán Java exception trước khi hủy JVM. */
static void report_java_exception(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env); /* Ghi chi tiết ra stderr. */
        (*env)->ExceptionClear(env);
    }
}

int main(void) {
    JavaVM *jvm = NULL;
    JNIEnv *env = NULL;
    jclass rule_class = NULL;
    jmethodID method = NULL;
    jint result = 0;
    int exit_code = EXIT_FAILURE;

    JavaVMOption options[1];
    options[0].optionString = "-Djava.class.path=.";
    options[0].extraInfo = NULL;

    JavaVMInitArgs args;
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    /* C executable tự tạo JVM trong cùng process. */
    jint create_status = JNI_CreateJavaVM(
        &jvm, (void **)&env, &args
    );
    if (create_status != JNI_OK || jvm == NULL || env == NULL) {
        fprintf(stderr, "Cannot create JVM: %d\n", create_status);
        return EXIT_FAILURE;
    }

    puts("C host: JVM started");

    /* Class nằm ở classpath "." đã cấu hình. */
    rule_class = (*env)->FindClass(env, "EmbeddedRule");
    if (rule_class == NULL) {
        goto shutdown;
    }

    method = (*env)->GetStaticMethodID(
        env, rule_class, "calculate", "(I)I"
    );
    if (method == NULL) {
        goto shutdown;
    }

    /* Gọi chính Java method trong JVM đã tạo. */
    result = (*env)->CallStaticIntMethod(
        env, rule_class, method, (jint)5
    );
    if ((*env)->ExceptionCheck(env)) {
        goto shutdown;
    }

    printf("C host: Java returned %d\n", (int)result);
    exit_code = EXIT_SUCCESS;

shutdown:
    /* Giữ exception detail ở stderr rồi dọn trước khi shutdown. */
    report_java_exception(env);

    if (rule_class != NULL) {
        (*env)->DeleteLocalRef(env, rule_class);
    }

    /* Không dùng env hoặc jvm sau khi DestroyJavaVM thành công. */
    jint destroy_status = (*jvm)->DestroyJavaVM(jvm);
    if (destroy_status != JNI_OK) {
        fprintf(stderr, "Cannot destroy JVM: %d\n", destroy_status);
        return EXIT_FAILURE;
    }

    if (exit_code == EXIT_SUCCESS) {
        puts("C host: JVM stopped");
    }
    return exit_code;
}
~~~

### Bước 3 — Biên dịch C executable để liên kết libjvm

**Linux (GCC, x86-64 hoặc ARM64 phù hợp JVM):**

~~~bash
gcc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" embed_host.c /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_host.exe
~~~

Trên Windows, lúc chạy cần đảm bảo hệ điều hành tìm được **jvm.dll** của đúng JDK (thường trong thư mục **%JAVA_HOME%\bin\server** đối với JDK phổ biến). Ví dụ trong **Command Prompt**:

~~~bat
set "PATH=%JAVA_HOME%\bin\server;%PATH%"
embed_host.exe
~~~

Các lệnh build giả định **JAVA_HOME** được cấu hình đúng và máy có toolchain tương ứng. Build riêng cho từng OS/CPU/ABI; không dùng một executable hoặc libjvm của hệ điều hành khác.

**Tại sao build cần -I và -L?** Hai đường include giúp compiler tìm **jni.h** và các khai báo JNI phụ thuộc nền tảng. Đường lib/server giúp linker tìm **libjvm**, còn **rpath** trong ví dụ Linux/macOS giúp dynamic loader tìm libjvm tại runtime. Với production, không nên đóng đinh đường dẫn máy build vào một binary phân phối rộng; hãy thiết kế đường dẫn runtime, packaging và patching phù hợp.

### Bước 4 — Chạy từ đúng thư mục

**Linux/macOS:**

~~~bash
./embed_host
~~~

**Windows:** chạy **embed_host.exe** sau khi cấu hình PATH trong Command Prompt.

Kết quả **stdout chính xác** trên môi trường build và load thành công, khi không có logging/VM options bổ sung:

~~~text
C host: JVM started
C host: Java returned 22
C host: JVM stopped
~~~

Trong ví dụ, **Java không tạo native library để gọi xuống C**. Chính executable C tạo JVM, dùng JNIEnv để tra class/method rồi gọi Java, sau đó yêu cầu shutdown.

### Phân tích luồng thực thi

1. **C main()** bắt đầu trước mọi Java method.
2. **JavaVMOption** chỉ định vị trí class Java qua classpath.
3. **JNI_CreateJavaVM** nạp/khởi tạo VM và attach thread hiện hành, trả cả JavaVM và JNIEnv.
4. **FindClass** tìm EmbeddedRule, **GetStaticMethodID** tìm method với descriptor **(I)I**.
5. **CallStaticIntMethod** chạy code Java và nhận **jint 22**.
6. **ExceptionCheck** ngăn C code coi Java exception là kết quả hợp lệ.
7. **DeleteLocalRef** dọn reference tới Class trong native code.
8. **DestroyJavaVM** yêu cầu kết thúc VM; khi thành công, native host tiếp tục và in thông báo kết thúc.

**Chưa thực hiện native build trên môi trường của tài liệu**: code và output ở trên là mẫu có điều kiện thành công, cần biên dịch/chạy trên toolchain/JDK mục tiêu để xác minh integration và đường dẫn libjvm thực tế.

## 8. Vì sao demo cần kiểm tra Java exception?

Từ C, gọi Java method có thể thất bại vì **class không tìm thấy**, **method descriptor không khớp**, **exception trong Java body**, lỗi class initialization hoặc lỗi tài nguyên.

Ví dụ:

- Nếu **EmbeddedRule.class** không ở classpath, **FindClass** có thể trả NULL với Java exception đang pending.
- Nếu đổi method Java từ **calculate(int)** thành **calculate(long)** mà C vẫn tìm **(I)I**, **GetStaticMethodID** sẽ không tìm đúng method.
- Nếu **calculate(-1)** được gọi, code Java ném **IllegalArgumentException**. C cần phát hiện pending exception sau **CallStaticIntMethod**, không dùng một giá trị trả về bất kỳ như kết quả hợp lệ.

**ExceptionDescribe** viết thông tin lỗi ra stderr để chẩn đoán, còn **ExceptionClear** xóa trạng thái pending. Code demo làm vậy trước khi gọi DestroyJavaVM. Trong production phải có chiến lược chuyển lỗi thành error code, log có correlation ID hoặc trả về lỗi qua API native host; không âm thầm nuốt exception.

Không nên gọi các JNI API thông thường liên tiếp khi **pending exception** chưa được xử lý. Một số API cleanup như **DeleteLocalRef** được cho phép khi exception còn pending, nhưng cách rõ ràng nhất là kiểm tra lỗi sau thao tác có thể thất bại và dùng nhánh cleanup nhất quán.

## 9. Cạm bẫy đặc biệt của vòng đời JVM nhúng

### 9.1. Không tạo một JVM cho mỗi request

Khởi tạo JVM tốn chi phí: nạp thư viện runtime, khởi tạo classloader, heap, GC, JIT, runtime threads và các lớp Java được gọi. Một JVM không giống một function object có thể tạo và hủy nhanh trên mỗi request.

**Kiến trúc sai:**

~~~text
for each incoming C request:
    JNI_CreateJavaVM()
    call Java once
    DestroyJavaVM()
~~~

Hậu quả: latency lớn, tài nguyên tăng/dao động, shutdown khó kiểm soát và nguy cơ dựa vào giả định tạo lại VM trong cùng process không được hỗ trợ. Với sản phẩm cần xử lý nhiều request, **khởi tạo VM một lần và tái sử dụng có kiểm soát** hoặc dùng **Java worker process** lâu dài.

### 9.2. Không dựa vào nhiều JVM trong cùng process

Theo JNI Specification, **tạo nhiều JVM trong cùng process không được hỗ trợ**. Một native plugin không thể bảo đảm được việc mở một JVM thứ hai bên cạnh VM đã có rồi “mỗi plugin một VM”.

**JNI_GetCreatedJavaVMs** cho phép liệt kê các JVM đã tạo theo khả năng API; nó có thể giúp phát hiện VM hiện có. Nhưng đừng xem API này là một registry có tính năng ownership, permission hoặc classloader isolation. Nếu sản phẩm có thể đã chạy trong một host có JVM, phải phối hợp lifecycle với host đó hoặc tách thành process khác.

### 9.3. Đừng giả định DestroyJavaVM là restart

**DestroyJavaVM** là yêu cầu chấm dứt VM, **không phải reset nhẹ để sau đó tạo lại VM ngay**. Thiết kế không nên yêu cầu nhiều vòng **create → destroy → create** trong cùng native process. Cần một process riêng nếu sản phẩm muốn restart Java runtime đáng tin cậy.

Nếu quá trình JVM hoặc một thư viện JNI đã phá hỏng bộ nhớ native, khả năng catch Java exception và gọi DestroyJavaVM cũng không phải biện pháp phục hồi lỗi crash.

### 9.4. DestroyJavaVM có thể phải chờ luồng Java/native còn sống

Theo Invocation API, DestroyJavaVM chờ các **non-daemon threads** không còn hoạt động (với quy tắc về thread hiện hành) trước khi tiến hành quá trình shutdown. Điều này gồm Java threads và native threads đã attach dưới dạng non-daemon. Nếu worker hoặc thread pool vẫn chạy và không dừng, native host có thể bị kẹt ở bước shutdown.

Vì vậy:

1. Ngừng nhận việc mới.
2. Ra lệnh dừng Java executors và native workers.
3. Chờ task hoàn tất có timeout theo chính sách của sản phẩm.
4. Đảm bảo native-created threads tự **DetachCurrentThread** trước khi kết thúc.
5. Xóa global JNI references/cache khi không còn cần.
6. Sau đó mới gọi DestroyJavaVM và xử lý status trả về.

Thư viện Java có thể tạo background threads ngoài dự kiến; cần quan sát thread dump và logs nếu DestroyJavaVM chờ lâu.

### 9.5. Thread gọi JNI_CreateJavaVM là main thread JVM

Thread native thực hiện **JNI_CreateJavaVM** được attached như **JVM main thread** và nhận JNIEnv của nó. Trong code demo, đó là C main thread. Tuy nhiên, JNI Specification lưu ý một số hệ điều hành xử lý **primordial process thread** khác thường, ví dụ hạn chế stack gây rủi ro StackOverflowError. Đối với host production, cân nhắc tạo **một native thread chuyên trách việc khởi tạo JVM** với stack size đủ, nếu phù hợp thiết kế.

Không vì vậy mà chuyển JNIEnv được trả về cho thread chuyên trách sang một thread C khác. **JNIEnv chỉ thuộc thread đã nhận nó**. Native worker khác phải GetEnv/AttachCurrentThread để có env riêng.

## 10. Native threads khi JVM do C tạo

Giả sử C host có một thread pool riêng và các worker muốn gọi Java. **JavaVM \*** có thể được chia sẻ trong phạm vi vòng đời hợp lệ, nhưng **JNIEnv \*** không được chia sẻ qua thread.

Mẫu helper C:

~~~c
/*
 * Snippet: dùng trong native worker đã nhận JavaVM* hợp lệ.
 * Chỉ minh họa việc lấy JNIEnv và ownership của detach.
 */
static int get_env_for_worker(
        JavaVM *vm, JNIEnv **out_env, int *attached_here) {
    *out_env = NULL;
    *attached_here = 0;

    jint status = (*vm)->GetEnv(
        vm, (void **)out_env, JNI_VERSION_1_8
    );

    if (status == JNI_OK) {
        return 1; /* Worker đã attached. */
    }

    if (status != JNI_EDETACHED) {
        return 0; /* Có thể JNI_EVERSION. */
    }

    if ((*vm)->AttachCurrentThread(
            vm, (void **)out_env, NULL) != JNI_OK) {
        return 0;
    }

    *attached_here = 1;
    return 1;
}
~~~

Khi worker hoàn tất Java calls, nếu **attached_here == 1**, nó gọi **DetachCurrentThread** **trên chính worker thread**. Nếu GetEnv trả JNI_OK từ đầu, worker không nên detach một thread được JVM/thành phần khác attach mà nó không sở hữu.

Không giữ lại JNIEnv của thread khởi tạo JVM trong một global variable để worker dùng. Truyền **JavaVM \*** là đúng, còn JNIEnv phải nhận **theo current thread**.

### Local/global references

JNI **jobject**, **jclass** và **jstring local references** của một thread không tự động hợp lệ trên native thread khác hoặc sau khi JNI call/frame kết thúc. Với đối tượng Java cần sống qua nhiều callback từ worker, tạo **NewGlobalRef** trên thread attached hợp lệ và giải phóng bằng **DeleteGlobalRef** khi thật sự không còn cần.

Global reference không làm object thread-safe; nếu nhiều worker cùng thay đổi Java state, vẫn cần lock, volatile, atomic hoặc thiết kế bất biến phù hợp.

### Class loader của native worker

Một native thread tự attach không nhất thiết có class loader context của một Java plugin. **FindClass** gọi từ thread không có Java native-method frame liên quan có thể sử dụng class loader mặc định khác bối cảnh đã nạp plugin. Nếu cần gọi application class của một class loader riêng, nên nhận **Class**, **ClassLoader** hoặc callback object từ phía Java trong context đúng rồi giữ reference có kiểm soát.

Tránh đoán rằng chỉ vì FindClass hoạt động trong một Java-originated native method, nó cũng hoạt động giống hệt trên mọi native thread của C host.

## 11. Quản lý khả năng quan sát và vận hành một JVM nhúng

Embedding khiến VM và native host dùng chung process, vì vậy khi chẩn đoán cần quan sát cả hai phía:

| Nhóm | Nội dung cần theo dõi |
| --- | --- |
| **Startup** | JDK distribution/version, VM options, java.class.path, module configuration, trạng thái JNI_CreateJavaVM |
| **Native loader** | Vị trí libjvm, dependency, OS/CPU/ABI, mã lỗi dynamic linker |
| **Java component** | Class/Method lookup, exception message/stack, thời gian gọi Java, cache method IDs có lifecycle đúng |
| **Threads** | Attached native threads, Java non-daemon workers, thread leak, shutdown blockers |
| **Memory** | Heap, off-heap/native allocation, RSS của **toàn process**, stack, GC, JIT/code cache |
| **Release** | Version native host, JVM runtime, Java classes/JAR, binary checksum, rollback và CVE |
| **Crashes** | JVM crash log, native core dump, Java stack + native stack/symbol tương ứng |

**Không cho rằng Java heap metric mô tả toàn bộ memory usage.** Khi JVM sống bên trong một C++ host có engine native lớn, bộ nhớ của cả C++ và JVM đều góp vào RSS và giới hạn container/process.

Với production, cân nhắc thiết kế **health check**:

- Đã tạo được JVM chưa?
- Class cần gọi có tìm thấy không?
- Method signature có khớp không?
- Một invocation an toàn có trả kết quả đúng không?
- Worker threads/callback có hoạt động và shutdown được không?

Một **JNI_CreateJavaVM thành công** chưa bảo đảm thư viện Java dùng được. Tương tự, **FindClass thành công** chưa đảm bảo class initialization hoặc method call không gây lỗi.

### Shutdown và System.exit

Java code chạy bên trong embedded JVM vẫn có thể gọi **System.exit** hoặc một API gây shutdown process. Đây là lý do cần quy định hợp đồng giữa host và Java component: thông thường thành phần Java nhúng **không tự kiểm soát việc kết thúc toàn tiến trình**.

Đừng xây dựng hệ thống dựa trên giả định rằng gọi System.exit ở Java chỉ “tắt plugin Java” mà giữ C++ host bình thường. Khi cần cách ly quyền điều khiển tiến trình, một Java process riêng an toàn về kiến trúc hơn.

## 12. Kiểm thử kiến trúc trước khi chọn embedding

Hãy thiết kế các phép thử để xác minh lý do chọn kiến trúc:

1. **Baseline:** so sánh C-native implementation, embedded JVM và Java child process theo cùng workload/semantics nếu các lựa chọn đều khả thi.
2. **Startup time:** đo thời gian nạp libjvm, khởi tạo VM, load classes và warm-up trước request đầu tiên.
3. **Per-call latency:** đo crossing, lookup, chuyển dữ liệu, GC, p50/p95/p99, batch size và concurrency, không chỉ Java method body.
4. **Memory:** đo RSS toàn process, Java heap, native allocations, code cache, thread stacks và startup spikes.
5. **Failure injection:** thiếu classpath/JDK, sai libjvm, method signature thay đổi, Java exception và native crash trong môi trường test.
6. **Concurrency:** native worker attach/detach, JNIEnv đúng thread, local/global references và class loader.
7. **Shutdown:** có Java thread pool/non-daemon thread, callback dang dở, worker native đang chạy; đo khả năng stop/destroy.
8. **Distribution:** chạy trên từng OS/architecture/ABI/JDK đích, gồm container thực tế và dependency bậc hai.
9. **Upgrade/rollback:** kiểm tra Java components và JVM binary theo ma trận version, cho phép rollback toàn bộ gói.
10. **Security:** kiểm tra nguồn/JDK patch, native library permissions và ranh giới dữ liệu tin cậy. Khi chạy code Java không tin cậy, đánh giá process isolation.

Nếu yêu cầu **crash isolation** và độc lập version là chủ đạo, kết quả đánh giá có thể nghiêng về child Java process ngay cả khi IPC chậm hơn một số microbenchmarks.

## 13. Các lỗi tư duy và triển khai thường gặp

| Sai lầm | Tại sao sai | Giải pháp |
| --- | --- | --- |
| “Có JNI nên C bắt buộc tự tạo JVM” | Khi Java gọi native, JVM đã tồn tại và đã truyền JNIEnv | Dùng JNIEnv sẵn có; chỉ nhúng VM khi native host sở hữu entry point |
| “Mỗi request tạo một JVM để tránh state cũ” | Startup tốn kém; nhiều/recreate VM trong một process không được hỗ trợ như kỳ vọng | Một VM sống dài hoặc Java worker process |
| “Một host C++ có thể tạo nhiều JVM cho mỗi plugin” | JNI spec không hỗ trợ nhiều VM trong cùng process | Một VM với class loader/lifecycle kiểm soát hoặc nhiều process |
| “JNI_CreateJavaVM tạo một process Java riêng” | JVM được nạp trong **cùng process** | Dùng IPC/process spawn nếu cần ranh giới process |
| “Có JavaVM thì gọi FindClass được ngay ở mọi native thread” | FindClass là hàm JNIEnv; thread phải attached | GetEnv/AttachCurrentThread và nhận JNIEnv riêng |
| “Có một JNIEnv global cho tất cả worker” | JNIEnv là thread-specific | Lưu JavaVM; lấy JNIEnv ở thread hiện tại |
| “C chỉ cần tìm thấy libjvm là Java class sẽ tự hoạt động” | Còn classpath, dependencies, method signatures, initialization | Health check đầy đủ và integration smoke test |
| “DestroyJavaVM luôn trả về ngay” | Phải phối hợp non-daemon threads và shutdown sequence | Stop/join/detach trước khi destroy |
| “Destroy xong có thể create lại dễ dàng” | Không có hợp đồng restart VM đáng tin trong một process | Restart native process/worker process |
| “JVM nhúng không tốn thêm RAM đáng kể” | Heap, native memory, JIT, GC, thread stacks đều cùng process | Đặt ngân sách tài nguyên và đo RSS |
| “C có thể truyền JNIEnv sang pthread” | Con trỏ JNIEnv không hợp lệ ở thread khác | Chia sẻ JavaVM và attach worker riêng |
| “Plugin Java có thể System.exit mà không ảnh hưởng C++ host” | Java runtime sống trong cùng process | Đặt hợp đồng shutdown; cô lập process nếu cần |
| “Một JNI call nhanh nên embedding chắc chắn tốt hơn IPC” | Bỏ qua startup, marshalling, memory và incident cost | Benchmark end-to-end và tính chi phí vận hành |

## 14. Checklist quyết định nhanh

Trước khi **C/C++ tự tạo JVM**, trả lời các câu hỏi sau:

- [ ] C/C++ **thật sự là entry point không thể thay đổi** của sản phẩm?
- [ ] Java component có đủ giá trị để chấp nhận đóng gói/vận hành cả JVM trong process?
- [ ] Có JVM nào đã chạy trong host chưa? Nếu có, đã xác định cơ chế sử dụng VM hiện hữu?
- [ ] Đã so sánh JNI embedding với Java child process/IPC về latency, isolation, versioning và deployment?
- [ ] Đã xác định một owner cho **JNI_CreateJavaVM**, **JavaVM \*** và **DestroyJavaVM**?
- [ ] Có kế hoạch cấu hình **classpath/module path, heap, GC và JVM options** theo JDK mục tiêu?
- [ ] Native executable có thể tìm đúng **libjvm** và các dependencies trên từng OS/ABI không?
- [ ] Có kiểm tra **FindClass/GetMethodID/call** và xử lý Java exception đúng nhánh không?
- [ ] Nếu dùng nhiều native threads, mỗi worker lấy JNIEnv riêng, attach/detach và cleanup đúng lifecycle?
- [ ] Có quy định classloader, local/global reference ownership và synchronization?
- [ ] Có shutdown policy cho Java non-daemon threads, executors, callback và native workers?
- [ ] Không dựa vào nhiều JVM hoặc vòng create/destroy/recreate trong cùng process?
- [ ] Đã đo startup, RSS, p95 latency, GC, crash behavior và khả năng rollback trên môi trường thật?
- [ ] Java component không tự gọi System.exit làm mất quyền kiểm soát process của host?

Nếu các điều kiện trên không đạt, **chưa nên nhúng JVM** chỉ vì có một thư viện Java cần dùng; hãy đánh giá lại ranh giới process hoặc tổ chức entry point.

## 15. Câu hỏi tự kiểm tra

**1. Java server đã chạy và một JNI native method cần gọi một Java method khác. Có cần JNI_CreateJavaVM không?**

**Đáp án:** Không. JVM đã có; native method nhận **JNIEnv của thread hiện tại** và có thể dùng JNI API để gọi Java trong cùng JVM. Nếu thread native do C tự tạo muốn gọi Java, nó cần attach vào JVM hiện hữu.

**2. C++ ứng dụng sở hữu UI và main loop, nhưng một thuật toán nghiệp vụ chỉ có trong Java. Có nên cân nhắc embedding?**

**Đáp án:** Có. Khi native host phải giữ entry point và Java component cần được gọi trực tiếp, JNI Invocation API là một phương án. Tuy nhiên cần so với Java process riêng theo latency, crash isolation, maintenance, startup và packaging.

**3. JNI_CreateJavaVM trả những gì khi thành công?**

**Đáp án:** Một **JavaVM \*** để thao tác cấp VM và một **JNIEnv \*** hợp lệ cho **thread đã gọi tạo VM**, cùng mã trạng thái **JNI_OK**. JNIEnv đó không được dùng trên thread khác.

**4. Vì sao không nên tạo JVM mỗi lần có request?**

**Đáp án:** JVM startup tốn tài nguyên và không có hợp đồng tạo nhiều/recreate VMs đáng tin trong một process. Nên duy trì một VM được quản lý lâu dài hoặc dùng Java worker process nếu cần restart/cô lập.

**5. Nếu JNI_CreateJavaVM thành công nhưng FindClass thất bại, nên điều tra điều gì?**

**Đáp án:** Classpath/module path, đường dẫn làm việc, dependencies/class loader, tên lớp dạng JNI (**/** thay cho **.**) và Java exception pending. Đây không nhất thiết là lỗi khởi tạo VM.

**6. Khi host gọi DestroyJavaVM nhưng bị chờ lâu, nguyên nhân có thể là gì?**

**Đáp án:** Java non-daemon threads hoặc native threads attached dạng non-daemon chưa dừng; shutdown hooks/cleanup có thể kéo dài. Cần có stop/join/detach đúng lifecycle.

**7. Vì sao embedded JVM không cung cấp crash isolation?**

**Đáp án:** Native host và JVM dùng **cùng process**. Một lỗi C/JNI hoặc crash nghiêm trọng của runtime có thể làm sập toàn bộ ứng dụng. Process Java riêng mới tạo ranh giới tiến trình hữu ích.

**8. Một JNI local reference lấy từ thread tạo JVM có thể chuyển sang C worker thread rồi dùng không?**

**Đáp án:** Không. Cần một **global reference** nếu object phải được chia sẻ qua thread/lượt gọi và worker phải có **JNIEnv riêng**; chủ sở hữu phải xóa global ref lúc không còn cần.

**9. Trong ví dụ, JVM có phải chạy một Java main() không?**

**Đáp án:** Không. Host C dùng **FindClass** và **GetStaticMethodID** để gọi thẳng phương thức Java static **calculate(int)**. JVM chỉ cần được tạo và nhìn thấy class.

**10. Khi nào child Java process có thể tốt hơn embedding dù có IPC?**

**Đáp án:** Khi cần cô lập crash/memory, nâng cấp Java độc lập, giới hạn quyền/tài nguyên hoặc xử lý plugin không tin cậy; lợi ích vận hành có thể vượt chi phí IPC.

## Tài liệu chính thức

- [Oracle JNI Specification — The Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — The Invocation API (JDK 26)](https://docs.oracle.com/en/java/javase/26/docs/specs/jni/invocation.html).
- [Oracle JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification — JNI Functions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Java SE Runtime — Shutdown and embedded JVM considerations](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Runtime.html).

**Điểm cần nhớ:** **Ứng dụng C/C++ chỉ nên tự tạo JVM khi native host thực sự cần sở hữu tiến trình và chạy Java code bên trong process đó**. Nếu Java đã là ứng dụng chính, hãy để Java gọi native code; nếu cần cô lập lỗi hoặc nâng cấp độc lập, hãy cân nhắc Java process riêng. Khi chọn embedding, coi **JNI_CreateJavaVM, JNIEnv theo thread, classloader, tài nguyên và DestroyJavaVM** là một hợp đồng vòng đời dài hạn cần quản lý, kiểm thử và vận hành.
