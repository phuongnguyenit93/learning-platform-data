# Đóng gói công cụ báo cáo thành application image có runtime tối giản

## 1. Mục tiêu và bối cảnh

Một công cụ báo cáo Java thường chỉ cần đọc dữ liệu, tổng hợp kết quả và ghi file đầu ra. Khi triển khai cho người dùng, yêu cầu thực tế là họ có thể chạy công cụ mà không phải cài riêng JDK hoặc tự cấu hình `JAVA_HOME`.

`jpackage` tạo application image chứa launcher, ứng dụng và runtime. `jlink` cho phép tạo runtime tùy chỉnh chỉ gồm các module cần thiết. Kết hợp hai công cụ giúp phân phối một ứng dụng Java tự chứa và giảm phần runtime không sử dụng.

`jpackage` được hoàn thiện để dùng production trong Java 16 qua JEP 392. Cách đóng gói modular app bằng `jlink` và `jpackage` vẫn được duy trì trong JDK hiện đại. Bài này thực hành trên một công cụ báo cáo dạng modular JAR, sau đó tạo runtime tối giản và application image.

JEP 392 là mốc Java 16 của công cụ đóng gói; các lệnh bên dưới dùng cú pháp được tài liệu JDK hiện hành hỗ trợ. Khi áp dụng với một JDK cụ thể, đối chiếu `jlink --help`, `jdeps --help` và `jpackage --help` của chính bộ JDK đó.

Kết quả cần đạt:

- Xây dựng một ứng dụng modular có thể chạy từ command line.
- Dùng `jdeps` để phân tích dependency tĩnh.
- Chọn đúng JDK modules cho runtime.
- Dùng `jlink` tạo custom runtime image.
- Dùng `jpackage` tạo application image có launcher và runtime riêng.
- Kiểm tra runtime, module, launcher và kết quả báo cáo.
- Kiểm thử trên máy sạch không cài JDK.
- Hiểu giới hạn của phân tích dependency và trách nhiệm cập nhật runtime.

## 2. Kiến trúc đầu ra

Quy trình gồm bốn phần:

~~~text
Source code
    |
    v
Modular JAR
    |
    +---- jdeps ----> Danh sách module phụ thuộc tĩnh
    |                         |
    |                         v
    |                       jlink
    |                         |
    |                         v
    |                 Custom runtime image
    |                         |
    +-------------------------+
                              |
                              v
                           jpackage
                              |
                              v
                     Application image
                     - launcher
                     - application JAR
                     - custom runtime
                              |
                              v
                    Kiểm thử và phân phối
~~~

Trong bài thực hành, ứng dụng cần hai module JDK:

- `java.base`: chứa API nền tảng như `Path`, `Files`, `List` và các kiểu cơ bản.
- `java.logging`: cung cấp `Logger` để ghi nhận quá trình tạo báo cáo.

Runtime cuối cùng sẽ gồm hai module này cùng các dependency bắc cầu mà `jlink` tự phân giải. Không cần đóng gói các công cụ phát triển như `javac` hoặc `javadoc`.

Cần phân biệt:

- **JDK:** bộ công cụ phát triển, có compiler và các công cụ như `jar`, `jdeps`, `jlink`, `jpackage`.
- **Runtime image:** môi trường chạy Java được tạo từ các module đã chọn.
- **Application image:** thư mục ứng dụng chứa launcher, payload ứng dụng và runtime.
- **Installer:** gói cài đặt native như MSI, EXE, DEB, RPM, PKG hoặc DMG. Bài này tạo application image để kiểm tra trước.

## 3. Chuẩn bị cấu trúc dự án

Tạo cấu trúc:

~~~text
report-tool/
├── src/
│   └── com.acme.reporter/
│       ├── module-info.java
│       └── com/
│           └── acme/
│               └── reporter/
│                   └── Main.java
├── data/
│   └── sales.csv
├── build/
│   ├── classes/
│   ├── mods/
│   ├── runtime/
│   └── dist/
└── reports/
~~~

