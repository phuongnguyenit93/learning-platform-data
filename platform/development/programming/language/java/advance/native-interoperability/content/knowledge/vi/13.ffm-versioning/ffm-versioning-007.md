# Chọn FFM hay JNI theo phiên bản Java và mức độ phụ thuộc vào đối tượng JVM

**Foreign Function & Memory API (FFM)** và **Java Native Interface (JNI)** đều giúp Java phối hợp với mã native, nhưng giải quyết những bài toán không hoàn toàn giống nhau. Với thư viện C có ABI rõ ràng, chủ yếu trao đổi số, con trỏ, cấu trúc và vùng nhớ ngoài heap, FFM chuẩn từ **JDK 22** thường giúp viết phần lớn binding bằng Java. Ngược lại, khi native code phải trực tiếp thao tác **`jobject`, `jclass`, `JNIEnv`, Java fields/methods, exception, class loader** hoặc dùng Invocation API để tạo/nhúng JVM, JNI vẫn là giao diện đúng.

Quyết định còn phụ thuộc **phiên bản Java thực sự dùng để biên dịch/chạy**. Một ví dụ dùng `java.lang.foreign.*` bản chuẩn của JDK 22 **không tự động chạy** trên Java 17 hay Java 21; cũng không có chuyện FFM thay thế mọi khả năng JNI chỉ vì hỗ trợ “upcall”. Bài này cung cấp ma trận phiên bản, tiêu chí kỹ thuật, các rủi ro về ABI và lifetime, hai ví dụ hoàn chỉnh dùng chung một thư viện C, cùng quy trình ra quyết định/migration có thể áp dụng trong dự án.

## 1. Hai ranh giới khác nhau: C ABI và JVM object model

~~~text
                              CHƯƠNG TRÌNH JAVA
                                     |
                +--------------------+--------------------+
                |                                         |
          FFM / java.lang.foreign                    JNI / native methods
                |                                         |
     Linker + SymbolLookup +                     javac -h + JNIEXPORT
     FunctionDescriptor + Arena                  + JNIEnv / jobject
                |                                         |
        Native C ABI function                     JNI entry point
   (int, double, pointer, struct...)        (JNIEnv*, jclass/jobject, ...)
                |                                         |
        Native memory / thư viện C         JVM object graph, fields, methods,
                                          exceptions, arrays, class loaders
~~~

**FFM** dùng `Linker.nativeLinker()` để tạo Java `MethodHandle` cho một hàm theo **ABI native**, mô tả chữ ký bằng `FunctionDescriptor`, truy địa chỉ symbol bằng `SymbolLookup` và làm việc với dữ liệu ngoài heap bằng `MemorySegment`/`Arena`. Nó không cần viết một hàm `Java_package_Class_method` để gọi C function thông thường.

**JNI** định nghĩa giao thức giữa JVM và native code. Java khai báo `native`, C/C++ triển khai function JNI với `JNIEnv *` và `jobject` hoặc `jclass`, từ đó có thể đọc/ghi field, tạo String/array, gọi Java method, quản lý local/global refs, throw exception và tương tác sâu với object model.

Cả hai cuối cùng đều thực thi **mã native không được Java memory-safety bảo vệ hoàn toàn**. FFM kiểm soát bounds/lifetime của các `MemorySegment` mà Java quản lý, nhưng C vẫn có thể dereference pointer sai, ghi quá buffer hoặc vi phạm ABI. JNI cũng không tự biến mọi truy cập C thành an toàn.

### 1.1. “Native gọi ngược Java” có hai nghĩa

Một API C có callback kiểu:

~~~c
/* Callback C ABI: C nhận function pointer, không biết jobject. */
int32_t run_callback(int32_t x, int32_t (*callback)(int32_t));
~~~

FFM tạo **upcall stub** từ Java `MethodHandle`, chuyển stub thành function pointer cho C, và C gọi lại Java qua ABI callback. Đây là **FFM upcall**, không phải truy cập tùy ý vào JVM heap. Callback target có thể là Java method (kể cả method handle đã bind tới một object), nhưng native chỉ thấy function pointer và dữ liệu theo ABI.

Ngược lại, C code cần:

~~~c
/* Mảnh minh họa JNI, không phải hàm C độc lập. */
jmethodID mid = (*env)->GetMethodID(env, clazz, "onEvent", "(I)V");
(*env)->CallVoidMethod(env, object, mid, (jint)42);
~~~

thì **JNI** mới có `JNIEnv`, `jobject`, method ID và Java exception semantics cần thiết. FFM `upcallStub` không thay thế trực tiếp `GetMethodID`/`CallVoidMethod`. Nếu muốn dùng FFM với thư viện phụ thuộc JNI, phải thiết kế một **lớp wrapper C ABI** hoặc giữ JNI cho phần liên quan JVM.

## 2. Ma trận phiên bản: FFM chưa phải API ổn định trước Java 22

| Phiên bản JDK | Tình trạng FFM | Lựa chọn thực tế |
| --- | --- | --- |
| **Java 8–15** | Chưa có FFM hợp nhất và ổn định như JDK 22 | JNI là API chuẩn sẵn có để tự viết native bridge; có thể xem xét binding libraries phù hợp dự án |
| **Java 16** | Foreign Linker/Memory APIs ở giai đoạn incubator (khác API chuẩn JDK 22) | Không coi source FFM 22 chạy được; JNI phù hợp khi cần API Java chuẩn tồn tại xuyên phiên bản |
| **Java 17** | `jdk.incubator.foreign`, **incubator** (JEP 412), API khác `java.lang.foreign` final | Với Java 17 baseline, **ưu tiên JNI** cho binding hệ thống/ứng dụng cần ổn định; FFM incubator chỉ khi chấp nhận phụ thuộc thử nghiệm |
| **Java 18** | FFM incubator vòng tiếp theo (JEP 419) | Cùng lưu ý: chưa phải API final |
| **Java 19** | FFM **first preview** (JEP 424) | Có thể đánh giá thử, nhưng API/flags gắn với đúng release |
| **Java 20** | FFM **second preview** (JEP 434) | Chưa là API Java SE final |
| **Java 21 (LTS)** | FFM **third preview** (JEP 442), package `java.lang.foreign` nhưng vẫn preview | Nếu cần code production không dựa preview, ưu tiên JNI hoặc hoãn binding FFM đến baseline 22+; preview cần `--enable-preview` và version-specific build |
| **Java 22+** | FFM **final/standard** (JEP 454), `java.lang.foreign` | FFM là lựa chọn đầu tiên đáng thử cho C ABI + foreign memory; JNI vẫn cần khi native phải thao tác JVM objects |
| **Java 24+** | FFM tiếp tục là API chuẩn; JEP 472 thống nhất cảnh báo **native access** cho JNI và FFM | Phân quyền native access bằng `--enable-native-access`; không dựa vào hành vi cảnh báo mặc định mãi mãi |

