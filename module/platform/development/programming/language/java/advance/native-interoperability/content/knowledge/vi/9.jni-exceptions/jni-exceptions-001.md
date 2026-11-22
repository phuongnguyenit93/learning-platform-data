# Phân biệt mã lỗi bản địa, giá trị trả về đặc biệt và ngoại lệ Java

## Mục tiêu

Khi Java gọi C/C++ qua Java Native Interface (JNI), lỗi có thể xuất hiện ở **nhiều lớp khác nhau**. Một thư viện C có thể trả mã trạng thái như `0`/`-1`, đặt `errno`, hoặc dùng con trỏ `NULL` để báo thất bại. Trong khi đó, JVM dùng **ngoại lệ Java** (`Throwable`) để thông báo lỗi cho mã Java. Còn chính các JNI functions có thể vừa trả giá trị đặc biệt vừa làm cho một ngoại lệ ở trạng thái **pending** trên Java thread hiện tại.

Ba cơ chế này **không tự động đồng nghĩa với nhau**. Một mã lỗi C không tự trở thành `IOException`; một giá trị trả về `-1` không luôn là lỗi; và một Java exception đang pending không biến thành một C `throw` hay tự nhảy khỏi native stack.

Sau bài học, bạn có thể:

1. Nhận biết **native error code**, **sentinel/special return value** và **Java exception** bằng hợp đồng API thay vì suy từ một con số.
2. Phân biệt mã lỗi của thư viện với `errno`/`GetLastError` của hệ điều hành và các hằng `JNI_OK`/`JNI_ERR` của JNI.
3. Xử lý đúng `ThrowNew`, `ExceptionCheck`, `ExceptionOccurred` và `ExceptionClear` trong một native method.
4. Dịch trạng thái lỗi có chủ đích sang ngoại lệ Java phù hợp; giữ ý nghĩa, thông điệp, khả năng retry và metadata chẩn đoán.
5. Không che lấp exception đang pending, không xử lý nhầm sentinel hợp lệ, không gọi JNI functions tùy ý trong lúc pending.
6. Chạy một ví dụ Java 17+ ↔ JNI C có **ba luồng lỗi độc lập**: trả status, chuyển lỗi thành exception và để exception từ Java callback đi xuyên qua JNI.

## 1. Ba lớp kết quả cần nhìn riêng

| Cơ chế | Nơi đặt thông tin lỗi | Ví dụ | Điều mà caller phải biết |
| --- | --- | --- | --- |
| **Mã lỗi bản địa** (native status code) | Trong giá trị trả về hoặc tham số output được API định nghĩa | `0` thành công, `7` tham số không hợp lệ, `9` service bận | Bảng status riêng của API; không tự suy status bằng tên biến |
| **Giá trị trả về đặc biệt** (sentinel) | Một giá trị được dành riêng để báo trạng thái khác thành công thông thường | `-1`, `NULL`, `EOF`, một enum `NOT_FOUND` | Sentinel có nằm ngoài miền dữ liệu hợp lệ không; có cần đọc `errno`/out-parameter không |
| **Ngoại lệ Java** | Trạng thái exception pending của Java thread hoặc exception đã được Java code nhận | `IllegalArgumentException`, `IOException`, `OutOfMemoryError` | Kiểm tra, làm sạch tài nguyên, propagate/handle và không gọi JNI APIs không hợp lệ khi pending |

Ví dụ hai hàm native đều trả `jint` nhưng mang nghĩa khác:

~~~c
/* status riêng: 0 = OK; số dương khác 0 = mã lỗi. */
jint library_process(const unsigned char *data, size_t length);

/* dữ liệu: kết quả nguyên; -1 được dành riêng làm sentinel lỗi. */
jint legacy_read_value(void);
~~~

Không thể nhìn `jint` để biết cách xử lý. **Hợp đồng API** mới quy định trả 0 là giá trị dữ liệu hay là thành công, và `-1` có hợp lệ trong miền dữ liệu không.

Tại JNI boundary, một phương thức `native int read()` cũng **không có cơ chế tự đóng gói C status thành Java exception**. Nếu implementation C chỉ `return -1;`, Java nhận một `int` bằng -1. Java `catch` không chạy trừ khi một ngoại lệ thực sự được thiết lập/đẩy ra.

Ngược lại, khi native code gọi `ThrowNew` thành công rồi `return 0;`, phía Java **không thấy 0 là kết quả bình thường**: JVM xử lý ngoại lệ pending khi quay lại Java. Giá trị `0` ở C chỉ để kết thúc hàm có return type `jint`, không phải kết quả thành công được Java nhận.

## 2. Native status code: biểu diễn lỗi rõ nhưng chỉ có ý nghĩa trong API của nó

Nhiều thư viện C trả trạng thái theo hợp đồng như sau:

~~~c
typedef enum {
    NATIVE_OK = 0,
    NATIVE_INVALID_ARGUMENT = 7,
    NATIVE_TEMPORARILY_UNAVAILABLE = 9
} NativeStatus;

/* out_value chỉ được ghi khi hàm trả NATIVE_OK. */
NativeStatus native_get_number(int request, int *out_value);
~~~

Ở đây:

- `NATIVE_OK` là thành công; `out_value` chỉ hợp lệ ở nhánh này.
- `NATIVE_INVALID_ARGUMENT` là lỗi input, thường nên được sửa trước khi retry.
- `NATIVE_TEMPORARILY_UNAVAILABLE` là lỗi trạng thái/tài nguyên; có thể retry nếu operation thực sự an toàn để thử lại.
- Các số 7 và 9 được chọn **riêng cho ví dụ**, **không** phải `errno` chuẩn hay hằng JNI; không được suy chúng là `E2BIG`, `EBADF` hoặc mã lỗi hệ thống nào.

Một mẫu gọi đúng:

~~~c
int value = 0;
NativeStatus status = native_get_number(request, &value);
if (status == NATIVE_OK) {
    /* Chỉ ở đây value mới là kết quả hợp lệ. */
} else {
    /* Xử lý status; không sử dụng value làm dữ liệu thành công. */
}
~~~

Đây là snippet vì `native_get_number` và `request` thuộc ngữ cảnh thư viện đang học. Ý chính: **return status và output payload là hai kênh**. API này hỗ trợ cả giá trị dữ liệu âm, số 0 và số lớn mà không trộn chúng với lỗi.

Các thư viện khác chọn một enum, một struct `{status, value}`, return code âm, hoặc callback báo lỗi. Không có quy tắc JNI toàn cục rằng số âm luôn là lỗi hay 0 luôn thành công.

## 3. Sentinel: `-1`, `NULL` và `EOF` dễ gây nhầm

**Sentinel** là một giá trị trả về được dành riêng để thể hiện “không có dữ liệu”, “đã hết”, “thất bại”, hoặc một điều kiện đặc biệt khác. Nó khác với status code vì nhiều API vẫn trả **dữ liệu trực tiếp** khi thành công.

Ví dụ `indexOf` của Java trả `-1` khi không tìm thấy phần tử:

~~~java
static int indexOf(int[] values, int needle) {
    for (int i = 0; i < values.length; i++) {
        if (values[i] == needle) {
            return i;
        }
    }
    return -1;
}
~~~

