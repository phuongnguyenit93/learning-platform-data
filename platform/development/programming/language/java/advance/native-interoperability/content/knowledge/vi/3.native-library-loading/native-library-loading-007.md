# Chọn phiên bản thư viện native theo hệ điều hành, CPU và ABI thực tế

## Mục tiêu

Khi một chương trình Java cần nạp thư viện native qua JNI, JNA hoặc Foreign Function & Memory API, tên thư viện giống nhau chưa đủ để bảo đảm nạp được. Một file `bridge.dll`, `libbridge.so` hoặc `libbridge.dylib` phải tương thích với **tiến trình JVM đang chạy** và bộ nạp thư viện của hệ điều hành.

Sau bài này, bạn có thể:

- Phân biệt hệ điều hành, kiến trúc CPU, kiến trúc của **tiến trình JVM**, ABI, C runtime và các thư viện phụ thuộc.
- Chọn đúng binary theo bộ điều kiện thực tế, kể cả khi hệ điều hành hoặc CPU vật lý hỗ trợ giả lập kiến trúc khác.
- Hiểu vì sao cùng Linux/x86-64 vẫn có thể không tương thích giữa glibc và musl, hoặc giữa hai bộ thư viện native có symbol/runtime khác nhau.
- Đặt quy ước đóng gói, kiểm tra phiên bản và nạp thư viện bằng `System.load`/`System.loadLibrary` theo cách có thể chẩn đoán.
- Viết bộ chọn biến thể Java 17 rõ ràng, kiểm tra các trường hợp thiếu hỗ trợ và xử lý lỗi nạp thay vì thử bừa nhiều binary.

## 1. Một biến thể native thực sự phụ thuộc vào những gì?

Một thư viện native là mã máy đã biên dịch, khác với bytecode `.class` trong JAR. JVM không biên dịch lại file `.so`/`.dll`/`.dylib` để sửa một kiến trúc hoặc ABI không tương thích. Hãy kiểm tra ít nhất các chiều sau:

| Chiều | Cần đối chiếu | Ví dụ |
|---|---|---|
| **OS và định dạng nhị phân** | Windows PE/COFF, Linux ELF, macOS Mach-O, môi trường Android riêng | DLL Windows không nạp trực tiếp như Linux ELF |
| **Kiến trúc của tiến trình** | x86 32-bit, x86-64, AArch64/ARM64; kiến trúc mà JVM hiện hành đang thực thi | JVM x86-64 cần mã native x86-64 hoặc slice tương thích |
| **ABI và calling convention** | C ABI của nền tảng, kiểu dữ liệu, alignment, tên symbol, cách truyền/nhận tham số, JNI convention | Windows x86 có khác biệt calling convention so với x64 |
| **Runtime và dependencies** | glibc/musl, MSVC runtime, libstdc++/libc++, thư viện phụ thuộc và bản phát hành yêu cầu | `GLIBC_2.34 not found` dù đều là Linux x86-64 |
| **Ràng buộc bổ sung** | Phiên bản OS tối thiểu, CPU instruction set (AVX2, NEON…), bảo mật/ký mã và phiên bản API/ABI thư viện | Binary biên dịch với AVX2 có thể lỗi trên CPU x86-64 cũ |

**Nguyên tắc quyết định:** đích được chọn phải tương thích với **process và runtime loader**, không chỉ tên máy hoặc nhãn “64-bit”. Hệ điều hành, kiến trúc, libc, ABI, dependency và mức CPU tối thiểu kết hợp thành **một biến thể đã được build và kiểm thử**.

Một cách đặt tên khái quát là `<os>-<arch>-<abi>`, ví dụ `linux-x86_64-glibc`, `linux-aarch64-musl`, `windows-x86_64-msvc` hoặc `macos-aarch64-darwin`. Đây là **quy ước phân phối do dự án định nghĩa**, không phải một chuẩn bắt buộc mà JVM tự hiểu.

## 2. Hệ điều hành không quyết định toàn bộ biến thể

### Windows

- Thư viện thường là `bridge.dll` (PE/COFF); cần đúng kiến trúc x86, x86-64 hay ARM64 của JVM đang thực thi.
- Binary có thể phụ thuộc Microsoft Visual C++ Runtime hoặc DLL khác. DLL đúng kiến trúc nhưng thiếu dependency vẫn không nạp được.
- Trên Windows x86 32-bit, calling convention, export/decorated names và `JNICALL` cần được tôn trọng; không coi C++ mangling hay tên exported symbol là giống nhau ở mọi toolchain.
- Windows ARM64 có thể hỗ trợ tiến trình được giả lập; một **JVM x64 đang chạy qua emulation** vẫn cần DLL x64 phù hợp với process ấy, không tự chuyển sang DLL ARM64 chỉ vì CPU vật lý là ARM64.

