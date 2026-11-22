# ExceptionCheck, ExceptionOccurred và các trường hợp cần dùng trong JNI

Trong Java Native Interface (JNI), ngoại lệ Java có thể phát sinh ngay khi mã C/C++ đang thực thi: ví dụ một hàm `CallStaticIntMethod` gọi phương thức Java ném `NumberFormatException`, hoặc `FindClass` không tìm thấy lớp, hoặc JNI không thể cấp phát đối tượng mới. Ngoại lệ ấy **được ghi nhận là pending exception trên thread JNI hiện tại**; nó không tự động làm hàm C nhảy khỏi vòng lặp như một câu lệnh `throw` trong Java.

Vì vậy, JNI code phải chủ động quan sát lỗi, dọn tài nguyên và chọn hành động tiếp theo. Hai API thường gặp nhất là:

- **`ExceptionCheck(JNIEnv *env)`:** hỏi **có pending exception hay không**; trả `JNI_TRUE` hoặc `JNI_FALSE`, không tạo local reference tới exception.
- **`ExceptionOccurred(JNIEnv *env)`:** lấy **đối tượng `jthrowable` đang pending**, hoặc `NULL`; nếu có đối tượng, kết quả là local reference JNI cần quản lý. Lời gọi này **không tự xóa** pending exception.

Nội dung dưới đây giải thích khi nào dùng API nào, các thao tác được phép khi pending exception, mẫu xử lý/lan truyền/khôi phục, và chương trình Java 17 + C11 chạy được để kiểm chứng.

## 1. Mô hình pending exception trong JNI

Hãy phân biệt ba lớp trạng thái:

1. **Java exception object:** một đối tượng kế thừa `java.lang.Throwable` như `IllegalArgumentException`, `IOException`, `OutOfMemoryError`.
2. **Pending-exception state:** JVM ghi nhận rằng thread hiện tại có exception cần được xử lý hoặc ném khi quyền điều khiển quay về Java.
3. **Giá trị trả về của hàm JNI:** có thể là `NULL`, `0` hoặc một giá trị bình thường tùy API. Giá trị này **không thể tự thay thế** việc kiểm tra pending exception với mọi JNI call.

Ví dụ: JNI gọi một phương thức Java kiểu `int`. Nếu phương thức ném exception, native caller vẫn nhận một `jint` nào đó ở mức giao tiếp, nhưng **không được coi nó là kết quả nghiệp vụ hợp lệ**. Hãy kiểm tra `ExceptionCheck` ngay sau `CallStaticIntMethod`, rồi cleanup và trả về để exception đi lên Java.

Lưu ý: pending exception là trạng thái gắn với **thread đang dùng `JNIEnv *`**, không phải một biến lỗi chung toàn tiến trình. Không lưu `JNIEnv *` để dùng ở thread khác; cũng không gọi `ExceptionOccurred` trên một thread rồi mặc định thấy exception của thread khác.

### 1.1. Điều gì xảy ra khi JNI function gây lỗi?

Một chuỗi thao tác điển hình:

```text
Java gọi native method
       |
       v
C/JNI: CallStaticIntMethod(...) gọi lại Java
       |
       v
Java callback ném NumberFormatException
       |
       v
JVM đặt pending exception trên JNI thread
       |
       v
C/JNI vẫn đang thực thi
       |
       +--> ExceptionCheck(...) == JNI_TRUE
       |    hoặc ExceptionOccurred(...) trả jthrowable
       |
       +--> dọn local references / buffers / C allocations
       |
       +--> return từ native method
       |
       v
Java caller nhận NumberFormatException
```

Native code **không phải** gọi `ThrowNew` lần nữa nếu muốn chuyển nguyên exception từ callback về Java. Chỉ cần để exception đang pending và trả về đúng cách. Nếu tiếp tục gọi các JNI APIs thông thường như `FindClass`, `NewStringUTF`, `GetObjectClass` hoặc `CallObjectMethod` trong lúc exception còn pending, code có thể vi phạm JNI contract.

### 1.2. Không phải mọi giá trị mặc định đều là lỗi

- Một phương thức Java kiểu `int` có thể **hợp lệ trả `0`**, nên `result == 0` không chứng minh nó ném exception.
- `GetObjectArrayElement` có thể **hợp lệ trả `NULL`** nếu phần tử mảng là `null`, đồng thời có thể phát sinh exception nếu chỉ số không hợp lệ. Khi cần phân biệt, kiểm tra pending state.
- `NewStringUTF` trả `NULL` khi thất bại; phải xử lý đường lỗi (không dereference hoặc dùng kết quả). Với nhiều hàm JNI có return value báo lỗi rõ ràng, kiểm tra return value trước là đủ để đi vào cleanup và không cần tạo `jthrowable` chỉ để kiểm tra.
- Một API JNI không báo lỗi bằng return value hữu ích, chẳng hạn một số biến thể truy cập mảng hoặc lời gọi Java trả giá trị primitive, cần kiểm tra exception tường minh khi kết quả tác động đến logic tiếp theo.

## 2. So sánh `ExceptionCheck` và `ExceptionOccurred`

### 2.1. Chữ ký ở C và giá trị trả về

```c
jboolean ExceptionCheck(JNIEnv *env);
jthrowable ExceptionOccurred(JNIEnv *env);
```

Khi dùng `jni.h` bằng C, chúng xuất hiện dưới dạng lời gọi qua JNI interface:

```c
jboolean hasPending = (*env)->ExceptionCheck(env);
jthrowable error = (*env)->ExceptionOccurred(env);
```

Trong C++ JNI, cú pháp là `env->ExceptionCheck()` và `env->ExceptionOccurred()`; ví dụ tiếp theo sử dụng **C11**.

