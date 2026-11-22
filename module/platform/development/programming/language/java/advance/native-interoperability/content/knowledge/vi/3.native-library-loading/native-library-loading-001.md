# Thư viện động .dll, .so, .dylib và kiến trúc của tiến trình Java

## 1. Thư viện động là gì và vì sao Java cần đến chúng?

Một chương trình Java thông thường biên dịch mã nguồn `.java` thành bytecode `.class`, rồi JVM tải lớp, kiểm tra bytecode và thực thi bằng interpreter/JIT. Tuy nhiên, một số chức năng cần mã máy riêng của hệ điều hành hoặc phần cứng: gọi thư viện C/C++, driver, API hệ điều hành, thuật toán native đã có sẵn hay tích hợp với phần mềm khác. Khi đó, Java có thể gọi **thư viện động (dynamic/shared library)** thông qua một cơ chế liên kết với mã native, điển hình là **JNI (Java Native Interface)**.

Thư viện động là tệp mã máy có thể được bộ nạp thư viện của hệ điều hành ánh xạ vào không gian địa chỉ của tiến trình đang chạy. Khác với `.jar` chứa class/bytecode Java, tệp native đã được biên dịch cho **một hệ điều hành, kiến trúc CPU và ABI cụ thể**. Đổi đuôi `.so` thành `.dll` không thể biến mã Linux thành mã Windows.

Một số điểm cần phân biệt ngay:

- **JAR**: nơi đóng gói class/resource Java; JVM/class loader hiểu cấu trúc và bytecode.
- **Thư viện động**: mã máy và các ký hiệu (symbol) native; **OS dynamic loader** nạp, sau đó JVM hoặc cầu nối native sử dụng.
- **JNI**: hợp đồng giữa Java và mã native, gồm kiểu dữ liệu `jint`, đối tượng `JNIEnv`, tên hàm/đăng ký phương thức và cách chuyển dữ liệu.
- **Tiến trình Java**: tiến trình hệ điều hành đang chứa JVM. Thư viện native được nạp vào **chính tiến trình này**, không tự động trở thành một tiến trình riêng.

## 2. Ba định dạng phổ biến: DLL, SO và DYLIB

| Hệ điều hành | Định dạng nhị phân thường gặp | Đuôi thư viện động | Tên ví dụ cho thư viện logic `nativecalc` | Ghi chú |
|---|---|---|---|---|
| Windows | PE/COFF | `.dll` | `nativecalc.dll` | Windows loader giải quyết DLL và các DLL phụ thuộc. |
| Linux | ELF | `.so`, đôi khi có phiên bản như `.so.1` | `libnativecalc.so` | `ld.so`/dynamic linker xử lý `DT_NEEDED`, `SONAME`, đường dẫn tìm thư viện. |
| macOS | Mach-O | `.dylib` | `libnativecalc.dylib` | `dyld` giải quyết thư viện; thường gặp `@rpath`, `@loader_path`, `@executable_path`. |

Tên ở bảng là **quy ước điển hình**; một thư viện có thể có tên, version và symlink khác. Java cung cấp `System.mapLibraryName("nativecalc")` để lấy tên tệp native theo nền tảng, nhưng việc tìm được một tệp mang tên phù hợp chưa bảo đảm nó tương thích hoặc tất cả dependency đều tồn tại.

**Biên dịch khác nạp (load):** compiler/linker tạo thư viện với định dạng và ABI cụ thể; khi chương trình chạy, OS loader mới ánh xạ thư viện vào tiến trình và xử lý các phụ thuộc. Trên Linux, `libfoo.so` thường là tên để liên kết hoặc tải, trong khi tên vận hành thực tế có thể mang version (`libfoo.so.2`). Trên macOS, một thư viện có thể chứa nhiều *architecture slice* (universal binary), nhưng vẫn phải có slice tương thích với tiến trình.

## 3. Thư viện nằm ở đâu trong kiến trúc tiến trình Java?

Sơ đồ khái niệm (các vùng không nhất thiết liên tục hoặc có kích thước cố định):

~~~text
Hệ điều hành
└── Tiến trình "java" (một PID, một không gian địa chỉ ảo)
    ├── JVM/HotSpot runtime
    │   ├── Java heap (đối tượng Java)
    │   ├── Metaspace, code cache/JIT và cấu trúc JVM
    │   └── Các Java thread và ngăn xếp liên quan
    ├── Native memory, ngăn xếp native, tài nguyên hệ điều hành
    ├── Các thư viện hệ thống mà tiến trình sử dụng
    └── Thư viện native của ứng dụng
        ├── nativecalc.dll        (Windows) HOẶC
        ├── libnativecalc.so      (Linux)   HOẶC
        └── libnativecalc.dylib   (macOS)