**Ba phân biệt:**

1. **Incubator ≠ preview ≠ final.** Java 17 có `jdk.incubator.foreign` không làm cho `import java.lang.foreign.*;` của Java 22 compile được. Java 21 có package gần tương tự nhưng **vẫn preview**; code/behavior có thể khác bản final.
2. **FFM chuẩn từ JDK 22** không đồng nghĩa “Java 22 là phiên bản tối thiểu của JNI”; JNI đã tồn tại lâu và vẫn là chuẩn hỗ trợ native methods.
3. **JDK version là một ràng buộc build/runtime thực tế**, không chỉ syntax. Một artifact biên dịch vào JDK 22 API và bytecode không được triển khai nguyên trạng lên JRE 17 hay 21.

Java 17 và 21 là những ví dụ phổ biến của nền tảng LTS trong dự án doanh nghiệp. Với Java 21 LTS, nếu hệ thống có chính sách cấm preview, đừng chọn FFM preview chỉ vì thấy import hợp lệ. Bạn có thể giữ native wrapper JNI hiện tại, tách C ABI cho dễ chuyển đổi, và lên kế hoạch nâng baseline JDK trước khi chuyển FFM.

### 2.1. Khi nào cần flags?

- **Java 17 incubator:** cần `--add-modules jdk.incubator.foreign` để truy cập incubator module, cùng các điều kiện riêng của phiên bản; ví dụ `java.lang.foreign` trong bài **không dùng** được.
- **Java 21 preview:** khi biên dịch/chạy preview feature cần `--enable-preview` kèm release phù hợp, và phải dùng code đúng API JDK 21. Không áp dụng nguyên lệnh Java 22 cho JDK 21.
- **Java 22 trở lên:** FFM final, **không cần `--enable-preview`**; các thao tác FFM nguy hiểm/restricted như `SymbolLookup.libraryLookup`, `Linker.downcallHandle`, `Linker.upcallStub` cần quyền **native access** cho module gọi.
- **Java 24+ với JNI:** JEP 472 chuẩn hóa quy tắc native access. JNI load/link của module chưa được cấp quyền có thể phát warning mặc định; tùy `--illegal-native-access` có thể bị từ chối. Đây không phải tuyên bố JNI bị xóa hoặc bị deprecate.

Với code ở **classpath** (unnamed module), hình thức phổ biến là:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

Với **named module**, thay `ALL-UNNAMED` bằng tên module chứa mã gọi restricted native APIs, ví dụ `--enable-native-access=com.example.nativebridge`. Nên chọn quyền tối thiểu cần thiết thay vì bật cho mọi module. Tùy JVM version, `--illegal-native-access=deny` là cách kiểm tra chủ động để phát hiện nơi còn thiếu quyền.

Không bỏ qua các cảnh báo native access chỉ vì chương trình vẫn chạy: các cảnh báo là thông tin về **chính sách runtime**, khác hẳn lỗi symbol hoặc ABI.

## 3. Đối tượng JVM là điểm phân nhánh quan trọng nhất

Hãy nhìn **contract của thư viện C**, chứ không nhìn tên công nghệ:

### 3.1. Trường hợp hợp với FFM

- Hàm C nhận số nguyên/số thực, pointer, C string, native array, struct/union, opaque handle.
- Đầu ra là primitive value, struct, buffer do một bên sở hữu, native error code hoặc handle.
- Native callback theo **function pointer C ABI**; Java cung cấp `MethodHandle` qua `Linker.upcallStub` và bảo đảm callback không tồn tại quá lifetime của stub.
- C library vốn độc lập với JVM: hệ thống mã hóa, nén, toán học, thiết bị, database driver lõi, native SDK có C headers.
- Java có thể biểu diễn ABI chính xác bằng `FunctionDescriptor`, `ValueLayout`, `MemoryLayout`; caller có thể quản lý vùng nhớ và ownership qua `Arena`.

Ví dụ header phù hợp:

~~~c
#include <stdint.h>

int64_t sum_i32(const int32_t *data, int32_t count);
int32_t call_unary(int32_t x, int32_t (*callback)(int32_t));
~~~

Hai function không tham chiếu `JNIEnv`, `jobject` hoặc class loader. Java 22+ có thể tạo downcall trực tiếp, không cần wrapper JNI.

### 3.2. Trường hợp hợp với JNI

- Native method nhận `String`, Java object instance, Java array, `Class<?>`, `Throwable` và phải thao tác trên chúng **như Java objects**.
- C/C++ cần `GetObjectClass`, `GetFieldID`, `CallObjectMethod`, `NewString`, `NewObject`, `GetArrayLength` hoặc quản lý `NewGlobalRef`/`DeleteGlobalRef`.
- Native phải gọi Java methods trên một `jobject` được cấp, duy trì Java callback refs, tra cứu các class theo class loader, attach thread và xử lý pending Java exceptions.
- Native library tích hợp với mã JNI hiện hữu, binding dài hạn phải chạy JDK 17/21 không dùng preview.
- Host native **nhúng một JVM** và gọi Invocation API như `JNI_CreateJavaVM`/`DestroyJavaVM`; FFM từ Java không thay thế API native tạo JVM.

Ví dụ JNI nhận một Java array:

~~~c
/* Mảnh minh họa: env thuộc current JNI thread. */
JNIEXPORT jlong JNICALL Java_demo_JniCalc_sum(
    JNIEnv *env, jclass owner, jintArray values);
~~~

JNI biết đây là `jintArray` và có thể dùng `GetIntArrayElements`. FFM khi thấy một C pointer **không thể tự nhận ra nó là `jintArray`** hay gọi `GetObjectArrayElement`. Đừng cast `MemorySegment` thành `jobject` hoặc nhầm `MemorySegment.NULL` với Java `null`.

### 3.3. Có thể dùng cả hai trong một ứng dụng

Một thiết kế hợp lý thường là:

~~~text
Java services / domain classes
            |
            +-- JNI bridge -> Java objects, lifecycle, exceptions
            |
            +-- FFM bridge -> C ABI native engine
                                     |
                                 buffers/structs
~~~

JNI có thể quản lý vài điểm tương tác chặt với JVM, trong khi FFM gọi nhiều hàm C ABI của một native engine thuần. Nếu cùng share native state, phải thiết kế rõ ai tạo/hủy handle, synchronization, classloader và library loading; **đừng có hai lớp giải phóng cùng một pointer**.

