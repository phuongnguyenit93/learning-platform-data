# Đóng gói ứng dụng Java bằng jpackage

**`jpackage`** là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc bộ cài native phù hợp với hệ điều hành đích. Gói tạo ra có thể chứa launcher, các tệp ứng dụng, dependency và một runtime Java riêng, nhờ đó người dùng có thể cài đặt hoặc chạy ứng dụng mà không cần tự cài JDK đầy đủ.

`jpackage` được đưa vào JDK từ Java 14 ở dạng incubator và trở thành công cụ chính thức từ JDK 16. Hướng dẫn này sử dụng cú pháp phổ biến của JDK 17 trở lên; tùy chọn cụ thể có thể thay đổi giữa các phiên bản và nền tảng, vì vậy hãy kiểm tra `jpackage --help` của JDK đang dùng.

## 1. jpackage giải quyết vấn đề gì?

Thông thường, để chạy một ứng dụng Java, người dùng cần có runtime Java tương thích, biết cách đặt classpath/module path và tự chạy lệnh `java`. Điều này có thể gây khó khăn khi phân phối ứng dụng cho người dùng cuối.

`jpackage` tự động hóa nhiều công việc đóng gói:

- Tạo launcher để khởi chạy ứng dụng bằng tên dễ nhận biết.
- Đưa JAR, tài nguyên và dependency vào application image.
- Tạo hoặc sử dụng runtime image riêng cho ứng dụng.
- Tạo bộ cài native theo hệ điều hành.
- Ghi metadata như tên, phiên bản, nhà cung cấp và mô tả.
- Hỗ trợ biểu tượng ứng dụng, tùy chọn JVM, đối số mặc định và launcher bổ sung.

Quy trình tổng quát:

```text
Java source code
      |
      | javac / build tool
      v
JAR hoặc modular application
      |
      | jpackage
      v
Application image
      |
      | jpackage --type msi / dmg / deb / ...
      v
Native installer
      |
      v
Người dùng cài đặt và chạy ứng dụng
```

`jpackage` thực hiện đóng gói, không thay thế bước biên dịch mã nguồn. Trước khi chạy công cụ, bạn cần chuẩn bị JAR, module hoặc artifact ứng dụng đã build thành công.

## 2. Application image và native installer

`jpackage` có hai nhóm đầu ra chính.

**Application image (`app-image`)** là thư mục ứng dụng đã đóng gói. Nó thường chứa launcher, các tệp ứng dụng và runtime cần thiết. Có thể chạy thử image trước khi tạo bộ cài.

**Native installer** là gói cài đặt theo nền tảng, có thể tích hợp với trình cài đặt và cơ chế quản lý phần mềm của hệ điều hành.

| Hệ điều hành | Application image | Native installer thường dùng |
| --- | --- | --- |
| Windows | Thư mục ứng dụng có launcher `.exe` | `.exe`, `.msi` |
| macOS | Bundle `.app` | `.dmg`, `.pkg` |
| Linux | Thư mục ứng dụng có launcher | `.deb`, `.rpm` |

Định dạng được hỗ trợ phụ thuộc nền tảng và JDK. Không phải mọi loại gói đều có thể tạo trên mọi hệ điều hành.

Nên tạo và kiểm thử `app-image` trước. Khi launcher, runtime và dependency hoạt động đúng, mới tạo installer cho người dùng.

## 3. Kiểm tra jpackage và môi trường

Mở terminal và chạy:

```bash
jpackage --version
jpackage --help
```

Nếu không nhận diện được lệnh:

- Kiểm tra máy đã cài JDK 16 trở lên.
- Kiểm tra thư mục `bin` của JDK có trong `PATH`.
- Kiểm tra `JAVA_HOME` trỏ đến thư mục gốc của JDK.
- Mở terminal mới sau khi cập nhật biến môi trường.

Có thể gọi trực tiếp `jpackage` từ thư mục `bin` của JDK. Để tạo runtime image mặc định, công cụ sử dụng `jlink`; vì vậy JDK cần có các công cụ và module cần thiết cho quá trình liên kết.

**Đóng gói theo nền tảng:** `jpackage` tạo gói cho nền tảng mà nó đang chạy. Hãy build installer trên hệ điều hành đích và chọn đúng kiến trúc CPU, chẳng hạn x64 hoặc ARM64. Không coi một gói Windows, macOS và Linux là các artifact có thể tạo chéo tùy ý từ cùng một máy build.

## 4. Các tùy chọn jpackage thường dùng

