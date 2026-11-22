# Những thao tác dọn dẹp được phép khi ngoại lệ JNI vẫn đang chờ

## Mục tiêu

Trong JNI, ngoại lệ Java được đánh dấu là **pending exception** (*ngoại lệ đang chờ*) trên thread hiện hành. Khi mã native gọi một phương thức Java qua `Call<Type>Method`, hoặc khi một JNI API thất bại và ném ngoại lệ, C/C++ **không tự động bị nhảy ra khỏi hàm** như khi Java thực thi `throw`. Native code tiếp tục chạy sau lời gọi đó. Tuy nhiên, **phần lớn JNI function không được gọi khi vẫn có pending exception**.

Mâu thuẫn bề ngoài: nếu phải dừng gọi JNI ngay, làm cách nào giải phóng con trỏ lấy từ `GetStringUTFChars`, mảng lấy từ `GetIntArrayElements`, các JNI references hay monitor đã khóa trước đó? JNI có một **danh sách ngoại lệ cụ thể**: một số API kiểm tra trạng thái, giải phóng tài nguyên và quản lý local frame vẫn được phép sử dụng trong khi lỗi đang chờ.

Bài này giúp bạn:

- Nhận ra một JNI call đã đặt pending exception, không hiểu nhầm `NULL` hoặc return value.
- Phân biệt **được phép gọi** với **nên gọi** trong đường xử lý lỗi.
- Thuộc nhóm JNI cleanup được đặc tả cho phép khi exception pending.
- Xử lý đúng `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`, `ReleaseString...`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`, `MonitorExit`, `PushLocalFrame` và `PopLocalFrame`.
- Phân biệt `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear` và `ExceptionDescribe`; tránh vô tình làm mất ngoại lệ gốc.
- Viết mã C có **một đường cleanup**, giải phóng các tài nguyên đã cấp phát một phần, trả ngoại lệ nguyên vẹn về Java.
- Biên dịch và chạy ví dụ Java 17 + JNI C có callback Java chủ động ném lỗi, trong khi native cleanup diễn ra an toàn.

## 1. Pending exception trong JNI thực sự là gì?

Xét luồng sau:

~~~text
Java gọi native method
       |
       v
C/JNI giữ một vài tài nguyên
       |
       v
C gọi ngược phương thức Java
       |
       v
Java ném IllegalStateException
       |
       v
C/JNI nhận lại quyền thực thi
       |
       +-- ExceptionCheck() == JNI_TRUE
       |
       +-- DỌN tài nguyên bằng JNI API được phép
       |
       v
C return; ngoại lệ vẫn pending
       |
       v
Java caller bắt IllegalStateException
~~~

Không giống Java, các lời gọi C/JNI thông thường không có cơ chế stack unwinding tự động cho Java exception. Nếu sau `CallStaticVoidMethod` có exception, CPU tiếp tục chạy statement C kế tiếp. Bạn phải **kiểm tra và chuyển sang nhánh lỗi**, hoặc chủ động clear rồi xử lý.

Ví dụ đúng về ý tưởng:

~~~c
(*env)->CallStaticVoidMethod(env, clazz, callback);

if ((*env)->ExceptionCheck(env)) {
    goto cleanup;  /* Không gọi thêm Java method ở đây. */
}

/* Chỉ đến đây nếu chưa có exception pending. */
~~~

Đây là **mảnh C minh họa** trong hàm JNI đã có `env`, `clazz`, `callback` và nhãn `cleanup`. `ExceptionCheck` không xóa exception. Nếu cleanup xong rồi return khỏi native method mà **không** `ExceptionClear`, JVM sẽ chuyển ngoại lệ sang Java caller như bình thường.

### Ba lựa chọn xử lý lỗi

1. **Chuyển tiếp lỗi nguyên bản — mặc định nên làm:** kiểm tra, dọn tài nguyên hợp lệ, return để Java caller thấy đúng throwable gốc.
2. **Xử lý và phục hồi có chủ đích:** lưu/quan sát ngoại lệ nếu cần, `ExceptionClear`, thực hiện logic xử lý hợp lệ sau khi không còn pending exception; đảm bảo ứng dụng định nghĩa rõ trường hợp có thể phục hồi.
3. **Chuyển đổi ngoại lệ có chủ đích:** sau khi dọn và clear, tạo/ném loại lỗi Java khác nếu hợp đồng API yêu cầu. Phải bảo toàn nguyên nhân nếu cần và thận trọng với thất bại cấp phát mới. Không âm thầm thay thế exception chỉ để log hoặc “cho chạy tiếp”.

**Không** phải lựa chọn hợp lệ: bỏ qua `ExceptionCheck` rồi tùy tiện gọi `FindClass`, `NewStringUTF`, `GetMethodID`, `CallObjectMethod` hoặc `GetArrayLength` trong khi ngoại lệ vẫn pending.

## 2. Danh sách chính thức: những lời gọi được phép

Theo phần **Exception Handling** trong đặc tả JNI của Java SE 17, có các nhóm sau (tên viết theo kiểu giao diện JNI; trong C dùng `(*env)->Method(env, ...)`):

| Nhóm | API được phép khi pending | Tác dụng và lưu ý |
|---|---|---|
| Kiểm tra/điều khiển exception | `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear` | Xem trạng thái, lấy reference throwable, in chẩn đoán hoặc clear; **hai API sau có tác dụng phụ quan trọng** |
| Xóa references | `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef` | Giải phóng ownership của đúng loại JNI reference đã tạo/giữ |
| Trả bộ đệm string | `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical` | Trả con trỏ đã lấy bằng Get tương ứng, không phải giải phóng `jstring` |
| Trả bộ đệm primitive array | `Release<PrimitiveType>ArrayElements`, `ReleasePrimitiveArrayCritical` | Trả con trỏ đã lấy bằng Get tương ứng; đúng mode và đúng array |
| Quản lý local frame | `PushLocalFrame`, `PopLocalFrame` | Được liệt kê trong danh sách; không có nghĩa nên cấp phát một frame mới giữa đường lỗi |
| Giải phóng monitor | `MonitorExit` | Chỉ dùng để thoát một monitor đã được chính luồng đó sở hữu hợp lệ |
| Invocation API đặc biệt | `DetachCurrentThread` | Đặc tả Java SE liệt kê; đây là thao tác `JavaVM` của **thread native đã attach**, không phải lời gọi dọn dẹp thường lệ của native method |

**Đếm theo từng mục API:** 4 exception + 3 reference + 3 string + 2 array + 2 local-frame + 1 monitor + 1 detach = 16 dạng hàm được liệt kê ở đặc tả Java SE. `Release<PrimitiveType>ArrayElements` thực tế là **một họ tám hàm** theo kiểu array, chứ không phải một function tên literal như vậy.

Các ví dụ cụ thể của họ Release:

~~~c
(*env)->ReleaseBooleanArrayElements(env, booleans, boolean_ptr, JNI_ABORT);
(*env)->ReleaseByteArrayElements(env, bytes, byte_ptr, JNI_ABORT);
(*env)->ReleaseIntArrayElements(env, ints, int_ptr, JNI_ABORT);
(*env)->ReleaseDoubleArrayElements(env, doubles, double_ptr, JNI_ABORT);
~~~

Đoạn trên **chỉ minh họa tên API**, không phải mã chạy độc lập; mỗi `array` và `pointer` phải là cặp đã được lấy thành công bằng chính hàm Get tương ứng. Có thể dùng mode `0` hoặc `JNI_ABORT` tùy thay đổi có cần ghi ngược; không truyền pointer tùy ý và không “release” hai lần.

### `DetachCurrentThread` không đồng nghĩa “được detach mọi lúc”

`DetachCurrentThread` thuộc **JNI Invocation Interface** trên `JavaVM*`, không phải bảng hàm `JNIEnv*`. Đặc tả Java SE có liệt kê nó trong ngữ cảnh pending exception; nhưng nó chỉ có ý nghĩa trong luồng native đã attach và phải tuân theo điều kiện detach của JVM. Một native method đang được gọi từ Java không nên tự detach chính Java thread đó. Với hầu hết hàm JNI thông thường, đường cleanup chỉ cần các nhóm exception, reference, release và monitor.

Tài liệu Android JNI tips liệt kê các hàm `JNIEnv` liên quan, không đưa `DetachCurrentThread` vào cùng bảng. Khi viết thư viện đa runtime, đối chiếu điều kiện của chính môi trường mà bạn chạy, thay vì coi detach là biện pháp chữa mọi ngoại lệ.

## 3. Những JNI call *không* được phép khi exception còn pending

| Không gọi trong trạng thái pending | Vì sao/cách thay thế |
|---|---|
| `FindClass`, `GetMethodID`, `GetFieldID` | Đây là tra cứu có thể load/initialize class hoặc phát sinh lỗi; nếu cần, thực hiện **trước** thao tác có thể ném hoặc sau khi clear có chủ đích |
| `NewObject`, `NewStringUTF`, `New<Type>Array` | Cấp phát Java object khi thread đang có exception là sai trình tự |
| `Call<Type>Method`, `CallStatic<Type>Method` | Không tiếp tục callback Java khi vẫn pending exception |
| `GetObjectClass`, `GetObjectField`, `SetObjectField` | Không dùng để dò/ghi dữ liệu Java giữa đường cleanup |
| `GetArrayLength`, `Get<Type>ArrayRegion`, `Set<Type>ArrayRegion` | Không lấy thêm dữ liệu mảng trong lúc pending; các region API **không phải Release** |
| `GetStringUTFChars`, `Get<Type>ArrayElements`, `GetPrimitiveArrayCritical` | Không lấy pointer mới; chỉ **trả** pointer đã lấy trước đó bằng Release tương ứng |
| `NewLocalRef`, `NewGlobalRef`, `EnsureLocalCapacity` | Không tạo thêm reference/capacity tùy ý; `Delete...Ref` mới là nhóm cleanup cho phép |
| `MonitorEnter` | Không khóa thêm monitor khi pending; chỉ `MonitorExit` cho lock cần nhả |
| `Throw`, `ThrowNew` | Không thay exception pending một cách tùy tiện; nếu cần thay, **clear trước rồi thực hiện luồng xử lý lỗi mới** |

**Điểm dễ nhầm:** một function “có vẻ vô hại” không tự động được phép. `GetArrayLength` chỉ đọc độ dài nhưng **không có trong danh sách an toàn**. `NewLocalRef` không gọi Java callback nhưng vẫn không thuộc danh sách. Ngược lại `ReleaseIntArrayElements` và `DeleteLocalRef` **được liệt kê riêng** vì phải cho phép cleanup trong tình trạng lỗi.

Một số JNI function có thể hoạt động trên một JVM cụ thể dù dùng sai khi pending exception; điều đó **không biến hành vi ấy thành portable JNI contract**. Khi bật CheckJNI hoặc chạy trên JVM khác, code sai có thể bị cảnh báo, báo lỗi hoặc gây hỏng trạng thái VM.

## 4. Bốn hàm Exception: cùng được phép nhưng ngữ nghĩa khác nhau

| JNI API | Giá trị trả về | Giữ pending exception? | Trường hợp sử dụng |
|---|---|---|---|
| `ExceptionCheck(env)` | `jboolean` | **Có** | Hỏi “hiện có pending exception không?” mà không tạo reference throwable |
| `ExceptionOccurred(env)` | `jthrowable` local reference hoặc `NULL` | **Có** | Lấy reference đến throwable để bảo toàn hoặc xử lý tiếp |
| `ExceptionClear(env)` | `void` | **Không** | **Cố ý** xóa trạng thái pending để có thể dùng JNI bình thường |
| `ExceptionDescribe(env)` | `void` | **Không** | In exception/backtrace vào kênh lỗi hệ thống **và clear pending như một tác dụng phụ** |

**Cảnh báo quan trọng: `ExceptionDescribe` không đơn thuần là “in log mà vẫn giữ lỗi”.** Đặc tả Oracle nêu rõ nó **clear pending exception** khi in thông tin. Nếu bạn gọi `ExceptionDescribe` chỉ để debug rồi return, Java caller có thể **không còn nhận được ngoại lệ gốc**.

Mẫu kiểm tra nhưng giữ lỗi:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* Không gọi ExceptionClear hoặc ExceptionDescribe. */
    goto cleanup;
}
~~~

Mẫu lấy reference tới throwable, giữ nguyên pending:

~~~c
jthrowable failure = (*env)->ExceptionOccurred(env);
if (failure != NULL) {
    /* failure là local JNI reference; exception VẪN pending. */
    (*env)->DeleteLocalRef(env, failure);
    goto cleanup;
}
~~~

Cả hai chỉ là **mảnh C trong một hàm JNI** có `env` và `cleanup`. `ExceptionOccurred` cho một local reference; nếu giữ nó chỉ để kiểm tra rồi không dùng, `ExceptionCheck` gọn hơn và tránh thêm local reference.

### Khi thực sự cần clear rồi khôi phục ngoại lệ

Một pattern có thể dùng trong mã xử lý lỗi chuyên biệt (không cần thiết cho đường return thông thường):

~~~c
jthrowable original = (*env)->ExceptionOccurred(env);
if (original != NULL) {
    (*env)->ExceptionClear(env);

    /*
     * Tới đây không còn pending exception.
     * Có thể thực hiện xử lý có chủ đích, nhưng JNI calls vẫn có
     * thể thất bại; không giả định mọi thao tác luôn thành công.
     */

    (*env)->Throw(env, original);
    (*env)->DeleteLocalRef(env, original);
}
~~~

Đây là **mảnh mã minh họa**, không phải hàm C chạy độc lập. `Throw` ở đây chỉ được gọi **sau khi `ExceptionClear`**, nên không vi phạm danh sách. Ngay khi `Throw` thành công, exception pending trở lại, vì vậy `DeleteLocalRef` ở dòng cuối hợp lệ. Code sản xuất còn phải kiểm tra kết quả `Throw` và tình trạng ngoại lệ phát sinh trong phần xử lý trung gian.

**Nếu bạn chỉ muốn giữ nguyên throwable, không cần chu trình clear/rethrow.** Việc này có thể làm mất lỗi gốc khi bước xử lý giữa chừng lỗi do thiếu bộ nhớ hay lookup khác.

## 5. Nguyên tắc quản lý tài nguyên: chỉ release thứ đã acquire thành công

Native function có thể đã lấy **một phần** tài nguyên trước khi Java exception xảy ra. Mô hình an toàn trong C là:

1. Khởi tạo **mọi pointer và JNI reference sở hữu** về `NULL` trước các lời gọi có thể thất bại.
2. Acquire tuần tự; sau mỗi bước thất bại, chuyển đến **một nhãn cleanup**.
3. Khi callback Java ném exception, chỉ `ExceptionCheck` hoặc `ExceptionOccurred`; dừng các JNI call không thuộc whitelist.
4. Cleanup (thường đảo thứ tự acquire) bằng Release/Delete API được phép; gọi `free`/`fclose`/`close` phù hợp cho tài nguyên **C/native**, nếu có.
5. Return với **pending exception còn nguyên**; Java caller sẽ nhận được lỗi.

Khung phổ biến:

~~~c
const char *utf = NULL;
jint *items = NULL;
jobject global_ref = NULL;
jclass local_cls = NULL;

/* Acquire một số tài nguyên; kiểm tra từng kết quả. */
/* ... */
/* Call Java callback có thể ném exception. */

if ((*env)->ExceptionCheck(env)) {
    goto cleanup;
}

/* Các bước tiếp theo chỉ khi chưa có exception. */

cleanup:
    if (global_ref != NULL) {
        (*env)->DeleteGlobalRef(env, global_ref);
    }
    if (items != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, java_array, items, JNI_ABORT);
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, java_string, utf);
    }
    if (local_cls != NULL) {
        (*env)->DeleteLocalRef(env, local_cls);
    }
    return;
~~~

Đây là **khung C minh họa**, không thể biên dịch độc lập vì cần `env`, `java_array`, `java_string`, các bước acquire và hàm trả `void`. Nó cho thấy các thao tác cleanup được phép thực hiện **ngay khi exception vẫn pending**.

**Vì sao khởi tạo `NULL`?** Bất kỳ acquire nào có thể thất bại, do đó nhánh cleanup cần biết chính xác tài nguyên nào đã được lấy. Không gọi `ReleaseStringUTFChars` với pointer không phải kết quả Get hợp lệ, không dùng `DeleteGlobalRef` cho local ref, không gọi `free` đối với pointer do JNI quản lý.

## 6. Ví dụ chạy được Java 17 + JNI C: Java ném lỗi, C vẫn dọn tài nguyên

Ví dụ dùng một native method `callAndClean` nhận `String` và `int[]`. Nó:

1. Lấy method ID Java **trước** khi có lỗi.
2. Tạo một local reference, lấy chuỗi UTF và primitive array elements, tạo global reference.
3. Gọi ngược một Java method cố ý ném `IllegalStateException`.
4. Khi exception pending, dùng **chỉ những JNI cleanup API được phép**.
5. Return sang Java; Java bắt được đúng exception ban đầu.

### 6.1. File Java: `PendingCleanupDemo.java`

~~~java
public final class PendingCleanupDemo {
    static {
        System.loadLibrary("pendingcleanupdemo");
    }

    private static native void callAndClean(
            String text, int[] values);

    private static void alwaysFails() {
        throw new IllegalStateException("boom from Java callback");
    }

    public static void main(String[] args) {
        try {
            callAndClean("hello JNI", new int[] {2, 4, 6});
            System.out.println("unexpected success");
        } catch (IllegalStateException error) {
            System.out.println(
                    "caught=" + error.getClass().getSimpleName());
            System.out.println("message=" + error.getMessage());
        }

        System.out.println("continued=true");
    }
}
~~~

Java source này không cần tự tạo JNI reference; tham số `String` và `int[]` được runtime truyền sang C qua `jstring` và `jintArray`. Java `alwaysFails()` được gọi từ C bằng JNI, và nội dung của nó được cố định để kiểm tra exception propagation.

### 6.2. Sinh header và định nghĩa JNI C

Chạy với JDK 17+:

~~~bash
javac -h . PendingCleanupDemo.java
~~~

Lệnh tạo `PendingCleanupDemo.class` và header `PendingCleanupDemo.h`. Giữ header và mã C trong cùng thư mục để các lệnh build bên dưới tìm thấy nhau.

File `pendingcleanupdemo.c`:

~~~c
#include "PendingCleanupDemo.h"

JNIEXPORT void JNICALL
Java_PendingCleanupDemo_callAndClean(
        JNIEnv *env, jclass declaring_class,
        jstring text, jintArray values) {

    jmethodID fail_method = NULL;
    jclass local_class = NULL;
    const char *utf = NULL;
    jint *elements = NULL;
    jobject global_text = NULL;

    /* Kiểm tra tham số trước khi có exception pending. */
    if (text == NULL || values == NULL) {
        jclass npe = (*env)->FindClass(
                env, "java/lang/NullPointerException");
        if (npe != NULL) {
            (*env)->ThrowNew(env, npe,
                    "text and values must be non-null");
            (*env)->DeleteLocalRef(env, npe);
        }
        return;
    }

    /* Lookup phải xong TRƯỚC callback có thể ném. */
    fail_method = (*env)->GetStaticMethodID(
            env, declaring_class, "alwaysFails", "()V");
    if (fail_method == NULL) {
        return; /* Để nguyên lỗi lookup/class initialization. */
    }

    /* Local reference minh họa: sở hữu và cần DeleteLocalRef. */
    local_class = (*env)->FindClass(env, "java/lang/Object");
    if (local_class == NULL) {
        goto cleanup;
    }

    /* Bộ đệm thuộc JNI: phải ReleaseStringUTFChars. */
    utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        goto cleanup;
    }

    /* Bộ đệm thuộc JNI: phải ReleaseIntArrayElements. */
    elements = (*env)->GetIntArrayElements(env, values, NULL);
    if (elements == NULL) {
        goto cleanup;
    }

    /* Global JNI reference: phải DeleteGlobalRef. */
    global_text = (*env)->NewGlobalRef(env, text);
    if (global_text == NULL) {
        goto cleanup;
    }

    /*
     * Java callback luôn ném IllegalStateException.
     * C KHÔNG tự unwind khi callback ném.
     */
    (*env)->CallStaticVoidMethod(
            env, declaring_class, fail_method);

    if ((*env)->ExceptionCheck(env)) {
        goto cleanup; /* Giữ nguyên pending exception. */
    }

cleanup:
    /*
     * Mỗi thao tác JNI bên dưới được phép khi exception pending.
     * Đảo thứ tự acquire, chỉ release tài nguyên đã có.
     */
    if (global_text != NULL) {
        (*env)->DeleteGlobalRef(env, global_text);
    }
    if (elements != NULL) {
        (*env)->ReleaseIntArrayElements(
                env, values, elements, JNI_ABORT);
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, text, utf);
    }
    if (local_class != NULL) {
        (*env)->DeleteLocalRef(env, local_class);
    }

    /*
     * KHÔNG gọi ExceptionClear hoặc ExceptionDescribe.
     * Java caller sẽ nhận đúng IllegalStateException.
     */
}
~~~

**Giải thích về tính đúng đắn:**

- `GetStaticMethodID`, `FindClass`, `GetStringUTFChars`, `GetIntArrayElements`, `NewGlobalRef` đều được gọi **trước** callback tạo exception. Nếu acquire thất bại, goto cleanup; có thể đã có lỗi JNI pending, nên cleanup vẫn phải dùng whitelist.
- `local_class` là local reference tạo bởi `FindClass`; nó phải được `DeleteLocalRef` khi không cần. `declaring_class` được JVM cung cấp cho native method, code không tự xóa.
- `utf` chỉ hợp lệ sau khi `GetStringUTFChars` thành công; `elements` chỉ hợp lệ sau khi `GetIntArrayElements` thành công. Không dùng `free(utf)` hay `free(elements)`.
- `global_text` có ownership riêng và phải `DeleteGlobalRef`; không được thay bằng `DeleteLocalRef`.
- Trong ví dụ không sửa phần tử `elements`, nên chọn `JNI_ABORT` để loại bỏ việc copy-back của **bản sao**. Không sử dụng `JNI_ABORT` để hứa hoàn tác dữ liệu đã sửa nếu JVM cho phép truy cập pinned storage trực tiếp.
- `ExceptionCheck` cho phép nhảy vào cleanup; tất cả JNI function được gọi trong cleanup có mặt trong danh sách được phép khi pending. Không có thêm `FindClass` hoặc callback Java trong đường lỗi này.
- `goto cleanup` ở đây không bỏ qua biến chưa khởi tạo: toàn bộ các biến sở hữu tài nguyên đã đặt `NULL` ngay đầu hàm.
- Nếu callback không ném (khác với `alwaysFails` của demo), luồng vẫn đi tới cleanup và return bình thường.

### 6.3. Build theo hệ điều hành

Thư viện phải được biên dịch với **JDK header** và compiler đúng kiến trúc của tiến trình JVM đang chạy. Các lệnh dưới đây là các phương án độc lập, chọn đúng hệ điều hành của bạn.

**Linux — GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  pendingcleanupdemo.c -o libpendingcleanupdemo.so

java -Djava.library.path=. PendingCleanupDemo
~~~

**macOS — Clang:**

~~~bash
clang -std=c11 -Wall -Wextra -dynamiclib \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  pendingcleanupdemo.c -o libpendingcleanupdemo.dylib

java -Djava.library.path=. PendingCleanupDemo
~~~

**Windows — MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" pendingcleanupdemo.c /Fe:pendingcleanupdemo.dll
java -Djava.library.path=. PendingCleanupDemo
~~~

Đảm bảo `JAVA_HOME` là JDK đầy đủ, không chỉ JRE; trên Windows chạy trong môi trường MSVC Developer Command Prompt có cấu hình compiler. `System.loadLibrary("pendingcleanupdemo")` sử dụng tên logic, còn JVM map sang `libpendingcleanupdemo.so`/`libpendingcleanupdemo.dylib`/`pendingcleanupdemo.dll` theo nền tảng.

### 6.4. Đầu ra mong đợi

Với binary được biên dịch và nạp thành công:

~~~text
caught=IllegalStateException
message=boom from Java callback
continued=true
~~~

Chương trình **không** in `unexpected success` vì exception từ Java callback lan qua native method về `main`. Java catch xử lý lỗi rồi thực thi `System.out.println("continued=true")`.

Đầu ra xác minh **exception gốc vẫn được chuyển về Java**; nó không phải công cụ chứng minh mọi resource đã release ở mọi lỗi hiếm gặp. Kiểm tra code review, native leak detector và thử các trường hợp acquire thất bại vẫn cần thiết cho ứng dụng thực.

## 7. Các nhóm cleanup và bẫy liên quan

### 7.1. `DeleteLocalRef`, `DeleteGlobalRef` và `DeleteWeakGlobalRef`

**Ba loại reference khác nhau, ba vòng đời khác nhau:**

- Local reference: ví dụ `FindClass`, `NewObject`, `ExceptionOccurred`; có hiệu lực trong local reference frame của thread. Dọn thủ công bằng `DeleteLocalRef` hoặc qua `PopLocalFrame`; JVM tự dọn local refs còn lại khi native method return, nhưng trong vòng lặp/lời gọi dài có thể cần dọn sớm.
- Global reference: được tạo bằng `NewGlobalRef`, tồn tại qua native calls cho đến khi `DeleteGlobalRef`; không bị auto-delete khi hàm hiện tại return.
- Weak global reference: được tạo bằng `NewWeakGlobalRef`; dọn bằng `DeleteWeakGlobalRef` và không coi nó là strong reference giữ object sống.

Các API delete **không** cần `ExceptionClear` trước. Tuy nhiên, việc delete phải đúng reference hợp lệ và đúng ownership. Một reference đã delete không được tiếp tục sử dụng; đừng delete cùng một reference hai lần. `DeleteLocalRef` không phải cách “free Java object”: đối tượng do GC quản lý; delete chỉ bỏ một JNI root/reference.

### 7.2. `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`

Hàm nào Get thì dùng **Release cùng cặp**:

| Acquire thành công trước lỗi | Release hợp lệ trong trạng thái pending |
|---|---|
| `GetStringChars(env, str, ...)` | `ReleaseStringChars(env, str, chars)` |
| `GetStringUTFChars(env, str, ...)` | `ReleaseStringUTFChars(env, str, utfChars)` |
| `GetStringCritical(env, str, ...)` | `ReleaseStringCritical(env, str, chars)` |

Con trỏ do Get cấp có thể là copy hoặc vùng được JVM giữ/pin; không tự `free`, không giữ sau khi đã Release. `GetStringUTFChars` cung cấp modified UTF-8 theo JNI, không nhất thiết trùng UTF-8 thông thường trong mọi trường hợp ký tự đặc biệt.

Với `GetStringCritical`, vùng critical có **ràng buộc bổ sung**: hạn chế gọi JNI khác và thao tác blocking trong khi giữ pointer. Khi lỗi xảy ra, ưu tiên release critical nhanh bằng `ReleaseStringCritical` (được phép khi pending), rồi mới thực hiện công việc native không liên quan nếu thực sự cần.

### 7.3. `Release<PrimitiveType>ArrayElements` và release mode

Các API như `GetIntArrayElements` có thể trả bản sao hoặc pointer đến dữ liệu mà JVM đang giữ. Sau khi đã lấy thành công, **phải** gọi `ReleaseIntArrayElements` với cùng `array` và `elements`, kể cả khi Java callback ném lỗi.

| `mode` | Ý nghĩa khi `elements` là copy | Lưu ý |
|---|---|---|
| `0` | Copy ngược nội dung và giải phóng buffer | Thường chọn khi native muốn commit thay đổi |
| `JNI_ABORT` | Giải phóng bản sao mà **không** copy ngược | Phù hợp nếu chỉ đọc; không thể “undo” thay đổi đã ghi trực tiếp khi không có copy |
| `JNI_COMMIT` | Copy ngược nhưng **không giải phóng buffer copy** | Nếu là copy, cần một lần Release cuối với `0` hoặc `JNI_ABORT` để giải phóng |

Ví dụ khi chỉ đọc mảng và Java callback ném:

~~~c
if (elements != NULL) {
    (*env)->ReleaseIntArrayElements(
            env, array, elements, JNI_ABORT);
}
~~~

Đây là **mảnh code minh họa** khi `elements` đến từ `GetIntArrayElements(env, array, ...)` thành công. Không gọi `ReleaseIntArrayElements` với con trỏ của `malloc` hoặc với pointer của mảng kiểu khác. Dù pending exception do nguyên nhân hoàn toàn không liên quan đến mảng, Release vẫn là nghĩa vụ quản lý lifetime.

Các kiểu khác dùng đúng họ: `ReleaseByteArrayElements`, `ReleaseLongArrayElements`, `ReleaseFloatArrayElements`,… Không có JNI API tổng quát tên literal `ReleaseArrayElements`.

### 7.4. `ReleasePrimitiveArrayCritical`

Nếu đã gọi `GetPrimitiveArrayCritical`, phải gọi `ReleasePrimitiveArrayCritical` ngay khi xong, kể cả lúc có pending exception. `GetPrimitiveArrayCritical` **không** nằm trong whitelist cho pending exception; chỉ có **Release**. Khi ở critical region, tránh những thao tác có thể block hoặc JNI calls không được cho phép theo hợp đồng critical access. Không giữ vùng critical để ghi log mạng, cấp phát thêm Java object hoặc chờ khóa dài.

### 7.5. `MonitorExit`

`MonitorExit` là JNI function cho phép khi exception pending, nhằm giải phóng monitor mà **thread hiện tại đã acquire hợp lệ**, ví dụ từ một lời gọi `MonitorEnter` thành công trước đó.

~~~c
jint entered = (*env)->MonitorEnter(env, lock);
if (entered != JNI_OK) {
    return; /* Không gọi MonitorExit nếu chưa acquire. */
}

/* ... Gọi Java code có thể ném exception ... */

/* MonitorExit được phép dù callback vừa ném exception. */
(*env)->MonitorExit(env, lock);
return;
~~~

Đây là **mảnh C minh họa**, không phải hàm tự chạy. Nó giả định `env` và `lock` hợp lệ, và không có JNI call không hợp lệ chen giữa. Trong mã thực, vẫn cần kiểm tra kết quả `MonitorExit`. Đừng gọi `MonitorExit` trên monitor chưa sở hữu hoặc gọi thừa lần vì có thể phát sinh `IllegalMonitorStateException` và làm lỗi khó chẩn đoán hơn. **`MonitorEnter` không nằm trong danh sách** được gọi sau khi exception đã pending.

Ngoài ra, native code không được tùy tiện release monitor do phương thức Java `synchronized` tự động quản lý. Chỉ dọn những lock mà native code thực sự sở hữu theo giao thức của nó.

### 7.6. `PushLocalFrame` và `PopLocalFrame`

JNI cho phép cả hai API này trong danh sách pending-exception. Tuy vậy, ở đường cleanup, thao tác thường cần là **`PopLocalFrame` của một frame đã được tạo trước lỗi**, không phải `PushLocalFrame` để tạo mới.

Một pattern chuẩn:

~~~c
if ((*env)->PushLocalFrame(env, 16) < 0) {
    return; /* Có thể đã có lỗi, không có frame mới. */
}

/* Trong frame này: tạo local refs, gọi Java callback... */

if ((*env)->ExceptionCheck(env)) {
    (*env)->PopLocalFrame(env, NULL);
    return; /* Giữ pending exception. */
}

(*env)->PopLocalFrame(env, NULL);
~~~

Đây là **đoạn minh họa trong native method trả `void`**, không phải chương trình độc lập. `PushLocalFrame` được thực hiện **trước** callback, khi chưa có exception. `PopLocalFrame(env, NULL)` làm sạch local refs của frame dù lỗi còn pending. Không dùng local ref thuộc frame đó sau khi frame đã pop.

**Phân biệt:** `PopLocalFrame` xử lý local references, **không tự giải phóng** con trỏ nhận từ `GetStringUTFChars` hay `GetIntArrayElements`, cũng không xóa global refs hoặc giải phóng native `malloc`. Các nghĩa vụ release này tồn tại độc lập; phải thực hiện đúng thứ tự trước/sau frame cleanup theo những references cần dùng.

## 8. Native resources không thuộc JNI: vẫn phải dọn

Pending exception là một hạn chế **đối với lời gọi JNI**; nó không tự động cấm các lệnh native C như `free(buffer)` hoặc thao tác cleanup phù hợp đối với file descriptor, socket, `FILE*`, mutex native. Tuy nhiên, quản lý C resource phải theo đúng ownership:

~~~c
void *heap = malloc(1024);
if (heap == NULL) {
    /* Báo lỗi theo hợp đồng trước khi tiếp tục. */
    return;
}

/* ... Có thể xảy ra pending Java exception ... */

free(heap);  /* Không phải JNI call. */
return;
~~~

Đây là **mảnh code C** giả định có `#include <stdlib.h>`. Nó không có `JNIEnv*` nên chỉ minh họa native ownership.

