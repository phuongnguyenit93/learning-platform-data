# Đánh giá tác động việc loại bỏ cổng x86 32-bit và khả năng cung cấp runtime đích

## Mục tiêu bài học

Một ứng dụng Java có thể chạy trên nhiều hệ điều hành và kiến trúc CPU vì bytecode JVM được thiết kế độc lập với phần cứng. Tuy nhiên, **JVM runtime, thư viện native, agent, installer và custom runtime image không có tính di động như JAR thuần Java**. Chúng phải được cung cấp đúng cho hệ điều hành và kiến trúc đích.

Từ JDK 25, OpenJDK đã loại bỏ cổng Linux x86 32-bit; cổng Windows x86 32-bit đã được loại bỏ trước đó trong JDK 24. Vì vậy, một hệ thống còn dùng Windows/Linux 32-bit x86 cần đánh giá khả năng cài đặt JDK mới, thư viện native, quy trình build, container image và kế hoạch rollback trước khi nâng cấp.

Bài **Đánh giá tác động việc loại bỏ cổng x86 32-bit và khả năng cung cấp runtime đích** thuộc chương **Tác động nâng cấp** của module **JAVA_VERSION_JAVA25**. Nội dung tập trung vào tác động của JEP 479 và JEP 503, cách xác định kiến trúc thực tế, lựa chọn runtime 64-bit, kiểm tra native dependencies và cung cấp đúng runtime cho từng target platform.

Sau bài này, bạn có thể:

1. Phân biệt x86 32-bit, x86-64, AArch64 và cách các hệ thống đặt tên kiến trúc.
2. Giải thích chính xác cổng Windows/Linux x86 32-bit bị loại bỏ ở phiên bản JDK nào.
3. Xác định hệ điều hành, kiến trúc CPU, bitness của process và kiến trúc của Java runtime đang chạy.
4. Phân biệt tính di động của bytecode Java với tính phụ thuộc nền tảng của JVM và native libraries.
5. Đọc ma trận hỗ trợ của từng nhà cung cấp JDK để xác nhận có runtime cho target OS/CPU hay không.
6. Đánh giá tác động tới JNI, JNA, FFM, native agents, JavaFX, custom runtime image và container.
7. Lập kế hoạch chuyển từ môi trường x86 32-bit sang x64 hoặc AArch64.
8. Tạo và kiểm tra runtime/image theo từng target platform.
9. Xây dựng tiêu chí GO/NO-GO, canary và rollback có thể thực hiện trên kiến trúc được hỗ trợ.

> **Phạm vi hiện hành:** bài tập trung vào các cổng x86 32-bit đã bị loại bỏ và các runtime đích 64-bit đang được cung cấp. Không suy rộng thay đổi này thành việc mọi kiến trúc 32-bit đều bị loại bỏ. Khả năng hỗ trợ một OS/CPU cụ thể phải được xác minh theo đúng vendor, JDK update và nền tảng triển khai.

## 1. Điều gì đã thay đổi?

JDK không còn cung cấp các cổng HotSpot x86 32-bit tiêu chuẩn cho Windows và Linux. Việc loại bỏ diễn ra theo hai mốc:

| Hệ điều hành | Giai đoạn cảnh báo | JEP loại bỏ | Release loại bỏ |
|---|---|---|---|
| Windows x86 32-bit | JDK 21 — JEP 449 | JEP 479 | JDK 24 |
| Linux x86 32-bit | JDK 24 — JEP 501 | JEP 503 | JDK 25 |

JEP 479 loại bỏ source code và build support cho Windows 32-bit x86. JEP 503 loại bỏ cổng 32-bit x86 còn lại, chủ yếu là Linux. Từ JDK 25, source/build support của cả hai cổng Windows và Linux x86 32-bit đã không còn trong OpenJDK.

### 1.1. Ý nghĩa đối với ứng dụng

Tác động trực tiếp là **không còn runtime HotSpot x86 32-bit tiêu chuẩn để cài đặt và triển khai theo cách trước đây**. Một ứng dụng đang chạy trên OS 32-bit không thể chỉ thay file JDK bằng JDK 25/27 64-bit rồi tiếp tục chạy.

Để dùng runtime 64-bit, hệ thống phải đáp ứng đồng thời:

- CPU hỗ trợ chế độ 64-bit.
- OS được cài đặt ở phiên bản 64-bit.
- JDK vendor có cung cấp build cho đúng OS và CPU architecture.
- Các thư viện native và agent có binary 64-bit tương ứng.
- Container base image, package và deployment target có cùng kiến trúc.
- Các giới hạn memory, filesystem và vận hành đã được kiểm thử lại.

### 1.2. Java bytecode vẫn độc lập với kiến trúc

Một JAR chỉ chứa bytecode Java thuần thường có thể chạy trên các JVM tương thích ở nhiều kiến trúc khác nhau, miễn là:

- JDK runtime có phiên bản và API phù hợp.
- Ứng dụng không phụ thuộc native binary của một kiến trúc cụ thể.
- Các khác biệt về hệ điều hành, charset, filesystem, network và runtime behavior đã được xử lý.