`-1` hợp lệ làm sentinel vì index mảng Java hợp lệ luôn từ 0 trở lên. Nhưng hãy tưởng tượng cảm biến thực sự có thể đo `-1` độ, hoặc thuật toán có thể trả bất kỳ `int` nào. Khi đó giao diện `int read()` với `-1` vừa là dữ liệu vừa là lỗi tạo **mơ hồ không giải quyết được từ một giá trị đơn lẻ**.

Một số sentinel quen thuộc:

| API hoặc tình huống | Sentinel điển hình | Cần kiểm tra thêm |
| --- | --- | --- |
| `read` POSIX | `-1` báo lỗi, `0` có thể báo EOF với yêu cầu đọc có độ dài dương | `errno` **khi** `read` trả -1; phân biệt EOF với lỗi |
| `open` POSIX | `-1` lỗi; file descriptor thành công có thể là `0` | `errno` khi thất bại; đừng coi fd 0 là lỗi |
| `malloc` | `NULL` biểu thị không cấp phát được theo hợp đồng `malloc` | `NULL` không phải Java exception; `malloc(0)` có hành vi đặc thù |
| `fgetc` C | `EOF` khi hết input **hoặc** lỗi đọc | `feof` / `ferror` để phân biệt |
| Hàm Java tìm index | `-1` không có phần tử | Theo hợp đồng API Java, không có ngoại lệ tự động |
| JNI function có thể trả `NULL` | Có thể là kết quả hợp lệ hoặc lỗi, tùy hàm | Xem đặc tả hàm và kiểm tra exception pending khi cần |

Từ bảng này suy ra: **một sentinel không đủ nói bản chất lỗi**. `NULL` có thể nghĩa là “field object hiện là null” (`GetObjectField`) chứ không phải exception. `0` có thể là file descriptor hợp lệ, kết quả phép tính bằng không, hoặc mã status thành công.

Khi sentinel **trùng miền dữ liệu**, dùng API khác: return status + output parameter; nullable wrapper với error code riêng; exception; hoặc một result object/record. Đừng đoán “giá trị này chắc chắn người dùng không bao giờ nhập”.

### Ví dụ Java 17+ chạy độc lập: mơ hồ sentinel

Tạo `SentinelOnly.java`:

~~~java
public final class SentinelOnly {
    static int indexOf(int[] a, int needle) {
        for (int i = 0; i < a.length; ++i) {
            if (a[i] == needle) return i;
        }
        return -1;
    }

    static int valueOrThrow(boolean present, int value) {
        if (!present) {
            throw new IllegalStateException("missing measurement");
        }
        return value;
    }

