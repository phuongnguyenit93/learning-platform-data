# Ném ngoại lệ Java từ JNI bằng `Throw` hoặc `ThrowNew` với thông điệp phù hợp

## 1. Mục tiêu: biến lỗi native thành ngoại lệ Java có ý nghĩa

Một phương thức `native` có thể phát hiện tham số không hợp lệ, lỗi trạng thái hoặc lỗi từ API C/C++. Nếu chỉ in thông báo bằng `printf` rồi trả một giá trị mặc định, phía Java thường không biết rằng thao tác đã thất bại. JNI cung cấp hai API chính để **đặt một Java exception ở trạng thái pending trên thread hiện tại**:

- `ThrowNew`: tạo **một đối tượng ngoại lệ mới** thuộc class chỉ định, dùng chuỗi thông điệp được cung cấp, rồi đánh dấu ngoại lệ để ném.
- `Throw`: dùng **một đối tượng `Throwable` đã tồn tại**, đánh dấu chính đối tượng đó để ném. Hữu ích khi muốn giữ nguyên cause, suppressed exceptions, loại ngoại lệ tùy biến, hoặc cùng exception instance.

Sau khi gọi thành công một trong hai hàm, **mã C/C++ vẫn tiếp tục chạy** cho đến khi nó chủ động `return` hoặc chuyển luồng điều khiển. JNI không hoạt động như câu lệnh `throw` trong Java/C++ tự động thoát khỏi native method. Thông thường, native method **dọn tài nguyên được phép dọn, rồi return**. JVM sẽ chuyển pending exception sang phía Java gọi native method; Java có thể bắt bằng `try/catch` như mọi Java exception khác.

Đây là sự khác biệt phải ghi nhớ:

```text
Mã Java gọi native method
         │
         ▼
JNI C/C++ phát hiện lỗi
         │
         ├─ ThrowNew(exceptionClass, message)
         │           hoặc
         └─ Throw(existingThrowable)
                     │
                     ▼
       Java exception trở thành pending
                     │
          Dọn native resources an toàn
                     │
           return khỏi native method
                     │
                     ▼
 Java thấy ngoại lệ trong try/catch
```

**Không coi mã trả về của `Throw`/`ThrowNew` là giá trị trả về nghiệp vụ.** Chúng trả về `jint` bằng `0` khi thiết lập ngoại lệ thành công, số âm khi thất bại. Đó là trạng thái thao tác JNI; ngoại lệ Java được mang bằng cơ chế *pending exception*, không phải bằng giá trị `jint` ấy.

## 2. Chữ ký, tham số và cách gọi đúng

### 2.1. `ThrowNew`: loại ngoại lệ mới và message

Chữ ký trong JNI C:

```c
jint ThrowNew(JNIEnv *env, jclass clazz, const char *message);
```

Cách gọi bằng C:

```c
jint rc = (*env)->ThrowNew(
        env, exceptionClass, "value must be >= 0");
```

Cách gọi bằng C++:

```cpp
jint rc = env->ThrowNew(
        exceptionClass, "value must be >= 0");
```

- `env` là JNI environment của **thread hiện tại**.
- `clazz` phải là `jclass` hợp lệ biểu diễn một lớp kế thừa `java.lang.Throwable`, ví dụ `java.lang.IllegalArgumentException`. Không truyền `NULL` cho `clazz`.
- `message` là chuỗi ký tự C **được mã hóa bằng JNI Modified UTF-8**, hoặc `NULL` khi thật sự không muốn cung cấp thông điệp. Nó không phải `jstring`.
- Hàm tạo một exception object và đặt nó thành pending, trả `0` khi thành công hoặc giá trị âm khi thất bại.

Mẫu phổ biến là tìm class exception bằng tên nhị phân JNI có dấu gạch chéo:

```c
jclass cls = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException");
if (cls == NULL) {
    /* FindClass không lấy được class; giữ nguyên lỗi hiện tại,
       không tiếp tục ThrowNew với cls == NULL. */
    return;
}

(void)(*env)->ThrowNew(
        env, cls, "argument size must be positive");
(*env)->DeleteLocalRef(env, cls);
return; /* Tự thoát khỏi native method. */
```

Đây là **fragment dành cho native method trả `void`**, không phải toàn bộ chương trình. `DeleteLocalRef` là một trong các JNI functions được phép gọi khi exception pending. Với native method trả `jint` hoặc `jobject`, phải viết một return phù hợp chữ ký C; khi exception vẫn pending, kết quả nghiệp vụ thông thường không được dùng như kết quả thành công.

### 2.2. `Throw`: dùng lại một `Throwable` đã có

Chữ ký JNI C:

```c
jint Throw(JNIEnv *env, jthrowable obj);
```

C:

```c
jint rc = (*env)->Throw(env, existingException);
```

C++:

```cpp
jint rc = env->Throw(existingException);
```

`existingException` là một `jthrowable` hợp lệ, **khác `NULL`** và còn sống trong phạm vi của JNI reference. Có thể đó là tham số Java gửi xuống, hoặc exception object do JNI tạo bằng constructor `NewObject`. Nếu muốn giữ lại một instance đã có, dùng `Throw` thay vì tạo ngoại lệ khác bằng `ThrowNew`.