| Khía cạnh | `ExceptionCheck` | `ExceptionOccurred` |
| --- | --- | --- |
| Câu hỏi trả lời | “Có exception đang pending không?” | “Exception object đang pending là gì?” |
| Kiểu trả về | `jboolean` | `jthrowable` (một JNI object reference) |
| Không có exception | `JNI_FALSE` | `NULL` |
| Có exception | `JNI_TRUE` | Local reference đến exception |
| Tạo local reference mới? | **Không** | **Có khi trả về exception** |
| Tự xóa exception pending? | **Không** | **Không** |
| Cần `DeleteLocalRef`? | Không có object để xóa | Có, nếu giữ được `jthrowable` local và không trả nó ra ngoài |
| Trường hợp dùng | Kiểm tra nhanh, quyết định cleanup/return | Cần giữ, phân loại, xử lý hoặc rethrow cùng một throwable |

**Ưu tiên `ExceptionCheck`** nếu chỉ cần câu trả lời có/không, đặc biệt trong hot loop. Nó không tích lũy thêm local reference. **Chọn `ExceptionOccurred`** nếu thật sự cần đối tượng lỗi để lưu tạm, phân biệt loại lỗi hoặc chuyển nguyên exception sang luồng xử lý khác theo quy tắc JNI.

Ví dụ khi chỉ kiểm tra:

```c
jint value = (*env)->CallStaticIntMethod(env, clazz, method, input);
if ((*env)->ExceptionCheck(env)) {
    /* Dọn tài nguyên đã có; giữ exception pending. */
    return 0; /* Giá trị này bị bỏ qua nếu exception đi lên Java. */
}
return value;
```

Đây là **đoạn trong một native method có kiểu trả về `jint`**, không phải chương trình C độc lập. Số `0` ở nhánh lỗi chỉ đáp ứng chữ ký C; Java quan sát exception thay vì coi đó là kết quả bình thường.

Ví dụ nếu cần đối tượng lỗi:

```c
jthrowable problem = (*env)->ExceptionOccurred(env);
if (problem != NULL) {
    /* Có một local reference; exception VẪN đang pending. */
    (*env)->DeleteLocalRef(env, problem);
    return 0;
}
```

`DeleteLocalRef` chỉ xóa local reference bổ sung mà `ExceptionOccurred` trả về; **không xóa pending state**. Đoạn này cũng chỉ là code nằm trong native method có `jint` return.

### 2.2. Tại sao `ExceptionOccurred` dễ gây rò local references?

Trong một vòng lặp hoặc native thread chạy lâu, mỗi lần `ExceptionOccurred` trả một `jthrowable` mới, JNI lại tạo một local handle. Không xóa các handle vừa tạo có thể làm đầy bảng local reference, ngay cả khi bạn đang cố xử lý lỗi.

Không được nhầm:

```c
jthrowable e = (*env)->ExceptionOccurred(env);
e = NULL;  /* Chỉ thay đổi biến C, không release local reference! */
```

Hãy dùng `DeleteLocalRef(env, e)` khi không cần nó nữa. Với logic chỉ cần boolean, dùng `ExceptionCheck` để tránh tạo ref từ đầu.

## 3. Những tình huống cần kiểm tra ngoại lệ

### 3.1. Ngay sau khi gọi Java method qua JNI

Các hàm như `CallObjectMethod`, `CallIntMethod`, `CallStaticIntMethod` và các biến thể `Call<Type>Method` có thể thực thi **Java code tùy ý**, nơi ngoại lệ có thể xuất hiện vì input, trạng thái ứng dụng hoặc lỗi VM.

Mẫu an toàn:

```c
jint parsed = (*env)->CallStaticIntMethod(env, cls, parseMethod, text);
if ((*env)->ExceptionCheck(env)) {
    /* Không dùng parsed. Dọn những tài nguyên đã lấy được. */
    return 0;
}

/* Đến đây mới có thể dùng parsed như kết quả của Java callback. */
```

Không dựa vào `parsed == 0` hoặc một sentinel do chương trình tự đoán. Nếu Java callback trả `void`, vẫn cần kiểm tra khi muốn gọi JNI tiếp theo hoặc cập nhật trạng thái native phụ thuộc vào callback.

### 3.2. Khi JNI API báo lỗi bằng `NULL` hoặc mã lỗi

Ví dụ:

```c
jclass cls = (*env)->FindClass(env, "java/lang/String");
if (cls == NULL) {
    /* Có thể có pending exception. Không dùng cls. */
    return;
}
(*env)->DeleteLocalRef(env, cls);
```

Ở đây return value đủ cho nhánh lỗi; **không cần gọi `ExceptionOccurred` chỉ để biết rằng `cls == NULL`**. Khi xây dựng thông báo hoặc cần xác định loại lỗi cụ thể, có thể quan sát exception theo hợp đồng của API.

Trường hợp `GetObjectArrayElement` trả `NULL` mơ hồ: null có thể là phần tử thật sự không có object; nếu code cần phân biệt, kiểm tra `ExceptionCheck` sau lời gọi:

```c
jobject element = (*env)->GetObjectArrayElement(env, array, index);
if ((*env)->ExceptionCheck(env)) {
    /* Index lỗi hoặc lỗi JNI khác; không dùng element. */
    return;
}
if (element == NULL) {
    /* Phần tử null hợp lệ. */
} else {
    /* Dùng element, sau đó DeleteLocalRef(env, element). */
    (*env)->DeleteLocalRef(env, element);
}
```

Hai đoạn trên minh họa **thân hàm JNI trả `void`**, với `env`, `array`, `index` đã được xác định hợp lệ; chúng không biên dịch độc lập.

