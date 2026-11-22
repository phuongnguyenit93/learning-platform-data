# Kiểm tra nội dung artifact và chạy thử sản phẩm đã đóng gói

Một dự án Java biên dịch thành công chưa có nghĩa sản phẩm phát hành đã sẵn sàng. Mã nguồn có thể chạy tốt trong IDE hoặc trên classpath của Gradle/Maven nhưng artifact cuối cùng vẫn thiếu class, resource, dependency, manifest hoặc cấu hình khởi chạy. Một JAR có thể được tạo ra nhưng không chạy được bằng `java -jar`; một WAR có thể thiếu thư viện cần thiết; một ZIP phân phối có thể chứa sai cấu trúc thư mục hoặc script không có quyền thực thi.

Vì vậy, quy trình đóng gói cần có bước **kiểm tra nội dung artifact** và **chạy thử chính sản phẩm đã đóng gói**. Hai việc này xác nhận những điều khác nhau:

- Kiểm tra nội dung xác nhận archive có đúng file, metadata, class, resource và dependency cần thiết.
- Chạy thử xác nhận artifact có thể khởi động và thực hiện một hành vi quan trọng trong môi trường gần với cách người dùng sẽ sử dụng nó.

Build chỉ kiểm tra source set hoặc chạy test trên classpath phát triển có thể bỏ sót lỗi đóng gói. Chạy thử artifact sau khi tạo giúp phát hiện nhóm lỗi chỉ xuất hiện ở ranh giới giữa build và runtime.

## 1. Vì sao cần kiểm tra artifact sau khi đóng gói?

Trong quá trình phát triển, ứng dụng thường được chạy từ IDE hoặc bằng task như `run`. Các công cụ này có thể tự tạo classpath đầy đủ từ thư mục class, resource và dependency đã phân giải. Khi đóng gói, plugin có thể áp dụng quy tắc khác: chọn file nào đưa vào archive, tạo manifest ra sao, có đưa dependency vào hay không, và resource nào được merge.

Một số lỗi chỉ xuất hiện trong artifact:

- JAR thiếu `Main-Class` hoặc khai báo sai tên lớp chính.
- JAR chứa lớp chính nhưng thiếu một resource cần thiết.
- Dependency có trong runtime classpath của IDE nhưng không có trong distribution.
- File `META-INF/services` bị ghi đè khi tạo fat JAR.
- WAR thiếu thư viện hoặc cấu hình cần thiết trong `WEB-INF`.
- Archive có tên đúng nhưng chứa nhầm version hoặc classifier.
- Script khởi chạy dùng đường dẫn tuyệt đối của máy build.
- Tệp cấu hình hoặc chứng thư không được đưa vào sản phẩm.
- Artifact bị hỏng trong quá trình upload, copy hoặc publish.

Ví dụ luồng tổng quát:

```text
Source + dependencies + build configuration
                  |
                  v
             Compile / test
                  |
                  v
              Package
                  |
                  v
           JAR / WAR / ZIP
                  |
          +-------+-------+
          |               |
          v               v
   Inspect contents   Run smoke test
          |               |
          +-------+-------+
                  |
                  v
        Artifact acceptance gate
                  |
                  v
            Publish / deploy
```

Chỉ publish hoặc triển khai sau khi các bước kiểm tra phù hợp với sản phẩm đã thành công.

## 2. Xác định artifact cần kiểm tra

Trước khi viết lệnh kiểm tra, cần biết chính xác sản phẩm build tạo ra là gì và nằm ở đâu.

| Loại sản phẩm | Định dạng | Nội dung thường cần xác nhận |
|---|---|---|
| JAR thư viện | `.jar` | Class public, resource, metadata, version và dependency declaration |
| Executable JAR | `.jar` | Main-Class, lớp điểm vào, resource và runtime dependency |
| Fat/uber JAR | `.jar` | Class của ứng dụng và dependency, service descriptor, resource merge, license/notice |
| WAR | `.war` | `WEB-INF/classes`, `WEB-INF/lib`, cấu hình web và tài nguyên tĩnh |
| Distribution ZIP/TAR | `.zip`, `.tar`, `.tar.gz` | Cây thư mục, script khởi chạy, JAR phụ thuộc, config và quyền file |
| Container image | Image OCI/Docker | Entrypoint, runtime, JAR được copy, user, port và cấu hình cần thiết |

Vị trí output thường gặp:

```text
Gradle: build/libs/
Maven:  target/
```

Tên file thực tế phụ thuộc `group`, `artifactId`/project name, version, classifier, extension và cấu hình archive. Không nên hard-code tên file trong pipeline nếu build tool có thể cung cấp output provider hoặc property tương ứng.

