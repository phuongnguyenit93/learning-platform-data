# Cập nhật runtime được phân phối cùng ứng dụng

## 1. Vì sao ứng dụng cần phân phối runtime riêng?

Một ứng dụng Java cần có JVM và các module nền tảng tương thích để chạy. Nếu yêu cầu người dùng tự cài Java, ứng dụng phụ thuộc vào runtime có sẵn trên máy:

- Người dùng có thể chưa cài Java.
- Phiên bản Java trên máy có thể quá cũ hoặc quá mới so với ứng dụng.
- Hai máy có thể dùng JDK vendor, patch level hoặc cấu hình khác nhau.
- Nâng cấp Java của hệ điều hành có thể làm thay đổi runtime mà ứng dụng đang sử dụng.
- Hỗ trợ người dùng khó hơn vì lỗi có thể chỉ xuất hiện trên một cấu hình Java cụ thể.

Với ứng dụng desktop, công cụ nội bộ hoặc service được triển khai theo image, việc phân phối một runtime riêng giúp kiểm soát phiên bản Java và các module nền tảng mà ứng dụng cần.

Trong Java 17, các công cụ chính để tạo và đóng gói runtime là:

- **jlink:** tạo runtime image tùy chỉnh từ các module của JDK và ứng dụng.
- **jpackage:** đóng gói ứng dụng thành application image hoặc installer phù hợp hệ điều hành.
- **jdeps:** phân tích dependency để hỗ trợ xác định các module JDK cần thiết.
- **java, jcmd, jar:** kiểm tra runtime, tiến trình và module của artifact.

Runtime image được phân phối cùng ứng dụng thường là một bản runtime riêng, có vòng đời cập nhật do đội phát triển ứng dụng quản lý. Khi có bản vá bảo mật Java 17, cần tạo lại runtime image từ JDK đã được cập nhật và phát hành phiên bản ứng dụng tương ứng. Cài đặt JDK mới trên máy build không tự cập nhật runtime đã được đóng gói và cài trên máy người dùng.

## 2. JDK, runtime image và ứng dụng Java

### 2.1. JDK và runtime image khác nhau

**JDK (Java Development Kit)** dành cho phát triển và vận hành, bao gồm runtime cùng các công cụ như:

- `java`: chạy ứng dụng.
- `javac`: biên dịch source.
- `jlink`: tạo runtime image.
- `jpackage`: đóng gói ứng dụng.
- `jdeps`: phân tích dependency.
- `jcmd`, `jstack`, `jmap`: chẩn đoán tiến trình.
- Các công cụ khác như `jar`, `keytool`.

**Runtime image** tạo bằng jlink chỉ chứa các module cần thiết để chạy ứng dụng và các file runtime liên quan. Thông thường image này không có compiler hoặc toàn bộ bộ công cụ phát triển.

Ví dụ cấu trúc runtime image:

~~~text
runtime/
├── bin/
│   └── java
├── conf/
├── legal/
├── lib/
│   ├── modules
│   └── security/
└── release
~~~

Tên file và cấu trúc chi tiết có thể khác theo nền tảng. Trên Windows, executable là `bin/java.exe`.

Runtime image có thể chứa ít module hơn JDK đầy đủ, giảm dung lượng phân phối và hạn chế những thành phần không cần thiết trong môi trường chạy.

### 2.2. Không cần phân phối compiler cho người dùng cuối

Ứng dụng đã được biên dịch thành class hoặc module thì người dùng cuối thường chỉ cần runtime để thực thi. Không nên đóng gói toàn bộ JDK chỉ vì ứng dụng cần lệnh `java`.

Một số hệ thống vận hành có thể cần công cụ chẩn đoán bổ sung. Hãy quyết định riêng theo nhu cầu hỗ trợ, thay vì mặc định đưa `javac`, toàn bộ toolchain và các module không dùng vào mọi bản phân phối.

### 2.3. Runtime đi cùng ứng dụng là một dependency có vòng đời

Khi đóng gói runtime riêng, đội phát triển chịu trách nhiệm:

- Chọn JDK vendor và bản cập nhật.
- Xác định module cần thiết.
- Kiểm thử trên OS và kiến trúc đích.
- Theo dõi bản vá bảo mật và lỗi runtime.
- Xây dựng lại runtime image khi nâng patch level.
- Phát hành installer/application image mới.
- Lưu thông tin phiên bản để hỗ trợ rollback và điều tra lỗi.

Không nên xem thư mục runtime là một file phụ có thể sao chép một lần rồi bỏ quên.

## 3. Hai cách phân phối runtime

### 3.1. Dùng runtime cài sẵn trên máy

Ứng dụng chạy bằng lệnh Java có sẵn trong PATH hoặc JAVA_HOME:

~~~shell
java -jar application.jar
~~~

Ưu điểm:

- Artifact ứng dụng nhỏ hơn.
- Người vận hành có thể quản lý JDK tập trung.
- Runtime được cập nhật qua quy trình quản lý phần mềm của máy chủ.

Nhược điểm:

- Phải cài đặt runtime trước.
- Cần xác định phiên bản tối thiểu và kiểm soát version drift.
- Môi trường người dùng có thể khác nhau.
- Việc nâng Java có thể ảnh hưởng nhiều ứng dụng dùng chung runtime.

Mô hình này phù hợp với server fleet hoặc container base image đã có quy trình quản lý JDK rõ ràng.

### 3.2. Đóng gói runtime riêng cùng ứng dụng