`Throw` **không gọi constructor lần nữa** và không tự tạo message mới. Nó ném **chính object** được cung cấp: message, cause, suppressed exceptions và custom fields vốn đã tồn tại vẫn gắn với object đó.

### 2.3. Bảng quyết định

| Nhu cầu | Cách thường phù hợp | Lý do |
| --- | --- | --- |
| Native kiểm tra tham số âm, sai range, trạng thái không hợp lệ | `ThrowNew` với loại exception cụ thể và message rõ | Ngắn gọn, không cần tự tạo đối tượng `Throwable` |
| Java truyền sẵn `Throwable` cần ném lại | `Throw` | Giữ nguyên exception instance, cause và metadata |
| Cần exception có constructor riêng, cause hoặc custom fields | Tạo `Throwable` với `NewObject`, rồi `Throw` | `ThrowNew` chỉ nhận class và chuỗi message; không cho truyền cause trực tiếp |
| Callback Java vừa ném ngoại lệ và native không xử lý được | **Giữ nguyên pending exception, cleanup rồi return** | Không cần ném lần thứ hai hay che mất lỗi gốc |
| Muốn chuyển ngoại lệ cũ thành loại domain mới | Kiểm tra/capture exception, `ExceptionClear` có chủ đích, tạo wrapper có cause, rồi `Throw` | Giữ chuỗi nguyên nhân và hợp đồng lỗi |
| Lỗi thật sự nằm trong tầng C/C++ | Chuyển sang Java exception tại ranh giới JNI sau cleanup C/C++ | Không để C++ exception tùy tiện vượt qua C/JNI ABI |

Không cần dùng `ThrowNew` cho mọi lỗi; và không gọi `Throw` khi chưa có một `Throwable` object hợp lệ.

## 3. Chọn class và message sao cho dễ sửa lỗi

### 3.1. Chọn loại ngoại lệ có ngữ nghĩa

Một message hay nhưng chọn sai exception type vẫn gây khó cho API Java. Nên sử dụng class chuẩn phù hợp, hoặc một domain exception công khai của thư viện khi có lý do rõ ràng.

| Bối cảnh | Class Java gợi ý | Message tốt hơn thông báo chung |
| --- | --- | --- |
| Tham số ngoài miền hợp lệ | `IllegalArgumentException` | `"batchSize must be > 0; received -4"` |
| Phép toán không thể thực hiện với trạng thái hiện tại | `IllegalStateException` | `"decoder is closed; cannot read frame"` |
| Chỉ số hoặc độ dài vượt phạm vi | `IndexOutOfBoundsException` | `"index 12 outside [0, 9]"` |
| Tính năng không được backend hỗ trợ | `UnsupportedOperationException` | `"native codec AV1 is unavailable on this platform"` |
| Lỗi quyền truy cập tài nguyên | `SecurityException` khi thực sự liên quan quyền | `"access denied for requested resource"` |
| Lỗi I/O ở native layer | `java.io.IOException` (checked) hoặc loại con phù hợp | `"cannot read header from input stream"` |
| Cần giữ lỗi backend với cause và mã lỗi riêng | Domain exception có fields và constructor phù hợp | Message mô tả operation + code, cause giữ lỗi gốc |

Phương thức Java nên **khai báo checked exception** trong hợp đồng khi dự kiến ném từ native, ví dụ `native byte[] read() throws IOException;`. JNI có thể ném một `Throwable` khi runtime cho phép ngay cả nếu Java declaration không liệt kê nó, nhưng cố tình bỏ khai báo checked exception khiến người dùng API khó xử lý đúng.

Không dùng `Error` (`OutOfMemoryError`, `LinkageError`, `InternalError`) như nhãn tiện lợi cho lỗi nhập liệu thường xuyên. `Error` thường biểu thị lỗi nghiêm trọng mà ứng dụng không nên coi như nhánh xử lý thông thường. Nếu chính JNI operation thất bại và VM đã đặt `OutOfMemoryError` pending, thường **trả quyền xử lý về Java** thay vì cố tạo ngoại lệ khác, vì mọi phép cấp phát bổ sung đều có nguy cơ thất bại.

### 3.2. Thông điệp phù hợp cần chứa thông tin gì?

Một message giúp người gọi biết **điều kiện mong đợi, giá trị nhận được, thao tác đang thực hiện**. Ví dụ:

```text
Không rõ:  "invalid input"
Rõ hơn:   "bufferLength must be >= 16; received 8"
Không rõ:  "operation failed"
Rõ hơn:   "cannot decode JPEG header: unsupported marker 0xD8"
```

Nguyên tắc thực hành:

1. **Tên tham số hoặc thao tác:** `length`, `offset`, `nativeDecode`, `openDevice`...
2. **Ràng buộc và giá trị liên quan:** `"expected 0..255; received 300"`. Chỉ đưa giá trị cần thiết và được phép công bố.
3. **Không giấu cause:** nếu phía Java cần phân tích ngữ cảnh sâu, dùng `Throwable` có cause (qua constructor phù hợp) rồi `Throw`.
4. **Tránh dữ liệu nhạy cảm:** không chép password, access token, toàn bộ payload, địa chỉ bộ nhớ raw hoặc dữ liệu người dùng nhạy cảm vào message; log có thể đi đến nhiều hệ thống.
5. **Ổn định theo loại ngoại lệ:** client nên dựa vào exception class, error code và contract; đừng parse message bằng regex để rẽ nhánh nghiệp vụ.
6. **Ngôn ngữ và encoding:** message của `ThrowNew` là Modified UTF-8; kiểm soát encoding trước khi đưa dữ liệu từ backend vào. Với thông báo Unicode phức tạp hoặc localized messages, có thể ưu tiên tạo `jstring`/`Throwable` từ Java.