## 3. Kiểm tra tính toàn vẹn của archive

Trước khi kiểm tra nội dung, xác nhận file tồn tại, có kích thước hợp lý và có thể được công cụ archive đọc.

### 3.1. Kiểm tra file tồn tại và kích thước

Linux/macOS:

```bash
ls -lh build/libs/application.jar
```

Windows PowerShell:

```powershell
Get-Item .\build\libs\application.jar |
    Select-Object FullName, Length, LastWriteTime
```

Nếu file không tồn tại, kiểm tra task package, tên archive và output directory. Nếu file có kích thước bằng 0 hoặc nhỏ bất thường, có thể task thất bại giữa chừng hoặc artifact chưa được tạo đầy đủ.

### 3.2. Kiểm tra cấu trúc ZIP/JAR/WAR

JAR và WAR dựa trên định dạng ZIP. Có thể kiểm tra bằng JDK `jar`:

```bash
jar --list --file build/libs/application.jar
```

Hoặc dùng `unzip`:

```bash
unzip -t build/libs/application.jar
```

`jar --list` hiển thị entry; `unzip -t` kiểm tra cấu trúc và CRC của các entry. Một archive có thể đọc được vẫn chứa nội dung sai, vì vậy bước này chỉ xác nhận tính toàn vẹn cấu trúc ở mức archive.

Với ZIP distribution:

```bash
unzip -l build/distributions/application.zip
unzip -t build/distributions/application.zip
```

Trên Windows có thể dùng `tar -tf` nếu phiên bản hệ thống hỗ trợ, hoặc công cụ ZIP tương ứng.

## 4. Kiểm tra nội dung JAR

### 4.1. Liệt kê class và resource

```bash
jar tf build/libs/application.jar
```

Ví dụ một JAR ứng dụng tối giản có thể chứa:

```text
META-INF/
META-INF/MANIFEST.MF
com/example/Application.class
com/example/service/OrderService.class
application.properties
```

Kiểm tra những entry quan trọng:

- Lớp điểm vào có mặt đúng package không?
- Các lớp cần thiết có nằm trong archive không?
- Resource cấu hình và template có được đóng gói không?
- Có vô tình đưa file test, file `.java`, file local hoặc dữ liệu nhạy cảm vào không?
- Có file trùng tên hoặc package đáng ngờ không?

Có thể lọc danh sách trên Linux/macOS:

```bash
jar tf build/libs/application.jar | grep 'com/example/Application.class'
```

PowerShell:

```powershell
jar tf .\build\libs\application.jar |
    Select-String 'com/example/Application.class'
```

Không nên chỉ dựa vào tên file JAR để kết luận nội dung đúng. Cần kiểm tra những entry quan trọng theo hợp đồng đóng gói của dự án.

### 4.2. Kiểm tra manifest

Manifest nằm tại:

```text
META-INF/MANIFEST.MF
```

Đọc nội dung bằng:

```bash
unzip -p build/libs/application.jar META-INF/MANIFEST.MF
```

Với executable JAR truyền thống, kiểm tra:

```text
Main-Class: com.example.Application
```

Nếu có `Class-Path`, xác nhận từng URL tham chiếu trỏ tới file được phân phối ở vị trí tương ứng. Nếu JAR được tạo bởi framework như Spring Boot, manifest có thể có loader class riêng và thuộc tính `Start-Class`; cần hiểu đúng định dạng executable archive của framework thay vì chỉ đòi một manifest tối giản.

### 4.3. Kiểm tra phiên bản và metadata

Manifest có thể chứa:

```text
Implementation-Title: Example Application
Implementation-Version: 2.4.0
Implementation-Vendor: Example Team
```

Nếu dự án dựa vào các thuộc tính này để hiển thị version hoặc chẩn đoán runtime, cần xác nhận chúng phản ánh đúng phiên bản build. Không đưa token, password, private key hoặc thông tin nội bộ nhạy cảm vào manifest vì người nhận artifact có thể đọc được.

### 4.4. Kiểm tra class bằng `javap`

JDK cung cấp `javap` để xem cấu trúc class file:

```bash
javap -classpath build/libs/application.jar -public com.example.Application
```

Có thể xác nhận lớp tồn tại và xem public method. Nếu cần kiểm tra bytecode hoặc chữ ký chi tiết hơn, dùng các tùy chọn như `-c`, `-p` hoặc `-verbose` phù hợp.

`javap` giúp kiểm tra class đã đóng gói. Nó không xác nhận toàn bộ dependency runtime, cấu hình hệ thống hoặc hành vi ứng dụng.

## 5. Kiểm tra dependency và cấu trúc fat JAR

