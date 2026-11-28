# Chẩn đoán thiếu dependency, launcher thoát sớm và tài nguyên không tìm thấy

> **Chương:** Bộ cài ứng dụng  
> **Học phần:** `JAVA_VERSION_JAVA16` — tìm hiểu cách đóng gói JDK và ứng dụng Java bằng jpackage, sau đó chẩn đoán các lỗi thường gặp khi phân phối. Bài này tập trung vào dependency không được đóng gói hoặc không được nạp, launcher thoát sớm và tài nguyên không tìm thấy trong application image hoặc native installer.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt lỗi của application image với lỗi riêng của native installer.
- Kiểm tra JAR, module, native library và service provider bị thiếu.
- Hiểu classpath và module path mà jpackage tạo cho launcher.
- Xác minh main JAR, main class, main module, JVM options và application arguments.
- Chẩn đoán launcher thoát sớm bằng log, console và cấu hình launcher.
- Phân biệt tài nguyên nằm trong JAR với file nằm trong application image.
- Tránh phụ thuộc vào working directory khi đọc file bên ngoài.
- Dùng `$APPDIR` để tham chiếu tài nguyên đi cùng ứng dụng.
- Kiểm tra runtime image, module cần thiết và thay đổi service binding trên JDK mới.
- Xây dựng quy trình kiểm thử application image và installer trên hệ điều hành đích.

## 1. Vì sao ứng dụng chạy được trong IDE nhưng lỗi sau khi cài?

Trong IDE, ứng dụng thường chạy với classpath hoặc module path do build tool thiết lập, JDK đầy đủ, working directory của project và tài nguyên có sẵn trong cây thư mục phát triển. Khi đóng gói bằng `jpackage`, ứng dụng chuyển sang một application image có launcher và runtime riêng.

Một số khác biệt có thể làm lộ lỗi:

- Một JAR dependency có trong IDE nhưng không có trong thư mục đầu vào của jpackage.
- Launcher dùng main class hoặc module không đúng.
- Runtime image thiếu module JDK hoặc provider module mà ứng dụng cần.
- Cấu hình `-cp` tự đặt ghi đè classpath mặc định của launcher.
- Ứng dụng đọc file bằng đường dẫn tương đối và giả định working directory là thư mục project.
- File cấu hình hoặc tài nguyên tĩnh không được đưa vào application image.
- Ứng dụng dùng native library nhưng thiếu file phù hợp với OS hoặc kiến trúc.
- Ứng dụng GUI thoát sớm nhưng không có console để hiển thị lỗi.
- Bản cài đặt được tạo trên một môi trường nhưng lại được kiểm tra trên OS, quyền hoặc kiến trúc khác.

Cần kiểm tra riêng ba lớp: **đầu vào đóng gói**, **application image và launcher**, **môi trường cài đặt**. Làm theo thứ tự này giúp khoanh vùng lỗi nhanh hơn.

## 2. Phân biệt application image và native installer

`jpackage` có thể tạo application image bằng `--type app-image` hoặc tạo gói cài đặt native như EXE/MSI, DEB/RPM, PKG/DMG.

Application image đã chứa launcher, ứng dụng và runtime image. Nó là mốc kiểm thử quan trọng trước khi điều tra installer.

| Kết quả kiểm thử | Khả năng cần điều tra |
| --- | --- |
| Application image không khởi động | Dependency, main class/module, runtime image, launcher config, tài nguyên hoặc native library |
| Application image chạy tốt nhưng installer lỗi | Cài đặt, quyền, shortcut, package metadata, signing hoặc yêu cầu công cụ của OS |
| Chạy được từ terminal nhưng mở từ menu thì lỗi | Working directory, biến môi trường, arguments, JVM options hoặc quyền của user |
| Chạy được trên máy build nhưng lỗi trên máy sạch | Dependency ngoài JDK, native library, OS runtime hoặc file bị thiếu trong package |

