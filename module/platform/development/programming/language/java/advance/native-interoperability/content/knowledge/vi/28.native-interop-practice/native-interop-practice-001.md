# Bài thực hành: tạo thư viện tính toán C và gọi cùng một hàm qua JNI rồi qua FFM

## Mục tiêu

Bài thực hành này xây dựng **một** thư viện native bằng C, bên trong có hàm tính toán `calc_multiply_add(a, b, c) = a × b + c`. Cùng hàm C đó được gọi từ Java theo **hai con đường**:

1. **JNI (Java Native Interface):** Java gọi `native` method; JNI bridge viết bằng C chuyển tiếp tới `calc_multiply_add`.
2. **FFM (Foreign Function & Memory API):** Java dùng `SymbolLookup` tìm symbol `calc_multiply_add` và `Linker.downcallHandle` để gọi thẳng vào địa chỉ hàm, không đi qua JNI bridge.

Sau bài này, bạn sẽ tự tạo file C và Java, dùng `javac -h` sinh JNI header, biên dịch một `.so`, chạy hai cách gọi trên **cùng bộ input**, giải thích được từng lớp liên kết, và xác minh kết quả bằng phép tính độc lập. Đây là bài thực hành về khả năng tương tác Java/native, không phải benchmark khẳng định JNI hay FFM luôn nhanh hơn.

**Môi trường của lệnh chạy:** Linux x86-64, JDK **25** và compiler C (GCC hoặc Clang), shell Bash. FFM API đã chính thức từ JDK 22; chọn JDK 25 để trình bày nhất quán các lớp `java.lang.foreign` và quyền native access. `int32_t` trong C và `jint`/`JAVA_INT` được ghép theo ABI của Linux x86-64. Khi đổi OS/CPU/ABI, cần kiểm tra lại layout và lệnh build.

## 1. Kiến trúc: chỉ có một hàm tính toán thật

Sơ đồ đường đi:

```text
NativeMathDemo.java
    |
    +-- computeViaJni(a,b,c) --------------------------+
    |       (Java native method)                       |
    |               |                                  |
    |          JNI bridge trong calc.c                 |
    |        Java_NativeMathDemo_computeViaJni         |
    |               |                                  |
    |               v                                  |
    |       calc_multiply_add(a,b,c) <-----------------+
    |               ^                                  |
    |               |                                  |
    +-- FFM: SymbolLookup -> Linker.downcallHandle ----+
                   symbol "calc_multiply_add"

Cùng thư viện native: libcalc.so
```

**Điểm cốt lõi:** JNI bridge chỉ là adapter; nó **không chứa công thức tính toán lần thứ hai**. FFM resolve đúng tên hàm C `calc_multiply_add` trong cùng `libcalc.so`. Do đó, khi sửa công thức ở hàm C, cả hai tuyến sẽ nhận cùng implementation sau khi biên dịch lại thư viện.

Cấu trúc thư mục lúc bắt đầu:

```text
jni-ffm-lab/
├── NativeMathDemo.java
└── calc.c
```

Sau khi build, thư mục sẽ có thêm `NativeMathDemo.class`, `NativeMathDemo.h` (do `javac -h` tạo) và `libcalc.so`. Không tự viết file `NativeMathDemo.h`, vì tên hàm/signature JNI nên lấy từ compiler Java.

## 2. Định nghĩa hợp đồng của hàm C

Chọn một chữ ký nhỏ, không có con trỏ và dễ quan sát:

```c
int32_t calc_multiply_add(int32_t a, int32_t b, int32_t c);
```

Ví dụ `calc_multiply_add(6, 7, 5)` trả `47`.

Lý do chọn ba `int32_t`:

- `jint` phía JNI là một số nguyên signed 32-bit; phía FFM, `ValueLayout.JAVA_INT` biểu diễn giá trị Java `int`.
- Trên Linux x86-64, C `int32_t` có cách truyền/nhận tương ứng với 32-bit integer theo ABI trong ví dụ; tránh việc đoán `long` C là 32 hay 64 bit.
- Không có chuỗi, mảng, memory allocation, con trỏ, arena hoặc callback nên tập trung vào việc **gọi cùng một function**, không bị phân tán sang các vấn đề quản lý native memory.

