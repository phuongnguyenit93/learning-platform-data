# Ngoại lệ JNI: Ngăn ngoại lệ C++ thoát qua ranh giới JNI và chuyển thành lỗi Java

## 1. Vấn đề: hai cơ chế ngoại lệ không tự tương thích

Trong Java Native Interface (JNI), Java gọi phương thức `native` được cài đặt ở C/C++, hoặc C++ gọi lại phương thức Java. Hai hệ thống exception có ngữ nghĩa khác nhau:

- **C++ exception:** câu lệnh `throw` ném một đối tượng C++ như `std::invalid_argument`, `std::runtime_error`, `std::bad_alloc`. C++ runtime đi qua các stack frame C++ bằng **stack unwinding** để tìm `catch`, đồng thời gọi destructor của các đối tượng stack.
- **Java exception:** JVM quản lý `Throwable`, ví dụ `IllegalArgumentException`, `ArithmeticException`, `OutOfMemoryError`. JNI có trạng thái **pending Java exception** trên luồng hiện tại. `ThrowNew` hoặc `Throw` đặt trạng thái này; khi native method trả về, JVM chuyển lỗi tới Java caller.

Một C++ exception **không được phép thoát không kiểm soát qua ranh giới JNI** vào JVM. Java runtime không có nghĩa vụ hiểu exception ABI của C++ và không có bảo đảm unwind an toàn qua các Java frames. Hậu quả có thể là `std::terminate`, crash hay hành vi không xác định. Vì thế, entry point JNI phải **bắt C++ exception, chuyển thành Java exception qua JNI, rồi return qua điểm vào/ra JNI theo quy ước bình thường**.

```text
Java gọi native method
          │
          ▼
   JNI entry point C++
          │
     try { work(); }
          │
     ┌────┴─────────┐
     │              │
   OK, return    C++ throw
                    │
                catch(...) trong C++
                    │
                chọn Java exception class
                    │
             env->ThrowNew(...)
                    │
              Java exception pending
                    │
             return qua JNI
                    │
             JVM ném Java Throwable
                    │
              Java try/catch
```

**Chiều ngược lại cũng quan trọng:** nếu C++ gọi Java bằng `CallObjectMethod`/`CallVoidMethod` và Java method ném `Throwable`, **C++ `catch (...)` không tự bắt được nó**. Đó là pending Java exception và phải được kiểm tra bằng `ExceptionCheck`.

## 2. Quy trình an toàn ở JNI boundary

1. **Bao kín công việc C++ có thể throw trong `try`** ở mỗi entry point JNI. Không để một bước cấp phát, khởi tạo object, gọi thư viện hay xử lý dữ liệu có thể ném nằm ngoài vùng bảo vệ.
2. **Bắt exception có ý nghĩa trước:** `std::invalid_argument`, `std::overflow_error`, `std::bad_alloc`… Sau đó bắt `std::exception`, và đặt **`catch (...)` cuối** để chặn cả ngoại lệ không kế thừa `std::exception`.
3. **Ánh xạ C++ exception sang Java class đúng hợp đồng API.** Ví dụ lỗi input → `IllegalArgumentException`, toán học → `ArithmeticException`, cấp phát → `OutOfMemoryError`. Đây là lựa chọn thiết kế, **không phải cơ chế tự động của JNI**.
4. **Không ghi đè pending Java exception** đã tồn tại. Chỉ tra class exception qua `FindClass` và tạo exception mới qua `ThrowNew` khi trạng thái cho phép.
5. **Dọn tài nguyên C++ bằng RAII**, dọn JNI references theo loại/vòng đời của chúng, rồi **return**. `ThrowNew` không tự thoát C++ function.
6. **Có chính sách khi chính việc tạo Java exception thất bại.** Không để native method âm thầm trả giá trị thành công khi cả lỗi C++ vẫn chưa được diễn đạt về Java.

Ví dụ **sai**:

```cpp
// SAI: C++ exception có thể vượt ra khỏi JNI entry point.
JNIEXPORT jint JNICALL Java_demo_jni_Bad_execute(JNIEnv*, jclass) {
    throw std::runtime_error("broken");
}

// SAI: ThrowNew chỉ đặt Java exception pending, không unwind C++.
env->ThrowNew(exceptionClass, "broken");
doMoreNativeWork(); // C++ vẫn chạy; có thể vi phạm trạng thái JNI.
```

