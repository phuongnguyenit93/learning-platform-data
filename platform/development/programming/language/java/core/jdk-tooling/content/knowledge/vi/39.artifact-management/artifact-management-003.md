# Runtime image artifact trong Java

**Runtime image artifact** là một gói runtime Java đã được tạo sẵn để chạy ứng dụng mà không cần cài toàn bộ JDK trên máy đích. Thay vì gửi riêng JAR rồi yêu cầu người vận hành tự cài đúng Java, nhóm phát triển có thể tạo một runtime image chỉ chứa các module cần thiết, ứng dụng, launcher và cấu hình đi kèm.

Trong Java Platform Module System, công cụ **jlink** liên kết các module ứng dụng, module JDK và dependency bắc cầu thành một runtime image tùy chỉnh. Công cụ **jpackage** có thể lấy ứng dụng cùng runtime image đó để tạo application image hoặc bộ cài native như MSI, EXE, DEB, RPM, PKG và DMG.

Runtime image là một loại build artifact. Nó phải được tạo từ source và toolchain có version rõ ràng, kiểm thử trên nền tảng mục tiêu, lưu cùng checksum và metadata, sau đó được promote qua các môi trường bằng chính binary đã kiểm thử.

## 1. Runtime image nằm ở đâu trong CI/CD?

~~~text
Source + build configuration + JDK toolchain
                    |
                    v
            Compile and test
                    |
                    v
        Analyze application modules
                    |
                    v
             Build with jlink
                    |
                    v
        Verify runtime and launch app
                    |
                    v
       Package with jpackage if needed
                    |
                    v
      Checksum + SBOM + provenance + sign
                    |
                    v
       Publish immutable runtime artifact
                    |
                    v
      Promote the same artifact to target
~~~

Các đầu ra thường gặp:

| Đầu ra | Nội dung | Cách sử dụng |
|---|---|---|
| JAR | Application classes và resources | Chạy trên một Java runtime có sẵn |
| Custom runtime image | Java runtime đã chọn module và launcher | Phân phối runtime độc lập |
| jpackage application image | Launcher, application payload và runtime | Chạy ứng dụng trên máy đích |
| Native installer | Bộ cài cho hệ điều hành cụ thể | Cài đặt ứng dụng cho người dùng |
| OCI/container image | Filesystem image, runtime, app và cấu hình container | Chạy trong Docker/Kubernetes |

Không đồng nhất custom runtime image với JDK hoặc OCI image. Runtime image thường không có compiler, debugger và nhiều công cụ phát triển của JDK. OCI image là lớp đóng gói container có thể chứa runtime image, ứng dụng, base OS và cấu hình triển khai.

## 2. JDK, JRE và custom runtime image

JDK là bộ công cụ phát triển, thường gồm Java runtime và các công cụ như javac, jlink, jpackage, javadoc và jcmd.

Runtime image được jlink tạo ra chỉ giữ các thành phần runtime cần thiết. Nó có thể chứa:

- Executable java và các native launcher.
- Các module JDK đã chọn.
- Runtime libraries và cấu hình.
- File legal và metadata của runtime.
- Launcher riêng nếu cấu hình bằng jlink.

Runtime image thường không có javac, jshell, javadoc, jcmd, man pages, header files và source archive. Đây là lý do runtime image nhỏ và phù hợp để triển khai.

### Phân biệt bytecode target và runtime version

Hai khái niệm này độc lập:

- javac --release 17 giới hạn API và bytecode mà source được phép sử dụng để tương thích Java 17.
- jlink lấy các module runtime từ JDK đang chạy lệnh jlink.

Vì vậy, nếu biên dịch ứng dụng với --release 17 nhưng chạy jlink từ JDK 26, runtime image được tạo là runtime JDK 26. Muốn đóng gói runtime Java 17, hãy dùng JDK 17 tương ứng để chạy jlink và tạo image. Không thể dùng --release để biến runtime JDK 26 thành runtime JDK 17.

Nên ghi riêng application version, Java release target và JDK vendor/version thực tế đã tạo runtime image.

