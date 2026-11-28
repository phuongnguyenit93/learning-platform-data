# Phân biệt kiến trúc JVM, bytecode ứng dụng và native library

Khi triển khai Java trên nhiều hệ điều hành hoặc kiến trúc CPU, cần phân biệt ba thành phần: kiến trúc của JVM, bytecode trong ứng dụng và mã native mà ứng dụng nạp. Một JAR chứa bytecode Java thuần thường có thể dùng trên nhiều nền tảng, nhưng bản thân JVM là chương trình native được xây dựng cho hệ điều hành và CPU cụ thể. JNI/JNA, Java agent có mã native và các thư viện `.so`, `.dll`, `.dylib` phải tương thích với kiến trúc của tiến trình JVM cùng ABI của hệ điều hành.

Hiểu ba lớp này giúp xác định thành phần nào có thể dùng chung, thành phần nào phải build hoặc tải riêng theo target. Đây là nguyên tắc vẫn áp dụng trên các JDK hiện đại, từ Java 16 đến những bản LTS mới hơn.

## 1. Ba lớp cần phân biệt

| Thành phần | Nội dung | Phụ thuộc CPU/OS? | Cách phân phối thường gặp |
|---|---|---|---|
| Bytecode ứng dụng | File `.class`, JAR, WAR chứa mã JVM và tài nguyên | Bản thân bytecode không gắn với một CPU cụ thể; vẫn phụ thuộc phiên bản class-file và API của JDK | Thường dùng chung giữa các nền tảng có JDK tương thích |
| JVM | HotSpot hoặc một JVM implementation khác, gồm interpreter, JIT và runtime | Có. Mỗi tổ hợp OS/CPU cần bản dựng phù hợp | JDK/JRE riêng cho Windows x64, Windows ARM64, Linux x64, Linux ARM64, macOS ARM64... |
| Native library | JNI/JNA, agent native, shared library hoặc executable phụ trợ | Có. Cần đúng định dạng binary, kiến trúc, ABI và dependency hệ thống | Binary riêng theo OS/CPU/libc hoặc artifact chứa nhiều biến thể native |

Ví dụ, cùng một file `orders-service.jar` có thể chạy trên Windows x64 và Linux ARM64 nếu cả hai môi trường có JDK tương thích và ứng dụng không phụ thuộc native binary không phù hợp. Nhưng không thể lấy `java.exe` Windows x64 hoặc `libjvm.so` Linux x64 rồi dùng trực tiếp trên Linux ARM64.

## 2. Bytecode Java độc lập kiến trúc như thế nào?

Compiler `javac` chuyển mã nguồn Java thành bytecode trong file `.class`. Bytecode là tập lệnh của máy ảo Java, không phải tập lệnh CPU như x86-64 hay AArch64. JVM đọc và thực thi bytecode bằng interpreter, hoặc biên dịch các đoạn mã thường chạy thành mã máy bằng JIT.

Vì vậy, một JAR thuần Java thường không cần build lại chỉ vì chuyển từ Windows x64 sang Linux ARM64. Điều kiện là JDK đích phải hiểu phiên bản class-file của ứng dụng và cung cấp các API mà ứng dụng sử dụng.

Ví dụ, có thể biên dịch ứng dụng với một mức API Java xác định:

```sh
javac --release 21 -d out src/com/example/Main.java
jar --create --file app.jar --main-class com.example.Main -C out .
```

`--release 21` xác định mức ngôn ngữ, phiên bản bytecode và tập API Java được phép sử dụng theo release 21. Tùy chọn này không tạo bytecode x64 hay ARM64. Cùng `app.jar` có thể chạy trên JDK 21 tương thích ở nhiều hệ điều hành và kiến trúc.

Nếu chạy ứng dụng trên JDK quá cũ so với class-file, JVM có thể ném `UnsupportedClassVersionError`. Nếu bytecode tương thích nhưng ứng dụng gọi API không có trong JDK đích, lỗi có thể xuất hiện khi biên dịch, liên kết hoặc thực thi tùy cách sử dụng API.

