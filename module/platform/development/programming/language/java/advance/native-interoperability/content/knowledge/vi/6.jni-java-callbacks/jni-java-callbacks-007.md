# Lưu bộ nhớ đệm JNI method/field ID theo vòng đời của lớp tương ứng

Khi mã C/C++ gọi lại phương thức Java hoặc truy cập trường Java qua JNI, nó thường phải lấy `jmethodID` bằng `GetMethodID`/`GetStaticMethodID` và `jfieldID` bằng `GetFieldID`/`GetStaticFieldID`. Tra cứu lặp lại tên và chữ ký trên mọi lần gọi có thể tạo chi phí không cần thiết. **Cache các ID giúp tái sử dụng kết quả tra cứu, nhưng một ID chỉ hợp lệ khi lớp định nghĩa thành viên đó vẫn còn được JVM nạp.** Class unloading, nhiều `ClassLoader` và quản lý `jclass` là những vấn đề phải giải quyết cùng lúc.

Bài này tập trung vào cách gắn cache với **đúng danh tính lớp và đúng vòng đời** khi Java gọi JNI rồi JNI gọi lại Java. Sau khi học, bạn phải phân biệt được ID với object reference, chọn cách giữ lớp sống hoặc tái tạo ID, thiết kế khởi tạo/dọn dẹp an toàn, và tự chạy một ví dụ Java 17 + C11 có cache `jmethodID`, `jfieldID` và tham chiếu lớp.

## 1. Tại sao cần cache và cache cái gì?

Trình tự gọi một instance method Java từ JNI thông thường:

~~~c
jclass cls = (*env)->GetObjectClass(env, object);
if (cls == NULL) return;  /* lỗi hoặc exception */

jmethodID mid = (*env)->GetMethodID(env, cls, "run", "()V");
if (mid == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;                 /* JNI có thể đang có pending exception */
}

(*env)->CallVoidMethod(env, object, mid);
(*env)->DeleteLocalRef(env, cls);
~~~

Đây chỉ là **mảnh minh họa**: giả định `object` không null, `env` là môi trường của thread hiện tại, caller kiểm tra exception sau khi gọi và method thật sự là instance `void run()`. Nếu lặp nhiều lần cho cùng lớp, `GetMethodID` với chuỗi `"run"` và `"()V"` có thể tránh được bằng cách lưu `mid`.

Một cache đúng còn phải trả lời: ID lấy từ **Class object cụ thể nào**, Class object đó còn sống không, các thread có dùng cache đồng thời không, và ai chịu trách nhiệm hủy dữ liệu cache. Các ID không tự mang ownership của lớp.

| Thực thể JNI | Vai trò | Có phải JNI object reference? | Thời hạn/cleanup |
| --- | --- | --- | --- |
| `jmethodID` | Định danh method theo tên + descriptor, dùng với `Call<Type>Method`/`CallStatic<Type>Method`... | **Không** | Hợp lệ khi lớp định nghĩa method chưa bị unload; không gọi `DeleteGlobalRef` với ID |
| `jfieldID` | Định danh field dùng với `Get<Type>Field`/`Set<Type>Field`... | **Không** | Tương tự method ID; không có hàm `DeleteFieldID` |
| `jclass` | JNI reference tới đối tượng `java.lang.Class` | **Có** | Local ref chỉ dùng trong phạm vi JNI call/thread; global ref cần `DeleteGlobalRef`; weak global cần `DeleteWeakGlobalRef` |
| `jobject` | JNI reference tới object Java | **Có** | Local/global/weak theo loại ref, không phải native pointer vào layout object |
| `JNIEnv *` | Giao diện JNI của thread đang gọi | Không phải ID hay reference được cache | Chỉ dùng với thread tương ứng, không giữ dùng xuyên thread |
| `JavaVM *` | Handle cấp JVM | Không phải ID Java member | Có thể lưu theo hợp đồng JVM, dùng để attach lấy `JNIEnv *` ở thread phù hợp |

**Quy tắc quan trọng:** `jmethodID`/`jfieldID` không giữ class sống; `NewGlobalRef` trên `jclass` thì có thể giữ `Class<?>` và class loader liên quan sống. Một ID được lấy ở quá khứ vẫn có thể là giá trị khác `NULL` nhưng **không còn hợp lệ** sau khi class unload.

## 2. Class identity: cùng tên chưa chắc cùng lớp

Trong Java, danh tính lớp chịu ảnh hưởng của cả **binary name và defining class loader**. Hai loader độc lập có thể định nghĩa hai lớp cùng tên `com.example.Plugin` nhưng tạo hai `Class<?>` khác nhau, với field/method IDs khác nhau. Một cache dùng khóa chỉ là chuỗi `"com/example/Plugin"` không đủ an toàn.

~~~text
ClassLoader A --> com.example.Plugin (Class A)
                       | GetMethodID("execute", "()I")
                       v
                   methodID A

