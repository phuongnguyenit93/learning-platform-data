# Truyền ngoại lệ về Java hoặc xóa rồi xử lý theo chính sách tường minh trong JNI

## 1. Mục tiêu và mô hình lỗi ở ranh giới Java ↔ native

Trong Java, khi một phương thức ném `Throwable`, điều khiển được chuyển sang khối `catch` thích hợp hoặc tiếp tục lan truyền trên call stack. Nhưng khi mã C/C++ gọi vào Java qua **Java Native Interface (JNI)**, một Java exception **không tự động thực hiện bước nhảy điều khiển trong C**. JVM ghi nhận một **pending exception** trên **thread hiện tại**; mã native vẫn tiếp tục chạy C nếu bạn không tự kiểm tra và rẽ nhánh.

Hai chính sách chính mà lập trình viên JNI phải chọn **tường minh** là:

1. **Truyền ngoại lệ về Java (propagate):** giữ nguyên pending exception, dọn tài nguyên bằng các thao tác được phép, **trả quyền điều khiển từ native method về JVM**. JVM sẽ để Java code thấy exception và xử lý bằng `catch` hoặc tiếp tục truyền lên.
2. **Xóa rồi xử lý (clear and handle):** xác định lỗi nào **được phép phục hồi** hoặc cần **dịch sang exception nghiệp vụ**; dùng `ExceptionClear` để bỏ trạng thái pending trước khi gọi các JNI API thông thường, sau đó trả fallback, ghi nhận thất bại theo hợp đồng, hoặc tạo/`Throw` một exception mới. Những lỗi **không thuộc chính sách** phải tiếp tục được truyền đi, không được âm thầm nuốt.

**Bài học này không khuyến khích “cứ gặp lỗi là ExceptionClear”.** Xóa ngoại lệ khi không có quy tắc phục hồi là làm mất tín hiệu lỗi, dễ tạo dữ liệu sai hoặc khiến hệ thống chạy tiếp trong trạng thái không hợp lệ.

Sau bài này, bạn sẽ phân biệt được `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `Throw`, `ThrowNew`, nhận diện các JNI calls được phép khi đang có ngoại lệ pending, viết đường cleanup an toàn và chạy một ví dụ Java 17 + C cho cả ba tình huống: **propagate**, **fallback có chọn lọc**, **translate có giữ nguyên cause**.

## 2. Pending exception là gì?

Xét lời gọi JNI kiểu C:

~~~c
jint result = (*env)->CallStaticIntMethod(
    env, clazz, methodId, divisor
);
~~~

Nếu Java method được gọi ném `ArithmeticException`, JVM ghi exception đang chờ trên thread của lời gọi. **C code không tự dừng** tại dòng này. Giá trị trả về của `CallStaticIntMethod` **không được dùng như kết quả tính toán hợp lệ** khi có exception pending; phải kiểm tra ngay:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* Đang có Java exception pending. */
    return 0;  /* Ví dụ trong JNI method trả về jint. */
}
return result;
~~~

Đoạn trên chỉ là **trích đoạn** trong JNI method có `JNIEnv *env` và `methodId` hợp lệ, chưa phải chương trình độc lập.

Tư duy đúng:

~~~text
Java caller
   |
   | gọi nativeMethod(...)
   v
C/JNI nativeMethod
   |
   | CallStaticIntMethod(...) gọi Java helper
   v
Java helper ném ArithmeticException
   |
   v
Trở lại mã C, thread có pending exception
   |
   +-- Chính sách A: cleanup được phép → return về JVM
   |       |
   |       v
   |     Java caller catch ArithmeticException
   |
   +-- Chính sách B: nhận diện lỗi → ExceptionClear
           |
           +-- lỗi dự kiến → trả fallback hợp lệ
           |
           +-- lỗi cần dịch → tạo exception mới với cause cũ → Throw
           |
           +-- lỗi khác → Throw lại original → return về Java
~~~

**Pending exception không phải một con trỏ lỗi C, mã trả về `errno`, hay C++ exception.** Đây là trạng thái exception của JVM theo thread JNI hiện tại. C++ `try/catch` không tự bắt được Java exception pending do `Call<Type>Method`; và không nên để một C++ exception bất ngờ thoát xuyên qua JNI boundary.

### 2.1. Trả `0`/`NULL` lúc có pending exception có làm “nuốt lỗi” không?

Không. Nếu native method trả về JVM **khi exception vẫn pending**, Java sẽ nhận exception chứ không coi `0` hay `NULL` là một kết quả trả về thông thường.

Ví dụ một JNI C function trả `jint` có thể viết:

~~~c
if ((*env)->ExceptionCheck(env)) {
    return 0;  /* Giá trị placeholder ở ABI C; Java sẽ thấy exception. */
}
~~~

Trái lại, nếu đã gọi `ExceptionClear` rồi trả `0`, thì **không còn exception pending**. Java có thể nhận `0` như một kết quả hợp lệ. Vì vậy, sau khi clear, phải có **hợp đồng nghiệp vụ cụ thể**: fallback có ý nghĩa, trạng thái lỗi riêng hoặc một exception khác thay thế.

## 3. Các JNI API liên quan đến ngoại lệ

| JNI API | Tác dụng | Thay đổi pending exception? |
|---|---|---|
| `ExceptionCheck(env)` | Kiểm tra có exception đang chờ hay không, trả `JNI_TRUE`/`JNI_FALSE` | **Không** clear; không tạo local reference cho throwable |
| `ExceptionOccurred(env)` | Lấy `jthrowable` local reference tới exception đang chờ (hoặc `NULL` nếu không có) | **Không** clear |
| `ExceptionClear(env)` | Xóa trạng thái exception đang chờ trên thread | **Có**; dùng trước khi xử lý lỗi bằng JNI APIs thông thường |
| `ExceptionDescribe(env)` | In thông tin lỗi và stack trace ra kênh chẩn đoán | **Có: nó clear pending exception như một side effect!** |
| `Throw(env, throwable)` | Đặt một object `Throwable` sẵn có làm exception cần ném | Tạo trạng thái pending; gọi khi không còn exception pending |
| `ThrowNew(env, clazz, message)` | Tạo và ném exception từ một class `Throwable` và message (modified UTF-8) | Tạo trạng thái pending; nên chuẩn bị class/call trong trạng thái hợp lệ |

Phân biệt hai thao tác hay bị nhầm:

~~~c
/* Không tạo local ref, phù hợp khi chỉ muốn biết có lỗi hay không. */
jboolean hasError = (*env)->ExceptionCheck(env);

/* Tạo một jthrowable local ref nếu đang có exception. */
jthrowable error = (*env)->ExceptionOccurred(env);
~~~

`ExceptionOccurred` được dùng khi cần **kiểm tra loại exception, ghi nguyên nhân hoặc rethrow**. Nếu lấy được local handle thì phải quản lý vòng đời; gọi `DeleteLocalRef(env, error)` khi không còn dùng, hoặc để JVM thu hồi khi native method kết thúc.

**Cảnh báo quan trọng:** Không dùng `ExceptionDescribe` như một “logger không tác dụng phụ” rồi `return` và mong Java bắt nguyên exception. Theo đặc tả JNI, `ExceptionDescribe` **in và clear** pending exception. Nếu chỉ cần biết có lỗi, dùng `ExceptionCheck`; nếu cần giữ nguyên nguyên nhân, dùng `ExceptionOccurred` rồi xử lý theo chính sách đã chọn.

## 4. Quy tắc “không gọi JNI bừa khi exception pending”

Khi đã có Java exception pending, **phần lớn JNI APIs không được phép gọi**; một số API dùng để kiểm tra trạng thái và giải phóng tài nguyên là ngoại lệ.

Những nhóm **được phép** theo đặc tả JNI gồm:

- Kiểm tra và điều khiển exception: `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- Giải phóng references: `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- Release vùng truy cập chuỗi/mảng: `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- Dọn trạng thái/scope JNI: `MonitorExit`, `PushLocalFrame`, `PopLocalFrame` và `DetachCurrentThread` theo điều kiện của các API đó.