Một message không nhất thiết phải dài. Khi class `IllegalArgumentException` và giá trị `batchSize` đã có, câu `"batchSize must be positive; received -4"` thường là đủ.

## 4. Pending exception: cơ chế quyết định cách viết code an toàn

### 4.1. Ném trong JNI không đồng nghĩa C đã dừng

Đoạn sau sai về luồng điều khiển:

```c
if (length < 0) {
    (*env)->ThrowNew(env, excClass, "length < 0");
}
/* SAI: mã C vẫn chạy, có thể tiếp tục truy cập buffer. */
read_bytes(buffer, length);
```

Đoạn đúng:

```c
if (length < 0) {
    (void)(*env)->ThrowNew(env, excClass, "length must be >= 0");
    return;  /* Ví dụ native method trả void. */
}

/* Chỉ thực hiện nếu dữ liệu đã hợp lệ. */
read_bytes(buffer, length);
```

Hai đoạn là **fragment** giả định `excClass` hợp lệ và `read_bytes` là hàm native do ứng dụng định nghĩa, không phải chương trình độc lập. Sau khi `ThrowNew` thành công, Java exception pending; nếu vẫn chạy code C như chưa có lỗi, có thể làm hỏng dữ liệu hoặc gây crash.

### 4.2. Khi nào cần `ExceptionCheck` / `ExceptionOccurred`?

Các JNI API sau giúp quản lý exception pending trên thread hiện tại:

- `ExceptionCheck(env)`: trả `JNI_TRUE` hoặc `JNI_FALSE` mà **không tạo local reference tới exception object**. Rất phù hợp khi chỉ cần rẽ nhánh nhanh.
- `ExceptionOccurred(env)`: trả `jthrowable` đang pending, hoặc `NULL` nếu không có. Đây là một local JNI reference; cần quản lý lifetime, đặc biệt nếu dùng qua nhiều bước.
- `ExceptionClear(env)`: **chủ động xóa pending exception**. Chỉ dùng khi mã native có chiến lược xử lý hoặc chuyển đổi lỗi đúng, không xóa để che lỗi.
- `ExceptionDescribe(env)`: in exception và stack trace ra kênh báo lỗi hệ thống rồi **xóa pending exception như một side effect**. Hữu ích khi debug, nhưng gọi vô ý có thể nuốt mất lỗi Java.
- `Throw` / `ThrowNew`: đặt exception pending nếu hợp lệ và thao tác thành công.

Ví dụ chuẩn khi native gọi ngược phương thức Java:

```c
(*env)->CallVoidMethod(env, callback, runMethod);
if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* Callback đã ném Java exception.
       Không gọi JNI API tùy ý; cleanup an toàn và return. */
    return;
}
```

JNI callback có thể ném `IllegalStateException`, `IOException` hoặc lỗi khác. Nếu không có yêu cầu chuyển đổi rõ, **giữ nguyên exception gốc**. Không nên gọi tiếp `FindClass` và `ThrowNew` khi exception cũ còn pending để “bọc” nó một cách tùy tiện.

### 4.3. JNI functions nào còn được dùng khi exception pending?

JNI specification cho phép **một tập giới hạn** các thao tác trong khi exception chưa được xóa, ví dụ:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- Các hàm `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`, `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame` và `DetachCurrentThread` (khi phù hợp với lifecycle).

Phần lớn các thao tác JNI còn lại, như `FindClass`, `GetMethodID`, `NewObject` hoặc gọi phương thức Java, **không được gọi khi exception vẫn pending**. Nếu cần xử lý/đổi ngoại lệ, trước hết phải lấy thông tin cần thiết và `ExceptionClear` đúng lúc, rồi mới dùng các JNI functions khác.

Code C/C++ thuần để `free` bộ nhớ, đóng một file descriptor hoặc giải phóng tài nguyên riêng vẫn có thể chạy nếu bản thân thao tác an toàn. Tuy nhiên, muốn gọi thêm JNI để cleanup thì phải chọn đúng loại hàm được phép.

**Nguyên tắc mặc định:** thấy exception pending → cleanup tối thiểu bằng API cho phép → return, để Java bắt. Chỉ clear khi có lý do cụ thể, code xử lý đầy đủ và giữ nguyên nghĩa lỗi.

## 5. Ví dụ chạy được: `ThrowNew`, `Throw` và lỗi từ callback Java

Ví dụ độc lập sau cho thấy ba trường hợp trong cùng một thư viện JNI:

1. Native kiểm tra giá trị đầu vào, ném `IllegalArgumentException` hoặc `ArithmeticException` mới bằng `ThrowNew`.
2. Java truyền một `IllegalStateException` **đã có cause** xuống native; `Throw` giữ nguyên cùng object và cause.
3. Native gọi `Runnable.run()`; callback ném lỗi Java, nên native phát hiện pending exception, cleanup và return mà **không ném ngoại lệ thứ hai**.