ClassLoader B --> com.example.Plugin (Class B)
                       | GetMethodID("execute", "()I")
                       v
                   methodID B

Tên lớp giống nhau ≠ cùng Class object / cùng class lifecycle
~~~

Một class được unload khi JVM xác định điều kiện unloading thỏa mãn. Thời điểm này phụ thuộc vào reachability, GC, loader và VM; **không được giả định** class đã unload ngay khi xóa một biến Java, hoặc luôn sống tới khi process kết thúc.

Nếu một plugin được unload rồi load lại, đối tượng `Class<?>` mới có thể mang tên giống cũ nhưng là **định nghĩa khác**. Tuyệt đối không tái sử dụng `jmethodID`/`jfieldID` của class đã unload cho class được load lại. JNI specification nêu rõ ID mất hiệu lực sau khi defining class bị unload.

Để tránh nhầm giữa hai JNI references cùng trỏ một class, dùng `IsSameObject(env, classA, classB)` khi cần so sánh identity; đừng so sánh raw C handle bằng `==` rồi tự suy ra chúng khác lớp vì các JNI handle có thể khác nhau dù cùng referent.

### 2.1. Method và field còn cần chữ ký chính xác

`GetMethodID(env, clazz, "read", "()I")` tìm **instance** method `int read()`; `GetStaticMethodID` tìm **static** method. `GetFieldID(env, clazz, "count", "I")` tìm instance field `int count`; `GetStaticFieldID` tìm static field.

| Java declaration | JNI descriptor |
| --- | --- |
| `int count` | `I` |
| `long id` | `J` |
| `String name` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `void tick()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String describe(long id)` | `(J)Ljava/lang/String;` |

Signature gồm cả kiểu tham số và **kiểu trả về**, dùng dạng internal name có `/`, không phải dấu `.`. `GetMethodID` không tìm một static method và `GetStaticMethodID` không phải phiên bản “nhanh hơn” của instance lookup. Khi lookup thất bại, JNI thường trả `NULL` và có thể phát sinh `NoSuchMethodError` hoặc `NoSuchFieldError`; không cache ID `NULL` như thể đã khởi tạo thành công.

Các hàm `GetMethodID`/`GetFieldID` có thể khởi tạo lớp chưa được initialize, từ đó chạy `<clinit>` và phát sinh lỗi khởi tạo. Vì vậy phải thiết kế điểm tạo cache để tránh vòng lặp khởi tạo lớp hoặc gọi vào trạng thái chưa sẵn sàng.

## 3. Ba chiến lược quản lý lifetime

### 3.1. Chiến lược A: cache với strong global `jclass` và giải phóng tường minh

Giữ một cấu trúc gồm strong global reference tới `Class<?>` cùng các ID:

~~~c
typedef struct {
    jclass class_ref;      /* global reference */
    jfieldID value_field;  /* ID, không phải jobject */
    jmethodID method;      /* ID, không phải jobject */
} ClassCache;
~~~

Khi tạo, lấy class được caller cung cấp, resolve các ID, sau đó tạo `NewGlobalRef(env, clazz)` và lưu vào cache. Miễn global reference còn sống, class được giữ reachable, nên IDs không mất hiệu lực vì class unloading. Khi không còn client nào sử dụng: chặn mọi lời gọi đang dùng cache, gọi `DeleteGlobalRef` **đúng một lần**, rồi `free` cấu trúc C. Sau đó tuyệt đối không dùng IDs hay pointer cache.

Ưu điểm: đơn giản và phù hợp native handle có vòng đời rõ ràng. Nhược điểm: giữ class/loader sống dài hơn mong muốn nếu quên close; đặc biệt nguy hiểm trong server có hot deployment hoặc plugin loader. Do đó lifecycle phải **có người sở hữu** (thí dụ `AutoCloseable` và `try-with-resources`) thay vì dựa vào GC.

Một lỗi thiết kế thường gặp: lưu global `jclass` trong static variable C rồi chỉ dự định xóa trong `JNI_OnUnload`. Strong global ref có thể ngăn class loader trở nên collectible, khiến `JNI_OnUnload` không xảy ra như dự tính. Nếu muốn class/loader unload, cần một cơ chế release độc lập, tường minh, trước khi điều kiện unload được thỏa mãn.

### 3.2. Chiến lược B: weak global `jclass` và tái tra cứu khi class không còn sống

`NewWeakGlobalRef` tạo weak global reference không giữ object/class sống. Trước mỗi lần dùng IDs thuộc class đó, cố gắng **nâng** weak ref thành một strong local bằng `NewLocalRef`:

~~~c
/* Mảnh minh họa: cache->weak_class là jweak đã tạo từ Class<?> đúng. */
jclass temporary = (jclass)(*env)->NewLocalRef(
    env, (jobject) cache->weak_class);