**Miền đầu vào:** các phép nhân và cộng phải có kết quả nằm trong khoảng signed 32-bit (−2.147.483.648 đến 2.147.483.647). **Signed integer overflow trong C là undefined behavior**; vì thế ví dụ không dùng số cực trị để “kiểm tra tràn”. Test bên Java dùng `Math.multiplyExact` và `Math.addExact` để xác nhận đầu vào an toàn.

## 3. Viết thư viện C chứa hàm chung và JNI bridge

Tạo tệp **`calc.c`** với nội dung đầy đủ:

```c
#include <stdint.h>
#include <jni.h>
#include "NativeMathDemo.h"

/* Export C symbol de FFM co the tra cuu theo ten. */
#if defined(_WIN32)
#define CALC_EXPORT __declspec(dllexport)
#else
#define CALC_EXPORT __attribute__((visibility("default")))
#endif

/*
 * HAM TINH TOAN DUY NHAT.
 * Tien dieu kien: a * b + c khong tran int32_t.
 */
CALC_EXPORT int32_t calc_multiply_add(
        int32_t a, int32_t b, int32_t c) {
    return a * b + c;
}

/*
 * Java native method -> JNI wrapper -> cung ham C ben tren.
 * JNI ten ham/chu ky khop voi file header javac -h sinh ra.
 */
JNIEXPORT jint JNICALL Java_NativeMathDemo_computeViaJni(
        JNIEnv *env, jclass clazz, jint a, jint b, jint c) {
    (void)env;   /* Demo khong can goi API qua JNIEnv*. */
    (void)clazz; /* Phuong thuc Java la static native. */

    return (jint)calc_multiply_add(
        (int32_t)a, (int32_t)b, (int32_t)c);
}
```

Giải thích:

- `CALC_EXPORT` làm symbol `calc_multiply_add` hiện diện trong bảng symbol xuất của thư viện chia sẻ. Nhờ vậy, FFM có thể tra cứu tên chính xác này. Macro được viết có nhánh Windows để nêu ý nghĩa export; lệnh build bên dưới dành riêng cho Linux.
- `JNIEXPORT` và `JNICALL` đến từ `jni.h`, cung cấp quy ước export/calling convention cho JNI. `Java_NativeMathDemo_computeViaJni` là tên entry point do JNI name-mangling quy định đối với class không có package và static native method không overload trong lab.
- `JNIEnv *env` và `jclass clazz` là tham số do JNI runtime đưa vào. Bridge không cần gọi JVM nên cố ý đánh dấu hai biến chưa dùng bằng `(void)`.
- `calc_multiply_add` **chỉ được định nghĩa một lần**. JNI bridge **gọi lại hàm này** thay vì tính `a * b + c` trong wrapper.
- FFM **không gọi** `Java_NativeMathDemo_computeViaJni`, mà gọi symbol `calc_multiply_add`. Hai đường đi có chung C core, nhưng entry point khác nhau.

Nếu đặt Java class trong package hoặc đổi tên method, tên JNI C entry point sẽ đổi. Khi đó chạy lại `javac -h`, mở header mới và cập nhật C code theo khai báo của header, thay vì đoán tên.

## 4. Viết chương trình Java: gọi cả JNI và FFM

Tạo tệp **`NativeMathDemo.java`** ở cùng thư mục:

```java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.invoke.MethodHandle;

import static java.lang.foreign.ValueLayout.JAVA_INT;

public final class NativeMathDemo {

    // JNI can wrapper Java_NativeMathDemo_computeViaJni trong calc.c.
    private static native int computeViaJni(int a, int b, int c);

    public static void main(String[] args) throws Throwable {
        // Nap DUNG MOT thu vien chia se cho ca JNI va FFM.
        System.loadLibrary("calc");

        // FFM: tim C core symbol trong thu vien vua nap.
        SymbolLookup lookup = SymbolLookup.loaderLookup();
        MemorySegment address =
                lookup.find("calc_multiply_add").orElseThrow();

        // C: int32_t calc_multiply_add(int32_t, int32_t, int32_t)
        // Java: int compute(int, int, int)
        Linker linker = Linker.nativeLinker();
        FunctionDescriptor signature = FunctionDescriptor.of(
                JAVA_INT,  // Gia tri tra ve
                JAVA_INT,  // a
                JAVA_INT,  // b
                JAVA_INT   // c
        );
        MethodHandle computeViaFfm =
                linker.downcallHandle(address, signature);

        int[][] samples = {
                {6, 7, 5},
                {-3, 4, 10},
                {0, 100, 5},
                {8, -2, -1}
        };

        for (int[] sample : samples) {
            int a = sample[0];
            int b = sample[1];
            int c = sample[2];

            // Oracle tinh bang Java: bao loi neu input gay tran int.
            int expected = Math.addExact(Math.multiplyExact(a, b), c);

            // Duong 1: Java -> JNI bridge -> calc_multiply_add.
            int jni = computeViaJni(a, b, c);

            // Duong 2: Java -> FFM downcall -> calc_multiply_add.
            // invokeExact bat buoc tham so int,int,int va ket qua int.
            int ffm = (int) computeViaFfm.invokeExact(a, b, c);

            if (jni != expected || ffm != expected) {
                throw new AssertionError(
                    "Mismatch: expected=" + expected
                        + ", JNI=" + jni + ", FFM=" + ffm);
            }

            System.out.printf(
                    "a=%d b=%d c=%d | JNI=%d | FFM=%d%n",
                    a, b, c, jni, ffm);
        }
        System.out.println("ALL MATCH");
    }
}
```

### Tại sao FFM code không cần JNI bridge?

`System.loadLibrary("calc")` nạp `libcalc.so` và liên kết thư viện với class loader đang gọi. `SymbolLookup.loaderLookup()` tìm các symbol trong những thư viện được nạp bằng `System.load` hoặc `System.loadLibrary` với class loader đó. Vì vậy `lookup.find("calc_multiply_add")` cho địa chỉ native của **C core**, còn `Linker.nativeLinker().downcallHandle(address, signature)` biến địa chỉ và mô tả ABI thành `MethodHandle` có thể gọi từ Java.

Trên JDK 25, `FunctionDescriptor.of(JAVA_INT, JAVA_INT, JAVA_INT, JAVA_INT)` đọc theo thứ tự **return type trước, ba argument type sau**. Handle bound vào `address` sẽ nhận ba `int` và trả `int`. `invokeExact` yêu cầu Java call-site khớp chính xác chữ ký handle; cast `(int)` thể hiện rõ loại kết quả, tránh nhầm lẫn do type adaptation.

Phương thức `System.loadLibrary` được dùng ở đây **chỉ để nạp cùng file thư viện cho cả hai tuyến**. Lời gọi tính toán FFM vẫn truy cập **trực tiếp** `calc_multiply_add`, không chạy qua wrapper JNI. Trong một chương trình chỉ dùng FFM, có thể thay cách nạp bằng `SymbolLookup.libraryLookup(path, arena)` và quản lý vòng đời thư viện với `Arena`; bài này chọn `loaderLookup` để hai tuyến dùng một file đã nạp duy nhất.

### Vì sao JNI code phải có Java `native` method?

Trong Java, `private static native int computeViaJni(...)` là khai báo entry point do JVM giải quyết. JVM tìm JNI wrapper tương ứng trong thư viện đã load rồi truyền `JNIEnv*`, `jclass` và các `jint` cho mã C. JNI wrapper tiếp tục gọi C core. Java không cần biết C core trong đường JNI, chỉ biết native method đã khai báo.

Ngược lại, FFM cần **địa chỉ symbol** và **mô tả signature**. API không tự dò ra kiểu tham số từ C binary; nếu khai báo sai `FunctionDescriptor` hoặc ABI, JVM có thể crash hoặc làm hỏng bộ nhớ. Vì vậy việc dùng đúng `JAVA_INT` và đúng thứ tự tham số là điều kiện an toàn, không chỉ vấn đề biên dịch.

