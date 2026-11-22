# Khai báo phiên bản JNI mà thư viện yêu cầu

## 1. Vì sao thư viện JNI cần khai báo phiên bản?

Thư viện native (C/C++) được nạp qua `System.loadLibrary` hoặc `System.load` có thể cần những hàm của **Java Native Interface (JNI)** chỉ xuất hiện từ một phiên bản JNI nhất định. JVM cần biết **mức giao diện JNI tối thiểu** thư viện dựa vào để quyết định có thể chấp nhận thư viện đó hay không.

Với **thư viện liên kết động**, cách khai báo tiêu chuẩn là xuất một hàm có tên chính xác **`JNI_OnLoad`** từ file `.so`/`.dylib`/`.dll`:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
```

Đoạn này là một **hàm C hoàn chỉnh** nhưng chưa phải shared library tự đủ để Java gọi phương thức native; mục 6 có cả Java, C và lệnh biên dịch/chạy. Hàm trả `JNI_VERSION_1_6` nghĩa là **“thư viện yêu cầu giao diện JNI từ mức 1.6 trở lên”**, không phải “chỉ chạy trên JDK 6”, và cũng không yêu cầu JVM báo lại phiên bản JNI đúng bằng 1.6.

**Điểm cần nắm:**

- `JNI_OnLoad` là **hook vòng đời thư viện**, không phải một phương thức `native` khai báo trong lớp Java.
- JVM gọi hook khi đang **nạp thư viện native**, trước khi bước nạp thành công kết thúc.
- Thư viện trả về một **hằng `JNI_VERSION_*` được JVM công nhận** cho mức JNI cần sử dụng.
- Nếu JVM không nhận diện phiên bản do `JNI_OnLoad` trả về, JVM **từ chối và dỡ việc nạp thư viện**, xử lý như thư viện chưa được nạp.
- Nếu thư viện động **không export `JNI_OnLoad`**, theo đặc tả JVM giả định thư viện chỉ yêu cầu `JNI_VERSION_1_1`. Đó là quy ước tương thích cũ, **không phải** khuyến nghị bỏ khai báo cho thư viện hiện đại.

Bài học này tập trung vào **cách khai báo, chọn, kiểm tra và xử lý phiên bản JNI** trong vòng đời thư viện, không nhầm nó với phiên bản Java source/bytecode hoặc hệ điều hành.

## 2. Phân biệt ba khái niệm phiên bản dễ nhầm

| Khái niệm | Ví dụ | Do đâu quyết định? | Dùng để làm gì? |
| --- | --- | --- | --- |
| Phiên bản JDK/JVM chạy ứng dụng | JDK 17, 21, 24 | Bộ runtime cài và chạy chương trình Java | Quyết định API Java, JVM và JNI thực tế hỗ trợ |
| Phiên bản ngôn ngữ/class file | Java `--release 17`, class file version 61 | Cấu hình compiler và target runtime | Quyết định mã Java có chạy trên JVM tương ứng không |
| **Phiên bản JNI thư viện yêu cầu** | `JNI_VERSION_1_6`, `JNI_VERSION_1_8` | Do nhà phát triển thư viện khai báo trong `JNI_OnLoad` | Yêu cầu mức API JNI mà thư viện phụ thuộc |

Ví dụ, **JDK 17** có thể nạp một thư viện C khai báo **`JNI_VERSION_1_6`**: thư viện chỉ yêu cầu một tập hàm JNI đã có từ mức đó. Không cần thay thành “`JNI_VERSION_17`”; trên JDK 17, `JNIEnv::GetVersion()` thực tế trả **`JNI_VERSION_10`**, vì cách đánh số phiên bản giao diện JNI không nhất thiết tăng theo từng bản Java SE.

Điều đó đồng nghĩa:

- `JNI_VERSION_1_6` **không phải** “cần Java 6 đúng bằng 6”.
- `JNI_VERSION_1_8` **không phải** tham số cấu hình compiler Java.
- `JavaVM::GetEnv(..., JNI_VERSION_1_6)` yêu cầu lấy interface JNI mức 1.6 trên luồng hiện tại; **không phải** lệnh nạp thư viện hay khởi động JVM.
- `System.getProperty("java.version")` cho biết phiên bản Java runtime; **không thay thế** `JNIEnv::GetVersion()` và không được dùng để tự bịa tên hằng `JNI_VERSION_*`.
- `--enable-native-access=...` của các JDK mới là **quyền native access**, không phải phiên bản JNI cần khai báo.

## 3. Các hằng `JNI_VERSION_*` và cách chọn

Các hằng được định nghĩa trong `jni.h` của JDK tương ứng. Các mức thường cần biết:

| Hằng | Giá trị số hex | Diễn giải |
| --- | --- | --- |
| `JNI_VERSION_1_1` | `0x00010001` | JNI 1.1 (mức tương thích cũ) |
| `JNI_VERSION_1_2` | `0x00010002` | JNI 1.2 |
| `JNI_VERSION_1_4` | `0x00010004` | JNI 1.4 |
| `JNI_VERSION_1_6` | `0x00010006` | JNI 1.6 |
| `JNI_VERSION_1_8` | `0x00010008` | JNI 1.8 |
| `JNI_VERSION_9` | `0x00090000` | JNI 9 |
| `JNI_VERSION_10` | `0x000A0000` | JNI 10 |
| `JNI_VERSION_19` | `0x00130000` | JNI 19, trên JDK hỗ trợ |
| `JNI_VERSION_21` | `0x00150000` | JNI 21, trên JDK hỗ trợ |
| `JNI_VERSION_24` | `0x00180000` | JNI 24, trên JDK hỗ trợ |

**Không phải mọi JDK đều định nghĩa hoặc hỗ trợ mọi hằng trong bảng.** Ví dụ `JNI_VERSION_24` không có trong header của JDK 17. Nếu biên dịch native code bằng `jni.h` cũ mà ghi hằng mới, compiler có thể báo identifier chưa được định nghĩa. Đồng thời, việc compiler nhận một hằng không bảo đảm JVM lúc chạy cũng hỗ trợ mức đó.

### 3.1. Phiên bản nào là “đúng”?

Nguyên tắc là **khai báo ít nhất phiên bản JNI cần cho những hàm thực sự sử dụng**:

- Thư viện chỉ dùng các hàm rất cơ bản nhưng muốn có hợp đồng tương thích tường minh: có thể chọn mức ổn định được hỗ trợ (ví dụ `JNI_VERSION_1_6` với môi trường hỗ trợ từ Java 6 trở lên).
- Thư viện sử dụng hàm mới hơn mức đã khai báo phải nâng mức yêu cầu đủ cao. Theo đặc tả, `AttachCurrentThreadAsDaemon` được giới thiệu trong JNI 1.4, do đó thư viện sử dụng hàm này phải khai báo **ít nhất `JNI_VERSION_1_4`**.
- Thư viện yêu cầu API xuất hiện ở JNI 1.8 trở lên thì trả `JNI_VERSION_1_8` hoặc mức hỗ trợ thích hợp, **không** giữ `JNI_VERSION_1_2` chỉ để có vẻ tương thích.
- Không trả hằng cao nhất mà SDK/`jni.h` tình cờ có nếu thư viện không dùng tính năng mới đó: làm vậy **tăng yêu cầu runtime một cách không cần thiết**.

**Ví dụ:** thư viện chỉ dùng `GetIntArrayElements`, `ReleaseIntArrayElements`, `GetMethodID` và `CallIntMethod`, chạy với các JDK hiện đại, hoàn toàn có thể lựa chọn mức yêu cầu phù hợp như `JNI_VERSION_1_6` trong chính sách hỗ trợ của dự án, thay vì luôn đòi JNI mới nhất.

Khi thiết kế cần tương thích với JVM rất cũ, phải đối chiếu chính xác **hàm JNI đầu tiên xuất hiện ở phiên bản nào** từ đặc tả và test với runtime thấp nhất được hỗ trợ; không suy diễn từ số phiên bản Java source.

### 3.2. Mã hằng biểu diễn major/minor

Kiểu `jint` trong JNI được dùng cho mã phiên bản. Giá trị trả về có thể quan sát như:

```c
jint version = JNI_VERSION_1_6; /* 0x00010006 */
jint major = (version >> 16) & 0xFFFF; /* 1 */
jint minor = version & 0xFFFF;         /* 6 */
```

Đây là ví dụ giải mã số; các hằng phiên bản JNI cho Java 9 trở đi có dạng major như `9`, `10`, `19`, v.v., minor `0`. Đừng nhầm `JNI_VERSION_10` với tên “1.10”.

## 4. Cơ chế `JNI_OnLoad` trong vòng đời thư viện

Chữ ký tiêu chuẩn:

```c
jint JNI_OnLoad(JavaVM *vm, void *reserved);
```

Các thành phần:

- **Tên `JNI_OnLoad`:** JVM tìm đúng ký hiệu exported này từ thư viện liên kết động; đây không phải tên tùy ý.
- **`jint`:** kiểu số nguyên trả về chứa mã `JNI_VERSION_*`.
- **`JavaVM *vm`:** con trỏ tới JVM hiện tại, có thể dùng để gọi Invocation API như `GetEnv`. Nếu lưu để dùng ở worker native sau này, phải quản lý vòng đời JVM và luồng đúng cách.
- **`void *reserved`:** tham số dành riêng, hiện không được sử dụng; không dereference nó.
- **`JNIEXPORT` và `JNICALL`:** macro trong `jni.h` hỗ trợ export symbol và convention gọi phù hợp, đặc biệt quan trọng trên Windows.

Luồng nạp điển hình:

```text
Java: System.loadLibrary("jniversiondemo")
                  |
                  v
    JVM/OS tìm và mở shared library
                  |
                  v
         Có JNI_OnLoad không?
          /                 \
       Có                    Không
        |                      |
        v                      v
    Gọi JNI_OnLoad(vm, ...)    JVM giả định JNI_VERSION_1_1
        |
        v
    Kiểm tra phiên bản trả về
       /             \
    Hợp lệ          Không được JVM nhận diện
      |                  |
      v                  v
    Hoàn thành nạp     Hủy việc nạp/thư viện không được chấp nhận
      |
      v
  Java tiếp tục và có thể gọi native methods
