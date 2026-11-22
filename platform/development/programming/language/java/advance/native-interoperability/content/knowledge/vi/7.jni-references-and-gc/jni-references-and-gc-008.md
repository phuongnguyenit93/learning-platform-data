# Thiết kế quyền sở hữu tham chiếu để tránh rò rỉ hoặc dùng tham chiếu hết hạn

## 1. Mục tiêu và bối cảnh: tham chiếu Java đi qua ranh giới native

Khi Java gọi mã C/C++ qua **JNI (Java Native Interface)**, một `jobject` không đơn thuần là địa chỉ bộ nhớ có thể cất giữ mãi. Đó là **tham chiếu do JVM quản lý**, có quy tắc về phạm vi, thread, thời điểm hết hạn và tác động đến garbage collector (GC). Một object có thể vẫn còn sống trong Java, trong khi **JNI local reference dùng để trỏ tới nó đã hết hạn**. Ngược lại, một JNI strong global reference có thể vô tình giữ object sống và gây rò rỉ dù Java application tưởng rằng đã bỏ mọi tham chiếu.

Bài này tập trung thiết kế ownership đúng: **ai tạo reference, ai được phép sử dụng, dùng trong bao lâu, ai phải xóa và điều gì xảy ra khi lỗi/hủy đồng thời**. Sau khi học, bạn cần thực hiện được:

- Phân biệt **local**, **strong global** và **weak global** JNI references theo lifetime, GC reachability và thao tác cleanup.
- Chuyển một local reference thành global reference một cách hợp lệ nếu native code cần giữ object sau khi phương thức JNI return.
- Thu hồi global/weak global ref đúng một lần về mặt logic; xử lý thay thế, lỗi cấp phát và đóng nhiều lần.
- Quản lý local refs trong vòng lặp/callback/attached native thread và tránh dùng tham chiếu sau lifetime.
- Định nghĩa owner rõ ràng cho native resource lẫn Java object; xử lý race khi close cùng lúc với callback/native access.
- Viết và chạy ví dụ **Java 17+ + C11**, quan sát hành vi có thể kiểm chứng mà không dựa vào thời điểm GC chạy.

**Phạm vi:** object references trong JNI và mối liên hệ với GC. Những địa chỉ của native memory cấp phát bằng `malloc`/`free`, direct buffer hay FFM có **quy tắc giải phóng khác**; không được trộn hai loại ownership.

## 2. Tách ba thứ dễ bị nhầm: object, reference và native allocation

~~~text
Java heap:
    Object O
       ^
       | (tham chiếu do JVM theo dõi)
       |
    Java local variable         JNI local ref         JNI strong global ref
    chỉ có trong Java           trong một JNI frame   trong bảng global của JVM
                                                         |
Native heap:                                            | giữ O reachable
    malloc(...) ---> block N                             |
    free(N) giải phóng N; không xóa JNI ref tới O --------+
~~~

- **Java object O:** đối tượng trên heap do JVM quản lý. GC quyết định thu hồi khi nó không còn reachable theo quy tắc GC; lập trình viên không được giả định địa chỉ vật lý cố định hoặc thời điểm thu hồi.
- **JNI reference handle:** giá trị kiểu `jobject` hoặc các kiểu dẫn xuất (`jclass`, `jstring`, `jobjectArray`, …) do JNI định nghĩa. Chỉ hợp lệ theo **loại và lifetime** đã cấp. Không biến một `jobject` thành native pointer lâu dài bằng cách cast sang `void *` hoặc `jlong`.
- **Native memory:** nếu C cấp phát một block `malloc`, C phải có quy ước giải phóng phù hợp. `DeleteGlobalRef` không gọi `free` cho block native, và `free` không xóa global reference. Nếu một handle nắm cả hai tài nguyên, cần **hai cleanup độc lập theo thứ tự hợp lý**.

Một reference được xóa **không có nghĩa object lập tức bị GC**: object vẫn có thể reachable qua những tham chiếu khác. Ngược lại, object còn reachable không giúp bạn “hồi sinh” một local reference đã bị xóa hoặc hết JNI frame. **Lifetime của handle và lifetime của referent là hai điều kiện riêng biệt.**

## 3. Bảng chọn reference: loại nào sở hữu lifetime nào?

| Loại | Cách nhận | Thời gian handle hợp lệ | Ảnh hưởng đến GC | Việc phải làm |
|---|---|---|---|---|
| **Local** (`jobject`, `jstring`, …) | Tham số native method, đa số JNI object-returning APIs, `NewLocalRef` | Trong JNI local frame và thread tạo ra; thường tự hết khi native call return | Giữ referent reachable trong thời gian local ref còn hợp lệ | `DeleteLocalRef` sớm ở vòng lặp; có thể dùng `PushLocalFrame`/`PopLocalFrame` |
| **Strong global** (`jobject`) | `NewGlobalRef(env, ref)` | Cho đến khi `DeleteGlobalRef(env, ref)` | Là strong JNI root, có thể giữ referent sống lâu hơn mong muốn | Owner phải gọi `DeleteGlobalRef` trong cleanup |
| **Weak global** (`jweak`) | `NewWeakGlobalRef(env, ref)` | Handle tồn tại tới `DeleteWeakGlobalRef`, nhưng referent có thể bị GC trước đó | Không giữ referent sống | Chủ động xóa weak handle; **promote** bằng `NewLocalRef` trước khi truy cập |

Một tham số `jobject obj` được JVM đưa vào một native method thường là **local reference**. Với local ref, lời gọi:

~~~c
/* Ví dụ sai: một tham số local bị lưu vượt lifetime. */
static jobject cached;             /* Không sở hữu reference hợp lệ. */

void wrong(JNIEnv *env, jobject obj) {
    (void)env;
    cached = obj;                  /* Sau khi JNI frame kết thúc, cached hết hạn. */
}
~~~