Mỗi thư mục có vai trò:

| Thư mục | Nội dung |
| --- | --- |
| `src` | Mã nguồn module. |
| `build/classes` | Class đã biên dịch. |
| `build/mods` | Modular JAR dùng làm đầu vào cho `jdeps` và `jpackage`. |
| `build/runtime` | Runtime image do `jlink` tạo. |
| `build/dist` | Application image do `jpackage` tạo. |
| `data` | File dữ liệu đầu vào. |
| `reports` | Báo cáo được tạo khi chạy ứng dụng. |

Ví dụ dữ liệu `data/sales.csv`:

~~~csv
order_id,customer,total
O-1001,An,120.50
O-1002,Binh,80.00
O-1003,Chi,45.25
~~~

Ví dụ chỉ đếm số dòng dữ liệu sau header. Đây là minh họa cho quy trình đóng gói; một bộ phân tích CSV production cần parser hiểu dấu phẩy, dấu nháy và newline nằm trong field theo đúng định dạng CSV.

## 4. Khai báo module-info.java

File `src/com.acme.reporter/module-info.java`:

~~~java
module com.acme.reporter {
    requires java.logging;
}
~~~

`java.base` luôn được đọc ngầm bởi mọi module Java nên không cần khai báo `requires java.base`.

Module chỉ khai báo dependency thực sự dùng. Nếu thêm thư viện bên ngoài, module descriptor cần khai báo module tương ứng theo thiết kế dependency của ứng dụng.

Không dùng module JDK nội bộ như `jdk.internal.*` hoặc API không được export để giảm số module. Hãy giữ dependency ở API công khai và được hỗ trợ.

## 5. Viết chương trình tạo báo cáo

File `src/com.acme.reporter/com/acme/reporter/Main.java`:

~~~java
package com.acme.reporter;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.logging.Level;
import java.util.logging.Logger;
import java.util.stream.Stream;

public final class Main {
    private static final Logger LOGGER =
        Logger.getLogger(Main.class.getName());

    private Main() {
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println(
                "Usage: ReportTool <input.csv> <output.txt>"
            );
            System.exit(2);
            return;
        }

        Path input = Path.of(args[0]);
        Path output = Path.of(args[1]);

        try {
            long rowCount;

            try (Stream<String> lines =
                     Files.lines(input, StandardCharsets.UTF_8)) {
                rowCount = lines.skip(1).count();
            }

            Path outputDirectory = output.toAbsolutePath().getParent();
            Files.createDirectories(outputDirectory);

            String report = "data_rows=" + rowCount
                + System.lineSeparator();

            Files.writeString(
                output,
                report,
                StandardCharsets.UTF_8
            );

            LOGGER.info(() -> "Report created: " + output);
        } catch (IOException ex) {
            LOGGER.log(Level.SEVERE, "Unable to create report", ex);
            System.exit(1);
        }
    }
}
~~~

Chương trình:

1. Nhận đường dẫn file CSV và đường dẫn file báo cáo.
2. Đọc file theo UTF-8.
3. Bỏ dòng header và đếm các dòng còn lại.
4. Tạo thư mục đầu ra nếu chưa tồn tại.
5. Ghi số dòng vào file báo cáo.
6. Ghi log thành công hoặc lỗi.

`Files.lines()` trả về stream gắn với tài nguyên file nên phải đóng bằng try-with-resources. Việc đóng stream cũng bảo đảm file được giải phóng sau khi đếm.
## 6. Biên dịch thành modular JAR

Đứng tại thư mục gốc `report-tool` và tạo các thư mục build.

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path build/classes, build/mods, build/dist, reports
~~~

Trên Linux hoặc macOS:

~~~bash
mkdir -p build/classes build/mods build/dist reports
~~~

Biên dịch module:

~~~bash
javac --module-source-path src -d build/classes -m com.acme.reporter
~~~

Đóng gói modular JAR:

~~~bash
jar --create --file build/mods/com.acme.reporter.jar --main-class com.acme.reporter.Main -C build/classes/com.acme.reporter .
~~~