```

Điểm quan trọng: **export một native method `Java_Package_Class_method` không thay thế `JNI_OnLoad`**. Trình tự nạp thư viện và việc tìm symbol native của phương thức là hai bước có vai trò khác nhau.

### 4.1. Vì sao nên dùng `JNI_OnLoad` dù không cần khởi tạo phức tạp?

Có nhiều lợi ích:

1. **Tuyên bố phiên bản tối thiểu bằng hợp đồng chính thức:** người đọc và JVM biết thư viện muốn giao diện nào.
2. **Kiểm tra môi trường ngay lúc nạp:** phát hiện `JNI_EVERSION` hoặc lỗi setup sớm, thay vì chờ đến lời gọi native đầu tiên.
3. **Nơi khởi tạo có kiểm soát:** có thể lưu `JavaVM*`, đăng ký native methods bằng `RegisterNatives` hoặc chuẩn bị tài nguyên nếu thực sự cần.
4. **Điểm gắn logic cleanup:** nếu có resource cần dọn khi class loader unload, có thể cung cấp `JNI_OnUnload` tương ứng (nhưng thời điểm hook unload không bảo đảm xảy ra khi tiến trình kết thúc).

Tuy nhiên, `JNI_OnLoad` **không nên** trở thành nơi khởi chạy background work không có shutdown, callback Java tùy ý hoặc giữ JNI reference không có ownership rõ. Đối với khởi tạo thất bại, nên dọn mọi tài nguyên đã cấp phát và trả giá trị lỗi thay vì giả vờ nạp thành công.

## 5. `GetEnv`, `GetVersion` và `JNI_OnLoad` không phải một việc

Ba API/khái niệm dễ bị lẫn:

| API | Vai trò | Nơi dùng |
| --- | --- | --- |
| `JNI_OnLoad(...)` | **Khai báo JNI tối thiểu mà native library yêu cầu** và thực hiện setup | Hook được JVM gọi lúc nạp thư viện |
| `JavaVM::GetEnv(..., requestedVersion)` | Lấy `JNIEnv*` cho **thread hiện tại** và một phiên bản interface được yêu cầu | Mã native có `JavaVM*` |
| `JNIEnv::GetVersion()` | Xem **phiên bản JNI của JVM** | Mã native đã có `JNIEnv*` hợp lệ |

Ví dụ kiểm tra mức `JNI_VERSION_1_6` trong `JNI_OnLoad`:

```c
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void)reserved;
    JNIEnv *env = NULL;

    jint status = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (status != JNI_OK || env == NULL) {
        return JNI_ERR;
    }
    return JNI_VERSION_1_6;
}
```

Đây là hàm C **đầy đủ**, dùng trong tệp native hoàn chỉnh ở mục 6. Lời gọi `GetEnv` không phải lệnh attach: nếu thread chưa attached, nó trả `JNI_EDETACHED`; nếu phiên bản interface không được hỗ trợ, nó trả `JNI_EVERSION`. Khi `JNI_OnLoad` được gọi từ Java đang tải thư viện, luồng hiện tại đã có ngữ cảnh JVM phù hợp, nên mẫu kiểm tra này là hợp lý.

**Đừng viết:**

```c
/* SAI: GetEnv không trả mã phiên bản, mà trả mã trạng thái. */
jint version = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_6);
return version;
```

`GetEnv` trả **`JNI_OK`, `JNI_EDETACHED` hoặc `JNI_EVERSION`**, chứ không trả hằng `JNI_VERSION_*`. Trả `JNI_OK` (thường bằng 0) từ `JNI_OnLoad` sẽ không khai báo một phiên bản JNI hợp lệ.

### 5.1. Vậy `GetVersion()` trả gì?

Trong một hàm C JNI đã được truyền `JNIEnv *env`:

```c
jint actual = (*env)->GetVersion(env);
```

`actual` mô tả phiên bản JNI mà JVM cung cấp; **không** buộc bằng mức tối thiểu thư viện trả trong `JNI_OnLoad`. Cụ thể, bảng đặc tả JNI liệt kê **Java SE 17 trả `JNI_VERSION_10`**, dù thư viện có thể khai báo `JNI_VERSION_1_6`.

Một thư viện có thể có yêu cầu tối thiểu thấp (`1.6`) nhưng chạy trên JVM có JNI cao hơn (`10`, `21`, `24`...). Đó là tương thích ngược bình thường.

Nếu code cần thêm API mới theo điều kiện runtime, nên kiểm tra khả năng hỗ trợ bằng cơ chế có căn cứ (ví dụ `GetEnv` đối với mức JNI cần thiết), thay vì suy ra rằng phiên bản Java luôn bằng mã phiên bản JNI. Không nên “nâng” phiên bản `JNI_OnLoad` theo runtime nếu điều đó làm mất khả năng chạy trên JVM cũ mà thư viện vẫn đủ chức năng.

## 6. Ví dụ chạy được: Java 17 + C khai báo `JNI_VERSION_1_6`

Ví dụ sau có đủ Java source, C source, header do `javac` sinh và lệnh build trên ba hệ điều hành. Bài tập xác nhận:

- JVM thực sự chấp nhận `JNI_OnLoad` trả `JNI_VERSION_1_6`.
- Java vẫn gọi được hai native methods.
- Giá trị JNI yêu cầu được in theo mã major/minor từ thư viện C.
- Stdout xác định giống nhau trên **JDK 17 và các JDK mới hơn còn hỗ trợ mức JNI 1.6**, trên đường đi nạp thành công.

### 6.1. Tệp `JniVersionDemo.java`

```java
public final class JniVersionDemo {
    static {
        System.loadLibrary("jniversiondemo");
    }

