# Bảo đảm trả tài nguyên trên mọi nhánh lỗi bằng cấu trúc dọn dẹp hoặc RAII trong JNI

Mã Java và mã native C/C++ có hai cơ chế quản lý lỗi khác nhau. Java có exception và việc thoát khỏi một khối `try` có thể kích hoạt `finally`/`try-with-resources`. Khi JNI gọi một phương thức Java ném exception, JVM ghi **pending Java exception trên thread**, nhưng điều đó **không tự động nhảy ra khỏi các khung hàm C/C++ đang chạy**. Native code vẫn tiếp tục tại lệnh kế tiếp cho đến khi nó chủ động kiểm tra, dọn dẹp và trả quyền điều khiển về Java.

Đây là nguyên nhân khiến JNI thường gặp các lỗi như: gọi `GetStringUTFChars` thành công nhưng thoát sớm mà không `ReleaseStringUTFChars`; lấy `GetByteArrayElements` rồi quên `ReleaseByteArrayElements` khi một Java callback ném lỗi; hoặc native heap/FILE handle/mutex bị bỏ lại trên một trong nhiều nhánh `return`.

**Nguyên tắc cốt lõi:** mỗi tài nguyên native phải có một **owner** và một thao tác dọn dẹp xác định. Với C, gom đường thoát về một khối `cleanup` duy nhất (thường bằng `goto cleanup`). Với C++, dùng **RAII** (*Resource Acquisition Is Initialization*): đối tượng sở hữu tài nguyên và destructor tự giải phóng khi rời scope, kể cả qua `return` hoặc khi bắt một C++ exception ở tầng phù hợp. Cả hai cách đều phải tôn trọng **danh sách các JNI operations được phép lúc có pending Java exception**.

## 1. Điều gì thực sự xảy ra khi Java callback ném exception?

```text
Java main()
   |
   +--> gọi native process(...)
             |
             +--> GetStringUTFChars(...)  [đang giữ lease 1]
             +--> GetByteArrayElements(...) [đang giữ lease 2]
             +--> malloc(...)            [đang giữ native heap]
             |
             +--> CallStaticVoidMethod(...)  // Java callback ném lỗi
             |       |
             |       +--> Java: throw new IllegalStateException(...)
             |       +--> JNI thread có pending Java exception
             |       +--> C/C++ trở về DÒNG NGAY SAU CallStaticVoidMethod
             |
             +--> C: goto cleanup
             |       hoặc
             +--> C++: return để destructor RAII thực thi
             |
             +--> free(native heap)
             +--> ReleaseByteArrayElements(...)
             +--> ReleaseStringUTFChars(...)
             |
             +--> return về JVM
   |
   +--> Java catch (IllegalStateException e) xử lý lỗi
```

Nếu native code bỏ qua `ExceptionCheck` sau `CallStaticVoidMethod`, nó có thể tiếp tục thực hiện công việc không phù hợp khi exception còn pending. Nguy hiểm hơn, nhiều JNI functions **không được phép gọi khi một exception đang chờ xử lý**. JVM có thể cảnh báo, báo lỗi hoặc crash khi bật kiểm tra JNI.

Phân biệt ba cơ chế:

| Cơ chế | Điều gì kích hoạt? | Có tự giải phóng JNI lease không? |
| --- | --- | --- |
| Java `throw` từ method được native gọi qua JNI | Đặt trạng thái pending Java exception trên thread native hiện tại | **Không**. C/C++ phải tiếp tục cleanup một cách chủ động |
| C `goto cleanup` | Chuyển điều khiển tới nhãn cleanup trong cùng function | Có, **nếu** nhãn cleanup giải phóng đầy đủ từng tài nguyên đã cấp |
| C++ RAII destructor | Scope kết thúc qua `return` hoặc C++ stack unwinding đúng chuẩn | Có, với **những tài nguyên được RAII wrapper thực sự sở hữu** |

Java exception **không phải** C++ `throw`. C++ `try/catch` không tự bắt Java `IllegalStateException` đang pending, và một Java exception **không tự kích hoạt stack unwinding của C++**. RAII vẫn giúp nếu native code **chủ động `return` hoặc xử lý lỗi bằng C++ exception nội bộ**, vì lúc đó scope C++ kết thúc theo cơ chế ngôn ngữ.

## 2. Phân loại owner và cặp Acquire/Release

Trước khi viết một phương thức JNI, liệt kê từng tài nguyên mà nó có thể giữ:

| Cấp phát/lấy tài nguyên | Tài nguyên do ai quản lý? | Thao tác trả lại | Lưu ý trên nhánh lỗi |
| --- | --- | --- | --- |
| `GetStringUTFChars` | JVM quản lý buffer/lease | `ReleaseStringUTFChars` với cùng `jstring` và pointer | Gọi kể cả khi `isCopy == JNI_FALSE` |
| `GetStringChars` | JVM quản lý `jchar *`/lease | `ReleaseStringChars` | Không dùng `free` hoặc tráo sang ReleaseUTF |
| `Get<PrimitiveType>ArrayElements` | JVM quản lý view/copy của Java primitive array | `Release<PrimitiveType>ArrayElements` | Mode `0`/`JNI_ABORT`/`JNI_COMMIT` có ý nghĩa khác nhau |
| `GetPrimitiveArrayCritical` | JVM có thể pin/copy array trong critical section | `ReleasePrimitiveArrayCritical` | Critical section phải thật ngắn, không gọi JNI tùy tiện hoặc block |
| `GetStringCritical` | JVM có thể pin/copy UTF-16 string | `ReleaseStringCritical` | Không dùng `ReleaseStringChars` thay thế |
| `NewGlobalRef` | JNI global reference | `DeleteGlobalRef` | Phải dọn theo lifetime đã thiết kế |
| `NewLocalRef`, `NewStringUTF`, `FindClass` tạo local refs | JNI local reference | `DeleteLocalRef` hoặc dọn khi frame kết thúc | Trong vòng lặp dài phải dọn sớm; local ref không phải string lease |
| `malloc` / `calloc` | Native heap | `free` | Không truyền pointer JVM cấp cho `free` |
| `new`/`new[]` trong C++ | Native heap / C++ objects | `delete`/`delete[]`, tốt nhất qua smart pointer/container | Không để C++ exception vượt qua biên JNI |
| `fopen`/file descriptor/socket | C runtime hoặc OS | `fclose`/`close`/close phù hợp OS | Có thể cần cleanup ngay cả khi JNI exception pending |
| `MonitorEnter` | Quyền sở hữu Java monitor | `MonitorExit` | Phải bảo đảm cặp enter/exit; lưu ý lỗi trong cleanup |
| Mutex native | Native synchronization | Unlock và destroy theo owner | Không giữ lock qua Java callback không kiểm soát được |