Một kiến trúc chuyển đổi thường gặp: tách thuật toán native ra thành **C ABI độc lập JVM**, giữ JNI wrapper mỏng cho caller Java 17 và thêm FFM wrapper cho Java 22+. Hai wrapper có thể cùng gọi một lõi, nhưng API Java phải phù hợp phiên bản chạy.

## 4. FFM hoạt động như thế nào?

FFM chuẩn có các thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Linker.nativeLinker()` | Hiểu ABI native trên OS/CPU hiện tại, tạo downcall/upcall |
| `SymbolLookup` | Tìm địa chỉ symbol C export trong thư viện, không phải tìm Java method |
| `FunctionDescriptor` | Khai báo kiểu ABI return và từng đối số |
| `ValueLayout`/`MemoryLayout` | Mô tả primitive, address, struct, sequence, alignment/padding |
| `MethodHandle` | Đại diện lời gọi native function từ Java; chữ ký carrier phải khớp |
| `MemorySegment` | View vùng nhớ, có size/scope và kiểm tra bounds ở phía Java |
| `Arena` | Quản lý lifetime của vùng nhớ native, đồng thời có thể quản lý thời gian sống của library lookup/upcall stub |
| `Linker.upcallStub` | Tạo function pointer C ABI gọi tới Java method handle |

Đường gọi đơn giản:

~~~text
Path tới native library
  -> SymbolLookup.libraryLookup(path, arena)
  -> find("sum_i32") -> MemorySegment chứa địa chỉ symbol
  -> Linker.downcallHandle(symbol, FunctionDescriptor...)
  -> MethodHandle.invokeExact(...)
  -> C ABI function -> kết quả Java primitive/MemorySegment
~~~

**Vòng đời:** `Arena.ofConfined()` là arena chỉ một thread sở hữu, `close()` invalidates những segment/stub gắn scope. `Arena.ofShared()` dành cho access đa thread khi phải có coordination; `Arena.global()` không tự đóng, không phù hợp nếu cần giải phóng theo request. `Arena.ofAuto()` phụ thuộc GC, không có thời điểm giải phóng xác định.

**Bounds và lifetime không phải ABI correctness.** Nếu mô tả C `long` 32 bit ở Windows bằng Java `JAVA_LONG` 64 bit, hoặc bỏ padding trong C struct, lời gọi có thể sai dù Java `MemorySegment` có bounds checks. Với type phụ thuộc nền tảng như `size_t`, `long`, `wchar_t`, dùng canonical layouts, header và ABI target để xác định đúng; không hard-code “mọi pointer đều long” hay “C long luôn 64 bit”.

**Upcall:** method handle có thể gọi Java, nhưng native C được trao một C function pointer theo signature đã mô tả, không được trao quyền trực tiếp đọc object heap. Nếu C lưu callback function pointer sau khi arena bị close, đó là lỗi lifetime; ngừng callbacks trước khi close và xử lý thread/exception của callback rõ ràng.

## 5. JNI hoạt động như thế nào?

Đường gọi JNI điển hình:

~~~text
Java: private static native long sum(int[] values);
  -> javac -h sinh demo_JniCalc.h
  -> C export Java_demo_JniCalc_sum(JNIEnv*, jclass, jintArray)
  -> native gọi GetArrayLength / GetIntArrayElements
  -> native tính toán và ReleaseIntArrayElements
  -> native trả jlong cho Java
~~~

`JNIEnv *` là bảng hàm JNI gắn với thread, không được cache dùng xuyên thread. `jobject` và `jclass` là JNI references chứ không phải địa chỉ raw Java object. `jmethodID` và `jfieldID` là opaque IDs hợp lệ theo lifetime lớp; không biến chúng thành FFM pointer tùy ý. Native code phải release borrowed array/string memory, xử lý pending Java exception, và xóa JNI global refs khi không còn dùng.

`JNIEXPORT`, `JNICALL` và generated header từ `javac -h` giúp giữ ABI chính xác. JNI không cần dùng `Linker` của FFM; cả hai dùng OS shared libraries (`.so`, `.dylib`, `.dll`), nhưng cách **tìm function/đối số** khác nhau. Một hàm C ABI như `sum_i32` không tự trở thành JNI native method chỉ vì có cùng tên với Java method.

JNI phù hợp khi object access là nghiệp vụ của bridge. Nếu chỉ truyền hàng triệu giá trị số sang C, JNI vẫn làm được, nhưng có thể phải viết nhiều glue code; FFM và việc batch dữ liệu qua `MemorySegment` là lựa chọn cần benchmark, không nên tuyên bố công nghệ nào luôn nhanh hơn.

## 6. Ví dụ hoàn chỉnh: một native library, hai Java clients, hai baseline JDK

Ví dụ minh họa **cùng nghiệp vụ tính tổng số nguyên** theo hai giao diện:

- **JNI client — Java 17+:** truyền `int[]`, JNI lấy phần tử qua `JNIEnv`, trả `long`. Đây là ranh giới **Java array object**.
- **FFM client — Java 22+:** tạo off-heap int buffer, gọi C ABI `sum_i32` bằng `Linker`, đồng thời thử C callback `call_unary` bằng `upcallStub`. Đây là ranh giới **pointer + C ABI**, không phải truy cập `jintArray`.

Kết quả được thiết kế xác định, không phụ thuộc benchmark hay output của GC. Chạy từng main class trong **process Java riêng** để tránh nhầm lifecycle/ownership của thư viện khi thử nghiệm.

~~~text
native-choice/
├── src/
│   └── demo/
│       ├── JniCalc.java          (Java 17+)
│       └── FfmCalc.java          (Java 22+)
├── native/
│   └── calcbridge.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 6.1. Thư viện C11 — `native/calcbridge.c`

~~~c
#include "demo_JniCalc.h"
#include <stdint.h>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

/* C ABI thuần, dùng cho FFM. */
EXPORT int64_t sum_i32(const int32_t *data, int32_t count) {
    if (count <= 0 || data == NULL) {
        return 0;
    }
    int64_t total = 0;
    for (int32_t i = 0; i < count; ++i) {
        total += (int64_t)data[i];
    }
    return total;
}

typedef int32_t (*unary_callback)(int32_t);

/* C ABI thuần: callback nhận/trả int32_t. */
EXPORT int32_t call_unary(int32_t value, unary_callback callback) {
    if (callback == NULL) {
        return 0;
    }
    return callback(value);
}

/* JNI entry point dành riêng cho Java int[]. */
JNIEXPORT jlong JNICALL Java_demo_JniCalc_sum(
        JNIEnv *env, jclass owner, jintArray values) {
    (void)owner;

    if (values == NULL) {
        jclass ex = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (ex != NULL) {
            (*env)->ThrowNew(env, ex, "values");
            (*env)->DeleteLocalRef(env, ex);
        }
        return 0;
    }

    jsize count = (*env)->GetArrayLength(env, values);
    if (count == 0) {
        return 0;
    }

    jint *data = (*env)->GetIntArrayElements(env, values, NULL);
    if (data == NULL) {
        return 0; /* Thường có pending exception từ JNI. */
    }

    jlong total = 0;
    for (jsize i = 0; i < count; ++i) {
        total += (jlong)data[i];
    }

    (*env)->ReleaseIntArrayElements(env, values, data, JNI_ABORT);
    return total;
}
~~~

**Ba exported functions có ý nghĩa khác nhau:**

- `sum_i32(const int32_t *, int32_t)`: C ABI. Java FFM truyền `MemorySegment` địa chỉ vùng nhớ cùng số phần tử; C không kiểm tra được độ hợp lệ của pointer tùy ý mà caller đã cung cấp. Quy tắc caller: dữ liệu phải chứa ít nhất `count` phần tử `int32_t` hợp lệ, nếu `count>0`; ở đây `count<=0` hoặc null cho kết quả 0. Đó là contract ví dụ, không phải quy tắc của mọi C library.
- `call_unary(int32_t, unary_callback)`: nhận function pointer C ABI rồi gọi **đồng bộ một lần**, không giữ pointer sau khi return. Điều này làm lifetime FFM stub dễ kiểm soát.
- `Java_demo_JniCalc_sum`: giao thức JNI, nhận `jintArray` Java, kiểm tra null/empty, mượn pointer bằng `GetIntArrayElements` rồi release với `JNI_ABORT` (vì chỉ đọc). Tính cộng trong `jlong` để tránh signed overflow 32 bit.

Một thư viện có thể export cả JNI entry point và C ABI functions. **FFM chỉ tìm `sum_i32` và `call_unary`**, không cần `JNIEnv*`; **JNI client gọi `Java_demo_JniCalc_sum`** qua quy tắc JNI. Việc FFM dùng `SymbolLookup.libraryLookup` không có nghĩa JVM tự gọi `JNI_OnLoad` của thư viện (nếu có); hai cơ chế loading/linking không nên bị đánh đồng.

Dòng `#include "demo_JniCalc.h"` yêu cầu bạn chạy `javac -h` cho `JniCalc.java` trước khi build C; nó giúp compiler đối chiếu generated prototype. C dùng `int32_t`/`int64_t` từ `<stdint.h>`, tránh mơ hồ kích thước kiểu `long` của C trên Windows/Linux.

