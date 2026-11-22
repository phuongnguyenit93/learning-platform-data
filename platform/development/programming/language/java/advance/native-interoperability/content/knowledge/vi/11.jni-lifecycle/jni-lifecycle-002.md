# Khởi tạo thư viện qua JNI_OnLoad và xử lý mã trả về

## 1. `JNI_OnLoad` giải quyết vấn đề gì?

Khi Java cần gọi mã C/C++ qua **Java Native Interface (JNI)**, JVM phải **nạp thư viện native** và liên kết các phương thức `native` với hàm máy tương ứng. Một thư viện có thể cần làm việc chuẩn bị trước khi Java gọi bất kỳ native method nào, ví dụ:

- Xác định phiên bản JNI mà thư viện yêu cầu.
- Nhận `JNIEnv *` của thread đang nạp thư viện.
- Tìm class Java theo đúng class loader.
- Đăng ký các phương thức native bằng `RegisterNatives`.
- Khởi tạo cache `jmethodID`/`jfieldID`, global reference hoặc tài nguyên native, có cơ chế dọn dẹp khi thất bại.

Điểm móc chính là hàm **`JNI_OnLoad`**, được export từ **thư viện JNI liên kết động**. JVM gọi hàm này khi nạp thư viện (chẳng hạn thông qua `System.loadLibrary`).

~~~c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved);
~~~

Một `JNI_OnLoad` thành công phải trả về **hằng số phiên bản JNI được JVM hỗ trợ**, ví dụ `JNI_VERSION_1_6`. Giá trị trả về không phải kết quả của native method thông thường và **không phải** `JNI_OK`. Nếu phiên bản trả về không được JVM công nhận, JVM từ chối nạp thư viện.

Bài học trình bày luồng từ Java sang native, cách lấy `JNIEnv *`, đăng ký method, cách báo lỗi và dọn tài nguyên, những lỗi phổ biến khi trả sai mã, và một ví dụ **Java 17+ / C11** hoàn chỉnh.

## 2. Vòng đời từ `System.loadLibrary` tới lần gọi native đầu tiên

Giả sử Java có:

~~~java
static {
    System.loadLibrary("onload_demo");
}
~~~

Luồng có thể hình dung:

~~~text
JVM khởi tạo lớp chứa static initializer
                    |
                    v
System.loadLibrary("onload_demo")
                    |
                    v
OS loader mở file đúng OS/CPU
(lib*.so / lib*.dylib / *.dll)
                    |
                    v
JVM tìm symbol JNI_OnLoad (nếu có)
                    |
                    v
JNI_OnLoad(JavaVM *, void *)
    |-- GetEnv -> lấy JNIEnv* của thread hiện tại
    |-- FindClass / RegisterNatives / chuẩn bị state
    |-- return JNI_VERSION_1_6  (thành công)
    |-- hoặc return JNI_ERR    (thất bại)
                    |
       +------------+-------------+
       |                          |
       v                          v
JVM chấp nhận version     JVM từ chối nạp thư viện
       |                          |
       v                          v
loadLibrary trả về        Java nhận lỗi nạp thư viện
       |
       v
Java gọi native method đã liên kết
       |
       v
C/C++ xử lý rồi trả kết quả Java
~~~

**Tách bạch ba bước:**

1. **Load library:** `System.loadLibrary` yêu cầu JVM nạp thư viện. Đây là lúc hook `JNI_OnLoad` có thể chạy.
2. **Initialize/register:** `JNI_OnLoad` tùy chọn có thể kiểm tra môi trường và gọi `RegisterNatives`, sau đó trả về phiên bản JNI cần thiết.
3. **Invoke native method:** lời gọi như `plusOne(41)` mới thực sự chuyển điều khiển sang hàm xử lý nghiệp vụ C/C++.

Chỉ nạp thư viện **không tự động** thực thi mọi native method. Nếu thư viện **không export `JNI_OnLoad`**, JVM giả định thư viện chỉ yêu cầu JNI `JNI_VERSION_1_1` theo đặc tả; phương thức native vẫn có thể được tìm qua quy tắc tên JNI. Với các thư viện hiện đại cần setup rõ ràng, chủ động định nghĩa hook thường dễ kiểm soát hơn.

Một class có thể gọi `System.load` (đường dẫn file tuyệt đối) thay vì `System.loadLibrary` (tên logic không có tiền tố/đuôi). Cả hai có thể dẫn tới việc JVM nạp thư viện và xử lý `JNI_OnLoad`. Gọi `dlopen` trực tiếp trong mã C **không tương đương** hoàn toàn với nạp một JNI library thông qua cơ chế JVM.

## 3. Chữ ký và ý nghĩa từng thành phần

~~~c
#include <jni.h>

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;
    return JNI_VERSION_1_6;
}
~~~

Đây là ví dụ **hook tối thiểu**, chưa có phương thức nghiệp vụ.

| Thành phần | Ý nghĩa |
| --- | --- |
| `JNIEXPORT` | Đảm bảo cách export symbol theo JNI trên nền tảng tương ứng |
| `jint` | Kiểu số nguyên JNI dùng làm **giá trị phiên bản cần trả về** |
| `JNICALL` | Quy ước gọi ABI theo header JNI của target |
| `JNI_OnLoad` | **Tên symbol cố định** mà JVM tìm cho thư viện liên kết động |
| `JavaVM *vm` | Con trỏ Invocation API tới JVM, được truyền vào hook |
| `void *reserved` | Tham số dành riêng cho tương lai; hiện không sử dụng |
| `return JNI_VERSION_1_6` | Thư viện yêu cầu ít nhất phiên bản giao diện JNI 1.6; JVM cần hỗ trợ |

