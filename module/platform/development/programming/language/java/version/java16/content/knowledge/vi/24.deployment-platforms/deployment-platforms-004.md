# Windows AArch64 port và ý nghĩa của chạy Java native trên ARM64

Java 16 đưa port Windows/AArch64 vào OpenJDK thông qua JEP 388. Thay đổi này giúp HotSpot chạy trực tiếp trên Windows dành cho bộ xử lý ARM64, thay vì chỉ có thể chạy một JDK x64 thông qua lớp giả lập. Nền tảng ARM64 vẫn được hỗ trợ trong các dòng JDK hiện đại, nhưng khi triển khai cần chọn đúng bản dựng JDK và đúng kiến trúc của các thư viện native đi kèm.

Trong ngữ cảnh này, “Java native trên ARM64” có nghĩa là tiến trình JVM được biên dịch cho kiến trúc ARM64. Nó không có nghĩa ứng dụng Java đã được biên dịch thành executable native bằng GraalVM Native Image. Bytecode Java vẫn giữ tính độc lập kiến trúc; JVM và mã native mà ứng dụng nạp mới phải phù hợp với kiến trúc tiến trình.

## 1. JEP 388 đã bổ sung điều gì?

Trước port Windows/AArch64, Windows trên máy ARM64 có thể chạy một số ứng dụng x86 thông qua giả lập, nhưng OpenJDK chưa có port HotSpot chính thức cho Windows ARM64 trong dòng chính. JEP 388 tích hợp hỗ trợ Windows/AArch64 vào OpenJDK 16.

Port này bao gồm phần triển khai nền tảng cần thiết để JVM hoạt động trên Windows ARM64, trong đó có HotSpot, bộ sinh mã JIT cho AArch64 và các phần tương tác với hệ điều hành. Đây là công việc ở tầng runtime/JVM, không yêu cầu thay đổi mã nguồn Java của ứng dụng chỉ vì chuyển từ CPU x64 sang ARM64.

Một số điểm cần nhớ:

- JEP 388 được đưa vào OpenJDK 16.
- Hỗ trợ Windows/AArch64 sau đó cũng được backport vào dòng OpenJDK 11; vì vậy đây không phải khả năng chỉ tồn tại ở Java 16.
- Port này dành cho Windows 64-bit trên ARM64, không phải Windows ARM 32-bit.
- Các bản phân phối JDK có thể khác nhau về phiên bản Windows, kiến trúc, công cụ đóng gói và thời gian hỗ trợ.

JEP 388 là một thay đổi nền tảng của JDK. Với ứng dụng mới, hãy dùng phiên bản LTS còn được nhà cung cấp hỗ trợ và kiểm tra ma trận Windows ARM64 của bản phân phối đó; không nên triển khai JDK 16 chỉ vì port được giới thiệu ở phiên bản này.

## 2. AArch64, ARM64 và x64 là gì?

`AArch64` là tên kiến trúc tập lệnh ARM 64-bit; `ARM64` là tên thường dùng trong hệ sinh thái Windows và công cụ của Microsoft. Hai tên này cùng chỉ nền tảng ARM 64-bit trong bối cảnh chọn JDK Windows.

`x64` là kiến trúc 64-bit thuộc họ x86 của Intel/AMD. Đây là kiến trúc khác với ARM64, dù cả hai đều là hệ thống 64-bit.

| Thuộc tính | Windows x64 | Windows ARM64 |
|---|---|---|
| CPU instruction set | x86-64 | AArch64/ARM64 |
| JDK native | Windows x64 JDK | Windows AArch64/ARM64 JDK |
| JNI DLL | DLL x64 | DLL ARM64 |
| Bytecode Java | Dùng được nếu JDK hỗ trợ class-file version | Dùng được nếu JDK hỗ trợ class-file version |
| Mã JIT | JVM sinh mã máy x64 | JVM sinh mã máy ARM64 |

Không nên nhầm `ARM64` với `ARM32`, `x86` hoặc `x64`. Một DLL có thể cùng định dạng PE nhưng vẫn không thể nạp vào tiến trình có kiến trúc khác.

## 3. JVM native ARM64 khác gì với chạy JDK x64 qua giả lập?

