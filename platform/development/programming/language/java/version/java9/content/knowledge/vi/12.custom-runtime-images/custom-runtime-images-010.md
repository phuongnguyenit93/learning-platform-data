# Cập nhật bản vá và tái tạo image khi JDK thay đổi

Một runtime image được tạo bằng **jlink** chứa tập module JDK đã chọn cùng launcher, thư viện native và cấu hình cần thiết để chạy ứng dụng. Khi JDK nhận bản cập nhật bảo mật hoặc sửa lỗi, runtime image cũ không tự nhận các bản vá đó. Cần dùng JDK đã cập nhật để tạo một image mới, kiểm thử image mới rồi triển khai nó như một phiên bản runtime mới.

Quy trình này áp dụng cho các bản cập nhật JDK cùng dòng phát hành và cả khi nâng lên feature release mới. Điểm quan trọng là **jlink phải lấy công cụ và các module đầu vào từ cùng bản JDK mục tiêu**. Hãy lưu lại phiên bản JDK, module đầu vào, tùy chọn liên kết và kết quả kiểm thử để có thể tái tạo và truy vết image đã phát hành.

Bài dùng cú pháp Java 17 trở lên. Ví dụ được biên dịch và liên kết trên Zulu OpenJDK 24.0.2; đây là môi trường kiểm chứng lệnh, không phải khuyến nghị chọn phiên bản JDK triển khai. Trong thực tế hãy dùng bản JDK còn được nhà cung cấp hỗ trợ và đã được tổ chức phê duyệt.

## 1. Runtime image chứa những gì?

**jlink** là công cụ của JDK dùng để liên kết một tập named module thành runtime image tùy chỉnh. Image chỉ chứa những module cần thiết cho ứng dụng và các thành phần runtime liên quan được công cụ đưa vào.

Một image điển hình có cấu trúc như sau:

~~~text
runtime-image/
  bin/
    java
    app
  conf/
  include/
  legal/
  lib/
    modules
    security/
  release
~~~

Tên file launcher và một số thư mục có thể khác theo hệ điều hành. Image thường có:

- Runtime launcher **java** và launcher ứng dụng nếu đã khai báo bằng **--launcher**.
- Các module đã được resolve và liên kết, nằm trong runtime module image.
- Thư viện native và thành phần hỗ trợ cần cho các module được chọn.
- Cấu hình runtime, thông tin phiên bản và giấy phép tương ứng.

Runtime image không phải bản sao đầy đủ của JDK. Nó thường không có **javac**, **jlink**, **jdeps**, source code hoặc toàn bộ công cụ phát triển. Hãy giữ JDK dùng để build image trong build environment riêng.

## 2. Vì sao phải tạo image mới khi JDK được vá?

Các bản cập nhật JDK có thể sửa lỗi trong module lõi, thư viện bảo mật, TLS, bộ xử lý chứng thư, parser, timezone data, thư viện native hoặc các thành phần runtime khác. Nếu ứng dụng đang chạy bằng image cũ, những thay đổi đó không tự xuất hiện chỉ vì máy build đã được cập nhật JDK.

Ví dụ:

~~~text
JDK 24.0.1
    |
    v
runtime-image-24.0.1
    |
    |  JDK nhận bản cập nhật bảo mật
    v
JDK 24.0.2
    |
    v
jlink + các module ứng dụng
    |
    v
runtime-image-24.0.2
~~~

Quy trình cập nhật đúng là dùng **jlink và jmods từ JDK đã vá** để liên kết lại image. Không thay từng file trong image cũ bằng file lấy từ JDK mới, vì các module, thư viện native, cấu hình và dữ liệu runtime cần đồng bộ theo cùng một bản phát hành.

Một image đã liên kết cũng không phải đầu vào để jlink tiếp tục cập nhật. Công cụ liên kết từ module/JMOD đầu vào; tài liệu trợ giúp JDK hiện đại ghi rõ khả năng liên kết từ runtime image không được hỗ trợ. Vì vậy hãy giữ module ứng dụng và cấu hình build để tạo image mới mỗi lần cập nhật.

## 3. Phân biệt cập nhật JDK với cập nhật ứng dụng

Hai thay đổi này có thể diễn ra cùng lúc nhưng cần truy vết riêng:

| Thay đổi | Đầu vào cần cập nhật | Việc cần làm |
|---|---|---|
| JDK có bản vá bảo mật/correction update | Bộ JDK đã vá, đặc biệt thư mục **jmods** | Chạy lại jlink để tạo runtime image mới |
| Ứng dụng thay đổi mã nguồn | Module/JAR ứng dụng đã build | Biên dịch lại ứng dụng rồi tạo image mới nếu image đóng gói module ứng dụng |
| Dependency ứng dụng thay đổi | Các modular JAR hoặc module dependency | Phân tích lại module cần thiết và liên kết lại |
| Nâng feature release JDK | Bộ JDK mới, API/module graph và tùy chọn jlink tương ứng | Build lại, rà soát tương thích và chạy kiểm thử rộng hơn |

Một ứng dụng được biên dịch bằng **--release 17** vẫn có thể chạy trên runtime image JDK 24 hoặc phiên bản mới hơn tương thích. Tuy nhiên, **--release 17 không biến image được tạo bằng jlink của JDK 24 thành runtime Java 17**. Phiên bản runtime của image được quyết định bởi bộ JDK cung cấp module đầu vào cho jlink.

Nếu sản phẩm cần chạy trên Java 17, hãy dùng JDK 17 được hỗ trợ để tạo image Java 17. Không trộn công cụ jlink của một feature release với thư mục jmods của feature release khác.

## 4. Quản lý JDK đầu vào cho build

Trước khi build, xác định chính xác JDK được dùng:

~~~bash
export JDK_HOME=/opt/jdk-supported-update

"$JDK_HOME/bin/java" --version
"$JDK_HOME/bin/javac" --version
"$JDK_HOME/bin/jlink" --version
cat "$JDK_HOME/release"
~~~

Kiểm tra các thông tin:

- Nhà cung cấp JDK và phiên bản update/build.
- Feature release và kiến trúc hệ điều hành.
- Phiên bản của **java**, **javac** và **jlink** có cùng bộ cài.
- Thư mục **$JDK_HOME/jmods** tồn tại và có **java.base.jmod**.
- Checksum hoặc chữ ký của gói JDK đã được xác minh theo quy trình phát hành của nhà cung cấp.

Trên Windows PowerShell, có thể kiểm tra tương ứng:

~~~powershell
$JDK_HOME = "C:\Java\jdk-supported-update"

& "$JDK_HOME\bin\java.exe" --version
& "$JDK_HOME\bin\javac.exe" --version
& "$JDK_HOME\bin\jlink.exe" --version
Get-Content "$JDK_HOME\release"
Test-Path "$JDK_HOME\jmods\java.base.jmod"
~~~

Không lấy **jlink.exe** từ một JDK cũ rồi trỏ nó vào **jmods** của JDK mới. Hãy gọi công cụ trực tiếp từ bộ JDK đang được dùng để tạo image.

## 5. Xác định module cần đóng gói

Trước khi liên kết image, cần biết ứng dụng cần module nào. Với ứng dụng modular, khai báo dependency trực tiếp trong **module-info.java**. Ví dụ:

~~~java
module com.example.app {
    requires java.sql;
}
~~~

Có thể dùng **jdeps --print-module-deps** để xem dependency module được phát hiện từ bytecode:

~~~bash
"$JDK_HOME/bin/jdeps" --print-module-deps \
    --module-path mods \
    --module com.example.app
~~~

Với ví dụ bên dưới, kết quả trên JDK 24.0.2 là:

~~~text
java.base,java.sql
~~~

Kết quả này hỗ trợ kiểm tra module graph, nhưng không thay thế việc rà soát cấu hình runtime. Một số module có thể được dùng qua reflection, service loading, plugin hoặc cấu hình nên không xuất hiện như dependency bytecode trực tiếp.

Nếu ứng dụng sử dụng service provider, kiểm tra các module cung cấp service. Tùy nhu cầu, **jlink --bind-services** có thể liên kết các provider module tìm thấy trên module path cùng dependency của chúng. Tùy chọn này có thể làm image lớn hơn; chỉ bật khi ứng dụng cần các provider đó.

Thư viện không modular đặt trên classpath không tự trở thành một phần của tập module được jlink liên kết. Hãy đóng gói và cấu hình các thư viện classpath đó theo cách triển khai ứng dụng, hoặc chuyển dependency sang module phù hợp khi kiến trúc cho phép.