## 5. Biên dịch và chạy từ đầu

Mở terminal Bash tại thư mục `jni-ffm-lab/` chứa hai source file. Đảm bảo `java` và `javac` trên `PATH` thuộc **cùng một JDK 25**.

### Bước 1: kiểm tra công cụ và xác định JDK home

```bash
java -version
javac -version
cc --version
JAVA_HOME="$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")"
test -f "$JAVA_HOME/include/jni.h"
```

Lệnh lấy `JAVA_HOME` phía trên dùng `readlink -f` của Linux để tìm thư mục JDK chứa `javac`. Nếu máy có nhiều JDK, hãy đặt `PATH` để cả `java` và `javac` trỏ đúng bản 25 trước khi chạy. `test -f` thành công nghĩa là header JNI tồn tại; nếu không, cần JDK đầy đủ thay vì chỉ Java runtime.

### Bước 2: sinh JNI header và Java class

```bash
javac -h . NativeMathDemo.java
```

Kết quả quan trọng là `NativeMathDemo.h`. Một phần khai báo header phải có dạng tương đương:

```c
JNIEXPORT jint JNICALL Java_NativeMathDemo_computeViaJni
  (JNIEnv *, jclass, jint, jint, jint);
```

Đây là **đoạn trích**, không phải nội dung đầy đủ của file header; giữ file do `javac -h` tạo, vì nó có include guard và phần khai báo cần thiết khác. Trong mã C của lab, `#include "NativeMathDemo.h"` giúp compiler phát hiện lỗi tên hoặc signature JNI ngay lúc build.

### Bước 3: biên dịch `calc.c` thành thư viện chia sẻ

```bash
cc -std=c11 -O0 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  calc.c -o libcalc.so
```

Ý nghĩa các tham số:

- `-fPIC -shared` tạo shared library dùng cho Linux.
- `-I"$JAVA_HOME/include"` và `-I"$JAVA_HOME/include/linux"` cho C compiler tìm `jni.h` cùng file header nền tảng.
- `-O0` giúp dễ debug và nhìn rõ đường gọi JNI bridge → C core khi dùng debugger; hiệu năng không phải mục tiêu của lab. Khi benchmark thật nên chọn cấu hình compiler phù hợp và giống môi trường triển khai.
- Kết quả là **một** file `libcalc.so` vừa chứa `Java_NativeMathDemo_computeViaJni` vừa chứa `calc_multiply_add`.

Có thể kiểm tra export trên Linux bằng lệnh sau (không bắt buộc):

```bash
nm -D --defined-only libcalc.so | grep -E 'calc_multiply_add|Java_NativeMathDemo_computeViaJni'
```

Bạn cần nhìn thấy **cả hai tên symbol**. Phần địa chỉ/loại symbol có thể khác nhau theo compiler, vì vậy không cố định toàn bộ output `nm`.

### Bước 4: chạy JVM có quyền native access

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. \
  -cp . NativeMathDemo