    private JniVersionDemo() {
    }

    private static native int requiredVersion();
    private static native int add(int a, int b);

    public static void main(String[] args) {
        int version = requiredVersion();

        int major = (version >>> 16) & 0xFFFF;
        int minor = version & 0xFFFF;

        System.out.println("required JNI: " + major + "." + minor);
        System.out.println("add: " + add(20, 22));
    }
}
```

`System.loadLibrary` nhận **tên logic** `"jniversiondemo"`, không chứa `lib` hoặc extension. Khi JVM chạy static initializer của lớp, nó tìm shared library tương ứng trong đường dẫn tìm native libraries rồi xử lý `JNI_OnLoad`. Phương thức `requiredVersion()` và `add(...)` được triển khai bằng C.

### 6.2. Sinh header JNI

Trong thư mục chứa `JniVersionDemo.java`, chạy:

```bash
javac -h . JniVersionDemo.java
```

Lệnh tạo `JniVersionDemo.class` và `JniVersionDemo.h`. Header sinh ra khai báo đúng hai hàm JNI:

- `Java_JniVersionDemo_requiredVersion` (trả `jint`).
- `Java_JniVersionDemo_add` (nhận hai `jint` và trả `jint`).

**`JNI_OnLoad` không phải Java method**, do đó **không cần và không có khai báo Java `native` tương ứng**; symbol `JNI_OnLoad` được xuất trực tiếp từ thư viện C theo đặc tả Invocation API.

### 6.3. Tệp `JniVersionDemo.c`

```c
#include "JniVersionDemo.h"