**Không đánh đồng hai loại con trỏ:**

- `malloc`/`calloc` → dùng `free` khi sở hữu.
- `GetStringUTFChars` → dùng `ReleaseStringUTFChars`.
- `GetIntArrayElements` → dùng `ReleaseIntArrayElements`.
- `NewGlobalRef` → dùng `DeleteGlobalRef`.
- `NewLocalRef`/`FindClass`/`NewObject` → dọn bằng `DeleteLocalRef` hoặc local frame đúng cách.

C++ RAII có thể gói những thao tác release này trong destructor để tránh quên cleanup, nhưng destructor chạy trên đường exception pending vẫn phải **chỉ gọi các JNI API được phép**, và destructor không được tự ném C++ exception ra khỏi JNI boundary. Java exception **không tự kích hoạt** C++ stack unwinding; muốn chạy destructor RAII, control flow C++ phải rời scope bình thường hoặc theo cơ chế C++ của chính nó.

## 9. Giữ lỗi gốc khi log và chuyển đổi exception

### Không gọi `ExceptionDescribe` chỉ để “xem thử”

Sai về mặt giữ nguyên ngoại lệ:

~~~c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env);
    return; /* ExceptionDescribe đã clear pending exception! */
}
~~~

Điều này thường làm Java caller không nhận được exception như dự định. `ExceptionDescribe` hữu ích trong debugging, nhưng nếu muốn vừa in stack trace vừa giữ throwable, phải chủ động xử lý việc bảo tồn/khôi phục trạng thái; cách đó phức tạp và có thể sinh lỗi mới. Trong sản phẩm, thường tốt hơn là **return với pending exception còn nguyên để Java log** bằng cơ chế logging/handler thông thường.

