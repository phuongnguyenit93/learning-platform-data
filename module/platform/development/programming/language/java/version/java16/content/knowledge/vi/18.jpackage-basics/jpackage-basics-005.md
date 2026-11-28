# Chuẩn bị thư mục input sạch chỉ chứa JAR, dependency và tài nguyên cần thiết

Với ứng dụng Java non-modular, `jpackage` nhận thư mục đầu vào qua `--input`. Công cụ đưa nội dung của thư mục này vào application image và dùng JAR trong input để xây dựng class path cho launcher. Vì vậy, thư mục input nên là một **staging directory riêng**, chỉ chứa JAR ứng dụng, dependency cần ở runtime và tài nguyên mà ứng dụng thực sự cần khi chạy.

Không nên trỏ `--input` vào toàn bộ repository, thư mục `target` hoặc `build` dùng chung. Những thư mục đó có thể chứa mã nguồn, file test, log, báo cáo, artifact cũ, secret và các file tạm. Một staging directory sạch giúp package nhỏ hơn, tránh lộ dữ liệu và làm cho kết quả đóng gói có thể tái lập.

Bài học thuộc chương **jpackage cơ bản** của module **JAVA_VERSION_JAVA16**. Nội dung tập trung vào cách chuẩn bị input cho ứng dụng non-modular theo hành vi đóng gói chính thức từ Java 16 và vẫn áp dụng trên JDK hiện đại. Với ứng dụng modular, cần chuẩn bị module path và điểm vào bằng `--module-path`/`--module`; `--input` trong bài này dành cho quy trình class path.

## 1. Thư mục input có vai trò gì?

`--input` nhận đường dẫn tới một thư mục chứa các file cần đóng gói cho ứng dụng. Các file trong thư mục này được đưa vào payload của application image. Với quy trình non-modular:

- `--main-jar` chỉ định JAR chính, với đường dẫn tương đối từ thư mục input.
- Các JAR runtime dependency đặt trực tiếp trong input được đưa vào class path mặc định của launcher.
- Các file khác như cấu hình mặc định, template hoặc dữ liệu tĩnh được đóng gói cùng ứng dụng, nhưng không tự động trở thành class path.
- `--main-class` chỉ định lớp có phương thức `main` nếu manifest của JAR chính chưa khai báo hoặc muốn xác định rõ điểm vào.

Ví dụ:

```powershell
jpackage --type app-image --name Inventory --input build\jpackage-input --main-jar inventory.jar --main-class com.example.inventory.Main --dest build\packages
```

Trong lệnh này, `build\jpackage-input` là thư mục staging. JAR chính và dependency phải có mặt ở đó trước khi chạy `jpackage`.

## 2. Cấu trúc staging directory nên như thế nào?

Một cấu trúc gọn cho ứng dụng non-modular có thể là:

```text
build/
  jpackage-input/
    inventory.jar
    jackson-core.jar
    jackson-databind.jar
    slf4j-api.jar
    config/
      application-defaults.properties
    templates/
      invoice.html
  packages/
```

Trong đó:

| Thành phần | Được đưa vào vì |
| --- | --- |
| `inventory.jar` | Chứa class và điểm vào ứng dụng |
| `jackson-core.jar`, `jackson-databind.jar`, `slf4j-api.jar` | Là dependency cần khi chạy |
| `config/application-defaults.properties` | Cấu hình mặc định không nhạy cảm, nếu ứng dụng đọc file ngoài JAR |
| `templates/invoice.html` | Template được ứng dụng đọc như file bên ngoài JAR |

Các JAR dependency được đặt trực tiếp ở thư mục gốc của input để phù hợp với class path mặc định của launcher. Các thư mục con có thể dùng để chứa tài nguyên bên ngoài JAR; ứng dụng phải định vị và đọc các file đó bằng đường dẫn thích hợp.