Ví dụ, cùng một file orders-service.jar có thể được chạy bằng JDK x64 trên Linux x86-64 hoặc JDK AArch64 trên Linux ARM64. Mỗi môi trường vẫn cần một JVM binary phù hợp với target.

**JAR portable không có nghĩa JVM portable.** Một container image chứa JDK x64, native library x64 và executable x64 không thể được coi là image ARM64 chỉ vì file JAR bên trong giống nhau.

## 2. Phân biệt tên kiến trúc

Tên kiến trúc có thể khác nhau giữa hệ điều hành, package manager, JDK vendor và container registry.

| Kiến trúc | Tên thường gặp | Ý nghĩa |
|---|---|---|
| x86 32-bit | x86, i386, i486, i586, i686 | Cổng x86 32-bit đã bị loại bỏ khỏi OpenJDK |
| x86 64-bit | x64, x86_64, amd64 | Cổng x86 64-bit phổ biến |
| ARM 64-bit | AArch64, aarch64, arm64 | Kiến trúc ARM 64-bit |
| ARM 32-bit | arm32, armhf, armv7 | Khác với AArch64; phải kiểm tra hỗ trợ riêng |

Trong Docker/OCI:

| Docker platform | Kiến trúc |
|---|---|
| linux/amd64 | Linux x86-64 |
| linux/arm64 | Linux AArch64 |
| windows/amd64 | Windows x86-64 |
| linux/arm/v7 | Linux ARM 32-bit |

Không suy ra rằng một vendor hỗ trợ linux/arm64 thì cũng hỗ trợ linux/arm/v7. Đây là hai target khác nhau.

### 2.1. Không đồng nhất CPU 64-bit với OS 64-bit

Một CPU x86-64 có thể chạy OS 32-bit. Khi đó process Java vẫn có thể là process 32-bit, dù phần cứng có khả năng chạy 64-bit.

Để chạy JDK 64-bit, cần cả OS và môi trường userspace phù hợp. Kiểm tra CPU hỗ trợ 64-bit là chưa đủ; phải kiểm tra OS đang cài, kiến trúc binary Java và thư viện native mà process cần nạp.

## 3. Zero port còn vai trò gì?

Sau khi các cổng Windows/Linux x86 32-bit bị loại bỏ, tài liệu OpenJDK 25 của Red Hat ghi nhận **Zero port** là con đường còn lại để chạy Java trên bộ xử lý x86 32-bit.

Zero là một port thiên về khả năng chuyển đổi giữa kiến trúc, dùng interpreter thay cho HotSpot Server VM với JIT compiler thông thường. Vì vậy, cần phân biệt:

- Zero không phải bản JDK x86 32-bit HotSpot JIT tiêu chuẩn được các vendor cung cấp rộng rãi.
- Việc có thể build Zero không đồng nghĩa vendor chứng nhận, cập nhật và hỗ trợ production cho target đó.
- Hiệu năng và tập tính năng runtime có thể khác đáng kể so với JDK Server VM.
- Phải xác nhận build, GC, provider, native libraries và support policy của nhà cung cấp.

Zero chỉ nên được xem là lựa chọn kỹ thuật đặc thù khi một hệ thống buộc phải duy trì môi trường x86 32-bit và vendor có phương án hỗ trợ cụ thể. Với kế hoạch nâng cấp sản phẩm dài hạn, hãy ưu tiên chuyển sang OS/CPU 64-bit có JDK runtime được vendor hỗ trợ.

## 4. Khả năng cung cấp runtime phụ thuộc vendor và target

Không tồn tại một ma trận hỗ trợ duy nhất áp dụng cho mọi bản OpenJDK. Các nhà cung cấp có thể khác nhau về:

- JDK release và update đang phát hành.
- OS version được kiểm thử hoặc chứng nhận.
- CPU architecture có binary hay không.
- Loại package: archive, installer, RPM, DEB, container image.
- Mức hỗ trợ production, security updates và thời hạn maintenance.
- Các thành phần tùy chọn như JavaFX, JMC, native-image và JDK Mission Control.

### 4.1. Ví dụ ma trận Oracle JDK 25 và JDK 27

Bảng sau là ví dụ theo binary downloads và certified system configurations của **Oracle JDK**, được kiểm tra tại thời điểm biên soạn. Đây không phải cam kết về ma trận của Temurin, Microsoft Build of OpenJDK, Azul, BellSoft hoặc vendor khác.

| Target | Oracle JDK 25 | Oracle JDK 27 |
|---|---|---|
| Linux x64 | Có | Có |
| Linux AArch64 | Có | Có |
| Windows x64 | Có | Có |
| Windows x86 32-bit | Không | Không |
| macOS x64 | Có binary JDK 25 | Không thấy binary JDK 27 trong danh sách hiện hành |
| macOS AArch64 | Có | Có |
| Windows AArch64 | Không thấy trong danh sách binary/certified tương ứng | Không thấy trong danh sách binary/certified tương ứng |
| Linux x86 32-bit | Không có cổng HotSpot tiêu chuẩn | Không có cổng HotSpot tiêu chuẩn |

Oracle certified system configurations chỉ chứng nhận JVM 64-bit. Danh sách OS được hỗ trợ còn chi tiết hơn bảng kiến trúc: một OS có binary không nhất thiết đồng nghĩa mọi phiên bản OS đều được chứng nhận.