Trên Windows 11 ARM64, Windows có thể chạy ứng dụng x64 thông qua lớp giả lập. Khi chạy một JDK x64 theo cách này, chính tiến trình `java.exe` là tiến trình x64 được giả lập. JVM native ARM64 là tiến trình ARM64 thực thi trực tiếp trên CPU ARM64.

| Khía cạnh | JDK x64 chạy qua giả lập | JDK native ARM64 |
|---|---|---|
| Kiến trúc tiến trình | x64 | ARM64 |
| Thực thi lệnh | Windows dịch/giả lập lệnh x64 | CPU chạy lệnh ARM64 trực tiếp |
| JNI DLL cần dùng | DLL x64 | DLL ARM64 |
| Tương thích dependency cũ | Có thể thuận tiện nếu dependency chỉ có bản x64 | Cần dependency có bản ARM64 |
| Hiệu năng và năng lượng | Có chi phí giả lập tùy workload | Tránh chi phí giả lập, thường có lợi về hiệu năng và pin |
| Yêu cầu kiểm thử | Kiểm thử đúng tiến trình x64 và DLL x64 | Kiểm thử đúng tiến trình ARM64 và DLL ARM64 |

Giả lập giúp tận dụng phần mềm x64 chưa có bản ARM64. Tuy nhiên, nó không tự chuyển một DLL x64 thành DLL ARM64. Windows 11 trên ARM hỗ trợ giả lập ứng dụng x64; khả năng giả lập phụ thuộc phiên bản Windows và không nên suy ra từ việc thiết bị có CPU ARM64.

Chạy native thường giúp giảm chi phí giả lập, nhưng mức cải thiện thực tế phụ thuộc ứng dụng, JIT, I/O, thư viện native và cấu hình máy. Hãy benchmark workload đại diện trước khi quyết định thay đổi nền tảng.

## 4. Bytecode Java có cần biên dịch lại cho ARM64 không?

Thông thường không. File `.class` và JAR chứa bytecode Java không mang lệnh máy x64 hay ARM64. Cùng một JAR có thể chạy trên Windows x64 và Windows ARM64 nếu:

- JDK trên mỗi nền tảng hỗ trợ phiên bản bytecode của ứng dụng.
- Ứng dụng chỉ dùng API có trên JDK đích.
- Các dependency Java và tài nguyên tương thích với môi trường chạy.
- Mọi thành phần native được chọn đúng theo kiến trúc tiến trình.

HotSpot JIT biên dịch bytecode thành mã máy của kiến trúc đang chạy. Với JVM ARM64, mã được sinh ra là mã máy ARM64; ứng dụng không cần tự viết hai phiên bản Java source chỉ vì khác CPU.

Ví dụ, cùng một lớp Java:

```java
public class RuntimeArchitecture {
    public static void main(String[] args) {
        System.out.println("OS: " + System.getProperty("os.name"));
        System.out.println("Architecture: " + System.getProperty("os.arch"));
        System.out.println("Data model: "
                + System.getProperty("sun.arch.data.model") + " bit");
        System.out.println("Java home: " + System.getProperty("java.home"));
        System.out.println("VM: " + System.getProperty("java.vm.name"));
    }
}
```

Khi chạy bằng JDK x64, `os.arch` thường cho biết kiến trúc x64 như `amd64`; khi chạy bằng JDK ARM64, giá trị thường là `aarch64`. Tên cụ thể là thuộc tính do JDK cung cấp, vì vậy không nên viết logic ứng dụng chỉ dựa trên một chuỗi duy nhất nếu cần hỗ trợ nhiều nhà cung cấp.

## 5. Kiểm tra kiến trúc Windows, tiến trình Java và JDK đang được chọn

Trước khi điều tra lỗi native library, hãy xác định Windows là ARM64 hay x64 và `java.exe` nào đang được gọi.

Trong PowerShell:

```powershell
Get-CimInstance Win32_Processor |
    Select-Object Name, Architecture

Get-Command java -All |
    Select-Object Source

where.exe java
```

Trong thuộc tính `Win32_Processor.Architecture`, giá trị `12` đại diện ARM64 và `9` đại diện x64. Một máy ARM64 vẫn có thể đang gọi JDK x64 nếu `PATH` trỏ đến bản cài đặt x64 trước.