**Đừng lẫn owner:** một `jstring` local reference và con trỏ trả từ `GetStringUTFChars` là **hai loại tài nguyên khác nhau**. `DeleteLocalRef` không thay thế `ReleaseStringUTFChars`. `ReleaseStringUTFChars` không xóa một global reference. `JNIEnv *` thuộc thread và không phải con trỏ muốn `free` hay cache dùng trên thread khác.

## 3. Đặc biệt: JNI operations nào dùng được khi exception đang pending?

Theo *JNI Specification, Design Overview*, sau khi JNI thread có pending exception, thông thường chỉ các thao tác về **kiểm tra/xử lý exception và cleanup** được phép thực hiện trước khi trả về Java hoặc trước khi clear exception có chủ đích. Nhóm liên quan trong bài:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `ExceptionDescribe`.
- `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`.
- `Release<PrimitiveType>ArrayElements` và `ReleasePrimitiveArrayCritical`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame` và một số thao tác JVM/thread được đặc tả cho trường hợp này.

**Không được tự do gọi** `FindClass`, `NewStringUTF`, `CallObjectMethod`, `GetMethodID` hay `NewObject` trong lúc exception còn pending. `ExceptionCheck` chỉ hỏi có pending exception hay không; nó **không** xóa lỗi. `ExceptionDescribe` dành cho chẩn đoán và có thể **clear** pending exception như side effect, do đó không chèn bừa vào production khi muốn truyền lỗi gốc về Java.

Ví dụ sai:

```c
(*env)->CallStaticVoidMethod(env, clazz, callback);
if ((*env)->ExceptionCheck(env)) {
    /* SAI: còn pending exception nhưng lại tiếp tục FindClass. */
    jclass ex = (*env)->FindClass(env, "java/lang/RuntimeException");
    /* ... */
}
```

Lựa chọn đơn giản nhất nếu Java callback đã ném lỗi: **không tạo exception mới**, chỉ trả các native resources hợp lệ rồi `return`; khi native frame kết thúc, Java thấy exception đang pending và bắt/xử lý ở phía Java.

Nếu thật sự cần **chuyển đổi exception**, phải có hợp đồng lỗi rõ ràng: giữ `jthrowable` gốc bằng reference hợp lệ, `ExceptionClear` có chủ đích, thực hiện thao tác JNI khác khi không còn pending, và quyết định Java exception mới nào sẽ được ném. Đây không phải hành vi mặc định của cơ chế cleanup. Với tài nguyên có thể lỗi khi đóng (file, socket, monitor), cần chính sách giữ lỗi ban đầu và ghi nhận lỗi dọn dẹp riêng; tránh vô tình che khuất Java exception gốc.

## 4. C: một đường `cleanup` thay vì nhiều lệnh `return`

C không có destructor RAII theo scope như C++. Mẫu thông dụng là **khởi tạo mọi handle bằng `NULL`**, đi từng bước acquire, nếu thất bại thì `goto cleanup`; ở cuối hàm chỉ giải phóng tài nguyên **đã acquire thành công**, theo thứ tự ngược với lúc lấy.

```c
/* MẪU MINH HỌA, nằm trong một hàm JNI có env hợp lệ.
 * 'text' là jstring, 'data' là jbyteArray.
 * Các biến đầu vào đã được kiểm tra khác NULL trước đó.
 */
const char *utf = NULL;
jbyte *bytes = NULL;
unsigned char *scratch = NULL;
jint result = 0;

utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) {
    goto cleanup;
}

bytes = (*env)->GetByteArrayElements(env, data, NULL);
if (bytes == NULL) {
    goto cleanup;
}

/* malloc chỉ cấp native buffer (khác với JNI lease). */
scratch = (unsigned char *)malloc(128);
if (scratch == NULL) {
    /* Chỉ tạo Java exception mới khi chưa có exception pending.
     * Xem helper throw_if_no_pending trong ví dụ chạy được.
     */
    goto cleanup;
}

/* Có thể gọi Java callback tại đây; callback có thể ném lỗi. */
(*env)->CallStaticVoidMethod(env, clazz, method);
if ((*env)->ExceptionCheck(env)) {
    goto cleanup;
}

result = 42;

cleanup:
free(scratch); /* free(NULL) an toàn theo C. */
if (bytes != NULL) {
    (*env)->ReleaseByteArrayElements(env, data, bytes, JNI_ABORT);
}
if (utf != NULL) {
    (*env)->ReleaseStringUTFChars(env, text, utf);
}
return result;
```

Đây là **mẫu cấu trúc**, chưa phải function độc lập: `clazz`, `method` và các giá trị đầu vào phải được xác định. Trong ví dụ đầy đủ ở phần 7 sẽ có helper kiểm tra exception và quy trình tạo Java exception cho lỗi cấp phát.

Tại sao đặt `cleanup` ở cuối? Nếu có 6 tài nguyên và 8 điểm lỗi, viết `return` ngay sau từng lỗi dễ khiến một số nhánh quên giải phóng tài nguyên. Một nhãn cleanup giúp người đọc đối chiếu **một lần** mọi tài nguyên cần trả.

**Không `Release` một pointer chưa Get thành công.** `NULL` cho biết chưa có lease hợp lệ. Khi đã gọi `Release`, coi pointer **hết hiệu lực**; nếu code phức tạp cần tiếp tục, đặt lại biến thành `NULL` để không vô tình Release lần hai.

### Mẫu kiểm soát exception khi cần ném lỗi mới

```c
/* C: helper dùng sau khi không còn hoặc chưa có pending exception.
 * Chỉ dùng ở nơi đã xác định cần báo một lỗi Java mới.
 */
