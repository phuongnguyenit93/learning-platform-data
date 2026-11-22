# Launcher script và module main

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vai trò của module main class khi khởi chạy modular application.
- Tạo launcher script gọi `java -m` và truyền arguments cho ứng dụng.
- Tạo launcher riêng trong custom runtime image bằng `jlink --launcher`.
- Đóng gói launcher ứng dụng bằng `jpackage`.
- Phân biệt module main class, main class chỉ định trên command line và launcher script.
- Chọn cách đóng gói phù hợp cho ứng dụng cần runtime riêng hoặc cần nhiều entry point.

## 1. Module main và launcher script

Một modular application có thể được khởi chạy bằng module name:

~~~bash
java --module-path app-modules \
     --module com.example.app
~~~

Khi command line chỉ có module name, Java launcher cần biết main class của module. Thông tin này có thể được lưu trong binary module descriptor dưới dạng `ModuleMainClass` attribute, thường được thiết lập khi đóng gói modular JAR bằng `jar --main-class`.

Nếu module descriptor chưa có main class, hãy chỉ rõ main class trong command line:

~~~bash
java --module-path app-modules \
     --module com.example.app/com.example.app.Main
~~~

Trong môi trường triển khai, người dùng cuối thường không muốn phải nhớ module path, module name, main class hoặc đường dẫn runtime. Launcher script giải quyết phần giao diện khởi chạy này: nó xác định thư mục cài đặt, gọi đúng Java runtime, truyền module entry point và chuyển tiếp arguments cho ứng dụng.

Một launcher script không thay thế module descriptor. Nó là một lớp khởi chạy bên ngoài, còn module main vẫn được quyết định bởi descriptor hoặc command line mà script gọi.

## 2. Chuẩn bị modular application

Giả sử ứng dụng có cấu trúc:

~~~text
customer-app/
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── build/
│   └── mods/
└── scripts/
~~~

Module descriptor:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Main class:

~~~java
package com.example.app;

import java.util.Arrays;
import java.util.logging.Logger;

public class Main {

    private static final Logger LOGGER =
            Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        LOGGER.info("Customer application started");
        System.out.println("Arguments: " + Arrays.toString(args));
    }
}
~~~

Biên dịch module:

~~~bash
javac --module-source-path src \
      -d build/mods \
      -m com.example.app
~~~

Output là một exploded module tại `build/mods/com.example.app`. Bạn có thể chạy trực tiếp bằng cách chỉ định module và main class:

~~~bash
java --module-path build/mods \
     --module com.example.app/com.example.app.Main \
     --config conf/app.properties
~~~

Arguments nằm sau module entry point được chuyển vào `main(String[] args)`.

## 3. Lưu module main class vào modular JAR

Nếu muốn launcher chỉ cần biết module name, hãy đóng gói ứng dụng thành modular JAR và lưu main class:

~~~bash
jar --create \
    --file build/mods/com.example.app.jar \
    --main-class com.example.app.Main \
    -C build/mods/com.example.app .
~~~

`--main-class` (hoặc `-e`) ghi tên main class vào module descriptor nhị phân. Có thể kiểm tra bằng:

~~~bash
jar --describe-module \
    --file build/mods/com.example.app.jar
~~~

Kết quả có thể hiển thị:

~~~text
com.example.app
requires java.base mandated
requires java.logging
main-class com.example.app.Main
~~~

Giờ đây có thể chạy module mà không phải viết tên class:

~~~bash
java --module-path build/mods \
     --module com.example.app \
     --config conf/app.properties
~~~

Nếu command line chỉ định `com.example.app/com.example.app.AdminMain`, class đó sẽ được dùng thay cho main class mặc định đã lưu. Điều này hữu ích khi một module cung cấp nhiều entry point.

## 4. Tạo launcher script trên Linux và macOS

Giả sử thư mục triển khai có cấu trúc:

~~~text
customer-app/
├── app/
│   └── com.example.app.jar
├── runtime/
│   └── bin/java
└── bin/
    └── customer-app
~~~

Script `bin/customer-app`:

~~~bash
#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_HOME=$(CDPATH= cd "$SCRIPT_DIR/.." && pwd)

JAVA="$APP_HOME/runtime/bin/java"
APP_MODULE_PATH="$APP_HOME/app"

exec "$JAVA" \
    --module-path "$APP_MODULE_PATH" \
    --module com.example.app \
    "$@"
~~~

Cấp quyền thực thi cho script:

~~~bash
chmod +x bin/customer-app
~~~

Chạy ứng dụng:

~~~bash
bin/customer-app --config "conf/customer settings.properties" --verbose
~~~

Script hoạt động như sau:

1. Xác định thư mục chứa script.
2. Tìm thư mục cài đặt gốc từ vị trí script, không phụ thuộc current working directory của người chạy.
3. Dùng Java runtime được đóng gói cùng ứng dụng.
4. Đặt module path tới thư mục chứa modular JAR.
5. Khởi chạy module bằng module main class đã lưu.
6. Chuyển tiếp từng argument qua `"$@"`, giữ nguyên ranh giới giữa các argument, kể cả khi có khoảng trắng.
7. `exec` thay tiến trình shell bằng Java process để exit code của ứng dụng được trả về trực tiếp.

Nếu JAR chưa lưu module main class, script có thể chỉ rõ entry point:

~~~bash
exec "$JAVA" \
    --module-path "$APP_MODULE_PATH" \
    --module com.example.app/com.example.app.Main \
    "$@"
~~~

Khi triển khai runtime riêng, hãy kiểm tra file `runtime/bin/java` tồn tại và có quyền thực thi. Không nên giả định máy người dùng đã cài đúng phiên bản JDK chỉ vì môi trường build có JDK.

## 5. Tạo launcher script trên Windows

Với cùng cấu trúc triển khai, tạo file `bin/customer-app.bat`:

~~~bat
@echo off
setlocal

for %%I in ("%~dp0..") do set "APP_HOME=%%~fI"

set "JAVA=%APP_HOME%\runtime\bin\java.exe"
set "APP_MODULE_PATH=%APP_HOME%\app"

"%JAVA%" --module-path "%APP_MODULE_PATH%" --module com.example.app %*

set "APP_EXIT=%ERRORLEVEL%"
endlocal & exit /b %APP_EXIT%
~~~

Giải thích:

- `%~dp0` là thư mục chứa batch file.
- `for %%I ... %%~fI` chuẩn hóa đường dẫn thư mục cài đặt.
- Đường dẫn runtime và module path được đặt trong dấu ngoặc kép để xử lý khoảng trắng.
- `%*` chuyển tiếp command-line arguments mà người dùng đã truyền.
- Exit code được lưu trước khi `endlocal`, sau đó trả lại cho tiến trình gọi.

Chạy:

~~~bat
bin\customer-app.bat --config "conf\customer settings.properties" --verbose
~~~

Nếu dùng main class tường minh, thay phần module argument bằng:

~~~bat
--module com.example.app/com.example.app.Main
~~~

Khi viết batch launcher, hãy kiểm tra cách gọi thực tế với arguments có khoảng trắng, dấu ngoặc kép và ký tự đặc biệt. Cú pháp xử lý argument của `cmd.exe` khác shell trên Unix.

## 6. Dùng jlink tạo runtime image có launcher riêng

Nếu muốn phân phối runtime chỉ chứa các module cần thiết, có thể dùng `jlink`.

Trước hết, đóng gói ứng dụng thành modular JAR như phần trước. Sau đó tạo runtime image:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:build/mods" \
    --add-modules com.example.app \
    --launcher customer-app=com.example.app \
    --output build/customer-runtime
~~~

Trong ví dụ này:

- `--module-path` cung cấp JDK modules và application modules.
- `--add-modules com.example.app` chọn module gốc để đưa vào image; dependency của nó cũng được resolve.
- `--launcher customer-app=com.example.app` tạo launcher tên `customer-app`.
- `--output` xác định thư mục runtime image.

Nếu module descriptor có `ModuleMainClass`, có thể chỉ cần module name trong khai báo launcher. Nếu descriptor chưa lưu main class, chỉ định rõ:

~~~bash
--launcher customer-app=com.example.app/com.example.app.Main
~~~

Sau khi tạo thành công, runtime image có dạng tổng quát:

~~~text
build/customer-runtime/
├── bin/
│   ├── java
│   ├── keytool
│   └── customer-app
├── conf/
├── legal/
└── lib/
~~~

Khởi chạy ứng dụng bằng launcher đã tạo:

~~~bash
build/customer-runtime/bin/customer-app --config conf/app.properties
~~~

Launcher được tạo bởi `jlink` là executable phù hợp với nền tảng, không phải shell script `.sh` hoặc batch `.bat` mà bạn tự viết. Nó sử dụng runtime image đi kèm và entry point đã cấu hình.

### 6.1. Module path khi chạy runtime image

Khi application module đã được link vào image, launcher không cần chỉ lại module path của JAR bên ngoài:

~~~bash
build/customer-runtime/bin/java \
    --module com.example.app \
    --config conf/app.properties
~~~

Nếu application module được link cùng runtime image và descriptor đã lưu main class, chỉ module name là đủ. Nếu cần một entry point khác, chỉ định `module/mainclass` trên command line hoặc tạo launcher riêng cho entry point đó.

### 6.2. Provider module và service binding

Nếu ứng dụng sử dụng service provider và muốn `jlink` tự đưa các provider module phù hợp vào image, cân nhắc option:

~~~bash
--bind-services
~~~

Provider vẫn phải có mặt trong module path đầu vào và được phát hiện thông qua service declaration. `--bind-services` hỗ trợ service binding khi tạo image; nó không tự tải provider JAR từ một thư mục bất kỳ ngoài module path.

## 7. Đóng gói application launcher bằng jpackage

`jpackage` tạo application image hoặc installer phù hợp với nền tảng. Nó có thể tạo launcher cho modular application trực tiếp:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --module-path build/mods \
    --module com.example.app
~~~

Nếu module descriptor đã lưu module main class, `--module` chỉ cần tên module. Nếu chưa có, chỉ rõ module và main class:

~~~bash
--module com.example.app/com.example.app.Main
~~~

Kết quả là application image có launcher cho người dùng chạy. Tùy hệ điều hành và loại package, launcher có thể là executable hoặc app bundle. Nếu muốn dùng runtime image đã tạo bằng `jlink`, có thể truyền `--runtime-image` cho `jpackage`:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --runtime-image build/customer-runtime \
    --module com.example.app
~~~

Không truyền đồng thời các tùy chọn tạo runtime riêng không tương thích với `--runtime-image`; hãy để image đã tạo cung cấp runtime cho package.

### 7.1. Nhiều launcher cho nhiều module main

Một ứng dụng có thể cung cấp nhiều lệnh khởi chạy khác nhau, ví dụ launcher chính và launcher quản trị. Với `jpackage`, dùng `--add-launcher` cùng file properties cho launcher bổ sung.

Ví dụ `admin-launcher.properties`:

~~~properties
module=com.example.app/com.example.app.AdminMain
arguments=--mode,admin
java-options=--add-opens=com.example.app/com.example.app.internal=ALL-UNNAMED
win-console=true
~~~

Đóng gói launcher bổ sung:

~~~bash
jpackage \
    --type app-image \
    --name CustomerApp \
    --dest build/package \
    --module-path build/mods \
    --module com.example.app \
    --add-launcher admin=admin-launcher.properties
~~~