## 3. Cấu trúc một runtime image

Một runtime image do jlink tạo thường có dạng:

~~~text
runtime-image/
  bin/
    java
    keytool
    runtime-demo
  conf/
  include/
  legal/
  lib/
    modules
    security/
  release
~~~

Các file cụ thể phụ thuộc JDK, module và tùy chọn build. Một số thành phần có thể bị loại bỏ bằng các jlink plugin.

| Thành phần | Vai trò |
|---|---|
| bin/java | Java launcher |
| bin/keytool | Công cụ quản lý key/certificate nếu được giữ |
| conf | Cấu hình runtime |
| legal | License và legal notices của module |
| lib/modules | Module runtime đã được liên kết |
| release | Metadata như Java version, implementor và module set |

Không dựa vào một danh sách file cố định để nhận diện image. Kiểm tra runtime bằng executable java, --list-modules, --version và ứng dụng thực tế.

## 4. Module graph và cách xác định module cần thiết

jlink làm việc với module graph. Module ứng dụng khai báo module dependency bằng module-info.java:

~~~java
module com.acme.runtimeimage {
    requires java.logging;
}
~~~

Trong ví dụ này, ứng dụng cần module java.logging. jlink sẽ giải quyết module gốc và các dependency bắc cầu của chúng.

Nếu module descriptor khai báo requires không chính xác, runtime image có thể thiếu module cần thiết hoặc chứa module thừa. Hãy kiểm tra module graph trước khi tối ưu dung lượng.

### Dùng jdeps để phân tích dependency

Với modular application, jdeps có thể phân tích module và dependency:

~~~bash
jdeps --module-path mods --module com.acme.runtimeimage --list-deps
~~~

Với ứng dụng JAR chạy trên classpath và có thư mục lib chứa dependency:

~~~bash
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" application.jar
~~~

Tùy chọn --print-module-deps in danh sách module dạng phân tách bằng dấu phẩy. Kết quả có thể dùng làm danh sách đầu vào cho --add-modules của jlink.

jdeps phân tích dependency mà nó có thể phát hiện từ bytecode và module metadata. Reflection, tên class được tạo động, ServiceLoader, JNI, native library và resource được nạp theo tên có thể cần kiểm tra bổ sung. Không lấy kết quả jdeps làm bằng chứng duy nhất rằng runtime image đã đầy đủ.

### Kiểm tra module descriptor

Có thể xem module trong JAR:

~~~bash
jar --describe-module --file application.jar
~~~

Xem dependency của module:

~~~bash
jdeps --module-path mods --module com.acme.runtimeimage --check com.acme.runtimeimage
~~~

Nếu ứng dụng dùng thư viện không modular, hãy kiểm tra automatic module name và khả năng tương thích khi đưa thư viện lên module path. Nếu ứng dụng vẫn chạy trên classpath, hãy chọn cách đóng gói và phân tích dependency phù hợp thay vì giả định mọi JAR đều là named module.

## 5. Tạo runtime image bằng jlink

jlink nhận module path, danh sách module gốc và thư mục output:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --output build/runtime-image
~~~

Trong đó:

- --module-path chỉ ra nơi tìm application modules và JDK modules.
- --add-modules xác định module gốc cần đưa vào image.
- --output xác định thư mục runtime image được tạo.
- jlink tự thêm các dependency bắc cầu cần thiết.

Nếu chỉ dùng module JDK chuẩn, module path mặc định của jlink là thư mục jmods thuộc JAVA_HOME. Khi truyền module path tùy chỉnh, cần bảo đảm jlink vẫn tìm thấy các module JDK cần thiết.

### Tối ưu dung lượng

Có thể dùng các plugin:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --output build/runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6
~~~

| Tùy chọn | Tác dụng | Lưu ý |
|---|---|---|
| --strip-debug | Loại debug information | Khó debug trực tiếp từ runtime image |
| --no-header-files | Bỏ C/C++ header files | Phù hợp runtime thông thường |
| --no-man-pages | Bỏ man pages | Giảm file không cần trên máy chạy |
| --compress=zip-6 | Nén resources trong image | Cân bằng dung lượng và chi phí giải nén |
| --include-locales | Chỉ giữ locale data được chọn | Cần module jdk.localedata |
| --bind-services | Liên kết service provider modules | Dùng khi ứng dụng cần service binding |