static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return; /* không che lỗi gốc */
    }

    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}
```

Nếu `FindClass` thất bại, nó có thể để lại một exception mới; helper không cố tạo thêm exception. `DeleteLocalRef` ở nhánh `type != NULL` được phép dùng khi pending exception, nên an toàn sau `ThrowNew`. Trong C++ phiên bản tương đương dùng cú pháp `env->...`.

### Lỗi thiết kế điển hình trong C

```c
const char *utf = (*env)->GetStringUTFChars(env, text, NULL);
if (utf == NULL) return 0;

jbyte *bytes = (*env)->GetByteArrayElements(env, data, NULL);
if (bytes == NULL) {
    return 0; /* SAI: quên ReleaseStringUTFChars(env,text,utf) */
}

(*env)->CallStaticVoidMethod(env, clazz, method);
if ((*env)->ExceptionCheck(env)) {
    return 0; /* SAI: quên Release cả bytes lẫn utf */
}
```

Hậu quả của hai `return` phía trên là **resource leak hoặc giữ vùng nhớ JVM không cần thiết**. Trong chương trình thực, đường cleanup cần vừa trả về đúng giá trị/lỗi, vừa giữ Java exception gốc nếu đã có lỗi; không chỉ thêm một dòng `free` tại nhánh thành công rồi xem như xong.

## 5. C++: RAII quản lý lifetime bằng destructor

Trong C++, RAII đặt `JNIEnv *`, owner JNI object và con trỏ mượn vào một object có destructor. Constructor hoặc factory thực hiện Acquire; destructor thực hiện Release **một lần** khi scope kết thúc. Đây là một ví dụ rút gọn:

```cpp
class UtfCharsLease {
    JNIEnv *env_;
    jstring source_;
    const char *ptr_;

public:
    UtfCharsLease(JNIEnv *env, jstring source)
        : env_(env), source_(source),
          ptr_(env->GetStringUTFChars(source, nullptr)) {}

    ~UtfCharsLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseStringUTFChars(source_, ptr_);
        }
    }

    const char *get() const noexcept { return ptr_; }

    UtfCharsLease(const UtfCharsLease &) = delete;
    UtfCharsLease &operator=(const UtfCharsLease &) = delete;
};
```

Đây là **class minh họa** cần `jni.h` và môi trường C++, chưa phải chương trình độc lập. Khi dùng:

```cpp
UtfCharsLease utf(env, text);
if (utf.get() == nullptr) {
    return 0;
}

/* Nếu code return tại đây, destructor sẽ ReleaseStringUTFChars. */
```

Hai thao tác bảo vệ quan trọng:

1. **Destructor `noexcept`**, không ném C++ exception và chỉ thực hiện cleanup phù hợp với trạng thái pending Java exception. `ReleaseStringUTFChars` thuộc danh sách được phép sử dụng khi có pending exception.
2. **Cấm copy** object owner: copy một pointer + owner dễ khiến hai destructor cùng Release **một tài nguyên** (*double release*). Khi cần move, phải triển khai chuyển quyền sở hữu thật sự, đặt owner cũ về trạng thái rỗng; ví dụ này đơn giản bằng cách cấm copy.

RAII áp dụng cả với native heap: `std::unique_ptr<unsigned char[]>` tự dùng `delete[]` theo owner, và `std::vector` quản lý bộ nhớ vector. Với JNI local reference có thể tạo wrapper và `DeleteLocalRef`, nhưng phải xét rõ local/global distinction, lifetime của `JNIEnv*` và quy tắc thread. Không lưu wrapper giữ `JNIEnv *` qua thread khác hoặc quá thời gian native call còn hợp lệ.

**Chú ý:** C++ destructor chạy khi code C++ rời scope. Java callback ném Java exception **không tự kích hoạt destructor ngay lập tức**. Native method phải kiểm tra `ExceptionCheck` (hoặc kết quả JNI), rồi `return` để RAII dọn dẹp. Đừng dựa vào `catch (std::exception&)` để bắt Java exception.

## 6. Thiết kế một ví dụ chạy được: hai biến thể, cùng bài toán

Ta tạo một class `NativeCleanupDemo` với hai native methods:

- `processC` dùng C và nhãn `cleanup:`.
- `processCpp` dùng C++ và các RAII wrappers.

Cả hai nhận `String text`, `byte[] payload` và `boolean fail`. Chúng lấy hai tài nguyên JNI (`GetStringUTFChars` và `GetByteArrayElements`) cùng một native heap buffer, rồi:

- Nếu `fail == false`, tính tổng giá trị unsigned của các **byte modified UTF-8** của `text` và các byte trong `payload`.
- Nếu `fail == true`, gọi một **Java static callback cố ý ném `IllegalStateException`** sau khi cả ba tài nguyên đã được cấp; hai phiên bản phải trả tài nguyên rồi quay về Java để exception đi tiếp.
- Java gọi lại lần nữa sau khi bắt exception để minh họa native method vẫn hoạt động. Đây chỉ là **quan sát hành vi**, không phải một phép đo leak hoặc bằng chứng không còn tài nguyên treo ở mọi JVM.

Giới hạn input trong ví dụ là tối đa **1024 UTF-16 units** và **1024 array elements**. Giới hạn giúp `GetStringUTFLength` kiểu `jsize` trên JDK 17 không bị overflow và tổng `jint` không tràn trong bài demo: mỗi UTF-16 unit tạo tối đa ba byte modified UTF-8; tổng số byte cộng vào tối đa 4096, mỗi byte tối đa 255.

### File 1 — `NativeCleanupDemo.java`

```java
public final class NativeCleanupDemo {
    static {
        System.loadLibrary("jnicleanupc");
        System.loadLibrary("jnicleanupraii");
    }