if (temporary == NULL) {
    /* Class có thể đã bị GC, hoặc thiếu bộ nhớ:
       kiểm tra pending exception, bỏ IDs cũ và tra cứu lại khi
       có Class<?> mới hợp lệ; không tiếp tục gọi với IDs cũ. */
} else {
    /* Trong khi temporary sống, lớp được giữ sống cho lời gọi này.
       Chỉ dùng IDs được lookup từ chính class identity này.
       Khóa cache/đồng bộ nếu có thao tác invalidation song song. */
    (*env)->DeleteLocalRef(env, temporary);
}
~~~

Đoạn này **không chạy độc lập** và mô tả giao thức lifetime, không phải implementation cache hoàn chỉnh. Cần thêm đồng bộ, cách lấy lại class, kiểm tra lỗi và `DeleteWeakGlobalRef` lúc hủy registry. Điều mấu chốt là **không chỉ gọi `IsSameObject(weakRef, NULL)` rồi mới dùng trực tiếp weak ref**, vì GC có thể thu hồi referent **giữa lúc kiểm tra và sử dụng**. `NewLocalRef` tạo strong reference trong khoảng sử dụng khi thành công.

Weak cache thích hợp nơi unloading là yêu cầu thực tế; đổi lại code phức tạp hơn và phải phân biệt “lớp không còn sống” với “không cấp phát được local ref”. Không được chuyển một ID từ class cũ sang class mới chỉ vì tên/descriptor giống nhau.

### 3.3. Chiến lược C: khởi tạo lại IDs theo `<clinit>` của mỗi lớp

Một mẫu quen thuộc là phương thức `nativeInit` được gọi trong initializer của Java class:

~~~java
final class NativeReady {
    static {
        System.loadLibrary("native_ready");
        nativeInit();
    }

    private static native void nativeInit();
}
~~~

Đây là **mảnh minh họa**, chưa thể chạy khi không có thư viện `native_ready`. `<clinit>` chạy cho mỗi class definition sau khi được nạp; nếu class unload rồi được định nghĩa lại, initializer của class mới sẽ chạy lại. Mẫu này có thể gắn thời điểm tra cứu ID với initialization của **lớp gọi**.

Tuy nhiên **đặt mọi ID trong đúng một biến static C toàn cục** không tự tạo cache riêng theo từng class identity. Phải chứng minh thư viện và class chỉ có một vòng đời tương ứng hoặc tạo registry khóa theo Class object / loader identity, tránh overwrite và truy cập concurrent. Nếu cần giữ `jclass` sau lời gọi initializer, vẫn phải quản lý local/global/weak references đúng quy tắc.

## 4. Ví dụ đầy đủ: Java 17 + JNI, cache theo vòng đời một native handle

Ta xây dựng `IdCache`. Mỗi instance Java tạo **một** native cache dành cho `Class<?>` được truyền vào, lưu một `jfieldID` cho instance field `value` và một `jmethodID` cho instance method `twice()`. JNI dùng ID đã cache để lấy field và gọi lại Java method. `IdCache.close()` giải phóng đúng global reference và native allocation.

Đây là mẫu có thể xây dựng và chạy trên Linux/macOS/Windows với compiler phù hợp, giả định target platform cung cấp `intptr_t` và native pointer có thể biểu diễn trong `jlong` (đúng với các môi trường JDK 17 thông dụng 32/64 bit). Với kiến trúc exotic hoặc API cần chống giả mạo handle, dùng bảng opaque handle có kiểm soát thay cho ép pointer thành số.

Cấu trúc thư mục:

~~~text
id-cache-demo/
├── src/
│   └── demo/
│       └── IdCache.java
├── native/
│   └── idcache.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 4.1. Java: sở hữu cache bằng `AutoCloseable`

Tạo nguyên tệp `src/demo/IdCache.java`:

~~~java
package demo;

import java.util.Objects;

public final class IdCache implements AutoCloseable {
    static {
        System.loadLibrary("idcache");
    }

    // 0 nghĩa là chưa tạo hoặc đã đóng.
    private long nativeHandle;

    public IdCache(Class<?> targetClass) {
        Objects.requireNonNull(targetClass, "targetClass");
        long opened = nativeOpen(targetClass);
        if (opened == 0L) {
            throw new IllegalStateException("native cache creation failed");
        }
        nativeHandle = opened;
    }

    public synchronized long calculate(Object object) {
        if (nativeHandle == 0L) {
            throw new IllegalStateException("cache is closed");
        }
        Objects.requireNonNull(object, "object");
        return nativeCalculate(nativeHandle, object);
    }

    @Override
    public synchronized void close() {
        long opened = nativeHandle;
        if (opened != 0L) {
            nativeHandle = 0L;
            nativeClose(opened);
        }
    }

    private static native long nativeOpen(Class<?> targetClass);
    private static native long nativeCalculate(long handle, Object object);
    private static native void nativeClose(long handle);

    public static final class Sample {
        private final int value;

        public Sample(int value) {
            this.value = value;
        }

        private int twice() {
            return Math.multiplyExact(value, 2);
        }
    }

