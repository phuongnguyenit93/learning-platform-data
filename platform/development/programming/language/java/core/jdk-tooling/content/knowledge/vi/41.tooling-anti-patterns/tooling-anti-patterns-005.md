# Tránh tạo runtime image Java quá lớn

Runtime image quá lớn là anti-pattern trong đóng gói Java: ứng dụng chỉ cần một tập nhỏ module để chạy nhưng artifact lại mang theo nhiều module JDK, locale, resource, công cụ hoặc file ứng dụng không cần thiết. Hậu quả là package tải lâu, chiếm dung lượng lưu trữ, tăng thời gian triển khai, mở rộng bề mặt cập nhật bảo mật và làm chậm quá trình phân phối.

Kích thước lớn không tự động có nghĩa là build sai. Ứng dụng desktop có giao diện, nhiều locale, font, JavaFX, database driver hoặc native library có thể cần nhiều thành phần. Mục tiêu là loại bỏ phần không cần cho hành vi đã cam kết, giữ lại những module và tài nguyên cần thiết, rồi đo lại trên cùng một nền tảng.

Công cụ chính là **jdeps** để phân tích dependency, **jlink** để liên kết custom runtime image và **jpackage** để đóng gói application image hoặc installer. Quy trình tối ưu phải dựa trên số đo và regression test, không dựa trên việc xóa module theo cảm tính.

## 1. Vì sao runtime image quá lớn là vấn đề?

Một runtime image lớn có thể gây ra:

- Tăng dung lượng tải xuống, lưu trữ và cache.
- Tăng thời gian build, upload, download và deploy.
- Tăng kích thước container image và thời gian pull image.
- Tăng số module cần theo dõi khi JDK có security update.
- Làm khó việc so sánh artifact giữa các release.
- Khi đóng gói nhiều ứng dụng, nhân bản runtime lớn ở mỗi package.

Nếu triển khai hàng trăm instance, chênh lệch vài chục MB trên mỗi image có thể tạo ra mức sử dụng storage và network đáng kể.

Tuy nhiên, không nên tối ưu chỉ theo một con số. Hãy xem đồng thời:

| Chỉ số | Ý nghĩa |
|---|---|
| Runtime directory size | Dung lượng thư mục runtime sau khi tạo |
| Application payload size | JAR, dependency, resource và native library của ứng dụng |
| Application image size | Tổng launcher, payload và runtime do jpackage tạo |
| Installer size | Kích thước file MSI/EXE/DEB/RPM/PKG/DMG |
| Installed footprint | Dung lượng sau khi cài đặt |
| Startup time | Thời gian từ lúc launch tới khi ứng dụng sẵn sàng |
| Memory usage | RSS, heap và native memory khi chạy |
| Functional coverage | Các tính năng còn hoạt động sau khi loại module/resource |

Installer được nén có thể nhỏ hơn application image đã giải nén. Hãy so sánh cùng một loại chỉ số, cùng OS/architecture và cùng phiên bản JDK.

## 2. Những nguyên nhân phổ biến

### Chọn quá nhiều module JDK

Một ứng dụng command-line nhỏ có thể chỉ cần java.base và java.logging, nhưng runtime image lại chứa java.desktop, java.sql, java.xml, java.naming, java.management, jdk.jfr, jdk.compiler và nhiều module khác.

Các module gốc được truyền cho jlink sẽ kéo theo dependency bắc cầu. Một module lớn có thể làm tăng cả tập module phụ thuộc.

### Bật service binding khi không cần

Tùy chọn --bind-services liên kết service provider modules cùng dependency của chúng. Điều này hữu ích khi ứng dụng cần tìm provider qua service binding, nhưng có thể mở rộng module graph đáng kể.

Không bật --bind-services mặc định chỉ vì muốn “đầy đủ”. Hãy xác định service interface, provider và hành vi ServiceLoader thực tế.

### Giữ toàn bộ locale data

Module jdk.localedata chứa dữ liệu locale bổ sung. Nếu thêm module này nhưng không giới hạn locale, image có thể mang theo nhiều dữ liệu hơn ứng dụng cần.

Ứng dụng chỉ hỗ trợ tiếng Anh và tiếng Việt có thể cân nhắc chỉ giữ en và vi, sau khi kiểm thử định dạng ngày, số, tiền tệ, collation và thông báo theo locale.

### Giữ debug information và tài liệu không cần thiết