Các đoạn trên **chỉ minh họa lỗi**, không phải chương trình độc lập. Phần 5 có chương trình đúng và đã biên dịch/chạy.

## 3. Các JNI API để báo và kiểm tra Java exception

Trong C++ với `JNIEnv* env`, gọi `env->Function(...)`; C thuần dùng dạng `(*env)->Function(env, ...)`.

| API | Công dụng | Lưu ý quan trọng |
| --- | --- | --- |
| `env->ThrowNew(jclass, const char*)` | Tạo một Java exception mới và đặt pending exception | Message dùng **modified UTF-8**; trả `JNI_OK` nếu thành công, giá trị âm nếu thất bại |
| `env->Throw(jthrowable)` | Đặt Java `Throwable` đã có làm pending | Phù hợp khi cần giữ đúng instance/cause |
| `env->ExceptionCheck()` | Trả `JNI_TRUE` khi luồng đang có pending Java exception | Không tạo thêm local ref |
| `env->ExceptionOccurred()` | Trả local reference đến pending exception hoặc `NULL` | Local ref phải được quản lý đúng |
| `env->ExceptionClear()` | Xóa pending exception | Chỉ làm khi **chủ động xử lý/thay thế** lỗi |
| `env->ExceptionDescribe()` | In exception và stack trace ra kênh chẩn đoán | **Có tác dụng phụ là xóa pending exception** |
| `env->DeleteLocalRef(ref)` | Dọn local JNI reference | Được phép khi Java exception đang pending |

Một mẫu đơn giản:

```cpp
// Ví dụ cục bộ, chưa bao gồm mọi nhánh thất bại.
if (!env->ExceptionCheck()) {
    jclass type = env->FindClass("java/lang/IllegalArgumentException");
    if (type != nullptr) {
        env->ThrowNew(type, "invalid native argument");
        env->DeleteLocalRef(type);
    }
}
return; // Nếu đây là JNI function trả void.
```

**`FindClass` có thể thất bại và tạo pending exception.** Không được gọi `ThrowNew` với `jclass == nullptr`. Nếu Java exception đã pending từ trước, không nên gọi `FindClass`/`ThrowNew` tùy tiện để thay nó.

Trong C++, `ThrowNew` **không tương đương `throw`**. Nó không tự động thực hiện C++ stack unwinding, không phá khỏi khối lệnh, và có thể để C++ tiếp tục chạy. Sau `ThrowNew` thành công, hãy cleanup bằng những thao tác hợp lệ và return.

## 4. Ánh xạ exception C++ sang loại Java nào?

| Trường hợp C++ | Java Throwable thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| `std::invalid_argument` | `IllegalArgumentException` | Java caller truyền tham số sai |
| `std::out_of_range` | `IndexOutOfBoundsException` nếu thực sự là lỗi chỉ số | Tùy hợp đồng API |
| `std::overflow_error` | `ArithmeticException` | Phép toán không biểu diễn được |
| `std::bad_alloc` | `OutOfMemoryError` | Không đủ native memory |
| `std::runtime_error` do trạng thái subsystem sai | `IllegalStateException` | Lỗi trạng thái chạy, không phải input |
| Một kiểu C++ exception không kế thừa `std::exception` | `RuntimeException` dự phòng, hoặc exception Java riêng | Được chặn bằng `catch (...)` |
| Java callback đã có pending exception | **Giữ nguyên lỗi Java** | Không ánh xạ lại trừ khi chính sách yêu cầu |

Bảng là **ví dụ chính sách**, không phải mapping mặc định của JNI. Thư viện production nên có hợp đồng rõ những Java exception caller có thể dựa vào và tránh lộ secrets/connection string/path nội bộ trong message.

**Vấn đề encoding:** `std::exception::what()` trả `const char*` nhưng không bảo đảm chuỗi đã mã hóa dạng **modified UTF-8** mà `ThrowNew` dùng. Bài chạy chỉ dùng message ASCII, nên an toàn. Với message Unicode thực tế cần chuyển mã/escape hoặc tạo Java `String` hợp lệ rồi dựng Java Throwable theo API phù hợp.

## 5. Ví dụ chạy được: Java 17+ và C++17