~~~ 

Khi Java gọi phương thức `native`:

1. Luồng đang thực thi Java đi qua ranh giới JNI (hoặc cơ chế giao tiếp native tương ứng).
2. JVM chuyển tham số theo hợp đồng JNI và điều khiển vào hàm mã máy đã được ánh xạ trong **cùng tiến trình**.
3. Hàm native có thể dùng CPU, vùng nhớ native, API hệ điều hành hoặc gọi tiếp các thư viện khác.
4. Hàm trả kết quả/ngoại lệ theo giao thức cầu nối; luồng tiếp tục chạy mã Java.

Thư viện dùng chung không có nghĩa là vùng nhớ được tự động chia sẻ giữa **các tiến trình**. Mỗi tiến trình có không gian địa chỉ ảo riêng; hệ điều hành có thể chia sẻ các trang mã chỉ đọc ở mức vật lý, nhưng con trỏ bộ nhớ của tiến trình này không thể tùy ý sử dụng ở tiến trình khác.

**Hệ quả an toàn rất quan trọng:** mã native không được JVM bảo vệ như bytecode Java. Truy cập con trỏ sai, ghi tràn bộ nhớ, lỗi đồng bộ hay ABI sai có thể làm **toàn bộ tiến trình Java** bị crash (ví dụ SIGSEGV/Access Violation). Java GC quản lý đối tượng Java, nhưng không tự động giải phóng mọi vùng nhớ do C/C++ cấp phát.

## 4. “Đúng hệ điều hành” vẫn chưa đủ: CPU, bitness, ABI và dependency

Một thư viện chỉ có thể tải thành công khi **bộ nạp hệ điều hành và tiến trình** hiểu được nhị phân đó.

| Yếu tố | Cần khớp/cần kiểm tra | Lỗi điển hình |
|---|---|---|
| Hệ điều hành và định dạng | Windows/PE, Linux/ELF, macOS/Mach-O | Đưa `.dll` Windows sang Linux mà không có môi trường tương thích không thể tải như `.so`. |
| Kiến trúc lệnh CPU (ISA) | `x86_64`/`amd64`, `aarch64`/`arm64`, `x86`… | JVM ARM64 không tải được thư viện chỉ chứa mã máy x86_64 thông thường. |
| Độ rộng tiến trình | JVM 64-bit cần thư viện native 64-bit đúng kiến trúc | JVM 64-bit không tải trực tiếp DLL/SO 32-bit. |
| ABI và symbol | Calling convention, tên hàm xuất ra, kiểu dữ liệu, runtime C/C++, JNI signature | `undefined symbol` hoặc không tìm thấy native method dù đã tìm được tệp. |
| Thư viện phụ thuộc | `libc`, runtime C++, DLL/SO/DYLIB khác, version tương thích | Tệp chính tồn tại nhưng loader báo thiếu dependency hoặc version. |
| Ràng buộc môi trường | Phiên bản hệ điều hành, chính sách ký mã/quyền truy cập, đường dẫn loader | Bị chặn load dù đường dẫn và kiến trúc đúng. |

Ví dụ: máy Linux 64-bit chạy được cả ứng dụng 32-bit nếu được hỗ trợ không có nghĩa **JVM 64-bit** có thể nạp `libfoo.so` 32-bit. Thư viện được tải *vào tiến trình JVM hiện tại*, do đó phải tương thích với kiến trúc/ABI của tiến trình, không chỉ với CPU vật lý. Trên macOS Apple Silicon, cần xem JVM đang chạy bản arm64 hay x86_64 (qua cơ chế dịch tương thích) rồi chọn slice phù hợp.

ABI (Application Binary Interface) quy định cách truyền đối số, giá trị trả về, tổ chức dữ liệu và quy ước gọi hàm ở mức máy. Cùng tên hàm và cùng mã nguồn C/C++ chưa chắc tạo ra nhị phân có thể hoán đổi giữa những hệ thống khác nhau. C++ còn có cơ chế *name mangling* và khác biệt ABI theo compiler; khi xây cầu nối JNI, nên dựa vào header do `javac -h` sinh ra để khai báo symbol đúng.

## 5. Quá trình nạp từ Java đến OS loader

Với JNI và lời gọi `System.loadLibrary("nativecalc")`, có thể hình dung trình tự:

1. JVM thực thi lệnh nạp khi class tương ứng khởi tạo (nếu đặt trong khối `static`) hoặc lúc ứng dụng gọi chủ động.
2. Cơ chế nạp native của JVM tìm ứng viên theo tên logic và đường dẫn tìm kiếm phù hợp (`java.library.path`, cùng những quy tắc riêng của JVM/hệ điều hành).
3. OS loader kiểm tra định dạng nhị phân, kiến trúc, quyền truy cập; ánh xạ các đoạn mã/dữ liệu và xử lý relocation, dependency, symbol khi cần. Một số symbol có thể được liên kết muộn.
4. Nếu có hàm `JNI_OnLoad`, JVM có thể gọi hàm này theo hợp đồng JNI để khởi tạo/đăng ký. **Hàm này là tùy chọn**, không phải mọi JNI library đều cần.
5. JVM kết nối phương thức `native` trong Java với entry point tương ứng (theo quy tắc tên JNI hoặc `RegisterNatives`). Sau đó lời gọi Java có thể chuyển vào mã native.

Đây là hai phép nạp thông dụng:

~~~java
System.loadLibrary("nativecalc");  // Tên logic, KHÔNG kèm lib/.dll/.so/.dylib
System.load("/duong/dan/tuyet/doi/libnativecalc.so"); // Đường dẫn tuyệt đối tới tệp
~~~

Các dòng trên **minh họa API**, không phải một chương trình độc lập và đường dẫn `System.load` là ví dụ kiểu Unix. `System.loadLibrary` không nhận đường dẫn tệp bất kỳ như `./libnativecalc.so`; `System.load` nhận tên tệp đầy đủ bằng đường dẫn tuyệt đối. Cả hai có thể thất bại nếu thư viện phụ thuộc không tìm thấy.

**Phân biệt hai lớp đường dẫn:**

- `java.library.path` giúp **JVM tìm thư viện JNI đầu tiên** theo cơ chế của JVM. Chỉ định ngay khi khởi động, ví dụ `java -Djava.library.path=/opt/app/native ...`. Đừng dựa vào `System.setProperty("java.library.path", ...)` sau khi JVM đã chạy để thay đổi cơ chế tìm kiếm.
- **Đường dẫn tìm dependency của OS loader** có thể khác: `PATH` và quy tắc Windows DLL search; `LD_LIBRARY_PATH`, `RUNPATH`/`RPATH`, cache loader trên Linux; `@rpath`/`@loader_path` và chính sách `dyld` trên macOS. `java.library.path` không tự giải quyết tất cả thư viện phụ thuộc lồng nhau.

Khi triển khai, ưu tiên đặt thư viện tại vị trí rõ ràng và cấu hình tìm kiếm có kiểm soát. Trên Windows cần lưu ý thứ tự tìm DLL để tránh nạp nhầm tệp cùng tên; trên macOS một số biến môi trường `DYLD_*` có thể bị hạn chế bởi chính sách bảo mật (chẳng hạn SIP), nên không coi chúng là giải pháp phổ quát.

## 6. Thực hành JNI: Java gọi hàm cộng trong thư viện native

Ví dụ này minh họa trọn đường đi **Java → JNI → C → Java**, chạy trên Java 17+ với **JDK**, C compiler phù hợp và thư viện được biên dịch **trên chính nền tảng đang chạy**. Tạo hai tệp trong cùng một thư mục, không khai báo `package` để tên JNI dễ quan sát.

**Bước 1 — `NativeCalc.java`:**

~~~java
public class NativeCalc {
    static {
        System.loadLibrary("nativecalc");
    }

    private native int add(int left, int right);

    public static void main(String[] args) {
        NativeCalc calculator = new NativeCalc();
        System.out.println("3 + 4 = " + calculator.add(3, 4));
    }
}
~~~

Từ khóa `native` khai báo phương thức do mã ngoài JVM triển khai. Khối `static` yêu cầu nạp thư viện khi `NativeCalc` được khởi tạo; nếu không nạp được, chương trình không đến được lời gọi `add`.

**Bước 2 — Sinh header JNI từ JDK:**

~~~bash
javac -h . NativeCalc.java
~~~

Lệnh này tạo `NativeCalc.class` và `NativeCalc.h`. Header sinh ra khai báo hàm tương ứng với phương thức instance `add(int, int)`, dạng khái niệm:

~~~c
JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *, jobject, jint, jint
);
~~~

`JNIEnv *` là giao diện JNI cho luồng gọi, `jobject` đại diện đối tượng `this`, hai `jint` là đối số Java `int`. Nếu đổi phương thức thành `static native`, tham số tham chiếu thứ hai là `jclass` thay vì `jobject`.

**Bước 3 — `nativecalc.c` (mã C):**

~~~c
#include "NativeCalc.h"