Runtime image dùng cho production thường không cần debug information, C/C++ header files hoặc man pages. Chúng có thể được loại bằng jlink plugin tương ứng.

Lưu ý: --strip-debug tác động lên nội dung runtime image được jlink tạo. Nó không tự động xóa debug information khỏi application JAR mà jpackage đưa vào payload. Nếu muốn giảm application JAR, cần xem lại cách biên dịch và đóng gói riêng.

### Đưa cả thư mục build vào jpackage

Tùy chọn --input của jpackage đóng gói tất cả file trong thư mục input. Nếu trỏ vào cả thư mục project hoặc build output, artifact có thể mang theo test classes, test report, Sources/Javadoc JAR, file debug, dependency không thuộc runtime, log, cache, file tạm và bản build cũ.

Đây là nguyên nhân thường bị bỏ qua vì runtime image có thể đã nhỏ nhưng application image vẫn rất lớn.

### Đóng gói trùng runtime

Một container có thể dùng base image chứa JDK đầy đủ, sau đó lại copy custom runtime image vào container. Khi đó cùng một số thành phần Java xuất hiện hai lần trong các layer khác nhau.

Cần phân tích layer của container và quyết định rõ container sẽ dùng runtime nào.

## 3. Đo kích thước trước khi tối ưu

Trước khi thay đổi, lưu lại kích thước baseline và thông tin build. Không so sánh image được tạo từ JDK khác, OS khác hoặc module set khác.

### Linux và macOS

