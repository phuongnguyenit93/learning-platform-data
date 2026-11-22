# Phân biệt tìm thư viện chính với tìm phụ thuộc động của hệ điều hành khi Java nạp native library

## 1. Vấn đề cần phân biệt

Khi ứng dụng Java gọi `System.loadLibrary("bridge")`, hai việc diễn ra nối tiếp:

1. **Tìm thư viện chính (top-level/native library):** Java/JVM xác định thư viện mà mã Java yêu cầu, ví dụ `libbridge.so` (Linux), `bridge.dll` (Windows), `libbridge.dylib` (macOS). Đây là phần mà `java.library.path`, `System.loadLibrary`, `System.load` và đôi khi `ClassLoader.findLibrary` liên quan trực tiếp.
2. **Tìm các phụ thuộc động (transitive/native dependencies):** bộ nạp liên kết động của **hệ điều hành** phải định vị và nạp các thư viện mà `libbridge.so`/`bridge.dll`/`libbridge.dylib` cần, chẳng hạn `libadder.so`. Những phụ thuộc này nằm trong metadata native của thư viện (ví dụ ELF `DT_NEEDED`, Mach-O load commands, PE import table), được giải quyết theo quy tắc riêng của Linux/macOS/Windows.

Hai bước có **bộ quy tắc tìm kiếm khác nhau**. Việc Java tìm thấy thư viện chính **không bảo đảm** hệ điều hành tìm được mọi phụ thuộc của thư viện đó.

Ví dụ:

```text
Java: System.loadLibrary("bridge")
            │
            ▼  [Bước 1: Java/JVM tìm thư viện chính]
       /opt/app/native/libbridge.so
            │
            ▼  [Bước 2: Linux dynamic loader đọc DT_NEEDED]
       cần: libadder.so
            │
          ┌─┴───────────────┐
          ▼                 ▼
   tìm được libadder.so    không tìm được
          │                 │
          ▼                 ▼
   nạp và liên kết      nạp libbridge.so thất bại
          │                 │
          ▼                 ▼
   JNI có thể chạy      UnsatisfiedLinkError
```

**Câu hỏi quan trọng khi debug:** “Không tìm thấy thư viện do Java yêu cầu, hay đã tìm được thư viện ấy nhưng hệ điều hành không tìm thấy một thư viện mà nó cần?”

## 2. Bước 1: Java/JVM tìm thư viện chính

### `System.loadLibrary(String libname)`

`System.loadLibrary("bridge")` nhận **tên logic**, không nhận tên file có tiền tố/hậu tố hoặc đường dẫn. Java/JVM thường ánh xạ tên đó thành tên native phù hợp nền tảng:

| Nền tảng | Tên logic | Tên file thường gặp |
| --- | --- | --- |
| Linux | `bridge` | `libbridge.so` |
| macOS | `bridge` | `libbridge.dylib` |
| Windows | `bridge` | `bridge.dll` |

Có thể quan sát quy tắc ánh xạ trên nền tảng đang chạy bằng `System.mapLibraryName("bridge")`. Đây là tên thư viện **chính** được yêu cầu; nó không cho biết tên hay vị trí các dependency của thư viện.

Đối với chương trình chạy trên JVM thông thường, `java.library.path` là thuộc tính chứa các thư mục JVM dùng để tìm thư viện native theo tên. Thiết lập ở thời điểm **khởi động Java**:

```bash
java -Djava.library.path=/opt/app/native -cp app.jar com.example.Main
```

Trong ví dụ này, Java tìm `bridge` theo cơ chế JVM, với thư mục `/opt/app/native` được chỉ định. `-Djava.library.path=...` phải đứng **trước tên lớp chính hoặc `-jar`**; đường dẫn được phân cách bằng ký tự phụ thuộc OS (`:` trên Linux/macOS, `;` trên Windows). Các Java module và ClassLoader tùy biến có thể đưa thêm quy tắc tìm kiếm vào luồng này; vì thế hãy hiểu `java.library.path` là **đầu vào cho cơ chế tìm native library của Java**, không phải một quy tắc linker thống nhất cho mọi hệ điều hành.