để lại handle không hợp lệ cho lần callback sau, kể cả khi Java code vẫn đang giữ object thật. Sửa bằng `NewGlobalRef` nếu contract cần giữ object lâu dài, và phải có đường cleanup tương ứng.

**Quy tắc quyết định:** Nếu chỉ dùng object trong **lời gọi native hiện tại**, local ref thường là đủ. Nếu cần dùng sau khi lời gọi kết thúc, trên callback hoặc giữa các thread, dùng **strong global** (khi cần bảo đảm object còn sống), hoặc **weak global + promote** (khi không muốn kéo dài reachability). Không có “một loại ref tốt nhất” cho mọi mục đích.

## 4. Ownership contract: trước khi tạo reference, phải trả lời sáu câu hỏi

Thiết kế một resource có thể kiểm tra được bằng bảng hợp đồng:

| Câu hỏi | Giá trị cần quyết định rõ |
|---|---|
| **Creator/owner?** | Java wrapper, một native context riêng, singleton registry hay engine? Chỉ một owner chịu trách nhiệm cuối cùng cho việc release |
| **Borrower?** | Thread/callback nào chỉ mượn handle trong một phạm vi hẹp? Có được giữ bản sao sau call không? |
| **Lifetime bắt đầu/kết thúc?** | `NewGlobalRef`/`NewWeakGlobalRef` thành công → `Delete...Ref`; local → hết frame hoặc delete trước |
| **GC semantics?** | Cần giữ object sống (strong) hay chấp nhận object biến mất (weak)? |
| **Concurrency?** | Khi Java gọi `close()` đúng lúc native callback đang truy cập, ai chặn việc xóa quá sớm? |
| **Lỗi và quyền sở hữu?** | Nếu tạo ref mới thất bại, ref cũ có còn không? Cleanup nào bắt buộc cả trong exception/failure path? |

Ví dụ một contract hợp lý cho cache một Java listener: **native context là owner của một strong global ref** được tạo khi đăng ký; callback chỉ **mượn một local ref hợp lệ** trong lúc thực thi; `unregister/close` ngăn callback mới, chờ callback đang chạy thoát rồi xóa global; Java chỉ giải phóng bản thân context sau khi JNI xác nhận không còn người mượn. Nếu vẫn muốn listener có thể bị GC khi Java bỏ nó, thay strong bằng weak, nhưng mỗi callback phải promote và xử lý trường hợp referent đã biến mất.

Hãy mô tả ownership bằng **sự kiện thực tế**, không dùng “GC sẽ dọn khi cần” làm cơ chế hủy. GC không tự biết khi nào native cache cần bỏ `NewGlobalRef` hoặc khi nào `malloc` cần `free`.

## 5. Ví dụ chạy được: một owner của strong global reference, cleanup tường minh

Ta tạo **một slot global duy nhất cho cả process**. Java public API gồm `retain(Object)`, `refersTo(Object)`, `release()` và `countNonNull(Object[])`. Các phương thức thao tác slot được khai báo **`static synchronized`**, nên trong phạm vi chỉ truy cập qua API này, mỗi thao tác slot được bảo vệ bởi cùng monitor của class. Đây là mẫu học tập có **một slot**, không phải thiết kế cho nhiều session độc lập; mở rộng nhiều owner ở mục 9.

Luồng chính:

~~~text
Java retain(marker)
    -> JNI argument local ref
    -> NewGlobalRef(marker) thành công
    -> held_global nắm strong ref
Java refersTo(marker)
    -> IsSameObject(held_global, marker) == JNI_TRUE
Java release()
    -> held_global = NULL
    -> DeleteGlobalRef(old)
Java refersTo(marker)
    -> held_global NULL => false, không giải tham chiếu handle cũ
~~~

### 5.1. Java source hoàn chỉnh, JDK 17+

Tạo file **`src/demo/jni/ReferenceOwnershipDemo.java`**:

~~~java
package demo.jni;

import java.util.Objects;

public final class ReferenceOwnershipDemo {
    static {
        System.loadLibrary("refownership");
    }

    private ReferenceOwnershipDemo() {}

    private static native void replace0(Object value);
    private static native boolean same0(Object candidate);
    private static native void clear0();
    private static native int countNonNull0(Object[] values);

    public static synchronized void retain(Object value) {
        replace0(Objects.requireNonNull(value, "value"));
    }

    public static synchronized boolean refersTo(Object candidate) {
        return same0(candidate);
    }

    public static synchronized void release() {
        clear0();
    }

    public static int countNonNull(Object[] values) {
        return countNonNull0(Objects.requireNonNull(values, "values"));
    }

    public static void main(String[] args) {
        Object marker = new Object();
        try {
            retain(marker);
            System.out.println("retainedSame=" + refersTo(marker));
            System.out.println("retainedOther=" + refersTo(new Object()));
            System.out.println("nonNull=" + countNonNull(
                    new Object[]{marker, null, new Object()}));
        } finally {
            release();
        }
        System.out.println("afterRelease=" + refersTo(marker));
    }
}
~~~

Giải thích các điểm thiết kế quan trọng:

- `Objects.requireNonNull` giữ contract `retain`: ref được đăng ký phải trỏ tới một object không null. `refersTo(null)` vẫn được cho phép, và `IsSameObject` sẽ so sánh identity với null.
- `retain`, `refersTo` và `release` dùng chung **class monitor**. Không có đường truy cập khác tới `held_global` từ native thread trong ví dụ. Nếu bổ sung native worker/registry đa luồng, phải bổ sung đồng bộ ở C/context thay vì chỉ dựa vào Java.
- `countNonNull` **không dùng slot toàn cục**. Nó cho thấy một native method độc lập cần xóa local refs tạm trong vòng lặp.
- `finally` luôn gọi `release` nếu khối test kết thúc bình thường hoặc ném exception. Không gọi `System.gc()` vì ví dụ đang kiểm tra **quyền sở hữu handle**, không kiểm tra thời điểm GC.
- `release` có thể gọi nhiều lần; việc lặp lại không double-delete. Sau khi release, `refersTo` chỉ trả `false`, không truy cập reference đã bị xóa.