Trong ví dụ, launcher chính dùng module main class mặc định; launcher `admin` chỉ định một main class khác và thêm arguments/options riêng. File properties cần được điều chỉnh theo module và quyền truy cập thực tế của ứng dụng.

## 8. Chọn launcher script, jlink hay jpackage

| Cách triển khai | Phù hợp khi | Kết quả |
|---|---|---|
| Script `.sh` / `.bat` tự viết | Muốn kiểm soát cách tìm runtime, cấu hình và arguments | File script mỏng gọi `java -m` |
| `jlink --launcher` | Muốn custom runtime image nhỏ và launcher riêng | Runtime image có executable launcher |
| `jpackage` | Muốn application image hoặc installer cho người dùng cuối | App image/installer theo nền tảng |

Có thể kết hợp các cách. Ví dụ, dùng `jlink` để tạo runtime image, sau đó dùng `jpackage --runtime-image` để đóng gói ứng dụng. Một script tự viết cũng có thể gọi runtime image do `jlink` tạo ra.

Hãy chọn theo nhu cầu triển khai:

- Nếu môi trường đích đã có Java phù hợp và ứng dụng đơn giản, script gọi `java -m` có thể đủ.
- Nếu cần mang theo runtime riêng và kiểm soát module được đóng gói, dùng `jlink`.
- Nếu cần app image hoặc installer dễ cài đặt, dùng `jpackage`.
- Nếu có nhiều entry point, dùng `jlink --launcher` hoặc `jpackage --add-launcher` để đặt tên riêng cho từng lệnh.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `Module ... not found` | Module path hoặc module image thiếu module ứng dụng | Kiểm tra `--module-path`, `--add-modules` và tên module |
| Không tìm thấy main class khi chỉ truyền module name | Module descriptor chưa lưu `ModuleMainClass` | Dùng `jar --main-class` hoặc chỉ rõ `module/mainclass` |
| Launcher chạy class không mong đợi | Script hoặc launcher khai báo main class khác với descriptor | Kiểm tra phần module argument sau dấu `/` |
| Script chạy được khi đứng trong thư mục dự án nhưng lỗi ở nơi khác | Script dựa vào current working directory | Tính `APP_HOME` từ vị trí file script |
| Không tìm thấy Java runtime | Đường dẫn runtime đóng gói không đúng hoặc image chưa đầy đủ | Kiểm tra `runtime/bin/java` hoặc `image/bin/java` |
| `jlink` báo thiếu module | Dependency hoặc provider module không nằm trong module path | Bổ sung module vào input path và kiểm tra module graph |
| Launcher Windows không nhận đúng argument | Batch file xử lý quoting/space không đúng | Kiểm tra `%*` với argument có khoảng trắng và dấu ngoặc kép |
| Installer thiếu runtime | `jpackage` không được cấp runtime image và không tạo runtime theo cấu hình mong muốn | Kiểm tra `--runtime-image` hoặc module path đầu vào |

Khi debug, hãy in hoặc kiểm tra command line thực tế mà script/launcher sử dụng. Đường dẫn module, module name và main class là ba giá trị cần đối chiếu đầu tiên.

## 10. Tóm tắt

Module main class xác định entry point mặc định của modular application. Launcher script đóng gói các tham số cần thiết để gọi `java -m`, tìm đúng runtime và chuyển tiếp arguments. Nếu cần runtime image riêng, `jlink` có thể tạo image cùng launcher qua `--launcher`; nếu cần application image hoặc installer, `jpackage` tạo launcher và có thể thêm nhiều entry point bằng `--add-launcher`.

Hãy giữ module name và main class rõ ràng trong cấu hình đóng gói. Nếu descriptor đã lưu `ModuleMainClass`, launcher có thể chỉ cần module name; nếu cần entry point riêng, chỉ định `module/mainclass` một cách tường minh.

Tài liệu tham khảo:

- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The jar Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [The jlink Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [The jpackage Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [ModuleDescriptor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleDescriptor.html)