### 6.2. Java 17+ — `src/demo/JniCalc.java`

~~~java
package demo;

public final class JniCalc {
    private JniCalc() {
    }

    static {
        System.loadLibrary("calcbridge");
    }

    private static native long sum(int[] values);

    public static void main(String[] args) {
        System.out.println("JNI sum=" +
                sum(new int[] {7, -2, 9}));
        System.out.println("JNI empty=" + sum(new int[0]));
    }
}
~~~

Java method `sum` nhận **Java array**, không phải pointer. JNI thấy `jintArray`, biết length qua `GetArrayLength`; Java không phải copy thủ công sang off-heap. C phải release pointer mượn và không được giữ `jint *` để sử dụng sau JNI call.

**Stdout chính xác** khi load được native library:

~~~text
JNI sum=14
JNI empty=0
~~~

Với Java 17 trở lên, mã Java trên không yêu cầu FFM, incubator hay preview flags. JDK 24+ có thể cần cấu hình native access để tránh warning hoặc tuân thủ chế độ deny, được trình bày ở phần chạy.

### 6.3. Java 22+ — `src/demo/FfmCalc.java`

~~~java
package demo;

import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;

public final class FfmCalc {
    private FfmCalc() {
    }

    // Java callback: C thấy function pointer (int32_t) -> int32_t.
    private static int twice(int value) {
        return value * 2;
    }

    public static void main(String[] args) throws Throwable {
        Path library = Path.of(
                "build", "lib",
                System.mapLibraryName("calcbridge")).toAbsolutePath();

        try (Arena arena = Arena.ofConfined()) {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, arena);

            // int64_t sum_i32(const int32_t*, int32_t);
            MethodHandle sum = linker.downcallHandle(
                    symbols.find("sum_i32").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_LONG,
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT));

            MemorySegment data = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 7, -2, 9);
            long total = (long) sum.invokeExact(data, 3);
            long empty = (long) sum.invokeExact(
                    MemorySegment.NULL, 0);

            System.out.println("FFM sum=" + total);
            System.out.println("FFM empty=" + empty);

            // int32_t call_unary(int32_t, int32_t (*)(int32_t));
            MethodHandle callUnary = linker.downcallHandle(
                    symbols.find("call_unary").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS));

            MethodHandle javaTarget = MethodHandles.lookup()
                    .findStatic(
                            FfmCalc.class,
                            "twice",
                            MethodType.methodType(int.class, int.class));

            FunctionDescriptor callbackType =
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT);

            MemorySegment callback =
                    linker.upcallStub(javaTarget, callbackType, arena);

            int result = (int) callUnary.invokeExact(21, callback);
            System.out.println("FFM callback=" + result);
        }
    }
}
~~~

**Stdout chính xác** khi build và quyền native access đúng:

~~~text
FFM sum=14
FFM empty=0
FFM callback=42
~~~

Mã này dùng API chuẩn **JDK 22** (`java.lang.foreign`, `Arena.allocateFrom`, `Linker.downcallHandle`, `Linker.upcallStub`). **Không compile bằng JDK 17 hoặc JDK 21**; code demo không được viết cho incubator/preview APIs của các release đó.

Giải thích ABI và lifetime:

1. `SymbolLookup.libraryLookup(path, arena)` load/tìm symbol tại **đường dẫn file native thực**. `System.mapLibraryName` tạo tên platform thích hợp: thường là `libcalcbridge.so` (Linux), `libcalcbridge.dylib` (macOS), `calcbridge.dll` (Windows).
2. `FunctionDescriptor.of(JAVA_LONG, ADDRESS, JAVA_INT)` mô tả C return `int64_t`, pointer `const int32_t *`, và `int32_t count` trên các ABI thông dụng. `ADDRESS` có Java carrier type là `MemorySegment`. `MethodHandle.invokeExact` yêu cầu chữ ký argument/return chính xác.
3. `arena.allocateFrom(JAVA_INT, 7, -2, 9)` cấp native memory (không phải `int[]` Java object), copy ba số vào đó, gắn thời hạn truy cập với `arena`. C chỉ đọc vùng nhớ trong thời gian `arena` còn sống.
4. `MemorySegment.NULL` kết hợp `count=0` hợp lệ với **contract của hàm C trong ví dụ**; không suy ra mọi C function nhận null pointer đều an toàn.
5. `upcallStub` tạo function pointer C ABI gọi tới Java `twice`. C gọi callback **đồng bộ trước khi return**; không giữ lại stub sau khi arena close. Native không được truyền `jobject` hay dùng `JNIEnv` trong lời gọi này.
6. Đóng arena cuối `try` giải phóng những memory segments được cấp bởi arena, làm stub hết hiệu lực và quản lý lifetime của library lookup tương ứng. Không lưu MethodHandle/segment/stub vượt scope rồi gọi lại.
7. Hàm Java `twice` không ném exception trong bài test. Với callback production, xử lý Java exceptions rõ ràng: không tùy tiện để một exception vượt qua biên C function pointer.