Trong JDK 26, compression dùng dạng zip-0 đến zip-9; zip-6 là mức mặc định. Các giá trị số cũ như --compress=2 đã deprecated, nên dùng cú pháp zip-6.

Không bật mọi tùy chọn giảm dung lượng một cách máy móc. Nếu ứng dụng cần locale, font, timezone data, crypto provider hoặc native library, phải kiểm tra chúng trong runtime image sau khi tối ưu.

### Tạo launcher riêng

Có thể tạo launcher để người vận hành không cần gõ module và main class:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main --output build/runtime-image
~~~

Launcher runtime-demo gọi main class của module. Launcher được tạo trong thư mục bin của image. Cú pháp module/main là tên module theo sau bởi dấu gạch chéo và tên main class đầy đủ.

## 6. Ví dụ Java 17+: tạo runtime image có thể chạy

Ví dụ sau tạo một modular application nhỏ sử dụng java.logging. Có thể biên dịch bằng JDK 17 trở lên và tạo runtime image bằng jlink của JDK mà bạn muốn phân phối.

Cấu trúc source:

~~~text
runtime-image-demo/
  src/
    com.acme.runtimeimage/
      module-info.java
      com/
        acme/
          runtimeimage/
            Main.java
  mods/
  build/
~~~

Tệp src/com.acme.runtimeimage/module-info.java:

~~~java
module com.acme.runtimeimage {
    requires java.logging;
}
~~~

Tệp src/com.acme.runtimeimage/com/acme/runtimeimage/Main.java:

~~~java
package com.acme.runtimeimage;

import java.util.logging.Logger;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String loggerName = Logger.getLogger(Main.class.getName()).getName();
        System.out.println(
            "RUNTIME_IMAGE_OK module=" + Main.class.getModule().getName()
            + " logger=" + loggerName
        );
    }
}
~~~

### Biên dịch trên Linux hoặc macOS

Từ thư mục project:

~~~bash
mkdir -p mods/com.acme.runtimeimage build
javac --release 17 -d mods/com.acme.runtimeimage src/com.acme.runtimeimage/module-info.java src/com.acme.runtimeimage/com/acme/runtimeimage/Main.java
~~~

### Biên dịch trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force mods\com.acme.runtimeimage, build | Out-Null
javac --release 17 -d mods\com.acme.runtimeimage src\com.acme.runtimeimage\module-info.java src\com.acme.runtimeimage\com\acme\runtimeimage\Main.java
~~~

### Tạo runtime image trên Linux hoặc macOS

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.runtimeimage --output build/runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6 --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

### Tạo runtime image trên Windows PowerShell

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.runtimeimage --output build\runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6 --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Chạy bằng runtime image vừa tạo.

Linux/macOS:

~~~bash
build/runtime-image/bin/java -m com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Windows PowerShell:

~~~powershell
.\build\runtime-image\bin\java.exe -m com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Stdout chính xác:

~~~text
RUNTIME_IMAGE_OK module=com.acme.runtimeimage logger=com.acme.runtimeimage.Main
~~~

Kiểm tra launcher riêng nếu cần:

~~~bash
build/runtime-image/bin/runtime-demo
~~~

Trên Windows, tên file launcher phụ thuộc định dạng launcher mà JDK tạo; có thể kiểm tra nội dung thư mục bin trước khi gọi. Dùng bin/java.exe -m ... là cách kiểm tra module launcher nhất quán giữa các nền tảng.

## 7. Kiểm tra runtime image sau khi tạo

Không coi việc lệnh jlink exit code 0 là bằng chứng duy nhất. Hãy kiểm tra image bằng nhiều lớp.

### Kiểm tra Java version

Linux/macOS:

~~~bash
build/runtime-image/bin/java --version
~~~

Windows:

~~~powershell
.\build\runtime-image\bin\java.exe --version
~~~