## 6. Ví dụ hoàn chỉnh: tạo runtime image cho ứng dụng modular

Ví dụ dùng module **com.example.app** phụ thuộc **java.sql**. Ứng dụng in phiên bản runtime và số JDBC driver được đăng ký. Không có driver provider nào được thêm vào ví dụ, vì vậy số lượng bằng 0.

Cấu trúc:

~~~text
project/
  src/
    com.example.app/
      module-info.java
      com/example/app/Main.java
  mods/
~~~

**Tệp src/com.example.app/module-info.java:**

~~~java
module com.example.app {
    requires java.sql;
}
~~~

**Tệp src/com.example.app/com/example/app/Main.java:**

~~~java
package com.example.app;

import java.sql.DriverManager;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Runtime: " + Runtime.version());
        System.out.println("JDBC drivers: " + DriverManager.drivers().count());
    }
}
~~~

Biên dịch module bằng JDK được chọn:

~~~bash
"$JDK_HOME/bin/javac" --release 17 \
    --module-source-path src \
    -d mods \
    -m com.example.app
~~~

Kiểm tra dependency:

~~~bash
"$JDK_HOME/bin/jdeps" --print-module-deps \
    --module-path mods \
    --module com.example.app
~~~

Liên kết runtime image vào một thư mục output mới:

~~~bash
"$JDK_HOME/bin/jlink" \
    --module-path "$JDK_HOME/jmods:mods" \
    --add-modules com.example.app \
    --launcher app=com.example.app/com.example.app.Main \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output runtime-image
~~~

Trên Windows, dấu phân cách các đường dẫn trong **--module-path** là dấu chấm phẩy (**;**) thay cho dấu hai chấm (**:**). Ví dụ PowerShell trên một dòng:

~~~powershell
& "$JDK_HOME\bin\jlink.exe" --module-path "$JDK_HOME\jmods;mods" --add-modules com.example.app --launcher app=com.example.app/com.example.app.Main --strip-debug --no-header-files --no-man-pages --output runtime-image
~~~

Chạy bằng launcher vừa tạo:

~~~bash
./runtime-image/bin/app
./runtime-image/bin/java --version
./runtime-image/bin/java --list-modules
~~~

Kết quả chạy ứng dụng trên môi trường kiểm chứng JDK 24.0.2:

~~~text
Runtime: 24.0.2+12
JDBC drivers: 0
~~~

Trên Windows, launcher tương ứng được tạo trong **runtime-image\bin\app.bat** và runtime launcher là **runtime-image\bin\java.exe**.

## 7. Quy trình tạo lại image sau một bản vá JDK

Giả sử image hiện tại được build bằng **JDK_HOME_OLD**. Nhà cung cấp phát hành một JDK update mới và tổ chức đã phê duyệt **JDK_HOME_NEW**.

Thực hiện theo các bước:

1. Lấy bộ JDK mới từ nhà cung cấp được phê duyệt và xác minh checksum/chữ ký.
2. Xác nhận phiên bản, vendor, build number, kiến trúc và thư mục **jmods** của JDK mới.
3. Giữ lại module ứng dụng, modular dependency, cấu hình jlink và metadata của image cũ.
4. Build lại ứng dụng nếu mã nguồn hoặc dependency thay đổi; nếu chỉ JDK được vá, vẫn phải tạo image mới từ module đầu vào của JDK mới.
5. Chạy **jdeps** và rà soát các module cần có.
6. Gọi **jlink** của JDK mới, dùng **jmods** của chính JDK mới và ghi ra thư mục image mới.
7. Kiểm tra phiên bản runtime trong image mới, module list, launcher và hành vi ứng dụng.
8. Chạy regression, integration, security/TLS và các kiểm thử đặc thù của sản phẩm.
9. Phát hành image mới với tag/version riêng. Giữ image trước đó trong thời gian rollback đã quy định.

Ví dụ lệnh build lại trên Linux/macOS:

~~~bash
export NEW_JDK_HOME=/opt/jdk-supported-update-new

"$NEW_JDK_HOME/bin/java" --version
"$NEW_JDK_HOME/bin/jlink" --version
test -f "$NEW_JDK_HOME/jmods/java.base.jmod"

"$NEW_JDK_HOME/bin/jlink" \
    --module-path "$NEW_JDK_HOME/jmods:mods" \
    --add-modules com.example.app \
    --launcher app=com.example.app/com.example.app.Main \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output runtime-image-new