### 3.3. Khi một JNI API không có kênh lỗi tách biệt hữu ích

Có API JNI thao tác theo side effect hoặc trả một giá trị cũng có thể là dữ liệu hợp lệ. Ví dụ phương thức setter trả `void`, nhưng JNI invocation vẫn có thể dẫn đến exception; giá trị trả về không giúp kiểm tra. Trước khi gọi bước tiếp theo, hãy quan sát pending state.

Điểm mấu chốt không phải “sau **mọi** JNI call luôn gọi `ExceptionOccurred`”, mà là **kiểm tra đúng contract của hàm vừa gọi** và mọi vị trí có thể phát sinh exception mà code sẽ còn làm công việc phụ thuộc.

### 3.4. Trong native loop hoặc lời gọi kéo dài

Một native loop chạy nhiều giây, đặc biệt khi không đi qua các JNI APIs khác có thể ném exception, có thể cần các điểm kiểm tra hợp lý để nhận diện exception bất đồng bộ do JVM ghi nhận. Tài liệu JNI khuyến nghị kiểm tra ở những vị trí cần thiết trong tác vụ kéo dài; trên các phiên bản JNI/JVM, chi tiết kiểm tra async exception có thể khác nhau.

```c
/*
 * Minh họa một vòng xử lý native dài:
 * do_work_unit() và total do chương trình sở hữu định nghĩa.
 */
for (size_t i = 0; i < total; ++i) {
    do_work_unit(i);

    if ((i & 1023u) == 0u && (*env)->ExceptionCheck(env)) {
        /* Cleanup tài nguyên native, rồi trả về Java. */
        break;
    }
}
```

Đây **không phải file chạy độc lập**, mà là cấu trúc minh họa một điểm kiểm tra định kỳ. Đừng coi check là cơ chế cancellation tổng quát hoặc cách “bắt” mọi exception bất đồng bộ ngay thời điểm nó được yêu cầu; exception có thể xuất hiện sau lần kiểm tra. Cũng không dùng `Thread.stop()` làm cơ chế dừng worker vì nó đã bị deprecated và có thể khiến trạng thái ứng dụng không nhất quán.

## 4. Điều được phép và không được phép khi exception đang pending

Quy tắc thực hành: **với pending exception, không tiếp tục gọi hầu hết các JNI APIs bình thường**. Cần cleanup trước khi thoát, hoặc chủ động clear exception rồi mới xử lý tiếp.

Theo Java JNI Design Overview, các API JNI có thể gọi an toàn khi pending gồm:

| Nhóm | API được phép | Mục đích |
| --- | --- | --- |
| Quan sát, điều khiển exception | `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear` | Xem trạng thái, log, clear |
| Dọn JNI references | `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef` | Release các JNI handles |
| Dọn chuỗi JNI | `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical` | Trả pointer/buffer lấy từ JNI |
| Dọn mảng JNI | `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical` | Unpin/copy back/release theo contract |
| Dọn monitor | `MonitorExit` | Thả monitor JNI đã giữ |
| Quản lý local frame | `PushLocalFrame`, `PopLocalFrame` | Quản lý phạm vi local refs |
| Quản lý attach thread | `DetachCurrentThread` | Kết thúc gắn thread native theo quy định |

Dù một thao tác nằm trong danh sách được phép, vẫn phải bảo đảm đầu vào hợp lệ và thực hiện đúng lifetime. Trong mã thông thường, **chỉ gọi các cleanup APIs thực sự cần**, sau đó return và để Java nhận exception.

Ngược lại, khi pending, tránh gọi `FindClass`, `GetObjectClass`, `GetMethodID`, `IsInstanceOf`, `NewObject`, `NewStringUTF`, `CallObjectMethod`, `CallStaticIntMethod` hay một chuỗi JNI operations khác chưa được cho phép. Nếu muốn kiểm tra class của throwable bằng `IsInstanceOf`, phải **clear pending state trước**, rồi mới gọi.

Mã C ngoài JNI như `free()`, `fclose()` hoặc thả mutex do ứng dụng tạo không bị cấm bởi danh sách JNI functions, nhưng việc cleanup native vẫn phải giữ đúng hợp đồng và không được gây lỗi mới che khuất exception gốc.

### 4.1. Ba cách xử lý thường gặp

**A. Propagate:** để exception pending, release mọi tài nguyên có thể release an toàn, rồi return. Java caller nhận đúng exception ban đầu.

**B. Recover:** lấy throwable nếu cần, clear pending, xác minh loại lỗi và tạo kết quả dự phòng hợp lệ. Chỉ áp dụng cho lỗi **được chủ động cho phép khôi phục**. Với `OutOfMemoryError`, `LinkageError` hoặc lỗi ngoài dự tính, không nên “nuốt” mặc định.

**C. Translate/rethrow:** lấy throwable, clear pending, kiểm tra hoặc tạo ngữ cảnh mới bằng các JNI APIs bình thường, rồi `Throw` hoặc `ThrowNew` để Java nhận exception. Nếu muốn giữ nguyên object lỗi, dùng `Throw(env, throwable)` khi đã clear và xóa local reference tạm đúng lúc.

Trong cả ba cách, phải quyết định rõ owner của local/global references, JNI acquired pointers và C heap allocation.

### 4.2. `ExceptionDescribe` không phải bộ ghi log vô hại

