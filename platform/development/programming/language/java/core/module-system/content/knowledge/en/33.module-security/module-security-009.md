# Audit module graph trong pipeline phát hành

Một ứng dụng Java modular có thể biên dịch thành công nhưng vẫn thất bại khi khởi chạy sau khi đóng gói. Nguyên nhân có thể nằm ở module bị thiếu, dependency bắc cầu không đúng, module provider không được đưa vào runtime, package chưa export hoặc cấu hình module path khác với môi trường build.

Vì vậy, pipeline phát hành cần kiểm tra **module graph của artifact sẽ được triển khai**, thay vì chỉ kiểm tra file module-info.java trong source. Việc audit phải xác nhận module nào được tìm thấy, module nào được resolve, các quan hệ dependency có hợp lệ và ứng dụng có khởi động được với cấu hình runtime dự kiến hay không.

## 1. Phân biệt source dependency graph và runtime module graph

Trong một dự án modular, có nhiều lớp dependency khác nhau:

- **Source dependency graph:** các module mà mã nguồn khai báo qua requires, uses và provides.
- **Observable module set:** các module mà JVM có thể tìm thấy từ system modules, module path và các nguồn module được cấu hình.
- **Resolved module graph:** các root modules cùng những dependency cần thiết sau quá trình resolution.
- **Runtime environment:** module graph thực tế cùng classpath, module path, JVM arguments, module layer và các cấu hình khởi chạy.

Các lớp này có liên quan nhưng không giống nhau. Một JAR nằm trên module path có thể observable nhưng chưa được resolve. Một module đã resolve cũng chưa chắc cung cấp đúng method mà bytecode consumer yêu cầu.

Ví dụ:

~~~text
com.example.app
    └── requires com.example.api

com.example.api
    └── requires java.base

com.example.plugin.audit
    └── requires com.example.api
~~~

Nếu app không khai báo dependency tới plugin.audit và không có cơ chế nào đưa plugin vào graph, plugin có thể nằm trên module path nhưng không xuất hiện trong graph được resolve.

Khi phát hành, cần xác định rõ plugin đó là dependency bắt buộc, module tùy chọn hay service provider được lựa chọn theo cấu hình. Không nên chỉ nhìn danh sách JAR trong thư mục phân phối để kết luận runtime đã sử dụng tất cả chúng.

## 2. Vì sao cần audit ở pipeline phát hành?

Audit module graph giúp phát hiện sớm các lỗi thường chỉ xuất hiện trên máy triển khai:

- Thiếu module hoặc dependency trong thư mục phân phối.
- Module name không khớp với requires.
- Dependency bắc cầu thay đổi sau khi nâng phiên bản thư viện.
- Package cần dùng không được export.
- Module provider không được resolve hoặc service không được phát hiện.
- Module path hoặc JVM arguments của production khác môi trường kiểm thử.
- Hai artifact cùng khai báo một module name hoặc chứa package xung đột.
- Module runtime không tương thích với bytecode consumer đã biên dịch.
- Package được opens quá rộng hoặc không đúng module đích.
- Ứng dụng phụ thuộc vào classpath hoặc JDK internals mà bản phát hành không còn cung cấp.

Một build xanh chỉ chứng minh những bước đã chạy trong build thành công. Nếu pipeline không kiểm tra runtime image hoặc tập artifact phát hành, nó chưa chứng minh module graph triển khai hợp lệ.

## 3. Xác định đầu vào của một lần audit

Trước khi chạy công cụ, cần cố định các đầu vào sau:

| Đầu vào | Cần xác định |
| --- | --- |
| JDK | Phiên bản JDK dùng để biên dịch và chạy kiểm thử |
| Application module | Module khởi động chính |
| Module path | Thư mục hoặc JAR chứa các named module |
| Classpath | Các thư viện còn chạy trên unnamed module, nếu có |
| Root modules | Module khởi động và các module bổ sung bằng --add-modules |
| Module limit | Có dùng --limit-modules hay không |
| Module patch/upgrade | Có dùng --patch-module hoặc --upgrade-module-path không |
| Runtime flags | Các tùy chọn --add-reads, --add-exports và --add-opens |
| Service declarations | Các module khai báo uses và provides |
| Artifact manifest | Danh sách file, module name, version metadata và checksum |