### Linux

- Thư viện thường là `libbridge.so` (ELF); phải đúng ELF class/`e_machine` và ABI của tiến trình.
- **glibc và musl là hai lựa chọn runtime/ABI khác nhau.** Hai file cùng `linux-x86_64` và tên `libbridge.so` không mặc nhiên hoán đổi được; dynamic loader, các symbol và thư viện phụ thuộc có thể khác.
- Với binary xây trên glibc, chú ý **mức glibc tối thiểu** và các symbol version được liên kết. Build trên distro mới rồi đem chạy trên distro cũ có thể thất bại ngay khi nạp.
- File `.so` có thể phụ thuộc `libstdc++.so`, `libgcc_s.so`, OpenSSL hoặc các `.so` khác. Tương thích với JVM chưa đủ nếu cây dependency không phù hợp.
- `linux-armv7` còn có thể phân biệt ABI hard-float/soft-float; ARM 32-bit, AArch64, x86-64 là những target khác nhau. Không gom tất cả ARM hoặc tất cả Linux vào một binary.

### macOS

- Thư viện JNI thường dùng `libbridge.dylib` (Mach-O); JVM x86-64 và JVM arm64 cần slice kiến trúc thích hợp.
- Một **universal/fat binary** có thể chứa nhiều slice, ví dụ cả x86_64 và arm64; phải kiểm tra binary thực sự chứa những slice nào.
- Mac Apple Silicon chạy JVM x86-64 qua Rosetta 2 vẫn nạp **slice x86_64**; chạy JVM arm64 thì nạp slice arm64.
- Mức macOS tối thiểu, dependencies, mã ký/code signing và chính sách runtime của ứng dụng có thể ảnh hưởng việc nạp. File Mach-O đúng CPU vẫn có thể không sử dụng được.
- `System.mapLibraryName` cho tên file phù hợp với nền tảng hiện tại, nhưng không đánh giá slice, deployment target hoặc thư viện phụ thuộc.

### Android không đồng nghĩa Linux desktop

Android dùng ELF nhưng libc thường là **Bionic**, với cách đóng gói JNI trong APK/AAB theo Android ABI (`arm64-v8a`, `armeabi-v7a`, `x86_64`...). Không lấy `linux-aarch64-glibc` rồi coi là binary Android hợp lệ. Khi làm Android, chọn mô hình packaging và API nạp của Android thay vì áp dụng nguyên vẹn quy trình JDK desktop/server.

## 3. CPU vật lý, OS và kiến trúc JVM: chọn ai làm nguồn quyết định?

Một máy 64-bit có thể chạy nhiều kiểu tiến trình. Với native code được nạp **vào cùng tiến trình Java**, quan trọng nhất là kiến trúc nhị phân của JVM đó:

~~~text
Máy vật lý                      Tiến trình JVM             Thư viện cần nạp
--------------------------------------------------------------------------------
Windows x64                     JVM x64                    DLL x64
Windows x64 (nếu còn hỗ trợ)     JVM x86 32-bit             DLL x86 32-bit
Apple Silicon arm64              JVM arm64                   Mach-O arm64
Apple Silicon arm64 + Rosetta    JVM x86_64                  Mach-O x86_64
Linux aarch64 + emulation        JVM x86_64 được giả lập     ELF x86_64 phù hợp môi trường ấy
~~~

`System.getProperty("os.arch")` là điểm xuất phát hữu ích cho **kiến trúc Java runtime**; đừng thay bằng CPU marketing name, thông tin `uname -m` của host hoặc chỉ xem số bit của hệ điều hành. Thuộc tính có alias: `amd64` và `x86_64` thường cùng chỉ x86-64; `aarch64` và `arm64` cùng chỉ ARM64. Hãy chuẩn hóa alias và **từ chối kiến trúc chưa được hỗ trợ**.

Kiểm tra bằng Java ngay trong môi trường cần chạy:

~~~java
System.out.println("os.name = " + System.getProperty("os.name"));
System.out.println("os.arch = " + System.getProperty("os.arch"));
System.out.println("os.version = " + System.getProperty("os.version"));
System.out.println("java.vm.name = " + System.getProperty("java.vm.name"));
~~~

Ở terminal, cũng có thể quan sát runtime:

~~~bash
java -XshowSettings:properties -version
~~~