Kiểm tra descriptor và nội dung JAR:

~~~bash
jar --describe-module --file build/mods/com.acme.reporter.jar
jar --list --file build/mods/com.acme.reporter.jar
~~~

Descriptor cần cho thấy module `com.acme.reporter` đọc `java.logging`. JAR cần chứa `module-info.class` và class `com/acme/reporter/Main.class`.

## 7. Chạy thử ứng dụng trước khi đóng gói

Chạy trực tiếp từ module path:

~~~bash
java --module-path build/mods --module com.acme.reporter/com.acme.reporter.Main data/sales.csv reports/summary.txt
~~~

Kiểm tra file `reports/summary.txt`. Với dữ liệu mẫu, nội dung dự kiến:

~~~text
data_rows=3
~~~

Đây là bước kiểm tra ứng dụng độc lập với runtime tối giản. Nếu chương trình chưa chạy đúng bằng JDK đầy đủ, chưa nên tiếp tục tạo runtime và application image.

## 8. Phân tích dependency bằng jdeps

`jdeps` phân tích dependency ở mức package, class và module từ bytecode. Tùy chọn `--print-module-deps` in danh sách module dạng phân tách bằng dấu phẩy, có thể dùng làm đầu vào cho `jlink`.

Chạy:

~~~bash
jdeps --print-module-deps --module-path build/mods --module com.acme.reporter
~~~

Với chương trình mẫu, kết quả dự kiến:

~~~text
java.base,java.logging
~~~

Ý nghĩa:

- `java.base` chứa API nền tảng mà chương trình sử dụng.
- `java.logging` chứa API logging được khai báo trong module descriptor.

`jdeps` giúp tránh chọn module theo phỏng đoán. Với ứng dụng lớn, hãy phân tích toàn bộ module và các modular JAR dependency có liên quan, sau đó xem lại kết quả trước khi tạo runtime.

### Kiểm tra dependency bị thiếu

Có thể yêu cầu `jdeps` tìm dependency không phân giải được:

~~~bash
jdeps --missing-deps --module-path build/mods --module com.acme.reporter
~~~

Kết quả cần được xem xét trước khi đóng gói. Không dùng `--ignore-missing-deps` để che cảnh báo rồi coi runtime là đầy đủ.

### Kiểm tra JDK internal API

~~~bash
jdeps --jdk-internals build/mods/com.acme.reporter.jar
~~~

Nếu có dependency vào JDK internal API, hãy tìm API công khai thay thế. Runtime tối giản không phải lý do để phụ thuộc vào package nội bộ.

## 9. Hiểu giới hạn của phân tích tĩnh

`jdeps` đọc dependency thể hiện trong bytecode và module metadata. Nó không thể bảo đảm phát hiện mọi thành phần được nạp lúc chạy.

Các trường hợp cần kiểm tra riêng:

- `Class.forName()` hoặc reflection tạo tên class từ cấu hình.
- `ServiceLoader` và các service provider module.
- JDBC driver được nạp thông qua service provider.
- Plugin được phát hiện từ thư mục hoặc file cấu hình.
- Native library được nạp bằng `System.loadLibrary()`.
- Resource, file cấu hình, locale và certificate được đọc lúc chạy.
- Class name hoặc module name được tạo động từ dữ liệu bên ngoài.

Ví dụ, code có thể gọi `Class.forName("com.vendor.Driver")`. Dependency này có thể không xuất hiện như một tham chiếu class trực tiếp mà `jdeps` phân tích được. Phải bổ sung module hoặc JAR tương ứng và kiểm tra bằng integration test.

### Service binding

`jlink --bind-services` yêu cầu công cụ liên kết các service provider module và dependency của chúng cho service type được dùng trong module graph đang được resolve. Tùy chọn này không thay thế việc đưa provider/JAR được nạp động vào module path hoặc application payload.

