# Kiểm tra java -version, os.arch và kiến trúc runtime trong gói

Khi triển khai ứng dụng Java, lệnh `java -version` chỉ cho biết phiên bản và nhà cung cấp của lệnh Java đang được gọi. Nó không phải lúc nào cũng cho biết đầy đủ kiến trúc CPU, đường dẫn JDK mà service thực sự dùng hoặc runtime đã được đóng gói bên trong ứng dụng. Để xác nhận môi trường chạy, cần kiểm tra `java.home`, `os.arch`, tiến trình JVM đang hoạt động và binary runtime trong gói triển khai.

Việc này đặc biệt quan trọng khi một máy có nhiều JDK, chạy ứng dụng qua service manager, dùng Windows ARM64 với giả lập x64, hoặc đóng gói runtime bằng `jlink`/`jpackage`. Các nguyên tắc và công cụ dưới đây vẫn dùng được trên các JDK hiện đại; Java 16 là feature release đã hết thời gian hỗ trợ thông thường nên không nên dùng làm runtime production mới chỉ vì bài học thuộc module Java 16.

## 1. Vì sao chỉ chạy java -version chưa đủ?

Một máy có thể cài đồng thời nhiều bản JDK, ví dụ JDK 21 x64 và JDK 25 ARM64. Lệnh `java` trong terminal phụ thuộc vào `PATH`, alias hoặc cấu hình shell. Ứng dụng chạy như Windows Service, systemd service, container hoặc launcher do `jpackage` tạo có thể sử dụng một đường dẫn Java hoàn toàn khác.

Ngoài ra, output cơ bản của `java -version` thường hiển thị:

- Phiên bản Java và build number.
- Nhà cung cấp JDK.
- Runtime/VM name.

Thông tin đó không đảm bảo hiển thị kiến trúc CPU. Vì vậy, khi điều tra lỗi native library hoặc xác minh triển khai ARM64, cần đọc thêm system properties của chính JVM.

Các thuộc tính hữu ích:

| Thuộc tính | Ý nghĩa |
|---|---|
| `java.version` | Phiên bản Java runtime |
| `java.runtime.version` | Phiên bản runtime đầy đủ, thường gồm build/update information |
| `java.vendor` | Nhà cung cấp JDK |
| `java.home` | Thư mục runtime mà JVM hiện tại sử dụng |
| `java.vm.name` | Tên implementation của VM |
| `os.name` | Hệ điều hành mà JVM nhận diện |
| `os.arch` | Kiến trúc mà JVM process báo cáo, ví dụ `amd64` hoặc `aarch64` |
| `sun.arch.data.model` | Thuộc tính chẩn đoán thường gặp trên HotSpot, thường là `32` hoặc `64`; không nên dùng làm API portable của ứng dụng |

`os.arch` phản ánh kiến trúc runtime/process mà JVM báo cáo. Trên máy ARM64 chạy JDK x64 qua giả lập, JVM có thể báo `amd64`; điều này có ý nghĩa hơn kiến trúc CPU vật lý khi xác định loại DLL hoặc `.so` mà tiến trình có thể nạp.

## 2. Kiểm tra JDK mà terminal đang chọn

Trước tiên hãy xác định lệnh `java` nào được shell tìm thấy. Đừng giả định `JAVA_HOME` luôn là đường dẫn mà lệnh `java` đang dùng; thứ tự `PATH`, shim và cấu hình công cụ có thể làm hai giá trị khác nhau.

### Windows PowerShell

```powershell
$env:JAVA_HOME
Get-Command java -All | Format-Table CommandType, Source
where.exe java
```

`Get-Command` cho biết PowerShell phân giải lệnh nào; `where.exe` liệt kê các file `java.exe` được tìm thấy trên `PATH`. Nếu có nhiều kết quả, lệnh đầu tiên thường là lệnh được gọi khi nhập `java`.

Có thể lưu đường dẫn executable được chọn và chạy bằng đường dẫn tuyệt đối:

```powershell
$java = (Get-Command java -CommandType Application | Select-Object -First 1).Source
& $java -version
& $java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|java.version|java.vendor|java.vm.name|os.name|os.arch|sun.arch.data.model'
```

### Linux