`ExceptionDescribe(env)` in exception và stack trace ra một kênh báo lỗi hệ thống (thường là `stderr`), nhưng **đồng thời clear pending exception**. Do đó:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env); /* In và CLEAR pending. */
    return 0; /* Java có thể không còn nhận exception ban đầu. */
}
```

Đây là **anti-pattern nếu mục tiêu là propagate nguyên exception**. `ExceptionDescribe` hữu ích khi debug, nhưng phải hiểu side effect trước khi dùng. Để giữ nguyên exception, có thể để nó pending và return; không cần tự in stack trace từ native.

### 4.3. `ExceptionClear` cũng không làm mất đối tượng `Throwable` mà bạn đã lấy local ref

Trình tự hợp lệ để xử lý một exception cụ thể:

```c
jthrowable saved = (*env)->ExceptionOccurred(env);
if (saved != NULL) {
    (*env)->ExceptionClear(env);

    /* Đã clear: lúc này mới được gọi các JNI API bình thường
       để inspect saved nếu thật sự cần. */

    /* ... hoặc Throw(env, saved) để ném lại exception cũ ... */

    (*env)->DeleteLocalRef(env, saved);
}
```

Đoạn code chỉ minh họa trình tự, **không phải translation unit độc lập**. `ExceptionClear` thay đổi pending state; `saved` vẫn là local reference hợp lệ trong phạm vi hiện tại cho đến khi bị xóa hoặc native method trả về. Ngược lại, `DeleteLocalRef(env, saved)` không tự clear pending exception.

## 5. Ví dụ Java 17 + C11 hoàn chỉnh: propagate, observe, recover

Chúng ta tạo ba native methods nhận cùng một chuỗi đầu vào và gọi ngược Java method `parsePositive`:

1. `nativeCheckAndPropagate` dùng **`ExceptionCheck`** để xác định lỗi rồi để Java nhận exception.
2. `nativeObserveAndPropagate` dùng **`ExceptionOccurred`** để lấy local `jthrowable`, xóa local ref, vẫn để exception pending.
3. `nativeRecoverFormat` lấy throwable, clear pending, xác nhận chính xác lỗi kiểu `NumberFormatException` rồi trả sentinel `-1`; nếu là lỗi khác, ném lại throwable gốc.

Ở đây `parsePositive` định nghĩa số hợp lệ là số nguyên **dương** (lớn hơn 0), nên `-1` có thể dành riêng làm kết quả fallback. Với API thực tế có miền số âm hợp lệ, **không** dùng sentinel trùng dữ liệu; nên trả status tách biệt hoặc một đối tượng kết quả Java.

### 5.1. File `ExceptionProbe.java`

```java
public final class ExceptionProbe {
    static {
        System.loadLibrary("exceptionprobe");
    }

    private ExceptionProbe() {}

    private static int parsePositive(String text) {
        int value = Integer.parseInt(text);
        if (value <= 0) {
            throw new NumberFormatException("must be positive");
        }
        return value;
    }

    private static native int nativeCheckAndPropagate(String text);
    private static native int nativeObserveAndPropagate(String text);
    private static native int nativeRecoverFormat(String text);

    public static void main(String[] args) {
        System.out.println(
            "check-good=" + nativeCheckAndPropagate("42"));

        try {
            nativeCheckAndPropagate("bad");
        } catch (NumberFormatException error) {
            System.out.println(
                "check-error=" + error.getClass().getSimpleName());
        }

        System.out.println(
            "occurred-good=" + nativeObserveAndPropagate("21"));

        try {
            nativeObserveAndPropagate("bad");
        } catch (NumberFormatException error) {
            System.out.println(
                "occurred-error=" + error.getClass().getSimpleName());
        }

        System.out.println(
            "recover-good=" + nativeRecoverFormat("7"));
        System.out.println(
            "recover-error=" + nativeRecoverFormat("bad"));
        System.out.println(
            "recover-negative=" + nativeRecoverFormat("-3"));
    }
}
```

Không có race hay phụ thuộc dữ liệu ngoài: parser là Java method tĩnh thuần với `Integer.parseInt`. Chuỗi `"bad"` luôn gây `NumberFormatException`; `"-3"` parse thành số âm rồi bị chặn theo contract của bài toán.

### 5.2. Tạo JNI header bằng `javac -h`

Tại thư mục chứa source Java:

```bash
javac -h . ExceptionProbe.java
```

Lệnh tạo `ExceptionProbe.class` và `ExceptionProbe.h`. Các prototype tương ứng có dạng:

```c
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeCheckAndPropagate(
    JNIEnv *, jclass, jstring);

JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeObserveAndPropagate(
    JNIEnv *, jclass, jstring);

JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeRecoverFormat(
    JNIEnv *, jclass, jstring);
```

Đây là **trích minh họa chữ ký**; file C đầy đủ bên dưới include header thật do `javac -h` sinh. Nếu thêm package, đổi class hoặc overload native method, chạy lại bước này để tránh sai tên symbol/descriptor.

### 5.3. File `ExceptionProbe.c`

```c
#include "ExceptionProbe.h"

static jmethodID find_parser(JNIEnv *env, jclass clazz) {
    return (*env)->GetStaticMethodID(
        env, clazz, "parsePositive", "(Ljava/lang/String;)I");
}

/*
 * A. Chỉ cần biết lỗi có pending hay không.
 * Để nguyên exception và trở lại Java.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeCheckAndPropagate(
    JNIEnv *env, jclass clazz, jstring text) {

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        return 0; /* Lỗi lookup: để pending exception đi lên. */
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Bỏ value, Java sẽ nhận exception. */
    }

    return value;
}

/*
 * B. Lấy object lỗi, nhưng không clear pending state.
 * Xóa local reference do ExceptionOccurred trả về.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeObserveAndPropagate(
    JNIEnv *env, jclass clazz, jstring text) {

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        return 0;
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    jthrowable observed = (*env)->ExceptionOccurred(env);
    if (observed != NULL) {
        /* DeleteLocalRef được phép khi exception pending. */
        (*env)->DeleteLocalRef(env, observed);
        return 0; /* Pending exception vẫn còn. */
    }

    return value;
}