### `System.load(String filename)`

`System.load("/opt/app/native/libbridge.so")` (đối với ví dụ Linux) nhận **đường dẫn tuyệt đối** đến thư viện chính, nên tránh bước tìm tên logic trong `java.library.path`. Nhưng **bước 2 vẫn còn**: nếu `libbridge.so` cần `libadder.so`, việc `System.load` được đưa đường dẫn tuyệt đối **không tự cung cấp đường dẫn đến `libadder.so`**.

Tránh nhầm lẫn:

- `java.class.path`/`-cp` tìm **lớp Java/JAR**; không phải đường tìm `.so`/`.dll`.
- `java.library.path` phục vụ cơ chế tìm **thư viện native chính** do Java yêu cầu.
- `System.load` chỉ định đích thư viện chính bằng đường dẫn; không thay thế logic giải quyết dependency của OS.
- `System.setProperty("java.library.path", "...")` khi chương trình đã chạy **không phải cách đáng tin cậy** để thay đổi đường tìm nạp đã được JVM khởi tạo hoặc cache. Cấu hình từ lúc khởi động hoặc dùng `System.load` với đường dẫn xác định.

## 3. Bước 2: bộ nạp liên kết động của hệ điều hành tìm dependencies

Sau khi JVM đã xác định một thư viện và chuyển việc nạp cho API native của OS, **dynamic linker/loader** đọc các tham chiếu phụ thuộc trong binary:

- **Linux (ELF):** `DT_NEEDED` chứa tên các shared objects phụ thuộc. `ld.so`/`ld-linux` xử lý tìm kiếm và liên kết.
- **macOS (Mach-O):** các lệnh tải thư viện và *install name* quyết định thư viện cần nạp; `dyld` xử lý các đường dẫn `@loader_path`, `@rpath`, v.v.
- **Windows (PE):** import table và cơ chế DLL loader xác định các DLL phụ thuộc. Thứ tự tìm kiếm phụ thuộc cấu hình tiến trình, chính sách DLL và cách gọi `LoadLibrary`/`LoadLibraryEx`.

Dependency lại có thể cần **dependency của chính nó**. Thành công ở bước 1 không có nghĩa toàn bộ cây dependency đã hợp lệ, cùng kiến trúc, cùng ABI, hoặc đã được nạp.

### Đường tìm trên Linux (glibc, ELF)

Khi tên một dependency như `libadder.so` không mang đường dẫn cụ thể, linker xem xét nhiều nguồn theo quy tắc ELF/`ld.so`, bao gồm:

1. `DT_RPATH` cũ trên đối tượng liên quan, nếu không có `DT_RUNPATH` tương ứng (thứ tự và phạm vi được quy định cụ thể).
2. Biến môi trường `LD_LIBRARY_PATH` được cung cấp từ **trước khi chạy tiến trình** (có những chế độ an toàn như *secure execution* mà biến này bị bỏ qua).
3. `DT_RUNPATH` nhúng trong đối tượng cần dependency, áp dụng cho **các dependency trực tiếp** trong `DT_NEEDED` của đối tượng đó; dependency tầng sâu phải có đường tìm thích hợp riêng.
4. Cache `/etc/ld.so.cache` và các thư mục thư viện mặc định của hệ thống (có thể thay đổi theo distro, kiến trúc và cấu hình).

Một giá trị RUNPATH rất hữu ích khi đóng gói cạnh nhau:

```text
RUNPATH = $ORIGIN
```

Trong ELF, `$ORIGIN` được loader mở rộng thành **thư mục chứa chính tệp ELF đang tham chiếu**, chứ không phải mặc định thư mục làm việc hiện tại. Nhờ đó `libbridge.so` có thể tìm `libadder.so` đặt cạnh nó mà không cần đặt các thư viện vào thư mục hệ thống.

**Điểm dễ sai:** đặt `libbridge.so` và `libadder.so` cùng một thư mục, rồi chỉ thêm thư mục ấy vào `-Djava.library.path`, **không mặc nhiên** buộc Linux dynamic linker tìm dependency ở đó. Cơ chế Linux thường không tự tra thư mục của đối tượng vừa được nạp nếu thiếu `RUNPATH`/`RPATH` hoặc đường tìm OS tương ứng.

