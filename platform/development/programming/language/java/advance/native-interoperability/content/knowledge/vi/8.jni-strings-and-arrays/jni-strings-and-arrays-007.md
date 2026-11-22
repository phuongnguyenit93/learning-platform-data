# Giới hạn không chặn và không gọi JNI tùy ý trong vùng Critical

## 1. Vùng Critical trong JNI là gì?

Khi mã C/C++ xử lý **mảng primitive** hoặc **chuỗi Java**, JNI có các API lấy con trỏ để đọc/ghi dữ liệu. Hai cặp API đặc biệt là:

- `GetPrimitiveArrayCritical` / `ReleasePrimitiveArrayCritical`: truy cập các phần tử của mảng primitive như `int[]`, `byte[]`, `double[]`.
- `GetStringCritical` / `ReleaseStringCritical`: truy cập các **đơn vị mã UTF-16 `jchar`** của một Java `String`.

Khoảng thời gian **sau khi lấy con trỏ thành công và trước khi gọi hàm Release tương ứng** là một **JNI critical region**. Trong khoảng này, mã native phải thực hiện rất ít việc: **không chặn (blocking), không gọi JNI tùy ý, không giữ vùng Critical lâu**.

Tại sao có giới hạn nghiêm ngặt? JVM có thể trả **con trỏ trực tiếp vào vùng nhớ được quản lý** và tạm giữ (*pin*) đối tượng, hoặc cần hạn chế hoạt động của bộ thu gom rác (GC) để con trỏ không bị vô hiệu. Nếu thread native giữ vùng Critical quá lâu, GC hoặc những thread Java khác có thể bị trì hoãn. Một thread đang giữ vùng Critical mà lại chờ công việc cần JVM tiến hành có thể tạo thành vòng chờ (*deadlock*).

**Không có cam kết zero-copy:** JVM **có thể sao chép** dữ liệu thay vì pin; tên `Critical` thể hiện **hợp đồng sử dụng nghiêm ngặt**, không bảo đảm lúc nào bạn cũng nhận con trỏ thẳng tới Java heap.

Mục tiêu sau bài:

1. Nhận diện thời điểm bắt đầu/kết thúc một vùng Critical.
2. Biết những thao tác được và không được làm khi đang giữ con trỏ Critical.
3. Sắp xếp mọi lệnh JNI/IO/đồng bộ **trước hoặc sau** vùng Critical.
4. Viết ví dụ **Java 17+ và C11 chạy được** dùng cả hai cặp API.
5. Phân biệt `0`, `JNI_ABORT`, `JNI_COMMIT` khi release mảng; xử lý `NULL`, `isCopy` và exception.
6. Chọn API khác khi cần IO, callback, khóa, xử lý dài hoặc làm việc theo từng khối.

## 2. Chữ ký, kiểu dữ liệu và vòng đời con trỏ

### 2.1. Mảng primitive

Trong mã C (từ `jni.h`):

~~~c
void *GetPrimitiveArrayCritical(
        JNIEnv *env, jarray array, jboolean *isCopy);

void ReleasePrimitiveArrayCritical(
        JNIEnv *env, jarray array, void *carray, jint mode);
~~~

Sử dụng từ một JNI function nhận `jintArray`:

~~~c
jint *ptr = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, numbers, NULL);

/* Nếu ptr != NULL: đọc/ghi nhanh và ngắn, không gọi JNI tùy ý */

if (ptr != NULL) {
    (*env)->ReleasePrimitiveArrayCritical(
            env, numbers, ptr, JNI_ABORT);
}
~~~

Đây là **mẫu rút gọn**, chưa phải hàm độc lập. `GetPrimitiveArrayCritical` trả một con trỏ `void *` tương ứng phần tử của **mảng primitive**, hoặc `NULL` nếu thất bại. Cần ép sang loại `jint *`, `jbyte *`, `jdouble *`... theo **kiểu phần tử thực**. Không áp dụng API này cho `jobjectArray` chứa các Java object.

Các thông tin phải có trước khi gọi Get:

- `array` phải là reference hợp lệ, **không NULL**.
- Kích thước mảng (`GetArrayLength`) phải được lấy **trước khi** đi vào vùng Critical.
- Buffer đầu ra và trạng thái native cần thiết nên được chuẩn bị trước.
- Có thể truyền `jboolean *isCopy` để quan sát JVM đang cho bản sao (`JNI_TRUE`) hay con trỏ trực tiếp (`JNI_FALSE`). Thông tin này **không thay đổi nghĩa vụ Release và giới hạn Critical**.

### 2.2. Chuỗi Java

~~~c
const jchar *GetStringCritical(
        JNIEnv *env, jstring string, jboolean *isCopy);

void ReleaseStringCritical(
        JNIEnv *env, jstring string, const jchar *carray);
~~~

`GetStringCritical` cung cấp dãy **đơn vị mã UTF-16** với kiểu `jchar`, không phải byte UTF-8 và **không có cam kết chuỗi kết thúc bằng NUL**. Dùng chiều dài từ `GetStringLength`, đã lấy **trước** khi mở vùng Critical.

Ví dụ nếu Java truyền `"A😀B"`, Java `String.length()` bằng **4 đơn vị UTF-16** vì biểu tượng cảm xúc chiếm một cặp surrogate. Mã C nhìn thấy bốn `jchar`; không được suy rằng có bốn Unicode code points. Chuỗi Java có thể chứa `'\u0000'`, nên không dùng `wcslen` hoặc tìm NUL để tính độ dài.

