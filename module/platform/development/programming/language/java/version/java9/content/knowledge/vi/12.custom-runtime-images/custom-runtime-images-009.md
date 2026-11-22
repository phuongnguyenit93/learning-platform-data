# Ràng buộc theo hệ điều hành, kiến trúc và bộ JDK đầu vào

## 1. Vì sao jlink phụ thuộc vào nền tảng?

`jlink` tạo một **runtime image** riêng bằng cách chọn các module cần thiết, phân giải dependency rồi đóng gói những thành phần runtime tương ứng. Kết quả không chỉ là các file bytecode Java. Runtime image còn chứa JVM, native launcher, thư viện native và cấu trúc dữ liệu nội bộ của JDK.

Vì có các thành phần native, một runtime image được tạo cho một nền tảng cụ thể. Ví dụ, image tạo trên Windows x64 không phải image có thể sao chép nguyên trạng sang Linux x64 hoặc Windows ARM64.

Khi chuẩn bị build, cần xác định ba yếu tố độc lập:

1. **Nền tảng đích:** hệ điều hành và kiến trúc CPU sẽ chạy image.
2. **JDK đích:** feature release của runtime muốn tạo, ví dụ Java 17 hoặc Java 25.
3. **Bộ module đầu vào:** JMOD/JAR và các thư viện native phải tương thích với nền tảng và JDK đích.

Không nên nhầm phiên bản bytecode của ứng dụng với phiên bản runtime được tạo. `javac --release 17` có thể tạo bytecode tương thích Java 17, nhưng nếu dùng `jlink` và JMOD của JDK 25 thì runtime image vẫn là Java 25.

## 2. Các khái niệm cần phân biệt

| Thành phần | Vai trò |
|---|---|
| JDK | Bộ công cụ phát triển Java, có `javac`, `jlink`, `jmod` và các module của JDK |
| `jlink` | Công cụ liên kết module thành runtime image |
| JMOD | Định dạng module archive có thể chứa class, native library, command, header và tài nguyên đi kèm |
| Modular JAR | JAR có `module-info.class`, khai báo tên module và các dependency |
| Module path | Nơi `jlink` tìm các module đầu vào |
| `java.base.jmod` | Module nền tảng bắt buộc, xác định feature release và ràng buộc nền tảng của bộ JDK đầu vào |
| Runtime image | Bộ runtime đã liên kết, có thể chạy ứng dụng mà không cần cài toàn bộ JDK |

Một JDK đầy đủ thường có cấu trúc:

~~~text
jdk/
├── bin/
│   ├── java
│   ├── javac
│   ├── jlink
│   └── jmod
└── jmods/
    ├── java.base.jmod
    ├── java.logging.jmod
    ├── java.sql.jmod
    └── ...
~~~

Khi dùng `jlink`, cần có công cụ linker và các module đầu vào phù hợp. Một runtime image đã được cắt gọn không nhất thiết còn thư mục `jmods`, vì vậy không thể coi một runtime image bất kỳ là bộ đầu vào thay thế cho JDK.

## 3. Ràng buộc theo hệ điều hành và kiến trúc CPU

JMOD của JDK có thông tin target platform. Có thể xem bằng:

~~~bash
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

Ví dụ trên JDK Windows x64:

~~~text
java.base@25.0.1
...
platform windows-amd64
~~~

Tên platform thể hiện cả hệ điều hành và kiến trúc. Một số tên thường gặp có dạng:

| Nền tảng | Ví dụ tên platform |
|---|---|
| Windows x64 | `windows-amd64` |
| Windows ARM64 | `windows-aarch64` |
| Linux x64 | `linux-amd64` |

Tên cụ thể phụ thuộc bản phân phối JDK và nền tảng được hỗ trợ. Hãy đọc metadata của JMOD thực tế thay vì tự suy ra tên.

Khi phân giải module, `jlink` kiểm tra ràng buộc target platform của các module. Nếu module nền tảng là `windows-amd64` nhưng một JMOD khác được đánh dấu `linux-amd64`, quá trình liên kết bị từ chối. Khác biệt kiến trúc cũng bị từ chối, kể cả khi hệ điều hành giống nhau.

Ví dụ lỗi khi ghép module Windows x64 với module Linux x64:

~~~text
Error: Module java.base has constraints on target platform
(windows-amd64) that conflict with other modules: linux-amd64
~~~

Ví dụ lỗi khi ghép Windows x64 với Windows ARM64:

~~~text
Error: Module java.base has constraints on target platform
(windows-amd64) that conflict with other modules: windows-aarch64
~~~

Đây là ràng buộc thật của module graph, không phải lỗi do cú pháp đường dẫn. Thay đổi dấu phân cách đường dẫn hoặc đổi tên file JMOD không làm các native binary tương thích với nhau.

### 3.1. jlink không phải công cụ cross-compile runtime

Tùy chọn `--module-path` chỉ định nơi tìm module; nó không chọn hệ điều hành đích. `jlink` không có tùy chọn tổng quát để chuyển một bộ JMOD Windows thành runtime Linux hoặc chuyển runtime x64 thành ARM64.

Tùy chọn `--endian little|big` điều khiển byte order của dữ liệu `jimage`; nó không đổi hệ điều hành, kiến trúc CPU hay định dạng native executable.

Nếu cần phân phối nhiều nền tảng, tạo một runtime image riêng cho từng target bằng JDK/JMOD tương ứng. Thực tế thường dùng CI runner, máy ảo hoặc môi trường build chạy trên từng hệ điều hành/kiến trúc đích.

## 4. Native library khiến image phụ thuộc nền tảng

Java bytecode trong file `.class` và modular JAR thường có thể dùng trên nhiều hệ điều hành. Tuy nhiên, các thành phần sau phụ thuộc nền tảng:

- JVM và native launcher.
- Thư viện native của JDK.
- JNI library do ứng dụng hoặc thư viện bên thứ ba cung cấp.
- Native command hoặc thư viện được đóng gói trong JMOD.
- ABI, kiến trúc CPU và các yêu cầu của hệ điều hành.

Ví dụ, thư viện JNI được biên dịch thành `.dll` cho Windows không thể nạp trực tiếp như `.so` trên Linux. Một thư viện native x64 cũng không tự tương thích với ARM64.

Khi tạo JMOD tùy chỉnh có native library, có thể khai báo target platform lúc tạo:

~~~bash
jmod create --class-path build/classes --libs build/native --target-platform windows-amd64 build/my.native.module.jmod
~~~

`--target-platform` ghi metadata nền tảng cho JMOD. Nó không chuyển đổi thư viện native; các file trong `build/native` vẫn phải được biên dịch cho đúng hệ điều hành và kiến trúc đã khai báo.

JMOD ứng dụng chỉ chứa bytecode Java và không khai báo native platform có thể không cần target-platform riêng. Khi module chứa native binary, hãy khai báo chính xác và build một biến thể phù hợp cho từng nền tảng.

## 5. Ràng buộc theo phiên bản JDK đầu vào

Runtime image được tạo từ các module của một feature release cụ thể. Module nền tảng `java.base` là đầu mối quan trọng để xác định release đó.

Có thể kiểm tra hai phiên bản:

~~~bash
jlink --version
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

Ví dụ, nếu linker thuộc JDK 25 nhưng `java.base.jmod` thuộc JDK 24, `jlink` từ chối:

~~~text
Error: jlink version 25.0 does not match target java.base version 24.0
~~~

Tương tự, JDK 24 linker không thể tạo runtime Java 17 bằng cách chỉ trỏ module path sang JMOD Java 17:

~~~text
Error: jlink version 24.0 does not match target java.base version 17.0
~~~

JDK mới hơn cũng có thể chứa module descriptor mà linker cũ chưa đọc được. Ví dụ, JDK 24 linker đọc JMOD của JDK 25 có thể gặp:

~~~text
Unsupported major.minor version 69.0
~~~

Vì vậy, muốn tạo runtime Java 17, hãy dùng `jlink` và JMOD của JDK 17. Muốn tạo runtime Java 25, hãy dùng `jlink` và JMOD của JDK 25.

### 5.1. Patch release và feature release

Cần phân biệt feature release như 17, 21, 24, 25 với patch release như 24.0.1 và 24.0.2.

Kiểm thử cho thấy linker 24.0.2 có thể dùng `java.base.jmod` 24.0.1; image tạo ra mang phiên bản runtime 24.0.1. Như vậy, kiểm tra tương thích của `jlink` tập trung vào feature release, còn patch version của image đi theo bộ module đầu vào.

Dù patch-level cùng feature release có thể liên kết được, cách build dễ tái lập nhất là dùng `jlink` và toàn bộ JMOD từ cùng một bản cài JDK. Điều này giúp tránh trộn các bản vá bảo mật, native library và module metadata từ nhiều bộ phát hành.

