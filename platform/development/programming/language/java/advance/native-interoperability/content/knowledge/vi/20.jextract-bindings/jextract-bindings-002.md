# Phân biệt công cụ jextract phân phối riêng với lệnh có sẵn của JDK

## 1. Câu trả lời cốt lõi: jextract không phải lệnh chuẩn đi kèm JDK

Khi mới học **Foreign Function & Memory API (FFM)**, có người đã cài một JDK mới, chạy được `java` và `javac` nhưng gõ `jextract --version` thì nhận lỗi **command not found** hoặc **is not recognized**. Đây không phải một nghịch lý hay một cài đặt JDK “hỏng”: **`jextract` là công cụ tạo Java bindings từ các C header files, được phát triển và phân phối riêng trong dự án OpenJDK jextract**, không phải một command bắt buộc có trong thư mục `bin` của bản JDK chuẩn.

Một vài điểm cần phân biệt ngay:

- **`java`** chạy JVM và Java classes; **`javac`** biên dịch Java source thành bytecode; **`javap`**, **`jar`**, **`jdeps`**, **`jlink`** là các công cụ thường có trong **JDK đầy đủ**.
- **`jextract`** phân tích **C header** (`.h`) bằng nền tảng Clang và **sinh mã nguồn Java** sử dụng FFM API để gọi một thư viện native. Nó phải được **tải/cài đặt riêng**, hoặc build từ nguồn của dự án jextract.
- Việc FFM API được **finalized từ JDK 22 (JEP 454)** **không đồng nghĩa** `jextract` trở thành tool đi kèm JDK.
- Bạn có thể **dùng FFM trực tiếp mà không cần jextract**: tự viết `SymbolLookup`, `MemoryLayout`, `FunctionDescriptor` và `Linker.downcallHandle(...)`. Ngược lại, muốn chạy generated bindings của jextract thì **vẫn cần một JDK tương thích để biên dịch/chạy** mã Java được sinh.
- **`javac -h` khác `jextract` và khác chiều xử lý**: `javac -h` đọc **Java `native` methods** rồi sinh **C JNI header**; `jextract` đọc **C header** rồi sinh **Java FFM bindings**.
- `jextract` bản phân phối ngoài có version, native platform support và phụ thuộc Clang/libclang riêng; không thể mặc định file `jextract` bất kỳ chạy được với mọi JDK và OS.

Bài này nằm trong nhóm **Sinh liên kết jextract** của **Java Advance – native-interoperability**. Trọng tâm là **nhận diện, cài đúng, kiểm tra đúng, không nhầm công cụ và thực hiện đúng chuỗi generation/build/runtime**. Các ví dụ Java tối thiểu được kiểm chứng trên JDK 24; phần chạy chính `jextract` được ghi là **quy trình dành cho môi trường đã cài công cụ**, không giả là kết quả của lần chạy nếu `jextract` chưa được cài.

### Ba câu hỏi tự kiểm tra trước khi bắt đầu

1. “Tôi có JDK nhưng không có `jextract`. Có bình thường không?” **Có.**
2. “Tôi có `jextract` rồi thì có bỏ `javac` không?” **Không.** Công cụ tạo Java source, còn Java compiler/runtime xử lý build và chạy.
3. “JDK có `javac -h`, vậy dùng thay `jextract` được không?” **Không.** Đầu vào, đầu ra, API và mục đích đều khác.

## 2. Hai công cụ thuộc hai lớp khác nhau

Một hệ thống native-interoperability có **Java toolchain**, **jextract generator**, **C toolchain** và **native library**. Không nên gom chúng thành một “bộ JDK”:

| Thành phần | Có sẵn trong một JDK phát triển chuẩn? | Đầu vào | Kết quả chính |
|---|---|---|---|
| `java` | Có | Java bytecode / module | Chạy ứng dụng trong JVM |
| `javac` | Có | `.java` | `.class` bytecode |
| `javac -h` | Có, là tùy chọn của `javac` | Java classes có `native` methods | C header cho **JNI implementations** |
| `javap` | Có | `.class` | Xem signatures, descriptors, bytecode |
| `jar` | Có | Java files/classes/resources | `.jar` và tác vụ archive |
| `jdeps` | Có | Java modules/JAR/classes | Phân tích dependencies |
| `jlink` | Có | Java modules | Custom runtime image |
| `jextract` | **Không phải bundled tool chuẩn** | **C header (`.h`)**, Clang/preprocessor, options | **Java FFM binding sources** |
| `clang` / `gcc` / `cl.exe` | Không phải công cụ JDK chuẩn | `.c`/`.h` | Native `.so`/`.dylib`/`.dll` |
| `libclang` | Phụ thuộc native của jextract | C AST/parser APIs | Giúp jextract hiểu C headers |

Bảng nói “JDK phát triển chuẩn” để phân biệt với **Java runtime image được tối giản hóa** bằng `jlink` hoặc các bản đóng gói vendor tùy chỉnh. Không suy từ một file `java.exe` rằng máy đang có mọi JDK commands. Ngược lại, một vendor có thể đóng gói thêm tools khác theo sản phẩm riêng; **kiểm tra phân phối thực tế** thay vì khẳng định mọi bộ cài đều giống nhau.

### Câu phân biệt một dòng

~~~text
JDK tools:    .java ----javac----> .class ----java----> chạy JVM
                            |
                            +--- javac -h ---> .h cho JNI/C adapter

Standalone:   C header .h ----jextract----> generated Java .java
                                              |
                                              +----javac----> .class
                                                         |
                                                         +----java + native .so/.dll/.dylib
~~~

**`jextract` là build-time code generator**, không phải Java runtime, compiler C hay thành phần đóng gói JVM. Một khi đã sinh mã Java bindings phù hợp và đưa vào build, bạn thường **không cần cài `jextract` trên máy production**, trừ khi production cố tình thực hiện generation lúc chạy (không phải mô hình mặc định).

## 3. Tại sao dễ nhầm: FFM vào JDK, nhưng jextract vẫn phân phối riêng

FFM API, được chuẩn hóa tại **JEP 454**, cung cấp các lớp như:

~~~java
// Một phần public FFM API đã finalized từ JDK 22.
import java.lang.foreign.Arena;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.Linker;
import java.lang.foreign.FunctionDescriptor;
~~~

Những **Java APIs** nằm trong module `java.base` của JDK 22+; Java compiler nhìn thấy chúng như các classes thường. Trong khi đó, **`jextract`** là một **executable tool** mà dự án OpenJDK phân phối bằng artifacts riêng; nó parse C headers và phát sinh Java source sử dụng chính FFM APIs nói trên.

