# Lệnh jpackage trong Java

## 1. jpackage là gì?

**jpackage** là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc gói cài đặt theo hệ điều hành. Mục tiêu là giúp người dùng cuối cài đặt và khởi chạy ứng dụng giống một ứng dụng desktop thông thường, thay vì phải tự cài JDK rồi chạy lệnh java với classpath dài.

Một gói được tạo bằng jpackage có thể bao gồm:

- JAR hoặc module của ứng dụng.
- Các thư viện và tài nguyên cần thiết.
- Một launcher riêng để khởi chạy ứng dụng.
- Một Java runtime image đi kèm để người dùng không phải cài Java riêng, nếu cấu hình đóng gói có runtime.

jpackage sử dụng **jlink** để tạo runtime image khi bạn không cung cấp runtime có sẵn. Vì vậy, công cụ này nối hai bước quan trọng của quá trình phát hành Java: tạo runtime phù hợp và đóng gói ứng dụng thành sản phẩm có thể phân phối.

jpackage được đưa vào JDK dưới dạng công cụ thử nghiệm ở các bản JDK 14–15 và trở thành công cụ hoàn chỉnh từ JDK 16. Với dự án mới, nên dùng JDK đang được dự án hỗ trợ và kiểm tra tùy chọn bằng chính lệnh `jpackage --help` của phiên bản đó.

## 2. Hai chế độ đầu ra chính

jpackage có hai nhóm đầu ra thường dùng:

| Chế độ | Kết quả | Mục đích |
|---|---|---|
| `app-image` | Một thư mục ứng dụng gồm launcher, payload và runtime | Kiểm thử, chạy trực tiếp hoặc làm đầu vào tạo installer |
| Native installer | Gói cài đặt theo hệ điều hành | Phân phối, cài đặt và tích hợp với hệ điều hành |

Các loại installer phổ biến:

| Hệ điều hành | Loại gói thường gặp |
|---|---|
| Windows | `.exe`, `.msi` |
| macOS | `.dmg`, `.pkg` |
| Linux | `.deb`, `.rpm` |

Loại gói có thể tạo phụ thuộc hệ điều hành, phiên bản JDK và công cụ đóng gói của nền tảng. Hãy xem `jpackage --help` trên máy build để biết chính xác các loại được hỗ trợ.

**Application image không phải installer.** Đây là thư mục đã đóng gói để có thể chạy ứng dụng. Installer có thêm quy trình cài đặt, gỡ cài đặt và tích hợp với hệ điều hành.

## 3. Điều kiện trước khi đóng gói

Trước khi chạy jpackage, cần chuẩn bị:

1. Một JDK có công cụ `jpackage` và `jlink`.
2. JAR ứng dụng đã biên dịch hoặc một ứng dụng modular.
3. Tất cả dependency runtime và resource cần thiết.
4. Tên ứng dụng, phiên bản, biểu tượng và metadata nếu cần.
5. Công cụ native packaging của hệ điều hành khi tạo installer.

Kiểm tra phiên bản:

~~~powershell
java -version
javac -version
jpackage --version
jpackage --help
~~~

jpackage tạo gói native cho nền tảng đang chạy. Hãy build trên hệ điều hành và kiến trúc mục tiêu: tạo `.msi` hoặc `.exe` trên Windows, `.dmg` hoặc `.pkg` trên macOS, và `.deb` hoặc `.rpm` trên Linux. Không nên xem jpackage là công cụ cross-compiler để tạo installer cho hệ điều hành khác.

Trên Windows, tạo installer `.exe` hoặc `.msi` thường cần cài WiX Toolset và cấu hình công cụ của WiX để jpackage tìm thấy. Linux và macOS cũng có yêu cầu công cụ đóng gói riêng. Application image thường là điểm bắt đầu thuận tiện để kiểm tra cấu trúc và launcher trước khi tạo installer.

## 4. Cú pháp tổng quát

Cú pháp cơ bản:

~~~bash
jpackage [options]
~~~

