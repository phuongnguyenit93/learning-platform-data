# Kiểm thử runtime image trong môi trường không cài JDK đầy đủ

`jlink` tạo một runtime image tùy chỉnh từ các module của JDK và các module ứng dụng cần thiết. Máy triển khai có thể chạy ứng dụng bằng Java launcher nằm trong image mà không cần cài JDK đầy đủ, không cần `javac`, `jlink` hoặc `jdeps` trên máy đó. JDK đầy đủ chỉ cần ở giai đoạn build image.

Để chứng minh image độc lập với JDK cài trên máy build, hãy đóng gói image, giải nén vào thư mục triển khai rồi chạy thử với `PATH` chỉ trỏ tới `bin` của image. Sau đó xác nhận các công cụ phát triển không được tìm thấy và ứng dụng vẫn chạy. Cuối cùng, nên lặp lại bài kiểm tra trên VM/container sạch có cùng hệ điều hành và kiến trúc với máy đích.

## 1. Runtime image chứa gì?

Runtime image do `jlink` tạo gồm Java launcher, các module runtime được chọn và các file cấu hình/thư viện cần thiết. Nó không chứa toàn bộ bộ công cụ phát triển như compiler và linker.

| Thành phần | Vai trò | Có trong runtime image tối giản? |
| --- | --- | --- |
| `bin/java` | Khởi chạy ứng dụng Java. | Có. |
| `lib/modules` | Các module runtime đã được liên kết. | Có. |
| `conf` | Cấu hình runtime, ví dụ bảo mật và logging. | Có khi module/runtime cần. |
| `javac` | Biên dịch mã nguồn Java. | Không. |
| `jlink` | Tạo runtime image. | Không. |
| `jdeps` | Phân tích dependency. | Không. |
| `jar` | Tạo và kiểm tra JAR. | Không. |

Máy đích chỉ cần runtime image phù hợp và các tài nguyên ứng dụng cần thiết. Không nên giả định image có thể dùng để biên dịch, debug hoặc đóng gói ứng dụng như một JDK.

## 2. Điều kiện trước khi dùng `jlink`

`jlink` liên kết các module tường minh. Ứng dụng và thư viện cần đưa vào image phải có module descriptor phù hợp; automatic module và JAR chỉ chạy trên classpath không thể được liên kết trực tiếp như một module trong image. Với dependency chưa modular hóa, cần xử lý ranh giới đóng gói trước khi tạo image, hoặc giữ nó ngoài image và thiết kế cách khởi chạy riêng phù hợp.

Xác định trước:

- Module gốc của ứng dụng, ví dụ `com.example.imagecheck`.
- Các module mà ứng dụng yêu cầu trực tiếp và các dependency bắc cầu.
- Provider cần được tìm qua `ServiceLoader`. Nếu cần liên kết các provider cho service trong module graph, cân nhắc `jlink --bind-services`.
- Phiên bản Java mục tiêu. Runtime image được tạo từ các module của JDK dùng để chạy `jlink`; `javac --release 17` chỉ đặt mức tương thích bytecode, không biến image tạo bởi JDK 24 thành runtime Java 17.
- Hệ điều hành và kiến trúc CPU mục tiêu. Runtime image chứa binary/native library theo nền tảng; cần build và kiểm thử image riêng cho từng nền tảng được hỗ trợ.

## 3. Tạo ứng dụng modular mẫu

Ví dụ tạo ứng dụng nhỏ dùng `java.net.http`. Chương trình khởi tạo `HttpClient` và in phiên bản runtime cùng tên module. Không gửi request mạng nên kết quả kiểm thử không phụ thuộc endpoint bên ngoài.

Cấu trúc dự án:

```text
src/
└── com.example.imagecheck/
    ├── module-info.java
    └── com/example/imagecheck/
        └── Main.java
```

**`src/com.example.imagecheck/module-info.java`**

```java
module com.example.imagecheck {
    requires java.net.http;
}
```