    private static native int processC(
            String text, byte[] payload, boolean fail);

    private static native int processCpp(
            String text, byte[] payload, boolean fail);

    // C/C++ gọi method này ngược về Java khi fail=true.
    private static void failFromJava() {
        throw new IllegalStateException("callback failure");
    }

    public static void main(String[] args) {
        byte[] bytes = {1, 2, 3};

        System.out.println("C sum="
                + processC("AB", bytes, false));
        try {
            processC("AB", bytes, true);
            System.out.println("C unexpected success");
        } catch (IllegalStateException e) {
            System.out.println("C failure=" + e.getMessage());
        }
        System.out.println("C after failure="
                + processC("AB", bytes, false));

        System.out.println("C++ sum="
                + processCpp("AB", bytes, false));
        try {
            processCpp("AB", bytes, true);
            System.out.println("C++ unexpected success");
        } catch (IllegalStateException e) {
            System.out.println("C++ failure=" + e.getMessage());
        }
        System.out.println("C++ after failure="
                + processCpp("AB", bytes, false));
    }
}
```

JNI generated header (`javac -h`) khai báo hai hàm native trả `jint`; `String` là `jstring`, `byte[]` là `jbyteArray`, `boolean` là `jboolean`. Các hàm Java được đánh dấu `static` nên đối số JNI thứ hai là `jclass`, không phải receiver `jobject`.

### File 2 — `jni_cleanup_c.c` (C11, dọn bằng `goto cleanup`)

```c
#include "NativeCleanupDemo.h"  /* javac -h tạo, có jni.h */
#include <stddef.h>
#include <stdlib.h>

static void throw_if_no_pending(JNIEnv *env,
                                const char *class_name,
                                const char *message) {
    if ((*env)->ExceptionCheck(env)) {
        return;
    }
    jclass type = (*env)->FindClass(env, class_name);
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

JNIEXPORT jint JNICALL
Java_NativeCleanupDemo_processC(JNIEnv *env, jclass clazz,
                                jstring text, jbyteArray payload,
                                jboolean fail) {
    const char *utf = NULL;            /* JVM lease */
    jbyte *elements = NULL;           /* JVM lease */
    unsigned char *scratch = NULL;    /* Native heap */
    jint sum = 0;
    jsize array_len = 0;
    jsize utf_len = 0;

    if (text == NULL || payload == NULL) {
        throw_if_no_pending(env, "java/lang/NullPointerException",
                            "text or payload is null");
        goto cleanup;
    }

    jsize units = (*env)->GetStringLength(env, text);
    array_len = (*env)->GetArrayLength(env, payload);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }
    if (units > 1024 || array_len > 1024) {
        throw_if_no_pending(env, "java/lang/IllegalArgumentException",
                            "demo input too large");
        goto cleanup;
    }
    utf_len = (*env)->GetStringUTFLength(env, text);
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    utf = (*env)->GetStringUTFChars(env, text, NULL);
    if (utf == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetStringUTFChars failed");
        goto cleanup;
    }

    elements = (*env)->GetByteArrayElements(env, payload, NULL);
    if (elements == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "GetByteArrayElements failed");
        goto cleanup;
    }

    size_t scratch_len = (size_t)utf_len + (size_t)array_len;
    scratch = (unsigned char *)malloc(
            scratch_len > 0 ? scratch_len : 1);
    if (scratch == NULL) {
        throw_if_no_pending(env, "java/lang/OutOfMemoryError",
                            "malloc failed");
        goto cleanup;
    }

    if (fail != JNI_FALSE) {
        jmethodID callback = (*env)->GetStaticMethodID(
                env, clazz, "failFromJava", "()V");
        if (callback == NULL) {
            goto cleanup;  /* lookup failure, exception có thể pending */
        }
        (*env)->CallStaticVoidMethod(env, clazz, callback);
        /* failFromJava() ném Java IllegalStateException. */
        goto cleanup;     /* không gọi JNI function không được phép */
    }

    for (jsize i = 0; i < utf_len; ++i) {
        unsigned char value = (unsigned char)utf[i];
        scratch[i] = value;
        sum += (jint)value;
    }
    for (jsize i = 0; i < array_len; ++i) {
        unsigned char value = (unsigned char)elements[i];
        scratch[utf_len + i] = value;
        sum += (jint)value;
    }

cleanup:
    /* Dọn theo thứ tự ngược acquire; hợp lệ cả khi pending exception. */
    free(scratch);  /* C cho phép free(NULL). */

    if (elements != NULL) {
        (*env)->ReleaseByteArrayElements(
                env, payload, elements, JNI_ABORT);
        elements = NULL;
    }
    if (utf != NULL) {
        (*env)->ReleaseStringUTFChars(env, text, utf);
        utf = NULL;
    }
    return sum;
}
```

`scratch` được cấp bằng `malloc` nên giải phóng bằng `free`; hai con trỏ `utf` và `elements` do JVM cấp nên phải dùng **đúng JNI Release**. `JNI_ABORT` biểu thị **không copy back** những thay đổi của mảng byte vì code chỉ đọc dữ liệu; đây là release thật sự, khác `JNI_COMMIT`.

Các nhánh lỗi ở giữa và sau khi acquire đều đi qua `cleanup`:

| Điểm dừng | Đã sở hữu gì? | `cleanup` làm gì? |
| --- | --- | --- |
| Input null / vượt giới hạn | Chưa có lease/heap | `free(NULL)`, bỏ qua hai Release |
| `GetStringUTFChars` thất bại | Không có `utf` hợp lệ | Bỏ qua Release string; báo lỗi nếu chưa có pending |
| `GetByteArrayElements` thất bại | `utf` | `ReleaseStringUTFChars` |
| `malloc` thất bại | `utf` + `elements` | Release array, Release string |
| `GetStaticMethodID` thất bại | Cả ba tài nguyên | Free heap, Release array, Release string |
| Java callback ném exception | Cả ba tài nguyên, đang có pending Java exception | Chỉ cleanup hợp lệ rồi return; Java thấy lỗi gốc |
| Thành công | Cả ba tài nguyên | Cleanup đầy đủ rồi trả `sum` |

Dù lỗi xảy ra ở sau bước acquire thứ nhất, thứ hai hay thứ ba, đường thoát vẫn thống nhất. Cần lưu ý `GetStaticMethodID` có thể gây lookup error; nếu fail, không được gọi callback hoặc các JNI calls không được phép khi exception còn pending.

### File 3 — `jni_cleanup_raii.cpp` (C++17, dọn bằng RAII)

```cpp
#include "NativeCleanupDemo.h"
#include <cstddef>
#include <memory>
#include <new>