Tạo application image trước:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --main-class com.example.report.Main --dest build/app-image
```

Chạy thử launcher trong application image trên chính OS sẽ phân phối. Nếu bước này thất bại, chưa cần tập trung vào cơ chế cài đặt của EXE, MSI, DEB, RPM, PKG hay DMG.

Khi application image đã chạy đúng, mới tạo installer từ image đó:

```bash
jpackage --type <installer-type-for-host> --name ReportDesk --app-image build/app-image/ReportDesk --dest build/installer
```

Thay `<installer-type-for-host>` bằng định dạng phù hợp với máy build, ví dụ `msi` hoặc `exe` trên Windows, `deb` hoặc `rpm` trên Linux, `pkg` hoặc `dmg` trên macOS. jpackage tạo package native trên nền tảng đích; không hỗ trợ cross-platform packaging.

## 3. Kiểm tra thư mục đầu vào và các JAR dependency

Với ứng dụng không modular, `--input` chỉ định thư mục chứa các file được đưa vào application image. `--main-jar` xác định JAR chính có main class. Mặc định, jpackage tạo classpath gồm đường dẫn đến từng JAR trong thư mục `--input`.

Ví dụ staging directory:

```text
staging/
  report-desk.jar
  reporting-core.jar
  database-driver.jar
  json-codec.jar
  config/
    app.properties
```

Các điểm cần kiểm tra:

- Tên file trong `--main-jar` phải khớp chính xác file nằm trong `--input`.
- Main class phải tồn tại trong JAR chính.
- Mọi JAR dependency cần thiết phải nằm trong input directory.
- Không bỏ sót dependency được thêm động theo profile hoặc theo môi trường.
- Kiểm tra các JAR có cùng tên nhưng khác phiên bản; tránh đóng gói nhầm bản.
- Nếu có file native, kiểm tra file đó được đóng gói và có thể nạp trên OS đích.

Nếu launcher báo `ClassNotFoundException` hoặc `NoClassDefFoundError`, hãy xác định tên class bị thiếu, JAR nào cung cấp class đó và classpath thực tế của launcher. Việc file xuất hiện trong image chưa đủ chứng minh class loader đã nạp được nó.

## 4. Cẩn thận khi tự ghi đè classpath bằng --java-options

jpackage tự tạo classpath mặc định từ các JAR trong thư mục `--input`. Nếu bạn đặt `-cp`, `-classpath` hoặc `-Djava.class.path` thông qua `--java-options`, cấu hình tự đặt sẽ ghi đè classpath mặc định.

Ví dụ dễ gây lỗi:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --java-options "-cp \$APPDIR/report-desk.jar" --dest build/app-image
```

Nếu staging còn có `reporting-core.jar` và `database-driver.jar`, classpath tự đặt ở trên chỉ giữ lại JAR chính. Các JAR khác vẫn có thể xuất hiện trong image nhưng không còn nằm trên classpath của launcher.

Nếu thật sự cần tự cấu hình classpath, hãy liệt kê đầy đủ tất cả JAR và thư mục cần thiết, đồng thời dùng đúng path separator của nền tảng. Nếu không có yêu cầu đặc biệt, nên giữ classpath mặc định do jpackage tạo.

Khi kiểm tra application image, có thể xem file cấu hình launcher dạng `<application-name>.cfg` trong thư mục `app` để đối chiếu classpath, arguments và Java options. Đây là file cấu hình được jpackage tạo; dùng nó để chẩn đoán, không coi định dạng nội bộ là API ổn định để chỉnh sửa thủ công lâu dài.

## 5. Chẩn đoán dependency của ứng dụng modular

Với ứng dụng modular, launcher được cấu hình bằng `--module-path` và `--module`. Module chính phải có mặt trên module path; module graph cần chứa các dependency mà ứng dụng sử dụng.

Ví dụ:

```bash
jpackage --type app-image --module-path mods --module com.example.report/com.example.report.Main --dest build/app-image
```

Nếu thiếu module hoặc package cần thiết, hãy kiểm tra:

- Module chính có đúng tên và có trong module path không?
- Các module phụ thuộc có trong module path không?
- Module descriptor có khai báo `requires` cho dependency không?
- Module có export package mà consumer cần truy cập không?
- Có module bổ sung nào chỉ được nạp qua reflection, plugin hoặc cấu hình không?
- Có provider module nào được tìm qua `ServiceLoader` không?

Dùng `--add-modules` khi cần đưa thêm module vào runtime image:

```bash
jpackage --type app-image --module-path mods --module com.example.report/com.example.report.Main --add-modules java.logging,java.sql --dest build/app-image
```

Chỉ thêm module mà ứng dụng thực sự cần. Không nên thêm một danh sách lớn để che việc chưa xác định dependency.

Với JAR/module phức tạp, có thể dùng `jdeps` trên JDK build để phân tích dependency. Kết quả phân tích tĩnh cần được đối chiếu với đường chạy thực tế, vì reflection, plugin và service loading có thể tạo dependency không thể hiện đầy đủ qua tham chiếu bytecode trực tiếp.

## 6. Lưu ý service provider khi dùng JDK 25 trở lên

Một thay đổi quan trọng trong jpackage hiện đại: từ JDK 25, runtime image do jpackage tạo không còn tự bao gồm service bindings như các bản trước. Nếu ứng dụng modular dựa vào service provider modules được phát hiện qua JPMS, một provider có thể không có trong runtime image dù module chính vẫn được đóng gói.

Với trường hợp đó, truyền tùy chọn `--bind-services` cho jlink thông qua `--jlink-options`:

```bash
jpackage --type app-image --module-path mods --module com.example.report/com.example.report.Main --jlink-options --bind-services --dest build/app-image
```

Nếu cần giữ cả các tùy chọn jlink mặc định và thêm service binding, chỉ định đầy đủ các tùy chọn cần thiết:

```bash
jpackage --type app-image --module-path mods --module com.example.report/com.example.report.Main --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" --dest build/app-image
```

Thay đổi này liên quan đến service binding của module runtime. Nếu ứng dụng không dùng provider module hoặc provider nằm trong JAR classpath, hãy kiểm tra theo cách đóng gói tương ứng:

- Với classpath application, bảo đảm JAR chứa provider và file `META-INF/services/...` được đưa vào input và có mặt trên classpath.
- Với modular application, kiểm tra khai báo `uses` và `provides` trong module descriptor, module path và service binding.
- Kiểm thử đường chạy thực tế có gọi `ServiceLoader`; không kết luận chỉ từ việc image tạo thành công.

Không thêm `--bind-services` một cách máy móc cho mọi ứng dụng. Chỉ dùng khi ứng dụng modular thực sự cần các provider module được liên kết vào runtime image.

## 7. Kiểm tra runtime image và module JDK bị thiếu

jpackage dùng `jlink` để tạo runtime image nếu bạn không cung cấp `--runtime-image`. Runtime được tạo nhằm chứa các module cần thiết cho ứng dụng, không phải một bản JDK đầy đủ.

Nếu ứng dụng dùng API thuộc module JDK không có trong runtime image, launcher có thể thất bại với lỗi như `NoClassDefFoundError`, `ClassNotFoundException` hoặc lỗi khởi tạo module.

Quy trình:

1. Xác định API hoặc class JDK bị thiếu từ stack trace.
2. Tìm module JDK chứa API đó.
3. Với ứng dụng modular, kiểm tra module graph và `requires`.
4. Nếu module cần được thêm rõ ràng, dùng `--add-modules`.
5. Tạo lại application image và chạy lại trên OS đích.

Ví dụ ứng dụng cần `java.sql`:

```bash
jpackage --type app-image --input staging --main-jar report-desk.jar --main-class com.example.report.Main --module-path "$JAVA_HOME/jmods" --add-modules java.sql --dest build/app-image
```

Nếu bạn tự tạo runtime bằng jlink rồi truyền qua `--runtime-image`, hãy xác minh runtime image được tạo từ JDK phù hợp với target OS/architecture và có đủ module. Một runtime image đã bị thu gọn không thể tự bổ sung module còn thiếu chỉ bằng cách thay launcher config.