./runtime-image-new/bin/java --version
./runtime-image-new/bin/app
~~~

Ví dụ trên cố ý tạo **runtime-image-new**. Không ghi đè image hiện đang phục vụ production. Đường dẫn output của lần build mới cần là thư mục mới/chưa tồn tại; nếu muốn build lại, hãy dùng một output path mới sau khi artifact cũ đã được lưu trữ theo quy trình.

Nếu JDK thay đổi feature release, không chỉ kiểm tra bản vá. Hãy xem lại API, module graph, tùy chọn plugin jlink, hành vi mặc định, dependency native và compatibility test. Nếu chỉ là update release trong cùng feature line, vẫn phải chạy đầy đủ các kiểm thử bảo mật và smoke test của sản phẩm.

## 8. Chọn tùy chọn jlink có chủ đích

Một số tùy chọn thường hữu ích:

| Tùy chọn | Ý nghĩa | Lưu ý |
|---|---|---|
| **--module-path** | Nơi tìm JMOD/module đầu vào | Bao gồm **jmods** của JDK mục tiêu và module ứng dụng |
| **--add-modules** | Chọn root module cần liên kết | Dependency cần thiết được resolve theo module graph |
| **--launcher** | Tạo launcher có tên cho module/main class | Giúp người vận hành chạy ứng dụng bằng lệnh ổn định |
| **--bind-services** | Liên kết service provider module và dependency của chúng | Chỉ bật khi cần provider được tìm thấy trên module path |
| **--strip-debug** | Loại bỏ debug information | Có thể làm giảm dung lượng; giữ symbol/debug artifact riêng nếu cần |
| **--no-header-files** | Không đưa header files vào image | Phù hợp với runtime không cần header phát triển |
| **--no-man-pages** | Không đưa man pages vào image | Phù hợp với runtime triển khai |

Có thể kiểm tra các tùy chọn và plugin được hỗ trợ bởi chính JDK dùng để build:

~~~bash
"$JDK_HOME/bin/jlink" --help
"$JDK_HOME/bin/jlink" --list-plugins
~~~

Không sao chép mù các tùy chọn từ pipeline cũ. Cú pháp plugin có thể thay đổi hoặc bị deprecated giữa các JDK. Ví dụ, JDK 24.0.2 đã đánh dấu các giá trị compression số **0**, **1**, **2** là deprecated; cú pháp hiện hành của plugin compression dùng dạng **zip-0** đến **zip-9**. Nếu không cần tinh chỉnh compression, giữ mặc định thường đơn giản hơn.

## 9. Kiểm tra image mới trước khi triển khai

Việc jlink kết thúc với exit code 0 chỉ xác nhận quá trình liên kết đã hoàn tất. Trước khi phát hành, hãy xác nhận image thực sự dùng đúng JDK và chạy được ứng dụng.

Các kiểm tra cơ bản:

~~~bash
runtime-image-new/bin/java --version
runtime-image-new/bin/java --list-modules
runtime-image-new/bin/app
cat runtime-image-new/release
~~~

Kiểm tra thêm:

- Phiên bản runtime và vendor đúng với JDK mới đã chọn.
- Các module bắt buộc của ứng dụng có trong image.
- Launcher ứng dụng hoạt động từ thư mục triển khai dự kiến.
- Các file cấu hình, truststore, certificate và resource cần thiết được cung cấp đúng.
- Kết nối TLS, JDBC, DNS, timezone, locale và native integration hoạt động theo yêu cầu của ứng dụng.
- Service provider được phát hiện nếu ứng dụng dựa vào **ServiceLoader** hoặc SPI.
- Các dependency classpath ngoài image được đóng gói và tìm thấy đúng cách.
- Kiểm thử trên cùng OS/architecture với môi trường triển khai.

Runtime image có launcher và thư viện native phù hợp với nền tảng build. Vì vậy, hãy tạo artifact riêng cho từng hệ điều hành và kiến trúc triển khai được hỗ trợ. Không mặc định một image Windows có thể chạy trên Linux hoặc ngược lại.

## 10. Triển khai và rollback an toàn

Sau khi image mới vượt qua kiểm thử, triển khai nó như một artifact có phiên bản riêng:

~~~text
releases/
  runtime-image-old/
  runtime-image-new/