Những thuộc tính này **không chứng minh đầy đủ ABI**: không có thuộc tính Java SE portable `native.libc` cho glibc/musl, và `os.arch` không kiểm tra các symbol version, CPU features hoặc dependencies. Các phần còn thiếu phải đến từ cấu hình đích build/deployment, metadata native đáng tin cậy hoặc kiểm tra môi trường đã được kiểm chứng.

Không sửa `-Dos.arch` hay `-Dos.name` chỉ để ép Java chọn bản khác: thay đổi chuỗi thuộc tính **không thay đổi kiến trúc thực tế của JVM**.

## 4. ABI thực tế: vì sao chỉ kiểm tra tên CPU vẫn thiếu?

ABI quy định hợp đồng máy giữa mã đã biên dịch: kích thước và alignment kiểu dữ liệu, cách đặt đối số, trả giá trị, stack/register usage, calling convention, tên/linkage symbol và những điều kiện của runtime. JNI áp đặt giao diện `JNIEnv*` và convention tương ứng, song native library vẫn là ELF/PE/Mach-O chịu quy tắc target.

Cùng `x86_64` nhưng các trường hợp sau có thể khác:

1. **Linux glibc so với Linux musl:** loader/runtime khác nhau; xác nhận build variant thực sự liên kết cho loại libc nào.
2. **glibc mới so với cũ:** file dùng symbol `GLIBC_2.xx` mà target không có sẽ thất bại; không chỉ so `ldd --version` rồi kết luận mọi dependency hợp lệ.
3. **C++ runtime/ABI:** `libstdc++`/`libc++`, phiên bản `GLIBCXX_*`, các cờ compiler và API C++ exported có thể tạo ràng buộc riêng. API JNI/C wrapper ổn định giúp giảm phụ thuộc vào C++ ABI giữa các bên nhưng không loại bỏ dependency.
4. **ARM32 hard-float/soft-float:** cả hai có thể mang nhãn ARM 32-bit nhưng convention truyền tham số floating-point khác nhau.
5. **Instruction set:** build với `-march=native` hoặc AVX2 có thể tạo mã không chạy được trên các CPU chỉ đáp ứng baseline của cùng họ kiến trúc.

Với thư viện trao đổi C struct hoặc callback, cần thêm độ rộng kiểu C, alignment, padding, thứ tự byte, chữ ký hàm và ownership memory. Không dùng `os.arch` để suy ra tất cả những điều này. Nếu thư viện công bố một ABI version riêng, phải kiểm tra version đó **bên cạnh** OS/CPU/libc.

## 5. Quy ước release: biến thể rõ ràng, kiểm tra được

Đóng gói song song nhiều binary với đường dẫn cố định, không đặt các biến thể cùng một đường dẫn rồi đổi chỗ lúc runtime:

~~~text
distribution/
└── native/
    ├── linux/
    │   ├── x86_64/
    │   │   ├── glibc/libbridge.so
    │   │   └── musl/libbridge.so
    │   └── aarch64/
    │       ├── glibc/libbridge.so
    │       └── musl/libbridge.so
    ├── windows/
    │   └── x86_64/msvc/bridge.dll
    └── macos/
        ├── x86_64/darwin/libbridge.dylib
        └── aarch64/darwin/libbridge.dylib
~~~

Sơ đồ biểu diễn **các biến thể dự kiến phát hành**; mỗi đường dẫn chỉ tồn tại nếu đã build và kiểm thử target tương ứng. `msvc` là nhãn của gói Windows dùng MSVC runtime do dự án chọn. `darwin` là nhãn packaging trong ví dụ; macOS còn có deployment target và slice kiểm tra riêng.

Bản phát hành nên kèm manifest hoặc metadata cho **từng artifact**, gồm:

- Phiên bản API/ABI thư viện và phiên bản release; target OS, CPU, libc/toolchain và độ rộng tiến trình.
- Runtime tối thiểu như glibc, macOS deployment target, MSVC runtime hoặc dependency cụ thể; baseline CPU features.
- Tên/đường dẫn file, danh sách thư viện phụ thuộc cần đi kèm và mã SHA-256 của artifact để kiểm tra tính toàn vẹn.
- Trạng thái CI đã build/test trên target tương ứng. **Không tạo một entry nếu artifact chưa tồn tại** và không chọn phiên bản “gần giống nhất” khi không tìm thấy entry phù hợp.

Một gói có thể chứa universal binary trên macOS hoặc một thư viện link tĩnh đúng target; khi đó manifest phải mô tả đúng cấu trúc thực tế. Đường dẫn ở trên là cách tổ chức minh bạch, không phải yêu cầu cứng của Java.

### Ma trận hỗ trợ mẫu