Kiểm tra JDK thực tế:

```powershell
java -version
java -XshowSettings:properties -version 2>&1 |
    findstr /I "os.arch os.name sun.arch.data.model java.home"
```

Đọc kết quả `os.arch`, `sun.arch.data.model` và `java.home` để xác nhận kiến trúc cùng thư mục JDK được sử dụng. Nếu máy có nhiều JDK, kiểm tra `JAVA_HOME`, thứ tự `PATH`, cấu hình IDE, Maven/Gradle daemon và cấu hình service; các tiến trình khác nhau có thể đang dùng các JDK khác nhau.

## 6. Native dependency và JNI phải khớp kiến trúc tiến trình

Mã JNI là mã native được đóng gói trong DLL trên Windows. Khi JVM gọi `System.loadLibrary` hoặc `System.load`, Windows phải nạp được DLL có kiến trúc tương thích với tiến trình JVM.

Ví dụ:

```java
public class NativeCodec {
    static {
        System.loadLibrary("codec");
    }

    public static native int encode(byte[] input, byte[] output);
}
```

Nếu chạy bằng JDK ARM64, `codec.dll` phải là DLL ARM64 và các DLL phụ thuộc của nó cũng phải tương thích. Nếu chạy bằng JDK x64 qua giả lập, DLL cần là bản x64. Một DLL ARM64 không thể được nạp vào tiến trình x64 và một DLL x64 thông thường không thể được nạp vào tiến trình ARM64.

Các dependency cần rà soát gồm:

- JNI/JNA do ứng dụng tự xây dựng hoặc thư viện bên thứ ba cung cấp.
- Java agent, profiler, APM agent và công cụ bảo mật có DLL native.
- Driver database, thư viện xử lý ảnh, codec, nén, mật mã hoặc network transport có native component.
- DLL được nạp gián tiếp bởi một DLL khác.
- Executable phụ trợ mà ứng dụng gọi qua `ProcessBuilder`.

Một dependency có JAR thuần Java vẫn có thể tải DLL từ resource theo `os.arch` hoặc giải nén DLL vào thư mục tạm khi chạy. Cần kiểm tra đúng phiên bản thư viện và đúng chức năng sử dụng, không chỉ nhìn vào phần mở rộng của artifact Maven/Gradle.

## 7. Kiểm tra kiến trúc DLL trên Windows

Trên Windows, native binary thường dùng định dạng PE/COFF. Có thể dùng `dumpbin` từ Visual Studio hoặc Visual Studio Build Tools để kiểm tra machine type và dependency của DLL.

```powershell
dumpbin /headers C:\app\native\codec.dll |
    findstr /I "machine"

dumpbin /dependents C:\app\native\codec.dll
```

Các machine type thường gặp:

| Giá trị PE machine | Kiến trúc |
|---|---|
| `AA64` | ARM64 |
| `8664` | AMD64/x64 |
| `14C` | x86 32-bit |

`dumpbin /dependents` liệt kê các DLL mà file yêu cầu. Cần kiểm tra tiếp kiến trúc và khả năng tìm thấy của từng dependency. Có thể dùng `llvm-readobj --file-headers --coff-imports` hoặc công cụ Dependencies để kiểm tra PE/import table nếu không có Visual Studio.

Một DLL chính là ARM64 nhưng một DLL phụ thuộc của nó lại là x64 vẫn không thể được nạp vào cùng tiến trình ARM64. Toàn bộ chuỗi native dependency phải tương thích với tiến trình và được tìm thấy theo cơ chế tìm kiếm DLL của Windows.

## 8. Build JNI cho Windows ARM64

Nếu thư viện bên thứ ba chưa có DLL ARM64, nhóm phát triển có thể cần build từ source hoặc yêu cầu nhà cung cấp phát hành bản tương thích. Việc build phải dùng toolchain tạo ra ARM64 binary; chỉ đổi tên DLL x64 hoặc copy file sang thư mục `arm64` không làm thay đổi kiến trúc.

Ví dụ mã native JNI đơn giản:

```java
public class NativeMath {
    public static native int add(int left, int right);
}
```