### Không gọi `ThrowNew` trước khi clear

Sai:

~~~c
if ((*env)->ExceptionCheck(env)) {
    /* Sai: đang có một Java exception pending. */
    (*env)->ThrowNew(env, cached_exception_class, "different error");
}
~~~

Đoạn trên chỉ minh họa một **anti-pattern**, không được đưa vào code chạy. `ThrowNew` không nằm trong whitelist. Đúng hơn là để throwable gốc lan truyền, hoặc khi hợp đồng API thật sự yêu cầu mapping, **lưu thông tin cần thiết và clear có chủ đích** rồi gọi JNI bình thường trong trạng thái không còn pending. Việc mapping phải bảo toàn nguyên nhân và không cố “recover” những lỗi JVM nghiêm trọng tùy tiện.

### Nhiều lỗi cùng lúc

Nếu callback Java đã ném exception, còn native cleanup của file hoặc monitor cũng thất bại, phải định nghĩa rõ lỗi nào được ưu tiên. Không mặc nhiên tạo Java exception mới trong lúc exception gốc vẫn pending. Với resource native, có thể ghi mã lỗi vào telemetry thuần native nếu an toàn; để Java xử lý ngoại lệ gốc trước. Nếu bắt buộc thay thế, hãy thực hiện bằng flow `ExceptionClear`/`Throw` có kiểm soát và kiểm thử kỹ cả đường lỗi thứ cấp.