Ứng dụng mang theo runtime image trong application image hoặc installer:

~~~text
AcmeApp/
├── app/
│   ├── application.jar
│   └── lib/
├── runtime/
│   ├── bin/java
│   └── lib/
└── bin/
    └── acme-launcher
~~~

Ưu điểm:

- Người dùng không cần tự cài Java.
- Ứng dụng kiểm soát được runtime cụ thể.
- Có thể tối giản module JDK cần thiết.
- Các bản ứng dụng khác nhau có thể mang runtime riêng.

Nhược điểm:

- Kích thước gói cài đặt tăng.
- Nhà phát triển phải phát hành lại runtime khi có bản vá.
- Cần xây dựng artifact riêng cho từng hệ điều hành và kiến trúc.
- Cần kiểm thử native library, installer và runtime image trên nền tảng đích.

Mô hình này thường phù hợp với desktop application, công cụ phân phối cho khách hàng và sản phẩm cần trải nghiệm cài đặt độc lập.

## 4. jlink tạo runtime image tùy chỉnh

### 4.1. jlink hoạt động thế nào?

`jlink` liên kết các module đã biên dịch thành một runtime image. Nó lấy module từ module path, bao gồm JDK modules và các application modules tương thích, sau đó tạo image có thể chạy bằng launcher Java bên trong image.

Các input chính:

- Module path: nơi chứa JDK modules và application modules.
- Root modules: các module được chọn làm điểm bắt đầu.
- Module dependency graph: các module mà root modules cần đọc.
- Linker options: cách tối ưu hoặc bổ sung launcher.

Ví dụ đơn giản tạo runtime từ các module JDK:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/runtime
~~~

Image tạo ra chứa các module được yêu cầu và dependency cần thiết của chúng. Ví dụ trên chưa đưa application JAR lên runtime; ứng dụng có thể được chạy bằng classpath riêng cùng runtime image này.

### 4.2. jlink cần module, không đóng gói tùy ý mọi JAR classpath

`jlink` làm việc với module. Một JAR có `module-info.class` là explicit named module. JAR không có descriptor có thể là automatic module khi được đặt trên module path, nhưng automatic modules không phải input phù hợp để liên kết runtime image bằng jlink.

Vì vậy:

- Ứng dụng modular có thể đưa module ứng dụng và các module dependency phù hợp vào module path.
- Ứng dụng classpath vẫn có thể dùng runtime image tối giản chứa các JDK modules cần thiết; application JAR và dependency JAR được phân phối riêng trên classpath.
- Không đặt một thư viện classpath bất kỳ vào `--add-modules` với giả định jlink sẽ tự đóng gói nó thành module.

Nếu dependency chưa modular, có thể tiếp tục chạy nó trên classpath của ứng dụng. Không cần biến mọi JAR thành module chỉ để dùng một runtime image nhỏ.

### 4.3. Chọn module bằng --add-modules

`--add-modules` xác định các root modules mà jlink sẽ đưa vào image cùng dependency của chúng:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --output build/runtime
~~~

Không chọn module chỉ theo tên thư viện. Hãy xem ứng dụng dùng API nào và module tương ứng:

| API/chức năng | Module JDK thường liên quan |
|---|---|
| Core language, collections, I/O cơ bản | `java.base` |
| Logging API | `java.logging` |
| JDBC API | `java.sql` |
| XML API | `java.xml` |
| HTTP Client | `java.net.http` |
| Management API | `java.management` |
| Desktop AWT/Swing | `java.desktop` |
| Naming/Directory API | `java.naming` |
| Scripting API | `java.scripting` |
| Security APIs/provider bổ sung | Có thể cần module `jdk.*` tương ứng |

Đây là gợi ý định hướng; dependency graph của ứng dụng mới quyết định module thực sự cần. Một API có thể kéo theo module khác thông qua `requires`.

### 4.4. Phân tích dependency bằng jdeps

`jdeps` phân tích dependency bytecode và có thể in ra danh sách module JDK cần thiết:

~~~shell
jdeps --multi-release 17 --print-module-deps application.jar
~~~

Với ứng dụng classpath có dependency JAR:

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" application.jar
~~~

Output có thể dùng làm đầu vào cho `jlink --add-modules`. Trước khi sử dụng, cần kiểm tra:

- Dependency JAR có đầy đủ trên classpath phân tích không.
- Artifact có multi-release entries và target version phù hợp không.
- Có module được nạp qua reflection hoặc `ServiceLoader` mà jdeps không thể suy ra đầy đủ không.
- Có JNI/native library hoặc provider được nạp động không.

Phân tích tĩnh không thể luôn phát hiện module được nạp theo tên từ configuration hoặc reflection. Nếu ứng dụng dùng plugin, scripting, JDBC driver discovery, security provider hoặc ServiceLoader, cần kiểm thử các đường chạy đó và bổ sung module cần thiết.

### 4.5. jlink và ServiceLoader

Một ứng dụng có thể dùng service provider:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class);
~~~

Nếu provider nằm trong module khác, module graph cần chứa provider phù hợp. Tùy cấu trúc module và cách service được khai báo, option:

~~~shell
--bind-services
~~~

có thể giúp jlink liên kết các provider của service được dùng trong graph. Hãy kiểm tra service descriptor, `uses`, `provides` và chạy test thực tế; không mặc định một module provider sẽ được bao gồm chỉ vì class API của service xuất hiện trong bytecode.

## 5. Các tùy chọn jlink hữu ích

### 5.1. Giảm dung lượng runtime image