    public static void main(String[] args) {
        IdCache cache = new IdCache(Sample.class);
        try (cache) {
            System.out.println(cache.calculate(new Sample(7)));
            System.out.println(cache.calculate(new Sample(11)));
        }

        cache.close(); // đóng lần nữa an toàn
        try {
            cache.calculate(new Sample(1));
        } catch (IllegalStateException expected) {
            System.out.println("closed");
        }
    }
}
~~~

**Ý nghĩa vòng đời:** constructor nhận **Class object thực** (không tự tìm bằng chuỗi tên), gọi `nativeOpen` và lưu handle; `calculate` và `close` là synchronized trên cùng instance nên không thể đồng thời sử dụng và hủy cùng một handle thông qua API public này. `close` đặt handle thành 0, gọi cleanup một lần; lời gọi sau close ném `IllegalStateException` trước khi đi JNI. Dùng `try (cache)` là cú pháp Java 9+, hợp lệ trong Java 17.

`Sample` là `static final` nested class. JNI có thể đọc field `private int value` và lấy ID của `private int twice()` (JNI không thực hiện cùng Java source access checks). Class là `final`, tránh làm bài đầu phức tạp bởi virtual override. Java `Math.multiplyExact` ném `ArithmeticException` nếu nhân vượt miền `int`; JNI phải tôn trọng pending exception đó.

**Sản xuất thực tế:** việc ép native pointer thành `long` chỉ là cơ chế handle nhỏ gọn cho ví dụ. Code native phải luôn kiểm soát nguồn handle, không cho caller tùy ý truyền integer giả, và phải có mô hình synchronization/ownership trên mọi đường gọi JNI. API Java public ở đây dùng synchronized để bảo đảm close và calculate tuần tự **cho một instance**; nếu phát triển API native công khai cho nhiều thread/native callback, cần thêm trạng thái reference-count hoặc lock ở native side.

### 4.2. C: lưu global class ref và hai ID đã resolve

Trước tiên sinh header từ Java (lệnh build đầy đủ ở mục 5). Header `build/include/demo_IdCache.h` chứa tên JNI do compiler xác nhận. Tạo nguyên tệp `native/idcache.c`:

~~~c
#include "demo_IdCache.h"
#include <stdint.h>
#include <stdlib.h>

_Static_assert(sizeof(void *) <= sizeof(jlong),
               "This demo needs native pointers to fit in jlong");

typedef struct {
    jclass class_ref;         /* Strong JNI global reference */
    jfieldID value_field;     /* Không phải jobject */
    jmethodID twice_method;   /* Không phải jobject */
} IdEntry;

static void throw_java(JNIEnv *env, const char *name,
                       const char *message) {
    jclass exception_type = (*env)->FindClass(env, name);
    if (exception_type != NULL) {
        (*env)->ThrowNew(env, exception_type, message);
        (*env)->DeleteLocalRef(env, exception_type);
    }
}

JNIEXPORT jlong JNICALL
Java_demo_IdCache_nativeOpen(JNIEnv *env, jclass owner,
                             jclass target_class) {
    (void) owner;

    if (target_class == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "targetClass");
        return 0;
    }

    /* 1. Resolve ID từ đúng Class object. */
    jfieldID value_field =
        (*env)->GetFieldID(env, target_class, "value", "I");
    if (value_field == NULL) {
        return 0; /* Thường đã có pending NoSuchFieldError */
    }

    jmethodID twice_method =
        (*env)->GetMethodID(env, target_class, "twice", "()I");
    if (twice_method == NULL) {
        return 0; /* Thường đã có pending NoSuchMethodError */
    }

    /* 2. Class sống ít nhất đến khi cache bị đóng. */
    jclass keep_class =
        (jclass)(*env)->NewGlobalRef(env, target_class);
    if (keep_class == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "NewGlobalRef failed");
        }
        return 0;
    }

    /* 3. Chỉ publish cache khi mọi thành phần đã hợp lệ. */
    IdEntry *entry = malloc(sizeof *entry);
    if (entry == NULL) {
        (*env)->DeleteGlobalRef(env, keep_class);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native cache allocation failed");
        return 0;
    }

    entry->class_ref = keep_class;
    entry->value_field = value_field;
    entry->twice_method = twice_method;
    return (jlong)(intptr_t)entry;
}

JNIEXPORT jlong JNICALL
Java_demo_IdCache_nativeCalculate(JNIEnv *env, jclass owner,
                                  jlong handle, jobject object) {
    (void) owner;

    if (handle == 0) {
        throw_java(env, "java/lang/IllegalStateException",
                   "cache is closed");
        return 0;
    }
    if (object == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "object");
        return 0;
    }

    IdEntry *entry = (IdEntry *)(intptr_t)handle;
    if ((*env)->IsInstanceOf(env, object, entry->class_ref)
            != JNI_TRUE) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "object has an incompatible class");
        return 0;
    }

    /* ID lấy một lần trong nativeOpen, dùng lại ở đây. */
    jint value =
        (*env)->GetIntField(env, object, entry->value_field);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }

    jint doubled =
        (*env)->CallIntMethod(env, object, entry->twice_method);
    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Giữ Java exception đang pending. */
    }

    return (jlong)value + (jlong)doubled;
}

