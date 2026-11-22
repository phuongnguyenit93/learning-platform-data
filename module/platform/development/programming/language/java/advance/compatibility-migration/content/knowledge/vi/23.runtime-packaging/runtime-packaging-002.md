# JRE đóng gói sẵn và runtime tùy biến bằng jlink

Khi chuyển một ứng dụng Java từ JDK cũ sang JDK hiện đại, việc **đóng gói môi trường chạy** có thể quan trọng không kém việc sửa source code hoặc nâng framework. Một ứng dụng được phát hành dưới dạng JAR có thể hoạt động trên máy developer nhưng thất bại trên máy khách vì chưa cài Java, cài sai phiên bản, thiếu module JDK, thiếu native library hoặc sử dụng một JRE đã lâu không được cập nhật bảo mật.

Một giải pháp là **phân phối kèm một Java runtime** đã được chọn và kiểm thử, thay vì yêu cầu người dùng tự cài JDK. Với Java 9 trở đi, công cụ `jlink` còn cho phép tạo **custom runtime image** chỉ gồm những module Java cần thiết, giúp kiểm soát kích thước và thành phần môi trường chạy. Tuy nhiên, image càng tối giản thì càng dễ bỏ sót module được gọi qua reflection, service provider hoặc những nhánh chức năng ít được kiểm thử.

Bài học này giải thích sự khác nhau giữa JRE có sẵn, JDK đầy đủ, runtime do `jlink` tạo và installer do `jpackage` tạo; hướng dẫn xác định module, tạo image, chạy ứng dụng modular và classpath, xử lý Java agents, TLS, locale, native libraries, đóng gói đa nền tảng, cập nhật bản vá và thiết kế pipeline migration an toàn.

> **Phạm vi:** Ví dụ trong bài minh họa mô hình triển khai cho Java hiện đại và giả định bạn có quyền sử dụng, phân phối JDK/runtime tương ứng. Lệnh, plugin và thành phần có thể khác giữa các phiên bản JDK hoặc vendor. Khi phát hành thật, phải kiểm tra tài liệu của JDK distribution, license, hệ điều hành và toolchain được tổ chức lựa chọn.

## 1. Vấn đề mà một runtime đóng gói kèm giải quyết

### 1.1. Mô hình phụ thuộc vào Java được cài trên máy

Một ứng dụng truyền thống có thể được phát hành như sau:

```text
Phía nhà phát triển
  source -> javac -> application.jar
                         |
                         v
                     Phân phối JAR
                         |
                         v
Máy khách: java -jar application.jar
            ^
            |
         Java cài sẵn trên máy
```

Đây là mô hình đơn giản, phù hợp khi hệ thống quản lý runtime tập trung. Nhưng nó đặt ra nhiều giả định:

- Lệnh `java` có tồn tại trong `PATH` không?
- JVM thực tế là Java 8, 11, 17, 21 hay bản khác?
- Java được cài từ vendor nào, có còn nhận security updates không?
- Người dùng có quyền cài đặt hoặc nâng Java không?
- Máy đang dùng Windows, macOS hay Linux; x86_64 hay ARM64?
- Runtime có những module và security providers mà ứng dụng cần không?
- Môi trường đã cấu hình truststore, locale, timezone và encoding phù hợp chưa?

Nếu các giả định này không được quản lý, bản nâng cấp Java có thể biến thành vấn đề triển khai trên hàng nghìn máy.

### 1.2. Mô hình phân phối kèm runtime

Một hướng khác:

```text
CI / Release pipeline
  |
  +--> Build application.jar
  |
  +--> Chọn runtime version/vendor
  |
  +--> Đóng gói application + runtime
  |
  v
Release bundle
  app/
    application.jar
    lib/
    runtime/
      bin/java
      lib/...
    bin/start
```

Lúc khởi động, script sử dụng `runtime/bin/java` của bản phát hành thay vì phiên bản `java` tìm thấy trên hệ thống.

Lợi ích:

- Chủ động chọn Java runtime được ứng dụng hỗ trợ.
- Giảm lỗi do người dùng cài Java sai.
- Giúp kiểm thử trên runtime tương đương bản phân phối.
- Có thể triển khai môi trường không có JDK toàn hệ thống.
- Quản lý cập nhật và rollback cùng ứng dụng.
- Có cơ hội giảm kích thước bằng runtime tùy biến.

Đổi lại, đội phát triển **phải chịu trách nhiệm cập nhật runtime** trong mỗi bản phát hành. Một bản JAR không đổi nhưng runtime chứa lỗ hổng vẫn cần được xây dựng và phân phối lại.

## 2. JDK, JRE, runtime image và ứng dụng đóng gói

### 2.1. JDK đầy đủ

**Java Development Kit (JDK)** thường bao gồm runtime và các công cụ phát triển như compiler, debugger, archiver và công cụ phân tích:

```text
jdk/
  bin/
    java
    javac
    jar
    jlink
    jdeps
    ...
  conf/
  legal/
  lib/
  jmods/ ... (tùy distribution và release)
```

Cấu trúc chính xác thay đổi theo vendor, hệ điều hành và phiên bản. JDK thích hợp cho máy build và phát triển. Không phải mọi ứng dụng production đều cần mang theo toàn bộ compiler và các công cụ phát triển.

### 2.2. JRE trong Java cũ

Trong các thế hệ Java trước hệ thống module, nhiều môi trường sử dụng **JRE được phát hành riêng** để chạy ứng dụng:

```text
Ứng dụng -> JRE được cài hoặc đóng gói kèm -> JVM
```

Đây là một sản phẩm/runtime distribution riêng với JDK đầy đủ ở những phiên bản và vendor hỗ trợ mô hình đó.

Khi nâng từ Java 8 sang JDK hiện đại, không nên mặc định còn tồn tại đường dẫn `$JAVA_HOME/jre` hoặc một thư mục `jre` bên trong JDK như trước. Từ JDK 9, JDK được tổ chức theo module và runtime images; sau các thay đổi ở thế hệ JDK mới, không phải vendor nào cũng phát hành một JRE tải riêng theo quy ước cũ.

**Quan trọng:** “JRE không còn là bản phát hành mặc định của một số JDK” không có nghĩa Java chỉ còn chạy được bằng JDK đầy đủ. Các vendor có thể phân phối runtime chuyên dùng, và `jlink` cho phép tạo runtime image riêng từ những module được hỗ trợ.

### 2.3. Runtime image tùy biến bằng jlink

`jlink` là công cụ trong hệ sinh thái Java module, được giới thiệu từ Java 9. Nó liên kết một tập module thành **runtime image** có cấu trúc dùng để khởi chạy Java code, ví dụ:

```text
custom-runtime/
  bin/
    java
    keytool
    ...
  conf/
  legal/
  lib/
  release
```

Danh sách file phụ thuộc module, plugin và JDK version. Runtime này không nhất thiết có compiler hoặc `jlink` bên trong.

### 2.4. jpackage

`jpackage` phục vụ bước đóng gói **ứng dụng** thành application image hoặc native installer cho nền tảng mục tiêu. Nó có thể sử dụng runtime image được tạo hoặc được cấp qua tùy chọn thích hợp.

Phân biệt:

| Thành phần | Vai trò chính | Ví dụ sử dụng |
|---|---|---|
| JDK đầy đủ | Compile, package, debug và chạy Java | CI build machine |
| JRE/runtime distribution | Chạy ứng dụng bằng runtime đã được vendor đóng gói | Máy production dùng runtime được cung cấp sẵn |
| `jlink` | Tạo runtime image từ các Java modules | Tối giản môi trường chạy theo ứng dụng |
| `jpackage` | Tạo application image hoặc installer | Desktop app cho Windows/macOS/Linux |
| JAR/WAR | Đóng gói class, resource và metadata của ứng dụng | Java service, CLI, thư viện |
| OCI container image | Phân phối filesystem, runtime và ứng dụng | Server/container deployments |

`jlink` không phải một công cụ tạo installer hoàn chỉnh, và `jpackage` không thay thế compiler Java. Thường các công cụ này kết hợp trong một release pipeline.

## 3. Tại sao jlink có thể giảm kích thước?

### 3.1. JDK gồm nhiều module

Với JPMS, Java runtime được chia thành những module có mô tả phụ thuộc rõ ràng. Một chương trình chỉ cần core API, logging và HTTP client có thể không cần phần lớn module Java Desktop, XML, SQL hoặc development tools.

Ví dụ đồ thị:

```text
com.example.cli
   |
   +--> java.base
   +--> java.logging
   +--> java.net.http
             |
             +--> các module nền tảng cần thiết
```

`jlink` sử dụng thông tin module graph để đưa vào những module cần thiết, thay vì sao chép toàn bộ JDK.

### 3.2. jlink không chỉ là nén ZIP

Có ba thao tác khác nhau:

1. **Module selection:** loại bỏ những module không cần trong runtime image.
2. **Image optimization:** có thể bỏ debug symbols, man pages, header files hoặc dùng cơ chế nén được runtime hỗ trợ.
3. **Distribution compression:** nén toàn bộ thư mục image thành ZIP, TAR, installer hoặc container layer để truyền tải.