## 6. Phân biệt --release của javac với JDK dùng để jlink

`javac --release N` điều khiển mức API Java và định dạng bytecode mà mã nguồn được phép sử dụng. Nó không thay đổi bộ module của JDK mà `jlink` dùng để tạo image.

Ví dụ:

~~~bash
javac --release 17 --module-source-path src -d build/mods -m com.example.app
~~~

Lệnh này biên dịch ứng dụng theo API Java 17. Nếu sau đó liên kết bằng JDK 25:

~~~bash
jlink --module-path "$JDK25_HOME/jmods:build/mods" --add-modules com.example.app --output build/runtime
~~~

thì kết quả vẫn là runtime Java 25, vì `java.base` đầu vào thuộc JDK 25.

| Cấu hình | Kết quả |
|---|---|
| `javac --release 17` + JDK 25 `jlink` và JMOD 25 | Ứng dụng nhắm API Java 17, runtime image Java 25 |
| `javac --release 17` + JDK 17 `jlink` và JMOD 17 | Ứng dụng nhắm API Java 17, runtime image Java 17 |
| `javac --release 25` + JDK 17 runtime | Không phù hợp; ứng dụng có thể dùng bytecode/API mà Java 17 không hỗ trợ |

Nếu mục tiêu triển khai là Java 17, không thể chỉ thêm `--release 17` vào lệnh biên dịch rồi dùng JDK 25 để tạo image. Phải chọn đúng JDK 17 cho bước liên kết runtime.

## 7. Loại module nào có thể đưa vào jlink?

`jlink` liên kết các module có tên và giải quyết dependency của chúng. Những đầu vào phổ biến:

- JMOD của JDK, ví dụ `java.base.jmod`.
- JMOD của ứng dụng hoặc thư viện.
- Modular JAR có `module-info.class`.
- Module đã được biên dịch và đặt đúng cấu trúc module path.

Một modular JAR có thể được dùng làm đầu vào module path. Ngược lại, JAR chỉ được xem là automatic module không thể đưa trực tiếp vào runtime image bằng `jlink`:

~~~text
Error: automatic module cannot be used with jlink: plain
~~~

JAR trên class path cũng không tự trở thành một named module chỉ vì được đưa vào thư mục module path. Nếu muốn đưa thư viện vào runtime image, hãy dùng phiên bản modular JAR có module descriptor hoặc đóng gói nó thành module phù hợp.

Nếu một dependency chưa thể modular hóa, có thể giữ JAR đó bên ngoài runtime image và cấu hình class path khi chạy, nhưng cần xử lý rõ ràng quan hệ đọc module nếu ứng dụng chính là named module.

## 8. Chọn JDK đầu vào và kiểm tra trước khi build

Trước khi chạy `jlink`, kiểm tra các thông tin sau:

~~~bash
java --version
javac --version
jlink --version
jmod describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

Các lệnh này giúp xác nhận:

- Java runtime hiện tại đang dùng.
- Phiên bản compiler.
- Phiên bản linker.
- Phiên bản và target platform của module nền tảng trong bộ JMOD.

Đảm bảo `JAVA_HOME` trỏ đến đúng JDK dùng để tạo image. Trên một máy có nhiều JDK, việc gọi `java` từ PATH nhưng gọi `jlink` từ một thư mục khác có thể tạo ra tổ hợp không nhất quán.

Có thể gọi công cụ bằng đường dẫn tuyệt đối để tránh nhầm:

Trên Windows PowerShell:

~~~powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-25"
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\jlink.exe" --version
& "$env:JAVA_HOME\bin\jmod.exe" describe "$env:JAVA_HOME\jmods\java.base.jmod"
~~~

Trên Linux hoặc macOS:

~~~bash
export JAVA_HOME=/opt/jdk-25
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/jlink" --version
"$JAVA_HOME/bin/jmod" describe "$JAVA_HOME/jmods/java.base.jmod"
~~~

Nếu thư mục `jmods` không tồn tại hoặc thiếu `java.base.jmod`, bộ cài có thể là runtime image hoặc bản JDK đã bị lược bỏ thành phần cần thiết. Hãy dùng bản JDK đầy đủ có `jlink` và JMOD phù hợp.

## 9. Ví dụ hoàn chỉnh: tạo runtime Java 25 cho một module