### Đường tìm trên macOS (dyld, Mach-O)

Thư viện thường mang *install name* và các tham chiếu chứa:

- `@loader_path`: thư mục của binary/image chứa tham chiếu đó.
- `@executable_path`: thư mục chứa file thực thi chính.
- `@rpath`: được giải theo các *runpath* phù hợp đã nhúng vào đối tượng/cây nạp.

Có thể xem tham chiếu dependency bằng `otool -L libbridge.dylib` và kiểm tra `LC_RPATH` bằng `otool -l`. Biến `DYLD_LIBRARY_PATH` có thể tác động việc tìm kiếm trong một số môi trường, nhưng các cơ chế bảo vệ của macOS như SIP, hardened runtime hoặc cách khởi chạy có thể hạn chế hay lọc biến môi trường `DYLD_*`. Trong ứng dụng phân phối, ưu tiên install name/runpath được đóng gói và ký hợp lệ thay vì trông đợi biến môi trường.

### Đường tìm trên Windows (DLL loader, PE)

`bridge.dll` có thể khai báo phụ thuộc `adder.dll`. Ngay cả khi ứng dụng dùng một **đường dẫn đầy đủ** để nạp `bridge.dll`, Windows vẫn có thể tìm `adder.dll` **theo tên module** dựa vào chính sách tìm DLL của tiến trình.

Đường tìm không chỉ là “thư mục cạnh DLL chính”: tùy loại ứng dụng và cách nạp, Windows có thể xét thư mục ứng dụng (`java.exe` hoặc executable ứng dụng), thư mục hệ thống, current directory, `PATH`, DLL đã nạp, Known DLLs, manifest/SxS, package graph hay các thư mục do API thiết lập. Thứ tự và tập thư mục thay đổi theo **Safe DLL Search Mode** và các cờ `LoadLibraryEx`/`LOAD_LIBRARY_SEARCH_*`. Chẳng hạn `LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR` có thể đưa thư mục chứa DLL đang nạp vào tìm kiếm **dependency**, nhưng không thể giả định mọi lời gọi nạp DLL đều dùng cờ đó.

Bởi vậy, thêm đường dẫn vào `-Djava.library.path` có thể giúp Java thấy `bridge.dll` mà **không khắc phục** việc Windows không thấy `adder.dll`. Khi cần chẩn đoán, xem import table bằng `dumpbin /DEPENDENTS bridge.dll` (Visual Studio Developer Command Prompt) và kiểm tra chính sách tìm DLL thực sự của tiến trình. Với ứng dụng sản xuất, dùng vị trí thư viện đã kiểm soát và cơ chế tìm kiếm an toàn; không tùy tiện đưa thư mục không tin cậy vào `PATH`.

## 4. Thí nghiệm Linux: thư viện chính tìm được nhưng dependency bị thiếu

Đây là một ví dụ JNI hoàn chỉnh trên **Linux x86-64 hoặc kiến trúc Linux tương thích**, với JDK 17+ và GCC. Ta chủ động tạo **hai thư viện**:

```text
NativeProbe.java
    │ System.loadLibrary("bridge")
    ▼
libbridge.so           ← thư viện JNI chính
    │ DT_NEEDED
    ▼
libadder.so            ← dependency native
    │
    ▼
int add_in_c(int, int)
```

### Bước A — Viết mã Java

Tệp `NativeProbe.java`:

```java
public final class NativeProbe {
    static {
        System.loadLibrary("bridge");
    }

    private static native int add(int a, int b);

    public static void main(String[] args) {
        System.out.println("7 + 5 = " + add(7, 5));
    }
}
```

Biên dịch Java đồng thời sinh JNI header:

```bash
javac -h . NativeProbe.java
```

Lệnh tạo `NativeProbe.class` và `NativeProbe.h`. `NativeProbe` ở default package nên JNI symbol có dạng `Java_NativeProbe_add`.

### Bước B — Viết dependency `libadder.so`

Tệp `adder.c`:

```c
int add_in_c(int a, int b) {
    return a + b;
}
```