| Tùy chọn | Công dụng |
| --- | --- |
| `--type` | Chọn loại đầu ra như `app-image`, `msi`, `exe`, `dmg`, `pkg`, `deb` hoặc `rpm` tùy nền tảng |
| `--name` | Tên ứng dụng và launcher |
| `--dest` | Thư mục chứa artifact đầu ra |
| `--input` | Thư mục chứa JAR và tài nguyên đầu vào cho ứng dụng classpath |
| `--main-jar` | JAR chính, tính tương đối từ thư mục `--input` |
| `--main-class` | Lớp chứa phương thức main |
| `--module-path` | Nơi tìm các module cho ứng dụng modular |
| `--module` | Module khởi chạy, có thể kèm tên lớp chính |
| `--runtime-image` | Runtime image đã được tạo sẵn, thường bằng `jlink` |
| `--app-version` | Phiên bản ứng dụng |
| `--vendor` | Nhà cung cấp ứng dụng |
| `--description` | Mô tả ứng dụng |
| `--icon` | Biểu tượng ứng dụng theo định dạng nền tảng hỗ trợ |
| `--java-options` | Tùy chọn truyền cho JVM khi launcher chạy |
| `--arguments` | Đối số mặc định truyền cho ứng dụng |
| `--add-launcher` | Khai báo thêm launcher với cấu hình riêng |
| `--resource-dir` | Thư mục chứa tài nguyên tùy chỉnh cho trình đóng gói |
| `--add-modules` | Chỉ định các module bổ sung cho runtime image |
| `--jlink-options` | Tùy chọn bổ sung truyền cho `jlink` khi tạo runtime image |

Không phải mọi tùy chọn đều dùng được với mọi loại gói. Chạy `jpackage --help` trên hệ điều hành đích để xem tùy chọn nền tảng và định dạng được hỗ trợ.

## 5. Chuẩn bị ứng dụng Java dạng JAR

Ví dụ này tạo một ứng dụng classpath đơn giản để đóng gói thành application image.

Cấu trúc dự án:

```text
project/
  src/
    com/
      example/
        Main.java
  out/
  input/
  dist/
```

Tạo tệp **`src/com/example/Main.java`**:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from packaged Java app");

        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "]=" + args[i]);
        }
    }
}
```

Tạo các thư mục đầu ra nếu chúng chưa tồn tại.

**Windows PowerShell:**

```powershell
New-Item -ItemType Directory -Force out, input, dist | Out-Null
```

**macOS/Linux:**

```bash
mkdir -p out input dist
```

Biên dịch mã nguồn:

```bash
javac -d out src/com/example/Main.java
```

Đóng gói thành JAR:

```bash
jar --create --file input/hello.jar --main-class com.example.Main -C out .
```

Trong ví dụ, JAR đã có thuộc tính `Main-Class`; khi chạy `jpackage`, ta cũng sẽ chỉ định lớp chính rõ ràng để lệnh đóng gói dễ đọc và dễ kiểm tra.

Kiểm tra JAR trước khi đóng gói:

```bash
jar --list --file input/hello.jar
```

Danh sách cần có lớp:

```text
com/example/Main.class
```

## 6. Tạo application image với --type app-image

Tại thư mục gốc `project`, chạy:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --dest dist
```

Giải thích:

- `--type app-image`: tạo application image.
- `--input input`: lấy JAR và tài nguyên trong thư mục `input`.
- `--name HelloApp`: đặt tên ứng dụng.
- `--main-jar hello.jar`: chọn JAR chính trong thư mục input.
- `--main-class com.example.Main`: chỉ định lớp khởi chạy.
- `--app-version 1.0.0`: gắn phiên bản ứng dụng.
- `--vendor "Example"`: ghi tên nhà cung cấp.
- `--dest dist`: ghi image vào thư mục `dist`.

Với ứng dụng classpath, các JAR khác đặt trong thư mục `input` cũng được đóng gói để làm dependency. Hãy giữ đúng cấu trúc và tên tệp mà ứng dụng cần.

`jpackage` tạo runtime image cho ứng dụng nếu bạn không truyền `--runtime-image`. Runtime đi kèm giúp ứng dụng chạy bằng môi trường Java đã được đóng gói, giảm phụ thuộc vào Java cài đặt toàn hệ thống của người dùng.

## 7. Chạy thử application image

Đường dẫn launcher phụ thuộc hệ điều hành.

**Windows PowerShell:**

```powershell
.\dist\HelloApp\HelloApp.exe
```