Phiên bản hiển thị phải khớp JDK dùng để tạo runtime image và policy của release.

### Kiểm tra module list

~~~bash
build/runtime-image/bin/java --list-modules
~~~

Đối chiếu module thực tế với module manifest hoặc module set dự kiến. Đặc biệt kiểm tra module bắt buộc như java.logging, java.sql, java.xml, java.desktop, jdk.crypto.ec và jdk.localedata khi ứng dụng cần.

### Kiểm tra module resolution

~~~bash
build/runtime-image/bin/java --validate-modules
~~~

Lệnh này giúp phát hiện xung đột hoặc vấn đề module resolution. Nó không thay thế integration test.

### Kiểm tra image content

Có thể xem nội dung module image bằng:

~~~bash
jimage list build/runtime-image/lib/modules
~~~

Có thể xem metadata tại file release trong root runtime image. File này giúp truy vết implementor, Java version và module set.

### Smoke test và integration test

Chạy application bằng java nằm trong runtime image, không dùng java của máy build. Kiểm tra:

- Main class khởi chạy và thoát với exit code đúng.
- Resource được load từ runtime image.
- TLS/HTTPS và certificate provider hoạt động.
- Locale, timezone và encoding phù hợp.
- ServiceLoader tìm được provider.
- JNI hoặc native library load được trên máy đích.
- File system path, permissions và working directory phù hợp.
- Kết nối database, network và các external service cần thiết.

Một runtime image có thể khởi động thành công nhưng vẫn thiếu module hoặc resource chỉ được sử dụng ở một nhánh code hiếm gặp. Hãy dùng integration test có coverage cho những nhánh đó.

## 8. ServiceLoader và service binding

Một số thư viện tìm implementation qua Java ServiceLoader. Service provider có thể nằm trong module khác với module ứng dụng.

jlink có tùy chọn:

~~~bash
--bind-services
~~~

Tùy chọn này liên kết service provider modules và dependency của chúng vào runtime image. Có thể kiểm tra module/provider cần thiết trước khi quyết định bật.

Một thay đổi quan trọng: từ JDK 25, jpackage không tự đưa service bindings vào runtime image mà nó tạo. Nếu ứng dụng cần service provider được phát hiện qua binding, hãy truyền --bind-services trong --jlink-options.

Ví dụ:

~~~bash
jpackage --name RuntimeImageDemo --input app-input --main-jar app.jar --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
~~~

Khi chỉ định --jlink-options, hãy liệt kê lại các tùy chọn mặc định mà bạn vẫn muốn giữ. Không giả định runtime image tạo bởi jpackage JDK 25+ có cùng module set với image từ JDK 24 hoặc cũ hơn.

## 9. Locale, native library và tài nguyên runtime

### Locale data

Nếu ứng dụng cần locale ngoài tập mặc định của runtime, có thể thêm jdk.localedata và chọn locale:

~~~bash
jlink --add-modules com.acme.runtimeimage,jdk.localedata --include-locales=en,vi --output build/runtime-image
~~~

Tên locale sử dụng BCP 47 language tag. Chỉ giữ locale ứng dụng thật sự cần để tránh thêm dữ liệu không cần thiết.

### Crypto provider và TLS

Ứng dụng HTTPS hoặc TLS có thể cần provider như SunEC hoặc module liên quan tới security. Không xóa module chỉ vì jdeps không phát hiện đường gọi trực tiếp. Hãy kiểm tra handshake với server và certificate chain trong runtime image.

### JNI và native library

jlink chỉ giải quyết module Java. JNI library và native dependency phải được phân phối riêng hoặc đưa vào application image phù hợp. Chúng thường phụ thuộc OS, CPU architecture, libc hoặc ABI.

Kiểm tra:

- Tên file native library và đường dẫn load.
- OS và architecture đích.
- Dynamic library dependency.
- Quyền thực thi và quyền đọc file.
- Cách cấu hình java.library.path nếu ứng dụng yêu cầu.

## 10. jpackage: đóng gói application image cùng runtime