Từ JDK 25, `jpackage` không còn tự đưa service bindings vào runtime image mặc định. Nếu để `jpackage` tự tạo runtime và ứng dụng cần service binding, truyền `--bind-services` qua `--jlink-options` cùng các tùy chọn runtime mong muốn. Trong bài này, ta tạo runtime riêng bằng `jlink` nên kiểm soát việc liên kết provider tại bước đó.

Khi dùng `jpackage` để tự tạo runtime, có thể giữ các tùy chọn tối ưu mặc định và bổ sung service binding bằng cấu hình:

~~~bash
jpackage --type app-image --name ReportTool --module-path mods --module com.acme.reporter/com.acme.reporter.Main --jlink-options --strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services
~~~

Không bật service binding theo thói quen. Nó có thể làm runtime lớn hơn do thêm provider và dependency. Hãy kiểm tra service type, provider và hành vi thực tế của ứng dụng.

## 10. Chọn module cần đưa vào runtime

Từ kết quả `jdeps` của ứng dụng mẫu, chọn:

~~~text
java.base,java.logging
~~~

Không cần đưa module ứng dụng `com.acme.reporter` vào runtime riêng trong kiến trúc ví dụ này. Modular JAR được `jpackage` đóng gói vào application payload; runtime image chỉ chứa module JDK cần để chạy ứng dụng.

Với ứng dụng có third-party modular JAR hoặc service provider, cần phân loại module:

- JDK modules cần có trong runtime.
- Application modules và library modules cần có trong payload/module path.
- Service provider modules cần được liên kết nếu ứng dụng dùng service binding.
- Native libraries và resource ngoài module graph cần được phân phối riêng theo nền tảng.

Không xóa dependency chỉ vì runtime tạo thành công. Mục tiêu là runtime nhỏ nhưng vẫn đủ cho mọi chức năng được hỗ trợ.

## 11. Tạo custom runtime bằng jlink

`jlink` liên kết các module đã chọn cùng dependency bắc cầu để tạo runtime image.

Trên PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.logging --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build/runtime
~~~

Trên Linux hoặc macOS:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods" \
    --add-modules java.base,java.logging \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=zip-6 \
    --output build/runtime
~~~

Giải thích:

| Tùy chọn | Tác dụng |
| --- | --- |
| `--module-path` | Chỉ vị trí các JDK modules trong thư mục `jmods`. |
| `--add-modules` | Chọn các module gốc cần đưa vào runtime. |
| `--strip-debug` | Loại bỏ debug information. |
| `--no-header-files` | Không đóng gói header files. |
| `--no-man-pages` | Không đóng gói manual pages. |
| `--compress=zip-6` | Nén resource theo mức ZIP 6 được hỗ trợ trong JDK hiện hành. |
| `--output` | Thư mục runtime image đầu ra. |

`jlink` tự bổ sung dependency bắc cầu của các module được chọn. Vì vậy, không cần liệt kê thủ công mọi module mà `java.logging` hoặc module khác phụ thuộc.

Cú pháp nén `--compress=zip-6` được dùng cho JDK hiện đại. Tránh dùng các mức số `0`, `1` hoặc `2` trong cấu hình mới vì các giá trị cũ này đã được deprecated trong tài liệu JDK hiện hành.

### Service provider khi cần

Ứng dụng mẫu không dùng `ServiceLoader`, nên lệnh `jlink` ở trên không cần `--bind-services`. Với ứng dụng thực tế, xác định service type, module khai báo `uses`, provider module khai báo `provides` và nơi đặt provider. Đưa các module cần thiết vào module graph/module path của bước link, sau đó kiểm tra runtime bằng `java --list-modules` và chạy integration test cho từng provider. Không thêm `--bind-services` một cách máy móc vì nó có thể làm runtime lớn hơn và không phát hiện mọi plugin nạp bằng reflection.

## 12. Kiểm tra runtime image vừa tạo

Liệt kê module:

~~~bash
build/runtime/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
.\build\runtime\bin\java.exe --list-modules
~~~

Danh sách cần có ít nhất `java.base` và `java.logging` cùng các dependency bắc cầu do `jlink` thêm vào.

Kiểm tra phiên bản runtime:

~~~bash
build/runtime/bin/java --version
~~~

Trên Windows:

~~~powershell
.\build\runtime\bin\java.exe --version
~~~

Runtime image không phải JDK đầy đủ. Không kỳ vọng có `javac`, `javadoc` hoặc toàn bộ công cụ phát triển trong đó. Runtime cần có launcher Java và các module đủ để chạy ứng dụng.

Có thể chạy thử ứng dụng bằng runtime vừa tạo:

~~~bash
build/runtime/bin/java --module-path build/mods --module com.acme.reporter/com.acme.reporter.Main data/sales.csv reports/summary-from-runtime.txt
~~~

Trên Windows:

~~~powershell
.\build\runtime\bin\java.exe --module-path build/mods --module com.acme.reporter/com.acme.reporter.Main .\data\sales.csv .\reports\summary-from-runtime.txt
~~~

Nếu chạy thành công và tạo đúng báo cáo, ta đã kiểm tra được runtime tối giản trước khi giao cho `jpackage`.

## 13. Tạo application image bằng jpackage

Dùng modular JAR làm đầu vào và custom runtime đã tạo:

~~~powershell
jpackage --type app-image --name ReportTool --app-version 1.0.0 --module-path build/mods --module com.acme.reporter/com.acme.reporter.Main --runtime-image build/runtime --dest build/dist
~~~

Lệnh tương đương trên Linux hoặc macOS:

~~~bash
jpackage \
    --type app-image \
    --name ReportTool \
    --app-version 1.0.0 \
    --module-path build/mods \
    --module com.acme.reporter/com.acme.reporter.Main \
    --runtime-image build/runtime \
    --dest build/dist
~~~

Các tùy chọn chính:

- `--type app-image` chỉ tạo application image, chưa tạo installer.
- `--name ReportTool` đặt tên ứng dụng và launcher chính.
- `--app-version 1.0.0` đặt phiên bản sản phẩm.
- `--module-path build/mods` cung cấp modular JAR của ứng dụng.
- `--module` chọn module và main class.
- `--runtime-image build/runtime` đưa runtime đã kiểm tra vào application image.
- `--dest build/dist` chỉ thư mục đầu ra.

Khi đã truyền `--runtime-image`, `jpackage` sử dụng runtime image có sẵn. Tùy chọn này phải được dùng khi tạo application image; không truyền đồng thời với `--app-image` khi tạo package từ một application image đã có.

Application image là thư mục có cấu trúc phụ thuộc nền tảng. Ví dụ trên Linux thường có launcher trong `bin`, payload trong `lib/app` và runtime trong `lib/runtime`. Windows và macOS có cấu trúc tương ứng theo định dạng ứng dụng của từng hệ điều hành.

## 14. Kiểm tra cấu trúc application image

Sau khi đóng gói, xác nhận có ba thành phần:

1. Launcher của `ReportTool`.
2. Modular JAR và cấu hình launcher.
3. Runtime image đã tạo bằng `jlink`.

Bố cục tham khảo:

~~~text
Linux:
build/dist/ReportTool/
├── bin/
│   └── ReportTool
└── lib/
    ├── app/
    │   ├── ReportTool.cfg
    │   └── com.acme.reporter.jar
    └── runtime/
        └── bin/java

Windows:
build/dist/ReportTool/
├── ReportTool.exe
├── app/
│   ├── ReportTool.cfg
│   └── com.acme.reporter.jar
└── runtime/
    └── bin/java.exe

macOS:
build/dist/ReportTool.app/
└── Contents/
    ├── MacOS/ReportTool
    ├── app/
    └── runtime/
~~~

Tên file và một số thư mục là chi tiết triển khai có thể thay đổi theo JDK. Dùng cấu trúc thực tế do `jpackage` tạo ra để kiểm tra.

Không di chuyển riêng launcher ra khỏi application image. Launcher cần file cấu hình, payload và runtime đúng vị trí tương đối để hoạt động.

## 15. Chạy launcher và xác minh runtime được sử dụng