/*
 * C. Chỉ recover đối với NumberFormatException.
 * Các exception khác được ném lại đúng object.
 */
JNIEXPORT jint JNICALL
Java_ExceptionProbe_nativeRecoverFormat(
    JNIEnv *env, jclass clazz, jstring text) {

    /* Resolve class trước khi callback có thể ném exception. */
    jclass expected = (*env)->FindClass(
        env, "java/lang/NumberFormatException");

    if (expected == NULL) {
        return 0;
    }

    jmethodID parser = find_parser(env, clazz);
    if (parser == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        return 0;
    }

    jint value = (*env)->CallStaticIntMethod(
        env, clazz, parser, text);

    if (!(*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, expected);
        return value;
    }

    jthrowable pending = (*env)->ExceptionOccurred(env);
    if (pending == NULL) {
        (*env)->DeleteLocalRef(env, expected);
        return 0; /* Không xử lý khi thiếu throwable. */
    }

    (*env)->ExceptionClear(env);

    /* Sau clear mới gọi IsInstanceOf. */
    jboolean isFormatError = (*env)->IsInstanceOf(
        env, pending, expected);

    (*env)->DeleteLocalRef(env, expected);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, pending);
        return 0; /* Giữ exception mới nếu thao tác inspect lỗi. */
    }

    if (isFormatError == JNI_TRUE) {
        (*env)->DeleteLocalRef(env, pending);
        return -1; /* Fallback hợp lệ theo miền giá trị dương. */
    }

    /* Lỗi ngoài loại cho phép: giữ nguyên throwable gốc. */
    (void)(*env)->Throw(env, pending);
    (*env)->DeleteLocalRef(env, pending);
    return 0;
}
```

Từng chi tiết quan trọng trong file C:

- `GetStaticMethodID` lấy `jmethodID`, **không** phải local reference; không gọi `DeleteLocalRef` cho `jmethodID`. Chuỗi descriptor `(Ljava/lang/String;)I` nghĩa là nhận một `java.lang.String` và trả `int`.
- `clazz` là tham chiếu class do JVM truyền cho native method `static`. Ví dụ không phải tự `FindClass` để định vị class chứa parser ở hai phương thức đầu.
- Khi `CallStaticIntMethod` gọi parser ném lỗi, `value` không còn đáng tin. `nativeCheckAndPropagate` dùng `ExceptionCheck` rồi return; **không gọi `ExceptionClear`**.
- `nativeObserveAndPropagate` gọi `ExceptionOccurred` đúng một lần; nếu có `jthrowable`, nó xóa local ref. Exception pending **không bị mất**.
- `nativeRecoverFormat` chuẩn bị local `jclass expected` **trước callback**; nếu chỉ gọi `FindClass` sau khi đã có pending exception thì sẽ vi phạm quy tắc JNI. Khi có exception, lấy `pending`, clear, rồi gọi `IsInstanceOf`.
- `IsInstanceOf` cho phép xử lý riêng `NumberFormatException`. Chỉ lỗi đã được contract cho phép mới chuyển thành `-1`. Nếu là loại exception khác, `Throw(env, pending)` ném lại cùng object và `DeleteLocalRef` xóa handle tạm.
- Sau `Throw` thành công, exception lại pending; `DeleteLocalRef` vẫn thuộc nhóm API cho phép trong trạng thái này. Trong thư viện production, còn phải xử lý trường hợp đặc biệt `Throw` báo lỗi (giá trị âm) theo chính sách lỗi của thư viện.
- Nếu lookup class hoặc method thất bại, các nhánh return giữ nguyên exception do JNI báo. Khi có một local reference hợp lệ, hàm cleanup nó trước khi return; không gọi JNI lookup mới trên đường lỗi.

Chương trình mẫu được viết với một callback xác định và ít tài nguyên. Trong ứng dụng thực, có thể có native mutex, file descriptor, buffers từ `GetStringUTFChars`, local frames và heap allocations phải release thêm ở cả nhánh success và exception.

### 5.4. Biên dịch và chạy (Linux, JDK 17+)

Đặt hai file `ExceptionProbe.java` và `ExceptionProbe.c` trong cùng thư mục. Thiết lập biến `JAVA_HOME` tới JDK đang dùng sao cho tồn tại `$JAVA_HOME/include/jni.h`. Biên dịch:

```bash
javac -h . ExceptionProbe.java

cc -std=c11 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  ExceptionProbe.c -o libexceptionprobe.so

java -Djava.library.path=. ExceptionProbe
```

**Stdout dự kiến, chính xác với input trong `main`:**

```text
check-good=42
check-error=NumberFormatException
occurred-good=21
occurred-error=NumberFormatException
recover-good=7
recover-error=-1
recover-negative=-1
```

Kết quả này minh họa sự khác biệt giữa **giữ pending** (Java catch nhận exception) và **clear có chủ đích** (Java nhận số fallback). Trên Windows/macOS, thư viện cần tên đuôi, compiler flags và đường include header JNI của hệ điều hành tương ứng; lệnh Linux không thể sao chép nguyên sang MSVC. Nếu gặp `UnsatisfiedLinkError`, kiểm tra `System.loadLibrary`, `java.library.path`, kiến trúc JDK/native library và header mới sinh.

Có thể bật kiểm tra JNI của HotSpot khi debug:

```bash
java -Xcheck:jni -Djava.library.path=. ExceptionProbe
```

`-Xcheck:jni` giúp phát hiện nhiều lỗi dùng JNI sai, đặc biệt gọi hàm không hợp lệ khi exception pending. Đây là công cụ kiểm tra bổ sung, không thay thế việc đọc contract và kiểm thử các đường lỗi.

## 6. Xử lý tài nguyên khi callback ném exception

Lỗi thực tế thường không nằm ở `ExceptionCheck` mà ở cách cleanup sau khi nó trả true. Ví dụ một native method giữ native memory và một JNI string buffer:

```c
/*
 * Minh họa cấu trúc bên trong native method có JNI env và
 * jstring input hợp lệ; không phải chương trình độc lập.
 */