jpackage tạo application image hoặc native installer. Nếu không cung cấp runtime image, jpackage gọi jlink để tự tạo runtime. Nếu đã có runtime image được kiểm thử, có thể truyền nó bằng --runtime-image.

Ví dụ với modular application:

~~~bash
jpackage --type app-image --name RuntimeImageDemo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build/runtime-image --dest build/packages
~~~

Application image thường chứa:

- Launcher của ứng dụng.
- Application JAR hoặc module payload.
- File cấu hình launcher.
- Runtime image bên trong thư mục package.
- Tài nguyên như icon và file metadata nếu được khai báo.

Application image có thể chạy mà không cần cài Java riêng, miễn runtime image và native dependencies phù hợp máy đích.

### Tạo native installer

Các định dạng phổ biến:

| Nền tảng | Định dạng |
|---|---|
| Windows | exe, msi |
| Linux | deb, rpm |
| macOS | pkg, dmg |

Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name RuntimeImageDemo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build\runtime-image --dest build\installers
~~~

Ví dụ trên Linux:

~~~bash
jpackage --type deb --name runtime-image-demo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build/runtime-image --dest build/installers
~~~

jpackage tạo package native theo nền tảng host. Không hỗ trợ cross-platform packaging; cần build agent tương ứng cho Windows, Linux và macOS. Windows và macOS có thể yêu cầu công cụ bổ sung để tạo installer hoặc ký package.

### Khi nào dùng app-image và khi nào dùng installer?

- app-image phù hợp để kiểm thử hoặc phân phối một thư mục chạy được.
- Installer phù hợp khi cần cài đặt, shortcut, menu, file association hoặc tích hợp với hệ điều hành.
- Runtime image thuần phù hợp khi ứng dụng được triển khai bởi script, service manager hoặc container mà không cần installer native.

## 11. Runtime image artifact và container image

Runtime image và container image là hai artifact khác nhau.

| Đặc điểm | Runtime image | Container image |
|---|---|---|
| Nội dung chính | Java runtime đã chọn module | Root filesystem và app/runtime |
| Có OS userland | Không phải một OS image hoàn chỉnh | Có base image và userland |
| Có thể chạy trực tiếp | Trên OS/architecture tương thích | Qua container runtime |
| Quản lý version | JDK vendor/version, module set, app version | Image tag và immutable digest |
| Lưu trữ | Artifact repository hoặc archive store | Container registry |

Một pipeline có thể build runtime image trước, kiểm thử, sau đó đưa runtime image và application vào OCI image. Khi promote container, dùng đúng digest của OCI image đã kiểm thử.

Không tạo runtime image cho một OS rồi mong chạy nguyên trạng trên OS khác. Runtime image chứa native binaries và thư viện theo nền tảng tạo image.

## 12. Versioning và metadata của runtime image

Một runtime image cần được nhận diện bằng nhiều thông tin hơn application version.

Metadata nên có:

- Application name và version.
- Git commit SHA hoặc source revision.
- JDK vendor, full version và build number.
- OS và CPU architecture.
- Java release target của application.
- Module list thực tế.
- jlink/jpackage options.
- Native library inventory.
- Build pipeline ID và build timestamp.
- SHA-256 digest.
- SBOM và provenance reference.

Ví dụ tên archive:

~~~text
runtime-image-demo-1.2.0-jdk26-linux-x64.tar.gz
runtime-image-demo-1.2.0-jdk26-windows-x64.zip
runtime-image-demo-1.2.0-jdk26-macos-aarch64.tar.gz
~~~

Tên file giúp nhận diện nhanh; metadata và checksum mới là căn cứ kiểm tra chính xác. Không tái sử dụng cùng release version cho hai image có module set, JDK patch hoặc binary khác nhau.

File release trong runtime image có thể được lưu kèm build manifest để đối chiếu với version dự kiến.

## 13. Reproducible build và tính bất biến

Hai runtime image được tạo từ cùng source chưa chắc có cùng byte hash nếu JDK patch, vendor, build options hoặc môi trường khác nhau.

Để tăng khả năng tái lập:

1. Pin JDK distribution và exact version.
2. Pin application dependency và module set.
3. Lưu đầy đủ lệnh jlink/jpackage hoặc options file.
4. Chuẩn hóa build environment và OS image.
5. Không nhúng timestamp động vào application resources nếu không cần.
6. Ghi lại native dependency và build tool version.
7. Build lại độc lập và so sánh archive checksum.
8. Khi release đã publish, không ghi đè artifact cùng version.

Tính tái lập phải được đo bằng việc build lại và so sánh output. Không giả định jlink image luôn có hash giống nhau giữa mọi vendor hoặc JDK patch.

## 14. Kiểm tra checksum, SBOM và chữ ký

Nếu runtime image được lưu dưới dạng thư mục, hãy archive nó trước khi tính checksum. Tính checksum sau khi hoàn tất mọi thay đổi đối với archive.

Linux:

~~~bash
tar -czf runtime-image-demo.tar.gz runtime-image
sha256sum runtime-image-demo.tar.gz
~~~

Windows PowerShell:

~~~powershell
Compress-Archive -Path runtime-image -DestinationPath runtime-image-demo.zip
Get-FileHash runtime-image-demo.zip -Algorithm SHA256
~~~

Checksum giúp phát hiện file bị thay đổi trong quá trình lưu trữ hoặc truyền tải. Để xác thực nguồn phát hành, kết hợp chữ ký số hoặc provenance đáng tin cậy.

SBOM nên mô tả application dependencies, runtime modules và native libraries có trong artifact. Scan các thành phần runtime để phát hiện CVE và license issue. Không chỉ scan JAR rồi kết luận runtime image an toàn; runtime image còn mang theo các module và native components của JDK.

Lưu checksum, signature, SBOM và provenance cạnh artifact hoặc trong release metadata. Không đưa private key, keystore password hay token vào runtime image.

## 15. Publish và promote runtime image trong CI/CD

Có thể lưu runtime image trong generic artifact repository, release storage hoặc object storage có versioning và immutable policy. Nếu runtime image được đưa vào OCI image, publish OCI artifact lên container registry.

Quy trình đề xuất:

1. Checkout source tại commit đã xác định.
2. Cài đúng JDK vendor/version cho target OS và architecture.
3. Compile và chạy test.
4. Dùng jdeps để phân tích dependency, rà soát module set.
5. Tạo runtime image bằng jlink.
6. Kiểm tra module list, runtime version và application startup.
7. Chạy integration test trên target platform.
8. Tạo jpackage application image hoặc installer nếu cần.
9. Scan runtime modules, dependency và native library.
10. Tạo SBOM, checksum, signature và provenance.
11. Publish artifact với version bất biến.
12. Deploy staging bằng artifact đã publish.
13. Sau khi staging đạt, promote đúng digest sang production.
14. Lưu kết quả kiểm thử và metadata gắn với digest.

Với nhiều nền tảng, dùng build matrix theo OS và architecture. Mỗi platform artifact có digest riêng. Không rebuild lại runtime image khi promote cùng một platform artifact từ staging sang production.

## 16. Bảo trì runtime image và cập nhật bảo mật

Runtime image tự tạo không tự cập nhật khi JDK có security patch mới. Nhóm phát triển chịu trách nhiệm cập nhật và phát hành image mới.

Khi nâng JDK:

- Đọc release notes và security advisories của vendor.
- Cập nhật JDK toolchain và base build environment.
- Chạy lại jdeps và tạo lại runtime image.
- So sánh module list và kích thước image.
- Chạy test tương thích, TLS, locale, JNI và ServiceLoader.
- Scan CVE và kiểm tra license.
- Tạo checksum/SBOM/provenance mới.
- Phát hành version runtime image mới và promote theo pipeline.

Không vá trực tiếp runtime image đã phát hành. Hãy tạo artifact mới từ build process có thể truy vết.