```sh
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
command -v java
type -a java
readlink -f "$(command -v java)"
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|java.version|java.vendor|java.vm.name|os.name|os.arch|sun.arch.data.model'
```

`readlink -f` giúp lần theo symlink trên các hệ thống có hỗ trợ tùy chọn này. Một số hệ thống Unix không có `readlink -f`; khi đó hãy kiểm tra symlink bằng công cụ của hệ điều hành hoặc dùng đường dẫn JDK đã cấu hình.

### macOS

```sh
/usr/libexec/java_home -V
command -v java
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|java.version|java.vendor|java.vm.name|os.name|os.arch'
```

`/usr/libexec/java_home -V` liệt kê các JDK được macOS nhận diện. Lệnh `java` trong shell vẫn có thể trỏ đến một runtime khác do `PATH` hoặc cấu hình người dùng.

## 3. Đọc os.arch từ chính ứng dụng

Lệnh shell chỉ kiểm tra runtime được gọi trong shell đó. Để biết ứng dụng đang chạy bằng kiến trúc nào, hãy ghi nhận system properties ngay trong tiến trình ứng dụng.

```java
public class RuntimeInfo {
    public static void main(String[] args) {
        print("java.version");
        print("java.runtime.version");
        print("java.vendor");
        print("java.home");
        print("java.vm.name");
        print("os.name");
        print("os.version");
        print("os.arch");

        // Thuộc tính HotSpot thường có, chỉ dùng để chẩn đoán.
        print("sun.arch.data.model");

        System.out.println("Runtime.version=" + Runtime.version());
    }

    private static void print(String name) {
        System.out.println(name + "=" + System.getProperty(name));
    }
}
```

Ví dụ output rút gọn khi chạy JDK ARM64:

```text
java.version=25.0.1
java.vendor=Example JDK Vendor
java.home=C:\\Program Files\\Java\\jdk-25
java.vm.name=OpenJDK 64-Bit Server VM
os.name=Windows 11
os.arch=aarch64
sun.arch.data.model=64
Runtime.version=25.0.1+...
```

Giá trị trên chỉ minh họa; tên vendor, đường dẫn, patch number và chuỗi `os.arch` phụ thuộc bản phân phối JDK. Các alias phổ biến gồm `amd64`/`x86_64` cho x64 và `aarch64`/`arm64` cho ARM64. Nếu ứng dụng cần chọn native artifact, nên chuẩn hóa các alias đã kiểm chứng và từ chối trường hợp không nhận diện được, thay vì mặc định mọi kiến trúc lạ là x64.

Không nên dùng `sun.arch.data.model` làm điều kiện nghiệp vụ hoặc API tương thích đa vendor vì đây là thuộc tính triển khai thường gặp của HotSpot. `os.arch` cũng nên được xem là dữ liệu nhận diện runtime, không phải bằng chứng duy nhất rằng mọi native dependency đều tương thích.

## 4. Xác minh kiến trúc của JVM đang chạy dưới dạng service

Một service có thể được khởi chạy bởi Windows Service, systemd, scheduler, container entrypoint hoặc một launcher riêng. Terminal tương tác có thể dùng JDK khác service.

Nếu JDK có công cụ `jcmd`, có thể liệt kê các JVM cục bộ:

```sh
jcmd -l
```

Sau khi xác định PID của ứng dụng, đọc system properties của đúng tiến trình:

```sh
jcmd 12345 VM.system_properties
```

Trên Windows có thể lọc các thuộc tính cần thiết:

```powershell
jcmd 12345 VM.system_properties |
    Select-String 'java.home|java.version|java.vendor|java.vm.name|os.name|os.arch'
```

Trên Linux/macOS:

```sh
jcmd 12345 VM.system_properties \
  | grep -E 'java.home|java.version|java.vendor|java.vm.name|os.name|os.arch'
```

`jcmd` cần có khả năng attach vào JVM mục tiêu; quyền người dùng, cấu hình attach và môi trường container có thể giới hạn thao tác. Nếu runtime image đã lược bỏ công cụ chẩn đoán hoặc attach bị tắt, hãy dùng chương trình chẩn đoán chạy bên trong ứng dụng, log startup hoặc endpoint health/diagnostic được bảo vệ.