JNIEXPORT void JNICALL
Java_demo_IdCache_nativeClose(JNIEnv *env, jclass owner,
                              jlong handle) {
    (void) owner;
    if (handle == 0) {
        return;
    }

    IdEntry *entry = (IdEntry *)(intptr_t)handle;
    (*env)->DeleteGlobalRef(env, entry->class_ref);
    free(entry);
}
~~~

Đây là **một tệp C đầy đủ** cho JNI example. Thư viện không có `main`; JVM gọi ba exported JNI functions. Kiểm tra header do `javac -h` sinh và không đổi tên Java mà quên compile lại C.

Các quyết định đáng chú ý:

1. **Lookup trước khi publish:** nếu `GetFieldID`/`GetMethodID` thất bại, không lưu nửa cache. `NULL` là tín hiệu lỗi, không phải ID để thử lại khi gọi.
2. **Global class ref:** `NewGlobalRef` nâng tham chiếu class của lời gọi này thành strong global; cache giữ nó suốt thời gian được phép dùng hai ID. Sau `DeleteGlobalRef`, không còn quyền dùng IDs qua cache ấy.
3. **Không ref-count ID:** ID do JVM quản lý, không `free`, không `NewGlobalRef` và không `DeleteLocalRef` trực tiếp trên `jmethodID`/`jfieldID`.
4. **Kiểm tra loại object:** `IsInstanceOf` dùng **Class object đã cache**, không tìm lại theo tên. Kiểm tra `object == NULL` trước, vì theo JNI một null reference có thể cast sang bất kỳ class nào (nên chỉ `IsInstanceOf` không đủ để bắt null).
5. **Pending exception:** `CallIntMethod` có thể chạy Java code ném exception. Sau khi gặp exception, trả về sớm để Java thấy exception gốc; không thay bằng giá trị `0` thành kết quả thành công.
6. **Không cache `JNIEnv *`:** mỗi native call nhận env của đúng thread; chỉ struct chứa class global và hai ID.
7. **Lifecycle native:** `free(entry)` nằm sau `DeleteGlobalRef`, đúng một lần; Java synchronized methods bảo vệ against close trong khi calculation đang chạy qua API public.

Về kiểu handle: `intptr_t` biểu diễn pointer bằng integer trên các target thông dụng; kết hợp ép kiểu `(jlong)(intptr_t)` là mẫu demo được giới hạn bởi `_Static_assert`. Giá trị handle **không phải** một Java object reference và không được GC tự giải phóng. Trên nền tảng không hỗ trợ `intptr_t`, cần thay bằng cơ chế handle khác và kiểm tra compatibility của ABI.

## 5. Build và chạy thực tế

Đặt `JAVA_HOME` trỏ tới JDK thích hợp và dùng compiler kiến trúc tương ứng với JVM. Chạy các lệnh từ thư mục `id-cache-demo`.

### 5.1. Linux (GCC/Clang, C11)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/IdCache.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/idcache.c -o build/lib/libidcache.so

java -Djava.library.path=build/lib \
  -cp build/classes demo.IdCache
~~~

### 5.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/IdCache.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/idcache.c -o build/lib/libidcache.dylib

java -Djava.library.path=build/lib \
  -cp build/classes demo.IdCache
~~~

### 5.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src\demo\IdCache.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\idcache.c ^
  /link /OUT:build\lib\idcache.dll

java -Djava.library.path=build\lib -cp build\classes demo.IdCache
~~~

Các lệnh Windows trên là **Command Prompt**, ký tự `^` nối dòng; dùng `cl` từ Visual Studio Developer Command Prompt và JDK đúng architecture. Tùy trình biên dịch, warning từ các header hệ thống khác nhau; điều cần nhất là compile/link thành công và chạy đúng hàm JNI. Nếu `JAVA_HOME` chưa đặt, cấu hình môi trường trước khi build.

Với Java 17+, mã Java thuần và hai native functions tính toán hoạt động như sau:

~~~text
21
33
closed
~~~

Tại lần thứ nhất, `value = 7`, `twice() = 14`, JNI trả `7 + 14 = 21`. Lần thứ hai, `11 + 22 = 33`. Sau `try (cache)`, Java tự gọi `close()`; gọi `close()` thêm lần nữa không hủy hai lần, rồi `calculate` ném `IllegalStateException` và được in thành `closed`. Stdout ở trên không bao gồm những thông báo build/compiler trên stderr.

### 5.4. Kiểm tra symbol và chữ ký

~~~sh
javap -s -classpath build/classes demo.IdCache
nm -D --defined-only build/lib/libidcache.so
~~~