Biên dịch thành shared library Linux, có SONAME rõ ràng:

```bash
gcc -fPIC -shared -Wl,-soname,libadder.so \
    -o libadder.so adder.c
```

### Bước C — Viết thư viện JNI chính `libbridge.so`

Tệp `bridge.c`:

```c
#include <jni.h>
#include "NativeProbe.h"

extern int add_in_c(int a, int b);

JNIEXPORT jint JNICALL Java_NativeProbe_add(
        JNIEnv *env, jclass clazz, jint a, jint b) {
    (void) env;
    (void) clazz;
    return (jint) add_in_c((int) a, (int) b);
}
```

Biên dịch `libbridge.so` và liên kết nó với `libadder.so`, **chưa cấu hình RUNPATH**:

```bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -L. -o libbridge.so bridge.c -ladder
```

`JAVA_HOME` cần trỏ đến thư mục JDK chứa `include/jni.h`; GCC có trong `PATH`. Thứ tự `bridge.c -ladder` giúp linker thấy ký hiệu `add_in_c` cần tìm. Kiểm tra metadata của **thư viện chính**:

```bash
readelf -d libbridge.so | grep NEEDED
```

Một dòng quan trọng trong kết quả sẽ mang nội dung:

```text
Shared library: [libadder.so]
```

Đó là **dependency của libbridge.so**, không phải thư viện được đặt trong `System.loadLibrary`. Kết quả `readelf` có thể có thêm các `NEEDED` tùy cách biên dịch.

### Bước D — Cố tình chỉ chỉ định đường tìm thư viện chính

Đứng tại thư mục chứa ba tệp nguồn, các tệp vừa biên dịch và hai shared libraries, chạy:

```bash
env -u LD_LIBRARY_PATH \
    java -Djava.library.path="$PWD" NativeProbe
```

Ta đã cung cấp đúng đường dẫn **chính**: Java có thể tìm `libbridge.so` trong `java.library.path`. Nếu `libadder.so` chưa được cài trong thư mục hệ thống, không có `RUNPATH` và không có cấu hình OS khác giúp tìm nó, chương trình **thường thất bại** với nguyên nhân tương tự:

```text
java.lang.UnsatisfiedLinkError: ... libadder.so: cannot open shared object file: No such file or directory
```

Thông điệp `...` ở đây chỉ lược bỏ đường dẫn/stack trace có thể khác nhau theo JDK và distro; đó là **mẫu lỗi minh họa**, không khẳng định dòng stderr sẽ y hệt. Điều đáng chú ý là **`libadder.so`**, không phải `libbridge.so`, được báo thiếu.

Nếu máy đã có `libadder.so` ở một vị trí được OS tìm kiếm, bước D có thể thành công; muốn tái hiện thất bại cần một môi trường thử nghiệm sạch và tên thư viện không bị trùng với bản đã cài.

### Bước E — Sửa bằng đường tìm của OS (thử nghiệm)

Trên Linux, truyền `LD_LIBRARY_PATH` cho **tiến trình Java ngay lúc khởi động**:

```bash
LD_LIBRARY_PATH="$PWD" \
    java -Djava.library.path="$PWD" NativeProbe
```

**stdout khi nạp và liên kết thành công:**

```text
7 + 5 = 12
```

Lệnh thành công vì hai cấu hình giải quyết **hai bước**: `-Djava.library.path` giúp JVM định vị `libbridge.so`, còn `LD_LIBRARY_PATH` cho dynamic linker một vị trí chứa `libadder.so`. Đây là cách chứng minh nguyên nhân hữu ích trong phát triển; không nên mặc định xuất thư mục tùy ý vào `LD_LIBRARY_PATH` trên mọi máy sản xuất.

### Bước F — Cách đóng gói bền hơn với `$ORIGIN`/RUNPATH

Thay vì phụ thuộc biến môi trường, tạo lại **chính `libbridge.so`** với GNU linker RUNPATH trỏ đến thư mục chứa nó:

```bash
gcc -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    -L. -Wl,--enable-new-dtags -Wl,-rpath,'$ORIGIN' \
    -o libbridge.so bridge.c -ladder
```