### 5.2. Biên dịch Java, sinh header từ chữ ký thật

Từ thư mục thực hành `jni-reference`:

~~~sh
mkdir -p src/demo/jni native out
javac --release 17 -h native -d out src/demo/jni/ReferenceOwnershipDemo.java
~~~

`javac -h` sinh **`native/demo_jni_ReferenceOwnershipDemo.h`** và class ở `out/demo/jni/ReferenceOwnershipDemo.class`. Không sửa tay generated header. Khi chạy:

~~~sh
javap -s -p -classpath out demo.jni.ReferenceOwnershipDemo
~~~

bốn native methods phải có descriptors sau:

~~~text
replace0(java.lang.Object);           (Ljava/lang/Object;)V
same0(java.lang.Object);              (Ljava/lang/Object;)Z
clear0();                              ()V
countNonNull0(java.lang.Object[]);    ([Ljava/lang/Object;)I
~~~

Bảng trên ghi tóm tắt **method và descriptor**, không phải nguyên văn toàn bộ output `javap`. Các ký hiệu: `L...;` là object reference, `[` là array, `Z` là boolean, `V` là void, `I` là int. Header thật sẽ có các prototype C tương ứng, với `JNIEnv *` và `jclass` đứng trước tham số Java vì các native method đều là `static`.

### 5.3. Native C source hoàn chỉnh, có đường hủy và đường lỗi

Tạo file **`native/reference_ownership.c`**:

~~~c
#include "demo_jni_ReferenceOwnershipDemo.h"

static jobject held_global = NULL;

JNIEXPORT void JNICALL Java_demo_jni_ReferenceOwnershipDemo_replace0(
        JNIEnv *env, jclass ignored, jobject value) {
    (void)ignored;
    jobject replacement = (*env)->NewGlobalRef(env, value);
    if (replacement == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            jclass error_class = (*env)->FindClass(
                    env, "java/lang/OutOfMemoryError");
            if (error_class != NULL) {
                (*env)->ThrowNew(env, error_class, "Cannot create global ref");
                (*env)->DeleteLocalRef(env, error_class);
            }
        }
        return;
    }

    jobject old = held_global;
    held_global = replacement;
    if (old != NULL) {
        (*env)->DeleteGlobalRef(env, old);
    }
}

JNIEXPORT jboolean JNICALL Java_demo_jni_ReferenceOwnershipDemo_same0(
        JNIEnv *env, jclass ignored, jobject candidate) {
    (void)ignored;
    if (held_global == NULL) {
        return JNI_FALSE;
    }
    return (*env)->IsSameObject(env, held_global, candidate)
           ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL Java_demo_jni_ReferenceOwnershipDemo_clear0(
        JNIEnv *env, jclass ignored) {
    (void)ignored;
    if (held_global != NULL) {
        jobject old = held_global;
        held_global = NULL;
        (*env)->DeleteGlobalRef(env, old);
    }
}

JNIEXPORT jint JNICALL Java_demo_jni_ReferenceOwnershipDemo_countNonNull0(
        JNIEnv *env, jclass ignored, jobjectArray values) {
    (void)ignored;
    jsize length = (*env)->GetArrayLength(env, values);
    jint count = 0;
    for (jsize i = 0; i < length; ++i) {
        jobject element = (*env)->GetObjectArrayElement(env, values, i);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Java exception remains pending. */
        }
        if (element != NULL) {
            ++count;
            (*env)->DeleteLocalRef(env, element);
        }
    }
    return count;
}
~~~

Code trên là một native library đầy đủ cho Java source của bài. Điểm cốt lõi:

1. `NewGlobalRef(env, value)` tạo **một strong global ref mới**. Không gán thẳng `held_global = value` vì `value` là local reference của lời gọi JNI hiện tại.
2. Khi **tạo ref mới thất bại**, code giữ `held_global` cũ. Nếu JVM chưa để lại pending exception, code cố tạo `OutOfMemoryError` cho Java. Không bỏ ref cũ chỉ vì quá trình thay thế không thành công.
3. Khi tạo thành công, `held_global` được cập nhật rồi ref cũ được `DeleteGlobalRef`. Lần `retain` tiếp theo không âm thầm tích lũy các global refs không còn dùng.
4. `clear0` đặt slot về `NULL` rồi mới xóa ref cũ; gọi lần nữa là no-op. Bên Java không bao giờ nhận lại hay sử dụng biến `old` đã xóa.
5. `IsSameObject` so sánh **object identity theo JNI**, không so sánh giá trị số của handle. Không giả định hai reference tới cùng object phải có địa chỉ/số bit giống nhau.
6. `GetObjectArrayElement` tạo local ref cho từng phần tử không null; `DeleteLocalRef` ngay sau khi dùng giúp không tích lũy local refs theo chiều dài mảng. Nếu JNI API ném exception, code return với pending Java exception; không gọi tiếp API thao tác object trong trạng thái lỗi.
7. `error_class` được `FindClass` trả dưới dạng **local ref**, nên được xóa ngay sau `ThrowNew`. Những hàm cleanup JNI thích hợp được phép dùng khi exception đang pending.

**Giới hạn cố ý:** C chỉ có một `held_global` ở file scope; Java wrappers `static synchronized` loại trừ các thao tác slot đồng thời **nếu chỉ truy cập qua wrappers**. Không mở rộng thiết kế này bằng cách cho native background thread dùng biến đó mà chưa có lock/lifetime protocol.