JAR thông thường của Java plugin thường chỉ chứa output của project và resource; dependency bên ngoài không tự động được chép vào JAR. Vì vậy, cần hiểu loại artifact trước khi kiểm tra.

### 5.1. JAR thông thường

Một JAR thư viện thường chứa class và resource của chính module. Dependency được mô tả trong POM hoặc Gradle Module Metadata khi publish. Consumer build tool phân giải dependency riêng.

Khi kiểm tra JAR thông thường, không nên kết luận thiếu dependency chỉ vì không thấy JAR phụ bên trong archive. Hãy kiểm tra metadata publication và runtime classpath của consumer.

### 5.2. Fat/uber JAR

Fat JAR chứa class/resource của ứng dụng cùng nội dung dependency được hợp nhất hoặc lồng theo quy ước của plugin. Kiểm tra:

- Class của các thư viện bắt buộc có mặt.
- Không có duplicate class gây che khuất hoặc lỗi liên kết.
- `META-INF/services` được merge đúng khi nhiều thư viện đăng ký provider.
- Resource cùng tên được xử lý theo chiến lược phù hợp.
- Chữ ký cũ trong `META-INF` được xử lý khi archive bị tái đóng gói.
- License và notice của dependency được giữ theo yêu cầu phân phối.
- Native library hoặc file ngoài archive được đóng gói/cung cấp đúng cách.

Ví dụ kiểm tra một số entry:

```bash
jar tf build/libs/application-all.jar | grep 'META-INF/services'
jar tf build/libs/application-all.jar | grep 'com/example/Application.class'
```

Fat JAR có thể chứa dependency theo cấu trúc phẳng hoặc dạng nested archive tùy plugin. Ví dụ executable JAR của Spring Boot thường có class ứng dụng trong `BOOT-INF/classes/` và dependency JAR trong `BOOT-INF/lib/`; không nên áp dụng quy tắc kiểm tra JAR phẳng cho mọi archive.

### 5.3. Kiểm tra dependency tĩnh bằng `jdeps`

JDK có công cụ `jdeps` để phân tích phụ thuộc ở mức class/package/module:

```bash
jdeps --summary build/libs/application.jar
```

Hoặc:

```bash
jdeps --recursive build/libs/application.jar
```

`jdeps` giúp xem dependency mà bytecode tham chiếu và có thể phát hiện một số phụ thuộc không được giải quyết trong phân tích. Kết quả phụ thuộc classpath/module path được cung cấp và không thay thế smoke test. Reflection, service loading, resource lookup và các dependency được xác định lúc runtime có thể không được phát hiện đầy đủ.

## 6. Kiểm tra WAR và web application archive

WAR thường có cấu trúc:

```text
application.war
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   └── com/example/...
│   ├── lib/
│   │   ├── dependency-a.jar
│   │   └── dependency-b.jar
│   └── web.xml              # Có thể không cần với cấu hình Servlet hiện đại
└── index.html               # Ví dụ tài nguyên web tĩnh
```

Kiểm tra:

- Class ứng dụng nằm trong `WEB-INF/classes/`.
- Dependency cần đóng gói nằm trong `WEB-INF/lib/`.
- Static resource nằm đúng vị trí và có thể được server phục vụ.
- `web.xml` có mặt nếu ứng dụng yêu cầu; nhiều ứng dụng hiện đại dùng annotation/configuration và không cần file này.
- Không đóng gói nhầm dependency do container cung cấp theo mô hình deployment đã chọn.

Liệt kê WAR:

```bash
jar tf target/application.war
```

WAR hợp lệ về cấu trúc chưa chứng minh nó triển khai được trên servlet container. Cần chạy thử trên container/phiên bản tương thích hoặc dùng integration test kiểm tra deployment.

## 7. Kiểm tra distribution ZIP/TAR

Một distribution thường chứa nhiều thành phần:

```text
application-2.4.0/
├── bin/
│   ├── application
│   └── application.bat
├── lib/
│   ├── application.jar
│   ├── dependency-a.jar
│   └── dependency-b.jar
├── conf/
│   └── application.yml
└── README.txt
```

Kiểm tra:

- Tên thư mục gốc và version có đúng không?
- Script Unix và Windows đều có mặt nếu sản phẩm hỗ trợ hai nền tảng.
- Script Unix có executable bit trong archive hoặc được cài đặt với quyền phù hợp.
- Script trỏ tới JAR và thư mục config đúng vị trí tương đối.
- Các dependency runtime được chép đủ.
- File cấu hình mẫu không chứa secret.
- Không có file tạm, cache hoặc output kiểm thử ngoài ý muốn.
- README hướng dẫn lệnh chạy và yêu cầu JDK chính xác.