Cùng C function `sum_i32` có thể được gọi từ C application khác nếu tuân thủ ABI; JNI function lại phụ thuộc VM. Điều này minh họa vì sao FFM phù hợp cho **native API vốn độc lập JVM**.

## 7. Biên dịch một lần thư viện C, chạy hai đường Java

Tại thư mục `native-choice`, luôn chạy `javac -h` trước để sinh generated header `build/include/demo_JniCalc.h`. Khi thay package hoặc native method signature, phải sinh header và build C lại. Với JNI Java 17+, có thể dùng JDK 17 riêng; để chạy cả FFM hãy dùng **JDK 22+**.

### 7.1. Linux (GCC/Clang, C11)

~~~sh
mkdir -p build/classes build/include build/lib

javac -h build/include -d build/classes src/demo/JniCalc.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/calcbridge.c -o build/lib/libcalcbridge.so

java -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

Sau đó, với **JDK 22+**:

~~~sh
javac -d build/classes src/demo/FfmCalc.java
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

Trên **JDK 24+**, nếu muốn dùng native access theo cách rõ ràng cho JNI client:

~~~sh
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

FFM `SymbolLookup.libraryLookup` sử dụng path file absolute được xây trong Java nên không cần `-Djava.library.path` trong FFM command; JNI `System.loadLibrary` tìm logical library name qua Java native library search path.

### 7.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib

javac -h build/include -d build/classes src/demo/JniCalc.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/calcbridge.c -o build/lib/libcalcbridge.dylib

java -Djava.library.path=build/lib \
  -cp build/classes demo.JniCalc
~~~

FFM client (JDK 22+):

~~~sh
javac -d build/classes src/demo/FfmCalc.java
java --enable-native-access=ALL-UNNAMED \
  -cp build/classes demo.FfmCalc
~~~

Nếu JVM là Apple Silicon, native library phải cùng architecture/ABI với JVM; đổi đuôi file không chuyển x86_64 thành arm64.

### 7.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib

javac -h build\include -d build\classes src\demo\JniCalc.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\calcbridge.c ^
  /link /OUT:build\lib\calcbridge.dll

java -Djava.library.path=build\lib -cp build\classes demo.JniCalc
~~~

FFM client với JDK 22+:

~~~bat
javac -d build\classes src\demo\FfmCalc.java
java --enable-native-access=ALL-UNNAMED -cp build\classes demo.FfmCalc
~~~

Các lệnh Windows dùng **Command Prompt**, `^` là ký tự nối dòng của cmd.exe. Cần dùng `cl` trong Developer Command Prompt và JDK cùng kiến trúc x64. Nếu compiler hoặc JNI headers thuộc toolchain khác, hãy xác minh ABI và các dependency trước khi trộn.

### 7.4. Kiểm tra exported symbols

Linux:

~~~sh
nm -D --defined-only build/lib/libcalcbridge.so
~~~

Kết quả phải bao gồm các tên symbol (địa chỉ và thứ tự không cố định):

~~~text
sum_i32
call_unary
Java_demo_JniCalc_sum
~~~

macOS: `nm -gU build/lib/libcalcbridge.dylib` (tool có thể thêm dấu `_` đầu symbol). Windows: `dumpbin /exports build\lib\calcbridge.dll`. **FFM yêu cầu symbol C ABI export như `sum_i32`**, không dùng tên `Java_demo_JniCalc_sum` trừ khi tự thiết kế gọi JNI entry point (không nên). JNI dựa vào exported JNI name từ `javac -h`, không tự resolve `sum_i32`.

**Chú ý:** đây là cùng một binary library có hai API, nhưng mỗi demo chạy trong **JVM process riêng**. Nếu trong một JVM cần vừa JNI `System.loadLibrary` vừa FFM `libraryLookup` cho cùng library, hãy kiểm tra loader ownership, lifetime, đồng bộ và rule của nhiều class loaders; không tự gọi `dlclose`/`FreeLibrary` để can thiệp vào handle VM đang quản lý.

## 8. So sánh ownership, threading và lỗi tại biên

| Mối quan tâm | JNI | FFM |
| --- | --- | --- |
| Đối tượng Java | `jobject`/`jclass`/`jarray`; JNI API biết object model | C ABI chỉ thấy primitives/pointers, không trực tiếp biết `jobject` |
| Java heap array | Có `Get<Type>ArrayElements`/`Get<Type>ArrayRegion` | Thường copy/marshal dữ liệu sang native `MemorySegment`; không giả định Java `int[]` là C pointer ổn định |
| Native memory | C `malloc/free`, native handles hoặc JNI borrowed pointers | `Arena` có thể sở hữu allocated segments; vẫn phải tuân thủ contract của malloc/free bên C |
| Thread | `JNIEnv *` gắn thread; attach native thread nếu cần | Confined/shared arena và scope checks; native worker thread/callback cần chính sách rõ |
| Callback | C dùng `Call<Type>Method` trên `jobject`/`jclass` | `upcallStub` chuyển MethodHandle thành C function pointer |
| Exception | Pending Java exception trên `JNIEnv`; `ThrowNew`/`ExceptionCheck` | Native C error code/errno/return conventions do wrapper giải mã; callback exceptions cần xử lý có chủ đích |
| Method binding | `javac -h`, exported JNI name, hoặc `RegisterNatives` | `SymbolLookup` + symbol C ABI + `FunctionDescriptor` |
| Cleanup | `DeleteLocalRef`/`DeleteGlobalRef`, Release array/string, native destroy | `Arena.close` cho scope mình sở hữu; native API vẫn cần explicit free/close nếu memory được cấp ở C |
| Safety | C có thể crash JVM nếu vi phạm pointer/prototype | MemorySegment kiểm tra Java-side bounds/lifetime; native ABI/callback sai vẫn crash hoặc corrupt |

### 8.1. FFM không tự giải phóng tài nguyên C chỉ vì có Arena