### 5.4. Build và chạy Linux, macOS, Windows

Chạy các lệnh từ thư mục `jni-reference` có cây file:

~~~text
jni-reference/
├─ src/demo/jni/ReferenceOwnershipDemo.java
├─ native/demo_jni_ReferenceOwnershipDemo.h   (tự sinh)
├─ native/reference_ownership.c
└─ out/demo/jni/ReferenceOwnershipDemo.class   (tự sinh)
~~~

**Linux** (GCC/Clang; `JAVA_HOME` trỏ đến gốc JDK; nếu chưa đặt và shell có `readlink -f`, dùng lệnh đầu để suy ra):

~~~sh
export JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Inative \
  -o librefownership.so native/reference_ownership.c

java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

**macOS** (Xcode Command Line Tools; chọn kiến trúc tương thích JVM):

~~~sh
export JAVA_HOME="$(/usr/libexec/java_home)"
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Inative \
  -o librefownership.dylib native/reference_ownership.c

java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

**Windows, MSVC Developer Command Prompt (CMD)** với `JAVA_HOME` và compiler đúng architecture:

~~~bat
javac --release 17 -h native -d out src\demo\jni\ReferenceOwnershipDemo.java

cl /nologo /W4 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /Inative ^
  native\reference_ownership.c /Fe:refownership.dll

java -Xcheck:jni -Djava.library.path=. -cp out demo.jni.ReferenceOwnershipDemo
~~~

Trong CMD, dấu `^` dùng nối dòng; không chạy nguyên cú pháp CMD trong PowerShell. `loadLibrary("refownership")` tự ánh xạ thành `librefownership.so` (Linux), `librefownership.dylib` (macOS) hay `refownership.dll` (Windows). `-cp out` là classpath Java; `-Djava.library.path=.` là vị trí tìm native library; chúng không thay thế cho nhau.

Với source đã cho, **stdout chính xác**:

~~~text
retainedSame=true
retainedOther=false
nonNull=2
afterRelease=false
~~~

Chương trình không in xác nhận object đã bị GC; **`afterRelease=false` chỉ chứng minh slot global đã được xóa**. Biến Java `marker` vẫn có thể giữ object sống, và GC không có nghĩa vụ thu hồi ngay.

Ví dụ C/Java đã được kiểm chứng trên Linux bằng **JDK 21, `javac --release 17`, GCC với `-std=c11 -Wall -Wextra -Werror -pedantic` và `java -Xcheck:jni`**. Đã đối chiếu exported JNI symbols và bốn descriptors từ `javap`. Các lệnh macOS và Windows áp dụng cùng hợp đồng JNI nhưng cần compiler/toolchain đúng nền tảng.

## 6. Local refs: tự hết ở cuối frame vẫn có thể làm đầy bảng tạm

Mỗi JNI call tạo local frame có các tham chiếu argument và refs tạm được JNI tạo thêm. JVM thường giải phóng các local refs của frame khi native method return, **nhưng không bảo đảm chương trình có thể tạo vô hạn refs trong một native call dài**. Vì vậy nếu làm một vòng lặp hàng nghìn/hàng triệu phần tử và giữ mỗi `GetObjectArrayElement` đến cuối call, native code có thể dùng ngày càng nhiều không gian tham chiếu local.

Mẫu áp dụng từ ví dụ:

~~~c
/* Trích từ countNonNull0 ở mục 5, không phải C program độc lập. */
jobject element = (*env)->GetObjectArrayElement(env, values, i);
if ((*env)->ExceptionCheck(env)) {
    return 0;                    /* Exception chuyển về Java. */
}
if (element != NULL) {
    ++count;
    (*env)->DeleteLocalRef(env, element); /* Hủy ngay sau lần dùng cuối. */
}
~~~

Với một chuỗi thao tác JNI phức tạp tạo nhiều local refs cùng lúc, có thể dùng:
- `EnsureLocalCapacity(env, n)`: yêu cầu JVM bảo đảm chỗ cho ít nhất `n` local refs bổ sung trong một frame; vẫn phải xử lý lỗi được báo.
- `PushLocalFrame(env, capacity)` và `PopLocalFrame(env, result)`: mở một frame con để gom refs tạm, giải phóng chúng cùng lúc và **giữ lại tối đa một local ref `result`** chuyển lên frame cha (nếu cần).
- `DeleteLocalRef(env, ref)`: release sớm từng local handle. Đây là lựa chọn đơn giản nhất cho vòng lặp khi không cần ref sau mỗi iteration.

Một pattern minh họa frame con (không phải file C độc lập):

~~~c
/* env thuộc thread hiện tại; dùng bên trong một JNI native method. */
if ((*env)->PushLocalFrame(env, 16) < 0) {
    return NULL;    /* Thường có pending OOME; để Java xử lý. */
}

jclass type = (*env)->FindClass(env, "java/lang/String");
if (type == NULL) {
    (*env)->PopLocalFrame(env, NULL);
    return NULL;    /* Giữ Java exception của FindClass. */
}

/* type chỉ còn cần trong frame con. */
(*env)->PopLocalFrame(env, NULL);
return NULL;
~~~

Đoạn minh họa này cho thấy các refs được frame quản lý, không nhằm triển khai một native API cụ thể. Trong thực tế, nếu cần trả một object tạo trong frame con, dùng `PopLocalFrame(env, objectToKeep)` để chuyển một ref hợp lệ lên frame cha, không trả một handle đã bị xóa. Với native thread do C tự tạo và attach vào JVM, local refs có thể tồn tại suốt thời gian thread còn attached nếu không giải phóng bằng phương án thích hợp; vì vậy vòng lặp và callback dài cần cleanup chủ động.