Các lệnh bên dưới giả định shell đang ở thư mục gốc `report-tool`. Nếu chạy từ thư mục khác, dùng đường dẫn tuyệt đối hoặc điều chỉnh đường dẫn input/output cho đúng working directory.

Trên Linux:

~~~bash
./build/dist/ReportTool/bin/ReportTool data/sales.csv reports/summary-packaged.txt
~~~

Trên Windows:

~~~powershell
.\build\dist\ReportTool\ReportTool.exe .\data\sales.csv .\reports\summary-packaged.txt
~~~

Trên macOS:

~~~bash
./build/dist/ReportTool.app/Contents/MacOS/ReportTool data/sales.csv reports/summary-packaged.txt
~~~

Kiểm tra file báo cáo có kết quả đúng. Sau đó chạy executable Java nằm trong application image để xem runtime thực tế:

Linux:

~~~bash
./build/dist/ReportTool/lib/runtime/bin/java --version
~~~

Windows:

~~~powershell
.\build\dist\ReportTool\runtime\bin\java.exe --version
~~~

macOS:

~~~bash
./build/dist/ReportTool.app/Contents/runtime/Contents/Home/bin/java --version
~~~

Đối chiếu phiên bản này với runtime đã tạo trong bước trước. Không dùng `java --version` từ terminal của máy build để kết luận runtime được đóng gói có cùng phiên bản.

## 16. Đo kích thước và đánh giá runtime

Trên Linux/macOS, có thể xem kích thước runtime và application image:

~~~bash
du -sh build/runtime build/dist/ReportTool
~~~

Trên PowerShell:

~~~powershell
$runtimeBytes = (Get-ChildItem .\build\runtime -Recurse -File | Measure-Object -Property Length -Sum).Sum
$appBytes = (Get-ChildItem .\build\dist\ReportTool -Recurse -File | Measure-Object -Property Length -Sum).Sum
"Runtime bytes: $runtimeBytes"
"Application image bytes: $appBytes"
~~~

Ghi lại:

- Kích thước runtime.
- Kích thước application image.
- Danh sách module.
- JDK vendor/version dùng để tạo runtime.
- Phiên bản ứng dụng.
- Kết quả smoke test.

Không kết luận runtime tốt hơn chỉ dựa trên kích thước. Cần xác nhận mọi chức năng vẫn hoạt động và thời gian khởi động phù hợp. Compression có thể giảm dung lượng nhưng nên đo cả kích thước lẫn hiệu năng trên workload thực tế.

## 17. Kiểm thử trên máy sạch

Application image có runtime riêng để loại bỏ phụ thuộc vào JDK cài trên máy người dùng. Hãy kiểm tra điều này trong môi trường sạch:

- Máy hoặc VM không cài JDK/JRE phát triển.
- Không có biến môi trường `JAVA_HOME` trỏ tới JDK của máy build.
- Không dựa vào `PATH` chứa Java bên ngoài.
- Có quyền đọc file đầu vào và ghi file báo cáo.
- Có đủ native dependency của hệ điều hành nếu ứng dụng hoặc thư viện sử dụng native code.

Thử nghiệm:

1. Sao chép toàn bộ application image sang máy sạch.
2. Chạy launcher chính.
3. Truyền file CSV từ một thư mục khác.
4. Ghi báo cáo vào thư mục đầu ra chưa tồn tại.
5. Kiểm tra log và file báo cáo.
6. Thử đường dẫn có khoảng trắng và ký tự Unicode.
7. Thử file không tồn tại, file rỗng và dữ liệu không hợp lệ.
8. Xác nhận chương trình trả exit code phù hợp.
9. Xác nhận không cần cài JDK ngoài.

Nếu ứng dụng chỉ chạy khi JDK phát triển được cài, kiểm tra launcher có thực sự dùng runtime đi kèm, file runtime có bị thiếu và thư viện native có được phân phối đúng hay không.

## 18. Dependency động, locale và native library

Runtime tối giản chỉ đúng khi tập module và tài nguyên đã được xác định đầy đủ.