namespace {

void throwIfNoPending(JNIEnv *env, const char *className,
                      const char *message) {
    if (env->ExceptionCheck()) {
        return;
    }
    jclass type = env->FindClass(className);
    if (type != nullptr) {
        env->ThrowNew(type, message);
        env->DeleteLocalRef(type);
    }
}

/* Không copy owner để tránh ReleaseStringUTFChars hai lần. */
class UtfCharsLease final {
    JNIEnv *env_;
    jstring text_;
    const char *ptr_;

public:
    UtfCharsLease(JNIEnv *env, jstring text) noexcept
        : env_(env), text_(text),
          ptr_(env->GetStringUTFChars(text, nullptr)) {}

    ~UtfCharsLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseStringUTFChars(text_, ptr_);
        }
    }

    const char *get() const noexcept { return ptr_; }

    UtfCharsLease(const UtfCharsLease &) = delete;
    UtfCharsLease &operator=(const UtfCharsLease &) = delete;
};

/* Đọc mảng, Release với JNI_ABORT kể cả khi có pending exception. */
class ByteArrayLease final {
    JNIEnv *env_;
    jbyteArray array_;
    jbyte *ptr_;

public:
    ByteArrayLease(JNIEnv *env, jbyteArray array) noexcept
        : env_(env), array_(array),
          ptr_(env->GetByteArrayElements(array, nullptr)) {}

    ~ByteArrayLease() noexcept {
        if (ptr_ != nullptr) {
            env_->ReleaseByteArrayElements(array_, ptr_, JNI_ABORT);
        }
    }

    const jbyte *get() const noexcept { return ptr_; }

    ByteArrayLease(const ByteArrayLease &) = delete;
    ByteArrayLease &operator=(const ByteArrayLease &) = delete;
};

}  // namespace

extern "C" JNIEXPORT jint JNICALL
Java_NativeCleanupDemo_processCpp(JNIEnv *env, jclass clazz,
                                  jstring text, jbyteArray payload,
                                  jboolean fail) {
    if (text == nullptr || payload == nullptr) {
        throwIfNoPending(env, "java/lang/NullPointerException",
                         "text or payload is null");
        return 0;
    }

    const jsize units = env->GetStringLength(text);
    const jsize arrayLen = env->GetArrayLength(payload);
    if (env->ExceptionCheck()) {
        return 0;
    }
    if (units > 1024 || arrayLen > 1024) {
        throwIfNoPending(env, "java/lang/IllegalArgumentException",
                         "demo input too large");
        return 0;
    }
    const jsize utfLen = env->GetStringUTFLength(text);
    if (env->ExceptionCheck()) {
        return 0;
    }

    UtfCharsLease utf(env, text);
    if (utf.get() == nullptr) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "GetStringUTFChars failed");
        return 0;
    }

    ByteArrayLease bytes(env, payload);
    if (bytes.get() == nullptr) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "GetByteArrayElements failed");
        return 0;  // ~utf() sẽ Release UTF pointer.
    }

    const std::size_t count = static_cast<std::size_t>(utfLen)
                            + static_cast<std::size_t>(arrayLen);
    std::unique_ptr<unsigned char[]> scratch(
            new (std::nothrow) unsigned char[count > 0 ? count : 1]);
    if (!scratch) {
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "native allocation failed");
        return 0;  // ~bytes() và ~utf() vẫn chạy.
    }

    if (fail != JNI_FALSE) {
        jmethodID callback = env->GetStaticMethodID(
                clazz, "failFromJava", "()V");
        if (callback == nullptr) {
            return 0;  // RAII cleanup dù JNI lookup có lỗi.
        }
        env->CallStaticVoidMethod(clazz, callback);
        return 0;      // Không clear exception, destructor vẫn chạy.
    }

    jint sum = 0;
    for (jsize i = 0; i < utfLen; ++i) {
        const unsigned char value =
                static_cast<unsigned char>(utf.get()[i]);
        scratch[i] = value;
        sum += static_cast<jint>(value);
    }
    for (jsize i = 0; i < arrayLen; ++i) {
        const unsigned char value =
                static_cast<unsigned char>(bytes.get()[i]);
        scratch[utfLen + i] = value;
        sum += static_cast<jint>(value);
    }
    return sum;
}
```

**Vì sao code C++ không cần `goto cleanup`?** Khi trả về, C++ hủy biến tự động theo thứ tự ngược construction: `scratch` giải phóng vùng `new[]`, `bytes` gọi `ReleaseByteArrayElements(...JNI_ABORT)`, rồi `utf` gọi `ReleaseStringUTFChars`. Các destructor của wrapper JNI dùng thao tác **được phép khi có pending exception** và có `noexcept`.

Trong đoạn này, `std::nothrow` ngăn lỗi cấp phát `new[]` thông thường biến thành C++ `std::bad_alloc` vượt biên JNI; code tự tạo `OutOfMemoryError` khi thích hợp. C++ code thực tế có thể có các hàm/thư viện khác ném `std::exception`; cần bắt chúng **ở bên trong** JNI entry point, giải phóng tài nguyên qua RAII và chuyển đổi thành Java exception khi chưa có pending exception. Không để C++ exception đi xuyên qua JVM boundary.

**Không để wrapper vượt scope của `JNIEnv *`:** owner `UtfCharsLease`/`ByteArrayLease` chỉ sống trong đúng native call/thread. Việc `JNIEnv *` của thread A không hợp lệ để dùng trên thread B là một quy tắc JNI độc lập với RAII.

## 7. Biên dịch và chạy trên Linux (JDK 17+, C11, C++17)

Các lệnh sau chạy trong một thư mục chứa ba file đã mô tả. `JAVA_HOME` phải trỏ tới **JDK có header JNI**; `cc`, `c++` phải tạo binary tương thích với kiến trúc của Java process. Bước đầu tiên tạo `NativeCleanupDemo.h`:

```bash
javac -encoding UTF-8 -h . NativeCleanupDemo.java