Trên Linux, bảng dynamic symbols cần chứa ba tên:

~~~text
Java_demo_IdCache_nativeOpen
Java_demo_IdCache_nativeCalculate
Java_demo_IdCache_nativeClose
~~~

Trên macOS, có thể kiểm tra `nm -gU build/lib/libidcache.dylib` (công cụ có thể thêm `_` trước tên symbol). Trên Windows, kiểm tra `dumpbin /exports build\lib\idcache.dll`. Nếu method name hoặc package Java thay đổi, tái sinh header và build lại thư viện; đừng tự đổi generated header.

## 6. Vì sao ví dụ này giữ ID hợp lệ đúng vòng đời?

Diễn tiến một instance:

~~~text
new IdCache(Sample.class)
    |
    | GetFieldID / GetMethodID -> IDs cho Sample.class hiện tại
    | NewGlobalRef(Sample.class) -> class được giữ sống
    | malloc(IdEntry) -> lưu strong ref + 2 IDs
    v
cache OPEN
    |
    | calculate(...): lấy lại IDs từ cùng IdEntry
    | IsInstanceOf(..., class_ref)
    | GetIntField + CallIntMethod
    v
close()
    |
    | đồng bộ để không có calculate song song trên cùng instance
    | nativeHandle = 0
    | DeleteGlobalRef(class_ref)
    | free(IdEntry)
    v
cache CLOSED -> không gọi với IDs cũ
~~~

Trong khoảng `OPEN`, strong global ref bảo đảm class không bị unload chỉ vì không còn Java reference khác. IDs vì thế hợp lệ khi method được gọi. Trong khoảng `CLOSED`, Java cấm dùng handle; native entry đã free. Class có thể trở nên eligible for unloading khi mọi reference khác không còn (không có lời hứa sẽ unload ngay).

Ví dụ cố ý **không giữ cache sống tới `JNI_OnUnload`**: gọi `close` độc lập cho phép strong global reference biến mất trước khi classloader muốn được GC. Khi sử dụng pattern này trong server, dọn từng instance, đặc biệt trước khi unload plugin hoặc dừng module.

Cũng cần phân biệt: JVM có thể cập nhật nội bộ representation của method qua tối ưu JIT, nhưng không vì vậy mà một ID được cache đúng class tự nhiên vô hiệu khi class vẫn đang sống. Điều kiện class lifetime mới là hợp đồng JNI thông thường; những thao tác đặc biệt như instrumentation/redefinition đòi tuân thủ thêm hợp đồng công cụ liên quan.

## 7. Những chi tiết khó dễ gây lỗi

### 7.1. Local `jclass` không dùng sau khi native method return

~~~c
/* SAI: cls là local reference, hết hiệu lực sau lời gọi hiện tại. */
static jclass cached_class;

JNIEXPORT void JNICALL Java_demo_Example_save(JNIEnv *env,
                                              jclass owner) {
    (void) env;
    cached_class = owner;
}
~~~

Đoạn này chỉ minh họa một lỗi; không phải mã để chạy. `owner` là local ref được JVM cấp cho lời gọi native static. Gán nó vào C static chỉ sao chép handle, **không đổi** thành global. Sau khi JNI call kết thúc, dùng lại handle là sai dù class chưa unload. Nếu thực sự phải giữ lớp qua nhiều lời gọi, dùng `NewGlobalRef` rồi hủy bằng `DeleteGlobalRef` khi không còn dùng.

### 7.2. IDs có thể khác với references và không thể giải phóng bằng JNI ref API

~~~c
jmethodID id = (*env)->GetMethodID(env, clazz, "twice", "()I");
/* Không làm như sau:
   (*env)->NewGlobalRef(env, (jobject) id);
   (*env)->DeleteGlobalRef(env, (jobject) id);
*/
~~~

`jmethodID`/`jfieldID` là opaque IDs, có representation do JVM quyết định. Đừng cast sang `jobject` để “giữ sống”, đừng `free`, đừng tự thao tác như pointer đến cấu trúc JVM. Chỉ dùng chúng làm tham số các JNI API chấp nhận ID tương ứng khi defining class còn hợp lệ.

### 7.3. Đừng cache duy nhất theo chuỗi tên lớp

Nếu registry C lưu `"com.example.Plugin" -> jmethodID`, một plugin loader mới có thể nhận ID thuộc class loader cũ. Registry nên gắn ID với **Class object identity** và lifetime token/handle cụ thể; việc dùng `IsSameObject` để so sánh classes giúp tránh phụ thuộc địa chỉ của local reference.

Với weak cache, nếu weak Class ref đã được thu hồi, phải bỏ ID cũ và tạo cache lại cho Class mới, không chỉ cập nhật ô `jclass`. Với strong cache, phải có cleanup rõ để class loader cũ không bị pin mãi. Các pattern này là lựa chọn thiết kế khác nhau; không nên pha trộn và hy vọng GC tự xử lý giúp.