Kiểm tra `DT_NEEDED` và `RUNPATH` của thư viện được liên kết:

```bash
readelf -d libbridge.so | grep -E 'NEEDED|RUNPATH|RPATH'
```

Thông tin thiết yếu dự kiến gồm:

```text
Shared library: [libadder.so]
Library runpath: [$ORIGIN]
```

Nay có thể bỏ biến môi trường mà vẫn nạp được dependency đặt cạnh thư viện chính:

```bash
env -u LD_LIBRARY_PATH \
    java -Djava.library.path="$PWD" NativeProbe
```

**stdout:**

```text
7 + 5 = 12
```

`$ORIGIN` là ký hiệu được dynamic linker mở rộng; viết `-Wl,-rpath,'$ORIGIN'` với **nháy đơn** để shell không thay `$ORIGIN` thành biến môi trường của shell. `-Wl,--enable-new-dtags` yêu cầu linker GNU tạo kiểu tag mới (thường `DT_RUNPATH`). Quy tắc `RUNPATH` chỉ áp dụng cho dependency **trực tiếp** của đối tượng chứa tag; nếu `libadder.so` còn phụ thuộc vào thư viện khác đặt ở nơi riêng, cần giải quyết đường tìm tầng kế tiếp tương ứng.

### Câu chuyện của lỗi trong thí nghiệm

- Nếu xóa/đổi tên `libbridge.so` hoặc chỉ định sai `java.library.path`, Java không tìm được thư viện chính: thường gặp `no bridge in java.library.path`.
- Nếu `libbridge.so` tồn tại nhưng `libadder.so` không nằm trong đường tìm OS, JVM đã đi qua bước chọn thư viện chính nhưng **OS loader không hoàn tất việc nạp**: thường gặp tên `libadder.so` trong `UnsatisfiedLinkError`.
- Nếu cả hai đều được tìm thấy, các điều kiện khác như kiến trúc, ABI, symbol export và JNI method binding vẫn phải đúng. Hai bước tìm kiếm thành công **không đủ** để bảo đảm mọi phương thức native đều hoạt động.

Lưu ý phiên bản JDK: trên các JDK mới có chính sách **native access** chặt hơn, mã classpath sử dụng `System.loadLibrary` có thể cần tham số `--enable-native-access=ALL-UNNAMED` (hoặc khai báo native access theo module) nếu runtime cảnh báo/chặn. Ví dụ ở trên dùng JNI truyền thống và mô tả kết quả khi quyền native access được cho phép.

## 5. Bảng so sánh nhanh

| Câu hỏi | Tìm thư viện chính | Tìm dependency native |
| --- | --- | --- |
| Ai khởi xướng? | Java gọi `System.loadLibrary`/`System.load` hoặc thư viện Java thực hiện lời gọi | Native loader đọc import/dependency metadata từ binary |
| Tên đang tìm | `bridge` → `libbridge.so`/`bridge.dll`/`libbridge.dylib` | `libadder.so`/`adder.dll`/`libadder.dylib` và các thư viện phụ thuộc tiếp theo |
| Thành phần phụ trách | JVM/ClassLoader/native loading mechanism | `ld.so` (Linux), `dyld` (macOS), Windows DLL loader |
| Đường tìm/định vị chủ yếu | `java.library.path` cho `loadLibrary`, hoặc absolute path cho `load` | `LD_LIBRARY_PATH`/RUNPATH trên Linux; install names/`@rpath` trên macOS; DLL search policy trên Windows |
| Công cụ quan sát | `System.mapLibraryName`, `System.getProperty("java.library.path")`, thông điệp lỗi của JVM | `readelf`/`LD_DEBUG` (Linux), `otool` (macOS), `dumpbin` và công cụ loader (Windows) |
| Lỗi điển hình | “Không có bridge trong java.library.path” | “libadder.so cannot open”, “adder.dll was not found”, thiếu symbol/không khớp ABI |
| Cách khắc phục | Chỉ định đúng tên, thư mục hoặc absolute path của lib chính | Đóng gói đủ dependency và cấu hình tìm kiếm native đúng nền tảng |