JNIEXPORT jint JNICALL JNI_OnLoad(
        JavaVM *vm, void *reserved) {
    (void)reserved;

    JNIEnv *env = NULL;
    jint status = (*vm)->GetEnv(
            vm, (void **)&env, JNI_VERSION_1_6);

    if (status != JNI_OK || env == NULL) {
        /* Không dùng JNI interface khi chưa được xác nhận. */
        return JNI_ERR;
    }

    /* Khai báo mức JNI tối thiểu thư viện yêu cầu. */
    return JNI_VERSION_1_6;
}

JNIEXPORT jint JNICALL Java_JniVersionDemo_requiredVersion(
        JNIEnv *env, jclass callerClass) {
    (void)env;
    (void)callerClass;
    return JNI_VERSION_1_6;
}

JNIEXPORT jint JNICALL Java_JniVersionDemo_add(
        JNIEnv *env, jclass callerClass, jint a, jint b) {
    (void)env;
    (void)callerClass;
    return a + b;
}
```

Giải thích:

- `JniVersionDemo.h` bao gồm `jni.h`, định nghĩa `JNIEXPORT`, `JNICALL`, `JNI_VERSION_1_6` và các kiểu `JNIEnv`/`JavaVM`/`jint`.
- `JNI_OnLoad` được JVM gọi khi thư viện nạp; nó kiểm tra `GetEnv` thành công và trả **`JNI_VERSION_1_6`**.
- `JNI_ERR` dùng để từ chối khởi tạo khi kiểm tra thất bại. Đây **không** phải hằng phiên bản JNI.
- `requiredVersion` trả cùng hằng `JNI_VERSION_1_6` để Java hiển thị; đó là **phương thức JNI minh họa**, không phải cơ chế khai báo phiên bản chính thức.
- Hai native methods là `static`, nên đối số ẩn JNI thứ hai là `jclass`, không phải `jobject`.
- Cộng `20 + 22` cho kết quả xác định và không có nguy cơ tràn `jint`.

### 6.4. Linux — GCC

Điều kiện: JDK 17+ được trỏ bởi `JAVA_HOME`, có `gcc`, các lệnh chạy cùng thư mục với hai tệp nguồn.

```bash
javac -h . JniVersionDemo.java

gcc -shared -fPIC \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/linux" \
    JniVersionDemo.c -o libjniversiondemo.so

java -Djava.library.path=. JniVersionDemo
```

### 6.5. macOS — Clang

Điều kiện: `JAVA_HOME` hợp lệ và có Clang/Xcode Command Line Tools.

```bash
javac -h . JniVersionDemo.java

clang -dynamiclib \
    -I"$JAVA_HOME/include" \
    -I"$JAVA_HOME/include/darwin" \
    JniVersionDemo.c -o libjniversiondemo.dylib