**Không có `JNIEnv *env` trong tham số của `JNI_OnLoad`.** Muốn gọi các JNI function như `FindClass`, trước tiên dùng `JavaVM->GetEnv` để nhận interface của **thread hiện tại**.

Trong C:

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->GetEnv(vm, (void **) &env, JNI_VERSION_1_6);
if (rc != JNI_OK) {
    return JNI_ERR;
}
~~~

Trong C++:

~~~cpp
JNIEnv *env = nullptr;
jint rc = vm->GetEnv(reinterpret_cast<void **>(&env),
                      JNI_VERSION_1_6);
if (rc != JNI_OK) {
    return JNI_ERR;
}
~~~

Hai đoạn trên là **mảnh ghép minh họa trong `JNI_OnLoad`**, không phải chương trình độc lập. `GetEnv` dùng để truy xuất `JNIEnv *` nếu thread đã attach, **không tự attach** một thread mới.

Một số kết quả `GetEnv`:

- `JNI_OK`: thành công, `env` có thể sử dụng.
- `JNI_EVERSION`: phiên bản JNI được yêu cầu không được hỗ trợ.
- `JNI_EDETACHED`: thread gọi không gắn với JVM.
- Các giá trị lỗi khác theo đặc tả Invocation API.

Trong `JNI_OnLoad` được JVM gọi trên thread nạp library, `GetEnv` thường thành công nếu yêu cầu phiên bản hợp lệ. Nếu không, trả mã thất bại thích hợp, tránh dereference `env == NULL`. **`JNIEnv *` gắn với thread**, không cache nó làm biến toàn cục để gọi từ các thread khác. Nếu cần giao tiếp từ native worker thread, phải sử dụng `JavaVM *` và cơ chế attach/detach riêng ngoài luồng ví dụ.

## 4. Phân biệt mã trạng thái và mã phiên bản JNI

Đây là chỗ dễ mắc lỗi nhất của `JNI_OnLoad`.

| Hằng số/giá trị | Vai trò | Có nên return trực tiếp từ `JNI_OnLoad`? |
| --- | --- | --- |
| `JNI_OK` (thường bằng `0`) | Mã trạng thái **thành công** của nhiều JNI/Invocation API, như `GetEnv` và `RegisterNatives` | **Không.** `0` không phải hằng số phiên bản JNI được yêu cầu |
| `JNI_ERR` (thường bằng `-1`) | Mã trạng thái thất bại chung | **Có thể** dùng để báo khởi tạo thất bại; JVM sẽ không coi đây là phiên bản hợp lệ |
| `JNI_VERSION_1_1` | Hằng số phiên bản JNI cũ | Chỉ khi thư viện thực sự yêu cầu mức giao diện đó |
| `JNI_VERSION_1_2`, `JNI_VERSION_1_4` | Hằng số phiên bản JNI tương ứng | Được phép nếu phù hợp API sử dụng và JVM mục tiêu |
| `JNI_VERSION_1_6` | Phiên bản phổ biến, được hỗ trợ bởi JDK 17 | **Có** trong ví dụ bài này |
| `JNI_VERSION_1_8` | Phiên bản JNI 1.8 | **Có** nếu code yêu cầu và JVM hỗ trợ |
| Một số nguyên ngẫu nhiên hoặc `0xDEADBEEF` | Không phải phiên bản JNI được công nhận | **Không.** JVM từ chối load |

**Điểm quyết định:** `JNI_OnLoad` không trả `JNI_OK` chỉ vì các bước khởi tạo thành công. Nó cần trả về **phiên bản JNI hợp lệ mà thư viện yêu cầu**.

Ví dụ logic chuẩn:

~~~c
JNIEnv *env = NULL;

if ((*vm)->GetEnv(vm, (void **) &env,
                  JNI_VERSION_1_6) != JNI_OK) {
    return JNI_ERR;       /* Không thể setup JNI */
}

/* Thực hiện các bước khởi tạo khác ... */

return JNI_VERSION_1_6;   /* Chấp nhận phiên bản JNI yêu cầu */
~~~

Nếu JVM **không nhận ra phiên bản** mà `JNI_OnLoad` trả về, đặc tả nêu JVM sẽ **unload thư viện và hành xử như thể chưa nạp thư viện**. Với lỗi trả về `JNI_ERR` hay lỗi nội bộ khi hook chạy, ứng dụng Java sẽ không có native library hợp lệ để sử dụng; ở các JVM thông dụng, thao tác load thường báo `UnsatisfiedLinkError`. Thông báo cụ thể và nguyên nhân được gói kèm phụ thuộc JVM và tình huống. Không cố bắt một chuỗi thông báo lỗi cố định.

**Không đánh đồng:** `JNI_VERSION_1_6` chỉ là **version negotiation**, không phải phiên bản của JDK đang chạy, cũng không phải giá trị cho biết đã đăng ký bao nhiêu native method hay số native resources đã cấp phát.

## 5. Ví dụ thực hành hoàn chỉnh: khởi tạo và đăng ký native method

Ta xây một thư viện C11 minh họa:

1. Java nạp thư viện qua `System.loadLibrary("onload_demo")`.
2. JVM tìm `JNI_OnLoad` và gọi hook.
3. Hook dùng `GetEnv`, `FindClass` và `RegisterNatives` để đăng ký phương thức native trước khi Java gọi nó.
4. Hook kiểm tra mã trả về từng bước và trả `JNI_VERSION_1_6` khi thành công.
5. Java gọi `plusOne(41)` và nhận `42`.

Lợi ích của ví dụ là làm rõ **`RegisterNatives` trả `JNI_OK`**, còn **`JNI_OnLoad` phải trả `JNI_VERSION_1_6`**.

### 5.1. File Java: `JniOnLoadDemo.java`

~~~java
public final class JniOnLoadDemo {
    static {
        System.loadLibrary("onload_demo");
        System.out.println("Java: library ready");
    }

    private JniOnLoadDemo() {
    }

    private static native int plusOne(int input);

    public static void main(String[] args) {
        int result = plusOne(41);
        System.out.println("Java: plusOne(41) = " + result);
    }
}
~~~

Lưu ý:

- `native` chỉ khai báo phương thức, **không** có thân hàm Java.
- Khi class `JniOnLoadDemo` được khởi tạo, `System.loadLibrary` chạy trước dòng in `"library ready"`. Nếu load thất bại, dòng đó **không được in**.
- Trong ví dụ, `plusOne` là private static native. Cơ chế `RegisterNatives` vẫn đăng ký được nó theo tên và descriptor.
- Java `int` tương ứng kiểu JNI `jint`; `plusOne(41)` tránh vấn đề overflow trong ví dụ.

Biên dịch Java và sinh header, từ thư mục chứa file:

~~~bash
javac -h . JniOnLoadDemo.java
~~~

Lệnh tạo `JniOnLoadDemo.class` và `JniOnLoadDemo.h`. Header sinh ra có prototype với tên JNI truyền thống:

~~~c
/* Trích yếu kiểu declaration do javac -h tạo. */
JNIEXPORT jint JNICALL Java_JniOnLoadDemo_plusOne(
        JNIEnv *, jclass, jint);
~~~

**Điểm cần hiểu:** vì ví dụ chọn **`RegisterNatives`** để liên kết tên `plusOne` với con trỏ C `native_plus_one`, **không phải export hàm `Java_JniOnLoadDemo_plusOne`** trong thư viện. Cả hai cách liên kết đều được JNI cho phép. Header được sinh giúp kiểm tra kiểu đúng; registration là quyết định của ví dụ.

### 5.2. File C: `onload_demo.c`

~~~c
#include <jni.h>

/* Signature C đúng cho Java static native int plusOne(int). */
static jint JNICALL native_plus_one(
        JNIEnv *env, jclass declaringClass, jint input) {
    (void) env;
    (void) declaringClass;
    return input + 1;
}

/*
 * JVM gọi hook này khi nạp thư viện bằng JNI load mechanism.
 * Trả JNI_VERSION_1_6 khi setup thành công.
 */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(vm, (void **) &env,
                      JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    /*
     * Khi gọi từ JNI_OnLoad, FindClass sử dụng class loader
     * của lớp đang nạp thư viện.
     */
    jclass localClass = (*env)->FindClass(
            env, "JniOnLoadDemo");
    if (localClass == NULL) {
        /* FindClass có thể đã để lại pending Java exception. */
        return JNI_ERR;
    }

    JNINativeMethod methods[] = {
        {
            "plusOne",
            "(I)I",
            (void *) native_plus_one
        }
    };

    jint registerStatus = (*env)->RegisterNatives(
            env, localClass, methods, 1);

    (*env)->DeleteLocalRef(env, localClass);

    if (registerStatus != JNI_OK) {
        /* Đăng ký thất bại: không công bố load thành công. */
        return JNI_ERR;
    }

    /* Trả VERSION, không trả registerStatus/JNI_OK. */
    return JNI_VERSION_1_6;
}
~~~

Đây là **toàn bộ code C cần thiết**; không cần tự định nghĩa `Java_JniOnLoadDemo_plusOne`. `#include <jni.h>` cung cấp các kiểu/hàm JNI. Khi đã có `JniOnLoadDemo.h`, cũng có thể include header đó để compiler so sánh kiểu ở mức khai báo truyền thống, nhưng vì ở đây dùng registration nên file C tập trung vào chữ ký `JNINativeMethod`.

Giải thích từng bước:

1. `GetEnv` lấy interface JNI phù hợp **thread đang chạy hook**; nếu trả khác `JNI_OK`, hook từ chối khởi tạo.
2. `FindClass("JniOnLoadDemo")` tìm lớp Java cần đăng ký. Vì code chạy bên trong `JNI_OnLoad`, loader được chọn là **loader của class đang nạp native library**.
3. `JNINativeMethod` mô tả ba phần: tên `plusOne`, JNI method descriptor `"(I)I"`, và con trỏ tới hàm C `native_plus_one`.
4. `RegisterNatives` đăng ký một entry. `registerStatus == JNI_OK` tức thao tác thành công; mã lỗi khác nghĩa là không nên tiếp tục như thể setup hợp lệ.
5. `DeleteLocalRef` giải phóng local `jclass` sau khi đã sử dụng. Không cache local reference sau hook.
6. Hook trả `JNI_VERSION_1_6` sau khi tất cả điều kiện đều đạt. Sau đó `System.loadLibrary` trả về Java và chương trình mới gọi `plusOne`.