Không gọi `GetObjectClass` hoặc `CallObjectMethod` trên `jthrowable` trong lúc exception pending chỉ để lấy message. Muốn xử lý sâu, phải clear có chủ đích; nếu chỉ cần biết có lỗi, dùng `ExceptionCheck`.

## 10. Khi acquire thất bại giữa chừng

Không phải chỉ callback Java mới gây pending exception. Các hàm acquire trong JNI có thể thất bại:

~~~text
GetStaticMethodID        -> thành công
FindClass(Object)        -> tạo localClass
GetStringUTFChars        -> thành công, có utf
GetIntArrayElements      -> thất bại (ví dụ không đủ bộ nhớ)
NewGlobalRef             -> CHƯA ĐƯỢC GỌI
CallStaticVoidMethod     -> CHƯA ĐƯỢC GỌI
           |
           v
cleanup:
  globalText == NULL  => không DeleteGlobalRef
  elements == NULL    => không ReleaseIntArrayElements
  utf != NULL         => ReleaseStringUTFChars
  localClass != NULL  => DeleteLocalRef
           |
           v
return, giữ lỗi ban đầu
~~~

Thiết kế **một nhãn cleanup** xử lý trường hợp này. Nếu bạn chỉ viết cleanup sau callback mà các lời gọi trước đó dùng `return` trực tiếp, có thể rò rỉ string pointer hoặc local/global references. Bởi vậy mọi bước acquire sau khi đã sở hữu tài nguyên khác đều phải có đường thoát chung.