Hai API khác cần phân biệt:

| JNI API | Dữ liệu nhận được | Có phải cặp Critical? |
| --- | --- | --- |
| `GetStringCritical` | `const jchar *`, UTF-16 code units | **Có**, phải `ReleaseStringCritical` |
| `GetStringChars` | `const jchar *`, UTF-16 code units | Không, dùng `ReleaseStringChars` |
| `GetStringUTFChars` | `const char *`, **Modified UTF-8** | Không, dùng `ReleaseStringUTFChars` |
| `GetStringRegion` | Sao chép một đoạn UTF-16 vào buffer do C cấp | Không có con trỏ Java cần giữ qua một cặp Get/Release |

Không tráo API Release, không giải phóng các con trỏ JNI bằng `free`, và **không dùng chúng sau khi Release**.

## 3. Quy tắc cốt lõi: giới hạn vùng Critical

Theo JNI Specification, khi giữ con trỏ từ `GetPrimitiveArrayCritical`, native code **không được gọi các JNI function khác một cách tùy ý** và **không được thực hiện system call có thể chặn thread hiện tại để chờ thread Java khác**. Với `GetStringCritical`, giới hạn tương tự áp dụng: **không gọi JNI tùy ý, không khiến thread bị chặn**. Hãy coi cả hai vùng Critical là **đoạn CPU ngắn, có thời gian thực thi được kiểm soát**.

| Thao tác | Trong vùng Critical? | Lý do/cách làm đúng |
| --- | --- | --- |
| Đọc vài phần tử, cộng số, kiểm tra `jchar`, thao tác `memcpy` ngắn vào buffer đã sẵn sàng | Thường **được**, nếu không chặn và kết thúc rất nhanh | Chỉ xử lý dữ liệu thô, không động chạm JVM |
| `GetArrayLength`, `GetStringLength` | **Không** | Lấy độ dài trước khi Get Critical |
| `FindClass`, `NewStringUTF`, `GetObjectClass`, `GetMethodID` | **Không** | Có thể liên quan JVM/GC/class loading; thực hiện sau Release |
| `CallObjectMethod`, `CallVoidMethod` hoặc gọi ngược Java | **Không** | Java callback có thể cấp phát, chặn, dùng lock hoặc gây GC |
| `ExceptionCheck`, `ThrowNew`, `NewGlobalRef`, `DeleteLocalRef` | **Không gọi trong Critical** | Xử lý lỗi/reference trước khi Get hoặc sau khi Release |
| `Thread.sleep` qua Java callback, `sleep`, `read`/`recv` có thể chặn, `accept`, đợi mạng/disk | **Không** | Thread có thể ngủ/chờ khi GC cần hoàn tất |
| `pthread_mutex_lock`, `WaitForSingleObject`, `condition_variable::wait` | **Không** nếu có thể chờ | Lấy/release lock bên ngoài; tránh lock bên trong |
| `printf`/log đồng bộ, ghi file, gửi telemetry, RPC | **Không nên** | IO và logging có thể chặn, lấy mutex hoặc cấp phát |
| Cấp phát qua `malloc`/`new`, gọi thư viện C/C++ có hành vi không rõ | **Tránh** | Allocator/runtime/library có thể lấy lock và gây chờ |
| `ReleasePrimitiveArrayCritical`/`ReleaseStringCritical` tương ứng | **Bắt buộc** | Đóng vùng Critical trước mọi JNI/callback/IO |
| Hai cặp Get/Release Critical lồng nhau | Đặc tả **cho phép** một số trường hợp | Vẫn phải release chính xác và giữ tất cả các vùng ngắn; không dùng lồng nhau nếu có giải pháp đơn giản hơn |

Từ “không chặn” không có nghĩa là “không dùng `synchronized` trong Java nữa”. Nó có nghĩa **native code đang giữ con trỏ Critical không được bắt đầu thao tác có thể phải chờ**. Tránh cả lệnh trông có vẻ nhẹ nhưng thực tế có thể chuyển sang JVM, gây class loading, lock contention hoặc IO.

### 3.1. Vì sao “gọi JNI nhỏ thôi” cũng không an toàn?

Giả sử sau khi Get Critical, mã native gọi `GetArrayLength`. Hàm này trông đơn giản, nhưng **đặc tả không cho phép suy ra mọi JNI API đều an toàn trong Critical**. Mỗi JNI transition có thể cần trạng thái runtime đặc biệt; GC có thể cần các thread đạt *safepoint*. Khi một thread giữ pin/critical guard rồi dùng JNI khác, JVM có thể phải đợi điều kiện mà chính thread đang trì hoãn.

Vì vậy quy tắc review hiệu quả hơn việc tự đoán “lệnh này có cấp phát không” là:

> **Sau Get Critical thành công, chỉ làm tính toán C/C++ ngắn trên dữ liệu đã chuẩn bị sẵn, rồi lập tức Release.**

Đặc tả có nêu việc **lồng các cặp Get/Release Critical** trong một số tình huống, nhưng đây không phải quyền gọi JNI bất kỳ; vẫn phải quản lý đầy đủ từng cặp và các hạn chế còn hiệu lực cho tới lần Release cuối cùng.

### 3.2. GC và safepoint: tác động mang tính hệ thống

Tùy JVM và cấu trúc dữ liệu, Get Critical có thể:

- Pin mảng hoặc ngăn việc di chuyển vùng nhớ có chứa mảng.
- Dùng bản sao tạm; khi đó vẫn yêu cầu Release để JVM hoàn tất hợp đồng sao chép/bộ nhớ.
- Làm GC/safepoint khó tiến triển hoặc phải chờ trong một số implementation/collector.

Không thể hứa “Get Critical luôn nhanh hơn `GetIntArrayRegion`” hay “GC sẽ luôn dừng hẳn khi có Critical”. **Chiến lược khác nhau giữa JVM/collector và phiên bản.** Chính vì rủi ro phụ thuộc implementation, native code phải tuân thủ giới hạn ngay cả khi `isCopy == JNI_TRUE`.

## 4. Quy trình an toàn: chuẩn bị → Get → tính toán → Release → tiếp tục

~~~text
Java gọi native method
         |
         v
[TRƯỚC CRITICAL]
- Kiểm tra tham số null / kích thước / phạm vi
- GetArrayLength hoặc GetStringLength
- Tạo vùng nhớ C cần dùng và xử lý JNI exception
- Chuẩn bị callback, class, method ID, lock nếu cần
         |
         v
GetPrimitiveArrayCritical / GetStringCritical
         |
       ptr == NULL ? ---> [Ngoài Critical] kiểm tra exception, báo lỗi
         |
         v
[TRONG CRITICAL]
- Vòng lặp ngắn, không chặn
- Chỉ đọc/ghi dữ liệu primitive hoặc jchar
- Không gọi JNI khác, không IO, không Java callback
         |
         v
ReleasePrimitiveArrayCritical / ReleaseStringCritical
         |
         v
[SAU CRITICAL]
- Kiểm tra/báo exception, logging, call Java
- Ghi kết quả, xử lý IO, trả giá trị về JVM
~~~

Một khi Get thành công, **mọi nhánh thoát phải đi qua Release**. Tránh `return`, `goto`, `break`, C++ exception hoặc long jump bỏ qua Release. Nếu xử lý có thể thất bại, lưu kết quả/lỗi vào biến C rồi Release trước khi chuyển sang JNI error handling.

Nên tách code thành ba phần có ranh giới rõ: **preparation**, **critical section**, **post-processing**. Tên hàm helper không bảo đảm an toàn; hãy kiểm tra cả những hàm được helper gọi bên trong.

## 5. Ví dụ đầy đủ: Java 17+ và C11

Ví dụ có hai phương thức:

- `sum(int[])` tính tổng năm số nguyên bằng `GetPrimitiveArrayCritical`, **chỉ đọc** mảng.
- `countA(String)` đếm ký tự ASCII `'a'` trong `"banana"` bằng `GetStringCritical`.

Cả hai đều lấy chiều dài **trước** Critical, không gọi JNI khác giữa Get/Release, rồi trả kết quả cho Java. Phép cộng dùng `jlong` để tránh tràn 32-bit với các giá trị ví dụ; phần chuỗi đếm theo **UTF-16 code units**.

### 5.1. Java: file `CriticalRegionDemo.java`

~~~java
import java.util.Objects;

public final class CriticalRegionDemo {
    static {
        System.loadLibrary("jnicritical");
    }

    private CriticalRegionDemo() {
    }

    private static native long sumNative(int[] values);

    private static native int countANative(String text);

    public static long sum(int[] values) {
        return sumNative(Objects.requireNonNull(values, "values"));
    }

    public static int countA(String text) {
        return countANative(Objects.requireNonNull(text, "text"));
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, 5};
        System.out.println("sum=" + sum(values));
        System.out.println("count a=" + countA("banana"));
    }
}
~~~

`Objects.requireNonNull` giúp Java từ chối null ở API public trước khi vào JNI. Hàm native C vẫn có kiểm tra phòng vệ để không bao giờ chuyển `NULL` vào API Critical.

### 5.2. Sinh JNI header

Trong thư mục chứa `CriticalRegionDemo.java`, dùng **JDK 17+**:

~~~bash
javac -h . CriticalRegionDemo.java
~~~

`javac` sinh `CriticalRegionDemo.class` và `CriticalRegionDemo.h`. Hai prototype quan trọng trong header:

~~~c
/* Khai báo tương đương trong header do javac -h tạo */
JNIEXPORT jlong JNICALL Java_CriticalRegionDemo_sumNative(
        JNIEnv *, jclass, jintArray);

JNIEXPORT jint JNICALL Java_CriticalRegionDemo_countANative(
        JNIEnv *, jclass, jstring);
~~~

Đừng tự sửa tên export; sử dụng header do JDK sinh để không sai signature khi Java class hoặc method đổi.

### 5.3. C: file `critical_demo.c`

~~~c
#include "CriticalRegionDemo.h"
#include <stddef.h>