Một lệnh thường dùng:

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

Các tùy chọn:

| Option | Tác dụng |
|---|---|
| `--strip-debug` | Loại bỏ thông tin debug không cần thiết khỏi module image |
| `--no-header-files` | Không đưa native header files vào image |
| `--no-man-pages` | Không đưa man pages vào image |
| `--compress=2` | Nén resource trong image theo mức compression được hỗ trợ |
| `--bind-services` | Liên kết service provider phù hợp với service use trong module graph |
| `--limit-modules` | Giới hạn tập module observable trong quá trình resolution |
| `--launcher` | Tạo launcher script/executable cho module và main class |
| `--output` | Thư mục đích của runtime image |

Compression có thể giảm dung lượng nhưng ảnh hưởng thời gian đọc/giải nén resource. Đo trên ứng dụng và filesystem đích trước khi chọn.

### 5.2. Tạo launcher với --launcher

Với ứng dụng modular, có thể tạo launcher:

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher acme=com.acme.app/com.acme.app.Main --strip-debug --no-header-files --no-man-pages --output build/acme-runtime
~~~

Trong ví dụ:

- `mods` chứa module ứng dụng và các module dependency.
- `com.acme.app` là module root.
- `com.acme.app.Main` là main class.
- `acme` là tên launcher được tạo trong runtime image.

Trên Windows, module path dùng dấu phân cách `;`; trên Linux/macOS dùng `:`. Hãy tạo image trên đúng nền tảng và kiểm tra launcher trong thư mục `bin`.

### 5.3. Không loại module theo phỏng đoán

Một runtime quá nhỏ có thể chạy được màn hình đầu tiên nhưng lỗi khi đi vào một chức năng hiếm:

- TLS hoặc cipher provider cần module crypto.
- JDBC driver được nạp động.
- Locale ngoài tập mặc định.
- XML parser hoặc scripting engine.
- Desktop toolkit.
- Logging handler hoặc service provider.
- Code gọi reflection tới một API/module ít dùng.

Hãy kiểm tra các chức năng đại diện và các feature được bật bằng configuration. Nếu không chắc, bắt đầu với tập module lớn hơn rồi giảm dần dựa trên phân tích và test, thay vì xóa module ngẫu nhiên.

### 5.4. Locale data

JDK tách một phần locale data thành module riêng như `jdk.localedata`. Nếu ứng dụng cần locale cụ thể, cần đảm bảo runtime image có dữ liệu đó.

Tùy chọn `--include-locales` có thể giới hạn locale data khi module liên quan được đưa vào image:

~~~shell
--add-modules jdk.localedata --include-locales=en,vi
~~~

Chỉ giới hạn locale khi đã kiểm tra format ngày, số, tiền tệ, collation và resource bundle của ứng dụng. Thiếu locale data có thể khiến ứng dụng hiển thị fallback hoặc không có hành vi mong đợi ở một ngôn ngữ.

### 5.5. Xem plugin mà jlink hỗ trợ

Các plugin có thể khác theo JDK vendor/build. Dùng:

~~~shell
jlink --list-plugins
~~~

Không sao chép option của JDK mới hơn vào pipeline Java 17 mà không kiểm tra. Build cần chạy với đúng JDK toolchain đã chọn.

## 6. Tạo runtime cho ứng dụng modular

### 6.1. Cấu trúc module mẫu

~~~text
project/
├── src/
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

Module descriptor:

~~~java
module com.acme.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.acme.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOG.info("Application started");
    }
}
~~~

### 6.2. Biên dịch module

~~~shell
javac --release 17 --module-source-path src -d mods -m com.acme.app
~~~

### 6.3. Chạy thử trên JDK đầy đủ

~~~shell
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Đây là bước xác nhận module hoạt động trước khi tạo runtime riêng. Nếu ứng dụng không chạy trên JDK đầy đủ thì runtime image tối giản cũng không sửa được lỗi ứng dụng.

### 6.4. Liên kết runtime image

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher acme=com.acme.app/com.acme.app.Main --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

### 6.5. Chạy bằng runtime image

~~~shell
build/runtime/bin/acme
~~~

Hoặc gọi launcher Java và module trực tiếp:

~~~shell
build/runtime/bin/java -m com.acme.app/com.acme.app.Main
~~~

Nếu chạy được bằng JDK đầy đủ nhưng không chạy bằng runtime image, kiểm tra module graph, service provider, locale, security provider và các module được nạp động.

## 7. Tạo runtime cho ứng dụng classpath

Không phải ứng dụng nào cũng đã modular. Một ứng dụng có thể vẫn dùng:

~~~shell
java -cp "app.jar:lib/*" com.acme.Main
~~~

Có thể đóng gói runtime JDK tối giản cho ứng dụng classpath bằng cách liên kết các module JDK cần thiết, rồi phân phối application JAR và dependencies riêng.

### 7.1. Phân tích JDK module dependencies

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" app.jar
~~~

Giả sử output là:

~~~text
java.base,java.logging,java.sql
~~~

Đây là output minh họa. Danh sách thực tế phụ thuộc bytecode và classpath của ứng dụng.

### 7.2. Tạo runtime chỉ chứa JDK modules

~~~shell
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.base,java.logging,java.sql --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

### 7.3. Phân phối app và dependency riêng

~~~text
distribution/
├── runtime/
├── app/
│   ├── app.jar
│   └── lib/
│       ├── dependency-a.jar
│       └── dependency-b.jar
└── launch.sh
~~~

Launcher trên Linux/macOS:

~~~shell
#!/bin/sh
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "$APP_DIR/runtime/bin/java" -cp "$APP_DIR/app/app.jar:$APP_DIR/app/lib/*" com.acme.Main "$@"
~~~

Trên Windows, classpath separator là `;`:

~~~bat
@echo off
set "APP_DIR=%~dp0"
"%APP_DIR%runtime\bin\java.exe" -cp "%APP_DIR%app\app.jar;%APP_DIR%app\lib\*" com.acme.Main %*
~~~

Launcher thực tế cần xử lý argument, working directory, log path và exit code theo yêu cầu sản phẩm. Không hardcode đường dẫn tuyệt đối của máy build.

### 7.4. Giới hạn của jdeps với ứng dụng classpath

Phân tích tĩnh có thể bỏ sót module cần cho:

- `Class.forName` với class name lấy từ cấu hình.
- Plugin được nạp ở runtime.
- JDBC driver/provider discovery.
- Security provider được đăng ký động.
- Scripting engine.
- JNI hoặc thư viện native.
- Resource bundle/locale data.

Sau khi tạo image, chạy test đầy đủ các feature và thêm module bị thiếu vào `--add-modules`. Không coi output jdeps là danh sách tuyệt đối cho mọi đường chạy động.

## 8. Đóng gói ứng dụng bằng jpackage

### 8.1. jpackage làm gì?

`jpackage` tạo application image hoặc package cài đặt cho ứng dụng Java. Công cụ có thể đóng gói launcher, application files và runtime image để người dùng không phải cài Java riêng.

Các kiểu package phổ biến trong JDK 17:

| Nền tảng | Kiểu package thường hỗ trợ |
|---|---|
| Windows | `exe`, `msi`, `app-image` |
| macOS | `dmg`, `pkg`, `app-image` |
| Linux | `deb`, `rpm`, `app-image` |

Kiểu installer cụ thể phụ thuộc hệ điều hành, công cụ native và môi trường build. `app-image` là thư mục ứng dụng tự chứa, có thể chạy trực tiếp mà không cần tạo installer native.

### 8.2. jpackage cho ứng dụng classpath

Giả sử thư mục input:

~~~text
dist/
├── app.jar
└── lib/
    ├── dependency-a.jar
    └── dependency-b.jar
~~~

Tạo application image dùng runtime đã tạo bằng jlink:

~~~shell
jpackage --type app-image --name AcmeApp --input dist --main-jar app.jar --main-class com.acme.Main --class-path "lib/dependency-a.jar:lib/dependency-b.jar" --runtime-image build/runtime --dest build/packages
~~~

Trong lệnh này:

- `--type app-image`: tạo application image.
- `--name`: tên ứng dụng/launcher.
- `--input`: thư mục chứa application files.
- `--main-jar`: JAR chứa entry point.
- `--main-class`: main class.
- `--class-path`: dependency JAR nằm tương đối trong input directory.
- `--runtime-image`: runtime image đã tạo bằng jlink.
- `--dest`: nơi ghi package output.

Classpath separator trong ví dụ là `:` của Linux/macOS. Trên Windows, dùng `;`. Nếu ứng dụng sử dụng manifest Class-Path trong main JAR, hãy kiểm tra manifest và đường dẫn dependency sau khi cài đặt.

### 8.3. jpackage cho ứng dụng modular

Với ứng dụng modular, có thể để jpackage tạo runtime image thông qua jlink:

~~~shell
jpackage --type app-image --name AcmeApp --module-path "mods:$JAVA_HOME/jmods" --module com.acme.app/com.acme.app.Main --jlink-options "--strip-debug --no-header-files --no-man-pages --compress=2" --dest build/packages
~~~

Ở đây:

- `--module-path` chỉ ra application modules và JDK modules có thể dùng khi tạo image.
- `--module` chỉ định module/main class của ứng dụng.
- `--jlink-options` chuyển tùy chọn linker để tạo runtime image.

Kiểm tra `jpackage --help` của đúng JDK 17 vendor/build vì các option và yêu cầu nền tảng có thể khác. Đường dẫn module path dùng dấu `:` trên Unix-like và `;` trên Windows.

### 8.4. Tạo installer native

Khi application image đã hoạt động, có thể tạo installer trên nền tảng đích:

~~~shell
jpackage --type msi --name AcmeApp --input dist --main-jar app.jar --main-class com.acme.Main --runtime-image build/runtime --dest build/installer
~~~

Ví dụ trên dành cho Windows và cần toolchain đóng gói phù hợp. Trên Linux có thể chọn `deb` hoặc `rpm`; trên macOS có thể chọn `dmg` hoặc `pkg`.

Hãy build và test package trên OS/architecture đích. Một application image hoặc installer chứa executable và native library của một nền tảng không thể được xem là artifact portable cho mọi OS.

### 8.5. Application image và installer khác nhau

| Artifact | Mục đích |
|---|---|
| Runtime image | Runtime Java tùy chỉnh, chưa nhất thiết có launcher ứng dụng |
| Application image | Thư mục ứng dụng có launcher, app files và runtime theo cấu hình |
| Native installer | Gói cài đặt tích hợp với nền tảng, có thể tạo shortcut/menu và metadata |
| Container image | Image triển khai ứng dụng/server cùng runtime và filesystem cần thiết |

Nên kiểm tra application image trước. Khi launcher và runtime chạy ổn định, mới tạo installer hoặc image phát hành.

## 9. Cập nhật runtime đã phân phối cùng ứng dụng