Một số JNI function có thể báo thất bại bằng `NULL` mà không nhất thiết luôn có pending exception; trong production code cần quy định riêng trường hợp này. Nếu sau cleanup **không** có pending exception nhưng không thể tiếp tục, bạn có thể tạo một lỗi Java mới *sau khi chắc chắn không còn pending*, hoặc trả mã trạng thái theo hợp đồng API. Ví dụ runnable chủ yếu minh họa đường **callback ném Java exception** nên không tạo lỗi tùy chọn trong từng nhánh acquire.

## 11. Phân biệt cleanup hợp lệ với tình huống dọn nguy hiểm

| Tình huống | Nên làm | Không nên làm |
|---|---|---|
| `CallStaticVoidMethod` ném `IllegalStateException`, có UTF buffer | `ReleaseStringUTFChars` rồi return giữ lỗi | `NewStringUTF` để log thông báo trong lúc pending |
| Đã gọi `GetIntArrayElements` thành công và chỉ đọc | `ReleaseIntArrayElements(..., JNI_ABORT)` | `free(elements)` hoặc bỏ qua Release |
| Đã tạo global reference | `DeleteGlobalRef` khi sở hữu không cần nữa | `DeleteLocalRef` thay thế |
| Đã tạo nhiều local refs trong local frame | `PopLocalFrame` đúng frame hoặc `DeleteLocalRef` | Dùng lại reference sau Pop hoặc tạo thêm references tùy ý |
| JNI `MonitorEnter` đã thành công | `MonitorExit` tương ứng, kiểm tra kết quả | Gọi `MonitorEnter` khác khi pending hoặc release monitor không sở hữu |
| Muốn Java thấy lỗi gốc | Không clear, cleanup hợp lệ và return | Gọi `ExceptionDescribe` rồi return với giả định lỗi còn pending |
| Muốn chuyển lỗi sang loại khác | Thiết kế rõ mapping; clear trước các JNI calls không thuộc whitelist | `ThrowNew` khi exception cũ vẫn pending |
| Con trỏ critical đang được giữ | `Release...Critical` sớm, tránh blocking | Gọi tùy tiện JNI khác hoặc chờ dài trước Release |
| Native thread tự attach JVM | Dọn references, monitor và thread lifecycle đúng Invocation API; detach khi thực sự hợp lệ | Detach thread do Java tạo, hoặc detach khi còn Java frame hoạt động |