Một file ZIP có thể lưu Unix permission trong external attributes, nhưng hành vi bảo toàn quyền phụ thuộc công cụ tạo và giải nén archive. Cần kiểm tra distribution sau khi giải nén trên hệ điều hành đích.

## 8. Kiểm tra checksum và chữ ký artifact

Khi artifact được copy hoặc publish qua nhiều hệ thống, cần xác nhận file nhận được đúng là file đã tạo.

Linux:

```bash
sha256sum build/libs/application.jar
```

macOS:

```bash
shasum -a 256 build/libs/application.jar
```

Windows PowerShell:

```powershell
Get-FileHash .\build\libs\application.jar -Algorithm SHA256
```

So sánh SHA-256 của file nguồn và file tải về. Checksum giúp phát hiện thay đổi nội dung, nhưng nếu checksum được lấy từ cùng một nguồn không đáng tin cậy thì nó không chứng minh nguồn gốc. Với yêu cầu xác thực publisher, cần quy trình ký và xác minh chữ ký.

Với JAR được ký, có thể kiểm tra bằng:

```bash
jarsigner -verify -verbose -certs application.jar
```

Kết quả cần được đánh giá theo certificate, trust policy, timestamp và cảnh báo của JDK. Một thông báo signature verification thành công không tự chứng minh publisher là tổ chức mà người dùng mong đợi nếu certificate chain không được tin cậy hoặc danh tính chưa được xác minh.

Nếu archive được shading hoặc sửa đổi sau khi ký, chữ ký cũ có thể mất hiệu lực. Quy trình đúng thường là hoàn tất đóng gói trước, sau đó ký artifact cuối cùng.

## 9. Chạy thử artifact đã đóng gói là gì?

Smoke test là kiểm tra ngắn nhằm xác nhận sản phẩm có thể khởi động và thực hiện một số hành vi cốt lõi. Với artifact Java, smoke test nên chạy đúng file JAR/WAR/distribution mà pipeline dự định phát hành.

Smoke test thường xác nhận:

- JVM có thể nạp điểm vào.
- Manifest hoặc script khởi chạy hoạt động.
- Dependency runtime cần thiết có mặt.
- Resource và cấu hình được tìm thấy.
- Ứng dụng khởi động thành công.
- Một endpoint hoặc lệnh kiểm tra sức khỏe trả kết quả mong đợi.
- Ứng dụng có thể dừng sạch sau kiểm tra.

Smoke test không thay thế unit/integration test. Nó có phạm vi nhỏ, tập trung vào artifact và đường chạy khởi động quan trọng.

## 10. Chạy executable JAR trực tiếp

Với JAR có manifest `Main-Class` và dependency runtime đã được xử lý, chạy:

```bash
java -jar build/libs/application.jar
```

Nếu ứng dụng hỗ trợ chế độ kiểm tra nhanh, có thể truyền đối số:

```bash
java -jar build/libs/application.jar --self-test
```

`--self-test` chỉ là ví dụ; ứng dụng cần tự triển khai chức năng này. Một self-test tốt nên kiểm tra các điều kiện khởi động quan trọng mà không tạo dữ liệu production hoặc thực hiện tác dụng phụ không thể đảo ngược.

Nếu ứng dụng chạy như server, smoke test có thể khởi động tiến trình, đợi health endpoint sẵn sàng, gửi request kiểm tra rồi dừng tiến trình. Cần có timeout, xử lý exit code và dọn dẹp tiến trình ngay cả khi request thất bại.

### 10.1. Kiểm tra endpoint sau khởi động

Ví dụ lệnh chạy một server đã cấu hình health endpoint:

```bash
java -jar build/libs/application.jar --server.port=18080
```

Sau khi server sẵn sàng:

```bash
curl --fail --silent --show-error http://localhost:18080/actuator/health
```

Kết quả cần được kiểm tra theo hợp đồng của ứng dụng, ví dụ HTTP status thành công và body biểu thị trạng thái healthy. Không nên chỉ kiểm tra tiến trình còn tồn tại vì ứng dụng có thể đang khởi động dở hoặc không thể phục vụ request.

Sau kiểm tra, dừng server bằng cơ chế shutdown được hỗ trợ. Không để tiến trình smoke test còn chạy và chiếm port cho các job tiếp theo.

## 11. Chạy thử distribution đã giải nén

Nếu sản phẩm được phát hành dưới dạng ZIP/TAR, smoke test nên giải nén archive vào một thư mục tạm rồi chạy script khởi động bên trong. Việc chạy từ thư mục project gốc có thể vô tình sử dụng file hoặc dependency không có trong distribution.

Ví dụ trên Linux/macOS:

```bash
tmp_dir="$(mktemp -d)"
unzip -q build/distributions/application.zip -d "$tmp_dir"
find "$tmp_dir" -maxdepth 3 -type f
```

Sau đó chạy script trong thư mục `bin/` của distribution đã giải nén. Trong CI, cần dùng `trap` hoặc cơ chế cleanup tương ứng để xóa thư mục tạm và dừng tiến trình khi job kết thúc.

Trên PowerShell:

```powershell
$tempDir = Join-Path $env:TEMP ([guid]::NewGuid().ToString())
Expand-Archive -LiteralPath '.\build\distributions\application.zip' -DestinationPath $tempDir
Get-ChildItem -LiteralPath $tempDir -Recurse -File
```

Smoke test phải chạy đúng script và cấu trúc được đóng gói. Nếu script chỉ hoạt động khi đứng ở project root, có thể nó đang phụ thuộc working directory ngoài ý muốn.

## 12. Chạy thử WAR trên servlet container

Với WAR, cần xác định servlet container hoặc application server mà sản phẩm hỗ trợ, ví dụ Tomcat hoặc một server Jakarta EE tương thích. Các phiên bản container khác nhau có thể hỗ trợ namespace/API khác nhau, nên phải kiểm tra version matrix.

Quy trình smoke test thường gồm:

1. Khởi động container thử nghiệm.
2. Deploy đúng file WAR vừa tạo.
3. Chờ deployment hoàn tất và kiểm tra log.
4. Gọi health endpoint hoặc một luồng HTTP quan trọng.
5. Xác nhận status/body và các tương tác cần thiết.
6. Undeploy hoặc dừng container.

Không nên kiểm tra WAR bằng cách chỉ chạy các class trong `build/classes` hoặc `target/classes`; việc đó bỏ qua deployment descriptor, `WEB-INF/lib`, container class loading và các khác biệt runtime.

## 13. Tạo task kiểm tra nội dung JAR trong Gradle

Gradle có thể nối bước kiểm tra archive vào task graph. Ví dụ dưới đây tạo task xác nhận JAR có manifest và lớp chính.

```groovy
import org.gradle.api.tasks.bundling.Jar

def applicationJar = tasks.named('jar', Jar)

tasks.register('verifyJarLayout') {
    group = 'verification'
    description = 'Checks the packaged JAR manifest and entry point.'

    dependsOn(applicationJar)
    inputs.file(applicationJar.flatMap { it.archiveFile })

    doLast {
        def jarFile = applicationJar.get().archiveFile.get().asFile

        if (!jarFile.isFile() || jarFile.length() == 0) {
            throw new GradleException("JAR is missing or empty: ${jarFile}")
        }

        def zip = new java.util.zip.ZipFile(jarFile)
        try {
            def manifestEntry = zip.getEntry('META-INF/MANIFEST.MF')
            if (manifestEntry == null) {
                throw new GradleException('JAR has no META-INF/MANIFEST.MF')
            }

            def manifest
            zip.getInputStream(manifestEntry).withCloseable { stream ->
                manifest = new java.util.jar.Manifest(stream)
            }

            def mainClass = manifest.mainAttributes.getValue('Main-Class')
            if (mainClass != 'com.example.Application') {
                throw new GradleException("Unexpected Main-Class: ${mainClass}")
            }

            def mainEntry = mainClass.replace('.', '/') + '.class'
            if (zip.getEntry(mainEntry) == null) {
                throw new GradleException("Main class entry is missing: ${mainEntry}")
            }
        } finally {
            zip.close()
        }
    }
}

tasks.named('check') {
    dependsOn(tasks.named('verifyJarLayout'))
}
```

Task này:

- Chờ task `jar` tạo archive.
- Khai báo file JAR là input.
- Mở archive như ZIP và tìm manifest.
- Đọc `Main-Class` rồi xác nhận class entry tương ứng tồn tại.
- Làm build thất bại nếu cấu trúc không đúng.

Ví dụ giả định lớp chính là `com.example.Application`. Dự án cần thay tên này theo ứng dụng. Với JAR không phải executable, bỏ phần kiểm tra `Main-Class` và xác nhận các entry phù hợp với hợp đồng thư viện.

Task trên chỉ kiểm tra cấu trúc cơ bản. Nó chưa xác nhận dependency ngoài archive, startup, database, endpoint hoặc hành vi ứng dụng. Những điều đó cần smoke/integration test riêng.

## 14. Tạo task smoke test JAR trong Gradle

Nếu ứng dụng có chế độ `--self-test` trả exit code `0` khi kiểm tra thành công và khác `0` khi thất bại, có thể gọi artifact sau khi package bằng `Exec` task.