Môi trường: **JDK 17+**, compiler C hỗ trợ C11, **Linux** với GCC/Clang và JNI headers. Các đoạn code được tách theo tên tệp để có thể tạo một thư mục dự án và chạy.

### 5.1. Cấu trúc dự án

```text
jni-errors/
├── src/
│   └── demo/
│       └── NativeErrors.java
├── native/
│   └── native_errors.c
└── build/                  # Được tạo khi biên dịch
```

### 5.2. Tệp `src/demo/NativeErrors.java`

```java
package demo;

import java.io.IOException;

public final class NativeErrors {
    static {
        System.loadLibrary("native_errors");
    }

    private NativeErrors() {
    }

    private static native int squareChecked(int value);

    private static native void rethrow(Throwable existing);

    private static native void invokeCallback(Runnable callback);

    public static void main(String[] args) {
        System.out.println("square(6): " + squareChecked(6));

        try {
            squareChecked(-2);
        } catch (IllegalArgumentException error) {
            System.out.println("invalid: " + error.getMessage());
        }

        try {
            squareChecked(50_000);
        } catch (ArithmeticException error) {
            System.out.println("overflow: " + error.getMessage());
        }

        IllegalStateException original = new IllegalStateException(
                "operation failed", new IOException("disk unavailable"));

        try {
            rethrow(original);
        } catch (IllegalStateException error) {
            System.out.println("same instance: " + (error == original));
            System.out.println(
                    "cause: " + error.getCause().getMessage());
        }

        try {
            invokeCallback(() -> {
                throw new IllegalStateException("callback failed");
            });
        } catch (IllegalStateException error) {
            System.out.println("callback: " + error.getMessage());
        }
    }
}
```

Trong chương trình, native method `squareChecked` trả `int` trong đường thành công. Khi có exception pending, native implementation sẽ `return 0` như giá trị kỹ thuật để đáp ứng chữ ký C; Java nhận ngoại lệ và **không xem 0 như một kết quả phép tính thành công**.

### 5.3. Tệp `native/native_errors.c`

```c
#include <stdio.h>
#include "demo_NativeErrors.h"

/* Fragment trợ giúp trong cùng tệp C:
   className dùng JNI binary name, ví dụ java/lang/...
   Chỉ gọi khi không có Java exception pending. */
static jint raise_new(
        JNIEnv *env,
        const char *className,
        const char *message) {

    jclass exceptionType = (*env)->FindClass(env, className);
    if (exceptionType == NULL) {
        /* Không cố ném thêm lỗi nếu FindClass thất bại;
           giữ nguyên lỗi mà JVM đã báo nếu có. */
        return JNI_ERR;
    }

    jint rc = (*env)->ThrowNew(env, exceptionType, message);

    /* Cho phép DeleteLocalRef kể cả khi exception pending. */
    (*env)->DeleteLocalRef(env, exceptionType);
    return rc;
}

JNIEXPORT jint JNICALL Java_demo_NativeErrors_squareChecked(
        JNIEnv *env, jclass ignored, jint value) {
    (void)ignored;

    if (value < 0) {
        char message[96];
        (void)snprintf(message, sizeof(message),
                "value must be >= 0; received %d", (int)value);

        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        message);
        return 0;
    }

    /* 46340^2 vẫn nằm trong miền signed Java int.
       46341^2 vượt Integer.MAX_VALUE. */
    if (value > 46340) {
        char message[96];
        (void)snprintf(message, sizeof(message),
                "value must be <= 46340; received %d", (int)value);

        (void)raise_new(env, "java/lang/ArithmeticException",
                        message);
        return 0;
    }

    return value * value;
}

JNIEXPORT void JNICALL Java_demo_NativeErrors_rethrow(
        JNIEnv *env, jclass ignored, jthrowable existing) {
    (void)ignored;

    if (existing == NULL) {
        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        "existing exception must not be null");
        return;
    }

    /* Dùng lại đúng Throwable đã được Java truyền vào. */
    (void)(*env)->Throw(env, existing);
    return;
}

JNIEXPORT void JNICALL Java_demo_NativeErrors_invokeCallback(
        JNIEnv *env, jclass ignored, jobject callback) {
    (void)ignored;

    if (callback == NULL) {
        (void)raise_new(env, "java/lang/IllegalArgumentException",
                        "callback must not be null");
        return;
    }

    jclass callbackClass = (*env)->GetObjectClass(env, callback);
    if (callbackClass == NULL) {
        /* JNI operation không thành công: giữ nguyên lỗi. */
        return;
    }

    jmethodID run = (*env)->GetMethodID(
            env, callbackClass, "run", "()V");
    if (run == NULL) {
        (*env)->DeleteLocalRef(env, callbackClass);
        return;
    }

    (*env)->CallVoidMethod(env, callback, run);

    if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
        /* Java Runnable.run() đã ném lỗi.
           Không gọi ThrowNew để che lỗi gốc. */
        (*env)->DeleteLocalRef(env, callbackClass);
        return;
    }

    (*env)->DeleteLocalRef(env, callbackClass);
}
```