### 9.1. Vì sao phải cập nhật runtime cùng sản phẩm?

Runtime riêng là một thành phần được đóng gói vào artifact. Khi ứng dụng mang theo runtime Java 17 ở một patch level cụ thể, việc máy người dùng cài JDK mới hơn không thay đổi runtime riêng đó.

Ví dụ:

~~~text
AcmeApp 4.2
  runtime: JDK 17 build A

JDK 17 build B được phát hành với bản vá bảo mật

Máy build được cập nhật lên build B
  |
  +-- Installer AcmeApp 4.2 đã phát hành vẫn chứa build A
~~~

Để người dùng nhận bản vá, cần tạo runtime image mới từ JDK đã cập nhật, kiểm thử, đóng gói và phát hành bản ứng dụng/installer mới.

### 9.2. Quy trình cập nhật có kiểm soát

Một chu kỳ cập nhật runtime:

1. Theo dõi security advisory và release của JDK vendor đã chọn.
2. Chọn patch release phù hợp cho Java 17.
3. Cập nhật JDK toolchain trong môi trường build.
4. Tạo lại runtime image bằng jlink hoặc để jpackage tạo runtime mới.
5. Tạo lại application image/installer/container image.
6. Chạy test chức năng, tích hợp, TLS/crypto, locale và native library.
7. Kiểm tra phiên bản runtime trong artifact.
8. Ký và phát hành artifact mới theo quy trình sản phẩm.
9. Có kế hoạch rollout, rollback và thông báo cho người dùng.

Không chỉnh sửa trực tiếp một runtime image đã cài trên máy người dùng bằng cách chép vài file từ JDK khác. Một runtime image là tập hợp các module, native library, security configuration và metadata cần nhất quán với nhau.

### 9.3. Ghi lại runtime provenance

Mỗi bản phát hành nên lưu:

- JDK vendor.
- JDK version và build number.
- OS/architecture dùng để tạo image.
- Các module được liên kết.
- Các linker/jpackage options.
- Version ứng dụng và dependency.
- Hash của runtime image và installer.
- Kết quả test trên nền tảng đích.

Thông tin này giúp trả lời chính xác runtime nào đang được cài trong một máy khách và tái tạo build khi cần.

### 9.4. Không dùng phiên bản runtime trôi nổi

Không nên tải “latest JDK 17” không cố định mỗi lần build mà không ghi lại build number. Cùng major version 17 nhưng patch, vendor và build có thể khác.

Pipeline nên chọn một JDK distribution cụ thể và ghi lại phiên bản đầy đủ. Khi nâng patch, thay đổi có chủ đích trong source/build configuration và tạo release mới.

### 9.5. Cập nhật runtime độc lập với version ứng dụng

Có thể ứng dụng không đổi source nhưng vẫn cần phát hành bản mới chỉ để cập nhật runtime. Khi đó release notes nên nói rõ đây là runtime/security update, và version runtime trong artifact phải thay đổi tương ứng.

Không nên giả định người dùng có thể cập nhật runtime bằng cách thay executable `java` riêng lẻ. Cập nhật toàn bộ image/application package theo quy trình đã kiểm thử.

## 10. Chọn JDK vendor và nguồn runtime

### 10.1. Chọn một distribution có chính sách cập nhật rõ

Các bản OpenJDK distribution có thể khác nhau về:

- Chu kỳ phát hành và thời gian hỗ trợ.
- Cách cung cấp security patch.
- Nền tảng và kiến trúc được hỗ trợ.
- Chính sách license và điều khoản phân phối.
- Native library, crypto provider hoặc build configuration.

Đội phát triển cần chọn vendor phù hợp với chính sách sản phẩm và môi trường vận hành. Không chỉ dựa vào tên “Java 17”; hãy ghi lại vendor/build thực tế.

### 10.2. Tuân thủ license và notices

Runtime image có thể chứa file license, copyright và notice của JDK modules. Giữ lại các file legal được phân phối cùng image. Kiểm tra điều khoản của JDK distribution và dependency trước khi đưa vào installer thương mại.

Không xóa thư mục legal chỉ để giảm vài MB. Nếu dùng plugin strip hoặc tự đóng gói file, phải bảo đảm nghĩa vụ notice vẫn được đáp ứng.

### 10.3. Bản vá bảo mật và thời gian hỗ trợ

Java 17 là một major release, nhưng trạng thái hỗ trợ và lịch patch phụ thuộc vendor/distribution. Dùng nguồn cập nhật chính thức của vendor đã chọn để xác định bản build nên triển khai.

Quy trình quản lý runtime cần có owner, cadence và cách xử lý bản vá khẩn cấp. Nếu runtime được nhúng vào hàng nghìn máy khách, phải tính thời gian phát hành và cập nhật sản phẩm, không chỉ thời gian nâng JDK trên CI.

## 11. Kiểm thử runtime image trước khi phát hành

### 11.1. Kiểm tra phiên bản và module

Chạy executable bên trong image:

~~~shell
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
~~~

Với Windows:

~~~powershell
build\runtime\bin\java.exe --version
build\runtime\bin\java.exe --list-modules
~~~

Xác nhận:

- Version và vendor đúng.
- Các module ứng dụng cần có.
- Module crypto, locale, desktop hoặc provider cần thiết đã được đưa vào.
- Runtime không chứa module dư thừa ngoài chủ đích.

### 11.2. Chạy không dựa vào JDK trên máy build