## 7. Weak global refs: không giữ object sống nhưng phải tránh kiểm tra-then-dùng

Dùng weak global ref khi native side muốn **ghi nhớ nếu object vẫn còn reachable**, nhưng không muốn cache/callback tự mình ngăn GC thu hồi object. Ví dụ observer không sở hữu listener hoặc cache key không được phép kéo dài lifetime của đối tượng Java.

**Không an toàn:**

~~~c
/* Mẫu minh họa lỗi race; weak là một jweak đã tạo hợp lệ. */
if (!(*env)->IsSameObject(env, weak, NULL)) {
    /* GC vẫn có thể clear weak trước lời gọi JNI tiếp theo. */
    use_object_somehow(weak); /* use_object_somehow chỉ là tên minh họa. */
}
~~~

`IsSameObject(weak, NULL)` chỉ trả lời trạng thái **tại thời điểm kiểm tra**. GC có thể chạy giữa việc kiểm tra và sử dụng. Mẫu đúng là cố **promote sang strong local** trước khi dùng:

~~~c
/* Đoạn bên trong JNI native method, không phải chương trình C độc lập. */
jobject alive = (*env)->NewLocalRef(env, weak);
if (alive == NULL) {
    /* Referent đã mất, hoặc không thể tạo local ref.
       Kiểm tra pending exception và xử lý theo contract. */
    return;
}

/* alive là strong local ref trong frame hiện tại. Dùng object ở đây. */
consume_java_object(env, alive); /* Hàm ứng dụng minh họa. */

(*env)->DeleteLocalRef(env, alive);
~~~

`NewLocalRef` trả `NULL` nếu referent đã bị GC, tham chiếu đầu vào là null, hoặc tạo ref không thành công do thiếu tài nguyên. Khi `alive` hợp lệ, strong local ref **giữ referent reachable** trong lúc thao tác, nên tránh race “vừa kiểm tra xong object biến mất”. Sau khi xong, xóa `alive` để thời gian giữ strong reachability không kéo dài ngoài phạm vi cần thiết.

Owner của `jweak` vẫn phải gọi:

~~~c
/* Trong cleanup, khi không có borrower đang dùng weak. */
(*env)->DeleteWeakGlobalRef(env, weak);
weak = NULL;
~~~

**Weak global không tự biến mất như một handle resource** chỉ vì referent đã bị GC; GC có thể làm handle đó trỏ tới object đã biến mất về mặt chức năng, nhưng trách nhiệm giải phóng weak global handle vẫn thuộc owner. Không dùng `System.gc()` như phép thử bắt buộc: lời gọi là gợi ý và thời điểm GC không xác định. Một bài test đúng có thể kiểm tra đường đi “promote trả NULL” bằng mô hình/stub có kiểm soát hoặc bằng quan sát không bắt buộc, không assert rằng object phải bị thu hồi trong một khoảng thời gian cố định.

## 8. Lỗi use-after-scope: object sống không làm local handle sống lại

### Lỗi 1: cất tham số local vào biến static C

~~~c
/* Sai: local ref chỉ có hiệu lực trong lời gọi JNI hiện tại. */
static jobject listener;

JNIEXPORT void JNICALL Java_demo_jni_SomeClass_register(
        JNIEnv *env, jclass ignored, jobject callback) {
    (void)env;
    (void)ignored;
    listener = callback;
}

/* Một callback native gọi về sau dùng listener => invalid reference. */
~~~

Sửa: `listener = NewGlobalRef(env, callback)` khi đăng ký thành công; `DeleteGlobalRef(env, listener)` khi hủy; và có đồng bộ không cho callback tiếp tục dùng sau khi giải phóng. Nếu không muốn giữ callback sống, lưu `NewWeakGlobalRef` và promote ở từng callback.

### Lỗi 2: DeleteLocalRef rồi tiếp tục dùng

~~~c
jobject temporary = (*env)->GetObjectArrayElement(env, values, 0);
(*env)->DeleteLocalRef(env, temporary);
/* Dùng temporary trong JNI API sau dòng này là sai, dù array vẫn giữ object. */
~~~

Sau `DeleteLocalRef`, **handle `temporary` hết hiệu lực**. Muốn truy cập tiếp, lấy reference mới hợp lệ khi vẫn có nguồn hợp lệ. Không kiểm tra “temporary khác NULL” rồi coi nó còn sống; khác null không tương đương validity.

### Lỗi 3: xóa global ref khi callback còn chạy

~~~text
Thread callback             Thread close
-----------------------     ----------------------------
đọc shared global handle
                            DeleteGlobalRef(handle)
CallObjectMethod(handle)    <- sử dụng handle đã xóa: không an toàn
~~~

Đây là race giữa **borrow** và **delete**. Phải tổ chức giao thức ownership/call-in-flight: lock/registry bảo vệ trạng thái, giữ một strong local ref riêng trong lúc callback, hoặc chờ mọi callback hoàn tất rồi mới delete. Chỉ khai báo pointer `volatile` không giải quyết lifetime.

### Lỗi 4: quên release global refs vì “đã hết biến Java”

Java wrapper có thể mất mọi tham chiếu Java thông thường, nhưng global JNI root còn sống nên object vẫn reachable. `DeleteGlobalRef` thiếu dẫn đến **rò rỉ giữ object Java** (và có thể giữ cả object graph, classloader cùng resource khác). Còn thiếu `DeleteWeakGlobalRef` gây rò rỉ native/JVM handle resources dù không giữ referent sống. Hãy đặt cleanup trong đường hủy bình thường, lỗi, timeout và shutdown.

## 9. Từ demo singleton sang API có owner tường minh

Ví dụ ở mục 5 dùng **một global slot** để tập trung vào lifecycle. Một thư viện thật có nhiều Java session/callback nên không thể chỉ giữ một biến `static jobject held_global` chung: session A có thể thay/xóa reference thuộc session B.