java -Djava.library.path=. JniVersionDemo
```

### 6.6. Windows — MSVC

Mở x64 Native Tools Command Prompt (hoặc Developer Command Prompt tương ứng với kiến trúc JDK), cấu hình `JAVA_HOME` và dùng `cmd.exe`:

```bat
javac -h . JniVersionDemo.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" JniVersionDemo.c /link /OUT:jniversiondemo.dll

java -Djava.library.path=. JniVersionDemo
```

Để tránh lỗi ABI, dùng compiler/định dạng binary phù hợp với kiến trúc JVM đang chạy. Nếu JVM 64 bit thì thư viện cũng phải tương thích 64 bit.

### 6.7. Stdout chính xác

Khi Java tìm thấy thư viện, JVM công nhận phiên bản và hai native methods chạy thành công:

```text
required JNI: 1.6
add: 42
```

Ở ví dụ này, code chỉ in **mức yêu cầu cố định** của thư viện và phép cộng; không in phiên bản JNI runtime, nên hai dòng trên không bị thay đổi chỉ vì JDK hỗ trợ một mức JNI mới hơn.

Nếu muốn quan sát runtime, bạn có thể thêm một native method trả `(*env)->GetVersion(env)` rồi giải mã major/minor ở Java. Khi đó **đầu ra phụ thuộc JDK**: ví dụ trên Java SE 17, `GetVersion` tương ứng `JNI_VERSION_10`, không phải 1.6; không nên hard-code “runtime JNI = 1.6” trong bài test đa JDK.

### 6.8. Nếu muốn yêu cầu JNI 1.8 thay vì 1.6?

Trong **`JniVersionDemo.c`**, chỉ khi logic thư viện thực sự yêu cầu mức đó, thay đổi nhất quán:

```c
/* Trích các thay đổi, không phải file C độc lập. */
jint status = (*vm)->GetEnv(
        vm, (void **)&env, JNI_VERSION_1_8);

/* Trong JNI_OnLoad sau khi GetEnv thành công: */
return JNI_VERSION_1_8;

/* Trong native requiredVersion() minh họa: */
return JNI_VERSION_1_8;
```

Sau đó phải **biên dịch lại** thư viện bằng header JDK có hằng `JNI_VERSION_1_8` và chạy trên JVM hỗ trợ mức này. Stdout minh họa sẽ trở thành `required JNI: 1.8`. Không chỉ đổi Java source, vì phiên bản được quyết định tại biên native.

## 7. Phân biệt version negotiation với việc gọi API không được hỗ trợ

### 7.1. `JNI_OnLoad` không cấp phép truy cập API tùy ý

Trả `JNI_VERSION_1_8` không “nâng cấp” một JVM cũ thành JNI 1.8. Nó chỉ yêu cầu JVM phải **công nhận** mức đó; nếu không, việc nạp bị từ chối. Các hàm JNI mới chỉ sử dụng được nếu runtime thực sự hỗ trợ. Hãy chọn phiên bản tối thiểu theo hàm dùng thực tế và testing matrix của dự án.

### 7.2. Thiếu `JNI_OnLoad` không nên được dùng như một thủ thuật tương thích

Có thể bỏ hàm `JNI_OnLoad` nếu thư viện động thực sự chỉ cần giao diện mức 1.1: JVM **mặc định giả định `JNI_VERSION_1_1`**. Tuy nhiên việc thư viện có thể nạp trên JDK hiện đại dù không export hook **không chứng minh** thư viện đã khai báo đúng các hàm mới mà nó cần. Với JNI hiện đại, nên export `JNI_OnLoad` và trả mức yêu cầu hợp lệ.

### 7.3. Đừng nhầm `GetEnv` với `AttachCurrentThread`

`GetEnv` chỉ truy xuất `JNIEnv*` của **thread đã attached**. Nếu một native worker do C/C++ tạo cần gọi Java, worker phải attach bằng `AttachCurrentThread` hoặc `AttachCurrentThreadAsDaemon` phù hợp trước khi dùng JNI. Đối số phiên bản của `GetEnv` không tự attach thread và không phải giá trị return của `JNI_OnLoad`.

Ví dụ với C (minh họa nằm trong code có `JavaVM *vm` hợp lệ):

```c
JNIEnv *threadEnv = NULL;
jint status = (*vm)->GetEnv(
        vm, (void **)&threadEnv, JNI_VERSION_1_6);