### 7.4. `FindClass` có thể chọn loader không mong muốn

`FindClass(env, "com/example/Plugin")` phụ thuộc vào ngữ cảnh class loader của native frame, và quy tắc khi gọi từ `JNI_OnLoad` hoặc native thread được attach có khác biệt. Trên môi trường plugin/server, tìm lớp bằng tên có thể trả về sai hoặc `ClassNotFoundException` dù lớp nằm ở loader khác.

Cách dễ kiểm chứng là **Java truyền `Class<?>` thực tế** xuống native trong bước tạo cache, như `IdCache(Sample.class)`; khi cần tìm lớp bằng tên phải quy định loader đúng và dùng cơ chế Java `ClassLoader.loadClass` phù hợp. Điều này đặc biệt quan trọng nếu thread C tự attach vào JVM rồi callback đến các class do custom loader định nghĩa.

### 7.5. Không dùng cache sau khi close, kể cả một lệnh

Một `jmethodID` không tự bị “zero hóa” khi hủy class reference. Sau `DeleteGlobalRef` và `free`, pointer C cũ có thể vẫn chứa các byte cũ; dereference/use-after-free là lỗi native nặng. `nativeHandle = 0` trong Java ngăn call tiếp theo qua wrapper này, nhưng **nếu bạn đã phát tán handle sang nơi khác**, không đủ để ngăn race. Khi thêm callback bất đồng bộ hoặc native worker thread, cần thiết kế thứ tự dừng công việc, chờ các lời gọi đang chạy hoàn tất, rồi mới free; có thể dùng mutex, reference counting hoặc generation-based handles.

### 7.6. Thread safety của cache và `JNIEnv *`

IDs và strong global refs có thể được sử dụng trên nhiều thread khi lifetime đúng, nhưng **`JNIEnv *` chỉ thuộc về thread mà nó được lấy**. Nếu callback trên native worker thread, attach theo Invocation API rồi lấy env của chính thread đó; không giữ `JNIEnv *` đã nhận từ lời gọi Java trước.

Trong ví dụ, `synchronized` trên instance Java bảo vệ chuỗi read/close của cùng cache. `GetFieldID` và `GetMethodID` được thực hiện một lần trong constructor, cấu trúc chỉ được publish sau khi cả IDs và global class ref hợp lệ. Đừng đồng thời thay đổi trường của struct cache mà những thread khác đọc mà thiếu synchronization. JNI APIs không tự giải quyết data race trong cấu trúc C của bạn.

### 7.7. Class initialization và lookup exception

`GetFieldID`/`GetMethodID` có thể kích hoạt class initialization. Nếu `<clinit>` ném exception, code native phải dừng tạo cache, để exception quay về Java. Đừng tiếp tục chạy `Call<Type>Method` hoặc `NewGlobalRef` tùy tiện khi JNI có pending exception.

Trong ví dụ, `nativeOpen` chỉ publish `IdEntry` sau khi lookup thành công và global reference tạo được. Nếu `malloc` thất bại sau `NewGlobalRef`, code xóa global ref ngay trước khi ném lỗi. Không có đường nào cố tình giữ một cache nửa khởi tạo.

## 8. Khi nào chọn chiến lược nào?

| Bối cảnh | Cách hợp lý | Vấn đề phải quản lý |
| --- | --- | --- |
| Ứng dụng đơn giản, một class tồn tại gần suốt vòng đời JVM | `<clinit>` gọi native init, cache IDs theo class tương ứng | Tránh static C cache dùng chung sai loader, xác minh cleanup |
| Native resource có `open/close` rõ ràng, caller chủ động sở hữu | Struct chứa strong global `jclass` + IDs, `AutoCloseable` | Bắt buộc close; class bị giữ sống trong lúc cache mở |
| Module/plugin cần hot unloading thường xuyên | Class-keyed registry không giữ strong ref lâu dài, có thể weak ref | Revalidate và rebuild IDs, đồng bộ GC/unload |
| Native callback gọi qua nhiều thread | Cache immutable ID theo class + global/strong local ref đúng lifetime | Không cache `JNIEnv *`; attach/detach và khóa shutdown |
| Nhiều defining loaders cùng tên class | Cache keyed theo Class identity/loader context | Không dùng tên lớp làm unique key; tránh stale IDs |

**Chọn strong cache khi bạn có điểm close được thực thi chắc chắn.** Chọn weak/recompute khi unloading là một yêu cầu chức năng và bạn sẵn sàng xử lý thêm synchronization cùng race với GC. Với hệ thống dùng `JNI_OnLoad`/`JNI_OnUnload`, phân tích kỹ việc global class references có pin loader hay không, tránh thiết kế dependency vòng tròn khiến unload không bao giờ xảy ra.

## 9. Bài tập kiểm tra theo trình tự