Một contract đa session nên có dạng:

~~~text
Java Session
  OPEN
    | register: native context cấp phát + NewGlobalRef
    v
  ACTIVE (mỗi Session sở hữu đúng 1 native context)
    | operation: mượn reference trong thời gian ngắn
    | close: ngăn operation mới, chờ operation còn chạy
    v
  CLOSING
    | native context DeleteGlobalRef (và free resource riêng nếu có)
    v
  CLOSED (close lần sau là no-op; operation mới báo "closed")
~~~

Bảng trách nhiệm gợi ý:

| Tài nguyên | Ai tạo | Ai chịu trách nhiệm hủy | Bên mượn được làm gì |
|---|---|---|---|
| JNI local ref từ tham số | JVM/call hiện tại | JVM khi frame kết thúc; native có thể xóa sớm nếu đúng scope | Chỉ dùng trong frame/thread hợp lệ |
| Strong global ref listener | Một native context/registration | Chính context khi `close/unregister` | Được dùng khi đã bảo đảm vẫn còn sống và không bị xóa đồng thời |
| Weak global ref cache entry | Một native cache entry | Chính cache entry khi evict/close | Promote thành local trước khi dùng; chấp nhận bị clear |
| Native buffer/struct | Native allocator hoặc caller | Owner định bởi C API (`free` hoặc release function) | Không dùng sau free; không nhập nhằng với JNI ref |
| Java wrapper `AutoCloseable` | Java code | Gọi `close()` theo lexical scope `try-with-resources` | Không tái sử dụng wrapper đã đóng |

Một mẫu Java wrapper chỉ minh họa **cơ chế state**, chưa có phần triển khai registry C:

~~~java
// Fragment thiết kế: không phải chương trình runnable độc lập.
public final class Session implements AutoCloseable {
    private boolean closed;

    public synchronized void perform() {
        if (closed) {
            throw new IllegalStateException("Session closed");
        }
        // Gọi native operation dưới cùng cơ chế bảo vệ lifetime.
    }

    @Override
    public synchronized void close() {
        if (!closed) {
            // Ngăn callback/operation mới, đợi callback đang chạy
            // (nếu native registry dùng thread riêng), rồi native release.
            closed = true;
        }
    }
}
~~~

Code thực tế phải định nghĩa thứ tự khi release thất bại và cách đồng bộ xuyên cả Java lẫn native. Với call dài, không nên giữ monitor Java trong khi native đang callback trở lại Java theo đường có thể tái nhập vào cùng object và gây deadlock; thay bằng một trạng thái `OPEN/CLOSING/CLOSED`, đếm **in-flight operations**, lock/condition hoặc một execution owner thread rõ ràng. Chỉ chuyển sang CLOSED sau khi tài nguyên đã thực sự release hoặc có chiến lược retry/khôi phục có căn cứ.

Nếu Java nắm một `long nativeHandle` chứa pointer/ID của C context, `nativeHandle` **không phải jobject**. Phải ngăn stale handles và double-free: khử hiệu lực handle ở phía Java, validate ở registry native, không cho use-after-close, và cẩn thận chuyện pointer address bị allocator tái sử dụng (ABA). Một bảng handle với **generation counter** thường dễ kiểm soát hơn việc cho phép Java giữ raw address tùy ý.

**`Cleaner`** có thể làm đường dự phòng khi ứng dụng quên close, nhưng cleanup đúng phải là **explicit `close()` / `try-with-resources`** khi lifetime xác định. Không dựa vào `finalize()` (cơ chế bị loại bỏ dần), không dựa vào GC để bảo đảm thứ tự hủy giữa resource native và callback, và không để lambda/cleaning action vô tình giữ lại chính referent cần được dọn.

## 10. Đa luồng: global reference dùng qua thread, nhưng JNIEnv thì không

Một strong global ref có thể được dùng từ thread khác **khi thread đó đã attach vào JVM đúng cách và ref vẫn hợp lệ**. Tuy nhiên `JNIEnv *` là interface pointer **chỉ hợp lệ cho thread đã nhận nó**; không lưu `JNIEnv *` trong global C rồi dùng ở một worker thread khác.

Nếu native library tự tạo thread và cần gọi JNI:
1. Có `JavaVM *` hợp lệ được lưu/được cung cấp theo JNI contract.
2. Thread worker gọi `AttachCurrentThread` (hoặc daemon variant phù hợp), nhận **`JNIEnv *` của chính thread đó**.
3. Khi gọi Java, nếu đang dùng weak ref thì promote; nếu dùng shared strong global thì chặn đường xóa đồng thời hoặc tạo local borrow dưới lock.
4. Xử lý Java exception phát sinh trong callback, và giải phóng local refs phát sinh trong vòng lặp.
5. Thread được attach bởi native code phải `DetachCurrentThread` trước khi kết thúc khi đã an toàn; không gọi detach khi còn Java methods trên stack.

Đoạn mô tả attach (minh họa giao diện, không phải chương trình đa luồng độc lập):

~~~c
/* JavaVM *vm được cấp hợp lệ từ JVM và tồn tại suốt phạm vi thread. */
JNIEnv *env = NULL;
jint status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
if (status != JNI_OK) {
    /* Xử lý lỗi attach; tuyệt đối không dùng env. */
    return;
}

/* JNI calls ở thread hiện tại; cleanup refs tạo trong công việc. */

(*vm)->DetachCurrentThread(vm);
~~~

Nếu thư viện nhận callback khi close xảy ra, phải bảo đảm **close không xóa ref/context trước callback đang chạy**. Kể cả khi `jobject` global có thể dùng cross-thread, việc đọc/ghi biến C nắm nó không tự có synchronization. Thực thi JNI dưới class monitor như mục 5 chỉ bảo vệ **đường gọi qua đúng wrappers Java đó**; một native worker thread phải có synchronization ở phía C hoặc thiết kế owner thread riêng.