Không bắt buộc mọi ứng dụng phải có đủ các thư mục trên. Chỉ tạo những thành phần mà ứng dụng thực sự dùng. Nếu template và properties đã được đóng gói trong JAR, không cần sao chép thêm bản ngoài JAR.

## 3. Chỉ đưa dependency cần ở runtime

Không phải mọi dependency xuất hiện trong quá trình build đều cần được phân phối cho người dùng. Staging directory nên chứa dependency cần khi ứng dụng chạy:

| Loại dependency | Có đưa vào input không? | Lý do |
| --- | :---: | --- |
| Runtime dependency | Có | Ứng dụng cần khi thực thi |
| Compile-only dependency | Thường không | Chỉ cần để biên dịch, không có mặt ở runtime |
| Test dependency | Không | Chỉ phục vụ kiểm thử |
| Annotation processor | Không | Chỉ chạy trong quá trình biên dịch |
| Công cụ build, plugin Maven/Gradle | Không | Không phải dependency của ứng dụng |
| JAR chính của ứng dụng | Có | Chứa mã ứng dụng và điểm vào |

Ví dụ, nếu ứng dụng dùng JUnit để kiểm thử, JUnit không nên xuất hiện trong package runtime chỉ vì nó có trong dependency cache của dự án. Hãy dùng cấu hình dependency scope của build tool để thu thập runtime dependencies.

Với Maven, `dependency:copy-dependencies` cùng `includeScope=runtime` có thể sao chép dependency compile và runtime vào staging. Với Gradle, lấy dependency từ `runtimeClasspath`. Không sao chép toàn bộ thư mục cache Maven hoặc Gradle vì cache chứa nhiều phiên bản và thư viện không liên quan.

## 4. Tránh JAR trùng lặp và dependency sai phiên bản

Một lỗi phổ biến là staging chứa nhiều phiên bản của cùng một thư viện:

```text
jpackage-input/
  jackson-databind-2.15.jar
  jackson-databind-2.17.jar
  inventory.jar
```

Nếu nhiều JAR chứa cùng class, kết quả nạp class có thể phụ thuộc thứ tự class path và gây lỗi khó tái hiện. Trước khi đóng gói:

- Chọn một phiên bản dependency theo dependency graph đã được build tool giải quyết.
- Không copy đồng thời JAR cũ và JAR mới của cùng artifact.
- Không đưa cả JAR thường, JAR shaded và JAR dependency đã nằm trong shaded JAR nếu việc đó làm trùng class.
- Không copy file source JAR, Javadoc JAR hoặc test JAR.
- Kiểm tra tên file và checksum nếu pipeline lấy artifact từ nhiều nguồn.

Staging directory nên phản ánh đúng dependency graph của một lần build cụ thể. Không giữ lại file từ lần đóng gói trước.

## 5. Phân biệt resource trong JAR và resource bên ngoài

Có hai cách phổ biến để phân phối resource:

### Resource nằm trong JAR

Template, ảnh mặc định hoặc file properties không cần chỉnh sửa sau khi cài đặt có thể được đặt trong resource directory của dự án và đóng gói vào JAR.

Đọc resource bằng class loader:

```java
try (var input = Main.class.getResourceAsStream("/templates/invoice.html")) {
    if (input == null) {
        throw new IllegalStateException("Missing invoice template");
    }
    // Đọc và xử lý nội dung template.
}
```

Cách này ít phụ thuộc vào cấu trúc thư mục cài đặt. Resource được đọc từ class path hoặc module tương ứng, không cần sao chép riêng vào input directory.

### Resource nằm ngoài JAR

File cấu hình mặc định, template có thể thay thế hoặc dữ liệu tĩnh có thể được đặt riêng trong staging:

```text
jpackage-input/
  inventory.jar
  jackson-databind.jar
  config/
    application-defaults.properties
  templates/
    invoice.html
```