~~~bash
du -sh build/runtime
du -h -d 2 build/runtime | sort -h
du -sh app-input
du -h app-input/* | sort -h
du -sh build/packages/MyApp
~~~

### Windows PowerShell

~~~powershell
$path = 'build/runtime'
$bytes = (Get-ChildItem -LiteralPath $path -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
'{0}: {1:N2} MiB' -f $path, ($bytes / 1MB)
~~~

So sánh hai runtime image:

~~~powershell
$paths = 'build/runtime-small', 'build/runtime-wide'
foreach ($path in $paths) {
    $bytes = (Get-ChildItem -LiteralPath $path -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
    '{0}: {1:N2} MiB' -f $path, ($bytes / 1MB)
}
~~~

PowerShell tính tổng byte của file. Kết quả không nhất thiết bằng dung lượng đã cấp phát trên filesystem vì block size và sparse file có thể khác nhau.

### Ghi lại cấu hình baseline

Lưu JDK vendor/full version/build number, OS và CPU architecture, danh sách module, jlink/jpackage options, application JAR và dependency list, kích thước runtime/payload/app image/installer, thời gian build/startup và kết quả test. Giữ baseline để biết thay đổi nào thực sự làm giảm dung lượng và có tác động gì.

## 4. Xác định module thực sự cần bằng jdeps

jdeps phân tích dependency ở cấp package, class và module. Với modular application, có thể lấy module dependency để dùng làm đầu vào cho jlink.

~~~bash
jdeps --module-path "mods:$JAVA_HOME/jmods" --module com.acme.imageapp --print-module-deps
~~~

Lệnh này in danh sách module dependency dạng phân tách bằng dấu phẩy. jdeps có thể phân tích dependency bắc cầu của class và module mà nó nhận diện được.

Với ứng dụng JAR chạy trên classpath:

~~~bash
jdeps --multi-release 17 --class-path "lib/*" --print-module-deps application.jar
~~~

Trong ví dụ này, lib chứa các dependency runtime. Nếu không truyền đúng classpath, jdeps có thể báo missing dependencies hoặc bỏ sót dependency của ứng dụng.

### Đọc kết quả cẩn thận

Kết quả jdeps là điểm khởi đầu, không phải danh sách đầy đủ mọi module mà ứng dụng có thể cần. Phân tích tĩnh có thể không phát hiện reflection nạp class bằng tên chuỗi, ServiceLoader và provider được tìm lúc runtime, JNI và native library, class hoặc resource được tạo/nạp động, plugin được cài thêm sau khi build hoặc nhánh code hiếm chỉ chạy trong một loại request/locale.

Sau khi lấy danh sách module, kiểm tra module descriptor, cấu hình, test và các plugin thực tế. Nếu ứng dụng cần module động, thêm rõ ràng vào danh sách module root và ghi lại lý do.

### Kiểm tra dependency ở mức chi tiết

~~~bash
jdeps --verbose:module --module-path "mods:$JAVA_HOME/jmods" --module com.acme.imageapp
~~~

Để tìm dependency bị thiếu:

~~~bash
jdeps --missing-deps --module-path "mods:$JAVA_HOME/jmods" --module com.acme.imageapp
~~~

Nếu input là exploded module directory, dùng tên module hoặc module path phù hợp với lệnh jdeps; không truyền module-info.class như thể nó là một JAR hoàn chỉnh.

## 5. Chọn module root hẹp bằng jlink

jlink liên kết module root cùng dependency bắc cầu của chúng. Cách tối ưu thường là bắt đầu từ module ứng dụng và thêm module JDK bổ sung khi có bằng chứng cần thiết.

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.imageapp --output build/runtime-small
~~~

Nếu module com.acme.imageapp khai báo requires java.logging, jlink sẽ đưa java.logging cùng dependency cần thiết vào image.

Tránh thêm một danh sách module lớn chỉ để phòng ngừa. Nếu một tính năng thực sự cần java.sql hoặc java.desktop, thêm module tương ứng và kiểm thử tính năng đó.

### Khi nào cần --limit-modules?

--limit-modules giới hạn tập module có thể quan sát trong quá trình resolution. Nó hữu ích để kiểm soát module universe khi module path rộng, nhưng không phải công cụ xóa module một cách mù quáng.

Nếu module ứng dụng hoặc service provider cần module nằm ngoài giới hạn, quá trình resolution sẽ thất bại hoặc ứng dụng không hoạt động như mong đợi. Chỉ dùng sau khi đã hiểu dependency graph.

### Không mở rộng module graph vô cớ

| Lựa chọn | Rủi ro |
|---|---|
| Thêm java.desktop cho ứng dụng server không dùng GUI | Kéo thêm AWT, font, imaging và các dependency liên quan |
| Thêm jdk.localedata nhưng không giới hạn locale | Giữ nhiều locale data hơn nhu cầu |
| Thêm jdk.compiler | Mang theo compiler dù chỉ chạy bytecode đã biên dịch |
| Thêm jdk.jfr cho mọi ứng dụng | Tăng image dù không dùng Flight Recorder trong runtime |
| Bật --bind-services không kiểm tra | Liên kết provider và dependency không cần thiết |
| Thêm toàn bộ module path | Làm mất lợi ích của custom runtime |

Danh sách trên là ví dụ về module cần xem xét, không phải quy tắc cấm. Ứng dụng có thể thực sự cần chúng.

## 6. Loại bỏ resource không cần và chọn mức compression

Sau khi chọn đúng module, mới tối ưu nội dung runtime image.

### Loại debug information

~~~bash
--strip-debug
~~~

Tùy chọn này loại debug information khỏi runtime image. Giữ lại debug symbol hoặc thông tin cần cho quy trình điều tra nếu production support yêu cầu. Đừng đánh đổi khả năng chẩn đoán mà không đánh giá chi phí.

### Bỏ header và man pages

~~~bash
--no-header-files
--no-man-pages
~~~

Các file này thường hữu ích cho phát triển hoặc native compilation hơn là runtime thông thường. Loại chúng khỏi runtime image production nếu ứng dụng không cần.

### Chọn compression

JDK 26 hỗ trợ:

~~~bash
--compress=zip-0
--compress=zip-6
--compress=zip-9
~~~

zip-0 không nén; zip-6 là mặc định; zip-9 nén mạnh hơn. Mức nén cao có thể giảm kích thước nhưng làm tăng chi phí CPU khi truy cập resource. Đo cả dung lượng lẫn startup/runtime performance trên máy mục tiêu.

Không dùng giá trị cũ --compress=2 cho build mới. JDK 26 đánh dấu các giá trị số cũ là deprecated; dùng cú pháp zip-{0-9}.

### Giới hạn locale

Nếu ứng dụng chỉ cần một tập locale cụ thể:

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.imageapp,jdk.localedata --include-locales=en,vi --output build/runtime-locales
~~~

--include-locales cần module jdk.localedata. Các tag là BCP 47 language tags; hãy chọn theo yêu cầu sản phẩm và kiểm thử locale thực tế. Không loại locale chỉ dựa vào ngôn ngữ giao diện vì thư viện có thể dùng locale cho sorting, parsing hoặc formatting.

### Kiểm tra plugin được hỗ trợ

~~~bash
jlink --list-plugins
~~~

Chỉ dùng plugin được JDK đang chạy hỗ trợ. Danh sách plugin và option có thể thay đổi giữa các phiên bản JDK.

## 7. Tạo hai image để thấy tác động của module selection

Ví dụ modular app có module descriptor:

~~~java
module com.acme.imageapp {
    requires java.logging;
}
~~~

Tệp Main.java:

~~~java
package com.acme.imageapp;

import java.util.logging.Logger;

public final class Main {
    private static final Logger LOG = Logger.getLogger(Main.class.getName());

    private Main() {
    }

    public static void main(String[] args) {
        LOG.fine("runtime image check");
        System.out.println("RUNTIME_IMAGE_OK module=" + Main.class.getModule().getName());
    }
}
~~~

Cấu trúc source:

~~~text
runtime-image-demo/
  src/
    com.acme.imageapp/
      module-info.java
      com/acme/imageapp/Main.java
  mods/
  build/
~~~

### Biên dịch trên Linux/macOS

~~~bash
mkdir -p mods/com.acme.imageapp build
javac -d mods/com.acme.imageapp src/com.acme.imageapp/module-info.java src/com.acme.imageapp/com/acme/imageapp/Main.java
~~~

### Biên dịch trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force mods\com.acme.imageapp, build | Out-Null
javac -d mods\com.acme.imageapp src\com.acme.imageapp\module-info.java src\com.acme.imageapp\com\acme\imageapp\Main.java
~~~

### Tạo runtime nhỏ trên Linux/macOS

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.imageapp --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build/runtime-small
~~~

### Tạo runtime lớn có chủ ý để so sánh

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.imageapp,java.desktop,java.sql,java.xml,java.naming,java.management,jdk.jfr,jdk.localedata --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build/runtime-wide
~~~

runtime-wide chứa thêm module để minh họa chi phí của module root rộng. Đây là ví dụ so sánh, không phải cấu hình production.

### Tạo runtime nhỏ trên Windows PowerShell

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.imageapp --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build\runtime-small
~~~

### Tạo runtime rộng trên Windows PowerShell

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.imageapp,java.desktop,java.sql,java.xml,java.naming,java.management,jdk.jfr,jdk.localedata --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build\runtime-wide
~~~

Chạy ứng dụng bằng runtime nhỏ.

Linux/macOS:

~~~bash
build/runtime-small/bin/java -m com.acme.imageapp/com.acme.imageapp.Main
~~~

Windows PowerShell:

~~~powershell
.\build\runtime-small\bin\java.exe -m com.acme.imageapp/com.acme.imageapp.Main
~~~

Stdout chính xác:

~~~text
RUNTIME_IMAGE_OK module=com.acme.imageapp
~~~

Cả hai runtime đều phải chạy được chương trình. Sau đó đo kích thước và so sánh module list để xem phần tăng đến từ đâu.

## 8. Đo và đối chiếu hai runtime image

Linux/macOS:

~~~bash
du -sh build/runtime-small build/runtime-wide
build/runtime-small/bin/java --list-modules
build/runtime-wide/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
$paths = 'build/runtime-small', 'build/runtime-wide'
foreach ($path in $paths) {
    $bytes = (Get-ChildItem -LiteralPath $path -Recurse -Force -File | Measure-Object -Property Length -Sum).Sum
    '{0}: {1:N2} MiB' -f $path, ($bytes / 1MB)
}
.\build\runtime-small\bin\java.exe --list-modules
.\build\runtime-wide\bin\java.exe --list-modules
~~~

Lưu kết quả vào build report cùng với JDK version và lệnh jlink. Nếu runtime nhỏ không chạy được một tính năng cần thiết, bổ sung module hoặc resource có căn cứ rồi chạy lại test.

Có thể xem nội dung module image:

~~~bash
jimage list build/runtime-small/lib/modules
~~~

jimage list giúp xem module/resource được đóng gói trong file modules. Nó không tự tạo báo cáo dung lượng chính xác theo từng module. Để tìm module làm tăng kích thước, tạo image đối chứng khi thêm/bớt từng nhóm module và so sánh tổng dung lượng.

## 9. Giảm kích thước application payload của jpackage

jpackage tạo application image từ runtime và file ứng dụng. Với --input, **mọi file trong thư mục input đều được đóng gói**. Vì vậy hãy tạo một staging directory chỉ chứa file cần phân phối.

Ví dụ:

~~~text
app-input/
  imageapp.jar
  lib/
    required-driver.jar
    required-client.jar
  conf/
    application-defaults.properties
  legal/
    THIRD-PARTY-NOTICES.txt
~~~

Không trỏ --input tới toàn bộ project, thư mục target, build hoặc thư mục cache. Kiểm tra từng JAR trong lib bằng dependency tree và runtime test trước khi loại bỏ.

Giữ lại license, legal notice, cấu hình mẫu và resource mà sản phẩm cần. Không xóa file chỉ vì tên của nó không quen thuộc.

### Kiểm tra application input

Linux/macOS:

~~~bash
du -sh app-input
du -h app-input/* | sort -h
find app-input -type f
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem -LiteralPath app-input -Recurse -Force -File |
    Select-Object FullName, Length |
    Sort-Object Length -Descending
~~~

Tìm các bản JAR trùng version, test artifact, source archive, Javadoc và file tạm. Nếu dependency được đóng gói riêng trong lib, xác nhận launcher classpath chỉ trỏ tới các dependency thực sự cần.

## 10. jpackage và runtime module set

jpackage có thể tự gọi jlink nếu không cung cấp runtime image. Cách chọn module phụ thuộc kiểu ứng dụng:

- Modular application: runtime image gồm main module và dependency bắc cầu.
- Non-modular application chạy từ main JAR: jpackage dùng default set module cho classpath application, trừ khi chỉ định --add-modules.
- Có thể truyền --runtime-image để tái sử dụng custom runtime đã tạo và kiểm thử bằng jlink.

Với non-modular JAR, dùng jdeps để phân tích module dependency, sau đó chỉ định module list phù hợp bằng --add-modules. Kiểm tra reflection, service provider và native library trước khi thu hẹp.

Ví dụ tạo application image từ modular app và custom runtime:

~~~bash
jpackage --type app-image --name ImageApp --module-path mods --module com.acme.imageapp/com.acme.imageapp.Main --runtime-image build/runtime-small --dest build/packages
~~~

Application image có launcher, app payload và runtime. Đo riêng runtime image, application payload và tổng app image để biết phần nào chiếm dung lượng.

### Service binding trong JDK 25+

Từ JDK 25, runtime image do jpackage tạo không còn tự bao gồm service bindings. Nếu ứng dụng thực sự cần provider modules được tìm qua service binding, truyền --bind-services bằng --jlink-options.

Ví dụ giữ các jlink option mặc định thường dùng và bật service binding:

~~~bash
jpackage --name ImageApp --input app-input --main-jar imageapp.jar --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
~~~

Khi chỉ định --jlink-options, hãy ghi rõ các option cần giữ vì danh sách option mặc định không tự động được ghép vào giá trị tùy chỉnh. Bật --bind-services có thể tăng module set và kích thước; chỉ dùng khi đã kiểm tra ServiceLoader/provider behavior.

## 11. Tối ưu runtime image trong container

Nếu runtime image được copy vào OCI image, kiểm tra toàn bộ container layer. Một image nhỏ bên trong không đảm bảo container cuối cùng nhỏ nếu base image hoặc build artifact còn dư.

Dùng multi-stage build:

~~~dockerfile
FROM eclipse-temurin:26-jdk AS build
WORKDIR /src
COPY . .
RUN ./gradlew --no-daemon clean build
RUN jlink --module-path "$JAVA_HOME/jmods:build/modules" --add-modules com.acme.imageapp --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output /out/runtime

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=build /out/runtime /opt/java
COPY --from=build /src/app-input /app
ENV PATH="/opt/java/bin:$PATH"
ENTRYPOINT ["java", "-m", "com.acme.imageapp/com.acme.imageapp.Main"]
~~~

Đây là cấu trúc minh họa; đường dẫn module build và tên module phải khớp project thật. Base image phải có native libraries, libc, CA certificates và timezone data mà ứng dụng cần.

Dùng .dockerignore để không gửi .git, IDE files, local build cache, test reports và output cũ vào build context. Không copy cả JDK từ stage build sang final stage nếu mục tiêu là custom runtime.

So sánh container image bằng công cụ phân tích layer của registry/build system. Tìm layer lớn, file trùng và layer không thể loại bỏ do thứ tự COPY. Không chỉ so sánh tag; dùng immutable image digest để xác nhận artifact được promote.

## 12. Những đánh đổi khi giảm kích thước

| Cách giảm | Lợi ích | Rủi ro cần kiểm thử |
|---|---|---|
| Giảm module root | Loại module và dependency không cần | Reflection, ServiceLoader hoặc nhánh hiếm có thể thiếu module |
| Bỏ jdk.localedata | Giảm locale data | Formatting, parsing, collation theo locale bị ảnh hưởng |
| --include-locales | Chỉ giữ locale được hỗ trợ | Locale fallback hoặc thư viện có thể cần locale khác |
| --strip-debug | Runtime image nhỏ hơn | Khó debug native/JVM runtime content |
| --no-man-pages | Bỏ tài liệu dòng lệnh | Không phù hợp image phục vụ mục đích phát triển |
| --no-header-files | Bỏ C/C++ headers | Không phù hợp nếu image dùng để biên dịch native |
| --compress=zip-9 | Có thể giảm dung lượng thêm | CPU/startup/resource access có thể tăng |
| Bỏ --bind-services | Giảm provider module | ServiceLoader không tìm thấy provider cần thiết |
| Thu gọn jpackage --input | Giảm app payload | Thiếu resource, dependency hoặc legal notice |
| Base container nhỏ hơn | Giảm container footprint | Thiếu CA cert, libc hoặc runtime OS dependency |

Không có cấu hình tối ưu chung cho mọi ứng dụng. Tập module nhỏ nhất về lý thuyết chưa chắc là cấu hình phù hợp nhất cho vận hành nếu nó làm mất khả năng chẩn đoán hoặc yêu cầu hỗ trợ production.

## 13. Kiểm thử sau khi tối ưu

Mỗi lần thay module, locale, service binding hoặc resource phải chạy test trên chính runtime image đã tạo.

### Runtime validation

~~~bash
build/runtime-small/bin/java --version
build/runtime-small/bin/java --list-modules
build/runtime-small/bin/java --validate-modules
~~~

Kiểm tra Java version, module set và module resolution. Sau đó chạy application bằng launcher bên trong runtime image.

### Functional regression

Kiểm tra startup/shutdown, mọi command/entry point được hỗ trợ, database driver và JDBC, XML/JSON/compression/crypto, TLS/HTTPS và certificate chain, locale/timezone/date formatting, ServiceLoader/plugin, JNI/native library trên từng OS/architecture, file access/permissions và logging.

### Performance regression

So sánh trước/sau kích thước runtime và application image, installer download size, installed footprint, startup time, CPU khi load resource/compression, RSS/heap/native memory và thời gian build/package/upload/deploy.

Chỉ chấp nhận tối ưu nếu dung lượng giảm mà các yêu cầu chức năng và vận hành vẫn đạt.

## 14. Lưu cấu hình build có thể tái lập

Không để lệnh jlink dài rải rác trong nhiều script mà không có bản chuẩn. Lưu options file:

~~~text
--module-path
mods:/opt/jdk/jmods
--add-modules
com.acme.imageapp
--strip-debug
--no-header-files
--no-man-pages
--compress=zip-6
--output
build/runtime
~~~

Sau đó gọi:

~~~bash
jlink @jlink.options
~~~

Đường dẫn trong options file phải phù hợp build agent. jlink options file không thay thế metadata; lưu thêm JDK vendor/version, OS, architecture, module list, checksum và application commit.

Có thể lưu module list tự động từ jdeps như build output, nhưng phải review thay đổi trước khi release. Nếu module graph thay đổi sau khi nâng dependency, cần xem xét vì nó có thể làm runtime image tăng.

## 15. Anti-pattern và cách sửa

| Anti-pattern | Vì sao gây image lớn | Cách sửa |
|---|---|---|
| Luôn dùng full JDK để chạy production | Mang theo compiler và tooling không cần | Dùng custom runtime hoặc runtime base phù hợp |
| Thêm mọi module để tránh lỗi | Kéo dependency không cần | Phân tích jdeps, review module root và test |
| Luôn bật --bind-services | Có thể kéo provider module bổ sung | Bật khi service binding là yêu cầu |
| Giữ mọi locale | Tăng runtime data | Chọn locale sản phẩm hỗ trợ |
| Dùng compression thấp hoặc tắt compression | Resource chiếm nhiều dung lượng hơn | Đo zip-6/zip-9 và startup |
| Đưa cả build directory vào --input | Đóng gói test, source, log và cache | Tạo staging input rõ ràng |
| Đóng gói trùng JDK và runtime image trong container | Lặp runtime ở nhiều layer | Dùng multi-stage và chỉ copy custom runtime |
| Xóa module không chạy test | Sự cố chỉ xuất hiện ở nhánh code chưa được cover | Thêm regression test theo tính năng |
| Tối ưu theo MB mà không đo startup | Compression có thể làm runtime chậm hơn | Đo footprint và performance cùng lúc |
| Không ghi lại JDK/options | Không tái tạo được image | Pin toolchain và lưu jlink options/provenance |

## 16. Quy trình xử lý khi runtime image quá lớn

1. Xác nhận kích thước runtime image, application payload, app image và installer.
2. Ghi JDK vendor/version, OS, architecture và command line.
3. Đo từng thư mục/file để tìm phần chiếm dung lượng.
4. Dùng jdeps phân tích module dependency của app và dependency runtime.
5. Kiểm tra module descriptor, reflection, ServiceLoader, JNI và plugin.
6. So sánh module list hiện tại với module set tối thiểu dự kiến.
7. Thu hẹp --add-modules và chỉ thêm module có lý do.
8. Rà soát --bind-services và jdk.localedata.
9. Dùng strip-debug, no-header-files, no-man-pages và compression phù hợp.
10. Tạo jpackage input directory chỉ chứa file runtime cần thiết.
11. Kiểm tra container layers nếu runtime được đưa vào OCI image.
12. Chạy runtime validation, functional regression và performance regression.
13. Đo lại cùng chỉ số và so sánh với baseline.
14. Lưu options, module list, digest và kết quả test.
15. Publish version mới và promote cùng artifact đã kiểm thử.

## 17. Checklist release runtime image tối ưu

- [ ] Đã đo riêng runtime, application payload, app image và installer.
- [ ] Đã xác định module/resource lớn nhất bằng số liệu.
- [ ] Đã dùng jdeps và review module dependency.
- [ ] Đã kiểm tra reflection, ServiceLoader, JNI và dynamic loading.
- [ ] Không thêm module chỉ để phòng ngừa chung chung.
- [ ] Đã review --bind-services.
- [ ] Đã review jdk.localedata và danh sách locale.
- [ ] Đã đánh giá strip-debug, no-header-files và no-man-pages.
- [ ] Đã so sánh compression level trên target hardware.
- [ ] jpackage input không chứa test, source, log hoặc build cache không cần.
- [ ] Container final không đóng gói trùng JDK/runtime.
- [ ] java --list-modules và --validate-modules đạt.
- [ ] Functional regression trên runtime image đạt.
- [ ] Startup, CPU, RSS và installed footprint đạt yêu cầu.
- [ ] JDK version, options, module list và digest được lưu.
- [ ] Artifact release bất biến và được promote bằng cùng digest.

## 18. Ghi nhớ

- Runtime image lớn thường do module root rộng, service provider, locale data hoặc app payload thừa.
- Đo runtime image riêng với application image và installer.
- jdeps giúp xác định module dependency; kết quả cần review vì reflection, JNI và service loading có thể không hiện đầy đủ.
- jlink chỉ thêm module root và dependency bắc cầu; hãy chọn root hẹp có căn cứ.
- --bind-services hữu ích khi ứng dụng cần service provider nhưng có thể tăng module set.
- --include-locales cần jdk.localedata và nên giữ đúng locale được hỗ trợ.
- --strip-debug, --no-header-files và --no-man-pages có thể giảm runtime image; chúng không thay thế việc thu gọn application payload.
- --compress=zip-6 là mặc định của JDK 26; zip-9 có thể nhỏ hơn nhưng cần đo startup/CPU.
- jpackage đóng gói mọi file trong --input; tạo staging directory chỉ có file cần phân phối.
- jpackage app image chứa launcher, application payload và runtime.
- Từ JDK 25, jpackage không tự include service bindings; bật --bind-services chỉ khi ứng dụng cần.
- Với container, dùng multi-stage build và kiểm tra từng layer để tránh đóng gói JDK trùng.
- Không đánh đổi tính năng, khả năng chẩn đoán hoặc bảo mật để đạt một con số MB.
- Kiểm thử trên chính runtime image đã tối ưu và promote cùng artifact digest.

## Tài liệu tham khảo chính thức

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Packaging Tool User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/index.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)