Ví dụ gồm hai phương thức `native`: `divide` thực hiện phép chia có kiểm tra miền; `failNative` mô phỏng lỗi C++ theo hai nhóm. Demo kiểm tra bốn nhánh chuyển lỗi: input sai, overflow, runtime error và exception không thuộc `std::exception`.

### 5.1. Cấu trúc file

```text
jni-cpp-exceptions/
├── src/
│   └── demo/
│       └── jni/
│           └── ExceptionBridgeDemo.java
├── native/
│   └── cppbridge.cpp
└── build/                        # được tạo khi biên dịch
    ├── classes/
    ├── headers/
    └── lib/
```

### 5.2. `src/demo/jni/ExceptionBridgeDemo.java`

```java
package demo.jni;

public final class ExceptionBridgeDemo {
    static { System.loadLibrary("cppbridge"); }

    private ExceptionBridgeDemo() {}

    private static native int divide(int numerator, int denominator);
    private static native void failNative(boolean unknown);

    public static void main(String[] args) {
        System.out.println("OK: " + divide(10, 2));

        try {
            divide(7, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Zero: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            divide(Integer.MIN_VALUE, -1);
        } catch (ArithmeticException e) {
            System.out.println("Overflow: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            failNative(false);
        } catch (IllegalStateException e) {
            System.out.println("Standard: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }

        try {
            failNative(true);
        } catch (RuntimeException e) {
            System.out.println("Unknown: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }
}
```

Java chỉ biết các Java `Throwable` được native code chuyển đổi. Các phương thức `static native` có tham số JNI ngầm thứ hai là `jclass`, không phải `jobject`.

### 5.3. Sinh JNI header và Java bytecode

Đứng tại thư mục `jni-cpp-exceptions` trên Linux:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/ExceptionBridgeDemo.java
```

Header sinh ra là `build/headers/demo_jni_ExceptionBridgeDemo.h`. Phần prototype tương đương:

```cpp
/* Signature: (II)I */
JNIEXPORT jint JNICALL Java_demo_jni_ExceptionBridgeDemo_divide
  (JNIEnv *, jclass, jint, jint);

/* Signature: (Z)V */
JNIEXPORT void JNICALL Java_demo_jni_ExceptionBridgeDemo_failNative
  (JNIEnv *, jclass, jboolean);
```

Đây là **đoạn trích minh họa**, không thay cho toàn bộ file `.h` sinh từ JDK. Mã C++ bên dưới include đúng header này, giữ prototype và C linkage tương thích.

### 5.4. `native/cppbridge.cpp`

```cpp
#include "demo_jni_ExceptionBridgeDemo.h"
#include <exception>
#include <limits>
#include <new>
#include <stdexcept>

namespace {
void raiseJava(JNIEnv* env, const char* className,
               const char* message) noexcept {
    if (env->ExceptionCheck()) {
        return; // Existing Java exception has priority.
    }

    jclass exceptionClass = env->FindClass(className);
    if (exceptionClass == nullptr) {
        // FindClass should have raised a Java exception.
        if (!env->ExceptionCheck()) {
            env->FatalError("Cannot resolve Java exception class");
        }
        return;
    }

    const jint result = env->ThrowNew(exceptionClass, message);
    env->DeleteLocalRef(exceptionClass);

    if (result != JNI_OK && !env->ExceptionCheck()) {
        // Unable even to communicate failure back to Java.
        env->FatalError("Cannot report native exception to Java");
    }
}

// Invoked ONLY from a C++ catch handler with an active exception.
void translateCppException(JNIEnv* env) noexcept {
    try {
        throw;
    } catch (const std::invalid_argument& e) {
        raiseJava(env, "java/lang/IllegalArgumentException", e.what());
    } catch (const std::overflow_error& e) {
        raiseJava(env, "java/lang/ArithmeticException", e.what());
    } catch (const std::bad_alloc&) {
        raiseJava(env, "java/lang/OutOfMemoryError", "native allocation failed");
    } catch (const std::exception& e) {
        raiseJava(env, "java/lang/IllegalStateException", e.what());
    } catch (...) {
        raiseJava(env, "java/lang/RuntimeException", "unrecognized C++ exception");
    }
}
} // namespace