Ví dụ tạo ứng dụng đơn giản và đóng gói thành runtime image. Ứng dụng được biên dịch với API Java 17, nhưng image đầu ra sử dụng JDK 25.

### 9.1. Cấu trúc source

~~~text
src/
└── com.example.runtimeapp/
    ├── module-info.java
    └── com/example/runtimeapp/
        └── Main.java
~~~

File `src/com.example.runtimeapp/module-info.java`:

~~~java
module com.example.runtimeapp {
}
~~~

File `src/com.example.runtimeapp/com/example/runtimeapp/Main.java`:

~~~java
package com.example.runtimeapp;

public final class Main {
    public static void main(String[] args) {
        System.out.println("runtime-image-ok");
    }
}
~~~

Module không khai báo `requires java.base` vì module này được yêu cầu ngầm định cho mọi named module.

### 9.2. Biên dịch và tạo modular JAR

Biên dịch theo API Java 17:

~~~bash
javac --release 17 --module-source-path src -d build/mods -m com.example.runtimeapp
~~~

Đóng gói module thành JAR có descriptor:

~~~bash
jar --create --file build/runtimeapp.jar -C build/mods/com.example.runtimeapp .
~~~

Có thể kiểm tra module descriptor:

~~~bash
jar --describe-module --file build/runtimeapp.jar
~~~

Kết quả cần thể hiện tên module `com.example.runtimeapp` và main class nếu đã khai báo khi đóng gói. Trong ví dụ, main class được chỉ định ở tùy chọn launcher của `jlink`.

### 9.3. Tạo image trên Windows x64

Đặt `JAVA_HOME` vào JDK 25 dành cho Windows x64:

~~~powershell
$env:JAVA_HOME = "C:\Program Files\Java\jdk-25"
$modulePath = "$env:JAVA_HOME\jmods;build\runtimeapp.jar"
& "$env:JAVA_HOME\bin\jlink.exe" --module-path $modulePath --add-modules com.example.runtimeapp --launcher app=com.example.runtimeapp/com.example.runtimeapp.Main --output build\runtime
~~~

Chạy launcher:

~~~powershell
& "build\runtime\bin\app.bat"
~~~

Kết quả:

~~~text
runtime-image-ok
~~~

Kiểm tra phiên bản runtime được tạo:

~~~powershell
& "build\runtime\bin\java.exe" --version
~~~

Image mang phiên bản Java của bộ JMOD JDK 25 được dùng để liên kết.

### 9.4. Tạo image trên Linux x64

Dùng JDK 25 dành cho Linux x64 và module path phân tách bằng dấu hai chấm:

~~~bash
export JAVA_HOME=/opt/jdk-25

"$JAVA_HOME/bin/jlink" \
  --module-path "$JAVA_HOME/jmods:build/runtimeapp.jar" \
  --add-modules com.example.runtimeapp \
  --launcher app=com.example.runtimeapp/com.example.runtimeapp.Main \
  --output build/runtime
~~~

Chạy:

~~~bash
./build/runtime/bin/app
~~~

Kết quả:

~~~text
runtime-image-ok
~~~

Các bước build Java source và modular JAR có thể được dùng lại nếu ứng dụng không chứa native binary phụ thuộc nền tảng. Bước `jlink` phải dùng JDK/JMOD tương ứng với nền tảng cần phát hành.

## 10. Ma trận build cho nhiều nền tảng

Nếu cần phát hành runtime cho nhiều hệ điều hành hoặc kiến trúc, tổ chức pipeline riêng cho từng target:

| Artifact | Build environment | Bộ JDK/JMOD |
|---|---|---|
| Windows x64 | Windows x64 runner | JDK Windows x64 |
| Windows ARM64 | Windows ARM64 runner | JDK Windows ARM64 |
| Linux x64 | Linux x64 runner | JDK Linux x64 |
| Linux ARM64 | Linux ARM64 runner | JDK Linux ARM64 |
| macOS ARM64 | macOS ARM64 runner | JDK macOS ARM64 |

Tên runner và tên platform thực tế phụ thuộc dịch vụ CI và nhà cung cấp JDK.

Một pipeline thường có các bước:

1. Chọn JDK đúng feature release và target platform.
2. Biên dịch ứng dụng theo API Java tối thiểu muốn hỗ trợ bằng `--release`.
3. Tạo modular JAR hoặc JMOD cho ứng dụng.
4. Kiểm tra `java.base.jmod` để xác nhận phiên bản và platform.
5. Chạy `jlink` với JMOD của JDK đích và các module ứng dụng.
6. Chạy thử image trên runner cùng nền tảng.
7. Đóng gói artifact theo hệ điều hành/kiến trúc.