## 8. Dependency native không giống JAR dependency

Một số thư viện Java gọi mã native qua JNI hoặc cơ chế tương tự. Trong trường hợp này, JAR có thể đã được đóng gói nhưng ứng dụng vẫn lỗi `UnsatisfiedLinkError` vì thiếu hoặc không nạp được thư viện native.

Kiểm tra:

- File `.dll`, `.so` hoặc `.dylib` có được đưa vào application image không?
- File có đúng OS và kiến trúc CPU của máy đích không?
- Thư viện có phụ thuộc vào shared library khác mà máy đích chưa cài không?
- Đường dẫn nạp native library có được cấu hình đúng không?
- Phiên bản ABI của native library có tương thích với ứng dụng và hệ điều hành không?

Nếu cần tham chiếu thư mục native nằm trong application image, có thể dùng macro `$APPDIR` trong JVM option:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --java-options "-Djava.library.path=\$APPDIR/native" --dest build/app-image
```

Đảm bảo thư mục `native` và các file thư viện thực sự được đóng gói. Cấu hình `java.library.path` chỉ giúp JVM tìm thư viện ở vị trí đã chỉ định; nó không tự đóng gói hoặc giải quyết dependency hệ điều hành của thư viện đó.

Trên máy đích, kiểm tra thêm dependency native theo công cụ của OS, ví dụ `ldd` trên Linux, `otool -L` trên macOS hoặc công cụ kiểm tra dependency DLL phù hợp trên Windows. Kiểm thử trên đúng kiến trúc và OS sẽ phát hiện lỗi mà máy build có thể không gặp.

## 9. Launcher thoát sớm: kiểm tra main entry point

Launcher có thể mở rồi thoát ngay nếu không tìm thấy entry point hoặc không thể khởi tạo ứng dụng.

Với ứng dụng không modular:

- `--main-jar` phải trỏ đến JAR có trong input directory.
- `--main-class` phải là tên đầy đủ của lớp chứa `public static void main(String[] args)`.
- Lớp main phải nằm trong JAR hoặc classpath của launcher.
- Kiểm tra package name và chữ hoa/chữ thường.
- Nếu dùng manifest để xác định main class, xác nhận manifest có giá trị đúng.

Với ứng dụng modular:

- `--module` phải chỉ đúng tên module.
- Main class phải nằm trong module đó, trừ khi entry point được xác định theo descriptor.
- Module path phải chứa module chính và dependency.
- Không truyền đồng thời `--module` và `--main-jar`.

Ví dụ khai báo launcher cho JAR:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --main-class com.example.report.Main --dest build/app-image
```

Nếu launcher đã tạo nhưng chạy không vào main method, hãy chạy JAR bằng JDK tương ứng để so sánh:

```bash
java -cp "staging/*" com.example.report.Main
```

Nếu lệnh Java thông thường cũng lỗi, hãy sửa ứng dụng hoặc dependency trước. Nếu lệnh này chạy được nhưng launcher image không chạy, tập trung vào cấu hình classpath, runtime image, JVM options và launcher config.

## 10. Launcher thoát sớm nhưng không hiển thị lỗi

Một ứng dụng GUI có thể được khởi chạy từ shortcut hoặc menu hệ điều hành mà không có cửa sổ console. Lỗi khởi tạo, exception hoặc log ghi ra stderr có thể không xuất hiện trước mắt người dùng.

Cách chẩn đoán:

- Trên Linux, chạy launcher trong terminal để xem stdout/stderr.
- Trên macOS, chạy executable của ứng dụng từ Terminal để quan sát thông báo; mở bundle bằng Finder có thể không cung cấp console tương tác.
- Trên Windows, tạo console launcher trong bản debug bằng `--win-console`. Đây là tùy chọn dành riêng cho Windows.
- Bổ sung log khởi động vào vị trí có thể ghi được bởi user.
- Ghi lại exception đầy đủ và nguyên nhân gốc, không chỉ ghi một dòng "startup failed".