Khi điều tra service, cũng cần kiểm tra command line và cấu hình launcher để biết đường dẫn executable thực tế. Ví dụ, systemd unit có thể gọi `/opt/app/runtime/bin/java` trực tiếp; Windows Service wrapper có thể lưu đường dẫn Java trong cấu hình riêng. `JAVA_HOME` của tài khoản đăng nhập không nhất thiết áp dụng cho service.

## 5. Kiểm tra kiến trúc của file JVM và executable

System property cho biết kiến trúc mà tiến trình Java báo cáo. Khi cần xác minh binary được đóng gói, hãy kiểm tra trực tiếp file executable và thư viện JVM.

### Windows: PE/COFF

Dùng `dumpbin` từ Visual Studio Build Tools:

```powershell
dumpbin /headers 'C:\app\runtime\bin\java.exe' |
    Select-String 'machine'

dumpbin /headers 'C:\app\runtime\bin\server\jvm.dll' |
    Select-String 'machine'
```

Machine type thường gặp:

| PE machine | Kiến trúc |
|---|---|
| `8664` | AMD64/x64 |
| `AA64` | ARM64 |
| `14C` | x86 32-bit |

Hãy kiểm tra cả `java.exe` và `jvm.dll`; runtime phải nhất quán. Một executable ARM64 không thể nạp JVM DLL x64 vào cùng tiến trình.

### Linux: ELF

```sh
file /opt/jdk/bin/java
file /opt/jdk/lib/server/libjvm.so
readelf -h /opt/jdk/bin/java
readelf -h /opt/jdk/lib/server/libjvm.so
```

Trường `Machine` trong ELF header cho biết kiến trúc, ví dụ `Advanced Micro Devices X86-64` hoặc `AArch64`. Trên Alpine, cần kiểm tra thêm loader và libc mà binary yêu cầu; kiến trúc đúng không có nghĩa glibc binary sẽ chạy trên musl.

### macOS: Mach-O

```sh
file /Library/Java/JavaVirtualMachines/jdk-25.jdk/Contents/Home/bin/java
lipo -info /Library/Java/JavaVirtualMachines/jdk-25.jdk/Contents/Home/bin/java
```

`lipo -info` cho biết Mach-O là một kiến trúc cụ thể hay universal binary chứa nhiều kiến trúc. Khi kiểm tra thư viện native, thực hiện tương tự với `.dylib` mà ứng dụng nạp.

## 6. Kiểm tra runtime đã đóng gói bằng jlink

`jlink` tạo runtime image tùy chỉnh từ các module của JDK. Runtime image có thư mục `bin` chứa launcher Java và các thư mục module/runtime cần thiết. Để biết runtime image thuộc kiến trúc nào, chạy chính executable Java nằm trong image đó.

Ví dụ tạo runtime image trên nền tảng build hiện tại:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime
```

Kiểm tra trên Windows:

```powershell
.\runtime\bin\java.exe -version
.\runtime\bin\java.exe -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|os.arch|java.version|java.vendor'
```

Kiểm tra trên Linux/macOS:

```sh
./runtime/bin/java -version
./runtime/bin/java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|os.arch|java.version|java.vendor'
```

Runtime image được tạo từ JDK và module thuộc nền tảng build. `jlink` không biến runtime x64 thành ARM64 và không phải công cụ cross-compile runtime cho một OS/CPU khác. Hãy tạo runtime trên target phù hợp hoặc dùng bộ JDK/module đúng nền tảng do nhà cung cấp hỗ trợ.

## 7. Kiểm tra runtime nhúng trong gói jpackage

Khi tạo ứng dụng bằng `jpackage`, gói `app-image` có thể chứa runtime riêng. Sau khi đóng gói, không nên chỉ chạy `java -version` từ terminal vì lệnh đó có thể trỏ đến JDK cài trên máy, không phải runtime nhúng trong ứng dụng.

Ví dụ tạo app image:

```sh
jpackage \
  --type app-image \
  --name OrdersApp \
  --input target \
  --main-jar orders-app.jar