if (status == JNI_OK) {
    /* Thread đã attached và có interface JNI 1.6. */
} else if (status == JNI_EDETACHED) {
    /* Thread chưa attached: cần thiết kế attach nếu muốn gọi JNI. */
} else if (status == JNI_EVERSION) {
    /* JVM không hỗ trợ phiên bản JNI yêu cầu. */
}
```

Không dùng `threadEnv` trên thread khác và không gọi `DetachCurrentThread` trong lúc đang có Java frame trên stack.

## 8. Khác biệt giữa thư viện động và thư viện liên kết tĩnh

Phần lớn ứng dụng JNI desktop/server dùng **shared library**; với loại này, hook tiêu chuẩn là **`JNI_OnLoad`**. Nhưng JNI Specification còn định nghĩa cơ chế **statically linked native library** (thư viện được liên kết tĩnh với VM/ứng dụng), xuất hiện từ JDK 8.

Nếu thư viện tĩnh có tên logic `L`, nó phải cung cấp hook:

```c
/* Cú pháp mang tính minh họa: L được thay bằng tên thư viện. */
JNIEXPORT jint JNICALL JNI_OnLoad_L(JavaVM *vm, void *reserved);
```

Cụ thể với tên `mylib`, hook là `JNI_OnLoad_mylib`. Đặc tả yêu cầu phiên bản JNI trả về từ `JNI_OnLoad_L` **tối thiểu `JNI_VERSION_1_8`**. Nếu JVM không nhận diện mã đó, thư viện tĩnh cũng không được chấp nhận nạp qua cơ chế JNI tương ứng.

**Đừng nhầm:** thư viện đang được build bằng `gcc -shared` hoặc `cl /LD` trong ví dụ ở mục 6 là **thư viện động**, nên dùng **`JNI_OnLoad`**, không thay bằng `JNI_OnLoad_jniversiondemo`. Hook có hậu tố tên thư viện chỉ dành cho đường đi static linking theo đặc tả.

Với thư viện động, hook dọn tương ứng là `JNI_OnUnload`; với thư viện tĩnh là `JNI_OnUnload_L`.

## 9. `JNI_OnUnload` và việc dọn tài nguyên

Nếu cần cleanup khi class loader sở hữu thư viện được thu gom, thư viện động có thể export:

```c
JNIEXPORT void JNICALL JNI_OnUnload(
        JavaVM *vm, void *reserved) {
    (void)vm;
    (void)reserved;
    /* Dọn các tài nguyên native mà thư viện thật sự sở hữu. */
}
```

Đây là **mẫu hook độc lập để giải thích**, không phải phần bắt buộc của ví dụ C mục 6.

Những lưu ý quan trọng:

- `JNI_OnUnload` được gọi khi **class loader chứa thư viện bị GC** trong những tình huống tương ứng, **không bảo đảm** chạy vào thời điểm Java `main` kết thúc hoặc JVM shutdown.
- Hook có thể được gọi trong **ngữ cảnh khó dự đoán**; đặc tả khuyến cáo sử dụng JNI services một cách thận trọng và tránh callback Java tùy ý.
- Nếu `JNI_OnLoad` cấp phát native resources mà sau đó thất bại trước khi trả phiên bản hợp lệ, **đừng trông chờ `JNI_OnUnload` luôn được gọi** để dọn các resource một phần. Hãy cleanup ngay đường lỗi trong chính `JNI_OnLoad`.
- Với native background threads, bảo đảm có cơ chế dừng/join/detach theo lifecycle độc lập. Đừng để thread tiếp tục gọi JNI qua `JavaVM*` sau khi VM kết thúc.

`JNI_OnLoad`/`JNI_OnUnload` là điểm gắn lifecycle; chúng **không thay thế** quy tắc sở hữu con trỏ, local/global references hoặc thread attachment.

## 10. Các lỗi thường gặp khi khai báo phiên bản JNI

| Hiện tượng hoặc sai lầm | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Trả `JNI_OK` từ `JNI_OnLoad` | Nhầm return code của `GetEnv` với mã phiên bản | Trả hằng `JNI_VERSION_*` hợp lệ sau khi xác nhận setup thành công |
| Trả `JNI_VERSION_1_8` trong binary chạy trên JVM quá cũ | Runtime không công nhận mức yêu cầu | Hạ yêu cầu **chỉ nếu thực sự không dùng API mới**, hoặc tăng minimum supported JVM |
| Trả `JNI_VERSION_1_1` nhưng dùng hàm JNI mới hơn | Khai báo không phản ánh phụ thuộc thực | Nâng phiên bản tối thiểu của thư viện |
| Không export symbol `JNI_OnLoad` | Thiếu `JNIEXPORT`/`JNICALL`, sai tên hoặc symbol C++ bị name mangling | Dùng `jni.h`, đúng chữ ký, thêm `extern "C"` khi viết C++ |
| Code native có `JNI_OnLoad` nhưng file build không được link vào thư viện | Thiếu object file trong linker input | Kiểm tra source/object được đóng vào `.so`/`.dll` |
| C compiler không nhận `JNI_VERSION_24` | Header `jni.h` quá cũ | Dùng JDK headers phù hợp, có kiểm thử tương thích với runtime đích |
| `GetEnv` trả `JNI_EVERSION` | JNI version được yêu cầu không được hỗ trợ | Đối chiếu hằng và mức runtime, xử lý thất bại |
| `GetEnv` trả `JNI_EDETACHED` | Thread hiện tại chưa attached | Attach thread theo đúng lifecycle nếu thực sự cần sử dụng JNI |
| `UnsatisfiedLinkError` khi `System.loadLibrary` | Có thể sai đường dẫn, architecture, dependency, version return hoặc symbol | Xem thông điệp thực tế, kiểm tra cả loader hệ điều hành lẫn JNI hook |
| Native method không tìm thấy sau khi load thành công | Tên exported JNI symbol hoặc chữ ký Java/C sai | Dùng `javac -h`, kiểm tra `nm`/`dumpbin` và tên class/package |
| Trả version cao nhất “cho chắc” | Làm mất tương thích không cần thiết | Dùng mức tối thiểu dựa trên API thật |
| Nghĩ Java 17 phải trả `JNI_VERSION_17` | Lẫn Java SE version và JNI API version | Đọc bảng `GetVersion` của đặc tả; JDK 17 trả JNI version 10 |
| Coi `JNI_OnLoad` là nơi có thể tự do gọi Java mọi lúc | Tại load còn hạn chế về context/class loader/exception | Chỉ setup cần thiết, kiểm tra lỗi, cân nhắc lazy initialization |
| Bỏ cleanup khi `JNI_OnLoad` thất bại | Resource cấp phát dở dang không được dọn | Dọn trước khi trả mã lỗi/unsupported version |

### 10.1. C++: bắt buộc tránh name mangling

C++ thường biến đổi tên symbol của hàm thành mã có thông tin overload/type. JVM cần **tên C chính xác `JNI_OnLoad`**. Vì thế nếu triển khai bằng C++, dùng:

```cpp
#include <jni.h>