## 17. Troubleshooting runtime image

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jlink báo module not found | Module path thiếu module ứng dụng hoặc JDK | Kiểm tra --module-path và JDK/JMOD tương ứng |
| jlink báo java.base không resolve | Module path không chứa JDK modules cần thiết | Thêm đúng thư mục JDK jmods |
| Application báo ClassNotFoundException | Thiếu dependency hoặc module | Chạy jdeps, kiểm tra classpath/module path |
| NoClassDefFoundError chỉ xuất hiện trên production | Nhánh code runtime cần module/resource chưa được test | Bổ sung integration test trên runtime image |
| ServiceLoader không tìm thấy provider | Service binding bị thiếu | Kiểm tra provider và dùng --bind-services khi cần |
| TLS handshake thất bại | Thiếu crypto provider hoặc native support | Kiểm tra module security và thử handshake trên image |
| Locale hiển thị sai | Thiếu jdk.localedata hoặc locale đã bị loại | Thêm module và --include-locales phù hợp |
| JNI UnsatisfiedLinkError | Native library thiếu hoặc sai architecture | Kiểm tra native dependency, path và OS/CPU |
| Runtime image lớn hơn dự kiến | Module, locale hoặc resource thừa | Xem --list-modules và jimage list |
| App image chạy nhưng installer lỗi | Package native cần tool hoặc option nền tảng | Build trên OS đích và kiểm tra prerequisite |
| Image không chạy trên máy khác | OS, architecture, ABI hoặc JDK runtime khác | Build artifact riêng cho từng target |
| jpackage image thiếu provider sau nâng JDK | JDK 25+ không include service bindings mặc định | Truyền --bind-services qua --jlink-options |
| Runtime thiếu security patch | Custom image không tự cập nhật | Rebuild từ JDK patch mới và phát hành artifact mới |
| Checksum thay đổi giữa hai lần build | Toolchain hoặc build environment khác | Pin JDK, options, platform và so sánh provenance |

## 18. Checklist release runtime image

Trước khi publish, xác nhận:

- [ ] Đã pin JDK vendor, full version và target OS/architecture.
- [ ] Đã phân biệt Java compile release với JDK runtime version.
- [ ] Module set được xác định và review.
- [ ] Dependency động, ServiceLoader và JNI đã được kiểm tra.
- [ ] jlink tạo image thành công.
- [ ] java --version và java --list-modules khớp kỳ vọng.
- [ ] java --validate-modules không báo lỗi.
- [ ] Application chạy bằng java bên trong runtime image.
- [ ] Integration test chạy trên môi trường gần production.
- [ ] Locale, TLS, native libraries và resource đã được kiểm tra.
- [ ] jpackage app-image hoặc installer được test nếu có.
- [ ] SBOM, checksum, signature và provenance đã lưu.
- [ ] Artifact có version và digest bất biến.
- [ ] Staging và production dùng cùng artifact digest.
- [ ] Có kế hoạch rebuild khi JDK nhận security update.

## 19. Ghi nhớ

- Runtime image là Java runtime đã chọn module và dependency cần thiết để chạy ứng dụng.
- jlink tạo custom runtime image từ module graph và các module JDK.
- jpackage tạo application image hoặc installer và có thể dùng runtime image được cung cấp.
- Runtime image không phải JDK đầy đủ và không có các công cụ phát triển như javac.
- javac --release 17 không ép jlink tạo runtime Java 17; runtime version phụ thuộc JDK chạy jlink.
- jdeps giúp phân tích dependency nhưng có thể không phát hiện reflection, ServiceLoader, JNI và dynamic loading.
- jlink có các tùy chọn strip-debug, no-header-files, no-man-pages, compress, include-locales và bind-services.
- Từ JDK 25, jpackage không tự include service bindings; cần --bind-services khi ứng dụng cần chúng.
- Runtime image gắn với OS và architecture; build matrix phải tạo image cho từng target.
- Kiểm thử bằng chính runtime image và ứng dụng bên trong image.
- Lưu module list, JDK version, checksum, SBOM và provenance.
- Runtime image không tự nhận security update; phải rebuild và phát hành artifact mới.
- Build một lần cho mỗi target, kiểm thử và promote cùng digest qua các môi trường.

## Tài liệu tham khảo chính thức

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Packaging Tool User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/index.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)