```

Nếu không truyền `--runtime-image`, `jpackage` tạo runtime image bằng JDK được dùng để chạy công cụ đóng gói. Nếu truyền `--runtime-image`, gói sẽ sử dụng runtime image đã cung cấp. Vì vậy, phải kiểm tra đúng runtime đã được đưa vào gói cuối.

Các đường dẫn thường gặp trong app image:

| Nền tảng | Đường dẫn runtime Java thường gặp |
|---|---|
| Windows | `OrdersApp\runtime\bin\java.exe` |
| Linux | `OrdersApp/lib/runtime/bin/java` |
| macOS | `OrdersApp.app/Contents/runtime/Contents/Home/bin/java` |

Đường dẫn cụ thể có thể khác theo loại gói, phiên bản JDK và cách tạo app image. Hãy duyệt cấu trúc thư mục được sinh ra và tìm executable trong runtime nhúng.

Kiểm tra trên Windows:

```powershell
.\OrdersApp\runtime\bin\java.exe -version
.\OrdersApp\runtime\bin\java.exe -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|os.arch|java.version|java.vendor'
```

Kiểm tra trên Linux:

```sh
./OrdersApp/lib/runtime/bin/java -version
./OrdersApp/lib/runtime/bin/java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|os.arch|java.version|java.vendor'
```

Kiểm tra trên macOS:

```sh
./OrdersApp.app/Contents/runtime/Contents/Home/bin/java -version
./OrdersApp.app/Contents/runtime/Contents/Home/bin/java \
  -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|os.arch|java.version|java.vendor'
```

Nếu ứng dụng chỉ chứa launcher và không có runtime riêng, launcher có thể sử dụng runtime được cấu hình hoặc runtime tìm thấy trên hệ thống. Khi đó, kiểm tra file cấu hình launcher, command line và JVM thực tế bằng `jcmd` hoặc log chẩn đoán.

## 8. Windows ARM64: phân biệt CPU máy với kiến trúc JVM process

Máy Windows ARM64 có thể chạy JDK ARM64 native hoặc JDK x64 qua giả lập. Vì vậy, hai thông tin sau không nhất thiết giống nhau:

- Kiến trúc CPU của máy vật lý.
- Kiến trúc tiến trình `java.exe` đang chạy.

Kiểm tra CPU máy trong PowerShell:

```powershell
Get-CimInstance Win32_Processor |
    Select-Object Name, Architecture
```

Giá trị `Architecture` thường là `12` cho ARM64 và `9` cho x64. Sau đó kiểm tra `os.arch` từ chính JVM. Nếu máy là ARM64 nhưng JVM báo `amd64`, nhiều khả năng ứng dụng đang chạy bằng JDK x64 qua giả lập.

Quy tắc chọn native library dựa trên process architecture:

| Máy vật lý | JVM process | Native DLL cần nạp |
|---|---|---|
| Windows ARM64 | ARM64 | ARM64 |
| Windows ARM64 | x64 qua giả lập | x64 |
| Windows x64 | x64 | x64 |

Không chọn DLL chỉ dựa trên CPU vật lý. Windows nạp DLL vào tiến trình; kiến trúc DLL phải tương thích với kiến trúc tiến trình đó.

## 9. Đưa thông tin runtime vào log và health diagnostics

Với service chạy lâu dài, nên ghi nhận thông tin runtime khi ứng dụng khởi động để tránh phải suy đoán từ máy triển khai. Chỉ ghi các thuộc tính cần thiết, không đưa biến môi trường, command line hoặc đường dẫn nhạy cảm vào log công khai.

```java
public final class RuntimeDiagnostics {
    private RuntimeDiagnostics() {
    }