Các thao tác này không đồng nghĩa nhau. Một runtime image có kích thước nhỏ trên ổ đĩa chưa chắc có compressed download nhỏ nhất, và ngược lại.

### 3.3. Không nên tối giản bằng mọi giá

Nếu cắt module quá mạnh, ứng dụng có thể:

- Không tìm được logging, JNDI hoặc XML API.
- Thiếu charset cho dữ liệu ngoài UTF-8.
- Không có locale data đầy đủ.
- Không tải được TLS/security provider cần thiết.
- Không khởi tạo các service providers.
- Không có JFR, management hoặc Attach API khi SRE cần.
- Không mở được desktop UI.
- Chỉ lỗi khi một tính năng ít dùng được kích hoạt.

Mục tiêu hợp lý là **runtime đủ nhỏ nhưng đầy đủ chức năng và dễ bảo trì**, không chỉ tối thiểu số byte.

## 4. Điều kiện tiên quyết trước khi dùng jlink

### 4.1. Dùng JDK có công cụ jlink

Kiểm tra:

```shell
java -version
jlink --version
jlink --help
```

JDK phải có `jlink` và tài nguyên module cần thiết. Nếu đang dùng một runtime image đã được cắt gọn, nó có thể không chứa `jlink`; cần sử dụng một JDK build toolchain phù hợp.

### 4.2. Hiểu module path và classpath

- **Classpath:** cách nạp class truyền thống, có thể chứa nhiều JAR không có module descriptor.
- **Module path:** dùng để resolve named modules theo JPMS.
- **Module descriptor:** `module-info.class` khai báo module name, dependencies, exports và service usage.
- **Automatic module:** JAR không có explicit module descriptor có thể được coi là automatic module khi đưa vào module path trong một số tình huống runtime.

`jlink` liên kết **named modules có module descriptor phù hợp**, nhưng không hỗ trợ liên kết automatic modules giống như explicit modules theo cách thông thường. Vì vậy, không thể đưa một thư viện classpath bất kỳ vào `--module-path`, gọi `jlink` và kỳ vọng mọi artifact Java đều được nhúng vào runtime.

Nếu ứng dụng chưa modularized, vẫn có thể tạo **runtime chứa các JDK modules cần thiết**, rồi phân phối JAR/thư viện classpath riêng. Đây thường là con đường migration thực tế và ít xáo trộn hơn.

### 4.3. Kiểm kê ứng dụng và dependency

Trước khi chọn module, cần biết:

- Ứng dụng là modular hay classpath-based?
- Entry point là `main class`, main module, framework launcher hay native launcher?
- Các module Java SE nào được dùng trực tiếp?
- Có JDBC, HTTP client, XML, GUI, JNDI hoặc scripting không?
- Có runtime reflection, `ServiceLoader`, dynamic proxy, classloader hoặc plugin không?
- Có Java agents, JVMTI, JNI hay JFR không?
- Các dependencies có native assets theo OS/arch không?
- Ứng dụng cần locale, timezone, charset hoặc crypto providers nào?
- Runtime tối thiểu của ứng dụng và của third-party libraries là phiên bản nào?

Một module graph xác định từ source code thường chưa đủ; cần thử đường chạy thực tế của ứng dụng.

## 5. jlink và các tùy chọn cơ bản

### 5.1. Mẫu lệnh

Một ví dụ đơn giản tạo runtime chứa một số Java modules:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http \
  --output build/runtime
```

Đường tiếp dòng bằng dấu `\` là cú pháp shell Unix-like. Trong PowerShell, có thể viết một dòng:

```powershell
jlink --add-modules java.base,java.logging,java.net.http --output build/runtime
```

`jlink` lấy Java module definitions từ JDK/toolchain tương ứng theo cách cấu hình. Với một ứng dụng modular riêng, cần cung cấp module path có cả application modules và Java platform modules thích hợp.

### 5.2. Chạy runtime đã tạo

Unix-like:

```shell
./build/runtime/bin/java --list-modules
./build/runtime/bin/java -version
```

Windows:

```powershell
.\build\runtime\bin\java.exe --list-modules
.\build\runtime\bin\java.exe -version
```

Danh sách modules giúp xác nhận những Java modules có mặt trong image, còn `java -version` cho biết runtime tương ứng với JDK được dùng để tạo image.

### 5.3. Những tùy chọn thường gặp

| Tùy chọn | Mục đích |
|---|---|
| `--module-path` | Chỉ đường dẫn chứa các modules tham gia liên kết |
| `--add-modules` | Chỉ định root modules cần đưa vào image |
| `--output` | Chọn thư mục image đầu ra |
| `--launcher` | Tạo launcher cho main module đã xác định |
| `--bind-services` | Bao gồm service provider modules phù hợp với module graph |
| `--strip-debug` | Bỏ thông tin debug theo khả năng plugin |
| `--no-header-files` | Loại header files khỏi image |
| `--no-man-pages` | Loại man pages khỏi image |
| `--compress` | Nén nội dung image bằng plugin/mode được JDK hỗ trợ |
| `--list-plugins` | Liệt kê các plugin hiện có |

Cú pháp chi tiết của một số plugin, đặc biệt `--compress` và các tùy chọn mới, có thể thay đổi theo JDK release. Nên dùng `jlink --help` và `jlink --list-plugins` của đúng toolchain thay vì sao chép một cấu hình từ JDK khác.

### 5.4. Tạo image tối giản nhưng không cần tùy chọn nén đặc thù

Ví dụ thường dùng:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

Sau đó đo kích thước, chạy smoke tests và so sánh với bản không tối ưu. Những tùy chọn loại tài nguyên này là quyết định packaging; nếu phát hiện một công cụ cần debug symbols hoặc thành phần bị loại, cần điều chỉnh.

### 5.5. Không ghi đè image cũ khi chưa rõ cách xử lý output

`--output` hướng tới một thư mục đích. Quy trình build nên tạo image mới trong thư mục được quản lý hoặc xóa output cũ một cách có kiểm soát trước khi tạo lại.

Không nên dùng một thư mục runtime mà ứng dụng đang chạy làm nơi ghi đè trực tiếp. Một runtime image được sử dụng bởi process khác cần được xem là artifact immutable; cập nhật bằng bản mới, sau đó chuyển launcher/installation tới bản đó.

## 6. Dự án modular: jlink bao gồm cả module ứng dụng

### 6.1. Khai báo module-info.java

Ví dụ ứng dụng Java modular tối giản:

```text
src/
  com.example.hello/
    module-info.java
    com/example/hello/Main.java
```

`module-info.java`:

```java
module com.example.hello {
    requires java.logging;
}
```

`Main.java`:

```java
package com.example.hello;

import java.util.logging.Logger;

public final class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Hello from custom runtime");
    }
}
```

### 6.2. Biên dịch module

Ví dụ minh họa từ thư mục root trên Unix-like:

```shell
mkdir -p mods/com.example.hello

javac \
  -d mods/com.example.hello \
  src/com.example.hello/module-info.java \
  src/com.example.hello/com/example/hello/Main.java
```

Đường dẫn và `javac` phải phù hợp với source directory thực tế. Với Maven/Gradle, compiler task thường sẽ đảm nhiệm bước này; không cần bỏ build tool để dùng lệnh thủ công.

### 6.3. Liên kết runtime có ứng dụng

Ví dụ với JDK distribution có `jmods`:

```shell
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.hello \
  --launcher hello=com.example.hello/com.example.hello.Main \
  --output build/hello-runtime
```

Trong ví dụ Unix-like, dấu `:` là module-path separator. Trên Windows, separator là `;`; đường dẫn `jmods` và cách tham chiếu môi trường cũng khác.

`--launcher hello=module/mainClass` tạo launcher dành cho ứng dụng trong image nếu JDK/linker hỗ trợ và module có main class được khai báo phù hợp. Có thể chạy:

```shell
./build/hello-runtime/bin/hello
```

Hoặc dùng Java launcher:

```shell
./build/hello-runtime/bin/java \
  --module com.example.hello/com.example.hello.Main
```

Hình thức CLI phù hợp với một **modular application** đã có module descriptor. Không áp dụng nguyên xi cho JAR classpath không có explicit module.

### 6.4. JPMS descriptors phải đúng

Nếu module ứng dụng `requires com.example.database` nhưng module này không có trong module path hoặc không có explicit module descriptor phù hợp, `jlink` có thể báo module not found hoặc không xử lý được automatic module.

Cần phân biệt:

- Module ứng dụng chưa được biên dịch.
- Module path sai.
- Module name không trùng thực tế.
- Third-party library là automatic module.
- Có module dependency được khai báo nhưng chưa cung cấp.
- Module descriptor không hợp lệ.

Đừng chỉ thêm mọi JAR trong `lib` vào module path và kỳ vọng `jlink` tự biến chúng thành native image modules.

## 7. Ứng dụng non-modular: jlink vẫn có ích

### 7.1. Không cần chuyển toàn bộ project sang JPMS ngay

Một Spring/Java CLI/service chạy bằng classpath có thể dùng custom runtime với các JDK modules cần thiết rồi giữ application JAR và các dependency ngoài runtime.

Ví dụ:

```text
dist/
  runtime/
    bin/java
    lib/...
  app/
    application.jar
  lib/
    dependency-a.jar
    dependency-b.jar
  bin/
    start.sh
    start.ps1