Giải thích các điểm đáng chú ý:

- `FindClass` dùng tên JNI như `java/lang/IllegalArgumentException`, không dùng dấu chấm hay ký pháp `Ljava/...;`.
- `raise_new` tạo local `jclass`, gọi `ThrowNew`, rồi xóa local ref bằng thao tác **được phép trong khi exception pending**. Nó trả `0` nếu `ThrowNew` thành công, số âm khi có lỗi; helper không tự phát sinh một ngoại lệ phụ để thay thế lỗi gốc nếu `FindClass` thất bại.
- `squareChecked` kiểm tra range **trước khi nhân**, tránh signed integer overflow không xác định trong C và phù hợp Java `int`.
- `rethrow` nhận `jthrowable` hợp lệ nên `Throw` dùng đúng exception instance, bao gồm cause `IOException` do Java gắn lúc tạo object.
- `invokeCallback` kiểm tra `GetObjectClass` và `GetMethodID`. `CallVoidMethod` có thể khiến exception pending mà **không trả mã lỗi phân biệt**; `ExceptionCheck` xác nhận trước khi native cleanup và return.
- Đoạn mẫu chỉ minh họa đường thành công/ngoại lệ thông thường. Trong tình huống tài nguyên cực hạn, `ThrowNew` hoặc class lookup vẫn có thể thất bại (mã trả về âm hoặc tình trạng lỗi phù hợp); một thư viện production cần có chính sách xử lý lỗi nghiêm trọng, không giả định mọi `ThrowNew` đều tạo được object.
- Tất cả thông điệp C ở đây là ASCII, cũng hợp lệ trong Modified UTF-8. Cách này giúp stdout dễ dự đoán giữa các hệ.

### 5.4. Biên dịch và chạy trên Linux

Đứng trong thư mục `jni-errors`; biến `JAVA_HOME` trỏ đến **JDK** có `include/jni.h`:

```bash
mkdir -p build/classes build/include

javac -h build/include -d build/classes \
  src/demo/NativeErrors.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/native_errors.c -o libnative_errors.so

java -Djava.library.path=. \
  -cp build/classes demo.NativeErrors
```

`javac -h` tạo header `build/include/demo_NativeErrors.h` theo chữ ký Java. Việc sử dụng header sinh tự động giảm nguy cơ sai symbol JNI, tham số ẩn `JNIEnv *`/`jclass` hoặc tên hàm. `cc` tạo bản shared library Linux và `System.loadLibrary("native_errors")` tìm `libnative_errors.so` trong `java.library.path`.

**Stdout dự kiến:**

```text
square(6): 36
invalid: value must be >= 0; received -2
overflow: value must be <= 46340; received 50000
same instance: true
cause: disk unavailable
callback: callback failed
```

Nếu chạy trên các phiên bản JDK có kiểm soát native access, có thể cần cấp quyền theo cơ chế của JDK đó; với ứng dụng classpath trên JDK 24+, ví dụ thường được chạy với `--enable-native-access=ALL-UNNAMED` để tránh cảnh báo hoặc lỗi do chính sách native access. Điều này **không ảnh hưởng** ngữ nghĩa `Throw`/`ThrowNew`. Windows/macOS phải dùng định dạng thư viện, tên đuôi, include JNI và lệnh build thích hợp với OS/CPU đó.

### 5.5. Tại sao `same instance: true` quan trọng?

Trong Java, `original` là một `IllegalStateException` cụ thể với cause. Khi native dùng `Throw(env, original)`, phía Java bắt được **đúng cùng instance**; `error == original` là `true`. Vì vậy message `"operation failed"` và cause `IOException("disk unavailable")` vẫn gắn với object. Nếu thay bằng `ThrowNew` cùng exception class và message giống nhau, đó sẽ là **đối tượng khác**, không giữ cause trừ khi lập trình viên dựng lại.

## 6. Cần đưa cause hoặc message Unicode phức tạp thì làm thế nào?

`ThrowNew` không nhận tham số `jthrowable cause`. Nếu muốn cung cấp cause, suppressed exceptions hoặc fields tùy biến, thường làm theo quy trình:

1. Xác định Java exception class phù hợp (có constructor mong muốn).
2. Tạo `jstring` message bằng phương thức encoding đúng; lấy constructor bằng `GetMethodID`.
3. Tạo `Throwable` bằng `NewObject`, với tham số `String` và có thể cả `Throwable cause`.
4. Gọi `Throw` với object mới.
5. Xóa các **local references** hợp lệ sau khi ném; không xóa strong ref thuộc về Java ngoài phạm vi của mình.

**Ví dụ minh họa JNI C** để tạo `IllegalStateException(message, cause)` khi **không có exception pending trước khi bắt đầu**; `cause` đã là `jthrowable` hợp lệ hoặc `NULL`:

```c
/* Fragment, giả định env hợp lệ và không có pending exception. */
jclass cls = (*env)->FindClass(
        env, "java/lang/IllegalStateException");
if (cls == NULL) {
    return; /* Giữ nguyên exception do FindClass nếu có. */
}

jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>",
        "(Ljava/lang/String;Ljava/lang/Throwable;)V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jstring message = (*env)->NewStringUTF(
        env, "native operation failed");
if (message == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;
}

jthrowable wrapped = (jthrowable)(*env)->NewObject(
        env, cls, ctor, message, cause);
if (wrapped != NULL) {
    (void)(*env)->Throw(env, wrapped);
    (*env)->DeleteLocalRef(env, wrapped);
}

(*env)->DeleteLocalRef(env, message);
(*env)->DeleteLocalRef(env, cls);
return;
```

Đây là **fragment bên trong native method trả `void`**, không phải chương trình C độc lập. Các bước `DeleteLocalRef` còn hợp lệ khi exception pending, ví dụ nếu constructor `NewObject` tự ném lỗi. `NewObject` có thể trả `NULL` khi cấp phát thất bại; không gọi `Throw` với `NULL`. Nếu cần tạo lỗi với message chứa ký tự Unicode không biểu diễn đơn giản bằng chuỗi ASCII, `NewStringUTF` cũng yêu cầu Modified UTF-8; đừng đưa byte UTF-8 bất kỳ mà chưa xác nhận encoding.

### 6.1. Modified UTF-8 không hoàn toàn giống UTF-8 thông thường

JNI `ThrowNew` và `NewStringUTF` sử dụng **Modified UTF-8** cho các chuỗi ký tự C. Cách biểu diễn `U+0000` và ký tự Unicode ngoài BMP (thông qua surrogate pairs) khác UTF-8 tiêu chuẩn. Do đó:

- Các thông điệp thuần ASCII trong ví dụ an toàn và tương thích.
- Chuỗi byte đọc từ file hoặc API bên ngoài không mặc nhiên là chuỗi hợp lệ cho `ThrowNew`.
- Nếu cần message có nội dung tiếng Việt, ký tự đặc biệt hoặc dữ liệu do người dùng nhập, nên chuyển đổi encoding đúng, hoặc tạo `jstring` từ dữ liệu UTF-16 hợp lệ bằng `NewString` rồi tạo exception object bằng constructor Java và `Throw`.
- Đừng nối nội dung C tùy ý vượt giới hạn buffer; dùng `snprintf` đúng kích thước và xem xét độ dài cần thiết. Khi rút ngắn thông điệp, đảm bảo ranh giới encoding không bị cắt dở.

Điểm quan trọng là **thông điệp giúp chẩn đoán**, không phải kênh truyền toàn bộ dữ liệu lỗi. Thông tin phức tạp nên nằm trong exception class/fields/cause được định nghĩa ở API Java.

## 7. Giữ hay chuyển đổi exception đang pending từ JNI call trước đó?

### 7.1. Mặc định: giữ nguyên exception

Các hàm như `FindClass`, `NewObject`, `GetMethodID`, `CallVoidMethod` có thể gây exception pending. Trong đa số trường hợp, nếu không có yêu cầu chuyển đổi rõ ràng:

```c
jobject result = (*env)->CallObjectMethod(
        env, service, methodID);

if ((*env)->ExceptionCheck(env) == JNI_TRUE) {
    /* Không gọi ThrowNew thêm; giữ nguyên exception. */
    return NULL; /* Ví dụ native method trả jobject. */
}

/* result chỉ được xử lý như thành công khi không có lỗi. */
return result;
```

Đây là fragment giả định `service` và `methodID` hợp lệ. Nếu đã giữ các JNI references/resources trước đó, phải giải phóng bằng các thao tác cho phép khi pending trước khi return.

### 7.2. Khi buộc phải wrap: capture → clear → construct → throw

Nếu API public muốn chuyển `IOException` từ callback thành một `NativeOperationException` có cause, không thể cứ gọi `FindClass`/`NewObject` khi lỗi cũ còn pending. Trình tự phải là:

```text
1. ExceptionOccurred(env) → lấy local reference tới Throwable cũ.
2. ExceptionClear(env) → chủ động clear, vì sẽ làm JNI operations mới.
3. FindClass/GetMethodID/NewObject → tạo wrapper chứa cause cũ.
4. Throw(env, wrapper) → pending exception mới.
5. DeleteLocalRef(env, refs) và return.
```

Trong bước (3), nếu lookup/constructor thất bại và ném lỗi mới, phải cleanup an toàn và để lỗi đó đi lên; tránh tự động xóa rồi tạo một vòng lặp ngoại lệ nữa. Nếu định giữ cause cũ xuyên qua các thao tác, bảo đảm local ref còn hợp lệ. Nếu đã `ExceptionClear` rồi **quên `Throw`**, lỗi gốc sẽ bị nuốt và phía Java có thể tưởng thao tác thành công.

Một chiến lược khác thường đơn giản hơn: **để lỗi đi lên Java và wrap bằng mã Java** trong method wrapper, nơi có đầy đủ cú pháp `try/catch`, constructor và cơ chế logging. JNI có thể chỉ cần phát hiện lỗi và return.

### 7.3. `ExceptionDescribe` không phải logging vô hại

`ExceptionDescribe` in stack trace ra kênh lỗi của JVM và **xóa pending exception**. Nếu viết:

```c
if ((*env)->ExceptionCheck(env)) {
    (*env)->ExceptionDescribe(env); /* Side effect: clear. */
    return;
}
```