Các file ngoài JAR được đóng gói thành payload nhưng không tự động nằm trong class path. Ứng dụng cần biết đường dẫn để đọc chúng. Có thể cấu hình đường dẫn dựa trên thư mục ứng dụng bằng token `$APPDIR` trong tùy chọn launcher được `jpackage` hỗ trợ; cú pháp escape cần phù hợp với shell và hệ điều hành.

Không giả định working directory khi người dùng mở launcher là thư mục cài đặt. Hãy dùng đường dẫn được xác định rõ ràng hoặc API resource phù hợp.

## 6. Không đưa secret vào staging directory

Thư mục input và package cuối cùng có thể được giải nén, sao chép và kiểm tra. Vì vậy, không đặt các dữ liệu sau vào staging:

- Password hoặc API token.
- Private key và credential production.
- File `.env` chứa thông tin xác thực.
- File cấu hình môi trường thật có endpoint nội bộ hoặc thông tin nhạy cảm.
- Log, dump hoặc dữ liệu người dùng từ máy build.

Có thể đóng gói cấu hình mặc định không nhạy cảm, ví dụ locale mặc định hoặc tên theme. Cấu hình theo môi trường nên được cấp khi triển khai hoặc lưu tại vị trí dữ liệu của người dùng. Secret nên được lấy từ secret manager hoặc cơ chế bảo mật của môi trường chạy.

Tách dữ liệu ghi trong quá trình chạy khỏi thư mục cài đặt ứng dụng. Thư mục cài đặt có thể chỉ đọc đối với người dùng thông thường; log, cache và dữ liệu thay đổi nên được ghi vào vị trí dữ liệu ứng dụng phù hợp với hệ điều hành.

## 7. Tạo staging directory sạch trên Windows

Ví dụ sau dùng PowerShell. Giả sử Maven đã tạo JAR chính tại `target\inventory.jar`:

```powershell
$stage = "target\jpackage-input"

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $stage | Out-Null
Copy-Item -LiteralPath "target\inventory.jar" -Destination "$stage\inventory.jar"

mvn dependency:copy-dependencies -DincludeScope=runtime "-DoutputDirectory=$stage"

New-Item -ItemType Directory -Force -Path "$stage\config", "$stage\templates" | Out-Null
Copy-Item -LiteralPath "src\packaging\config\application-defaults.properties" -Destination "$stage\config\application-defaults.properties"
Copy-Item -LiteralPath "src\packaging\templates\invoice.html" -Destination "$stage\templates\invoice.html"
```

Kết quả dự kiến:

```text
target/
  jpackage-input/
    inventory.jar
    <runtime-dependency>.jar
    config/
      application-defaults.properties
    templates/
      invoice.html
```

Tên dependency do Maven quyết định theo phiên bản đã resolve. Kiểm tra thư mục sau lệnh copy để xác nhận JAR chính và dependency đều có mặt. Nếu resource đã nằm trong JAR, bỏ các lệnh copy resource tương ứng.

Sau khi staging sẵn sàng, tạo application image:

```powershell
jpackage --type app-image --name Inventory --input target\jpackage-input --main-jar inventory.jar --main-class com.example.inventory.Main --dest target\packages
```

Không chạy lệnh xóa staging trên một thư mục chứa dữ liệu do người dùng quản lý. Ví dụ này chỉ dành cho thư mục build được tạo riêng cho pipeline.

## 8. Ví dụ chuẩn bị staging bằng Maven

Có thể chạy build và thu thập dependency runtime theo thứ tự:

```powershell
mvn clean package dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=target/jpackage-input
```

Sau khi lệnh hoàn tất, copy JAR chính vào input nếu plugin chỉ mới copy dependency:

```powershell
Copy-Item -LiteralPath "target\inventory.jar" -Destination "target\jpackage-input\inventory.jar"
```

Tên JAR chính cần khớp với artifact thực tế. Nếu Maven tạo file có tên `inventory-1.0.0.jar`, có thể dùng tên đó trong `--main-jar` hoặc chuẩn hóa tên khi copy sang staging.