### Reflection và plugin

Nếu ứng dụng nạp class từ tên cấu hình hoặc plugin folder, bổ sung module/classpath cần thiết và kiểm thử từng plugin. `jdeps` không thể suy ra mọi class sẽ được tạo tên động.

### ServiceLoader

Nếu ứng dụng dùng `ServiceLoader`, kiểm tra module descriptor có khai báo `uses` và provider module có khai báo `provides` phù hợp. Khi tạo runtime bằng `jlink`, cân nhắc `--bind-services` và kiểm tra module provider thực sự có trong image.

### Locale

Nếu ứng dụng cần locale data cụ thể, kiểm tra module `jdk.localedata`. Có thể dùng plugin `--include-locales` của `jlink` để giới hạn locale cần đóng gói:

~~~bash
jlink --add-modules java.base,java.logging,jdk.localedata --include-locales=vi,en --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output build/runtime
~~~

Chỉ dùng ví dụ này khi ứng dụng thực sự cần locale data và đã kiểm tra các locale được hỗ trợ. Nếu không, đừng thêm module chỉ để dự phòng.

### Native library

`jlink` không tự động thu thập mọi thư viện native bên ngoài JDK. Nếu thư viện bên thứ ba cần DLL, SO hoặc dylib, phải phân phối đúng file cho OS/CPU mục tiêu và kiểm tra đường dẫn nạp thư viện trên máy sạch.

## 19. Cập nhật và phát hành runtime

Custom runtime là một phần của sản phẩm. Nó không tự cập nhật khi máy người dùng cài JDK mới hoặc khi nhà cung cấp JDK phát hành bản vá.

Mỗi lần phát hành cần:

1. Chọn JDK vendor và phiên bản cập nhật được tổ chức hỗ trợ.
2. Build lại modular JAR nếu cần.
3. Chạy lại `jdeps` và review module dependencies.
4. Tạo lại runtime bằng `jlink` từ JDK mới.
5. Tạo lại application image bằng `jpackage`.
6. Chạy regression test trên máy sạch.
7. Kiểm tra version runtime nằm trong application image.
8. Phát hành artifact mới cùng thông tin JDK/runtime tương ứng.

Không lấy runtime cũ và chỉ thay file `java` bằng executable mới. Runtime image gồm nhiều module, native library và metadata phải đồng bộ theo cùng một JDK build.

### Nền tảng và kiến trúc

Runtime image do `jlink` tạo gắn với nền tảng và kiến trúc của JDK dùng để tạo nó. Application image cũng cần được tạo và kiểm thử trên nền tảng đích.

Để phân phối Windows x64, Linux x64 và macOS ARM64, chuẩn bị pipeline build/package tương ứng cho từng nền tảng. Không dùng một runtime image của Windows cho Linux hoặc macOS.

## 20. Lỗi thường gặp và cách khắc phục

1. **Chọn module theo cảm tính:** chạy `jdeps --print-module-deps` và review kết quả.
2. **Cho rằng jdeps tìm được mọi dependency:** kiểm tra reflection, ServiceLoader, plugin, resource và native library.
3. **Bỏ qua module ứng dụng:** bảo đảm modular JAR vẫn được truyền qua `--module-path` và `--module` của `jpackage`.
4. **Đưa toàn bộ JDK vào runtime:** dùng `jlink` để chọn module cần thiết thay vì phân phối nguyên JDK.
5. **Quên dependency bắc cầu:** `jlink` tự phân giải dependency của module gốc; không bỏ qua lỗi module resolution.
6. **Dùng --ignore-missing-deps để che lỗi:** giải quyết dependency bị thiếu trước khi tạo runtime.
7. **Bỏ service provider:** kiểm tra `uses`/`provides` và `--bind-services` khi ứng dụng cần service binding.
8. **Cho rằng jpackage JDK mới vẫn bind service mặc định:** từ JDK 25, kiểm tra và thêm `--bind-services` khi cần.
9. **Dùng compression syntax cũ:** dùng cú pháp hiện hành như `--compress=zip-6`.
10. **Dùng runtime không cùng nền tảng:** tạo runtime và application image trên đúng OS/CPU đích.
11. **Chỉ kiểm tra trên máy có JDK:** cài/chạy trên VM sạch để phát hiện phụ thuộc môi trường.
12. **Không cập nhật runtime:** custom runtime cần được rebuild và phát hành khi cập nhật JDK.
13. **Đo kích thước mà không test chức năng:** runtime nhỏ nhưng thiếu module không phải kết quả đạt.
14. **Đặt resource ngoài application image:** đưa file cấu hình, template và dữ liệu mặc định cần thiết vào payload hoặc xác định rõ vị trí cung cấp lúc chạy.