### Multi-release JAR không phải cơ chế chọn kiến trúc CPU

Multi-release JAR có thể chứa nhiều phiên bản class cho các mức Java khác nhau, được đặt dưới `META-INF/versions/`. JVM chọn class phù hợp với phiên bản Java đang chạy. Cơ chế này giải quyết khác biệt phiên bản JDK, không tự chọn binary x64 hay ARM64.

Nếu một thư viện cần cả biến thể Java khác nhau và native library theo CPU, hai cơ chế cần được xử lý riêng: multi-release JAR cho class Java, còn native loader hoặc dependency packaging phải chọn đúng binary theo nền tảng.

## 3. JVM là chương trình native theo từng nền tảng

JVM được biên dịch thành mã máy cho hệ điều hành và kiến trúc cụ thể. Ví dụ:

- Windows x64 dùng executable và DLL của Windows x64.
- Windows ARM64 dùng executable và DLL ARM64.
- Linux x86-64 dùng binary ELF x86-64.
- Linux AArch64 dùng binary ELF AArch64.
- macOS Apple Silicon dùng binary ARM64 hoặc universal binary phù hợp.

Khi JVM chạy, interpreter đọc bytecode và JIT biên dịch mã nóng thành mã máy của kiến trúc tiến trình. Vì vậy, cùng một JAR có thể được JIT thành mã x64 trên một máy và mã ARM64 trên máy khác mà không cần thay đổi bytecode ban đầu.

Điều này cũng có nghĩa JDK/JRE là artifact theo nền tảng. Một runtime image tạo cho Linux ARM64 không thể mặc nhiên được copy sang Windows x64 hoặc macOS ARM64. Khi dùng `jlink`, hãy tạo runtime từ JDK và các module thuộc đúng nền tảng đích. Khi đóng gói installer bằng `jpackage`, cần tuân theo yêu cầu nền tảng và kiến trúc của định dạng gói muốn tạo.

## 4. Native library phải khớp kiến trúc của tiến trình JVM

Native library là mã máy được nạp vào cùng tiến trình với JVM. Do đó, kiến trúc của nó phải tương thích với kiến trúc tiến trình JVM, không chỉ với CPU vật lý của máy.

Ví dụ trên Windows ARM64:

- Nếu chạy JDK ARM64 native, JNI DLL phải là ARM64.
- Nếu chạy JDK x64 thông qua Windows x64 emulation, JNI DLL phải là x64.

Windows không thể nạp một DLL ARM64 vào tiến trình x64 hoặc một DLL x64 thông thường vào tiến trình ARM64. Cùng nguyên tắc áp dụng cho Linux `.so` và macOS `.dylib`.

Ngoài CPU, native library còn phải phù hợp với:

- Định dạng binary và ABI của hệ điều hành: PE/COFF trên Windows, ELF trên Linux, Mach-O trên macOS.
- C library trên Linux, chẳng hạn glibc hoặc musl.
- Các shared library hoặc runtime mà binary phụ thuộc.
- Phiên bản API hệ điều hành và mức triển khai tối thiểu mà binary yêu cầu.
- Quyền truy cập, vị trí tìm kiếm và chính sách bảo mật của tiến trình.

Một `.so` đúng kiến trúc AArch64 vẫn có thể không nạp được trên Alpine nếu nó được build cho glibc và phụ thuộc loader/symbol của glibc. Tương tự, một DLL ARM64 vẫn có thể thất bại nếu thiếu DLL phụ thuộc hoặc yêu cầu API Windows không có trên phiên bản hệ điều hành đang chạy.

## 5. JNI, JNA và thư viện native được đóng gói trong JAR

JNI cho phép mã Java gọi hàm native trong thư viện được nạp bằng `System.load` hoặc `System.loadLibrary`:

```java
public final class ImageCodec {
    static {
        System.loadLibrary("imagecodec");
    }

    private ImageCodec() {
    }

    public static native byte[] resize(byte[] image, int width, int height);
}
```