Ví dụ tạo application image có console trên Windows:

```powershell
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --main-class com.example.report.Main --win-console --dest build/app-image-debug
```

Không cần phát hành bản GUI production với console nếu thiết kế không yêu cầu. Có thể duy trì một cấu hình debug riêng để hỗ trợ chẩn đoán.

## 11. Kiểm tra arguments và JVM options của launcher

Launcher có thể chạy được nhưng ứng dụng thoát sớm do arguments hoặc JVM options sai.

jpackage hỗ trợ:

- `--arguments`: giá trị mặc định truyền cho main class khi người dùng không cung cấp arguments.
- `--java-options`: tùy chọn truyền cho JVM khi launcher khởi chạy.
- `--add-launcher`: tạo launcher phụ với cấu hình khác.

Ví dụ:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --main-class com.example.report.Main --arguments "--mode desktop" --java-options "-Xms128m" --dest build/app-image
```

Nếu launcher cần file cấu hình nằm cùng application image, có thể tham chiếu bằng `$APPDIR` trong JVM property. File phải được đưa vào input directory:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --main-class com.example.report.Main --java-options "-Dapp.config=\$APPDIR/config/app.properties" --dest build/app-image
```

Trong shell POSIX, escape dấu `$` để shell không mở rộng biến trước khi jpackage xử lý macro. Kiểm tra `--help` của JDK đang dùng và quoting theo shell trên Windows/macOS/Linux.

Nếu ứng dụng thoát sớm sau khi nhận arguments, hãy xác minh nội dung trong `app-name.cfg` và đối chiếu với lệnh đóng gói. File cấu hình này hữu ích để chẩn đoán arguments và Java options mà launcher đang sử dụng.

## 12. Tài nguyên không tìm thấy: phân biệt resource trong JAR và file ngoài

Có hai nhóm tài nguyên thường bị nhầm:

1. **Classpath/module resource:** file được đóng gói bên trong JAR hoặc module và được truy cập qua class loader/module.
2. **Filesystem resource:** file cấu hình, chứng thư, dữ liệu, template hoặc file người dùng nằm bên ngoài JAR.

Cách tải hai loại này khác nhau.

### 12.1. Tài nguyên nằm trong JAR

Nếu resource nằm trong JAR, dùng class loader hoặc class tương ứng để đọc:

```java
try (var input = ReportApplication.class
        .getResourceAsStream("/config/default.properties")) {

    if (input == null) {
        throw new IllegalStateException(
                "Missing classpath resource: /config/default.properties"
        );
    }

    var properties = new java.util.Properties();
    properties.load(input);
}
```

Đường dẫn resource phải khớp chính xác với entry trong JAR. Kiểm tra bằng `jar tf report-desk.jar` và chú ý chữ hoa/chữ thường. Đừng dùng `new File("config/default.properties")` để đọc một resource vốn nằm bên trong JAR.

### 12.2. File nằm ngoài JAR

Nếu ứng dụng cần file cấu hình có thể thay đổi, đóng gói file đó cùng application image hoặc cung cấp đường dẫn từ cấu hình launcher.

Không dựa vào working directory hiện tại:

```java
Path config = Path.of("config", "app.properties");
```

Đường dẫn tương đối trên có thể hoạt động trong IDE nhưng thất bại khi người dùng mở ứng dụng từ Start Menu, desktop shortcut, Finder hoặc menu Linux. Working directory không phải cam kết của launcher.

Dùng một đường dẫn tuyệt đối được truyền vào ứng dụng:

```java
String configValue = System.getProperty("app.config");

if (configValue == null || configValue.isBlank()) {
    throw new IllegalStateException("Missing app.config system property");
}

Path configPath = Path.of(configValue);

if (!Files.isRegularFile(configPath)) {
    throw new IllegalStateException(
            "Configuration file does not exist: " + configPath
    );
}
```

Nếu file đi cùng image, truyền đường dẫn bằng `$APPDIR` như phần trước. Nếu file là dữ liệu người dùng có thể chỉnh sửa, hãy lưu ở thư mục cấu hình hoặc dữ liệu của user, không ghi vào thư mục cài đặt có thể chỉ đọc hoặc cần quyền quản trị.