**Lưu ý về function pointer:** trường `fnPtr` của `JNINativeMethod` có kiểu `void *` theo JNI C API và ví dụ chuyển con trỏ hàm sang `void *` theo cách thường dùng trong JNI implementations; việc ép kiểu này có thể không hoàn toàn portable theo ISO C thuần ngoài các ABI JNI được hỗ trợ. Vì vậy luôn dùng compiler/ABI tương ứng JVM đích và tránh tắt cảnh báo một cách mù quáng.

**Lưu ý về pending exception:** nếu `FindClass` hoặc `RegisterNatives` thất bại, có thể có Java exception đang chờ. Ví dụ trả `JNI_ERR` để không báo load thành công; chính xác Java sẽ thấy error nào có thể phụ thuộc JVM. Trong sản phẩm, ghi thông tin lỗi qua logging native thích hợp, thu hồi tài nguyên đã sở hữu và tránh gọi tùy ý các JNI API khi còn pending exception. `DeleteLocalRef` được phép trong các tình huống cleanup liên quan.

### 5.3. Biên dịch thư viện cho từng hệ điều hành

`JAVA_HOME` phải trỏ tới thư mục gốc **JDK 17+** có `include/jni.h`. Dùng compiler cùng kiến trúc/ABI với JVM, ví dụ cùng x64 hoặc cùng ARM64.

**Linux (GCC/Clang):**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  onload_demo.c -o libonload_demo.so
~~~

**macOS (Clang):**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  onload_demo.c -o libonload_demo.dylib
~~~

**Windows x64 (x64 Native Tools Command Prompt for Visual Studio):**

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" onload_demo.c /link /OUT:onload_demo.dll
~~~

Chỉ chạy **một nhóm lệnh theo nền tảng**. Đặt thư viện output trong thư mục chứa `JniOnLoadDemo.class`. Nếu dùng MSVC x64, hãy mở đúng Developer Command Prompt x64; không tải binary khác kiến trúc với JVM. Trên hệ điều hành có kiểm soát tìm dependent libraries, có thể còn cần cấu hình đường dẫn đến các dependency riêng của thư viện.

### 5.4. Chạy chương trình và kiểm tra stdout

~~~bash
java -Djava.library.path=. JniOnLoadDemo
~~~

Kết quả stdout khi nạp và đăng ký thành công:

~~~text
Java: library ready
Java: plusOne(41) = 42
~~~

Dòng đầu chỉ in **sau khi `System.loadLibrary` đã hoàn thành**, vì câu lệnh println đứng sau load trong cùng static initializer. Dòng thứ hai chứng minh `RegisterNatives` đã liên kết được `plusOne(int)` với hàm C trả về `42`.

**Khi gọi `plusOne`, JVM truyền hai tham số ngầm:** `JNIEnv *` của thread hiện tại và `jclass` vì đây là static native method; tiếp theo mới đến `jint input`. Vì vậy hàm C có ba tham số dù Java method chỉ khai báo một `int`.

Nếu bỏ `RegisterNatives` mà không export hàm theo quy tắc tên JNI, thư viện vẫn **có thể nạp thành công**, nhưng khi gọi `plusOne` sẽ không tìm được native implementation. Đó là **lỗi liên kết method**, khác với lỗi xảy ra ngay trong `JNI_OnLoad`.

## 6. Xử lý kết quả từng bước và khôi phục khi lỗi

Trong native initialization, không được nhìn vào một bước thành công rồi suy ra toàn bộ thư viện đã khởi tạo xong. Các loại kết quả khác nhau:

| Lời gọi | Dấu hiệu thành công | Cách xử lý thất bại |
| --- | --- | --- |
| `GetEnv(vm, ..., JNI_VERSION_1_6)` | `JNI_OK`, `env` hợp lệ | Dừng hook, trả `JNI_ERR` |
| `FindClass(env, name)` | `jclass != NULL` | Xem pending exception và lý do class loader; dừng hook |
| `GetMethodID` / `GetStaticMethodID` nếu cache method | ID khác `NULL` | Kiểm tra descriptor, release tài nguyên đã tạo |
| `NewGlobalRef` nếu tạo reference bền | Reference khác `NULL` | Dọn các resource trước đó và dừng |
| `RegisterNatives` | `JNI_OK` | Kiểm tra tên, signature, method static/instance; dừng |
| `JNI_OnLoad` | Trả `JNI_VERSION_*` được VM hỗ trợ | JNI version không hợp lệ hoặc khởi tạo thất bại làm load không thành công |

Dạng sơ đồ:

~~~text
GetEnv?
  +-- fail --> cleanup nếu cần --> JNI_ERR
  |
  v
FindClass?
  +-- fail --> xử lý exception/cleanup --> JNI_ERR
  |
  v
RegisterNatives?
  +-- fail --> release local/global resources --> JNI_ERR
  |
  v
return JNI_VERSION_1_6
~~~

### 6.1. Khi một bước khởi tạo thất bại

Chẳng hạn `FindClass` không tìm thấy class vì tên nội bộ sai, custom loader không nhìn thấy class, hoặc dependency bị thiếu. `FindClass` có thể trả `NULL` và để lại `NoClassDefFoundError`. `RegisterNatives` có thể trả mã lỗi hoặc có Java exception như `NoSuchMethodError` nếu method/descriptor không khớp.