extern "C" JNIEXPORT jint JNICALL
JNI_OnLoad(JavaVM* vm, void* reserved) {
    (void)vm;
    (void)reserved;
    return JNI_VERSION_1_6;
}
```

Đây là **hook C++ hợp lệ**, nhưng không có phương thức native của ứng dụng để chạy riêng. Khi viết trong file `.c` như mục 6, **không dùng `extern "C"`**, vì cú pháp ấy dành cho C++.

### 10.2. Chẩn đoán lỗi nạp thư viện theo đúng tầng

Khi `System.loadLibrary("jniversiondemo")` thất bại, có ít nhất ba tầng cần kiểm tra:

1. **Tìm thư viện chính:** đúng tên logic, tên file theo OS, thư mục `java.library.path`, quyền truy cập.
2. **Native OS loader:** đúng kiến trúc JVM/ABI, DLL/so/dylib hợp lệ, và các thư viện phụ thuộc có thể tải được.
3. **JNI loader:** đúng exported `JNI_OnLoad`, nhận `JavaVM*` hợp lệ, trả mã phiên bản được JVM hỗ trợ; sau load còn phải đúng exported native method names.

Hãy bắt đầu từ thông báo lỗi thực tế, không đoán rằng mọi `UnsatisfiedLinkError` là do yêu cầu JNI quá cao. Dùng `nm -D`/`objdump -T` trên Linux, `nm` trên macOS, `dumpbin /EXPORTS` trên Windows khi cần kiểm tra symbol. Công cụ và flags khác nhau theo nền tảng.

## 11. Chính sách tương thích cho thư viện phát hành thật

### 11.1. Xác định mức hỗ trợ tối thiểu trước khi build

Một thư viện phát hành cho nhiều phiên bản Java nên ghi rõ:

- **Minimum supported JDK/JVM** và kiến trúc/OS hỗ trợ.
- **Minimum JNI API version** (`JNI_VERSION_*`) dựa trên các hàm thật sự sử dụng.
- **JDK dùng để build native library** (để tìm đúng `jni.h`/architecture).
- **Native ABI/toolchain** và dependency hệ điều hành, vì JNI version đúng vẫn không cứu được binary sai hệ điều hành.

Nếu phát hành một binary cho nhiều JDK, kiểm thử **thực tế trên runtime thấp nhất** và một vài runtime cao hơn. Không chỉ chạy trên JDK mới nhất rồi suy đoán JVM cũ sẽ hiểu mã phiên bản do `jni.h` mới định nghĩa.

### 11.2. Khai báo theo nhu cầu, không theo “số phiên bản dự án”

Giả sử sản phẩm dùng Java 17 để phát triển, nhưng mã C chỉ dựa vào các JNI functions cũ. `JNI_OnLoad` có thể trả `JNI_VERSION_1_6`, dù ứng dụng Java source dùng Java 17, nếu mục tiêu của thư viện cho phép. Ngược lại, nếu C code thật sự dùng JNI 1.8 features, phải khai báo ít nhất `JNI_VERSION_1_8`, bất kể Java sources được viết bằng cú pháp cũ.

Trường hợp muốn hỗ trợ cả API cũ và mới theo runtime: cần thiết kế **fallback thực sự**. Một `JNI_OnLoad` trả mức tối thiểu, sau đó code chỉ gọi các hàm mới khi đã xác nhận runtime hỗ trợ. Không tự động cho rằng một phiên bản số cao hơn nghĩa là tất cả platform-specific features đều tồn tại.

### 11.3. Quyền native access trên JDK mới độc lập với version

Trong các JDK có chính sách native access hạn chế hơn, thao tác nạp/call JNI có thể phát cảnh báo hoặc đòi hỏi cấu hình `--enable-native-access`. Ví dụ với classpath trên JDK hỗ trợ:

```bash
java --enable-native-access=ALL-UNNAMED \
     -Djava.library.path=. JniVersionDemo