```groovy
import org.gradle.api.tasks.bundling.Jar

def applicationJar = tasks.named('jar', Jar)

tasks.register('smokeTestJar', Exec) {
    group = 'verification'
    description = 'Runs the packaged application self-test.'
    dependsOn(applicationJar)

    doFirst {
        def jarFile = applicationJar.get().archiveFile.get().asFile
        commandLine 'java', '-jar', jarFile.absolutePath, '--self-test'
    }
}

tasks.named('check') {
    dependsOn(tasks.named('smokeTestJar'))
}
```

Gradle thực thi lệnh `java -jar` trên file archive đã tạo. Nếu ứng dụng trả exit code khác `0`, task `Exec` thất bại và `check` thất bại.

Lưu ý:

- `java` phải có trong `PATH` của tiến trình Gradle. Với yêu cầu JDK cụ thể, nên cấu hình toolchain/Java launcher tương ứng thay vì dựa vào JDK mặc định của shell.
- Ứng dụng phải triển khai `--self-test`; nếu không, dùng một lệnh smoke test phù hợp với ứng dụng, chẳng hạn khởi động server và gọi health endpoint.
- Task `Exec` có tác dụng chạy tiến trình và thường không nên được cache như một task tạo output thuần túy.
- Không chạy smoke test có tác dụng phụ production trong `check` của mọi môi trường. Dùng endpoint mock, database tạm hoặc môi trường kiểm thử.

## 15. Maven: kiểm tra và chạy thử artifact

Maven có thể thực hiện kiểm tra artifact thông qua plugin goals được gắn vào lifecycle. Unit test thường chạy qua Surefire ở phase `test`; integration test thường dùng Failsafe ở các phase `integration-test` và `verify`.

Với kiểm tra artifact đã đóng gói, cần bảo đảm bước kiểm tra chạy sau khi `package` tạo ra JAR/WAR. Một integration test có thể khởi chạy JAR hoặc deploy WAR vào container thử nghiệm rồi xác nhận hành vi.

Ví dụ cấu hình Failsafe:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.2.5</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

Khi chạy:

```bash
mvn clean verify
```

Maven thực hiện các phase trước và tới `verify`; artifact đã được tạo ở `package`, sau đó integration test có thể kiểm tra sản phẩm. Failsafe không tự động biết cách khởi chạy mọi JAR/WAR; test code hoặc plugin hỗ trợ phải triển khai bước khởi động, chờ sẵn sàng, kiểm tra và cleanup.

### 15.1. Integration test khởi chạy JAR

Một test có thể dùng `ProcessBuilder` để chạy artifact được tạo trong `target/`, sau đó kiểm tra exit code hoặc output. Cần truyền đường dẫn artifact qua system property/plugin configuration hoặc xác định từ Maven build output theo cách ổn định.

Ví dụ Java minh họa cách khởi chạy một tiến trình:

```java
import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

public class PackagedApplicationSmokeTest {
    public static void main(String[] args) throws Exception {
        Path jar = Path.of("target", "application-1.0.0.jar").toAbsolutePath();

        Process process = new ProcessBuilder(
            "java", "-jar", jar.toString(), "--self-test"
        )
            .redirectErrorStream(true)
            .inheritIO()
            .start();

        boolean completed = process.waitFor(30, TimeUnit.SECONDS);
        if (!completed) {
            process.destroyForcibly();
            throw new IllegalStateException("Smoke test timed out");
        }

        if (process.exitValue() != 0) {
            throw new IllegalStateException(
                "Packaged application failed with exit code " + process.exitValue()
            );
        }
    }
}
```

Đây là ví dụ tối giản về timeout và exit code, không phải test framework hoàn chỉnh. Với JUnit/Failsafe, nên dùng assertion, quản lý output và cleanup trong `finally`, đồng thời lấy đường dẫn artifact từ cấu hình Maven thay vì hard-code version.

## 16. Kiểm tra artifact bằng CI

CI nên kiểm tra đúng artifact sẽ được publish hoặc deploy. Không nên chỉ chạy test trên source tree rồi tải một file khác từ thư mục build mà chưa xác minh.

Một pipeline có thể gồm:

1. Build sạch với toolchain/version đã chọn.
2. Chạy unit test và integration test.
3. Tạo JAR/WAR/distribution.
4. Kiểm tra cấu trúc archive và metadata.
5. Tính checksum hoặc xác minh chữ ký nếu quy trình yêu cầu.
6. Giải nén/chạy thử artifact trong môi trường tạm.
7. Lưu artifact và report.
8. Publish/deploy đúng file đã kiểm tra.

Ví dụ Gradle:

```bash
./gradlew clean check build
```