| Target runtime | Binary được chọn | Điều kiện bổ sung |
|---|---|---|
| Linux JVM x86-64 + glibc | `linux/x86_64/glibc/libbridge.so` | Kiểm tra glibc version và dependencies |
| Linux JVM x86-64 + musl | `linux/x86_64/musl/libbridge.so` | Build/link cho musl |
| Linux JVM ARM64 + glibc | `linux/aarch64/glibc/libbridge.so` | Không dùng bản ARMv7 |
| Windows JVM x64 | `windows/x86_64/msvc/bridge.dll` | Runtime DLL và exports phù hợp |
| macOS JVM arm64 | `macos/aarch64/darwin/libbridge.dylib` | Slice arm64, deployment target và ký mã nếu cần |
| macOS x86-64 qua Rosetta | `macos/x86_64/darwin/libbridge.dylib` | Xác minh JVM đang chạy x86-64 |

Không có gói trong ma trận thì ứng dụng báo target chưa được hỗ trợ, thay vì thử file của OS/ABI khác.

## 6. Ví dụ Java 17: chọn binary theo target tường minh

Chương trình sau chuẩn hóa tên OS/CPU, yêu cầu chỉ rõ glibc/musl cho Linux, cho phép xem kết quả chọn mà **không cần có thư viện native** và có phương thức nạp từ thư mục phân phối đã được xác minh. Tên thư viện là `bridge`; `relativePath()` tuân theo cấu trúc ví dụ ở trên.

Lưu vào `NativeVariantSelector.java`:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public final class NativeVariantSelector {

    record Target(String os, String arch, String abi) {
        String relativePath() {
            String fileName = switch (os) {
                case "linux" -> "libbridge.so";
                case "windows" -> "bridge.dll";
                case "macos" -> "libbridge.dylib";
                default -> throw new IllegalStateException(os);
            };
            return "native/" + os + "/" + arch + "/" + abi + "/" + fileName;
        }
    }

    static String normalizeOs(String value) {
        String os = value.toLowerCase(Locale.ROOT);
        if (os.startsWith("windows")) {
            return "windows";
        }
        if (os.startsWith("mac") || os.startsWith("darwin")) {
            return "macos";
        }
        if (os.equals("linux")) {
            return "linux";
        }
        throw new IllegalArgumentException("Unsupported OS: " + value);
    }

    static String normalizeArch(String value) {
        return switch (value.toLowerCase(Locale.ROOT)) {
            case "amd64", "x86_64" -> "x86_64";
            case "aarch64", "arm64" -> "aarch64";
            case "x86", "i386", "i486", "i586", "i686" -> "x86";
            default -> throw new IllegalArgumentException(
                    "Unsupported JVM architecture: " + value);
        };
    }

    static Target choose(String osName, String archName, String linuxLibc) {
        String os = normalizeOs(osName);
        String arch = normalizeArch(archName);

        String abi = switch (os) {
            case "linux" -> switch (linuxLibc.toLowerCase(Locale.ROOT)) {
                case "glibc" -> "glibc";
                case "musl" -> "musl";
                default -> throw new IllegalArgumentException(
                        "Linux requires native.libc=glibc or musl");
            };
            case "windows" -> "msvc";
            case "macos" -> "darwin";
            default -> throw new IllegalStateException(os);
        };

        return new Target(os, arch, abi);
    }

    static void loadFromDistribution(Path directory, Target target)
            throws IOException {
        // Dùng đường dẫn đã được chuẩn hóa và tồn tại thực tế.
        Path root = directory.toRealPath();
        Path binary = root.resolve(target.relativePath()).toRealPath();

        // Không cho symbolic link dẫn ra khỏi thư mục phân phối.
        if (!binary.startsWith(root) || !Files.isRegularFile(binary)) {
            throw new IOException("Invalid native binary path: " + binary);
        }

        // Chỉ gọi sau khi artifact, checksum và điều kiện ABI đã kiểm chứng.
        System.load(binary.toString());
    }

    public static void main(String[] args) throws IOException {
        if (args.length == 0) {
            // Chạy thử logic chọn: kết quả cố định trên mọi JVM.
            System.out.println(choose("Linux", "amd64", "glibc")
                    .relativePath());
            System.out.println(choose("Linux", "aarch64", "musl")
                    .relativePath());
            System.out.println(choose("Mac OS X", "arm64", "")
                    .relativePath());
            System.out.println(choose("Windows 11", "amd64", "")
                    .relativePath());
            return;
        }

        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java NativeVariantSelector [distributionDir]");
        }

        // Nạp thật: chọn theo JVM hiện hành, không dùng target giả lập.
        Target runtime = choose(
                System.getProperty("os.name"),
                System.getProperty("os.arch"),
                System.getProperty("native.libc", ""));
        loadFromDistribution(Path.of(args[0]), runtime);
        System.out.println("Loaded: " + runtime.relativePath());
    }
}
~~~