Danh sách này **không có** `FindClass`, `GetMethodID`, `GetFieldID`, `NewStringUTF`, `NewObject`, `CallObjectMethod`, `CallStaticIntMethod` hay `ThrowNew`. Nếu muốn gọi các API thông thường để phục hồi hoặc tạo exception khác, **phải clear exception trước**, sau đó kiểm tra lỗi mới có thể xuất hiện.

Ví dụ sai (**không chạy**):

~~~c
/* SAI: sau một CallStaticIntMethod ném exception,
   tiếp tục gọi FindClass khi exception vẫn pending. */
jint answer = (*env)->CallStaticIntMethod(env, clazz, methodId, 0);
jclass otherClass = (*env)->FindClass(env, "java/lang/String");
return answer;
~~~

Ví dụ đúng về mặt **đường truyền nguyên lỗi**:

~~~c
jint answer = (*env)->CallStaticIntMethod(env, clazz, methodId, 0);
if ((*env)->ExceptionCheck(env)) {
    /* Cleanup refs, release buffer nếu có; KHÔNG clear. */
    return 0;
}
return answer;
~~~

Đây đều là trích đoạn trong JNI method, không phải tệp C độc lập. Trong mã thực tế, luôn kiểm tra kết quả của bước lấy `methodId` trước đó.

**Khi có tài nguyên native đã acquire:** dọn bằng đúng cơ chế release được phép khi pending; ví dụ `ReleaseStringUTFChars` hoặc `DeleteLocalRef`. `ExceptionClear` **không** giải phóng `malloc` buffer, file descriptor, JNI global reference hay local frame. Phải quản lý những tài nguyên ấy riêng.

## 5. Chính sách A: giữ pending và truyền lỗi gốc về Java

Đây là lựa chọn mặc định khi JNI chỉ là một lớp cầu nối và **không có quy tắc phục hồi rõ ràng**.

Mẫu trong JNI method trả `jint`:

~~~c
jmethodID id = (*env)->GetStaticMethodID(
    env, clazz, "divide", "(I)I"
);
if (id == NULL) {
    /* Thường có pending NoSuchMethodError: để Java nhận lỗi. */
    return 0;
}

jint value = (*env)->CallStaticIntMethod(env, clazz, id, 0);
if ((*env)->ExceptionCheck(env)) {
    /* Java helper đã ném lỗi; dọn tài nguyên rồi return.
       Không gọi ExceptionClear. */
    return 0;
}
return value;
~~~

**Chỉ là trích đoạn**, code chạy đầy đủ ở phần thực hành. Lưu ý:

1. `GetStaticMethodID` có thể thất bại và thường để lại pending Java exception; không gọi `CallStaticIntMethod` khi `id == NULL`.
2. `CallStaticIntMethod` có thể gọi vào Java method ném lỗi. C code cần kiểm tra `ExceptionCheck` **trước khi sử dụng kết quả**.
3. Nếu có lỗi, `return` từ native method để JVM chuyển exception về phía Java. Java `catch` có thể xử lý đúng **cùng loại và nội dung lỗi gốc**; không cần tạo thêm exception ở JNI.
4. Việc gọi `return 0` không phải thành công giả, miễn pending exception vẫn còn. Nếu clear trước khi return, ý nghĩa hoàn toàn khác.

Ví dụ Java caller:

~~~java
try {
    int value = NativeExceptionPolicy.propagate(0);
    System.out.println(value); // Không chạy nếu Java exception được truyền về.
} catch (ArithmeticException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
~~~

Đây là trích đoạn từ chương trình sẽ viết ở phần 8. Java nhận và xử lý exception ở vị trí phù hợp, trong khi JNI chỉ chịu trách nhiệm **bảo toàn và lan truyền**.

## 6. Chính sách B: clear rồi trả fallback — nhưng chỉ cho lỗi dự kiến

Có lúc Java layer quy định một lỗi **có thể phục hồi**: ví dụ phép tính thử bị chia cho 0 được phép dùng một giá trị mặc định. Với yêu cầu ấy, native layer có thể:

1. Xác định loại lỗi được phép phục hồi, chẳng hạn chỉ `ArithmeticException`.
2. **Giữ một local reference tới throwable** bằng `ExceptionOccurred` khi lỗi còn pending.
3. Gọi `ExceptionClear` trước khi sử dụng `IsInstanceOf` hoặc bất kỳ JNI API thông thường nào.
4. Nếu đúng loại dự kiến: cleanup refs, trả fallback theo hợp đồng.
5. Nếu là loại khác (ví dụ `OutOfMemoryError`, `NoSuchMethodError`): **rethrow nguyên exception** bằng `Throw`, rồi return.

Sơ đồ:

~~~text
CallStaticIntMethod -> pending exception?
    |
    +-- Không --> dùng kết quả tính toán
    |
    +-- Có --> original = ExceptionOccurred()
               |
               v
            ExceptionClear()
               |
               v
         IsInstanceOf(original, ArithmeticException)
               |
               +-- true  --> cleanup --> return fallback
               |
               +-- false --> Throw(original) --> cleanup --> return
                              (Java vẫn nhận lỗi không mong đợi)
~~~

Tại sao **không clear vô điều kiện**? Một exception ngoài dự kiến có thể báo lỗi cấu hình class loader, thiếu phương thức, tài nguyên cạn kiệt, bug trong Java helper hay trạng thái không nhất quán. Nếu nuốt nó và trả fallback, hệ thống có thể tiếp tục với dữ liệu bị hỏng.

### 6.1. Vì sao phải lấy throwable trước khi clear?

`ExceptionClear` chỉ xóa **trạng thái đang ném exception**; nó không tự tạo một bản sao hoặc bảo đảm bạn có thể lấy lại lỗi đã clear. Vì thế, khi cần kiểm tra hoặc rethrow lỗi, hãy lấy reference trước:

~~~c
jthrowable original = (*env)->ExceptionOccurred(env);
if (original == NULL) {
    /* Không có throwable để phân tích; cần quyết định lỗi theo ngữ cảnh. */
    return 0;
}

(*env)->ExceptionClear(env);

/* Lúc này mới gọi các JNI API thông thường trên original. */
/* Cuối cùng: DeleteLocalRef(env, original). */
~~~

Đây là trích đoạn. `ExceptionOccurred` trả local reference; sau khi clear, `original` vẫn tham chiếu object throwable cho tới khi local ref hết hiệu lực. Nhưng **đừng giữ `original` làm biến global C** để dùng sau khi native method trả về; muốn lưu qua nhiều calls cần global reference được quản lý đúng.

### 6.2. Vì sao nên lấy sẵn class cho phép phục hồi trước Java call?

`IsInstanceOf` cần một `jclass`. `FindClass` không được gọi khi còn pending exception. Vì vậy, chương trình thực hành **tra cứu `java/lang/ArithmeticException` trước khi gọi Java helper**, rồi chỉ kiểm tra loại throwable sau khi clear.

Cách này phân biệt được “lỗi dự kiến thuộc danh sách cho phép” với các lỗi khác mà không gọi JNI sai trong trạng thái pending.

## 7. Chính sách C: clear rồi chuyển thành exception khác và giữ nguyên cause

Đôi khi lỗi ở tầng thấp không phù hợp với API public: một component nhận đối số “không hợp lệ” có thể muốn báo `IllegalArgumentException` cho Java caller, dù Java helper nội bộ ném `ArithmeticException`.

Nếu **đổi loại lỗi**, nên giữ **chuỗi nguyên nhân (cause)** thay vì phá hủy lịch sử lỗi:

~~~text
ArithmeticException("divide by zero")    (lỗi gốc)
             |
             v  JNI capture -> clear -> tạo IllegalArgumentException
IllegalArgumentException("divisor must not be zero")
             |
             v  cause = ArithmeticException("divide by zero")
Java catch IllegalArgumentException
   -> getCause() vẫn truy được exception gốc
~~~

JNI có thể:

1. Tra cứu class đích `java/lang/IllegalArgumentException` và constructor `(Ljava/lang/String;Ljava/lang/Throwable;)V` trong trạng thái chưa có pending exception.
2. Gọi Java helper; nếu lỗi thuộc loại cần dịch, `ExceptionOccurred` lấy `jthrowable original` rồi `ExceptionClear`.
3. `NewStringUTF` tạo message; `NewObject` tạo `IllegalArgumentException(message, original)`; `Throw` đặt exception mới làm pending; sau đó cleanup các local references (được phép lúc pending) và return.
4. Nếu exception gốc không thuộc loại đã quy định: `Throw(original)` để truyền nguyên lỗi, **không dịch tất cả ngoại lệ**.
5. Nếu việc xây exception mới thất bại (chẳng hạn `OutOfMemoryError`), không được tùy tiện xóa tiếp lỗi mới rồi tiếp tục như thành công.

**Không thể dùng `ThrowNew` một cách tùy ý khi exception khác còn pending.** Nếu muốn thay lỗi, hãy xử lý/clear lỗi cũ theo chính sách trước. `ThrowNew` thuận tiện cho exception với message đơn giản, nhưng nếu cần giữ cause, dùng constructor nhận `Throwable` hoặc nối nguyên nhân hợp lệ qua API Java/JNI.

Cách đơn giản hơn về kiến trúc, khi JNI không cần xử lý lỗi, là **để nguyên exception đi về Java rồi dịch tại Java boundary**:

~~~java
static int api(int divisor) {
    try {
        return NativeExceptionPolicy.propagate(divisor);
    } catch (ArithmeticException ex) {
        throw new IllegalArgumentException("divisor must not be zero", ex);
    }
}
~~~

Đoạn này **minh họa**, không phải method thuộc tệp thực hành; ở phần 8 ta sẽ thử cả việc dịch ngay trong C. Dịch ở Java thường ít rủi ro hơn vì có sẵn `try/catch`, constructor và quản lý tài nguyên tự động. Chỉ dịch ở native khi boundary/hợp đồng kiến trúc yêu cầu.

## 8. Ví dụ hoàn chỉnh: Java 17 + JNI C với ba chính sách

Ta tạo một class Java, một thư viện JNI C và **ba native methods**. Java helper `divide(int divisor)` cố tình ném lỗi khi mẫu số bằng 0 để so sánh ba chính sách.

Cấu trúc thư mục:

~~~text
jni-exception-policy/
├── NativeExceptionPolicy.java
├── NativeExceptionPolicy.h       (javac -h tạo)
├── nativeexceptionpolicy.c
├── NativeExceptionPolicy.class   (javac tạo)
└── thư viện native              (compiler tạo theo hệ điều hành)
~~~

### 8.1. Java — tệp `NativeExceptionPolicy.java`

~~~java
public final class NativeExceptionPolicy {
    static {
        System.loadLibrary("nativeexceptionpolicy");
    }

    private NativeExceptionPolicy() {
    }

    private static int divide(int divisor) {
        if (divisor == 0) {
            throw new ArithmeticException("divide by zero");
        }
        return 20 / divisor;
    }

    public static native int propagate(int divisor);

    public static native int recover(int divisor, int fallback);

    public static native int translate(int divisor);

    public static void main(String[] args) {
        System.out.println("normal propagation = " + propagate(4));

        try {
            propagate(0);
        } catch (ArithmeticException ex) {
            System.out.println(
                "propagated = " + ex.getClass().getSimpleName()
                + ": " + ex.getMessage()
            );
        }

        System.out.println("normal fallback = " + recover(4, -1));
        System.out.println("fallback = " + recover(0, -1));
        System.out.println("normal translation = " + translate(4));

        try {
            translate(0);
        } catch (IllegalArgumentException ex) {
            System.out.println(
                "translated = " + ex.getClass().getSimpleName()
                + ": " + ex.getMessage()
            );
            Throwable cause = ex.getCause();
            System.out.println(
                "cause = " + cause.getClass().getSimpleName()
                + ": " + cause.getMessage()
            );
        }
    }
}
~~~

Đây là tệp Java **đầy đủ, biên dịch bằng JDK 17+**. Method `divide` là `private static` nhưng vẫn có thể được JNI tìm và gọi qua `GetStaticMethodID`, miễn đúng tên `divide` và descriptor `(I)I`. Không có lời gọi Java trực tiếp từ `main` vào helper; ba JNI methods tự gọi helper bằng `CallStaticIntMethod`.

Khi `divisor == 0`, helper ném `ArithmeticException("divide by zero")`. Khi `divisor == 4`, nó trả `20 / 4 = 5`. Số được chọn nhỏ, tránh các vấn đề tràn số của phép chia nguyên trong ví dụ.

### 8.2. Sinh header bằng JDK

Chạy trong thư mục chứa tệp Java:

~~~bash
javac -h . NativeExceptionPolicy.java
~~~

JDK tạo `NativeExceptionPolicy.class` và `NativeExceptionPolicy.h`. Các khai báo hàm cốt lõi trong header có dạng:

~~~c
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_propagate
  (JNIEnv *, jclass, jint);

JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_recover
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_translate
  (JNIEnv *, jclass, jint);
~~~

Đây là **trích đoạn** header; header thật còn include guard và `#include <jni.h>`. Cả ba Java methods là `static native`, nên tham số JNI ẩn thứ hai là `jclass`. Nếu bỏ `static` trong Java, chữ ký C phải thay bằng `jobject`.

### 8.3. C — tệp `nativeexceptionpolicy.c`

~~~c
#include "NativeExceptionPolicy.h"

/* Trả kết quả bình thường, hoặc để pending Java exception nguyên vẹn. */
static jint callDivide(JNIEnv *env, jclass clazz, jint divisor) {
    jmethodID method = (*env)->GetStaticMethodID(
        env, clazz, "divide", "(I)I"
    );
    if (method == NULL) {
        /* Giữ pending exception, chẳng hạn NoSuchMethodError. */
        return 0;
    }

    return (*env)->CallStaticIntMethod(
        env, clazz, method, divisor
    );
}

/* A. Không clear: truyền Java exception gốc về Java caller. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_propagate(
    JNIEnv *env, jclass clazz, jint divisor
) {
    jint value = callDivide(env, clazz, divisor);
    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Pending exception vẫn còn. */
    }
    return value;
}