`JNI_OnUnload` có thể là điểm cleanup cho những resource thuộc lifecycle của library/classloader, nhưng không phải lý do bỏ qua `close/unregister` ở đối tượng có lifetime ngắn hơn. Khi native library giữ `jclass` bằng strong global, nó có thể kéo dài lifetime của class và classloader; cân nhắc điều đó khi cache.

## 11. Failure-safe cleanup: không rò rỉ khi API thất bại

### Tạo strong ref mới trước rồi mới xóa ref cũ

Mẫu an toàn trong demo:

~~~c
jobject replacement = (*env)->NewGlobalRef(env, value);
if (replacement == NULL) {
    /* Giữ held_global cũ, chuyển hoặc tạo Java exception. */
    return;
}

jobject old = held_global;
held_global = replacement;
if (old != NULL) {
    (*env)->DeleteGlobalRef(env, old);
}
~~~

Đây là **failure atomicity** ở phạm vi một slot đã được đồng bộ: nếu cấp phát ref mới thất bại, state cũ vẫn còn. Nếu xóa ref cũ trước rồi mới gọi `NewGlobalRef`, một lỗi bộ nhớ có thể khiến registry mất owner cũ dù thao tác thay thế không thành công.

### API JNI ném exception phải xử lý theo nhánh lỗi

Nhiều JNI functions có thể thiết lập **pending Java exception**. Khi đó bạn không được coi kết quả kiểu reference/primitive là thành công rồi sử dụng tiếp; hãy kiểm tra return value và `ExceptionCheck` khi API có khả năng lỗi, thực hiện cleanup phù hợp, sau đó return để JVM chuyển exception về Java. Không “nuốt” exception bằng `ExceptionClear` trừ khi contract minh bạch và bạn đã chuyển/khôi phục tình trạng lỗi có ý nghĩa.

Trong `countNonNull0`, nếu `GetObjectArrayElement` thất bại, các local refs của vòng lặp trước đã được xóa, và native method return, chuyển pending exception về Java. Nếu một hàm phức tạp đã cấp phát C heap hoặc global refs trước khi lỗi xảy ra, phải có đường cleanup cho **từng tài nguyên đã cấp phát thành công**.

### Có thể có rò rỉ cả hai phía

~~~text
Resource C context:  malloc -> context
Java reference root: NewGlobalRef -> object graph
                               |
close/unregister:
    stop new calls + wait in-flight callbacks
    DeleteGlobalRef(env, context->listener)
    context->listener = NULL
    free(context)
~~~

Nếu chỉ gọi `free(context)` mà bỏ `DeleteGlobalRef`, JNI global table vẫn giữ root trong JVM. Nếu chỉ `DeleteGlobalRef` mà bỏ `free`, native context vẫn chiếm bộ nhớ. Thứ tự thực tế phải phù hợp với invariants và locking của context; ví dụ bảng trên chỉ ra **hai nghĩa vụ giải phóng độc lập**.

## 12. Cách kiểm thử ownership và quan sát lỗi

### Test hành vi có tính quyết định

Bài demo cho các phép assert quan sát được mà **không cần chạy GC**:

1. Sau `retain(marker)`, `refersTo(marker)` trả `true`.
2. So với `new Object()` khác, `refersTo(...)` trả `false` vì kiểm tra identity.
3. Vòng lặp `countNonNull` trả đúng 2 cho mảng ba phần tử có một `null`; native xóa local ref của phần tử đã dùng.
4. Sau `release()`, `refersTo(marker)` trả `false`. Gọi `release()` thêm lần nữa không crash/double-delete.

Trong bản thử nhiều owner, bổ sung test: hủy A không ảnh hưởng B; replace lỗi thì ref cũ còn; close đồng thời với callback không use-after-delete; callback bị hủy không được gọi lại; luôn release native memory trong mọi path.

### Test môi trường JNI

Chạy:

~~~sh
java -Xcheck:jni -Djava.library.path=. \
  -cp out demo.jni.ReferenceOwnershipDemo
~~~

HotSpot có thể cảnh báo hoặc abort khi phát hiện một số misuse JNI. Đây là trợ giúp chẩn đoán; **không bảo đảm mọi misuse đều được phát hiện**, nhất là concurrency races hoặc C memory corruption. Kết hợp các phương pháp theo biểu hiện:

| Dấu hiệu | Giả thuyết cần điều tra | Cách thu hẹp |
|---|---|---|
| Memory/JVM JNI reference usage tăng sau nhiều lần đăng ký | Thiếu `DeleteGlobalRef` hoặc `DeleteWeakGlobalRef` | Đếm số lần create/delete, đối chiếu lifecycle/registration, kiểm tra JNI global roots bằng công cụ heap/profiler có hỗ trợ |
| Java listener/classloader vẫn không được GC sau unregister | Strong global root hoặc Java owner vẫn giữ object | Xem reachability từ GC roots, đặc biệt JNI global refs; không kết luận chỉ từ một lần `System.gc()` |
| Crash/corrupted reference sau callback | Local ref đã hết hạn, global bị xóa sớm, thread chưa attach, hoặc sai ABI | Đối chiếu loại ref/lifetime/thread; chạy `-Xcheck:jni` và trace native |
| Local reference table overflow khi xử lý nhiều object | Mỗi vòng lặp tạo refs nhưng không xóa | `DeleteLocalRef` ở vòng lặp, hoặc `PushLocalFrame/PopLocalFrame` |
| Chạy đúng đơn luồng nhưng crash khi shutdown | Callback/operation đang dùng resource trong lúc close | Kiểm thử race có barrier/latch, lock và in-flight counter |
| Heap native tăng dù global refs đã xóa | Native allocation không được free | So đối xứng malloc/free và release của từng native resource |
| Cache weak lúc được lúc không | GC đã clear referent | Xem code promote; xử lý `NewLocalRef(...) == NULL` như tình huống bình thường |