Nếu project dùng shaded/fat JAR, kiểm tra dependency đã nằm trong JAR chính chưa. Không copy thêm các JAR chứa cùng thư viện nếu không cần.

Với dự án Maven nhiều module, hãy chạy lệnh ở module tạo ứng dụng hoặc dùng cấu hình reactor phù hợp để bảo đảm dependency nội bộ đã được build. Không giả định dependency nội bộ đã có trong local repository nếu pipeline chưa cài hoặc build module đó.

## 9. Ví dụ chuẩn bị staging bằng Gradle

Gradle Application Plugin có thể tạo distribution qua `installDist`. Thư mục `build\install\<application-name>\lib` thường chứa JAR ứng dụng và runtime dependency:

```powershell
.\gradlew clean test installDist
Get-ChildItem -File "build\install\inventory\lib"
```

Nếu cấu trúc distribution đáp ứng yêu cầu của launcher và tất cả JAR cần thiết nằm trực tiếp trong thư mục `lib`, có thể dùng thư mục đó làm input:

```powershell
jpackage --type app-image --name Inventory --input build\install\inventory\lib --main-jar inventory.jar --main-class com.example.inventory.Main --dest build\packages
```

Tên JAR và tên application directory phụ thuộc cấu hình Gradle. Hãy kiểm tra output thật trước khi dùng. Resource bên ngoài JAR cần được thêm vào staging riêng hoặc cấu hình trong distribution; không mặc định `installDist` đã chứa mọi file nghiệp vụ.

## 10. Kiểm tra nội dung trước khi gọi jpackage

Có thể liệt kê staging đệ quy:

```powershell
Get-ChildItem -LiteralPath "target\jpackage-input" -Recurse -File | Select-Object FullName, Length
```

Kiểm tra nhanh các loại file không nên xuất hiện:

```powershell
Get-ChildItem -LiteralPath "target\jpackage-input" -Recurse -File | Where-Object { $_.Name -match '\.(java|log|tmp|dump|env)$' -or $_.Name -match '(-sources|-javadoc|-tests)\.jar$' } | Select-Object FullName
```

Lệnh kiểm tra chỉ hiển thị các file đáng xem lại; pipeline nên xử lý kết quả theo chính sách dự án trước khi package. Không phải mọi file properties hoặc mọi file text đều không hợp lệ; cần xem nội dung và mục đích sử dụng.

Checklist trước đóng gói:

- [ ] Thư mục staging được tạo mới cho lần build hiện tại.
- [ ] Có đúng một JAR chính hoặc đúng bộ module đầu vào.
- [ ] Main class hoặc main module được xác định đúng.
- [ ] Chỉ có runtime dependency cần thiết, không có test/compile-only dependency.
- [ ] Không có nhiều phiên bản của cùng một thư viện.
- [ ] Resource ngoài JAR được đặt đúng vị trí và ứng dụng biết cách đọc.
- [ ] Không có mã nguồn, log, file tạm, secret hoặc dữ liệu người dùng.
- [ ] Native library đúng hệ điều hành và kiến trúc đích.
- [ ] Kích thước staging và danh sách file phù hợp với package dự kiến.

## 11. Lưu ý với ứng dụng modular và native library

Quy trình `--input` trong bài này dành cho ứng dụng non-modular chạy trên class path. Với ứng dụng modular, cần build module và chỉ định `--module-path` cùng `--module`. Không chuyển một thư mục module output sang `--input` rồi coi nó tương đương module path.

Nếu ứng dụng sử dụng JNI hoặc thư viện native, staging phải chứa đúng binary theo nền tảng và kiến trúc. Ví dụ:

| Nền tảng | Định dạng native library phổ biến |
| --- | --- |
| Windows | `.dll` |
| Linux | `.so` |
| macOS | `.dylib` |