/* B. Chỉ hồi phục ArithmeticException bằng fallback tường minh. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_recover(
    JNIEnv *env, jclass clazz, jint divisor, jint fallback
) {
    /* Tra class để phân loại TRƯỚC lời gọi có thể ném lỗi. */
    jclass arithmetic = (*env)->FindClass(
        env, "java/lang/ArithmeticException"
    );
    if (arithmetic == NULL) {
        return 0; /* Giữ lỗi từ FindClass. */
    }

    jint value = callDivide(env, clazz, divisor);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return value;
    }

    /* Capture gốc khi đang pending; chưa được gọi IsInstanceOf. */
    jthrowable original = (*env)->ExceptionOccurred(env);
    if (original == NULL) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    (*env)->ExceptionClear(env);

    jboolean expected = (*env)->IsInstanceOf(
        env, original, arithmetic
    );
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0; /* Giữ lỗi mới nếu bước kiểm tra thất bại. */
    }

    if (!expected) {
        /* Không được nuốt exception ngoài chính sách phục hồi. */
        (void) (*env)->Throw(env, original);
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    /* Đây là ArithmeticException được cho phép phục hồi. */
    (*env)->DeleteLocalRef(env, original);
    (*env)->DeleteLocalRef(env, arithmetic);
    return fallback;
}