Một số tùy chọn quan trọng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--type` | Chọn loại đầu ra, ví dụ `app-image`, `exe`, `msi`, `dmg`, `pkg`, `deb`, `rpm` tùy nền tảng |
| `--name` | Tên ứng dụng hoặc gói |
| `--dest` | Thư mục nhận kết quả |
| `--input` | Thư mục chứa các tệp đầu vào cần đóng gói |
| `--main-jar` | JAR chính, đường dẫn tính tương đối từ input |
| `--main-class` | Lớp main đầy đủ nếu JAR không khai báo Main-Class phù hợp |
| `--module-path` | Nơi chứa các module |
| `--module` | Module chính và tùy chọn tên lớp main |
| `--runtime-image` | Runtime image đã được tạo sẵn |
| `--add-modules` | Các module cần đưa vào runtime |
| `--jlink-options` | Các tùy chọn truyền cho jlink |
| `--app-version` | Phiên bản ứng dụng |
| `--vendor` | Nhà cung cấp |
| `--description` | Mô tả ứng dụng |
| `--icon` | Tệp biểu tượng theo định dạng của nền tảng |

Một số quy tắc:

- Chọn **một trong hai** `--main-jar` hoặc `--module`; không dùng cả hai cho cùng một lần đóng gói.
- `--main-class` chỉ dùng cùng `--main-jar`.
- Với ứng dụng modular, module chính phải nằm trên `--module-path`.
- Nếu không cung cấp `--runtime-image`, jpackage tự gọi jlink để tạo runtime.
- Nếu đã có runtime image phù hợp, dùng `--runtime-image` để jpackage sao chép runtime đó vào application image.

Có thể dùng `@filename` để đọc tùy chọn từ một tệp argument file. Cách này hữu ích khi command line dài hoặc cần lưu cấu hình đóng gói để tái sử dụng.

## 5. Đóng gói ứng dụng không dùng module

Ứng dụng Java truyền thống thường được đóng gói từ một JAR chính. JAR nên khai báo `Main-Class` trong manifest hoặc bạn chỉ định lớp main bằng `--main-class`.

Ví dụ cấu trúc:

~~~text
project/
  src/
    demo/
      Main.java
  classes/
  input/
    hello.jar
  output/
~~~

Tạo tệp `src/demo/Main.java`:

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from jpackage");
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

Biên dịch bằng Java 17:

~~~powershell
New-Item -ItemType Directory -Force classes,input,output
javac --release 17 -d classes src\demo\Main.java
~~~

Đóng gói thành JAR và khai báo lớp main trong manifest:

~~~powershell
jar --create --file input\hello.jar --main-class demo.Main -C classes .
~~~

Tạo application image trên Windows:

~~~powershell
jpackage --type app-image --name HelloApp --app-version 1.2.3 --vendor Example --description "Demo application" --input input --main-jar hello.jar --dest output --win-console
~~~

`--main-jar hello.jar` là tên JAR tương đối với thư mục `input`. Tùy chọn `--win-console` tạo launcher console trên Windows, phù hợp với chương trình in kết quả ra terminal. Với ứng dụng GUI, thường không cần tùy chọn này.

Trên Linux hoặc macOS, có thể dùng cùng cấu hình ứng dụng nhưng bỏ `--win-console`:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --app-version 1.2.3 \
    --vendor Example \
    --input input \
    --main-jar hello.jar \
    --dest output
~~~

Trên Windows, application image tạo ra có cấu trúc khái quát:

~~~text
output/
  HelloApp/
    HelloApp.exe
    app/
      hello.jar
      HelloApp.cfg
    runtime/
      bin/
      lib/
~~~

Chạy launcher trên Windows:

~~~powershell
.\output\HelloApp\HelloApp.exe one two
~~~

Kết quả:

~~~text
Hello from jpackage
args=one,two
~~~

Application image đã có runtime riêng. Người dùng không cần gọi `java -jar` và không cần cài JDK riêng để chạy gói này.

## 6. Đóng gói ứng dụng modular

Với ứng dụng dùng JPMS, khai báo module chính và module path thay cho JAR chính:

~~~bash
jpackage --type app-image \
    --name ModularApp \
    --module-path mods \
    --module com.example.app/com.example.app.Main \
    --dest output
~~~

Trong đó:

- `--module-path mods` chỉ định thư mục chứa các module đã biên dịch hoặc modular JAR.
- `--module com.example.app/com.example.app.Main` chỉ định module chính và lớp main.
- jpackage dùng module graph để tạo runtime image phù hợp thông qua jlink nếu không được cung cấp runtime riêng.

Các module dependency cần có mặt trên module path và phải resolve được. Nếu ứng dụng dùng service provider, reflection hoặc resource đặc biệt, hãy kiểm tra các module được đưa vào runtime và thử chạy application image trước khi phát hành.

Không trộn `--module` với `--main-jar`. Chọn đúng cách đóng gói theo cấu trúc ứng dụng.

## 7. Runtime image và jlink

Khi không chỉ định `--runtime-image`, jpackage tự chạy jlink để tạo runtime image. Runtime được tạo có thể nhỏ hơn một JDK đầy đủ vì nó chỉ cần các module phục vụ ứng dụng và các thành phần runtime cần thiết.

Có thể điều chỉnh module được đưa vào runtime bằng:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --add-modules java.base,java.desktop \
    --dest output
~~~

Chỉ thêm module ứng dụng thực sự cần. Ví dụ ứng dụng Swing hoặc AWT cần `java.desktop`; chương trình chỉ xử lý logic cơ bản có thể chỉ cần các module nền tảng thích hợp.

### Tạo runtime riêng bằng jlink

Khi cần kiểm soát chi tiết runtime, chạy jlink trước:

~~~bash
jlink --add-modules java.base --output custom-runtime
~~~

Sau đó đưa runtime đó cho jpackage:

~~~bash
jpackage --type app-image \
    --name HelloAppCustom \
    --input input \
    --main-jar hello.jar \
    --runtime-image custom-runtime \
    --dest output
~~~

Với runtime image tự tạo, cần bảo đảm:

- Runtime được tạo cho đúng hệ điều hành và kiến trúc đích.
- Đã bao gồm các module mà ứng dụng cần.
- Phiên bản runtime tương thích với bytecode và thư viện ứng dụng.
- Có đủ thành phần native và cấu hình cần thiết cho môi trường triển khai.

Nếu dùng runtime image riêng, jpackage sẽ sao chép runtime đó vào application image thay vì tự tạo một runtime mới bằng jlink.

### Tùy chỉnh jlink options

`--jlink-options` cho phép truyền tùy chọn đến jlink. Ví dụ:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --jlink-options "--strip-debug --no-man-pages --no-header-files" \
    --dest output
~~~

Các tùy chọn này ảnh hưởng đến runtime image, không thay thế các tùy chọn xác định ứng dụng như `--main-jar` hoặc `--module`. Hãy kiểm tra `jlink --help` và chạy thử ứng dụng sau khi tinh giản runtime để tránh bỏ thiếu module hoặc dữ liệu cần thiết.

## 8. Tạo native installer

Sau khi application image đã được kiểm thử, có thể tạo installer từ thư mục image có sẵn bằng `--app-image`.

Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name HelloApp --app-image output\HelloApp --dest installers --win-per-user-install --win-menu --win-shortcut
~~~

Có thể dùng `--type exe` thay cho `msi` nếu muốn định dạng installer EXE được hỗ trợ trên máy build. Các tùy chọn Windows thường gặp:

- `--win-per-user-install`: cài đặt theo người dùng.
- `--win-menu`: tạo mục trong Start Menu.
- `--win-shortcut`: tạo shortcut.
- `--win-dir-chooser`: cho phép người dùng chọn thư mục cài đặt.
- `--win-menu-group`: tên nhóm trong Start Menu.
- `--win-console`: tạo launcher console cho ứng dụng cần terminal.

Trên Windows, WiX Toolset là yêu cầu phổ biến để tạo MSI/EXE. Nếu jpackage báo không tìm thấy WiX hoặc công cụ tương ứng, hãy cài và cấu hình đúng phiên bản được JDK đang dùng hỗ trợ.

Ví dụ trên macOS:

~~~bash
jpackage --type dmg \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --dest installers
~~~

Có thể tạo gói PKG bằng `--type pkg` nếu cần kiểu installer đó. macOS có thêm tùy chọn cho bundle identifier, ký ứng dụng và cấu hình DMG; tên và yêu cầu tùy chọn phụ thuộc phiên bản JDK.

Ví dụ trên Linux:

~~~bash
jpackage --type deb \
    --name helloapp \
    --input input \
    --main-jar hello.jar \
    --dest installers
~~~

Có thể dùng `--type rpm` nếu hệ thống build hỗ trợ định dạng RPM. Linux có các tùy chọn riêng như tên package, maintainer, category, dependency và shortcut. Kiểm tra `jpackage --help` trên đúng bản phân phối Linux để xem công cụ đóng gói cần cài.

jpackage không tự biến một application image thành installer cho mọi hệ điều hành. Installer phải được tạo và kiểm thử trên nền tảng mục tiêu.

## 9. Metadata, biểu tượng và tài nguyên bổ sung

Một installer tốt nên có tên, phiên bản, vendor, mô tả và icon nhất quán.

Ví dụ:

~~~bash
jpackage --type app-image \
    --name InventoryClient \
    --app-version 2.4.0 \
    --vendor "Example Company" \
    --description "Inventory desktop client" \
    --copyright "Copyright 2026 Example Company" \
    --icon assets/app-icon.ico \
    --input input \
    --main-jar inventory.jar \
    --dest output
~~~

Định dạng icon phải phù hợp nền tảng, chẳng hạn ICO trên Windows và ICNS trên macOS. Linux thường dùng PNG. Hãy kiểm tra tài liệu của nền tảng và kích thước biểu tượng trước khi đóng gói.

Một số tùy chọn khác:

- `--license-file`: đưa tệp license vào installer nếu nền tảng hỗ trợ.
- `--about-url`: trang chủ hoặc trang thông tin ứng dụng.
- `--install-dir`: thư mục con trong vị trí cài đặt mặc định.
- `--app-content`: thêm file hoặc thư mục vào payload ứng dụng.
- `--resource-dir`: thay thế resource/template mặc định của jpackage khi cần tùy chỉnh sâu.

`--input` đưa toàn bộ tệp trong thư mục đầu vào vào application payload. Dependency phải được tổ chức để launcher tìm thấy chúng, ví dụ thông qua manifest Class-Path của JAR chính hoặc module path. jpackage không thay thế Maven/Gradle trong việc phân giải phiên bản dependency.

## 10. Tạo nhiều launcher cho cùng một ứng dụng

Một application image có thể có thêm launcher với cấu hình khác nhau bằng `--add-launcher`.

Ví dụ, tạo tệp `admin.properties`:

~~~properties
main-jar=hello.jar
arguments=--mode=admin
java-options=-Xmx512m
description=Administrative launcher
~~~

Sau đó chạy:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --add-launcher Admin=admin.properties \
    --dest output
~~~

Launcher chính dùng cấu hình dòng lệnh gốc; launcher Admin nhận cấu hình bổ sung trong tệp properties. Có thể tạo nhiều launcher phụ bằng cách lặp lại `--add-launcher`.

Một số key được hỗ trợ trong launcher properties gồm:

- `main-jar`, `main-class`, `module`.
- `description`, `arguments`, `java-options`.
- `app-version`, `icon`.
- `win-console`, `win-shortcut`, `win-menu`.
- `linux-app-category`, `linux-shortcut`.
- `launcher-as-service` trên nền tảng hỗ trợ.

Các key được hỗ trợ phụ thuộc nền tảng và phiên bản jpackage. Dùng `jpackage --help` để kiểm tra trước khi sử dụng.

## 11. Cấu hình file association và installer resource

jpackage hỗ trợ mô tả file association bằng một tệp properties. Ví dụ `document.properties`:

~~~properties
extension=example
mime-type=application/x-example
description=Example document
~~~

Đưa tệp này vào lệnh đóng gói installer trên Windows:

~~~powershell
jpackage --type exe --name ExampleEditor --input input --main-jar editor.jar --file-associations document.properties --dest installers
~~~

File association yêu cầu tích hợp hệ điều hành và có thể chỉ áp dụng khi tạo installer phù hợp. Hãy kiểm tra kết quả sau cài đặt trên hệ điều hành mục tiêu; application image đơn thuần không đảm bảo hệ điều hành đã đăng ký liên kết file.

Tùy chọn `--resource-dir` dành cho trường hợp cần thay icon, template hoặc resource đóng gói mặc định. Chỉ dùng khi thực sự cần tùy biến giao diện installer; giữ cấu trúc resource tương thích với phiên bản jpackage đang dùng.

## 12. Kiểm tra đầu ra và chẩn đoán

Sau khi đóng gói, không nên chỉ kiểm tra lệnh jpackage đã kết thúc thành công. Hãy kiểm tra toàn bộ sản phẩm:

1. Application image có launcher và thư mục runtime.
2. Payload có JAR, dependency và resource cần thiết.
3. Launcher chạy được từ thư mục đầu ra.
4. Ứng dụng hoạt động khi không dựa vào JDK cài trên máy build.
5. Installer cài đặt, khởi chạy và gỡ cài đặt đúng.
6. Phiên bản, icon, shortcut và file association hiển thị đúng.

Một số lệnh kiểm tra:

~~~powershell
jpackage --version
jpackage --help
jar --list --file input\hello.jar
Get-ChildItem -Recurse output
~~~

Nếu launcher không chạy, kiểm tra file cấu hình trong thư mục app, runtime đi kèm, main class và dependency. Nếu lỗi xuất hiện khi nạp lớp, kiểm tra manifest Class-Path hoặc module path trước khi kết luận runtime bị thiếu.

Khi cần giữ lại tệp trung gian để điều tra, có thể dùng `--temp` trỏ đến một thư mục mới hoặc rỗng. Nếu chỉ định `--temp`, thư mục tạm sẽ được giữ lại sau khi đóng gói và người thực hiện phải tự dọn dẹp khi không còn cần.

## 13. Lỗi thường gặp và cách xử lý

### jpackage không được nhận diện

Nguyên nhân thường là đang dùng JRE thay vì JDK, hoặc thư mục bin của JDK chưa có trong PATH. Kiểm tra `java -version`, `jpackage --version` và đường dẫn thực tế của công cụ. Có thể gọi jpackage bằng đường dẫn đầy đủ đến thư mục bin của JDK.

### Main class không tìm thấy

Với ứng dụng không modular, xác nhận JAR chính có manifest Main-Class hợp lệ hoặc cung cấp `--main-class`. Tên lớp phải đầy đủ package và không có phần mở rộng `.class`.

Với ứng dụng modular, xác nhận tên module và lớp main trong `--module` chính xác, đồng thời module nằm trên `--module-path`.

### Thiếu dependency lúc chạy

jpackage có thể đóng gói file trong input nhưng không tự giải quyết toàn bộ dependency của dự án. Kiểm tra các JAR phụ thuộc có được đưa vào payload và được tham chiếu đúng qua manifest Class-Path hay module path. Chạy thử application image trong môi trường sạch để phát hiện dependency vô tình lấy từ máy build.

### jlink không tạo được runtime

Có thể module path thiếu dependency, module name sai hoặc module graph không resolve được. Kiểm tra bằng `jdeps`, `java --list-modules` và `jlink --list-plugins` khi cần. Bảo đảm các module native hoặc module đặc thù đã được đưa vào runtime.

### Installer không tạo được

Nguyên nhân thường do thiếu công cụ đóng gói native, sai định dạng icon, metadata không hợp lệ hoặc tùy chọn chỉ hỗ trợ trên hệ điều hành khác. Đọc thông báo lỗi cụ thể, kiểm tra `jpackage --help` trên máy build và cài các công cụ nền tảng cần thiết.

### Gói chạy trên máy build nhưng lỗi trên máy khác

Có thể application image đang thiếu runtime, dependency hoặc resource. Kiểm thử trên máy không có JDK, cùng hệ điều hành và kiến trúc với người dùng mục tiêu. Đừng chỉ chạy JAR bằng lệnh `java -jar` rồi kết luận installer đã đúng.

### Kích thước gói quá lớn

Runtime mặc định có thể chứa nhiều module hơn ứng dụng cần. Xác định dependency module, sau đó tinh giản bằng `--add-modules` hoặc tạo runtime riêng bằng jlink. Sau khi tinh giản, chạy toàn bộ luồng ứng dụng để phát hiện module bị thiếu.

## 14. Quy trình phát hành khuyến nghị

Một quy trình thực tế có thể chia thành các bước:

1. Biên dịch và kiểm thử ứng dụng bằng JDK mục tiêu.
2. Chuẩn bị thư mục input chứa JAR, dependency và resource.
3. Tạo application image bằng `--type app-image`.
4. Chạy launcher trong môi trường sạch, không phụ thuộc JDK của máy build.
5. Kiểm tra runtime, log, icon và cấu hình.
6. Tạo native installer trên nền tảng mục tiêu bằng `--app-image` hoặc đóng gói trực tiếp.
7. Kiểm thử cài đặt, nâng cấp, khởi chạy và gỡ cài đặt.
8. Ký mã theo quy trình của hệ điều hành nếu sản phẩm yêu cầu.
9. Lưu artifact, checksum, phiên bản JDK và cấu hình build để tái lập bản phát hành.

jpackage tạo gói phân phối; nó không tự cung cấp hệ thống cập nhật ứng dụng, quản lý dependency lúc chạy hoặc thay thế quy trình ký và phát hành của tổ chức.

## 15. Checklist trước khi giao ứng dụng

- [ ] Đã kiểm tra phiên bản JDK và tùy chọn bằng `jpackage --version` và `jpackage --help`.
- [ ] Đã chọn đúng chế độ `app-image` hoặc installer.
- [ ] Đã chọn đúng `--main-jar` hoặc `--module`.
- [ ] Main-Class hoặc module main đã được xác định chính xác.
- [ ] Dependency và resource cần thiết đã được đưa vào payload.
- [ ] Runtime image có đủ module và phù hợp nền tảng mục tiêu.
- [ ] Đã kiểm thử launcher trên máy không có JDK cài sẵn.
- [ ] Đã kiểm tra metadata, icon, version và shortcut.
- [ ] Đã tạo installer trên đúng hệ điều hành và kiến trúc.
- [ ] Đã kiểm thử cài đặt, chạy, nâng cấp và gỡ cài đặt.
- [ ] Đã ký ứng dụng/gói cài đặt nếu yêu cầu.
- [ ] Đã lưu checksum và thông tin build để tái lập artifact.