JNIEXPORT jint JNICALL Java_NativeCalc_add(
    JNIEnv *env, jobject receiver, jint left, jint right
) {
    (void) env;
    (void) receiver;
    return left + right;
}
~~~

Tên hàm và kiểu phải theo header do JDK tạo; không tự sửa signature theo cảm tính. Đây là C thuần; với C++ cần lưu ý name mangling/`extern "C"` theo hợp đồng trong header JNI. Ví dụ chỉ cộng hai số nhỏ để không gặp khác biệt về tràn số nguyên có dấu giữa C và Java.

**Bước 4 — Biên dịch thư viện cho hệ điều hành tương ứng.** Các lệnh dưới đây là **ba lựa chọn thay thế**, không chạy cả ba. `JAVA_HOME` phải trỏ đến JDK chứa thư mục `include`; Windows dùng *Developer Command Prompt for Visual Studio* có lệnh `cl`.

Linux (GCC):

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  nativecalc.c -o libnativecalc.so
java -Djava.library.path=. NativeCalc
~~~

macOS (Clang):

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
  nativecalc.c -o libnativecalc.dylib
java -Djava.library.path=. NativeCalc
~~~

Windows (MSVC, trong **Developer Command Prompt**, cú pháp biến môi trường của `cmd.exe`):

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativecalc.c /Fe:nativecalc.dll
java -Djava.library.path=. NativeCalc
~~~

**Kết quả stdout của chương trình Java khi build/load thành công trên mỗi nền tảng:**

~~~text
3 + 4 = 7
~~~

Với cách đặt tên này, `System.loadLibrary("nativecalc")` chọn `nativecalc.dll` trên Windows, `libnativecalc.so` trên Linux, và `libnativecalc.dylib` trên macOS. `-Djava.library.path=.` được đặt **trước** tên class để JVM tìm thư viện tại thư mục hiện hành. Trong sản phẩm thật, nên dùng thư mục native cụ thể và cấu hình rõ ràng thay vì phụ thuộc thư mục hiện hành.

**Điều gì diễn ra khi chạy?** Java gọi `add(3, 4)`; JNI chuyển hai `int` thành `jint` và gọi `Java_NativeCalc_add` trong thư viện đã load; C trả về 7; JVM chuyển kết quả về Java để in. Đây là một luồng gọi đồng bộ trong cùng tiến trình, không có IPC/network và không sinh tiến trình C riêng.

## 7. Chẩn đoán lỗi nạp thư viện

Phân biệt **không tìm thấy tệp**, **tệp sai kiến trúc**, **thiếu dependency**, và **sai symbol JNI**. Tất cả có thể xuất hiện dưới dạng `UnsatisfiedLinkError` nhưng cách xử lý khác nhau.

| Triệu chứng | Khả năng chính | Kiểm tra/khắc phục |
|---|---|---|
| `no nativecalc in java.library.path` | JVM chưa tìm được thư viện chính | Kiểm tra tên logic, tên tệp, thư mục thực tế và `-Djava.library.path`. |
| `wrong ELF class: ELFCLASS32` hoặc báo sai machine type | Bitness/CPU architecture không khớp với JVM | Đọc kiến trúc của Java process và binary; build lại cho đúng target. |
| `cannot open shared object file` hoặc “module not found” dù tệp chính tồn tại | Thiếu thư viện phụ thuộc, sai đường dẫn OS loader | Kiểm tra dependency và runtime loader path, không chỉ `java.library.path`. |
| `undefined symbol` hoặc lỗi thiếu entry point | ABI/symbol/dependency version không tương thích | Kiểm tra exported symbol, C++ mangling, JNI header, phiên bản thư viện. |
| Native method declared nhưng chưa được liên kết | Hàm JNI sai tên/signature hoặc thiếu `RegisterNatives` | Sinh lại header bằng `javac -h` và export đúng hàm. |
| Crash JVM (SIGSEGV/Access Violation) khi đang gọi native | Lỗi con trỏ, bộ nhớ, thread, dữ liệu/ABI | Kiểm tra mã native, crash log `hs_err_pid...log` nếu có, native debugger. |

Các lệnh hỗ trợ quan sát:

~~~bash
java -version
java -XshowSettings:properties -version
# Xem phiên bản JVM, os.arch, java.library.path...
~~~

Linux:

~~~bash
file libnativecalc.so
readelf -h libnativecalc.so
readelf -d libnativecalc.so
ldd libnativecalc.so
~~~

macOS:

~~~bash
file libnativecalc.dylib
lipo -info libnativecalc.dylib
otool -L libnativecalc.dylib
~~~

Windows (Developer Command Prompt):