**Hợp lệ trong whitelist không có nghĩa mọi lần gọi đều an toàn với tham số sai.** `MonitorExit` trên monitor không sở hữu hoặc `ReleaseIntArrayElements` với pointer không khớp vẫn là lỗi lập trình native; whitelist chỉ nói JNI chấp nhận *loại thao tác* đó khi exception pending.

## 12. CheckJNI, test lỗi và kiểm thử đa nền tảng

Để kiểm tra JNI code, nên dùng bản JVM có khả năng kiểm tra JNI misuse. Với HotSpot/OpenJDK, có thể bật diagnostic CheckJNI bằng tùy chọn:

~~~bash
java -Xcheck:jni -Djava.library.path=. PendingCleanupDemo
~~~

Tùy chọn hỗ trợ và hình thức cảnh báo phụ thuộc JVM. CheckJNI có thể phát hiện nhiều lỗi JNI như dùng API không phù hợp trong lúc pending, sai reference hoặc quản lý JNI không chuẩn, nhưng **không chứng minh chương trình không rò rỉ toàn bộ tài nguyên C**. Chạy thêm sanitizer/native leak detector và kiểm thử thực tế nếu yêu cầu độ tin cậy cao.

Các test nên có:

1. Callback thành công: cleanup vẫn chạy, không rò rỉ.
2. Callback ném `RuntimeException`: Java caller nhận **đúng loại và message**; native không xóa lỗi.
3. Acquire UTF buffer thành công nhưng acquire array thất bại: UTF phải được release.
4. Có global ref tạo thành công và callback ném: global ref được delete đúng cách.
5. Tạo nhiều local references trong loop: không có overflow local ref table; đúng local frame lifetime.
6. JNI monitor được acquire trước callback: chắc chắn `MonitorExit` tương ứng, kể cả khi callback ném.
7. Có critical pointer: thời gian giữ ngắn, release không bị bỏ sót dù code path lỗi.
8. Code chạy trên JVM và ABI đã hỗ trợ; lỗi native library loading như `UnsatisfiedLinkError` phải được xử lý riêng, không nhầm với exception pending do Java callback.