Đầu vào phải phản ánh cấu hình sẽ dùng để chạy bản phát hành. Nếu production có thêm một JVM argument hoặc một thư mục module path mà CI không biết, kết quả audit sẽ không đại diện cho production.

Nên lưu lại command line hoặc cấu hình khởi chạy đã được chuẩn hóa để các lần build có thể tái lập.

## 4. Kiểm tra descriptor của từng module artifact

Dùng công cụ jar để xem module descriptor được đóng gói trong artifact:

~~~shell
jar --describe-module --file build/dist/com.example.api.jar
~~~

Kết quả giúp xác nhận:

- Tên module.
- Version metadata nếu có.
- Các package được export.
- Các package được opens.
- requires, uses và provides.
- Module là explicit, automatic hoặc dạng phù hợp với artifact.

Ví dụ descriptor:

~~~java
module com.example.api {
    exports com.example.api;
    exports com.example.api.spi;

    uses com.example.api.spi.AuditProvider;
}
~~~

Provider:

~~~java
module com.example.audit.provider {
    requires com.example.api;

    provides com.example.api.spi.AuditProvider
        with com.example.audit.internal.DefaultAuditProvider;
}
~~~

Consumer khai báo uses cho service mà nó cần. Provider khai báo provides để đăng ký implementation. Các khai báo này cần được kiểm tra cùng với việc provider có được đưa vào runtime graph và được service loading phát hiện hay không.

Không nên chỉ kiểm tra source module-info.java. Hãy kiểm tra descriptor bên trong JAR cuối cùng, vì artifact có thể được tạo, thay thế hoặc đóng gói lại trong một bước khác.

## 5. Kiểm tra dependency bằng jdeps

jdeps phân tích dependency của class và module. Công cụ này giúp tìm module được tham chiếu, dependency thiếu và sự khác biệt giữa descriptor với các dependency mà bytecode thực sự sử dụng.

### Liệt kê dependency của artifact

~~~shell
jdeps --module-path build/dist --list-deps build/dist/com.example.app.jar
~~~

Lệnh này hiển thị các module dependency mà jdeps phát hiện từ artifact và module path được cung cấp.

### In danh sách module dependency

~~~shell
jdeps --module-path build/dist --print-module-deps build/dist/com.example.app.jar
~~~

Kết quả là danh sách tên module phân cách bằng dấu phẩy. Có thể dùng kết quả này làm dữ liệu tham khảo khi tạo runtime image hoặc đối chiếu với danh sách module mong đợi.

### Kiểm tra descriptor của named module

~~~shell
jdeps --module-path build/dist --check com.example.app
~~~

Tùy chọn --check phân tích module được chỉ định, hiển thị descriptor và dependency của module để hỗ trợ phát hiện sự không nhất quán trong module declaration.

Nếu pipeline audit nhiều module, hãy chạy kiểm tra cho từng module ứng dụng hoặc module quan trọng, đồng thời giữ kết quả theo từng artifact.

### Kiểm tra API và dependency của JDK

Có thể dùng:

~~~shell
jdeps --module-path build/dist --api-only build/dist/com.example.app.jar
~~~

Hoặc kiểm tra việc sử dụng JDK internal APIs:

~~~shell
jdeps --jdk-internals build/dist/com.example.app.jar
~~~

jdeps là công cụ phân tích bytecode tĩnh. Nó không thể phát hiện đầy đủ mọi dependency được nạp động qua reflection, tên class được đọc từ cấu hình, custom class loader hoặc service discovery ở runtime. Các dependency động phải được bổ sung vào danh sách audit và kiểm thử tích hợp.

## 6. Xác thực tập module observable và resolution

Sau khi chuẩn bị module path, có thể yêu cầu JVM xác thực các module tìm thấy:

~~~shell
java --module-path build/dist --validate-modules
~~~

Tùy chọn --validate-modules yêu cầu JVM xác thực module trong cấu hình observable rồi thoát. Đây là một bước kiểm tra hữu ích để phát hiện lỗi module configuration trước khi chạy ứng dụng.

Tiếp theo, khởi chạy module chính và hiển thị quá trình resolution:

~~~shell
java \
  --module-path build/dist \
  --show-module-resolution \
  --module com.example.app/com.example.app.Main
~~~

Output giúp quan sát:

- Module nào được resolve.
- Dependency nào được yêu cầu.
- Nguồn module được sử dụng trong quá trình resolution.
- Các service binding hoặc module liên quan được runtime đưa vào graph theo cấu hình.

Nếu ứng dụng cần module tùy chọn làm root, hãy đưa đúng tùy chọn đó vào audit:

~~~shell
java \
  --module-path build/dist \
  --add-modules com.example.audit.provider \
  --show-module-resolution \
  --module com.example.app/com.example.app.Main
~~~

Không nên dùng ALL-MODULE-PATH trong audit nếu production chỉ resolve một tập module xác định. Audit phải tái hiện cấu hình thực tế, nếu không có thể kiểm tra một graph khác với graph được phát hành.

## 7. Kiểm tra các quan hệ requires và package boundary

Một module graph hợp lệ vẫn có thể không đáp ứng contract truy cập của ứng dụng.

Cần kiểm tra các khai báo:

- requires: module cần đọc module khác.
- requires transitive: dependency được truyền tiếp tới các module đọc module này.
- requires static: dependency cần lúc biên dịch nhưng có thể không bắt buộc ở runtime.
- exports: package công khai cho module khác.
- opens: package mở cho deep reflection.
- uses: module tiêu thụ service.
- provides: module cung cấp implementation cho service.

Đặc biệt, cần xem các kiểu trong public API có đến từ module được khai báo phù hợp hay không. Nếu API của một module export kiểu thuộc dependency khác, quan hệ requires có thể cần transitive để consumer sử dụng API một cách đúng đắn.

Với requires static, pipeline nên xác định module đó có thật sự cần trong production hay chỉ phục vụ compile-time. Nếu một tính năng tùy chọn được kích hoạt ở runtime nhưng dependency tương ứng bị thiếu, ứng dụng có thể gặp lỗi khi thực hiện tính năng đó.

Với opens, kiểm tra đúng package và đúng module đích. Không nên đưa một cờ --add-opens rộng vào cấu hình chung chỉ để làm cho smoke test chạy qua.

## 8. Kiểm tra service provider và module tùy chọn

ServiceLoader là một phần quan trọng của ứng dụng modular có plugin hoặc adapter.

Ví dụ service API:

~~~java
module com.example.audit.api {
    exports com.example.audit.api;

    uses com.example.audit.api.AuditProvider;
}
~~~

Provider:

~~~java
module com.example.audit.file {
    requires com.example.audit.api;

    provides com.example.audit.api.AuditProvider
        with com.example.audit.file.internal.FileAuditProvider;
}
~~~

Một pipeline chỉ kiểm tra module app và audit.api có thể bỏ sót provider nếu provider không được đưa vào graph hoặc artifact phân phối không chứa nó.

Hãy kiểm tra theo ba lớp:

1. Descriptor của provider có khai báo provides đúng service type không?
2. Provider module có nằm trong tập module observable và được resolve theo cấu hình không?
3. Runtime test có thực sự tìm được provider bằng ServiceLoader không?

Ví dụ kiểm thử:

~~~java
long providerCount =
    ServiceLoader.load(AuditProvider.class)
        .stream()
        .count();

if (providerCount == 0) {
    throw new IllegalStateException(
        "No AuditProvider was discovered"
    );
}
~~~

Nếu provider là tùy chọn, kiểm thử cần phản ánh chính sách của ứng dụng: không có provider có phải là trạng thái hợp lệ hay là lỗi phát hành. Không nên ép mọi môi trường phải có tất cả provider nếu kiến trúc cho phép lựa chọn theo cấu hình.