Nếu `check` đã phụ thuộc vào kiểm tra layout và smoke test, lệnh `build` sẽ sử dụng cùng graph theo dependency mặc định của Java plugin. Trong CI, có thể chọn một entry point chuẩn như `build` và bảo đảm các kiểm tra bắt buộc được nối vào lifecycle.

Ví dụ Maven:

```bash
mvn clean verify
```

Nếu integration test artifact được cấu hình qua Failsafe, `verify` là phase quan trọng để xác nhận kết quả sau package và integration-test.

### 16.1. Kiểm tra file thực sự được publish

Một lỗi pipeline phổ biến là kiểm tra `build/libs/application.jar` nhưng publish một file khác, chẳng hạn file có classifier hoặc version khác. Nên dùng cùng một output provider/property để:

- Kiểm tra artifact.
- Tính checksum.
- Lưu artifact CI.
- Upload/publish artifact.

Nếu publish từ repository sau khi upload, có thể tải lại artifact và so sánh checksum với file đã kiểm tra. Điều này xác nhận đường truyền publish/download không làm thay đổi nội dung.

## 17. Tính tái lập của artifact

Tính tái lập (reproducibility) nghĩa là cùng đầu vào được kiểm soát có thể tạo ra artifact tương đương hoặc giống byte-for-byte theo tiêu chí của dự án.

Một số yếu tố ảnh hưởng:

- Version JDK và build tool.
- Version dependency và repository metadata.
- Thời gian sửa file, timestamp archive hoặc thứ tự entry.
- Encoding, line ending và cách xử lý file permission.
- Biến môi trường, hostname, build number hoặc đường dẫn tuyệt đối được nhúng vào artifact.
- Generator tạo nội dung không xác định.
- Resource được thêm từ thư mục có trạng thái ngoài dự án.

Gradle archive task có các tùy chọn như `preserveFileTimestamps` và `reproducibleFileOrder` để hỗ trợ archive reproducible. Cấu hình cụ thể cần phù hợp yêu cầu và phiên bản Gradle.

Ví dụ:

```groovy
tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Khi artifact cần reproducible, có thể build hai lần trong môi trường sạch và so sánh SHA-256. Nếu checksum khác, cần xác định thành phần nào tạo khác biệt; checksum khác không tự chứng minh artifact sai, nhưng là tín hiệu cần điều tra khi dự án cam kết byte-for-byte reproducibility.

## 18. Kiểm tra nội dung không mong muốn và thông tin nhạy cảm

Artifact là sản phẩm có thể được gửi cho khách hàng hoặc triển khai công khai. Vì vậy, ngoài kiểm tra file bắt buộc, cần xác nhận không đóng gói nhầm:

- `.env`, file credential, token, private key hoặc mật khẩu.
- File cấu hình cá nhân và đường dẫn local.
- Source map hoặc debug dump không được phép phân phối.
- Test fixture chứa dữ liệu cá nhân hoặc dữ liệu production.
- Log, dump, cache và file tạm.
- Dependency hoặc thư viện không được phép phân phối.

Không nên chỉ tìm theo tên file. Secret có thể nằm trong properties, YAML, JSON, manifest hoặc resource bất kỳ. Dự án có yêu cầu bảo mật nên dùng scanner phù hợp trên artifact và kiểm tra license/dependency theo chính sách tổ chức.

## 19. Những lỗi thường gặp khi kiểm tra artifact

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| IDE chạy được nhưng `java -jar` thất bại | JAR thiếu dependency hoặc manifest sai | Kiểm tra manifest, runtime dependency và packaging strategy |
| `no main manifest attribute` | Không khai báo Main-Class cho executable JAR | Cấu hình Gradle/Maven manifest hoặc dùng Application distribution |
| `NoClassDefFoundError` sau đóng gói | Dependency có trên IDE classpath nhưng không được phân phối | Tạo distribution có `lib/`, khai báo Class-Path hoặc fat JAR |
| JAR không có resource | Resource chưa được thêm vào source set hoặc task processResources | Kiểm tra output resource và archive entries |
| WAR deploy thất bại | Sai cấu trúc `WEB-INF`, thiếu dependency hoặc không tương thích container | Inspect WAR và chạy thử trên container đúng version |
| Fat JAR mất service provider | `META-INF/services` bị ghi đè khi merge | Cấu hình merge service descriptors và test ServiceLoader |
| Archive đọc được nhưng ứng dụng lỗi | Cấu trúc ZIP hợp lệ nhưng nội dung hoặc runtime dependency sai | Kiểm tra entry, manifest và smoke test |
| Artifact publish khác artifact đã kiểm tra | Pipeline dùng đường dẫn/file khác ở bước upload | Dùng cùng output provider và so checksum sau upload |
| Script distribution không chạy trên Linux | Thiếu executable bit, line ending sai hoặc shebang không hợp lệ | Kiểm tra mode, LF và chạy thử sau khi giải nén |
| Smoke test treo | Server không sẵn sàng, thiếu timeout hoặc cleanup | Đặt timeout, readiness probe và dọn dẹp tiến trình |
| Artifact có secret | File cấu hình hoặc metadata nhạy cảm bị đóng gói | Scan artifact và chuyển secret sang runtime/secret store |
| Checksum khác giữa hai lần build | Timestamp, thứ tự entry hoặc dữ liệu môi trường thay đổi | Kiểm tra reproducible archive và nguồn input không xác định |

## 20. Quy trình kiểm tra artifact từ đầu đến cuối

Có thể dùng trình tự sau cho một lần build phát hành:

1. **Xác định sản phẩm:** JAR, WAR, ZIP/TAR hay container image; ghi nhận output path và version.
2. **Xác nhận file được tạo:** kiểm tra tồn tại, kích thước và thời gian.
3. **Kiểm tra archive:** xác nhận cấu trúc ZIP/JAR/WAR đọc được và không hỏng.
4. **Kiểm tra nội dung:** class, resource, manifest, dependency layout và file cần thiết.
5. **Kiểm tra metadata:** Main-Class, version, classifier, POM/module metadata và cấu hình launch.
6. **Kiểm tra integrity/provenance:** checksum, chữ ký và dependency verification theo chính sách.
7. **Kiểm tra file không mong muốn:** secret, dữ liệu local, test fixture và file tạm.
8. **Chạy thử artifact:** khởi động đúng JAR/script/WAR/container đã đóng gói.
9. **Kiểm tra hành vi:** health endpoint, lệnh self-test hoặc luồng nghiệp vụ tối thiểu.
10. **Dọn dẹp:** dừng process, undeploy, xóa thư mục tạm và thu hồi tài nguyên test.
11. **Lưu bằng chứng:** log, report, checksum và artifact đã xác minh.
12. **Publish/deploy:** sử dụng chính file đã qua các bước kiểm tra.

## 21. Mức kiểm tra theo loại sản phẩm

Không phải mọi artifact cần cùng một bộ smoke test. Có thể chọn mức kiểm tra theo mục đích:

| Sản phẩm | Kiểm tra cấu trúc tối thiểu | Smoke test phù hợp |
|---|---|---|
| JAR thư viện | Class/API, resource, POM/module metadata, sources/Javadoc nếu phát hành | Consumer sample project compile và chạy một API đại diện |
| Executable JAR | Manifest, Main-Class, dependency/runtime layout | `java -jar` với self-test hoặc khởi động và gọi health endpoint |
| Fat JAR | Class/resource merge, service descriptors, license, manifest | Chạy artifact độc lập trong môi trường sạch |
| WAR | `WEB-INF/classes`, `WEB-INF/lib`, resource và descriptor | Deploy lên servlet container tương thích, gọi endpoint |
| Distribution ZIP/TAR | Cây thư mục, script, lib, config, permissions | Giải nén sang thư mục tạm và chạy script như người dùng |
| Container image | Entrypoint, command, user, port, JAR/config | Chạy container và kiểm tra health/readiness |

Với thư viện, việc compile một consumer sample có giá trị đặc biệt vì nó xác nhận metadata publication và dependency graph có thể được consumer sử dụng. Với ứng dụng, chạy file artifact thật thường quan trọng hơn việc chỉ kiểm tra class output.

## 22. Kết luận

Kiểm tra artifact xác nhận sản phẩm đóng gói có cấu trúc, nội dung và metadata đúng như hợp đồng phát hành. Chạy thử artifact xác nhận sản phẩm có thể khởi động và thực hiện một hành vi cốt lõi trong môi trường gần với cách người dùng sẽ sử dụng.

JAR/WAR/ZIP cần được kiểm tra bằng công cụ archive, manifest, class/resource inspection và các công cụ phân tích phù hợp. Sau đó, smoke test phải chạy đúng file hoặc distribution đã tạo, không vô tình dùng classpath đầy đủ của IDE hoặc thư mục build khác. Với Gradle, có thể nối kiểm tra layout và smoke test vào `check`; với Maven, có thể tích hợp kiểm tra sau package qua Failsafe hoặc plugin chuyên dụng.

Một artifact chỉ nên được publish hoặc deploy sau khi các kiểm tra cần thiết đã đạt. Việc lưu checksum, report, log và chính file đã kiểm tra giúp pipeline có thể truy vết sản phẩm được phát hành và giảm rủi ro khác biệt giữa môi trường phát triển, CI và production.