Nếu native library trả một pointer từ `malloc` và yêu cầu gọi `free_buffer`, **Arena không biết ownership bên trong thư viện** trừ khi bạn gắn chính sách cleanup phù hợp. Phải định nghĩa rõ:

- Ai cấp phát vùng nhớ? Java `Arena.allocate` hay C `malloc`?
- Ai giải phóng? `Arena.close`, `free_buffer(ptr)` hay một native destroy API khác?
- Pointer có được giữ lại sau khi downcall return không?
- Callback được native giữ bao lâu? Có function `unregister_callback`/`stop` chạy **trước** khi đóng arena không?
- Những hàm nào cho phép null, dữ liệu rỗng, length lớn, error code đặc biệt?

Không gọi `free` hai lần, không đóng arena khi C vẫn dùng pointer, không đọc `MemorySegment` sau close. FFM giảm glue code nhưng không xóa bỏ thỏa thuận ownership của C ABI.

### 8.2. JNI không được coi mọi handle là C pointer thường

`jobject` có thể là indirect handle do JVM quản lý, không phải địa chỉ ổn định của Java object. Một C function nhận `void *` không có quyền sử dụng `jobject` như raw struct; Java GC có thể di chuyển object, reference có scope riêng. Nếu cần cho C library xử lý dữ liệu, copy sang buffer native hoặc dùng JNI accessors với lifetime đúng, chứ không ép tùy tiện `jobject` qua `MemorySegment`.

`jmethodID` không giống `jobject`; lưu cache ID phải xét vòng đời defining class, không giữ nguyên qua classloader reload. Nếu native lib cần thao tác Java ClassLoader, exception và array/object thật sự, giữ JNI cho lớp tích hợp này là lựa chọn đúng kỹ thuật.

### 8.3. Callback từ native là nơi cần thiết kế thận trọng

JNI callback:

- Lưu `JavaVM *` nếu cần, attach/detach đúng thread; **không cache `JNIEnv *` của thread khác**.
- Nếu lưu Java object qua nhiều lời gọi, dùng `NewGlobalRef`/`DeleteGlobalRef` theo lifecycle, không giữ local ref.
- `Call<Type>Method` có thể khiến Java ném exception; native cần dừng/clear/propagate có chủ đích.

FFM callback:

- `Linker.upcallStub` gắn một `MethodHandle` với địa chỉ function pointer C ABI và arena scope.
- Stub phải còn sống **toàn bộ thời gian** C có thể gọi; nếu C lưu callback, phải unregister/stop và chờ in-flight calls xong trước arena close.
- Callback được gọi trên thread do native quyết định; thread confinement, thread attach và exception handling có thể cần xem xét theo runtime và contract của native API.
- **Không cho Java exception thoát bừa qua C ABI**; chuyển lỗi sang error code/result hoặc xử lý ở tầng callback trước khi quay về C.

Trong demo, `call_unary` gọi ngay trong cùng thread và không giữ pointer. Với hàm C đăng ký event handler bất đồng bộ, đừng sao chép ví dụ rồi đóng `Arena.ofConfined()` ngay sau khi gọi `register_callback`: đó là dangling callback.

## 9. Ra quyết định bằng hai câu hỏi theo thứ tự

**Câu hỏi 1: Java baseline thực tế là gì?**

- **Bắt buộc chạy Java 17**: không dùng mã final FFM 22. Nếu cần bridge trong Java SE hiện tại, JNI là hướng ổn định; nếu chấp nhận thư viện bên thứ ba, đánh giá thêm JNA/JNR theo maintenance, overhead, native-access requirements và policy dự án.
- **Bắt buộc chạy Java 21 LTS và không chấp nhận preview**: dùng JNI cho production bridge hoặc chờ nâng baseline; không xem `java.lang.foreign` preview trong Java 21 là final API.
- **Baseline Java 22+**: FFM chuẩn có thể sử dụng; tiếp tục hỏi C API có đủ độc lập JVM không.
- **Nhiều baseline cùng lúc**: giữ lớp interface Java ổn định, đóng gói implementation riêng (JNI cho cũ, FFM cho mới) bằng dependency/version selection; tránh bắt JVM cũ load class chứa references API chỉ tồn tại ở JDK mới.

**Câu hỏi 2: Native code cần quyền gì đối với JVM?**

- **Chỉ C ABI/foreign memory/function pointer callback**: thường bắt đầu bằng FFM nếu JDK cho phép.
- **Cần đọc/ghi field, gọi Java method, tạo Java objects, truyền Java arrays như Java objects, quản lý ClassLoader hoặc exceptions**: chọn JNI cho phần này.
- **Cần cả hai**: tách lõi C độc lập JVM; dùng JNI wrapper nhỏ nơi bắt buộc, FFM wrapper cho API ABI thuần.
- **Nhúng JVM từ ứng dụng C/C++**: xét JNI Invocation API (FFM từ Java không khởi tạo JVM cho host).
- **Native SDK chỉ có C++ ABI phức tạp**: thường tạo một **C ABI wrapper** (extern "C", opaque handles, exported functions) trước; C++ name mangling, exceptions và ABI compiler không tự biến thành FFM/JNI-friendly.

## 10. Bảng tình huống và đề xuất

| Tình huống | Quyết định ưu tiên | Vì sao |
| --- | --- | --- |
| Java 17 service gọi thư viện C để tính toán | **JNI** hoặc binding library tương thích 17 | Không dùng FFM final API khi runtime là 17 |
| Java 21 LTS, chính sách cấm preview, native SDK C ABI | **JNI hiện tại**, kế hoạch FFM khi nâng JDK | FFM 21 vẫn preview |
| Java 22+ gọi C SDK có primitive, pointer và struct | **FFM** | Có downcall, MemoryLayout, Arena, SymbolLookup chuẩn |
| Java 22+ cần callback `int (*)(int)`, không lưu lâu | **FFM upcallStub** | Callback là C function pointer với contract ABI rõ |
| C cần giữ `jobject` và gọi Java instance methods | **JNI** | Chỉ JNI cung cấp object model và `JNIEnv` |
| Native thread phải gọi Java method theo class loader cụ thể | **JNI** cho phần truy cập JVM | Cần JavaVM/attach, refs, lookup, exceptions |
| Kế thừa legacy JNI library đang hoạt động tốt | **Không bắt buộc rewrite** | Migration có cost/risk; chỉ đổi khi có lợi ích đo được |
| Native engine dùng chung Java, Python, Node | **C ABI ổn định + FFM wrapper** (Java 22+) | Tránh buộc engine phụ thuộc Java |
| Java 22+ gọi C++ SDK thiếu C ABI | **C ABI adapter trước**, sau đó FFM hoặc JNI | FFM không tự hiểu vtable/C++ ABI không ổn định |
| Embedded JVM do host C khởi động | **JNI Invocation API** | Cần `JNI_CreateJavaVM` và quản lý VM từ native |
| Module plugin cần unload/reload thường xuyên | **Thiết kế lifetime trước**, rồi chọn JNI/FFM cho từng bridge | Global jclass refs, Arena và callbacks đều có thể pin hoặc gây use-after-free |
| Ứng dụng không được phép bật native access | **Không dùng JNI/FFM restricted operations** cho phần đó | Quyền runtime/policy quan trọng hơn cách viết binding |