## 13. Phân biệt --resource-dir với tài nguyên ứng dụng

`--resource-dir` dùng để thay thế tài nguyên của chính công cụ jpackage, chẳng hạn icon, launcher properties hoặc template installer. Nó không tự động thêm file cấu hình hoặc ảnh mà code ứng dụng đang tải lúc runtime.

Để đưa file vào payload ứng dụng:

- Đặt JAR và file cần đóng gói trong `--input`.
- Hoặc dùng `--app-content` để thêm file/thư mục vào application payload.
- Với resource bên trong JAR, xác nhận entry đã được đóng gói vào JAR.
- Với file ngoài JAR, xác định rõ vị trí trong image và truyền đường dẫn runtime phù hợp.

Ví dụ thêm thư mục nội dung:

```bash
jpackage --type app-image --input staging --name ReportDesk --main-jar report-desk.jar --app-content extra-data --dest build/app-image
```

Sau khi tạo image, kiểm tra file thực tế có mặt ở vị trí dự kiến. Không suy luận từ việc lệnh jpackage thành công rằng mọi resource runtime đều đã được code ứng dụng tham chiếu đúng.

## 14. Kiểm tra application image trước khi cài đặt

Application image giúp kiểm tra launcher, classpath, runtime và resource mà không cần đưa installer vào quá trình điều tra.

Checklist:

- [ ] Launcher tồn tại trong thư mục image.
- [ ] Main JAR hoặc module có trong image.
- [ ] Các JAR dependency được đóng gói và có trên classpath.
- [ ] Module path và module cần thiết được cấu hình đúng.
- [ ] Runtime image có đủ module JDK.
- [ ] Service provider được đóng gói đúng với loại ứng dụng.
- [ ] Native library đúng OS và kiến trúc.
- [ ] Resource trong JAR có thể đọc bằng class loader.
- [ ] File ngoài JAR tồn tại và đường dẫn runtime đúng.
- [ ] Arguments và JVM options đúng.
- [ ] Launcher chạy được từ terminal hoặc console debug.

Sau đó kiểm tra installer trên máy thử nghiệm sạch, nơi không có JDK phát triển hoặc dependency vô tình được cài sẵn. Đây là cách phát hiện việc ứng dụng dựa vào môi trường máy build.

## 15. Khác biệt giữa máy build và máy cài đặt

Một package có thể chạy trên máy build nhưng lỗi ở máy người dùng do môi trường khác nhau:

| Khác biệt | Triệu chứng có thể gặp | Cách kiểm tra |
| --- | --- | --- |
| OS hoặc kiến trúc CPU | Native library không nạp được | Build và test trên đúng OS/architecture |
| Native runtime dependency | Thiếu DLL/shared library | Kiểm tra dependency native trên máy sạch |
| Quyền thư mục | Không đọc/ghi được file cấu hình hoặc log | Dùng thư mục dữ liệu của user và kiểm tra ACL/permission |
| Biến môi trường | Không tìm thấy file hoặc executable | Tránh phụ thuộc PATH và biến chỉ có trên máy build |
| Working directory | File tương đối không tìm thấy | Dùng classpath resource hoặc đường dẫn từ APPDIR/config |
| JDK build khác JDK runtime | Module hoặc hành vi runtime khác | Ghi rõ JDK dùng để đóng gói và kiểm thử image |
| Service provider | Không tìm thấy provider | Kiểm tra service binding và cấu hình jlink |
| Cài đặt native | Shortcut hoặc package metadata sai | Kiểm tra installer trên host cùng nền tảng |

jpackage đóng gói Java runtime và application payload theo cấu hình. Nó không tự động đóng gói mọi thư viện hệ điều hành, driver, database server, executable bên ngoài hoặc dịch vụ mà ứng dụng phụ thuộc.