```

`jlink` tạo phần `runtime/`. Phần `app/` và `lib/` tiếp tục được đóng gói bằng Maven hoặc Gradle.

### 7.2. Ví dụ khởi chạy classpath application

Unix-like:

```shell
./dist/runtime/bin/java \
  -cp "dist/app/application.jar:dist/lib/*" \
  com.example.Main
```

Windows:

```powershell
.\dist\runtime\bin\java.exe -cp "dist\app\application.jar;dist\lib\*" com.example.Main
```

Đây là ví dụ dành cho JAR có main class và dependencies nằm trên classpath. Nếu artifact là executable fat JAR được framework đóng gói theo launcher riêng, có thể cần `-jar application.jar` và layout phù hợp với launcher của framework.

Classpath separator không giống nhau giữa Windows và Unix-like. Để giảm sai sót, cung cấp launcher script riêng cho mỗi OS hoặc dùng packager tạo launcher thích hợp.

### 7.3. Vì sao không link luôn tất cả dependencies?

`jlink` cần module graph rõ ràng. Nhiều JAR bên thứ ba được phát hành theo classpath truyền thống, không có explicit module descriptor. Automatic modules có thể hữu ích tại runtime module path nhưng không được `jlink` xử lý như một explicit module bình thường.

Với ứng dụng lớn, một chiến lược dễ bảo trì là:

```text
jlink(JDK modules)
       +
application JAR
       +
third-party JARs
       =
self-contained application distribution
```

Cách này giảm phụ thuộc Java cài trên hệ thống mà không buộc phải modularize toàn bộ framework trong một lần migration.

## 8. Tìm module cần thiết bằng jdeps

### 8.1. jdeps làm gì?

`jdeps` phân tích phụ thuộc tĩnh của class/JAR, hỗ trợ xác định những Java modules được code tham chiếu. Nó là điểm khởi đầu hữu ích để xây danh sách `--add-modules`.

Ví dụ ứng dụng JAR:

```shell
jdeps \
  --print-module-deps \
  --ignore-missing-deps \
  application.jar
```

Kết quả có thể là một danh sách cách nhau bằng dấu phẩy:

```text
java.base,java.logging,java.net.http
```

Đây là ví dụ đầu ra, không phải kết quả cố định của mọi ứng dụng.

### 8.2. Đưa third-party libraries vào phân tích

Nếu JAR ứng dụng tham chiếu classes của dependencies:

```shell
jdeps \
  --multi-release 21 \
  --ignore-missing-deps \
  --print-module-deps \
  --class-path "lib/*" \
  application.jar
```

`--multi-release 21` có ý nghĩa khi phân tích multi-release JAR cho runtime mục tiêu 21. Với runtime khác, cần chọn release tương ứng trong phạm vi công cụ hỗ trợ.

`--ignore-missing-deps` giúp xuất thông tin khi có dependencies không resolve được, nhưng **không phải bằng chứng mọi dependency đã đầy đủ**. Không nên dựa vào tùy chọn này để bỏ qua một missing library trong production packaging.

### 8.3. Phân tích tất cả artifact liên quan

Nếu chỉ chạy `jdeps` trên main JAR, kết quả có thể bỏ sót JDK modules mà third-party JAR sử dụng. Cần cân nhắc cả dependency JARs và những artifact được tải động, theo khả năng tooling.

Một số framework đóng JAR phụ thuộc bên trong executable archive; `jdeps` không phải lúc nào cũng xử lý nested JAR trực tiếp theo layout đó. Có thể cần tách runtime dependencies thành các JAR riêng để phân tích hoặc dùng tooling chuyên biệt.

### 8.4. Những giới hạn của phân tích tĩnh

`jdeps` không thể chứng minh hoàn toàn module requirements khi chương trình dùng:

- Reflection bằng class name dưới dạng string.
- `Class.forName`.
- `ServiceLoader` và provider modules chỉ được chọn lúc runtime.
- JDBC drivers được tự đăng ký theo service mechanism.
- Plugin JARs tải bằng custom classloader.
- JNI/native integration.
- Script engines.
- Framework code generation.
- JNDI hoặc module được sử dụng trên những code paths ít gặp.
- Multi-release class selection và framework-specific launchers.

Vì thế, kết quả `jdeps` là **đề xuất ban đầu**, không phải danh sách luôn đầy đủ.

## 9. Bổ sung module cho reflection và ServiceLoader

### 9.1. Dynamic features có thể cần thêm module

Một ứng dụng tưởng chỉ dùng `java.base` nhưng có thể thực sự cần:

| Module | Tình huống cần xem xét |
|---|---|
| `java.logging` | Java Util Logging hoặc framework bridge |
| `java.net.http` | HTTP Client API của JDK |
| `java.sql` | JDBC APIs |
| `java.naming` | JNDI, directory services |
| `java.xml` | XML processing |
| `java.desktop` | AWT, image processing hoặc UI APIs |
| `java.management` | MXBeans/management APIs |
| `jdk.management` | Một số management extensions của JDK |
| `jdk.jfr` | Java Flight Recorder |
| `java.instrument` | Java instrumentation agents |
| `jdk.attach` | Attach API tooling |
| `jdk.unsupported` | Một số legacy APIs như `sun.misc.Unsafe`, cần rà soát |
| `jdk.charsets` | Charset providers ngoài các charset lõi |
| `jdk.localedata` | Locale data mở rộng |
| `jdk.crypto.ec` | Security provider hỗ trợ các thuật toán phù hợp |

Bảng mô tả những **ứng viên cần đánh giá**, không phải lời khuyên luôn thêm tất cả module. Một số module được kéo theo transitively, một số provider cần được chọn/bind đúng cách, và tập module có thể thay đổi theo JDK.

### 9.2. Ví dụ mở rộng danh sách module

```shell
jlink \
  --add-modules java.base,java.logging,java.sql,java.naming,jdk.crypto.ec \
  --output build/runtime
```

Không được suy luận rằng danh sách này đủ cho một framework cụ thể. Hãy dùng `jdeps`, tài liệu framework/vendor và các integration tests chạy trên image thực tế.

### 9.3. Dùng --bind-services

`jlink --bind-services` có thể đưa vào modules cung cấp service implementations tương ứng với module graph theo khả năng của JDK.

Ví dụ:

```shell
jlink \
  --add-modules java.base,java.net.http \
  --bind-services \
  --output build/runtime-with-providers
```

Ưu điểm là giảm nguy cơ thiếu service provider, nhưng nhược điểm có thể là **image lớn hơn nhiều** do nhiều provider modules được kéo vào. Không nên coi đây là lựa chọn luôn tối ưu.

Sau khi tạo image, kiểm tra `--list-modules` và thử các hành vi thực tế. Nếu application dùng third-party providers ở JAR ngoài image, `--bind-services` không tự biến tất cả thư viện classpath thành modules được link.

### 9.4. Dịch vụ cấu hình động

Một số tính năng chỉ kích hoạt khi có cấu hình:

```text
App start -> không dùng XML -> startup thành công
User export report -> cần XML -> lỗi do thiếu module
```

Do đó, runtime image tối giản cần thử toàn bộ các luồng nghiệp vụ quan trọng, không chỉ healthcheck.

## 10. Security providers, TLS và truststore

### 10.1. Một runtime nhỏ vẫn cần giao tiếp an toàn

Một service có thể chỉ gửi HTTPS request nhưng thực tế cần các thành phần:

- TLS implementation và cryptography providers.
- Chứng thư gốc để xác minh server certificates.
- Security policies.
- Supported algorithms/cipher suites.
- Truststore hoặc custom CA configuration.
- HTTP client và hostname verification.

Nếu custom runtime thiếu provider cần thiết hoặc truststore không tương thích, lỗi có thể xuất hiện như:

```text
javax.net.ssl.SSLHandshakeException
java.security.NoSuchAlgorithmException
java.security.KeyStoreException
```

Không nên vội thêm mọi `--add-modules`. Phải kiểm tra nguyên nhân: certificate chain không tin cậy, thiếu provider, protocol disabled, hostname mismatch hoặc lỗi network.

### 10.2. jdk.crypto.ec và những provider khác

Một số runtime image tối giản có thể thiếu module provider như `jdk.crypto.ec` nếu không được chọn theo module graph hoặc service binding phù hợp.

Trong ứng dụng dùng TLS, hãy xác minh rằng các thuật toán/security providers cần thiết hoạt động trên runtime cuối. Cấu hình cụ thể phụ thuộc JDK distribution, provider và phiên bản.

### 10.3. Truststore là dữ liệu bảo mật có vòng đời riêng

Một runtime đóng gói kèm có thể mang kho chứng thư mặc định, thường được quản lý trong Java runtime hoặc cấu hình hệ thống theo distribution.

Khi cập nhật runtime, truststore có thể thay đổi do cập nhật root CA và security policies. Nếu ứng dụng sử dụng custom truststore, phải có quy trình:

1. Quản lý file CA/keystore an toàn.
2. Không ghi private keys hoặc password trực tiếp vào repository.
3. Kiểm tra quyền đọc của process.
4. Xác định cách cấu hình `javax.net.ssl.trustStore` nếu áp dụng.
5. Kiểm thử kết nối HTTPS/JDBC/TLS thực tế.
6. Có kế hoạch xử lý certificate rotation.

Không khóa một bản runtime không được vá chỉ vì “các chứng chỉ hiện tại vẫn hoạt động”.

## 11. Locale, timezone, charset và Unicode

### 11.1. Locale data không chỉ dùng cho UI

Ứng dụng có thể format ngày, số và tiền tệ theo locale:

```java
import java.text.NumberFormat;
import java.util.Locale;