    public static void logStartupInfo() {
        System.getLogger(RuntimeDiagnostics.class.getName()).log(
                System.Logger.Level.INFO,
                "Java runtime: version={0}, vendor={1}, vm={2}, os={3}, arch={4}",
                System.getProperty("java.runtime.version"),
                System.getProperty("java.vendor"),
                System.getProperty("java.vm.name"),
                System.getProperty("os.name"),
                System.getProperty("os.arch"));
    }
}
```

Gọi `RuntimeDiagnostics.logStartupInfo()` trong giai đoạn khởi động. Nếu có endpoint diagnostics, chỉ công bố thông tin này cho người vận hành được phép truy cập; không cần đưa endpoint chi tiết runtime ra Internet.

Đối với ứng dụng đóng gói runtime riêng, log startup là bằng chứng hữu ích để xác nhận launcher đã khởi chạy đúng runtime nhúng. Có thể ghi thêm `java.home` nếu đường dẫn runtime không chứa thông tin nhạy cảm trong môi trường cụ thể.

## 10. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `java -version` hiển thị phiên bản nên đã biết kiến trúc | Cần kiểm tra `os.arch` hoặc binary metadata; output cơ bản không nhất thiết nêu kiến trúc. |
| `JAVA_HOME` cho biết chắc chắn ứng dụng đang dùng JDK nào | Shell, service, IDE và launcher có thể dùng đường dẫn khác. Kiểm tra JVM process thực tế. |
| CPU máy là ARM64 nên Java chắc chắn chạy ARM64 | JDK x64 có thể chạy qua giả lập; `os.arch` của JVM process mới cho biết kiến trúc runtime đang dùng. |
| JAR chạy được trên ARM64 nên runtime nhúng cũng là ARM64 | JAR bytecode có thể portable trong khi JDK/JRE đóng gói vẫn là binary x64. |
| `jlink` chuyển runtime sang kiến trúc mong muốn | `jlink` tạo runtime từ JDK/module target; nó không tự cross-compile sang kiến trúc khác. |
| Chạy `java -version` trên máy đã xác nhận app image | Phải chạy executable `java` nằm trong runtime nhúng hoặc kiểm tra JVM do launcher khởi chạy. |
| `sun.arch.data.model` là API chuẩn để chọn thư viện | Đây là thuộc tính triển khai; dùng `os.arch` và kiểm tra binary/dependency theo hợp đồng của ứng dụng. |

## 11. Quy trình xác minh trước khi phát hành

1. Ghi nhận JDK vendor, version, `java.home`, `os.name` và `os.arch` từ ứng dụng.
2. Kiểm tra lệnh `java` mà shell, service hoặc container entrypoint thực sự gọi.
3. Nếu dùng `jlink`, chạy `runtime/bin/java` trong runtime image đã tạo.
4. Nếu dùng `jpackage`, chạy `java` nằm trong runtime nhúng của app image hoặc xác minh JVM process qua `jcmd`.
5. Kiểm tra executable và thư viện JVM bằng `dumpbin`, `readelf` hoặc `file` khi cần xác nhận binary architecture.
6. Đối chiếu JNI/JNA và native dependency với kiến trúc tiến trình, ABI và libc.
7. Chạy smoke test và integration test bằng đúng gói sẽ phát hành, trên từng target OS/CPU.
8. Ghi lại tag/digest hoặc checksum của runtime cùng kết quả xác minh trong release record.

Nếu thông tin từ shell, service log và runtime nhúng không khớp, hãy coi đó là dấu hiệu có nhiều JDK hoặc launcher configuration khác nhau. Xác định executable thực tế trước khi thay đổi `PATH`, `JAVA_HOME` hoặc cài đặt JDK trên máy chủ.

## 12. Ghi nhớ

- `java -version` hữu ích để nhận diện phiên bản và vendor, nhưng thường chưa đủ để xác nhận kiến trúc.
- `os.arch` từ chính JVM process cho biết kiến trúc runtime đang chạy; `java.home` cho biết runtime location.
- Shell, service và launcher có thể sử dụng các JDK khác nhau trên cùng một máy.
- Dùng `jcmd <pid> VM.system_properties` để kiểm tra JVM đang hoạt động khi attach được phép.
- Kiểm tra binary bằng `dumpbin` trên Windows, `file`/`readelf` trên Linux và `file`/`lipo` trên macOS.
- Với `jlink` và `jpackage`, phải kiểm tra runtime nằm trong gói cuối, không chỉ JDK trên máy build.
- Trên Windows ARM64, phân biệt CPU vật lý với kiến trúc process khi chạy JDK x64 qua giả lập.
- Xác nhận native dependency theo kiến trúc tiến trình, ABI và môi trường triển khai thực tế.

Khi kiểm tra đồng thời phiên bản, `java.home`, `os.arch` và runtime được đóng gói, nhóm vận hành có thể xác định chính xác ứng dụng đang chạy bằng JDK nào và kiến trúc nào. Đây là cơ sở để chẩn đoán lỗi native library và phát hành gói Java đa nền tảng một cách có thể kiểm chứng.