phía Java có thể **không nhận ngoại lệ**, mặc dù native code vừa in stack trace. Muốn chẩn đoán trong production, ưu tiên để exception lên Java logger; nếu dùng `ExceptionDescribe` khi debug, phải hiểu và xử lý rõ việc nó clear exception. Không che mất lỗi chỉ để thêm một dòng log.

## 8. Cleanup, tài nguyên và vấn đề hiệu năng

Native code có thể nắm giữ buffer từ `malloc`, con trỏ chuỗi qua `GetStringUTFChars`, local refs hoặc lock. Khi lỗi xảy ra, cần giải phóng tài nguyên theo đúng API:

```c
/* Fragment: giả định chars đã nhận từ GetStringUTFChars. */
const char *chars = (*env)->GetStringUTFChars(env, input, NULL);
if (chars == NULL) {
    return; /* Có thể có exception pending. */
}

/* ... thao tác native có thể xác định lỗi ... */

(*env)->ReleaseStringUTFChars(env, input, chars);
```

`ReleaseStringUTFChars` nằm trong nhóm JNI functions an toàn để gọi khi exception pending. `DeleteLocalRef` cũng vậy. Ngược lại, không gọi một `NewObject` mới chỉ để log/cleanup trong lúc pending, nếu chưa clear theo chiến lược hợp lệ.

Đối với native memory:

```c
/* Mô hình C chung: cleanup bằng label, phù hợp với đường lỗi. */
void *buffer = allocate_buffer_somehow();
if (buffer == NULL) {
    /* Chọn Java exception phù hợp trước khi return,
       nếu các JNI calls trước chưa để lại pending exception. */
    return;
}

/* ... xử lý ... */
free_buffer_somehow(buffer);
```

Đoạn trên là **pseudo-fragment có hàm cấp phát/giải phóng do ứng dụng định nghĩa**, không phải chương trình runnable. Không bao giờ dùng `free` để giải phóng JNI object reference; dùng `DeleteLocalRef`/`DeleteGlobalRef` đúng loại. Nếu làm việc trong JNI critical region hoặc giữ monitor, phải tuân thủ quy tắc release/exit riêng ngay cả khi có lỗi.

### 8.1. ThrowNew có miễn phí không?

Không. Nó cần truy cập class và tạo exception object/stack trace theo runtime. Nếu mỗi phần tử bình thường trong một vòng lặp ném exception như cách điều khiển luồng, chi phí thường cao hơn một mã trả về hoặc xử lý Java bình thường. Hãy dùng exception khi **thật sự có lỗi theo hợp đồng**, không dùng để báo từng bước hợp lệ của một hot loop. Đồng thời đừng hy sinh khả năng chẩn đoán bằng cách luôn ném `RuntimeException("failed")`.

Nếu call native có thể thất bại rất thường xuyên và thuộc nhánh nghiệp vụ bình thường (ví dụ thử tìm phần tử không có), cân nhắc API trả `Optional`/status ở Java hoặc một mã kết quả được định nghĩa rõ, thay vì bắt ngoại lệ liên tục. Ranh giới giữa lỗi và kết quả hợp lệ phải được nêu trong hợp đồng API.

## 9. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Gọi `ThrowNew` rồi tiếp tục dùng input không hợp lệ | Mã native vẫn chạy, có thể đọc sai bộ nhớ | Cleanup hợp lệ và return ngay |
| Gọi `FindClass` với `java.lang.IllegalStateException` | Tên class sai định dạng JNI | Dùng `java/lang/IllegalStateException` |
| Dùng `ThrowNew` để “ném lại” một Throwable có cause | Tạo instance mới và mất dữ liệu exception cũ | `Throw(env, existing)` |
| Truyền `NULL` làm `jthrowable` cho `Throw` | Vi phạm tham số JNI, nguy cơ lỗi nghiêm trọng | Kiểm tra null trước khi gọi |
| `FindClass` đã thất bại nhưng vẫn gọi `ThrowNew` với class null | Ghi đè/chồng lỗi, có thể crash | Giữ pending exception và return |
| Sau `CallVoidMethod` không kiểm tra pending exception | Lỡ lỗi callback, gọi JNI tiếp sai | `ExceptionCheck` trước các bước JNI tiếp |
| Gọi `ExceptionClear` để “bỏ cảnh báo” | Nuốt lỗi mà Java cần thấy | Chỉ clear khi sẽ thực sự handle/wrap |
| Gọi `ExceptionDescribe` rồi tưởng Java vẫn sẽ catch lỗi cũ | `ExceptionDescribe` làm clear pending | Biết rõ side effect; để Java log/catch |
| Dùng byte UTF-8 bất kỳ làm `ThrowNew` message | Có thể sai Modified UTF-8 | Chuyển đổi encoding hoặc tạo `jstring` đúng cách |
| Dùng `ThrowNew` mà không kiểm tra lỗi cấp phát nghiêm trọng | Nếu thao tác ném không thành công, chương trình có thể trả sentinel | Thiết kế đường lỗi/sự cố phù hợp; không tự giả định luôn thành công |
| Giữ con trỏ native hoặc local JNI ref sau khi return | Leak hoặc use-after-release | Dọn tài nguyên bằng đúng JNI/C API |
| Để C++ exception vượt qua JNI frame | Không phải cách ném Java exception được bảo đảm | Catch C++ ở biên native, map sang Java Throwable |