Một JAR có thể dùng chung giữa nhiều nền tảng, nhưng native library thường phải được build hoặc tải riêng cho từng OS/CPU. Tạo staging directory riêng cho từng target platform, không dùng chung một thư mục có DLL, SO và dylib của nhiều môi trường nếu ứng dụng không được thiết kế để lựa chọn chúng rõ ràng.

## 12. Tạo application image và kiểm thử

Sau khi kiểm tra staging, chạy `jpackage`:

```powershell
jpackage --type app-image --name Inventory --input target\jpackage-input --main-jar inventory.jar --main-class com.example.inventory.Main --dest target\packages
```

Sau đó chạy launcher trong application image trên máy build:

```powershell
& "target\packages\Inventory\Inventory.exe"
```

Đường dẫn launcher thay đổi theo nền tảng. Hãy chạy đúng launcher do `jpackage` tạo, không chỉ chạy lại JAR bằng JDK đã cài trên máy build. Kiểm tra các chức năng cần resource, dependency, file cấu hình và native library để phát hiện file bị thiếu.

Cuối cùng, thử application image trên môi trường sạch gần với máy người dùng. Nếu ứng dụng chỉ chạy được trên máy build, hãy kiểm tra staging có bỏ sót dependency hoặc file cấu hình mà máy phát triển vô tình cung cấp qua working directory, class path hoặc environment variable hay không.

## 13. Các lỗi thường gặp khi chuẩn bị input

| Triệu chứng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| `ClassNotFoundException` | Thiếu dependency JAR trong input hoặc class path bị ghi đè | Thu thập runtime dependency và kiểm tra class path launcher |
| `NoClassDefFoundError` | Có dependency khi test nhưng không có trong staging | Dùng runtime dependency, không dùng test classpath |
| Không tìm thấy main JAR | `--main-jar` sai tên hoặc không tương đối với input | Kiểm tra file và đường dẫn tương đối |
| Không tìm thấy template/config | Resource ngoài JAR chưa được copy hoặc đường dẫn runtime sai | Thêm resource vào payload và cấu hình đường dẫn rõ ràng |
| Nạp nhầm phiên bản thư viện | Staging có nhiều JAR cùng artifact | Chỉ giữ phiên bản đã resolve |
| Package quá lớn | Input chứa log, test report, cache hoặc file phát triển | Tạo staging directory mới và chỉ copy file cần thiết |
| Lộ credential | File secret bị copy từ cấu hình máy build | Loại bỏ secret và cấp chúng tại môi trường chạy |
| Lỗi nạp native library | Binary không đúng OS/CPU hoặc thiếu dependency native | Tạo staging riêng theo nền tảng và kiểm tra native dependency |

## Ghi nhớ

**`--input` nên trỏ tới staging directory được tạo riêng cho một lần đóng gói và chỉ chứa JAR ứng dụng, runtime dependency cùng resource thật sự cần thiết.** Đặt JAR dependency trực tiếp ở thư mục gốc để launcher class path mặc định nhận được chúng; resource ngoài JAR được đóng gói nhưng phải được ứng dụng định vị riêng. Thu thập dependency runtime bằng Maven hoặc Gradle, loại bỏ test/source/log/secret, tránh nhiều phiên bản thư viện và kiểm tra danh sách file trước khi gọi `jpackage`. Với ứng dụng modular hoặc native dependency, chuẩn bị đầu vào riêng theo module và nền tảng đích.

## Tài liệu tham khảo

- [Oracle Java SE 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Oracle Java SE 26 — Packaging Overview](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Oracle Java SE 26 — Support Application Requirements](https://docs.oracle.com/en/java/javase/26/jpackage/support-application-features.html)
- [Apache Maven Dependency Plugin — copy-dependencies](https://maven.apache.org/plugins/maven-dependency-plugin/copy-dependencies-mojo.html)
- [Gradle Application Plugin — Creating distributions](https://docs.gradle.org/current/userguide/application_plugin.html)
- [JEP 392 — Packaging Tool](https://openjdk.org/jeps/392)