Một ví dụ thay đổi đáng chú ý là Oracle JDK 25 còn cung cấp macOS x64, trong khi danh sách downloads/certified của Oracle JDK 27 tập trung vào macOS AArch64. Điều này cho thấy kiểm tra runtime availability phải làm lại ở mỗi lần nâng JDK, kể cả khi kiến trúc không thay đổi.

### 4.2. JDK 25 và JDK 27 trong kế hoạch nâng cấp

Tại thời điểm 27/11/2026:

- JDK 25 là bản LTS hiện hành của Java SE theo trang tải xuống Oracle.
- JDK 27 là release mới nhất trên trang tải xuống Oracle.
- JDK 25 có thời hạn cập nhật riêng theo chính sách vendor.
- JDK 27 là feature release, có chu kỳ thay thế nhanh hơn LTS.

Không lấy thời hạn hỗ trợ của Oracle áp dụng cho mọi vendor. Trước khi chọn runtime, cần xác nhận license, support contract, security update policy và vòng đời của đúng distribution đang sử dụng.

## 5. Tác động tới từng thành phần của hệ thống

### 5.1. Source code và bytecode Java

Với ứng dụng thuần Java:

- Phần lớn source code không cần sửa chỉ vì chuyển từ x86 32-bit sang x64/AArch64.
- Bytecode không chứa machine instruction x86 32-bit.
- Build bằng javac --release 25 điều khiển language level, API và class-file target; nó **không tạo ra JVM 32-bit hoặc 64-bit**.
- Cần chạy integration test trên runtime đích để kiểm tra khác biệt về OS, charset, file path, process, networking và concurrency.

Ví dụ:

~~~bash
javac --release 25 -d out src/com/example/Main.java
~~~

Lệnh này không chọn CPU architecture. Cùng class file có thể được chạy trên các JDK 25 tương thích cho x64 hoặc AArch64 nếu ứng dụng không có phụ thuộc native không tương thích.

### 5.2. JNI, JNA và thư viện native

Đây thường là nhóm rủi ro lớn nhất khi chuyển process từ 32-bit sang 64-bit.

Các thư viện native được biên dịch cho một tổ hợp cụ thể:

- OS: Linux, Windows hoặc macOS.
- CPU: x86, x64, AArch64...
- ABI và C runtime: ví dụ glibc/musl trên Linux.
- Bitness: 32-bit hoặc 64-bit.
- Phiên bản thư viện phụ thuộc.

Một JVM 64-bit không thể nạp trực tiếp shared library x86 32-bit. Trên Linux có thể gặp lỗi wrong ELF class: ELFCLASS32; trên Windows có thể gặp lỗi load module do sai kiến trúc hoặc dependency không phù hợp.

Kiểm tra toàn bộ:

- JNI libraries được nạp qua System.loadLibrary hoặc System.load.
- JNA/JNR và thư viện native đi kèm dependency.
- Netty native transport, TLS native provider, compression, database driver có native component.
- JavaFX native modules.
- Native agent, profiler, APM agent và security agent.
- Các binary helper được khởi chạy bằng ProcessBuilder.
- FFM API và native libraries được gọi trực tiếp.
- Các thư viện đóng gói trong JAR dưới thư mục theo platform như linux-x86, windows-x86.

### 5.3. Pointer, struct và dữ liệu native

Khi chuyển từ process 32-bit sang 64-bit, kích thước pointer và một số kiểu dữ liệu native thay đổi. Code native hoặc binding có thể gặp vấn đề nếu trước đây:

- Lưu pointer vào biến int.
- Giả định sizeof(void*) == 4.
- Tính offset/size bằng kiểu 32-bit.
- Định nghĩa struct không đúng alignment/padding của ABI đích.
- Ép kiểu giữa size_t, pointer và integer không an toàn.
- Serialize trực tiếp cấu trúc C/C++ theo layout của một kiến trúc.

Trong JNI, dùng kiểu JNI phù hợp như jlong cho handle/pointer được mã hóa theo quy ước của thư viện; không lưu pointer 64-bit vào jint. Khi dùng FFM, định nghĩa MemoryLayout, alignment và kích thước theo ABI của native target thay vì sao chép layout 32-bit cũ.

### 5.4. Agent và công cụ vận hành

Native agent thường được build riêng cho từng OS/architecture. Cần kiểm tra:

- APM/profiling agent có bản x64/AArch64 tương ứng không.
- Native JVMTI agent có hỗ trợ JDK mới và target process 64-bit không.
- Security/endpoint monitoring agent có được vendor chứng nhận trên OS mới không.
- Script khởi động có trỏ tới đúng binary java và thư viện native không.
- Các công cụ dump, attach, diagnostic và service wrapper có tương thích architecture không.

Không chỉ kiểm tra ứng dụng chính. Một agent không tương thích có thể làm JVM không khởi động hoặc gây crash khi attach.

## 6. Kiểm tra kiến trúc thực tế trước khi nâng cấp

Đừng chỉ đọc cấu hình máy chủ hoặc tên image. Xác minh cả OS, binary Java và native dependencies.

### 6.1. Linux