JNIEXPORT jint JNICALL Java_demo_jni_ExceptionBridgeDemo_divide(
        JNIEnv* env, jclass /* owner */, jint numerator, jint denominator) {
    try {
        if (denominator == 0) {
            throw std::invalid_argument("denominator must not be zero");
        }

        const long long result = static_cast<long long>(numerator)
                               / static_cast<long long>(denominator);

        if (result < std::numeric_limits<jint>::min()
                || result > std::numeric_limits<jint>::max()) {
            throw std::overflow_error("quotient out of jint range");
        }

        return static_cast<jint>(result);
    } catch (...) {
        translateCppException(env);
        return 0; // Placeholder result; pending Java exception takes precedence.
    }
}

JNIEXPORT void JNICALL Java_demo_jni_ExceptionBridgeDemo_failNative(
        JNIEnv* env, jclass /* owner */, jboolean unknown) {
    try {
        if (unknown == JNI_TRUE) {
            throw 42; // Deliberately not a std::exception.
        }
        throw std::runtime_error("native worker failure");
    } catch (...) {
        translateCppException(env);
        return;
    }
}
```

**Tại sao chương trình chặn đúng ngoại lệ C++?**

1. `divide`/`failNative` đều bọc operation có thể throw trong `try` và có `catch (...)`. Không C++ exception nào của những operation này thoát khỏi entry point.
2. `translateCppException` chạy **chỉ trong ngữ cảnh catch handler đang có một exception active**. `throw;` trong helper rethrow chính exception đang xử lý, rồi các nhánh `catch` phân loại. **Không gọi helper ngoài catch**; `throw;` khi không có exception active sẽ khiến `std::terminate`.
3. Bắt các subtype `std::invalid_argument`, `std::overflow_error`, `std::bad_alloc` trước `std::exception`; `catch (...)` cuối xử lý `throw 42`.
4. `raiseJava` kiểm tra Java pending exception. Nếu đã có, nó không gọi thêm `FindClass`/`ThrowNew` và bảo toàn lỗi Java gốc.
5. Khi không pending, helper tìm Java class exception, gọi `ThrowNew`, rồi `DeleteLocalRef`. Dọn local ref **sau khi đặt pending exception** là một thao tác JNI hợp lệ.
6. Nếu thậm chí không thể tìm class hay tạo Java exception **mà không có pending exception**, demo dùng `FatalError` làm **last resort** để không trả về một kết quả thành công giả. `FatalError` dừng JVM, chỉ phù hợp với tình huống không thể phục hồi và phải có chính sách production riêng.
7. Helper `raiseJava`/`translateCppException` là `noexcept`, tránh cấp phát C++ động khi đang chuyển lỗi. JNI entry points dùng **chính chữ ký từ header**: không tự thêm `noexcept` vào định nghĩa JNI khi khác exception specification của khai báo đã include.
8. Tính thương bằng `long long` rồi kiểm tra giới hạn `jint`. Phép `INT_MIN / -1` trực tiếp ở signed 32-bit C++ có thể là **undefined behavior**, không tự động thành `std::overflow_error`; chương trình chủ động tránh nó.
9. `return 0` ở nhánh lỗi của `divide` chỉ là cách kết thúc hàm có kiểu `jint` sau khi đặt Java exception pending. Java nhận Throwable thay vì dùng số `0` như kết quả phép chia.

### 5.5. Biên dịch C++17 và chạy trên Linux

`JAVA_HOME` phải là thư mục JDK tương thích với `javac`, có `include/jni.h` và `include/linux/jni_md.h`. Sau lệnh `javac -h`, chạy:

```bash
g++ -std=c++17 -Wall -Wextra -Werror -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libcppbridge.so \
  native/cppbridge.cpp

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.ExceptionBridgeDemo
```

`g++` liên kết đúng C++ runtime, `-fPIC -shared` tạo shared library `libcppbridge.so`; `System.loadLibrary("cppbridge")` tương ứng tên logic. Tham số `-Ibuild/headers` cho compiler tìm đúng JNI header. `-Xcheck:jni` hỗ trợ phát hiện một số lỗi JNI.

**Stdout chính xác, đã kiểm chứng bằng OpenJDK 21 + G++ 14 trên Linux (build với `-Wall -Wextra -Werror`, chạy với `-Xcheck:jni`):**

```text
OK: 5
Zero: IllegalArgumentException: denominator must not be zero
Overflow: ArithmeticException: quotient out of jint range
Standard: IllegalStateException: native worker failure
Unknown: RuntimeException: unrecognized C++ exception
```

Trên macOS, dùng `$JAVA_HOME/include/darwin` và thư viện `libcppbridge.dylib`; trên Windows, dùng `%JAVA_HOME%\include\win32`, compiler/linker C++ tương thích và `cppbridge.dll`. Ví dụ lệnh build trên là dành riêng cho Linux.

## 6. Từng bước khi `ThrowNew` được gọi

Với `divide(7, 0)`:

1. Java gọi native method; C++ nhận hai `jint`.
2. C++ kiểm tra `denominator == 0` và `throw std::invalid_argument(...)`.
3. C++ stack unwinding đi tới `catch (...)` của `divide` mà **chưa** vượt qua JNI boundary.
4. Translator nhận loại lỗi là `std::invalid_argument` và gọi helper với `java/lang/IllegalArgumentException`.
5. `ThrowNew` đặt một Java exception pending trên luồng; điều này **không làm C++ lập tức ngừng chạy**.
6. Helper return; JNI entry point return qua biên giới JVM.
7. JVM phát Java `IllegalArgumentException` về vị trí gọi, nơi Java `catch` in dòng `Zero: ...`.

**`ThrowNew` không phải `throw` C++:** nó không tự gọi C++ destructors, không tự rời hàm, không tự tạo C++ stack trace. Trái lại, C++ `throw` chỉ được xử lý bởi C++ catch và không tự hình thành Java Throwable.

`ThrowNew` nhận **Java exception class + message**. `Throw` nhận **một `jthrowable` đã có**. Khi muốn lưu Java cause hoặc metadata phức tạp, phải tự xây dựng đối tượng Java Throwable/chain theo API Java, không hy vọng JNI tự chuyển C++ exception object và stack trace sang Java.

## 7. Java callback ném lỗi: dùng `ExceptionCheck`, không chỉ C++ `catch`

Ví dụ native C++ gọi một phương thức Java:

```cpp
// Đoạn cục bộ, không độc lập: listener và methodId đã hợp lệ.
env->CallVoidMethod(listener, methodId);
if (env->ExceptionCheck()) {
    // Java callback đã ném Throwable.
    // Dọn tài nguyên JNI được phép rồi return qua native boundary.
    return;
}
```

Đoạn sau **không** có tác dụng bắt Java exception:

```cpp
try {
    env->CallVoidMethod(listener, methodId);
} catch (const std::exception& e) {
    // Không tự động bắt được Java Throwable pending.
}
```

Nếu Java callback ném exception, JNI đánh dấu **pending Java exception**, chứ không biến nó thành `std::exception`. Khi đã pending, phần lớn JNI functions **không được gọi**. Các ngoại lệ được phép gồm một số thao tác kiểm tra/clear và cleanup, ví dụ `ExceptionCheck`, `ExceptionOccurred`, `ExceptionClear`, `DeleteLocalRef`, `DeleteGlobalRef`, các hàm release string/array hợp lệ.

Thông thường hãy **giữ nguyên pending exception, cleanup rồi return** cho Java nhận lỗi gốc. Nếu muốn thay thế, phải có xử lý chủ đích và cân nhắc giữ original exception làm cause. `ExceptionDescribe` **xóa pending exception** sau khi in nên không dùng nó làm logger vô hại.

## 8. Dọn tài nguyên: RAII, destructor và JNI references

C++ unwind vẫn cần cleanup tài nguyên. Nên ưu tiên `std::unique_ptr`, `std::vector`, `std::lock_guard` và các lớp RAII, tránh `new/delete` thủ công trên nhiều nhánh lỗi.

```cpp
// Phác thảo, không độc lập: cần <vector> và doNativeWork.
try {
    std::vector<int> buffer(1024);
    doNativeWork(buffer);
} catch (...) {
    translateCppException(env);
    return;
}
```

Destructor của object RAII phải **không ném exception**, đặc biệt khi một exception khác đang unwind. Nếu destructor throw trong lúc này, C++ có thể gọi `std::terminate` trước khi helper dịch sang Java.

JNI references có vòng đời khác tài nguyên C++:

- Local `jobject` từ JNI call có thể dọn bằng `DeleteLocalRef` trước khi frame kết thúc; dọn sớm trong vòng lặp dài.
- Global `jobject` từ `NewGlobalRef` phải có owner và xóa bằng `DeleteGlobalRef` ở đúng thời điểm; không tự xóa mọi global ref chỉ vì có một exception.
- `DeleteLocalRef`/`DeleteGlobalRef` thuộc nhóm cleanup cho phép trong lúc pending Java exception.
- `JNIEnv *` và local references gắn với luồng; không cache rồi dùng từ luồng khác.

Một wrapper cục bộ minh họa:

```cpp
struct LocalRefGuard {
    JNIEnv* env;
    jobject ref;