~~~bat
dumpbin /HEADERS nativecalc.dll
dumpbin /DEPENDENTS nativecalc.dll
~~~

`file`/`readelf -h` cho biết dạng và kiến trúc ELF; `readelf -d`/`ldd` xem dependency trên Linux. `otool -L` xem các liên kết Mach-O; `lipo -info` cho biết slice kiến trúc. `dumpbin` xem PE headers và DLL phụ thuộc. Đọc kết quả theo **kiến trúc JVM thực tế**, không chỉ theo tên OS hoặc CPU của máy.

Nếu lỗi phát sinh ngay trong khối `static`, việc tải class có thể thất bại trước khi `main` thực hiện lệnh ứng dụng. Log đầy đủ gồm nguyên nhân sâu bên dưới, tên thư viện phụ thuộc và kiến trúc nhị phân hữu ích hơn việc thay đổi ngẫu nhiên các biến đường dẫn.

## 8. Đóng gói, phân phối và bảo trì

Thư viện native **không tự động được load chỉ vì có mặt bên trong JAR**. Khi phát hành ứng dụng chạy trên nhiều nền tảng:

1. Build **binary phù hợp từng hệ điều hành/kiến trúc** (ví dụ Linux x86_64, Linux arm64, Windows x64, macOS arm64) bằng toolchain được hỗ trợ. Cân nhắc tương thích `glibc`/`musl`, runtime C/C++ và minimum OS version.
2. Phân phối native binaries dưới cấu trúc xác định, ví dụ `native/linux-x86_64/`, `native/windows-x86_64/`. Chọn đúng tệp theo môi trường runtime đã kiểm tra, không chỉ nhìn tên thư mục.
3. Đặt thư viện ở đường dẫn có thể được JVM/OS loader truy cập. Nếu cần trích thư viện từ JAR ra filesystem trước khi nạp, phải quản lý vị trí, quyền truy cập, tính toàn vẹn và vòng đời file cẩn thận.
4. Quản lý dependency và version của thư viện native cùng với artifact Java; kiểm thử trên hệ thống thực tế. Chữ ký/kiểm tra checksum và nguồn binary đáng tin giúp tránh nạp mã ngoài ý muốn.
5. Thiết kế ranh giới JNI rõ ràng: chuyển chuỗi/mảng/buffer đúng kiểu, giải phóng resource native, không giữ con trỏ hoặc JNI reference quá vòng đời hợp lệ. Mã native dùng chung tiến trình và có thể ảnh hưởng toàn bộ JVM khi sai.

**Class loader cũng có vòng đời riêng:** JVM theo dõi thư viện native gắn với loader; nạp cùng một thư viện native qua các class loader độc lập có thể gặp lỗi kiểu “already loaded in another classloader”. Đừng xem việc nạp/unload như thao tác có thể thay nóng tùy ý; hãy thiết kế nơi sở hữu thư viện rõ ràng.

Ngoài JNI, Java có các lựa chọn kết nối native như **JNA** (thư viện bên thứ ba) và **Foreign Function & Memory API (FFM)** (API chuẩn từ JDK 22). Chúng giảm bớt hoặc thay đổi cách viết cầu nối, nhưng **không xóa yêu cầu tương thích binary, ABI, kiến trúc CPU và cơ chế OS loader**. Khi học kiến trúc tiến trình, trước hết phải hiểu những ràng buộc này dù chọn bridge nào.

## 9. Tự kiểm tra hiểu biết

- Vì sao JDK/JVM 64-bit không thể nạp DLL 32-bit trực tiếp, ngay cả khi Windows hỗ trợ chạy tiến trình 32-bit?
- Tại sao tệp `libnativecalc.so` tồn tại trong thư mục đã cấu hình mà loader vẫn báo thiếu `libdependency.so`?
- Điểm khác nhau giữa `System.loadLibrary("nativecalc")` và `System.load("/absolute/path/libnativecalc.so")` là gì?
- Nếu Java chạy trên macOS ARM64 nhưng native library chỉ có slice x86_64, cần thay đổi gì trong binary hoặc môi trường chạy?
- Nếu lỗi native pointer khiến JVM crash, tại sao `try/catch` Java không bảo đảm khôi phục được tiến trình?

**Ghi nhớ:** `.dll`, `.so` và `.dylib` là các thư viện mã máy được OS loader đưa vào **không gian địa chỉ của tiến trình Java**. Tải thành công phụ thuộc đồng thời vào **định dạng OS, kiến trúc và bitness của JVM, ABI/symbol, dependency và quy tắc đường dẫn**. JNI là một cách Java gọi vào những thư viện đó; nó không biến native code thành bytecode hay cô lập native code khỏi JVM.