Sự khác biệt quan trọng:

- **API finalized**: cam kết một bề mặt lập trình của **JDK 22+** cho ứng dụng Java.
- **Generator standalone**: một **tool phát triển độc lập**, version của tool phải phù hợp với Java/FFM API và môi trường Clang trên máy generation.
- **Generated source**: code được tạo tại build time; cần được **compile** bởi JDK phù hợp và **link tới native library** đúng ABI/runtime.
- **Native binary**: bản thân `.so`/`.dll`/`.dylib` được compiler/linker C hoặc nhà cung cấp thư viện phân phối; jextract **không biến header thành native binary**.

Một C header có thể chứa khai báo mà không có implementation. Ví dụ:

~~~c
/* adder.h chỉ là hợp đồng C ABI: chưa có native implementation. */
#ifndef ADDER_H
#define ADDER_H
int add_numbers(int a, int b);
#endif
~~~

Chạy `jextract` đối với header ấy có thể sinh Java declarations/bindings, nhưng **khi ứng dụng chạy** vẫn cần C library có symbol thực `add_numbers`. Nếu thiếu binary, sai exports hoặc sai ABI, generated Java code không tự tạo được implementation.

## 4. Nguồn tải: xác định jextract là artifact riêng

Các điểm khởi đầu chính thức:

- Trang phát hành công cụ: [OpenJDK jextract](https://jdk.java.net/jextract/).
- Source và hướng dẫn build: [openjdk/jextract](https://github.com/openjdk/jextract).
- Sổ tay sử dụng: [OpenJDK jextract GUIDE.md](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- Bài học chính thức: [dev.java – Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/).
- Ví dụ trong [Java SE 22 – Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).

**Quy trình chọn artifact trước khi tải:**

1. Xác định **JDK runtime/build hiện dùng** bằng `java -version` và `javac -version`; đừng chỉ dựa vào IDE project SDK.
2. Vào **release page của jextract**; chọn binary theo **OS và CPU architecture** của máy generation, không lấy bản x86_64 cho ARM64 một cách mù quáng.
3. Đọc release notes/README về **JDK version mà tool và generated bindings nhắm tới**. Dự án jextract có thể cập nhật theo mainline JDK và cung cấp branches/releases cho các mốc JDK cũ. Không giả định “jextract mới nhất” luôn tương thích với ứng dụng buộc dùng JDK 22.
4. Xem yêu cầu về **native libclang/LLVM**, đường dẫn thư viện, headers hệ thống và runtime libraries. Build từ source jextract thường cần một toolchain JDK phù hợp và `libclang`; binary đóng gói sẵn có thể đã giải quyết một phần phụ thuộc tùy release.
5. Giải nén/cài ở **thư mục độc lập** (`tools/jextract-...` chẳng hạn), không chép thủ công vào `$JAVA_HOME/bin` như thể nó là file JDK gốc.
6. Chạy **đường dẫn thực của executable** để xác minh trước khi thêm `PATH`; kiểm tra `jextract --version`, `jextract --help` và JDK target.
7. Pin phiên bản jextract và JDK cùng script/toolchain config trong CI, thay vì để PATH tình cờ trỏ tới các releases khác nhau trên máy developers.

**Bảo mật:** chỉ nhận binary từ nguồn tin cậy, kiểm tra checksum/signature khi nhà phát hành cung cấp, tránh chạy executable `jextract` mạo danh trong một thư mục ghi được bởi người khác. C header không tin cậy cũng có thể chứa macro/include phức tạp; generation trong CI nên chạy với quyền vừa đủ.

### jextract và libclang

`jextract` không phải parser Java source; nó tận dụng **Clang C frontend / libclang** để đọc C syntax, macros, typedefs, structs, comments và các `#include`. Vì vậy:
- C header phải được parse thành công trên máy đang chạy generator, với include paths/defines phù hợp.
- Có thể phải cài/deploy LLVM hoặc cung cấp đúng `libclang` theo hướng dẫn release.
- Không thể thay `libclang` bằng mỗi `javac`; Java compiler không parse C AST.
- Khác compiler/version/preprocessor macros có thể cho **ABI model/generation khác nhau**. Kiểm thử source sinh trên đúng platform (Windows/Linux/macOS) nếu C header không portable.

Trang jextract chính thức là nguồn xác nhận download location và version details; **không tự bịa số phiên bản “mới nhất”** trong một README có thể tồn tại nhiều năm.

## 5. Kiểm tra có jextract chưa: PATH, JDK bin, tool riêng

### 5.1. Linux/macOS, POSIX shell

~~~sh
java -version
javac -version

command -v java
command -v javac
command -v javap
command -v jar
command -v jdeps
command -v jlink

# jextract là lệnh riêng: có thể không được cài.
if command -v jextract >/dev/null 2>&1; then
    jextract --version
else
    echo "jextract is not on PATH; install a separate distribution if needed"
fi

# Chỉ xem bin của JDK đã đặt JAVA_HOME (nếu có).
if [ -n "$JAVA_HOME" ]; then
    ls "$JAVA_HOME/bin"
fi
~~~

`command -v jextract` trả không tìm thấy **chỉ chứng minh** command không nằm trên PATH hiện tại; nó có thể đang được cài trong một thư mục mà PATH chưa trỏ tới. Nếu biết rõ nơi giải nén, gọi trực tiếp `/opt/tools/jextract/bin/jextract --version` (đường dẫn chỉ minh họa) trước khi đổi PATH.

### 5.2. Windows PowerShell

~~~powershell
java -version
javac -version

Get-Command java, javac, javap, jar, jdeps, jlink |
    Select-Object Name, Source

# Nếu không có, kết quả rỗng; không phải bằng chứng lỗi JDK.
$extract = Get-Command jextract -ErrorAction SilentlyContinue
if ($null -eq $extract) {
    Write-Output "jextract not on PATH"
} else {
    $extract.Source
    jextract --version
}

# Tùy chọn: quan sát bin của JDK mà JAVA_HOME trỏ tới.
if ($env:JAVA_HOME) {
    Get-ChildItem -LiteralPath (Join-Path $env:JAVA_HOME "bin") |
        Select-Object Name
}
~~~

`Get-Command` cho biết **lệnh đang được resolve từ đâu**. Nếu `jextract` nằm trong `C:\tools\jextract\bin`, kết quả đó chứng minh có executable ngoài JDK, không phải JDK “tự có jextract”. Trường hợp PATH bị trùng nhiều tool versions, dùng `Get-Command jextract -All` để xem các candidates, rồi chọn đúng absolute path.

### 5.3. Windows CMD

~~~bat
where java
where javac
where jextract

java -version
javac -version
jextract --version
~~~

`where jextract` hoặc `jextract --version` có thể trả exit code khác 0 khi chưa cài; **đó là kết quả chẩn đoán**, không phải lỗi phải xử lý bằng cài lại JDK.

### 5.4. Ba mức kết luận đúng

| Kết quả kiểm tra | Kết luận đáng tin |
|---|---|
| `javac` chạy, `jextract` không có trên PATH | JDK compiler có thể hoạt động bình thường; chưa thấy jextract trên PATH |
| `jextract --version` chạy, Source ở ngoài JDK | Công cụ riêng đã cài/được thêm PATH; cần xem version/compatibility |
| `jextract` có trong thư mục mà vendor đặt cạnh JDK | Chỉ chứng minh **bộ phân phối hiện tại** có tool đó; không nên nói “mọi JDK chuẩn đều đi kèm” |
| `java` có nhưng `javac` không có | Có thể đang dùng runtime image tối giản, JRE/alias khác hoặc PATH sai |
| `jextract` có nhưng `javac` không có | Generator riêng hiện diện; chưa chắc có compiler Java phù hợp để build generated source |

Nếu cùng máy có nhiều JDK, `java -version` và `javac -version` có thể lấy từ **hai installations khác nhau**. Chỉ chạy thành công một command chưa đủ: kiểm tra `JAVA_HOME` và resolved executable paths, rồi giữ toolchain nhất quán.

## 6. Java 17+ runnable: audit những tool thật sự có trong java.home/bin

Ví dụ này cố ý **không dùng FFM và không cần jextract**. Nó kiểm tra file tools cạnh Java runtime hiện tại và in rõ điều quan sát. Lý do chọn Java 17+ là để người học có thể làm bài nhận diện **ngay cả khi chưa nâng JDK tới 22**.

Tạo **`JdkToolAudit.java`**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class JdkToolAudit {
    private static void show(Path bin, String suffix, String tool) {
        boolean found = Files.isRegularFile(bin.resolve(tool + suffix));
        System.out.println(tool + "InRuntimeBin=" + found);
    }

    public static void main(String[] args) {
        Path bin = Path.of(System.getProperty("java.home"), "bin");
        String suffix = System.getProperty("os.name")
                .toLowerCase(Locale.ROOT).contains("win") ? ".exe" : "";

        System.out.println("jdkFeature=" + Runtime.version().feature());
        show(bin, suffix, "javac");
        show(bin, suffix, "javap");
        show(bin, suffix, "jar");
        show(bin, suffix, "jdeps");
        show(bin, suffix, "jlink");
        show(bin, suffix, "jextract");
    }
}
~~~

Biên dịch và chạy tại thư mục có file:

~~~sh
mkdir -p out
javac --release 17 -d out JdkToolAudit.java
java -cp out JdkToolAudit
~~~

**Windows CMD**, nếu `out` chưa có: `mkdir out` rồi dùng hai lệnh `javac`/`java` tương tự. PowerShell có thể dùng `New-Item -ItemType Directory -Force out | Out-Null`.

Trên **môi trường kiểm thử Windows x64 / Azul JDK 24.0.2**, stdout **đúng** là:

~~~text
jdkFeature=24
javacInRuntimeBin=true
javapInRuntimeBin=true
jarInRuntimeBin=true
jdepsInRuntimeBin=true
jlinkInRuntimeBin=true
jextractInRuntimeBin=false
~~~

Ý nghĩa:
- `java.home` là root **runtime mà JVM hiện tại đang dùng**; trong JDK đầy đủ ở môi trường kiểm thử, nó chứa các executable chuẩn.
- `Files.isRegularFile(...)` **không scan PATH**: nếu có `jextract` cài ở chỗ khác, dòng `jextractInRuntimeBin=false` vẫn có thể đúng. Cần `command -v` / `Get-Command` để kiểm tra PATH.
- `jdkFeature=24` là giá trị **theo máy chạy**; trên JDK 22/23/25/26 nó thay đổi. Các dòng `true/false` cũng có thể khác theo bản build, runtime image, OS và vendor.
- Ví dụ **không kiểm tra executable thực sự chạy được hoặc có đúng version**; nó chỉ trả lời câu hỏi hẹp “file tên này có ở `java.home/bin` không?”. Để kiểm tra khả năng hoạt động, vẫn phải chạy `--version` và kiểm tra exit code.

Đây là một **dấu hiệu thực nghiệm**, không nên dùng một máy Windows để suy ra tất cả distributions trên thế giới đều có danh sách files y hệt.

## 7. Không nhầm `javac -h` với `jextract`: hướng sinh mã ngược nhau

Cả hai liên quan Java và native code, nhưng ở **hai workflow khác nhau**.

### 7.1. `javac -h`: Java `native` declaration → C JNI header

Tạo **`JniHeaderCheck.java`**:

~~~java
public final class JniHeaderCheck {
    private static native int twice(int value);

    public static void main(String[] args) {
        System.out.println("JVM_OK");
    }
}
~~~

Chạy JDK compiler:

~~~sh
mkdir -p out headers
javac --release 17 -h headers -d out JniHeaderCheck.java
java -cp out JniHeaderCheck
~~~

**Windows CMD** có thể tạo lần lượt `mkdir out` và `mkdir headers`; lệnh `javac`/`java` không đổi. `javac -h` được hỗ trợ trên JDK 17+ và tạo file **`headers/JniHeaderCheck.h`** từ **native method Java**.

Trong generated C header có prototype tương đương:

~~~c
/* Chỉ là trích đoạn của header được javac -h tạo. */
JNIEXPORT jint JNICALL Java_JniHeaderCheck_twice
  (JNIEnv *, jclass, jint);
~~~

Giải thích:
- `JNIEnv *` là environment pointer của thread gọi native.
- `jclass` ở đây vì Java method là **`static native`**, nếu instance native method thì là `jobject`.
- `jint` biểu diễn Java `int` theo JNI.
- Prefix `Java_JniHeaderCheck_twice` là JNI exported symbol naming convention.
- Generated header giúp bạn **viết implementation C** tương ứng; `javac` **không sinh code implementation C**.

**Stdout khi chạy class trên**:

~~~text
JVM_OK
~~~

Mã `main` **không gọi `twice`**, vì chưa có native library implementation; điều đó cho phép minh họa build và header generation độc lập. Nếu sửa main để gọi `twice(2)` khi chưa có C JNI binary, sẽ có `UnsatisfiedLinkError`. Không lấy `JVM_OK` làm bằng chứng một JNI native method đã hoạt động.

Trong môi trường kiểm thử JDK 24, `javac --release 17 -h` đã tạo header chứa cả `JNIEXPORT` và `Java_JniHeaderCheck_twice`; chương trình Java in `JVM_OK` đúng như trên.

### 7.2. `jextract`: C header → Java FFM bindings

Với C header:

~~~c
#ifndef ADDER_H
#define ADDER_H

int add_numbers(int a, int b);

#endif
~~~

C file **`native/adder.h`** ở trên đi vào **`jextract`**, đầu ra thông thường là một nhóm **Java source files** có các helper/FFM wrappers (tùy headers và version). Không phải C JNI header:

~~~text
native/adder.h
       |
    jextract        (tool cài riêng, dùng Clang parser)
       |
       v
gensrc/demo/ffm/...  các file .java được sinh
       |
     javac          (tool JDK)
       |
       v
Java bytecode .class
       |
     java            (tool JDK)
       |
       v
C shared library thật (libadder.so / libadder.dylib / adder.dll)
~~~

`jextract` nhìn **C declarations** và tạo một lớp Java mapping phù hợp. Nó không cần Java class chứa `native` methods từ trước và không yêu cầu dùng naming convention `Java_Class_method`. Binding tạo ra gọi **C ABI symbols** thông thường qua `java.lang.foreign.Linker`.

### 7.3. Bảng đối chiếu không thể nhầm

| Câu hỏi | `javac -h` | `jextract` |
|---|---|---|
| Là tool có sẵn trong JDK chuẩn? | **Có**, là option của `javac` | **Không**, lấy phân phối riêng |
| Đầu vào | `.java` với `native` methods | **C header `.h`** |
| Output | **C JNI header `.h`** | **Java FFM binding sources `.java`** |
| Cần libclang để parse C header? | Không | Thường có **libclang/LLVM dependencies** theo tool distribution |
| Mục tiêu | Để C implementation của Java JNI native method khớp signature | Java gọi C ABI library functions / structs / constants |
| Dùng `JNIEnv *`? | Có, JNI C signatures | Generated FFM bindings bình thường không có JNI adapter |
| Phụ thuộc bản JDK? | Theo Java compiler/JNI platform | Theo **jextract release + FFM/JDK target** |
| Lúc nào chạy? | Build JNI adapter | Generate Java bindings từ C headers |

**Một quy tắc dễ nhớ:** “`javac -h` cho *Java → C*, còn `jextract` cho *C → Java*.” Mũi tên nói về **hướng sinh declaration/binding**, không phải hướng thực thi của native call.

## 8. Cài riêng jextract: quy trình tổng quát có thể tái lập

### Bước 1 – Xác minh JDK cho tool và project

~~~sh
java -version
javac -version
~~~

Ví dụ dự án dùng FFM finalized chọn **JDK 22+**. Nếu tool jextract binary đã được build cho một release JDK cao hơn (do mainline tiến lên), dùng **JDK mà release jextract ghi rõ** để chạy generator, rồi bảo đảm generated source sử dụng APIs có sẵn trong **runtime target của ứng dụng**. Không tự kết luận tool được build cho 25 có thể tạo bindings chạy trên 22 mà không có điều chỉnh.

### Bước 2 – Download đúng binary OS/architecture

Tải ở `https://jdk.java.net/jextract/` hoặc tham khảo build từ `https://github.com/openjdk/jextract`. Giải nén vào thư mục riêng. Ví dụ **đường dẫn minh họa**, không phải yêu cầu phải dùng chính xác:

~~~text
Linux:    /opt/tools/jextract/bin/jextract
macOS:    /opt/tools/jextract/bin/jextract
Windows:  C:\tools\jextract\bin\jextract.bat hoặc executable do release cung cấp
~~~

**Không đoán phần mở rộng Windows**: xem thực tế các files trong `bin` của bản tải. Tùy bản phát hành, launcher có thể là `jextract.bat`, `jextract.exe` hoặc script tương ứng; gọi đúng file đang có.

### Bước 3 – Kiểm tra trước khi sửa PATH

~~~sh
# Linux/macOS; path minh họa:
"/opt/tools/jextract/bin/jextract" --version
"/opt/tools/jextract/bin/jextract" --help
~~~

Windows PowerShell có thể dùng:

~~~powershell
# Thay tên launcher bằng file thật sự đã giải nén.
& "C:\tools\jextract\bin\jextract.bat" --version
& "C:\tools\jextract\bin\jextract.bat" --help
~~~

Nếu launch thất bại vì missing DLL/`libclang`, hãy đọc đúng release prerequisites và kiểm tra đường dẫn native dependencies; **đừng cài lại JDK ngẫu nhiên**.

### Bước 4 – Chỉ khi cần, thêm bin riêng vào PATH

Linux/macOS shell:

~~~sh
export PATH="/opt/tools/jextract/bin:$PATH"
jextract --version
~~~

Windows PowerShell cho **session hiện tại**:

~~~powershell
$env:PATH = "C:\tools\jextract\bin;" + $env:PATH
Get-Command jextract -All
jextract --version
~~~

Điều này chỉ chỉnh môi trường shell/CI session, không sửa JDK. Trong build/CI reproducible, thích dùng **đường dẫn executable pinned** thay vì tìm lệnh theo PATH không kiểm soát.

### Bước 5 – Đóng băng thông tin để tái lập

Ghi vào build documentation hoặc CI cache metadata:
- Release/version jextract (output từ `jextract --version`).
- JDK toolchain version (output `java/javac -version`).
- OS/architecture của generator và target.
- Native header/library version; hash hoặc dependency lock nếu thích hợp.
- C compiler/preprocessor defines/include paths dùng để parse.
- Generated files được commit theo policy của dự án hay regenerate trong build.
- Các native access flags runtime cần cấp cho generated binding module.

Đừng ghi version giả hoặc output được suy đoán từ tên zip; phải dùng giá trị **thực** từ tool installed.

## 9. Ví dụ workflow jextract: từ adder.h tới Java bindings

**Phần này yêu cầu máy đã cài jextract và C compiler.** Trong môi trường kiểm thử của bài, `jextract` **chưa được cài**, nên các câu lệnh generation sau là **hướng dẫn theo official CLI**, không được ghi nhận là đã chạy hoặc đã xác minh output cụ thể.

### 9.1. C header và implementation là hai file khác nhau

Cấu trúc mẫu:

~~~text
adder-demo/
  native/
    adder.h
    adder.c
  gensrc/               # jextract sinh Java sources vào đây
  out/                  # javac sinh .class vào đây
~~~

File **`native/adder.h`**:

~~~c
#ifndef ADDER_H
#define ADDER_H

int add_numbers(int a, int b);

#endif
~~~

File **`native/adder.c`**:

~~~c
#include "adder.h"

int add_numbers(int a, int b) {
    return a + b;
}
~~~

`adder.h` mô tả **C ABI contract**; `adder.c` là **native implementation**. Trên nền tảng muốn xuất symbol từ DLL (đặc biệt Windows/MSVC), cần kiểm tra **export visibility**; có thể đánh dấu `__declspec(dllexport)` hoặc dùng file `.def`. Đoạn C tối giản trên Linux/macOS thường có global function symbol mặc định, nhưng Windows không tự bảo đảm export y như các hệ khác.

### 9.2. Biên dịch native library riêng

Trên Linux:

~~~sh
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -o libadder.so native/adder.c
~~~

Trên macOS:

~~~sh
cc -std=c11 -Wall -Wextra -dynamiclib \
  -o libadder.dylib native/adder.c
~~~

Trên Windows MSVC Developer Command Prompt, nếu `adder.c` chưa có export attribute thì chỉ định export ở linker:

~~~bat
cl /nologo /W4 /LD native\adder.c /link /EXPORT:add_numbers /OUT:adder.dll
~~~

Các lệnh trên là **mẫu theo toolchain**, không phải output đã được test trên cả ba OS. Sửa syntax theo compiler/version/architecture nếu cần. Trước khi tin Java bindings, kiểm tra **exported symbol** thực sự mang tên `add_numbers`:
- Linux: `nm -D --defined-only libadder.so`;
- macOS: `nm -gU libadder.dylib`;
- Windows: `dumpbin /EXPORTS adder.dll`.

Nếu C++ implementation, hãy công bố **C ABI** qua `extern "C"` thích hợp rồi generate từ header C-compatible. jextract parse C declarations; không tự trích toàn bộ C++ templates/classes thành binding Java FFM tương ứng.

### 9.3. Chạy standalone jextract với các tham số rõ nghĩa

Tại thư mục `adder-demo`, sau khi `jextract --version` đã chạy thành công:

~~~sh
jextract \
  --include-dir native \
  --output gensrc \
  --target-package demo.ffm \
  --library adder \
  native/adder.h
~~~

Trên Windows CMD viết một dòng:

~~~bat
jextract --include-dir native --output gensrc --target-package demo.ffm --library adder native\adder.h
~~~

Các options:
- `--include-dir native`: bổ sung đường dẫn tìm `#include` / C headers.
- `--output gensrc`: thư mục root để ghi **generated Java source files**.
- `--target-package demo.ffm`: package của Java bindings.
- `--library adder`: bảo generated bindings nạp native library tên logic `adder`; tool/runtime map tên theo OS, ví dụ `libadder.so`/`libadder.dylib`/`adder.dll`.
- `native/adder.h`: C header chính cần parse, **không phải Java source file**.

Theo guide chính thức, generated root class thường được suy từ tên header; `adder.h` có thể tạo **`adder_h`** cùng các files phụ khi có structs, unions, function pointers. **Tên class/methods và loại file cần kiểm tra trên output thực tế**, vì chúng có thể thay đổi theo jextract release/options và C declarations; không viết sẵn một bản Java client “runnable” giả sử exact generated signatures khi chưa có tool/output.

### 9.4. Kiểm tra artifacts, rồi dùng JDK tools tiếp

Linux/macOS:

~~~sh
find gensrc -type f -name '*.java'
# Kiểm tra những files đã sinh; nếu không có file .java thì dừng.
# Compile generated source bằng JDK phù hợp với jextract release.
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem gensrc -Recurse -Filter *.java |
    Select-Object FullName
~~~

**Bước kế tiếp là `javac`**, không phải chạy `jextract` để thực hiện một C function. Trong dự án thật, dùng Gradle/Maven/IDE compile generated sources cùng source application; CI có thể đưa chúng vào source set `gensrc`. Kiểm tra required target JDK trước khi sử dụng `javac --release ...`, đừng ép `--release 22` cho bindings generated bằng tool mới chỉ hỗ trợ một FFM API sau đó.

Sau khi build, JVM cần:
1. Java classpath/module path tìm được generated classes.
2. Native shared library thực `adder` có đúng platform/arch.
3. Loader tìm được library qua **OS library search rules**, hoặc binding được generate với explicit path/appropriate loader option.
4. Module thực hiện restricted FFM calls được cấp **native access** khi JDK yêu cầu, ví dụ code trên classpath:

~~~sh
java --enable-native-access=ALL-UNNAMED -cp out YourClient
~~~

`YourClient` ở dòng này là **tên class client do ứng dụng tự viết**, không phải file tự động có sẵn từ generator. Khi dùng named module, thay `ALL-UNNAMED` bằng module name thích hợp.

### 9.5. Trường hợp cần explicit native library path

Official `jextract` guide hỗ trợ tham số `--library` với **tên logic** hoặc **đường dẫn** được prefix bằng dấu hai chấm:

~~~sh
# Minh họa Linux; file và path phải thực sự tồn tại khi chạy.
jextract \
  --output gensrc \
  --target-package demo.ffm \
  --library :/opt/native/libadder.so \
  native/adder.h
~~~

Giá trị `:/opt/native/libadder.so` ở đây là **một argument** bắt đầu bằng dấu `:`, không phải hai option tách. Nếu không dùng prefix, `--library adder` được map sang tên file theo OS và loader tìm theo search path. Trên Windows, đường dẫn native có dấu `:` của ổ đĩa; dùng đúng shell quoting và tùy chọn mà **release đang dùng** quy định.

Một option khác là `--use-system-load-library`: nó chuyển cách generated bindings load library qua `System.loadLibrary/System.load` theo JVM JNI loader conventions. Khi đó `java.library.path` liên quan trực tiếp; nếu dùng native `libraryLookup` default thì OS search paths như Linux `LD_LIBRARY_PATH` / Windows `PATH` có thể quan trọng. **Đừng sửa `java.library.path` và chờ mọi kiểu loader đều bị ảnh hưởng như nhau**.

## 10. Ví dụ FFM JDK 22+ chạy được mà KHÔNG cần jextract

Để chứng minh `jextract` là **tiện ích sinh mã, không phải phụ thuộc để viết mọi FFM code**, ta tự xây một binding `strlen` bằng classes chuẩn `java.lang.foreign`.

Tạo **`FfmWithoutJextract.java`**:

~~~java
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;

public final class FfmWithoutJextract {
    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();
        MemorySegment symbol = linker.defaultLookup().find("strlen")
                .orElseThrow(() -> new IllegalStateException(
                        "strlen absent from default lookup"));

        MethodHandle strlen = linker.downcallHandle(
                symbol,
                FunctionDescriptor.of(
                        linker.canonicalLayouts().get("size_t"),
                        ValueLayout.ADDRESS));

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment text = arena.allocateFrom("hello");
            long count = ((Number)
                    strlen.invokeWithArguments(text)).longValue();
            System.out.println("strlen=" + count);
            if (count != 5) {
                throw new AssertionError(count);
            }
        }

        System.out.println("FFM_PASS_WITHOUT_JEXTRACT");
    }
}
~~~

Biên dịch và chạy (JDK 22+):

~~~sh
mkdir -p out
javac --release 22 -d out FfmWithoutJextract.java
java --enable-native-access=ALL-UNNAMED \
  -cp out FfmWithoutJextract
~~~

Trên Windows CMD/PowerShell có thể viết `java --enable-native-access=ALL-UNNAMED -cp out FfmWithoutJextract` thành một dòng. Chạy trên JDK 24 Windows x64 đã được kiểm chứng đúng:

~~~text
strlen=5
FFM_PASS_WITHOUT_JEXTRACT
~~~

**Không có dòng nào gọi `jextract`!** Code tự viết `SymbolLookup`, `FunctionDescriptor`, `Linker.downcallHandle`. `Arena.allocateFrom("hello")` cấp chuỗi UTF-8 kết thúc bằng `NUL`; C `strlen` đếm năm byte.

Giới hạn môi trường: `Linker.nativeLinker().defaultLookup()` có danh sách symbols phụ thuộc OS/JVM; trên môi trường không expose `strlen`, code sẽ chủ động ném `IllegalStateException("strlen absent from default lookup")`. Có thể dùng explicit library lookup nếu biết C runtime tương ứng. Đừng suy ra jextract “chạy hay không” từ default symbol availability.

### So sánh ba ví dụ runnable trong bài

| Ví dụ | JDK tối thiểu | Cần jextract? | Cần C compiler? | Kiểm tra điều gì? |
|---|---:|---|---|---|
| `JdkToolAudit` | 17 | Không | Không | Files có trong `java.home/bin` |
| `JniHeaderCheck` với `javac -h` | 17 | Không | Không nếu chỉ generate header | Hướng Java native → C JNI declaration |
| `FfmWithoutJextract` | 22 | Không | Không nếu platform đã cung cấp `strlen` | FFM manual downcall từ JDK APIs |
| `adder.h` → jextract → generated code | Phụ thuộc release jextract; FFM finalized từ 22 | **Có** | Có nếu tự xây `adder` library | Hướng C header → Java FFM bindings |

**Không nhầm “không cần jextract” với “không cần native library”:** `strlen` vẫn được thực thi trong native C runtime của hệ điều hành/JVM. Java FFM đóng vai trò bridge chứ không tái hiện C function bằng Java.

## 11. JDK releases và compatibility matrix cần tự xác minh

Trong lịch sử dự án Panama, FFM API và jextract thay đổi theo Java releases:

| Java release | Trạng thái FFM | Đọc một bài jextract cần lưu ý |
|---|---|---|
| JDK 17–18 | Incubator-era APIs, ví dụ `jdk.incubator.foreign` | Source/flags và jextract branch lịch sử khác; không dùng nguyên mã finalized |
| JDK 19–21 | Nhiều phiên bản preview với API thay đổi | Phải chọn **jextract build/branch và generated code** tương ứng |
| **JDK 22** | **FFM finalized**, JEP 454, `java.lang.foreign` | Source của ví dụ FFM manual trong bài biên dịch với `--release 22` |
| JDK 23+ | FFM tiếp tục phát triển; native-access policy thay đổi theo release | Kiểm tra jextract release compatibility, required flags và generated API thay vì đoán |

Không có mệnh đề an toàn “jextract bản X dùng cho tất cả JDK từ 22 trở đi”. Dự án jextract master thường nhắm mainline JDK gần nhất và có thể có branches/tags riêng cho JDK targets cũ. Người học phải dựa vào **`jextract --version`**, source README của release đang tải và Javadoc của target JDK.

### Nguyên tắc CI pin version

~~~text
JDK dùng để chạy jextract -> đúng yêu cầu của jextract binary
jextract binary            -> đúng version/branch cho API target
C headers + libclang       -> cùng include/macro/ABI contract
javac target               -> biên dịch được Java source vừa sinh
java target/runtime        -> có FFM APIs/flags và native library đúng
~~~

Trong pipeline có nhiều OS, cần kiểm thử generated layout và native ABI theo từng OS. C `long` có thể khác kích thước giữa Windows x64 và Linux x64; preprocessor `#ifdef` cũng có thể tạo declarations khác. Không chia sẻ một set generated files giữa platforms chỉ vì các file đều mang đuôi `.java`.

## 12. libclang, native compiler và C header: ba thứ khác nhau

Một lỗi thường gặp là “jextract parse header được rồi, vậy không cần C compiler nữa?”. Câu trả lời phụ thuộc library:

- Nếu bạn **đã có native binary** đáng tin cậy của nhà cung cấp, `jextract` có thể generate Java bindings từ headers tương ứng; bạn không cần tự biên dịch lại C source.
- Nếu bạn **tự viết C source**, cần C toolchain (GCC/Clang/MSVC) để sinh `.so`/`.dll`/`.dylib`.
- `libclang` là thư viện hỗ trợ **phân tích header trong công cụ jextract**, không đồng nghĩa với việc đã có C shared library của ứng dụng.
- `javac` compile generated Java bindings, **không** compile C. `jar` đóng gói Java classes/resources, **không tự biến C source thành executable**.
- Khi generated code được biên dịch thành `.class`, **không cần jextract lúc chạy bình thường**; runtime cần FFM JDK phù hợp và native binary có thật.

### Header bản đúng với binary bản đúng

Giả sử một nhà cung cấp phát hành `libfoo-v1.so` và `foo-v2.h`. Dù jextract parse thành công header v2, generated method signatures có thể **không** khớp C ABI của binary v1. Điều này nguy hiểm hơn lỗi compilation: native call có thể trả rác, đọc nhầm pointer hoặc crash JVM. Dự án cần pair **headers ↔ binary ↔ architecture ↔ compiler ABI** cùng phiên bản hỗ trợ.

Đừng dùng C++ headers có templates/classes trực tiếp và kỳ vọng jextract hiểu C++ ABI đầy đủ. Một hướng thông thường là viết lớp **C ABI wrapper** khai báo bằng `extern "C"` trong C-compatible header, sau đó dùng jextract với header của lớp wrapper.

## 13. Có cần cài jextract trên production không?

Trong workflow chuẩn:

~~~text
Developer / CI:
  1. obtain headers + compatible jextract
  2. generate Java sources
  3. compile Java and package app
  4. ship app bytecode + native binary

Production:
  1. start suitable JVM
  2. load app/generated bindings
  3. load native library
  4. call C via FFM
~~~

**Không cần jextract executable ở production** nếu mọi Java bindings đã được generate/compile trong build. Ngoại lệ có thể tồn tại nếu ứng dụng cố tình generate code runtime, nhưng đó là kiến trúc đặc biệt cần compiler/source/runtime privileges khác.

### Commit generated sources hay generate mỗi build?

Cả hai đều khả thi:

- **Commit generated sources**: người dùng chỉ cần JDK và native binary để build; code review dễ nhận ra generated code thay đổi khi headers cập nhật. Đổi lại, phải quản lý diff, metadata tool version và tránh sửa tay generated files.
- **Generate trong CI**: kiểm soát C headers/defines và tái tạo bindings tự động; đảm bảo pipeline có **jextract distribution và libclang**. Đổi lại, build phức tạp hơn và cần pin tool versions/repositories để tránh drift.
- **Hybrid**: generate có kiểm soát rồi commit vào thư mục `generated`, CI chạy generation check để đảm bảo không lệch. Điều quan trọng là **có một nguồn chân lý** cho C header/ABI và biết lúc nào regeneration là bắt buộc.

Jextract guide khuyến nghị tư duy generate khi headers/tool được cập nhật chứ không nhất thiết mỗi JVM run; kiểm tra generated file naming/output thật của version đã pin trước khi thiết kế Maven/Gradle tasks.

## 14. Các lỗi phổ biến: xác định lỗi ở đúng lớp thay vì cài lại JDK

| Lỗi/hiện tượng | Tầng phát sinh | Cách xử lý đúng |
|---|---|---|
| `jextract: command not found` / `not recognized` | PATH hoặc chưa cài **standalone tool** | Tải artifact riêng và chạy absolute path, rồi điều chỉnh PATH nếu cần |
| `java`/`javac` có, `jextract` không có | **Không phải lỗi** của JDK chuẩn | Chỉ cài jextract khi thực sự cần generate bindings |
| `UnsupportedClassVersionError` khi chạy jextract | Tool được build cho JDK mới hơn runtime đang dùng | Chọn JDK theo tool release hoặc jextract release đúng target |
| Missing `libclang`/native DLL khi jextract khởi động | Native dependency của generator | Kiểm tra LLVM/libclang theo README release/OS |
| `fatal error: foo.h: No such file or directory` | Clang include paths | `--include-dir/-I` đúng và C SDK headers cần thiết |
| Parse fail do macro/typedef | C preprocessor/ABI config | `-D` defines phù hợp, target OS/toolchain include paths |
| Generated Java code compile fail | `javac`/generated API mismatch | Chọn JDK và jextract target version tương thích; không đoán fix bằng flag bất kỳ |
| `javac -h` không tạo Java bindings từ C | Sai công cụ | `javac -h` chỉ sinh **C JNI header** từ Java `native` |
| `jextract` tạo Java code nhưng không có `adder.dll` | Thiếu native implementation binary | Build/cài C library riêng và kiểm tra exports |
| `UnsatisfiedLinkError` / library load fail khi chạy | Runtime library loading | File/path/OS deps/architecture/loader mode |
| `Optional.empty` khi tra symbol | Export name/library mismatch | `nm`/`dumpbin`/header đúng version |
| `IllegalCallerException` khi gọi restricted FFM | Runtime native-access permissions | `--enable-native-access=ALL-UNNAMED` hoặc named module |
| `WrongMethodTypeException` khi gọi handle | Java method handle signature mismatch | Xem carrier types/`MethodHandle.type()` |
| JVM crash trong native call | ABI/pointer/lifetime sai | So C header với generated bindings, debug native; `try/catch` không bảo đảm cứu JVM |
| Bindings hoạt động trên Linux, sai trên Windows | C `long`, macros, name decoration, struct packing | Generate/validate theo OS/ABI thực, không chỉ copy generated files |
| `jextract --version` chạy nhưng generated code không build trên JDK22 | Generator binary nhắm API JDK khác | Pin release/branch tương ứng target, regeneration |

**Một lỗi công cụ không nên được giải quyết bằng “tải JDK khác” theo phản xạ.** Hãy xác định lỗi thuộc layer nào: JDK bin/PATH, jextract CLI/libclang, C header preprocessing, native library exports, Java compile target, native access policy hay C ABI.

## 15. Bài tập chọn công cụ (có lời giải)

**Bài 1.** Dự án đã có `libmath.so` và C header `math.h`. Muốn tạo các Java wrappers dùng FFM cho functions trong header, nên chạy `javac -h` hay `jextract`?  
**Đáp án:** **`jextract`**. Nó đọc C declarations và phát sinh Java FFM binding sources. Dùng `javac` sau đó để compile generated Java source.

**Bài 2.** Java class khai báo `private native int compute(int x);` và bạn muốn biết C function prototype để triển khai JNI. Dùng tool gì?  
**Đáp án:** **`javac -h`** từ JDK, vì nó sinh C JNI header từ Java `native` declaration. `jextract` đi theo chiều ngược và không sinh JNI implementation.

**Bài 3.** `java -version` in JDK 24, `javac -version` thành công, `jextract --version` thất bại. Có cần cài lại JDK không?  
**Đáp án:** Không. Đây là trường hợp bình thường. Tải/giải nén standalone jextract phù hợp và cấu hình PATH nếu cần generator.

**Bài 4.** Có jextract trên PATH nhưng generated bindings gọi C function sai vì `sizeof(long)` khác giữa Windows và Linux. Lỗi được giải quyết bằng thêm `--enable-native-access`?  
**Đáp án:** Không. Native access cấp **quyền** FFM restricted operations, không sửa layout/ABI. Phải kiểm tra headers, platform defines và generated bindings trên từng ABI.

**Bài 5.** Một `JAR` đã chứa generated Java bindings đầy đủ và production có native library đúng, có cần ship `jextract` executable?  
**Đáp án:** Không trong mô hình thường. Production JVM chạy bytecode, FFM gọi native library; codegen là build-time step.

**Bài 6.** Dùng `jextract --library foo`, runtime không tìm thấy `foo.dll`. Có phải Java package generated sai?  
**Đáp án:** Có thể không. Trước hết kiểm tra binary có thật, export names, OS native loader path, dependencies và mapping `System.mapLibraryName`. Java classpath và native library search path là hai cơ chế khác.

**Bài 7.** Đặt `jextract` vào `$JAVA_HOME/bin` để “sửa” cảnh báo công cụ thiếu có tốt không?  
**Đáp án:** Không khuyến khích. Giữ jextract artifact riêng, version pin rõ, chạy absolute path hoặc thêm riêng jextract `bin` vào PATH. Chép thủ công vào JDK bin che mất nguồn gốc và dễ hỏng khi cập nhật JDK.

**Bài 8.** Có `adder.h` nhưng không có `adder.c` hay binary, `jextract` có tạo được library chạy thật không?  
**Đáp án:** Không. It generates Java bindings từ C headers; vẫn cần native implementation và compatible binary runtime.

**Bài 9.** Bạn muốn dùng FFM cho một C function nhỏ mà không muốn setup jextract. Làm được không?  
**Đáp án:** Có. Tự dùng `SymbolLookup`, `FunctionDescriptor` và `Linker.downcallHandle` như ví dụ `FfmWithoutJextract`, với JDK 22+ và native access phù hợp.

**Bài 10.** `jextract --version` in target JDK mới hơn JDK production. Có thể bỏ qua vì “FFM finalized rồi” không?  
**Đáp án:** Không. Generated Java source vẫn có thể dùng APIs hoặc bytecode target không tồn tại ở production. Chọn đúng generator branch/release và kiểm thử với Java runtime target trước khi ship.

## 16. Checklist trước khi tự động hóa jextract trong CI

- [ ] Xác định dự án **cần code generation từ C headers** hay chỉ cần FFM manual binding; không cài jextract không cần thiết.
- [ ] Pin **JDK**, **jextract version**, **OS/CPU architecture**, native headers và binary versions; không dùng “latest” thiếu kiểm soát.
- [ ] Xác minh `jextract --version` trên **binary riêng**, không giả định tool nằm trong `$JAVA_HOME/bin`.
- [ ] Xác minh `javac -version` và `java -version` đúng runtime target; không để PATH/JAVA_HOME trỏ JDK khác nhau.
- [ ] Kiểm tra Clang/libclang dependencies và include paths/defines trước khi parse C.
- [ ] Chọn C header public API thật (đúng include tree), không trộn C++ templates/class declarations vào C ABI binding.
- [ ] Dùng `--target-package`, `--output`, `--include-dir/-I`, `--library` đúng semantics của jextract release.
- [ ] Kiểm tra **Java source files được sinh**, root header class name và generated method signatures; không dùng class/method name chỉ từ đoán.
- [ ] Dùng **`javac`** để compile generated sources; không nhầm `javac -h` với generator C→Java.
- [ ] Native shared library có thật và export đúng names; build/test C implementation trên OS/ABI mục tiêu.
- [ ] Phân biệt classpath/module path, OS loader path và `java.library.path`; không thay sai cấu hình.
- [ ] Cấp native access cho module chứa FFM binding theo JDK policy; không dùng `--enable-preview` khi FFM finalized JDK22+ nếu không có preview features khác.
- [ ] Không assume ABI portable: `long`/`size_t`/struct padding, macros và callbacks phải được kiểm thử theo platform.
- [ ] Có smoke test gọi native function và kiểm tra kết quả; không chỉ nhìn generated files hay compiler exit code.
- [ ] Khi headers hoặc generator thay đổi, regenerate/review/diff có kiểm soát, không sửa tay generated code rồi quên source of truth.
- [ ] CI deploy không yêu cầu jextract nếu codegen đã hoàn tất ở build time; production có đúng native binary/JVM.
- [ ] Khi tool thiếu, báo rõ **“standalone jextract not installed”**, không mặc định lỗi JDK setup.
- [ ] Ghi chính xác những gì đã chạy; đừng tuyên bố generation thành công nếu chỉ mới trình bày lệnh minh họa.

## 17. Tổng kết và tài liệu gốc

Hãy nhớ chuỗi sau:

~~~text
C HEADER .h ──[standalone jextract / libclang]──> Java FFM binding .java
                                                         |
                                                    [JDK javac]
                                                         |
                                                    Java .class
                                                         |
                                                    [JDK java]
                                                         |
                                           Native C library thật
~~~

Đối chiếu:

~~~text
Java source có "native" ──[JDK javac -h]──> C JNI header .h
                  Đây là CHIỀU KHÁC; không thể dùng thay jextract.
~~~

**`jextract` là công cụ phân phối riêng, chuyên sinh bindings từ C headers; `javac`/`java` và các JDK tools là một phần Java toolchain; FFM API là thư viện chuẩn trong JDK22+; native compiler và native library là lớp riêng.** Tách bốn lớp này giúp chẩn đoán đúng lệnh bị thiếu, đúng version không tương thích và đúng lỗi runtime thay vì sửa nhầm môi trường.

Nguồn chính thức để học/cập nhật theo release:
- [OpenJDK jextract downloads](https://jdk.java.net/jextract/).
- [OpenJDK jextract source / build instructions](https://github.com/openjdk/jextract).
- [OpenJDK jextract detailed guide](https://github.com/openjdk/jextract/blob/master/doc/GUIDE.md).
- [dev.java — Generate Java Bindings with Jextract](https://dev.java/learn/ffm/jextract/).
- [Oracle Java SE 22 — Calling Native Functions with jextract](https://docs.oracle.com/en/java/javase/22/core/call-native-functions-jextract.html).
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454).
- [Oracle Java SE 22 — java.lang.foreign package](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- [Oracle javac documentation (JDK 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/man/javac.html).

**Giới hạn kiểm chứng:** ba ví dụ `JdkToolAudit`, `JniHeaderCheck` và `FfmWithoutJextract` đã compile/chạy với JDK 24 trong phiên kiểm thử. **`jextract` chưa có trong PATH/JDK bin của môi trường này**, vì thế phần download và generation từ `adder.h` là hướng dẫn theo official documentation, không phải output đã được chạy thực tế. Khi có binary riêng, lệnh đầu tiên phải là `jextract --version` để xác định đúng tool/release trước khi generate.