Biên dịch và chạy bản **kiểm tra logic lựa chọn**:

~~~bash
javac NativeVariantSelector.java
java NativeVariantSelector
~~~

Đầu ra chính xác:

~~~text
native/linux/x86_64/glibc/libbridge.so
native/linux/aarch64/musl/libbridge.so
native/macos/aarch64/darwin/libbridge.dylib
native/windows/x86_64/msvc/bridge.dll
~~~

Đây là **dry run lựa chọn biến thể**, không phải bằng chứng file native nào đã nạp hoặc chạy được. Các input được chỉ định tường minh để kết quả chạy mẫu không phụ thuộc OS của máy học.

Khi đã có thư viện thật và thư mục `distribution/` chứa gói phù hợp, ví dụ trên **Linux glibc**:

~~~bash
java -Dnative.libc=glibc NativeVariantSelector distribution
~~~

Nếu binary được nạp thành công, dòng cuối có dạng:

~~~text
Loaded: native/linux/x86_64/glibc/libbridge.so
~~~

Kết quả minh họa này áp dụng cho **JVM Linux x86-64 glibc**, khi file và dependencies thực sự tồn tại. Ở môi trường khác, thông báo phản ánh target đang chạy hoặc chương trình có thể thất bại có chủ đích khi không có artifact phù hợp.

### Điểm phải hiểu đúng về ví dụ

1. `choose(...)` thuần Java chỉ **chọn tên đường dẫn**. Nó không tự phát hiện Linux libc, kiểm tra CPU instruction set, dependency hay binary format. `native.libc` phải do build/deployment đáng tin cậy cung cấp; nếu không rõ thì fail fast.
2. Các alias thường gặp được chuẩn hóa có chủ đích. Target khác (`riscv64`, `ppc64le`, ARM32…) báo chưa hỗ trợ, **không đoán**. `choose` cũng chưa xác minh release manifest có đủ gói; `toRealPath` ở bước nạp sẽ báo thiếu file.
3. Khi nạp thật, `System.load(...)` nhận đường dẫn tuyệt đối đến **file native tồn tại**. `toRealPath` giải quyết đường dẫn thực và kiểm tra symlink nằm trong root, nhưng **không thay thế kiểm tra chữ ký/SHA-256 hoặc kiểm toán nguồn artifact**.
4. Ví dụ dùng đường dẫn giả định `msvc` và `darwin` của dự án. Trên build thực, manifest phải ghi rõ biến thể có sẵn và các điều kiện runtime mà ba nhãn này chưa diễn tả.
5. Không nạp thử bản khác sau khi đã nạp lỗi: thông báo lỗi cần được giữ nguyên để xác định có sai kiến trúc, thiếu dependency hay bản native bị lỗi. Việc thử sai biến thể có thể gây lỗi khó chẩn đoán.

## 7. `System.loadLibrary` và `System.load` khác nhau thế nào?

Hai API liên quan nhưng có hợp đồng đầu vào khác nhau:

~~~java
// Tên logical, không có prefix/suffix và không phải đường dẫn file.
System.loadLibrary("bridge");

// Đường dẫn tuyệt đối đến một file native cụ thể.
System.load("/opt/app/native/linux/x86_64/glibc/libbridge.so");
~~~

| API | Ưu điểm | Điểm cần kiểm soát |
|---|---|---|
| `System.loadLibrary("bridge")` | Tên thư viện gọn, JVM tìm file theo cơ chế native library search của platform/JVM và map tên | `java.library.path`, search path, file thực được chọn, dependencies; khó thể hiện cả ma trận ABI qua một tên |
| `System.load("/absolute/path/...")` | Chỉ rõ chính xác file top-level do bộ chọn quyết định | Phải resolve file/path và xác minh nguồn tin cậy; linker của OS vẫn cần tìm được các dependencies |

`System.mapLibraryName("bridge")` giúp lấy tên file thông thường cho **platform hiện hành** (ví dụ `libbridge.so` trên Linux), nhưng **không tự chọn glibc/musl, kiến trúc khác, CPU feature hoặc phiên bản thư viện**.