Không viết test mặc định **assert GC phải chạy trong N giây**, vì tính quyết định của GC không nằm trong contract ứng dụng. Test ownership bằng state/đối xứng create–release và kiểm tra truy cập sau close; dùng GC logs, heap dump và stress test để **chẩn đoán** thêm, không làm chứng cứ duy nhất.

## 13. Checklist thiết kế trước khi publish native API

- [ ] Mỗi JNI reference đã phân loại **local / global / weak global**; không cất local quá frame.
- [ ] Mỗi `NewGlobalRef` có đường `DeleteGlobalRef`; mỗi `NewWeakGlobalRef` có `DeleteWeakGlobalRef`. Đường lỗi, replace và shutdown đều được tính.
- [ ] Nếu dùng weak: luôn tạo strong local/global tạm để sử dụng; xử lý kết quả `NULL` của promote.
- [ ] Không dùng handle sau `DeleteLocalRef`/`DeleteGlobalRef`/`DeleteWeakGlobalRef`; không dựa vào giá trị bit của `jobject` để so identity.
- [ ] Loop tạo local refs có cleanup sớm, hoặc frame con với capacity và cleanup.
- [ ] Owner và borrower có tên rõ; `close/unregister` là hành động tường minh, idempotent, ngăn operation mới.
- [ ] Không tồn tại race giữa callback/đọc global và delete; có protocol đồng bộ hoặc local borrow đã được bảo vệ.
- [ ] `JNIEnv *` chỉ dùng trong thread tạo nó; native worker phải attach/detach đúng.
- [ ] Native memory và JNI ref là hai tài nguyên riêng; cả hai có cleanup cân đối.
- [ ] Java exceptions được truyền/biến đổi đúng; không bỏ ref cũ khi việc tạo ref thay thế thất bại.
- [ ] Kiểm thử kết quả và lifecycle xác định, không cần giả định thời điểm GC; dùng `-Xcheck:jni` khi có thể.

## 14. Câu hỏi tự đánh giá

**Câu 1.** Một native method nhận `jobject listener`, lưu trực tiếp vào `static jobject saved` để callback sau 10 phút. Java vẫn giữ listener trong một field. Code có đúng không?  
**Trả lời:** Không. `listener` ở JNI method là local handle và hết lifetime khi native frame kết thúc. Object vẫn sống không hợp thức hóa handle cũ. Cần tạo strong global ref (hoặc weak global + promote tùy semantics) và cleanup khi unregister.

**Câu 2.** Sau `DeleteGlobalRef`, object Java chắc chắn bị thu hồi ngay?  
**Trả lời:** Không. Việc delete chỉ loại bỏ một JNI strong root. Other Java/JNI roots có thể vẫn giữ object; GC hoạt động không đồng bộ và không có cam kết thời điểm cụ thể.

**Câu 3.** JNI weak global ref còn khác null, ta có thể check một lần rồi gọi method sau đó không?  
**Trả lời:** Không đủ. GC có thể clear referent giữa kiểm tra và dùng. Phải `NewLocalRef(env, weak)` (hoặc `NewGlobalRef`) để lấy strong ref tạm, kiểm tra result và xóa ref mới khi xong.

**Câu 4.** Vì sao `jobject` global hợp lệ dùng cross-thread mà `JNIEnv *` thì không?  
**Trả lời:** Global reference thuộc bảng tham chiếu toàn JVM với lifetime do owner quản lý; `JNIEnv *` là interface pointer có trạng thái/contract gắn với thread. Worker thread cần attach và nhận env của chính nó.

**Câu 5.** Một native context chứa `jobject global` và một buffer `malloc`. Chỉ `free(context)` có đủ không?  
**Trả lời:** Không. Phải `DeleteGlobalRef` theo JNI trước khi mất handle; đồng thời giải phóng buffer/context bằng allocator phù hợp, sau khi không còn callback sử dụng.

**Câu 6.** Hai Java threads gọi `close` và `call` đồng thời vào cùng native session. Vì sao kiểm tra `if (!closed)` bên Java chưa chắc đủ?  
**Trả lời:** Nếu native call tiếp tục chạy sau khi Java kiểm tra, close có thể xóa global ref/context giữa call. Cần atomic acquire/borrow hoặc in-flight counter + synchronization xuyên đúng phạm vi; close chỉ release khi không còn borrower.

## 15. Ghi nhớ và nguồn tham khảo

**Điểm mấu chốt:** thiết kế JNI reference luôn gồm hai phần: **lifetime của handle** và **reachability của Java referent**. Local ref phải ở trong frame/thread hợp lệ; strong global là tài nguyên phải delete và có thể giữ object sống; weak global không giữ object sống nhưng vẫn phải giải phóng handle và promote an toàn khi dùng. Một owner chịu trách nhiệm release, mọi borrower có ranh giới rõ, còn close phải phối hợp với callback/concurrency để không có use-after-delete.

Tài liệu kỹ thuật chính thức để đối chiếu: [Oracle JNI Design Overview — Referencing Java Objects](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html), [Oracle JNI Functions — Local/Global/Weak Global References, NewLocalRef và Push/PopLocalFrame](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html), [Oracle JNI Invocation API — AttachCurrentThread và DetachCurrentThread](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html). Đối với hệ sinh thái Android, [Android NDK JNI tips](https://developer.android.com/ndk/guides/jni-tips) có thêm ví dụ thực tế về lifetime của references; quy tắc JNI vẫn cần đối chiếu theo đặc tả JVM/toolchain đang sử dụng.