**macOS:**

```bash
./dist/HelloApp.app/Contents/MacOS/HelloApp
```

Có thể mở bundle bằng Finder hoặc lệnh:

```bash
open dist/HelloApp.app
```

**Linux:**

```bash
./dist/HelloApp/bin/HelloApp
```

Khi chạy ví dụ không truyền đối số, kết quả trên terminal là:

```text
Hello from packaged Java app
```

Application image có thể chứa runtime riêng, launcher và thư mục ứng dụng. Không cần gọi trực tiếp `java -cp` như lúc chạy JAR thủ công; launcher được tạo bởi `jpackage` đã cấu hình để khởi chạy ứng dụng.

Trên Windows, nếu ứng dụng là chương trình console và cần hiển thị stdout/stderr trong cửa sổ terminal, dùng tùy chọn `--win-console` khi tạo image. Ứng dụng GUI thường không cần tùy chọn này.

## 8. Đóng gói dependency bên ngoài

Nếu ứng dụng sử dụng thêm thư viện JAR, đặt chúng trong thư mục input cùng với JAR chính.

Ví dụ:

```text
input/
  hello.jar
  lib/
    helper.jar
    logging.jar
```

Đường dẫn và classpath của ứng dụng phải khớp với cách các dependency được đóng gói. Với ứng dụng classpath, có thể cấu hình classpath của JAR chính trong manifest hoặc build artifact theo đúng cấu trúc mà launcher sử dụng.

Một cách phổ biến là đóng gói tất cả JAR dependency vào input directory theo quy ước của dự án và xác nhận launcher tìm được chúng sau khi tạo image.

Nếu dự án dùng Maven hoặc Gradle, nên tạo thư mục phân phối chứa JAR chính và các dependency runtime bằng task build riêng. Sau đó dùng thư mục đó làm `--input`. Điều này giúp quá trình đóng gói có thể lặp lại và tránh lấy nhầm thư viện chỉ có trong máy phát triển.

**Kiểm tra:** nếu ứng dụng chạy được từ IDE nhưng lỗi `ClassNotFoundException` sau khi đóng gói, hãy kiểm tra dependency runtime đã được đưa vào artifact và launcher có tham chiếu đúng vị trí chưa.

## 9. Đóng gói ứng dụng modular

Với ứng dụng dùng JPMS, có thể chỉ định module path và module khởi chạy thay cho `--input` và `--main-jar`.

Ví dụ, giả sử đã biên dịch module `com.example.app` vào thư mục `mods`:

```text
mods/
  com.example.app/
    module-info.class
    com/example/app/Main.class
```

Tạo application image:

```bash
jpackage --type app-image --name ModularApp --module-path mods --module com.example.app/com.example.app.Main --dest dist
```

Trong đó:

- `--module-path mods` chỉ nơi chứa các module đã biên dịch và dependency modular.
- `--module com.example.app/com.example.app.Main` chỉ định module và lớp main.
- `--name ModularApp` đặt tên launcher.
- `--dest dist` đặt nơi lưu application image.

Module descriptor cần khai báo đúng `requires`, `exports`, `uses` và `provides` theo thiết kế ứng dụng. Tất cả module phụ thuộc phải có thể được phân giải trên module path.

Với ứng dụng modular phức tạp, hãy kiểm tra đồ thị module bằng công cụ `java`, `jdeps` và `jlink` trước khi đóng gói.

## 10. Tạo runtime image riêng bằng jlink

Mặc định, `jpackage` tạo runtime image cho ứng dụng thông qua `jlink`. Nếu cần kiểm soát chính xác các module runtime hoặc đã có runtime image được kiểm thử, có thể tạo image trước rồi truyền vào `jpackage` bằng `--runtime-image`.

Ví dụ với module `com.example.app`:

**macOS/Linux:**

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output runtime
```

**Windows PowerShell:**

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output runtime
```

Sau khi tạo runtime image, kiểm tra:

```bash
runtime/bin/java --list-modules
```

Trên Windows:

```powershell
.\runtime\bin\java.exe --list-modules
```

Truyền runtime vào jpackage:

```bash
jpackage --type app-image --name ModularApp --module-path mods --module com.example.app/com.example.app.Main --runtime-image runtime --dest dist
```

Khi dùng `--runtime-image`, `jpackage` sử dụng runtime image đã cung cấp. Hãy bảo đảm image chứa đầy đủ module mà ứng dụng cần, có đúng kiến trúc và được tạo bằng toolchain tương thích với môi trường đích.