```

Dòng này **không tăng** phiên bản JNI mà VM hỗ trợ và **không sửa** mã return của `JNI_OnLoad`. Nó chỉ xử lý **quyền dùng native access** theo chính sách runtime. Với JDK 17, dùng lệnh chạy không có flag này ở mục 6.

JNI version cũng **không phải** version của Java Foreign Function & Memory API (FFM). FFM là một cách interop khác, có hợp đồng và điều kiện phiên bản riêng.

## 12. Câu hỏi tự kiểm tra

**1. Nếu thư viện động không khai báo `JNI_OnLoad`, JVM giả định JNI phiên bản nào?** Theo đặc tả, **`JNI_VERSION_1_1`**.

**2. Nạp trên JDK 17 có bắt buộc trả `JNI_VERSION_17` không?** Không. JDK 17 hỗ trợ nhiều phiên bản JNI cũ; `JNI_OnLoad` trả mức yêu cầu của thư viện. Bảng `GetVersion` ghi JDK 17 tương ứng `JNI_VERSION_10`.

**3. `GetEnv` trả `JNI_OK` thì có được trả lại ngay mã `JNI_OK` từ `JNI_OnLoad` không?** Không. `JNI_OK` chỉ là **mã trạng thái**; `JNI_OnLoad` phải trả **mã phiên bản** hợp lệ như `JNI_VERSION_1_6`.

**4. Vì sao ví dụ gọi `GetEnv(..., JNI_VERSION_1_6)` trước khi return `JNI_VERSION_1_6`?** Để xác nhận rằng luồng hiện tại lấy được interface JNI ở mức thư viện cần. Nếu không thành công, thư viện chủ động từ chối khởi tạo.

**5. Nếu JVM không công nhận mã `JNI_VERSION_*` trả về thì sao?** JVM **không chấp nhận việc nạp thư viện** và xử lý như thư viện chưa được nạp. Java có thể thấy lỗi nạp, thay vì gọi native method bình thường.

**6. `JNI_OnLoad_mylib` có thay được `JNI_OnLoad` trong ví dụ shared library không?** Không. `JNI_OnLoad_mylib` là mẫu hook **cho thư viện liên kết tĩnh tên mylib**; shared library động dùng tên cố định `JNI_OnLoad`.

**7. Vì sao không nên chọn JNI version cao nhất có trong header chỉ cho “an toàn”?** Vì JVM cũ có thể từ chối thư viện dù thư viện chẳng dùng API ở mức cao ấy. Khai báo tối thiểu giúp tương thích đúng phạm vi hỗ trợ.

**8. Trả `JNI_VERSION_1_6` có tự bảo đảm thư viện C tương thích Linux/Windows/macOS không?** Không. JNI API version chỉ là một trục tương thích; còn binary format, CPU architecture, ABI, loader paths và native dependencies.

## 13. Checklist trước khi giao một JNI library

1. Xác định chính xác các JNI functions thư viện cần và mức phiên bản đầu tiên hỗ trợ chúng.
2. Trong **shared library**, export `JNI_OnLoad(JavaVM*, void*)`, dùng `JNIEXPORT`/`JNICALL` và `extern "C"` nếu viết C++.
3. Trả một **`JNI_VERSION_*` được JVM công nhận**, không trả nhầm `JNI_OK`, Java version hoặc custom integer.
4. Nếu kiểm tra `GetEnv` trong `JNI_OnLoad`, kiểm tra cả `JNI_OK` và `JNIEnv*` trước khi dùng.
5. Dọn mọi resource khởi tạo dở dang trước khi trả lỗi; không ỷ lại `JNI_OnUnload`.
6. Biên dịch bằng header `jni.h` phù hợp và test JDK thấp nhất được hỗ trợ.
7. Kiểm tra `javac -h`, native symbols, architecture và file name cho từng OS.
8. Phân biệt **JDK version**, **JNI API version** và **native-access permission**.
9. Nếu dùng static JNI linking, áp dụng đúng `JNI_OnLoad_L` và mức JNI tối thiểu 1.8 theo đặc tả, không trộn với dynamic linking.
10. Xác minh `System.loadLibrary` thực sự thành công và native methods gọi được; theo dõi lỗi nạp và cleanup lifecycle.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — JNI Specification: Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_OnLoad`, `JNI_OnUnload`, `JNI_OnLoad_L`, `GetEnv` và quy tắc từ chối phiên bản không được công nhận.
- [Oracle Java 17 — JNI Functions: GetVersion](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): cách đọc version JNI runtime; bảng phiên bản JNI gắn với các bản Java SE.
- [Oracle Java 24 — JNI Functions: Version Constants](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html): các mã phiên bản `JNI_VERSION_1_1`, `JNI_VERSION_1_6`, `JNI_VERSION_1_8`, `JNI_VERSION_9`, `JNI_VERSION_10` và các mức mới.
- [Oracle Java 17 — System.loadLibrary](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#loadLibrary(java.lang.String)): đường nạp native library từ chương trình Java.
- [Oracle Java 17 — javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): tùy chọn `-h` sinh JNI native header.
- [OpenJDK — JEP 472](https://openjdk.org/jeps/472): hướng hạn chế native access đối với JNI trên các JDK hiện đại.