```c
#include <jni.h>

JNIEXPORT jint JNICALL
Java_NativeMath_add(JNIEnv *env, jclass type, jint left, jint right) {
    return left + right;
}
```

Quy trình build ở mức tổng quát:

1. Cài Visual Studio Build Tools và thành phần C++ hỗ trợ ARM64.
2. Mở Developer Command Prompt/PowerShell có target ARM64 hoặc cấu hình cross-compile từ host x64 sang ARM64.
3. Dùng `JAVA_HOME` trỏ đến JDK phù hợp và include JNI từ `$env:JAVA_HOME\include` cùng `$env:JAVA_HOME\include\win32`.
4. Build DLL bằng compiler/linker target ARM64.
5. Dùng `dumpbin /headers` xác nhận machine là `AA64`.
6. Kiểm tra toàn bộ DLL phụ thuộc và chạy integration test bằng JDK ARM64.

Ví dụ lệnh build cần chạy trong môi trường Visual Studio đã cấu hình target ARM64:

```cmd
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" NativeMath.c /link /OUT:NativeMath.dll
```

Lệnh trên chỉ minh họa cách truyền JNI include và tạo DLL. Kiến trúc đầu ra do môi trường compiler/linker đã chọn quyết định; phải xác nhận bằng `dumpbin`, không suy luận từ tên Developer Prompt hoặc tên file.

## 9. Chọn bản phân phối JDK cho Windows ARM64

Không phải mọi nhà cung cấp JDK đều phát hành mọi tổ hợp phiên bản Java, hệ điều hành và kiến trúc. Hãy kiểm tra bảng tải xuống của vendor và chọn rõ Windows AArch64/ARM64.

Tại thời điểm cập nhật bài học (tháng 11/2026), trang tải Microsoft Build of OpenJDK liệt kê gói Windows AArch64 cho Java 25 LTS, gồm EXE, MSI và ZIP. Trang tải Azul Zulu cũng liệt kê JDK Java 25 LTS cho Windows ARM 64-bit. Đây là các ví dụ về lựa chọn hiện có; trước khi triển khai, vẫn cần xác nhận patch mới nhất, kiến trúc, checksum/chữ ký và chính sách hỗ trợ của nhà cung cấp.

| Nhà cung cấp | Điều cần kiểm tra |
|---|---|
| Microsoft Build of OpenJDK | Windows AArch64/ARM64 trong bảng tải xuống của đúng major version; gói cài đặt và checksum/chữ ký |
| Azul Zulu | Chọn Windows, ARM 64-bit, JDK/JRE và phiên bản LTS cụ thể |
| Các nhà cung cấp khác | Xác nhận có binary Windows AArch64 cho chính phiên bản Java cần dùng; không suy ra từ việc họ có Linux ARM64 hoặc macOS AArch64 |

Java 25 là LTS phù hợp cho hệ thống mới nếu framework và dependency đã tương thích. Java 21 cũng là LTS có thể chọn khi ứng dụng cần duy trì nền tảng 21. Java 16 là feature release đã qua thời gian hỗ trợ thông thường; không dùng nó làm runtime production mới chỉ vì JEP 388 được đưa vào phiên bản này.

## 10. Đóng gói và triển khai ứng dụng Java ARM64

JAR thuần Java thường có thể dùng chung giữa Windows x64 và Windows ARM64. Tuy nhiên, nếu ứng dụng đi kèm runtime image, DLL native hoặc executable phụ trợ, gói triển khai phải khớp kiến trúc đích.

Khi dùng `jlink` để tạo runtime riêng, hãy dùng JDK cho đúng hệ điều hành và kiến trúc target để tạo runtime image. Khi dùng `jpackage` trên Windows, tạo gói cài đặt trong môi trường Windows/JDK phù hợp với kiến trúc muốn phát hành và kiểm tra gói kết quả trên thiết bị ARM64 thật hoặc máy ảo ARM64.

Một chiến lược phân phối có thể là:

- Phân phối JAR thuần Java dùng chung nếu không có thành phần native.
- Phân phối runtime và installer riêng cho `x64` và `ARM64` nếu đóng gói JVM cùng ứng dụng.
- Đóng gói DLL theo từng kiến trúc và chọn đúng artifact trong pipeline build/release.
- Ghi rõ kiến trúc hỗ trợ trong tài liệu cài đặt và kiểm tra trước khi khởi chạy.