current -> runtime-image-new
~~~

Trong môi trường có thể đổi symlink hoặc cấu hình deployment pointer, chuyển sang image mới sau khi kiểm thử. Trên Windows hoặc hệ thống container, dùng cơ chế phát hành/đổi phiên bản tương đương của nền tảng.

Giữ image trước đó cho tới khi hết khoảng thời gian rollback. Nếu smoke test hoặc giám sát sau triển khai phát hiện lỗi, chuyển deployment về artifact cũ đã được lưu trữ. Không sửa file trong image đang chạy để thử vá nóng; việc thay thế file runtime tùy tiện có thể làm module và thư viện native không đồng bộ.

Với container, cập nhật base/build stage chứa JDK đã vá, tạo lại runtime image, build container image mới và phát hành tag bất biến. Chỉ cập nhật tag của container registry sau khi artifact đã qua kiểm thử và có thể truy xuất lại đúng digest.

## 11. Lỗi thường gặp khi cập nhật runtime image

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **jlink** báo không tìm thấy module | Module ứng dụng hoặc dependency không có trên module path | Kiểm tra đường dẫn **jmods**, thư mục **mods** và module name |
| Image vẫn báo phiên bản JDK cũ | Đã dùng nhầm **jlink** hoặc **jmods** của JDK cũ | Kiểm tra đường dẫn công cụ và module đầu vào bằng **--version** |
| Build mới chạy nhưng thiếu service provider | Provider module không nằm trên module path hoặc chưa được bind | Bổ sung provider module; cân nhắc **--bind-services** và test SPI |
| Ứng dụng không tìm thấy thư viện classpath | JAR không modular không tự được đóng gói vào module image | Đóng gói dependency riêng và cấu hình classpath của launcher |
| Image mới thiếu module được nạp động | Dependency reflection/plugin không xuất hiện trong phân tích tĩnh | Thêm module root cần thiết và kiểm thử luồng nạp động |
| jlink từ chối output directory | Đường dẫn output đã tồn tại hoặc chứa nội dung cũ | Chọn thư mục output mới cho mỗi lần build |
| Image chạy trên máy build nhưng lỗi trên production | Khác OS/architecture, cấu hình, quyền file hoặc native dependency | Build/test trên nền tảng triển khai tương ứng |
| Tùy chọn jlink cũ không còn được hỗ trợ | Plugin option đã deprecated hoặc thay đổi giữa JDK | Kiểm tra **jlink --help** và **--list-plugins** của JDK mục tiêu |
| Nâng JDK làm thay đổi TLS hoặc chứng thư | Security provider, truststore hoặc thuật toán mặc định thay đổi | Kiểm tra cấu hình bảo mật và chạy integration test TLS |
| Không thể cập nhật image cũ bằng jlink | jlink liên kết từ JMOD/module đầu vào, không cập nhật trực tiếp runtime image đã tạo | Dùng JDK mới và module đầu vào để tạo image mới |

## 12. Checklist trước khi phát hành image đã cập nhật

- [ ] Đã xác định bản JDK mới, vendor, update/build và kiến trúc mục tiêu.
- [ ] Đã xác minh checksum/chữ ký của bộ JDK.
- [ ] **java**, **javac**, **jlink** và **jmods** đến từ cùng bộ JDK mục tiêu.
- [ ] Đã kiểm tra module graph và dependency bằng **jdeps**.
- [ ] Đã rà soát service provider, reflection, plugin và dependency classpath.
- [ ] Đã tạo image mới vào output path riêng.
- [ ] Đã kiểm tra **java --version**, **java --list-modules** và file **release** trong image.
- [ ] Launcher và cấu hình ứng dụng hoạt động trên OS/architecture triển khai.
- [ ] Đã chạy regression, integration, security/TLS và smoke test.
- [ ] Đã lưu build options, phiên bản JDK, checksum dependency và digest artifact.
- [ ] Image cũ vẫn được giữ để rollback.
- [ ] Deployment pointer/container tag chỉ chuyển sau khi image mới được phê duyệt.

## 13. Tài liệu tham khảo

- [Java SE 25 — jlink tool reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html)
- [Java SE 25 — jdeps tool reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jdeps.html)
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282)
- [JEP 220 — Modular Run-Time Images](https://openjdk.org/jeps/220)
- [Java SE 25 — java launcher reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