var fmt = NumberFormat.getCurrencyInstance(
    Locale.forLanguageTag("vi-VN")
);

System.out.println(fmt.format(123456.78));
```

Nếu runtime custom không có dữ liệu locale phù hợp hoặc có behavior khác do JDK version/tzdb/locale providers, output có thể thay đổi.

### 11.2. jdk.localedata

Module `jdk.localedata` cung cấp dữ liệu locale mở rộng trong các JDK có module này. Khi ứng dụng cần nhiều locale, cần kiểm tra nó có trong image hay không và có nên sử dụng tùy chọn lọc locales của `jlink` trên JDK đích hay không.

Ví dụ minh họa:

```shell
jlink \
  --add-modules java.base,jdk.localedata \
  --include-locales=en,vi \
  --output build/runtime-localized
```

Tùy chọn `--include-locales` được cung cấp bởi plugin trong những JDK hỗ trợ; cú pháp và locale coverage cần được kiểm tra bằng `jlink --list-plugins` của đúng toolchain.

### 11.3. Timezone database

Java runtime cung cấp quy tắc timezone. Ứng dụng lên lịch theo múi giờ địa phương có thể bị ảnh hưởng bởi cập nhật dữ liệu tzdb.

Các test cần có:

- `ZoneId.of("Asia/Ho_Chi_Minh")` được hỗ trợ.
- Parse/format date-time theo locale mong đợi.
- Lịch chạy theo timezone thật trong production.
- Những timezone có DST được xử lý đúng nếu ứng dụng phục vụ quốc tế.
- Runtime mới có cập nhật timezone data phù hợp.

### 11.4. Charset và default encoding

JDK hiện đại có những thay đổi liên quan default charset, trong đó JEP 400 đưa UTF-8 làm mặc định ở Java 18 trong phần lớn trường hợp. Tuy nhiên, ứng dụng vẫn nên chỉ định charset tường minh khi đọc/ghi dữ liệu có hợp đồng:

```java
String text = java.nio.file.Files.readString(
    path,
    java.nio.charset.StandardCharsets.UTF_8
);
```

Một runtime tùy biến thiếu charset provider có thể gây lỗi ở luồng xử lý legacy encoding dù những test UTF-8 thông thường vẫn đạt.

## 12. Java agents, JFR và diagnostic tooling

### 12.1. Instrumentation trong runtime custom

Nếu ứng dụng dùng agent khi startup:

```shell
./runtime/bin/java \
  -javaagent:agents/apm.jar \
  -jar application.jar
```

Runtime image cần hỗ trợ instrumentation và các module/capabilities mà agent yêu cầu. Ví dụ module `java.instrument` có thể cần được đưa vào image.

Không giả định mọi agent hoạt động chỉ vì `java` launcher có mặt. Agent có thể dùng thêm classloading, JDK internals, JVMTI, native libraries hoặc quản lý module access.

### 12.2. jdk.jfr và management

Đối với production observability, đội SRE có thể cần:

- Java Flight Recorder.
- Thread dumps.
- Heap dumps.
- GC logging.
- MXBeans/JMX.
- Attach API và `jcmd` trên một số môi trường.
- Native profiler hoặc APM agents.

Một runtime image tối giản có thể không mang mọi công cụ JDK. Nếu các công cụ này là một phần quy trình incident response, cần xác định cách cung cấp chúng — trong image, trong một companion diagnostic environment hoặc một cách khác được vendor hỗ trợ.

### 12.3. Dynamic attach khác startup agent

Khi JDK mới đưa cảnh báo hoặc giới hạn dynamic agent loading, vấn đề này phải được đánh giá riêng với việc có module `java.instrument` hay không.

Một runtime có `java.instrument` không tự bảo đảm:

- Attach Mechanism đang bật.
- `jdk.attach` có mặt trong image cần dùng.
- OS/process namespace cho phép attach.
- Dynamic agent loading được JVM target cho phép.
- Agent tương thích class-file versions của ứng dụng.

Đối với runtime dùng JDK 21 trở đi, cần đọc chính sách dynamic agent loading của phiên bản JDK đích và quyết định startup agent hay dynamic agent theo nhu cầu vận hành.

### 12.4. Không loại bỏ khả năng chẩn đoán chỉ để tiết kiệm vài MB

Một dịch vụ production khó chẩn đoán có thể tốn chi phí vận hành lớn hơn lợi ích tiết kiệm dung lượng nhỏ. Trước khi bỏ JFR, management hoặc những thành phần hỗ trợ observability, nên thử kịch bản sự cố:

```text
Service có latency tăng
    |
    v
Có thể lấy thread/GC/JFR data?
    |
    +-- Có --> điều tra được
    |
    +-- Không --> phải rebuild/redeploy runtime?
```

Đây là quyết định product/SRE cần được ghi nhận, không chỉ là lựa chọn kỹ thuật của `jlink`.

## 13. Đóng gói đa nền tảng: không copy một image đi mọi nơi

### 13.1. Runtime image là artifact theo hệ điều hành/kiến trúc

Một JAR Java thông thường có thể tương đối portable, nhưng `jlink` image chứa JVM launcher và native runtime components theo platform.

Vì vậy:

```text
runtime-windows-x64  != runtime-linux-x64
runtime-linux-x64    != runtime-linux-aarch64
runtime-macos-arm64  != runtime-windows-arm64
```

Không tạo image trên máy Linux rồi giả định nó chạy trực tiếp trên Windows. Thông thường cần xây image bằng toolchain phù hợp cho target platform; việc cross-targeting phụ thuộc khả năng và bộ module tương ứng của công cụ, nên không được mặc định hỗ trợ.

### 13.2. Ma trận build artifacts

| Target | Runtime image | Gói phát hành |
|---|---|---|
| Windows x64 | JVM và native components Windows x64 | ZIP/application image/installer |
| Windows ARM64 | JVM và native components Windows ARM64 | ZIP/installer tương ứng |
| Linux x64 | JVM và native components Linux x64 | TAR/OCI layer |
| Linux ARM64 | JVM và native components Linux ARM64 | TAR/OCI layer |
| macOS x64 | JVM và native components macOS x64 | Application bundle/installer |
| macOS ARM64 | JVM và native components macOS ARM64 | Application bundle/installer |

Ma trận chỉ nêu khả năng đóng gói theo target, không khẳng định mọi JDK vendor đều cung cấp binary cho mọi platform.

### 13.3. Linux libc và native dependencies

Trên Linux, cần xác định:

- glibc hay musl environment.
- CPU architecture.
- Native dependencies do JNI/framework sử dụng.
- Base container image.
- File permissions.
- Runtime linker và thư viện hệ thống.
- Security policies hoặc FIPS requirements.

Một runtime được build cho một môi trường Linux không tự bảo đảm hoạt động trên mọi distro và libc khác nhau.

### 13.4. Windows và macOS

Trên Windows, launcher thường có `.exe` và script dùng `.bat`/PowerShell; đường dẫn và separator khác Unix-like.

Trên macOS, application bundle, code signing và notarization có thể quan trọng đối với desktop distributions. Một runtime image `jlink` tự nó không giải quyết đầy đủ quy trình cài đặt/ký phân phối; `jpackage` và tooling nền tảng có vai trò riêng.

## 14. Tạo launcher tránh phụ thuộc PATH

### 14.1. Launcher Unix-like

Ví dụ `bin/start.sh`:

```sh
#!/bin/sh
set -eu

APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

exec "$APP_HOME/runtime/bin/java" \
  -cp "$APP_HOME/app/application.jar:$APP_HOME/lib/*" \
  com.example.Main "$@"