Không đặt DLL x64 và ARM64 cùng tên vào một thư mục native chung rồi để hệ thống chọn ngẫu nhiên. Hãy phân tách artifact theo kiến trúc, ví dụ `native/windows-x64` và `native/windows-arm64`, sau đó chọn dựa trên runtime đã được xác minh.

## 11. Kiểm thử trên Windows ARM64

Kiểm thử bằng JDK x64 chạy giả lập không xác nhận được ứng dụng hoạt động với JDK ARM64. Để xác nhận native deployment, cần chạy test bằng chính JDK ARM64 và DLL ARM64 trên Windows ARM64.

Checklist kiểm thử:

- `java -version` hiển thị đúng bản phân phối và phiên bản mong muốn.
- `os.arch`, `sun.arch.data.model` và `java.home` cho thấy tiến trình Java đang chạy bằng JDK ARM64.
- Ứng dụng khởi động, biên dịch/JIT và chạy các luồng nghiệp vụ chính.
- JNI/JNA và toàn bộ DLL phụ thuộc được nạp thành công.
- Java agent, profiler, APM agent và công cụ giám sát tương thích với ARM64.
- Các executable gọi qua `ProcessBuilder` có bản ARM64 hoặc được hỗ trợ trên Windows 11 ARM.
- Cài đặt, nâng cấp, gỡ cài đặt và service startup hoạt động trên thiết bị ARM64.
- Đo thời gian khởi động, throughput, latency, CPU và mức tiêu thụ pin trên workload đại diện.
- Chạy thêm test x64 emulated nếu sản phẩm cam kết hỗ trợ cả hai chế độ.

Nên dùng Windows ARM64 vật lý hoặc máy ảo Windows 11 ARM64 để kiểm thử. Emulation có ích cho compatibility test, nhưng không thay thế test native vì process architecture và DLL được nạp khác nhau.

## 12. Ghi nhớ

- JEP 388 đưa port Windows/AArch64 vào OpenJDK 16; hỗ trợ sau đó cũng được backport vào dòng JDK 11.
- ARM64/AArch64 và x64 là hai kiến trúc khác nhau dù đều là 64-bit.
- Bytecode Java thường dùng chung; JVM, runtime image và DLL native phải đúng kiến trúc.
- Windows 11 ARM có thể chạy ứng dụng x64 qua giả lập, nhưng giả lập không chuyển DLL x64 thành DLL ARM64.
- Dùng JDK ARM64 và DLL ARM64 cho tiến trình native ARM64.
- Kiểm tra PE machine type bằng `dumpbin` hoặc `llvm-readobj` và kiểm tra toàn bộ DLL phụ thuộc.
- Chọn JDK LTS còn được hỗ trợ, xác nhận rõ vendor có Windows ARM64 build và kiểm thử trên thiết bị ARM64.
- Đánh giá `jlink`, `jpackage`, JNI và executable phụ trợ theo kiến trúc của gói triển khai.

## Tài liệu tham khảo

- [JEP 388: Windows/AArch64 Port](https://openjdk.org/jeps/388) — port Windows ARM64 được tích hợp vào OpenJDK 16.
- [Microsoft OpenJDK for Windows on ARM64](https://github.com/microsoft/openjdk-aarch64) — thông tin port, lịch sử backport và nền tảng Windows ARM64.
- [Download the Microsoft Build of OpenJDK](https://learn.microsoft.com/en-us/java/openjdk/download) — gói JDK Windows AArch64 và checksum/chữ ký.
- [Azul Zulu Downloads](https://www.azul.com/downloads/) — lựa chọn Windows ARM 64-bit cho các bản Java LTS.
- [Microsoft: How emulation works on Arm](https://learn.microsoft.com/en-us/windows/arm/apps-on-arm-x86-emulation) — giới hạn và cách hoạt động của giả lập x86/x64 trên Windows ARM.
- [Microsoft: Add Arm support to your Windows app](https://learn.microsoft.com/en-us/windows/arm/add-arm-support) — native ARM64, dependency và kiểm thử ứng dụng trên Windows ARM.