~~~bash
uname -m
getconf LONG_BIT
file "$JAVA_HOME/bin/java"
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.vendor|java.version|os.name|os.arch'
~~~

Cách đọc phổ biến:

- uname -m = i686: OS userland x86 32-bit.
- uname -m = x86_64: OS x86-64.
- uname -m = aarch64: OS ARM64.
- os.arch của Java cho biết kiến trúc mà JVM process báo cáo.
- file xác định định dạng/architecture của binary java.

Nếu dùng Debian/Ubuntu:

~~~bash
dpkg --print-architecture
~~~

Nếu dùng RPM-based Linux:

~~~bash
rpm --eval '%{_arch}'
~~~

Các lệnh này kiểm tra package architecture của hệ thống, không thay thế việc kiểm tra binary Java và native library.

### 6.2. Windows PowerShell

~~~powershell
[Environment]::Is64BitOperatingSystem
[Environment]::Is64BitProcess

java -version
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.vendor|java.version|os.name|os.arch'
~~~

Nếu có Visual Studio Build Tools:

~~~powershell
dumpbin /headers "$env:JAVA_HOME\bin\java.exe" |
    Select-String 'machine'
~~~

Kiểm tra các DLL native tương tự bằng dumpbin /headers và dumpbin /dependents.

### 6.3. macOS

~~~bash
uname -m
file "$JAVA_HOME/bin/java"
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.vendor|java.version|os.name|os.arch'
~~~

Trên máy Apple Silicon, cần xác định process đang chạy native AArch64 hay qua môi trường tương thích x86. Không chỉ dựa vào model máy; hãy kiểm tra binary runtime thực tế.

### 6.4. Kiểm tra native binary

Linux:

~~~bash
file libexample.so
readelf -h libexample.so
ldd libexample.so
~~~

macOS:

~~~bash
file libexample.dylib
otool -hv libexample.dylib
otool -L libexample.dylib
~~~

Windows:

~~~powershell
dumpbin /headers libexample.dll
dumpbin /dependents libexample.dll
~~~

Mục tiêu là xác nhận kiến trúc, ABI và các dependency native của từng binary. Một thư viện có tên file libexample.so không cho biết nó là x86, x64 hay AArch64.

## 7. Kiểm tra khả năng cung cấp runtime đích

Trước khi chọn JDK, lập bảng cho từng target environment:

| Thuộc tính | Ví dụ cần ghi |
|---|---|
| JDK vendor | Oracle, Eclipse Temurin, Microsoft, Azul, BellSoft... |
| JDK release/update | 25.0.x hoặc 27.0.x |
| OS distribution | Ubuntu, RHEL, Oracle Linux, Windows Server, macOS... |
| OS version | Phiên bản cụ thể, không chỉ tên họ OS |
| CPU architecture | x64 hoặc AArch64 |
| Package | tar.gz, zip, MSI, RPM, DEB, container image |
| Runtime type | JDK, JRE/runtime image, jlink image |
| Certification | Certified, supported, community build hoặc không có cam kết |
| Update policy | Security updates, maintenance window và EOL |
| License/support | Điều khoản sử dụng và hỗ trợ production |

Không chọn runtime chỉ dựa vào việc tải xuống được một file. Cần xác nhận tổ hợp OS/architecture đó nằm trong phạm vi hỗ trợ của vendor.

### 7.1. Ma trận quyết định cho môi trường hiện tại

| Hệ thống hiện tại | Tình trạng khi dùng JDK 25+ | Hướng xử lý |
|---|---|---|
| Windows x86 32-bit | Không còn cổng HotSpot x86 32-bit tiêu chuẩn | Chuyển sang Windows x64 và JDK x64 được hỗ trợ |
| Linux x86 32-bit | Không còn cổng HotSpot x86 32-bit tiêu chuẩn | Chuyển sang Linux x86-64 hoặc AArch64 với runtime được hỗ trợ |
| Windows x64 | Có thể dùng JDK x64 nếu vendor hỗ trợ OS version | Kiểm tra native DLL và installer |
| Linux x86-64 | Có thể dùng JDK x64 nếu vendor hỗ trợ distro/version | Kiểm tra glibc, container base và native .so |
| Linux AArch64 | Có thể dùng JDK AArch64 nếu vendor hỗ trợ distro/version | Cung cấp native library ARM64 |
| macOS Intel x64 | Có thể có JDK x64 ở release/vendor nhất định | Kiểm tra ma trận của từng JDK update; không giả định JDK mới còn cung cấp |
| macOS Apple Silicon | Dùng JDK AArch64 nếu vendor hỗ trợ | Kiểm tra native dependency ARM64 |
| ARM 32-bit | Không nằm trong phạm vi loại bỏ x86 32-bit | Kiểm tra hỗ trợ riêng, không suy luận từ JEP 503 |

### 7.2. Kiểm tra cả runtime và support lifecycle

Với mỗi lựa chọn:

1. Tải đúng bản JDK từ nguồn vendor chính thức.
2. Kiểm tra checksum/signature.
3. Xác nhận OS version và CPU architecture được hỗ trợ.
4. Xác nhận runtime còn nhận security updates trong thời gian triển khai.
5. Xác nhận container base image có manifest cho target.
6. Kiểm tra các native component có build tương ứng.
7. Xác nhận license và support contract cho môi trường production.