Điều cần nhớ: **JNI không phải công nghệ “cũ nên luôn phải bỏ”; FFM không phải công nghệ “mới nên tự động nhanh hơn”.** Quyết định đúng xuất phát từ baseline JDK, ABI, object-dependency, ownership và quyền native access.

## 11. Migration từ JNI sang FFM: không đổi API chỉ bằng search/replace

Một migration có kiểm soát nên làm theo các bước:

1. **Inventory hiện tại:** liệt kê native declarations, generated headers, function calls, `JNIEnv` operations, global refs, arrays/Strings, exception mapping, callbacks, và native threads.
2. **Tách phân loại:** đánh dấu hàm thực sự xử lý **C ABI thuần**, hàm phụ thuộc JVM objects, hàm hybrid. Chỉ những hàm thuần mới là candidate FFM downcall trực tiếp.
3. **Ổn định C contract:** API export function names rõ ràng, cố định kiểu `int32_t`/`int64_t` hoặc ABI mappings, có tài liệu ownership, nullability, error status, alignment, struct packing và callback lifetime.
4. **Tăng baseline Java nếu cần:** JDK 17/21 không chạy code final 22; không giả định deploy service đã được nâng chỉ vì local dev chạy 22+.
5. **Tạo FFM wrapper:** `SymbolLookup`, `FunctionDescriptor`, `MemoryLayout`, `Arena`; cân nhắc dùng **jextract** (công cụ sinh binding từ C headers, không phải tùy chọn built-in của `javac`) cho native header phức tạp.
6. **Giữ JNI nơi cần:** Java object callbacks, ClassLoader, Java exceptions, native methods làm việc trên `jobject`; không cast chúng thành raw C pointers.
7. **Thiết kế lỗi:** chuyển C error code, errno hoặc error object sang Java exceptions tại Java wrapper; ở JNI giữ pending exception semantics. Không cho C++ exception vượt C ABI.
8. **Quản lý lifetime:** đóng arena đúng thời điểm, giải phóng C allocations bằng API native, unregister callback và dừng worker threads, xóa JNI refs theo owner.
9. **Kiểm tra native access policy:** classpath/unnamed modules hoặc module names; trên JDK 24+ thử `--illegal-native-access=deny` để phát hiện code chưa được cấp quyền.
10. **So sánh kết quả và hiệu năng:** test parity, binary compatibility, OS/architecture matrix, cold start, throughput/latency, allocation/GC. Dùng JMH/benchmark có warmup, batching phù hợp; không suy kết luận từ một microbenchmark duy nhất.

### 11.1. Kế hoạch tách legacy JNI wrapper

Nếu hiện tại:

~~~text
Java -> nativeCompute(jintArray) -> C algorithm
~~~

thì việc tách có thể theo hai pha:

~~~text
PHA 1 (không đổi Java API):
Java 17 -> JNI wrapper -> C ABI core

PHA 2 (sau khi baseline >=22):
Java 22+ -> FFM downcall -> cùng C ABI core
                    |
             JNI wrapper vẫn tồn tại cho JVM-object-dependent calls
~~~

Như vậy không cần xóa JNI trên toàn hệ thống. Bảo đảm **chỉ một owner** cho native context nếu hai bridge có thể đồng thời truy cập nó; mỗi wrapper phải respect cùng locking và free protocol. Nếu API cần trả Java object, thay đổi lên FFM không tự cung cấp phép màu biểu diễn object; cần trả data dạng bytes/struct/handle và thực hiện mapping ở Java hoặc giữ JNI.

## 12. Lỗi thường gặp khi chọn công nghệ

**Lỗi 1 — “Java 17 có FFM nên code `java.lang.foreign` JDK 22 chạy được”.** Sai: Java 17 có incubator API khác, không phải bản final `java.lang.foreign`.

**Lỗi 2 — “Java 21 LTS nghĩa là FFM đã final”.** Sai: FFM của Java 21 là third preview. Chính sách sản phẩm có thể không chấp nhận preview code.

**Lỗi 3 — “FFM upcall thay thế toàn bộ JNI calls”.** Upcall stub là C function pointer tới Java MethodHandle, **không** cho C tự thao tác `jobject`, Java fields, class loader hay pending Java exception qua `JNIEnv`.

**Lỗi 4 — “JNI luôn chậm hơn FFM” hoặc ngược lại.** Overhead phụ thuộc cách copy dữ liệu, số lượng calls, pin/copy, JIT, critical calls, struct marshalling, callback và workload. Benchmark đúng điều kiện deployment trước khi quyết định.

**Lỗi 5 — “Arena.close() tự gọi C free cho mọi pointer”.** Chỉ memory do arena sở hữu hoặc cleanup được cấu hình tương ứng mới có lifecycle đó. Malloc từ C SDK cần matching free/destroy.

**Lỗi 6 — “`MemorySegment` làm C an toàn như Java”.** FFM kiểm tra truy cập Java-side trong scope/bounds của segment, nhưng function C vẫn có thể đọc sai số phần tử, theo pointer rác hoặc ghi ngoài buffer.

**Lỗi 7 — “Native access warnings là compile errors”.** Từ JDK 24, warnings khi JNI/FFM restricted operations có thể xuất hiện ở runtime; policy có thể chuyển thành deny. Fix bằng cấu hình module phù hợp và hiểu quyền của deployer, không bằng cách đổi JNI function name.

**Lỗi 8 — “C `long` và Java `long` đều 64 bit trên mọi OS”.** Sai, C `long` thường 32-bit trên Windows x64 nhưng 64-bit trên Linux x64. Dùng fixed-width types hoặc canonical layouts và kiểm tra ABI.

**Lỗi 9 — “C++ method export có tên tương tự Java method nên FFM tìm được”.** C++ name mangling/ABI không ổn định giữa toolchains. Tạo C ABI wrapper có `extern "C"` và export chính xác trước khi dùng FFM.

**Lỗi 10 — “Có thể đóng arena ngay sau khi đăng ký callback bất đồng bộ”.** Sai: C có thể giữ function pointer và gọi sau khi stub invalidated; phải unregister, stop, wait-in-flight rồi mới close.