### Phân biệt ngoại lệ từ mã C/C++ và Java

- `Throw`/`ThrowNew` tạo **Java pending exception**. Không dùng `try/catch` C++ để chờ nó tự được ném ở phía C++.
- C++ `throw std::runtime_error(...)` là **C++ exception**, không tự trở thành `java.lang.RuntimeException`. Trong JNI C++ wrapper, catch ở biên, chuyển thông tin lỗi phù hợp sang JNI `ThrowNew` hoặc `Throw`, cleanup và return. Tránh để C++ exception vượt qua runtime frame không bảo đảm tương thích.
- Gọi `FatalError` không tương đương ném Java exception: nó là thao tác lỗi nghiêm trọng mà VM không dự kiến phục hồi; không dùng để xử lý lỗi tham số thông thường.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Native phát hiện `length = -5`. Dùng `ThrowNew` hay `Throw`?  
**Đáp án:** Nếu chưa có exception object, chọn `ThrowNew` với `IllegalArgumentException`, message dạng `"length must be >= 0; received -5"`, sau đó cleanup và return.

**Câu 2.** Native đã nhận `jthrowable existing` từ Java, đối tượng có cause và suppressed exceptions. Cách ném lại mà giữ nguyên cùng instance?  
**Đáp án:** `(*env)->Throw(env, existing)` (C) hoặc `env->Throw(existing)` (C++), với reference hợp lệ và non-null.

**Câu 3.** `CallVoidMethod` gọi callback Java đã ném ngoại lệ. Có nên lập tức `FindClass` và `ThrowNew` để tạo `RuntimeException("callback failed")`?  
**Đáp án:** Thông thường không. Giữ exception đang pending, dọn resources bằng API được phép rồi return. Nếu thực sự phải wrap thì capture/clear/construct/throw theo đúng trình tự.

**Câu 4.** `ThrowNew` trả `0` thì native method đã tự return chưa?  
**Đáp án:** Chưa. `0` là trạng thái thành công của hàm JNI; code C/C++ phải chủ động `return`.

**Câu 5.** Sau `ThrowNew`, có được `DeleteLocalRef` và `ReleaseStringUTFChars` không?  
**Đáp án:** Có, cả hai nằm trong nhóm JNI cleanup cho phép khi exception pending. Không gọi tùy ý `FindClass` hoặc `NewObject` khi chưa clear.

**Câu 6.** Lệnh `ExceptionDescribe` chỉ in log rồi giữ pending exception?  
**Đáp án:** Không. JNI specification quy định nó in chi tiết và **xóa exception pending**.

**Câu 7.** Muốn ném exception mới với một `Throwable cause` sẵn có, chỉ truyền message vào `ThrowNew` là đủ?  
**Đáp án:** Không. Phải tạo exception object có cause bằng constructor/API thích hợp rồi `Throw`; hoặc để Java wrapper tạo/wrap exception.

**Câu 8.** Có thể chuyển mọi mã lỗi native thành `IllegalStateException("error")` được không?  
**Đáp án:** Về mặt thao tác JNI có thể tạo class ngoại lệ hợp lệ, nhưng API chất lượng nên chọn class tương ứng lỗi và message đủ ngữ cảnh, tránh bỏ mất cause/error code có ích.

## 11. Ghi nhớ

- `ThrowNew`: **tạo mới** Java exception bằng class + Modified UTF-8 message; `Throw`: **ném object đã tồn tại**.
- Cả hai thiết lập **pending exception** trên thread hiện tại; **không tự thoát** khỏi native method. Cleanup an toàn rồi `return`.
- Khi một JNI operation hoặc Java callback đã tạo pending exception, **không tự ý gọi thêm JNI functions**. `ExceptionCheck` và các hàm release/delete được cho phép giúp xử lý/cleanup; `ExceptionClear` chỉ dùng khi có chiến lược rõ ràng.
- Message nên mô tả **tham số/thao tác, điều kiện mong đợi và giá trị thực tế**, không chứa bí mật; exception class là phần ổn định của hợp đồng lỗi.
- `ThrowNew` không có tham số cause. Muốn giữ cause hoặc instance, dùng `Throw` với `Throwable` phù hợp.
- `ExceptionDescribe` in lỗi và **clear** pending exception; đừng vô ý nuốt lỗi.
- C++ exception, native errno và Java exception là các cơ chế khác nhau; chuyển đổi rõ tại biên JNI.

### Tài liệu chính thức

- [Oracle JNI Functions — Throw, ThrowNew, ExceptionCheck, ExceptionOccurred, ExceptionClear (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#exceptions): chữ ký, tham số, mã trả về và các API ngoại lệ.
- [Oracle JNI Design Overview — Java Exceptions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#java-exceptions): propagation, pending exceptions và các JNI functions được phép gọi khi exception còn pending.
- [Oracle JNI Types and Data Structures — Modified UTF-8 (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html#modified-utf-8-strings): quy tắc encoding cho chuỗi JNI.
- [Java SE 17 API — Throwable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html): message, cause, suppressed exceptions và vòng đời exception object.