## 9. Tạo một bước audit trong CI

Một pipeline có thể chia thành các bước sau:

~~~text
Compile
  |
  v
Package modular JARs
  |
  v
Assemble release module path
  |
  v
Inspect module descriptors
  |
  v
Run jdeps analysis
  |
  v
Validate observable modules
  |
  v
Launch with production JVM arguments
  |
  v
Run module and service smoke tests
  |
  v
Generate audit evidence
  |
  v
Publish release artifact
~~~

Ví dụ script Bash tối giản:

~~~shell
#!/usr/bin/env bash
set -euo pipefail

DIST="build/dist"
AUDIT="build/module-audit"
APP_MODULE="com.example.app"
MAIN_CLASS="com.example.app.Main"

mkdir -p "$AUDIT"

java -version 2> "$AUDIT/jdk-version.txt"

# Inspect each modular artifact.
for artifact in "$DIST"/*.jar; do
  name=$(basename "$artifact")
  jar --describe-module --file "$artifact" \
    > "$AUDIT/$name.module.txt"
done

# Validate the observable module set.
java --module-path "$DIST" --validate-modules \
  > "$AUDIT/validate-modules.txt" 2>&1

# Analyze application module dependencies.
jdeps --module-path "$DIST" --check "$APP_MODULE" \
  > "$AUDIT/module-check.txt" 2>&1

jdeps --module-path "$DIST" --list-deps "$DIST/$APP_MODULE.jar" \
  > "$AUDIT/module-dependencies.txt" 2>&1

# Resolve modules and run the application smoke test.
java \
  --module-path "$DIST" \
  --show-module-resolution \
  --module "$APP_MODULE/$MAIN_CLASS" \
  > "$AUDIT/runtime-resolution.txt" 2>&1
~~~

Script trên minh họa cấu trúc kiểm tra. Tên JAR, main class, module path và JVM arguments phải được điều chỉnh theo artifact thực tế. Nếu ứng dụng dùng classpath, --add-modules, --add-reads, --add-opens hoặc custom runtime image, hãy đưa chính cấu hình đó vào bước audit.

Trong CI thực tế, nên chia kết quả thành các file riêng để reviewer dễ tìm nguyên nhân. Một lệnh thất bại phải làm pipeline dừng trước khi publish artifact.

## 10. Đưa audit vào Gradle pipeline

Với Gradle Java plugin, có thể tạo một task phụ thuộc vào artifact đã đóng gói. Ý tưởng là audit JAR thực tế sau khi task jar hoàn tất, không chỉ chạy javac trên source.

Ví dụ cấu hình minh họa:

~~~groovy
tasks.register('auditModuleDescriptor') {
    dependsOn tasks.named('jar')

    doLast {
        def artifact = tasks.named('jar').get().archiveFile.get().asFile
        exec {
            commandLine 'jar',
                '--describe-module',
                '--file',
                artifact.absolutePath
        }
    }
}
~~~

Có thể bổ sung các task riêng cho:

- jdeps --check trên module ứng dụng.
- jdeps --print-module-deps để lưu danh sách dependency.
- java --validate-modules trên thư mục release module path.
- Smoke test chạy bằng cùng JDK và JVM arguments với production.

Nếu là Gradle multi-project, cần tập hợp đúng runtime artifacts của module ứng dụng và các dependency. Không nên dùng toàn bộ JAR trong cache Gradle làm module path vì cache có thể chứa nhiều phiên bản hoặc artifact không được phát hành cùng ứng dụng.

Các task audit cần dùng artifact đã được resolve theo configuration dành cho runtime, không tự suy đoán từ tên thư mục hoặc dependency khai báo ở compile time.

## 11. Tạo bằng chứng audit gắn với release

Kết quả audit cần gắn với đúng bộ artifact được phát hành. Một thư mục evidence có thể gồm:

~~~text
module-audit/
├── jdk-version.txt
├── artifact-checksums.txt
├── app.module.txt
├── module-check.txt
├── module-dependencies.txt
├── validate-modules.txt
├── runtime-resolution.txt
└── smoke-test-result.txt
~~~

Nên ghi nhận:

- Commit hoặc source revision tạo artifact.
- JDK vendor và version.
- Tên, version metadata và checksum của từng modular JAR.
- Module path hoặc runtime image đã kiểm tra.
- Root module và JVM arguments được sử dụng.
- Kết quả descriptor, jdeps, validation và smoke test.
- Các module tùy chọn hoặc provider được bật trong từng profile.

Checksum giúp liên kết evidence với đúng artifact. Nếu JAR được thay thế sau khi audit, evidence cũ không còn chứng minh cho artifact mới.

Có thể dùng SHA-256 để tạo manifest:

~~~shell
sha256sum build/dist/*.jar > build/module-audit/artifact-checksums.txt
~~~

Trên Windows, có thể dùng Get-FileHash trong PowerShell hoặc công cụ checksum tương ứng của môi trường CI.

Không nên chỉ lưu log "audit passed". Hãy lưu cấu hình và danh sách module đã kiểm tra để có thể giải thích vì sao một bản phát hành được chấp nhận.

## 12. Những gì static audit không thể chứng minh

jdeps và module descriptor cung cấp góc nhìn tĩnh. Chúng không chứng minh toàn bộ hành vi runtime.

Một số dependency có thể không xuất hiện rõ trong bytecode:

- Class được nạp bằng Class.forName với tên lấy từ cấu hình.
- Framework quét package hoặc dùng reflection.
- Service provider được chọn theo môi trường.
- Module layer được tạo động.
- Resource hoặc cấu hình được tải theo tên.
- Code phụ thuộc vào thứ tự hoặc nội dung của runtime image.

Do đó, pipeline cần có smoke test và integration test cho các đường chạy quan trọng. Với module layer động, hãy tạo test khởi tạo layer giống production và xác nhận các module mong đợi xuất hiện.

Nếu ứng dụng hỗ trợ nhiều profile, hãy audit từng profile có module graph khác nhau. Ví dụ profile database, profile plugin hoặc profile chạy batch có thể sử dụng tập module khác nhau.

## 13. Những nhầm lẫn thường gặp

1. **Có JAR trong thư mục dist nghĩa là module đã resolve:** module có thể observable nhưng chưa nằm trong graph.
2. **Compile thành công chứng minh runtime graph hợp lệ:** runtime có thể thiếu artifact hoặc dùng JVM arguments khác.
3. **jdeps là kiểm thử runtime đầy đủ:** jdeps phân tích dependency tĩnh và không phát hiện mọi dynamic loading.
4. **Module version bảo đảm API tương thích:** version metadata không thay thế binary compatibility check.
5. **Audit chỉ cần đọc module-info.java trong source:** phải kiểm tra descriptor trong artifact được phát hành.
6. **ALL-MODULE-PATH giúp audit toàn diện hơn:** nếu production không dùng selector đó, kết quả có thể không phản ánh graph thực tế.
7. **Service API đã resolve nghĩa là provider đã hoạt động:** cần kiểm tra provider module và gọi ServiceLoader trong runtime test.
8. **Một lần audit cho mọi JDK là đủ:** module behavior và JDK internal access có thể khác theo phiên bản runtime.
9. **Lưu log mà không gắn checksum là đủ:** artifact có thể bị thay đổi sau khi audit.

## Kết luận

Audit module graph nên là một quality gate trước khi phát hành ứng dụng Java modular. Pipeline cần kiểm tra descriptor của artifact, phân tích dependency bằng jdeps, xác thực module set, quan sát quá trình resolution và chạy smoke test với đúng cấu hình production. Hãy lưu kết quả cùng checksum và revision của release để có thể truy vết. Static audit phát hiện vấn đề về cấu trúc; runtime test xác nhận các module, service và tính năng quan trọng thực sự hoạt động trong môi trường triển khai.