## 8. Xây dựng JAR và runtime image cho đúng target

### 8.1. JAR thuần Java có thể dùng chung

Nếu ứng dụng chỉ chứa class file và resource độc lập nền tảng, pipeline có thể build một JAR rồi triển khai lên nhiều kiến trúc JVM tương thích.

Ví dụ:

~~~bash
mvn clean package
~~~

hoặc:

~~~bash
./gradlew clean build
~~~

Một file JAR thuần Java không cần đóng gói lại chỉ vì target chuyển từ x64 sang AArch64. Tuy nhiên, nếu plugin build tạo native artifact hoặc đóng gói thư viện theo classifier kiến trúc, cần build/publish artifact tương ứng cho từng target.

### 8.2. --release không chọn architecture

Ví dụ:

~~~bash
javac --release 25 -d out src/com/example/Main.java
~~~

--release 25 đặt language/API/class-file target của Java 25. Nó không chọn x86 32-bit, x64 hay AArch64. Kiến trúc của process được quyết định bởi JDK runtime được cài trên máy đích.

Tương tự, cấu hình Maven maven.compiler.release hoặc Gradle options.release không tạo ra runtime cho một CPU architecture cụ thể.

### 8.3. jlink image phải khớp target runtime

jlink tạo custom runtime image từ các module của JDK. Image chứa native executable và thư viện runtime của nền tảng đó.

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.logging,java.sql \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime-image
~~~

Ví dụ này tạo runtime từ JDK đang nằm trong JAVA_HOME. Vì vậy, nếu JDK đó là Linux x64 thì output là runtime image cho target tương ứng; không thể đổi tên thư mục thành ARM64 rồi dùng trên máy ARM.

Khi cần nhiều kiến trúc:

- Cung cấp JDK/JMOD đúng target cho từng build.
- Chạy jlink trong builder tương ứng hoặc dùng quy trình cross-link được vendor hỗ trợ rõ ràng.
- Kiểm tra runtime image bằng runtime-image/bin/java -version trên target.
- Kiểm tra module list và native dependencies.
- Đóng gói image riêng cho từng OS/architecture.

### 8.4. Native Image cũng phụ thuộc target

Nếu dùng GraalVM Native Image hoặc công cụ biên dịch Java thành executable native, binary đầu ra phụ thuộc OS, architecture, toolchain và thư viện native.

Một native executable Linux x64 không trở thành Linux ARM64 chỉ vì file JAR đầu vào là portable. Xây dựng và kiểm thử native executable riêng cho từng target mà công cụ hỗ trợ.

## 9. Cung cấp container image đa kiến trúc

Container không xóa bỏ phụ thuộc CPU architecture. Image cần chứa runtime và native dependencies phù hợp với node sẽ chạy nó.

Docker/OCI thường dùng:

- linux/amd64 cho Linux x86-64.
- linux/arm64 cho Linux AArch64.

### 9.1. Multi-platform manifest

Một image đa kiến trúc có thể có manifest list trỏ tới nhiều image variant. Khi pull image, runtime chọn variant phù hợp với kiến trúc node.

~~~bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/orders-service:25 \
  --push .
~~~

Lệnh trên chỉ hoạt động đúng khi:

- Builder hỗ trợ cả hai target.
- Base image JDK/JRE có variant cho từng target.
- Mọi native library được cung cấp đúng architecture.
- Các bước RUN trong Dockerfile có runtime/emulation phù hợp nếu builder thực thi lệnh cho target khác.
- Các test được chạy trên từng architecture hoặc môi trường mô phỏng đã được xác minh.

### 9.2. Dockerfile dùng base image đa kiến trúc

~~~dockerfile
# syntax=docker/dockerfile:1
FROM registry.example.com/java/runtime:25

WORKDIR /application
COPY app.jar /application/app.jar

ENTRYPOINT ["java", "-jar", "/application/app.jar"]
~~~

registry.example.com/java/runtime:25 là placeholder cho base image của tổ chức hoặc vendor. Trước khi dùng, xác nhận tag/digest đó có manifest linux/amd64 và linux/arm64 nếu pipeline cần cả hai.

Nếu base image chỉ có x64, Docker Buildx không thể tự biến JDK x64 thành JDK ARM64. Cần cung cấp base image đúng target hoặc tách build theo kiến trúc.

### 9.3. Kiểm tra manifest

~~~bash
docker buildx imagetools inspect registry.example.com/orders-service:25
~~~

Xác nhận danh sách platform có đúng các target cần triển khai. Sau đó pull và chạy smoke test riêng trên node x64 và ARM64.

Không chỉ kiểm tra tag image. Hãy lưu image digest và platform manifest trong release metadata để có thể tái tạo đúng binary đã phát hành.

## 10. Tác động tới bộ nhớ và hiệu năng sau khi chuyển 32-bit sang 64-bit

Chuyển từ process 32-bit sang 64-bit có thể thay đổi footprint bộ nhớ và đặc tính runtime:

- Pointer/reference native rộng hơn.
- Layout của một số struct native thay đổi.
- Heap và native memory có giới hạn khác.
- Compressed ordinary object pointers (compressed oops) có thể giúp giảm chi phí reference trong HotSpot khi điều kiện phù hợp.
- Số lượng thread, stack size và native allocations có thể ảnh hưởng RSS.
- Một số CPU architecture có vector instruction, cache hierarchy và performance profile khác nhau.

Không nhân đôi -Xmx chỉ vì chuyển sang JVM 64-bit. Hãy đo lại:

| Chỉ số | Cần đánh giá |
|---|---|
| Heap used/committed | Live set và heap headroom |
| RSS/container memory | Tổng memory thực tế của process |
| Native memory | Metaspace, code cache, thread stacks, direct buffers |
| Allocation rate | Bytes allocated mỗi giây |
| GC pause/CPU | Tác động của collector trên target |
| Throughput | Request hoặc job hoàn thành |
| p95/p99 latency | Tail latency sau khi chuyển architecture |
| Startup time | Thời gian khởi động và warm-up |
| CPU utilization | Khác biệt giữa x64 và ARM64 |

Benchmark trên đúng phần cứng, OS, JDK build và container limits dự kiến chạy production.

## 11. Quy trình migration theo giai đoạn

### 11.1. Giai đoạn 1 — Inventory

Lập danh sách toàn bộ hệ thống còn liên quan x86 32-bit:

- Máy chủ, VM, thiết bị edge và máy trạm.
- OS version và bitness.
- CPU architecture.
- JDK vendor/version/build.
- Container images và registry manifests.
- Native libraries, JNI/JNA/FFM, agent và executable helper.
- JavaFX hoặc thư viện có thành phần native.
- Custom runtime image được tạo bằng jlink.
- Native Image hoặc installer riêng cho từng OS.
- Quy trình backup, rollback và disaster recovery.

### 11.2. Giai đoạn 2 — Chọn target runtime

Với từng workload, xác định:

1. OS 64-bit nào có thể chạy trên hardware hiện tại?
2. CPU hỗ trợ x64 hay AArch64?
3. Vendor JDK có cung cấp runtime đúng target không?
4. OS version có nằm trong certified/supported matrix không?
5. Native dependencies có build đúng target không?
6. Vendor có cam kết cập nhật bảo mật trong thời gian vận hành không?
7. Runtime có thể được đóng gói, phân phối và rollback qua pipeline hiện tại không?

Nếu một target không có runtime được hỗ trợ, cần chọn lại OS/hardware/vendor trước khi triển khai. Không dùng một JDK binary gần giống kiến trúc làm phương án thay thế.

### 11.3. Giai đoạn 3 — Nâng nền tảng

Chuyển OS/hardware hoặc node pool sang target 64-bit được chọn. Kiểm tra:

- Boot mode và OS image.
- Driver, storage, network và monitoring agent.
- Runtime container và registry.
- Quyền file, service account và systemd/service wrapper.
- Native library paths và package dependencies.
- Resource limits và memory sizing.

Nếu chuyển từ x86-64 sang AArch64, kiểm tra thêm các native dependencies và image base cho ARM64.

### 11.4. Giai đoạn 4 — Build và kiểm thử

- Build JAR và native artifacts theo đúng target.
- Tạo jlink runtime image nếu dùng.
- Tạo container image variant theo platform.
- Chạy unit, integration và end-to-end tests.
- Kiểm tra JNI load, database driver, TLS provider, compression và agent.
- Đo heap/RSS, throughput, latency và startup.
- Kiểm tra log, crash dump, profiling và backup/restore.

### 11.5. Giai đoạn 5 — Canary và rollout

1. Triển khai một nhóm nhỏ instance trên target mới.
2. Chuyển một phần traffic hoặc workload.
3. Theo dõi error rate, latency, CPU, memory và native library load.
4. Kiểm tra sự ổn định qua giờ cao điểm và batch window.
5. Mở rộng theo từng đợt khi guardrail đạt.
6. Cập nhật runtime inventory và release metadata.

## 12. Xây dựng tiêu chí GO/NO-GO

| Tiêu chí | GO khi | NO-GO khi |
|---|---|---|
| Runtime availability | Vendor có binary và support matrix cho target | Không có runtime được hỗ trợ |
| OS/CPU | OS 64-bit chạy trên CPU đích được vendor hỗ trợ | OS còn 32-bit hoặc CPU không hỗ trợ |
| Native dependencies | Có đủ binary native đúng OS/architecture | Còn thư viện x86 32-bit không thay thế được |
| Build | Pipeline tạo được JAR/runtime/image theo target | Image chứa nhầm runtime architecture |
| Correctness | Unit/integration/E2E tests đạt | Có lỗi native, dữ liệu hoặc hành vi |
| Performance | Đạt SLO và capacity budget | Latency/throughput/memory vượt ngưỡng |
| Operations | Monitoring, logging, backup, diagnostics hoạt động | Thiếu agent hoặc công cụ vận hành |
| Rollback | Có target rollback 64-bit đã kiểm thử | Rollback phụ thuộc runtime 32-bit không còn được cung cấp |
| Support lifecycle | Vendor support đủ thời hạn dự kiến | Runtime/OS sắp hết hỗ trợ |

Ngưỡng cụ thể phải lấy từ SLO và capacity policy của tổ chức. Không dùng các giá trị benchmark ví dụ trong tài liệu làm ngưỡng production mặc định.