## 6. Quy trình xử lý lỗi trong dự án thật

**Bước 1 — Đọc chính xác lỗi, xác định tên thư viện đang thiếu.**

- `UnsatisfiedLinkError: no bridge in java.library.path` thường cho thấy chưa định vị được **thư viện chính** theo tên logic.
- `UnsatisfiedLinkError: ... libadder.so: cannot open shared object file` thường cho thấy **dependency** đã được OS linker yêu cầu nhưng chưa tìm thấy.
- `wrong ELF class`, `bad CPU type`, `%1 is not a valid Win32 application` hoặc tương tự: có thư viện nhưng **không hợp định dạng/kiến trúc**.
- `undefined symbol`, `symbol not found` hoặc lỗi versioned symbol: có thư viện nhưng **không thỏa mãn symbol/ABI**.
- `java.lang.UnsatisfiedLinkError: ... native method ...` khi gọi phương thức JNI cũng có thể là **sai tên JNI symbol/signature**, khác với việc tìm đường dẫn thư viện.

`UnsatisfiedLinkError` là **nhóm lỗi**, không tự nói ra đó là bước 1 hay bước 2. Phải dựa vào tên thư viện và chi tiết từ loader.

**Bước 2 — Kiểm tra thư viện chính với Java.**

- In `System.mapLibraryName("bridge")` để xem tên file mong đợi trên OS hiện tại.
- In `System.getProperty("java.library.path")` hoặc kiểm tra tùy chọn `-D` lúc khởi động.
- Với `System.load`, kiểm tra đường dẫn **tuyệt đối**, quyền truy cập file, kiến trúc và loại binary.
- Đảm bảo `-Djava.library.path` đặt trước tên lớp chính trong câu lệnh khởi chạy và môi trường JVM/IDE/container đang thực sự dùng giá trị đó.

**Bước 3 — Liệt kê native dependencies.**

```bash
# Linux: liệt kê khai báo DT_NEEDED / DT_RUNPATH / DT_RPATH
readelf -d /opt/app/native/libbridge.so | grep -E 'NEEDED|RUNPATH|RPATH'

# Linux: hỏi dynamic linker thực sự tra thư viện ở đâu (output rất dài)
LD_DEBUG=libs java -Djava.library.path=/opt/app/native -cp app.jar com.example.Main
```

Với binary đã tin cậy, `ldd libbridge.so` cũng hữu ích để phát hiện thư viện “not found”; tránh sử dụng `ldd` tùy tiện với binary không tin cậy vì một số tình huống có thể gây thực thi mã.

```bash
# macOS: các thư viện được tham chiếu và metadata runpath
otool -L libbridge.dylib
otool -l libbridge.dylib
```

```bat
rem Windows, trong Visual Studio Developer Command Prompt
dumpbin /DEPENDENTS bridge.dll
```

Trên Windows, ProcMon hoặc công cụ phân tích dependency phù hợp cũng có thể hỗ trợ thấy các đường dẫn mà tiến trình thử truy cập; danh sách import tĩnh không luôn cho biết mọi thư viện được nạp động bằng `LoadLibrary`.

**Bước 4 — Xác nhận đúng kiến trúc, ABI và quyền.**

Kiểm tra 32/64 bit, CPU architecture, glibc/Visual C++ runtime, version/SO name, exported symbols, dependency lồng nhau và các hạn chế nạp thư viện của OS (quyền file, sandbox, code signing). File “có tồn tại” không đảm bảo “loader có thể sử dụng”.

**Bước 5 — Chọn cách khắc phục hợp lý theo nơi triển khai.**

- **Dev/Test:** cấu hình `java.library.path` cho thư viện chính; điều chỉnh đường tìm OS (`LD_LIBRARY_PATH` hoặc môi trường tương ứng) để xác định nhanh nguyên nhân.
- **Linux production:** đóng gói lib chính/phụ thuộc đúng bản và dùng `RUNPATH` tương đối `$ORIGIN` khi thích hợp; nhớ rằng mỗi tầng dependency cần đường tìm riêng.
- **macOS production:** gói Mach-O dependency với `@loader_path`/`@rpath` đúng và đáp ứng các yêu cầu ký, đóng gói của macOS.
- **Windows production:** bố trí DLL ở thư mục được loader tìm theo chính sách thực tế hoặc cấu hình API tìm DLL an toàn; tránh phụ thuộc `PATH` toàn hệ thống chứa thư mục không kiểm soát.
- **CI/Docker/Service:** truyền đầy đủ cả Java property và OS environment lúc khởi động, đúng OS/CPU; đừng chỉ kiểm tra file hiện diện trong source tree.