`java.library.path` không phải một kho thông minh chứa metadata bản native; thay đổi thuộc tính này giữa runtime không nên được dùng làm cơ chế chọn phiên bản. Ngoài ra, binary có thể đã được nạp hoặc gắn với class loader; nạp/unload/hot-swap không tự do như thay một file JAR. Nếu cần thay phiên bản ABI lớn, cách an toàn thường là khởi động process mới với bộ binary đã kiểm thử.

### Thư viện nằm trong JAR

Một native file đặt tại `src/main/resources/native/...` rồi đóng gói vào JAR là **resource**, chưa phải file trên hệ thống mà `System.load` có thể trực tiếp dùng làm DLL/ELF/Mach-O. Quy trình thường là:

1. Chọn entry tài nguyên phù hợp theo target và manifest đã xác minh.
2. Giải nén đến một vị trí file có quyền phù hợp và tên tách biệt theo version/architecture; kiểm tra hash của binary.
3. Xử lý file path, symbolic links và quyền ghi để tránh một process khác thay thế thư viện giữa lúc kiểm tra và nạp.
4. `System.load` với đường dẫn tuyệt đối; dọn file tạm theo vòng đời ứng dụng, lưu ý Windows có thể giữ DLL được nạp cho đến khi process thoát.

Không tải và thực thi thư viện native từ URL không kiểm soát trong lúc khởi động, và không trích xuất nhiều phiên bản cùng một tên vào một thư mục dùng chung dễ có race condition.

## 8. Kiểm tra binary và dependencies trước khi nạp

Một bản build cần mang **evidence về target thực tế**. Tên folder có thể bị đặt sai; inspect header là bước kiểm tra độc lập.

### Linux (ELF)

~~~bash
file libbridge.so
readelf -h libbridge.so
readelf -d libbridge.so
readelf --version-info libbridge.so
~~~

Trong `readelf -h`, xem `Class` (ELF32/ELF64) và `Machine`; trong dynamic section xem `NEEDED`, `RPATH`/`RUNPATH` nếu có; trong version info xem yêu cầu `GLIBC_*` hoặc symbol version khác. `readelf` hiển thị metadata và không cần thực thi file đang kiểm tra. Với binary từ nguồn không tin cậy, đừng mặc định chạy `ldd` lên nó: một số môi trường/triển khai `ldd` có thể dẫn tới thực thi mã.

### macOS (Mach-O)

~~~bash
file libbridge.dylib
lipo -info libbridge.dylib
otool -hv libbridge.dylib
otool -L libbridge.dylib
~~~

`lipo -info` nêu slice kiến trúc hiện có, `otool -L` nêu dependencies; khi cần, kiểm tra minimum OS và code signature bằng công cụ phù hợp với môi trường macOS. Một universal binary không bảo đảm mọi slice có đúng ABI/dependencies cần thiết.

### Windows (PE)

Trong Developer Command Prompt có Visual Studio tools:

~~~bat
dumpbin /headers bridge.dll
dumpbin /dependents bridge.dll
dumpbin /exports bridge.dll
~~~

Kiểm tra machine type (x86/x64/ARM64), DLL phụ thuộc và exported JNI symbol. Cần runtime DLL chính xác; tên file `.dll` và đuôi giống nhau không chứng minh cùng architecture.

### Đối chiếu với JVM

- Kiểm tra `java -XshowSettings:properties -version` để biết kiến trúc/JVM đang chạy; không chỉ đọc kiến trúc OS host.
- Trên Linux container, kiểm tra libc và runtime của **container/process** nơi JVM thực chạy. Host dùng glibc không có nghĩa container Alpine dùng musl cũng vậy.
- Nếu app dùng nhiều `.so` cùng bộ, kiểm tra **transitive dependencies** và các thư viện hệ thống thực sự được loader tìm thấy. Một file top-level đúng target vẫn có thể thất bại do file phụ thuộc sai kiến trúc.

## 9. Xử lý lỗi nạp: đi từ thông báo đến nguyên nhân

Java thường báo `UnsatisfiedLinkError` khi không thể nạp/resolve native library, nhưng lỗi cụ thể rất khác nhau:

| Thông báo/triệu chứng | Khả năng cần kiểm tra | Hướng xử lý |
|---|---|---|
| `no bridge in java.library.path` | `System.loadLibrary` không tìm thấy top-level library theo search path | Xác nhận tên logical, mapping, path/cách đóng gói |
| `Can't load IA 32-bit .dll on a AMD 64-bit platform` hoặc tương đương | Sai kiến trúc 32/64-bit của JVM và DLL | Đối chiếu machine type với JVM hiện tại |
| `wrong ELF class: ELFCLASS32` | Nạp ELF32 vào tiến trình yêu cầu ELF64 | Chọn đúng kiến trúc/độ rộng |
| `invalid ELF header`, `not a valid Win32 application`, `wrong architecture` | Sai format, corrupted binary hoặc sai target | Đọc PE/ELF/Mach-O header và checksum |
| `GLIBC_2.xx not found` | Binary yêu cầu symbol glibc mới hơn môi trường | Rebuild trên baseline phù hợp hoặc nâng runtime theo chính sách |
| `libstdc++.so.6: cannot open shared object file` | Thiếu dependency hoặc loader không tìm thấy | Kiểm tra `NEEDED` và đóng gói/search path dependencies |
| `undefined symbol` | Thiếu/mismatch exported symbol hoặc ABI/native dependency | Kiểm tra export, JNI name/signature, phiên bản liên kết |
| `SIGILL` sau khi load hoặc khi gọi hàm | Binary dùng CPU instruction không được hỗ trợ | Xác nhận baseline/CPU features và build flags |
| Lỗi symbol JNI chỉ xuất hiện khi gọi method | JNI entry point/chữ ký không khớp dù library đã nạp | Dùng `javac -h` tạo header JNI, kiểm tra `JNIEXPORT`/`JNICALL` |

Ví dụ thông báo là dấu hiệu **cần xác minh**, không phải chẩn đoán duy nhất cho mọi nền tảng. Ngay cả khi OS loader báo không tìm thấy `bridge.dll`, file top-level có thể tồn tại nhưng **một dependency** bị thiếu; phải xem thông báo và công cụ phụ thuộc.

Mẫu xử lý của ứng dụng:

~~~java
try {
    System.load(absoluteTrustedLibraryPath);
} catch (UnsatisfiedLinkError error) {
    // Ghi lại os.name, os.arch, target/variant, đường dẫn đã chọn,
    // mã lỗi và thông báo đầy đủ; không nuốt nguyên nhân.
    throw new IllegalStateException(
            "Cannot load native variant for current JVM", error);
}
~~~

Đây là **đoạn minh họa** trong phương thức đã có biến `absoluteTrustedLibraryPath`; không phải chương trình Java độc lập. Tránh tự động bắt mọi `UnsatisfiedLinkError` để thử file của ABI khác, vì điều đó che giấu sự không tương thích và có thể làm việc khởi động khó kiểm soát.

## 10. Kiểm thử bằng ma trận thay vì chỉ build thành công

Một artifact được biên dịch thành công chưa được chứng minh tương thích khi nạp. Nên có hai nhóm kiểm thử độc lập:

**Kiểm thử bộ chọn (không cần native):**

| Input OS/arch/libc | Kết quả mong muốn |
|---|---|
| `Linux` / `amd64` / `glibc` | `linux/x86_64/glibc` |
| `Linux` / `aarch64` / `musl` | `linux/aarch64/musl` |
| `Mac OS X` / `arm64` / rỗng | `macos/aarch64/darwin` |
| `Windows 11` / `amd64` / rỗng | `windows/x86_64/msvc` |
| `Linux` / `amd64` / rỗng | Lỗi rõ: thiếu lựa chọn libc |
| `Linux` / `riscv64` / `glibc` | Lỗi rõ: kiến trúc chưa hỗ trợ |

**Kiểm thử native trên target thật:** với mỗi biến thể phát hành, chạy JVM tương ứng, gọi `System.load` hoặc `System.loadLibrary`, thực thi một hàm JNI/FFM có đầu vào–kết quả cố định, kiểm tra dependencies, runtime tối thiểu và tình huống thiếu/sai artifact. Nếu hỗ trợ Windows ARM64, macOS Rosetta hoặc Alpine musl, phải có test tương ứng thay vì suy ra từ một CI x86-64 glibc.

Ở CI, lưu lại manifest, SHA-256, compiler/toolchain, sysroot, flags kiến trúc, output của công cụ inspect binary và kết quả smoke test. Cập nhật một file `.so` mà không cập nhật các thông tin này sẽ khiến lỗi ABI khó tái hiện.

## 11. Quy trình áp dụng vào ứng dụng