Sau khi lỗi:

1. **Không dereference** con trỏ `NULL` hoặc dùng method ID chưa có.
2. Dọn **native resources** cấp phát trước đó (buffer, mutex, file handle, connection đã mở) trước khi trả về.
3. Dọn JNI local/global references theo hợp đồng; các hàm cleanup được phép sử dụng khi exception pending phải được chọn cẩn thận.
4. Trả giá trị cho thấy load **không hoàn thành**, chẳng hạn `JNI_ERR`, thay vì một phiên bản hợp lệ.
5. Tránh mặc định gọi `ExceptionClear` để che lỗi; chỉ clear khi có chính sách chuyển đổi lỗi rõ ràng và giữ thông tin chẩn đoán.

`JNI_OnUnload` **không phải nơi duy nhất để sửa sai `JNI_OnLoad`**: khi nạp chưa thành công, không nên dựa vào việc JVM sẽ gọi unload hook và giải phóng mọi tài nguyên bạn cấp phát. Thiết kế cleanup cục bộ theo từng bước và quản lý ownership rõ ràng.

### 6.2. Nếu cần cache nhiều thứ, thiết kế state “tất cả hoặc không”

Ví dụ một thư viện cần cache `jclass` và `jmethodID`:

~~~c
/* Đoạn thuật toán minh họa; không phải source độc lập. */
jclass local = (*env)->FindClass(env, "com/example/Bridge");
if (local == NULL) {
    return JNI_ERR;
}

jclass global = (jclass) (*env)->NewGlobalRef(env, local);
(*env)->DeleteLocalRef(env, local);
if (global == NULL) {
    return JNI_ERR;
}

jmethodID callback = (*env)->GetStaticMethodID(
        env, global, "callback", "(I)V");

if (callback == NULL) {
    (*env)->DeleteGlobalRef(env, global);
    return JNI_ERR;
}

/* Chỉ tại đây mới công bố state hoàn chỉnh cho worker khác:
   storedClass = global;
   storedMethod = callback;
   return JNI_VERSION_1_6; */
~~~

Trong code thực, phải xác định cấu trúc state, thread synchronization và chính sách cleanup rõ ràng. **`jclass` là JNI reference**, nếu muốn giữ qua nhiều lời gọi phải là **global reference**; `jmethodID` không phải object reference và chỉ hợp lệ khi class liên quan còn sống. Đừng lưu `JNIEnv *` toàn cục vì nó gắn với một thread cụ thể.

Các chuỗi đặt trong `FindClass` dùng tên JNI như `"com/example/Bridge"` (dấu slash). `GetStaticMethodID` dùng method descriptor `"(I)V"` nếu callback static nhận `int`, trả `void`. Mọi descriptor phải khớp class thực sự đã tải.

### 6.3. Có nên bắt/clear exception khi đang `JNI_OnLoad`?

Một JNI API thất bại có thể để một Java exception ở trạng thái **pending**. Mã native có thể kiểm tra nó bằng `ExceptionCheck`; trong môi trường debug dùng `ExceptionDescribe` có kiểm soát. Tuy nhiên, khi exception pending, không được tiếp tục gọi tùy ý các JNI function khác: chỉ một nhóm thao tác cleanup/exception hợp lệ. Việc `JNI_OnLoad` trả mã thất bại khi còn exception pending có thể tạo biểu hiện khác nhau giữa JVM, do đó đường lỗi production nên có chính sách nhất quán.

Một nguyên tắc hữu ích:

- **Thông tin lỗi để Java xử lý:** để JVM/Java nhận nguyên nhân theo hợp đồng JNI nếu phù hợp.
- **Thông tin lỗi cần ghi log native:** ghi trước/sau phần cleanup an toàn, không làm mất exception gốc.
- **Chuyển đổi lỗi:** nếu thực sự muốn chuyển thành lỗi native initialization duy nhất, thực hiện có chủ đích và ghi lại nguyên nhân; không `ExceptionClear` một cách vô điều kiện.

Đừng cố tạo thêm Java object, gọi callback hoặc tra thêm class sau khi một JNI call đã thất bại, nếu chưa kiểm soát trạng thái exception.

## 7. `JNI_OnUnload` và trách nhiệm dọn tài nguyên

Thư viện liên kết động có thể export hook:

~~~c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void) vm;
    (void) reserved;

    /* Chỉ cleanup những tài nguyên do thư viện sở hữu
       và chắc chắn không còn thread nào sử dụng. */
}
~~~

`JNI_OnUnload` được JVM gọi khi class loader chứa native library được GC theo đặc tả. Tuy nhiên **không được dựa vào nó như một lời hứa chạy đúng vào lúc JVM exit hoặc sau mỗi lần `System.loadLibrary`**. Nhiều ứng dụng dùng application/system class loader trong suốt tiến trình; không nên kỳ vọng unload hook luôn chạy trước khi process kết thúc.

Với các tài nguyên đặc biệt như native worker threads, sockets, global references, hãy chủ động cung cấp **API đóng/cleanup** ở mức ứng dụng khi cần giải phóng xác định. `JNI_OnUnload` chỉ là điểm dọn bổ sung phù hợp với cơ chế GC/class-loader lifecycle.

### 7.1. Những hạn chế trong unload hook