## 7. Những hiểu nhầm cần tránh

1. **“`-Djava.library.path` thêm vào là OS tự tìm được mọi DLL/`.so` phụ thuộc.”** Không đúng. Property này phục vụ nạp thư viện theo cơ chế Java; loader native có quy tắc riêng.
2. **“`System.load` bằng absolute path đảm bảo mọi dependency đều được giải.”** Không đúng. Nó định vị thư viện chính; dependency vẫn phải được OS loader giải quyết.
3. **“Hai file `.so` nằm cạnh nhau nên Linux luôn load được.”** Không đúng. Cần đường tìm loader phù hợp, ví dụ `RUNPATH=$ORIGIN`.
4. **“Windows luôn tìm dependency ngay cạnh DLL đã được load.”** Không thể mặc định như vậy; search mode và cờ nạp có ảnh hưởng.
5. **“`LD_LIBRARY_PATH` và `java.library.path` là một.”** Không đúng. Một bên là biến môi trường của dynamic loader trên Linux, một bên là Java system property.
6. **“Java có tìm thấy file là JNI chắc chắn gọi được.”** Không đúng. Kiến trúc, symbol export, ABI, access policy và signature JNI vẫn có thể sai.
7. **“Thêm mọi thư mục vào PATH/LD_LIBRARY_PATH là cách sửa tốt nhất.”** Cách đó có thể gây xung đột version và nguy cơ library preloading. Ưu tiên đóng gói rõ ràng, thư mục tin cậy và cơ chế load hạn chế phạm vi.

## 8. Bài tập tự kiểm tra

**Tình huống A:** `libbridge.so` nằm ở `/srv/app/native`, Java chạy với `-Djava.library.path=/srv/app/native`, và lỗi báo `libhelper.so: cannot open shared object file`. Bạn đang ở bước nào? **Bước 2**: Java đã đi đủ xa để nạp thư viện chính, nhưng OS chưa tìm được dependency `libhelper.so`. Hãy xem `DT_NEEDED` và `RUNPATH`, không chỉ thay `java.library.path`.

**Tình huống B:** Ứng dụng dùng `System.load("/srv/app/native/libbridge.so")` nhưng vẫn báo thiếu `libhelper.so`. Có mâu thuẫn không? **Không**: absolute path chỉ áp dụng cho `libbridge.so`; hãy kiểm tra cơ chế loader cho dependency.

**Tình huống C:** Hai `.so` đặt cạnh nhau và hoạt động khi đặt `LD_LIBRARY_PATH`, nhưng lỗi khi chạy như service. Vì sao? Có thể shell tương tác có cấu hình biến môi trường mà service không nhận được; hoặc thiếu `RUNPATH` thích hợp. So sánh environment lúc khởi động và metadata ELF, tránh giả định mọi cách khởi chạy dùng cùng biến.

## Tài liệu chính thức và cơ sở tra cứu

- [Java SE — `System.load` / `System.loadLibrary`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [JNI Specification — Loading and Linking Native Methods](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Linux `ld.so(8)`: dependency lookup, RPATH/RUNPATH, `$ORIGIN`](https://man7.org/linux/man-pages/man8/ld.so.8.html)
- [Linux `dlopen(3)`: thứ tự tìm shared object](https://man7.org/linux/man-pages/man3/dlopen.3.html)
- [Apple — Run-Path Dependent Libraries](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/RunpathDependentLibraries.html)
- [Microsoft — Dynamic-link library search order](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-search-order)
- [Microsoft — Dynamic-link library security](https://learn.microsoft.com/en-us/windows/win32/dlls/dynamic-link-library-security)