Đối với môi trường đa thread, hãy nhớ pending exception là trạng thái **theo thread** và `JNIEnv*` cũng là interface pointer dành cho thread tương ứng; không chuyển `JNIEnv*` hay local references sang thread khác để “dọn hộ”.

## 13. Câu hỏi tự kiểm tra

**1. `ExceptionCheck` có clear ngoại lệ đang chờ không?** Không. Nó chỉ trả `JNI_TRUE`/`JNI_FALSE`.

**2. `ExceptionOccurred` trả gì khi có exception?** Một local reference đến `jthrowable`; pending exception vẫn giữ nguyên. Nếu không còn dùng local ref, `DeleteLocalRef` được phép gọi.

**3. `ExceptionDescribe` chỉ log hay còn thay đổi trạng thái?** Nó in exception/stack trace ra kênh lỗi và **clear pending exception**. Đừng dùng nó như logging không có tác dụng phụ.

**4. Khi callback lỗi, có được gọi `ReleaseByteArrayElements` và `DeleteLocalRef` không?** Có, nếu pointer/reference đã được tạo hợp lệ từ trước và phải được release/delete đúng loại.

**5. `GetArrayLength` có trong whitelist không?** Không. Dù tên là hàm đọc, không gọi khi exception còn pending.

**6. Có nên gọi `NewGlobalRef` trong cleanup để lưu exception lại không?** Không khi còn pending. Nếu cần giữ throwable, `ExceptionOccurred` cung cấp local ref; muốn thao tác sâu hoặc tạo global ref phải thiết kế flow `ExceptionClear` rõ ràng trước.