## 11. Truyền tùy chọn JVM và đối số ứng dụng

Có thể cấu hình launcher để luôn truyền một số tùy chọn cho JVM hoặc đối số cho ứng dụng.

Ví dụ:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --java-options "-Dapp.mode=production" --java-options "-Xmx512m" --arguments "first-run" --dest dist
```

Ý nghĩa:

- `--java-options "-Dapp.mode=production"`: đặt system property cho JVM.
- `--java-options "-Xmx512m"`: đặt giới hạn heap tối đa.
- `--arguments "first-run"`: truyền đối số mặc định cho ứng dụng khi launcher chạy.

Trong chương trình Java, đối số mặc định có thể đọc qua `args` trong `main(String[] args)`. Nếu người dùng truyền thêm đối số lúc chạy, hãy kiểm tra cách launcher của nền tảng kết hợp đối số đó với cấu hình mặc định.

Không đưa mật khẩu, token hoặc bí mật vào `--java-options`, `--arguments` hay file cấu hình launcher vì các giá trị này có thể được lưu trong artifact và có thể đọc được.

## 12. Tạo native installer trên Windows

Trên Windows, `jpackage` có thể tạo gói `.exe` hoặc `.msi`. Các định dạng installer này cần công cụ đóng gói Windows tương ứng; JDK yêu cầu WiX Toolset tương thích để tạo các gói installer.

Ví dụ tạo MSI:

```powershell
jpackage --type msi --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --win-menu --win-shortcut --win-dir-chooser --win-console --dest dist
```

Một số tùy chọn Windows:

| Tùy chọn | Công dụng |
| --- | --- |
| `--win-menu` | Tạo shortcut trong Start Menu |
| `--win-shortcut` | Tạo shortcut trên desktop |
| `--win-menu-group` | Chọn nhóm Start Menu |
| `--win-dir-chooser` | Cho phép chọn thư mục cài đặt |
| `--win-console` | Tạo launcher có console |
| `--win-per-user-install` | Cấu hình cài đặt theo người dùng |
| `--win-upgrade-uuid` | Định danh để quản lý nâng cấp MSI |

Để tạo gói EXE, đổi `--type msi` thành `--type exe` nếu JDK và môi trường Windows hỗ trợ định dạng đó.

Trước khi phát hành, kiểm thử cài đặt, chạy, nâng cấp và gỡ cài đặt trên máy Windows sạch. Với ứng dụng phân phối rộng, hãy ký số installer và kiểm tra danh tính nhà phát hành theo quy trình phát hành của tổ chức.

## 13. Tạo native installer trên macOS

Trên macOS, `jpackage` hỗ trợ các định dạng như `.dmg` và `.pkg`.

Ví dụ tạo DMG:

```bash
jpackage --type dmg --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --mac-package-identifier com.example.hello --dest dist
```

Ví dụ tạo PKG:

```bash
jpackage --type pkg --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --mac-package-identifier com.example.hello --dest dist
```

Một số tùy chọn macOS:

- `--mac-package-identifier`: bundle identifier theo dạng reverse DNS, ví dụ `com.example.hello`.
- `--mac-package-name`: tên hiển thị của package khi phù hợp.
- `--mac-package-signing-prefix`: tiền tố identifier dùng trong quá trình ký.
- `--mac-sign`: yêu cầu ký ứng dụng/package bằng danh tính ký phù hợp.
- `--mac-signing-key-user-name`: danh tính ký được chọn.
- `--mac-signing-keychain`: keychain chứa chứng chỉ.
- `--mac-entitlements`: tệp entitlements cho quá trình ký khi cần.

Tùy quy trình phân phối, ứng dụng macOS có thể cần code signing và notarization. Việc tạo DMG/PKG thành công không tự chứng minh artifact đã đáp ứng yêu cầu Gatekeeper hoặc chính sách phân phối của Apple. Hãy ký, notarize, staple và kiểm tra artifact theo quy trình phát hành phù hợp.

## 14. Tạo native installer trên Linux

Trên Linux, `jpackage` có thể tạo gói `.deb` hoặc `.rpm`, tùy công cụ đóng gói có sẵn trên hệ thống.

Ví dụ tạo DEB:

```bash
jpackage --type deb --input input --name helloapp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --linux-package-name helloapp --linux-shortcut --dest dist
```

Ví dụ tạo RPM:

```bash
jpackage --type rpm --input input --name helloapp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --linux-package-name helloapp --linux-shortcut --dest dist
```

Một số tùy chọn Linux:

| Tùy chọn | Công dụng |
| --- | --- |
| `--linux-package-name` | Tên gói |
| `--linux-deb-maintainer` | Thông tin maintainer của gói DEB |
| `--linux-package-deps` | Các dependency package hệ thống |
| `--linux-app-release` | Release number của package |
| `--linux-app-category` | Nhóm ứng dụng |
| `--linux-shortcut` | Tạo shortcut desktop khi được hỗ trợ |
| `--linux-rpm-license-type` | Loại giấy phép cho gói RPM |

Để tạo DEB, máy build cần các công cụ đóng gói Debian tương ứng; để tạo RPM, cần công cụ build RPM. Hãy cài công cụ phù hợp với bản phân phối và kiểm tra yêu cầu của JDK đang sử dụng.

Kiểm thử gói trên bản phân phối Linux mục tiêu. Package dependency của hệ điều hành, thư viện native và kiến trúc CPU có thể khiến một gói hoạt động trên máy build nhưng lỗi trên máy khác.

## 15. Tạo launcher bổ sung bằng --add-launcher

Một ứng dụng có thể cần nhiều launcher với cấu hình khác nhau, ví dụ launcher mặc định và launcher chạy ở chế độ quản trị hoặc chẩn đoán.

Tạo tệp cấu hình **`admin-launcher.properties`**:

```properties
module=com.example.app/com.example.app.Main
java-options=-Dapp.mode=admin
arguments=--admin
```

Với ứng dụng modular, truyền tệp cấu hình cho `--add-launcher`:

```bash
jpackage --type app-image --name MainApp --module-path mods --module com.example.app/com.example.app.Main --add-launcher Admin=admin-launcher.properties --dest dist
```

`Admin` là tên launcher bổ sung. Cấu hình launcher có thể khai báo module hoặc JAR entry point cùng các tùy chọn JVM và đối số mặc định phù hợp với loại ứng dụng.

Cú pháp và các khóa được hỗ trợ phụ thuộc phiên bản JDK; hãy xem phần `--add-launcher` trong `jpackage --help`. Không sao chép cấu hình của ứng dụng modular sang ứng dụng classpath nếu chưa thay các khóa entry point cho phù hợp.

## 16. Icon, metadata và tài nguyên tùy chỉnh

Có thể thêm biểu tượng và thông tin nhận diện vào package:

```bash
jpackage --type app-image --input input --name HelloApp --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example" --description "Example Java application" --icon icons/hello.ico --dest dist
```

Định dạng icon phụ thuộc hệ điều hành. Ví dụ, Windows thường dùng `.ico`, macOS dùng `.icns`; Linux hỗ trợ định dạng ảnh phù hợp với môi trường desktop. Dùng đúng định dạng được nền tảng và phiên bản JDK hỗ trợ.

`--resource-dir` cho phép cung cấp tài nguyên tùy chỉnh cho trình đóng gói, chẳng hạn template hoặc resource nền tảng. Chỉ dùng khi cần thay đổi tài nguyên mặc định và kiểm tra tên file mà JDK đang yêu cầu.

Metadata nên nhất quán với tên ứng dụng, phiên bản phát hành, nhà cung cấp và identifier. Tránh dùng tên hoặc identifier thay đổi tùy tiện giữa các bản nâng cấp nếu nền tảng sử dụng chúng để nhận diện ứng dụng đã cài.

## 17. Kiểm tra artifact sau khi đóng gói

Sau khi tạo image hoặc installer, cần xác nhận artifact có thể sử dụng trong môi trường sạch.

Các bước kiểm tra:

1. Xác nhận lệnh `jpackage` kết thúc thành công và artifact xuất hiện trong thư mục `--dest`.
2. Kiểm tra launcher và runtime được tạo.
3. Chạy ứng dụng từ application image, không dựa vào JDK cài toàn hệ thống.
4. Kiểm tra chức năng chính, file cấu hình, tài nguyên, logging và dependency.
5. Cài native installer trên máy thử nghiệm hoặc máy ảo sạch.
6. Xác nhận shortcut, menu, đường dẫn cài đặt, quyền truy cập và gỡ cài đặt.
7. Kiểm tra cập nhật/nâng cấp giữa hai phiên bản nếu installer hỗ trợ.
8. Kiểm tra chữ ký số và metadata trước khi phát hành.

Một bài test đơn giản là chạy ứng dụng trên máy không cài JDK riêng. Nếu app-image hoạt động, điều đó cho thấy runtime đi kèm đã đủ cho đường chạy được kiểm tra. Vẫn cần kiểm thử toàn bộ tính năng và dependency native của ứng dụng.

## 18. Lỗi thường gặp khi dùng jpackage

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `jpackage` không được nhận diện | Chưa cài JDK phù hợp hoặc `PATH` chưa đúng | Kiểm tra `JAVA_HOME` và thư mục `bin` |
| Không tìm thấy main JAR | Tên `--main-jar` không đúng hoặc không nằm trong `--input` | Kiểm tra đường dẫn tương đối và nội dung input directory |
| Không tìm thấy main class | Sai package/class name hoặc class file không có trong JAR | Kiểm tra manifest, `--main-class` và `jar --list` |
| Ứng dụng chạy trong IDE nhưng lỗi trong image | Thiếu runtime dependency hoặc tài nguyên | Đóng gói đầy đủ dependency và kiểm thử lại image |
| Runtime thiếu module | Runtime image không có module ứng dụng cần | Kiểm tra `--add-modules`, module path hoặc tạo runtime bằng jlink |
| Không tạo được MSI/EXE | Thiếu hoặc sai phiên bản WiX Toolset | Cài WiX tương thích và kiểm tra cấu hình môi trường |
| Không tạo được DEB/RPM | Thiếu công cụ đóng gói của Linux | Cài công cụ tương ứng và kiểm tra yêu cầu của JDK |
| Installer tạo được nhưng không cài trên máy khác | Khác kiến trúc, thư viện native, phiên bản OS hoặc package dependency | Build và kiểm thử trên nền tảng đích |
| macOS cảnh báo ứng dụng chưa xác minh | Artifact chưa ký/notarize theo chính sách phân phối | Thực hiện code signing và notarization phù hợp |
| Artifact đầu ra đã tồn tại | Thư mục đích có sản phẩm trùng tên | Dùng thư mục đích mới hoặc quản lý artifact cũ theo quy trình build |

Khi chẩn đoán, hãy giữ lại log lệnh đầy đủ và kiểm tra đầu ra của `jpackage --help` trên đúng JDK. Một tùy chọn có thể được hỗ trợ trên nền tảng này nhưng không có trên nền tảng khác.

## 19. Thực hành tốt khi đóng gói và phát hành

- Build ứng dụng bằng quy trình có thể tái lập, chẳng hạn Maven hoặc Gradle.
- Tách artifact đầu vào khỏi thư mục đầu ra của jpackage.
- Tạo `app-image` và kiểm thử trước khi tạo installer.
- Đóng gói dependency runtime và tài nguyên cần thiết.
- Dùng runtime image tối thiểu đã được kiểm thử khi muốn kiểm soát module đi kèm.
- Ghi rõ phiên bản JDK, hệ điều hành, kiến trúc và loại package trong quy trình phát hành.
- Tạo installer trên hệ điều hành đích.
- Ký số ứng dụng và installer theo chính sách của nền tảng.
- Kiểm thử cài đặt, chạy, nâng cấp và gỡ cài đặt trên môi trường sạch.
- Không nhúng bí mật vào manifest, launcher properties hoặc tùy chọn JVM.
- Lưu artifact và checksum theo quy trình phát hành để có thể truy vết bản đã phân phối.

## 20. Ghi nhớ

- `jpackage` đóng gói ứng dụng Java thành application image hoặc native installer.
- Cần build JAR hoặc module trước; `jpackage` không biên dịch mã nguồn Java.
- Dùng `--input` và `--main-jar` cho ứng dụng classpath; dùng `--module-path` và `--module` cho ứng dụng modular.
- `--type app-image` hữu ích để kiểm thử trước khi tạo installer.
- Nếu không truyền `--runtime-image`, `jpackage` tạo runtime image cho ứng dụng; có thể dùng `jlink` để kiểm soát runtime riêng.
- Định dạng installer phụ thuộc nền tảng: Windows `.msi`/`.exe`, macOS `.dmg`/`.pkg`, Linux `.deb`/`.rpm`.
- Cần công cụ đóng gói nền tảng tương ứng và build trên hệ điều hành đích.
- Luôn kiểm thử artifact trên môi trường sạch trước khi phát hành.

Khi nắm được quy trình build artifact → tạo application image → tạo native installer → kiểm thử và ký phát hành, bạn có thể phân phối ứng dụng Java với launcher và runtime phù hợp cho người dùng cuối.