```

Đoạn script giả định:

- `bin/start.sh` nằm trong bundle.
- `runtime/bin/java` tồn tại cho OS tương ứng.
- Main class là `com.example.Main`.
- Các dependencies nằm trong `lib/*`.
- `APP_HOME` trỏ đúng thư mục bundle.

`"$@"` chuyển từng argument nhận được vào Java application mà không ghép thành một chuỗi làm mất ranh giới arguments.

### 14.2. Launcher Windows PowerShell

Ví dụ `bin/start.ps1`:

```powershell
$ErrorActionPreference = "Stop"

$appHome = Split-Path -Parent $PSScriptRoot
$java = Join-Path $appHome "runtime\bin\java.exe"
$appJar = Join-Path $appHome "app\application.jar"
$lib = Join-Path $appHome "lib\*"
$classPath = "$appJar;$lib"

& $java -cp $classPath com.example.Main @args
exit $LASTEXITCODE
```

Đây là ví dụ launcher đơn giản. Nếu ứng dụng đích yêu cầu đường dẫn hoặc cách truyền arguments đặc thù, cần kiểm tra trên Windows thật. Không phụ thuộc hệ thống có lệnh `java` toàn cục.

### 14.3. Không tự trộn shell quoting với Java arguments

Nếu startup script có đường dẫn chứa dấu cách, phải quote đúng theo shell của hệ điều hành. Trong Java code sử dụng `ProcessBuilder`, đường dẫn và argument là các phần tử riêng; không tự thêm dấu nháy như dữ liệu.

Trong bundle, nên giữ các thư mục có tên rõ, không phụ thuộc working directory mà người dùng khởi chạy từ terminal.

### 14.4. Launcher phiên bản hóa

Một cấu trúc thuận tiện để rollback:

```text
releases/
  2.1.0/
    runtime/
    app/
    bin/
  2.2.0/
    runtime/
    app/
    bin/
current -> releases/2.2.0
```

Trên từng OS, `current` có thể được quản lý bằng symlink, junction, config hoặc cơ chế installer phù hợp. Khi cập nhật, không nên sửa file runtime của process đang chạy theo cách không kiểm soát; nên phát hành bundle mới, chuyển startup target và rollback bằng bản phát hành đã được xác minh.

## 15. jpackage: từ custom runtime đến installer

### 15.1. Khi nào dùng jpackage?

Nếu người dùng cuối cần cài ứng dụng desktop/CLI theo cách quen thuộc của hệ điều hành, `jpackage` có thể tạo application image hoặc installer. Nó làm việc với application input và runtime image được cung cấp hoặc tạo theo cơ chế hỗ trợ.

Ví dụ hướng tiếp cận:

```text
Compile Java source
       |
       v
Create application JAR
       |
       v
Build custom runtime with jlink
       |
       v
jpackage creates app image / installer
       |
       v
Sign, publish, test install/uninstall
```

### 15.2. Ví dụ dùng runtime image đã tạo

```shell
jpackage \
  --type app-image \
  --name ExampleApp \
  --input build/app \
  --main-jar application.jar \
  --main-class com.example.Main \
  --runtime-image build/runtime \
  --dest build/package
```

Ví dụ này yêu cầu `build/app/application.jar` và runtime image đã tồn tại. Các tùy chọn, image layout, dependency packaging, signing và loại installer phụ thuộc OS/JDK version.

Không coi một lệnh minh họa là cấu hình production hoàn chỉnh. Cần kiểm tra cả installer behavior, icon, version, file associations, OS permissions và update strategy.

### 15.3. Đừng kết hợp sai hai cơ chế tạo runtime

Nếu `jpackage` tự tạo runtime theo cấu hình của nó, không nhất thiết phải chạy `jlink` riêng trước. Nếu tổ chức cần kiểm soát module list, có thể tạo runtime image bằng `jlink` rồi truyền qua `--runtime-image` khi phiên bản công cụ hỗ trợ.

Điều cần quyết định là **ai chịu trách nhiệm chọn module và tạo runtime artifact cuối**. Tránh để hai bước cùng tạo runtime với cấu hình khác nhau rồi dùng nhầm image.

### 15.4. Bản phát hành có nhiều native artifacts

Ứng dụng desktop có thể đi kèm:

- Java runtime image.
- Main application JAR.
- Các JAR dependencies.
- Native libraries.
- Resource files.
- Configuration templates.
- Launcher và installer metadata.

Một số tài nguyên cần cập nhật độc lập, một số cần đi cùng runtime; nên xác định rõ trong release manifest.

## 16. Container images và jlink

### 16.1. Khi nào custom runtime hữu ích trong container?

Trong containerized services, một image thường chứa JDK/JRE base image và application JAR:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

Đây là mẫu khái niệm. Một image dùng runtime `jlink` có thể giúp giảm kích thước và kiểm soát thành phần, đặc biệt nếu ứng dụng chỉ dùng số ít JDK modules.

### 16.2. Multi-stage Dockerfile

Ví dụ minh họa cho ứng dụng classpath và runtime được tạo từ JDK ở build stage:

```dockerfile
FROM eclipse-temurin:21-jdk AS runtime-builder

RUN jlink \
    --add-modules java.base,java.logging,java.net.http,jdk.crypto.ec \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output /opt/custom-runtime

FROM debian:bookworm-slim

WORKDIR /app

COPY --from=runtime-builder /opt/custom-runtime /opt/java
COPY application.jar /app/application.jar

ENV PATH="/opt/java/bin:$PATH"

ENTRYPOINT ["/opt/java/bin/java", "-jar", "/app/application.jar"]
```

Đây là Dockerfile để minh họa hai stages, **không phải bản cấu hình bảo mật hoặc phân phối hoàn chỉnh**. Trong sản phẩm thực tế, cần:

- Pin base image bằng digest và patch policy.
- Chọn image chạy phù hợp libc/native dependencies.
- Kiểm soát user không đặc quyền.
- Kiểm tra certificate/truststore và DNS/TLS behavior.
- Giữ các license notices theo nghĩa vụ phân phối.
- Cập nhật runtime khi JDK có security fix.
- Xác minh các module cần dùng cho framework, JDBC, JFR, agents.
- Build và kiểm thử trên đúng CPU architecture.

### 16.3. Distroless và runtime dependencies

Có thể dùng một base image tối giản hoặc distroless khi phù hợp. Tuy nhiên, JVM và native code vẫn có các phụ thuộc OS/platform. Không thể mặc định sao chép runtime image vào một `scratch` image là đủ cho mọi JDK/build.

Một base image nhỏ nhưng thiếu certificate data, locale files hoặc native libraries có thể gây lỗi chỉ xuất hiện trong production. Hãy thử đúng final container image, không chỉ thử runtime builder stage.

### 16.4. Container image có nhiều lớp

Một lợi ích tiềm năng của OCI images là caching và layering. Nếu runtime thay đổi ít hơn ứng dụng, có thể để runtime ở layer trước, JAR ở layer sau; CI/registry có thể tái sử dụng layers.

Nhưng khi có security update JDK, runtime layer **phải được rebuild**. Không nên để một cached layer chứa JVM cũ chỉ vì application code chưa đổi.

## 17. Runtime security patching và vòng đời hỗ trợ

### 17.1. Đóng gói runtime đồng nghĩa sở hữu trách nhiệm vá lỗi

Khi người dùng tự cài Java từ kênh IT, đội nền tảng có thể chịu trách nhiệm cập nhật JRE. Khi ứng dụng phát hành kèm runtime riêng, nhóm phát hành phải theo dõi:

- Security updates của JDK vendor.
- CVEs ảnh hưởng JVM/runtime modules.
- Root CA updates và truststore.
- tzdb/locale data updates.
- Native runtime libraries.
- Release line còn maintenance hay đã EOL.
- Container base image vulnerabilities nếu áp dụng.

Một application.jar không thay đổi vẫn có thể cần release mới chỉ để cập nhật runtime.

### 17.2. Patch level quan trọng hơn nhãn major

Ví dụ:

```text
Java 21 runtime A: patch release cũ
Java 21 runtime B: patch release mới
```

Cả hai có thể báo Java major 21, nhưng khác security fixes, truststore và behavior. Trong release metadata cần lưu JDK vendor, full version/build number, OS/arch và checksum của runtime image.

### 17.3. Đừng cập nhật runtime ngầm, không kiểm thử

Vá runtime là cần thiết nhưng cũng có rủi ro regression:

- TLS/crypto policies thay đổi.
- Timezone/locale data đổi.
- JVM bug fix làm lộ behavior dựa vào lỗi cũ.
- GC hoặc performance behavior khác.
- Native library/agent tương thích khác.

Hãy có CI test matrix cho patch upgrades, canary và rollback. Không bỏ qua mọi validation chỉ vì phiên bản mới cùng major.

### 17.4. Quy trình SBOM và provenance

Một release có thể lưu:

```text
Application version
Source commit
Application artifact SHA-256
JDK vendor
JDK full runtime version
Runtime image target OS/architecture
List of Java modules
Third-party dependency inventory/SBOM
Container image digest
Build tool version
Build timestamp/provenance
Test report
```

Thông tin này giúp xác định một lỗ hổng ảnh hưởng release nào và tạo lại artifact khi cần.

### 17.5. Các nghĩa vụ license và notice

Không phải tất cả JDK distributions có cùng điều khoản phân phối thương mại hoặc yêu cầu notice. Trước khi bundling, kiểm tra license của **đúng vendor, phiên bản và binary**. JDK-derived runtime image cũng có thể cần giữ những license notices mà JDK cung cấp.

`jlink --no-man-pages` hoặc `--no-header-files` không phải cách loại bỏ nghĩa vụ license. Tài liệu pháp lý/notice cần được xử lý theo license áp dụng.

## 18. Kích thước, startup và hiệu năng: đo thay vì đoán

### 18.1. Dung lượng không phải chỉ số duy nhất

Khi so sánh runtime đi kèm:

| Chỉ số | Câu hỏi |
|---|---|
| Runtime image size | Tốn bao nhiêu dung lượng trên ổ đĩa? |
| Download size | File ZIP/installer/container layer nén có dung lượng bao nhiêu? |
| Application startup | Mất bao lâu để sẵn sàng xử lý request? |
| RSS/memory | Có thay đổi đáng kể so với runtime đầy đủ không? |
| CPU | Hiệu năng workload thực tế có khác không? |
| TLS/locale behavior | Có bỏ sót providers/dữ liệu cần thiết không? |
| Diagnostics | Có còn JFR/management/attach path cần thiết không? |
| Update footprint | Mỗi lần vá runtime phải tải lại bao nhiêu byte? |
| Operational complexity | Có thêm lỗi packaging theo OS/architecture không? |

Một runtime nhỏ hơn có thể giảm dung lượng và số module không dùng, nhưng không nên tuyên bố nó luôn chạy nhanh hơn hoặc giảm đáng kể RSS nếu chưa đo.

### 18.2. Đo trên Unix-like

```shell
du -sh build/runtime
du -sh build/app-bundle
```

`du` là công cụ OS, không phải `jlink` option. Kết quả phụ thuộc filesystem, block size và cách đóng gói.

### 18.3. Đo trên PowerShell

```powershell
$bytes = (
    Get-ChildItem "build\runtime" -Recurse -File |
    Measure-Object -Property Length -Sum
).Sum

"{0:N2} MiB" -f ($bytes / 1MB)
```

Khi so sánh qua CI runners, nên lưu cả kích thước file được phân phối và extracted size; hai chỉ số có ý nghĩa khác nhau.

### 18.4. Benchmark phải tương đương

Nếu so sánh runtime image với JDK đầy đủ, cần giữ nguyên:

- Application code và dependencies.
- JVM flags.
- JDK vendor/full patch version nếu có thể.
- OS/architecture.
- Workload và warm-up policy.
- Số lần đo và cách lấy median/percentiles.
- Filesystem/container/network conditions.

Không so sánh bản custom Java 21 với một JDK 8 cũ rồi quy toàn bộ chênh lệch hiệu năng cho `jlink`.

## 19. Cập nhật phiên bản JDK khi dùng jlink

### 19.1. Không chỉ thay tên thư mục

Khi di chuyển từ Java 17 sang Java 21:

1. Chọn JDK 21 distribution được hỗ trợ.
2. Cập nhật build tool/compiler/toolchain nếu cần.
3. Kiểm tra source/bytecode dependencies và framework support.
4. Chạy `jdeps` bằng toolchain phù hợp.
5. Xem lại danh sách `--add-modules` và providers.
6. Tạo runtime image mới bằng `jlink` từ JDK target.
7. Đóng gói application và runtime mới.
8. Kiểm thử trên OS/architecture mục tiêu.
9. Lưu runtime checksum/provenance.
10. Triển khai canary và giữ bản cũ để rollback.

Nếu chỉ copy JAR từ bản cũ vào runtime mới, có thể vẫn chạy nhưng chưa xử lý các thay đổi API/behavior, agent compatibility và cấu hình môi trường.

### 19.2. Module graph có thể thay đổi

Một JDK release có thể tổ chức modules hoặc các implementation providers khác so với bản trước. Vì vậy đừng mặc định output từ `jdeps` trên JDK cũ đủ cho JDK mới.

Cần chạy lại phân tích trong build pipeline, review diff module list và thử các integration cần thiết.

### 19.3. Minimum runtime của third-party libraries

Ứng dụng biên dịch bằng `--release 17` không đảm bảo một dependency mới vẫn hỗ trợ Java 17. Nếu dependency JAR chứa class-file major 65, Java 17 runtime không thể nạp class đó.

Đối với runtime image được link từ Java 17, cần kiểm tra toàn bộ runtime dependency closure tương thích Java 17. Nếu image dùng Java 21, cần xác nhận app và library có thể chạy trên Java 21, không chỉ class-file major.

## 20. Chẩn đoán những lỗi thường gặp

### 20.1. `java: command not found` sau cài đặt

**Nguyên nhân:** launcher script vẫn gọi `java` toàn cục thay vì runtime đi kèm, hoặc đường dẫn bundle bị sai.

**Hướng xử lý:** tham chiếu rõ `runtime/bin/java` theo vị trí của launcher; kiểm tra quyền execute và đúng OS binary.

### 20.2. `Module ... not found` khi chạy jlink

**Nguyên nhân:** module path thiếu module, tên module sai, application module chưa build, hoặc JAR chỉ là automatic module.

**Hướng xử lý:** kiểm tra `--module-path`, `jar --describe-module`, output modules và explicit module descriptors. Với non-modular dependencies, cân nhắc runtime chỉ gồm JDK modules và phân phối JAR riêng.

### 20.3. `java.lang.NoClassDefFoundError` khi chạy ứng dụng

**Nguyên nhân:** runtime dependency JAR bị thiếu, classpath sai, hoặc module Java bị loại.

**Hướng xử lý:** phân biệt class thuộc JDK module hay third-party JAR. Dùng `jdeps`, dependency report và startup logs; không thêm tất cả JDK modules khi lỗi thực ra là thiếu application library.

### 20.4. `java.lang.module.FindException`

**Nguyên nhân:** JPMS module path/descriptor không nhất quán, module bị thiếu hoặc cấu hình launcher sai.

**Hướng xử lý:** đối chiếu `requires` và module path với bộ module đã link, thử `--list-modules`, `jar --describe-module` và lệnh startup chính xác.

### 20.5. `UnsupportedClassVersionError`

**Nguyên nhân:** application hoặc dependency có bytecode cao hơn JVM trong runtime image.

**Hướng xử lý:** xác định runtime Java version, major class-file version và dependency nguồn. `jlink` không tự hạ target bytecode của application.

### 20.6. `NoSuchAlgorithmException` hoặc TLS handshake lỗi

**Nguyên nhân khả dĩ:** thiếu security provider, truststore, protocol hoặc chứng chỉ không tin cậy.

**Hướng xử lý:** xem security providers và truststore của image, kiểm tra CA/hostname/protocol, thêm module cần thiết dựa vào bằng chứng và chạy HTTPS integration tests.

### 20.7. `UnsupportedCharsetException`

**Nguyên nhân:** ứng dụng dùng legacy charset nhưng runtime chưa có provider phù hợp.

**Hướng xử lý:** xác minh charset thật của dữ liệu và module/provider cần thiết như `jdk.charsets` khi áp dụng. Nếu có thể, chuẩn hóa giao thức sang UTF-8 với migration rõ ràng.

### 20.8. Locale hoặc định dạng ngày/tiền tệ thay đổi

**Nguyên nhân:** thiếu `jdk.localedata` hoặc khác locale/tzdb giữa JDK versions.

**Hướng xử lý:** kiểm tra locale/timezone configuration, image modules, plugin lọc locale và golden fixtures cho date/number formatting.

### 20.9. Java agent không hoạt động

**Nguyên nhân khả dĩ:** thiếu `java.instrument`, JDK/bytecode agent không tương thích, sai `-javaagent` path, policy dynamic attach hoặc OS permissions.

**Hướng xử lý:** xác định startup vs dynamic agent, kiểm tra modules, manifest, logs và JDK support matrix. Không chỉ bật `jdk.attach` khi agent cần cơ chế khác.

### 20.10. JFR hoặc `jcmd` không sẵn có

**Nguyên nhân:** runtime được tối giản hoặc không mang các công cụ serviceability cần thiết.

**Hướng xử lý:** xác định diagnostic workflow, bổ sung module/tool trong build phù hợp hoặc cung cấp companion environment có quyền phù hợp. Không coi custom image là một JDK đầy đủ.

### 20.11. Chạy Linux image trên Windows thất bại

**Nguyên nhân:** runtime image chứa native components theo OS/architecture.

**Hướng xử lý:** tạo gói riêng cho từng platform được hỗ trợ và kiểm tra native dependencies.

### 20.12. Native library không nạp được trong container

**Nguyên nhân:** khác CPU architecture, libc, runtime linker, permissions hoặc classifier.

**Hướng xử lý:** đối chiếu JDK/container base image/native library ABI. `jlink` không tự giải quyết native compatibility.

### 20.13. Build image nhỏ nhưng ứng dụng chỉ lỗi ở production

**Nguyên nhân:** một module được dùng gián tiếp qua reflection/ServiceLoader/JDBC/feature flag chưa được test.

**Hướng xử lý:** bổ sung runtime module có căn cứ, mở rộng test paths và chạy toàn bộ acceptance matrix trên **final distributed image**.

## 21. Thiết kế pipeline Maven

### 21.1. Những phần Maven nên quản lý

Trong dự án Maven, có thể phân chia:

```text
validate / compile / test
         |
         v
package application JAR
         |
         v
resolve runtime dependencies
         |
         v
analyze JDK modules
         |
         v
jlink runtime image
         |
         v
assemble distribution
         |
         v
verify / integration tests / publish
```

Không nhất thiết mọi thao tác phải nằm trong Maven plugin duy nhất. Một số tổ chức dùng script packaging đã được version-control và CI orchestration.

### 21.2. Kiểm soát toolchain

Ví dụ property compile target:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Đây là target cho application code, không phải chỉ thị `jlink` tự chọn đúng JDK. Toolchain dùng để chạy `jlink` cần được pin theo policy và đối chiếu với JDK runtime target.

### 21.3. Application dependencies cần được đóng gói

Nếu ứng dụng vẫn dùng classpath, Maven dependency/plugin configuration cần cấp đủ runtime-scope JARs cho distribution. Đừng chỉ copy application JAR và runtime image nếu nó không chứa những dependencies cần thiết.

Đối với JAR dùng plugin tạo uber JAR, hãy kiểm tra merge resources, service descriptors và nested JAR behavior. `jlink` không thay thế dependency packaging.

### 21.4. Reproducibility

Pin Maven Wrapper/compiler/plugin versions, dependency versions và JDK vendor/full version. Lưu module list, runtime image checksum và license notices cùng release.

Cùng `pom.xml` nhưng dùng JDK patch release khác có thể tạo runtime image khác byte; không nên suy rằng chỉ cần pin Maven là đủ.

## 22. Thiết kế pipeline Gradle

### 22.1. Gradle Java toolchains

Ví dụ Groovy DSL:

```groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'com.example.Main'
}
```

Toolchain giúp Gradle chọn JDK cho các task được tích hợp. Nếu sử dụng `jlink` qua plugin hoặc custom task, phải kiểm tra tool đó lấy `jlink` từ JDK nào; không mặc định mọi task đều dùng đúng toolchain.

### 22.2. Task liên kết runtime

Một Gradle build có thể dùng plugin chuyên cho jlink hoặc custom task gọi `jlink` bằng executable từ JDK đã được cấp. Nên thiết kế đầu vào/đầu ra rõ:

```text
Inputs:
  Java modules selected
  Toolchain JDK version/vendor
  Application JAR
  Dependencies / module descriptors
  jlink plugin options

Outputs:
  build/custom-runtime/
  build/distribution/
```

Tránh những task phụ thuộc ngầm vào `JAVA_HOME` của máy developer nhưng CI dùng JDK khác.

### 22.3. Version catalog, BOM và locks

Các công cụ như version catalog, Gradle platform/BOM và dependency locking giúp kiểm soát dependency graph, nhưng không tự kiểm tra modules trong runtime image.

Nếu framework được nâng, `jdeps` và integration test phải được chạy lại; lockfile không thể chứng minh ứng dụng không cần thêm JDK module.

### 22.4. Không đưa toàn bộ custom runtime vào mọi test task

Có thể dùng JDK đầy đủ trong unit tests để có tốc độ phát triển tốt, nhưng phải có **ít nhất một lớp test** chạy với final custom runtime. Nếu chỉ test trên full JDK, các module bị thiếu sẽ không được phát hiện.

## 23. Reproducibility và cache của runtime image

### 23.1. Những đầu vào ảnh hưởng runtime image

Để tái tạo image:

- JDK vendor/distribution.
- JDK full build version.
- OS/architecture.
- JDK modules được chọn.
- `jlink` options và plugin versions.
- Build environment.
- External application modules nếu link chung.
- Certificates/configuration mà bước packaging bổ sung sau đó.
- File timestamps/permissions và archive packaging settings.

### 23.2. Image checksum phải gắn với phạm vi rõ

Một runtime image là thư mục nhiều file. Để so sánh bằng checksum, có thể đóng nó thành archive với file order/timestamps được kiểm soát, hoặc lập manifest checksums cho từng file. Nếu chỉ tính checksum cho ZIP phát hành, phải kiểm soát metadata của ZIP để có tính tái lập byte-for-byte.

Không so sánh thô một image Windows với image Linux rồi cho rằng khác SHA-256 là lỗi build.

### 23.3. Cache build phải được invalidated khi JDK đổi

Một cache key quá đơn giản:

```text
cache-key = application-commit
```

có thể tái sử dụng runtime image cũ khi JDK security patch đổi. Một key hợp lý cần chứa JDK version/vendor, target platform và jlink module/configuration fingerprint.

### 23.4. Immutable release

Khi đã phát hành:

```text
ExampleApp-2.4.0-linux-x64.tar.gz
SHA-256: ...
Runtime JDK: ...
Application commit: ...
```

Không ghi đè cùng tên/version bằng artifact khác nếu hệ thống update và caching dựa vào version. Nên tăng release version hoặc dùng content-addressed artifacts và lưu provenance.

## 24. Khả năng rollback và cập nhật runtime

### 24.1. Runtime là một phần version của ứng dụng

Nếu một phiên bản app được kiểm thử với Java 21.0.x cụ thể, rollback ứng dụng nhưng giữ runtime của bản mới có thể không khôi phục đúng môi trường đã được kiểm chứng.

Một chiến lược an toàn là version hóa toàn bộ bundle:

```text
Release 3.1.0:
  app.jar v3.1.0
  runtime JDK version A

Release 3.2.0:
  app.jar v3.2.0
  runtime JDK version B
```

Rollback bundle có thể phục hồi cả app và runtime. Tuy nhiên, nếu dữ liệu đã được nâng schema, rollback vẫn cần chính sách dữ liệu riêng.

### 24.2. Atomic update

Đối với desktop/service distribution, quy trình update nên tránh trạng thái nửa cũ nửa mới:

1. Download/copy bundle mới vào thư mục tạm.
2. Xác minh checksum/signature.
3. Thử cấu trúc file và quyền.
4. Dừng hoặc chuyển traffic khỏi process cũ theo quy trình.
5. Chuyển đường dẫn launcher/version target theo thao tác atomic hoặc cơ chế installer được hỗ trợ.
6. Khởi động, healthcheck và quan sát.
7. Rollback khi cần.

Không ghi đè các binary trong runtime directory đang được process chạy sử dụng.

### 24.3. Dữ liệu và protocol vẫn cần tương thích

`jlink` chỉ quyết định môi trường chạy; nó không tự đảm bảo JSON, database schema, Java Serialization hoặc message protocol giữ compatibility.

Nếu bản ứng dụng mới đã ghi dữ liệu mà phiên bản cũ không đọc được, rollback runtime/JAR vẫn có thể thất bại. Đây là một trục migration riêng cần test.

## 25. Ma trận kiểm thử custom runtime

Một bảng test hữu ích:

| Nhóm | Tình huống cần kiểm thử | Lý do |
|---|---|---|
| Startup | Khởi động bằng `runtime/bin/java` | Không phụ thuộc Java toàn cục |
| Java modules | `--list-modules` và đường chạy thật | Phát hiện thiếu module |
| Dependency | Nạp class, SPI, JDBC driver | Phát hiện thiếu JAR/service provider |
| Networking | HTTP/HTTPS, proxy, DNS | TLS/crypto/truststore |
| Data | JDBC, XML, JSON, timezone | API và providers |
| Locale | vi-VN, en-US và Unicode | Locale/charset behavior |
| File I/O | Read/write/temp, permissions | OS-specific paths |
| Security | Auth, certificates, cryptography | Provider và trust policy |
| Observability | Logs, JFR, agents, management | Khả năng chẩn đoán |
| Native | JNI, image codecs nếu dùng | ABI/OS/architecture |
| Performance | Startup, RSS, latency | Đánh giá trade-off |
| Deployment | ZIP/installer/container image | Final artifact |
| Update | Patch JDK, install/uninstall, rollback | Lifecycle runtime |

### 25.1. Test trên JDK thấp nhất được công bố

Nếu application JAR cần Java 17 nhưng runtime được link từ Java 21, **bản phát hành đóng gói** chỉ chạy trên Java 21 runtime đi kèm. Nếu tổ chức đồng thời phát hành JAR cho người dùng tự mang Java 17, phải có một test path riêng với Java 17.

Không đồng nhất “bytecode hỗ trợ Java 17” với “bundle chỉ gồm runtime Java 21 vẫn được kiểm thử trên Java 17”.

### 25.2. Test theo nền tảng

Ví dụ deployment targets:

```text
Windows x64      : app + runtime Windows x64
Linux x64 glibc  : app + runtime Linux x64
Linux ARM64      : app + runtime Linux ARM64
macOS ARM64      : app + runtime macOS ARM64
```

Không dùng thành công của một target để kết luận toàn bộ targets đều tương thích. Đặc biệt cần chạy native integration tests trên kiến trúc thật khi có JNI.

### 25.3. Test trong môi trường không có Java cài sẵn

Nếu yêu cầu sản phẩm là self-contained, nên thử trên VM/container sạch không có `java` toàn cục. Startup phải dùng runtime đi kèm và không ngầm phụ thuộc `JAVA_HOME` của hệ thống.

## 26. Những sai lầm thường gặp

**Chỉ chép thư mục `jre` từ JDK 8 sang bản mới.** Cấu trúc runtime và module system đã thay đổi; cần dùng JDK/runtime distribution phù hợp cho phiên bản đích.

**Cho rằng jlink chỉ chạy được với ứng dụng modular.** `jlink` link Java modules; ứng dụng classpath vẫn có thể sử dụng custom runtime chứa JDK modules rồi được đóng gói riêng.

**Cho rằng jlink nhúng mọi JAR bên ngoài.** Nhiều third-party JAR không phải explicit modules và không thể được link trực tiếp như mô hình JPMS chuẩn.

**Tin hoàn toàn vào jdeps.** Phân tích tĩnh có thể bỏ sót reflection, ServiceLoader, JDBC, plugin hoặc framework-specific code paths.

**Tạo image cực nhỏ chỉ có java.base mà không test.** Startup có thể thành công nhưng HTTPS/JDBC/locale/diagnostics thất bại.

**Quên module/provider bảo mật và locale.** TLS, encoding hoặc format ngày/tiền có thể lỗi ở production.

**Cho rằng custom runtime chạy trên mọi OS/architecture.** Image chứa native components theo platform.

**Bỏ hết công cụ chẩn đoán để giảm vài MB.** SRE có thể mất JFR/JMX/attach path cần cho incident response.

**Cho rằng jlink tự bảo đảm Java source/dependency compatibility.** Nó không hạ bytecode của app hoặc sửa framework/API đã bị loại bỏ.

**Chỉ cập nhật application.jar khi có JDK security patch.** Runtime đi kèm phải được cập nhật và phát hành lại.

**Đóng gói runtime nhưng không kiểm tra license.** Quyền phân phối và notices phụ thuộc binary/vendor/license.

**Test trên JDK đầy đủ nhưng không test final image.** Đây là nguồn lỗi module thiếu phổ biến nhất.

## 27. Quy trình migration thực hành từ JRE cũ sang jlink

### Giai đoạn 1: Kiểm kê baseline

Thu thập:

```text
Application:
  version
  main class/module
  framework
  package format
  runtime dependencies

Existing Java:
  vendor
  full version
  OS/architecture
  installation/distribution model
  JVM flags
  truststore/custom CA

Operations:
  diagnostic tools
  agents/JFR
  deployment/update/rollback
  license policy
```

Không cần đọc tất cả file trên máy production nếu có inventory được quản trị, nhưng phải xác nhận đúng runtime mà ứng dụng đang dùng.

### Giai đoạn 2: Chọn mô hình phân phối

Lựa chọn:

- Giữ system-managed JDK/runtime nếu hạ tầng đã quản trị Java tập trung.
- Bundle vendor runtime distribution nếu muốn ít tùy biến.
- Dùng `jlink` khi cần kiểm soát module list và image size.
- Kết hợp `jlink` + `jpackage` cho desktop installer.
- Đưa `jlink` runtime vào OCI image cho containerized service.

Đây là các lựa chọn kiến trúc, không phải một chuỗi bắt buộc làm hết mọi bước.

### Giai đoạn 3: Xác định Java modules và dependencies

1. Build application bằng toolchain chuẩn.
2. Xuất dependency graph/packaged JAR list.
3. Dùng `jdeps --print-module-deps` với classpath phù hợp.
4. Bổ sung modules cho reflection, services, JDBC, locales, crypto, JFR/agent.
5. Kiểm tra explicit module descriptors nếu muốn link application module.
6. Ghi module list như một phần release configuration.

### Giai đoạn 4: Tạo runtime image

Ví dụ tổng quát cho một classpath application dùng JDK modules:

```shell
jlink \
  --add-modules java.base,java.logging,java.net.http,java.sql,jdk.crypto.ec \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
```

Đây là cấu hình giả định, **không phải module list đủ cho mọi ứng dụng**.

### Giai đoạn 5: Tạo distribution

```text
build/dist/
  runtime/
  app/
    application.jar
  lib/
    ...
  agents/
    ... (nếu có)
  bin/
    start.sh
    start.ps1
  licenses/
    ...
  manifest.json
```

Launcher phải dùng đúng runtime tương ứng OS và thiết kế app. Manifest có thể ghi application version, JDK version và checksums.

### Giai đoạn 6: Test bằng final runtime

Chạy chính `build/dist/runtime/bin/java` hoặc launcher trong final distribution, không chỉ build JVM của CI.

Kiểm tra test matrix: startup, TLS, JDBC, locale, reflection/SPI, native, agents/JFR, performance, OS/architecture và rollback.

### Giai đoạn 7: Release và quản trị patch

1. Pin JDK vendor/full version và base image.
2. Lưu artifact checksums/provenance.
3. Publish immutable bundle/installer/OCI image.
4. Triển khai canary.
5. Theo dõi runtime exceptions, startup time và resource usage.
6. Lưu bản phát hành trước để rollback.
7. Theo dõi JDK security updates và rebuild runtime định kỳ.

## 28. Bài tập thực hành

### Bài tập 1: Tạo runtime cho CLI

Một CLI Java 21 sử dụng `java.logging` và `java.net.http`, không dùng GUI và không có native dependency.

Hãy:

1. Build application JAR.
2. Chạy `jdeps --print-module-deps`.
3. Tạo image bằng `jlink`.
4. Đóng gói app JAR và runtime thành một thư mục.
5. Viết launcher không phụ thuộc Java trong PATH.
6. So sánh kích thước image và JDK đầy đủ.
7. Chạy smoke test HTTP/HTTPS trên runtime custom.

### Bài tập 2: Phát hiện module bị bỏ sót

Một app JDBC chạy được trên JDK đầy đủ nhưng lỗi khi khởi chạy một màn hình báo cáo trên custom runtime.

Hãy xác định:

- Đây là thiếu Java module hay thiếu third-party driver JAR?
- Có sử dụng `ServiceLoader`/JDBC auto-registration không?
- `jdeps` có nhìn thấy code path này không?
- Cần bổ sung test nào để phát hiện trước khi release?

### Bài tập 3: Runtime cho nhiều nền tảng

Một desktop app cần phát hành trên Windows x64 và macOS ARM64. Hãy thiết kế build matrix, giải thích vì sao không thể lấy nguyên runtime image Windows làm runtime macOS, và đề xuất bước `jpackage`/installer signing cho từng target.

### Bài tập 4: Java agent và JFR

Một service cần APM agent khi startup và JFR trong lúc điều tra sự cố. Hãy lập danh sách modules/capabilities cần kiểm tra khi tạo runtime bằng `jlink`, nêu rõ những yếu tố không thể kết luận chỉ từ `jdeps`.

### Bài tập 5: Security patch

Bản phát hành 2.4.0 đóng gói JDK runtime có lỗ hổng mới công bố nhưng source code ứng dụng không thay đổi. Hãy xây dựng quy trình tái tạo bundle với JDK patch mới, xác minh checksum, test TLS/database và triển khai/rollback.

## 29. Checklist trước khi công bố runtime đóng gói

### Kiến trúc và module

- [ ] Đã xác định có cần bundle runtime hay vẫn dùng system-managed Java.
- [ ] Đã phân biệt JDK, JRE/runtime distribution, `jlink` và `jpackage`.
- [ ] Biết ứng dụng là modular hay classpath-based.
- [ ] Đã kiểm tra Java modules bằng `jdeps` và test thực tế.
- [ ] Không cố link automatic modules như explicit modules khi không được hỗ trợ.
- [ ] Đã xem xét reflection, ServiceLoader, JDBC và plugin loading.
- [ ] Đã kiểm tra module list trong image cuối.

### Runtime behavior

- [ ] Launcher dùng `runtime/bin/java`, không phụ thuộc Java toàn cục.
- [ ] App và dependencies được đóng gói đầy đủ.
- [ ] HTTPS/truststore/security providers hoạt động.
- [ ] Charset, locale và timezone phù hợp.
- [ ] Java agents, JFR, management và diagnostic workflow còn dùng được.
- [ ] JNI/native dependencies phù hợp OS/architecture.
- [ ] Runtime thấp nhất và class-file versions của dependencies đã được xác minh.

### Phát hành

- [ ] JDK vendor/full patch version được pin.
- [ ] Có bundle riêng cho mỗi OS/architecture được hỗ trợ.
- [ ] Đã kiểm tra license và notices.
- [ ] Runtime/image checksums và provenance được lưu.
- [ ] Installer/container image được kiểm thử đúng final artifact.
- [ ] Có cơ chế cập nhật runtime khi JDK có security patch.
- [ ] Có rollout/canary/rollback và dữ liệu monitoring phù hợp.
- [ ] Không ghi đè runtime directory đang được process sử dụng.

## Kết luận

**JRE đóng gói sẵn** và **runtime tùy biến bằng `jlink`** cùng giải quyết nhu cầu chủ động môi trường chạy Java, nhưng ở hai mức độ kiểm soát khác nhau. Bundle một vendor runtime là cách trực tiếp để tránh phụ thuộc Java cài trên máy khách. `jlink` tiến xa hơn bằng cách liên kết những Java modules cần thiết thành một runtime image có thể phân phối cùng ứng dụng.

Để sử dụng `jlink` bền vững trong Java Advance Compatibility Migration, cần hiểu JPMS và giới hạn của automatic modules, dùng `jdeps` làm điểm khởi đầu chứ không phải nguồn chân lý duy nhất, kiểm tra reflection/SPI/JDBC/security/locale/agents và thử trực tiếp final runtime image trên OS/architecture đích. Tối ưu dung lượng phải được cân bằng với khả năng chẩn đoán, tính đúng đắn và cập nhật bảo mật. Khi runtime được phát hành cùng ứng dụng, **runtime cũng là một phần của sản phẩm**, cần được version hóa, kiểm thử, vá lỗi, ký/xác minh và rollback với cùng kỷ luật như application artifact.