1. **Kiểm tra cache và output.** Chạy ví dụ trên, xác nhận stdout có ba dòng `21`, `33`, `closed`. Xác nhận `javac -h` sinh `demo_IdCache.h` và native library export đủ ba function.
2. **Kiểm tra sai loại object.** Trong Java, gọi `cache.calculate("hello")` khi cache đang mở. Native `IsInstanceOf` từ chối và báo `IllegalArgumentException`; class/IDs vẫn còn hiệu lực để dùng tiếp nếu caller bắt lỗi.
3. **Kiểm tra lỗi field name.** Trong C đổi `"value"` thành `"missing"`, rebuild; `GetFieldID` trả `NULL` và Java sẽ nhận lỗi tương ứng. Đừng cho constructor tạo cache với một ID chưa hợp lệ.
4. **Kiểm tra method signature.** Trong C đổi `"()I"` thành `"()J"` nhưng giữ Java method trả `int`, rebuild; lookup sẽ không phù hợp. Trả lại descriptor đúng trước khi hoàn thành.
5. **Kiểm tra close.** Đặt lời gọi `cache.calculate(...)` sau `close`; phải nhận `IllegalStateException` trong Java, không rơi vào native function dùng pointer đã giải phóng.
6. **Thử hai cache.** Mở hai `IdCache(Sample.class)` rồi đóng từng cái. Mỗi instance có native global reference riêng; đóng một cache không làm cache còn mở mất hiệu lực. Khi đóng tất cả, không còn global ref do hai cache này sở hữu.
7. **Xem loader identity.** Với hai custom `ClassLoader` thật sự định nghĩa hai class cùng tên, thử thiết kế cache cho từng `Class<?>` riêng. Đừng chuyển handle/IDs giữa hai lớp; so sánh identity bằng `IsSameObject` hoặc phía Java bằng `==` trên `Class<?>`.

Trong debug, dùng `java -Xcheck:jni -Djava.library.path=build/lib -cp build/classes demo.IdCache` (một số kiểm tra JNI được JVM bật). Công cụ này **không** phát hiện đầy đủ mọi lỗi C memory lifetime, không biến một ID hết hiệu lực thành hợp lệ. Với mã native phức tạp, dùng C debugger và sanitizer có hỗ trợ trên target compiler.

## 10. Checklist trước khi lưu cache JNI trong sản phẩm

- **Class identity:** Cache thuộc `Class<?>` cụ thể nào? Có nhiều `ClassLoader` hoặc hot reload không? Key là class object hay chỉ tên?
- **Member metadata:** Method/field name, descriptor, static/instance và kiểu `Call<Type>...` hoặc `Get<Type>...` đã khớp tuyệt đối chưa?
- **Lifetime:** Giữ defining class sống bằng strong ref rõ scope, hay có weak ref + phương thức tái tra cứu ID? ID có còn hợp lệ ở lúc gọi?
- **Reference category:** `jclass` local/global/weak nào? Có `NewGlobalRef`/`DeleteGlobalRef` hoặc `NewLocalRef`/`DeleteLocalRef` đúng cặp? IDs không bị coi là `jobject`?
- **Initialization:** Tra cứu thành công toàn bộ rồi mới publish cache? Có pending exception, `NULL`, lỗi `malloc` hoặc khả năng class initialization thất bại không?
- **Cleanup:** Có cơ chế `close`/destroy độc lập với `JNI_OnUnload`? Ai dừng callback/worker thread và chờ active call trước khi free? Double-close có an toàn không?
- **Threading:** Có dùng đúng `JNIEnv *` ở từng thread, không có race giữa lookup/invalidation/use/free, không giữ local ref quá hạn không?
- **Verification:** Có kiểm thử null, wrong class, missing field/method, close-after-use, multi-instance, custom ClassLoader và class unload/reload khi môi trường hỗ trợ không?

Một cache JNI đúng phải giữ được bất biến:

> **Không một `jmethodID` hoặc `jfieldID` nào được sử dụng nếu không còn bảo đảm rằng defining class của ID đó đang sống, và không một JNI object reference nào được giữ vượt phạm vi loại reference của nó.**

Nếu không chứng minh được bất biến này với cách lưu cache hiện tại, chỉ tối ưu tra cứu sẽ tạo ra một lỗi class unloading khó tái hiện hơn nhiều so với chi phí lookup ban đầu.

### Tài liệu chuẩn để tra cứu

- Oracle, [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): `Accessing Fields and Methods`, lưu ý ID không ngăn class unload và local/global references.
- Oracle, [JNI Specification — Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `GetMethodID`, `GetFieldID`, `NewGlobalRef`, `DeleteGlobalRef`, `NewWeakGlobalRef`, `NewLocalRef`, `IsInstanceOf` và `ExceptionCheck`.
- Android Developers, [JNI tips](https://developer.android.com/ndk/guides/jni-tips): ví dụ về caching IDs, class initialization, global refs và class loaders (các nguyên tắc JNI cần đặt trong bối cảnh platform).