cc -std=c11 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicleanupc.so jni_cleanup_c.c

c++ -std=c++17 -Wall -Wextra -shared -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjnicleanupraii.so jni_cleanup_raii.cpp

java -Djava.library.path=. NativeCleanupDemo
```

Trên Windows/macOS, tên file và cách build shared library khác; ví dụ là **runnable trên Linux có toolchain/JDK tương thích**, không tuyên bố cùng lệnh compile áp dụng cho mọi OS. `-Djava.library.path=.` là JVM argument đặt **trước** main class.

**Stdout kỳ vọng:**

```text
C sum=137
C failure=callback failure
C after failure=137
C++ sum=137
C++ failure=callback failure
C++ after failure=137
```

Giải thích:

- `"AB"` có hai ASCII bytes `65` và `66` trong modified UTF-8; `payload` có `1, 2, 3`. Tổng `65 + 66 + 1 + 2 + 3 = 137`.
- Với `fail == true`, native code đã acquire các resources rồi gọi `failFromJava()`. Callback ném `IllegalStateException("callback failure")`; native code dọn lease và buffer, **giữ nguyên pending exception**, sau đó Java `catch` in message.
- Phép gọi kế tiếp được chạy từ Java sau khi exception trước đã được Java xử lý, nên có thể lại trả `137`. Đây không phải phép chứng minh độc lập rằng không có leak trong một chương trình lớn; nghĩa vụ cleanup được bảo đảm bởi logic trong các nhánh được minh họa.

Có thể chạy thêm:

```bash
java -Xcheck:jni -Djava.library.path=. NativeCleanupDemo
```

`-Xcheck:jni` trên các JVM hỗ trợ giúp phát hiện nhiều sai phạm JNI, như gọi API không được phép khi pending exception hoặc sai reference/critical region. Nó **không** thay thế kiểm thử native với AddressSanitizer, Valgrind hoặc công cụ phát hiện leak thích hợp.

## 8. Trường hợp khác: array write, `JNI_COMMIT` và `JNI_ABORT`

`Release<PrimitiveType>ArrayElements` nhận đối số `mode` và thường gây nhầm trong code cleanup:

| Mode | Ý nghĩa | Tài nguyên đã thực sự trả xong? |
| --- | --- | --- |
| `0` | Commit những thay đổi cần copy back rồi giải phóng/cởi pin vùng elements | **Có** |
| `JNI_ABORT` | Không copy back bản sao; trả vùng elements; phù hợp read-only hoặc bỏ thay đổi | **Có** |
| `JNI_COMMIT` | Copy back những thay đổi nhưng **giữ lại** quyền truy cập/elements buffer | **Chưa**; cần một lần Release cuối với `0` hoặc `JNI_ABORT` theo contract |

Trong ví dụ, byte array chỉ đọc nên dùng `JNI_ABORT`. Với code sửa Java array và muốn thay đổi được áp dụng, nên chọn `0` ở Release cuối (hoặc phối hợp `JNI_COMMIT` rồi một Release cuối khi cần). Chọn `JNI_ABORT` sau khi đã sửa buffer nhằm “bỏ thay đổi” không bảo đảm phục hồi dữ liệu nếu JVM trả pointer tới vùng nhớ trực tiếp; thiết kế thuật toán nên tránh sửa khi cần rollback.

Sai lầm phổ biến:

```c
jint *elems = (*env)->GetIntArrayElements(env, array, NULL);
if (elems != NULL) {
    /* ... đọc/sửa dữ liệu ... */
    (*env)->ReleaseIntArrayElements(env, array, elems, JNI_COMMIT);
    /* SAI: cho rằng JNI_COMMIT đã release hoàn toàn rồi return. */
}
```

Cần một Release cuối thích hợp (ví dụ `0`) để kết thúc quyền truy cập. Khi viết RAII wrapper cho primitive array, phải **mô tả mục đích** rõ: read-only wrapper có thể luôn `JNI_ABORT`, còn wrapper mutate nên dùng `0` nếu muốn các thay đổi được lưu. Không ẩn một chế độ commit không phù hợp trong destructor dùng chung cho mọi hoàn cảnh.

## 9. Critical region, local references và native locks

### `GetPrimitiveArrayCritical` / `GetStringCritical`

Các API critical có thể tạo điều kiện JVM pin vùng nhớ để tránh copy, với giới hạn nghiêm ngặt: **không được giữ critical region qua thao tác blocking hoặc JNI calls tùy ý**. Giữ critical pointer trong lúc `CallStaticVoidMethod` là ví dụ cần tránh. Hãy đọc/chuyển dữ liệu ngắn gọn, Release bằng đúng `ReleasePrimitiveArrayCritical` hoặc `ReleaseStringCritical`, **sau đó mới** gọi Java callback.

RAII cho critical region có thể hỗ trợ bảo đảm Release, nhưng **không xóa đi lệnh cấm blocking/callback trong thời gian scope còn mở**. Thiết kế nên tách scope:

```cpp
/* Minh họa ý tưởng, không phải chương trình độc lập. */
{
    CriticalArrayLease lease(env, array); // wrapper phải được tự triển khai
    if (!lease.ok()) {
        return; // destructor xử lý nếu đã acquire
    }
    // Chỉ một đoạn thao tác native ngắn, không block/không gọi JNI tùy ý.
} // ReleasePrimitiveArrayCritical tại đây.