char *scratch = malloc(4096);
if (scratch == NULL) {
    /* Có thể báo OutOfMemoryError qua JNI trước khi có pending. */
    return;
}

const char *utf8 = (*env)->GetStringUTFChars(env, input, NULL);
if (utf8 == NULL) {
    free(scratch);  /* Không có buffer JNI để release. */
    return;
}

/* Công việc có thể gọi ngược Java và ném exception. */
(*env)->CallVoidMethod(env, target, callbackMethod);

if ((*env)->ExceptionCheck(env)) {
    (*env)->ReleaseStringUTFChars(env, input, utf8);
    free(scratch);
    return; /* Giữ exception pending. */
}

(*env)->ReleaseStringUTFChars(env, input, utf8);
free(scratch);
```

Đoạn này cần include `<stdlib.h>` và có `target`/`callbackMethod` hợp lệ do chương trình sở hữu chuẩn bị; nó chỉ mô tả **đường cleanup**, không được quảng cáo là file C biên dịch độc lập.

Nhớ rằng:

- `ReleaseStringUTFChars` phải ghép với `GetStringUTFChars` nếu đã lấy được buffer; `DeleteLocalRef` không thay thế thao tác release này.
- `free(scratch)` thuộc trách nhiệm C allocator, khác với việc delete local JNI reference.
- Khi JNI callback tạo pending exception, `ReleaseStringUTFChars` thuộc nhóm hàm được phép gọi để cleanup.
- Nếu có monitor JNI được lấy bằng `MonitorEnter`, phải cân nhắc `MonitorExit` đúng một lần. Không tiếp tục gọi method Java để “đóng” tài nguyên trong khi exception pending.
- Với local refs tạm do `NewStringUTF`, `FindClass` hoặc `GetObjectClass` tạo ra, gọi `DeleteLocalRef` khi chúng không còn cần. Riêng local `jthrowable` lấy từ `ExceptionOccurred` cũng cần cleanup nếu không trả nó ra ngoài.
- Nếu đã `PushLocalFrame` thành công, phải `PopLocalFrame` trước khi rời scope khi cần quản lý ref theo frame, kể cả trên đường lỗi; chỉ dùng đúng API được cho phép khi đang pending.

Một thiết kế thực tế tốt thường gom cleanup ở một nhánh thống nhất, kiểm soát thứ tự release và chỉ return sau khi không còn tài nguyên native do caller sở hữu.

## 7. Khi nào cần lấy đối tượng `Throwable`?

Đa số JNI call chỉ cần biết thành công hay thất bại; `ExceptionCheck` đơn giản hơn. `ExceptionOccurred` có ý nghĩa khi chính object lỗi là **dữ liệu để giải quyết chính sách xử lý**.

Những trường hợp hợp lý:

1. **Phân loại lỗi:** cần phân biệt `NumberFormatException` với exception ngoài dự tính trước khi chọn fallback. Lấy throwable, clear, rồi `IsInstanceOf` với lớp đã chuẩn bị.
2. **Giữ và ném lại đúng exception:** khi cần hoàn tất cleanup có thêm bước xử lý bình thường sau khi clear, có thể giữ local `jthrowable` rồi gọi `Throw` khi xong. Nếu chỉ cleanup đơn giản, giữ pending và return sẽ gọn hơn.
3. **Chuyển exception sang một wrapper khác:** có thể clear, xây dựng Java throwable mới bằng `ThrowNew`/constructor phù hợp rồi gắn cause theo policy. Trình tự phải tránh gọi các JNI APIs bị cấm khi pending. Không nên làm mất stack trace/cause mà không có lý do.
4. **Quản lý lỗi ở native-attached worker thread:** nếu thread native không có Java caller trực tiếp chờ exception, code phải có một kênh báo lỗi cho chủ sở hữu. Điều này cần thiết kế riêng về JavaVM, attach, local/global refs, đồng bộ hóa và quy tắc thread; chỉ gọi `ExceptionOccurred` không tự chuyển exception sang thread khác.
5. **Chẩn đoán có kiểm soát:** khi thực sự cần type/message/stack của exception, phải clear trước các JNI method calls thông thường, rồi xử lý hoặc rethrow đúng policy. Đừng để code debug thay đổi ngầm behavior production.

Đừng giữ local `jthrowable` sau khi native method kết thúc hoặc truyền nó sang thread khác. Muốn giữ object Java dài hạn thì cần global reference bằng `NewGlobalRef` (khi pending đã được xử lý đúng); sau đó `DeleteGlobalRef` đúng thời điểm. Global ref giữ object sống, nên không thể để thất lạc.

## 8. Phối hợp `Throw`, `ThrowNew`, `ExceptionClear` và `ExceptionDescribe`

| API | Ý nghĩa | Tác dụng với pending state |
| --- | --- | --- |
| `ExceptionCheck` | Kiểm tra boolean | Không clear |
| `ExceptionOccurred` | Lấy local `jthrowable` | Không clear |
| `ExceptionClear` | Xóa trạng thái exception hiện tại | Clear; Java không còn tự nhận lỗi ấy |
| `ExceptionDescribe` | In exception và stack trace để debug | **Có thể clear pending như side effect được mô tả trong JNI spec** |
| `Throw(env, throwable)` | Đặt một object Throwable đã có thành exception cần ném | Tạo pending cho throwable đó; trả status |
| `ThrowNew(env, clazz, message)` | Tạo exception từ class và message | Đặt exception mới thành pending; message dùng Modified UTF-8 |

### 8.1. Không tạo exception thứ hai khi exception thứ nhất vẫn pending

Anti-pattern:

```c
(*env)->CallVoidMethod(env, receiver, method); /* Có thể ném. */
/* Sai: tìm class và ném lỗi khác khi chưa kiểm tra pending. */
jclass c = (*env)->FindClass(env, "java/lang/IllegalStateException");
(*env)->ThrowNew(env, c, "wrapper error");
```

Đoạn này là **minh họa sai**, không có cleanup và không biên dịch độc lập. Nếu callback đã ném lỗi, `FindClass` nằm ngoài danh sách JNI calls được phép khi pending. Cách đúng bắt đầu bằng `ExceptionCheck`, sau đó:

- Propagate: giữ nguyên pending, dọn tài nguyên, return.
- Translate: lấy exception nếu muốn giữ cause, clear, tìm class/khởi tạo exception mới và đảm bảo không che khuất lỗi ngoài dự tính.
- Recover: chỉ khi contract cho phép, clear sau khi giữ đủ thông tin cần thiết, rồi trả fallback hợp lệ.

### 8.2. Sự khác nhau giữa “đã quan sát” và “đã xử lý”

`ExceptionOccurred` không có nghĩa là đã bắt/consume exception. JNI vẫn giữ lỗi pending. Chỉ đọc local `jthrowable` và xóa reference ấy cũng không thay đổi trạng thái pending.

`ExceptionCheck` cũng không có cơ chế “try-catch” Java tự động. Nó chỉ trả boolean để native code quyết định đường tiếp theo.

`ExceptionClear` thực sự bỏ pending exception; gọi nó mà không có chính sách xử lý sẽ biến lỗi thành thành công giả. Nếu một API vẫn trả được kết quả số cũ khi có exception, kết quả đó không được phép coi là hợp lệ chỉ vì đã clear lỗi.

## 9. Tình huống biên và các lỗi thường gặp

| Lỗi hoặc giả định sai | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `ExceptionOccurred` sau mỗi JNI call chỉ để lấy boolean | Tạo local ref thừa nếu có lỗi | Dùng `ExceptionCheck` nếu không cần throwable |
| Gọi `ExceptionOccurred` rồi không `DeleteLocalRef` | Tích lũy local references trong hàm chạy lâu | Release từng local handle |
| Dùng giá trị `jint` của `CallIntMethod` sau khi callback ném | Dữ liệu không đáng tin | Check ngay; bỏ kết quả và cleanup |
| Thấy `NULL` từ array read là kết luận có exception | Phần tử `null` cũng hợp lệ | Kiểm tra `ExceptionCheck` nếu cần phân biệt |
| Gọi `GetObjectClass`/`FindClass` khi pending | Vi phạm JNI contract | Clear có chủ đích trước bước inspect |
| Gọi `ExceptionDescribe` rồi kỳ vọng lỗi tự lên Java | Pending có thể đã bị clear | Không dùng để propagate; debug rõ side effect |
| Gọi `ExceptionClear` để chạy tiếp mà không kiểm tra loại lỗi | Nuốt lỗi, bỏ `OutOfMemoryError` hoặc lỗi logic | Selective recovery; rethrow unexpected |
| Dùng `ThrowNew` để “bọc” lỗi khi callback vẫn pending | Thao tác JNI bị cấm/chồng lỗi | Lấy/clear trước khi xây wrapper |
| Gọi `DeleteLocalRef` và tưởng đã clear exception | Java vẫn nhận exception pending | Phân biệt handle lifetime và pending state |
| Truyền `JNIEnv *`/local `jthrowable` sang thread khác | Sai thread/lifetime | Attach thread riêng; dùng global ref đúng contract |
| Không release `GetStringUTFChars` khi exception | Native buffer bị giữ/rò | Release trong cleanup được phép |
| Không pop local frame trên đường exception | Local refs tồn tại lâu | Pop frame sau push thành công |
| Dùng `ExceptionCheck` như dấu hiệu cancel chính xác từng microsecond | Async exception có thể xuất hiện giữa checks | Đặt check phù hợp; cơ chế hủy có contract riêng |
| Gọi JNI lặp lại khi đã pending để log thêm | Có thể dẫn tới undefined behavior/crash | Chỉ gọi APIs được cho phép rồi return |
| Bắt mọi `Throwable` như lỗi parse bình thường | Che khuất lỗi hệ thống | Chỉ recover lỗi mà business contract xác định |

### 9.1. Chú ý tới JNI result và mã lỗi C

Mã lỗi `errno` của C, return code từ thư viện C và Java pending exception là **ba cơ chế khác nhau**. `ExceptionCheck` không thông báo rằng `fopen()` thất bại; `errno != 0` không có nghĩa Java đang ném exception. Nếu gọi thư viện C và gặp lỗi, JNI layer có thể chủ động dựng Java exception bằng `ThrowNew` theo mapping đã định nghĩa, nhưng cần thực hiện khi chưa có một exception khác pending.

Tương tự, `JNI_FALSE` từ `ExceptionCheck` không chứng minh mọi thao tác native thành công: nó chỉ chứng minh **không có Java exception đang pending ở thời điểm kiểm tra**. C code vẫn cần kiểm tra null pointers, bounds, tài nguyên đã đóng, return code và lifetime.

## 10. Kiểm thử hành vi JNI khi lỗi

Một bộ kiểm thử nên bao phủ:

1. **Không lỗi:** `nativeCheckAndPropagate("42")` trả `42`; `nativeObserveAndPropagate("21")` trả `21`; `nativeRecoverFormat("7")` trả `7`.
2. **Có lỗi, propagate bằng Check:** `nativeCheckAndPropagate("bad")` phải ném `NumberFormatException` tới Java, không trả `0` như kết quả thành công.
3. **Có lỗi, lấy Throwable:** `nativeObserveAndPropagate("bad")` cũng phải ném cùng loại exception, dù local reference lấy từ `ExceptionOccurred` đã được xóa.
4. **Recover đúng loại:** `nativeRecoverFormat("bad")` và `nativeRecoverFormat("-3")` trả `-1`; không có pending exception sau khi hàm trả.
5. **Ngoài loại lỗi được cho phép:** khi callback giả lập `IllegalStateException` hoặc `OutOfMemoryError`, đường recover phải giữ/đẩy exception đi lên Java, không biến thành `-1`.
6. **Cleanup:** tạo các JNI local refs và `GetStringUTFChars` buffers trước callback, cố ý kích hoạt exception; kiểm tra mọi đường return release đúng tài nguyên.
7. **Long loop:** dùng nhiều callbacks, kiểm tra sau JNI calls có thể thất bại; không tích lũy `jthrowable` local refs trong vòng lặp.
8. **Thread isolation:** tạo exceptions trên nhiều Java threads, bảo đảm mỗi lần kiểm tra dùng `JNIEnv *` của chính thread đó.
9. **Debug behavior:** bật `-Xcheck:jni` khi JVM hỗ trợ để phát hiện JNI calls bị cấm khi pending và các reference sai.

Một đoạn test Java độc lập với JNI implementation của bài có thể viết:

```java
// Ví dụ chỉ là đoạn trong class test có sẵn,
// không phải một source file độc lập.
try {
    nativeCheckAndPropagate("bad");
    throw new AssertionError("Expected NumberFormatException");
} catch (NumberFormatException expected) {
    // Pending exception đã được Java nhận và xử lý.
}
```

Có thể dùng JUnit trong dự án thật, nhưng bài mẫu ở trên đã có `main` và stdout xác định để kiểm tra nhanh.

## 11. Quy trình quyết định khi có pending exception

```text
Sau một JNI call có thể phát sinh exception
                |
                v
   Có error sentinel rõ ràng? ---- Có ---> vào nhánh lỗi
                |                            |
               Không                         |
                |                            |
                v                            v
      ExceptionCheck(env) ? <--------- có pending?
          |          |
       FALSE        TRUE
          |          |
          v          v
  Dùng kết quả   Có cần đối tượng Throwable?
                    |             |
                  Không          Có
                    |             |
                    v             v
                 Cleanup     ExceptionOccurred()
                 an toàn         |
                    |             v
                    |       Giữ local ref
                    |       (quản lý lifetime)
                    |             |
                    +-------+-----+
                            |
                            v
             Propagate hay Recover/Translate?
                    |                 |
                Propagate         Recover/Translate
                    |                 |
             Giữ pending         Clear có chủ đích
             Cleanup, return     Inspect/handle/rethrow
                                      |
                                      v
                              Dọn local refs, return