Với package Linux, có thể khai báo dependency package hệ điều hành bằng tùy chọn phù hợp như `--linux-package-deps`. Trên Windows và macOS, kiểm tra yêu cầu runtime native, signing và thư viện hệ thống theo nền tảng.

## 16. Quy trình chẩn đoán theo triệu chứng

### Thiếu class hoặc JAR

1. Đọc exception để lấy tên class.
2. Xác định JAR chứa class.
3. Kiểm tra JAR nằm trong `--input`.
4. Kiểm tra classpath launcher có bao gồm JAR.
5. Nếu đã tự đặt `-cp` bằng `--java-options`, kiểm tra danh sách có ghi đè classpath mặc định không.
6. Tạo lại app image và thử trên máy sạch.

### Thiếu module hoặc provider

1. Xác định module chứa API hoặc provider.
2. Kiểm tra module graph và module path.
3. Bổ sung `--add-modules` khi cần.
4. Nếu modular service provider không có trong runtime image của JDK 25+, xem xét `--jlink-options --bind-services`.
5. Chạy lại chức năng thực tế có sử dụng provider.

### Launcher thoát ngay

1. Chạy launcher từ terminal hoặc tạo Windows console launcher để xem lỗi.
2. Kiểm tra main JAR, main class hoặc main module.
3. Kiểm tra arguments và JVM options.
4. Xem file cấu hình launcher do jpackage tạo.
5. Kiểm tra startup log và exception đầu tiên.
6. So sánh với lệnh Java chạy trực tiếp trên cùng JDK.

### Resource không tìm thấy

1. Xác định resource nằm trong JAR hay filesystem.
2. Nếu trong JAR, kiểm tra entry bằng `jar tf` và dùng `getResourceAsStream`.
3. Nếu là file ngoài JAR, xác nhận file được đóng gói.
4. Không dựa vào working directory.
5. Dùng `$APPDIR` hoặc đường dẫn cấu hình tuyệt đối.
6. Kiểm tra chữ hoa/chữ thường và quyền đọc file.

### Installer chạy khác application image

1. Xác nhận application image đã chạy thành công.
2. Cài package trên máy thử nghiệm sạch.
3. Kiểm tra đường dẫn cài đặt, shortcut và quyền.
4. Kiểm tra native dependency và package dependency của OS.
5. Thu thập log của launcher và OS để phân biệt lỗi cài đặt với lỗi ứng dụng.

## 17. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `ClassNotFoundException` | Thiếu JAR hoặc classpath sai | Kiểm tra input và classpath launcher |
| `NoClassDefFoundError` | Dependency có mặt lúc compile nhưng thiếu lúc runtime, hoặc khởi tạo class thất bại | Đọc cause gốc và kiểm tra dependency runtime |
| `FindException` hoặc `ModuleNotFoundException` | Module không có trong module path/runtime image | Kiểm tra `--module-path`, `--module`, `--add-modules` |
| `ServiceConfigurationError` hoặc không tìm thấy provider | Thiếu provider JAR/module hoặc service binding | Kiểm tra `META-INF/services`, `uses/provides`, `--bind-services` |
| `UnsatisfiedLinkError` | Native library thiếu, sai kiến trúc hoặc thiếu dependency hệ điều hành | Kiểm tra file native và shared-library dependency |
| Launcher thoát không thông báo | GUI launcher không có console hoặc log chưa được cấu hình | Chạy từ terminal, dùng `--win-console` trên Windows, ghi startup log |
| Main class not found | Sai `--main-class`, `--main-jar` hoặc module entry point | Kiểm tra cấu hình launcher |
| `FileNotFoundException` | Đường dẫn tương đối hoặc file không có trong image | Dùng resource API hoặc đường dẫn tuyệt đối |
| Resource trả về `null` | Sai resource name, sai chữ hoa/chữ thường hoặc JAR thiếu entry | Kiểm tra bằng `jar tf` và class loader |
| Chạy trong IDE nhưng lỗi sau cài | IDE cung cấp dependency, biến môi trường hoặc working directory khác | Test app image và máy sạch |
| Image chạy nhưng installer lỗi | Vấn đề package, quyền, shortcut hoặc native toolchain | Điều tra installer riêng trên OS đích |