/* Sau khi rời critical section mới gọi Java callback. */
```

### Local references

`jobject`, `jstring`, `jclass` từ nhiều JNI API là **local references**. Chúng thường được JVM dọn khi native frame trả về Java, nhưng trong vòng lặp xử lý hàng nghìn phần tử, phải `DeleteLocalRef` sớm hoặc quản lý local frame. `DeleteLocalRef` được phép khi pending exception. Một RAII `LocalRef<T>` có thể giữ `JNIEnv *` và reference; destructor gọi `DeleteLocalRef` nếu khác `nullptr`, cấm copy để tránh double-delete.

Chú ý `PopLocalFrame(result)` có hợp đồng cho phép giữ lại một local reference qua frame, **khác** với việc đơn giản xóa mọi reference. Không trả pointer từ `GetStringUTFChars` ra ngoài native frame sau Release; không dùng local `jobject` sau khi owner native frame hết hiệu lực. `jmethodID`/`jfieldID` là ID opaque, **không** phải local reference để `DeleteLocalRef`.

### Native heap, file handle và khóa

RAII chuẩn trong C++ có thể kết hợp:

- `std::unique_ptr<T>` hoặc `std::unique_ptr<T, Deleter>` cho cấp phát native/handle tùy chỉnh.
- `std::vector<T>`/`std::string` cho vùng nhớ C++ thay `malloc`/`free` thủ công, có điều kiện kiểm soát C++ exceptions.
- `std::unique_ptr<FILE, FileCloser>` cho `FILE *` nếu đã thiết kế deleter gọi `fclose`.
- `std::lock_guard<std::mutex>` hoặc `std::unique_lock<std::mutex>` cho mutex C++.

Không phải mọi destructor đều hoàn toàn “không có lỗi”: `fclose`, flush, release OS resource, hoặc `MonitorExit` có thể có điều kiện lỗi. Quy tắc là **không ném C++ exception từ destructor chạy khi đang xử lý lỗi khác**; nếu cleanup thất bại, phải ghi nhận theo hợp đồng logging/error propagation và bảo toàn Java exception ban đầu khi có thể. Tránh giữ lock native qua Java callback nếu callback có thể re-enter native code, block hoặc tạo deadlock.

## 10. Chuyển đổi lỗi C++ sang Java đúng cách

C++ code có thể ném `std::bad_alloc`, `std::runtime_error` hoặc ngoại lệ riêng. Chúng **không** được phép vô tình thoát qua JNI entry boundary và được kỳ vọng là Java `Exception`. Một boundary C++ cần bắt C++ exceptions ở tầng bao ngoài và chuyển thành một lỗi Java tương ứng khi phù hợp:

```cpp
/* Mẫu ý tưởng, không phải function hoàn chỉnh:
 * runNativeWork có thể ném C++ exception; không có pending Java exception.
 * Các RAII owners ở bên trong runNativeWork sẽ được dọn khi stack unwinds.
 */
try {
    runNativeWork(env);
} catch (const std::bad_alloc &) {
    if (!env->ExceptionCheck()) {
        // Tìm class và ThrowNew OutOfMemoryError; xem helper ở ví dụ C++.
        throwIfNoPending(env, "java/lang/OutOfMemoryError",
                         "native allocation failed");
    }
} catch (const std::exception &) {
    if (!env->ExceptionCheck()) {
        throwIfNoPending(env, "java/lang/RuntimeException",
                         "native operation failed");
    }
}
```

Đây là **đoạn minh họa**, cần các `#include <exception>` và C++ helper/logic phù hợp. Không dùng `ExceptionClear` chỉ để có thể ném exception khác; việc thay nguyên nhân lỗi gốc phải là quyết định có chủ đích. Nếu code native gọi Java làm phát sinh pending exception, nên **dọn dẹp và return** như ví dụ runnable, thay vì cố chuyển sang một C++ exception để kích hoạt RAII.

Một lưu ý tinh tế: **Java pending exception không tự làm C++ stack unwind**, nên code C++ không nên gọi tiếp `env->Call...` hoặc các JNI functions ngoài danh sách an toàn rồi “trông chờ destructor chạy”. Phải kiểm tra trạng thái và chuyển điều khiển bằng `return`/phạm vi C++ để destructor được chạy đúng lúc.

## 11. Kiểm thử nhánh lỗi thay vì chỉ nhìn happy path

Bài toán “mọi nhánh lỗi” cần một ma trận kiểm thử theo **thời điểm đã acquire bao nhiêu tài nguyên**. Với ba tài nguyên `utf`, `elements` và `scratch` trong bài:

| Tình huống | Kết quả mong đợi | Điểm cần quan sát |
| --- | --- | --- |
| `text == null` hoặc `payload == null` | Java `NullPointerException` | Không gọi JNI Get với object null; chưa có lease nào |
| Chuỗi/mảng vượt giới hạn demo | Java `IllegalArgumentException` | Dừng trước Acquire |
| `GetStringUTFChars` không trả pointer | Java error nếu phù hợp, hoặc JNI pending exception | Không Release một pointer chưa tồn tại |
| `GetByteArrayElements` không trả pointer | Rời JNI boundary với lỗi | `utf` được Release |
| Native allocation không thành công | Java `OutOfMemoryError` nếu chưa có pending | Cả hai leases được Release |
| `GetStaticMethodID` thất bại | Java lookup exception tiếp tục | Các resources đã acquire được dọn |
| Java callback chủ động ném | Java nhận `IllegalStateException` gốc | Dọn resources khi pending, không gọi JNI không an toàn |
| Thành công | Java nhận `137` | Tài nguyên cũng được trả, không chỉ khi lỗi |

Hai tình huống callback thành công/thất bại có thể chạy bằng mã đã cho. Các tình huống *memory allocation failure* cần **fault injection**, mocks hoặc native test harness có kiểm soát để chứng minh, chứ không đáng tin nếu cố làm máy hết RAM. Kiểm thử thực tế nên đưa các bước Acquire vào wrapper có khả năng mô phỏng lỗi và đếm từng cặp acquire/release để phát hiện double-free hoặc missing-release.