## 13. Kế hoạch rollback

Rollback phải xét cả architecture và runtime availability. Một bản JDK 64-bit không thể chạy trên OS 32-bit chỉ bằng cách đổi JAVA_HOME.

Kế hoạch rollback nên bảo đảm:

- Image trước đó vẫn có bản 64-bit tương thích với target OS/CPU.
- Container registry giữ đúng manifest và digest của release trước.
- Native libraries của release trước vẫn có binary đúng architecture.
- Database schema và message format không bị thay đổi theo cách không thể tương thích ngược.
- Configuration/secret và endpoint vẫn dùng được với bản trước.
- Có thể chuyển traffic về node pool 64-bit đã được kiểm thử.
- Rollback đã được diễn tập trước production rollout.

Nếu hệ thống cũ chỉ có runtime x86 32-bit, việc chuyển toàn bộ hardware/OS sang 64-bit là một thay đổi nền tảng riêng. Không được coi rollback về JDK 32-bit là phương án chắc chắn sau khi đã thay đổi target OS hoặc node architecture.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Không cài được JDK trên OS 32-bit | Không còn cổng HotSpot x86 32-bit tiêu chuẩn | Xác minh OS/process bitness và vendor matrix |
| JVM không khởi động trên node mới | Runtime binary sai architecture | Kiểm tra file, java -version, os.arch |
| wrong ELF class: ELFCLASS32 | Nạp thư viện native 32-bit vào process 64-bit | Kiểm tra binary bằng file/readelf |
| Windows báo lỗi load DLL | DLL sai architecture hoặc thiếu dependency | Dùng dumpbin /headers và /dependents |
| UnsatisfiedLinkError | Thiếu native binary hoặc sai đường dẫn | Kiểm tra native library path và platform classifier |
| Container không chạy trên ARM64 | Image chỉ có variant amd64 | Kiểm tra manifest bằng imagetools inspect |
| Image ARM64 khởi động nhưng native call lỗi | JAR chứa native library x64 | Build/publish native artifact ARM64 |
| jlink image chạy trên build host nhưng không chạy target | Runtime image được tạo từ JDK sai platform | Tạo image từ target JDK/modules |
| App chạy nhưng RSS tăng | Pointer width, native allocation hoặc heap sizing khác | Đo heap, native memory và RSS |
| Throughput thay đổi sau khi chuyển ARM64 | Khác CPU, JIT, memory bandwidth hoặc native library | Benchmark cùng workload trên target |
| Agent không attach được | Agent binary không tương thích hoặc thiếu quyền | Cập nhật agent và kiểm tra vendor support |
| Rollback thất bại | Rollback image/JDK chỉ có kiến trúc cũ | Chuẩn bị rollback runtime trên target 64-bit trước rollout |

## 15. Ma trận kiểm thử nghiệm thu

| Mã | Kịch bản | Kết quả mong đợi |
|---|---|---|
| U1 | Xác định architecture của OS | Phân biệt x86, x64 và AArch64 |
| U2 | Kiểm tra binary Java bằng file hoặc công cụ tương ứng | Xác nhận bitness/architecture của runtime |
| U3 | Kiểm tra java -XshowSettings:properties -version | Ghi nhận vendor, version, OS và architecture |
| U4 | Kiểm tra JDK vendor support matrix | Target nằm trong phạm vi hỗ trợ |
| U5 | Build ứng dụng thuần Java | JAR chạy trên các JVM target tương thích |
| U6 | Quét dependency tìm native binary | Không còn native library sai architecture |
| U7 | Load JNI/JNA/FFM trên x64 | Native calls hoạt động |
| U8 | Load JNI/JNA/FFM trên AArch64 nếu target hỗ trợ | Native calls hoạt động trên ARM64 |
| U9 | Tạo jlink image cho target | Runtime image chạy trên đúng target |
| U10 | Build container linux/amd64 | Image chạy trên node amd64 |
| U11 | Build container linux/arm64 | Image chạy trên node arm64 |
| U12 | Kiểm tra multi-platform manifest | Registry có đúng platform variants |
| U13 | Chạy integration/E2E tests | Nghiệp vụ và dữ liệu đúng |
| U14 | Benchmark heap/RSS/CPU/latency | Đạt capacity budget và SLO |
| U15 | Kiểm tra agent, monitoring, diagnostics | Công cụ vận hành tương thích |
| U16 | Canary rollout | Không vượt guardrail |
| U17 | Rollback trên target 64-bit | Runtime cũ khởi động và SLO phục hồi |
| U18 | Diễn tập restore/DR | Có thể khôi phục trên runtime target được hỗ trợ |

## 16. Bài thực hành tổng hợp

Một dịch vụ nội bộ đang chạy trên Linux x86 32-bit với JDK cũ. Ứng dụng sử dụng JAR thuần Java, một thư viện JNI để xử lý nén dữ liệu và một APM native agent. Hạ tầng mới có thể cung cấp Linux x86-64 hoặc Linux AArch64.

Thực hiện:

1. Ghi lại OS version, CPU architecture, process bitness và JDK vendor/version hiện tại.
2. Kiểm tra JDK 25/27 runtime availability theo vendor cho Linux x64 và AArch64.
3. Lập inventory tất cả .so, JNI/JNA/FFM và native agents.
4. Xác nhận nhà cung cấp thư viện nén và APM agent có binary 64-bit cho cả hai target hay không.
5. Build lại native library nếu source và toolchain cho phép.
6. Build ứng dụng JAR và kiểm tra phần code Java thuần không chứa giả định 32-bit.
7. Tạo runtime image hoặc container image cho từng target.
8. Chạy integration tests và benchmark trên x64; lặp lại trên AArch64 nếu chọn target đó.
9. So sánh CPU, RSS, throughput và p99 latency.
10. Tạo multi-platform manifest nếu triển khai cả hai kiến trúc.
11. Diễn tập canary và rollback về runtime 64-bit trước đó.
12. Ghi quyết định target cuối cùng cùng lý do loại bỏ các target không có vendor support.

**Sản phẩm nghiệm thu:** inventory OS/JDK/CPU, bảng target runtime availability, danh sách native dependencies, Docker/jlink artifacts theo target, kết quả test/benchmark và runbook rollout/rollback.

## 17. Checklist trước khi nâng cấp

- Xác định đúng hệ thống đang là x86 32-bit hay x86-64.
- Nhớ Windows x86 32-bit port bị loại bỏ trong JDK 24; Linux x86 32-bit trong JDK 25.
- Không nhầm thay đổi x86 32-bit với việc mọi kiến trúc 32-bit đều bị loại bỏ.
- Không giả định mọi vendor có cùng OS/architecture matrix.
- Xác nhận OS 64-bit và CPU target được hỗ trợ.
- Kiểm tra JDK vendor, update release, certification và support lifecycle.
- Kiểm tra JNI/JNA/FFM, native agents, JavaFX và native helpers.
- Kiểm tra kiến trúc của từng .so, .dll, .dylib.
- Phân biệt JAR portable với JVM/runtime image/native binary.
- Không dùng --release như tùy chọn chọn CPU architecture.
- Tạo jlink/native image/container riêng theo target platform.
- Xác minh multi-platform image manifest và base image variants.
- Benchmark lại heap, RSS, CPU, throughput và tail latency.
- Kiểm thử diagnostics, monitoring, backup và restore.
- Có rollback runtime 64-bit đã kiểm thử trước khi chuyển production.

## Tài liệu tham khảo chính thức

- [JEP 449 — Deprecate the Windows 32-bit x86 Port for Removal](https://openjdk.org/jeps/449): mốc deprecate Windows x86 32-bit trong JDK 21.
- [JEP 479 — Remove the Windows 32-bit x86 Port](https://openjdk.org/jeps/479): loại bỏ cổng Windows x86 32-bit trong JDK 24.
- [JEP 501 — Deprecate the 32-bit x86 Port for Removal](https://openjdk.org/jeps/501): mốc deprecate Linux x86 32-bit trong JDK 24.
- [JEP 503 — Remove the 32-bit x86 Port](https://openjdk.org/jeps/503): loại bỏ cổng x86 32-bit còn lại trong JDK 25.
- [Inside.java — What's New in JDK 25](https://inside.java/2025/10/17/new-in-jdk-25-2-mins/): tóm tắt việc loại bỏ cổng 32-bit x86 trong JDK 25.
- [Eclipse Temurin 25 — Deprecated and Unsupported Capabilities](https://docs.redhat.com/en/documentation/red_hat_build_of_openjdk/25/html/release_notes_for_eclipse_temurin_25/openjdk-temurin25-deprecated-unsupported-features): xác nhận trạng thái Windows/Linux 32-bit x86 và ghi chú về Zero port.
- [Oracle JDK 25 Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk25certconfig.html): ma trận OS/CPU được Oracle chứng nhận cho JDK 25.
- [Oracle JDK 27 Certified System Configurations](https://www.oracle.com/java/technologies/javase/products-doc-jdk27certconfig.html): ma trận OS/CPU được Oracle chứng nhận cho JDK 27; chỉ JVM 64-bit được chứng nhận.
- [Oracle Java Downloads](https://www.oracle.com/java/technologies/downloads/): binary packages và target architectures đang được Oracle cung cấp cho JDK 25/27.
- [Oracle JDK Script-Friendly URLs](https://www.oracle.com/apac/java/technologies/jdk-script-friendly-urls/): tên OS/architecture trong URL phân phối JDK và cách xác minh checksum.
- [Oracle JDK 25 — Preparing for Migration](https://docs.oracle.com/en/java/javase/25/migrate/preparing-migration.html): quy trình kiểm tra ứng dụng, dependency, compile và jdeps khi nâng cấp.
- [Oracle JDK 26 — jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): cách tạo custom runtime image từ module và dependency.
- [Docker — Multi-platform builds](https://docs.docker.com/build/building/multi-platform/): xây dựng image cho linux/amd64, linux/arm64, native builders và emulation.
- [Oracle JDK 25 — Migrating from JDK 8 to Later JDK Releases](https://docs.oracle.com/en/java/javase/25/migrate/migrating-jdk-8-later-jdk-releases.html): các lưu ý khi ứng dụng sử dụng JNI và native access.