    LocalRefGuard(JNIEnv* e, jobject r) noexcept : env(e), ref(r) {}
    LocalRefGuard(const LocalRefGuard&) = delete;
    LocalRefGuard& operator=(const LocalRefGuard&) = delete;

    ~LocalRefGuard() noexcept {
        if (ref != nullptr) env->DeleteLocalRef(ref);
    }
};
```

Đây là snippet riêng để giải thích RAII; không thay cho chương trình ở mục 5. Chỉ dùng wrapper trong JNI frame và thread có `env` hợp lệ; không lưu nó qua native calls.

## 9. Nhánh lỗi khi chính exception translator thất bại

### `FindClass` trả `NULL`

Lý do có thể là không tìm được class, thiếu tài nguyên hoặc class loader không thích hợp. Nó có thể đặt Java exception pending. **Không gọi `ThrowNew` với `jclass` không hợp lệ.** Trong demo, exception classes đều thuộc Java core. Với exception class riêng của ứng dụng, native thread tự attach có thể tra class khác context; có thể cần cache global `jclass` đúng class loader hoặc nhận class từ Java ở thời điểm thích hợp.

### `ThrowNew` thất bại

Nếu native đã ném `std::bad_alloc` thì việc cấp phát Java `OutOfMemoryError` cũng có thể gặp khó khăn. `ThrowNew` có kết quả trả về và cần chính sách khi không thể thông báo Java exception. Demo dùng `FatalError` cực hạn nếu không có pending exception và không thể báo lỗi: đó là **fail-fast không phục hồi**, không phải xử lý thông thường. Dự án thực tế có thể tổ chức dữ liệu/thông điệp lỗi hạn chế cấp phát và có chiến lược fallback riêng.

### Lỗi không phải C++ exception

`catch (...)` không tự cứu `SIGSEGV`, memory corruption, `abort()`, `std::terminate`, native stack overflow hay undefined behavior. Cần phòng ngừa từ nguồn: kiểm tra bounds, tính số học tránh UB, ownership rõ, dùng ASan/UBSan hoặc công cụ phù hợp. `-Xcheck:jni` chỉ kiểm tra được một phần vi phạm JNI.

### Biên dịch C++ không hỗ trợ exception

Với `-fno-exceptions`, không thể dùng mẫu `throw/try/catch`. Phải dùng error code/result type và chuyển sang Java Throwable ngay JNI boundary, đồng thời bảo đảm các thư viện phụ không ném qua ABI không được hỗ trợ.

### Native worker thread và lỗi bất đồng bộ

`ThrowNew` đặt exception trên **JNIEnv/luồng hiện tại**; nó không tự ném sang một Java thread khác. Nếu C++ tự tạo worker thread, thread cần attach JVM, có `JNIEnv*` của chính nó, và báo lỗi qua Java callback, `CompletableFuture` hoặc message queue theo hợp đồng async. Java callback có thể để lại pending exception trên worker thread; phải xử lý trước khi tiếp tục hoặc detach, không tự chuyển qua C++ `catch`.

## 10. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Crash/`std::terminate` khi native lỗi | C++ exception thoát khỏi JNI function | Bao kín tất cả throw path bằng `try/catch (...)` ở boundary |
| Java không bắt đúng loại | Mapping sai hoặc `std::exception` bắt trước subtype | Catch subtype trước; xác định Java exception contract |
| Java callback throw nhưng native không phát hiện | Nhầm Java pending với C++ throw | `ExceptionCheck` sau `Call...Method` |
| C++ vẫn làm việc sau `ThrowNew` | Quên rằng `ThrowNew` không unwind | Cleanup hợp lệ rồi return |
| `FindClass` lỗi lúc tạo exception | Class name/loader sai hoặc đã có pending exception | Dùng internal class name `java/lang/...`; không lookup khi pending |
| `ExceptionDescribe` làm mất lỗi | Hàm debug có side effect clear | Không dùng làm logger production |
| JVM crash khi cleanup | Destructor ném hoặc JNI reference bị dùng sau delete | RAII destructor `noexcept`; quản lý references đúng |
| Kết quả phép chia sai/crash ở min-int | Signed overflow trong C++ trước khi throw | Tính bằng kiểu rộng, kiểm tra giới hạn `jint` |
| Message sai dấu Unicode | `what()` không đúng modified UTF-8 | Chuẩn hóa encoding/Java String trước khi ThrowNew |
| Lỗi compile `noexcept` conflicting | Định nghĩa JNI khác prototype header | Dùng đúng `javac -h` generated prototype, catch-all bên trong |

**Không nên đặt `noexcept` tùy ý trên JNI entry point** nếu generated header khai báo exception specification khác; compiler C++ có thể từ chối định nghĩa. Dùng `try/catch (...)` để đảm bảo hành vi không thoát exception; chỉ dùng `noexcept` cho helper nội bộ thực sự không ném.

## 11. Checklist trước khi đưa vào production

- [ ] Entry point JNI chặn được mọi C++ exception có thể phát sinh bên trong.
- [ ] Catch order đúng, có `catch (...)` cuối và Java exception mapping rõ.
- [ ] Helper không vô tình làm mất pending Java exception trước đó.
- [ ] `FindClass`/`ThrowNew` failure có cách xử lý; không return thành công giả.
- [ ] `ThrowNew` xong dọn tài nguyên được phép và **return**, không tiếp tục tùy tiện gọi JNI.
- [ ] Không truyền thông điệp không an toàn/không đúng modified UTF-8 vào `ThrowNew`.
- [ ] RAII destructor không throw, local/global JNI references có owner rõ.
- [ ] C++ catch không được dùng để thay cho `ExceptionCheck` sau Java callback.
- [ ] Xem xét thread, class loader, exception propagation của tác vụ async.
- [ ] Kiểm thử đường thành công, invalid argument, overflow, `std::bad_alloc`, ngoại lệ không phải `std::exception`, lỗi JNI đang pending, và cleanup.

## 12. Câu hỏi ôn tập

1. Tại sao `throw std::runtime_error(...)` không được đi thẳng từ C++ sang Java qua JNI?
2. `ThrowNew` có tự dừng C++ function không? Vì sao phải return sau khi đã đặt Java exception pending?
3. Vì sao `catch (const std::bad_alloc&)` phải đứng trước `catch (const std::exception&)`?
4. Nếu C++ `throw 42`, nhánh catch nào xử lý? Vì sao cần `catch (...)`?
5. Với `divide(Integer.MIN_VALUE,-1)`, vì sao code cần kiểu `long long` trước phép chia thay vì dựa vào catch của C++?
6. Nếu Java callback ném `IOException`, C++ `catch (...)` có tự bắt được không? Gọi API JNI nào?
7. `FindClass` trả `NULL` thì có thể gọi `ThrowNew` ngay không? Cần làm gì với pending exception?
8. Vì sao không bảo đảm tạo được Java `OutOfMemoryError` khi đã có lỗi `std::bad_alloc`?
9. Khi C++ destructor ném trong lúc một exception khác đang unwind, chuyện gì có thể xảy ra?
10. Native worker thread muốn báo lỗi cho Java thread khác cần cơ chế gì ngoài việc gọi `ThrowNew`?

**Ghi nhớ:** **C++ exception phải dừng trong `catch (...)` của C++ trước khi vượt JNI boundary.** Dịch nó thành Java `Throwable` bằng `ThrowNew`/`Throw`, cleanup an toàn và return. Một **pending Java exception không phải C++ exception**; phải kiểm tra và xử lý riêng qua JNI.

### Tài liệu chính thức

- [Oracle JNI Specification JDK 21 — Design Overview / Java Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- [Oracle JNI Specification JDK 21 — JNI Functions: Throw, ThrowNew, ExceptionCheck](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- [Android NDK — JNI tips: Exceptions](https://developer.android.com/ndk/guides/jni-tips).
- [JDK 21 javac tool — `-h` header generation](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html).