/* Chỉ gọi ngoài vùng Critical. */
static void throw_null_pointer(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/NullPointerException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

/*
 * Get Critical có thể trả NULL. Đặc tả không bắt buộc
 * mọi lỗi NULL đều đi kèm pending exception.
 * Helper này chỉ được gọi KHI Get đã thất bại,
 * tức không có vùng Critical nào đang được giữ.
 */
static void throw_oom_if_needed(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    jclass type = (*env)->FindClass(
            env, "java/lang/OutOfMemoryError");
    if (type != NULL) {
        (*env)->ThrowNew(
                env, type, "Cannot obtain JNI critical data");
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jlong JNICALL Java_CriticalRegionDemo_sumNative(
        JNIEnv *env, jclass declaringClass, jintArray values) {
    (void) declaringClass;

    if (values == NULL) {
        throw_null_pointer(env, "values must not be null");
        return 0;
    }

    /* Mọi JNI call chuẩn bị đều diễn ra TRƯỚC Critical. */
    const jsize length = (*env)->GetArrayLength(env, values);
    if (length == 0) {
        return 0;
    }

    jint *elements = (jint *)(*env)->GetPrimitiveArrayCritical(
            env, values, NULL);
    if (elements == NULL) {
        /* Không có con trỏ được giữ; được dùng JNI để xử lý lỗi. */
        throw_oom_if_needed(env);
        return 0;
    }

    /* BẮT ĐẦU vùng Critical: chỉ tính toán C trên dữ liệu. */
    jlong total = 0;
    for (jsize i = 0; i < length; i++) {
        total += (jlong) elements[i];
    }

    /* KẾT THÚC vùng Critical trước khi quay về Java. */
    (*env)->ReleasePrimitiveArrayCritical(
            env, values, elements, JNI_ABORT);
    return total;
}

JNIEXPORT jint JNICALL Java_CriticalRegionDemo_countANative(
        JNIEnv *env, jclass declaringClass, jstring text) {
    (void) declaringClass;

    if (text == NULL) {
        throw_null_pointer(env, "text must not be null");
        return 0;
    }

    /* Số đơn vị UTF-16, lấy TRƯỚC Critical. */
    const jsize length = (*env)->GetStringLength(env, text);
    if (length == 0) {
        return 0;
    }

    const jchar *chars = (*env)->GetStringCritical(
            env, text, NULL);
    if (chars == NULL) {
        throw_oom_if_needed(env);
        return 0;
    }

    /* BẮT ĐẦU vùng Critical: không JNI, IO hoặc blocking. */
    jint count = 0;
    for (jsize i = 0; i < length; i++) {
        if (chars[i] == (jchar) 'a') {
            count++;
        }
    }

    /* KẾT THÚC vùng Critical. */
    (*env)->ReleaseStringCritical(env, text, chars);
    return count;
}
~~~

**Vì sao `JNI_ABORT` ở `sumNative`?** Hàm chỉ đọc mảng. Nếu JVM dùng bản sao, `JNI_ABORT` giải phóng bản sao **không copy-back**. Nếu JVM trả con trỏ trực tiếp, mode này không làm mảng bị hủy và không có bản sao để bỏ; Release vẫn bắt buộc. `countANative` không có mode vì API `ReleaseStringCritical` chỉ nhận `env, text, chars`.

**Vì sao kiểm tra `length == 0`?** Trả trực tiếp tránh mở vùng Critical không cần thiết. Code không dựa vào hành vi nhận con trỏ của một mảng/chuỗi rỗng.

**Vì sao dùng `throw_oom_if_needed`?** JNI Specification cho phép một số hàm trả `NULL` để báo lỗi mà không nhất thiết ném exception. Mã này chỉ chạy **sau khi Get thất bại**, không nằm trong vùng Critical, và bảo đảm Java không nhận nhầm giá trị `0` như kết quả thành công nếu Get không lấy được dữ liệu.

### 5.4. Biên dịch thư viện trên Linux

Thiết lập `JAVA_HOME` tới thư mục gốc của **JDK đang chạy JVM**; `jni.h` phải tồn tại trong `$JAVA_HOME/include`. Dùng GCC/Clang:

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  critical_demo.c -o libjnicritical.so
~~~

### 5.5. Biên dịch trên macOS

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  critical_demo.c -o libjnicritical.dylib
~~~

### 5.6. Biên dịch trên Windows x64

Trong **x64 Native Tools Command Prompt for Visual Studio**, với `JAVA_HOME` trỏ tới JDK x64:

~~~bat
cl /nologo /std:c11 /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" critical_demo.c /link /OUT:jnicritical.dll
~~~

Chọn **một** nhóm lệnh tương ứng OS; không dùng thư viện x86 trên JVM x64, hay binary của OS khác. Đặt file thư viện trong thư mục cùng `CriticalRegionDemo.class`.

### 5.7. Chạy và đọc kết quả

~~~bash
java -Djava.library.path=. CriticalRegionDemo
~~~

Stdout mong đợi:

~~~text
sum=15
count a=3
~~~

Giải thích: `1 + 2 + 3 + 4 + 5 = 15` và `"banana"` có ba ký tự `'a'`. Kết quả không dựa vào JVM dùng pin hay copy, vì code tuân thủ hợp đồng JNI và luôn gọi Release sau mỗi Get thành công.

**Điều kiện chạy:** JDK 17+; compiler C cho đúng OS/CPU; chạy tại thư mục có `.class` và shared library; `JAVA_HOME` trỏ JDK. Ví dụ không thực hiện IO, logging, callback hoặc JNI call **bên trong** một vùng Critical.

## 6. Đoạn sai: tại sao dễ deadlock hoặc làm chậm GC?

Đây là **anti-pattern minh họa, không chạy và không đưa vào sản phẩm**:

~~~c
/* SAI: đặt trong một JNI method có env, array, callback... */
jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (p == NULL) {
    return;
}

/* Cả ba thao tác sau đều sai trong vùng Critical. */
jsize length = (*env)->GetArrayLength(env, array);
(*env)->CallVoidMethod(env, callback, methodId);
log_to_file_or_network(p, length);

(*env)->ReleasePrimitiveArrayCritical(env, array, p, 0);
~~~

Các vấn đề:

- `GetArrayLength` là JNI call khác giữa Get/Release.
- `CallVoidMethod` có thể chạy Java code, cấp phát, chờ lock hoặc kích hoạt GC.
- `log_to_file_or_network` có thể chờ disk, socket, khóa nội bộ hoặc heap allocator.
- Nếu callback ném exception/nhảy khỏi luồng code, con trỏ có thể bị giữ quá lâu hoặc Release bị bỏ quên.

**Cách sửa:** lấy `length` và chuẩn bị đối số callback **trước Get**; trong Critical chỉ sao chép/tính toán nhỏ đã dự trù; **Release**; rồi mới gọi callback và ghi log. Nếu cần IO trực tiếp trên dữ liệu, hãy copy một phần vào buffer C riêng rồi Release trước khi làm IO.

### 6.1. Ví dụ sửa luồng (sơ đồ code)

~~~c
/* Minh họa về thứ tự; tên helper/biến phụ thuộc ứng dụng. */
jsize length = (*env)->GetArrayLength(env, array);
prepare_noncritical_state();     /* Có thể cấp phát, kiểm tra lỗi */

jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (p == NULL) {
    handle_error_outside_critical();
    return;
}

/* Chỉ CPU nhanh, tránh callback/IO/lock và JNI tùy ý. */
compute_a_small_result(p, length);

(*env)->ReleasePrimitiveArrayCritical(env, array, p, JNI_ABORT);

/* Lúc này đã ra khỏi Critical. */
call_java_callback_or_log();
~~~

Đây là **pseudocode C**, không biên dịch độc lập; `prepare_noncritical_state`/`compute_a_small_result`/`call_java_callback_or_log` là tên hàm mô tả. Khi code thật, phải kiểm tra rằng `compute_a_small_result` **không ẩn** JNI call, lock hay IO.

## 7. Release: mode `0`, `JNI_ABORT`, `JNI_COMMIT`

Với `ReleasePrimitiveArrayCritical`, tham số `mode` xử lý trường hợp JVM **dùng bản sao**:

| `mode` | Khi JVM tạo bản sao | Khi JVM trả con trỏ trực tiếp |
| --- | --- | --- |
| `0` | Copy-back các thay đổi (nếu có), giải phóng bản sao | Kết thúc việc giữ con trỏ; không có copy-back |
| `JNI_ABORT` | Bỏ thay đổi trong bản sao, giải phóng bản sao | Mode bị bỏ qua vì không có bản sao; **không thể dùng mode này để rollback ghi trực tiếp** |
| `JNI_COMMIT` | Copy-back nhưng **không giải phóng bản sao**; vẫn cần Release cuối | Mode không có tác dụng với buffer không phải bản sao |

**Điểm rất dễ sai:** `JNI_ABORT` là lựa chọn hợp lý cho **đọc thuần**, không phải cơ chế transaction/rollback. Nếu bạn **đã ghi vào con trỏ trực tiếp của mảng Java**, `JNI_ABORT` không hoàn tác được các thay đổi. Mã muốn **sửa mảng** thông thường nên Release với `mode = 0` và tự bảo đảm logic lỗi.

Không dùng `JNI_COMMIT` để “Release xong rồi” khi thực tế còn bản sao chưa được giải phóng; muốn hoàn tất phải có lần Release sau cùng theo đúng hợp đồng. Khi không có yêu cầu đặc biệt, **`0`** là cách đơn giản cho vùng ghi mảng; **`JNI_ABORT`** cho vùng chỉ đọc. Với `ReleaseStringCritical` **không có** tham số mode vì chuỗi Java là immutable từ góc nhìn Java và con trỏ chỉ đọc là `const jchar *`.

### 7.1. `isCopy` có ý nghĩa gì?

~~~c
/* Minh họa: kiểm tra isCopy SAU Release, không gọi JNI khi đang giữ. */
jboolean is_copy = JNI_FALSE;
jint *p = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, &is_copy);

if (p != NULL) {
    /* Chỉ đọc dữ liệu; không gọi JNI tùy ý ở đây. */
    jint first = p[0];  /* Chỉ hợp lệ khi array không rỗng! */
    (*env)->ReleasePrimitiveArrayCritical(
            env, array, p, JNI_ABORT);

    /* Có thể kiểm tra is_copy và first ngoài Critical. */
}
~~~

Đoạn này **minh họa, không chạy độc lập**; giả định `array` có ít nhất một phần tử. `JNI_TRUE` báo JVM đã tạo bản sao, `JNI_FALSE` báo có thể truy cập dữ liệu trực tiếp. Dù kết quả nào, bạn vẫn **phải Release**, không được block hoặc làm JNI call tùy ý trong vùng Critical. Hãy đo hiệu năng trên workload thực tế thay vì dùng `isCopy` để xây logic phụ thuộc implementation.

## 8. Ngoại lệ, null pointer, đường thoát và C++

Với cả hai hàm Get Critical:

- Tham số `jarray`/`jstring` phải hợp lệ, khác `NULL`. Kiểm tra ở Java hoặc trước khi Get bằng JNI hợp lệ.
- Hàm Get có thể trả **`NULL`** khi thất bại (chẳng hạn thiếu bộ nhớ). Không đọc, không Release một con trỏ `NULL` như thể Get thành công.
- Nếu Get trả `NULL`, **chưa có** critical pointer được giữ bởi lần Get đó. Đó là lúc có thể kiểm tra `ExceptionCheck`, bảo toàn pending exception hoặc báo lỗi theo hợp đồng.
- Nếu Get thành công, **mọi nhánh** phải Release trước khi trả về hoặc xử lý lỗi/exception ở JNI.
- Trong code C++, dùng scope/RAII phù hợp để bảo đảm Release khi có nhiều nhánh. Tuy nhiên không để C++ exception vượt qua biên JNI và **không** làm cleanup bằng các hàm có thể block trong critical destructor.

Mẫu luồng có biến trạng thái lỗi:

~~~c
/* Ý tưởng bên trong hàm JNI; chưa phải chương trình độc lập. */
jint status = 0;
jint *elements = (jint *)(*env)->GetPrimitiveArrayCritical(
        env, array, NULL);
if (elements == NULL) {
    return 0;      /* Xử lý lỗi sau Get thất bại ở mã thực */
}

/* Chỉ thực hiện thao tác thô an toàn. */
if (elements[0] < 0) {
    status = 1;    /* Ghi trạng thái, KHÔNG ThrowNew tại đây */
}

(*env)->ReleasePrimitiveArrayCritical(
        env, array, elements, JNI_ABORT);

/* Ra ngoài Critical, bây giờ mới được làm JNI error handling. */
if (status != 0) {
    /* Có thể ThrowNew hoặc gọi callback tại đây. */
}
~~~

Đoạn này giả định mảng không rỗng, được dùng để giải thích **thứ tự xử lý**, không thay cho kiểm tra null/length và lỗi trong code chạy ở phần 5.

**Không tự suy rằng JNI Critical là khóa chống truy cập đồng thời:** mảng có thể được quan sát/chỉnh sửa bởi Java threads khác theo quy tắc bộ nhớ và đồng bộ riêng; JNI không biến thao tác trên một mảng chung thành atomic hoặc thread-safe. Nếu cần snapshot nhất quán, hãy thiết kế đồng bộ **ở ngoài vùng Critical** hoặc copy dữ liệu vào vùng nhớ native độc lập.

## 9. Khi cần xử lý lâu hoặc chặn: chọn API khác

Giới hạn Critical là lý do cần **tránh giữ Java array/string pointer trong lúc chạy IO hoặc xử lý thời gian dài**. Một số lựa chọn:

| Nhu cầu | Lựa chọn phù hợp | Điều cần kiểm soát |
| --- | --- | --- |
| Đọc một đoạn `int[]` nhỏ vào C | `GetIntArrayRegion` | Buffer C đủ chỗ, offset/length hợp lệ |
| Ghi một đoạn `int[]` về Java | `SetIntArrayRegion` | Kiểm tra biên và pending exception |
| Đọc nhiều chunk và gọi IO giữa các chunk | Sao chép từng đoạn bằng `GetIntArrayRegion`, xử lý **ngoài vùng Critical** | Size chunk, overflow, đồng bộ dữ liệu |
| Đọc UTF-16 từ Java String | `GetStringRegion` hoặc `GetStringChars` / `ReleaseStringChars` | `jchar` là UTF-16 code unit, lifetime phù hợp |
| Đọc chuỗi dạng bytes cho C API | `GetStringUTFChars` / `ReleaseStringUTFChars` hoặc chuyển mã rõ ràng | JNI dùng **Modified UTF-8**, không đồng nhất UTF-8 chuẩn |
| Trao đổi buffer native lớn có lifetime riêng | `ByteBuffer.allocateDirect` + JNI DirectBuffer API hoặc FFM tùy JDK | Ownership, GC reachability, alignment và thread safety |

`Get<PrimitiveType>ArrayElements` và `GetStringChars` không có **cùng ràng buộc Critical nghiêm ngặt** theo API, nhưng JVM vẫn có thể dùng bản sao/pin. Vì vậy cũng cần Release sớm và tránh giữ con trỏ lâu không cần thiết. Nếu thao tác có thể kéo dài tùy input, thường dễ kiểm soát hơn khi **copy vào native-owned memory**, Release rồi mới xử lý.

### 9.1. Ví dụ copy theo chunk, sau đó mới xử lý IO

Đoạn C sau là helper **độc lập về thuật toán**; không có IO bên trong, và chỉ minh họa cấu trúc. Có thể thêm xử lý IO sau mỗi lần `GetIntArrayRegion` kết thúc, vì không có vùng Critical đang mở.

~~~c
#include <jni.h>
#include <stddef.h>

static jlong sum_chunks(JNIEnv *env, jintArray array) {
    enum { CHUNK = 1024 };
    jint buffer[CHUNK];

    jsize n = (*env)->GetArrayLength(env, array);
    jlong total = 0;

    for (jsize start = 0; start < n; ) {
        jsize size = n - start;
        if (size > CHUNK) {
            size = CHUNK;
        }

        (*env)->GetIntArrayRegion(
                env, array, start, size, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return 0;  /* Pending exception sẽ được xử lý ở caller. */
        }

        for (jsize i = 0; i < size; ++i) {
            total += (jlong) buffer[i];
        }
        start += size;
    }

    return total;
}
~~~

Helper giả định `array != NULL`; nếu dùng trong JNI method thật, kiểm tra trước và đảm bảo type/caller contract. `GetIntArrayRegion` copy ngay vào buffer C, nên sau khi call trả về **không giữ con trỏ vào Java heap**. Có thể chèn logging/IO giữa các chunk nếu hợp đồng ứng dụng cho phép, nhưng độ nhất quán khi mảng Java có writer khác vẫn cần đồng bộ riêng.

### 9.2. Quy trình IO an toàn với dữ liệu Java

Nếu một API native cần gửi `byte[]` qua socket:

1. Kiểm tra độ dài và quyền truy cập socket trước khi dùng dữ liệu.
2. Dùng `GetByteArrayRegion` để **copy một chunk** sang buffer C.
3. Đã kết thúc JNI copy call, có thể `send`/`write` trên chính buffer C đó, kể cả khi IO phải chặn.
4. Tiếp tục chunk tiếp theo khi cần; xác nhận phạm vi và consistency.

Nếu dùng Critical chỉ để copy một chunk rất nhỏ, phải **Release ngay sau copy**, rồi mới `send`. Không truyền pointer từ `GetPrimitiveArrayCritical` trực tiếp vào một `send` có thể chặn trong khi vẫn giữ Critical.

## 10. Hiệu năng: Critical không phải lựa chọn luôn tối ưu

Mục tiêu của các API Critical là giúp JVM có cơ hội cung cấp đường truy cập hiệu quả tới dữ liệu, nhưng điều đó **không bảo đảm zero-copy**. Việc một đoạn code có nhanh hơn hay không phụ thuộc:

- JVM/collector, phiên bản Java và chế độ GC.
- Kích thước mảng/chuỗi, số lần gọi JNI, số byte cần xử lý.
- Tần suất copy và chi phí pin/GC/safepoint.
- Mức độ tranh chấp giữa các Java threads, độ dài của critical section.
- Việc xử lý có thực sự ngắn và CPU-only hay không.

Một vòng lặp trên cả mảng cực lớn trong Critical dù không gọi JNI cũng có thể quá dài. Nên **giới hạn lượng việc mỗi lần giữ Critical**; với workload lớn, cân nhắc copy theo chunk. Đừng cố “cứ có `GetPrimitiveArrayCritical` là dùng” hoặc đo benchmark không có GC pressure rồi kết luận cho production.

Nên benchmark có dữ liệu đại diện và cả độ trễ GC/throughput/tail latency, không chỉ microbenchmark một lời gọi nhỏ.

## 11. Debug các lỗi vùng Critical

### 11.1. `-Xcheck:jni` trên HotSpot/OpenJDK

Với ví dụ phần 5:

~~~bash
java -Xcheck:jni -Djava.library.path=. CriticalRegionDemo
~~~

`-Xcheck:jni` có thể in cảnh báo khi phát hiện **JNI call khác giữa Get Critical và Release Critical**, ví dụ:

~~~text
Warning: Calling other JNI functions in the scope of
Get/ReleasePrimitiveArrayCritical or Get/ReleaseStringCritical
~~~

Đây là **ví dụ dạng cảnh báo**, không phải stdout của chương trình đúng. Với source hợp lệ ở phần 5, stdout ứng dụng vẫn là hai dòng `sum=15` và `count a=3`; không mong đợi cảnh báo trên. CheckJNI là công cụ phát hiện nhiều lỗi JNI, nhưng **không chứng minh code không bao giờ block** và không thay thế review các lời gọi C/C++ ẩn IO/lock.

### 11.2. Dấu hiệu cần điều tra

| Triệu chứng | Câu hỏi chẩn đoán | Hành động |
| --- | --- | --- |
| Pause GC kéo dài hoặc latency tăng khi native code hoạt động | Có thread nào giữ Critical quá lâu? | Giảm số phép tính, copy chunk rồi Release |
| Native method treo khi Java threads hoạt động mạnh | Có gọi Java callback, lock, IO dưới Critical? | Dời callback/IO/lock ra ngoài |
| `-Xcheck:jni` cảnh báo các lệnh JNI trong Critical | Có `GetArrayLength`, `ExceptionCheck` hoặc `FindClass` sau Get chưa Release? | Chuyển phần chuẩn bị/kiểm tra sang trước hoặc sau |
| Mảng không đổi sau khi native viết vào copy | Release nhầm `JNI_ABORT` | Với thay đổi cần giữ, dùng `mode = 0` |
| Dữ liệu sửa dù Release dùng `JNI_ABORT` | JVM trả pointer trực tiếp, không có bản sao để bỏ | Đừng coi `JNI_ABORT` là rollback |
| Crash / memory corruption sau Release | Native còn dùng pointer đã hết hiệu lực | Chấm dứt mọi truy cập ngay khi Release |
| Chuỗi nhận về sai ký tự/số lượng | Đang hiểu `jchar` như UTF-8 bytes hoặc như code points | `GetStringCritical` cho UTF-16 units; kiểm tra surrogate |
| Get trả `NULL` nhưng Java thấy kết quả `0` | Code không xử lý nhánh Get lỗi đúng hợp đồng | Kiểm tra pending exception và báo lỗi **ngoài Critical** |
| Chạy tốt ở một JDK nhưng chậm ở JDK/GC khác | Implementation có thể pin/copy khác nhau | Benchmark lại, cân nhắc Region API |

Không dùng `ExceptionDescribe`/`printf` để log khi đang giữ pointer; chỉ kiểm tra/log **sau khi Release**. Nếu phát hiện lỗi trong Critical, lưu một cờ hoặc mã lỗi ở biến C, Release rồi mới dùng JNI báo exception.

## 12. Checklist review code JNI Critical

- **Trước Get:** `jarray`/`jstring` không null, đã biết chiều dài, con trỏ output/buffer cần thiết có sẵn.
- **Sau Get:** luôn kiểm tra `ptr != NULL` trước truy cập; nếu thất bại, xử lý ngoài Critical.
- **Trong Critical:** chỉ vòng lặp C/C++ ngắn; **không tùy tiện gọi JNI**, không Java callback, không đợi mutex/condition, không file/socket IO có thể block.
- **Mọi nhánh:** Release khớp đúng Get, đúng object, đúng pointer; không bỏ qua khi có lỗi.
- **Mảng chỉ đọc:** có thể Release bằng `JNI_ABORT`; **mảng có ghi:** thường dùng `0`, không kỳ vọng `JNI_ABORT` hoàn tác ghi trực tiếp.
- **Chuỗi:** `const jchar *`, chiều dài UTF-16 lấy trước; `ReleaseStringCritical` không có mode.
- **Sau Release:** mới xử lý exception, log, callback, IO và tiếp tục dùng JNI.
- **Giữ lâu:** cân nhắc `Get/Set<PrimitiveType>ArrayRegion`, `GetStringRegion`, copy chunk hoặc vùng nhớ native riêng.
- **Đánh giá hiệu năng:** kiểm tra cả ứng xử GC và tail latency trên target JVM, không suy ra zero-copy từ tên API.

## 13. Câu hỏi ôn tập

**1.** Gọi `GetPrimitiveArrayCritical` có bảo đảm luôn nhận pointer trực tiếp tới Java heap?  
**Đáp án:** Không. JVM có thể pin hoặc trả bản sao; phải Release trong cả hai trường hợp và tuân thủ giới hạn Critical.

**2.** Có thể gọi `GetArrayLength` sau khi Get Critical để biết bao nhiêu phần tử cần đọc?  
**Đáp án:** Không nên; `GetArrayLength` là một JNI API khác. Lấy chiều dài **trước** khi mở Critical.

**3.** Vì sao `printf` hoặc socket `recv` bên trong Critical là ý tưởng nguy hiểm?  
**Đáp án:** IO/logging có thể chặn hoặc đợi lock; thread có thể giữ trạng thái cản trở GC/safepoint, tăng latency hoặc deadlock.

**4.** Nếu chỉ đọc `int[]` và JVM cấp bản sao, vì sao `JNI_ABORT` hợp lý?  
**Đáp án:** Không có thay đổi cần copy-back; JVM có thể giải phóng bản sao mà bỏ qua ghi ngược.

**5.** Có thể dùng `JNI_ABORT` để đảo ngược thay đổi sau khi sửa phần tử của mảng qua pointer Critical?  
**Đáp án:** Không. Nếu pointer trực tiếp tới mảng gốc, thay đổi đã xảy ra; mode bị bỏ qua khi không có bản sao.

**6.** `GetStringCritical` trả bytes UTF-8 hay các đơn vị UTF-16? Có cần NUL termination?  
**Đáp án:** `const jchar *` chứa đơn vị UTF-16; phải dùng `GetStringLength` lấy độ dài, không giả định chuỗi NUL-terminated.

**7.** Cần gọi `CallVoidMethod` để thông báo tiến trình Java sau mỗi chunk xử lý. Đặt lời gọi này ở đâu?  
**Đáp án:** **Sau** `Release...Critical`; nếu còn nhiều chunk thì có thể Get/Release từng chunk nhỏ rồi callback giữa các cặp.

**8.** Tại sao `-Xcheck:jni` không đủ để xác nhận code an toàn?  
**Đáp án:** Nó có thể cảnh báo JNI call trong Critical nhưng không chứng minh mọi hàm C/C++ gọi gián tiếp đều không block và không thay thế việc review lifetime/GC.

## 14. Tài liệu chuẩn

- [Oracle Java SE 17 — JNI: GetPrimitiveArrayCritical/ReleasePrimitiveArrayCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getprimitivearraycritical-releaseprimitivearraycritical): hợp đồng con trỏ, thời gian giữ, hạn chế JNI/blocking và Release mode.
- [Oracle Java SE 17 — JNI: GetStringCritical/ReleaseStringCritical](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#getstringcritical-releasestringcritical): truy cập UTF-16 và các hạn chế tương tự.
- [Oracle Java SE 17 — JNI: Get/Release Primitive Array Elements](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#releaseprimitivetypearrayelements-routines): ý nghĩa `0`, `JNI_COMMIT`, `JNI_ABORT`.
- [Oracle Java SE 17 — Troubleshooting: -Xcheck:jni](https://docs.oracle.com/en/java/javase/17/troubleshoot/command-line-options1.html): kiểm tra JNI và cảnh báo gọi JNI trong critical region.
- [Oracle Java SE 17 — JNI Specification Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): danh mục JNI APIs và trách nhiệm native caller.

**Ghi nhớ khi viết production code:** Vùng Critical càng ngắn và dễ kiểm chứng càng tốt. Lấy độ dài và chuẩn bị trước, giữ pointer chỉ để tính toán thô không chặn, luôn Release, rồi mới dùng lại JVM, callback, IO hoặc lock.