Không nên tạo một image trên Windows rồi đổi tên hoặc nén lại để phát hành cho Linux. Cần chạy lại bước liên kết với bộ JDK/JMOD Linux tương ứng.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Module java.base has constraints on target platform ...` | Các JMOD khác OS hoặc kiến trúc | Dùng toàn bộ JMOD đúng target platform |
| `jlink version ... does not match target java.base version ...` | Feature release của linker và JMOD không khớp | Chọn `jlink` cùng feature release với `java.base.jmod` |
| `Unsupported major.minor version` khi đọc JMOD | Linker quá cũ so với module descriptor đầu vào | Dùng JDK linker cùng release hoặc mới tương thích |
| `automatic module cannot be used with jlink` | Đầu vào chỉ là automatic module | Chuyển thư viện thành explicit named module hoặc modular JAR |
| `Module ... not found` | Thiếu module hoặc sai module path | Kiểm tra JMOD, modular JAR và tên module |
| Không tìm thấy `java.base.jmod` | Dùng runtime image hoặc JDK không có thư mục JMOD | Cài JDK đầy đủ đúng nền tảng |
| `UnsatisfiedLinkError` khi chạy image | Thiếu native library hoặc native library sai OS/architecture | Đóng gói đúng DLL/SO/dylib và ABI của target |
| Ứng dụng chạy trên JDK phát triển nhưng lỗi trong image | Image thiếu module hoặc runtime quá cũ so với API mà ứng dụng dùng | Kiểm tra dependency, `--add-modules` và `javac --release` |
| Launcher chạy trên Windows nhưng không có file tương ứng trên Linux | Khác tên và định dạng launcher theo OS | Dùng launcher được tạo trên đúng nền tảng; kiểm tra `bin/app.bat` hoặc `bin/app` |

Khi gặp lỗi platform, hãy kiểm tra `jmod describe` trước. Khi gặp lỗi version, kiểm tra `jlink --version` và dòng `java.base@...`. Không nên đổi tên JMOD hoặc bỏ metadata platform để né lỗi, vì điều đó không sửa native binary bên trong.

## 12. Nguyên tắc build an toàn và có thể tái lập

- Ghi rõ target OS, CPU architecture và feature release của runtime trong cấu hình build.
- Chọn JDK đầy đủ có `jlink`, `jmod` và thư mục `jmods`.
- Dùng `jlink` và JMOD từ cùng bộ JDK khi có thể.
- Xác nhận `java.base.jmod` trước khi liên kết.
- Không trộn JMOD từ các feature release khác nhau.
- Không trộn JMOD có target platform khác nhau.
- Đóng gói dependency thành explicit named module nếu muốn đưa vào runtime image.
- Dùng `javac --release N` để giữ API/bytecode tương thích với mức Java cần hỗ trợ.
- Kiểm tra riêng JNI và native library theo OS/architecture.
- Build một artifact riêng cho từng nền tảng đích.
- Chạy thử runtime image trên môi trường tương ứng với artifact.
- Lưu phiên bản JDK, vendor, patch và danh sách module đầu vào để tái tạo build.

## 13. Checklist trước khi phát hành

- [ ] Đã xác định OS và CPU architecture đích.
- [ ] JDK đầu vào đúng nền tảng và có thư mục `jmods`.
- [ ] `jlink --version` tương thích với feature release của `java.base.jmod`.
- [ ] `jmod describe java.base.jmod` cho đúng platform.
- [ ] Tất cả JMOD native đều cùng target platform.
- [ ] Dependency muốn link là explicit named module.
- [ ] Ứng dụng được biên dịch theo API Java mà runtime hỗ trợ.
- [ ] Các native library bên thứ ba đúng định dạng và kiến trúc.
- [ ] Runtime image được chạy thử trên target platform.
- [ ] Artifact và thông tin JDK đầu vào được lưu lại để tái lập.

## 14. Tài liệu tham khảo

- [The jlink Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html) — tùy chọn module path, root modules, launcher và cách tạo runtime image.
- [The jmod Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jmod.html) — tạo, mô tả và khai báo target platform cho JMOD.
- [Java Platform Module System — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/package-summary.html) — khái niệm module và module descriptor.
- [javac — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html) — tùy chọn `--release` và biên dịch module.