- `JNI_OnUnload` nhận `JavaVM *`, không có `JNIEnv *` truyền trực tiếp.
- JVM có thể gọi unload trong **ngữ cảnh không xác định**. Không nên thực hiện callback Java tùy ý hoặc thao tác gây phụ thuộc vào class loader đã biến mất.
- `FindClass` bên trong `JNI_OnUnload` dùng **system class loader**, khác với quy tắc trong `JNI_OnLoad`.
- Global `jclass` reference mạnh có thể **ngăn class và class loader bị thu gom**, nên nếu đợi `JNI_OnUnload` mới xóa reference có thể tạo vòng đời không mong muốn.
- Không giải phóng tài nguyên khi native method hoặc background thread vẫn còn sử dụng.

Đối với ví dụ chạy ở phần 5, ta **không cấp phát global JNI reference hoặc OS resources riêng**, nên không cần `JNI_OnUnload` để chương trình hoạt động đúng. `RegisterNatives` trong ví dụ chỉ tạo đăng ký phù hợp với vòng đời library và class khi load thành công.

## 8. Class loader: lý do `FindClass` trong `JNI_OnLoad` thường được chọn

Khi `JNI_OnLoad` chạy, `FindClass` sử dụng loader của **class đang nạp thư viện**. Điều này rất hữu ích trong ứng dụng plugin: `FindClass("com/example/PluginBridge")` có thể tìm lớp do plugin loader định nghĩa, trong khi một native worker thread tự attach về sau có thể chỉ nhìn thấy system loader.

Sự khác biệt:

| Ngữ cảnh `FindClass` | Loader liên quan |
| --- | --- |
| `JNI_OnLoad` | Loader của class gọi thao tác nạp thư viện |
| Native method bình thường | Loader của class khai báo native method |
| Native thread tự attach và không có native method context | System loader theo Invocation Interface |
| `JNI_OnUnload` | System class loader |

Do đó, một chiến lược phổ biến là tìm class/method lúc load, rồi chỉ **cache reference hợp lệ** để dùng từ thread khác. Nếu cache `jclass`, phải tạo global reference qua `NewGlobalRef` và quản lý `DeleteGlobalRef`. Không giữ một local `jclass` trong biến static để dùng sau khi `JNI_OnLoad` kết thúc.

**Cảnh báo reentrancy khi khởi tạo class:** `JNI_OnLoad` thường chạy ngay trong `static` initializer gọi `System.loadLibrary`. Code trong hook không nên gọi ngược các Java method hoặc khởi tạo phụ thuộc vòng tròn khi các lớp liên quan còn đang được initialize. Ví dụ chỉ `FindClass` và `RegisterNatives` một phương thức đơn giản, tránh callback lồng nhau.

Theo JNI Specification, **một native library không thể tùy ý được nạp đồng thời bởi hai class loaders độc lập** trong cùng JVM. Cố nạp lại cùng library từ loader khác có thể gây `UnsatisfiedLinkError`. Khi dùng plugin/hot-reload, cân nhắc lớp native bridge được tải bởi loader ổn định, hoặc cấu trúc thư viện/module phù hợp với lifecycle mỗi loader.

## 9. Không dùng `JNI_OnLoad` để thay toàn bộ chương trình

`JNI_OnLoad` là một **hook khởi tạo**, không phải điểm đặt mọi việc ứng dụng sẽ làm.

Nên làm:

- Lấy `JNIEnv *` và xác nhận khả năng API.
- Đăng ký các native method cần thiết.
- Tra ID/class đã biết trong phạm vi nhỏ.
- Khởi tạo tài nguyên native tối thiểu, có rollback/cleanup nếu lỗi.
- Trả một JNI version được hỗ trợ khi tất cả điều kiện hợp lệ.

Hạn chế hoặc tránh:

- Gọi Java callback quá sớm khi lớp đang khởi tạo.
- Bắt đầu thread và để chúng dùng state chưa init xong.
- Thực hiện network RPC, tải cấu hình từ xa hoặc IO kéo dài khiến `System.loadLibrary` bị chặn lâu.
- Giữ mutex rồi gọi Java code/loader phức tạp dẫn tới deadlock.
- Cấp phát global references mà không có lifecycle cleanup.
- Đưa business logic cần chạy mỗi lần gọi vào hook vốn thường chỉ chạy khi nạp library.

Không có thời hạn cụ thể do JNI Specification áp đặt cho `JNI_OnLoad`, nhưng hook chạy trong quá trình nạp thư viện, nên mọi trì hoãn tại đây sẽ trì hoãn **class initialization / thư viện sẵn sàng** của ứng dụng. Đặt các thao tác tốn thời gian hoặc có thể lỗi mạng vào API khởi tạo rõ ràng hơn khi thực tế cần.

## 10. C++: giữ đúng tên export và quy ước gọi

Nếu viết bằng C++, phải bảo đảm symbol `JNI_OnLoad` được export theo **C linkage** để JVM tìm thấy tên chính xác; mã C++ mặc định có thể bị name mangling.

Ví dụ **hook C++ tối thiểu độc lập về ý tưởng**:

~~~cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = nullptr;
    if (vm->GetEnv(reinterpret_cast<void **>(&env),
                   JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

Trong C++ dùng `vm->GetEnv(...)` và `env->FindClass(...)` thay cú pháp hai cấp `(*vm)->GetEnv(vm, ...)`/`(*env)->FindClass(env, ...)` của C.

Với phương thức JNI đăng ký bằng `RegisterNatives`, con trỏ function phải trỏ đến hàm có signature đúng JNI. Thường dùng một hàm C++ `static` hoặc `extern "C"` phù hợp và `reinterpret_cast<void *>(...)` theo quy ước toolchain JNI; không để C++ exception thoát ra qua biên JNI. Nếu initialization C++ có thể ném exception, catch, cleanup, ghi lại lỗi native và trả mã lỗi phù hợp theo chính sách ứng dụng.

**Đừng nhầm:** tên export của `JNI_OnLoad` phải chính xác; còn tên một hàm C++ **được đăng ký bằng `RegisterNatives`** không nhất thiết phải mang dạng `Java_package_Class_method`. Khai báo JNI method descriptor và function pointer mới là hợp đồng được JVM sử dụng trong trường hợp đăng ký động.

## 11. Khi hook không tồn tại hoặc không được gọi

Có một số trường hợp:

- **Không định nghĩa `JNI_OnLoad`:** JVM có thể vẫn nạp được library và tìm method native theo tên JNI. Theo đặc tả, JVM giả định thư viện chỉ yêu cầu JNI `JNI_VERSION_1_1`.
- **Đã định nghĩa nhưng symbol không export:** do thiếu `JNIEXPORT`/C linkage hoặc build toolchain sai; JVM có thể không thấy hook và coi như không có hook.
- **Chỉ có file library, chưa gọi `System.loadLibrary`/`System.load`:** JNI load hook chưa có lý do để chạy.
- **Java load library một lần, sau đó gọi nhiều native methods:** không mong đợi `JNI_OnLoad` chạy lại **trước mỗi method call**.
- **Library được liên kết tĩnh vào JVM:** đặc tả JNI phân biệt hook `JNI_OnLoad_L` dành cho thư viện tĩnh có tên `L` (và yêu cầu phiên bản JNI ít nhất `JNI_VERSION_1_8`), khác với `JNI_OnLoad` của thư viện động. Không dùng quy tắc static-link này cho ví dụ `.so/.dylib/.dll`.

Để chẩn đoán hook, kiểm tra symbol thực tế:

~~~bash
# Linux ELF
nm -D libonload_demo.so

# macOS Mach-O
nm -gU libonload_demo.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /exports onload_demo.dll
~~~

Tìm symbol `JNI_OnLoad`. Tên có thể hiện trang trí ở một số ABI/kiến trúc cũ; tuân thủ `JNIEXPORT`/`JNICALL` và toolchain target. Nếu build nhầm kiến trúc, JVM có thể thất bại **trước khi gọi hook**.

## 12. Lỗi thường gặp và biểu hiện

| Triệu chứng | Nguyên nhân khả dĩ | Khắc phục |
| --- | --- | --- |
| `UnsatisfiedLinkError: no onload_demo in java.library.path` | JVM không tìm được file thư viện | Tên logic/tên file theo OS, đường dẫn `-Djava.library.path`, kiến trúc |
| `UnsatisfiedLinkError` về phiên bản JNI lúc load | `JNI_OnLoad` trả `JNI_OK`, `JNI_ERR` hoặc version không được hỗ trợ | Trả đúng hằng số `JNI_VERSION_*` hỗ trợ khi setup thành công |
| Native method chạy tới mới báo `UnsatisfiedLinkError` | Không đăng ký thành công/không có exported `Java_*` symbol | So `JNINativeMethod`, header `javac -h`, tên/signature và đường link |
| `RegisterNatives` trả lỗi hoặc có pending exception | Method không tồn tại, descriptor sai, class không đúng | Kiểm tra `"(I)I"` và method thực tế là `static native int plusOne(int)` |
| `FindClass` không thấy class khi load | Sai tên nội bộ, loader không nhìn thấy class, thiếu dependency | Dùng tên slash; xem class gọi `loadLibrary`/context loader |
| JVM crash hoặc lỗi khó tái hiện từ native worker | Cache `JNIEnv *`/local `jclass` sai phạm vi hoặc race với init | Mỗi thread lấy `JNIEnv *` riêng; dùng global ref/cleanup hợp lệ |
| C++ hook có trong source nhưng JVM không gọi | Name mangling hoặc symbol không được export | `extern "C" JNIEXPORT jint JNICALL JNI_OnLoad`; kiểm tra export |
| Lỗi chỉ khi hot reload plugin | Global refs giữ class loader sống hoặc cùng library được load bởi loader khác | Thiết kế owner loader, explicit cleanup và bridge |
| Trông đợi `JNI_OnUnload` nhưng chưa thấy | Loader vẫn sống; JVM có thể kết thúc trước khi unload | Không dùng unload hook làm bảo đảm shutdown; đóng tài nguyên chủ động |

### 12.1. Công cụ kiểm tra JNI

Trên HotSpot/OpenJDK, có thể chạy lại ví dụ với:

~~~bash
java -Xcheck:jni -Djava.library.path=. JniOnLoadDemo
~~~

`-Xcheck:jni` hỗ trợ phát hiện nhiều lỗi dùng JNI, nhưng không bảo đảm bắt được mọi lỗi memory/ABI/lifecycle; cần kết hợp stack trace Java, symbol export, phiên bản JDK và log native. Mã đúng vẫn in hai dòng stdout ở phần 5.

Khi gặp `ExceptionInInitializerError` hoặc `NoClassDefFoundError` về việc không thể khởi tạo class, tìm **lỗi ban đầu** xuất phát từ `System.loadLibrary` trong static initializer; lần dùng class tiếp theo có thể cho thông báo khác với lần đầu.

## 13. Checklist áp dụng vào thư viện JNI thực tế

- Lớp nào sở hữu `System.loadLibrary` và class loader nào nạp nó?
- Shared library có export đúng `JNI_OnLoad`, dùng `JNIEXPORT`/`JNICALL` và C linkage nếu là C++?
- Hook có gọi `GetEnv` với version thực sự được thư viện yêu cầu?
- Mọi thao tác `FindClass`, `RegisterNatives`, `NewGlobalRef` đều kiểm tra kết quả?
- Mã trạng thái `JNI_OK`/`JNI_ERR` có được phân biệt với **JNI_VERSION** dùng để trả từ hook?
- Khi setup một phần thất bại, đã release **tất cả tài nguyên sở hữu** và không tiếp tục với state nửa chừng?
- Có tránh callback/IO dài, reentrancy vào các class đang initialize?
- Local/global references, method IDs và JNI env có đúng phạm vi thread/lifetime?
- Có chính sách unload/cleanup chủ động khi plugin cần reload?
- Build có đúng OS/ABI, đường dẫn và symbol? Đã dùng `javac -h`/JNI descriptor để kiểm tra các method được đăng ký?
- Khi app gặp lỗi load, đã chẩn đoán **load library**, **JNI_OnLoad initialization** và **native method resolution** thành ba bước khác nhau?

## 14. Câu hỏi tự kiểm tra

**1.** `RegisterNatives` trả `JNI_OK`. Có thể `return JNI_OK;` từ `JNI_OnLoad` không?  
**Đáp án:** **Không.** `JNI_OnLoad` phải trả phiên bản JNI được JVM hỗ trợ, ví dụ `JNI_VERSION_1_6`, nếu khởi tạo thành công.

**2.** `JNI_OnLoad` có nhận `JNIEnv *` trực tiếp không?  
**Đáp án:** Không; nhận `JavaVM *` và lấy `JNIEnv *` của thread hiện tại qua `GetEnv`.

**3.** JVM phải làm gì nếu hook trả một version không được công nhận?  
**Đáp án:** Từ chối nạp, unload library và hành xử như library chưa được nạp theo đặc tả.

**4.** Vì sao có thể dùng `FindClass` cho class plugin trong `JNI_OnLoad` nhưng thất bại từ worker thread tự attach?  
**Đáp án:** Trong `JNI_OnLoad` JNI dùng loader của lớp nạp library; native thread không có native method context thường dùng system loader.

**5.** Có thể lưu `JNIEnv *` mà `GetEnv` trả về rồi dùng trong tất cả worker threads không?  
**Đáp án:** Không. `JNIEnv *` gắn với thread; lưu `JavaVM *` và lấy `JNIEnv *` riêng cho từng thread.

**6.** Nếu đăng ký `plusOne` với descriptor `"(J)I"` nhưng Java khai báo `native int plusOne(int)` thì sao?  
**Đáp án:** Mismatch signature (Java `long` vs `int`); `RegisterNatives` không đăng ký đúng Java method và hook phải xử lý lỗi, không trả version thành công.

**7.** Tại sao không nên trông đợi `JNI_OnUnload` chạy để rollback khi `JNI_OnLoad` thất bại?  
**Đáp án:** Nạp chưa hoàn thành không bảo đảm unload hook sẽ làm cleanup cho những tài nguyên bạn đã cấp phát; khởi tạo phải có cleanup theo nhánh lỗi.

**8.** `JNI_OnLoad` nên gọi Java callback để bắt đầu mọi tác vụ ngay không?  
**Đáp án:** Không phải mặc định. Hook chạy lúc class/library đang khởi tạo; callback có thể gây reentrancy, deadlock hoặc trì hoãn load. Chỉ thực hiện setup nhỏ và chắc chắn, còn logic dài nên thuộc API khác.

## 15. Tài liệu tham khảo

- [Oracle Java SE 17 — JNI Invocation API: JNI_OnLoad, JNI_OnUnload](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): chữ ký hook, thời điểm gọi, yêu cầu trả phiên bản, không có hook và unload.
- [Oracle Java SE 17 — JNI Invocation API: GetEnv](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html#getenv): lấy `JNIEnv *` của thread, `JNI_OK`/`JNI_EVERSION`/`JNI_EDETACHED`.
- [Oracle Java SE 17 — JNI Functions: RegisterNatives](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#registernatives): `JNINativeMethod`, tên, chữ ký, function pointer và kết quả.
- [Oracle Java SE 17 — JNI Functions: FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): loader theo native method và `JNI_OnLoad`, tên internal.
- [Oracle Java SE 17 — JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html): `jint`, `jclass`, `JavaVM`, method descriptors.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): thực hành `RegisterNatives` trong `JNI_OnLoad` và quản lý class loader/refs.

**Quy tắc nhớ:** Trong `JNI_OnLoad`, kiểm tra kết quả từng bước bằng mã trạng thái thích hợp, dọn tài nguyên khi thất bại, rồi **trả JNI_VERSION được hỗ trợ** chỉ khi toàn bộ quá trình khởi tạo đã thành công.