## 21. Checklist hoàn thành bài thực hành

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Modular descriptor | Khai báo đúng dependency trực tiếp. |
| Modular JAR | Có module descriptor và main class. |
| Static dependency | Đã xem kết quả `jdeps --print-module-deps`. |
| Missing dependency | Không còn dependency tĩnh chưa giải quyết. |
| Dynamic dependency | Reflection, service, plugin và native library đã được rà soát. |
| Runtime modules | Chỉ chứa module cần thiết cùng dependency bắc cầu. |
| Runtime image | `jlink` tạo thành công. |
| Runtime version | `java --version` từ runtime image đúng phiên bản mục tiêu. |
| Application image | Có launcher, payload và runtime. |
| Launcher test | Chạy đúng trên máy build và máy sạch. |
| Output test | File báo cáo có dữ liệu mong đợi. |
| Platform | Runtime và image khớp OS/CPU mục tiêu. |
| Update plan | Có quy trình rebuild runtime khi JDK được cập nhật. |

## 22. Bài tập mở rộng

1. Thêm module `java.sql` và một JDBC driver modular; phân tích module dependency và service provider.
2. So sánh runtime khi bật và không bật `--bind-services`.
3. Thêm locale tiếng Việt và tiếng Anh bằng `jdk.localedata`, sau đó kiểm tra format ngày và số.
4. Thêm một plugin được nạp bằng reflection và xác định cách đưa plugin vào application image.
5. Tạo custom runtime cho một ứng dụng modular có hai library module.
6. So sánh kích thước runtime do `jpackage` tự tạo với runtime do `jlink` tạo thủ công.
7. Chạy application image trong VM không có JDK và lưu kết quả smoke test.
8. Tạo pipeline build cho hai nền tảng khác nhau và ghi lại JDK/runtime version của từng artifact.
9. Kiểm tra `jdeps --jdk-internals` để xác nhận không phụ thuộc JDK internal API.
10. Viết manifest phát hành gồm application version, JDK vendor/version, module list, OS/architecture và checksum của application archive.

## Ghi nhớ

`jdeps` phân tích dependency tĩnh và có thể in danh sách module dùng cho `jlink`. `jlink` tạo runtime image từ các module được chọn cùng dependency bắc cầu; `jpackage` ghép modular application với runtime đó thành application image có launcher. Runtime tối giản phải được kiểm tra bằng `java --list-modules`, `java --version` và smoke test trên máy sạch. Phân tích tĩnh không phát hiện mọi dependency được nạp bằng reflection, service loading, plugin hoặc native library, nên phải kiểm thử các đường chạy thực tế. Từ JDK 25, service bindings không còn được `jpackage` đưa vào runtime mặc định; chỉ thêm `--bind-services` khi ứng dụng cần provider. Custom runtime là một phần của sản phẩm và phải được cập nhật, kiểm thử, đóng gói lại theo từng JDK và nền tảng đích.

**Tài liệu tham khảo chính thức:**

- [JEP 392 – Packaging Tool](https://openjdk.org/jeps/392)
- [JDK 26 – jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [JDK 26 – jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [JDK 26 – jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [JDK 26 – Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Java Language Specification – Module declarations](https://docs.oracle.com/javase/specs/jls/se16/html/jls-7.html#jls-7.7)