**7. `JNI_ABORT` chắc chắn hoàn tác mọi thay đổi đã ghi vào primitive array không?** Không. Khi JVM trả pointer trực tiếp tới mảng thay vì bản sao, thay đổi tại chỗ có thể đã tác động tới mảng. `JNI_ABORT` chủ yếu tránh copy-back khi có buffer copy.

**8. `PopLocalFrame` có tự `ReleaseStringUTFChars` không?** Không. Local references và pointer buffer sở hữu qua Get/Release là hai cơ chế khác nhau; phải giải phóng từng loại phù hợp.

**9. Nếu JNI function trả về `NULL` nhưng không có pending exception, cleanup rồi return có chắc chắn báo lỗi tới Java không?** Không. Cần hợp đồng riêng để chuyển lỗi thành Java exception hoặc mã trạng thái nếu operation không thể tiếp tục.

**10. Vì sao `goto cleanup` thường hợp lý trong C/JNI?** Nó gom đường dọn tài nguyên từ nhiều điểm thất bại, tránh quên Release/Delete khi exception xảy ra giữa chuỗi acquire, và không đòi hỏi gọi JNI trái whitelist.

## Tài liệu chuẩn

- [Oracle Java SE 17 — JNI Design Overview, Exception Handling](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): danh sách những JNI function cho phép khi exception pending.
- [Oracle Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`, các họ Release, local/global refs, local frames và monitor.
- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): vòng đời attach/detach của native thread.
- [Android NDK — JNI tips, Exceptions](https://developer.android.com/ndk/guides/jni-tips): hướng dẫn thực hành về hạn chế gọi JNI khi exception pending và các thao tác cleanup được phép.

## Ghi nhớ

**Khi Java exception đang pending, không được gọi JNI tùy ý.** Đường xử lý thông thường là: **kiểm tra lỗi → trả buffer / xóa references / nhả monitor hoặc local frame bằng API được phép → return mà không clear**, để Java caller nhận đúng throwable gốc.

Hãy nhớ rõ khác biệt:

- `ExceptionCheck` / `ExceptionOccurred`: **quan sát, không clear**.
- `ExceptionClear`: **clear có chủ đích**.
- `ExceptionDescribe`: **in chẩn đoán đồng thời clear pending exception**.
- `Release...` và `Delete...Ref`: **dọn những tài nguyên đã acquire hợp lệ**; không phải cách tạo resource mới hoặc chạy tiếp logic Java.
- `PopLocalFrame`: dọn local references, **không thay thế** Release của chuỗi/mảng hay cleanup của tài nguyên native.

Trong C, lưu ownership rõ ràng bằng các pointer/reference khởi tạo `NULL` và một nhãn `cleanup`. Đó là cách đơn giản, dễ review để xử lý ngoại lệ JNI mà không mất lỗi gốc hoặc rò rỉ tài nguyên.