    public static void main(String[] args) {
        int[] values = {8, 5, 9};
        System.out.println("found=" + indexOf(values, 5));
        System.out.println("not-found=" + indexOf(values, 1));
        System.out.println("real-minus-one=" + valueOrThrow(true, -1));

        try {
            valueOrThrow(false, 0);
        } catch (IllegalStateException ex) {
            System.out.println("missing=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SentinelOnly.java
java SentinelOnly
~~~

Stdout:

~~~text
found=1
not-found=-1
real-minus-one=-1
missing=missing measurement
~~~

Trong `indexOf`, -1 không thể là index hợp lệ. Trong `valueOrThrow`, -1 được **giữ nguyên là dữ liệu thành công**; trạng thái “không có phép đo” được báo bằng exception Java.

## 4. `errno` trên POSIX: chi tiết lỗi kèm theo một số API bản địa

Trên hệ POSIX, nhiều system calls/C library functions báo lỗi qua giá trị trả về như `-1` rồi đặt `errno` (định nghĩa trong `<errno.h>`). **Không phải mọi hàm C đều dùng `errno`.** Đặc biệt, nhiều pthread functions trả trực tiếp error number và không set `errno`. Từng API quyết định cách báo lỗi.

Ví dụ POSIX (minh họa, **không phải** chương trình có `main` độc lập):

~~~c
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>

/* Thành công: trả file descriptor >= 0 và caller phải close(fd).
   Thất bại: trả -1, ghi mã errno đã chụp vào *out_error. */
int open_read_only(const char *path, int *out_error) {
    int fd = open(path, O_RDONLY);
    if (fd == -1) {
        int saved = errno;   /* Chụp NGAY sau lời gọi lỗi. */
        *out_error = saved;
        return -1;
    }
    *out_error = 0;
    return fd;
}
~~~

Hợp đồng ví dụ yêu cầu `path` và `out_error` là pointer hợp lệ. Caller phải `close(fd)` khi thành công, đồng thời tự xử lý nếu việc đóng file thất bại. Trên Windows native API có thể dùng `GetLastError`, `HRESULT` hoặc cơ chế khác; **không thay các mã đó bằng `errno`** nếu API không định nghĩa như vậy.

Bốn quy tắc với `errno`:

1. **Chỉ đọc khi API báo nó có ý nghĩa.** Thành công không bảo đảm `errno == 0`; một số hàm có thể thay `errno` dù thành công.
2. **Chụp ngay** (`int saved = errno;`) sau lời gọi thất bại và trước khi gọi log/JNI/allocating/formatting khác; những lời gọi sau có thể thay nó.
3. **Không giả định cùng một số có cùng ý nghĩa trên mọi OS/ABI.** So sánh với tên macro như `ENOENT`/`EACCES` trên nền tảng hỗ trợ; mã số numeric không phải wire protocol portable.
4. **`errno` gắn với thread** trên môi trường POSIX hiện đại. Khi code native chuyển việc sang thread khác, không mong thread mới “đọc lại” được lỗi của thread cũ; đưa mã lỗi vào result/context cụ thể.

Ví dụ cách phân loại một lỗi POSIX sau khi bắt trạng thái thất bại:

~~~c
int saved_errno = errno;   /* Chỉ hợp lý ngay sau API báo lỗi. */

if (saved_errno == ENOENT) {
    /* File/path không tồn tại. */
} else if (saved_errno == EACCES) {
    /* Không được phép truy cập. */
} else {
    /* Lỗi khác; giữ lại mã gốc cho log/diagnostics. */
}
~~~

Những mã trên chỉ có ý nghĩa theo hợp đồng POSIX. Khi thiết kế Java API, bạn có thể map `ENOENT` thành `NoSuchFileException`, `EACCES` thành `AccessDeniedException` hoặc fallback thành `IOException` **nếu thao tác thật sự là truy cập tệp** và bạn có đầy đủ thông tin cần thiết. Không có bảng “mọi errno X luôn bằng Java exception Y” cho mọi thư viện và mọi bài toán.

### Trường hợp đặc biệt: `-1` vẫn có thể là thành công

Một số API được tài liệu hóa có thể trả `-1` **như một kết quả hợp lệ** (ví dụ `getpriority` trên POSIX). Với những API này, phải làm đúng chỉ dẫn của API, thường là **đặt `errno = 0` trước lời gọi**, rồi kiểm tra đồng thời return value và `errno`. Đó là ngoại lệ theo hợp đồng riêng, không phải lời khuyên đặt `errno = 0` trước mọi lời gọi C.

## 5. Hằng trạng thái JNI cũng không phải ngoại lệ Java

JNI có các mã trả về như `JNI_OK` (thành công, 0), `JNI_ERR` (lỗi chung, -1), `JNI_EDETACHED` (thread chưa attach), `JNI_EVERSION` (phiên bản JNI không hỗ trợ) trong các API phù hợp như JavaVM Invocation API. Đây là **status codes của API JNI**, không phải Java `Throwable`.

Đừng viết:

~~~c
/* Sai khi hàm "calculate" có nghĩa trả dữ liệu số học. */
return JNI_ERR; /* Java nhìn thấy số nguyên -1, không tự có exception. */
~~~

Nếu Java method khai báo `native int calculate()`, việc trả `JNI_ERR` bằng số nguyên vẫn chỉ trả -1 trừ khi có exception pending. `JNI_ERR` cũng không phải mã lỗi POSIX `errno`, và hoàn toàn không đồng nghĩa với một nguyên nhân cụ thể như thiếu file, kết nối thất bại hoặc sai input.

Ở chiều ngược lại, một API JNI trả `NULL` và có pending exception thì code C phải **kiểm tra exception**, không tùy tiện thay thế bằng một exception khác hoặc xử lý NULL như một value bình thường.

## 6. Java exception pending là trạng thái của Java thread

Java có cơ chế `try/catch/finally` và các lớp exception. JNI định nghĩa một cách tương tác **theo trạng thái**:

- Native code có thể yêu cầu JVM ném một `Throwable` bằng `Throw` hoặc `ThrowNew`.
- JNI API như `FindClass`, `NewObject`, `CallObjectMethod`, `GetObjectArrayElement` cũng có thể làm phát sinh exception, tùy hàm và điều kiện.
- Trong native method, exception thường nằm ở trạng thái **pending** trên Java thread hiện tại. Sau `ThrowNew`, C **không tự nhảy** đến một khối `catch` nào và không tự rời hàm.
- Khi quay lại Java, JVM chuyển pending exception sang cơ chế exception thông thường của Java; phía Java có thể `catch` kiểu phù hợp.

Sơ đồ khái niệm:

~~~text
Java gọi native method
        |
        v
C gọi JNI hoặc thư viện native
        |
        +--> Native status code? ----> C quyết định kiểm tra và dịch lỗi
        |
        +--> Sentinel? --------------> C hiểu đúng theo API; có thể là dữ liệu
        |
        +--> JNI exception pending --> C cleanup hợp lệ và return
                                          |
                                          v
                                  JVM quay về Java
                                          |
                                          v
                                    Java catch/finally
~~~

**Lỗi dễ mắc:** tưởng `ThrowNew` giống C++ `throw` và các câu lệnh C ngay sau sẽ không chạy. Thực tế, nếu code C tự tiếp tục chạy, nó có thể thao tác dữ liệu chưa khởi tạo hoặc gọi JNI functions bị cấm khi exception đang pending.

## 7. Các JNI exception API cốt lõi

| API JNI | Chức năng chính | Điều cần nhớ |
| --- | --- | --- |
| `Throw(env, throwable)` | Đặt một `jthrowable` có sẵn thành exception pending | Cần một `jthrowable` hợp lệ |
| `ThrowNew(env, exceptionClass, message)` | Tạo throwable từ class và message, rồi đặt thành pending | `message` theo **Modified UTF-8** của JNI; kết quả `0` khi thành công, âm khi thất bại |
| `ExceptionCheck(env)` | Trả `JNI_TRUE` nếu đang có pending exception | Không cần tạo local reference mới; thường là lựa chọn gọn |
| `ExceptionOccurred(env)` | Lấy local reference tới throwable pending, hoặc `NULL` | Có thể dùng để phân tích/giữ throwable; phải tôn trọng local-reference lifetime |
| `ExceptionClear(env)` | Xóa exception pending | Chỉ dùng khi bạn **cố ý đã xử lý hoặc thay thế** lỗi |
| `ExceptionDescribe(env)` | In diagnostic/backtrace ra kênh lỗi hệ thống | **Có side effect xóa pending exception**; không dùng vô ý trong đường propagate bình thường |
| `FatalError(env, message)` | Báo lỗi fatal và không kỳ vọng JVM hồi phục | Không dùng cho lỗi nghiệp vụ hay lỗi I/O có thể xử lý |

Các hàm này cần `JNIEnv *` hợp lệ của thread hiện tại. Một JNI native function thường có `JNIEnv *env` làm tham số thứ nhất.

Mẫu tạo Java exception từ native C (snippet có đầy đủ helper, nhưng cần được gọi trong native method có `env` hợp lệ):

~~~c
#include <jni.h>

/* Chỉ gọi helper khi chưa có exception pending. */
static void throw_illegal_argument(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(env, "java/lang/IllegalArgumentException");
    if (type == NULL) {
        /* FindClass không thành công; giữ lỗi đang pending nếu có. */
        return;
    }

    (void) (*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type); /* Cleanup hợp lệ khi pending. */
}
~~~

Trong code production, kiểm tra thêm nhánh JNI API thất bại mà **không** tạo pending exception (một số JNI functions có thể chỉ trả giá trị lỗi theo implementation) và bảo đảm không âm thầm biến thất bại tạo throwable thành kết quả hợp lệ. Việc xử lý OOM/low-memory ở JNI khó hơn code happy path; ví dụ ở đây tập trung vào phân biệt các mô hình lỗi.

Một C native method trả `jint` thường cần return một giá trị tạm để kết thúc hàm sau `ThrowNew`:

~~~c
/* Chỉ là snippet trong một hàm JNI đã xác định kiểu trả về jint. */
throw_illegal_argument(env, "invalid request");
return 0;  /* Khi exception pending, Java không nhận 0 như success. */
~~~

**Điều kiện cuối cùng:** helper phải thực sự tạo pending exception. Nếu helper thất bại hoàn toàn mà không còn exception, return 0 có thể bị hiểu thành dữ liệu thành công; đây là lý do cần quan tâm lỗi khi tạo exception.

## 8. Điều gì được gọi khi có exception pending?

Quy tắc JNI: **không gọi hầu hết JNI functions khi exception vẫn pending**. Hai hướng xử lý thông dụng:

1. **Propagate:** chỉ thực hiện cleanup bằng các API được cho phép, sau đó return khỏi native method; để JVM đưa lỗi tới Java.
2. **Handle/translate:** xác định rằng native code sở hữu việc xử lý lỗi, giữ thông tin cần thiết, gọi `ExceptionClear` có chủ đích, rồi thực hiện đường xử lý/mapping mới. Làm vậy có thể thay đổi ngữ nghĩa gốc; không được xóa exception chỉ để “tiếp tục chạy”.

Một số JNI functions dùng cho kiểm tra và cleanup được phép khi pending, ví dụ:

~~~text
ExceptionCheck, ExceptionOccurred, ExceptionClear, ExceptionDescribe
DeleteLocalRef, DeleteGlobalRef, DeleteWeakGlobalRef
ReleaseByteArrayElements, ReleaseStringChars, ReleaseStringUTFChars
ReleasePrimitiveArrayCritical, ReleaseStringCritical
MonitorExit, PopLocalFrame, PushLocalFrame
~~~

Đây là **danh sách ví dụ**, không thay thế danh sách đầy đủ trong [JNI Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html). Trong thực hành, `FindClass`, `NewStringUTF`, `GetMethodID` và các `Call...Method` **không** nên được gọi tùy ý khi có exception pending.

Ví dụ **sai**:

~~~c
jobject result = (*env)->CallObjectMethod(env, service, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* SAI: đang có exception pending; FindClass không được dùng ngay. */
    jclass type = (*env)->FindClass(env, "java/io/IOException");
    /* ... */
}
~~~

Ví dụ **đúng khi muốn propagate**:

~~~c
jobject result = (*env)->CallObjectMethod(env, service, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* Giải phóng các native resources / local refs đang sở hữu,
       chỉ dùng các JNI cleanup functions được phép. */
    return 0; /* Với native method có kiểu trả về jint. */
}
/* Chỉ được dùng result sau khi xác định không có lỗi. */
~~~

Nếu một function callback Java ném exception, kết quả trả về từ `Call...Method` có thể **không còn ý nghĩa**; không dùng nó làm dữ liệu thành công. Với callback chứa side effects, exception không tự rollback những gì C đã làm trước đó.

### Tránh một bẫy đặc biệt: `ExceptionDescribe`

Trong quá trình debug, `ExceptionDescribe` in lỗi/stack trace ra kênh chẩn đoán, **đồng thời xóa pending exception**. Nếu gọi nó rồi return mà không khôi phục hoặc thay thế, Java có thể thấy **native method thành công hoặc trả sentinel**, thay vì exception ban đầu. Log một lỗi không đồng nghĩa với xử lý được lỗi.

### Khi nào dùng `ExceptionClear`?

Chỉ khi chủ động chọn chính sách khác, ví dụ native code gọi một Java callback có thể fail và **có contract nói lỗi callback được bỏ qua, operation được phục hồi**; hoặc native code muốn chuyển exception sang loại khác có cause/context phù hợp. Khi thay exception, hãy chú ý bảo toàn thông tin gốc và các lỗi phát sinh trong lúc dựng exception mới. Đừng dùng `ExceptionClear` như bước “sửa lỗi” mặc định.

## 9. Ví dụ hoàn chỉnh JNI: status, exception và callback

Ví dụ này dùng **error codes do thư viện minh họa tự định nghĩa**, nên stdout ổn định trên nhiều OS. Nó không cần file thật, network hay hệ thống `errno` để kích hoạt lỗi. Mục đích là quan sát ba kênh lỗi rõ ràng.

Hợp đồng thư viện C giả lập:

- `read_number(request, &value)` trả `STATUS_OK=0` và value `request * 2` khi hợp lệ.
- Request âm trả `STATUS_INVALID=7`.
- Request bằng 13 trả `STATUS_BUSY=9`.
- Request quá lớn để nhân đôi trong `jint` được xem là không hợp lệ để tránh signed C overflow.
- `out_value` **chỉ hợp lệ khi status = STATUS_OK**.

JNI expose ba phương thức Java:

1. `rawStatus`: trả **mã lỗi native**, Java phải đọc code.
2. `checkedValue`: ở nhánh thành công trả giá trị số; ở nhánh lỗi dịch status sang **Java exception**.
3. `callJava`: gọi lại Java callback bằng JNI; nếu callback ném exception, **giữ nguyên pending exception** cho Java caller.

### 9.1. Java source: `NativeErrorModels.java`

~~~java
import java.util.function.IntSupplier;

public final class NativeErrorModels {
    static {
        System.loadLibrary("nativeerrormodels");
    }

    // 0 = OK, 7 = invalid request, 9 = simulated busy.
    private static native int rawStatus(int request);

    // Trả payload nếu thành công; ném exception Java nếu thất bại.
    private static native int checkedValue(int request);

    // Có thể nhận exception từ Java callback được gọi trong C.
    private static native int callJava(boolean fail);

    private static int javaCallback(boolean fail) {
        if (fail) {
            throw new IllegalStateException("Java callback failed");
        }
        return 41;
    }

    private static void show(String label, IntSupplier operation) {
        try {
            System.out.println(label + "=" + operation.getAsInt());
        } catch (RuntimeException ex) {
            System.out.println(label + "="
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        System.out.println("status-ok=" + rawStatus(7));
        System.out.println("status-invalid=" + rawStatus(-1));
        System.out.println("status-busy=" + rawStatus(13));

        show("value-ok", () -> checkedValue(7));
        show("value-zero", () -> checkedValue(0));
        show("value-invalid", () -> checkedValue(-1));
        show("value-busy", () -> checkedValue(13));

        show("callback-ok", () -> callJava(false));
        show("callback-fail", () -> callJava(true));
    }
}
~~~

Lưu ý: `show` chỉ `catch RuntimeException` để làm rõ kết quả mong đợi của ví dụ. Ứng dụng thực không nên bắt tràn lan rồi nuốt mọi lỗi; với I/O và resource management, caller cần phân loại lỗi, propagate khi cần, và giữ cause.

### 9.2. C source: `NativeErrorModels.c`

~~~c
#include <jni.h>
#include <stdint.h>
#include "NativeErrorModels.h"  /* Được sinh bằng javac -h . */

enum {
    STATUS_OK = 0,
    STATUS_INVALID = 7,
    STATUS_BUSY = 9
};

/* Mô phỏng thư viện C với return=status, out_value=payload. */
static jint read_number(jint request, jint *out_value) {
    if (request < 0 || request > INT32_MAX / 2) {
        return STATUS_INVALID;
    }
    if (request == 13) {
        return STATUS_BUSY;
    }
    *out_value = request * 2;
    return STATUS_OK;
}

/* Chỉ gọi helper này khi chưa có exception pending. */
static void raise_java(JNIEnv *env,
                       const char *exception_class,
                       const char *message) {
    jclass type = (*env)->FindClass(env, exception_class);
    if (type == NULL) {
        /* Không tạo exception mới: để nguyên lỗi JNI nếu đã có. */
        return;
    }
    (void) (*env)->ThrowNew(env, type, message);
    (*env)->DeleteLocalRef(env, type);
}

/* Java nhận status 0/7/9 nguyên vẹn, không tự có exception. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_rawStatus(
        JNIEnv *env, jclass cls, jint request) {
    (void) env;
    (void) cls;
    jint ignored_value = 0;
    return read_number(request, &ignored_value);
}

/* Java nhận payload hoặc exception, không nhận status như dữ liệu. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_checkedValue(
        JNIEnv *env, jclass cls, jint request) {
    (void) cls;
    jint value = 0;
    jint status = read_number(request, &value);

    if (status == STATUS_INVALID) {
        raise_java(env, "java/lang/IllegalArgumentException",
                   "negative or oversized request");
        return 0;  /* Giá trị tạm; Java sẽ nhận exception. */
    }
    if (status == STATUS_BUSY) {
        raise_java(env, "java/lang/IllegalStateException",
                   "simulated native busy");
        return 0;
    }
    if (status != STATUS_OK) {
        raise_java(env, "java/lang/IllegalStateException",
                   "unexpected native status");
        return 0;
    }
    return value; /* Chỉ thành công mới đọc payload. */
}

/* Native gọi Java callback; Java exception được giữ nguyên. */
JNIEXPORT jint JNICALL Java_NativeErrorModels_callJava(
        JNIEnv *env, jclass cls, jboolean fail) {
    jmethodID method = (*env)->GetStaticMethodID(
            env, cls, "javaCallback", "(Z)I");

    if (method == NULL) {
        /* JNI lookup lỗi; có thể có pending exception. */
        return 0;
    }

    jint result = (*env)->CallStaticIntMethod(env, cls, method, fail);
    if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
        /* Giữ exception từ callback; KHÔNG gọi FindClass/ThrowNew. */
        return 0;
    }
    return result;
}
~~~

**Kiểm tra các điểm then chốt:**

- `read_number` là **hàm C thuần**, trả status riêng. Nó không dùng `JNIEnv` và không thể tự “ném Java exception” nếu không có JNI context/hợp đồng khác.
- `rawStatus` là wrapper truyền trạng thái qua biên JNI. Java sẽ nhìn thấy các số `0`, `7`, `9` như giá trị `int` bình thường.
- `checkedValue` chọn ánh xạ từ status sang `IllegalArgumentException` hoặc `IllegalStateException`. Đó là **quyết định thiết kế của wrapper**. Với lỗi file thật, loại phù hợp có thể là `IOException` hoặc subtype cụ thể.
- `raise_java` gọi `FindClass` trước khi có pending exception, rồi `ThrowNew`. `DeleteLocalRef` là một cleanup được phép sau `ThrowNew`.
- `GetStaticMethodID` tìm đúng callback `(Z)I` (một `boolean`, trả `int`). `CallStaticIntMethod` có thể chạy Java code và làm phát sinh exception; C dùng `ExceptionCheck` rồi return.
- **Không** xóa callback exception và không thay bằng `IllegalStateException` khác, nên Java caller nhận được chính exception `"Java callback failed"`.

Đây là một mẫu học tập đơn giản; trong production cần harden nhánh tạo Java exception thất bại mà không có pending exception, chiến lược log/telemetry và owner của mọi native resources. Ví dụ cố ý không đặt JNI methods trên nhiều thread và không giữ pointer lâu dài.

### 9.3. Biên dịch và chạy trên Linux

Đặt `NativeErrorModels.java` và `NativeErrorModels.c` trong cùng thư mục. Yêu cầu JDK **17 trở lên**, compiler C hỗ trợ C11 và biến `JAVA_HOME` trỏ tới đúng JDK.

~~~bash
javac -encoding UTF-8 -h . NativeErrorModels.java

cc -std=c11 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  NativeErrorModels.c -o libnativeerrormodels.so

java -Djava.library.path=. NativeErrorModels
~~~

Stdout của lệnh `java`:

~~~text
status-ok=0
status-invalid=7
status-busy=9
value-ok=14
value-zero=0
value-invalid=IllegalArgumentException: negative or oversized request
value-busy=IllegalStateException: simulated native busy
callback-ok=41
callback-fail=IllegalStateException: Java callback failed
~~~

Thực tế `javac -h .` tạo header `NativeErrorModels.h` để prototype C được compiler kiểm tra. Lệnh `cc` ở trên dùng include path Linux và tên shared library `.so`. Trên Windows/macOS, bạn cần compiler, platform include directory và cách tạo shared library tương ứng; không dùng nguyên lệnh Linux như chỉ dẫn đa nền tảng.

Bài này không yêu cầu gọi `System.gc()`, network hoặc tạo lỗi OS thật. Ba kênh kết quả được kiểm thử **deterministic**:

- `status-invalid=7` là một **mã lỗi native** được Java nhận trực tiếp.
- `value-invalid=IllegalArgumentException...` là **một Java exception** được wrapper tạo từ mã lỗi 7.
- `callback-fail=IllegalStateException...` là **exception Java có nguồn gốc từ callback**, native code chỉ phát hiện pending và propagate.

### 9.4. Chú ý về nhánh tạo throwable thất bại

Mẫu `raise_java` ở trên minh họa case thường gặp; trong hệ thống production, cần định nghĩa rõ cách xử lý khi `FindClass` không tìm được class, khi `ThrowNew` thất bại hoặc khi hệ thống thiếu bộ nhớ nghiêm trọng. Một số JNI functions có thể báo lỗi bằng giá trị `NULL`/âm mà không đồng thời tạo pending exception. Nếu wrapper luôn `return 0` sau helper bất kể có exception hay không, Java có nguy cơ nhìn thấy **giá trị 0 hợp lệ nhưng sai**.

Cách phòng ngừa ở mức thiết kế:

1. Dùng class ngoại lệ Java chuẩn, có khả năng load ổn định theo class loader phù hợp.
2. Kiểm tra kết quả `FindClass` và `ThrowNew`; nếu thất bại, **không âm thầm coi operation thành công**.
3. Thiết kế hợp đồng kết quả có thể biểu diễn thất bại khi không dựng được throwable (ví dụ status + out parameter hoặc result object do Java tạo ở lớp wrapper), và xác định cách fallback cho low-memory.
4. Không gọi `FindClass`/`ThrowNew` nếu **đã có exception pending** từ bước trước; hãy ưu tiên propagate lỗi gốc khi không có lý do rõ ràng để thay thế.

Đối với mã đơn giản, nhiều library wrappers ánh xạ native status **ở Java layer** thay vì trực tiếp trong JNI C. Điều đó có thể làm dễ test/class loading hơn, đặc biệt khi native side không cần biết hierarchy các exception.

## 10. Pattern khác: JNI trả status, Java wrapper ném exception

Một biến thể thường rõ ràng hơn khi cần giữ nhiều thông tin native: C chỉ ghi `status` và `output`, Java wrapper chịu trách nhiệm ném exception. Chẳng hạn một API JNI có thể khai báo:

~~~java
// Contract: status 0/7/9; nếu status != 0, output[0] không hợp lệ.
private static native int readRaw(int request, int[] output);

public static int readNumber(int request) {
    int[] output = new int[1];
    int status = readRaw(request, output);

    switch (status) {
        case 0:
            return output[0];
        case 7:
            throw new IllegalArgumentException("invalid request");
        case 9:
            throw new IllegalStateException("native busy");
        default:
            throw new IllegalStateException("native status: " + status);
    }
}
~~~

**Đây là minh họa thiết kế**, chưa chạy độc lập vì thiếu class bao quanh và C implementation của `readRaw`. Nhánh thành công dùng `output[0]` sau khi status đúng; nhánh lỗi không đụng đến output. Nếu native code đọc/ghi `int[]`, phải dùng JNI array functions đúng cặp; `jintArray` không phải `jint *`.

Ưu điểm của cách này: Java code trực tiếp kiểm soát kiểu exception, cause, retry policy, stack trace và log. Nhưng khi chính JNI call bên dưới đã tạo một pending Java exception (ví dụ `SetIntArrayRegion` thất bại), wrapper Java **không thể nhận status bình thường** cho lời gọi đó; exception cần được propagate hoặc xử lý ở JNI theo hợp đồng.

## 11. Chọn Java exception theo ý nghĩa lỗi

Khi native code phát hiện lỗi, hãy chọn loại exception dựa vào **ý nghĩa Java API đang cung cấp**, chứ không phải chỉ dựa số status.

| Điều kiện | Lựa chọn Java điển hình | Vì sao |
| --- | --- | --- |
| Tham số Java không hợp lệ | `IllegalArgumentException` (hoặc subtype thích hợp) | Caller cần sửa input |
| Trạng thái đối tượng/operation không phù hợp | `IllegalStateException` | Caller cần đổi trạng thái/thứ tự gọi |
| Truy cập tệp hoặc stream gặp lỗi I/O | `IOException`, `FileNotFoundException` hoặc `java.nio.file` subtype | Thể hiện lỗi I/O đúng miền nghiệp vụ |
| Dữ liệu native bị malformed | `IllegalArgumentException`, exception parser cụ thể hoặc checked type | Tùy hợp đồng parser |
| Operation bị timeout | Exception timeout có ý nghĩa với Java API | Có thể cần retry với timeout/cancellation |
| Không tìm thấy dữ liệu mà API coi là bình thường | `Optional`/`null`/sentinel có document rõ | Không nhất thiết là exception |
| Thiếu bộ nhớ trầm trọng | `OutOfMemoryError` do JVM/native policy phù hợp | Không ngụy tạo thành lỗi input thông thường |

**Checked vs unchecked:** `IOException` là checked exception. Nếu Java native method có thể ném loại này, thông thường nên khai báo `throws IOException` để caller biết hợp đồng:

~~~java
public native byte[] readFile(String path) throws java.io.IOException;
~~~

JNI có thể tạo một checked exception ngay cả khi Java declaration thiếu `throws` (JVM không bắt buộc JNI tuân thủ compile-time checked-exception rules). Tuy nhiên, không vì thế mà cố tình bỏ `throws` khỏi public Java API; điều đó làm sai lệch contract của thư viện và khiến caller khó xử lý.

**Giữ cause:** nếu native library cung cấp mã hệ điều hành, tên subsystem và operation, hãy giữ nguyên thông tin đó trong exception message, custom field hoặc cause theo chính sách API. Không gộp tất cả lỗi thành `RuntimeException("native failed")` khiến điều tra nguyên nhân không thể thực hiện.

## 12. Khi Java callback ném exception trong lúc C đang chạy

Luồng gọi có thể ngược chiều:

~~~text
Java caller
  -> JNI native method
       -> C gọi CallStaticIntMethod / CallObjectMethod
            -> Java callback ném IllegalStateException
       <- C nhận quyền điều khiển và thấy exception PENDING
  <- Native return (sau cleanup hợp lệ)
Java caller catch IllegalStateException
~~~

Quan trọng: **exception từ callback không tự unwind native C stack**. Native phải gọi `ExceptionCheck` hoặc kiểm kết quả JNI theo hợp đồng, rồi chủ động rời hàm. Không tiếp tục công việc như thể callback đã thành công.

Snippet sai:

~~~c
jint result = (*env)->CallIntMethod(env, callback, method_id);
/* SAI: callback có thể đã ném exception.
   Dùng result như dữ liệu hợp lệ là sai và có thể làm lệch state. */
native_commit(result);
~~~

Mẫu đúng hơn:

~~~c
jint result = (*env)->CallIntMethod(env, callback, method_id);
if ((*env)->ExceptionCheck(env)) {
    /* Rollback native state nếu hợp đồng yêu cầu, cleanup tài nguyên.
       Không gọi các JNI functions không được phép khi pending. */
    return 0; /* Với native method có kiểu trả về jint. */
}
native_commit(result); /* Chỉ chạy khi callback thực sự thành công. */
~~~

Hai snippet minh họa; `callback`/`method_id`/`native_commit` được định nghĩa bởi ứng dụng thực. Nếu việc gọi callback đã thực hiện side effects trước khi ném, không giả định native code có thể rollback toàn bộ side effects Java.

## 13. C++ exception và native crash: không đồng nhất với Java `Throwable`

Một native C++ function có thể `throw std::runtime_error`. Nhưng **C++ exception không được để thoát xuyên qua JNI boundary** vào JVM như thể nó tự biến thành Java exception. Hãy chặn ở C++ adapter, cleanup tài nguyên theo RAII, rồi ánh xạ sang Java status/exception theo chính sách. Mã minh họa (đoạn trong C++ JNI method; `translateToJava` là helper của ứng dụng):

~~~cpp
try {
    run_native_operation();
} catch (const std::bad_alloc&) {
    /* Chuyển thành chính sách lỗi bộ nhớ phù hợp cho Java. */
    translateToJava(env, "java/lang/OutOfMemoryError", "native allocation failed");
} catch (const std::exception& ex) {
    translateToJava(env, "java/lang/IllegalStateException", ex.what());
}
~~~

**Không biên dịch snippet này độc lập:** cần `run_native_operation`, `translateToJava` và định nghĩa JNI method. Nó chỉ biểu diễn ranh giới bắt ngoại lệ C++.

Tương tự, segmentation fault hoặc undefined behavior trong C/C++ có thể làm **crash cả tiến trình JVM**; chúng không phải `NullPointerException` Java có thể luôn `catch`. JNI `FatalError` cũng là đường lỗi fatal, không dùng để xử lý “file không tồn tại” hoặc status `BUSY` bình thường.

Điều này làm nổi bật một khác biệt khác: **kiểm tra mã lỗi native** là bắt buộc ngay cả khi phía Java có `try/catch`. `try/catch` Java không bảo vệ được mọi sai lầm quản lý bộ nhớ, con trỏ và ABI ở mã C.

## 14. Tài nguyên JNI khi xảy ra lỗi

Native function có thể đang giữ:

- Local/global JNI references;
- Dữ liệu từ `GetByteArrayElements`, `GetStringUTFChars` hoặc `GetPrimitiveArrayCritical`;
- File descriptors, socket handles, mutexes, buffer native `malloc`;
- Một callback hoặc transaction có state cần rollback.

Khi có lỗi, hãy cleanup **đúng nguồn tài nguyên** trước khi return:

~~~c
/* Snippet: data là jbyte* đã nhận từ GetByteArrayElements,
   array là jbyteArray hợp lệ, và callback đã ném Java exception. */
if ((*env)->ExceptionCheck(env)) {
    (*env)->ReleaseByteArrayElements(env, array, data, JNI_ABORT);
    /* Nếu có fd native hợp lệ, close(fd) theo hợp đồng POSIX. */
    return 0; /* Hàm JNI hiện tại trả jint. */
}
~~~

`ReleaseByteArrayElements` là API cleanup được phép khi có exception pending; `JNI_ABORT` báo không cần copy nội dung native buffer về mảng nếu thao tác chỉ đọc. Trường hợp native đã sửa dữ liệu và yêu cầu commit một phần khi lỗi phải được thiết kế riêng.

**Thứ tự cleanup matters:** nếu native operation thất bại và đặt `errno`, chụp `errno` trước khi gọi cleanup khác có thể thay nó; sau đó dùng mã đã chụp để tạo Java exception (trong trạng thái chưa có pending exception) hoặc trả status. Khi callback Java đã gây pending exception, cleanup bằng các JNI functions được phép, tránh dựng một Java exception thứ hai trừ khi chủ động xử lý/translate cái đầu.

Ví dụ chiến lược control flow:

~~~text
acquire native resource
try native operation
    success -> produce result
    native status failure -> capture code -> release resources -> map error
    Java callback pending -> release allowed resources -> return (propagate)
release resources
return result
~~~

Với C thuần có nhiều lối thoát, một khối `cleanup:` cùng `goto cleanup` có thể giúp bảo đảm mọi đường lỗi đều giải phóng tài nguyên; nhưng **không** đồng nghĩa cleanup xong thì có thể tiếp tục gọi JNI tùy ý trong khi pending. Ở C++, RAII hữu ích để giải phóng native resources khi C++ exception đã được bắt đúng boundary.

## 15. Tách "không có dữ liệu" khỏi "không thực thi được"

Một API tìm kiếm có thể trả trạng thái `FOUND`, `NOT_FOUND` và `ERROR`. Không nên dùng một kiểu Java exception cho mọi trường hợp nếu “không tìm thấy” là nghiệp vụ bình thường:

~~~java
// Gợi ý Java API: native method đã phân loại lỗi thật trong wrapper.
public java.util.OptionalInt findValue(int key) {
    // return OptionalInt.empty() khi dữ liệu thực sự không tồn tại;
    // ném exception khi database/native library không thể truy vấn.
    throw new UnsupportedOperationException("illustrative API shape");
}
~~~

Đoạn này **chỉ mô tả contract**, không phải implementation; không đưa placeholder đó vào code production. Nếu Java API chọn `OptionalInt.empty()` cho absence, nó vẫn cần một đường riêng để báo “query failed” (chẳng hạn exception), vì absence và failure là hai trạng thái khác nhau.

Một result type đầy đủ cũng có thể giữ metadata:

~~~text
Outcome:
  success(value)
  not_found
  invalid_input(details)
  temporary_failure(native_code, operation, can_retry)
  permanent_failure(native_code, operation)
~~~

Đây là một **mô hình khái niệm**, không phải Java syntax. Không cần ép mọi API dùng result object; lựa chọn dựa vào tần suất lỗi, nhu cầu xử lý của caller, yêu cầu binary compatibility và thông lệ Java API.

## 16. Nên retry khi nào?

Native error code có thể biểu thị “tạm thời không sẵn sàng”, ví dụ service bận hoặc I/O gián đoạn. Nhưng retry chỉ hợp lệ khi đồng thời kiểm tra:

1. **Operation có idempotent không?** Việc gửi thanh toán, ghi record hoặc tiêu thụ message có thể đã có side effect dù caller nhận lỗi.
2. **Mã lỗi nói chính xác gì?** Không phải mọi `EAGAIN`/`BUSY` đều nên retry vô hạn; phải xem hợp đồng API và thời hạn.
3. **Có cancellation, deadline, backoff và giới hạn số lượt?** Retry thiếu giới hạn có thể làm quá tải service.
4. **Error context có được giữ không?** Ghi nhận attempt, operation, native status và nguyên nhân cuối cùng mà không lộ dữ liệu nhạy cảm.

Ở Java boundary, việc đổi mọi status thành cùng một `IllegalStateException` mà bỏ mã gốc có thể làm mất khả năng phân loại retry. Nếu cần logic tự động, cân nhắc exception subtype hoặc result có error kind ổn định thay vì parse string message.

## 17. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Java `catch` không chạy khi C trả `-1` | C chỉ trả một số, chưa có Java exception pending | Thiết kế Java wrapper kiểm status hoặc dùng `ThrowNew` có chủ đích |
| Lỗi file bị báo như giá trị 0 | JNI code trả 0 sau thất bại nhưng không tạo được exception | Kiểm kết quả tạo exception; giữ fail-closed contract ở lớp wrapper |
| `errno` cho giá trị lạ dù `open` thất bại | Đọc `errno` sau JNI calls/log/cleanup | Lưu `int saved = errno;` ngay sau lỗi |
| Hàm báo success nhưng `errno != 0` | Giả định `errno` luôn được reset khi thành công | Chỉ đọc `errno` khi contract nói có lỗi |
| Callback Java ném nhưng C tiếp tục dùng result | C++/C không tự unwind bởi Java exception pending | `ExceptionCheck` rồi cleanup/return |
| `FindClass`/`NewStringUTF` crash khi pending | Gọi JNI không hợp lệ trong trạng thái pending | Propagate và chỉ cleanup bằng JNI APIs được phép, hoặc clear có chủ đích |
| Log xong Java không còn thấy exception | `ExceptionDescribe` đã xóa pending | Không dùng như logger thường xuyên trên đường propagate |
| `NULL` từ `GetObjectField` bị coi là lỗi | Java field thực sự có giá trị `null` | Phân biệt null hợp lệ với pending exception |
| `JNI_ERR` bị coi là `IOException` | Nhầm mã JNI API với phân loại lỗi filesystem | Dựa vào API cụ thể và mapping ở boundary |
| C++ exception thoát khỏi JNI entry point | Không bắt ở native wrapper | Catch trong C++ và chuyển sang contract Java |
| Native error bị ném hai lần | Vừa có pending exception vừa gọi `ThrowNew` khác | Ưu tiên giữ lỗi gốc, clear/translate có chủ đích nếu cần |
| JNI làm mất resource khi callback fail | Chỉ cleanup ở nhánh success | Gom đường cleanup cho mọi lối thoát, kiểm pending |

### Anti-pattern: tự dựng exception khi JNI đã pending

~~~c
jclass cls = (*env)->FindClass(env, "com/example/LibraryClass");
if (cls == NULL) {
    /* SAI: FindClass có thể đã tạo một exception pending.
       Không gọi thêm FindClass ở đây để tự ép một lỗi khác. */
    jclass replacement =
        (*env)->FindClass(env, "java/lang/IllegalStateException");
    (void) replacement;
}
~~~

Phương án đúng là **kiểm tra pending, cleanup được phép, rồi return** hoặc chủ động xử lý/clear lỗi cũ theo một mapping được thiết kế cẩn thận.

## 18. Ma trận kiểm thử cho JNI error boundary

| Tình huống | Kết quả mong muốn | Gợi ý kiểm tra |
| --- | --- | --- |
| Success với output = 0 | `0` là dữ liệu thành công, không bị coi là lỗi | `checkedValue(0)` |
| Status lỗi input | Java wrapper ném đúng exception hoặc trả status được caller kiểm | `rawStatus(-1)`, `checkedValue(-1)` |
| Native busy/tạm không sẵn | Status được giữ và mapping đúng contract | `rawStatus(13)`, `checkedValue(13)` |
| Sentinel -1 là dữ liệu hợp lệ | Không nhầm thành lỗi | `valueOrThrow(true, -1)` |
| Java callback ném exception | C không dùng callback result; Java nhận exception gốc | `callJava(true)` |
| JNI API lookup thất bại | Propagate pending exception, không gọi tiếp JNI bừa bãi | Cố ý kiểm `GetStaticMethodID`/signature khi test |
| Native allocation thất bại | Không trả thành công giả; cleanup và phân loại phù hợp | Mô phỏng allocator fail bằng dependency injection |
| POSIX call báo -1/`errno` | Chụp đúng `errno`, giữ metadata | Fake native wrapper hoặc kiểm thử trên POSIX |
| Error path qua JNI array/string | Các cặp acquire/release cân bằng | Valgrind/ASan hoặc CheckJNI khi có thể |
| Nhiều thread | Mã lỗi thread riêng và exception đúng thread | Test concurrency theo thiết kế bridge |
| C++ exception/native crash | Không để C++ exception đi xuyên JNI; crash được điều tra native | Native unit tests và sanitizer |

**Đừng cố gây segmentation fault trong JVM chỉ để chứng minh `try/catch` không chặn được.** Dùng unit tests/sanitizer trên native layer phù hợp và phân tích crash logs khi có lỗi thật.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Hàm C trả `-1` và Java native method cũng có return type `int`. `catch(IOException)` có tự chạy không?

Không. Nếu C chỉ `return -1;`, Java nhận số -1; muốn `catch` chạy phải có Java exception thực sự (được Java/JNI tạo) hoặc Java wrapper kiểm giá trị rồi ném.

**Câu 2.** Hàm native thành công với dữ liệu `0`, còn status `0` cũng quy ước thành công. Làm sao phân biệt?

Dựa vào hợp đồng. Nếu return chỉ chứa status, dữ liệu đi qua out-parameter; nếu return chứa dữ liệu, không xem 0 là status. Phân biệt hai hàm khác nhau bằng contract, không chỉ kiểu `jint`.

**Câu 3.** `errno` có luôn bằng 0 sau một lời gọi C thành công không?

Không. `errno` chỉ có ý nghĩa theo hợp đồng của API khi có dấu hiệu lỗi, và thành công không nhất thiết xóa `errno`.

**Câu 4.** Java callback ném `IllegalStateException` qua `CallStaticIntMethod`. C có thể gọi `NewStringUTF` trước khi return không?

Thông thường không. Khi exception vẫn pending, không gọi hầu hết JNI functions; hãy cleanup bằng API được phép và return để propagate, hoặc clear có chủ đích khi thật sự xử lý lỗi.

**Câu 5.** `ThrowNew` là C++ `throw` và tự dừng C function ngay lập tức?

Không. Nó đặt Java exception pending; C vẫn thực thi nếu code còn chạy. Native code phải tự chọn control flow thích hợp và kết thúc sau cleanup.

**Câu 6.** `ExceptionDescribe` có thể dùng để log exception rồi để Java bắt chính exception đó không?

Không được giả định vậy. `ExceptionDescribe` **xóa pending exception** như side effect, nên muốn giữ exception gốc phải chọn một chiến lược chẩn đoán khác hoặc quản lý khôi phục có chủ đích.

**Câu 7.** Nếu một JNI call trả `NULL`, có chắc đã có Java exception?

Không. Một số API cho phép `NULL` là kết quả bình thường hoặc có thể chỉ báo lỗi mà không đặt exception. Phải xét contract từng hàm và kiểm tra pending khi cần.

**Câu 8.** Khi POSIX `open` trả lỗi, nên chuyển raw `errno` thành `IllegalArgumentException` luôn không?

Không. Phân loại theo ý nghĩa thao tác và hợp đồng Java API; có thể là `IOException`/`NoSuchFileException`/`AccessDeniedException`. Chụp `errno` đúng lúc, giữ error kind/context.

**Câu 9.** Native thread A có pending Java exception. Thread B có thể đọc `ExceptionCheck` bằng `JNIEnv *` của thread A không?

Không. `JNIEnv *` gắn với thread. Native thread B phải có JNI environment riêng sau khi được attach phù hợp; exception pending thuộc thread tương ứng.

**Câu 10.** Tại sao một C++ `throw std::runtime_error` không nên vượt JNI boundary?

Vì JNI không định nghĩa việc C++ stack unwinding đi xuyên JVM frame để thành một Java `Throwable`. Bắt C++ exception ở native adapter và dịch sang Java contract trước khi trở về JVM.

## 20. Checklist quyết định ở ranh giới Java ↔ native

- [ ] Xác định **mỗi C API** trả status, sentinel hay payload; có nhánh `errno`/out-parameter nào không?
- [ ] Phân biệt `JNI_OK`/`JNI_ERR` với errno/native library codes, không cố dùng một mã cho tất cả.
- [ ] Chỉ dùng giá trị output khi hàm báo thành công; không để `-1`/`NULL` bị hiểu nhầm thành lỗi nếu chúng hợp lệ.
- [ ] Chụp lỗi OS **ngay** khi contract cho biết có lỗi, giữ native code/context nếu cần chẩn đoán.
- [ ] Quy định chính sách Java API: return result, absence, checked/unchecked exception, mapping/retry.
- [ ] Sau JNI call có thể throw, kiểm return value và `ExceptionCheck`/`ExceptionOccurred` theo hợp đồng.
- [ ] Khi exception pending, cleanup bằng JNI APIs được phép; tránh gọi `FindClass`/`Call...Method`/`NewStringUTF` tùy ý.
- [ ] Nếu dùng `ThrowNew`, kết thúc C flow rõ ràng; bảo đảm không biến lỗi tạo throwable thành return thành công giả.
- [ ] Nếu dùng `ExceptionClear` hoặc `ExceptionDescribe`, có chủ đích rõ; không vô tình nuốt lỗi Java gốc.
- [ ] Native resources và JNI references được release trên cả success/error/exception paths.
- [ ] C++ exception được catch tại native boundary; không để undefined behavior/crash lẫn vào Java error flow.
- [ ] Kiểm thử success=0, dữ liệu=-1, missing, native error, JNI pending, callback failure, resource cleanup, OOM fallback và concurrency khi liên quan.

## Tài liệu tham khảo

- [Oracle JNI Specification: Design Overview — Exceptions and Error Codes](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): pending exception, JNI control flow, các JNI functions hợp lệ khi pending.
- [Oracle JNI Specification: Functions — `ThrowNew`, `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe` và `ExceptionClear`](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): hợp đồng chi tiết từng function.
- [Oracle JNI Specification: Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jint`, `jobject`, `JNIEnv` và cách dùng kiểu JNI.
- [Linux man-pages `errno(3)`](https://man7.org/linux/man-pages/man3/errno.3.html): thời điểm đọc `errno` và ý nghĩa của mã lỗi POSIX.
- [POSIX `errno`](https://man7.org/linux/man-pages/man3/errno.3p.html): giới hạn hiệu lực và điều kiện của `errno`.
- [Java SE 17 `IOException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/IOException.html): Java checked exception tiêu biểu cho I/O.

**Ghi nhớ:** Native error code và sentinel là **hợp đồng giá trị trả về của API bản địa**; Java exception là **trạng thái lỗi được JVM quản lý**. JNI bridge phải chủ động phân loại, kiểm tra, chuyển đổi và cleanup. Đừng để một số nguyên, `NULL` hay `errno` tự quyết định ngữ nghĩa Java; và đừng để một Java exception pending bị che lấp bởi JNI calls tiếp theo.