1. **Định nghĩa support matrix**: OS, arch của JVM, libc/runtime, OS tối thiểu, CPU baseline và ABI version được phát hành; ghi rõ môi trường không hỗ trợ.
2. **Build đúng target và xác minh**: compile ở toolchain/sysroot có kiểm soát; inspect header, symbol/dependencies, chạy smoke test thực sự cho từng target.
3. **Đóng gói tường minh**: mỗi biến thể có resource path/tên riêng, manifest/version/checksum; không lẫn binary của platform khác.
4. **Nhận diện runtime**: chuẩn hóa `os.name` và `os.arch`; lấy thông tin libc/ABI từ nguồn đáng tin được cấu hình, không đoán từ CPU vật lý.
5. **Đối chiếu manifest**: chỉ chấp nhận variant có artifact, mức runtime/CPU tương thích và checksum đúng; từ chối target chưa hỗ trợ bằng thông báo cụ thể.
6. **Nạp một file đã chọn**: giải nén nếu ở trong JAR, giải quyết đường dẫn an toàn, gọi `System.load` một lần; bảo đảm loader tìm được dependencies tương ứng.
7. **Ghi log có ích và test hồi quy**: log target và phiên bản, đường dẫn thật và thông báo loader; kiểm thử trên các JVM/OS đã công bố hỗ trợ.

## 12. Tình huống thực hành

**Tình huống A — chạy Docker Alpine.** Trên host Ubuntu x86-64, ứng dụng Java chạy **bên trong Alpine Linux container**. `os.name=Linux` và `os.arch=amd64` có thể giống host, nhưng Alpine thường dùng musl. Bộ chọn phải lấy thông tin libc của runtime container rồi chọn `linux/x86_64/musl` (nếu được build) hoặc báo không hỗ trợ. Không chọn glibc chỉ vì host Ubuntu.

**Tình huống B — Mac Apple Silicon chạy Rosetta.** Mac vật lý ARM64, nhưng ứng dụng chạy JVM x86-64 dưới Rosetta 2. Native thư viện cần slice x86_64; chuyển sang JDK/JVM arm64 thì cần slice arm64. Không dùng một quy tắc đọc thông tin phần cứng máy để ép nạp arm64 trong tiến trình JVM x86_64.

**Tình huống C — cùng x86-64/glibc nhưng khác distro.** Một file `.so` build trên bản Linux rất mới yêu cầu `GLIBC_2.37`, còn runtime chỉ có symbol cũ hơn. Kiến trúc và libc family đều đúng nhưng loader vẫn từ chối. Giải pháp là build bằng baseline glibc được hỗ trợ, hoặc thay đổi mức yêu cầu runtime một cách có chủ đích, rồi chạy smoke test.

**Tình huống D — Windows x64 thiếu DLL phụ thuộc.** `bridge.dll` khớp x64 của JVM nhưng lỗi nạp. `dumpbin /dependents` cho thấy DLL runtime hoặc một thư viện đồng hành không hiện diện; cần bổ sung/cấu hình dependency tương ứng. Thử `bridge.dll` x86 32-bit sẽ không sửa được lỗi đó.

## 13. Câu hỏi tự kiểm tra

1. Một máy ARM64 chạy JVM x86-64 dưới trình giả lập. Nên chọn binary native nào? **Binary cho x86-64 của process**, với OS/ABI và dependencies tương thích.
2. `os.arch=amd64` có chứng minh thư viện Linux yêu cầu glibc thay vì musl không? **Không.** Cần thông tin libc/runtime độc lập.
3. `System.mapLibraryName("bridge")` đã xác định đúng version ABI chưa? **Chưa.** Nó chỉ map tên thư viện theo quy tắc platform hiện hành.
4. Vì sao `linux-x86_64-glibc` có thể vẫn chưa đủ để xác định một artifact nạp được? **Thiếu mức glibc, C++/native dependencies, ABI version và CPU baseline.**
5. Khi `System.loadLibrary("bridge")` báo lỗi, có nên lặp qua các DLL/SO khác theo thứ tự bất kỳ không? **Không.** Chẩn đoán nguyên nhân và chọn bằng manifest đã kiểm chứng.
6. Đặt `libbridge.so` trong JAR có cho phép `System.load` nhận đường dẫn resource bên trong JAR không? **Không.** Cần file thực trên filesystem hoặc cách packaging/load khác phù hợp.

## Ghi nhớ

- **Thư viện native phải khớp tiến trình JVM**, OS loader, ABI, runtime dependencies và mức CPU được hỗ trợ. “Đều 64-bit” không phải điều kiện đủ.
- Trên Linux, **phân biệt glibc/musl** và kiểm tra symbol version; trên macOS xét slice của JVM và deployment target; trên Windows xét PE machine type, runtime DLL và exports.
- `System.loadLibrary` và `System.load` nạp thư viện theo hai cách định danh khác nhau; cả hai **không tự sửa sai ABI**.
- **Chọn biến thể bằng manifest rõ ràng, xác minh binary thật, rồi nạp có kiểm soát**. Nếu không có bản phù hợp, báo unsupported thay vì đoán hoặc ép load.