Một lỗi phổ biến là application image vô tình dùng `java` từ PATH thay vì runtime đi kèm. Để kiểm tra:

- Chạy launcher của application image.
- Dùng máy/VM/container không cài JDK ngoài.
- Không thiết lập JAVA_HOME tới JDK build.
- Xác nhận process command line trỏ tới runtime trong application image.

Nếu ứng dụng chỉ chạy khi máy có JDK đầy đủ, runtime image có thể thiếu module hoặc launcher đang dùng sai Java executable.

### 11.3. Kiểm tra feature động

Chạy test cho các feature có thể không được phát hiện bởi jdeps:

- JDBC driver và connection pool.
- TLS/HTTPS, certificate và crypto provider.
- ServiceLoader/plugin.
- Locale, date/number/currency formatting.
- XML hoặc scripting nếu ứng dụng dùng.
- Reflection và class loading.
- JNI/native library.
- GUI, font, printing hoặc media nếu là desktop application.

### 11.4. Kiểm tra trên từng OS/architecture

Runtime image chứa native components phù hợp với nền tảng được build. Kiểm tra riêng:

- Windows x64/ARM64 nếu sản phẩm hỗ trợ.
- Linux distribution/libc và kiến trúc CPU.
- macOS Intel/Apple Silicon nếu sản phẩm hỗ trợ.
- Native library và launcher executable.
- Installer upgrade/uninstall, shortcut, file association và quyền ghi.

Không giả định một runtime image Linux có thể chạy nguyên trạng trên Windows hoặc macOS.

### 11.5. Kiểm tra đường dẫn dữ liệu

Không lưu file người dùng, log hoặc cấu hình mutable vào thư mục runtime image nếu installer có thể cập nhật/thay thế thư mục đó.

Tách:

- Application binaries.
- Runtime image.
- User configuration.
- User data.
- Logs và diagnostic files.

Đặt dữ liệu mutable vào thư mục phù hợp của user/service account. Như vậy, nâng cấp runtime không vô tình xóa dữ liệu ứng dụng.

## 12. Runtime image trong Docker và Kubernetes

### 12.1. Đóng gói runtime vào container image

Một container image có thể chứa runtime image jlink cùng application JAR:

~~~dockerfile
FROM debian:stable-slim
WORKDIR /opt/acme
COPY runtime/ /opt/acme/runtime/
COPY app/ /opt/acme/app/
ENTRYPOINT ["/opt/acme/runtime/bin/java", "-cp", "/opt/acme/app/app.jar:/opt/acme/app/lib/*", "com.acme.Main"]
~~~

Đây là ví dụ khái niệm. Base image, user, certificates, timezone data, CA trust và native dependencies cần được chọn theo ứng dụng và môi trường triển khai.

### 12.2. Cập nhật base image và runtime là hai việc khác nhau

Container có thể chứa:

- Base OS image.
- JDK runtime image được copy vào image.
- Application files.

Nâng base OS image không tự cập nhật runtime Java đã được copy vào layer. Tương tự, cập nhật JDK trên build agent không thay đổi runtime đã có trong container image cũ.

Khi cập nhật:

1. Rebuild từ base image đã vá.
2. Rebuild jlink runtime từ JDK patch mới.
3. Copy runtime và application vào container image.
4. Scan/test image.
5. Push image mới và rollout theo digest/version đã pin.

### 12.3. Dùng image bất biến

Trong môi trường container, ưu tiên build image mới rồi rollout thay cho việc vào container đang chạy và sửa file runtime tại chỗ. Cách làm bất biến giúp:

- Dễ truy xuất phiên bản đang chạy.
- Dễ rollback.
- Dễ kiểm tra artifact.
- Không có trạng thái runtime khác nhau giữa các replica cùng tag do sửa tay.

## 13. Tối ưu kích thước và hiệu năng runtime

### 13.1. Bỏ module không cần

Runtime image nhỏ hơn có thể giúp tải xuống nhanh, giảm dung lượng cài đặt và giảm số thành phần không dùng. Tuy nhiên, mục tiêu không phải tạo image nhỏ nhất bằng mọi giá.

Hãy giữ module cần cho toàn bộ feature và security provider. Một image nhỏ nhưng thiếu TLS provider, locale hoặc JDBC driver support sẽ tạo lỗi khó điều tra.

### 13.2. Đo dung lượng trước và sau

Ghi nhận:

- Kích thước JDK đầy đủ.
- Kích thước runtime image.
- Kích thước application image.
- Kích thước installer.
- Thời gian startup.
- Thời gian chạy feature chính.

Compression và strip options có thể làm thay đổi dung lượng và startup. Đo trên cùng OS/filesystem và cùng workload.

### 13.3. Không nhầm runtime size với heap size

jlink giảm module/runtime components được phân phối. Nó không trực tiếp đặt heap max, thread stack, metaspace hoặc container memory limit.

Heap vẫn được cấu hình qua JVM options như `-Xms`, `-Xmx` hoặc percentage flags. Runtime image nhỏ hơn không đồng nghĩa ứng dụng cần ít heap hơn.

## 14. Bảo mật và vận hành runtime được phân phối

### 14.1. Giữ runtime đồng bộ với bản vá

Theo dõi security advisory của vendor và lên lịch cập nhật. Khi có bản vá ảnh hưởng đến Java 17 runtime, đánh giá ứng dụng, tạo image mới và phát hành artifact. Không chờ người dùng tự cài một JDK mới để vá runtime riêng của ứng dụng.

### 14.2. Kiểm soát file runtime