```

Đây là sơ đồ tư duy, không thay cho contract từng API. Nếu return value báo lỗi nhưng không có pending exception, native method vẫn phải xử lý lỗi theo API đó; nếu return value bình thường mà Java callback ném, phải ưu tiên pending exception.

Checklist trước khi bàn giao:

- Sau mỗi `Call<Type>Method` hoặc JNI API có thể gây lỗi, nhánh kiểm tra có phân biệt **pending exception** và **giá trị kết quả** không?
- Chỉ cần biết có lỗi hay thật sự cần `jthrowable` object? Nếu chỉ cần boolean, dùng `ExceptionCheck`.
- Nếu dùng `ExceptionOccurred`, local reference có được xóa đúng lúc không? Có dùng ref sau khi xóa hoặc qua thread khác không?
- Có JNI calls thông thường nào xảy ra trong lúc exception đang pending không?
- `ExceptionClear` có được gọi **chỉ khi** thực sự chọn recover/translate, và có tránh nuốt `Error` ngoài dự tính không?
- Có dùng `ExceptionDescribe` trong production khiến pending tự mất không?
- Có xử lý tài nguyên từ JNI và C allocator ở mọi đường success/exception không?
- Với native loop dài, các điểm kiểm tra lỗi có hợp lý và không tạo thêm local ref không?
- Kết quả fallback có miền giá trị rõ ràng, không mơ hồ với dữ liệu hợp lệ không?

**Quy tắc ghi nhớ:** `ExceptionCheck` trả lời “có exception không?” với chi phí quản lý reference thấp. `ExceptionOccurred` trả lời “exception nào?” và tạo một local reference khi có lỗi. **Cả hai đều không clear pending state.** Sau khi phát hiện lỗi, hãy cleanup bằng những API được phép và return để Java nhận lỗi, hoặc thực hiện quy trình clear/inspect/rethrow có chủ đích.

### Tài liệu tham khảo

- [Oracle Java SE 17 — JNI Design Overview, Java Exceptions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — JNI Functions: ExceptionCheck, ExceptionOccurred, ExceptionClear, Throw](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Android Developers — JNI Tips: Exceptions](https://developer.android.com/ndk/guides/jni-tips)
- [Oracle Java SE 17 — javac -h để tạo JNI header](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