**`src/com.example.imagecheck/com/example/imagecheck/Main.java`**

```java
package com.example.imagecheck;

import java.net.http.HttpClient;

public class Main {
    public static void main(String[] args) {
        HttpClient.newHttpClient();
        System.out.println("Runtime feature: " + Runtime.version().feature());
        System.out.println("HTTP module: " + HttpClient.class.getModule().getName());
        System.out.println("Application module: " + Main.class.getModule().getName());
    }
}
```

Biên dịch bằng JDK cài trên máy build:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.imagecheck
New-Item -ItemType Directory -Force app-mods | Out-Null
jar --create --file app-mods/com.example.imagecheck.jar -C out/com.example.imagecheck .
```

Kiểm tra JAR là explicit module:

```powershell
jar --describe-module --file app-mods/com.example.imagecheck.jar
```

Kết quả cần hiển thị module `com.example.imagecheck` và dependency `java.net.http`. Nếu JAR không có module descriptor, hãy xử lý trước khi chuyển sang bước `jlink`.

## 4. Tạo runtime image bằng `jlink`

Lấy thư mục JDK chứa `javac`, sau đó dùng thư mục `jmods` của chính JDK đó làm nguồn module:

```powershell
$jdkBin = Split-Path (Get-Command javac -CommandType Application).Source -Parent
$javaHome = Split-Path $jdkBin -Parent
jlink --module-path "$javaHome\jmods;app-mods" --add-modules com.example.imagecheck --launcher imagecheck=com.example.imagecheck/com.example.imagecheck.Main --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output runtime-image
```

Ý nghĩa các tùy chọn:

- `--module-path`: nơi tìm module của JDK và module ứng dụng.
- `--add-modules`: chọn module gốc; `jlink` tự đưa các dependency cần thiết vào image.
- `--launcher`: tạo lệnh khởi chạy ứng dụng trong thư mục `bin` của image.
- `--strip-debug`: bỏ thông tin debug khỏi runtime image.
- `--no-header-files` và `--no-man-pages`: bỏ header native và trang hướng dẫn không cần trên máy chạy.
- `--compress=zip-6`: nén tài nguyên theo mức zip-6; đây cũng là mức mặc định hiện hành của plugin nén.
- `--output`: thư mục đích chứa runtime image.

Không dùng các giá trị số cũ `--compress=0`, `--compress=1` hoặc `--compress=2`; JDK hiện hành đánh dấu chúng deprecated. `zip-0` đến `zip-9` là dạng giá trị hiện hành.

Kiểm tra image vừa tạo:

```powershell
Test-Path runtime-image/bin/java.exe
Test-Path runtime-image/bin/javac.exe
Test-Path runtime-image/bin/jlink.exe
Test-Path runtime-image/bin/jdeps.exe
```

Trên Windows, kết quả mong đợi lần lượt là `True`, `False`, `False`, `False`. Tên executable khác nhau trên Linux/macOS; ở các nền tảng đó kiểm tra `bin/java`, `bin/javac`, `bin/jlink` và `bin/jdeps`.

## 5. Chạy thử ngay trong runtime image

Chạy ứng dụng bằng Java launcher nằm trong image:

```powershell
.\runtime-image\bin\java.exe -m com.example.imagecheck/com.example.imagecheck.Main
```

Với image tạo bằng JDK 24, STDOUT:

```text
Runtime feature: 24
HTTP module: java.net.http
Application module: com.example.imagecheck
```

Số `24` là phiên bản feature của JDK dùng để tạo image trong ví dụ. Nếu tạo bằng JDK khác, dòng đầu thay đổi theo runtime image đó.

Kiểm tra module đã được liên kết:

```powershell
.\runtime-image\bin\java.exe --list-modules
.\runtime-image\bin\java.exe --describe-module com.example.imagecheck
```

Danh sách phải có `com.example.imagecheck`, `java.base` và `java.net.http`. Nếu module cần thiết không có trong image, xem lại `requires`, module path và danh sách `--add-modules` trước khi phát hành.

## 6. Đóng gói image để chuyển sang máy triển khai

Runtime image là một thư mục có cấu trúc. Khi phân phối, cần giữ nguyên toàn bộ cấu trúc đó; không chỉ sao chép riêng `java.exe` vì launcher cần các thư viện và module đi kèm.

Ví dụ tạo ZIP và giải nén vào thư mục triển khai:

```powershell
New-Item -ItemType Directory -Force dist, deploy | Out-Null
Compress-Archive -Path runtime-image\* -DestinationPath dist\imagecheck-runtime.zip -Force
Expand-Archive -LiteralPath dist\imagecheck-runtime.zip -DestinationPath deploy\imagecheck-runtime -Force
```

Trong sản phẩm thực tế, có thể đặt thêm file cấu hình, dữ liệu, log directory hoặc script dịch vụ bên cạnh runtime image. Giữ đường dẫn cấu hình và quyền truy cập theo quy ước triển khai; không ghi dữ liệu vận hành vào thư mục image nếu image được thay thế theo từng bản phát hành.

## 7. Mô phỏng máy không có JDK đầy đủ trên Windows

Chỉ đặt `PATH` vào `bin` của image và thư mục hệ thống Windows. Tạm bỏ `JAVA_HOME` để chắc chắn tiến trình không dựa vào JDK cài trên máy build:

```powershell
$runtimeBin = (Resolve-Path .\deploy\imagecheck-runtime\bin).Path
$oldPath = $env:PATH
$oldJavaHome = $env:JAVA_HOME
$system32 = Join-Path $env:SystemRoot 'System32'
try {
    $env:PATH = "$runtimeBin;$system32"
    Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue

    $javaCommand = Get-Command java -CommandType Application -ErrorAction Stop
    if ($javaCommand.Source -ne (Join-Path $runtimeBin 'java.exe')) {
        throw 'Java launcher is not coming from the deployed image.'
    }

    foreach ($tool in @('javac', 'jlink', 'jdeps', 'jar')) {
        if (Get-Command $tool -CommandType Application -ErrorAction SilentlyContinue) {
            throw "$tool unexpectedly exists on the isolated PATH."
        }
    }

    java -m com.example.imagecheck/com.example.imagecheck.Main
    if ($LASTEXITCODE -ne 0) {
        throw 'Application failed with the custom runtime image.'
    }
}
finally {
    $env:PATH = $oldPath
    if ($null -eq $oldJavaHome) {
        Remove-Item Env:JAVA_HOME -ErrorAction SilentlyContinue
    } else {
        $env:JAVA_HOME = $oldJavaHome
    }
}
```

Trong lúc chạy đoạn kiểm thử:

1. `Get-Command java` phải trỏ tới `deploy\imagecheck-runtime\bin\java.exe`.
2. `javac`, `jlink`, `jdeps` và `jar` không được tìm thấy trên `PATH` đã cô lập.
3. Lệnh `java -m ...` vẫn phải chạy và in đủ ba dòng kết quả.
4. Sau kiểm thử, `PATH` và `JAVA_HOME` của shell được khôi phục.

Đây là bài kiểm tra tốt để phát hiện ứng dụng vô tình gọi `java` hoặc tool từ JDK cài trên máy build. Để nghiệm thu cuối cùng, vẫn nên sao chép ZIP sang một VM/container sạch không cài JDK, giải nén và chạy cùng smoke test; cô lập `PATH` trên máy build không thay thế hoàn toàn môi trường sạch.

## 8. Kiểm thử thực tế trên máy đích

Trên VM/container hoặc máy không cài JDK đầy đủ, kiểm tra theo thứ tự:

1. **Nền tảng:** xác nhận OS, kiến trúc CPU và runtime image được build cho đúng nền tảng.
2. **Khởi động:** chạy launcher được tạo bởi `--launcher` hoặc gọi trực tiếp `bin/java -m module/main-class`.
3. **Module:** dùng `java --list-modules` và `java --describe-module` để xác nhận module ứng dụng và dependency hiện diện.
4. **Ứng dụng:** chạy smoke test, sau đó chạy các luồng nghiệp vụ quan trọng.
5. **Tài nguyên ngoài image:** kiểm tra file cấu hình, certificate, timezone data, font, native library, quyền ghi log và biến môi trường.
6. **Mạng và dữ liệu:** nếu ứng dụng kết nối database hoặc HTTP endpoint, kiểm thử DNS, TLS, firewall, credential và kết nối thực tế trong môi trường đích.
7. **Vận hành:** kiểm tra log, shutdown, restart, service manager và cách cập nhật image.

Image có thể chạy trên máy không cài JDK, nhưng vẫn cần các thư viện native hoặc hệ điều hành mà ứng dụng phụ thuộc. `jlink` không tự đóng gói mọi thư viện native của ứng dụng, driver bên ngoài, cấu hình dịch vụ hoặc dữ liệu nghiệp vụ.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `jlink` báo automatic module hoặc module không hợp lệ | Dependency chưa phải explicit module hoặc module path thiếu JMOD/JAR phù hợp. | Modular hóa dependency và kiểm tra bằng `jar --describe-module`. |
| Image tạo thành công nhưng ứng dụng không khởi động | Thiếu module, resource hoặc provider cần lúc runtime. | Kiểm tra `requires`, `uses`/`provides`; cân nhắc `--bind-services` khi dùng service binding. |
| Chạy được trên máy build nhưng lỗi trên máy đích | Máy build có JDK hoặc thư viện native ngoài image mà máy đích không có. | Kiểm thử trong VM/container sạch, cô lập `PATH`, bổ sung native dependency cần thiết. |
| `UnsatisfiedLinkError` | Thiếu native library, sai kiến trúc hoặc thư viện không có trong đường dẫn hệ điều hành. | Đóng gói đúng native binary và kiểm tra OS/CPU/library path. |
| Runtime image báo phiên bản Java không phù hợp | Image được tạo từ JDK khác phiên bản mục tiêu. | Dùng `jlink` từ đúng JDK mục tiêu; `--release` khi biên dịch không đổi phiên bản runtime image. |
| Ứng dụng không tìm thấy file cấu hình | Đường dẫn được tính tương đối theo thư mục làm việc khác dự kiến. | Dùng thư mục cấu hình rõ ràng, tham số hoặc biến môi trường được tài liệu hóa. |

## 10. Checklist phát hành

- [ ] Build ứng dụng và dependency thành các explicit module cần thiết.
- [ ] Dùng đúng JDK/JMOD cho phiên bản runtime mục tiêu.
- [ ] Tạo image bằng `jlink` với module gốc và launcher rõ ràng.
- [ ] Kiểm tra `bin/java` có mặt và các công cụ phát triển không có trong image tối giản.
- [ ] Chạy smoke test bằng chính Java launcher trong image.
- [ ] Đóng gói toàn bộ thư mục image và kiểm tra ZIP sau khi giải nén.
- [ ] Chạy thử với `PATH` cô lập, không có JDK/JAVA_HOME.
- [ ] Kiểm thử trên VM/container sạch cùng OS và kiến trúc với môi trường triển khai.
- [ ] Xác minh native library, cấu hình, chứng chỉ, quyền truy cập, log và các kết nối bên ngoài.

`jlink` cho phép phân phối runtime vừa đủ để chạy ứng dụng mà không yêu cầu máy đích cài JDK đầy đủ. Kiểm thử image sau khi đóng gói, chạy với `PATH` không có compiler/linker và xác nhận trên môi trường sạch giúp phát hiện sớm dependency vô tình còn dựa vào máy build.