File `imagecodec` phải được build cho đúng OS/CPU/ABI của JVM. Với Linux, file thường là `libimagecodec.so`; Windows dùng `imagecodec.dll`; macOS dùng `libimagecodec.dylib`.

JNA cung cấp cách gọi native function qua Java mà không cần tự viết JNI wrapper cho từng hàm, nhưng thư viện native mà JNA tải vẫn phải đúng nền tảng. Dùng JNA không làm binary x64 trở thành ARM64 hoặc binary glibc trở thành musl.

Một số thư viện đóng gói nhiều native binary bên trong JAR và chọn một file khi chạy dựa trên OS/architecture. Một số thư viện khác phát hành artifact riêng qua classifier hoặc module riêng. Cần đọc tài liệu đúng version để biết dependency nào phải khai báo và cách thư viện chọn binary.

Ví dụ về cách tổ chức artifact theo target (tên classifier chỉ mang tính minh họa; dùng đúng tọa độ do nhà cung cấp công bố):

| Target | Native artifact cần chọn |
|---|---|
| Windows x64 | `windows-x86_64` |
| Windows ARM64 | `windows-aarch64` |
| Linux x64 glibc | `linux-x86_64` |
| Linux ARM64 musl | `linux-aarch64-musl` |
| macOS ARM64 | `osx-aarch64` |

Không phải mọi thư viện đều dùng các tên classifier này. Hãy kiểm tra nội dung artifact, checksum, kiến trúc và ABI của binary thật.

## 6. Ví dụ kiểm tra nền tảng của JVM đang chạy

Có thể đọc các system property để ghi nhận hệ điều hành, kiến trúc mà JVM nhìn thấy và vị trí JDK:

```java
public class RuntimePlatformInfo {
    public static void main(String[] args) {
        System.out.println("OS name: " + System.getProperty("os.name"));
        System.out.println("OS version: " + System.getProperty("os.version"));
        System.out.println("OS architecture: " + System.getProperty("os.arch"));
        System.out.println("Java version: " + System.getProperty("java.version"));
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("VM name: " + System.getProperty("java.vm.name"));
    }
}
```

`os.arch` phản ánh kiến trúc mà runtime báo cáo. Giá trị thường gặp gồm `amd64` hoặc `x86_64` cho x64 và `aarch64` cho ARM64, nhưng tên có thể khác giữa nhà cung cấp và nền tảng. Nếu viết logic chọn native artifact, nên chuẩn hóa các alias đã xác nhận và xử lý trường hợp không nhận diện được thay vì giả định một chuỗi duy nhất.

Để xác định JDK được gọi từ shell:

```sh
java -version
java -XshowSettings:properties -version
```

Kiểm tra `java.home`, `os.name`, `os.arch` và `java.version`. Trên máy có nhiều JDK, cũng cần kiểm tra `JAVA_HOME`, `PATH`, cấu hình service, IDE và tiến trình Maven/Gradle vì mỗi tiến trình có thể sử dụng một JDK khác.

Không nên chỉ dựa vào kiến trúc CPU của máy chủ. Một tiến trình x64 chạy qua emulation trên máy ARM64 vẫn cần binary native x64. Điều cần khớp là kiến trúc tiến trình JVM thực tế.

## 7. Phân biệt JVM native, Java bytecode và Native Image

Ba khái niệm thường bị nhầm:

| Khái niệm | Cách chạy | Yêu cầu triển khai |
|---|---|---|
| Java bytecode trên JVM | JVM diễn giải hoặc JIT biên dịch bytecode khi chạy | Cần JDK/JRE đúng OS/CPU; JAR thuần Java thường dùng chung |
| JVM native ARM64 | Bản thân JVM được build cho ARM64 | Cần JDK ARM64 và native dependency ARM64 |
| GraalVM Native Image | Biên dịch ứng dụng và phần runtime cần thiết thành executable native trước khi chạy | Tạo executable riêng theo OS/CPU; kiểm tra hỗ trợ dynamic features và native dependency |