- Không cho user ứng dụng sửa file executable/module runtime nếu không cần.
- Đặt quyền filesystem phù hợp.
- Không chạy ứng dụng với quyền admin/root chỉ để đọc runtime.
- Giữ file legal và security configuration.
- Không chép native library không rõ nguồn vào runtime.

### 14.3. Trust store và security configuration

Runtime image có thể chứa security configuration và trust store của JDK. Nếu ứng dụng dùng TLS, kiểm tra:

- CA certificates được cung cấp bởi runtime/base OS hoặc cấu hình ứng dụng.
- Trust store thực sự mà JVM sử dụng.
- Crypto provider và module cần thiết.
- Quy trình cập nhật CA certificate.

Không sửa file security configuration bằng thao tác thủ công không có version control. Nếu cần cấu hình riêng, tạo bản image mới hoặc cung cấp cấu hình bên ngoài có kiểm soát.

### 14.4. Native libraries

Nếu ứng dụng dùng JNI hoặc thư viện native:

- Phân phối đúng binary theo OS/architecture.
- Kiểm tra dependency hệ thống và libc.
- Kiểm tra loader path.
- Kiểm thử trong môi trường sạch.
- Cập nhật native library cùng release khi có bản vá.

Runtime image Java không tự đóng gói mọi native dependency bên thứ ba.

## 15. Chẩn đoán lỗi runtime image và installer

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `Module ... not found` | Module không được đưa vào image hoặc module path sai | Kiểm tra `--add-modules`, module path và module graph |
| `NoClassDefFoundError` | Class/JAR dependency thiếu hoặc module không có | Kiểm tra classpath/module path và packaged files |
| `ClassNotFoundException` | Class được nạp động nhưng không có trong distribution | Kiểm tra plugin/configuration và classloader |
| Service provider không được tìm thấy | Provider/module/service descriptor không được đóng gói | Kiểm tra `uses`, `provides`, `--bind-services` |
| TLS/crypto lỗi sau khi slim runtime | Thiếu provider/module hoặc security configuration | Kiểm tra module crypto và test TLS |
| Locale hiển thị sai/fallback | Thiếu locale data hoặc resource bundle | Kiểm tra `jdk.localedata`, locale và resource |
| Launcher chạy bằng Java khác | PATH/JAVA_HOME hoặc launcher cấu hình sai | Kiểm tra process command line và runtime path |
| Native library load failed | Binary sai kiến trúc hoặc thiếu OS dependency | Kiểm tra native binary, loader và OS |
| Installer cài được nhưng app không khởi động | Runtime/module/permission/path không đúng | Chạy app-image trước và đọc log launcher |
| Bản cập nhật vẫn dùng Java cũ | Installer mới không chứa runtime mới hoặc app trỏ tới system Java | Kiểm tra version runtime bên trong artifact |
| Một OS chạy, OS khác lỗi | Image/native library/installer phụ thuộc nền tảng | Build và test artifact riêng cho từng OS/architecture |

Khi chẩn đoán, kiểm tra runtime image trước bằng `runtime/bin/java --version` và `--list-modules`, sau đó chạy application launcher với log đủ để xác định executable và class/module path thực tế.

## 16. Ví dụ pipeline tạo runtime và application image

Một pipeline đơn giản cho ứng dụng modular:

~~~text
Source + dependencies
        |
        v
Compile with JDK 17
        |
        v
Resolve module graph
        |
        v
jlink / jpackage
        |
        v
Application image
        |
        v
Test on target OS and architecture
        |
        v
Sign + publish artifact
        |
        v
User installs application with private runtime
~~~

Các bước có thể tự động hóa:

1. Chọn JDK vendor/build được pin trong build environment.
2. Biên dịch với `--release 17`.
3. Kiểm tra module/dependency bằng `jdeps` và module descriptors.
4. Tạo runtime image hoặc để jpackage gọi jlink.
5. Tạo application image.
6. Chạy smoke test trên môi trường không có JDK bên ngoài.
7. Chạy test feature và native integration.
8. Kiểm tra runtime version/module list và package contents.
9. Ký artifact và lưu hash/provenance.
10. Phát hành theo kênh cập nhật và lưu rollback artifact.

Với ứng dụng classpath, thay bước module graph bằng phân tích JDK module dependency, tạo runtime JDK-only và đóng gói app JAR/dependencies trên classpath.

## 17. Ví dụ tổng hợp: build runtime image cho ứng dụng modular

Giả sử module ứng dụng tên `com.acme.desktop`, main class `com.acme.desktop.Main`, các module đã compile nằm trong `mods`.

Tạo runtime image:

~~~shell
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.desktop --launcher acme=com.acme.desktop/com.acme.desktop.Main --strip-debug --no-header-files --no-man-pages --compress=2 --output build/runtime
~~~

Kiểm tra runtime:

~~~shell
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
~~~

Chạy launcher:

~~~shell
build/runtime/bin/acme
~~~

Tạo application image trực tiếp từ runtime image và module đã được liên kết không phải lúc nào cũng cần thiết; runtime image trên đã có launcher. Có thể phân phối thư mục image đó như một application bundle, bổ sung tài nguyên và script cài đặt phù hợp nền tảng. Nếu cần installer native và muốn jpackage quản lý launcher/package layout, cấu hình jpackage cho modular app bằng `--module-path`, `--module` và `--jlink-options` để nó tạo runtime image trong quá trình đóng gói.

Ví dụ jpackage tạo application image từ module path:

~~~shell
jpackage --type app-image --name AcmeDesktop --module-path "mods:$JAVA_HOME/jmods" --module com.acme.desktop/com.acme.desktop.Main --jlink-options "--strip-debug --no-header-files --no-man-pages --compress=2" --dest build/packages
~~~

Trên Windows, thay dấu phân cách module path thành `;`. Sau khi tạo, chạy launcher bên trong `build/packages/AcmeDesktop` trên máy test sạch và xác nhận runtime đi kèm được sử dụng.

## 18. Bài tập thực hành

### Bài 1 — Quan sát JDK và runtime image

Chạy:

~~~shell
java --version
java --list-modules
jlink --version
jpackage --version
~~~

Ghi lại vendor/build và module list của JDK 17. So sánh với runtime image được tạo từ một tập module nhỏ.

### Bài 2 — Phân tích dependency bằng jdeps

Tạo hoặc chọn một ứng dụng Java 17 có một số JAR dependency. Chạy:

~~~shell
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" app.jar
~~~

Tạo runtime image từ các module được in ra. Kiểm tra ứng dụng có chạy đủ các feature hay không. Bổ sung module nếu có dependency được nạp động.

### Bài 3 — Liên kết ứng dụng modular

Tạo module có `module-info.java`, compile vào `mods`, rồi dùng jlink với `--add-modules` và `--launcher`. Chạy bằng launcher được tạo mà không dùng JDK đầy đủ.

### Bài 4 — So sánh linker options

Tạo hai runtime image: một mặc định và một dùng `--strip-debug`, `--no-header-files`, `--no-man-pages`, `--compress=2`. So sánh kích thước và thời gian startup.

### Bài 5 — Tạo application image bằng jpackage

Dùng jpackage tạo `app-image` cho một ứng dụng classpath có runtime riêng. Kiểm tra launcher, classpath, thư mục runtime và cách ứng dụng tìm file cấu hình.

### Bài 6 — Cập nhật runtime patch

Trong môi trường thử nghiệm, build artifact với một JDK 17 patch build, ghi version vào release metadata. Sau đó cập nhật JDK build environment lên patch mới, tạo runtime/app image mới và xác nhận runtime version trong artifact đã thay đổi.

### Bài 7 — Kiểm tra môi trường sạch

Chép application image sang VM/container không cài JDK. Chạy ứng dụng, kiểm tra TLS, locale, JDBC, plugin hoặc các feature động đang được sử dụng. Ghi lại lỗi nếu module hoặc native dependency thiếu.

### Bài 8 — Kiểm tra cập nhật và rollback

Tạo hai artifact có runtime version khác nhau. Cài bản đầu, nâng lên bản sau và kiểm tra dữ liệu/configuration người dùng còn nguyên. Thử rollback theo quy trình phát hành.

## 19. Câu hỏi tự kiểm tra

1. JDK khác runtime image ở điểm nào?
2. Vì sao ứng dụng phân phối runtime riêng cần có quy trình cập nhật riêng?
3. jlink nhận input là module hay mọi loại JAR?
4. Vì sao automatic module không phải input phù hợp cho jlink?
5. `--add-modules` xác định điều gì?
6. jdeps có thể bỏ sót dependency nào được nạp động?
7. `--bind-services` giúp gì khi ứng dụng dùng ServiceLoader?
8. `--strip-debug`, `--no-man-pages` và `--compress=2` có tác dụng gì?
9. Vì sao runtime image quá nhỏ có thể lỗi ở TLS hoặc JDBC dù ứng dụng khởi động được?
10. Ứng dụng classpath có thể dùng runtime image jlink không?
11. jpackage khác jlink thế nào?
12. Application image khác native installer thế nào?
13. Vì sao nên test application image trước khi tạo installer?
14. Vì sao artifact jlink cần được build riêng theo OS/architecture?
15. Nâng JDK trên máy build có tự cập nhật runtime đã phân phối không?
16. Cần lưu metadata nào để truy xuất runtime provenance?
17. Vì sao không nên sửa runtime image đã cài bằng cách chép một executable Java mới?
18. Container base image update có tự cập nhật runtime được copy vào image không?
19. Vì sao dữ liệu người dùng không nên nằm trong runtime directory?
20. Làm thế nào kiểm tra ứng dụng thực sự chạy bằng runtime đi kèm?

## 20. Tài liệu tham khảo

- [Java SE 17 jlink Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): tạo runtime image và các linker options.
- [Java SE 17 jpackage Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): tạo application image và installer packages.
- [Java SE 17 jdeps Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency và module dependency.
- [Java SE 17 java Tool Reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): chạy ứng dụng, module path và runtime options.
- [JEP 282 — jlink: The Java Linker](https://openjdk.org/jeps/282): thiết kế công cụ tạo runtime image tùy chỉnh.
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): công cụ đóng gói ứng dụng Java.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): module path, module graph và module resolution.

Phân phối runtime cùng ứng dụng giúp kiểm soát phiên bản Java và giảm phụ thuộc vào môi trường máy người dùng. Với Java 17, dùng jlink để tạo runtime image chứa module cần thiết, jpackage để tạo application image hoặc installer, và jdeps làm điểm khởi đầu cho phân tích dependency. Mỗi runtime image là một artifact có vòng đời riêng: pin JDK vendor/build, kiểm thử trên nền tảng đích, lưu provenance và phát hành lại image khi có bản vá Java. Không coi runtime đã đóng gói là tự động được cập nhật chỉ vì JDK trên máy build hoặc hệ điều hành đã thay đổi.