Trên JVM hỗ trợ `-Xcheck:jni`, kiểm tra đúng quy tắc JNI; kết hợp AddressSanitizer/UndefinedBehaviorSanitizer cho C/C++ khi có thể, công cụ leak detection, và các test Java bắt exception sau mỗi lỗi. Một lệnh compile/chạy thành công **không** chứng minh tất cả các đường thoát đều đã được thử. Code review phải đếm mỗi điểm `return`, `goto`, `throw`, mỗi destructor và mọi release tương ứng.

### Checklist code review trước khi đưa JNI vào production

1. **Inventory:** mọi lời gọi `Get...`/`NewGlobalRef`/`malloc`/`new`/open/lock đều có owner và hàm Release xác định.
2. **Acquisition:** pointer chưa được cấp được khởi tạo `NULL`/`nullptr`; chỉ ghi nhận đã sở hữu sau khi Acquire thành công.
3. **Release:** cleanup chỉ giải phóng tài nguyên đang sở hữu, đúng hàm, đúng object, đúng thread/lifetime; không double-release.
4. **Order:** khi nhiều resources phụ thuộc nhau, thường dọn theo thứ tự ngược acquire.
5. **Exception:** sau JNI callback hoặc một hàm JNI có thể lỗi, kiểm tra return/pending exception và dừng đường chạy không an toàn.
6. **Pending-safe:** code cleanup khi pending chỉ dùng JNI calls được đặc tả cho tình huống ấy; không gọi `FindClass`/`NewStringUTF`/method callback tùy tiện.
7. **Exception priority:** giữ Java exception ban đầu; nếu không có pending, chuyển native error thành Java error theo contract.
8. **RAII:** destructor `noexcept`, không copy ownership một cách vô ý, không giữ `JNIEnv *` xuyên thread.
9. **Arrays:** chọn mode `0`/`JNI_ABORT` theo read-only hay write; `JNI_COMMIT` chưa chấm dứt lease.
10. **Critical:** không giữ critical region qua callback/đoạn block; Release đúng `Critical` API.
11. **Validation:** ít nhất có test nhánh thành công, callback ném, null input, lỗi trước/sau acquire; kiểm thử native tool nếu có.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Tại sao `CallStaticVoidMethod` gọi Java method ném `IllegalStateException` không khiến C tự nhảy tới `cleanup`?

Vì lỗi Java được ghi thành **pending exception** trong JNI thread; nó không phải `longjmp` của C hoặc C++ stack unwinding. Native code cần `ExceptionCheck`/kiểm tra kết quả theo contract rồi chủ động `goto cleanup` hoặc `return`.

**Câu 2.** `GetByteArrayElements` thất bại sau khi `GetStringUTFChars` đã thành công. Cần làm gì?

Không Release byte pointer `NULL`; phải `ReleaseStringUTFChars` cho con trỏ đã lấy, đồng thời truyền tiếp pending Java error hoặc báo lỗi mới khi không có pending. C `goto cleanup` và C++ destructor đều giải quyết được.

**Câu 3.** Tại sao C++ `UtfCharsLease` cấm copy constructor?

Hai objects không được sở hữu và Release **cùng một JNI string pointer** độc lập. Nếu copy pointer thô, cả hai destructor có thể Release hai lần; wrapper cần unique ownership, hoặc move đúng cách.

**Câu 4.** Có thể dùng `FindClass` trong destructor RAII để tạo message khi Java exception đang pending không?

Không. `FindClass` không thuộc nhóm JNI calls được phép dùng tùy tiện khi pending. Destructor nên chỉ cleanup và `noexcept`; tạo/thay Java exception phải xử lý ngoài cơ chế destructor ở nơi phù hợp.

**Câu 5.** `JNI_COMMIT` đã đủ để kết thúc `GetIntArrayElements` chưa?

Chưa. `JNI_COMMIT` copy back nhưng không trả hoàn toàn quyền truy cập. Cần Release cuối với `0` hoặc `JNI_ABORT` theo contract. Nếu chỉ đọc dữ liệu, `JNI_ABORT` thường phù hợp hơn.

**Câu 6.** Khi một Java callback ném lỗi, RAII có cần gọi `ExceptionClear` để destructor hoạt động không?

Không. Destructor dùng các JNI cleanup calls **được phép khi pending**; code chỉ cần kết thúc scope để destructor chạy. `ExceptionClear` nếu không có chủ đích sẽ nuốt lỗi gốc của Java.

**Câu 7.** Nếu đã dọn mọi JNI lease nhưng vẫn còn file handle do `fopen`, có thể xem như cleanup hoàn tất không?

Không. File handle là tài nguyên của C runtime/OS, cần `fclose` hoặc RAII wrapper tương ứng, ngay cả khi lỗi bắt nguồn từ Java callback. Inventory phải bao gồm cả JNI lẫn tài nguyên ngoài JVM.

## Tài liệu đối chiếu

- Oracle JNI Specification — *Java Exceptions, Exception Handling* và danh sách JNI functions được phép khi đang có pending exception: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html#exception-handling
- Oracle JNI Specification — *JNI Functions*, `ExceptionCheck`/`ExceptionClear`/`ThrowNew`, `ReleaseStringUTFChars`, `Release<PrimitiveType>ArrayElements` và `MonitorExit`: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html
- Android NDK — *JNI tips: Exceptions; Local and global references*: https://developer.android.com/ndk/guides/jni-tips
- Oracle Java 17 `javac` — `-h` để tạo native headers: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- C++ Core Guidelines — *Resource management (R), RAII, unique ownership*: https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines#S-resource

**Ghi nhớ:** Java exception không tự động dọn C/C++ resources. Hãy xây **một đường cleanup rõ ràng trong C** hoặc **RAII ownership trong C++**, dọn mọi resource đã acquire trên **tất cả** các đường thoát, chỉ dùng JNI calls cho phép khi exception pending và giữ nguyên lỗi Java gốc để caller xử lý.