**Lỗi 11 — “Dùng cùng một native pointer ở cả FFM và JNI rồi bên nào close trước cũng được”.** Không: ownership/synchronization phải thống nhất, nếu không dễ double-free/use-after-free.

**Lỗi 12 — “Mọi Java array có thể đưa thẳng sang C pointer”.** Java heap thuộc JVM/GC; JNI có borrowed accessors, FFM thường dùng off-heap buffer/marshalling. Không tùy ý biến `int[]` thành address của C buffer.

## 13. Câu hỏi tự kiểm tra

1. Một service buộc chạy **JDK 17** dùng C SDK chỉ nhận `int*` và trả `double`. Vì sao mã FFM final của JDK 22 không compile trên service đó? Nếu chưa đổi Java baseline, chọn cách nào?
2. Một app **JDK 21** có cho phép preview nhưng đội vận hành không muốn `--enable-preview` ở production. Có nên viết binding FFM 21 production không?
3. Native C có `void notify(JNIEnv*, jobject)`, cần gọi Java method trên object. FFM `upcallStub` có thể trực tiếp thực hiện công việc của `JNIEnv` không?
4. Một C library có `int square(int)` và callback `int (*)(int)` trên **JDK 22**. Khi nào FFM phù hợp, và khi nào cần giữ callback stub/arena lâu hơn?
5. Native function trả buffer cấp bằng `malloc`. Chỉ `Arena.ofConfined().close()` có đủ giải phóng buffer đó không nếu buffer không do arena cấp?
6. Bạn thấy warning từ `System.loadLibrary` trên JDK 24. Đây là `UnsatisfiedLinkError` hay native access policy? Bạn cần flag gì cho code ở unnamed module?
7. Một legacy JNI library có hàng trăm `GetFieldID`/`CallObjectMethod` calls nhưng chỉ vài phép tính C. Nên rewrite toàn bộ sang FFM hay tách C ABI core và giữ JNI cho JVM objects?
8. Trên Windows x64, C header dùng `long`. Bạn có thể luôn dùng `ValueLayout.JAVA_LONG` cho nó không?
9. Một FFM upcall callback được C giữ để gọi sau một phút, nhưng arena đóng sau khi đăng ký. Lỗi lifetime nào xảy ra?
10. Hai binding cùng sở hữu một native handle. Thiết kế nào ngăn chúng double-free?

### Gợi ý đáp án ngắn

1. API incubator Java 17 khác final FFM 22; giữ JNI/binding library tương thích 17 hoặc nâng JDK.
2. Không: preview chưa đáp ứng policy; dùng JNI hoặc đợi nâng baseline.
3. Không: FFM upcall chỉ trình bày function pointer theo C ABI; JNI cần cho object model.
4. FFM hợp khi ABI thuần; stub sống ít nhất đến callback cuối cùng; unregister trước close.
5. Không: phải gọi API free/destroy tương ứng hoặc gắn cleanup hợp lệ.
6. Native access policy nếu thư viện load được nhưng cảnh báo; dùng `--enable-native-access=ALL-UNNAMED` (hoặc tên module).
7. Tách C ABI core, giữ JNI cho tác vụ phụ thuộc JVM, đánh giá FFM ở JDK 22+.
8. Không; kiểm tra canonical ABI layout, nhất là Windows LLP64 vs Linux LP64.
9. C có thể gọi function pointer đã hết hiệu lực; use-after-scope/crash.
10. Một owner, protocol close/reference counting, synchronization và chống double-free.

## 14. Checklist ra quyết định cuối cùng

- **JDK:** Production minimum là 17, 21 hay 22+? Có cho phép incubator/preview không? Build và runtime có dùng cùng API release không?
- **JVM objects:** Native có cần truy cập trực tiếp `jobject/jclass/jarray`, Java fields, methods, exceptions, class loader hoặc Invocation API không?
- **C ABI:** Có headers/exported symbols độc lập JVM? Signature/memory layout, alignment, `size_t/long`, C++ name mangling đã hiểu chưa?
- **Lifetime:** MemorySegment/Arena, JNI refs, native pointer, async callbacks, worker threads và close/unregister có owner rõ ràng chưa?
- **Errors:** Java exceptions và native error codes/errno được chuyển đổi đúng, không để C++ exceptions xuyên biên hoặc pending JNI exception bị bỏ qua?
- **Native access:** Có bật quyền ở đúng named/unnamed module và kiểm tra warning/deny trên JDK triển khai không?
- **Portability:** Có shared library đúng OS/CPU/ABI và test cùng Java runtime thực tế không?
- **Performance:** Đã đo batching, copy-vs-view, callback overhead, memory allocation và GC thay vì đoán?
- **Migration:** Nếu đang dùng JNI, phần nào thật sự có thể tách thành C ABI để FFM gọi? Có cần hỗ trợ nhiều Java versions không?
- **Testing:** Có test giá trị đúng, null/empty, overflow, errors, ownership, wrong-thread, out-of-scope và callback shutdown không?

**Kết luận:** Chọn theo **hai trục ưu tiên**: (1) phiên bản JDK có cung cấp FFM **ổn định** hay chưa, và (2) native code có phải thao tác **JVM object model** hay chỉ cần **C ABI/foreign memory**. Với Java 22+ và C API thuần, FFM thường là điểm bắt đầu hợp lý; với JDK 17/21 không muốn preview, hoặc native cần `JNIEnv/jobject`, JNI vẫn là công cụ phù hợp. Một hệ thống có thể dùng cả hai mà không mâu thuẫn, miễn ABI, native access và ownership được xác định rõ ràng.

### Tài liệu chính thức

- Oracle, [JDK 17 `jdk.incubator.foreign`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.incubator.foreign/module-summary.html): incubator, khác API final.
- Oracle, [JDK 21 Preview List](https://docs.oracle.com/en/java/javase/21/docs/api/preview-list.html): `java.lang.foreign` vẫn là FFM third preview (JEP 442).
- Oracle, [JDK 22 Foreign Function & Memory API](https://docs.oracle.com/en/java/javase/22/core/foreign-function-and-memory-api.html): FFM final, downcall, upcall, Arena và native memory.
- Oracle, [JDK 22 `Linker`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): FunctionDescriptor, ABI, downcall/upcall.
- Oracle, [JDK 22 `SymbolLookup`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): native symbol lookup, library lifetime.
- Oracle, [JDK 22 `Arena`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): allocation, scope, thread confinement.
- Oracle, [JDK 17 JNI Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): object model, native methods, references, Invocation API.
- OpenJDK, [JEP 454](https://openjdk.org/jeps/454): chuẩn hóa FFM ở JDK 22.
- OpenJDK, [JEP 472](https://openjdk.org/jeps/472): native access restrictions và cảnh báo JNI/FFM từ JDK 24.