/* C. Dịch ArithmeticException -> IllegalArgumentException, giữ cause. */
JNIEXPORT jint JNICALL Java_NativeExceptionPolicy_translate(
    JNIEnv *env, jclass clazz, jint divisor
) {
    jclass arithmetic = (*env)->FindClass(
        env, "java/lang/ArithmeticException"
    );
    if (arithmetic == NULL) {
        return 0;
    }

    jclass illegal = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException"
    );
    if (illegal == NULL) {
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jmethodID ctor = (*env)->GetMethodID(
        env, illegal, "<init>",
        "(Ljava/lang/String;Ljava/lang/Throwable;)V"
    );
    if (ctor == NULL) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jint value = callDivide(env, clazz, divisor);
    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return value;
    }

    jthrowable original = (*env)->ExceptionOccurred(env);
    if (original == NULL) {
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    (*env)->ExceptionClear(env);

    jboolean expected = (*env)->IsInstanceOf(
        env, original, arithmetic
    );
    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    if (!expected) {
        (void) (*env)->Throw(env, original);
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jstring message = (*env)->NewStringUTF(
        env, "divisor must not be zero"
    );
    if (message == NULL) {
        /* Nếu OOM khi tạo message, để lỗi mới lan về Java. */
        (*env)->DeleteLocalRef(env, original);
        (*env)->DeleteLocalRef(env, illegal);
        (*env)->DeleteLocalRef(env, arithmetic);
        return 0;
    }

    jthrowable translated = (jthrowable) (*env)->NewObject(
        env, illegal, ctor, message, original
    );
    if (translated != NULL && !(*env)->ExceptionCheck(env)) {
        (void) (*env)->Throw(env, translated);
    }

    /* DeleteLocalRef được phép khi đang có pending exception. */
    if (translated != NULL) {
        (*env)->DeleteLocalRef(env, translated);
    }
    (*env)->DeleteLocalRef(env, message);
    (*env)->DeleteLocalRef(env, original);
    (*env)->DeleteLocalRef(env, illegal);
    (*env)->DeleteLocalRef(env, arithmetic);
    return 0;
}
~~~

Đây là **toàn bộ tệp C** của ví dụ, không phải pseudocode. `#include "NativeExceptionPolicy.h"` đảm bảo các hàm export có prototype đúng theo header JNI sinh từ mã Java.

Đọc ba điểm then chốt:

- **`propagate`:** nếu `CallStaticIntMethod` gây lỗi, C trả về **mà không clear**. Java caller bắt đúng `ArithmeticException`.
- **`recover`:** tra `ArithmeticException` trước; capture `original` rồi clear; phân loại bằng `IsInstanceOf`. Chỉ loại đúng mới trả `fallback`, loại khác được `Throw` lại để Java nhìn thấy. Kết quả bình thường được trả nguyên vẹn khi không có exception.
- **`translate`:** tra cả class exception đích và constructor trước khi gọi helper; khi nhận đúng loại lỗi thì clear, tạo `IllegalArgumentException(String, Throwable)` với `original` làm **cause**, dùng `Throw` để đặt exception mới pending. Nếu tạo chuỗi hoặc exception mới thất bại, giữ lỗi mới phát sinh thay vì trả “thành công giả”.

Trong các nhánh đã có pending exception, chỉ có `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear` và `DeleteLocalRef` được sử dụng. Các bước như `IsInstanceOf`, `NewStringUTF`, `NewObject` và `Throw` được thực hiện **sau khi đã clear** và sau khi kiểm tra trạng thái hợp lệ.

Đây là ví dụ học thuật với điều kiện lỗi dự kiến `divisor == 0`. Trong hệ thống thực tế, nên quy định rõ loại lỗi có thể phục hồi; không tự động coi `OutOfMemoryError`, `LinkageError`, `NoSuchMethodError` hay lỗi dữ liệu không nhất quán là trường hợp có thể bỏ qua.

### 8.4. Biên dịch native library và chạy trên từng hệ điều hành

Cần JDK 17+ có `jni.h`, compiler C, biến môi trường `JAVA_HOME` chỉ tới JDK phù hợp với JVM sẽ chạy, và thư viện được biên dịch cho đúng hệ điều hành/kiến trúc/ABI.

**Linux với GCC:**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativeexceptionpolicy.c -o libnativeexceptionpolicy.so

java -Djava.library.path=. NativeExceptionPolicy
~~~

**macOS với Clang:**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  nativeexceptionpolicy.c -o libnativeexceptionpolicy.dylib

java -Djava.library.path=. NativeExceptionPolicy
~~~

**Windows với MSVC trong Developer Command Prompt (`cmd.exe`):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativeexceptionpolicy.c /Fe:nativeexceptionpolicy.dll

java -Djava.library.path=. NativeExceptionPolicy
~~~

Chỉ chạy **một bộ lệnh** tương ứng hệ điều hành sau khi đã chạy `javac -h . NativeExceptionPolicy.java`. Đặt `-Djava.library.path=.` trước tên class. Tên logic `System.loadLibrary("nativeexceptionpolicy")` tương ứng với `nativeexceptionpolicy.dll` (Windows), `libnativeexceptionpolicy.so` (Linux) hay `libnativeexceptionpolicy.dylib` (macOS).

**Stdout chính xác khi biên dịch và nạp thành công:**

~~~text
normal propagation = 5
propagated = ArithmeticException: divide by zero
normal fallback = 5
fallback = -1
normal translation = 5
translated = IllegalArgumentException: divisor must not be zero
cause = ArithmeticException: divide by zero
~~~

Giải thích từng dòng:

1. `propagate(4)` không gây lỗi; Java helper trả `20/4 = 5`.
2. `propagate(0)` tạo pending `ArithmeticException`, JNI không clear nên Java `catch` nhận lỗi gốc.
3. `recover(4, -1)` thành công bình thường nên trả 5.
4. `recover(0, -1)` chỉ clear `ArithmeticException` đã được chính sách cho phép, rồi trả `-1` như fallback.
5. `translate(4)` thành công bình thường nên trả 5.
6. `translate(0)` chuyển đúng lỗi đã xác nhận thành `IllegalArgumentException` với message nghiệp vụ.
7. `getCause()` của exception mới vẫn trả `ArithmeticException("divide by zero")`, giúp giữ dấu vết nguồn gốc.

**Phân biệt rõ:** Fallback trong ví dụ **không phải** `0` trả về do pending exception; đó là **`-1` được quyết định tường minh bởi Java caller**. Nếu JVM gặp một lỗi khác không được cho phép phục hồi, C sẽ để lỗi đó truyền về Java thay vì lặng lẽ trả `-1`.

## 9. Sơ đồ trạng thái: tại đâu được gọi API JNI thông thường?

~~~text
STATE: CLEAR (không pending exception)
   |
   +-- GetStaticMethodID / CallStaticIntMethod / FindClass ...
   |          |
   |          +-- thành công --> tiếp tục
   |          |
   |          +-- thất bại --> STATE: PENDING
   |                                  |
   |                                  +-- Policy PROPAGATE
   |                                  |      cleanup hợp lệ -> return JNI
   |                                  |      Java catch exception gốc
   |                                  |
   |                                  +-- Policy RECOVER/TRANSLATE
   |                                         ExceptionOccurred: lấy original
   |                                         ExceptionClear: STATE=CLEAR
   |                                             |
   |                                             +-- classify exception
   |                                             +-- fallback
   |                                             +-- Throw(original) -> PENDING
   |                                             +-- NewObject + Throw(new) -> PENDING
   |
   +-- return bình thường khi không pending
~~~

Không dùng `ThrowNew`/`FindClass`/`NewObject`/`Call...Method` trong **STATE: PENDING**. Trước khi muốn gọi chúng để phục hồi, phải clear có chủ ý. Với policy propagate, hạn chế làm thêm gì ngoài **cleanup có kiểm soát** và trả về JVM.

Đừng suy ra từ việc một giá trị JNI khác `NULL` rằng mọi lời gọi Java đều không gây exception: `Call<Type>Method` gọi Java method có thể ném lỗi bất kỳ, nên **kiểm tra `ExceptionCheck`** sau lời gọi nếu kết quả được sử dụng.

## 10. Vòng đời local reference và cleanup khi lỗi pending

Đường lỗi cần dọn tài nguyên đã acquire trước đó. Một số thao tác release được cho phép trong trạng thái pending:

~~~c
/* Trích đoạn: giả sử resource đã được acquire thành công. */
if ((*env)->ExceptionCheck(env)) {
    if (utfChars != NULL) {
        (*env)->ReleaseStringUTFChars(env, inputString, utfChars);
    }
    if (temporaryRef != NULL) {
        (*env)->DeleteLocalRef(env, temporaryRef);
    }
    return 0;
}
~~~

Đây là **trích đoạn minh họa**: `utfChars`, `inputString` và `temporaryRef` cần được định nghĩa, cấp phát/lấy hợp lệ trước đó; không ghép nguyên đoạn vào tệp `nativeexceptionpolicy.c`.

Nếu bạn đã `PushLocalFrame` thành công, `PopLocalFrame(env, NULL)` cũng là cách cleanup được phép khi exception pending. Không pop một frame chưa push thành công. Nếu đã `GetPrimitiveArrayCritical` hoặc `GetStringCritical`, phải tuân thủ các hạn chế riêng của critical region và release đúng cách; không gọi tùy tiện API khác trong khi còn giữ critical pointer.

**Local handle của `original = ExceptionOccurred(env)` cũng cần được dọn.** Trong ví dụ trên, sau khi recover/translate/Throw lại, mã C gọi `DeleteLocalRef(env, original)` ngay cả khi exception mới đang pending. Việc xóa **handle local** không hủy object throwable mà JVM đang giữ như pending exception hoặc cause.

Native memory `malloc`, file handles, locks C++ và những tài nguyên khác phải được giải phóng bằng chính cơ chế acquire/release của chúng; `ExceptionClear`, `DeleteLocalRef` hay `PopLocalFrame` không thay thế `free`, `fclose`, mutex unlock.

## 11. Lựa chọn chính sách theo hợp đồng API

| Hoàn cảnh | Chính sách phù hợp | Điều cần giữ |
|---|---|---|
| JNI làm cầu nối mỏng, Java caller biết cách `catch` | **Propagate** | Loại và nội dung exception gốc; không clear |
| Lỗi dữ liệu thử nghiệm được phép dùng giá trị mặc định | **Recover** đúng loại | Chỉ clear lỗi đã được đặc tả; fallback phải tường minh |
| JNI thực hiện ánh xạ tầng hạ tầng thành API nghiệp vụ | **Translate** có kiểm soát | Phân loại lỗi gốc, giữ `cause` nếu cần |
| `OutOfMemoryError`, lỗi linkage, sai cấu hình JNI hoặc lỗi không biết trước | **Propagate/fail** | Không nuốt thành “kết quả hợp lệ” |
| Mã Java dễ hơn để quyết định phục hồi/dịch lỗi | **Để JNI propagate rồi `catch` ở Java** | Giữ native layer đơn giản, giảm JNI calls khi đang lỗi |
| Cần log nhưng vẫn phải truyền lỗi | **Ghi log không làm mất pending exception**, hoặc để Java log sau catch | Tránh dùng `ExceptionDescribe` nếu không muốn clear |

**Recovery là một quyết định nghiệp vụ, không phải mẹo tránh exception.** Ví dụ “nếu mạng chậm thì trả cache còn hạn” khác hoàn toàn với “nếu thiếu bộ nhớ thì coi như thành công”. Với JNI, càng gần tài nguyên hệ thống càng phải có nguyên tắc rõ về việc xử lý lỗi nào tại tầng nào.

Có thể thiết kế Java API trả một kiểu kết quả như `OptionalInt` hay `Result` thay vì ném exception cho lỗi thông thường; nhưng đó là hợp đồng API Java, không có nghĩa JNI được quyền clear mọi lỗi bên dưới.

## 12. Sai lầm dễ mắc và cách phát hiện

| Sai lầm | Tác hại | Sửa thế nào |
|---|---|---|
| Sau `CallStaticIntMethod` không kiểm tra exception | Dùng giá trị trả về không hợp lệ, gọi JNI tiếp khi đang pending | `ExceptionCheck` hoặc kiểm tra giá trị theo hợp đồng |
| Clear mọi exception rồi trả `0` | Nuốt `OutOfMemoryError`/`NoSuchMethodError`, tạo thành công giả | Chỉ clear lỗi được phân loại và cho phép |
| Gọi `FindClass` trước khi clear trong nhánh lỗi | Vi phạm quy tắc pending exception | Tra class trước rủi ro hoặc capture → clear → tra |
| Dùng `ExceptionDescribe` để log rồi return | `ExceptionDescribe` **clear** exception gốc | Dùng `ExceptionCheck`; Java logging sau catch |
| Dùng `ExceptionOccurred` mà không quản lý local ref | Có thể tích lũy handle trong vòng lặp native | `DeleteLocalRef` khi xong hoặc quản lý local frame |
| `ThrowNew` khi exception khác đang pending | Không hợp lệ theo quy tắc gọi JNI lúc pending | Clear theo chính sách trước, rồi tạo/Throw lỗi mới |
| Translate exception nhưng bỏ mất cause | Khó điều tra nguyên nhân lỗi | Dùng constructor `(String, Throwable)` hoặc giải pháp tương đương |
| Recover cả lỗi không thuộc whitelist | Che bug/hỏng trạng thái | Rethrow original với `Throw` |
| Không cleanup resource khi lỗi pending | Rò rỉ native memory, references hoặc khóa | Dùng API release/cleanup được phép rồi return |
| Tự kỳ vọng C++ `catch` bắt Java exception | Trộn hai cơ chế exception khác nhau | Dùng JNI exception APIs |
| Gọi `ExceptionClear` chỉ để làm tiếp code happy path | Đánh mất cơ chế xử lý lỗi | Chỉ clear sau khi đã chọn fallback/recovery/translation rõ |
| Dùng `Throw` để “rethrow” trước khi clear exception cũ | Vi phạm hợp đồng JNI đối với pending exception | Capture → clear → `Throw(original)` |
| Giả định mọi JNI call báo lỗi bằng `NULL` | Một số `Call<Type>Method` có thể tạo exception với giá trị C không đáng tin | Kiểm tra pending sau Java invocation |

### 12.1. Kiểm tra bằng HotSpot

Sau khi build thư viện, có thể bật chế độ kiểm tra JNI trên HotSpot:

~~~bash
java -Xcheck:jni -Djava.library.path=. NativeExceptionPolicy
~~~

`-Xcheck:jni` có thể giúp phát hiện một số lời gọi JNI khi còn pending exception hoặc tham chiếu không hợp lệ. Nó **không bảo đảm** mọi lỗi C/C++ đều bị phát hiện, và không thay thế kiểm thử chính sách recovery/translation. Khi code hợp lệ, stdout ứng dụng vẫn là bảy dòng ở phần thực hành; JVM có thể in thêm cảnh báo nếu phát hiện misuse.

Nếu gặp `UnsatisfiedLinkError`, cần phân biệt **không tìm thấy thư viện native** với **không tìm thấy symbol/hàm JNI**. Đây là lỗi liên kết/nạp thư viện, không phải lý do hợp lệ để tự clear rồi giả vờ kết quả tính toán đúng.

### 12.2. Bốn câu hỏi phải trả lời khi review nhánh JNI có lỗi

1. **Lỗi phát sinh từ API nào?** API gọi Java có ném exception không, hoặc JNI call trả `NULL`/mã lỗi?
2. **Trước khi gọi JNI tiếp, còn pending exception không?** Nếu có, API định gọi có thuộc danh sách cleanup/check được phép không?
3. **Chính sách lỗi ghi rõ ở đâu?** Giữ nguyên để Java bắt, hồi phục đúng loại hay chuyển đổi có giữ cause?
4. **Tài nguyên nào cần dọn trên mọi nhánh?** Local/global refs, pinned arrays, chuỗi native, con trỏ C, file handles, locks.

Nếu không trả lời được, **giữ và truyền lỗi gốc về Java thường an toàn hơn** việc clear rồi tiếp tục.

## 13. Câu hỏi và bài tập tự kiểm tra

1. Khi `CallStaticIntMethod` làm Java helper ném `ArithmeticException`, điều gì xảy ra với luồng thực thi C ngay sau lời gọi?
2. Vì sao `return 0` khi exception pending khác với `ExceptionClear` rồi `return 0`?
3. `ExceptionCheck` và `ExceptionOccurred` khác nhau ở việc tạo local reference như thế nào?
4. Vì sao `ExceptionDescribe` không phù hợp nếu mục tiêu là giữ nguyên lỗi để Java `catch`?
5. Sau khi có pending exception, có được gọi `FindClass`, `NewStringUTF` hoặc `ThrowNew` ngay không?
6. Trong chính sách fallback, vì sao phải phân loại lỗi thay vì clear tất cả exception?
7. Nếu `GetStaticMethodID` không tìm được Java method `divide(I)I`, `recover` có nên trả fallback `-1` không?
8. Nếu đã capture một `jthrowable original` rồi gọi `ExceptionClear`, object throwable có lập tức biến mất không?
9. Khi dịch `ArithmeticException` sang `IllegalArgumentException`, constructor nhận `Throwable cause` giúp giải quyết điều gì?
10. Trong một nhánh có pending Java exception, những API JNI nào có thể dùng để dọn `jstring` local và buffer từ `GetStringUTFChars`?
11. Nếu việc tạo exception mới trong lúc translation gây `OutOfMemoryError`, vì sao không nên clear lỗi mới và coi thao tác thành công?
12. Trường hợp nào nên để Java wrapper chịu trách nhiệm `catch` và dịch lỗi thay vì triển khai nhiều logic exception handling trong C?

**Kết luận:** JNI yêu cầu **quyết định rõ ràng** ở từng ranh giới lỗi: hoặc **giữ pending exception và return để Java xử lý**, hoặc **capture → clear → xử lý đúng chính sách**. Chính sách phục hồi chỉ áp dụng với lỗi được phép, phải dọn tài nguyên đúng cách và không che giấu lỗi khác. Nếu dịch loại lỗi, hãy giữ `cause` để bảo toàn khả năng chẩn đoán. Khi không chắc có thể phục hồi, **propagate nguyên lỗi** là hành vi an toàn và dễ kiểm chứng hơn.

### Tài liệu chuẩn

- [JNI Specification — Design Overview, Java Exceptions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): pending exceptions, hai cách xử lý và danh sách JNI functions được phép khi exception đang chờ.
- [JNI Specification — Exception APIs](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`, `Throw` và `ThrowNew`.
- [Java SE 17 — IllegalArgumentException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/IllegalArgumentException.html): constructor nhận `String` và `Throwable cause`.
- [Android NDK — JNI Tips, Exceptions](https://developer.android.com/ndk/guides/jni-tips): kiểm tra pending exception sau Java callbacks và giới hạn JNI API được phép.