Khi nói “chạy Java native trên ARM64” trong ngữ cảnh port JVM, thường đang nói về JVM ARM64. Điều này không đồng nghĩa ứng dụng đã được chuyển thành executable Native Image.

Native Image là một cách đóng gói và thực thi khác. Executable tạo ra không phải file JAR bytecode portable; cần build cho target OS/architecture và quản lý native dependency theo nền tảng. Việc chọn Native Image phải xét thêm reflection, resource, dynamic proxy, serialization, JNI và các tính năng cần cấu hình khi build.

## 8. ProcessBuilder và executable phụ trợ

Một ứng dụng Java có thể gọi chương trình bên ngoài qua `ProcessBuilder`. Executable đó chạy thành tiến trình riêng, không được nạp vào cùng tiến trình JVM như JNI library.

```java
import java.io.IOException;

public class ExternalCommandDemo {
    public static void main(String[] args) throws IOException, InterruptedException {
        Process process = new ProcessBuilder("git", "--version")
                .redirectErrorStream(true)
                .start();

        int exitCode = process.waitFor();
        System.out.println("git exit code: " + exitCode);
    }
}
```

Executable phụ trợ phải được hệ điều hành đích chạy được. Nó có thể là binary theo kiến trúc khác nếu hệ điều hành hỗ trợ emulation cho loại tiến trình đó, nhưng không thể giả định điều này trên mọi nền tảng. Ngoài kiến trúc, cần kiểm tra đường dẫn, quyền thực thi, DLL/shared library phụ thuộc và cách xử lý stdout/stderr.

Điểm khác biệt quan trọng: JNI DLL hoặc `.so` phải tương thích với kiến trúc của JVM process; executable do `ProcessBuilder` khởi chạy là process riêng và tuân theo khả năng chạy binary của hệ điều hành.

## 9. Ma trận build và triển khai đa nền tảng

Với một ứng dụng có native dependency, nên xác định target ngay trong pipeline build/release:

| Target triển khai | Bytecode ứng dụng | JVM/runtime | Native dependency |
|---|---|---|---|
| Windows x64 | JAR dùng chung nếu JDK/API tương thích | Windows x64 JDK/JRE | DLL x64 |
| Windows ARM64 | JAR dùng chung nếu JDK/API tương thích | Windows ARM64 JDK/JRE | DLL ARM64 nếu JVM native ARM64 |
| Linux x64 glibc | JAR dùng chung nếu JDK/API tương thích | Linux x64 glibc JDK/JRE | `.so` x64 build cho ABI phù hợp |
| Linux ARM64 musl | JAR dùng chung nếu JDK/API tương thích | Linux ARM64 musl JDK/JRE | `.so` ARM64 musl |
| macOS ARM64 | JAR dùng chung nếu JDK/API tương thích | macOS ARM64 JDK/JRE | `.dylib` ARM64 |

Nếu ứng dụng không có native dependency và chỉ phát hành JAR, pipeline có thể build artifact một lần rồi kiểm thử trên nhiều target. Nếu có native code, có thể vẫn dùng chung JAR nhưng cần build, tải hoặc đóng gói native artifact riêng theo target.

Một pipeline CI đa nền tảng nên:

1. Build bytecode với `--release` phù hợp và tạo JAR ứng dụng.
2. Xác định target OS, CPU, libc/ABI và JDK vendor/version.
3. Lấy native dependency đúng target hoặc build từ source bằng toolchain tương ứng.
4. Tạo runtime image bằng JDK đúng nền tảng nếu dùng `jlink`.
5. Đóng gói installer bằng công cụ và môi trường phù hợp target nếu dùng `jpackage`.
6. Chạy unit/integration test trên runner hoặc máy ảo đúng kiến trúc và OS.
7. Lưu artifact theo tên target rõ ràng và checksum/digest để phát hành, rollback.

Ví dụ cách đặt tên artifact:

```text
orders-service-2.4.0.jar
orders-service-2.4.0-windows-x64.zip
orders-service-2.4.0-windows-arm64.zip
orders-service-2.4.0-linux-x64-glibc.tar.gz
orders-service-2.4.0-linux-arm64-musl.tar.gz
```

Nếu các gói nền tảng chỉ khác runtime và native library, có thể giữ chung phiên bản JAR rồi đóng gói các thành phần nền tảng bên ngoài. Cách tổ chức cụ thể phụ thuộc yêu cầu cài đặt và cập nhật của ứng dụng.

## 10. Lỗi thường gặp khi trộn sai kiến trúc

| Triệu chứng | Nguyên nhân thường gặp | Hướng điều tra |
|---|---|---|
| `UnsupportedClassVersionError` | JDK chạy ứng dụng quá cũ so với class-file version | Kiểm tra `java -version`, build JDK và `--release` |
| `UnsatisfiedLinkError` | Không tìm thấy native library, sai kiến trúc, sai ABI hoặc thiếu dependency | Kiểm tra đường dẫn nạp, kiến trúc và dependency của `.so`/DLL |
| Windows báo `Bad Image` hoặc không thể nạp DLL | DLL sai kiến trúc, thiếu dependency hoặc binary không hợp lệ | Kiểm tra PE machine type và danh sách DLL phụ thuộc |
| Linux báo `wrong ELF class` hoặc `Exec format error` | Binary sai word size/CPU hoặc executable không đúng kiến trúc | Dùng `file`, `readelf -h` và xác nhận target |
| `Error loading shared library` hoặc symbol không tìm thấy | Sai libc/ABI hoặc thiếu shared library | Kiểm tra loader, `NEEDED`, glibc/musl và phiên bản dependency |
| Chỉ một chức năng mới lỗi | Native library chỉ được nạp khi chức năng đó chạy | Tạo integration test bao phủ đường chức năng và kiểm tra runtime load |

Không phải lỗi nào khi chạy trên ARM64 cũng do bytecode. Nếu ứng dụng khởi động được nhưng lỗi khi nạp một `.dll` hoặc `.so`, hãy kiểm tra native dependency trước khi biên dịch lại mã Java.

## 11. Checklist trước khi phát hành

- [ ] Xác nhận JDK vendor, version, OS và kiến trúc của tiến trình thực tế.
- [ ] Xác nhận class-file version và API Java mà ứng dụng yêu cầu.
- [ ] Lập danh sách JNI/JNA, Java agent native và native library bắc cầu.
- [ ] Kiểm tra định dạng binary, CPU architecture, ABI/libc và shared-library dependencies.
- [ ] Xác nhận executable phụ trợ tương thích với hệ điều hành đích.
- [ ] Tạo runtime image và installer đúng target nếu ứng dụng đóng gói JVM.
- [ ] Chạy integration test trên từng target OS/CPU/libc được hỗ trợ.
- [ ] Ghi rõ target trong artifact name, release metadata và tài liệu vận hành.

## 12. Ghi nhớ

- Bytecode Java không gắn với x64 hay ARM64; nó phụ thuộc class-file version và API của JDK.
- JVM là chương trình native, cần JDK/JRE phù hợp OS và CPU.
- JIT sinh mã máy theo kiến trúc của JVM đang chạy.
- JNI/JNA library được nạp vào JVM phải khớp kiến trúc tiến trình và ABI hệ điều hành.
- Executable gọi qua `ProcessBuilder` là process riêng, tuân theo khả năng chạy binary của OS.
- JAR thuần Java thường dùng chung; runtime image, installer và native artifact có thể cần gói riêng.
- Native Image là mô hình biên dịch/đóng gói khác với chạy bytecode trên JVM.

Khi tách rõ bytecode, JVM và native dependency, việc triển khai Java đa nền tảng trở nên dễ dự đoán hơn. Hãy dùng chung JAR khi có thể, tạo runtime và native artifact đúng target, rồi xác nhận bằng kiểm thử trên chính môi trường triển khai.