Không nên chỉ ghi nhận thông báo ngoài cùng. Hãy tìm exception đầu tiên, cause gốc và đường dẫn hoặc module được nhắc trong stack trace.

## 18. Bài tập tự luyện

### Bài 1: Thiếu dependency sau khi cài

Ứng dụng chạy trong IDE nhưng báo `ClassNotFoundException` sau khi đóng gói. JAR dependency có trong thư mục build nhưng không có trong thư mục `--input`. Cần sửa ở đâu?

**Đáp án:** Đưa JAR dependency vào input directory của jpackage hoặc cấu hình đóng gói tương ứng để nó được đưa vào application image. Sau đó xác nhận classpath launcher chứa JAR đó.

### Bài 2: Tự đặt classpath

Một lệnh jpackage dùng `--java-options "-cp $APPDIR/report-desk.jar"` trong khi input có thêm hai JAR dependency. Vì sao ứng dụng có thể lỗi?

**Đáp án:** Classpath tự đặt ghi đè classpath mặc định do jpackage tạo từ các JAR trong input. Cần bỏ tùy chọn classpath nếu không cần, hoặc liệt kê đầy đủ tất cả JAR và thư mục cần thiết.

### Bài 3: Service provider biến mất trên JDK mới

Ứng dụng modular dùng `ServiceLoader` và chạy tốt với runtime image cũ, nhưng provider module không còn được tìm thấy sau khi đóng gói bằng JDK 25 trở lên. Cần kiểm tra gì?

**Đáp án:** Kiểm tra module provider và service binding trong runtime image. Nếu ứng dụng cần liên kết service provider modules, truyền `--bind-services` qua `--jlink-options`, rồi kiểm thử lại chức năng dùng `ServiceLoader`.

### Bài 4: Launcher thoát khi mở từ shortcut

Ứng dụng chạy được từ terminal nhưng mở từ shortcut Windows thì thoát mà không có thông báo. Cách chẩn đoán phù hợp là gì?

**Đáp án:** Tạo application image debug với `--win-console` để xem lỗi, kiểm tra arguments/JVM options và ghi startup log vào thư mục user có quyền ghi. Không giả định shortcut dùng cùng working directory với terminal.

### Bài 5: File cấu hình không tìm thấy

Ứng dụng đọc `config/app.properties` bằng đường dẫn tương đối. Trong IDE file tồn tại nhưng sau khi cài đặt thì không tìm thấy. Nên thay đổi cách đọc thế nào?

**Đáp án:** Nếu file là tài nguyên bất biến trong JAR, dùng `getResourceAsStream`. Nếu là file ngoài JAR đi cùng image, đóng gói file và truyền đường dẫn dựa trên `$APPDIR` hoặc cấu hình tuyệt đối. Nếu file người dùng chỉnh sửa, lưu trong thư mục dữ liệu/cấu hình của user.

## Ghi nhớ

Khi ứng dụng jpackage lỗi sau cài đặt, hãy kiểm tra application image trước rồi mới điều tra native installer. Với ứng dụng classpath, jpackage mặc định tạo classpath từ các JAR trong `--input`; tùy chọn `-cp` tự đặt qua `--java-options` có thể ghi đè cấu hình đó. Với ứng dụng modular, kiểm tra module graph, `--add-modules` và service binding, đặc biệt thay đổi từ JDK 25. Khi launcher thoát sớm, kiểm tra main entry point, arguments, JVM options và chạy từ terminal hoặc console debug. Với tài nguyên, phân biệt resource trong JAR với file ngoài JAR; không dựa vào working directory và dùng `$APPDIR` cho file đi cùng application image. Luôn kiểm thử application image và installer trên OS, kiến trúc và môi trường gần với máy người dùng.

## Tài liệu tham khảo

- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392).
- [The jpackage Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html).
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html).
- [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html).
- [Support Application Requirements — Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html).
- [Packaging Tool User's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf).