```

`--enable-native-access=ALL-UNNAMED` cấp quyền native access cho classpath code, phù hợp JDK 25 khi gọi API FFM restricted và dùng `System.loadLibrary`. `-Djava.library.path=.` chỉ nơi JVM tìm `libcalc.so`. Đặt các cờ **trước tên main class**; nếu đặt sau `NativeMathDemo`, chúng trở thành `args` ứng dụng.

**Stdout kỳ vọng chính xác** với JDK 25, Linux x86-64, thư viện và inputs như trên:

```text
a=6 b=7 c=5 | JNI=47 | FFM=47
a=-3 b=4 c=10 | JNI=-2 | FFM=-2
a=0 b=100 c=5 | JNI=5 | FFM=5
a=8 b=-2 c=-1 | JNI=-17 | FFM=-17
ALL MATCH
```

Giải thích nhanh:

- `6 × 7 + 5 = 47`.
- `-3 × 4 + 10 = -2`.
- `0 × 100 + 5 = 5`.
- `8 × -2 - 1 = -17`.

Chương trình **không chỉ kiểm tra JNI bằng FFM**; từng kết quả được so với một oracle tính bằng Java `Math.multiplyExact`/`Math.addExact`. Hai đường cùng dùng một C core, nên nếu core sai thì cả hai vẫn có thể **sai giống nhau**; việc so với oracle là quan trọng.

### Bước 5: sửa core để xác nhận hai tuyến dùng chung implementation

Sau khi chạy thành công, bạn có thể tạm đổi trong `calc.c`:

```c
return a * b + c + 1;  /* Chi la thu nghiem chung minh shared core */
```

Đây là **một dòng thay thế trong hàm `calc_multiply_add`**, không phải chương trình C độc lập. Biên dịch lại `libcalc.so` bằng lệnh ở Bước 3, rồi chạy chương trình Java ở Bước 4. Với chương trình test hiện tại, `AssertionError` sẽ xuất hiện vì **cả JNI lẫn FFM đều dùng kết quả mới, khác oracle Java**. Điều đó chứng minh hai tuyến quan sát cùng core và bộ test bắt lỗi thay đổi hợp đồng. Sau thí nghiệm, **khôi phục `return a * b + c;`**, biên dịch lại và chạy cho đến khi nhận đủ `ALL MATCH`.

## 6. So sánh cơ chế JNI và FFM trong đúng bài này

| Tiêu chí | JNI | FFM |
| --- | --- | --- |
| Điểm gọi Java | `computeViaJni(a,b,c)` được khai báo `native` | `computeViaFfm.invokeExact(a,b,c)` |
| Điểm vào native thực tế | `Java_NativeMathDemo_computeViaJni` | `calc_multiply_add` |
| Mã adapter C | **Cần** JNI wrapper trong lab | Không cần wrapper tính toán |
| Cách xác định tên | Quy tắc JNI mangling; sinh header bằng `javac -h` | Chuỗi symbol tên C và `SymbolLookup` |
| Chữ ký ở biên | Java `native` signature + `JNIEXPORT ... (JNIEnv*, jclass, ...)` | `FunctionDescriptor` + ABI C chính xác |
| Cơ chế giao tiếp | JNI gọi native qua JVM native-method dispatch | FFM tạo `MethodHandle` cho downcall |
| Thư viện và core | `libcalc.so` / `calc_multiply_add` | **Cùng `libcalc.so` / `calc_multiply_add`** |
| Lỗi cấu hình hay gặp | Không tìm thấy lib/JNI symbol, header sai | Không tìm được C symbol, descriptor sai, `WrongMethodTypeException` |
| Dữ liệu ví dụ | Ba số nguyên 32-bit | Cũng ba số nguyên 32-bit |

**JNI không mặc định “xấu” và FFM không mặc định “nhanh hơn”.** Với bài đơn giản, FFM giảm nhu cầu viết thêm wrapper JNI. Với API native phức tạp (struct, callback, string, mảng, ownership), phải hiểu ABI và vòng đời bộ nhớ; công cụ `jextract` có thể hỗ trợ tạo FFM binding từ C header. Việc chọn công nghệ dựa trên yêu cầu tích hợp, khả năng duy trì và benchmark đúng, không dựa vào một lần chạy `System.nanoTime()`.

## 7. Những điều cần hiểu về an toàn và đúng kiểu

### 7.1. Java `int`, JNI `jint`, C `int32_t` và FFM `JAVA_INT`

Trong lab, cả ba argument và return đều là integer 32-bit. Chữ ký JNI wrapper gồm ba `jint`; hàm C core gồm ba `int32_t`; descriptor FFM có **bốn** layout `JAVA_INT`: một cho return và ba cho arguments.

Đừng tự suy diễn rằng `JAVA_LONG` luôn tương đương C `long`. C `long` có thể khác kích thước theo nền tảng, trong khi Java `long` cố định 64-bit. Với JNI dùng `jlong`, còn với FFM cần chọn layout đúng ABI và kiểu C thật. Nếu đổi kiểu, phải sửa đồng thời core, Java native method, JNI wrapper, descriptor FFM và kiểm thử.

### 7.2. FFM không tự bảo vệ native code khỏi UB

Một `FunctionDescriptor` đúng giúp linker bố trí tham số phù hợp; nó không khiến phép toán C an toàn trước overflow, truy cập con trỏ sai, race hay lỗi memory của native code. Sai ABI/signature có thể gây crash JVM. Giữ việc tính toán C trong miền an toàn và kiểm thử riêng phần native.

### 7.3. Vòng đời và quyền truy cập

Lab này chỉ truyền các số nguyên nên **không cần** tạo `Arena`, `MemorySegment` data buffer, cấp phát hay giải phóng bộ nhớ native. `MemorySegment address` trong Java đại diện cho **địa chỉ hàm** do `SymbolLookup` tìm thấy, khác với buffer dữ liệu. `loaderLookup` gắn với thư viện được nạp bởi class loader; giữ cho code dùng handle/symbol trong lúc thư viện còn được nạp.

Nếu mở rộng sang `char*`, mảng, chuỗi, struct hoặc callback, cần học riêng cách cấp phát `Arena`, lifetime, thread ownership, encoding, layout, alignment và cách chuyển đổi dữ liệu. Không tùy tiện chuyển `byte[]` sang `ADDRESS` rồi nghĩ FFM đã sao chép hoặc pin mảng an toàn.

### 7.4. Khi đóng gói ứng dụng

JVM phải tìm được thư viện **đúng kiến trúc** và mọi dependent native library. `java.library.path` và `LD_LIBRARY_PATH` không phải cùng một cơ chế; cấu hình từ shell/system service, container và IDE có thể khác nhau. Khi đưa vào module path, thay `ALL-UNNAMED` bằng tên module thích hợp. Trên macOS thường build `libcalc.dylib`, còn Windows build `calc.dll` với JNI include cho `win32`; không áp dụng nguyên xi câu lệnh `cc -shared -fPIC ...` của Linux.

## 8. Tự chẩn đoán lỗi hay gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| `javac` báo không tồn tại `java.lang.foreign` | Đang dùng JDK cũ, hoặc compiler khác runtime | Chạy `javac -version`, dùng JDK 25 |
| Compiler C báo không tìm thấy `jni.h` | `JAVA_HOME` sai, thiếu JDK hoặc sai `-I` | Kiểm tra `"$JAVA_HOME/include/jni.h"`, `include/linux` |
| Compiler C báo không tìm thấy `NativeMathDemo.h` | Chưa chạy `javac -h . NativeMathDemo.java` | Sinh lại header trước khi build C |
| `UnsatisfiedLinkError: no calc in java.library.path` | Không thấy `libcalc.so`, tên/đường dẫn sai | Kiểm tra vị trí lib và `-Djava.library.path=.` |
| `UnsatisfiedLinkError` khi gọi `computeViaJni` | JNI entry point sai tên hoặc chưa export | Dùng header sinh tự động; kiểm tra symbol bằng `nm -D` |
| `NoSuchElementException` khi `lookup.find(...).orElseThrow()` | Thiếu export `calc_multiply_add` hoặc lookup sai class loader | Kiểm tra `CALC_EXPORT`, `nm -D`, `System.loadLibrary` chạy trước lookup |
| `WrongMethodTypeException` tại `invokeExact` | Descriptor hoặc kiểu call-site không khớp | Đối chiếu `(int,int,int)int`, cast `(int)` và `JAVA_INT` |
| Cảnh báo/native access bị từ chối | Thiếu cờ cho module gọi restricted method | Dùng `--enable-native-access=ALL-UNNAMED` cho classpath trên JDK 25 |
| Crash hoặc kết quả số bất thường | Sai ABI, function pointer, pointer/lifetime hoặc overflow C | Kiểm tra lại chữ ký native, giới hạn số, build debug/sanitizer; không coi crash là Java exception |
| Hai đường bằng nhau nhưng sai expected | Logic core thay đổi/hỏng | So với oracle Java, test các giá trị độc lập |

Nếu dùng JDK 25 và vẫn gặp lỗi, thu **đủ** lệnh biên dịch, lệnh chạy, `java -version`, `javac -version`, stderr và kết quả `nm -D`. Đừng sửa bằng cách đoán thêm `-Xcheck:jni` cho FFM: cờ này kiểm tra một số hợp đồng JNI, không xác nhận descriptor FFM.

## 9. Bài tập mở rộng có đáp án định hướng

**Bài 1 — Thêm input an toàn.** Thêm `{12, 3, 7}` vào `samples`. Kỳ vọng cả JNI và FFM trả `43`, và oracle Java cũng bằng `43`.

**Bài 2 — Phát hiện mismatch ở native core.** Đổi phép cộng `+ c` thành `- c` trong **một** hàm C, build lại và chạy. Kỳ vọng chương trình ném `AssertionError` ở input đầu, bởi cả JNI và FFM dùng core đã đổi nhưng oracle vẫn kiểm tra `a * b + c`. Khôi phục code gốc sau thí nghiệm.

**Bài 3 — Thử lỗi FFM lookup có kiểm soát.** Đổi chuỗi tìm symbol thành `"missing_symbol"` nhưng giữ `calc.c` nguyên. Kỳ vọng `NoSuchElementException` khi `orElseThrow()` chạy; chưa có downcall native nào được tạo. Khôi phục tên `"calc_multiply_add"`.

**Bài 4 — Phân tích JNI bridge.** Vì sao không viết `return (jint)(a * b + c);` ngay trong JNI wrapper?  
**Gợi ý:** Khi đó có **hai implementation** có thể lệch nhau sau chỉnh sửa; bài yêu cầu một core duy nhất được cả JNI và FFM gọi.

**Bài 5 — Nêu hạn chế test.** Vì sao `JNI == FFM` chưa đủ chứng minh kết quả đúng?  
**Gợi ý:** Hai đường cùng gọi C core; một lỗi chung sẽ cho kết quả sai giống nhau. Cần oracle độc lập hoặc bộ test được tính trước và so sánh với hợp đồng.

## 10. Checklist hoàn thành bài thực hành

- [ ] Hai source file đầy đủ: `NativeMathDemo.java` và `calc.c`.
- [ ] `calc.c` chứa **chính xác một** implementation `calc_multiply_add` và JNI wrapper chuyển tiếp vào đó.
- [ ] `javac -h . NativeMathDemo.java` sinh `NativeMathDemo.h`; C code include đúng header.
- [ ] `libcalc.so` export cả `calc_multiply_add` và `Java_NativeMathDemo_computeViaJni`.
- [ ] Chạy bằng JDK 25 với `--enable-native-access=ALL-UNNAMED` và đường dẫn thư viện đúng.
- [ ] `JNI` nhận cùng input với `FFM`, FFM tìm symbol qua `loaderLookup` rồi gọi `downcallHandle`.
- [ ] Mỗi đường được đối chiếu với oracle `Math.multiplyExact`/`Math.addExact`.
- [ ] Stdout đủ bốn dòng kiểm thử và `ALL MATCH`, không có JNI/FFM lookup hay linkage error.
- [ ] Hiểu vì sao Java `int`, JNI `jint`, FFM `JAVA_INT` và C `int32_t` khớp ở môi trường lab.
- [ ] Khi thay C core để thử nghiệm, khôi phục code rồi build lại thư viện và chạy lại.

## Tài liệu tham khảo

- Oracle JDK 25 — `Linker`: downcall method handles và yêu cầu descriptor/ABI: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html
- Oracle JDK 25 — `SymbolLookup`: `loaderLookup` tìm symbol từ thư viện nạp bằng `System.loadLibrary`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/SymbolLookup.html
- Oracle JDK 25 — `FunctionDescriptor` và `ValueLayout`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html và https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/ValueLayout.html
- Oracle JDK 25 — restricted methods và cách bật native access: https://docs.oracle.com/en/java/javase/25/core/restricted-methods.html
- Oracle JNI Specification — native methods và `JNIEnv`: https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html
- Oracle `javac` — `-h` sinh native header: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html
- OpenJDK JEP 454 — FFM API được final trong JDK 22: https://openjdk.org/jeps/454
